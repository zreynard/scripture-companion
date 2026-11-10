"""Meditate: pastors in the library reading Jesus' own words aloud. For each saying, the sermons placed on its chapter
are transcribed with word times (Buzzsprout: its feed's transcript) as far as where the verse should be read, and the
saying is found by its words (any translation: a loose match), from His first word to His last.

    python tools/med_find.py find SHARD SHARDS   -> med/<shard>.jsonl   one line per reading heard
    python tools/med_find.py report              -> med/report.txt      every saying's readings, best match first

A reading: {key, ref, src, who, t, a, b (seconds from the file's start), cover (share of the saying's words heard, in
order), span (words heard / the saying's words: over 1.4 = comment in between), wps (words a second), dyn (dB between
the loud and the soft of his voice), heard (the words as he read them)}.
"""
import difflib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trim

HERE = trim.HERE
OUT = os.path.join(HERE, "med")
# the sayings to look for: only what Jesus said (the narration before His words is dropped from the match)
SAY = ["Matthew 11:28-30", "John 14:27", "John 15:5", "Matthew 6:33", "John 8:12", "John 11:25-26", "John 14:6", "John 10:11",
       "John 16:33", "Matthew 22:37-39", "John 6:35", "Matthew 7:7-8", "John 13:34-35", "Mark 8:34", "Matthew 5:8",
       "John 14:1-3", "Matthew 6:6", "Revelation 3:20", "John 10:10", "John 7:37-38", "John 6:37", "Luke 22:42", "John 8:31-32",
       "Matthew 16:24-26", "John 12:24", "John 15:13", "John 10:27-28", "Matthew 28:18-20", "John 4:13-14", "John 15:9-11",
       "Matthew 5:3-6", "Mark 10:45", "John 5:24", "Luke 9:23-24", "John 17:3", "John 20:29", "Matthew 5:14-16", "John 14:21",
       "Luke 12:32", "Matthew 10:29-31", "John 3:3", "Luke 19:10", "Mark 1:15", "John 14:18", "Matthew 9:37-38", "John 15:16"]
NAME = {"Matthew 11:28-30": "Come to Me", "John 14:27": "Peace I leave with you", "John 15:5": "I am the vine", "Matthew 6:33": "Seek first the kingdom",
        "John 8:12": "The light of the world", "John 11:25-26": "The resurrection and the life", "John 14:6": "The way, the truth and the life",
        "John 10:11": "The good shepherd", "John 16:33": "I have overcome the world", "Matthew 22:37-39": "Love the Lord your God", "John 6:35": "The bread of life",
        "Matthew 7:7-8": "Ask, seek, knock", "John 13:34-35": "Love one another", "Mark 8:34": "Take up your cross", "Matthew 5:8": "The pure in heart",
        "John 14:1-3": "Let not your heart be troubled", "Matthew 6:6": "Your Father who sees in secret", "Revelation 3:20": "I stand at the door and knock",
        "John 10:10": "Life to the full", "John 7:37-38": "If anyone thirsts", "John 6:37": "I will never cast out", "Luke 22:42": "Not My will, but Yours",
        "John 8:31-32": "The truth will set you free", "Matthew 16:24-26": "Lose your life to find it", "John 12:24": "Unless a grain of wheat falls",
        "John 15:13": "Greater love has no one", "John 10:27-28": "My sheep hear My voice", "Matthew 28:18-20": "I am with you always",
        "John 4:13-14": "Living water", "John 15:9-11": "Abide in My love", "Matthew 5:3-6": "Blessed are the poor in spirit", "Mark 10:45": "Not to be served, but to serve",
        "John 5:24": "From death to life", "Luke 9:23-24": "Deny yourself", "John 17:3": "This is eternal life", "John 20:29": "Blessed are those who have not seen",
        "Matthew 5:14-16": "You are the light of the world", "John 14:21": "Whoever loves Me", "Luke 12:32": "Fear not, little flock",
        "Matthew 10:29-31": "Not one sparrow", "John 3:3": "You must be born again", "Luke 19:10": "To seek and to save the lost", "Mark 1:15": "The kingdom of God is near",
        "John 14:18": "I will not leave you orphans", "Matthew 9:37-38": "The harvest is plentiful", "John 15:16": "You did not choose Me"}

