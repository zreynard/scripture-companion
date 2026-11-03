"""Where the teaching starts in each Wisdom Journey episode, found by listening to its opening.

Buzzsprout plays a message from the ministry at the start of every episode ("It's time to be planning your year-end
giving ... Now here's Stephen"); it can change at any time and its length moves everything after it. So for each
episode: transcribe the first 90 s with word times, pass the message ("... here's Stephen"), the music, and a
co-host's greeting ("Hello, and thank you for joining us ... a lesson called ..."), and start at the first word after.
At the end: the last "Amen" in the final minutes; the app stops there (counted back from the file's end).

    SOURCE=davey_journey python tools/intro_speech.py all     -> data/intro_skip/<source>.json (+ _opening.json)
    SOURCE=davey_journey python tools/intro_speech.py check   -> prints "changed" if the opening message differs
    SOURCE=davey_journey python tools/intro_speech.py daily   -> all if the message changed, else only new episodes
Runs on GitHub's servers (ffmpeg + faster-whisper). Plain requests under the app's own name; a refusal is left alone."""
import json, os, re, subprocess, sys, tempfile, wave
import numpy as np
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
SOURCE = os.environ.get("SOURCE", "davey_journey")
OUT = os.path.join(HERE, "data", "intro_skip", f"{SOURCE}.json")
OPEN = os.path.join(HERE, "data", "intro_skip", f"{SOURCE}_opening.json")
END = os.path.join(HERE, "data", "intro_skip", f"{SOURCE}_end.json")   # {id: seconds before the file's end to stop}
TAIL = 150  # seconds of the end to listen to
SECS = 90
HANDOFF = re.compile(r"here'?s\s*$", re.I)          # "... Now here's" + "Stephen"
GREET = re.compile(r"thank(s| you) for joining|welcome (back )?to (the )?wisdom journey|wisdom journey with stephen|"
                   r"lesson (is )?(called|titled|entitled)|today'?s lesson is|stephen (returns|continues|takes (us|you)|is back|brings|walks|leads)|"
                   r"stephen dav[a-z]* is (taking|teaching|walking)|66 books|over three years|this is the wisdom journey|"
                   r"on (today'?s|this) (episode|wisdom journey)|glad you'?ve joined us|joining us (today|again)", re.I)
_model = None


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _model


def opening(url):
    """Words of the first SECS seconds: [(start, end, word, segment index)], or None if the audio would not load."""
    with tempfile.TemporaryDirectory() as d:
        mp3, wav = os.path.join(d, "a.mp3"), os.path.join(d, "a.wav")
        try:
            r = requests.get(url, headers=H, timeout=90, stream=True)
            if r.status_code not in (200, 206): print("  refused", r.status_code, flush=True); return None
            with open(mp3, "wb") as f:
                got = 0
                for chunk in r.iter_content(65536):
                    f.write(chunk); got += len(chunk)
                    if got > 3_000_000: break
            r.close()
        except requests.RequestException as x:
            print("  ", type(x).__name__, flush=True); return None
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", str(SECS), "-i", mp3, "-ac", "1", "-ar", "16000", wav], check=False)
        if not os.path.exists(wav): return None
        with wave.open(wav) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return words_of(pcm)


def words_of(pcm):
    segs, _ = model().transcribe(pcm, beam_size=1, language="en", vad_filter=True, word_timestamps=True,
                                 condition_on_previous_text=False)
    return [(w.start, w.end, w.word.strip(), k) for k, s in enumerate(segs) for w in (s.words or [])]


def ending(url):
    """Seconds between the teaching's last word ("Amen") and the end of the file, or None."""
    with tempfile.TemporaryDirectory() as d:
        mp3, wav = os.path.join(d, "a.mp3"), os.path.join(d, "a.wav")
        try:
            r = requests.get(url, headers={**H, "Range": "bytes=-2500000"}, timeout=120, stream=True)
            if r.status_code not in (200, 206): return None
            keep = bytearray()
            for chunk in r.iter_content(262144):
                keep += chunk
                if len(keep) > 5_000_000: del keep[:-2_500_000]   # a server that sends the whole file: keep its end
            r.close()
            open(mp3, "wb").write(bytes(keep[-2_500_000:]))
        except requests.RequestException:
            return None
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ac", "1", "-ar", "16000", wav], check=False)
        if not os.path.exists(wav): return None
        with wave.open(wav) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    pcm = pcm[-TAIL * 16000:]
    L = len(pcm) / 16000
    ws = words_of(pcm)
    amens = [w for w in ws if re.fullmatch(r"amen[.!,]?", w[2], re.I)]
    if not amens: return None
    left = L - amens[-1][1]
    if os.environ.get("N"):  # trial: show what the cut would leave out
        print("      before:", " ".join(w[2] for w in ws if w[1] <= amens[-1][1])[-160:], flush=True)
        print("      after: ", " ".join(w[2] for w in ws if w[0] > amens[-1][1])[:400], flush=True)
    return round(left - 0.6, 1) if 3 < left < 120 else None


