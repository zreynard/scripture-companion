"""The passage a sermon is on, as the preacher announces it ("turn with me to Acts chapter 1").

For David Platt sermons whose publisher listing names no passage (so they cannot stand on the road), listen to the
first minutes with speech recognition and keep a passage only when he announces it: a "turn to / open to / look at /
our text is ..." phrase followed by a book and chapter. Nothing is guessed from the topic.

    python tools/spoken_refs.py            -> data/spoken_refs.json  {entry id: {ref, quote, at}}
    python tools/spoken_refs.py K N        -> share K of N only, into data/spoken_refs.K.json
    python tools/spoken_refs.py merge      -> fold the shares into data/spoken_refs.json
Runs on GitHub's servers (needs ffmpeg and faster-whisper)."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from refs import parse_refs, merge_refs, refs_to_text  # noqa: E402

OUT = os.path.join(HERE, "data", "spoken_refs.json")
MINUTES = 9
UA = "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"
CUE = re.compile(r"\b(?:turn(?:ing)?|open(?:ing)?|look(?:ing)?|find|go|join me|read(?:ing)?|we(?:'re| are) in|our (?:text|passage)|the (?:text|passage)|"
                 r"in your bibles?|in our (?:study|journey) (?:of|through)|today in|this morning in|tonight in)\b", re.I)
ORD = {"first": "1", "second": "2", "third": "3", "1st": "1", "2nd": "2", "3rd": "3"}


def audio_of(e):
    u = e.get("audio_override") or e.get("url") or ""
    if re.search(r"\.(mp3|mp4|m4a)(\?|$)", u): return u
    m = re.search(r"buzzsprout\.com/(\d+)/(?:episodes/)?(\d+)", u)
    return f"https://www.buzzsprout.com/{m.group(1)}/{m.group(2)}.mp3" if m else None


def norm(t):
    """Speech-recognition wording to Bible-reference wording."""
    t = re.sub(r"\b(first|second|third|1st|2nd|3rd)\s+(Samuel|Kings|Chronicles|Corinthians|Thessalonians|Timothy|Peter|John)\b",
               lambda m: ORD[m.group(1).lower()] + " " + m.group(2), t, flags=re.I)
    t = re.sub(r"\bchapters?\s+(\d+)", r"\1", t, flags=re.I)
    t = re.sub(r"\b(\d+)[,.]?\s+(?:starting (?:in|at|with) )?verses?\s+(\d+)(?:\s*(?:through|to|-|and)\s*(\d+))?",
               lambda m: f"{m.group(1)}:{m.group(2)}" + (f"-{m.group(3)}" if m.group(3) else ""), t, flags=re.I)
    return t


def announced(text):
    """The first book-and-chapter that follows an announcing phrase, with the words around it."""
    t = norm(text)
    for m in CUE.finditer(t):
        win = t[m.start():m.end() + 90]
        refs = merge_refs(parse_refs(win))
        txt = refs_to_text(refs)
        if refs and re.search(r"\d", txt):  # a chapter, not just a book name
            return txt, t[max(0, m.start() - 40):m.end() + 110].strip()
    return None, None


def merge():
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    import glob
    for p in sorted(glob.glob(os.path.join(HERE, "data", "spoken_refs.*.json"))):
        done.update(json.load(open(p, encoding="utf-8"))); os.remove(p)
    json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(done)} sermons listened to, {sum(1 for v in done.values() if v.get('ref'))} with an announced passage")


def main(k=0, n=1):
    from faster_whisper import WhisperModel
    rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = [e for e in rows if e.get("speaker") == "Platt" and e.get("track") == "sermon" and not e.get("refs")
            and e["id"] not in done and audio_of(e)]
    todo = todo[k::n]
    out = OUT if n == 1 else os.path.join(HERE, "data", f"spoken_refs.{k}.json")
    if n > 1: done = {}
    print(f"{len(todo)} Platt sermons with no stated passage to listen to", flush=True)
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    tmp = tempfile.mkdtemp()
    found = 0
    for i, e in enumerate(todo, 1):
        wav = os.path.join(tmp, "a.wav")
        if os.path.exists(wav): os.remove(wav)
        try:
            r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-user_agent", UA, "-t", str(MINUTES * 60), "-i", audio_of(e),
                                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav], capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            print(f"  {e['title'][:60]}: audio timed out", flush=True); continue
        if r.returncode or not os.path.exists(wav) or os.path.getsize(wav) < 100000:
            print(f"  {e['title'][:60]}: audio did not load ({r.stderr[:100]})", flush=True); continue
        try:
            import wave, numpy as np   # read the samples here: faster-whisper's own file reader breaks on newer PyAV releases
            with wave.open(wav) as w: pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            segs, _ = model.transcribe(pcm, beam_size=1, language="en", vad_filter=True, condition_on_previous_text=False)
            text, at = "", {}
            for s in segs:
                at[len(text)] = s.start; text += s.text + " "
        except Exception as x:
            print(f"  {e['title'][:60]}: could not transcribe ({str(x)[:80]})", flush=True); continue
        ref, quote = announced(text)
        done[e["id"]] = {"ref": ref, "quote": quote, "title": e["title"]}
        if ref: found += 1
        print(f"  [{i}/{len(todo)}] {e['title'][:55]!r}: {ref or '-'}" + (f"   <- \"{quote[:120]}\"" if quote else ""), flush=True)
        if i % 10 == 0: json.dump(done, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(done, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"announced passage heard in {found} of {len(todo)}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["merge"]: merge()
    elif len(a) == 2: main(int(a[0]), int(a[1]))
    else: main()
