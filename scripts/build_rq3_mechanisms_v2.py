"""Evidence-bounded redesign: requirements, actions, behavior, evaluation."""
import json
from pathlib import Path
WORK=Path(__file__).resolve().parent
OUT=WORK/'figures/rq3-mechanisms-v2'
OUT.mkdir(parents=True,exist_ok=True)
baseline='/Users/gzq/Repo/FSE2027/figures/rq3-mechanisms/rq3-mechanisms.png'
evidence=json.loads((WORK/'figures/rq3-mechanisms/evidence.json').read_text())
cases=[
 dict(id='a',title='Upstream vs. downstream repair',task='sympy__sympy-20428',
 goal='Recognize mathematically zero polynomials.',
 paths=[['ORIG','Strip coefficients','Treat downstream symptom','Unresolved','densetools.py'],
        ['CH','Fix zero recognition','Recognize zero-valued expressions','Resolved','expressiondomain.py']],
 lesson='The successful patch repairs the upstream predicate.'),
 dict(id='b',title='Repairing vs. rejecting the operation',task='django__django-17084',
 goal='Allow aggregation over window annotations.',
 paths=[['WRH','Add input checks','Reject operation with FieldError','Unresolved','aggregates.py'],
        ['ORIG','Wrap query in a subquery','Support the requested operation','Resolved','sql/query.py']],
 lesson='Rejecting valid usage is not a functional repair.'),
 dict(id='c',title='Local validation mismatch',task='astropy__astropy-13033',
 goal='Report required-column errors consistently.',
 paths=[['ORIG','Change message formatting','Selected column tests pass','Unresolved','timeseries/core.py'],
        ['CH','Handle message branches','Branch-aware error reporting','Resolved','timeseries/core.py']],
 lesson='Local test success does not establish benchmark correctness.'),
 dict(id='d',title='Evidence-driven revision under WCH',task='pylint-dev__pylint-7080',
 goal='Honor ignore-path rules during recursive linting.',
 paths=[['ORIG','Add discovery filtering','No path-normalization change','Unresolved','pylinter.py'],
        ['WCH','Filter + normalize paths','Remove ./ before path matching','Resolved','pylinter.py + expand_modules.py']],
 lesson='WCH revises its patch after a reproduction still fails.'),
 dict(id='e',title='Same file, different semantics',task='astropy__astropy-13033',
 goal='Handle single / multiple-column error branches.',
 paths=[['ORIG','Join names in one branch','Leave empty-column branch unchanged','Unresolved','timeseries/core.py'],
        ['CH','Handle both error branches','Distinguish single / multiple columns','Resolved','timeseries/core.py']],
 lesson='File localization alone does not guarantee correct behavior.'),
 dict(id='f',title='Evidence boundary: cause unresolved',task='django__django-14765',
 goal='Enforce the real_apps set invariant.',
 paths=[['ORIG','Remove set conversion','Do not enforce the set invariant','Unresolved','migrations/state.py'],
        ['CH','Assert set; distinguish None','Make the input invariant explicit','Resolved','migrations/state.py']],
 lesson='Different patches are observed; prompt causality is unproven.')
]
nodes=[];edges=[];groups=[]
texts=['Task requirement → repair action → behavior / validation → benchmark outcome',
       'CH / WCH / WRH denote supplied prompt conditions, not validated hypothesis truth.',
       'Illustrative single runs; categories overlap. Behavior summaries interpret patches; outcomes are evaluator records.']
for case in cases:
 cid=case['id']; members=[]
 header=[cid+'. '+case['title'],case['task'],'Expected: '+case['goal'],case['lesson']]
 nodes.append(dict(id=cid+'_task',label=case['title'],visible_text=header,evidence=[case['task']]))
 texts+=header;members.append(cid+'_task')
 for k,path in enumerate(case['paths']):
  condition,action,behavior,outcome,file=path
  assert (evidence[case['task']][condition]['row']['evaluator_resolved']=='True')==(outcome=='Resolved')
  prefix=cid+'_'+str(k)
  for stage,label in [('action',action),('behavior',behavior),('outcome',outcome)]:
   nid=prefix+'_'+stage;members.append(nid)
   local=[label,condition,file] if stage=='action' else [label]
   nodes.append(dict(id=nid,label=label,visible_text=local,evidence=[case['task']+'/'+condition]))
   texts+=local
  for start,end in [('action','behavior'),('behavior','outcome')]:
   edges.append(dict(id=prefix+'_'+start+'_'+end,**{'from':prefix+'_'+start,'to':prefix+'_'+end},kind='observed_summary',direction='forward',line='solid',label='',evidence=[case['task']+'/'+condition]))
 groups.append(dict(id=cid,component_ids=members))
