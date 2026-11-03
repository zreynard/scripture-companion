"""Stephen Davey: what does his own library hold beyond the three Buzzsprout feeds? Plain requests, honest user agent;
a site that refuses (bot check, sign-in) is reported and left alone."""
import json, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=45); print(f"  {r.status_code} {u} ({len(r.content)} bytes, {r.headers.get('content-type','')[:40]})"); return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:120]}"); return None
def head(t): print("\n==== " + t, flush=True)

head("Apple Podcasts directory: Davey feeds")
r = get("https://itunes.apple.com/search?term=stephen+davey&entity=podcast&limit=50")
if r is not None and r.ok:
    for x in r.json().get("results", []):
        print(f"  - {x.get('collectionName')} | {x.get('artistName')} | eps={x.get('trackCount')} | {x.get('feedUrl')}")
r = get("https://itunes.apple.com/search?term=wisdom+for+the+heart&entity=podcast&limit=20")
if r is not None and r.ok:
    for x in r.json().get("results", []):
        print(f"  - {x.get('collectionName')} | {x.get('artistName')} | eps={x.get('trackCount')} | {x.get('feedUrl')}")

for site in ("https://wisdomonline.org", "https://www.wisdomonline.org", "https://wisdomintl.org"):
    head(site)
    r = get(site + "/robots.txt")
    if r is not None and r.ok: print("   robots:", r.text[:600].replace("\n", " | "))
    for p in ("/sitemap.xml", "/sitemap_index.xml", "/wp-json/wp/v2/types", "/sermons", "/sermons/"):
        r = get(site + p)
        if r is not None and r.ok:
            t = r.text
            print("   locs:", re.findall(r"<loc>([^<]+)</loc>", t)[:40])
            print("   mp3:", len(re.findall(r"\.mp3", t)), "audio tags:", len(re.findall(r"<audio", t)), "| sample links:", list(dict.fromkeys(re.findall(r'href="(https?://[^"]*(?:sermon|series|book)[^"]*)"', t)))[:25])
            if p.endswith("types"):
                try: print("   types:", list(r.json().keys()))
                except Exception: pass
