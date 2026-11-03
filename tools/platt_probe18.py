"""Stephen Davey: size of SermonAudio's wfth broadcaster and the @StephenDavey YouTube channel. Honest user agent."""
import json, re, subprocess, sys, requests, collections
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=60); print(f"  {r.status_code} {u} ({len(r.content)} bytes)", flush=True); return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:120]}"); return None
print("==== SermonAudio wfth")
r = get("https://legacy.sermonaudio.com/rss_source.rss?sourceid=wfth")
if r is not None and r.ok:
    t = r.text; its = t.split("<item>")[1:]; print("   items:", len(its))
    for it in its[:8]:
        g = lambda k: (re.search(rf"<{k}[^>]*>(.*?)</{k}>", it, re.S) or [None, ""])[1][:100]
        print("   -", g("title"), "|", g("itunes:duration"), "|", g("pubDate"), "|", (re.search(r'enclosure url="([^"]+)"', it) or [None, ""])[1])
for u in ("https://legacy.sermonaudio.com/sermonsource.asp?sourceid=wfth", "https://legacy.sermonaudio.com/search.asp?sourceonly=true&currsection=sermonssource&keyword=wfth"):
    r = get(u)
    if r is not None and r.ok:
        t = r.text; print("   counts:", re.findall(r"([\d,]+)\s+(?:sermons|Sermons|results)", t)[:6], "| sermon ids:", len(set(re.findall(r"SID=(\d+)", t))), "| book links:", len(re.findall(r"bibleonly|book=", t)))
print("==== YouTube @StephenDavey")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"], check=False)
for tab in ("videos", "streams"):
    p = subprocess.run(["yt-dlp", "--flat-playlist", "-J", f"https://www.youtube.com/@StephenDavey/{tab}"], capture_output=True, text=True)
    if p.returncode: print("  ", tab, "error", p.stderr[-300:]); continue
    j = json.loads(p.stdout); E = j.get("entries") or []
    long_ = [e for e in E if (e.get("duration") or 0) >= 25*60]
    print(f"   {tab}: channel={j.get('channel')} entries={len(E)} >=25min={len(long_)} hours={sum((e.get('duration') or 0) for e in E)/3600:.0f}")
    for e in long_[:15]: print("    -", e.get("title"), "|", round((e.get("duration") or 0)/60), "min")
    words = collections.Counter(w for e in E for w in re.findall(r"\b(Romans|Acts|John|Luke|Genesis|Revelation|Kings|Job|James|Mark|Matthew|Peter|Psalm|Ezra|Nehemiah|Exodus)\b", e.get("title") or ""))
    print("   books named in titles:", dict(words.most_common(16)))
