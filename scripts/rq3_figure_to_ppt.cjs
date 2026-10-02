const fs = require('fs');
const pptxgen = require('/Users/gzq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pptxgenjs');
const root = '/Users/gzq/Repo/FSE2027';
const dir = root + '/figures/rq3-mechanisms-v2';
const cases = JSON.parse(fs.readFileSync(dir+'/cases.json','utf8'));
const ppt = new pptxgen();
ppt.defineLayout({name:'FIGURE',width:16,height:12});
ppt.layout='FIGURE';
ppt.author='FSE2027 research';
ppt.subject='RQ3 evidence-grounded case comparisons';
ppt.title='RQ3 case figure: original and editable';
ppt.lang='en-US';
ppt.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:'en-US'};
let slide=ppt.addSlide();
slide.background={color:'FFFFFF'};
slide.addImage({path:dir+'/rq3-mechanisms-v2.png',x:0,y:0,w:16,h:12});
slide.addNotes('Original verified raster figure, preserved without cropping. Slide 2 reconstructs the figure using editable PowerPoint shapes and text.');
slide=ppt.addSlide();
slide.background={color:'FFFFFF'};
const S=ppt.ShapeType;
function box(x,y,w,h,fill,line='CCD3DA',dash){
 slide.addShape(S.roundRect,{x,y,w,h,radius:.06,rectRadius:.06,
  fill:{color:fill},line:{color:line,width:.7,...(dash?{dashType:'dash'}:{})},radius:.04});
}
function text(t,x,y,w,h,size=15,bold=false,color='17212B',align='left'){
 slide.addText(t,{x,y,w,h,fontFace:'Arial',fontSize:size,bold,color,margin:0,align,
  valign:'mid',breakLine:false,paraSpaceAfter:0,fit:'shrink'});
}
function arrow(x,y,w){
 slide.addShape(S.line,{x,y,w,h:0,line:{color:'28343D',width:1.4,beginArrowType:'none',endArrowType:'triangle'}});
}
function document(x,y){
 slide.addShape(S.rect,{x,y,w:.18,h:.24,fill:{color:'FFFFFF'},line:{color:'263238',width:1}});
 for(let j=0;j<3;j++)slide.addShape(S.line,{x:x+.035,y:y+.06+j*.05,w:.11,h:0,line:{color:'263238',width:.8}});
}
function status(x,y,resolved){
 const color=resolved?'246C55':'A44F30';
 slide.addShape(S.ellipse,{x,y,w:.28,h:.28,fill:{color},line:{color,width:.5}});
 if(resolved){
  slide.addShape(S.line,{x:x+.065,y:y+.15,w:.055,h:.05,line:{color:'FFFFFF',width:1.5}});
  slide.addShape(S.line,{x:x+.12,y:y+.20,w:.10,h:-.12,line:{color:'FFFFFF',width:1.5}});
 }else{
  slide.addShape(S.line,{x:x+.08,y:y+.08,w:.12,h:.12,line:{color:'FFFFFF',width:1.5}});
  slide.addShape(S.line,{x:x+.08,y:y+.20,w:.12,h:-.12,line:{color:'FFFFFF',width:1.5}});
 }
}
box(.3,.16,15.4,.48,'EEF2F5','8392A0');
text('Task requirement → repair action → behavior / validation → benchmark outcome',.43,.2,15.14,.36,20,true,'17212B','center');
const fills=['EAF3FD','FDECEE','FFF7DF','EAF7EE','F0EDFA','EEF1F4'];
const borders=['78A9D9','D97E86','C8A94E','78B58D','AA94CC','81909F'];
cases.forEach((c,i)=>{
 const x=.3+(i%2)*7.83, y=.81+Math.floor(i/2)*3.43, w=7.57;
 box(x,y,w,3.29,fills[i],borders[i],i===5);
 text(c.id+'. '+c.title,x+.16,y+.1,w-.32,.38,20,true);
 text('Task: '+c.task,x+.16,y+.5,w-.32,.27,14,true);
 box(x+.16,y+.85,w-.32,.49,'FFFFFF',borders[i]);
 document(x+.29,y+.97);
 text('Expected: '+c.goal,x+.59,y+.89,w-.9,.40,14,true);
 c.paths.forEach((p,j)=>{
  const [cond,action,behavior,outcome,file]=p;
  const yy=y+1.48+j*.71;
  const good=outcome==='Resolved';
  const tint=good?'E3F3E6':'FBE4E7';
  box(x+.16,yy,.86,.59,tint);
  text(cond,x+.2,yy+.04,.78,.50,16,true,'17212B','center');
  arrow(x+1.08,yy+.29,.26);
  box(x+1.43,yy,2.12,.59,'FFFFFF');
  text(action,x+1.52,yy+.035,1.94,.34,13.5,true,'17212B','center');
  text(file,x+1.50,yy+.38,1.98,.17,file.length>30?8.5:10,false,'45535F','center');
  arrow(x+3.62,yy+.29,.24);
  box(x+3.96,yy,2.00,.59,tint);
  text(behavior,x+4.06,yy+.055,1.80,.47,13.5,false,'17212B','center');
  arrow(x+6.03,yy+.29,.22);
  box(x+6.34,yy,1.07,.59,tint);
  status(x+6.735,yy+.025,good);
  text(outcome,x+6.38,yy+.345,.99,.19,9.5,true,'17212B','center');
 });
 box(x+.16,y+2.97,w-.32,.22,fills[i],borders[i]);
 text(c.lesson,x+.27,y+2.95,w-.54,.25,12.7,true,'17212B','center');
 if(i===5) text('?',x+w-.5,y+.15,.23,.25,18,true,'52616B','center');
});
text('CH / WCH / WRH denote supplied prompt conditions, not validated hypothesis truth.',.3,11.19,15.4,.27,12,false,'354451','center');
text('Illustrative single runs; categories overlap. Behavior summaries interpret patches; outcomes are evaluator records.',.3,11.52,15.4,.27,12,false,'354451','center');
slide.addNotes('Editable reconstruction of verified figure v2. All text boxes, panels, arrows and status markers are native PowerPoint objects. Cases c/e share one task but focus on validation versus semantic coverage. Panel f is an evidence boundary, not an established mechanism. Outcomes originate from recorded evaluator rows. See evidence.json and figure-spec.json alongside the figure.');
ppt.writeFile({fileName:dir+'/rq3-mechanisms-v2.pptx'});
