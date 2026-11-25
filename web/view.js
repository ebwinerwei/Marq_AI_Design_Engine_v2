import * as T from 'three';
import {addFacadePanels} from './facade-skin.js';
import {SoftwareRenderer} from './software-renderer.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {FBXLoader} from 'three/addons/loaders/FBXLoader.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {normalizeStaticModel} from './rendering-fixes.js';
export const colors={Silver:'#bec5cc','Slate Navy':'#607895',White:'#f8f8f5','Dark Gray':'#44433f','Electric Blue':'#0744f7','Medium Gray':'#898782',Column:'#353431'};
const target=document.querySelector('#viewport');
let renderer,camera,scene,orbit,sun,ambient,skin,model,ground,pick,modelKey,interior,first=true,last=[];
const rad=d=>d*Math.PI/180;
export function point(f,h,u,v){let a=rad(f.azimuth||0),o=f.origin||[0,0,0];return new T.Vector3((o[0]+u*Math.cos(a))/1000,(o[1]+h-v)/1000,(o[2]+u*Math.sin(a))/1000)}
function init(){
 if(renderer)return;
 try{renderer=new T.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true})}catch{renderer=new SoftwareRenderer()}renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;target.replaceChildren(renderer.domElement);
 scene=new T.Scene();camera=new T.PerspectiveCamera(40,1,.1,3000);orbit=new OrbitControls(camera,renderer.domElement);orbit.addEventListener('change',render);
 ambient=new T.HemisphereLight(0xffffff,0xb1c2cb,2.1);sun=new T.DirectionalLight(0xfff5df,2);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);
 Object.assign(sun.shadow.camera,{left:-130,right:130,top:130,bottom:-130,far:650});scene.add(ambient,sun);
 ground=new T.Mesh(new T.PlaneGeometry(1200,1200),new T.MeshStandardMaterial({color:0xd0d6d7}));ground.rotation.x=-Math.PI/2;ground.position.y=-.025;ground.receiveShadow=true;scene.add(ground);
 renderer.domElement.addEventListener('click',e=>{
  if(!pick||!model)return;
  const b=renderer.domElement.getBoundingClientRect(),ray=new T.Raycaster();ray.setFromCamera(new T.Vector2((e.clientX-b.left)/b.width*2-1,1-(e.clientY-b.top)/b.height*2),camera);
  const hit=ray.intersectObject(model,true)[0];if(hit)pick(hit);
 });
 new ResizeObserver(render).observe(target);
}
function clear(group){if(!group)return;scene.remove(group);group.traverse(m=>{m.geometry?.dispose();if(m.material){for(const v of [].concat(m.material)){v.map?.dispose();v.dispose()}}})}
function frame(group){const box=new T.Box3().setFromObject(group);if(box.isEmpty())return;const center=box.getCenter(new T.Vector3()),s=box.getSize(new T.Vector3()).length();orbit.target.copy(center);camera.position.copy(center).add(new T.Vector3(.74,.45,1).multiplyScalar(Math.max(5,s*.95)));camera.far=Math.max(3000,s*14);camera.updateProjectionMatrix();orbit.update()}
export function render(){if(!renderer||!target.clientWidth||!target.clientHeight)return;const w=target.clientWidth,h=target.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();renderer.render(scene,camera)}
function label(text,kind,f,h,poly){
 const c=document.createElement('canvas');c.width=512;c.height=160;const ctx=c.getContext('2d');ctx.fillStyle=kind==='logo'?'#f7faff':'#14191c';ctx.fillRect(0,0,512,160);ctx.fillStyle=kind==='logo'?'#143db7':'white';ctx.font='bold 100px sans-serif';ctx.textAlign='center';ctx.fillText(text,256,116,500);
 const lo=poly[0],hi=poly[2];const w=Math.abs(hi[0]-lo[0])/1000,hh=Math.abs(hi[1]-lo[1])/1000;
 const tex=new T.CanvasTexture(c);tex.colorSpace=T.SRGBColorSpace;const mesh=new T.Mesh(new T.PlaneGeometry(w,hh),new T.MeshBasicMaterial({map:tex,side:T.DoubleSide,polygonOffset:true,polygonOffsetFactor:-5}));
 mesh.position.copy(point(f,h,(lo[0]+hi[0])/2,(lo[1]+hi[1])/2-(kind==='berth'?(hi[1]-lo[1])*.6:0)));mesh.rotation.y=-rad(f.azimuth||0);if(kind==='berth')mesh.scale.y=.2;return mesh;
}
export function draw3(p,r,assetURL){
 init();clear(skin);skin=new T.Group();const faces=new Map(p.faces.map(f=>[f.id,f])),hs=new Map(r.faces.map(f=>[f.face,f.height]));
 addFacadePanels(skin,p,r,colors,renderer.capabilities.maxTextureSize||3072,renderer.capabilities.getMaxAnisotropy(),point,renderer.isSoftware);
 for(const mark of r.labels){const m=label(mark.text,mark.kind,faces.get(mark.face),hs.get(mark.face),mark.poly);skin.add(m);if(mark.asset&&assetURL)new T.TextureLoader().load(assetURL(mark.asset),t=>{t.colorSpace=T.SRGBColorSpace;m.material.map?.dispose();m.material.map=t;m.material.transparent=true;m.material.alphaTest=.4;m.material.needsUpdate=true;render()})}
 scene.add(skin);if(first){frame(skin);first=false}lighting(p.light);render();
}
export function lighting(l={}){if(!renderer)return;ambient.intensity=+(l.ambient??2.5);sun.position.set(160*Math.sin(rad(l.az??42))*Math.cos(rad(l.alt??45)),160*Math.sin(rad(l.alt??45)),160*Math.cos(rad(l.az??42))*Math.cos(rad(l.alt??45)));sun.castShadow=l.shadow!==false;sun.color.set(l.sky==='dusk'?0xffbb88:0xffffff);sun.intensity=l.sky==='night'?.5:2;renderer.setClearColor(l.sky==='night'?0x25384c:l.sky==='dusk'?0xe0c5b6:0xdce7ee,1);render()}
export async function loadModel(bytes,name,key,transform){
 init();const manager=new T.LoadingManager();manager.setURLModifier(u=>/^(data:|blob:)/.test(u)?u:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==');
 let obj=/\.fbx$/i.test(name)?new FBXLoader(manager).parse(bytes,''):(await new GLTFLoader(manager).parseAsync(bytes,'')).scene;
 let tris=0;obj.traverse(m=>{if(m.isMesh)tris+=(m.geometry.index?.count??m.geometry.attributes.position.count)/3});if(renderer.isSoftware&&tris>30000)throw Error('互換3D表示は3万三角形までです。現在の工程立面を軽量モデルとして表示します。');if(tris>500000)throw Error('50万三角形を超えています');
 const prep=normalizeStaticModel(obj);clear(model);model=new T.Group();model.add(prep.group);scene.add(model);modelKey=key;
 if(transform){model.position.fromArray(transform.position);model.rotation.y=transform.angle;model.scale.setScalar(transform.scale)}
 frame(model);render();return prep.report;
}
export function calibration(f,H,done,status){if(!model)throw Error('先に3Dモデルを読み込んでください');skin.visible=false;last=[];render();
 pick=hit=>{const pos=hit.object.geometry.attributes.position;const choices=[hit.face.a,hit.face.b,hit.face.c].map(i=>new T.Vector3().fromBufferAttribute(pos,i).applyMatrix4(hit.object.matrixWorld));choices.sort((a,b)=>a.distanceToSquared(hit.point)-b.distanceToSquared(hit.point));last.push(choices[0]);if(last.length===1){status('続いて同じ壁の右下端を選択してください');return}
 const a=last[0],b=last[1],v=b.clone().sub(a);try{
 if(Math.hypot(v.x,v.z)<.001)throw Error('異なる2点を指定してください');
 const width=f.spans.reduce((s,v)=>s+v,0)/1000,ratio=width/Math.hypot(v.x,v.z),delta=Math.atan2(v.z,v.x)-rad(f.azimuth||0);
 const dest=point(f,H,0,H);model.position.sub(a).multiplyScalar(ratio).applyAxisAngle(new T.Vector3(0,1,0),delta).add(dest);model.scale.multiplyScalar(ratio);model.rotation.y+=delta;
 done({key:modelKey,position:model.position.toArray(),angle:model.rotation.y,scale:model.scale.x});
 }finally{pick=null;skin.visible=true;render()}};status('モデル上で対象壁の左下端を選択してください')}
export function capture(transparent=false){init();if(transparent){ground.visible=false;renderer.setClearAlpha(0)}renderer.last=0;renderer.render(scene,camera);const url=renderer.domElement.toDataURL();if(transparent){ground.visible=true;renderer.setClearAlpha(1)}render();return url}
export function getCamera(){return camera?{position:camera.position.toArray(),target:orbit.target.toArray()}:null}
export function setCamera(v){if(camera&&v){camera.position.fromArray(v.position);orbit.target.fromArray(v.target);orbit.update();render()}}
export function resetModel(){if(renderer){clear(model);clear(interior);model=interior=null;pick=null;first=true}}
export function capturePass(which){
 init();if(which==='siteDepth'&&(interior||pick||!skin?.visible))throw Error('全周 3D で外観表示に戻り、面の指定を完了してください');if(renderer.isSoftware)throw Error('深度・IDパスはWebGL対応端末で出力してください');const originals=[],was=renderer.getClearColor(new T.Color()),alpha=renderer.getClearAlpha(),oldGround=ground.visible;
 ground.visible=false;renderer.setClearColor(0,0);const wasModel=model?.visible;
 if(which==='finish'&&model)model.visible=false;
 const palette=Object.fromEntries(Object.keys(colors).map((n,i)=>[colors[n],i+1]));
 try{
  scene.traverse(o=>{
    if(!o.isMesh&&!o.isLineSegments)return;
    originals.push([o,o.material,o.visible]);
    if(o.isLineSegments){o.visible=false;return}
    if(which==='siteDepth'){
      const range=Math.max(1,camera.position.distanceTo(orbit.target));
      o.material=new T.ShaderMaterial({side:T.DoubleSide,uniforms:{range:{value:range}},
       vertexShader:'varying float dist; void main(){vec4 v=modelViewMatrix*vec4(position,1.0);dist=-v.z;gl_Position=projectionMatrix*v;}',
       fragmentShader:'uniform float range; varying float dist; void main(){float d=clamp(1.0-dist/(2.0*range),0.0,1.0);gl_FragColor=vec4(vec3(d),1.0);}'});
    }else if(which==='depth')o.material=new T.MeshDepthMaterial({depthPacking:T.RGBADepthPacking,side:T.DoubleSide});
    else{let name=o.material?.color?.getHexString();let id=palette[colors[o.material?.userData?.facadeFinish]||'#'+name]||20;o.material=new T.MeshBasicMaterial({color:new T.Color().setRGB(id/255,0,0,T.SRGBColorSpace),side:T.DoubleSide,toneMapped:false})}
  });
  renderer.render(scene,camera);return renderer.domElement.toDataURL()
 }finally{for(const [o,m,v] of originals){if(o.material!==m)o.material.dispose();o.material=m;o.visible=v}ground.visible=oldGround;if(model)model.visible=wasModel;renderer.setClearColor(was,alpha);render()}
}
export function bindSurface(f,H,done,status){
 if(!model)throw Error('先に校正済みモデルを開いてください');
 skin.visible=false;render();const w=f.spans.reduce((a,b)=>a+b,0);
 pick=h=>{pick=null;skin.visible=true;try{
 const a=rad(f.azimuth||0),o=point(f,H,0,H),U=new T.Vector3(Math.cos(a),0,Math.sin(a)),N=new T.Vector3(-Math.sin(a),0,Math.cos(a));
 if(Math.abs(h.point.clone().sub(o).dot(N))>.15)throw Error('選択面が登録立面から150mm以上離れています。基準2点と方位を確認してください');
 const geom=h.object.geometry,pos=geom.attributes.position,idx=geom.index,tri=[];
 for(let i=0;i<(idx?.count||pos.count);i+=3){
  const pts=[0,1,2].map(k=>new T.Vector3().fromBufferAttribute(pos,idx?idx.getX(i+k):i+k).applyMatrix4(h.object.matrixWorld).sub(o));
  if(pts.some(q=>Math.abs(q.dot(N))>.15))continue;
  const poly=pts.map(q=>[Math.round(q.dot(U)*1000),Math.round(H-q.y*1000)]);
  if(poly.every(q=>q[0]<0||q[0]>w||q[1]<0||q[1]>H))continue;
  const [l,m,n]=poly;if(Math.abs((m[0]-l[0])*(n[1]-l[1])-(n[0]-l[0])*(m[1]-l[1]))>0)tri.push(poly)
 }
 if(!tri.length||tri.length>4000)throw Error('対象三角形が0または4000超です。外壁メッシュを分割してください');
 done(tri,h.object.name);
 }catch(e){status(e.message)}finally{render()}};
 status('対応付ける外壁メッシュをクリックしてください。投影形状を材料域に使用します。')
}
export function spaceView(item){
 init();clear(interior);interior=null;if(!item){if(skin)skin.visible=true;if(model)model.visible=true;if(skin)frame(skin);render();return}
 if(skin)skin.visible=false;if(model)model.visible=false;
 interior=new T.Group();const [w,h,d]=item.dimensions.map(v=>v/1000);
 function box(size,pos,col){const m=new T.Mesh(new T.BoxGeometry(...size),new T.MeshStandardMaterial({color:col,roughness:.8}));m.position.set(...pos);m.receiveShadow=m.castShadow=true;interior.add(m)}
 box([w,.1,d],[0,0,0],item.floor);box([w,h,.12],[0,h/2,-d/2],item.wall);box([.12,h,d],[-w/2,h/2,0],item.wall);
 if(item.category==='approach'){box([w*.28,.08,d],[w*.28,.06,0],item.accent);for(let i=0;i<4;i++){const m=new T.Mesh(new T.SphereGeometry(.6,12,8),new T.MeshStandardMaterial({color:'#517753'}));m.position.set(-w*.33,1,-d*.32+i*d*.20);interior.add(m)}}
 else{box([w,.09,.08],[0,h*.64,-d/2+.1],item.accent);for(let i=0;i<3;i++)box([.12,.08,d*.65],[(i-1)*w*.28,h-.08,0],'#fff4d6')}
 scene.add(interior);frame(interior);render()
}

export function projectWorldMM(xyz){
 if(!camera)throw Error('全周3Dで確認視点を選択してください');
 const point=new T.Vector3(...xyz).multiplyScalar(.001).applyMatrix4(camera.matrixWorldInverse);
 if(point.z>=-camera.near)throw Error('基準点がカメラの背面または手前にあります');
 point.applyMatrix4(camera.projectionMatrix);
 return [(point.x+1)/2,(1-point.y)/2];
}
