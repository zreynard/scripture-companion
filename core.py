"""Core and Go Deeper: one primary exposition for each chapter or natural passage of the Journey, and every other
teaching kept, ranked, for optional depth.

How a Core sermon is chosen, book by book:
  1. Candidates. Every full sermon placed on a chapter (devotionals and overviews stay in Go Deeper), by a Core teacher
     (Platt, PAM, Skip, Davey), with playable audio. Its passage comes from its verse coverage: one book, one run of
     chapters. A sermon spread over several books or scattered passages is not a candidate.
  2. Quality of each candidate, 0..1, the product of:
       fit       how much of the chapter it explains (a whole chapter = 1; a substantial passage within it, a little less;
                 a verse or two, much less)
       span      by verses: up to ~60 verses (one chapter, or a few short ones) = full; up to ~100 nearly; longer
                 stretches less, and beyond ~140 verses a fallback only; more than eight chapters = never Core (a survey)
       depth     verses per minute: a survey moving faster than ~1.6 verses a minute is weighed down
       trust     a passage heard in the recording (speech recognition) or inferred from a description counts a little less
       teacher   Platt 1.00, PAM 0.97, Skip 0.74, Davey 0.62: a preference, which a clearly better fit outweighs
  3. The Journey for a book is chosen as a whole (dynamic programming over its chapters): non-overlapping sermons that
     explain the most chapters as well as possible, with a small cost per listening hour (no padding, no duplicates) and
     a small cost for changing teacher between neighbouring passages (fewer awkward transitions).
  4. A sermon spanning chapters plays after the last of them, so its Scripture is always read first.
Every choice keeps its reason. Go Deeper holds everything else on the chapter, ranked: other expositions, verse-by-verse
studies, broader messages, devotionals.
"""
from collections import defaultdict
import re

PART = re.compile(r"^(.*?)[\s\-–—:,(]*\bPart\s+([A-Z]|\d+)\b\)?\s*$", re.I)

W = {"Platt": 1.00, "PAM": 0.97, "Skip": 0.74, "Davey": 0.62}
NAME = {"Platt": "David Platt", "PAM": "Philip Anthony Mitchell", "Skip": "Skip Heitzig", "Davey": "Stephen Davey"}
LAMBDA = 0.30      # cost per listening hour, in chapters-explained units
MU = 0.05          # cost of a change of teacher between neighbouring Core passages
SURVEY_SRC = {"secret_church", "secret_church_podcast", "twr360_secret_church", "youtube_radical"}
SPEED = 0.9        # the listener's usual playback speed, for the hours report


def minutes(it, med):
    d = it.get("dur") or 0
    est = not d
    if est: d = med.get(it["src"], 45 * 60)
    d = max(60, d - (it.get("s") or 0) - (it.get("e") or 0))
    return d / 60, est


def _segments(chs):
    out, cur = [], [chs[0]]
    for c in chs[1:]:
        if c == cur[-1] + 1: cur.append(c)
        else: out.append(cur); cur = [c]
    return out + [cur]


def _range_txt(book, a, b, cov, V):
    if a != b: return f"{book} {a}–{b}"
    vs = sorted(v for (c, v) in cov if c == a)
    if not vs or len(vs) >= V[a - 1]: return f"{book} {a}"
    return f"{book} {a}:{vs[0]}–{vs[-1]}" if vs[-1] != vs[0] else f"{book} {a}:{vs[0]}"


