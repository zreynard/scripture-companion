"""Harvest every publisher catalog into data/catalog.jsonl.

Sources (publisher-issued only):
  ptw            Pray the Word RSS (Buzzsprout)                     -> devotional track
  platt_messages David Platt Messages RSS (Buzzsprout)              -> sermon track
  radical        radical.net message / podcast / series pages       -> sermon/overview (via sitemap or WP REST)
  secret_church  radical.net Secret Church event pages              -> overview track
  mclean         McLean Bible Church podcast (iTunes lookup)        -> sermon (mixed speakers; Platt kept)
  2819_podcast   2819 Church podcast (iTunes lookup)                -> PAM / guest
  youtube_*      2819 / PAM / Victory channels via yt-dlp           -> PAM / guest
Run:  python run.py harvest [--sources ptw,platt_messages,...]
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time, urllib.parse
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import config
from net import get, get_json, parse_rss, page_meta, strip_tags
from html import unescape as html_unescape
from classify import make_entry

DATA = os.path.join(os.path.dirname(__file__), "data")
CATALOG = os.path.join(DATA, "catalog.jsonl")
REPORT = os.path.join(DATA, "harvest_report.json")

def _log(msg): print(f"[harvest] {msg}", flush=True)

def _buzz_episode_url(item: dict) -> str:
    if item.get("link"):
        return item["link"]
    enc = item.get("enclosure", "")
    return re.sub(r"\.mp3(\?.*)?$", "", enc)

# ---------- Buzzsprout feeds ----------
def harvest_feed(key: str, feed_url: str, era: str = "platt") -> list[dict]:
    r = get(feed_url, timeout=60)
    if not r.ok:
        _log(f"{key}: feed fetch failed {r.status} {r.note}")
        return []
    items = parse_rss(r.text)
    out = []
    for it in items:
        url = _buzz_episode_url(it)
        if not url:
            continue
        alt = []
        # radical.net mirrors PTW episodes at /podcasts/pray-the-word/<slug>/ — recorded as alt, verified later
        if key == "ptw":
            slug = re.sub(r"^#?\d+\s*[–-]\s*", "", it["title"])
            slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
            alt.append(f"https://radical.net/podcasts/pray-the-word/{slug}/")
        e = make_entry(source=key, source_url=feed_url, url=url, title=it["title"],
                       description=it["description"], published=it["pubdate"],
                       duration=it["duration"], author=it["author"], era=era, alt_urls=alt)
        e["audio_override"] = it.get("enclosure") or None
        out.append(e)
    _log(f"{key}: {len(out)} items")
    return out

# ---------- iTunes-resolved podcasts ----------
def itunes_feed_url(term: str, must_match: str) -> tuple[str, str] | None:
    data, r = get_json(config.ITUNES_SEARCH + urllib.parse.quote(term))
    if not data:
        _log(f"itunes search failed for {term!r}: {r.status} {r.note}")
        return None
    for res in data.get("results", []):
        name = res.get("collectionName", "")
        if re.search(must_match, name, re.I) and res.get("feedUrl"):
            return res["feedUrl"], name
    return None

def harvest_itunes_podcast(key: str, term: str, must_match: str, era: str, channel_default=None) -> list[dict]:
    found = itunes_feed_url(term, must_match)
    if not found:
        _log(f"{key}: no podcast found in iTunes for {term!r}")
        return []
    feed_url, name = found
    r = get(feed_url, timeout=60)
    if not r.ok:
        _log(f"{key}: feed fetch failed {r.status}")
        return []
    out = []
    for it in parse_rss(r.text):
        url = it.get("link") or ""
        if not url and re.search(r"buzzsprout\.com/\d+/(episodes/)?\d+", it.get("enclosure", "")):
            url = re.sub(r"\.mp3(\?.*)?$", "", it["enclosure"])  # Buzzsprout: the episode page is the mp3 address minus .mp3
            if "/episodes/" not in url:
                url = re.sub(r"(buzzsprout\.com/\d+)/", r"\1/episodes/", url, count=1)
        url = url or it.get("enclosure")
        if not url:
            continue
        e = make_entry(source=key, source_url=feed_url, url=url, title=it["title"],
                       description=it["description"], published=it["pubdate"], duration=it["duration"],
                       author=it["author"], era=era, channel_default=channel_default, series=name)
        e["audio_override"] = it.get("enclosure") or None
        if key == "secret_church_podcast":
            secret_church_fixup(e)
        out.append(e)
    _log(f"{key} ({name}): {len(out)} items")
    return out

# ---------- Secret Church podcast: numbering + whole-book spans ----------
_GENRES = [  # fixed spans for genre words (CLAUDE_CODE_PROMPT.md Phase 2)
    (r"\bpentateuch\b|\bthe law\b", "Genesis", "Deuteronomy"),
    (r"historical books", "Joshua", "Esther"),
    (r"wisdom literature|poetry and wisdom|wisdom books", "Job", "Song of Solomon"),
    (r"major prophets", "Isaiah", "Daniel"),
    (r"minor prophets", "Hosea", "Malachi"),
    (r"\bthe prophets\b|\bprophets\b", "Isaiah", "Malachi"),
    (r"\bgospels\b", "Matthew", "John"),
    (r"letters of paul|paul'?s letters|pauline", "Romans", "Philemon"),
    (r"letters from others|general letters", "Hebrews", "Revelation"),
    (r"old testament", "Genesis", "Malachi"),
    (r"new testament", "Matthew", "Revelation"),
]
def _span(a, z):
    from canon import BOOKS
    names = [b[0] for b in BOOKS]
    return names[names.index(a):names.index(z) + 1]

def secret_church_fixup(e: dict) -> dict:
    """Sets sc_season/sc_episode from 'N.M – Title' and maps bare book lists / genre words to whole books.
    Only for titles that name no chapter numbers (no inference beyond the stated books)."""
    from canon import CHAPTERS
    from refs import _canon
    m = re.match(r"\s*(\d+)\.(\d+)\s*[\u2013\u2014-]\s*(.+)$", e["title"])
    if not m:
        return e
    e["sc_season"], e["sc_episode"], rest = int(m.group(1)), int(m.group(2)), m.group(3)
    e["track"] = "overview"; e["speaker"] = "Platt"; e["era"] = "platt"
    if e.get("refs"):
        return e
    books = []
    lst = re.sub(r"^(the )?(books? of )", "", rest, flags=re.I)
    lst = re.sub(r"\b([123])\s*(?:&|and)\s*([23])\s*(?:&|and)?\s*(3)?\s+([A-Z][a-z]+)",  # "1 & 2 Kings" -> "1 Kings, 2 Kings"
                 lambda m: ", ".join(f"{n} {m.group(4)}" for n in (m.group(1), m.group(2), m.group(3)) if n), lst)
    pieces = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+|\s*&\s*", lst)]
    canon_pieces = [_canon(re.sub(r"^the\s+", "", p, flags=re.I)) for p in pieces if p]
    if canon_pieces and all(canon_pieces):
        books = canon_pieces
    elif not re.search(r"\d", rest):  # genre words only when no numbers are stated
        for pat, a, z in _GENRES:
            if re.search(pat, rest, re.I):
                books = _span(a, z); break
    if books:
        e["refs"] = {b: {"chapters": list(range(1, CHAPTERS[b] + 1)), "verse_level": False, "whole_book": True, "raw": [rest]} for b in books}
        e["refs_text"] = rest
    return e

# ---------- radical.net ----------
def _sitemap_urls(sitemap_url: str, depth=0) -> list[str]:
    r = get(sitemap_url, timeout=60)
    if not r.ok or "<" not in r.text:
        return []
    try:
        root = ET.fromstring(r.text.encode() if isinstance(r.text, str) else r.text)
    except ET.ParseError:
        return []
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text.strip() for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if e.text]
    if root.tag.endswith("sitemapindex") and depth < 2:
        urls = []
        for l in locs:
            if any(k in l for k in ("message", "podcast", "secret", "series", "video", "post")):
                urls += _sitemap_urls(l, depth + 1)
        return urls
    return locs

def radical_page_urls() -> list[str]:
    """All radical.net content URLs under the teaching prefixes, via sitemap (preferred) or WP REST."""
    urls: list[str] = []
    for sm in config.RADICAL_SITEMAP_CANDIDATES:
        urls = _sitemap_urls(sm)
        if urls:
            _log(f"radical sitemap {sm}: {len(urls)} urls")
            break
    if not urls:
        data, r = get_json(config.RADICAL_REST_TYPES)
        if data:
            for slug, t in data.items():
                base = t.get("rest_base")
                if not base or slug in ("attachment", "wp_block", "nav_menu_item"):
                    continue
                page = 1
                while True:
                    items, rr = get_json(f"{config.RADICAL_BASE}/wp-json/wp/v2/{base}?per_page=100&page={page}&_fields=link")
                    if not items:
                        break
                    urls += [i["link"] for i in items if "link" in i]
                    page += 1
                    time.sleep(config.REQUEST_SLEEP)
            _log(f"radical REST: {len(urls)} urls")
    keep = [u for u in urls if any(p in u for p in config.RADICAL_PATH_PREFIXES)]
    # PTW pages are covered by the feed; keep sermons/series/secret church/radical podcast
    keep = [u for u in keep if "/podcasts/pray-the-word/" not in u]
    return sorted(set(keep))

def harvest_radical(limit: int | None = None) -> list[dict]:
    urls = radical_page_urls()
    if limit:
        urls = urls[:limit]
    out = []
    for i, u in enumerate(urls, 1):
        r = get(u)
        if not r.ok:
            _log(f"radical page {u}: {r.status} {r.note}")
            continue
        meta = page_meta(r.text)
        title = meta["headline"] or meta["og_title"] or re.sub(r"\s*[–-]\s*Radical.*$", "", meta["title"])
        # scripture line on message pages: "In this message on Genesis 22, Pastor David Platt ..."
        body = strip_tags(r.text)
        m = re.search(r"(?:message|sermon|episode|session)[^.]{0,80}?\bon\s+([^,.]{3,80})", meta["description"] or body[:3000], re.I)
        extra = m.group(1) if m else ""
        src = "secret_church" if "/secret_church/" in u else ("radical_series" if "/series/" in u else "radical_message")
        out.append(make_entry(source=src, source_url=u, url=u, title=title, description=meta["description"],
                              author=meta["author"], era="platt", extra_ref_text=extra))
        if i % 25 == 0:
            _log(f"radical: {i}/{len(urls)}")
        time.sleep(config.REQUEST_SLEEP)
    _log(f"radical: {len(out)} pages")
    return out

def harvest_secret_church() -> list[dict]:
    out = []
    for u in config.SECRET_CHURCH_PAGES:
        r = get(u)
        if not r.ok:
            _log(f"secret church {u}: {r.status} {r.note}")
            continue
        meta = page_meta(r.text)
        title = meta["headline"] or meta["og_title"] or meta["title"]
        body = strip_tags(r.text)
        # session rows: "Session 1 ... Session 4"; most pages host sessions on the same URL
        sessions = sorted(set(re.findall(r"\b(Session\s+\d+)\b", body)))
        extra = " ".join(re.findall(r"\b(?:Genesis|Exodus|Ruth|Jonah|Matthew|1 Kings|2 Kings)\b[^.]{0,30}", body)[:5])
        out.append(make_entry(source="secret_church", source_url=u, url=u, title=title, description=meta["description"],
                              author=meta["author"] or "David Platt", era="platt", series="Secret Church",
                              extra_ref_text=extra))
        out[-1]["sessions"] = sessions
        time.sleep(config.REQUEST_SLEEP)
    _log(f"secret church: {len(out)} event pages")
    return out

# ---------- YouTube via yt-dlp ----------
def ytdlp_list(channel_url: str) -> list[dict]:
    """Flat listing of a channel's videos: id, title, url, duration, upload_date (when available)."""
    cmd = ["yt-dlp", "--flat-playlist", "--ignore-errors", "--no-warnings", "-J", channel_url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        _log("yt-dlp not installed: pip install yt-dlp"); return []
    if not p.stdout.strip():
        _log(f"yt-dlp returned nothing for {channel_url}: {p.stderr[:300]}"); return []
    data = json.loads(p.stdout)
    vids = []
    for e in data.get("entries", []) or []:
        if not e or not e.get("id"):
            continue
        vids.append({"id": e["id"], "title": e.get("title", ""), "url": f"https://www.youtube.com/watch?v={e['id']}",
                     "duration": e.get("duration"), "upload_date": e.get("upload_date") or "",
                     "description": e.get("description") or ""})
    return vids

def harvest_youtube(key: str) -> list[dict]:
    url, era, default = config.YOUTUBE_CHANNELS[key]
    vids = ytdlp_list(url)
    out = []
    for v in vids:
        out.append(make_entry(source=f"youtube_{key}", source_url=url, url=v["url"], title=v["title"],
                              description=v["description"], published=v["upload_date"],
                              duration=str(v["duration"] or ""), era=era, channel_default=default))
    _log(f"youtube_{key}: {len(out)} videos")
    return out

# ---------- TWR360 (Radical's Secret Church ministry channel; sessions with audio) ----------
TWR_SERIES = {48: 1, 49: 2, 50: 3, 51: 4, 52: 5, 37: 6, 53: 7, 54: 8, 55: 9, 56: 11, 57: 12}  # series_id -> Secret Church number
def harvest_twr360() -> list[dict]:
    import base64
    out = []
    for sid, sc in TWR_SERIES.items():
        src = f"https://www.twr360.org/programs/ministry_id,2/series_id,{sid}"
        r = get(src)
        if not r.ok: _log(f"twr360 series {sid}: {r.status}"); continue
        progs = re.findall(r'href="(?:https://www\.twr360\.org)?/programs/view/id,(\d+)"[^>]*>\s*([^<]+?)\s*</a>', r.text)
        for pid, title in dict.fromkeys(progs):
            title = html_unescape(title)
            pr = get(f"https://www.twr360.org/programs/view/id,{pid}")
            mp3 = None
            if pr.ok:
                m = re.search(r"src:\s*'(https://[^']+\.mp3[^']*)'", pr.text)
                if m: mp3 = m.group(1)
                else:
                    for b64 in re.findall(r'mediahit/id,\d+/url,([A-Za-z0-9+/~=_-]+)', pr.text):
                        u = base64.b64decode(b64.replace("~", "=") + "==").decode(errors="ignore")
                        if ".mp3" in u: mp3 = u; break
            e = make_entry(source="twr360_secret_church", source_url=src,
                           url=f"https://www.twr360.org/programs/view/id,{pid}", title=f"Secret Church {sc} – {title}",
                           author="David Platt", era="platt", series=f"Secret Church {sc}")
            e["track"] = "overview"; e["speaker"] = "Platt"; e["audio_override"] = mp3; e["sc_season"] = sc
            mm = re.search(r"Part (\d+)", title); e["sc_episode"] = int(mm.group(1)) if mm else 0
            if not e["refs"]:  # a span only when the title states one ("Survey of the New Testament")
                bare = re.sub(r"\s*[-–,]?\s*Part \d+\s*$", "", title, flags=re.I)
                for pat, a, z in _GENRES:
                    if not re.search(r"\d", bare) and re.search(pat, bare, re.I):
                        from canon import CHAPTERS
                        e["refs"] = {b: {"chapters": list(range(1, CHAPTERS[b] + 1)), "verse_level": False, "whole_book": True, "raw": [bare]} for b in _span(a, z)}
                        e["refs_text"] = bare; break
            out.append(e); time.sleep(config.REQUEST_SLEEP)
    _log(f"twr360: {len(out)} sessions, {sum(1 for e in out if e['audio_override'])} with audio")
    return out

# ---------- Buzzsprout archive: episodes older than the feed's newest 1,000 ----------
def harvest_buzzsprout_archive(key: str, show_id: int, feed_url: str, era: str = "platt") -> list[dict]:
    """The RSS feed stops at 1,000 items. The show's 'load more' pages (episodes.turbo_stream?page=N)
    each return a 1,000-episode window that moves back 25 episodes per page, so stepping 36 pages at a
    time walks the whole archive with overlap. Stops when a page adds nothing new."""
    seen, out, page = set(), [], 0
    blk = re.compile(r'<h3 id="title_episode_(\d+)"[^>]*>(.*?)</h3>\s*<p id="description_episode_\1"[^>]*>(.*?)</p>'
                     r'.*?<time datetime="([^"]+)"[^>]*>.*?</time>\s*<span\s*>[^<]*</span>\s*([\d:]+)', re.S)
    while page < 2000:
        r = get(f"https://www.buzzsprout.com/{show_id}/episodes.turbo_stream?page={page}", timeout=90)
        if not r.ok: _log(f"{key} archive page {page}: {r.status}"); break
        slugs = dict(re.findall(rf'href="/{show_id}/episodes/(\d+)-([\w-]+)"', r.text))
        new = 0
        for eid, title, desc, date, dur in blk.findall(r.text):
            if eid in seen or eid not in slugs: continue
            seen.add(eid); new += 1
            secs = 0
            for part in dur.split(":"): secs = secs * 60 + int(part)
            try: pub = datetime.strptime(date, "%B %d, %Y").date().isoformat()
            except ValueError: pub = date
            title = html_unescape(strip_tags(title)); url = f"https://www.buzzsprout.com/{show_id}/episodes/{eid}-{slugs[eid]}"
            alt = []
            if key == "ptw":
                slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"^#?\d+\s*[–-]\s*", "", title).lower()).strip("-")
                alt.append(f"https://radical.net/podcasts/pray-the-word/{slug}/")
            e = make_entry(source=key, source_url=feed_url, url=url, title=title, description=html_unescape(strip_tags(desc)),
                           published=pub, duration=str(secs), era=era, alt_urls=alt)
            e["audio_override"] = url + ".mp3"
            out.append(e)
        _log(f"{key} archive page {page}: +{new} (total {len(out)})")
        if new == 0: break
        page += 36; time.sleep(config.REQUEST_SLEEP)
    return out

