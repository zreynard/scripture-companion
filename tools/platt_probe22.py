"""Stephen Davey on Subsplash, the platform behind Wisdom International's app (app key 3TZNBD): its public web pages,
feeds and the content API its web player uses. Honest user agent; anything that refuses is reported and left alone."""
import json, os, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)", "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
os.makedirs("probe3", exist_ok=True)
def get(u, save=None):
    try:
        r = requests.get(u, headers=H, timeout=45, allow_redirects=True); print(f"  {r.status_code} {u} -> {r.url[:90]} ({len(r.content)} b, {r.headers.get('content-type','')[:30]})", flush=True)
        if save and r.ok: open("probe3/" + save, "w").write(r.text)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:100]}"); return None
K = "3TZNBD"
for u, sv in ((f"https://subsplash.com/u/-{K}/media", "ss_media.html"), (f"https://subsplash.com/+{K.lower()}", "ss_plus.html"),
              (f"https://subsplash.com/u/-{K}", "ss_u.html"), (f"https://{K.lower()}.subspla.sh", "ss_short.html"),
              (f"https://core.subsplash.com/media/v1/media-series?filter%5Bapp_key%5D={K}&page%5Bsize%5D=50", "ss_series.json"),
              (f"https://core.subsplash.com/media/v1/media-items?filter%5Bapp_key%5D={K}&page%5Bsize%5D=50", "ss_items.json"),
              (f"https://core.subsplash.com/builder/v1/app-configs?filter%5Bapp_key%5D={K}", "ss_cfg.json"),
              (f"https://feeds.subsplash.com/{K}", "ss_feeds.txt"),
              ("https://wisdomonline.org/podcast", "wo_podcast.html"), ("https://www.wisdomonline.org/rss", "wo_rss.xml"),
              ("https://www.wisdomonline.org/feed", "wo_feed.xml")):
    r = get(u, sv)
    if r is not None and r.ok:
        t = r.text
        print("    hints:", sorted(set(re.findall(r"(feeds\.subsplash\.com/[^\"'\s<]+|cdn\.subsplash\.com/audios/[^\"'\s<]+|/media-series/[a-z0-9-]+|podcasts?/[a-z0-9-]{4,})", t)))[:12],
              "| titles:", re.findall(r'"title"\s*:\s*"([^"]{3,80})"', t)[:10], "| total:", re.findall(r'"total"\s*:\s*(\d+)', t)[:3])
