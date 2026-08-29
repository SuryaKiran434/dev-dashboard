#!/usr/bin/env python3
"""
Render data.json into a single self-contained index.html.

Design intent: the page ships 180 days of raw events inline (~3 kB gzipped) and
does ALL filtering, sorting and recomputation in the browser. Changing the time
window or sorting a column is instant and costs no network. Zero external
requests — no web fonts, no CDN, no analytics.
"""
import json, os, html

HERE = os.path.dirname(__file__)
D = json.load(open(os.path.join(HERE, "..", "data.json")))
OWNER = D["owner"]

CSS = """
*{box-sizing:border-box}
:root{color-scheme:light;
--bg:#F2F4F7;--card:#fff;--card2:#FAFBFC;--ink:#0d1117;--ink2:#4a5462;--ink3:#8b95a3;
--line:#E3E7ED;--line2:#EDF0F4;--accent:#2a78d6;--s1:#2a78d6;--s2:#eb6834;
--good:#0ca30c;--warning:#b07600;--serious:#ec835a;--critical:#d03b3b;--mute:#6B7280;
--goodbg:#E4F4E4;--warnbg:#FBF1DA;--critbg:#FAE4E4;--mutebg:#EDEFF3;--grid:#E9EDF2;
--shadow:0 1px 2px rgba(16,24,40,.05),0 1px 3px rgba(16,24,40,.04)}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--bg:#0d1117;--card:#161b22;--card2:#1a2029;--ink:#e6edf3;--ink2:#adbac7;--ink3:#7d8590;
--line:#262c36;--line2:#21262d;--accent:#539bf5;--s1:#539bf5;--s2:#d95926;
--good:#3fb950;--warning:#d29922;--critical:#f85149;--mute:#8b949e;
--goodbg:#12261a;--warnbg:#2b2317;--critbg:#2d1618;--mutebg:#21262d;--grid:#21262d;
--shadow:0 1px 2px rgba(0,0,0,.3)}}
:root[data-theme=dark]{color-scheme:dark;
--bg:#0d1117;--card:#161b22;--card2:#1a2029;--ink:#e6edf3;--ink2:#adbac7;--ink3:#7d8590;
--line:#262c36;--line2:#21262d;--accent:#539bf5;--s1:#539bf5;--s2:#d95926;
--good:#3fb950;--warning:#d29922;--critical:#f85149;--mute:#8b949e;
--goodbg:#12261a;--warnbg:#2b2317;--critbg:#2d1618;--mutebg:#21262d;--grid:#21262d;
--shadow:0 1px 2px rgba(0,0,0,.3)}
body{margin:0;background:var(--bg);color:var(--ink);
font:14.5px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto;padding:26px 20px 70px}
header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
h1{font-size:1.32rem;font-weight:650;letter-spacing:-.021em;margin:0}
.sub{color:var(--ink3);font-size:12.5px;margin:0 0 18px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

/* filter bar — one row, above everything it scopes */
.bar{position:sticky;top:0;z-index:20;background:var(--bg);padding:9px 0 11px;
margin-bottom:16px;border-bottom:1px solid var(--line);display:flex;gap:9px;
align-items:center;flex-wrap:wrap}
.seg{display:inline-flex;background:var(--mutebg);border-radius:7px;padding:2px}
.seg button{border:0;background:none;color:var(--ink2);font:inherit;font-size:12.5px;
font-weight:550;padding:4px 11px;border-radius:5px;cursor:pointer;transition:none}
.seg button[aria-pressed=true]{background:var(--card);color:var(--ink);box-shadow:var(--shadow)}
.seg button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
select,input[type=search]{font:inherit;font-size:12.5px;padding:5px 9px;border:1px solid var(--line);
border-radius:7px;background:var(--card);color:var(--ink);min-width:0}
input[type=search]{width:190px}
select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:-1px}
.spacer{flex:1}
.chip{font-size:11.5px;color:var(--ink3);white-space:nowrap}

h2{font-size:.86rem;font-weight:650;margin:26px 0 3px;letter-spacing:.005em;
text-transform:uppercase;color:var(--ink2)}
.cap{font-size:12px;color:var(--ink3);margin:0 0 11px;max-width:78ch}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(152px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:12px 14px;box-shadow:var(--shadow)}
.tile b{display:block;font-size:24px;font-weight:620;letter-spacing:-.024em;
font-variant-numeric:tabular-nums;line-height:1.22}
.tile span{font-size:10.5px;color:var(--ink3);text-transform:uppercase;
letter-spacing:.06em;font-weight:650}
.tile em{font-style:normal;font-size:11px;color:var(--ink3);display:block;margin-top:1px}
.delta{font-size:11px;font-weight:650;margin-left:6px;vertical-align:2px}
.delta.up{color:var(--good)}.delta.down{color:var(--critical)}.delta.flat{color:var(--ink3)}

.panel{background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:14px 16px;box-shadow:var(--shadow)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
@media(max-width:860px){.two{grid-template-columns:1fr}}
svg.chart{width:100%;height:auto;display:block;overflow:visible}
.grid{stroke:var(--grid);stroke-width:1}
.ax{fill:var(--ink3);font-size:9.5px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.bar-m{transition:none}
.bar-m:hover,.bar-m:focus{filter:brightness(1.14);outline:none}
.legend{display:flex;gap:14px;margin-top:8px;font-size:11.5px;color:var(--ink2)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}

table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:9px;overflow:hidden;box-shadow:var(--shadow)}
th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;
color:var(--ink3);font-weight:650;padding:8px 11px;border-bottom:1px solid var(--line);
background:var(--card2);white-space:nowrap}
th.s{cursor:pointer;user-select:none}
th.s:hover{color:var(--ink)}
th.s::after{content:"";opacity:.32;margin-left:4px;font-size:9px}
th.s[data-dir=asc]::after{content:"▲";opacity:1}
th.s[data-dir=desc]::after{content:"▼";opacity:1}
th.s:not([data-dir])::after{content:"↕"}
td{padding:7px 11px;border-bottom:1px solid var(--line2);font-size:13px}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--card2)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.dim{color:var(--ink3)}
.empty{text-align:center;color:var(--ink3);padding:22px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.pill{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:650;
padding:2px 7px;border-radius:20px;white-space:nowrap}
.pill.good{background:var(--goodbg);color:var(--good)}
.pill.critical{background:var(--critbg);color:var(--critical)}
.pill.warning{background:var(--warnbg);color:var(--warning)}
.pill.mute{background:var(--mutebg);color:var(--mute)}
.sev{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:10.5px;
padding:1px 5px;border-radius:4px;margin-left:2px}
.sev.c,.sev.h{background:var(--critbg);color:var(--critical)}
.sev.m{background:var(--warnbg);color:var(--warning)}
.sev.l{background:var(--mutebg);color:var(--mute)}
.spark{width:64px;height:17px;display:block}
.hb{display:grid;grid-template-columns:1fr 90px 26px;gap:9px;align-items:center;
padding:3.5px 0;font-size:12.5px}
.hbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hbt{background:var(--mutebg);border-radius:3px;height:7px;display:block;overflow:hidden}
.hbt i{display:block;height:7px;border-radius:3px}
.hbt i.bad{background:var(--critical)}.hbt i.warn{background:var(--warning)}
.hbt i.acc{background:var(--s1)}
.hbv{text-align:right;color:var(--ink3);font-variant-numeric:tabular-nums}
.note{font-size:12px;color:var(--ink3);margin:9px 0 0}
code{font-family:ui-monospace,Menlo,monospace;font-size:11px;background:var(--mutebg);
padding:1px 4px;border-radius:3px}
footer{margin-top:32px;padding-top:13px;border-top:1px solid var(--line);
font-size:11.5px;color:var(--ink3)}
.scroll{overflow-x:auto}
#tip{position:fixed;z-index:60;pointer-events:none;opacity:0;background:var(--card);
border:1px solid var(--line);border-radius:7px;padding:7px 10px;font-size:12px;
box-shadow:0 4px 14px rgba(16,24,40,.13);max-width:250px}
#tip b{font-size:14px;font-variant-numeric:tabular-nums}
#tip .k{display:inline-block;width:11px;height:2.5px;border-radius:2px;margin-right:6px;
vertical-align:3px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = r"""
const D = window.__DATA__, NOWH = D.epoch_hours, OWNER = D.owner;
const $ = s => document.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const state = { days: 90, repo: "*", q: "" };

