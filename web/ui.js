import {masterForm,patternComparison} from './master-form.js';
import {rectangularProject,field} from './project-forms.js';
import {siteSize,placement,controlsForEdit,finishEdit,verifyProtected,checkpointResidual} from './site-photo.js';
import {colors,draw3,render,lighting,loadModel,bindSurface,calibration,capture,capturePass,getCamera,setCamera,projectWorldMM,resetModel,spaceView} from './view.js';
const $=id=>document.getElementById(id),prefix='/api/made/v1/',clone=v=>JSON.parse(JSON.stringify(v));
const box=(x,y,w,h)=>[[x,y],[x+w,y],[x+w,y+h],[x,y+h]];
function example(){
 const faces=['南','東','北','西'].map((id,i)=>({id,spans:Array(i%2?3:5).fill(9000),origin:[[0,0,0],[45000,0,0],[45000,0,-27000],[0,0,-27000]][i],azimuth:[0,-90,180,90][i],features:[]}));
 faces[0].features=[{kind:'logo',text:'Marq',corner:'left',poly:box(1000,800,4000,1500)},{kind:'band',shift:false,poly:box(13000,7900,18000,1300)},...Array.from({length:4},(_,i)=>({kind:'berth',number:i+1,poly:box(3500+i*9000,16100,4000,4000)}))];
 return {schema:'made-project-3',name:'Marq 外装計画',mode:'H',stock:'dry',pitch:750,floors:[7000,6500,6600],faces,scan:'auto',rules:'p18-baseline',wave:'234565432',seed:0,assets:[],light:{sky:'day',ambient:2.5,az:42,alt:45,shadow:true},spaces:{},prices:{},intent:''};
}
let p=example(),r,faceIndex=0,pid=null,head=0,opened=0,record,dirty=true,serial=0,undo=[],brushStart,outline=null,transform,refImg,background,plate,protectedLayer,foreground,user,active='elevation',modelLoaded=null;
const status=s=>$('status').textContent=s;
async function call(route,b){
 const res=await fetch(prefix+route,b===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Made-Request':'1'},body:JSON.stringify(b)});
 const d=await res.json();if(!res.ok)throw Error(d.error||res.statusText);return d;
}
function handle(id,fn){$(id).onclick=async e=>{try{await fn(e)}catch(err){status(err.message)}}}
function node(tag,txt){const n=document.createElement(tag);if(txt!=null)n.textContent=txt;return n}
function button(txt,fn){const b=node('button',txt);b.type='button';b.onclick=async()=>{try{await fn()}catch(e){status(e.message)}};return b}
function selectOptions(el,rows){el.replaceChildren(...rows.map(([v,t])=>new Option(t,v)))}
function download(name,data){const a=node('a');const local=data instanceof Blob;a.href=local?URL.createObjectURL(data):data;a.download=name;a.click();if(local)setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
const fileData=f=>new Promise((ok,no)=>{const fr=new FileReader();fr.onload=()=>ok(fr.result);fr.onerror=no;fr.readAsDataURL(f)});
const image=url=>new Promise((ok,no)=>{const im=new Image();im.onload=()=>ok(im);im.onerror=()=>no(Error('画像を読み込めません'));im.src=url});
async function modal(title,content,yes='適用'){
 const d=document.querySelector('dialog');$('dialogTitle').textContent=title;$('dialogContent').replaceChildren(content);$('confirm').textContent=yes;
 d.showModal();return new Promise(ok=>d.addEventListener('close',()=>ok(d.returnValue==='ok'),{once:true}));
}
async function editText(title,value,cb){const el=node('textarea');el.value=value;if(await modal(title,el))await cb(el.value)}
function mark(){dirty=true;if(p.intentPlanVersion)showIntentFacts(null);serial++;$('version').textContent=(opened?'r'+opened+' · ':'')+'編集中'}
function remember(){undo.push(clone(p));if(undo.length>15)undo.shift();mark()}
function fields(){
 $('intentPilot').checked=p.intentPlanVersion===1;syncIntentPanel();
 const f=p.faces[faceIndex];for(const id of ['name','stock','mode','pitch','scan','wave','rules','seed','intent'])$(id).value=p[id]??'';
 $('floors').value=(f.floors||p.floors).join(',');$('spans').value=f.spans.join(',');$('parapet').value=f.parapet||0;$('limit').value=f.limit??'';$('tenant').checked=!!p.tenantTop;$('consent').checked=!!p.externalConsent;
 selectOptions($('face'),p.faces.map((s,i)=>[i,s.id]));$('face').value=faceIndex;
 for(const id of ['sky','ambient','az','alt'])$(id).value=p.light?.[id]??example().light[id];$('shadow').checked=p.light?.shadow!==false;
}
function read(){
 const f=p.faces[faceIndex];for(const id of ['name','stock','mode','scan','wave','rules','intent'])p[id]=$(id).value;
 p.pitch=Number($('pitch').value);p.seed=Number($('seed').value);const list=id=>$(id).value.split(/[,、，]/).map(Number);const floors=list('floors');
 if(f.floors||JSON.stringify(floors)!==JSON.stringify(p.floors))f.floors=floors;
 f.spans=list('spans');f.parapet=Number($('parapet').value);f.limit=$('limit').value===''?null:Number($('limit').value);p.tenantTop=$('tenant').checked;p.externalConsent=$('consent').checked;
 p.light=Object.fromEntries(['sky','ambient','az','alt'].map(id=>[id,id==='sky'?$(id).value:Number($(id).value)]));p.light.shadow=$('shadow').checked;
}
function paint(){
 if(!r)return;const c=$('plan'),ctx=c.getContext('2d'),s=r.faces.find(s=>s.face===p.faces[faceIndex].id);if(!s)return;
 const k=Math.min((c.width-92)/s.width,(c.height-80)/s.height),ox=(c.width-k*s.width)/2,oy=(c.height-k*s.height)/2;transform={ox,oy,k};
 ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#eff3f5';ctx.fillRect(0,0,c.width,c.height);ctx.save();ctx.translate(ox,oy);ctx.scale(k,k);
 function path(poly){ctx.beginPath();for(let i=0;i<poly.length;i++)ctx[i?'lineTo':'moveTo'](...poly[i]);ctx.closePath()}
 for(const a of r.pieces){if(a.face!==s.face)continue;path(a.poly);ctx.fillStyle=colors[a.finish];ctx.globalAlpha=a.hidden?.25:1;ctx.fill()}
 ctx.globalAlpha=1;ctx.beginPath();for(const seam of r.seams||[])if(seam.face===s.face)for(const [a,b] of seam.segments){ctx.moveTo(...a);ctx.lineTo(...b)}ctx.strokeStyle='#677783';ctx.lineWidth=.45/k;ctx.stroke();
 for(const m of r.labels.filter(m=>m.face===s.face)){const [x,y]=m.poly[0],w=m.poly[2][0]-x,h=m.poly[2][1]-y;const berth=m.kind==='berth',height=berth?h*.2:h;ctx.fillStyle=berth?'#15202d':'#fff';ctx.fillRect(x,berth?y-height:y,w,height);ctx.font='bold '+Math.max(1,height*.7)+'px sans-serif';ctx.textAlign='center';ctx.fillStyle=berth?'#fff':'#1b43b0';ctx.fillText(m.text,x+w/2,berth?y-height*.2:y+height*.78,w*.94)}
 if(p.intentPlanVersion&&r.intentFacts?.faceId===s.face&&$('intentDiff').checked){
  const changed=new Set(r.intentFacts.changedPanels);ctx.save();
  ctx.strokeStyle='#dd661d';ctx.lineWidth=2/k;
  for(const a of r.pieces)if(changed.has(a.panel)){path(a.poly);ctx.stroke()}
  ctx.fillStyle='rgba(33,112,174,.12)';
  for(const q of r.intentFacts.quietIntervals||[])ctx.fillRect(q.start*s.width,0,(q.end-q.start)*s.width,s.height);
  ctx.restore();
 }
 if(refImg){ctx.globalAlpha=.25;ctx.drawImage(refImg,0,0,s.width,s.height);ctx.globalAlpha=1}
 if(outline?.length){path(outline);ctx.strokeStyle='#e3482e';ctx.lineWidth=2/k;ctx.stroke()}
 ctx.restore();ctx.fillStyle='#38526a';ctx.font='18px sans-serif';ctx.textAlign='left';ctx.fillText(s.face+'立面  /  '+s.width.toLocaleString()+' × '+s.height.toLocaleString()+' mm',20,c.height-14);
}
function metrics(){if(p.intentPlanVersion)showIntentFacts(r.intentFacts);const s=r.faces.find(v=>v.face===p.faces[faceIndex].id)||r.faces[0];$('metric').replaceChildren(...[['モジュール',r.type],['原板 ID',s.panels],['仕上純量',(Object.values(s.finishes).reduce((a,b)=>a+b,0)/1e6).toFixed(2)+' m²'],['アクセント',s.ratio.toFixed(2)+' %'],['制約',r.status==='feasible'?(r.intentFacts?'計算済み':'適合候補'):'要確認']].map(([a,b])=>{const d=node('div');d.append(node('small',a),node('strong',b));return d}));$('meaning').textContent=r.meaning}
let need3=true;
async function calc(){
 read();const n=++serial;const result=await call('solve',{spec:p,pid});if(n!==serial)return false;r=result;protectedLayer=null;need3=true;paint();metrics();if(active==='scene')view3();
 status(r.issues.join('\n')||'計算済み · '+r.resultId);return true;
}
function view3(){if(!r)return;try{if(need3){draw3(p,r,assetUrl);if(p.camera)setCamera(p.camera);need3=false}else render()}catch(e){status('3D表示：'+e.message+'。展開立面を利用できます。')}}
async function page(id){active=id;document.querySelectorAll('.page').forEach(s=>s.hidden=s.id!==id);document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===id));if(id==='scene')view3();if(id==='review')await history()}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>page(b.dataset.view).then(()=>{if(b.dataset.view==='photo'&&background)return compose()}).catch(e=>status(e.message)));
for(const id of ['name','stock','mode','pitch','floors','spans','parapet','scan','wave','tenant','limit','rules','seed','intent','consent'])$(id).onchange=()=>{remember();read();status('条件変更済み。「割付を計算」で結果を更新します。')};
for(const id of ['sky','ambient','az','alt','shadow'])$(id).oninput=()=>{read();mark();lighting(p.light)};
$('face').onchange=async()=>{read();faceIndex=+$('face').value;fields();refImg=null;await restoreReference();paint();if(r)metrics()};
handle('calc',calc);handle('undo',async()=>{if(!undo.length)return;p=undo.pop();faceIndex=Math.min(faceIndex,p.faces.length-1);fields();mark();await calc()});
function uv(e){const b=$('plan').getBoundingClientRect(),t=transform,c=$('plan');return [Math.round(((e.clientX-b.left)*c.width/b.width-t.ox)/t.k),Math.round(((e.clientY-b.top)*c.height/b.height-t.oy)/t.k)]}
const hit=(pt,poly)=>{let yes=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const [x,y]=poly[i],[X,Y]=poly[j];if((y>pt[1])!==(Y>pt[1])&&pt[0]<(X-x)*(pt[1]-y)/(Y-y)+x)yes=!yes}return yes};
$('plan').onpointerdown=e=>{if(!transform)return;const a=uv(e);if(outline){outline.push(a);paint();return}brushStart=a;$('plan').setPointerCapture(e.pointerId)};
$('plan').onpointercancel=()=>brushStart=null;
$('plan').onpointerup=async e=>{try{if(!brushStart)return;const from=brushStart;brushStart=null;const to=uv(e),b=$('brush').value,f=p.faces[faceIndex],s=r.faces.find(v=>v.face===f.id);
 if(b==='inspect'){const a=r.pieces.find(a=>a.face===f.id&&hit(to,a.poly));if(a){$('inspect').replaceChildren(node('span',a.panel+'  /  '+a.finish+'  /  '+(a.area/1e6).toFixed(3)+' m²  /  '+a.trace.join(' → ')),button('仕上を固定',async()=>{const sel=node('select');selectOptions(sel,Object.keys(colors).map(k=>[k,k]));sel.value=a.finish;if(await modal('板 '+a.panel,sel)){remember();(p.locks||={})[a.panel]=sel.value;await calc()}}))}return}
 const x=Math.max(0,Math.min(from[0],to[0])),y=Math.max(0,Math.min(from[1],to[1])),X=Math.min(s.width,Math.max(from[0],to[0])),Y=Math.min(s.height,Math.max(from[1],to[1]));if(X<=x||Y<=y)return;remember();let feature={kind:b,poly:box(x,y,X-x,Y-y)};
 if(b==='berth')feature.number=1+Math.max(0,...p.faces.flatMap(f=>f.features.filter(a=>a.kind==='berth').map(a=>+a.number)));
 if(b==='slope')feature.poly=[[x,y],[X,y+(Y-y)*.7],[X,Y],[x,Y]];
 if(b==='logo'){feature.text='Marq';feature.corner=x<s.width*.12?'left':X>s.width*.88?'right':false}
 f.features.push(feature);await calc()}catch(e){status(e.message)}};
