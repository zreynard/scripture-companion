"""Fifth look (GitHub's servers): the old Brook Hills website (2006-2013), before the /media/sermons/ pages existed.
Where were its sermon lists, its podcast feed, and its audio files? Saves the Archive's list of the old site's
addresses to probe3/bh_old.json (pushed to the diag branch). Plain requests, slow and polite."""
import collections, json, os, re, time, requests

H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
WB = "https://web.archive.org"
os.makedirs("probe3", exist_ok=True)


def get(u, tries=6, **kw):
    for k in range(tries):
        try:
            r = requests.get(u, headers=H, timeout=120, **kw)
            if r.status_code in (429, 502, 503, 504): time.sleep(20 * (k + 1)); continue
            time.sleep(2.5)
            return r
        except requests.RequestException as e:
            print("  retry", u[:100], type(e).__name__, flush=True); time.sleep(15 * (k + 1))


def cdx(**p):
    p.setdefault("output", "json")
    r = get(WB + "/cdx/search/cdx", params=p)
    if r is None or not r.ok: print("cdx failed", p, r and r.status_code, flush=True); return []
    rows = r.json()
    return [dict(zip(rows[0], x)) for x in rows[1:]] if rows else []


# 1. Every address the Archive kept for the church's site, 2005-2013, page by page
rows = []
for host in ("brookhills.org", "churchatbrookhills.org", "brookhills.net"):
    n = get(WB + "/cdx/search/cdx", params={"url": host, "matchType": "domain", "from": "2005", "to": "2013", "showNumPages": "true"})
    pages = int(n.text.strip()) if n is not None and n.ok and n.text.strip().isdigit() else 0
    print(host, "cdx pages", pages, flush=True)
    for i in range(min(pages, 60)):
        got = cdx(url=host, matchType="domain", **{"from": "2005", "to": "2013"}, page=i, fl="original,timestamp,mimetype,statuscode",
                  collapse="urlkey")
        rows += got
        print(f"  page {i}: +{len(got)} ({len(rows)})", flush=True)
json.dump(rows, open("probe3/bh_old.json", "w"))
ok = [x for x in rows if x.get("statuscode") == "200"]
print("addresses:", len(rows), "ok:", len(ok))
pre = collections.Counter("/".join(re.sub(r"^https?://[^/]+", "", x["original"]).split("?")[0].strip("/").split("/")[:2]) for x in ok)
print("by path:", pre.most_common(60))
print("types:", collections.Counter(x["mimetype"] for x in ok).most_common(15))
aud = [x["original"] for x in rows if re.search(r"audio|mpeg|mp4", x["mimetype"]) or re.search(r"\.(mp3|m4a|mp4)\b", x["original"], re.I)]
print("audio addresses:", len(aud), aud[:40])
feeds = [x for x in ok if re.search(r"xml|rss", x["mimetype"]) or re.search(r"rss|feed|podcast|\.xml", x["original"], re.I)]
print("feed-like:", len(feeds), sorted({x["original"] for x in feeds})[:60])

# 2. Old home and sermon pages: the feed the site advertised and where its sermon links pointed
def snap(u, ts):
    r = get(f"{WB}/web/{ts}id_/{u}")
    if r is None or not r.ok: print("  no copy", u, ts); return ""
    return r.text

for ts in ("2008", "2010", "2012", "2013"):
    t = snap("http://www.brookhills.org/", ts + "0601")
    print(f"\n== home {ts}: {len(t)} bytes")
    print("  feeds:", re.findall(r'<link[^>]+(?:rss|atom)[^>]+>', t, re.I)[:5])
    print("  sermon-ish links:", list(dict.fromkeys(re.findall(r'href="([^"]*(?:sermon|media|podcast|audio|message|listen|resources)[^"]*)"', t, re.I)))[:25])
    print("  audio links:", list(dict.fromkeys(re.findall(r'(https?://[^"\'\s>]+\.(?:mp3|m4a|mp4))', t, re.I)))[:10])

cands = [x for x in ok if re.search(r"sermon|media|podcast|message|audio", x["original"], re.I) and "text/html" in x["mimetype"]]
picked = cands[:: max(1, len(cands) // 15)][:15]
for x in picked:
    t = snap(x["original"], x["timestamp"])
    if not t: continue
    print(f"\n== {x['original']} @{x['timestamp']}: {len(t)} bytes; platt {len(re.findall('platt', t, re.I))}")
    print("  audio:", list(dict.fromkeys(re.findall(r'(https?://[^"\'\s>]+\.(?:mp3|m4a|mp4)[^"\'\s>]*)', t, re.I)))[:8])
    print("  links:", list(dict.fromkeys(re.findall(r'href="([^"]*(?:sermon|media|podcast|download|series)[^"]*)"', t, re.I)))[:15])

# 3. Podcast directories: the church's feed address, as Apple lists it
for term in ("Brook Hills", "Church at Brook Hills", "Brook Hills sermons", "David Platt Brook Hills"):
    r = get("https://itunes.apple.com/search", params={"media": "podcast", "entity": "podcast", "term": term, "limit": 25})
    if r is not None and r.ok:
        for x in r.json().get("results", []):
            print(f"  [{term}] {x.get('collectionName')!r} by {x.get('artistName')!r} n={x.get('trackCount')} feed={x.get('feedUrl')}")
