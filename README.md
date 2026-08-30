# dev-dashboard

One page showing every repository in this account: open pull requests, CI status
on the default branch, and open Dependabot alerts.

**Repositories are discovered, not configured.** The build lists the account's
repos from the API on every run, so a repo created tomorrow appears in the next
build with no edit here. Archived repos are skipped.

## How it works

Two scripts, run in order. `scripts/collect.py` queries the GitHub API and the
SonarCloud API and writes `data.json`; `scripts/render.py` turns that into a
single self-contained `index.html`. Splitting them keeps a render change from
costing an API round trip, and lets the page be re-rendered from a collection
that has already happened.

A scheduled Action runs both hourly and publishes the result to GitHub Pages.
The page is **deployed as a Pages artifact, not committed** — so the dashboard
generates no commits and no notification email.

## Dependabot alert counts

These need a token with the `security_events` scope; the default `GITHUB_TOKEN`
is scoped to this repository only. Add a fine-grained PAT as the repository
secret `DASHBOARD_TOKEN` to enable them.

Without it the build still succeeds — the alert column reads `n/a` and the page
explains why. It never fails for want of a scope.

## Running it locally

```bash
GH_TOKEN=$(gh auth token) python3 scripts/collect.py   # → data.json
python3 scripts/render.py                              # → index.html
open index.html
```

`render.py` needs no token and no network: it reads `data.json` and nothing else,
so iterating on the page costs no API quota.

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

## Rebuilding on demand

The scheduled rebuild is **hourly**, not more frequent. GitHub deprioritises
high-frequency schedules on free public repositories: a measured `*/10` cron
fired 4 times in 15.5 hours — a 96% drop rate — at roughly 5-hour intervals.
A less aggressive cron is honoured more reliably, so hourly produces *more*
actual rebuilds than `*/10` did.

For an immediate rebuild, any of:

- the **Rebuild now** button in the page header — it dispatches the workflow over
  the GitHub API, polls the run with a live elapsed timer, and reloads the page
  itself once the deploy lands
- `gh workflow run dashboard.yml -R SuryaKiran434/dev-dashboard`
- `./refresh.sh` — triggers a build, waits for it, prints the live timestamp
- Actions → *Build dashboard* → **Run workflow**, including from the mobile app

A build takes about 40 seconds end to end.

### The token behind the Rebuild button

GitHub Pages is static, so nothing on the page can start a workflow without
credentials. There are exactly two ways to do it: a server holding a secret, or
the viewer's own token. This takes the second — a repo-writing credential in a
public page is not a trade worth making.

On first use the page asks for a fine-grained token scoped to **only** this
repository with a single permission, **Actions: Read and write**. It is kept in
that browser's `localStorage`, is never committed and never rendered into the
page, and goes nowhere but `api.github.com`. **Forget token** clears it.

One caveat: every page under `<owner>.github.io` shares a single origin, so any
Pages site of the same owner can read that entry. That is why the token is
scoped to one repository and one permission.

### If you want true real-time

Event-driven rebuilds (~60s after any push anywhere) require a
`repository_dispatch` call from each source repo, which means a PAT secret in
all twelve — twelve more places to rotate. Worth it only if hourly plus
on-demand proves insufficient.

### One thing to watch

**GitHub disables scheduled workflows after 60 days without a push to the
repository.** This repo only receives pushes when the dashboard code changes,
so a long quiet period will silently stop the cron. Triggering a manual run
does not reset that timer — only a commit does.