# ---------- orchestration ----------
ALL_SOURCES = ["ptw", "platt_messages", "secret_church", "secret_church_podcast", "twr360", "radical", "mclean", "2819_podcast",
               "youtube_2819", "youtube_pam", "youtube_victory", "victory_podcast"]

def run(sources: list[str], radical_limit: int | None = None):
    os.makedirs(DATA, exist_ok=True)
    existing = {}
    verified = os.path.join(DATA, "catalog_verified.jsonl")
    if not os.path.exists(CATALOG) and os.path.exists(verified):
        # first run on a fresh checkout: start from the shipped catalog so nothing already found is lost
        import shutil; shutil.copy(verified, CATALOG); _log(f"seeded {CATALOG} from catalog_verified.jsonl")
    pending = []  # placeholders: title known, link not captured yet (url == "")
    if os.path.exists(CATALOG):
        for line in open(CATALOG, encoding="utf-8"):
            e = json.loads(line)
            if e.get("url"): existing[e["url"]] = e
            else: pending.append(e)
    report = {"started": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for s in sources:
        t0 = time.time(); entries = []
        try:
            if s == "ptw": entries = harvest_feed("ptw", config.PTW_FEED) + harvest_buzzsprout_archive("ptw", 112848, config.PTW_FEED)
            elif s == "platt_messages": entries = harvest_feed("platt_messages", config.PLATT_MESSAGES_FEED)
            elif s == "secret_church": entries = harvest_secret_church()
            elif s == "twr360": entries = harvest_twr360()
            elif s == "radical": entries = harvest_radical(radical_limit)
            elif s == "secret_church_podcast": entries = harvest_itunes_podcast("secret_church_podcast", config.PODCAST_SEARCH_TERMS["secret_church"], r"secret church", "platt", channel_default="Platt")
            elif s == "mclean": entries = harvest_itunes_podcast("mclean_podcast", config.PODCAST_SEARCH_TERMS["mclean"], r"mclean", "platt")
            elif s == "2819_podcast": entries = harvest_itunes_podcast("2819_podcast", config.PODCAST_SEARCH_TERMS["2819"], r"2819", "2819")
            elif s == "victory_podcast": entries = harvest_itunes_podcast("victory_podcast", config.PODCAST_SEARCH_TERMS["victory"], r"victory", "victory")
            elif s.startswith("youtube_"): entries = harvest_youtube(s.split("_", 1)[1])
            else: _log(f"unknown source {s}")
        except Exception as e:  # keep going; report the failure
            _log(f"{s}: ERROR {type(e).__name__}: {e}")
            report["sources"][s] = {"error": f"{type(e).__name__}: {e}"}
            continue
        from urllib.parse import urlparse
        _n = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
        by_title = {}
        for x in existing.values():
            by_title.setdefault(_n(x.get("title")), x)
        added = merged = 0
        for e in entries:
            old_e = existing.get(e["url"])
            if old_e is None:
                twin = by_title.get(_n(e["title"]))
                if twin and urlparse(twin["url"]).netloc != urlparse(e["url"]).netloc:
                    old_e = twin  # same episode published on another host: keep the shipped id/url
                    if e["url"] not in twin.setdefault("alt_urls", []):
                        twin["alt_urls"].append(e["url"])
            if old_e is None:
                existing[e["url"]] = e; by_title.setdefault(_n(e["title"]), e); added += 1
            else:
                # curated fields win; only fill what is missing (audio, duration, dates, description)
                for k, v in e.items():
                    if k in ("id", "url", "alt_urls"): continue
                    if v and not old_e.get(k): old_e[k] = v
                # parser-mapped sources: take the fresh full description so the passage rules see all of it
                if e.get("description") and len(e["description"]) > len(old_e.get("description") or ""):
                    old_e["description"] = e["description"]
                merged += 1
        _log(f"{s}: {added} new, {merged} matched existing entries")
        report["sources"][s] = {"count": len(entries), "seconds": round(time.time() - t0, 1)}
    # re-apply the passage rules to every parser-mapped entry (rules change; curated entries are untouched)
    from classify import remap
    for e in existing.values():
        remap(e)
    # a placeholder retires once the real episode (same title) has been harvested
    _t = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
    found = {_t(e.get("title")) for e in existing.values()}
    def _segs(e):  # "SERIES | Name | Passage | Speaker" -> name-like segments
        return {_t(x) for x in (e.get("title") or "").split("|")[:-1] if _t(x) and not re.search(r"\d", x)}
    _pk = lambda e: (e.get("source"), tuple(sorted((b, tuple(d["chapters"])) for b, d in (e.get("refs") or {}).items())))
    by_pass = {}
    for e in existing.values():
        if e.get("refs"): by_pass.setdefault(_pk(e), []).append(_segs(e))
    def _found(p):
        if _t(p.get("title")) in found: return True
        return bool(p.get("refs")) and any(_segs(p) & segs for segs in by_pass.get(_pk(p), []))
    kept = [e for e in pending if not _found(e)]
    _log(f"placeholders: {len(pending)} -> {len(kept)} still waiting for a link")
    with open(CATALOG, "w", encoding="utf-8") as f:
        for e in list(existing.values()) + kept:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    report["catalog_total"] = len(existing) + len(kept)
    json.dump(report, open(REPORT, "w"), indent=2)
    _log(f"catalog: {len(existing) + len(kept)} entries -> {CATALOG}")
    return report

if __name__ == "__main__":
    run(sys.argv[1:] or ALL_SOURCES)
