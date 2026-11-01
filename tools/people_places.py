"""Build the app's people / places / who-is-where data from Theographic Bible Metadata (CC BY-SA 4.0,
github.com/robertrouse/theographic-bible-metadata). Run: python -I tools/people_places.py <path-to-theographic-checkout>

Writes data/people/:
  people.json    {slug: {n name, g gender, f/m/s/p/c [slugs] father mother siblings partners children,
                          vc verse count, ch [[book, chapter], ...] chapters where they appear (canonical order)}}
  places.json    {slug: {n name, t type, lat, lon, vc, ch [[book, chapter], ...]}}
  chapters.json  {"Book N": {"pe": [person slugs by verse count], "pl": [place slugs]}}
Dates in the source follow a different chronology from the app's years table, so they are not used.
"""
import json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from canon import BOOKS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "people")
OSIS = ["Gen", "Exod", "Lev", "Num", "Deut", "Josh", "Judg", "Ruth", "1Sam", "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr", "Ezra", "Neh",
        "Esth", "Job", "Ps", "Prov", "Eccl", "Song", "Isa", "Jer", "Lam", "Ezek", "Dan", "Hos", "Joel", "Amos", "Obad", "Jonah", "Mic",
        "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal", "Matt", "Mark", "Luke", "John", "Acts", "Rom", "1Cor", "2Cor", "Gal", "Eph", "Phil",
        "Col", "1Thess", "2Thess", "1Tim", "2Tim", "Titus", "Phlm", "Heb", "Jas", "1Pet", "2Pet", "1John", "2John", "3John", "Jude", "Rev"]
BOOK = {o: b[0] for o, b in zip(OSIS, BOOKS)}
ORDER = {b[0]: i for i, b in enumerate(BOOKS)}

def ids(v):
    """Fields are lists, or lists written as strings."""
    if not v: return []
    if isinstance(v, list): return v
    try: return json.loads(v.replace("'", '"'))
    except Exception: return []

def main():
    src = sys.argv[1]
    people = json.load(open(os.path.join(src, "json", "people.json"), encoding="utf-8"))
    places = json.load(open(os.path.join(src, "json", "places.json"), encoding="utf-8"))
    verses = json.load(open(os.path.join(src, "json", "verses.json"), encoding="utf-8"))
    pslug = {r["id"]: r["fields"]["slug"] for r in people if r["fields"].get("slug")}
    lslug = {r["id"]: r["fields"]["slug"] for r in places if r["fields"].get("slug")}
    pchs, lchs = defaultdict(set), defaultdict(set)
    chap = defaultdict(lambda: {"pe": defaultdict(int), "pl": defaultdict(int)})
    for v in verses:
        f = v["fields"]; o = f.get("osisRef", "").split(".")
        if len(o) < 3 or o[0] not in BOOK: continue
        key = (BOOK[o[0]], int(o[1]))
        for pid in ids(f.get("people")):
            if pid in pslug: pchs[pslug[pid]].add(key); chap[key]["pe"][pslug[pid]] += 1
        for lid in ids(f.get("places")):
            if lid in lslug: lchs[lslug[lid]].add(key); chap[key]["pl"][lslug[lid]] += 1
    srt = lambda s: sorted(s, key=lambda k: (ORDER[k[0]], k[1]))
    out_p = {}
    for r in people:
        f = r["fields"]; s = f.get("slug")
        if not s: continue  # "wip" records are still usable; profile writers check family links against Scripture
        rel = lambda k: [pslug[i] for i in ids(f.get(k)) if i in pslug]
        out_p[s] = {"n": f.get("name") or f.get("displayTitle"), "g": (f.get("gender") or "")[:1],
                    "f": rel("father"), "m": rel("mother"), "s": rel("siblings") + rel("halfSiblingsSameFather") + rel("halfSiblingsSameMother"),
                    "p": rel("partners"), "c": rel("children"), "vc": int(f.get("verseCount") or 0),
                    "ch": [list(k) for k in srt(pchs[s])]}
    out_l = {}
    for r in places:
        f = r["fields"]; s = f.get("slug")
        if not s: continue
        lat = f.get("openBibleLat") or f.get("latitude"); lon = f.get("openBibleLong") or f.get("longitude")
        out_l[s] = {"n": f.get("esvName") or f.get("displayTitle"), "t": f.get("featureType") or "",
                    "lat": round(float(lat), 4) if lat else None, "lon": round(float(lon), 4) if lon else None,
                    "vc": int(f.get("verseCount") or 0), "ch": [list(k) for k in srt(lchs[s])]}
    out_c = {f"{b} {c}": {"pe": [s for s, _ in sorted(d["pe"].items(), key=lambda x: -x[1])],
                          "pl": [s for s, _ in sorted(d["pl"].items(), key=lambda x: -x[1])]}
             for (b, c), d in sorted(chap.items(), key=lambda kv: (ORDER[kv[0][0]], kv[0][1]))}
    os.makedirs(OUT, exist_ok=True)
    for name, obj in (("people", out_p), ("places", out_l), ("chapters", out_c)):
        json.dump(obj, open(os.path.join(OUT, f"{name}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"people {len(out_p)} | places {len(out_l)} ({sum(1 for p in out_l.values() if p['lat'] is not None)} on the map) | chapters {len(out_c)}")
    big = sorted(out_p.values(), key=lambda p: -p["vc"])
    for t in (5, 10, 20, 50): print(f"  people in {t}+ verses: {sum(1 for p in big if p['vc'] >= t)}")
    for t in (3, 5, 10): print(f"  places in {t}+ verses: {sum(1 for p in out_l.values() if p['vc'] >= t)}")

if __name__ == "__main__":
    main()
