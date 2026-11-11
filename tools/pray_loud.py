"""How loud each Pray recording is where it is used: integrated loudness (LUFS, EBU R128) of the exact stretch of every
Be Led prayer, Meditate reading and the Lord's Prayer, decoded from the file's start so the times are true times.
Runs on GitHub Actions (needs ffmpeg). Reads out/site/index.html after a build; prints one line per stretch:
    LOUD {"k": "led|med|lp", "id": ..., "lu": -19.3, "peak": -2.1}
    python tools/pray_loud.py SHARD OF        (files are split across shards by their URL)
    python tools/pray_loud.py merge LOG...    (local: write "lu" into data/be_led.json, data/meditate.json, data/guided_lp.json)
"""
import hashlib, json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"

def lufs(path, t0, dur):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}",
                        "-af", "ebur128=framelog=quiet:peak=true", "-f", "null", "-"], capture_output=True, text=True, timeout=900)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr); pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)
    return (float(i[-1]) if i else None), (float(pk[-1]) if pk else None)

def length(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-f", "null", "-"], capture_output=True, text=True, timeout=900)   # stats on: the last time= is the decoded length
    t = re.findall(r"time=(\d+):(\d+):([\d.]+)", p.stderr)
    return int(t[-1][0]) * 3600 + int(t[-1][1]) * 60 + float(t[-1][2]) if t else None

def jobs():
    h = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(h[h.index("const D=") + 8:]); P = D["pray"]; out = []
    for x in P["led"]: out.append(("led", x["id"], x["audio"], ("end", x["sb"], x.get("e") or 0)))
    for x in P["med"]:
        if x.get("audio"): out.append(("med", f'{x["src"]}@{x["a"]}', x["audio"], ("abs", x["a"], x["b"])))
    if P.get("lp"): out.append(("lp", "lp", P["lp"]["audio"], ("abs", P["lp"]["a"], P["lp"]["b"])))
    return out

def run(shard, of):
    import requests
    by = {}
    kinds = set((os.environ.get("KINDS") or "led,med,lp").split(","))
    for j in jobs():
        if j[0] in kinds and int(hashlib.md5(j[2].encode()).hexdigest(), 16) % of == shard: by.setdefault(j[2], []).append(j)
    print(f"shard {shard}/{of}: {len(by)} files, {sum(len(v) for v in by.values())} stretches", flush=True)
    for url, js in by.items():
        if "buzzsprout" in url:
            for k, i, _, _ in js: print("LOUD " + json.dumps({"k": k, "id": i, "lu": None, "note": "buzzsprout refuses GitHub"}), flush=True)
            continue
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "a")
            try:
                with requests.get(url, headers={"User-Agent": UA}, timeout=900, stream=True) as r:
                    r.raise_for_status()
                    with open(f, "wb") as o:
                        for c in r.iter_content(1 << 20): o.write(c)
                L = None
                for k, i, _, sp in js:
                    if sp[0] == "end":
                        L = L or length(f); t0, t1 = L - sp[1], L - sp[2]
                    else: t0, t1 = sp[1], sp[2]
                    lu, pk = lufs(f, t0, t1 - t0)
                    print("LOUD " + json.dumps({"k": k, "id": i, "lu": lu, "peak": pk, "t0": round(t0, 2), "dur": round(t1 - t0, 2)}), flush=True)
            except Exception as ex:
                for k, i, _, _ in js: print("LOUD " + json.dumps({"k": k, "id": i, "lu": None, "note": str(ex)[:100]}), flush=True)

def merge(logs):
    got = {}
    for p in logs:
        for line in open(p, encoding="utf-8", errors="replace"):
            if "LOUD {" in line:
                x = json.loads(line[line.index("LOUD {") + 5:])
                if x.get("lu") is not None and x["lu"] > -70: got[(x["k"], x["id"])] = round(x["lu"], 1)
    n = 0
    p = os.path.join(HERE, "data", "be_led.json"); L = json.load(open(p, encoding="utf-8"))
    for x in L["prayers"]:
        k = ("led", "led:" + x["src"] + ("" if not x.get("n") else f":{x['n']}"))
        if k in got: x["lu"] = got[k]; n += 1
    json.dump(L, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    p = os.path.join(HERE, "data", "meditate.json"); M = json.load(open(p, encoding="utf-8"))
    for x in M["sayings"]:
        k = ("med", f'{x["src"]}@{x["a"]}')
        if k in got: x["lu"] = got[k]; n += 1
    json.dump(M, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    p = os.path.join(HERE, "data", "guided_lp.json"); G = json.load(open(p, encoding="utf-8"))
    if ("lp", "lp") in got: G["lu"] = got[("lp", "lp")]; n += 1
    json.dump(G, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{n} stretches given their loudness ({len(got)} measured)")

if __name__ == "__main__":
    if sys.argv[1] == "merge": merge(sys.argv[2:])
    else: run(int(sys.argv[1]), int(sys.argv[2]))
