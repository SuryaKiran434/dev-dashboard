#!/usr/bin/env python3
"""
Render data.json into a single self-contained index.html.

Design intent: the page ships 180 days of raw events inline (~3 kB gzipped) and
does ALL filtering, sorting and recomputation in the browser. Changing the time
window or sorting a column is instant and costs no network. Zero external
requests — no web fonts, no CDN, no analytics.
"""
import json, os, html
from datetime import datetime as _dt, datetime, timezone

HERE = os.path.dirname(__file__)
DATA_PATH = os.path.join(HERE, "..", "data.json")
OUT_PATH = os.path.join(HERE, "..", "index.html")

CSS = """
*{box-sizing:border-box}
:root{color-scheme:light;
/* Surfaces — light ground, white cards, in the Devias/Minimal idiom */
--bg:#F9FAFB;--card:#FFFFFF;--card2:#F4F6F8;--ink:#212B36;--ink2:#637381;--ink3:#919EAB;
--line:#EDF0F2;--line2:#F4F6F8;--grid:#EDF0F2;
--accent:#2C66A3;--s1:#3169A6;--s2:#B76E00;
/* Magnitude ramp — computed, not picked. Validated light: monotone L,
   adjacent dL>=0.06, light end 2.09:1 vs surface, hue spread 4deg. */
--m1:#82B4E5;--m2:#619CD7;--m3:#4382C4;--m4:#2C66A3;--m5:#1E4F82;--m6:#12385F;
/* Status — reserved, never reused as a series colour */
--good:#22A06B;--warning:#B76E00;--critical:#B71D18;--mute:#637381;
--goodbg:#DCF6E9;--warnbg:#FFF3D6;--critbg:#FFE9E7;--mutebg:#F4F6F8;
--sh:0 0 2px rgba(145,158,171,.20),0 12px 24px -4px rgba(145,158,171,.12);
--sh-lift:0 0 2px rgba(145,158,171,.24),0 20px 40px -8px rgba(145,158,171,.24);
--shadow:var(--sh);--r:16px}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
--bg:#161C24;--card:#212B36;--card2:#1C242E;--ink:#F9FAFB;--ink2:#919EAB;--ink3:#637381;
--line:#2A3541;--line2:#232D38;--grid:#2A3541;
--accent:#6BAFDD;--s1:#5199CE;--s2:#E0A93D;
/* Validated dark: light end 2.17:1 vs #161C24, monotone, hue spread 10deg */
--m1:#2E5478;--m2:#386A97;--m3:#4381B6;--m4:#5199CE;--m5:#70B4E1;--m6:#98CAEE;
--good:#5BE49B;--warning:#FFD666;--critical:#FF8A80;--mute:#919EAB;
--goodbg:#123D2B;--warnbg:#3D3117;--critbg:#3D1D1B;--mutebg:#1C242E;
--sh:0 0 2px rgba(0,0,0,.32),0 12px 24px -4px rgba(0,0,0,.42);
--sh-lift:0 0 2px rgba(0,0,0,.4),0 20px 40px -8px rgba(0,0,0,.55)}}
:root[data-theme=dark]{color-scheme:dark;
--bg:#161C24;--card:#212B36;--card2:#1C242E;--ink:#F9FAFB;--ink2:#919EAB;--ink3:#637381;
--line:#2A3541;--line2:#232D38;--grid:#2A3541;
--accent:#6BAFDD;--s1:#5199CE;--s2:#E0A93D;
--m1:#2E5478;--m2:#386A97;--m3:#4381B6;--m4:#5199CE;--m5:#70B4E1;--m6:#98CAEE;
--good:#5BE49B;--warning:#FFD666;--critical:#FF8A80;--mute:#919EAB;
--goodbg:#123D2B;--warnbg:#3D3117;--critbg:#3D1D1B;--mutebg:#1C242E;
--sh:0 0 2px rgba(0,0,0,.32),0 12px 24px -4px rgba(0,0,0,.42);
--sh-lift:0 0 2px rgba(0,0,0,.4),0 20px 40px -8px rgba(0,0,0,.55)}
html,body{background:var(--bg)}
body{margin:0;color:var(--ink);
font:15px/1.55 "Public Sans","IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:1320px;margin:0 auto;padding:32px 24px 80px}

/* ── motion ─────────────────────────────────────────────── */
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
.tile,.panel,table,.pat{animation:rise .55s cubic-bezier(.22,.9,.28,1) both}
.tile:nth-child(2),.panel:nth-child(2){animation-delay:.06s}
.tile:nth-child(3){animation-delay:.12s}.tile:nth-child(4){animation-delay:.18s}
.tile:nth-child(5){animation-delay:.24s}.tile:nth-child(6){animation-delay:.3s}

header{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:4px}
h1{font-size:1.6rem;font-weight:800;letter-spacing:-.03em;margin:0}
.sub{color:var(--ink2);font-size:13.5px;margin:4px 0 24px;display:flex;align-items:center;gap:8px}
.sub::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--good);
animation:pulse 2.2s ease-in-out infinite;flex:none}
.mono{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

/* ── rebuild control ────────────────────────────────────── */
.rbwrap{margin-left:auto;align-self:center;display:flex;align-items:center;gap:8px}
.rebuild{font:inherit;font-size:13.5px;font-weight:700;cursor:pointer;color:#fff;
background:var(--accent);border:0;border-radius:10px;padding:9px 16px;white-space:nowrap;
box-shadow:0 8px 16px -8px color-mix(in oklab,var(--accent) 90%,transparent);
transition:transform .18s,box-shadow .18s,filter .18s}
.rebuild:hover:not([disabled]){transform:translateY(-2px);filter:brightness(1.08);
box-shadow:0 14px 22px -10px color-mix(in oklab,var(--accent) 90%,transparent)}
.rebuild[disabled]{cursor:progress;opacity:.65}
.rbkey{font:inherit;font-size:12.5px;cursor:pointer;color:var(--ink3);background:none;
border:0;padding:4px;text-decoration:underline;text-underline-offset:2px}
.rbkey:hover{color:var(--ink2)}
.rbstat{font-size:13px;color:var(--ink3);white-space:nowrap;font-variant-numeric:tabular-nums}
.rbstat.bad{color:var(--critical)}
.rbstat a{color:inherit}
.pat{background:var(--card);border-radius:var(--r);padding:20px;margin:0 0 20px;
box-shadow:var(--sh);max-width:680px}
.pat p{margin:0 0 12px;font-size:14px;color:var(--ink2);line-height:1.5}
.pat p:last-child{margin-bottom:0}
.patrow{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.patrow input{flex:1 1 260px;font:inherit;font-size:13.5px;padding:10px 12px;
border:1px solid var(--line);border-radius:10px;background:var(--card2);color:var(--ink)}
.patrow button{font:inherit;font-size:13.5px;font-weight:700;cursor:pointer;padding:10px 16px;
border-radius:10px;border:0;background:var(--accent);color:#fff}
.patrow button.ghost{background:var(--card2);color:var(--ink2)}
.patnote{font-size:12.5px!important;color:var(--ink3)!important}

/* ── filter bar ─────────────────────────────────────────── */
.bar{position:sticky;top:0;z-index:20;background:color-mix(in oklab,var(--bg) 88%,transparent);
backdrop-filter:blur(8px);padding:12px 0 16px;margin-bottom:20px;
border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.seg{display:inline-flex;background:var(--card);border-radius:12px;padding:4px;box-shadow:var(--sh)}
.seg button{border:0;background:none;color:var(--ink2);font:inherit;font-size:13.5px;
font-weight:600;padding:7px 15px;border-radius:9px;cursor:pointer;transition:background .2s,color .2s}
.seg button[aria-pressed=true]{background:var(--accent);color:#fff}
select,input[type=search]{font:inherit;font-size:13.5px;padding:9px 13px;border:1px solid var(--line);
border-radius:10px;background:var(--card);color:var(--ink);min-width:0;box-shadow:var(--sh)}
input[type=search]{width:230px}
.seg button:focus-visible,select:focus-visible,input:focus-visible,.rebuild:focus-visible,
.rbkey:focus-visible,th.s:focus-visible,.bar-m:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.spacer{flex:1}
.chip{font-size:13px;color:var(--ink3);white-space:nowrap}

h2{font-size:1.14rem;font-weight:700;margin:36px 0 4px;letter-spacing:-.02em;color:var(--ink)}
.cap{font-size:13.5px;color:var(--ink2);margin:0 0 16px;max-width:86ch}

/* ── stat tiles ─────────────────────────────────────────── */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.tile{background:var(--card);border-radius:var(--r);padding:20px;box-shadow:var(--sh);
transition:transform .28s cubic-bezier(.22,.9,.28,1),box-shadow .28s}
.tile:hover{transform:translateY(-4px);box-shadow:var(--sh-lift)}
/* Flex + wrap so a long value and its delta badge can never overflow the
   card: the badge drops to its own line instead of pushing past the edge. */
.tile b{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px;
font-size:2.1rem;font-weight:800;letter-spacing:-.04em;
font-variant-numeric:tabular-nums;line-height:1.1;margin:8px 0 2px;
min-width:0;overflow-wrap:anywhere}
.tile span{font-size:12px;color:var(--ink3);text-transform:uppercase;
letter-spacing:.08em;font-weight:700}
.tile em{font-style:normal;font-size:12.5px;color:var(--ink3);display:block;margin-top:4px}
.delta{font-size:12.5px;font-weight:700;padding:3px 8px;border-radius:99px;
letter-spacing:0;white-space:nowrap;flex:none;align-self:center}
.delta.up{color:var(--good);background:var(--goodbg)}
.delta.down{color:var(--critical);background:var(--critbg)}
.delta.flat{color:var(--ink2);background:var(--mutebg)}

.panel{background:var(--card);border-radius:var(--r);padding:20px;box-shadow:var(--sh);
transition:transform .28s cubic-bezier(.22,.9,.28,1),box-shadow .28s}
.panel:hover{transform:translateY(-3px);box-shadow:var(--sh-lift)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
@media(max-width:880px){.two{grid-template-columns:1fr}}
svg.chart{width:100%;height:auto;display:block;overflow:visible}
.grid{stroke:var(--grid);stroke-width:1}
.ax{fill:var(--ink3);font-size:11px;font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace}
.bar-m{transition:filter .18s}
.bar-m:hover,.bar-m:focus{filter:brightness(1.12);outline:none}
.legend{display:flex;gap:16px;margin-top:12px;font-size:13px;color:var(--ink2)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:4px;margin-right:8px}

/* ── tables ─────────────────────────────────────────────── */
table{width:100%;border-collapse:collapse;background:var(--card);
border-radius:var(--r);overflow:hidden;box-shadow:var(--sh)}
th{text-align:left;font-size:12px;letter-spacing:.04em;color:var(--ink2);text-transform:uppercase;
font-weight:700;padding:14px 16px;border-bottom:1px solid var(--line);
background:var(--card2);white-space:nowrap}
th.s{cursor:pointer;user-select:none}
th.s:hover{color:var(--ink)}
th.s::after{content:"↕";opacity:.3;margin-left:6px;font-size:10px}
th.s[data-dir=asc]::after{content:"▲";opacity:1}
th.s[data-dir=desc]::after{content:"▼";opacity:1}
td{padding:13px 16px;border-bottom:1px solid var(--line2);font-size:14px}
tbody tr:last-child td{border-bottom:0}
tbody tr{transition:background .18s}
tbody tr:hover{background:var(--card2)}
.num{text-align:right;font-variant-numeric:tabular-nums}
.dim{color:var(--ink3)}
.empty{text-align:center;color:var(--ink3);padding:32px;font-size:14px}
a{color:var(--accent);text-decoration:none;font-weight:600}
a:hover{text-decoration:underline}

/* ── pills, severities, bars ────────────────────────────── */
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;
padding:4px 10px;border-radius:8px;white-space:nowrap}
.pill b{font-size:11px}
.pill.good{background:var(--goodbg);color:var(--good)}
.pill.critical{background:var(--critbg);color:var(--critical)}
.pill.warning{background:var(--warnbg);color:var(--warning)}
.pill.mute{background:var(--mutebg);color:var(--mute)}
.sevwrap{display:flex;gap:4px;justify-content:flex-end;align-items:center;flex-wrap:nowrap}
.sev{display:inline-flex;align-items:center;justify-content:center;min-width:26px;
font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:12.5px;
font-weight:600;padding:3px 7px;border-radius:6px;line-height:1.35}
.sev.c,.sev.h{background:var(--critbg);color:var(--critical)}
.sev.m{background:var(--warnbg);color:var(--warning)}
.sev.l{background:var(--mutebg);color:var(--mute)}
.spark{width:74px;height:20px;display:block}
.hb{display:grid;grid-template-columns:1fr 120px 64px;gap:12px;align-items:center;
padding:7px 0;font-size:14px}
.hbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hbt{background:var(--mutebg);border-radius:99px;height:10px;display:block;overflow:hidden}
.hbt i{display:block;height:10px;border-radius:99px;
transition:width 1.1s cubic-bezier(.22,.9,.28,1)}
.hbt i.bad{background:var(--critical)}.hbt i.warn{background:var(--warning)}
.hbt i.good{background:var(--good)}.hbt i.acc{background:var(--m4)}
.hbv{text-align:right;color:var(--ink2);font-variant-numeric:tabular-nums;font-weight:600}
.note{font-size:13.5px;color:var(--ink2);margin:12px 0 0}
code{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:13px;
background:var(--mutebg);padding:2px 6px;border-radius:6px}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);
font-size:13px;color:var(--ink3)}
.scroll{overflow-x:auto}
#tip{position:fixed;z-index:60;pointer-events:none;opacity:0;background:var(--card);
border:1px solid var(--line);border-radius:12px;padding:10px 13px;font-size:13.5px;
box-shadow:var(--sh-lift);max-width:280px}
#tip b{font-size:15px;font-variant-numeric:tabular-nums}
#tip .k{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:8px;vertical-align:4px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = r"""
const D = window.__DATA__, NOWH = D.epoch_hours, OWNER = D.owner;
const $ = s => document.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const state = { days: 90, repo: "*", q: "" };

