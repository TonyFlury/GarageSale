'use strict';
const logoData = [
  ['google','Google',512,168],['microsoft','Microsoft',512,110],['ibm','IBM',512,205],['airbnb','Airbnb',512,161],
  ['spotify','Spotify',512,160],['github','GitHub',512,139],['adobe','Adobe',512,134],['paypal','PayPal',256,302],
  ['slack','Slack',512,130],['zoom','Zoom',512,117],['dropbox','Dropbox',256,218],['atlassian','Atlassian',256,256],
  ['docker','Docker',512,131],['firefox','Firefox',256,265],['opera','Opera',256,256],['safari','Safari',256,256],
  ['chrome','Chrome',256,256],['mailchimp','Mailchimp',512,137],['wordpress','WordPress',512,117],['apple','Apple',256,315]
].map(([id,name,w,h])=>({id,name,ratio:w/h}));
const wall=document.getElementById('wall'), preview=document.getElementById('preview');
const count=document.getElementById('count'), headliners=document.getElementById('headliners');
const viewport=document.getElementById('viewport'), outlines=document.getElementById('outlines');
const dialog=document.getElementById('sponsor-dialog');
let seed=4821, currentLayout, previousWidth=0;
function render() {
  preview.classList.toggle('mobile',viewport.value==='mobile');
  const width=wall.clientWidth;
  const columns=width<450?4:width<750?8:12;
  const cellWidth=(width-(columns-1)*6)/columns;
  const cellHeight=columns===4?42:32;
  const sponsors=logoData.slice(0,Number(count.value)).map((s,i)=>({...s,headline:i<Number(headliners.value)}));
  const start=performance.now();
  currentLayout=layoutLogos(sponsors,columns,cellWidth,cellHeight,seed);
  const elapsed=performance.now()-start;
  wall.style.gridTemplateColumns=`repeat(${columns},minmax(0,1fr))`;
  wall.style.gridTemplateRows=`repeat(${currentLayout.rows},${cellHeight}px)`;
  wall.classList.toggle('outlines',outlines.checked);
  wall.replaceChildren();
  // Keep reading and keyboard order independent of geometric placement.
  for(const sponsor of sponsors) {
    const p=currentLayout.items.find(p=>p.id===sponsor.id);
    const tile=document.createElement('button');
    tile.type='button';tile.className='logo-tile'+(p.headline?' headline':'');
    tile.style.gridColumn=`${p.x+1} / span ${p.w}`;
    tile.style.gridRow=`${p.y+1} / span ${p.h}`;
    tile.dataset.size=`${p.headline?'Headline · ':''}${p.w} × ${p.h}`;
    tile.setAttribute('aria-label',`${p.name}${p.headline?', headline supporter':''} — example sponsor details`);
    tile.setAttribute('aria-haspopup','dialog');
    const img=document.createElement('img');img.src=`assets/${p.id}.svg`;img.alt=p.name;img.draggable=false;
    tile.append(img);
    tile.addEventListener('click',()=>{
      document.getElementById('dialog-tier').textContent=p.headline?'Headline supporter · demo':'Community supporter · demo';
      document.getElementById('dialog-name').textContent=p.name;
      document.getElementById('dialog-logo').src=img.src;
      document.getElementById('dialog-logo').alt=p.name;
      document.getElementById('dialog-source').href=`https://github.com/gilbarbara/logos/blob/main/logos/${p.id}.svg`;
      dialog.showModal();
    });
    wall.append(tile);
  }
  document.getElementById('summary').textContent=`${sponsors.length} sponsors · ${headliners.value} headliners · ${Math.round(elapsed)} ms layout`;
  previousWidth=width;
  window.prototypeLayout=currentLayout;
}
for(const control of [count,headliners,viewport]) control.addEventListener('change',render);
outlines.addEventListener('change',()=>wall.classList.toggle('outlines',outlines.checked));
document.getElementById('shuffle').addEventListener('click',()=>{seed++;render();});
document.getElementById('close-dialog').addEventListener('click',()=>dialog.close());
new ResizeObserver(()=>{if(Math.abs(wall.clientWidth-previousWidth)>1)render();}).observe(wall);
render();
