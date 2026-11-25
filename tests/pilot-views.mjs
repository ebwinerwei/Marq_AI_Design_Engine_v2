import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

async function browserModule(path){
 const js=await readFile(new URL(path,import.meta.url),'utf8');
 return import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
}
const {checkpointResidual}=await browserModule('../web/site-photo.js');
const {annualReturn}=await browserModule('../web/benchmark.js');

const camera=([x,y,z])=>[.5+x/z,.5-y/z],layer={width:400,height:200},pos={scale:100,cx:0,cy:0};
assert.equal(checkpointResidual(camera,[100,50,1000],[480,180],800,400,layer,pos).errorPX,0);
assert.equal(checkpointResidual(camera,[100,50,1000],[483,184],800,400,layer,pos).errorPX,5);
assert.equal(checkpointResidual(camera,[100,50,1000],[240,90],400,200,layer,pos).errorPX,0);
const m={manualHours:20,systemHours:10,hourlyRate:2000,manualVendor:5000,systemVendor:3000,running:2000,investment:100000};
assert.deepEqual(annualReturn(m,10,100000),{perProject:20000,annualNet:100000,years:1});
assert.equal(annualReturn(m,5,100000).years,null);
assert.equal(annualReturn(m,4,100000).years,null);
console.log('PASS 合成対応点・独立誤差・画幅変更・年間費用');
