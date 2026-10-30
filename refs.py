"""Scripture reference parser.

parse_refs(text) -> list of Ref(book, chapters:set[int], verse_level:bool, raw:str, whole_book:bool)

Rules (literal, no inference):
  "Genesis 1"            -> ch 1
  "Genesis 1:1-11"       -> ch 1 (verse range inside one chapter)
  "Genesis 1-11"         -> ch 1..11
  "Genesis 1:26-2:3"     -> ch 1..2
  "Genesis 12, 15, 17"   -> 12, 15, 17
  "1 Kings 17-2 Kings 2" -> 1 Kings 17..22 + 2 Kings 1..2
  "Jude 3" / "Philemon 6" (single-chapter books) -> ch 1, verse-level
  "The Book of Ruth" / "Gospel of Matthew" / "Ruth" alone in a series title -> whole book
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from canon import BOOKS, CHAPTERS, NAME_TO_INDEX

DASH = r"[\-\u2013\u2014\u2012]"  # - – — ‒

# alias -> canonical name; longest aliases first so "1 John" wins over "John", "Song of Songs" over "Song"
_ALIASES: list[tuple[str, str]] = []
for name, _abbr, _n, _t, aliases in BOOKS:
    for a in aliases:
        _ALIASES.append((a, name))
_ALIASES.sort(key=lambda x: -len(x[0]))

def _alias_pattern(a: str) -> str:
    # allow "1 Samuel", "1Samuel", "I Samuel", "First Samuel" variants for numbered books
    m = re.match(r"^([123])\s*(.+)$", a)
    if m:
        num, rest = m.group(1), m.group(2)
        roman = {"1": "I", "2": "II", "3": "III"}[num]
        word = {"1": "First", "2": "Second", "3": "Third"}[num]
        return rf"(?:{num}|{roman}|{word})\s*{re.escape(rest)}\.?"
    return re.escape(a) + r"\.?"

_BOOK_ALT = "|".join(_alias_pattern(a) for a, _ in _ALIASES)
# A reference: Book  chapter[:verse][ -chapter[:verse] ][, chapter[:verse][-...]]*
_NUM = r"\d{1,3}"
_CV = rf"{_NUM}(?::{_NUM}(?:[a-c])?)?"
_SEG = rf"{_CV}(?:\s*{DASH}\s*{_CV})?"
REF_RE = re.compile(
    rf"(?<![A-Za-z])(?P<book>{_BOOK_ALT})\s+(?P<segs>{_SEG}(?:\s*(?:,\s*and|,|;|&|and)\s*(?:ff\.?\s*)?{_SEG})*)(?!\d)(?:\s*ff\.?)?",
    re.IGNORECASE,
)
# cross-book range: "1 Kings 17-2 Kings 2"
XBOOK_RE = re.compile(
    rf"(?<![A-Za-z])(?P<b1>{_BOOK_ALT})\s+(?P<c1>{_NUM})(?::{_NUM})?\s*{DASH}\s*(?P<b2>{_BOOK_ALT})\s+(?P<c2>{_NUM})(?::{_NUM})?",
    re.IGNORECASE,
)
WHOLE_RE = re.compile(
    rf"(?:\b(?:the\s+)?(?:book|gospel|letter|epistle|prophecy)\s+of\s+(?P<book>{_BOOK_ALT})\b)"
    rf"|(?:\b(?P<book2>{_BOOK_ALT})\s+(?:overview|survey|introduction|in\s+one\s+session)\b)",
    re.IGNORECASE,
)

@dataclass
class Ref:
    book: str
    chapters: set = field(default_factory=set)
    verse_level: bool = False
    raw: str = ""
    whole_book: bool = False

def _canon(alias_text: str) -> str | None:
    t = re.sub(r"\.", "", alias_text).strip()
    t = re.sub(r"^(I{1,3})(?:\s+|(?=[A-Z][a-z]))(?!saiah|sa\b|s\b)", lambda m: str(len(m.group(1))) + " ", t)
    t = re.sub(r"^(First|Second|Third)\s*", lambda m: {"first": "1", "second": "2", "third": "3"}[m.group(1).lower()] + " ", t, flags=re.I)
    t = re.sub(r"^([123])(?=[A-Za-z])", r"\1 ", t)
    tl = re.sub(r"\s+", "", t.lower())
    for a, name in _ALIASES:
        if re.sub(r"\s+", "", a.lower()) == tl:
            return name
    return None

def _expand(book: str, seg: str) -> tuple[set[int], bool]:
    """Expand one segment like '1', '1:3', '1-11', '1:26-2:3' into chapters."""
    n = CHAPTERS[book]
    seg = seg.replace("\u2013", "-").replace("\u2014", "-").replace("\u2012", "-")
    parts = [p.strip() for p in seg.split("-")]
    def cv(p):
        m = re.match(r"(\d+)(?::(\d+))?", p)
        return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
    c1, v1 = cv(parts[0])
    verse_level = v1 is not None
    if n == 1:                      # single-chapter book: "Jude 3" is a verse
        return {1}, True
    if len(parts) == 1:
        return ({c1} if 1 <= c1 <= n else set()), verse_level
    c2, v2 = cv(parts[1])
    if v1 is not None and v2 is None:
        # "1:3-5" -> verses 3-5 of chapter 1 (c2 is actually a verse)
        return ({c1} if 1 <= c1 <= n else set()), True
    lo, hi = sorted((c1, c2))
    hi = min(hi, n)
    return set(range(max(lo, 1), hi + 1)), (v1 is not None or v2 is not None)

def parse_refs(text: str) -> list[Ref]:
    if not text:
        return []
    refs: list[Ref] = []
    consumed: list[tuple[int, int]] = []
    # 1) cross-book ranges first
    for m in XBOOK_RE.finditer(text):
        b1, b2 = _canon(m.group("b1")), _canon(m.group("b2"))
        if not b1 or not b2 or NAME_TO_INDEX[b2] < NAME_TO_INDEX[b1]:
            continue
        c1, c2 = int(m.group("c1")), int(m.group("c2"))
        if b1 == b2:
            continue
        refs.append(Ref(b1, set(range(max(c1, 1), CHAPTERS[b1] + 1)), False, m.group(0)))
        for bi in range(NAME_TO_INDEX[b1] + 1, NAME_TO_INDEX[b2]):
            nm = BOOKS[bi][0]
            refs.append(Ref(nm, set(range(1, CHAPTERS[nm] + 1)), False, m.group(0)))
        refs.append(Ref(b2, set(range(1, min(c2, CHAPTERS[b2]) + 1)), False, m.group(0)))
        consumed.append(m.span())
    # 2) ordinary references
    for m in REF_RE.finditer(text):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        alias_text = m.group("book").rstrip(".")
        if len(alias_text) <= 3 and not (alias_text[0].isupper() or alias_text[0].isdigit()):
            continue  # "is 2", "am 2": short aliases must be capitalised
        book = _canon(m.group("book"))
        if not book:
            continue
        chapters: set[int] = set()
        verse_level = False
        for seg in re.split(r"\s*(?:,\s*and|,|;|&|\band\b)\s*", m.group("segs")):
            seg = seg.strip()
            if not seg:
                continue
            ch, vl = _expand(book, seg)
            chapters |= ch
            verse_level = verse_level or vl
        if chapters:
            refs.append(Ref(book, chapters, verse_level, m.group(0).strip()))
        consumed.append(m.span())
    # 3) whole-book mentions — only when no specific reference to that book was found
    #    ("THE GOSPEL OF MATTHEW | Matthew 27:11-14" is a series name + a passage, not a book overview)
    specific = {r.book for r in refs}
    for m in WHOLE_RE.finditer(text):
        book = _canon(m.group("book") or m.group("book2"))
        if not book or book in specific:
            continue
        refs.append(Ref(book, set(range(1, CHAPTERS[book] + 1)), False, m.group(0).strip(), whole_book=True))
    return refs

def merge_refs(refs: list[Ref]) -> dict[str, dict]:
    """Collapse to {book: {chapters:set, verse_level:bool, whole_book:bool, raw:[...]}}"""
    out: dict[str, dict] = {}
    for r in refs:
        d = out.setdefault(r.book, {"chapters": set(), "verse_level": False, "whole_book": False, "raw": []})
        d["chapters"] |= r.chapters
        d["verse_level"] = d["verse_level"] or r.verse_level
        d["whole_book"] = d["whole_book"] or r.whole_book
        if r.raw not in d["raw"]:
            d["raw"].append(r.raw)
    return out

def refs_to_text(merged: dict[str, dict]) -> str:
    return "; ".join(sorted({raw for d in merged.values() for raw in d["raw"]}))

if __name__ == "__main__":
    tests = [
        "The Power of God's Word (Genesis 1:3)",
        "Prologue: Creation — Genesis 1–11",
        "Chapter 1: Believing in God (Genesis 12, 15, and 17)",
        "CROSS TO COMMISSION | But After | Matthew 26:30-35 | Philip Anthony Mitchell",
        "A POWER IN SILENCE | MATTHEW 27:11-14 | PHILIP ANTHONY MITCHELL",
        "Secret Church 24: The Book of Ruth",
        "Elijah: 1 Kings 17–2 Kings 2",
        "Jude 3 and Philemon 6",
        "Psalm 23; Ps. 1:1-2",
        "God's Good Design in Creation, Part 2 (Genesis 1-2) | David Platt",
        "Genesis 1:26–2:3 and John 3:16",
        "ACTS I & II | Be A Witness | Acts 1:1-8 | Philip Anthony Mitchell",
        "The Gospel of Matthew",
        "I John 4:7-12 and Song of Songs 2",
    ]
    for t in tests:
        m = merge_refs(parse_refs(t))
        print(t, "->", {k: (sorted(v["chapters"])[:6] + (["…"] if len(v["chapters"]) > 6 else []), v["verse_level"], v["whole_book"]) for k, v in m.items()})
