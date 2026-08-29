# dev-dashboard

One page showing every repository in this account: open pull requests, CI status
on the default branch, and open Dependabot alerts.

**Repositories are discovered, not configured.** The build lists the account's
repos from the API on every run, so a repo created tomorrow appears in the next
build with no edit here. Archived repos are skipped.

## How it works

`scripts/build_dashboard.py` queries the GitHub API and writes `index.html`.
A scheduled Action runs it roughly every 30 minutes and publishes the result to
GitHub Pages. The page is **deployed as a Pages artifact, not committed** — so
the dashboard generates no commits and no notification email.

## Dependabot alert counts

These need a token with the `security_events` scope; the default `GITHUB_TOKEN`
is scoped to this repository only. Add a fine-grained PAT as the repository
secret `DASHBOARD_TOKEN` to enable them.

Without it the build still succeeds — the alert column reads `n/a` and the page
explains why. It never fails for want of a scope.

## Running it locally

```bash
GH_TOKEN=$(gh auth token) python3 scripts/build_dashboard.py
open index.html
```

## Metrics

**Delivery (DORA proxies).** There is no deploy pipeline in these repos, so
*merge to default branch* stands in for a deployment and *default-branch CI
failure* for a change failure:

| Metric | How it is derived |
|---|---|
| Deploy frequency | merges to the default branch per week |
| Lead time | median PR open → merge |
| Change failure rate | failed ÷ completed default-branch runs |
| Time to restore | median failing run → next passing run |

**Activity.** PRs opened/merged per week, open PRs with age, failed runs mapped
back to the PR that caused them (via `merge_commit_sha` → PR), and Dependabot
alerts raised vs resolved per month with median time-to-fix.

**Code quality** is intentionally empty. GitHub has no code-quality API; that
panel fills in once SonarQube or CodeQL reports.

## Caveats worth knowing

- Notification workflows are excluded from CI stats so Slack runs don't dilute
  the failure rate.
- "Caused by" resolves only when a failing run's `head_sha` matches a PR's merge
  commit. Direct pushes to the default branch show the commit instead.
- Dependabot's alerts endpoint uses **cursor** pagination; `?page=` returns 400.
