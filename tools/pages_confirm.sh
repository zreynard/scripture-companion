#!/usr/bin/env bash
# Make sure GitHub actually put the site live. Its Pages deploy step sometimes times out or is cancelled on GitHub's
# side (5 Nov 2026: four in a row), which leaves the old site up with no warning. Publish again until it is live.
set -uo pipefail
R="$GITHUB_REPOSITORY"; URL="https://x-access-token:${GITHUB_TOKEN}@github.com/$R.git"
for attempt in 1 2 3; do
  sha=$(git ls-remote "$URL" gh-pages | cut -f1); res=""
  for i in $(seq 1 90); do
    res=$(gh api "repos/$R/actions/runs?head_sha=$sha&per_page=10" --jq '[.workflow_runs[]|select(.name=="pages build and deployment")][0]|(.status+" "+(.conclusion//""))' 2>/dev/null || true)
    case "$res" in "completed success") echo "Site is live (${sha:0:7})"; exit 0;; completed*) break;; esac
    sleep 10
  done
  echo "::warning::GitHub Pages did not finish putting ${sha:0:7} live ($res); publishing again (try $attempt)"
  tmp=$(mktemp -d)
  git clone -q --depth 1 -b gh-pages "$URL" "$tmp" && (cd "$tmp" && git -c user.name="github-actions[bot]" -c user.email="41898+github-actions[bot]@users.noreply.github.com" commit -q --allow-empty -m "Publish again (GitHub Pages did not finish)" && git push -q origin gh-pages)
  rm -rf "$tmp"; sleep 20
done
echo "::warning::GitHub Pages did not put the site live after 3 tries"; exit 0   # a warning, not a failure: no email