// minutes -> "3h 20m". Rounding each repo to whole hours and summing those is
// what made the total disagree with the rows; format once, at the end.
const fmtDebt = m => !m ? "—" : m<60 ? m+"m" : (m%60 ? Math.floor(m/60)+"h "+(m%60)+"m" : Math.floor(m/60)+"h");
const fmtDur = h => h == null ? "—" : h < 1 ? Math.round(h*60)+"m"
  : h < 48 ? h.toFixed(1)+"h" : (h/24).toFixed(1)+"d";
const median = a => { if (!a.length) return null; const s=[...a].sort((x,y)=>x-y), m=s.length>>1;
  return s.length%2 ? s[m] : (s[m-1]+s[m])/2; };
const ET = {timeZone:"America/New_York",month:"short",day:"numeric",
  hour:"numeric",minute:"2-digit",timeZoneName:"short"};
// epoch-hours -> a real Eastern timestamp; Intl applies EST/EDT from the tz
// database, so daylight saving needs no special handling here.
const absTime = h => new Date(Date.UTC(2020,0,1)+h*3600e3).toLocaleString(undefined,ET);
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
  // `opened` and `merged` count different cohorts on purpose: PRs CREATED in
  // the window, and PRs MERGED in it, which are not the same set -- a pull
  // request opened before the window and merged inside it lands in the second
  // and not the first. Read as a funnel they look like broken arithmetic, so
  // cohortMerged tracks the one thing that IS a funnel: of the pull requests
  // opened in this window, how many were ever merged.
  let cohortMerged=0;
  for (const r of repos()) {
    for (const [c,m] of r.pr_events) {
      if (c>=lo && c<hi) { opened++; if (m>=0) cohortMerged++; }
      if (m>=0 && m>=lo && m<hi) { merged++; lead.push(m-c); }
    }
    for (const [c,o] of (r.run_events||[])) if (c>=lo && c<hi) { runs++; if(o===0) fails++; }
    const a = r.alerts;
    if (a) for (const [c,f] of a.events) {
      if (c>=lo && c<hi) aOpen++;
      if (f>=0 && f>=lo && f<hi) { aFix++; fixH.push(f-c); }
    }
  }
  return { opened, merged, cohortMerged, lead, runs, fails, aOpen, aFix, fixH };
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
  // Hard rule: never more than three digits in a delta badge.
  //   |p| < 1000        -> a percentage, at most 3 digits ("+999%", "-100%").
  //                        Negatives cannot pass -100% because now >= 0.
  //   p >= 1000         -> a percentage that large is noise ("+25200%"); the
  //                        multiplier is both shorter and clearer ("x253").
  //   multiplier > 999  -> clamp, so even that cannot spill to four digits.
  if (p >= 1000) {
    const x = Math.round(now/prev);
    return { t: x > 999 ? "\u00d7999+" : "\u00d7"+x, c:"up" };
  }
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

