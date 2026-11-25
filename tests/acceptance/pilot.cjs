const {chromium}=require('playwright');
const port=process.argv[2];
if(!/^\d+$/.test(port))throw Error('Usage: node pilot.cjs TEST_PORT');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+port);
 await page.waitForSelector('#metric strong');
 await page.selectOption('#mode','wave');await page.selectOption('#face','1');
 await page.locator('summary').filter({hasText:'ルールと設計条件'}).click();
 await page.check('#intentPilot');
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('計算済み'));
 await page.click('#save');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('r1 を保存'));
 await page.click('#planIntent');await page.waitForSelector('dialog[open]');
 await page.locator('dialog input[type=checkbox]').first().check();
 await page.click('#confirm');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('意図案を計算'));
 console.log(await page.locator('#planFacts').textContent());
 await page.click('#save');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('r2 を保存'));
 await page.click('[data-view=scene]');await page.waitForSelector('#viewport canvas');
 await page.click('[data-view=review]');await page.click('[data-export=xlsx]');
 await page.waitForFunction(()=>document.querySelector('#jobs').textContent.includes('r2 · ready'));
 const pixels=await page.evaluate(async()=>{
  const {surface,verifyProtected,finishEdit}=await import('/site-photo.js');
  const controls={w:40,h:20,pos:[2,2,10,10],crop:[0,0,1536,1024]};
  const building=surface(10,10),ctx=building.getContext('2d');ctx.fillStyle='#657990';ctx.fillRect(0,0,10,10);
  const fg=surface(40,20),tree=fg.getContext('2d');tree.fillStyle='#173c36';tree.fillRect(6,2,3,12);
  const edited=surface(1536,1024),env=edited.getContext('2d');env.fillStyle='#ffeecc';env.fillRect(0,0,1536,1024);
  const output=finishEdit(edited,controls,building,fg),report=verifyProtected(output,controls,building,fg);
  output.getContext('2d').clearRect(7,5,1,1);let detected=false;
  try{verifyProtected(output,controls,building,fg)}catch{detected=true}
  if(!detected||report.interior!==106)throw Error('pixel mismatch QA '+JSON.stringify(report));
  return report;
 });
 console.log(pixels,await page.locator('#jobs').textContent(),errors);if(errors.length)throw Error(errors.join(','));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
