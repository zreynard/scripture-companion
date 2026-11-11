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
# more of what Jesus said, searched for in a second pass (SET=2)
SAY2 = """Matthew 4:4|Matthew 4:17|Matthew 4:19|Matthew 5:7|Matthew 5:9|Matthew 5:10-12|Matthew 5:13|Matthew 5:17|Matthew 5:43-45|Matthew 5:48|Matthew 6:14-15|Matthew 6:19-21|Matthew 6:22-23|Matthew 6:24|Matthew 6:25-27|Matthew 6:28-30|Matthew 6:34|Matthew 7:1-2|Matthew 7:3-5|Matthew 7:9-11|Matthew 7:12|Matthew 7:13-14|Matthew 7:21|Matthew 7:24-25|Matthew 8:26|Matthew 9:12-13|Matthew 9:22|Matthew 10:16|Matthew 10:28|Matthew 10:32-33|Matthew 10:37-39|Matthew 11:25-27|Matthew 12:30|Matthew 12:34-35|Matthew 12:50|Matthew 13:44-46|Matthew 14:27|Matthew 14:31|Matthew 16:15|Matthew 16:18|Matthew 17:20|Matthew 18:3-4|Matthew 18:12-14|Matthew 18:20|Matthew 18:21-22|Matthew 19:14|Matthew 19:26|Matthew 20:26-28|Matthew 21:22|Matthew 22:21|Matthew 23:11-12|Matthew 23:37|Matthew 24:35|Matthew 24:42|Matthew 25:21|Matthew 25:34-36|Matthew 25:40|Matthew 26:26-28|Matthew 26:38|Matthew 26:39|Matthew 26:41|Matthew 27:46|Mark 1:15|Mark 1:17|Mark 2:17|Mark 4:39-40|Mark 5:34|Mark 5:36|Mark 8:34|Mark 8:36-37|Mark 9:23|Mark 9:35|Mark 10:14-15|Mark 10:27|Mark 11:22-24|Mark 11:25|Mark 12:29-31|Mark 14:36|Mark 16:15|Luke 4:18-19|Luke 5:31-32|Luke 6:27-28|Luke 6:31|Luke 6:35-36|Luke 6:37-38|Luke 6:45|Luke 6:46|Luke 7:47|Luke 7:50|Luke 8:48|Luke 9:23-24|Luke 9:62|Luke 10:2|Luke 10:20|Luke 10:41-42|Luke 11:9-10|Luke 11:13|Luke 11:28|Luke 12:6-7|Luke 12:15|Luke 12:22-24|Luke 12:32|Luke 12:34|Luke 12:48|Luke 13:3|Luke 14:11|Luke 14:27|Luke 15:7|Luke 15:10|Luke 17:21|Luke 18:14|Luke 18:27|Luke 21:33|Luke 22:19-20|Luke 22:32|Luke 23:34|Luke 23:43|Luke 23:46|Luke 24:38-39|John 3:3|John 3:5-7|John 3:16-17|John 4:23-24|John 4:34|John 4:35|John 5:39-40|John 6:27|John 6:29|John 6:40|John 6:44|John 6:47-48|John 6:51|John 6:63|John 8:7|John 8:11|John 8:36|John 8:58|John 9:4-5|John 10:9|John 10:14-15|John 10:30|John 11:40|John 12:24|John 12:26|John 12:32|John 12:46|John 13:7|John 13:14-15|John 13:34-35|John 14:9|John 14:12-14|John 14:15-17|John 14:23|John 14:26|John 15:1-2|John 15:4|John 15:7-8|John 15:12|John 15:14-15|John 15:18-19|John 16:7|John 16:13|John 16:20-22|John 16:24|John 17:15-17|John 17:20-21|John 17:24|John 19:30|John 20:21|John 20:27|John 21:22|Acts 1:8|Acts 20:35|Revelation 1:17-18|Revelation 2:4-5|Revelation 2:10|Revelation 21:5-6|Revelation 22:12-13|Revelation 22:20""".split("|")
if os.environ.get("SET") == "2": SAY = SAY2
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

