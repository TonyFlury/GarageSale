(function(root) {
'use strict';
function random(seed) { return () => {seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296;}; }
function layoutLogos(sponsors, columns, cellWidth, cellHeight, seed = 1) {
  const rng = random(seed);
  const headliners = sponsors.filter(s => s.headline).length;
  const baseArea = columns >= 10 ? 6 : columns >= 6 ? 4 : 2;
  const largeArea = baseArea * 4;
  let rows = Math.max(6, Math.ceil((headliners * largeArea + (sponsors.length - headliners) * baseArea) / columns * 1.16));
  const occupied = Array.from({length: rows}, () => Array(columns).fill(false));
  const items = sponsors.map(s => ({...s, tie: rng()})).sort((a,b) => Number(b.headline) - Number(a.headline) || a.tie - b.tie);
  const placed = [];
  let headlineIndex = 0;
  for (const item of items) {
    const area = item.headline ? largeArea : baseArea;
    const ratio = item.ratio;
    const shapes = [];
    for (let w = 1; w <= columns; w++) {
      for (let h = 1; h <= Math.ceil(area); h++) {
        const areaError = Math.abs(w*h - area) / area;
        const aspectError = Math.abs(Math.log((w*cellWidth/(h*cellHeight)) / ratio));
        if (areaError <= .35) shapes.push({w,h,penalty: areaError * 2 + aspectError});
      }
    }
    shapes.sort((a,b) => a.penalty-b.penalty);
    const candidates = shapes.slice(0,4);
    let best = null;
    while (!best) {
      for (const shape of candidates) {
        for (let y=0; y<=rows-shape.h; y++) for(let x=0; x<=columns-shape.w; x++) {
          let free = true;
          for(let yy=y; yy<y+shape.h && free; yy++) for(let xx=x; xx<x+shape.w; xx++) if(occupied[yy][xx]) {free=false;break;}
          if(!free) continue;
          const cx=x+shape.w/2, cy=y+shape.h/2;
          let tx=columns/2, ty=rows/2;
          if(item.headline && columns>=6) {
            tx += (headlineIndex%2 ? 1 : -1)*columns/4;
            ty += (Math.floor(headlineIndex/2)%2 ? 1 : -1)*2;
          }
          const distance = ((cx-tx)/columns)**2 + ((cy-ty)/rows)**2;
          const score = shape.penalty*.15 + distance*(item.headline ? 4 : 2) + rng()*.018;
          if(!best || score<best.score) best={...item,...shape,x,y,score};
        }
      }
      if(!best) {occupied.push(Array(columns).fill(false));rows++;}
    }
    for(let yy=best.y; yy<best.y+best.h; yy++) for(let xx=best.x; xx<best.x+best.w; xx++) occupied[yy][xx]=true;
    placed.push(best);
    if(item.headline) headlineIndex++;
  }
  const minY=Math.min(...placed.map(p=>p.y));
  const maxY=Math.max(...placed.map(p=>p.y+p.h));
  return {columns,rows:maxY-minY,items:placed.map(p=>({...p,y:p.y-minY}))};
}
root.layoutLogos=layoutLogos;
if(typeof module!=='undefined') module.exports={layoutLogos};
})(typeof window!=='undefined'?window:globalThis);