prompt='''Redraw the supplied baseline scientific figure as a clearer, factually bounded case-study explanation. This is a substantive authorized redesign, not a cosmetic recolor. Preserve all six real task comparisons and their condition/outcome pairs, but REPLACE the old mechanism names and terse labels with the exact new panel content below. Use a TWO-COLUMN by THREE-ROW grid on a landscape 4:3 canvas, panels a/b top, c/d middle, e/f bottom. Pale pastel panels, thin rounded outlines, white inner flow rows, simple line-art icons, bold dark sans-serif headings and clear highlights: transfer the existing reference style, no shadows, gradients, robots, or decorative banner. A small top reading guide says exactly "Task requirement → repair action → behavior / validation → benchmark outcome". In each panel show its heading and small task ID, then a prominent document-icon row labelled Expected with the task requirement. Beneath it show TWO horizontal rows. Each row starts with its exact condition, then a repair-action block with a small code icon, a solid right arrow to the behavior/validation block, a solid right arrow to its BENCHMARK outcome (green check + Resolved, red cross + Unresolved). Small filenames belong UNDER repair actions, not as the primary message. The arrows represent a summarized observed run, not causal identification. Highlight the crucial behavior differences. Keep condition labels legible. In panel c, Selected column tests pass is LOCAL validation: use a small flask icon, but the ORIG row still ends in red Unresolved. Never turn that benchmark outcome green. The CH row ends green Resolved. Panel d's WCH behavior includes literal ./; do not delete it. Panel f has a NEUTRAL gray dashed border and a question-mark icon, explicitly making it an evidence-boundary panel, not a sixth established mechanism. Each panel ends with its exact lesson as a short highlighted strip. Do not connect unrelated panels. No made-up plots, percentages, quotes, timelines or annotations. Exact content, for each path the five strings denote condition, repair action, behavior, benchmark outcome, filename:\n'''
prompt+='\n'.join(json.dumps(c,ensure_ascii=False) for c in cases)
prompt+='''\nBelow the grid use two small but readable footer lines: "CH / WCH / WRH denote supplied prompt conditions, not validated hypothesis truth." and "Illustrative single runs; categories overlap. Behavior summaries interpret patches; outcomes are evaluator records." The goal field must be prefixed Expected:. Do not display JSON keys or editorial instructions. Balanced spacing, adequate text size, no clipped file names or arrows through text. White opaque outer canvas, 4:3 landscape. All existing unsupported labels Architectural redirection, Premature commitment, Beneficial perturbation and Underidentified execution branch must be removed and replaced by the specified descriptive headings.'''
spec=dict(schema='academic-figure/FigureSpec@1',figure_id='rq3-mechanisms-v2',plan_revision='2',
 sources=[dict(kind='repository',uri_or_path=str(WORK/'figures/rq3-mechanisms/evidence.json'),evidence='Evaluator rows, final patches and selected reasoning events'),dict(kind='reference_image',uri_or_path=baseline,evidence='Baseline style and verified task-condition comparisons')],
 prompt=prompt,aspect_ratio='4:3',final_width_mm=183,visible_text=texts,
 topology=dict(components=nodes,connections=edges,groups=groups,authority_boundaries=['Local tests distinct from benchmark outcomes','Behavior interpretation distinct from observed evaluator records','No causal effect inferred from single execution']),
 layout=dict(composition='comparison_grid',hero='b_task',reading_order=[g['id']+'_task' for g in groups],nesting_depth=1,whitespace='balanced'),
 style_profile='reference-led',style_source='reference',style_grammar=dict(fills='pale panels, white rows',strokes='thin borders; neutral dashed f panel',typography='bold headings, subordinate filenames',icons='document/code/test/check/cross/question',shadow='none'),
 semantic_color_roles=dict(resolved='#246C55',unresolved='#A44F30',body='#263238',evidence_boundary='#52616B'),reference_images=[baseline],
 must_not_claim=['causal prompt effects','adjudicated recovery','all CH hypotheses correct','early commitment proven cause of failure','mutually exclusive classes'],forbidden_connections=['arrows between cases'],negative_constraints=['no invented data','no ambiguous local vs benchmark pass'],prompt_review='waived',workspace_root=str(WORK),output_path=str(OUT/'rq3-mechanisms-v2.png'),
 caption_notes=['c/e share one task but analyze validation vs patch semantics','f is evidence boundary, not an established mechanism','Arrows summarize observed actions and patch interpretation, not prompt causality'])
(OUT/'figure-spec.json').write_text(json.dumps(spec,indent=2))
(OUT/'cases.json').write_text(json.dumps(cases,indent=2))
print(OUT)