def candidates(book, chapters, items, VS, ref_how, item_books, V, med):
    """Every possible Core choice for one book: single sermons and same-teacher groupings within a chapter."""
    seen, out = set(), []
    for c, ids in chapters.items():
        for i in ids:
            if i in seen: continue
            seen.add(i)
            it = items[i]
            if it["tr"] != "sermon" or not it.get("audio") or it["who"] not in W: continue
            if it["src"] in SURVEY_SRC: continue                          # Secret Church: theology sessions that quote a text
            cov_all = VS.get(i) or {}
            cov = {(c, v) for (c, v) in (cov_all.get(book) or ()) if 1 <= c <= len(V)}   # a chapter the book lacks is a feed's typo
            if not cov: continue
            total = sum(len(s) for s in cov_all.values()) or 1
            if len(cov) / total < 0.75: continue                            # mostly another book
            segs = _segments(sorted({c for c, _ in cov}))
            seg = max(segs, key=lambda s: sum(1 for (c, _) in cov if c in s))
            inseg = {(c, v) for (c, v) in cov if c in seg}
            if len(inseg) / len(cov) < 0.8: continue                        # scattered passages: topical
            fills = {c: sum(1 for (cc, _) in inseg if cc == c) / V[c - 1] for c in seg}
            while len(seg) > 1 and fills[seg[0]] < 0.4: seg = seg[1:]      # an edge chapter it only touches stays free
            while len(seg) > 1 and fills[seg[-1]] < 0.4: seg = seg[:-1]
            inseg = {(c, v) for (c, v) in inseg if c in seg}
            a, b = seg[0], seg[-1]
            out.append(make(book, [i], a, b, inseg, items, ref_how, V, med))
    # a sermon in parts ("Genesis 37 - Part A", "Part B"): the parts together are one candidate, never a part alone
    done = set()
    for x in list(out):
        it = items[x["ids"][0]]
        m = PART.match(it["t"] or "")
        if not m: continue
        key = (it["who"], it["src"], m.group(1).strip().lower())
        out.remove(x)
        if key in done: continue
        done.add(key)
        sib = sorted(PARTS.get(key, []), key=lambda p: (len(p[0]), p[0]))
        ids = [i for _, i in sib if items[i].get("audio")]
        if len(ids) < 2: continue                                            # a part alone is never Core
        cov = {(c, v) for i in ids for (c, v) in ((VS.get(i) or {}).get(book) or ()) if 1 <= c <= len(V)}
        chs = sorted({c for c, _ in cov})
        if not chs: continue
        g = make(book, ids, chs[0], chs[-1], cov, items, ref_how, V, med)
        g["parts"] = True
        out.append(g)
    # groupings: one teacher's consecutive studies of parts of one chapter (a series, or a radio sermon in parts)
    by = defaultdict(list)
    for x in out:
        if x["a"] == x["b"] and x["fill"] < 0.6: by[(x["a"], items[x["ids"][0]]["who"])].append(x)
    for (c, who), xs in by.items():
        if len(xs) < 2: continue
        xs = sorted(xs, key=lambda x: (min(v for _, v in x["cov"]), x["ids"][0]))
        grp, have = [], set()
        for x in xs:
            if len(x["cov"] & have) <= 0.3 * len(x["cov"]): grp.append(x); have |= x["cov"]
        if len(grp) >= 2 and len(have) / V[c - 1] >= 0.6:
            g = make(book, [i for x in grp for i in x["ids"]], c, c, have, items, ref_how, V, med)
            g["q"] *= 0.96; g["value"] *= 0.96; g["group"] = True
            out.append(g)
    return out


def make(book, ids, a, b, cov, items, ref_how, V, med):
    it0 = items[ids[0]]
    mins, est = 0, False
    for i in ids:
        m, e = minutes(items[i], med); mins += m; est = est or e
    nch, U = b - a + 1, sum(V[c - 1] for c in range(a, b + 1))
    fills = {c: sum(1 for (cc, _) in cov if cc == c) / V[c - 1] for c in range(a, b + 1)}
    n = len(cov)
    fill = n / U
    # span, by verses as much as chapters: three short psalms are one natural passage, three long chapters are not
    if nch == 1: span = 1.0
    elif nch > 8: span = 0.0
    elif U <= 60: span = 1.0 if nch <= 4 else 0.8
    elif U <= 100: span = 0.95 if nch == 2 else 0.85
    elif U <= 140: span = 0.8 if nch == 2 else 0.65
    elif U <= 220: span = 0.4
    else: span = 0.2
    if fill >= 0.6: fit = 1.0
    elif n >= 10 or fill >= 0.3: fit = 0.55 + 0.45 * fill / 0.6
    else: fit = 0.3 + fill
    vpm = n / max(mins, 1)
    depth = 1.0 if vpm <= 1.6 else (1.6 / vpm) ** 0.5
    if mins < 18: depth *= 0.85
    how = {ref_how.get(i, "curated") for i in ids}
    heard = "spoken" in how or "none" in how or any(items[i]["src"] == "brookhills_ia" for i in ids)   # passage from the listening check
    read_aloud = min((HEARD.get(i, 0) for i in ids), default=0)          # how much of the passage he was heard reading
    trust = (0.95 if read_aloud >= 0.7 else 0.85) if heard else 0.9 if "description-first" in how else 1.0
    w = W[it0["who"]]
    q = w * span * fit * depth * trust
    chapters_explained = sum(1.0 if (f >= 0.3 or f * V[c - 1] >= 10) else f / 0.3 for c, f in fills.items())
    return {"book": book, "ids": ids, "a": a, "b": b, "cov": cov, "who": it0["who"], "mins": mins, "est": est, "fill": fill,
            "fills": fills, "n": n, "U": U, "span": span, "fit": fit, "depth": depth, "trust": trust, "q": q,
            "value": q * chapters_explained, "group": False}


