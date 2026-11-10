"""Be Led: find the prayer each sermon closes with. The last minutes of every recording are transcribed with word times
(faster-whisper, as tools/trim.py) — or, for Buzzsprout, read from the transcript its feed publishes — and the closing
prayer is found: from the first words addressed to God after "let's pray" (or the like) through the amen.

    python tools/led_mine.py mine SHARD SHARDS   -> led/<shard>.jsonl     recordings not on Buzzsprout
    python tools/led_mine.py buzz                -> led/buzz.jsonl        Buzzsprout, from its transcripts
    python tools/led_mine.py report              -> led/report.txt        counts, then every candidate's words

One line per candidate prayer: {src, who, t, sb, e, len, music, flags, lines}. Times are seconds before the file's
end (as data/be_led.json): sb where the prayer starts, e where it ends. `lines` = [[sb_start, sb_end, sentence], ...]
from a little before the prayer to the window's end, so a reader can move the start or the end to another sentence.
Environment: IDS (comma list) to run only those.
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trim
import requests

HERE = trim.HERE
I = re.I
OUT = os.path.join(HERE, "led")
OPEN = re.compile(r"\b(let'?s pray|let us pray|let me pray|pray with me|pray together|pray over (you|us)|we pray\b(?=\.)|bow (your|our) heads?|close (your|our) eyes|let'?s (go to|talk to|lift (this|it) up to) (the lord|god|him|jesus)|i'?m (going|gonna) (to )?pray|i want to pray|let'?s go to prayer|in prayer\b(?=[.!]))", I)
ADDR = re.compile(r"^(and |so |oh,? |o |now,? |yes,? )?(heavenly |dear |holy |gracious |good |sweet |almighty |precious |loving |righteous |our |mighty |faithful |great )?(father|lord|god|jesus|abba|holy spirit|lord jesus|father god)\b(?! (said|says|is|was|has|had|will|wants|did|does|told|tells|knows|calls|called|gave|sent)\b)", I)
AMEN = re.compile(r"\bamen\b", I)
SECOND = re.compile(r"\b(you|your|yours|thee|thou|thy)\b", I)
TEACHY = re.compile(r"\b(turn (with me )?to|verse \d+|chapter \d+|he says here|paul says|the text|this passage|in context|the greek|the hebrew)\b", I)
FLAGS = {
    "refs": r"\b(this text|this passage|verse \d+|as we (saw|read|looked|studied)|this morning'?s (text|passage)|this letter|this book|this series|chapter \d+)\b",
    "logistics": r"\b(communion|the elements|the bread and the cup|stand (up|with me)|connect card|card in|offering|tithe|giv(e|ing) (online|today)|campus|baptism|next steps|this week(end)? at|sign up|small groups?|serve team)\b",
    "altar": r"\b(pray (this|after me|with me after)|repeat after me|raise (your|a) hand|come forward|come down front|if you prayed that|prayer (team|counselors?)|text the word|first time (decision|commitment))\b",
    "word": r"\b(read(ing)? (your|the|our|my) (bible|word|scripture)|stud(y|ying) (your|the) (word|bible|scriptures?)|as we (walk|go|work) through|this study|open (your|the) word|in your word this week)\b",
}

def sents(ws):
    """Sentences [(t0, t1, text)] from words [(start, end, word)]."""
    out, row, t0 = [], [], None
    for a, b, w in ws:
        if t0 is None: t0 = a
        row.append(w)
        if re.search(r"[.?!]$", w): out.append((t0, b, " ".join(row))); row, t0 = [], None
    if row: out.append((t0, ws[-1][1], " ".join(row)))
    return out

def prayers(S, end_at):
    """Closing prayer candidates [(i_start, i_amen)] in the sentences S; amens after end_at (seconds) are the outro's."""
    amen = [k for k, s in enumerate(S) if AMEN.search(s[2]) and s[0] <= end_at + 20]
    out = []
    for a in amen:
        prev = max([k for k in amen if k < a and S[a][0] - S[k][1] > 25] or [-1])   # an amen right before is the same prayer
        lo = prev + 1
        op = [k for k in range(lo, a + 1) if OPEN.search(S[k][2]) and S[a][0] - S[k][0] < 420]
        st = None
        if op:
            o = op[-1] if S[a][0] - S[op[-1]][0] >= 40 else op[0]          # "let's pray ... (prayer) ... let's pray together" — the first that leaves a prayer
            st = next((k for k in range(o, min(a, o + 4) + 1) if ADDR.search(S[k][2])), None)
            if st is None:
                tail = re.split(OPEN, S[o][2], maxsplit=1)
                st = o + 1 if o < a and (not tail or len(tail[-1].split()) < 4) else o
        else:                                                                  # no "let's pray": the earliest address to God from which it is prayer
            for k in range(lo, a + 1):
                if not ADDR.search(S[k][2]): continue
                rest = S[k:a + 1]
                if sum(1 for s in rest if SECOND.search(s[2])) >= 0.5 * len(rest) and not any(TEACHY.search(s[2]) for s in rest):
                    st = k; break
        if st is not None and st <= a: out.append((st, a))
    # drop a candidate inside a longer one
    out = [c for c in out if not any(o != c and o[0] <= c[0] and o[1] >= c[1] for o in out)]
    return out

