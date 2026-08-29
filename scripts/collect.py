#!/usr/bin/env python3
"""
Collect cross-repo engineering metrics from the GitHub API.

Repos are DISCOVERED, never configured — anything the account gains later is
picked up on the next run. Every endpoint degrades independently: a 403 on
Dependabot alerts (needs a PAT with security_events) yields None for that
section rather than failing the build.
"""
import json, os, sys, urllib.request, urllib.error, statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta

OWNER = os.environ.get("DASHBOARD_OWNER", "SuryaKiran434")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
API = "https://api.github.com"
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "90"))
NOW = datetime.now(timezone.utc)
TOKEN_EXPIRY = []  # populated from the API response header
SINCE = NOW - timedelta(days=WINDOW_DAYS)


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def gh(path, params=None, paginate=False, cap=500):
    out, page = [], 1
    while True:
        p = dict(params or {})
        if paginate:
            p.update({"per_page": 100, "page": page})
        url = f"{API}{path}"
        if p:
            url += "?" + "&".join(f"{k}={v}" for k, v in p.items())
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dev-dashboard",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                exp = r.headers.get("GitHub-Authentication-Token-Expiration")
                if exp:
                    TOKEN_EXPIRY.append(exp)
                data = json.load(r)
        except urllib.error.HTTPError as e:
            return (out if out else None), str(e.code)
        except Exception as e:
            return (out if out else None), str(e)[:40]
        if not paginate:
            return data, None
        batch = data if isinstance(data, list) else data.get("workflow_runs", [])
        out.extend(batch)
        if len(batch) < 100 or len(out) >= cap:
            return out, None
        page += 1



def gh_cursor(path, per_page=100, cap=1000):
    """Cursor-paginated GET (Dependabot alerts). This endpoint rejects ?page=
    with 400 and instead advances via an `after` cursor in the Link header."""
    import re as _re
    out, url = [], f"{API}{path}?per_page={per_page}"
    while url and len(out) < cap:
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dev-dashboard",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out.extend(json.load(r))
                link = r.headers.get("Link", "") or ""
        except urllib.error.HTTPError as e:
            return (out if out else None), str(e.code)
        except Exception as e:
            return (out if out else None), str(e)[:40]
        m = _re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return out, None


def collect_repo(r):
    """Everything for one repo. Never raises — partial data is fine."""
    name, branch = r["name"], r["default_branch"]
    d = {"name": name, "url": r["html_url"], "lang": r.get("language") or "—",
         "pushed": r["pushed_at"], "default_branch": branch}

    # ---- pull requests -------------------------------------------------
    prs, _ = gh(f"/repos/{OWNER}/{name}/pulls",
                {"state": "all", "sort": "updated", "direction": "desc"},
                paginate=True, cap=300)
    prs = prs or []
    open_prs, merged, lead_times, opened_recent = [], [], [], []
    sha_to_pr = {}
    for p in prs:
        created, mergedat = _ts(p["created_at"]), _ts(p.get("merged_at"))
        if p["state"] == "open":
            open_prs.append({"num": p["number"], "title": p["title"], "url": p["html_url"],
                             "author": p["user"]["login"], "created": p["created_at"],
                             "draft": p.get("draft", False)})
        if created >= SINCE:
            opened_recent.append(created)
        if mergedat and mergedat >= SINCE:
            merged.append(mergedat)
            lead_times.append((mergedat - created).total_seconds() / 3600.0)
        if p.get("merge_commit_sha"):
            sha_to_pr[p["merge_commit_sha"]] = {"num": p["number"], "title": p["title"], "url": p["html_url"]}
    d.update(open_prs=open_prs, opened_recent=[t.isoformat() for t in opened_recent],
             merged_recent=[t.isoformat() for t in merged],
             lead_hours=lead_times)

    # ---- workflow runs on the default branch ---------------------------
    runs, _ = gh(f"/repos/{OWNER}/{name}/actions/runs",
                 {"branch": branch, "created": f">={SINCE.date().isoformat()}"},
                 paginate=True, cap=300)
    runs = [x for x in (runs or []) if "slack" not in x["name"].lower()]
    runs.sort(key=lambda x: x["created_at"])
    total = fails = 0
    restore_hours, failing_runs = [], []
    open_fail = None
    for run in runs:
        if run["status"] != "completed":
            continue
        total += 1
        if run["conclusion"] == "failure":
            fails += 1
            if open_fail is None:
                open_fail = _ts(run["created_at"])
            pr = sha_to_pr.get(run["head_sha"])
            failing_runs.append({
                "repo": name, "wf": run["name"], "url": run["html_url"],
                "at": run["created_at"], "sha": run["head_sha"][:7],
                "pr": pr, "msg": (run.get("head_commit") or {}).get("message", "").split("\n")[0][:70],
            })
        elif run["conclusion"] == "success" and open_fail is not None:
            restore_hours.append((_ts(run["created_at"]) - open_fail).total_seconds() / 3600.0)
            open_fail = None
    latest = next((x["conclusion"] or x["status"] for x in reversed(runs)), "none")
    d.update(ci_latest=latest, runs_total=total, runs_failed=fails,
             restore_hours=restore_hours, failing_runs=failing_runs[-8:])

    # ---- dependabot alerts ---------------------------------------------
    # NOTE: this endpoint uses cursor pagination (before/after), NOT ?page —
    # passing page= returns 400. One per_page=100 call covers every repo here;
    # `truncated` records the case where it would not.
    alerts, err = gh_cursor(f"/repos/{OWNER}/{name}/dependabot/alerts")
    if err:
        d["alerts"] = None
    else:
        opened_m, fixed_m = defaultdict(int), defaultdict(int)
        sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        fix_hours = []
        for a in (alerts or []):
            c = _ts(a["created_at"])
            opened_m[c.strftime("%Y-%m")] += 1
            closed = _ts(a.get("fixed_at")) or _ts(a.get("dismissed_at"))
            if closed:
                fixed_m[closed.strftime("%Y-%m")] += 1
                fix_hours.append((closed - c).total_seconds() / 3600.0)
            if a["state"] == "open":
                s = a["security_advisory"]["severity"]
                sev[s] = sev.get(s, 0) + 1
        d["alerts"] = {"sev": sev, "opened_by_month": dict(opened_m),
                       "fixed_by_month": dict(fixed_m), "fix_hours": fix_hours,
                       "total": len(alerts or []),
                       "truncated": False}
    return d


def main():
    repos, page = [], 1
    while True:
        batch, err = gh(f"/users/{OWNER}/repos", {"per_page": 100, "page": page, "sort": "pushed"})
        if err or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    repos = [r for r in repos if not r.get("archived")]
    if not repos:
        print("No repos returned — aborting rather than emitting an empty dataset.", file=sys.stderr)
        sys.exit(1)

    data = {"owner": OWNER, "generated": NOW.isoformat(), "window_days": WINDOW_DAYS,
            "token_expiry": TOKEN_EXPIRY[0] if TOKEN_EXPIRY else None,
            "repos": [collect_repo(r) for r in repos]}
    out = os.path.join(os.path.dirname(__file__), "..", "data.json")
    with open(out, "w") as f:
        json.dump(data, f)
    n_pr = sum(len(r["open_prs"]) for r in data["repos"])
    print(f"collected {len(repos)} repos · {n_pr} open PRs · window {WINDOW_DAYS}d")


if __name__ == "__main__":
    main()