def words_of_saying(ref):
    import pray
    t = pray.text(ref)
    q = t.find("“")
    if 0 < q < 160: t = t[q:]                                      # "Jesus said to her, “I am ..." -> His words
    t = re.sub(r"[“”‘’\"]", "", t).replace("’", "'")
    return t

def norm(w): return re.sub(r"[^a-z0-9]", "", w.lower().replace("’", "'"))

def parse(ref):
    m = re.match(r"^(.+?) (\d+):(\d+)(?:-(\d+))?$", ref)
    return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4) or m.group(3))

def plan():
    """[(item, [refs], seconds to transcribe)] — each sermon once, for every saying it may read."""
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    I = D["items"]; byb = {b["name"]: b for b in D["books"]}
    want = {}
    for ref in SAY:
        bk, c, v1, v2 = parse(ref)
        b = byb.get(bk)
        if not b: continue
        ids = next((ch["ids"] for ch in b["ch"] if ch.get("c", ch.get("n")) == c), [])
        cand = []
        for i in ids:
            it = I.get(i)
            if not it or it["who"] == "Davey" or not isinstance(it.get("audio"), str) or it.get("tr") != "sermon": continue
            m = re.match(rf"{re.escape(bk)} (\d+)(?::(\d+))?(?:[-–](?:(\d+):)?(\d+))?", it.get("pass") or "")
            frac, rank = 0.5, 2
            if m:
                c1, s1 = int(m.group(1)), int(m.group(2) or 1)
                c2 = int(m.group(3) or (m.group(1) if m.group(2) else (m.group(4) or m.group(1))))
                s2 = int(m.group(4) or 200) if m.group(2) else 200
                if c1 == c2 == c and m.group(2):
                    if not s1 <= v1 <= max(s2, s1): continue          # the sermon's passage does not hold the verse
                    frac, rank = (v1 - s1) / max(1, s2 - s1 + 1), 0 if s2 - s1 < 20 else 1
                elif c1 <= c <= c2: frac, rank = ((c - c1) + v1 / 40) / (c2 - c1 + 1), 1 if c1 == c2 else 2
            dur = float(it.get("dur") or 2400)
            need = min(dur, max(900, 240 + frac * dur + 720))
            cand.append((rank, abs(frac), i, need))
        for rank, _, i, need in sorted(cand)[:10]:
            w = want.setdefault(i, [I[i], [], 0]); w[1].append(ref); w[2] = max(w[2], need)
    return [tuple(v) for _, v in sorted(want.items())]