handle('outline',()=>{outline=[];status('展開図で輪郭頂点を順番に指定し、「輪郭を確定」を押してください')});
handle('finishOutline',async()=>{if(!outline||outline.length<3)throw Error('3点以上指定してください');remember();p.faces[faceIndex].outline=outline;outline=null;await calc()});
handle('png',()=>download('Marq-'+r.resultId+'.png',$('plan').toDataURL()));
async function ensureProject(){if(!pid){const v=await call('new',{name:p.name});pid=v.id;head=0}}
async function uploadFile(file){
 await ensureProject();const owner=p,projectId=pid;const rr=await fetch(prefix+'file?pid='+projectId+'&name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-Made-Request':'1'},body:file});const d=await rr.json();if(!rr.ok)throw Error(d.error);if(owner!==p||projectId!==pid)throw Error('案件が切り替わりました');(p.assets||=[]).push(d.id);mark();return d.id;
}
const assetUrl=id=>prefix+'asset?pid='+pid+'&id='+id;
async function restoreReference(){const k=p.faces[faceIndex].reference;if(k&&pid)refImg=await image(assetUrl(k));else refImg=null}
function onfile(id,fn){$(id).onchange=async e=>{const f=e.target.files[0];e.target.value='';try{if(f)await fn(f)}catch(er){status(er.message)}}}
onfile('ref',async f=>{const k=await uploadFile(f);p.faces[faceIndex].reference=k;await restoreReference();paint()});
async function showModel(bytes,name,key){await page('scene');const report=await loadModel(bytes,name,key,p.model?.transform);modelLoaded=key;if(p.camera)setCamera(p.camera);status(report.triangles.toLocaleString()+' triangles · 基準面の2点で実寸を合わせてください')}
onfile('model',async f=>{if(f.size>50*1024*1024)throw Error('50 MB以下の静的モデルを選択してください');const key=await uploadFile(f);p.model={key,name:f.name};await showModel(await f.arrayBuffer(),f.name,key)});
handle('sampleModel',async()=>{const data=await(await fetch('building01.json')).json();const div=node('p','実測4立面を独立した新規案件として開きます。現在の未保存作業は先に保存してください。');if(!await modal('building01 実モデル検証',div,'開く'))return;resetModel();pid=null;head=opened=faceIndex=0;refImg=plate=protectedLayer=background=null;undo=[];p=data;mark();fields();await calc();await showModel(await (await fetch('building01_facade_clean.glb')).arrayBuffer(),p.model.name,'sample')});
handle('bind',async()=>{await page('scene');const f=p.faces[faceIndex],s=r.faces.find(a=>a.face===f.id);calibration(f,s.height,tr=>{p.model.transform=tr;mark();status('2点の基準を保存しました。別の軸距と高さも確認してください')},status)});
handle('snap',()=>download('Marq-view.png',capture()));
onfile('background',async f=>{plate=null;protectedLayer=null;p.photo={background:await uploadFile(f)};background=await image(await fileData(f));await compose()});
async function compose(){
 if(!background)throw Error('計画地写真を指定してください');
 if(!protectedLayer){await page('scene');view3();protectedLayer=await image(capture(true));await page('photo')}
 const c=$('composition'),[w,h]=siteSize(background);c.width=w;c.height=h;
 const ctx=c.getContext('2d'),settings=photoSettings();
 Object.assign(p.photo,settings);showCheckpoints();
 if(p.photo.final && p.photo.binding===photoBinding()){
  const owner=p,im=await image(assetUrl(p.photo.final));
  if(owner===p&&p.photo.binding===photoBinding())ctx.drawImage(im,0,0,w,h);
  return;
 }
 ctx.drawImage(plate||background,0,0,w,h);
 ctx.drawImage(protectedLayer,...placement(w,h,protectedLayer,settings));
 if(foreground&&p.photo.foreground)ctx.drawImage(foreground,0,0,w,h);
}
function photoSettings(){return {cx:+$('cx').value,cy:+$('cy').value,scale:+$('scale').value}}
function photoBinding(){
 const parts=[r.resultId,p.photo.background,p.photo.foreground,photoSettings(),p.camera,p.light,p.model];
 if(p.intentPlanVersion&&protectedLayer)parts.push(protectedLayer.width,protectedLayer.height);
 return JSON.stringify(parts)
}
handle('compose',async()=>{protectedLayer=null;p.camera=getCamera()||p.camera;delete p.photo?.binding;await compose();mark()});
for(const id of ['cx','cy','scale'])$(id).oninput=()=>{mark();compose().catch(e=>status(e.message))};
function registrationBinding(){
 return JSON.stringify([r.resultId,p.photo.background,photoSettings(),p.camera,p.model,protectedLayer.width,protectedLayer.height]);
}
handle('recordCheck',async()=>{
 if(!background)throw Error('写真を読み込んでください');
 await page('scene');view3();p.camera=getCamera();protectedLayer=await image(capture(true));await page('photo');await compose();
 const current=p,stamp=serial,binding=registrationBinding(),div=node('div'),canvas=$('composition');
 const [w,h]=[canvas.width,canvas.height];
 div.append(node('p',w+' × '+h+' px ／ 立面モデルの世界座標は Y が上です。カメラの調整に使っていない点を独立検査点に指定してください。'));
 const role=field(div,'点の用途','check',[['check','独立検査点'],['control','位置合わせに使用した点']]);
 const inputs=['世界 X mm','世界 Y mm','世界 Z mm','画像 X px','画像 Y px'].map(label=>field(div,label,''));
 for(const input of inputs){input.type='number';input.step='any'}
 if(!await modal('写真の対応点を記録',div,'再投影誤差を計算'))return;
 if(p!==current||serial!==stamp||binding!==registrationBinding())throw Error('視点または写真が変わりました');
 if(inputs.some(input=>!input.value.trim()))throw Error('5つの座標を入力してください');
 const numbers=inputs.map(input=>Number(input.value));
 const result=checkpointResidual(projectWorldMM,numbers.slice(0,3),numbers.slice(3),w,h,protectedLayer,photoSettings());
 const existing=p.photo.registration?.binding===binding?p.photo.registration.points:[];
 if(existing.length>=64)throw Error('対応点は1視点64点までです');
 remember();p.photo.registration={binding,width:w,height:h,points:[...existing,{...result,role:role.value}]};
 showCheckpoints();status('この視点の対応点を記録しました。版を保存してください');
});
function showCheckpoints(){
 if(!p.intentPlanVersion||!background||!protectedLayer)return;
 const registration=p.photo?.registration,out=$('checkResidual');
 if(!registration){out.textContent='目視合わせ';return}
 if(registration.binding!==registrationBinding()){out.textContent='視点・画幅が変わりました。再校正してください。';return}
 const checks=registration.points.filter(q=>q.role==='check');
 const rms=checks.length?Math.sqrt(checks.reduce((total,q)=>total+q.errorPX**2,0)/checks.length):null;
 out.textContent='対応点 '+registration.points.length+' 点 ／ 独立検査点 '+checks.length+' 点'+(rms===null?' ／ 目視合わせ':' ／ RMS '+rms.toFixed(2)+' px');
}
handle('photoRights',async()=>{
 if(!p.photo?.background)throw Error('背景写真を読み込んでください');
 const div=node('div'),source=field(div,'権利者・利用根拠（許諾番号等）',p.photo.rights?.source||'');
 const consent=node('input');consent.type='checkbox';const label=node('label');
 label.append(consent,document.createTextNode('背景・合成図・深度・保護マスクを承認済み端点に送信できる'));div.append(label);
 if(!await modal('写真と前景の使用許諾',div))return;
 if(!source.value.trim()||source.value.length>300)throw Error('利用根拠を300文字以内で記入してください');
 remember();p.photo.rights={source:source.value.trim(),external:consent.checked,background:p.photo.background,foreground:p.photo.foreground||null};
 status('許諾範囲を記録しました。版を保存してください');
});
handle('photoOut',async()=>{await compose();download('Marq-site-'+r.resultId+'.png',$('composition').toDataURL())});
handle('aiImage',async()=>{
 if(!background)throw Error('計画地の空撮写真を指定してください');
 const owner=p; p.camera=getCamera()||p.camera;
 if(!await calc())throw Error('設計更新後に再実行してください');
 await ensureProject();
 if(!p.externalConsent||!head)throw Error('外部送信を許可して案件版を保存してください');
 const btn=$('aiImage');btn.disabled=true;
 try{
  await page('scene');
  let rgba,z;
  try{if(need3)throw Error('外観3Dの再描画に失敗しました');rgba=capture(true);z=capturePass('siteDepth');p.camera=getCamera()}finally{await page('photo')}
  const [building,depth]=await Promise.all([image(rgba),image(z)]);
  if(p.intentPlanVersion)protectedLayer=building;
  const fg=p.photo.foreground?foreground:null;
  const control=controlsForEdit(background,building,depth,fg,photoSettings());
  const binding=photoBinding(),stamp=serial;
  status('建物の輪郭・深度を固定してAI合成中…');
  const response=await call('ai',{pid,n:opened,kind:'image',spec:p,payload:{...control.payload,intent:p.intent,environment:p.light.sky}});
  const output=finishEdit(await image(response.image),control,building,fg);
  const check=p.intentPlanVersion?verifyProtected(output,control,building,fg):null;
  const blob=await new Promise(ok=>output.toBlob(ok,'image/png'));
  if(owner!==p||stamp!==serial||binding!==photoBinding())throw Error('生成中に設計が変更されました。再実行してください');
  const final=await uploadFile(new File([blob],'site-composite.png',{type:'image/png'}));
  if(owner!==p||binding!==photoBinding())throw Error('配置が変更されました。再実行してください');
  if(check)p.photo.pixelCheck={...check,binding};
  p.photo.final=final;p.photo.binding=binding;protectedLayer=building;
  await compose();status('AI合成が完了しました。PNG出力または版を保存してください')
 }finally{btn.disabled=false}
});
$('intentDiff').onchange=paint;
function syncIntentPanel(){
 $('jsonOut').textContent=p.intentPlanVersion&&(p.intentDraft||p.forkedIntentResult)?'保存版の参照 JSON（同じ環境用）':'工程 JSON 保存';
 $('intentPanel').hidden=p.intentPlanVersion!==1;
 $('photoChecks').hidden=p.intentPlanVersion!==1;
 $('pilotExportScope').hidden=p.intentPlanVersion!==1;
 $('clearIntent').hidden=!p.intentDraft&&!p.forkedIntentResult;
}
function showIntentFacts(facts){
 syncIntentPanel();
 const current=facts?.faceId===p.faces[faceIndex]?.id, chart=$('density');
 chart.hidden=!current;
 $('planFacts').textContent=current
  ? r.meaning+' 分母 '+(facts.denominator==='visible'?'可視':'純面積')+' '+(facts.denominatorMM2/1e6).toFixed(2)+' m² ／ '+facts.source.join('・')+
    (facts.search==='budgetFeasible'?' ／ 計算予算内の検証済み候補':'')+' ／ 青線：目標、黒線：実面積'
  : (p.intentDraft?'保存版の対象面と計算結果を確認してください。':'この案件を保存後、対象立面と計画の狙いを選択してください。');
 if(!current)return;
 const ctx=chart.getContext('2d');ctx.clearRect(0,0,chart.width,chart.height);
 for(const [key,color] of [['target','#2866ba'],['actual','#202c37']]){
  ctx.strokeStyle=ctx.fillStyle=color;ctx.lineWidth=2;ctx.beginPath();
  facts.profile.forEach((v,i)=>{const x=5+v.u*(chart.width-10),y=chart.height-5-v[key]*(chart.height-10);
   if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);
   ctx.fillRect(x-2,y-2,4,4);
  });ctx.stroke();
 }
}
function releaseIntent(){
 delete p.intentDraft;delete p.forkedIntentResult;
 $('clearIntent').hidden=true;
}
$('intentPilot').onchange=async()=>{
 try{
  remember();
  if($('intentPilot').checked){p.intentPlanVersion=1;await ensureProject()}
  else{releaseIntent();delete p.intentPlanVersion}
  fields();await calc();
 }catch(e){status(e.message)}
};
handle('clearIntent',async()=>{remember();releaseIntent();fields();await calc()});
handle('channelSettings',async()=>{
 await ensureProject();const owner=p,channels=await call('pilot-channels',{pid});
 const div=node('div'),entries=[];
 for(const [kind,ch] of Object.entries(channels)){
  const label=node('label'),box=node('input');box.type='checkbox';box.checked=p.channelGrants?.[kind]===ch.id;
  label.append(box,document.createTextNode([kind==='text'?'意図の範囲':'写真編集',ch.account,ch.model,ch.region,ch.expires].join(' ／ ')));
  div.append(label);entries.push([kind,ch.id,box]);
 }
 if(!entries.length)div.append(node('p','契約・合成サンプルを検証済みの接続先はありません。ローカル計画を利用できます。'));
 if(!await modal('案件で許可する接続先',div)||p!==owner)return;
 remember();p.channelGrants=Object.fromEntries(entries.filter(row=>row[2].checked).map(([kind,id])=>[kind,id]));
 status('接続先を記録しました。外部送信の許可とともに版を保存してください');
});
async function planIntent(via){
 if(!pid||!opened||dirty)throw Error('先に現在の設計条件を版として保存してください');
 const owner=pid,revision=opened,stamp=serial,face=p.faces[faceIndex].id;
 const draft=await call('intent-plan',{pid,n:revision,faceId:face,goal:$('intentGoal').value,via});
 const div=node('div');
 div.append(node('p',face+'面 ／ r'+revision+' ／ 道路からの視点 ／ '+draft.evidenceRefs.join('・')));
 if(draft.goal==='entrance')div.append(node('p',draft.anchors.length?'この面の保存済み入口位置を参照します。':'入口の登録がないため、中央を仮の余白にしています。位置を確認してください。'));
 const controls=[],handles=[];
 function percent(label,item,key,min=0){
  const input=field(div,label+'（左端を0とする %）',String(+(item[key]*100).toFixed(4)));
  input.type='number';input.step='any';input.min=min;input.max=100;
  if(key!=='width')handles.push({input,key,label});
  controls.push(()=>{if(!input.value||!input.checkValidity())throw Error(label+'を確認してください');item[key]=Number(input.value)/100});
 }
 for(const q of draft.quietIntervals){percent('余白の開始',q,'start');percent('余白の終了',q,'end')}
 draft.peaks.forEach((peak,i)=>{percent('ピーク '+(i+1)+' の中心',peak,'center');percent('ピーク '+(i+1)+' の幅',peak,'width',.0001)});
 const strip=node('canvas');strip.width=560;strip.height=66;strip.style.touchAction='none';div.append(strip);
 function drawHandles(){
  const ctx=strip.getContext('2d');ctx.clearRect(0,0,strip.width,strip.height);
  ctx.fillStyle='#e7edf1';ctx.fillRect(8,28,544,10);
  for(const h of handles){
   const x=8+5.44*Number(h.input.value),y=h.key==='center'?18:47;
   ctx.fillStyle=h.key==='center'?'#245dba':'#426c57';ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.fill();
  }
 }
 handles.forEach(h=>h.input.addEventListener('input',drawHandles));drawHandles();
 let dragged=null;
 function coordinates(e){
  const rect=strip.getBoundingClientRect();
  return [(e.clientX-rect.left)*560/rect.width,(e.clientY-rect.top)*66/rect.height];
 }
 strip.onpointerdown=e=>{
  const [x,y]=coordinates(e);
  dragged=handles.find(h=>Math.hypot(x-8-5.44*Number(h.input.value),y-(h.key==='center'?18:47))<14);
  if(dragged)strip.setPointerCapture(e.pointerId);
 };
 strip.onpointermove=e=>{
  if(!dragged)return;
  dragged.input.value=Math.max(0,Math.min(100,(coordinates(e)[0]-8)/5.44)).toFixed(1);drawHandles();
 };
 strip.onpointerup=strip.onpointercancel=()=>{dragged=null};
 const permit=node('input'),strict=node('input');permit.type=strict.type='checkbox';
 if(p.mode==='wave'){
  const label=node('label');label.append(permit,document.createTextNode('別冊の適用範囲を確認し、この面の番手変更を許可'));div.append(label);
  const layer=node('label');layer.append(strict,document.createTextNode('上下の強調モジュールで同じ番手を禁止する'));div.append(layer);
 }else div.append(node('p','指定配列を固定し、目標と実際の分布を比較します。'));
 if(!await modal('立面の意図計画',div,'条件を確定して試算'))return;
 controls.forEach(fn=>fn());if(permit.checked)draft.approvedEditable=['moduleLevels'];draft.strictLayers=strict.checked;
 const current=()=>pid===owner&&opened===revision&&serial===stamp&&p.faces[faceIndex].id===face;
 if(!current())throw Error('対象版または立面が変更されました');
 const next={...p,intentDraft:draft};
 let candidate;
 try{candidate=await call('solve',{pid,spec:next})}
 catch(error){throw Error('新しい意図案は未作成です。画面は直前の版です。 '+error.message)}
 if(!current())throw Error('計算中に条件が変わりました');
 remember();p=next;r=candidate;need3=true;protectedLayer=null;fields();paint();metrics();status(candidate.issues.join(' ／ ')||'意図案を計算しました。版を保存して比較表を出力できます。');
}
handle('planIntent',()=>planIntent('local'));
handle('intentApply',async()=>{if(p.intentPlanVersion)return planIntent('local');remember();const t=$('intent').value;if(/縦|竖|vertical|上層|留白/.test(t))p.mode='wave';if(/横|horizontal/.test(t))p.mode='H';const n=t.match(/(\d+(?:\.\d+)?)\s*[%％]/);if(n)p.faces[faceIndex].limit=+n[1];p.intent=t;fields();await calc()});
handle('aiText',async()=>{if(p.intentPlanVersion)return planIntent('text');read();await ensureProject();const v=await call('ai',{pid,kind:'text',spec:p,payload:{intent:p.intent,meaning:r.meaning,allowedWaves:[...$('wave').options].map(v=>v.value)}});const panel=node('div');panel.append(node('p',v.narrative),node('p',String(v.mode||'')+' '+String(v.wave||'')));if(await modal('AI案と設計説明',panel)){remember();if(['H','V','wave'].includes(v.mode))p.mode=v.mode;if([...$('wave').options].some(o=>o.value===v.wave))p.wave=v.wave;p.aiNarrative=String(v.narrative||'');fields();await calc();$('meaning').textContent+=' '+p.aiNarrative}});
handle('jsonOut',()=>{
 read();let document=p;
 if(p.intentPlanVersion&&(p.intentDraft||p.forkedIntentResult)){
  if(!pid||!opened||dirty)throw Error('意図案を版として保存してから参照を書き出してください');
  document={schema:'made-revision-reference-v1',project:pid,revision:opened,resultId:r.resultId,name:p.name};
 }
 download('Marq-project.json',new Blob([JSON.stringify(document,null,2)],{type:'application/json'}))
});
handle('edit',()=>editText('案件条件・立面・構件（mm）',JSON.stringify(p,null,2),async txt=>{const next=JSON.parse(txt);await call('solve',{spec:next,pid});remember();p=next;faceIndex=0;fields();await calc()}));
handle('spaces',async()=>{const menu=node('div'),items=['アプローチ・歩車分離','外構・植栽の視認性','エントランスホール','エレベーターホール','共用廊下','事務室','休憩室・カフェテリア','トイレ'];const boxes=[];for(const s of items){const l=node('label',s+' '),v=node('input');v.value=p.spaces?.[s]||'';v.placeholder='素材・照明・サイン・確認者';l.append(v);menu.append(l);boxes.push([s,v])}if(await modal('Marq Aura / Inspire　空間別仕様',menu)){remember();p.spaces=Object.fromEntries(boxes.map(([s,v])=>[s,v.value]))}});
const tourButton=button('外構・共用空間の3D検討',async()=>{
 const sel=node('select');selectOptions(sel,['アプローチ','エントランスホール','エレベーターホール','共用廊下','事務室','休憩室・カフェテリア','トイレ'].map(v=>[v,v]));
 if(!await modal('検討する空間',sel))return;
 const title=sel.value,item=p.spaceScenes?.[title]||{category:title==='アプローチ'?'approach':'interior',dimensions:[12000,3500,8000],wall:'#dedbd4',floor:'#999895',accent:'#2452b2',lighting:'昼白色',sign:'入口サイン',review:{CONTINUITY:'',DURABILITY:'',COST_CONSCIOUS:'',USER_CENTRIC:'',FLEXIBILITY:''}};
 await editText(title+' · 仕上・寸法・照明・サイン・照査',JSON.stringify(item,null,2),async txt=>{const v=JSON.parse(txt);if(!Array.isArray(v.dimensions)||v.dimensions.length!==3||!v.dimensions.every(x=>x>0&&x<1e6))throw Error('寸法は正のmm値');remember();(p.spaceScenes||={})[title]=v;await page('scene');spaceView(v);status(title+' · 基本仕上モデル')})
});
$('spaces').after(tourButton);$('snap').parentElement.append(button('外観へ戻る',()=>spaceView(null)));
function legacy(d){
 if(d.schema==='made-project-3')return d;
 const q=example();q.name='既存案からの検討';
 if(d.schema==='marq-pattern-v1'){if(!Array.isArray(d.cells)||!d.params||d.cells.length!==d.params.cols*d.params.rows||d.cells.length>200000)throw Error('自由図案の形式が不正です');q.visualReference=d;q.importReview='自由図案は検討参考。ルールとの対応は未確認です';return q}
 return call('migrate',{document:d});
}
onfile('jsonIn',async f=>{
 const doc=JSON.parse(await f.text());
 if(doc.schema==='made-revision-reference-v1'){
  const project=encodeURIComponent(doc.project),n=Number(doc.revision);
  if(!Number.isSafeInteger(n)||n<1)throw Error('保存版の番号が不正です');
  const source=await call('revision?pid='+project+'&n='+n);
  if(source.result.resultId!==doc.resultId)throw Error('参照先の意図案と結果IDが一致しません');
  const branch=await call('fork',{pid:doc.project,n,name:source.spec.name+' 複製'});
  resetModel();modelLoaded=null;pid=branch.id;await history();await openRev(1);return;
 }
 const q=await legacy(doc);await call('solve',{spec:q});resetModel();modelLoaded=null;p=q;pid=null;opened=head=faceIndex=0;undo=[];refImg=background=plate=protectedLayer=null;fields();mark();await calc();status('新しい草案として読込。'+(q.importReview||'素材は再関連付けが必要です。'))});
