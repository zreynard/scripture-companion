"""Listen to every candidate free worship instrumental: length, singing or speech (speech recognition on three 60-second
windows), loudness range (sudden peaks), drum-like hits, and a 45-second preview from the middle.
    python tools/music_check.py -> music3/ (tracks.json, previews/*.mp3, log.txt), saved to diag-music3"""
import json, os, re, subprocess, time
import numpy as np, requests, wave
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
S = requests.Session(); S.headers["User-Agent"] = UA
OUT = "music3"; os.makedirs(f"{OUT}/previews", exist_ok=True); log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
IA = ["30-minutes-deep-prayer-music-prophetic-worship-intercession-warfare-time-with-holy-spirit", "OverflowSoaking",
      "jamendo-240505", "jamendo-165254", "jamendo-177616", "jamendo-629438", "KenCarlsonSpontaneousWorship", "E4g004-Graphite412AGrainOfWheat",
      "E4g001-Graphite412KardiaPsalloI", "E4g015-Graphite412PeacemakeriiishortVersion", "jamendo-192410", "jamendo-152130", "luv001",
      "AliveCommunityChurch091025-PropheticWorship"]
r = S.get("https://archive.org/advancedsearch.php", params={"q": 'creator:("Samuel Liu")', "fl[]": ["identifier"], "rows": 100, "output": "json"}, timeout=60).json()
IA += [d["identifier"] for d in r["response"]["docs"] if "preview" not in d["identifier"].lower()]
tracks = []
for i in IA:
    try: m = S.get(f"https://archive.org/metadata/{i}", timeout=60).json()
    except Exception as ex: note("meta fail", i, ex); continue
    md = m.get("metadata", {}); fs = [f for f in m.get("files", []) if f["name"].lower().endswith(".mp3")]
    orig = [f for f in fs if f.get("source") == "original"] or fs
    for f in orig:
        tracks.append({"src": "archive.org", "item": i, "artist": md.get("creator"), "album": md.get("title"), "t": f.get("title") or f["name"],
                       "license": md.get("licenseurl"), "url": f"https://archive.org/download/{i}/{requests.utils.quote(f['name'])}", "page": f"https://archive.org/details/{i}"})
# Scott Buckley: ambient / piano track pages (CC BY 4.0 per page)
pages = set()
for tag in ("piano-music", "ambient", "ambient-music", "piano"):
    try: t = S.get(f"https://www.scottbuckley.com.au/tag/{tag}/", timeout=40).text; time.sleep(1)
    except Exception: continue
    pages |= set(re.findall(r'href="(https://www\.scottbuckley\.com\.au/library/[a-z0-9\-]+/?)"', t))
for p in ["https://www.scottbuckley.com.au/library/she-moved-mountains/", "https://www.scottbuckley.com.au/library/there-is-a-place/", "https://www.scottbuckley.com.au/library/cobalt/", "https://www.scottbuckley.com.au/library/skyward/"]: pages.add(p)
for p in sorted(pages)[:40]:
    try: t = S.get(p, timeout=40).text; time.sleep(1)
    except Exception: continue
    if "creativecommons.org/licenses/by/4.0" not in t: continue
    mp3 = re.findall(r"""https?://[^"'\s<>]+?\.mp3""", t)
    if mp3: tracks.append({"src": "scottbuckley", "artist": "Scott Buckley", "t": p.rstrip("/").rsplit("/", 1)[-1], "license": "https://creativecommons.org/licenses/by/4.0/", "url": mp3[0], "page": p})
note(f"{len(tracks)} tracks to hear")
from faster_whisper import WhisperModel
model = WhisperModel("base.en", device="cpu", compute_type="int8")
def pcm(path):
    with wave.open(path) as w: return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
for k, tr in enumerate(tracks):
    f = "/tmp/full.mp3"
    try:
        with S.get(tr["url"], timeout=300, stream=True) as r:
            r.raise_for_status(); open(f, "wb").write(r.content)
    except Exception as ex: tr["err"] = str(ex)[:120]; note("  get fail", tr["t"], ex); continue
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f], capture_output=True, text=True).stdout.strip()
    try: d = float(d)
    except ValueError: tr["err"] = "no duration"; continue
    tr["dur"] = round(d)
    words = []
    for frac in (0.15, 0.5, 0.85):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(d * frac), "-t", "60", "-i", f, "-ac", "1", "-ar", "16000", "/tmp/w.wav"])
        segs, _ = model.transcribe(pcm("/tmp/w.wav"), beam_size=1, language="en", vad_filter=True, condition_on_previous_text=False, no_speech_threshold=0.5)
        words += [s.text.strip() for s in segs if s.no_speech_prob < 0.5]
    tr["heard"] = " / ".join(words)[:300]; tr["words"] = sum(len(w.split()) for w in words)
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", e); lra = re.findall(r"LRA:\s+([\d.]+) LU", e)
    tr["lufs"] = float(m[-1]) if m else None; tr["lra"] = float(lra[-1]) if lra else None
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(d * 0.5), "-t", "60", "-i", f, "-ac", "1", "-ar", "22050", "/tmp/o.wav"])
    x = pcm("/tmp/o.wav"); n = 1024; fr = x[: len(x) // n * n].reshape(-1, n)
    sp = np.abs(np.fft.rfft(fr * np.hanning(n), axis=1))[:, 80:]   # above ~1.7 kHz
    flux = np.maximum(np.diff(sp, axis=0), 0).sum(1); thr = np.median(flux) * 4 + 1e-9
    tr["hits_per_min"] = int((flux > thr).sum())
    pv = f"{OUT}/previews/{k:03d}.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(max(0, d * 0.45)), "-t", "45", "-i", f, "-af", "afade=t=in:d=2,afade=t=out:st=43:d=2", "-ac", "2", "-b:a", "96k", pv])
    tr["preview"] = pv[len(OUT) + 1:]
    note(f"  [{k}] {tr['artist']} | {tr['t'][:50]} | {round(d/60)} min | words {tr['words']} | LRA {tr['lra']} | hits {tr['hits_per_min']} | {tr['heard'][:120]}")
    json.dump(tracks, open(f"{OUT}/tracks.json", "w"), indent=1, ensure_ascii=False)
json.dump(tracks, open(f"{OUT}/tracks.json", "w"), indent=1, ensure_ascii=False)
open(f"{OUT}/log.txt", "w").write("\n".join(log))
