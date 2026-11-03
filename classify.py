"""Turn a raw harvested item into a normalized catalog entry."""
from __future__ import annotations
import hashlib, re
from canon import CHAPTERS
from refs import parse_refs, merge_refs, refs_to_text
from config import PAM_NAME_RE

OVERVIEW_WORDS = re.compile(
    r"\b(survey of|overview|introduction to|intro to|an introduction|whole bible|bible in one|in one session)\b", re.I)
PLATT_RE = re.compile(r"david\s+platt", re.I)
GUEST_HINT_RE = re.compile(r"\b(guest|with pastor|featuring)\b", re.I)

def _id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]

def detect_speaker(source: str, title: str, description: str, author: str, channel_default: str | None) -> tuple[str, str]:
    """Return (speaker, how). speaker ∈ {'Platt','PAM','guest:<name>','unknown'}"""
    blob = f"{title} || {description} || {author}"
    if source in ("ptw", "platt_messages"):
        # Platt's own feeds; flag a guest only when the item itself names another preacher
        m = re.search(r"\b(sermon|message)\s+(from|by)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", description or "")
        if m and not PLATT_RE.search(m.group(3)):  # "a message from David Platt" is his own
            return f"guest:{m.group(3)}", "feed-description"
        return "Platt", "feed-owner"
    if source.startswith("radical") or source == "secret_church":
        if author and not PLATT_RE.search(author):
            return f"guest:{author}", "page-author"
        return ("Platt", "page-author") if (PLATT_RE.search(blob) or author) else ("unknown", "no-author")
    if source.startswith("youtube") or source in ("2819_podcast", "victory_podcast", "pam_podcast"):
        # The speaker is the trailing "| Name" in the title (CLAUDE_CODE_PROMPT rule 3). Channel descriptions
        # name PAM on every episode ("messages from Philip Anthony Mitchell and guest communicators"), so the
        # description never decides the speaker when the title names one.
        m = re.search(r"\|\s*([^|]{3,60}?)\s*$", title)
        if m and re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}|^PAM$", m.group(1).strip(), re.I) and not re.search(r"\d", m.group(1)):
            who = m.group(1).strip()
            if re.search(PAM_NAME_RE, who, re.I):
                return "PAM", "title-suffix"
            return f"guest:{re.sub(r'^(?:Elder|Pastor|Minister|Rev\.?|Dr\.?)\s+', '', who, flags=re.I)}", "title-suffix"
        if re.search(PAM_NAME_RE, title, re.I):
            return "PAM", "named-in-title"
        if channel_default == "PAM":
            return "PAM", "channel-default"
        return "unknown", "no-name"
    if source.startswith("skip_"):  # Calvary Church feeds: each episode's author is its speaker
        a = (author or "").strip()
        if not a or re.fullmatch(r"(?:Pastor\s+)?Skip Heitzig", a, re.I):
            return "Skip", "episode-author"
        return f"guest:{re.sub(r'^(?:Pastor|Dr\.?)\s+', '', a)}", "episode-author"
    if source.startswith("davey_"):  # his own feeds
        return "Davey", "feed-owner"
    if source == "street_preachers":  # PAM's own podcast (with Tim Timberlake)
        return "PAM", "feed-owner"
    if source in ("mclean_podcast", "mclean_oceans"):
        if PLATT_RE.search(title):  # McLean posts every campus pastor; only a title naming him is Platt
            return "Platt", "named-in-title"
        if PLATT_RE.search(author or ""):  # the church's own record names him as the preacher
            return "Platt", "church-app-speaker"
        return (f"guest:{author}" if author else "unknown"), "feed-author"
    return "unknown", "none"

def detect_track(source: str, title: str, description: str, merged_refs: dict) -> str:
    if source in ("ptw", "davey_journey"):
        return "devotional"
    if source == "secret_church":
        return "overview"
    if OVERVIEW_WORDS.search(title):          # title-level signal only; descriptions mention series names
        return "overview"
    # whole-book or ≥60% of a book's chapters in one message = overview
    for book, d in merged_refs.items():
        if d["whole_book"]:
            return "overview"
        if len(d["chapters"]) >= 4 and len(d["chapters"]) / CHAPTERS[book] >= 0.6:
            return "overview"
    return "sermon"

