"""Every name tappable: report Bible names that appear in the app's text without a link.
python tools/name_coverage.py [--list]   (reads out/site/index.html and out/site/atlas.json after a build)
A known name = any person or place name in the people/places data. Names inside "(Genesis 39)" are ignored."""
import json, os, re, sys
from collections import Counter
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from atlas import Atlas, NEVER_LINK, REF_SPAN

OUT = []
COMMON = {"Sin", "Even", "Hope", "Grace", "Rock", "Light", "Life", "Peace", "Joy", "Gate", "Most", "Holy", "Great", "Salt", "Chief", "Hand"}

def main():
    A = Atlas(); d = A.data()
    # summaries as the app shows them
    import app_build
    texts = []
    for b, v in app_build.SUMMARIES.items():
        for x in [v["line"], *v.get("more", [])]: texts.append(("book " + b, A.link_book(x, b)))
        for c, cv in v["chapters"].items():
            for x in [cv.get("line", ""), *cv.get("more", [])]: texts.append((f"{b} {c}", A.link_chapter(x, b, int(c))))
    for s, p in d["p"].items():
        for t in [p["who"], p.get("why", ""), *p["key"]]: texts.append(("card " + s, t))
    for s, l in d["l"].items():
        for t in [l["what"], l.get("why", ""), *l["key"]]: texts.append(("card " + s, t))
    names = {v["n"] for v in A.src_p.values() if v.get("n")} | {v["n"] for v in A.src_l.values() if v.get("n")}
    names = {n for n in names if n and len(n) > 2 and n[0].isupper() and n not in NEVER_LINK and n not in
             {"Israel", "Judah", "The", "Son", "King", "Most High", "Satan", "Devil", "Lord", "River", "Sea", "Great Sea"}}
    pat = re.compile(r"(?<![\w'’])(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")(?![\w])")
    miss, where = Counter(), {}
    for w, t in texts:
        plain = re.sub(r"⟦[pl]:[^|⟧]+\|[^⟧]+⟧", lambda m: " " * len(m.group(0)), t)
        plain = REF_SPAN.sub(lambda m: " " * len(m.group(0)), plain)
        linked = set(re.findall(r"⟦[pl]:[^|⟧]+\|([^⟧]+)⟧", t))
        own = set()
        if w.startswith("card "):
            v = d["p"].get(w[5:]) or d["l"].get(w[5:]); own = {v["n"], *A._names("p" if w[5:] in d["p"] else "l", w[5:], True)}
        found = {m.group(1) for m in pat.finditer(plain) if not (m.group(1) in COMMON and (m.start() == 0 or plain[max(0, m.start() - 2):m.start()].strip() in (".", "")))}
        for n in found - linked - own:  # a repeat of a name already linked in this line, or a card naming itself, is fine
            miss[n] += 1; where.setdefault(n, w)
            OUT.append({"ctx": w, "name": n, "sentence": re.sub(r"⟦[pl]:[^|⟧]+\|([^⟧]+)⟧", r"\1", t)})
    total = sum(len(re.findall(r"⟦", t)) for _, t in texts)
    print(f"linked names: {total} | unlinked mentions of known names: {sum(miss.values())} ({len(miss)} distinct)")
    if "--json" in sys.argv:
        json.dump(OUT, open(sys.argv[sys.argv.index("--json") + 1], "w"), ensure_ascii=False, indent=1)
    if "--list" in sys.argv:
        for n, c in miss.most_common(): print(f"  {c:4} {n}  e.g. {where[n]}")

if __name__ == "__main__":
    main()
