#!/usr/bin/env python3
"""Render data.json into index.html. Pure formatting — no network."""
import json, os, statistics, html
from collections import defaultdict
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(__file__)
D = json.load(open(os.path.join(HERE, "..", "data.json")))
OWNER, REPOS, WIN = D["owner"], D["repos"], D["window_days"]
NOW = datetime.fromisoformat(D["generated"])
E = html.escape


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def dur(h):
    if h is None:
        return "—"
    if h < 1:
        return f"{int(h*60)}m"
    if h < 48:
        return f"{h:.1f}h"
    return f"{h/24:.1f}d"


def age(iso):
    d = NOW - ts(iso)
    return f"{d.days}d" if d.days else (f"{d.seconds//3600}h" if d.seconds >= 3600 else f"{max(d.seconds//60,1)}m")


# ── aggregate ─────────────────────────────────────────────────────────────────
opened = [ts(t) for r in REPOS for t in r["opened_recent"]]
merged = [ts(t) for r in REPOS for t in r["merged_recent"]]
lead = [h for r in REPOS for h in r["lead_hours"]]
restore = [h for r in REPOS for h in r["restore_hours"]]
runs_tot = sum(r["runs_total"] for r in REPOS)
runs_bad = sum(r["runs_failed"] for r in REPOS)
open_prs = [dict(p, repo=r["name"]) for r in REPOS for p in r["open_prs"]]
failing = sorted([f for r in REPOS for f in r["failing_runs"]], key=lambda x: x["at"], reverse=True)[:12]
have_alerts = [r for r in REPOS if r["alerts"] is not None]
alerts_missing = len(have_alerts) < len(REPOS)

sev_tot = defaultdict(int)
for r in have_alerts:
    for k, v in r["alerts"]["sev"].items():
        sev_tot[k] += v
fix_hours = [h for r in have_alerts for h in r["alerts"]["fix_hours"]]

