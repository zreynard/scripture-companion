"""Fetch a few URLs from GitHub's runner and save what came back (status, size, RSS item count,
regex hits, a snippet) to probe.json — for diagnosing feeds this sandbox cannot reach."""
import json, re, sys, requests
URLS = [
  "https://feeds.buzzsprout.com/112848.rss",
  "https://feeds.buzzsprout.com/112848.rss?page=2",
  "https://www.buzzsprout.com/112848/episodes",
  "https://www.buzzsprout.com/112848/episodes?page=2",
  "https://www.buzzsprout.com/112848",
  "https://praytheword.buzzsprout.com/",
  "https://itunes.apple.com/search?media=podcast&term=Pray%20the%20Word%20David%20Platt",
  "https://www.twr360.org/programs/ministry_id,2/series_id,48",
  "https://www.twr360.org/ministries/view/id,2",
]
SAVE = [
  "https://www.buzzsprout.com/112848/episodes",
  "https://www.twr360.org/programs/ministry_id,2/series_id,48",
  "https://www.buzzsprout.com/112848.js?container_id=buzzsprout-large-player&player=large",
]
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
out = []
for u in URLS + sys.argv[1:]:
    try:
        r = requests.get(u, headers=H, timeout=40)
        t = r.text
        out.append({"url": u, "status": r.status_code, "final": r.url, "bytes": len(t),
                    "items": t.count("<item>"), "episode_links": len(set(re.findall(r'/112848/episodes?/(\d+)', t))),
                    "twr_programs": len(set(re.findall(r'programs/view/id,(\d+)', t))),
                    "twr_series": sorted(set(re.findall(r'series_id,(\d+)', t)))[:80],
                    "next_page": re.findall(r'href="([^"]*page=\d+[^"]*)"', t)[:5],
                    "new_feed_url": re.findall(r'<itunes:new-feed-url>([^<]+)', t)[:1],
                    "first_title": re.findall(r'<title>([^<]{0,120})', t)[:3],
                    "last_item_date": re.findall(r'<pubDate>([^<]+)', t)[-1:],
                    "snippet": re.sub(r"\s+", " ", t[:1500])})
    except Exception as e:
        out.append({"url": u, "error": f"{type(e).__name__}: {e}"})
json.dump(out, open("probe.json", "w"), indent=1)
# full bodies for pages listed in SAVE (written to pages/N.html)
import os
os.makedirs("pages", exist_ok=True)
for i, u in enumerate(SAVE):
    try:
        open(f"pages/{i}.html", "w").write(f"<!-- {u} -->\n" + requests.get(u, headers=H, timeout=60).text)
    except Exception as e:
        open(f"pages/{i}.html", "w").write(f"<!-- {u} ERROR {e} -->")
print(json.dumps([{k: v for k, v in o.items() if k != "snippet"} for o in out], indent=1))