function drawBars(host, buckets, labels, names, colors, titles) {
  titles = titles || labels;
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
      p.setAttribute("aria-label",`${names[j]} ${titles[i]}: ${v}`);
      bindTip(p, [[names[j], v, colors[j]]], titles[i]);
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

/* ---------- day-aligned buckets ----------
   Bars are whole Eastern calendar days. They used to be twelve equal slices of
   the window, which on a 7-day view made each bar 14 hours wide -- so the
   labels repeated ("Mon Mon Tue Wed Wed Thu Thu Fri Fri Sat Sun Sun"), and
   each bar was named after the day it ENDED in. A bucket running Sat 13:00 to
   Sun 03:00 was therefore labelled "Sun", which is how 204 pull requests
   opened on Saturday came to sit under Sunday with Saturday reading empty. */

const ET_DAY = {timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"};
const etDayFmt = new Intl.DateTimeFormat("en-CA", ET_DAY);   // -> "2026-08-29"
const dayKeyOf = h => etDayFmt.format(new Date(Date.UTC(2020,0,1) + h*3600e3));

// Stepping a UTC date at noon means no daylight-saving shift can ever move the
// walk across a day boundary, which stepping at midnight would.
function dayKeysBetween(loH, hiH) {
  const end = dayKeyOf(hiH), keys = [];
  const [y,m,d] = dayKeyOf(loH).split("-").map(Number);
  const cur = new Date(Date.UTC(y, m-1, d, 12));
  for (let i=0; i<400; i++) {
    const k = etDayFmt.format(cur); keys.push(k);
    if (k === end) break;
    cur.setUTCDate(cur.getUTCDate()+1);
  }
  return keys;
}

// Cached per render: sparkFor() runs once per repository and would otherwise
// rebuild the same plan on every row.
let PLAN = null;

function bucketPlan() {
  const [lo, hi] = cut();
  const days = dayKeysBetween(lo, hi);
  // Whole days per bar, so a bar never straddles a midnight. Twelve bars is the
  // target width, not a rule -- 7 days gives 8 one-day bars, 90 gives 12 of
  // eight days each.
  const per = Math.ceil(days.length / 12);
  const n = Math.ceil(days.length / per);
  const idxOf = new Map(days.map((k,i) => [k, Math.floor(i/per)]));

  // Dated rather than named. Every window on offer spans more than one of some
  // weekday, so "Sat" would be ambiguous about which Saturday it meant -- and a
  // bar grouping several days has no single weekday to be named after.
  const asLabel = k => { const [y,m,d]=k.split("-").map(Number);
    return new Date(Date.UTC(y,m-1,d,12)).toLocaleDateString(undefined,
      {day:"numeric", month:"short", timeZone:"America/New_York"}); };
  const lab = [], range = [];
  for (let i=0; i<n; i++) {
    const first = days[i*per], last = days[Math.min((i+1)*per-1, days.length-1)];
    lab.push(asLabel(first));
    // The axis shows the bucket's first day for width, but a grouped bar covers
    // several -- so tooltips name the span rather than implying a single day.
    range.push(first === last ? asLabel(first) : asLabel(first)+" \u2013 "+asLabel(last));
  }
  return {n, per, idxOf, lab, range};
}

function timeBuckets() {
  const {n, idxOf, lab, range} = PLAN;
  const po=Array(n).fill(0), pm=Array(n).fill(0), ao=Array(n).fill(0), af=Array(n).fill(0);
  // Events outside the window are simply absent from idxOf, so the lookup is
  // also the window filter -- and the bars therefore sum to the tiles above.
  const put = (arr,h) => { const i = idxOf.get(dayKeyOf(h)); if (i !== undefined) arr[i]++; };
  for(const r of repos()){
    for(const [c,m] of r.pr_events){ put(po,c); if(m>=0) put(pm,m); }
    if(r.alerts) for(const [c,f] of r.alerts.events){ put(ao,c); if(f>=0) put(af,f); }
  }
  return {lab, range, po, pm, ao, af};
}

function sparkFor(r){
  const {n, idxOf, range} = PLAN, v=Array(n).fill(0);
  for(const [c] of r.pr_events){ const i=idxOf.get(dayKeyOf(c)); if(i!==undefined) v[i]++; }
  if(!v.some(Boolean)) return null;
  const top=Math.max(...v), NS="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(NS,"svg");
  svg.setAttribute("viewBox","0 0 64 17");svg.setAttribute("class","spark");
  svg.setAttribute("role","img");
  // "activity trend" described the picture rather than the data. Each row now
  // says whose activity it is and when it peaked, which is the one fact the
  // shape is meant to convey.
  svg.setAttribute("aria-label",
    `${r.name}: pull requests opened, peak ${top} on ${range[v.indexOf(top)]}`);
  // One hover target for the whole cell rather than n bars a few pixels wide --
  // the per-bucket counts are read out in the tooltip instead of being aimed at.
  bindTip(svg, v.map((x,i)=>[range[i], x, "var(--s1)"]).filter(([,x])=>x), r.name);
  const bw=(64-(n-1))/n;
  v.forEach((x,i)=>{ if(!x)return; const h=Math.max(x/top*17,1.5);
    const rc=document.createElementNS(NS,"rect");
    rc.setAttribute("x",(i*(bw+1)).toFixed(1));rc.setAttribute("y",(17-h).toFixed(1));
    rc.setAttribute("width",bw.toFixed(1));rc.setAttribute("height",h.toFixed(1));
    rc.setAttribute("rx","1");rc.setAttribute("fill","var(--s1)");svg.appendChild(rc); });
  return svg;
}

/* ── motion: count figures up, grow bars from zero ──────────────────
   Runs after every render pass, so it also fires when a filter redraws
   the page. Honours prefers-reduced-motion by snapping to the value. */
const RM_ = matchMedia("(prefers-reduced-motion: reduce)").matches;
function animateFigures(){
  document.querySelectorAll(".tile b").forEach(el=>{
    /* The value lives in the FIRST TEXT NODE; a .delta badge may follow it as
       a sibling element. Mutate only that node -- writing el.textContent would
       destroy the badge. */
    const node=el.firstChild;
    if(!node||node.nodeType!==3) return;
    const raw=node.nodeValue.trim();
    const m=raw.match(/^(-?[\d,]+(?:\.\d+)?)(.*)$/);
    if(!m) return;
    const to=parseFloat(m[1].replace(/,/g,"")), tail=m[2]||"";
    if(!isFinite(to)||RM_||el.dataset.done===raw) return;
    el.dataset.done=raw;
    const dec=(m[1].includes(".")?1:0), t0=performance.now();
    (function tick(t){
      const pr=Math.min(1,(t-t0)/900), e=1-Math.pow(1-pr,3);
      node.nodeValue=(to*e).toFixed(dec).replace(/\B(?=(\d{3})+(?!\d))/g,",")+tail;
      if(pr<1) requestAnimationFrame(tick); else node.nodeValue=raw;
    })(t0);
  });
  document.querySelectorAll(".hbt i").forEach((el,i)=>{
    const w=el.style.width;
    if(!w||el.dataset.grown) return;
    el.dataset.grown="1"; el.style.width="0";
    if(RM_){el.style.width=w;return;}
    setTimeout(()=>{el.style.width=w;}, 60+i*45);
  });
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
    if(c.help) th.title=c.help;
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
  PLAN = bucketPlan();
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
    ["PRs opened",now.opened,
      now.opened ? `last ${state.days}d · ${now.cohortMerged} merged, ${now.opened-now.cohortMerged} closed unmerged`
                 : `last ${state.days}d`,
      delta(now.opened,prev.opened)],
    ["PRs merged",now.merged,`merged in the last ${state.days}d`,delta(now.merged,prev.merged)],
    ["Open alerts",sev?sev.c+sev.h+sev.m+sev.l:"—",sev?`${sev.c} critical · ${sev.h} high`:"",null],
    ["Alert fix time",fmtDur(median(now.fixH)),`median · n=${now.fixH.length}`,null],
  ]);

  const b=timeBuckets();
  drawBars($("#chPR"),[b.po,b.pm],b.lab,["Opened","Merged"],["var(--s1)","var(--s2)"],b.range);
  drawBars($("#chAL"),[b.ao,b.af],b.lab,["Raised","Resolved"],["var(--s1)","var(--s2)"],b.range);

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
    {key:"status",label:"Status",val:f=>f.fixed_h?1:0,render:f=>{
      if(!f.fixed_h){const p=el("span","pill critical");p.appendChild(el("b",null,"✕"));
        p.appendChild(document.createTextNode("still failing"));return p;}
      const p=el("span","pill good");p.appendChild(el("b",null,"✓"));
      p.appendChild(document.createTextNode("fixed"));return p;}},
    {key:"cause",label:"Broken by",val:f=>f.pr?f.pr.title:f.msg,render:f=>{const s=el("span");
      if(f.pr){s.appendChild(link("#"+f.pr.num,f.pr.url,"mono"));s.appendChild(document.createTextNode(" "+f.pr.title));}
      else{s.appendChild(el("span","mono dim",f.sha));s.appendChild(document.createTextNode(" "+f.msg));}return s;}},
    {key:"fixedby",label:"Fixed by",val:f=>f.fixed_h?(f.fixed_by?f.fixed_by.num:1):-1,render:f=>{
      if(!f.fixed_h) return el("span","dim","— not yet");
      const s=el("span");
      if(f.fixed_by){s.appendChild(link("#"+f.fixed_by.num,f.fixed_by.url,"mono"));
        s.appendChild(document.createTextNode(" "+f.fixed_by.title.slice(0,38)));}
      else s.appendChild(link(f.fixed_sha,f.fixed_url,"mono"));
      return s;}},
    {key:"when",label:"Failed",cls:"num mono dim",val:f=>-f.at_h,render:f=>{
      const a=link(ageH(f.at_h)+" ago",f.url); a.title=absTime(f.at_h); return a;}},
  ],"status");

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
    {key:"open",label:"Open PRs",cls:"num",val:r=>r.open_prs.length,render:r=>r.open_prs.length||"—"},
    {key:"o",label:"PRs opened",cls:"num dim",val:r=>r._o,render:r=>r._o},
    {key:"m",label:"PRs merged",cls:"num dim",val:r=>r._m,render:r=>r._m},
    {key:"lead",label:"Median merge time",help:"Median time from a pull request being opened to being merged, within the selected window. Blank when nothing merged.",cls:"num mono",val:r=>r._lead??1e9,render:r=>fmtDur(r._lead)},
    {key:"fr",label:"CI failure rate",help:"Share of completed CI runs on the default branch that failed, within the selected window.",cls:"num mono",val:r=>r._fr??-1,render:r=>r._fr==null?"—":r._fr.toFixed(0)+"%"},
    {key:"ci",label:"CI",val:r=>r.ci_latest==="failure"?0:1,render:r=>ciPill(r.ci_latest)},
    {key:"alerts",label:"Alerts",cls:"num",val:r=>r._sev?r._sev.c*100+r._sev.h*10+r._sev.m:-1,
      render:r=>{ if(!r._sev)return el("span","dim","—"); const s=el("span","sevwrap");
        [["c",r._sev.c],["h",r._sev.h],["m",r._sev.m],["l",r._sev.l]].forEach(([k,v])=>{
          if(v){const c=el("span","sev "+k,v);
            c.title={c:"critical",h:"high",m:"medium",l:"low"}[k]+": "+v; s.appendChild(c);} });
        return s.childNodes.length?s:el("span","dim","0"); }},
    {key:"cq",label:"CodeQL",cls:"num",val:r=>r._cq??-1,render:r=>r._cq==null?el("span","dim","—"):String(r._cq)},
    {key:"spark",label:"PR activity",help:"Pull requests opened per day across the selected window, on the same buckets as the Activity charts (days are grouped into blocks on longer windows). Shape only \u2014 each row is scaled to its own busiest day, so heights are not comparable between repositories. Hover for the counts; the window total is in the PRs opened column.",val:r=>r._o,render:r=>sparkFor(r)||el("span","dim","—")},
    {key:"pushed",label:"Last commit",help:"Time since the most recent push to any branch. Hover the value for the exact timestamp.",cls:"num mono dim",val:r=>-r.pushed_h,render:r=>{const sp=el("span",null,ageH(r.pushed_h)+" ago");sp.title=absTime(r.pushed_h);return sp;}},
  ],"alerts");

  paintRT();
  paintCQ();
  $("#chip").textContent=`${rs.length} repo${rs.length===1?"":"s"} · ${openPRs.length} open PR${openPRs.length===1?"":"s"}`;
  animateFigures();
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

