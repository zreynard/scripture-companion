"""Length of every recording the app lists without one (data/durations.json {entry id: seconds}), read from each audio
file's header with ffprobe (a few kilobytes, not the whole file). Used where a feed gives no duration.
Runs on GitHub's servers:  python tools/durations.py"""
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
OUT = os.path.join(HERE, "data", "durations.json")

def probe(u):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-user_agent", UA, "-show_entries", "format=duration", "-of", "csv=p=0", u],
                           capture_output=True, text=True, timeout=90)
        return round(float(r.stdout.strip())) if r.stdout.strip() else None
    except Exception:
        return None

def main():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    have = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [i for i in D["items"].values() if not i.get("dur") and i.get("audio") and i["id"] not in have and not i["id"].startswith(("nar:", "int:"))]
    print(len(todo), "recordings without a length", flush=True)
    with ThreadPoolExecutor(12) as ex:
        for k, (i, d) in enumerate(zip(todo, ex.map(lambda i: probe(i["audio"]), todo)), 1):
            if d: have[i["id"]] = d
            if k % 100 == 0: print(f"  {k}/{len(todo)}", flush=True)
    json.dump(have, open(OUT, "w"), indent=0, sort_keys=True)
    print(len(have), "lengths known", flush=True)

if __name__ == "__main__":
    main()