const fmtDur = h => h == null ? "—" : h < 1 ? Math.round(h*60)+"m"
  : h < 48 ? h.toFixed(1)+"h" : (h/24).toFixed(1)+"d";
const median = a => { if (!a.length) return null; const s=[...a].sort((x,y)=>x-y), m=s.length>>1;
  return s.length%2 ? s[m] : (s[m-1]+s[m])/2; };
const ageH = h => { const d = NOWH - h; return d>=24 ? Math.floor(d/24)+"d" : Math.max(d,0)+"h"; };
const el = (t, cls, txt) => { const n=document.createElement(t); if(cls)n.className=cls;
  if(txt!=null)n.textContent=txt; return n; };

function repos() {
  return D.repos.filter(r => state.repo === "*" || r.name === state.repo);
}
// window in hours; `back` shifts to the previous equivalent period for deltas
function cut(back = 0) { return [NOWH - state.days*24*(back+1), NOWH - state.days*24*back]; }

function slice(back = 0) {
  const [lo, hi] = cut(back);
  let opened=0, merged=0, lead=[], runs=0, fails=0, aOpen=0, aFix=0, fixH=[];
  for (const r of repos()) {
    for (const [c,m] of r.pr_events) {
      if (c>=lo && c<hi) opened++;
      if (m>=0 && m>=lo && m<hi) { merged++; lead.push(m-c); }
    }
    for (const [c,o] of (r.run_events||[])) if (c>=lo && c<hi) { runs++; if(o===0) fails++; }
    const a = r.alerts;
    if (a) for (const [c,f] of a.events) {
      if (c>=lo && c<hi) aOpen++;
      if (f>=0 && f>=lo && f<hi) { aFix++; fixH.push(f-c); }
    }
  }
  return { opened, merged, lead, runs, fails, aOpen, aFix, fixH };
}

