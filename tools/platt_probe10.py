"""Tenth look (GitHub's servers): Fearless church (fearlesstn.org) sermon archive, for its Nehemiah teaching.
What the archive lists, where each message plays (podcast feed, Subsplash, Vimeo, YouTube, mp3), and its passage.
Plain requests under the app's own name."""
import json, re, time, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
def get(u, **kw):
    try:
        r = requests.get(u, headers=H, timeout=45, **kw); time.sleep(1); return r
    except requests.RequestException as e: print("  !", u[:90], type(e).__name__)
clean = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
r = get("https://www.fearlesstn.org/archive")
t = r.text if r is not None else ""
print("archive", r and r.status_code, len(t), r is not None and r.url)
print("generator/platform:", re.findall(r'<meta[^>]+generator[^>]+>', t)[:2], sorted(set(re.findall(r'(squarespace|wix|subsplash|churchcenter|planningcenter|sermonaudio|vimeo|youtube|podbean|buzzsprout|anchor|spotify|apple\.com/podcast|libsyn|transistor|simplecast|wordpress|elvanto|faithlife|sermons\.io|onehub|churchco|clearstream|tithely|nucleus)', t, re.I))))
print("feeds:", re.findall(r'<link[^>]+(?:rss|atom)[^>]+>', t, re.I)[:5])
links = list(dict.fromkeys(re.findall(r'href="([^"]+)"', t)))
print("links", len(links)); print([l for l in links if re.search(r'nehem|sermon|series|archive|message|media|watch|listen|podcast', l, re.I)][:80])
print("nehemiah mentions:", [clean(m)[:160] for m in re.findall(r'.{0,200}nehemiah.{0,200}', t, re.I | re.S)][:20])
print("media:", list(dict.fromkeys(re.findall(r'https?://[^"\'\s<>]+?(?:\.mp3|\.m4a|vimeo\.com/[^"\'\s<>]+|youtu[^"\'\s<>]+|subsplash[^"\'\s<>]+|churchcenter[^"\'\s<>]+)', t)))[:40])
print("text:", clean(t)[:3000])
neh = [l for l in links if re.search(r'nehem', l, re.I)]
for l in neh[:6]:
    u = l if l.startswith("http") else "https://www.fearlesstn.org" + ("" if l.startswith("/") else "/") + l
    p = get(u)
    if p is None: continue
    pt = p.text
    print("\n== ", u, p.status_code, len(pt))
    print("  links:", [x for x in dict.fromkeys(re.findall(r'href="([^"]+)"', pt)) if re.search(r'nehem|sermon|media|watch|listen|mp3|vimeo|youtu|subsplash', x, re.I)][:40])
    print("  media:", list(dict.fromkeys(re.findall(r'https?://[^"\'\s<>]+?(?:\.mp3|\.m4a|vimeo\.com/[^"\'\s<>]+|youtu[^"\'\s<>]+|subsplash[^"\'\s<>]+)', pt)))[:20])
    print("  text:", clean(pt)[:1500])
for q in ("Fearless Church", "Fearless TN", "fearlesstn"):
    a = get("https://itunes.apple.com/search", params={"media": "podcast", "entity": "podcast", "term": q, "limit": 10})
    if a is not None and a.ok:
        for x in a.json().get("results", []): print(f"  [{q}] {x.get('collectionName')!r} by {x.get('artistName')!r} n={x.get('trackCount')} feed={x.get('feedUrl')}")
