"""David Platt's missing years (Brook Hills 2006-2012), A Chronicle of Redemption and McLean's lost series: every public place left.
1. Internet Archive: the Brook Hills audio captures themselves (CDX), and whether a capture plays back.
2. Those file names on the church's current storage (DigitalOcean), under the old paths too.
3. archive.org uploads of Platt audio (the public advanced-search API, no key).
4. Podcast directories (Apple) for feeds of the Brook Hills years, the Chronicle, The Story of Scripture.
Honest user agent; refusals are reported and left alone. Results in probe3/."""
import json, os, re, time, requests, collections
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, t=120, **kw):
    for k in range(3):
        try:
            r = requests.get(u, headers={**H, **kw.pop("headers", {})}, timeout=t, **kw); return r
        except requests.RequestException as e: print("  !", u[:90], type(e).__name__); time.sleep(6)
print("==== 1. Internet Archive captures of Brook Hills audio")
caps = {}
for q in ("brookhills.org/audio/", "brookhills.org/media/files_audio/", "www.brookhills.org/audio/", "www.brookhills.org/media/files_audio/", "brookhills.org/media/audio/"):
    r = get("https://web.archive.org/cdx/search/cdx", 300, params={"url": q, "matchType": "prefix", "output": "json", "fl": "original,timestamp,mimetype,statuscode,length", "collapse": "urlkey", "limit": 50000})
    rows = r.json()[1:] if r is not None and r.ok and r.text.strip().startswith("[") else []
    mp = [x for x in rows if x[0].lower().split("?")[0].endswith(".mp3")]
    ok = [x for x in mp if x[3] == "200" and int(x[4] or 0) > 500000]
    print(f"  {q}: {len(rows)} captures, {len(mp)} mp3, {len(ok)} real audio captures")
    for x in ok: caps.setdefault(x[0].split("/")[-1].split("?")[0], x)
print("  distinct audio files captured:", len(caps), "e.g.", list(caps)[:8])
json.dump(caps, open("probe3/bh_caps.json", "w"))
if caps:
    name, x = next(iter(caps.items()))
    for mode in ("id_", ""):
        r = get(f"https://web.archive.org/web/{x[1]}{mode}/{x[0]}", 120, headers={"Range": "bytes=0-1023"}, allow_redirects=True)
        if r is not None: print(f"  replay {mode or 'plain'}: {r.status_code} {r.headers.get('content-type')} {r.headers.get('content-range')} {len(r.content)} b")
print("==== 2. On the church's current storage")
names = sorted(caps)
hit = collections.Counter()
for n in names[:60]:
    for base in ("https://brookhills-a.atl1.cdn.digitaloceanspaces.com/", "https://brookhills-a.atl1.cdn.digitaloceanspaces.com/audio/", "https://brookhills-a.atl1.cdn.digitaloceanspaces.com/media/files_audio/"):
        r = get(base + n, 30, headers={"Range": "bytes=0-1"})
        if r is not None and r.status_code in (200, 206): hit[base] += 1; break
print("  of the first 60 captured names, found:", dict(hit))
print("==== 3. archive.org uploads")
for q in ('"David Platt" AND mediatype:audio', '"Brook Hills" AND mediatype:audio', '"Chronicle of Redemption"', 'creator:"David Platt"', '"Platt" AND "Brook Hills"'):
    r = get("https://archive.org/advancedsearch.php", 120, params={"q": q, "fl[]": ["identifier", "title", "item_size", "date", "creator"], "rows": 200, "output": "json"})
    docs = r.json().get("response", {}).get("docs", []) if r is not None and r.ok else []
    print(f"  {q}: {len(docs)} items")
    for d in docs[:12]: print("     ", d.get("identifier"), "|", str(d.get("title"))[:70], "|", d.get("date"), "|", round((d.get("item_size") or 0) / 1e6), "MB")
print("==== 4. Podcast directories")
for q in ("david+platt", "brook+hills", "chronicle+of+redemption", "story+of+scripture+mclean", "platt+sermons", "church+at+brook+hills"):
    r = get(f"https://itunes.apple.com/search?term={q}&entity=podcast&limit=50", 60)
    if r is None or not r.ok: continue
    for x in r.json().get("results", []):
        if re.search(r"platt|brook ?hills|mclean|radical|chronicle", (x.get("collectionName", "") + x.get("artistName", "")), re.I):
            print(f"   - {x.get('collectionName')} | {x.get('artistName')} | eps={x.get('trackCount')} | {x.get('feedUrl')}")
