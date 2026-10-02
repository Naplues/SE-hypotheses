"""Ground the six-panel RQ3 figure in local evaluator rows and trajectories."""
import csv
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = Path('/Users/gzq/Repo/FSE2027')
OUT = WORK / 'figures/rq3-mechanisms'
OUT.mkdir(parents=True, exist_ok=True)
REF = '/private/var/folders/ss/283vmm4n5qsd18m_mfkyh4j40000gn/T/codex-clipboard-5e882aa0-08b2-420d-8d5f-55a7250b9fb5.png'
cases = [
 dict(id='a', title='Architectural redirection', task='sympy__sympy-20428',
      issue='Zero polynomial not recognized',
      left=['ORIG: Unresolved','densetools.py','Strip downstream coefficients'],
      right=['CH: Resolved','expressiondomain.py','__bool__: not f.ex.is_zero'],
      takeaway='Upstream semantics, not symptom patching'),
 dict(id='b', title='Mislocalization', task='django__django-17084',
      issue='Aggregate over a window annotation',
      left=['WRH: Unresolved','aggregates.py','Reject input: raise FieldError'],
      right=['ORIG: Resolved','sql/query.py','Enable subquery wrapping'],
      takeaway='Rejecting the operation does not repair it'),
 dict(id='c', title='Premature commitment', task='astropy__astropy-13033',
      issue='Required-column error message',
      left=['ORIG: Unresolved','core.py: format-only patch','Targeted column tests pass'],
      right=['CH: Resolved','core.py: branch-aware patch','Benchmark evaluation passes'],
      takeaway='Self-selected tests can validate a near miss'),
 dict(id='d', title='Beneficial perturbation', task='pylint-dev__pylint-7080',
      issue='Recursive ignore-path filtering',
      left=['ORIG: Unresolved','pylinter.py','Add discovery-stage filtering'],
      right=['WCH: Resolved','Also edit expand_modules.py','Normalize paths before matching'],
      takeaway='Additional evidence redirects the repair'),
 dict(id='e', title='Semantic near miss', task='astropy__astropy-13033',
      issue='Same file, different error semantics',
      left=['ORIG: Unresolved','timeseries/core.py','Join names in one error branch'],
      right=['CH: Resolved','timeseries/core.py','Single / multiple-column branches'],
      takeaway='Correct file does not ensure correct semantics'),
 dict(id='f', title='Underidentified execution branch', task='django__django-14765',
      issue='ProjectState real_apps invariant',
      left=['ORIG: Unresolved','migrations/state.py','Remove set conversion'],
      right=['CH: Resolved','migrations/state.py','Assert set; distinguish None'],
      takeaway='One run cannot establish the causal mechanism'),
]
evidence = {}
for case in cases:
 t = case['task']
 if t in evidence:
  continue
 evidence[t] = {}
 for condition, folder in [('ORIG','ORGI'),('CH','CH'),('WLH','WLH'),('WCH','WCH'),('WRH','WRH')]:
  rows = csv.DictReader((ROOT/'results'/folder/'trajectory-features.csv').open())
  row = next(r for r in rows if r['instance_id']==t)
  p = next((ROOT/'results'/folder/'runs').glob(t+'*/trajectory.jsonl'))
  events = [json.loads(line) for line in p.open()]
  selected = [e for e in events if e['event_type']=='patch']
  if t=='astropy__astropy-13033' and condition=='ORIG':
   selected += [e for e in events if e['step'] in [25,27,29,37,51]]
  if t=='pylint-dev__pylint-7080' and condition=='WCH':
   selected += [e for e in events if e['step'] in [167,173,181,185,249]]
  evidence[t][condition] = dict(row=row, trajectory_path=str(p), selected_events=selected)
 for side in ['left','right']:
  condition, outcome = case[side][0].split(': ')
  assert (evidence[t][condition]['row']['evaluator_resolved']=='True') == (outcome=='Resolved')
text = ['Illustrative mechanisms behind outcome flips',
        'Observed trajectories; one execution per task-condition',
        'Single-run cases; mechanism labels are exploratory, not causal estimates.']
