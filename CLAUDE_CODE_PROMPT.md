# MASTER PROMPT — Scripture Companion build-out (paste into Claude Code; run phase by phase)

You are finishing a Bible-listening companion for one user. Read this whole file, then `HANDOFF.md`, then `README.md`, before touching code. Work inside `sermon_companion/`. Python 3.11+; `pip install -r requirements.txt yt-dlp feedparser`.

## What exists (do not rebuild from scratch)
- `data/catalog_verified.jsonl` — 1,021 entries. Tiers: V2 (fetched, title matches), V1 (publisher-issued, not opened), PENDING (cataloged, no link), FAIL (rejected). The app shows only V1/V2 by Platt or PAM.
- `app_build.py` — generates the single-file app `out/scripture-companion-v19.html`. The app is the product. `build.py` (XLSX + roadmap) is secondary.
- `harvest.py` (Buzzsprout feeds, radical.net, Secret Church event pages, TWR360 sessions, iTunes, yt-dlp hooks), `verify.py` (fetch + title match), `refs.py` (literal Scripture parser, no inference), `canon.py` (66 books / 1,189 chapters), `data/narrative_order.json` (the user's EPUB chapter sequence).

## Non-negotiable rules — these ARE the product
1. **No inferred passages.** A chapter mapping comes only from a passage stated in the publisher's title or description. Topical episodes with no passage stay off the road (counted in settings).
2. **Publisher links only.** Buzzsprout, radical.net, Apple Podcasts, Spotify for Creators (anchor.fm), TWR360, official YouTube channels (Radical `UCTP7mGxH9LFTaMO2Kw9nZ7g`, `@2819Church`, `@PhilipAnthonyMitchell`, `@VictoryWorldChurch`). Never third-party re-uploads (e.g. "Walking Witness"), never search URLs, never an index page as an episode link.
3. **Guests excluded.** Episodes by Lonnell Williams, Milton James, Arik Hayes or any non-PAM speaker → GUEST list, never the road. Speaker = trailing `| Name` in the title.
4. **PAM eras.** 2819 Church first; Victory-era or other-era PAM only where 2819 has nothing, labeled gap-fill.
5. **Spans.** A multi-book overview stands once, at the first book of its span in the current reading order, labeled by exact span (a land name only when it covers the whole land; else `First–Last`; else the list). A single-book overview is that book's own. One event in several forms (event page / podcast episodes / video session / TWR360 session) → keep the forms that play; drop the event page.
6. **Audio in-app.** Every road item should carry a direct audio URL (`audio_override`, or Buzzsprout `<episode page>.mp3`). No hand-offs to other apps. Items without audio render greyed, "audio soon".
7. **Stable ids.** `id` = hash of the canonical `url` (`classify._id`). Never change a shipped entry's `url` — progress is keyed on `id`. Put better links in `alt_urls`/`audio_override`.
8. **Design law.** Do not redesign. Keep the v19 visual language exactly (HANDOFF.md → Design law). Data and bug fixes only, unless the user asks.

## Phase 1 — Pull every feed completely (the main unlock)
```
python run.py harvest --sources ptw,platt_messages,secret_church_podcast,twr360
python run.py harvest --sources 2819_podcast
```
Expected: Pray the Word 3,000+; David Platt Messages ≈570; Secret Church podcast exactly 198 (seasons 1–21, `N.M – Title`); TWR360 every session in series 48,49,50,51,52,37,53,54,55,56,57 with decoded CloudFront MP3s; 2819 ≈147 from `https://anchor.fm/s/ff787bd4/podcast/rss`.
If a Buzzsprout feed comes back short, fetch it with `requests` (no size cap) and parse with `feedparser`. Store per item: title, published, duration, enclosure URL → `audio_override`, episode page → `url`, description.
Acceptance: total entries ≈4,000+; zero entries from non-publisher hosts.

## Phase 2 — Map passages literally
Run `refs.parse(title + ' ' + description)` on every new entry. Secret Church titles such as `1.3 – Genesis, Exodus, and Leviticus` are whole-book spans: extend `refs.py` to accept comma/`and` lists of bare book names **only** for Secret Church podcast / TWR360 entries whose title has no chapter numbers. Genre words → fixed spans: Pentateuch = Genesis–Deuteronomy; Historical Books = Joshua–Esther; Wisdom Literature = Job–Song of Solomon; Prophets = Isaiah–Malachi; Gospels = Matthew–John; Letters of Paul = Romans–Philemon; Letters from Others = Hebrews–Revelation; Old/New Testament = the testament. No passage → `refs = {}` (off-road).
Acceptance: `python app_build.py`; at Genesis 1 the app shows "Entering Genesis–Leviticus" (1.3 + TWR Session 1), "Entering The Law" (19.2), "Entering the Old Testament" (1.1, 1.2, 20.3, TWR Session 4, …); Matthew 1 shows the NT surveys; no survey appears at a second book.

## Phase 3 — Verify
```
python run.py verify
```
Open every V1 link; live + title match → V2; dead/mismatch → FAIL. HEAD every `.mp3` / CloudFront URL and record `audio_ok`. Log to `out/verification_log.csv`.
Acceptance: 0 V1 left for Buzzsprout/TWR360/2819; every road item has `audio_ok=true` or is greyed.

## Phase 4 — YouTube-only material (optional, personal use)
Secret Church 22–26 (Who Am I, Jonah, Ruth, Matthew, Elijah) and PAM's pre-podcast years exist only on YouTube. If wanted: `yt-dlp -x --audio-format m4a` into `out/audio/`, host beside the app, set `audio_override` to the relative path; keep the official YouTube URL as `url`. Official channels only.

## Phase 5 — Build and ship
```
python app_build.py        # bump the version number in app_build.py first
```
Deploy as a static site (GitHub Pages or Netlify): the HTML file (+ `out/audio/` if Phase 4 ran). On iPhone Safari: open URL → Share → Add to Home Screen → full-screen, audio streams, lock-screen controls (Media Session), progress survives relaunch.
Acceptance: Genesis 1 opens with rays and the sun; Exodus 14 shows the parted sea with the Platt sermon playable; Secret Church sessions play from TWR360; Acts 1 shows PAM's "Be A Witness" playing from the 2819 feed; Revelation 21 glows; no emoji; no grey wash; no icon medallions on the road.

## Phase 6 — Add a teacher (when asked)
Register the feed in `config.py`, add a speaker rule in `classify.py` (name → `who`), harvest, verify, build. Their episodes land on the road by passage like everyone else.

## Reporting
After each phase print: entries total; by tier; by source; chapters with ≥1 road item; items with audio; off-road items (no passage); guests excluded; FAILs with reasons. Never claim a link works that you did not open.
