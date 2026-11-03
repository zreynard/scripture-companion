"""David Platt's Brook Hills sermons (2006-2014) that the church's current site no longer lists.

The church still serves its audio: it moved the files from its old storage (Rackspace) to DigitalOcean under the same
names. What it no longer has is the list. The Internet Archive kept the list: old copies of the church's podcast feeds
and sermon pages name each sermon, its preacher, date, passage and audio file. This reads those copies (slowly, the
Archive asks for that), keeps David Platt's, and checks each audio file plays from the church's current storage.

    python tools/brookhills_archive.py      -> data/brookhills_archive.json
Runs on GitHub's servers. Plain requests; a refusal is logged and left alone."""
import html, json, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "brookhills_archive.json")
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
NEW = "https://brookhills-a.atl1.cdn.digitaloceanspaces.com/"
WB = "https://web.archive.org"


def log(*a): print(*a, flush=True)


def wb_get(url, tries=6):
    """The Archive rate-limits: wait and try again rather than hammer it."""
    for k in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=90)
            if r.status_code in (429, 503):
                time.sleep(20 * (k + 1)); continue
            time.sleep(2.5)
            return r
        except requests.RequestException as e:
            log("  retry", url[:100], type(e).__name__); time.sleep(15 * (k + 1))
    return None


def cdx(**params):
    params.setdefault("output", "json")
    r = wb_get(WB + "/cdx/search/cdx?" + "&".join(f"{k}={requests.utils.quote(str(v), safe='*:,')}" for k, v in params.items()))
    if r is None or not r.ok:
        log("cdx failed", params, r and r.status_code); return []
    rows = r.json()
    return [dict(zip(rows[0], x)) for x in rows[1:]] if rows else []


def fname(u):
    return u.split("?")[0].rstrip("/").rsplit("/", 1)[-1]


checked = {}
def plays(name):
    """Does the church's current storage serve this file?"""
    if name in checked: return checked[name]
    try:
        h = requests.head(NEW + requests.utils.quote(name), headers=H, timeout=40, allow_redirects=True)
        ok = h.status_code == 200 and int(h.headers.get("content-length") or 0) > 500_000
        checked[name] = (NEW + requests.utils.quote(name)) if ok else None
    except requests.RequestException:
        checked[name] = None
    return checked[name]


def clean(t): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


found = {}  # audio file name -> sermon
def keep(name, **kw):
    if not name: return
    cur = found.get(name, {})
    for k, v in kw.items():
        if v and not cur.get(k): cur[k] = v
    found[name] = cur


# 1. The podcast feeds, as archived over the years (one copy a month is plenty: a feed lists the newest ~100)
feeds = {}
for q in ("brookhills.org/podcast*", "brookhills.org/feed*", "brookhills.org/media/*.xml", "brookhills.org/*rss*", "feeds.feedburner.com/brookhills*",
          "feeds.feedburner.com/BrookHills*", "feeds.feedburner.com/TheChurchAtBrookHills*"):
    for x in cdx(url=q, matchType="prefix" if q.endswith("*") else "exact", filter="statuscode:200", collapse="timestamp:6", limit=3000,
                 fl="original,timestamp,mimetype"):
        if "xml" in x["mimetype"] or "rss" in x["mimetype"] or x["original"].endswith((".xml", "/podcasts", "/podcast", "/video")):
            feeds.setdefault(x["original"], []).append(x["timestamp"])
log("feed urls:", {k: len(v) for k, v in feeds.items()})
for u, stamps in feeds.items():
    for ts in stamps:
        r = wb_get(f"{WB}/web/{ts}id_/{u}")
        if r is None or not r.ok: continue
        for item in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            enc = re.search(r'<enclosure[^>]+url="([^"]+)"', item)
            if not enc: continue
            who = clean((re.search(r"<itunes:author>(.*?)</itunes:author>", item, re.S) or re.search(r"<author>(.*?)</author>", item, re.S) or [None, ""])[1])
            keep(fname(enc.group(1)), title=clean((re.search(r"<title>(.*?)</title>", item, re.S) or [None, ""])[1]),
                 date=clean((re.search(r"<pubDate>(.*?)</pubDate>", item, re.S) or [None, ""])[1]), who=who,
                 desc=clean((re.search(r"<description>(.*?)</description>", item, re.S) or re.search(r"<itunes:summary>(.*?)</itunes:summary>", item, re.S) or [None, ""])[1])[:600],
                 via=f"{WB}/web/{ts}/{u}")
    log(f"  {u}: {len(found)} files so far")

# 2. The sermon pages the Archive kept (byline, date, passage, audio link)
pages = {}
for x in cdx(url="brookhills.org/media/sermons/", matchType="prefix", filter="statuscode:200", collapse="urlkey", limit=20000, fl="original,timestamp"):
    m = re.search(r"/media/sermons/([a-z0-9-]+)/?$", x["original"])
    if m and not m.group(1).startswith(("page", "category")): pages.setdefault(m.group(1), (x["original"], x["timestamp"]))
log("archived sermon pages:", len(pages))
for i, (slug, (u, ts)) in enumerate(sorted(pages.items())):
    r = wb_get(f"{WB}/web/{ts}id_/{u}")
    if r is None or not r.ok: continue
    t = r.text.split("<footer")[0]
    by = clean((re.search(r'<div class="speakers">\s*By\s+([^<]+?)\s*</div>', t) or [None, ""])[1])
    aud = re.findall(r'href="(https?://[^"]+_AUD\.mp4)"', t) or re.findall(r'<div class="action audio"><a href="([^"]+)"', t) or re.findall(r'href="(https?://[^"]+\.mp3)"', t)
    d = re.search(r'<time datetime="(\d\d)/(\d\d)/(\d{4})"', t)
    title = clean((re.search(r'</nav>\s*<h1>(.*?)</h1>', t, re.S) or re.search(r'<h1>(.*?)</h1>', t, re.S) or [None, ""])[1])
    series = clean((re.search(r'<nav class="breadcrumb">.*?<a [^>]*>([^<]+)</a>', t, re.S) or [None, ""])[1])
    verses = [clean(v) for v in re.findall(r'<h4 class="verse">\s*([^<]+?)\s*</h4>', t)]
    for a in aud[:1]:
        keep(fname(a), title=title, who=by, date=f"{d.group(3)}-{d.group(1)}-{d.group(2)}" if d else "", verses=verses, series=series,
             page=f"https://www.brookhills.org/media/sermons/{slug}/", via=f"{WB}/web/{ts}/{u}")
    if i % 50 == 0: log(f"  pages {i}/{len(pages)}; {len(found)} files")

# 3. Platt's, and only those whose audio the church still serves
out = []
for name, s in found.items():
    if not re.search(r"platt", s.get("who", "") + " " + s.get("desc", "")[:200], re.I): continue
    if not re.search(r"platt", s.get("who", ""), re.I) and re.search(r"\b(?:by|from)\s+(?!david platt)[A-Z][a-z]+ [A-Z][a-z]+", s.get("desc", "")): continue
    u = plays(name)
    s.update({"file": name, "audio": u})
    out.append(s)
json.dump(sorted(out, key=lambda s: s.get("date", "")), open(OUT, "w"), indent=1, ensure_ascii=False)
log(f"David Platt: {len(out)} sermons found, {sum(1 for s in out if s['audio'])} still playable from the church's storage")
yrs = {}
for s in out:
    y = re.search(r"(20\d\d)", s.get("date", ""))
    yrs[y.group(1) if y else "?"] = yrs.get(y.group(1) if y else "?", 0) + (1 if s["audio"] else 0)
log("playable by year:", dict(sorted(yrs.items())))
