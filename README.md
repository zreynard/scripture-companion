# Platt + PAM Bible listening companion — build pipeline

One command rebuilds the whole thing from the publishers' own catalogs, verifies every link,
and writes the spreadsheet + HTML roadmap. Needs a machine with normal internet access
(it runs in Claude Code / a laptop; the claude.ai chat sandbox cannot reach these hosts).

    pip install -r requirements.txt
    python run.py fixtures          # offline dry run on bundled sample data (proves the build)
    python run.py all               # harvest -> verify -> build  (several hours; resumable)
    python run.py harvest --sources ptw,platt_messages,secret_church,radical
    python run.py verify            # re-run any time; only unchecked/stale links are fetched
    python run.py build

Outputs: out/platt_pam_bible_companion.xlsx and out/roadmap.html
Data:    data/catalog.jsonl (harvest), data/verification_log.jsonl (every URL ever tested),
         data/catalog_verified.jsonl (tiered), data/narrative_order.json (from NRSVue_Narrative_Order.epub)

## Rules the code enforces
* Links come only from publisher catalogs: Buzzsprout RSS feeds (Pray the Word 112848, David Platt
  Messages 107460), radical.net sitemap/REST + Secret Church pages, iTunes-resolved podcast feeds
  (McLean, 2819, Victory), YouTube channels enumerated with yt-dlp. No search URLs, ever.
* Tier V2 = the URL was fetched, is live, and the fetched title matches the claimed title.
  V1 = publisher-issued but the host blocked the check. FAIL = dead or title mismatch -> excluded.
* Passages are parsed literally from the publisher's own title/description (refs.py). No inference.
* Track: Pray the Word -> devotional; Secret Church / "survey|overview|introduction" titles /
  whole-book or >=60%-of-book coverage -> overview (pinned above chapter 1); everything else -> sermon.
* Speaker: PAM only when the publisher names him; 2819 guests -> GUEST sheet; radical.net pages take
  the page's author; speaker-unknown pages -> REVIEW sheet. Only Platt and PAM reach the ledger.
* PAM era rule: 2819-era first; Victory-era / other-era PAM fills a chapter only when 2819 has nothing.
* Every chapter with no sermon gets a VERIFIED GAP row naming the sources that were checked.
* Canonical order is the spine; narrative sequence (from the EPUB spine) is a sort column.

## Things to confirm on first run
* config.YOUTUBE_CHANNELS: the @PhilipAnthonyMitchell and @VictoryWorldChurch handles are best guesses;
  yt-dlp prints an error if a handle is wrong — fix the URL and re-run that source.
* radical.net has bot protection. `cloudscraper` is used automatically on 403; if pages still come back
  403, those rows stay V1 (publisher-issued) rather than being invented or dropped.
