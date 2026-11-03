"""Learn how Wisdom International names its sermon audio, from the one known file (Genesis01-Genesis1_1.mp3) and the lesson
numbers and passages its Genesis series page publishes: a few candidate names per lesson, each checked with one small request."""
import requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)", "Range": "bytes=0-1"}
B = "https://wisdomonline-a.atl1.cdn.digitaloceanspaces.com/"
L = [(1, "1:1"), (2, "1:1-23"), (3, "2:1-23"), (4, "2:23-25"), (5, "3:1-24"), (6, "4:1-25"), (7, "5:1-32"), (8, "6-9"), (12, "14"), (14, "22")]
def cands(n, ref):
    nn = f"{n:02d}"
    c, _, v = ref.partition(":"); a = ref.replace(":", "_")
    out = [f"Genesis{nn}-Genesis{a}", f"Genesis{nn}-Genesis{a.replace('-', '_')}", f"Genesis{nn}-Genesis{c}_{v.split('-')[0]}" if v else None,
           f"Genesis{nn}-Genesis{c.split('-')[0]}", f"Genesis{nn}-Genesis{c.split('-')[0]}_1", f"Genesis{nn}-Genesis{ref.replace(':', '_').replace('-', 'to')}",
           f"Genesis{nn}-Genesis_{a}", f"Genesis{nn}"]
    return [x for x in dict.fromkeys(out) if x]
for n, ref in L:
    hits = []
    for cnd in cands(n, ref):
        r = requests.get(B + cnd + ".mp3", headers=H, timeout=30)
        if r.status_code in (200, 206): hits.append(cnd)
    print(f"lesson {n} ({ref}): {hits or 'none of ' + str(len(cands(n, ref)))}", flush=True)
