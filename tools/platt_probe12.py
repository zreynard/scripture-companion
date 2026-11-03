"""Twelfth look (GitHub's servers): fearlesstn.org's archive and sermons pages as Squarespace serves them
(the ?format=json form of each page) and any embedded players (iframes), to find the Nehemiah messages."""
import json, re, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
clean = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
for path in ("/archive", "/sermons"):
    r = requests.get("https://www.fearlesstn.org" + path, headers=H, timeout=45)
    t = r.text
    print("\n==", path, r.status_code, len(t))
    print("  iframes:", re.findall(r'<iframe[^>]+src="([^"]+)"', t)[:20])
    print("  data-src/embeds:", list(dict.fromkeys(re.findall(r'(?:data-src|data-url|data-html)="([^"]{0,300})"', t)))[:12])
    print("  media hosts:", sorted(set(re.findall(r'(youtube\.com/[^"\'\s<>]{0,80}|youtu\.be/[^"\'\s<>]{0,40}|vimeo\.com/[^"\'\s<>]{0,60}|subsplash\.com/[^"\'\s<>]{0,80}|churchcenter\.com/[^"\'\s<>]{0,80}|\.mp3[^"\'\s<>]{0,20}|spotify\.com/[^"\'\s<>]{0,60}|podcasts\.apple\.com/[^"\'\s<>]{0,80}|buzzsprout\.com/[^"\'\s<>]{0,60}|anchor\.fm/[^"\'\s<>]{0,60})', t)))[:40])
    body = t.split("<body", 1)[-1]
    print("  body text:", clean(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S))[:2500])
    j = requests.get("https://www.fearlesstn.org" + path, params={"format": "json"}, headers=H, timeout=45)
    print("  json", j.status_code, j.headers.get("content-type"))
    try:
        d = j.json()
        print("  keys", list(d.keys())[:20]); col = d.get("collection") or {}; print("  collection", col.get("title"), col.get("typeName"), col.get("itemCount"))
        items = d.get("items") or []
        print("  items", len(items))
        for it in items[:200]:
            txt = (it.get("title") or "") + " " + clean(it.get("body") or "")[:300] + " " + (it.get("excerpt") or "")
            if re.search(r"nehemiah", txt, re.I) or len(items) < 30:
                print("   -", it.get("title"), "|", it.get("fullUrl"), "|", it.get("publishOn"), "|", (it.get("structuredContent") or {}).get("audioAssetUrl") if isinstance(it.get("structuredContent"), dict) else "", "|", re.findall(r'(?:youtube\.com/embed/[\w-]+|vimeo\.com/\d+|https?://[^"\s]+\.mp3)', json.dumps(it))[:3], "|", clean(it.get("excerpt") or "")[:150])
        main = (d.get("mainContent") or "")
        print("  mainContent media:", list(dict.fromkeys(re.findall(r'(?:youtube\.com/embed/[\w-]+|youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+|vimeo\.com/(?:video/)?\d+|https?://[^"\s<>]+\.mp3|subsplash[^"\s<>]{0,80}|churchcenter[^"\s<>]{0,80})', main + json.dumps(d))))[:40])
        print("  mainContent nehemiah:", [clean(x)[:200] for x in re.findall(r".{0,200}nehemiah.{0,200}", main, re.I | re.S)][:10])
    except Exception as e:
        print("  json parse", e, j.text[:200])
