"""Public web archives for Stephen Davey's sermon pages and audio links: the Internet Archive (CDX index, by domain and by prefix,
and the availability API) and Common Crawl's public index. Honest user agent. Writes what it finds to probe3/."""
import json, os, re, requests, collections
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, t=180):
    try:
        r = requests.get(u, headers=H, timeout=t); print(f"  {r.status_code} {u[:150]} ({len(r.content)} b)", flush=True); return r
    except Exception as e:
        print(f"  ! {u[:120]}: {type(e).__name__} {str(e)[:80]}"); return None
print("==== Internet Archive")
for u in ("https://archive.org/wayback/available?url=wisdomonline.org/teaching-series/genesis",
          "https://archive.org/wayback/available?url=wisdomonline.org/teachings-detail/romans-lesson-71",
          "https://web.archive.org/cdx/search/cdx?url=wisdomonline.org&matchType=domain&output=json&fl=original&collapse=urlkey&limit=20",
          "https://web.archive.org/cdx/search/cdx?url=wisdomonline.org/teachings-detail/&matchType=prefix&output=json&fl=original,timestamp,statuscode&collapse=urlkey&limit=3000",
          "https://web.archive.org/cdx/search/cdx?url=atl1.cdn.digitaloceanspaces.com&matchType=domain&output=json&fl=original&collapse=urlkey&filter=original:.*wisdomonline.*&limit=3000"):
    r = get(u)
    if r is not None and r.ok: print("   ", r.text[:600].replace("\n", " "))
print("==== Common Crawl")
r = get("https://index.commoncrawl.org/collinfo.json", 60)
cols = [c["cdx-api"] for c in (r.json() if r is not None and r.ok else [])][:6]
pages = {}
for api in cols:
    for q in ("wisdomonline.org/teachings-detail/*", "www.wisdomonline.org/teachings-detail/*"):
        x = get(f"{api}?url={q}&output=json&limit=5000", 240)
        if x is None or not x.ok: continue
        rows = [json.loads(l) for l in x.text.splitlines() if l.strip().startswith("{")]
        for o in rows:
            k = re.sub(r"^https?://(www\.)?", "", o["url"]).split("?")[0]
            if o.get("status") == "200" and k not in pages: pages[k] = o
        print(f"   {api.split('/')[-1]} {q}: {len(rows)} rows, {len(pages)} distinct ok pages so far")
json.dump(list(pages.values()), open("probe3/cc_pages.json", "w"))
print("distinct sermon pages in Common Crawl with status 200:", len(pages))
if pages:
    o = next(iter(pages.values()))
    rng = f"bytes={int(o['offset'])}-{int(o['offset']) + int(o['length']) - 1}"
    w = requests.get("https://data.commoncrawl.org/" + o["filename"], headers={**H, "Range": rng}, timeout=120)
    import gzip
    try:
        body = gzip.decompress(w.content).decode("utf-8", "replace")
        print("   sample record:", o["url"], "| mp3 links:", re.findall(r"https?://[^\"'\s<>]+\.mp3", body)[:3], "| h1:", re.findall(r"<h1[^>]*>(.*?)</h1>", body, re.S)[:1])
    except Exception as e: print("   sample fetch", w.status_code, e)
