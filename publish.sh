#!/usr/bin/env bash
# Save the catalog, build the app from the LATEST code, record the audit, and publish out/site to gh-pages.
# A long job (the link check) started on older code, so everything is rebuilt from the newest main first.
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898+github-actions[bot]@users.noreply.github.com"
if [ "${REFRESH:-false}" = "true" ]; then
  git add data/
  git diff --cached --quiet || git commit -q -m "Refresh catalog ($(date -u +%F))"
fi
git pull -q --rebase --autostash origin main      # newest code and data before building
python app_build.py
python tools/audit.py > out/audit.txt 2>&1 || true   # full audit of every publish
tail -1 out/audit.txt
if [ "${REFRESH:-false}" = "true" ]; then
  git add out/audit.txt out/off_road.json
  git diff --cached --quiet || git commit -q -m "Audit record ($(date -u +%F))"
  git push -q origin HEAD:main                    # fails the step loudly if the catalog cannot be saved
fi
REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
cd out/site && touch .nojekyll && rm -rf .git
git init -q -b gh-pages && git add -A
git -c user.name="github-actions[bot]" -c user.email="41898+github-actions[bot]@users.noreply.github.com" commit -q -m "$1 ($(date -u +%F))"
git push -q -f "$REMOTE" gh-pages
rm -rf .git
echo "published"
