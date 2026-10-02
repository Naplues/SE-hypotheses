"""Recompute all available evidence without relabeling or executing agents.

Exploratory synthesis. Original 272-task estimates and selected repeated cohorts
are never pooled as if sampling probabilities were equal.
"""
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats
import scipy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path('/Users/gzq/Repo/FSE2027')
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'analysis/fse-comprehensive-2026-10-02'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'src'))
from rfm.trajectory_extraction import extract_trajectory
from rfm.swebench import load_swebench

CONDS=['ORIG','CH','WLH','WCH','WRH'];SEED=20261002;B=20000
METRICS=['elapsed_seconds','time_to_first_successful_edit_seconds','total_tokens','steps','tool_calls','search_read_calls','edit_calls','test_calls','modified_file_count','patch_added_lines','patch_deleted_lines','gold_file_precision','gold_file_recall','gold_added_line_recall','gold_removed_line_recall','submitted_added_line_precision']
tasks={t.instance_id:t for t in load_swebench(ROOT/'data/swebench_verified_test.jsonl')}
orig={};raws={};source_manifest=[]
for c in CONDS:
 folder='ORGI' if c=='ORIG' else c;p=ROOT/'results'/folder/'trajectory-features.csv'
 source_manifest.append(dict(evidence_id='E_ORIG_'+c,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),verification='machine_checked; human verification pending'))
 orig[c]={}
 for row in csv.DictReader(p.open()):
  t=row['instance_id'];r={**row,'condition':c,'round':0,'cohort':'full_original'}
  r['resolved']=None if row['evaluator_resolved']=='' else int(row['evaluator_resolved']=='True')
  for m in METRICS:r[m]=float(row[m]) if row[m] else None
  orig[c][t]=r
  rawpath=ROOT/'result'/('glm46_'+folder)/'mini_run'/t/(t+'.traj.json')
  raws[(t,c,0)]=json.loads(rawpath.read_text())
assert all(len(x)==272 for x in orig.values())
ids=sorted(orig['ORIG'])

def holm(ps):
 order=np.argsort(ps);out=np.zeros(len(ps));prev=0
 for i,j in enumerate(order):prev=max(prev,(len(ps)-i)*ps[j]);out[j]=min(1,prev)
 return out.tolist()
def bootstrap(a,kind='mean'):
 a=np.array(a,float);rng=np.random.default_rng(SEED);ix=rng.integers(len(a),size=(B,len(a)))
 z=a[ix].mean(axis=1) if kind=='mean' else np.median(a[ix],axis=1)
 return np.quantile(z,[.025,.975]).tolist()
def wilson(k,n):
 z=stats.norm.ppf(.975);p=k/n;d=1+z*z/n;center=(p+z*z/(2*n))/d;h=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return [float(center-h),float(center+h)]
def process_stat(ds,rels):
 ds=np.array(ds,float);nz=ds[ds!=0];rank=stats.rankdata(abs(nz)) if len(nz) else []
 p=float(stats.wilcoxon(ds,zero_method='wilcox',method='approx').pvalue) if len(nz) else 1
 signp=float(stats.binomtest(int(sum(nz>0)),len(nz),.5).pvalue) if len(nz) else 1
 q1,q3=np.quantile(ds,[.25,.75]);iq=q3-q1
 return dict(n=len(ds),nonzero_n=len(nz),mean_difference=float(ds.mean()),median_difference=float(np.median(ds)),median_relative_change=float(np.median(rels)) if rels else None,
  ci95_median=bootstrap(ds,'median'),rank_biserial=float(np.sum(np.sign(nz)*rank)/sum(rank)) if len(nz) else 0,
  W=float(stats.wilcoxon(ds,method='approx').statistic) if len(nz) else 0,p_wilcoxon=p,p_sign=signp,
  normality_p=float(stats.shapiro(ds).pvalue) if len(set(ds))>1 else None,
  outliers_IQR_n=int(sum((ds<q1-1.5*iq)|(ds>q3+1.5*iq))),positive_n=int(sum(ds>0)),negative_n=int(sum(ds<0)),zero_n=int(sum(ds==0)))