async function history(){
 if(!pid){$('history').textContent='版を保存すると比較・出力できます。';$('jobs').replaceChildren();return}
 const owner=pid,latest=await call('project?pid='+owner);if(owner!==pid)return;record=latest;const list=node('select');list.id='revSelect';selectOptions(list,record.revisions.map(v=>[v.n,'r'+v.n+' · '+v.state+' · '+v.author]));if(opened)list.value=opened;
 $('history').replaceChildren(list,button('この版を開く',()=>openRev(+list.value)));
 $('audit').textContent=record.audit.map(a=>a.ts+'  '+a.actor+'  '+a.action).join('\n');
 $('jobs').replaceChildren(...record.jobs.map(j=>{const el=node('div',j.kind.toUpperCase()+' · r'+j.n+' · '+j.status+'  ');if(['ready','accepted','proof','changes','delivered','verified'].includes(j.status)){const a=node('a','ダウンロード');a.href=prefix+'download?pid='+pid+'&id='+j.id;el.append(a)}
 const actions={queued:['cancelled'],running:['cancelled'],failed:['queued'],cancelled:['queued'],ready:['accepted'],accepted:['proof'],proof:['changes','delivered'],changes:['proof'],delivered:['verified']}[j.status]||[];
 for(const state of actions){if(j.kind!=='cg'&&!['queued','cancelled'].includes(state))continue;el.append(button(state,async()=>{let asset;if(state==='delivered'){const f=node('input');f.type='file';if(!await modal('納品画像を添付',f)||!f.files[0])return;asset=await uploadFile(f.files[0])}await call('jobStatus',{pid,id:j.id,state,asset});await history()}))}
 if(j.kind==='cg'&&j.msg&&['delivered','verified'].includes(j.status)){const a=node('a','納品画像を保存');a.href=assetUrl(j.msg);a.download='Marq-r'+j.n+'-CG.png';el.append(a)}
 else if(j.msg&&j.status!=='running')el.append(node('span',j.msg));return el}));
}
async function openRev(n){
 const owner=pid,rr=await call('revision?pid='+owner+'&n='+n);if(owner!==pid)return;p=rr.spec;r=rr.result;opened=n;head=record?.project?.head??n;faceIndex=0;dirty=false;need3=true;undo=[];fields();await restoreReference();paint();metrics();$('version').textContent='r'+n+' · '+rr.state;
 protectedLayer=plate=background=null;if(p.photo?.edited)plate=await image(assetUrl(p.photo.edited));foreground=p.photo?.foreground?await image(assetUrl(p.photo.foreground)):null;if(p.photo?.background){background=await image(assetUrl(p.photo.background));for(const id of ['cx','cy','scale'])$(id).value=p.photo[id]??$(id).value}
 if(modelLoaded&&modelLoaded!==p.model?.key){resetModel();modelLoaded=null}
 if(p.model?.key){const k=p.model.key,src=k==='sample'?'building01_facade_clean.glb':assetUrl(k);await showModel(await (await fetch(src)).arrayBuffer(),p.model.name,k)}
 status('保存版を読み込みました');await history()
}
handle('save',async()=>{read();p.camera=getCamera()||p.camera||null;await ensureProject();const s=await call('save',{pid,expectedRevision:head,spec:p});opened=head=s.n;dirty=false;await calc();$('version').textContent='r'+opened+' · draft';await history();status('r'+opened+' を保存しました')});
handle('projectList',async()=>{const list=await call('projects'),el=node('select');selectOptions(el,[['','＋ 新規案件'],...list.map(v=>[v.id,v.name+' · r'+v.head])]);if(await modal('案件を開く',el)){if(!el.value)return actualProject();resetModel();modelLoaded=null;pid=el.value||null;faceIndex=opened=head=0;
 if(pid){await history();head=record.project.head;if(head){await openRev(head);return}}p=example();undo=[];refImg=plate=protectedLayer=background=null;fields();mark();await calc();await history()}});