function openAlertSev() {
  const s = {c:0,h:0,m:0,l:0}; let any=false;
  for (const r of repos()) { const a=r.alerts; if(!a) continue; any=true;
    for (const [,,sev,isOpen] of a.events) if (isOpen) s[["l","m","h","c"][sev]]++; }
  return any ? s : null;
}

function delta(now, prev) {
  if (prev === 0) return now ? {t:"new", c:"flat"} : null;
  const p = Math.round((now-prev)/prev*100);
  if (!p) return {t:"0%", c:"flat"};
  return { t:(p>0?"+":"")+p+"%", c: p>0?"up":"down" };
}

/* ---------- charts ---------- */
const tip = () => $("#tip");
function bindTip(node, rows, title) {
  const show = e => { const t=tip(); t.innerHTML="";
    if (title) t.appendChild(el("div","dim",title));
    rows.forEach(([name,val,color]) => { const d=el("div");
      const k=el("span","k"); k.style.background=color; d.appendChild(k);
      const b=el("b"); b.textContent=val; d.appendChild(b);
      d.appendChild(document.createTextNode(" "));
      d.appendChild(el("span","dim",name)); t.appendChild(d); });
    t.style.opacity=1;
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.min(r.left + r.width/2, innerWidth - 130);
    t.style.left = Math.max(8,x-60)+"px";
    t.style.top = Math.max(8, r.top - t.offsetHeight - 9)+"px"; };
  node.addEventListener("pointerenter", show);
  node.addEventListener("focus", show);
  const hide = () => tip().style.opacity=0;
  node.addEventListener("pointerleave", hide);
  node.addEventListener("blur", hide);
}

function drawBars(host, buckets, labels, names, colors) {
  host.innerHTML = "";
  const W=640,H=126,PL=28,GAP=2,n=buckets[0].length,k=buckets.length;
  const top = Math.max(1, ...buckets.flat());
  const step=(W-PL)/n, bw=Math.max((step-GAP*(k+1))/k, 2.5);
  const NS="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox",`0 0 ${W} ${H+26}`); svg.setAttribute("class","chart");
  svg.setAttribute("role","img"); svg.setAttribute("aria-label",names.join(" and "));
  for(let g=0;g<4;g++){ const y=H-H*g/3;
    const l=document.createElementNS(NS,"line");
    l.setAttribute("x1",PL);l.setAttribute("x2",W);l.setAttribute("y1",y);l.setAttribute("y2",y);
    l.setAttribute("class","grid"); svg.appendChild(l);
    const tx=document.createElementNS(NS,"text");
    tx.setAttribute("x",PL-5);tx.setAttribute("y",y+3.4);tx.setAttribute("class","ax");
    tx.setAttribute("text-anchor","end"); tx.textContent=Math.round(top*g/3); svg.appendChild(tx); }
  for(let i=0;i<n;i++){
    for(let j=0;j<k;j++){
      const v=buckets[j][i]; if(!v) continue;
      const bh=(v/top)*H, x=PL+i*step+GAP+j*(bw+GAP), r=Math.min(4,bw/2,bh);
      const p=document.createElementNS(NS,"path");
      p.setAttribute("d",`M${x},${H} v${-(bh-r)} a${r},${r} 0 0 1 ${r},${-r} h${bw-2*r} a${r},${r} 0 0 1 ${r},${r} V${H} z`);
      p.setAttribute("fill",colors[j]); p.setAttribute("class","bar-m");
      p.setAttribute("tabindex","0"); p.setAttribute("role","img");
      p.setAttribute("aria-label",`${names[j]} ${labels[i]}: ${v}`);
      bindTip(p, [[names[j], v, colors[j]]], labels[i]);
      svg.appendChild(p);
    }
    if(n<=12||i%Math.ceil(n/12)===0){
      const tx=document.createElementNS(NS,"text");
      tx.setAttribute("x",PL+i*step+step/2);tx.setAttribute("y",H+15);
      tx.setAttribute("class","ax");tx.setAttribute("text-anchor","middle");
      tx.textContent=labels[i]; svg.appendChild(tx); }
  }
  host.appendChild(svg);
}

