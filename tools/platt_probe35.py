"""Every part of David Platt's 'The Story of Scripture' (McLean Bible Church, 2019): from Radical's site (its public
WordPress data: the posts and the transcript PDFs it hosts), the oceans.com watch pages, and McLean's podcast feeds.
Honest user agent, a pause between requests. Saves probe3/story_of_scripture.json."""
import json, os, re, time, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
out = {"radical_media": [], "radical_search": [], "radical_posts": [], "oceans": [], "mclean_feed": []}
def get(u, **kw):
    try: return requests.get(u, headers=H, timeout=60, **kw)
    except Exception as e: print("  !", u, e); return None
print("== Radical: transcript PDFs and posts")
for q in ("StoryofScripture", "Story of Scripture", "Story-of-Scripture"):
    for page in range(1, 6):
        r = get("https://radical.net/wp-json/wp/v2/media", params={"search": q, "per_page": 100, "page": page})
        if not r or not r.ok: print("  media", q, page, r.status_code if r else None); break
        js = r.json()
        for m in js: out["radical_media"].append({"title": html.unescape(m.get("title", {}).get("rendered", "")), "date": m.get("date"), "url": m.get("source_url")})
        if len(js) < 100: break
        time.sleep(1)
    r = get("https://radical.net/wp-json/wp/v2/search", params={"search": q, "per_page": 100})
    if r and r.ok:
        for m in r.json(): out["radical_search"].append({"title": html.unescape(m.get("title", "")), "url": m.get("url"), "type": m.get("subtype")})
    time.sleep(1)
for m in out["radical_search"]:
    if "story-of-scripture" in (m["url"] or "") or "Story of Scripture" in m["title"]:
        r = get(m["url"]); time.sleep(1)
        if r and r.ok:
            t = r.text
            out["radical_posts"].append({"url": m["url"], "title": m["title"],
                "mp3": sorted(set(re.findall(r"https?://[^\"'\s<>]+?\.mp3", t)))[:5],
                "passage": re.findall(r"(?:Scripture|Passage|Text)[^<]{0,20}</[^>]+>\s*<[^>]+>([^<]{3,60})", t)[:3],
                "date": re.findall(r'"datePublished":"([^"]+)"', t)[:1]})
print("== oceans.com watch pages")
for i in range(4470, 4600):
    r = get(f"https://www.oceans.com/watch/{i}")
    if r is not None and r.ok:
        t = r.text
        tt = html.unescape((re.findall(r'<meta property="og:title" content="([^"]+)"', t) or re.findall(r"<title>([^<]+)", t) or [""])[0])
        if re.search(r"story of scripture", tt + t[:20000], re.I):
            d = html.unescape((re.findall(r'<meta (?:property|name)="og:description" content="([^"]+)"', t) or [""])[0])
            out["oceans"].append({"id": i, "title": tt, "desc": d[:300], "mp3": sorted(set(re.findall(r"https?://[^\"'\s<>]+?\.(?:mp3|m4a|m3u8|mp4)", t)))[:4]})
    time.sleep(0.7)
print("== McLean podcast feeds")
for k in range(1, 13):
    r = get(f"https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id={k}")
    if not r or not r.ok: continue
    for it in r.text.split("<item")[1:]:
        if re.search(r"story of scripture", it, re.I):
            g = lambda tag: html.unescape((re.findall(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", it, re.S) or [""])[0]).strip()
            out["mclean_feed"].append({"feed": k, "title": g("title"), "date": g("pubDate"), "enc": (re.findall(r'<enclosure[^>]+url="([^"]+)"', it) or [""])[0], "desc": g("description")[:200]})
    time.sleep(1)
for k, v in out.items():
    print(f"\n-- {k}: {len(v)}")
    for x in v[:80]: print("  ", json.dumps(x)[:260])
json.dump(out, open("probe3/story_of_scripture.json", "w"), indent=1)
