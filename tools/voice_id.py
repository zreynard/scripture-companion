"""Who is preaching? Harvest Church Memphis posts many Sunday sermons without the preacher's name. Kennon Vaughan's
own sermons (named in the feed) give his voice; the other named preachers give theirs. Each recording is heard for
three minutes from the middle of the sermon and turned into a voice print (ECAPA, speechbrain); an unnamed sermon is
his only when it is clearly closer to him than to anyone else, by a margin set so that no named sermon is misjudged.

    python tools/voice_id.py embed K N   -> voice/<K>.json      (voice prints for every K-th of N recordings)
    python tools/voice_id.py report      -> data/vaughan_voice.json and voice/report.txt
Runs on GitHub's servers (ffmpeg, torch, speechbrain). Polite: one request at a time, a small range of each file."""
import glob, html, json, os, re, subprocess, sys, time
import xml.etree.ElementTree as ET
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import config  # noqa: E402

H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
IT = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
OUT = os.path.join(HERE, "voice")
# a preacher named in the title: "(Ronnie Stevens)", "- Seth Jewell", "Julius James - Matthew 6"
NAMED = re.compile(r"\(([A-Z][a-z]+(?: [A-Z][a-z\-]+)+) ?\)|[-–] ?([A-Z][a-z]+(?: [A-Z][a-z\-]+)+)\s*$|^([A-Z][a-z]+ [A-Z][a-z]+) -|\) ([A-Z][a-z]+ [A-Z][a-z]+)$")
NOT_NAME = re.compile(r"^(Easter|Palm|Mother|Father|Family|Advent|Christmas|Prayer|The |God |Respectable|Begin|Sermon|Going|Kingdom)")


def secs(d):
    d = (d or "").strip()
    if d.isdigit(): return int(d)
    p = [int(x) for x in d.split(":") if x.isdigit()]
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))


def feed():
    r = requests.get(config.HARVEST_MEMPHIS_FEED, headers=H, timeout=90); r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).find("channel").findall("item"):
        t = (it.findtext("title") or "").strip(); a = (it.findtext(IT + "author") or "").strip()
        d = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
        enc = it.find("enclosure"); url = html.unescape(enc.get("url")) if enc is not None else ""
        if not url: continue
        if re.search(r"\bkennon\b|\bvuaghan\b", t + " " + a, re.I): who = "Kennon Vaughan"
        elif a and a != "Harvest Church": who = a
        else:
            m = NAMED.search(t); g = next((x for x in (m.groups() if m else ()) if x), None)
            who = g.strip() if g and not NOT_NAME.match(g) else ""
        out.append({"url": url, "t": t, "date": (it.findtext("pubDate") or "")[5:16], "dur": secs(it.findtext(IT + "duration")), "who": who})
    return out