def choose(book, cands, N):
    """The best non-overlapping set of candidates for a book's chapters 1..N (weighted intervals, with a teacher-change cost)."""
    ends = defaultdict(list)
    for x in cands:
        if x["span"] > 0: ends[x["b"]].append(x)
    T = list(W) + [None]
    best = [{t: (-1e9, None) for t in T} for _ in range(N + 1)]
    best[0][None] = (0.0, None)
    for k in range(1, N + 1):
        for t in T:                                                          # chapter k without its own Core
            if best[k - 1][t][0] > best[k][t][0]: best[k][t] = (best[k - 1][t][0], ("skip", k - 1, t))
        for x in ends[k]:
            gain = x["value"] - LAMBDA * x["mins"] / 60
            for t in T:
                prev = best[x["a"] - 1][t][0]
                if prev <= -1e8: continue
                sc = prev + gain - (MU if t and t != x["who"] else 0)
                if sc > best[k][x["who"]][0]: best[k][x["who"]] = (sc, ("take", x["a"] - 1, t, x))
    t = max(T, key=lambda t: best[N][t][0]); k = N; pick = []
    while k > 0:
        _, step = best[k][t]
        if step is None: break
        if step[0] == "skip": k, t = step[1], step[2]
        else: pick.append(step[3]); k, t = step[1], step[2]
    return pick[::-1]


def reason(x, rivals, V):
    """Why this one, in a sentence or two the listener can read in the app."""
    who = NAME[x["who"]]
    where = _range_txt(x["book"], x["a"], x["b"], x["cov"], V)
    fit = (f"Explains the whole of {where}." if x["a"] == x["b"] and x["fill"] >= 0.9 else
           f"Explains {where} in one sermon." if x["a"] != x["b"] else
           f"Explains {where}, {round(100 * x['fill'])}% of the chapter, in parts." if x["group"] or x.get("parts") else
           f"Explains {where}, {round(100 * x['fill'])}% of the chapter.")
    bits = [fit]
    def weaker(r):
        rng = _range_txt(r["book"], r["a"], r["b"], r["cov"], V)
        mine = {c for c, _ in x["cov"]}
        if r["span"] < 0.85: return f"covers {rng}, too broad for this passage"
        if len({(c, v) for (c, v) in r["cov"] if c in mine}) < 0.7 * len(x["cov"]): return f"covers only {rng}"
        if r["depth"] < 0.85: return f"moves through {rng} as a quick survey"
        if r["trust"] < 1: return f"names its passage ({rng}) less certainly"
        return f"is less focused on {rng}"
    better = [r for r in rivals if W[r["who"]] > W[x["who"]]]
    said = []
    for t in [t for t in W if W[t] > W[x["who"]]]:
        rs = [r for r in better if r["who"] == t]
        if rs: said.append(f"{NAME[t].split()[-1]}'s sermon here {weaker(max(rs, key=lambda r: r['q']))}")
        elif t != "PAM" or x["book"] in PAM_BOOKS: said.append(f"{NAME[t].split()[-1]} has no sermon on it")
    if said: bits.append("; ".join(said)[0].upper() + "; ".join(said)[1:] + ".")
    elif x["who"] in ("Platt", "PAM"): bits.append(f"{who} is a first-choice teacher.")
    return " ".join(bits)


PAM_BOOKS = set()
PARTS = defaultdict(list)
HEARD = {}                  # entry id -> share of the passage heard read aloud (data/spoken_refs.json)   # (teacher, source, title without "Part X") -> [(part, id)]

