"""Sixth look (GitHub's servers): the Big Picture series' official listings.
A Chronicle of Redemption on radical.net (every message: date, title, speaker, passage, how it plays), and the
2018 Bible from 30,000 Feet listing in Calvary's shop. Plain requests; a refusal is reported and left alone."""
import json, os, re, time, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, **kw):
    for k in range(3):
        try:
            r = requests.get(u, headers=H, timeout=60, **kw); time.sleep(1.5); return r
        except requests.RequestException as e: print("  !", u[:90], type(e).__name__); time.sleep(8)
out = {}
r = get("https://radical.net/wp-json/wp/v2/series", params={"search": "chronicle", "per_page": 20})
print("series search", r and r.status_code)
ser = r.json() if r is not None and r.ok else []
for s in ser: print("  ", s.get("id"), s.get("name"), s.get("count"), s.get("link"))
msgs = []
for s in ser:
    if "chronicle" not in (s.get("name") or "").lower(): continue
    for page in range(1, 5):
        q = get("https://radical.net/wp-json/wp/v2/message", params={"series": s["id"], "per_page": 100, "page": page, "orderby": "date", "order": "asc"})
        if q is None or not q.ok or not q.json(): break
        msgs += q.json()
print("messages", len(msgs))
rows = []
for m in msgs:
    pg = get(m["link"]); t = pg.text if pg is not None and pg.ok else ""
    who = re.findall(r'(?:speaker|author)[^>]*>\s*(?:<[^>]+>\s*)*([A-Z][a-z]+ [A-Z][a-zA-Z]+)', t)[:2]
    rows.append({"id": m["id"], "date": m["date"][:10], "title": re.sub("<[^>]+>", "", m["title"]["rendered"]), "link": m["link"],
                 "acf": {k: v for k, v in (m.get("acf") or {}).items() if v} if isinstance(m.get("acf"), dict) else None,
                 "who": who, "mp3": list(dict.fromkeys(re.findall(r'https?://[^"\'\s>]+\.(?:mp3|m4a)', t)))[:3],
                 "embeds": list(dict.fromkeys(re.findall(r'(?:player\.vimeo\.com/video/\d+|youtube(?:-nocookie)?\.com/embed/[\w-]+|buzzsprout\.com/\d+/\d+)', t)))[:3],
                 "dur": re.findall(r'(\d{1,2}:\d{2}(?::\d{2})?)', t)[:2]})
    print(json.dumps(rows[-1])[:400], flush=True)
out["chronicle"] = rows
r = get("https://radical.net/series/a-chronicle-of-redemption/")
if r is not None:
    t = r.text; print("series page", r.status_code, len(t))
    print("  links", list(dict.fromkeys(re.findall(r'href="(https://radical\.net/(?:message|sermons?|podcasts?)/[^"]+)"', t)))[:60])
    print("  text", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:1500])
r = get("https://shop.calvaryabq.org/mm5/merchant.mvc?Category_Code=TS_Biblefrom30k2018&Screen=CTGY&Store_Code=CALVARY")
if r is not None:
    t = r.text; print("\ncalvary shop", r.status_code, len(t))
    names = re.findall(r'class="[^"]*(?:product|name|title)[^"]*"[^>]*>\s*(?:<a[^>]*>)?\s*([^<]{4,120})<', t)
    print("  names", len(names), names[:90])
    print("  text", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:3000])
json.dump(out, open("probe3/bigpicture.json", "w"), indent=1)
