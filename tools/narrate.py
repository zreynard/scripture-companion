"""The whole Bible (BSB) read aloud by the narrator Alistair: Chatterbox Turbo, in the voice of a man who donated it
(Kyutai voice donations, CC0). Runs on GitHub's machines, many chapters at a time.

Each chapter becomes one mp3 (a release asset, so the site stays small) and a small timing file saying where every
verse starts, so the app can start at any verse and follow along. Every verse is made on its own, checked by
speech recognition, and made again if it came out wrong. The chapter opens with its name ("Genesis, chapter one."),
verse numbers are never read, and section headings (not part of the text) are left out.

    python tools/narrate.py plan SHARDS             matrix for the workflow (chapters split evenly by length)
    python tools/narrate.py run SHARD SHARDS [ONLY] make and upload the shard's chapters that are not uploaded yet
    python tools/narrate.py collect                 gather every chapter's timings into data/narration/<abbr>.json
    python tools/narrate.py publish                 copy new mp3s to the narration-audio branch, then collect those
ONLY limits a run to some chapters, e.g. "Gen:1,Psa:23".
"""
import difflib, glob, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from canon import BOOKS  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "zreynard/scripture-companion")
VOICE = ("kyutai/tts-voices", "voice-donations/gmaskell92_enhanced.wav")  # Alistair
TAG = lambda t: "narration-" + t.lower()  # one release per testament
OUTDIR = os.path.join(HERE, "data", "narration")
SEED = 5          # the seed of the sample that was chosen
PAUSE = {"verse": 0.45, "para": 0.8, "piece": 0.25, "title": 1.0}


# ---------- the words to be spoken ----------
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def words_for(n):
    """British style: 'two hundred and twelve', 'one thousand, two hundred'."""
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000: return ONES[n // 100] + " hundred" + (" and " + words_for(n % 100) if n % 100 else "")
    for size, name in ((10 ** 6, "million"), (1000, "thousand")):
        if n >= size:
            hi, lo = divmod(n, size)
            rest = "" if not lo else (" and " if lo < 100 else ", ") + words_for(lo)
            return words_for(hi) + " " + name + rest
    return str(n)


def spoken(t):
    t = t.replace("\n", " ").replace("[", "").replace("]", "").replace("…", "...")
    t = re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group(0).title(), t)          # LORD -> Lord, GOD -> God
    t = re.sub(r"\d[\d,]*\d|\d", lambda m: words_for(int(m.group(0).replace(",", ""))), t)
    return re.sub(r"\s+", " ", t).strip()


def say_book(name):
    return re.sub(r"^([123]) ", lambda m: ["First ", "Second ", "Third "][int(m.group(1)) - 1], name)


def title(name, c, chapters):
    if name == "Psalms": return f"Psalm {words_for(c)}."
    if chapters == 1: return f"{say_book(name)}."
    return f"{say_book(name)}, chapter {words_for(c)}."


def pieces(t, limit=300):
    """A verse longer than the model reads well is split at sentence ends, then at semicolons or commas."""
    if len(t) <= limit: return [t]
    out, cur = [], ""
    for p in re.split(r"(?<=[.!?;:”’])\s+", t):
        if len(p) > limit:  # one very long sentence: split at commas
            for q in re.split(r"(?<=,)\s+", p):
                if cur and len(cur) + len(q) > limit: out.append(cur); cur = q
                else: cur = (cur + " " + q).strip()
            continue
        if cur and len(cur) + len(p) > limit: out.append(cur); cur = p
        else: cur = (cur + " " + p).strip()
    if cur: out.append(cur)
    return out


# ---------- which chapters ----------
def chapters():
    out = []
    for name, abbr, n, testament, _ in BOOKS:
        b = json.load(open(os.path.join(HERE, "data", "bible", name + ".json"), encoding="utf-8"))
        for c, verses in enumerate(b["chapters"], 1):
            out.append({"book": name, "abbr": abbr, "c": c, "n": n, "t": testament, "verses": verses,
                        "size": sum(len(v["t"]) for v in verses) + 40})
    return out


