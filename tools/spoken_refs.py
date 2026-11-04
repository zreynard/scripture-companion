"""The passage a sermon is on, as the preacher announces it ("turn with me to Acts chapter 1").

For David Platt sermons whose publisher listing names no passage (so they cannot stand on the road), listen to the
first minutes with speech recognition and keep a passage only when he announces it: a "turn to / open to / look at /
our text is ..." phrase followed by a book and chapter. Nothing is guessed from the topic.

    python tools/spoken_refs.py            -> data/spoken_refs.json  {entry id: {ref, quote, at}}
    python tools/spoken_refs.py K N        -> share K of N only, into data/spoken_refs.K.json
    python tools/spoken_refs.py merge      -> fold the shares into data/spoken_refs.json, then review
    python tools/spoken_refs.py review     -> hold back any placement that fails the checks below
Runs on GitHub's servers (needs ffmpeg and faster-whisper)."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from refs import parse_refs, merge_refs, refs_to_text  # noqa: E402

OUT = os.path.join(HERE, "data", "spoken_refs.json")
MINUTES = 20            # long enough for a story, a welcome or a long introduction before the text
V = 2                   # scoring version: entries heard with an older one are heard again
TEXT = os.path.join(HERE, "data", "spoken_text")   # what was heard, by entry id, so the checks can be re-run without the audio
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


def chapter(book, ch):
    if book not in _BIBLE:
        p = os.path.join(HERE, "data", "bible", f"{book}.json")
        _BIBLE[book] = json.load(open(p, encoding="utf-8"))["chapters"] if os.path.exists(p) else []
    chs = _BIBLE[book]
    return chs[ch - 1] if 1 <= ch <= len(chs) else []


def passage_words(book, ch, v1=None, v2=None):
    """Distinctive words of the verses announced (or the opening verses of the chapter): the reading should contain them."""
    vs = [x for x in chapter(book, ch) if v1 is None or v1 <= x["v"] <= (v2 or v1 + 5)][:6]
    return words(" ".join(x["t"] for x in vs))


def best_reading(book, ch, v1, v2, heard):
    """The five-verse stretch of the passage he reads most of (he may read a later part of the chapter, or start a few
    verses on): its first verse, its share of words heard, and how many words it has."""
    vs = chapter(book, ch)
    if v1: vs = [x for x in vs if v1 <= x["v"] <= (v2 or len(vs))] or vs
    best = (None, 0.0, 0)
    for i in range(max(1, len(vs) - 4)):
        w = words(" ".join(x["t"] for x in vs[i:i + 5]))
        if len(w) < 5: continue
        sc = len(w & heard) / len(w)
        if sc > best[1]: best = (vs[i]["v"], round(sc, 2), len(w))
    return best


def candidates(text):
    """Every passage he announces in the opening minutes, scored by how much of it he then reads aloud."""
    t = norm(text); out, seen = [], set()
    for m in CUE.finditer(t):
        e = m.end() + 90
        while e < len(t) and not t[e].isspace(): e += 1   # never cut a number in half ("Romans 8:2" of "8:28")
        win = t[m.start():e]
        for r in parse_refs(win):
            if r.whole_book or not r.chapters: continue
            ch = min(r.chapters)
            vm = re.search(r":(\d+)(?:\s*[-–]\s*(\d+))?", r.raw) if r.verse_level else None
            v1, v2 = (int(vm.group(1)), int(vm.group(2)) if vm.group(2) else None) if vm else (None, None)
            key = (r.book, ch, v1)
            if key in seen: continue
            seen.add(key)
            heard = words(t[m.end():m.end() + 6000])   # about the next six minutes
            at, score, n = best_reading(r.book, ch, v1, v2, heard)
            if v1: ref = f"{r.book} {ch}:{v1}" + (f"-{v2}" if v2 else "")
            else: ref = f"{r.book} {ch}" + (f":{at}" if at and at > 1 and score >= READS else "")   # where in the chapter he read
            out.append({"ref": ref, "score": score, "words": n, "quote": t[max(0, m.start() - 40):m.end() + 110].strip()})
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


def review():
    """Before a heard passage places a sermon: it must be a passage read, not a verse quoted (enough of its words); not
    contradict a book the title names; and not break a run of Sundays in another book (a series outlier). What fails is
    held back, with the reason, and the sermon stays in the Library only."""
    from datetime import datetime
    from email.utils import parsedate_to_datetime
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    rows = {e["id"]: e for e in (json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8"))}
    def day(i):
        try: return parsedate_to_datetime(rows[i]["published"]).date()
        except Exception: return None
    def heard(x):  # the best candidate, whether or not it was placed
        c = max(x.get("candidates") or [], key=lambda c: c["score"], default=None)
        return c if c and c["score"] >= READS else None
    book = lambda ref: re.match(r"(.+?) \d", ref).group(1)
    placed = {i: heard(x) for i, x in done.items() if heard(x) and i in rows}
    held = 0
    for i, c in placed.items():
        x, why = done[i], None
        m = re.match(r"(.+?) (\d+)(?::(\d+)(?:-(\d+))?)?$", c["ref"])
        b, ch = m.group(1), int(m.group(2))
        v1, v2 = (int(m.group(3)), int(m.group(4)) if m.group(4) else None) if m.group(3) else (None, None)
        if (c.get("words") if "words" in c else len(passage_words(b, ch, v1, v2))) < 12:
            why = "a verse quoted, not a passage read"
        named = [r.book for r in parse_refs(x.get("title", ""))]
        if not why and named and b not in named:
            why = f"the title names {named[0]}"
        d = day(i)
        if not why and d and not re.match(r"Chapter \d+", x.get("title", "")):
            near = [book(placed[j]["ref"]) for j in placed if j != i and day(j) and 0 < abs((day(j) - d).days) <= 21]
            top = max(set(near), key=near.count) if near else None
            if top and top != b and near.count(top) >= 3:
                why = f"the Sundays around it are a series in {top}"
        x["ref"] = None if why else c["ref"]; x["score"] = c["score"]
        if why: x["held"] = why; held += 1
        else: x.pop("held", None)
    json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(placed) - held} placed, {held} held back for review")


def merge():
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    import glob
    for p in sorted(glob.glob(os.path.join(HERE, "data", "spoken_refs.*.json"))):
        done.update(json.load(open(p, encoding="utf-8"))); os.remove(p)
    json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(done)} sermons listened to, {sum(1 for v in done.values() if v.get('ref'))} with an announced passage")
    review()


def main(k=0, n=1):
    from faster_whisper import WhisperModel
    rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = [e for e in rows if e.get("speaker") == "Platt" and e.get("track") == "sermon" and not e.get("refs")
            and done.get(e["id"], {}).get("v") != V and audio_of(e)]
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
        os.makedirs(TEXT, exist_ok=True)
        open(os.path.join(TEXT, f"{e['id']}.txt"), "w", encoding="utf-8").write(text)
        done[e["id"]] = {"v": V, "ref": ok["ref"] if ok else None, "score": best["score"] if best else 0, "quote": (best or {}).get("quote"),
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
    elif a[:1] == ["review"]: review()
    elif len(a) == 2: main(int(a[0]), int(a[1]))
    else: main()
