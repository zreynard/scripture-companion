"""Wisdom's file names for sermons spanning chapters: candidates built from the passage in each sermon's own title."""
import requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)", "Range": "bytes=0-1"}
B = "https://wisdomonline-a.atl1.cdn.digitaloceanspaces.com/"
L = [(8, "6:1-9:17", "6-9"), (9, "9:20-11:25", "9-11"), (10, "12:1-3", "12:1-3"), (11, "12-14:4", "12-13"), (12, "13-19", "13-19"), (13, "14", "14"),
     (14, "15-18", "15-18"), (15, "22", "22"), (16, "23-25:21", "24"), (20, "33-36", "33-36"), (22, "38-39", "38-39"), (30, "46-50", "46-50")]
def cands(n, t, r):
    nn = f"{n:02d}"; out = []
    for p in (t, r):
        a = p.replace(":", "_")
        out += [a, a.replace("-", "_"), a.replace("-", "-Genesis"), p.split("-")[0].replace(":", "_"), p.split(":")[0].split("-")[0], a.replace(" ", "")]
    return [f"Genesis{nn}-Genesis{x}" for x in dict.fromkeys(out)] + [f"Genesis{nn}-Genesis{t.split(':')[0].split('-')[0]}_1"]
for n, t, r in L:
    hits = [c for c in cands(n, t, r) if requests.get(B + c + ".mp3", headers=H, timeout=30).status_code in (200, 206)]
    print(f"lesson {n} ({t} / {r}): {hits or 'none'}", flush=True)