def clip(url, dur):
    """Three minutes of speech from the middle of the sermon (16 kHz mono), from a byte range of the file."""
    try:
        n = int(requests.head(url, headers=H, timeout=60, allow_redirects=True).headers.get("content-length") or 0)
    except Exception: n = 0
    if not n or not dur: return None
    at = min(max(0.3 * dur, 300), dur - 240)
    a, b = int(n * at / dur), int(n * (at + 190) / dur)
    for k in range(3):
        try:
            r = requests.get(url, headers={**H, "Range": f"bytes={a}-{b}"}, timeout=120, allow_redirects=True)
            if r.status_code in (200, 206) and len(r.content) > 100_000: break
        except Exception: pass
        time.sleep(5 * (k + 1))
    else: return None
    pcm = subprocess.run(["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         input=r.content, capture_output=True).stdout
    return pcm


def embed(k, n):
    import numpy as np, torch
    from speechbrain.inference.speaker import EncoderClassifier
    spk = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir="/tmp/ecapa")
    rows = feed()[k::n]; os.makedirs(OUT, exist_ok=True); res = []
    for x, it in enumerate(rows, 1):
        pcm = clip(it["url"], it["dur"]); time.sleep(1)
        if not pcm or len(pcm) < 16000 * 2 * 60:
            print(f"[{x}/{len(rows)}] no audio  {it['t'][:60]}", flush=True); continue
        w = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
        segs = [w[i:i + 16000 * 20] for i in range(0, len(w) - 16000 * 20, 16000 * 30)][:6]   # six 20-second windows
        with torch.no_grad():
            E = [torch.nn.functional.normalize(spk.encode_batch(torch.tensor(s)[None]).squeeze(), dim=0) for s in segs]
        e = torch.nn.functional.normalize(torch.stack(E).mean(0), dim=0)
        res.append({**it, "emb": [round(float(v), 5) for v in e]})
        print(f"[{x}/{len(rows)}] {it['who'] or '?':18s} {it['t'][:60]}", flush=True)
    json.dump(res, open(os.path.join(OUT, f"{k}.json"), "w"))


def report():
    import numpy as np
    R = [r for f in glob.glob(os.path.join(OUT, "*.json")) for r in json.load(open(f))]
    E = {r["url"]: np.array(r["emb"]) for r in R}
    K = [r for r in R if r["who"] == "Kennon Vaughan"]
    others = {}
    for r in R:
        if r["who"] and r["who"] != "Kennon Vaughan": others.setdefault(r["who"], []).append(r)
    def cent(rows, skip=None):
        v = [E[r["url"]] for r in rows if r["url"] != skip]
        if not v: return None
        c = np.mean(v, 0); return c / np.linalg.norm(c)
    def scores(url):
        ck = cent(K, url); s_k = float(E[url] @ ck)
        s_o = max((float(E[url] @ c), w) for w, rows in others.items() if (c := cent(rows, url)) is not None)
        return s_k, s_o
    # calibrate on the named sermons: the margin over the nearest other preacher that never misjudges one
    lab = [(r, *scores(r["url"])) for r in R if r["who"]]
    neg = sorted((sk - so[0], r["t"], r["who"]) for r, sk, so in lab if r["who"] != "Kennon Vaughan")
    pos = sorted((sk - so[0], r["t"]) for r, sk, so in lab if r["who"] == "Kennon Vaughan")
    margin = max(0.05, (neg[-1][0] if neg else 0) + 0.03)
    lines = [f"named: Kennon {len(K)}, others {sum(len(v) for v in others.values())} ({len(others)} preachers); unnamed {sum(1 for r in R if not r['who'])}",
             f"others' best margin toward Kennon: {neg[-3:] if neg else None}", f"Kennon's weakest margins: {pos[:3]}",
             f"rule: Kennon when his similarity beats the nearest other preacher by more than {margin:.3f}",
             f"named Kennon sermons the rule would miss: {sum(1 for m, _ in pos if m <= margin)} of {len(pos)}", ""]
    out = {}
    for r in sorted((r for r in R if not r["who"]), key=lambda r: r["date"][-4:] + r["date"]):
        sk, (so, w) = scores(r["url"]); m = sk - so
        verdict = "Kennon" if m > margin else ("unsure" if m > margin - 0.08 else w)
        out[r["url"]] = {"t": r["t"], "date": r["date"], "dur": r["dur"], "kennon": round(sk, 3), "other": round(so, 3), "nearest": w, "verdict": verdict}
        lines.append(f"{verdict:16s} {m:+.3f}  K {sk:.3f}  {w[:16]:16s} {so:.3f}  {r['date']}  {r['t'][:70]}")
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    json.dump({"margin": margin, "items": out}, open(os.path.join(HERE, "data", "vaughan_voice.json"), "w"), indent=1)
    open(os.path.join(OUT, "report.txt"), "w").write("\n".join(lines)); print("\n".join(lines))


if __name__ == "__main__":
    if sys.argv[1] == "embed": embed(int(sys.argv[2]), int(sys.argv[3]))
    else: report()
