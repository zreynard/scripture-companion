"""Fourteenth look (GitHub's servers): Fearless Church's sermon feed on praise.global: each item's title, date,
speaker, passage, audio and length, and whether the audio plays."""
import re, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
clean = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!\[CDATA\[|\]\]>", "", t or "")))).strip()
r = requests.get("https://praise.global/feed/fearlesstn", headers=H, timeout=60)
t = r.text; print("feed", r.status_code, r.headers.get("content-type"), len(t))
print("channel:", t.split("<item>")[0][:1200])
f = lambda it, tag: clean((re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1])
for it in re.findall(r"<item>(.*?)</item>", t, re.S):
    enc = (re.findall(r'<enclosure[^>]+>', it) or [""])[0]
    u = (re.findall(r'url="([^"]+)"', enc) or [""])[0]
    live = None
    if u:
        try:
            h = requests.head(u, headers=H, timeout=30, allow_redirects=True); live = (h.status_code, h.headers.get("content-type"), h.headers.get("content-length"), h.headers.get("access-control-allow-origin"), h.headers.get("accept-ranges"))
        except requests.RequestException as e: live = type(e).__name__
    print("\n-", f(it, "title"), "|", f(it, "pubDate"), "|", f(it, "itunes:author") or f(it, "author") or f(it, "dc:creator"), "|", f(it, "itunes:duration"), "|", f(it, "link"))
    print("   enc:", enc[:220], "| live:", live)
    print("   desc:", f(it, "description")[:400])
