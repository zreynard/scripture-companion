"""Where else does David Platt's preaching live? Run on GitHub's servers (this sandbox cannot reach most of these sites).
Prints what each source holds: how many messages, whether each one carries playable audio, and whether it names
its passage. Plain requests only: a site that refuses (bot check, sign-in) is reported and left alone."""
import json, re, sys, time, requests
if sys.argv[1:] and sys.argv[1] in ("2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36"):
    import runpy; runpy.run_path(__file__.replace("platt_probe.py", f"platt_probe{sys.argv[1]}.py")); sys.exit()

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}


def get(u, **kw):
    try:
        r = requests.get(u, headers=H, timeout=45, **kw)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:120]}")
        return None


def head(title):
    print("\n==== " + title, flush=True)


def hits(text, pats):
    return {p: len(re.findall(p, text, re.I)) for p in pats}


AUD = [r"\.mp3", r"\.m4a", r"buzzsprout", r"vimeo\.com/video", r"youtube\.com/embed|youtu\.be", r"<audio", r"podcast", r"download"]

# 1. Radical's own library (WordPress REST: public data the site serves to every browser)
head("radical.net REST")
r = get("https://radical.net/wp-json/wp/v2/types")
if r is not None:
    print("types:", r.status_code, list(r.json().keys()) if r.ok and r.headers.get("content-type", "").startswith("application/json") else r.text[:200])
for t in ("message", "podcast", "series", "sermon", "resource", "posts"):
    r = get(f"https://radical.net/wp-json/wp/v2/{t}?per_page=3&_fields=id,date,link,title,scripture,series,content")
    if r is None: continue
    print(f"{t}: {r.status_code} total={r.headers.get('X-WP-Total')} pages={r.headers.get('X-WP-TotalPages')}")
    if r.ok:
        try:
            for m in r.json()[:3]:
                c = (m.get("content") or {}).get("rendered", "")
                print("   ", m.get("date", "")[:10], (m.get("title") or {}).get("rendered", "")[:70], "|", m.get("link"), "| content", hits(c, AUD))
        except Exception as e:
            print("   parse", e)
r = get("https://radical.net/wp-json/wp/v2/message?per_page=100&page=1&_fields=id,date,link,title")
if r is not None and r.ok:
    ms = r.json()
    yrs = {}
    for p in range(1, int(r.headers.get("X-WP-TotalPages") or 1) + 1):
        rr = r if p == 1 else get(f"https://radical.net/wp-json/wp/v2/message?per_page=100&page={p}&_fields=id,date,link,title")
        if rr is None or not rr.ok: print("  page", p, rr and rr.status_code); break
        for m in rr.json(): yrs[m["date"][:4]] = yrs.get(m["date"][:4], 0) + 1
        time.sleep(0.5)
    print("messages by year:", dict(sorted(yrs.items())))
    for m in ms[:2] + ms[50:51]:
        pg = get(m["link"])
        if pg is None: continue
        t = pg.text
        print(f"  page {pg.status_code} {m['link']}: bytes={len(t)}", hits(t, AUD))
        print("    mp3s:", list(dict.fromkeys(re.findall(r'https?://[^"\'\s>]+\.(?:mp3|m4a)[^"\'\s>]*', t)))[:4])
        print("    embeds:", list(dict.fromkeys(re.findall(r'(?:player\.vimeo\.com/video/\d+|youtube\.com/embed/[\w-]+|buzzsprout\.com/\d+/\d+)', t)))[:4])

# 2. Podcast directories (Apple's public search, no key): every show that carries Platt
head("Apple Podcasts search")
for term in ("David Platt", "Radical David Platt", "McLean Bible Church", "Brook Hills", "David Platt sermons", "Secret Church"):
    r = get("https://itunes.apple.com/search", params={"media": "podcast", "entity": "podcast", "term": term, "limit": 50})
    if r is None or not r.ok: print(term, r and r.status_code); continue
    for x in r.json().get("results", []):
        print(f"  [{term}] {x.get('collectionName')!r} by {x.get('artistName')!r} episodes={x.get('trackCount')} feed={x.get('feedUrl')}")

