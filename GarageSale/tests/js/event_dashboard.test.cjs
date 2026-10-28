/** Dependency-free checks for the generic renderer, without a browser framework. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {categoryChart,graph,mount,fmt,tableHtml,layoutMarkers,metricAtDate,dateAt} = require('../../static/GarageSale/js/event_dashboard.js');

function metric(extra={}) {
    return {id:'arbitrary-query',label:'Custom query',colour:'#123456',countLabel:'records',unit:'',precision:0,
        days:9,total:12,finalAverage:15,finalMaximum:20,comparableAverage:8,differencePercent:50,
        start:'2030-01-01',finalSample:3,comparableSample:3,description:'Custom data',warnings:[],historicalWarnings:[],
        cumulative:[{day:0,current:0,average:0,maximum:0},{day:9,current:12,average:8,maximum:10}],
        weekly:[{day:0,fromDay:null,current:0,average:0,maximum:0,partial:false},
            {day:9,fromDay:7,current:2,average:0,maximum:0,partial:true}],...extra};
}

function fakeDocument() {
    const nodes = new Map();
    const element = () => ({innerHTML:'',textContent:'',attrs:{},handlers:{},
        setAttribute(key,value){this.attrs[key]=value;},addEventListener(key,value){this.handlers[key]=value;},
        appendChild(child){nodes.set(child.id,child);},insertAdjacentHTML(_,html){this.innerHTML+=html;}});
    return {nodes,createElement:element,getElementById(id){
        if (!nodes.has(id)) nodes.set(id,element());
        return nodes.get(id);
    }};
}

test('arbitrary fifth metric renders and selects both chart modes',()=>{
    const document = fakeDocument();
    const metrics = Array.from({length:5},(_,i)=>metric({id:'query-'+i,label:'Query '+i}));
    mount(document,{metrics});
    document.nodes.get('dashboard-metric-4').handlers.click();
    assert.equal(document.nodes.get('dashboard-chart-title').textContent,'Query 4');
    document.nodes.get('dashboard-weekly').handlers.click();
    assert.match(document.nodes.get('dashboard-chart-data').innerHTML,/8–9 \(partial\)/);
    assert.equal(document.nodes.get('dashboard-metric-4').attrs['aria-pressed'],'true');
});

test('scales circles correctly for zero and new records without invalid geometry',()=>{
    for (const total of [0,10,20,40]) {
        const svg = categoryChart(metric({total}));
        assert.match(svg,new RegExp('Full circle: '+Math.max(total,20)));
        assert.doesNotMatch(svg,/NaN|Infinity|undefined/);
    }
    assert.doesNotMatch(categoryChart(metric({total:0,finalMaximum:0})),/NaN|Infinity/);
});

test('unknown benchmarks are omitted and unknown totals are not coerced to zero',()=>{
    const m = metric({total:null,finalAverage:null,finalMaximum:null,comparableAverage:null});
    assert.match(categoryChart(m),/Unavailable/);
    assert.doesNotMatch(categoryChart(m),/Previous maximum/);
    assert.doesNotMatch(graph(m,[]),/NaN|Infinity/);
});

test('cash keeps pence and labels cannot inject HTML or SVG',()=>{
    const m = metric({unit:'£',precision:2,label:'<script>alert(1)</script>',countLabel:'<img onerror="bad">'});
    assert.equal(fmt(m,12.34),'£12.34');
    assert.doesNotMatch(categoryChart(m),/<img/);
    assert.doesNotMatch(graph(m,m.cumulative),/<script>/);
    assert.match(tableHtml(m,m.weekly,'weekly'),/8–9 \(partial\)/);
});

/** Minimum distance of a leader segment from the circle's centre. */
function segmentRadius(a, b) {
    const dx=b[0]-a[0], dy=b[1]-a[1];
    const length=dx*dx+dy*dy;
    const fraction=length ? ((150-a[0])*dx+(151-a[1])*dy)/length : 0;
    const t=Math.max(0,Math.min(1,fraction));
    return Math.hypot(a[0]+t*dx-150,a[1]+t*dy-151);
}

