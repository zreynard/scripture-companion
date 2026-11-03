"""Stephen Davey on SermonAudio: list every sermon (title, date, passage, length, mp3) from the public search pages,
one page a second. Honest user agent. Writes probe3/sa_davey.json."""
import json, os, re, time, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
out, seen = [], set()
for p in range(1, 60):
    u = f"https://legacy.sermonaudio.com/search.asp?currpage={p}&keyword=Stephen%5FDavey&SpeakerOnly=true&AudioOnly=false&sortby=added"
    try: r = requests.get(u, headers=H, timeout=60)
    except Exception as e: print("!", p, e); break
    if p == 1: open("probe3/sa_page1.html", "w").write(r.text)
    rows = r.text.split("sermoninfo.asp?SID=")[1:]
    new = 0
    for chunk in rows:
        sid = re.match(r"(\d+)", chunk).group(1)
        if sid in seen: continue
        seen.add(sid); new += 1
        t = html.unescape((re.search(r">([^<]{2,160})<", chunk) or [None, ""])[1]).strip()
        seg = chunk[:3000]
        out.append({"sid": sid, "title": t,
                    "date": (re.search(r"(\d{1,2}/\d{1,2}/\d{4})", seg) or [None, ""])[1],
                    "ref": html.unescape((re.search(r'bibleref[^>]*>([^<]+)<|class="?ref"?[^>]*>([^<]+)<', seg, re.I) or [None, ""])[1] or ""),
                    "len": (re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", seg) or [None, ""])[1],
                    "mp3": (re.search(r'https?://mp3\.sermonaudio\.com/[^"\']+\.mp3', seg) or [""])[0]})
    print(f"page {p}: {r.status_code} new={new} total={len(out)}", flush=True)
    if not new: break
    time.sleep(1)
json.dump(out, open("probe3/sa_davey.json", "w"), indent=0)
