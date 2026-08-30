#!/usr/bin/env bash
# Trigger a dashboard rebuild and wait for it, then print the live timestamp.
set -euo pipefail
REPO="SuryaKiran434/dev-dashboard"
gh workflow run dashboard.yml -R "$REPO"
printf 'building'
until [ "$(gh run list -R "$REPO" --workflow dashboard.yml --limit 1 --json status -q '.[0].status')" = completed ]; do
  printf '.'; sleep 5
done
echo
gh run list -R "$REPO" --workflow dashboard.yml --limit 1 --json conclusion -q '"run: " + .[0].conclusion'
curl -s https://suryakiran434.github.io/dev-dashboard/ | grep -o 'rebuilt [^·<]*' | head -1
