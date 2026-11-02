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
MAX_SKIP = 200                                   # never skip more than this
MIN_SHARED = 6                                   # a shared stretch shorter than this (seconds) is not an intro


def fingerprint(url):
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-user_agent", "Mozilla/5.0", "-t", str(HEAD),
                        "-i", url, "-ac", "1", "-ar", "11025", wav], check=True, timeout=300)
        out = subprocess.run(["fpcalc", "-raw", "-length", str(HEAD), wav], capture_output=True, text=True, timeout=120).stdout
        feats = voice_feats(wav)
    dur = fp = None
    for line in out.splitlines():
        if line.startswith("DURATION="): dur = float(line.split("=")[1])
        if line.startswith("FINGERPRINT="): fp = np.array([int(x) for x in line.split("=")[1].split(",") if x], dtype=np.uint32)
    if fp is None or not len(fp) or not dur: return None
    return fp, min(dur, HEAD) / len(fp), feats


VSTEP = 0.5  # seconds between voice-feature windows

def voice_feats(wav):
    """Tone colour of the sound, every half second: log energy in 24 bands (100-4500 Hz) over a 1 s window, with
    overall loudness removed, so two speakers can be told apart however loud they are."""
    import wave
    with wave.open(wav) as w:
        sr = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n, hop = 1024, 512
    if len(x) < n * 4: return np.zeros((0, 24))
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    edges = np.geomspace(100, 4500, 25) * n / sr
    bands = np.stack([spec[:, int(edges[k]):max(int(edges[k]) + 1, int(edges[k + 1]))].sum(1) for k in range(24)], 1)
    logb = np.log(bands + 1e-6)
    per = sr / hop                          # frames per second
    out = []
    t = 0.0
    while (t + 1.0) * per <= len(logb):
        seg = logb[int(t * per):int((t + 1.0) * per)]
        v = seg.mean(0); out.append(v - v.mean())
        t += VSTEP
    return np.array(out)


def davey_starts(feats, after, ann=(41, 52), ref=(175, 235), hold=12.0, share=0.8):
    """First moment after `after` seconds where the main speaker (as heard deep in the episode, ref) takes over from
    the announcer (as heard in the fixed intro, ann) and keeps going for `hold` seconds."""
    if feats is None or len(feats) < ref[1] / VSTEP: return None
    w = lambda a, b: feats[int(a / VSTEP):int(b / VSTEP)]
    A, Dv = w(*ann).mean(0), w(*ref).mean(0)
    lab = np.linalg.norm(feats - Dv, axis=1) < np.linalg.norm(feats - A, axis=1)
    k0, need = int(after / VSTEP), int(hold / VSTEP)
    for k in range(k0, min(len(lab) - need, int(MAX_SKIP / VSTEP))):
        if lab[k] and lab[k:k + need].mean() >= share:
            return round(k * VSTEP, 1)
    return None


def bits(a):
    return np.unpackbits(a.view(np.uint8)).reshape(-1, 32).sum(1)


BITS = int(os.environ.get("BITS", "10"))      # fingerprint points match when at most this many of 32 bits differ
MINRUN = float(os.environ.get("MINRUN", "3"))  # seconds

def runs(a, b, max_shift=960, min_pts=None):
    """Every stretch of matching fingerprint points between a and b, over shifts up to about 2 minutes.
    Returns [(start_a, end_a, start_b, end_b)] in points, longest first, without overlaps in a."""
    found = []
    k5 = np.ones(5)
    min_pts = min_pts or int(MINRUN / 0.1238)
    for s in range(-min(max_shift, len(b) - 1), min(max_shift, len(a) - 1) + 1):
        ia, ib = (s, 0) if s >= 0 else (0, -s)
        n = min(len(a) - ia, len(b) - ib)
        if n < min_pts: continue
        ok = (bits(a[ia:ia + n] ^ b[ib:ib + n]) <= BITS).astype(float)
        okb = np.convolve(ok, k5, "same") >= 1          # bridge gaps of up to 4 points
        d = np.diff(np.concatenate(([0], okb.astype(int), [0])))
        for st, sp in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            st, sp = int(st) + 2, int(sp) - 2
            if sp - st >= min_pts and ok[st:sp].mean() > 0.5:
                found.append((ia + st, ia + sp, ib + st, ib + sp))
    found.sort(key=lambda r: -(r[1] - r[0]))
    keep = []
    for r in found:
        if all(r[1] <= k[0] or r[0] >= k[1] for k in keep): keep.append(r)
    return keep


