"""Verify every catalog URL. Writes data/verification_log.jsonl and data/catalog_verified.jsonl.

Tier:
  V2   fetched, live (HTTP 2xx / oEmbed 200), fetched title matches claimed title
  V1   publisher-issued URL but the host blocked/timed out the check (403/429/0) — not yet confirmed
  FAIL 404/410, or the page's title does not match the claimed item -> excluded from the ledger
Run:  python run.py verify [--force] [--limit N]
"""
from __future__ import annotations
import difflib, json, os, re, sys, time
from datetime import datetime, timezone, timedelta

import config
from net import get, page_meta, youtube_oembed
from refs import parse_refs, merge_refs

DATA = os.path.join(os.path.dirname(__file__), "data")
CATALOG = os.path.join(DATA, "catalog.jsonl")
LOG = os.path.join(DATA, "verification_log.jsonl")
VERIFIED = os.path.join(DATA, "catalog_verified.jsonl")

def _log(msg): print(f"[verify] {msg}", flush=True)

SUFFIXES = [r"\s*[-–|]\s*pray the word with david platt\s*$", r"\s*[-–|]\s*radical(\.net)?\s*$",
            r"\s*[-–|]\s*david platt messages\s*$", r"\s*[-–|]\s*youtube\s*$", r"\s*[-–|]\s*2819 church\s*$"]

def norm(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"^#?\d+\s*[–\-:]\s*", "", t)          # "#299 – " episode numbers
    for s in SUFFIXES:
        t = re.sub(s, "", t)
    t = t.replace("&amp;", "&").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def title_match(claimed: str, fetched: str) -> tuple[bool, float]:
    a, b = norm(claimed), norm(fetched)
    if not a or not b:
        return False, 0.0
    if a in b or b in a:
        return True, 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio >= config.TITLE_MATCH_MIN, round(ratio, 3)

def check_url(url: str, claimed_title: str) -> dict:
    rec = {"url": url, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "status": 0, "final_url": url, "fetched_title": "", "fetched_desc": "", "match": False, "ratio": 0.0,
           "tier": "V1", "note": ""}
    if "youtube.com/watch" in url or "youtu.be/" in url:
        data, r = youtube_oembed(url)
        rec["status"] = r.status
        if data:
            rec["fetched_title"] = data.get("title", ""); rec["fetched_desc"] = data.get("author_name", "")
        elif r.status in (401, 403, 404):
            rec["tier"] = "FAIL"; rec["note"] = "video private/removed"; return rec
        else:
            rec["note"] = f"oembed {r.status} {r.note}"; return rec
    elif re.search(r"\.(mp3|m4a|aac|wav)(\?|$)", url, re.I):
        # a direct audio link has no page title to compare: it passes when it answers as audio (first bytes only)
        import requests
        try:
            a = requests.get(url, headers={"Range": "bytes=0-1023", "User-Agent": "Mozilla/5.0"}, timeout=40, stream=True)
            rec["status"], rec["final_url"] = a.status_code, a.url
            if a.status_code in (200, 206) and a.headers.get("content-type", "").startswith(("audio", "application/octet-stream")):
                rec["tier"] = "V2"; rec["note"] = "audio file answers"
            elif a.status_code in (404, 410):
                rec["tier"] = "FAIL"; rec["note"] = "gone"
            else:
                rec["note"] = f"audio not confirmed {a.status_code} {a.headers.get('content-type', '')}"
        except Exception as ex:
            rec["note"] = f"unreachable {type(ex).__name__}"
        return rec
    else:
        r = get(url)
        rec["status"], rec["final_url"] = r.status, r.final_url
        if r.status in (404, 410):
            rec["tier"] = "FAIL"; rec["note"] = "gone"; return rec
        if not r.ok:
            rec["note"] = f"blocked/unreachable {r.status} {r.note}"; return rec
        meta = page_meta(r.text)
        rec["fetched_title"] = meta["headline"] or meta["og_title"] or meta["title"]
        rec["fetched_desc"] = (meta["description"] or "")[:300]
    ok, ratio = title_match(claimed_title, rec["fetched_title"])
    rec["match"], rec["ratio"] = ok, ratio
    if ok:
        rec["tier"] = "V2"
    else:
        rec["tier"] = "FAIL"; rec["note"] = "title mismatch"
    # passage visible on the fetched page? (informational; the title match already pins the item)
    fetched_refs = merge_refs(parse_refs(f"{rec['fetched_title']} {rec['fetched_desc']}"))
    rec["fetched_refs"] = "; ".join(sorted({raw for d in fetched_refs.values() for raw in d["raw"]}))
    return reconsider(rec, claimed_title)