def outcomes(useids):
 rate=[];effects=[]
 for c in CONDS:
  a=[orig[c][t]['resolved'] for t in useids if orig[c][t]['resolved'] is not None];n=len(a);k=sum(a)
  rate.append(dict(condition=c,n=n,resolved=k,rate=k/n,ci95_wilson=wilson(k,n)))
 for c in CONDS[1:]:
  use=[t for t in useids if orig[c][t]['resolved'] is not None and orig['ORIG'][t]['resolved'] is not None]
  ds=[orig[c][t]['resolved']-orig['ORIG'][t]['resolved'] for t in use];g=sum(d>0 for d in ds);l=sum(d<0 for d in ds)
  effects.append(dict(condition=c,n=len(use),gains=g,losses=l,difference=float(np.mean(ds)),ci95=bootstrap(ds),p_exact=float(stats.binomtest(g,g+l,.5).pvalue) if g+l else 1))
 for r,p in zip(effects,holm([r['p_exact'] for r in effects])):r['p_holm']=p
 return dict(rates=rate,effects=effects)

def process(useids):
 rows=[]
 for m in METRICS:
  for c in CONDS[1:]:
   ds=[];rels=[]
   for t in useids:
    a,b=orig[c][t][m],orig['ORIG'][t][m]
    if a is None or b is None:continue
    ds.append(a-b)
    if b>0:rels.append(a/b-1)
   rows.append(dict(condition=c,metric=m,**process_stat(ds,rels)))
 for m in METRICS:
  fam=[r for r in rows if r['metric']==m]
  for r,p in zip(fam,holm([r['p_wilcoxon'] for r in fam])):r['p_holm_four']=p
 for r,p,q in zip(rows,holm([x['p_wilcoxon'] for x in rows]),holm([x['p_sign'] for x in rows])):r['p_holm_64']=p;r['p_sign_holm_64']=q
 return rows

summary=dict(seed=SEED,versions=dict(numpy=np.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__),original=outcomes(ids),original_process=process(ids))
complete=[t for t in ids if all(orig[c][t]['resolved'] is not None for c in CONDS)]
signatures={t:''.join(str(orig[c][t]['resolved']) for c in CONDS) for t in complete}
summary['original_outcome_signatures']=dict(Counter(signatures.values()))
summary['missing_outcomes']=[dict(instance_id=t,condition=c) for c in CONDS for t in ids if orig[c][t]['resolved'] is None]
summary['original_repositories']=dict(Counter(orig['ORIG'][t]['repo'] for t in ids))

# All original evaluation specifications, normalized for string/list representation.
specs={};metadata=[]
for c in CONDS:
 folder='ORGI' if c=='ORIG' else c;base=ROOT/'result'/('glm46_'+folder);ds={}
 for sub in ['testds','dataset']:
  for p in (base/sub).glob('*.json'):
   d=json.loads(p.read_text());d=d[0] if isinstance(d,list) else d
   if d.get('instance_id') in ids:ds[d['instance_id']]=d
 specs[c]=ds
for t in ids:
 for c in CONDS[1:]:
  if t not in specs[c] or t not in specs['ORIG']:
   metadata.append(dict(instance_id=t,condition=c,field='missing_specification'));continue
  for k in ['base_commit','test_patch','patch','FAIL_TO_PASS','PASS_TO_PASS','version']:
   a,b=specs['ORIG'][t].get(k),specs[c][t].get(k)
   if k in ['FAIL_TO_PASS','PASS_TO_PASS']:
    if isinstance(a,str):a=json.loads(a)
    if isinstance(b,str):b=json.loads(b)
    a,b=sorted(a),sorted(b)
   if a!=b:metadata.append(dict(instance_id=t,condition=c,field=k,only_original=list(set(a)-set(b)) if isinstance(a,list) else None,only_condition=list(set(b)-set(a)) if isinstance(b,list) else None))