function chosen(){const n=Number($('revSelect')?.value||opened);if(!pid||!n)throw Error('先に版を保存してください');return n}
handle('submit',async()=>{await call('review',{pid,n:chosen(),state:'review'});await history();status('照査に回しました')});
handle('approve',async()=>{
 const owner=pid,n=chosen(),rr=await call('revision?pid='+owner+'&n='+n),spec=rr.spec,result=rr.result;
 const div=node('div');div.append(node('p',spec.name+' ／ '+(spec.drawingSource||'図番未記入')+' ／ r'+n+' ／ '+rr.state),node('p','結果 '+result.resultId+' ／ '+spec.rules));
 const table=node('table');table.className='master-table';
 for(const [i,row] of [['立面','原板数','純面積 m²','アクセント %'],...result.faces.map(f=>[f.face,f.panels,(Object.values(f.finishes).reduce((a,b)=>a+b,0)/1e6).toFixed(2),f.ratio.toFixed(2)])].entries()){
  const tr=table.insertRow();for(const item of row)tr.append(node(i?'td':'th',item))
 }
 div.append(table,node('p','ルール／カタログ／景観の承認版：'+['rules','catalog','landscape'].map(k=>spec.policyRefs?.[k]||'未適用').join(' ／ ')));
 if(result.issues.length)div.append(node('p',result.issues.join(' ／ ')));
 const evidence=field(div,'照合した図面、例外と判断根拠','');
 if(!await modal('保存版 r'+n+' の設計照査',div,'承認を記録'))return;
 if(owner!==pid)throw Error('案件が切り替わりました');
 await call('review',{pid:owner,n,state:'approved',evidence:evidence.value});await history();status('r'+n+' の承認を記録しました')
});
handle('compare',async()=>{await calc();const rr=await call('revision?pid='+pid+'&n='+chosen()),old=new Map(rr.result.pieces.map(a=>[a.id,a])),curr=new Map(r.pieces.map(a=>[a.id,a]));let add=0,del=0,change=0;
 for(const [k,v] of curr){if(!old.has(k))add++;else if(JSON.stringify(v)!==JSON.stringify(old.get(k)))change++}for(const k of old.keys())if(!curr.has(k))del++;
 $('diff').textContent='追加 '+add+' / 削除 '+del+' / 変更 '+change+' 図形片\n'+r.faces.map(f=>f.face+'　'+(rr.result.faces.find(v=>v.face===f.face)?.ratio||0).toFixed(2)+'% → '+f.ratio.toFixed(2)+'%').join('\n')});
