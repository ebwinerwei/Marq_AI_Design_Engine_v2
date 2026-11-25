const { chromium } = require('playwright');
const fs = require('node:fs');
const [port,dir] = process.argv.slice(2);
if(!/^\d+$/.test(port)||!dir)throw Error('Usage: node orbit.cjs PORT OUTPUT_DIRECTORY');
(async () => {
 const browser = await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
 try{
 const page = await browser.newPage({viewport:{width:1440,height:960},deviceScaleFactor:1});
 await page.goto('http://127.0.0.1:'+port);
 await page.waitForSelector('#metric strong');
 await page.click('[data-view=scene]');
 await page.waitForSelector('#viewport canvas');
 await page.locator('#viewport').scrollIntoViewIfNeeded();
 fs.mkdirSync(dir,{recursive:true});
 const stats=await page.evaluate(async()=>{const view=await import('/view.js');return {camera:view.getCamera(),userAgent:navigator.userAgent,webgl:!!document.querySelector('#viewport canvas').getContext('webgl2')}});
 console.log(stats);
 for(let i=0;i<24;i++){
  const image=await page.evaluate(async({i,initial})=>{const view=await import('/view.js'),angle=i*Math.PI/12,d=(i<18?68:68-3*(i-17)),t=initial.target;
   view.setCamera({target:t,position:[t[0]+Math.sin(angle)*d,t[1]+20,t[2]+Math.cos(angle)*d]});
   return view.capture();
  },{i,initial:stats.camera});
  fs.writeFileSync(dir+'/'+String(i).padStart(2,'0')+'.png',Buffer.from(image.split(',')[1],'base64'));
 }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
