"""Second look (GitHub's servers): Brook Hills' page links and McLean's sermon manager."""
import re, requests

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
get = lambda u, **kw: requests.get(u, headers=H, timeout=45, **kw)

print("==== Brook Hills pagination")
r = get("https://www.brookhills.org/media/sermons/category,Sermon/?speaker=David+Platt&category=Sermon")
print("page links:", list(dict.fromkeys(re.findall(r'href="([^"]*page,\d+[^"]*)"', r.text)))[:8])
print("first sermons:", list(dict.fromkeys(re.findall(r'href="/media/sermons/([a-z0-9-]+)"', r.text)))[:6])
for u in ("https://www.brookhills.org/media/sermons/category,Sermon/page,2/?speaker=David+Platt&category=Sermon",
          "https://www.brookhills.org/media/sermons/page,2/?speaker=David+Platt&category=Sermon",
          "https://www.brookhills.org/media/sermons/page,10/?speaker=David+Platt&category=Sermon",
          "https://www.brookhills.org/media/sermons/page,18/?speaker=David+Platt&category=Sermon"):
    t = get(u).text
    s = list(dict.fromkeys(re.findall(r'href="/media/sermons/([a-z0-9-]+)"', t)))
    s = [x for x in s if not x.startswith(("page,", "category"))]
    print(u, len(s), s[:4])
m = re.search(r'href="/media/sermons/([a-z0-9-]+)"', get("https://www.brookhills.org/media/sermons/page,15/?speaker=David+Platt&category=Sermon").text)
if m:
    t = get("https://www.brookhills.org/media/sermons/" + m.group(1)).text
    print("old sermon", m.group(1), "| by", re.findall(r'<div class="speakers">\s*By\s+([^<]+?)\s*</div>', t), "| date", re.findall(r'<time datetime="([^"]+)"', t)[:1],
          "| audio", re.findall(r'<div class="action audio"><a href="(https://[^"]+)"', t)[:1], re.findall(r'href="(https://[^"]+_AUD\.mp4)"', t)[:1],
          "| verse", re.findall(r'<h4 class="verse">\s*([^<]+?)\s*</h4>', t)[:2])
    a = (re.findall(r'<div class="action audio"><a href="(https://[^"]+)"', t) or re.findall(r'href="(https://[^"]+\.(?:mp3|mp4|m4a))"', t) or [""])[0]
    if a:
        h = requests.head(a, headers=H, timeout=45, allow_redirects=True)
        print("   audio head:", h.status_code, h.headers.get("content-type"), h.headers.get("content-length"), h.url[:120])

print("\n==== McLean sermon manager")
js = get("https://sermon-manager.mclean.apps.blackpulp.com/app/sermonmanager.js").text
print("js bytes", len(js))
print("urls:", list(dict.fromkeys(re.findall(r'https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9_./{}:-]*)?', js)))[:30])
print("paths:", list(dict.fromkeys(re.findall(r'["\'`](/(?:api|v\d)[a-zA-Z0-9_./${}:-]*)', js)))[:30])
t = get("https://mcleanbible.org/tysons/sermons/").text
print("page config:", re.findall(r'(?:data-[a-z-]+|sermonManager[A-Za-z]*)\s*=\s*["\'][^"\']{0,200}', t)[:10])
print("blackpulp mentions:", re.findall(r'[^"\'<>]{0,80}blackpulp[^"\'<>]{0,120}', t)[:6])
for u in ("https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id=1",
          "https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id=1&limit=2000",
          "https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id=1&page=2",
          "https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id=1&per_page=2000",
          "https://mclean.api.pocketplatform.io/v1/podcasts/feed.xml?series_type_id=1&offset=200",
          "https://mclean.api.pocketplatform.io/v1/sermons?limit=5", "https://mclean.api.pocketplatform.io/v1/series?limit=5",
          "https://mclean.api.pocketplatform.io/v1/media?limit=5"):
    try:
        r = get(u); t = r.text
        print(u, r.status_code, "items", t.count("<item>"), "oldest", re.findall(r"<pubDate>([^<]+)", t)[-1:], "| ", re.sub(r"\s+", " ", t[:160]) if "<item>" not in t else "")
    except Exception as e:
        print(u, type(e).__name__)