weeks = [(NOW - timedelta(days=7 * i)).date() for i in range(11, -1, -1)]
wk_open = [sum(1 for t in opened if (NOW.date() - t.date()).days // 7 == 11 - i) for i in range(12)]
wk_merge = [sum(1 for t in merged if (NOW.date() - t.date()).days // 7 == 11 - i) for i in range(12)]

months = sorted({m for r in have_alerts for m in
                 list(r["alerts"]["opened_by_month"]) + list(r["alerts"]["fixed_by_month"])})[-8:]
m_open = [sum(r["alerts"]["opened_by_month"].get(m, 0) for r in have_alerts) for m in months]
m_fix = [sum(r["alerts"]["fixed_by_month"].get(m, 0) for r in have_alerts) for m in months]

deploy_wk = len(merged) / max(WIN / 7, 1)
cfr = 100 * runs_bad / runs_tot if runs_tot else 0


# ── charts ────────────────────────────────────────────────────────────────────
def bars(series, labels, colors, names, h=132, gap=2, pad_l=30):
    """Grouped bars. Rounded data-ends anchored to the baseline; a 2px surface
    gap between adjacent fills; <title> gives every mark a native tooltip."""
    n, k = len(labels), len(series)
    top = max([max(s) for s in series if s] + [1])
    w, step = 640, (640 - pad_l) / max(n, 1)
    bw = max((step - gap * (k + 1)) / k, 3)
    out = [f'<svg viewBox="0 0 {w} {h+30}" class="chart" role="img" aria-label="{E(" and ".join(names))}">']
    for gl in range(4):
        y = h - h * gl / 3
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l-6}" y="{y+3.5:.1f}" class="ax" text-anchor="end">{round(top*gl/3)}</text>')
    for i in range(n):
        for j, s in enumerate(series):
            v = s[i]
            bh = (v / top) * h if top else 0
            x = pad_l + i * step + gap + j * (bw + gap)
            if bh > 0:
                r = min(4, bw / 2, bh)
                out.append(
                    f'<path d="M{x:.1f},{h} v{-(bh-r):.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{-r:.1f} '
                    f'h{bw-2*r:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} V{h} z" fill="{colors[j]}">'
                    f'<title>{E(names[j])} · {E(labels[i])}: {v}</title></path>')
        if n <= 12 or i % 2 == 0:
            out.append(f'<text x="{pad_l+i*step+step/2:.1f}" y="{h+16}" class="ax" text-anchor="middle">{E(labels[i])}</text>')
    out.append("</svg>")
    return "".join(out)


def legend(names, colors):
    return '<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{E(n)}</span>' for n, c in zip(names, colors)) + "</div>"



def spark(vals, w=62, h=16):
    """Thin activity bars. Sparklines carry shape, not exact values — the row's
    numeric columns already give the precise counts."""
    if not any(vals):
        return '<span class="dim" style="font-size:11px">—</span>'
    top = max(vals)
    n = len(vals)
    bw = (w - (n - 1)) / n
    out = [f'<svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="activity trend">']
    for i, v in enumerate(vals):
        bh = max((v / top) * h, 1) if v else 0
        if bh:
            x = i * (bw + 1)
            out.append(f'<rect x="{x:.1f}" y="{h-bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="1" fill="var(--s1)"/>')
    out.append("</svg>")
    return "".join(out)


def weekly(repo, key="opened_recent", n=12):
    out = [0] * n
    for t in repo[key]:
        d = (NOW.date() - ts(t).date()).days // 7
        if 0 <= d < n:
            out[n - 1 - d] += 1
    return out


def attention(r):
    """Sort key: things needing action first, then most active."""
    a = r["alerts"] or {"sev": {}}
    bad = 2 if r["ci_latest"] == "failure" else 0
    bad += min(a["sev"].get("critical", 0) + a["sev"].get("high", 0), 5)
    bad += 1 if r["open_prs"] else 0
    return (-bad, -len(r["opened_recent"]))


STATUS = {"success": ("good", "✓", "passing"), "failure": ("critical", "✕", "failing"),
          "cancelled": ("warning", "•", "cancelled"), "in_progress": ("warning", "◐", "running"),
          "queued": ("warning", "◔", "queued"), "none": ("mute", "–", "no CI")}


def ci_pill(c):
    cls, icon, label = STATUS.get(c, ("warning", "•", c))
    return f'<span class="pill {cls}"><b>{icon}</b>{label}</span>'


pr_rows = "".join(
    f'<tr><td class="mono"><a href="https://github.com/{OWNER}/{E(p["repo"])}">{E(p["repo"])}</a></td>'
    f'<td class="num mono"><a href="{p["url"]}">#{p["num"]}</a></td>'
    f'<td>{E(p["title"][:74])}{"…" if len(p["title"])>74 else ""}'
    f'{" <span class=\'pill mute\'>draft</span>" if p["draft"] else ""}</td>'
    f'<td class="mono dim">{E(p["author"])}</td><td class="num mono dim">{age(p["created"])}</td></tr>'
    for p in sorted(open_prs, key=lambda x: x["created"])
) or '<tr><td colspan="5" class="empty">No open pull requests in any repository.</td></tr>'

fail_rows = "".join(
    f'<tr><td class="mono"><a href="https://github.com/{OWNER}/{E(f["repo"])}">{E(f["repo"])}</a></td>'
    f'<td class="dim">{E(f["wf"])}</td>'
    f'<td>{(f"<a href=\"{f['pr']['url']}\" class=\"mono\">#{f['pr']['num']}</a> " + E(f['pr']['title'][:46])) if f["pr"] else f"<span class=\"mono dim\">{E(f['sha'])}</span> " + E(f["msg"][:46])}</td>'
    f'<td class="num mono dim"><a href="{f["url"]}">{age(f["at"])}</a></td></tr>'
    for f in failing
) or f'<tr><td colspan="4" class="empty">No failed runs on any default branch in {WIN} days.</td></tr>'


def repo_row(r):
    a = r["alerts"]
    lt = statistics.median(r["lead_hours"]) if r["lead_hours"] else None
    fr = f'{100*r["runs_failed"]/r["runs_total"]:.0f}%' if r["runs_total"] else "—"
    sev = "—" if a is None else (" ".join(
        f'<span class="sev {k}">{v}</span>' for k, v in a["sev"].items() if v) or '<span class="dim">0</span>')
    return (f'<tr><td class="mono"><a href="{r["url"]}">{E(r["name"])}</a></td>'
            f'<td class="dim">{E(r["lang"])}</td>'
            f'<td class="num">{len(r["open_prs"]) or "<span class=\'dim\'>0</span>"}</td>'
            f'<td class="num dim">{len(r["opened_recent"])}</td>'
            f'<td class="num dim">{len(r["merged_recent"])}</td>'
            f'<td class="num mono">{dur(lt)}</td>'
            f'<td class="num mono">{fr}</td>'
            f'<td>{ci_pill(r["ci_latest"])}</td>'
            f'<td class="num">{sev}</td>'
            f'<td>{spark(weekly(r))}</td>'
            f'<td class="num mono dim">{age(r["pushed"])}</td></tr>')


_missing = [r["name"] for r in REPOS if r["alerts"] is None]
alerts_note = (
    '<p class="note">No alert data for <b>' + ", ".join(map(E, _missing)) +
    '</b> — Dependabot alerts are switched off on those repositories '
    '(the API returns 403 even to a fully-scoped token). Enable them under '
    'Settings → Code security to include them here.</p>') if _missing else ""

tok_note = ""
_te = D.get("token_expiry")
if _te:
    try:
        _d = datetime.strptime(_te.split(" ")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        _left = (_d - NOW).days
        if _left < 21:
            tok_note = (f'<p class="note">⚠ The build token expires in <b>{_left} days</b> '
                        f'({_d.strftime("%d %b %Y")}). After that the alert columns read n/a '
                        f'until <code>DASHBOARD_TOKEN</code> is replaced.</p>')
        else:
            tok_note = (f'<p class="note">Build token valid for {_left} more days '
                        f'(expires {_d.strftime("%d %b %Y")}).</p>')
    except Exception:
        pass

C1L, C2L = "#2a78d6", "#eb6834"
HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(OWNER)} — engineering dashboard</title>
<meta name="description" content="Open PRs, delivery metrics and security alerts across every {E(OWNER)} repository.">
<style>
:root{{color-scheme:light;--bg:#F4F6F8;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--ink3:#8b8a85;
--line:#E2E6EC;--accent:#2a78d6;--s1:{C1L};--s2:{C2L};
--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--mute:#6B7280;
--goodbg:#E4F4E4;--warnbg:#FCF3DC;--critbg:#FAE4E4;--mutebg:#EDEFF3;--grid:#E8ECF1}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{color-scheme:dark;
--bg:#101318;--card:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--ink3:#8a8a84;--line:#2a2b30;
--accent:#3987e5;--s1:#3987e5;--s2:#d95926;--goodbg:#16301a;--warnbg:#2E2617;--critbg:#301A1A;
--mutebg:#22242A;--grid:#26282e}}}}
:root[data-theme=dark]{{color-scheme:dark;--bg:#101318;--card:#1a1a19;--ink:#fff;--ink2:#c3c2b7;
--ink3:#8a8a84;--line:#2a2b30;--accent:#3987e5;--s1:#3987e5;--s2:#d95926;--goodbg:#16301a;
--warnbg:#2E2617;--critbg:#301A1A;--mutebg:#22242A;--grid:#26282e}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:32px 22px 72px}}
h1{{font-size:1.45rem;font-weight:700;letter-spacing:-.02em;margin:0 0 3px}}
.sub{{color:var(--ink2);font-size:13.5px;margin:0 0 24px}}
h2{{font-size:.95rem;font-weight:600;margin:32px 0 4px;letter-spacing:-.01em}}
.cap{{font-size:12.5px;color:var(--ink3);margin:0 0 12px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:11px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:14px 16px}}
.tile b{{display:block;font-size:26px;font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.2}}
.tile span{{font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.07em;font-weight:600}}
.tile em{{font-style:normal;font-size:11.5px;color:var(--ink3);display:block;margin-top:2px}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:16px 18px}}
.chart{{width:100%;height:auto;display:block}}
.grid{{stroke:var(--grid);stroke-width:1}}
.ax{{fill:var(--ink3);font-size:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
.legend{{display:flex;gap:15px;margin-top:9px;font-size:12px;color:var(--ink2)}}
.legend i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:7px;overflow:hidden}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink3);
font-weight:600;padding:9px 12px;border-bottom:1px solid var(--line);background:var(--bg)}}
td{{padding:8px 12px;border-bottom:1px solid var(--line);font-size:13.5px}}
tr:last-child td{{border-bottom:0}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.dim{{color:var(--ink3)}}
.empty{{text-align:center;color:var(--ink3);padding:24px}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
.pill{{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;padding:2px 8px;border-radius:20px}}
.pill b{{font-size:10px}}
.pill.good{{background:var(--goodbg);color:var(--good)}}.pill.critical{{background:var(--critbg);color:var(--critical)}}
.pill.warning{{background:var(--warnbg);color:var(--warning)}}.pill.mute{{background:var(--mutebg);color:var(--mute)}}
.sev{{display:inline-block;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;padding:1px 5px;border-radius:4px;margin-left:3px}}
.sev.critical,.sev.high{{background:var(--critbg);color:var(--critical)}}
.sev.medium{{background:var(--warnbg);color:var(--warning)}}.sev.low{{background:var(--mutebg);color:var(--mute)}}
.spark{{width:62px;height:16px;display:block}}
.note{{font-size:12.5px;color:var(--ink3);margin:10px 0 0}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;background:var(--mutebg);padding:1px 4px;border-radius:3px}}
footer{{margin-top:36px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--ink3)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:820px){{.two{{grid-template-columns:1fr}}}}
.scroll{{overflow-x:auto}}
</style></head><body><div class="wrap">
<h1>{E(OWNER)}</h1>
<p class="sub">Every repository, discovered automatically · {WIN}-day window · rebuilt {NOW.strftime('%Y-%m-%d %H:%M UTC')}</p>

<h2>Delivery</h2>
<p class="cap">DORA proxies. There is no deploy pipeline here, so <em>merge to default branch</em> stands in for deployment and default-branch CI failure for change failure.</p>
<div class="tiles">
  <div class="tile"><b>{deploy_wk:.1f}</b><span>Deploy frequency</span><em>merges / week</em></div>
  <div class="tile"><b>{dur(statistics.median(lead) if lead else None)}</b><span>Lead time</span><em>median, open → merge (n={len(lead)})</em></div>
  <div class="tile"><b>{cfr:.1f}%</b><span>Change failure rate</span><em>{runs_bad} of {runs_tot} runs</em></div>
  <div class="tile"><b>{dur(statistics.median(restore) if restore else None)}</b><span>Time to restore</span><em>median (n={len(restore)})</em></div>
</div>

<h2>Activity</h2>
<div class="tiles">
  <div class="tile"><b>{len(REPOS)}</b><span>Repositories</span></div>
  <div class="tile"><b>{len(open_prs)}</b><span>Open PRs</span></div>
  <div class="tile"><b>{len(opened)}</b><span>PRs opened</span><em>last {WIN}d</em></div>
  <div class="tile"><b>{len(merged)}</b><span>PRs merged</span><em>last {WIN}d</em></div>
  <div class="tile"><b>{sum(sev_tot.values()) if have_alerts else '—'}</b><span>Open alerts</span><em>{sev_tot.get('critical',0)} critical · {sev_tot.get('high',0)} high</em></div>
  <div class="tile"><b>{dur(statistics.median(fix_hours) if fix_hours else None)}</b><span>Alert fix time</span><em>median (n={len(fix_hours)})</em></div>
</div>

<div class="two" style="margin-top:14px">
  <div class="panel"><h2 style="margin-top:0">Pull requests per week</h2>
    <p class="cap">Opened vs merged, last 12 weeks.</p>
    {bars([wk_open, wk_merge], [w.strftime('%d %b') for w in weeks], ['var(--s1)','var(--s2)'], ['Opened','Merged'])}
    {legend(['Opened','Merged'], ['var(--s1)','var(--s2)'])}</div>
  <div class="panel"><h2 style="margin-top:0">Dependabot alerts per month</h2>
    <p class="cap">Raised vs resolved (fixed or dismissed).</p>
    {bars([m_open, m_fix], [m[2:] for m in months], ['var(--s1)','var(--s2)'], ['Raised','Resolved']) if months else '<p class="empty">No alert history available.</p>'}
    {legend(['Raised','Resolved'], ['var(--s1)','var(--s2)']) if months else ''}</div>
</div>

<h2>Open pull requests</h2>
<div class="scroll"><table><thead><tr><th>Repo</th><th class="num">PR</th><th>Title</th><th>Author</th><th class="num">Age</th></tr></thead><tbody>{pr_rows}</tbody></table></div>

<h2>Recent failed runs</h2>
<p class="cap">Default-branch failures, with the pull request that introduced them where the commit maps to one.</p>
<div class="scroll"><table><thead><tr><th>Repo</th><th>Workflow</th><th>Caused by</th><th class="num">When</th></tr></thead><tbody>{fail_rows}</tbody></table></div>

<h2>Per-repository</h2>
<p class="cap">Ordered by what needs attention — failing CI, then severe alerts, then open PRs — not alphabetically.</p>
<div class="scroll"><table><thead><tr><th>Repo</th><th>Language</th><th class="num">Open</th><th class="num">Opened</th><th class="num">Merged</th><th class="num">Lead</th><th class="num">Fail&nbsp;%</th><th>CI</th><th class="num">Alerts</th><th>12&nbsp;wk</th><th class="num">Pushed</th></tr></thead><tbody>{"".join(repo_row(r) for r in sorted(REPOS, key=attention))}</tbody></table></div>

<h2>Code quality</h2>
<div class="panel"><p class="cap" style="margin:0">GitHub exposes no code-quality API, so this section stays empty until an analyser reports in. Wiring SonarQube (or CodeQL, which is free for public repositories) will populate maintainability, duplication and coverage here. Lint runs today as a non-blocking CI step in two repositories; its results are not yet collected.</p></div>

{tok_note}
{alerts_note}
<footer>Rebuilt on a schedule by GitHub Actions and published as a Pages artifact — no commits, no notifications. New repositories appear with no configuration.</footer>
</div></body></html>"""

with open(os.path.join(HERE, "..", "index.html"), "w") as f:
    f.write(HTML)
print(f"rendered — {len(REPOS)} repos, {len(open_prs)} open PRs, {len(failing)} failed runs")
