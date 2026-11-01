"""People, places and the map for the app (out/site/atlas.json), and name links inside summaries.

Profiles come from data/people/profiles/*.json (written to the house rules), joined with who-appears-where data
(Theographic Bible Metadata, CC BY-SA 4.0) and the map base (Natural Earth, public domain).
A name in a summary links only to a person or place that actually appears in that chapter (or, for a book's
overview, in that book), so shared names (Mary, James, Zechariah) resolve to the right one.
Link token inside text: ⟦p:slug|Shown text⟧ (person) or ⟦l:slug|Shown text⟧ (place).
"""
import glob, json, os, re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data", "people")
NEVER_LINK = {"God", "Lord", "LORD", "Spirit", "Holy Spirit", "Christ", "Messiah", "Son", "King", "Father"}
TRIBAL = {"Israel", "Judah", "Ephraim", "Manasseh", "Benjamin", "Levi", "Dan", "Gad", "Asher", "Reuben", "Simeon",
          "Issachar", "Zebulun", "Naphtali", "Joseph", "Edom", "Moab", "Ammon", "Aram", "Esau", "Jacob", "Ishmael", "Midian"}

def _load(pattern):
    out = {}
    for f in sorted(glob.glob(os.path.join(D, "profiles", pattern))):
        try:
            out.update(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print("atlas: skipped", os.path.basename(f), e)
    return out

class Atlas:
    def __init__(self):
        self.ok = os.path.exists(os.path.join(D, "people.json"))
        if not self.ok:
            return
        self.src_p = json.load(open(os.path.join(D, "people.json"), encoding="utf-8"))
        self.src_l = json.load(open(os.path.join(D, "places.json"), encoding="utf-8"))
        self.chap = json.load(open(os.path.join(D, "chapters.json"), encoding="utf-8"))
        self.prof_p = {s: v for s, v in _load("people_*.json").items() if not v.get("skip") and v.get("who")}
        self.prof_l = {s: v for s, v in _load("places_*.json").items() if not v.get("skip") and v.get("what")}
        self.mean = {}
        for f in sorted(glob.glob(os.path.join(D, "meanings", "*.json"))):
            try: self.mean.update(json.load(open(f, encoding="utf-8")))
            except Exception as e: print("atlas: skipped", os.path.basename(f), e)
        base = os.path.join(HERE, "data", "map", "base.json")
        self.map = json.load(open(base)) if os.path.exists(base) else None
        self.ok = bool(self.prof_p or self.prof_l)
        book_count = defaultdict(Counter)
        for key, d in self.chap.items():
            b = key.rsplit(" ", 1)[0]
            for s in d["pe"]: book_count[b]["p:" + s] += 1
            for s in d["pl"]: book_count[b]["l:" + s] += 1
        self.book_top = {b: [k for k, _ in c.most_common(60)] for b, c in book_count.items()}

    # ---------- names ----------
    def _names(self, kind, slug):
        prof = (self.prof_p if kind == "p" else self.prof_l).get(slug)
        if not prof:
            return []
        if not hasattr(self, "_primary"):  # a name that is some other entry's main name is never used as an alias
            self._primary = Counter(v.get("name") for v in list(self.prof_p.values()) + list(self.prof_l.values()))
        aka = [a for a in (prof.get("aka") or []) if a and self._primary.get(a.strip(), 0) == 0]
        names = [prof.get("name")] + aka
        return [n for n in dict.fromkeys(n.strip() for n in names if n) if n not in NEVER_LINK and len(n) > 1]

    def _annotate(self, text, cands, book):
        if not text or not cands:
            return text
        table = []  # (name, kind, slug, weight)
        for w, key in enumerate(cands):
            kind, slug = key.split(":", 1)
            for n in self._names(kind, slug):
                if n in TRIBAL and book != "Genesis" and kind == "p":
                    continue  # outside Genesis these words almost always mean the tribe or nation
                table.append((n, kind, slug, w))
        table.sort(key=lambda t: (-len(t[0]), t[3]))   # longest names first, then the most present in the chapter
        taken, used, out = [], set(), []
        for n, kind, slug, _ in table:
            if (kind, slug) in used:
                continue
            for m in re.finditer(r"(?<![\w'’])" + re.escape(n) + r"(?![\w])", text):
                a, b = m.span()
                if any(a < y and x < b for x, y in taken):
                    continue
                taken.append((a, b)); used.add((kind, slug)); out.append((a, b, kind, slug))
                break
        for a, b, kind, slug in sorted(out, reverse=True):
            text = text[:a] + f"⟦{kind}:{slug}|{text[a:b]}⟧" + text[b:]
        return text

    def link_chapter(self, text, book, ch):
        d = self.chap.get(f"{book} {ch}", {"pe": [], "pl": []})
        cands = ["p:" + s for s in d["pe"] if s in self.prof_p] + ["l:" + s for s in d["pl"] if s in self.prof_l]
        return self._annotate(text, cands, book)

    def link_book(self, text, book):
        cands = [k for k in self.book_top.get(book, []) if (k[2:] in (self.prof_p if k[0] == "p" else self.prof_l))]
        return self._annotate(text, cands, book)

    # ---------- the file the app loads on first tap ----------
    def data(self):
        def where(chs):
            return {"nc": len(chs), "first": f"{chs[0][0]} {chs[0][1]}" if chs else "", "last": f"{chs[-1][0]} {chs[-1][1]}" if chs else ""}
        P = {}
        for s, v in self.prof_p.items():
            src = self.src_p.get(s, {})
            fam = {}
            for k, items in (v.get("family") or {}).items():
                row = []
                for it in items:
                    if it in self.src_p:
                        row.append({"s": it if it in self.prof_p else "", "n": (self.prof_p.get(it) or {}).get("name") or self.src_p[it]["n"]})
                    else:
                        row.append({"s": "", "n": it})
                if row: fam[k] = row
            m = self.mean.get(s, {})
            P[s] = {"n": v["name"], "who": v["who"], "key": v.get("key", []), "fam": fam, **where(src.get("ch", [])),
                    **({"mean": m["meaning"]} if m.get("meaning") else {}), **({"why": m["why"]} if m.get("why") else {})}
        L = {}
        pr = self.map["proj"] if self.map else None
        for s, v in self.prof_l.items():
            src = self.src_l.get(s, {})
            pos = {}
            if pr and src.get("lat") is not None:
                pos = {"x": round((src["lon"] - pr["lon0"]) * pr["kx"], 2), "y": round((pr["lat1"] - src["lat"]) * pr["ky"], 2)}
            m = self.mean.get(s, {})
            L[s] = {**({"mean": m["meaning"]} if m.get("meaning") else {}), **({"why": m["why"]} if m.get("why") else {}), "n": v["name"], "what": v["what"], "today": v.get("today", ""), "key": v.get("key", []), **pos, **where(src.get("ch", []))}
        here = {k: [s for s in d["pl"] if s in L and "x" in L[s]][:8] for k, d in self.chap.items()}
        base = {k: v for k, v in (self.map or {}).items() if k not in ("journey", "paul")} or None
        return {"p": P, "l": L, "map": base, "here": {k: v for k, v in here.items() if v}, "trip": self.trip(pr) if pr else None}

    def trip(self, pr):
        """The journey map's legs (journey.py) with each stop placed on the map."""
        import journey
        def xy(lon, lat): return [round((lon - pr["lon0"]) * pr["kx"], 2), round((pr["lat1"] - lat) * pr["ky"], 2)]
        def place(slug):
            src = self.src_l.get(slug)
            if not src or src.get("lat") is None:
                raise SystemExit(f"journey: place {slug} has no position")
            return xy(src["lon"], src["lat"]), (self.prof_l.get(slug) or {}).get("name") or src["n"]
        legs = []
        for leg in journey.LEGS:
            stops = []
            for slug, book, ch, beat, o in leg["stops"]:
                (x, y), name = place(slug)
                stops.append({"x": x, "y": y, "n": o.get("lab") or name, "sl": slug if slug in self.prof_l else "", "b": book, "c": ch,
                              "beat": beat, "t": o.get("t", "a"), **({"np": 1} if o.get("np") else {})})
            home = place(leg["home"]) if leg.get("home") else None
            legs.append({"t": leg["t"], "s": leg["s"], "stops": stops, **({"home": [*home[0], home[1]]} if home else {})})
        bl = {b: (v if isinstance(v, list) else [(1, v)]) for b, v in journey.BOOK_LEG.items()}
        notes = {b: ([*place(s)[0], place(s)[1]] if s else None, line) for b, (s, line) in journey.NOTES.items()}
        reg = [[n, *xy(lon, lat), list(r) if r is not None else None] for n, lon, lat, r in journey.REGIONS]
        seas = [[n, *xy(lon, lat)] for n, lon, lat in journey.SEAS]
        return {"legs": legs, "bl": bl, "notes": notes, "follow": sorted(journey.FOLLOW), "reg": reg, "seas": seas}
