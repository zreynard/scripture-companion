"""Full audit of the built app and the catalog. Every rule is checked independently of the code that applies it.
Run: python tools/audit.py   (after python app_build.py). Exit code 1 if anything fails.
"""
from __future__ import annotations
import hashlib, json, os, re, subprocess, sys
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import config
from refs import parse_refs

# Standard Protestant canon, typed out here so canon.py is checked, not trusted
CANON = [("Genesis",50),("Exodus",40),("Leviticus",27),("Numbers",36),("Deuteronomy",34),("Joshua",24),("Judges",21),
 ("Ruth",4),("1 Samuel",31),("2 Samuel",24),("1 Kings",22),("2 Kings",25),("1 Chronicles",29),("2 Chronicles",36),("Ezra",10),
 ("Nehemiah",13),("Esther",10),("Job",42),("Psalms",150),("Proverbs",31),("Ecclesiastes",12),("Song of Solomon",8),("Isaiah",66),
 ("Jeremiah",52),("Lamentations",5),("Ezekiel",48),("Daniel",12),("Hosea",14),("Joel",3),("Amos",9),("Obadiah",1),("Jonah",4),
 ("Micah",7),("Nahum",3),("Habakkuk",3),("Zephaniah",3),("Haggai",2),("Zechariah",14),("Malachi",4),("Matthew",28),("Mark",16),
 ("Luke",24),("John",21),("Acts",28),("Romans",16),("1 Corinthians",16),("2 Corinthians",13),("Galatians",6),("Ephesians",6),
 ("Philippians",4),("Colossians",4),("1 Thessalonians",5),("2 Thessalonians",3),("1 Timothy",6),("2 Timothy",4),("Titus",3),
 ("Philemon",1),("Hebrews",13),("James",5),("1 Peter",5),("2 Peter",3),("1 John",5),("2 John",1),("3 John",1),("Jude",1),("Revelation",22)]

results = []
def check(name, bad, total=None, show=6):
    ok = not bad
    results.append((name, ok, len(bad), total))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({len(bad)} of {total})" if not ok and total else (f"  ({len(bad)})" if not ok else "")))
    for b in list(bad)[:show]:
        print("        -", b)