summary['original_metadata_mismatches']=metadata
# Stored task inputs and the actual evaluator report can be different versions.
report_spec_disagreements=[];reports={}
for c in CONDS:
 folder='ORGI' if c=='ORIG' else c
 for p in (ROOT/'result'/('glm46_'+folder)).glob('logs/**/report.json'):
  for t,d in json.loads(p.read_text()).items():
   if t not in ids:continue
   reports[(t,c)]=d
   for field,category in [('FAIL_TO_PASS','FAIL_TO_PASS'),('PASS_TO_PASS','PASS_TO_PASS')]:
    value=specs[c].get(t,{}).get(field)
    if value is None:continue
    if isinstance(value,str):value=json.loads(value)
    expected=set(x for x in value if x)
    group=d.get('tests_status',{}).get(category,{})
    observed=set(group.get('success',[])+group.get('failure',[]))
    if expected!=observed:report_spec_disagreements.append(dict(instance_id=t,condition=c,field=field,
      only_stored_spec=sorted(expected-observed),only_actual_report=sorted(observed-expected),report=str(p)))
summary['stored_spec_vs_evaluator_report_disagreements']=report_spec_disagreements
summary['report_spec_disagreement_explanations']={'django__django-10554/WRH':'Report says patch_successfully_applied=False; absent test categories are not evidence of a changed test specification.'}

# Exact exposure, patch conflicts, recorded configurations and abnormal terminations.
conflicts=[];quality=[];configs=Counter();prompt_mismatches=[]
for t in ids:
 byhash=defaultdict(list)
 for c in CONDS:
  raw=raws[(t,c,0)];info=raw['info'];patch=info.get('submission','') or ''
  if patch.strip():byhash[hashlib.sha256(patch.encode()).hexdigest()].append(dict(condition=c,resolved=orig[c][t]['resolved']))
  if info.get('exit_status')!='Submitted':quality.append(dict(instance_id=t,condition=c,exit_status=info.get('exit_status'),empty_patch=not bool(patch)))
  user=next(m['content'] for m in raw['messages'] if m['role']=='user')
  if c!='ORIG':
   prompt=(ROOT/'data/heuristic-prompts'/c/(t+'.txt')).read_text().strip()
   if prompt not in user:prompt_mismatches.append(dict(instance_id=t,condition=c))
  config=info['config'];model=config['model'];agent=config['agent']
  configs[(c,info.get('mini_version'),model.get('model_name'),agent.get('step_limit'),agent.get('wall_time_limit_seconds'),json.dumps(model.get('model_kwargs'),sort_keys=True))]+=1
 for h,rs in byhash.items():
  outcomeset={r['resolved'] for r in rs if r['resolved'] is not None}
  if len(outcomeset)>1:conflicts.append(dict(instance_id=t,patch_sha256=h,cells=rs))
summary['original_identical_patch_conflicts']=conflicts
summary['original_prompt_mismatches']=prompt_mismatches
summary['original_abnormal_exit']=quality
summary['original_configs']=[dict(values=k,count=v) for k,v in configs.items()]
submission_disagreements=[];raw_submissions=Counter()
for c in CONDS:
 folder='ORGI' if c=='ORIG' else c
 preds=json.loads((ROOT/'result'/('glm46_'+folder)/'mini_run/preds.json').read_text())
 for t in ids:
  patch=raws[(t,c,0)]['info'].get('submission','') or ''
  prediction=preds[t].get('model_patch','') or ''
  assert patch==prediction,(t,c,'raw patch vs prediction mismatch')
  raw_submissions[c]+=bool(patch)
  if bool(patch)!=(orig[c][t]['submitted']=='True'):
   submission_disagreements.append(dict(instance_id=t,condition=c,raw_submitted=bool(patch),normalized_submitted=orig[c][t]['submitted'],exit_status=raws[(t,c,0)]['info'].get('exit_status')))