def shard_of(chs, k, shards):
    total = sum(x["size"] for x in chs); per = total / shards
    run, out = 0, []
    for x in chs:
        if int(run // per) == k: out.append(x)
        run += x["size"]
    return out


def asset(x, ext): return f'{x["abbr"]}_{x["c"]:03d}.{ext}'


def release_files(t):
    """Every file in a testament's release (listed page by page: a release holds over a thousand)."""
    rid = subprocess.run(["gh", "api", f"repos/{REPO}/releases/tags/{TAG(t)}", "-q", ".id"], capture_output=True, text=True).stdout.strip()
    if not rid: return set()
    r = subprocess.run(["gh", "api", "--paginate", f"repos/{REPO}/releases/{rid}/assets?per_page=100", "-q", ".[].name"],
                       capture_output=True, text=True, check=True)
    return set(r.stdout.split())


def uploaded():
    return release_files("OT") | release_files("NT")


# ---------- making the audio ----------
def reference():
    from huggingface_hub import hf_hub_download
    ref = os.path.join(tempfile.gettempdir(), "alistair.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", hf_hub_download(*VOICE), "-t", "14", "-ac", "1", "-ar", "24000",
                    "-af", "loudnorm=I=-18:TP=-2", ref], check=True)  # exactly as for the chosen sample
    return ref


def letters(t):
    t = re.sub(r"\d[\d,]*", lambda m: words_for(int(m.group(0).replace(",", ""))) if m.group(0).replace(",", "").isdigit() else m.group(0), t)
    return re.sub(r"[^a-z]", "", t.lower())


class Reader:
    def __init__(self):
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        from faster_whisper import WhisperModel
        torch.set_num_threads(os.cpu_count() or 4)
        self.torch = torch
        self.tts = ChatterboxTurboTTS.from_pretrained(device="cpu")
        self.sr = self.tts.sr
        self.asr = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.ref = reference()
        self.fast = self._fast_ok()

    def _fast_ok(self):
        """Prepare the voice once instead of before every piece, if that gives exactly the same sound."""
        import numpy as np
        try:
            t = "In the beginning God created the heavens and the earth."
            self.torch.manual_seed(SEED); a = self.tts.generate(t, audio_prompt_path=self.ref).squeeze().cpu().numpy()
            self.torch.manual_seed(SEED); b = self.tts.generate(t).squeeze().cpu().numpy()   # uses the voice just prepared
            same = a.shape == b.shape and np.allclose(a, b, atol=1e-4)
            print("voice prepared once:", same, flush=True)
            return same
        except Exception as e:
            print("voice prepared once: no,", type(e).__name__, e, flush=True)
            return False

    def gen(self, text):
        return self.tts.generate(text) if self.fast else self.tts.generate(text, audio_prompt_path=self.ref)

    def heard(self, wav):
        import numpy as np, scipy.signal as ss
        x = ss.resample_poly(wav, 2, 3).astype(np.float32)  # 24 kHz -> 16 kHz
        segs, _ = self.asr.transcribe(x, beam_size=1, language="en", condition_on_previous_text=False)
        return " ".join(s.text for s in segs)

    def trim(self, wav):
        import numpy as np
        n = int(self.sr * 0.02)
        if len(wav) < n * 3: return wav
        e = np.sqrt(np.convolve(wav ** 2, np.ones(n) / n, "same"))
        on = np.flatnonzero(e > max(e.max() * 0.03, 1e-4))
        if not len(on): return wav
        a, b = max(0, on[0] - n * 2), min(len(wav), on[-1] + n * 4)
        return wav[a:b]

    def say(self, text, log):
        """Read one piece; check it by ear (speech recognition) and pace; try again up to twice; keep the best."""
        best = None
        want = letters(text)
        for k in range(3):
            self.torch.manual_seed(SEED + k)
            wav = self.trim(self.gen(text).squeeze().cpu().numpy())
            dur = len(wav) / self.sr
            got = letters(self.heard(wav))
            sim = difflib.SequenceMatcher(None, want, got, autojunk=False).ratio() if want else 1
            cps = len(text) / max(dur, 0.1)
            ok_pace = 7 <= cps <= 26 or len(text) < 15
            score = sim - (0 if ok_pace else 0.5)
            if best is None or score > best[0]: best = (score, wav, sim, cps, k)
            if sim >= (0.6 if len(want) < 25 else 0.72) and ok_pace: break
        if best[4] or best[0] < 0.72:
            log.append({"text": text[:80], "sim": round(best[2], 2), "cps": round(best[3], 1), "tries": k + 1})
        return best[1]


