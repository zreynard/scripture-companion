"""Free instrumental worship music: fetch candidate pages (license text, track lists, audio links) and search archive.org
for Creative Commons / public-domain worship instrumentals. Honest user agent; robots.txt honoured.
    python tools/music_probe.py [extra urls...] -> music/ (pages/*.html, found.json, log.txt), saved to diag-music"""
import json, os, re, sys, time, urllib.parse, urllib.robotparser
import requests
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
S = requests.Session(); S.headers["User-Agent"] = UA
os.makedirs("music/pages", exist_ok=True); log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
PAGES = [
 "https://www.fromhispresence.com/free-soaking-music/",
 "https://www.secretplaceministries.org/pages/genre/soaking-worship-music.html",
 "https://www.secretplaceministries.org/pages/journey/soaking/instrumental-soaking.html",
 "https://www.scottbuckley.com.au/library/she-moved-mountains/", "https://www.scottbuckley.com.au/library/there-is-a-place/",
 "https://www.scottbuckley.com.au/library/cobalt/", "https://www.scottbuckley.com.au/library/skyward/",
 "https://www.scottbuckley.com.au/tag/piano-music/", "https://www.scottbuckley.com.au/library/",
 "https://freemusicarchive.org/music/pamela-yuen/", "https://freemusicarchive.org/music/pamela-yuen/afterglow-ambient",
 "https://freemusicarchive.org/music/pamela-yuen/panacea", "https://freemusicarchive.org/music/pamela-yuen/piano-pieces",
 "https://soakingworship.castos.com/podcasts/28241/about", "https://blubrry.com/worshipinterludes/",
 "https://opengameart.org/content/the-budding-of-consciousness-%E2%80%93-cc0-ambient-minimalist-theme-yoiyami-blue-series-%E2%80%93-no4",
] + sys.argv[1:]
robots = {}
def allowed(u):
    h = urllib.parse.urlparse(u); base = f"{h.scheme}://{h.netloc}"
    if base not in robots:
        rp = urllib.robotparser.RobotFileParser()
        try: r = S.get(base + "/robots.txt", timeout=20); rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception: rp.parse([])
        robots[base] = rp
    return robots[base].can_fetch(UA, u)
found = {}
for u in PAGES:
    if not allowed(u): note("ROBOTS NO", u); continue
    try: r = S.get(u, timeout=40); time.sleep(1)
    except Exception as ex: note("FAIL", u, ex); continue
    t = r.text; fn = re.sub(r"[^a-z0-9]+", "_", u.lower())[8:110] + ".html"
    open(f"music/pages/{fn}", "w").write(t[:800000])
    aud = sorted(set(re.findall(r"""https?://[^"'\s<>]+?\.(?:mp3|m4a|ogg|flac|wav)(?:\?[^"'\s<>]*)?""", t)))
    lic = sorted(set(m.lower() for m in re.findall(r"creativecommons\.org/(?:licenses|publicdomain)/[a-z0-9.\-/]+|cc[ -]?by[ -a-z0-9.]*|cc0|public domain|royalty[- ]free|free (?:for|to) (?:use|download)[^<.]{0,80}|all rights reserved", t, re.I)))[:25]
    found[u] = {"status": r.status_code, "bytes": len(t), "audio": aud[:200], "license_hits": lic}
    note(f"{r.status_code} {u} | {len(aud)} audio links | {lic[:8]}")
# archive.org: CC / public-domain worship-ish instrumentals
qs = ['(soaking OR "instrumental worship" OR "worship instrumental" OR "prayer music" OR "worship piano" OR "hymns piano") AND mediatype:audio AND (licenseurl:*creativecommons* OR licenseurl:*publicdomain*)']
for q in qs:
    try:
        r = S.get("https://archive.org/advancedsearch.php", params={"q": q, "fl[]": ["identifier", "title", "creator", "licenseurl", "downloads", "date"], "rows": 300, "output": "json", "sort[]": "downloads desc"}, timeout=60).json()
        docs = r["response"]["docs"]; found["archive.org"] = docs
        note(f"archive.org: {r['response']['numFound']} items")
        for d in docs[:80]: note(f"  IA {d.get('downloads')} | {d.get('title')} | {d.get('creator')} | {d.get('licenseurl')} | {d['identifier']}")
    except Exception as ex: note("IA fail", ex)
json.dump(found, open("music/found.json", "w"), indent=1, ensure_ascii=False)
open("music/log.txt", "w").write("\n".join(log))
