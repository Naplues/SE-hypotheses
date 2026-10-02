"""Analyze the original selected cells plus two follow-up repetitions.

All run-level records retain source paths. Inferential units are tasks, not
individual repetitions. Follow-up-only comparisons avoid conditioning tests
on the outcomes used to select the sensitive cohort.
"""
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats
import scipy

ROOT=Path('/Users/gzq/Repo/FSE2027')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/repeated-runs-2026-10-02'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'src'))
from rfm.trajectory_extraction import extract_trajectory

CONDS=['ORIG','CH','WLH','WCH','WRH']
SEED=20261002
METRICS=['elapsed_seconds','time_to_first_successful_edit_seconds','total_tokens','tool_calls','search_read_calls','edit_calls','test_calls']
selection=json.loads((ROOT/'repeated-experiment-instances.json').read_text())
sets={'sensitive':[x['instance_id'] for x in selection['sensitive_tasks']],
      'stable':selection['stable_tasks']['all_resolved']+selection['stable_tasks']['all_unresolved']}
signature0={x['instance_id']:x['outcome_signature'] for x in selection['sensitive_tasks']}
for t in selection['stable_tasks']['all_resolved']:signature0[t]='11111'
for t in selection['stable_tasks']['all_unresolved']:signature0[t]='00000'
rows=[];audit=[];patches={}; configs=Counter();templates=Counter();duplicate_reports=[]
all_tasks=set(sum(sets.values(),[]))
for ci,c in enumerate(CONDS):
 folder='ORGI' if c=='ORIG' else c
 p=ROOT/'results'/folder/'trajectory-features.csv'
 for r in csv.DictReader(p.open()):
  t=r['instance_id']
  if t not in all_tasks:continue
  cohort='sensitive' if t in sets['sensitive'] else 'stable'
  outcome=r['evaluator_resolved']=='True'
  assert r['evaluator_resolved'] in ['True','False']
  assert int(outcome)==int(signature0[t][ci])
  rawpath=ROOT/'result'/('glm46_'+folder)/'mini_run'/t/(t+'.traj.json')
  raw=json.loads(rawpath.read_text()) if rawpath.exists() else None
  patch=raw['info'].get('submission','') if raw else ''
  patches[(t,c,0)]=patch
  m={k:float(r[k]) if r.get(k) else None for k in METRICS}
  rows.append(dict(cohort=cohort,instance_id=t,condition=c,round=0,resolved=int(outcome),uncertain=False,
    uncertainty_reason='',exit_status=raw['info'].get('exit_status') if raw else r['status'],source=str(p),
    modified_files=r['modified_files'],patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),**m))

