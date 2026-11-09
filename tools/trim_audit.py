"""Check the cuts: what a listener hears right after each recording's start point, what was cut before it, and the
same around the end. Speech recognition with word times (as tools/trim.py), then a report to read.

    python tools/trim_audit.py audit SHARD SHARDS   -> audit/<shard>.jsonl   one line per recording
    python tools/trim_audit.py report               -> audit/report.txt     flags by source, then every recording's words

Which recordings (environment): SRCS (comma list of sources), IDS (comma list of ids), PER (a random sample per source,
0 = all), SEED. Runs on GitHub's servers (ffmpeg + faster-whisper); Buzzsprout refuses them, so its recordings are skipped.
"""
import glob, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trim
import requests

HERE = trim.HERE
I = re.I
# language a publisher or church adds around a sermon (if the listener still hears it, the cut is too early)
ADD = [r"\b(give|giving|generosity|offering|tithe|donat\w+|support (this|our|the) ministry|partner with us)\b",
       r"\b(podcast|episode|subscribe|broadcast|radio|station|program)\b", r"\b(www\.|dot org|dot com|\.org\b|\.com\b)",
       r"\b(announcement|sign up|register|registration|baby dedication|baptism sunday|small groups?|connect card|next steps)\b",
       r"\bwelcome (to|back to) (\w+ ){0,3}(church|campus|service|worship|the show|this)\b", r"\b(you'?re listening to|thanks? for (listening|joining us|tuning in))\b",
       r"\b(stay tuned|after this|coming up|today on)\b", r"\b(order|request|copy of|free (resource|gift|download)|study guide)\b"]
# language that means the teaching has begun (if it was cut, the cut is too late)
TEACH = [r"\b(turn (with me )?(in your bibles? )?to|open (up )?your bibles?|if you have (a|your) bible|grab (a|your) bible)\b",
         r"\b(chapter|verse) \d+", r"\b(the (lord|scripture|text|passage) (says|tells))\b", r"\blet'?s pray\b", r"\bfather,? (we|i) (thank|pray|ask)\b"]

def items_all():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    return D, [it for it in D["items"].values() if it.get("audio") and not it.get("nar") and it.get("tr") != "intro" and it["src"] in trim.RULES]

def pick():
    D, L = items_all()
    SR = {x for x in os.environ.get("SRCS", "").split(",") if x}; ID = {x for x in os.environ.get("IDS", "").split(",") if x}
    L = [i for i in L if (not SR or i["src"] in SR) and (not ID or i["id"] in ID) and "buzzsprout.com" not in i["audio"]]
    per = int(os.environ.get("PER", "0") or 0)
    if per and not ID:
        rnd = random.Random(int(os.environ.get("SEED", "7"))); by = {}
        for i in sorted(L, key=lambda x: x["id"]): by.setdefault(i["src"], []).append(i)
        L = [x for v in by.values() for x in rnd.sample(v, min(per, len(v)))]
    return D, sorted(L, key=lambda i: i["id"])

def head_bytes(url, secs, dur):
    """Enough of the file's opening to hold `secs` seconds (from its size and length), within reason."""
    try:
        r = requests.head(url, headers=trim.H, timeout=60, allow_redirects=True); n = int(r.headers.get("content-length") or 0)
    except Exception: n = 0
    if n and dur: return min(n, int(n * min(1.0, (secs + 30) / dur) * 1.15) + 400_000)
    return int((secs + 30) * 24_000)   # about 192 kbit/s

def sentences(ws, lo, hi, off=0.0):
    out, row, t = [], [], None
    for w in ws:
        if w[0] < lo or w[0] >= hi: continue
        if t is None: t = w[0]
        row.append(w[2])
        if re.search(r"[.?!]$", w[2]): out.append([round(t + off, 1), " ".join(row)]); row, t = [], None
    if row: out.append([round(t + off, 1), " ".join(row)])
    return out

def hits(pats, text): return [m.group(0) for p in pats for m in re.finditer(p, text, I)][:6]

