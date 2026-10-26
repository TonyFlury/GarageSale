import {spawn} from 'node:child_process';
import {mkdtemp, readFile, writeFile, mkdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const folder=fileURLToPath(new URL('.',import.meta.url));
const profile=await mkdtemp(join(tmpdir(),'sponsor-wall-qa-'));
const chrome=spawn('google-chrome',['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
let socket;
try {
 let port;
 for(let i=0;i<80;i++) {try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await new Promise(r=>setTimeout(r,100));}}
 if(!port) throw Error('Chrome did not start');
 const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 socket=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
 let id=0;const pending=new Map();
 socket.onmessage=event=>{const msg=JSON.parse(event.data);if(msg.id){const call=pending.get(msg.id);pending.delete(msg.id);msg.error?call.reject(Error(msg.error.message)):call.resolve(msg.result);}};
 const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
 const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
 await send('Page.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1600,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:new URL('index.html',import.meta.url).href});
 for(let i=0;i<50;i++){if(await evaluate('document.querySelectorAll(".logo-tile").length===18 && [...document.images].filter(i=>i.closest("#wall")).every(i=>i.complete && i.naturalWidth>0)'))break;await new Promise(r=>setTimeout(r,100));}
 async function validate(expected) {
  const result=await evaluate(`(() => {const tiles=[...document.querySelectorAll('.logo-tile')];const rects=tiles.map(t=>t.getBoundingClientRect());let overlap=false;for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++){const a=rects[i],b=rects[j];if(Math.min(a.right,b.right)>Math.max(a.left,b.left)+1 && Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)+1)overlap=true;}return {count:tiles.length,loaded:tiles.every(t=>t.querySelector('img').naturalWidth>0),overflow:document.documentElement.scrollWidth>innerWidth,overlap,summary:document.getElementById('summary').textContent};})()`);
  if(result.count!==expected||!result.loaded||result.overflow||result.overlap)throw Error(JSON.stringify(result));
  console.log(result.summary);
 }
 console.log(await evaluate('location.href + " | " + document.title + " | " + document.body?.innerText.slice(0,180)')); await validate(18);
 await mkdir(join(folder,'previews'),{recursive:true});
 async function screenshot(name) {const metrics=await send('Page.getLayoutMetrics');const size=metrics.cssContentSize;const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:size.width,height:size.height,scale:1}});await writeFile(join(folder,'previews',name),Buffer.from(shot.data,'base64'));}
 await screenshot('desktop.png');
 for(const count of [16,20])for(const heads of [3,4]) {await evaluate(`document.getElementById('count').value='${count}';document.getElementById('headliners').value='${heads}';document.getElementById('count').dispatchEvent(new Event('change'));document.getElementById('shuffle').click();`);await validate(count);}
 await evaluate("document.querySelector('.logo-tile').click()");
 if(!await evaluate("document.getElementById('sponsor-dialog').open"))throw Error('Logo details did not open');
 await evaluate("document.getElementById('close-dialog').click(); document.getElementById('count').value='18';document.getElementById('count').dispatchEvent(new Event('change'));");
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await new Promise(r=>setTimeout(r,200));
 console.log(await evaluate('location.href + " | " + document.title + " | " + document.body?.innerText.slice(0,180)')); await validate(18);await screenshot('mobile.png');
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1600,deviceScaleFactor:1,mobile:false});
 await evaluate("document.getElementById('viewport').value='mobile';document.getElementById('viewport').dispatchEvent(new Event('change'));document.getElementById('outlines').click()");
 await new Promise(r=>setTimeout(r,100));console.log(await evaluate('location.href + " | " + document.title + " | " + document.body?.innerText.slice(0,180)')); await validate(18);
 console.log('Browser QA passed: real logo loading, controls, reshuffle, modal, desktop/mobile, no horizontal overflow.');
} finally {socket?.close();chrome.kill();await new Promise(r=>setTimeout(r,200));await rm(profile,{recursive:true,force:true}).catch(()=>{});}
