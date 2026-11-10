"""Be Led: make each prayer start and end in a pause, never on a word or in the middle of a sound.

For every prayer in tools/led_check_in.json ({"prayers": [{src, sb, e, ...}]}; sb/e = seconds before the file's end):
the stretch around its start and its end is heard again (faster-whisper small.en, word times) and its level measured
in 20 ms frames.
  start: in the quietest moment of the gap before his first word (never on the word before it);
  end:   after the amen, where the sound has died away (held quiet for 0.4 s); with music under him, as far as the
         music takes to settle (up to 15 s, with no one speaking); if it never settles before the next words: "abrupt".
Buzzsprout (its audio refuses GitHub's servers): from the transcript its feed publishes, a pause either side.

    python tools/led_check.py   -> led/check.jsonl {src, sb, e, verdict, first, last, tail_s, ...} and a line each
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trim

HERE = trim.HERE
OUT = os.path.join(HERE, "led")
AMEN = re.compile(r"amen", re.I)

def frames(pcm):
    import numpy as np
    n = len(pcm) // 320
    fr = pcm[: n * 320].reshape(-1, 320)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-5)       # dB per 20 ms

def quiet_from(db, t0, t1, thr, hold=0.4):
    """The first time in [t0, t1] (s) where the level stays under thr for `hold` seconds."""
    k0, k1, need = int(t0 / 0.02), min(len(db), int(t1 / 0.02)), int(hold / 0.02)
    run = 0
    for k in range(k0, k1):
        run = run + 1 if db[k] < thr else 0
        if run >= need: return (k - need + 1) * 0.02
    return None

def check_audio(x, it, model):
    import numpy as np
    W = x["sb"] + 25
    data, whole = trim.fetch(it["audio"], tail=True, nbytes=trim.head_bytes(it["audio"], W, it.get("dur")))
    pcm = trim.decode(data)
    if whole: pcm = pcm[-int(W * 16000):]
    else: pcm = pcm[16000 * 2:]
    TL = len(pcm) / 16000; ts, te = TL - x["sb"], TL - x["e"]
    db = frames(pcm)
    body = db[int(max(0, ts) / 0.02): int(te / 0.02)]
    speech = float(np.percentile(body, 70)); floor = float(np.percentile(body, 8))
    thr = max(floor + 6, speech - 28)
    def words(a, b):
        a, b = max(0.0, a), min(TL, b)
        return [(s + a, e + a, w) for s, e, w in trim.words_of(pcm[int(a * 16000): int(b * 16000)], model)]
    hw = words(ts - 8, ts + 10)
    after = [w for w in hw if w[0] >= ts - 0.6]
    if not after: return {"verdict": "no words at the start"}
    w0 = after[0]; prev = [w for w in hw if w[1] <= w0[0] - 0.05]
    pe = prev[-1][1] if prev else max(0.0, w0[0] - 1.2)
    lo, hi = max(pe + 0.05, w0[0] - 0.8), w0[0] - 0.04
    if hi <= lo: start = max(pe, w0[0] - 0.05)
    else:
        k0, k1 = int(lo / 0.02), max(int(lo / 0.02) + 1, int(hi / 0.02))
        start = (k0 + int(np.argmin(db[k0:k1]))) * 0.02
    tw = words(te - 12, te + 18)
    ams = [w for w in tw if AMEN.search(w[2]) and w[1] <= te + 1.5]
    last = ams[-1] if ams else max([w for w in tw if w[1] <= te + 0.8] or [None], key=lambda w: w[1] if w else 0)
    if not last: return {"verdict": "no words at the end"}
    nxt = [w for w in tw if w[0] > last[1] + 0.02]
    nw = nxt[0][0] if nxt else min(TL, last[1] + 15)
    q = quiet_from(db, last[1] + 0.3, min(nw - 0.1, last[1] + 15), thr)
    if q is not None:
        end = min(q + 0.3, nw - 0.1); verdict = "clean" if q - last[1] <= 2.5 else "settled"
    elif nw - last[1] >= 0.35 and float(np.min(db[int((last[1] + 0.05) / 0.02): int((nw - 0.05) / 0.02)] if nw - last[1] > 0.15 else [0])) < thr:
        end = last[1] + (nw - last[1]) / 2; verdict = "tight"
    else:
        end = last[1] + 0.4; verdict = "abrupt"
    tail_db = float(np.mean(db[int(end / 0.02): int(min(TL, end + 1.0) / 0.02)])) if end + 0.1 < TL else floor
    return {"sb": round(TL - start, 2), "e": round(max(0.0, TL - end), 2), "verdict": verdict, "len": round(end - start, 1),
            "first": " ".join(w[2] for w in after[:8]), "before": " ".join(w[2] for w in prev[-6:]),
            "last": " ".join(w[2] for w in tw if w[1] <= last[1] + 0.01)[-80:], "next": " ".join(w[2] for w in nxt[:8]),
            "gap_after": round(nw - last[1], 2), "tail_s": round(end - last[1], 2), "level_after_end_db": round(tail_db - speech, 1)}

def check_buzz(x, it):
    import buzz_trim as B
    sh, ep = B.show_ep(it["audio"]); ws = B.words(sh, ep) if sh else None
    if not ws: return {"verdict": "no transcript"}
    L = max(float(it.get("dur") or 0), ws[-1][1] + 1); ts, te = L - x["sb"], L - x["e"]
    after = [w for w in ws if w[0] >= ts - 0.6]
    w0 = after[0]; prev = [w for w in ws if w[1] <= w0[0] - 0.05]
    start = max((prev[-1][1] + 0.1) if prev else 0.0, w0[0] - 0.5)
    ams = [w for w in ws if AMEN.search(w[2]) and te - 12 <= w[1] <= te + 1.5]
    last = ams[-1] if ams else max([w for w in ws if w[1] <= te + 0.8], key=lambda w: w[1])
    nxt = [w for w in ws if w[0] > last[1] + 0.02]
    nw = nxt[0][0] if nxt else L
    end = min(last[1] + 1.0, nw - 0.15) if nw - last[1] > 0.4 else last[1] + 0.2
    return {"sb": round(L - start, 2), "e": round(max(0.0, L - end), 2), "verdict": "transcript" if nw - last[1] > 0.6 else "transcript-tight",
            "len": round(end - start, 1), "first": " ".join(w[2] for w in after[:8]), "before": " ".join(w[2] for w in prev[-6:]),
            "last": " ".join(w[2] for w in ws if te - 12 <= w[1] <= last[1] + 0.01)[-80:], "next": " ".join(w[2] for w in nxt[:8]), "gap_after": round(nw - last[1], 2)}

def main(k=0, n=1):
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    P = json.load(open(os.path.join(HERE, "tools", "led_check_in.json")))["prayers"][k::n]
    os.makedirs(OUT, exist_ok=True); f = open(os.path.join(OUT, f"check-{k}.jsonl"), "w")
    for i, x in enumerate(P, 1):
        it = D["items"].get(x["src"])
        try:
            if not it: r = {"verdict": "not in the app"}
            elif "buzzsprout.com" in it["audio"]: r = check_buzz(x, it)
            else: r = check_audio(x, it, model)
        except Exception as ex:
            r = {"verdict": f"error {type(ex).__name__} {str(ex)[:60]}"}
        r = {"key": x.get("key") or x["src"], "src": x["src"], "who": (it or {}).get("who"), "was": [x["sb"], x["e"]], **r}
        f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
        print(f"[{i}/{len(P)}] {r['who']} {x['src']} {r['verdict']}: {r.get('sb')}/{r.get('e')} (was {x['sb']}/{x['e']}) tail {r.get('tail_s')}s gap {r.get('gap_after')}  «{r.get('first', '')[:40]}» … «{r.get('last', '')[-40:]}» → «{r.get('next', '')[:30]}»", flush=True)

if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
