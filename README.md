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
