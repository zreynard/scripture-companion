"""What is in archive.org's 'the-church-at-brook-hills-birmingham-194426' item (38 GB), and which other McLean Bible Church
feeds the church's podcast platform publishes. Public APIs, honest user agent. Saves the file list to probe3/."""
import json, os, re, requests, collections
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
for ident in ("the-church-at-brook-hills-birmingham-194426",):
    r = requests.get(f"https://archive.org/metadata/{ident}", headers=H, timeout=120); m = r.json()
    md = m.get("metadata", {}); files = m.get("files", [])
    print("==", ident, r.status_code, "| title:", md.get("title"), "| creator:", md.get("creator"), "| date:", md.get("date"), "| collection:", md.get("collection"))
    print("   description:", re.sub(r"<[^>]+>|\s+", " ", str(md.get("description", "")))[:500])
    audio = [f for f in files if f.get("name", "").lower().endswith((".mp3", ".m4a", ".wav"))]
    print("   files:", len(files), "audio:", len(audio), "formats:", collections.Counter(f.get("format") for f in files).most_common(8))
    yrs = collections.Counter(re.findall(r"(?:19|20)\d{2}", f["name"])[0] if re.findall(r"(?:19|20)\d{2}", f["name"]) else "?" for f in audio)
    print("   audio by year in name:", sorted(yrs.items())[:30])
    for f in audio[:25]: print("     ", f["name"], "|", f.get("title"), "|", f.get("length"), "|", f.get("creator"))
    json.dump(files, open("probe3/ia_brookhills_files.json", "w"))
    if audio:
        u = f"https://archive.org/download/{ident}/{audio[0]['name']}"
        a = requests.get(u, headers={**H, "Range": "bytes=0-1023"}, timeout=60, allow_redirects=True); print("   playback:", a.status_code, a.headers.get("content-type"), a.headers.get("content-range"), a.headers.get("access-control-allow-origin"))
print("== McLean Bible Church podcast platform")
for k in range(1, 13):
    u = f"https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id={k}"
    try: r = requests.get(u, headers=H, timeout=60)
    except Exception as e: print(" ", k, e); continue
    items = r.text.split("<item")[1:] if r.ok else []
    t = re.findall(r"<title>(?:<!\[CDATA\[)?([^<\]]+)", r.text)[:1]
    platt = sum(1 for it in items if re.search(r"platt", it, re.I))
    dates = re.findall(r"<pubDate>([^<]+)", r.text)
    print(f"  series_type_id={k}: {r.status_code} {t} items={len(items)} platt={platt} dates={dates[-1:] } .. {dates[:1]}")
