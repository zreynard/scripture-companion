"""Fourth look (GitHub's servers): McLean's podcast before 2021, and conference hosts with Platt's messages."""
import re, time, requests

H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}


def get(u, **kw):
    for k in range(4):
        try:
            r = requests.get(u, headers=H, timeout=60, **kw)
            if r.status_code == 429: time.sleep(20 * (k + 1)); continue
            time.sleep(2)
            return r
        except Exception as e:
            print("  !", u[:90], type(e).__name__); time.sleep(10)


print("==== Apple: McLean's podcasts")
for i in ("990724465",):
    r = get(f"https://itunes.apple.com/lookup?id={i}&entity=podcast")
    if r is not None: print([(x.get("collectionName"), x.get("feedUrl"), x.get("trackCount")) for x in r.json().get("results", [])])

print("\n==== Wayback: McLean feed addresses")
seen = {}
for q in ("mcleanbible.org/*", "feeds.feedburner.com/mclean*", "feeds.feedburner.com/McLean*", "mclean.api.pocketplatform.io/*", "podcasts.subsplash.com/*mclean*"):
    r = get("https://web.archive.org/cdx/search/cdx", params={"url": q, "output": "json", "collapse": "urlkey", "limit": 20000,
                                                             "fl": "original,timestamp,mimetype", "filter": "statuscode:200"})
    if r is None or not r.ok: print(q, r and r.status_code); continue
    rows = r.json()[1:]
    feeds = [x for x in rows if re.search(r"rss|xml", x[2]) or re.search(r"podcast|feed|\.xml|rss", x[0], re.I)]
    print(f"{q}: {len(rows)} urls, feed-like {len(feeds)}")
    for x in feeds[:30]: print("   ", x)
    for x in feeds: seen[x[0]] = x[1]

print("\n==== an old McLean feed copy: who, when, where the audio is, does it still play")
for u, ts in list(seen.items())[:8]:
    r = get(f"https://web.archive.org/web/{ts}id_/{u}")
    if r is None or not r.ok: continue
    items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
    if not items: continue
    print(u, ts, "items", len(items))
    for it in items[:3]:
        enc = (re.findall(r'<enclosure[^>]+url="([^"]+)"', it) or [""])[0]
        live = None
        if enc:
            try:
                h = requests.head(enc, headers=H, timeout=40, allow_redirects=True); live = (h.status_code, h.headers.get("content-type"))
            except Exception as e: live = type(e).__name__
        print("   ", re.findall(r"<title>(.*?)</title>", it, re.S)[:1], re.findall(r"<pubDate>(.*?)</pubDate>", it)[:1],
              re.findall(r"<itunes:author>(.*?)</itunes:author>", it)[:1], enc[:110], live)

print("\n==== conference hosts")
r = get("https://www.thegospelcoalition.org/profile/david-platt/")
if r is not None:
    links = list(dict.fromkeys(re.findall(r'href="(https://www\.thegospelcoalition\.org/(?:conference_media|sermon|podcasts?|video)/[^"]+)"', r.text)))
    print("TGC media links:", len(links), links[:15])
    for l in links[:2]:
        p = get(l)
        if p is not None: print("   ", l, p.status_code, "mp3:", re.findall(r'https?://[^"\'\s]+\.mp3', p.text)[:2])
for u in ("https://www.desiringgod.org/search?q=david+platt", "https://www.sebts.edu/?s=platt", "https://www.imb.org/?s=platt+sermon",
          "https://www.sbc.net/?s=platt"):
    r = get(u)
    if r is not None: print(u, r.status_code, "mp3", len(re.findall(r"\.mp3", r.text)), "platt", len(re.findall("platt", r.text, re.I)))
