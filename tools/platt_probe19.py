"""Stephen Davey: SermonAudio speaker 14913 and the Wisdom International YouTube channel. Honest user agent; pages saved to probe3/."""
import json, os, re, subprocess, sys, requests, collections
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, save=None):
    try:
        r = requests.get(u, headers=H, timeout=60); print(f"  {r.status_code} {u} ({len(r.content)} bytes)", flush=True)
        if save and r.ok: open("probe3/" + save, "w").write(r.text)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:120]}"); return None
print("==== SermonAudio speaker")
for u, sv in (("https://legacy.sermonaudio.com/search.asp?SpeakerOnly=true&currSection=sermonsspeaker&keyword=Stephen_Davey", "sa_speaker.html"),
              ("https://legacy.sermonaudio.com/search.asp?SpeakerOnly=true&currSection=sermonsspeaker&keyword=Stephen_Davey&page=2", "sa_speaker2.html"),
              ("https://legacy.sermonaudio.com/sermonsource.asp?sourceid=wfth", "sa_source.html"),
              ("https://legacy.sermonaudio.com/rss_search.rss?keyword=Stephen+Davey&speakeronly=true", "sa_rss.xml"),
              ("https://web.sermonaudio.com/speakers/14913", "sa_web.html")):
    r = get(u, sv)
    if r is not None and r.ok:
        t = r.text
        print("   SIDs:", len(set(re.findall(r"[?&]SID=(\d+)", t, re.I))), "| totals:", re.findall(r"([\d,]{2,})\s*(?:sermons|Sermons|results|matches)", t)[:5],
              "| mp3:", re.findall(r'https?://[^"\'\s]+\.mp3', t)[:3], "| durations:", re.findall(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", t)[:10])
print("==== YouTube: Wisdom International UCenBoQiDkEqTjhyfa4TXR_g")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"], check=False)
base = "https://www.youtube.com/channel/UCenBoQiDkEqTjhyfa4TXR_g"
for tab in ("videos", "streams", "playlists"):
    p = subprocess.run(["yt-dlp", "--flat-playlist", "-J", f"{base}/{tab}"], capture_output=True, text=True)
    if p.returncode: print("  ", tab, "error", p.stderr[-200:]); continue
    j = json.loads(p.stdout); E = j.get("entries") or []
    json.dump([{k: e.get(k) for k in ("id", "title", "duration", "url")} for e in E], open(f"probe3/yt_{tab}.json", "w"))
    long_ = [e for e in E if (e.get("duration") or 0) >= 30*60]
    print(f"   {tab}: channel={j.get('channel')} entries={len(E)} >=30min={len(long_)} hours={sum((e.get('duration') or 0) for e in E)/3600:.0f}")
    for e in (long_ or E)[:20]: print("    -", e.get("title"), "|", round((e.get("duration") or 0)/60), "min")