def find(ws, ref, pcm=None):
    """The best reading of the saying in the words ws [(start, end, word)], or None."""
    T = [norm(w) for w in words_of_saying(ref).split()]; T = [w for w in T if w]
    W = [norm(w[2]) for w in ws]; n = len(T)
    if n < 4 or len(W) < n: return None
    st = set(T); hits = [1 if w in st else 0 for w in W]
    run, best = sum(hits[:n]), []
    for i in range(len(W) - n + 1):
        if i: run += hits[i + n - 1] - hits[i - 1]
        if run >= 0.6 * n: best.append(i)
    top = None
    for i in best[::max(1, len(best) // 400)] if len(best) > 400 else best:
        seg = W[max(0, i - 3): i + int(n * 1.5) + 3]
        sm = difflib.SequenceMatcher(None, T, seg, autojunk=False)
        bl = [b for b in sm.get_matching_blocks() if b.size]
        if not bl: continue
        cover = sum(b.size for b in bl) / n
        if top is None or cover > top[0]:
            j0 = max(0, i - 3) + bl[0].b; j1 = max(0, i - 3) + bl[-1].b + bl[-1].size - 1
            top = (cover, j0, j1)
    if not top or top[0] < 0.7: return None
    cover, j0, j1 = top
    a, b = ws[j0][0], ws[j1][1]
    rec = {"ref": ref, "a": round(max(0, a - 0.25), 2), "b": round(b + 0.45, 2), "cover": round(cover, 2), "span": round((j1 - j0 + 1) / n, 2),
           "wps": round((j1 - j0 + 1) / max(0.5, b - a), 2), "heard": " ".join(w[2] for w in ws[j0:j1 + 1]),
           "before": " ".join(w[2] for w in ws[max(0, j0 - 14):j0]), "after": " ".join(w[2] for w in ws[j1 + 1:j1 + 12])}
    if pcm is not None:
        import numpy as np
        seg = pcm[int(a * 16000): int(b * 16000)]
        if len(seg) > 16000:
            fr = seg[: len(seg) // 800 * 800].reshape(-1, 800); rms = np.sqrt((fr ** 2).mean(1)) + 1e-5; sp = rms[rms > np.percentile(rms, 35)]
            rec["dyn"] = round(float(20 * np.log10(np.percentile(sp, 95) / np.percentile(sp, 20))), 1)
    return rec

def run(k, n):
    from faster_whisper import WhisperModel
    import buzz_trim as B
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    P = plan()[k::n]
    os.makedirs(OUT, exist_ok=True); f = open(os.path.join(OUT, f"{k}.jsonl"), "w")
    print(f"shard {k}/{n}: {len(P)} sermons", flush=True)
    for x, (it, refs, need) in enumerate(P, 1):
        try:
            pcm = None
            if "buzzsprout.com" in it["audio"]:
                sh, ep = B.show_ep(it["audio"]); ws4 = B.words(sh, ep) if sh else None
                if not ws4: print(f"[{x}] {it['t'][:40]!r}: no transcript", flush=True); continue
                ws = [w[:3] for w in ws4]
            else:
                data, _ = trim.fetch(it["audio"], nbytes=trim.head_bytes(it["audio"], need, it.get("dur")))
                pcm = trim.decode(data)[: int(need * 16000)]
                ws = trim.words_of(pcm, model)
            got = []
            for ref in refs:
                r = find(ws, ref, pcm)
                if r:
                    r.update({"key": ref, "src": it["id"], "who": it["who"], "t": it["t"], "via": "transcript" if pcm is None else "whisper"})
                    f.write(json.dumps(r, ensure_ascii=False) + "\n"); got.append(f"{ref} {r['cover']}")
            f.flush()
            print(f"[{x}/{len(P)}] {it['who']:8} {it['t'][:40]!r} ({need:.0f}s): {', '.join(got) or 'none'}  (of {', '.join(refs)})", flush=True)
        except Exception as ex:
            print(f"[{x}/{len(P)}] {it['t'][:40]!r}: {type(ex).__name__} {str(ex)[:80]}", flush=True)

def report():
    import glob
    R = [json.loads(l) for p in sorted(glob.glob(os.path.join(OUT, "*.jsonl"))) for l in open(p) if l.strip()]
    by = {}
    for r in R: by.setdefault(r["key"], []).append(r)
    with open(os.path.join(OUT, "report.txt"), "w") as f:
        f.write(f"{len(R)} readings of {len(by)} sayings (of {len(SAY)})\n")
        for ref in SAY:
            v = sorted(by.get(ref, []), key=lambda r: (-r["cover"], abs(r["span"] - 1)))
            f.write(f"\n## {ref}  {NAME.get(ref, '')}: {len(v)}\n   {words_of_saying(ref)}\n")
            for r in v:
                f.write(f"  {r['src']} {r['who']:8} {r['a']:7.1f}-{r['b']:7.1f}  cover {r['cover']} span {r['span']} wps {r['wps']} dyn {r.get('dyn')}  {r['t'][:40]!r}\n     … {r['before'][-60:]} [[ {r['heard']} ]] {r['after'][:60]} …\n")
    print(open(os.path.join(OUT, "report.txt")).read()[:3000])

if __name__ == "__main__":
    {"find": lambda: run(int(sys.argv[2]), int(sys.argv[3])), "report": report}[sys.argv[1]]()
