"""Seventh look (GitHub's servers): the old Brook Hills audio files (2006-2013) the Internet Archive lists, and
whether the church's current storage still serves each one. Also A Chronicle of Redemption (2010) at Brook Hills.
Saves probe3/bh_audio.json. Plain requests, slow and polite."""
import collections, json, os, re, time, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
WB, NEW = "https://web.archive.org", "https://brookhills-a.atl1.cdn.digitaloceanspaces.com/"
os.makedirs("probe3", exist_ok=True)
def get(u, **kw):
    for k in range(5):
        try:
            r = requests.get(u, headers=H, timeout=120, **kw)
            if r.status_code in (429, 502, 503, 504): time.sleep(20 * (k + 1)); continue
            time.sleep(2); return r
        except requests.RequestException as e: print("  retry", type(e).__name__, flush=True); time.sleep(15 * (k + 1))
names = {}
for q in ("brookhills.org/audio/", "brookhills.org/media/files_audio/", "brookhills.org/media/audio/", "pseudo01.hddn.com/vod/brookhills.agroup/audio/"):
    r = get(WB + "/cdx/search/cdx", params={"url": q, "matchType": "prefix", "output": "json", "collapse": "urlkey", "fl": "original,timestamp", "limit": 20000})
    rows = r.json()[1:] if r is not None and r.ok and r.text.strip() else []
    print(q, len(rows), flush=True)
    for u, ts in rows:
        n = u.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if re.search(r"\.(mp3|mp4|m4a)$", n, re.I): names.setdefault(n, (u, ts))
print("distinct audio files", len(names))
pre = collections.Counter(re.sub(r"[\d_]*(AUD)?\.\w+$", "", n, flags=re.I).upper() for n in names)
print("series prefixes", pre.most_common(120))
chron = sorted(n for n in names if re.search(r"chron|redemp|prolog|epilog", n, re.I))
print("chronicle-like", chron)
live = {}
for n in sorted(names):
    try:
        h = requests.head(NEW + requests.utils.quote(n), headers=H, timeout=30, allow_redirects=True)
        live[n] = h.status_code == 200 and int(h.headers.get("content-length") or 0) > 500_000
    except requests.RequestException: live[n] = False
    time.sleep(0.3)
print("still served by the church:", sum(live.values()), "of", len(live))
print("  live examples", [n for n in sorted(live) if live[n]][:80])
for q in ("brookhills.org/media/series/a-chronicle-of-redemption", "brookhills.org/media/series/chronicle"):
    r = get(WB + "/cdx/search/cdx", params={"url": q, "matchType": "prefix", "output": "json", "collapse": "urlkey", "fl": "original,timestamp", "filter": "statuscode:200", "limit": 50})
    rows = r.json()[1:] if r is not None and r.ok and r.text.strip() else []
    print("series pages", q, rows[:5])
    for u, ts in rows[:2]:
        p = get(f"{WB}/web/{ts}id_/{u}")
        if p is not None and p.ok:
            print("   ", u, "audio:", list(dict.fromkeys(re.findall(r'https?://[^"\'\s>]+\.(?:mp3|mp4)', p.text)))[:60])
            print("    titles:", re.findall(r'<h[34][^>]*>\s*(?:<a[^>]*>)?([^<]{4,80})', p.text)[:60])
json.dump({"names": names, "live": live}, open("probe3/bh_audio.json", "w"))
