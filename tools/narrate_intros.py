"""The Bible Narrative read aloud by Alistair: every book and chapter introduction in data/narrative/<abbr>.txt
(see data/narrative/STYLE.md), with the same voice, takes and speech check as the Bible reading (tools/narrate.py).

Each introduction becomes one mp3 and a small json (its length and a fingerprint of its text), kept as release assets
and copied to the narration-audio branch, which the app plays from. An introduction whose text has changed since it
was recorded is recorded again.

    python tools/narrate_intros.py plan SHARDS              matrix for the workflow
    python tools/narrate_intros.py run SHARD SHARDS [ONLY]  record this shard's introductions that are missing or out of date
    python tools/narrate_intros.py publish                  copy new mp3s to the audio branch, write data/narrative_audio.json
ONLY limits a run, e.g. "Gen:0,Gen:1" (0 = the book introduction).
"""
import glob, hashlib, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tools"))
from canon import BOOKS  # noqa: E402
import narrate as N  # noqa: E402  (the reader, the voice, the spoken forms of numbers)
from narrative_check import sections as read_sections  # noqa: E402

REPO = N.REPO
TAGS = [f"narrative-{i}" for i in range(1, 7)]   # a release holds at most 1000 files
OUT = os.path.join(HERE, "data", "narrative_audio.json")
PAUSE = {"piece": 0.32, "para": 0.85}


def fp(text): return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
def asset(a, c, ext): return f"intro_{a}_{c:03d}.{ext}"


def items():
    """Every introduction written so far: {"a", "c" (0 = book), "text", "h"} in Bible order."""
    out = []
    for name, abbr, n, _, _ in BOOKS:
        s, _, files = read_sections(abbr)
        if not files: continue
        for k in ["intro"] + [str(c) for c in range(1, n + 1)]:
            t = (s.get(k) or "").strip()
            if t: out.append({"a": abbr, "b": name, "c": 0 if k == "intro" else int(k), "text": t, "h": fp(t), "size": len(t)})
    return out


