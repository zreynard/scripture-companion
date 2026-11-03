"""Build out/scripture-companion.html — a single-file, installable web app:
podcast-style player (Media Session lock-screen controls, resume, speed, auto-advance),
books → chapters → episodes with progress bars, Secret Church in order, Pray the Word list.
Progress lives in localStorage; export/import as JSON. Run: python app_build.py
"""
from __future__ import annotations
import json, os, re, shutil
from collections import defaultdict
from canon import BOOKS, CHAPTERS, TESTAMENT
from refs import parse_refs
from datetime import date as _dd
import config
import years
import topics
from atlas import Atlas
ATLAS = Atlas()
import glob as _glob
SUMMARIES = {}
for _f in sorted(_glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "summaries", "g*.json"))):
    SUMMARIES.update(json.load(open(_f, encoding="utf-8")))
SHOW_YEARS = os.environ.get("YEARS", "1") == "1"  # best-estimate years on each stop and beside each book (YEARS=0 hides them)

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(HERE, "data", "catalog_verified.jsonl")
NARR = os.path.join(HERE, "data", "narrative_order.json")
VERSION = 101  # bump on every shipped build; also busts the service-worker cache
OUT = os.path.join(HERE, "out", f"scripture-companion-v{VERSION}.html")
SITE = os.path.join(HERE, "out", "site")  # deploy this folder (Netlify drop / GitHub Pages)
PWA = os.path.join(HERE, "pwa")

def audio_url(e: dict) -> str | None:
    """Publisher audio file for an entry. Buzzsprout serves <episode page>.mp3; the feeds confirmed the pattern."""
    if e.get("audio_override"):
        return e["audio_override"]
    for u in [e.get("primary_url") or e["url"]] + e.get("alt_urls", []):
        if re.search(r"buzzsprout\.com/\d+/episodes/\d+-[\w-]+$", u):
            return u + ".mp3"
    for u in [e["url"]] + e.get("alt_urls", []):
        m = re.search(r"buzzsprout\.com/(\d+)/(\d+)$", u)
        if m:  # short id form: Buzzsprout redirects the id-only mp3 to the full file
            return f"https://www.buzzsprout.com/{m.group(1)}/{m.group(2)}.mp3"
    return None

def _first_verse(d: dict) -> tuple:
    """(chapter, verse) where a passage starts, for ordering a series that was posted on one day."""
    for raw in d.get("raw", []):
        m = re.search(r"(\d+):(\d+)", raw)
        if m: return (int(m.group(1)), int(m.group(2)))
    return (min(d.get("chapters") or [0]), 0)

def iso_date(s) -> str:
    """'Sun, 04 Feb 2024 02:00:00 -0600' (RSS) or '2024-02-04…' -> '2024-02-04'."""
    s = (s or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s): return s[:10]
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return ""

def is_walk(title):
    """A walk-through message: titled only by its passage ("Genesis 1", "Expound: Romans 9-10:4 - Part A")."""
    rest = title or ""
    for r in parse_refs(rest): rest = rest.replace(r.raw, " ")
    return bool(parse_refs(title or "")) and not re.search(r"[A-Za-z]{2,}", re.sub(r"\b(?:and|part|review|expound)\b", " ", rest, flags=re.I))

def big_picture(items):
    """Big Picture: whole-Bible series heard in order, each with its own place. Episodes are items already in the app."""
    sc = sorted([i for i in items.values() if i["src"] == "secret_church_podcast" and i["sc"] and i["sc"][0] in (1, 2)], key=lambda i: tuple(i["sc"]))
    flights = sorted([i for i in items.values() if i["src"] == "skip_archive" and re.match(r"\s*Flight\b", i["t"])], key=lambda i: (i["date"], i["t"]))
    out = [{"id": "survey", "title": "Secret Church — Bible Survey", "by": "David Platt", "art": "survey",
            "desc": "The whole Bible in two nights. Secret Church 1 surveys the Old Testament; Secret Church 2 the New. The shortest way to see the entire story at once.",
            "parts": [["The Old Testament · Secret Church 1", [i["id"] for i in sc if i["sc"][0] == 1]], ["The New Testament · Secret Church 2", [i["id"] for i in sc if i["sc"][0] == 2]]]},
           {"id": "30k", "title": "The Bible from 30,000 Feet", "by": "Skip Heitzig", "art": "30k",
            "desc": "A flight over all 66 books, from Genesis to Revelation: the setting, the shape and the themes of each. Calvary Albuquerque, 2018–2020.",
            "parts": [["", [i["id"] for i in flights]]]}]
    # Skip's flights by the books they cover ("Flight GEN02" -> "Genesis · Part 2")
    code = lambda i: re.sub(r"^\s*Flight\s*", "", i["t"])
    stem = lambda i: re.sub(r"\d+$", "", code(i)) if not re.match(r"^\d", code(i)) else re.sub(r"\d$", "", code(i))
    count = defaultdict(int)
    for i in flights: count[stem(i)] += 1
    names = {}
    for i in flights:
        bks = re.findall(r"the book of ([^;]+)", i["pass"] or "")
        bks.sort(key=lambda n: [b[0] for b in BOOKS].index(n) if n in [b[0] for b in BOOKS] else 99)
        nm = "Between the Testaments" if stem(i) == "INT" else (", ".join(bks[:-1]) + " and " + bks[-1] if len(bks) > 1 else (bks[0] if bks else code(i)))
        n = int(re.search(r"(\d)$", code(i)).group(1)) if re.search(r"\d$", code(i)) else 1
        names[i["id"]] = nm + (f" · Part {n}" if count[stem(i)] > 1 else "")
    out[1]["names"] = names
    out[0]["unit"], out[1]["unit"] = "session", "flight"
    out[0]["group"] = out[1]["group"] = "bp"
    return [x for x in out if any(ids for _, ids in x["parts"])]

def main():
    # where each episode's intro ends, found by tools/intro_detect.py (data/intro_skip/<source>.json: {id: seconds})
    INTROS = {}
    OUTROS = {}  # seconds before the end where the teaching's last word ends (data/intro_skip/<source>_end.json)
    for f in sorted(_glob.glob(os.path.join(HERE, "data", "intro_skip", "*.json"))):
        if f.endswith("_opening.json"): continue
        (OUTROS if f.endswith("_end.json") else INTROS).update(json.load(open(f, encoding="utf-8")))
    entries = [json.loads(l) for l in open(VERIFIED, encoding="utf-8")]
    narr = {(o["book"], o["chapter"]): o["seq"] for o in json.load(open(NARR))}
    team = {f"guest:{n}" for n in config.PAM_CHURCH_PREACHERS}
    skip_guest = lambda e: e["source"].startswith("skip_") and e["speaker"].startswith("guest:")  # Calvary Church guests keep Skip's series unbroken
    # Skip Heitzig: his verse-by-verse walk-throughs and Bible from 30,000 Feet, not his topical Sunday sermons
    skip_kept = lambda e: not e["source"].startswith("skip_") or is_walk(e["title"]) or re.match(r"\s*Flight\b", e["title"])
    usable = [e for e in entries if e["tier"] in ("V2", "V1") and e["source"] not in config.OFF_ROAD_SOURCES and skip_kept(e) and (e["speaker"] in ("Platt", "PAM", "Davey", "Skip") or e["speaker"] in team or skip_guest(e) or e["speaker"].startswith("fearless:"))]
    items, by_chapter, by_book_ov, spans = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    CH, WALK, VS = {}, {}, {}  # chapters per book for each item; WALK = titled only by its passage (a walk-through message); VS = verses
    VC = {}
    def vcount(book, c):
        if book not in VC:
            try: VC[book] = [len(x) for x in json.load(open(os.path.join(HERE, "data", "bible", book + ".json"), encoding="utf-8"))["chapters"]]
            except (OSError, ValueError, KeyError): VC[book] = []
        return VC[book][c - 1] if 0 < c <= len(VC[book]) else 30
    def verses_of(book, d):
        """The verses a reference covers in this book, as (chapter, verse) pairs (whole chapters when no verses are named)."""
        out = set()
        for raw in d.get("raw") or []:
            m = re.match(r"^\s*(?:[1-3]|I{1,3}|First|Second|Third)?\s*[A-Za-z][A-Za-z. ]*?\s*(\d.*)$", raw)
            tail = (m.group(1) if m else "").replace("\u2013", "-").replace("\u2014", "-")
            cur = None
            for seg in re.split(r"\s*(?:,|;|&|\band\b)\s*", tail):
                seg = seg.strip().rstrip("abc")
                if not seg: continue
                x = re.match(r"^(\d+)(?::(\d+))?(?:\s*-\s*(\d+)(?::(\d+))?)?", seg)
                if not x: continue
                a, av, b, bv = [int(g) if g else None for g in x.groups()]
                if av is None and b is not None and bv is None and cur is not None and ":" not in seg:
                    pass
                if av is not None and b is not None and bv is None:      # 3:16-21 → verses in one chapter
                    sc, sv, ec, ev = a, av, a, b
                elif av is None and b is None and cur is not None and ":" not in seg and a <= vcount(book, cur) and re.search(r":", tail) and False:
                    sc = sv = ec = ev = None
                else:
                    sc, sv = a, (av or 1)
                    ec = b if b is not None else a
                    ev = bv if bv is not None else (av if (b is None and av is not None) else vcount(book, ec))
                cur = ec
                for c in range(sc, ec + 1):
                    lo = sv if c == sc else 1; hi = ev if c == ec else vcount(book, c)
                    out.update((c, v) for v in range(lo, hi + 1))
        if not out:
            for c in d.get("chapters") or []: out.update((c, v) for v in range(1, vcount(book, c) + 1))
        return out
    item_books, title_states, ref_how, cited, first_verse = {}, {}, {}, {}, {}
    order = [b[0] for b in BOOKS]; OT = order[:39]; NT = order[39:]
    def span_label(bks):
        if set(bks) >= set(OT): return "the Old Testament"
        if set(bks) >= set(NT): return "the New Testament"
        lands = [("Genesis","Deuteronomy","The Law"),("Joshua","Esther","History"),("Job","Song of Solomon","Wisdom & Song"),("Isaiah","Daniel","Major Prophets"),("Hosea","Malachi","Minor Prophets"),("Matthew","John","The Gospels"),("Acts","Acts","The Church Begins"),("Romans","Philemon","Letters of Paul"),("Hebrews","Jude","General Letters")]
        for a, z, lab in lands:
            if set(bks) == set(order[order.index(a):order.index(z)+1]): return lab
        idx = sorted(order.index(b) for b in bks)
        return f"{order[idx[0]]}–{order[idx[-1]]}" if idx[-1]-idx[0] == len(idx)-1 else ", ".join(bks)
    # TWR360 rebroadcasts Secret Church nights cut into four parts: where the podcast has the whole night, one copy is enough
    pod_nights = {e.get("sc_season") for e in usable if e["source"] == "secret_church_podcast" and e.get("sc_season")}
    usable = [e for e in usable if not (e["source"] == "twr360_secret_church" and e.get("sc_season") in pod_nights)]
    for e in usable:
        it = {"id": e["id"], "t": e["title"], "who": "Fearless" if e["speaker"].startswith("fearless:") else "PAM" if (e["speaker"] == "PAM" or e["speaker"] in team) else ("Skip" if skip_guest(e) else e["speaker"] if e["speaker"] in ("Davey", "Skip") else "Platt"),
              "show": config.SHOWS.get(e["source"]),
              **(({"s": INTROS[e["id"]]} if INTROS[e["id"]] else {}) if e["id"] in INTROS else {"s": 13} if e["source"] == "skip_archive" and re.match(r"\s*Flight\b", e["title"]) else {"s": config.INTRO_SKIP[e["source"]]} if config.INTRO_SKIP.get(e["source"]) else {}),
              "by": ("Pastor " + e["speaker"].split(":", 1)[1] if e["speaker"] != "fearless:Fearless Church" else None) if e["speaker"].startswith("fearless:") else e["speaker"].split(":", 1)[1] if (e["speaker"] in team or skip_guest(e)) else None,
              "era": e["era"], "tr": e["track"], "src": e["source"], "url": e.get("primary_url") or e["url"],
              "audio": audio_url(e), "dur": int(e["duration"]) if str(e["duration"]).isdigit() else 0,
              "date": iso_date(e.get("published")), "pass": e.get("refs_text", ""), "tier": e["tier"],
              "sc": [e.get("sc_season"), e.get("sc_episode")] if e.get("sc_season") else None,
              **({"e": OUTROS[e["id"]]} if OUTROS.get(e["id"]) else {})}
        items[it["id"]] = it
        item_books[it["id"]] = set(e["refs"])
        CH[it["id"]] = {b: set(d["chapters"]) for b, d in e["refs"].items()}
        VS[it["id"]] = {b: verses_of(b, d) for b, d in e["refs"].items()}
        WALK[it["id"]] = is_walk(e["title"])
        first_verse[it["id"]] = {b: _first_verse(d) for b, d in e["refs"].items()}
        ref_how[it["id"]] = e.get("ref_how", "curated")
        cited[it["id"]] = len({(r.book, tuple(sorted(r.chapters))) for r in parse_refs(e.get("description", "")) if not r.whole_book})
        title_states[it["id"]] = bool(parse_refs(e["title"]))
        ov_books = [b for b, d in e["refs"].items() if e["track"] == "overview" and (d["whole_book"] or len(d["chapters"]) / CHAPTERS[book] >= 0.6)] if False else \
                   [b for b, d in e["refs"].items() if e["track"] == "overview" and (d["whole_book"] or len(d["chapters"]) / CHAPTERS[b] >= 0.6)]
        if len(ov_books) > 1:
            ov_books.sort(key=order.index)
            spans[ov_books[0]].append({"label": span_label(ov_books), "id": it["id"], "books": ov_books})
        for book, d in e["refs"].items():
            if book in ov_books:
                if len(ov_books) == 1: by_book_ov[book].append(it["id"])
            else:
                for c in d["chapters"]:
                    by_chapter[(book, c)].append(it["id"])
    def core(t):  # title without episode numbers, "| Speaker" tails, or (Bible reference) brackets
        t = re.sub(r"^\s*#?[\d,]+\s*[\u2013\u2014-]\s*", "", t or "")
        t = re.sub(r"^\s*Expound:\s*", "", t, flags=re.I)  # Skip's radio labels his Expound series
        t = re.sub(r"^\s*MBC [A-Z][A-Za-z ]+\|\|\s*", "", t)  # McLean campus postings ("MBC Loudoun || ...") of the main sermon
        segs = [x.strip() for x in t.split("|")]
        if len(segs) > 1:  # "SERIES | Name | Passage | Speaker": keep series + name, drop passage and speaker
            segs = [x for x in segs[:-1] if x and not parse_refs(x)] or segs[:1]
        t = " ".join(segs)
        t = re.sub(r"\(([^)]*)\)", lambda m: "" if parse_refs(m.group(1)) else " " + m.group(1), t)
        t = re.sub(r"[^a-z0-9]+", " ", t.lower().replace("\u2019", "'")).strip()
        return re.sub(r"\bpart (\w+)\b", r"part \1", t)
    SRC_PREF = {"platt_messages": 0, "ptw": 0, "2819_podcast": 0, "secret_church_podcast": 0, "twr360_secret_church": 1,
                "mclean_podcast": 2, "radical_message": 3, "victory_podcast": 3, "radical_vimeo": 1, "street_preachers": 2,
                "davey_sermons": 0, "davey_wfth": 1, "davey_journey": 0, "skip_archive": 0, "skip_church": 1, "skip_connect": 2}
    def one_each(lst):  # one teaching, one entry: keep the best form of same-titled items
        best = {}
        for i in lst:
            key = (core(items[i]["t"]), items[i]["who"])
            score = (not items[i]["audio"], SRC_PREF.get(items[i]["src"], 5), i)
            if key not in best or score < best[key][0]: best[key] = (score, i)
        keep = {v[1] for v in best.values()}
        lst[:] = [i for i in lst if i in keep]
        # radio broadcasts split a sermon into parts (Davey "Part 1", Skip "Part A"): drop the parts when the whole sermon is here
        RADIO, PART = ("davey_wfth", "skip_connect"), r"\bpart (?:\d+|[a-c])$"
        whole = {(core(items[i]["t"]), items[i]["who"]) for i in lst if items[i]["audio"] and items[i]["src"] not in RADIO}
        lst[:] = [i for i in lst if not (items[i]["src"] in RADIO and re.search(PART, core(items[i]["t"]))
                                         and (re.sub(r"\s*" + PART, "", core(items[i]["t"])).strip(), items[i]["who"]) in whole)]
        # the same sermon posted by two feeds under slightly different titles, days apart
        from difflib import SequenceMatcher
        drop = set()
        for a in lst:
            for b in lst:
                A, B = items[a], items[b]
                if a >= b or a in drop or b in drop or A["src"] == B["src"] or A["who"] != B["who"] or A["tr"] != B["tr"]:
                    continue
                try: gap = abs((_dd.fromisoformat(A["date"]) - _dd.fromisoformat(B["date"])).days)
                except ValueError: continue
                first = lambda t: core(re.split(r"\s*\|", t)[0])
                sim = max(SequenceMatcher(None, core(A["t"]), core(B["t"])).ratio(),
                          SequenceMatcher(None, first(A["t"]), first(B["t"])).ratio())
                if gap <= 10 and sim >= 0.75:
                    sa = (not A["audio"], SRC_PREF.get(A["src"], 5)); sb = (not B["audio"], SRC_PREF.get(B["src"], 5))
                    drop.add(b if sa <= sb else a)
        lst[:] = [i for i in lst if i not in drop]
    for lst in by_chapter.values(): one_each(lst)
    # Skip taught through the Bible several times (1980s, 90s, 2000s, today): where an older walk-through message of his
    # covers much the same chapters as a newer one, keep only the newer (decided once per message, for the whole book)
    on_road = {i for lst in by_chapter.values() for i in lst}
    drop = set()
    for book in {b for i in on_road for b in CH.get(i, {})}:
        walks = sorted([i for i in on_road if items[i]["who"] == "Skip" and not items[i].get("by") and WALK.get(i) and CH[i].get(book)],
                       key=lambda i: items[i]["date"] or "", reverse=True)
        kept = []
        for i in walks:
            a = VS[i].get(book) or set()
            # redundant: a newer kept walk-through covers most of this one's verses and is not much wider
            if a and any(len(a & VS[j][book]) >= 0.6 * len(a) and len(VS[j][book]) <= 4 * len(a) for j in kept): drop.add(i)
            elif not re.search(r"\breview\b", items[i]["t"], re.I): kept.append(i)   # a recap stays but never replaces the study itself
    for lst in by_chapter.values():
        lst[:] = [i for i in lst if i not in drop]
    for lst in by_book_ov.values(): one_each(lst)
    for book, sp in spans.items():  # multi-book overviews
        ids = [x["id"] for x in sp]; one_each(ids); sp[:] = [x for x in sp if x["id"] in set(ids)]
    for k, lst in by_chapter.items():  # 2819 first; Victory-era only where 2819 has nothing
        if any(items[i]["who"] == "PAM" and items[i]["era"] == "2819" and items[i]["tr"] == "sermon" for i in lst):
            lst[:] = [i for i in lst if not (items[i]["who"] == "PAM" and items[i]["era"] != "2819")]
    # Ranking inside a chapter: teaching from a run through this book first (a series), then teaching
    # whose own title names the passage, then the rest; newest first within each.
    from datetime import date as _d
    def _day(i):
        try: return _d.fromisoformat(items[i]["date"]).toordinal()
        except ValueError: return None
    by_book_sermons = defaultdict(list)
    for i, it in items.items():
        if it["tr"] == "sermon" and _day(i):
            for b in item_books[i]: by_book_sermons[(b, it["who"])].append(_day(i))
    def focus(i, book):
        it, d = items[i], _day(i)
        if it["tr"] == "sermon" and d and sum(1 for x in by_book_sermons[(book, it["who"])] if abs(x - d) <= 90) >= 3:
            return 2
        return 1 if title_states[i] else 0
    TOPICAL, NEVER = re.compile(config.TOPICAL_TITLE_RE, re.I), re.compile(config.NEVER_ON_ROAD_RE, re.I)
    WHY = {}
    def on_road(i, book):
        it = items[i]
        if NEVER.search(it["t"]): WHY[i] = "never: " + NEVER.search(it["t"]).group(0); return False
        if it["tr"] != "sermon": return True
        parallel = set(item_books[i]) <= {"1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles"} or set(item_books[i]) <= {"Matthew", "Mark", "Luke", "John"}
        if ref_how[i] == "description-first" and cited[i] > 1 and focus(i, book) < 2 and not parallel: WHY[i] = "several passages"; return False  # several passages, none named the text, not in a series
        if TOPICAL.search(it["t"]) and focus(i, book) < 2 and it["src"] != "secret_church_podcast": WHY[i] = "topical: " + TOPICAL.search(it["t"]).group(0); return False  # one-off topical message (Secret Church sessions are placed on purpose)
        return True
    off_road = set()
    for (book, c), lst in by_chapter.items():
        keep = [i for i in lst if on_road(i, book)]
        off_road |= set(lst) - set(keep); lst[:] = keep
    # a series (same teacher, same book, sermons no more than 90 days apart (a summer break stays inside a series)) plays in preaching order;
    # the most recent series comes first
    run_end = {}
    for (book, who), days in by_book_sermons.items():
        ds = sorted(set(days)); start = 0
        for k in range(1, len(ds) + 1):
            if k == len(ds) or ds[k] - ds[k - 1] > 90:
                for x in ds[start:k]: run_end[(book, who, x)] = ds[k - 1]
                start = k
    def rank(book):
        def key(i):
            it, d, f = items[i], _day(i) or 0, focus(i, book)
            series = (-run_end.get((book, it["who"], d), d), d) if f == 2 else ((0, d) if it["src"] == "davey_journey" else (0, -d))  # the Journey walks forward day by day
            return (it["tr"] != "sermon", not it["audio"], -f, it["who"] != "Platt", series, i)
        return key
    books = []
    for name, abbr, n, t, _a in BOOKS:
        chs = []
        for c in range(1, n + 1):
            ids = sorted(set(by_chapter.get((name, c), [])), key=rank(name))
            # keep each series together, in preaching order (date, then where its passage starts)
            def run_of(i):  # (teacher, series, playable): a series groups only with its own kind
                d = _day(i)
                return (items[i]["who"], run_end.get((name, items[i]["who"], d)), bool(items[i]["audio"])) if items[i]["tr"] == "sermon" and d else None
            out, done_runs = [], set()
            for i in ids:
                r = run_of(i)
                if r is None or r[1] is None: out.append(i); continue
                if r in done_runs: continue
                done_runs.add(r)
                out += sorted([j for j in ids if run_of(j) == r],
                              key=lambda j: (_day(j), first_verse[j].get(name, (0, 0)), j))
            out += [j for j in ids if j not in out]
            ids = out
            sm = SUMMARIES.get(name, {}).get("chapters", {}).get(str(c), {})
            lk = (lambda t, _b=name, _c=c: ATLAS.link_chapter(t, _b, _c)) if ATLAS.ok else (lambda t: t)
            chs.append({"c": c, "seq": narr[(name, c)], "ids": ids, **({"y": years.chapter_label(name, c)} if SHOW_YEARS else {}),
                        **({"sl": lk(sm["line"]), "sm": [lk(x) for x in sm.get("more", [])]} if sm.get("line") else {})})
        ov = sorted(set(by_book_ov.get(name, [])), key=lambda i: (items[i]["sc"] or [99, 99], items[i]["date"], i))
        # drop a Secret Church event page when its podcast episodes or video sessions are present
        if any(items[i]["src"] in ("secret_church_podcast", "youtube_radical", "twr360_secret_church") for i in ov):
            ov = [i for i in ov if items[i]["src"] != "secret_church"]
        sp = sorted(spans.get(name, []), key=lambda x: (x["label"], items[x["id"]]["sc"] or [99, 99]))
        if any(items[x["id"]]["src"] in ("secret_church_podcast", "youtube_radical", "twr360_secret_church") for x in sp):
            sp = [x for x in sp if items[x["id"]]["src"] != "secret_church"]
        books.append({"name": name, "abbr": abbr, "n": n, "t": t, "ov": ov, "spans": sp, "ch": chs, **({"yr": years.BOOKS[name]} if SHOW_YEARS else {}),
                      **({"bl": blk(SUMMARIES[name]["line"], name), "bm": [blk(x, name) for x in SUMMARIES[name].get("more", [])]} if SUMMARIES.get(name, {}).get("line") else {})})
    sc_events = [{"n": n, "title": title, "url": url, "scope": scope} for n, title, url, scope in config.SECRET_CHURCH_EVENTS]
    sc_items = sorted([i for i in items.values() if i["sc"]], key=lambda i: (i["sc"][0], i["sc"][1]))
    ptw = sorted([i for i in items.values() if i["tr"] == "devotional"], key=lambda i: i["date"])
    narr = {}  # chapters read aloud by Alistair: {abbr: {"t": release tag, "c": [chapters], "d": [seconds]}}; timings go to narration/
    ndir = os.path.join(HERE, "data", "narration")
    if os.path.isdir(ndir):
        os.makedirs(os.path.join(SITE, "narration"), exist_ok=True)
        for f in sorted(os.listdir(ndir)):
            if not f.endswith(".json"): continue
            nb = json.load(open(os.path.join(ndir, f)))
            cs = sorted(int(c) for c in nb["c"])
            narr[f[:-5]] = {"t": nb["tag"], "c": cs, "d": [round(nb["c"][str(c)]["d"]) for c in cs]}
            shutil.copy(os.path.join(ndir, f), os.path.join(SITE, "narration", f))
    data = {"built": __import__("datetime").date.today().isoformat(), "items": items, "books": books, "narr": narr,
            "sc": {"events": sc_events, "ids": [i["id"] for i in sc_items]}, "ptw": [i["id"] for i in ptw], "bp": big_picture(items),
            "topics": topics.build(items, CH, {i for lst in by_chapter.values() for i in lst} | {i for lst in by_book_ov.values() for i in lst})}
    html = TEMPLATE.replace("__VERSION__", str(VERSION)).replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    n_audio = sum(1 for i in items.values() if i["audio"])
    print(f"wrote {OUT}: {len(items)} items, {n_audio} with in-app audio; off the road: {len(off_road)}")
    json.dump(sorted(f'{items[i]["t"]}  [{WHY.get(i, "")}]' for i in off_road), open(os.path.join(HERE, "out", "off_road.json"), "w"), indent=0, ensure_ascii=False)
    write_site(html)

def blk(t, book):
    return ATLAS.link_book(t, book) if ATLAS.ok else t

def write_site(html: str):
    """out/site/: index.html + manifest + icons + service worker — the installable home-screen app."""
    import shutil
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(SITE, "version.txt"), "w").write(str(VERSION))
    if ATLAS.ok:  # people, places and the map: loaded on the first tap of a name or the map button
        json.dump(ATLAS.data(), open(os.path.join(SITE, "atlas.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    # narrator samples page (voices.html): the current round only; men only
    rows, sections = "", [("voice_samples3", "Real voices, clean recordings", "The prodigal son (Luke 15), read in the voices of real British men who shared recordings of their voices for voice research and cloning. Each comes in two readers; the short clip under it is the man himself.")]
    os.makedirs(os.path.join(SITE, "voices"), exist_ok=True)
    for d, head, sub in sections:
        vdir = os.path.join(HERE, "data", d)
        if not os.path.isdir(vdir): continue
        meta = json.load(open(os.path.join(vdir, "voices.json"))) if os.path.exists(os.path.join(vdir, "voices.json")) else []
        meta = [m for m in meta if m.get("voice") == "male"]
        if not meta: continue
        for f in os.listdir(vdir):
            if f.endswith(".mp3") and any(f in (m["file"], m.get("ref")) for m in meta): shutil.copy(os.path.join(vdir, f), os.path.join(SITE, "voices", f))
        rows += f'<h2>{head}</h2><p>{sub}</p>'
        for m in meta:
            rows += (f'<div class="v"><div class="n">{m["name"]}<span>{m.get("about", "British")}</span></div>'
                     f'<audio controls preload="none" src="voices/{m["file"]}"></audio>'
                     + (f'<div class="sub">His own voice (the recording it learned from):</div><audio controls preload="none" src="voices/{m["ref"]}"></audio>'
                        if m.get("ref") and (m["id"].startswith("turbo_") or not any(x["id"] == "turbo_" + m["id"].split("_")[-1] for x in meta)) else "")
                     + '</div>')
    if rows:
        open(os.path.join(SITE, "voices.html"), "w", encoding="utf-8").write(VOICES_PAGE.replace("__ROWS__", rows))
    bdir = os.path.join(HERE, "data", "bible")
    if os.path.isdir(bdir):  # Berean Standard Bible, one file per book, loaded when a chapter is opened
        os.makedirs(os.path.join(SITE, "bible"), exist_ok=True)
        for f in os.listdir(bdir):
            shutil.copy(os.path.join(bdir, f), os.path.join(SITE, "bible", f))
    for f in os.listdir(PWA):
        if f == "sw.js":
            src = open(os.path.join(PWA, f), encoding="utf-8").read().replace("__VERSION__", str(VERSION))
            open(os.path.join(SITE, f), "w", encoding="utf-8").write(src)
        elif not f.startswith("."):
            shutil.copy(os.path.join(PWA, f), os.path.join(SITE, f))
    print(f"wrote {SITE}/ (deploy this folder)")

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#f4efe3"><title>Scripture Companion</title>
<link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="icon-180.png"><link rel="icon" href="icon.svg" type="image/svg+xml">
<meta name="apple-mobile-web-app-title" content="Companion"><meta name="mobile-web-app-capable" content="yes">
<style>
:root{color-scheme:light;--bg:#f4efe3;--ink:#1b2440;--mute:#6b7390;--line:rgba(27,36,64,.12);--gold:#c9a24a;--gold2:#a8812a;--card:rgba(255,255,255,.78)}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",Inter,system-ui,sans-serif;overflow-x:hidden}
.serif{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
/* world */
.world{position:relative;background:linear-gradient(180deg,#eef3fb 0%,#f4efe3 18%,#efe6d9 40%,#e9e4ef 58%,#f3e6d6 76%,#fbf0d4 90%,#fff7dc 100%)}
.world > svg{display:block;width:100%}.world svg svg{overflow:visible}
.land{font:600 10px -apple-system,system-ui,sans-serif;fill:rgba(168,129,42,.95);letter-spacing:.18em;text-transform:uppercase}
.bl{font:15px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;fill:rgba(27,36,64,.55)}.bl.big{font-size:19px;fill:rgba(27,36,64,.9)}.bl.here{fill:var(--gold2)}
.you{filter:drop-shadow(0 0 12px rgba(201,162,74,.9))}
.glow{filter:blur(28px);opacity:.55}
/* clearing: the chapter where you stand, placed in the world */
.clearing{position:relative;margin:0 auto;width:min(340px,92vw);z-index:3;padding:14px 14px 16px;border-radius:22px;background:linear-gradient(180deg,rgba(255,255,255,.55),rgba(255,255,255,.92) 18%,rgba(255,255,255,.92) 85%,rgba(255,255,255,.55));backdrop-filter:blur(8px);box-shadow:0 10px 40px rgba(27,36,64,.10)}
.clearing .where{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--gold)}
.scene{font:italic 15px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--gold2);margin:-4px 0 10px;display:flex;align-items:center;gap:8px}
.clearing .ch{font-size:30px;line-height:1.05;margin:2px 0 8px}
.voice{display:flex;align-items:center;gap:10px;padding:8px 10px;margin:5px 0;background:var(--card);border:1px solid rgba(27,36,64,.08);border-radius:16px}
.voice .pb{width:42px;height:42px;border-radius:50%;flex:none;border:0;background:conic-gradient(var(--gold) var(--p,0deg),rgba(27,36,64,.10) 0);display:flex;align-items:center;justify-content:center;color:var(--ink);font-size:18px;cursor:pointer}
.voice .pb::before{content:"";position:absolute;width:35px;height:35px;border-radius:50%;background:#fff}
.voice .pb span{position:relative}
.voice .pb.playing span{color:var(--gold2)}.voice .pb.off{opacity:.35}
.voice .tx{flex:1;min-width:0}.voice .who{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute)}
.voice .ti{font-size:14px;line-height:1.25;margin:1px 0}
.voice .vb{display:inline-block;margin:0 8px 0 0;padding:1px 7px;border-radius:8px;background:rgba(201,162,74,.16);color:#7a5c16;font-size:11.5px;font-weight:700;letter-spacing:0;text-transform:none;text-decoration:none}
.lks{display:flex;gap:6px;overflow-x:auto;padding:2px 0 12px;scrollbar-width:none}.lks::-webkit-scrollbar{display:none}
.lk{flex:none;min-height:38px;border-radius:19px;padding:7px 11px;border:1px solid rgba(27,36,64,.16);background:#fff;font:inherit;font-size:13.5px;font-weight:600;color:var(--ink);cursor:pointer;white-space:nowrap}
.lk span{display:inline-block;min-width:20px;margin-left:7px;padding:1px 7px;border-radius:10px;background:rgba(201,162,74,.18);color:#7a5c16;font-size:12px;font-weight:700;line-height:18px;text-align:center}.lk.on span{background:rgba(255,255,255,.2);color:#fff}.lk.on{background:var(--ink);border-color:var(--ink);color:#fff}
.lk-sep{flex:none;align-self:center;font-style:normal;color:#b59a5a;font-size:15px;margin:0 -3px}
.lk-hint{margin:0 0 10px 2px;font-size:13px;line-height:1.4;color:var(--mute)}.voice .ln{font-size:12px;color:var(--mute)}
.voice.done .ti{color:var(--mute)}.voice .ck{flex:none;background:none;border:1px solid rgba(27,36,64,.15);color:var(--mute);width:30px;height:30px;border-radius:50%;font-size:14px}
.voice.done .ck{background:var(--gold);color:#fff;border-color:var(--gold)}.voice .ck{display:flex;align-items:center;justify-content:center;box-sizing:border-box}
.acts{display:flex;gap:6px;margin:12px 0 0}
.acts button{font:inherit;font-size:14px;white-space:nowrap;border-radius:22px;padding:10px 8px;flex:1 1 auto;min-width:0;border:1px solid rgba(27,36,64,.15);background:rgba(255,255,255,.6);color:var(--ink)}
.acts .bk{flex:0 0 44px;padding:10px 0;font-size:18px;line-height:1}
.myplace{display:inline-flex;align-items:center;min-height:36px;vertical-align:middle;background:none;border:0;padding:0 2px;font:inherit;font-size:12px;color:var(--gold2);text-decoration:underline;text-underline-offset:2px;cursor:pointer}.acts .bk:disabled{opacity:.3}
.clearing .hd{display:flex;align-items:center;justify-content:space-between;gap:10px}
.ck-c{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#c9a24a;color:#fff;font:700 14px/1 -apple-system,system-ui,sans-serif;margin-left:9px;vertical-align:4px}
.pg{display:grid;gap:5px;margin:8px 0 6px}
.pg-r{display:grid;grid-template-columns:minmax(52px,auto) minmax(0,1fr) auto;align-items:center;gap:10px;font-size:12.5px;color:var(--mute)}
.pg-l{white-space:nowrap}.pg-b{height:6px;border-radius:3px;background:rgba(27,36,64,.08);overflow:hidden}
.pg-b i{display:block;height:100%;min-width:0;border-radius:3px;background:linear-gradient(90deg,#d9b45a,#c9a24a);transition:width .5s ease}
.pg-p{text-align:right;font-weight:650;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap;min-width:44px}
.pg-h{font-weight:500;color:var(--mute)}.clearing .hd .ch{cursor:pointer}
.clearing .fold{flex:none;width:36px;height:36px;border-radius:50%;border:1px solid rgba(27,36,64,.15);background:rgba(255,255,255,.6);color:var(--ink);display:flex;align-items:center;justify-content:center;padding:0;cursor:pointer}
.clearing .yr{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);margin:-2px 0 8px}.clearing.folded .yr{margin:-2px 0 4px}
.byr{font:600 9px -apple-system,system-ui,sans-serif;letter-spacing:.14em;fill:rgba(168,129,42,.85);text-transform:uppercase}
.clearing .sline{font-size:15px;line-height:1.4;color:var(--ink);margin:0 0 6px}
.clearing .about{border-left:2px solid var(--gold);padding:2px 0 2px 10px;margin:4px 0 10px}.clearing .ab-t{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);margin-bottom:2px}
.sum2{margin:0 0 8px}.sum2 summary{list-style:none;cursor:pointer;font-size:13px;color:var(--gold2)}.sum2 summary::-webkit-details-marker{display:none}
.sum2 ul{margin:6px 0 0;padding-left:18px}.sum2 li{font-size:14px;line-height:1.4;color:var(--ink);margin:3px 0}
#bookhd{position:fixed;left:14px;top:calc(10px + env(safe-area-inset-top));z-index:6;background:rgba(255,255,255,.85);backdrop-filter:blur(8px);border:1px solid rgba(27,36,64,.12);color:var(--ink);border-radius:16px;padding:6px 14px;font:16px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;cursor:pointer}
#bookhd:empty{display:none}
#topbar{position:fixed;left:0;right:0;top:0;height:calc(52px + env(safe-area-inset-top));z-index:5;background:rgba(244,239,227,.97);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line);opacity:0;pointer-events:none;transition:opacity .2s,transform .25s}
body.scrolled #topbar{opacity:1}#bookhd,.top{transition:transform .25s}
body.hidehd #topbar,body.hidehd #bookhd,body.hidehd .top{transform:translateY(calc(-100% - 20px - env(safe-area-inset-top)))}
.readx{margin:0 0 10px}.readx summary{list-style:none;cursor:pointer;font-size:13px;color:var(--gold2)}.readx summary::-webkit-details-marker{display:none}
.txt{font:17px/1.65 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink);margin-top:8px}
.txt .endacts{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px;font:15px -apple-system,system-ui,sans-serif}
.txt .endacts button{border-radius:20px;padding:10px 14px;border:1px solid rgba(27,36,64,.15);background:#fff;color:var(--ink);font:inherit;cursor:pointer}
.txt .endacts .walk{background:var(--gold);border-color:var(--gold);font-weight:600;color:#1b2440}
.txt h4{font:600 11px -apple-system,system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);margin:14px 0 4px}
.txt p{margin:0 0 10px}.txt p.poem{padding-left:1.2em;text-indent:-1.2em}.txt p.q2{padding-left:2.2em}
.txt .ptitle{font-style:italic;color:var(--mute);margin:4px 0 8px;font-size:15px}
.txt sup{font:600 10px -apple-system,system-ui,sans-serif;color:var(--gold2);margin-right:3px;vertical-align:super}
.txt .hl{background:rgba(201,162,74,.22);border-radius:3px;box-shadow:0 0 0 2px rgba(201,162,74,.22)}
.txt.narr .vs{cursor:pointer;-webkit-tap-highlight-color:transparent}.txt .vs.now{background:rgba(201,162,74,.32);border-radius:3px;box-shadow:0 0 0 3px rgba(201,162,74,.32);transition:background .25s}
.narbar{display:flex;align-items:center;gap:12px;margin:4px 0 12px;padding:10px 12px;border-radius:14px;background:rgba(27,36,64,.05);font:14px -apple-system,system-ui,sans-serif;color:var(--mute)}
.narbar button{display:flex;align-items:center;gap:8px;border:0;border-radius:20px;padding:9px 16px 9px 12px;background:var(--ink);color:#fff;font:600 15px -apple-system,system-ui,sans-serif;cursor:pointer;flex:none}
.narbar span{line-height:1.3}.narbar span b{color:var(--ink);font-weight:600;white-space:nowrap}
.txt .src{font:11px -apple-system,system-ui,sans-serif;color:var(--mute);margin-top:6px}
.pref{background:none;border:0;padding:0;font:inherit;color:var(--gold2);text-decoration:underline;text-underline-offset:2px;cursor:pointer}
.nm{background:none;border:0;padding:0;font:inherit;color:inherit;font-weight:650;text-decoration:underline;text-decoration-color:rgba(168,129,42,.7);text-decoration-thickness:1.5px;text-underline-offset:3px;cursor:pointer}
.nm.l{text-decoration-style:dotted}
.top{display:flex;gap:8px;align-items:center}.top #mapbtn{display:flex;align-items:center;justify-content:center;padding:6px 10px}
span.nw{white-space:nowrap}
.chv{margin-left:6px;vertical-align:5px;opacity:.55}
#srch{display:flex;align-items:center;gap:6px;padding:7px 12px 7px 10px;min-height:36px}#srch span{font-size:13.5px;color:var(--mute)}
@media (max-width:389px){#srch span{display:none}#srch{padding:7px 10px}}
#bookhd{max-width:calc(100vw - 215px);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#jump{position:fixed;inset:0;z-index:25;background:#f7f2e7;display:flex;flex-direction:column}
#jump[hidden]{display:none}
#jump .jp-top{display:flex;gap:10px;align-items:center;padding:calc(10px + env(safe-area-inset-top)) 14px 10px;background:#f7f2e7;border-bottom:1px solid rgba(27,36,64,.08)}
#jump .jp-field{flex:1;display:flex;align-items:center;gap:8px;background:#fff;border:1px solid rgba(27,36,64,.14);border-radius:14px;padding:0 12px;min-height:44px;color:var(--mute)}
#jump input{flex:1;border:0;outline:0;background:transparent;font:inherit;font-size:17px;color:var(--ink);min-width:0;-webkit-appearance:none}
#jump #jx{border:0;background:none;font:inherit;font-size:15px;color:var(--gold2);font-weight:600;padding:8px 2px;min-height:44px}
#jbody{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:6px 14px calc(30px + env(safe-area-inset-bottom))}
.jp-h{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);font-weight:650;margin:16px 2px 8px}
.jp-sec{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin:14px 2px 6px}
.jp-bk{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin:14px 2px 12px}.jp-bn{font-size:28px;color:var(--ink)}.jp-bs{font-size:13px;color:var(--mute)}
.jp-all{flex:none;border:1px solid rgba(168,129,42,.4);border-radius:18px;background:#fff;font:inherit;font-size:14px;font-weight:600;color:var(--gold2);padding:8px 14px;min-height:40px;cursor:pointer}
.jg{display:grid;grid-template-columns:repeat(auto-fill,minmax(52px,1fr));gap:8px}.jg.small{margin:10px 0 2px}
.jc{min-height:48px;border-radius:12px;border:1px solid rgba(27,36,64,.12);background:#fff;font:inherit;font-size:16px;font-weight:600;color:var(--ink);cursor:pointer}
@keyframes slideL{from{transform:translateX(44px);opacity:.35}to{transform:none;opacity:1}}@keyframes slideR{from{transform:translateX(-44px);opacity:.35}to{transform:none;opacity:1}}#clearing.in-l{animation:slideL .28s ease-out}#clearing.in-r{animation:slideR .28s ease-out}
.sccard{display:flex;flex-direction:column;align-items:flex-start;gap:4px;width:100%;margin:0 0 18px;padding:16px 18px;border:0;border-radius:18px;background:linear-gradient(140deg,#2a2f3f,#1b2440);color:#fff;text-align:left;cursor:pointer;box-shadow:0 8px 24px rgba(27,36,64,.18)}.sccard .serif{font-size:24px}.sccard small{font-size:13px;opacity:.8;font-weight:600}
.sce{border:1px solid rgba(27,36,64,.1);border-radius:16px;background:#fff;margin:10px 0;overflow:hidden}.sce summary{display:flex;align-items:center;gap:12px;padding:14px 16px;cursor:pointer;list-style:none}.sce summary::-webkit-details-marker{display:none}
.sce-n{flex:none;width:34px;height:34px;border-radius:17px;background:rgba(201,162,74,.18);color:#7a5c16;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:14px}.sce-t{flex:1;font-family:'Iowan Old Style',Palatino,Georgia,serif;font-size:18px;color:var(--ink)}.sce-p{flex:none;font-size:13px;color:var(--mute);font-weight:600}.sce-b{padding:0 10px 10px}
.jc-bk{grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;padding:10px;font-family:'Iowan Old Style',Palatino,Georgia,serif;font-size:19px;font-weight:400}.jc-bk small{font-family:-apple-system,system-ui,sans-serif;font-size:12px;font-weight:600;color:var(--mute);letter-spacing:.04em}
.jc.done{background:#c9a24a;border-color:#c9a24a;color:#fff}.jc.here{box-shadow:0 0 0 2.5px #1b2440;}
.jb{display:flex;justify-content:space-between;align-items:center;width:100%;min-height:46px;border:0;border-bottom:1px solid rgba(27,36,64,.07);background:none;font:inherit;font-size:16px;color:var(--ink);padding:0 4px;cursor:pointer;text-align:left}
.jb.cur{font-weight:700}.jb-r{font-size:13px;color:var(--mute)}.jb-r .ok{font-style:normal;color:#fff;background:#c9a24a;border-radius:50%;width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;font-size:12px}
.jr{display:flex;align-items:center;gap:12px;width:100%;min-height:56px;padding:9px 10px;margin:0 0 6px;border:1px solid rgba(27,36,64,.09);border-radius:14px;background:#fff;font:inherit;color:var(--ink);text-align:left;cursor:pointer}
.jr.top{border-color:rgba(201,162,74,.6);background:#fbf3df}
.jr-ic{flex:none;width:34px;height:34px;border-radius:50%;background:#f3ead3;color:#8a6a1e;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}.jr-ic.pin{color:#a8812a;font-size:15px}.jr-ic.play{font-size:11px}
.jr-t{min-width:0;display:flex;flex-direction:column;gap:2px}.jr-t b{font-size:15.5px;font-weight:650}.jr-t small{font-size:13px;color:var(--mute);line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.jp-empty{margin:24px 6px;font-size:15px;line-height:1.5;color:var(--mute)}
body.jumpopen{overflow:hidden}

.medal{flex:none;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:#fbf5e6;border:2px solid var(--ring);box-shadow:inset 0 0 0 3px #fbf5e6,inset 0 0 0 4px rgba(201,162,74,.5);box-sizing:border-box;vertical-align:middle}
#sheet .ph{display:flex;align-items:center;gap:14px;margin:2px 0 6px}#sheet .ph-t{min-width:0}#sheet .ph h3{margin:0}
#sheet .ph-r{font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;color:#6b7186;font-weight:600;margin-top:5px}
#sheet .chip .medal{border-width:1.5px;box-shadow:inset 0 0 0 2px #fbf5e6;margin:-3px 6px -3px -4px}
.unfold{display:block;width:100%;margin:10px 0 2px;padding:12px 14px;border-radius:14px;border:1px solid rgba(201,162,74,.45);background:#fbf3df;color:var(--ink);font:inherit;font-size:15px;font-weight:600;text-align:left;cursor:pointer}
#sheetbg{position:fixed;inset:0;background:rgba(27,36,64,.28);z-index:20;touch-action:none}
#sheet{position:fixed;left:0;right:0;bottom:0;z-index:21;max-height:84vh;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;background:#fbf8f1;border-radius:22px 22px 0 0;box-shadow:0 -12px 40px rgba(27,36,64,.18);padding:8px max(18px,env(safe-area-inset-right)) calc(24px + env(safe-area-inset-bottom)) max(18px,env(safe-area-inset-left));transition:transform .25s cubic-bezier(.2,.8,.2,1)}
#sheet .sh-grab{width:40px;height:4px;border-radius:2px;background:rgba(27,36,64,.2);margin:4px auto 6px}
#sheet .sh-top{display:flex;align-items:center;gap:8px;position:sticky;top:-8px;background:#fbf8f1;padding:6px 0;z-index:2}
#sheet .sh-top button{border:1px solid rgba(27,36,64,.15);background:#fff;border-radius:50%;width:36px;height:36px;font-size:18px;color:var(--ink);cursor:pointer}
#sheet .sh-kind{flex:1;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold2)}
#sheet h3{font:400 30px/1.1 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;margin:2px 0 6px;color:var(--ink)}
#sheet .who{font-size:16px;line-height:1.45;margin:0 0 12px;color:var(--ink)}
#sheet .sec{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold2);margin:14px 0 6px}
#sheet ul{margin:0;padding-left:18px}#sheet li{margin:5px 0;line-height:1.4;font-size:15px}
#sheet .fam{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:15px;align-items:baseline}
#sheet .fam .k{color:var(--mute);font-size:13px}
#sheet .chip{display:inline-flex;align-items:center;min-height:36px;margin:0 6px 6px 0;padding:6px 12px;border-radius:14px;border:1px solid rgba(27,36,64,.14);background:#fff;font:inherit;font-size:14px;color:var(--ink)}
#sheet button.chip{cursor:pointer;border-color:rgba(168,129,42,.5);color:var(--gold2)}
#sheet .go{background:none;border:0;padding:0;font:inherit;color:var(--gold2);text-decoration:underline;text-underline-offset:2px;cursor:pointer}
#sheet .mean{font:italic 18px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--gold2);margin:-2px 0 4px}
#sheet .why{font-size:13px;color:var(--mute);margin:0 0 10px;line-height:1.4}
#sheet ul.story{list-style:none;padding-left:0;margin:0;border-left:2px solid rgba(201,162,74,.35);margin-left:6px}
#sheet ul.story li{position:relative;padding-left:16px;margin:8px 0}
#sheet ul.story li::before{content:"";position:absolute;left:-6px;top:.45em;width:10px;height:10px;border-radius:50%;background:#fbf8f1;border:2px solid rgba(201,162,74,.8)}
#sheet ul.story li.past{color:var(--mute)}#sheet ul.story li.past::before{background:rgba(201,162,74,.8)}
#sheet ul.story li.now{font-weight:600}#sheet ul.story li.now::before{background:var(--gold);box-shadow:0 0 0 4px rgba(201,162,74,.25)}
#sheet ul.story li.here{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2);font-weight:600}
#sheet ul.story li.here::before{left:-8px;width:14px;height:14px;background:var(--gold);border-color:#fff;box-shadow:0 0 0 3px rgba(201,162,74,.35)}
#sheet .meta{font-size:13px;color:var(--mute);margin-top:12px}
#sheet .mini{position:relative;overflow:hidden;display:block;width:100%;border-radius:14px;border:1px solid rgba(27,36,64,.1);margin:4px 0 10px;background:#d6e4e3;cursor:pointer}
#sheet .mini .mm{display:block;width:100%;height:auto}
#sheet .mini .inset{position:absolute;right:8px;bottom:8px;width:96px;height:58px;border-radius:8px;border:1px solid rgba(27,36,64,.18);box-shadow:0 2px 8px rgba(27,36,64,.15);background:#d6e4e3}
#sheet .within{font-size:14px;color:#5a6178;margin:2px 0 8px;line-height:1.4}
#sheet .within span{color:#b59a5a}
#sheet .open{display:inline-block;margin-top:2px;font-size:14px}
#mapv{position:fixed;inset:0;z-index:22;background:#d6e4e3;overscroll-behavior:contain}
#mapv::after{content:"";position:absolute;inset:0;z-index:1;pointer-events:none;background:radial-gradient(ellipse 85% 70% at 50% 42%,rgba(255,250,235,0) 60%,rgba(110,90,50,.18) 100%)}
#mapsvg{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:grab;-webkit-user-select:none;user-select:none}
#mapsvg [data-pl]{cursor:pointer}
#mapsvg .draw{stroke-dasharray:1;stroke-dashoffset:1;animation:mvdraw 1.7s cubic-bezier(.45,0,.2,1) .1s forwards}
@keyframes mvdraw{to{stroke-dashoffset:0}}
#mapsvg .fade{opacity:0;animation:mvfade .7s ease 1.3s forwards}
@keyframes mvfade{to{opacity:1}}
#mapsvg .pulse{transform-box:fill-box;transform-origin:center;animation:mvpulse 2.6s ease-in-out infinite}
@keyframes mvpulse{0%,100%{transform:scale(.7);opacity:.95}50%{transform:scale(1.25);opacity:.35}}
@media (prefers-reduced-motion:reduce){#mapsvg .draw{animation:none;stroke-dasharray:none;stroke-dashoffset:0}#mapsvg .fade{animation:none;opacity:1}#mapsvg .pulse{animation:none}}
#mapv .mv-top{position:absolute;left:0;right:0;top:0;z-index:2;display:flex;align-items:center;gap:12px;padding:calc(10px + env(safe-area-inset-top)) max(14px,env(safe-area-inset-right)) 18px max(14px,env(safe-area-inset-left));background:linear-gradient(rgba(251,248,241,.94),rgba(251,248,241,0));pointer-events:none}
#mapv .mv-top>*{pointer-events:auto}
#mapv .mv-title{font:21px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink)}
#mapv #mvx{flex:none;width:40px;height:40px;border-radius:50%;border:1px solid rgba(27,36,64,.15);background:rgba(255,255,255,.94);font:inherit;font-size:17px;color:var(--ink);cursor:pointer}
#mapv .mv-panel{position:absolute;left:0;right:0;bottom:0;z-index:2;padding:26px 0 calc(10px + env(safe-area-inset-bottom));background:linear-gradient(rgba(246,241,230,0),rgba(246,241,230,.92) 30px)}
#mapv .mv-card{margin:0 max(12px,env(safe-area-inset-left)) 10px;background:#fbf8f1;border-radius:18px;padding:13px 16px 12px;box-shadow:0 8px 28px rgba(70,52,16,.16);border:1px solid rgba(170,138,70,.2)}
#mapv .mv-k{font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;color:#a8812a;font-weight:650}
#mapv .mv-t{font:24px/1.15 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink);margin:3px 0 4px}
#mapv .mv-s{font-size:14.5px;line-height:1.42;color:#4b5266}
#mapv .mv-here{display:flex;gap:9px;align-items:flex-start;margin-top:9px;padding-top:9px;border-top:1px solid rgba(27,36,64,.08);font-size:14px;line-height:1.42;color:var(--ink)}
#mapv .mv-here i{flex:none;width:10px;height:10px;border-radius:50%;background:#c9a24a;box-shadow:0 0 0 4px rgba(201,162,74,.25);margin-top:5px}
#mapv .mv-here.ink i{background:#fff;border:2px solid #1b2440;box-shadow:none;width:9px;height:9px}
#mapv .mv-ref{color:#7a8094;white-space:nowrap}
#mapv .mv-legs{display:flex;gap:8px;overflow-x:auto;padding:2px max(12px,env(safe-area-inset-left)) 4px;scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch;scrollbar-width:none;overscroll-behavior-x:contain}
#mapv .mv-legs::-webkit-scrollbar{display:none}
#mapv .mv-legs button{flex:none;scroll-snap-align:center;min-height:40px;display:flex;align-items:center;gap:7px;white-space:nowrap;border-radius:20px;padding:8px 14px;border:1px solid rgba(27,36,64,.14);background:rgba(255,255,255,.92);font:inherit;font-size:14px;color:var(--ink);cursor:pointer}
#mapv .mv-legs button span{font-size:11.5px;font-weight:700;color:#a8812a}
#mapv .mv-legs .walked{background:#f5ead0;border-color:rgba(201,162,74,.4)}
#mapv .mv-legs .now{background:#1b2440;border-color:#1b2440;color:#fff}
#mapv .mv-legs .now span{color:#e9c76f}
#mapv .mv-legs .ahead{background:rgba(255,255,255,.62);color:rgba(27,36,64,.6)}
#mapv .mv-legs .sel{box-shadow:0 0 0 2.5px #c9a24a}
body.mapopen #sheetbg{z-index:23}
body.mapopen #sheet{z-index:24}
.clearing .sum{font-size:13px;color:var(--mute);margin:-4px 0 0}.clearing.folded .ch{font-size:24px;margin:2px 0 6px}.clearing.folded .acts{margin-top:10px}
.acts .go{background:var(--gold);color:#1b2440;border-color:var(--gold);font-weight:600}
.acts .read.on{background:rgba(201,162,74,.18);color:var(--gold2);border-color:var(--gold)}
.tabs{display:flex;gap:4px;background:rgba(27,36,64,.06);border-radius:14px;padding:4px;margin:10px 0 12px}
.tab{flex:1;min-height:40px;border:0;border-radius:11px;background:transparent;font:inherit;font-size:15px;font-weight:600;color:var(--mute);cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px}
.tab span{font-size:12px;font-weight:700;color:var(--gold2);background:rgba(201,162,74,.16);border-radius:9px;padding:1px 7px}
.tab.on{background:#fff;color:var(--ink);box-shadow:0 1px 4px rgba(27,36,64,.14)}
.next{margin:12px 0 4px}
.cont{display:flex;align-items:center;gap:12px;width:100%;text-align:left;border:0;border-radius:18px;padding:12px 14px 12px 12px;background:linear-gradient(180deg,#d6b25e,#c9a24a);color:var(--ink);font:inherit;cursor:pointer;box-shadow:0 6px 18px rgba(168,129,42,.28)}
.cont:active{transform:scale(.99)}
.cont-ic{flex:none;width:46px;height:46px;border-radius:50%;background:rgba(255,255,255,.55);display:flex;align-items:center;justify-content:center}
.cont-t{display:flex;flex-direction:column;min-width:0;gap:1px}
.cont-t small{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:rgba(27,36,64,.7);font-weight:650}
/*cb*/.cont-t b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:19px;font-weight:500;line-height:1.2;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.cont-t em{font-style:normal;font-size:13px;color:rgba(27,36,64,.72);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cont.ghost{background:#fff;border:1px solid rgba(27,36,64,.16);box-shadow:none}
.cont.ghost .cont-ic{background:rgba(27,36,64,.06)}
.cont-alt{display:flex;justify-content:flex-end;margin:4px 2px 0}
.cont-alt button{border:0;background:none;font:inherit;font-size:13px;color:var(--mute);padding:6px 4px;cursor:pointer;text-decoration:underline;text-decoration-color:rgba(107,115,144,.35);text-underline-offset:3px}
.cont-end{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;text-align:center;color:var(--gold2);padding:10px}
.tab.step .ok{font-style:normal;font-size:13px;color:var(--gold2);font-weight:700}
.tab.nextstep:not(.on){color:var(--ink)}
.tab.nextstep:not(.on)::after{content:'';width:6px;height:6px;border-radius:50%;background:var(--gold);margin-left:2px}
.tabs .tab.step{padding:0 4px;font-size:14.5px;gap:5px}
.tabs .tab.step span{padding:0;background:none;color:var(--gold2);font-size:12.5px;font-weight:650}
.tabs{gap:2px}
.tab.tmap{flex:0 0 38px;padding:0}
.lk-h{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);margin:14px 0 6px;font-weight:650}
.pane .lk-h:first-child{margin-top:2px}
.voice.upnext{border-color:rgba(201,162,74,.75);box-shadow:inset 3px 0 0 var(--gold)}
.upn{color:var(--gold2);font-weight:700}
.acts .go2{background:rgba(255,255,255,.6)}
.endacts .rdone{flex:1;text-align:center;color:var(--gold2);font-weight:600;padding:10px}
#note{position:fixed;left:50%;top:calc(env(safe-area-inset-top,0px) + 64px);transform:translate(-50%,-12px);max-width:min(340px,90vw);background:var(--ink);color:#fff;border-radius:16px;padding:10px 16px;font-size:14px;line-height:1.35;text-align:center;opacity:0;pointer-events:none;transition:opacity .25s,transform .25s;z-index:60}
#note.on{opacity:1;transform:translate(-50%,0)}
.lnk{border:0;background:none;padding:0;font:inherit;color:var(--gold2);text-decoration:underline;text-underline-offset:3px;cursor:pointer}
.pane.story .st-t{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);margin:2px 0 6px;font-weight:600}
.pane.story ul{margin:0 0 12px;padding-left:18px}.pane.story li{font-size:15px;line-height:1.45;color:var(--ink);margin:4px 0}
.pane .readx>summary{display:none}
.maptab{font-size:15px;color:var(--mute)}
.maptab .mini{position:relative;overflow:hidden;border-radius:16px;border:1px solid rgba(27,36,64,.1);background:#d6e4e3;margin:0 0 12px}
.maptab .mini .mm{display:block;width:100%;height:auto}
.maptab .mini .inset{position:absolute;right:8px;bottom:8px;width:96px;height:58px;border-radius:8px;border:1px solid rgba(27,36,64,.18);box-shadow:0 2px 8px rgba(27,36,64,.15);background:#d6e4e3}
.maptab .mt-k{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold2);font-weight:600}
.maptab .mt-s{margin:4px 0 6px;font-size:15px;line-height:1.45;color:var(--ink)}
.maptab .mt-here{margin:0 0 8px;font-size:14px;line-height:1.4;color:#4b5266}
.maptab .mt-note{margin:0 0 12px;font-size:14px;line-height:1.6;color:#4b5266}
.maptab .mt-open{width:100%;min-height:46px;border:1px solid rgba(27,36,64,.15);border-radius:14px;background:#fff;font:inherit;font-size:15px;font-weight:600;color:var(--ink);text-align:left;padding:10px 14px;cursor:pointer}
.sv-t{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin:10px 0 4px}
.enter{margin:6px 0 8px}.enter summary{list-style:none;cursor:pointer;font-size:13px;color:var(--mute)}.enter summary::-webkit-details-marker{display:none}
.empty{font-size:14px;color:var(--mute);padding:8px 2px}
.more{background:none;border:0;color:var(--gold2);font:inherit;font-size:13px;padding:6px 2px}
/* top */
.top{position:fixed;top:0;right:0;z-index:6;padding:calc(10px + env(safe-area-inset-top)) 14px 10px}
.top .pct{font-size:13px;color:var(--mute)}.top .pct b{color:var(--gold2);font-weight:600}
.top button{background:rgba(255,255,255,.7);border:1px solid rgba(27,36,64,.12);color:var(--ink);border-radius:16px;padding:6px 12px;font:inherit;font-size:13px}
/* now playing */
#np{position:fixed;left:0;right:0;bottom:0;z-index:9;transform:translateY(110%);transition:transform .35s cubic-bezier(.2,.8,.2,1);background:rgba(255,255,255,.86);backdrop-filter:blur(24px);border-top:1px solid rgba(27,36,64,.1);box-shadow:0 -10px 40px rgba(27,36,64,.12);border-radius:24px 24px 0 0;padding:14px 20px calc(16px + env(safe-area-inset-bottom))}
#np.on{transform:none}
#np .grab{width:40px;height:4px;border-radius:2px;background:rgba(27,36,64,.2);margin:0 auto 12px}
#np .t{font-size:20px;line-height:1.2;color:var(--ink)}#np .s{color:var(--mute);font-size:13px;margin-top:3px}
#np input[type=range]{width:100%;accent-color:var(--gold);margin:14px 0 2px}
#np .times{display:flex;justify-content:space-between;color:var(--mute);font-size:11px}
#np .ctl{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
#np .ctl button{background:none;border:0;color:var(--ink);font:inherit;font-size:15px;padding:10px}
#np .ctl .big{width:64px;height:64px;border-radius:50%;background:var(--gold);color:#1b2440;font-size:26px}
#np .grab{position:relative;cursor:grab}#np .grab::after{content:"";position:absolute;left:-80px;right:-80px;top:-14px;bottom:-12px}
#np{touch-action:none}#np input[type=range]{touch-action:auto}
#np:not(.mini){top:0;border-radius:0;display:flex;flex-direction:column;background:#f7f2e7;backdrop-filter:none;padding:calc(6px + env(safe-area-inset-top)) 26px calc(18px + env(safe-area-inset-bottom));overflow-y:auto}
#np:not(.mini) .grab{display:none}
#np .np-top{display:flex;align-items:center;justify-content:space-between;margin:2px -8px 0}
#np .np-top button{background:none;border:0;color:var(--ink);width:44px;height:44px;display:flex;align-items:center;justify-content:center;font-size:18px;cursor:pointer}
#np .np-lab{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--mute);font-weight:600}
#np .art{width:min(76vw,44vh,340px);aspect-ratio:1;margin:18px auto 24px;border-radius:20px;box-shadow:0 18px 40px rgba(27,36,64,.22);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;padding:22px;box-sizing:border-box;color:#fff}
#np .art .a-w{font-size:11px;letter-spacing:.2em;text-transform:uppercase;font-weight:700;opacity:.85}
#np .art .a-p{font-family:'Iowan Old Style',Palatino,Georgia,serif;font-size:clamp(30px,9vw,44px);line-height:1.02;margin-top:6px}
#np .art .a-s{font-size:13px;opacity:.8;margin-top:8px}
#np .art svg.a-m{position:absolute;right:-18px;top:-18px;width:62%;height:62%;opacity:.16}
#np .np-d{color:var(--gold2);font-size:14px;font-weight:600}
#np:not(.mini) .t{font-size:24px;line-height:1.2;margin-top:4px}
#np:not(.mini) .s{font-size:15px;color:var(--gold2);margin-top:4px}
#np:not(.mini) input[type=range]{margin-top:18px}
#np:not(.mini) .ctl{margin-top:10px}
#np:not(.mini) .ctl .big{width:76px;height:76px}
#np .ctl .sk{display:flex;align-items:center;justify-content:center}
#np-read{display:none}#np.reading:not(.mini) #np-read{display:block;flex:1;min-height:0;overflow-y:auto;touch-action:pan-y;-webkit-overflow-scrolling:touch;margin:6px -26px 0;padding:4px 26px 40px;border-bottom:1px solid var(--line)}
#np.reading:not(.mini) .art,#np.reading:not(.mini) .np-d{display:none}#np.reading:not(.mini) .t{font-size:20px;margin-top:0}#np.reading:not(.mini) .s{font-size:13px}
#np-read .rc.first{display:none}#np-read .rprev{display:block;margin:2px auto 10px;border:0;background:none;padding:8px 12px;font:600 13px -apple-system,system-ui,sans-serif;letter-spacing:.03em;color:var(--gold2);cursor:pointer}
#np-read .rc{font:600 12px -apple-system,system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--gold2);margin:22px 0 2px}#np-read .rc:first-child{margin-top:6px}
#np-read .txt{font-size:19px;line-height:1.7}#np-read .rmore{display:block;margin:18px auto;border:1px solid var(--line);background:#fff;border-radius:20px;padding:9px 16px;font:14px -apple-system,system-ui,sans-serif;color:var(--ink)}
.narbar .nx{background:#fff;color:var(--ink);border:1px solid var(--line);padding:9px 12px}
#np .ctl2{display:flex;justify-content:space-between;margin-top:10px}
.spd{display:flex;align-items:center;gap:2px;border:1px solid rgba(27,36,64,.14);border-radius:22px;background:#fff}.spd button{min-width:40px;font-weight:600}#np .ctl2 .spd button{padding:8px 10px}#spd{min-width:58px!important}
#np .ctl2 button{background:none;border:0;color:var(--ink);font:inherit;font-size:15px;padding:10px 4px}
@keyframes npL{from{transform:translateX(50px);opacity:.2}to{transform:none;opacity:1}}@keyframes npR{from{transform:translateX(-50px);opacity:.2}to{transform:none;opacity:1}}
#np.sw-l .art,#np.sw-l .t,#np.sw-l .s{animation:npL .28s ease-out}#np.sw-r .art,#np.sw-r .t,#np.sw-r .s{animation:npR .28s ease-out}
#np.mini .np-top,#np.mini .art,#np.mini .np-d,#np.mini #zz{display:none}
#np.mini .ctl #nxt{display:flex;padding:6px}
#np.mini{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto auto auto auto;column-gap:12px;align-items:center;padding:8px 16px calc(6px + env(safe-area-inset-bottom));cursor:pointer}
#np.mini .grab{grid-column:1/-1;grid-row:1;margin:0 auto 8px}
#np.mini .t{grid-column:1;grid-row:2;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#np.mini .s{grid-column:1;grid-row:3;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#np.mini #cls{display:none}
#np.mini .ctl2{grid-column:2;grid-row:2;margin:0;justify-self:end}#np.mini .ctl2 .spd button{padding:4px 9px;min-width:32px;font-size:14px}#np.mini #spd{min-width:46px!important}
#np.mini .times{justify-self:end}
#np.mini .times{grid-column:2;grid-row:3;gap:8px;font-size:12px;font-variant-numeric:tabular-nums}
#np.mini input[type=range]{grid-column:1/-1;grid-row:4;margin:6px 0 0;height:18px}
#np.mini .ctl .side{font-size:15px;padding:6px 10px}
#np.mini .ctl{grid-column:1/-1;grid-row:5;margin:0;padding:0 4px}#np.mini .ctl .big{width:46px;height:46px;font-size:18px}
#np.mini .ctl{display:flex;justify-content:space-between}#np.mini{background:rgba(255,255,255,.96)}
.settings{padding:calc(70px + env(safe-area-inset-top)) 20px 60px;max-width:560px}
.settings .note{color:var(--mute);font-size:14px;line-height:1.5}textarea{width:100%;height:110px;background:#fff;color:var(--ink);border:1px solid var(--line);border-radius:8px;font:12px/1.4 ui-monospace,monospace}
.btn{background:#fff;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:10px 14px;font:inherit;margin:4px 6px 4px 0}
.bk-steps{padding-left:20px}.bk-steps li{margin:6px 0}.bk-steps a{color:var(--gold2);font-weight:600}
.bkf{display:flex;flex-direction:column;gap:8px;max-width:420px}.bkf input{font:16px -apple-system,system-ui,sans-serif;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--ink)}.bkf .btn{align-self:flex-start}
.bk-u{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
#gear{position:relative}#gear.alert::after{content:'';position:absolute;top:6px;right:6px;width:9px;height:9px;border-radius:50%;background:#d93025;border:2px solid #fff}

/* ---- the four places ---- */
:root{--tabh:calc(58px + env(safe-area-inset-bottom))}
#tabs{position:fixed;left:0;right:0;bottom:0;z-index:8;height:var(--tabh);display:flex;justify-content:space-around;align-items:flex-start;background:rgba(250,246,236,.96);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border-top:1px solid rgba(27,36,64,.08)}
#tabs button{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:7px 0 0;border:0;background:none;color:#5a6280;font:500 11px -apple-system,system-ui,sans-serif;cursor:pointer;min-height:52px}
#tabs button.on{color:var(--gold2);font-weight:650}
#tabs button.on svg{stroke-width:2.1}
body > #bookhd,body:not([data-z="road"]) > div.top,body[data-z="road"] .top #gear,body[data-z="road"] #clearing{display:none!important}
body[data-z="road"] > div.top{top:calc(env(safe-area-inset-top) + 50px);padding-top:8px}
body[data-z="road"].hidehd > div.top{transform:none}
#zt{position:fixed;left:0;right:0;top:0;z-index:7;display:flex;gap:10px;align-items:center;padding:calc(env(safe-area-inset-top) + 8px) 16px 8px 20px;background:rgba(244,239,227,.94);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
#zt[hidden]{display:none}
.zt-seg{flex:1;min-width:0;display:flex;height:40px;padding:3px;border-radius:20px;background:rgba(27,36,64,.07);box-sizing:border-box}
.zt-seg button{flex:1;min-width:0;display:flex;align-items:center;justify-content:center;gap:6px;border:0;border-radius:17px;background:none;color:#4a5272;font:600 14px -apple-system,system-ui,sans-serif;cursor:pointer;padding:0 8px}
.zt-seg button span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.zt-seg button.on{background:#fff;color:var(--ink);box-shadow:0 1px 4px rgba(27,36,64,.14)}
.zt-more{flex:none;width:36px;height:36px;border-radius:50%;border:0;background:rgba(27,36,64,.06);color:#4a5272;display:flex;align-items:center;justify-content:center;cursor:pointer}
.jvz{padding-top:calc(env(safe-area-inset-top) + 70px)!important;touch-action:pan-y}
.jvz .jv-eb{margin-right:0}.jvz .jv-t{margin-right:0}
@keyframes jvl{from{transform:translateX(36px);opacity:.3}to{transform:none;opacity:1}}@keyframes jvr{from{transform:translateX(-36px);opacity:.3}to{transform:none;opacity:1}}
.jv.in-l{animation:jvl .26s ease-out}.jv.in-r{animation:jvr .26s ease-out}
.jv-back{color:#7a5c16!important;font-weight:650!important;background:rgba(154,117,36,.12)!important;border-radius:16px;padding:6px 12px!important}
body[data-z="road"] .world{padding-top:calc(env(safe-area-inset-top) + 40px)}
#here{position:fixed;left:14px;right:14px;bottom:calc(var(--tabh) + var(--npH,0px) + 12px);z-index:7;display:flex;align-items:center;gap:12px;padding:12px 12px 12px 16px;border-radius:22px;background:#fffdf8;box-shadow:0 12px 30px rgba(27,36,64,.16);max-width:520px;margin:0 auto}
.here-t{flex:1;min-width:0;display:flex;flex-direction:column;border:0;background:none;padding:0;text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.here-t small{font:650 10.5px -apple-system,system-ui,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:#7a5c16}
.here-t b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:20px;font-weight:500}
.here-t em{font:normal 12.5px -apple-system,system-ui,sans-serif;color:#5a6280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.here-p{flex:none;width:46px;height:46px;border-radius:50%;border:0;background:#9a7524;display:flex;align-items:center;justify-content:center;cursor:pointer}
.bk-ov{display:flex;align-items:center;justify-content:space-between;width:100%;margin-top:16px;padding:12px 14px;border:0;border-radius:16px;background:#fffdf8;box-shadow:0 2px 10px rgba(27,36,64,.06);cursor:pointer;font:inherit;color:var(--ink)}
.bk-ov span{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:17px}.bk-ov em{font-style:normal;font-size:12.5px;font-weight:700;color:#9a7524}.bk-ov.cur{box-shadow:0 0 0 2px #c9a24a}
.bk-g{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:6px}
.bk-g button{height:40px;border:0;border-radius:12px;background:rgba(27,36,64,.05);font:500 14.5px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer;font-variant-numeric:tabular-nums}
.bk-g button.done{background:rgba(201,162,74,.18);color:#7a5c16}
.bk-g button.cur{background:#9a7524;color:#fff;font-weight:700;box-shadow:0 0 0 3px rgba(201,162,74,.3)}
body.bpsopen{overflow:hidden}
#np.mini{left:10px;right:10px;bottom:calc(var(--tabh) + 8px);border-radius:20px;background:#1b2440;color:#fff;border:0;box-shadow:0 12px 28px rgba(27,36,64,.32);padding:10px 14px 6px;row-gap:0}
#np.mini .grab{display:none}
#np.mini .t{grid-row:1;color:#fff;font-size:15.5px}#np.mini .s{grid-row:2}#np.mini .ctl2{grid-row:1}#np.mini .times{grid-row:2}
#np.mini input[type=range]{grid-row:3;margin:4px 0 0}
#np.mini .ctl{grid-row:4;margin-top:0}#np.mini .ctl .big{width:44px!important;height:44px!important}#np.mini .ctl .side{font-size:14px;padding:4px 8px}#np.mini .ctl svg{width:22px;height:22px}
#np.mini .s,#np.mini .times{color:rgba(255,255,255,.72)}
#np.mini .ctl button,#np.mini .ctl2 > button{color:#fff}
#np.mini .grab{background:rgba(255,255,255,.3)}
#np.mini .spd{background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.2)}#np.mini .spd button{color:#fff}
#np.mini input[type=range]{accent-color:var(--gold)}
/* ---- Journey, Big Picture, Library: one calm column ---- */
.jv{max-width:430px;margin:0 auto;padding:calc(env(safe-area-inset-top) + 18px) 20px 34px;position:relative;font-family:-apple-system,system-ui,sans-serif;color:var(--ink)}
.vmore{position:absolute;top:calc(env(safe-area-inset-top) + 16px);right:16px;width:36px;height:36px;border-radius:50%;border:0;background:rgba(27,36,64,.06);color:#4a5272;display:flex;align-items:center;justify-content:center;cursor:pointer}
.jv-eb{font-size:11px;font-weight:650;letter-spacing:.2em;text-transform:uppercase;color:#7a5c16;margin-right:48px}
.jv-t{margin:2px 48px 14px 0}
.jv-t button,.jv-t{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:40px;font-weight:500;letter-spacing:-.01em;line-height:1.08;color:var(--ink)}
.jv-t button{border:0;background:none;padding:0;display:inline-flex;align-items:center;gap:6px;cursor:pointer;text-align:left}.jv-t button svg{color:#7a5c16;flex:none;margin-top:6px}
.jv-nav{display:flex;justify-content:space-between;gap:10px;margin:10px 2px 0}
.jv-nav button{border:0;background:none;padding:8px 0;font:inherit;font-size:13.5px;color:#4a5272;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:48%}
.jv-art{display:block;position:relative;border-radius:24px;overflow:hidden;box-shadow:0 12px 30px rgba(27,36,64,.12);background:#efe3c5}
.jv-art svg{display:block;width:100%;height:230px}
.jv-art.sm svg{height:150px}
.jv-cap{position:absolute;left:0;right:0;bottom:0;padding:34px 16px 14px;background:linear-gradient(180deg,rgba(246,238,218,0),rgba(246,238,218,.78) 38%,rgba(246,238,218,.92));color:var(--ink)}
.jv-cap i{display:block;font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:21px}
.jv-cap .cs{font-size:13.5px;line-height:1.4;color:#2c3554}
.jv-cap button{font-size:inherit}
.jv-seg{display:flex;gap:8px;margin:16px 0 18px}
.jvz .jv-seg{position:sticky;top:calc(env(safe-area-inset-top) + 56px);z-index:3;background:rgba(244,239,227,.96);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);margin:10px -20px 14px;padding:2px 20px 4px}
.jv-seg button{flex:1;font:11.5px -apple-system,system-ui,sans-serif;color:#5a6280;display:flex;flex-direction:column;gap:6px;border:0;background:none;padding:6px 0 4px;text-align:left;cursor:pointer}
.jv-seg button.now{color:var(--ink);font-weight:650}
@keyframes flash{0%{background:rgba(201,162,74,.28)}100%{background:transparent}}.flash{animation:flash 1.2s ease-out;border-radius:12px}
.jv-none{font-size:13.5px;color:#5a6280;margin:4px 2px}
.jv-seg i{display:block;height:3px;border-radius:2px;background:rgba(27,36,64,.12);overflow:hidden}
.jv-seg b{display:block;height:100%;background:#9a7524;border-radius:2px;transition:width .4s}
.jv-next{display:flex;align-items:center;gap:14px;width:100%;text-align:left;padding:14px;border:0;border-radius:22px;background:#fffdf8;color:var(--ink);box-shadow:0 6px 20px rgba(27,36,64,.08);cursor:pointer;font:inherit}
.jv-next:active{transform:scale(.99)}
.jv-pp{flex:none;width:56px;height:56px;border-radius:50%;background:#9a7524;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px rgba(154,117,36,.35)}
.jv-nt{flex:1;min-width:0;display:flex;flex-direction:column}
.jv-nt small{font-size:10.5px;font-weight:650;letter-spacing:.18em;text-transform:uppercase;color:#7a5c16}
.jv-nt b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:21px;font-weight:500;line-height:1.2;margin-top:1px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.jv-nt em{font-style:normal;font-size:13px;color:#5a6280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jv-alt{display:flex;justify-content:flex-end;gap:16px;margin:6px 4px 0}
.jv-alt button{border:0;background:none;font:inherit;font-size:13px;color:#5a6280;padding:6px 0;cursor:pointer;text-decoration:underline;text-decoration-color:rgba(90,98,128,.35);text-underline-offset:3px}
.jv-done{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:19px;line-height:1.45;color:#2c3554;margin:0 0 14px}
.jv-nextstop{display:block;width:100%;padding:0;border:0;border-radius:26px;overflow:hidden;background:#fffdf8;text-align:left;color:var(--ink);box-shadow:0 14px 34px rgba(27,36,64,.12);cursor:pointer;font:inherit}
.jv-nextstop .jv-art{border-radius:0;box-shadow:none}
.jv-ns{display:flex;flex-direction:column;padding:16px 18px 18px}
.jv-ns small{font-size:10.5px;font-weight:650;letter-spacing:.2em;text-transform:uppercase;color:#7a5c16}
.jv-ns b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:28px;font-weight:500;margin-top:2px}
.jv-ns em{font-style:normal;font-size:14px;color:#4a5272;line-height:1.4;margin-top:4px}
.jv-go{display:flex;align-items:center;justify-content:center;gap:10px;height:52px;border-radius:26px;background:#9a7524;color:#fff;font-size:17px;font-weight:600;margin-top:16px}
.jv-sec{font-size:10.5px;font-weight:650;letter-spacing:.2em;text-transform:uppercase;color:#7a5c16;margin:24px 2px 4px}
.jv-sub{font-size:12px;font-weight:600;color:#4a5272;margin:12px 2px 2px}
.jv-sec:empty{display:none}
.jw{display:flex;align-items:center;gap:12px;padding:10px 2px}
.jr+.jw{border-top:1px solid rgba(27,36,64,.07)}
.jw.up .jw-t b{color:#7a5c16}
.jpb{flex:none;width:36px;height:36px;border-radius:50%;border:0;background:rgba(27,36,64,.06);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer}
.jpb.off{opacity:.35}
.jw-t{flex:1;min-width:0;display:flex;flex-direction:column}
.jw-t b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:16.5px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jw-t span{font-size:12.5px;color:#5a6280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jw.heard .jw-t b{color:#5a6280}
.jw-ok{flex:none;font-style:normal;color:#9a7524;font-weight:700}
.jw .vb{flex:none;font-size:11.5px;font-weight:650;color:#7a5c16;font-variant-numeric:tabular-nums}
.jv-more{display:block;margin:10px auto 0;border:1px solid rgba(27,36,64,.14);background:#fff;border-radius:18px;padding:8px 16px;font:inherit;font-size:13.5px;color:var(--ink);cursor:pointer}
/* ---- Big Picture ---- */
.bpc{flex:none;border-radius:18px;box-shadow:0 8px 18px rgba(27,36,64,.18)}
.bp-cont{display:flex;align-items:center;gap:14px;width:100%;text-align:left;padding:14px;border:0;border-radius:22px;background:#1b2440;color:#fff;box-shadow:0 14px 30px rgba(27,36,64,.22);cursor:pointer;font:inherit;margin-bottom:6px}
.bp-cont .bpc{border-radius:14px;box-shadow:none}
.bp-ct{flex:1;min-width:0;display:flex;flex-direction:column}
.bp-ct small{font-size:10.5px;font-weight:650;letter-spacing:.16em;text-transform:uppercase;color:#e9cf8c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bp-ct b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:19px;font-weight:500;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bp-ct em{font-style:normal;font-size:12.5px;color:rgba(255,255,255,.72)}
.bp-pp{flex:none;width:46px;height:46px;border-radius:50%;background:#c9a24a;display:flex;align-items:center;justify-content:center}
.bp-row{display:flex;gap:14px;align-items:center;width:100%;text-align:left;padding:12px 0;border:0;background:none;color:var(--ink);cursor:pointer;font:inherit}
.bp-row+.bp-row{border-top:1px solid rgba(27,36,64,.08)}
.bp-rt{flex:1;min-width:0;display:flex;flex-direction:column}
.bp-rt b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:19px;font-weight:500;line-height:1.2}
.bp-rt .by{font-size:12.5px;color:#7a5c16;font-weight:650;margin-top:2px}
.bp-rt .ds{font-size:13px;color:#4a5272;line-height:1.35;margin-top:4px}
.bp-rt .pr{display:flex;align-items:center;gap:8px;font-size:12px;color:#5a6280;margin-top:6px}
.bp-rt .pr i{flex:1;height:3px;border-radius:2px;background:rgba(27,36,64,.1);overflow:hidden}.bp-rt .pr i b{display:block;height:3px;background:#9a7524}
#bps{position:fixed;inset:0;z-index:12}
#bps .bps-bg{position:absolute;inset:0;background:rgba(27,36,64,.32);opacity:0;transition:opacity .25s}
#bps .bps-sh{position:absolute;left:0;right:0;bottom:0;top:calc(env(safe-area-inset-top) + 40px);max-width:560px;margin:0 auto;background:#f7f2e7;border-radius:30px 30px 0 0;padding:6px 22px calc(28px + env(safe-area-inset-bottom));overflow-y:auto;-webkit-overflow-scrolling:touch;transform:translateY(100%);transition:transform .3s cubic-bezier(.2,.8,.2,1);font-family:-apple-system,system-ui,sans-serif;color:var(--ink)}
#bps.on .bps-bg{opacity:1}#bps.on .bps-sh{transform:none}
.grab2{display:block;width:60px;height:24px;margin:0 auto;border:0;background:none;position:relative;cursor:pointer}.grab2::after{content:'';position:absolute;left:12px;right:12px;top:9px;height:5px;border-radius:3px;background:rgba(27,36,64,.22)}
.bps-hd{display:flex;gap:16px;align-items:flex-end;margin-top:10px}
.bps-hd .bpc{border-radius:22px;box-shadow:0 14px 28px rgba(27,36,64,.25)}
.bps-t{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:25px;line-height:1.15}
.bps-by{font-size:13.5px;font-weight:650;color:#7a5c16;margin-top:4px}
.bps-n{font-size:12.5px;color:#5a6280;margin-top:2px}
.bps-d{font-size:14px;line-height:1.45;color:#2c3554;margin:14px 0 0}
.bps-go{display:flex;align-items:center;gap:12px;width:100%;margin:16px 0 4px;height:60px;padding:0 18px 0 8px;border:0;border-radius:30px;background:#9a7524;color:#fff;text-align:left;cursor:pointer;font:inherit;box-shadow:0 8px 18px rgba(154,117,36,.32)}
.bps-go>span:first-child{flex:none;width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;align-items:center;justify-content:center}
.bps-go>span:last-child{flex:1;min-width:0;display:flex;flex-direction:column}.bps-go b{font-size:16.5px}.bps-go em{font-style:normal;font-size:12.5px;opacity:.88;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bp-ep{display:flex;align-items:center;gap:12px;width:100%;padding:11px 2px;border:0;border-top:1px solid rgba(27,36,64,.07);background:none;text-align:left;color:var(--ink);font:inherit;cursor:pointer}
.bp-ep .n{flex:none;width:28px;font-size:12.5px;font-weight:650;color:#7a5c16;font-variant-numeric:tabular-nums}
.bp-ep b{flex:1;min-width:0;font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:16.5px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bp-ep .d{flex:none;font-size:12.5px;color:#5a6280;font-variant-numeric:tabular-nums}
.bp-ep.heard b{color:#5a6280}.bp-ep.heard .d{color:#9a7524;font-weight:700}
.bp-ep.now{background:rgba(201,162,74,.13);border-radius:12px;border-top-color:transparent;padding:11px 10px;margin:0 -8px;width:calc(100% + 16px)}.bp-ep.now .d{color:#7a5c16;font-weight:650}
/* ---- Library ---- */
.lib-sc{display:flex;flex-direction:column;justify-content:flex-end;width:100%;height:96px;padding:14px 18px;border:0;border-radius:22px;background:radial-gradient(circle at 86% 20%,rgba(201,162,74,.22),rgba(201,162,74,0) 45%),#1b2440;color:#fff;text-align:left;cursor:pointer;font:inherit}
.lib-sc b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:22px;font-weight:500}.lib-sc span{font-size:13px;color:rgba(255,255,255,.75)}
.lib-t{display:flex;align-items:center;gap:12px;width:100%;padding:10px 4px;border:0;border-bottom:1px solid rgba(27,36,64,.08);background:none;text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.lib-t .av{flex:none;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:"Iowan Old Style",Palatino,Georgia,serif;font-size:15px;color:#fff}
.lib-t>span:nth-child(2){flex:1;display:flex;flex-direction:column}.lib-t b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:17px;font-weight:500}.lib-t em{font-style:normal;font-size:12.5px;color:#5a6280}.lib-t i{font-style:normal;color:#5a6280;font-size:20px}
.lib-rec{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.lib-rec button{display:flex;flex-direction:column;gap:3px;padding:12px;border:0;border-radius:16px;background:#fffdf8;text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.lib-rec small{font-size:10px;font-weight:650;letter-spacing:.14em;text-transform:uppercase;color:#7a5c16}.lib-rec b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:15px;font-weight:500;line-height:1.25;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}.lib-rec em{font-style:normal;font-size:12px;color:#5a6280}
.lib-sk{display:block;margin:16px 4px 0;font-size:13px}
.tch-b{border-top:1px solid rgba(27,36,64,.08)}.tch-b summary{display:flex;justify-content:space-between;padding:12px 2px;font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;cursor:pointer;list-style:none}.tch-b summary span{font:600 12.5px -apple-system,system-ui,sans-serif;color:#7a5c16}
/* the mini player: one slim bar above the tabs; it slips under them while you scroll down */
#np.mini{grid-template-columns:minmax(0,1fr) auto auto;grid-template-rows:auto auto;column-gap:8px;row-gap:1px;padding:9px 8px 12px 16px;transition:transform .28s cubic-bezier(.2,.8,.2,1)}
#np.mini .t{grid-column:1;grid-row:1;font-size:15px;line-height:1.25}
#np.mini .s{grid-column:1;grid-row:2;font-size:12.5px}
#np.mini .times,#np.mini input[type=range]{display:none!important}
#np.mini .ctl2{grid-column:2;grid-row:1/3;align-self:center;justify-self:end;margin:0}
#np.mini #spd-dn,#np.mini #spd-up{display:none}
#np.mini .spd{border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.08)}
#np.mini #spd{min-width:46px!important;padding:6px 9px!important;font-size:13px!important;color:#fff}
#np.mini .ctl{grid-column:3;grid-row:1/3;display:flex;align-items:center;gap:2px;margin:0;padding:0}
#np.mini .ctl #prv,#np.mini .ctl #bk,#np.mini .ctl #fw{display:none!important}
#np.mini .ctl .big{width:42px!important;height:42px!important}
#np.mini .ctl #nxt{padding:6px 8px}
#np-hl{display:none}
#np.mini #np-hl{display:block;position:absolute;left:16px;right:16px;bottom:5px;height:2px;border-radius:1px;background:rgba(255,255,255,.16);overflow:hidden;pointer-events:none}
#np-hl i{display:block;height:100%;width:0;background:var(--gold);border-radius:1px}
body.hidehd #np.on.mini{transform:translateY(calc(100% + var(--tabh) + 20px))}
body.npon.hidehd #tabs{box-shadow:inset 0 2px 0 var(--gold)}
.jv-back svg{flex:none}.jv-back{display:inline-flex;align-items:center;gap:5px}
.t-ctl{display:flex;flex-direction:column;gap:10px;margin:0 0 6px}
.t-sort{display:flex;padding:3px;border-radius:18px;background:rgba(27,36,64,.07)}
.lib-seg{margin:10px 0 4px}.t-who{margin:0 0 6px;overflow-x:auto}.t-who button{flex:1 0 auto;padding:0 10px}
.lib-lead{font-size:13.5px;color:#5a6280;margin:14px 2px 6px}
.lib-tp{display:flex;align-items:center;gap:12px;width:100%;padding:13px 4px;border:0;border-bottom:1px solid rgba(27,36,64,.08);background:none;text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.lib-tp>span{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.lib-tp b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;font-weight:500}.lib-tp em{font-style:normal;font-size:12.5px;color:#5a6280;line-height:1.35;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}.lib-tp i{font-style:normal;font-size:12.5px;font-weight:600;color:#7a5c16}
.lib-bk{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.lib-bk button{display:flex;justify-content:space-between;align-items:baseline;gap:6px;padding:11px 12px;border:0;border-radius:14px;background:#fffdf8;color:var(--ink);text-align:left;cursor:pointer;font:inherit;min-width:0}
.lib-bk b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:16px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lib-bk em{font-style:normal;font-size:12px;color:#7a5c16;font-weight:600}
.tp-k{display:flex;align-items:center;gap:10px;width:100%;padding:10px 4px;border:0;border-bottom:1px solid rgba(27,36,64,.08);background:none;text-align:left;color:var(--ink);cursor:pointer;font:inherit;flex-wrap:wrap}
.tp-k b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:16.5px;font-weight:500;flex:none}.tp-k span{flex:1;min-width:140px;font-size:13px;color:#5a6280}.tp-k i{font-style:normal;color:#5a6280}
.tp-sc{display:flex;flex-direction:column;gap:2px;width:100%;margin:4px 0;padding:12px 16px;border:0;border-radius:18px;background:radial-gradient(circle at 86% 20%,rgba(201,162,74,.22),rgba(201,162,74,0) 45%),#1b2440;color:#fff;text-align:left;cursor:pointer;font:inherit}
.tp-sc small{font-size:10px;font-weight:650;letter-spacing:.16em;text-transform:uppercase;color:#e9cf8c}.tp-sc b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;font-weight:500}.tp-sc span{font-size:12.5px;color:rgba(255,255,255,.75)}
.jv-tp{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:22px 2px 4px}.jv-tp span{width:100%;font-size:10.5px;font-weight:650;letter-spacing:.2em;text-transform:uppercase;color:#7a5c16}
.jv-tp button{height:34px;padding:0 14px;border:1px solid rgba(154,117,36,.35);border-radius:17px;background:#fffdf8;color:#1b2440;font:600 13.5px -apple-system,system-ui,sans-serif;cursor:pointer}
.bp-gs{font-size:13px;color:#5a6280;margin:0 2px 2px}
.t-sort button{flex:1;height:34px;border:0;border-radius:15px;background:none;font:600 13.5px -apple-system,system-ui,sans-serif;color:#4a5272;cursor:pointer}
.t-sort button.on{background:#fff;color:var(--ink);box-shadow:0 1px 4px rgba(27,36,64,.14)}
.t-q{display:flex;align-items:center;gap:8px;height:40px;padding:0 14px;border-radius:20px;background:#fff;border:1px solid rgba(27,36,64,.1);color:#5a6280}
.t-q input{flex:1;min-width:0;border:0;background:none;font:15px -apple-system,system-ui,sans-serif;color:var(--ink);outline:none}
.tr2{display:flex;align-items:center;gap:12px;padding:10px 2px}.tr2+.tr2{border-top:1px solid rgba(27,36,64,.07)}
.tr2 .jw-t .t3{font-size:12px;color:#7a5c16}.tr2.heard .jw-t b{color:#5a6280}
</style></head><body>
<div id="topbar" aria-hidden="true"></div><button id="bookhd" aria-label="Go to this book's opening stop"></button><div class="top"><span id="pct" style="display:none"></span><button id="srch" aria-label="Search or go to a chapter"><svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg><span>Search</span></button><button id="mapbtn" aria-label="Map of the journey"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Zm0 0v13m6-10.5v13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg></button><button id="gear">⋯</button></div>
<div id="sheetbg" hidden></div><div id="sheet" role="dialog" aria-modal="true" hidden><div class="sh-grab"></div><div class="sh-top"><button id="shback" aria-label="Back" hidden>‹</button><span class="sh-kind" id="shkind"></span><button id="shx" aria-label="Close">✕</button></div><div id="shbody"></div></div>
<div id="jump" role="dialog" aria-modal="true" aria-label="Go to" hidden><div class="jp-top"><label class="jp-field"><svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><input id="jq" type="search" placeholder="Nehemiah, John 3:16, Goliath" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" enterkeyhint="go" aria-label="Search"></label><button id="jx">Close</button></div><div id="jbody"></div></div><div id="mapv" role="dialog" aria-modal="true" aria-label="Map of the journey" hidden><svg id="mapsvg" preserveAspectRatio="xMidYMid meet"></svg><div class="mv-top"><button id="mvx" aria-label="Close map">✕</button><div class="mv-title" id="mvtitle">Your journey</div></div><div class="mv-panel" id="mvpanel"><div class="mv-card" id="mvcard"></div><div class="mv-legs" id="mvlegs" aria-label="Legs of the journey"></div></div></div>
<div id="zt" hidden></div><div id="main"></div><nav id="tabs" aria-label="Main"></nav><div id="bps" hidden></div>
<div id="np"><div class="grab"></div>
<div class="np-top"><button id="np-min" aria-label="Shrink player"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><span class="np-lab">Now playing</span><button id="cls" aria-label="Stop and close">✕</button></div>
<div class="art" id="np-art"></div><div class="np-d" id="np-d"></div>
<div class="t serif" id="np-t"></div><div class="s" id="np-s"></div><div id="np-read" aria-label="Reader"></div>
<input type="range" id="seek" min="0" max="1000" value="0"><div class="times"><span id="cur">0:00</span><span id="rem">-0:00</span></div>
<div class="ctl"><button class="side sk" id="prv" aria-label="Previous"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14M19 5l-10 7 10 7z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg></button><button class="side" id="bk">↺ 10</button><button class="big" id="pp" style="display:flex;align-items:center;justify-content:center"></button><button class="side" id="fw">10 ↻</button><button class="side sk" id="nxt" aria-label="Next"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 5v14M5 5l10 7-10 7z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg></button></div>
<div id="np-hl" aria-hidden="true"><i></i></div><div class="ctl2"><div class="spd"><button id="spd-dn" aria-label="Slower">−</button><button id="spd">1×</button><button id="spd-up" aria-label="Faster">+</button></div><button id="zz">Sleep off</button></div></div>
<audio id="audio" preload="metadata"></audio><audio id="audiofx" preload="metadata" crossorigin="anonymous"></audio>
<script>
const D=__DATA__,I=D.items;
const S={get(k,d){try{const v=localStorage.getItem('sc:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},set(k,v){try{localStorage.setItem('sc:'+k,JSON.stringify(v));if(BK_KEYS.includes(k))localStorage.setItem('sc:bkdirty','1')}catch(e){}}};
/* Automatic backup to the listener's own private GitHub repo. The key never leaves this phone except to GitHub.
   Saved about every 10 minutes while something changed, and whenever the app goes to the background; every backup is
   a commit, so older versions stay in the repo's history. A new phone: paste the key once and everything comes back. */
const BK_KEYS=['camp','camp2','cfg','jp','level','lk2','narpos','prog','read','skip','speed','tab'],BK={sha:null,busy:false,tried:0,err:S.get('bkerr','')};
const bkRepo=()=>S.get('bkrepo','zreynard/scripture-companion-backup'),bkKey=()=>S.get('bkkey',''),bkOn=()=>!!bkKey();
function bkSnap(){const o={};BK_KEYS.forEach(k=>{try{const v=localStorage.getItem('sc:'+k);if(v!=null)o[k]=JSON.parse(v)}catch(e){}});return o}
function bkB64(str){const b=new TextEncoder().encode(str);let s='';for(let i=0;i<b.length;i+=0x8000)s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000));return btoa(s)}
function bkUn64(b64){return new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\s/g,'')),c=>c.charCodeAt(0)))}
function bkGH(path,opt={},key=bkKey(),repo=bkRepo()){return fetch('https://api.github.com/repos/'+repo+path,{method:opt.method||'GET',body:opt.body,cache:'no-store',headers:Object.assign({Authorization:'Bearer '+key,Accept:'application/vnd.github+json'},opt.body?{'Content-Type':'application/json'}:{})})}
async function bkFetch(){const r=await bkGH('/contents/progress.json');if(r.status===404){BK.sha=null;return null}if(!r.ok)throw r.status;const j=await r.json();BK.sha=j.sha;let c=j.content;
 if(!c||j.encoding!=='base64'){const r2=await bkGH('/git/blobs/'+j.sha);if(!r2.ok)throw r2.status;c=(await r2.json()).content}return JSON.parse(bkUn64(c))}
function bkFail(e){BK.err=e===401||e===403?'GitHub no longer accepts the backup key: paste a new one in ⋯':e===404?'The backup repo was not found':'';S.set('bkerr',BK.err);bkDot()}
async function bkSave(){if(!bkOn()||BK.busy)return;BK.busy=true;BK.tried=Date.now();try{
  const body={message:'Backup '+new Date().toISOString().slice(0,16).replace('T',' '),content:bkB64(JSON.stringify({v:1,at:Date.now(),data:bkSnap()}))};
  if(BK.sha===null)await bkFetch().catch(()=>{});if(BK.sha)body.sha=BK.sha;
  let r=await bkGH('/contents/progress.json',{method:'PUT',body:JSON.stringify(body)});
  if(r.status===409||r.status===422){await bkFetch();if(BK.sha)body.sha=BK.sha;r=await bkGH('/contents/progress.json',{method:'PUT',body:JSON.stringify(body)})}
  if(!r.ok)throw r.status;BK.sha=(await r.json()).content.sha;localStorage.removeItem('sc:bkdirty');S.set('bklast',Date.now());bkFail(0)}
 catch(e){if(typeof e==='number')bkFail(e)}finally{BK.busy=false;const st=document.getElementById('bkst');if(st)st.innerHTML=bkStatus()}}
function bkDue(){return bkOn()&&localStorage.getItem('sc:bkdirty')==='1'}
function bkApply(d){BK_KEYS.forEach(k=>{if(k in d)localStorage.setItem('sc:'+k,JSON.stringify(d[k]))});localStorage.setItem('sc:view',JSON.stringify('walk'));localStorage.removeItem('sc:bkdirty')}
function bkAgo(t){if(!t)return 'not yet';const m=Math.round((Date.now()-t)/60000);return m<1?'just now':m<60?m+' min ago':m<1440?Math.round(m/60)+' h ago':Math.round(m/1440)+' days ago'}
function bkStatus(){return BK.err?`<b style="color:#b3261e">Backup stopped.</b> ${BK.err}.`:`Backed up ${bkAgo(S.get('bklast',0))} to your private repo <b>${bkRepo()}</b>. It saves on its own; nothing to do.`}
function bkDot(){const g=document.getElementById('gear');if(g)g.classList.toggle('alert',!!(bkOn()&&BK.err))}
/* how much progress a snapshot holds, to tell an empty new phone from a used one */
function bkWeight(d){return Object.keys((d&&d.prog)||{}).length+Object.keys((d&&d.read)||{}).length}

let prog=S.get('prog',{}),read=S.get('read',{}),cfg=Object.assign(S.get('cfg',{who:''}),{order:'canon'}),view=S.get('view','walk'),camp=S.get('camp',null);
const okWho=id=>!cfg.who||I[id].who===cfg.who;
// --- denser scenery: terrain everywhere, per-book motifs, more vignettes, celestial bodies, rivers ---
const MOTIF={'The Law':'palm','History':'town','Wisdom & Song':'olive','Major Prophets':'cedar','Minor Prophets':'town','The Gospels':'olive','The Church Begins':'sail','Letters of Paul':'column','General Letters':'fire','The New Beginning':'tree'};
function motif(kind,x,y,sc=1){const d=x<195?1:-1;return `<g transform="translate(${x} ${y}) scale(${d*sc} ${sc})" fill="none" stroke="${G}.28)" stroke-width="1" stroke-linecap="round"><path d="M0 0 c14 -10 30 -8 38 4 c6 10 -4 18 -12 12 c-6 -6 2 -14 8 -8 M0 0 c-8 -12 -8 -26 2 -36 c8 -8 20 -6 22 4 c2 8 -8 12 -12 6 c-3 -5 3 -10 8 -6"/><circle cx="26" cy="8" r="1.4" fill="${G}.5)" stroke="none"/><circle cx="4" cy="-30" r="1.4" fill="${G}.5)" stroke="none"/></g>`}
const I_='rgba(60,80,160,';function terrain(H){let out='';for(let y=160;y<H;y+=560){const k=y/560;out+=hills(y+40,20+(k%3)*6,.045,I_,k*137)+hills(y+140,14,.03,I_,k*89+200)}return out}
function celestial(H){return `<circle cx="195" cy="-60" r="420" fill="url(#dawn)"/><g stroke="${G}.10)" stroke-width="1">${[-70,-50,-30,-10,10,30,50,70].map(a=>`<line x1="195" y1="-40" x2="${195+Math.sin(a*Math.PI/180)*900}" y2="${-40+Math.cos(a*Math.PI/180)*900}"/>`).join('')}</g><circle cx="195" cy="${H-60}" r="700" fill="url(#glory)"/><g stroke="${G}.14)" stroke-width="1">${[-80,-60,-40,-20,0,20,40,60,80].map(a=>`<line x1="195" y1="${H-60}" x2="${195+Math.sin(a*Math.PI/180)*900}" y2="${H-60-Math.cos(a*Math.PI/180)*900}"/>`).join('')}</g>`}
function river(x,y,op=.22){return `<path d="M0 ${y-6} C 60 ${y-26} 120 ${y+14} 190 ${y} S 320 ${y-22} 390 ${y+4} v18 C 320 ${y+2} 260 ${y+26} 190 ${y+18} S 60 ${y-4} 0 ${y+12}z" fill="${B}${op})"/>`}
function vignette2(kind,x,y){const t=`transform="translate(${x} ${y})"`;
 switch(kind){
 case 'sun':return `<g ${t}><circle cx="0" cy="-60" r="34" fill="url(#halo)"/><circle cx="0" cy="-60" r="10" fill="${G}.7)"/>${[0,1,2,3,4,5,6,7].map(i=>`<line x1="${Math.cos(i*Math.PI/4)*16}" y1="${-60+Math.sin(i*Math.PI/4)*16}" x2="${Math.cos(i*Math.PI/4)*26}" y2="${-60+Math.sin(i*Math.PI/4)*26}" stroke="${G}.45)" stroke-width="1.4"/>`).join('')}</g>`;
 case 'serpent':return `<g ${t} stroke="${G}.4)" fill="${G}.10)" stroke-width="1.4"><path d="M-70 10 v-30"/><circle cx="-70" cy="-54" r="18"/><circle cx="-82" cy="-44" r="12"/><circle cx="-58" cy="-44" r="12"/><circle cx="-76" cy="-50" r="2.5" fill="${G}.9)"/><circle cx="-62" cy="-46" r="2.5" fill="${G}.9)"/><path d="M60 10 c6 -14 -8 -20 -4 -32 4 -8 14 -8 16 -2 2 8 -10 10 -12 2" fill="none"/></g>`;
 case 'tent':return `<g ${t} fill="${W_}.12)"><path d="M-100 10 l24 -28 24 28z M-40 10 l18 -20 18 20z M40 10 l28 -32 28 32z"/><path d="M110 10 v-50 M110 -40 c-16 -4 -26 -14 -28 -28 14 2 24 10 28 28 c4 -18 14 -26 28 -28 -2 14 -12 24 -28 28" stroke="${G}.35)" fill="none" stroke-width="1.5"/></g>`;
 case 'altar':return `<g ${t}><path d="M-90 10 L0 -70 L90 10Z" fill="${W_}.08)"/><rect x="-16" y="-20" width="32" height="12" fill="${W_}.2)"/><circle cx="0" cy="-30" r="16" fill="url(#ember)"/></g>`;
 case 'coat':return `<g ${t}><path d="M-120 10 q60 -20 120 0 t120 0" stroke="${G}.18)" fill="none" stroke-width="2"/>${[-70,-40,-10,20,50].map(cx=>`<path d="M${cx} 4 l6 -14 8 0 6 14z M${cx+6} -10 l4 -8 4 8" fill="${W_}.14)"/>`).join('')}</g>`;
 case 'flame':return `<g ${t}><circle cx="70" cy="-30" r="44" fill="url(#ember)"/><g stroke="${G}.4)" fill="none" stroke-width="1.3"><path d="M70 -6 c-14 -2 -22 -10 -22 -22 M70 -6 c14 -2 22 -10 22 -22 M70 -6 c-8 -10 -8 -20 -2 -30 M70 -6 c8 -10 8 -20 2 -30 M70 -6 v-12"/></g></g>`;
 case 'grapes':return `<g ${t} fill="${G}.22)" stroke="${G}.4)" stroke-width="1"><path d="M-80 10 c0 -30 20 -40 40 -40 M-40 -30 c20 0 40 10 40 40" fill="none"/>${[-50,-40,-30,-45,-35,-40].map((cx,i)=>`<circle cx="${cx}" cy="${-22+(i>2?10:0)+(i>4?10:0)}" r="5"/>`).join('')}</g>`;
 case 'pillars':return `<g ${t} fill="${W_}.12)"><rect x="-60" y="-70" width="14" height="70" transform="rotate(-10 -53 -35)"/><rect x="46" y="-70" width="14" height="70" transform="rotate(10 53 -35)"/><path d="M-70 -70 h140 l-10 -12 h-120z" transform="rotate(-3)"/></g>`;
 case 'wheat':return `<g ${t} stroke="${G}.35)" fill="none" stroke-width="1.2">${[-90,-75,-60,-45,-30,30,45,60,75,90].map((cx,i)=>`<path d="M${cx} 10 v-${28+(i%3)*6} M${cx} -${20+(i%3)*6} l-5 -6 M${cx} -${26+(i%3)*6} l5 -6 M${cx} -${30+(i%3)*6} l-5 -6"/>`).join('')}</g>`;
 case 'stone':return `<g ${t} fill="${W_}.12)"><path d="M-110 10 q60 -16 220 0z"/><path d="M40 10 v-50 l10 -26 10 26 v50z" /><circle cx="-40" cy="-14" r="6" fill="${W_}.3)"/><path d="M-40 -14 q30 -40 70 -40" stroke="${W_}.25)" fill="none" stroke-dasharray="3 4"/></g>`;
 case 'crown':return `<g ${t}><circle cx="0" cy="-30" r="70" fill="url(#halo)"/><path d="M-40 0 h80 l-6 -40 -18 14 -16 -30 -16 30 -18 -14z" fill="${G}.35)"/></g>`;
 case 'house':return `<g ${t} fill="${W_}.12)"><path d="M-80 10 v-30 l30 -22 30 22 v30z M-62 10 v-18 h22 v18z"/><path d="M20 10 v-24 l24 -18 24 18 v24z" opacity=".7"/><path d="M-120 10 h240" stroke="${W_}.2)"/></g>`;
 case 'wall':return `<g ${t} fill="${W_}.12)"><rect x="-130" y="-30" width="260" height="30"/>${[-130,-110,-90,-70,-50,-30,-10,10,30,50,70,90,110].map(cx=>`<rect x="${cx+3}" y="-40" width="12" height="10"/>`).join('')}<rect x="-20" y="-56" width="40" height="56" /><rect x="-24" y="-66" width="48" height="10"/></g>`;
 case 'wind':return `<g ${t} stroke="${W_}.25)" fill="none" stroke-width="1.6"><path d="M-110 -20 c30 -20 60 20 90 0 s60 -20 90 0 M-100 0 c30 -20 60 20 90 0 s60 -20 90 0 M-90 20 c30 -20 60 20 90 0 s60 -20 90 0"/></g>`;
 case 'staff':return `<g ${t}><path d="M-130 10 q65 -30 130 -10 t130 10z" fill="${W_}.08)"/>${[-60,-30,10,40,70].map(cx=>`<ellipse cx="${cx}" cy="-8" rx="9" ry="6" fill="${W_}.3)"/>`).join('')}<path d="M-90 0 v-50 a8 8 0 0 1 16 0" stroke="${G}.5)" fill="none" stroke-width="2"/></g>`;
 case 'eye':return `<g ${t}><circle cx="0" cy="-50" r="80" fill="url(#halo)"/>${[-60,-40,-20,0,20,40,60].map(a=>`<line x1="0" y1="-50" x2="${Math.sin(a*Math.PI/180)*150}" y2="${-50-Math.cos(a*Math.PI/180)*150}" stroke="${G}.2)"/>`).join('')}<path d="M-30 -30 h60 v30 h-60z" fill="${G}.3)"/></g>`;
 case 'lamb':return `<g ${t}><path d="M-120 10 q60 -20 240 0z" fill="${W_}.08)"/><path d="M-20 0 a20 14 0 0 1 40 0z M-14 0 v8 M14 0 v8 M18 -14 l8 -6" fill="${W_}.35)" stroke="${W_}.35)"/><path d="M60 0 v-60 M46 -44 h28" stroke="${W_}.3)" stroke-width="2"/></g>`;
 case 'scroll':return `<g ${t} fill="${W_}.12)"><path d="M-50 -60 h100 v70 h-100z"/><g stroke="${W_}.25)">${[-44,-32,-20,-8,4].map(yy=>`<line x1="-40" y1="${yy}" x2="40" y2="${yy}"/>`).join('')}</g><circle cx="-50" cy="-60" r="6"/><circle cx="50" cy="-60" r="6"/></g>`;
 case 'bones':return `<g ${t} stroke="${W_}.3)" stroke-width="3" stroke-linecap="round">${[[-90,0,-60,-14],[-40,4,-6,2],[20,-6,52,6],[70,2,100,-10],[-70,-30,-40,-26]].map(([a,b,c,d])=>`<line x1="${a}" y1="${b}" x2="${c}" y2="${d}"/>`).join('')}</g>`;
 case 'star':return `<g ${t}><circle cx="0" cy="-90" r="60" fill="url(#halo)"/><circle cx="0" cy="-90" r="2.5" fill="${G}.95)"/><path d="M0 -120 v60 M-30 -90 h60" stroke="${G}.35)"/><path d="M-120 10 q60 -24 120 -6 t120 6z" fill="${W_}.08)"/></g>`;
 case 'lamp':return `<g ${t}><circle cx="0" cy="-40" r="60" fill="url(#halo)"/><path d="M-40 0 h80 M0 0 v-40 M-30 -40 h60 M-30 -40 v-14 M-15 -40 v-20 M0 -40 v-26 M15 -40 v-20 M30 -40 v-14" stroke="${G}.5)" stroke-width="2" fill="none"/></g>`;
 case 'figure':return `<g ${t}><path d="M-140 10 q70 -30 280 0z" fill="${W_}.08)"/><path d="M-30 -2 l0 -22 M-30 -24 a4 4 0 1 1 .1 0 M-30 -18 l-8 10 M-30 -18 l10 8 M-30 -2 l-6 12 M-30 -2 l8 12" stroke="${W_}.45)" fill="none" stroke-width="1.6"/><path d="M60 -2 l0 -24 M60 -26 a4 4 0 1 1 .1 0 M60 -18 l-12 -6 M60 -18 l12 -6 M60 -2 l-6 12 M60 -2 l6 12" stroke="${G}.6)" fill="none" stroke-width="1.6"/></g>`;
 case 'tomb':return `<g ${t}><path d="M-60 10 v-40 a60 40 0 0 1 120 0 v40z" fill="${W_}.10)"/><circle cx="-30" cy="-10" r="22" fill="rgba(255,255,255,.9)" stroke="${W_}.2)"/></g>`;
 case 'lightning':return `<g ${t}><circle cx="0" cy="-60" r="70" fill="url(#halo)"/><path d="M10 -130 l-22 50 h20 l-16 60 l40 -74 h-20 l16 -36z" fill="${G}.55)"/></g>`;
 case 'dove':return `<g ${t}><path d="M-20 -40 c10 -16 30 -16 40 -4 8 -4 20 -2 26 4 l-10 2 c-10 10 -30 14 -46 8 -8 -2 -10 -6 -10 -10z" fill="${W_}.4)"/><path d="M-110 10 q110 -30 220 0z" fill="${W_}.06)"/></g>`;
 case 'heart':return `<g ${t}><circle cx="0" cy="-40" r="60" fill="url(#halo)"/><path d="M0 -10 s-30 -18 -30 -40 a16 16 0 0 1 30 -8 16 16 0 0 1 30 8c0 22 -30 40 -30 40z" fill="${G}.35)"/></g>`;
 }return vignette(kind,x,y,0)}

const G='rgba(168,129,42,',W_='rgba(27,36,64,',B='rgba(70,120,200,';
let HH=4000;function hills(y,amp,op,col,phase=0){let d=`M0 ${y+amp}`;for(let x=0;x<=390;x+=10){d+=` L${x} ${(y+amp*Math.sin((x+phase)/62)).toFixed(1)}`}return `<path d="${d}" fill="none" stroke="${col}${Math.min(.35,op*4)})" stroke-width="1"/>`}
function sceneSVG(kind,x,y){
 const sky=(c,r)=>`<circle cx="${x}" cy="${y-20}" r="${r}" fill="url(#halo)"/>`;
 switch(kind){
 case 'dunes':return sky(0,150)+hills(y+40,26,.10,G,0)+hills(y+90,18,.08,G,200)+hills(y+140,12,.06,W_,80)+`<path d="M${x+120} ${y+58} v-34 M${x+120} ${y+30} c-14 -6 -24 -18 -22 -30 12 2 22 10 22 30 c0 -20 10 -28 22 -30 2 12 -8 24 -22 30" fill="none" stroke="${G}.35)" stroke-width="1.6"/>`;
 case 'city':return `<path d="M0 ${y+120} h30 v-30 h22 v12 h18 v-40 l10 -14 10 14 v40 h26 v-20 h30 v20 h40 v-28 h24 v-12 h16 v12 h22 v28 h30 v-36 l12 -16 12 16 v36 h28 v-20 h30 v20 h30" fill="none" stroke="${G}.26)" stroke-width="1"/><path d="M0 ${y+128} H390" stroke="${G}.12)" stroke-width="1"/>`;
 case 'harp':return hills(y+60,30,.09,W_,40)+hills(y+120,20,.06,W_,300)+`<g stroke="${G}.22)" stroke-width="1">${[0,1,2,3,4,5].map(i=>`<line x1="${30+i*60}" y1="${y-40}" x2="${60+i*60}" y2="${y+200}"/>`).join('')}</g>`;
 case 'flame':return `<path d="M0 ${y+150} L40 ${y+60} L80 ${y+120} L130 ${y+20} L180 ${y+110} L230 ${y+50} L280 ${y+130} L330 ${y+70} L390 ${y+140}" fill="none" stroke="${G}.3)" stroke-width="1"/><path d="M0 ${y+170} L60 ${y+120} L120 ${y+160} L200 ${y+100} L270 ${y+165} L340 ${y+120} L390 ${y+160}" fill="none" stroke="${G}.18)" stroke-width="1"/><ellipse cx="195" cy="${y+150}" rx="150" ry="40" fill="url(#ember)"/>`;
 case 'star':return `<circle cx="${x}" cy="${y-30}" r="3" fill="${G}.95)"/><path d="M${x} ${y-70} v80 M${x-40} ${y-30} h80" stroke="${G}.35)" stroke-width="1"/><circle cx="${x}" cy="${y-30}" r="60" fill="url(#halo)"/>`+hills(y+80,24,.10,W_,120)+`<g fill="${W_}.08)">${[150,180,205,235].map((cx,i)=>`<rect x="${cx}" y="${y+66-(i%2)*8}" width="22" height="${30+(i%2)*8}"/>`).join('')}<path d="M148 ${y+66} l13 -12 13 12z M203 ${y+58} l13 -12 13 12z"/></g>`+`<path d="M0 ${y+200} Q 100 ${y+185} 200 ${y+200} T 390 ${y+195} V${HH} H0Z" fill="${B}.10)"/>`;
 case 'waves':return `<g fill="none" stroke="${B}.25)" stroke-width="1.5">${[0,1,2,3,4].map(i=>`<path d="M0 ${y+60+i*22} Q 40 ${y+48+i*22} 80 ${y+60+i*22} T 160 ${y+60+i*22} T 240 ${y+60+i*22} T 320 ${y+60+i*22} T 400 ${y+60+i*22}"/>`).join('')}</g><path d="M${x-50} ${y+150} h70 l-10 12 h-50z M${x-15} ${y+150} v-50 l40 40z" fill="${W_}.12)"/>`;
 case 'letters':return `<path d="M0 ${y+150} C 80 ${y+120} 140 ${y+170} 220 ${y+140} S 340 ${y+120} 390 ${y+150} V${HH} H0Z" fill="${B}.08)"/><g fill="${W_}.08)"><rect x="40" y="${y+60}" width="10" height="70"/><rect x="64" y="${y+60}" width="10" height="70"/><rect x="88" y="${y+60}" width="10" height="70"/><path d="M30 ${y+60} h78 l-8 -14 h-62z"/><rect x="30" y="${y+130}" width="78" height="8"/></g>`;
 case 'lamp':return hills(y+80,22,.08,W_,0)+`<g>${[60,140,230,320].map((cx,i)=>`<circle cx="${cx}" cy="${y+70+(i%2)*14}" r="26" fill="url(#ember)"/><circle cx="${cx}" cy="${y+70+(i%2)*14}" r="2" fill="${G}.9)"/>`).join('')}</g>`;
 case 'city2':return `<circle cx="195" cy="${y+60}" r="170" fill="url(#halo)"/><path d="M60 ${y+150} v-40 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v-50 l15 -22 15 22 v50 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v40" fill="none" stroke="${G}.45)" stroke-width="1.2"/><g stroke="${G}.22)" stroke-width="1">${[-60,-30,0,30,60].map(a=>`<line x1="195" y1="${y+40}" x2="${195+Math.sin(a*Math.PI/180)*220}" y2="${y+40-Math.cos(a*Math.PI/180)*220}"/>`).join('')}</g>`;
 }return ''}
function vignette(kind,x,y,i){const L=x<195;const side=L?1:-1;
 switch(kind){
 case 'waves':return `<g transform="translate(${x} ${y})"><path d="M-110 10 C -90 -40 -60 -50 -30 -60 L -30 40 L -110 40Z" fill="${B}.22)"/><path d="M110 10 C 90 -40 60 -50 30 -60 L 30 40 L 110 40Z" fill="${B}.22)"/><path d="M-30 -60 c-10 -12 -16 -24 -14 -40 M30 -60 c10 -12 16 -24 14 -40" stroke="${B}.35)" fill="none"/></g>`;
 case 'mountain':return `<g transform="translate(${x} ${y})"><path d="M-140 60 L-60 -120 L-20 -60 L20 -150 L70 -70 L140 60Z" fill="${W_}.10)"/><path d="M-40 -170 q30 -20 60 0 q30 20 60 0" stroke="${W_}.20)" fill="none" stroke-width="3"/><path d="M20 -150 l-14 40 l16 -8 l-18 48" stroke="${G}.6)" stroke-width="1.6" fill="none"/></g>`;
 case 'rain':return `<g transform="translate(${x} ${y})"><g stroke="${B}.35)" stroke-width="1">${[-90,-70,-50,-30,-10,10,30,50,70,90].map(d=>`<line x1="${d}" y1="-120" x2="${d-12}" y2="-50"/>`).join('')}</g><path d="M-70 -30 h140 l-16 26 h-108z M-25 -30 v-28 h50 v28" fill="${W_}.14)"/><path d="M-120 0 q60 -14 120 0 t120 0" stroke="${B}.3)" fill="none" stroke-width="2"/></g>`;
 case 'trumpet':return `<g transform="translate(${x} ${y})" fill="${W_}.12)"><rect x="-120" y="-70" width="60" height="70" transform="rotate(-8 -90 -35)"/><rect x="60" y="-80" width="60" height="80" transform="rotate(10 90 -40)"/><rect x="-150" y="-40" width="30" height="40" transform="rotate(-24 -135 -20)"/><rect x="120" y="-30" width="30" height="30" transform="rotate(20 135 -15)"/></g>`;
 case 'temple':return `<g transform="translate(${x} ${y})" fill="${G}.18)"><path d="M-80 -40 h160 l-10 -18 h-140z"/>${[-70,-45,-20,5,30,55].map(cx=>`<rect x="${cx}" y="-40" width="12" height="46"/>`).join('')}<rect x="-85" y="6" width="170" height="8"/><path d="M-140 40 L-80 14 L80 14 L140 40Z" fill="${W_}.06)"/></g>`;
 case 'ruins':return `<g transform="translate(${x} ${y})" fill="${W_}.10)"><path d="M-120 20 v-50 l16 10 v40z M-80 20 v-80 l18 -12 v92z M40 20 v-40 l16 -18 v58z M90 20 v-70 l14 8 v62z"/><ellipse cx="0" cy="-30" rx="110" ry="30" fill="url(#ember)"/></g>`;
 case 'cross':return `<g transform="translate(${x} ${y})"><path d="M-130 30 Q 0 -40 130 30Z" fill="${W_}.08)"/><g stroke="${W_}.45)" stroke-width="2.5" stroke-linecap="round"><path d="M0 -20 v-70 M-16 -70 h32"/><path d="M-45 -10 v-50 M-56 -46 h22"/><path d="M45 -10 v-50 M34 -46 h22"/></g></g>`;
 case 'sunrise':return `<g transform="translate(${x} ${y})"><circle cx="0" cy="-20" r="90" fill="url(#halo)"/><path d="M-50 10 a50 50 0 0 1 100 0z" fill="${W_}.10)"/><path d="M-22 10 a22 30 0 0 1 44 0z" fill="rgba(255,255,255,.9)"/></g>`;
 case 'manger':return `<g transform="translate(${x} ${y})"><circle cx="0" cy="-130" r="3" fill="${G}.95)"/><path d="M0 -127 L-26 10 M0 -127 L26 10" stroke="${G}.18)" fill="none"/><path d="M-60 10 v-40 l60 -36 60 36 v40z" fill="${W_}.10)"/></g>`;
 case 'city':return `<g transform="translate(${x} ${y})"><circle cx="0" cy="-60" r="160" fill="url(#halo)"/><path d="M-120 10 v-40 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v-50 l20 -26 20 26 v50 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v40" fill="none" stroke="${G}.6)" stroke-width="1.4" stroke-linejoin="round"/><path d="M-130 10 h260" stroke="${G}.35)"/></g>`;
 case 'tent':return `<g transform="translate(${x} ${y})"><path d="M${side*90} 14 v-60 M${side*90} -46 c-18 -4 -30 -18 -30 -36 16 2 28 14 30 36 2 -22 14 -34 30 -36 0 18 -12 32 -30 36" stroke="${G}.4)" fill="none" stroke-width="1.6"/><path d="M${side*20} 14 l24 -30 24 30z" fill="${W_}.12)"/></g>`;
 case 'flame':return `<g transform="translate(${x} ${y})"><circle cx="${side*60}" cy="-30" r="50" fill="url(#ember)"/><path d="M${side*60} -10 c8 -14 2 -24 -2 -34 -3 8 -8 10 -8 2 -8 10 -6 24 10 32z" fill="${G}.45)"/></g>`;
 case 'lion':return `<g transform="translate(${x} ${y})"><path d="M-70 20 a70 60 0 0 1 140 0z" fill="rgba(27,36,64,.18)"/><path d="M-70 20 a70 60 0 0 1 140 0" stroke="${W_}.14)" fill="none"/></g>`;
 case 'whale':return `<g transform="translate(${x} ${y})"><path d="M-130 10 q60 -16 130 0 t130 0 v40 h-260z" fill="${B}.18)"/><path d="M-40 10 c20 -24 60 -24 80 0 l24 -16 -6 16 6 16 -24 -16" fill="rgba(27,36,64,.25)"/></g>`;
 default:return ''}}

const ICON={sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
serpent:'<path d="M4 17c3-5 6 5 9 0s4-6 7-2M20 15l-1-1"/>',rain:'<path d="M7 14h10a4 4 0 0 0 0-8 5 5 0 0 0-9.6 1A3.5 3.5 0 0 0 7 14zM9 17v3M13 17v3M17 17v3"/>',
tent:'<path d="M3 20h18L12 5zM12 5v15"/>',flame:'<path d="M12 3c3 4 6 6 6 11a6 6 0 0 1-12 0c0-3 1-4 2-6 1 2 2 3 3 3 0-3 0-5 1-8z"/>',
coat:'<path d="M8 4h8l3 4-3 1v11H8V9L5 8zM12 4v16"/>',waves:'<path d="M2 9c3-2 5-2 8 0s5 2 8 0 3-1 4 0M2 15c3-2 5-2 8 0s5 2 8 0 3-1 4 0"/>',
mountain:'<path d="M2 20L9 7l4 6 2-3 7 10z"/>',grapes:'<circle cx="12" cy="7" r="2"/><circle cx="9" cy="11" r="2"/><circle cx="15" cy="11" r="2"/><circle cx="12" cy="15" r="2"/><circle cx="9" cy="19" r="2"/><circle cx="15" cy="19" r="2"/><path d="M12 5V2"/>',
trumpet:'<path d="M3 10h8l9-5v14l-9-5H3z"/>',pillars:'<path d="M4 20h16M6 20V8M12 20V8M18 20V8M4 8h16"/>',
wheat:'<path d="M12 22V8M12 8C9 8 7 6 7 3c3 0 5 2 5 5zM12 8c3 0 5-2 5-5-3 0-5 2-5 5zM12 13c-3 0-5-2-5-5 3 0 5 2 5 5zM12 13c3 0 5-2 5-5-3 0-5 2-5 5z"/>',
stone:'<path d="M3 21c3-5 7-7 10-7M9 16a5 4 0 1 0 10 0 5 4 0 1 0-10 0"/>',crown:'<path d="M3 18h18l-2-10-5 4-2-6-2 6-5-4z"/>',
temple:'<path d="M4 20h16M5 8h14M7 8v12M12 8v12M17 8v12M4 8l8-5 8 5"/>',ruins:'<path d="M3 20h18M5 20V12l3 2v6M10 20V9l3-2v13M16 20v-6l3-3v9"/>',
wall:'<path d="M3 8h18v12H3zM3 12h18M3 16h18M8 8v4M14 8v4M11 12v4M6 16v4M16 16v4"/>',wind:'<path d="M3 8h11a3 3 0 1 0-3-3M3 13h15a3 3 0 1 1-3 3M3 18h8"/>',
staff:'<path d="M9 22V7a3 3 0 1 1 6 0v2"/>',eye:'<path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="3"/>',
scroll:'<path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h4"/>',bones:'<path d="M5 19L19 5M5 5l14 14"/><circle cx="5" cy="5" r="1.5"/><circle cx="19" cy="19" r="1.5"/><circle cx="19" cy="5" r="1.5"/><circle cx="5" cy="19" r="1.5"/>',
lion:'<circle cx="12" cy="12" r="7"/><path d="M9 11h.1M15 11h.1M9 15c2 2 4 2 6 0M12 2v3M5 5l2 2M19 5l-2 2"/>',fish:'<path d="M3 12c4-6 10-6 14 0-4 6-10 6-14 0zM17 12l4-4v8z"/>',
star:'<path d="M12 2l3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>',cross:'<path d="M12 3v18M6 9h12"/>',
sunrise:'<path d="M3 18h18M7 18a5 5 0 0 1 10 0M12 7V4M5 10L3 8M19 10l2-2"/>',manger:'<path d="M3 20h18M5 20l7-8 7 8M12 12V9M12 2l1.5 3 3.5.5-2.5 2.5.5 3.5-3-1.5-3 1.5.5-3.5L7 5.5 10.5 5z"/>',
figure:'<circle cx="12" cy="5" r="2"/><path d="M9 21l3-8 3 8M12 13V8M8 11l4-3 4 3"/>',lamp:'<path d="M9 18h6M10 21h4M12 3a6 6 0 0 1 3 11v4H9v-4a6 6 0 0 1 3-11z"/>',
tomb:'<path d="M4 20h16M6 20V10a6 6 0 0 1 12 0v10M9 20v-6h6v6"/>',dove:'<path d="M3 12c4 0 6-4 9-4 2 0 3 2 6 2l3-1-3 3c-2 4-6 6-9 6-3 0-4-2-6-6z"/>',
lightning:'<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',heart:'<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
city:'<path d="M3 20h18M4 20V9h5v11M9 20V5h6v15M15 20v-8h5v8"/>',play:'<path d="M8 5l12 7-12 7z" fill="currentColor" stroke="none"/>',pause:'<path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" stroke="none"/>',altar:'<path d="M4 20h16M6 20v-6h12v6M12 14c2-2 3-4 2-6-1 1-2 1-2-1-2 2-3 4-2 6"/>',goat:'<path d="M4 18l3-7h10l3 7M7 11c-2-2-3-4-2-7M17 11c2-2 3-4 2-7M9 18v3M15 18v3"/>',
whale:'<path d="M2 13c3-5 9-7 15-4l4-3-1 5 1 5-4-3c-6 3-12 1-15-4zM6 12h.1"/>',house:'<path d="M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6"/>',lamb:'<path d="M6 12a4 4 0 0 1 4-4h5a3 3 0 0 1 3 3v2a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3zM9 16v4M15 16v4M18 9l2-2"/>'};
const icon=(k,sz=14,st=1.6,color='var(--gold2)')=>`<svg viewBox="0 0 24 24" width="${sz}" height="${sz}" fill="none" stroke="${color}" stroke-width="${st}" stroke-linecap="round" stroke-linejoin="round">${ICON[k]||ICON.star}</svg>`;
const LANDMARKS={'Gen1':['sun','Creation'],'Gen3':['serpent','The Fall'],'Gen7':['rain','The Flood'],'Gen12':['tent','The call of Abram'],'Gen22':['altar','Moriah'],'Gen37':['coat','Joseph sold'],'Exo3':['flame','The burning bush'],'Exo14':['waves','The sea parts'],'Exo20':['mountain','Sinai'],'Lev16':['goat','The Day of Atonement'],'Num13':['grapes','The spies'],'Deu34':['mountain','Moses sees the land'],'Jos6':['trumpet','Jericho'],'Jdg16':['pillars','Samson'],'Rut1':['wheat','Ruth in the fields'],'1Sa17':['stone','David and Goliath'],'2Sa7':['crown','A throne forever'],'1Ki8':['temple','The Temple'],'1Ki18':['flame','Carmel'],'2Ki25':['ruins','Jerusalem falls'],'Ezr1':['house','The return'],'Neh2':['wall','The walls'],'Job38':['wind','Out of the whirlwind'],'Psa23':['staff','The Shepherd'],'Isa6':['eye','Holy, holy, holy'],'Isa53':['lamb','The suffering servant'],'Jer31':['scroll','A new covenant'],'Eze37':['bones','Dry bones'],'Dan6':['lion','The lions’ den'],'Jon2':['whale','Jonah'],'Mic5':['star','Bethlehem foretold'],'Mat2':['star','The star'],'Mat5':['mountain','The Sermon on the Mount'],'Mat27':['cross','The cross'],'Mat28':['sunrise','The empty tomb'],'Luk2':['manger','Bethlehem'],'Luk15':['figure','The prodigal'],'Joh1':['lamp','The Word'],'Joh11':['tomb','Lazarus'],'Act2':['flame','Pentecost'],'Act9':['lightning','The Damascus road'],'Rom8':['dove','No condemnation'],'1Co13':['heart','Love'],'Rev21':['city','The New Jerusalem']};
const SCENES={'The Law':'dunes','History':'city','Wisdom & Song':'harp','Major Prophets':'flame','Minor Prophets':'flame','The Gospels':'star','The Church Begins':'waves','Letters of Paul':'letters','General Letters':'lamp','The New Beginning':'city2'};

const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=s=>{s=Math.max(0,Math.round(s||0));const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(x).padStart(2,'0')};
const mins=s=>s?Math.round(s/60)+' min':'';
const isDone=id=>!!(prog[id]&&prog[id].done);
// Listened = at least 70% of the teaching actually played (seconds heard, not where the slider sits)
const DONE_AT=0.7,body=id=>{const p=prog[id]||{};return Math.max(1,(p.dur||0)-(I[id].s||0)-(I[id].e||0))},tail=()=>cur&&I[cur]&&I[cur].e||0,heardPct=id=>{const p=prog[id]||{};return p.dur&&p.heard?Math.min(100,Math.round(100*p.heard/body(id))):0};
let lastT=null,ready=true;const OPEN=new Set();
/* ---- the Bible text (Berean Standard Bible, public domain): one file per book, fetched once, then offline ---- */
/* ---- people, places and the map (atlas.json, loaded on first use) ---- */
let ATL=null,ATL_D=null;function atlas(){return ATL||(ATL=fetch('atlas.json').then(r=>{if(!r.ok)throw 0;return r.json()}).then(d=>(ATL_D=d)).catch(e=>{ATL=null;throw e}))}
function rich(t){return esc(t).replace(/⟦([pl]):([^|⟧]+)\|([^⟧]+)⟧((?:(?:&#39;|['’])s)?[.,;:!?)]*)/g,(m,k,sl,tx,tail)=>{const btn=`<button class="nm ${k}" data-nk="${k}" data-ns="${sl}">${tx}</button>`;return tail?`<span class="nw">${btn}${tail}</span>`:btn})}
const SHEET=[];
function bookNames(){return D.books.map(b=>b.name)}
function refLinks(t){ /* "(Exodus 3)" -> a tap goes to that chapter; names become name buttons */
 return rich(t).replace(/\(([1-3]?\s?[A-Z][A-Za-z]+(?:\s(?:of\s)?[A-Z][a-z]+)?)\s(\d+)(?::[\d–\-, ]+)?\)/g,(m,bk,ch)=>{const nm=bk==='Psalm'?'Psalms':bk==='Song of Songs'?'Song of Solomon':bk;
  return bookNames().includes(nm)?`<span style="white-space:nowrap">(<button class="go" data-gob="${nm}" data-goc="${ch}">${bk} ${ch}</button>)</span>`:m})}
/* ---- hours: listened of available (rounded); a feed without a length counts 40 min (10 for a devotional) ---- */
let AVAIL=null;function avail(){if(AVAIL)return AVAIL;const est=it=>+it.dur||(it.tr==='devotional'?600:2400),book={},all=new Set();
 for(const b of D.books){const set=new Set([...b.ch.flatMap(c=>c.ids),...b.ov,...(b.spans||[]).map(x=>x.id)].filter(id=>I[id]&&I[id].audio));book[b.name]=[...set].reduce((a,id)=>a+est(I[id]),0);set.forEach(id=>all.add(id))}
 return AVAIL={book,bible:[...all].reduce((a,id)=>a+est(I[id]),0)}}
function hrsOf(heard,av){return `<span data-hrs="${Math.round(heard)},${Math.round(av)}">${hrsTxt(heard,av)}</span>`}
function hrsTxt(heard,av){const sp=spNow();heard/=sp;av/=sp;const H=Math.max(1,Math.round(av/3600)).toLocaleString();return heard<30?`0 of ${H} h`:heard<3600?`${Math.round(heard/60)} min of ${H} h`:`${Math.round(heard/3600).toLocaleString()} of ${H} h`}
/* how long something takes at the listener's speed (speed is set further down: before that, 1×) */
function spNow(){try{return speed>0?speed:1}catch(e){return 1}}
function atSpd(sec){const sp=spNow(),t=sec/sp;return t<3600?Math.max(1,Math.round(t/60))+' min':Math.floor(t/3600)+' h '+Math.round(t%3600/60)+' min'}
function durTxt(sec){const sp=spNow();return atSpd(sec)+(sp!==1?' at '+spdLabel():'')}

/* ---- Go to: one panel for jumping anywhere. Tap the chapter title to browse chapters and books; the search at
   the top understands books and abbreviations ("neh 4", "1 cor 13", "jn 3:16"), names (Goliath), what happens
   in a chapter ("burning bush") and sermon titles. Enter takes the first result. ---- */
const nrm=t=>(t||'').toLowerCase().replace(/[^a-z0-9]/g,'');
const plainT=t=>(t||'').replace(/⟦[pl]:[^|⟧]+\|([^⟧]+)⟧/g,'$1');
let BKA=null;function bookAliases(){if(BKA)return BKA;const m={},add=(k,b)=>{k=nrm(k);if(k&&!(k in m))m[k]=b};
 const X={Genesis:['gn','gen'],Exodus:['ex','exo','exod'],Leviticus:['lv','lev'],Numbers:['nm','num'],Deuteronomy:['dt','deut'],Joshua:['josh','jos'],Judges:['jdg','judg'],
  Nehemiah:['neh'],Esther:['est','esth'],Psalms:['psalm','ps','psa','pss'],Proverbs:['prov','prv','pr'],Ecclesiastes:['eccl','ecc','qoh'],'Song of Solomon':['songofsongs','song','sos','canticles'],
  Isaiah:['isa'],Jeremiah:['jer'],Lamentations:['lam'],Ezekiel:['ezk','ezek'],Daniel:['dan','dn'],Hosea:['hos'],Obadiah:['obad','ob'],Jonah:['jnh'],Micah:['mic'],Nahum:['nah'],
  Habakkuk:['hab'],Zephaniah:['zeph','zep'],Haggai:['hag'],Zechariah:['zech','zec'],Malachi:['mal'],Matthew:['mt','matt'],Mark:['mk','mrk'],Luke:['lk','luk'],John:['jn','jhn'],
  Acts:['ac'],Romans:['rom','ro'],Galatians:['gal'],Ephesians:['eph'],Philippians:['phil','php'],Colossians:['col'],Titus:['tit'],Philemon:['phm','philem'],Hebrews:['heb'],
  James:['jas'],Jude:['jud'],Revelation:['rev','revelations','apocalypse']};
 const NUM={Samuel:['sam','sa','sm'],Kings:['kgs','ki','kin'],Chronicles:['chr','ch','chron'],Corinthians:['cor','co'],Thessalonians:['thess','thes','th'],Timothy:['tim','ti','tm'],Peter:['pet','pe','pt'],John:['jn','jo','joh','jhn']};
 for(const b of D.books){add(b.name,b);add(b.abbr,b);(X[b.name]||[]).forEach(a=>add(a,b));const mm=b.name.match(/^([1-3]) (.+)$/);
  if(mm){for(const a of [mm[2],...(NUM[mm[2]]||[])])for(const pre of [mm[1],['','i','ii','iii'][mm[1]],['','first','second','third'][mm[1]]])add(pre+a,b)}}
 return BKA=m}
function lev(a,b){const d=Array.from({length:a.length+1},(_,i)=>[i]);for(let j=1;j<=b.length;j++)d[0][j]=j;for(let i=1;i<=a.length;i++)for(let j=1;j<=b.length;j++)d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]===b[j-1]?0:1));return d[a.length][b.length]}
function findBook(q){const k=nrm(q.replace(/^(first|1st)\s+/i,'1').replace(/^(second|2nd)\s+/i,'2').replace(/^(third|3rd)\s+/i,'3'));if(!k)return null;const A=bookAliases();if(A[k])return A[k];
 const pre=D.books.filter(b=>nrm(b.name).startsWith(k));if(pre.length===1||(pre.length&&k.length>=3))return pre[0];
 if(/^[a-z]/.test(k)&&A['1'+k])return A['1'+k];
 if(k.length>=4){let best=null,bd=9;for(const b of D.books){const n=nrm(b.name),d=lev(k,n.slice(0,Math.max(k.length,4)));if(d<bd){bd=d;best=b}}if(bd<=(k.length>=6?2:1))return best}return null}
function parsePassage(q){const m=q.trim().match(/^((?:[1-3]|i{1,3}|first|second|third|1st|2nd|3rd)?\s*[a-z][a-z\s.]*?)\.?\s*(\d+)?(?:\s*[:.]\s*(\d+)(?:\s*[-–]\s*(\d+))?)?\s*$/i);if(!m)return null;
 const b=findBook(m[1]);if(!b)return null;const max=b.ch[b.ch.length-1].c,ch=Math.min(Math.max(1,+(m[2]||1)),max);return{b,ch,v1:m[3]?+m[3]:null,v2:m[4]?+m[4]:(m[3]?+m[3]:null),whole:!m[2]}}
let SIDX=null;function searchIndex(){if(SIDX)return SIDX;const w=walk();SIDX=w.map((x,i)=>({i,x,t:(plainT(x.c.sl||'')+' '+(x.c.sm||[]).map(plainT).join(' ')).toLowerCase()}));return SIDX}
const JP={open:false,book:null,list:false};
function openJump(mode){const el=$('#jump');el.hidden=false;document.body.classList.add('jumpopen');JP.open=true;const w=walk(),x=w[camp||0];JP.book=x.b;JP.list=false;
 const q=$('#jq');q.value='';if(mode==='search')q.focus();atlas().then(()=>{if(JP.open)renderJump()}).catch(()=>{});renderJump()}
function closeJump(){$('#jump').hidden=true;document.body.classList.remove('jumpopen');JP.open=false;$('#jq').blur()}
function chDoneAt(x){return !!read[x.b.abbr+x.c.c]||x.c.ids.some(isDone)}
function jumpGo(i,o={}){closeJump();if(view==='journey'){JZ='stop';S.set('jz',JZ);jMove(i);if(o.sid){JM=false;BPM=null;PLAYSTOP=i;play(o.sid)}else if(o.hl){const x=walk()[i];if(x&&!x.c.intro&&hasNar(x.b.abbr,x.c.c))narPlay(x.b,x.c.c,o.hl.from,{load:true,full:true})}return}if(o.hl){HL=o.hl;TAB='scripture';S.set('tab',TAB)}if(o.listen){TAB='teaching';S.set('tab',TAB);if(o.lk){LK=o.lk;S.set('lk2',LK)}}go(i)}
function renderJump(){const body=$('#jbody'),q=$('#jq').value.trim(),w=walk(),cur=w[camp||0];let h='';
 if(q&&/secret|platt.*church/i.test(q))h+=`<button class="jr" id="jsc"><span class="jr-ic">▶</span><span class="jr-t"><b>Secret Church</b><span>${scGroups().length} nights · every session in order</span></span></button>`;
 if(!q){if(JP.list){h+=`<div class="jp-h">All books</div>`;let land='';for(const b of D.books){const L=(LANDS.slice().reverse().find(l=>D.books.indexOf(b)>=D.books.findIndex(bb=>bb.name===l[0]))||[,''])[1];
    if(L!==land){h+=`<div class="jp-sec">${esc(L)}</div>`;land=L}const n=b.ch.filter(c=>chDoneAt({b,c})).length,done=n===b.ch.length;
    h+=`<button class="jb${b===cur.b?' cur':''}" data-jb="${esc(b.name)}"><span>${esc(b.name)}</span><span class="jb-r">${done?'<i class="ok">✓</i>':n?Math.round(100*n/b.ch.length)+'%':b.ch.length+' ch'}</span></button>`}}
  else{const b=JP.book,n=b.ch.filter(c=>chDoneAt({b,c})).length;
   h+=`<div class="jp-bk"><div><div class="jp-bn serif">${esc(b.name)}</div><div class="jp-bs">${n} of ${b.ch.length} chapters done</div></div><button class="jp-all" id="jall">All books ›</button></div><div class="jg">`;
   {const i=w.findIndex(x=>x.b===b&&x.c.intro);h+=`<button class="jc jc-bk${i===camp?' here':''}" data-ji="${i}">The book of ${esc(b.name)}<small>Overview · summary</small></button>`}
   for(const c of b.ch){const i=w.findIndex(x=>x.b===b&&x.c===c),done=chDoneAt({b,c}),here=i===camp;h+=`<button class="jc${done?' done':''}${here?' here':''}" data-ji="${i}" aria-label="${esc(b.name)} ${c.c}${done?', done':''}">${c.c}</button>`}h+='</div>'}}
 else{const P=parsePassage(q),ql=q.toLowerCase(),words=ql.split(/\s+/).filter(x=>x.length>1);
  if(P){const i=w.findIndex(x=>x.b===P.b&&x.c.c===P.ch),x=w[i];const ref=`${P.b.name} ${P.ch}${P.v1?':'+P.v1+(P.v2&&P.v2!==P.v1?'–'+P.v2:''):''}`;
   h+=`<div class="jp-h">Go to</div><button class="jr top" data-ji="${i}"${P.v1?` data-v1="${P.v1}" data-v2="${P.v2}"`:''}><span class="jr-ic">›</span><span class="jr-t"><b>${esc(ref)}</b><small>${esc(plainT(x.c.sl||''))}</small></span></button>`;
   if(P.whole){h+=`<div class="jg small">`;for(const c of P.b.ch){const k=w.findIndex(y=>y.b===P.b&&y.c===c);h+=`<button class="jc${chDoneAt({b:P.b,c})?' done':''}${k===camp?' here':''}" data-ji="${k}">${c.c}</button>`}h+='</div>'}}
  if(!P||P.whole){
   if(ATL_D&&ql.length>=2){const hit=(n)=>{const l=n.toLowerCase();return l===ql?3:l.startsWith(ql)?2:l.split(/[\s-]/).some(p=>p.startsWith(ql))&&ql.length>=3?1:0};
    const ppl=Object.entries(ATL_D.p).map(([s,p])=>[s,p,hit(p.n)]).filter(r=>r[2]).sort((a,z)=>z[2]-a[2]||(z[1].nc||0)-(a[1].nc||0)).slice(0,4);
    const pls=Object.entries(ATL_D.l).map(([s,l])=>[s,l,hit(l.n)]).filter(r=>r[2]).sort((a,z)=>z[2]-a[2]||(z[1].nc||0)-(a[1].nc||0)).slice(0,3);
    if(ppl.length||pls.length){h+=`<div class="jp-h">People &amp; places</div>`;
     ppl.forEach(([s,p])=>h+=`<button class="jr" data-nk="p" data-ns="${s}">${medal(p,34)}<span class="jr-t"><b>${esc(p.n)}</b><small>${esc(plainT(p.who))}</small></span></button>`);
     pls.forEach(([s,l])=>h+=`<button class="jr" data-nk="l" data-ns="${s}"><span class="jr-ic pin">◉</span><span class="jr-t"><b>${esc(l.n)}</b><small>${esc(plainT(l.what))}</small></span></button>`)}}
   if(ql.length>=3&&words.length){const ch=searchIndex().filter(r=>words.every(x=>r.t.includes(x))).slice(0,6);
    if(ch.length){h+=`<div class="jp-h">In the story</div>`;ch.forEach(r=>h+=`<button class="jr" data-ji="${r.i}"><span class="jr-ic">${r.x.c.intro?'•':r.x.c.c}</span><span class="jr-t"><b>${esc(r.x.b.name)} ${r.x.c.c}</b><small>${esc(plainT(r.x.c.sl||''))}</small></span></button>`)}
    const seen=new Set(),ser=[];for(const r of searchIndex()){for(const id of stopIds(r.x)){if(seen.has(id))continue;seen.add(id);const t=(I[id].t||'').toLowerCase();if(okWho(id)&&words.every(x=>t.includes(x)))ser.push([id,r.i])}if(ser.length>=8)break}
    if(ser.length){h+=`<div class="jp-h">Sermons</div>`;ser.forEach(([id,i])=>{const it=I[id];h+=`<button class="jr" data-ji="${i}" data-sid="${id}"><span class="jr-ic play">▶</span><span class="jr-t"><b>${esc(it.t)}</b><small>${esc(teacher(it))}${it.pass?' · '+esc(shortPass(it.pass)):''}</small></span></button>`})}}}
  if(!h)h=`<div class="jp-empty">No match for “${esc(q)}”. Try a book (“Nehemiah”), a passage (“John 3:16”), a name, or a phrase from the story.</div>`}
 body.innerHTML=h;
 body.querySelectorAll('[data-jb]').forEach(b=>b.onclick=()=>{JP.book=D.books.find(x=>x.name===b.dataset.jb);JP.list=false;renderJump();body.scrollTop=0});
 const al=$('#jall');if(al)al.onclick=()=>{JP.list=true;renderJump();const c=body.querySelector('.jb.cur');if(c)c.scrollIntoView({block:'center'})};
 {const js=$('#jsc');if(js)js.onclick=()=>{closeJump();view='sc';S.set('view',view);render();window.scrollTo(0,0)}}
 body.querySelectorAll('[data-ji]').forEach(b=>b.onclick=()=>{const i=+b.dataset.ji,x=w[i];if(b.dataset.v1)return jumpGo(i,{hl:{book:x.b.name,ch:x.c.c,from:+b.dataset.v1,to:+b.dataset.v2}});
  if(b.dataset.sid){const g=listenGroups(x.b,x.c),lk=['overview','chapter','verses'].find(k=>g[k].some(y=>y.id===b.dataset.sid));return jumpGo(i,{listen:1,lk,sid:b.dataset.sid})}jumpGo(i)});
 body.querySelectorAll('[data-nk]').forEach(b=>b.onclick=()=>{closeJump();openSheet(b.dataset.nk,b.dataset.ns)})}
/* ---- medallions: one engraved emblem per role (a few people have their own); the ring's tint is the era ---- */
const MEDAL_ICON={patriarch:'M8 38 L24 14 L40 38 Z M24 14 V38 M18 38 L24 29 L30 38 M10 10 l1.5 3 M15 6 l.8 2.4 M37 7 l-1 3 M41 12 l-2 2',
 matriarch:'M12 22 H36 M14 22 V40 H34 V22 M18 22 V14 H30 V22 M24 14 V8 M20 8 H28 M14 31 H34',
 king:'M10 34 L8 16 L17 24 L24 12 L31 24 L40 16 L38 34 Z M10 39 H38 M24 12 V9',
 queen:'M12 33 L14 19 L20 26 L24 17 L28 26 L34 19 L36 33 Z M12 38 H36 M14 16 v.1 M24 14 v.1 M34 16 v.1 M18 30 h12',
 ruler:'M14 40 V22 C14 13 34 13 34 22 V40 M10 40 H38 M18 23 H30 M24 7 V13 M20 9.5 H28',
 official:'M24 9 a8 8 0 1 0 .1 0 Z M24 25 V40 M18 34 H30 M21 17 h6',
 prophet:'M24 41 C14 39 12 29 18 22 C18 28 22 28 22 24 C22 18 26 14 26 7 C32 13 36 22 34 30 C33 37 29 41 24 41 Z',
 priest:'M16 13 H32 V37 H16 Z M20 19 h2 M26 19 h2 M20 25 h2 M26 25 h2 M20 31 h2 M26 31 h2 M13 13 L24 6 L35 13',
 levite:'M16 39 H32 M18 39 C13 30 13 18 18 9 M30 39 C35 30 35 18 30 9 M18 13 H30 M21 13 V36 M24 13 V36 M27 13 V36',
 judge:'M9 31 C18 31 29 27 35 14 L40 16 C36 31 24 37 11 37 Z M11 31 V37 M35 14 L37 10',
 warrior:'M24 5 L28 11 V31 H20 V11 Z M15 31 H33 M24 31 V40 M20.5 40.5 H27.5',
 apostle:'M6 24 C14 14 30 14 38 24 C30 34 14 34 6 24 Z M38 24 L44 18 V30 Z M14 23 h.5',
 writer:'M12 10 H32 C35 10 36 12 36 14 V38 H16 C13 38 12 36 12 34 Z M12 34 C12 31 14 30 16 30 H36 M18 16 H30 M18 21 H30 M18 26 H26',
 faithful:'M14 30 C14 24 20 22 24 15 C28 22 34 24 34 30 C34 36 28 38 24 38 C20 38 14 36 14 30 Z M24 15 V9 M20 38 L18 42 H30 L28 38',
 shepherd:'M28 41 V18 C28 9 17 9 17 17 C17 22 21 23 23 21',
 craftsman:'M11 11 H29 V19 H11 Z M21 19 L33 41',
 servant:'M16 13 H30 M18 13 C18 18 14 21 14 28 C14 36 18 40 24 40 C30 40 34 36 34 28 C34 21 30 18 30 13 M34 21 C40 21 40 32 34 32',
 angel:'M24 18 C20 10 10 8 6 12 C10 14 12 18 12 22 C16 20 20 22 24 26 C28 22 32 20 36 22 C36 18 38 14 42 12 C38 8 28 10 24 18 Z M24 26 V40',
 family:'M24 41 V12 M24 31 C18 29 14 25 14 19 M24 23 C30 21 34 17 34 11 M14 17 a2 2 0 1 0 .1 0 M34 9 a2 2 0 1 0 .1 0 M24 10 a2 2 0 1 0 .1 0',
 false_god:'M18 40 H30 M20 40 V26 M28 40 V30 M20 26 L26 20 M28 30 L32 26 M19 14 a5 5 0 1 0 10 0 a5 5 0 1 0 -10 0 M30 18 L36 12',
 people:'M5 38 L13 26 L21 38 Z M17 38 L25 21 L33 38 Z M27 38 L35 28 L43 38 Z',
 christ:'M24 8 V41 M15 18 H33 M10 9 l3 3 M38 9 l-3 3 M24 3 v2.5 M7 22 h3 M38 22 h3',
 ark:'M5 28 H43 L37 38 H11 Z M14 28 V20 H34 V28 M18 20 V15 H30 V20 M22 24 h4',
 coat:'M18 8 L24 12 L30 8 L40 14 L36 22 L32 20 V40 H16 V20 L12 22 L8 14 Z M16 26 H32 M16 32 H32 M24 12 V40',
 tablets:'M10 13 C10 8 22 8 22 13 V40 H10 Z M26 13 C26 8 38 8 38 13 V40 H26 Z M13 19 H19 M13 25 H19 M13 31 H19 M29 19 H35 M29 25 H35 M29 31 H35',
 tree:'M24 41 V24 M24 29 L18 23 M24 27 L30 21 M24 24 C12 24 10 14 16 10 C18 4 30 4 32 10 C38 14 36 24 24 24 M18 41 H30',
 sheaf:'M24 40 V16 M24 22 C20 20 18 16 18 12 C22 14 24 18 24 22 M24 22 C28 20 30 16 30 12 C26 14 24 18 24 22 M24 30 C19 28 16 24 16 19 C21 21 24 25 24 30 M24 30 C29 28 32 24 32 19 C27 21 24 25 24 30 M18 40 H30',
 god:'M24 15 a9 9 0 1 0 .1 0 Z M24 4 V8 M24 40 V44 M4 24 H8 M40 24 H44 M10 10 l3 3 M35 35 l3 3 M38 10 l-3 3 M13 35 l-3 3',
 dove:'M8 22 C14 22 18 20 22 16 C24 12 28 10 32 12 L38 10 L34 15 C34 24 28 30 18 30 L10 36 L12 30 C8 28 6 25 8 22 Z M30 14 h.5',
 wave:'M24 7 C20 13 18 16 18 19 a6 6 0 0 0 12 0 C30 16 28 13 24 7 Z M8 31 C14 27 18 27 24 31 C30 35 34 35 40 31 M8 39 C14 35 18 35 24 39 C30 43 34 43 40 39'};
const ERA_C=(()=>{const a=[217,180,90],b=[59,85,120];return Array.from({length:14},(_,i)=>{const t=i/13;return`rgb(${a.map((v,k)=>Math.round(v+(b[k]-v)*t)).join(',')})`})})();
function medal(p,size){if(!p)return'';const d=MEDAL_ICON[p.ic]||MEDAL_ICON.family,c=ERA_C[Math.max(0,Math.min(13,p.era||0))];
 return `<span class="medal" style="width:${size}px;height:${size}px;--ring:${c}"><svg viewBox="0 0 48 48" width="${Math.round(size*.58)}" height="${Math.round(size*.58)}" aria-hidden="true"><path d="${d}" fill="none" stroke="#1b2440" stroke-width="${size<30?2.4:1.8}" stroke-linecap="round" stroke-linejoin="round"/></svg></span>`}
function famRow(k,label,list){if(!list||!list.length)return'';return `<div class="k">${label}</div><div>${list.map(x=>x.s?`<button class="chip" data-nk="p" data-ns="${x.s}">${ATL_D?medal(ATL_D.p[x.s],22):''}${esc(x.n)}</button>`:`<span class="chip">${esc(x.n)}</span>`).join('')}</div>`}
function miniMap(A,x,y,sl){const nm=sl&&A.l[sl]?A.l[sl].n:'';return mapSVG(A,x,y,46,[{x,y,n:nm,main:1}],{skip:sl})}
/* a close map: territory names, waters, a nearby town or two, the marked places, and a tiny whole-world inset.
   marks: [{x,y,n,sl?,main?}] — main = the gold "here" dot; others = ink dots (tappable when sl is set); trail = dotted road */
function mapSVG(A,x,y,w,marks,opts={}){const M=A.map,T=A.trip;if(!M)return'';
 const W=340,H=200,h=w*H/W,u=w/W,vx=x-w/2,vy=y-h/2,leg=T?standing(A).leg:0,lab=[],dots=[];
 const inV=(px,py)=>px>vx&&px<vx+w&&py>vy&&py<vy+h,rc='stroke-linecap="round" stroke-linejoin="round"';
 let o=`<rect x="${vx-60}" y="${vy-60}" width="${w+120}" height="${h+120}" fill="#d6e4e3"/><path d="${M.land}" fill="none" stroke="#e8f0ee" stroke-width="${7*u}" ${rc}/><path d="${M.land}" fill="#f4ecda" stroke="#c6b186" stroke-width="${.9*u}" ${rc}/>`+
  M.lakes.map(l=>`<path d="${l.d}" fill="#c8dad9"/>`).join('')+M.rivers.map(r=>`<path d="${r.d}" fill="none" stroke="#93b2b8" stroke-width="${1.3*u}" ${rc}/>`).join('');
 if(opts.trail&&opts.trail.length>1)o+=`<path d="${curve(opts.trail.map(p=>[p.x,p.y]))}" fill="none" stroke="rgba(176,138,52,.8)" stroke-width="${3*u}" stroke-dasharray="0 ${7*u}" ${rc}/>`;
 marks.forEach(m=>dots.push([m.x,m.y,m.main?7:5]));
 if(T){const skip=new Set([opts.skip,...marks.map(m=>m.sl)]);T.anchors.filter(([s,ax,ay])=>!skip.has(s)&&inV(ax,ay)&&marks.every(m=>Math.hypot(ax-m.x,ay-m.y)>1.2)).sort((a,b)=>Math.hypot(a[1]-x,a[2]-y)-Math.hypot(b[1]-x,b[2]-y)).slice(0,marks.length>2?1:2)
   .forEach(([s,ax,ay,n])=>{o+=`<circle cx="${ax}" cy="${ay}" r="${2.4*u}" fill="#6b7186" stroke="#fff" stroke-width="${u}"/>`;dots.push([ax,ay,4]);lab.push({x:ax,y:ay,t:n,fs:10.5,col:'#5a6178',pri:2,r:4})});
  T.fine.forEach(([n,fx,fy,legs])=>{if(legs.includes(leg)&&inV(fx,fy))lab.push({x:fx,y:fy,t:n.toUpperCase(),fs:9.5,col:'rgba(122,98,50,.62)',pri:3,ctr:1,up:1})});
  T.reg.forEach(([n,rx,ry,legs])=>{if((!legs||legs.includes(leg))&&inV(rx,ry))lab.push({x:rx,y:ry,t:n.toUpperCase(),fs:10.5,col:'rgba(122,98,50,.5)',pri:4,ctr:1,up:1})});
  T.waters.forEach(([n,wx,wy])=>{if(inV(wx,wy))lab.push({x:wx,y:wy,t:n,fs:10,col:'rgba(64,98,108,.7)',it:1,pri:5,ctr:1})})}
 marks.forEach(m=>{const tap=m.sl?` data-nk="l" data-ns="${m.sl}" style="cursor:pointer"`:'';
  o+=m.main?`<circle cx="${m.x}" cy="${m.y}" r="${9*u}" fill="rgba(201,162,74,.28)"/><circle cx="${m.x}" cy="${m.y}" r="${3.8*u}" fill="#a8812a" stroke="#fff" stroke-width="${1.4*u}"${tap}/>`
   :`<circle cx="${m.x}" cy="${m.y}" r="${3.4*u}" fill="${m.hollow?'#fffaf0':'#1b2440'}" stroke="${m.hollow?'#c9a24a':'#fff'}" stroke-width="${1.3*u}"${tap}/>`;
  if(m.n)lab.push({x:m.x,y:m.y,t:m.n,fs:m.main?12.5:12,col:m.main?'#3b2f12':'#1b2440',b:1,pri:m.main?0:1,r:m.main?7:5,sl:m.sl})});
 const boxes=dots.map(([dx,dy,r])=>[dx-r*u,dy-r*u,dx+r*u,dy+r*u]),hit=b=>boxes.some(q=>b[0]<q[2]&&q[0]<b[2]&&b[1]<q[3]&&q[1]<b[3]),fits=b=>b[0]>=vx&&b[2]<=vx+w&&b[1]>=vy&&b[3]<=vy+h;
 lab.sort((a,b)=>a.pri-b.pri).forEach(l=>{const fs=l.fs*u,tw=l.t.length*fs*(l.up?.86:.55),th=fs*1.2,g=(l.r||0)*u+3*u;
  const c=l.ctr?[[l.x-tw/2,l.y-th/2]]:[[l.x+g,l.y-th/2],[l.x-g-tw,l.y-th/2],[l.x-tw/2,l.y-g-th],[l.x-tw/2,l.y+g*.8]];let ok=null;
  for(const[cx,cy]of c){const b=[cx,cy,cx+tw,cy+th];if(fits(b)&&!hit(b)){ok=b;break}}if(!ok)return;boxes.push(ok);
  o+=`<text x="${ok[0]}" y="${ok[1]+th*.8}" font-size="${fs}" font-family='${SERIF}' fill="${l.col}" ${l.b?'font-weight="700"':''} ${l.it?'font-style="italic"':''} ${l.up?`letter-spacing="${fs*.28}"`:''} ${l.ctr?'':`paint-order="stroke" stroke="#f7f0e1" stroke-width="${2.6*u}" stroke-linejoin="round"`}${l.sl?` data-nk="l" data-ns="${l.sl}" style="cursor:pointer"`:''}>${esc(l.t)}</text>`});
 const V=M.view,iu=V[2]/96;
 const inset=`<svg class="inset" viewBox="${V.join(' ')}" aria-hidden="true"><rect x="0" y="0" width="${V[2]}" height="${V[3]}" fill="#d6e4e3"/><path d="${M.land}" fill="#f1e8d4"/><rect x="${vx}" y="${vy}" width="${w}" height="${h}" fill="rgba(201,162,74,.25)" stroke="#a8812a" stroke-width="${1.6*iu}"/><circle cx="${x}" cy="${y}" r="${2.2*iu}" fill="#a8812a"/></svg>`;
 return `<div class="mini"${opts.notap?'':' role="button" aria-label="Open the map"'}><svg class="mm" viewBox="${vx} ${vy} ${w} ${h}">${o}</svg>${inset}</div>`}
function storyList(items){ /* key moments as a timeline, with where the reader stands */
 const order=D.books.map(b=>b.name),pos=(b,c)=>order.indexOf(b)*1000+c,w=walk()[camp||0],me=pos(w.b.name,w.c.c);let placed=false,h='';
 for(const x of items){const m=x.match(/\(([1-3]?\s?[A-Z][A-Za-z]+(?:\s(?:of\s)?[A-Z][a-z]+)?)\s(\d+)/);const bk=m&&(m[1]==='Psalm'?'Psalms':m[1]==='Song of Songs'?'Song of Solomon':m[1]),p=m&&order.includes(bk)?pos(bk,+m[2]):null;
  if(!placed&&p!=null&&p>me){h+=`<li class="here">You are here · ${esc(w.b.name)} ${w.c.c}</li>`;placed=true}
  h+=`<li class="${p==null?'':p<me?'past':p===me?'now':''}">${refLinks(x)}</li>`}
 if(!placed&&items.length)h+=`<li class="here">You are here · ${esc(w.b.name)} ${w.c.c}</li>`;
 return `<ul class="story">${h}</ul>`}
function sheetHTML(A,k,sl){
 if(k==='p'){const p=A.p[sl];if(!p)return '<p class="who">No profile yet.</p>';
  const f=p.fam||{};const fam=famRow('father','Father',f.father)+famRow('mother','Mother',f.mother)+famRow('spouses',(f.spouses||[]).length>1?'Spouses':'Spouse',f.spouses)+famRow('siblings','Siblings',f.siblings)+famRow('children','Children',f.children);
  const eraT0=!['god','dove','christ'].includes(p.ic)&&A.trip&&A.trip.legs[p.era]?A.trip.legs[p.era].t:'',eraT=/^(Abraham|Jacob|Joseph|Jesus)$/.test(eraT0)?'Age of '+eraT0:eraT0;
  return `<div class="ph">${medal(p,76)}<div class="ph-t"><h3>${esc(p.n)}</h3>${p.mean?`<div class="mean">${/^(possibly|meaning unknown)/i.test(p.mean)?esc(p.mean):'“'+esc(p.mean)+'”'}</div>`:''}${p.role||eraT?`<div class="ph-r">${esc([p.role,eraT].filter(Boolean).join(' · '))}</div>`:''}</div></div>${p.why?`<div class="why">${refLinks(p.why)}</div>`:''}<p class="who">${rich(p.who)}</p>${p.key&&p.key.length?`<div class="sec">Their story</div>${storyList(p.key)}`:''}${fam?`<div class="sec">Family</div><div class="fam">${fam}</div>`:''}<div class="meta">${p.nc?`Appears in ${p.nc===1?'1 chapter':p.nc+' chapters'}`:''}${p.first?` · ${refLinksPlain(p.first)}${p.last&&p.last!==p.first?' → '+refLinksPlain(p.last):''}`:''}</div>`}
 const l=A.l[sl];if(!l)return '<p class="who">No profile yet.</p>';
 return `<h3>${esc(l.n)}</h3>${l.mean?`<div class="mean">${/^(possibly|meaning unknown)/i.test(l.mean)?esc(l.mean):'“'+esc(l.mean)+'”'}</div>`:''}${l.why?`<div class="why">${refLinks(l.why)}</div>`:''}${l.in?`<div class="within">${l.in.map(esc).join('<span> · </span>')}</div>`:''}${l.x!=null?miniMap(A,l.x,l.y,sl):''}<p class="who">${rich(l.what)}</p>${l.key&&l.key.length?`<div class="sec">What happens here</div>${storyList(l.key)}`:''}${l.today?`<div class="sec">Today</div><p class="who" style="margin:0">${esc(l.today)}</p>`:''}${l.x!=null?`<button class="go open" data-openmap="${sl}">Open the map ›</button>`:''}<div class="meta">${l.nc?`Named in ${l.nc===1?'1 chapter':l.nc+' chapters'}`:''}${l.first?` · ${refLinksPlain(l.first)}${l.last&&l.last!==l.first?' → '+refLinksPlain(l.last):''}`:''}</div>`}
function refLinksPlain(r){const m=r.match(/^(.+) (\d+)$/);return m?`<button class="go" data-gob="${m[1]}" data-goc="${m[2]}">${esc(r)}</button>`:esc(r)}
function openSheet(k,sl,push=true){atlas().then(A=>{if(push)SHEET.push([k,sl]);const sh=$('#sheet');
  $('#shkind').textContent=k==='p'?((A.p[sl]||{}).lab||'Person'):'Place';$('#shback').hidden=SHEET.length<2;$('#shbody').innerHTML=sheetHTML(A,k,sl);
  $('#sheetbg').hidden=false;sh.hidden=false;sh.scrollTop=0;sh.style.transform='';wireSheet()}).catch(()=>{})}
function closeSheet(){SHEET.length=0;$('#sheet').hidden=true;$('#sheetbg').hidden=true}
function wireSheet(){$('#shbody').querySelectorAll('[data-nk]').forEach(b=>b.onclick=()=>openSheet(b.dataset.nk,b.dataset.ns));
 $('#shbody').querySelectorAll('[data-gob]').forEach(b=>b.onclick=()=>{const i=walk().findIndex(x=>x.b.name===b.dataset.gob&&x.c.c===+b.dataset.goc);if(i>=0){closeSheet();closeMap();go(i)}});
 $('#shbody').querySelectorAll('[data-openmap]').forEach(b=>b.onclick=()=>openMap(b.dataset.openmap));
 $('#shbody').querySelectorAll('.mini').forEach(m=>m.onclick=()=>openMap(SHEET[SHEET.length-1][1]))}
(()=>{$('#shx').onclick=closeSheet;$('#sheetbg').onclick=closeSheet;$('#shback').onclick=()=>{SHEET.pop();const t=SHEET[SHEET.length-1];if(t)openSheet(t[0],t[1],false)};
 const sh=$('#sheet');let y0=null,dy=0;sh.addEventListener('touchstart',e=>{if(sh.scrollTop>0){y0=null;return}y0=e.touches[0].clientY;dy=0},{passive:true});
 sh.addEventListener('touchmove',e=>{if(y0===null)return;dy=e.touches[0].clientY-y0;if(dy>0){e.preventDefault();sh.style.transform=`translateY(${dy}px)`}},{passive:false});
 sh.addEventListener('touchend',()=>{if(y0===null)return;if(dy>90)closeSheet();else sh.style.transform='';y0=null});
 addEventListener('keydown',e=>{if(e.key==='Escape'){closeSheet();closeMap()}})})();
/* ---- the map: the Bible as one road in 14 legs; your leg walked in gold, the road ahead still dotted ---- */
let MV=null;
const SERIF='"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif';
function legOf(T,b,c){let L=0;for(const[s,i]of(T.bl[b]||[[1,0]]))if(c>=s)L=i;return L}
function bkey(b,c){return D.books.findIndex(x=>x.name===b)*1000+c}
function standing(A){const T=A.trip,W=walk(),w=W[Math.max(0,Math.min(W.length-1,jpIdx()))],b=w.b.name,c=w.c.c||1,leg=legOf(T,b,c),L=T.legs[leg];
 const places=(A.here[b+' '+c]||[]).map(s=>[s,A.l[s]]).filter(x=>x[1]&&x[1].x!=null);
 const r={leg,b,c,idx:-1,mark:null,line:'',places},note=T.notes[b],me=bkey(b,c);L.stops.forEach((s,i)=>{if(!s.np&&bkey(s.b,s.c)<=me)r.idx=i});
 if(note){if(note[0])r.mark={x:note[0][0],y:note[0][1],n:note[0][2]};r.line=note[1];return r}
 if(L.stops.some(s=>s.b===b&&!s.np)||T.follow.includes(b)){if(r.idx>=0){const s=L.stops[r.idx];r.mark={x:s.x,y:s.y,n:s.n};r.line=s.beat}else{const n=L.stops.find(s=>!s.np&&s.beat);if(n)r.line='Up next: '+n.beat}return r}
 r.ch=1;
 if(places.length)r.line='In this chapter: '+places.slice(0,3).map(([,l])=>l.n).join(', ');
 return r}
function curve(p){p=p.filter((q,i)=>!i||q[0]!==p[i-1][0]||q[1]!==p[i-1][1]);if(p.length<2)return'';
 if(p.length===2){const[a,b]=p,dx=b[0]-a[0],dy=b[1]-a[1];return`M${a} Q${(a[0]+b[0])/2-dy*.16},${(a[1]+b[1])/2+dx*.16} ${b}`}
 let d=`M${p[0]}`;for(let i=0;i<p.length-1;i++){const p0=p[i-1]||p[i],p1=p[i],p2=p[i+1],p3=p[i+2]||p2;
  d+=` C${p1[0]+(p2[0]-p0[0])/6},${p1[1]+(p2[1]-p0[1])/6} ${p2[0]-(p3[0]-p1[0])/6},${p2[1]-(p3[1]-p1[1])/6} ${p2}`}return d}
function trails(L){const g={};L.stops.forEach((s,i)=>{if(s.t==null)return;(g[s.t]=g[s.t]||[]).push([s,i])});return Object.values(g)}
function drawMap(A){const M=A.map,T=A.trip,st=standing(A),cur=st.leg,whole=MV.leg<0,hl=whole?cur:MV.leg,el=$('#mapsvg'),px=MV.w/(el.clientWidth||390),gold='#c9a24a';
 const out=[],labels=[],dots=[],P=a=>a.map(([s])=>[s.x,s.y]),rc=`stroke-linecap="round" stroke-linejoin="round" fill="none"`;
 out.push(`<rect x="-3000" y="-3000" width="7000" height="7000" fill="#d6e4e3"/>`,`<path d="${M.land}" fill="none" stroke="#e8f0ee" stroke-width="${10*px}" stroke-linejoin="round"/>`,
  `<path d="${M.land}" fill="#f4ecda" stroke="#c6b186" stroke-width="${1.1*px}" stroke-linejoin="round"/>`,...M.lakes.map(l=>`<path d="${l.d}" fill="#c8dad9"/>`),
  ...M.rivers.map(r=>`<path d="${r.d}" ${rc} stroke="#93b2b8" stroke-width="${1.4*px}"/>`));
 {const[,,VW,VH]=M.view,e=16,pc='#efe7d3';out.push(`<defs>${['T:0,0,0,1','B:0,1,0,0','L:0,0,1,0','R:1,0,0,0'].map(g=>{const[n,v]=g.split(':'),[a,b,c2,d]=v.split(',');return`<linearGradient id="pf${n}" x1="${a}" y1="${b}" x2="${c2}" y2="${d}"><stop offset="0" stop-color="${pc}"/><stop offset="1" stop-color="${pc}" stop-opacity="0"/></linearGradient>`}).join('')}</defs>`,
  `<path fill-rule="evenodd" fill="${pc}" d="M-3000,-3000H4000V4000H-3000Z M0,0V${VH}H${VW}V0Z"/>`,`<rect x="0" y="0" width="${VW}" height="${e}" fill="url(#pfT)"/>`,`<rect x="0" y="${VH-e}" width="${VW}" height="${e}" fill="url(#pfB)"/>`,
  `<rect x="0" y="0" width="${e}" height="${VH}" fill="url(#pfL)"/>`,`<rect x="${VW-e}" y="0" width="${e}" height="${VH}" fill="url(#pfR)"/>`)}
 T.legs.forEach((L,i)=>{if(i===hl||i>cur||(!whole&&i!==hl-1))return;trails(L).forEach(t=>out.push(`<path d="${curve(P(t))}" ${rc} stroke="rgba(201,162,74,.42)" stroke-width="${2*px}"/>`))});
 const L=T.legs[hl],now=hl===cur,ahead=hl>cur,idx=now?st.idx:(ahead?-1:1e9),an=MV.anim?' class="draw" pathLength="1"':'';
 trails(L).forEach(t=>{const w=t.filter(([,i])=>i<=idx),rest=w.length?t.slice(w.length-1):t;
  if(w.length>1){const d=curve(P(w));out.push(`<path d="${d}"${an} ${rc} stroke="#fffaf0" stroke-opacity=".95" stroke-width="${8*px}"/>`,`<path d="${d}"${an} ${rc} stroke="${gold}" stroke-width="${3.6*px}"/>`)}
  if(rest.length>1)out.push(`<path d="${curve(P(rest))}"${MV.anim?' class="fade"':''} ${rc} stroke="${ahead?'rgba(27,36,64,.4)':'rgba(176,138,52,.8)'}" stroke-width="${3.4*px}" stroke-dasharray="0 ${7.5*px}"/>`)});
 const seen=new Set();L.stops.forEach((s,i)=>{const k=s.x+','+s.y;if(seen.has(k))return;seen.add(k);const done=!ahead&&(i<=idx&&!s.np||!now);
  out.push(`<circle cx="${s.x}" cy="${s.y}" r="${4.6*px}" fill="${done?gold:'#fffaf0'}" stroke="${done?'#fff':gold}" stroke-width="${1.6*px}"${s.sl?` data-pl="${s.sl}"`:''}/>`);dots.push([s.x,s.y,6]);
  if(!whole)labels.push({x:s.x,y:s.y,t:s.n,fs:14,col:done?'#4a3b17':'#7d6c49',pri:2,r:6,sl:s.sl})});
 if(!whole&&now)st.places.forEach(([sl,l])=>{if(dots.some(([x,y])=>Math.hypot(x-l.x,y-l.y)<2.5*px))return;
  out.push(`<circle cx="${l.x}" cy="${l.y}" r="${3.2*px}" fill="#1b2440" stroke="#fff" stroke-width="${1.2*px}" data-pl="${sl}"/>`);dots.push([l.x,l.y,5]);
  labels.push({x:l.x,y:l.y,t:l.n,fs:12.5,col:'#1b2440',it:1,pri:3,r:5,sl})});
 const f=MV.focus&&A.l[MV.focus];if(f&&f.x!=null){out.push(`<circle cx="${f.x}" cy="${f.y}" r="${6*px}" fill="#b23a2a" stroke="#fff" stroke-width="${2*px}" data-pl="${MV.focus}"/>`);dots.push([f.x,f.y,8]);
  labels.push({x:f.x,y:f.y,t:f.n,fs:15,col:'#1b2440',b:1,pri:1,r:8,sl:MV.focus})}
 if(st.mark&&(now||whole)){const m=st.mark;for(let i=labels.length-1;i>=0;i--)if(Math.hypot(labels[i].x-m.x,labels[i].y-m.y)<.01&&labels[i].pri===2)labels.splice(i,1);
  out.push(`<circle class="pulse" cx="${m.x}" cy="${m.y}" r="${15*px}" fill="rgba(201,162,74,.28)"/>`,`<circle cx="${m.x}" cy="${m.y}" r="${6.5*px}" fill="${gold}" stroke="#fff" stroke-width="${2.6*px}"/>`);dots.push([m.x,m.y,9]);
  labels.push({x:m.x,y:m.y,t:m.n,fs:15,col:'#3b2f12',b:1,pri:0,r:10})}
 T.reg.forEach(([n,x,y,legs])=>{if(!legs||legs.includes(hl))labels.push({x,y,t:n.toUpperCase(),fs:11.5,col:'rgba(122,98,50,.5)',pri:5,ctr:1,up:1})});
 T.seas.forEach(([n,x,y])=>labels.push({x,y,t:n,fs:13,col:'rgba(64,98,108,.55)',it:1,pri:6,ctr:1}));
 if(MV.w<70){T.fine.forEach(([n,x,y,legs])=>{if(legs.includes(hl))labels.push({x,y,t:n.toUpperCase(),fs:10.5,col:'rgba(122,98,50,.55)',pri:4,ctr:1,up:1})});T.waters.forEach(([n,x,y])=>labels.push({x,y,t:n,fs:12,col:'rgba(64,98,108,.6)',it:1,pri:6,ctr:1}))}
 const boxes=dots.map(([x,y,r])=>[x-r*px,y-r*px,x+r*px,y+r*px]),hit=b=>boxes.some(o=>b[0]<o[2]&&o[0]<b[2]&&b[1]<o[3]&&o[1]<b[3]);
 labels.sort((a,b)=>a.pri-b.pri).forEach(l=>{if(l.x<MV.x||l.x>MV.x+MV.w||l.y<MV.y||l.y>MV.y+MV.h)return;const inV=b=>b[0]>=MV.x&&b[2]<=MV.x+MV.w&&b[1]>=MV.y&&b[3]<=MV.y+MV.h;
  const fs=l.fs*px,w=l.t.length*fs*(l.up?.86:.54),h=fs*1.2,g=(l.r||0)*px+3*px;
  const c=l.ctr?[[l.x-w/2,l.y-h/2]]:[[l.x+g,l.y-h/2],[l.x-g-w,l.y-h/2],[l.x-w/2,l.y-g-h],[l.x-w/2,l.y+g*.8]];
  let ok=null;for(const[x,y]of c){const b=[x,y,x+w,y+h];if(inV(b)&&!hit(b)){ok=b;break}}if(!ok&&l.pri===0)for(const[x,y]of c){const b=[x,y,x+w,y+h];if(inV(b)){ok=b;break}}if(!ok&&l.pri===0)ok=[c[0][0],c[0][1],c[0][0]+w,c[0][1]+h];if(!ok)return;boxes.push(ok);
  const halo=l.ctr?'':`paint-order="stroke" stroke="#f7f0e1" stroke-width="${3.2*px}" stroke-linejoin="round"`;
  out.push(`<text x="${ok[0]}" y="${ok[1]+h*.8}" font-size="${fs}" font-family='${SERIF}' fill="${l.col}" ${l.b?'font-weight="700"':''} ${l.it?'font-style="italic"':''} ${l.up?`letter-spacing="${fs*.28}"`:''} ${halo}${l.sl?` data-pl="${l.sl}"`:''}>${esc(l.t)}</text>`)});
 el.setAttribute('viewBox',`${MV.x} ${MV.y} ${MV.w} ${MV.h}`);el.innerHTML=out.join('');MV.anim=false}
function mvCard(A){const T=A.trip,st=standing(A),cur=st.leg,i=MV.leg,L=T.legs[i<0?cur:i];
 const nm=st.mark&&!st.line.toLowerCase().includes(st.mark.n.toLowerCase())?st.mark.n:'',here=`<div class="mv-here${st.mark?'':' ink'}"><i></i><div>${nm?`<b>${esc(nm)}</b>${st.line?' · ':''}`:''}${esc(st.line)}<span class="mv-ref">${st.line||st.mark?' · ':''}${esc(st.b)} ${st.c}</span></div></div>`;
 $('#mvcard').innerHTML=i<0?`<div class="mv-k">The whole story</div><div class="mv-t">Genesis to Revelation</div><div class="mv-s">One road in 14 legs. You are on leg ${cur+1}: ${esc(T.legs[cur].t)}.</div>${here}`:
  `<div class="mv-k">Leg ${i+1} of 14 · ${i===cur?'You are here':i<cur?'Walked':'The road ahead'}</div><div class="mv-t">${esc(L.t)}</div><div class="mv-s">${esc(L.s)}</div>${i===cur?here:''}`}
function mvStrip(A,smooth){const T=A.trip,cur=standing(A).leg,box=$('#mvlegs');
 box.innerHTML=`<button data-leg="-1" class="all${MV.leg<0?' sel':''}">Whole story</button>`+T.legs.map((L,i)=>`<button data-leg="${i}" class="${i<cur?'walked':i===cur?'now':'ahead'}${i===MV.leg?' sel':''}"><span>${i+1}</span>${esc(L.t)}</button>`).join('');
 box.querySelectorAll('button').forEach(b=>b.onclick=()=>pickLeg(A,+b.dataset.leg));
 const on=box.querySelector('.sel');if(on)box.scrollTo({left:on.offsetLeft-box.clientWidth/2+on.offsetWidth/2,behavior:smooth?'smooth':'auto'})}
function boxView(x0,y0,x1,y1,minW,pad){const el=$('#mapsvg'),W=el.clientWidth||390,H=el.clientHeight||700,top=$('#mapv .mv-top').offsetHeight||64,bot=$('#mvpanel').offsetHeight||230;
 const aw=W-(pad==null?150:pad),ah=Math.max(140,H-top-bot-40),s=Math.max((x1-x0)/aw,(y1-y0)/ah,(minW||40)/W),cx=(x0+x1)/2,cy=(y0+y1)/2;return{x:cx-W/2*s,y:cy-(top+20+ah/2)*s,w:W*s,h:H*s}}
function bbox(pts,minW,pad){const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);return boxView(Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys),minW,pad)}
function legBox(A,i){const st=standing(A),p=A.trip.legs[i].stops.map(s=>[s.x,s.y]);if(i===st.leg){if(st.mark)p.push([st.mark.x,st.mark.y]);st.places.slice(0,4).forEach(([,l])=>p.push([l.x,l.y]))}return bbox(p,26)}
function wholeBox(A){return bbox(A.trip.legs.flatMap(L=>L.stops.map(s=>[s.x,s.y])),100,24)}
function fly(A,t){const el=$('#mapsvg'),f={x:MV.x,y:MV.y,w:MV.w,h:MV.h},t0=performance.now(),dur=matchMedia('(prefers-reduced-motion: reduce)').matches?0:700;cancelAnimationFrame(MV.raf);
 const step=now=>{const k=dur?Math.min(1,(now-t0)/dur):1,e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
  MV.w=Math.exp(Math.log(f.w)+(Math.log(t.w)-Math.log(f.w))*e);MV.h=MV.w*t.h/t.w;
  const cx=f.x+f.w/2+(t.x+t.w/2-f.x-f.w/2)*e,cy=f.y+f.h/2+(t.y+t.h/2-f.y-f.h/2)*e;MV.x=cx-MV.w/2;MV.y=cy-MV.h/2;el.setAttribute('viewBox',`${MV.x} ${MV.y} ${MV.w} ${MV.h}`);
  if(k<1)MV.raf=requestAnimationFrame(step);else{Object.assign(MV,t);MV.anim=true;drawMap(A)}};MV.raf=requestAnimationFrame(step)}
function pickLeg(A,i){MV.leg=i;MV.focus=null;$('#mvtitle').textContent='Your journey';mvStrip(A,true);mvCard(A);fly(A,i<0?wholeBox(A):legBox(A,i))}
function openMap(focus){atlas().then(A=>{if(!A.map||!A.trip)return;if(SHEET.length)closeSheet();$('#mapv').hidden=false;document.body.classList.add('mapopen');const st=standing(A);
  const f=focus&&A.l[focus]&&A.l[focus].x!=null?A.l[focus]:null;MV={x:0,y:0,w:100,h:100,leg:st.leg,focus:f?focus:null,anim:true};
  $('#mvtitle').textContent=f?f.n:'Your journey';mvStrip(A);mvCard(A);Object.assign(MV,f?boxView(f.x-10,f.y-10,f.x+10,f.y+10,60):legBox(A,st.leg));drawMap(A)})}
function closeMap(){$('#mapv').hidden=true;document.body.classList.remove('mapopen')}
(()=>{const el=$('#mapsvg'),P=new Map();let start=null,moved=0;
 const zoom=(f,cx,cy)=>{atlas().then(A=>{const r=el.getBoundingClientRect(),s=MV.w/r.width,mx=MV.x+(cx-r.left)*s,my=MV.y+(cy-r.top)*s,nw=Math.min(420,Math.max(14,MV.w*f)),k=nw/MV.w;MV.x=mx-(mx-MV.x)*k;MV.y=my-(my-MV.y)*k;MV.w=nw;MV.h*=k;drawMap(A)})};
 el.addEventListener('pointerdown',e=>{el.setPointerCapture(e.pointerId);P.set(e.pointerId,[e.clientX,e.clientY]);if(P.size===1)moved=0;cancelAnimationFrame(MV.raf);start={x:MV.x,y:MV.y,pts:new Map(P),w:MV.w,h:MV.h}});
 el.addEventListener('pointermove',e=>{if(!P.has(e.pointerId)||!start)return;P.set(e.pointerId,[e.clientX,e.clientY]);const r=el.getBoundingClientRect(),s=start.w/r.width;
  if(P.size===1){const[a]=[...start.pts.values()],[b]=[...P.values()];moved=Math.max(moved,Math.hypot(b[0]-a[0],b[1]-a[1]));MV.x=start.x-(b[0]-a[0])*s;MV.y=start.y-(b[1]-a[1])*s;el.setAttribute('viewBox',`${MV.x} ${MV.y} ${MV.w} ${MV.h}`)}
  else if(P.size===2&&start.pts.size===2){moved=99;const[a1,a2]=[...start.pts.values()],[b1,b2]=[...P.values()];const d0=Math.hypot(a1[0]-a2[0],a1[1]-a2[1]),d1=Math.hypot(b1[0]-b2[0],b1[1]-b2[1]);if(d0>10&&d1>10){MV.w=Math.min(420,Math.max(14,start.w*d0/d1));MV.h=start.h*MV.w/start.w;const cx=(a1[0]+a2[0])/2,cy=(a1[1]+a2[1])/2,mx=start.x+(cx-r.left)*s,my=start.y+(cy-r.top)*s,k=MV.w/start.w,nx=(b1[0]+b2[0])/2,ny=(b1[1]+b2[1])/2;MV.x=mx-(nx-r.left)*s*k;MV.y=my-(ny-r.top)*s*k;el.setAttribute('viewBox',`${MV.x} ${MV.y} ${MV.w} ${MV.h}`)}}});
 const end=e=>{P.delete(e.pointerId);if(P.size){start={x:MV.x,y:MV.y,pts:new Map(P),w:MV.w,h:MV.h};return}start=null;
  if(moved<8)return;atlas().then(A=>drawMap(A))};
 el.addEventListener('click',e=>{if(moved>=8)return;const t=document.elementFromPoint(e.clientX,e.clientY),g=t&&t.closest&&t.closest('[data-pl]');if(g)openSheet('l',g.dataset.pl)});
 el.addEventListener('pointerup',end);el.addEventListener('pointercancel',end);
 el.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.15:1/1.15,e.clientX,e.clientY)},{passive:false});
 $('#mvx').onclick=closeMap;$('#mapbtn').onclick=()=>openMap(null)})();
(()=>{$('#srch').onclick=()=>openJump('search');$('#jx').onclick=closeJump;const q=$('#jq');q.oninput=()=>renderJump();
 q.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();const f=$('#jbody').querySelector('.jr,[data-ji]');if(f)f.click()}else if(e.key==='Escape')closeJump()}})();
const BIBLE={};let HL=null;  /* HL = {book, ch, from, to}: verses to highlight */
function loadBook(book){return BIBLE[book]||(BIBLE[book]=fetch('bible/'+encodeURIComponent(book)+'.json').then(r=>{if(!r.ok)throw 0;return r.json()}).catch(e=>{delete BIBLE[book];throw e}))}
function shortPass(p){return p.split(';')[0].trim()}
/* a passage inside the stop's book -> {sc,sv,ec,ev} (start/end chapter and verse); null if it names more than this book */
function prange(pass,book){if(!pass)return null;const bk=new RegExp('^'+book.replace(/^Psalms$/,'Psalms?').replace(/ /g,'\\s+')+'\\s+\\d','i');let cur=null,seg=null;
 /* a harmony passage names several books ("Luke 8:22-25; Mark 4:35-41; Matthew 8:18, 23-27"): take this book's part */
 for(let part of pass.replace(/[–—]/g,'-').split(';')){part=part.trim();const m=part.match(/^((?:[1-3]\s+)?[A-Za-z]+(?:\s+of\s+[A-Za-z]+)?)\s+(\d.*)$/);
  if(m){cur=m[1];if(bk.test(part)){seg=m[2];break}}else if(cur&&/^\d/.test(part)&&bk.test(cur+' '+part)){seg=part;break}}
 /* one passage with a spelling the book test misses ("I Samuel 16:1-13", "Matt. 11:11", "MT 17:22", "1Kings 18"): it is this book's, since it was placed here */
 if(seg==null&&!pass.includes(';')){const m=pass.replace(/[–—]/g,'-').match(/^\s*(?:[1-3]|I{1,3}|First|Second|Third)?\s*[A-Za-z][A-Za-z.]*(?:\s+of\s+[A-Za-z]+)?\.?\s*(\d.*)$/);if(m)seg=m[1]}
 if(seg==null)return null;const p=seg.split(',')[0].replace(/\s+and\s+/gi,'-').replace(/\s/g,'');let m;
 if(m=p.match(/^(\d+):(\d+)-(\d+):(\d+)/))return{sc:+m[1],sv:+m[2],ec:+m[3],ev:+m[4]};
 if(m=p.match(/^(\d+):(\d+)-(\d+)/))return{sc:+m[1],sv:+m[2],ec:+m[1],ev:+m[3]};
 if(m=p.match(/^(\d+)-(\d+):(\d+)/))return{sc:+m[1],sv:1,ec:+m[2],ev:+m[3]};
 if(m=p.match(/^(\d+):(\d+)/))return{sc:+m[1],sv:+m[2],ec:+m[1],ev:+m[2]};
 if(m=p.match(/^(\d+)-(\d+)/))return{sc:+m[1],sv:1,ec:+m[2],ev:999};
 if(m=p.match(/^(\d+)/))return{sc:+m[1],sv:1,ec:+m[1],ev:999};return null}
function vbadge(r){if(!r)return'';if(r.sc===r.ec)return r.sv===1&&r.ev===999?`${r.sc}`:`${r.sc}:${r.sv}${r.ev!==r.sv&&r.ev<999?'–'+r.ev:''}`;
 return `${r.sc}${r.sv>1?':'+r.sv:''}–${r.ec}${r.ev<999?':'+r.ev:''}`}
/* a stop's audio as three zoom levels, biggest picture first:
   overview = whole Bible / section surveys (at a book's first chapter), the whole book, then stretches of 3+ chapters, widest first;
   chapter  = full sermons on this chapter (one or two chapters), by where they start;
   verses   = short devotionals on a verse or two, by verse */
function listenGroups(b,c){const g={overview:[],chapter:[],verses:[]},R=x=>x.r||{sc:999,sv:999,ec:999,ev:999},first=!!c.intro;
 const span=x=>x.r?(x.r.ec-x.r.sc)*1000+(x.r.ev-x.r.sv):1e9;
 if(first){const ord=books().map(x=>x.name),groups={};(b.spans||[]).forEach(x=>{if(!okWho(x.id))return;let lab=x.label;
   if(x.books&&!/Testament|Law|History|Wisdom|Prophets|Gospels|Church|Letters|Revelation/.test(lab)){const idxs=x.books.map(n=>ord.indexOf(n)).sort((p,q)=>p-q);const contig=idxs[idxs.length-1]-idxs[0]===idxs.length-1;lab=contig?`${ord[idxs[0]]}–${ord[idxs[idxs.length-1]]}`:x.books.join(', ')}
   const w=/Bible/i.test(lab)?1000:/Testament/i.test(lab)?500:x.books?x.books.length:50;(groups[lab]=groups[lab]||{w:0,ids:[]}).ids.push(x.id);groups[lab].w=Math.max(groups[lab].w,w)});
  Object.entries(groups).sort((a,z)=>z[1].w-a[1].w).forEach(([lab,o])=>o.ids.forEach(id=>g.overview.push({id,r:null,h:lab.charAt(0).toUpperCase()+lab.slice(1)})));
  b.ov.filter(okWho).forEach(id=>g.overview.push({id,r:prange(I[id].pass,b.name),h:'The book of '+b.name}))}
 const st=[];c.ids.filter(okWho).forEach((id,k)=>{const it=I[id],r=prange(it.pass,b.name),verse=!!r&&(r.sv>1||r.ev<999),wide=!verse&&(!r||r.ec-r.sc>=2||/^All |survey/i.test(it.pass||''));
  /* zoom by how exact the passage is: whole books and long stretches → overview, whole chapters → chapter, named verses → verses */
  (it.tr==='devotional'||verse?g.verses:wide?st:g.chapter).push({id,r,k})});
 st.sort((a,z)=>(span(z)-span(a))||(R(a).sc-R(z).sc)||(a.k-z.k));
 st.forEach(x=>g.overview.push({...x,h:x.r?`${b.name} ${vbadge(x.r)}`:(shortPass(I[x.id].pass||'')||'Across several books')}));
 const byVerse=(a,z)=>(R(a).sc-R(z).sc)||(R(a).sv-R(z).sv)||(R(a).ec-R(z).ec)||(R(a).ev-R(z).ev)||(a.k-z.k);
 g.chapter.sort(byVerse);g.verses.sort(byVerse);for(const k in g)g[k]=partsInOrder(g[k]);return g}
/* radio messages come in parts ("… - Part A", "Part 2"): keep each message's parts together and in order A, B, C */
function partOf(t){const m=(t||'').match(/^(.*?)[\s\-–—:,(]*\bPart\s+([A-Z]|\d+)\b\)?\s*$/i);return m?{base:m[1].trim().toLowerCase(),n:isNaN(+m[2])?m[2].toUpperCase().charCodeAt(0)-64:+m[2]}:null}
function partsInOrder(a){const by={},P=a.map(x=>partOf(I[x.id]&&I[x.id].t));P.forEach((p,k)=>{if(p)(by[p.base]=by[p.base]||[]).push(k)});
 const out=[],done=new Set();a.forEach((x,k)=>{const p=P[k],grp=p&&by[p.base];if(!grp||grp.length<2){out.push(x);return}if(done.has(p.base))return;done.add(p.base);
  grp.slice().sort((u,v)=>P[u].n-P[v].n).forEach(u=>out.push(a[u]))});return out}
function orderedIds(b,c){const g=listenGroups(b,c);return [...g.overview,...g.chapter,...g.verses].map(x=>x.id)}
function versesFor(pass,book,ch){ /* the verse range a passage names inside this chapter, or null for the whole chapter */
 const esc2=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');const re=new RegExp(esc2(book).replace(/^Psalms$/,'Psalms?')+'\\s+(\\d+)(?::(\\d+)(?:\\s*[–-]\\s*(?:(\\d+):)?(\\d+))?)?','i');
 for(const part of pass.split(/;/)){const m=part.match(re);if(!m||+m[1]!==ch)continue;if(!m[2])return null;const a=+m[2];const b=m[3]&&+m[3]!==ch?999:(m[4]?+m[4]:a);return{from:a,to:b}}return null}
function chapterHTML(data,c,hl){const nb=D.books.find(x=>x.name===data.book);const top=nb&&hasNar(nb.abbr,c)?`<div class="narbar"><button data-narplay="1">${icon('play',16,0,'#fff')}<b>Listen</b></button><button class="nx" data-narfull="1" aria-label="Open the full reader"><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><span><b data-dur="${narDur(nb.abbr,c)}">${durTxt(narDur(nb.abbr,c))}</b> · Tap a verse to start there.</span></div>`:'';const w=walk(),nx=w[camp+1];
 const here=w[camp],done=here&&!here.c.intro&&!!read[scrKey(here)];
 return top+chapterBody(data,c,hl)+`<div class="endacts">${done?`<div class="rdone">✓ Read</div>`:`<button class="walk" data-endread="1">I’ve read ${esc(data.book+' '+c)} ›</button>`}<button data-endclose="1">Back to the teaching</button></div><div class="src">Berean Standard Bible · public domain</div>`}
function chapterBody(data,c,hl){const vs=data.chapters[c-1]||[];let h='',open=false;
 for(const v of vs){if(v.h){if(open){h+='</p>';open=false}h+=`<h4>${esc(v.h)}</h4>`}if(v.d)h+=`<div class="ptitle">${esc(v.d)}</div>`;
  if(v.p||!open){if(open)h+='</p>';h+=`<p class="${v.q?'poem q'+v.q:''}">`;open=true}
  const on=hl&&v.v>=hl.from&&v.v<=hl.to;h+=`<span class="vs${on?' hl':''}" data-v="${v.v}"><sup>${v.v}</sup>${esc(v.t).replace(/\n/g,'<br>')}</span> `}
 if(open)h+='</p>';return h}
function wireReader(el){const d=el.closest('details'),nb=D.books.find(x=>x.name===el.dataset.book),nc=+el.dataset.ch;
 if(nb&&hasNar(nb.abbr,nc)){el.classList.add('narr');
  el.querySelectorAll('[data-narplay]').forEach(b=>b.onclick=e=>{e.stopPropagation();const id=narId(nb.abbr,nc);if(cur===id){audio.paused?audio.play().catch(()=>{}):audio.pause();return}narPlay(nb,nc,null)});
  el.querySelectorAll('[data-narfull]').forEach(b=>b.onclick=e=>{e.stopPropagation();const id=narId(nb.abbr,nc);if(cur===id){setMini(false);return}
   const top=[...el.querySelectorAll('.vs')].find(v=>v.getBoundingClientRect().bottom>80);narPlay(nb,nc,top&&+top.dataset.v>1?+top.dataset.v:null,{load:true,full:true})});
  wireVerses(el,nb,nc);narMark(true);narBar()}
 el.querySelectorAll('[data-endclose]').forEach(b=>b.onclick=()=>{TAB='teaching';S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false;const cl=$('#clearing');if(cl)window.scrollTo({top:cl.getBoundingClientRect().top+scrollY-70,behavior:'smooth'})});
 el.querySelectorAll('[data-endread]').forEach(b=>b.onclick=()=>{const x=walk()[camp];read[scrKey(x)]=true;S.set('read',read);const a=camp===jpIdx()?nextAction(camp):null;showStep(a&&a.step||TAB);const cl=$('#clearing');if(cl)setTimeout(()=>window.scrollTo({top:cl.getBoundingClientRect().top+scrollY-70,behavior:'smooth'}),60)})}
function fillMapTab(){const el=document.querySelector('.maptab');if(!el||el.dataset.done)return;el.dataset.done='1';
 atlas().then(A=>{if(!A.map||!A.trip){el.textContent='The map could not be opened.';return}const T=A.trip,st=standing(A),L=T.legs[st.leg],key=el.dataset.b+' '+el.dataset.c;
  const places=(A.here[key]||[]).map(s=>[s,A.l[s]]).filter(x=>x[1]&&x[1].x!=null).slice(0,6);let marks,trail=null;
  if(places.length)marks=places.map(([s,l],i)=>({x:l.x,y:l.y,n:l.n,sl:s,main:st.mark&&Math.hypot(st.mark.x-l.x,st.mark.y-l.y)<.01}));
  else{const seen=new Set();marks=L.stops.filter(s=>{const k=s.x+','+s.y;if(seen.has(k))return false;seen.add(k);return true}).map(s=>({x:s.x,y:s.y,n:s.n,sl:s.sl,hollow:1}));trail=L.stops.filter(s=>s.t!=null)}
  if(st.mark&&!marks.some(m=>m.main))marks.push({x:st.mark.x,y:st.mark.y,n:places.length?'':st.mark.n,main:1});
  const xs=marks.map(m=>m.x),ys=marks.map(m=>m.y),bw=Math.max(...xs)-Math.min(...xs),bh=Math.max(...ys)-Math.min(...ys),w=Math.max(30,bw*1.5,bh*1.5*340/200);
  const line=st.mark?st.line:(st.line||'');
  el.innerHTML=mapSVG(A,(Math.max(...xs)+Math.min(...xs))/2,(Math.max(...ys)+Math.min(...ys))/2,w,marks,{trail,notap:1})+
   `<div class="mt-k">Leg ${st.leg+1} of 14 · ${esc(L.t)}</div><p class="mt-s">${esc(L.s)}</p>`+(line?`<p class="mt-here">${esc(line)}</p>`:'')+
   (places.length?`<p class="mt-note">Places in ${esc(key)}: ${places.map(([s,l])=>`<button class="nm l" data-nk="l" data-ns="${s}">${esc(l.n)}</button>`).join(', ')}</p>`:'')+
   `<button class="mt-open" id="mtopen">Open the whole journey map ›</button>`;
  el.querySelectorAll('[data-nk]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(b.dataset.nk,b.dataset.ns)});
  const ob=el.querySelector('#mtopen');if(ob)ob.onclick=e=>{e.stopPropagation();openMap(null)}}).catch(()=>{el.textContent='The map could not be opened.'})}
function fillReaders(){document.querySelectorAll('details.readx[open] .txt').forEach(el=>{const book=el.dataset.book,c=+el.dataset.ch;
 if(el.dataset.done==='1')return;el.dataset.done='1';el.textContent='Opening '+book+' '+c+'…';
 loadBook(book).then(d=>{const hl=HL&&HL.book===book&&HL.ch===c?HL:null;el.innerHTML=chapterHTML(d,c,hl);wireReader(el);
  if(hl){const t=el.querySelector('.hl');if(t)setTimeout(()=>t.scrollIntoView({behavior:'smooth',block:'center'}),80)}}).catch(()=>{el.dataset.done='';el.textContent='This book could not be opened. Check the connection and try again.'})})}  /* summaries the listener opened stay open across redraws */  /* ready: the episode has loaded and jumped to its place, so positions can be saved */
const LANDS=[['Genesis','The Law'],['Joshua','History'],['Job','Wisdom & Song'],['Isaiah','Major Prophets'],['Hosea','Minor Prophets'],['Matthew','The Gospels'],['Acts','The Church Begins'],['Romans','Letters of Paul'],['Hebrews','General Letters'],['Revelation','The End & the New Beginning']];
function books(){const b=[...D.books];if(cfg.order==='narr')b.sort((x,y)=>Math.min(...x.ch.map(c=>c.seq))-Math.min(...y.ch.map(c=>c.seq)));return b}
function introOf(b){return b._in||(b._in={c:0,intro:true,ids:[],sl:b.bl||'',y:b.yr||'',sm:null,seq:-1})}
/* each book opens with its own stop (title, what the book is about, its overviews); its chapters follow */
function walk(){const w=[];for(const b of books()){const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;w.push({b,c:introOf(b)});for(const c of chs)w.push({b,c})}return w}
function stopName(x){return x.c.intro?x.b.name:x.b.name+' '+x.c.c}
function stopIds(x){return x.c.intro?[...(x.b.spans||[]).map(s=>s.id),...x.b.ov]:x.c.ids}
function stopRead(x){return x.c.intro?!!(read[x.b.abbr+'0']||x.b.ch.some(cc=>read[x.b.abbr+cc.c]||cc.ids.some(id=>((prog[id]||{}).heard||0)>0))):!!read[x.b.abbr+x.c.c]}
/* saved places from before book stops existed: move them once onto the same chapter */
function migrateCamp(){if(S.get('camp2'))return;if(camp!=null){let cum=0,bi=0;for(const b of books()){if(camp<cum+b.n){camp=camp+bi+1;break}cum+=b.n;bi++}S.set('camp',camp)}S.set('camp2',1)}
const NAMES={Platt:'David Platt',PAM:'Philip Anthony Mitchell',Davey:'Stephen Davey',Skip:'Skip Heitzig',Fearless:'Fearless Church'};
function teacher(i){return i.by||NAMES[i.who]}
function dispTitle(i){let t=(i.sc?(i.t||'').replace(/^\s*\d+\.\d+\s*[–—-]\s*/,''):(i.t||''));if(i.sc&&/^(introduction|conclusions?|critical conclusions|gospel foundations|gospel conclusions|practical takeaways|applications|the gospel|concluding challenges)\b/i.test(t)){const ev=(D.sc.events||[]).find(e=>e.n===i.sc[0]);if(ev)t=ev.title+': '+t}const fl=t.match(/^Flight\s+([1-3]?[A-Z]{2,4}?)(\d{1,2})\b(?:\s*-\s*(Part\s+\w+))?/);if(fl){const ord=books().map(x=>x.name),bk=fl[1]==='INT'?['Between the Testaments']:(i.pass||'').split(';').map(x=>x.replace(/the book of/i,'').replace(/\s+\d+(?:\s*[-–]\s*\d+)?\s*$/,'').trim()).filter(Boolean).sort((p,q)=>ord.indexOf(p)-ord.indexOf(q));return ['Bible from 30,000 Feet',bk.join(', ')+(+fl[2]>1?' ('+(+fl[2])+')':''),fl[3]].filter(Boolean).join(' · ')}if(!t.includes('|'))return t;const parts=t.split('|').map(x=>x.trim()).filter(Boolean),who=(teacher(i)||'').toLowerCase();
 const keep=parts.filter(x=>!/^(?:[1-3]\s?)?[A-Za-z]+\.?\s*\d+(?::\d+)?(?:\s*[-–]\s*\d+(?::\d+)?)?$/.test(x)&&!(who&&x.toLowerCase().replace(/^(elder|pastor|minister)\s+/,'')===who.replace(/^(elder|pastor|minister)\s+/,''))&&!/^(philip anthony mitchell|pam)$/i.test(x));
 return keep.length?keep.join(' · '):t}
function vItem(id,bd,up){const h=voiceHTML(id,bd);return id===up?h.replace('<div class="voice','<div class="voice upnext').replace('<div class="who">','<div class="who"><b class="upn">Up next</b> · '):h}
function voiceHTML(id,bd){const i=I[id],p=prog[id]||{},hp=heardPct(id),deg=!isDone(id)?Math.round(3.6*hp):0,playing=cur===id&&!audio.paused;
 return `<div class="voice ${isDone(id)?'done':''}"><button class="pb ${i.audio?'':'off'} ${playing?'playing':''}" style="--p:${deg}deg;position:relative" data-play="${id}"><span style="color:${playing?'var(--gold2)':'var(--ink)'}">${icon(playing?'pause':'play',18,0,'currentColor')}</span></button>
 <div class="tx"><div class="who">${bd?`<button class="pref vb" data-pass="${esc(i.pass)}">${bd}</button>`:''}${teacher(i)}${i.show?' · '+i.show:i.tr==='overview'?' · Overview':''}</div><div class="ti">${esc(dispTitle(i))}</div><div class="ln">${mins(i.dur)||(i.audio?'':'audio soon')}${hp&&!isDone(id)?' · '+hp+'% heard':''}${!bd&&i.pass&&!/^All \d|survey/i.test(i.pass)?` · <button class="pref" data-pass="${esc(i.pass)}">${esc(shortPass(i.pass))}</button>`:''}</div></div>
 <span class="ck" role="img" aria-label="${isDone(id)?'Listened':'Not yet listened'}">✓</span></div>`}
let W=null; // cached world geometry
/* ---- the journey: one place in Scripture (jp), and one next step at a time.
   Each stop's steps: Overview (the book, or a stretch of chapters) → Scripture (read or listen) → Teaching (the whole
   chapter, then verse by verse). A teaching that covers several chapters waits at the first of them; once heard or
   skipped it is not asked for again (it stays in the lists). Nothing walks on by itself: the next chapter waits for you. */
Object.assign(ICON,{book:'<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20"/>',arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',map:'<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>'});
let SKIP=S.get('skip',{}),JM=false,FIRSTAT=null,PLAYSTOP=null;
const stopKey=x=>x.b.abbr+':'+(x.c.intro?0:x.c.c),scrKey=x=>x.b.abbr+x.c.c;
function firstAt(){if(FIRSTAT)return FIRSTAT;const m={};walk().forEach((x,i)=>stopIds(x).forEach(id=>{if(!(id in m))m[id]=i}));return FIRSTAT=m}
function jpIdx(){const w=walk(),k=S.get('jp',null);let i=k?w.findIndex(x=>stopKey(x)===k):-1;
 if(i<0){i=camp!=null&&w[camp]?camp:w.findIndex(x=>!stopRead(x));if(i<0)i=0;S.set('jp',stopKey(w[i]))}return i}
function setJP(i){const w=walk();if(w[i])S.set('jp',stopKey(w[i]))}
function stepsOf(i){const x=walk()[i];if(!x)return null;const G=listenGroups(x.b,x.c);return {x,ov:G.overview.map(g=>g.id),teach:[...G.chapter,...G.verses].map(g=>g.id)}}
const queued=(id,i)=>firstAt()[id]===i&&!!I[id]&&!!I[id].audio&&!isDone(id)&&!SKIP[id];
const scrDone=x=>!!read[scrKey(x)]||!!SKIP['S:'+scrKey(x)];
function nextAction(i){const s=stepsOf(i);if(!s)return null;const x=s.x;
 for(const id of s.ov)if(queued(id,i))return{kind:'play',id,step:'overview'};
 if(!x.c.intro&&!scrDone(x))return{kind:'scripture',step:'scripture'};
 for(const id of s.teach)if(queued(id,i))return{kind:'play',id,step:'teaching'};
 return i+1<walk().length?{kind:'walk',to:i+1,step:null}:{kind:'end',step:null}}
function stepState(i){const s=stepsOf(i),pend=l=>l.some(id=>queued(id,i));return{overview:{n:s.ov.length,done:!pend(s.ov)},scripture:{n:1,done:s.x.c.intro||scrDone(s.x)},teaching:{n:s.teach.length,done:!pend(s.teach)}}}
function leftOf(id){const it=I[id],p=prog[id]||{};return p.dur&&p.pos>30?Math.max(0,p.dur-p.pos-(it.e||0)):0}
function contHTML(i){const w=walk(),x=w[i],a=nextAction(i);if(!a)return'';
 const btn=(ic,small,big,sub,cls='')=>`<button class="cont ${cls}" id="cont"><span class="cont-ic">${ic}</span><span class="cont-t"><small>${small}</small><b>${big}</b>${sub?`<em>${sub}</em>`:''}</span></button>`;
 if(a.kind==='play'){const it=I[a.id],playing=cur===a.id&&!audio.paused,left=leftOf(a.id),stage=a.step==='overview'?(x.c.intro?'Book overview':'Overview'):'Teaching';
  return btn(icon(playing?'pause':'play',22,0,'#1b2440'),playing?'Playing · '+stage:left?'Resume · '+stage:stage,esc(dispTitle(it)),esc(teacher(it))+(left?' · '+atSpd(left)+' left':it.dur?' · '+durTxt(+it.dur):''))
   +`<div class="cont-alt"><button data-skipnext="${a.id}">Skip for now</button></div>`}
 if(a.kind==='scripture'){const n=hasNar(x.b.abbr,x.c.c)?narDur(x.b.abbr,x.c.c):0;
  return btn(icon('book',22,1.8,'#1b2440'),'Scripture','Read '+esc(stopName(x)),n?'or listen · '+durTxt(n):'')+`<div class="cont-alt"><button data-skipnext="S:${scrKey(x)}">Skip for now</button></div>`}
 if(a.kind==='walk'){const nx=w[a.to];return btn(icon('arrow',22,2,'#1b2440'),'When you’re ready','Walk on to '+esc(stopName(nx)),nx.c.intro?'A new book begins':'','walk')}
 return `<div class="cont-end">You have walked the whole of Scripture.</div>`}
function awayHTML(j){const w=walk();return `<div class="away"><button class="cont ghost" id="cont"><span class="cont-ic">${icon('arrow',20,2,'var(--ink)')}</span><span class="cont-t"><small>Your place</small><b>Return to ${esc(stopName(w[j]))}</b></span></button><div class="cont-alt"><button id="sethere">Make ${esc(stopName(w[camp]))} my place</button></div></div>`}
/* in Explore the card points to Journey, where your place is kept */
function exploreNext(j){const w=walk();if(camp===j)return `<button class="cont ghost" id="tojourney"><span class="cont-ic">${icon('book',20,1.8,'var(--ink)')}</span><span class="cont-t"><small>Your place</small><b>Continue in Journey</b></span></button>`;
 return `<button class="cont ghost" id="tojourney"><span class="cont-ic">${icon('arrow',20,2,'var(--ink)')}</span><span class="cont-t"><small>Your place · ${esc(stopName(w[j]))}</small><b>Continue in Journey</b></span></button><div class="cont-alt"><button id="sethere">Make ${esc(stopName(w[camp]))} my place</button></div>`}
function showStep(step,scroll){if(step)TAB=step;S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false;
 if(scroll){const el=document.querySelector(scroll==='text'?'details.readx':'.tabs');if(el)setTimeout(()=>window.scrollTo({top:el.getBoundingClientRect().top+scrollY-70,behavior:'smooth'}),60)}}
function walkOn(to){const w=walk(),fr=w[jpIdx()],nx=w[to];setJP(to);if(fr&&nx&&nx.b!==fr.b&&!fr.c.intro)note('You have walked through '+fr.b.name+'.');go(to)}
function doCont(){const i=jpIdx();if(camp!==i){go(i);return}const a=nextAction(i);
 if(a.kind==='play'){if(cur===a.id){audio.paused?audio.play().catch(()=>{}):audio.pause();return}JM=true;showStep(a.step);play(a.id)}
 else if(a.kind==='scripture')showStep('scripture','text');
 else if(a.kind==='walk')walkOn(a.to)}
function contRefresh(){const b=$('#cont');if(!b||camp!==jpIdx())return;const a=nextAction(camp);if(a&&a.kind==='play'&&a.id===cur){const ic=b.querySelector('.cont-ic'),sm=b.querySelector('small');if(ic)ic.innerHTML=icon(audio.paused?'play':'pause',22,0,'#1b2440');if(sm)sm.textContent=(audio.paused?'Resume · ':'Playing · ')+sm.textContent.replace(/^(Playing|Resume) · /,'')}}
function note(t){let n=$('#note');if(!n){n=document.createElement('div');n.id='note';n.setAttribute('role','status');document.body.appendChild(n)}n.textContent=t;n.classList.add('on');clearTimeout(note.t);note.t=setTimeout(()=>n.classList.remove('on'),3800)}
/* ======== Four places along the bottom: Journey · Big Picture · Explore (the road) · Library. Settings sit behind ⋯ ======== */
const TABS=[['journey','Journey'],['bigpicture','Series'],['library','Library']];
let JZ=S.get('jz','stop')==='road'?'road':'stop',BACK=null;
const TAB_IC={journey:'<path d="M12 6.5C9.8 5 7 4.6 3.5 5v13c3.5-.4 6.3 0 8.5 1.5 2.2-1.5 5-1.9 8.5-1.5V5c-3.5-.4-6.3 0-8.5 1.5z"/><path d="M12 6.5v13"/>',
 bigpicture:'<path d="M3 17h18"/><path d="M7 17a5 5 0 0 1 10 0"/><path d="M12 6v2M5.6 9.6l1.4 1.4M18.4 9.6 17 11M3 13.5h1.5M19.5 13.5H21"/>',
 walk:'<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',library:'<path d="M4 5h4v15H4zM10 5h4v15h-4zM16.5 5.5l3.6-.9 3 14.5-3.6.9z"/>'};
let PREV='journey';
function tabOf(v){return v==='sc'?'library':v==='walk'?'journey':v}
function tabsPaint(){ztPaint();const t=$('#tabs');if(!t)return;if(!t.dataset.on){t.dataset.on=1;t.innerHTML=TABS.map(([k,l])=>`<button data-tab2="${k}"><svg viewBox="0 0 24 24" width="25" height="25" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TAB_IC[k]}</svg><span>${l}</span></button>`).join('');
  t.querySelectorAll('[data-tab2]').forEach(b=>b.onclick=()=>{const v=b.dataset.tab2;if(v===view){window.scrollTo({top:0,behavior:'smooth'});return}setView(v)})}
 t.querySelectorAll('[data-tab2]').forEach(b=>{const on=b.dataset.tab2===tabOf(view);b.classList.toggle('on',on);b.setAttribute('aria-current',on?'page':'false')});document.body.dataset.v=view}
function setView(v){if(v==='walk'){v='journey';JZ='road';S.set('jz',JZ)}if(view!=='settings')PREV=view;view=v;S.set('view',v);if(v==='journey'&&JZ==='road'){decorate.first=true;camp=jpIdx()}render();if(!(v==='journey'&&JZ==='road'))window.scrollTo(0,0)}
function setZoom(z){JZ=z;S.set('jz',z);if(z==='road'){camp=jpIdx();decorate.first=true}else closeSeries();render();if(z==='stop')window.scrollTo(0,0)}
/* the bar at the top of Journey: [ your stop | The Road ] and settings */
function ztPaint(){let el=$('#zt');const on=view==='journey';document.body.dataset.z=on?JZ:'';if(!el)return;el.hidden=!on;if(!on)return;const x=walk()[jpIdx()];
 el.innerHTML=`<div class="zt-seg" role="group" aria-label="Zoom"><button data-z="stop" class="${JZ==='stop'?'on':''}" aria-pressed="${JZ==='stop'}">${icon('book',15,1.9,'currentColor')}<span>${esc(stopName(x))}</span></button><button data-z="road" class="${JZ==='road'?'on':''}" aria-pressed="${JZ==='road'}">${icon('map',15,1.9,'currentColor')}<span>The Road</span></button></div><button class="zt-more" data-settings aria-label="Settings"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg></button>`;
 el.querySelectorAll('[data-z]').forEach(b=>b.onclick=()=>{if(b.dataset.z===JZ){if(JZ==='stop')window.scrollTo({top:0,behavior:'smooth'});return}setZoom(b.dataset.z)});el.querySelector('[data-settings]').onclick=()=>setView('settings')}
/* The Road: a book opens its chapters in a sheet; a chapter on the road opens its player */
function roadPick(i){const w=walk(),x=w[i];if(!x)return;if(x.c.intro){openBook(x.b);return}JZ='stop';S.set('jz',JZ);jMove(i)}
function openBook(b){const w=walk(),el=$('#bps'),j=jpIdx(),here=w[j],bi=w.findIndex(x=>x.b===b&&x.c.intro),land=landOf(b);
 el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${esc(b.name)}"><button class="grab2" data-bpsx aria-label="Close"></button>
  <div class="jv-eb" style="margin:4px 2px 0">${esc(land)}${b.yr?' · '+esc(b.yr):''}</div><div class="bps-t" style="font-size:34px;margin:2px 2px 0">${esc(b.name)}</div>${b.bl?`<p class="bps-d" style="font-family:'Iowan Old Style',Palatino,Georgia,serif;font-size:17px">${esc(plainT(b.bl))}</p>`:''}
  <button class="bk-ov${here.b===b&&here.c.intro?' cur':''}" data-pick="${bi}"><span>Book overview</span><em>${stopRead(w[bi])?'✓ heard':''}</em></button>
  <div class="jv-sec" style="margin-top:18px">${b.ch.length} chapter${b.ch.length>1?'s':''}</div><div class="bk-g">${b.ch.map(c=>{const k=w.findIndex(x=>x.b===b&&x.c===c),dn=!!read[b.abbr+c.c]||c.ids.some(isDone);return `<button data-pick="${k}" class="${k===j?'cur':dn?'done':''}" aria-label="${esc(b.name)} ${c.c}${dn?', read':''}">${c.c}</button>`}).join('')}</div>
  <p class="bps-n" style="text-align:center;margin-top:14px">Tap a chapter to go there.</p></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));el.querySelectorAll('[data-bpsx]').forEach(x=>x.onclick=closeSeries);
 el.querySelectorAll('[data-pick]').forEach(x=>x.onclick=()=>{const k=+x.dataset.pick;el.classList.remove('on');document.body.classList.remove('bpsopen');el.hidden=true;el.innerHTML='';JZ='stop';S.set('jz',JZ);jMove(k)})}
function hereCard(){const w=walk(),i=jpIdx(),x=w[i],a=nextAction(i);let sub='';if(a.kind==='play')sub='Up next · '+dispTitle(I[a.id])+' · '+teacher(I[a.id]);else if(a.kind==='scripture')sub='Up next · Read '+stopName(x);else if(a.kind==='walk')sub='Next · '+stopName(w[a.to]);
 return `<div id="here"><button class="here-t" data-z2="stop"><small>You are here · tap to open</small><b>${esc(stopName(x))}</b><em>${esc(sub)}</em></button>${a.kind==='play'||a.kind==='scripture'?`<button class="here-p" id="herep" aria-label="Play">${icon('play',15,0,'#fff')}</button>`:''}</div>`}
const moreBtn=()=>`<button class="vmore" data-settings aria-label="Settings">${'<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg>'}</button>`;

/* ---- the illustration at the top of a stop: a dawn over the land, tinted by its part of the Bible ---- */
const LAND_HUE={'The Law':['#c8b183','#f2e2ba','#a8946c','#8a7756'],'History':['#b9ae8c','#efe6c6','#9c8f6a','#7d7254'],'Wisdom & Song':['#c3b59a','#f3e9cf','#a59575','#86775b'],
 'Major Prophets':['#b4a088','#eee0c4','#94806a','#776350'],'Minor Prophets':['#bcab8c','#f0e4c6','#9e8a6b','#816d51'],'The Gospels':['#cdb98c','#f6ead0','#ab9568','#8b7650'],
 'The Church Begins':['#b5bfb2','#eef0e2','#909f8c','#73836d'],'Letters of Paul':['#c4b89c','#f3ead4','#a39678','#857a5d'],'General Letters':['#c0ae8e','#f1e6c8','#a08f6e','#827153'],'The New Beginning':['#d6c08a','#fbf0cf','#b69d64','#94804f']};
function landOf(b){return (LANDS.slice().reverse().find(l=>books().indexOf(b)>=books().findIndex(bb=>bb.name===l[0]))||[,''])[1]}
function heroArt(x,w,h,id){const c=LAND_HUE[landOf(x.b)]||LAND_HUE['The Law'],sd=((D.books.indexOf(x.b)*37+(x.c.c||0)*13)%97)/97,sx=Math.round(w*(.3+.4*sd)),sy=Math.round(h*.42),
  hl=(y,a,ph)=>{let d=`M0 ${y}`;for(let k=0;k<=8;k++){const px=w*k/8;d+=` L${px.toFixed(0)} ${(y+a*Math.sin(k*1.1+ph)).toFixed(1)}`}return d+` V${h} H0 Z`},lm=LANDMARKS[x.b.abbr+x.c.c];
 return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs><linearGradient id="${id}s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c[0]}"/><stop offset=".62" stop-color="${c[1]}"/><stop offset="1" stop-color="${c[1]}"/></linearGradient><radialGradient id="${id}g" cx="${(sx/w).toFixed(2)}" cy=".42" r=".55"><stop offset="0" stop-color="#fffbef"/><stop offset=".38" stop-color="#fff0c4" stop-opacity=".85"/><stop offset="1" stop-color="#fff0c4" stop-opacity="0"/></radialGradient></defs>
  <rect width="${w}" height="${h}" fill="url(#${id}s)"/><g stroke="#fff8e0" stroke-opacity=".55" stroke-width="6" stroke-linecap="round">${[-2,-1,0,1,2].map(k=>`<path d="M${sx} ${sy} L${(sx+k*w*.22).toFixed(0)} ${h}"/>`).join('')}</g><rect width="${w}" height="${h}" fill="url(#${id}g)"/>
  <g fill="#fffaf0" opacity=".8"><ellipse cx="${(w*.2).toFixed(0)}" cy="${(h*.3).toFixed(0)}" rx="${(w*.17).toFixed(0)}" ry="13"/><ellipse cx="${(w*.8).toFixed(0)}" cy="${(h*.36).toFixed(0)}" rx="${(w*.19).toFixed(0)}" ry="13"/></g>
  <path d="${hl(h*.5,8,sd*6)}" fill="${c[2]}" opacity=".5"/><path d="${hl(h*.6,6,sd*9+2)}" fill="${c[3]}" opacity=".45"/>
  ${lm?`<g opacity=".5" transform="translate(${(w*.82).toFixed(0)} ${(h*.6).toFixed(0)}) scale(.55) translate(${-w*.82} ${-h*.6})">${vignette2(lm[0],w*.82,h*.6)}</g>`:''}</svg>`}

/* ---- Journey: your place, the next step, and the whole stop beneath it, on one screen ---- */
let JV={more:false};
function stepFrac(i,list){const q=list.filter(id=>firstAt()[id]===i&&I[id]&&I[id].audio);if(!q.length)return 1;return q.filter(id=>isDone(id)||SKIP[id]).length/q.length}
function jRow(id,badge,up){const it=I[id];if(!it)return'';const done=isDone(id),pl=cur===id&&!audio.paused,left=leftOf(id);
 return `<div class="jw${done?' heard':''}${up===id?' up':''}"><button class="jpb${it.audio?'':' off'}" data-play="${id}" aria-label="${pl?'Pause':'Play'} ${esc(dispTitle(it))}"${it.audio?'':' disabled'}>${icon(pl?'pause':'play',12,0,'currentColor')}</button><div class="jw-t"><b>${esc(dispTitle(it))}</b><span>${esc(teacher(it))}${left?' · '+atSpd(left)+' left':it.dur?' · '+durTxt(+it.dur):''}${it.audio?'':' · audio soon'}</span></div>${done?'<i class="jw-ok" aria-label="heard">✓</i>':badge?`<span class="vb">${badge}</span>`:''}</div>`}
function journeyView(){const w=walk(),i=jpIdx(),x=w[i],b=x.b,c=x.c,a=nextAction(i),s=stepsOf(i),G=listenGroups(b,c),lm=LANDMARKS[b.abbr+c.c],up=a&&a.kind==='play'?a.id:null;
 const pv=w[i-1],nx2=w[i+1];
 let h=`<div class="jv jvz${jMove.dir?' in-'+jMove.dir:''}" id="jv"><div class="jv-eb">${esc(landOf(b))}${(c.y||b.yr)?' · '+esc(c.y||b.yr):''}</div><h1 class="jv-t"><button id="jpick" aria-label="Choose a book or chapter">${esc(stopName(x))}<svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button></h1>`;
 h+=`<div class="jv-art" id="jart">${heroArt(x,350,230,'ja')}<div class="jv-cap">${!c.intro&&lm?`<i>${esc(lm[1])}</i>`:''}<div class="cs">${rich(c.intro?(b.bl||''):(c.sl||''))}</div></div></div>`;
 const bk=BACK&&BACK.from!==i&&w[BACK.from]?BACK.from:null;
 h+=`<div class="jv-nav">${pv?`<button data-jgo="${i-1}" aria-label="Back to ${esc(stopName(pv))}">‹ ${esc(stopName(pv))}</button>`:'<span></span>'}${bk!=null?`<button class="jv-back" data-jgo="${bk}" data-back="1" aria-label="Back to ${esc(stopName(w[bk]))}"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M9 14 4 9l5-5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>${esc(stopName(w[bk]))}</button>`:''}${nx2?`<button data-jgo="${i+1}" aria-label="On to ${esc(stopName(nx2))}">${esc(stopName(nx2))} ›</button>`:'<span></span>'}</div>`;
 const segs=c.intro?[['overview','Book overview',stepFrac(i,s.ov)]]:[['overview','Overview',stepFrac(i,s.ov)],['scripture','Scripture',scrDone(x)?1:(cur===narId(b.abbr,c.c)&&audio.duration?Math.min(.95,audio.currentTime/audio.duration):0)],['teaching','Teaching',stepFrac(i,s.teach)]];
 h+=`<div class="jv-seg">${segs.map(([k,l,f])=>`<button data-jseg="${k}" class="${a&&a.step===k?'now':''}" aria-label="Go to ${l}"><i><b style="width:${Math.round(100*f)}%"></b></i>${l}</button>`).join('')}</div>`;
 if(a.kind==='play'){const it=I[a.id],pl=cur===a.id&&!audio.paused,left=leftOf(a.id);
  h+=`<button class="jv-next" id="jnext"><span class="jv-pp">${icon(pl?'pause':'play',20,0,'#fff')}</span><span class="jv-nt"><small>${pl?'Playing':left?'Resume':'Up next'}${a.step==='overview'&&!c.intro?' · Overview':''}</small><b>${esc(dispTitle(it))}</b><em>${esc(teacher(it))}${left?' · '+atSpd(left)+' left':it.dur?' · '+durTxt(+it.dur):''}</em></span></button><div class="jv-alt"><button data-skipnext="${a.id}">Skip for now</button></div>`}
 else if(a.kind==='scripture'){const n=narDur(b.abbr,c.c),pl=cur===narId(b.abbr,c.c)&&!audio.paused;
  h+=`<button class="jv-next" id="jnext"><span class="jv-pp">${icon(pl?'pause':'play',20,0,'#fff')}</span><span class="jv-nt"><small>${pl?'Reading':'Up next'}</small><b>Read ${esc(stopName(x))}</b><em>Listen along${n?' · '+durTxt(n):''}</em></span></button><div class="jv-alt"><button data-jread="1">I’ve read it</button><button data-skipnext="S:${scrKey(x)}">Skip for now</button></div>`}
 else if(a.kind==='walk'){const nx=w[a.to],nlm=LANDMARKS[nx.b.abbr+nx.c.c];
  h+=`<p class="jv-done">${c.intro?`That’s the overview of ${esc(b.name)}.`:`You’ve walked through ${esc(stopName(x))}.`} ${esc(stopName(nx))} is ready whenever you are.</p>
  <button class="jv-nextstop" id="jnext"><span class="jv-art sm">${heroArt(nx,350,150,'jn')}</span><span class="jv-ns"><small>${nx.c.intro?'A new book':'Next stop'}${nlm?' · '+esc(nlm[1]):''}</small><b>${esc(stopName(nx))}</b><em>${esc(plainT(nx.c.intro?(nx.b.bl||''):(nx.c.sl||'')))}</em><span class="jv-go">Begin ${esc(stopName(nx))} ${icon('arrow',18,2.2,'#fff')}</span></span></button>`}
 else h+=`<p class="jv-done">You have walked the whole of Scripture.</p>`;
 /* the stop's whole list: overview, scripture, teaching, in order; heard ones stay, quietly ticked */
 const cap=n=>JV.more?n:Math.min(n,8);let rows='',shown=0,total=0;
 const sec=(t,list,k)=>{if(!list.length)return'';let o=`<div class="jv-sec" id="js-${k}">${t}</div>`,last=null;list.forEach(g=>{total++;if(shown>=cap(1e9))return;if(g.h&&g.h!==last&&c.intro){o+=`<div class="jv-sub">${esc(g.h)}</div>`;last=g.h}o+=jRow(g.id,g.r?vbadge(g.r):'',up);shown++});return o};
 rows+=sec(c.intro?'Teaching on the book':'Overview',G.overview,'overview');
 if(!c.intro){const rd=!!read[scrKey(x)],pl=cur===narId(b.abbr,c.c)&&!audio.paused;rows+=`<div class="jv-sec" id="js-scripture">Scripture</div><div class="jw${rd?' heard':''}"><button class="jpb" data-jscr="1" aria-label="Read ${esc(stopName(x))}">${icon(pl?'pause':'book',13,1.8,'currentColor')}</button><div class="jw-t"><b>${esc(stopName(x))}</b><span>Read or listen${narDur(b.abbr,c.c)?' · '+durTxt(narDur(b.abbr,c.c)):''}</span></div>${rd?'<i class="jw-ok" aria-label="read">✓</i>':''}</div>`}
 rows+=sec(c.intro?'':'Teaching · in passage order',[...G.chapter,...G.verses],'teaching');if(!c.intro&&!G.chapter.length&&!G.verses.length)rows+=`<div class="jv-sec" id="js-teaching">Teaching</div><p class="jv-none">No teaching on this chapter alone yet.</p>`;if(!G.overview.length&&!c.intro)rows=`<div id="js-overview"></div>`+rows;
 if(shown<total)rows+=`<button class="jv-more" id="jmore">${total-shown} more</button>`;
 const tp=c.intro?[]:(D.topics||[]).filter(t=>t.keys.some(k=>k.b===b.name&&c.c>=k.c&&c.c<=k.to));
 if(tp.length)rows+=`<div class="jv-tp"><span>Explore this topic</span>${tp.map(t=>`<button data-topic="${t.id}">${esc(t.name)} ›</button>`).join('')}</div>`;
 return h+`<div class="jv-list">${rows}</div></div>`}
function jCont(){const w=walk(),i=jpIdx(),x=w[i],a=nextAction(i);BPM=null;
 if(a.kind==='play'){if(cur===a.id){audio.paused?audio.play().catch(()=>{}):audio.pause();return}JM=true;play(a.id)}
 else if(a.kind==='scripture'){const id=narId(x.b.abbr,x.c.c);if(cur===id){audio.paused?audio.play().catch(()=>{}):audio.pause();return}JM=true;narPlay(x.b,x.c.c,null,{jm:true,full:true})}
 else if(a.kind==='walk'){const fr=x,nx=w[a.to];setJP(a.to);camp=a.to;S.set('camp',camp);if(nx.b!==fr.b&&!fr.c.intro)note('You have walked through '+fr.b.name+'.');JV.more=false;render();window.scrollTo({top:0,behavior:'smooth'})}}
function jMove(i,back){const w=walk(),f=jpIdx();if(!w[i])return;if(back)BACK=null;else if(Math.abs(i-f)>1)BACK={from:f};else if(BACK&&i===BACK.from)BACK=null;
 jMove.dir=i>f?'l':i<f?'r':'';setJP(i);camp=i;S.set('camp',camp);JV.more=false;render();jMove.dir='';window.scrollTo({top:0})}
function wireJourney(){const n=$('#jnext');if(n)n.onclick=jCont;document.querySelectorAll('#jv [data-topic]').forEach(b=>b.onclick=()=>openTopic(b.dataset.topic));
 document.querySelectorAll('[data-jgo]').forEach(b=>b.onclick=()=>jMove(+b.dataset.jgo,!!b.dataset.back));
 document.querySelectorAll('[data-jseg]').forEach(b=>b.onclick=()=>{const k=b.dataset.jseg,t=$('#js-'+k)||$('.jv-list');if(!t)return;if(k!=='overview'||$('#js-overview')){const y=t.getBoundingClientRect().top+scrollY-(($('#zt')||{}).offsetHeight||0)-12;window.scrollTo({top:Math.max(0,y),behavior:'smooth'});const row=t.nextElementSibling&&t.nextElementSibling.classList.contains('jw')?t.nextElementSibling:t;row.classList.remove('flash');void row.offsetWidth;row.classList.add('flash')}});
 const pk=$('#jpick');if(pk)pk.onclick=()=>{camp=jpIdx();openJump('browse')};
 document.querySelectorAll('.jv [data-nk]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(b.dataset.nk,b.dataset.ns)});
 /* swipe anywhere on the player: left = on to the next stop, right = back one */
 /* listened to passively, so scrolling stays the phone's own; a clearly sideways flick steps once the finger lifts */
 const jv=$('#jv');if(jv){let t0=null;const o={passive:true};
  jv.addEventListener('touchstart',e=>{t0=e.touches.length===1?{x:e.touches[0].clientX,y:e.touches[0].clientY,t:Date.now(),y0:scrollY}:null},o);
  jv.addEventListener('touchend',e=>{if(!t0)return;const t=e.changedTouches[0],dx=t.clientX-t0.x,dy=t.clientY-t0.y,ok=Date.now()-t0.t<700&&Math.abs(scrollY-t0.y0)<12;t0=null;
   if(ok&&Math.abs(dx)>60&&Math.abs(dx)>2.2*Math.abs(dy)&&!(e.target.closest&&e.target.closest('input,textarea'))){const to=jpIdx()+(dx<0?1:-1);if(walk()[to])jMove(to)}},o);
  jv.addEventListener('touchcancel',()=>{t0=null},o)}const mo=$('#jmore');if(mo)mo.onclick=()=>{JV.more=true;render()};
 document.querySelectorAll('[data-jread]').forEach(b=>b.onclick=()=>{const x=walk()[jpIdx()];read[scrKey(x)]=true;S.set('read',read);render()});
 document.querySelectorAll('[data-jscr]').forEach(b=>b.onclick=()=>{const x=walk()[jpIdx()],id=narId(x.b.abbr,x.c.c);BPM=null;if(cur===id){setMini(false);return}const a=nextAction(jpIdx());JM=!!(a&&a.kind==='scripture');narPlay(x.b,x.c.c,null,{jm:JM,full:true})})}

/* ---- Big Picture: whole-Bible series, each heard in order, each keeping its own place ---- */
let BP=S.get('bp',{}),BPM=null;
const bpList=()=>D.bp||[],bpGet=id=>bpList().find(s=>s.id===id),bpIds=s=>s.parts.flatMap(p=>p[1]).filter(id=>I[id]),bpName=(s,id)=>(s.names&&s.names[id])||dispTitle(I[id]);
function bpAt(s){const ids=bpIds(s),k=BP[s.id]?ids.indexOf(BP[s.id].cur):-1;if(k>=0){if(!isDone(ids[k]))return k;const n=ids.findIndex((id,j)=>j>k&&!isDone(id));return n>=0?n:k}const f=ids.findIndex(id=>!isDone(id));return f<0?0:f}
const unitN=(s,n)=>n+' '+(s.unit==='life'?(n>1?'lives':'life'):(s.unit||'episode')+(n>1?'s':''));
function bpNum(s,id){const it=I[id];return it.sc?it.sc[0]+'.'+it.sc[1]:String(bpIds(s).indexOf(id)+1)}
function bpCover(art,sz){const v={survey:`<rect width="104" height="104" fill="#1b2440"/><g fill="#f0d79a"><circle cx="18" cy="20" r="1.2"/><circle cx="40" cy="12" r="1"/><circle cx="78" cy="18" r="1.4"/><circle cx="90" cy="40" r="1"/><circle cx="14" cy="50" r="1"/><circle cx="64" cy="30" r="1"/></g><circle cx="52" cy="64" r="30" fill="#c9a24a" opacity=".14"/><path d="M52 46 C 46 54 46 60 52 64 C 58 60 58 54 52 46Z" fill="#e9cf8c"/><path d="M44 66h16v18H44z" fill="none" stroke="#e9cf8c" stroke-width="2"/><text x="52" y="96" text-anchor="middle" font-family="-apple-system,system-ui,sans-serif" font-size="7" letter-spacing="1.6" fill="#e9cf8c">OT · NT</text>`,
  chronicle:`<rect width="104" height="104" fill="#e7dbbd"/><path d="M16 86 C 36 66 28 50 50 46 C 72 42 66 22 88 16" fill="none" stroke="#9a7524" stroke-width="3" stroke-linecap="round"/><g transform="translate(16 86)" fill="none" stroke="#4f5f3f" stroke-width="1.8" stroke-linecap="round"><path d="M0 0 V-16"/><path d="M0 -12 C -9 -18 -12 -26 -5 -30 C 0 -33 6 -31 7 -26 C 15 -28 16 -18 10 -14 C 6 -12 3 -12 0 -13"/></g><path d="M78 22h20v-12h-4v-5h-4v5h-4v-8h-4v8h-4z" fill="#1b2440"/>`,
  legacies:`<rect width="104" height="104" fill="#2e4639"/><circle cx="52" cy="40" r="30" fill="#f0d79a" opacity=".12"/><circle cx="52" cy="40" r="17" fill="#f0d79a" opacity=".16"/><path d="M52 24 C 46 32 46 38 52 42 C 58 38 58 32 52 24Z" fill="#f0d79a"/><rect x="47" y="44" width="10" height="34" rx="2" fill="#e9dfc6"/><path d="M36 80h32" stroke="#c9a24a" stroke-width="3" stroke-linecap="round"/><text x="52" y="96" text-anchor="middle" font-family="-apple-system,system-ui,sans-serif" font-size="7" letter-spacing="1.6" fill="#e9cf8c">LIVES OF FAITH</text>`,
  '30k':`<rect width="104" height="104" fill="#dfe6df"/><g fill="none" stroke="#8fa08a" stroke-width="1.2"><path d="M-4 30 C 20 20 40 36 60 26 S 96 22 110 30"/><path d="M-4 46 C 22 36 42 54 64 42 S 98 38 110 46"/><path d="M-4 62 C 24 52 44 70 66 58 S 98 56 110 62"/><path d="M-4 78 C 26 68 46 86 68 74 S 98 72 110 78"/><path d="M-4 94 C 28 84 48 100 70 90 S 98 88 110 94"/></g><path d="M14 90 C 34 70 50 64 60 52 S 84 26 92 14" fill="none" stroke="#9a7524" stroke-width="2" stroke-dasharray="4 4" stroke-linecap="round"/><path d="M88 10 l8 2 -6 6z" fill="#1b2440"/><text x="12" y="20" font-family="-apple-system,system-ui,sans-serif" font-size="8" font-weight="700" letter-spacing="1" fill="#1b2440">30,000 FT</text>`}[art]||'';
 return `<svg viewBox="0 0 104 104" width="${sz}" height="${sz}" class="bpc" aria-hidden="true">${v}</svg>`}
function bpLen(s){const ids=bpIds(s),known=ids.filter(id=>+I[id].dur>0),sec=known.reduce((t,id)=>t+ +I[id].dur,0);
 return unitN(s,ids.length)+(known.length>=ids.length*.8&&sec?` · about ${Math.round(sec/3600)} hours`:s.id==='30k'?' · Genesis to Revelation':'')}
function bpPlay(sid,id){const s=bpGet(sid);if(!s||!I[id])return;const ids=bpIds(s),k=ids.indexOf(id);JM=false;
 if(cur===id&&BPM===sid){audio.paused?audio.play().catch(()=>{}):audio.pause();return}
 BPM=sid;const ck=BP[sid]?ids.indexOf(BP[sid].cur):-1;if(k>ck)BP[sid]={cur:id};S.set('bp',BP);S.set('bplast',sid);play(id);bpLabel()}
function bpLabel(){if(!BPM||!cur)return;const s=bpGet(BPM);if(!s)return;const ids=bpIds(s),k=ids.indexOf(cur);if(k<0)return;$('#np-t').textContent=bpName(s,cur);$('#np-s').textContent=teacher(I[cur])+' · '+s.title+' · '+(k+1)+' of '+ids.length}
function bpView(){const L=bpList(),ls=bpGet(S.get('bplast',''));let h=`<div class="jv bpv">${moreBtn()}<div class="jv-eb">Guided listening</div><h1 class="jv-t">Series</h1>`;
 if(ls&&BP[ls.id]){const ids=bpIds(ls),k=bpAt(ls),id=ids[k],it=I[id],pl=cur===id&&!audio.paused,left=leftOf(id);
  h+=`<button class="bp-cont" data-bpcont="${ls.id}">${bpCover(ls.art,64)}<span class="bp-ct"><small>Continue · ${esc(ls.title)}</small><b>${esc(bpName(ls,id))}</b><em>${esc(teacher(it))}${left?' · '+atSpd(left)+' left':` · ${k+1} of ${unitN(ls,ids.length)}`}</em></span><span class="bp-pp">${icon(pl?'pause':'play',16,0,'#1b2440')}</span></button>`}
 const row=s=>{const ids=bpIds(s),st=!!BP[s.id],k=bpAt(s),f=ids.filter(isDone).length/ids.length,U={session:'Session',flight:'Flight'}[s.unit];
  return `<button class="bp-row" data-bps="${s.id}">${bpCover(s.art,104)}<span class="bp-rt"><b>${esc(s.title)}</b><span class="by">${esc(s.by)}</span><span class="ds">${esc(s.desc.split('. ')[0].replace(/\.$/,''))}.</span><span class="pr"><i><b style="width:${f>0?Math.max(3,Math.round(100*f)):0}%"></b></i>${st||f>0?(U?`${U} ${k+1} of ${ids.length}`:`${k+1} of ${unitN(s,ids.length)}`):`${unitN(s,ids.length)} · not started`}</span></span></button>`};
 [['bp','Big Picture','The whole story of Scripture, start to finish'],['growth','Spiritual Growth','Teaching to grow by, one series at a time']].forEach(([g,t,sub])=>{const G=L.filter(s=>(s.group||'bp')===g);if(G.length)h+=`<div class="jv-sec">${t}</div><p class="bp-gs">${sub}</p>`+G.map(row).join('')});
 return h+'</div>'}
function openSeries(sid){const s=bpGet(sid);if(!s)return;const ids=bpIds(s),k=bpAt(s),el=$('#bps'),st=!!BP[s.id];
 let list='';s.parts.forEach(([t,p])=>{if(t)list+=`<div class="jv-sub">${esc(t)}</div>`;p.filter(id=>I[id]).forEach(id=>{const j=ids.indexOf(id),done=isDone(id),left=leftOf(id),now=j===k&&st;
  list+=`<button class="bp-ep${done?' heard':''}${now?' now':''}" data-bpplay="${id}"><span class="n">${bpNum(s,id)}</span><b>${esc(bpName(s,id))}</b><span class="d">${done?'✓':left?atSpd(left)+' left':I[id].dur?Math.round(I[id].dur/60)+' min':''}</span></button>`})});
 el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${esc(s.title)}"><button class="grab2" data-bpsx aria-label="Close"></button>
  <div class="bps-hd">${bpCover(s.art,128)}<div><div class="bps-t">${esc(s.title)}</div><div class="bps-by">${esc(s.by)}</div><div class="bps-n">${bpLen(s)}</div></div></div><p class="bps-d">${esc(s.desc)}</p>
  <button class="bps-go" data-bpcont="${s.id}"><span>${icon('play',16,0,'#fff')}</span><span><b>${st?'Continue Listening':'Begin'}</b><em>${esc(bpNum(s,ids[k])+' · '+bpName(s,ids[k]))}</em></span></button><div class="bps-list">${list}</div></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));
 el.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);el.querySelectorAll('[data-bpcont]').forEach(b=>b.onclick=()=>{const t=bpGet(b.dataset.bpcont);bpPlay(t.id,bpIds(t)[bpAt(t)]);closeSeries()});
 el.querySelectorAll('[data-bpplay]').forEach(b=>b.onclick=()=>{bpPlay(s.id,b.dataset.bpplay);closeSeries()});
 const sh=el.querySelector('.bps-sh');let y0=null;sh.ontouchstart=e=>{y0=sh.scrollTop<=0?e.touches[0].clientY:null};sh.ontouchmove=e=>{if(y0==null)return;const dy=e.touches[0].clientY-y0;if(dy>0){sh.style.transform=`translateY(${dy}px)`}};sh.ontouchend=e=>{if(y0==null)return;const dy=e.changedTouches[0].clientY-y0;y0=null;sh.style.transform='';if(dy>90)closeSeries()}}
function closeSeries(){const el=$('#bps');el.classList.remove('on');document.body.classList.remove('bpsopen');setTimeout(()=>{if(!el.classList.contains('on')){el.hidden=true;el.innerHTML='';if(view==='bigpicture')render()}},260)}
function wireBP(){document.querySelectorAll('#main [data-bps]').forEach(b=>b.onclick=()=>openSeries(b.dataset.bps));document.querySelectorAll('#main [data-bpcont]').forEach(b=>b.onclick=()=>{const t=bpGet(b.dataset.bpcont);bpPlay(t.id,bpIds(t)[bpAt(t)])})}

/* ---- Library: Secret Church, the four teachers, what you played lately ---- */
const TCH_C={Platt:'#2f4a6b',PAM:'#7a4b2a',Skip:'#5b4a7a',Davey:'#3c5a4c',Fearless:'#6b5320'};
let LT=S.get('libtab','teachers');
function libView(){const cnt={};Object.values(I).forEach(i=>{if(i.tr!=='devotional'&&i.audio&&!i.nar)cnt[i.who]=(cnt[i.who]||0)+1});
 const bpOf=id=>bpList().find(s=>bpIds(s).includes(id));
 let h=`<div class="jv lib">${moreBtn()}<h1 class="jv-t" style="margin-top:6px">Library</h1><div class="t-sort lib-seg" role="tablist" aria-label="Browse by">${[['teachers','Teachers'],['topics','Topics'],['books','Books']].map(([v,l])=>`<button role="tab" data-lt="${v}" class="${LT===v?'on':''}" aria-selected="${LT===v}">${l}</button>`).join('')}</div>`;
 if(LT==='topics'){h+=`<p class="lib-lead">What Scripture teaches about a subject, across every book and teacher.</p>`+(D.topics||[]).map(t=>{const n=t.ess.length+t.more.length;return `<button class="lib-tp" data-topic="${t.id}"><span><b>${esc(t.name)}</b><em>${esc(t.blurb.split(/(?<=[.:])\s/)[0].replace(/[.:]$/,''))}</em></span><i>${n}</i></button>`}).join('');return h+'</div>'}
 if(LT==='books'){const n={};const w=walk(),fa=firstAt();Object.values(I).forEach(i=>{if(i.tr==='devotional'||i.nar||!i.audio)return;const st=w[fa[i.id]];if(st)n[st.b.name]=(n[st.b.name]||0)+1});
  const grid=bs=>`<div class="lib-bk">${bs.map(b=>`<button data-lbook="${esc(b.name)}"><b>${esc(b.name)}</b><em>${n[b.name]||0}</em></button>`).join('')}</div>`;const mi=D.books.findIndex(b=>b.name==='Matthew'),ot=D.books.slice(0,mi),nt=D.books.slice(mi);
  return h+`<div class="jv-sec">Old Testament</div>${grid(ot)}<div class="jv-sec">New Testament</div>${grid(nt)}</div>`}
 const rec=Object.entries(prog).filter(([id,p])=>I[id]&&!I[id].nar&&p&&p.at).sort((a,z)=>z[1].at-a[1].at).slice(0,6);
 h+=`<button class="lib-sc" id="opensc"><b>Secret Church</b><span>David Platt · all ${scGroups().length} nights · ${D.sc.ids.length} sessions ›</span></button>`;
 h+=`<div class="jv-sec">Teachers</div>`+['Platt','PAM','Skip','Davey','Fearless'].filter(k=>cnt[k]).map(k=>`<button class="lib-t" data-tch="${k}"><span class="av" style="background:${TCH_C[k]}">${(n=>n[0][0]+n[n.length-1][0])(NAMES[k].split(' '))}</span><span><b>${NAMES[k]}</b><em>${(cnt[k]||0).toLocaleString()} teachings</em></span><i>›</i></button>`).join('');
 if(rec.length)h+=`<div class="jv-sec">Recently played</div><div class="lib-rec">${rec.map(([id,p])=>{const s=bpOf(id),left=leftOf(id);return `<button data-${s?'bpplay2':'play'}="${id}"${s?` data-sid="${s.id}"`:''}><small>${s?'Series':'Journey'}</small><b>${esc(s?bpName(s,id):dispTitle(I[id]))}</b><em>${esc(teacher(I[id]).split(' ').slice(-1)[0])} · ${p.done?'heard':left?atSpd(left)+' left':'started'}</em></button>`}).join('')}</div>`;
 const sk=Object.keys(SKIP).length;if(sk)h+=`<button class="lnk lib-sk" id="unskip">${sk} skipped for now — bring them back</button>`;
 return h+'</div>'}
/* a sheet over the page (#bps) holding a list of teachings; rows play in place */
function openSheet(label,inner,list,after){const el=$('#bps');el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${esc(label)}"><button class="grab2" data-bpsx aria-label="Close"></button>${inner}<div id="tlist">${list()}</div></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));el.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);
 const wireL=()=>{el.querySelectorAll('#tlist [data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();JM=false;BPM=null;PLAYSTOP=null;play(b.dataset.play);setTimeout(()=>{$('#tlist').innerHTML=list();wireL()},60)});if(after)after(el,()=>{$('#tlist').innerHTML=list();wireL()})};wireL();return el}
/* a topic: what it is, the key passages (each opens that stop on the Journey), the Secret Church night on it, essential teaching, then the rest by teacher */
function goStop(bk,c){const w=walk(),i=w.findIndex(x=>x.b.name===bk&&!x.c.intro&&x.c.c===c);if(i<0)return;closeSeries();JZ='stop';S.set('jz',JZ);if(view!=='journey'){if(view!=='settings')PREV=view;view='journey';S.set('view',view)}jMove(i)}
function openSCNight(n){closeSeries();OPEN.add('sc:'+n);view='sc';S.set('view',view);render();setTimeout(()=>{const d=document.querySelector(`[data-sck="sc:${n}"]`);if(d){d.open=true;d.scrollIntoView({block:'start'})}},40)}
function openTopic(id){const t=(D.topics||[]).find(x=>x.id===id);if(!t)return;const G=scGroups();
 const keys=t.keys.map(k=>`<button class="tp-k" data-kgo="${esc(k.b)}|${k.c}"><b>${esc(k.ref)}</b><span>${esc(k.note)}</span><i>›</i></button>`).join('');
 const nights=t.sc.map(n=>G.find(g=>g.ev.n===n)).filter(Boolean).map(g=>`<button class="tp-sc" data-scn="${g.ev.n}"><small>Secret Church ${g.ev.n}</small><b>${esc(g.ev.title)}</b><span>David Platt · ${g.ids.length} sessions ›</span></button>`).join('');
 const list=()=>{const row=id=>tRow({i:I[id]},null);let h=`<div class="jv-sec">Essential teaching</div>${t.ess.map(row).join('')}`;
  if(t.more.length){const by={};t.more.forEach(id=>(by[I[id].who]=by[I[id].who]||[]).push(id));h+=`<div class="jv-sec">More teaching</div>`+Object.entries(by).map(([k,l])=>`<details class="tch-b"><summary>${esc(NAMES[k]||k)}<span>${l.length}</span></summary>${l.map(row).join('')}</details>`).join('')}return h};
 openSheet(t.name,`<div class="bps-t" style="margin:6px 4px 0">${esc(t.name)}</div><p class="bps-d">${esc(t.blurb)}</p><div class="jv-sec">Key Scripture</div>${keys}${nights?`<div class="jv-sec">The deep dive</div>${nights}`:''}`,list,el=>{
  el.querySelectorAll('[data-kgo]').forEach(b=>b.onclick=()=>{const [bk,c]=b.dataset.kgo.split('|');goStop(bk,+c)});el.querySelectorAll('[data-scn]').forEach(b=>b.onclick=()=>openSCNight(+b.dataset.scn))})}
/* a book: every teaching on it from every teacher, in passage order, by chapter */
let LB={t:'all'};
function openLibBook(name){const b=D.books.find(x=>x.name===name);if(!b)return;const w=walk(),fa=firstAt();if(LB.b!==name){LB={b:name,t:'all'}}
 const all=Object.values(I).filter(i=>i.tr!=='devotional'&&!i.nar&&i.audio&&w[fa[i.id]]&&w[fa[i.id]].b===b).map(i=>({i,r:prange(i.pass,name),ov:w[fa[i.id]].c.intro}));
 const who=['Platt','PAM','Skip','Davey','Fearless'].filter(k=>all.some(x=>x.i.who===k));
 const list=()=>{const L=all.filter(x=>LB.t==='all'||x.i.who===LB.t),R=x=>x.r||{sc:0,sv:0,ec:999,ev:999};if(!L.length)return `<p class="bps-n" style="margin:16px 4px">Nothing here yet.</p>`;
  L.sort((a,z)=>(z.ov-a.ov)||(R(a).sc-R(z).sc)||(R(a).sv-R(z).sv)||(R(a).ec-R(z).ec)||((a.i.date||'')<(z.i.date||'')?-1:1));
  const g=[];L.forEach(x=>{const k=x.ov||!x.r?'The whole book':'Chapter '+x.r.sc;const l=g[g.length-1];if(l&&l.k===k)l.l.push(x);else g.push({k,l:[x]})});
  return g.map(x=>`<details class="tch-b"${g.length<=2||L.length<=12?' open':''}><summary>${esc(x.k)}<span>${x.l.length}</span></summary>${x.l.map(y=>tRow(y,null)).join('')}</details>`).join('')};
 openSheet(name,`<div class="bps-t" style="margin:6px 4px 0">${esc(name)}</div><div class="bps-n" style="margin:2px 4px 12px">${all.length} teaching${all.length===1?'':'s'}${b.bl?' · '+esc(plainT(b.bl)).split('. ')[0]:''}</div>${who.length>1?`<div class="t-sort t-who" role="group" aria-label="Teacher">${[['all','All'],...who.map(k=>[k,k])].map(([v,l])=>`<button data-lbt="${v}" class="${LB.t===v?'on':''}" aria-pressed="${LB.t===v}">${esc(l)}</button>`).join('')}</div>`:''}`,list,(el,re)=>{
  el.querySelectorAll('[data-lbt]').forEach(x=>x.onclick=()=>{LB.t=x.dataset.lbt;el.querySelectorAll('[data-lbt]').forEach(y=>{y.classList.toggle('on',y===x);y.setAttribute('aria-pressed',y===x)});re()})})}
/* a teacher's whole collection: sort by Bible order (passage order inside each book), newest or oldest; search; full details */
let TS={k:null,sort:S.get('tsort','bible'),q:'',more:0};
const fmtDate=d=>{try{return d?new Date(d+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):''}catch(e){return d}};
function tItems(k){const w=walk(),fa=firstAt();return Object.values(I).filter(i=>i.who===k&&i.tr!=='devotional'&&!i.nar&&i.audio).map(i=>{const st=w[fa[i.id]],bk=st?st.b.name:'Other teaching';return {i,bk,bi:st?D.books.indexOf(st.b):999,r:st?prange(i.pass,bk):null}})}
function tRow(x,k){const i=x.i,id=i.id,done=isDone(id),pl=cur===id&&!audio.paused,left=leftOf(id),ps=i.pass&&!/^the book of/i.test(i.pass)?shortPass(i.pass):(i.pass||'').replace(/^the book of /i,''),who=k?(i.by&&i.by!==NAMES[k]?i.by:''):teacher(i);
 return `<div class="tr2${done?' heard':''}"><button class="jpb${i.audio?'':' off'}" data-play="${id}" aria-label="${pl?'Pause':'Play'} ${esc(dispTitle(i))}">${icon(pl?'pause':'play',12,0,'currentColor')}</button><div class="jw-t"><b>${esc(dispTitle(i))}</b><span>${[ps,fmtDate(i.date),left?atSpd(left)+' left':i.dur?durTxt(+i.dur):''].filter(Boolean).map(esc).join(' · ')}</span>${(sh=>who||sh?`<span class="t3">${esc([who,sh].filter(Boolean).join(' · '))}</span>`:'')(i.show&&i.show!==NAMES[k]?i.show:'')}</div>${done?'<i class="jw-ok" aria-label="heard">✓</i>':''}</div>`}
function tList(){const k=TS.k,q=TS.q.trim().toLowerCase();let L=tItems(k);
 if(q){const ws=q.split(/\s+/).map(w=>/^\d+$/.test(w)?new RegExp('(^|[^0-9])'+w+'([^0-9]|$)'):w);L=L.filter(x=>{const t=(x.i.t+' '+(x.i.pass||'')+' '+(x.i.by||'')+' '+(x.i.show||'')+' '+x.bk).toLowerCase();return ws.every(w=>typeof w==='string'?t.includes(w):w.test(t))})}
 if(!L.length)return `<p class="bps-n" style="margin:16px 4px">Nothing matches “${esc(TS.q)}”.</p>`;
 const R=x=>x.r||{sc:999,sv:999,ec:999,ev:999};
 if(TS.sort==='bible'){L.sort((a,z)=>(a.bi-z.bi)||(R(a).sc-R(z).sc)||(R(a).sv-R(z).sv)||(R(a).ec-R(z).ec)||((a.i.date||'')<(z.i.date||'')?-1:1));
  const by=[];L.forEach(x=>{const g=by[by.length-1];if(g&&g.bk===x.bk)g.l.push(x);else by.push({bk:x.bk,l:[x]})});const open=q||by.length<=2;
  return by.map(g=>`<details class="tch-b"${open?' open':''}><summary>${esc(g.bk)}<span>${g.l.length}</span></summary>${g.l.map(x=>tRow(x,k)).join('')}</details>`).join('')}
 L.sort((a,z)=>((a.i.date||'')<(z.i.date||'')?-1:(a.i.date||'')>(z.i.date||'')?1:0)*(TS.sort==='newest'?-1:1));
 const cap=150*(TS.more+1),show=L.slice(0,cap);let h='',last='';show.forEach(x=>{const m=x.i.date?new Date(x.i.date+'T12:00:00').toLocaleDateString('en-US',{month:'long',year:'numeric'}):'Undated';if(m!==last){h+=`<div class="jv-sub">${esc(m)}</div>`;last=m}h+=tRow(x,k)});
 return h+(L.length>cap?`<button class="jv-more" id="tmore">${L.length-cap} more</button>`:'')}
function openTeacher(k){const el=$('#bps');if(TS.k!==k){TS.k=k;TS.q='';TS.more=0}const n=tItems(k).length;
 el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${NAMES[k]}"><button class="grab2" data-bpsx aria-label="Close"></button>
  <div class="bps-t" style="margin:6px 4px 0">${NAMES[k]}</div><div class="bps-n" style="margin:2px 4px 12px">${n.toLocaleString()} teaching${n>1?'s':''}</div>
  <div class="t-ctl"><div class="t-sort" role="group" aria-label="Sort">${[['bible','Bible order'],['newest','Newest'],['oldest','Oldest']].map(([v,l])=>`<button data-tsort="${v}" class="${TS.sort===v?'on':''}" aria-pressed="${TS.sort===v}">${l}</button>`).join('')}</div>
  <label class="t-q"><svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><input id="tq" type="search" placeholder="Search these sermons" value="${esc(TS.q)}" autocomplete="off" aria-label="Search this teacher"></label></div>
  <div id="tlist">${tList()}</div></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));el.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);
 const wireL=()=>{el.querySelectorAll('#tlist [data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();JM=false;BPM=null;PLAYSTOP=null;play(b.dataset.play);setTimeout(()=>{$('#tlist').innerHTML=tList();wireL()},60)});const m=$('#tmore');if(m)m.onclick=()=>{TS.more++;$('#tlist').innerHTML=tList();wireL()}};wireL();
 el.querySelectorAll('[data-tsort]').forEach(b=>b.onclick=()=>{TS.sort=b.dataset.tsort;S.set('tsort',TS.sort);TS.more=0;el.querySelectorAll('[data-tsort]').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b)});$('#tlist').innerHTML=tList();wireL()});
 const q=$('#tq');let tt=null;q.oninput=()=>{clearTimeout(tt);tt=setTimeout(()=>{TS.q=q.value;TS.more=0;$('#tlist').innerHTML=tList();wireL()},150)}}
function wireLib(){document.querySelectorAll('[data-tch]').forEach(b=>b.onclick=()=>openTeacher(b.dataset.tch));document.querySelectorAll('[data-lt]').forEach(b=>b.onclick=()=>{LT=b.dataset.lt;S.set('libtab',LT);render()});document.querySelectorAll('#main [data-topic]').forEach(b=>b.onclick=()=>openTopic(b.dataset.topic));document.querySelectorAll('[data-lbook]').forEach(b=>b.onclick=()=>openLibBook(b.dataset.lbook));document.querySelectorAll('[data-bpplay2]').forEach(b=>b.onclick=()=>bpPlay(b.dataset.sid,b.dataset.bpplay2))}

function render(){const m=$('#main');if(!render.boot){render.boot=true;view='journey';S.set('view',view);migrateCamp()}tabsPaint();if(view==='journey'&&JZ==='stop'){m.innerHTML=journeyView();wire();wireJourney();return}if(view==='bigpicture'){m.innerHTML=bpView();wire();wireBP();return}if(view==='library'){m.innerHTML=libView();wire();wireLib();return}if(!render.boot2){render.boot2=true;migrateCamp();camp=jpIdx();const a=nextAction(camp);if(a&&a.step){TAB=a.step;S.set('tab',TAB)}}if(view==='settings'){m.innerHTML=settingsView();wire();return}if(view==='sc'){m.innerHTML=scView();wire();return}
 migrateCamp();const w=walk();let first=jpIdx();if(camp==null||camp>=w.length)camp=first;  /* the road is walked up to your place */
 const rd=w.filter(x=>!x.c.intro&&read[x.b.abbr+x.c.c]).length;$('#pct').innerHTML=`<b>${rd}</b> of 1,189 chapters · ${Math.round(1000*rd/1189)/10}%`;
 const rows=D.books[0].yr?24:16,rowH=240,top=120,H=top+rows*rowH+200,x0=70,x1=320;let d=`M ${x0} ${top}`;for(let r=0;r<rows;r++){const f=r%2?x1:x0,t=r%2?x0:x1,y=top+r*rowH;d+=` C ${f} ${y+rowH*.55}, ${t} ${y+rowH*.45}, ${t} ${y+rowH}`}
 const POS=[];let acc=0;for(const b of books()){const wgt=(D.books[0].yr?11:6)+2.2*Math.sqrt(b.n);const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;[0,...chs].forEach((c,k)=>POS.push(acc+wgt*(k+0.5)/(b.n+1)));acc+=wgt}
 render.POS=POS;render.TOT=acc;const fill=first>0?(POS[first-1]+POS[first])/2/acc:0;
 m.innerHTML=`<div class="world" id="world"><svg id="w1" viewBox="0 0 390 ${H}" preserveAspectRatio="xMidYMin meet">
  <defs><radialGradient id="g"><stop offset="0" stop-color="#d9b15a" stop-opacity=".55"/><stop offset="1" stop-color="#d9b15a" stop-opacity="0"/></radialGradient>
  <radialGradient id="halo"><stop offset="0" stop-color="#e9c979" stop-opacity=".40"/><stop offset=".6" stop-color="#e9c979" stop-opacity=".10"/><stop offset="1" stop-color="#e9c979" stop-opacity="0"/></radialGradient>
  <radialGradient id="ember"><stop offset="0" stop-color="#e2a35a" stop-opacity=".30"/><stop offset="1" stop-color="#e2a35a" stop-opacity="0"/></radialGradient><radialGradient id="dawn"><stop offset="0" stop-color="#fff6d8" stop-opacity=".95"/><stop offset=".5" stop-color="#f6e7c0" stop-opacity=".35"/><stop offset="1" stop-color="#f6e7c0" stop-opacity="0"/></radialGradient><radialGradient id="glory"><stop offset="0" stop-color="#fffdf2" stop-opacity="1"/><stop offset=".35" stop-color="#fff3cc" stop-opacity=".85"/><stop offset=".7" stop-color="#f3dfa2" stop-opacity=".3"/><stop offset="1" stop-color="#f3dfa2" stop-opacity="0"/></radialGradient></defs>
  <g id="scene"><g id="sky"></g><g id="lands"></g>
  <path id="road" d="${d}" fill="none" stroke="rgba(27,36,64,.10)" stroke-width="30" stroke-linecap="round"/>
  <path d="${d}" fill="none" stroke="var(--gold)" stroke-width="30" stroke-linecap="round" pathLength="1" stroke-dasharray="${fill} 1" opacity=".9"/>
  <path d="${d}" fill="none" stroke="rgba(255,255,255,.95)" stroke-width="3" stroke-dasharray="3 14" stroke-linecap="round"/>
  <path id="hit" d="${d}" fill="none" stroke="transparent" stroke-width="70"/>
  <g id="labels"></g><g id="marker" style="pointer-events:none"></g></g></svg>
  <div class="clearing" id="clearing"></div>
  <svg id="w2" viewBox="0 0 390 ${H}" preserveAspectRatio="xMidYMin meet"><use href="#scene"/></svg></div>`;
 decorate(w,first);wire();if(view==='journey'){m.insertAdjacentHTML('beforeend',hereCard());const ht=m.querySelector('[data-z2]');if(ht)ht.onclick=()=>setZoom('stop');const hp=$('#herep');if(hp)hp.onclick=()=>{jCont();render()}}}
function decorate(w,first){const road=$('#road'),svg=road.ownerSVGElement,L=road.getTotalLength(),POS=render.POS,TOT=render.TOT,at=i=>road.getPointAtLength(L*POS[Math.max(0,Math.min(w.length-1,Math.round(i)))]/TOT);
 // labels with collision avoidance: short books alternate sides and get pushed apart, with leader lines back to the road
 const labs=[];let lands='',idx=0,prevSide=null,prevShort=false;
 for(const b of books()){const mid=at(idx+(b.n+1)/2),st=at(idx);let side=mid.x<195?'L':'R';if(b.n<10&&prevShort&&side===prevSide)side=side==='L'?'R':'L';
  const land=cfg.order==='canon'?LANDS.find(l=>l[0]===b.name):null;
  if(land){lands+=`<circle cx="${st.x}" cy="${st.y}" r="90" fill="url(#g)" class="glow"/>`;const txt=land[1].replace('The End & the New Beginning','The New Beginning');labs.push({kind:'land',side:st.x<195?'L':'R',x:st.x<195?st.x+40:st.x-40,y:mid.y+5-0.5,txt})  /* heading sits right above its first book */}
  labs.push({kind:'book',side,x:side==='L'?Math.min(mid.x+30,250):Math.max(mid.x-30,140),y:mid.y+5,px:mid.x,py:mid.y,txt:b.name,yr:b.yr||'',big:b.n>=20,here:w[camp].b===b,idx});
  prevSide=side;prevShort=b.n<10;idx+=b.n+1}
 labs.sort((a,b)=>a.y-b.y);const last={L:-1e9,R:-1e9};let lbl='';decorate.drift=labs;
 for(const l of labs){const gap=l.kind==='land'?30:(D.books[0].yr?38:24);const ref=Math.max(last.L,last.R);  /* one column: labels on either side can reach the middle */if(l.y-ref<gap)l.y=ref+gap;if(l.kind==='land'){last.L=last.R=l.y}else last[l.side]=l.y;
  if(l.kind==='land'){lbl+=`<text x="${l.x}" y="${l.y}" text-anchor="${l.side==='L'?'start':'end'}" class="land">${l.txt}</text>`}
  else{const moved=Math.abs(l.y-5-l.py)>12;if(moved)lbl+=`<line x1="${l.px}" y1="${l.py}" x2="${l.side==='L'?l.x-6:l.x+6}" y2="${l.y-5}" stroke="rgba(241,237,228,.25)" stroke-width="1"/>`;
   lbl+=`<text x="${l.x}" y="${l.y}" text-anchor="${l.side==='L'?'start':'end'}" class="bl ${l.big?'big':''} ${l.here?'here':''}" data-camp="${l.idx}">${l.txt}</text>${l.yr?`<text x="${l.x}" y="${l.y+15}" text-anchor="${l.side==='L'?'start':'end'}" class="byr">${l.yr}</text>`:''}`}}
 // scenery: stars thin out toward the New Testament dawn; each land gets its horizon
 let sky='';const Hs=+svg.getAttribute('viewBox').split(' ')[3];HH=Hs;let seed=7;const rnd=()=>{seed=(seed*9301+49297)%233280;return seed/233280};
 for(let i=0;i<140;i++){const yy=rnd()*Hs;if(rnd()<1-yy/Hs)sky+=`<circle cx="${(rnd()*390).toFixed(0)}" cy="${yy.toFixed(0)}" r="${(0.6+rnd()*1.2).toFixed(1)}" fill="rgba(168,129,42,${(0.12+rnd()*0.25).toFixed(2)})"/>`}
 let scenes='';idx=0;for(const b of books()){const land=cfg.order==='canon'?LANDS.find(l=>l[0]===b.name):null;if(land){const st=at(idx);scenes+=`<g opacity=".7">${sceneSVG(SCENES[land[1]],st.x,st.y-40)}</g>`}idx+=b.n+1}
 // landmarks: where the great scenes stand
 let marks='',lastVy=-1e9;
 w.forEach((x,i)=>{const lm=LANDMARKS[x.b.abbr+x.c.c];if(!lm)return;const pt=at(i);if(pt.y-lastVy<110)return;lastVy=pt.y;marks+=`<g transform="translate(${pt.x} ${pt.y}) scale(.6) translate(${-pt.x} ${-pt.y})" opacity=".75">${vignette2(lm[0],pt.x,pt.y)}</g>`});
 // per-book motifs beside the road, alternating sides; rivers at the Jordan and the river of life
 let mot='';idx=0;for(const b of books()){const land=cfg.order==='canon'?(LANDS.slice().reverse().find(l=>books().indexOf(b)>=books().findIndex(bb=>bb.name===l[0]))||[,''])[1]:'';const mid=at(idx+(b.n+1)/2);const side=mid.x<195?1:-1;const kinds={'The Law':['palm','tent','palm'],'History':['town','town','palm'],'Wisdom & Song':['olive','olive','palm'],'Major Prophets':['cedar','town','cedar'],'Minor Prophets':['olive','town','olive'],'The Gospels':['olive','town','olive'],'The Church Begins':['sail','sail','town'],'Letters of Paul':['column','sail','column'],'General Letters':['fire','fire','town'],'The New Beginning':['tree','tree','tree']}[land];
  if(kinds){const ox=mid.x+side*(118+(b.n%3)*12);if(ox>30&&ox<360)mot+=motif('',ox,mid.y+12,b.n>=20?.9:.7)}
  if(b.name==='Joshua'){const st=at(idx);mot+=river(st.x,st.y+6)}if(b.name==='Revelation'){const st=at(idx+b.n-2);mot+=river(st.x,st.y+40,.18)}idx+=b.n+1}
 $('#sky').innerHTML=terrain(Hs)+celestial(Hs)+sky+scenes+mot;
 $('#lands').innerHTML=lands;$('#labels').innerHTML=lbl+marks;
 const m=at(camp),f=at(first);
 $('#marker').innerHTML=`${camp!==first?`<circle cx="${f.x}" cy="${f.y}" r="8" fill="var(--gold)" opacity=".7"/>`:''}<circle cx="${m.x}" cy="${m.y}" r="26" fill="rgba(240,215,154,.18)"/><circle cx="${m.x}" cy="${m.y}" r="13" fill="var(--gold)" class="you"/><circle cx="${m.x}" cy="${m.y}" r="5" fill="#fff"/>`;
 // clearing placed in the world beside the marker
 const sc=svg.getBoundingClientRect().width/390,cl=$('#clearing');const x=w[camp],b=x.b,c=x.c,ids=c.ids.filter(okWho),r=!!read[b.abbr+c.c],ov=(c.intro?b.ov:[]).filter(okWho);const fold=FOLD;cl.classList.toggle('folded',fold);
 let nextV=null;for(let i=camp+1;i<w.length;i++){if(stopIds(w[i]).some(okWho)){nextV={i,x:w[i]};break}}
 {const cut=Math.min(Hs-20,m.y+44);svg.setAttribute('viewBox',`0 0 390 ${cut}`);$('#w2').setAttribute('viewBox',`0 ${cut} 390 ${Hs-cut}`)}
 const land=cfg.order==='canon'?(LANDS.slice().reverse().find(l=>books().indexOf(b)>=books().findIndex(bb=>bb.name===l[0]))||[,''])[1]:'';
 const chDone=x=>!!read[x.b.abbr+x.c.c]||x.c.ids.some(isDone),bibleN=w.filter(x=>!x.c.intro&&chDone(x)).length,bookN=b.ch.filter(cc=>chDone({b,c:cc})).length,hereDone=x.c.intro?stopRead(x):chDone(x),heardIn=ids2=>[...new Set(ids2)].reduce((a,id)=>a+((prog[id]||{}).heard||0),0),bookHeard=heardIn([...b.ch.flatMap(cc=>cc.ids),...b.ov,...(b.spans||[]).map(sp=>sp.id)]),bibleHeard=Object.values(prog).reduce((a,v)=>a+(v&&v.heard||0),0),AV=avail(),pct=(n,d)=>{const v=100*n/d;return v>0&&v<10?v.toFixed(1):String(Math.round(v))},lm=LANDMARKS[b.abbr+c.c],T_=(t=>c.intro&&(t==='scripture'||t==='teaching')?'overview':t)(({summary:'overview',read:'scripture',listen:'teaching'})[TAB]||TAB),jpI=jpIdx(),NA=camp===jpI?nextAction(camp):null,SS=stepState(camp);cl.innerHTML=`<div class="where">${land}<span style="float:right;letter-spacing:0;text-transform:none;color:var(--mute)"></span></div><div class="hd"><div class="ch serif"><span id="chT">${stopName(x)}<svg class="chv" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>${hereDone?'<span class="ck-c" role="img" aria-label="Completed">✓</span>':''}</div><button class="fold" id="fold" aria-label="${fold?'Open this stop':'Fold this stop'}"><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="${fold?'M3 6l5 5 5-5':'M3 10l5-5 5 5'}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>${c.y?`<div class="yr">${c.y}</div>`:''}${lm?`<div class="scene">${lm[1]}</div>`:''}${c.sl?`<div class="sline">${rich(c.sl)}</div>`:''}<div class="next">${exploreNext(jpI)}</div>${fold?`<button class="unfold" id="unfold">${ids.length?'▸ Open · '+ids.length+' voice'+(ids.length>1?'s':''):'▸ Open this stop'}</button>`:''}<div class="body"${fold?' hidden':''}>
  <div class="tabs" role="tablist">${(c.intro?[['overview','Overview']]:[['overview','Overview'],['scripture','Scripture'],['teaching','Teaching']]).map(([k,l])=>{const st=SS[k],nx=NA&&NA.step===k,ok=camp===jpI&&st.done&&(st.n||k==='scripture')&&!c.intro;
   return `<button class="tab step${T_===k?' on':''}${nx?' nextstep':''}" role="tab" aria-selected="${T_===k}" data-tab="${k}">${l}${ok?'<i class="ok" aria-label="nothing waiting">✓</i>':k!=='scripture'&&st.n?`<span>${st.n}</span>`:''}</button>`}).join('')}<button class="tab tmap${T_==='map'?' on':''}" role="tab" aria-selected="${T_==='map'}" aria-label="Map" data-tab="map">${icon('map',18,1.7,T_==='map'?'var(--ink)':'var(--mute)')}</button></div>
  ${T_==='overview'?`<div class="pane story">${(()=>{const G=listenGroups(b,c),up=NA&&NA.kind==='play'?NA.id:null;let h='';
   if(c.intro){if(b.bm&&b.bm.length)h+=`<div class="st-t">Inside ${b.name}</div><ul>${b.bm.map(x=>`<li>${rich(x)}</li>`).join('')}</ul>`}
   else{if(c.sm&&c.sm.length)h+=`<div class="st-t">What happens in ${b.name} ${c.c}</div><ul>${c.sm.map(x=>`<li>${rich(x)}</li>`).join('')}</ul>`;
    if(b.bl)h+=`<details class="sum2" data-k="b:${b.abbr}"${OPEN.has('b:'+b.abbr)?' open':''}><summary>About the book of ${b.name} ›</summary><div class="sline" style="margin-top:6px">${rich(b.bl)}</div>${b.bm&&b.bm.length?`<ul>${b.bm.map(x=>`<li>${rich(x)}</li>`).join('')}</ul>`:''}</details>`}
   if(G.overview.length){h+=`<div class="lk-h">${c.intro?'Teaching on the book':'Teaching on the wider stretch'}</div>`;let last=null;G.overview.forEach(x=>{if(x.h!==last){h+=`<div class="sv-t">${esc(x.h)}</div>`;last=x.h}h+=vItem(x.id,'',up)})}
   return h})()}</div>`:''}
  ${T_==='scripture'?`<div class="pane"><details class="readx" open data-k="r:${b.abbr}${c.c}"><summary hidden></summary><div class="txt" data-book="${b.name}" data-ch="${c.c}"></div></details></div>`:''}
  ${T_==='teaching'?`<div class="pane">${(()=>{const G=listenGroups(b,c),up=NA&&NA.kind==='play'?NA.id:null;
   if(!G.chapter.length&&!G.verses.length)return `<div class="empty">No teaching on this chapter alone yet${G.overview.length?' — the wider stretch is under Overview':''}.${nextV?` Next teaching: <b style="color:var(--gold2);cursor:pointer" data-camp="${nextV.i}" class="nv">${stopName(nextV.x)}</b>.`:''}</div>`;
   let h='';if(G.chapter.length)h+=`<div class="lk-h">The whole chapter</div>`+G.chapter.map(x=>vItem(x.id,vbadge(x.r),up)).join('');
   if(G.verses.length){const show=decorate.more||G.verses.length<=8?G.verses:G.verses.slice(0,6);h+=`<div class="lk-h">Verse by verse</div>`+show.map(x=>vItem(x.id,vbadge(x.r),up)).join('')+(show.length<G.verses.length?`<button class="more" id="more">${G.verses.length-show.length} more ›</button>`:'')}
   return h})()}</div>`:''}
  ${T_==='map'?`<div class="pane"><div class="maptab" data-b="${b.name}" data-c="${c.c||1}">Opening the map…</div></div>`:''}
  </div><div class="acts"><button class="bk" data-camp="${Math.max(0,camp-1)}" aria-label="Back a chapter"${camp===0?' disabled':''}>‹</button>${c.intro?'':`<button class="read ${r?'on':''}" data-read="${b.abbr+c.c}">${r?'Read ✓':'Mark read'}</button>`}<button class="go2" data-camp="${Math.min(w.length-1,camp+1)}" aria-label="Next stop">${w[camp+1]?esc(stopName(w[camp+1]))+' ›':'›'}</button></div>`;
 /* swipe the stop card: left walks on, right goes back (not when the swipe starts on a scrolling row or the map) */
 {let sw=null;cl.ontouchstart=e=>{sw=null;if(e.touches.length!==1||e.target.closest('.lks,.maptab,input,textarea,select,#np'))return;const t=e.touches[0];sw={x:t.clientX,y:t.clientY,t:Date.now()}};
  cl.ontouchend=e=>{if(!sw)return;const t=e.changedTouches[0],dx=t.clientX-sw.x,dy=t.clientY-sw.y,fast=Date.now()-sw.t<800;sw=null;
   if(fast&&Math.abs(dx)>60&&Math.abs(dx)>2*Math.abs(dy)){const to=camp+(dx<0?1:-1);if(to>=0&&to<w.length){decorate.slide=dx<0?'l':'r';stepTo(to)}}}}
 if(decorate.slide){const k='in-'+decorate.slide;decorate.slide=null;cl.classList.remove('in-l','in-r');void cl.offsetWidth;cl.classList.add(k);setTimeout(()=>cl.classList.remove(k),320)}
 /* the road below the stop: tap a book name or the road to go there */
 $('#w2').onclick=e=>{const w2=$('#w2'),pt=w2.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const p=pt.matrixTransform(w2.getScreenCTM().inverse());
  const lb=(decorate.drift||[]).find(l=>l.kind==='book'&&p.y>l.y-18&&p.y<l.y+(l.yr?20:8)&&(l.side==='L'?p.x>l.x-6&&p.x<l.x+150:p.x<l.x+6&&p.x>l.x-150));
  if(lb){go(lb.idx);return}let best=0,bd=1e12;for(let i=0;i<w.length;i++){const q=at(i),dd=(q.x-p.x)**2+(q.y-p.y)**2;if(dd<bd){bd=dd;best=i}}if(bd<60*60)go(best)};
 $('#bookhd').textContent=b.name+(bookN===b.ch.length?' ✓':'');$('#bookhd').dataset.camp=w.findIndex(x=>x.b===b);
 // camera: keep you ~30% from top
 if(!decorate.moving&&(decorate.follow||decorate.first)){const y=m.y*sc+$('#world').offsetTop-window.innerHeight*0.30;window.scrollTo({top:Math.max(0,y),behavior:decorate.first?'auto':'smooth'})}decorate.first=false;decorate.follow=false
 $('#hit').onclick=e=>{const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const p=pt.matrixTransform(svg.getScreenCTM().inverse());let best=0,bd=1e12;for(let i=0;i<w.length;i++){const q=at(i),dd=(q.x-p.x)**2+(q.y-p.y)**2;if(dd<bd){bd=dd;best=i}}go(best)};
 document.querySelectorAll('.bl[data-camp], #labels g[data-camp]').forEach(t=>t.onclick=e=>{e.stopPropagation();go(+t.dataset.camp)})}
let LK=['overview','chapter','verses'].includes(S.get('lk2','overview'))?S.get('lk2','overview'):'overview',FOLD=false,TAB=(t=>({summary:'overview',read:'scripture',listen:'teaching'})[t]||(['overview','scripture','teaching','map'].includes(t)?t:'overview'))(S.get('tab','overview'));  /* folding is for this stop only; every stop (and every app open) starts with its voices showing */
function go(i){if(view==='journey'&&JZ==='road'){roadPick(i);return}{const w=walk(),here=camp!=null&&w[camp];if(here&&here.c.intro&&i>camp&&!read[here.b.abbr+'0']){read[here.b.abbr+'0']=true;S.set('read',read)}}camp=i;FOLD=false;decorate.more=false;decorate.follow=true;S.set('camp',camp);if(i===jpIdx()){const a=nextAction(i);if(a&&a.step){TAB=a.step;S.set('tab',TAB)}}render()}
/* one step along the road: from your place that is walking on; anywhere else it is just looking */
function stepTo(to){go(to)}
function bkForm(again){return `<form id="bkf" class="bkf" autocomplete="on"><input type="text" name="username" autocomplete="username" value="Scripture Companion backup" readonly class="bk-u" tabindex="-1" aria-hidden="true"><input type="password" name="password" id="bkkey" autocomplete="current-password" placeholder="${again?'Paste a new GitHub key':'Paste your GitHub key'}" required><input type="text" id="bkrepo" value="${esc(bkRepo())}" aria-label="Backup repo (owner/name)" autocapitalize="off" spellcheck="false"><button class="btn" type="submit">${again?'Use this key':'Turn on backup'}</button><p class="note" id="bkmsg"></p></form>`}
function settingsView(){
 return `<div class="settings"><button class="sccard" id="opensc"><span class="serif">Secret Church</span><small>${scGroups().length} nights · every session in order ›</small></button><h2 class="serif" style="margin:0 0 8px">Your journey</h2><p class="note">${(()=>{const w=walk(),j=jpIdx(),rd=w.filter(x=>!x.c.intro&&read[scrKey(x)]).length,hh=Math.round(Object.values(prog).reduce((a,v)=>a+(v&&v.heard||0),0)/3600),sk=Object.keys(SKIP).length;
  return `You are at <b>${esc(stopName(w[j]))}</b>${rd?`, with ${rd.toLocaleString()} chapter${rd>1?'s':''} of Scripture read`:''}${hh?` and ${hh.toLocaleString()} hour${hh>1?'s':''} of teaching heard`:''}.</p><p class="note">Each stop on the road has three steps: an <b>Overview</b> (the book, or a stretch of chapters), the <b>Scripture</b> itself to read or hear, and <b>Teaching</b>: the whole chapter first, then verse by verse. Continue always offers the next one. A teaching that covers several chapters waits at the first of them, and the next chapter waits for you.${sk?` <button class="lnk" id="unskip">Bring back the ${sk} you skipped</button>`:''}`})()}</p>
 <p>
 <span class="btn" id="who" style="display:inline-block;cursor:pointer">Voices: ${cfg.who?NAMES[cfg.who]+' only':'everyone'} — switch</span></p>
 <p class="note">Bible text: Berean Standard Bible (public domain). People, places and family links adapted from Theographic Bible Metadata (CC BY-SA 4.0). Map: Natural Earth (public domain).</p><h2 class="serif" style="margin:22px 0 8px">Backup</h2>${bkOn()?`<p class="note" id="bkst">${bkStatus()}</p><button class="btn" id="bknow">Back up now</button><button class="btn" id="bkrest">Restore from backup</button><button class="btn" id="bkoff">Turn off</button>${BK.err?bkForm(true):''}`:`<p class="note">Your progress lives only on this phone. Turn on backup and it saves itself to a private GitHub repo you own; on a new phone, paste the same key and everything comes back.</p>
 <ol class="note bk-steps"><li><a href="https://github.com/new?name=scripture-companion-backup&visibility=private" target="_blank" rel="noopener">Create the private repo</a> (name and Private are filled in: tap <b>Create repository</b>).</li><li><a href="https://github.com/settings/personal-access-tokens/new?name=Scripture%20Companion%20backup&description=Lets%20the%20app%20save%20listening%20progress&expires_in=none&contents=write" target="_blank" rel="noopener">Make a key</a>: under <b>Repository access</b> pick <b>Only select repositories</b> → scripture-companion-backup; check <b>Contents: Read and write</b>; tap <b>Generate</b> and copy it.</li><li>Paste it here. Your iPhone offers to save it in Passwords, so a new phone fills it in.</li></ol>${bkForm(false)}`}
 <p class="note" style="margin-top:18px">By hand:</p><button class="btn" id="exp">Export</button><button class="btn" id="imp">Import</button><button class="btn" id="reset">Reset</button><textarea id="io" placeholder="Exported progress appears here; paste here to import."></textarea>
 <p class="note" id="envn">${location.protocol==='file:'||window!==window.top?'This viewer blocks audio. Serve the file from a web address and open it in Safari, then Add to Home Screen.':'Audio should stream here.'} <button class="btn" id="atest" style="padding:4px 10px">Test audio</button><span id="atest-out"></span></p>
 <button class="btn" id="back">‹ Back to the road</button></div>`}
/* Secret Church library: every night, every session, in order (the podcast's sessions where it has them) */
function scGroups(){const by={};D.sc.ids.forEach(id=>{const i=I[id];if(!i||!i.sc)return;(by[i.sc[0]]=by[i.sc[0]]||[]).push(id)});
 return D.sc.events.map(ev=>{let ids=by[ev.n]||[];const pod=ids.filter(id=>I[id].src==='secret_church_podcast');if(pod.length)ids=pod;
  return {ev,ids:ids.slice().sort((a,b)=>(I[a].sc[1]||0)-(I[b].sc[1]||0))}}).filter(g=>g.ids.length)}
function scSeq(){return scGroups().flatMap(g=>g.ids).filter(id=>I[id].audio)}
function scView(){const G=scGroups(),tot=G.reduce((a,g)=>a+g.ids.length,0);
 let h=`<div class="settings scl"><button class="btn" id="scback">‹ Library</button><h2 class="serif" style="margin:14px 0 4px">Secret Church</h2>
 <p class="note">David Platt · ${G.length} nights of deep teaching, ${tot} sessions, in order. Sessions that teach a stretch of the Bible also sit on the road.</p>`;
 G.forEach(({ev,ids})=>{const done=ids.filter(isDone).length,k='sc:'+ev.n;
  h+=`<details class="sce" data-sck="${k}"${OPEN.has(k)?' open':''}><summary><span class="sce-n">${ev.n}</span><span class="sce-t">${esc(ev.title)}</span><span class="sce-p">${done===ids.length?'✓':done+' / '+ids.length}</span></summary><div class="sce-b">${ids.map(id=>voiceHTML(id,(I[id].sc||[])[0]+'.'+(I[id].sc||[])[1])).join('')}</div></details>`});
 return h+'</div>'}
/* player */
function spdLabel(){return (speed%1?speed.toFixed(2).replace(/0$/,''):speed)+'×'}
let audio=$('#audio');const AUDIO_EL=[$('#audio'),$('#audiofx')];let cur=null,speed=S.get('speed',1);AUDIO_EL.forEach(a=>a.playbackRate=speed);
/* events from whichever player is active (the other one is idle) */
function onAudio(type,fn){AUDIO_EL.forEach(el=>el.addEventListener(type,e=>{if(el===audio)fn(e)}))}
/* ---- Even out volume: the leveler listens as audio plays and steers every episode to one level (loud ones down,
   quiet ones up, within ±10 dB, slowly so speech never pumps; pauses between words are ignored), then a gentle
   limiter catches peaks. Only for hosts that allow the browser to process their audio (CORS). ---- */
const LEVEL_SRC=new Set(['davey_wfth','davey_journey','davey_sermons','platt_messages','ptw','secret_church_podcast','mclean_podcast','mclean_oceans','brookhills','brookhills_archive','mclean_api']);
let AC=null,LVG=null,LVA=null,lvl=null,lvlFast=0;
function levelOn(){return S.get('level',true)!==false}
function levelFor(i){return false}  // leveler turned off: every episode plays straight through the plain audio element
function leveler(){if(AC)return AC;try{AC=new (window.AudioContext||window.webkitAudioContext)();try{if(navigator.audioSession)navigator.audioSession.type='playback'}catch(e){}
  const src=AC.createMediaElementSource($('#audiofx')),g=AC.createGain(),an=AC.createAnalyser(),cp=AC.createDynamicsCompressor();
  an.fftSize=2048;cp.threshold.value=-12;cp.knee.value=8;cp.ratio.value=4;cp.attack.value=.005;cp.release.value=.2;
  src.connect(an);src.connect(g);g.connect(cp);cp.connect(AC.destination);LVG=g;LVA=an;const buf=new Float32Array(an.fftSize),TARGET=-21;
  setInterval(()=>{if(audio!==$('#audiofx')||audio.paused)return;an.getFloatTimeDomainData(buf);let q=0;for(let k=0;k<buf.length;k++)q+=buf[k]*buf[k];
   const db=10*Math.log10(q/buf.length+1e-12);if(db<-48)return;const a=lvlFast>0?.25:.03;lvlFast=Math.max(0,lvlFast-1);lvl=lvl==null?db:lvl+(db-lvl)*a;
   const want=Math.max(-10,Math.min(10,TARGET-lvl));g.gain.setTargetAtTime(Math.pow(10,want/20),AC.currentTime,lvlFast>0?.3:2)},100)}catch(e){AC=null}return AC}
function useAudioFor(i){const fx=levelFor(i)&&leveler(),want=fx?$('#audiofx'):$('#audio');if(fx&&AC.state!=='running')AC.resume().catch(()=>{});
 if(want!==audio){try{audio.pause()}catch(e){}audio=want;audio.playbackRate=speed}if(fx){lvl=null;lvlFast=40}}$('#spd').textContent=spdLabel();
function where(id){if(I[id]&&I[id].nar)return I[id].nar.book+' '+I[id].nar.c;for(const b of D.books){if(b.ov.includes(id)||(b.spans||[]).some(x=>x.id===id))return b.name;for(const c of b.ch)if(c.ids.includes(id))return b.name+' '+c.c}return ''}
function play(id,o={}){const i=I[id];if(!i.audio)return;let wait=false;if(cur!==id){cur=id;NP().classList.toggle('reading',!!i.nar);$('.np-lab').textContent=i.nar?'Reading':'Now playing';if(!i.nar)NAR=null;ready=false;const p=i.nar?{}:prog[id]||{},saved=p.pos||0;useAudioFor(i);const meta=()=>{const st=i.s||0;if(i.nar){if(narAt)audio.currentTime=narAt;narAt=null;narRetry=0;ready=true;narMark(true);return}if(saved&&saved>st&&saved<audio.duration-5)audio.currentTime=saved;else if(st&&st<audio.duration-30)audio.currentTime=st;ready=true};const setSrc=u=>{audio.src=u;narWait=false;audio.addEventListener('loadedmetadata',meta,{once:true})};if(!i.nar)setSrc(i.audio);else if(NB[id]&&NB[id].u)setSrc(NB[id].u);else{narWait=true;wait=true;if(audio.src!==SILENT)try{audio.pause()}catch(e){}$('#cur').textContent='Loading…';narBlob(id).then(u=>{if(cur!==id)return;setSrc(u);if(!o.load)audio.play().catch(()=>{})}).catch(()=>{if(cur!==id)return;narWait=false;$('#np-s').textContent='This chapter did not load — check your connection and tap play.'})}  /* fresh plays start after the intro */
  $('#np-t').textContent=dispTitle(i);$('#np-s').textContent=i.nar?'\u00a0':teacher(i)+' · '+where(id);npArt(id);if(!NP().classList.contains('on')){NP().classList.add('on');setMini(!!i.nar&&!o.full)}else if(o.full)setMini(false);if(i.nar)readerFill(true);setPP();
  if('mediaSession' in navigator){navigator.mediaSession.metadata=new MediaMetadata({title:i.t,artist:teacher(i),album:where(id)});['play',()=>audio.play().catch(()=>{}),'pause',()=>audio.pause(),'seekbackward',()=>audio.currentTime-=10,'seekforward',()=>audio.currentTime+=10,'nexttrack',()=>skipTrack(1),'previoustrack',()=>skipTrack(-1)].reduce((a,v,k,arr)=>{if(k%2===0)navigator.mediaSession.setActionHandler(v,arr[k+1]);return a},0)}}
 if(o.load||wait)return;audio.paused?audio.play().catch(()=>{}):audio.pause()}
function next(){if(BPM&&cur){const s=bpGet(BPM),ids=s?bpIds(s):[],k=ids.indexOf(cur);if(k>=0){if(k+1<ids.length)bpPlay(s.id,ids[k+1]);else{BPM=null;note('That is the end of '+s.title+'.')}render();return}BPM=null}
 if(cur&&I[cur].sc&&scSeq().includes(cur)){const q=scSeq();for(let j=q.indexOf(cur)+1;j<q.length;j++)if(!isDone(q[j])&&okWho(q[j])){play(q[j]);return}return}
 if(JM){const i=jpIdx(),a=nextAction(i),here=camp===i;
  if(a.kind==='play'){if(here){TAB=a.step;S.set('tab',TAB)}play(a.id);if(here){decorate.moving=true;render();decorate.moving=false}return}
  if(a.kind==='scripture'){const x=walk()[i];if(hasNar(x.b.abbr,x.c.c)){if(here){TAB='scripture';S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false}narPlay(x.b,x.c.c,0,{jm:true});return}}
  JM=false;decorate.moving=true;render();decorate.moving=false;if(a.kind==='walk')note('That is everything waiting in '+stopName(walk()[i])+'. Walk on when you’re ready.');return}
 const w=walk(),x=w[PLAYSTOP!=null?PLAYSTOP:camp];if(!x)return;const ids=orderedIds(x.b,x.c),k=ids.indexOf(cur);if(k<0)return;
 for(let j=k+1;j<ids.length;j++)if(I[ids[j]].audio&&!isDone(ids[j])&&okWho(ids[j])&&!SKIP[ids[j]]){play(ids[j]);return}}
let saveSec=-1;onAudio('timeupdate',()=>{if(!cur||narWait)return;const d=audio.duration||0,t=audio.currentTime;{const hl=$('#np-hl i');if(hl)hl.style.width=(d?Math.min(100,100*t/d):0)+'%'}$('#seek').value=d?1000*t/d:0;$('#cur').textContent=fmt(t);$('#rem').textContent='-'+fmt(Math.max(0,d-t-tail())/speed);
 if(tail()&&d&&d-t<=tail()&&!audio.paused&&!audio.seeking&&ready){audio.pause();finished();return}/* the outro after the last word: done */
 if(I[cur].nar){if(!ready)return;narMark();if(d&&d-t<45)narPrefetch();const sec=Math.floor(t);if(sec%5===0&&sec!==saveSec){saveSec=sec;const pos=S.get('narpos',{});pos[cur]=t;S.set('narpos',pos)}return}
 if(!ready)return;const p=prog[cur]=Object.assign(prog[cur]||{},{dur:d});
 if(lastT!==null&&!audio.paused&&!audio.seeking){const dt=t-lastT;if(dt>0&&dt<4)p.heard=Math.min(d||Infinity,(p.heard||0)+dt)}lastT=t;
 const wasDone=!!p.done;if(d&&p.heard>=DONE_AT*body(cur))p.done=true;const nowDone=!!p.done,sec=Math.floor(t);
 if((sec%5===0&&sec!==saveSec)||nowDone!==wasDone){saveSec=sec;p.pos=t;p.at=Date.now();S.set('prog',prog);if(nowDone!==wasDone)render()}});
onAudio('seeking',()=>{lastT=null});onAudio('play',()=>{lastT=null});
function finished(){if(narWait)return;if(cur&&I[cur].nar){narNext();return}const p=prog[cur]=Object.assign(prog[cur]||{},{pos:0});if(p.dur&&p.heard>=DONE_AT*body(cur))p.done=true;S.set('prog',prog);render();next()}
onAudio('ended',finished);
const setPP=()=>{$('#pp').innerHTML=icon(audio.paused?'play':'pause',28,0,'#1b2440')};setPP();/* play/pause only changes the play buttons: update them in place so the page (and an open reading) never re-lays out */
function refreshVoices(){contRefresh();if(view==='journey'||view==='bigpicture'){cancelAnimationFrame(refreshVoices.r);refreshVoices.r=requestAnimationFrame(()=>{const y=scrollY;render();window.scrollTo(0,y)})}document.querySelectorAll('.pb[data-play]').forEach(b=>{const id=b.dataset.play,i=I[id],playing=String(cur)===id&&!audio.paused,deg=!isDone(id)?Math.round(3.6*heardPct(id)):0;
 b.classList.toggle('playing',playing);b.style.setProperty('--p',deg+'deg');b.innerHTML=`<span style="color:${playing?'var(--gold2)':'var(--ink)'}">${icon(playing?'pause':'play',18,0,'currentColor')}</span>`})}
onAudio('play',()=>{setPP();refreshVoices();narBar()});onAudio('pause',()=>{setPP();refreshVoices();narBar()});
$('#audiofx').addEventListener('error',()=>{if(audio!==$('#audiofx')||!cur)return;const t=audio.currentTime||0,src=audio.src;audio=$('#audio');audio.playbackRate=speed;audio.src=src;audio.addEventListener('loadedmetadata',()=>{try{audio.currentTime=t}catch(e){}},{once:true});audio.play().catch(()=>{})});
onAudio('error',()=>{if(narWait)return;if(cur&&I[cur].nar&&narRetry<3){narRetry++;const id=cur,t=audio.currentTime||narAt||0;if(NB[id]){if(NB[id].u)URL.revokeObjectURL(NB[id].u);delete NB[id]}narBlob(id).then(u=>{if(cur!==id)return;audio.src=u;audio.addEventListener('loadedmetadata',()=>{try{audio.currentTime=t}catch(e){}},{once:true});audio.play().catch(()=>{})}).catch(()=>{});return}$('#np-s').textContent=(location.protocol==='file:'||window!==window.top)?'Audio is blocked in this viewer — open in Safari from a web address.':'This file did not load.'});
$('#pp').onclick=()=>cur&&(audio.paused?audio.play().catch(()=>{}):audio.pause());$('#bk').onclick=()=>audio.currentTime-=10;$('#fw').onclick=()=>audio.currentTime+=10;
$('#seek').oninput=e=>{if(audio.duration)audio.currentTime=audio.duration*e.target.value/1000};
const setSpeed=v=>{speed=Math.round(Math.min(3,Math.max(0.5,v))*100)/100;AUDIO_EL.forEach(a=>a.playbackRate=speed);$('#spd').textContent=spdLabel();S.set('speed',speed);retime()};
function retime(){document.querySelectorAll('[data-dur]').forEach(e=>e.textContent=durTxt(+e.dataset.dur));document.querySelectorAll('[data-hrs]').forEach(e=>{const [h,a]=e.dataset.hrs.split(',').map(Number);e.textContent=hrsTxt(h,a)});if(cur&&audio.duration)$('#rem').textContent='-'+fmt(Math.max(0,audio.duration-audio.currentTime-tail())/speed)}$('#spd').onclick=e=>{e.stopPropagation();if(NP().classList.contains('mini')){const L=[.7,.8,.9,1,1.25,1.5,1.75,2],k=L.findIndex(v=>Math.abs(v-speed)<.01);setSpeed(L[(k+1)%L.length]);return}setSpeed(1)};$('#spd-dn').onclick=e=>{e.stopPropagation();setSpeed(speed-0.05)};$('#spd-up').onclick=e=>{e.stopPropagation();setSpeed(speed+0.05)};
let zz=0,zzT=null;$('#zz').onclick=()=>{const m=[0,15,30,60];zz=m[(m.indexOf(zz)+1)%m.length];$('#zz').textContent=zz?'Sleep '+zz+'m':'Sleep off';clearTimeout(zzT);if(zz)zzT=setTimeout(()=>{audio.pause();zz=0;$('#zz').textContent='Sleep off'},zz*60000)};
$('#prv').onclick=e=>{e.stopPropagation();skipTrack(-1)};$('#nxt').onclick=e=>{e.stopPropagation();skipTrack(1)};$('#np-min').onclick=e=>{e.stopPropagation();setMini(true)};
$('#cls').onclick=e=>{e.stopPropagation();audio.pause();audio.removeAttribute('src');audio.load();cur=null;NAR=null;document.querySelectorAll('.vs.now').forEach(e=>e.classList.remove('now'));narBar();NP().classList.remove('on');roomForPlayer();render()};
/* player sheet: swipe down or tap the page to shrink it to a bar; tap or swipe up the bar to open it */
function NP(){return $('#np')}
function roomForPlayer(){requestAnimationFrame(()=>{const np=NP(),tb=($('#tabs')||{}).offsetHeight||0;document.body.classList.toggle('npon',np.classList.contains('on')&&np.classList.contains('mini'));if(!np.classList.contains('on')){document.documentElement.style.setProperty('--npH','0px');document.body.style.paddingBottom=tb+'px';return}const mh=np.classList.contains('mini')?np.offsetHeight+16:0;document.documentElement.style.setProperty('--npH',mh+'px');document.body.style.paddingBottom=(tb+mh)+'px'})}
/* the full-screen player's cover: the passage on the teacher's colour, with their medallion mark */
const ART_C={Platt:['#1b2440','#3b5578'],PAM:['#4a1f3a','#8a3b5c'],Davey:['#1f3b33','#3f6b5a'],Skip:['#5a3417','#a8662e'],Fearless:['#2c2f36','#8a6a2a']};
function npArt(id){const i=I[id],c=ART_C[i.who]||['#1b2440','#a8812a'],d=i.date?new Date(i.date+'T12:00:00'):null;
 $('#np-art').style.background=`linear-gradient(150deg,${c[1]},${c[0]})`;
 $('#np-art').innerHTML=`<svg class="a-m" viewBox="0 0 48 48"><path d="${MEDAL_ICON[{Platt:'apostle',PAM:'prophet',Davey:'writer',Skip:'patriarch'}[i.who]]||''}" fill="none" stroke="#fff" stroke-width="2"/></svg><div class="a-w">${esc(teacher(i))}</div><div class="a-p">${esc(where(id))}</div>${i.show?`<div class="a-s">${esc(i.show)}</div>`:''}`;
 $('#np-d').textContent=[d&&!isNaN(d)?d.toLocaleDateString('en-US',{month:'long',day:'numeric',year:'numeric'}):'',i.show||''].filter(Boolean).join(' · ')}
/* previous / next teaching along the road (manual: every teaching in order; ⏮ restarts first if you are past 5 s) */
function skipTrack(dir){if(BPM&&cur&&!(I[cur]&&I[cur].nar)){const s=bpGet(BPM),ids=s?bpIds(s):[],j=ids.indexOf(cur)+dir;if(dir<0&&audio.currentTime>5){audio.currentTime=(I[cur]&&I[cur].s)||0;return}if(ids.includes(cur)){if(j>=0&&j<ids.length)bpPlay(s.id,ids[j]);return}}if(cur&&I[cur].nar&&NAR&&NAR.id===cur){narStep(dir);return}if(dir<0&&audio.currentTime>5&&cur){audio.currentTime=(I[cur]&&I[cur].s)||0;return}
 if(cur&&I[cur].sc&&scSeq().includes(cur)){const q=scSeq(),j=q.indexOf(cur)+dir;if(j>=0&&j<q.length){const np=NP();np.classList.remove('sw-l','sw-r');void np.offsetWidth;np.classList.add(dir>0?'sw-l':'sw-r');play(q[j])}return}
 const w=walk(),seq=[],start=[];w.forEach((x,i)=>{start[i]=seq.length;seq.push(...orderedIds(x.b,x.c))});
 let k=cur?seq.indexOf(cur,start[Math.max(0,Math.min(camp==null?0:camp,w.length-1))]):-1;if(k<0&&cur)k=seq.indexOf(cur);
 for(let j=k+dir;j>=0&&j<seq.length;j+=dir){const id=seq[j];if(id!==cur&&I[id].audio&&okWho(id)){const np=NP();np.classList.remove('sw-l','sw-r');void np.offsetWidth;np.classList.add(dir>0?'sw-l':'sw-r');setTimeout(()=>np.classList.remove('sw-l','sw-r'),320);play(id);return}}}
/* ---- the Bible read aloud (Alistair): one recording per chapter, with where each verse starts ---- */
const NARR=D.narr||{},NRAW='https://raw.githubusercontent.com/zreynard/scripture-companion/narration-audio/',NT={},NB={},SILENT='data:audio/mpeg;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//OEwAAAAAAAAAAAAEluZm8AAAAPAAAABwAAA2AAVVVVVVVVVVVVVVVVVVVxcXFxcXFxcXFxcXFxcY6Ojo6Ojo6Ojo6Ojo6Oqqqqqqqqqqqqqqqqqqqqx8fHx8fHx8fHx8fHx8fj4+Pj4+Pj4+Pj4+Pj4///////////////////AAAAAExhdmM2MC4zMQAAAAAAAAAAAAAAACQEIAAAAAAAAANgmVBi7QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//NExAAAAANIAAAAAExBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExFMAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKYAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NExKwAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NExKwAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV';let NAR=null,narAt=null,narV=null,narUser=0,narRetry=0,narWait=false,narPre=null;
/* GitHub sends the chapter as a plain download, which iPhones will not play as a stream: fetch it, then play it as audio */
function narBlob(id){const e0=NB[id];if(e0)return e0.p;const ks=Object.keys(NB);for(const k of ks.slice(0,Math.max(0,ks.length-3)))if(k!==cur&&NB[k].u){URL.revokeObjectURL(NB[k].u);delete NB[k]}
 const e=NB[id]={};e.p=fetch(I[id].audio).then(r=>{if(!r.ok)throw 0;return r.blob()}).then(b=>e.u=URL.createObjectURL(new Blob([b],{type:'audio/mpeg'}))).catch(x=>{delete NB[id];throw x});return e.p}
/* a tap may have to wait for the download: play a moment of silence right away so the phone lets the chapter play when it arrives */
function narUnlock(){const a=$('#audio');if(a.dataset.ok)return;try{a.src=SILENT;a.play().then(()=>{a.dataset.ok=1}).catch(()=>{})}catch(e){}}
function narPrefetch(){if(!NAR||narPre===NAR.id)return;narPre=NAR.id;const nx=narAfter(NAR.b,NAR.c);if(nx)narTimes(nx[0].abbr).then(()=>narBlob(narItem(nx[0],nx[1]))).catch(()=>{})}
function hasNar(abbr,c){const n=NARR[abbr];return !!n&&n.c.includes(c)}
function narId(abbr,c){return 'nar:'+abbr+':'+c}
function narDur(abbr,c){const n=NARR[abbr];return n&&n.d?n.d[n.c.indexOf(c)]||0:0}
function narTimes(abbr){return NT[abbr]||(NT[abbr]=fetch('narration/'+abbr+'.json').then(r=>{if(!r.ok)throw 0;return r.json()}).catch(e=>{delete NT[abbr];throw e}))}
function narItem(b,c){const id=narId(b.abbr,c);if(!I[id])I[id]={id,t:b.name+' '+c,audio:NRAW+b.abbr+'_'+String(c).padStart(3,'0')+'.mp3',who:'Alistair',by:'The Bible',nar:{abbr:b.abbr,c,book:b.name}};return id}
/* start chapter c of book b: at verse v, from the top (v=0), or where it was left (v=null) */
function narPlay(b,c,v,o={}){if(!o.jm)JM=false;if(!o.load&&cur!==narId(b.abbr,c)&&!NB[narId(b.abbr,c)]?.u){narWait=true;narUnlock()}narTimes(b.abbr).then(T=>{const ch=T.c[String(c)];if(!ch)return;const id=narItem(b,c),pos=S.get('narpos',{});
  NAR={b,c,id,m:ch.v};const at=v===0?0:v?((ch.v.find(m=>m[0]===v)||ch.v[0])[1]):(pos[id]&&pos[id]<ch.d-3?pos[id]:0);narV=null;
  if(cur===id){audio.currentTime=at;if(!o.load&&audio.paused)audio.play().catch(()=>{});if(o.full)setMini(false);readerFill(true);return}narAt=at;play(id,o)}).catch(()=>{narWait=false})}
/* verses are taps: start reading there */
function wireVerses(el,b,c){el.querySelectorAll('.vs').forEach(v=>v.onclick=e=>{if(e.target.closest('button,a,[data-nk]'))return;const sel=getSelection&&getSelection();if(sel&&String(sel).length)return;e.stopPropagation();narPlay(b,c,+v.dataset.v)})}
/* the full reader: the chapter being read, then the next ones as you scroll (read straight on, as long as you like) */
function chAfter(b,c){if(c<b.ch.length)return [b,c+1];const i=D.books.indexOf(b);return i>=0&&i+1<D.books.length?[D.books[i+1],1]:null}
function chBefore(b,c){if(c>1)return [b,c-1];const i=D.books.indexOf(b);return i>0?[D.books[i-1],D.books[i-1].ch.length]:null}
function readerSec(b,c,first){return loadBook(b.name).then(d=>{const sec=document.createElement('section');sec.dataset.k=b.abbr+c;
  sec.innerHTML=`<h3 class="rc${first?' first':''}">${esc(b.name)} ${c}</h3><div class="txt${hasNar(b.abbr,c)?' narr':''}" data-book="${esc(b.name)}" data-ch="${c}">${chapterBody(d,c,null)}</div>`;
  if(hasNar(b.abbr,c))wireVerses(sec.querySelector('.txt'),b,c);return sec})}
let RD={busy:false,first:null,last:null};
function readerFill(reset){const box=$('#np-read');if(!NAR||!box)return;const key=NAR.b.abbr+NAR.c;
 if(reset&&!box.querySelector(`section[data-k="${key}"]`)){if(RD.loading===key)return;box.innerHTML='';RD={busy:true,loading:key,first:[NAR.b,NAR.c],last:[NAR.b,NAR.c]};
  readerSec(NAR.b,NAR.c,true).then(sec=>{if(RD.loading!==key)return;RD.loading=null;box.innerHTML='';box.appendChild(sec);const pv=chBefore(NAR.b,NAR.c);if(pv){const bt=document.createElement('button');bt.className='rprev';bt.textContent='↑ '+pv[0].name+' '+pv[1];bt.onclick=e=>{e.stopPropagation();readerPrev(bt)};box.prepend(bt)}
   RD.busy=false;narMark(true);readerMore()}).catch(()=>{RD.busy=false});return}
 readerMore()}
function readerMore(){const box=$('#np-read');if(RD.busy||!RD.last||!box.clientHeight||box.scrollHeight-box.scrollTop-box.clientHeight>900)return;const nx=chAfter(...RD.last);if(!nx)return;RD.busy=true;
 readerSec(...nx).then(sec=>{box.appendChild(sec);RD.last=nx;RD.busy=false;readerMore()}).catch(()=>{RD.busy=false})}
function readerPrev(bt){const pv=chBefore(...RD.first);if(!pv)return;const box=$('#np-read');readerSec(...pv).then(sec=>{const h0=box.scrollHeight;box.querySelectorAll('.rc.first').forEach(h=>h.classList.remove('first'));bt.after(sec);RD.first=pv;box.scrollTop+=box.scrollHeight-h0;
 const p2=chBefore(...pv);if(p2)bt.textContent='↑ '+p2[0].name+' '+p2[1];else bt.remove()})}
$('#np-read').addEventListener('scroll',()=>{narUser=Date.now();readerMore()},{passive:true});
function narNow(){if(!NAR)return null;const t=audio.currentTime+.05;let k=-1;for(let j=0;j<NAR.m.length;j++){if(NAR.m[j][1]<=t)k=j;else break}return k}
function narEls(v){return [...document.querySelectorAll(`.txt[data-book="${CSS.escape(NAR.b.name)}"][data-ch="${NAR.c}"] .vs[data-v="${v}"]`)]}
function narMark(force){if(!NAR||!cur||cur!==NAR.id)return;const k=narNow(),v=k>=0?NAR.m[k][0]:null;if(v===narV&&!force)return;narV=v;
 document.querySelectorAll('.vs.now').forEach(e=>e.classList.remove('now'));$('#np-t').textContent=NAR.b.name+' '+NAR.c;if(v==null)return;const els=narEls(v);els.forEach(e=>e.classList.add('now'));
 $('#np-s').textContent='Verse '+v;if(Date.now()-narUser<5000||(audio.paused&&!force))return;
 const full=NP().classList.contains('on')&&!NP().classList.contains('mini'),box=$('#np-read');
 if(full){const el=els.find(e=>box.contains(e));if(!el){readerFill(true);return}const r=el.getBoundingClientRect(),b=box.getBoundingClientRect();if(force||r.top<b.top+10||r.bottom>b.bottom-30)box.scrollTo({top:box.scrollTop+r.top-b.top-b.height/4,behavior:force?'auto':'smooth'});return}
 const el=els.find(e=>!box.contains(e));if(!el)return;const r=el.getBoundingClientRect(),bottom=innerHeight-(NP().classList.contains('on')?NP().offsetHeight:0);if(r.top<70||r.bottom>bottom-20)window.scrollTo({top:scrollY+r.top-Math.max(90,(bottom-r.height)/3),behavior:'smooth'})}
function narBar(){document.querySelectorAll('[data-narplay]').forEach(b=>{const el=b.closest('.txt'),on=NAR&&cur===NAR.id&&el&&el.dataset.book===NAR.b.name&&+el.dataset.ch===NAR.c&&!audio.paused;b.innerHTML=icon(on?'pause':'play',16,0,'#fff')+`<b>${on?'Pause':'Listen'}</b>`})}
['touchmove','wheel'].forEach(t=>addEventListener(t,()=>{narUser=Date.now()},{passive:true}));
/* the header: a solid bar once the page scrolls (so text never shows through the buttons); it slides away while
   reading down and comes back on the slightest scroll up */
(()=>{let y0=scrollY;addEventListener('scroll',()=>{const y=scrollY,dy=y-y0;document.body.classList.toggle('scrolled',y>24);
 if(y<120||dy<-6)document.body.classList.remove('hidehd');else if(dy>6)document.body.classList.add('hidehd');if(Math.abs(dy)>6)y0=y},{passive:true})})();
/* the arrows step a verse at a time; back first returns to the start of the verse being read */
function narStep(dir){const k=narNow();if(dir<0){const t0=k>=0?NAR.m[k][1]:0;audio.currentTime=(k>=0&&audio.currentTime-t0>1.5)?t0:(k>0?NAR.m[k-1][1]:0);return}
 if(k+1<NAR.m.length)audio.currentTime=NAR.m[k+1][1];else narNext()}
/* the next chapter read aloud, across books */
function narAfter(b,c){if(hasNar(b.abbr,c+1))return [b,c+1];const i=D.books.findIndex(x=>x.name===b.name);for(let j=i+1;j<D.books.length;j++)if(hasNar(D.books[j].abbr,1))return [D.books[j],1];return null}
function narNext(){const was=NAR;if(!was)return;read[was.b.abbr+was.c]=true;S.set('read',read);const pos=S.get('narpos',{});delete pos[was.id];S.set('narpos',pos);
 if(JM){const x=walk()[jpIdx()];if(x&&!x.c.intro&&x.b.name===was.b.name&&x.c.c===was.c){next();return}JM=false}
 const nx=narAfter(was.b,was.c);if(!nx){render();return}const w=walk(),here=w[camp];
 if(here&&!here.c.intro&&here.b.name===was.b.name&&here.c.c===was.c){const k=w.findIndex(x=>!x.c.intro&&x.b.name===nx[0].name&&x.c.c===nx[1]);if(k>=0){TAB='scripture';S.set('tab',TAB);go(k)}}else render();
 narPlay(nx[0],nx[1],0)}
let fullAtScroll=0;
function setMini(m){NP().classList.toggle('mini',m);if(!m)fullAtScroll=scrollY;roomForPlayer();if(!m&&NAR&&cur===NAR.id){narUser=0;readerFill(true);setTimeout(()=>narMark(true),60)}}
(()=>{const np=NP();let y0=null,x0=0,dy=0,dx=0,tb=null,bx=0,by=0;
 /* buttons act the moment the finger lifts: an iPhone can drop the click while the reader moves, and a button press never drags the player */
 np.addEventListener('touchstart',e=>{tb=e.target.closest('button');if(tb){bx=e.touches[0].clientX;by=e.touches[0].clientY}},{passive:true});
 np.addEventListener('touchmove',e=>{if(tb&&Math.hypot(e.touches[0].clientX-bx,e.touches[0].clientY-by)>12)tb=null},{passive:true});
 np.addEventListener('touchend',e=>{const b=tb;tb=null;if(!b||b.disabled)return;if(e.cancelable)e.preventDefault();b.click()});
 np.addEventListener('touchcancel',()=>{tb=null});
 np.addEventListener('touchstart',e=>{if(e.target.closest('input,button')||(e.target.closest('#np-read')&&!np.classList.contains('mini')))return;y0=e.touches[0].clientY;x0=e.touches[0].clientX;dy=0;dx=0;np.style.transition='none'},{passive:true});
 np.addEventListener('touchmove',e=>{if(y0===null)return;dy=e.touches[0].clientY-y0;dx=e.touches[0].clientX-x0;if(!np.classList.contains('mini')&&dy>0&&Math.abs(dy)>Math.abs(dx))np.style.transform=`translateY(${dy}px)`},{passive:true});
 np.addEventListener('touchend',()=>{if(y0===null)return;np.style.transition='';np.style.transform='';y0=null;
  if(Math.abs(dx)>60&&Math.abs(dx)>2*Math.abs(dy)){np.dataset.swiped=Date.now();skipTrack(dx<0?1:-1);return}
  if(dy>50)setMini(true);else if(dy<-30)setMini(false)});
 np.addEventListener('click',e=>{if(e.target.closest('input')||e.target.closest('button'))return;if(Date.now()-(+np.dataset.swiped||0)<500)return;if(np.classList.contains('mini'))setMini(false);else if(e.target.closest('.grab'))setMini(true)});
 document.addEventListener('click',e=>{if(np.classList.contains('on')&&!np.classList.contains('mini')&&!np.contains(e.target))setMini(true)},true);
 addEventListener('scroll',()=>{if(np.classList.contains('on')&&!np.classList.contains('mini')&&Math.abs(scrollY-fullAtScroll)>60)setMini(true)},{passive:true});
})();
/* wiring */
function wire(){document.querySelectorAll('.clearing [data-nk]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(b.dataset.nk,b.dataset.ns)});
 document.querySelectorAll('details[data-k]').forEach(d=>d.ontoggle=()=>{d.open?OPEN.add(d.dataset.k):OPEN.delete(d.dataset.k);if(d.classList.contains('readx'))fillReaders()});
 fillReaders();fillMapTab();
 document.querySelectorAll('.pref').forEach(b=>b.onclick=e=>{e.stopPropagation();const x=walk()[camp];const r=versesFor(b.dataset.pass,x.b.name,x.c.c);
  HL=r?{book:x.b.name,ch:x.c.c,...r}:null;TAB='scripture';S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false;
  const d=document.querySelector('details.readx');if(d)setTimeout(()=>d.scrollIntoView({behavior:'smooth',block:'start'}),60)});
 const bh=$('#bookhd');if(bh)bh.onclick=()=>{if(view!=='walk'){view='walk';S.set('view',view)}go(+bh.dataset.camp)};document.querySelectorAll('[data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();JM=false;BPM=null;PLAYSTOP=view==='journey'?jpIdx():camp;if(SKIP[b.dataset.play]){delete SKIP[b.dataset.play];S.set('skip',SKIP)}play(b.dataset.play)});
 
 document.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>{const was=!!read[b.dataset.read];read[b.dataset.read]=!was;S.set('read',read);decorate.moving=true;render();decorate.moving=false});
 document.querySelectorAll('.acts [data-camp]').forEach(b=>b.onclick=()=>{decorate.more=false;stepTo(+b.dataset.camp)});document.querySelectorAll('.nv[data-camp], .myplace[data-camp]').forEach(b=>b.onclick=()=>{decorate.more=false;go(+b.dataset.camp)});
 const ct2=$('#cont');if(ct2)ct2.onclick=e=>{e.stopPropagation();doCont()};const sh=$('#sethere');if(sh)sh.onclick=e=>{e.stopPropagation();setJP(camp);note(stopName(walk()[camp])+' is your place now.');setView('journey')};const tj=$('#tojourney');if(tj)tj.onclick=e=>{e.stopPropagation();setView('journey')};
 document.querySelectorAll('[data-skipnext]').forEach(b=>b.onclick=e=>{e.stopPropagation();SKIP[b.dataset.skipnext]=true;S.set('skip',SKIP);const a=nextAction(camp);if(a&&a.step)TAB=a.step;decorate.moving=true;render();decorate.moving=false});document.querySelectorAll('.lk[data-lk]').forEach(t=>t.onclick=e=>{e.stopPropagation();if(LK===t.dataset.lk)return;LK=t.dataset.lk;S.set('lk2',LK);decorate.more=false;decorate.moving=true;render();decorate.moving=false});document.querySelectorAll('.tab[data-tab]').forEach(t=>t.onclick=e=>{e.stopPropagation();if(TAB===t.dataset.tab)return;TAB=t.dataset.tab;S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false});const uf=$('#unfold');if(uf)uf.onclick=e=>{e.stopPropagation();const f=$('#fold');if(f)f.onclick()};const fd=$('#fold');if(fd){fd.onclick=e=>{e&&e.stopPropagation();const f=!FOLD;FOLD=f;if(f&&NP().classList.contains('on'))setMini(true);decorate.moving=true;render();decorate.moving=false;
   /* folding while scrolled down inside a long stop: keep the stop's top in view instead of the page jumping */
   const cl=$('#clearing');if(cl){const t=cl.getBoundingClientRect().top;if(t<60||t>innerHeight-120)window.scrollTo({top:scrollY+t-70})}};const ct=$('#chT');if(ct){ct.onclick=e=>{e.stopPropagation();openJump('browse')};ct.setAttribute('role','button');ct.setAttribute('aria-label','Choose a chapter')}}
 const mo=$('#more');if(mo)mo.onclick=()=>{decorate.more=true;decorate.moving=true;render();decorate.moving=false};
 const g=$('#gear');g.onclick=()=>setView(view==='settings'?PREV:'settings');document.querySelectorAll('[data-settings]').forEach(b=>b.onclick=()=>setView('settings'));
 const back=$('#back');if(back)back.onclick=()=>setView(PREV==='settings'?'journey':PREV);const us=$('#unskip');if(us)us.onclick=()=>{SKIP={};S.set('skip',SKIP);note('Everything you skipped is waiting again where it belongs.');render()};
 const osc=$('#opensc');if(osc)osc.onclick=()=>{view='sc';S.set('view',view);render();window.scrollTo(0,0)};
 const scb=$('#scback');if(scb)scb.onclick=()=>setView('library');
 document.querySelectorAll('details.sce').forEach(d=>d.ontoggle=()=>{d.open?OPEN.add(d.dataset.sck):OPEN.delete(d.dataset.sck)});const ord=$('#ord');if(ord)ord.onclick=()=>{cfg.order=cfg.order==='narr'?'canon':'narr';S.set('cfg',cfg);render()};const lvb=$('#lvl');if(lvb)lvb.onclick=()=>{S.set('level',!levelOn());render()};const wh=$('#who');if(wh)wh.onclick=()=>{const order=['','Platt','PAM','Davey','Skip','Fearless'];cfg.who=order[(order.indexOf(cfg.who)+1)%order.length];S.set('cfg',cfg);render()};
 const io=$('#io');if(io){$('#exp').onclick=()=>io.value=JSON.stringify({prog,read,cfg});$('#imp').onclick=()=>{try{const v=JSON.parse(io.value);prog=v.prog||prog;read=v.read||read;S.set('prog',prog);S.set('read',read);render()}catch(e){io.value='Could not read that JSON.'}};
  const bkf=$('#bkf');if(bkf)bkf.onsubmit=async e=>{e.preventDefault();const key=$('#bkkey').value.trim(),repo=$('#bkrepo').value.trim().replace(/^https?:\/\/github\.com\//,'').replace(/\.git$|\/$/g,''),msg=$('#bkmsg');msg.textContent='Checking…';
   try{const r=await bkGH('',{},key,repo);if(r.status===401)throw 'GitHub did not accept that key.';if(r.status===404)throw 'Could not open '+repo+' with that key: check the repo exists and the key was given access to it.';if(!r.ok)throw 'GitHub said '+r.status+'.';
    const j=await r.json();if(!j.private&&!confirm(repo+' is public: anyone could see your listening history. Use it anyway?'))throw 'Make the repo private, then try again.';
    if(j.permissions&&!j.permissions.push)throw 'That key can read the repo but not save to it: give it Contents: Read and write.';
    S.set('bkkey',key);S.set('bkrepo',repo);BK.sha=null;BK.err='';S.set('bkerr','');bkDot();
    const remote=await bkFetch().catch(()=>null),here=bkSnap();
    if(remote&&remote.data&&bkWeight(remote.data)>0){const when=new Date(remote.at).toLocaleString();
     if(bkWeight(here)===0||confirm('Found a backup from '+when+'. Restore it on this phone? (Cancel keeps this phone\'s progress and backs it up instead.)')){bkApply(remote.data);location.reload();return}}
    await bkSave();render()}catch(err){msg.textContent=typeof err==='string'?err:'Could not reach GitHub. Check your connection.'}};
  const bkn=$('#bknow');if(bkn)bkn.onclick=async()=>{localStorage.setItem('sc:bkdirty','1');$('#bkst').textContent='Backing up…';await bkSave()};
  const bkr=$('#bkrest');if(bkr)bkr.onclick=async()=>{try{const d=await bkFetch();if(!d||!d.data){alert('No backup yet.');return}if(confirm('Replace this phone\'s progress with the backup from '+new Date(d.at).toLocaleString()+'?')){bkApply(d.data);location.reload()}}catch(e){alert('Could not reach the backup.')}};
  const bko=$('#bkoff');if(bko)bko.onclick=()=>{if(confirm('Stop backing up? The backups already saved stay in your repo.')){localStorage.removeItem('sc:bkkey');localStorage.removeItem('sc:bkerr');BK.err='';bkDot();render()}};
  $('#reset').onclick=()=>{if(confirm('Erase all progress on this device?')){prog={};read={};camp=null;S.set('prog',prog);S.set('read',read);S.set('camp',null);render()}};
  $('#atest').onclick=()=>{const o=$('#atest-out');o.textContent=' testing…';const a=new Audio();a.src=Object.values(I).find(i=>i.audio).audio;a.addEventListener('loadedmetadata',()=>o.textContent=' ✓ streams ('+fmt(a.duration)+')');a.addEventListener('error',()=>o.textContent=' ✗ blocked here');a.load()}}}
decorate.first=true;render();let lastW=innerWidth;window.addEventListener('resize',()=>{if(innerWidth===lastW)return;lastW=innerWidth;decorate.first=true;render()});
setInterval(()=>{if(bkDue()&&Date.now()-BK.tried>10*60e3)bkSave()},60e3);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&bkDue())bkSave()});setTimeout(()=>{bkDot();if(bkDue())bkSave()},5000);
/* home-screen app: offline shell + keep progress from being evicted */
if('serviceWorker' in navigator&&isSecureContext)navigator.serviceWorker.register('sw.js').catch(()=>{});
/* pick up new versions: check on open and whenever the app comes back to the front */
const APPV=__VERSION__;function checkV(){fetch('version.txt?'+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.text():'').then(t=>{if(+t>APPV){let k='';try{k=sessionStorage.getItem('sc:rl')}catch(e){}if(k===t)return;try{sessionStorage.setItem('sc:rl',t)}catch(e){}location.replace(location.pathname+'?v='+t)}}).catch(()=>{})}checkV();document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkV()});
if(navigator.storage&&navigator.storage.persist)navigator.storage.persist().catch(()=>{});
</script></body></html>"""

VOICES_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Narrator voices</title><style>
:root{--bg:#f4efe3;--ink:#1b2440;--mute:#6b7390;--gold:#c9a24a;--gold2:#a8812a}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,system-ui,sans-serif;padding:calc(20px + env(safe-area-inset-top)) max(16px,env(safe-area-inset-right)) 40px max(16px,env(safe-area-inset-left))}
h1{font:400 30px "Iowan Old Style",Palatino,Georgia,serif;margin:0 0 4px}p{color:var(--mute);margin:0 0 18px;max-width:34em}
.v{background:rgba(255,255,255,.8);border:1px solid rgba(27,36,64,.08);border-radius:16px;padding:12px 14px;margin:10px 0}
.n{font:20px "Iowan Old Style",Palatino,Georgia,serif;margin-bottom:6px}.n span{font:12px -apple-system,system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2);margin-left:10px}
audio{width:100%}\nh2{font:400 22px "Iowan Old Style",Palatino,Georgia,serif;margin:26px 0 2px}.sub{font-size:13px;color:var(--mute);margin:8px 0 4px}
.speed{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;display:flex;align-items:center;justify-content:space-between;gap:10px;background:rgba(244,239,227,.94);backdrop-filter:blur(8px);padding:10px 0 12px;margin:0 0 6px;border-bottom:1px solid rgba(27,36,64,.1)}
.speed .lab{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2)}
.speed .ctl{display:flex;align-items:center;gap:10px}
.speed button{width:46px;height:46px;border-radius:50%;border:1px solid rgba(27,36,64,.18);background:#fff;font:22px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}
.speed button:active{background:rgba(201,162,74,.25)}
.speed .val{font:600 24px -apple-system,system-ui,sans-serif;min-width:3.6em;text-align:center;font-variant-numeric:tabular-nums}
.speed .reset{width:auto;height:auto;border-radius:14px;padding:6px 12px;font-size:13px}
</style></head><body><h1>Choose the narrator</h1><p>Pick the voice you want reading the whole Bible to you. Change the speed to hear each one faster or slower.</p>
<div class="speed"><span class="lab">Speed</span><div class="ctl"><button id="dn" aria-label="Slower">−</button><span class="val" id="sv">1.00×</span><button id="up" aria-label="Faster">+</button></div><button class="reset" id="rs">Reset</button></div>
__ROWS__
<script>
let rate=1;try{rate=+localStorage.getItem('voiceRate')||1}catch(e){}
const A=[...document.querySelectorAll('audio')];
function apply(){rate=Math.round(Math.min(2,Math.max(0.5,rate))*100)/100;document.getElementById('sv').textContent=rate.toFixed(2)+'×';
 A.forEach(a=>{a.preservesPitch=true;a.playbackRate=rate});try{localStorage.setItem('voiceRate',rate)}catch(e){}}
document.getElementById('up').onclick=()=>{rate+=0.05;apply()};document.getElementById('dn').onclick=()=>{rate-=0.05;apply()};document.getElementById('rs').onclick=()=>{rate=1;apply()};
A.forEach(a=>{a.addEventListener('play',()=>{A.forEach(b=>{if(b!==a)b.pause()});a.playbackRate=rate});a.addEventListener('loadedmetadata',()=>{a.playbackRate=rate})});
apply();
</script></body></html>"""

if __name__ == "__main__":
    main()