summary['original_raw_submitted_counts']=dict(raw_submissions)
summary['original_submission_export_disagreements']=submission_disagreements
patchmatches=Counter();allfive=0
for t in ids:
 patches={c:raws[(t,c,0)]['info'].get('submission','') or '' for c in CONDS}
 allfive+=bool(patches['ORIG']) and len(set(patches.values()))==1
 for c in CONDS[1:]:patchmatches[c]+=bool(patches['ORIG']) and patches[c]==patches['ORIG']
summary['original_exact_patch_matches']=dict(relative_to_ORIG=dict(patchmatches),all_five_identical_nonempty=allfive,denominator_tasks=272)
wr_bodies=Counter();wlh_same_file=0;constructed_n=0
for p in (ROOT/'data/heuristic-hypotheses').glob('*.json'):
 if p.name=='construction-summary.json':continue
 d=json.loads(p.read_text());constructed_n+=1
 wlh_same_file+=bool(set(d['ground_truth']['files'])&set(d['hypotheses']['wrong_location'][0]['files']))
 wr_bodies[d['hypotheses']['wrong_repair'][0]['repair']]+=1
summary['construction_artifact_descriptives']=dict(n=constructed_n,wlh_shares_ground_file=wlh_same_file,WRH_bodies=dict(wr_bodies),semantic_validity='not independently adjudicated')

repeat=json.loads((ROOT/'analysis/repeated-runs-2026-10-02/summary.json').read_text())
summary['repetitions']=repeat
excluded={r['instance_id'] for r in metadata}|{r['instance_id'] for r in conflicts}|set(repeat['strict_audit_sensitivity']['sensitive']['excluded_tasks'])|set(repeat['strict_audit_sensitivity']['stable']['excluded_tasks'])
summary['conservative_original_excluded_tasks']=sorted(excluded)
safe=[t for t in ids if t not in excluded]
summary['conservative_original_outcomes']=outcomes(safe)
summary['conservative_original_process']=process(safe)
substantive_metadata={r['instance_id'] for r in metadata if r['field'] not in ['FAIL_TO_PASS','PASS_TO_PASS'] or any(x for x in (r.get('only_original') or [])+(r.get('only_condition') or []))}
focused_excluded=substantive_metadata|{r['instance_id'] for r in conflicts}|set(repeat['strict_audit_sensitivity']['sensitive']['excluded_tasks'])|set(repeat['strict_audit_sensitivity']['stable']['excluded_tasks'])
focused=[t for t in ids if t not in focused_excluded]
summary['focused_audit_excluded_tasks']=sorted(focused_excluded)
summary['focused_audit_original_outcomes']=outcomes(focused)
summary['focused_audit_original_process']=process(focused)

# Recompute held-out process contrasts on balanced, audit-clean tasks.
rr=list(csv.DictReader((ROOT/'analysis/repeated-runs-2026-10-02/run-level.csv').open()))
rr_lookup={(r['instance_id'],r['condition'],int(r['round'])):r for r in rr}
rep_metrics=['elapsed_seconds','time_to_first_successful_edit_seconds','total_tokens','tool_calls','search_read_calls','edit_calls','test_calls']
strict_rep=[]
for cohort in ['sensitive','stable']:
 use=sorted({r['instance_id'] for r in rr if r['cohort']==cohort}-focused_excluded)
 for m in rep_metrics:
  for c in CONDS[1:]:
   ds=[];relative=[]
   for t in use:
    differences=[];rels=[]
    for rd in [1,2]:
     a,b=rr_lookup[(t,c,rd)].get(m),rr_lookup[(t,'ORIG',rd)].get(m)
     if not a or not b:continue
     a,b=float(a),float(b);differences.append(a-b)
     if b>0:rels.append(a/b-1)
    if differences:ds.append(np.mean(differences))
    if rels:relative.append(np.mean(rels))
   strict_rep.append(dict(cohort=cohort,condition=c,metric=m,**process_stat(ds,relative)))
 for r,p,q in zip([x for x in strict_rep if x['cohort']==cohort],holm([x['p_wilcoxon'] for x in strict_rep if x['cohort']==cohort]),holm([x['p_sign'] for x in strict_rep if x['cohort']==cohort])):r['p_holm_28']=p;r['p_sign_holm_28']=q