def music_db(pcm, a, b):
    """The quiet frames' level against the speech (dB) between a and b seconds in pcm: near silence (< -14) = no music."""
    import numpy as np
    seg = pcm[int(a * 16000): int(b * 16000)]
    if len(seg) < 16000 * 10: return None
    fr = seg[: len(seg) // 800 * 800].reshape(-1, 800); rms = np.sqrt((fr ** 2).mean(1)) + 1e-5
    return round(float(20 * np.log10(np.percentile(rms, 10) / np.percentile(rms, 50))), 1)

def records(it, ws, TL, pcm=None, via="whisper"):
    """Candidates for one recording: ws are words timed within a window of TL seconds that ends at the file's end."""
    S = sents(ws)
    e_trim = float(it.get("e") or 0)
    out = []
    for st, a in prayers(S, TL - e_trim):
        t0, t1 = S[st][0], S[a][1]
        if not 40 <= t1 - t0 <= 420: continue
        text = " ".join(s[2] for s in S[st:a + 1])
        lo = max(0.0, t0 - 45)
        rec = {"src": it["id"], "who": it["who"], "t": it["t"], "pass": it.get("pass", ""), "via": via,
               "sb": round(TL - t0 + 0.3, 1), "e": round(max(0.0, TL - t1 - 0.5), 1), "len": round(t1 - t0),
               "music_db": music_db(pcm, t0, t1) if pcm is not None else None,
               "flags": {k: sorted({m.group(0).lower() for m in re.finditer(p, text, I)})[:5] for k, p in FLAGS.items()},
               "lines": [[round(TL - s[0], 1), round(TL - s[1], 1), s[2]] for s in S if s[0] >= lo]}
        rec["music"] = rec["music_db"] is None or rec["music_db"] <= -14     # true: none of its own, the soaking music plays
        out.append(rec)
    return out

def blocks(pcm, TL):
    """The voice's level in 10 s blocks: [seconds before the end at the block's start, quiet frames dB, middle dB]."""
    import numpy as np
    out = []
    for a in range(0, int(len(pcm) / 16000) - 5, 10):
        seg = pcm[a * 16000:(a + 10) * 16000]
        fr = seg[: len(seg) // 800 * 800].reshape(-1, 800); rms = np.sqrt((fr ** 2).mean(1)) + 1e-5
        out.append([round(TL - a, 1), round(float(20 * np.log10(np.percentile(rms, 10))), 1), round(float(20 * np.log10(np.percentile(rms, 50))), 1)])
    return out

def window(it, ws, TL, pcm=None, via="whisper"):
    """Everything heard in the closing window: every sentence (seconds before the end) and the levels."""
    return {"src": it["id"], "who": it["who"], "t": it["t"], "pass": it.get("pass", ""), "via": via, "e_trim": float(it.get("e") or 0), "TL": round(TL, 1),
            "lines": [[round(TL - s[0], 1), round(TL - s[1], 1), s[2]] for s in sents(ws)], "blocks": blocks(pcm, TL) if pcm is not None else []}

def pick(buzz):
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    ID = {x for x in os.environ.get("IDS", "").split(",") if x}
    L = [it for it in D["items"].values() if isinstance(it.get("audio"), str) and it.get("tr") == "sermon" and not it.get("nar")
         and it["who"] != "Davey" and ("buzzsprout.com" in it["audio"]) == buzz and (not ID or it["id"] in ID)]
    return sorted(L, key=lambda i: i["id"])

def mine(k, n):
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    todo = pick(False)[k::n]
    os.makedirs(OUT, exist_ok=True); f = open(os.path.join(OUT, f"{k}.jsonl"), "w")
    print(f"shard {k}/{n}: {len(todo)} recordings", flush=True); found = 0
    for x, it in enumerate(todo, 1):
        try:
            W = min(float(it.get("e") or 0) + 400, 700)
            data, whole = trim.fetch(it["audio"], tail=True, nbytes=trim.head_bytes(it["audio"], W, it.get("dur")))
            pcm = trim.decode(data)
            if whole: pcm = pcm[-int(W * 16000):]
            pcm = pcm[16000 * 2:] if not whole else pcm      # the first moments of a cut-in tail may be a broken frame
            TL = len(pcm) / 16000
            ws = trim.words_of(pcm, model)
            rs = records(it, ws, TL, pcm)
            f.write(json.dumps(window(it, ws, TL, pcm), ensure_ascii=False) + "\n")
            f.flush(); found += bool(rs)
            print(f"[{x}/{len(todo)}] {it['who']:8} {it['t'][:44]!r}: " + ("; ".join(f"{r['len']}s at -{r['sb']:.0f} music {r['music_db']}" for r in rs) or "none"), flush=True)
        except Exception as ex:
            print(f"[{x}/{len(todo)}] {it['t'][:44]!r}: {type(ex).__name__} {str(ex)[:80]}", flush=True)
    print(f"done: {found} of {len(todo)} with a prayer", flush=True)

def buzz():
    import buzz_trim as B
    todo = pick(True)
    os.makedirs(OUT, exist_ok=True); f = open(os.path.join(OUT, "buzz.jsonl"), "w")
    shows = sorted({B.show_ep(it["audio"])[0] for it in todo} - {None}); avail = {}
    for sh in shows: avail[sh] = B.with_transcripts(sh); print(f"feed {sh}: {len(avail[sh])} with transcripts", flush=True)
    found = 0
    for x, it in enumerate(todo, 1):
        sh, ep = B.show_ep(it["audio"])
        if not sh or ep not in avail.get(sh, set()): continue
        ws4 = B.words(sh, ep)
        if not ws4: continue
        L = max(float(it.get("dur") or 0), ws4[-1][1] + 1)
        W = min(float(it.get("e") or 0) + 400, 700); off = L - W
        ws = [(a - off, b - off, w) for a, b, w, _ in ws4 if a >= off]
        rs = records(it, ws, W, via="transcript")
        f.write(json.dumps(window(it, ws, W, via="transcript"), ensure_ascii=False) + "\n")
        f.flush(); found += bool(rs)
        print(f"[{x}/{len(todo)}] {it['who']:8} {it['t'][:44]!r}: " + ("; ".join(f"{r['len']}s at -{r['sb']:.0f}" for r in rs) or "none"), flush=True)
    print(f"done: {found} of {len(todo)} with a prayer", flush=True)

def report():
    import glob
    R = [json.loads(l) for p in sorted(glob.glob(os.path.join(OUT, "*.jsonl"))) if not p.endswith("lp.jsonl") for l in open(p) if l.strip()]
    by = {}
    for r in R: by.setdefault(r["who"], []).append(r)
    with open(os.path.join(OUT, "report.txt"), "w") as f:
        f.write(f"{len(R)} recordings\n")
        for w, v in sorted(by.items()):
            f.write(f"  {w}: {len(v)} recordings heard\n")
    print(open(os.path.join(OUT, "report.txt")).read())

if __name__ == "__main__":
    {"mine": lambda: mine(int(sys.argv[2]), int(sys.argv[3])), "buzz": buzz, "report": report}[sys.argv[1]]()
