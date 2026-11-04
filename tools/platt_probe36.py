"""The Story of Scripture parts with no audio in the app (3, 9, 13, 20, 21, 22): Radical's media library and search,
old captures of the David Platt Messages feed and of the oceans.com pages in the Internet Archive, and the series chart.
Public data, honest user agent. Saves probe3/sos_missing.json and probe3/sos_chart.txt."""
import json, os, re, time, html, subprocess, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
WANT = {3: "Abraham", 9: "Leviticus", 13: "Shepherd", 20: "Faithful Provider", 21: "Give Up on the Church", 22: "Fully Commit"}
out = {"media": [], "search": [], "feed_caps": [], "feed_items": [], "oceans_caps": [], "pages": []}
def get(u, **kw):
    try: return requests.get(u, headers=H, timeout=90, **kw)
    except Exception as e: print("  !", u, str(e)[:100]); return None
r = get("https://cdn.radical.net/images/20191206110353/2019-12-01_Chart-TheStoryofScripture.pdf")
if r is not None and r.ok:
    open("probe3/sos_chart.pdf", "wb").write(r.content)
    subprocess.run(["pdftotext", "-layout", "probe3/sos_chart.pdf", "probe3/sos_chart.txt"])
    print("== chart\n" + open("probe3/sos_chart.txt").read()[:6000])
for n, q in WANT.items():
    for params in ({"search": q, "media_type": "audio", "per_page": 50}, {"search": q + " 2019", "per_page": 50}):
        r = get("https://radical.net/wp-json/wp/v2/media", params=params); time.sleep(1)
        if r is not None and r.ok:
            for m in r.json():
                if "2019" in (m.get("date") or "") or ".mp3" in (m.get("source_url") or ""):
                    out["media"].append({"part": n, "title": html.unescape(m["title"]["rendered"]), "date": m["date"], "url": m["source_url"]})
    r = get("https://radical.net/wp-json/wp/v2/search", params={"search": q, "per_page": 50, "subtype": "radical-podcast"}); time.sleep(1)
    if r is not None and r.ok:
        for m in r.json(): out["search"].append({"part": n, "title": html.unescape(m["title"]), "url": m["url"]})
for m in out["search"]:
    r = get(m["url"]); time.sleep(1)
    if r is not None and r.ok:
        out["pages"].append({**m, "mp3": sorted(set(re.findall(r"https?://[^\"'\s<>]+?\.mp3", r.text)))[:4],
                             "date": re.findall(r'"datePublished":"([^"]+)"', r.text)[:1]})
# old captures of the podcast feed: it once listed episodes the current feed may have dropped
for feed in ("feeds.buzzsprout.com/107460.rss", "rss.buzzsprout.com/107460.rss"):
    r = get("https://web.archive.org/cdx/search/cdx", params={"url": feed, "from": "2019", "to": "2021", "output": "json", "filter": "statuscode:200", "collapse": "timestamp:6"})
    caps = r.json()[1:] if r is not None and r.ok and r.text.strip().startswith("[") else []
    out["feed_caps"] += [feed + " " + c[1] for c in caps]
    for c in caps[:12]:
        f = get(f"https://web.archive.org/web/{c[1]}id_/https://{feed}"); time.sleep(2)
        if f is None or not f.ok: continue
        for it in f.text.split("<item")[1:]:
            t = html.unescape((re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S) or [""])[0])
            if any(re.search(q, t, re.I) for q in WANT.values()):
                out["feed_items"].append({"cap": c[1], "title": t, "date": (re.findall(r"<pubDate>([^<]+)", it) or [""])[0],
                                          "enc": (re.findall(r'<enclosure[^>]+url="([^"]+)"', it) or [""])[0]})
for i in (4546, 4516, 4517, 4530, 4531, 4532, 4533, 4534, 4535, 4536, 4537, 4538, 4539, 4540, 4518, 4519, 4520):
    r = get("https://web.archive.org/cdx/search/cdx", params={"url": f"oceans.com/watch/{i}*", "output": "json", "limit": 5}); time.sleep(1.5)
    caps = r.json()[1:] if r is not None and r.ok and r.text.strip().startswith("[") else []
    for c in caps[:1]:
        p = get(f"https://web.archive.org/web/{c[1]}id_/{c[2]}"); time.sleep(2)
        if p is None or not p.ok: continue
        t = html.unescape((re.findall(r"<title>([^<]+)", p.text) or [""])[0])
        out["oceans_caps"].append({"id": i, "cap": c[1], "title": t, "media": sorted(set(re.findall(r"https?://[^\"'\s<>]+?\.(?:mp3|m4a|mp4|m3u8)", p.text)))[:4]})
for k, v in out.items():
    print(f"\n-- {k}: {len(v)}")
    for x in v[:60]: print("  ", json.dumps(x)[:300])
json.dump(out, open("probe3/sos_missing.json", "w"), indent=1)