def check():
    """Every chosen clip (tools/med_check.json) heard again on its own, with a few seconds around it: the words inside
    the clip are in [[ ]], so its first and last word can be checked."""
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    for x in json.load(open(os.path.join(HERE, "tools", "med_check.json")))["sayings"]:
        it = D["items"].get(x["src"])
        if not it: print(f"== {x['ref']}: recording not in the app"); continue
        if "buzzsprout.com" in it["audio"]: print(f"== {x['ref']} {x['who']}: Buzzsprout (times from its transcript, not checked)"); continue
        try:
            data, _ = trim.fetch(it["audio"], nbytes=trim.head_bytes(it["audio"], x["b"] + 20, it.get("dur")))
            pcm = trim.decode(data); lo = max(0, x["a"] - 6)
            ws = [(a + lo, b + lo, w) for a, b, w in trim.words_of(pcm[int(lo * 16000): int((x["b"] + 6) * 16000)], model)]
            inn = [w for w in ws if w[0] >= x["a"] - 0.05 and w[1] <= x["b"] + 0.15]
            txt = " ".join(("[[ " if w is inn[0] else "") + w[2] + (" ]]" if w is inn[-1] else "") for w in ws) if inn else " ".join(w[2] for w in ws)
            cut = [w for w in ws if w[0] < x["a"] - 0.05 < w[1] or w[0] < x["b"] + 0.15 < w[1]]
            print(f"== {x['ref']} {x['who']} {x['a']}-{x['b']}{'  CUTS A WORD: ' + ', '.join(f'{w[2]}@{w[0]:.2f}-{w[1]:.2f}' for w in cut) if cut else ''}\n   {txt}", flush=True)
            near = lambda t: " ".join(f"{w[2]}@{w[0]:.2f}-{w[1]:.2f}" for w in ws if abs(w[0] - t) < 4 or abs(w[1] - t) < 4)
            print(f"   START: {near(x['a'])}\n   END:   {near(x['b'])}", flush=True)
        except Exception as ex:
            print(f"== {x['ref']}: {type(ex).__name__} {str(ex)[:80]}", flush=True)

def fix():
    """Every reading in tools/med_check.json set on His exact first and last words: the stretch around it heard
    (small.en), matched to the saying's text "t", the start put in the pause before the first word and the end in the
    pause after the last; and the file's true length counted frame by frame (some headers understate it)."""
    from faster_whisper import WhisperModel
    import clip_probe as CP
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    out = []
    for x in json.load(open(os.path.join(HERE, "tools", "med_check.json")))["sayings"]:
        it = D["items"].get(x["src"]); r = dict(x)
        try:
            if not it: r["note"] = "recording not in the app"; out.append(r); continue
            if "buzzsprout.com" in it["audio"]: r["note"] = "Buzzsprout: kept as found"; out.append(r); continue
            data = requests.get(it["audio"], headers=trim.H, timeout=900).content
            pcm = trim.decode(data); lo = max(0, x["a"] - 5); hi = x["b"] + 5
            ws = [(a + lo, b + lo, w) for a, b, w in trim.words_of(pcm[int(lo * 16000): int(hi * 16000)], model)]
            T = [norm(w) for w in x["t"].split() if norm(w)]; W = [norm(w[2]) for w in ws]
            sm = difflib.SequenceMatcher(None, T, W, autojunk=False); bl = [b for b in sm.get_matching_blocks() if b.size]
            if not bl: r["note"] = "words not found"; out.append(r); continue
            j0, j1 = bl[0].b, bl[-1].b + bl[-1].size - 1
            cover = sum(b.size for b in bl) / max(1, len(T))
            prev_end = ws[j0 - 1][1] if j0 > 0 else ws[j0][0] - 1; nxt = ws[j1 + 1][0] if j1 + 1 < len(ws) else ws[j1][1] + 1
            a = max(prev_end + 0.05, ws[j0][0] - 0.15); b = min(nxt - 0.05, ws[j1][1] + 0.3)
            r.update(a=round(a, 2), b=round(b, 2), cover=round(cover, 2), heard=" ".join(w[2] for w in ws[j0:j1 + 1]),
                     before=" ".join(w[2] for w in ws[max(0, j0 - 6):j0]), after=" ".join(w[2] for w in ws[j1 + 1:j1 + 6]),
                     gap_before=round(ws[j0][0] - prev_end, 2), gap_after=round(nxt - ws[j1][1], 2), was=[x["a"], x["b"]])
            if not re.search(r"\.(m4a|mp4)(\?|$)", it["audio"]):
                sc = CP.scan(data)
                if sc: r["Lt"] = round(sc[1], 3); r["Le"] = round(sc[2], 3)
        except Exception as ex: r["err"] = f"{type(ex).__name__} {str(ex)[:80]}"
        out.append(r); print(json.dumps(r, ensure_ascii=False), flush=True)
    os.makedirs(OUT, exist_ok=True); json.dump({"sayings": out}, open(os.path.join(OUT, "fixed.json"), "w"), indent=1, ensure_ascii=False)

if __name__ == "__main__":
    if sys.argv[1] == "fix": fix(); sys.exit()
    {"find": lambda: run(int(sys.argv[2]), int(sys.argv[3])), "report": report, "check": check}[sys.argv[1]]()