summary['strict_repeat_process']=strict_rep

# Success/failure contrasts are descriptive: outcome is not randomized.
mixed=[t for t in complete if len(set(signatures[t]))>1];contrasts=[]
for m in METRICS:
 ds=[]
 for t in mixed:
  a=[orig[c][t][m] for c in CONDS if orig[c][t]['resolved']==1 and orig[c][t][m] is not None]
  b=[orig[c][t][m] for c in CONDS if orig[c][t]['resolved']==0 and orig[c][t][m] is not None]
  if a and b:ds.append(np.mean(a)-np.mean(b))
 contrasts.append(dict(metric=m,**process_stat(ds,[])))
summary['mixed_task_success_minus_failure_exploratory']=contrasts

# Patch overlap does not measure correctness and exact line overlap ignores file identity.
patchdiag=[]
for c in CONDS:
 for resolved in [0,1]:
  rs=[r for r in orig[c].values() if r['resolved']==resolved]
  patchdiag.append(dict(condition=c,resolved=resolved,n=len(rs),gold_file_precision_one=sum(r['gold_file_precision']==1 for r in rs),gold_file_recall_one=sum(r['gold_file_recall']==1 for r in rs),no_agent_test_calls=sum(r['test_calls']==0 for r in rs)))
summary['original_patch_diagnostics']=patchdiag

# Independently available repository-origin diagnostic is not contamination evidence.
diags=[json.loads(x) for x in (ROOT/'data/issue-only-diagnostics/glm-4.6-repository-origin.jsonl').read_text().splitlines() if x.strip()]
summary['repository_origin_diagnostic']=dict(n=len(diags),repository_correct=sum(x.get('repository_match') is True for x in diags),predicted_PR_nonnull=sum(x.get('predicted_pull_request_number') is not None for x in diags),recognition_basis=dict(Counter(x.get('recognition_basis') for x in diags)))

# Descriptives and raw distributions for all conditions.
descriptives=[]
for c in CONDS:
 for m in METRICS:
  v=np.array([r[m] for r in orig[c].values() if r[m] is not None],float)
  descriptives.append(dict(condition=c,metric=m,n=len(v),missing=272-len(v),mean=float(v.mean()),SD=float(v.std(ddof=1)),median=float(np.median(v)),q25=float(np.quantile(v,.25)),q75=float(np.quantile(v,.75)),min=float(v.min()),max=float(v.max())))
summary['descriptives']=descriptives