test('callout leaders stay outside the ring for all benchmark quadrants',()=>{
    // Include coincident markers, zero values and both sides of every quadrant.
    for (const average of [0,1,24,25,26,49,50,51,74,75,76,99,100]) {
        for (const comparable of [0,1,25,50,75,99,100]) {
            const svg=categoryChart(metric({total:100,finalMaximum:100,
                finalAverage:average,comparableAverage:comparable}));
            const paths=[...svg.matchAll(/<polyline points="([^"]+)"/g)];
            assert.equal(paths.length,3);
            paths.forEach(path=>{
                const points=path[1].split(' ').map(pair=>pair.split(',').map(Number));
                points.slice(1).forEach((point,index)=>{
                    assert.ok(segmentRadius(points[index],point)>=94-1e-9);
                });
            });
        }
    }
});

test('clustered benchmark labels have separate ordered slots in each outer band',()=>{
    const markers=layoutMarkers(metric({total:100,finalMaximum:100,
        finalAverage:99,comparableAverage:98}),100);
    // Almost equal totals must remain readable rather than stacking at noon.
    [16,276].forEach(labelY=>{
        const band=markers.filter(marker=>marker.labelY===labelY).sort((a,b)=>a.outer[0]-b.outer[0]);
        band.slice(1).forEach((marker,index)=>{
            assert.ok(marker.x-band[index].x>=100);
        });
    });
});

/** Dense server-shaped rows include partial-week benchmarks for every date. */
function replayMetric(extra={}) {
    const cumulative=Array.from({length:10},(_,day)=>({day,current:day*2,average:day,maximum:day+1}));
    const weeklyToDate=cumulative.map(row=>({...row,fromDay:row.day?0:null,partial:row.day%7!==0,maximum:99}));
    return metric({total:18,cumulative,weeklyToDate,weekly:[weeklyToDate[0],weeklyToDate[7],weeklyToDate[9]],...extra});
}

test('replay slices totals and uses preloaded partial-week maxima without mutating data',()=>{
    const source=replayMetric(), snapshot=metricAtDate(source,'2030-01-06');
    assert.equal(snapshot.total,10);
    assert.equal(snapshot.comparableAverage,5);
    assert.equal(snapshot.differencePercent,100);
    assert.equal(snapshot.cumulative.length,6);
    assert.equal(snapshot.weekly.at(-1).maximum,99);
    assert.equal(source.total,18);
    assert.equal(source.cumulative.length,10);
});

test('one calendar date respects different openings and unknown historical dates',()=>{
    const early=metricAtDate(replayMetric(),'2030-01-04');
    const later=metricAtDate(replayMetric({start:'2030-01-05'}),'2030-01-04');
    const unknown=metricAtDate(replayMetric({cumulative:[],weekly:[]}), '2030-01-04');
    assert.equal(early.total,6);
    assert.equal(later.total,0);
    assert.equal(later.comparableAverage,null);
    assert.deepEqual(later.weekly,[]);
    assert.equal(unknown.total,null);
    assert.equal(dateAt('2030-03-30',2),'2030-04-01');
});

test('slider and day buttons update every category locally and retain metric selection',()=>{
    const document=fakeDocument(), source=replayMetric();
    mount(document,{metrics:[source,replayMetric({label:'Later metric',start:'2030-01-04'})],
        timeline:{start:'2030-01-01',end:'2030-01-10'}});
    const slider=document.nodes.get('dashboard-replay-day');
    slider.value='5';slider.handlers.input();
    assert.match(document.nodes.get('dashboard-metric-0').innerHTML,/>10<\/text>/);
    assert.match(document.nodes.get('dashboard-metric-1').innerHTML,/>4<\/text>/);
    document.nodes.get('dashboard-metric-1').handlers.click();
    document.nodes.get('dashboard-weekly').handlers.click();
    assert.equal(document.nodes.get('dashboard-chart-title').textContent,'Later metric');
    assert.match(document.nodes.get('dashboard-chart-data').innerHTML,/partial/);
    document.nodes.get('dashboard-replay-end').handlers.click();
    assert.equal(slider.value,'9');
    assert.equal(document.nodes.get('dashboard-replay-next').disabled,true);
    document.nodes.get('dashboard-replay-previous').handlers.click();
    assert.equal(slider.value,'8');
    slider.value='0';slider.handlers.input();
    assert.equal(document.nodes.get('dashboard-replay-previous').disabled,true);
    assert.equal(source.total,18);
});
