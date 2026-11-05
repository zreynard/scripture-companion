"""Matt Chandler's whole sermon archive on thevillagechurch.net, and what plays before he starts preaching.

    python tools/chandler_probe2.py  -> chandler2/ (sermons.json, heard.json, log.txt), saved to the diag-chandler branch
Lists every sermon the site files under Matt Chandler, year by year (2006 on); reads each sermon page (title, date,
speaker, passage, series, mp3); then hears the first 5 minutes of 30 recordings spread over the years."""
import json, os, re, subprocess, time, html
import requests

UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
B = "https://www.thevillagechurch.net"
OUT = "chandler2"; os.makedirs(OUT, exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = UA
log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
def get(u):
    for k in range(3):
        try:
            r = S.get(u, timeout=40); time.sleep(0.7); return r
        except Exception as ex: note("  retry", u, ex); time.sleep(5)

urls = {}
for y in range(2026, 2005, -1):
    p = 1
    while p < 40:
        r = get(f"{B}/resources/sermons?author=matt-chandler&year={y}&page={p}")
        if not r or r.status_code != 200: note("list fail", y, p, r and r.status_code); break
        found = [u for u in re.findall(r'href="(https://www\.thevillagechurch\.net/resources/sermons/[^"?#]+)"', r.text)]
        new = [u for u in dict.fromkeys(found) if u not in urls]
        for u in new: urls[u] = y
        nxt = f"page={p + 1}" in r.text
        if not new or not nxt: break
        p += 1
    note(f"{y}: {sum(1 for v in urls.values() if v == y)} sermon pages")
note("total pages", len(urls))

def field(t, pat):
    m = re.search(pat, t, re.S); return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
ser = []
for i, (u, y) in enumerate(urls.items()):
    r = get(u)
    if not r or r.status_code != 200: ser.append({"url": u, "status": r and r.status_code}); continue
    t = r.text
    row = {"url": u, "year": y,
           "t": field(t, r"<h1[^>]*>(.*?)</h1>"),
           "by": field(t, r'<p class="h4 font-weight-semibold">(.*?)</p>'),
           "pass": [html.unescape(x) for x in re.findall(r'btn-tag btn-sm text-primary">([^<]+)<', t)],
           "series": field(t, r'href="/resources/series/[^"]*"[^>]*>(.*?)</a>') or field(t, r'(?i)series</span>\s*(.*?)</p>'),
           "mp3": list(dict.fromkeys(re.findall(r"""https?://[^"'\s<>]+?\.mp3""", t)))[:2]}
    ser.append(row)
    if i % 50 == 0: note(f"  [{i}/{len(urls)}] {row['by']} | {row['t']} | {row['pass']} | {row['mp3'][:1]}")
json.dump(ser, open(f"{OUT}/sermons.json", "w"), indent=1, ensure_ascii=False)
withmp3 = [s for s in ser if s.get("mp3")]
note(f"sermon pages {len(ser)}, with an mp3 {len(withmp3)}, with a passage {sum(1 for s in ser if s.get('pass'))}")

from faster_whisper import WhisperModel
import numpy as np, wave
model = WhisperModel("base.en", device="cpu", compute_type="int8")
withmp3.sort(key=lambda s: s["url"])
byyear = {}
for s in withmp3: byyear.setdefault(s["year"], []).append(s)
pick = []
while len(pick) < 30 and any(byyear.values()):
    for y in sorted(byyear):
        if byyear[y] and len(pick) < 30: pick.append(byyear[y].pop(len(byyear[y]) // 2))
heard = {}
for s in pick:
    u = s["mp3"][0]; wav = "/tmp/h.wav"
    if os.path.exists(wav): os.remove(wav)
    d = subprocess.run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_entries", "format=duration", "-of", "csv=p=0", u], capture_output=True, text=True, timeout=300).stdout.strip()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-user_agent", UA, "-t", "300", "-i", u, "-ac", "1", "-ar", "16000", wav], timeout=900)
    if not os.path.exists(wav): note("  no audio", u); continue
    with wave.open(wav) as w: pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = model.transcribe(pcm, beam_size=1, language="en", vad_filter=True, condition_on_previous_text=False)
    lines = [f"{x.start:6.1f}  {x.text.strip()}" for x in segs]
    heard[u] = {"year": s["year"], "t": s["t"], "by": s["by"], "pass": s["pass"], "dur": d, "lines": lines}
    note(f"  HEARD {s['year']} {s['t'][:40]} ({d}s): " + " / ".join(l for l in lines[:5])[:400])
json.dump(heard, open(f"{OUT}/heard.json", "w"), indent=1, ensure_ascii=False)
open(f"{OUT}/log.txt", "w").write("\n".join(log))
