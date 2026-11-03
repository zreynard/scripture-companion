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
MINUTES = 14            # long enough for a story or a welcome before the text
READS = 0.45            # share of the passage's words he must say after announcing it (classify.py applies the same bar)
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


STOP = set("""that this with have from they them their there were what when which will would shall your unto upon into
then than also said says because about these those every before after again where while being been even only over
some such very just like more most must make made know come came going went shall yours ours ourselves""".split())
_BIBLE = {}


def words(t):
    return {w for w in re.findall(r"[a-z]+", t.lower()) if len(w) >= 4 and w not in STOP}


def passage_words(book, ch, v1=None, v2=None):
    """Distinctive words of the verses announced (or the opening verses of the chapter): the reading should contain them."""
    if book not in _BIBLE:
        p = os.path.join(HERE, "data", "bible", f"{book}.json")
        _BIBLE[book] = json.load(open(p, encoding="utf-8"))["chapters"] if os.path.exists(p) else []
    chs = _BIBLE[book]
    if not 1 <= ch <= len(chs): return set()
    vs = [x for x in chs[ch - 1] if v1 is None or v1 <= x["v"] <= (v2 or v1 + 5)][:6]
    return words(" ".join(x["t"] for x in vs))


def candidates(text):
    """Every passage he announces in the opening minutes, scored by how much of it he then reads aloud."""
    t = norm(text); out, seen = [], set()
    for m in CUE.finditer(t):
        win = t[m.start():m.end() + 90]
        for r in parse_refs(win):
            if r.whole_book or not r.chapters: continue
            ch = min(r.chapters)
            vm = re.search(r":(\d+)(?:\s*[-–]\s*(\d+))?", r.raw) if r.verse_level else None
            v1, v2 = (int(vm.group(1)), int(vm.group(2)) if vm.group(2) else None) if vm else (None, None)
            key = (r.book, ch, v1)
            if key in seen: continue
            seen.add(key)
            want = passage_words(r.book, ch, v1, v2)
            heard = words(t[m.end():m.end() + 3000])   # about the next three minutes
            score = round(len(want & heard) / len(want), 2) if len(want) >= 5 else 0.0
            ref = f"{r.book} {ch}" + (f":{v1}" + (f"-{v2}" if v2 else "") if v1 else "")
            out.append({"ref": ref, "score": score, "quote": t[max(0, m.start() - 40):m.end() + 110].strip()})
    return out


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
            and "score" not in done.get(e["id"], {}) and audio_of(e)]
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
        cands = candidates(text)
        best = max(cands, key=lambda c: c["score"], default=None)   # the passage he reads, not the first one he mentions
        ok = best if best and best["score"] >= READS else None
        done[e["id"]] = {"ref": ok["ref"] if ok else None, "score": best["score"] if best else 0, "quote": (best or {}).get("quote"),
                         "title": e["title"], "candidates": cands[:8]}
        if ok: found += 1
        print(f"  [{i}/{len(todo)}] {e['title'][:55]!r}: {ok['ref'] if ok else '-'}"
              + (f"  (read {best['score']:.0%}; also heard {', '.join(c['ref'] for c in cands if c is not best)[:80]})" if best else ""), flush=True)
        if i % 10 == 0: json.dump(done, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(done, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"announced passage heard in {found} of {len(todo)}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["merge"]: merge()
    elif len(a) == 2: main(int(a[0]), int(a[1]))
    else: main()
