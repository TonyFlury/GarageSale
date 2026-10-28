/**
 * Model-independent SVG dashboard renderer.
 *
 * Python supplies {metrics: [...]}, safely embedded with Django's json_script.
 * Each metric contains presentation metadata (label/unit/precision/colour),
 * totals/benchmarks, sample sizes, warnings, and cumulative/weekly chart rows.
 * A row has day/current/average/maximum; weekly rows add fromDay and partial.
 * Numbers may be null (unavailable); zero is always real measured inactivity.
 * Completed events also supply a calendar timeline and weeklyToDate rows for
 * each stopping day. Replay slices loaded data; it never fetches another snapshot.
 *
 * Campaign clocks, database queries, carry-forward and weekly aggregation belong
 * in Python. Adding a metric in the view requires no template or JS changes.
 */
(() => {
    'use strict';

    /** Escape all server-supplied labels before inserting HTML or SVG markup. */
    const escape = value => String(value).replace(/[&<>"']/g, c => ({
        '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
    }[c]));
    const known = value => typeof value === 'number' && Number.isFinite(value);
    const colour = m => /^#[a-f\d]{6}$/i.test(m.colour) ? m.colour : '#28624f';

    /** Keep currency decimals while rendering counts as whole numbers. */
    function fmt(m, n) {
        // Unknown amounts must never be displayed as zero contributions.
        if (!known(n)) return 'Unavailable';
        return (m.unit || '') + n.toLocaleString('en-GB', {
            minimumFractionDigits:m.precision || 0, maximumFractionDigits:m.precision || 0
        });
    }

    /** This percentage is relative to the elapsed-day average, not final totals. */
    function percent(n) {
        // Zero or missing historical baselines cannot define a percentage change.
        if (!known(n)) return 'Same-stage percentage unavailable';
        const rounded = Math.round(n);
        return `${rounded > 0 ? '+' : ''}${rounded}% vs same-stage average`;
    }

    /** Midday parsing avoids shifting date-only strings across time zones. */
    function date(value) {
        // Missing booking dates are a configuration issue, not January 1970.
        if (!value) return 'Unknown';
        return new Date(value + 'T12:00:00').toLocaleDateString('en-GB', {
            day:'numeric', month:'short', year:'numeric'
        });
    }

    /** Date-only arithmetic is UTC-based so daylight-saving changes stay one day. */
    const dayNumber = value=>Date.parse(value+'T00:00:00Z')/86400000;
    const dateAt = (start,offset)=>new Date((dayNumber(start)+offset)*86400000).toISOString().slice(0,10);

    /** Slice a loaded metric at a calendar date without touching its source rows. */
    function metricAtDate(m, snapshot) {
        if (m.stages) {
            const {stages,...base}=m;
            return {...metricAtDate(base,snapshot),stages:stages.map(stage=>metricAtDate(stage,snapshot))};
        }
        // Live views and categories without an opening date retain their data notes.
        if (!snapshot || !m.start) return m;
        const day = dayNumber(snapshot)-dayNumber(m.start);
        // Opening dates differ: a shared replay date may precede this category.
        if (day<0) return {...m,total:0,days:0,comparableAverage:null,differencePercent:null,
            cumulative:[],weekly:[],warnings:['Not open by the selected date.']};
        // The final position is exactly the original server-rendered snapshot.
        if (day>=m.days) return m;
        const row = m.cumulative[day];
        // Undated totals cannot honestly be reconstructed at an earlier date.
        if (!row) return {...m,total:null,days:day,comparableAverage:null,differencePercent:null};
        const weekly = m.weekly.filter(item=>item.day<=day);
        // Python supplies partial-week maxima; cumulative maxima cannot derive them.
        if (weekly.at(-1)?.day!==day) weekly.push(m.weeklyToDate[day]);
        return {...m,days:day,total:row.current,comparableAverage:row.average,
            differencePercent:known(row.average) && row.average>0 ? (row.current/row.average-1)*100 : null,
            cumulative:m.cumulative.slice(0,day+1),weekly};
    }

    /** Convert a benchmark into a clockwise position from twelve o'clock. */
    function radialPoint(value, radius, scale) {
        const angle = (scale > 0 ? value / scale : 0) * 2 * Math.PI - Math.PI / 2;
        return [150 + radius * Math.cos(angle), 151 + radius * Math.sin(angle)];
    }

    /** Assign labels to the nearest outer band and keep their left-to-right order. */
    function layoutMarkers(m, scale) {
        const markers = [
            {label:'Final average',value:m.finalAverage,dash:'3 2'},
            {label:'Maximum',value:m.finalMaximum,dash:''},
            {label:`Day ${m.days} avg`,value:m.comparableAverage,dash:'',colour:'#b44d10'}
        ].filter(marker=>known(marker.value)).map(marker=>({
            ...marker,outer:radialPoint(marker.value,104,scale)
        }));
        // Upper and lower labels never need leaders through the circle itself.
        [true,false].forEach(upper=>positionMarkerBand(markers,upper));
        return markers;
    }

    /** At most three labels share a band, with a full text slot for each. */
    function positionMarkerBand(markers, upper) {
        const band = markers.filter(marker=>(marker.outer[1]<151)===upper);
        band.sort((a,b)=>a.outer[0]-b.outer[0]);
        // Order-preserving slots prevent neighbouring callouts swapping sides.
        band.forEach((marker,index)=>{
            marker.x = band.length===1 ? Math.max(60,Math.min(240,marker.outer[0])) :
                (index+0.5)*300/band.length;
            marker.labelY = upper ? 16 : 276;
            marker.railY = upper ? 44+index*3 : 258-index*3;
            marker.endY = upper ? 44 : 258;
        });
    }

    /** Route radially out, then along an exterior rail; never cut across the pie. */
    function markerSvg(m, marker, scale) {
        const inner = radialPoint(marker.value,70,scale), outer = marker.outer;
        const ink = marker.colour || '#18372e';
        return `<line x1="${inner[0]}" y1="${inner[1]}" x2="${outer[0]}" y2="${outer[1]}" stroke="${ink}" stroke-width="${marker.colour ? 3 : 2}" stroke-dasharray="${marker.dash}"/>
            <polyline points="${outer.join(',')} ${outer[0]},${marker.railY} ${marker.x},${marker.railY} ${marker.x},${marker.endY}" fill="none" stroke="${ink}" stroke-dasharray="${marker.dash}"/>
            <text x="${marker.x}" y="${marker.labelY}" text-anchor="middle" class="gauge-label">${escape(marker.label)}</text>
            <text x="${marker.x}" y="${marker.labelY+18}" text-anchor="middle" class="gauge-benchmark">${escape(fmt(m,marker.value))}</text>`;
    }

    /** Missing benchmarks have no tick; real zero benchmarks remain visible. */
    function markersSvg(m, scale) {
        return layoutMarkers(m,scale).map(marker=>markerSvg(m,marker,scale)).join('');
    }

    /** A full circle equals max(current total, historical final maximum). */
    function categoryChart(m) {
        const stages=m.stages || [m];
        const scale = Math.max(...stages.map(stage=>stage.total || 0),m.finalMaximum || 0);
        const circumference = 2 * Math.PI * 82;
        const sectors=stages.map(stage=>{
            const proportion=scale>0 && known(stage.total) ? Math.max(0,stage.total/scale) : 0;
            return `<circle data-stage="${escape(stage.id)}" cx="150" cy="151" r="82" fill="none" stroke="${colour(stage)}" stroke-width="24" stroke-dasharray="${circumference*proportion} ${circumference}" transform="rotate(-90 150 151)"/>`;
        }).join('');
        const headline=m.stages ? m.stages.at(-1) : m;
        const valueStyle = known(headline.total) ? '' : 'font-size:18px;letter-spacing:0';
        return `<svg class="category-chart" viewBox="0 0 300 322" aria-hidden="true" focusable="false">
            <circle cx="150" cy="151" r="82" fill="none" stroke="#e9eee7" stroke-width="24"/>
            ${sectors}
            ${markersSvg(m,scale)}
            <text x="150" y="151" text-anchor="middle" class="gauge-value" fill="${colour(headline)}" style="${valueStyle}">${escape(fmt(headline,headline.total))}</text>
            <text x="150" y="174" text-anchor="middle" class="gauge-label">${escape(m.countLabel)}</text>
            <text x="150" y="318" text-anchor="middle" class="gauge-scale">Full circle: ${escape(fmt(m,scale))}</text>
        </svg>`;
    }

    /** Use a nonzero extent for opening-day and entirely empty charts. */
    function graphScale(rows) {
        const values = rows.flatMap(r=>[r.current,r.average,r.maximum]).filter(known);
        const top = values.reduce((maximum,value)=>Math.max(maximum,value),1) * 1.12;
        const lastDay = rows.at(-1)?.day || 0;
        return {top,lastDay,x:d=>88+d/Math.max(1,lastDay)*870,y:n=>260-n/top*230};
    }

    /** Draw a bounded number of axis labels, even for long campaigns. */
    function axesSvg(m, scale) {
        let svg = '';
        // Four intervals keep labels readable regardless of total magnitude.
        for (let i=0;i<=4;i++) {
            const n = m.precision ? scale.top*i/4 : Math.round(scale.top*i/4);
            svg += `<line x1="88" x2="958" y1="${scale.y(n)}" y2="${scale.y(n)}" stroke="#e4eae1"/><text x="78" y="${scale.y(n)+4}" text-anchor="end" font-size="12" fill="#63746b">${escape(fmt(m,n))}</text>`;
        }
        const ticks = new Set([0,scale.lastDay]), step = Math.max(1,Math.ceil(scale.lastDay/8));
        // Include both endpoints and roughly eight elapsed-day ticks.
        for (let day=step;day<scale.lastDay;day+=step) ticks.add(day);
        [...ticks].sort((a,b)=>a-b).forEach(day=>{
            svg += `<text x="${scale.x(day)}" y="284" text-anchor="middle" font-size="12" fill="#63746b">${day}</text>`;
        });
        return svg;
    }

    /** All daily points form the line; tooltip circles are capped around fifty. */
    function lineSvg(m, rows, scale, key, ink, dash) {
        const points = rows.filter(row=>known(row[key]));
        // No previous events produces no misleading historical zero line.
        if (!points.length) return '';
        let svg = `<polyline points="${points.map(r=>`${scale.x(r.day)},${scale.y(r[key])}`).join(' ')}" fill="none" stroke="${ink}" stroke-width="3" stroke-dasharray="${dash}"/>`;
        const every = Math.max(1,Math.ceil(points.length/50));
        points.filter((row,index)=>index%every===0 || index===points.length-1).forEach(row=>{
            svg += `<circle cx="${scale.x(row.day)}" cy="${scale.y(row[key])}" r="3" fill="${ink}"><title>Day ${row.day} · ${key==='current'?escape(m.label):key}: ${escape(fmt(m,row[key]))}</title></circle>`;
        });
        return svg;
    }

    /** Draw supplied rows without recalculating any historical comparisons. */
    function graph(m, rows, mode='cumulative') {
        const scale = graphScale(m.stages ? [...rows,...m.stages.flatMap(stage=>stage[mode])] : rows);
        const title = `<title id="dashboard-svg-title">${escape(m.label)} run rate</title><desc id="dashboard-svg-desc">Days since opening. Exact values are available in the chart data table below.</desc>`;
        const lines = [['maximum','#b2872f','5 5'],['average','#7c9382','5 5'],['current',colour(m),'']];
        const curves=m.stages ? lines.slice(0,2).map(args=>lineSvg(m,rows,scale,...args)).join('') +
            m.stages.map(stage=>lineSvg(stage,stage[mode],scale,'current',colour(stage),'')).join('') :
            lines.map(args=>lineSvg(m,rows,scale,...args)).join('');
        return title + axesSvg(m,scale) + curves +
            '<text x="520" y="314" text-anchor="middle" font-size="12" fill="#63746b">Days since opening</text>';
    }

    /** Table intervals match Python's endpoints, including partial final weeks. */
    function intervalLabel(row, mode) {
        // Cumulative rows and the separate opening-day row have no interval.
        if (mode!=='weekly' || row.fromDay===null) return row.day;
        return `${row.fromDay+1}–${row.day}${row.partial?' (partial)':''}`;
    }

    /** Accessible exact values supplement SVG geometry and mouse tooltips. */
    function tableHtml(m, rows, mode) {
        if (m.stages) {
            const stages=m.stages.map(stage=>new Map(stage[mode].map(row=>[row.day,row.current])));
            return '<caption>Distinct trader milestones; historical benchmarks are accepted-or-paid traders.</caption>' +
                '<thead><tr><th>Day / interval</th>'+m.stages.map(stage=>`<th>${escape(stage.label)}</th>`).join('')+
                '<th>Historical average</th><th>Historical maximum</th></tr></thead><tbody>'+
                rows.map(row=>`<tr><td>${intervalLabel(row,mode)}</td>${stages.map(stage=>`<td>${escape(fmt(m,stage.get(row.day)))}</td>`).join('')}<td>${escape(fmt(m,row.average))}</td><td>${escape(fmt(m,row.maximum))}</td></tr>`).join('')+'</tbody>';
        }
        const caption = mode==='weekly' ? 'Additions in each interval; opening day is separate.' : 'Daily cumulative totals.';
        const body = rows.map(row=>`<tr><td>${intervalLabel(row,mode)}</td><td>${escape(fmt(m,row.current))}</td><td>${escape(fmt(m,row.average))}</td><td>${escape(fmt(m,row.maximum))}</td></tr>`).join('');
        return `<caption>${caption}</caption><thead><tr><th>Day / interval</th><th>Selected event</th><th>Previous average</th><th>Previous maximum</th></tr></thead><tbody>${body}</tbody>`;
    }

    /** Describe missing data as well as complete and incomplete weekly intervals. */
    function insight(m, rows, mode) {
        const last = rows.at(-1);
        // Keep the chart selectable even when its dates or amounts need repair.
        if (!last) return m.warnings.join(' ') || 'Run-rate data is unavailable.';
        if (m.stages) {
            const counts=m.stages.map(stage=>`${stage.label}: ${fmt(stage,stage[mode].find(row=>row.day===last.day)?.current)}`).join(' · ');
            return `${mode==='weekly'?'Latest interval':'At day '+last.day}: ${counts}. Historical accepted/paid average: ${fmt(m,last.average)}; maximum: ${fmt(m,last.maximum)}.`;
        }
        const weekly = last.partial ? 'Latest partial week' : last.day===0 ? 'Opening day' : 'Latest week';
        return `${mode==='weekly' ? weekly : 'At day '+last.day}: ${fmt(m,last.current)}. Previous average: ${fmt(m,last.average)}; maximum: ${fmt(m,last.maximum)}.`;
    }

    /** The enclosing button exposes text hidden from SVG screen-reader traversal. */
    function cardLabel(m) {
        if (m.stages) return `${m.label}: ${m.stages.map(stage=>`${fmt(stage,stage.total)} ${stage.label}`).join(', ')}. Historical accepted/paid average: ${fmt(m,m.finalAverage)}; maximum: ${fmt(m,m.finalMaximum)}. Explore run rate.`;
        return `${m.label}: ${fmt(m,m.total)}. Average at day ${m.days}: ${fmt(m,m.comparableAverage)}. Final average: ${fmt(m,m.finalAverage)}; maximum: ${fmt(m,m.finalMaximum)}. ${percent(m.differencePercent)}. Explore run rate.`;
    }

    /** Percentages stay below the circle, leaving its centre uncluttered. */
    function cardHtml(m) {
        const totals=m.stages ? `<span class="pipeline-totals">${m.stages.map(stage=>`<span style="--c:${colour(stage)}">${escape(fmt(stage,stage.total))} ${escape(stage.label.toLowerCase())}</span>`).join('')}</span>` : '';
        const benchmark=m.stages?'Accepted/paid benchmarks':'Final benchmarks';
        return `<span class="label">${escape(m.label)}</span>${categoryChart(m)}${totals}<span class="delta">${m.stages?'Accepted: ':''}${escape(percent(m.differencePercent))}</span><span class="card-note">${benchmark}: ${m.finalSample} events · Same-stage: ${m.comparableSample}</span>${m.warnings.length?'<small>Data notes below</small>':''}<span class="link">Explore run rate ↗</span>`;
    }

    /** Add every metric's description and data-quality notes from the payload. */
    function appendNotes(get, m) {
        get('definitions').insertAdjacentHTML('beforeend',`<p class="foot"><strong>${escape(m.label)}:</strong> ${escape(m.description)}</p>`);
        const warnings = [...m.warnings,...m.historicalWarnings];
        // Hide the notes expander when there is no data-quality issue to explain.
        if (!warnings.length) return;
        get('warnings').insertAdjacentHTML('beforeend',`<details><summary>${escape(m.label)}: data notes</summary>${warnings.map(w=>`<p class="warning">${escape(w)}</p>`).join('')}</details>`);
    }

    /** Build a keyboard-accessible metric selector without model-specific IDs. */
    function appendCard(document, get, m, index, select) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'dashboard-metric'; button.id = 'dashboard-metric-'+index;
        button.setAttribute('aria-controls','dashboard-chart');
        button.setAttribute('aria-label',cardLabel(m));
        button.innerHTML = cardHtml(m);
        button.addEventListener('click',()=>select(m));
        get('cards').appendChild(button);
        get('finals').insertAdjacentHTML('beforeend',finalRow(m));
        appendNotes(get,m);
    }

    /** Refresh every headline and the summary table at the same replay date. */
    function refreshCards(get, metrics, visible, selected) {
        metrics.forEach((metric,index)=>{
            const button=get('metric-'+index), snapshot=visible[index];
            button.setAttribute('aria-pressed',String(metric===selected));
            button.setAttribute('aria-label',cardLabel(snapshot));
            button.innerHTML=cardHtml(snapshot);
        });
        get('finals').innerHTML=visible.map(finalRow).join('');
    }

    function finalRow(m) {
        const label=m.label+(m.stages?' — accepted':'');
        return `<tr><td>${escape(label)}</td><td>${escape(fmt(m,m.total))}</td><td>${escape(fmt(m,m.finalAverage))}</td><td>${escape(fmt(m,m.finalMaximum))}</td><td>${m.finalSample}</td></tr>`;
    }

    /** Selection and replay changes only use the already-aggregated payload. */
    function render(get, metrics, state) {
        const visible=metrics.map(metric=>metricAtDate(metric,state.replayDate));
        const m=visible[metrics.indexOf(state.selected)], rows=m[state.mode];
        refreshCards(get,metrics,visible,state.selected);
        ['cumulative','weekly'].forEach(value=>get(value).setAttribute('aria-pressed',String(value===state.mode)));
        get('chart-title').textContent=m.label;
        get('current-legend').setAttribute('style','--c:'+colour(m));
        get('current-legend').className=m.stages?'stage-legend':'';
        if (m.stages) get('current-legend').innerHTML=m.stages.map(stage=>`<span style="--c:${colour(stage)}">${escape(stage.label)}</span>`).join('');
        else get('current-legend').textContent='Selected event';
        get('chart-subtitle').textContent=`Opened ${date(m.start)} · Day ${m.days} · ${m.comparableSample} previous events with dated comparisons${m.stages?' · Historical benchmarks: accepted-or-paid traders':''}`;
        get('chart').innerHTML=graph(m,rows,state.mode);
        get('insight').textContent=insight(m,rows,state.mode);
        get('chart-data').innerHTML=tableHtml(m,rows,state.mode);
    }

    /** Update the date readout and all charts without requests or database queries. */
    function setReplayDay(get, metrics, state, timeline, value) {
        const last=dayNumber(timeline.end)-dayNumber(timeline.start);
        const day=Math.max(0,Math.min(last,Number(value)));
        const slider=get('replay-day');
        slider.value=String(day);
        state.replayDate=dateAt(timeline.start,day);
        get('replay-date').textContent=date(state.replayDate);
        slider.setAttribute('aria-valuetext',date(state.replayDate));
        get('snapshot').textContent=`Viewing ${date(state.replayDate)} · ${last-day} days until the event`;
        get('replay-previous').disabled=day===0;
        get('replay-next').disabled=day===last;
        render(get,metrics,state);
    }

    /** Only completed events receive a replay control; initialise at the finish. */
    function bindReplay(get, metrics, state, timeline) {
        // A live event keeps the ordinary snapshot and has no replay controls.
        if (!timeline) return;
        get('timeline').hidden=false;
        const slider=get('replay-day'), last=dayNumber(timeline.end)-dayNumber(timeline.start);
        slider.max=String(last);
        const move=value=>setReplayDay(get,metrics,state,timeline,value);
        slider.addEventListener('input',()=>move(slider.value));
        get('replay-previous').addEventListener('click',()=>move(Number(slider.value)-1));
        get('replay-next').addEventListener('click',()=>move(Number(slider.value)+1));
        get('replay-end').addEventListener('click',()=>move(last));
        move(last);
    }

    /** Bind the generic controls once; support any number of query-defined metrics. */
    function mount(document, data) {
        const metrics = data.metrics;
        // A new installation may have no configured events or metrics yet.
        if (!metrics.length) return;
        const get = id=>document.getElementById('dashboard-'+id);
        const state = {selected:metrics[0],mode:'cumulative'};
        const select = metric=>{state.selected=metric;render(get,metrics,state);};
        metrics.forEach((metric,index)=>appendCard(document,get,metric,index,select));
        ['cumulative','weekly'].forEach(value=>get(value).addEventListener('click',()=>{
            state.mode=value;render(get,metrics,state);
        }));
        render(get,metrics,state);
        bindReplay(get,metrics,state,data.timeline);
    }

    // Export pure rendering helpers for dependency-free Node regression checks.
    if (typeof module!=='undefined' && module.exports) {
        module.exports = {categoryChart,graph,mount,fmt,percent,tableHtml,layoutMarkers,metricAtDate,dateAt};
    }

    // A server-rendered empty event list needs no chart initialisation.
    if (typeof document!=='undefined') {
        const source = document.getElementById('event-dashboard-data');
        // json_script escapes HTML-sensitive data before it reaches the DOM.
        if (source) mount(document,JSON.parse(source.textContent));
    }
})();
