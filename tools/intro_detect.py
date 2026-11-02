"""Find where each episode's shared intro ends, so the app can start playback right after it.

Runs on GitHub Actions (needs ffmpeg and fpcalc from libchromaprint-tools). For one source, it takes the first
few minutes of every episode, turns them into audio fingerprints, and compares each episode with its neighbours
(by date). The stretch of sound two episodes have in common near the start is the intro; its end, in each
episode's own timeline, is that episode's skip point. Writes intro_<source>.json: {item id: seconds}.

    SOURCE=davey_journey python tools/intro_detect.py
"""
import json, os, statistics, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.environ.get("SOURCE", "davey_journey")
HEAD = int(os.environ.get("HEAD", "180"))        # seconds of each episode to look at
LIMIT = int(os.environ.get("N", "0"))            # 0 = every episode
MAX_SKIP = 150                                   # never skip more than this
MIN_SHARED = 6                                   # a shared stretch shorter than this (seconds) is not an intro


def fingerprint(url):
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-user_agent", "Mozilla/5.0", "-t", str(HEAD),
                        "-i", url, "-ac", "1", "-ar", "11025", wav], check=True, timeout=300)
        out = subprocess.run(["fpcalc", "-raw", "-length", str(HEAD), wav], capture_output=True, text=True, timeout=120).stdout
    dur = fp = None
    for line in out.splitlines():
        if line.startswith("DURATION="): dur = float(line.split("=")[1])
        if line.startswith("FINGERPRINT="): fp = np.array([int(x) for x in line.split("=")[1].split(",") if x], dtype=np.uint32)
    if fp is None or not len(fp) or not dur: return None
    return fp, min(dur, HEAD) / len(fp)


def bits(a):
    return np.unpackbits(a.view(np.uint8)).reshape(-1, 32).sum(1)


def shared(a, b, step, max_shift=480):
    """Longest run of matching fingerprint points between a and b over shifts up to about 60 s.
    Returns (start_a, start_b, length) in points, or None."""
    best = None
    k5 = np.ones(5)
    for s in range(-min(max_shift, len(b) - 1), min(max_shift, len(a) - 1) + 1):
        ia, ib = (s, 0) if s >= 0 else (0, -s)
        n = min(len(a) - ia, len(b) - ib)
        if n < 20: continue
        ok = (bits(a[ia:ia + n] ^ b[ib:ib + n]) <= 10).astype(float)
        okb = np.convolve(ok, k5, "same") >= 1          # bridge gaps of up to 4 points
        d = np.diff(np.concatenate(([0], okb.astype(int), [0])))
        starts, stops = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        if not len(starts): continue
        L = stops - starts; m = int(L.argmax())
        st, ln = int(starts[m]) + 2, int(L[m]) - 4      # undo the 2-point widening on each side
        if ln > 0 and (best is None or ln > best[2]):
            best = (ia + st, ib + st, ln)
    return best


def main():
    cat = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    eps = [e for e in cat if e.get("source") == SOURCE and (e.get("audio_override") or e.get("url"))]
    eps.sort(key=lambda e: e.get("published") or "")
    if LIMIT: eps = eps[:LIMIT]
    print(f"{SOURCE}: {len(eps)} episodes", flush=True)

    def fp_of(e):
        try: return e["id"], fingerprint(e.get("audio_override") or e["url"])
        except Exception as ex:
            print("  fail", e["title"][:50], type(ex).__name__, flush=True); return e["id"], None
    with ThreadPoolExecutor(8) as ex:
        F = dict(ex.map(fp_of, eps))

    ends = {e["id"]: [] for e in eps}
    ids = [e["id"] for e in eps if F.get(e["id"])]
    for k, i in enumerate(ids):
        for j in ids[k + 1:k + 4]:  # compare with the next three episodes
            (a, sa), (b, sb) = F[i], F[j]
            r = shared(a, b, sa)
            if not r: continue
            ia, ib, n = r
            secs = n * sa
            if secs < MIN_SHARED or secs > MAX_SKIP: continue           # too short to be an intro, or the same episode twice
            if ia * sa > 60 or ib * sb > 60: continue                   # an intro starts near the beginning
            ends[i].append((ia + n) * sa); ends[j].append((ib + n) * sb)

    out = {}
    for e in eps:
        v = ends.get(e["id"]) or []
        if v:
            out[e["id"]] = round(min(MAX_SKIP, statistics.median(v)), 1)
    found = list(out.values())
    print(f"\nintro found in {len(out)} of {len(eps)} episodes"
          + (f"; skip median {statistics.median(found):.1f}s, range {min(found):.1f}-{max(found):.1f}s" if found else ""))
    for e in eps[:15]:
        print(f"  {out.get(e['id'], '-'):>6}  {e['published'][:10]}  {e['title'][:60]}")
    json.dump(out, open(f"intro_{SOURCE}.json", "w"), indent=0)


if __name__ == "__main__":
    main()
