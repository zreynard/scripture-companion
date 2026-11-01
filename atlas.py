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
NEVER_LINK = {"God", "Lord", "LORD", "the LORD", "the Lord", "LORD God", "Lord God", "God Almighty", "the Most High", "Yahweh", "Spirit", "Holy Spirit", "Christ", "Messiah", "Son", "King", "Father"}
# medallions: a few people get their own emblem; everyone else shows their role's
SPECIAL = {"jesus_905": "christ", "noah_2210": "ark", "joseph_1710": "coat", "moses_2108": "tablets", "adam_78": "tree",
           "eve_1231": "tree", "ruth_2450": "sheaf", "john_1676": "wave", "god_1324": "god", "holy_spirit_7400": "dove"}
SPECIAL_LABEL = {"god": "God", "dove": "The Holy Spirit", "christ": "The Messiah"}
ROLE_LABEL = {"patriarch": "Patriarch", "matriarch": "Matriarch", "king": "King", "queen": "Queen", "ruler": "Ruler", "official": "Official",
              "prophet": "Prophet", "priest": "Priest", "levite": "Levite", "judge": "Judge", "warrior": "Warrior", "apostle": "Apostle",
              "writer": "Writer", "faithful": "Faithful", "shepherd": "Shepherd", "craftsman": "Craftsman", "servant": "Servant",
              "angel": "Angel", "family": "Family line", "false_god": "False god", "people": "People group", "christ": "The Messiah"}
