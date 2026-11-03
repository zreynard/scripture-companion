"""Philippians: how are lessons after the seventh named? A few name forms for lessons eight to sixty, one tiny request each."""
import requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)", "Range": "bytes=0-1"}
B = "https://wisdomonline-a.atl1.cdn.digitaloceanspaces.com/"
hits = []
for k in range(1, 61):
    for name in (f"{k:05d}Philippians.mp3.mp3", f"{k:05d}Philippians.mp3", f"{k:04d}Philippians.mp3.mp3", f"{k:05d}-Philippians.mp3.mp3", f"{k:05d}Phil.mp3.mp3",
                 f"Philippians{k:02d}.mp3", f"{k:05d}philippians.mp3.mp3"):
        r = requests.get(B + name, headers=H, timeout=30)
        if r.status_code in (200, 206): hits.append(name); break
print("hits:", hits)