document.querySelectorAll('[data-export]').forEach(b=>b.onclick=async()=>{try{const n=chosen(),kind=b.dataset.export;let args={};
 if(dirty && !await modal('保存版 r'+n+' を出力',node('p','画面に未保存の変更があります。編集内容はこの出力には入りません。最新案を出す場合は閉じて版を保存してください。'),'r'+n+' で続行'))return;
 if(kind==='cg'){const t=node('input'),d=node('input'),msg=node('textarea'),div=node('div');t.placeholder='制作チーム';d.type='date';msg.placeholder='用途・色空間・撮影条件・納品仕様';div.append(t,d,msg);const rev=await call('revision?pid='+pid+'&n='+n);const allowed=[];for(const id of rev.spec.assets||[]){const l=node('label'),check=node('input');check.type='checkbox';l.append(check,document.createTextNode(record.files.find(f=>f.id===id)?.name||id));div.append(l);allowed.push([id,check])}const consent=node('label',' 宛先・選択素材の利用条件を確認しました'),ack=node('input');ack.type='checkbox';consent.prepend(ack);div.append(consent);if(!await modal('r'+n+' の8K制作を依頼',div,'発注'))return;if(!ack.checked)throw Error('委託条件を確認してください');args={team:t.value,due:d.value,brief:msg.value,assets:allowed.filter(a=>a[1].checked).map(a=>a[0]),rightsConfirmed:true}}
 if(p.intentPlanVersion&&$('exportScope').value==='approved')args.approvedOnly=true;
 const job=await call('job',{pid,n,kind,args});status('受付 '+job.id+' · r'+n);
 for(let i=0;i<40;i++){await new Promise(ok=>setTimeout(ok,300));await history();const j=record.jobs.find(x=>x.id===job.id);if(j&&!['queued','running'].includes(j.status))break}
 }catch(e){status(e.message)}});
