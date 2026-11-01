"""List every link whose name is shared by more than one person or place, so each can be checked against its sentence.
python tools/link_review.py <out.json>  ->  [{ctx, name, chosen, sentences, options:[{id, who, where}]}]
Reviewed answers go in data/people/link_fix.json as {ctx: {name: "p:slug" | "l:slug" | ""}}."""
import json, os, re, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from atlas import Atlas, REF_SPAN

def main():
    A = Atlas(); import app_build
    owners = defaultdict(set)
    for kind, prof in (("p", A.prof_p), ("l", A.prof_l)):
        for slug in prof:
            for n in A._names(kind, slug, all_aka=True): owners[n].add(f"{kind}:{slug}")
    units = []  # (ctx, text)
    for b, v in app_build.SUMMARIES.items():
        for x in [v["line"], *v.get("more", [])]: units.append((f"book {b}", A.link_book(x, b)))
        for c, cv in v["chapters"].items():
            for x in [cv.get("line", ""), *cv.get("more", [])]: units.append((f"{b} {c}", A.link_chapter(x, b, int(c))))
    d = A.data()
    for s, p in d["p"].items():
        for t in [p["who"], p.get("why", ""), *p["key"]]: units.append((f"card {s}", t))
    for s, l in d["l"].items():
        for t in [l["what"], l.get("why", ""), *l["key"]]: units.append((f"card {s}", t))
    items = {}
    for ctx, t in units:
        plain = re.sub(r"⟦[pl]:[^|⟧]+\|([^⟧]+)⟧", r"\1", t)
        for kind, slug, name in re.findall(r"⟦([pl]):([^|⟧]+)\|([^⟧]+)⟧", t):
            if len(owners.get(name, ())) < 2: continue
            k = (ctx, name)
            it = items.setdefault(k, {"ctx": ctx, "name": name, "chosen": f"{kind}:{slug}", "sentences": [], "options": sorted(owners[name])})
            if plain not in it["sentences"] and len(it["sentences"]) < 3: it["sentences"].append(plain)
    def desc(o):
        kind, slug = o.split(":", 1); v = (d["p"] if kind == "p" else d["l"])[slug]
        return {"id": o, "name": v["n"], "who": re.sub(r"⟦[pl]:[^|⟧]+\|([^⟧]+)⟧", r"\1", v.get("who") or v.get("what") or ""), "where": f"{v.get('first','')} → {v.get('last','')}"}
    out = []
    for it in items.values():
        it["options"] = [desc(o) for o in it["options"]]
        if it["ctx"].startswith("card "):
            s = it["ctx"][5:]; v = d["p"].get(s) or d["l"].get(s); it["card_of"] = f"{v['n']}: " + re.sub(r"⟦[pl]:[^|⟧]+\|([^⟧]+)⟧", r"\1", v.get("who") or v.get("what") or "")
        out.append(it)
    json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
    print(len(out), "shared-name links to review")

if __name__ == "__main__":
    main()
