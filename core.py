"""Core and Go Deeper: one primary exposition for each chapter or natural passage of the Journey, and every other
teaching kept, ranked, for optional depth.

The choice, book by book:
  0. Protected series are Core whole, in preaching order: Philip Anthony Mitchell's 2819 Church series through
     Matthew (PROTECTED). The chapters it teaches are not offered to anything else; a chapter it barely touches stays
     open for other teaching as well.
  1. Candidates for the other chapters: full sermons placed on the chapter by PAM, Platt, Skip or Davey, Davey's
     Wisdom Journey lessons (short, consecutive studies through the Bible), sermons in parts taken together, one
     teacher's series run through a chapter taken together (consecutive messages of one source). Never two
     unrelated sermons or two teachers in one Core. Not candidates: Secret Church sessions, devotionals (Pray the Word),
     book overviews, sermons spread over several books or scattered passages.
  2. What a candidate is worth: for each chapter it covers, a completeness credit (whole chapter 1.0, most of it 0.85,
     a substantial part 0.65, a section 0.45, less = a little), times
       span      by verses: up to ~60 = full; to ~100 nearly; longer stretches less; past ~140 a fallback; >8 chapters never
       depth     verses per minute: a survey faster than ~1.6 verses a minute is weighed down
       trust     a passage heard in the recording counts 95% (read aloud clearly) or 85%; one inferred from a description 90%
       teacher   PAM 1.00, Platt 0.95, Skip 0.78, Davey 0.66 (a Wisdom Journey lesson 0.56): a preference a clearly
                 better fit outweighs
  3. The book is chosen as a whole (dynamic programming over its chapters): non-overlapping choices worth the most,
     less a cost per listening hour, plus a small reward for staying with one teacher's series through a book and a
     small cost for changing teacher. Three settings of these costs give the Quality, Balanced and Lean Journeys.
  4. A passage spanning chapters plays after the last of them, so its Scripture is read first.
Every choice keeps its reason (for the report; the app does not show it). Go Deeper holds everything else.
"""
from collections import defaultdict
import json, os, re

W = {"PAM": 1.00, "Platt": 0.95, "Vaughan": 0.85, "Skip": 0.78, "Davey": 0.66}
WJ = 0.85                    # Davey's Wisdom Journey lessons, relative to his sermons
NAME = {"Platt": "David Platt", "PAM": "Philip Anthony Mitchell", "Skip": "Skip Heitzig", "Davey": "Stephen Davey", "Vaughan": "Kennon Vaughan"}
MODES = {"quality": {"lam": 0.12, "mu": 0.03, "sb": 0.015, "light": 1.0, "gap": 0.5},
         "balanced": {"lam": 0.30, "mu": 0.03, "sb": 0.015, "light": 3.0, "gap": 0.45},
         "lean": {"lam": 0.55, "mu": 0.03, "sb": 0.015, "light": 4.0, "gap": 0.35},
         "short": {"lam": 1.2, "mu": 0.03, "sb": 0.015, "light": 2.0, "gap": 0.35}}   # for comparison: what ~400 hours takes
