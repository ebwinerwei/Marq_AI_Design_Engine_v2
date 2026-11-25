import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
// Load the browser ES module without imposing a package.json on the workbench.
const src=await readFile(new URL('../web/project-forms.js',import.meta.url),'utf8');
const {rectangularProject}=await import('data:text/javascript;base64,'+Buffer.from(src).toString('base64'));
const data={name:'実案件',source:'A-012 Rev.2',x:'6000,7500,8000',z:'5000,7000',floors:'6500,8000',stock:'cs',mode:'V'};
const p=rectangularProject({faces:[{features:[{kind:'logo'}]}]},data);
assert.deepEqual(p.faces.map(f=>f.origin),[[0,0,0],[21500,0,0],[21500,0,-12000],[0,0,-12000]]);
assert.deepEqual(p.faces[2].spans,[8000,7500,6000]);assert.deepEqual(p.faces[3].spans,[7000,5000]);
assert.ok(p.faces.every(f=>!f.features.length));
assert.throws(()=>rectangularProject({}, {...data,x:'9000,'}));
console.log('PASS 図番・異跨4面・新規案件');