def teaching_start(words):
    """Seconds where the teaching begins, and the ministry message's wording (to notice when it changes)."""
    i, msg = 0, ""
    for j in range(len(words) - 1):
        if words[j][0] > 75: break
        if re.fullmatch(r"stephen[.,!]?", words[j + 1][2], re.I) and HANDOFF.search(" ".join(w[2] for w in words[max(0, j - 1):j + 1])):
            i, msg = j + 2, " ".join(w[2] for w in words[:j + 2]); break
    # a co-host's greeting before the lesson: pass whole sentences of it
    while i < len(words):
        seg = words[i][3]
        text = " ".join(w[2] for w in words if w[3] == seg)
        if words[i][0] > 80 or not GREET.search(text): break
        while i < len(words) and words[i][3] == seg: i += 1
    if i >= len(words): return None, msg
    return max(0.0, round(words[i][0] - 0.4, 1)), msg


def episodes():
    rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    return sorted([e for e in rows if e["source"] == SOURCE and (e.get("audio_override") or "").endswith(".mp3")],
                  key=lambda e: e.get("published") or "", reverse=True)


def norm(t): return re.sub(r"[^a-z]+", " ", t.lower()).strip()


def daily():
    """Re-measure everything when the opening message has changed; otherwise only episodes not measured yet."""
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): check()
    print(buf.getvalue(), end="")
    import datetime
    weekly = datetime.date.today().weekday() == 6   # Sundays: re-measure everything anyway (the ending can change too)
    run_all(only_new=not (weekly or buf.getvalue().rstrip().endswith("changed")))


def check():
    old = json.load(open(OPEN)) if os.path.exists(OPEN) else {}
    for e in episodes()[:: 97][:2]:
        w = opening(e["audio_override"])
        if w is None: continue
        _, msg = teaching_start(w)
        same = norm(msg) == norm(old.get("message", ""))
        print(f"{e['title'][:60]}: opening message {'unchanged' if same else 'CHANGED'}: {msg[:140]!r}", flush=True)
        if not same:
            print("changed"); return
    print("unchanged")


def run_all(only_new=False):
    skips = json.load(open(OUT)) if os.path.exists(OUT) else {}
    ends = json.load(open(END)) if os.path.exists(END) else {}
    msgs = {}  # message wording -> how many episodes carry it
    eps = [e for e in episodes() if not (only_new and e["id"] in skips)][:int(os.environ.get("N") or 10**6)]
    if os.environ.get("N"): skips, ends = {}, {}  # a trial: write only what it measured
    for n, e in enumerate(eps, 1):
        w = opening(e["audio_override"])
        if w is None: continue
        s, msg = teaching_start(w)
        if s is None: continue
        skips[e["id"]] = s
        if msg: msgs[msg] = msgs.get(msg, 0) + 1
        nxt = " ".join(x[2] for x in w if x[0] >= s)[:60]
        t = ending(e["audio_override"])
        if t: ends[e["id"]] = t
        else: ends.pop(e["id"], None)
        print(f"[{n}/{len(eps)}] {s:5.1f}s  end -{t or 0:4.1f}s  {e['title'][:44]!r}  -> {nxt!r}", flush=True)
        if n % 25 == 0:
            json.dump(skips, open(OUT, "w"), indent=0, sort_keys=True); json.dump(ends, open(END, "w"), indent=0, sort_keys=True)
    json.dump(skips, open(OUT, "w"), indent=0, sort_keys=True); json.dump(ends, open(END, "w"), indent=0, sort_keys=True)
    top = max(msgs, key=msgs.get, default="")
    if not only_new: json.dump({"message": top}, open(OPEN, "w"), indent=1, ensure_ascii=False)
    print(f"done: {len(skips)} episodes; opening message: {top[:160]!r}")


if __name__ == "__main__":
    {"all": run_all, "check": check, "daily": daily}[sys.argv[1]]()
