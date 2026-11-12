"""Build out/scripture-companion.html — a single-file, installable web app:
podcast-style player (Media Session lock-screen controls, resume, speed, auto-advance),
books → chapters → episodes with progress bars, Secret Church in order, Pray the Word list.
Progress lives in localStorage; export/import as JSON. Run: python app_build.py
"""
from __future__ import annotations
import glob, json, os, re, shutil, sys
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
VERSION = 107  # the app's version name (file names)
# Every build gets a newer number: the installed app compares it with version.txt when it opens or comes back to the
# front, and reloads to the new build; it also renews the service-worker cache. (A fixed number kept phones on old builds.)
BUILD = int(__import__("time").time())
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

ONE_CH = {"Obadiah", "Philemon", "2 John", "3 John", "Jude"}   # one-chapter books: a study may be titled by the book alone
def is_walk(title):
    """A walk-through message: titled only by its passage ("Genesis 1", "Expound: Romans 9-10:4 - Part A", or "Jude")."""
    if (title or "").strip() in ONE_CH: return True
    rest = title or ""
    for r in parse_refs(rest): rest = rest.replace(r.raw, " ")
    return bool(parse_refs(title or "")) and not re.search(r"[A-Za-z]{2,}", re.sub(r"\b(?:and|part|review|expound)\b", " ", rest, flags=re.I))

def be_led(items):
    """Be Led: pastors leading in prayer, each the closing prayer of a sermon, played from that sermon's recording
    (data/be_led.json: sb/e = seconds before the file's end where the prayer starts and ends)."""
    p = os.path.join(HERE, "data", "be_led.json")
    if not os.path.exists(p): return []
    out = []
    for x in json.load(open(p, encoding="utf-8")).get("prayers", []):
        it = items.get(x["src"])
        if not it or not it.get("audio"): continue
        if x["sb"] - x["e"] < 60: continue          # a minute at least: the ones that carry you into prayer
        out.append({"id": "led:" + x["src"] + ("" if not x.get("n") else f":{x['n']}"), "src": x["src"], "sb": x["sb"], "e": x["e"], "who": it["who"],
                    "audio": it["audio"], "len": round(x["sb"] - x["e"]), "music": bool(x.get("music")), "power": int(x.get("power") or 4),
                    "dur": it.get("dur"), **({"L": x["L"]} if x.get("L") else {}), **({"lu": x["lu"]} if x.get("lu") is not None else {})})   # L = the file's length as a browser reports it; lu = how loud the prayer is (LUFS)
    return out

def guided_lp(items):
    """Guided: a pastor praying the Lord's Prayer through (data/guided_lp.json: src, a/b = seconds from the file's start,
    at = where each movement begins, music = none of its own under it)."""
    p = os.path.join(HERE, "data", "guided_lp.json")
    if not os.path.exists(p): return None
    x = json.load(open(p, encoding="utf-8")); it = items.get(x["src"])
    if not it or not it.get("audio"): return None
    return {"src": x["src"], "who": it["who"], "audio": it["audio"], "a": x["a"], "b": x["b"], "at": x["at"], "music": bool(x.get("music")), **({"Lt": x["Lt"]} if x.get("Lt") else {}), **({"lu": x["lu"]} if x.get("lu") is not None else {})}

def pray_level(P):
    """How loud Pray's recordings are (tools/pray_loud.py, LUFS): the middle of them (lum), which the music under each is set
    against; a prayer or reading far quieter than the rest (over 6 dB) is left out, since a phone cannot turn it up."""
    vals = [x["lu"] for x in P["led"] + P["med"] + ([P["lp"]] if P.get("lp") else []) if x.get("lu") is not None]
    if not vals: return P
    import statistics
    m = statistics.median(vals); P["lum"] = round(m, 1)
    for k in ("led", "med"): P[k] = [x for x in P[k] if x.get("lu") is None or x["lu"] >= m - 6]
    return P

def big_picture(items, vser=None):
    """Big Picture: whole-Bible series heard in order, each with its own place. Episodes are items already in the app."""
    sc = sorted([i for i in items.values() if i["src"] == "secret_church_podcast" and i["sc"] and i["sc"][0] in (1, 2)], key=lambda i: tuple(i["sc"]))
    flights = sorted([i for i in items.values() if i["src"] == "skip_archive" and re.match(r"\s*Flight\b", i["t"])], key=lambda i: (i["date"], i["t"]))
    out = [{"id": "survey", "title": "Bible Survey", "by": "David Platt", "art": "survey",
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
    # The Story of Scripture (Platt, McLean 2019): Genesis to Revelation over forty Sundays, in preaching order
    sos = json.load(open(os.path.join(HERE, "data", "story_of_scripture.json"), encoding="utf-8"))
    key = lambda t: re.sub(r"[^a-z0-9]", "", re.sub(r"[’']", "", (t or "").lower()))
    platt = defaultdict(list)
    for i in items.values():
        if i.get("who") == "Platt": platt[key(i["t"])].append(i)
    ids, names = [], {}
    for x in sos["parts"]:
        cand = list(platt.get(key(x["title"]), []))
        cand.sort(key=lambda i: (not i.get("audio"), i["src"] == "ptw"))
        if not cand: continue
        ids.append(cand[0]["id"]); names[cand[0]["id"]] = x.get("name") or x["title"]
    out.insert(1, {"id": "sos", "title": "The Story of Scripture", "by": "David Platt", "art": "sos", "group": "bp", "unit": "part",
                   "desc": "Genesis to Revelation over forty Sundays: God bringing his people to his place for his purpose, from creation to new creation. McLean Bible Church, 2019.",
                   "parts": [["", ids]], "names": names})
    # Kennon Vaughan's sermon series, each in the order he preached it (series of three or more)
    runs = defaultdict(list)
    for i, name in (vser or {}).items():
        if i in items: runs[name].append(items[i])
    for name, L in sorted(runs.items(), key=lambda kv: min(i["date"] or "9" for i in kv[1]), reverse=True):
        if len(L) < 3: continue
        L.sort(key=lambda i: (i["date"] or "", i["t"]))
        books = defaultdict(int)
        for i in L:
            m = re.match(r"\s*((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?)\s+\d", i.get("pass") or "")
            if m: books[m.group(1)] += 1
        book = max(books, key=books.get) if books else ""
        if book and books[book] * 2 < len(L): book = ""   # several books (a topical series): name none
        yrs = sorted({i["date"][:4] for i in L if i["date"]})
        when = yrs[0] if len(yrs) == 1 else f"{yrs[0]}–{yrs[-1]}" if yrs else ""
        head = re.sub(r"^The ", "", name.split(":")[0])
        label = book if book and book.lower() in head.lower() else head if len(head) <= 14 else (book or head.split()[0])
        out.append({"id": "kv-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), "title": name, "by": "Kennon Vaughan", "art": "kv:" + label.upper(),
                    "group": "kv", "unit": "sermon", "desc": f"{len(L)} sermons{' through ' + book if book and book.lower() not in name.lower() else ''}, preached at Harvest Church in Memphis{', ' + when if when else ''}. In the order he preached them.",
                    "parts": [["", [i["id"] for i in L]]]})
    return [x for x in out if any(ids for _, ids in x["parts"])]

def main():
    # where each episode's intro ends, found by tools/intro_detect.py (data/intro_skip/<source>.json: {id: seconds})
    INTROS = {}
    OUTROS = {}  # seconds before the end where the teaching's last word ends (data/intro_skip/<source>_end.json)
    for f in sorted(_glob.glob(os.path.join(HERE, "data", "intro_skip", "*.json"))):
        if f.endswith("_opening.json"): continue
        (OUTROS if f.endswith("_end.json") else INTROS).update(json.load(open(f, encoding="utf-8")))
    entries = [json.loads(l) for l in open(VERIFIED, encoding="utf-8")]
    _dp = os.path.join(HERE, "data", "durations.json")   # lengths read from the audio files where a feed gives none (tools/durations.py)
    DURS = json.load(open(_dp)) if os.path.exists(_dp) else {}
    narr = {(o["book"], o["chapter"]): o["seq"] for o in json.load(open(NARR))}
    team = {f"guest:{n}" for n in config.PAM_CHURCH_PREACHERS}
    skip_guest = lambda e: e["source"].startswith("skip_") and e["speaker"].startswith("guest:")  # Calvary Church guests keep Skip's series unbroken
    # Skip Heitzig: his verse-by-verse walk-throughs and Bible from 30,000 Feet, not his topical Sunday sermons
    skip_kept = lambda e: not e["source"].startswith("skip_") or is_walk(e["title"]) or re.match(r"\s*Flight\b", e["title"]) or e["id"] in config.SKIP_TOPICAL_KEEP
    for e in entries:   # Skip's studies of one-chapter books are titled "Jude", "2 John": give them their passage
        t = (e.get("title") or "").strip()
        if e["source"].startswith("skip_") and t in ONE_CH and not e.get("refs"):
            e["refs"] = {t: {"chapters": [1], "verse_level": False, "whole_book": True, "raw": [t]}}; e["refs_text"] = t + " 1"
        bk = config.SKIP_TOPICAL_KEEP.get(e["id"])
        if bk:   # a sermon on the whole book: on that book's page
            e["refs"] = {bk: {"chapters": list(range(1, CHAPTERS[bk] + 1)), "verse_level": False, "whole_book": True, "raw": [bk]}}
            e["refs_text"] = bk; e["track"] = "overview"
        # a walk-through of part of a book ("Song of Solomon 4-8") belongs on those chapters, even when it is most of the book
        if e["source"].startswith("skip_") and e.get("track") == "overview" and len(e.get("refs") or {}) == 1 and is_walk(t):
            (b, d), = e["refs"].items()
            if not d["whole_book"] and b in CHAPTERS and len(d["chapters"]) < CHAPTERS[b] and min(d["chapters"]) > 1: e["track"] = "sermon"
    usable = [e for e in entries if e["tier"] in ("V2", "V1") and e["source"] not in config.OFF_ROAD_SOURCES and skip_kept(e) and (e["speaker"] in ("Platt", "PAM", "Davey", "Skip") or e["speaker"] in team or skip_guest(e) or e["speaker"].startswith("fearless:") or e["speaker"] == "Vaughan") and not (config.DAVEY_HIDDEN and e["speaker"] == "Davey" and e["id"] not in config.DAVEY_KEEP)]
    items, by_chapter, by_book_ov, spans = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    CH, WALK, VS, VSER = {}, {}, {}, {}  # chapters per book for each item; WALK = titled only by its passage (a walk-through message); VS = verses
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
        it = {"id": e["id"], "t": re.sub(r"\s{2,}", " ", re.sub(r"[\ue000-\uf8ff]", " ", e["title"])).strip(), "who": "Fearless" if e["speaker"].startswith("fearless:") else "Vaughan" if e["speaker"] == "Vaughan" else "PAM" if (e["speaker"] == "PAM" or e["speaker"] in team) else ("Skip" if skip_guest(e) else e["speaker"] if e["speaker"] in ("Davey", "Skip") else "Platt"),
              "show": config.SHOWS.get(e["source"]),
              **({"s": 13} if e["source"] == "skip_archive" and re.match(r"\s*Flight\b", e["title"]) else   # every 30,000 Feet flight opens with the same 13-second intro
                 ({"s": INTROS[e["id"]]} if INTROS[e["id"]] else {}) if e["id"] in INTROS else {"s": config.INTRO_SKIP[e["source"]]} if config.INTRO_SKIP.get(e["source"]) else {}),
              "by": ("Pastor " + e["speaker"].split(":", 1)[1] if e["speaker"] != "fearless:Fearless Church" else None) if e["speaker"].startswith("fearless:") else e["speaker"].split(":", 1)[1] if (e["speaker"] in team or skip_guest(e)) else None,
              "era": e["era"], "tr": e["track"], "src": e["source"], "url": e.get("primary_url") or e["url"],
              "audio": audio_url(e), "dur": int(e["duration"]) if str(e["duration"]).isdigit() and int(e["duration"]) else DURS.get(e["id"], 0),
              "date": iso_date(e.get("published")), "pass": e.get("refs_text", ""), "tier": e["tier"],
              "sc": [e.get("sc_season"), e.get("sc_episode")] if e.get("sc_season") else None,
              **({"e": OUTROS[e["id"]]} if OUTROS.get(e["id"]) else {})}
        items[it["id"]] = it
        if e["source"] == "harvest_memphis" and e.get("series"): VSER[it["id"]] = e["series"]
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
    # recordings the publisher attached to the wrong episode titles: each title gets the recording that is that sermon
    NOFILE = {}
    _fp = os.path.join(HERE, "data", "audio_fixes.json")
    if os.path.exists(_fp):
        _fx = {k: v for k, v in json.load(open(_fp, encoding="utf-8")).items() if not k.startswith("_")}
        _orig = {v: {f: items[v].get(f) for f in ("audio", "dur", "s", "e")} for v in _fx.values() if v in items}
        for t, src in _fx.items():   # the recording brings its own start and end points (data/intro_skip is kept by recording)
            if t in items and src in _orig:
                for f, v in _orig[src].items():
                    if v is None: items[t].pop(f, None)
                    else: items[t][f] = v
                items[t]["aid"] = src
        # listings whose file on the publisher's server is another sermon, with no right copy anywhere: no audio, off the road
        _none = json.load(open(_fp, encoding="utf-8")).get("_no_recording", {})
        for t, why in _none.items():
            if t in items:
                for f in ("dur", "s", "e"): items[t].pop(f, None)
                items[t]["audio"] = None
                NOFILE[t] = why
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
                "davey_archive": 0, "davey_sermons": 0, "davey_wfth": 1, "brookhills_ia": 1, "davey_journey": 0, "skip_archive": 0, "skip_church": 1, "skip_connect": 2}
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
        if i in NOFILE: WHY[i] = "no recording: " + NOFILE[i]; return False
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
    # Davey's archive has no dates: its lessons play in the order of the recordings (the file names are numbered in preaching order)
    LESSON = {}
    for _f in sorted(glob.glob(os.path.join(HERE, "data", "davey_archive", "*.json"))):
        for _x in json.load(open(_f, encoding="utf-8")).get("sermons", []):
            if _x.get("mp3"): LESSON[_x["mp3"]] = _x["n"]
    def rank(book):
        def key(i):
            it, d, f = items[i], _day(i) or 0, focus(i, book)
            series = (-run_end.get((book, it["who"], d), d), d) if f == 2 else ((0, d) if it["src"] == "davey_journey" else (0, LESSON.get(it["audio"], 0)) if it["src"] == "davey_archive" else (0, -d))  # the Journey walks forward day by day; the archive (no dates) in lesson order
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
    # The Bible Narrative: book and chapter introductions (data/narrative/<abbr>.txt). The texts go to narrative/<abbr>.json,
    # fetched when shown; an introduction appears in the app once its recording matches its current text.
    import hashlib
    sys.path.insert(0, os.path.join(HERE, "tools"))
    from narrative_check import sections as _nsec
    rec = json.load(open(os.path.join(HERE, "data", "narrative_audio.json"))) if os.path.exists(os.path.join(HERE, "data", "narrative_audio.json")) else {}
    intro, intro_txt = {}, {}
    os.makedirs(os.path.join(SITE, "narrative"), exist_ok=True)
    for _name, abbr, _n, _t, _ in BOOKS:
        sec, _d, files = _nsec(abbr)
        if not files: continue
        texts = {("0" if k == "intro" else k): v for k, v in sec.items() if v}
        # names in the introductions link to their cards, each name at its first mention in a paragraph
        lk = lambda c, t: "\n\n".join((ATLAS.link_book(p, _name) if c == "0" else ATLAS.link_chapter(p, _name, int(c))) for p in re.split(r"\n\s*\n", t)) if ATLAS.ok else t
        json.dump({c: lk(c, t) for c, t in texts.items()}, open(os.path.join(SITE, "narrative", abbr + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        intro_txt[abbr] = sorted(int(c) for c in texts)
        for c, t in texts.items():
            r = (rec.get(abbr) or {}).get(c)
            if r and r[1] == hashlib.sha1(t.encode("utf-8")).hexdigest()[:12]:
                intro.setdefault(abbr, {})[c] = round(r[0])
    # Core: one primary exposition per chapter or passage, the rest kept for Go Deeper (core.py)
    import core as _core
    if os.environ.get("CORE_DUMP"):
        import pickle; pickle.dump({"books": books, "items": items, "VS": VS, "ref_how": ref_how, "cited": cited, "item_books": item_books,
                                    "VC": {b[0]: [vcount(b[0], c) for c in range(1, b[2] + 1)] for b in BOOKS}}, open(os.environ["CORE_DUMP"], "wb"))
    CORE = _core.select(books, items, VS, ref_how, cited, item_books, {b[0]: [vcount(b[0], c) for c in range(1, b[2] + 1)] for b in BOOKS})
    data = {"built": __import__("datetime").date.today().isoformat(), "hide": ["Davey"] if config.DAVEY_HIDDEN else [], "core": CORE["app"], "items": items, "books": books, "narr": narr, "intro": intro, "itx": intro_txt,
            "sc": {"events": sc_events, "ids": [i["id"] for i in sc_items]}, "ptw": [i["id"] for i in ptw], "bp": big_picture(items, VSER),
            "topics": topics.build(items, CH, {i for lst in by_chapter.values() for i in lst} | {i for lst in by_book_ov.values() for i in lst}),
            "alias": {a.lower().replace(".", ""): b[0] for b in BOOKS for a in b[4] + [b[0], b[1]]},
            "pray": pray_level({"moves": __import__("pray").build(), "led": be_led(items), "med": __import__("pray").meditate(items), "lp": guided_lp(items)})}
    html = TEMPLATE.replace("__VERSION__", str(BUILD)).replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    n_audio = sum(1 for i in items.values() if i["audio"])
    print(f"wrote {OUT}: {len(items)} items, {n_audio} with in-app audio; off the road: {len(off_road)}")
    json.dump(sorted(f'{items[i]["t"]}  [{WHY.get(i, "")}]' for i in off_road), open(os.path.join(HERE, "out", "off_road.json"), "w"), indent=0, ensure_ascii=False)
    write_site(html)
    write_share_pages(items, html)

def blk(t, book):
    return ATLAS.link_book(t, book) if ATLAS.ok else t

SITE_URL = "https://zreynard.github.io/scripture-companion/"   # the app's public address: link previews need it in full

def write_share_pages(items, html):
    """s/<id>.html: one small page per sermon, for a link you send a friend — its own preview card (title, teacher,
    passage), and a player that streams the sermon from the church's host. Only the sermon's public details are in it.
    The artwork's colours, icons and teacher names are read from the app's own code, so the page matches the player."""
    import html as H, re as _re
    d = os.path.join(SITE, "s"); os.makedirs(d, exist_ok=True)
    js = lambda name: _re.search(r"const " + name + r"=(\{.*?\});", TEMPLATE, _re.S).group(1)
    art = "window.SC_ART={colors:" + js("ART_C") + ",icons:" + js("MEDAL_ICON") + ",medal:{Platt:'apostle',PAM:'prophet',Davey:'writer',Skip:'patriarch'}};"
    names = dict(_re.findall(r"(\w+):'([^']+)'", js("NAMES")))
    open(os.path.join(d, "art.js"), "w", encoding="utf-8").write(art + "\n")
    for f in ("listen.js", "listen.css"): shutil_copy(os.path.join(HERE, "site_extra", "s", f), os.path.join(d, f))
    D, _ = json.JSONDecoder().raw_decode(html[html.index("const D=") + 8:])
    place = {}                                   # the label the player's artwork shows: the same rule as the app's where()
    for bk in D.get("books", []):
        for x in bk.get("ov", []) + [s["id"] for s in bk.get("spans", []) or []]: place.setdefault(x, bk["name"])
        for c in bk.get("ch", []):
            for x in c.get("ids", []): place.setdefault(x, f'{bk["name"]} {c["c"]}')
    n = 0
    for i in items.values():
        if not i.get("audio") or i.get("nar") or i.get("intro") or i.get("blob") or i.get("led") or not _re.fullmatch(r"[\w-]+", i["id"]): continue
        who = i.get("who") or ""; teach = i.get("by") or names.get(who, who)
        m = _re.match(r"^((?:[123]\s)?[A-Za-z][A-Za-z ]*?\s*\d+)", i.get("pass") or "")
        rec = {"id": i["id"], "t": i.get("t") or "", "who": who, "teacher": teach, "pass": i.get("pass") or "", "where": place.get(i["id"]) or (m.group(1) if m else ""),
               "show": i.get("show") or "", "audio": i["audio"], "s": float(i.get("s") or 0), "dur": float(i.get("dur") or 0), "url": i.get("url") or ""}
        desc = " · ".join(x for x in (teach, i.get("pass")) if x)
        e = lambda s: H.escape(str(s), quote=True)
        data = json.dumps(rec, ensure_ascii=False).replace("</", "<\\/")
        page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                f'<title>{e(rec["t"])} · {e(teach)}</title><meta name="description" content="{e(desc)}"><meta name="robots" content="noindex">'
                f'<meta property="og:type" content="website"><meta property="og:title" content="{e(rec["t"])}"><meta property="og:description" content="{e(desc)}">'
                f'<meta property="og:image" content="{SITE_URL}icon-512.png"><meta property="og:url" content="{SITE_URL}s/{e(i["id"])}.html"><meta name="twitter:card" content="summary">'
                f'<meta name="theme-color" content="#f4efe4"><link rel="icon" href="../icon-192.png"><link rel="apple-touch-icon" href="../icon-180.png">'
                f'<link rel="stylesheet" href="listen.css?v={BUILD}"></head><body>'
                f'<script type="application/json" id="sd">{data}</script>'
                f'<script src="art.js?v={BUILD}"></script><script src="listen.js?v={BUILD}"></script></body></html>')
        open(os.path.join(d, i["id"] + ".html"), "w", encoding="utf-8").write(page); n += 1
    print(f"wrote {n} share pages in {d}")

def shutil_copy(a, b):
    import shutil; shutil.copy(a, b)

def write_site(html: str):
    """out/site/: index.html + manifest + icons + service worker — the installable home-screen app."""
    import shutil
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(SITE, "version.txt"), "w").write(str(BUILD))
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
    xdir = os.path.join(HERE, "site_extra")   # Worship: song engine, live sync, the TV page and the presenter/remote page
    if os.path.isdir(xdir):
        for root, _, files in os.walk(xdir):
            for f in files:
                src = os.path.join(root, f); dst = os.path.join(SITE, os.path.relpath(src, xdir))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if f.endswith((".html", ".js")):   # pages know which build they are, so a TV can tell it is out of date
                    open(dst, "w", encoding="utf-8").write(open(src, encoding="utf-8").read().replace("__BUILD__", str(BUILD)))
                else: shutil.copy(src, dst)
    for f in os.listdir(PWA):
        if f == "sw.js":
            src = open(os.path.join(PWA, f), encoding="utf-8").read().replace("__VERSION__", str(BUILD))
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
*{box-sizing:border-box}html{height:100%}body{min-height:100%}/* min, so the room kept for the player is added after the content, not inside the screen height */
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
#jump{position:fixed;top:0;right:0;bottom:0;left:0;z-index:25;background:#f7f2e7;display:flex;flex-direction:column}
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
#sheetbg{position:fixed;top:0;right:0;bottom:0;left:0;background:rgba(27,36,64,.28);z-index:20;touch-action:none}
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
#mapv{position:fixed;top:0;right:0;bottom:0;left:0;z-index:22;background:#d6e4e3;overscroll-behavior:contain}
#mapv::after{content:"";position:absolute;top:0;right:0;bottom:0;left:0;z-index:1;pointer-events:none;background:radial-gradient(ellipse 85% 70% at 50% 42%,rgba(255,250,235,0) 60%,rgba(110,90,50,.18) 100%)}
#mapsvg{position:absolute;top:0;right:0;bottom:0;left:0;width:100%;height:100%;touch-action:none;cursor:grab;-webkit-user-select:none;user-select:none}
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
.np-tr{display:flex;align-items:center;gap:12px}.np-tr .t{flex:1;min-width:0}
#np-more{flex:none;width:36px;height:36px;border-radius:18px;border:0;background:rgba(27,36,64,.08);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}#np-more[hidden],#np.mini #np-more{display:none}
[data-row],[data-full]{-webkit-touch-callout:none;-webkit-user-select:none;user-select:none}
#smenu{position:fixed;inset:0;z-index:300}#smenu .sm-bg{position:absolute;inset:0;background:rgba(27,36,64,.18);opacity:0;transition:opacity .18s}
#smenu .sm-bg.blur{background:rgba(27,36,64,.22);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}#smenu.on .sm-bg{opacity:1}
#smenu .sm-box{position:absolute;width:250px;background:rgba(255,253,248,.98);border-radius:16px;box-shadow:0 18px 50px rgba(27,36,64,.28);overflow:hidden;opacity:0;transform:scale(.96);transition:transform .16s,opacity .16s}#smenu.on .sm-box{opacity:1;transform:none}
#smenu .sm-box button{display:flex;align-items:center;justify-content:space-between;width:100%;padding:14px 16px;border:0;background:none;font:16px -apple-system,system-ui,sans-serif;color:var(--ink);text-align:left;cursor:pointer}
#smenu .sm-box button+button{border-top:1px solid rgba(27,36,64,.08)}#smenu .sm-box i{color:#6b7088;display:flex}
#smenu .sm-lift{position:absolute;margin:0!important;transform:scale(1.03);box-shadow:0 14px 34px rgba(27,36,64,.3);border-radius:18px;background:#fffdf8;pointer-events:none}
.fav-av{background:#c9a24a!important;color:#c0392b;display:flex;align-items:center;justify-content:center}
.fav-h{display:flex;align-items:center;gap:12px;margin:4px 0 12px}.fav-h .fav-av{width:44px;height:44px;border-radius:22px;flex:none}.fav-h b{display:block;font-size:24px;font-weight:500}.fav-h small{color:var(--mute);font-size:13px}
.fav-q{display:flex;align-items:center;gap:8px;background:rgba(27,36,64,.07);border-radius:12px;padding:0 12px;height:42px;margin:0 0 10px;color:#7a7f96}
.fav-q input{flex:1;min-width:0;border:0;background:none;font:16px -apple-system,system-ui,sans-serif;color:var(--ink);outline:none;height:100%}
.fav-bar{display:flex;justify-content:space-between;align-items:center;margin:0 2px 10px;font:600 14px -apple-system,system-ui,sans-serif;color:var(--mute)}
.fav-sort{position:relative;color:#9a7a2c;cursor:pointer}.fav-sort select{position:absolute;inset:0;width:100%;height:100%;opacity:0;font-size:16px;cursor:pointer;-webkit-appearance:none;appearance:none}
.fav-g{font:700 11.5px -apple-system,system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#9a7a2c;margin:16px 4px 6px}.fav-none{color:var(--mute);margin:18px 4px}
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
#np:not(.mini){top:0;z-index:13;border-radius:0;display:flex;flex-direction:column;background:#f7f2e7;backdrop-filter:none;padding:calc(6px + env(safe-area-inset-top)) 26px calc(18px + env(safe-area-inset-bottom));overflow-y:auto}
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
#np .ctl2{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:10px}
#np #bedb{border:1px solid rgba(27,36,64,.14);border-radius:22px;background:#fff;padding:8px 14px;font-weight:600;color:var(--ink)}#np #bedb.on{background:var(--ink);color:#fff;border-color:var(--ink)}#bedb[hidden],#bedpop[hidden]{display:none}
#bedpop{margin-top:10px;padding:14px 16px;border-radius:18px;background:#fff;border:1px solid rgba(27,36,64,.1);text-align:left}
#bedpop .bp-row{display:flex;align-items:center;gap:12px}#bedpop .bp-row span{flex:1}#bedpop b{display:block;font-size:15px}#bedpop small{display:block;color:var(--mute);font-size:13px;margin-top:2px}
#bedpop input[type=checkbox]{width:48px;height:28px;accent-color:#1b2440;flex:none}#bedpop input[type=range]{width:100%;margin:12px 0 2px;accent-color:#1b2440}
#bedpop .bp-l{display:flex;justify-content:space-between;font-size:12.5px;color:var(--mute)}#bedpop button{margin-top:10px;border:0;background:var(--ink);color:#fff;border-radius:18px;padding:9px 16px;font-weight:700}
.spd{display:flex;align-items:center;gap:2px;border:1px solid rgba(27,36,64,.14);border-radius:22px;background:#fff}.spd button{min-width:40px;font-weight:600}#np .ctl2 .spd button{padding:8px 10px}#spd{min-width:58px!important}
#np .ctl2 button{background:none;border:0;color:var(--ink);font:inherit;font-size:15px;padding:10px 4px}
@keyframes npL{from{transform:translateX(50px);opacity:.2}to{transform:none;opacity:1}}@keyframes npR{from{transform:translateX(-50px);opacity:.2}to{transform:none;opacity:1}}
#np.sw-l .art,#np.sw-l .t,#np.sw-l .s{animation:npL .28s ease-out}#np.sw-r .art,#np.sw-r .t,#np.sw-r .s{animation:npR .28s ease-out}
#np.mini .np-top,#np.mini .art,#np.mini .np-d,#np.mini #zz,#np.mini #bedb,#np.mini #bedpop{display:none!important}
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
body[data-v=pray] #np,body[data-v=worship] #np{display:none!important}
.wsp{padding-bottom:30px}
.w-list{display:flex;flex-direction:column;gap:10px;margin:14px 0}
.w-row{display:flex;align-items:center;gap:12px;width:100%;padding:14px 16px;border-radius:16px;border:0;background:#fffdf8;box-shadow:0 3px 12px rgba(27,36,64,.06);text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.w-row span{flex:1;min-width:0}.w-row b{display:block;font-size:19px;font-weight:500}.w-row small{display:block;font-size:13px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.w-row i{font-style:normal;color:var(--gold2);font-size:22px}
.w-empty{color:var(--mute);font-size:15px;line-height:1.5;margin:18px 4px}
.w-add{display:block;width:100%;height:50px;margin-top:8px;border-radius:25px;border:1px dashed rgba(27,36,64,.25);background:none;font:600 15px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}
.w-q{width:100%;height:44px;border-radius:22px;border:1px solid var(--line);background:#fff;padding:0 16px;font:inherit;margin:12px 0 0}
.w-grp{font:700 11.5px -apple-system,system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#9a7a2c;margin:22px 4px -4px}
.w-tn{display:block;width:100%;text-align:left;border:0;border-radius:20px;padding:16px 18px 14px;margin:14px 0 4px;background:linear-gradient(180deg,#fbf3df,#f6ead0);box-shadow:0 4px 16px rgba(150,110,30,.12);color:var(--ink);font:inherit;cursor:pointer}
.w-tn .k{font:700 11.5px -apple-system,system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#9a7a2c}
.w-tn b{display:block;font-size:25px;font-weight:500;margin:4px 0 8px}
.w-tn ol{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:3px}
.w-tn li{font-size:15px;color:#3b4262;display:flex;gap:10px}.w-tn li em{font-style:normal;color:#b08a3a;font-weight:600;width:14px;text-align:right;flex:none}
.w-tn .go{display:flex;align-items:center;justify-content:space-between;margin-top:12px;font:600 14px -apple-system,system-ui,sans-serif;color:#9a7a2c}
.w-row .w-when{display:block;font:600 12.5px -apple-system,system-ui,sans-serif;font-style:normal;color:#9a7a2c;margin-bottom:1px}
.w-past{display:block;width:100%;border:0;background:none;color:var(--mute);font:600 14px -apple-system,system-ui,sans-serif;padding:16px 4px 4px;text-align:left;cursor:pointer}
.w-row.w-pastrow{background:#faf6ee;box-shadow:none;border:1px solid rgba(27,36,64,.06)}.w-row.w-pastrow b{font-size:17px;color:#4a5272}
.w-dl{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:8px 0 0}
.w-date{position:relative;display:inline-flex;align-items:center;gap:8px;border-radius:16px;background:#f6ecd6;padding:7px 12px;font:600 14.5px -apple-system,system-ui,sans-serif;color:#7a5c1c;cursor:pointer}
.w-date small{font-weight:500;color:#9a7a2c;font-size:13.5px}
.w-date input{position:absolute;inset:0;width:100%;height:100%;opacity:0;font-size:16px;cursor:pointer;-webkit-appearance:none;appearance:none;border:0;padding:0;margin:0}
.w-nod{border:0;background:none;color:var(--mute);font:500 13.5px -apple-system,system-ui,sans-serif;padding:8px 6px;cursor:pointer}
.w-live{display:flex;align-items:center;gap:12px;margin:14px 0 4px;padding:12px 16px;border-radius:16px;background:var(--ink);color:#fff;text-decoration:none}.w-live i{width:9px;height:9px;border-radius:50%;background:#4fc184;box-shadow:0 0 0 4px rgba(79,193,132,.25)}.w-live span{flex:1}.w-live b{display:block}.w-live small{display:block;opacity:.75;font-size:13px}
.w-back{display:inline-flex;align-items:center;gap:4px;border:0;background:none;color:var(--gold2);font:600 15px -apple-system,system-ui,sans-serif;padding:10px 0;cursor:pointer}
.w-title{font-size:30px;font-weight:400;line-height:1.15;margin:4px 0 2px}.w-by{color:var(--mute);font-size:15px}
.w-keys{display:flex;align-items:center;gap:5px;margin:16px 0 0;flex-wrap:nowrap}.w-kl{font:700 11px -apple-system,system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#7a5c16;margin-right:4px}
.w-kb{width:36px;height:36px;border-radius:18px;border:1px solid rgba(27,36,64,.15);background:#fff;font-size:20px;line-height:1;color:var(--ink);cursor:pointer;padding:0}.w-kb.s{width:30px;height:30px;font-size:16px}
.w-kv{min-width:38px;text-align:center;font:700 16px ui-monospace,Menlo,monospace;color:var(--gold2)}
.w-capo{margin-top:8px;font-size:13.5px;color:var(--mute)}
.w-acts{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}
.w-btn{display:inline-flex;align-items:center;gap:7px;height:44px;padding:0 18px;border-radius:22px;border:1px solid rgba(27,36,64,.16);background:#fff;color:var(--ink);font:600 15px -apple-system,system-ui,sans-serif;text-decoration:none;cursor:pointer}
.w-btn.pri{background:var(--ink);border-color:var(--ink);color:#fff}.w-btn[disabled]{opacity:.4}.w-del{color:#b3261e}
.w-notes{background:rgba(201,162,74,.12);border-radius:12px;padding:10px 12px;font-size:14.5px;margin:0 0 14px}
.w-chart{margin-top:6px}
.wc-s{margin:0 0 18px;padding:2px 0}.wc-h{margin:0 0 6px;font:700 11.5px -apple-system,system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#7a5c16}.wc-h i{font-style:normal;color:var(--mute);letter-spacing:0;text-transform:none;font-weight:600}
.wc-l{display:flex;flex-wrap:wrap;align-items:flex-end;font-size:17.5px;line-height:1.25;margin:0 0 7px}.wc-w{display:inline-flex;flex-direction:column;white-space:pre-wrap;max-width:100%}
.wc-c{font:700 14.5px/1.2 ui-monospace,Menlo,monospace;color:#a8812a;min-height:1.2em;padding-right:4px}.wc-t{white-space:pre-wrap;max-width:100%}.wc-only .wc-t{display:none}.wc-gap{height:12px}
.w-f{display:block;margin:12px 0}.w-f span{display:block;font-size:13px;font-weight:600;color:var(--mute);margin:0 0 5px}
.w-f input,.w-f select,.w-f textarea{width:100%;border:1px solid rgba(27,36,64,.16);border-radius:12px;background:#fff;padding:11px 12px;font:16px -apple-system,system-ui,sans-serif;color:var(--ink)}
.w-pastebtn{width:100%;justify-content:center;margin:4px 0 2px}.w-tidy{margin:4px 2px 0}.w-tidy .lnk{font-weight:600}
.w-f textarea#wf-src{font:14px/1.45 ui-monospace,Menlo,Consolas,monospace;white-space:pre;overflow-x:auto}
.w-two{display:grid;grid-template-columns:1fr 110px;gap:10px}
.w-found{font-size:13.5px;color:var(--mute);line-height:1.8}.w-sc{display:inline-block;min-width:26px;padding:0 6px;border-radius:8px;background:rgba(27,36,64,.07);font:700 12px ui-monospace,Menlo,monospace;color:var(--ink);text-align:center}
.w-hint{font-size:13.5px;color:var(--mute);margin:8px 2px}.w-warn{display:block;margin-top:6px;font-size:13px;color:#a05a2c}
.w-am{display:flex;flex-direction:column;gap:6px;margin-top:10px}.w-am button{display:flex;align-items:center;gap:10px;padding:8px;border-radius:12px;border:1px solid var(--line);background:#fff;text-align:left;font:inherit;color:var(--ink);cursor:pointer}
.w-am img{width:44px;height:44px;border-radius:6px;flex:none;background:#eee}.w-am span{flex:1;min-width:0}.w-am b{display:block;font-size:14.5px}.w-am small{display:block;font-size:12.5px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.w-am i{font-style:normal;font-size:12px;color:#3f9b6a;font-weight:700;flex:none}
.w-name{width:100%;border:0;border-bottom:1px solid var(--line);background:none;font-size:28px;padding:6px 0;margin:2px 0 4px;color:var(--ink)}
.w-items{display:flex;flex-direction:column;gap:8px}
.w-it{display:flex;align-items:center;gap:8px;padding:10px 10px 10px 12px;border-radius:14px;background:#fffdf8;box-shadow:0 2px 10px rgba(27,36,64,.05)}
.w-n{width:24px;height:24px;border-radius:12px;background:rgba(27,36,64,.07);font-size:12.5px;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none}
.w-itt{flex:1;min-width:0;border:0;background:none;text-align:left;font:inherit;color:var(--ink);padding:0;cursor:pointer}.w-itt b{display:block;font-size:17px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.w-itt small{display:block;font-size:12.5px;color:var(--mute)}
.w-ik{display:flex;align-items:center;gap:4px;flex:none}.w-ik b{min-width:34px;text-align:center;font:700 13px ui-monospace,Menlo,monospace;color:var(--gold2)}
.w-mv{display:flex;gap:2px;flex:none}.w-mv button{width:30px;height:30px;border:0;border-radius:15px;background:rgba(27,36,64,.05);color:var(--ink);cursor:pointer;padding:0}.w-mv button[disabled]{opacity:.25}
.jv.wsp{max-width:760px}.jv.wsong{max-width:none;padding-bottom:0}@media (min-width:700px){.jv.wsong{padding-left:28px;padding-right:28px}}.w-st{display:flex;align-items:center;gap:8px;margin-top:-4px}.w-st .sp{flex:1}
.w-btn.sm{height:38px;padding:0 14px;font-size:14px}.w-btn.ic{width:38px;padding:0;justify-content:center}
.wsong .w-title{font-size:24px;margin:2px 0 0}.w-sub{color:var(--mute);font-size:14px}
.wsong .w-keys{margin:10px 0 4px}.wsong .w-capo{margin:0 0 4px}
.wfit{position:relative;overflow:hidden;margin:8px -4px 0;border-radius:12px}
@media (max-height:520px){.wsong .w-title,.wsong .w-sub,.wsong .w-capo{display:none}.wsong .w-keys{margin:6px 0 0}.jv.wsong{padding-top:calc(env(safe-area-inset-top) + 8px)}}
.wfit .wc .wc-s{break-inside:avoid;margin:0 0 .65em;padding:.15em .35em .2em;border-radius:.5em}
.wfit .wc .wc-h{font-size:.6em;margin:0 0 .2em}.wfit .wc .wc-l{font-size:1em;margin:0 0 .22em;line-height:1.16}.wfit .wc .wc-c{font-size:.8em}.wfit .wc .wc-gap{height:.35em}
.wfit-pg{position:absolute;right:8px;bottom:6px;font:700 12px -apple-system,system-ui,sans-serif;color:var(--mute);background:rgba(244,239,227,.9);padding:3px 8px;border-radius:10px}
body.wsong-open #tabs{display:none}body.wsong-open{padding-bottom:0!important}
.wsong .w-st{gap:6px;margin-top:-8px}.wsong .w-back{padding:8px 6px 8px 0}
.w-tt{flex:1;min-width:0}.w-tt b{display:block;font-size:19px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.w-tt small{display:block;font-size:12px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.w-kchip{flex:none;height:36px;padding:0 12px;border-radius:18px;border:1px solid rgba(201,162,74,.5);background:rgba(201,162,74,.12);color:#7a5c16;font:700 13.5px ui-monospace,Menlo,monospace;cursor:pointer}.w-kchip.on{background:rgba(201,162,74,.3);border-color:#c9a24a;color:#5e4610}
.w-btn.gold{background:#c9a24a;border-color:#c9a24a;color:#fff}.w-btn.gold svg{fill:#fff;color:#fff}.w-pres{flex:none;padding:0 13px 0 11px;gap:5px}
.w-tools{margin:6px 0 2px;padding:8px 10px;border-radius:14px;background:#fffdf8;box-shadow:0 2px 10px rgba(27,36,64,.06)}.w-tools .w-keys{margin:0}.w-tools .w-acts{margin:8px 0 0}
.wfit .wc.inl .wc-l{display:block}.wfit .wc.inl .wc-w{display:inline;white-space:pre-wrap}.wfit .wc.inl .wc-t{display:inline}
.wfit .wc.inl .wc-c{display:inline;font-size:.66em;vertical-align:.62em;line-height:1;min-height:0;padding:0 .12em 0 0}.wfit .wc.inl .wc-c:empty{display:none}
.wfit .wc.inl .wc-in{position:relative}.wfit .wc.inl .wc-in>.wc-c{position:absolute;left:0;bottom:100%;padding:0;vertical-align:0;white-space:nowrap}.wfit .wc.inl .wc-hasin{padding-top:.55em}
.wc-in{position:relative}.wc-note{margin:0 0 .3em;font-size:.72em;font-style:italic;color:var(--mute,#7a7f96)}.wc-miss .wc-h i{color:#b4553a}
.wfit .wc.inl .wc-only .wc-c{font-size:.82em;vertical-align:0;padding-right:.5em}
.w-pick{position:fixed;top:0;right:0;bottom:0;left:0;background:rgba(15,22,40,.38);z-index:40;display:flex;align-items:flex-end;justify-content:center}
.w-pk{background:var(--bg);width:100%;max-width:560px;max-height:80vh;overflow:auto;border-radius:22px 22px 0 0;padding:18px 18px calc(20px + env(safe-area-inset-bottom))}.w-pk h3{margin:0 0 8px;font-weight:400;font-size:22px}
.w-pl label{display:flex;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px solid var(--line)}.w-pl input{width:22px;height:22px;flex:none}.w-pl b{display:block;font-weight:600}.w-pl small{display:block;color:var(--mute);font-size:13px}

.pray .pr-seg{margin:12px 0 18px}.pray .pr-sub{margin:-8px auto 18px;max-width:330px;background:none;padding:0;gap:4px}.pray .pr-sub button{height:30px;font-size:13px;font-weight:600;color:#6b7088;border-radius:15px}.pray .pr-sub button.on{background:#f3e7c7;color:#5d4510;box-shadow:none}.led-lead{margin:18px 2px 14px;color:#5b6280;font-size:15px;line-height:1.45;text-align:center}.led,.med{padding:22px 8px 4px;text-align:center}.med{padding-top:18px}.led-who{font-size:30px;line-height:1.2;margin:12px 0 0;color:var(--ink)}.led-ctl{display:flex;align-items:center;justify-content:center;gap:26px;margin:30px 0 14px}.led-sk{width:44px;height:44px;border:0;background:none;color:#8a8fa6;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;border-radius:50%}.led-sk:active{background:rgba(27,36,64,.06)}.led-ring{position:relative;width:112px;height:112px;border:0;border-radius:50%;background:none;padding:0;cursor:pointer;color:#5d4510}.led-ring>svg{position:absolute;inset:0;width:100%;height:100%}.led-in svg{width:30px;height:30px}.led-tr{fill:none;stroke:rgba(201,162,74,.22);stroke-width:2.2}.led-fg{fill:none;stroke:#c9a24a;stroke-width:2.6;stroke-linecap:round;transition:stroke-dasharray .4s linear}.led-in{position:absolute;inset:12px;border-radius:50%;background:#fbf4e3;box-shadow:0 8px 22px rgba(120,92,30,.16),inset 0 0 0 1px rgba(201,162,74,.25);display:flex;align-items:center;justify-content:center;transition:transform .2s}.led-ring:active .led-in{transform:scale(.96)}.led-opt{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;column-gap:22px;margin:6px 0 4px}.led-pick{position:relative;display:inline-flex;align-items:center;color:#6b7088;font:600 14px -apple-system,system-ui,sans-serif;padding:8px 6px;min-height:38px}.led-pick select{position:absolute;inset:0;width:100%;height:100%;opacity:0;font-size:16px;cursor:pointer;-webkit-appearance:none;appearance:none}.led-opt button{border:0;background:none;color:#6b7088;font:600 14px -apple-system,system-ui,sans-serif;padding:8px 6px;min-height:38px;cursor:pointer}.pr-nav>span:empty{flex:1}.med-n{font-size:13.5px;color:var(--mute)}.med-q{margin:14px auto 0;max-width:24ch;font-size:24px;line-height:1.42;color:var(--ink);text-wrap:balance}.med-q.l{font-size:20px;line-height:1.4;max-width:29ch}.med-q.xl{font-size:17.5px;line-height:1.4;max-width:34ch}.med-q.xxl{font-size:16px;line-height:1.36;max-width:36ch}.pray .pr-band.sm{height:72px}.pray .pr-nav.flow{position:static;background:none;margin-top:6px}.pr-eb.err{color:#9a4a2a;letter-spacing:.04em;text-transform:none;font-size:13.5px;font-weight:600}.med-opt{margin:2px 0 0}.med-ref{margin-top:14px;font-size:13px;color:#6b7088}.med-by{margin-top:4px;font-size:12.5px;color:#8a8fa6}.med-ctl{display:flex;justify-content:center;margin:20px 0 4px;min-height:58px;align-items:center}.med-go{min-width:170px;height:54px;padding:0 30px;border-radius:27px;border:1px solid rgba(201,162,74,.45);background:#fbf4e3;color:#5d4510;font:600 16px -apple-system,system-ui,sans-serif;cursor:pointer}.lp-line{display:flex;align-items:center;justify-content:center;gap:10px;margin:14px 0 -6px}.lp-line .led-sk[hidden]{display:flex;visibility:hidden}.lp-pp{display:inline-flex;align-items:center;gap:10px;min-height:44px;padding:0 18px 0 8px;border-radius:22px;border:1px solid rgba(201,162,74,.4);background:#fbf4e3;color:#5d4510;font:600 14.5px -apple-system,system-ui,sans-serif;cursor:pointer}.lp-pp i{display:flex;width:30px;height:30px;align-items:center;justify-content:center}.lp-pp i svg{width:18px;height:18px}.pr-mu{margin:8px auto 0;max-width:300px;padding:12px 16px 10px;border-radius:16px;background:#fff;border:1px solid rgba(27,36,64,.08);text-align:left}.pr-mu-row{display:flex;justify-content:space-between;align-items:center;gap:12px;font:500 14.5px -apple-system,system-ui,sans-serif;color:var(--ink);padding:2px 0 10px}#prmulv{-webkit-appearance:none;appearance:none;width:100%;height:4px;margin:12px 0 10px;border-radius:2px;background:linear-gradient(#c9a24a,#c9a24a) 0/var(--p,40%) 100% no-repeat,#e8e3d6;outline:none}#prmulv::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;border-radius:50%;background:#fff;border:1px solid rgba(201,162,74,.5);box-shadow:0 1px 4px rgba(27,36,64,.18)}#prmulv::-moz-range-thumb{width:24px;height:24px;border-radius:50%;background:#fff;border:1px solid rgba(201,162,74,.5)}.pr-mu .bp-l{display:flex;justify-content:space-between;font-size:12.5px;color:var(--mute)}#prmulv:disabled{opacity:.4}.pr-mu-none{margin:0;font-size:13.5px;color:var(--mute);line-height:1.4}.pr-sw{appearance:none;-webkit-appearance:none;flex:none;width:46px;height:28px;border-radius:14px;background:#dcd8cc;position:relative;cursor:pointer;transition:background .2s;margin:0}.pr-sw::before{content:'';position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:transform .2s}.pr-sw:checked{background:#c9a24a}.pr-sw:checked::before{transform:translateX(18px)}.pr-head{display:flex;align-items:center;justify-content:center;gap:10px;margin:0 auto}.pr-hc{min-width:150px;max-width:230px;display:flex;flex-direction:column;align-items:center;gap:5px}.pr-ha{flex:none;width:44px;height:44px;border:0;padding:0;background:radial-gradient(circle,rgba(27,36,64,.07) 0 16.5px,transparent 17.5px);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;border-radius:50%}.pr-ha:active{background:radial-gradient(circle,rgba(27,36,64,.13) 0 16.5px,transparent 17.5px)}.pr-ha[disabled]{opacity:.28;cursor:default}.pr-hc .med-n{font-size:12px;color:var(--mute);letter-spacing:.01em}.pr-hc .pr-dots i{width:5px;height:5px}.pr-hc .pr-dots i.on{width:14px}.lp-opt{margin:2px 0 -4px}.med-pp{width:54px;height:54px;border-radius:50%;border:1px solid rgba(201,162,74,.35);background:#fbf4e3;color:#5d4510;display:flex;align-items:center;justify-content:center;padding:0;cursor:pointer}.med-pp svg{width:22px;height:22px}.med-pp[disabled]{opacity:.45}
.pr-art{position:relative;border-radius:26px;overflow:hidden;box-shadow:0 10px 30px rgba(27,36,64,.12);background:#eadfca;transform:translateZ(0)}
.pr-art svg{display:block;width:100%;height:100%}
.pr-still{height:calc(100svh - var(--tabh) - 330px);min-height:280px;max-height:560px}
.pr-add{text-align:center;margin:26px 0 10px}.pr-addb{min-height:46px;padding:0 26px;border-radius:23px;border:1px solid rgba(27,36,64,.18);background:#fff;color:var(--ink);font:600 15px -apple-system,system-ui,sans-serif;cursor:pointer}.pr-add p{margin:12px 0 0;font-size:13.5px;color:var(--mute)}
.pr-st{text-align:center;font-size:13.5px;line-height:1.4;color:var(--mute);margin:4px auto 0;max-width:30ch;min-height:1.4em}
.pr-ctl{display:flex;align-items:center;justify-content:center;gap:36px;margin:28px 0 10px}
.pr-pp{width:80px;height:80px;border-radius:50%;border:0;background:var(--ink);color:#fbf6ea;display:flex;align-items:center;justify-content:center;box-shadow:0 10px 24px rgba(27,36,64,.22);cursor:pointer;padding:0;transition:transform .2s}
.pr-pp:active{transform:scale(.96)}
.pr-sk,.pr-ar{width:46px;height:46px;border-radius:50%;border:0;background:rgba(27,36,64,.06);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}
.pr-ar[disabled]{opacity:.28;cursor:default}
.pr-band{height:96px}
.pr-mini svg{width:20px;height:20px}.pr-mini{position:absolute;right:10px;bottom:10px;width:44px;height:44px;border-radius:50%;border:0;background:rgba(251,246,234,.88);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;box-shadow:0 2px 10px rgba(27,36,64,.12)}
.pr-g{padding:22px 8px 4px;text-align:center}
.pr-g.in-l{animation:prin-l .38s ease}.pr-g.in-r{animation:prin-r .38s ease}
@keyframes prin-l{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}@keyframes prin-r{from{opacity:0;transform:translateX(-14px)}to{opacity:1;transform:none}}
.pr-eb{font-size:11.5px;letter-spacing:.2em;font-weight:700;color:#7a5c16;text-transform:uppercase}
.pr-lp{font-size:29px;line-height:1.22;margin:12px 0 6px;color:var(--ink);text-wrap:balance}
.pr-lpr{font-size:13px;color:var(--mute);letter-spacing:.02em}
.pr-ins{font-size:16px;line-height:1.42;color:#3a4362;margin:14px auto 0;max-width:30ch;text-wrap:balance}
.pr-rule{width:34px;height:2px;background:var(--gold);opacity:.55;margin:18px auto 16px;border-radius:1px}
.pr-sup{margin:0}.pr-sup blockquote{margin:0 auto;max-width:34ch;font-size:18px;line-height:1.48;color:#2f3858;text-wrap:pretty;transition:opacity .22s}
.pr-sup blockquote.fade{opacity:0}
.pr-supr{margin-top:6px;border:0;background:none;color:var(--gold2);font:600 13.5px -apple-system,system-ui,sans-serif;display:inline-flex;gap:7px;align-items:center;padding:8px 12px;min-height:38px;cursor:pointer;border-radius:19px}
.pr-supr svg{opacity:.75}
.pr-nav{display:flex;align-items:center;justify-content:space-between;margin:14px -4px 0;padding:10px 4px 8px;position:sticky;bottom:var(--tabh);background:linear-gradient(rgba(244,239,227,0),var(--bg) 40%);z-index:2}
.pr-dots{display:flex;gap:7px;align-items:center}.pr-dots i{width:6px;height:6px;border-radius:3px;background:rgba(27,36,64,.16);transition:width .3s,background .3s}.pr-dots i.on{width:18px;background:var(--gold2)}
.pr-drift{animation:prdrift 80s ease-in-out infinite alternate}.pr-mist{animation:prmist 24s ease-in-out infinite alternate}
@keyframes prdrift{from{transform:translateX(-14px)}to{transform:translateX(14px)}}@keyframes prmist{from{opacity:.55}to{opacity:.9}}
@media (prefers-reduced-motion:reduce){.pr-drift,.pr-mist,.pr-g.in-l,.pr-g.in-r{animation:none}}
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
.jv.in-l{animation:jvl .26s ease-out}.jv.in-r{animation:jvr .26s ease-out}.jv-list.in-l{animation:jvl .22s ease-out}.jv-list.in-r{animation:jvr .22s ease-out}
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
body.bpsopen{overflow:hidden}body.bpsopen #np.on.mini{z-index:13}body.bpsopen.npon #bps .bps-sh{padding-bottom:calc(120px + env(safe-area-inset-bottom))}
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
.jv-cast{margin:10px 0 0}
.jv-cast-b{display:flex;align-items:center;gap:10px;width:100%;min-height:46px;padding:7px 14px 7px 9px;border-radius:18px;border:1px solid rgba(27,36,64,.09);background:rgba(255,255,255,.6);font:inherit;font-size:14.5px;color:var(--ink);cursor:pointer;-webkit-tap-highlight-color:transparent}
.jv-cast-b .stk{display:flex;align-items:center;min-width:28px;justify-content:center}.jv-cast-b .stk .medal{margin-left:-9px;box-shadow:0 0 0 2px #fbf7ec,inset 0 0 0 3px #fbf5e6}.jv-cast-b .stk .medal:first-child{margin-left:0}
.jv-cast-b .lb{flex:1;text-align:left;font-weight:600}.jv-cast-b .n{color:#5a6280;font-size:13.5px}
.jv-cast-b .chev{color:var(--gold2);transition:transform .2s}.jv-cast-b[aria-expanded=true] .chev{transform:rotate(180deg)}
.jv-cast-l{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;padding:10px 0 2px}
.jv-cast-l .chip{display:flex;align-items:center;gap:9px;min-height:48px;padding:6px 10px 6px 7px;border-radius:16px;border:1px solid rgba(168,129,42,.32);background:#fff;font:inherit;color:var(--ink);text-align:left;cursor:pointer;min-width:0}
.jv-cast-l .chip span{display:flex;flex-direction:column;min-width:0}.jv-cast-l .chip b{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.jv-cast-l .chip small{font-size:11.5px;color:#5a6280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jv-art.sm svg{height:150px}
.jv-cap{position:absolute;left:0;right:0;bottom:0;padding:34px 16px 14px;background:linear-gradient(180deg,rgba(246,238,218,0),rgba(246,238,218,.78) 38%,rgba(246,238,218,.92));color:var(--ink)}
.jv-cap i{display:block;font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:21px}
.jv-cap .cs{font-size:13.5px;line-height:1.4;color:#2c3554}
.jv-cap button{font-size:inherit}
.jv-seg{margin:22px 0 6px}.jv-sgr{display:flex;gap:10px}
.jvz .jv-seg{position:sticky;top:calc(env(safe-area-inset-top) + 56px);z-index:3;background:rgba(244,239,227,.96);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);margin:10px -20px 14px;padding:2px 20px 4px}
.jv-seg button{flex:1;font:11.5px -apple-system,system-ui,sans-serif;color:#5a6280;display:flex;flex-direction:column;gap:6px;border:0;background:none;padding:6px 0 4px;text-align:left;cursor:pointer}
.jv-seg button.now{color:var(--ink);font-weight:650}
@keyframes flash{0%{background:rgba(201,162,74,.28)}100%{background:transparent}}.flash{animation:flash 1.2s ease-out;border-radius:12px}
.jv-none{font-size:13.5px;color:#5a6280;margin:4px 2px}
.jv-seg i{display:block;height:3px;border-radius:2px;background:rgba(27,36,64,.12);overflow:hidden}
.jv-seg b{display:block;height:100%;background:#9a7524;border-radius:2px;transition:width .4s}
.jv-next{display:flex;align-items:center;gap:14px;width:100%;text-align:left;padding:14px;border:0;border-radius:22px;background:#fffdf8;color:var(--ink);box-shadow:0 6px 20px rgba(27,36,64,.08);cursor:pointer;font:inherit}
.jv-next:active{transform:scale(.99)}
.jread{margin:-2px 0 14px;padding:14px 18px 16px;background:#fffdf7;border:1px solid rgba(27,36,64,.08);border-radius:0 0 20px 20px}
.jr-bar,.jr-end{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.jr-end{margin-top:14px}
.jr-b{height:36px;padding:0 14px;border-radius:18px;border:1px solid rgba(27,36,64,.14);background:#fff;font:600 14px -apple-system,system-ui,sans-serif;color:var(--ink);display:inline-flex;align-items:center;gap:6px}
.jr-open{width:44px;height:44px;flex:none;border-radius:22px;border:1px solid rgba(27,36,64,.12);background:#fff;color:var(--ink);display:flex;align-items:center;justify-content:center;margin-left:6px;padding:0}.jr-open.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.jr-fab{position:fixed;right:16px;z-index:7;height:46px;padding:0 18px;border-radius:23px;border:0;background:var(--ink);color:#fff;font:700 15px -apple-system,system-ui,sans-serif;display:flex;align-items:center;gap:8px;box-shadow:0 6px 20px rgba(27,36,64,.28);opacity:0;pointer-events:none;transform:translateY(8px);transition:opacity .2s,transform .2s}
.jr-fab.show{opacity:1;pointer-events:auto;transform:none}
.jr-b.pri{background:var(--ink);color:#fff;border-color:var(--ink)}
.jr-done{height:40px;padding:0 16px;border-radius:20px;border:0;background:var(--ink);color:#fff;font:700 14px -apple-system,system-ui,sans-serif}.jr-ok{color:var(--gold2);font-weight:700;margin-right:6px}
.jr-txt{font:19px/1.65 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink);margin-top:12px}.jr-txt h4{font:700 12px -apple-system,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:var(--gold2);margin:16px 0 6px}
.jr-txt p{margin:0 0 12px}.jr-txt sup{font-size:.62em;color:var(--gold2);font-weight:700;margin-right:3px}.jr-txt .poem{padding-left:14px}
.jw[data-row],.jw[data-scrrow],.voice[data-row]{cursor:pointer;-webkit-tap-highlight-color:transparent}.jw[data-row]:active,.jw[data-scrrow]:active{opacity:.72}
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
.cprefs{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 4px}.cprefs .btn{padding:6px 12px}.cprefs .btn.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.jv-seg button.on{color:var(--ink);font-weight:700}.jv-tabbed>.jv-sec:not(.jv-tsec){display:none}.jv-tabbed{margin-top:8px}
.jv-tsec{display:flex;align-items:center;justify-content:space-between;gap:10px}
.jv-tg{display:inline-flex;padding:2px;border-radius:14px;background:rgba(27,36,64,.07);letter-spacing:normal;text-transform:none}
.jv-tg button{border:0;background:none;font:600 12.5px -apple-system,system-ui,sans-serif;color:#4a5272;padding:5px 11px;border-radius:12px;cursor:pointer}
.jv-tg button.on{background:#fff;color:var(--ink);box-shadow:0 1px 3px rgba(27,36,64,.12)}
.jv-why{font-size:12.5px;line-height:1.45;color:#5a6280;margin:2px 2px 6px 56px}.jv-why b{color:#4a5272;font-weight:650}
.jv-mk{margin:-8px 2px 6px 56px}.jv-mk .lnk{font-size:12px;color:#7b8199;text-decoration:none;font-weight:600}.jv-mk .lnk::before{content:"↑ "}
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
#bps{position:fixed;top:0;right:0;bottom:0;left:0;z-index:12}
#bps .bps-bg{position:absolute;top:0;right:0;bottom:0;left:0;background:rgba(27,36,64,.32);opacity:0;transition:opacity .25s}
#bps .bps-sh{position:absolute;left:0;right:0;bottom:0;top:calc(env(safe-area-inset-top) + 40px);max-width:560px;margin:0 auto;background:#f7f2e7;border-radius:30px 30px 0 0;padding:6px 22px calc(28px + env(safe-area-inset-bottom));overflow-y:auto;-webkit-overflow-scrolling:touch;transform:translateY(100%);transition:transform .3s cubic-bezier(.2,.8,.2,1);font-family:-apple-system,system-ui,sans-serif;color:var(--ink)}
#bps.on .bps-bg{opacity:1}#bps.on .bps-sh{transform:none}
.grab2{display:block;width:60px;height:24px;margin:0 auto;border:0;background:none;position:relative;cursor:pointer}.grab2::after{content:'';position:absolute;left:12px;right:12px;top:9px;height:5px;border-radius:3px;background:rgba(27,36,64,.22)}
.bps-hd{display:flex;gap:16px;align-items:flex-end;margin-top:10px}
.tp-back{border:0;background:none;padding:8px 0;margin:4px 0 2px;font:600 14px -apple-system,system-ui,sans-serif;color:#7a5c16;cursor:pointer}
.tp-ph{display:flex;align-items:center;gap:14px;justify-content:space-between;margin:4px 0 12px}
.tp-pl{flex:none;width:48px;height:48px;border-radius:50%;border:0;background:#c9a24a;display:flex;align-items:center;justify-content:center;cursor:pointer}
.tp-tx{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;line-height:1.6;color:#1b2440}.tp-tx p{margin:0 0 12px}.tp-tx sup{font:700 10.5px -apple-system,system-ui,sans-serif;color:#a8812a;margin-right:3px}
.tp-ch{font:700 11px -apple-system,system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#7a5c16;margin:18px 0 8px}.tp-hh{font:600 13px -apple-system,system-ui,sans-serif;color:#5a6280;margin:14px 0 6px}
.tp-j{display:block;margin:14px 0 8px;border:0;background:none;padding:10px 0;font:600 14px -apple-system,system-ui,sans-serif;color:#4a5272;cursor:pointer;text-decoration:underline;text-decoration-color:rgba(90,98,128,.35);text-underline-offset:3px}
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
.bbv{padding-top:0}
.bb-h{position:sticky;top:0;z-index:4;margin:0 -20px;padding:calc(env(safe-area-inset-top) + 12px) 20px 8px;background:rgba(244,239,227,.95);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:0 10px}
.jv-secst .jv-seg{display:none}.jv-secst .jv-tr{margin-top:6px}
.bb-left,#np .np-left{font:500 13px -apple-system,system-ui,sans-serif;color:#8a8fa3;letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bb-left{flex-basis:100%;margin-top:-2px}.bb-left:empty{display:none}.bb-left b,#np .np-left b{font-weight:600;color:#5b6077}.bb-left i,#np .np-left i{font-style:normal;margin:0 7px}
#np .np-left{text-align:center;margin:8px 0 0}#np .np-left[hidden],#np.mini .np-left{display:none}
.bb-tt{border:0;background:none;padding:4px 0;font:500 27px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink);display:flex;align-items:center;gap:8px;cursor:pointer;min-width:0}.bb-tt span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bb-tt i{font-style:normal;font-size:14px;color:var(--gold2)}
.bb-in{flex:none;height:32px;padding:0 12px;border-radius:16px;border:1px solid rgba(201,162,74,.45);background:#fffaf0;color:var(--gold2);font:700 13px -apple-system,system-ui,sans-serif;cursor:pointer}.bb-in.on{background:#c9a24a;color:#fff;border-color:#c9a24a}
.bb-up{display:block;margin:10px auto 0;border:0;background:none;color:var(--gold2);font:700 14px -apple-system,system-ui,sans-serif;padding:8px 12px;cursor:pointer}.bb-up[hidden]{display:none}
.bb-tx{font:20px/1.7 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink);padding-bottom:140px}.bb-wait{font:15px -apple-system,system-ui,sans-serif;color:var(--mute);padding:30px 0}
.bb-ch{font:500 26px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;margin:26px 0 6px;color:var(--ink)}.bb-sec:first-child .bb-ch{display:none}   /* the bar above already names it */
.bb-body h4{font:700 12px -apple-system,system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--gold2);margin:18px 0 6px}.bb-body sup{font-size:.58em;color:var(--gold2);font-weight:700;margin-right:3px}.bb-body p{margin:0 0 12px}.bb-body .poem{padding-left:14px}.bb-body .ptitle{font-style:italic;color:var(--mute);font-size:.85em}
.bb-body .vs.now{background:rgba(201,162,74,.22);border-radius:4px;box-shadow:0 0 0 3px rgba(201,162,74,.22)}
.bb-fab{position:fixed;right:18px;bottom:100px;z-index:7;height:50px;padding:0 20px 0 16px;border-radius:25px;border:0;background:#c9a24a;color:#fff;font:700 16px -apple-system,system-ui,sans-serif;display:flex;align-items:center;gap:8px;box-shadow:0 8px 22px rgba(168,129,42,.35);cursor:pointer}.bb-fab[hidden]{display:none}
.bb-js .bb-k{font:700 11px -apple-system,system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2);margin:16px 4px 8px}
.bb-rec{display:flex;gap:8px;flex-wrap:wrap}.bb-rec button{height:34px;padding:0 13px;border-radius:17px;background:#fff;border:1px solid rgba(27,36,64,.1);font:600 13.5px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}
.bb-cg{display:grid;grid-template-columns:repeat(7,1fr);gap:7px}.bb-cg button{height:42px;border-radius:21px;background:#fff;border:1px solid rgba(27,36,64,.08);font:600 15px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}.bb-cg button.here{background:#c9a24a;color:#fff;border-color:#c9a24a}
.bb-bk{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.bb-bk button{min-height:40px;padding:4px;border-radius:12px;background:#fff;border:1px solid rgba(27,36,64,.08);font:600 13px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}.bb-bk button.on{background:rgba(201,162,74,.22);border-color:#c9a24a;color:#5e4610}
.bb-sf{display:flex;align-items:center;gap:9px;height:46px;margin:0 2px 4px;padding:0 6px 0 15px;border-radius:23px;background:#fffdf7;border:1px solid rgba(27,36,64,.1);box-shadow:0 1px 2px rgba(60,45,10,.05);color:#8a8fa3;transition:border-color .15s,box-shadow .15s}
.bb-sf:focus-within{border-color:#c9a24a;box-shadow:0 0 0 3px rgba(201,162,74,.18);color:#a8812a}
.bb-sf input{flex:1;min-width:0;border:0;background:none;outline:none;font:500 16px -apple-system,system-ui,sans-serif;color:var(--ink);-webkit-appearance:none;appearance:none}.bb-sf input::placeholder{color:#9a9eb0}.bb-sf input::-webkit-search-cancel-button{display:none}
.bb-sf button{flex:none;width:32px;height:32px;border-radius:50%;border:0;background:rgba(27,36,64,.07);color:#5b6077;font-size:13px;cursor:pointer}
#bbmain.typing .bb-cur{display:none}
.bb-jr{display:flex;align-items:center;justify-content:space-between;width:100%;margin:12px 0 2px;padding:12px 16px;border-radius:16px;background:#fff;border:1px solid rgba(201,162,74,.55);box-shadow:0 2px 10px rgba(201,162,74,.12);text-align:left;cursor:pointer}
.bb-jr small{display:block;font:700 10.5px -apple-system,system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--gold2)}.bb-jr b{font:500 21px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink)}.bb-jr i{font-style:normal;font-size:22px;color:#c9a24a}
.bb-flt{display:flex;gap:6px;overflow-x:auto;margin:0 0 6px;padding:0 2px 2px;scrollbar-width:none}.bb-flt::-webkit-scrollbar{display:none}
.bb-flt button{flex:none;height:30px;padding:0 12px;border-radius:15px;border:1px solid rgba(27,36,64,.1);background:#fff;font:600 12.5px -apple-system,system-ui,sans-serif;color:#5b6077;cursor:pointer}.bb-flt button.on{background:rgba(201,162,74,.2);border-color:#c9a24a;color:#5e4610}
.bb-vr{display:block;width:100%;text-align:left;padding:11px 4px;border:0;border-bottom:1px solid rgba(27,36,64,.07);background:none;cursor:pointer}
.bb-vr b{display:block;font:600 13px -apple-system,system-ui,sans-serif;color:var(--gold2);margin-bottom:3px}.bb-vr span{display:block;font:400 16px/1.45 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--ink)}.bb-vr mark{background:rgba(201,162,74,.28);color:inherit;border-radius:3px;padding:0 1px}
.bb-more{display:block;margin:12px auto 4px;height:36px;padding:0 18px;border-radius:18px;border:1px solid rgba(27,36,64,.12);background:#fff;font:600 13.5px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}
.bb-none{margin:12px 4px;color:#7a7f93;font-size:14.5px}
.vs.bb-flash{background:rgba(201,162,74,.28);border-radius:6px;transition:background 1.2s ease}
.lib .bp-cont{background:#fffdf7;color:var(--ink);border:1px solid rgba(27,36,64,.08);box-shadow:0 2px 10px rgba(27,36,64,.06);margin:4px 0 14px}.lib .bp-cont small{color:var(--gold2)}.lib .bp-cont em{color:var(--mute)}.lib .bp-cont .bp-pp{background:#c9a24a;color:#fff}.lib .bp-cont .bp-pp svg path,.lib .bp-cont .bp-pp svg rect{fill:#fff}
.lib-ser{margin-top:6px}
.sh-sec{display:flex;align-items:baseline;justify-content:space-between}
.sh-len{position:relative;font:600 13px -apple-system,system-ui,sans-serif;letter-spacing:0;text-transform:none;color:var(--gold2);cursor:pointer}.sh-len select{position:absolute;top:0;right:0;bottom:0;left:0;width:100%;opacity:0;font-size:16px;cursor:pointer}
.lib-t .av.sh-av{background:#c9a24a;color:#fff}.lib-t.sh-row em{color:var(--gold2)}.lib-t .sh-pl{font-style:normal;color:var(--gold2);display:flex;align-items:center}
.sh-th{display:flex;align-items:center;justify-content:space-between;gap:10px}.sh-tb{height:36px;padding:0 14px;border-radius:18px;border:1px solid rgba(201,162,74,.45);background:#fffaf0;color:var(--gold2);font:700 14px -apple-system,system-ui,sans-serif;display:flex;align-items:center;gap:6px;flex:none;margin-top:4px}
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


.jv-back svg{flex:none}.jv-back{display:inline-flex;align-items:center;gap:5px}
.t-ctl{display:flex;flex-direction:column;gap:10px;margin:0 0 6px}
.t-sort{display:flex;padding:3px;border-radius:18px;background:rgba(27,36,64,.07)}
.lib-seg{margin:10px 0 4px}.t-who{margin:0 0 6px;overflow-x:auto}.t-who button{flex:1 0 auto;padding:0 10px}
.lib-lead{font-size:13.5px;color:#5a6280;margin:14px 2px 6px}
.lib-tp{display:flex;align-items:center;gap:12px;width:100%;padding:13px 4px;border:0;border-bottom:1px solid rgba(27,36,64,.08);background:none;text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.lib-tp>span:not(.tp-ic){flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.lib-tp b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;font-weight:500}.lib-tp em{font-style:normal;font-size:12.5px;color:#5a6280;line-height:1.35;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}.lib-tp i{font-style:normal;font-size:12.5px;font-weight:600;color:#7a5c16}
.tp-ic{flex:none;display:flex;align-items:center;justify-content:center;border-radius:11px}
.tp-hd{display:flex;align-items:center;gap:14px;margin:6px 4px 0}
.lib-bk{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.lib-bk button{display:flex;justify-content:space-between;align-items:baseline;gap:6px;padding:11px 12px;border:0;border-radius:14px;background:#fffdf8;color:var(--ink);text-align:left;cursor:pointer;font:inherit;min-width:0}
.lib-bk b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:16px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lib-bk em{font-style:normal;font-size:12px;color:#7a5c16;font-weight:600}
.tp-k{display:flex;align-items:center;gap:10px;width:100%;padding:10px 4px;border:0;border-bottom:1px solid rgba(27,36,64,.08);background:none;text-align:left;color:var(--ink);cursor:pointer;font:inherit;flex-wrap:wrap}
.tp-k b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:16.5px;font-weight:500;flex:none}.tp-k span{flex:1;min-width:140px;font-size:13px;color:#5a6280}.tp-k i{font-style:normal;color:#5a6280}
.tp-sc{display:flex;flex-direction:column;gap:2px;width:100%;margin:4px 0;padding:12px 16px;border:0;border-radius:18px;background:radial-gradient(circle at 86% 20%,rgba(201,162,74,.22),rgba(201,162,74,0) 45%),#1b2440;color:#fff;text-align:left;cursor:pointer;font:inherit}
.tp-sc small{font-size:10px;font-weight:650;letter-spacing:.16em;text-transform:uppercase;color:#e9cf8c}.tp-sc b{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;font-weight:500}.tp-sc span{font-size:12.5px;color:rgba(255,255,255,.75)}
.jv-rd{display:block;margin:6px 0 2px 44px;padding:6px 0;border:0;background:none;font:600 13px -apple-system,system-ui,sans-serif;color:#7a5c16;cursor:pointer}
.jv-itx{margin:4px 2px 6px 44px;font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:17px;line-height:1.55;color:#2c3554}.jv-itx p{margin:0 0 .8em}
.itx p{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:18px;line-height:1.6;margin:0 0 .9em}
.jv-tp{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:22px 2px 4px}.jv-tp span{width:100%;font-size:10.5px;font-weight:650;letter-spacing:.2em;text-transform:uppercase;color:#7a5c16}
/* the Journey stop: a calm header, then one card style for every row (introduction, scripture, core, go deeper) */
.jv-tr{display:flex;align-items:center;gap:10px;margin:6px 0 18px}
.jv .jv-tr .jv-t{flex:1;min-width:0;margin:0;font-size:38px}
.jv-ar{flex:none;width:42px;height:42px;border-radius:21px;border:0;background:rgba(27,36,64,.07);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}.jv-ar:disabled{opacity:.3;cursor:default}
.jv-ban svg{height:128px}.jv-ban .jv-cap{padding:30px 16px 14px}.jv-ban .jv-cap .cs{font-size:14.5px;line-height:1.42}
.jv-cast{margin:16px 0 0}.jv-cast:empty{display:none}
.jv-ppr{display:flex;align-items:center;gap:8px;margin-right:-20px}.jv-pps{flex:1;min-width:0;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;padding:2px 20px 2px 0;-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent)}.jv-pps::-webkit-scrollbar{display:none}
.jv-pl{flex:none;font-size:10.5px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:#5a6280;margin-right:4px}
.jv-chip{flex:none;display:inline-flex;align-items:center;gap:7px;height:38px;padding:0 13px 0 5px;border-radius:19px;border:1px solid rgba(168,129,42,.35);background:#fff;font:600 14px -apple-system,system-ui,sans-serif;color:var(--ink);cursor:pointer}
.jv-chip span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.jv-chip .medal{flex:none}.jv-chip.more{flex:none;padding:0 14px;color:#7a5c16}
.jv-nav:empty{display:none}
.jv-seg button{font-size:13px;gap:8px}.jv-seg i{height:4px}
.jv-st{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:19px;line-height:1.2;color:var(--ink);height:0;opacity:0;overflow:hidden;transition:height .18s,opacity .18s,margin .18s}
.jvz .jv-seg{margin:22px -20px 6px;padding:4px 20px 8px}.jvz .jv-seg.stuck{border-bottom:1px solid rgba(27,36,64,.06)}.jv-seg.stuck .jv-st{height:24px;opacity:1;margin:0 0 8px}
.jv-tabbed>.jv-sec{margin:18px 2px 12px;font-size:11.5px;letter-spacing:.18em}
.jv-sk{border:0;background:none;padding:6px 0;font:600 12.5px -apple-system,system-ui,sans-serif;letter-spacing:normal;text-transform:none;color:#5a6280;cursor:pointer;text-decoration:underline;text-decoration-color:rgba(90,98,128,.35);text-underline-offset:3px}
.jv .jw{background:#fffdf8;border-radius:16px;box-shadow:0 3px 12px rgba(27,36,64,.06);padding:10px 14px 10px 10px;margin:0 0 12px;gap:12px}
.jv .jpb{width:40px;height:40px;background:rgba(27,36,64,.07)}
.jv .jw.pl .jpb{background:rgba(168,129,42,.18);color:#7a5c16}
.jv .jw-t b{font-size:17px}.jv .jw-t span{margin-top:2px}.jv .jw-t span+span{white-space:normal}
.jv .jw.up .jw-t b{color:inherit}
.jw-up{font-style:normal;color:#7a5c16;font-weight:650}
.jw-go{flex:none;color:#a8812a}
.jv .jv-sub{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#5a6280;margin:18px 4px 10px}
.jv-deep .jw{margin-bottom:7px;padding:8px 13px 8px 9px}.jv-deep .jv-sub{margin:12px 4px 7px}.jv-deep>.jv-sec{margin-bottom:8px}
.jv .jv-why{margin:-4px 4px 12px 4px}
#np .np-top:has(.np-core:not([hidden])) .np-lab{display:none}#np .np-top button.np-core{width:auto;margin-left:auto;white-space:nowrap;flex:none;height:32px;padding:0 12px;border-radius:16px;border:1px solid rgba(154,117,36,.4);background:none;color:var(--gold2);font:600 12.5px -apple-system,system-ui,sans-serif;cursor:pointer}
#np .np-top .np-core:not([hidden])+#np-fav{margin-left:8px}#np.mini .np-core{display:none}
.jv-tp button{height:34px;padding:0 14px;border:1px solid rgba(154,117,36,.35);border-radius:17px;background:#fffdf8;color:#1b2440;font:600 13.5px -apple-system,system-ui,sans-serif;cursor:pointer}
.bp-gs{font-size:13px;color:#5a6280;margin:0 2px 2px}
.t-sort button{flex:1;height:34px;border:0;border-radius:15px;background:none;font:600 13.5px -apple-system,system-ui,sans-serif;color:#4a5272;cursor:pointer}
.t-sort button.on{background:#fff;color:var(--ink);box-shadow:0 1px 4px rgba(27,36,64,.14)}.tp-seg{position:sticky;top:-6px;z-index:3;background:#f7f2e7;margin:16px -22px 8px;padding:8px 22px 6px}.tp-seg .t-sort button i{font-style:normal;font-weight:500;color:#8a8fa6;margin-left:5px}.tp-segl{font:400 13px -apple-system,system-ui,sans-serif;color:#7b8098;margin:6px 2px 0}
.t-q{display:flex;align-items:center;gap:8px;height:40px;padding:0 14px;border-radius:20px;background:#fff;border:1px solid rgba(27,36,64,.1);color:#5a6280}
.t-q input{flex:1;min-width:0;border:0;background:none;font:15px -apple-system,system-ui,sans-serif;color:var(--ink);outline:none}
.tr2{display:flex;align-items:center;gap:12px;padding:10px 2px}
.vsrch{position:absolute;top:calc(env(safe-area-inset-top) + 16px);right:60px;width:36px;height:36px;border-radius:50%;border:0;background:rgba(27,36,64,.06);color:#4a5272;display:flex;align-items:center;justify-content:center;cursor:pointer}
#np .np-top #np-fav{margin-left:auto;color:var(--mute)}#np .np-top #np-fav.on{color:var(--gold2)}#np .np-top #np-fav.on path{fill:currentColor}#np .np-top #np-fav[hidden]+#np-srch{margin-left:auto}
#np-core,#np-fav{display:none!important}#np .np-top #np-srch{color:var(--mute);margin-left:auto}#np.mini #np-srch,#np.mini #np-fav{display:none}
#gsr{position:fixed;top:0;right:0;bottom:0;left:0;z-index:30;background:#f4efe3;display:flex;flex-direction:column;opacity:0;transform:translateY(12px);transition:opacity .18s,transform .18s}
#gsr.on{opacity:1;transform:none}
#gsr .sh{display:flex;gap:10px;align-items:center;padding:calc(env(safe-area-inset-top) + 10px) 16px 10px}
#gsr .sbox{flex:1;min-width:0;display:flex;align-items:center;gap:8px;height:44px;padding:0 14px;border-radius:22px;background:#fff;box-shadow:0 1px 0 rgba(27,36,64,.06),0 0 0 1px rgba(27,36,64,.08)}
#gsr input::-webkit-search-cancel-button,#gsr input::-webkit-search-decoration{-webkit-appearance:none;appearance:none;display:none}#gsr input{flex:1;-webkit-appearance:none;appearance:none;min-width:0;border:0;outline:0;background:none;font:17px -apple-system,system-ui,sans-serif;color:var(--ink)}
#gsr .sx{border:0;background:none;color:var(--mute);font-size:15px;padding:6px;cursor:pointer}
#gsr .scan{flex:none;border:0;background:none;color:var(--gold2);font:600 16px -apple-system,system-ui,sans-serif;padding:8px 2px;cursor:pointer}
#gsr .sr{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:4px 16px calc(30px + env(safe-area-inset-bottom))}
#gsr .sg{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--gold2);font-weight:700;margin:18px 4px 6px}
#gsr .si{display:flex;align-items:center;gap:12px;width:100%;text-align:left;border:0;background:none;padding:11px 4px;border-top:1px solid rgba(27,36,64,.07);cursor:pointer;color:var(--ink);font:inherit}
#gsr .si:active{background:rgba(27,36,64,.04)}
#gsr .si b{display:block;font:400 17px/1.3 'Iowan Old Style',Palatino,Georgia,serif;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#gsr .si span{display:block;font-size:13px;color:var(--mute);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#gsr .si .vt{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
#gsr .si i{font-style:normal;color:var(--mute);margin-left:auto;flex:none}
#gsr .si .sk{flex:none;width:30px;height:30px;border-radius:50%;background:rgba(27,36,64,.06);display:flex;align-items:center;justify-content:center;color:#4a5272}
#gsr .si>div{min-width:0;flex:1}
#gsr mark{background:rgba(201,162,74,.28);color:inherit;border-radius:3px;padding:0 1px}
#gsr .pc{background:#fff;border-radius:18px;padding:16px 16px 14px;margin:10px 0 4px;box-shadow:0 1px 0 rgba(27,36,64,.05),0 0 0 1px rgba(27,36,64,.06)}
#gsr .pc h3{margin:0;font:400 24px 'Iowan Old Style',Palatino,Georgia,serif;color:var(--ink)}
#gsr .pc p{margin:8px 0 0;font:16px/1.5 'Iowan Old Style',Palatino,Georgia,serif;color:#3a4160}
#gsr .pc p sup{color:var(--gold2);font:600 10px -apple-system,system-ui,sans-serif;margin-right:2px}
#gsr .pa{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
#gsr .pa button{border:0;border-radius:18px;height:36px;padding:0 14px;font:600 14px -apple-system,system-ui,sans-serif;cursor:pointer;background:rgba(27,36,64,.07);color:var(--ink)}
#gsr .pa button.pri{background:var(--gold);color:#fff}
#gsr .chips{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 0}
#gsr .chips button{border:0;border-radius:16px;padding:8px 12px;background:rgba(27,36,64,.06);color:var(--ink);font:14px -apple-system,system-ui,sans-serif;cursor:pointer}
#gsr .more{border:0;background:none;color:var(--gold2);font:600 14px -apple-system,system-ui,sans-serif;padding:12px 4px;cursor:pointer}
#gsr .none{color:var(--mute);margin:28px 4px;font-size:15px}.tr2[data-open]{cursor:pointer}.tr2[data-open]:active{background:rgba(27,36,64,.04)}.tr2+.tr2{border-top:1px solid rgba(27,36,64,.07)}
.tr2 .jw-t .t3{font-size:12px;color:#7a5c16}.tr2.heard .jw-t b{color:#5a6280}
#np.mini{background:#fffcf5;color:var(--ink);border:1px solid rgba(201,162,74,.32);box-shadow:0 10px 26px rgba(80,60,20,.16)}
#np.mini .t{color:var(--ink)}#np.mini .s,#np.mini .times{color:#6b7088}#np.mini .ctl button,#np.mini .ctl2>button,#np.mini .spd button,#np.mini #spd{color:var(--ink)}
#np.mini .spd{background:#f4efe3;border-color:rgba(27,36,64,.1)}#np.mini .grab{background:rgba(27,36,64,.15)}#np.mini #np-hl{background:rgba(201,162,74,.18)}#np.mini #np-hl i{background:#c9a24a}
#np.mini .s[data-left]::after{content:attr(data-left)}
body.npslim #np.mini{left:48px;right:48px;padding:5px 6px 7px 16px;border-radius:26px}body.npslim #np.mini .s,body.npslim #np.mini .ctl2,body.npslim #np.mini .ctl #nxt{display:none!important}
body.npslim #np.mini .ctl .big{width:36px!important;height:36px!important}body.npslim #np.mini .t{grid-row:1/3;align-self:center}
#np .np-cut{display:flex;justify-content:center;margin:10px 0 0}#np .np-cut button{border:0;background:none;padding:6px 10px;font:600 13px -apple-system,system-ui,sans-serif;color:#8a6a1c;text-decoration:underline;text-decoration-color:rgba(201,162,74,.5);text-underline-offset:3px;cursor:pointer}#np.mini .np-cut{display:none}
#note .note-undo{margin-left:12px;border:0;background:none;color:#f0d79a;font:700 14px -apple-system,system-ui,sans-serif;cursor:pointer}
.pt-lock{display:inline-block;vertical-align:1px;margin-left:6px;color:#9a8a6a}.pt-note{margin:-2px 2px 6px;font:600 12px -apple-system,system-ui,sans-serif;color:#9a8a6a;letter-spacing:.02em}
</style></head><body>
<div id="topbar" aria-hidden="true"></div><button id="bookhd" aria-label="Go to this book's opening stop"></button><div class="top"><span id="pct" style="display:none"></span><button id="srch" aria-label="Search or go to a chapter"><svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg><span>Search</span></button><button id="mapbtn" aria-label="Map of the journey"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Zm0 0v13m6-10.5v13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg></button><button id="gear">⋯</button></div>
<div id="sheetbg" hidden></div><div id="sheet" role="dialog" aria-modal="true" hidden><div class="sh-grab"></div><div class="sh-top"><button id="shback" aria-label="Back" hidden>‹</button><span class="sh-kind" id="shkind"></span><button id="shx" aria-label="Close">✕</button></div><div id="shbody"></div></div>
<div id="jump" role="dialog" aria-modal="true" aria-label="Go to" hidden><div class="jp-top"><label class="jp-field"><svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><input id="jq" type="search" placeholder="Nehemiah, John 3:16, Goliath" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" enterkeyhint="go" aria-label="Search"></label><button id="jx">Close</button></div><div id="jbody"></div></div><div id="mapv" role="dialog" aria-modal="true" aria-label="Map of the journey" hidden><svg id="mapsvg" preserveAspectRatio="xMidYMid meet"></svg><div class="mv-top"><button id="mvx" aria-label="Close map">✕</button><div class="mv-title" id="mvtitle">Your journey</div></div><div class="mv-panel" id="mvpanel"><div class="mv-card" id="mvcard"></div><div class="mv-legs" id="mvlegs" aria-label="Legs of the journey"></div></div></div>
<div id="zt" hidden></div><div id="main"></div><nav id="tabs" aria-label="Main"></nav><div id="bps" hidden></div>
<div id="np"><div class="grab"></div>
<div class="np-top"><button id="np-min" aria-label="Shrink player"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><span class="np-lab">Now playing</span><button id="np-core" class="np-core" hidden>Make Core</button><button id="np-fav" aria-label="Save this teaching" aria-pressed="false"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M7 4h10v16l-5-3.6L7 20z"/></svg></button><button id="np-srch" aria-label="Search"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg></button><button id="cls" aria-label="Stop and close">✕</button></div>
<div class="art" id="np-art"></div><div class="np-d" id="np-d"></div>
<div class="np-tr"><div class="t serif" id="np-t"></div><button id="np-more" aria-label="Favorite or share this sermon" hidden></button></div><div class="s" id="np-s"></div><div id="np-read" aria-label="Reader"></div>
<input type="range" id="seek" min="0" max="1000" value="0"><div class="times"><span id="cur">0:00</span><span id="rem">-0:00</span></div><div class="np-left" id="npleft" hidden></div>
<div class="ctl"><button class="side sk" id="prv" aria-label="Previous"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14M19 5l-10 7 10 7z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg></button><button class="side" id="bk">↺ 10</button><button class="big" id="pp" style="display:flex;align-items:center;justify-content:center"></button><button class="side" id="fw">10 ↻</button><button class="side sk" id="nxt" aria-label="Next"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 5v14M5 5l10 7-10 7z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg></button></div>
<div id="np-hl" aria-hidden="true"><i></i></div><div class="ctl2"><div class="spd"><button id="spd-dn" aria-label="Slower">−</button><button id="spd">1×</button><button id="spd-up" aria-label="Faster">+</button></div><button id="bedb" hidden aria-haspopup="true">♪ Music</button><button id="zz">Sleep off</button></div><div id="bedpop" hidden></div><div class="np-cut"><button id="cutb" hidden>Teaching starts here</button></div></div>
<audio id="audio" preload="metadata"></audio><audio id="praym" preload="none"></audio><audio id="bedm" preload="none"></audio><audio id="ledm" preload="none"></audio><audio id="medm" preload="none"></audio><audio id="lpm" preload="none"></audio><audio id="audiofx" preload="metadata" crossorigin="anonymous"></audio>
<script src="worship.js"></script>
<script type="application/json" id="dj">const D=__DATA__</script>
<script>
var DIAG={a:[],t0:Date.now(),sv:0,last:{}};
/* what the phone did: the last 300 events (opening, Pray's taps, its players' and the music's events), kept on the phone;
   ⋯ → Copy diagnostics copies them as text. Nothing is sent anywhere. */
function dlog(k,o){try{DIAG.a.push([new Date().toISOString().slice(11,23),k,o==null?'':o]);if(DIAG.a.length>300)DIAG.a.splice(0,DIAG.a.length-300);
 clearTimeout(DIAG.sv);DIAG.sv=setTimeout(()=>{try{const old=JSON.parse(localStorage.getItem('sc:diag')||'[]');localStorage.setItem('sc:diag',JSON.stringify(old.concat(DIAG.a.splice(0)).slice(-300)))}catch(e){}},1200)}catch(e){}}
function diagText(){let L=[];try{L=JSON.parse(localStorage.getItem('sc:diag')||'[]')}catch(e){}L=L.concat(DIAG.a).slice(-300);
 return 'Scripture Companion diagnostics · build '+(typeof APPV!=='undefined'?APPV:'?')+' · '+navigator.userAgent+'\n'+L.map(e=>e[0]+'  '+e[1]+'  '+(typeof e[2]==='string'?e[2]:JSON.stringify(e[2]))).join('\n')}
function diagCopy(){const t=diagText(),m=document.getElementById('diagmsg');const ok=()=>{if(m)m.textContent='Copied. Paste it to Claude.'};
 try{navigator.clipboard.writeText(t).then(ok).catch(()=>{prompt('Copy this:',t)})}catch(e){prompt('Copy this:',t)}}
const D=JSON.parse(document.getElementById('dj').textContent.slice(8)),I=D.items;   /* the data as JSON (parsed much faster than a script literal); the block starts "const D=" so the tools still find it */
/* "Teaching starts here": your own start points (synced), over the measured ones */
const CUT0={};function cutApply(){const c=S.get('cut',{})||{};for(const k in c){if(!I[k])continue;if(!(k in CUT0))CUT0[k]=I[k].s||0;I[k].s=c[k]==null?CUT0[k]:+c[k]}}
const S={get(k,d){try{const v=localStorage.getItem('sc:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},set(k,v){try{let old;if(BK_DELK.includes(k))try{old=JSON.parse(localStorage.getItem('sc:'+k)||'null')}catch(e){}localStorage.setItem('sc:'+k,JSON.stringify(v));if(BK_KEYS.includes(k)){localStorage.setItem('sc:bkdirty','1');bkMark(k,old,v)}}catch(e){}}};
/* Automatic backup to the listener's own private GitHub repo. The key never leaves this phone except to GitHub.
   Saved about every 10 minutes while something changed, and whenever the app goes to the background; every backup is
   a commit, so older versions stay in the repo's history. A new phone: paste the key once and everything comes back. */
const BK_KEYS=['camp','camp2','camp3','npl','cfg','jp','level','lk2','narpos','prog','read','skip','speed','tab','wsongs','wsets','bedon','bedlv','bedlvp','bedpos',
 'fav','coreSet','bp','bplast','prm','prsub','prsup','prlast','ledord','ledsp','medsp','bedled','wimp','pmpos','srecent','shlen','bbpos','bbintro','bbrec','cut'],BK={sha:null,busy:false,tried:0,err:S.get('bkerr',''),pulled:0};
/* Sync between devices. Each synced setting remembers when it last changed (sc:bkts), and what was removed from it
   (sc:bkdel), so two devices merge instead of overwriting each other:
   - lists of things by id (progress, chapters read, favorites, Core, bookmarks, songs, setlists) are merged item by item;
     an item removed on one device is removed everywhere, unless the other device changed that list after the removal
   - listening progress keeps the newest position, and anything finished on either device stays finished
   - everything else: the most recent change wins
   - where you are (the stop, tab, view) stays with the device you are using; opening the app takes the newest */
const BK_MAP=['prog','read','narpos','fav','coreSet','skip','bp','wsongs','prsup','cut'],BK_LIST=['wsets'],BK_UNION=['wimp'],BK_NAV=['camp','camp2','camp3','npl','jp','tab','lk2'],BK_DELK=BK_MAP.concat(BK_LIST);
function bkJ(k,d){try{const v=localStorage.getItem('sc:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}}
function bkIds(k,v){return !v?[]:BK_LIST.includes(k)?(Array.isArray(v)?v.map(x=>x&&x.id).filter(Boolean):[]):(typeof v==='object'?Object.keys(v):[])}
function bkMark(k,old,v){const t=Date.now(),ts=bkJ('bkts',{});ts[k]=t;localStorage.setItem('sc:bkts',JSON.stringify(ts));
 if(!BK_DELK.includes(k)||!old)return;const now=new Set(bkIds(k,v)),gone=bkIds(k,old).filter(id=>!now.has(id));if(!gone.length)return;
 const del=bkJ('bkdel',{}),m=del[k]=del[k]||{};gone.forEach(id=>m[id]=t);localStorage.setItem('sc:bkdel',JSON.stringify(del))}
function bkMerge(L,R){const out={data:{},ts:{},del:{}},YEAR=365*864e5,now=Date.now();
 [L.del,R.del].forEach(d=>Object.keys(d||{}).forEach(k=>{const m=out.del[k]=out.del[k]||{};Object.keys(d[k]).forEach(id=>{const t=d[k][id];if(now-t<YEAR&&(!m[id]||t>m[id]))m[id]=t})}));
 const keys=new Set([...Object.keys(L.data||{}),...Object.keys(R.data||{})]);
 keys.forEach(k=>{const lt=L.ts[k]||0,rt=R.ts[k]||0,lv=L.data[k],rv=R.data[k],rNew=rt>lt;out.ts[k]=Math.max(lt,rt);
  if(lv===undefined){out.data[k]=rv;return}if(rv===undefined){out.data[k]=lv;return}
  const gone=out.del[k]||{},keep=(id,side)=>!(gone[id]&&gone[id]>=(side==='L'?lt:rt));
  if(BK_MAP.includes(k)&&typeof lv==='object'&&typeof rv==='object'&&!Array.isArray(lv)){const o={};
   new Set([...Object.keys(lv),...Object.keys(rv)]).forEach(id=>{const x=lv[id],y=rv[id];
    if(x!==undefined&&y!==undefined){let v=rNew?y:x;if(k==='prog'&&typeof x==='object'&&typeof y==='object'){const xn=(x.at||0)>=(y.at||0);v=Object.assign({},xn?y:x,xn?x:y);const xd=x.done&&!(y.reopen&&(y.at||0)>=(x.at||0)),yd=y.done&&!(x.reopen&&(x.at||0)>=(y.at||0));if(xd||yd)v.done=true;else delete v.done}else if(k==='read')v=x||y;o[id]=v}
    else if(x!==undefined){if(keep(id,'L'))o[id]=x}else if(keep(id,'R'))o[id]=y});out.data[k]=o;return}
  if(BK_LIST.includes(k)&&Array.isArray(lv)&&Array.isArray(rv)){const A=rNew?rv:lv,B=rNew?lv:rv,aS=rNew?'R':'L',bS=rNew?'L':'R',ids=new Set(),o=[];
   A.forEach(x=>{if(x&&x.id&&!ids.has(x.id)&&keep(x.id,aS)){ids.add(x.id);o.push(x)}});B.forEach(x=>{if(x&&x.id&&!ids.has(x.id)&&keep(x.id,bS)){ids.add(x.id);o.push(x)}});out.data[k]=o;return}
  if(BK_UNION.includes(k)&&Array.isArray(lv)&&Array.isArray(rv)){out.data[k]=[...new Set([...lv,...rv])];return}
  out.data[k]=rNew?rv:lv});
 return out}
/* after a merge brought something new: the app's own copies in memory follow */
function bkRefresh(keys){const has=k=>keys.includes(k);
 try{if(has('prog'))prog=S.get('prog',{});if(has('read'))read=S.get('read',{});if(has('cfg'))cfg=Object.assign(S.get('cfg',{who:''}),{order:'canon'});if(has('camp'))camp=S.get('camp',null)}catch(e){}
 try{if(has('skip'))SKIP=S.get('skip',{})}catch(e){}try{if(has('bp'))BP=S.get('bp',{})}catch(e){}try{if(has('tab'))TAB=S.get('tab',TAB)}catch(e){}
 try{if(has('npl')&&(!cur||audio.paused))setTimeout(nplRestore,200)}catch(e){}
 try{if(has('cut'))cutApply()}catch(e){}
 try{if(has('speed')){speed=S.get('speed',1);AUDIO_EL.forEach(x=>x.playbackRate=speed)}}catch(e){}
 try{if(has('bedon'))BED.on=!!S.get('bedon',false);if(has('bedlv'))BED.lv=+S.get('bedlv',0.2)||0.2}catch(e){}
 const busy=WS.edit||(document.activeElement&&/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName));if(!busy)try{render()}catch(e){}}
let BK_ID=bkJ('bkdev','');if(!BK_ID){BK_ID='d'+Math.random().toString(36).slice(2,10);localStorage.setItem('sc:bkdev',JSON.stringify(BK_ID))}
const bkRepo=()=>S.get('bkrepo','zreynard/scripture-companion-backup'),bkKey=()=>S.get('bkkey',''),bkOn=()=>!!bkKey();
function bkSnap(){const o={};BK_KEYS.forEach(k=>{try{const v=localStorage.getItem('sc:'+k);if(v!=null)o[k]=JSON.parse(v)}catch(e){}});return o}
function bkB64(str){const b=new TextEncoder().encode(str);let s='';for(let i=0;i<b.length;i+=0x8000)s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000));return btoa(s)}
function bkUn64(b64){return new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\s/g,'')),c=>c.charCodeAt(0)))}
function bkGH(path,opt={},key=bkKey(),repo=bkRepo()){return fetch('https://api.github.com/repos/'+repo+path,{method:opt.method||'GET',body:opt.body,cache:'no-store',headers:Object.assign({Authorization:'Bearer '+key,Accept:opt.accept==='raw'?'application/vnd.github.raw+json':'application/vnd.github+json'},opt.body?{'Content-Type':'application/json'}:{})})}
async function bkFetch(){const r=await bkGH('/contents/progress.json');if(r.status===404){BK.sha=null;return null}if(!r.ok)throw r.status;const j=await r.json();BK.sha=j.sha;let c=j.content;
 if(!c||j.encoding!=='base64'){const r2=await bkGH('/git/blobs/'+j.sha);if(!r2.ok)throw r2.status;c=(await r2.json()).content}return JSON.parse(bkUn64(c))}
function bkFail(e){BK.err=e===401||e===403?'GitHub no longer accepts the backup key: paste a new one in ⋯':e===404?'The backup repo was not found':'';S.set('bkerr',BK.err);bkDot()}
async function bkSave(){return bkSync('save')}
/* why: 'open' (app opened or came back: the newest place wins), 'save', 'pull' (in the background while in use) */
async function bkSync(why){if(!bkOn()||BK.busy)return;BK.busy=true;BK.tried=Date.now();let changed=[];
 try{for(let tries=0;tries<3;tries++){
   const remote=await bkFetch(),R=remote&&remote.data?{data:remote.data,ts:remote.ts||{},del:remote.del||{}}:{data:{},ts:{},del:{}},
    L={data:bkSnap(),ts:bkJ('bkts',{}),del:bkJ('bkdel',{})},M=bkMerge(L,R);
   /* where you are: the backup always holds the newest place, but a device in use keeps showing its own until it is opened again */
   changed=Object.keys(M.data).filter(k=>JSON.stringify(M.data[k])!==JSON.stringify(L.data[k])&&(why==='open'||!BK_NAV.includes(k)));
   changed.forEach(k=>localStorage.setItem('sc:'+k,JSON.stringify(M.data[k])));
   const tsNow=bkJ('bkts',{});Object.keys(M.ts).forEach(k=>{if(why==='open'||!BK_NAV.includes(k))tsNow[k]=M.ts[k]});localStorage.setItem('sc:bkts',JSON.stringify(tsNow));localStorage.setItem('sc:bkdel',JSON.stringify(M.del));
   const same=remote&&JSON.stringify(M.data)===JSON.stringify(R.data)&&JSON.stringify(M.del)===JSON.stringify(R.del);
   if(!same){const body={message:'Sync '+new Date().toISOString().slice(0,16).replace('T',' ')+' from '+BK_ID,content:bkB64(JSON.stringify({v:2,at:Date.now(),dev:BK_ID,data:M.data,ts:M.ts,del:M.del}))};if(BK.sha)body.sha=BK.sha;
    const r=await bkGH('/contents/progress.json',{method:'PUT',body:JSON.stringify(body)});if(r.status===409||r.status===422){BK.sha=null;continue}if(!r.ok)throw r.status;BK.sha=(await r.json()).content.sha}
   localStorage.removeItem('sc:bkdirty');S.set('bklast',Date.now());BK.pulled=Date.now();bkFail(0);break}
  if(changed.length)bkRefresh(changed)}
 catch(e){if(typeof e==='number')bkFail(e)}finally{BK.busy=false;const st=document.getElementById('bkst');if(st)st.innerHTML=bkStatus()}}
function bkDue(){return bkOn()&&localStorage.getItem('sc:bkdirty')==='1'}
function bkApply(d){BK_KEYS.forEach(k=>{if(k in d)localStorage.setItem('sc:'+k,JSON.stringify(d[k]))});localStorage.setItem('sc:view',JSON.stringify('walk'));localStorage.removeItem('sc:bkdirty')}
function bkAgo(t){if(!t)return 'not yet';const m=Math.round((Date.now()-t)/60000);return m<1?'just now':m<60?m+' min ago':m<1440?Math.round(m/60)+' h ago':Math.round(m/1440)+' days ago'}
function bkStatus(){return BK.err?`<b style="color:#b3261e">Backup stopped.</b> ${BK.err}.`:`Backed up ${bkAgo(S.get('bklast',0))} to your private repo <b>${bkRepo()}</b>. It saves on its own; nothing to do.`}
function bkDot(){const g=document.getElementById('gear');if(g)g.classList.toggle('alert',!!(bkOn()&&BK.err))}
/* how much progress a snapshot holds, to tell an empty new phone from a used one */
function bkWeight(d){return Object.keys((d&&d.prog)||{}).length+Object.keys((d&&d.read)||{}).length}

const HIDE=D.hide||[];   /* teachers left out of this build (config.DAVEY_HIDDEN): no teacher row, switch or Core choice */
let prog=S.get('prog',{}),read=S.get('read',{}),cfg=Object.assign(S.get('cfg',{who:''}),{order:'canon'}),view=S.get('view','walk'),camp=S.get('camp',null);
if(HIDE.includes(cfg.who))cfg.who='';if(HIDE.includes(cfg.corePref))cfg.corePref='';   /* a hidden teacher's 'only' or 'prefer' falls back to everyone / Suggested */
const okWho=id=>!cfg.who||I[id].who===cfg.who;
/* Core (core.py): one primary exposition for each chapter or passage, chosen book by book; everything else is Go Deeper.
   A passage spanning chapters plays at the last of them, once its Scripture has been read. Your choices persist:
   coreSet {unit or "k:<abbr>:<chapter>": [ids]} replaces a Core, cfg.corePref prefers one teacher, cfg.core=false is the
   previous Journey (every teaching queued). */
const CORE=D.core||{u:[],at:{},deep:{},alt:{},bk:{}};CORE.bk=CORE.bk||{};
const coreOn=()=>cfg.core!==false&&CORE.u.length>0;
const coreSet=()=>S.get('coreSet',{});
function coreKey(x){if(!x)return null;if(x.c.sec)return 's:'+x.b.abbr;if(x.c.intro)return CORE.bk[x.b.abbr]?'b:'+x.b.abbr:null;const k=x.b.abbr+':'+x.c.c,u=CORE.at[k];return u!=null?u:('k:'+k)}
function coreIdsOf(u){const set=coreSet()[u];if(set)return set.filter(id=>I[id]&&okWho(id));if(typeof u==='string')return u.startsWith('s:')?(()=>{const b=D.books.find(z=>z.abbr===u.slice(2));return b?listenGroups(b,secOf(b)).overview.map(g=>g.id):[]})():u.startsWith('b:')?((CORE.bk[u.slice(2)]||{}).ids||[]).filter(id=>I[id]&&okWho(id)):[];
 const p=cfg.corePref;if(p&&CORE.u[u][0]){const a=(CORE.alt[u]||[]).find(z=>z[2]===p);if(a)return a[0].filter(id=>I[id]&&okWho(id))}
 return CORE.u[u][3].filter(id=>I[id]&&okWho(id))}
function coreHere(x){const u=coreKey(x);if(u==null)return null;if(typeof u==='string')return coreSet()[u]||/^[bs]:/.test(u)?u:null;return CORE.u[u][2]===x.c.c?u:null}
function coreLater(x){const u=coreKey(x);return u!=null&&typeof u!=='string'&&CORE.u[u][2]!==x.c.c?u:null}
function coreWhy(u){if(coreSet()[u])return null;if(typeof u==='string')return null;const p=cfg.corePref;if(p&&(CORE.alt[u]||[]).some(z=>z[2]===p))return'Your preferred teacher for Core.';return CORE.u[u][4]}
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

const ICON={people:'<circle cx="9" cy="8" r="3.2"/><path d="M3 19c.6-3.4 3-5 6-5s5.4 1.6 6 5"/><circle cx="17" cy="9" r="2.6"/><path d="M15.5 14.2c2.6-.3 4.8 1.2 5.5 4.3"/>',sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
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
const DONE_AT=0.5,   /* heard at least half, and reached the last two minutes (or the end): finished */
 nearEnd=(id,t)=>{const p=prog[id]||{},d=p.dur||0;return d>0&&t>=Math.min(d-(I[id].e||0)-120,(I[id].s||0)+0.95*body(id))},body=id=>{const p=prog[id]||{};if(I[id].sb)return Math.max(1,I[id].sb-(I[id].e||0));return Math.max(1,(p.dur||0)-(I[id].s||0)-(I[id].e||0))},tail=()=>cur&&I[cur]&&I[cur].e||0,heardPct=id=>{const p=prog[id]||{};return p.dur&&p.heard?Math.min(100,Math.round(100*p.heard/body(id))):0};
let lastT=null,ready=true;const OPEN=new Set();
/* ---- the Bible text (Berean Standard Bible, public domain): one file per book, fetched once, then offline ---- */
/* ---- people, places and the map (atlas.json, loaded on first use) ---- */
let ATL=null,ATL_D=null;function atlas(){if(!ATL){ATL=fetch('atlas.json').then(r=>{if(!r.ok)throw 0;return r.json()}).then(d=>(ATL_D=d)).catch(e=>{ATL=null;throw e});ATL.catch(()=>{})}return ATL}   /* a failed or interrupted download is never an unhandled error */
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
function jumpGo(i,o={}){closeJump();if(view==='journey'){JZ='stop';S.set('jz',JZ);jMove(i);if(o.sid){JM=false;BPM=null;PLAYSTOP=i;DEEP=null;play(o.sid,{full:true})}else if(o.hl){const x=walk()[i];if(x&&!x.c.intro&&hasNar(x.b.abbr,x.c.c))narPlay(x.b,x.c.c,o.hl.from,{load:true,full:true})}return}if(o.hl){HL=o.hl;TAB='scripture';S.set('tab',TAB)}if(o.listen){TAB='teaching';S.set('tab',TAB);if(o.lk){LK=o.lk;S.set('lk2',LK)}}go(i)}
function renderJump(){const body=$('#jbody'),q=$('#jq').value.trim(),w=walk(),cur=w[camp||0];let h='';
 if(q&&/secret|platt.*church/i.test(q))h+=`<button class="jr" id="jsc"><span class="jr-ic">▶</span><span class="jr-t"><b>Secret Church</b><span>${scGroups().length} nights · every session in order</span></span></button>`;
 if(!q){if(JP.list){h+=`<div class="jp-h">All books</div>`;let land='';for(const b of D.books){const L=(LANDS.slice().reverse().find(l=>D.books.indexOf(b)>=D.books.findIndex(bb=>bb.name===l[0]))||[,''])[1];
    if(L!==land){h+=`<div class="jp-sec">${esc(L)}</div>`;land=L}const n=b.ch.filter(c=>chDoneAt({b,c})).length,done=n===b.ch.length;
    h+=`<button class="jb${b===cur.b?' cur':''}" data-jb="${esc(b.name)}"><span>${esc(b.name)}</span><span class="jb-r">${done?'<i class="ok">✓</i>':n?Math.round(100*n/b.ch.length)+'%':b.ch.length+' ch'}</span></button>`}}
  else{const b=JP.book,n=b.ch.filter(c=>chDoneAt({b,c})).length;
   h+=`<div class="jp-bk"><div><div class="jp-bn serif">${esc(b.name)}</div><div class="jp-bs">${n} of ${b.ch.length} chapters done</div></div><button class="jp-all" id="jall">All books ›</button></div><div class="jg">`;
   {const i=w.findIndex(x=>x.b===b&&x.c.intro&&!x.c.sec);h+=`<button class="jc jc-bk${i===camp?' here':''}" data-ji="${i}">The book of ${esc(b.name)}<small>Overview · summary</small></button>`}
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
  $('#mvtitle').textContent=f?f.n:'Your journey';mvStrip(A);mvCard(A);Object.assign(MV,f?boxView(f.x-10,f.y-10,f.x+10,f.y+10,60):legBox(A,st.leg));drawMap(A)}).catch(()=>{})}
function closeMap(){$('#mapv').hidden=true;document.body.classList.remove('mapopen')}
(()=>{const el=$('#mapsvg'),P=new Map();let start=null,moved=0;
 const zoom=(f,cx,cy)=>{atlas().then(A=>{const r=el.getBoundingClientRect(),s=MV.w/r.width,mx=MV.x+(cx-r.left)*s,my=MV.y+(cy-r.top)*s,nw=Math.min(420,Math.max(14,MV.w*f)),k=nw/MV.w;MV.x=mx-(mx-MV.x)*k;MV.y=my-(my-MV.y)*k;MV.w=nw;MV.h*=k;drawMap(A)}).catch(()=>{})};
 el.addEventListener('pointerdown',e=>{el.setPointerCapture(e.pointerId);P.set(e.pointerId,[e.clientX,e.clientY]);if(P.size===1)moved=0;cancelAnimationFrame(MV.raf);start={x:MV.x,y:MV.y,pts:new Map(P),w:MV.w,h:MV.h}});
 el.addEventListener('pointermove',e=>{if(!P.has(e.pointerId)||!start)return;P.set(e.pointerId,[e.clientX,e.clientY]);const r=el.getBoundingClientRect(),s=start.w/r.width;
  if(P.size===1){const[a]=[...start.pts.values()],[b]=[...P.values()];moved=Math.max(moved,Math.hypot(b[0]-a[0],b[1]-a[1]));MV.x=start.x-(b[0]-a[0])*s;MV.y=start.y-(b[1]-a[1])*s;el.setAttribute('viewBox',`${MV.x} ${MV.y} ${MV.w} ${MV.h}`)}
  else if(P.size===2&&start.pts.size===2){moved=99;const[a1,a2]=[...start.pts.values()],[b1,b2]=[...P.values()];const d0=Math.hypot(a1[0]-a2[0],a1[1]-a2[1]),d1=Math.hypot(b1[0]-b2[0],b1[1]-b2[1]);if(d0>10&&d1>10){MV.w=Math.min(420,Math.max(14,start.w*d0/d1));MV.h=start.h*MV.w/start.w;const cx=(a1[0]+a2[0])/2,cy=(a1[1]+a2[1])/2,mx=start.x+(cx-r.left)*s,my=start.y+(cy-r.top)*s,k=MV.w/start.w,nx=(b1[0]+b2[0])/2,ny=(b1[1]+b2[1])/2;MV.x=mx-(nx-r.left)*s*k;MV.y=my-(ny-r.top)*s*k;el.setAttribute('viewBox',`${MV.x} ${MV.y} ${MV.w} ${MV.h}`)}}});
 const end=e=>{P.delete(e.pointerId);if(P.size){start={x:MV.x,y:MV.y,pts:new Map(P),w:MV.w,h:MV.h};return}start=null;
  if(moved<8)return;atlas().then(A=>drawMap(A)).catch(()=>{})};
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
 if(first){const ord=books().map(x=>x.name),groups={};spansAt(b,c).forEach(x=>{if(!okWho(x.id))return;let lab=x.label;
   if(x.books&&!/Testament|Law|History|Wisdom|Prophets|Gospels|Church|Letters|Revelation/.test(lab)){const idxs=x.books.map(n=>ord.indexOf(n)).sort((p,q)=>p-q);const contig=idxs[idxs.length-1]-idxs[0]===idxs.length-1;lab=contig?`${ord[idxs[0]]}–${ord[idxs[idxs.length-1]]}`:x.books.join(', ')}
   const w=/Bible/i.test(lab)?1000:/Testament/i.test(lab)?500:x.books?x.books.length:50;(groups[lab]=groups[lab]||{w:0,ids:[]}).ids.push(x.id);groups[lab].w=Math.max(groups[lab].w,w)});
  Object.entries(groups).sort((a,z)=>z[1].w-a[1].w).forEach(([lab,o])=>o.ids.forEach(id=>g.overview.push({id,r:null,h:lab.charAt(0).toUpperCase()+lab.slice(1)})));
  (c.sec?[]:b.ov).filter(okWho).forEach(id=>g.overview.push({id,r:prange(I[id].pass,b.name),h:'The book of '+b.name}))}
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
/* where a major section begins, its wide surveys get their own stop in front of the first book (the book's own Core pick stays with the book) */
const SEC={Genesis:'The Old Testament',Joshua:'History',Job:'Wisdom & Song',Isaiah:'The Prophets',Matthew:'The New Testament',Acts:'Acts & the Letters'};
const bkCore=b=>(CORE.bk[b.abbr]||{}).ids||[];
function secHas(b){if(!SEC[b.name]||cfg.order==='narr')return false;const k=bkCore(b);return (b.spans||[]).some(x=>!k.includes(x.id))}
function spansAt(b,c){const sp=b.spans||[];if(!secHas(b))return c.sec?[]:sp;const k=bkCore(b);return sp.filter(x=>c.sec?!k.includes(x.id):k.includes(x.id))}
function secOf(b){return b._sec||(b._sec={c:'s',intro:true,sec:true,name:SEC[b.name],ids:[],sl:'',y:'',sm:null,seq:-2})}
const nSt=b=>b.n+1+(secHas(b)?1:0);
/* each book opens with its own stop (title, what the book is about, its overviews); its chapters follow */
function walk(old){const w=[];for(const b of books()){const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;if(!old&&secHas(b))w.push({b,c:secOf(b)});w.push({b,c:introOf(b)});for(const c of chs)w.push({b,c})}return w}
function stopName(x){return x.c.sec?x.c.name:x.c.intro?x.b.name:x.b.name+' '+x.c.c}
function stopIds(x){return x.c.sec?spansAt(x.b,x.c).map(s=>s.id):x.c.intro?[...spansAt(x.b,x.c).map(s=>s.id),...x.b.ov]:x.c.ids}
function stopRead(x){return x.c.sec?!!(read[x.b.abbr+'s']||stopIds(x).some(id=>((prog[id]||{}).heard||0)>0)):x.c.intro?!!(read[x.b.abbr+'0']||x.b.ch.some(cc=>read[x.b.abbr+cc.c]||cc.ids.some(id=>((prog[id]||{}).heard||0)>0))):!!read[x.b.abbr+x.c.c]}
/* saved places from before book stops existed: move them once onto the same chapter */
function migrateCamp3(){if(S.get('camp3'))return;if(camp!=null){const o=walk(true)[camp];if(o){const k=stopKey(o),i=walk().findIndex(x=>stopKey(x)===k);if(i>=0){camp=i;S.set('camp',camp)}}}S.set('camp3',1)}
function migrateCamp(){if(S.get('camp2'))return;if(camp!=null){let cum=0,bi=0;for(const b of books()){if(camp<cum+b.n){camp=camp+bi+1;break}cum+=b.n;bi++}S.set('camp',camp)}S.set('camp2',1)}
const NAMES={Platt:'David Platt',PAM:'Philip Anthony Mitchell',Davey:'Stephen Davey',Skip:'Skip Heitzig',Fearless:'Fearless Church',Vaughan:'Kennon Vaughan'};
function teacher(i){return i.by||NAMES[i.who]}
function dispTitle(i){let t=(i.sc?(i.t||'').replace(/^\s*\d+\.\d+\s*[–—-]\s*/,''):(i.t||''));if(i.sc&&/^(introduction|conclusions?|critical conclusions|gospel foundations|gospel conclusions|practical takeaways|applications|the gospel|concluding challenges)\b/i.test(t)){const ev=(D.sc.events||[]).find(e=>e.n===i.sc[0]);if(ev)t=ev.title+': '+t}const fl=t.match(/^Flight\s+([1-3]?[A-Z]{2,4}?)(\d{1,2})\b(?:\s*-\s*(Part\s+\w+))?/);if(fl){const ord=books().map(x=>x.name),bk=fl[1]==='INT'?['Between the Testaments']:(i.pass||'').split(';').map(x=>x.replace(/the book of/i,'').replace(/\s+\d+(?:\s*[-–]\s*\d+)?\s*$/,'').trim()).filter(Boolean).sort((p,q)=>ord.indexOf(p)-ord.indexOf(q));return ['Bible from 30,000 Feet',bk.join(', ')+(+fl[2]>1?' ('+(+fl[2])+')':''),fl[3]].filter(Boolean).join(' · ')}if(!t.includes('|'))return t;const parts=t.split('|').map(x=>x.trim()).filter(Boolean),who=(teacher(i)||'').toLowerCase();
 const keep=parts.filter(x=>!/^(?:[1-3]\s?)?[A-Za-z]+\.?\s*\d+(?::\d+)?(?:\s*[-–]\s*\d+(?::\d+)?)?$/.test(x)&&!(who&&x.toLowerCase().replace(/^(elder|pastor|minister)\s+/,'')===who.replace(/^(elder|pastor|minister)\s+/,''))&&!/^(philip anthony mitchell|pam)$/i.test(x));
 return keep.length?keep.join(' · '):t}
function vItem(id,bd,up){const h=voiceHTML(id,bd);return id===up?h.replace('<div class="voice','<div class="voice upnext').replace('<div class="who">','<div class="who"><b class="upn">Up next</b> · '):h}
function voiceHTML(id,bd){const i=I[id],p=prog[id]||{},hp=heardPct(id),deg=!isDone(id)?Math.round(3.6*hp):0,playing=cur===id&&!audio.paused;
 return `<div class="voice ${isDone(id)?'done':''}"${i.audio?` data-row="${id}"`:''}><button class="pb ${i.audio?'':'off'} ${playing?'playing':''}" style="--p:${deg}deg;position:relative" data-play="${id}"><span style="color:${playing?'var(--gold2)':'var(--ink)'}">${icon(playing?'pause':'play',18,0,'currentColor')}</span></button>
 <div class="tx"><div class="who">${bd?`<button class="pref vb" data-pass="${esc(i.pass)}">${bd}</button>`:''}${teacher(i)}${i.show?' · '+i.show:i.tr==='overview'?' · Overview':''}</div><div class="ti">${esc(dispTitle(i))}</div><div class="ln">${mins(i.dur)||(i.audio?'':'audio soon')}${hp&&!isDone(id)?' · '+hp+'% heard':''}${!bd&&i.pass&&!/^All \d|survey/i.test(i.pass)?` · <button class="pref" data-pass="${esc(i.pass)}">${esc(shortPass(i.pass))}</button>`:''}</div></div>
 <span class="ck" role="img" aria-label="${isDone(id)?'Listened':'Not yet listened'}">✓</span></div>`}
let W=null; // cached world geometry
/* ---- the journey: one place in Scripture (jp), and one next step at a time.
   Each stop's steps: Overview (the book, or a stretch of chapters) → Scripture (read or listen) → Teaching (the whole
   chapter, then verse by verse). A teaching that covers several chapters waits at the first of them; once heard or
   skipped it is not asked for again (it stays in the lists). Nothing walks on by itself: the next chapter waits for you. */
Object.assign(ICON,{book:'<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20"/>',arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',map:'<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>'});
let SKIP=S.get('skip',{}),JM=false,FIRSTAT=null,PLAYSTOP=null,DEEP=null,START=null;   /* DEEP {i}: playing through the Go Deeper list at stop i */
const stopKey=x=>x.b.abbr+':'+(x.c.sec?'s':x.c.intro?0:x.c.c),scrKey=x=>x.b.abbr+x.c.c;
function firstAt(){if(FIRSTAT)return FIRSTAT;const m={};walk().forEach((x,i)=>stopIds(x).forEach(id=>{if(!(id in m))m[id]=i}));return FIRSTAT=m}
function jpIdx(){const w=walk(),k=S.get('jp',null);let i=k?w.findIndex(x=>stopKey(x)===k):-1;
 if(i<0){i=camp!=null&&w[camp]?camp:w.findIndex(x=>!stopRead(x));if(i<0)i=0;S.set('jp',stopKey(w[i]))}return i}
function setJP(i){const w=walk();if(w[i])S.set('jp',stopKey(w[i]))}
function stepsOf(i){const x=walk()[i];if(!x)return null;
 if(coreOn()){const u=coreHere(x),bq=u&&String(u).startsWith('b:')&&!coreSet()[u]?new Set(CORE.bk[x.b.abbr].q):null;return {x,ov:[],teach:u==null?[]:coreIdsOf(u).filter(id=>!bq||bq.has(id)),u}}
 const G=listenGroups(x.b,x.c);return {x,ov:G.overview.map(g=>g.id),teach:[...G.chapter,...G.verses].map(g=>g.id)}}
const queued=(id,i)=>(coreOn()||firstAt()[id]===i)&&!!I[id]&&!!I[id].audio&&!isDone(id)&&!SKIP[id];
const scrDone=x=>!!read[scrKey(x)]||!!SKIP['S:'+scrKey(x)];
function nextAction(i){const s=stepsOf(i);if(!s)return null;const x=s.x;
 const ii=stopIntro(x);if(ii&&!isDone(ii)&&!SKIP[ii])return{kind:'play',id:ii,step:'intro'};
 if(!x.c.intro&&!scrDone(x))return{kind:'scripture',step:'scripture'};
 for(const id of s.ov)if(queued(id,i))return{kind:'play',id,step:'overview'};
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
 if(a.kind==='walk'){const nx=w[a.to];return btn(icon('arrow',22,2,'#1b2440'),'When you’re ready','Walk on to '+esc(stopName(nx)),nx.c.sec?'A new section begins':nx.c.intro&&!(w[a.to-1]&&w[a.to-1].c.sec)?'A new book begins':'','walk')}
 return `<div class="cont-end">You have walked the whole of Scripture.</div>`}
function awayHTML(j){const w=walk();return `<div class="away"><button class="cont ghost" id="cont"><span class="cont-ic">${icon('arrow',20,2,'var(--ink)')}</span><span class="cont-t"><small>Your place</small><b>Return to ${esc(stopName(w[j]))}</b></span></button><div class="cont-alt"><button id="sethere">Make ${esc(stopName(w[camp]))} my place</button></div></div>`}
/* in Explore the card points to Journey, where your place is kept */
function exploreNext(j){const w=walk();if(camp===j)return `<button class="cont ghost" id="tojourney"><span class="cont-ic">${icon('book',20,1.8,'var(--ink)')}</span><span class="cont-t"><small>Your place</small><b>Continue in Journey</b></span></button>`;
 return `<button class="cont ghost" id="tojourney"><span class="cont-ic">${icon('arrow',20,2,'var(--ink)')}</span><span class="cont-t"><small>Your place · ${esc(stopName(w[j]))}</small><b>Continue in Journey</b></span></button><div class="cont-alt"><button id="sethere">Make ${esc(stopName(w[camp]))} my place</button></div>`}
function showStep(step,scroll){if(step)TAB=step;S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false;
 if(scroll){const el=document.querySelector(scroll==='text'?'details.readx':'.tabs');if(el)setTimeout(()=>window.scrollTo({top:el.getBoundingClientRect().top+scrollY-70,behavior:'smooth'}),60)}}
function walkOn(to){const w=walk(),fr=w[jpIdx()],nx=w[to];setJP(to);if(fr&&nx&&nx.b!==fr.b&&!fr.c.intro)note('You have walked through '+fr.b.name+'.');go(to)}
function doCont(o={}){const i=jpIdx();if(camp!==i){go(i);return}const a=nextAction(i);
 if(a.kind==='play'){if(cur===a.id){if(o.full)setMini(false);else audio.paused?audio.play().catch(()=>{}):audio.pause();return}JM=true;showStep(a.step);play(a.id,o.full?{full:true}:{})}
 else if(a.kind==='scripture')showStep('scripture','text');
 else if(a.kind==='walk')walkOn(a.to)}
function contRefresh(){const b=$('#cont');if(!b||camp!==jpIdx())return;const a=nextAction(camp);if(a&&a.kind==='play'&&a.id===cur){const ic=b.querySelector('.cont-ic'),sm=b.querySelector('small');if(ic)ic.innerHTML=icon(audio.paused?'play':'pause',22,0,'#1b2440');if(sm)sm.textContent=(audio.paused?'Resume · ':'Playing · ')+sm.textContent.replace(/^(Playing|Resume) · /,'')}}
function note(t){let n=$('#note');if(!n){n=document.createElement('div');n.id='note';n.setAttribute('role','status');document.body.appendChild(n)}n.textContent=t;n.classList.add('on');clearTimeout(note.t);note.t=setTimeout(()=>n.classList.remove('on'),3800)}
/* ======== Four places along the bottom: Journey · Big Picture · Explore (the road) · Library. Settings sit behind ⋯ ======== */
const TABS=[['journey','Journey'],['bible','Bible'],['library','Library'],['worship','Worship'],['pray','Pray']];
let JZ=S.get('jz','stop')==='road'?'road':'stop',BACK=null;
const TAB_IC={journey:'<path d="M12 6.5C9.8 5 7 4.6 3.5 5v13c3.5-.4 6.3 0 8.5 1.5 2.2-1.5 5-1.9 8.5-1.5V5c-3.5-.4-6.3 0-8.5 1.5z"/><path d="M12 6.5v13"/>',
 bible:'<path d="M6.5 3h11a1.5 1.5 0 0 1 1.5 1.5v15a1.5 1.5 0 0 1-1.5 1.5h-11A2.5 2.5 0 0 1 4 18.5v-13A2.5 2.5 0 0 1 6.5 3z"/><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H19"/><path d="M11.5 6.5v6M9 9h5"/>',
 bigpicture:'<path d="M3 17h18"/><path d="M7 17a5 5 0 0 1 10 0"/><path d="M12 6v2M5.6 9.6l1.4 1.4M18.4 9.6 17 11M3 13.5h1.5M19.5 13.5H21"/>',
 walk:'<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',library:'<path d="M4 5h4v15H4zM10 5h4v15h-4zM16.5 5.5l3.6-.9 3 14.5-3.6.9z"/>',
 worship:'<path d="M9 18V5.5l11-2V16"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
 pray:'<path d="M12 3.6c-.9 0-1.6.6-1.8 1.5L8.7 11.6c-.2 1-.9 1.9-1.8 2.3L4 15.3V20l4.2-1.6c2.3-.9 3.8-3.1 3.8-5.6V3.6z"/><path d="M12 3.6c.9 0 1.6.6 1.8 1.5l1.5 6.5c.2 1 .9 1.9 1.8 2.3l2.9 1.4V20l-4.2-1.6c-2.3-.9-3.8-3.1-3.8-5.6"/><path d="M9.3 9.2 11 12.6M14.7 9.2 13 12.6"/>'};
let PREV='journey';
function tabOf(v){return v==='sc'||v==='bigpicture'?'library':v==='walk'?'journey':v}
function tabsPaint(){ztPaint();const t=$('#tabs');if(!t)return;if(!t.dataset.on){t.dataset.on=1;t.innerHTML=TABS.map(([k,l])=>`<button data-tab2="${k}"><svg viewBox="0 0 24 24" width="25" height="25" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TAB_IC[k]}</svg><span>${l}</span></button>`).join('');
  t.querySelectorAll('[data-tab2]').forEach(b=>b.onclick=()=>{const v=b.dataset.tab2;if(v===view){window.scrollTo({top:0,behavior:'smooth'});return}setView(v)})}
 t.querySelectorAll('[data-tab2]').forEach(b=>{const on=b.dataset.tab2===tabOf(view);b.classList.toggle('on',on);b.setAttribute('aria-current',on?'page':'false')});document.body.dataset.v=view}
function setView(v){if(v==='walk'){v='journey';JZ='road';S.set('jz',JZ)}if(view!=='settings')PREV=view;view=v;S.set('view',v);if(v==='journey'&&JZ==='road'){decorate.first=true;camp=jpIdx()}render();if(!(v==='journey'&&JZ==='road'))window.scrollTo(0,0)}
function setZoom(z){JZ=z;S.set('jz',z);if(z==='road'){camp=jpIdx();decorate.first=true}else closeSeries();render();if(z==='stop')window.scrollTo(0,0)}
/* the bar at the top of Journey: [ your stop | The Road ] and settings */
function ztPaint(){let el=$('#zt');const on=view==='journey';document.body.dataset.z=on?JZ:'';if(!el)return;el.hidden=!on;if(!on)return;const x=walk()[jpIdx()];
 el.innerHTML=`<div class="zt-seg" role="group" aria-label="Zoom"><button data-z="stop" class="${JZ==='stop'?'on':''}" aria-pressed="${JZ==='stop'}">${icon('book',15,1.9,'currentColor')}<span>${esc(stopName(x))}</span></button><button data-z="road" class="${JZ==='road'?'on':''}" aria-pressed="${JZ==='road'}">${icon('map',15,1.9,'currentColor')}<span>The Road</span></button></div><button class="zt-more" data-srch aria-label="Search">${SRCH_IC}</button><button class="zt-more" data-settings aria-label="Settings"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg></button>`;
 el.querySelectorAll('[data-z]').forEach(b=>b.onclick=()=>{if(b.dataset.z===JZ){if(JZ==='stop')window.scrollTo({top:0,behavior:'smooth'});return}setZoom(b.dataset.z)});el.querySelector('[data-settings]').onclick=()=>setView('settings');el.querySelector('[data-srch]').onclick=()=>openSearch()}
/* The Road: a book opens its chapters in a sheet; a chapter on the road opens its player */
function roadPick(i){const w=walk(),x=w[i];if(!x)return;if(x.c.intro&&!x.c.sec){openBook(x.b);return}JZ='stop';S.set('jz',JZ);jMove(i)}
function openBook(b){const w=walk(),el=$('#bps'),j=jpIdx(),here=w[j],bi=w.findIndex(x=>x.b===b&&x.c.intro&&!x.c.sec),land=landOf(b);
 el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${esc(b.name)}"><button class="grab2" data-bpsx aria-label="Close"></button>
  <div class="jv-eb" style="margin:4px 2px 0">${esc(land)}${b.yr?' · '+esc(b.yr):''}</div><div class="bps-t" style="font-size:34px;margin:2px 2px 0">${esc(b.name)}</div>${b.bl?`<p class="bps-d" style="font-family:'Iowan Old Style',Palatino,Georgia,serif;font-size:17px">${esc(plainT(b.bl))}</p>`:''}
  <button class="bk-ov${here.b===b&&here.c.intro&&!here.c.sec?' cur':''}" data-pick="${bi}"><span>Book overview</span><em>${stopRead(w[bi])?'✓ heard':''}</em></button>
  <div class="jv-sec" style="margin-top:18px">${b.ch.length} chapter${b.ch.length>1?'s':''}</div><div class="bk-g">${b.ch.map(c=>{const k=w.findIndex(x=>x.b===b&&x.c===c),dn=!!read[b.abbr+c.c]||c.ids.some(isDone);return `<button data-pick="${k}" class="${k===j?'cur':dn?'done':''}" aria-label="${esc(b.name)} ${c.c}${dn?', read':''}">${c.c}</button>`}).join('')}</div>
  <p class="bps-n" style="text-align:center;margin-top:14px">Tap a chapter to go there.</p></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));el.querySelectorAll('[data-bpsx]').forEach(x=>x.onclick=closeSeries);
 el.querySelectorAll('[data-pick]').forEach(x=>x.onclick=()=>{const k=+x.dataset.pick;el.classList.remove('on');document.body.classList.remove('bpsopen');el.hidden=true;el.innerHTML='';JZ='stop';S.set('jz',JZ);jMove(k)})}
function hereCard(){const w=walk(),i=jpIdx(),x=w[i],a=nextAction(i);let sub='';if(a.kind==='play')sub='Up next · '+dispTitle(I[a.id])+' · '+teacher(I[a.id]);else if(a.kind==='scripture')sub='Up next · Read '+stopName(x);else if(a.kind==='walk')sub='Next · '+stopName(w[a.to]);
 return `<div id="here"><button class="here-t" data-z2="stop"><small>You are here · tap to open</small><b>${esc(stopName(x))}</b><em>${esc(sub)}</em></button>${a.kind==='play'||a.kind==='scripture'?`<button class="here-p" id="herep" aria-label="Play">${icon('play',15,0,'#fff')}</button>`:''}</div>`}
const moreBtn=()=>`<button class="vsrch" data-srch aria-label="Search">${SRCH_IC}</button><button class="vmore" data-settings aria-label="Settings">${'<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg>'}</button>`;

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
function stepFrac(i,list){const q=list.filter(id=>(coreOn()||firstAt()[id]===i)&&I[id]&&I[id].audio);if(!q.length)return 1;return q.filter(id=>isDone(id)||SKIP[id]).length/q.length}
function jRow(id,badge,up,note){const it=I[id];if(!it)return'';const done=isDone(id),pl=cur===id&&!audio.paused,left=leftOf(id);
 const tag=pl?'<em class="jw-up">Playing</em> · ':up===id&&!done?'<em class="jw-up">Up next</em> · ':'';
 return `<div class="jw${done?' heard':''}${up===id?' up':''}${pl?' pl':''}"${it.audio?` data-row="${id}"`:''}><button class="jpb${it.audio?'':' off'}" data-play="${id}" aria-label="${pl?'Pause':'Play'} ${esc(dispTitle(it))}"${it.audio?'':' disabled'}>${icon(pl?'pause':'play',12,0,'currentColor')}</button><div class="jw-t"><b>${esc(dispTitle(it))}</b><span>${tag}${esc(teacher(it))}${left?' · '+atSpd(left)+' left':it.dur?' · '+durTxt(+it.dur):''}${it.audio?'':' · audio soon'}</span>${note?`<span>${note}</span>`:''}</div>${done?'<i class="jw-ok" aria-label="heard">✓</i>':badge?`<span class="vb">${badge}</span>`:it.audio?'<svg class="jw-go" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>':''}</div>`}
/* People on a Journey stop: who is in this chapter (or, at a book's opening, the book's main people). Tap to open them all. */
let PPO=S.get('ppOpen',false);
const castOf=x=>x&&x.c.sec?[]:ATL_D&&ATL_D.cast?(ATL_D.cast[x.c.intro?'book '+x.b.name:x.b.name+' '+x.c.c]||[]).map(e=>{const [s,n]=e.split('|');return {s,n:n||(ATL_D.p[s]||{}).n}}).filter(e=>ATL_D.p[e.s]):null;
function ppHTML(x){const L=castOf(x);if(!L||!L.length)return'';
 return `<div class="jv-ppr"><span class="jv-pl">People</span><div class="jv-pps">${L.map(e=>`<button class="jv-chip" data-nk="p" data-ns="${e.s}">${medal(ATL_D.p[e.s],26)}<span>${esc(e.n)}</span></button>`).join('')}</div></div>`}
function ppWire(){const el=$('#jpp');if(!el)return;const x=walk()[jpIdx()];
 const paint=()=>{const e=$('#jpp');if(!e)return;e.innerHTML=ppHTML(walk()[jpIdx()]);ppWire()};
 const b=$('#jppb');if(b)b.onclick=()=>{PPO=!PPO;S.set('ppOpen',PPO);if(ATL_D)paint();else atlas().then(paint).catch(()=>{PPO=false;note('People did not load. Check your connection.')})};
 wireNames(el);
 if(!ATL_D){const go=()=>atlas().then(()=>{if(walk()[jpIdx()]===x)paint()}).catch(()=>{});window.requestIdleCallback?requestIdleCallback(go,{timeout:2500}):setTimeout(go,800)}}
function journeyView(){const w=walk(),i=jpIdx(),x=w[i],b=x.b,c=x.c,a=nextAction(i),s=stepsOf(i),G=listenGroups(b,c),lm=LANDMARKS[b.abbr+c.c],up=a&&a.kind==='play'?a.id:null;
 const pv=w[i-1],nx2=w[i+1];
 let h=`<div class="jv jvz${jMove.dir?' in-'+jMove.dir:''}${c.sec?' jv-secst':''}" id="jv">${c.sec?'':`<div class="jv-eb">${esc(landOf(b))}${(c.y||b.yr)?' · '+esc(c.y||b.yr):''}</div>`}<div class="jv-tr"><h1 class="jv-t"><button id="jpick" aria-label="Choose a book or chapter">${esc(stopName(x))}<svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button></h1>`
  +`<button class="jv-ar" ${pv?`data-jgo="${i-1}" aria-label="Back to ${esc(stopName(pv))}"`:'disabled aria-label="Back"'}><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><button class="jv-ar" ${nx2?`data-jgo="${i+1}" aria-label="On to ${esc(stopName(nx2))}"`:'disabled aria-label="On"'}><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>`;
 if(!c.sec)h+=`<div class="jv-art jv-ban" id="jart">${heroArt(x,350,128,'ja')}<div class="jv-cap"><div class="cs">${rich(c.intro?(b.bl||''):(c.sl||''))}</div></div></div>`;
 h+=`<div class="jv-cast" id="jpp">${ppHTML(x)}</div>`;

 const ii=stopIntro(x),itx=hasIntroText(x),iiF=ii?(isDone(ii)||SKIP[ii]?1:Math.min(.95,heardPct(ii)/100)):0;
 const segs=coreOn()?[...(ii||itx?[['intro','Introduction',iiF]]:[]),...(c.intro?(CORE.bk[b.abbr]||G.overview.length?[['teaching','Teaching',s.teach.length?stepFrac(i,s.teach):1]]:[]):[['scripture','Scripture',scrDone(x)?1:(cur===narId(b.abbr,c.c)&&audio.duration?Math.min(.95,audio.currentTime/audio.duration):0)],['teaching','Teaching',s.teach.length?stepFrac(i,s.teach):(coreLater(x)!=null?stepFrac(i,coreIdsOf(coreLater(x))):1)]])]:[...(ii||itx?[['intro','Introduction',iiF]]:[]),...(c.intro?[['overview',c.sec?'Overview':'Book overview',stepFrac(i,s.ov)]]:[['scripture','Scripture',scrDone(x)?1:(cur===narId(b.abbr,c.c)&&audio.duration?Math.min(.95,audio.currentTime/audio.duration):0)],['overview','Overview',stepFrac(i,s.ov)],['teaching','Teaching',stepFrac(i,s.teach)]])];
 /* Core: the steps are tabs, one section at a time; the tab follows where you are unless you pick one */
 const tabs=segs.map(z=>z[0]),TABK=stopKey(x),tab=coreOn()?(JV.tabFor===TABK&&tabs.includes(JV.tab)?JV.tab:a&&tabs.includes(a.step)?a.step:tabs.includes('teaching')&&a&&a.kind==='walk'?'teaching':tabs[0]):null;
 h+=`<div class="jv-seg" id="jseg"><div class="jv-st" aria-hidden="true">${esc(stopName(x))}</div><div class="jv-sgr"${coreOn()?' role="tablist"':''}>${segs.map(([k,l,f])=>`<button data-jseg="${k}" class="${!tab&&a&&a.step===k?'now':''}${tab===k?' on':''}"${coreOn()?` role="tab" aria-selected="${tab===k}"`:` aria-label="Go to ${l}"`}><i><b style="width:${Math.round(100*f)}%"></b></i>${l}${f>=1?' ✓':''}</button>`).join('')}</div></div>`;
 /* with tabs, Up next sits on the tab it belongs to; the walk-on card on the last tab */
 const card=!tab||(a&&tab===a.step)||(a&&(a.kind==='walk'||a.kind==='end')&&tab===tabs[tabs.length-1])||tabs.length===0;
 if(!card){}
 else if(coreOn()&&(a.kind==='play'||a.kind==='scripture')){}
 else if(a.kind==='play'){const it=I[a.id],pl=cur===a.id&&!audio.paused,left=leftOf(a.id);
  h+=`<button class="jv-next" id="jnext"><span class="jv-pp">${icon(pl?'pause':'play',20,0,'#fff')}</span><span class="jv-nt"><small>${pl?'Playing':left?'Resume':'Up next'}${a.step==='intro'?' · Introduction':a.step==='overview'&&!c.intro?' · Overview':''}</small><b>${esc(dispTitle(it))}</b><em>${esc(teacher(it))}${left?' · '+atSpd(left)+' left':it.dur?' · '+durTxt(+it.dur):''}</em></span></button><div class="jv-alt"><button data-skipnext="${a.id}">Skip for now</button></div>`}
 else if(a.kind==='scripture'){const n=narDur(b.abbr,c.c),pl=cur===narId(b.abbr,c.c)&&!audio.paused;
  h+=`<button class="jv-next" id="jnext"><span class="jv-pp">${icon(pl?'pause':'play',20,0,'#fff')}</span><span class="jv-nt"><small>${pl?'Reading':'Up next'}</small><b>Read ${esc(stopName(x))}</b><em>Listen along${n?' · '+durTxt(n):''}</em></span></button><div class="jv-alt"><button data-jread="1">I’ve read it</button><button data-skipnext="S:${scrKey(x)}">Skip for now</button></div>`}
 else if(a.kind==='walk'){const nx=w[a.to],nlm=LANDMARKS[nx.b.abbr+nx.c.c];
  h+=`<p class="jv-done">${c.intro?`That’s the overview of ${esc(stopName(x))}.`:`You’ve walked through ${esc(stopName(x))}.`} ${esc(stopName(nx))} is ready whenever you are.</p>
  <button class="jv-nextstop" id="jnext"><span class="jv-art sm">${heroArt(nx,350,150,'jn')}</span><span class="jv-ns"><small>${nx.c.sec?'A new section':nx.c.intro?'A new book':'Next stop'}${nlm?' · '+esc(nlm[1]):''}</small><b>${esc(stopName(nx))}</b><em>${esc(plainT(nx.c.sec?'':nx.c.intro?(nx.b.bl||''):(nx.c.sl||'')))}</em><span class="jv-go">Begin ${esc(stopName(nx))} ${icon('arrow',18,2.2,'#fff')}</span></span></button>`}
 else h+=`<p class="jv-done">You have walked the whole of Scripture.</p>`;
 /* the stop's whole list: introduction, scripture, overview, teaching, in order; heard ones stay, quietly ticked */
 const cap=n=>JV.more?n:Math.min(n,8);let rows='',shown=0,total=0;
 const sec=(t,list,k)=>{if(!list.length)return'';let o=`<div class="jv-sec" id="js-${k}">${t}</div>`,last=null;list.forEach(g=>{total++;if(shown>=cap(1e9))return;if(g.h&&g.h!==last&&c.intro&&!c.sec){o+=`<div class="jv-sub">${esc(g.h)}</div>`;last=g.h}o+=jRow(g.id,g.r?vbadge(g.r):'',up);shown++});return o};
 const show=k=>!tab||tab===k;
 const skipL=(st,key)=>coreOn()&&a&&a.step===st&&(a.kind==='play'||a.kind==='scripture')?`<button class="jv-sk" data-skipnext="${key}">Skip for now</button>`:'';
 if((ii||itx)&&show('intro'))rows+=`<div class="jv-sec jv-tsec" id="js-intro"><span>Introduction</span>${ii?skipL('intro',ii):''}</div>${ii?(!coreOn()&&tab&&card&&a.id===ii?'':jRow(ii,'',up)):`<div class="jw"><span class="jpb off" aria-hidden="true">${icon('book',13,1.8,'currentColor')}</span><div class="jw-t"><b>${esc(c.intro?'Introducing '+b.name:stopName(x)+' · Introduction')}</b><span>The Narrator · narration coming soon</span></div></div>`}${ii&&coreOn()?'':`<button class="jv-rd" id="jrd" aria-expanded="false">Read the introduction</button><div class="jv-itx" id="jitx" hidden></div>`}`;
 if(!c.intro&&show('scripture')&&!(!coreOn()&&tab&&card&&a.kind==='scripture')){const rd=!!read[scrKey(x)],pl=cur===narId(b.abbr,c.c)&&!audio.paused,nup=a&&a.kind==='scripture',nd=narDur(b.abbr,c.c);
  rows+=`<div class="jv-sec jv-tsec" id="js-scripture"><span>Scripture</span>${skipL('scripture','S:'+scrKey(x))}</div><div class="jw${rd?' heard':''}${pl?' pl':''}" data-scrrow="1"><button class="jpb" data-jscr="1" aria-label="${pl?'Pause':'Listen to'} ${esc(stopName(x))}">${icon(pl?'pause':'play',12,0,'currentColor')}</button><div class="jw-t"><b>${esc(stopName(x))}</b><span>${pl?'<em class="jw-up">Reading</em> · ':nup&&!rd?'<em class="jw-up">Up next</em> · ':''}Read or listen${nd?' · '+durTxt(nd):''}</span></div><button class="jr-open${RDO===scrKey(x)?' on':''}" data-rdopen="1" aria-label="${RDO===scrKey(x)?'Close the text of':'Read the text of'} ${esc(stopName(x))}" aria-expanded="${RDO===scrKey(x)}">${icon('book',18,1.8,'currentColor')}</button>${rd?'<i class="jw-ok" aria-label="read">✓</i>':'<svg class="jw-go" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'}</div>`+(RDO===scrKey(x)?`<div class="jread" id="jread"><div class="jr-bar"><button class="jr-b pri" data-rdlisten="1">${icon('play',12,0,'currentColor')} Listen</button><button class="jr-b" data-rdclose="1">Close</button></div><div class="txt jr-txt" data-book="${esc(b.name)}" data-ch="${c.c}">Opening ${esc(stopName(x))}…</div><button class="jr-fab" data-rdlisten="1" aria-label="Listen from here">${icon('play',13,0,'currentColor')} Listen from here</button><div class="jr-end">${rd?'<span class="jr-ok">✓ Read</span>':`<button class="jr-done" data-jread="1">I’ve read ${esc(stopName(x))} ✓</button>`}<button class="jr-b" data-rdclose="1">Close</button></div></div>`:'')}
 if(!coreOn())rows+=G.overview.length||c.intro?sec(c.sec?'Teaching':c.intro?'Teaching on the book':'Overview',G.overview,'overview'):'<div id="js-overview"></div>';
 if(coreOn()){if(show('teaching'))rows+=coreRows(x,i,G,sec,up)}else{rows+=sec(c.intro?'':'Teaching · in passage order',[...G.chapter,...G.verses],'teaching');if(!c.intro&&!G.chapter.length&&!G.verses.length)rows+=`<div class="jv-sec" id="js-teaching">Teaching</div><p class="jv-none">No teaching on this chapter alone yet.</p>`;}
 if(shown<total)rows+=`<button class="jv-more" id="jmore">${total-shown} more</button>`;
 const tp=c.intro?[]:(D.topics||[]).filter(t=>t.keys.some(k=>k.b===b.name&&c.c>=k.c&&c.c<=k.to));
 if(tp.length&&show('teaching'))rows+=`<div class="jv-tp"><span>Explore this topic</span>${tp.map(t=>`<button data-topic="${t.id}">${esc(t.name)} ›</button>`).join('')}</div>`;
 return h+`<div class="jv-list${tab?' jv-tabbed':''}${JV.anim?' in-'+JV.anim:''}${coreOn()&&tab==='teaching'&&JV.deep?' jv-deep':''}">${rows}</div></div>`}
/* Teaching at a stop: Core (the one exposition to hear) or Go Deeper (everything else, optional) */
/* Go Deeper at a stop: everything shown there besides Core, in the order shown */
function deepGroups(x,G){const {b,c}=x,k=b.abbr+':'+c.c,u=coreHere(x),lt=coreLater(x),cs=new Set([...(u!=null?coreIdsOf(u):[]),...(lt!=null?coreIdsOf(lt):[])]),dp=c.intro?{alt:(G||listenGroups(b,c)).overview.map(g=>g.id)}:(CORE.deep[k]||{});
 const uk=coreKey(x),orig=uk!=null&&typeof uk!=='string'?CORE.u[uk][3]:(uk&&String(uk).startsWith('b:')?(CORE.bk[b.abbr]||{}).ids||[]:[]);
 const extra=orig.filter(id=>!cs.has(id)&&I[id]);                          /* the suggested Core when you replaced it */
 return [[c.intro?'Other overviews':'Other expositions',[...extra,...(dp.alt||[])]],['Verse by verse',dp.verse||[]],[c.intro?'Book overviews':'Broader teaching',dp.broad||[]],['Devotionals',dp.dev||[]]]
  .map(([t,l])=>[t,[...new Set(l)].filter(id=>I[id]&&okWho(id)&&!cs.has(id))]).filter(g=>g[1].length)}
function deepIds(i){const x=walk()[i];return x?deepGroups(x).flatMap(g=>g[1]).filter(id=>I[id].audio):[]}
const inDeep=()=>!!(DEEP&&coreOn()&&cur&&deepIds(DEEP.i).includes(cur));
function coreRows(x,i,G,sec,up){const {b,c}=x,k=b.abbr+':'+c.c,deepOn=!!JV.deep&&!c.sec,u=coreHere(x),later=coreLater(x);
 const ids=u!=null?coreIdsOf(u):[],uk=coreKey(x),groups=deepGroups(x,G);
 const nDeep=groups.reduce((a,g)=>a+g[1].length,0);
 let o=`<div class="jv-sec jv-tsec" id="js-teaching"><span>Teaching</span>${c.sec&&!nDeep?'':`<span class="jv-tg" role="tablist"><button role="tab" data-deep="0" aria-selected="${!deepOn}" class="${deepOn?'':'on'}">Core</button><button role="tab" data-deep="1" aria-selected="${deepOn}" class="${deepOn?'on':''}">Go Deeper${nDeep?' · '+nDeep:''}</button></span>`}</div>`;
 if(!deepOn){
  if(ids.length){ids.forEach(id=>{o+=jRow(id,'',up)});
   if(coreSet()[u])o+=`<p class="jv-why">You chose this one. <button class="lnk" data-coreback="${u}">Back to the suggested teaching</button></p>`}
  else if(later!=null){const L=CORE.u[later],nx=walk().find(w=>w.b.abbr===L[0]&&w.c.c===L[2]),lids=coreIdsOf(later);
   /* a sermon on several chapters is the Core teaching of each; Up next offers it once all its Scripture is read */
   lids.forEach(id=>{o+=jRow(id,'',up)})}
  else o+=`<p class="jv-none">No focused teaching on ${esc(stopName(x))} alone.${nDeep?' Go Deeper has '+nDeep+' related message'+(nDeep>1?'s':'')+'.':''}</p>`}
 else{if(!nDeep)o+=`<p class="jv-none">Nothing more on ${esc(stopName(x))} yet.</p>`;
  groups.forEach(([t,l])=>{o+=`<div class="jv-sub">${t}</div>`;l.forEach(id=>{o+=jRow(id,'',up)})})}
 return o}
function jCont(o={}){const w=walk(),i=jpIdx(),x=w[i],a=nextAction(i);BPM=null;JV.tabFor=null;DEEP=null;
 if(a.kind==='play'){if(cur===a.id){if(o.full)setMini(false);else audio.paused?audio.play().catch(()=>{}):audio.pause();return}JM=true;play(a.id,o.full?{full:true}:{})}
 else if(a.kind==='scripture'){const id=narId(x.b.abbr,x.c.c);if(cur===id){if(o.full)setMini(false);else audio.paused?audio.play().catch(()=>{}):audio.pause();return}JM=true;narPlay(x.b,x.c.c,null,{jm:true,full:!!o.full})}
 else if(a.kind==='walk'){const fr=x,nx=w[a.to];setJP(a.to);camp=a.to;S.set('camp',camp);if(nx.b!==fr.b&&!fr.c.intro)note('You have walked through '+fr.b.name+'.');JV.more=false;render();window.scrollTo({top:0,behavior:'smooth'})}}
function jMove(i,back){const w=walk(),f=jpIdx();if(!w[i])return;if(back)BACK=null;else if(Math.abs(i-f)>1)BACK={from:f};else if(BACK&&i===BACK.from)BACK=null;
 jMove.dir=i>f?'l':i<f?'r':'';setJP(i);camp=i;S.set('camp',camp);JV.more=false;render();jMove.dir='';window.scrollTo({top:0})}
addEventListener('scroll',()=>{const g=$('#jseg');if(!g)return;const t=$('.jv-t');g.classList.toggle('stuck',!!t&&t.getBoundingClientRect().bottom<parseFloat(getComputedStyle(g).top)+8)},{passive:true});
/* a sideways swipe anywhere on the Journey screen steps through the stop's tabs (introduction, scripture, teaching),
   then on to the next stop's first tab; back the same way. Passive, so scrolling stays the phone's own. */
function stopTabs(i){const x=walk()[i];if(!x)return[];const {b,c}=x,t=[];if(stopIntro(x)&&I[stopIntro(x)]||hasIntroText(x))t.push('intro');
 if(c.intro){if(CORE.bk[b.abbr]||listenGroups(b,c).overview.length)t.push('teaching')}else t.push('scripture','teaching');return t}
function jSwipe(dir){const i=jpIdx(),w=walk();
 if(coreOn()){const T=stopTabs(i),g=document.querySelector('#jseg [data-jseg].on'),k=g?T.indexOf(g.dataset.jseg):-1;
  if(k>=0&&k+dir>=0&&k+dir<T.length){JV.tabFor=stopKey(w[i]);JV.tab=T[k+dir];JV.anim=dir>0?'l':'r';const y=scrollY;render();JV.anim='';window.scrollTo(0,y);return}
  const to=i+dir;if(!w[to])return;const T2=stopTabs(to);if(T2.length){JV.tabFor=stopKey(w[to]);JV.tab=dir>0?T2[0]:T2[T2.length-1]}jMove(to);return}
 const to=i+dir;if(w[to])jMove(to)}
{let t0=null;const o={passive:true};
 document.addEventListener('touchstart',e=>{t0=null;if(view!=='journey'||e.touches.length!==1||!$('#jv'))return;const t=e.touches[0];
  if(t.clientX<22||(e.target.closest&&e.target.closest('#np,#sheet,#bps,#jump,#gsr,#tabs,input,textarea,select,.jv-pps')))return;t0={x:t.clientX,y:t.clientY,lx:t.clientX,ly:t.clientY,t:Date.now(),y0:scrollY}},o);
 document.addEventListener('touchmove',e=>{if(t0&&e.touches.length===1){t0.lx=e.touches[0].clientX;t0.ly=e.touches[0].clientY}},o);
 document.addEventListener('touchend',e=>{if(!t0)return;const t=e.changedTouches[0]||{},ex=t.clientX!=null&&t.clientX!==t0.x?t.clientX:t0.lx,ey=t.clientY!=null&&t.clientX!==t0.x?t.clientY:t0.ly,dx=ex-t0.x,dy=ey-t0.y,ok=Date.now()-t0.t<900&&Math.abs(scrollY-t0.y0)<16;t0=null;
  if(ok&&Math.abs(dx)>50&&Math.abs(dx)>1.7*Math.abs(dy))jSwipe(dx<0?1:-1)},o);
 document.addEventListener('touchcancel',()=>{t0=null},o)}
function wireJourney(){corePaint();{const g=$('#jseg');if(g)g.classList.remove('stuck')}const n=$('#jnext');if(n)n.onclick=e=>jCont({full:!e.target.closest('.jv-pp')});
 document.querySelectorAll('[data-deep]').forEach(b=>b.onclick=()=>{JV.deep=b.dataset.deep==='1';const y=scrollY;render();window.scrollTo(0,y)});
 document.querySelectorAll('[data-mkcore]').forEach(b=>b.onclick=()=>{const [u,id]=b.dataset.mkcore.split('|'),set=coreSet();set[u]=[id];S.set('coreSet',set);JV.deep=false;const y=scrollY;render();window.scrollTo(0,y)});
 document.querySelectorAll('[data-coreback]').forEach(b=>b.onclick=()=>{const set=coreSet();delete set[b.dataset.coreback];S.set('coreSet',set);const y=scrollY;render();window.scrollTo(0,y)});
 const rd=$('#jrd');if(rd)rd.onclick=()=>{const bx=$('#jitx'),x=walk()[jpIdx()],open=bx.hidden;bx.hidden=!open;rd.setAttribute('aria-expanded',open);rd.textContent=open?'Hide the introduction':'Read the introduction';
  if(open&&!bx.innerHTML)introText(x.b.abbr).then(T=>{bx.innerHTML=introParas(T[String(x.c.intro?0:x.c.c)]);wireNames(bx)}).catch(()=>{bx.textContent='The text did not load. Check your connection.'})};document.querySelectorAll('#jv [data-topic]').forEach(b=>b.onclick=()=>openTopic(b.dataset.topic));
 document.querySelectorAll('[data-jgo]').forEach(b=>b.onclick=()=>jMove(+b.dataset.jgo,!!b.dataset.back));
 document.querySelectorAll('[data-jseg]').forEach(b=>b.onclick=()=>{const k=b.dataset.jseg,t=$('#js-'+k)||$('.jv-list');
  if(coreOn()){JV.tabFor=stopKey(walk()[jpIdx()]);JV.tab=k;const y=scrollY;render();window.scrollTo(0,y);return}
  /* a step with one thing to do opens it: the reading, the introduction, the overview; Teaching (a choice of sermons) shows its list */
  {const i=jpIdx(),x=walk()[i],st=stepsOf(i);BPM=null;
   const open=id=>{if(cur===id){if(audio.paused)audio.play().catch(()=>{});setMini(false);return true}JM=true;PLAYSTOP=i;play(id,{full:true});return true};
   if(k==='scripture'&&x&&!x.c.intro){const id=narId(x.b.abbr,x.c.c);if(cur===id){if(audio.paused)audio.play().catch(()=>{});setMini(false);return}JM=true;narPlay(x.b,x.c.c,null,{jm:true,full:true});return}
   if(k==='intro'&&x){const ii=stopIntro(x);if(ii&&I[ii]&&open(ii))return}
   if(k==='overview'&&st){const ok=id=>I[id]&&I[id].audio,id=st.ov.find(id=>ok(id)&&!isDone(id))||st.ov.find(ok);if(id&&open(id))return}}
  if(!t)return;if(k!=='overview'||$('#js-overview')){const y=t.getBoundingClientRect().top+scrollY-(($('#zt')||{}).offsetHeight||0)-12;window.scrollTo({top:Math.max(0,y),behavior:'smooth'});const row=t.nextElementSibling&&t.nextElementSibling.classList.contains('jw')?t.nextElementSibling:t;row.classList.remove('flash');void row.offsetWidth;row.classList.add('flash')}});
 const pk=$('#jpick');if(pk)pk.onclick=()=>{camp=jpIdx();openJump('browse')};
 document.querySelectorAll('.jv [data-nk]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(b.dataset.nk,b.dataset.ns)});ppWire();
 /* swipe anywhere on the player: left = on to the next stop, right = back one */
 /* swiping: see jSwipe (one listener for the whole Journey screen) */
const mo=$('#jmore');if(mo)mo.onclick=()=>{JV.more=true;render()};
 document.querySelectorAll('[data-jread]').forEach(b=>b.onclick=()=>{const x=walk()[jpIdx()];read[scrKey(x)]=true;S.set('read',read);RDO=null;render()});
 const scr=full=>{const x=walk()[jpIdx()],id=narId(x.b.abbr,x.c.c);BPM=null;DEEP=null;if(cur===id){if(full)setMini(false);else audio.paused?audio.play().catch(()=>{}):audio.pause();return}const a=nextAction(jpIdx());JM=!!(a&&a.kind==='scripture');narPlay(x.b,x.c.c,null,{jm:JM,full})};
 document.querySelectorAll('[data-jscr]').forEach(b=>b.onclick=e=>{e.stopPropagation();scr(false)});
 document.querySelectorAll('[data-scrrow]').forEach(r=>r.onclick=e=>{if(e.target.closest('button,a'))return;scr(true)});
 /* the book button: the chapter's text opens right here, with no sound */
 document.querySelectorAll('[data-rdopen]').forEach(b=>b.onclick=e=>{e.stopPropagation();const x=walk()[jpIdx()],k=scrKey(x);RDO=RDO===k?null:k;render();if(RDO){const j=$('#jread');if(j)setTimeout(()=>window.scrollTo({top:j.getBoundingClientRect().top+scrollY-140,behavior:'smooth'}),60)}});
 /* changed your mind: listen, starting at the verse you have reached */
 document.querySelectorAll('[data-rdlisten]').forEach(b=>b.onclick=e=>{e.stopPropagation();const x=walk()[jpIdx()],top=[...document.querySelectorAll('#jread .vs')].find(v=>v.getBoundingClientRect().bottom>150),v=top?+top.dataset.v:0;RDO=null;BPM=null;DEEP=null;const a=nextAction(jpIdx());JM=!!(a&&a.kind==='scripture');narPlay(x.b,x.c.c,v>1?v:null,{jm:JM,full:true})});
 document.querySelectorAll('[data-rdclose]').forEach(b=>b.onclick=e=>{e.stopPropagation();RDO=null;render()});
 jrFab();const jr=$('#jread .jr-txt');if(jr){const x=walk()[jpIdx()];loadBook(x.b.name).then(d=>{if(jr.isConnected)jr.innerHTML=chapterBody(d,x.c.c,null)}).catch(()=>{jr.textContent='This chapter could not be opened. Check the connection and try again.'})}}

/* ---- Big Picture: whole-Bible series, each heard in order, each keeping its own place ---- */
let BP=S.get('bp',{}),BPM=null;
const bpList=()=>D.bp||[],bpGet=id=>bpList().find(s=>s.id===id),bpIds=s=>s.parts.flatMap(p=>p[1]).filter(id=>I[id]),bpName=(s,id)=>(s.names&&s.names[id])||dispTitle(I[id]);
function bpAt(s){const ids=bpIds(s),k=BP[s.id]?ids.indexOf(BP[s.id].cur):-1;if(k>=0){if(!isDone(ids[k]))return k;const n=ids.findIndex((id,j)=>j>k&&!isDone(id));return n>=0?n:k}const f=ids.findIndex(id=>!isDone(id));return f<0?0:f}
const unitN=(s,n)=>n+' '+(s.unit==='life'?(n>1?'lives':'life'):(s.unit||'episode')+(n>1?'s':''));
function bpNum(s,id){const it=I[id];return it.sc?it.sc[0]+'.'+it.sc[1]:String(bpIds(s).indexOf(id)+1)}
function bpCover(art,sz){const v={sc:`<rect width="104" height="104" fill="#141b33"/><g fill="#f0d79a"><circle cx="16" cy="16" r="1.1"/><circle cx="34" cy="26" r=".9"/><circle cx="70" cy="12" r="1.2"/><circle cx="88" cy="28" r="1"/><circle cx="56" cy="22" r=".8"/></g><circle cx="52" cy="62" r="28" fill="#c9a24a" opacity=".16"/><path d="M26 70 C 36 64 46 64 52 70 C 58 64 68 64 78 70 V 80 C 68 74 58 74 52 80 C 46 74 36 74 26 80Z" fill="#e9dfc6"/><path d="M52 70 V80" stroke="#141b33" stroke-width="1.2"/><path d="M52 40 C 47 47 47 52 52 56 C 57 52 57 47 52 40Z" fill="#f0d79a"/><text x="52" y="97" text-anchor="middle" font-family="-apple-system,system-ui,sans-serif" font-size="7" font-weight="700" letter-spacing="1.6" fill="#e9cf8c">21 NIGHTS</text>`,survey:`<rect width="104" height="104" fill="#1b2440"/><g fill="#f0d79a"><circle cx="18" cy="20" r="1.2"/><circle cx="40" cy="12" r="1"/><circle cx="78" cy="18" r="1.4"/><circle cx="90" cy="40" r="1"/><circle cx="14" cy="50" r="1"/><circle cx="64" cy="30" r="1"/></g><circle cx="52" cy="64" r="30" fill="#c9a24a" opacity=".14"/><path d="M52 46 C 46 54 46 60 52 64 C 58 60 58 54 52 46Z" fill="#e9cf8c"/><path d="M44 66h16v18H44z" fill="none" stroke="#e9cf8c" stroke-width="2"/><text x="52" y="96" text-anchor="middle" font-family="-apple-system,system-ui,sans-serif" font-size="7" letter-spacing="1.6" fill="#e9cf8c">OT · NT</text>`,
  chronicle:`<rect width="104" height="104" fill="#e7dbbd"/><path d="M16 86 C 36 66 28 50 50 46 C 72 42 66 22 88 16" fill="none" stroke="#9a7524" stroke-width="3" stroke-linecap="round"/><g transform="translate(16 86)" fill="none" stroke="#4f5f3f" stroke-width="1.8" stroke-linecap="round"><path d="M0 0 V-16"/><path d="M0 -12 C -9 -18 -12 -26 -5 -30 C 0 -33 6 -31 7 -26 C 15 -28 16 -18 10 -14 C 6 -12 3 -12 0 -13"/></g><path d="M78 22h20v-12h-4v-5h-4v5h-4v-8h-4v8h-4z" fill="#1b2440"/>`,
  legacies:`<rect width="104" height="104" fill="#2e4639"/><circle cx="52" cy="40" r="30" fill="#f0d79a" opacity=".12"/><circle cx="52" cy="40" r="17" fill="#f0d79a" opacity=".16"/><path d="M52 24 C 46 32 46 38 52 42 C 58 38 58 32 52 24Z" fill="#f0d79a"/><rect x="47" y="44" width="10" height="34" rx="2" fill="#e9dfc6"/><path d="M36 80h32" stroke="#c9a24a" stroke-width="3" stroke-linecap="round"/><text x="52" y="96" text-anchor="middle" font-family="-apple-system,system-ui,sans-serif" font-size="7" letter-spacing="1.6" fill="#e9cf8c">LIVES OF FAITH</text>`,
  sos:`<rect width="104" height="104" fill="#22304f"/><path d="M10 78 C 26 50 40 70 52 46 S 80 30 94 22" fill="none" stroke="#c9a24a" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="1 6"/><g fill="#f0d79a"><circle cx="10" cy="78" r="3.2"/><circle cx="23" cy="60" r="2.4"/><circle cx="36" cy="64" r="2.4"/><circle cx="48" cy="52" r="2.4"/><circle cx="60" cy="40" r="2.4"/><circle cx="72" cy="35" r="2.4"/><circle cx="84" cy="27" r="2.4"/><circle cx="94" cy="22" r="3.6"/></g><text x="12" y="20" font-family="-apple-system,system-ui,sans-serif" font-size="8" font-weight="700" letter-spacing="1" fill="#f0d79a">GEN → REV</text>`,
  '30k':`<rect width="104" height="104" fill="#dfe6df"/><g fill="none" stroke="#8fa08a" stroke-width="1.2"><path d="M-4 30 C 20 20 40 36 60 26 S 96 22 110 30"/><path d="M-4 46 C 22 36 42 54 64 42 S 98 38 110 46"/><path d="M-4 62 C 24 52 44 70 66 58 S 98 56 110 62"/><path d="M-4 78 C 26 68 46 86 68 74 S 98 72 110 78"/><path d="M-4 94 C 28 84 48 100 70 90 S 98 88 110 94"/></g><path d="M14 90 C 34 70 50 64 60 52 S 84 26 92 14" fill="none" stroke="#9a7524" stroke-width="2" stroke-dasharray="4 4" stroke-linecap="round"/><path d="M88 10 l8 2 -6 6z" fill="#1b2440"/><text x="12" y="20" font-family="-apple-system,system-ui,sans-serif" font-size="8" font-weight="700" letter-spacing="1" fill="#1b2440">30,000 FT</text>`}[art]||(String(art).startsWith('kv:')?(()=>{const t=esc(art.slice(3)),fs=t.length>9?8:t.length>6?10:12;   /* a book series: open book and the book's name */
  return `<rect width="104" height="104" fill="#e5ecea"/><rect y="78" width="104" height="26" fill="#2f5d62"/><path d="M22 34 C 34 28 44 30 52 36 C 60 30 70 28 82 34 V 64 C 70 58 60 60 52 66 C 44 60 34 58 22 64Z" fill="#fff" stroke="#2f5d62" stroke-width="2.2" stroke-linejoin="round"/><path d="M52 36V66" stroke="#2f5d62" stroke-width="2"/><text x="52" y="${fs>9?95:94}" text-anchor="middle" font-family="-apple-system,system-ui,sans-serif" font-size="${fs}" font-weight="700" letter-spacing="1.2" fill="#fff">${t}</text>`})():'');
 return `<svg viewBox="0 0 104 104" width="${sz}" height="${sz}" class="bpc" aria-hidden="true">${v}</svg>`}
function bpLen(s){const ids=bpIds(s),known=ids.filter(id=>+I[id].dur>0),sec=known.reduce((t,id)=>t+ +I[id].dur,0);
 return unitN(s,ids.length)+(known.length>=ids.length*.8&&sec?` · about ${Math.round(sec/3600)} hours`:s.id==='30k'?' · Genesis to Revelation':'')}
function bpPlay(sid,id,full){const s=bpGet(sid);if(!s||!I[id])return;const ids=bpIds(s),k=ids.indexOf(id);JM=false;
 if(cur===id&&BPM===sid){if(full)setMini(false);else audio.paused?audio.play().catch(()=>{}):audio.pause();return}
 BPM=sid;const ck=BP[sid]?ids.indexOf(BP[sid].cur):-1;if(k>ck)BP[sid]={cur:id};S.set('bp',BP);S.set('bplast',sid);play(id,full?{full:true}:{});bpLabel()}
function bpLabel(){if(!BPM||!cur)return;const s=bpGet(BPM);if(!s)return;const ids=bpIds(s),k=ids.indexOf(cur);if(k<0)return;$('#np-t').textContent=bpName(s,cur);$('#np-s').textContent=teacher(I[cur])+' · '+s.title+' · '+(k+1)+' of '+ids.length}
/* ---- Bible: Scripture on its own, frictionless. It opens where you left off (or where your Journey is),
   scrolls straight on through chapters and books, and one button reads aloud from the verse at the top of the
   screen, carrying on chapter after chapter (with the narrator's introductions first, if you turn them on).
   Chapters you read here count in your Journey too. ---- */
const BB={pos:S.get('bbpos',null),intros:!!S.get('bbintro',false),first:null,last:null,busy:false,uScroll:0,auto:false,seen:{},q:null,mk:''};
let BBM=false;   /* the narration now playing was started here, so it keeps going */
function bbBook(n){return D.books.find(b=>b.name===n)||D.books[0]}
function bbPos(){const p=BB.pos;if(p&&D.books.some(b=>b.name===p.b)&&p.c>=1)return p;const x=walk()[jpIdx()];return x&&!x.c.intro?{b:x.b.name,c:x.c.c,v:1}:{b:'Genesis',c:1,v:1}}
function bibleView(){const p=bbPos();return `<div class="jv bbv"><div class="bb-h"><button class="bb-tt" id="bbtt" aria-label="Go to a book and chapter"><span id="bbtl">${esc(p.b+' '+p.c)}</span><i>▾</i></button><button class="bb-in${BB.intros?' on':''}" id="bbin" aria-pressed="${BB.intros}">Intros</button><div class="bb-left" id="bbleft"></div></div><button class="bb-up" id="bbup" hidden></button><div class="bb-tx" id="bbtx"><p class="bb-wait">Opening ${esc(p.b+' '+p.c)}…</p></div></div><button class="bb-fab" id="bbfab" aria-label="Listen from here">${icon('play',15,0,'#fff')}<span>Listen</span></button>`}
function bbSec(b,c){return loadBook(b.name).then(d=>{const s=document.createElement('section');s.className='bb-sec';s.dataset.b=b.name;s.dataset.c=c;s.dataset.k=b.abbr+c;s.innerHTML=`<h3 class="bb-ch">${esc(b.name)} ${c}</h3><div class="bb-body">${chapterBody(d,c,null)}</div>`;return s})}
function bbTop(){const h=document.querySelector('.bb-h');return h?h.getBoundingClientRect().bottom:0}
function bbTopVerse(){const t=bbTop()+4;for(const v of document.querySelectorAll('.bb-sec .vs')){if(v.getBoundingClientRect().bottom>t){const s=v.closest('.bb-sec');return {b:s.dataset.b,c:+s.dataset.c,v:+v.dataset.v}}}return null}
function bbScrollTo(y,smooth){BB.auto=true;window.scrollTo({top:Math.max(0,y),behavior:smooth?'smooth':'auto'});clearTimeout(BB.at);BB.at=setTimeout(()=>{BB.auto=false},800)}
function bbUp(){const bt=$('#bbup');if(!bt||!BB.first)return;const pv=chBefore(...BB.first);bt.hidden=!pv;if(!pv)return;bt.textContent='↑ '+pv[0].name+' '+pv[1];
 bt.onclick=()=>{if(BB.busy)return;BB.busy=true;bbSec(...pv).then(sec=>{const h0=document.documentElement.scrollHeight,y0=scrollY;$('#bbtx').prepend(sec);BB.first=pv;bbScrollTo(y0+document.documentElement.scrollHeight-h0);BB.busy=false;bbUp()}).catch(()=>{BB.busy=false})}}
function bbMore(){if(view!=='bible'||BB.busy||!BB.last||document.documentElement.scrollHeight-scrollY-innerHeight>1600)return;const nx=chAfter(...BB.last);if(!nx)return;BB.busy=true;
 bbSec(...nx).then(sec=>{const tx=$('#bbtx');if(tx&&view==='bible'){tx.appendChild(sec);BB.last=nx}BB.busy=false;bbMore()}).catch(()=>{BB.busy=false})}
/* where you are: saved as you scroll; a chapter you read through (for more than a few seconds) counts in your Journey */
function bbScrolled(){if(view!=='bible')return;const t=bbTopVerse();if(!t)return;const was=BB.pos;BB.pos=t;S.set('bbpos',t);const tl=$('#bbtl');if(tl)tl.textContent=t.b+' '+t.c;if(!was||was.b!==t.b||was.c!==t.c)bbLeftPaint();
 if(!was||was.b!==t.b||was.c!==t.c){const r=(S.get('bbrec',[])||[]).filter(x=>!(x.b===t.b&&x.c===t.c));r.unshift({b:t.b,c:t.c});S.set('bbrec',r.slice(0,6))}
 const now=Date.now();let changed=false;document.querySelectorAll('.bb-sec').forEach(s=>{const vs=s.querySelectorAll('.vs');if(!vs.length)return;const f=vs[0].getBoundingClientRect(),l=vs[vs.length-1].getBoundingClientRect();
  if(f.bottom>0&&f.top<innerHeight&&!BB.seen[s.dataset.k])BB.seen[s.dataset.k]=now;
  if(l.top<innerHeight&&l.bottom>0&&BB.seen[s.dataset.k]&&now-BB.seen[s.dataset.k]>15000&&!read[s.dataset.k]){read[s.dataset.k]=true;changed=true}});
 if(changed)S.set('read',read)}
let NPY=0;addEventListener('scroll',()=>{const y=scrollY,dy=y-NPY;if(view!=='bible'){if(document.body.classList.contains('npslim'))document.body.classList.remove('npslim');NPY=y;return}if(Math.abs(dy)>8){document.body.classList.toggle('npslim',dy>0&&y>140);NPY=y}},{passive:true});
addEventListener('scroll',()=>{if(view!=='bible')return;if(!BB.auto)BB.uScroll=Date.now();bbMore();clearTimeout(BB.st);BB.st=setTimeout(bbScrolled,250)},{passive:true});
function wireBible(){const p=bbPos(),b=bbBook(p.b),tx=$('#bbtx');BB.first=[b,p.c];BB.last=[b,p.c];BB.busy=true;BB.seen={};BB.mk='';bbLeftPaint();
 bbSec(b,p.c).then(sec=>{if(view!=='bible')return;tx.innerHTML='';tx.appendChild(sec);BB.busy=false;bbUp();
  const v=(p.v||1)>1?sec.querySelector(`.vs[data-v="${p.v}"]`):null;bbScrollTo(v?v.getBoundingClientRect().top+scrollY-bbTop()-14:0);if(v&&BB.flash===p.v){v.classList.add('bb-flash');setTimeout(()=>v.classList.remove('bb-flash'),2200)}BB.flash=0;setTimeout(bbMore,60);bbSync();if(BBM)bbMark(true)})
  .catch(()=>{BB.busy=false;tx.innerHTML='<p class="bb-wait">This chapter could not be opened. Check the connection and try again.</p>'});
 $('#bbtt').onclick=()=>bbJump();
 $('#bbin').onclick=()=>{BB.intros=!BB.intros;S.set('bbintro',BB.intros);const bt=$('#bbin');bt.classList.toggle('on',BB.intros);bt.setAttribute('aria-pressed',BB.intros);note(BB.intros?'The narrator’s introduction will come before each chapter':'Straight from chapter to chapter');bbLeftPaint();npLeftPaint()};
 $('#bbfab').onclick=()=>{const t=bbTopVerse()||p;bbPlayFrom(bbBook(t.b),t.c,t.v)};bbSync()}
/* reading aloud from here; with intros on, a new chapter starts with its introduction (and a new book with the book's) */
function bbPlayFrom(b,c,v){JM=false;BPM=null;DEEP=null;PLAYSTOP=null;BB.q=null;BBM=true;BB.uScroll=0;
 if(BB.intros&&(!v||v<=1)){const st=[];if(c===1&&introId(b.abbr,0))st.push(introId(b.abbr,0));if(introId(b.abbr,c))st.push(introId(b.abbr,c));if(st.length){BB.q={b,c,st};play(st.shift(),{bb:true});bbSync();return}}
 narPlay(b,c,v&&v>1?v:0,{bb:true});bbSync()}
/* the verse being read is marked, and the page follows it (unless you have just scrolled yourself) */
function bbMark(force){if(!NAR||view!=='bible')return;const t=audio.currentTime;let v=NAR.m&&NAR.m[0]?NAR.m[0][0]:1;for(const m of NAR.m||[]){if(m[1]<=t+0.05)v=m[0];else break}
 const k=NAR.b.abbr+NAR.c;if(!force&&BB.mk===k+':'+v)return;BB.mk=k+':'+v;
 const sec=document.querySelector(`.bb-sec[data-k="${k}"]`);if(!sec){bbEnsure(NAR.b,NAR.c);return}
 document.querySelectorAll('.bb-sec .vs.now').forEach(e=>e.classList.remove('now'));const el=sec.querySelector(`.vs[data-v="${v}"]`);if(!el)return;el.classList.add('now');
 if(Date.now()-BB.uScroll>6000){const r=el.getBoundingClientRect();if(r.top<bbTop()+10||r.bottom>innerHeight*0.72)bbScrollTo(r.top+scrollY-bbTop()-innerHeight*0.16,true)}}
function bbEnsure(b,c){if(BB.busy)return;const nx=BB.last&&chAfter(...BB.last);
 if(nx&&nx[0].name===b.name&&nx[1]===c){BB.busy=true;bbSec(b,c).then(s=>{const tx=$('#bbtx');if(tx){tx.appendChild(s);BB.last=nx}BB.busy=false;bbMark(true)}).catch(()=>{BB.busy=false});return}
 BB.pos={b:b.name,c,v:1};S.set('bbpos',BB.pos);render()}
function bbSync(){const f=$('#bbfab');if(!f)return;f.hidden=!!(BBM&&cur&&!audio.paused);const tb=($('#tabs')||{}).offsetHeight||0,np=$('#np'),nt=np?np.getBoundingClientRect().top:innerHeight;f.style.bottom=(Math.max(tb,nt<innerHeight?innerHeight-nt:0)+14)+'px'}
/* go to: recent places, this book's chapters, every book */
function bbShort(b){return b.name.length<=7?b.name:b.abbr}
function bbJump(sel){const p=bbPos(),cb=sel||p.b,b=bbBook(cb),el=$('#bps'),rec=(S.get('bbrec',[])||[]).filter(x=>D.books.some(y=>y.name===x.b)).slice(0,4),mi=D.books.findIndex(x=>x.name==='Matthew');
 const grid=bs=>`<div class="bb-bk">${bs.map(x=>`<button data-bbb="${esc(x.name)}" class="${x.name===cb?'on':''}">${esc(bbShort(x))}</button>`).join('')}</div>`;
 el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh bb-js" role="dialog" aria-modal="true" aria-label="Go to"><button class="grab2" data-bpsx aria-label="Close"></button><div class="bps-t" style="margin:6px 4px 10px">Go to</div>
  <label class="bb-sf"><svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><input id="bbq" type="search" enterkeyhint="go" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="Book, chapter or words" aria-label="Find a book, chapter or words"><button id="bbqx" type="button" aria-label="Clear" hidden>✕</button></label>
  <div id="bbres"></div><div id="bbmain">
  ${rec.length?`<div class="bb-cur"><div class="bb-k">Recent</div><div class="bb-rec">${rec.map(x=>`<button data-bbgo="${esc(x.b)}|${x.c}">${esc(x.b+' '+x.c)}</button>`).join('')}</div></div>`:''}
  <div class="bb-cur"><div class="bb-k">${esc(b.name)} · chapter</div><div class="bb-cg">${Array.from({length:+b.n},(_,i)=>i+1).map(c=>`<button data-bbgo="${esc(b.name)}|${c}" class="${b.name===p.b&&c===p.c?'here':''}">${c}</button>`).join('')}</div></div>
  <div class="bb-grp"><div class="bb-k">Old Testament</div>${grid(D.books.slice(0,mi))}</div><div class="bb-grp"><div class="bb-k">New Testament</div>${grid(D.books.slice(mi))}</div></div></div>`;
 const opening=el.hidden;el.hidden=false;document.body.classList.add('bpsopen');if(opening)requestAnimationFrame(()=>el.classList.add('on'));
 el.querySelectorAll('[data-bpsx]').forEach(x=>x.onclick=closeSeries);
 el.querySelectorAll('[data-bbb]').forEach(x=>x.onclick=()=>{bbJump(x.dataset.bbb);const sh=el.querySelector('.bps-sh');if(sh)sh.scrollTop=0});
 bbWireGo(el);const q=$('#bbq');q.oninput=()=>{clearTimeout(BB.jt);$('#bbqx').hidden=!q.value;BB.jt=setTimeout(bbFilter,120)};
 q.onkeydown=e=>{if(e.key!=='Enter')return;e.preventDefault();bbFilter();const f=$('#bbres [data-bbv]')||(document.querySelectorAll('#bbmain .bb-bk button:not([hidden])').length===1?$('#bbmain .bb-bk button:not([hidden])'):null);if(f)f.click();else q.blur()};
 $('#bbqx').onclick=()=>{q.value='';$('#bbqx').hidden=true;bbFilter();q.focus()}}
function bbGo(bn,c,v){BB.pos={b:bn,c:+c,v:+v||1};BB.flash=+v>1?+v:0;S.set('bbpos',BB.pos);{const r=(S.get('bbrec',[])||[]).filter(y=>!(y.b===bn&&y.c===+c));r.unshift({b:bn,c:+c});S.set('bbrec',r.slice(0,6))}closeSeries();render();window.scrollTo(0,0)}
function bbWireGo(root){root.querySelectorAll('[data-bbgo]').forEach(x=>x.onclick=()=>{const [bn,c]=x.dataset.bbgo.split('|');bbGo(bn,c,1)});root.querySelectorAll('[data-bbv]').forEach(x=>x.onclick=()=>{const [bn,c,v]=x.dataset.bbv.split('|');bbGo(bn,c,v)})}
/* the search field: a reference jumps, letters narrow the books, words find verses (all, one testament, or this book) */
function bbBookMatch(b,n){if(!n)return true;const nz=n.replace(/\s+/g,''),nm=srNorm(b.name),A=D.alias||{};
 return nm.startsWith(n)||nm.replace(/\s+/g,'').startsWith(nz)||(!/^\d/.test(n)&&nm.replace(/^\d\s*/,'').startsWith(n))||srNorm(b.abbr).startsWith(nz)||(nz.length>=2&&Object.keys(A).some(k=>A[k]===b.name&&k.replace(/\s+/g,'').startsWith(nz)))}
function bbFilter(){const inp=$('#bbq'),res=$('#bbres'),main=$('#bbmain');if(!inp||!res||!main)return;const q=inp.value.trim(),n=srNorm(q);main.classList.toggle('typing',!!n);
 let ref=n?srRef(q):null;if(ref&&!ref.c)ref=null;let shown=[];   /* a book name alone ("neh", "nehemiah") is a book, not a jump: the Go to card needs a chapter */
 main.querySelectorAll('.bb-bk button').forEach(x=>{const b=bbBook(x.dataset.bbb),on=!n||(ref?b.name===ref.b.name:bbBookMatch(b,n));x.hidden=!on;if(on&&n)shown.push(b)});
 main.querySelectorAll('.bb-grp').forEach(g=>{g.hidden=!!n&&!g.querySelector('.bb-bk button:not([hidden])')});
 const AL=D.alias||{},nz=n.replace(/\s+/g,''),exact=n&&!ref?D.books.find(b=>srNorm(b.name)===n||AL[n]===b.name||AL[nz]===b.name):null,
  wordy=!ref&&n.replace(/[0-9:]/g,'').trim().length>=3&&!shown.length;   /* words search the text when they are not a book name */
 let h='';if(ref){const {b,c,v,e}=ref,cc=c||1,lab=b.name+' '+cc+(v?':'+v+(e?'–'+e:''):'');h+=`<button class="bb-jr" data-bbv="${esc(b.name)}|${cc}|${v||1}"><span><small>Go to</small><b>${esc(lab)}</b></span><i>›</i></button>`}
 else if(exact||shown.length===1){const b=exact||shown[0];h+=`<div class="bb-k">${esc(b.name)} · chapter</div><div class="bb-cg">${Array.from({length:+b.n},(_,i)=>i+1).map(c=>`<button data-bbgo="${esc(b.name)}|${c}">${c}</button>`).join('')}</div>`}
 if(wordy)h+=`<div id="bbvs"><div class="bb-k">In the Bible</div><p class="bb-none">Searching…</p></div>`;
 else if(n&&!ref&&!shown.length)h+=`<p class="bb-none">No book by that name. Type a few more letters to search the words.</p>`;
 res.innerHTML=h;bbWireGo(res);if(wordy)bbWords(n)}
function bbWords(n){const W=n.replace(/[0-9:]/g,' ').split(' ').filter(Boolean),ph=W.join(' '),f=BB.jf||'all',mi=D.books.findIndex(x=>x.name==='Matthew'),here=bbPos().b,k=BB.jk||20;
 srBible().then(all=>{const box=$('#bbvs'),inp=$('#bbq');if(!box||!inp||srNorm(inp.value.trim())!==n)return;const A=[],B=[];
  all.forEach(([b,d],bi)=>{if(!d)return;if(f==='ot'&&bi>=mi||f==='nt'&&bi<mi||f==='book'&&b.name!==here)return;d.chapters.forEach((vs,ci)=>(vs||[]).forEach(x=>{const t=srNorm(x.t);if(t.includes(ph))A.push([b,ci+1,x]);else if(W.length>1&&W.every(w=>t.includes(w)))B.push([b,ci+1,x])}))});
  const L=[...A,...B],chip=(v,l)=>`<button data-bbf="${v}" class="${f===v?'on':''}">${esc(l)}</button>`;
  box.innerHTML=`<div class="bb-k">In the Bible${L.length?' · '+L.length.toLocaleString()+' verse'+(L.length>1?'s':''):''}</div><div class="bb-flt">${chip('all','All')}${chip('ot','Old Testament')}${chip('nt','New Testament')}${chip('book',here)}</div>`
   +(L.length?L.slice(0,k).map(([b,c,x])=>`<button class="bb-vr" data-bbv="${esc(b.name)}|${c}|${x.v}"><b>${esc(b.name+' '+c+':'+x.v)}</b><span>${srHi(srSnip(x.t,ph,W),W)}</span></button>`).join('')+(L.length>k?`<button class="bb-more" data-bbmore>Show more</button>`:''):`<p class="bb-none">Nothing found${f!=='all'?' here':''} for “${esc(n)}”.</p>`);
  bbWireGo(box);box.querySelectorAll('[data-bbf]').forEach(x=>x.onclick=()=>{BB.jf=x.dataset.bbf;BB.jk=20;bbWords(n)});const m=box.querySelector('[data-bbmore]');if(m)m.onclick=()=>{BB.jk=k+40;bbWords(n)}})
  .catch(()=>{const box=$('#bbvs');if(box)box.innerHTML='<p class="bb-none">The Bible text did not load. Check your connection.</p>'})}
function bpView(){return `<div class="jv bpv">${moreBtn()}<div class="jv-eb">Guided listening</div><h1 class="jv-t">Series</h1>`+bpCont()+bpBody()+'</div>'}
/* the series you are in the middle of, one tap to carry on (also at the top of Library) */
function bpCont(){const ls=bpGet(S.get('bplast',''));let h='';
 if(ls&&BP[ls.id]){const ids=bpIds(ls),k=bpAt(ls),id=ids[k],it=I[id],pl=cur===id&&!audio.paused,left=leftOf(id);
  h+=`<button class="bp-cont" data-bpcont="${ls.id}">${bpCover(ls.art,64)}<span class="bp-ct"><small>Continue · ${esc(ls.title)}</small><b>${esc(bpName(ls,id))}</b><em>${esc(teacher(it))}${left?' · '+atSpd(left)+' left':` · ${k+1} of ${unitN(ls,ids.length)}`}</em></span><span class="bp-pp">${icon(pl?'pause':'play',16,0,'#1b2440')}</span></button>`}return h}
function bpBody(){const L=bpList();let h='';
 const row=s=>{const ids=bpIds(s),st=!!BP[s.id],k=bpAt(s),f=ids.filter(isDone).length/ids.length,U={session:'Session',flight:'Flight'}[s.unit];
  return `<button class="bp-row" data-bps="${s.id}">${bpCover(s.art,104)}<span class="bp-rt"><b>${esc(s.title)}</b><span class="by">${esc(s.by)}</span><span class="ds">${esc(s.desc.split('. ')[0].replace(/\.$/,''))}.</span><span class="pr"><i><b style="width:${f>0?Math.max(3,Math.round(100*f)):0}%"></b></i>${st||f>0?(U?`${U} ${k+1} of ${ids.length}`:`${k+1} of ${unitN(s,ids.length)}`):`${unitN(s,ids.length)} · not started`}</span></span></button>`};
 [['bp','Big Picture','The whole story of Scripture, start to finish'],['sc','Secret Church','David Platt’s six-hour nights of Bible study, every session in order'],['kv','Kennon Vaughan','His series at Harvest Church, Memphis: whole books, sermon by sermon'],['growth','Spiritual Growth','Teaching to grow by, one series at a time']].forEach(([g,t,sub])=>{
  if(g==='sc'){if(D.sc&&D.sc.ids.length){const N=D.sc.ids.length,n=D.sc.ids.filter(isDone).length,f=n/N;
    h+=`<div class="jv-sec">${t}</div><p class="bp-gs">${sub}</p><button class="bp-row" id="opensc">${bpCover('sc',104)}<span class="bp-rt"><b>Secret Church</b><span class="by">David Platt</span><span class="ds">Every night of Secret Church, from the whole Bible to prayer, suffering and the end of the world.</span><span class="pr"><i><b style="width:${f>0?Math.max(3,Math.round(100*f)):0}%"></b></i>${n?`${n} of ${N} sessions heard`:`${scGroups().length} nights · ${N} sessions · not started`}</span></span></button>`}return}
  const G=L.filter(s=>(s.group||'bp')===g);if(G.length)h+=`<div class="jv-sec">${t}</div><p class="bp-gs">${sub}</p>`+G.map(row).join('')});
 return h}
function openSeries(sid){const s=bpGet(sid);if(!s)return;const ids=bpIds(s),k=bpAt(s),el=$('#bps'),st=!!BP[s.id];
 let list='';s.parts.forEach(([t,p])=>{if(t)list+=`<div class="jv-sub">${esc(t)}</div>`;p.filter(id=>I[id]).forEach(id=>{const j=ids.indexOf(id),done=isDone(id),left=leftOf(id),now=j===k&&st;
  list+=`<button class="bp-ep${done?' heard':''}${now?' now':''}" data-bpplay="${id}"><span class="n">${bpNum(s,id)}</span><b>${esc(bpName(s,id))}</b><span class="d">${done?'✓':left?atSpd(left)+' left':I[id].dur?Math.round(I[id].dur/60)+' min':''}</span></button>`})});
 el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${esc(s.title)}"><button class="grab2" data-bpsx aria-label="Close"></button>
  <div class="bps-hd">${bpCover(s.art,128)}<div><div class="bps-t">${esc(s.title)}</div><div class="bps-by">${esc(s.by)}</div><div class="bps-n">${bpLen(s)}</div></div></div><p class="bps-d">${esc(s.desc)}</p>
  <button class="bps-go" data-bpcont="${s.id}"><span>${icon('play',16,0,'#fff')}</span><span><b>${st?'Continue Listening':'Begin'}</b><em>${esc(bpNum(s,ids[k])+' · '+bpName(s,ids[k]))}</em></span></button><div class="bps-list">${list}</div></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));
 el.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);el.querySelectorAll('[data-bpcont]').forEach(b=>b.onclick=()=>{const t=bpGet(b.dataset.bpcont);bpPlay(t.id,bpIds(t)[bpAt(t)]);closeSeries()});
 el.querySelectorAll('[data-bpplay]').forEach(b=>b.onclick=()=>{bpPlay(s.id,b.dataset.bpplay,true);closeSeries()});
 const sh=el.querySelector('.bps-sh');let y0=null;sh.ontouchstart=e=>{y0=sh.scrollTop<=0?e.touches[0].clientY:null};sh.ontouchmove=e=>{if(y0==null)return;const dy=e.touches[0].clientY-y0;if(dy>0){sh.style.transform=`translateY(${dy}px)`}};sh.ontouchend=e=>{if(y0==null)return;const dy=e.changedTouches[0].clientY-y0;y0=null;sh.style.transform='';if(dy>90)closeSeries()}}
function closeSeries(){const el=$('#bps');el.classList.remove('on');document.body.classList.remove('bpsopen');setTimeout(()=>{if(!el.classList.contains('on')){el.hidden=true;el.innerHTML='';if(view==='bigpicture'||view==='library')render()}},260)}
function wireBP(){document.querySelectorAll('#main [data-bps]').forEach(b=>b.onclick=()=>openSeries(b.dataset.bps));document.querySelectorAll('#main [data-bpcont]').forEach(b=>b.onclick=()=>{const t=bpGet(b.dataset.bpcont);bpPlay(t.id,bpIds(t)[bpAt(t)])})}

/* ---- Library: Secret Church, the four teachers, what you played lately ---- */
const TCH_C={Platt:'#2f4a6b',PAM:'#7a4b2a',Skip:'#5b4a7a',Davey:'#3c5a4c',Fearless:'#6b5320',Vaughan:'#2f5d62'};
let LT=S.get('libtab','teachers');
/* each topic's tile: a muted colour and a line drawing, like the teachers' and series' covers */
const TOPIC_IC={kingdom:['#6b5320','<path d="M4 17 3 7l5 4 4-6 4 6 5-4-1 10z"/><path d="M4 20.5h16"/>'],
 prayer:['#2f4a6b','<path d="M11.4 3.5c-.8 0-1.4.7-1.4 1.6V12l-3.2 3.6a1.6 1.6 0 0 0 .1 2.2l2.6 2.7"/><path d="M12.6 3.5c.8 0 1.4.7 1.4 1.6V12l3.2 3.6a1.6 1.6 0 0 1-.1 2.2l-2.6 2.7"/><path d="M12 4.5V16"/>'],
 spirit:['#8a4a2a','<path d="M12 3c.6 3 4.5 4.8 4.5 9.5a4.5 4.5 0 0 1-9 0c0-2.2 1.1-3.6 2.2-4.4.2 1.7 1 2.6 2.1 2.9C11.2 8.7 10.9 6 12 3z"/>'],
 marriage:['#7a4b5e','<circle cx="9" cy="14.5" r="5"/><circle cx="15" cy="14.5" r="5"/><path d="m13.4 5.6 1.6-2.1 1.6 2.1L15 7.8z"/>'],manhood:['#46566e','<path d="M7 21V9h10v12"/><path d="M7 9V5h2v2h2V5h2v2h2V5h2v4"/><path d="M10.5 21v-3.5a1.5 1.5 0 0 1 3 0V21"/><path d="M5 21h14"/>'],
 disciple:['#3c5a4c','<path d="M7 3.5c1.7 0 2.5 1.8 2.5 4S8.6 11 7 11 4.5 9.7 4.5 7.5 5.3 3.5 7 3.5z"/><path d="M5.2 13.5h3.6l-.3 2.2a1.5 1.5 0 0 1-3 0z"/><path d="M17 8.5c1.7 0 2.5 1.8 2.5 4S18.6 16 17 16s-2.5-1.3-2.5-3.5.8-4 2.5-4z"/><path d="M15.2 18.5h3.6l-.3 2a1.5 1.5 0 0 1-3 0z"/>'],
 holiness:['#1b2440','<circle cx="12" cy="12" r="4"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>'],
 repent:['#6b3a3a','<path d="M7 20V10a5 5 0 0 1 10 0v5"/><path d="m13.5 12 3.5 3.5 3.5-3.5"/>'],
 faith:['#2e5a6b','<circle cx="12" cy="5" r="2"/><path d="M12 7v14"/><path d="M5 13.5a7 7 0 0 0 14 0"/><path d="M8.5 10.5h7"/>'],
 grace:['#5b4a7a','<path d="M12 3v18M7 8.5h10"/>'],
 suffering:['#4a5272','<path d="M12 3.5s6 6.4 6 10.5a6 6 0 0 1-12 0c0-4.1 6-10.5 6-10.5z"/><path d="M9.2 14.5a2.9 2.9 0 0 0 2.8 2.6"/>'],
 enemy:['#4a4f63','<path d="M12 3 5 5.8v5.4c0 4.4 3 8 7 9.8 4-1.8 7-5.4 7-9.8V5.8z"/><path d="M12 8v7M9 11h6"/>'],
 church:['#7a4b2a','<path d="M12 2v4M10 4h4"/><path d="M5 21V11l7-5 7 5v10z"/><path d="M10 21v-4.5a2 2 0 0 1 4 0V21"/>'],
 missions:['#2e4639','<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.7 3.5 5.7 3.5 9s-1 6.3-3.5 9c-2.5-2.7-3.5-5.7-3.5-9s1-6.3 3.5-9z"/>']};
const topicIc=(id,sz)=>{const t=TOPIC_IC[id]||['#4a5272',''];return `<span class="tp-ic" style="background:${t[0]}1a;width:${sz}px;height:${sz}px" aria-hidden="true"><svg viewBox="0 0 24 24" width="${Math.round(sz*.56)}" height="${Math.round(sz*.56)}" fill="none" stroke="${t[0]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" opacity=".85">${t[1]}</svg></span>`};
/* Worship (site_extra/worship.js does the music): a personal songbook, setlists, and Present, which hands the set to
   live/ (presenter and remote) and tv/ (the screen). Songs and setlists live on this phone and in your private backup. */
const WS={pane:S.get('wpane','sets'),song:null,edit:null,set:null,q:'',am:null,past:false};
/* setlists by date: a set may carry a day ('YYYY-MM-DD', your local calendar); one without is a saved set (a playlist) */
function wToday(o){const d=new Date();if(o)d.setDate(d.getDate()+o);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
function wDate(s){const m=/^(\d{4})-(\d\d)-(\d\d)$/.exec(s||'');return m?new Date(+m[1],+m[2]-1,+m[3]):null}
function wIn(st){const d=wDate(st&&st.date);return d?Math.round((d.getTime()-d.getTimezoneOffset()*6e4)/864e5)-dayNo():null}   /* days from today */
function wWhen(st){const d=wDate(st.date),n=wIn(st);if(!d)return '';if(n===0)return new Date().getHours()>=15?'Tonight':'Today';if(n===1)return 'Tomorrow';
 if(n>1&&n<7)return d.toLocaleDateString('en-US',{weekday:'long'})+' · in '+n+' days';return d.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'})}
function wGroups(sets){const g={today:[],upcoming:[],saved:[],past:[]};sets.forEach(st=>{const n=wIn(st);(n==null?g.saved:n===0?g.today:n>0?g.upcoming:g.past).push(st)});
 g.upcoming.sort((a,b)=>a.date.localeCompare(b.date));g.past.sort((a,b)=>b.date.localeCompare(a.date));g.saved.sort((a,b)=>(a.name||'').localeCompare(b.name||''));return g}
const wSongs=()=>S.get('wsongs',{}),wSets=()=>S.get('wsets',[]);
function wId(){return 'w'+Date.now().toString(36)+Math.random().toString(36).slice(2,6)}
function wLive(){const w=S.get('wlive',null);return w&&Date.now()-w.at<12*3600e3?w:null}
const W_IC={back:'<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
 play:'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5v14l12-7z" fill="currentColor"/></svg>',
 apple:'<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18V6l11-2v12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="18" r="2.5" fill="currentColor"/><circle cx="17.5" cy="16" r="2.5" fill="currentColor"/></svg>'};
/* the key a song is played in: the setlist's choice, else the song's own, else as written; capo turns it into shapes */
const W_SPOT='<svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M7.5 9.5c3-1 6.5-.7 9 .9M8 12.6c2.5-.7 5.3-.4 7.4.8M8.6 15.5c2-.5 4-.3 5.7.6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
/* Apple Music: always the song itself (an album link with ?i= becomes the song's own link) */
function amLink(u){if(!u)return '';const m=/music\.apple\.com\/([a-z]{2})\/album\/[^?]*\?(?:.*&)?i=(\d+)/.exec(u);return m?'https://music.apple.com/'+m[1]+'/song/'+m[2]:u}
/* Spotify from the Apple Music recording, through song.link (free, no account) */
function wQ(s){return encodeURIComponent((s.t||'')+' '+(s.a||'')).replace(/%20/g,'+')}
function wAm(s){return s.am?amLink(s.am):'https://music.apple.com/us/search?term='+wQ(s)}
function wSp(s){return s.sp||'https://open.spotify.com/search/'+encodeURIComponent((s.t||'')+' '+(s.a||''))}
function wLinks(s,cls){return `<a class="w-btn ${cls}" href="${esc(wAm(s))}" target="_blank" rel="noopener" aria-label="Listen on Apple Music">${W_IC.apple}</a><a class="w-btn ${cls}" href="${esc(wSp(s))}" target="_blank" rel="noopener" aria-label="Listen on Spotify">${W_SPOT}</a>`}
function wKeyOf(song,item){return (item&&item.key)||song.pk||song.key||''}
function wShape(song,key,capo){const semis=song.key&&key?Worship.semitones(song.key,key):0,sk=capo?Worship.transposeKey(key,-capo):key;return {semis:((semis-(capo||0))%12+12)%12,flats:sk||key||false,shapeKey:sk}}
function wParsed(song){return song._p&&song._p.src===song.src&&song._p.pv===Worship.PV?song._p.v:(song._p={src:song.src,pv:Worship.PV,v:Worship.parse(song.src)}).v}   /* read again after the reader improves */
function wOrder(song){const p=wParsed(song);if(!song.arr||!song.arr.trim())return null;const by={};p.sections.forEach((s,i)=>{const k=s.short.toLowerCase();if(!(k in by))by[k]=i;const l=s.label.toLowerCase();if(!(l in by))by[l]=i});
 const o=song.arr.split(/[\s,>→-]+/).map(t=>by[t.toLowerCase()]).filter(i=>i!=null);return o.length?o:null}
function wDeckSong(song,item){const p=wParsed(song),key=wKeyOf(song,item),capo=item&&item.capo!=null?item.capo:(song.capo||0),sh=wShape(song,key,capo);
 return {id:song.id,t:song.t,a:song.a||'',key,capo,slides:Worship.slides({parsed:p},wOrder(song)),short:p.sections.map(s=>s.short),src:song.src||'',semis:sh.semis||0,flats:!!sh.flats}}
/* the link carries the whole songbook: this set first, then every other song (A to Z), so anyone helping can pick any song */
/* a worship time lasts until End, or until it has sat untouched this long; then Present starts a new one and the TV follows */
const WLIVE_IDLE=4*3600e3;
function wPresent(items,name){const songs=wSongs(),list=items.map(it=>songs[it.id]&&wDeckSong(songs[it.id],it)).filter(Boolean);if(!list.length)return;
 const inSet=new Set(list.map(s=>s.id)),rest=Object.values(songs).filter(s=>s&&!inSet.has(s.id)).sort((x,y)=>String(x.t).localeCompare(String(y.t),undefined,{numeric:true,sensitivity:'base'})).map(s=>wDeckSong(s,null)),set=list.map((x,i)=>i);
 {const old=S.get('wlive',null);if(old&&old.sid&&old.key&&Date.now()-(old.last||old.at)<WLIVE_IDLE){const now=Date.now();S.set('wlive',Object.assign({},old,{name:name||list[0].t,last:now,go:now,deck:{name:name||'',set,songs:list.concat(rest),dv:now}}));location.href='live/#s='+old.sid+'&k='+old.key+'&lead=1';return}}
 const b=new Uint8Array(28);crypto.getRandomValues(b);const u=x=>btoa(String.fromCharCode.apply(null,x)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
 const sid=u(b.slice(0,12)),key=u(b.slice(12,28));{const old=S.get('wlive',null);if(old&&old.sid){const pv=(S.get('wprev',[])||[]).filter(x=>x&&x.sid!==old.sid&&Date.now()-x.at<8*24*3600e3);pv.unshift({sid:old.sid,key:old.key,at:Date.now()});S.set('wprev',pv.slice(0,4))}}S.set('wlive',{sid,key,at:Date.now(),last:Date.now(),go:Date.now(),name:name||list[0].t,deck:{name:name||'',set,songs:list.concat(rest)}});
 location.href='live/#s='+sid+'&k='+key+'&lead=1'}
function wHead(t){return `<div class="jv wsp">${moreBtn()}<h1 class="jv-t" style="margin-top:6px">${t}</h1>`}
function worshipView(){
 if(WS.edit)return wEditView();if(WS.song)return wSongView();if(WS.set)return wSetView();
 const live=wLive();let h=wHead('Worship')+`<div class="t-sort lib-seg" role="tablist" aria-label="Worship">${[['sets','Setlists'],['songs','Songs']].map(([v,l])=>`<button role="tab" data-wp="${v}" class="${WS.pane===v?'on':''}" aria-selected="${WS.pane===v}">${l}</button>`).join('')}</div>`;
 if(live)h+=`<a class="w-live" href="live/#s=${live.sid}&k=${live.key}&lead=1"><i></i><span><b>Live now</b><small>${esc(live.name||'')} · back to the presentation</small></span>${W_IC.play}</a>`;
 const songs=wSongs(),ids=Object.keys(songs).sort((a,b)=>songs[a].t.localeCompare(songs[b].t));
 if(WS.pane==='songs'){
  if(ids.length>8)h+=`<input class="w-q" id="wq" type="search" placeholder="Search your songs" value="${esc(WS.q)}">`;
  const q=WS.q.trim().toLowerCase(),show=ids.filter(id=>!q||(songs[id].t+' '+(songs[id].a||'')).toLowerCase().includes(q));
  h+=show.length?`<div class="w-list">${show.map(id=>{const s=songs[id];return `<button class="w-row" data-wsong="${id}"><span><b class="serif">${esc(s.t)}</b><small>${esc([s.a,wKeyOf(s)&&'Key '+wKeyOf(s)].filter(Boolean).join(' · '))}</small></span><i>›</i></button>`}).join('')}</div>`
   :`<p class="w-empty">${ids.length?'No song matches.':'Your songbook is empty. Add a song by pasting its chord chart: chords above the words, or ChordPro.'}</p>`;
  return h+`<button class="w-add" data-wnew>Add a song</button></div>`}
 const sets=wSets();
 const titles=st=>st.items.map(it=>(songs[it.id]||{}).t).filter(Boolean),g=wGroups(sets);
 const row=(st,past)=>`<button class="w-row${past?' w-pastrow':''}" data-wset="${st.id}"><span>${st.date?`<em class="w-when">${esc(wWhen(st))}</em>`:''}<b class="serif">${esc(st.name||'Untitled set')}</b><small>${st.items.length} song${st.items.length===1?'':'s'}${st.items.length?' · '+esc(titles(st).slice(0,3).join(', ')):''}</small></span><i>›</i></button>`;
 const card=st=>`<button class="w-tn" data-wset="${st.id}"><span class="k">${esc(wWhen(st))} · ${wDate(st.date).toLocaleDateString('en-US',{weekday:'long'})}</span><b class="serif">${esc(st.name||'Untitled set')}</b>${st.items.length?`<ol>${titles(st).slice(0,8).map((t,i)=>`<li><em>${i+1}</em>${esc(t)}</li>`).join('')}</ol>`:''}<span class="go"><span>${st.items.length} song${st.items.length===1?'':'s'}</span><span>Open ›</span></span></button>`;
 h+=sets.length?g.today.map(card).join('')+(g.upcoming.length?`<div class="w-grp">Coming up</div><div class="w-list">${g.upcoming.map(st=>row(st)).join('')}</div>`:'')
   +(g.saved.length?`${g.today.length||g.upcoming.length||g.past.length?'<div class="w-grp">Saved</div>':''}<div class="w-list">${g.saved.map(st=>row(st)).join('')}</div>`:'')
   +(g.past.length?`<button class="w-past" data-wpast aria-expanded="${WS.past}">Past sets · ${g.past.length} ${WS.past?'⌃':'⌄'}</button>${WS.past?`<div class="w-list">${g.past.map(st=>row(st,1)).join('')}</div>`:''}`:'')
  :`<p class="w-empty">${ids.length?'Gather songs into a setlist for your next worship time.':'Start by adding songs in the Songs tab, then gather them into a setlist.'}</p>`;
 return h+`<button class="w-add" data-wnewset>New setlist</button></div>`}
function wSongView(){const s=wSongs()[WS.song];if(!s){WS.song=null;return worshipView()}
 const key=wKeyOf(s),capo=s.capo||0,sh=wShape(s,key,capo),p=wParsed(s),set=WS.from&&wSets().find(x=>x.id===WS.from),pos=set?set.items.findIndex(it=>it.id===s.id):-1;
 return `<div class="jv wsp wsong"><div class="w-st"><button class="w-back" data-wback aria-label="Back">${W_IC.back}</button><div class="w-tt"><b class="serif">${esc(s.t)}</b><small>${esc([s.a,set&&pos>=0?'Song '+(pos+1)+' of '+set.items.length:''].filter(Boolean).join(' · '))}</small></div>
 <button class="w-btn sm gold w-pres" data-wpresent="${s.id}">${W_IC.play}Present</button><button class="w-kchip${WS.tools?' on':''}" data-wtools aria-expanded="${!!WS.tools}">${esc(key||'Key')}${capo?' · capo '+capo:''} ▾</button></div>
 ${WS.tools?`<div class="w-tools"><div class="w-keys"><span class="w-kl">Key</span><button class="w-kb" data-wk="-1" aria-label="Key down">−</button><b class="w-kv">${esc(key||'?')}</b><button class="w-kb" data-wk="1" aria-label="Key up">+</button>
 <span class="w-kl" style="margin-left:auto">Capo</span><button class="w-kb" data-wc="-1" aria-label="Capo down">−</button><b class="w-kv">${capo}</b><button class="w-kb" data-wc="1" aria-label="Capo up">+</button></div>
 ${capo&&sh.shapeKey?`<div class="w-capo">Capo ${capo}: play ${esc(sh.shapeKey)} shapes, sounds in ${esc(key)}</div>`:''}
 <div class="w-acts">${wLinks(s,'sm ic')}<button class="w-btn sm" data-wedit="${s.id}">Edit</button></div></div>`:''}
 ${p.sections.length?`<div class="wfit" id="wfit"><div class="wc">${Worship.chartHTML({parsed:p},{semis:sh.semis,flats:sh.flats})}</div><span class="wfit-pg" id="wfpg" hidden></span></div>`:'<p class="w-empty">No chart yet. Tap the key button, then Edit, to paste one.</p>'}</div>`}
/* next or previous song when the song was opened from a setlist */
function wStep(d){const set=WS.from&&wSets().find(x=>x.id===WS.from);if(!set)return false;const ids=set.items.map(it=>it.id).filter(id=>wSongs()[id]),i=ids.indexOf(WS.song),j=i+d;if(i<0||j<0||j>=ids.length)return false;WS.song=ids[j];render();return true}
/* the chart fills the screen below the header: biggest text that fits, more columns on iPad and sideways; pages turn by a tap at the side */
function wFitSong(){const box=$('#wfit');if(!box)return;const tb=($('#tabs')||{}).offsetHeight||0,top=box.getBoundingClientRect().top+scrollY;
 box.style.height=Math.max(150,innerHeight-top-tb-6)+'px';const info=Worship.fit(box);box._fit=info;box._pg=WS.toLast&&info.pages>1?info.pages-1:0;WS.toLast=false;Worship.turn(box,box._pg,info);
 const pg=$('#wfpg'),show=()=>{if(pg){pg.hidden=info.pages<2;pg.textContent=(box._pg+1)+' / '+info.pages}};show();
 const go=d=>{const i=box._fit,n=box._pg+d;if(i&&n>=0&&n<i.pages){box._pg=n;Worship.turn(box,n,i);show();return}if(d<0)WS.toLast=true;if(!wStep(d))WS.toLast=false};
 box.onclick=e=>{if(box._swiped&&Date.now()-box._swiped<400)return;const i=box._fit;if(!i||i.pages<2)return;const r=box.getBoundingClientRect();go(e.clientX-r.left>r.width/2?1:-1)};
 if(!box._sw){box._sw=1;Worship.swipe(box,go)}}
/* re-fit when the screen changes size or turns: Safari does not always send 'resize' when an iPad turns, so the
   page's own size is watched too */
function wRefit(){if(view==='worship'&&WS.song&&!WS.edit){clearTimeout(wFitSong.t);wFitSong.t=setTimeout(wFitSong,150)}}
addEventListener('resize',wRefit);addEventListener('orientationchange',()=>setTimeout(wRefit,250));
if(window.visualViewport)visualViewport.addEventListener('resize',wRefit);
if(window.ResizeObserver){let lw=0,lh=0;new ResizeObserver(()=>{const w=innerWidth,h=innerHeight;if(w===lw&&h===lh)return;lw=w;lh=h;wRefit()}).observe(document.documentElement)}
/* songs found for you (and any added later) arrive through your private backup: songs/inbox.json; each comes in once */
async function wsInbox(force){if(!bkOn()||wsInbox.busy||(!force&&Date.now()-(wsInbox.last||0)<10*60e3))return;wsInbox.busy=true;wsInbox.last=Date.now();
 try{const r=await bkGH('/contents/songs/inbox.json');if(!r.ok)return;const j=await r.json();let c=j.content;if(!c||j.encoding!=='base64'){const r2=await bkGH('/git/blobs/'+j.sha);c=(await r2.json()).content}
  const d=JSON.parse(bkUn64(c)),imp=new Set(S.get('wimp',[])),songs=wSongs();let n=0;
  (d.songs||[]).forEach(x=>{const o=songs[x.id];
   if(o&&(x.rev||0)>(o.rev||0)){o.rev=x.rev;o.am=x.am||o.am;o.sp=x.sp||o.sp;if(!o.edited){o.src=x.src;o.t=x.t;o.a=x.a;o.key=x.key;o.notes=x.notes;delete o._p}n++;return}
   if(imp.has(x.id))return;imp.add(x.id);if(!o){songs[x.id]=Object.assign({},x,{at:Date.now()});n++}});
  const sets=wSets();(d.sets||[]).forEach(x=>{if(imp.has(x.id))return;imp.add(x.id);if(!sets.some(y=>y.id===x.id)){sets.unshift(Object.assign({},x,{items:x.items.filter(it=>songs[it.id])}));n++}});
  if(n){S.set('wsongs',songs);S.set('wsets',sets)}S.set('wimp',[...imp]);if(n&&view==='worship'){const y=scrollY;render();scrollTo(0,y)}}catch(e){}finally{wsInbox.busy=false}}
setTimeout(()=>wsInbox(),4000);
function wEditView(){const isNew=WS.edit==='new',s=isNew?{t:'',a:'',key:'',capo:0,am:'',notes:'',src:'',arr:''}:wSongs()[WS.edit];if(!s){WS.edit=null;return worshipView()}
 const keys=[''].concat(Worship.KEYS_MAJ,Worship.KEYS_MIN);
 return `<div class="jv wsp"><button class="w-back" data-wcancel>${W_IC.back}${isNew?'Songs':'Back'}</button><h1 class="w-title serif">${isNew?'Add a song':'Edit song'}</h1>
 <label class="w-f"><span>Title</span><input id="wf-t" value="${esc(s.t)}" autocomplete="off"></label>
 <label class="w-f"><span>Artist or worship collective</span><input id="wf-a" value="${esc(s.a||'')}" autocomplete="off"></label>
 <div class="w-two"><label class="w-f"><span>Key the chart is written in</span><select id="wf-k">${keys.map(k=>`<option ${k===(s.key||'')?'selected':''} value="${k}">${k||'(from the chart)'}</option>`).join('')}</select></label>
 <label class="w-f"><span>Capo</span><select id="wf-c">${[0,1,2,3,4,5,6,7].map(c=>`<option ${c===(s.capo||0)?'selected':''}>${c}</option>`).join('')}</select></label></div>
 ${s.src?'':`<button class="w-btn w-pastebtn" id="wf-clip" type="button">Paste from clipboard</button>`}<p class="w-hint w-tidy" id="wf-tidy" hidden></p>
 <label class="w-f"><span>Chord chart</span><textarea id="wf-src" rows="16" spellcheck="false" autocapitalize="off" placeholder="Paste the chart: chords on their own line above the words, with section names like Verse 1, Chorus, Bridge. ChordPro works too.">${esc(s.src||'')}</textarea></label>
 <div class="w-found" id="wf-found"></div>
 <label class="w-f"><span>Order to sing it (optional), e.g. V1 C V2 C B C</span><input id="wf-arr" value="${esc(s.arr||'')}" autocomplete="off" autocapitalize="characters"></label>
 <label class="w-f"><span>Apple Music link</span><input id="wf-am" value="${esc(s.am||'')}" placeholder="https://music.apple.com/…" autocomplete="off" inputmode="url"></label>
 <label class="w-f"><span>Spotify link</span><input id="wf-sp" value="${esc(s.sp||'')}" placeholder="https://open.spotify.com/track/…" autocomplete="off" inputmode="url"></label>
 <button class="w-btn" id="wf-find">${W_IC.apple}Find the recording</button><div id="wf-res"></div>
 <label class="w-f"><span>Notes</span><textarea id="wf-n" rows="2">${esc(s.notes||'')}</textarea></label>
 <div class="w-acts"><button class="w-btn pri" id="wf-save">Save</button><button class="w-btn" data-wcancel>Cancel</button>${isNew?'':'<button class="w-btn w-del" id="wf-del">Delete</button>'}</div></div>`}
function wSetView(){const sets=wSets(),st=sets.find(x=>x.id===WS.set);if(!st){WS.set=null;return worshipView()}const songs=wSongs();
 return `<div class="jv wsp"><button class="w-back" data-wback>${W_IC.back}Setlists</button>
 <input class="w-name serif" id="ws-name" value="${esc(st.name||'')}" placeholder="Name this set">
 <div class="w-dl"><label class="w-date"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg><span id="ws-dtxt">${wDateTxt(st)}</span><span aria-hidden="true">⌄</span><input type="date" id="ws-date" value="${esc(st.date||'')}" aria-label="The day of this set"></label>${st.date?'<button class="w-nod" data-wnodate>No date</button>':''}</div>
 <div class="w-acts"><button class="w-btn pri" data-wpresentset="${st.id}" ${st.items.length?'':'disabled'}>${W_IC.play}Present</button><button class="w-btn" data-wpick>Add songs</button></div>
 ${st.items.length?`<div class="w-items">${st.items.map((it,i)=>{const s=songs[it.id];if(!s)return '';const key=wKeyOf(s,it);return `<div class="w-it"><span class="w-n">${i+1}</span><button class="w-itt" data-wsong="${s.id}"><b class="serif">${esc(s.t)}</b><small>${esc(s.a||'')}</small></button>
  <span class="w-ik"><button class="w-kb s" data-wik="${i}|-1" aria-label="Key down">−</button><b>${esc(key||'?')}</b><button class="w-kb s" data-wik="${i}|1" aria-label="Key up">+</button></span>
  <span class="w-mv"><button data-wmv="${i}|-1" aria-label="Move up" ${i?'':'disabled'}>↑</button><button data-wmv="${i}|1" aria-label="Move down" ${i<st.items.length-1?'':'disabled'}>↓</button><button data-wrm="${i}" aria-label="Remove">✕</button></span></div>`}).join('')}</div>`:'<p class="w-empty">No songs yet. Tap Add songs.</p>'}
 <div class="w-acts"><button class="w-btn" data-wagain>Use again…</button><button class="w-btn" data-wdup>Duplicate</button><button class="w-btn w-del" data-wdelset>Delete</button></div></div>`}
function wDateTxt(st){const d=wDate(st.date);if(!d)return 'No date';const n=wIn(st),rel=n===0?'today':n===1?'tomorrow':n>1&&n<7?'in '+n+' days':n===-1?'yesterday':'';
 return esc(d.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'}))+(rel?` <small>· ${rel}</small>`:'')}
/* the next day on the same weekday as this set's (from tomorrow on); a set with no day: today */
function wNextLike(st){const d=wDate(st.date);if(!d)return wToday();let o=1;while(o<8&&(new Date(Date.now()+o*864e5)).getDay()!==d.getDay())o++;return wToday(o)}
function wSaveSet(st){const sets=wSets(),i=sets.findIndex(x=>x.id===st.id);st.at=Date.now();if(i<0)sets.unshift(st);else sets[i]=st;S.set('wsets',sets)}
/* a pasted chord-site page: keep the chart, fill the title, artist and key from the page if they are empty; Undo puts the paste back */
function wPasteIn(raw,whole){const box=$('#wf-src'),note=$('#wf-tidy');if(!box)return false;const c=Worship.clean(raw);if(!c.dropped&&!c.title&&!c.key&&!whole)return false;
 const before=box.value,a=box.selectionStart,z=box.selectionEnd,ins=c.src;box.value=whole||!before?ins:before.slice(0,a)+ins+before.slice(z);
 const filled=[];if(c.title&&!$('#wf-t').value.trim()){$('#wf-t').value=c.title;filled.push('title')}if(c.artist&&!$('#wf-a').value.trim()){$('#wf-a').value=c.artist;filled.push('artist')}
 const k=$('#wf-k');if(c.key&&k&&!k.value&&[...k.options].some(o=>o.value===c.key)){k.value=c.key;filled.push('key '+c.key)}
 const cp=$('#wf-c');if(c.capo&&cp&&cp.value==='0'){cp.value=String(c.capo);filled.push('capo '+c.capo)}
 if(note){note.hidden=false;note.innerHTML=(c.dropped?`Tidied the paste: removed ${c.dropped} line${c.dropped===1?'':'s'} from the web page`:'Pasted')+(filled.length?' · filled in the '+filled.join(', '):'')+`. <button class="lnk" id="wf-undo" type="button">Undo</button>`;
  $('#wf-undo').onclick=()=>{box.value=whole||!before?raw:before.slice(0,a)+raw+before.slice(z);note.hidden=true;wFound()}}
 const cb=$('#wf-clip');if(cb)cb.hidden=true;wFound();return true}
function wFound(){const box=$('#wf-found');if(!box)return;const p=Worship.parse($('#wf-src').value);
 const warn=(p.warnings||[]).length?`<span class="w-warn">${p.warnings.slice(0,4).map(esc).join('<br>')}</span>`:'';   /* what the chart reader could not use: shown, never blocking */
 box.innerHTML=(p.sections.length?'Found: '+p.sections.map(s=>`<span class="w-sc">${esc(s.short)}</span> ${esc(s.label)}${s.rep>1?' ×'+s.rep:''}${s.ref?' (repeat)':''}${s.missing?' (not in this chart)':''}`).join(' · ')+(p.meta.title&&!$('#wf-t').value?` <button class="lnk" id="wf-use">Use “${esc(p.meta.title)}” as the title</button>`:''):'')+warn;
 const u=$('#wf-use');if(u)u.onclick=()=>{$('#wf-t').value=p.meta.title;if(p.meta.artist&&!$('#wf-a').value)$('#wf-a').value=p.meta.artist;if(p.meta.key&&!$('#wf-k').value)$('#wf-k').value=Worship.keyInfo(p.meta.key)?p.meta.key:'';wFound()}}
/* Apple Music: the store's own search (no account), so you pick the exact recording and artist */
function wAmSearch(q,cb){fetch('https://itunes.apple.com/search?media=music&entity=song&limit=12&term='+encodeURIComponent(q),{cache:'no-store'}).then(r=>{if(!r.ok)throw r.status;return r.json()}).then(d=>cb((d&&d.results)||[])).catch(()=>wAmJsonp(q,cb))}
function wAmJsonp(q,cb){const n='amcb'+Date.now();const sc=document.createElement('script');let done=false;window[n]=d=>{done=true;delete window[n];sc.remove();cb((d&&d.results)||[])};
 sc.src='https://itunes.apple.com/search?media=music&entity=song&limit=12&term='+encodeURIComponent(q)+'&callback='+n;sc.onerror=()=>{if(!done){delete window[n];cb(null)}};document.head.appendChild(sc);setTimeout(()=>{if(!done)cb(null)},9000)}
function wireWorship(){wsInbox();document.body.classList.toggle('wsong-open',!!(WS.song&&!WS.edit));if(WS.song&&!WS.edit)requestAnimationFrame(wFitSong);
 document.querySelectorAll('[data-wtools]').forEach(b=>b.onclick=()=>{WS.tools=!WS.tools;render()});
 document.querySelectorAll('[data-wp]').forEach(b=>b.onclick=()=>{WS.pane=b.dataset.wp;S.set('wpane',WS.pane);render()});
 const q=$('#wq');if(q)q.oninput=()=>{WS.q=q.value;const y=q.selectionStart;render();const n=$('#wq');n.focus();n.setSelectionRange(y,y)};
 document.querySelectorAll('[data-wsong]').forEach(b=>b.onclick=()=>{WS.song=b.dataset.wsong;WS.from=WS.set;WS.set=null;render();scrollTo(0,0)});
 document.querySelectorAll('[data-wset]').forEach(b=>b.onclick=()=>{WS.set=b.dataset.wset;render();scrollTo(0,0)});
 document.querySelectorAll('[data-wpast]').forEach(b=>b.onclick=()=>{WS.past=!WS.past;const y=scrollY;render();window.scrollTo(0,y)});
 document.querySelectorAll('[data-wback]').forEach(b=>b.onclick=()=>{if(WS.song){WS.song=null;if(WS.from){WS.set=WS.from;WS.from=null}}else WS.set=null;render();scrollTo(0,0)});
 document.querySelectorAll('[data-wnew]').forEach(b=>b.onclick=()=>{WS.edit='new';render();scrollTo(0,0)});
 document.querySelectorAll('[data-wedit]').forEach(b=>b.onclick=()=>{WS.edit=b.dataset.wedit;render();scrollTo(0,0)});
 document.querySelectorAll('[data-wcancel]').forEach(b=>b.onclick=()=>{WS.edit=null;render();scrollTo(0,0)});
 document.querySelectorAll('[data-wnewset]').forEach(b=>b.onclick=()=>{const st={id:wId(),name:'',items:[],date:wToday()};wSaveSet(st);WS.set=st.id;render();scrollTo(0,0);const n=$('#ws-name');if(n)n.focus()});
 document.querySelectorAll('[data-wpresent]').forEach(b=>b.onclick=()=>wPresent([{id:b.dataset.wpresent}],''));
 document.querySelectorAll('[data-wpresentset]').forEach(b=>b.onclick=()=>{const st=wSets().find(x=>x.id===b.dataset.wpresentset);if(st)wPresent(st.items,st.name)});
 const song=WS.song&&wSongs()[WS.song];
 document.querySelectorAll('[data-wk]').forEach(b=>b.onclick=()=>{const all=wSongs(),s=all[WS.song],k=wKeyOf(s);if(!k){alert('Set the key in Edit first.');return}s.pk=Worship.transposeKey(k,+b.dataset.wk);if(s.pk===s.key)delete s.pk;delete s._p;S.set('wsongs',all);render()});
 document.querySelectorAll('[data-wc]').forEach(b=>b.onclick=()=>{const all=wSongs(),s=all[WS.song];s.capo=Math.max(0,Math.min(9,(s.capo||0)+ +b.dataset.wc));delete s._p;S.set('wsongs',all);render()});
 // editor
 const src=$('#wf-src');if(src){src.oninput=wFound;wFound();
  src.addEventListener('paste',e=>{const raw=e.clipboardData&&e.clipboardData.getData('text/plain');if(!raw)return;if(wPasteIn(raw,false))e.preventDefault()});
  {const cb=$('#wf-clip');if(cb)cb.onclick=()=>{const fail=()=>{const n=$('#wf-tidy');if(n){n.hidden=false;n.textContent='Your phone kept the clipboard to itself: tap and hold the chart box below, then Paste.'}src.focus()};
   try{navigator.clipboard.readText().then(t=>{if(!t||!t.trim()){fail();return}wPasteIn(t,true)}).catch(fail)}catch(e){fail()}}}
  $('#wf-find').onclick=()=>{const t=$('#wf-t').value.trim(),a=$('#wf-a').value.trim(),res=$('#wf-res');if(!t){res.innerHTML='<p class="w-hint">Type the title first.</p>';return}res.innerHTML='<p class="w-hint">Searching Apple Music…</p>';
   wAmSearch(t+' '+a,r=>{if(r===null){res.innerHTML='<p class="w-hint">Apple Music did not answer. Paste the link from the Music app instead (Share → Copy Link).</p>';return}
    const norm=x=>String(x||'').toLowerCase().replace(/[^a-z0-9]/g,'');r=r.filter(x=>x.trackViewUrl);
    r.sort((x,y)=>(norm(y.artistName).includes(norm(a))&&a?1:0)-(norm(x.artistName).includes(norm(a))&&a?1:0));
    res.innerHTML=r.length?`<div class="w-am">${r.slice(0,8).map((x,i)=>`<button data-am="${i}"><img src="${esc(x.artworkUrl60||'')}" alt="" loading="lazy"><span><b>${esc(x.trackName)}</b><small>${esc(x.artistName)} · ${esc(x.collectionName||'')}</small></span>${a&&norm(x.artistName).includes(norm(a))?'<i>✓ artist</i>':''}</button>`).join('')}</div><p class="w-hint">Pick the exact recording. Several artists often record the same song.</p>`:'<p class="w-hint">No match. Try the title alone, or paste the link.</p>';
    res.querySelectorAll('[data-am]').forEach(b=>b.onclick=()=>{const x=r[+b.dataset.am],am='https://music.apple.com/us/song/'+x.trackId;$('#wf-am').value=am;if(!$('#wf-a').value)$('#wf-a').value=x.artistName;
     res.innerHTML=`<p class="w-hint">Apple Music: ${esc(x.trackName)} · ${esc(x.artistName)}<br>Spotify: the button opens a Spotify search for this song. For the exact track, paste its link (Spotify → Share → Copy Song Link).</p>`})})};
  $('#wf-save').onclick=()=>{const t=$('#wf-t').value.trim();if(!t){alert('Give the song a title.');return}const all=wSongs(),id=WS.edit==='new'?wId():WS.edit,o=all[id]||{id};
   const p=Worship.parse(src.value);let key=$('#wf-k').value||(p.meta.key&&Worship.keyInfo(p.meta.key)?p.meta.key:'');
   Object.assign(o,{id,t,a:$('#wf-a').value.trim(),key,capo:+$('#wf-c').value||0,src:src.value,arr:$('#wf-arr').value.trim(),am:amLink($('#wf-am').value.trim()),sp:$('#wf-sp').value.trim(),notes:$('#wf-n').value.trim(),at:Date.now(),edited:1});delete o._p;
   if(o.am&&!/^https:\/\/(music|itunes)\.apple\.com\//.test(o.am)){alert('That does not look like an Apple Music link (it should start with https://music.apple.com/).');return}
   if(o.sp&&!/^https:\/\/open\.spotify\.com\//.test(o.sp)){alert('That does not look like a Spotify link (it should start with https://open.spotify.com/).');return}
   all[id]=o;S.set('wsongs',all);WS.edit=null;WS.song=id;render();scrollTo(0,0)};
  const del=$('#wf-del');if(del)del.onclick=()=>{if(!confirm('Delete this song? It is also taken out of your setlists.'))return;const all=wSongs();delete all[WS.edit];S.set('wsongs',all);S.set('wsets',wSets().map(st=>(st.items=st.items.filter(it=>it.id!==WS.edit),st)));WS.edit=null;WS.song=null;render()}}
 // setlist
 const st=WS.set&&wSets().find(x=>x.id===WS.set);
 if(st){const nm=$('#ws-name');nm.onchange=()=>{st.name=nm.value.trim();wSaveSet(st)};
  document.querySelectorAll('[data-wmv]').forEach(b=>b.onclick=()=>{const [i,d]=b.dataset.wmv.split('|').map(Number),j=i+d;[st.items[i],st.items[j]]=[st.items[j],st.items[i]];wSaveSet(st);render()});
  document.querySelectorAll('[data-wrm]').forEach(b=>b.onclick=()=>{st.items.splice(+b.dataset.wrm,1);wSaveSet(st);render()});
  document.querySelectorAll('[data-wik]').forEach(b=>b.onclick=()=>{const [i,d]=b.dataset.wik.split('|').map(Number),it=st.items[i],s=wSongs()[it.id],k=wKeyOf(s,it);if(!k){alert('Set this song’s key in Edit first.');return}it.key=Worship.transposeKey(k,d);wSaveSet(st);render()});
  document.querySelectorAll('[data-wdup]').forEach(b=>b.onclick=()=>{const c={id:wId(),name:(st.name||'Set')+' (copy)',items:st.items.map(x=>Object.assign({},x))};wSaveSet(c);WS.set=c.id;render();scrollTo(0,0)});
  /* use again: the same set on a new day (the next of its weekday), the calendar open to change it */
  document.querySelectorAll('[data-wagain]').forEach(b=>b.onclick=()=>{const c={id:wId(),name:st.name||'',items:st.items.map(x=>Object.assign({},x)),date:wNextLike(st)};wSaveSet(c);WS.set=c.id;render();scrollTo(0,0);
   const di=$('#ws-date');if(di)try{di.showPicker?di.showPicker():di.focus()}catch(e){di.focus()}});
  {const di=$('#ws-date');if(di)di.onchange=()=>{st.date=di.value||undefined;if(!st.date)delete st.date;wSaveSet(st);const tx=$('#ws-dtxt');if(tx)tx.innerHTML=wDateTxt(st)};
   if(di)di.onblur=()=>setTimeout(()=>{if(view==='worship'&&WS.set===st.id&&!WS.song&&document.body.contains(di)){const y=scrollY;render();window.scrollTo(0,y)}},0)}   /* after the calendar closes; never mid-redraw */
  document.querySelectorAll('[data-wnodate]').forEach(b=>b.onclick=()=>{delete st.date;wSaveSet(st);render()});
  document.querySelectorAll('[data-wdelset]').forEach(b=>b.onclick=()=>{if(!confirm('Delete this setlist? The songs stay in your songbook.'))return;S.set('wsets',wSets().filter(x=>x.id!==st.id));WS.set=null;render()});
  document.querySelectorAll('[data-wpick]').forEach(b=>b.onclick=()=>{const songs=wSongs(),ids=Object.keys(songs).sort((a,c)=>songs[a].t.localeCompare(songs[c].t));
   if(!ids.length){alert('Your songbook is empty: add songs in the Songs tab first.');return}
   const box=document.createElement('div');box.className='w-pick';box.innerHTML=`<div class="w-pk"><h3 class="serif">Add songs</h3><div class="w-pl">${ids.map(id=>`<label><input type="checkbox" value="${id}"><span><b>${esc(songs[id].t)}</b><small>${esc(songs[id].a||'')}</small></span></label>`).join('')}</div><div class="w-acts"><button class="w-btn pri" id="wpk-ok">Add</button><button class="w-btn" id="wpk-x">Cancel</button></div></div>`;
   document.body.appendChild(box);box.onclick=e=>{if(e.target===box||e.target.id==='wpk-x')box.remove()};
   $('#wpk-ok').onclick=()=>{box.querySelectorAll('input:checked').forEach(c=>st.items.push({id:c.value}));wSaveSet(st);box.remove();render()}})}}
function libView(){const cnt={};Object.values(I).forEach(i=>{if(i.tr!=='devotional'&&i.audio&&!i.nar)cnt[i.who]=(cnt[i.who]||0)+1});
 const bpOf=id=>bpList().find(s=>bpIds(s).includes(id));
 let h=`<div class="jv lib">${moreBtn()}<h1 class="jv-t" style="margin-top:6px">Library</h1>${bpCont()}<div class="t-sort lib-seg" role="tablist" aria-label="Browse by">${[['teachers','Teachers'],['series','Series'],['topics','Topics'],['books','Books']].map(([v,l])=>`<button role="tab" data-lt="${v}" class="${LT===v?'on':''}" aria-selected="${LT===v}">${l}</button>`).join('')}</div>`;
 if(LT==='series')return h+`<div class="lib-ser">${bpBody()}</div></div>`;
 if(LT==='topics'){h+=`<p class="lib-lead">What Scripture teaches about a subject, across every book and teacher.</p>`+(D.topics||[]).map(t=>{const n=t.ess.length+t.more.length+(t.bks||[]).reduce((s,g)=>s+g.ids.length,0);return `<button class="lib-tp" data-topic="${t.id}">${topicIc(t.id,36)}<span><b>${esc(t.name)}${t.private?LOCK_IC:''}</b><em>${t.private?'Only on your devices':esc(t.blurb.split(/(?<=[.:])\s/)[0].replace(/[.:]$/,''))}</em></span><i>${n}</i></button>`}).join('');return h+'</div>'}
 if(LT==='books'){const n={};const w=walk(),fa=firstAt();Object.values(I).forEach(i=>{if(i.tr==='devotional'||i.nar||!i.audio)return;const st=w[fa[i.id]];if(st)n[st.b.name]=(n[st.b.name]||0)+1});
  const grid=bs=>`<div class="lib-bk">${bs.map(b=>`<button data-lbook="${esc(b.name)}"><b>${esc(b.name)}</b><em>${n[b.name]||0}</em></button>`).join('')}</div>`;const mi=D.books.findIndex(b=>b.name==='Matthew'),ot=D.books.slice(0,mi),nt=D.books.slice(mi);
  return h+`<div class="jv-sec">Old Testament</div>${grid(ot)}<div class="jv-sec">New Testament</div>${grid(nt)}</div>`}
 const rec=Object.entries(prog).filter(([id,p])=>I[id]&&!I[id].nar&&p&&p.at).sort((a,z)=>z[1].at-a[1].at).slice(0,6);

 {const nf=favList().length;if(nf)h+=`<button class="lib-t sh-row fav-row" data-favs><span class="av sh-av fav-av">${IC_HEART(true).replace(/19/g,'21')}</span><span><b>Favorites</b><em>${nf} sermon${nf===1?'':'s'} you’ve marked</em></span><i>›</i></button>`}
 h+=`<div class="jv-sec sh-sec"><span>Teachers</span>${shLenPick()}</div><button class="lib-t sh-row" data-shuf=""><span class="av sh-av"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg></span><span><b>Shuffle</b><em id="shsub">A sermon you haven’t heard</em></span><i class="sh-pl"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8.5 5.6v12.8a.8.8 0 0 0 1.2.7l10-6.4a.8.8 0 0 0 0-1.4l-10-6.4a.8.8 0 0 0-1.2.7z" fill="currentColor"/></svg></i></button>`+['Platt','PAM','Skip','Davey','Vaughan','Fearless'].filter(k=>!HIDE.includes(k)).filter(k=>cnt[k]).map(k=>`<button class="lib-t" data-tch="${k}"><span class="av" style="background:${TCH_C[k]}">${(n=>n[0][0]+n[n.length-1][0])(NAMES[k].split(' '))}</span><span><b>${NAMES[k]}</b><em>${(cnt[k]||0).toLocaleString()} teachings</em></span><i>›</i></button>`).join('');
 const fav=Object.entries(S.get('fav',{})).filter(([id])=>I[id]).sort((a,z)=>z[1]-a[1]);
 if(false&&fav.length)h+=`<div class="jv-sec">Saved</div><div class="lib-rec">${fav.slice(0,12).map(([id])=>{const left=leftOf(id);return `<button data-full="${id}"><small>${esc(teacher(I[id]).split(' ').slice(-1)[0])}</small><b>${esc(dispTitle(I[id]))}</b><em>${esc(I[id].pass?shortPass(I[id].pass):'')}${isDone(id)?' · heard':left?' · '+atSpd(left)+' left':''}</em></button>`}).join('')}</div>`;
 if(rec.length)h+=`<div class="jv-sec">Recently played</div><div class="lib-rec">${rec.map(([id,p])=>{const s=bpOf(id),left=leftOf(id);return `<button data-${s?'bpplay2':'full'}="${id}"${s?` data-sid="${s.id}"`:''}><small>${s?'Series':'Journey'}</small><b>${esc(s?bpName(s,id):dispTitle(I[id]))}</b><em>${esc(teacher(I[id]).split(' ').slice(-1)[0])} · ${p.done?'heard':left?atSpd(left)+' left':'started'}</em></button>`}).join('')}</div>`;
 const sk=Object.keys(SKIP).length;if(sk)h+=`<button class="lnk lib-sk" id="unskip">${sk} skipped for now — bring them back</button>`;
 return h+'</div>'}
/* a sheet over the page (#bps) holding a list of teachings; rows play in place */
function openListSheet(label,inner,list,after){   /* a sheet of sermons (topic, book); openSheet is the atlas's people and places */const el=$('#bps');el.innerHTML=`<div class="bps-bg" data-bpsx></div><div class="bps-sh" role="dialog" aria-modal="true" aria-label="${esc(label)}"><button class="grab2" data-bpsx aria-label="Close"></button>${inner}<div id="tlist">${list()}</div></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));el.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);
 const wireL=()=>{el.querySelectorAll('#tlist [data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();JM=false;BPM=null;PLAYSTOP=null;DEEP=null;play(b.dataset.play);setTimeout(()=>{$('#tlist').innerHTML=list();wireL()},60)});wireOpen(el);if(after)after(el,()=>{$('#tlist').innerHTML=list();wireL()})};wireL();return el}
/* a topic: what it is, the key passages (each opens that stop on the Journey), the Secret Church night on it, essential teaching, then the rest by teacher */
function goStop(bk,c){const w=walk(),i=w.findIndex(x=>x.b.name===bk&&!x.c.intro&&x.c.c===c);if(i<0)return;closeSeries();JZ='stop';S.set('jz',JZ);if(view!=='journey'){if(view!=='settings')PREV=view;view='journey';S.set('view',view)}jMove(i)}
function openSCNight(n){closeSeries();OPEN.add('sc:'+n);view='sc';S.set('view',view);render();setTimeout(()=>{const d=document.querySelector(`[data-sck="sc:${n}"]`);if(d){d.open=true;d.scrollIntoView({block:'start'})}},40)}
/* Private topics: defined in your private backup repo (private/topics.json) and built here, only on devices that have
   your backup key. Nothing about them is in this public page; a device without the key never asks for them. */
const PT_ORDER={Platt:0,PAM:1,Davey:2,Skip:3,Vaughan:4,Fearless:5},LOCK_IC='<svg class="pt-lock" viewBox="0 0 24 24" width="12" height="12" aria-label="Private"><rect x="5" y="11" width="14" height="9" rx="2" fill="currentColor"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
function ptTitle(t){t=(t||'').replace(/\s*\([^)]*\d[^)]*\)\s*/g,' ');let g=t.split('|').map(x=>x.trim());if(g.length>2)g=g.slice(0,2);else if(g.length===2&&/David Platt|^[A-Z][a-z]+ [A-Z][a-z]+$|Image Of|Kingmaker|Let Down|How To Fight|Here As It Is/.test(g[1]))g=g.slice(0,1);return g.join(' | ').trim()}
function ptKey(t){return ptTitle(t).toLowerCase().replace(/’/g,"'").replace(/[^a-z0-9]+/g,' ').trim()}
function ptBuild(d){let R=null,N;try{R=d.rx?new RegExp(d.rx,'i'):null;N=d.nx?new RegExp(d.nx,'i'):null}catch(e){return null}
 const best={};if(R)for(const i of Object.values(I)){if(i.tr==='devotional'||!i.audio||i.nar||String(i.id).startsWith('int:'))continue;const t=ptTitle(i.t);if(!R.test(t)||(N&&N.test(t))||/^\s*Secret Church\b/.test(t))continue;
  const k=i.who+'|'+ptKey(i.t),r=[i.dur?1:0,i.date||''],h=best[k];if(!h||r[0]>h.r[0]||(r[0]===h.r[0]&&r[1]>h.r[1]))best[k]={r,id:i.id}}
 const ids=Object.values(best).map(x=>x.id),ess=[];
 for(const pat of d.ess||[]){let P;try{P=new RegExp(pat,'i')}catch(e){continue}const hit=ids.filter(x=>P.test(ptTitle(I[x].t))&&!ess.includes(x)).sort((a,b)=>String(I[a].date||'').localeCompare(String(I[b].date||'')));if(hit.length)ess.push(hit[0])}
 /* whole books the topic takes in: every message on that book, chapter by chapter, then the book overviews */
 const bks=[],inBk=new Set();for(const p of d.pb||[]){const b=(D.books||[]).find(x=>x.name===p.b);if(!b)continue;const L=[],ok=id=>{const i=I[id];return i&&i.audio&&!i.nar&&!i.sc&&!/^\s*Secret Church\b/.test(i.t)&&!ess.includes(id)&&!L.includes(id)};
  const ord=(a,b)=>(PT_ORDER[I[a].who]??9)-(PT_ORDER[I[b].who]??9);
  for(const ch of b.ch||[])for(const id of (ch.ids||[]).filter(ok).sort(ord))L.push(id);for(const id of (b.ov||[]).filter(ok).sort(ord))L.push(id);
  if(L.length){bks.push({label:p.label||p.b,ids:L});L.forEach(x=>inBk.add(x))}}
 const sc=d.sc||[],more=ids.filter(x=>!ess.includes(x)&&!inBk.has(x)&&!(I[x].sc&&sc.includes(I[x].sc[0]))).sort((a,b)=>((PT_ORDER[I[a].who]??9)-(PT_ORDER[I[b].who]??9))||ptKey(I[a].t).localeCompare(ptKey(I[b].t)));
 return {id:d.id,name:d.name,blurb:d.blurb||'',keys:d.keys||[],sc,ess,bks,more,private:true}}
function ptApply(defs){D.topics=(D.topics||[]).filter(t=>!t.private);for(const d of defs||[]){if(!d||!d.id||!(d.rx||(d.pb&&d.pb.length)))continue;const t=ptBuild(d);if(!t)continue;D.topics.push(t);if(d.icon)TOPIC_IC[d.id]=d.icon}
 if(view==='library'&&LT==='topics')render()}
async function ptLoad(){if(!bkOn()){try{localStorage.removeItem('sc:ptdef')}catch(e){}if((D.topics||[]).some(t=>t.private))ptApply([]);return}
 const c=S.get('ptdef',null);if(c)ptApply(c);   /* kept on this device only (not a synced key) */
 try{const r=await bkGH('/contents/private/topics.json',{accept:'raw'});if(r.status===404){S.set('ptdef',[]);ptApply([]);return}if(!r.ok)return;const defs=await r.json();if(!Array.isArray(defs))return;
  if(JSON.stringify(defs)!==JSON.stringify(c)){S.set('ptdef',defs);ptApply(defs)}}catch(e){}}
function openTopic(id){const t=(D.topics||[]).find(x=>x.id===id);if(!t)return;const G=scGroups();
 const keys=t.keys.map(k=>`<button class="tp-k" data-kgo="${esc(k.b)}|${k.c}"><b>${esc(k.ref)}</b><span>${esc(k.note)}</span><i>›</i></button>`).join('');
 const nights=t.sc.map(n=>G.find(g=>g.ev.n===n)).filter(Boolean).map(g=>`<button class="tp-sc" data-scn="${g.ev.n}"><small>Secret Church ${g.ev.n}</small><b>${esc(g.ev.title)}</b><span>David Platt · ${g.ids.length} sessions ›</span></button>`).join('');
 const list=()=>{const row=id=>tRow({i:I[id]},null);let h=t.ess.length?`<div class="jv-sec">Essential teaching</div>${t.ess.map(row).join('')}`:'';const B=t.bks||[];if(B.length>1){const k=Math.min(+(S.get('tptab',{})[t.id]||0),B.length-1),g=B[k];   /* subtopics: a switch that stays at the top while you scroll */
   h+=`<div class="tp-seg"><div class="t-sort" role="tablist" aria-label="Subtopics">${B.map((b,j)=>`<button role="tab" data-tpseg="${j}" aria-selected="${j===k}" class="${j===k?'on':''}">${esc(b.short||b.label)}<i>${b.ids.length}</i></button>`).join('')}</div><div class="tp-segl">${esc(g.label)}</div></div>${g.ids.map(row).join('')}`}
  else for(const g of B)h+=`<div class="jv-sec">${esc(g.label)}</div>${g.ids.map(row).join('')}`;
  if(t.more.length){const by={};t.more.forEach(id=>(by[I[id].who]=by[I[id].who]||[]).push(id));h+=`<div class="jv-sec">More teaching</div>`+Object.entries(by).map(([k,l])=>`<details class="tch-b"><summary>${esc(NAMES[k]||k)}<span>${l.length}</span></summary>${l.map(row).join('')}</details>`).join('')}return h};
 openListSheet(t.name,`<div class="tp-hd">${topicIc(t.id,44)}<div class="bps-t">${esc(t.name)}${t.private?LOCK_IC:''}</div></div>${t.private?'<p class="pt-note">Only on your devices</p>':''}<p class="bps-d">${esc(t.blurb)}</p><div class="jv-sec">Key Scripture</div>${keys}${nights?`<div class="jv-sec">The deep dive</div>${nights}`:''}`,list,(el,again)=>{
  el.querySelectorAll('[data-tpseg]').forEach(b=>b.onclick=()=>{const tb=S.get('tptab',{});tb[t.id]=+b.dataset.tpseg;S.set('tptab',tb);const sh=el.querySelector('.bps-sh'),y0=el.querySelector('.tp-seg').getBoundingClientRect().top;
   again();const s2=el.querySelector('.tp-seg');if(sh&&s2)sh.scrollTop+=s2.getBoundingClientRect().top-y0});
  el.querySelectorAll('[data-kgo]').forEach((b,j)=>b.onclick=()=>{const sh=el.querySelector('.bps-sh');topicPassage(t,t.keys[j],sh?sh.scrollTop:0)});el.querySelectorAll('[data-scn]').forEach(b=>b.onclick=()=>{const sh=el.querySelector('.bps-sh');topicNight(t,+b.dataset.scn,sh?sh.scrollTop:0)})})}
/* a Secret Church night, inside the topic: its sessions in order, and back to the topic where you were */
function topicNight(t,n,y){const el=$('#bps'),sh=el.querySelector('.bps-sh'),g=scGroups().find(x=>x.ev.n===n);if(!sh||!g)return;
 const paint=()=>{const heard=g.ids.filter(isDone).length;
  sh.innerHTML=`<button class="grab2" data-bpsx aria-label="Close"></button><button class="tp-back" id="tpback">‹ ${esc(t.name)}</button>
   <div class="tp-ph"><div><div class="bps-n" style="font-weight:650;letter-spacing:.14em;text-transform:uppercase;color:#7a5c16">Secret Church ${n}</div><div class="bps-t">${esc(g.ev.title)}</div><div class="bps-n">David Platt · ${g.ids.length} sessions${heard?` · ${heard} heard`:''}</div></div></div>
   <div id="tnl">${g.ids.map(id=>tRow({i:I[id]},'Platt')).join('')}</div><button class="tp-j" data-nj="1">Open in Secret Church ›</button>`;
  sh.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);
  $('#tpback').onclick=()=>{openTopic(t.id);const s2=$('#bps .bps-sh');if(s2)s2.scrollTop=y||0};
  sh.querySelector('[data-nj]').onclick=()=>openSCNight(n);
  sh.querySelectorAll('#tnl [data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();playRow(b.dataset.play,false);setTimeout(()=>{const k=sh.scrollTop;paint();sh.scrollTop=k},80)});
  sh.querySelectorAll('#tnl [data-open]').forEach(r=>r.onclick=e=>{if(e.target.closest('button'))return;playRow(r.dataset.open,true)})};
 paint();sh.scrollTop=0}
/* a key passage, read inside the topic: the verses, a play button, and back to the topic where you were */
function keyRange(k){const r=k.ref.replace(/^.*?\s(?=\d+(?::|–|$))/,'');let m;
 if((m=r.match(/^(\d+):(\d+)–(\d+):(\d+)$/)))return[[+m[1],+m[2]],[+m[3],+m[4]]];
 if((m=r.match(/^(\d+):(\d+)–(\d+)$/)))return[[+m[1],+m[2]],[+m[1],+m[3]]];
 if((m=r.match(/^(\d+):(\d+)$/)))return[[+m[1],+m[2]],[+m[1],+m[2]]];
 if((m=r.match(/^(\d+)–(\d+)$/)))return[[+m[1],1],[+m[2],999]];
 return[[k.c,1],[k.to||k.c,999]]}
function topicPassage(t,k,y){const el=$('#bps'),sh=el.querySelector('.bps-sh');if(!sh)return;const B=D.books.find(x=>x.name===k.b);if(!B)return;
 const [[c1,v1],[c2,v2]]=keyRange(k),can=hasNar(B.abbr,c1),pl=()=>NAR&&NAR.b===B&&cur===narId(B.abbr,c1)&&!audio.paused;
 sh.innerHTML=`<button class="grab2" data-bpsx aria-label="Close"></button><button class="tp-back" id="tpback">‹ ${esc(t.name)}</button>
  <div class="tp-ph"><div><div class="bps-t">${esc(k.ref)}</div><div class="bps-n">${esc(k.note)}</div></div>${can?`<button class="tp-pl" id="tppl" aria-label="Listen to ${esc(k.ref)}">${icon(pl()?'pause':'play',16,0,'#1b2440')}</button>`:''}</div>
  <div class="tp-tx" id="tptx">Loading…</div><button class="tp-j" data-kj="1">Open ${esc(k.b)} ${c1} in the Journey ›</button>`;
 sh.scrollTop=0;sh.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);
 $('#tpback').onclick=()=>{openTopic(t.id);const s2=$('#bps .bps-sh');if(s2)s2.scrollTop=y||0};
 sh.querySelector('[data-kj]').onclick=()=>goStop(k.b,c1);
 const p=$('#tppl');if(p)p.onclick=()=>{const id=narId(B.abbr,c1);if(cur===id){audio.paused?audio.play().catch(()=>{}):audio.pause()}else{JM=false;BPM=null;DEEP=null;narPlay(B,c1,v1>1?v1:null,{})}setTimeout(()=>{const q=$('#tppl');if(q)q.innerHTML=icon(pl()?'pause':'play',16,0,'#1b2440')},400)};
 loadBook(k.b).then(d=>{const box=$('#tptx');if(!box)return;let h='';
  for(let c=c1;c<=c2;c++){const vs=(d.chapters[c-1]||[]).filter(x=>(c>c1||x.v>=v1)&&(c<c2||x.v<=v2));if(c2>c1)h+=`<div class="tp-ch">${esc(k.b)} ${c}</div>`;
   h+=`<p>${vs.map(x=>`${x.h&&c2-c1+(v2-v1)>8?`</p><div class="tp-hh">${esc(x.h)}</div><p>`:''}<sup>${x.v}</sup>${esc(x.t)} `).join('')}</p>`}
  box.innerHTML=h.replace(/<p><\/p>/g,'')}).catch(()=>{const box=$('#tptx');if(box)box.textContent='The passage did not load. Check your connection.'})}
/* a book: every teaching on it from every teacher, in passage order, by chapter */
let LB={t:'all'};
function openLibBook(name){const b=D.books.find(x=>x.name===name);if(!b)return;const w=walk(),fa=firstAt();if(LB.b!==name){LB={b:name,t:'all'}}
 const all=Object.values(I).filter(i=>i.tr!=='devotional'&&!i.nar&&i.audio&&w[fa[i.id]]&&w[fa[i.id]].b===b).map(i=>({i,r:prange(i.pass,name),ov:w[fa[i.id]].c.intro}));
 const who=['Platt','PAM','Skip','Davey','Vaughan','Fearless'].filter(k=>!HIDE.includes(k)).filter(k=>all.some(x=>x.i.who===k));
 const list=()=>{const L=all.filter(x=>LB.t==='all'||x.i.who===LB.t),R=x=>x.r||{sc:0,sv:0,ec:999,ev:999};if(!L.length)return `<p class="bps-n" style="margin:16px 4px">Nothing here yet.</p>`;
  L.sort((a,z)=>(z.ov-a.ov)||(R(a).sc-R(z).sc)||(R(a).sv-R(z).sv)||(R(a).ec-R(z).ec)||((a.i.date||'')<(z.i.date||'')?-1:1));
  const g=[];L.forEach(x=>{const k=x.ov||!x.r?'The whole book':'Chapter '+x.r.sc;const l=g[g.length-1];if(l&&l.k===k)l.l.push(x);else g.push({k,l:[x]})});
  return g.map(x=>`<details class="tch-b"${g.length<=2||L.length<=12?' open':''}><summary>${esc(x.k)}<span>${x.l.length}</span></summary>${x.l.map(y=>tRow(y,null)).join('')}</details>`).join('')};
 openListSheet(name,`<div class="bps-t" style="margin:6px 4px 0">${esc(name)}</div><div class="bps-n" style="margin:2px 4px 12px">${all.length} teaching${all.length===1?'':'s'}${b.bl?' · '+esc(plainT(b.bl)).split('. ')[0]:''}</div>${who.length>1?`<div class="t-sort t-who" role="group" aria-label="Teacher">${[['all','All'],...who.map(k=>[k,k])].map(([v,l])=>`<button data-lbt="${v}" class="${LB.t===v?'on':''}" aria-pressed="${LB.t===v}">${esc(l)}</button>`).join('')}</div>`:''}`,list,(el,re)=>{
  el.querySelectorAll('[data-lbt]').forEach(x=>x.onclick=()=>{LB.t=x.dataset.lbt;el.querySelectorAll('[data-lbt]').forEach(y=>{y.classList.toggle('on',y===x);y.setAttribute('aria-pressed',y===x)});re()})})}
/* a teacher's whole collection: sort by Bible order (passage order inside each book), newest or oldest; search; full details */
let TS={k:null,sort:S.get('tsort','bible'),q:'',more:0};
const fmtDate=d=>{try{return d?new Date(d+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):''}catch(e){return d}};
/* Shuffle: a sermon you have never started, from everyone or from one teacher, of the length you like (optional) */
const SH_LEN=[['any','Any length'],['u20','Under 20 min'],['20-40','20–40 min'],['40-60','40–60 min'],['60+','1 hr+']];
function shLen(){const v=S.get('shlen','any');return SH_LEN.some(x=>x[0]===v)?v:'any'}
function shLenPick(){const v=shLen();return `<label class="sh-len"><span id="shlent">${(SH_LEN.find(x=>x[0]===v)||SH_LEN[0])[1]}</span> ▾<select id="shlen" aria-label="Shuffle length">${SH_LEN.map(([k,l])=>`<option value="${k}"${k===v?' selected':''}>${l}</option>`).join('')}</select></label>`}
function shMin(i){const d=(+i.dur||0)-(+i.s||0)-(+i.e||0);return d>0?d/60:0}
function shFits(i,len){if(len==='any')return true;const m=shMin(i);if(!m)return false;return len==='u20'?m<20:len==='20-40'?m>=20&&m<40:len==='40-60'?m>=40&&m<60:m>=60}
function shHeard(id){const p=prog[id];return !!(p&&(p.done||p.pos>0||p.heard>0))}
function shPool(k){const len=shLen();return Object.values(I).filter(i=>i.audio&&!i.nar&&i.tr!=='devotional'&&(!k||i.who===k)&&i.id!==cur&&!shHeard(i.id)&&shFits(i,len))}
function shuffle(k,btn){const pool=shPool(k);
 if(!pool.length){const t=btn&&(btn.querySelector('em')||btn),was=t&&t.textContent;if(t){t.textContent=shLen()==='any'?'You’ve heard them all':'Nothing new at this length';setTimeout(()=>{t.textContent=was},2600)}return}
 const i=pool[Math.floor(Math.random()*pool.length)];JM=false;BPM=null;PLAYSTOP=null;DEEP=null;play(i.id,{full:true})}
function tItems(k){const w=walk(),fa=firstAt();return Object.values(I).filter(i=>i.who===k&&i.tr!=='devotional'&&!i.nar&&i.audio).map(i=>{const st=w[fa[i.id]],bk=st?st.b.name:'Other teaching';return {i,bk,bi:st?D.books.indexOf(st.b):999,r:st?prange(i.pass,bk):null}})}
function tRow(x,k){const i=x.i,id=i.id,done=isDone(id),pl=cur===id&&!audio.paused,left=leftOf(id),ps=i.pass&&!/^the book of/i.test(i.pass)?shortPass(i.pass):(i.pass||'').replace(/^the book of /i,''),who=k?(i.by&&i.by!==NAMES[k]?i.by:''):teacher(i);
 return `<div class="tr2${done?' heard':''}"${i.audio?` data-open="${id}"`:''}><button class="jpb${i.audio?'':' off'}" data-play="${id}" aria-label="${pl?'Pause':'Play'} ${esc(dispTitle(i))}">${icon(pl?'pause':'play',12,0,'currentColor')}</button><div class="jw-t"><b>${esc(dispTitle(i))}</b><span>${[ps,fmtDate(i.date),left?atSpd(left)+' left':i.dur?durTxt(+i.dur):''].filter(Boolean).map(esc).join(' · ')}</span>${(sh=>who||sh?`<span class="t3">${esc([who,sh].filter(Boolean).join(' · '))}</span>`:'')(i.show&&i.show!==NAMES[k]?i.show:'')}</div>${done?'<i class="jw-ok" aria-label="heard">✓</i>':''}</div>`}
/* Search, from every tab and from the player: a passage ("John 3:16", "rom 8", "ps 23"), words in the Bible
   ("love is patient"), sermons (title, passage, teacher, show), series, topics, teachers and books. */
const SRCH_IC='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>';
const SR={q:'',ctx:null,more:{},bible:null,t:0};
const srNorm=t=>(t||'').toLowerCase().replace(/[’']/g,'').replace(/[^a-z0-9: -]+/g,' ').replace(/\s+/g,' ').trim();
function srBook(name){const A=D.alias||{},n=name.replace(/\./g,'').trim().toLowerCase();let k=A[n]||A[n.replace(/\s+/g,'')];
 if(!k&&n.replace(/\s/g,'').length>=3){const c=D.books.filter(b=>b.name.toLowerCase().replace(/\s/g,'').startsWith(n.replace(/\s/g,'')));if(c.length)k=c[0].name}
 return k?D.books.find(b=>b.name===k):null}
/* "John 3:16", "1 cor 13 4-7", "ps 23", "romans" -> {b, c, v, e} */
function srRef(q){let s=q.trim().toLowerCase().replace(/\./g,'').replace(/\s+/g,' ').replace(/^(1st|first|i) /,'1 ').replace(/^(2nd|second|ii) /,'2 ').replace(/^(3rd|third|iii) /,'3 ').replace(/\bchapter /,'').replace(/ verses? /,':');
 const m=s.match(/^([123] ?)?([a-z][a-z ]*?) ?(\d{1,3})?(?:(?: ?: ?| )(\d{1,3})(?: ?[-–] ?(\d{1,3}))?)?$/);if(!m)return null;
 const b=srBook((m[1]||'')+m[2]);if(!b)return null;const c=m[3]?+m[3]:0;if(c>b.n)return null;
 if(!c&&srNorm(b.name)!==srNorm((m[1]||'')+m[2])&&!(D.alias||{})[((m[1]||'')+m[2]).trim()])return null;   // a bare word only as a whole book name ("Romans", "rom"), not "job hunting"
 return {b,c,v:m[4]?+m[4]:0,e:m[5]?+m[5]:0}}
function srBible(){return SR.bible||(SR.bible=Promise.all(D.books.map(b=>loadBook(b.name).then(d=>[b,d]).catch(()=>[b,null]))))}
function srClose(){const el=$('#gsr');if(!el)return;el.classList.remove('on');setTimeout(()=>el.remove(),180)}
function srRecent(q){try{const r=S.get('srecent',[]).filter(x=>x!==q);r.unshift(q);S.set('srecent',r.slice(0,6))}catch(e){}}
function openSearch(){if($('#gsr'))return;SR.ctx=NAR&&cur===NAR.id&&NP().classList.contains('on')&&!NP().classList.contains('mini')?{b:NAR.b,c:NAR.c}:null;SR.more={};
 const el=document.createElement('div');el.id='gsr';el.setAttribute('role','dialog');el.setAttribute('aria-label','Search');
 el.innerHTML=`<div class="sh"><label class="sbox">${SRCH_IC}<input id="sq" type="search" enterkeyhint="search" autocomplete="off" autocorrect="off" spellcheck="false" placeholder="${SR.ctx?'Search '+esc(SR.ctx.b.name+' '+SR.ctx.c)+', the Bible, sermons':'Passage, words, sermon…'}"><button class="sx" hidden aria-label="Clear">✕</button></label><button class="scan">Cancel</button></div><div class="sr" id="sres"></div>`;
 document.body.appendChild(el);requestAnimationFrame(()=>el.classList.add('on'));
 const inp=$('#sq'),sx=el.querySelector('.sx');inp.value=SR.q;sx.hidden=!SR.q;
 const run=()=>{SR.q=inp.value;sx.hidden=!SR.q;clearTimeout(SR.t);srPaint(true);SR.t=setTimeout(()=>srPaint(false),220)};
 inp.oninput=run;sx.onclick=()=>{inp.value='';run();inp.focus()};el.querySelector('.scan').onclick=srClose;
 inp.onkeydown=e=>{if(e.key==='Escape')srClose();if(e.key==='Enter'){e.preventDefault();inp.blur();const f=el.querySelector('#sres [data-go]');if(f)f.click()}};
 srPaint(false);setTimeout(()=>{inp.focus();inp.select()},60)}
/* leave the search for a place in the app: shrink the full player first, so sheets and the Journey show */
function srLeave(){srRecent(SR.q.trim());srClose();if(NP().classList.contains('on')&&!NP().classList.contains('mini'))setMini(true)}
function srGo(kind,a,b,c){if(kind==='read'){srRecent(SR.q.trim());srClose();const bk=D.books.find(x=>x.name===a);narPlay(bk,+b,+c||null,{full:true});return}
 if(kind==='play'){srRecent(SR.q.trim());srClose();if(cur===a){setMini(false);return}JM=false;BPM=null;PLAYSTOP=null;DEEP=null;play(a,{full:true});return}
 srLeave();if(kind==='stop')goStop(a,+b||1);else if(kind==='series')openSeries(a);else if(kind==='topic')openTopic(a);else if(kind==='teacher')openTeacher(a);else if(kind==='book')openLibBook(a);else if(kind==='sc')openSCNight(+a)}
const srHi=(t,ws)=>{let h=esc(t);for(const w of ws.filter(w=>w.length>1).sort((a,b)=>b.length-a.length)){h=h.replace(new RegExp('(?![^<]*>)('+w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<mark>$1</mark>')}return h};
/* a long verse shown around its match, so the words searched for are in view */
function srSnip(t,ph,W){const L=t.toLowerCase();let k=L.indexOf(ph);if(k<0)k=Math.min(...W.map(w=>{const j=L.indexOf(w);return j<0?1e9:j}));if(k>=1e9||k<70||t.length<120)return t;const st=t.lastIndexOf(' ',k-35);return '…'+t.slice(st<0?0:st+1)}
function srRow(go,ic,title,sub,ws,cls){return `<button class="si" data-go="${esc(go)}"><span class="sk">${ic}</span><div><b>${srHi(title,ws)}</b>${sub?`<span class="${cls||''}">${srHi(sub,ws)}</span>`:''}</div><i>›</i></button>`}
function srPaint(quick){const box=$('#sres');if(!box)return;const q=SR.q.trim(),n=srNorm(q),ws=n.split(' ').filter(Boolean);let h='';
 if(!q){const r=S.get('srecent',[]);h+=SR.ctx?`<div class="sg">Reading ${esc(SR.ctx.b.name+' '+SR.ctx.c)}</div><div class="chips"><button data-q="${esc(SR.ctx.b.name+' '+SR.ctx.c)}">Teaching on this chapter</button></div>`:'';
  if(r.length)h+=`<div class="sg">Recent</div><div class="chips">${r.map(x=>`<button data-q="${esc(x)}">${esc(x)}</button>`).join('')}</div>`;
  h+=`<div class="sg">Try</div><div class="chips">${['John 3:16','Psalm 23','Romans 8','love is patient','grace','Platt Ephesians','Secret Church','prayer'].map(x=>`<button data-q="${esc(x)}">${esc(x)}</button>`).join('')}</div>`;
  box.innerHTML=h;srWire(box);return}
 const ref=srRef(q);
 if(ref){const {b,c,v,e}=ref,lab=b.name+(c?' '+c+(v?':'+v+(e?'–'+e:''):''):'');
  h+=`<div class="pc"><h3>${esc(lab)}</h3><p id="spv">${c?'…':esc((b.ch[0]&&b.ch[0].sl)||'')}</p><div class="pa">${c?`<button class="pri" data-go="read|${esc(b.name)}|${c}|${v||''}">${icon('play',12,0,'currentColor')} Read${v?' from verse '+v:''}</button>`:''}<button data-go="stop|${esc(b.name)}|${c||1}">Go to ${esc(c?b.name+' '+c:b.name)}</button><button data-go="book|${esc(b.name)}">Sermons on ${esc(b.name)}</button></div></div>`;
  const ch=c?b.ch.find(x=>x.c===c):null,ids=(ch?ch.ids:[]).filter(id=>I[id]&&I[id].audio);
  if(ids.length)h+=`<div class="sg">Teaching on ${esc(b.name+' '+c)}</div>`+ids.slice(0,8).map(id=>srRow('play|'+id,icon('play',11,0,'currentColor'),dispTitle(I[id]),[teacher(I[id]),I[id].pass&&shortPass(I[id].pass)].filter(Boolean).join(' · '),[])).join('');
  if(c)loadBook(b.name).then(d=>{const p=$('#spv');if(!p||SR.q.trim()!==q)return;const vs=(d.chapters[c-1]||[]).filter(x=>v?x.v>=v&&x.v<=(e||v):x.v<=3);p.innerHTML=vs.map(x=>`<sup>${x.v}</sup>${esc(x.t)}`).join(' ')+(!v&&(d.chapters[c-1]||[]).length>3?' …':'')}).catch(()=>{})}
 // series, topics, teachers, books by name
 const has=t=>{const x=srNorm(t);return ws.every(w=>x.includes(w))};
 const named=[];(D.bp||[]).forEach(x=>{if(has(x.title+' '+x.by))named.push(srRow('series|'+x.id,icon('star',13,1.8,'currentColor'),x.title,'Series · '+x.by,ws))});
 (D.topics||[]).forEach(x=>{if(has(x.name))named.push(srRow('topic|'+x.id,icon('star',13,1.8,'currentColor'),x.name,'Topic',ws))});
 Object.entries(NAMES).forEach(([k,v])=>{if(has(v)||has(k))named.push(srRow('teacher|'+k,`<b style="font:600 11px -apple-system,system-ui">${v.split(' ').map(w=>w[0]).join('').slice(0,2)}</b>`,v,'Teacher · all teachings',ws))});
 if(/secret|church/.test(n)&&has('secret church'))named.push(srRow('sc|1',icon('star',13,1.8,'currentColor'),'Secret Church','David Platt · all nights',ws));
 if(named.length)h+=`<div class="sg">Series, topics, teachers</div>`+named.slice(0,6).join('');
 // sermons
 const hits=[];for(const i of Object.values(I)){if(!i.audio||i.nar||i.blob||i.tr==='devotional')continue;const tt=srNorm(i.t),hay=tt+' '+srNorm((i.pass||'')+' '+teacher(i)+' '+(i.show||'')+' '+(i.by||''));
  if(!ws.every(w=>hay.includes(w)))continue;let sc=0;if(tt.includes(n))sc+=4;if(tt.startsWith(n))sc+=2;ws.forEach(w=>{if(tt.includes(w))sc+=1});hits.push([sc,i])}
 hits.sort((a,z)=>(z[0]-a[0])||((z[1].date||'')>(a[1].date||'')?1:-1));
 const words=n.replace(/[0-9:]/g,'').trim(),bibFirst=SR.ctx&&!ref&&words.length>=3;if(bibFirst)h+='<div id="sbib"></div>';
 if(hits.length){const k=SR.more.s?60:(ref?5:8);h+=`<div class="sg">Sermons · ${hits.length.toLocaleString()}</div>`+hits.slice(0,k).map(([_,i])=>srRow('play|'+i.id,icon('play',11,0,'currentColor'),dispTitle(i),[teacher(i),i.pass&&shortPass(i.pass),fmtDate(i.date)].filter(Boolean).join(' · '),ws)).join('')+(hits.length>k?`<button class="more" data-more="s">Show ${Math.min(60,hits.length)-k>0&&!SR.more.s?'more':''} sermons</button>`:'')}
 // the Bible's words (not for a bare reference)
 if(!ref&&words.length>=3){const wait=`<div class="sg">In the Bible</div><p class="none" style="margin:8px 4px">${quick?'…':'Searching the Bible…'}</p>`;h=bibFirst?h.replace('<div id="sbib"></div>',`<div id="sbib">${wait}</div>`):h+`<div id="sbib">${wait}</div>`;
  if(!quick)srBible().then(all=>{const el=$('#sbib');if(!el||SR.q.trim()!==q)return;const ph=[],aw=[];const W=words.split(' ');
   const look=(b,d,cs)=>{for(const c of cs){const vs=d.chapters[c-1]||[];for(const x of vs){const t=srNorm(x.t);if(t.includes(words))ph.push([b,c,x]);else if(W.length>1&&W.every(w=>t.includes(w)))aw.push([b,c,x])}}};
   if(SR.ctx){const d=all.find(([b])=>b.name===SR.ctx.b.name);if(d&&d[1])look(d[0],d[1],[SR.ctx.c])}const inCh=ph.length+aw.length;
   for(const [b,d] of all){if(!d)continue;look(b,d,d.chapters.map((_,k)=>k+1).filter(c=>!(SR.ctx&&b.name===SR.ctx.b.name&&c===SR.ctx.c)))}
   const L=[...ph,...aw];if(!L.length){el.innerHTML=hits.length||named.length?'':`<p class="none">Nothing found for “${esc(q)}”.</p>`;return}
   const k=SR.more.b?120:12;
   el.innerHTML=`<div class="sg">In the Bible · ${L.length.toLocaleString()} verse${L.length>1?'s':''}</div>`+L.slice(0,k).map(([b,c,x],j)=>(SR.ctx&&j===0&&inCh?`<div class="sg" style="margin-top:6px">In ${esc(SR.ctx.b.name+' '+SR.ctx.c)}</div>`:'')+(SR.ctx&&inCh&&j===inCh?`<div class="sg" style="margin-top:10px">Elsewhere</div>`:'')+srRow(`read|${b.name}|${c}|${x.v}`,icon('book',13,1.8,'currentColor'),`${b.name} ${c}:${x.v}`,srSnip(x.t,words,W),W,'vt')).join('')+(L.length>k?`<button class="more" data-more="b">Show more verses</button>`:'');srWire(el)})}
 if(!h)h=`<p class="none">Nothing found for “${esc(q)}”.</p>`;
 box.innerHTML=h;srWire(box)}
function srWire(box){box.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{const [k,a,x,y]=b.dataset.go.split('|');srGo(k,a,x,y)});
 box.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>{const i=$('#sq');i.value=b.dataset.q;i.dispatchEvent(new Event('input'))});
 box.querySelectorAll('[data-more]').forEach(b=>b.onclick=()=>{SR.more[b.dataset.more]=1;srPaint(false)})}
// tapping a sermon's row (not its play button) opens it in the full player
function wireOpen(el){el.querySelectorAll('#tlist [data-open]').forEach(r=>r.onclick=()=>{const id=r.dataset.open;if(cur===id){setMini(false);return}JM=false;BPM=null;PLAYSTOP=null;DEEP=null;play(id,{full:true})})}
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
  <div class="sh-th"><div class="bps-t" style="margin:6px 4px 0">${NAMES[k]}</div><button class="sh-tb" data-shuf="${k}" aria-label="Shuffle a sermon of ${NAMES[k]}'s you haven't heard"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg> Shuffle</button></div><div class="bps-n" style="margin:2px 4px 12px">${n.toLocaleString()} teaching${n>1?'s':''}</div>
  <div class="t-ctl"><div class="t-sort" role="group" aria-label="Sort">${[['bible','Bible order'],['newest','Newest'],['oldest','Oldest']].map(([v,l])=>`<button data-tsort="${v}" class="${TS.sort===v?'on':''}" aria-pressed="${TS.sort===v}">${l}</button>`).join('')}</div>
  <label class="t-q"><svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><input id="tq" type="search" placeholder="Search these sermons" value="${esc(TS.q)}" autocomplete="off" aria-label="Search this teacher"></label></div>
  <div id="tlist">${tList()}</div></div>`;
 el.hidden=false;document.body.classList.add('bpsopen');requestAnimationFrame(()=>el.classList.add('on'));el.querySelectorAll('[data-bpsx]').forEach(b=>b.onclick=closeSeries);
 const wireL=()=>{el.querySelectorAll('#tlist [data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();JM=false;BPM=null;PLAYSTOP=null;DEEP=null;play(b.dataset.play);setTimeout(()=>{$('#tlist').innerHTML=tList();wireL()},60)});wireOpen(el);const m=$('#tmore');if(m)m.onclick=()=>{TS.more++;$('#tlist').innerHTML=tList();wireL()}};wireL();
 el.querySelectorAll('[data-tsort]').forEach(b=>b.onclick=()=>{TS.sort=b.dataset.tsort;S.set('tsort',TS.sort);TS.more=0;el.querySelectorAll('[data-tsort]').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b)});$('#tlist').innerHTML=tList();wireL()});
 el.querySelectorAll('[data-shuf]').forEach(b=>b.onclick=()=>shuffle(b.dataset.shuf,b));
 const q=$('#tq');let tt=null;q.oninput=()=>{clearTimeout(tt);tt=setTimeout(()=>{TS.q=q.value;TS.more=0;$('#tlist').innerHTML=tList();wireL()},150)}}
function wireLib(){wireBP();document.querySelectorAll('#main [data-favs]').forEach(b=>b.onclick=openFavs);document.querySelectorAll('[data-tch]').forEach(b=>b.onclick=()=>openTeacher(b.dataset.tch));document.querySelectorAll('#main [data-shuf]').forEach(b=>b.onclick=()=>shuffle(b.dataset.shuf||null,b));const sl=$('#shlen');if(sl)sl.onchange=()=>{S.set('shlen',sl.value);const t=$('#shlent');if(t)t.textContent=(SH_LEN.find(x=>x[0]===sl.value)||SH_LEN[0])[1]};document.querySelectorAll('[data-lt]').forEach(b=>b.onclick=()=>{LT=b.dataset.lt;S.set('libtab',LT);render()});document.querySelectorAll('#main [data-topic]').forEach(b=>b.onclick=()=>openTopic(b.dataset.topic));document.querySelectorAll('[data-lbook]').forEach(b=>b.onclick=()=>openLibBook(b.dataset.lbook));document.querySelectorAll('[data-bpplay2]').forEach(b=>b.onclick=()=>bpPlay(b.dataset.sid,b.dataset.bpplay2,true));document.querySelectorAll('#main [data-full]').forEach(b=>b.onclick=e=>{e.stopPropagation();playRow(b.dataset.full,true)})}

/* Pray (pray.py): Stillness is music and a quiet landscape; Guided walks the Lord's Prayer (Matthew 6:9-13). The music
   plays on its own element: it pauses a sermon and a sermon pauses it, and it is never kept in listening history */
const PRAY=D.pray||{moves:[],music:[]};
const PR={mode:['guided','led','med'].includes(S.get('prm','still'))?S.get('prm','still'):'still',mv:0,anim:''};
const PM={el:null,k:0,ms:false,err:0,sv:0};
const PR_PLAY='<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path d="M8.5 5.6v12.8a.8.8 0 0 0 1.2.7l10-6.4a.8.8 0 0 0 0-1.4l-10-6.4a.8.8 0 0 0-1.2.7z" fill="currentColor"/></svg>',
 PR_PAUSE='<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><rect x="6.5" y="5" width="3.6" height="14" rx="1.2" fill="currentColor"/><rect x="13.9" y="5" width="3.6" height="14" rx="1.2" fill="currentColor"/></svg>',
 PR_SKIP=d=>`<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" style="transform:scaleX(${d})"><path d="M6 6.5v11l8-5.5z" fill="currentColor"/><rect x="15" y="6.5" width="2.4" height="11" rx="1" fill="currentColor"/></svg>`,
 PR_AR=d=>`<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="${d<0?'M10 3 5 8l5 5':'M6 3l5 5-5 5'}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
 PR_TURN='<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function prShuf(n){const o=[...Array(n).keys()];for(let i=n-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[o[i],o[j]]=[o[j],o[i]]}return o}
function pmEl(){if(PM.el)return PM.el;const a=PM.el=$('#praym');
 a.addEventListener('play',()=>{if(BED.tail)bedStopAfter();AUDIO_EL.forEach(b=>{if(!b.paused)b.pause()});[$('#ledm'),$('#medm'),$('#lpm')].forEach(x=>{if(x&&!x.paused)x.pause()});if(window.MED&&MED.on)medStop(false);pmSession();pmPaint()});
 a.addEventListener('pause',pmPaint);a.addEventListener('playing',()=>{PM.err=0});
 a.addEventListener('ended',()=>{if(a.src!==SILENT)pmSkip(1,true)});
 a.addEventListener('error',()=>{if(!a.getAttribute('src')||a.src===SILENT||PM.err>3)return;PM.err++;setTimeout(()=>pmSkip(1,true),900)});
 a.addEventListener('timeupdate',()=>{const n=Date.now();if(n-PM.sv>5000){PM.sv=n;S.set('pmpos',{k:PM.k,t:Math.floor(a.currentTime)})}});
 AUDIO_EL.forEach(b=>b.addEventListener('play',()=>{if(!a.paused)a.pause();if(PM.ms){PM.ms=false;if(cur)msSermon(cur)}}));
 return a}
/* Music under the reading and under every prayer: your soaking music (the same files as Pray) plays softly while Bible
   narration or a prayer plays. It is a plain audio element, like Stillness (an iPhone keeps those playing beside another
   recording, with the screen locked too; it pauses Web Audio). iPhones ignore an element's volume, so how soft it is
   goes into the file itself: each MP3 frame carries a gain the decoder applies, and lowering it (1.5 dB a step, as
   mp3gain does) makes a quieter copy without re-encoding; a WAV's samples are scaled. A gentle fade-in is put in the
   same way where it starts. Other formats (rare) go through a Web Audio gain as before. */
const BED={plv:+S.get('bedlvp',0.25)||0.25,led:S.get('bedled',true)!==false,on:!!S.get('bedon',false),lv:+S.get('bedlv',0.2)||0.2,ctx:null,g:null,el:null,unl:false,t:null,url:null,id:null,sv:0,busy:false,
 src:null,st:null,mode:'',vt:null,ours:0};
const VOLOK=(()=>{try{const a=new Audio();a.volume=0.5;return Math.abs(a.volume-0.5)<0.01}catch(e){return false}})();   /* false on an iPhone */
/* MP3: every granule's global gain, where it is in the file (bit position), which frame, and its original value */
function mp3Map(u8){let i=0;const n=u8.length;if(u8[0]===0x49&&u8[1]===0x44&&u8[2]===0x33)i=10+((u8[6]&127)<<21|(u8[7]&127)<<14|(u8[8]&127)<<7|(u8[9]&127));
 const BR1=[0,32,40,48,56,64,80,96,112,128,160,192,224,256,320],BR2=[0,8,16,24,32,40,48,56,64,80,96,112,128,144,160],SR={3:[44100,48000,32000],2:[22050,24000,16000],0:[11025,12000,8000]};
 const pos=[],frm=[],crc=[];let f=0,spf=1152,sr=44100,miss=0;
 const hdr=k=>{if(k+4>n||u8[k]!==0xFF||(u8[k+1]&0xE0)!==0xE0)return null;const ver=(u8[k+1]>>3)&3,lay=(u8[k+1]>>1)&3,bri=u8[k+2]>>4,sri=(u8[k+2]>>2)&3;
  if(ver===1||lay!==1||bri===0||bri===15||sri===3)return null;const kb=(ver===3?BR1:BR2)[bri],r=SR[ver][sri],pad=(u8[k+2]>>1)&1;
  return {ver,r,len:Math.floor((ver===3?144000:72000)*kb/r)+pad,crc:!(u8[k+1]&1),nch:(u8[k+3]>>6)===3?1:2}};
 while(i<n-4){const h=hdr(i);if(!h||(i+h.len<n-4&&!hdr(i+h.len))){i++;if(++miss>65536&&!pos.length)return null;continue}
  if(i+h.len>n)break;sr=h.r;spf=h.ver===3?1152:576;const si=(i+4+(h.crc?2:0))*8,m1=h.ver===3;
  const head=m1?9+(h.nch===1?5:3)+4*h.nch:8+(h.nch===1?1:2),slot=m1?59:63,ng=m1?2:1;
  for(let g=0;g<ng;g++)for(let c=0;c<h.nch;c++){pos.push(si+head+(g*h.nch+c)*slot+21);frm.push(f)}
  if(h.crc)crc.push([i,h.nch,m1]);f++;i+=h.len}
 if(f<20)return null;const p=Uint32Array.from(pos),o=new Uint8Array(p.length);for(let k=0;k<p.length;k++)o[k]=bits8(u8,p[k]);
 return {kind:'mp3',pos:p,frm:Uint32Array.from(frm),orig:o,crc,fps:sr/spf}}
function bits8(u8,b){const B=b>>3,s=b&7;return ((u8[B]<<8|u8[B+1])>>(8-s))&255}
function setBits8(u8,b,v){const B=b>>3,s=b&7,w=(u8[B]<<8|u8[B+1])&~(255<<(8-s))|(v<<(8-s));u8[B]=(w>>8)&255;u8[B+1]=w&255}
function crc16(u8,i,nbits){let c=0xFFFF;const add=(v,nb)=>{for(let k=nb-1;k>=0;k--){const bit=(v>>k)&1,top=(c>>15)&1;c=(c<<1)&0xFFFF;if(top^bit)c^=0x8005}};
 add(u8[i+2],8);add(u8[i+3],8);const s=(i+6)*8;for(let k=0;k<nbits;k++)add((u8[(s+k)>>3]>>(7-((s+k)&7)))&1,1);return c}
/* WAV (16-bit PCM): where the samples are */
function wavMap(u8){const dv=new DataView(u8.buffer,u8.byteOffset,u8.byteLength);if(u8.length<44||dv.getUint32(0)!==0x52494646||dv.getUint32(8)!==0x57415645)return null;
 let i=12,fmt=null;while(i+8<=u8.length){const id=dv.getUint32(i),sz=dv.getUint32(i+4,true);if(id===0x666d7420)fmt={ch:dv.getUint16(i+10,true),sr:dv.getUint32(i+12,true),bits:dv.getUint16(i+22,true),tag:dv.getUint16(i+8,true)};
  if(id===0x64617461&&fmt&&fmt.tag===1&&fmt.bits===16&&!((i+8)&1)){const n=Math.min(sz,u8.length-i-8)>>1;return {kind:'wav',off:i+8,n,orig:new Int16Array(u8.slice(i+8,i+8+n*2).buffer),sps:fmt.sr*fmt.ch}}
  i+=8+sz+(sz&1)}return null}
/* a copy of the piece, `steps` × 1.5 dB softer, fading in over 2 s from `at` seconds (null: no fade) */
function bedSoft(steps,at){const s=BED.src,u8=s.u8,m=s.map,FADE=16;
 if(m.kind==='mp3'){const f0=at==null?-1:Math.floor(at*m.fps),fn=Math.max(1,Math.round(2*m.fps));
  for(let k=0;k<m.pos.length;k++){const fr=m.frm[k];let st=steps;if(f0>=0&&fr>=f0&&fr<f0+fn)st+=Math.round(FADE*(1-(fr-f0)/fn));setBits8(u8,m.pos[k],Math.max(0,m.orig[k]-st))}
  for(const [i,nch,m1] of m.crc){const nb=m1?(nch===1?136:256):(nch===1?72:136),c=crc16(u8,i,nb);u8[i+4]=c>>8;u8[i+5]=c&255}}
 else{const pcm=new Int16Array(u8.buffer,u8.byteOffset+m.off,m.n),g=Math.pow(10,-1.5*steps/20),s0=at==null?-1:Math.floor(at*m.sps),sn=2*m.sps;
  for(let k=0;k<m.n;k++){let v=m.orig[k]*g;if(s0>=0&&k>=s0&&k<s0+sn)v*=Math.pow(10,-1.5*FADE*(1-(k-s0)/sn)/20);pcm[k]=v}}
 return new Blob([u8],{type:s.type})}
function bedSteps(v){return Math.max(0,Math.min(40,Math.round(-20*Math.log10(Math.max(0.001,v))/1.5)))}
function bedEl(){if(BED.el)return BED.el;const b=BED.el=$('#bedm');
 AUDIO_EL.forEach(x=>x.addEventListener('play',()=>{if(BED.tail){BED.tail=false;bedSync()}}));
 b.addEventListener('pause',()=>{if(Date.now()-BED.ours<300||!bedWanted()||b.src===SILENT)return;   /* not one we made (a swap or our own pause) */const n=Date.now();BED.rts=(BED.rts||[]).filter(t=>n-t<10000);
  dlog('music paused by the phone',{with:['audio','ledm','medm','lpm'].filter(i=>{const e=document.getElementById(i);return e&&!e.paused}).join(' ')||'nothing',tries:BED.rts.length});
  if(BED.rts.length>=3)return;BED.rts.push(n);   /* paused by the phone, not by us: once more */
  setTimeout(()=>{if(bedWanted()&&b.paused)bedStart()},400)});
 b.addEventListener('ended',()=>bedLoad(1).then(ok=>{if(ok&&bedWanted())bedStart(0)}));
 b.addEventListener('timeupdate',()=>{const n=Date.now();if(BED.id&&n-BED.sv>5000){BED.sv=n;S.set('bedpos',{id:BED.id,t:Math.floor(b.currentTime)})}});return b}
/* other formats only: the music through a Web Audio gain */
function bedCtx(){if(BED.ctx)return BED.ctx;const C=window.AudioContext||window.webkitAudioContext;if(!C)return null;
 try{BED.ctx=new C();const s=BED.ctx.createMediaElementSource(bedEl());BED.g=BED.ctx.createGain();BED.g.gain.value=0;s.connect(BED.g);BED.g.connect(BED.ctx.destination)}catch(e){BED.ctx=null;BED.g=null}
 try{if(navigator.audioSession)navigator.audioSession.type='playback'}catch(e){}return BED.ctx}
/* the element's own volume, where a phone honours it: only for fading in and out */
function bedVol(v,ms){const b=bedEl();clearInterval(BED.vt);if(!VOLOK)return;const v0=b.volume,n=Math.max(1,Math.round(ms/40));let k=0;
 BED.vt=setInterval(()=>{k++;try{b.volume=Math.max(0,Math.min(1,v0+(v-v0)*k/n))}catch(e){}if(k>=n)clearInterval(BED.vt)},40)}
/* set the music to `v` (0 fades it out); a different level makes a new copy, swapped in where it is */
function bedGain(v,ms){const b=bedEl();
 if(BED.mode==='wa'){const c=bedCtx();if(c&&BED.g){const t=c.currentTime,g=BED.g.gain;try{g.cancelScheduledValues(t);g.setValueAtTime(g.value,t);g.linearRampToValueAtTime(v,t+ms/1000)}catch(e){g.value=v}}return}
 if(v<=0){bedVol(0,ms);return}
 if(BED.src&&bedSteps(v)!==BED.st&&b.getAttribute('src')&&b.src!==SILENT){const t=b.currentTime,on=!b.paused;bedPut(v,null,t);if(on)b.play().catch(()=>{})}
 bedVol(1,ms)}
/* put the piece on the element at level v, fading in from `fade` (seconds) or not, at position t */
function bedPut(v,fade,t){const b=bedEl(),s=bedSteps(v);BED.st=s;const bl=bedSoft(s,fade),old=BED.url;BED.url=URL.createObjectURL(bl);BED.ours=Date.now();b.src=BED.url;
 if(t)b.addEventListener('loadedmetadata',()=>{try{b.currentTime=t}catch(e){}},{once:true});if(old)setTimeout(()=>URL.revokeObjectURL(old),3000);dlog('music level',{steps:s,dB:-1.5*s,fade:fade!=null,at:Math.round(t||0)})}
/* which piece and where: carries on from where it last stopped, track after track */
function bedLoad(step){return plLoad().then(L=>{if(!L.length)return false;const p=S.get('bedpos',null);let k=p?L.findIndex(x=>x.id===p.id):-1,t=0;
  if(step){k=(Math.max(k,0)+step)%L.length;t=0}else if(k<0)k=0;else t=p.t||0;const tr=L[k];if(!step&&BED.id===tr.id&&BED.src)return true;
  return pdbDo('blob','readonly',x=>x.objectStore('blob').get(tr.id)).then(bl=>{if(!bl)return false;return bl.arrayBuffer().then(ab=>{const u8=new Uint8Array(ab);
   let map=null;try{map=mp3Map(u8)||wavMap(u8)}catch(e){map=null}
   BED.src={u8,map,type:bl.type||'audio/mpeg',t};BED.id=tr.id;BED.st=null;S.set('bedpos',{id:tr.id,t});
   if(!map){BED.mode='wa';const b=bedEl();if(BED.url)URL.revokeObjectURL(BED.url);BED.url=URL.createObjectURL(bl);b.src=BED.url;if(t)b.addEventListener('loadedmetadata',()=>{try{b.currentTime=t}catch(e){}},{once:true})}
   else BED.mode=map.kind;dlog('music piece',{kind:BED.mode,mb:Math.round(u8.length/1e5)/10,at:t});return true})})}).catch(e=>{dlog('music load failed',String(e).slice(0,80));return false})}
/* start (or carry on) the music at its level, fading in */
function bedStart(t0){const b=bedEl(),v=bedLevel();
 if(BED.mode==='wa'){const c=bedCtx();if(c&&c.state!=='running')c.resume().catch(()=>{});b.play().then(()=>bedGain(v,1500)).catch(e=>dlog('music play refused',String(e).slice(0,60)));return}
 if(!BED.src)return;const t=t0!=null?t0:(b.getAttribute('src')&&b.src!==SILENT?b.currentTime:BED.src.t||0);
 if(VOLOK)try{b.volume=0}catch(e){}bedPut(v,t,t);if(BED.g)BED.g.gain.value=1;
 b.play().then(()=>bedVol(1,1500)).catch(e=>dlog('music play refused',String(e).slice(0,60)))}
/* how loud the music is right now (0 when it is not playing), as a gain */
function bedNow(){const b=bedEl();if(b.paused||!b.getAttribute('src')||b.src===SILENT)return 0;if(BED.mode==='wa')return BED.g?BED.g.gain.value:0;return (BED.st==null?0:Math.pow(10,-1.5*BED.st/20))*(VOLOK?b.volume:1)}
function bedNarr(){return !!(NAR&&cur===NAR.id)}
function bedOn(){return BED.on}
/* Pray (Be Led's prayers, Meditate's readings and stillness) has the music too, on its own switch (BED.led) and level (BED.plv) */
function bedPray(){return !!(BED.tail||(window.MED&&MED.on)||(window.LED&&LED.c&&LED.c.busy())||(window.LP&&LP.c&&LP.c.busy()))}
/* after a prayer's amen the music plays on, piece after piece, like Stillness — until you play something else, turn the
   music off, or pause it from the lock screen or your earbuds */
function bedOnAfter(){if(!BED.led||!(PL.list||[]).length)return;BED.tail=true;dlog('music carries on','after the amen');bedSync();
 if('mediaSession' in navigator){PM.ms=false;try{navigator.mediaSession.metadata=new MediaMetadata({title:'Prayer music',artist:'',album:'Pray'})}catch(e){}
  [['play',()=>{BED.tail=true;bedSync()}],['pause',()=>bedStopAfter()],['seekbackward',null],['seekforward',null],['previoustrack',()=>{bedLoad(-1).then(ok=>{if(ok&&bedWanted())bedStart(0)})}],['nexttrack',()=>{bedLoad(1).then(ok=>{if(ok&&bedWanted())bedStart(0)})}]].forEach(([k,f])=>{try{navigator.mediaSession.setActionHandler(k,f)}catch(e){}})}}
function bedStopAfter(){if(!BED.tail)return;BED.tail=false;dlog('music stops','');bedGain(0,900);setTimeout(()=>{if(!bedWanted()){BED.ours=Date.now();bedEl().pause()}},950)}
/* how loud the music is: your level; under a prayer, moved by how loud that pastor's recording is, so it sits the same
   under every one */
function bedVoice(){const lu=window.LP&&LP.c&&LP.c.busy()?(lpD()||{}).lu:window.MED&&MED.on?(medCur()||{}).lu:window.LED&&LED.id?(ledById(LED.id)||{}).lu:null;
 return lu==null||PRAY.lum==null?1:Math.max(0.25,Math.min(1.6,Math.pow(10,(lu-PRAY.lum)/20)))}
function bedLevel(){return bedPray()?BED.plv*bedVoice():BED.lv}
function bedWanted(){if(window.MED&&MED.on)return BED.led&&MED.step!=='load'&&!MED.paused;if(BED.tail)return BED.led;if(window.LED&&LED.c&&LED.c.busy())return BED.led;if(window.LP&&LP.c&&LP.c.busy())return BED.led;return bedOn()&&bedNarr()&&!audio.paused}
function bedSync(){const b=bedEl();{const w=bedWanted(),k=w+'|'+BED.mode+'|'+(b.getAttribute('src')||'').slice(0,5)+'|'+b.paused;if(DIAG.last.bed!==k){DIAG.last.bed=k;dlog('music',{wanted:w,kind:BED.mode||'none',file:(b.getAttribute('src')||'none').slice(0,5),paused:b.paused,on:BED.led,pieces:(PL.list||[]).length})}}$('#bedb').hidden=!bedNarr();$('#bedb').classList.toggle('on',bedOn());
 if(bedWanted()){clearTimeout(BED.t);
  if(!BED.src){if(BED.busy)return;BED.busy=true;bedLoad(0).then(ok=>{BED.busy=false;if(ok&&bedWanted())bedStart()});return}
  if(b.paused||b.src===SILENT)bedStart();else bedGain(bedLevel(),1500);return}
 clearTimeout(BED.t);BED.t=setTimeout(()=>{if(bedWanted())return;bedGain(0,700);setTimeout(()=>{if(!bedWanted()){BED.ours=Date.now();b.pause()}},750)},2500)}
/* iPhones only start a sound from a tap: a prayer or reading was tapped, so the music's player is readied in that tap */
function bedKick(){dlog('music kick',{on:BED.led,pieces:(PL.list||[]).length,kind:BED.mode||'none'});if(!BED.led||!(PL.list||[]).length)return;const b=bedEl();
 if(BED.mode==='wa'){const c=bedCtx();if(c&&c.state!=='running')c.resume().catch(()=>{})}
 if(b.paused&&(!b.getAttribute('src')||b.src===SILENT)){b.src=SILENT;b.play().catch(()=>{})}}
function bedUnlock(){const c0=BED.ctx;if(c0&&c0.state!=='running')c0.resume().catch(()=>{});if(!(BED.on||BED.led)||BED.unl)return;BED.unl=true;const b=bedEl();
 if(!b.getAttribute('src')){b.src=SILENT;b.play().then(()=>{if(!bedWanted()){BED.ours=Date.now();b.pause()}}).catch(()=>{BED.unl=false})}}
['touchend','click'].forEach(ev=>document.addEventListener(ev,bedUnlock,true));
function bedPop(){const p=$('#bedpop');if(!p.hidden){p.hidden=true;return}
 plLoad().then(L=>{const have=L.length>0,pc=Math.round(BED.lv*100);
  const ld=false;p.innerHTML=`<label class="bp-row"><span><b>Soaking music under the ${ld?'prayer':'reading'}</b><small>${have?esc((L[0].a||'Your music')+' · plays softly behind '+(ld?'the prayer':'the narration')):'Your music is not on this phone yet'}</small></span><input type="checkbox" id="bedon"${bedOn()?' checked':''}${have?'':' disabled'}></label>`+
   (have?`<input type="range" id="bedlv" min="3" max="60" step="1" value="${pc}" aria-label="Music level"><div class="bp-l"><span>Softer</span><span id="bedpc">Music level ${pc}%</span><span>Louder</span></div>`:`<button id="bedget">Get it in Pray</button>`);
  p.hidden=false;const on=$('#bedon');if(on)on.onchange=()=>{if(ld){BED.led=on.checked;S.set('bedled',BED.led)}else{BED.on=on.checked;S.set('bedon',BED.on)}BED.unl=false;bedUnlock();bedSync()};
  const lv=$('#bedlv');if(lv){lv.oninput=()=>{BED.lv=+lv.value/100;S.set('bedlv',BED.lv);$('#bedpc').textContent='Music level '+lv.value+'%';if(bedWanted()&&BED.mode==='wa')bedGain(BED.lv,150)};lv.onchange=()=>{if(bedWanted())bedGain(bedLevel(),150)}}
  const gt=$('#bedget');if(gt)gt.onclick=()=>{p.hidden=true;setMini(true);const t=document.querySelector('#tabs [data-tab2=pray]');if(t)t.click()}})}
/* the music lives on this phone: albums you bought (MP3s, or the store's ZIP), kept in IndexedDB, never uploaded */
const PDB={db:null};
function pdb(){return PDB.db||(PDB.db=new Promise((ok,no)=>{const r=indexedDB.open('sc-pray',1);r.onupgradeneeded=()=>{const d=r.result;d.createObjectStore('meta',{keyPath:'id'});d.createObjectStore('blob')};r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)}))}
function pdbDo(st,mode,f){return pdb().then(d=>new Promise((ok,no)=>{const t=d.transaction(st,mode),q=f(t);t.oncomplete=()=>ok(q&&q.result);t.onerror=()=>no(t.error);t.onabort=()=>no(t.error)}))}
const PL={list:null,url:null};
function plSort(a,b){return (a.al||'').localeCompare(b.al||'')||(a.n||1e4)-(b.n||1e4)||a.f.localeCompare(b.f,undefined,{numeric:true})}
function plLoad(){if(PL.list)return Promise.resolve(PL.list);return pdbDo('meta','readonly',t=>t.objectStore('meta').getAll()).then(r=>{PL.list=(r||[]).sort(plSort);return PL.list}).catch(()=>{PL.list=[];return PL.list})}
function pmTrack(){return (PL.list||[])[PM.k]}
function pmLoad(k,t){const a=pmEl(),L=PL.list||[],n=L.length;if(!n)return Promise.resolve();PM.k=((k%n)+n)%n;const tr=L[PM.k];
 return pdbDo('blob','readonly',x=>x.objectStore('blob').get(tr.id)).then(bl=>{if(!bl)return;if(PL.url)URL.revokeObjectURL(PL.url);PL.url=URL.createObjectURL(bl);a.src=PL.url;PM.cur=tr.id;
  if(t)a.addEventListener('loadedmetadata',()=>{try{a.currentTime=t}catch(e){}},{once:true})})}
/* iPhones start sound only straight from a tap, so the piece is made ready before the tap */
function pmPrime(){return plLoad().then(L=>{if(!L.length||PM.cur&&L.some(x=>x.id===PM.cur))return;const p=S.get('pmpos',null),k=p?Math.max(0,L.findIndex(x=>x.id===p.id)):0;return pmLoad(k,p&&L[k]&&L[k].id===p.id?p.t:0)})}
function pmToggle(){const a=pmEl();if(!(PL.list||[]).length){mbSync(true);return}if(!a.getAttribute('src')||a.src===SILENT){a.src=SILENT;a.play().catch(()=>{});PM.cur=null;pmPrime().then(()=>a.play().catch(()=>{}));return}if(a.paused)a.play().catch(()=>{});else a.pause()}
function pmSkip(d,auto){const a=pmEl();if(!(PL.list||[]).length)return;const on=auto||!a.paused;pmLoad(PM.k+d,0).then(()=>{S.set('pmpos',{id:PM.cur,t:0});if(on)a.play().catch(()=>{});else pmPaint()})}
function pmSession(){if(!('mediaSession' in navigator))return;const t=pmTrack()||{},a=pmEl();PM.ms=true;try{navigator.mediaSession.metadata=new MediaMetadata({title:t.t||'Prayer music',artist:t.a||'',album:t.al||'Pray'})}catch(e){}
 [['play',()=>a.play().catch(()=>{})],['pause',()=>a.pause()],['nexttrack',()=>pmSkip(1)],['previoustrack',()=>pmSkip(-1)],['seekbackward',null],['seekforward',null]].forEach(([k,f])=>{try{navigator.mediaSession.setActionHandler(k,f)}catch(e){}})}
function pmPaint(){const on=!!PM.el&&!PM.el.paused;document.querySelectorAll('[data-pm]').forEach(b=>{b.innerHTML=on?PR_PAUSE:PR_PLAY;b.setAttribute('aria-label',on?'Pause the music':'Play the music')})}
function prCredits(){return ''}
/* the prayer music is also kept in your private backup repo (music/<piece>/<part>, 12 MB parts, and music/index.json),
   so a new or replaced phone gets it back on its own once the backup key is in */
const MB={busy:false,msg:'',last:0},MB_PART=2*1048576;   /* GitHub ends any API request after 10 s: small parts finish in time on slow Wi‑Fi */
const mbWait=ms=>new Promise(r=>setTimeout(r,ms));
function b64blob(bl){return new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(r.error);r.readAsDataURL(bl)})}
async function mbIndex(){const r=await bkGH('/contents/music/index.json');if(r.status===404)return {sha:null,list:[]};if(!r.ok)throw r.status;const j=await r.json();let c=j.content;
 if(!c||j.encoding!=='base64'){const r2=await bkGH('/git/blobs/'+j.sha);if(!r2.ok)throw r2.status;c=(await r2.json()).content}return {sha:j.sha,list:JSON.parse(bkUn64(c))}}
async function mbPutIndex(list,sha){const body={message:'Prayer music list',content:bkB64(JSON.stringify(list))};if(sha)body.sha=sha;let r=await bkGH('/contents/music/index.json',{method:'PUT',body:JSON.stringify(body)});
 if(r.status===409||r.status===422){const cur=await mbIndex();if(cur.sha)body.sha=cur.sha;r=await bkGH('/contents/music/index.json',{method:'PUT',body:JSON.stringify(body)})}if(!r.ok)throw r.status;return (await r.json()).content.sha}
async function mbPut(path,b64,msg){const body={message:msg,content:b64};let r=await bkGH('/contents/'+path,{method:'PUT',body:JSON.stringify(body)});
 if(r.status===422||r.status===409){const g=await bkGH('/contents/'+path);if(g.ok){body.sha=(await g.json()).sha;r=await bkGH('/contents/'+path,{method:'PUT',body:JSON.stringify(body)})}}if(!r.ok)throw r.status}
function mbSay(m){MB.msg=m;document.querySelectorAll('[data-mbst]').forEach(e=>e.textContent=m)}
const mbKey=x=>x.f+'|'+x.sz;
async function mbSync(force){if(!bkOn()||MB.busy||(!force&&Date.now()-MB.last<10*60e3))return;MB.busy=true;MB.last=Date.now();try{
  let L=await plLoad(),{sha,list}=await mbIndex();
  const here=new Set(L.map(mbKey)),miss=list.filter(x=>!here.has(mbKey(x)));
  if(miss.length)try{if(navigator.storage&&navigator.storage.persist)navigator.storage.persist()}catch(e){}
  const tot=miss.reduce((a,x)=>a+x.parts,0);let done=0;if(tot)mbSay('Bringing your prayer music onto this phone… 0%');
  for(const [k,x] of miss.entries()){const pk=i=>x.id+'#'+x.parts+'#'+i,parts=[];
   for(let i=0;i<x.parts;i++){   /* each part is kept as it arrives, so an interrupted download carries on where it stopped */
    let got=await pdbDo('blob','readonly',t=>t.objectStore('blob').get(pk(i))).catch(()=>null);
    for(let tr=0;!got;tr++){try{const r=await bkGH('/contents/music/'+x.id+'/'+i,{accept:'raw'});if(!r.ok){if(r.status===401||r.status===403||r.status===404||tr>=4)throw r.status;await mbWait(1500*(tr+1));continue}got=await r.blob()}
     catch(e){if(typeof e==='number')throw e;if(tr>=4)throw 'net';await mbWait(1500*(tr+1))}}
    if(!got.size)throw 'net';
    try{await pdbDo('blob','readwrite',t=>t.objectStore('blob').put(got,pk(i)))}catch(e){throw 'space'}
    parts.push(got);done++;mbSay(`Bringing your prayer music onto this phone… ${Math.round(done/tot*100)}%`)}
   const bl=new Blob(parts,{type:x.ty||'audio/mpeg'}),meta={id:x.id,f:x.f,sz:x.sz,t:x.t,a:x.a,al:x.al,n:x.n};
   if(bl.size!==x.sz)throw 'size';
   try{await pdbDo(['meta','blob'],'readwrite',t=>{const st=t.objectStore('blob');st.put(bl,x.id);for(let i=0;i<x.parts;i++)st.delete(pk(i));return t.objectStore('meta').put(meta)})}catch(e){throw 'space'}}
  if(miss.length){PL.list=null;L=await plLoad();if(view==='pray'||view==='settings'){const y=scrollY;render();window.scrollTo(0,y)}}
  const there=new Set(list.map(mbKey)),up=L.filter(x=>!there.has(mbKey(x)));
  for(const [k,x] of up.entries()){mbSay(`Backing up your prayer music: ${k+1} of ${up.length}…`);const bl=await pdbDo('blob','readonly',t=>t.objectStore('blob').get(x.id));if(!bl)continue;
   const n=Math.max(1,Math.ceil(bl.size/MB_PART));
   for(let i=0;i<n;i++){const b64=await b64blob(bl.slice(i*MB_PART,(i+1)*MB_PART));for(let tr=0;;tr++){try{await mbPut('music/'+x.id+'/'+i,b64,'Prayer music: '+(x.t||x.f)+(n>1?` (${i+1}/${n})`:''));break}catch(e){if(e===401||e===403||tr>=4)throw typeof e==='number'?e:'net';await mbWait(2000*(tr+1))}}}
   list.push({id:x.id,f:x.f,sz:x.sz,t:x.t,a:x.a,al:x.al,n:x.n,ty:bl.type,parts:n});sha=await mbPutIndex(list,sha)}
  mbSay(list.length?`Backed up to your private repo, so it comes back on a new phone.`:'No prayer music in your backup yet.');S.set('mbok',list.length)}
 catch(e){mbSay(e===401||e===403?'GitHub no longer accepts your backup key: paste a new one in ⋯ → Backup.':e===404?'Your backup repo was not found.':e==='space'?'Your phone is out of room for the music: free up some space, then tap ▶.':e==='net'||e instanceof TypeError?'The connection dropped. Tap ▶ to carry on from where it stopped.':e==='size'?'The music arrived incomplete. Tap ▶ to try again.':`Your backup said ${e}: tap ▶ to try again.`);MB.last=0}
 finally{MB.busy=false}}
async function mbRemoveAll(){if(!bkOn())return;const {sha,list}=await mbIndex();for(const x of list){const r=await bkGH('/contents/music/'+x.id);if(!r.ok)continue;for(const f of await r.json())await bkGH('/contents/'+f.path,{method:'DELETE',body:JSON.stringify({message:'Remove prayer music',sha:f.sha})})}
 if(sha)await mbPutIndex([],sha);S.set('mbok',0);mbSay('')}
setTimeout(()=>mbSync(),6000);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')mbSync()});

/* reading what you picked: ZIPs opened here (stored or deflated entries), and each MP3's own title, artist, album, track */
const AUD_RE=/\.(mp3|m4a|aac|flac|wav|ogg|opus|aif|aiff)$/i,AUD_T={mp3:'audio/mpeg',m4a:'audio/mp4',aac:'audio/aac',flac:'audio/flac',wav:'audio/wav',ogg:'audio/ogg',opus:'audio/ogg',aif:'audio/aiff',aiff:'audio/aiff'};
async function unzip(f){const u8=async(a,b)=>new Uint8Array(await f.slice(a,b).arrayBuffer()),dv=x=>new DataView(x.buffer,x.byteOffset,x.byteLength);
 const tl=Math.min(f.size,66000),t=await u8(f.size-tl,f.size);let e=-1;for(let i=t.length-22;i>=0;i--)if(t[i]===0x50&&t[i+1]===0x4b&&t[i+2]===5&&t[i+3]===6){e=i;break}if(e<0)throw new Error('not a zip');
 const E=dv(t.subarray(e)),cnt=E.getUint16(10,true),cs=E.getUint32(12,true),co=E.getUint32(16,true),cd=await u8(co,co+cs),D=dv(cd),out=[];let p=0;
 for(let k=0;k<cnt&&p+46<=cd.length;k++){if(D.getUint32(p,true)!==0x02014b50)break;const m=D.getUint16(p+10,true),csz=D.getUint32(p+20,true),nl=D.getUint16(p+28,true),xl=D.getUint16(p+30,true),cl=D.getUint16(p+32,true),lo=D.getUint32(p+42,true),
  name=new TextDecoder().decode(cd.subarray(p+46,p+46+nl));p+=46+nl+xl+cl;const base=name.split('/').pop();if(!AUD_RE.test(base)||/^\._|__MACOSX/.test(name))continue;
  const L=dv(await u8(lo,lo+30)),st=lo+30+L.getUint16(26,true)+L.getUint16(28,true),ext=base.split('.').pop().toLowerCase(),raw=f.slice(st,st+csz);
  let bl;if(m===0)bl=new Blob([raw],{type:AUD_T[ext]});else if(m===8)bl=new Blob([await new Response(raw.stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer()],{type:AUD_T[ext]});else continue;
  out.push({f:name,bl})}
 return out}
async function id3(bl){const h=new Uint8Array(await bl.slice(0,10).arrayBuffer()),r={};if(h[0]!==73||h[1]!==68||h[2]!==51)return r;const v=h[3],sz=(h[6]<<21)|(h[7]<<14)|(h[8]<<7)|h[9],b=new Uint8Array(await bl.slice(10,10+Math.min(sz,600000)).arrayBuffer());let p=0;
 const dec=x=>{const e=x[0],y=x.subarray(1);try{return (e===1||e===2?new TextDecoder(e===2?'utf-16be':'utf-16'):new TextDecoder(e===3?'utf-8':'latin1')).decode(y).replace(/\u0000/g,'').trim()}catch(_){return ''}};
 while(p+10<b.length){const id=String.fromCharCode(b[p],b[p+1],b[p+2],b[p+3]);if(!/^[A-Z0-9]{4}$/.test(id))break;const fs=v===4?(b[p+4]<<21)|(b[p+5]<<14)|(b[p+6]<<7)|b[p+7]:((b[p+4]<<24)>>>0)+(b[p+5]<<16)+(b[p+6]<<8)+b[p+7];
  const d=b.subarray(p+10,p+10+fs);if(id==='TIT2')r.t=dec(d);else if(id==='TPE1')r.a=dec(d);else if(id==='TALB')r.al=dec(d);else if(id==='TRCK')r.n=parseInt(dec(d))||undefined;p+=10+fs}return r}
async function prImport(files,say){const got=[];for(const f of files){if(/\.zip$/i.test(f.name)||f.type==='application/zip'){say(`Opening ${f.name}…`);try{(await unzip(f)).forEach(x=>got.push(x))}catch(e){}}else if(AUD_RE.test(f.name)||/^audio\//.test(f.type))got.push({f:f.name,bl:f})}
 if(!got.length){say('No music found in what you picked.');return 0}
 try{if(navigator.storage&&navigator.storage.persist)navigator.storage.persist()}catch(e){}
 const have=new Set((await plLoad()).map(x=>x.f+'|'+x.sz));let n=0;
 for(const [k,x] of got.entries()){say(`Adding ${k+1} of ${got.length}…`);if(have.has(x.f.split('/').pop()+'|'+x.bl.size))continue;const tg=/\.mp3$/i.test(x.f)?await id3(x.bl):{},base=x.f.split('/').pop(),id='m'+Date.now().toString(36)+k+Math.random().toString(36).slice(2,6);
  const meta={id,f:base,sz:x.bl.size,t:tg.t||base.replace(AUD_RE,'').replace(/^\d+[\s._-]+/,'').replace(/_/g,' '),a:tg.a||'',al:tg.al||'',n:tg.n};
  await pdbDo(['meta','blob'],'readwrite',t=>{t.objectStore('blob').put(x.bl,id);return t.objectStore('meta').put(meta)});n++}
 PL.list=null;await plLoad();return n}
function prPick(after){const i=document.createElement('input');i.type='file';i.multiple=true;i.accept='.mp3,.m4a,.aac,.flac,.wav,.zip';i.style.display='none';document.body.appendChild(i);
 i.onchange=async()=>{const fs=[...i.files];i.remove();if(!fs.length)return;const say=m=>{document.querySelectorAll('[data-prsay]').forEach(e=>{e.textContent=m;e.hidden=false})};
  try{const n=await prImport(fs,say);say(n?`Added ${n} piece${n>1?'s':''}.`:'Those were already here.');if(n)setTimeout(()=>mbSync(true),800)}catch(e){say('That did not work — your phone may be out of space.')}setTimeout(()=>after&&after(),700)};i.click()}
function prRemoveAll(){const a=pmEl();a.pause();a.removeAttribute('src');a.load();if(PL.url)URL.revokeObjectURL(PL.url);PL.url=null;PM.cur=null;S.set('pmpos',null);return pdbDo(['meta','blob'],'readwrite',t=>{t.objectStore('meta').clear();t.objectStore('blob').clear()}).then(()=>{PL.list=[]})}
function prMusicNote(){const L=PL.list||[],mb=Math.round(L.reduce((a,x)=>a+(x.sz||0),0)/1048576),al=[...new Set(L.map(x=>x.al).filter(Boolean))];
 return `<h2 class="serif" style="margin:22px 0 8px">Prayer music</h2><p class="note">${L.length?`${L.length} piece${L.length>1?'s':''}${al.length?' from '+esc(al.slice(0,3).join(', '))+(al.length>3?'…':''):''}, kept on this phone (${mb.toLocaleString()} MB).`:(bkOn()?'Not on this phone yet: it comes from your backup the next time the app is open on Wi‑Fi.':'Turn on Backup below; your prayer music comes from there.')}</p>${L.length?`<p class="note" data-mbst>${bkOn()?esc(MB.msg||(S.get('mbok',0)?'Backed up to your private repo, so it comes back on a new phone.':'Backing up to your private repo…')):'<b>Not backed up yet.</b> Turn on Backup below so this music comes back on a new or replaced phone.'}</p>`:''}`}
/* a new time of prayer (half an hour since the last) brings the next supporting passage for each movement */
function prSession(){const last=S.get('prlast',0);if(Date.now()-last>30*60e3){const st=S.get('prsup',{});PRAY.moves.forEach(m=>{const n=m.sup.length;let x=st[m.k];if(!x||!Array.isArray(x.o)||x.o.length!==n)x={o:prShuf(n),p:0};else if(++x.p>=n)x={o:prShuf(n),p:0};st[m.k]=x});S.set('prsup',st);PR.mv=0}S.set('prlast',Date.now())}
function prSup(m){const x=S.get('prsup',{})[m.k],n=m.sup.length;return m.sup[x&&Array.isArray(x.o)&&x.o.length===n?x.o[x.p%n]:0]}
function prAnother(m){const st=S.get('prsup',{});let x=st[m.k];if(!x||!Array.isArray(x.o)||x.o.length!==m.sup.length)x={o:prShuf(m.sup.length),p:0};else if(++x.p>=m.sup.length)x={o:prShuf(m.sup.length),p:0};st[m.k]=x;S.set('prsup',st);S.set('prlast',Date.now())}
function prayArt(id,band){return `<svg viewBox="${band?'0 214 390 196':'0 0 390 520'}" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs>
<linearGradient id="${id}s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c3cedb"/><stop offset=".38" stop-color="#e3dccd"/><stop offset=".56" stop-color="#f5e5c6"/><stop offset=".64" stop-color="#f7ead0"/></linearGradient>
<radialGradient id="${id}g" cx=".6" cy=".52" r=".42"><stop offset="0" stop-color="#fffaf0"/><stop offset=".25" stop-color="#fdf1d8" stop-opacity=".9"/><stop offset="1" stop-color="#fdf1d8" stop-opacity="0"/></radialGradient>
<linearGradient id="${id}m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbf4e6" stop-opacity="0"/><stop offset=".5" stop-color="#fbf4e6" stop-opacity=".8"/><stop offset="1" stop-color="#fbf4e6" stop-opacity="0"/></linearGradient>
<linearGradient id="${id}f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#46536f"/><stop offset="1" stop-color="#25304a"/></linearGradient>
<filter id="${id}b" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="7"/></filter></defs>
<rect width="390" height="520" fill="url(#${id}s)"/><rect width="390" height="520" fill="url(#${id}g)"/><circle cx="234" cy="270" r="14" fill="#fffbf2" opacity=".95"/>
<g class="pr-drift" filter="url(#${id}b)" opacity=".75"><ellipse cx="96" cy="150" rx="86" ry="11" fill="#fbf5ea"/><ellipse cx="300" cy="196" rx="104" ry="12" fill="#fbf3e4"/><ellipse cx="190" cy="236" rx="70" ry="8" fill="#fdf6e8"/></g>
<path d="M0 318 C22 309 34 300 50 299 C68 298 76 309 96 306 C116 303 124 289 142 288 C160 287 168 300 188 297 C206 294 214 283 232 283 C250 283 258 297 278 295 C296 293 304 285 320 286 C340 287 352 299 372 296 C380 295 386 293 390 292 V520 H0Z" fill="#aeb6c4" opacity=".7"/>
<rect class="pr-mist" x="0" y="300" width="390" height="46" fill="url(#${id}m)"/>
<path d="M0 340 C40 330 70 322 104 328 C140 334 166 314 206 318 C248 322 270 334 308 328 C342 323 366 330 390 326 V520 H0Z" fill="#8792a8" opacity=".85"/>
<rect class="pr-mist" x="0" y="334" width="390" height="40" fill="url(#${id}m)" opacity=".7"/>
<path d="M0 372 C54 358 96 360 140 368 C190 377 222 356 270 360 C318 364 350 376 390 368 V520 H0Z" fill="#5f6b86"/>
<path d="M0 404 C70 390 120 396 176 404 C236 413 280 398 330 400 C356 401 374 405 390 408 V520 H0Z" fill="url(#${id}f)"/>
<path d="M0 446 C90 434 170 440 240 448 C300 455 350 446 390 442 V520 H0Z" fill="#1f2840" opacity=".9"/></svg>`}
/* One stretch of a recording, played on its own element (Be Led's prayers, Meditate's readings). It opens the file at
   the stretch's start (a time fragment: nothing before it is heard, and never muted), stops exactly at its end (a timer
   from the time left, not only the coarse timeupdate an iPhone sends four times a second), and does not get stuck:
   "Loading…" after 3 s of waiting, one retry after 12 s or on an error, then an error the screen can say. */
/* A recording's times are its true times (counted frame by frame). Some files' headers understate their length (Skip
   Heitzig's: 3529 s for 3546 s); a phone that trusts the header measures on that shorter scale, one that counts frames
   on the true one. Once the file opens, its length on this phone says which, and every time is put on that scale. */
function tscale(d,Lt){return Lt&&isFinite(d)&&d>0&&Math.abs(d-Lt)>0.3?d/Lt:1}
function clipper(a,h){const c={a,t0:0,end:0,url:'',rate:1,tm:null,wd:null,ld:null,tries:0,state:'',fix:null,r:1,endT:null,aE:null,aT:null};
 const st=s=>{if(c.state===s)return;c.state=s;if(h.state)h.state(s)},clr=()=>{clearTimeout(c.tm);clearTimeout(c.wd);clearTimeout(c.ld)};
 c.arm=()=>{clearTimeout(c.tm);if(!c.end||a.paused)return;const left=(c.end-a.currentTime)/(a.playbackRate||1);if(left<=0.03){c.fin();return}
  c.tm=setTimeout(()=>{if(!a.paused&&a.currentTime>=c.end-0.06)c.fin();else c.arm()},Math.max(15,left*1000-20))};
 /* a file whose length is misreported: the engine finds a time by that length (true × r), but once it plays its clock runs
    at true speed — so the end is where it is now plus the true time still to go (re-anchored at every jump) */
 c.anchor=()=>{if(c.endT==null)return;const t=a.currentTime;c.aE=t;c.aT=t/(c.r||1);c.end=t+(c.endT-c.aT);c.arm()};
 c.trueAt=t=>c.aE==null?t/(c.r||1):c.aT+(t-c.aE);
 c.fin=(why)=>{clr();if(c.state==='ended')return;c.stopAt=a.currentTime;dlog((a.id||'clip')+' stopped',{at:Math.round(a.currentTime*100)/100,end:Math.round(c.end*100)/100,why:why||'end reached',true_at:c.endT!=null?Math.round(c.trueAt(a.currentTime)*100)/100:undefined,r:c.r!==1?Math.round(c.r*1e5)/1e5:undefined});st('ended');a.pause();if(h.end)h.end()};
 c.watch=()=>{clearTimeout(c.wd);clearTimeout(c.ld);c.prog=Date.now();c.ld=setTimeout(()=>{if(c.state==='starting')st('loading')},3000);
  const chk=()=>{if(c.state!=='starting'&&c.state!=='loading')return;if(Date.now()-c.prog>25000){c.retry();return}c.wd=setTimeout(chk,2500)};c.wd=setTimeout(chk,2500)};   /* a retry only when nothing has arrived for 25 s */
 c.retry=()=>{if(c.tries>=1){c.err();return}c.tries++;c.chk=true;a.removeAttribute('src');try{a.load()}catch(e){}a.src=c.url;c.speed();a.play().catch(()=>{});c.watch()};
 c.err=()=>{clr();try{a.pause()}catch(e){}st('error');if(h.error)h.error()};
 c.speed=()=>{try{a.defaultPlaybackRate=c.rate;a.playbackRate=c.rate}catch(e){}};
 a.addEventListener('playing',()=>{clearTimeout(c.wd);clearTimeout(c.ld);c.tries=0;if(c.endT!=null&&c.aE==null)c.anchor();st('playing');c.arm()});
 ['progress','loadedmetadata','loadeddata','canplay','seeked'].forEach(e=>a.addEventListener(e,()=>{c.prog=Date.now()}));   /* bytes are arriving */
 a.addEventListener('waiting',()=>{if(c.state==='starting')return;clearTimeout(c.ld);c.ld=setTimeout(()=>{if(!a.paused&&a.readyState<3&&c.state==='playing')st('loading')},3000)});   /* while starting, the start's own 3 s timer says Loading… */
 a.addEventListener('pause',()=>{clearTimeout(c.tm);clearTimeout(c.ld);if(c.state==='playing'||c.state==='loading')st('paused')});
 a.addEventListener('seeked',()=>{if(c.endT!=null)c.anchor();else c.arm()});a.addEventListener('ratechange',()=>c.arm());
 a.addEventListener('durationchange',()=>{if(c.fix&&c.url&&isFinite(a.duration)&&a.duration>0){const e=c.end;c.fix(a.duration);if(c.endT!=null&&c.aE!=null)c.end=e}});   /* a revised length changes later jumps only */
 a.addEventListener('timeupdate',()=>{if(c.chk&&!a.paused&&a.currentTime>0){c.chk=false;if(a.currentTime<c.t0-0.5||a.currentTime>c.t0+3){try{a.currentTime=c.t0}catch(e){}return}}   /* an engine that ignored the time fragment: put it right once it plays */
  if(c.end&&!a.paused&&a.currentTime>=c.end-0.03)c.fin();else if(h.tick)h.tick()});
 a.addEventListener('ended',()=>c.fin('the file ended'));
 a.addEventListener('error',()=>{if(!a.getAttribute('src')||c.state===''||c.state==='ended')return;c.retry()});
 a.addEventListener('loadedmetadata',()=>{if(c.fix)c.fix(a.duration);if(Math.abs(a.currentTime-c.t0)>0.15)try{a.currentTime=c.t0}catch(e){}else if(c.endT!=null)c.anchor()});
 /* get the file ready while the screen shows it (a phone may wait for the tap anyway) */
 c.prep=(url,t0)=>{if(!a.paused||c.state==='starting')return;const u=url+'#t='+Math.max(0,t0).toFixed(2);if(a.getAttribute('src')===u)return;c.url=u;c.t0=t0;a.preload='metadata';a.src=u};
 /* start the stretch from its first word: call it straight from the tap */
 c.go=(url,t0,end,fix,endT)=>{clr();c.t0=Math.max(0,t0);c.end=end;c.fix=fix||null;c.tries=0;c.chk=true;c.r=1;c.endT=endT==null?null:endT;c.aE=null;c.aT=null;const u=url+'#t='+c.t0.toFixed(2);
  if(a.getAttribute('src')!==u){c.url=u;a.src=u}else{c.url=u;try{a.currentTime=c.t0}catch(e){}}c.speed();st('starting');a.play().catch(()=>{});c.watch()};
 c.again=()=>{clr();c.chk=true;try{a.currentTime=c.t0}catch(e){}c.speed();st('starting');a.play().catch(()=>{});c.watch()};
 c.resume=()=>{if(!a.getAttribute('src'))return;if(a.currentTime<c.t0-0.5||a.currentTime>=c.end-0.05)try{a.currentTime=c.t0}catch(e){}st('starting');a.play().catch(()=>{});c.watch()};
 c.pause=()=>{clr();a.pause();st('paused')};
 c.seek=d=>{if(!a.getAttribute('src'))return;try{a.currentTime=Math.max(c.t0,Math.min(c.end-0.5,a.currentTime+d))}catch(e){}c.arm()};
 c.setRate=r=>{c.rate=r;c.speed();c.arm()};
 c.stop=()=>{clr();try{a.pause()}catch(e){}st('')};
 c.clear=()=>{c.stop();a.removeAttribute('src');try{a.load()}catch(e){}c.url=''};
 c.busy=()=>c.state==='starting'||c.state==='loading'||c.state==='playing';
 c.at=()=>c.end>c.t0?Math.max(0,Math.min(1,(a.currentTime-c.t0)/(c.end-c.t0))):0;
 return c}
/* Be Led: a shuffle of pastors leading in prayer (the closing prayers of their sermons), one at a time, played right
   here on its own player: the ring plays and pauses, the small arrows either side go back or on 15 seconds, the arrows
   below go to the previous or next prayer. Nothing else on the screen but who is praying. */
var LED={c:null,id:null,sp:+S.get('ledsp',1)||1,done:false,tail:false,tt:null,fd:null,who:S.get('ledwho','')||''};   /* var: the music bed asks about it before this line runs */
const LED_SP=[1,1.1,1.25,0.9],
 PR_BACK=`<svg viewBox="0 0 28 28" width="30" height="30" aria-hidden="true"><path d="M7.6 9.2A8.6 8.6 0 1 1 5.4 15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M7.9 4.6v4.9h4.9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><text x="14.4" y="18.2" text-anchor="middle" font-size="7.6" font-weight="600" font-family="-apple-system,system-ui,sans-serif" fill="currentColor">15</text></svg>`,
 PR_FWD=PR_BACK.replace('<svg ','<svg style="transform:scaleX(-1)" ').replace('<text ','<text transform="translate(28 0) scale(-1 1)" ');
function dayNo(){return Math.floor((Date.now()-new Date().getTimezoneOffset()*6e4)/864e5)}
function ledList(){return PRAY.led||[]}
function ledById(id){return ledList().find(x=>x.id===id)||null}
/* today's place in the shuffle: the strongest first, none again until all are prayed, a new one each day */
function ledOrd(){const L=ledList(),ids=L.map(x=>x.id),have=new Set(ids);let o=S.get('ledord',null);
 const fresh=()=>{const f=p=>{const a=L.filter(p).map(x=>x.id);return prShuf(a.length).map(i=>a[i])};return {o:[...f(x=>(x.power||4)>=5),...f(x=>(x.power||4)<5)],p:0,d:dayNo()}};
 if(!o||!Array.isArray(o.o)||o.o.length!==ids.length||o.o.some(i=>!have.has(i)))o=fresh();
 else if(o.d!==dayNo()){o.p++;o.d=dayNo();if(o.p>=o.o.length)o=fresh()}
 S.set('ledord',o);return o}
function ledOk(id){const x=ledById(id);return !!x&&(!LED.who||x.who===LED.who)}
/* with a pastor chosen: his prayer at or after today's place in the shuffle */
function ledCur(){const L=ledList();if(!L.length)return null;const o=ledOrd();
 if(LED.who&&!ledOk(o.o[o.p])){let p=o.o.findIndex((id,j)=>j>o.p&&ledOk(id));if(p<0)p=o.o.findIndex(ledOk);if(p>=0){o.p=p;S.set('ledord',o)}}
 return ledById(o.o[o.p])||L[0]}
function ledPrev(){const o=ledOrd();return o.o.some((id,j)=>j<o.p&&ledOk(id))}
function ledWhos(){const s=[];ledList().forEach(x=>{if(!s.includes(x.who))s.push(x.who)});return s}
/* where the prayer starts and ends, in seconds from the file's start: from its measured length (sb/e count back from the end) */
function ledSpan(x,L){L=L||x.L||x.dur||0;return L?[Math.max(0,L-x.sb),Math.max(0,L-x.sb)+Math.max(1,x.sb-(x.e||0))]:[0,1e9]}
function ledC(){if(LED.c)return LED.c;const a=$('#ledm');
 LED.c=clipper(a,{state:s=>{if(s==='playing'&&LED.fade){LED.fade=false;ledFade(1,700)}ledPaint()},end:ledEnd,error:ledPaint,
  tick:()=>{const c=LED.c;if(c.end&&c.end-a.currentTime<1.2&&!LED.fd&&!a.paused)ledFade(0,Math.max(50,(c.end-a.currentTime)*1000/(a.playbackRate||1)));ledRing()}});
 a.addEventListener('play',()=>{LED.done=false;AUDIO_EL.forEach(b=>{if(!b.paused)b.pause()});if(LP.c&&LP.c.busy())LP.c.pause();{const p=pmEl();if(!p.paused)p.pause()}if(window.MED&&MED.on)medStop(false);ledSession()});
 AUDIO_EL.forEach(b=>b.addEventListener('play',()=>{if(!a.paused)a.pause()}));
 return LED.c}
function ledFade(v,ms){const a=$('#ledm');clearInterval(LED.fd);LED.fd=null;let v0=a.volume;if(Math.abs(v0-v)<0.01)return;const n=Math.max(1,Math.round(ms/40));let k=0;
 LED.fd=setInterval(()=>{k++;try{a.volume=Math.max(0,Math.min(1,v0+(v-v0)*k/n))}catch(e){}if(k>=n){clearInterval(LED.fd);LED.fd=null}},40)}
/* the prayer has ended: your music (under a prayer without its own) carries on a few seconds after the amen, then fades away */
function ledEnd(){const c=LED.c;LED.done=true;clearInterval(LED.fd);LED.fd=null;try{c.a.volume=1}catch(e){}c.clear();   /* let go of the sermon's file: nothing keeps downloading */
 bedOnAfter();ledPaint()}
function ledPP(){const x=ledCur(),c=ledC();if(!x)return;dlog('tap Be Led',x.id+' '+(c.state||'new'));bedKick();clearInterval(LED.fd);LED.fd=null;
 if(LED.id===x.id&&c.a.getAttribute('src')&&c.state!=='error'){if(c.busy()){c.pause();return}try{c.a.volume=0}catch(e){}LED.fade=true;if(LED.done||c.state==='ended'){LED.done=false;c.again()}else c.resume();return}
 LED.id=x.id;LED.done=false;c.rate=LED.sp;try{c.a.volume=0}catch(e){}LED.fade=true;const [t0,end]=ledSpan(x);
 c.go(x.audio,t0,end,d=>{if(isFinite(d)&&d>0){const [s,e]=ledSpan(x,d);c.t0=s;c.end=e}});ledPaint()}
function ledSeek(d){if(LED.c&&LED.id)LED.c.seek(d);ledRing()}
function ledGo(d){const L=ledList();if(!L.length)return;const o=ledOrd(),on=!!(LED.c&&LED.c.busy());let p=o.p+d;while(p>=0&&p<o.o.length&&!ledOk(o.o[p]))p+=d;
 if(p<0)return;if(p>=o.o.length){S.set('ledord',null);const n=ledOrd();n.p=Math.max(0,n.o.findIndex(ledOk));S.set('ledord',n)}else{o.p=p;S.set('ledord',o)}
 if(LED.c)LED.c.clear();LED.id=null;LED.done=false;
 if(view==='pray'&&PR.mode==='led'){const y=scrollY;render();window.scrollTo(0,y)}if(on)ledPP();else bedSync()}
function ledSession(){if(!('mediaSession' in navigator))return;const x=ledById(LED.id)||{};PM.ms=false;
 try{navigator.mediaSession.metadata=new MediaMetadata({title:'Be Led',artist:NAMES[x.who]||x.who||'',album:'Pray'})}catch(e){}
 [['play',()=>{if(!LED.c.busy())ledPP()}],['pause',()=>{if(LED.c.busy())LED.c.pause()}],['seekbackward',()=>ledSeek(-15)],['seekforward',()=>ledSeek(15)],['previoustrack',()=>ledGo(-1)],['nexttrack',()=>ledGo(1)]].forEach(([k,f])=>{try{navigator.mediaSession.setActionHandler(k,f)}catch(e){}})}
function ledRing(){const r=$('#ledfg'),c=LED.c;if(!r)return;const x=ledCur();let f=0;
 if(c&&x&&LED.id===x.id)f=LED.done?1:c.at();r.setAttribute('stroke-dasharray',(f*100).toFixed(2)+' 100');r.style.opacity=f>0?1:0}
function ledOn(){const x=ledCur(),c=LED.c;return !!(c&&x&&LED.id===x.id&&c.busy())}
function ledPaint(){bedSync();const b=$('[data-ledpp]');if(!b)return;const on=ledOn(),c=LED.c,s=c&&LED.id===(ledCur()||{}).id?c.state:'';
 b.querySelector('.led-in').innerHTML=on?PR_PAUSE:PR_PLAY;b.setAttribute('aria-label',on?'Pause':'Pray');b.classList.toggle('on',on);
 const eb=$('#ledeb');if(eb)eb.textContent=s==='loading'?'Loading…':s==='error'?"This prayer didn't load. Tap to try again.":'Be Led';eb&&eb.classList.toggle('err',s==='error');ledRing()}
/* the music under Pray: on or off and how loud, in a small panel the ♪ opens */
function prMuBtn(){const have=(PL.list||[]).length;return `<button data-prmu aria-expanded="${!!PR.mu}" aria-controls="prmu">♪ Music${have?(BED.led?' on':' off'):''}</button>`}
function prMuPanel(){const have=(PL.list||[]).length;return `<div class="pr-mu" id="prmu"${PR.mu?'':' hidden'}>${have?`<label class="pr-mu-row"><span>Music under the prayer</span><input type="checkbox" class="pr-sw" id="prmuon"${BED.led?' checked':''}></label><input type="range" id="prmulv" min="3" max="60" step="1" value="${Math.round(BED.plv*100)}" style="--p:${((BED.plv*100-3)/57*100).toFixed(1)}%" aria-label="Music level"${BED.led?'':' disabled'}><div class="bp-l"><span>Softer</span><span>Louder</span></div>`:`<p class="pr-mu-none">Add your prayer music in Stillness, and it plays softly under every prayer and reading.</p>`}</div>`}
function ledMusic(){const x=LED.id&&ledById(LED.id);return !!(x&&x.music)}
/* the heading with its arrows: ‹ BE LED ›, ‹ MEDITATE › (n of N), ‹ DRAW NEAR › (the movements) — always in view */
function prHead(eb,id,attr,prev,next,sub,err,lb){return `<div class="pr-head"><button class="pr-ha" ${attr}="-1" aria-label="Previous ${lb}"${prev?'':' disabled'}>${PR_AR(-1)}</button><div class="pr-hc"><div class="pr-eb${err?' err':''}"${id?` id="${id}"`:''}>${esc(eb)}</div>${sub||''}</div><button class="pr-ha" ${attr}="1" aria-label="Next ${lb}"${next?'':' disabled'}>${PR_AR(1)}</button></div>`}
function ledView(){const x=ledCur();if(!x)return `<p class="led-lead">Prayers are on their way.</p>`;
 return `<div class="pr-art pr-band">${prayArt('pl',1)}</div><section class="led" aria-label="Be Led">${prHead('Be Led','ledeb','data-ledgo',ledPrev(),true,'',false,'prayer')}<p class="led-who serif">${esc(NAMES[x.who]||x.who)}</p>
<div class="led-ctl"><button class="led-sk" data-ledsk="-15" aria-label="Back 15 seconds">${PR_BACK}</button><button class="led-ring" data-ledpp aria-label="Pray"><svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="47" class="led-tr"/><circle id="ledfg" cx="50" cy="50" r="47" class="led-fg" pathLength="100" stroke-dasharray="0 100" style="opacity:0" transform="rotate(-90 50 50)"/></svg><span class="led-in">${PR_PLAY}</span></button><button class="led-sk" data-ledsk="15" aria-label="Forward 15 seconds">${PR_FWD}</button></div>
<div class="led-opt"><button data-ledsp aria-label="Speed">${LED.sp}×</button><label class="led-pick"><select data-ledwho aria-label="Which pastor"><option value="">All pastors</option>${ledWhos().map(w=>`<option value="${esc(w)}"${LED.who===w?' selected':''}>${esc(NAMES[w]||w)}</option>`).join('')}</select><span aria-hidden="true">${esc(LED.who?(NAMES[LED.who]||LED.who):'All pastors')} ⌄</span></label>${prMuBtn()}</div>${prMuPanel()}</section>`}
/* Meditate: one thing Jesus said, read once by a pastor from his own sermon; then be still with it (your music under
   it) until you say Amen. A shuffle, a new one each day. No clock. Its own speed, remembered. */
var MED={c:null,on:false,step:'',k:0,t:null,pick:null,paused:false,sp:+S.get('medsp',1)||1};   /* var: the music bed may ask about it before this line runs */
const MED_SP=[1,0.9,0.8,1.1,1.25];
function medList(){return (PRAY.med||[]).filter(x=>x.audio)}
function medKey(x){return x.ref+'|'+x.who}
function medFresh(){const k=medList().map(medKey);return {o:prShuf(k.length).map(i=>k[i]),p:0,d:dayNo()}}
/* today's place in the shuffle: none again until all are heard, a new one each day */
function medOrd(){const keys=medList().map(medKey),have=new Set(keys);let o=S.get('medord',null);
 if(!o||!Array.isArray(o.o)||o.o.length!==keys.length||o.o.some(k=>!have.has(k)))o=medFresh();
 else if(o.d!==dayNo()){o.p++;o.d=dayNo();if(o.p>=o.o.length)o=medFresh()}
 S.set('medord',o);return o}
function medIdx(){const L=medList();if(!L.length)return -1;if(MED.pick){const k=L.findIndex(x=>x.ref===MED.pick);if(k>=0)return k}const o=medOrd(),k=L.findIndex(x=>medKey(x)===o.o[o.p]);return k>=0?k:0}
function medCur(){const k=medIdx();return k<0?null:medList()[k]}
function medC(){if(MED.c)return MED.c;const a=$('#medm');
 MED.c=clipper(a,{state:s=>{if(s==='loading'||s==='playing')medEb();bedSync()},end:()=>{if(MED.on&&MED.step==='listen')medNext()},error:()=>{if(!MED.on)return;MED.on=false;MED.paused=false;clearTimeout(MED.t);MED.step='err';medPaint();bedSync()}});
 a.addEventListener('play',()=>{AUDIO_EL.forEach(b=>{if(!b.paused)b.pause()});{const p=pmEl();if(!p.paused)p.pause()}if(LED.c&&LED.c.busy())LED.c.pause();if(window.LP&&LP.c&&LP.c.busy())LP.c.pause();medSession()});
 AUDIO_EL.forEach(b=>b.addEventListener('play',()=>{if(MED.on)medStop(false)}));return MED.c}
function medSession(){if(!('mediaSession' in navigator))return;const m=medCur()||{};PM.ms=false;
 try{navigator.mediaSession.metadata=new MediaMetadata({title:m.ref||'Meditate',artist:NAMES[m.who]||m.who||'',album:'Pray'})}catch(e){}
 [['play',()=>{if(MED.on&&MED.paused)medPause()}],['pause',()=>{if(MED.on&&!MED.paused)medPause()}],['seekbackward',null],['seekforward',null],['previoustrack',null],['nexttrack',null]].forEach(([k,f])=>{try{navigator.mediaSession.setActionHandler(k,f)}catch(e){}})}
function medLabel(){const s=MED.c&&MED.c.state;if(MED.on&&s==='loading')return 'Loading…';const L={listen:'Listen',pause:'',again:'Again',still:'Be still',done:'Amen',err:"This reading didn't load. Tap Begin to try again."};return MED.step in L?L[MED.step]:'Meditate'}
function medEb(){const e=$('#medeb');if(e)e.textContent=medLabel()}
function medPaint(){if(view!=='pray'||PR.mode!=='med')return;const y=scrollY;render();window.scrollTo(0,y)}
/* the saying sized to the screen it is on: a size smaller at a time (not below 15px) until Begin, the pause or Amen sits
   above the tab bar — every phone's font and screen differ, so it is measured, not guessed */
function medFit(){const q=document.querySelector('.med-q'),c=document.querySelector('.med-ctl button'),tb=$('#tabs');if(!q||!c||!tb)return;
 q.style.fontSize='';q.style.lineHeight='';let fs=parseFloat(getComputedStyle(q).fontSize);const lim=tb.getBoundingClientRect().top-6;
 for(let k=0;k<12&&fs>15&&c.getBoundingClientRect().bottom+window.scrollY>lim;k++){fs=Math.max(15,fs-1);q.style.fontSize=fs+'px';q.style.lineHeight='1.38'}}
window.addEventListener('resize',()=>{if(view==='pray'&&PR.mode==='med')medFit()});window.addEventListener('orientationchange',()=>setTimeout(()=>{if(view==='pray'&&PR.mode==='med')medFit()},300));
function medStart(){const m=medCur();if(!m)return;dlog('tap Begin',m.ref);bedKick();if(!audio.paused)audio.pause();{const pa=pmEl();if(!pa.paused)pa.pause()}if(LED.c&&LED.c.busy())LED.c.pause();
 const c=medC();clearTimeout(MED.t);MED.on=true;MED.k=0;MED.paused=false;MED.step='listen';c.rate=MED.sp;c.go(m.audio,m.a,m.b,d=>{const r=c.r=tscale(d,m.Lt);c.t0=m.a*r;dlog('scale',{length:d,true_length:m.Lt,ratio:Math.round(r*100000)/100000})},m.b);medPaint();bedSync()}
function medNext(){if(!MED.on)return;
 MED.step='still';if(MED.c)MED.c.clear();medPaint();bedSync()}
function medPause(){const c=MED.c;if(!MED.on||!c||MED.step==='pause'||MED.step==='still')return;MED.paused=!MED.paused;if(MED.paused)c.pause();else c.resume();medPaint();bedSync()}
function medStop(done){MED.on=false;MED.paused=false;clearTimeout(MED.t);MED.step=done?'done':'';if(MED.c)MED.c.clear();medPaint();bedSync()}
function medGo(d){if(!medList().length)return;const o=medOrd(),p=o.p+d;if(p<0)return;if(MED.on)medStop(false);S.set('medord',p>=o.o.length?medFresh():Object.assign(o,{p}));MED.pick=null;MED.step='';medPaint()}
function medView(){const L=medList(),m=medCur(),k=medIdx();if(!m)return `<p class="led-lead">The sayings are on their way.</p>`;const long=m.t.length>150;
 const ctl=MED.step==='still'?`<button class="med-go" data-medamen>Amen</button>`:MED.on?`<button class="med-pp" data-medpp aria-label="${MED.paused?'Go on':'Pause'}"${MED.step==='pause'?' disabled':''}>${MED.paused?PR_PLAY:PR_PAUSE}</button>`:`<button class="med-go" data-medgo>Begin</button>`;
 return `<div class="pr-art pr-band${long?' sm':''}">${prayArt('pm',1)}</div><section class="med${MED.on?' on':''}" aria-label="Meditate">${prHead(medLabel(),'medeb','data-medgo2',medOrd().p>0,true,`<span class="med-n">${medOrd().p+1} of ${L.length}</span>`,MED.step==='err','saying')}<p class="med-q serif${m.t.length>330?' xl xxl':m.t.length>240?' xl':m.t.length>=140?' l':''}">${esc(m.t)}</p><div class="med-ref">${esc(m.ref)}</div>${m.who?`<div class="med-by">Read by ${esc(NAMES[m.who]||m.who)}</div>`:''}
<div class="med-ctl">${ctl}</div><div class="led-opt med-opt"><button data-medsp aria-label="Reading speed">${MED.sp}×</button>${prMuBtn()}</div>${prMuPanel()}</section>`}
/* Guided with a pastor: one of the library's pastors praying the Lord's Prayer through (data/guided_lp.json), played
   from his sermon; the movement on screen follows him, the arrows go to a movement in his prayer */
var LP={c:null,done:false};
function lpD(){return PRAY.lp||null}
function lpC(){if(LP.c)return LP.c;const a=$('#lpm');
 LP.c=clipper(a,{state:()=>lpPaint(),end:()=>{LP.done=true;LP.c.clear();bedOnAfter();lpPaint()},error:lpPaint,tick:lpFollow});
 a.addEventListener('play',()=>{LP.done=false;AUDIO_EL.forEach(b=>{if(!b.paused)b.pause()});{const p=pmEl();if(!p.paused)p.pause()}if(LED.c&&LED.c.busy())LED.c.pause();if(MED.on)medStop(false);lpSession()});
 AUDIO_EL.forEach(b=>b.addEventListener('play',()=>{if(!a.paused)a.pause()}));return LP.c}
function lpLive(){return !!(LP.c&&LP.c.a.getAttribute('src')&&!LP.done&&LP.c.state!=='error'&&LP.c.state!=='')}
/* the movement on screen follows him */
function lpFollow(){if(!LP.c.busy())return;const x=lpD(),t=LP.c.trueAt(LP.c.a.currentTime);let k=0;x.at.forEach((s,i)=>{if(t>=s-0.3)k=i});if(k!==PR.mv&&view==='pray'&&PR.mode==='guided'){PR.mv=k;PR.anim='l';const y=scrollY;render();PR.anim='';window.scrollTo(0,y)}}
function lpPP(){const x=lpD();if(!x)return;dlog('tap Pray it with',LP.c?LP.c.state:'new');bedKick();const c=lpC();
 if(c.a.getAttribute('src')&&!LP.done&&c.state!=='error'&&c.state!==''){if(c.busy())c.pause();else c.resume();return}
 LP.done=false;c.rate=1;LP.r=1;const t0=PR.mv>0&&x.at[PR.mv]!=null?x.at[PR.mv]:x.a;
 c.go(x.audio,t0,x.b,d=>{const r=LP.r=c.r=tscale(d,x.Lt);c.t0=t0*r;dlog('scale',{length:d,true_length:x.Lt,ratio:Math.round(r*100000)/100000})},x.b);lpPaint()}
function lpSeek(d){const x=lpD(),c=LP.c,r=LP.r||1;if(!lpLive())return;try{c.a.currentTime=Math.max(x.a*r,Math.min(c.end-0.5,c.a.currentTime+d))}catch(e){}}
function lpSession(){if(!('mediaSession' in navigator))return;const x=lpD();PM.ms=false;try{navigator.mediaSession.metadata=new MediaMetadata({title:"The Lord's Prayer",artist:NAMES[x.who]||x.who,album:'Pray'})}catch(e){}
 [['play',()=>{if(!LP.c.busy())lpPP()}],['pause',()=>{if(LP.c.busy())LP.c.pause()}],['seekbackward',()=>lpSeek(-15)],['seekforward',()=>lpSeek(15)],['previoustrack',()=>prGo(-1)],['nexttrack',()=>prGo(1)]].forEach(([k,f])=>{try{navigator.mediaSession.setActionHandler(k,f)}catch(e){}})}
function lpMusic(){return true}
function lpPaint(){bedSync();const b=$('[data-lpp]');if(!b)return;const on=!!(LP.c&&LP.c.busy()),st=LP.c&&LP.c.state;b.querySelector('i').innerHTML=on?PR_PAUSE:PR_PLAY;b.setAttribute('aria-label',on?'Pause':'Pray it with '+(NAMES[lpD().who]||''));
 const sp=b.querySelector('span');if(sp)sp.textContent=st==='loading'?'Loading…':st==='error'?"It didn't load. Tap to try again.":'Pray it with '+(NAMES[lpD().who]||lpD().who);
 document.querySelectorAll('[data-lpsk]').forEach(s=>s.hidden=!lpLive())}
function lpLine(){const x=lpD();if(!x)return '';return `<div class="lp-line"><button class="led-sk" data-lpsk="-15" aria-label="Back 15 seconds" hidden>${PR_BACK}</button><button class="lp-pp" data-lpp><i>${PR_PLAY}</i><span>Pray it with ${esc(NAMES[x.who]||x.who)}</span></button><button class="led-sk" data-lpsk="15" aria-label="Forward 15 seconds" hidden>${PR_FWD}</button></div><div class="led-opt lp-opt">${prMuBtn()}</div>${prMuPanel()}`}
function prayView(){if(PR.mode==='guided')prSession();
 let h=`<div class="jv pray" id="pray">${moreBtn()}<h1 class="jv-t" style="margin-top:6px">Pray</h1><div class="t-sort lib-seg pr-seg" role="tablist" aria-label="Pray">${[['still','Stillness'],['g','Guided']].map(([v,l])=>{const on=v==='still'?PR.mode==='still':PR.mode!=='still';return `<button role="tab" data-prtop="${v}" class="${on?'on':''}" aria-selected="${on}">${l}</button>`}).join('')}</div>${PR.mode==='still'?'':`<div class="t-sort pr-sub" role="tablist" aria-label="Guided">${[['led','Be Led'],['guided',"Lord's Prayer"],['med','Meditate']].map(([v,l])=>`<button role="tab" data-prm="${v}" class="${PR.mode===v?'on':''}" aria-selected="${PR.mode===v}">${l}</button>`).join('')}</div>`}`;
 if(PR.mode==='led')return h+ledView()+'</div>';
 if(PR.mode==='med')return h+medView()+'</div>';
 if(PR.mode==='still'&&PL.list&&!PL.list.length)return h+`<div class="pr-art pr-still">${prayArt('ps')}</div><div class="pr-ctl"><button class="pr-pp" data-pm aria-label="Bring the music onto this phone" style="opacity:.4">${PR_PLAY}</button></div><p class="pr-st" data-mbst>${esc(bkOn()?(MB.msg||'Bringing your prayer music onto this phone…'):'Turn on Backup in ⋯ to bring your prayer music onto this phone.')}</p></div>`;
 if(PR.mode==='still')return h+`<div class="pr-art pr-still">${prayArt('ps')}</div><div class="pr-ctl"><button class="pr-sk" data-pms="-1" aria-label="Previous piece">${PR_SKIP(-1)}</button><button class="pr-pp" data-pm aria-label="Play the music">${PR_PLAY}</button><button class="pr-sk" data-pms="1" aria-label="Next piece">${PR_SKIP(1)}</button></div></div>`;
 const m=PRAY.moves[PR.mv]||PRAY.moves[0],s=prSup(m),n=PRAY.moves.length;
 return h+`<div class="pr-art pr-band">${prayArt('pg',1)}${(PL.list||[]).length&&!lpD()?`<button class="pr-mini" data-pm aria-label="Play the music">${PR_PLAY}</button>`:''}</div>
${lpLine()}<section class="pr-g${PR.anim?' in-'+PR.anim:''}" aria-label="${esc(m.label)}">${prHead(m.label,'','data-prmv',PR.mv>0,PR.mv<n-1,`<span class="pr-dots" aria-hidden="true">${PRAY.moves.map((x,k)=>`<i class="${k===PR.mv?'on':''}"></i>`).join('')}</span>`,false,'movement')}<p class="pr-lp serif">${esc(m.lp)}</p><div class="pr-lpr">${esc(m.lpr)}</div><p class="pr-ins">${esc(m.ins)}</p><div class="pr-rule" aria-hidden="true"></div>
<figure class="pr-sup"><blockquote class="serif" id="prst">${esc(s.t)}</blockquote><figcaption><button class="pr-supr" id="prsr" aria-label="${esc(s.r)}: show another passage"><span>${esc(s.r)}</span>${PR_TURN}</button></figcaption></figure></section></div>`}
function prGo(d){const k=PR.mv+d;if(k<0||k>=PRAY.moves.length)return;if(lpLive()){const x=lpD();try{LP.c.a.currentTime=x.at[k]*(LP.r||1)}catch(e){}}PR.mv=k;S.set('prlast',Date.now());PR.anim=d>0?'l':'r';const y=scrollY;render();PR.anim='';window.scrollTo(0,y)}
function wirePray(){pmEl();pmPaint();if(!PL.list){plLoad().then(()=>{if(view==='pray')render()});return}pmPrime();if(!PL.list.length&&bkOn()&&!MB.busy)mbSync(true);
 document.querySelectorAll('[data-pradd]').forEach(b=>b.onclick=()=>prPick(()=>{if(view==='pray')render()}));
 document.querySelectorAll('[data-prm]').forEach(b=>b.onclick=()=>{if(PR.mode===b.dataset.prm)return;PR.mode=b.dataset.prm;S.set('prm',PR.mode);S.set('prsub',PR.mode);render()});
 document.querySelectorAll('[data-prtop]').forEach(b=>b.onclick=()=>{const m=b.dataset.prtop==='still'?'still':(['led','guided','med'].includes(S.get('prsub','led'))?S.get('prsub','led'):'led');if(PR.mode===m||(b.dataset.prtop==='g'&&PR.mode!=='still'))return;PR.mode=m;S.set('prm',PR.mode);render()});
 document.querySelectorAll('[data-medgo]').forEach(b=>b.onclick=medStart);document.querySelectorAll('[data-medamen]').forEach(b=>b.onclick=()=>medStop(true));document.querySelectorAll('[data-medpp]').forEach(b=>b.onclick=medPause);
 document.querySelectorAll('[data-medgo2]').forEach(b=>b.onclick=()=>medGo(+b.dataset.medgo2));
 document.querySelectorAll('[data-lpp]').forEach(b=>b.onclick=lpPP);document.querySelectorAll('[data-lpsk]').forEach(b=>b.onclick=()=>lpSeek(+b.dataset.lpsk));if(PR.mode==='guided'&&lpD())lpPaint();
 document.querySelectorAll('[data-ledpp]').forEach(b=>b.onclick=ledPP);document.querySelectorAll('[data-ledsk]').forEach(b=>b.onclick=()=>ledSeek(+b.dataset.ledsk));document.querySelectorAll('[data-ledgo]').forEach(b=>b.onclick=()=>ledGo(+b.dataset.ledgo));
 document.querySelectorAll('[data-ledwho]').forEach(s=>s.onchange=()=>{LED.who=s.value;S.set('ledwho',LED.who);const on=!!(LED.c&&LED.c.busy());if(LED.id&&!ledOk(LED.id)){if(LED.c)LED.c.clear();LED.id=null;LED.done=false}const y=scrollY;render();window.scrollTo(0,y);if(on&&!LED.id)ledPP()});
 document.querySelectorAll('[data-ledsp]').forEach(b=>b.onclick=()=>{LED.sp=LED_SP[(LED_SP.indexOf(LED.sp)+1)%LED_SP.length];S.set('ledsp',LED.sp);if(LED.c)LED.c.setRate(LED.sp);b.textContent=LED.sp+'×'});
 document.querySelectorAll('[data-medsp]').forEach(b=>b.onclick=()=>{MED.sp=MED_SP[(MED_SP.indexOf(MED.sp)+1)%MED_SP.length];S.set('medsp',MED.sp);if(MED.c)MED.c.setRate(MED.sp);b.textContent=MED.sp+'×'});
 document.querySelectorAll('[data-prmu]').forEach(b=>b.onclick=()=>{PR.mu=!PR.mu;const p=$('#prmu');if(p)p.hidden=!PR.mu;b.setAttribute('aria-expanded',PR.mu)});
 {const on=$('#prmuon'),lv=$('#prmulv');if(on)on.onchange=()=>{BED.led=on.checked;S.set('bedled',BED.led);BED.unl=false;bedUnlock();bedSync();const b=$('[data-prmu]');if(b)b.textContent='♪ Music '+(BED.led?'on':'off');if(lv)lv.disabled=!BED.led};
  if(lv){lv.oninput=()=>{BED.plv=+lv.value/100;lv.style.setProperty('--p',((lv.value-3)/57*100).toFixed(1)+'%');S.set('bedlvp',BED.plv);if(bedWanted()&&bedPray()&&BED.mode==='wa')bedGain(bedLevel(),120)};lv.onchange=()=>{if(bedWanted()&&bedPray())bedGain(bedLevel(),120)}}}
 if(PR.mode==='led')ledPaint();if(PR.mode==='med')medFit();
 document.querySelectorAll('[data-pm]').forEach(b=>b.onclick=pmToggle);
 document.querySelectorAll('[data-pms]').forEach(b=>b.onclick=()=>pmSkip(+b.dataset.pms));
 document.querySelectorAll('[data-prmv]').forEach(b=>b.onclick=()=>prGo(+b.dataset.prmv));
 const r=$('#prsr');if(r)r.onclick=()=>{const m=PRAY.moves[PR.mv];prAnother(m);const s=prSup(m),q=$('#prst');q.classList.add('fade');setTimeout(()=>{q.textContent=s.t;r.querySelector('span').textContent=s.r;r.setAttribute('aria-label',s.r+': show another passage');q.classList.remove('fade')},230)};
 const g=$('#pray');if(g){let t0=null;   /* a swipe left or right anywhere in Pray: the next or the previous (not from the screen's edge, not on the music panel) */
  const swipe=d=>{if(PR.mode==='led')ledGo(d);else if(PR.mode==='med')medGo(d);else if(PR.mode==='guided')prGo(d);else if(PR.mode==='still')pmSkip(d)};
  g.addEventListener('touchstart',e=>{t0=null;if(e.touches.length!==1)return;const t=e.touches[0];if(t.clientX<22||(e.target.closest&&e.target.closest('.pr-mu,input,.pr-sub,.pr-seg')))return;t0={x:t.clientX,y:t.clientY,lx:t.clientX,ly:t.clientY,t:Date.now(),y0:scrollY}},{passive:true});
  g.addEventListener('touchmove',e=>{if(t0&&e.touches.length===1){t0.lx=e.touches[0].clientX;t0.ly=e.touches[0].clientY}},{passive:true});
  g.addEventListener('touchend',()=>{if(!t0)return;const dx=t0.lx-t0.x,dy=t0.ly-t0.y,ok=Date.now()-t0.t<900&&Math.abs(scrollY-t0.y0)<16;t0=null;if(ok&&Math.abs(dx)>50&&Math.abs(dx)>1.7*Math.abs(dy))swipe(dx<0?1:-1)},{passive:true})}}
function render(){roomForPlayer();const m=$('#main');if(!render.boot){render.boot=true;view=location.hash==='#worship'?'worship':'journey';if(location.hash==='#worship')history.replaceState(null,'',location.pathname);S.set('view',view);try{cutApply()}catch(e){}migrateCamp();migrateCamp3();nplFix();setTimeout(nplOnce,400);setTimeout(()=>{try{ptLoad()}catch(e){}},700)}tabsPaint();if(view==='pray'){m.innerHTML=prayView();wire();wirePray();return}if(view!=='worship')document.body.classList.remove('wsong-open');if(view==='worship'){m.innerHTML=worshipView();wire();wireWorship();return}if(view==='journey'&&JZ==='stop'){m.innerHTML=journeyView();wire();wireJourney();return}if(view==='bigpicture'){view='library';LT='series';S.set('view',view);S.set('libtab',LT)}if(view==='bible'){m.innerHTML=bibleView();wire();wireBible();return}if(view==='library'){m.innerHTML=libView();wire();wireLib();return}if(!render.boot2){render.boot2=true;migrateCamp();camp=jpIdx();const a=nextAction(camp);if(a&&a.step){TAB=a.step;S.set('tab',TAB)}}if(view==='settings'){m.innerHTML=settingsView();wire();return}if(view==='sc'){m.innerHTML=scView();wire();return}
 migrateCamp();migrateCamp3();const w=walk();let first=jpIdx();if(camp==null||camp>=w.length)camp=first;  /* the road is walked up to your place */
 const rd=w.filter(x=>!x.c.intro&&read[x.b.abbr+x.c.c]).length;$('#pct').innerHTML=`<b>${rd}</b> of 1,189 chapters · ${Math.round(1000*rd/1189)/10}%`;
 const rows=D.books[0].yr?24:16,rowH=240,top=120,H=top+rows*rowH+200,x0=70,x1=320;let d=`M ${x0} ${top}`;for(let r=0;r<rows;r++){const f=r%2?x1:x0,t=r%2?x0:x1,y=top+r*rowH;d+=` C ${f} ${y+rowH*.55}, ${t} ${y+rowH*.45}, ${t} ${y+rowH}`}
 const POS=[];let acc=0;for(const b of books()){const wgt=(D.books[0].yr?11:6)+2.2*Math.sqrt(b.n);const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;[...(secHas(b)?['s']:[]),0,...chs].forEach((c,k)=>POS.push(acc+wgt*(k+0.5)/nSt(b)));acc+=wgt}
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
 for(const b of books()){const mid=at(idx+nSt(b)/2),st=at(idx);let side=mid.x<195?'L':'R';if(b.n<10&&prevShort&&side===prevSide)side=side==='L'?'R':'L';
  const land=cfg.order==='canon'?LANDS.find(l=>l[0]===b.name):null;
  if(land){lands+=`<circle cx="${st.x}" cy="${st.y}" r="90" fill="url(#g)" class="glow"/>`;const txt=land[1].replace('The End & the New Beginning','The New Beginning');labs.push({kind:'land',side:st.x<195?'L':'R',x:st.x<195?st.x+40:st.x-40,y:mid.y+5-0.5,txt})  /* heading sits right above its first book */}
  labs.push({kind:'book',side,x:side==='L'?Math.min(mid.x+30,250):Math.max(mid.x-30,140),y:mid.y+5,px:mid.x,py:mid.y,txt:b.name,yr:b.yr||'',big:b.n>=20,here:w[camp].b===b,idx:idx+(secHas(b)?1:0)});
  prevSide=side;prevShort=b.n<10;idx+=nSt(b)}
 labs.sort((a,b)=>a.y-b.y);const last={L:-1e9,R:-1e9};let lbl='';decorate.drift=labs;
 for(const l of labs){const gap=l.kind==='land'?30:(D.books[0].yr?38:24);const ref=Math.max(last.L,last.R);  /* one column: labels on either side can reach the middle */if(l.y-ref<gap)l.y=ref+gap;if(l.kind==='land'){last.L=last.R=l.y}else last[l.side]=l.y;
  if(l.kind==='land'){lbl+=`<text x="${l.x}" y="${l.y}" text-anchor="${l.side==='L'?'start':'end'}" class="land">${l.txt}</text>`}
  else{const moved=Math.abs(l.y-5-l.py)>12;if(moved)lbl+=`<line x1="${l.px}" y1="${l.py}" x2="${l.side==='L'?l.x-6:l.x+6}" y2="${l.y-5}" stroke="rgba(241,237,228,.25)" stroke-width="1"/>`;
   lbl+=`<text x="${l.x}" y="${l.y}" text-anchor="${l.side==='L'?'start':'end'}" class="bl ${l.big?'big':''} ${l.here?'here':''}" data-camp="${l.idx}">${l.txt}</text>${l.yr?`<text x="${l.x}" y="${l.y+15}" text-anchor="${l.side==='L'?'start':'end'}" class="byr">${l.yr}</text>`:''}`}}
 // scenery: stars thin out toward the New Testament dawn; each land gets its horizon
 let sky='';const Hs=+svg.getAttribute('viewBox').split(' ')[3];HH=Hs;let seed=7;const rnd=()=>{seed=(seed*9301+49297)%233280;return seed/233280};
 for(let i=0;i<140;i++){const yy=rnd()*Hs;if(rnd()<1-yy/Hs)sky+=`<circle cx="${(rnd()*390).toFixed(0)}" cy="${yy.toFixed(0)}" r="${(0.6+rnd()*1.2).toFixed(1)}" fill="rgba(168,129,42,${(0.12+rnd()*0.25).toFixed(2)})"/>`}
 let scenes='';idx=0;for(const b of books()){const land=cfg.order==='canon'?LANDS.find(l=>l[0]===b.name):null;if(land){const st=at(idx);scenes+=`<g opacity=".7">${sceneSVG(SCENES[land[1]],st.x,st.y-40)}</g>`}idx+=nSt(b)}
 // landmarks: where the great scenes stand
 let marks='',lastVy=-1e9;
 w.forEach((x,i)=>{const lm=LANDMARKS[x.b.abbr+x.c.c];if(!lm)return;const pt=at(i);if(pt.y-lastVy<110)return;lastVy=pt.y;marks+=`<g transform="translate(${pt.x} ${pt.y}) scale(.6) translate(${-pt.x} ${-pt.y})" opacity=".75">${vignette2(lm[0],pt.x,pt.y)}</g>`});
 // per-book motifs beside the road, alternating sides; rivers at the Jordan and the river of life
 let mot='';idx=0;for(const b of books()){const land=cfg.order==='canon'?(LANDS.slice().reverse().find(l=>books().indexOf(b)>=books().findIndex(bb=>bb.name===l[0]))||[,''])[1]:'';const mid=at(idx+nSt(b)/2);const side=mid.x<195?1:-1;const kinds={'The Law':['palm','tent','palm'],'History':['town','town','palm'],'Wisdom & Song':['olive','olive','palm'],'Major Prophets':['cedar','town','cedar'],'Minor Prophets':['olive','town','olive'],'The Gospels':['olive','town','olive'],'The Church Begins':['sail','sail','town'],'Letters of Paul':['column','sail','column'],'General Letters':['fire','fire','town'],'The New Beginning':['tree','tree','tree']}[land];
  if(kinds){const ox=mid.x+side*(118+(b.n%3)*12);if(ox>30&&ox<360)mot+=motif('',ox,mid.y+12,b.n>=20?.9:.7)}
  if(b.name==='Joshua'){const st=at(idx);mot+=river(st.x,st.y+6)}if(b.name==='Revelation'){const st=at(idx+b.n-2);mot+=river(st.x,st.y+40,.18)}idx+=nSt(b)}
 $('#sky').innerHTML=terrain(Hs)+celestial(Hs)+sky+scenes+mot;
 $('#lands').innerHTML=lands;$('#labels').innerHTML=lbl+marks;
 const m=at(camp),f=at(first);
 $('#marker').innerHTML=`${camp!==first?`<circle cx="${f.x}" cy="${f.y}" r="8" fill="var(--gold)" opacity=".7"/>`:''}<circle cx="${m.x}" cy="${m.y}" r="26" fill="rgba(240,215,154,.18)"/><circle cx="${m.x}" cy="${m.y}" r="13" fill="var(--gold)" class="you"/><circle cx="${m.x}" cy="${m.y}" r="5" fill="#fff"/>`;
 // clearing placed in the world beside the marker
 const sc=svg.getBoundingClientRect().width/390,cl=$('#clearing');const x=w[camp],b=x.b,c=x.c,ids=c.ids.filter(okWho),r=!!read[b.abbr+c.c],ov=(c.sec?spansAt(b,c).map(s=>s.id):c.intro?b.ov:[]).filter(okWho);const fold=FOLD;cl.classList.toggle('folded',fold);
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
function go(i){if(view==='journey'&&JZ==='road'){roadPick(i);return}{const w=walk(),here=camp!=null&&w[camp];if(here&&here.c.intro&&i>camp&&!read[here.b.abbr+(here.c.sec?'s':'0')]){read[here.b.abbr+(here.c.sec?'s':'0')]=true;S.set('read',read)}}camp=i;FOLD=false;decorate.more=false;decorate.follow=true;S.set('camp',camp);if(i===jpIdx()){const a=nextAction(i);if(a&&a.step){TAB=a.step;S.set('tab',TAB)}}render()}
/* one step along the road: from your place that is walking on; anywhere else it is just looking */
function stepTo(to){go(to)}
function bkForm(again){return `<form id="bkf" class="bkf" autocomplete="on"><input type="text" name="username" autocomplete="username" value="Scripture Companion backup" readonly class="bk-u" tabindex="-1" aria-hidden="true"><input type="password" name="password" id="bkkey" autocomplete="current-password" placeholder="${again?'Paste a new GitHub key':'Paste your GitHub key'}" required><input type="text" id="bkrepo" value="${esc(bkRepo())}" aria-label="Backup repo (owner/name)" autocapitalize="off" spellcheck="false"><button class="btn" type="submit">${again?'Use this key':'Turn on backup'}</button><p class="note" id="bkmsg"></p></form>`}
function settingsView(){
 return `<div class="settings"><button class="sccard" id="opensc"><span class="serif">Secret Church</span><small>${scGroups().length} nights · every session in order ›</small></button><h2 class="serif" style="margin:0 0 8px">Your journey</h2><p class="note">${(()=>{const w=walk(),j=jpIdx(),rd=w.filter(x=>!x.c.intro&&read[scrKey(x)]).length,hh=Math.round(Object.values(prog).reduce((a,v)=>a+(v&&v.heard||0),0)/3600),sk=Object.keys(SKIP).length;
  return `You are at <b>${esc(stopName(w[j]))}</b>${rd?`, with ${rd.toLocaleString()} chapter${rd>1?'s':''} of Scripture read`:''}${hh?` and ${hh.toLocaleString()} hour${hh>1?'s':''} of teaching heard`:''}.</p><p class="note">${coreOn()?`Each stop has three steps: the narrator's <b>Introduction</b>, the <b>Scripture</b> to read or hear, and one <b>Core</b> teaching on it, chosen for how well it explains the passage. Everything else on the chapter is in <b>Go Deeper</b>, optional. A teaching that covers several chapters shows on each of them. Any sermon in Go Deeper can be made Core with a tap.`:`Each stop on the road has three steps: an <b>Overview</b> (the book, or a stretch of chapters), the <b>Scripture</b> itself to read or hear, and <b>Teaching</b>: the whole chapter first, then verse by verse. Continue always offers the next one. A teaching that covers several chapters waits at the first of them, and the next chapter waits for you.`}${sk?` <button class="lnk" id="unskip">Bring back the ${sk} you skipped</button>`:''}`})()}</p>
 <p>
 <span class="btn" id="who" style="display:inline-block;cursor:pointer">Voices: ${cfg.who?NAMES[cfg.who]+' only':'everyone'} — switch</span></p>
 ${CORE.u.length?`<p class="note" style="margin-top:14px"><b>Core teacher.</b> ${coreOn()?`Core picks the teaching that best explains each passage, favouring ${esc(cfg.corePref?NAMES[cfg.corePref]:'Mitchell, then Platt, then Vaughan, then Heitzig, then Davey')}.`:'Off: every teaching on a chapter is queued, as before.'}</p>
 <div class="cprefs" role="group" aria-label="Preferred teacher for Core">${[['','Suggested'],['Platt','Platt'],['PAM','Mitchell'],['Skip','Heitzig'],['Davey','Davey'],['Vaughan','Vaughan']].filter(([k])=>!HIDE.includes(k)).map(([k,l])=>`<button class="btn${coreOn()&&(cfg.corePref||'')===k?' on':''}" data-cpref="${k}">${l}</button>`).join('')}<button class="btn${coreOn()?'':' on'}" data-cpref="off">Every teaching</button></div>
 ${Object.keys(coreSet()).length?`<p class="note"><button class="lnk" id="corereset">Undo the ${Object.keys(coreSet()).length} Core choice${Object.keys(coreSet()).length>1?'s':''} you made</button></p>`:''}`:''}
 <p class="note">Bible text: Berean Standard Bible (public domain). People, places and family links adapted from Theographic Bible Metadata (CC BY-SA 4.0). Map: Natural Earth (public domain).${prCredits()}</p>${prMusicNote()}<h2 class="serif" style="margin:22px 0 8px">Backup</h2>${bkOn()?`<p class="note" id="bkst">${bkStatus()}</p><button class="btn" id="bknow">Back up now</button><button class="btn" id="bkrest">Restore from backup</button><button class="btn" id="bkoff">Turn off</button>${BK.err?bkForm(true):''}`:`<p class="note">Your progress lives only on this phone. Turn on backup and it saves itself to a private GitHub repo you own; on a new phone, paste the same key and everything comes back.</p>
 <ol class="note bk-steps"><li><a href="https://github.com/new?name=scripture-companion-backup&visibility=private" target="_blank" rel="noopener">Create the private repo</a> (name and Private are filled in: tap <b>Create repository</b>).</li><li><a href="https://github.com/settings/personal-access-tokens/new?name=Scripture%20Companion%20backup&description=Lets%20the%20app%20save%20listening%20progress&expires_in=none&contents=write" target="_blank" rel="noopener">Make a key</a>: under <b>Repository access</b> pick <b>Only select repositories</b> → scripture-companion-backup; check <b>Contents: Read and write</b>; tap <b>Generate</b> and copy it.</li><li>Paste it here. Your iPhone offers to save it in Passwords, so a new phone fills it in.</li></ol>${bkForm(false)}`}
 <p class="note" style="margin-top:18px">By hand:</p><button class="btn" id="exp">Export</button><button class="btn" id="imp">Import</button><button class="btn" id="reset">Reset</button><textarea id="io" placeholder="Exported progress appears here; paste here to import."></textarea>
 <p class="note" id="envn">${location.protocol==='file:'||window!==window.top?'This viewer blocks audio. Serve the file from a web address and open it in Safari, then Add to Home Screen.':'Audio should stream here.'} <button class="btn" id="atest" style="padding:4px 10px">Test audio</button><span id="atest-out"></span></p>
 <h2 class="serif" style="margin:22px 0 8px">Diagnostics</h2><p class="note">If something isn't working, copy this and paste it to Claude: what the app did (opening, Pray's players, the music). It stays on this phone.</p><p><button class="btn" onclick="diagCopy()">Copy diagnostics</button> <span id="diagmsg" class="note"></span></p>
 <button class="btn" id="back">‹ Back to the road</button></div>`}
/* Secret Church library: every night, every session, in order (the podcast's sessions where it has them) */
function scGroups(){const by={};D.sc.ids.forEach(id=>{const i=I[id];if(!i||!i.sc)return;(by[i.sc[0]]=by[i.sc[0]]||[]).push(id)});
 return D.sc.events.map(ev=>{let ids=by[ev.n]||[];const pod=ids.filter(id=>I[id].src==='secret_church_podcast');if(pod.length)ids=pod;
  return {ev,ids:ids.slice().sort((a,b)=>(I[a].sc[1]||0)-(I[b].sc[1]||0))}}).filter(g=>g.ids.length)}
function scSeq(){return scGroups().flatMap(g=>g.ids).filter(id=>I[id].audio)}
function scView(){const G=scGroups(),tot=G.reduce((a,g)=>a+g.ids.length,0);
 let h=`<div class="settings scl"><button class="btn" id="scback">‹ Series</button><h2 class="serif" style="margin:14px 0 4px">Secret Church</h2>
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
function where(id){if(I[id]&&I[id].led)return 'from '+dispTitle({t:I[id].led.from});if(I[id]&&I[id].nar)return I[id].nar.book+' '+I[id].nar.c;if(I[id]&&I[id].intro)return I[id].intro.book+(I[id].intro.c?' '+I[id].intro.c:'');for(const b of D.books){if(b.ov.includes(id)||(b.spans||[]).some(x=>x.id===id))return b.name;for(const c of b.ch)if(c.ids.includes(id))return b.name+' '+c.c}return ''}
/* every list works the same way: the play button plays (or pauses) in the mini player; tapping the row opens the full player */
function playRow(id,full){if(!I[id]||!I[id].audio)return;JM=false;BPM=null;PLAYSTOP=view==='journey'?jpIdx():view==='walk'?camp:null;
 DEEP=view==='journey'&&coreOn()&&JV.deep&&deepIds(jpIdx()).includes(id)?{i:jpIdx()}:null;if(SKIP[id]){delete SKIP[id];S.set('skip',SKIP)}
 if(full&&cur===id){setMini(false);return}play(id,full?{full:true}:{})}
function msSermon(id){const i=I[id];if(!i||!('mediaSession' in navigator))return;navigator.mediaSession.metadata=new MediaMetadata({title:i.t,artist:teacher(i),album:where(id)});['play',()=>audio.play().catch(()=>{}),'pause',()=>audio.pause(),'seekbackward',()=>audio.currentTime-=10,'seekforward',()=>audio.currentTime+=10,'nexttrack',()=>skipTrack(1),'previoustrack',()=>skipTrack(-1)].reduce((a,v,k,arr)=>{if(k%2===0)navigator.mediaSession.setActionHandler(v,arr[k+1]);return a},0)}
function play(id,o={}){const i=I[id];if(!i.audio)return;BBM=!!o.bb;if(!o.restore)S.set('npl',{id,at:Date.now()});let wait=false;if(cur!==id){cur=id;NP().classList.toggle('reading',!!i.nar);$('.np-lab').textContent=i.nar?'Reading':'Now playing';if(!i.nar)NAR=null;ready=false;const p=i.nar?{}:prog[id]||{},saved=p.pos||0;useAudioFor(i);const meta=()=>{let st=i.s||0;if(i.nar){if(narAt)audio.currentTime=narAt;narAt=null;narRetry=0;ready=true;narMark(true);return}const L=isFinite(audio.duration)&&audio.duration>0?audio.duration:(+i.dur||Infinity);   /* some hosts report no length yet */
 if(i.sb&&isFinite(L))st=Math.max(0,L-i.sb);   /* Be Led: the prayer starts this far before the end */
 if(saved&&saved>st&&saved<L-5)audio.currentTime=saved;else if(st&&st<L-30){audio.currentTime=st;START={id,st}}ready=true};const setSrc=u=>{audio.src=u;narWait=false;audio.addEventListener('loadedmetadata',meta,{once:true})};if(!i.nar&&!i.blob)setSrc(i.audio);else if(NB[id]&&NB[id].u)setSrc(NB[id].u);else{narWait=true;wait=true;if(audio.src!==SILENT)try{audio.pause()}catch(e){}$('#cur').textContent='Loading…';narBlob(id).then(u=>{if(cur!==id)return;setSrc(u);if(!o.load)audio.play().catch(()=>{})}).catch(()=>{if(cur!==id)return;narWait=false;$('#np-s').textContent='This chapter did not load — check your connection and tap play.'})}  /* fresh plays start after the intro */
  $('#np-t').textContent=dispTitle(i);{const mb=$('#np-more');if(mb){mb.innerHTML=IC_DOTS;mb.hidden=!canShare(id)}}$('#np-s').textContent=i.nar?'\u00a0':teacher(i)+' · '+where(id);npArt(id);favPaint();if(!NP().classList.contains('on')){NP().classList.add('on');setMini(!o.full)}else if(o.full)setMini(false);if(i.nar)readerFill(true);if(i.intro){NP().classList.add('reading');const box=$('#np-read');box.innerHTML='';introText(i.intro.abbr).then(T=>{if(cur!==id)return;box.innerHTML=`<section class="itx"><h3 class="rc first">${esc(dispTitle(i))}</h3>${introParas(T[String(i.intro.c)])}</section>`}).catch(()=>{})}setPP();
  msSermon(id)}
 if(o.load||wait)return;audio.paused?audio.play().catch(()=>{}):audio.pause()}
function next(){if(inDeep()){const i=DEEP.i,ids=deepIds(i),k=ids.indexOf(cur),nx=ids.slice(k+1).find(id=>!isDone(id)&&!SKIP[id]);
  if(nx){PLAYSTOP=i;play(nx);render();return}
  const t=stopSteps(i).find(z=>z.k==='teaching'&&!isDone(z.id)&&!SKIP[z.id]);DEEP=null;
  if(t){JM=true;PLAYSTOP=i;if(jpIdx()===i)JV.deep=false;play(t.id);render();return}
  note('That is everything in Go Deeper for '+stopName(walk()[i])+'. Walk on when you’re ready.');render();return}
 if(BPM&&cur){const s=bpGet(BPM),ids=s?bpIds(s):[],k=ids.indexOf(cur);if(k>=0){if(k+1<ids.length)bpPlay(s.id,ids[k+1]);else{BPM=null;note('That is the end of '+s.title+'.')}render();return}BPM=null}
 if(cur&&I[cur].sc&&scSeq().includes(cur)){const q=scSeq();for(let j=q.indexOf(cur)+1;j<q.length;j++)if(!isDone(q[j])&&okWho(q[j])){play(q[j]);return}return}
 if(JM){const i=jpIdx(),a=nextAction(i),here=camp===i;
  if(a.kind==='play'){if(here){TAB=a.step;S.set('tab',TAB)}play(a.id);if(here){decorate.moving=true;render();decorate.moving=false}return}
  if(a.kind==='scripture'){const x=walk()[i];if(hasNar(x.b.abbr,x.c.c)){if(here){TAB='scripture';S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false}narPlay(x.b,x.c.c,0,{jm:true});return}}
  JM=false;decorate.moving=true;render();decorate.moving=false;if(a.kind==='walk')note('That is everything waiting in '+stopName(walk()[i])+'. Walk on when you’re ready.');return}
 const w=walk(),x=w[PLAYSTOP!=null?PLAYSTOP:camp];if(!x)return;const ids=orderedIds(x.b,x.c),k=ids.indexOf(cur);if(k<0)return;
 for(let j=k+1;j<ids.length;j++)if(I[ids[j]].audio&&!isDone(ids[j])&&okWho(ids[j])&&!SKIP[ids[j]]){play(ids[j]);return}}
let saveSec=-1;onAudio('timeupdate',()=>{if(!cur||narWait)return;const d=audio.duration||0,t=audio.currentTime;
 if(START){if(START.id!==cur)START=null;else if(t<START.st-1){if(!audio.seeking)audio.currentTime=START.st}else START=null}   /* the start point holds even where the first seek is dropped */{const hl=$('#np-hl i');if(hl)hl.style.width=(d?Math.min(100,100*t/d):0)+'%'}$('#seek').value=d?1000*t/d:0;$('#cur').textContent=fmt(t);$('#rem').textContent='-'+fmt(Math.max(0,d-t-tail())/speed);npLeftPaint();cutPaint();{const se=$('#np-s');if(se&&!I[cur].nar&&d){const L=' · '+Math.max(1,Math.round(Math.max(0,d-t-tail())/speed/60))+' min left';if(se.dataset.left!==L)se.dataset.left=L}}
 if(tail()&&d&&d-t<=tail()&&!audio.paused&&!audio.seeking&&ready){audio.pause();finished();return}/* the outro after the last word: done */
 if(I[cur].nar){if(!ready)return;narMark();if(BBM&&view==='bible')bbMark();if(d&&d-t<45)narPrefetch();const sec=Math.floor(t);if(sec%5===0&&sec!==saveSec){saveSec=sec;const pos=S.get('narpos',{});pos[cur]=t;S.set('narpos',pos)}return}
 if(!ready)return;const p=prog[cur]=Object.assign(prog[cur]||{},{dur:d});
 if(lastT!==null&&!audio.paused&&!audio.seeking){const dt=t-lastT;if(dt>0&&dt<4)p.heard=Math.min(d||Infinity,(p.heard||0)+dt)}lastT=t;
 const wasDone=!!p.done;if(d&&p.heard>=DONE_AT*body(cur)&&nearEnd(cur,t)){p.done=true;delete p.reopen}const nowDone=!!p.done,sec=Math.floor(t);
 if((sec%5===0&&sec!==saveSec)||nowDone!==wasDone){saveSec=sec;p.pos=t;p.at=Date.now();S.set('prog',prog);if(nowDone!==wasDone)render()}});
onAudio('seeking',()=>{lastT=null});onAudio('play',()=>{lastT=null});
function finished(){if(narWait)return;if(BBM&&cur&&I[cur].intro&&BB.q){const q=BB.q;if(q.st.length){play(q.st.shift(),{bb:true});return}BB.q=null;narPlay(q.b,q.c,0,{bb:true});return}if(cur&&I[cur].nar){narNext();return}const p=prog[cur]=Object.assign(prog[cur]||{},{pos:0});if(p.dur&&p.heard>=DONE_AT*body(cur)){p.done=true;delete p.reopen}S.set('npl',null);S.set('prog',prog);render();next()}
onAudio('ended',finished);
const setPP=()=>{$('#pp').innerHTML=icon(audio.paused?'play':'pause',28,0,'#1b2440')};setPP();/* play/pause only changes the play buttons: update them in place so the page (and an open reading) never re-lays out */
function refreshVoices(){contRefresh();if(view==='journey'||view==='bigpicture'||(view==='library'&&LT==='series')){cancelAnimationFrame(refreshVoices.r);refreshVoices.r=requestAnimationFrame(()=>{const y=scrollY;render();window.scrollTo(0,y)})}document.querySelectorAll('.pb[data-play]').forEach(b=>{const id=b.dataset.play,i=I[id],playing=String(cur)===id&&!audio.paused,deg=!isDone(id)?Math.round(3.6*heardPct(id)):0;
 b.classList.toggle('playing',playing);b.style.setProperty('--p',deg+'deg');b.innerHTML=`<span style="color:${playing?'var(--gold2)':'var(--ink)'}">${icon(playing?'pause':'play',18,0,'currentColor')}</span>`})}
onAudio('play',()=>{setPP();refreshVoices();narBar()});onAudio('pause',()=>{setPP();refreshVoices();narBar()});
$('#audiofx').addEventListener('error',()=>{if(audio!==$('#audiofx')||!cur)return;const t=audio.currentTime||0,src=audio.src;audio=$('#audio');audio.playbackRate=speed;audio.src=src;audio.addEventListener('loadedmetadata',()=>{try{audio.currentTime=t}catch(e){}},{once:true});audio.play().catch(()=>{})});
onAudio('error',()=>{if(narWait)return;if(cur&&I[cur].nar&&narRetry<3){narRetry++;const id=cur,t=audio.currentTime||narAt||0;if(NB[id]){if(NB[id].u)URL.revokeObjectURL(NB[id].u);delete NB[id]}narBlob(id).then(u=>{if(cur!==id)return;audio.src=u;audio.addEventListener('loadedmetadata',()=>{try{audio.currentTime=t}catch(e){}},{once:true});audio.play().catch(()=>{})}).catch(()=>{});return}$('#np-s').textContent=(location.protocol==='file:'||window!==window.top)?'Audio is blocked in this viewer — open in Safari from a web address.':'This file did not load.'});
$('#pp').onclick=()=>cur&&(audio.paused?audio.play().catch(()=>{}):audio.pause());$('#bk').onclick=()=>audio.currentTime-=10;$('#fw').onclick=()=>audio.currentTime+=10;
$('#seek').oninput=e=>{if(audio.duration)audio.currentTime=audio.duration*e.target.value/1000};
const setSpeed=v=>{speed=Math.round(Math.min(3,Math.max(0.5,v))*100)/100;AUDIO_EL.forEach(a=>a.playbackRate=speed);$('#spd').textContent=spdLabel();S.set('speed',speed);retime()};
function retime(){document.querySelectorAll('[data-dur]').forEach(e=>e.textContent=durTxt(+e.dataset.dur));document.querySelectorAll('[data-hrs]').forEach(e=>{const [h,a]=e.dataset.hrs.split(',').map(Number);e.textContent=hrsTxt(h,a)});if(cur&&audio.duration)$('#rem').textContent='-'+fmt(Math.max(0,audio.duration-audio.currentTime-tail())/speed);bbLeftPaint();npLeftPaint()}$('#spd').onclick=e=>{e.stopPropagation();if(NP().classList.contains('mini')){const L=[.7,.8,.9,1,1.25,1.5,1.75,2],k=L.findIndex(v=>Math.abs(v-speed)<.01);setSpeed(L[(k+1)%L.length]);return}setSpeed(1)};$('#spd-dn').onclick=e=>{e.stopPropagation();setSpeed(speed-0.05)};$('#spd-up').onclick=e=>{e.stopPropagation();setSpeed(speed+0.05)};
$('#bedb').onclick=e=>{e.stopPropagation();bedPop()};AUDIO_EL.forEach(b=>['play','pause','ended'].forEach(ev=>b.addEventListener(ev,()=>{try{bbSync()}catch(e){}})));AUDIO_EL.forEach(b=>['play','pause','ended','emptied'].forEach(ev=>b.addEventListener(ev,()=>bedSync())));
let zz=0,zzT=null;$('#cutb').onclick=e=>{e.stopPropagation();if(!cur||!I[cur]||I[cur].nar)return;const id=cur,t=Math.max(0,Math.round(audio.currentTime-1)),c=S.get('cut',{})||{},was=id in c?c[id]:undefined;c[id]=t;S.set('cut',c);cutApply();cutPaint();
 note('Will start at '+fmt(t)+' from now on');const n=$('#note');if(n){const u=document.createElement('button');u.className='note-undo';u.textContent='Undo';u.onclick=()=>{const c2=S.get('cut',{})||{};if(was===undefined)delete c2[id];else c2[id]=was;S.set('cut',c2);if(was===undefined&&id in CUT0){I[id].s=CUT0[id]}cutApply();n.classList.remove('on')};n.appendChild(u)}};
function cutPaint(){const b=$('#cutb');if(!b)return;const it=cur&&I[cur],t=audio.currentTime||0,show=!!it&&!it.nar&&!it.intro&&!/^int:/.test(cur)&&t>5&&t<1500&&Math.abs(t-(it.s||0))>4;if(b.hidden===show)b.hidden=!show}
$('#zz').onclick=()=>{const m=[0,15,30,60];zz=m[(m.indexOf(zz)+1)%m.length];$('#zz').textContent=zz?'Sleep '+zz+'m':'Sleep off';clearTimeout(zzT);if(zz)zzT=setTimeout(()=>{audio.pause();zz=0;$('#zz').textContent='Sleep off'},zz*60000)};
$('#prv').onclick=e=>{e.stopPropagation();skipTrack(-1)};$('#nxt').onclick=e=>{e.stopPropagation();skipTrack(1)};$('#np-min').onclick=e=>{e.stopPropagation();setMini(true)};$('#np-more').onclick=e=>{e.stopPropagation();if(cur)sermonMenu(cur,e.currentTarget)};$('#np-core').onclick=e=>{e.stopPropagation();const u=e.currentTarget.dataset.u;if(u==null||!cur)return;const set=coreSet();set[u]=[cur];S.set('coreSet',set);JV.deep=false;DEEP=null;note('Now Core for '+stopName(walk()[jpIdx()])+'.');corePaint();render()};$('#np-srch').onclick=e=>{e.stopPropagation();openSearch()};$('#np-fav').onclick=e=>{e.stopPropagation();if(!cur)return;const f=S.get('fav',{});if(f[cur])delete f[cur];else f[cur]=Date.now();S.set('fav',f);favPaint()};
$('#cls').onclick=e=>{e.stopPropagation();S.set('npl',null);audio.pause();audio.removeAttribute('src');audio.load();cur=null;NAR=null;document.querySelectorAll('.vs.now').forEach(e=>e.classList.remove('now'));narBar();NP().classList.remove('on');roomForPlayer();render()};
/* player sheet: swipe down or tap the page to shrink it to a bar; tap or swipe up the bar to open it */
function NP(){return $('#np')}
/* the bar is there when the app opens: the last thing played, paused where it was left */
function nplFix(){if(S.get('done2'))return;let n=0;for(const id in prog){const p=prog[id],it=I[id];if(!p||!p.done||!it||it.nar||!p.dur||!p.pos)continue;if(p.pos<p.dur-(it.e||0)-180&&p.pos>(it.s||0)+60){p.done=false;p.reopen=1;p.at=Date.now();n++}}if(n)S.set('prog',prog);S.set('done2',1)}
function nplRestore(){const n=S.get('npl',null);if(!n||!n.id||!I[n.id]||!I[n.id].audio||isDone(n.id))return;if(cur&&!audio.paused)return;if(cur===n.id)return;
 const it=I[n.id];if(it.nar){const b=D.books.find(x=>x.name===it.nar.book);if(b)narPlay(b,it.nar.c,null,{load:true,restore:true})}else play(n.id,{load:true,restore:true})}
function nplOnce(){if(nplOnce.done)return;nplOnce.done=true;try{nplRestore()}catch(e){}}
function roomForPlayer(){if(view!=='bible')document.body.classList.remove('npslim');requestAnimationFrame(()=>{const np=NP(),tb=($('#tabs')||{}).offsetHeight||0;const npOn=np.classList.contains('on')&&view!=='pray'&&view!=='worship';document.body.classList.toggle('npon',npOn&&np.classList.contains('mini'));if(!npOn){document.documentElement.style.setProperty('--npH','0px');document.body.style.paddingBottom=tb+'px';return}const mh=np.classList.contains('mini')?np.offsetHeight+16:0;document.documentElement.style.setProperty('--npH',mh+'px');document.body.style.paddingBottom=(tb+mh)+'px'})}
/* the full-screen player's cover: the passage on the teacher's colour, with their medallion mark */
const ART_C={Platt:['#1b2440','#3b5578'],PAM:['#4a1f3a','#8a3b5c'],Davey:['#1f3b33','#3f6b5a'],Skip:['#5a3417','#a8662e'],Fearless:['#2c2f36','#8a6a2a'],Vaughan:['#173a3e','#3f7a78']};
function npArt(id){const i=I[id],c=ART_C[i.who]||['#1b2440','#a8812a'],d=i.date?new Date(i.date+'T12:00:00'):null;
 $('#np-art').style.background=`linear-gradient(150deg,${c[1]},${c[0]})`;
 $('#np-art').innerHTML=`<svg class="a-m" viewBox="0 0 48 48"><path d="${MEDAL_ICON[{Platt:'apostle',PAM:'prophet',Davey:'writer',Skip:'patriarch'}[i.who]]||''}" fill="none" stroke="#fff" stroke-width="2"/></svg><div class="a-w">${esc(teacher(i))}</div><div class="a-p">${esc(where(id))}</div>${i.show?`<div class="a-s">${esc(i.show)}</div>`:''}`;
 $('#np-d').textContent=[d&&!isNaN(d)?d.toLocaleDateString('en-US',{month:'long',day:'numeric',year:'numeric'}):'',i.show||''].filter(Boolean).join(' · ')}
/* previous / next teaching along the road (manual: every teaching in order; ⏮ restarts first if you are past 5 s) */
/* the Journey as one sequence: each stop's introduction, its Scripture, its Core teaching, then the next stop.
   The player's next and back move through it (back restarts what is playing first). */
function stopSteps(i){const x=walk()[i];if(!x)return[];const st=[],ii=stopIntro(x);if(ii&&I[ii])st.push({k:'intro',id:ii});
 if(!x.c.intro&&hasNar(x.b.abbr,x.c.c))st.push({k:'scripture',id:narId(x.b.abbr,x.c.c)});
 stepsOf(i).teach.forEach(id=>{if(I[id]&&I[id].audio)st.push({k:'teaching',id})});return st}
function seqWhere(id){const i0=jpIdx(),w=walk();for(const d of [0,1,-1,2,-2]){const i=i0+d;if(i<0||i>=w.length)continue;const k=stopSteps(i).findIndex(z=>z.id===id);if(k>=0)return[i,k]}return null}
function jStep(dir){const p=seqWhere(cur);if(!p)return false;let [i,k]=p;return jWalk(i,k+dir,dir)}
function swipe(dir){const np=NP();np.classList.remove('sw-l','sw-r');void np.offsetWidth;np.classList.add(dir>0?'sw-l':'sw-r');setTimeout(()=>np.classList.remove('sw-l','sw-r'),320)}
function jWalk(i,k,dir){const w=walk();DEEP=null;JV.deep=false;
 while(i>=0&&i<w.length){const st=stopSteps(i);if(k<0){i--;if(i<0)return true;k=stopSteps(i).length-1;continue}if(k>=st.length){i++;k=0;continue}
  const z=st[k];setJP(i);JV.tabFor=null;JM=true;BPM=null;PLAYSTOP=i;const np=NP();np.classList.remove('sw-l','sw-r');void np.offsetWidth;np.classList.add(dir>0?'sw-l':'sw-r');setTimeout(()=>np.classList.remove('sw-l','sw-r'),320);
  if(z.k==='scripture'){const x=w[i];narPlay(x.b,x.c.c,0,{jm:true})}else play(z.id);if(view==='journey')render();return true}
 return true}
/* in Go Deeper, next / back move through its list; past the end comes the next Core item */
function deepStep(dir){if(!inDeep())return false;const i=DEEP.i,ids=deepIds(i),k=ids.indexOf(cur);
 if(dir<0&&audio.currentTime>5){audio.currentTime=(I[cur]&&I[cur].s)||0;return true}
 const j=k+dir;if(j>=0&&j<ids.length){setJP(i);JV.tabFor=stopKey(walk()[i]);JV.tab='teaching';JV.deep=true;JM=false;BPM=null;PLAYSTOP=i;swipe(dir);play(ids[j]);if(view==='journey')render();return true}
 const st=stopSteps(i);if(dir>0){const t=st.findIndex(z=>z.k==='teaching'&&!isDone(z.id)&&!SKIP[z.id]);swipe(1);return jWalk(t>=0?i:i+1,t>=0?t:0,1)}
 swipe(-1);return jWalk(i,st.length-1,-1)}
function skipTrack(dir){if(deepStep(dir))return;if(coreOn()&&cur&&!BPM&&!(I[cur]&&I[cur].sc&&scSeq().includes(cur))&&seqWhere(cur)){if(dir<0&&audio.currentTime>5){audio.currentTime=I[cur]&&I[cur].nar?0:((I[cur]&&I[cur].s)||0);return}if(jStep(dir))return}if(BPM&&cur&&!(I[cur]&&I[cur].nar)){const s=bpGet(BPM),ids=s?bpIds(s):[],j=ids.indexOf(cur)+dir;if(dir<0&&audio.currentTime>5){audio.currentTime=(I[cur]&&I[cur].s)||0;return}if(ids.includes(cur)){if(j>=0&&j<ids.length)bpPlay(s.id,ids[j]);return}}if(cur&&I[cur].nar&&NAR&&NAR.id===cur){narStep(dir);return}if(dir<0&&audio.currentTime>5&&cur){audio.currentTime=(I[cur]&&I[cur].s)||0;return}
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
/* The Bible Narrative: Alistair's introduction to each book (c 0) and chapter, first in its stop. Each is an item like a teaching */
const NI=D.intro||{},NTX={};
const introId=(abbr,c)=>NI[abbr]&&NI[abbr][String(c)]?'int:'+abbr+':'+c:null;
D.books.forEach(b=>Object.entries(NI[b.abbr]||{}).forEach(([c,d])=>{const id='int:'+b.abbr+':'+c;I[id]={id,t:+c?b.name+' '+c+' · Introduction':'Introducing '+b.name,who:'Narrator',by:'The Narrator',tr:'intro',dur:d,blob:1,
 audio:NRAW+'intro_'+b.abbr+'_'+String(c).padStart(3,'0')+'.mp3',intro:{abbr:b.abbr,c:+c,book:b.name}}}));
const stopIntro=x=>x&&!x.c.sec?introId(x.b.abbr,x.c.intro?0:x.c.c):null;
const ITX=D.itx||{},hasIntroText=x=>!!x&&!x.c.sec&&(ITX[x.b.abbr]||[]).includes(x.c.intro?0:x.c.c);
function introText(abbr){return NTX[abbr]||(NTX[abbr]=fetch('narrative/'+abbr+'.json').then(r=>{if(!r.ok)throw 0;return r.json()}).catch(e=>{delete NTX[abbr];throw e}))}
function introParas(t){return (t||'').split(/\n\s*\n/).map(p=>`<p>${rich(p.trim())}</p>`).join('')}
const wireNames=el=>el.querySelectorAll('[data-nk]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(b.dataset.nk,b.dataset.ns)});
function narDur(abbr,c){const n=NARR[abbr];return n&&n.d?n.d[n.c.indexOf(c)]||0:0}
/* time left in the book and the whole Bible from a chapter on, at the current speed (with the narrator's intros when they are on) */
let BBL=null;
function bbLeftIdx(){const k=BB.intros?1:0;if(BBL&&BBL.k===k)return BBL;const L=[],at={};
 D.books.forEach(b=>{const n=NI[b.abbr]||{};for(let c=1;c<=+b.n;c++){const ip=k?(+n[String(c)]||0)+(c===1?(+n['0']||0):0):0;at[b.abbr+c]=L.length;L.push({b:b.name,d:(narDur(b.abbr,c)||0)+ip,ip})}});
 const suf=new Array(L.length+1).fill(0),bk=new Array(L.length+1).fill(0);for(let i=L.length-1;i>=0;i--){suf[i]=suf[i+1]+L[i].d;bk[i]=L[i].d+(i+1<L.length&&L[i+1].b===L[i].b?bk[i+1]:0)}
 return BBL={k,at,L,suf,bk}}
function bbLeft(b,c,into){const X=bbLeftIdx(),i=X.at[b.abbr+c];if(i==null)return null;const sp=spNow(),u=into==null?0:X.L[i].ip+Math.max(0,into);return {book:Math.max(0,X.bk[i]-u)/sp,bible:Math.max(0,X.suf[i]-u)/sp}}
function leftHM(s){const m=Math.round(s/60);return m>=60?Math.floor(m/60).toLocaleString()+' h '+(m%60)+' m':Math.max(1,m)+' min'}
function leftTxt(name,L){return L?`<b>${esc(name)}</b> ${leftHM(L.book)} left<i>·</i><b>Bible</b> ${leftHM(L.bible)} left`:''}
function bbLeftPaint(){const el=$('#bbleft');if(!el)return;const p=BB.pos||bbPos(),b=bbBook(p.b);el.innerHTML=leftTxt(b.name,bbLeft(b,p.c))}
let NPL='';function npLeftPaint(){const el=$('#npleft');if(!el)return;let h='';
 if(BBM){if(NAR&&cur===NAR.id)h=leftTxt(NAR.b.name,bbLeft(NAR.b,NAR.c,audio.currentTime||0));else if(BB.q)h=leftTxt(BB.q.b.name,bbLeft(BB.q.b,BB.q.c))}
 if(h!==NPL){NPL=h;el.innerHTML=h;el.hidden=!h}}
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
/* the chapter open for reading (no sound) on the Journey screen, by stop; null when closed */
let RDO=null;
/* while reading, once the top Listen button has scrolled away, a floating one stays in reach (above the tabs and any player) */
function jrFab(){const f=document.querySelector('#jread .jr-fab'),bar=document.querySelector('#jread .jr-bar'),jr=document.querySelector('#jread');if(!f||!bar||!jr)return;
 const tb=($('#tabs')||{}).offsetHeight||0,np=$('#np'),npTop=np?np.getBoundingClientRect().top:innerHeight,occ=Math.max(tb,npTop<innerHeight?innerHeight-npTop:0);
 f.style.bottom=(occ+14)+'px';f.classList.toggle('show',bar.getBoundingClientRect().bottom<130&&jr.getBoundingClientRect().bottom>innerHeight*.55)}
addEventListener('scroll',()=>jrFab(),{passive:true});
let RD={busy:false,first:null,last:null};
function readerFill(reset){const box=$('#np-read');if(!NAR||!box)return;const key=NAR.b.abbr+NAR.c;
 if(reset&&!box.querySelector(`section[data-k="${key}"]`)){if(RD.loading===key)return;box.innerHTML='';RD={busy:true,loading:key,first:[NAR.b,NAR.c],last:[NAR.b,NAR.c]};
  readerSec(NAR.b,NAR.c,true).then(sec=>{if(RD.loading!==key)return;RD.loading=null;box.innerHTML='';box.appendChild(sec);
   RD.busy=false;narMark(true)}).catch(()=>{RD.busy=false});return}}   /* just this chapter: reading straight on is the Bible tab */
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
 if(BBM){const nx=narAfter(was.b,was.c);if(nx)bbPlayFrom(nx[0],nx[1],1);else{BBM=false;bbSync()}return}   /* from the Bible tab: on to the next chapter */
 if(JM){const x=walk()[jpIdx()];if(x&&!x.c.intro&&x.b.name===was.b.name&&x.c.c===was.c){next();return}JM=false}
 render();note(was.b.name+' '+was.c+' ✓')}   /* one chapter at a time: the Bible tab is where reading keeps going */
let fullAtScroll=0;
/* ---- a sermon's menu (the ••• by its title, or press and hold it in any list): Favorite, Share, Share from where you
   are, Copy link. A shared link opens a small page anyone can listen on (s/<id>.html), nothing of yours in it. ---- */
const IC_DOTS='<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="5" cy="12" r="1.9" fill="currentColor"/><circle cx="12" cy="12" r="1.9" fill="currentColor"/><circle cx="19" cy="12" r="1.9" fill="currentColor"/></svg>',
 IC_HEART=on=>`<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true" fill="${on?'#c0392b':'none'}" stroke="${on?'#c0392b':'currentColor'}" stroke-width="2" stroke-linejoin="round"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/></svg>`,
 IC_SHARE='<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/><path d="M7.5 7.5L12 3l4.5 4.5"/><path d="M6 11H5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-1"/></svg>',
 IC_LINK='<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>';
function canShare(id){const i=I[id];return !!(i&&i.audio&&!i.nar&&!i.intro&&!i.blob&&!i.led&&/^[\w-]+$/.test(id))}
function isFav(id){return !!S.get('fav',{})[id]}
function setFav(id,on){const f=S.get('fav',{});if(on)f[id]=Date.now();else delete f[id];S.set('fav',f);dlog(on?'favorite':'unfavorite',id);if(view==='library'){const y=scrollY;render();window.scrollTo(0,y)}}
function shareUrl(id,t){return new URL('s/'+id+'.html'+(t?'?t='+t:''),location.href.replace(/[?#].*$/,'')).href}
function copyLink(url){const ok=()=>note('Link copied'),old=()=>{const t=document.createElement('textarea');t.value=url;t.setAttribute('readonly','');t.style.cssText='position:fixed;opacity:0;top:0';document.body.appendChild(t);t.select();let done=false;try{done=document.execCommand('copy')}catch(e){}t.remove();done?ok():note(url)};
 try{navigator.clipboard.writeText(url).then(ok,old)}catch(e){old()}}
function shareSermon(id,t){const i=I[id],url=shareUrl(id,t),text=[teacher(i),i.pass].filter(Boolean).join(' · ');dlog('share',{id,from:t||0});
 if(navigator.share)navigator.share({title:dispTitle(i),text,url}).catch(e=>{if(!e||e.name!=='AbortError')copyLink(url)});else copyLink(url)}
function clock(s){s=Math.max(0,Math.floor(s));const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(x).padStart(2,'0')}
function sermonMenu(id,anchor,lift){closeSermonMenu();if(!canShare(id))return;const i=I[id],fav=isFav(id);
 const here=cur===id&&audio&&isFinite(audio.currentTime)&&audio.currentTime>(+i.s||0)+5?Math.floor(audio.currentTime):0;
 const items=[['fav',fav?'Favorited':'Favorite',IC_HEART(fav)],['share','Share sermon',IC_SHARE]].concat(here?[['here','Share from '+clock(here),IC_SHARE]]:[],[['copy','Copy link',IC_LINK]]);
 const m=document.createElement('div');m.id='smenu';m.innerHTML=`<div class="sm-bg${lift?' blur':''}"></div><div class="sm-box" role="menu" aria-label="${esc(dispTitle(i))}">${items.map(([k,t,ic])=>`<button role="menuitem" data-sm="${k}"><span>${esc(t)}</span><i>${ic}</i></button>`).join('')}</div>`;
 document.body.appendChild(m);
 if(lift){const r=lift.getBoundingClientRect(),c=lift.cloneNode(true);c.classList.add('sm-lift');c.removeAttribute('id');c.style.cssText=`left:${r.left}px;top:${r.top}px;width:${r.width}px`;m.insertBefore(c,m.lastChild)}
 const box=m.querySelector('.sm-box'),r=anchor.getBoundingClientRect(),h=box.offsetHeight,below=r.bottom+10+h<innerHeight-10;
 box.style.top=(below?r.bottom+10:Math.max(10,r.top-10-h))+'px';box.style.right=Math.max(14,innerWidth-r.right)+'px';box.style.transformOrigin=(below?'top':'bottom')+' right';
 requestAnimationFrame(()=>m.classList.add('on'));m.querySelector('.sm-bg').onclick=closeSermonMenu;
 m.querySelectorAll('[data-sm]').forEach(b=>b.onclick=e=>{e.stopPropagation();const k=b.dataset.sm;closeSermonMenu();
  if(k==='fav'){setFav(id,!fav);note(fav?'Removed from Favorites':'Added to Favorites')}else if(k==='share')shareSermon(id,0);else if(k==='here')shareSermon(id,here);else copyLink(shareUrl(id,0))})}
function closeSermonMenu(){const m=$('#smenu');if(m)m.remove()}
/* press and hold a sermon in any list (or right-click it) for the same menu; the press never also plays or opens it */
(function(){let t=null,sx=0,sy=0,fired=0;const ROW='[data-row],[data-full]',idOf=r=>r.dataset.row||r.dataset.full;
 document.addEventListener('touchstart',e=>{const r=e.target.closest&&e.target.closest(ROW);if(!r||!canShare(idOf(r))||e.target.closest('#smenu'))return;sx=e.touches[0].clientX;sy=e.touches[0].clientY;clearTimeout(t);
  t=setTimeout(()=>{t=null;fired=Date.now();try{navigator.vibrate&&navigator.vibrate(8)}catch(x){}sermonMenu(idOf(r),r,r)},480)},{passive:true});
 document.addEventListener('touchmove',e=>{if(!t)return;const p=e.touches[0];if(Math.abs(p.clientX-sx)>10||Math.abs(p.clientY-sy)>10){clearTimeout(t);t=null}},{passive:true});
 ['touchend','touchcancel'].forEach(ev=>document.addEventListener(ev,()=>{clearTimeout(t);t=null},{passive:true}));
 document.addEventListener('click',e=>{if(Date.now()-fired<700&&!(e.target.closest&&e.target.closest('#smenu'))){e.preventDefault();e.stopPropagation()}},true);
 document.addEventListener('contextmenu',e=>{const r=e.target.closest&&e.target.closest(ROW);if(!r||!canShare(idOf(r)))return;e.preventDefault();fired=Date.now();sermonMenu(idOf(r),r,r)})})();
/* Favorites: one row in the Library opens them all — searchable, sorted your way, grouped when sorted by teacher or book */
const FAV_SORTS=[['saved','Recently saved'],['teacher','Teacher'],['book','Book of the Bible'],['new','Not heard yet'],['short','Shortest first']];
function favList(){return Object.entries(S.get('fav',{})).filter(([id])=>canShare(id)).map(([id,ts])=>({id,ts}))}
function favBook(id){const m=/^((?:[123]\s)?[A-Za-z][A-Za-z ]*?)\s*\d/.exec(I[id].pass||'');return m?m[1].trim():''}
function openFavs(){let q='',sort=S.get('favsort','saved');if(!FAV_SORTS.some(s=>s[0]===sort))sort='saved';
 const bix=b=>{const k=D.books.findIndex(x=>x.name===b);return k<0?999:k},ch=id=>+((/(\d+)/.exec((I[id].pass||'').replace(/^[123]\s/,''))||[])[1]||0);
 const match=x=>{if(!q)return true;const i=I[x.id],s=[dispTitle(i),i.t,teacher(i),i.pass,i.show].filter(Boolean).join(' ').toLowerCase();return q.toLowerCase().split(/\s+/).filter(Boolean).every(w=>s.includes(w))};
 const BY={saved:(a,b)=>b.ts-a.ts,teacher:(a,b)=>teacher(I[a.id]).localeCompare(teacher(I[b.id]))||b.ts-a.ts,book:(a,b)=>bix(favBook(a.id))-bix(favBook(b.id))||ch(a.id)-ch(b.id)||b.ts-a.ts,
  new:(a,b)=>(isDone(a.id)?1:0)-(isDone(b.id)?1:0)||b.ts-a.ts,short:(a,b)=>(+I[a.id].dur||1e9)-(+I[b.id].dur||1e9)||b.ts-a.ts};
 const shown=()=>favList().filter(match).sort(BY[sort]);
 const list=()=>{const L=shown(),N=favList().length,grp=sort==='teacher'?x=>teacher(I[x.id]):sort==='book'?x=>favBook(x.id)||'Other':null;let h='',last=null;
  if(!L.length)return `<p class="fav-none">${N?'No favorite matches “'+esc(q)+'”.':'No favorites yet. Tap ••• on a sermon, then Favorite.'}</p>`;
  L.forEach(x=>{if(grp){const g=grp(x);if(g!==last){h+=`<div class="fav-g">${esc(g)}</div>`;last=g}}h+=voiceHTML(x.id)});return h};
 const head=`<div class="fav-h"><span class="fav-av">${IC_HEART(true).replace(/19/g,'22')}</span><span><b class="serif">Favorites</b><small id="favc"></small></span></div>
<label class="fav-q">${'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>'}<input id="favq" type="search" placeholder="Search your favorites" autocomplete="off" enterkeyhint="search" aria-label="Search your favorites"></label>
<div class="fav-bar"><span id="favn"></span><label class="fav-sort">Sort: <span id="favsl">${FAV_SORTS.find(s=>s[0]===sort)[1]}</span> ⌄<select id="favs" aria-label="Sort favorites">${FAV_SORTS.map(([k,l])=>`<option value="${k}"${k===sort?' selected':''}>${l}</option>`).join('')}</select></label></div>`;
 openListSheet('Favorites',head,list,(el,refresh)=>{const qi=el.querySelector('#favq'),ss=el.querySelector('#favs'),N=favList().length;
  el.querySelector('#favc').textContent=N+' sermon'+(N===1?'':'s');el.querySelector('#favn').textContent=q?shown().length+' of '+N:'';
  qi.oninput=()=>{q=qi.value.trim();refresh()};ss.onchange=()=>{sort=ss.value;S.set('favsort',sort);el.querySelector('#favsl').textContent=FAV_SORTS.find(s=>s[0]===sort)[1];refresh()}})}

/* teaching you mark as particularly valuable: kept in the Library under Saved */
function corePaint(){const b=$('#np-core');if(b)b.hidden=true;return;   /* Make Core is no longer offered */
 let ok=false;
 if(coreOn()&&cur&&I[cur]&&!I[cur].nar){const x=walk()[jpIdx()],uk=x?coreKey(x):null;ok=uk!=null&&deepIds(jpIdx()).includes(cur);if(ok)b.dataset.u=String(uk)}b.hidden=!ok}
function favPaint(){corePaint();const b=$('#np-fav');if(b)b.hidden=true;return;   /* the bookmark is no longer offered */
 if(!b)return;const it=I[cur],ok=it&&!it.nar&&!it.blob;b.hidden=!ok;const on=ok&&!!S.get('fav',{})[cur];b.classList.toggle('on',on);b.setAttribute('aria-pressed',on);b.setAttribute('aria-label',on?'Saved: tap to remove':'Save this teaching')}
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
 np.addEventListener('click',e=>{if(e.target.closest('input')||e.target.closest('button'))return;if(Date.now()-(+np.dataset.swiped||0)<500)return;if(np.classList.contains('mini')){if(document.body.classList.contains('npslim')){document.body.classList.remove('npslim');return}setMini(false)}else if(e.target.closest('.grab'))setMini(true)});
 document.addEventListener('click',e=>{if(np.classList.contains('on')&&!np.classList.contains('mini')&&!np.contains(e.target))setMini(true)},true);
 addEventListener('scroll',()=>{if(np.classList.contains('on')&&!np.classList.contains('mini')&&Math.abs(scrollY-fullAtScroll)>60)setMini(true)},{passive:true});
})();
/* wiring */
function wire(){if(view==='settings'&&!PL.list)plLoad().then(()=>{if(view==='settings')render()});document.querySelectorAll('.settings [data-pradd]').forEach(b=>b.onclick=()=>prPick(()=>{if(view==='settings')render()}));document.querySelectorAll('.settings [data-prrm]').forEach(b=>b.onclick=()=>{if(confirm(bkOn()?'Remove all prayer music from this phone and from your backup?':'Remove all prayer music from this phone?'))prRemoveAll().then(()=>mbRemoveAll().catch(()=>{})).then(()=>render())});document.querySelectorAll('.clearing [data-nk]').forEach(b=>b.onclick=e=>{e.stopPropagation();openSheet(b.dataset.nk,b.dataset.ns)});
 document.querySelectorAll('details[data-k]').forEach(d=>d.ontoggle=()=>{d.open?OPEN.add(d.dataset.k):OPEN.delete(d.dataset.k);if(d.classList.contains('readx'))fillReaders()});
 fillReaders();fillMapTab();
 document.querySelectorAll('.pref').forEach(b=>b.onclick=e=>{e.stopPropagation();const x=walk()[camp];const r=versesFor(b.dataset.pass,x.b.name,x.c.c);
  HL=r?{book:x.b.name,ch:x.c.c,...r}:null;TAB='scripture';S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false;
  const d=document.querySelector('details.readx');if(d)setTimeout(()=>d.scrollIntoView({behavior:'smooth',block:'start'}),60)});
 const bh=$('#bookhd');if(bh)bh.onclick=()=>{if(view!=='walk'){view='walk';S.set('view',view)}go(+bh.dataset.camp)};document.querySelectorAll('[data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();playRow(b.dataset.play,false)});
 document.querySelectorAll('[data-row]').forEach(r=>r.onclick=e=>{if(e.target.closest('button,a'))return;playRow(r.dataset.row,true)});
 document.querySelectorAll('[data-full]').forEach(b=>b.onclick=e=>{e.stopPropagation();playRow(b.dataset.full,true)});
 
 document.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>{const was=!!read[b.dataset.read];read[b.dataset.read]=!was;S.set('read',read);decorate.moving=true;render();decorate.moving=false});
 document.querySelectorAll('.acts [data-camp]').forEach(b=>b.onclick=()=>{decorate.more=false;stepTo(+b.dataset.camp)});document.querySelectorAll('.nv[data-camp], .myplace[data-camp]').forEach(b=>b.onclick=()=>{decorate.more=false;go(+b.dataset.camp)});
 const ct2=$('#cont');if(ct2)ct2.onclick=e=>{e.stopPropagation();doCont({full:!e.target.closest('.cont-ic')})};const sh=$('#sethere');if(sh)sh.onclick=e=>{e.stopPropagation();setJP(camp);note(stopName(walk()[camp])+' is your place now.');setView('journey')};const tj=$('#tojourney');if(tj)tj.onclick=e=>{e.stopPropagation();setView('journey')};
 document.querySelectorAll('[data-skipnext]').forEach(b=>b.onclick=e=>{e.stopPropagation();SKIP[b.dataset.skipnext]=true;S.set('skip',SKIP);const a=nextAction(camp);if(a&&a.step)TAB=a.step;decorate.moving=true;render();decorate.moving=false});document.querySelectorAll('.lk[data-lk]').forEach(t=>t.onclick=e=>{e.stopPropagation();if(LK===t.dataset.lk)return;LK=t.dataset.lk;S.set('lk2',LK);decorate.more=false;decorate.moving=true;render();decorate.moving=false});document.querySelectorAll('.tab[data-tab]').forEach(t=>t.onclick=e=>{e.stopPropagation();if(TAB===t.dataset.tab)return;TAB=t.dataset.tab;S.set('tab',TAB);decorate.moving=true;render();decorate.moving=false});const uf=$('#unfold');if(uf)uf.onclick=e=>{e.stopPropagation();const f=$('#fold');if(f)f.onclick()};const fd=$('#fold');if(fd){fd.onclick=e=>{e&&e.stopPropagation();const f=!FOLD;FOLD=f;if(f&&NP().classList.contains('on'))setMini(true);decorate.moving=true;render();decorate.moving=false;
   /* folding while scrolled down inside a long stop: keep the stop's top in view instead of the page jumping */
   const cl=$('#clearing');if(cl){const t=cl.getBoundingClientRect().top;if(t<60||t>innerHeight-120)window.scrollTo({top:scrollY+t-70})}};const ct=$('#chT');if(ct){ct.onclick=e=>{e.stopPropagation();openJump('browse')};ct.setAttribute('role','button');ct.setAttribute('aria-label','Choose a chapter')}}
 const mo=$('#more');if(mo)mo.onclick=()=>{decorate.more=true;decorate.moving=true;render();decorate.moving=false};
 const g=$('#gear');g.onclick=()=>setView(view==='settings'?PREV:'settings');document.querySelectorAll('[data-settings]').forEach(b=>b.onclick=()=>setView('settings'));document.querySelectorAll('[data-srch]').forEach(b=>b.onclick=()=>openSearch());
 const back=$('#back');if(back)back.onclick=()=>setView(PREV==='settings'?'journey':PREV);const us=$('#unskip');if(us)us.onclick=()=>{SKIP={};S.set('skip',SKIP);note('Everything you skipped is waiting again where it belongs.');render()};
 const osc=$('#opensc');if(osc)osc.onclick=()=>{view='sc';S.set('view',view);render();window.scrollTo(0,0)};
 const scb=$('#scback');if(scb)scb.onclick=()=>{LT='series';S.set('libtab',LT);setView('library')};
 document.querySelectorAll('details.sce').forEach(d=>d.ontoggle=()=>{d.open?OPEN.add(d.dataset.sck):OPEN.delete(d.dataset.sck)});const ord=$('#ord');if(ord)ord.onclick=()=>{cfg.order=cfg.order==='narr'?'canon':'narr';S.set('cfg',cfg);render()};const lvb=$('#lvl');if(lvb)lvb.onclick=()=>{S.set('level',!levelOn());render()};document.querySelectorAll('[data-cpref]').forEach(b=>b.onclick=()=>{const k=b.dataset.cpref;if(k==='off')cfg.core=false;else{cfg.core=true;cfg.corePref=k}S.set('cfg',cfg);render()});
 const cr=$('#corereset');if(cr)cr.onclick=()=>{S.set('coreSet',{});render()};
 const wh=$('#who');if(wh)wh.onclick=()=>{const order=['','Platt','PAM','Davey','Skip','Vaughan','Fearless'].filter(k=>!HIDE.includes(k));cfg.who=order[(order.indexOf(cfg.who)+1)%order.length];S.set('cfg',cfg);render()};
 const io=$('#io');if(io){$('#exp').onclick=()=>io.value=JSON.stringify({prog,read,cfg});$('#imp').onclick=()=>{try{const v=JSON.parse(io.value);prog=v.prog||prog;read=v.read||read;S.set('prog',prog);S.set('read',read);render()}catch(e){io.value='Could not read that JSON.'}};
  const bkf=$('#bkf');if(bkf)bkf.onsubmit=async e=>{e.preventDefault();const key=$('#bkkey').value.trim(),repo=$('#bkrepo').value.trim().replace(/^https?:\/\/github\.com\//,'').replace(/\.git$|\/$/g,''),msg=$('#bkmsg');msg.textContent='Checking…';
   try{const r=await bkGH('',{},key,repo);if(r.status===401)throw 'GitHub did not accept that key.';if(r.status===404)throw 'Could not open '+repo+' with that key: check the repo exists and the key was given access to it.';if(!r.ok)throw 'GitHub said '+r.status+'.';
    const j=await r.json();if(!j.private&&!confirm(repo+' is public: anyone could see your listening history. Use it anyway?'))throw 'Make the repo private, then try again.';
    if(j.permissions&&!j.permissions.push)throw 'That key can read the repo but not save to it: give it Contents: Read and write.';
    S.set('bkkey',key);S.set('bkrepo',repo);BK.sha=null;BK.err='';S.set('bkerr','');bkDot();try{ptLoad()}catch(e){}
    msg.textContent='Syncing…';await bkSync('open');mbSync(true);location.reload()}catch(err){msg.textContent=typeof err==='string'?err:'Could not reach GitHub. Check your connection.'}};
  const bkn=$('#bknow');if(bkn)bkn.onclick=async()=>{localStorage.setItem('sc:bkdirty','1');$('#bkst').textContent='Backing up…';await bkSave()};
  const bkr=$('#bkrest');if(bkr)bkr.onclick=async()=>{try{const d=await bkFetch();if(!d||!d.data){alert('No backup yet.');return}if(confirm('Replace this phone\'s progress with the backup from '+new Date(d.at).toLocaleString()+'?')){bkApply(d.data);location.reload()}}catch(e){alert('Could not reach the backup.')}};
  const bko=$('#bkoff');if(bko)bko.onclick=()=>{if(confirm('Stop backing up? The backups already saved stay in your repo.')){localStorage.removeItem('sc:bkkey');try{ptLoad()}catch(e){}localStorage.removeItem('sc:bkerr');BK.err='';bkDot();render()}};
  $('#reset').onclick=()=>{if(confirm(bkOn()?'Erase all progress? This also clears it on your other devices that sync.':'Erase all progress on this device?')){prog={};read={};camp=null;S.set('prog',prog);S.set('read',read);S.set('camp',null);render()}};
  $('#atest').onclick=()=>{const o=$('#atest-out');o.textContent=' testing…';const a=new Audio();a.src=Object.values(I).find(i=>i.audio).audio;a.addEventListener('loadedmetadata',()=>o.textContent=' ✓ streams ('+fmt(a.duration)+')');a.addEventListener('error',()=>o.textContent=' ✗ blocked here');a.load()}}}
decorate.first=true;render();let lastW=innerWidth;window.addEventListener('resize',()=>{if(innerWidth===lastW)return;lastW=innerWidth;decorate.first=true;render()});
/* sync: on opening, on coming back to the app, every 2 minutes while it is open, and on leaving it */
setInterval(()=>{if(bkOn()&&document.visibilityState==='visible'&&Date.now()-BK.tried>110e3)bkSync('pull')},30e3);
document.addEventListener('visibilitychange',()=>{if(!bkOn())return;if(document.visibilityState==='hidden'){if(bkDue())bkSync('save')}else if(Date.now()-BK.tried>20e3)bkSync('open')});
setTimeout(()=>{bkDot();if(bkOn())bkSync('open')},1500);
/* keep the screen on while it is being read from (Guided prayer) or played from (a Worship song chart).
   The phone's own wake lock where it works; and, since home-screen apps on older iPhones ignore it, a tiny silent,
   muted video loop (the usual way to keep an iPhone awake). Off as soon as you leave those screens. */
const AWAKE={why:new Set(),lock:null,vid:null};
function awakeVid(on){let v=AWAKE.vid;if(!v){if(!on)return;v=AWAKE.vid=document.createElement('video');v.muted=true;v.defaultMuted=true;v.loop=true;v.playsInline=true;v.setAttribute('playsinline','');v.setAttribute('muted','');v.setAttribute('aria-hidden','true');
  v.style.cssText='position:fixed;left:0;bottom:0;width:1px;height:1px;opacity:0.01;pointer-events:none;z-index:-1';v.src='data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAZ1bW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAB9AAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAwAAApp0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAB9AAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAABAAAAAQAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAfQAAAAAAABAAAAAAISbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAoAAAAUABVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABvW1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAAX1zdGJsAAAAuXN0c2QAAAAAAAAAAQAAAKlhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAABAAEABIAAAASAAAAAAAAAABFUxhdmM2MC4zMS4xMDIgbGlieDI2NAAAAAAAAAAAAAAAGP//AAAAL2F2Y0MBQsAe/+EAFmdCwB7ZHsBEAAADAAQAAAMAKDxYuSABAAZoy4BlLIAAAAAQcGFzcAAAAAEAAAABAAAAFGJ0cnQAAAAAAAALWAAAC1gAAAAYc3R0cwAAAAAAAAABAAAACgAACAAAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAAAAEAAAABAAAAAQAAAAEAAAA8c3RzegAAAAAAAAAAAAAACgAAAoMAAAAKAAAACgAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAA4c3RjbwAAAAAAAAAKAAAGugAACUUAAAlXAAAJZQAACXYAAAmDAAAJlAAACaEAAAmyAAAJwwAAAwV0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAACAAAAAAAAB9AAAAAAAAAAAAAAAAEBAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAfQAAAEAAABAAAAAAJ9bWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAfQAAAQoBVxAAAAAAALWhkbHIAAAAAAAAAAHNvdW4AAAAAAAAAAAAAAABTb3VuZEhhbmRsZXIAAAACKG1pbmYAAAAQc21oZAAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAAB7HN0YmwAAAB+c3RzZAAAAAAAAAABAAAAbm1wNGEAAAAAAAAAAQAAAAAAAAAAAAEAEAAAAAAfQAAAAAAANmVzZHMAAAAAA4CAgCUAAgAEgICAF0AVAAAAAAAfQAAAAT8FgICABRWIVuUABoCAgAECAAAAFGJ0cnQAAAAAAAAfQAAAAT8AAAAgc3R0cwAAAAAAAAACAAAAEAAABAAAAAABAAACgAAAAHxzdHNjAAAAAAAAAAkAAAABAAAAAQAAAAEAAAACAAAAAgAAAAEAAAAEAAAAAQAAAAEAAAAFAAAAAgAAAAEAAAAGAAAAAQAAAAEAAAAHAAAAAgAAAAEAAAAIAAAAAQAAAAEAAAAJAAAAAgAAAAEAAAALAAAAAQAAAAEAAABYc3RzegAAAAAAAAAAAAAAEQAAABUAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAAAAEAAAAPHN0Y28AAAAAAAAACwAABqUAAAk9AAAJTwAACWEAAAluAAAJfwAACYwAAAmdAAAJqgAACbsAAAnMAAAAGnNncGQBAAAAcm9sbAAAAAIAAAAB//8AAAAcc2JncAAAAAByb2xsAAAAAQAAABEAAAABAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExhdmY2MC4xNi4xMDAAAAAIZnJlZQAAAzNtZGF03gIATGF2YzYwLjMxLjEwMgACMEAOAAACcAYF//9s3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NCByMzEwOCAzMWUxOWY5IC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyMyAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTAgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MToweDExMSBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MCBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0wIHdlaWdodHA9MCBrZXlpbnQ9MjUwIGtleWludF9taW49NSBzY2VuZWN1dD00MCBpbnRyYV9yZWZyZXNoPTAgcmNfbG9va2FoZWFkPTQwIHJjPWNyZiBtYnRyZWU9MSBjcmY9NTEuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBzdGVwPTQgaXBfcmF0aW89MS40MCBhcT0xOjEuMDAAgAAAAAtliIQEfJigACCfgAEYIAcBGCAHAAAABkGaOAj6gAEYIAcBGCAHAAAABkGaVAI+oAEYIAcAAAAFQZpgEfUBGCAHARggBwAAAAVBmoAR9QEYIAcAAAAFQZqgEfUBGCAHARggBwAAAAVBmsAR9QEYIAcAAAAFQZrgEfUBGCAHARggBwAAAAVBmwAQ9QEYIAcBGCAHAAAABUGbID/UARggBw==';document.body.appendChild(v)}
 if(on){if(v.paused){const q=v.play();if(q&&q.catch)q.catch(()=>{AWAKE.pend=true})}}else if(!v.paused)v.pause()}
function awakeSync(){const want=AWAKE.why.size>0&&document.visibilityState==='visible';AWAKE.on=want;
 if(want){try{if(navigator.wakeLock&&navigator.wakeLock.request&&!AWAKE.lock){AWAKE.lock='asking';navigator.wakeLock.request('screen').then(l=>{AWAKE.lock=l;l.addEventListener('release',()=>{AWAKE.lock=null})},()=>{AWAKE.lock=null})}}catch(e){AWAKE.lock=null}awakeVid(true)}
 else{try{if(AWAKE.lock&&AWAKE.lock.release)AWAKE.lock.release().catch(()=>{})}catch(e){}AWAKE.lock=null;awakeVid(false)}}
function awakeSet(why,on){const had=AWAKE.why.has(why);if(on)AWAKE.why.add(why);else AWAKE.why.delete(why);if(had!==!!on)awakeSync()}
document.addEventListener('visibilitychange',()=>{AWAKE.lock=null;awakeSync()});
['touchend','click'].forEach(ev=>document.addEventListener(ev,()=>{if(AWAKE.pend&&AWAKE.why.size){AWAKE.pend=false;awakeVid(true)}},true));
{const r0=render;render=function(){if(r0.boot&&!render.boot)render.boot=r0.boot;const o=r0.apply(this,arguments);try{awakeSet('pray',view==='pray'&&PR.mode==='guided');awakeSet('song',view==='worship'&&!!WS.song&&!WS.edit)}catch(e){}return o};Object.keys(r0).forEach(k=>{render[k]=r0[k]})}   /* the original keeps its own markers (render.boot) */
try{awakeSet('pray',view==='pray'&&PR.mode==='guided')}catch(e){}
/* home-screen app: offline shell + keep progress from being evicted */
if('serviceWorker' in navigator&&isSecureContext)navigator.serviceWorker.register('sw.js').catch(()=>{});
/* pick up new versions: check on open and whenever the app comes back to the front */
/* A newer build: the app opens from the phone's copy at once, and the new one is fetched in the background; it takes
   over when nothing is playing (never mid-prayer) — at once if the app has only just opened, else when you put it away */
const APPV=__VERSION__,UPD={ready:null,tap:0,t0:Date.now()};
(function(){try{const n=performance.getEntriesByType('navigation')[0]||{};dlog('open',{from:navigator.serviceWorker&&navigator.serviceWorker.controller?'app copy (service worker)':'network',fetch_ms:Math.round((n.responseEnd||0)-(n.startTime||0)),ready_ms:Math.round(n.domContentLoadedEventEnd||performance.now()),bytes:n.transferSize,v:APPV})}catch(e){}
 ['ledm','medm','lpm','bedm','praym','audio'].forEach(id=>{const a=document.getElementById(id);if(!a)return;let pg=0;
  const say=ev=>{let h='';try{const u=a.currentSrc||a.src||'';h=u.startsWith('blob:')?'blob':u.startsWith('data:')?'silence':u?new URL(u).host:''}catch(e){}
   const b=a.buffered&&a.buffered.length?Math.round(a.buffered.end(a.buffered.length-1)):null;
   dlog(id+' '+ev,{at:Math.round(a.currentTime*10)/10,host:h,ready:a.readyState,net:a.networkState,buf:b,err:a.error?a.error.code:undefined,vol:id==='bedm'&&window.BED&&BED.g?Math.round(BED.g.gain.value*100)/100:undefined,ctx:id==='bedm'&&window.BED&&BED.ctx?BED.ctx.state:undefined})};
  ['loadstart','loadedmetadata','canplay','playing','waiting','stalled','pause','ended','error','emptied','abort'].forEach(ev=>a.addEventListener(ev,()=>say(ev)));
  a.addEventListener('progress',()=>{const n=Date.now();if(n-pg>4000){pg=n;say('progress')}})})})();document.addEventListener('pointerdown',()=>{UPD.tap=Date.now()},true);
function anyPlaying(){return ['audio','audiofx','praym','ledm','medm','lpm','bedm'].some(i=>{const a=document.getElementById(i);return a&&!a.paused})}
function updGo(){if(!UPD.ready)return;let k='';try{k=sessionStorage.getItem('sc:rl')}catch(e){}if(k===UPD.ready)return;try{sessionStorage.setItem('sc:rl',UPD.ready)}catch(e){}location.replace(location.pathname+'?v='+UPD.ready)}
function updMaybe(){if(!UPD.ready||anyPlaying())return;if(document.hidden||(Date.now()-UPD.t0<4000&&Date.now()-UPD.tap>4000))updGo()}
function checkV(){fetch('version.txt?'+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.text():'').then(t=>{if(!(+t>APPV)||UPD.ready===t)return;
  fetch('index.html?sw-refresh='+t,{cache:'no-store'}).then(r=>{if(r.ok){UPD.ready=t;updMaybe()}}).catch(()=>{})}).catch(()=>{})}
checkV();document.addEventListener('visibilitychange',()=>{if(document.hidden)updMaybe();else checkV()});
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
