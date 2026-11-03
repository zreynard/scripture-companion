"""Eleventh look (GitHub's servers): the Fearless Church Podcast feed (Buzzsprout 852544): is it fearlesstn.org's,
and its Nehemiah messages (title, date, speaker, passage, audio, length)."""
import re, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
clean = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!\[CDATA\[|\]\]>", "", t or "")))).strip()
r = requests.get("https://rss.buzzsprout.com/852544.rss", headers=H, timeout=60)
t = r.text; print("feed", r.status_code, len(t))
ch = t.split("<item>")[0]
print("channel:", clean((re.search(r"<title>(.*?)</title>", ch, re.S) or [None, ""])[1]), "|", clean((re.search(r"<link>(.*?)</link>", ch, re.S) or [None, ""])[1]), "|", clean((re.search(r"<itunes:author>(.*?)</itunes:author>", ch, re.S) or [None, ""])[1]), "|", clean((re.search(r"<description>(.*?)</description>", ch, re.S) or [None, ""])[1])[:300])
items = re.findall(r"<item>(.*?)</item>", t, re.S)
print("items", len(items))
f = lambda it, tag: clean((re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1])
neh = [it for it in items if re.search(r"nehemiah", it, re.I)]
print("nehemiah items", len(neh))
for it in neh:
    print("  ", f(it, "title")[:80], "|", f(it, "pubDate")[:16], "|", f(it, "itunes:author"), "|", f(it, "itunes:duration"), "|", (re.findall(r'<enclosure[^>]+url="([^"]+)"', it) or [""])[0][:90], "|", f(it, "description")[:220])
print("recent titles:", [f(it, "title")[:50] for it in items[:15]])
