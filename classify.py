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
        if re.search(r"\b(sermon|message)\s+(from|by)\s+(?!david platt)([A-Z][a-z]+\s+[A-Z][a-z]+)", description or ""):
            m = re.search(r"\b(sermon|message)\s+(from|by)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", description)
            return f"guest:{m.group(3)}", "feed-description"
        return "Platt", "feed-owner"
    if source.startswith("radical") or source == "secret_church":
        if author and not PLATT_RE.search(author):
            return f"guest:{author}", "page-author"
        return ("Platt", "page-author") if (PLATT_RE.search(blob) or author) else ("unknown", "no-author")
    if source.startswith("youtube") or source in ("2819_podcast", "victory_podcast", "pam_podcast"):
        if re.search(PAM_NAME_RE, blob, re.I):
            return "PAM", "named-in-title"
        # 2819 titles end "| Speaker Name"; capture a non-PAM speaker
        m = re.search(r"\|\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3})\s*$", title)
        if m:
            return f"guest:{m.group(1).strip()}", "title-suffix"
        if channel_default == "PAM":
            return "PAM", "channel-default"
        return "unknown", "no-name"
    if source in ("mclean_podcast", "mclean_oceans"):
        if PLATT_RE.search(blob):
            return "Platt", "named"
        return (f"guest:{author}" if author else "unknown"), "feed-author"
    return "unknown", "none"

def detect_track(source: str, title: str, description: str, merged_refs: dict) -> str:
    if source == "ptw":
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

def make_entry(*, source: str, source_url: str, url: str, title: str, description: str = "",
               published: str = "", duration: str = "", author: str = "", era: str = "",
               channel_default: str | None = None, series: str = "", alt_urls: list[str] | None = None,
               extra_ref_text: str = "") -> dict:
    merged = merge_refs(parse_refs(f"{title}\n{description}\n{extra_ref_text}"))
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
        "description": (description or "").strip()[:600],
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
    }