def main():
    cat = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    eps = [e for e in cat if e.get("source") == SOURCE and (e.get("audio_override") or e.get("url"))]
    from email.utils import parsedate_to_datetime
    def when(e):
        try: return parsedate_to_datetime(e.get("published")).timestamp()
        except Exception:
            return 0
    eps.sort(key=when)
    FOCUS = os.environ.get("FOCUS", "")
    if FOCUS:  # look at the episodes around one title (for checking against a known intro end)
        k = next((n for n, e in enumerate(eps) if FOCUS.lower() in e["title"].lower()), 0)
        eps = eps[max(0, k - 6):k + 7]
    if LIMIT: eps = eps[:LIMIT]
    print(f"{SOURCE}: {len(eps)} episodes", flush=True)

    def fp_of(e):
        try: return e["id"], fingerprint(e.get("audio_override") or e["url"])
        except Exception as ex:
            print("  fail", e["title"][:50], type(ex).__name__, flush=True); return e["id"], None
    with ThreadPoolExecutor(8) as ex:
        F = dict(ex.map(fp_of, eps))

    ids = [e["id"] for e in eps if F.get(e["id"])]
    title = {e["id"]: e["title"] for e in eps}
    OPEN = float(os.environ.get("OPEN", "150"))       # the intro's last shared stretch must start within this many seconds
    def analyse():
        # every shared stretch each episode has with each of its neighbours (three before, three after), in its own timeline
        seen = {i: [] for i in ids}
        for k, i in enumerate(ids):
            for j in ids[k + 1:k + 4]:
                (a, sa, _), (b, sb, _) = F[i], F[j]
                for r in runs(a, b):
                    if (r[1] - r[0]) * sa > MAX_SKIP: continue                 # the same episode twice
                    seen[i].append((r[0] * sa, r[1] * sa, j)); seen[j].append((r[2] * sb, r[3] * sb, i))
        ends = {}
        for i in ids:
            nbrs = {x[2] for x in seen[i]}
            need = max(2, (len(nbrs) + 1) // 2)                               # found with at least half of the neighbours
            segs = sorted(seen[i])
            steady = []
            for st, en, j in segs:
                if st > OPEN: continue
                same = {x[2] for x in segs if abs(x[0] - st) <= 2.5 and abs(x[1] - en) <= 3}
                if len(same) >= need: steady.append((st, en))
            if steady:
                ends[i] = [max(en for st, en in steady)]
            if FOCUS and FOCUS.lower() in title[i].lower():
                print(f"  {title[i][:40]}: steady {sorted(set((round(a), round(b)) for a, b in steady))}  of {len(nbrs)} neighbours", flush=True)

        return ends
    global BITS, MINRUN
    sweep = [(int(x.split("/")[0]), float(x.split("/")[1])) for x in os.environ.get("SWEEP", "").split(",") if "/" in x]
    for BITS, MINRUN in sweep:
        print(f"-- BITS {BITS}, MINRUN {MINRUN}s", flush=True); analyse()
    BITS, MINRUN = int(os.environ.get("BITS", "10")), float(os.environ.get("MINRUN", "3"))
    ends = analyse()
    # the shared pieces end the intro when the last one comes late (a sting right before the sermon); when the last
    # shared piece is early (the fixed announcer bit), the announcer goes on speaking: find where the main voice takes over
    VOICE = os.environ.get("VOICE", "0") == "1"
    out, check = {}, []
    for e in eps:
        i = e["id"]; v = ends.get(i) or []
        shared_end = max(v) if v else None
        feats = F[i][2] if F.get(i) else None
        if VOICE and shared_end is not None and shared_end > 70:
            vs = davey_starts(feats, after=55)
            if vs is not None: check.append((shared_end, vs))
        if shared_end is None: continue
        if VOICE and shared_end <= 70:
            vs = davey_starts(feats, after=shared_end)
            out[i] = round(min(MAX_SKIP, vs if vs is not None else shared_end), 1)
        else:
            out[i] = round(min(MAX_SKIP, shared_end), 1)
    if check:
        diffs = [abs(a - b) for a, b in check]
        print(f"\nvoice check against the sting, {len(check)} episodes: median off by {statistics.median(diffs):.1f}s; "
              f"within 5 s {sum(d <= 5 for d in diffs)}, within 10 s {sum(d <= 10 for d in diffs)}")
        for a, b in check[:12]: print(f"    sting {a:6.1f}   voice {b:6.1f}")
    found = list(out.values())
    print(f"\nintro found in {len(out)} of {len(eps)} episodes"
          + (f"; skip median {statistics.median(found):.1f}s, range {min(found):.1f}-{max(found):.1f}s" if found else ""))
    for e in eps[:15]:
        print(f"  {out.get(e['id'], '-'):>6}  {e['published'][:10]}  {e['title'][:60]}")
    json.dump(out, open(f"intro_{SOURCE}.json", "w"), indent=0)


if __name__ == "__main__":
    main()
