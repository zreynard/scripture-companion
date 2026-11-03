"""Eighth look (GitHub's servers): A Chronicle of Redemption's original audio.
1. Radical's Vimeo uploads of the series: MP3 links Radical put in the descriptions, and whether each plays.
2. The church's original files (CHRONICLE-PARTn-m_AUD.mp3): does the Internet Archive hold the audio itself?
Plain requests under the app's own name; a refusal is reported and left alone."""
import json, os, re, time, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, **kw):
    for k in range(3):
        try:
            r = requests.get(u, headers=H, timeout=60, **kw); time.sleep(1.5); return r
        except requests.RequestException as e: print("  !", u[:90], type(e).__name__); time.sleep(8)
out = {"vimeo": [], "wayback": []}
ids = {}
for q in ('site:vimeo.com "chronicle of redemption"', 'vimeo "A Chronicle of Redemption" Platt chapter', 'vimeo radical "chronicle of redemption" mp3'):
    r = get("https://html.duckduckgo.com/html/", params={"q": q})
    if r is None: continue
    print("search", r.status_code, len(r.text), q)
    for m in re.finditer(r'vimeo\.com(?:%2F|/)(\d{6,12})', r.text): ids[m.group(1)] = 1
print("vimeo ids", list(ids)[:60])
for vid in list(ids)[:80]:
    r = get(f"https://vimeo.com/{vid}")
    if r is None: continue
    t = r.text.replace("\\/", "/")
    title = (re.search(r'<title>([^<]+)</title>', t) or [None, ""])[1]
    mp3 = list(dict.fromkeys(re.findall(r'https?://[^\s"\'<>()\\]+?\.mp3', t)))
    row = {"id": vid, "status": r.status_code, "title": title[:120], "mp3": mp3[:4]}
    for u in mp3[:2]:
        try:
            h = requests.head(u, headers=H, timeout=40, allow_redirects=True)
            row.setdefault("live", []).append([u, h.status_code, h.headers.get("content-type"), h.headers.get("content-length"), h.headers.get("access-control-allow-origin")])
        except requests.RequestException as e: row.setdefault("live", []).append([u, type(e).__name__])
    out["vimeo"].append(row); print(json.dumps(row)[:600], flush=True)
for q in ("brookhills.org/audio/", "brookhills.org/media/files_audio/"):
    r = get("https://web.archive.org/cdx/search/cdx", params={"url": q, "matchType": "prefix", "output": "json", "fl": "original,timestamp,mimetype,statuscode,length", "limit": 20000})
    rows = r.json()[1:] if r is not None and r.ok and r.text.strip() else []
    for o, ts, mt, sc, ln in rows:
        if re.search(r"chron", o, re.I): out["wayback"].append([o, ts, mt, sc, ln])
print("wayback chronicle captures", len(out["wayback"]))
for x in out["wayback"][:80]: print("  ", x)
json.dump(out, open("probe3/chronicle_audio.json", "w"), indent=1)
