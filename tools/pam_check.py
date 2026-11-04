"""Check every Philip Anthony Mitchell / 2819 Church recording in the app by listening to it.

For each recording:
  - the file loads, and its real length (ffprobe) against the length the app shows
  - the first 25 minutes, heard with speech recognition: the passage he announces and reads aloud, scored against the
    passage the app places it on (the share of that passage's distinctive words heard), and the words around the
    start point the app skips to
  - an audio fingerprint of 90 seconds from the middle, so two listings of the same sermon are caught even when their
    titles, intros or lengths differ
  - the preachers named in the opening (the host introduces a guest preacher by name)

    python tools/pam_check.py K N     -> pam_check/<K>.json, transcripts in pam_check/text/
    python tools/pam_check.py report  -> data/pam_check.json (findings) and a readable summary
Runs on GitHub's servers (ffmpeg, chromaprint and faster-whisper)."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tools"))
from refs import parse_refs                                    # noqa: E402
from spoken_refs import norm, words, best_reading, candidates  # noqa: E402

UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
OUT = os.path.join(HERE, "pam_check")
MIN = int(os.environ.get("PAM_MINUTES", "25"))


def items():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    place = {}
    for b in D["books"]:
        for c in b["ch"]:
            for i in c["ids"]: place.setdefault(i, []).append(f"{b['name']} {c['c']}")
    out = []
    for i, it in D["items"].items():
        if it.get("who") == "PAM" and it.get("audio"):
            out.append({**it, "placed": place.get(i, [])})
    return sorted(out, key=lambda x: x["id"])


def run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def duration(url):
    r = run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_entries", "format=duration", "-of", "csv=p=0", url], 300)
    try: return float(r.stdout.strip())
    except ValueError: return None


def wav(url, start, length, path):
    if os.path.exists(path): os.remove(path)
    run(["ffmpeg", "-loglevel", "error", "-y", "-user_agent", UA, "-ss", str(start), "-t", str(length), "-i", url,
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", path], 1200)
    return os.path.exists(path) and os.path.getsize(path) > 100000


def fingerprint(path):
    r = run(["fpcalc", "-raw", "-json", "-length", "90", path], 300)
    try: return json.loads(r.stdout)["fingerprint"]
    except Exception: return None


def measure(k, n):
    from faster_whisper import WhisperModel
    import wave, numpy as np
    todo = items()
    if os.environ.get("PAM_SRC"): todo = [i for i in todo if i["src"] == os.environ["PAM_SRC"]]
    todo = todo[k::n]
    os.makedirs(os.path.join(OUT, "text"), exist_ok=True)
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    tmp = tempfile.mkdtemp(); res = {}
    print(f"shard {k}/{n}: {len(todo)} recordings", flush=True)
    for x, it in enumerate(todo, 1):
        r = {"t": it["t"], "dur_app": it.get("dur"), "s": it.get("s"), "e": it.get("e"), "placed": it["placed"], "pass": it.get("pass", "")}
        try:
            d = duration(it["audio"]); r["dur_file"] = d
            if not d: r["error"] = "the file did not load"; res[it["id"]] = r; print(f"  [{x}] {it['t'][:60]}: no file", flush=True); continue
            mid = os.path.join(tmp, "m.wav")
            if wav(it["audio"], round(d * 0.42), 90, mid): r["fp"] = fingerprint(mid)
            head = os.path.join(tmp, "h.wav")
            if wav(it["audio"], 0, MIN * 60, head):
                with wave.open(head) as w: pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                segs, _ = model.transcribe(pcm, beam_size=1, language="en", vad_filter=True, condition_on_previous_text=False)
                lines = [(round(s.start, 1), s.text.strip()) for s in segs]
                open(os.path.join(OUT, "text", it["id"] + ".txt"), "w", encoding="utf-8").write("\n".join(f"{a:7.1f}  {t}" for a, t in lines))
                text = " ".join(t for _, t in lines); r["heard_s"] = len(text)
                heard = words(norm(text))
                # the passage in the title / listing, and how much of it he reads aloud
                tp = parse_refs(it.get("pass") or it["t"])
                r["title_ref"] = []
                for ref in tp:
                    if ref.whole_book or not ref.chapters: continue
                    ch = min(ref.chapters)
                    vm = re.search(r":(\d+)(?:\s*[-–]\s*(\d+))?", ref.raw) if ref.verse_level else None
                    v1, v2 = (int(vm.group(1)), int(vm.group(2)) if vm.group(2) else None) if vm else (None, None)
                    at, sc, nw = best_reading(ref.book, ch, v1, v2, heard)
                    r["title_ref"].append({"ref": f"{ref.book} {ch}" + (f":{v1}" + (f"-{v2}" if v2 else "") if v1 else ""), "read": sc, "words": nw})
                r["announced"] = [{"ref": c["ref"], "read": c["score"]} for c in candidates(text)][:8]
                st = it.get("s") or 0
                r["at_start"] = " ".join(t for a, t in lines if st - 12 <= a <= st + 25)[:400]
                r["opening"] = " ".join(t for a, t in lines if a <= 240)[:1500]
                low = text.lower()
                r["names"] = sorted({nm for nm in ("philip anthony mitchell", "pastor phil", "pastor philip", "arik hayes", "elder arik", "milton james",
                                                   "lonnell williams", "lonell", "brandon freeman", "marquavious walker", "tyonna lewis")
                                     if nm in low})
        except Exception as ex:
            r["error"] = str(ex)[:200]
        res[it["id"]] = r
        tr = r.get("title_ref") or [{}]
        print(f"  [{x}/{len(todo)}] {it['t'][:58]!r}: file {round(r.get('dur_file') or 0)}s vs {it.get('dur')}s, title passage read {tr[0].get('read')}", flush=True)
        json.dump(res, open(os.path.join(OUT, f"{k}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(res, open(os.path.join(OUT, f"{k}.json"), "w", encoding="utf-8"), ensure_ascii=False)


def similar(a, b):
    """Share of matching fingerprint bits at the best alignment (two copies of one recording: ~0.9+; different: ~0.5)."""
    import numpy as np
    A, B = np.array(a, dtype=np.uint32), np.array(b, dtype=np.uint32)
    best = 0.0
    for off in range(-40, 41, 2):
        x, y = (A[off:], B) if off >= 0 else (A, B[-off:])
        m = min(len(x), len(y))
        if m < 100: continue
        diff = np.unpackbits((x[:m] ^ y[:m]).view(np.uint8)).sum()
        best = max(best, 1 - diff / (32 * m))
    return best


def report():
    res = {}
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".json"): res.update(json.load(open(os.path.join(OUT, f), encoding="utf-8")))
    ids = sorted(res)
    dups = []
    fps = {i: res[i]["fp"] for i in ids if res[i].get("fp")}
    ks = sorted(fps)
    for a in range(len(ks)):
        for b in range(a + 1, len(ks)):
            s = similar(fps[ks[a]], fps[ks[b]])
            if s >= 0.75: dups.append((round(s, 3), ks[a], ks[b]))
    flags = []
    for i in ids:
        r = res[i]; why = []
        if r.get("error"): why.append("error: " + r["error"])
        if r.get("dur_file") and r.get("dur_app") and abs(r["dur_file"] - r["dur_app"]) > 90: why.append(f"length {round(r['dur_file'])}s, app says {r['dur_app']}s")
        tr = r.get("title_ref") or []
        if tr and max(t["read"] for t in tr) < 0.45:
            best = max(r.get("announced") or [{"ref": None, "read": 0}], key=lambda c: c["read"])
            why.append(f"title passage {', '.join(t['ref'] for t in tr)} read {max(t['read'] for t in tr)}; best heard {best['ref']} ({best['read']})")
        if not tr and r.get("placed"): why.append("placed without a passage in its title")
        if why: flags.append({"id": i, "t": r["t"], "why": why, "placed": r.get("placed")})
    out = {"n": len(ids), "duplicates": [{"sim": s, "a": a, "b": b, "ta": res[a]["t"], "tb": res[b]["t"]} for s, a, b in sorted(dups, reverse=True)],
           "flags": flags, "all": {i: {k: v for k, v in res[i].items() if k != "fp"} for i in ids}}
    json.dump(out, open(os.path.join(HERE, "data", "pam_check.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(ids)} recordings checked; {len(dups)} possible duplicate pairs; {len(flags)} flagged")
    for d in out["duplicates"]: print(f"  DUP {d['sim']}: {d['ta'][:60]}  ==  {d['tb'][:60]}")
    for f in flags: print(f"  FLAG {f['t'][:70]}: {'; '.join(f['why'])}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["report"]: report()
    else: measure(int(a[0]), int(a[1]))
