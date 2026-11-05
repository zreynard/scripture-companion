"""Free soaking / instrumental worship feeds: what each holds (episodes, lengths, audio host) and whether its audio loads.
    python tools/soak_probe.py -> soak/feeds.json, soak/log.txt (saved to the diag-soak branch)"""
import json, os, re, subprocess, statistics
import xml.etree.ElementTree as ET
import requests
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
S = requests.Session(); S.headers["User-Agent"] = UA
os.makedirs("soak", exist_ok=True); log = []
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)
feeds = {}
for q in ("soaking worship", "instrumental worship", "soaking music", "worship interludes", "instrumental soaking worship",
          "prayer instrumental music", "soaking in his presence", "worship pads", "in the wait soaking worship", "a kind and gentle word"):
    try: r = S.get("https://itunes.apple.com/search", params={"term": q, "media": "podcast", "limit": 30}, timeout=30).json()
    except Exception as ex: note("search fail", q, ex); continue
    for x in r.get("results", []):
        if x.get("feedUrl"): feeds.setdefault(x["feedUrl"], {"name": x.get("collectionName"), "artist": x.get("artistName"), "genre": x.get("primaryGenreName")})
import sys
for u in sys.argv[1:]: feeds.setdefault(u, {"name": u, "artist": "", "genre": ""})
music_extra = set(sys.argv[1:])
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
def dur(s):
    if not s: return None
    v = 0
    for x in s.strip().split(":"):
        try: v = v * 60 + int(float(x))
        except ValueError: return None
    return v
music = re.compile(r"soak|instrumental|interlude|pad|piano|worship music|prayer music|ambient", re.I)
for u, f in list(feeds.items()):
    if u not in music_extra and not music.search(f"{f['name']} {f['artist']}"): del feeds[u]; continue
    try: r = S.get(u, timeout=40); root = ET.fromstring(r.content)
    except Exception as ex: f["err"] = str(ex)[:100]; note("FAIL", f["name"], u, ex); continue
    eps = []
    for it in root.iter("item"):
        e = it.find("enclosure")
        eps.append({"t": (it.findtext("title") or "").strip(), "date": it.findtext("pubDate"), "dur": dur(it.findtext("itunes:duration", namespaces=NS)), "audio": e.get("url") if e is not None else None})
    ds = [e["dur"] for e in eps if e["dur"]]
    f.update(n=len(eps), eps=eps[:400], med_min=round(statistics.median(ds) / 60) if ds else None, total_h=round(sum(ds) / 3600, 1) if ds else None,
             hosts=sorted({re.sub(r"https?://([^/]+).*", r"\1", e["audio"]) for e in eps if e["audio"]})[:4],
             last=eps[0]["date"] if eps else None, rights=root.findtext("channel/copyright"))
    a = next((e["audio"] for e in eps if e["audio"]), None)
    if a:
        p = subprocess.run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_entries", "format=duration", "-of", "csv=p=0", a], capture_output=True, text=True, timeout=120)
        f["loads"] = bool(p.stdout.strip())
    note(f"FEED {f['name']} | {f['artist']} | {f['n']} eps | median {f['med_min']} min | {f['total_h']} h | loads {f.get('loads')} | {f['hosts']} | last {f['last']} | (c) {f['rights']} | {u}")
json.dump(feeds, open("soak/feeds.json", "w"), indent=1, ensure_ascii=False)
open("soak/log.txt", "w").write("\n".join(log))