function timeBuckets() {
  // 12 buckets across whatever window is selected
  const n=12, span=state.days*24/n, [lo]=cut();
  const lab=[], po=Array(n).fill(0), pm=Array(n).fill(0), ao=Array(n).fill(0), af=Array(n).fill(0);
  for(let i=0;i<n;i++){
    const endH = lo + span*(i+1);
    const d = new Date(Date.UTC(2020,0,1) + endH*3600e3);
    lab.push(state.days<=14 ? d.toLocaleDateString(undefined,{weekday:"short"})
      : d.toLocaleDateString(undefined,{day:"numeric",month:"short"}));
  }
  const idx = h => Math.min(n-1, Math.max(0, Math.floor((h-lo)/span)));
  for(const r of repos()){
    for(const [c,m] of r.pr_events){ if(c>=lo) po[idx(c)]++; if(m>=0&&m>=lo) pm[idx(m)]++; }
    if(r.alerts) for(const [c,f] of r.alerts.events){ if(c>=lo) ao[idx(c)]++; if(f>=0&&f>=lo) af[idx(f)]++; }
  }
  return {lab, po, pm, ao, af};
}

function sparkFor(r){
  const n=12, [lo]=cut(), span=state.days*24/n, v=Array(n).fill(0);
  for(const [c] of r.pr_events) if(c>=lo) v[Math.min(n-1,Math.floor((c-lo)/span))]++;
  if(!v.some(Boolean)) return null;
  const top=Math.max(...v), NS="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 64 17");svg.setAttribute("class","spark");
  svg.setAttribute("role","img");svg.setAttribute("aria-label","activity trend");
  const bw=(64-(n-1))/n;
  v.forEach((x,i)=>{ if(!x)return; const h=Math.max(x/top*17,1.5);
    const rc=document.createElementNS(NS,"rect");
    rc.setAttribute("x",(i*(bw+1)).toFixed(1));rc.setAttribute("y",(17-h).toFixed(1));
    rc.setAttribute("width",bw.toFixed(1));rc.setAttribute("height",h.toFixed(1));
    rc.setAttribute("rx","1");rc.setAttribute("fill","var(--s1)");svg.appendChild(rc); });
  return svg;
}
"""

JS += r"""
/* ---------- tables (sortable) ---------- */
const CI = {success:["good","✓","passing"],failure:["critical","✕","failing"],
  cancelled:["warning","•","cancelled"],in_progress:["warning","◐","running"],
  queued:["warning","◔","queued"],none:["mute","–","no CI"]};
function ciPill(c){ const [cls,ic,lb]=CI[c]||["warning","•",c];
  const s=el("span","pill "+cls); s.appendChild(el("b",null,ic));
  s.appendChild(document.createTextNode(lb)); return s; }

function sortable(table, rows, cols, defaultCol){
  // rows: array of objects; cols: [{key,label,cls,render,val}]
  let sortKey = table.dataset.sk || defaultCol, dir = table.dataset.sd || "desc";
  const thead=el("thead"), trh=el("tr");
  cols.forEach(c=>{ const th=el("th",(c.cls||"")+" s",c.label);
    if(c.key===sortKey) th.dataset.dir=dir;
    th.tabIndex=0; th.setAttribute("role","button");
    const go=()=>{ if(sortKey===c.key) dir = dir==="asc"?"desc":"asc";
      else { sortKey=c.key; dir="desc"; }
      table.dataset.sk=sortKey; table.dataset.sd=dir; paint(); };
    th.addEventListener("click",go);
    th.addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){e.preventDefault();go();} });
    trh.appendChild(th); });
  thead.appendChild(trh);
  const tbody=el("tbody");
  function paint(){
    const col=cols.find(c=>c.key===sortKey)||cols[0];
    const sorted=[...rows].sort((a,b)=>{
      const x=col.val(a), y=col.val(b);
      const n = typeof x==="number" ? x-y : String(x).localeCompare(String(y));
      return dir==="asc"?n:-n; });
    tbody.innerHTML="";
    if(!sorted.length){ const tr=el("tr"),td=el("td","empty",table.dataset.empty||"Nothing to show.");
      td.colSpan=cols.length; tr.appendChild(td); tbody.appendChild(tr); return; }
    sorted.forEach(r=>{ const tr=el("tr");
      cols.forEach(c=>{ const td=el("td",c.cls); const out=c.render(r);
        if(out instanceof Node) td.appendChild(out); else td.textContent=out??"";
        tr.appendChild(td); }); tbody.appendChild(tr); });
    $$("th.s",table).forEach(th=>delete th.dataset.dir);
    const th=[...trh.children][cols.findIndex(c=>c.key===sortKey)];
    if(th) th.dataset.dir=dir;
  }
  table.innerHTML=""; table.appendChild(thead); table.appendChild(tbody); paint();
}
const link=(t,h,cls)=>{ const a=el("a",cls,t); a.href=h; return a; };