def make(reader, x, outdir):
    import numpy as np, soundfile as sf
    sr = reader.sr
    gap = lambda s: np.zeros(int(sr * s), dtype=np.float32)
    audio, t, marks, weak = [], 0.0, [], []
    def add(w):
        nonlocal t
        audio.append(w.astype(np.float32)); t += len(w) / sr
    add(gap(0.3))
    add(reader.say(title(x["book"], x["c"], x["n"]), weak))
    for i, v in enumerate(x["verses"]):
        add(gap(PAUSE["title"] if i == 0 else PAUSE["para"] if v.get("p") else PAUSE["verse"]))
        marks.append([v["v"], round(t, 2)])
        for j, p in enumerate(pieces(spoken(v["t"]))):
            if j: add(gap(PAUSE["piece"]))
            add(reader.say(p, weak))
    add(gap(1.2))
    wav = os.path.join(outdir, asset(x, "wav")); mp3 = os.path.join(outdir, asset(x, "mp3"))
    sf.write(wav, np.concatenate(audio), sr)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-ar", "24000",
                    "-af", "loudnorm=I=-17:TP=-1.5:LRA=11", "-b:a", "48k", mp3], check=True)
    os.remove(wav)
    meta = {"b": x["book"], "a": x["abbr"], "c": x["c"], "d": round(t, 2), "v": marks, "weak": weak}
    json.dump(meta, open(os.path.join(outdir, asset(x, "json")), "w"), separators=(",", ":"))
    return mp3, os.path.join(outdir, asset(x, "json")), meta


def upload(files, testament):
    for k in range(5):
        r = subprocess.run(["gh", "release", "upload", TAG(testament), *files, "--clobber", "-R", REPO], capture_output=True, text=True)
        if not r.returncode: return
        print("  upload retry", r.stderr[:200], flush=True)
        import time; time.sleep(5 * (k + 1))
    raise RuntimeError("upload failed")


def run(k, shards, only=""):
    import time
    chs = chapters()
    if only:
        want = {tuple(s.split(":")) for s in only.split(",")}
        todo = [x for x in chs if (x["abbr"], str(x["c"])) in want]
    else:
        todo = shard_of(chs, int(k), int(shards))
    have = uploaded()
    todo = [x for x in todo if asset(x, "mp3") not in have or asset(x, "json") not in have]
    print(f"shard {k}/{shards}: {len(todo)} chapters to make", flush=True)
    if not todo: return
    reader = Reader()
    out = tempfile.mkdtemp()
    for x in todo:
        t0 = time.time()
        mp3, js, meta = make(reader, x, out)
        upload([mp3, js], x["t"])
        print(f'{x["book"]} {x["c"]}: {meta["d"] / 60:.1f} min audio in {(time.time() - t0) / 60:.1f} min; '
              f'{len(meta["weak"])} weak pieces', flush=True)
        for w in meta["weak"]: print("   weak", w, flush=True)
        os.remove(mp3)


