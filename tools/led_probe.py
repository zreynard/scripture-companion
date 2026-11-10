"""Is there music under each Be Led prayer? In a speech-only recording the gaps between phrases fall near silence; with
keys or a pad underneath they stay full. Reads only the prayer's stretch at the end of each file (a byte range).
    python tools/led_probe.py   -> prints, per prayer: the quiet frames' level against the speech (dB) and a verdict"""
import json, os, subprocess, sys
import numpy as np, requests
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
for p in json.load(open(os.path.join(HERE, "data", "be_led.json")))["prayers"]:
    it = D["items"].get(p["src"])
    if not it: print("missing", p["src"]); continue
    url = it["audio"]
    n = int(requests.head(url, headers=H, allow_redirects=True, timeout=60).headers.get("content-length") or 0)
    dur = float(it.get("dur") or 0) or 3000
    a = max(0, int(n * (1 - (p["sb"] + 20) / dur)))
    r = requests.get(url, headers={**H, "Range": f"bytes={a}-"}, allow_redirects=True, timeout=120)
    pcm = np.frombuffer(subprocess.run(["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], input=r.content, capture_output=True).stdout, dtype=np.int16).astype(np.float32)
    L = len(pcm) / 16000; seg = pcm[int(max(0, L - p["sb"]) * 16000): int((L - p["e"]) * 16000)]
    fr = seg[: len(seg) // 800 * 800].reshape(-1, 800); rms = np.sqrt((fr ** 2).mean(1)) + 1e-3
    p10, p50 = np.percentile(rms, 10), np.percentile(rms, 50)
    gap = 20 * np.log10(p10 / p50)
    print(json.dumps({"src": p["src"], "title": p["title"], "secs": round(len(seg) / 16000), "quiet_vs_speech_db": round(float(gap), 1), "music_under": bool(gap > -14)}), flush=True)
