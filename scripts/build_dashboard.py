#!/usr/bin/env python3
"""
Regenerate index.html from the GitHub API.

Repos are DISCOVERED, never listed: anything the account gains later appears
automatically. Reads GH_TOKEN from the environment.

Degrades rather than fails: any endpoint that 403s (typically Dependabot
alerts, which need a PAT with security_events) is reported as unavailable in
the page instead of aborting the build.
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone

OWNER = os.environ.get("DASHBOARD_OWNER", "SuryaKiran434")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
API = "https://api.github.com"


def gh(path, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "dev-dashboard",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        return None, f"{e.code}"
    except Exception as e:
        return None, str(e)[:40]


def age_of(iso):
    d = datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if d.days >= 1:
        return f"{d.days}d"
    h = d.seconds // 3600
    return f"{h}h" if h else f"{max(d.seconds // 60, 1)}m"


def collect():
    repos, page = [], 1
    while True:
        batch, err = gh(f"/users/{OWNER}/repos", {"per_page": 100, "page": page, "sort": "pushed"})
        if err or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    rows, prs = [], []
    for r in repos:
        name = r["name"]
        if r.get("archived"):
            continue
        open_prs, _ = gh(f"/repos/{OWNER}/{name}/pulls", {"state": "open", "per_page": 100})
        open_prs = open_prs or []
        for p in open_prs:
            prs.append({
                "repo": name, "num": p["number"], "title": p["title"],
                "author": p["user"]["login"], "url": p["html_url"],
                "age": age_of(p["created_at"]), "draft": p.get("draft", False),
            })

        # latest non-notification workflow run on the default branch
        runs, _ = gh(f"/repos/{OWNER}/{name}/actions/runs",
                     {"branch": r["default_branch"], "per_page": 15})
        ci = "none"
        if runs and runs.get("workflow_runs"):
            for run in runs["workflow_runs"]:
                if "slack" in run["name"].lower():
                    continue
                ci = run["conclusion"] or run["status"]
                break

        alerts, aerr = gh(f"/repos/{OWNER}/{name}/dependabot/alerts", {"state": "open", "per_page": 100})
        if aerr:
            sev = None
        else:
            sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for a in (alerts or []):
                s = a["security_advisory"]["severity"]
                sev[s] = sev.get(s, 0) + 1

        rows.append({
            "name": name, "url": r["html_url"], "lang": r.get("language") or "—",
            "prs": len(open_prs), "ci": ci, "sev": sev,
            "pushed": age_of(r["pushed_at"]), "private": r["private"],
        })
    return rows, prs


def render(rows, prs):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    failing = sum(1 for r in rows if r["ci"] == "failure")
    crit = sum((r["sev"] or {}).get("critical", 0) + (r["sev"] or {}).get("high", 0) for r in rows)
    unavail = any(r["sev"] is None for r in rows)

    def ci_pill(c):
        m = {"success": ("ok", "passing"), "failure": ("bad", "failing"),
             "cancelled": ("warn", "cancelled"), "in_progress": ("warn", "running"),
             "queued": ("warn", "queued"), "none": ("mute", "no CI")}
        cls, label = m.get(c, ("warn", c))
        return f'<span class="pill {cls}">{label}</span>'

    pr_rows = "".join(
        f'<tr><td class="mono"><a href="https://github.com/{OWNER}/{p["repo"]}">{p["repo"]}</a></td>'
        f'<td class="mono num"><a href="{p["url"]}">#{p["num"]}</a></td>'
        f'<td>{p["title"][:78]}{"…" if len(p["title"])>78 else ""}'
        f'{" <span class=\'pill mute\'>draft</span>" if p["draft"] else ""}</td>'
        f'<td class="mono dim">{p["author"]}</td><td class="mono num dim">{p["age"]}</td></tr>'
        for p in sorted(prs, key=lambda x: (x["repo"], x["num"]))
    ) or '<tr><td colspan="5" class="empty">No open pull requests anywhere. </td></tr>'

    repo_rows = "".join(
        f'<tr><td class="mono"><a href="{r["url"]}">{r["name"]}</a></td>'
        f'<td class="dim">{r["lang"]}</td>'
        f'<td class="num">{"<b>"+str(r["prs"])+"</b>" if r["prs"] else "<span class=\'dim\'>0</span>"}</td>'
        f'<td>{ci_pill(r["ci"])}</td>'
        f'<td class="num">' + (
            "<span class='dim'>n/a</span>" if r["sev"] is None else
            (" ".join(f'<span class="sev {k}">{v}</span>' for k, v in r["sev"].items() if v) or "<span class='dim'>0</span>")
        ) + '</td>'
        f'<td class="mono num dim">{r["pushed"]}</td></tr>'
        for r in rows
    )

    note = ('<p class="note">Dependabot alert counts are unavailable — the build token lacks the '
            '<code>security_events</code> scope. Add a PAT as the <code>DASHBOARD_TOKEN</code> secret to enable them.</p>'
            if unavail else "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{OWNER} — repo dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#F5F6F8;--card:#FFF;--ink:#151922;--ink2:#5A6472;--ink3:#8C95A3;--line:#E1E5EC;
--accent:#2B4A7E;--ok:#1C6B45;--okbg:#E3F2EA;--bad:#A32C24;--badbg:#FBE7E5;
--warn:#8A5A11;--warnbg:#FBF0DC;--mute:#6B7280;--mutebg:#EDEFF3;}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0E1117;--card:#161B24;--ink:#E7EBF2;
--ink2:#A2ACBB;--ink3:#727C8B;--line:#252C38;--accent:#8AA9E0;--ok:#68C79B;--okbg:#14291F;
--bad:#E9877E;--badbg:#2E1A18;--warn:#DCA85C;--warnbg:#2B2216;--mute:#8B93A0;--mutebg:#1E242E;}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Inter Tight",-apple-system,system-ui,sans-serif}}
.wrap{{max-width:1160px;margin:0 auto;padding:34px 22px 70px}}
h1{{font-size:1.5rem;font-weight:700;letter-spacing:-.02em;margin:0 0 3px}}
.sub{{color:var(--ink2);font-size:13.5px;margin:0 0 26px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:30px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:15px 17px}}
.tile b{{display:block;font-size:27px;font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.15}}
.tile span{{font-size:11.5px;color:var(--ink3);text-transform:uppercase;letter-spacing:.07em;font-weight:500}}
.tile.alert b{{color:var(--bad)}} .tile.good b{{color:var(--ok)}}
h2{{font-size:1rem;font-weight:600;margin:30px 0 11px;letter-spacing:-.01em}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:7px;overflow:hidden}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink3);
font-weight:600;padding:9px 13px;border-bottom:1px solid var(--line);background:var(--bg)}}
td{{padding:9px 13px;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:middle}}
tr:last-child td{{border-bottom:0}}
.mono{{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:12.5px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.dim{{color:var(--ink3)}}
.empty{{text-align:center;color:var(--ink3);padding:26px}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
.pill{{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:20px;letter-spacing:.02em}}
.pill.ok{{background:var(--okbg);color:var(--ok)}} .pill.bad{{background:var(--badbg);color:var(--bad)}}
.pill.warn{{background:var(--warnbg);color:var(--warn)}} .pill.mute{{background:var(--mutebg);color:var(--mute)}}
.sev{{display:inline-block;font-family:"JetBrains Mono",monospace;font-size:11px;font-weight:500;
padding:1px 6px;border-radius:4px;margin-left:3px}}
.sev.critical,.sev.high{{background:var(--badbg);color:var(--bad)}}
.sev.medium{{background:var(--warnbg);color:var(--warn)}} .sev.low{{background:var(--mutebg);color:var(--mute)}}
.note{{font-size:12.5px;color:var(--ink3);margin:9px 0 0}}
code{{font-family:"JetBrains Mono",monospace;font-size:11.5px;background:var(--mutebg);padding:1px 4px;border-radius:3px}}
footer{{margin-top:34px;padding-top:15px;border-top:1px solid var(--line);font-size:12px;color:var(--ink3)}}
@media(max-width:660px){{td,th{{padding:8px 9px;font-size:12.5px}}}}
</style></head><body><div class="wrap">
<h1>{OWNER}</h1>
<p class="sub">Every repository, discovered automatically. Rebuilt {now}.</p>
<div class="tiles">
  <div class="tile"><b>{len(rows)}</b><span>Repositories</span></div>
  <div class="tile {'alert' if prs else 'good'}"><b>{len(prs)}</b><span>Open PRs</span></div>
  <div class="tile {'alert' if failing else 'good'}"><b>{failing}</b><span>Failing CI</span></div>
  <div class="tile {'alert' if crit else 'good'}"><b>{'n/a' if unavail else crit}</b><span>Critical + High</span></div>
</div>
<h2>Open pull requests</h2>
<table><thead><tr><th>Repo</th><th class="num">PR</th><th>Title</th><th>Author</th><th class="num">Age</th></tr></thead>
<tbody>{pr_rows}</tbody></table>
<h2>Repository health</h2>
<table><thead><tr><th>Repo</th><th>Language</th><th class="num">PRs</th><th>CI (default branch)</th><th class="num">Alerts</th><th class="num">Last push</th></tr></thead>
<tbody>{repo_rows}</tbody></table>
{note}
<footer>Regenerated on a schedule by GitHub Actions. New repositories appear with no configuration.</footer>
</div></body></html>"""


if __name__ == "__main__":
    rows, prs = collect()
    if not rows:
        print("No repos returned — refusing to overwrite with an empty page.", file=sys.stderr)
        sys.exit(1)
    out = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(out, "w") as f:
        f.write(render(rows, prs))
    print(f"wrote index.html — {len(rows)} repos, {len(prs)} open PRs")
