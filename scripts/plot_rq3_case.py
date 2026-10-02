"""Reproduce the Section 4.4 case figure from recorded experiment artifacts."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'figures' / 'rq3-case'
OUT.mkdir(parents=True, exist_ok=True)
INSTANCE = 'django__django-17084'
rows = {}
events = {}
for condition, directory in [('ORIG','ORGI'),('CH','CH'),('WLH','WLH'),('WCH','WCH'),('WRH','WRH')]:
    with (ROOT/'results'/directory/'trajectory-features.csv').open() as stream:
        rows[condition] = next(r for r in csv.DictReader(stream) if r['instance_id']==INSTANCE)
    path = next((ROOT/'results'/directory/'runs').glob(INSTANCE+'*/trajectory.jsonl'))
    events[condition] = [json.loads(line) for line in path.open()]

plt.rcParams.update({'pdf.fonttype':42,'svg.fonttype':'none','font.family':'DejaVu Sans'})
fig, ax = plt.subplots(figsize=(12.8,5.0))
ax.set(xlim=(0,12.8), ylim=(0,5.0)); ax.axis('off')
ink, green, rust = '#263238', '#246C55', '#A44F30'
ax.text(.12,4.73,INSTANCE,fontsize=12,weight='bold',color=ink)
ax.text(.12,4.35,'Shared issue: aggregate over a window annotation produces invalid SQL.',fontsize=11,color=ink)
xs = [1.0,3.7,6.65,10.05]
for x,title in zip(xs,['1  Task context','2  Inspect / interpret','3  Modify / revise','4  Evaluated outcome']):
    ax.text(x,3.88,title,fontsize=10,weight='bold',color=ink)
ax.plot([.12,12.6],[3.68,3.68],color='#B8BEC2',lw=.8)
def block(x,y,title,detail,color,highlight,code=False):
    ax.text(x,y,title,fontsize=10,weight='bold',color=color,va='top',
            family='DejaVu Sans Mono' if code else 'DejaVu Sans',
            bbox={'facecolor':highlight,'edgecolor':'none','pad':3})
    ax.text(x,y-.44,detail,fontsize=9,color='#545D63',va='top',linespacing=1.45)
def arrows(y):
    for a,b in [(3.13,3.53),(6.08,6.48),(9.49,9.88)]:
        ax.annotate('',xy=(b,y),xytext=(a,y),arrowprops={'arrowstyle':'->','lw':1,'color':ink})
for y,c,color in [(3.31,'ORIG',green),(1.61,'WRH',rust)]:
    ax.text(.12,y,c,fontsize=11,weight='bold',color=ink,va='top')
    arrows(y-.12)
    assert (rows[c]['evaluator_resolved']=='True') == (c=='ORIG')
block(xs[0],3.31,'Original issue','Restore support for\naggregation over\nwindow annotations.',green,'#E4F0E9')
block(xs[1],3.31,'sql/query.py','Inspect aggregate and\nwindow-expression handling.\nRecorded read: event 26.',green,'#E4F0E9',True)
block(xs[2],3.31,'Enable subquery wrapping','102: broaden window detection.\n128: revert that attempt.\n144: detect referenced windows\nand trigger subquery wrapping.',green,'#E4F0E9')
block(xs[3],3.31,'Resolved','Final repair changes\nquery construction;\nbenchmark evaluation passes.',green,'#E4F0E9')
ax.plot([.12,12.6],[1.94,1.94],color='#E0E3E5',lw=.7)
block(xs[0],1.61,'Validation hypothesis','“Add input validation\nbefore the operation.”\nInjected developer hypothesis.',rust,'#F8E9E0')
block(xs[1],1.61,'aggregates.py','69: interpret the SQL error\nas missing validation in\nAggregate.resolve_expression.',rust,'#F8E9E0',True)
block(xs[2],1.61,'Raise FieldError','90: add contains_over_clause\nchecks to reject window inputs.\n171: retain these checks\nin the submitted patch.',rust,'#F8E9E0')
block(xs[3],1.61,'Unresolved','Final repair rejects\nthe requested operation;\nbenchmark evaluation fails.',rust,'#F8E9E0')
ax.text(.12,.15,'Numbers denote normalized trajectory events, not tool-call counts. Arrows summarize observed paths, not causal effects.',fontsize=8,color='#545D63')
fig.subplots_adjust(left=.01,right=.99,bottom=.025,top=.99)
for ext in ['png','pdf','svg']:
    fig.savefig(OUT/('django-17084.'+ext),dpi=250,facecolor='white')
evidence={'instance_id':INSTANCE,'rows':rows,'wrh_prompt':(ROOT/'data/heuristic-prompts/WRH'/(INSTANCE+'.txt')).read_text(),'selected_events':{}}
for c,steps in {'ORIG':[26,98,102,128,144],'WRH':[69,90,171]}.items():
    evidence['selected_events'][c]=[e for e in events[c] if e['step'] in steps]
(OUT/'evidence.json').write_text(json.dumps(evidence,indent=2))
plt.close(fig)