def audit(k, n):
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    D, todo = pick(); todo = todo[k::n]
    os.makedirs(os.path.join(HERE, "audit"), exist_ok=True)
    path = os.path.join(HERE, "audit", f"{k}.jsonl"); f = open(path, "w")
    print(f"shard {k}/{n}: {len(todo)} recordings", flush=True)
    for x, it in enumerate(todo, 1):
        s, e, dur = float(it.get("s") or 0), float(it.get("e") or 0), float(it.get("dur") or 0)
        rec = {"id": it["id"], "src": it["src"], "t": it["t"], "who": it["who"], "pass": it.get("pass", ""), "s": s, "e": e, "dur": dur}
        try:
            need = s + 100
            whole = bool(re.search(r"\.(m4a|mp4|m4v)(\?|$)", it["audio"], I))
            if whole: data, _ = trim.fetch(it["audio"])
            else:
                nb = head_bytes(it["audio"], need, dur); data, _ = trim.fetch(it["audio"], nbytes=nb)
            pcm = trim.decode(data); have = len(pcm) / 16000
            lo = max(0.0, s - 75)
            hw = trim.words_of(pcm[int(lo * 16000): int(min(have, s + 100) * 16000)], model)
            ws = [(a + lo, b + lo, w) for a, b, w in hw]
            rec["before"] = sentences(ws, lo, s); rec["after"] = sentences(ws, s, s + 100)
            if s > 80:   # what the very start of the file is (the part that is cut)
                op = trim.words_of(pcm[: 45 * 16000], model); rec["opening"] = sentences(op, 0, 45)
            if whole: tl = pcm
            else: tail, _ = trim.fetch(it["audio"], tail=True, nbytes=int(max(e + 120, 150) * 26_000)); tl = trim.decode(tail)
            TL = len(tl) / 16000; a0 = max(0.0, TL - e - 90)
            tw = trim.words_of(tl[int(a0 * 16000):], model); tw = [(a + a0, b + a0, w) for a, b, w in tw]
            rec["end_before"] = sentences(tw, a0, TL - e, off=-TL); rec["end_after"] = sentences(tw, TL - e, TL, off=-TL)
            aft = " ".join(z[1] for z in rec["after"] if z[0] < s + 60).lower(); bef = " ".join(z[1] for z in rec["before"]).lower()
            rec["flags"] = {"added_after_start": hits(ADD, aft), "teaching_before_start": hits(TEACH, bef) if s > 0 else [],
                            "added_before_end": hits(ADD, " ".join(z[1] for z in rec["end_before"][-4:]).lower())}
            if not rec["after"]: rec["flags"]["silent_after_start"] = ["no words in 100 s"]
        except Exception as ex:
            rec["error"] = f"{type(ex).__name__} {str(ex)[:120]}"
        f.write(json.dumps(rec) + "\n"); f.flush()
        fl = {k2: v for k2, v in rec.get("flags", {}).items() if v}
        print(f"[{x}/{len(todo)}] {it['src']:18} s={s:6.1f} e={e:5.1f} {it['t'][:40]!r} {fl or ''} {rec.get('error', '')}", flush=True)
    f.close()

def report():
    recs = [json.loads(l) for p in sorted(glob.glob(os.path.join(HERE, "audit", "*.jsonl"))) for l in open(p) if l.strip()]
    by = {}
    for r in recs: by.setdefault(r["src"], []).append(r)
    out = ["CUTS AUDIT", ""]
    for src, L in sorted(by.items()):
        f = lambda k: sum(1 for r in L if r.get("flags", {}).get(k))
        out.append(f"{src:22} {len(L):4} checked  errors {sum(1 for r in L if r.get('error')):3}  added-after-start {f('added_after_start'):3}  "
                   f"teaching-before-start {f('teaching_before_start'):3}  silent-after-start {f('silent_after_start'):3}  added-before-end {f('added_before_end'):3}")
    out.append("")
    for src, L in sorted(by.items()):
        out.append("=" * 100); out.append(src); out.append("=" * 100)
        for r in L:
            fl = {k: v for k, v in r.get("flags", {}).items() if v}
            out.append(f"\n## {r['id']} | {r['t'][:70]} | {r['who']} | {r['pass']} | start {r['s']}s  end -{r['e']}s  len {r['dur']}{'  (was +%s -%s)' % tuple(r['old']) if r.get('old') else ''}{'  [' + r['speaker_fix'] + ']' if r.get('speaker_fix') else ''}{'  end: ' + r['end_why'] if r.get('end_why') else ''}  {'FLAGS ' + json.dumps(fl) if fl else ''} {r.get('error', '')}")
            for lab in ("opening", "before", "after", "end_before", "end_after"):
                if r.get(lab): out.append(f"  [{lab}]"); out += [f"    {t:8.1f}  {s}" for t, s in r[lab]]
    open(os.path.join(HERE, "audit", "report.txt"), "w").write("\n".join(out))
    print("\n".join(out[: len(by) + 3]))

if __name__ == "__main__":
    if sys.argv[1] == "audit": audit(int(sys.argv[2]), int(sys.argv[3]))
    else: report()
