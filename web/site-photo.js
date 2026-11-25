// Register the photo, geometry, depth and editing mask in the same image space.
export function surface(w,h){
 const c=document.createElement('canvas');c.width=w;c.height=h;return c;
}
export function siteSize(photo){
 const scale=1440/Math.max(photo.width,photo.height);
 return [Math.max(1,Math.round(photo.width*scale)),Math.max(1,Math.round(photo.height*scale))];
}
export function placement(w,h,layer,controls){
 const k=Math.min(w/layer.width,h/layer.height)*controls.scale/100;
 const width=layer.width*k,height=layer.height*k;
 return [(w-width)/2+w*controls.cx/100,(h-height)/2+h*controls.cy/100,width,height];
}
export function controlsForEdit(photo,building,depth,foreground,controls){
 const [w,h]=siteSize(photo),pos=placement(w,h,building,controls);
 const k=Math.min(1536/w,1024/h),width=Math.round(w*k),height=Math.round(h*k);
 const crop=[Math.floor((1536-width)/2),Math.floor((1024-height)/2),width,height];
 function plane(){
  const c=surface(1536,1024),ctx=c.getContext('2d');
  ctx.translate(crop[0],crop[1]);ctx.scale(width/w,height/h);
  ctx.beginPath();ctx.rect(0,0,w,h);ctx.clip();return ctx;
 }
 const base=plane(),scene=plane(),mask=plane(),z=plane();
 base.drawImage(photo,0,0,w,h);scene.drawImage(photo,0,0,w,h);
 scene.drawImage(building,...pos);mask.drawImage(building,...pos);z.drawImage(depth,...pos);
 if(!mask.getImageData(0,0,1536,1024).data.some((v,i)=>i%4===3&&v>0))throw Error('建物を写真内に配置してください');
 if(foreground){scene.drawImage(foreground,0,0,w,h);mask.drawImage(foreground,0,0,w,h)}
 return {crop,w,h,pos,payload:{background:base.canvas.toDataURL(),composite:scene.canvas.toDataURL(),depth:z.canvas.toDataURL(),mask:mask.canvas.toDataURL()}};
}
export function finishEdit(edited,controls,building,foreground){
 if(edited.width!==1536||edited.height!==1024)throw Error('AI応答の画像寸法が指定と異なります');
 const {w,h,crop,pos}=controls,canvas=surface(w,h),ctx=canvas.getContext('2d');
 ctx.drawImage(edited,...crop,0,0,w,h);
 ctx.drawImage(building,...pos);
 if(foreground)ctx.drawImage(foreground,0,0,w,h);
 return canvas;
}

// Coordinates are measured in the saved composition, after the same crop and placement as the building.
export function checkpointResidual(worldToLayer,worldMM,pixel,w,h,layer,settings){
 if(!worldMM.every(Number.isFinite)||!pixel.every(Number.isFinite)||pixel[0]<0||pixel[0]>=w||pixel[1]<0||pixel[1]>=h)
  throw Error('世界座標 mm と画面内の画像座標 px を確認してください');
 const [u,v]=worldToLayer(worldMM),[left,top,width,height]=placement(w,h,layer,settings);
 const predicted=[left+u*width,top+v*height];
 return {worldMM,pixel,predicted,errorPX:Math.hypot(predicted[0]-pixel[0],predicted[1]-pixel[1])};
}

export function verifyProtected(canvas,controls,building,foreground){
 const {w,h,pos}=controls,protectedLayer=surface(w,h),ctx=protectedLayer.getContext('2d');
 ctx.drawImage(building,...pos);
 if(foreground)ctx.drawImage(foreground,0,0,w,h);
 const ref=ctx.getImageData(0,0,w,h).data,actual=canvas.getContext('2d').getImageData(0,0,w,h).data;
 let interior=0,edge=0;
 for(let i=0;i<ref.length;i+=4){
  if(!ref[i+3])continue;
  // Partially transparent overlays depend on the edited background. Review their boundary separately.
  if(ref[i+3]!==255){edge++;continue}
  interior++;
  if(ref[i]!==actual[i]||ref[i+1]!==actual[i+1]||ref[i+2]!==actual[i+2]||actual[i+3]!==255)
   throw Error('保護領域の画素が一致しません。設計確認図をご利用ください');
 }
 if(!interior)throw Error('検査できる保護領域がありません');
 return {interior,edge};
}