AUDIO = "narration-audio"  # branch the app plays from (raw.githubusercontent.com lets the app fetch it; releases do not)


def git(d, *a, **kw): return subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, text=True, **kw).stdout


def mirror():
    """Copy every chapter mp3 that is not yet on the audio branch from the releases. Without downloading what is
    already there: a clone with no file contents, then only the new files are added."""
    url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{REPO}.git"
    d = tempfile.mkdtemp()
    r = subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1", "-b", AUDIO, url, d],
                       capture_output=True, text=True)
    git_id = ["-c", "user.name=github-actions[bot]", "-c", "user.email=41898+github-actions[bot]@users.noreply.github.com"]
    if r.returncode:  # first time: start the branch
        git(d, "init", "-q", "-b", AUDIO)
        git(d, "remote", "add", "origin", url)
        open(os.path.join(d, "README.md"), "w").write("The Bible read aloud by Alistair, one mp3 per chapter. Made by tools/narrate.py on main.\n")
        git(d, "add", "README.md"); git(d, *git_id, "commit", "-q", "-m", "Narration audio")
        have = set()
    else:
        git(d, "read-tree", "HEAD")
        have = set(git(d, "ls-tree", "--name-only", "HEAD").split())
    todo = []
    for t in ("OT", "NT"):
        todo += [(t, n) for n in sorted(release_files(t)) if n.endswith(".mp3") and n not in have]
    print(f"{len(have & {n for n in have if n.endswith('.mp3')})} chapters on the audio branch, {len(todo)} to add", flush=True)
    for i in range(0, len(todo), 80):
        batch = todo[i:i + 80]
        for t, n in batch:
            subprocess.run(["gh", "release", "download", TAG(t), "-R", REPO, "-p", n, "-D", d, "--clobber"], check=True)
            git(d, "add", n); os.remove(os.path.join(d, n))
        git(d, *git_id, "commit", "-q", "-m", f"Narration audio: {len(batch)} chapters")
        for k in range(4):
            if subprocess.run(["git", "-C", d, "push", "-q", "origin", f"HEAD:{AUDIO}"]).returncode == 0: break
            import time; time.sleep(10 * (k + 1))
        else: raise RuntimeError("push failed")
        have |= {n for _, n in batch}
        print(f"  added {len(batch)}", flush=True)
    return have


def collect(playable=None):
    """Timings for every chapter; with playable, only the chapters whose audio the app can already fetch."""
    tmp = tempfile.mkdtemp()
    for t in ("OT", "NT"):
        subprocess.run(["gh", "release", "download", TAG(t), "-R", REPO, "-p", "*.json", "-D", tmp, "--clobber"], check=False)
    books = {}
    for f in sorted(glob.glob(os.path.join(tmp, "*.json"))):
        m = json.load(open(f))
        if playable is not None and os.path.basename(f)[:-5] + ".mp3" not in playable: continue
        books.setdefault(m["a"], {"b": m["b"], "tag": TAG("OT" if any(b[1] == m["a"] and b[3] == "OT" for b in BOOKS) else "NT"), "c": {}})
        books[m["a"]]["c"][str(m["c"])] = {"d": m["d"], "v": m["v"]}
    os.makedirs(OUTDIR, exist_ok=True)
    for f in glob.glob(os.path.join(OUTDIR, "*.json")): os.remove(f)
    for a, b in books.items():
        json.dump(b, open(os.path.join(OUTDIR, a + ".json"), "w"), separators=(",", ":"))
    n = sum(len(b["c"]) for b in books.values())
    print(f"{n} chapters in {len(books)} books; {sum(c['d'] for b in books.values() for c in b['c'].values()) / 3600:.1f} hours")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "plan": print(json.dumps(list(range(int(sys.argv[2])))))
    elif cmd == "run": run(*sys.argv[2:])
    elif cmd == "collect": collect()
    elif cmd == "publish": collect(mirror())
