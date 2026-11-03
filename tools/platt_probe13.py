"""Thirteenth look (GitHub's servers): Fearless church's sermons on praise.global (the archive fearlesstn.org embeds):
the data behind the embed, its Nehemiah messages, and how each plays (audio file, podcast feed, video)."""
import json, re, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
clean = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
def get(u, **kw):
    try: return requests.get(u, headers=H, timeout=45, **kw)
    except requests.RequestException as e: print("  !", u[:90], type(e).__name__)
for u in ("https://praise.global/embed/church/fearlesstn/archive", "https://praise.global/church/fearlesstn", "https://praise.global/fearlesstn"):
    r = get(u)
    if r is None: continue
    t = r.text
    print("\n==", u, r.status_code, len(t), r.url)
    print("  scripts:", re.findall(r'<script[^>]+src="([^"]+)"', t)[:12])
    print("  feeds:", re.findall(r'<link[^>]+(?:rss|atom|alternate)[^>]+>', t, re.I)[:5])
    print("  api-ish:", sorted(set(re.findall(r'https?://[a-z0-9.-]*(?:api|cdn|media|stream|audio|praise)[a-z0-9.-]*\.[a-z]{2,}[^"\'\s<>]{0,100}', t)))[:30])
    print("  mp3/m3u8:", list(dict.fromkeys(re.findall(r'https?://[^"\'\s<>]+?\.(?:mp3|m4a|m3u8)', t)))[:10])
    print("  nehemiah:", [clean(x)[:220] for x in re.findall(r'.{0,240}nehemiah.{0,240}', t, re.I | re.S)][:12])
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    if m:
        d = json.loads(m.group(1)); s = json.dumps(d)
        print("  NEXT_DATA keys:", list((d.get("props") or {}).get("pageProps", {}).keys())[:20], "len", len(s))
        print("  NEXT nehemiah:", [x[:300] for x in re.findall(r'.{0,300}[Nn]ehemiah.{0,300}', s)][:8])
        print("  NEXT media:", list(dict.fromkeys(re.findall(r'https?://[^"\\\s]+?\.(?:mp3|m4a|m3u8|mp4)', s)))[:10])
    print("  text:", clean(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S))[:1500])