for cohort,tasks in sets.items():
 for rd in [1,2]:
  for c in CONDS:
   cd=ROOT/'result'/('glm46_'+cohort)/('round'+str(rd))/c
   summaries=[]
   for p in cd.glob('*.json'):
    d=json.loads(p.read_text())
    if isinstance(d,dict) and 'resolved_ids' in d:summaries.append((p,d))
   assert len(summaries)==1,(cohort,rd,c)
   sp,s=summaries[0]
   resolved=set(s['resolved_ids']);unresolved=set(s['unresolved_ids']);empty=set(s.get('empty_patch_ids',[]))
   assert not resolved&unresolved
   assert resolved|unresolved|empty==set(tasks)
   reports={}
   for p in cd.glob('logs/**/report.json'):
    for t,v in json.loads(p.read_text()).items():
     if t in reports:duplicate_reports.append(str(p))
     reports[t]=(p,v)
   seen=set()
   for p in sorted(cd.glob('mini_run/*/*.traj.json')):
    raw=json.loads(p.read_text());t=raw['instance_id'];assert t not in seen;seen.add(t)
    record,events=extract_trajectory(raw,source_file=str(p),condition=c)
    info=raw['info'];patch=info.get('submission','') or ''
    patches[(t,c,rd)]=patch
    pred=json.loads((cd/'mini_run/preds.json').read_text())[t].get('model_patch','') or ''
    assert pred==patch,(t,c,rd,'prediction does not match recorded submission')
    outcome=int(t in resolved)
    if t in reports:assert bool(reports[t][1]['resolved'])==bool(outcome),(t,c,rd,'grade mismatch')
    else:assert t in empty,(t,c,rd,'missing nonempty evaluation report')
    failure_reason=s.get('failure_reasons',{}).get(t,'')
    exit_status=info.get('exit_status','')
    ambiguous=t in s.get('ambiguous_failure_ids',[])
    infra=t in s.get('infra_failure_ids',[]) or exit_status in ['RateLimitError','APIError','AuthenticationError','ConnectionError']
    uncertain=ambiguous or infra
    if uncertain or not patch or exit_status!='Submitted':
     audit.append(dict(cohort=cohort,round=rd,condition=c,instance_id=t,exit_status=exit_status,
       empty_patch=not bool(patch),ambiguous=ambiguous,infra=infra,reason=failure_reason,
       report_present=t in reports,summary_path=str(sp),trajectory_path=str(p)))
    hypothesis=record['developer_hypothesis_present']
    assert hypothesis==(c!='ORIG'),(t,c,rd,'hypothesis exposure mismatch')
    firstuser=next(m['content'] for m in raw['messages'] if m['role']=='user')
    if c!='ORIG':
     prompt=(ROOT/'data/heuristic-prompts'/c/(t+'.txt')).read_text().strip()
     assert prompt in firstuser,(t,c,rd,'prompt mismatch')
    config=info['config'];agent=config['agent'];model=config['model']
    cfg=(cohort,info.get('mini_version'),model.get('model_name'),agent.get('step_limit'),agent.get('wall_time_limit_seconds'),json.dumps(model.get('model_kwargs'),sort_keys=True))
    configs[cfg]+=1
    templates[(cohort,hashlib.sha256(agent['system_template'].encode()).hexdigest(),hashlib.sha256(agent['instance_template'].encode()).hexdigest())]+=1
    rows.append(dict(cohort=cohort,instance_id=t,condition=c,round=rd,resolved=outcome,
      uncertain=uncertain,uncertainty_reason=failure_reason or (exit_status if infra else ''),exit_status=exit_status,
      source=str(p),evaluation_source=str(reports[t][0]) if t in reports else str(sp),
      modified_files=';'.join(record['modified_files']),patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),
      **{k:record[k] for k in METRICS}))
   assert seen==set(tasks),(cohort,rd,c,'coverage')
assert len(rows)==1260
assert not duplicate_reports
lookup={(r['instance_id'],r['condition'],r['round']):r for r in rows}
with (OUT/'run-level.csv').open('w',newline='') as f:
 fields=sorted(set().union(*(r.keys() for r in rows)));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(OUT/'data-quality-audit.json').write_text(json.dumps(dict(issues=audit,configurations=[dict(values=k,count=v) for k,v in configs.items()],templates=[dict(values=k,count=v) for k,v in templates.items()]),indent=2))

def matrix(tasks,rd):return np.array([[lookup[(t,c,rd)]['resolved'] for c in CONDS] for t in tasks])
def wilson(k,n):
 z=1.95996398454;p=k/n;d=1+z*z/n
 center=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return [center-h,center+h]
def bootstrap(values,stat='mean',B=20000):
 v=np.asarray(values,dtype=float);rng=np.random.default_rng(SEED);ix=rng.integers(len(v),size=(B,len(v)))
 z=np.mean(v[ix],axis=1) if stat=='mean' else np.median(v[ix],axis=1)
 return np.quantile(z,[.025,.975]).tolist()
def exact_signflip(d):
 a=np.rint(np.asarray(d)*2).astype(int);a=a[a!=0]
 distribution={0:1}
 for v in a:
  nxt=defaultdict(int)
  for total,n in distribution.items():nxt[total+int(v)]+=n;nxt[total-int(v)]+=n
  distribution=nxt
 target=abs(int(a.sum()))
 return sum(n for total,n in distribution.items() if abs(total)>=target)/(2**len(a))
def holm(ps):
 order=np.argsort(ps);adjusted=np.zeros(len(ps));running=0
 for i,j in enumerate(order):running=max(running,(len(ps)-i)*ps[j]);adjusted[j]=min(1,running)
 return adjusted.tolist()
def paired_effect(tasks,rounds,c,clean_cells=False):
 ds=[]
 for t in tasks:
  rs=[rd for rd in rounds if not clean_cells or not (lookup[(t,c,rd)]['uncertain'] or lookup[(t,'ORIG',rd)]['uncertain'])]
  if rs:ds.append(np.mean([lookup[(t,c,rd)]['resolved']-lookup[(t,'ORIG',rd)]['resolved'] for rd in rs]))
 return dict(n_tasks=len(ds),difference=float(np.mean(ds)),ci95=bootstrap(ds),p_task_signflip=exact_signflip(ds),
             favorable_tasks=int(np.sum(np.array(ds)>0)),unfavorable_tasks=int(np.sum(np.array(ds)<0)),tied_tasks=int(np.sum(np.array(ds)==0)))