def writecsv(name,data):
 with (OUT/name).open('w',newline='') as f:
  fields=list(dict.fromkeys(k for r in data for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
for name,rs in [('original-outcome-effects.csv',summary['original']['effects']),('original-process-effects.csv',summary['original_process']),('conservative-original-process-effects.csv',summary['conservative_original_process']),('focused-audit-original-process-effects.csv',summary['focused_audit_original_process']),('strict-repeat-process-effects.csv',strict_rep),('original-descriptives.csv',descriptives),('mixed-task-success-failure.csv',contrasts)]:writecsv(name,rs)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
for eid,p in [
 ('E_REPEAT_SUMMARY',ROOT/'analysis/repeated-runs-2026-10-02/summary.json'),
 ('E_REPEAT_RUNS',ROOT/'analysis/repeated-runs-2026-10-02/run-level.csv'),
 ('E_REPEAT_TASKS',ROOT/'analysis/repeated-runs-2026-10-02/task-level.csv'),
 ('E_VALIDITY',ROOT/'docs/hypothesis-validity-audit.md'),
 ('E_EXTRACTOR',ROOT/'src/rfm/trajectory_extraction.py'),
 ('E_PROTOCOL',ROOT/'docs/protocol.md'),
 ('E_ORIGIN',ROOT/'data/issue-only-diagnostics/glm-4.6-repository-origin.jsonl')]:
 source_manifest.append(dict(evidence_id=eid,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),verification='machine_checked; human verification pending'))
for rd in [0,1,2]:
 p=ROOT/'result'/('glm46_WRH' if rd==0 else f'glm46_sensitive/round{rd}/WRH')/'mini_run/django__django-17084/django__django-17084.traj.json'
 source_manifest.append(dict(evidence_id=f'E_DJANGO17084_WRH_R{rd}',path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),verification='machine_checked; mechanism adjudication pending'))
claims={
 'C01':('Data coverage and denominators',['E_ORIG_ORIG','E_REPEAT_RUNS'],['original','repetitions']),
 'C02':('Exposure and construction limitations',['E_VALIDITY'],['original_prompt_mismatches','construction_artifact_descriptives']),
 'C03':('Initial outcome-stratified cohorts',['E_ORIG_ORIG','E_REPEAT_TASKS'],['original_outcome_signatures','repetitions/cohorts']),
 'C04':('Initial paired resolution outcomes',['E_ORIG_ORIG','E_ORIG_CH','E_ORIG_WLH','E_ORIG_WCH','E_ORIG_WRH'],['original','focused_audit_original_outcomes','conservative_original_outcomes']),
 'C05':('Original process effects and correction sensitivity',['E_ORIG_ORIG','E_EXTRACTOR'],['original_process','focused_audit_original_process']),
 'C06':('Repeated stable process differences',['E_REPEAT_RUNS'],['strict_repeat_process']),
 'C07':('Repeatability and held-out condition effects',['E_REPEAT_SUMMARY','E_REPEAT_TASKS'],['repetitions/cohorts','repetitions/followup_effects','repetitions/strict_audit_sensitivity']),
 'C08':('Submission/evaluator consistency audit',['E_EXTRACTOR','E_REPEAT_SUMMARY'],['original_raw_submitted_counts','original_submission_export_disagreements','original_metadata_mismatches','stored_spec_vs_evaluator_report_disagreements','original_identical_patch_conflicts','repetitions/identical_patch_outcome_conflicts']),
 'C09':('Case trajectories and reproduction boundary',['E_REPEAT_TASKS','E_DJANGO17084_WRH_R0','E_DJANGO17084_WRH_R1','E_DJANGO17084_WRH_R2'],['repetitions/case_replication']),
 'C10':('Exploratory success/failure contrasts',['E_ORIG_ORIG'],['mixed_task_success_minus_failure_exploratory']),
 'C11':('Repository recognition is not proof of contamination',['E_ORIGIN'],['repository_origin_diagnostic'])}
registry=[dict(claim_id=k,scope=v[0],evidence_ids=v[1],summary_json_locators=v[2],analysis_intent='exploratory or descriptive; not preregistered',human_verified=False,human_verifier=None,status='analysis draft; independent verification pending') for k,v in claims.items()]
(OUT/'claim-evidence.json').write_text(json.dumps(registry,indent=2,ensure_ascii=False))
(OUT/'source-manifest.json').write_text(json.dumps(source_manifest,indent=2))

# Produce raw diagnostic distributions before interpretive panels.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
def savefig(fig,name):
 for ext in ['png','pdf','svg']:fig.savefig(OUT/(name+'.'+ext),dpi=250,bbox_inches='tight',facecolor='white')
 plt.close(fig)