# Listening time from the favourite teachers costs less: they are not cut to save hours
HOUR_COST = {"PAM": 0.4, "Platt": 0.5, "Vaughan": 0.8, "Skip": 1.0, "Davey": 1.0}
# Chapters that are mostly lists (genealogies, census figures, building specifications, land allotments, rosters):
# here a short lesson serves better than an hour, so listening time costs more ("light" times the usual cost).
LIGHT = {"Genesis": [5, 10, 36], "Exodus": [25, 26, 27, 28, 30, 31, 35, 36, 37, 38, 39], "Leviticus": [1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15],
         "Numbers": [1, 2, 3, 4, 7, 26, 28, 29, 33, 34], "Joshua": [12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
         "1 Chronicles": [1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 23, 24, 25, 26, 27], "Ezra": [2, 8, 10], "Nehemiah": [3, 7, 10, 11, 12],
         "Ezekiel": [40, 41, 42, 45, 47, 48]}
MODE = "balanced"
PROTECTED = [("PAM", "2819_podcast", "Matthew")]   # (teacher, source, book): the series is Core whole
SURVEY_SRC = {"secret_church", "secret_church_podcast", "twr360_secret_church", "youtube_radical"}
LESSON_SRC = {"davey_journey"}
NOT_SERMON = re.compile(r"^\s*bonus\b|\binterview\b|conversation with|roundtable|panel discussion|\bq ?& ?a\b", re.I)   # never Core
PART = re.compile(r"^(.*?)[\s\-–—:,(]*\bPart\s+([A-Z]|\d+)\b\)?\s*$", re.I)
SPEED = 0.9


SERIES_GAP = 21              # days between messages of one series run


def _days(a, b):
    from datetime import date
    try: return abs((date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days)
    except ValueError: return 9999


def minutes(it, med):
    d = it.get("dur") or 0
    est = not d
    if est: d = med.get(it["src"], 45 * 60)
    return max(60, d - (it.get("s") or 0) - (it.get("e") or 0)) / 60, est


def credit(f):
    return 1.0 if f >= 0.8 else 0.85 if f >= 0.6 else 0.65 if f >= 0.4 else 0.45 if f >= 0.25 else 1.8 * f


def _segments(chs):
    out, cur = [], [chs[0]]
    for c in chs[1:]:
        if c == cur[-1] + 1: cur.append(c)
        else: out.append(cur); cur = [c]
    return out + [cur]


def rng(book, a, b, cov, V):
    if a != b: return f"{book} {a}–{b}"
    vs = sorted(v for (c, v) in cov if c == a)
    if not vs or len(vs) >= V[a - 1]: return f"{book} {a}"
    return f"{book} {a}:{vs[0]}–{vs[-1]}" if vs[-1] != vs[0] else f"{book} {a}:{vs[0]}"


class Engine:
    def __init__(self, books, items, VS, ref_how, item_books, VC):
        self.books, self.items, self.VS, self.ref_how, self.VC = books, items, VS, ref_how, VC
        med = defaultdict(list)
        for it in items.values():
            if it.get("dur"): med[it["src"]].append(it["dur"])
        self.med = {k: sorted(v)[len(v) // 2] for k, v in med.items()}
        sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spoken_refs.json")
        self.heard = {k: v.get("score", 0) for k, v in (json.load(open(sp)) if os.path.exists(sp) else {}).items() if v.get("ref")}
        self.parts = defaultdict(list)
        for i, it in items.items():
            m = PART.match(it["t"] or "")
            if m: self.parts[(it["who"], it["src"], m.group(1).strip().lower())].append((m.group(2).upper(), i))
        # a series: one teacher's sermons in one source on one book, no more than 120 days apart
        by = defaultdict(list)
        for i, it in items.items():
            for b in (VS.get(i) or {}): by[(it["who"], it["src"], b)].append((it.get("date") or "", i))
        self.series = {}
        from datetime import date
        for key, xs in by.items():
            xs.sort(); n, last = 0, None
            for d, i in xs:
                try: day = date.fromisoformat(d).toordinal()
                except ValueError: day = None
                if last is not None and day is not None and day - last > 120: n += 1
                if day is not None: last = day
                self.series[(i, key[2])] = f"{key[0]}|{key[1]}|{n}"
        pam = defaultdict(int)
        for i, it in items.items():
            if it["who"] == "PAM" and it["tr"] == "sermon":
                for b in (VS.get(i) or {}): pam[b] += 1
        self.pam_books = {b for b, n in pam.items() if n >= 3}

    # ---- one candidate
    def make(self, book, ids, a, b, cov, kind="single"):
        items, V = self.items, self.VC[book]
        mins, est, wsum = 0, False, 0
        for i in ids:
            m, e = minutes(items[i], self.med); mins += m; est = est or e
            w = W[items[i]["who"]] * (WJ if items[i]["src"] in LESSON_SRC else 1)
            wsum += w * m
        w = wsum / mins
        nch, U = b - a + 1, sum(V[c - 1] for c in range(a, b + 1))
        fills = {c: sum(1 for (cc, _) in cov if cc == c) / V[c - 1] for c in range(a, b + 1)}
        n = len(cov)
        if nch == 1: span = 1.0
        elif nch > 8: span = 0.0
        elif U <= 60: span = 1.0 if nch <= 4 else 0.8
        elif U <= 100: span = 0.95 if nch == 2 else 0.85
        elif U <= 140: span = 0.8 if nch == 2 else 0.65
        elif U <= 220: span = 0.4
        else: span = 0.2
        vpm = n / max(mins, 1)
        depth = (1.0 if vpm <= 1.6 else (1.6 / vpm) ** 0.5) * (0.9 if mins < 18 else 1.0)
        how = {self.ref_how.get(i, "curated") for i in ids}
        heard = "spoken" in how or "none" in how or any(items[i]["src"] == "brookhills_ia" for i in ids)
        aloud = min((self.heard.get(i, 0) for i in ids), default=0)
        trust = (0.95 if aloud >= 0.7 else 0.85) if heard else 0.9 if "description-first" in how else 1.0
        value = sum(credit(f) for f in fills.values()) * w * span * depth * trust
        who = items[ids[0]]["who"]
        return {"book": book, "ids": list(ids), "a": a, "b": b, "cov": cov, "who": who, "mins": mins, "est": est, "fills": fills,
                "n": n, "U": U, "span": span, "depth": depth, "trust": trust, "w": w, "value": value, "q": value / nch, "kind": kind,
                "sid": self.series.get((ids[0], book), who), "lesson": items[ids[0]]["src"] in LESSON_SRC}

    def candidates(self, book, chapters):
        items, VS, V = self.items, self.VS, self.VC[book]
        seen, out = set(), []
        for c, ids in chapters.items():
            for i in ids:
                if i in seen: continue
                seen.add(i)
                it = items[i]
                lesson = it["src"] in LESSON_SRC
                if not (it["tr"] == "sermon" or lesson) or not it.get("audio") or it["who"] not in W or it["src"] in SURVEY_SRC: continue
                if NOT_SERMON.search(it["t"] or ""): continue
                cov_all = VS.get(i) or {}
                cov = {(c_, v) for (c_, v) in (cov_all.get(book) or ()) if 1 <= c_ <= len(V)}
                if not cov: continue
                if len(cov) / (sum(len(s) for s in cov_all.values()) or 1) < 0.75: continue     # mostly another book
                segs = _segments(sorted({c_ for c_, _ in cov}))
                seg = max(segs, key=lambda s: sum(1 for (c_, _) in cov if c_ in s))
                inseg = {(c_, v) for (c_, v) in cov if c_ in seg}
                if len(inseg) / len(cov) < 0.8: continue                                           # scattered: topical
                fl = {c_: sum(1 for (cc, _) in inseg if cc == c_) / V[c_ - 1] for c_ in seg}
                while len(seg) > 1 and fl[seg[0]] < 0.4: seg = seg[1:]
                while len(seg) > 1 and fl[seg[-1]] < 0.4: seg = seg[:-1]
                inseg = {(c_, v) for (c_, v) in inseg if c_ in seg}
                out.append(self.make(book, [i], seg[0], seg[-1], inseg))
        # sermons in parts: taken whole, never a part alone
        done = set()
        for x in list(out):
            it = items[x["ids"][0]]
            m = PART.match(it["t"] or "")
            if not m: continue
            key = (it["who"], it["src"], m.group(1).strip().lower())
            out.remove(x)
            if key in done: continue
            done.add(key)
            ids = [i for _, i in sorted(self.parts.get(key, []), key=lambda p: (len(p[0]), p[0])) if items[i].get("audio")]
            if len(ids) < 2: continue
            cov = {(c_, v) for i in ids for (c_, v) in ((VS.get(i) or {}).get(book) or ()) if 1 <= c_ <= len(V)}
            chs = sorted({c_ for c_, _ in cov})
            if chs: out.append(self.make(book, ids, chs[0], chs[-1], cov, "parts"))
        singles = [x for x in out if x["a"] == x["b"]]
        by = defaultdict(list)
        for x in singles: by[x["a"]].append(x)
        for c, xs in by.items():
            Vc = V[c - 1]
            # one teacher's series through the chapter, its messages together (consecutive weeks of one source)
            per = defaultdict(list)
            for x in xs:
                if len(x["cov"]) < 0.6 * Vc: per[(x["who"], x["lesson"], items[x["ids"][0]]["src"])].append(x)
            runs = []
            for ys in per.values():
                ys = sorted([y for y in ys if items[y["ids"][0]].get("date")], key=lambda y: items[y["ids"][0]]["date"])
                run = []
                for y in ys:
                    if run and _days(items[run[-1]["ids"][0]]["date"], items[y["ids"][0]]["date"]) > SERIES_GAP:
                        runs.append(run); run = []
                    run.append(y)
                if run: runs.append(run)
            for ys in runs:
                ys = sorted(ys, key=lambda y: (min(v for _, v in y["cov"]), y["ids"][0]))
                grp, have = [], set()
                for y in ys:
                    if len(y["cov"] & have) <= 0.3 * len(y["cov"]): grp.append(y); have |= y["cov"]
                if len(grp) >= 2 and len(have) >= 0.6 * Vc:
                    out.append(self.make(book, [i for y in grp for i in y["ids"]], c, c, have, "group"))
            # never two unrelated sermons together: Core is one teaching, or one sermon's parts, or one series' run
        return out

    # ---- a book as a whole
    def choose(self, book, cands, N, blocked, P):
        ends = defaultdict(list)
        for x in cands:
            if x["span"] > 0 and not any(c in blocked for c in range(x["a"], x["b"] + 1)): ends[x["b"]].append(x)
        PROT = "PROTECTED"
        teacher = lambda s: None if s is None else "PAM" if s == PROT else s.split("|")[0]
        def link(s, t_sid, t_who):
            if s is None: return 0
            if s == t_sid: return P["sb"]
            return -P["mu"] / 2 if teacher(s) == t_who else -P["mu"]
        best = [dict() for _ in range(N + 1)]
        best[0][None] = (0.0, None)
        for k in range(1, N + 1):
            if k in blocked:                                                   # a protected series chapter
                for s, (v, _) in best[k - 1].items():
                    sc = v + link(s, PROT, "PAM")
                    if sc > best[k].get(PROT, (-1e9,))[0]: best[k][PROT] = (sc, ("skip", k - 1, s))
                continue
            has = any(k >= x["a"] for x in cands if x["a"] <= k <= x["b"] and x["span"] > 0)   # suitable teaching exists here
            for s, (v, _) in best[k - 1].items():
                v2 = v - (P["gap"] if has else 0)                                # a chapter left without Core costs something
                if v2 > best[k].get(s, (-1e9,))[0]: best[k][s] = (v2, ("skip", k - 1, s))
            for x in ends[k]:
                light = sum(1 for c in range(x["a"], x["b"] + 1) if c in LIGHT.get(book, ())) / (x["b"] - x["a"] + 1)
                gain = x["value"] - P["lam"] * HOUR_COST.get(x["who"], 1) * (1 + (P["light"] - 1) * light) * x["mins"] / 60
                for s, (v, _) in best[x["a"] - 1].items():
                    sc = v + gain + link(s, x["sid"], x["who"])
                    if sc > best[k].get(x["sid"], (-1e9,))[0]: best[k][x["sid"]] = (sc, ("take", x["a"] - 1, s, x))
        s = max(best[N], key=lambda s: best[N][s][0]); k = N; pick = []
        while k > 0:
            _, step = best[k][s]
            if step[0] == "skip": k, s = step[1], step[2]
            else: pick.append(step[3]); k, s = step[1], step[2]
        return pick[::-1]

    def protected(self, book, chapters):
        """A protected series on this book: its sermons in preaching order, and the chapters it teaches."""
        items, VS, V = self.items, self.VS, self.VC[book]
        keys = [(w, s) for w, s, b in PROTECTED if b == book]
        if not keys: return [], set()
        ids = sorted({i for lst in chapters.values() for i in lst if (items[i]["who"], items[i]["src"]) in keys and items[i]["tr"] == "sermon" and items[i].get("audio")},
                     key=lambda i: (min((c, v) for (c, v) in VS[i][book]) if (VS.get(i) or {}).get(book) else (999, 0), items[i].get("date") or "", i))
        cover = defaultdict(set); xs = []
        for i in ids:
            cov = {(c, v) for (c, v) in VS[i][book] if 1 <= c <= len(V)}
            if not cov: continue
            fl = defaultdict(int)
            for c, _ in cov: fl[c] += 1
            chs = sorted(fl)
            end = max([c for c in chs if fl[c] / V[c - 1] >= 0.2] or chs)
            start = min([c for c in chs if fl[c] / V[c - 1] >= 0.2] or chs)
            x = self.make(book, [i], start, end, {(c, v) for (c, v) in cov if start <= c <= end}, "protected")
            xs.append(x)
            for cv in cov: cover[cv[0]].add(cv)
        blocked = {c for c, s in cover.items() if len(s) / V[c - 1] >= 0.4}
        return xs, blocked

    def reason(self, x, rivals):
        V = self.VC[x["book"]]
        where = rng(x["book"], x["a"], x["b"], x["cov"], V)
        if x["kind"] == "protected":
            return "Philip Anthony Mitchell's 2819 Church series through Matthew, kept whole in preaching order."
        f = len(x["cov"]) / x["U"]
        fit = (f"Explains the whole of {where}." if x["a"] == x["b"] and f >= 0.9 else
               f"Explains {where} in one sermon." if x["a"] != x["b"] and x["kind"] == "single" else
               f"Explains {where} ({round(100 * f)}% of it) in two sermons." if x["kind"] == "pair" else
               f"Explains {where} ({round(100 * f)}% of it) in parts." if x["kind"] in ("group", "parts") else
               f"Explains {where}, {round(100 * f)}% of the chapter.")
        bits = [fit]
        if x["lesson"]: bits.append("A short Wisdom Journey lesson.")
        def weaker(r):
            rr = rng(r["book"], r["a"], r["b"], r["cov"], V)
            mine = {c for c, _ in x["cov"]}
            if r["span"] < 0.85: return f"covers {rr}, too broad for this passage"
            if len({cv for cv in r["cov"] if cv[0] in mine}) < 0.7 * len(x["cov"]): return f"covers only {rr}"
            if r["depth"] < 0.85: return f"moves through {rr} as a quick survey"
            if r["trust"] < 1: return f"names its passage ({rr}) less certainly"
            return f"is less complete on {rr}"
        said = []
        for t in [t for t in W if W[t] > W[x["who"]]]:
            rs = [r for r in rivals if r["who"] == t]
            if rs: said.append(f"{NAME[t].split()[-1]}'s sermon here {weaker(max(rs, key=lambda r: r['value']))}")
            elif t != "PAM" or x["book"] in self.pam_books: said.append(f"{NAME[t].split()[-1]} has no sermon on it")
        if said: bits.append(("; ".join(said))[0].upper() + "; ".join(said)[1:] + ".")
        return " ".join(bits)

    def run(self, mode=None):
        P = MODES[mode or MODE]
        units, at, deep, alts, rows = [], {}, {}, {}, []
        for b in self.books:
            name, abbr, V = b["name"], b["abbr"], self.VC[b["name"]]
            chapters = {c["c"]: c["ids"] for c in b["ch"]}
            prot, blocked = self.protected(name, chapters)
            cands = self.candidates(name, chapters)
            pick = self.choose(name, cands, b["n"], blocked, P)
            chosen = prot + pick
            for x in chosen:
                rivals = [r for r in cands if r is not x and not set(r["ids"]) & set(x["ids"]) and r["a"] <= x["b"] and r["b"] >= x["a"]]
                x["why"] = self.reason(x, rivals)
                x["rival_best"] = max(rivals, key=lambda r: r["value"] / (r["b"] - r["a"] + 1), default=None)
            # one unit per chapter where teaching plays (a passage's last chapter); the protected series first, in order
            byend = defaultdict(list)
            for x in chosen: byend[x["b"]].append(x)
            covered = defaultdict(set)
            for end in sorted(byend):
                xs = sorted(byend[end], key=lambda x: (x["kind"] != "protected", x["a"]))
                ids = [i for x in xs for i in x["ids"]]
                a = min(x["a"] for x in xs)
                u = len(units)
                units.append([abbr, a, end, ids, "", round(max(x["q"] for x in xs), 2)])
                for c in range(a, end + 1):
                    if f"{abbr}:{c}" not in at or units[at[f"{abbr}:{c}"]][2] < end: at[f"{abbr}:{c}"] = u
                for x in xs:
                    for c in range(x["a"], x["b"] + 1): covered[c] |= set(x["ids"])
                    same = sorted([r for r in cands if r["a"] == x["a"] and r["b"] == x["b"] and r["who"] != x["who"] and not set(r["ids"]) & set(x["ids"])], key=lambda r: -r["value"])
                    if x["kind"] != "protected" and len(xs) == 1:
                        seen_t, al = set(), []
                        for r in same:
                            if r["who"] in seen_t: continue
                            seen_t.add(r["who"]); al.append([r["ids"], round(r["q"], 2), r["who"]])
                        if al: alts[u] = al
                    rows.append({"book": name, "a": x["a"], "b": x["b"], "ids": x["ids"], "who": x["who"], "mins": x["mins"], "est": x["est"],
                                 "q": x["q"], "why": x["why"], "kind": x["kind"], "lesson": x["lesson"], "trust": x["trust"],
                                 "fills": x["fills"], "n": x["n"], "U": x["U"], "cov": sorted(x["cov"]),
                                 "rival": (x["rival_best"]["who"], x["rival_best"]["value"] / (x["rival_best"]["b"] - x["rival_best"]["a"] + 1)) if x["rival_best"] else None})
            # Go Deeper: everything else on each chapter, ranked
            vof = {}
            for r in cands:
                if r["kind"] == "single":
                    for i in r["ids"]: vof[i] = max(vof.get(i, 0), r["q"])
            for c, ids in chapters.items():
                g = {"alt": [], "verse": [], "broad": [], "dev": []}
                for i in ids:
                    if i in covered[c]: continue
                    it, cov = self.items[i], (self.VS.get(i) or {}).get(name) or set()
                    chs = {cc for cc, _ in cov}
                    if it["tr"] == "devotional": g["dev"].append(i)
                    elif len(chs) >= 3 or it["tr"] == "overview" or i not in vof: g["broad"].append(i)
                    elif len(chs) == 1 and len(cov) < 0.6 * V[c - 1]: g["verse"].append(i)
                    else: g["alt"].append(i)
                g["alt"].sort(key=lambda i: -vof.get(i, 0))
                g["verse"].sort(key=lambda i: min((v for (cc, v) in (self.VS.get(i) or {}).get(name, ()) if cc == c), default=0))
                g["broad"].sort(key=lambda i: len({cc for cc, _ in (self.VS.get(i) or {}).get(name, ())}) or 99)
                deep[f"{abbr}:{c}"] = {k: v for k, v in g.items() if v}
        return {"app": {"u": units, "at": at, "deep": deep, "alt": {str(k): v for k, v in alts.items()}, "bk": self.book_core()}, "rows": rows}

    def book_core(self):
        """Each book's opening stop: Skip's Bible from 30,000 Feet flight on it (in its parts) is Core; a flight over
        several books is the Core of each, offered at the first of them. Every other overview stays in Go Deeper."""
        order = [b["name"] for b in self.books]
        abbr = {b["name"]: b["abbr"] for b in self.books}
        groups = defaultdict(list)
        for i, it in self.items.items():
            if it["src"] != "skip_archive" or not it.get("audio") or not re.match(r"\s*Flight\b", it["t"] or ""): continue
            code = re.sub(r"^\s*Flight\s*", "", it["t"])
            stem = re.sub(r"\d$", "", code) if re.match(r"^\d", code) else re.sub(r"\d+$", "", code)
            groups[stem].append((code, i))
        # one flight per book (its parts together): the one most its own, never "Between the Testaments"
        flights = []
        for stem, xs in groups.items():
            ids = [i for _, i in sorted(xs)]
            books = sorted({b for i in ids for b in (self.VS.get(i) or {}) if b in abbr}, key=order.index)
            if books and stem != "INT": flights.append((stem, ids, books))
        pick = {}
        for b in order:
            mine = [f for f in flights if b in f[2]]
            if mine: pick[b] = min(mine, key=lambda f: (len(f[2]), f[0]))
        out = {}
        for b, (stem, ids, books) in pick.items():
            first = next(x for x in books if pick.get(x, (None,))[0] == stem)
            out[abbr[b]] = {"ids": ids, "q": ids if b == first else []}
        return out


def select(books, items, VS, ref_how, cited, item_books, VC, mode=None):
    return Engine(books, items, VS, ref_how, item_books, VC).run(mode)