def global_permutation(mat,B=49999):
 rng=np.random.default_rng(SEED);n=len(mat)
 observed=float(np.sum((mat.sum(axis=0)-mat.sum()/5)**2))
 exceeds=0
 for _ in range(B//1000+1):
  size=min(1000,B-_ *1000)
  if size<=0:break
  order=np.argsort(rng.random((size,n,5)),axis=2)
  shuffled=np.take_along_axis(np.broadcast_to(mat,(size,n,5)),order,axis=2)
  scores=np.sum((shuffled.sum(axis=1)-mat.sum()/5)**2,axis=1)
  exceeds+=int(np.sum(scores>=observed-1e-12))
 return dict(statistic=observed,p=(exceeds+1)/(B+1),permutations=B,seed=SEED)

summary={'seed':SEED,'versions':dict(numpy=np.__version__,scipy=scipy.__version__),
 'design':'Round0 selected tasks; round1/round2 additional independent executions. Repetitions clustered within task.',
 'cohorts':{},'followup_effects':[],'clean_followup_effects':[],'case_replication':{},'process_effects':[]}
taskrows=[]
for cohort,tasks in sets.items():
 mats=[matrix(tasks,rd) for rd in [0,1,2]]
 stack=np.stack(mats,axis=1)
 badtasks={r['instance_id'] for r in rows if r['cohort']==cohort and r['uncertain']}
 clean=[t for t in tasks if t not in badtasks]
 out=dict(n_tasks=len(tasks),condition_order=CONDS,round_success_counts=[m.sum(axis=0).tolist() for m in mats],
          followup_success_counts=(mats[1]+mats[2]).sum(axis=0).tolist(),
          three_run_success_counts=stack.sum(axis=(0,1)).tolist(),excluded_for_balanced_clean=list(sorted(badtasks)),
          clean_n=len(clean),global_condition_test_followup=global_permutation((mats[1]+mats[2])/2))
 out['round_sensitive_task_counts']=[int(np.sum(m.max(axis=1)!=m.min(axis=1))) for m in mats]
 out['round_exact_signature_reproductions']=[int(np.sum(np.all(m==mats[0],axis=1))) for m in mats]
 out['both_followup_exact_signature_reproductions']=int(np.sum(np.all(mats[1]==mats[0],axis=1)&np.all(mats[2]==mats[0],axis=1)))
 same_dis=(stack.max(axis=1)!=stack.min(axis=1))
 out['variable_task_condition_cells']=int(same_dis.sum());out['total_task_condition_cells']=len(tasks)*5
 out['tasks_with_same_condition_variability']=int(np.any(same_dis,axis=1).sum())
 out['tasks_with_any_outcome_variability_all15']=int(np.sum(stack.max(axis=(1,2))!=stack.min(axis=(1,2))))
 out['pairwise_round_disagreement_counts']={f'{a}-{b}':int(np.sum(mats[a]!=mats[b])) for a,b in [(0,1),(0,2),(1,2)]}
 within=np.mean(mats[1]!=mats[2],axis=1)
 across=np.array([np.mean([m[t,i]!=m[t,j] for m in mats[1:] for i in range(5) for j in range(i+1,5)]) for t in range(len(tasks))])
 out['followup_within_condition_disagreement']=dict(mean=float(within.mean()),ci95=bootstrap(within))
 out['followup_cross_condition_disagreement']=dict(mean=float(across.mean()),ci95=bootstrap(across))
 out['cross_minus_within_disagreement']=dict(mean=float((across-within).mean()),ci95=bootstrap(across-within))
 if clean:
  cm=[matrix(clean,r) for r in [0,1,2]];cs=np.stack(cm,axis=1)
  out['clean_balanced']=dict(round_success_counts=[m.sum(axis=0).tolist() for m in cm],
       variable_task_condition_cells=int(np.sum(cs.max(axis=1)!=cs.min(axis=1))),
       tasks_with_variability_all15=int(np.sum(cs.max(axis=(1,2))!=cs.min(axis=(1,2)))),
       round_sensitive_task_counts=[int(np.sum(m.max(axis=1)!=m.min(axis=1))) for m in cm])
 for t,arr in zip(tasks,stack):
  signatures=[''.join(map(str,arr[rd].tolist())) for rd in [0,1,2]]
  counts=arr.sum(axis=0);majority=''.join(str(int(v>=2)) for v in counts)
  tr=dict(cohort=cohort,instance_id=t,original_signature=signatures[0],round1_signature=signatures[1],round2_signature=signatures[2],
       three_run_majority_signature=majority,variable_conditions=int(np.sum(arr.max(axis=0)!=arr.min(axis=0))),
       has_flagged_evaluation=t in badtasks)
  for ci,c in enumerate(CONDS):
   tr[c+'_outcomes']=''.join(str(arr[rd,ci]) for rd in range(3));tr[c+'_successes_of3']=int(counts[ci])
  taskrows.append(tr)
 out['majority_sensitive_task_count']=sum(len(set(tr['three_run_majority_signature']))>1 for tr in taskrows if tr['cohort']==cohort)
 out['majority_signature_matches_original']=sum(tr['three_run_majority_signature']==tr['original_signature'] for tr in taskrows if tr['cohort']==cohort)
 summary['cohorts'][cohort]=out
 for c in CONDS[1:]:
  summary['followup_effects'].append(dict(cohort=cohort,condition=c,**paired_effect(tasks,[1,2],c)))
  summary['clean_followup_effects'].append(dict(cohort=cohort,condition=c,**paired_effect(clean,[1,2],c)))
 for metric in METRICS:
  for c in CONDS[1:]:
   diffs=[];reldiffs=[]
   for t in tasks:
    pairs=[];relative=[]
    for rd in [1,2]:
     a,b=lookup[(t,c,rd)],lookup[(t,'ORIG',rd)]
     if a['uncertain'] or b['uncertain']:continue
     if a[metric] is None or b[metric] is None:continue
     pairs.append(a[metric]-b[metric])
     if b[metric]>0:relative.append(a[metric]/b[metric]-1)
    if pairs:diffs.append(float(np.mean(pairs)))
    if relative:reldiffs.append(float(np.mean(relative)))
   ds=np.array(diffs);nonzero=ds[ds!=0]
   if len(nonzero):
    ranks=stats.rankdata(abs(nonzero));rbc=float(np.sum(np.sign(nonzero)*ranks)/sum(ranks))
    w=stats.wilcoxon(ds,alternative='two-sided',zero_method='wilcox',method='approx')
    p=float(w.pvalue);W=float(w.statistic)
   else:rbc=0;p=1;W=0
   summary['process_effects'].append(dict(cohort=cohort,condition=c,metric=metric,n_tasks=len(ds),
       mean_difference=float(ds.mean()),median_difference=float(np.median(ds)),median_relative_difference=float(np.median(reldiffs)) if reldiffs else None,
       median_ci95=bootstrap(ds,'median'),p_wilcoxon=p,W=W,rank_biserial=rbc,
       normality_of_differences_p=float(stats.shapiro(ds).pvalue) if len(set(ds))>1 else None,
       nonzero_n=len(nonzero)))
for family in ['followup_effects','clean_followup_effects']:
 for result,p in zip(summary[family],holm([r['p_task_signflip'] for r in summary[family]])):result['p_holm_eight']=p
for cohort in sets:
 family=[r for r in summary['process_effects'] if r['cohort']==cohort]
 for r,p in zip(family,holm([x['p_wilcoxon'] for x in family])):r['p_holm_28']=p

for task in ['sympy__sympy-20428','django__django-17084','astropy__astropy-13033','pylint-dev__pylint-7080','django__django-14765','astropy__astropy-7606','scikit-learn__scikit-learn-14629','sympy__sympy-13877']:
 summary['case_replication'][task]=dict(outcomes={c:[lookup[(task,c,rd)]['resolved'] for rd in [0,1,2]] for c in CONDS},
       modified_files={c:[lookup[(task,c,rd)]['modified_files'] for rd in [0,1,2]] for c in CONDS})

# Exact patch identity exposes evaluator inconsistency, not model variability.
patch_conflicts=[]
for t in all_tasks:
 byhash=defaultdict(list)
 for c in CONDS:
  for rd in [0,1,2]:
   patch=patches[(t,c,rd)]
   if not patch.strip():continue
   byhash[hashlib.sha256(patch.encode()).hexdigest()].append(lookup[(t,c,rd)])
 for h,rs in byhash.items():
  if len({r['resolved'] for r in rs})>1:
   patch_conflicts.append(dict(instance_id=t,patch_sha256=h,cells=[dict(condition=r['condition'],round=r['round'],resolved=r['resolved'],uncertain=r['uncertain'],source=r['source']) for r in rs]))
summary['identical_patch_outcome_conflicts']=patch_conflicts

for cohort in sets:
 tasks=sets[cohort];flips=[]
 for c in CONDS[1:]:
  gains=[];losses=[];rep_gain=[];rep_loss=[];reverse_gain=[];reverse_loss=[]
  for t in tasks:
   d0=lookup[(t,c,0)]['resolved']-lookup[(t,'ORIG',0)]['resolved']
   ds=[lookup[(t,c,rd)]['resolved']-lookup[(t,'ORIG',rd)]['resolved'] for rd in [1,2]]
   if d0>0:gains.append(t);rep_gain.append(sum(x>0 for x in ds));reverse_gain.append(sum(x<0 for x in ds))
   if d0<0:losses.append(t);rep_loss.append(sum(x<0 for x in ds));reverse_loss.append(sum(x>0 for x in ds))
  flips.append(dict(condition=c,original_gains=len(gains),original_losses=len(losses),
   gain_reproduced_in_both=sum(v==2 for v in rep_gain),gain_reproduced_in_at_least_one=sum(v>0 for v in rep_gain),
   loss_reproduced_in_both=sum(v==2 for v in rep_loss),loss_reproduced_in_at_least_one=sum(v>0 for v in rep_loss),
   gain_reproduction_observations=sum(rep_gain),gain_opposite_observations=sum(reverse_gain),
   loss_reproduction_observations=sum(rep_loss),loss_opposite_observations=sum(reverse_loss)))
 summary['cohorts'][cohort]['original_flip_replication']=flips

# Verify normalized evaluation metadata, not merely its JSON representation.
metadata_issues=[]
metadata_fields=['base_commit','test_patch','patch','FAIL_TO_PASS','PASS_TO_PASS','version']
for cohort,tasks in sets.items():
 for rd in [1,2]:
  datasets={}
  for c in CONDS:
   datasets[c]={}
   for p in (ROOT/'result'/('glm46_'+cohort)/f'round{rd}'/c/'dataset').glob('*.json'):
    d=json.loads(p.read_text());d=d[0] if isinstance(d,list) else d
    datasets[c][d['instance_id']]=d
  for t in tasks:
   for c in CONDS[1:]:
    for k in metadata_fields:
     a,b=datasets['ORIG'][t].get(k),datasets[c][t].get(k)
     if k in ['FAIL_TO_PASS','PASS_TO_PASS']:
      if isinstance(a,str):a=json.loads(a)
      if isinstance(b,str):b=json.loads(b)
      a,b=sorted(a),sorted(b)
     if a!=b:
      metadata_issues.append(dict(cohort=cohort,round=rd,condition=c,instance_id=t,field=k,
       only_original=list(set(a)-set(b)) if isinstance(a,list) else None,
       only_condition=list(set(b)-set(a)) if isinstance(b,list) else None))
summary['evaluation_metadata_mismatches']=metadata_issues
summary['strict_audit_sensitivity']={}
for cohort,tasks in sets.items():
 excluded={r['instance_id'] for r in rows if r['cohort']==cohort and r['uncertain']}
 excluded|={r['instance_id'] for r in patch_conflicts}
 excluded|={r['instance_id'] for r in metadata_issues}
 clean=[t for t in tasks if t not in excluded]
 mats=[matrix(clean,r) for r in [0,1,2]]
 summary['strict_audit_sensitivity'][cohort]=dict(n_tasks=len(clean),excluded_tasks=sorted(set(tasks)&excluded),
  round_success_counts=[m.sum(axis=0).tolist() for m in mats],
  within_condition_followup_disagreement=float(np.mean(mats[1]!=mats[2])),
  effects=[dict(condition=c,**paired_effect(clean,[1,2],c)) for c in CONDS[1:]])

for name,data in [('task-level.csv',taskrows),('followup-condition-effects.csv',summary['followup_effects']),('process-effects.csv',summary['process_effects'])]:
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in summary.items() if k!='process_effects'},indent=2))
