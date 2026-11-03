"""Ninth look (GitHub's servers): Radical's Vimeo account and the MP3 links in its video descriptions, for
A Chronicle of Redemption; and Internet Archive copies of the church's own Chronicle files. Plain requests."""
import json, os, re, time, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, **kw):
    for k in range(3):
        try:
            r = requests.get(u, headers=H, timeout=60, **kw); time.sleep(1.2); return r
        except requests.RequestException as e: print("  !", u[:90], type(e).__name__); time.sleep(8)
out = {}
r = get("https://vimeo.com/api/oembed.json", params={"url": "https://vimeo.com/830346750/b5f0c1c9f1"})
print("oembed", r and r.status_code, r is not None and r.text[:400])
author = r.json().get("author_url") if r is not None and r.ok else None
users = [u for u in [author and author.rstrip("/").rsplit("/", 1)[-1], "radical", "radicalnet", "davidplatt", "brookhills", "thechurchatbrookhills"] if u]
vids = []
for u in dict.fromkeys(users):
    for page in (1, 2, 3):
        q = get(f"https://vimeo.com/api/v2/{u}/videos.json", params={"page": page})
        print("simple api", u, page, q and q.status_code, q is not None and q.text[:150])
        if q is None or not q.ok: break
        try: got = q.json()
        except Exception: break
        if not got: break
        vids += got
print("videos listed", len(vids))
chron = [v for v in vids if re.search(r"chronicle|redemption", (v.get("title") or "") + " " + (v.get("description") or ""), re.I)]
for v in chron: print("  ", v.get("id"), v.get("title"), v.get("duration"), re.findall(r'https?://[^\s"<>]+\.mp3', v.get("description") or "")[:2])
out["vimeo"] = vids
for q in ("brookhills.org/audio/", "brookhills.org/media/files_audio/"):
    r = get("https://web.archive.org/cdx/search/cdx", params={"url": q, "matchType": "prefix", "output": "json", "collapse": "urlkey", "fl": "original,timestamp,mimetype,statuscode,length", "limit": 5000})
    rows = r.json()[1:] if r is not None and r.ok and r.text.strip() else []
    c = [x for x in rows if re.search(r"chron", x[0], re.I)]
    print(q, len(rows), "chronicle", len(c))
    for x in c[:60]: print("   ", x)
    out.setdefault("wb", []).extend(c)
json.dump(out, open("probe3/vimeo.json", "w"))