def reconsider(rec: dict, claimed_title: str) -> dict:
    """A title 'mismatch' where the live page names the same passage is the same episode under the
    publisher's real title (our copy had a placeholder like 'Pray the Word on Jeremiah 18:6')."""
    if rec.get("note") != "title mismatch" or not rec.get("fetched_title"):
        return rec
    if re.search(r"youtube\.com/watch|youtu\.be/", rec.get("url", "")) and re.search(r"^radical$|2819 church|philip anthony mitchell", rec.get("fetched_desc", ""), re.I):
        rec["tier"] = "V2"; rec["note"] = "official channel video; its own title adopted"; rec["adopt_title"] = True
        return rec
    mine = {b: tuple(sorted(d["chapters"])) for b, d in merge_refs(parse_refs(claimed_title)).items()}
    theirs = {b: tuple(sorted(d["chapters"])) for b, d in merge_refs(parse_refs(rec["fetched_title"])).items()}
    if mine and mine == theirs:
        rec["tier"] = "V2"; rec["note"] = "same passage; publisher's title adopted"; rec["adopt_title"] = True
    return rec

def load_log() -> dict:
    out = {}
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            rec = json.loads(line); out[rec["url"]] = rec
    return out

def run(force: bool = False, limit: int | None = None, sources: list[str] | None = None):
    entries = [json.loads(l) for l in open(CATALOG, encoding="utf-8")]
    if sources:
        entries = [e for e in entries if e["source"] in sources]
    log = load_log()
    ttl = datetime.now(timezone.utc) - timedelta(days=config.VERIFY_TTL_DAYS)
    todo = []
    for e in entries:
        for u in [e["url"]] + e.get("alt_urls", []):
            if not u: continue  # placeholder with no link yet
            rec = log.get(u)
            fresh = rec and datetime.fromisoformat(rec["checked_at"]) > ttl and rec["tier"] != "V1"
            if force or not fresh:
                todo.append((u, e["title"]))
    if limit:
        todo = todo[:limit]
    _log(f"{len(todo)} urls to check ({len(entries)} entries)")
    with open(LOG, "a", encoding="utf-8") as f:
        for i, (u, t) in enumerate(todo, 1):
            rec = check_url(u, t)
            log[u] = rec
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 50 == 0:
                _log(f"{i}/{len(todo)}  V2={sum(1 for r in log.values() if r['tier']=='V2')} "
                     f"V1={sum(1 for r in log.values() if r['tier']=='V1')} FAIL={sum(1 for r in log.values() if r['tier']=='FAIL')}")
            time.sleep(config.REQUEST_SLEEP)
    # stamp entries
    all_entries = [json.loads(l) for l in open(CATALOG, encoding="utf-8")]
    with open(VERIFIED, "w", encoding="utf-8") as f:
        for e in all_entries:
            if not e.get("url"):  # placeholder: keep it PENDING, never shown on the road
                e["tier"] = "PENDING"; e["primary_url"] = ""
                f.write(json.dumps(e, ensure_ascii=False) + "\n"); continue
            main = log.get(e["url"], {"tier": "V1", "note": "unchecked"})
            main = reconsider(dict(main), e["title"])
            if main.get("note") == "title mismatch" and re.search(r"\.(mp3|m4a|aac|wav)(\?|$)", e["url"], re.I):
                main.update({"tier": "V1", "note": "audio link: re-check as audio"})  # older check compared an mp3's 'title'
            if main.get("adopt_title"):
                e["title"] = re.sub(r"\s+-\s+(Pray the Word with David Platt|Wisdom for the Heart|YouTube)\s*$", "", main["fetched_title"]).strip()
            e["tier"], e["verify_note"], e["verified_at"] = main["tier"], main.get("note", ""), main.get("checked_at", "")
            e["fetched_title"] = main.get("fetched_title", "")
            # prefer a verified radical.net page over the Buzzsprout page for Pray the Word
            good_alts = [u for u in e.get("alt_urls", []) if log.get(u, {}).get("tier") == "V2"]
            if good_alts and e["source"] == "ptw":
                e["primary_url"] = good_alts[0]
            else:
                e["primary_url"] = e["url"]
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    tiers = {}
    for e in all_entries:
        tiers[e["tier"]] = tiers.get(e["tier"], 0) + 1
    _log(f"entries by tier: {tiers}")
    return tiers

if __name__ == "__main__":
    run(force="--force" in sys.argv)
