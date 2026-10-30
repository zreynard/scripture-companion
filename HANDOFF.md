# HANDOFF — Scripture Companion (state as of 2026-10-30)

## The idea in one sentence
A single-file web app in which you walk the Bible as one road — Genesis to Revelation, canonical or your narrative order — and at every chapter the teaching that belongs there (David Platt, Philip Anthony Mitchell, Secret Church, Pray the Word) plays inside the app like a podcast; progress is the road turning gold behind you.

## Files that matter
- `out/site/` — **the app to deploy** (index.html + manifest + icons + service worker). Open in Safari from a web address, Add to Home Screen. Progress lives on the device (export/import under ⋯).
- `out/scripture-companion-v21.html` — the same app as one file (no icon/offline).
- `pwa/` — home-screen pieces copied into `out/site/` on every build (manifest, `sw.js`, icons; `icon.svg` is the source).
- `app_build.py` — regenerates the app from the catalog. All design code lives in its `TEMPLATE`. Bump `VERSION` on each shipped build (it also refreshes the offline cache).
- `data/catalog_verified.jsonl` — the catalog (one JSON per line). Fields that matter: `id`, `url`, `primary_url`, `alt_urls`, `audio_override`, `title`, `speaker` (Platt/PAM/guest), `era` (platt/2819/victory), `track` (sermon/devotional/overview), `tier` (V2/V1/PENDING/FAIL), `refs` ({book: {chapters, whole_book}}), `refs_text`, `sc_season`, `sc_episode`, `verify_note`.
- `config.py` — registered sources. `harvest.py` — harvesters incl. `harvest_twr360` (decodes the mediahit base64 → CloudFront MP3). `verify.py`, `refs.py`, `canon.py`, `data/narrative_order.json`.
- `out/platt_pam_bible_companion.xlsx`, `out/roadmap.html` — the ledger workbook and roadmap (secondary; `python run.py build`).

## Where the data stands (2026-10-30, after the first full pull)
4,465 catalog entries; 4,376 Platt/PAM items in the app, 4,281 with in-app audio; 1,100 of 1,189 chapters have a voice.
Pray the Word 3,397 (2017 to now; feed gives the newest 1,000, the rest come from Buzzsprout's load-more pages), David Platt Messages 528, Secret Church podcast 198, TWR360 Secret Church sessions 43 (events 1–12), 2819 PAM 121 (guests excluded), McLean OCEANS videos 76 (no audio; silent twins of playable items are hidden).
497 items name no passage and stay off the road. Still missing: Secret Church 22–26 and PAM's pre-podcast years (YouTube only, Phase 4), link checking (Phase 3; runs weekly).

## How it refreshes
GitHub Actions (`.github/workflows/refresh.yml`) runs on GitHub's servers every Monday and on demand (Actions tab → Refresh and publish → Run workflow): pull feeds → `run.py stamp` → build → publish to the `gh-pages` branch → check links → publish again. The catalog is committed back to `main`. Live app: https://zreynard.github.io/scripture-companion/
`tools/probe.py` (Actions → Probe feeds) fetches URLs from GitHub's servers and saves the results to the `diag` branch.

## Hosting in two minutes
Drag the `out/site` folder onto app.netlify.com/drop (or serve it from GitHub Pages). Open the address on the phone in Safari → Share → Add to Home Screen. The Claude app's file viewer and iOS Quick Look block audio; Safari does not. A home-screen app keeps its own storage separate from Safari tabs, so move progress with export/import once after installing.

## Design law (so nobody regresses it)
Register: illuminated manuscript / sacred cartography. Vellum ground that warms from pale sky at creation to white-gold glory at Revelation. Lettering in deep ink blue; lands in small gold capitals; gold leaf for the walked road and the marker; a white dashed center line; the road ahead a pale ink wash. Scenery is drawn, never iconic: engraved single-line horizons, gold hairline marginalia beside each book, the great scenes as fine line-and-glow vignettes spaced apart, rivers at the Jordan and the river of life, rays of the first morning at the top and rays of glory at the end. No emoji, no icon medallions, no grey washes, no dark/depressing passages, no lists or grids. One world, camera follows you, the clearing sits in the world where you stand, Now Playing rises over everything.

## Interaction law
No back navigation. The clearing shows: land · n of 1,189; chapter; scene name; the voices (≤3, "n more" to expand); "Next voice ahead"; Mark read (advances the camp); Walk on; My place. Tap the road or a book name to look ahead; the faint dot is your true position. Settings (⋯): order, voice filter, export/import/reset, audio test.

## Rules (short form)
Publisher links only · no inferred passages · guests off the road · 2819 first, other PAM eras as gap-fill · surveys stand once at the first book of their span · one event, one playing form · every road item carries audio · ids never change.
