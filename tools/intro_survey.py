"""What every source sounds like at its start and end: transcribe the opening 150 s and closing 180 s of a few
episodes per source (spread over the years), with times and the music/silence gaps, so each source's intro and
outro can be cut where the teaching starts and ends.

    SOURCE=platt_messages K=6 python tools/intro_survey.py
Runs on GitHub's servers (ffmpeg + faster-whisper). Plain requests under the app's own name."""
import json, os, re, subprocess, sys, tempfile, wave
import numpy as np, requests
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
from app_build import audio_url  # noqa: E402
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
SRC, K = os.environ.get("SOURCE", "platt_messages"), int(os.environ.get("K", "6"))
from faster_whisper import WhisperModel
M = WhisperModel("base.en", device="cpu", compute_type="int8")

def pcm_of(url, tail=False, nbytes=3_000_000, secs=150):
    with tempfile.TemporaryDirectory() as d:
        a, w = os.path.join(d, "a"), os.path.join(d, "a.wav")
        try:
            r = requests.get(url, headers={**H, **({"Range": f"bytes=-{nbytes}"} if tail else {})}, timeout=120, stream=True)
            if r.status_code not in (200, 206): return None, f"HTTP {r.status_code}"
            buf = bytearray()
            for ch in r.iter_content(262144):
                buf += ch
                if not tail and len(buf) > nbytes: break
                if tail and len(buf) > 3 * nbytes: del buf[:-nbytes]
            r.close(); open(a, "wb").write(bytes(buf[-nbytes:] if tail else buf))
        except requests.RequestException as e: return None, type(e).__name__
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", a, "-ac", "1", "-ar", "16000", w], check=False)
        if not os.path.exists(w): return None, "no decode"
        with wave.open(w) as f: x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return (x[-secs * 16000:] if tail else x[:secs * 16000]), None

def show(x, label, offset_from_end=None):
    segs, _ = M.transcribe(x, beam_size=1, language="en", vad_filter=True, condition_on_previous_text=False)
    segs = list(segs); L = len(x) / 16000; prev = 0.0
    print(f"  -- {label} ({L:.0f} s)")
    for s in segs:
        if s.start - prev > 2.5: print(f"     [no speech {prev:6.1f}-{s.start:6.1f}  {s.start - prev:4.1f}s]")
        t = s.start if offset_from_end is None else s.start - L
        print(f"     {t:7.1f}  {s.text.strip()[:150]}"); prev = s.end
    if L - prev > 2.5: print(f"     [no speech {prev:6.1f}-{L:6.1f}  {L - prev:4.1f}s to the end]")

rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
eps = [e for e in rows if e["source"] == SRC and e["tier"] in ("V1", "V2") and audio_url(e)]
eps.sort(key=lambda e: e.get("published") or "")
pick = eps[:: max(1, len(eps) // K)][:K]
print(f"### {SRC}: {len(eps)} episodes; sampling {len(pick)}")
for e in pick:
    u = audio_url(e); print(f"\n## {e['title'][:90]} | {e.get('published','')[:16]} | {e.get('speaker')} | dur {e.get('duration')} | {u[:100]}", flush=True)
    x, err = pcm_of(u)
    if x is None: print("  head:", err); continue
    show(x, "opening")
    y, err = pcm_of(u, tail=True, secs=180)
    if y is None: print("  tail:", err); continue
    show(y, "closing (times from the end)", offset_from_end=True)
