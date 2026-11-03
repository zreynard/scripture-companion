"""The Colonial Baptist Church (Stephen Davey) podcast as Crossmap lists it: its feed address, episodes and whether the audio is
still served. Honest user agent."""
import os, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, save=None, **kw):
    try:
        r = requests.get(u, headers=H, timeout=45, **kw); print(f"  {r.status_code} {u} ({len(r.content)} b) -> {r.url[:100]}", flush=True)
        if save and r.ok: open("probe3/" + save, "w").write(r.text)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:100]}"); return None
r = get("https://podcasts.crossmap.com/channels/Stephen-Davey:-Colonial-Baptist-Church-Cary-NC-(Audio-Podcast)/1577", "crossmap.html")
if r is not None and r.ok:
    t = r.text
    feeds = sorted(set(re.findall(r'(https?://[^"\'\s<>]+(?:rss|feed|\.xml|podcast)[^"\'\s<>]*)', t)))
    mp3 = re.findall(r'https?://[^"\'\s<>]+\.mp3[^"\'\s<>]*', t)
    print("   feeds:", feeds[:10]); print("   mp3:", len(mp3), mp3[:4]); print("   episodes:", re.findall(r'"name"\s*:\s*"([^"]{4,90})"|<h\d[^>]*>([^<]{4,90})</h', t)[:10])
    for f in feeds[:4]:
        x = get(f, "colonial_feed.xml")
        if x is not None and x.ok and "<item" in x.text:
            items = x.text.split("<item")[1:]; print("   feed items:", len(items))
            enc = re.findall(r'enclosure[^>]+url="([^"]+)"', x.text); print("   enclosures:", enc[:3])
            dates = re.findall(r"<pubDate>([^<]+)</pubDate>", x.text); print("   dates:", dates[:1], dates[-1:])
            if enc:
                a = get(enc[0], headers={**H, "Range": "bytes=0-1023"}, allow_redirects=True)
                if a is not None: print("   audio:", a.status_code, a.headers.get("content-type"), a.headers.get("content-range"))
            break
    for u in mp3[:2]:
        a = get(u, headers={**H, "Range": "bytes=0-1023"}, allow_redirects=True)
        if a is not None: print("   audio:", a.status_code, a.headers.get("content-type"), a.headers.get("content-range"))