/* ---------- render ---------- */
function render(){
  const now=slice(0), prev=slice(1), rs=repos();
  const wkDiv=state.days/7;
  const sev=openAlertSev();
  const cfr = now.runs ? 100*now.fails/now.runs : 0;
  const pcfr = prev.runs ? 100*prev.fails/prev.runs : 0;

  const tiles=[
    ["Deploy frequency",(now.merged/wkDiv).toFixed(1),"merges / week",delta(now.merged,prev.merged)],
    ["Lead time",fmtDur(median(now.lead)),`median · n=${now.lead.length}`,null],
    ["Change failure rate",cfr.toFixed(1)+"%",`${now.fails} of ${now.runs} runs`,
      prev.runs?delta(Math.round(pcfr*10),Math.round(cfr*10)):null],
    ["Time to restore",fmtDur(restoreMedian()),"failing → next pass",null],
  ];
  paintTiles($("#dora"),tiles);

  const openPRs=rs.flatMap(r=>r.open_prs.map(p=>({...p,repo:r.name})))
    .filter(p=>!state.q||p.title.toLowerCase().includes(state.q)||p.repo.toLowerCase().includes(state.q));
  paintTiles($("#act"),[
    ["Repositories",rs.length,"",null],
    ["Open PRs",openPRs.length,"",null],
    ["PRs opened",now.opened,`last ${state.days}d`,delta(now.opened,prev.opened)],
    ["PRs merged",now.merged,`last ${state.days}d`,delta(now.merged,prev.merged)],
    ["Open alerts",sev?sev.c+sev.h+sev.m+sev.l:"—",sev?`${sev.c} critical · ${sev.h} high`:"",null],
    ["Alert fix time",fmtDur(median(now.fixH)),`median · n=${now.fixH.length}`,null],
  ]);

  const b=timeBuckets();
  drawBars($("#chPR"),[b.po,b.pm],b.lab,["Opened","Merged"],["var(--s1)","var(--s2)"]);
  drawBars($("#chAL"),[b.ao,b.af],b.lab,["Raised","Resolved"],["var(--s1)","var(--s2)"]);

  sortable($("#tPR"),openPRs,[
    {key:"repo",label:"Repo",cls:"mono",val:r=>r.repo,render:r=>link(r.repo,`https://github.com/${OWNER}/${r.repo}`)},
    {key:"num",label:"PR",cls:"num mono",val:r=>r.num,render:r=>link("#"+r.num,r.url)},
    {key:"title",label:"Title",val:r=>r.title,render:r=>{const s=el("span",null,r.title);
      if(r.draft){s.appendChild(document.createTextNode(" "));s.appendChild(el("span","pill mute","draft"));}return s;}},
    {key:"author",label:"Author",cls:"mono dim",val:r=>r.author,render:r=>r.author},
    {key:"age",label:"Age",cls:"num mono dim",val:r=>-r.created_h,render:r=>ageH(r.created_h)},
  ],"age");

  const fails=rs.flatMap(r=>r.failing_runs.map(f=>({...f,repo:r.name})))
    .filter(f=>f.at_h>=cut()[0]);
  sortable($("#tFail"),fails,[
    {key:"repo",label:"Repo",cls:"mono",val:f=>f.repo,render:f=>link(f.repo,`https://github.com/${OWNER}/${f.repo}`)},
    {key:"wf",label:"Workflow",cls:"dim",val:f=>f.wf,render:f=>f.wf},
    {key:"cause",label:"Caused by",val:f=>f.pr?f.pr.title:f.msg,render:f=>{const s=el("span");
      if(f.pr){s.appendChild(link("#"+f.pr.num,f.pr.url,"mono"));s.appendChild(document.createTextNode(" "+f.pr.title));}
      else{s.appendChild(el("span","mono dim",f.sha));s.appendChild(document.createTextNode(" "+f.msg));}return s;}},
    {key:"when",label:"When",cls:"num mono dim",val:f=>-f.at_h,render:f=>link(ageH(f.at_h),f.url)},
  ],"when");

  sortable($("#tRepo"),rs.map(r=>{
    const [lo,hi]=cut(); let o=0,m=0,lead=[],runs=0,fails=0;
    for(const [c,mg] of r.pr_events){ if(c>=lo&&c<hi)o++; if(mg>=0&&mg>=lo&&mg<hi){m++;lead.push(mg-c);} }
    for(const [c,oc] of (r.run_events||[])) if(c>=lo&&c<hi){runs++;if(oc===0)fails++;}
    const s={c:0,h:0,m:0,l:0}; let has=false;
    if(r.alerts){has=true;for(const [,,sv,op] of r.alerts.events) if(op)s[["l","m","h","c"][sv]]++;}
    return {...r,_o:o,_m:m,_lead:median(lead),_fr:runs?100*fails/runs:null,_sev:has?s:null,
            _cq:r.codeql?r.codeql.total:null};
  }),[
    {key:"name",label:"Repo",cls:"mono",val:r=>r.name,render:r=>link(r.name,r.url)},
    {key:"lang",label:"Lang",cls:"dim",val:r=>r.lang,render:r=>r.lang},
    {key:"open",label:"Open",cls:"num",val:r=>r.open_prs.length,render:r=>r.open_prs.length||"—"},
    {key:"o",label:"Opened",cls:"num dim",val:r=>r._o,render:r=>r._o},
    {key:"m",label:"Merged",cls:"num dim",val:r=>r._m,render:r=>r._m},
    {key:"lead",label:"Lead",cls:"num mono",val:r=>r._lead??1e9,render:r=>fmtDur(r._lead)},
    {key:"fr",label:"Fail %",cls:"num mono",val:r=>r._fr??-1,render:r=>r._fr==null?"—":r._fr.toFixed(0)+"%"},
    {key:"ci",label:"CI",val:r=>r.ci_latest==="failure"?0:1,render:r=>ciPill(r.ci_latest)},
    {key:"alerts",label:"Alerts",cls:"num",val:r=>r._sev?r._sev.c*100+r._sev.h*10+r._sev.m:-1,
      render:r=>{ if(!r._sev)return el("span","dim","—"); const s=el("span");
        [["c",r._sev.c],["h",r._sev.h],["m",r._sev.m],["l",r._sev.l]].forEach(([k,v])=>{
          if(v)s.appendChild(el("span","sev "+k,v)); });
        return s.childNodes.length?s:el("span","dim","0"); }},
    {key:"cq",label:"CodeQL",cls:"num",val:r=>r._cq??-1,render:r=>r._cq==null?el("span","dim","—"):String(r._cq)},
    {key:"spark",label:state.days+"d",val:r=>r._o,render:r=>sparkFor(r)||el("span","dim","—")},
    {key:"pushed",label:"Pushed",cls:"num mono dim",val:r=>-r.pushed_h,render:r=>ageH(r.pushed_h)},
  ],"alerts");

  paintCQ();
  $("#chip").textContent=`${rs.length} repo${rs.length===1?"":"s"} · ${openPRs.length} open PR${openPRs.length===1?"":"s"}`;
}