components = []
groups = []
for case in cases:
 strings = [case['id']+'. '+case['title'],'Task: '+case['task'],case['issue']]+case['left']+case['right']+[case['takeaway']]
 text += strings
 components.append(dict(id=case['id'],label=case['title'],role='case_comparison',visible_text=strings,
                        evidence=[str(OUT/'evidence.json')+'#'+case['task']]))
 groups.append(dict(id='group_'+case['id'],component_ids=[case['id']]))
prompt = '''Create a camera-ready scientific case-study figure. The input image is STYLE ONLY: transfer its pale pastel rounded regions, black sans-serif headings, white side-by-side code/file cards, clean document/file icons, green check and red cross outcome circles, emphasized code tokens, thin borders, no shadows. Do not copy any reference claims or fake examples. Output one opaque white landscape 3:2 image, high resolution. Arrange SIX panels in a 3-column by 2-row grid, a/b/c on top and d/e/f below. Do not draw arrows between unrelated cases. Use equal panel dimensions, substantial legible text, dark ink, monospaced filenames, discreet line icons. The top header is a small document icon and the exact title "Illustrative mechanisms behind outcome flips", subtitle "Observed trajectories; one execution per task-condition". Each panel has a bold numbered mechanism heading, its full task ID, a short issue subtitle, two white comparison cards with the exact three lines listed below, and a one-line takeaway strip. Left cards show red X with the text Unresolved, right cards show green check with text Resolved. Outcome icons mean BENCHMARK outcomes, not hypothesis truth. Filename lines and decisive repair actions should be highlighted using pale colored backgrounds. Show tiny file/code icons to aid reading, not generic robots. Panel c can show a tiny check beside targeted tests plus a separate benchmark failure X; never conflate these. Panel d may have a small magnifying-glass beside path normalization, panel f a small question-mark beside its takeaway. All text below must appear exactly, with sensible wrapping. Never invent code or metrics. Panel backgrounds: a pale blue, b pale coral, c pale cream, d pale mint, e pale lavender, f neutral blue-gray. Do not saturate the full cards. Exact panel content:\n'''
for case in cases:
 prompt += json.dumps(case,ensure_ascii=False)+'\n'
prompt += 'Footer: "Single-run cases; mechanism labels are exploratory, not causal estimates." No other visible text. Bold/highlight key actions but avoid dense prose, decorations, gradients, 3D effects, logos, watermark, speculative recovery or anchoring rates.'
spec = dict(schema='academic-figure/FigureSpec@1',figure_id='rq3-mechanisms',plan_revision='1',
 sources=[dict(kind='repository',uri_or_path=str(ROOT/'results'),evidence='Evaluator outcomes and final patches; selected reasoning events in evidence.json'),
          dict(kind='reference_image',uri_or_path=REF,evidence='Visual grammar only; scientific content not reused')],
 prompt=prompt,aspect_ratio='3:2',final_width_mm=183,visible_text=text,
 topology=dict(components=components,connections=[],groups=groups,authority_boundaries=['Agent-selected tests are distinct from benchmark evaluator outcomes']),
 layout=dict(composition='comparison_grid',hero='b',reading_order=[c['id'] for c in cases],nesting_depth=1,whitespace='balanced'),
 style_profile='reference-led',style_source='reference',
 style_grammar=dict(marks='simple file/code/magnifier/status line icons',fills='pastel panels and white comparison cards',strokes='thin borders',typography='sans-serif headings, monospaced filenames',shadow='none',density='balanced'),
 semantic_color_roles=dict(resolved='#246C55',unresolved='#A44F30',body='#263238'),reference_images=[REF],
 must_not_claim=['All CH hypotheses semantically correct','causal effect from one run','measured recovery or anchoring rate','mutually exclusive mechanism taxonomy'],
 forbidden_connections=['connections between unrelated case panels'],negative_constraints=['no invented transcript','no unsourced metrics','no gradients or shadows'],
 prompt_review='waived',workspace_root=str(WORK),output_path=str(OUT/'rq3-mechanisms.png'),
 caption_notes=['Panels c and e intentionally reuse one task to distinguish validation behavior from patch semantics.','All comparisons are illustrative and not mutually exclusive.'])
(OUT/'figure-spec.json').write_text(json.dumps(spec,indent=2))
(OUT/'evidence.json').write_text(json.dumps(evidence,indent=2))
(OUT/'cases.json').write_text(json.dumps(cases,indent=2))
print(OUT)
