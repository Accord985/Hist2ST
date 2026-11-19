"""Self-contained canvas viewer: complete patch data, no CDN or server needed."""
import json
from pathlib import Path


def write_viewer(path, payload):
    data = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c')
    Path(path).write_text(TEMPLATE.replace('__HEATMAP_DATA__', data), encoding='utf-8')


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shared gene expression | patient atlas</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f8;color:#1a2940;font:14px system-ui,Segoe UI,sans-serif}
header{background:#16273f;color:white;padding:25px 30px}header .eyebrow{font-size:11px;letter-spacing:2px;color:#8bcec8;text-transform:uppercase}
h1{font-size:27px;margin:7px 0 9px;font-weight:650}header p{margin:0;color:#c7d2e1;max-width:1100px;line-height:1.55}
main{padding:20px 26px;max-width:2100px;margin:auto}.card{background:white;border:1px solid #dce2ea;border-radius:10px;box-shadow:0 2px 7px #182a4410}
.stats{display:flex;gap:12px;margin-bottom:15px;flex-wrap:wrap}.stat{padding:13px 19px;min-width:150px}.stat b{display:block;font-size:24px}.stat span{font-size:12px;color:#61718a}
.toolbar{display:flex;gap:9px;align-items:center;padding:12px;flex-wrap:wrap;margin-bottom:14px}select,input,button{font:inherit;border:1px solid #c6d0dd;border-radius:6px;background:white;padding:8px 10px;color:#20334f}select{max-width:390px}input{width:100px}button{cursor:pointer}button:hover{background:#eaf5f3;border-color:#579c94}.primary{background:#207f76;color:white;border-color:#207f76}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:14px}.plot{overflow:auto;padding:7px;position:relative}.plot p{margin:6px 12px;color:#627086;font-size:12px}canvas{display:block;touch-action:none}.aside{padding:17px;align-self:start;position:sticky;top:10px}.aside h2{font-size:16px;margin:0 0 13px}.aside dt{font-size:11px;color:#728095;margin-top:12px;text-transform:uppercase;letter-spacing:.6px}.aside dd{margin:3px 0;line-height:1.45;word-break:break-word}.muted{color:#68768c;font-size:12px;line-height:1.5}.ramp{height:14px;border-radius:3px;background:linear-gradient(90deg,#053061,#f7f7f7,#67001f);margin-top:17px}.ramp-labels{display:flex;justify-content:space-between;font-size:11px;color:#627086}.legend{display:flex;flex-wrap:wrap;gap:8px 15px;margin:10px 0}.legend span{font-size:11px;display:inline-flex;align-items:center;gap:6px}.dot{display:inline-block;width:11px;height:11px;border-radius:2px}.table-card{margin-top:18px;padding:17px}.table-card h2{margin:0 0 8px;font-size:18px}.search{width:min(500px,100%);margin:10px 0}.table-scroll{max-height:520px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;position:sticky;top:0;background:#edf2f7;color:#40536e;padding:10px;white-space:nowrap}td{padding:9px 10px;border-bottom:1px solid #e7ecf2;vertical-align:top}tbody tr{cursor:pointer}tbody tr:hover{background:#eef8f5}a{color:#1c756f}.notice{border-left:3px solid #d29a32;padding:8px 12px;background:#fff9ec;margin-top:15px}.group-code{font-weight:650;white-space:nowrap}
@media(max-width:1150px){.layout{grid-template-columns:1fr}.aside{position:static}.aside dl{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.aside dt{margin:0}main{padding:12px}header{padding:20px}}
</style></head><body>
<header><div class="eyebrow">JamesExperiment · HEST · 7% patches per slide</div><h1>Shared gene expression / patient atlas</h1>
<p>Every sampled patch is included. White vertical lines mark the beginning and end of each patient group. Hover to identify the tissue, slide-level disease annotation and expression value; select a patient or drag across the plot to inspect individual patches.</p></header>
<main><div id="stats" class="stats"></div>
<div class="card toolbar"><label>Patient / slide <select id="patient"><option value="all">All patient groups</option></select></label>
<button id="prev">← Previous</button><button id="next">Next →</button><button id="reset">Full cohort</button>
<label>Start <input id="start" type="number" min="1"></label><label>End <input id="end" type="number" min="1"></label><button id="apply" class="primary">Show range</button><button id="save">Save view PNG</button></div>
<div class="layout"><section class="card plot"><p id="range">Loading expression matrix…</p><canvas id="heatmap"></canvas><p>Wheel to zoom; drag left-to-right to select a range. When zoomed out, screen pixels show the mean z-score of their patch columns. Hover values describe the actual patch at the cursor.</p></section>
<aside class="card aside"><h2 id="detail-title">Patch details</h2><p class="muted">Hover over a gene row to inspect a patch.</p><dl id="details"></dl>
<div class="ramp"></div><div class="ramp-labels"><span>−2.5</span><span>0</span><span>+2.5</span></div><p class="muted">Per-gene z-score of log1p(raw expression). Colors are clipped; original expression values are preserved.</p>
<div class="notice muted">P codes: known patient labels, scoped to their dataset. S codes: patient ID is unavailable; each slide remains separate. Boundaries of S groups are slide boundaries, not confirmed biological patient boundaries.</div></aside></div>
<section class="card table-card"><h2>Annotation key</h2><p class="muted">Cancer status comes from slide metadata, not a tumor prediction for individual patches. “Tumor” does not establish malignancy; “Diseased” and “Treated” remain unknown.</p>
<b>Organ</b><div id="organ-legend" class="legend"></div><b>Cancer annotation</b><div id="cancer-legend" class="legend"></div><b>Disease state</b><div id="disease-legend" class="legend"></div>
<p class="muted">Exact tissue names appear in hover details and the boundary table. Tissue track colors distinguish recorded tissue labels.</p></section>
<section class="card table-card"><h2>Patient boundaries and tissue annotations</h2><p class="muted">Column ranges are 1-based and inclusive. Click a row to zoom to that group. The source tensor row mapping is saved in patch_annotations.csv.</p>
<input id="search" class="search" placeholder="Filter by patient, slide, tissue or disease…"><div class="table-scroll"><table><thead><tr><th>Patient / slide group</th><th>Start</th><th>End</th><th>Patches</th><th>Organ</th><th>Tissue</th><th>Disease</th><th>Cancer annotation</th></tr></thead><tbody id="rows"></tbody></table></div>
<p><a href="patient_mean_overview.png">Patient-mean overview PNG</a> · <a href="patient_boundaries.csv">Exact boundaries CSV</a> · <a href="slide_annotations.csv">Slide annotations CSV</a></p></section></main>
<script id="heatmap-data" type="application/json">__HEATMAP_DATA__</script>
<script>
'use strict';
const D=JSON.parse(document.getElementById('heatmap-data').textContent), N=D.patches, G=D.genes.length;
const decoded=atob(D.expression_b64), bytes=new Uint8Array(decoded.length);
for(let i=0;i<bytes.length;i++)bytes[i]=decoded.charCodeAt(i);
const raw=new Float32Array(bytes.buffer), prefix=new Float64Array(G*(N+1));
for(let g=0;g<G;g++){const base=g*(N+1),m=D.log_mean[g],s=D.log_std[g];for(let i=0;i<N;i++)prefix[base+i+1]=prefix[base+i]+(s>0?(Math.log1p(raw[g*N+i])-m)/s:0);}
const canvas=document.getElementById('heatmap'), ctx=canvas.getContext('2d'), patientSelect=document.getElementById('patient');
let lo=0,hi=N,selected=-1,drag=null,layout={};
const format=n=>n.toLocaleString('en-US');
for(const [value,label] of [[N,'sampled patches'],[G,'shared genes'],[D.slides.length,'slides'],[D.patients.filter(p=>p.patient_id_known).length,'known patient groups'],[D.patients.filter(p=>!p.patient_id_known).length,'slides with unknown patient ID']]){
const card=document.createElement('div');card.className='card stat';const b=document.createElement('b');b.textContent=format(value);const s=document.createElement('span');s.textContent=label;card.append(b,s);document.getElementById('stats').append(card);}
D.patients.forEach((p,i)=>{const option=document.createElement('option');option.value=i;option.textContent=p.patient_label+' · '+p.organs;patientSelect.append(option);});
function legend(id,colors){for(const [label,color] of Object.entries(colors)){if(label==='Mixed')continue;const span=document.createElement('span'),dot=document.createElement('i');dot.className='dot';dot.style.background=color;span.append(dot,document.createTextNode(label));document.getElementById(id).append(span);}}
legend('organ-legend',D.organ_colors);legend('cancer-legend',D.cancer_colors);legend('disease-legend',D.disease_colors);
function findRange(rows,col,startKey='start',endKey='end'){let a=0,b=rows.length-1;while(a<=b){const m=(a+b)>>1,r=rows[m];if(col<r[startKey])b=m-1;else if(col>=r[endKey])a=m+1;else return r;}return null;}
function tissueColor(label){let h=0;for(const c of label)h=((h*31)+c.charCodeAt(0))>>>0;return `hsl(${h%360},48%,61%)`;}
function draw(){
 const width=Math.max(950,Math.min(2300,canvas.parentElement.clientWidth-16)),left=116,right=20,top=145,rh=22,pw=Math.floor(width-left-right),bottom=top+G*rh,height=bottom+55,ratio=Math.min(2,window.devicePixelRatio||1);
 canvas.style.width=width+'px';canvas.style.height=height+'px';canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);ctx.fillStyle='white';ctx.fillRect(0,0,width,height);
 layout={left,top,rh,pw,bottom,width,height};
 const off=document.createElement('canvas');off.width=pw;off.height=G;const oc=off.getContext('2d'),img=oc.createImageData(pw,G),span=hi-lo;
 const trackY=[61,80,99,118],trackNames=['Organ','Tissue','Disease','Cancer status'];
 ctx.font='11px system-ui';ctx.textAlign='right';ctx.fillStyle='#52627a';trackNames.forEach((name,i)=>ctx.fillText(name,left-10,trackY[i]+12));
 for(let x=0;x<pw;x++){
  const a=Math.min(hi-1,lo+Math.floor(x*span/pw)),b=Math.min(hi,Math.max(a+1,lo+Math.floor((x+1)*span/pw))),mid=Math.min(hi-1,Math.floor((a+b)/2));
  for(let g=0;g<G;g++){const z=(prefix[g*(N+1)+b]-prefix[g*(N+1)+a])/(b-a),ci=Math.max(0,Math.min(255,Math.round((z+2.5)/5*255))),rgb=D.palette[ci],offset=(g*pw+x)*4;img.data[offset]=rgb[0];img.data[offset+1]=rgb[1];img.data[offset+2]=rgb[2];img.data[offset+3]=255;}
  const slide=findRange(D.slides,mid);const colors=[D.organ_colors[slide.organ],tissueColor(slide.tissue),D.disease_colors[slide.disease],D.cancer_colors[slide.cancer]];
  colors.forEach((color,i)=>{ctx.fillStyle=color||'#adb4c1';ctx.fillRect(left+x,trackY[i],1,15);});
 }
 oc.putImageData(img,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(off,left,top,pw,G*rh);
 ctx.font='11px system-ui';ctx.fillStyle='#172840';ctx.textAlign='right';D.genes.forEach((gene,g)=>ctx.fillText(gene,left-10,top+g*rh+15));
 const visible=D.patients.filter(p=>p.end_index_0based_exclusive>lo&&p.start_index_0based<hi);
 for(const p of visible){const start=(p.start_index_0based-lo)/span*pw+left,end=(p.end_index_0based_exclusive-lo)/span*pw+left;
  ctx.save();ctx.beginPath();ctx.rect(left,38,pw,bottom-38);ctx.clip();ctx.strokeStyle='#ffffff';ctx.lineWidth=1.1;
  for(const x of [start,end]){ctx.beginPath();ctx.moveTo(x,54);ctx.lineTo(x,bottom);ctx.stroke();}ctx.restore();
  if(Math.min(end,left+pw)-Math.max(start,left)>78){ctx.textAlign='center';ctx.font='11px system-ui';ctx.fillStyle='#344c66';ctx.fillText(p.group_code+' '+(p.patient_id_known?p.patient_id:p.slide_ids),Math.max(left+20,Math.min(left+pw-20,(start+end)/2)),43);}
 }
 ctx.font='11px system-ui';ctx.fillStyle='#52627a';for(let i=0;i<=5;i++){const x=left+i*pw/5;ctx.textAlign=i===0?'left':i===5?'right':'center';ctx.fillText(format(lo+Math.round(i*(span-1)/5)+1),x,bottom+22);}
 ctx.textAlign='center';ctx.fillText('Reordered patch column · patient groups are contiguous',left+pw/2,bottom+43);
 document.getElementById('start').value=lo+1;document.getElementById('end').value=hi;document.getElementById('end').max=N;document.getElementById('start').max=N;
 document.getElementById('range').textContent=`Columns ${format(lo+1)}–${format(hi)} · ${format(span)} patches · ${visible.length} patient / slide groups`;
}
function setRange(start,end,index=-1){lo=Math.max(0,Math.min(N-1,Math.floor(start)));hi=Math.max(lo+1,Math.min(N,Math.ceil(end)));selected=index;patientSelect.value=index<0?'all':String(index);draw();}
function focusGroup(index){const p=D.patients[index];setRange(p.start_index_0based,p.end_index_0based_exclusive,index);}
patientSelect.onchange=()=>patientSelect.value==='all'?setRange(0,N):focusGroup(Number(patientSelect.value));
document.getElementById('reset').onclick=()=>setRange(0,N);document.getElementById('apply').onclick=()=>setRange(Number(document.getElementById('start').value)-1,Number(document.getElementById('end').value));
document.getElementById('prev').onclick=()=>focusGroup(Math.max(0,selected<0?0:selected-1));document.getElementById('next').onclick=()=>focusGroup(Math.min(D.patients.length-1,selected<0?0:selected+1));
document.getElementById('save').onclick=()=>{const a=document.createElement('a');a.download=`gene_heatmap_columns_${lo+1}_${hi}.png`;a.href=canvas.toDataURL('image/png');a.click();};
function coord(event){const r=canvas.getBoundingClientRect();return {x:(event.clientX-r.left)*layout.width/r.width,y:(event.clientY-r.top)*layout.height/r.height};}
function patchAt(x){return Math.max(lo,Math.min(hi-1,lo+Math.floor((x-layout.left)/layout.pw*(hi-lo))));}
canvas.addEventListener('wheel',event=>{event.preventDefault();const {x}=coord(event);if(x<layout.left||x>layout.left+layout.pw)return;const f=(x-layout.left)/layout.pw,span=Math.max(2,Math.min(N,(hi-lo)*(event.deltaY>0?1.5:1/1.5))),anchor=lo+f*(hi-lo);let start=Math.max(0,Math.min(N-span,anchor-f*span));setRange(start,start+span);},{passive:false});
canvas.addEventListener('pointerdown',event=>{const p=coord(event);if(p.x>=layout.left&&p.x<=layout.left+layout.pw){drag={x:p.x,patch:patchAt(p.x)};canvas.setPointerCapture(event.pointerId);}});
canvas.addEventListener('pointerup',event=>{if(!drag)return;const p=coord(event),end=patchAt(p.x);if(Math.abs(p.x-drag.x)>6)setRange(Math.min(end,drag.patch),Math.max(end,drag.patch)+1);drag=null;});
canvas.addEventListener('pointermove',event=>{const {x,y}=coord(event);if(x<layout.left||x>layout.left+layout.pw||y<layout.top||y>=layout.bottom)return;
 const col=patchAt(x),gene=Math.floor((y-layout.top)/layout.rh),slide=findRange(D.slides,col),p=findRange(D.patients,col,'start_index_0based','end_index_0based_exclusive'),value=raw[gene*N+col],z=D.log_std[gene]>0?(Math.log1p(value)-D.log_mean[gene])/D.log_std[gene]:0;
 const rows=[['Gene',D.genes[gene]],['Raw expression',value.toLocaleString('en-US',{maximumFractionDigits:5})],['Display z-score',z.toFixed(3)],['Patch column',format(col+1)],['Patient / slide',slide.patient],['Patient ID available',slide.patient_known?'Yes (dataset-scoped)':'No — separate slide'],['Group starts / ends',`${format(p.start_column_1based)}–${format(p.end_column_1based_inclusive)}`],['Slide',slide.slide_id],['Organ',slide.organ],['Tissue',slide.tissue],['Disease state',slide.disease],['Cancer annotation',slide.cancer],['Study',slide.study]];
 const dl=document.getElementById('details');dl.replaceChildren();for(const [label,text] of rows){const box=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=text;box.append(dt,dd);dl.append(box);}document.getElementById('detail-title').textContent=D.genes[gene]+' · '+format(col+1);
});
function drawTable(query=''){const tbody=document.getElementById('rows');tbody.replaceChildren();D.patients.forEach((p,index)=>{const values=[p.patient_label,format(p.start_column_1based),format(p.end_column_1based_inclusive),format(p.patch_count),p.organs,p.tissues,p.disease_states,p.cancer_annotations];if(query&&!values.join(' ').toLowerCase().includes(query))return;const tr=document.createElement('tr');values.forEach((value,i)=>{const td=document.createElement('td');td.textContent=value;if(i===0)td.className='group-code';tr.append(td);});tr.onclick=()=>{focusGroup(index);canvas.scrollIntoView({behavior:'smooth',block:'start'});};tbody.append(tr);});}
document.getElementById('search').oninput=event=>drawTable(event.target.value.toLowerCase());
window.addEventListener('resize',()=>draw());draw();drawTable();document.body.dataset.ready='true';
</script></body></html>'''