function restoreMedian(){
  const [lo]=cut(), out=[];
  for(const r of repos()){
    const ev=(r.run_events||[]).filter(([c])=>c>=lo).sort((a,b)=>a[0]-b[0]);
    let f=null; for(const [c,o] of ev){ if(o===0&&f===null)f=c; else if(o===1&&f!==null){out.push(c-f);f=null;} }
  }
  return median(out);
}

function paintTiles(host,rows){
  host.innerHTML="";
  rows.forEach(([label,val,sub,d])=>{ const t=el("div","tile");
    const b=el("b"); b.textContent=val;
    if(d){ const s=el("span","delta "+d.c,d.t); b.appendChild(s); }
    t.appendChild(b); t.appendChild(el("span",null,label));
    if(sub) t.appendChild(el("em",null,sub)); host.appendChild(t); });
}

function paintCQ(){
  const rs=repos().filter(r=>r.sonar&&r.sonar.measures);
  const num=(r,k)=>parseFloat((r.sonar.measures[k]??"0"))||0;
  const vuln=rs.reduce((a,r)=>a+num(r,"vulnerabilities"),0);
  const bugs=rs.reduce((a,r)=>a+num(r,"bugs"),0);
  const smell=rs.reduce((a,r)=>a+num(r,"code_smells"),0);
  const debt=rs.reduce((a,r)=>a+num(r,"sqale_index"),0);
  const ncloc=rs.reduce((a,r)=>a+num(r,"ncloc"),0);
  // lines-weighted, not a mean of percentages — a 6k-line repo should not
  // count the same as a 600-line one
  const covRs=rs.filter(r=>r.sonar.measures.coverage!=null);
  const covW=covRs.reduce((a,r)=>a+num(r,"coverage")*num(r,"ncloc"),0);
  const covN=covRs.reduce((a,r)=>a+num(r,"ncloc"),0);
  const failing=rs.filter(r=>r.sonar.gate==="ERROR").length;
  const cq=repos().filter(r=>r.codeql).reduce((a,r)=>a+r.codeql.total,0);
  paintTiles($("#sq"),[
    ["Quality gates",`${rs.length-failing}/${rs.length}`,"passing",null],
    ["Coverage",(covN?covW/covN:0).toFixed(1)+"%","weighted by lines",null],
    ["Vulnerabilities",vuln,"all code, not just new",null],
    ["Bugs",bugs,"",null],
    ["Code smells",smell,`${Math.round(debt/60)}h estimated debt`,null],
    ["CodeQL",cq,"open security alerts",null],
  ]);

  sortable($("#tSonar"),rs.map(r=>({...r,
    _g:r.sonar.gate,_c:r.sonar.measures.coverage==null?null:num(r,"coverage"),
    _n:num(r,"ncloc"),_v:num(r,"vulnerabilities"),_b:num(r,"bugs"),
    _s:num(r,"code_smells"),_d:num(r,"duplicated_lines_density"),
    _t:num(r,"sqale_index"),_q:r.codeql?r.codeql.total:null})),[
    {key:"name",label:"Repo",cls:"mono",val:r=>r.name,render:r=>link(r.name,`https://sonarcloud.io/project/overview?id=${OWNER}_${r.name}`)},
    {key:"gate",label:"Gate",val:r=>r._g==="ERROR"?0:r._g==="OK"?2:1,render:r=>{
      const m={OK:["good","✓","passing"],ERROR:["critical","✕","failing"]}[r._g]||["mute","–","no baseline"];
      const s=el("span","pill "+m[0]); s.appendChild(el("b",null,m[1]));
      s.appendChild(document.createTextNode(m[2])); return s;}},
    {key:"cov",label:"Coverage",cls:"num mono",val:r=>r._c??-1,render:r=>r._c==null?el("span","dim","—"):r._c.toFixed(1)+"%"},
    {key:"ncloc",label:"Lines",cls:"num mono dim",val:r=>r._n,render:r=>r._n.toLocaleString()},
    {key:"vuln",label:"Vuln",cls:"num",val:r=>r._v,render:r=>r._v?el("span","sev h",r._v):el("span","dim","0")},
    {key:"bugs",label:"Bugs",cls:"num",val:r=>r._b,render:r=>r._b?el("span","sev m",r._b):el("span","dim","0")},
    {key:"smells",label:"Smells",cls:"num mono dim",val:r=>r._s,render:r=>String(r._s)},
    {key:"dup",label:"Dup %",cls:"num mono dim",val:r=>r._d,render:r=>r._d.toFixed(1)},
    {key:"debt",label:"Debt",cls:"num mono dim",val:r=>r._t,render:r=>r._t<60?"—":Math.round(r._t/60)+"h"},
    {key:"codeql",label:"CodeQL",cls:"num",val:r=>r._q??-1,render:r=>r._q==null?el("span","dim","—"):String(r._q)},
  ],"vuln");

  hbars($("#sqCov"),rs.filter(r=>r.sonar.measures.coverage!=null)
    .sort((a,b)=>num(b,"coverage")-num(a,"coverage"))
    .map(r=>[r.name,+num(r,"coverage").toFixed(1),
      num(r,"coverage")<40?"bad":num(r,"coverage")<70?"warn":"acc",
      `https://sonarcloud.io/component_measures?id=${OWNER}_${r.name}&metric=coverage`]));
  hbars($("#sqIss"),rs.map(r=>[r.name,num(r,"vulnerabilities")+num(r,"bugs"),
      num(r,"vulnerabilities")?"bad":"warn",
      `https://sonarcloud.io/project/issues?id=${OWNER}_${r.name}&resolved=false`])
    .filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]));
}
function hbars(host,rows){
  host.innerHTML="";
  if(!rows.length){ host.appendChild(el("p","empty","No open findings.")); return; }
  const top=Math.max(...rows.map(r=>r[1]),1);
  rows.forEach(([label,val,cls,href])=>{ const d=el("div","hb");
    const l=el("span","hbl mono"); l.appendChild(href?link(label,href):document.createTextNode(label));
    const t=el("span","hbt"); const i=el("i",cls); i.style.width=(val/top*100).toFixed(1)+"%";
    t.appendChild(i); d.appendChild(l); d.appendChild(t); d.appendChild(el("span","hbv num mono",val));
    host.appendChild(d); });
}

