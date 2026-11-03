"""Stephen Davey elsewhere: the old Colonial Baptist Church podcast (297 episodes, archived on Player.fm), and the Christian radio
sites that carry Wisdom for the Heart. Honest user agent; refusals are reported and left alone. Pages saved to probe3/."""
import json, os, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, save=None):
    try:
        r = requests.get(u, headers=H, timeout=45); print(f"  {r.status_code} {u} ({len(r.content)} b)", flush=True)
        if save and r.ok: open("probe3/" + save, "w").write(r.text)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:100]}"); return None
print("==== Apple directory: Colonial Baptist / Shepherd's Church")
for q in ("colonial+baptist+church+cary", "stephen+davey+colonial", "shepherds+church+cary", "wisdom+international+davey"):
    r = get(f"https://itunes.apple.com/search?term={q}&entity=podcast&limit=25")
    if r is not None and r.ok:
        for x in r.json().get("results", []): print(f"   - {x.get('collectionName')} | {x.get('artistName')} | eps={x.get('trackCount')} | {x.get('feedUrl')}")
print("==== Player.fm")
for sid in ("1279157", "2534601"):
    r = get(f"https://player.fm/series/{sid}", f"pfm_{sid}.html")
    if r is not None and r.ok: print("   feed:", re.findall(r'(https?://[^"\'\s<>]+(?:rss|feed|xml)[^"\'\s<>]*)', r.text)[:6], "| mp3:", re.findall(r'https?://[^"\'\s<>]+\.mp3', r.text)[:3])
print("==== Radio sites")
for u, sv in (("https://www.oneplace.com/ministries/wisdom-for-the-heart/", "op.html"), ("https://www.oneplace.com/ministries/wisdom-for-the-heart/listen/", "op_listen.html"),
              ("https://www.lightsource.com/ministry/wisdom-for-the-heart/", "ls.html"), ("https://myfaithradio.com/programs/wisdom-for-the-heart/", "mfr.html"),
              ("https://www.oneplace.com/ministries/wisdom-for-the-heart/podcast/", "op_pod.html")):
    r = get(u, sv)
    if r is not None and r.ok:
        t = r.text; print("   mp3:", len(re.findall(r"\.mp3", t)), "| feed:", sorted(set(re.findall(r'(https?://[^"\'\s<>]+(?:rss|podcast|feed)[^"\'\s<>]*)', t)))[:6],
                         "| episode links:", len(set(re.findall(r'href="([^"]*wisdom-for-the-heart/listen/[^"]+)"', t))), "| archive/page links:", sorted(set(re.findall(r'href="([^"]*(?:archive|page=|/page/)[^"]*)"', t)))[:5])