REF_SPAN = re.compile(r"\([^()]*\d[^()]*\)")
REF_IN = re.compile(r"((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?) (\d+)")
# outside Genesis these words almost always mean the nation, kingdom or land, so they never link to the ancestor;
# the twelve tribes (Benjamin, Ephraim, ...) do link to their ancestor's card, which tells where the tribe came from
TRIBAL = {"Israel", "Judah", "Edom", "Moab", "Ammon", "Aram", "Midian", "Seir"}

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
        self.roles = {}  # medallion role per person: data/people/roles/*.json
        for f in sorted(glob.glob(os.path.join(D, "roles", "*.json"))):
            self.roles.update(json.load(open(f, encoding="utf-8")))
        self.fix = {}  # reviewed link choices: data/people/link_fix/*.json, {ctx: {name: "p:slug" | "l:slug" | ""}}
        for f in sorted(glob.glob(os.path.join(D, "link_fix", "*.json"))):
            for ctx, m in json.load(open(f, encoding="utf-8")).items():
                self.fix.setdefault(ctx, {}).update(m)
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
    def _names(self, kind, slug, all_aka=False):
        prof = (self.prof_p if kind == "p" else self.prof_l).get(slug)
        if not prof:
            return []
        if not hasattr(self, "_primary"):  # main name -> the largest verse count among entries with that main name
            self._primary = {}
            for k2, pr in (("p", self.prof_p), ("l", self.prof_l)):
                for sl, v in pr.items():
                    vc = (self.src_p if k2 == "p" else self.src_l).get(sl, {}).get("vc", 0)
                    self._primary[v.get("name")] = max(self._primary.get(v.get("name"), -1), vc)
        me_vc = (self.src_p if kind == "p" else self.src_l).get(slug, {}).get("vc", 0)
        # an alias that is another entry's main name: never in the whole-Bible fallback; in a chapter, only for the bigger figure
        # (Peter keeps "Simon"; Jebus does not take "Jerusalem")
        aka = [a for a in (prof.get("aka") or []) if a and (a.strip() not in self._primary or (all_aka and me_vc > self._primary[a.strip()]))]
        names = [prof.get("name")] + aka
        return [n for n in dict.fromkeys(n.strip() for n in names if n) if n not in NEVER_LINK and len(n) > 1]

    def _annotate(self, text, cands, book, me=None, ctx=None):
        if not text:
            return text
        table = []  # (name, kind, slug, weight)
        for w, key in enumerate(cands):
            kind, slug = key.split(":", 1)
            if slug == me:
                continue  # a card never links to itself
            for n in self._names(kind, slug, all_aka=True):
                if n in TRIBAL and book != "Genesis" and kind == "p":
                    continue  # outside Genesis these words almost always mean the tribe or nation
                table.append((n, kind, slug, w))
        # reviewed choices for shared names in this passage: {"Saul": "p:saul_2470"} or "" for no link
        fx = self.fix.get(ctx, {}) if ctx else {}
        if fx:
            table = [t for t in table if t[0] not in fx] + [(n, *v.split(":", 1), -1) for n, v in fx.items() if v]
        table.sort(key=lambda t: (-len(t[0]), t[3]))   # longest names first, then the most present in the chapter
        taken = [m.span() for m in REF_SPAN.finditer(text)]  # never inside "(Genesis 39)"
        used, out = set(), []
        for n, kind, slug, _ in table:
            if (kind, slug, n) in used or any(u[2] == n for u in used):
                continue  # each name once per passage; a person's other name (Jacob / Israel) links too
            for m in re.finditer(r"(?<![\w'’-])" + re.escape(n) + r"(?![\w]|-\w)", text):
                a, b = m.span()
                if any(a < y and x < b for x, y in taken):
                    continue
                taken.append((a, b)); used.add((kind, slug, n)); out.append((a, b, kind, slug))
                break
        # a name that belongs to only one person or place in the whole Bible links even when that chapter's data misses it
        for n, (kind, slug) in sorted(self._unique().items(), key=lambda kv: -len(kv[0])):
            if any(u[2] == n for u in used) or slug == me or n in fx or (n in TRIBAL and kind == "p" and book != "Genesis") or n not in text:
                continue
            for m in re.finditer(r"(?<![\w'’-])" + re.escape(n) + r"(?![\w]|-\w)", text):
                a, b = m.span()
                if any(a < y and x < b for x, y in taken):
                    continue
                taken.append((a, b)); used.add((kind, slug, n)); out.append((a, b, kind, slug))
                break
        for a, b, kind, slug in sorted(out, reverse=True):
            text = text[:a] + f"⟦{kind}:{slug}|{text[a:b]}⟧" + text[b:]
        return text

    def _unique(self):
        if not hasattr(self, "_uq"):
            # who could a bare name mean? every profiled person or place called that, plus every entry in the source data
            owners = defaultdict(dict)
            for kind, prof in (("p", self.prof_p), ("l", self.prof_l)):
                for slug in prof:
                    for n in self._names(kind, slug, all_aka=True):
                        owners[n][(kind, slug)] = (self.src_p if kind == "p" else self.src_l).get(slug, {}).get("vc", 0)
            for kind, src in (("p", self.src_p), ("l", self.src_l)):
                for slug, v in src.items():
                    if v.get("n") in owners:
                        owners[v["n"]].setdefault((kind, slug), v.get("vc", 0))
            # link only when one profiled owner clearly dominates (Jesus, David, Canaan the land); never for Mary, John, Pharaoh
            self._uq = {}
            for n, o in owners.items():
                if len(n) < 3: continue
                (top, vc), *rest = sorted(o.items(), key=lambda kv: -kv[1])
                prof = self.prof_p if top[0] == "p" else self.prof_l
                if top[1] in prof and (not rest or vc >= 4 * sum(r[1] for r in rest)) and (len(rest) == 0 or vc >= 20 or not rest):
                    self._uq[n] = top
        return self._uq

    def link_chapter(self, text, book, ch):
        d = self.chap.get(f"{book} {ch}", {"pe": [], "pl": []})
        cands = ["p:" + s for s in d["pe"] if s in self.prof_p] + ["l:" + s for s in d["pl"] if s in self.prof_l]
        # the chapter's own tags first, then the book's main people and places (chapter tags miss some mentions)
        cands += [k for k in self.book_top.get(book, []) if k not in cands and k[2:] in (self.prof_p if k[0] == "p" else self.prof_l)]
        return self._annotate(text, cands, book, ctx=f"{book} {ch}")

    def link_book(self, text, book):
        cands = [k for k in self.book_top.get(book, []) if (k[2:] in (self.prof_p if k[0] == "p" else self.prof_l))]
        return self._annotate(text, cands, book, ctx=f"book {book}")

    @staticmethod
    def cited(text):
        """Chapters cited in a line: "(Genesis 25; 32)" -> ["Genesis 25", "Genesis 32"]."""
        out = []
        for sp in REF_SPAN.finditer(text or ""):
            book = None
            for part in re.split(r"[;,]", sp.group(0).strip("()")):
                m = re.match(r"\s*((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?)?\s*(\d+)", part)
                if not m: continue
                book = m.group(1) or book
                if book: out.append(f"{book} {m.group(2)}")
        return out

    def link_card(self, text, me, fallback, fam=()):
        """Names inside a card line link to people and places in the chapters that line cites
        (or, with no citation, the chapters of the card's own story)."""
        keys = self.cited(text) or fallback
        cands, seen = ["p:" + f for f in fam if f in self.prof_p], set()
        for k in keys:
            d = self.chap.get(k, {"pe": [], "pl": []})
            for c in ["p:" + x for x in d["pe"] if x in self.prof_p] + ["l:" + x for x in d["pl"] if x in self.prof_l]:
                if c not in seen: seen.add(c); cands.append(c)
        book = keys[0].rsplit(" ", 1)[0] if keys else ""
        return self._annotate(text, cands, book, me, ctx=f"card {me}")

    def _era(self, v, chs):
        """Which of the 14 journey legs a person's story starts in (the medallion ring's color)."""
        import journey
        ref = next(iter(self._card_chapters(v)), None)
        b, c = (ref.rsplit(" ", 1)[0], int(ref.rsplit(" ", 1)[1])) if ref else (tuple(chs[0]) if chs else ("Genesis", 1))
        legs = journey.BOOK_LEG.get(b, 0)
        legs = legs if isinstance(legs, list) else [(1, legs)]
        out = 0
        for start, i in legs:
            if c >= start: out = i
        return out

    def _card_chapters(self, v):
        return [k for line in v.get("key", []) for k in self.cited(line)]

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
            cc, fs = self._card_chapters(v), [x["s"] for row in fam.values() for x in row if x["s"]]
            ic = SPECIAL.get(s) or self.roles.get(s) or ("false_god" if v.get("label") == "False god" else "people" if v.get("label") == "People group" else "family")
            P[s] = {**({"lab": v["label"]} if v.get("label") else {}), "ic": ic, "role": SPECIAL_LABEL.get(ic) or ROLE_LABEL.get(self.roles.get(s) or ic, ""), "era": self._era(v, src.get("ch", [])), "n": v["name"], "who": self.link_card(v["who"], s, cc, fs), "key": [self.link_card(k, s, cc, fs) for k in v.get("key", [])], "fam": fam, **where(src.get("ch", [])),
                    **({"mean": m["meaning"]} if m.get("meaning") else {}), **({"why": self.link_card(m["why"], s, cc, fs)} if m.get("why") else {})}
        L = {}
        pr = self.map["proj"] if self.map else None
        for s, v in self.prof_l.items():
            src = self.src_l.get(s, {})
            pos = {}
            if pr and src.get("lat") is not None:
                pos = {"x": round((src["lon"] - pr["lon0"]) * pr["kx"], 2), "y": round((pr["lat1"] - src["lat"]) * pr["ky"], 2)}
            m = self.mean.get(s, {})
            cc = self._card_chapters(v)
            L[s] = {**({"mean": m["meaning"]} if m.get("meaning") else {}), **({"why": self.link_card(m["why"], s, cc)} if m.get("why") else {}), "n": v["name"],
                    "what": self.link_card(v["what"], s, cc), "today": v.get("today", ""), "key": [self.link_card(k, s, cc) for k in v.get("key", [])], **pos, **where(src.get("ch", []))}
        here = {k: [s for s in d["pl"] if s in L and "x" in L[s]][:8] for k, d in self.chap.items()}
        within = {}
        for f in sorted(glob.glob(os.path.join(D, "within", "*.json"))):
            within.update(json.load(open(f, encoding="utf-8")))
        for sl, lv in within.items():
            if sl in L and lv: L[sl]["in"] = lv[:3]
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
        fine = [[n, *xy(lon, lat), list(r)] for n, lon, lat, r in journey.FINE]
        waters = [[n, *xy(lon, lat)] for n, lon, lat in journey.WATERS]
        anchors = [[s, *place(s)[0], place(s)[1]] for s in journey.ANCHORS]
        return {"legs": legs, "bl": bl, "notes": notes, "follow": sorted(journey.FOLLOW), "reg": reg, "seas": seas,
                "fine": fine, "waters": waters, "anchors": anchors}
