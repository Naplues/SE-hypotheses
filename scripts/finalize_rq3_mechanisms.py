"""Publish the inspected case figure and preserve source evidence."""
import json
import shutil
import sys
from pathlib import Path
from PIL import Image

work = Path(__file__).resolve().parent
out = work/'figures/rq3-mechanisms'
source = Path(sys.argv[1])
with Image.open(source) as im:
 clean = im.convert('RGB')
 clean.save(out/'rq3-mechanisms.png')
 clean.save(out/'rq3-mechanisms.pdf',resolution=213.2)
spec = json.loads((out/'figure-spec.json').read_text())
plan = dict(schema='academic-figure/FigurePlan@1',source_revision='local-five-condition-runs',venue='FSE',sources=spec['sources'],
 figures=[dict(figure_id=spec['figure_id'],figure_type='qualitative_case_comparison',priority='primary',
 communication_goal='Contrast six overlapping exploratory mechanisms using actual repair paths and evaluator outcomes.',
 claim_scope=['illustrative single-run comparisons'],hero_element='b',required_nodes=[n['id'] for n in spec['topology']['components']],
 required_connections=[],authority_boundaries=spec['topology']['authority_boundaries'],secondary_context=[],
 forbidden_claims=spec['must_not_claim'],forbidden_connections=spec['forbidden_connections'],aspect_ratio='3:2',final_width_mm=183,
 style_profile_hint='reference-led',reference_assets=spec['reference_images'],open_questions=[],confidence='bounded by one run per cell',review_status='waived')])
(out/'figure-plan.json').write_text(json.dumps(plan,indent=2))
repo = Path('/Users/gzq/Repo/FSE2027')
dest = repo/'figures/rq3-mechanisms'
dest.mkdir(parents=True,exist_ok=True)
for p in out.iterdir():
 if p.is_file():
  shutil.copy2(p,dest/p.name)
shutil.copy2(work/'build_rq3_mechanism_spec.py',repo/'scripts/build_rq3_mechanism_spec.py')
shutil.copy2(work/'finalize_rq3_mechanisms.py',repo/'scripts/finalize_rq3_mechanisms.py')
print(dest)
