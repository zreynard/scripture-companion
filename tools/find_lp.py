"""Guided: is there a pastor in the library who prays the Lord's Prayer through, line by line? Every sermon placed on
Matthew 6 or Luke 11 (and a few on prayer) is transcribed in full with word times (Buzzsprout: its feed's transcript),
and every stretch where the prayer's lines come close together is written out with its times.

    python tools/find_lp.py   -> led/lp.txt (to read) and led/lp.jsonl {src, who, t, at, lines: [[t0, t1, sentence]]}
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trim, led_mine

HERE = trim.HERE
I = re.I
LINES = {"father": r"\bour father\b", "heaven": r"\b(who art|who is|in) heaven\b", "hallowed": r"\bhallow", "kingdom": r"\b(your|thy) kingdom come\b",
         "will": r"\b(your|thy) will be done\b", "earth": r"\bon earth as\b", "bread": r"\bdaily bread\b", "forgive": r"\bforgive us\b",
         "debtors": r"\bas we (also )?(have )?forg[ia]ve?n?\b|\bour debtors\b|\bthose who trespass\b", "lead": r"\blead us not\b|\bnot lead us\b|\binto temptation\b",
         "deliver": r"\bdeliver us\b|\bfrom (the )?evil( one)?\b", "doxology": r"\b(yours|thine) is the kingdom\b"}
TITLE = r"lord'?s prayer|our father|teach us to pray|pray and fast|fatherhood of god|being with god in quiet|surviving to thriving|secret of prayer|most important part|^pray$|^19\.1"

def candidates():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    I_ = D["items"]; ids = set()
    for b in D["books"]:
        if b["name"] in ("Matthew", "Luke"):
            for c in b["ch"]:
                if (b["name"], c.get("c", c.get("n"))) in (("Matthew", 6), ("Luke", 11)): ids |= set(c["ids"])
    ids |= {i for i, it in I_.items() if re.search(TITLE, it["t"] or "", I) or re.match(r"(Matthew 6|Luke 11)\b", it.get("pass") or "")}
    return [I_[i] for i in sorted(ids) if i in I_ and isinstance(I_[i].get("audio"), str) and I_[i]["who"] != "Davey"]

def clusters(S):
    """Stretches where 5+ of the prayer's lines are said within 4 minutes."""
    hits = sorted((s[0], k, name) for k, s in enumerate(S) for name, p in LINES.items() if re.search(p, s[2], I))
    out = []
    for j, (t, k, _) in enumerate(hits):
        win = [h for h in hits[j:] if h[0] - t <= 240]
        names = {h[2] for h in win}
        if len(names) >= 5:
            a, b = win[0][1], win[-1][1]
            if out and a <= out[-1][1] + 3: out[-1] = (out[-1][0], max(b, out[-1][1]), out[-1][2] | names)
            else: out.append((a, b, names))
    return out

def main():
    from faster_whisper import WhisperModel
    import buzz_trim as B
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    os.makedirs(led_mine.OUT, exist_ok=True)
    txt, js = open(os.path.join(led_mine.OUT, "lp.txt"), "w"), open(os.path.join(led_mine.OUT, "lp.jsonl"), "w")
    C = candidates(); print(f"{len(C)} candidates", flush=True)
    for it in C:
        try:
            if "buzzsprout.com" in it["audio"]:
                sh, ep = B.show_ep(it["audio"]); ws4 = B.words(sh, ep) if sh else None
                if not ws4: print(f"{it['t'][:50]!r}: no transcript", flush=True); continue
                ws = [w[:3] for w in ws4]
            else:
                data, _ = trim.fetch(it["audio"], nbytes=400_000_000)
                ws = trim.words_of(trim.decode(data), model)
            S = led_mine.sents(ws)
            cs = clusters(S)
            print(f"{it['who']:8} {it['id']} {it['t'][:50]!r}: {len(cs)} stretch(es)", flush=True)
            for a, b, names in cs:
                lo, hi = max(0, a - 6), min(len(S), b + 8)
                txt.write(f"\n=== {it['id']} {it['who']} {it['t']!r}  {S[a][0]:.0f}s–{S[b][1]:.0f}s  lines: {len(names)} {sorted(names)}\n")
                for s in S[lo:hi]: txt.write(f"  {s[0]:7.1f} {s[1]:7.1f}  {s[2]}\n")
                js.write(json.dumps({"src": it["id"], "who": it["who"], "t": it["t"], "at": [S[a][0], S[b][1]], "names": sorted(names),
                                     "lines": [[round(s[0], 1), round(s[1], 1), s[2]] for s in S[lo:hi]]}, ensure_ascii=False) + "\n")
            txt.flush(); js.flush()
        except Exception as ex:
            print(f"{it['t'][:50]!r}: {type(ex).__name__} {str(ex)[:80]}", flush=True)

if __name__ == "__main__":
    main()