def select(books, items, VS, ref_how, cited, item_books, VC):
    med = defaultdict(list)
    for it in items.values():
        if it.get("dur"): med[it["src"]].append(it["dur"])
    med = {k: sorted(v)[len(v) // 2] for k, v in med.items()}
    units, at, deep, alts, rows = [], {}, {}, {}, []
    pam = defaultdict(int)
    for i, it in items.items():
        if it["who"] == "PAM" and it["tr"] == "sermon":
            for b_ in (VS.get(i) or {}): pam[b_] += 1
    PAM_BOOKS.update(b_ for b_, n in pam.items() if n >= 3)              # books PAM preaches through
    import json, os
    sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spoken_refs.json")
    HEARD.clear(); HEARD.update({k: v.get("score", 0) for k, v in (json.load(open(sp)) if os.path.exists(sp) else {}).items() if v.get("ref")})
    PARTS.clear()
    for i, it in items.items():
        m = PART.match(it["t"] or "")
        if m: PARTS[(it["who"], it["src"], m.group(1).strip().lower())].append((m.group(2).upper(), i))
    for b in books:
        name, abbr, V = b["name"], b["abbr"], VC[b["name"]]
        chapters = {c["c"]: c["ids"] for c in b["ch"]}
        cands = candidates(name, chapters, items, VS, ref_how, item_books, V, med)
        pick = choose(name, cands, b["n"])
        covered = {}
        for x in pick:
            rivals = [r for r in cands if r is not x and not set(r["ids"]) & set(x["ids"]) and r["a"] <= x["b"] and r["b"] >= x["a"]]
            x["why"] = reason(x, rivals, V)
            u = len(units)
            units.append([abbr, x["a"], x["b"], x["ids"], x["why"], round(x["q"], 2)])
            same = sorted([r for r in rivals if r["a"] == x["a"] and r["b"] == x["b"] and r["who"] != x["who"]], key=lambda r: -r["q"])
            seen_t, al = set(), []
            for r in same:
                if r["who"] in seen_t: continue
                seen_t.add(r["who"]); al.append([r["ids"], round(r["q"], 2), r["who"]])
            if al: alts[u] = al
            for c in range(x["a"], x["b"] + 1):
                at[f"{abbr}:{c}"] = u; covered[c] = x
            rows.append({"book": name, "a": x["a"], "b": x["b"], "ids": x["ids"], "who": x["who"], "mins": x["mins"], "est": x["est"],
                         "q": x["q"], "why": x["why"], "fill": x["fill"], "n": x["n"], "span": x["span"], "rivals": len(rivals),
                         "base": x["q"] / W[x["who"]], "rival_base": max((r["q"] / W[r["who"]] for r in rivals if r["who"] != x["who"]), default=0),
                         "rival_who": max(((r["q"] / W[r["who"]], r["who"]) for r in rivals if r["who"] != x["who"]), default=(0, ""))[1]})
        # Go Deeper: everything else on each chapter, ranked
        qof = {}
        for r in cands:
            for i in r["ids"]:
                qof[i] = max(qof.get(i, 0), r["q"] if not r["group"] else 0)
        for c, ids in chapters.items():
            core_ids = set(covered[c]["ids"]) if c in covered else set()
            g = {"alt": [], "verse": [], "broad": [], "dev": []}
            for i in ids:
                if i in core_ids: continue
                it, cov = items[i], (VS.get(i) or {}).get(name) or set()
                chs = {cc for cc, _ in cov}
                if it["tr"] == "devotional": g["dev"].append(i)
                elif len(chs) >= 3 or it["tr"] == "overview" or i not in qof: g["broad"].append(i)
                elif len(chs) == 1 and len(cov) < 0.6 * V[c - 1]: g["verse"].append(i)
                else: g["alt"].append(i)
            g["alt"].sort(key=lambda i: -qof.get(i, 0))
            g["broad"].sort(key=lambda i: len({cc for cc, _ in (VS.get(i) or {}).get(name, ())}) or 99)
            deep[f"{abbr}:{c}"] = {k: v for k, v in g.items() if v}
    return {"app": {"u": units, "at": at, "deep": deep, "alt": {str(k): v for k, v in alts.items()}}, "rows": rows}
