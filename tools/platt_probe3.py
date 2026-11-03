"""Third look (GitHub's servers). Saves what it finds to probe3/ (pushed to the diag branch) for study:
- radical.json: every Radical message (date, title, link, Scripture tags), to see which the app lacks
- mclean.json: McLean's sermon API (the church app's own data): fields, how far back, which speakers
- wayback.json: old Brook Hills sermon pages as the Internet Archive kept them, and whether their audio still plays"""
import json, os, re, time, requests

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
get = lambda u, **kw: requests.get(u, headers=H, timeout=60, **kw)
os.makedirs("probe3", exist_ok=True)

# Radical: all messages with Scripture names
terms, page = {}, 1
while page < 40:
    r = get(f"https://radical.net/wp-json/wp/v2/scripture?per_page=100&page={page}&_fields=id,name,parent")
    if r.status_code != 200 or not r.json(): break
    terms.update({t["id"]: t for t in r.json()}); page += 1
msgs, page = [], 1
while page < 40:
    r = get(f"https://radical.net/wp-json/wp/v2/message?per_page=100&page={page}&_fields=id,date,link,title,scripture,series")
    if r.status_code != 200 or not r.json(): break
    msgs += r.json(); page += 1
for m in msgs:
    m["title"] = m["title"]["rendered"]
    m["refs"] = [(terms[terms[t]["parent"]]["name"] + " " + terms[t]["name"]) if terms.get(t, {}).get("parent") in terms else terms.get(t, {}).get("name")
                 for t in m.get("scripture") or []]
json.dump(msgs, open("probe3/radical.json", "w"), indent=0)
print("radical messages", len(msgs), "terms", len(terms))

# McLean's sermon API
out = {}
r = get("https://mclean.api.pocketplatform.io/v1/sermons?limit=3")
out["sample"] = r.json()
for q in ("limit=1000", "limit=100&offset=100", "limit=100&page=2", "page=2", "limit=100&skip=100", "speaker=David%20Platt&limit=5", "search=Platt&limit=5"):
    try:
        j = get("https://mclean.api.pocketplatform.io/v1/sermons?" + q).json()
        d = j.get("data") if isinstance(j, dict) else j
        out[q] = {"keys": list(j.keys()) if isinstance(j, dict) else "list", "n": len(d or []),
                  "first": (d or [{}])[0].get("Description") if d else None, "last": (d or [{}])[-1].get("Description") if d else None,
                  "meta": {k: v for k, v in j.items() if k != "data"} if isinstance(j, dict) else None}
    except Exception as e:
        out[q] = str(e)[:200]
try:
    j = get("https://mclean.api.pocketplatform.io/v1/sermons?limit=5000").json()
    d = j.get("data") if isinstance(j, dict) else j
    out["all_count"] = len(d)
    json.dump(d, open("probe3/mclean_all.json", "w"))
except Exception as e:
    out["all"] = str(e)[:200]
json.dump(out, open("probe3/mclean.json", "w"), indent=1, default=str)
print("mclean", {k: (v["n"] if isinstance(v, dict) and "n" in v else "") for k, v in out.items()}, out.get("all_count"))

# Wayback: old Brook Hills sermon pages
r = get("https://web.archive.org/cdx/search/cdx", params={"url": "brookhills.org/media/sermons/*", "output": "json", "collapse": "urlkey",
                                                          "limit": 5000, "fl": "original,timestamp,statuscode", "filter": "statuscode:200"})
rows = r.json()[1:]
slugs = {}
for u, ts, sc in rows:
    m = re.search(r"/media/sermons/([a-z0-9-]+)/?$", u)
    if m and not m.group(1).startswith(("page", "category")): slugs.setdefault(m.group(1), (u, ts))
print("wayback sermon slugs", len(slugs))
samples = []
for slug, (u, ts) in list(slugs.items())[::max(1, len(slugs) // 12)][:12]:
    try:
        a = get(f"https://web.archive.org/web/{ts}id_/{u}")
        t = a.text
        aud = re.findall(r'href="(https?://[^"]+(?:_AUD\.mp4|\.mp3|\.m4a)[^"]*)"', t) or re.findall(r'<div class="action audio"><a href="([^"]+)"', t)
        by = re.findall(r'<div class="speakers">\s*By\s+([^<]+?)\s*</div>', t) or re.findall(r'(?:Speaker|By)[:\s]+(David Platt)', t)
        live = None
        if aud:
            try:
                h = requests.head(aud[0], headers=H, timeout=40, allow_redirects=True)
                live = [h.status_code, h.headers.get("content-type"), h.headers.get("content-length")]
            except Exception as e:
                live = str(e)[:80]
        samples.append({"slug": slug, "ts": ts, "status": a.status_code, "by": by[:1], "audio": aud[:2], "live": live,
                        "verse": re.findall(r'<h4 class="verse">\s*([^<]+?)\s*</h4>', t)[:2], "date": re.findall(r'<time datetime="([^"]+)"', t)[:1],
                        "links": list(dict.fromkeys(re.findall(r'href="(https?://[^"]*(?:mp3|mp4|m4a|audio|media|download)[^"]*)"', t)))[:6]})
        time.sleep(1)
    except Exception as e:
        samples.append({"slug": slug, "error": str(e)[:120]})
json.dump({"slugs": slugs, "samples": samples}, open("probe3/wayback.json", "w"), indent=1)
for s in samples: print(json.dumps(s)[:400])
