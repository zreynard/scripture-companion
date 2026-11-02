"""Measure how loud each source is (integrated loudness, LUFS, EBU R128) from a sample of its episodes.
Runs on GitHub Actions (needs ffmpeg). Reads out/site/index.html after a build; writes loudness.json.
For each source: up to N episodes spread across the catalog; measures minutes 2-6 of each (past any intro)."""
import json, os, random, re, subprocess, sys, statistics
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = int(os.environ.get("N", "8"))

def lufs(url):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", "120", "-t", "240", "-user_agent", "Mozilla/5.0", "-i", url,
                        "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True, text=True, timeout=240)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)
    return (float(m[-1]) if m else None), (float(pk[-1]) if pk else None)

def main():
    h = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    i = h.index("const D=") + 8; D, _ = json.JSONDecoder().raw_decode(h[i:])
    cat = {}
    for line in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8"):
        e = json.loads(line); cat[e["id"]] = e.get("source")
    by = {}
    for it in D["items"].values():
        if it.get("audio") and (it.get("dur") or 0) > 400:
            by.setdefault(cat.get(it["id"]) or it.get("src") or "?", []).append(it)
    random.seed(7); out = {}
    for src, items in sorted(by.items()):
        pick = random.sample(items, min(N, len(items)))
        vals = []
        for it in pick:
            try: l, pk = lufs(it["audio"])
            except Exception as ex: l, pk = None, None
            vals.append({"t": it["t"][:60], "lufs": l, "peak": pk})
            print(f"{src:24} {str(l):>7} LUFS  {str(pk):>6} dBFS  {it['t'][:50]}", flush=True)
        good = [v["lufs"] for v in vals if v["lufs"] is not None]
        out[src] = {"n": len(good), "median": statistics.median(good) if good else None,
                    "min": min(good) if good else None, "max": max(good) if good else None, "items": len(items), "samples": vals}
    json.dump(out, open("loudness.json", "w"), indent=1)
    print("\nSUMMARY (median integrated loudness; podcast norm is about -16 to -19 LUFS)")
    for s, v in sorted(out.items(), key=lambda kv: -(kv[1]["median"] or -99)):
        print(f"  {s:24} median {v['median']} LUFS  range {v['min']}..{v['max']}  ({v['n']} measured of {v['items']})")

if __name__ == "__main__":
    main()