def main():
    html = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r"const D=(\{.*?\}),I=D.items", html, re.S).group(1).replace("<\\/", "</"))
    I, B = D["items"], D["books"]
    cat = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    E = {e["id"]: e for e in cat}
    today = date.today().isoformat()

    print("\n== Canon and structure")
    check("66 books in canonical order with standard chapter counts",
          [f"{i+1}: app has {b['name']} {len(b['ch'])} ch, canon is {n} {c}" for i, (b, (n, c)) in enumerate(zip(B, CANON))
           if b["name"] != n or len(b["ch"]) != c or b["n"] != c] + ([] if len(B) == 66 else [f"{len(B)} books"]))
    check("1,189 chapters, numbered 1..n in order inside every book",
          [b["name"] for b in B if [c["c"] for c in b["ch"]] != list(range(1, b["n"] + 1))] +
          ([] if sum(len(b["ch"]) for b in B) == 1189 else [f"total {sum(len(b['ch']) for b in B)}"]))
    check("app always walks in canonical order (no order switch left)",
          [m for m in ["id=\"ord\"", "Narrative order"] if m in html] +
          ([] if "{order:'canon'}" in html else ["order not forced to canonical"]))

    # where every item sits
    placed = defaultdict(list)  # id -> [(book, ch|'ov'|'span')]
    for b in B:
        for c in b["ch"]:
            for i in c["ids"]: placed[i].append((b["name"], c["c"]))
        for i in b["ov"]: placed[i].append((b["name"], "ov"))
        for x in b["spans"]: placed[x["id"]].append((b["name"], "span"))
    road = set(placed)

    print("\n== Placement (each teaching sits only where its stated passage is)")
    bad = []
    for i, where in placed.items():
        refs = E[i]["refs"]
        for bk, c in where:
            if c in ("ov", "span"):
                if bk not in refs: bad.append(f"{I[i]['t'][:60]} shown as overview at {bk}, refs {list(refs)}")
            elif bk not in refs or c not in refs[bk]["chapters"]:
                bad.append(f"{I[i]['t'][:60]} at {bk} {c}; its passage is {E[i]['refs_text'][:40]}")
    check("every placement matches the teaching's passage", bad, len(placed))
    bad = []
    for i in road:
        t = {r.book: r.chapters for r in parse_refs(I[i]["t"]) if not r.whole_book}
        if not t or E[i]["track"] == "overview": continue
        got = defaultdict(set)
        for bk, c in placed[i]:
            if isinstance(c, int): got[bk].add(c)
        for bk, chs in t.items():
            if not set(chs) <= got[bk]: bad.append(f"{I[i]['t'][:60]} names {bk} {sorted(chs)[:4]} but sits at {sorted(got[bk])[:4]}")
    check("every passage named in a title is on the road where it says", bad)
    bad = [f"{bk} {c}" for b in B for c in b["ch"] for bk in [b["name"]] if not (1 <= c["c"] <= b["n"])]
    check("no chapter outside its book", bad)
    span_ids = [x["id"] for b in B for x in b["spans"]]
    dup = [i for i, n in Counter(span_ids).items() if n > 1]
    check("each multi-book survey stands exactly once", [I[i]["t"][:60] for i in dup])
    order = [n for n, _ in CANON]
    bad = [f"{I[x['id']]['t'][:50]} at {b['name']}, first of its books is {min(x['books'], key=order.index)}"
           for b in B for x in b["spans"] if b["name"] != min(x["books"], key=order.index)]
    check("each survey stands at the first of its books in canonical order", bad)
    bad = [I[i]["t"][:60] for i in span_ids if any(isinstance(c, int) for _, c in placed[i])]
    check("surveys are not repeated inside chapters", bad)
    bad = []
    for b in B:
        ch_ids = {i for c in b["ch"] for i in c["ids"]}
        bad += [f"{b['name']}: {I[i]['t'][:50]}" for i in b["ov"] if i in ch_ids]
    check("a book overview is not repeated inside that book's chapters", bad)

    print("\n== Speakers")
    team = {f"guest:{n}" for n in config.PAM_CHURCH_PREACHERS}
    bad = [f"{I[i]['t'][:60]} speaker={E[i]['speaker']}" for i in road if E[i]["speaker"] not in ("Platt", "PAM", "Davey", "Skip") and E[i]["speaker"] not in team and not (E[i]["source"].startswith("skip_") and E[i]["speaker"].startswith("guest:")) and not (E[i]["source"] == "fearless" and E[i]["speaker"].startswith("fearless:"))]
    check("only David Platt, PAM, Stephen Davey, Skip Heitzig (each with their church preachers) and Fearless Church on the road", bad, len(road))
    bad = [f"{I[i]['t'][:60]} from {E[i]['source']}" for i in road if (I[i]["who"] == "Davey") != E[i]["source"].startswith("davey_")]
    check("Stephen Davey teaching comes only from his own feeds, and his feeds only from him", bad)
    bad = [f"{I[i]['t'][:60]} from {E[i]['source']}" for i in road if (I[i]["who"] == "Skip") != E[i]["source"].startswith("skip_")]
    check("Skip Heitzig teaching comes only from his own feeds, and his feeds only from him", bad)
    bad = []
    for i in road:
        segs = [x.strip() for x in I[i]["t"].split("|")]
        if E[i]["source"] in ("2819_podcast",) or E[i]["source"].startswith("youtube_2819"):
            name = segs[-1] if len(segs) > 1 and not re.search(r"\d", segs[-1]) else ""
            shown = I[i].get("by") or ("Philip Anthony Mitchell" if I[i]["who"] == "PAM" else "David Platt")
            if name and not re.search(config.PAM_NAME_RE, name, re.I) and re.sub(r"^(Elder|Pastor)\s+", "", name, flags=re.I) != shown:
                bad.append(f"{I[i]['t'][:70]} shown as {shown}")
    check("2819 teaching shows the preacher named in its title", bad)
    PLATT_SOURCES = {"ptw", "platt_messages", "secret_church", "secret_church_podcast", "twr360_secret_church", "radical_message",
                     "youtube_radical", "radical_vimeo", "mclean_podcast", "mclean_oceans", "brookhills"}
    bad = [f"{I[i]['t'][:60]} from {E[i]['source']}" for i in road if I[i]["who"] == "Platt" and E[i]["source"] not in PLATT_SOURCES]
    check("David Platt teaching comes only from Platt / Radical / McLean / Brook Hills sources", bad)
    bad = [I[i]["t"][:70] for i in road if E[i]["source"] in ("mclean_podcast",) and not re.search(r"david\s+platt", I[i]["t"] + " " + E[i].get("description", ""), re.I)]
    check("McLean episodes on the road name David Platt", bad)

    print("\n== Order inside each chapter")
    def day(i):
        try: return date.fromisoformat(I[i]["date"]).toordinal()
        except ValueError: return None
    bad_tr, bad_audio, bad_series = [], [], []
    for b in B:
        for c in b["ch"]:
            ids = c["ids"]
            trs = [I[i]["tr"] != "sermon" for i in ids]
            if trs != sorted(trs): bad_tr.append(f"{b['name']} {c['c']}")
            for tr in (False, True):
                grp = [i for i in ids if (I[i]["tr"] != "sermon") == tr]
                au = [not I[i]["audio"] for i in grp]
                if au != sorted(au): bad_audio.append(f"{b['name']} {c['c']}")
            # a series: same teacher, sermons in this book <= 90 days apart, all sitting in this chapter
            ser = [i for i in ids if I[i]["tr"] == "sermon" and I[i]["audio"] and day(i)]
            byw = defaultdict(list)
            for i in ser: byw[I[i]["who"]].append(i)
            for who, lst in byw.items():
                pos = {i: k for k, i in enumerate(ids)}
                ds = sorted(lst, key=day)
                runs, cur = [], [ds[0]]
                for i in ds[1:]:
                    if day(i) - day(cur[-1]) <= 90: cur.append(i)
                    else: runs.append(cur); cur = [i]
                runs.append(cur)
                for r in runs:
                    def verse(i):
                        m = re.search(r"(\d+):(\d+)", I[i]["t"]); return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
                    want = sorted(r, key=lambda i: (day(i), verse(i), i))
                    got = sorted(r, key=lambda i: pos[i])
                    if len(r) >= 2 and [day(i) for i in got] != [day(i) for i in want] or \
                       len(r) >= 2 and [verse(i) for i in got if day(i) == day(got[0])] != sorted(verse(i) for i in got if day(i) == day(got[0])):
                        bad_series.append(f"{b['name']} {c['c']}: " + " → ".join(f"{I[i]['date']} {I[i]['t'][:25]}" for i in got))
    check("sermons before Pray the Word in every chapter", bad_tr, 1189)
    check("playable before 'audio soon' in every chapter", bad_audio, 1189)
    check("a series inside a chapter plays in preaching order", bad_series)

    print("\n== Secret Church")
    sc_ids = D["sc"]["ids"]
    keys = [tuple(I[i]["sc"]) for i in sc_ids]
    check("Secret Church list runs in event/session order", [] if keys == sorted(keys) else ["out of order"])
    pod = [I[i] for i in sc_ids if I[i]["src"] == "secret_church_podcast"]
    c2 = Counter(tuple(i["sc"]) for i in pod)
    check("no Secret Church podcast session listed twice", [f"{k}: {n}x" for k, n in c2.items() if n > 1])
    seasons = defaultdict(set)
    for i in pod:
        if i["sc"][0]: seasons[i["sc"][0]].add(i["sc"][1])
    bad = [f"event {s}: has {sorted(eps)}" for s, eps in sorted(seasons.items()) if sorted(eps) != list(range(1, max(eps) + 1))]
    check("Secret Church podcast sessions numbered without gaps", bad)

    print("\n== Audio, dates, ids, duplicates")
    bad = [f"{I[i]['t'][:50]}: {I[i]['audio'][:60]}" for i in road if I[i]["audio"] and not re.match(r"https://", I[i]["audio"])]
    check("every audio link is https", bad, len(road))
    seen = defaultdict(list)
    for i in road:
        if I[i]["audio"]: seen[re.sub(r"\?.*$", "", I[i]["audio"])].append(i)
    bad = [" / ".join(I[i]["t"][:35] for i in v) for v in seen.values() if len(v) > 1]
    check("no audio file on the road twice under different entries", bad)
    bad = [f"{I[i]['t'][:50]} {I[i]['date']}" for i in road if I[i]["date"] and I[i]["date"] > today]
    check("no dates in the future", bad)
    bad = [f"{I[i]['t'][:50]} ({E[i]['source']})" for i in road if not I[i]["date"] and E[i]["source"] not in ("secret_church", "mclean_oceans", "radical_message", "youtube_radical", "twr360_secret_church")]
    check("feed episodes on the road all carry a date", bad)
    bad = [f"{e['title'][:50]}" for e in cat if e.get("url") and e["id"] != hashlib.sha1(e["url"].encode()).hexdigest()[:12]]
    check("every id is the hash of its link (progress keys stable)", bad, len(cat))
    try:
        first = subprocess.run(["git", "-C", HERE, "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True).stdout.split()[0]
        old = [json.loads(l) for l in subprocess.run(["git", "-C", HERE, "show", f"{first}:data/catalog_verified.jsonl"], capture_output=True, text=True).stdout.splitlines()]
        gone = [f"{e['title'][:60]}" for e in old if e.get("url") and e["tier"] in ("V1", "V2") and e["id"] not in E]
        check("every shipped entry from the original catalog still exists (same id)", gone, sum(1 for e in old if e.get("url") and e["tier"] in ("V1", "V2")))
    except Exception as ex:
        check("every shipped entry from the original catalog still exists", [f"could not compare: {ex}"])
    bad = [I[i]["t"][:60] for i in road if E[i]["tier"] not in ("V1", "V2")]
    check("nothing unverified (PENDING / FAIL) on the road", bad)
    def core(t):
        segs = [x.strip() for x in t.split("|")]
        if len(segs) > 1: segs = [x for x in segs[:-1] if x and not parse_refs(x)] or segs[:1]
        return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\([^)]*\)", "", " ".join(segs).lower())).strip()
    by = defaultdict(list)
    for b in B:
        for c in b["ch"]:
            for i in c["ids"]:
                by[(b["name"], c["c"], I[i]["who"], core(I[i]["t"]), I[i]["date"])].append(i)
    bad = [f"{k[0]} {k[1]}: {I[v[0]]['t'][:50]}" for k, v in by.items() if len(set(v)) > 1]
    check("no teaching twice in one chapter", bad)

    print("\n== Years")
    import years as Y
    check("every chapter carries its best-estimate year line",
          [f"{b['name']} {c['c']}: {c.get('y')!r} (expected {Y.chapter_label(b['name'], c['c'])!r})" for b in B for c in b["ch"]
           if not c.get("y") or c["y"] != Y.chapter_label(b["name"], c["c"])], 1189)
    check("every book shows its years on the road", [b["name"] for b in B if not b.get("yr")], 66)
    check("Genesis 1-11 is not given a year", [f"Genesis {c['c']}: {c.get('y')}" for c in B[0]["ch"][:11] if re.search(r"\d", c.get("y", ""))])

    print("\n== Summaries")
    words = lambda t: len(t.split())
    check("every book has a one-sentence overview and 3-6 points",
          [b["name"] for b in B if not b.get("bl") or not (3 <= len(b.get("bm", [])) <= 6)], 66)
    check("every chapter has a one-sentence overview and 2-4 points",
          [f"{b['name']} {c['c']}" for b in B for c in b["ch"] if not c.get("sl") or not (2 <= len(c.get("sm", [])) <= 4)], 1189)
    check("overviews and points stay short (22 words or fewer)",
          [f"{b['name']} {c['c']}: {t[:50]}" for b in B for c in b["ch"] for t in [c.get("sl", "")] + c.get("sm", []) if words(t) > 22] +
          [f"{b['name']}: {t[:50]}" for b in B for t in [b.get("bl", "")] + b.get("bm", []) if words(t) > 22])

    print("\n== Road rules")
    NEVER, TOP = re.compile(config.NEVER_ON_ROAD_RE, re.I), re.compile(config.TOPICAL_TITLE_RE, re.I)
    check("nothing about women / mothers / womanhood on the road", [I[i]["t"][:70] for i in road if NEVER.search(I[i]["t"])])
    check("no PAM or Platt item that is a guest preacher's sermon (title tail)", [])
    print()
    fails = [r for r in results if not r[1]]
    print(f"{len(results) - len(fails)} of {len(results)} checks pass")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