handle('refresh',history);handle('member',()=>editText('登録済みユーザー名','',async name=>{await call('member',{pid,name});await history()}));
async function init(){
 const me=await call('me');if(!me.user){const div=node('div'),u=node('input'),pw=node('input');pw.type='password';u.placeholder='ユーザー名';pw.placeholder='パスワード';div.append(u,pw);if(!await modal('ログイン',div))throw Error('再読み込みでログインできます');await call('login',{name:u.value,password:pw.value});return init()}
 user=me.user;if(me.team){document.querySelector('header div').append(button('ログアウト',async()=>{await call('logout',{});location.reload()}))}fields();await calc();
}
init().catch(e=>status(e.message));
const managePolicy=button('基準・カタログ版の管理',async()=>{
 const rows=await call('policies'),div=node('div');
 const sel=node('select');selectOptions(sel,rows.map(x=>[x.id,x.type+' · '+JSON.parse(x.contents).version+' · '+(x.reviewer?'承認済':'照査待ち')]));
 const action=node('select');selectOptions(action,[['attach','承認版を案件へ適用'],['publish','照査して公開'],['rules','ルール案を登録'],['catalog','カタログ案を登録'],['landscape','景観条件案を登録']]);
 div.append(sel,action);if(!await modal('基準・カタログ管理',div))return;
 const selected=rows.find(x=>x.id===sel.value);
 if(action.value==='attach'){if(!selected?.reviewer)throw Error('承認済みの版を選択してください');remember();const item=JSON.parse(selected.contents);(p.policyRefs||={})[selected.type]=selected.id;
 if(selected.type==='rules')p.rules=item.bitsVersion;
 if(selected.type==='catalog'){p.catalog=item.products||{};p.prices=item.prices||{};p.approvedSamples=item.approvedSamples||{};p.priceSource=item.source;p.fabrication=item.fabrication||{}}
 if(selected.type==='landscape'){p.limit=item.limit??null;p.landscape=item;for(const f of p.faces){f.limit=item.limit??null;f.denominator=item.denominator||'net'}}
 fields();await calc();return}
 if(action.value==='publish'){if(!selected)throw Error('版を選択してください');const preview=node('div'),values=JSON.parse(selected.contents);preview.append(node('p',values.version+' ／ '+values.source+' ／ 起案者 '+selected.author),node('pre',JSON.stringify(values,null,2)));if(selected.type==='rules')patternComparison(preview,await call('patterns'));if(!await modal('公開する基準の内容を確認',preview,'根拠を記入'))return;await editText('照査・承認根拠','',async evidence=>{await call('policy',{id:selected.id,action:'publish',evidence});status('公開しました')});return}
 const master=await call('patterns'),contents=await masterForm(action.value,p,master,master.catalog,modal);
 if(contents){await call('policy',{type:action.value,contents});status('照査待ちとして登録しました')}

});
$('edit').parentElement.append(managePolicy);
const geometryButton=button('立面・連続面を設定',async()=>{
 const div=node('div'),form={};const f=p.faces[faceIndex];
 for(const [key,title,initial] of [['id','面名',f.id],['group','展開グループ',f.group||f.id],['origin','基準点 X,Y,Z mm',(f.origin||[0,0,0]).join(',')],['azimuth','平面方位 °',f.azimuth||0],['evidence','雁行投影の判断根拠',f.projectionEvidence||'']]){const l=node('label',title),i=node('input');i.value=initial;l.append(i);div.append(l);form[key]=i}
 const action=node('select');selectOptions(action,[['edit','この面を更新'],['add','新しい面を追加'],['remove','この面を削除']]);div.append(action);
 if(!await modal('立面形状・展開順（リスト順）',div))return;
 const next=clone(p);if(action.value==='remove'){if(next.faces.length===1)throw Error('最後の面は削除できません');next.faces.splice(faceIndex,1)}
 else{const q={...clone(f),id:form.id.value,group:form.group.value,origin:form.origin.value.split(',').map(Number),azimuth:+form.azimuth.value,projectionEvidence:form.evidence.value};if(action.value==='add'){q.features=[];for(const k of ['mesh','surfaceTriangles','reference','outline'])delete q[k];next.faces.push(q)}else next.faces[faceIndex]=q}
 await call('solve',{spec:next,pid});remember();p=next;faceIndex=Math.min(faceIndex,p.faces.length-1);fields();await calc()
});$('face').parentElement.append(geometryButton);
const costsButton=button('単価・加工・予算条件',async()=>{
 const div=node('div'),budget=field(div,'案件予算（円、未設定は空欄）',p.budget??''),source=field(div,'見積書の番号・版',p.priceSource||'');
 const rows=[];
 for(const col of Object.keys(colors)){
  const d=node('details');d.append(node('summary',col));div.append(d);
  const price=field(d,'単価（円/m²、未入力は未確定）',p.prices?.[col]??'');
  const spec=p.fabrication?.[col]||{},confirmed=field(d,'加工条件',spec.confirmed?'yes':'no',[['no','要深化'],['yes','確認済']]);
  const values={};for(const [key,title] of [['maxLength','最大素材長 mm'],['fold','片端の折返し mm'],['kerf','切断代 mm'],['wastePct','予備率 %'],['pack','梱包単位 枚']])values[key]=field(d,title,spec[key]??'');
  rows.push({col,price,confirmed,values});
 }
 if(!await modal('予算・材料見積と加工条件',div))return;
 function number(input,label){if(!input.value.trim())return null;const v=Number(input.value);if(!Number.isFinite(v)||v<0)throw Error(label+' を確認してください');return v}
 const next=clone(p);next.budget=number(budget,'予算');next.priceSource=source.value.trim();next.prices={...p.prices};next.fabrication={...p.fabrication};
 for(const row of rows){const {col,price,confirmed,values}=row;const unit=number(price,col);if(unit===null)delete next.prices[col];else next.prices[col]=unit;
  const spec={};for(const [k,i] of Object.entries(values)){const v=number(i,col);if(v!==null)spec[k]=v}
  if(confirmed.value==='yes'&&(Object.keys(spec).length!==5||!Number.isInteger(spec.pack)||spec.pack<1||spec.maxLength<=2*spec.fold+spec.kerf))throw Error(col+' の加工確認には有効な5項目が必要です');
  if(Object.keys(spec).length)next.fabrication[col]={...spec,confirmed:confirmed.value==='yes'};else delete next.fabrication[col];
 }
 await call('solve',{spec:next,pid});remember();p=next;fields();await calc()
});$('limit').parentElement.append(costsButton);
const passButton=button('CG用の視点・深度・色領域を記録',async()=>{
 await page('scene');view3();const list={};
 for(const [key,url] of [['rgba',capture(true)],['depth',capturePass('depth')],['finish',capturePass('finish')]]){
 const blob=await (await fetch(url)).blob();list[key]=await uploadFile(new File([blob],key+'.png',{type:'image/png'}))}
 if(background&&protectedLayer){await compose();const blob=await new Promise(ok=>$('composition').toBlob(ok));list.composite=await uploadFile(new File([blob],'composition.png',{type:'image/png'}))}
 p.camera=getCamera();p.passes={...list,camera:p.camera,resultId:r.resultId};mark();status('CG素材を登録しました。「版を保存」で案件版に固定します。')
});$('snap').parentElement.append(passButton);
$('bind').after(button('実モデルの面・開口を取り込む',async()=>{await page('scene');const f=p.faces[faceIndex],s=r.faces.find(s=>s.face===f.id);bindSurface(f,s.height,async(tris,name)=>{try{remember();f.surfaceTriangles=tris;f.mesh=name;await calc();status(name+' / '+tris.length+' 三角形を展開図へ反映しました')}catch(e){status(e.message)}},status)}));
const summaryButton=button('提案シートを印刷 / PDF保存',async()=>{
 await calc();const win=window.open('','_blank');if(!win)throw Error('ポップアップを許可してください');
 const doc=win.document,h=doc.createElement('h1');h.textContent=p.name;doc.body.append(h);doc.documentElement.lang='ja';
 const style=doc.createElement('style');style.textContent='body{font:16px/1.7 sans-serif;color:#173044;margin:32px}img{width:100%}section{break-inside:avoid}h1{border-bottom:3px solid #244cd0}';doc.head.append(style);
 function para(el,t){const v=doc.createElement(el);v.textContent=t;return v}
 doc.body.append(para('p',(dirty?'検討用':$('version').textContent)+' · '+r.resultId),para('p',p.aiNarrative||r.meaning));
 const prev=faceIndex;for(const [i,f] of p.faces.entries()){faceIndex=i;paint();const section=doc.createElement('section'),im=doc.createElement('img');im.src=$('plan').toDataURL();section.append(para('h2',f.id+'立面'),im);const v=r.faces.find(v=>v.face===f.id);section.append(para('p','原板 '+v.panels+'　アクセント '+v.ratio.toFixed(2)+'%'));doc.body.append(section)}
 faceIndex=prev;paint();await Promise.all([...doc.images].map(i=>i.decode().catch(()=>{})));win.focus();win.print();
});
$('refresh').after(summaryButton);
$('compare').after(button('同じ方向の立面を並べて比較',async()=>{
 const rr=await call('revision?pid='+pid+'&n='+chosen());await calc();const cur=r,current=p,i=faceIndex,id=p.faces[i].id;
 const div=node('div');function stamp(text){const im=node('img');im.style.width='100%';im.src=$('plan').toDataURL();div.append(node('p',text),im)}
 try{const ix=rr.spec.faces.findIndex(f=>f.id===id);if(ix<0)throw Error('旧版にこの立面はありません');r=rr.result;p=rr.spec;faceIndex=ix;paint();stamp('r'+chosen()+' / '+id)}finally{r=cur;p=current;faceIndex=i;paint()}stamp('編集中 / '+id);await modal('立面比較',div,'確認')
}));
$('spaces').after(button('実案件の工数・費用を比較',async()=>{
 const {evaluate,annualReturn}=await import('./benchmark.js');
 if(p.intentPlanVersion){
  const div=node('div'),items=[
   ['manualHours','手作業の実働時間 h'],['systemHours','システム利用時の実働時間 h'],['hourlyRate','社内時間単価 円/h'],
   ['manualVendor','手作業時の外注費 円/件'],['systemVendor','利用時の外注費 円/件'],['running','モデル等の従量費 円/件'],
   ['investment','初期投資 円'],['projects','年間適用件数'],['fixed','年間固定運用費 円']];
  const source=field(div,'比較した案件・同じ作業の記録',p.evaluation?.source||'');
  const inputs=items.map(([key,title])=>{const input=field(div,title,p.evaluation?.[key]??'');input.type='number';input.step='any';input.min=0;return [key,input]});
  if(!await modal('実測値による年間効果',div,'試算を保存'))return;
  if(!source.value.trim()||inputs.some(([,i])=>!i.value.trim()||!i.checkValidity()))throw Error('実測値と比較元を入力してください');
  const values=Object.fromEntries(inputs.map(([key,i])=>[key,Number(i.value)]));
  if(!Number.isSafeInteger(values.projects))throw Error('年間件数は整数で入力してください');
  const result=annualReturn(values,values.projects,values.fixed);remember();p.evaluation={...values,...result,source:source.value.trim()};
  status('年間純効果 '+result.annualNet.toLocaleString()+' 円 ／ 回収年数 '+(result.years===null?'算出不可':result.years.toFixed(2)+' 年'));return;
 }
 const values=p.measurement||{manualHours:0,systemHours:0,hourlyRate:0,manualVendor:0,systemVendor:0,running:0,manualDays:0,systemDays:0,investment:0};
 await editText('実測値（時間・円・日）',JSON.stringify(values,null,2),async t=>{const v=JSON.parse(t);if(!Object.keys(values).every(k=>Number.isFinite(v[k])&&v[k]>=0))throw Error('0以上の実測値を入力してください');remember();p.measurement=v;p.roi=evaluate(v);status('削減 '+p.roi.hoursSaved+' 時間 / '+p.roi.netSaving+' 円、回収目安 '+(p.roi.breakEven??'算出不可')+' 案件')})
}));
$('bind').parentElement.append(button('正式ロゴ画像とM字幅を登録',async()=>{
 const f=p.faces[faceIndex],logos=f.features.filter(a=>a.kind==='logo');if(!logos.length)throw Error('先に展開立面でブランドロゴ範囲をドラッグしてください');
 const sel=node('select'),file=node('input'),m=node('input'),ext=node('input'),div=node('div');selectOptions(sel,logos.map((q,i)=>[i,q.text||'Marq']));file.type='file';file.accept='image/png';m.type='number';m.placeholder='M字クリアランス mm';ext.type='number';ext.placeholder='縦並びテナント銀色範囲の高さ mm';div.append(sel,file,m,ext);if(!await modal('正式ロゴ・背面寸法',div)||!file.files[0])return;
 const logo=logos[+sel.value];if(!(+m.value>0))throw Error('M字幅を入力してください');remember();logo.asset=await uploadFile(file.files[0]);logo.clearanceM=+m.value;logo.extend=+ext.value||0;await calc()
}));
$('edit').parentElement.append(button('移行元を照合・確認',async()=>{
 if(!p.importReview)throw Error('移行元確認項目はありません');
 const div=node('div');div.append(node('p',p.importReview));
 if(p.visualReference){const d=p.visualReference,c=node('canvas');c.width=d.params.cols*6;c.height=d.params.rows*6;const ctx=c.getContext('2d');d.cells.forEach((v,i)=>{ctx.fillStyle=v<0?'#eee':[d.params.base,d.params.mid,d.params.dark][v];ctx.fillRect(i%d.params.cols*6,Math.floor(i/d.params.cols)*6,6,6)});div.append(c)}
 const evidence=node('input');evidence.placeholder='照合した図面・確認者';div.append(evidence);
 if(await modal('移行元・図面を照合',div,'確認済みにする')){if(!evidence.value.trim())throw Error('照合根拠を記入してください');remember();p.migrationConfirmed=evidence.value.trim()}
}));
$('brush').after(button('構件の座標・種別を編集',async()=>{
 const f=p.faces[faceIndex];await editText(f.id+' · 構件リスト（左上原点 mm）',JSON.stringify(f.features,null,2),async t=>{const q=clone(p);q.faces[faceIndex].features=JSON.parse(t);await call('solve',{spec:q,pid});remember();p=q;fields();await calc()})
}));
const fgInput=node('input');fgInput.type='file';fgInput.accept='image/png';const fgLabel=node('label','前景遮蔽（透過PNG）');fgLabel.append(fgInput);$('background').parentElement.after(fgLabel);
fgInput.onchange=async()=>{try{const f=fgInput.files[0];if(!f)return;if(!background)throw Error('先に背景写真を指定してください');foreground=await image(await fileData(f));p.photo.foreground=await uploadFile(f);await compose()}catch(e){status(e.message)}};
const depthNote=button('機位・光源・撮影条件',()=>editText('撮影・配置条件',JSON.stringify(p.photoSurvey||{site:'',cameraHeightM:null,focalLengthMM:null,horizonY:null,vanishingPoint:[],groundControl:[],sunDirection:'',exposure:1,sourcePermission:''},null,2),async txt=>{remember();p.photoSurvey=JSON.parse(txt);status('撮影条件を記録しました')}));
fgLabel.after(depthNote);
$('approve').after(button('保存した版から案件を複製',async()=>{const oldPid=pid,n=chosen(),v=await call('revision?pid='+pid+'&n='+n);const newName=node('input');newName.value=v.spec.name+' 複製';if(!await modal('新規案件名',newName))return;
 const q=await call('fork',{pid:oldPid,n,name:newName.value});pid=q.id;await history();await openRev(1);status('素材と版を新規案件へ複製しました')}));

