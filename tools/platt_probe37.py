"""Every audio file Radical's site uploaded from February 2019 to January 2020 (its public media list), to find The Story
of Scripture parts still missing (9: Why We Need Leviticus; 22: Are You Willing to Fully Commit Your Life to Jesus?), and
a playback check (status, length) of the parts found. Honest user agent. Saves probe3/radical_audio_2019.json."""
import json, os, subprocess, time, html, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
allm = []
for page in range(1, 20):
    r = requests.get("https://radical.net/wp-json/wp/v2/media", headers=H, timeout=90,
                     params={"media_type": "audio", "after": "2019-01-25T00:00:00", "before": "2020-01-31T00:00:00", "per_page": 100, "page": page, "orderby": "date", "order": "asc"})
    if not r.ok: print("page", page, r.status_code); break
    js = r.json()
    allm += [{"title": html.unescape(m["title"]["rendered"]), "date": m["date"], "url": m["source_url"], "len": (m.get("media_details") or {}).get("length")} for m in js]
    if len(js) < 100: break
    time.sleep(1)
print(len(allm), "audio files")
for m in allm: print(" ", m["date"][:10], m["len"], m["title"][:70], "|", m["url"].split("/")[-1][:70])
FOUND = ["https://cdn.radical.net/images/20190224191450/ABRAHAM-THE-PROMISES-OF-GOD.mp3",
         "https://cdn.radical.net/images/20190510095311/http___link.theplatform.com_s_IfSiAC_GpdCmru_qdYUmetafilefalse.mp3",
         "https://cdn.radical.net/images/20190719101325/TheBlessingOfAFaithfulFather.mp3",
         "https://cdn.radical.net/images/20190722083244/Should-We-Give-Up-on-the-Church.mp3",
         "https://cdn.radical.net/images/20190719103056/TheBlessingOfAFaithfulFather1.mp3"]
print("== playback")
for u in FOUND:
    r = requests.get(u, headers={**H, "Range": "bytes=0-1023"}, timeout=60)
    p = subprocess.run(["ffprobe", "-v", "error", "-user_agent", H["User-Agent"], "-show_entries", "format=duration", "-of", "csv=p=0", u], capture_output=True, text=True, timeout=120)
    print(" ", r.status_code, r.headers.get("content-type"), r.headers.get("access-control-allow-origin"), p.stdout.strip(), u.split("/")[-1])
json.dump(allm, open("probe3/radical_audio_2019.json", "w"), indent=1)
