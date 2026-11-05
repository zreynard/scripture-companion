"""archive.org: more soaking / instrumental worship under Creative Commons or public domain, with each item's files and
lengths.   python tools/music_probe2.py -> music2/ (items.json, log.txt), saved to diag-music"""
import json, os, re, requests
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
S = requests.Session(); S.headers["User-Agent"] = UA
os.makedirs("music2", exist_ok=True); log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
LIC = '(licenseurl:*creativecommons* OR licenseurl:*publicdomain*)'
Q = [f'creator:(DappyTKeys) OR uploader:(dappy*)', 'DappyTKeys', 'creator:(Overflow) AND soaking', 'creator:("Samuel Liu")',
     f'("soaking music" OR "soaking worship" OR "soaking prayer") AND mediatype:audio AND {LIC}',
     f'("prophetic worship" OR "spontaneous worship" OR "worship instrumental" OR "instrumental worship" OR "prayer instrumental") AND mediatype:audio AND {LIC}',
     f'("worship pad" OR "worship pads" OR "ambient worship" OR "piano worship" OR "worship piano") AND mediatype:audio AND {LIC}',
     f'subject:(soaking) AND mediatype:audio']
seen = {}
for q in Q:
    try:
        r = S.get("https://archive.org/advancedsearch.php", params={"q": q, "fl[]": ["identifier", "title", "creator", "licenseurl", "downloads", "date", "subject"], "rows": 200, "output": "json", "sort[]": "downloads desc"}, timeout=60).json()
    except Exception as ex: note("fail", q, ex); continue
    note(f"## {q} -> {r['response']['numFound']}")
    for d in r["response"]["docs"]:
        if d["identifier"] in seen: continue
        seen[d["identifier"]] = d
        note(f"  {d.get('downloads')} | {d.get('title')} | {d.get('creator')} | {d.get('licenseurl')} | {d['identifier']}")
keep = re.compile(r"soak|worship|prayer|prophetic|instrumental|piano|pad|psalm|presence|holy spirit|intercession", re.I)
items = {}
for i, d in seen.items():
    if not keep.search(f"{d.get('title')} {d.get('subject')}"): continue
    try: m = S.get(f"https://archive.org/metadata/{i}", timeout=60).json()
    except Exception as ex: note("meta fail", i, ex); continue
    fs = [{"name": f["name"], "len": float(f["length"]) if re.match(r"^[\d.]+$", str(f.get("length", ""))) else None, "fmt": f.get("format")}
          for f in m.get("files", []) if f["name"].lower().endswith(".mp3")]
    md = m.get("metadata", {})
    items[i] = {**d, "desc": re.sub(r"<[^>]+>", " ", str(md.get("description", "")))[:600], "files": fs, "lic": md.get("licenseurl")}
    tot = sum(f["len"] or 0 for f in fs)
    note(f"ITEM {i} | {d.get('title')} | {d.get('creator')} | {md.get('licenseurl')} | {len(fs)} mp3 | {round(tot/60)} min")
json.dump(items, open("music2/items.json", "w"), indent=1, ensure_ascii=False)
open("music2/log.txt", "w").write("\n".join(log))
