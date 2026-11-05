"""Where Matt Chandler's sermons live online, and what plays before the preaching starts.

    python tools/chandler_probe.py   -> chandler/ (feeds.json, site/, intros/), saved to the diag-chandler branch

  1. podcast directory: every feed for Matt Chandler / The Village Church, with episode counts, date range, lengths and
     who preaches (the feed's own author / title fields)
  2. the church's site (tvc.org, thevillagechurch.net): robots.txt honoured, sermon pages crawled a little, every audio
     link found
  3. intros: the first 4 minutes of a spread of episodes heard with speech recognition, plus where the sermon starts
Runs on GitHub's servers."""
import json, os, re, subprocess, sys, time, urllib.parse, urllib.robotparser
import xml.etree.ElementTree as ET
import requests

UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
OUT = "chandler"; os.makedirs(f"{OUT}/site", exist_ok=True); os.makedirs(f"{OUT}/intros", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = UA
log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)

def get(url, **kw):
    try:
        r = S.get(url, timeout=40, **kw); return r
    except Exception as ex:
        note("  fail", url, ex); return None

# ---- 1. feeds
feeds = {}
for q in ("matt chandler", "matt chandler sermons", "the village church sermons", "village church flower mound", "the village church"):
    r = get("https://itunes.apple.com/search", params={"term": q, "media": "podcast", "limit": 25})
    if not r or r.status_code != 200: note("itunes search", q, r and r.status_code); continue
    for x in r.json().get("results", []):
        if x.get("feedUrl"): feeds.setdefault(x["feedUrl"], {"name": x.get("collectionName"), "artist": x.get("artistName"), "n_listed": x.get("trackCount"), "apple": x.get("collectionId")})
r = get("https://itunes.apple.com/lookup", params={"id": 82014403})
if r and r.status_code == 200:
    for x in r.json().get("results", []):
        if x.get("feedUrl"): feeds.setdefault(x["feedUrl"], {"name": x.get("collectionName"), "artist": x.get("artistName"), "n_listed": x.get("trackCount"), "apple": x.get("collectionId")})
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
def dur(s):
    if not s: return None
    p = [int(float(x)) for x in s.split(":") if x.strip().replace(".", "").isdigit()]
    v = 0
    for x in p: v = v * 60 + x
    return v
rel = re.compile(r"chandler|village church", re.I)
for url, f in list(feeds.items()):
    if not rel.search(f"{f['name']} {f['artist']}"): del feeds[url]; continue
    r = get(url)
    f["status"] = r.status_code if r else None
    if not r or r.status_code != 200: continue
    try: root = ET.fromstring(r.content)
    except Exception as ex: f["parse"] = str(ex); continue
    eps = []
    for it in root.iter("item"):
        enc = it.find("enclosure")
        eps.append({"t": (it.findtext("title") or "").strip(), "date": it.findtext("pubDate"),
                    "author": it.findtext("itunes:author", namespaces=NS) or it.findtext("author"),
                    "dur": dur(it.findtext("itunes:duration", namespaces=NS)),
                    "audio": enc.get("url") if enc is not None else None,
                    "desc": re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:300]})
    f["n"] = len(eps); f["eps"] = eps
    f["hosts"] = sorted({urllib.parse.urlparse(e["audio"]).netloc for e in eps if e["audio"]})
    ds = [e["dur"] for e in eps if e["dur"]]
    f["median_min"] = round(sorted(ds)[len(ds) // 2] / 60) if ds else None
    note(f"FEED {f['name']} | {f['artist']} | {len(eps)} episodes | {eps[-1]['date'] if eps else ''} .. {eps[0]['date'] if eps else ''} | median {f['median_min']} min | {f['hosts']} | {url}")
json.dump(feeds, open(f"{OUT}/feeds.json", "w"), indent=1, ensure_ascii=False)

# ---- 2. the church's site
audio_links = {}
for site in ("https://www.tvc.org", "https://www.thevillagechurch.net"):
    rp = urllib.robotparser.RobotFileParser(); rr = get(site + "/robots.txt")
    rp.parse((rr.text if rr is not None and rr.status_code == 200 else "").splitlines())
    open(f"{OUT}/site/{urllib.parse.urlparse(site).netloc}_robots.txt", "w").write(rr.text if rr is not None else "")
    todo = [site + p for p in ("/sermons", "/resources/sermons", "/sermons/series", "/resources/sermons/series", "/watch", "/media")]
    seen, n = set(), 0
    while todo and n < 120:
        u = todo.pop(0)
        if u in seen: continue
        seen.add(u)
        if not rp.can_fetch(UA, u): note("  robots disallow", u); continue
        r = get(u); time.sleep(1)
        if r is None: continue
        n += 1
        note(f"  {r.status_code} {u} -> {r.url} ({len(r.text)} chars)")
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""): continue
        fn = re.sub(r"[^a-z0-9]+", "_", r.url.lower())[-120:] + ".html"
        open(f"{OUT}/site/{fn}", "w").write(r.text[:600000])
        for m in re.findall(r"""https?://[^"'\s<>]+?\.(?:mp3|m4a)(?:\?[^"'\s<>]*)?""", r.text): audio_links.setdefault(m, r.url)
        base = urllib.parse.urlparse(r.url).netloc
        for h in re.findall(r'href="([^"#]+)"', r.text):
            a = urllib.parse.urljoin(r.url, h)
            if urllib.parse.urlparse(a).netloc == base and re.search(r"sermon|series|message", a, re.I) and a not in seen: todo.append(a)
json.dump(audio_links, open(f"{OUT}/site/audio_links.json", "w"), indent=1)
note(f"site audio links: {len(audio_links)}")

# ---- 3. intros: the main sermon feed (most episodes, Chandler named), 24 episodes spread over its whole range
cand = [f for f in feeds.values() if f.get("eps")]
cand.sort(key=lambda f: (not re.search(r"sermon", f["name"] or "", re.I), -sum(1 for e in f["eps"] if re.search("chandler", f"{e['author']} {e['t']} {e['desc']}", re.I)), -f["n"]))
heard = {}
if cand:
    from faster_whisper import WhisperModel
    import numpy as np, wave
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    for f in cand[:2]:
        eps = [e for e in f["eps"] if e["audio"]]
        pick = [eps[int(i * (len(eps) - 1) / 23)] for i in range(24)] if len(eps) > 24 else eps
        for e in pick:
            wav = "/tmp/h.wav"
            if os.path.exists(wav): os.remove(wav)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-user_agent", UA, "-t", "240", "-i", e["audio"], "-ac", "1", "-ar", "16000", wav], timeout=600)
            if not os.path.exists(wav): note("  no audio", e["t"]); continue
            with wave.open(wav) as w: pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            segs, _ = model.transcribe(pcm, beam_size=1, language="en", vad_filter=True, condition_on_previous_text=False)
            lines = [f"{s.start:6.1f}  {s.text.strip()}" for s in segs]
            key = f"{f['name']}|{e['t']}|{e['date']}"
            heard[key] = lines
            note(f"  INTRO [{f['name'][:30]}] {e['date'][:16] if e['date'] else ''} {e['t'][:50]}: " + " / ".join(l[8:] for l in lines[:4])[:300])
json.dump(heard, open(f"{OUT}/intros/heard.json", "w"), indent=1, ensure_ascii=False)
open(f"{OUT}/log.txt", "w").write("\n".join(log))
