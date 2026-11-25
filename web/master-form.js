import {field} from './project-forms.js';

function paragraph(parent,value){
 const el=document.createElement('p');el.textContent=value;parent.append(el);
}
function table(parent,head,rows){
 const t=document.createElement('table');t.className='master-table';
 for(const [n,row] of [head,...rows].entries()){
  const tr=t.insertRow();for(const item of row){const cell=document.createElement(n?'td':'th');cell.textContent=item;tr.append(cell)}
 }
 parent.append(t);
}
export function patternComparison(parent,rule){
 const format=bits=>bits.flatMap((v,i)=>v?[i+1]:[]).join('・')||'全て銀';
 for(const type of ['A','B','C']){
  table(parent,['モジュール','番号','2.0 基準｜アクセント位置','提案書｜アクセント位置'],
   rule.baseline[type].map((row,i)=>[type,i,format(row),format(rule.proposal[type][i])]));
 }
 paragraph(parent,'位置は1始まり。横貼は上から、縦貼は左から数えます。C4・C6は原図と照合して採用版を選択してください。');
 for(const [i,seq] of rule.sequence.entries()){
  const d=document.createElement('details'),summary=document.createElement('summary');
  summary.textContent=(i?'縦':'横')+'貼の公式配列（'+seq.length+'桁）';d.append(summary);paragraph(d,seq.match(/.{1,5}/g).join(' '));parent.append(d);
 }
}
export async function masterForm(type,p,patterns,defaults,modal){
 const div=document.createElement('div'),version=field(div,'基準版の名称',''),source=field(div,'出典（資料名・改訂・頁または照合図番）','');
 let build;
 if(type==='rules'){
  const choice=field(div,'採用する配列版',p.rules,[['p18-baseline','2.0 基準（主指南 P.18 照合用）'],['word-comparison','提案書 C4・C6 案']]);
  patternComparison(div,patterns);build=()=>({bitsVersion:choice.value,orientation:'立面正面・上から下、左から右'});
 }else if(type==='catalog'){
  const products={},prices={},refs={...defaults,...p.catalog};
  for(const col of Object.keys({...defaults,'Slate Navy':1,'Electric Blue':1,'Dark Gray':1,'Column':1,...p.catalog})){
   const d=document.createElement('details'),s=document.createElement('summary');s.textContent=col;d.append(s);div.append(d);
   const values=refs[col]||[];
   products[col]=['日鉄鋼板 横','日鉄鋼板 縦','ヨドコウ 横','ヨドコウ 縦','アイジー工業 横','アイジー工業 縦'].map((name,i)=>field(d,name+' 品番',values[i]||''));
   prices[col]=field(d,'設計概算単価（円/m²、未確認は空欄）',p.prices?.[col]??'');
  }
  build=()=>{
   const units={};for(const [k,i] of Object.entries(prices))if(i.value.trim()){const v=Number(i.value);if(!Number.isFinite(v)||v<0)throw Error(k+' の単価を確認してください');units[k]=v}
   return {products:Object.fromEntries(Object.entries(products).map(([k,row])=>[k,row.map(i=>i.value.trim()||null)])),prices:units,fabrication:p.fabrication||{},approvedSamples:p.approvedSamples||{}};
  };
 }else{
  const town=field(div,'自治体・地区名',p.landscape?.municipality||''),limit=field(div,'アクセント上限 %（規定がない場合は空欄）',p.landscape?.limit??'');
  const den=field(div,'立面ごとの面積分母',p.landscape?.denominator||'net',[['net','設計純面積'],['visible','設備遮蔽を除く可視面積']]);
  build=()=>{const value=limit.value.trim()?Number(limit.value):null;if(value!==null&&(!Number.isFinite(value)||value<0||value>100))throw Error('上限は0〜100%');return {...p.landscape,municipality:town.value,limit:value,denominator:den.value}};
 }
 if(!await modal('基準案を登録',div,'照査待ちで登録'))return;
 if(!version.value.trim()||!source.value.trim())throw Error('版名・出典を入力してください');
 return {...build(),version:version.value.trim(),source:source.value.trim()};
}