function paintRT(){
  const [lo,hi]=cut();
  let secs=0, runs=0, macSecs=0;
  const byRepo=[], byWf={};
  for(const r of repos()){
    let s=0,n=0;
    for(const [c,,d] of (r.run_events||[])) if(c>=lo&&c<hi){ s+=(d||0); n++; }
    if(n){ byRepo.push([r.name,s,r.runner_os]); }
    secs+=s; runs+=n;
    if(r.runner_os==="macos") macSecs+=s;
    for(const [w,t] of Object.entries(r.wf_time||{})) byWf[w]=(byWf[w]||0)+t;
  }
  const fmt=x=> x<60?Math.round(x)+"s" : x<3600?(x/60).toFixed(1)+"m" : (x/3600).toFixed(1)+"h";
  /* GitHub bills runner minutes at a different rate per OS: Linux 1x,
     Windows 2x, macOS 10x. Ranking by RAW seconds therefore hides where the
     spend actually goes -- a macOS repo can sit mid-table on raw time while
     being the single largest consumer once weighted. Rank by the billable
     equivalent and show the multiplier, so the ordering means something. */
  const RATE={ubuntu:1,linux:1,windows:2,macos:10};
  const rateOf=os=>RATE[os]||1;
  const billable=byRepo.reduce((a,[,v,os])=>a+v*rateOf(os),0);
  paintTiles($("#rt"),[
    ["Runner time",fmt(secs),`across ${runs} run${runs===1?"":"s"}`,null],
    ["Billable equivalent",fmt(billable),
      billable>secs?`${(billable/secs).toFixed(1)}x raw · Linux 1x, macOS 10x`:"all Linux, 1x",null],
    ["Runs",runs,`in the last ${state.days}d`,null],
    ["Average run",runs?fmt(secs/runs):"—","",null],
    ["macOS time",macSecs?fmt(macSecs):"—",macSecs?`${fmt(macSecs*10)} billable`:"none",null],
  ]);
  const wRepo=byRepo.map(([n,v,os])=>[n,v,os,v*rateOf(os)]);
  const wtop=Math.max(...wRepo.map(x=>x[3]),1);
  hbars($("#rtRepo"), wRepo.sort((a,b)=>b[3]-a[3])
    .map(([n,v,os,w])=>[n+(rateOf(os)>1?`  ${os} ${rateOf(os)}x · ${fmt(v)} raw`:""),
      fmt(w), rateOf(os)>1?"warn":"acc",
      `https://github.com/${OWNER}/${n}/actions`, w/wtop]));
  const wf=Object.entries(byWf).filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]).slice(0,6);
  const wtop=Math.max(...wf.map(x=>x[1]),1);
  hbars($("#rtWf"), wf.map(([n,v])=>[n,fmt(v),"acc",null,v/wtop]));
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
  /* Secret scanning: repos where the API answered at all are "covered";
     a null means the feature is off or the token cannot see it. Reporting
     coverage matters as much as the count -- zero findings across zero
     scanned repos is not the same as zero findings across twelve. */
  const secAll=repos().filter(r=>r.secrets);
  const secOn=secAll.filter(r=>r.secrets.status==="enabled");
  const secOff=secAll.filter(r=>r.secrets.status==="disabled");
  const secN=secOn.reduce((a,r)=>a+r.secrets.total,0);
  /* Zero findings across zero scanned repos is not the same as zero findings
     across twelve, so the caption reports coverage, and an unscanned repo is
     called out rather than silently counted as clean. */
  const secCov=secOff.length
    ? `${secOn.length} scanned · ${secOff.length} not scanning`
    : `${secOn.length}/${repos().length} repos scanned`;
  paintTiles($("#sq"),[
    ["Quality gates",`${rs.length-failing}/${rs.length}`,"passing",null],
    ["Coverage",(covN?covW/covN:0).toFixed(1)+"%","weighted by lines",null],
    ["Vulnerabilities",vuln,"all code, not just new",null],
    ["Bugs",bugs,"",null],
    ["Code smells",smell,fmtDebt(debt)+" estimated debt",null],
    ["CodeQL",cq,"open security alerts",null],
    ["Exposed secrets",secOn.length?secN:"—",secAll.length?secCov:"scanning unavailable",null],
  ]);

  sortable($("#tSonar"),rs.map(r=>({...r,
    _g:r.sonar.gate,_c:r.sonar.measures.coverage==null?null:num(r,"coverage"),
    _n:num(r,"ncloc"),_v:num(r,"vulnerabilities"),_b:num(r,"bugs"),
    _s:num(r,"code_smells"),_d:num(r,"duplicated_lines_density"),
    _t:num(r,"sqale_index"),_q:r.codeql?r.codeql.total:null})),[
    {key:"name",label:"Repo",cls:"mono",val:r=>r.name,render:r=>link(r.name,`https://sonarcloud.io/project/overview?id=${OWNER}_${r.name}`)},
    {key:"gate",label:"Gate",help:"SonarCloud quality gate. It judges NEW code only \u2014 a repository can pass while carrying findings on existing code.",val:r=>r._g==="ERROR"?0:r._g==="OK"?2:1,render:r=>{
      const m={OK:["good","✓","passing"],ERROR:["critical","✕","failing"]}[r._g]||["mute","–","no baseline"];
      const s=el("span","pill "+m[0]); s.appendChild(el("b",null,m[1]));
      s.appendChild(document.createTextNode(m[2])); return s;}},
    {key:"cov",label:"Coverage",help:"Line coverage as SonarCloud measures it. May differ from the CI figure when sonar.sources covers files the test run does not.",cls:"num mono",val:r=>r._c??-1,render:r=>r._c==null?el("span","dim","—"):r._c.toFixed(1)+"%"},
    {key:"ncloc",label:"Lines",cls:"num mono dim",val:r=>r._n,render:r=>r._n.toLocaleString()},
    {key:"vuln",label:"Vulnerabilities",help:"Open SonarCloud vulnerabilities across ALL code, not only new code.",cls:"num",val:r=>r._v,render:r=>r._v?el("span","sev h",r._v):el("span","dim","0")},
    {key:"bugs",label:"Bugs",cls:"num",val:r=>r._b,render:r=>r._b?el("span","sev m",r._b):el("span","dim","0")},
    {key:"smells",label:"Smells",cls:"num mono dim",val:r=>r._s,render:r=>String(r._s)},
    {key:"dup",label:"Duplication",help:"Percentage of lines SonarCloud considers duplicated.",cls:"num mono dim",val:r=>r._d,render:r=>r._d.toFixed(1)},
    {key:"debt",label:"Tech debt",help:"SonarCloud\u2019s estimated effort to remediate all code smells in this repository.",cls:"num mono dim",val:r=>r._t,render:r=>fmtDebt(r._t)},
    {key:"codeql",label:"CodeQL",cls:"num",val:r=>r._q??-1,render:r=>r._q==null?el("span","dim","—"):String(r._q)},
  ],"vuln");

  hbars($("#sqCov"),rs.filter(r=>r.sonar.measures.coverage!=null)
    .sort((a,b)=>num(b,"coverage")-num(a,"coverage"))
    .map(r=>[r.name,+num(r,"coverage").toFixed(1),
      num(r,"coverage")<40?"bad":num(r,"coverage")<70?"warn":"good",
      `https://sonarcloud.io/component_measures?id=${OWNER}_${r.name}&metric=coverage`]));
  hbars($("#sqIss"),rs.map(r=>[r.name,num(r,"vulnerabilities")+num(r,"bugs"),
      num(r,"vulnerabilities")?"bad":"warn",
      `https://sonarcloud.io/project/issues?id=${OWNER}_${r.name}&resolved=false`])
    .filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]));
}
function hbars(host,rows){
  host.innerHTML="";
  if(!rows.length){ host.appendChild(el("p","empty","Nothing to show.")); return; }
  const nums=rows.map(r=>typeof r[1]==="number"?r[1]:0);
  const top=Math.max(...nums,1);
  rows.forEach(([label,val,cls,href,frac])=>{ const d=el("div","hb");
    const l=el("span","hbl mono"); l.appendChild(href?link(label,href):document.createTextNode(label));
    const t=el("span","hbt"); const i=el("i",cls);
    const w = frac!=null ? frac*100 : (typeof val==="number" ? val/top*100 : 0);
    i.style.width=Math.max(w,2).toFixed(1)+"%";
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

/* ---------- on-demand rebuild ----------
   GitHub Pages is static: nothing here can start a workflow without credentials.
   The only two options are a server holding a secret, or the viewer's own token.
   We take the second — the token is typed by the user, lives in localStorage,
   and never touches the repository or the rendered HTML. */
const RB = {
  repo: OWNER + "/dev-dashboard",
  wf: "dashboard.yml",
  key: "dashboard_pat",
  busy: false,
  get token() { try { return localStorage.getItem(RB.key) || ""; } catch (e) { return ""; } },
  set token(v) { try { v ? localStorage.setItem(RB.key, v) : localStorage.removeItem(RB.key); } catch (e) {} }
};
const rbBtn = $("#rebuild"), rbStat = $("#rbstat"), rbForget = $("#rbforget"),
      patWrap = $("#patwrap"), patIn = $("#pat");
const sleep = ms => new Promise(r => setTimeout(r, ms));

let ticker = null;
function rbLabel(txt, t0) {
  rbBtn.textContent = txt;
  clearInterval(ticker);
  if (t0) { const tick = () => rbSay(Math.round((Date.now()-t0)/1000) + "s");
            tick(); ticker = setInterval(tick, 1000); }
}
function rbSay(txt, bad) { rbStat.textContent = txt || ""; rbStat.className = "rbstat" + (bad ? " bad" : ""); }
function rbIdle() { RB.busy = false; rbBtn.disabled = false; clearInterval(ticker);
                    rbBtn.textContent = "Rebuild now"; rbForget.hidden = !RB.token; }
function showPat(msg) {
  patWrap.hidden = false; rbSay(msg || "", !!msg);
  patIn.value = ""; patIn.focus();
}

async function gh(path, opts) {
  opts = opts || {};
  const r = await fetch("https://api.github.com" + path, {
    method: opts.method || "GET",
    body: opts.body,
    // fetch would otherwise label a string body text/plain
    headers: Object.assign({ "Accept": "application/vnd.github+json",
               "Authorization": "Bearer " + RB.token,
               "X-GitHub-Api-Version": "2022-11-28" },
               opts.body ? { "Content-Type": "application/json" } : {})
  });
  if (r.status === 401) { RB.token = ""; throw new Error("Token rejected — create a new one."); }
  if (r.status === 403) { RB.token = ""; throw new Error("Token lacks Actions: write on this repo."); }
  if (r.status === 404) { RB.token = ""; throw new Error("Token can't see dev-dashboard — check its repository access."); }
  if (!r.ok) throw new Error("GitHub returned " + r.status);
  return r.status === 204 ? null : r.json();
}

async function rebuild() {
  if (RB.busy) return;
  if (!RB.token) { showPat(); return; }
  patWrap.hidden = true;
  RB.busy = true; rbBtn.disabled = true; rbForget.hidden = true;
  const t0 = Date.now();
  rbLabel("Starting…", t0);
  try {
    await gh("/repos/" + RB.repo + "/actions/workflows/" + RB.wf + "/dispatches",
             { method: "POST", body: JSON.stringify({ ref: "main" }) });

    // The dispatch endpoint returns 204 with no body, so the run has to be
    // found by its creation time rather than by an id we were handed.
    let run = null;
    for (let i = 0; i < 30 && !run; i++) {
      rbLabel("Queued…", t0);
      await sleep(2000);
      const d = await gh("/repos/" + RB.repo + "/actions/workflows/" + RB.wf +
                         "/runs?event=workflow_dispatch&per_page=5");
      run = (d.workflow_runs || []).find(x => Date.parse(x.created_at) >= t0 - 20000);
    }
    if (!run) throw new Error("Run never appeared — check Actions.");

    while (run.status !== "completed") {
      rbLabel(run.status === "queued" ? "Queued…" : "Building…", t0);
      await sleep(3000);
      run = await gh("/repos/" + RB.repo + "/actions/runs/" + run.id);
    }
    clearInterval(ticker);

    if (run.conclusion === "success") {
      rbLabel("Reloading…"); rbSay("");
      // The deploy is the last step of the same job, so the run finishing means
      // the new page is live. The query string defeats the Pages CDN cache.
      await sleep(1500);
      location.replace(location.pathname + "?t=" + Date.now());
      return;
    }
    rbSay("", true);
    rbStat.innerHTML = "Build " + run.conclusion + " — " +
      '<a href="' + run.html_url + '" target="_blank" rel="noopener">see the run</a>';
    rbStat.className = "rbstat bad";
    rbIdle();
  } catch (e) {
    rbIdle();
    if (!RB.token) showPat(e.message); else rbSay(e.message, true);
  }
}

rbBtn.addEventListener("click", rebuild);
rbForget.addEventListener("click", () => { RB.token = ""; rbIdle(); rbSay("Token removed."); });
$("#patcancel").addEventListener("click", () => { patWrap.hidden = true; rbSay(""); });
$("#patsave").addEventListener("click", () => {
  const v = patIn.value.trim();
  if (!v) { patIn.focus(); return; }
  RB.token = v; patIn.value = ""; patWrap.hidden = true; rebuild();
});
patIn.addEventListener("keydown", e => { if (e.key === "Enter") $("#patsave").click(); });
rbForget.hidden = !RB.token;
"""

E = html.escape


def generated_stamp(D):
    """Human-readable build time in Eastern time, with a UTC fallback."""
    try:
        from zoneinfo import ZoneInfo
        _et = _dt.fromisoformat(D["generated"]).astimezone(ZoneInfo("America/New_York"))
        # %Z yields EST or EDT automatically, so daylight saving is handled by the
        # tz database rather than a hard-coded offset.
        return _et.strftime("%d %b %Y, %-I:%M %p %Z")
    except Exception:
        return D["generated"][:16].replace("T", " ") + " UTC"


def token_note(D):
    """Countdown to build-token expiry, or "" when the collector did not report one."""
    te = D.get("token_expiry")
    if not te:
        return ""
    try:
        d = datetime.strptime(te.split(" ")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        left = (d - datetime.now(timezone.utc)).days
        return (f'<p class="note">{"⚠ " if left < 21 else ""}Build token '
                f'{"expires in <b>%d days</b>" % left if left < 21 else "valid for %d more days" % left} '
                f'({d.strftime("%d %b %Y")}).</p>')
    except Exception:
        return ""


def build_html(D):
    """Render a data.json payload into the complete self-contained page."""
    OWNER = D["owner"]
    gen = generated_stamp(D)
    tok = token_note(D)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(OWNER)} — engineering dashboard</title>
<meta name="description" content="Open PRs, delivery metrics, security alerts and code quality across every repository.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Public+Sans:wght@400;500;600;700;800&display=swap">
<style>{CSS}</style></head><body>
<div class="wrap">
<header><h1>{E(OWNER)}</h1><span class="chip mono" id="chip"></span><span class="rbwrap"><span class="rbstat" id="rbstat" role="status" aria-live="polite"></span><button class="rbkey" id="rbforget" type="button" hidden>Forget token</button><button class="rebuild" id="rebuild" type="button">Rebuild now</button></span></header>
<p class="sub">Every repository, discovered automatically · rebuilt {E(gen)} · filters apply to everything below</p>

<div class="pat" id="patwrap" hidden>
  <p><b>One-time setup.</b> Starting a build from this page needs a GitHub token —
  GitHub Pages is static, so the page has no server of its own to sign the request.</p>
  <p>Create a <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">fine-grained
  token</a> scoped to <b>only</b> the <code>dev-dashboard</code> repository, with a single permission:
  <b>Actions &rarr; Read and write</b>. Nothing else.</p>
  <div class="patrow">
    <input type="password" id="pat" placeholder="github_pat_&hellip;" autocomplete="off" spellcheck="false" aria-label="GitHub token">
    <button type="button" id="patsave">Save &amp; rebuild</button>
    <button type="button" id="patcancel" class="ghost">Cancel</button>
  </div>
  <p class="patnote">The token is kept in this browser only (<code>localStorage</code>) — it is never committed,
  never rendered into the page, and never sent anywhere but <code>api.github.com</code>. Note that every page under
  <code>{E(OWNER).lower()}.github.io</code> shares one origin and can read it. Remove it with <b>Forget token</b>.</p>
</div>

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
    <p class="cap">Opened vs merged. Each bar is a whole day in Eastern time, grouped into blocks when the window is long.</p>
    <div id="chPR"></div>
    <div class="legend"><span><i style="background:var(--s1)"></i>Opened</span><span><i style="background:var(--s2)"></i>Merged</span></div></div>
  <div class="panel"><h2 style="margin:0 0 2px">Dependabot alerts</h2>
    <p class="cap">Raised vs resolved (fixed or dismissed), on the same day bars.</p>
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

<h2>Runner time</h2>
<p class="cap">Elapsed wall-clock across CI runs in the selected window, derived from run timestamps. This is <em>not</em> billable time: standard GitHub-hosted runners are free and unmetered on public repositories, and GitHub reports <code>billable = 0</code> for every repo here. It is shown because the shape still matters &mdash; and because macOS runners bill at 10&times; the moment a repo goes private.</p>
<div class="tiles" id="rt"></div>
<div class="two">
  <div class="panel"><h2 style="margin:0 0 2px">Time by repository</h2><p class="cap">Longest first.</p><div id="rtRepo"></div></div>
  <div class="panel"><h2 style="margin:0 0 2px">Time by workflow</h2><p class="cap">Which workflow consumes the most.</p><div id="rtWf"></div></div>
</div>

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
<footer>Rebuilt hourly by GitHub Actions, published as a Pages artifact — no commits, no notifications.
GitHub throttles frequent schedules on free public repositories, so hourly is the honest cadence; <b>Rebuild now</b> at the top of the page starts one immediately and reloads when it lands (or <code>gh workflow run dashboard.yml -R {E(OWNER)}/dev-dashboard</code>) for an immediate rebuild.
180 days of events ship inline, so every filter and sort is instant and needs no network. New repositories appear with no configuration.</footer>
</div>
<div id="tip" role="status" aria-live="polite"></div>
<script>window.__DATA__={json.dumps(D, separators=(",", ":"))};</script>
<script>{JS}</script>
</body></html>"""


def main():
    with open(DATA_PATH) as f:
        D = json.load(f)
    HTML = build_html(D)
    with open(OUT_PATH, "w") as f:
        f.write(HTML)
    print(f"rendered {len(HTML)} bytes")


if __name__ == "__main__":
    main()
