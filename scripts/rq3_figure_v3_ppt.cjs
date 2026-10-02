const fs=require('fs');
const path=require('path');
const PptxGenJS=require('/Users/gzq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pptxgenjs');
const ppt=new PptxGenJS();
ppt.defineLayout({name:'CASEFIGURE',width:16,height:10.6});
ppt.layout='CASEFIGURE';
ppt.title='RQ3: Four illustrative repair-path comparisons';
ppt.author='FSE2027 research';
ppt.lang='en-US';
ppt.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:'en-US'};
const slide=ppt.addSlide();slide.background={color:'FFFFFF'};
const S=ppt.ShapeType;
const ink='17212B',red='A44F30',green='246C55';
const evidence=JSON.parse(fs.readFileSync('/Users/gzq/Repo/FSE2027/figures/rq3-mechanisms-v2/evidence.json','utf8'));
function box(x,y,w,h,fill,line='CAD3DB',dash=false){
 slide.addShape(S.roundRect,{x,y,w,h,rectRadius:.055,fill:{color:fill},line:{color:line,width:.7,...(dash?{dashType:'dash'}:{})}});
}
function text(t,x,y,w,h,size=15,bold=false,color=ink,align='left'){
 slide.addText(t,{x,y,w,h,fontFace:'Arial',fontSize:size,bold,color,margin:0,valign:'mid',align,fit:'shrink',paraSpaceAfter:0});
}
function arrow(x,y,w){slide.addShape(S.line,{x,y,w,h:0,line:{color:'34424C',width:1.2,endArrowType:'triangle'}});}
function document(x,y){
 slide.addShape(S.rect,{x,y,w:.18,h:.24,fill:{color:'FFFFFF'},line:{color:ink,width:1}});
 for(let j=0;j<3;j++)slide.addShape(S.line,{x:x+.035,y:y+.06+j*.05,w:.11,h:0,line:{color:ink,width:.8}});
}
function status(x,y,resolved){
 const color=resolved?green:red;
 slide.addShape(S.ellipse,{x,y,w:.27,h:.27,fill:{color},line:{color,width:.5}});
 if(resolved){
  slide.addShape(S.line,{x:x+.06,y:y+.14,w:.05,h:.05,line:{color:'FFFFFF',width:1.5}});
  slide.addShape(S.line,{x:x+.11,y:y+.19,w:.10,h:-.12,line:{color:'FFFFFF',width:1.5}});
 }else{
  slide.addShape(S.line,{x:x+.075,y:y+.075,w:.12,h:.12,line:{color:'FFFFFF',width:1.5}});
  slide.addShape(S.line,{x:x+.075,y:y+.195,w:.12,h:-.12,line:{color:'FFFFFF',width:1.5}});
 }
}
function outcome(x,y,w,label,h=.66){
 const good=label==='Resolved';box(x,y,w,h,good?'E3F3E6':'FBE4E7');
 status(x+w/2-.135,y+.065,good);
 text(label,x+.03,y+.405,w-.06,.17,10,true,ink,'center');
}
function row(x,y,condition,action,file,behavior,result,task){
 if((evidence[task][condition].row.evaluator_resolved==='True')!==(result==='Resolved'))throw Error('Outcome mismatch');
 const tint=result==='Resolved'?'E3F3E6':'FBE4E7';
 box(x+.16,y,.78,.66,tint);text(condition,x+.19,y+.07,.72,.5,16,true,ink,'center');
 arrow(x+1.01,y+.33,.22);
 box(x+1.32,y,2.1,.66,'FFFFFF');
 text(action,x+1.42,y+.035,1.9,.39,14,true,ink,'center');
 text(file,x+1.4,y+.455,1.94,.16,10,false,'45535F','center');
 arrow(x+3.49,y+.33,.22);
 box(x+3.8,y,2.22,.66,tint);
 text(behavior,x+3.9,y+.055,2.02,.55,14,false,ink,'center');
 arrow(x+6.09,y+.33,.22);
 outcome(x+6.4,y,1.0,result);
}
function panel(x,y,label,title,task,goal,fill,border){
 box(x,y,7.55,3.58,fill,border);
 text(label+'. '+title,x+.16,y+.10,7.23,.4,21,true);
 text('Task: '+task,x+.16,y+.55,7.23,.24,14,true);
 box(x+.16,y+.88,7.23,.49,'FFFFFF',border);document(x+.28,y+1.0);
 text('Expected: '+goal,x+.57,y+.925,6.72,.38,14,true);
}
function lesson(x,y,t,fill,border){
 box(x+.16,y+3.14,7.23,.30,fill,border);
 text(t,x+.25,y+3.16,7.05,.25,12.8,true,ink,'center');
}
text('Task requirement → repair / revision → behavior or validation → benchmark outcome',.35,.20,15.30,.39,22,true,ink,'center');
const x1=.32,x2=8.13,y1=.83,y2=4.66;
panel(x1,y1,'a','Upstream vs. downstream repair','sympy__sympy-20428','Recognize mathematically zero polynomials.','EAF3FD','78A9D9');
row(x1,y1+1.58,'ORIG','Strip coefficients','densetools.py','Zero-recognition predicate unchanged','Unresolved','sympy__sympy-20428');
row(x1,y1+2.35,'CH','Fix zero recognition','expressiondomain.py','Recognize zero-valued expressions','Resolved','sympy__sympy-20428');
lesson(x1,y1,'The successful patch repairs the upstream zero predicate.','EAF3FD','78A9D9');
panel(x2,y1,'b','Repairing vs. rejecting valid usage','django__django-17084','Allow aggregation over window annotations.','FDECEE','D97E86');
row(x2,y1+1.58,'WRH','Add input checks','aggregates.py','Reject the operation with FieldError','Unresolved','django__django-17084');
row(x2,y1+2.35,'ORIG','Wrap query in a subquery','sql/query.py','Support the requested operation','Resolved','django__django-17084');
lesson(x2,y1,'Rejecting the requested operation does not restore its behavior.','FDECEE','D97E86');
panel(x1,y2,'c','Local validation vs. semantic coverage','astropy__astropy-13033','Report required-column errors consistently.','F0EDFA','AA94CC');
row(x1,y2+1.58,'ORIG','Format one error branch','timeseries/core.py','Column tests pass; empty-column branch unchanged','Unresolved','astropy__astropy-13033');
row(x1,y2+2.35,'CH','Handle both error branches','timeseries/core.py','Distinguish single / multiple-column messages','Resolved','astropy__astropy-13033');
lesson(x1,y2,'Same file and passing selected tests do not establish correctness.','F0EDFA','AA94CC');
panel(x2,y2,'d','Evidence-driven revision under WCH','pylint-dev__pylint-7080','Honor ignore-path rules during recursive linting.','EAF7EE','78B58D');
row(x2,y2+1.58,'ORIG','Add discovery filtering','pylinter.py','Path normalization remains unchanged','Unresolved','pylint-dev__pylint-7080');
const yy=y2+2.35;
box(x2+.16,yy,.78,.66,'E3F3E6');text('WCH',x2+.19,yy+.07,.72,.5,16,true,ink,'center');
arrow(x2+1.01,yy+.33,.20);
box(x2+1.3,yy,1.43,.66,'FFFFFF');text('Add filtering',x2+1.39,yy+.06,1.25,.53,13.5,true,ink,'center');
arrow(x2+2.80,yy+.33,.20);
box(x2+3.09,yy,1.45,.66,'FFF2D9');text('Reproduction still fails',x2+3.18,yy+.06,1.27,.53,13.5,true,ink,'center');
arrow(x2+4.61,yy+.33,.20);
box(x2+4.9,yy,1.27,.66,'E3F3E6');text('Normalize paths: remove ./',x2+4.98,yy+.06,1.11,.53,13.5,true,ink,'center');
arrow(x2+6.24,yy+.33,.15);outcome(x2+6.47,yy,.93,'Resolved');
lesson(x2,y2,'A failing reproduction precedes path normalization and resolution.','EAF7EE','78B58D');
box(.32,8.53,15.36,1.32,'EEF1F4','81909F',true);
text('?',.53,8.71,.28,.33,22,true,'52616B','center');
text('Evidence boundary — observed differences are not causal proof',.92,8.68,14.45,.35,19,true);
text('django__django-14765: ORIG removes set conversion (unresolved); CH asserts the set invariant and distinguishes None (resolved).',.55,9.10,14.9,.25,13.5);
text('One run per task-condition cannot establish whether the prompt caused the outcome difference; repeated runs and adjudicated trajectories are needed.',.55,9.47,14.9,.24,13.5,true);
text('Benchmark outcomes: check = resolved; cross = unresolved. CH / WCH / WRH name prompt conditions, not verified hypothesis truth.',.32,10.03,15.36,.23,11.5,false,'354451','center');
text('Behavior descriptions interpret recorded patches; cases are illustrative, overlapping, and not measured anchoring or recovery rates.',.32,10.32,15.36,.18,11,false,'354451','center');
slide.addNotes('Revised from six panels to four distinct task examples plus a neutral evidence boundary. All shapes, arrows, status icons and text are editable. Panel c merges former c/e, not two independent examples. Panel d shows WCH revision after a reproduction remained unsuccessful, based on reasoning events 173, 181, 185 and final patch 263. The path does not establish adjudicated recovery from the misleading hypothesis. The normalization change is in pylint/lint/expand_modules.py. Benchmark outcomes verified against evidence.json. Panel a failure leaves expressiondomain zero predicate unchanged; this is a patch interpretation, not an instrumented causal measurement. No hidden-test failure cause is claimed. The django-14765 boundary example is descriptive and not an established sixth mechanism.');
const out=path.join(__dirname,'figures/rq3-mechanisms-v3');fs.mkdirSync(out,{recursive:true});
ppt.writeFile({fileName:path.join(out,'rq3-mechanisms-v3.pptx')});