# Sources whose passages come from the parser (never hand-curated) — re-mapped whenever the rules change.
REPARSE_SOURCES = {"ptw", "platt_messages", "2819_podcast", "street_preachers", "mclean_oceans",
                   "davey_sermons", "davey_wfth", "davey_journey", "victory_podcast", "mclean_podcast", "radical_message",
                   "youtube_2819", "youtube_pam", "youtube_victory", "skip_church", "skip_connect"}
MAIN_TEXT_RE = re.compile(r"\b(?:message|sermon|episode|teaching|talk|study)\b[^.]{0,60}?"
                          r"\b(?:from|on|through|in|of|unpacks|walks through|looks at|explores|expounds)\s+", re.I)

def _first_ref(text: str) -> dict:
    """The first chapter-level reference in text (by position), never a bare whole-book mention."""
    found = [(text.find(r.raw), r) for r in parse_refs(text) if not r.whole_book]
    found = [x for x in found if x[0] >= 0]
    if not found:
        return {}
    found.sort(key=lambda x: x[0])
    chain, end = [found[0][1]], found[0][0] + len(found[0][1].raw)
    for p, r in found[1:]:  # "from Acts 2:42–47 and Acts 4:32–37": passages joined directly to the first
        if p >= end and re.fullmatch(r"[\s,;&]*(?:and\s*)?", text[end:p]):
            chain.append(r); end = p + len(r.raw)
        elif p >= end:
            break
    return merge_refs(chain)

_USFM = {"GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers", "DEU": "Deuteronomy", "JOS": "Joshua",
         "JDG": "Judges", "JUG": "Judges", "RUT": "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
         "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah", "EST": "Esther", "JOB": "Job",
         "PSA": "Psalms", "PRO": "Proverbs", "ECC": "Ecclesiastes", "SNG": "Song of Solomon", "SOS": "Song of Solomon",
         "ISA": "Isaiah", "JER": "Jeremiah", "LAM": "Lamentations", "EZK": "Ezekiel", "EZE": "Ezekiel", "DAN": "Daniel",
         "HOS": "Hosea", "JOL": "Joel", "JOE": "Joel", "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah", "MIC": "Micah",
         "NAM": "Nahum", "NAH": "Nahum", "HAB": "Habakkuk", "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah",
         "MAL": "Malachi", "MAT": "Matthew", "MRK": "Mark", "MAR": "Mark", "LUK": "Luke", "JHN": "John", "JOH": "John",
         "ACT": "Acts", "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians", "GAL": "Galatians",
         "EPH": "Ephesians", "PHP": "Philippians", "PHI": "Philippians", "COL": "Colossians", "1TH": "1 Thessalonians",
         "2TH": "2 Thessalonians", "1TI": "1 Timothy", "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon",
         "HEB": "Hebrews", "JAS": "James", "JAM": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John",
         "2JN": "2 John", "3JN": "3 John", "JUD": "Jude", "REV": "Revelation"}

def flight_books(code: str) -> list[str]:
    from config import SKIP_FLIGHT_BOOKS
    return SKIP_FLIGHT_BOOKS.get(code) or ([_USFM[code]] if code in _USFM else [])

