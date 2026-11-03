"""One SermonAudio sermon page (passage, description, length) and its mp3 headers. Honest user agent."""
import os, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
for sid in ("121720120476710", "12820120395232", "111620131875372"):
    r = requests.get(f"https://legacy.sermonaudio.com/sermoninfo.asp?SID={sid}", headers=H, timeout=60)
    print(sid, r.status_code, len(r.text)); open(f"probe3/sa_info_{sid}.html", "w").write(r.text)
    m = requests.get(f"https://mp3.sermonaudio.com/filearea/{sid}/{sid}.mp3", headers={**H, "Range": "bytes=0-1023"}, timeout=60, allow_redirects=True)
    print("   mp3", m.status_code, m.url, m.headers.get("content-type"), m.headers.get("content-range"), m.headers.get("access-control-allow-origin"))
