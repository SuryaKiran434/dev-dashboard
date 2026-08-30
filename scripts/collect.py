#!/usr/bin/env python3
"""
Collect cross-repo engineering metrics from the GitHub API.

Repos are DISCOVERED, never configured — anything the account gains later is
picked up on the next run. Every endpoint degrades independently: a 403 on
Dependabot alerts (needs a PAT with security_events) yields None for that
section rather than failing the build.
"""
import json, os, sys, urllib.request, urllib.error, statistics
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import datetime, timezone, timedelta

OWNER = os.environ.get("DASHBOARD_OWNER", "SuryaKiran434")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
API = "https://api.github.com"
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "180"))
NOW = datetime.now(timezone.utc)
EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)
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
    sep = "&" if "?" in path else "?"
    out, url = [], f"{API}{path}{sep}per_page={per_page}"
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
         "pushed_h": int((_ts(r["pushed_at"]) - EPOCH).total_seconds() // 3600)}

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
                             "author": p["user"]["login"], "draft": p.get("draft", False),
                             "created_h": int((created - EPOCH).total_seconds() // 3600)})
        if created >= SINCE:
            opened_recent.append(created)
        if mergedat and mergedat >= SINCE:
            merged.append(mergedat)
            lead_times.append((mergedat - created).total_seconds() / 3600.0)
        if p.get("merge_commit_sha"):
            sha_to_pr[p["merge_commit_sha"]] = {"num": p["number"], "title": p["title"], "url": p["html_url"]}
    # Compact event log: [created_epoch_days, merged_epoch_days|-1] per PR.
    # Enough to recompute counts and lead time for ANY window client-side,
    # at a fraction of the bytes of full PR objects.
    ev = []
    for p in prs:
        c = _ts(p["created_at"])
        if c < SINCE:
            continue
        m = _ts(p.get("merged_at"))
        ev.append([int((c - EPOCH).total_seconds() // 3600),
                   int((m - EPOCH).total_seconds() // 3600) if m else -1])
    d.update(open_prs=open_prs, pr_events=ev)

    # ---- workflow runs on the default branch ---------------------------
    runs, _ = gh(f"/repos/{OWNER}/{name}/actions/runs",
                 {"branch": branch, "created": f">={SINCE.date().isoformat()}"},
                 paginate=True, cap=300)
    runs = [x for x in (runs or [])
            if "slack" not in x["name"].lower()
            and x.get("event") != "dynamic"
            and not str(x.get("path", "")).startswith("dynamic/")]
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
                "at_h": int((_ts(run["created_at"]) - EPOCH).total_seconds() // 3600),
                "_raw_at": run["created_at"],
                "sha": run["head_sha"][:7],
                "pr": pr, "msg": (run.get("head_commit") or {}).get("message", "").split("\n")[0][:70],
            })
        elif run["conclusion"] == "success" and open_fail is not None:
            restore_hours.append((_ts(run["created_at"]) - open_fail).total_seconds() / 3600.0)
            open_fail = None
    latest = next((x["conclusion"] or x["status"] for x in reversed(runs)), "none")
    def _elapsed_s(x):
        st = _ts(x.get("run_started_at") or x["created_at"])
        en = _ts(x.get("updated_at") or x["created_at"])
        d = (en - st).total_seconds()
        return int(d) if 0 <= d < 6 * 3600 else 0   # clamp absurd values

    run_ev = [[int((_ts(x["created_at"]) - EPOCH).total_seconds() // 3600),
               1 if x["conclusion"] == "success" else (0 if x["conclusion"] == "failure" else 2),
               _elapsed_s(x)]
              for x in runs if x["status"] == "completed"]

    # elapsed seconds per workflow, so the page can show which workflow costs most
    wf_time = {}
    for x in runs:
        if x["status"] == "completed":
            wf_time[x["name"]] = wf_time.get(x["name"], 0) + _elapsed_s(x)
    d["wf_time"] = wf_time
    # macOS runners bill at 10x on private repos; irrelevant while public but
    # worth surfacing, so record which repos use one.
    d["runner_os"] = "macos" if any("macos" in str(x.get("name", "")).lower()
                                    for x in runs) or name == "folderlock-mac" else "ubuntu"

    # For each failure, find the next SUCCESSFUL run of the SAME workflow. That
    # run's commit is what actually restored the build, so the PR it belongs to
    # is the one that addressed the failure. Without this a reader cannot tell a
    # live breakage from one fixed hours ago.
    by_wf = {}
    for x in runs:
        if x["status"] == "completed":
            by_wf.setdefault(x["name"], []).append(x)
    for f in failing_runs:
        later = [x for x in by_wf.get(f["wf"], [])
                 if _ts(x["created_at"]) > _ts(f["_raw_at"]) and x["conclusion"] == "success"]
        if later:
            fix = min(later, key=lambda x: x["created_at"])
            f["fixed_h"] = int((_ts(fix["created_at"]) - EPOCH).total_seconds() // 3600)
            f["fixed_by"] = sha_to_pr.get(fix["head_sha"])
            f["fixed_sha"] = fix["head_sha"][:7]
            f["fixed_url"] = fix["html_url"]
        else:
            f["fixed_h"] = None
        f.pop("_raw_at", None)

    d.update(ci_latest=latest, run_events=run_ev, failing_runs=failing_runs[-25:])

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
        aev = []
        for a in (alerts or []):
            c = _ts(a["created_at"])
            closed = _ts(a.get("fixed_at")) or _ts(a.get("dismissed_at"))
            aev.append([int((c - EPOCH).total_seconds() // 3600),
                        int((closed - EPOCH).total_seconds() // 3600) if closed else -1,
                        {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(
                            a["security_advisory"]["severity"], 0),
                        1 if a["state"] == "open" else 0])
        d["alerts"] = {"events": aev, "total": len(alerts or [])}
    # ---- code scanning (CodeQL) ----------------------------------------
    # 404 = default setup not configured / no analysis yet; 403 = disabled.
    # Either way this is "nothing to report", not a build failure.
    scan, serr = gh_cursor(f"/repos/{OWNER}/{name}/code-scanning/alerts?state=open")
    if serr:
        d["codeql"] = None
    else:
        buckets = {"error": 0, "warning": 0, "note": 0}
        rules = defaultdict(int)
        for a in (scan or []):
            sev = (a.get("rule") or {}).get("security_severity_level") \
                  or (a.get("rule") or {}).get("severity") or "note"
            sev = sev.lower()
            key = "error" if sev in ("critical", "high", "error") else \
                  "warning" if sev in ("medium", "moderate", "warning") else "note"
            buckets[key] += 1
            rules[(a.get("rule") or {}).get("description", "?")[:70]] += 1
        d["codeql"] = {"buckets": buckets, "total": len(scan or []),
                       "top": sorted(rules.items(), key=lambda x: -x[1])[:5]}
    # ---- SonarCloud ------------------------------------------------------
    # Public projects answer unauthenticated, so this needs no extra secret.
    d["sonar"] = None
    try:
        base = "https://sonarcloud.io/api"
        key = f"{OWNER}_{name}"
        req = urllib.request.Request(
            f"{base}/measures/component?component={key}&metricKeys="
            "coverage,ncloc,bugs,vulnerabilities,code_smells,duplicated_lines_density,"
            "sqale_index,security_rating,reliability_rating,sqale_rating",
            headers={"User-Agent": "dev-dashboard"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ms = {m["metric"]: m.get("value") for m in
                  json.load(r)["component"].get("measures", [])}
        req2 = urllib.request.Request(
            f"{base}/qualitygates/project_status?projectKey={key}",
            headers={"User-Agent": "dev-dashboard"})
        with urllib.request.urlopen(req2, timeout=20) as r:
            gate = json.load(r)["projectStatus"]["status"]
        d["sonar"] = {"measures": ms, "gate": gate}
    except Exception:
        pass  # project missing or Sonar unreachable — panel says so

    return d


def rate_budget():
    """Remaining core-API quota. Guards against a large account silently
    exhausting the hourly limit and producing a half-empty dashboard."""
    d, err = gh("/rate_limit")
    if err or not d:
        return None
    c = d.get("resources", {}).get("core", {})
    return c.get("remaining"), c.get("limit")


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
    budget = rate_budget()
    if budget and budget[0] is not None:
        need = len(repos) * 6 + 2
        if budget[0] < need:
            print(f"Rate limit too low ({budget[0]}/{budget[1]} left, need ~{need}) — "
                  f"refusing to build a partial dashboard.", file=sys.stderr)
            sys.exit(1)

    repos = [r for r in repos if not r.get("archived")]
    if not repos:
        print("No repos returned — aborting rather than emitting an empty dataset.", file=sys.stderr)
        sys.exit(1)

    # Collection is latency-bound, not CPU-bound: ~6 sequential HTTP round
    # trips per repo, each mostly spent waiting. Sequentially that is O(n)
    # wall-clock and hits ~7.6 min at 200 repos. A bounded pool makes it
    # O(n / workers) while keeping concurrent requests low enough not to
    # trip secondary rate limits. Bounded, not unbounded: an unbounded pool
    # over hundreds of repos would open hundreds of sockets and get throttled.
    workers = max(1, min(int(os.environ.get("COLLECT_WORKERS", "8")), len(repos)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        collected = list(pool.map(collect_repo, repos))   # map preserves input order

    data = {"owner": OWNER, "generated": NOW.isoformat(), "window_days": WINDOW_DAYS,
            "epoch_hours": int((NOW - EPOCH).total_seconds() // 3600),
            "token_expiry": TOKEN_EXPIRY[0] if TOKEN_EXPIRY else None,
            "workers": workers,
            "repos": collected}
    out = os.path.join(os.path.dirname(__file__), "..", "data.json")
    with open(out, "w") as f:
        json.dump(data, f)
    n_pr = sum(len(r["open_prs"]) for r in data["repos"])
    print(f"collected {len(repos)} repos · {n_pr} open PRs · window {WINDOW_DAYS}d")


if __name__ == "__main__":
    main()