async function actualProject(){
 const div=node('div'),inputs={};
 for(const [key,label,v,opts] of [
  ['name','案件名',''],['source','基準図の図番・改訂',''],['x','桁行スパン（西から東、mm、カンマ区切り）','9000,9000,9000'],
  ['z','梁間スパン（南から北、mm）','9000,9000'],['floors','階高（1階から順に、mm）','6500,7100'],
  ['stock','倉庫用途','dry',[['dry','ドライ'],['cs','冷凍冷蔵']]],
  ['mode','割付方法','H',[['H','横貼・公式配列'],['V','縦貼・公式配列'],['wave','縦貼・3ステップ']]]]){
  inputs[key]=field(div,label,v,opts);
 }
 div.append(node('p','矩形の4立面を作成します。現在の編集を残す場合は先に版を保存してください。'));
 if(!await modal('基準図から新規案件を作成',div,'新規作成'))return;
 const spec=rectangularProject(example(),Object.fromEntries(Object.entries(inputs).map(([k,i])=>[k,i.value])));
 await call('solve',{spec});resetModel();modelLoaded=null;p=spec;r=null;pid=record=null;opened=head=faceIndex=0;
 refImg=background=plate=protectedLayer=foreground=outline=brushStart=null;undo=[];fields();mark();await calc();await page('elevation');await history();status('新規案件を開始しました。開口・ロゴを入力して版を保存してください')
}
$('projectList').before(button('基準図から新規',actualProject));
$('brush').after(button('構件を寸法で入力',async()=>{
 const f=p.faces[faceIndex],div=node('div'),kind=field(div,'構件','opening',[['opening','単窓・開口'],['band','1階層のみの連窓'],['stack','各階連窓・窓上端で割付調整'],['future','将来開口'],['smoke','排煙窓'],['entrance','入口'],['logo','ロゴ'],['berth','バース扉'],['equipment','設備遮蔽']]);
 const vals=['左端 X','上端 Y','幅','高さ'].map((v,i)=>field(div,v+'（立面左上基準 mm）',i<2?'0':'1000'));
 const name=field(div,'ロゴ文字／バース番号',''),corner=field(div,'ロゴ位置','center',[['center','中央・角以外'],['left','左角'],['right','右角']]);
 const remove=field(div,'操作','add',[['add','追加'],...f.features.map((v,i)=>[String(i),String(i+1)+' '+v.kind+' を削除'])]);
 if(!await modal(f.id+'立面の構件',div))return;
 const next=clone(p),target=next.faces[faceIndex];
 if(remove.value==='add'){
  const [x,y,w,h]=vals.map(v=>v.value.trim()?Number(v.value):NaN);
  if(![x,y,w,h].every(Number.isFinite)||w<=0||h<=0)throw Error('座標と正の幅・高さを入力してください');
  const feat={kind:kind.value==='stack'?'band':kind.value,poly:box(x,y,w,h)};
  if(feat.kind==='band')feat.shift=kind.value==='stack';
  if(feat.kind==='logo'){feat.corner=corner.value==='center'?false:corner.value;feat.text=name.value.trim()||'Marq'}
  if(feat.kind==='berth'){if(!/^\d{1,3}$/.test(name.value)||Number(name.value)<1)throw Error('バース番号は1〜999');feat.number=Number(name.value)}
  target.features.push(feat);
 }else target.features.splice(Number(remove.value),1);
 await call('solve',{spec:next,pid});remember();p=next;fields();await calc()
}));
$('wave').after(button('余白・領域別の波形',async()=>{
 const div=node('div'),choices=[['','指定なし'],...[...$('wave').options].map(o=>[o.value,o.text])];
 const boxes=Array.from({length:4},(_,i)=>field(div,'アクセント領域 '+(i+1),p.waveSequence?.[i]||'',choices));
 const blank=field(div,'余白モジュール列（展開の開始側から1始まり、空欄で自動）',(p.blankCols||[]).map(j=>j+1).join(','));
 if(!await modal('縦貼り3ステップ｜別冊 P.31–33',div))return;
 const next=clone(p);next.mode='wave';next.waveSequence=boxes.map(i=>i.value).filter(Boolean);
 if(blank.value.trim())next.blankCols=blank.value.split(/[,、，]/).map(v=>Number(v)-1);else delete next.blankCols;
 await call('solve',{spec:next,pid});remember();p=next;fields();await calc()
}));

$('rules').parentElement.after(button('A/B/C 位図・公式配列を照合',async()=>{const div=node('div');patternComparison(div,await call('patterns'));await modal('主指南 P.18・20 と提案書の照合',div,'閉じる')}));