fig,axs=plt.subplots(2,3,figsize=(11,6.5),constrained_layout=True)
for ax,m in zip(axs.flat,['elapsed_seconds','total_tokens','tool_calls','search_read_calls','edit_calls','test_calls']):
 data=[np.array([r[m] for r in orig[c].values() if r[m] is not None]) for c in CONDS]
 ax.boxplot(data,tick_labels=CONDS,showfliers=True,flierprops=dict(markersize=2));ax.set_title(m)
 if m in ['elapsed_seconds','total_tokens']:ax.set_yscale('log')
 ax.grid(axis='y',alpha=.2)
savefig(fig,'raw-process-distributions')

fig,axs=plt.subplots(1,3,figsize=(12,3.9),constrained_layout=True)
colors=['#0072B2','#D55E00'];styles=['o','s']
for ax,key,title in zip(axs,['original','conservative_original_outcomes'],['Original 272-task sample','Conservative audit exclusion']):
 for i,r in enumerate(summary[key]['effects']):
  d=r['difference']*100;lo,hi=np.array(r['ci95'])*100
  ax.errorbar(d,i,xerr=[[d-lo],[hi-d]],fmt='o',color=colors[0],capsize=3)
 ax.axvline(0,color='.5',lw=1);ax.set_yticks(range(4),CONDS[1:]);ax.set_title(title);ax.set_xlabel('Paired resolve-rate difference (pp)');ax.grid(axis='x',alpha=.2)
ax=axs[2]
for j,co in enumerate(['sensitive','stable']):
 r=repeat['cohorts'][co]['followup_within_condition_disagreement'];v=r['mean']*100;lo,hi=np.array(r['ci95'])*100
 ax.errorbar(v,j,xerr=[[v-lo],[hi-v]],fmt=styles[j],color=colors[j],capsize=3)
ax.set_yticks([0,1],['Initially mixed (n=34)','Initially stable (n=50)']);ax.set_xlabel('Same-condition repeat disagreement (%)');ax.set_title('Two held-out rounds');ax.set_xlim(0,50);ax.grid(axis='x',alpha=.2)
savefig(fig,'outcomes-and-repeatability')

fig,axs=plt.subplots(1,3,figsize=(11,4.2),constrained_layout=True)
for ax,m in zip(axs,['tool_calls','search_read_calls','test_calls']):
 for i,c in enumerate(CONDS[1:]):
  for j,key in enumerate(['original_process','conservative_original_process']):
   r=next(x for x in summary[key] if x['condition']==c and x['metric']==m)
   # Plot mean difference rather than median intervals degenerating at zero.
   use=ids if j==0 else safe;ds=[orig[c][t][m]-orig['ORIG'][t][m] for t in use if orig[c][t][m] is not None and orig['ORIG'][t][m] is not None]
   v=np.mean(ds);lo,hi=bootstrap(ds)
   ax.errorbar(v,i+(j-.5)*.15,xerr=[[v-lo],[hi-v]],fmt=styles[j],color=colors[j],capsize=2,label=['All original tasks','Audit exclusion'][j] if i==0 else None)
 ax.axvline(0,color='.5',lw=1);ax.set_yticks(range(4),CONDS[1:]);ax.set_title(m.replace('_',' '));ax.set_xlabel('Mean paired difference (calls)');ax.grid(axis='x',alpha=.2)
handles,labels=axs[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,-.025),ncol=2,fontsize=9,frameon=False)
savefig(fig,'process-paired-effects')

print(json.dumps(dict(original=summary['original'],metadata=metadata,conflicts=conflicts,excluded=sorted(excluded),conservative=summary['conservative_original_outcomes'],process_significant_global=[r for r in summary['original_process'] if r['p_holm_64']<.05],safe_process_significant_global=[r for r in summary['conservative_original_process'] if r['p_holm_64']<.05],origin_diagnostic=summary['repository_origin_diagnostic']),indent=2))
