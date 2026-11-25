function dimensions(text,label){
 const items=text.trim().split(/[、,，]/).map(Number);
 if(items.some(n=>!Number.isFinite(n)||n<=0||n>1e7))throw Error(label+'を正のmm値で入力してください');
 return items;
}
export function rectangularProject(base,data){
 if(!data.name.trim()||!data.source.trim())throw Error('案件名と基準図の図番・改訂を入力してください');
 const x=dimensions(data.x,'桁行スパン'),z=dimensions(data.z,'梁間スパン');
 const floors=dimensions(data.floors,'階高（下階から）');
 const w=x.reduce((a,b)=>a+b,0),d=z.reduce((a,b)=>a+b,0);
 // Lengths are entered from southwest towards east and north respectively.
 const faces=[['南',x,[0,0,0],0],['東',z,[w,0,0],-90],['北',[...x].reverse(),[w,0,-d],180],['西',[...z].reverse(),[0,0,-d],90]];
 return {...base,name:data.name.trim(),drawingSource:data.source.trim(),floors,stock:data.stock,mode:data.mode,
  faces:faces.map(([id,spans,origin,azimuth])=>({id,spans,origin,azimuth,features:[]}))};
}
export function field(parent,title,value,options){
 const label=document.createElement('label'),input=document.createElement(options?'select':'input');
 label.textContent=title;if(options)for(const [v,t] of options)input.add(new Option(t,v));
 input.value=value;label.append(input);parent.append(label);return input;
}
