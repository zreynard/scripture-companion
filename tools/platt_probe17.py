"""Stephen Davey elsewhere: SermonAudio's public RSS and Wisdom International's YouTube channel feed. Honest user agent."""
import re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=45); print(f"  {r.status_code} {u} ({len(r.content)} bytes)", flush=True); return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:120]}"); return None
print("==== SermonAudio")
for u in ("https://legacy.sermonaudio.com/rss_search.rss?keyword=Stephen+Davey&speakeronly=true",
          "https://legacy.sermonaudio.com/search.asp?speakeronly=true&keyword=Stephen+Davey",
          "https://www.sermonaudio.com/speakers/search?q=Stephen%20Davey"):
    r = get(u)
    if r is not None and r.ok:
        t = r.text; print("   items:", t.count("<item>"), "| titles:", re.findall(r"<title>([^<]{0,90})</title>", t)[:12], "| source/church:", sorted(set(re.findall(r"(?:sourceid|broadcaster)[=/]([a-z0-9]+)", t, re.I)))[:10])
print("==== YouTube")
for q in ("https://www.youtube.com/@WisdomInternational", "https://www.youtube.com/@wisdomonline", "https://www.youtube.com/@StephenDavey"):
    r = get(q)
    if r is not None and r.ok:
        ids = sorted(set(re.findall(r'"channelId":"(UC[\w-]{22})"', r.text)))[:3]; print("   channel ids:", ids)
        for cid in ids[:1]:
            f = get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
            if f is not None and f.ok: print("   latest:", re.findall(r"<title>([^<]{0,80})</title>", f.text)[:8])