def stated_refs(source: str, title: str, description: str, extra_ref_text: str = "") -> tuple[dict, str]:
    """Which passage a teaching is ON, stated by the publisher — not every passage it mentions.
    1. a passage in the title;  2. the passage the description names as the main text
    ("In this message from Genesis 1, …");  3. otherwise the first passage the description cites.
    Whole-book mentions ("the book of Romans") in a description never place a teaching."""
    t = merge_refs(parse_refs(title))
    if t:
        return t, "title"
    fl = re.match(r"\s*Flight\s+([1-3]?[A-Z]{2,4}?)\d{1,2}\b", title or "")
    if fl and source.startswith("skip_"):  # Bible from 30,000 Feet: the flight code names the book(s)
        books = flight_books(fl.group(1))
        if books:
            return merge_refs(parse_refs(", ".join(f"the book of {b}" for b in books))), "flight-code"
    if extra_ref_text:
        x = merge_refs(parse_refs(extra_ref_text))
        if x:
            return x, "stated"
    if source not in REPARSE_SOURCES:  # curated / survey sources keep the full literal parse
        return merge_refs(parse_refs(f"{title}\n{description}")), "full"
    d = description or ""
    for m in MAIN_TEXT_RE.finditer(d):
        x = _first_ref(d[m.end():m.end() + 80])
        if x and d[m.end():m.end() + 80].find(next(iter(x.values()))["raw"][0]) <= 12:
            return x, "description-main-text"
    x = _first_ref(d)
    return (x, "description-first") if x else ({}, "none")

def make_entry(*, source: str, source_url: str, url: str, title: str, description: str = "",
               published: str = "", duration: str = "", author: str = "", era: str = "",
               channel_default: str | None = None, series: str = "", alt_urls: list[str] | None = None,
               extra_ref_text: str = "") -> dict:
    merged, ref_how = stated_refs(source, title, description, extra_ref_text)
    if not merged: merged, ref_how = spoken_refs(_id(url))
    speaker, how = detect_speaker(source, title, description, author, channel_default)
    track = detect_track(source, title, description, merged)
    if not era:
        era = "platt" if speaker == "Platt" or source in ("ptw", "platt_messages", "secret_church") or source.startswith("radical") else "unknown"
    return {
        "id": _id(url),
        "source": source,
        "source_url": source_url,
        "url": url,
        "alt_urls": alt_urls or [],
        "title": title.strip(),
        "description": (description or "").strip()[:4000],
        "published": published,
        "duration": duration,
        "author_raw": author,
        "speaker": speaker,
        "speaker_evidence": how,
        "era": era,
        "track": track,
        "series": series,
        "refs": {b: {"chapters": sorted(d["chapters"]), "verse_level": d["verse_level"],
                     "whole_book": d["whole_book"], "raw": d["raw"]} for b, d in merged.items()},
        "refs_text": refs_to_text(merged),
        "ref_how": ref_how,
    }


_SPOKEN = None
def spoken_refs(entry_id: str) -> tuple[dict, str]:
    """The passage the preacher announces at the start of the sermon ("turn with me to Acts 1"), heard by speech
    recognition (tools/spoken_refs.py -> data/spoken_refs.json). Used only when the publisher's listing names none."""
    global _SPOKEN
    if _SPOKEN is None:
        import json, os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spoken_refs.json")
        _SPOKEN = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    x = _SPOKEN.get(entry_id)
    if not x or not x.get("ref"): return {}, "none"
    m = merge_refs(parse_refs(x["ref"]))
    return (m, "spoken") if m else ({}, "none")


def remap(e: dict) -> dict:
    """Re-apply the passage rules to a parser-mapped entry (keeps id/url/audio)."""
    if e.get("source") not in REPARSE_SOURCES or not e.get("url"):
        return e
    merged, how = stated_refs(e["source"], e["title"], e.get("description", ""))
    if not merged: merged, how = spoken_refs(e.get("id", ""))
    e["refs"] = {b: {"chapters": sorted(d["chapters"]), "verse_level": d["verse_level"],
                     "whole_book": d["whole_book"], "raw": d["raw"]} for b, d in merged.items()}
    e["refs_text"] = refs_to_text(merged); e["ref_how"] = how
    if e["source"] in ("2819_podcast", "victory_podcast", "mclean_podcast", "mclean_oceans") or e["source"].startswith("youtube_") and e["source"] != "youtube_radical":
        e["speaker"], e["speaker_evidence"] = detect_speaker(e["source"], e["title"], e.get("description", ""), e.get("author_raw", ""), None)
    e["track"] = detect_track(e["source"], e["title"], e.get("description", ""), merged)
    return e
