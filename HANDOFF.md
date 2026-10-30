# HANDOFF — Scripture Companion (state as of 2026-10-30)

## The idea in one sentence
A single-file web app in which you walk the Bible as one road — Genesis to Revelation, canonical or your narrative order — and at every chapter the teaching that belongs there (David Platt, Philip Anthony Mitchell, Secret Church, Pray the Word) plays inside the app like a podcast; progress is the road turning gold behind you.

## Files that matter
- `out/site/` — **the app to deploy** (index.html + manifest + icons + service worker). Open in Safari from a web address, Add to Home Screen. Progress lives on the device (export/import under ⋯).
- `out/scripture-companion-v20.html` — the same app as one file (no icon/offline).
- `pwa/` — home-screen pieces copied into `out/site/` on every build (manifest, `sw.js`, icons; `icon.svg` is the source).
- `app_build.py` — regenerates the app from the catalog. All design code lives in its `TEMPLATE`. Bump `VERSION` on each shipped build (it also refreshes the offline cache).
- `data/catalog_verified.jsonl` — the catalog (one JSON per line). Fields that matter: `id`, `url`, `primary_url`, `alt_urls`, `audio_override`, `title`, `speaker` (Platt/PAM/guest), `era` (platt/2819/victory), `track` (sermon/devotional/overview), `tier` (V2/V1/PENDING/FAIL), `refs` ({book: {chapters, whole_book}}), `refs_text`, `sc_season`, `sc_episode`, `verify_note`.
- `config.py` — registered sources. `harvest.py` — harvesters incl. `harvest_twr360` (decodes the mediahit base64 → CloudFront MP3). `verify.py`, `refs.py`, `canon.py`, `data/narrative_order.json`.
- `out/platt_pam_bible_companion.xlsx`, `out/roadmap.html` — the ledger workbook and roadmap (secondary; `python run.py build`).

## Where the data stands
319 road items, 200 with audio: Secret Church podcast 12.7–21.9 (82, Buzzsprout MP3), Secret Church 1 sessions 1–4 (TWR360 MP3), David Platt Messages 25 (Buzzsprout), Pray the Word ≈100, 2819 episodes 29 (Apple pages, no audio yet), McLean OCEANS videos (no audio; their podcast twins arrive with the Platt Messages feed). Missing until Claude Code runs: Secret Church 1.4–12.6 episodes, Secret Church 2–12 TWR360 sessions, all 2819 audio, the other ~3,000 Pray the Word episodes, the other ~545 Platt sermons.

## Hosting in two minutes
Drag the `out/site` folder onto app.netlify.com/drop (or serve it from GitHub Pages). Open the address on the phone in Safari → Share → Add to Home Screen. The Claude app's file viewer and iOS Quick Look block audio; Safari does not. A home-screen app keeps its own storage separate from Safari tabs, so move progress with export/import once after installing.

## Design law (so nobody regresses it)
Register: illuminated manuscript / sacred cartography. Vellum ground that warms from pale sky at creation to white-gold glory at Revelation. Lettering in deep ink blue; lands in small gold capitals; gold leaf for the walked road and the marker; a white dashed center line; the road ahead a pale ink wash. Scenery is drawn, never iconic: engraved single-line horizons, gold hairline marginalia beside each book, the great scenes as fine line-and-glow vignettes spaced apart, rivers at the Jordan and the river of life, rays of the first morning at the top and rays of glory at the end. No emoji, no icon medallions, no grey washes, no dark/depressing passages, no lists or grids. One world, camera follows you, the clearing sits in the world where you stand, Now Playing rises over everything.

## Interaction law
No back navigation. The clearing shows: land · n of 1,189; chapter; scene name; the voices (≤3, "n more" to expand); "Next voice ahead"; Mark read (advances the camp); Walk on; My place. Tap the road or a book name to look ahead; the faint dot is your true position. Settings (⋯): order, voice filter, export/import/reset, audio test.

## Rules (short form)
Publisher links only · no inferred passages · guests off the road · 2819 first, other PAM eras as gap-fill · surveys stand once at the first book of their span · one event, one playing form · every road item carries audio · ids never change.
