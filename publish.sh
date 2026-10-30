#!/usr/bin/env bash
# Build the app, save the catalog to main, and publish out/site to the gh-pages branch (GitHub Pages).
set -euo pipefail
python app_build.py
python tools/audit.py > out/audit.txt 2>&1 || true   # full audit of every publish; report saved with the build
tail -1 out/audit.txt
python - <<'PY'
import json, collections
es = [json.loads(l) for l in open("data/catalog_verified.jsonl")]
road = [e for e in es if e["tier"] in ("V1", "V2") and e["speaker"] in ("Platt", "PAM")]
print("entries:", len(es), "| by tier:", dict(collections.Counter(e["tier"] for e in es)))
print("by source:", dict(collections.Counter(e["source"] for e in es)))
print("Platt/PAM usable:", len(road), "| with audio:", sum(1 for e in road if e.get("audio_override") or "buzzsprout.com" in e["url"]))
PY
git config user.name "github-actions[bot]"
git config user.email "41898+github-actions[bot]@users.noreply.github.com"
if [ "${REFRESH:-false}" = "true" ]; then
  git add data/ out/audit.txt out/off_road.json   # the built app lives on gh-pages; only the record is kept here
  git diff --cached --quiet || git commit -q -m "Refresh catalog ($(date -u +%F))"
  git pull -q --rebase origin main && git push -q origin HEAD:main
fi
REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
cd out/site && touch .nojekyll && rm -rf .git
git init -q -b gh-pages && git add -A
git -c user.name="github-actions[bot]" -c user.email="41898+github-actions[bot]@users.noreply.github.com" commit -q -m "$1 ($(date -u +%F))"
git push -q -f "$REMOTE" gh-pages
rm -rf .git
echo "published"