/* ---------- wire up ---------- */
$$("#win button").forEach(b=>b.addEventListener("click",()=>{
  state.days=+b.dataset.d;
  $$("#win button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
  render(); }));
const sel=$("#repo");
D.repos.slice().sort((a,b)=>a.name.localeCompare(b.name)).forEach(r=>{
  const o=el("option",null,r.name); o.value=r.name; sel.appendChild(o); });
sel.addEventListener("change",()=>{ state.repo=sel.value; render(); });
let qt; $("#q").addEventListener("input",e=>{ clearTimeout(qt);
  qt=setTimeout(()=>{ state.q=e.target.value.trim().toLowerCase(); render(); },120); });
render();
"""

E = html.escape
gen = D["generated"][:16].replace("T", " ")
te = D.get("token_expiry")
tok = ""
if te:
    from datetime import datetime, timezone
    try:
        d = datetime.strptime(te.split(" ")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        left = (d - datetime.now(timezone.utc)).days
        tok = (f'<p class="note">{"⚠ " if left < 21 else ""}Build token '
               f'{"expires in <b>%d days</b>" % left if left < 21 else "valid for %d more days" % left} '
               f'({d.strftime("%d %b %Y")}).</p>')
    except Exception:
        pass

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(OWNER)} — engineering dashboard</title>
<meta name="description" content="Open PRs, delivery metrics, security alerts and code quality across every repository.">
<style>{CSS}</style></head><body>
<div class="wrap">
<header><h1>{E(OWNER)}</h1><span class="chip mono" id="chip"></span></header>
<p class="sub">Every repository, discovered automatically · rebuilt {E(gen)} UTC · filters apply to everything below</p>

<div class="bar" role="group" aria-label="Filters">
  <div class="seg" id="win" role="group" aria-label="Time range">
    <button data-d="7" aria-pressed="false">7d</button>
    <button data-d="30" aria-pressed="false">30d</button>
    <button data-d="90" aria-pressed="true">90d</button>
    <button data-d="180" aria-pressed="false">180d</button>
  </div>
  <select id="repo" aria-label="Repository"><option value="*">All repositories</option></select>
  <input type="search" id="q" placeholder="Filter PRs…" aria-label="Filter pull requests">
  <span class="spacer"></span>
</div>

<h2>Delivery</h2>
<p class="cap">DORA proxies. No deploy pipeline exists here, so <em>merge to default branch</em> stands in for a deployment and default-branch CI failure for a change failure. Deltas compare against the previous equal-length period.</p>
<div class="tiles" id="dora"></div>

<h2>Activity</h2>
<div class="tiles" id="act"></div>

<div class="two">
  <div class="panel"><h2 style="margin:0 0 2px">Pull requests</h2>
    <p class="cap">Opened vs merged across the selected window.</p>
    <div id="chPR"></div>
    <div class="legend"><span><i style="background:var(--s1)"></i>Opened</span><span><i style="background:var(--s2)"></i>Merged</span></div></div>
  <div class="panel"><h2 style="margin:0 0 2px">Dependabot alerts</h2>
    <p class="cap">Raised vs resolved (fixed or dismissed).</p>
    <div id="chAL"></div>
    <div class="legend"><span><i style="background:var(--s1)"></i>Raised</span><span><i style="background:var(--s2)"></i>Resolved</span></div></div>
</div>

<h2>Open pull requests</h2>
<div class="scroll"><table id="tPR" data-empty="No open pull requests match these filters."></table></div>

<h2>Failed runs</h2>
<p class="cap">Default-branch failures, with the pull request that introduced them where the commit maps to one.</p>
<div class="scroll"><table id="tFail" data-empty="No failed runs in this window."></table></div>

<h2>Per-repository</h2>
<p class="cap">Every column sorts — click a header or focus it and press Enter. Defaults to worst alerts first.</p>
<div class="scroll"><table id="tRepo"></table></div>

<h2>Code quality</h2>
<p class="cap">SonarCloud static analysis with imported test coverage, plus CodeQL security scanning. Quality gates judge <em>new</em> code only — a repo can pass its gate while carrying findings on existing code.</p>
<div class="tiles" id="sq"></div>
<div class="scroll" style="margin-top:12px"><table id="tSonar"></table></div>
<div class="two">
  <div class="panel"><h2 style="margin:0 0 2px">Coverage by repository</h2><p class="cap">Imported from CI into SonarCloud.</p><div id="sqCov"></div></div>
  <div class="panel"><h2 style="margin:0 0 2px">Open findings</h2><p class="cap">Vulnerabilities plus bugs, worst first.</p><div id="sqIss"></div></div>
</div>
<p class="note" id="cqNote"></p>
{tok}
<footer>Rebuilt on a schedule by GitHub Actions and published as a Pages artifact — no commits, no notifications.
180 days of events ship inline, so every filter and sort is instant and needs no network. New repositories appear with no configuration.</footer>
</div>
<div id="tip" role="status" aria-live="polite"></div>
<script>window.__DATA__={json.dumps(D, separators=(",", ":"))};</script>
<script>{JS}</script>
</body></html>"""

with open(os.path.join(HERE, "..", "index.html"), "w") as f:
    f.write(HTML)
print(f"rendered {len(HTML)} bytes")