def release_files():
    out = {}
    for tag in TAGS:
        q = subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{tag}", "-q", ".id"], capture_output=True, text=True)
        rid = q.stdout.strip()
        if q.returncode or not rid.isdigit(): continue
        r = subprocess.run(["gh", "api", "--paginate", f"repos/{REPO}/releases/{rid}/assets?per_page=100", "-q", '.[]|"\\(.name) \\(.id)"'],
                           capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            n, i = line.split(); out.setdefault(n, (tag, int(i)))
    return out


def recorded():
    """{asset json name: its contents} for every introduction already made."""
    tmp = tempfile.mkdtemp()
    for tag in TAGS:
        subprocess.run(["gh", "release", "download", tag, "-R", REPO, "-p", "intro_*.json", "-D", tmp, "--clobber"], capture_output=True)
    return {os.path.basename(f): json.load(open(f)) for f in glob.glob(os.path.join(tmp, "intro_*.json"))}


_START = None


def first_open():
    """The first release with room (one API call), so uploads do not knock on full ones first."""
    global _START
    if _START is None:
        r = subprocess.run(["gh", "api", f"repos/{REPO}/releases?per_page=100", "-q", '.[]|"\\(.tag_name) \\(.assets|length)"'], capture_output=True, text=True)
        n = dict(l.split() for l in r.stdout.splitlines() if l.strip())
        _START = next((i for i, t in enumerate(TAGS) if int(n.get(t, 0)) < 990), 0)
    return _START


def upload(files):
    import time
    for tag in TAGS[first_open():]:
        for k in range(12):
            r = subprocess.run(["gh", "release", "upload", tag, *files, "--clobber", "-R", REPO], capture_output=True, text=True)
            if not r.returncode: return
            if "file_count limited" in r.stderr: break
            if "release not found" in r.stderr.lower():
                subprocess.run(["gh", "release", "create", tag, "-R", REPO, "--title", f"The Bible Narrative ({tag})",
                                "--notes", "Book and chapter introductions read by Alistair. Made by tools/narrate_intros.py."], capture_output=True)
                continue
            wait = 60 * (k + 1) if "rate limit" in r.stderr.lower() else 5 * (k + 1)   # GitHub asks us to slow down: wait it out
            print("  upload retry in", wait, "s:", r.stderr[:120], flush=True); time.sleep(wait)
        else:
            raise RuntimeError("upload failed")
    raise RuntimeError("every release is full")


def make(reader, x, outdir):
    import numpy as np, soundfile as sf
    sr = reader.sr
    gap = lambda s: np.zeros(int(sr * s), dtype=np.float32)
    audio, weak = [gap(0.25)], []
    for i, para in enumerate(p for p in re.split(r"\n\s*\n", x["text"]) if p.strip()):
        if i: audio.append(gap(PAUSE["para"]))
        for j, piece in enumerate(N.pieces(N.spoken(para), 260)):
            if j: audio.append(gap(PAUSE["piece"]))
            audio.append(reader.say(piece, weak).astype(np.float32))
    audio.append(gap(0.9))
    wav = np.concatenate(audio); d = round(len(wav) / sr, 2)
    w = os.path.join(outdir, asset(x["a"], x["c"], "wav")); mp3 = os.path.join(outdir, asset(x["a"], x["c"], "mp3"))
    sf.write(w, wav, sr)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", w, "-ac", "1", "-ar", "24000", "-af", "loudnorm=I=-17:TP=-1.5:LRA=11", "-b:a", "48k", mp3], check=True)
    os.remove(w)
    meta = {"a": x["a"], "c": x["c"], "d": d, "h": x["h"], "weak": weak}
    js = os.path.join(outdir, asset(x["a"], x["c"], "json")); json.dump(meta, open(js, "w"), separators=(",", ":"))
    return mp3, js, meta


def todo_list(only=""):
    xs = items()
    if only:
        want = {tuple(s.split(":")) for s in only.split(",") if s}
        xs = [x for x in xs if (x["a"], str(x["c"])) in want]
    # what is already recorded, from the record the app reads (no downloads, so no API calls)
    rec = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    return [x for x in xs if ((rec.get(x["a"]) or {}).get(str(x["c"])) or [None, None])[1] != x["h"]]


def run(k, shards, only=""):
    import time
    k, shards = int(k), int(shards)
    todo = todo_list(only)
    total = sum(x["size"] for x in todo) or 1; per = total / shards; acc = 0; mine = []
    for x in todo:
        if min(int(acc // per), shards - 1) == k: mine.append(x)
        acc += x["size"]
    print(f"shard {k}/{shards}: {len(mine)} introductions to record ({len(todo)} in all)", flush=True)
    if not mine: return
    reader = N.Reader(); out = tempfile.mkdtemp()
    for x in mine:
        t0 = time.time()
        mp3, js, meta = make(reader, x, out)
        upload([mp3, js]); os.remove(mp3)
        print(f'{x["b"]} {x["c"] or "introduction"}: {meta["d"] / 60:.1f} min in {(time.time() - t0) / 60:.1f} min; {len(meta["weak"])} weak pieces', flush=True)
        for w in meta["weak"]: print("   weak", w, flush=True)


def publish():
    """Copy every recorded mp3 not yet on the audio branch, then write the lengths the app needs."""
    url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{REPO}.git"
    d = tempfile.mkdtemp()
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1", "-b", N.AUDIO, url, d], check=True)
    N.git(d, "read-tree", "HEAD")
    have = set(N.git(d, "ls-tree", "--name-only", "HEAD").split())
    gid = ["-c", "user.name=github-actions[bot]", "-c", "user.email=41898+github-actions[bot]@users.noreply.github.com"]
    man = json.loads(N.git(d, "show", "HEAD:intro_manifest.json")) if "intro_manifest.json" in have else {}
    rel = release_files()
    todo = [(tag, n) for n, (tag, i) in sorted(rel.items()) if n.startswith("intro_") and n.endswith(".mp3") and (n not in have or man.get(n) != i)]
    print(f"{len(todo)} introductions to copy to the audio branch", flush=True)
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        for t, n in batch:
            subprocess.run(["gh", "release", "download", t, "-R", REPO, "-p", n, "-D", d, "--clobber"], check=True)
            N.git(d, "add", n); os.remove(os.path.join(d, n)); man[n] = rel[n][1]
        json.dump(man, open(os.path.join(d, "intro_manifest.json"), "w"), separators=(",", ":"), sort_keys=True)
        N.git(d, "add", "intro_manifest.json"); N.git(d, *gid, "commit", "-q", "-m", f"The Bible Narrative: {len(batch)} introductions")
        for k in range(4):
            if subprocess.run(["git", "-C", d, "push", "-q", "origin", f"HEAD:{N.AUDIO}"]).returncode == 0: break
            import time; time.sleep(10 * (k + 1))
        else: raise RuntimeError("push failed")
        have |= {n for _, n in batch}
    meta = recorded(); out = {}
    for n, m in meta.items():
        if n[:-5] + ".mp3" in have: out.setdefault(m["a"], {})[str(m["c"])] = [m["d"], m["h"]]
    json.dump(out, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
    print(f"{sum(len(v) for v in out.values())} introductions playable; {sum(x[0] for v in out.values() for x in v.values()) / 3600:.1f} hours")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "plan": print(json.dumps(list(range(int(sys.argv[2])))))
    elif cmd == "run": run(*sys.argv[2:])
    elif cmd == "publish": publish()