# 3. McLean Bible Church: the sermon archive behind the website
head("McLean Bible Church")
for u in ("https://mcleanbible.org/sermons/", "https://mcleanbible.org/watch/", "https://mcleanbible.org/media/",
          "https://mcleanbible.org/wp-json/wp/v2/types", "https://mcleanbible.org/sermons/?speaker=david-platt",
          "https://mcleanbible.org/sitemap_index.xml", "https://mcleanbible.org/sitemap.xml"):
    r = get(u)
    if r is None: continue
    t = r.text
    print(f"{u}: {r.status_code} bytes={len(t)} final={r.url}", hits(t, AUD + [r"subsplash", r"wp-json", r"sermon", r"platt"]))
    print("   links:", list(dict.fromkeys(re.findall(r'href="(https?://[^"]*(?:sermon|series|message|watch|media|podcast)[^"]*)"', t)))[:12])
    print("   apis:", list(dict.fromkeys(re.findall(r'https?://[a-z0-9.-]*(?:subsplash|api|cdn|vimeo|sermon|podcast)[a-z0-9.-]*\.[a-z]+/[^"\'\s<]{0,80}', t)))[:12])
    if "xml" in u and r.ok: print("   sitemap entries:", re.findall(r"<loc>([^<]+)</loc>", t)[:40])

# 4. The Church at Brook Hills (Platt 2006-2014): how far back the archive goes
head("Brook Hills")
for u in ("https://www.brookhills.org/media/sermons/", "https://www.brookhills.org/media/sermons/category,Sermon/?speaker=David+Platt&category=Sermon",
          "https://www.brookhills.org/media/sermons/page,19/?speaker=David+Platt&category=Sermon", "https://www.brookhills.org/media/series/",
          "https://www.brookhills.org/sitemap.xml"):
    r = get(u)
    if r is None: continue
    t = r.text
    print(f"{u}: {r.status_code} bytes={len(t)}", "sermon links", len(set(re.findall(r'href="/media/sermons/([a-z0-9-]+)"', t))),
          "years", sorted(set(re.findall(r'datetime="\d\d/\d\d/(\d{4})"', t))), "pages", sorted(set(re.findall(r'page,(\d+)', t)), key=int)[-3:])
    print("   series links:", list(dict.fromkeys(re.findall(r'href="(/media/series/[^"]+)"', t)))[:15])
    if "sitemap" in u and r.ok: print("   sitemap:", len(re.findall(r"<loc>", t)), re.findall(r"<loc>([^<]+)</loc>", t)[:20])

# 5. Internet Archive: what is there under his name (only publisher uploads would be usable)
head("Internet Archive")
r = get("https://archive.org/advancedsearch.php", params={"q": '("David Platt") AND mediatype:(audio)', "fl[]": ["identifier", "title", "uploader", "collection", "date"],
                                                          "rows": 60, "output": "json"})
if r is not None and r.ok:
    d = r.json()["response"]; print("found", d["numFound"])
    for x in d["docs"][:60]: print("  ", x.get("identifier"), "|", str(x.get("title"))[:60], "|", x.get("uploader"), "|", x.get("collection"))
# the old Brook Hills site as the Wayback Machine saw it: did its sermon pages link mp3s?
for q in ("brookhills.org/media/sermons/*", "brookhills.org/*.mp3", "media.brookhills.org/*", "brookhills.org/media/download/*"):
    r = get("https://web.archive.org/cdx/search/cdx", params={"url": q, "output": "json", "collapse": "urlkey", "limit": 5000, "fl": "original,timestamp,mimetype,statuscode"})
    if r is None or not r.ok: print(q, r and r.status_code); continue
    rows = r.json()[1:]
    mimes = {}
    for x in rows: mimes[x[2]] = mimes.get(x[2], 0) + 1
    print(f"wayback {q}: {len(rows)} urls; types {dict(sorted(mimes.items(), key=lambda kv: -kv[1])[:6])}")
    print("   e.g.", [x[0] for x in rows if "mp3" in x[0] or "audio" in x[2]][:8] or [x[0] for x in rows[:8]])

# 6. Conference and ministry hosts with Platt messages and their own audio
head("Other hosts")
for u in ("https://www.desiringgod.org/authors/david-platt", "https://www.thegospelcoalition.org/profile/david-platt/",
          "https://www.sermonaudio.com/speakers/7445", "https://www.imb.org/?s=david+platt", "https://passionconferences.com/",
          "https://www.ligonier.org/learn/teachers/david-platt", "https://www.t4g.org/speakers/david-platt/"):
    r = get(u)
    if r is None: continue
    print(f"{u}: {r.status_code} bytes={len(r.text)} final={r.url}", hits(r.text, AUD + [r"platt"]))

# 7. Buzzsprout: does David Platt Messages hold more episodes on its site than its feed lists?
head("Buzzsprout 107460")
r = get("https://feeds.buzzsprout.com/107460.rss")
if r is not None: print("feed items:", r.text.count("<item>"), "oldest:", re.findall(r"<pubDate>([^<]+)", r.text)[-1:])
r = get("https://www.buzzsprout.com/107460")
if r is not None: print("site:", r.status_code, re.findall(r"(\d[\d,]*)\s+episodes", r.text, re.I)[:3])
