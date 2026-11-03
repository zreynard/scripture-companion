"""Which Stephen Davey sermon files on Wisdom International's media server do public web archives know about? The Internet
Archive's public index (CDX) of the links it has seen. Honest user agent. Writes probe3/do_cdx.json."""
import json, os, re, requests, collections
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
found = {}
for host in ("wisdomonline-a.atl1.cdn.digitaloceanspaces.com", "wisdomonline-a.atl1.digitaloceanspaces.com",
             "wisdomonline-b.atl1.cdn.digitaloceanspaces.com", "wisdomonline.atl1.cdn.digitaloceanspaces.com"):
    u = f"https://web.archive.org/cdx/search/cdx?url={host}/*&output=json&fl=original,timestamp,statuscode,mimetype&collapse=urlkey&limit=100000"
    try:
        r = requests.get(u, headers=H, timeout=300); rows = r.json()[1:] if r.ok and r.text.strip().startswith("[") else []
    except Exception as e:
        print("!", host, e); continue
    print(f"  {r.status_code} {host}: {len(rows)} archived urls")
    for o, ts, sc, mt in rows: found.setdefault(re.sub(r"^https?://[^/]+/", "", o).split("?")[0], (o, ts, sc, mt))
mp3 = {k: v for k, v in found.items() if k.lower().endswith(".mp3")}
print("distinct files:", len(found), "mp3:", len(mp3))
stems = collections.Counter(re.sub(r"\d.*$", "", k.split("-")[0]) for k in mp3)
print("by series:", dict(stems.most_common(60)))
print("samples:", sorted(mp3)[:20], sorted(mp3)[-10:])
json.dump(sorted(mp3), open("probe3/do_cdx.json", "w"))
# the site's own sermon pages, as the archive saw them (just the list of addresses)
u = "https://web.archive.org/cdx/search/cdx?url=wisdomonline.org/teachings-detail/*&output=json&fl=original&collapse=urlkey&limit=50000"
try:
    r = requests.get(u, headers=H, timeout=300); rows = r.json()[1:] if r.ok and r.text.strip().startswith("[") else []
    print("archived sermon pages:", len(rows))
except Exception as e: print("!", e)
