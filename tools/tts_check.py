"""Transcribe each narrator sample and compare with the passage, to catch skipped, repeated or garbled words."""
import difflib, glob, json, os, re, sys
from faster_whisper import WhisperModel
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(HERE, "data", "bible", "Luke.json"), encoding="utf-8"))
ref = " ".join(v["t"] for v in d["chapters"][14][10:24])
words = lambda t: re.findall(r"[a-z']+", t.lower().replace("’", "'"))
R = words(ref)
m = WhisperModel("small.en", device="cpu", compute_type="int8")
for f in sorted(glob.glob(os.path.join(HERE, sys.argv[1], "*.mp3"))):
    if os.path.basename(f).startswith("ref_"): continue
    segs, _ = m.transcribe(f, beam_size=5)
    H = words(" ".join(s.text for s in segs))
    sm = difflib.SequenceMatcher(None, R, H, autojunk=False)
    errs = [(op, " ".join(R[a:b]), " ".join(H[c:e])) for op, a, b, c, e in sm.get_opcodes() if op != "equal"]
    bad = sum(max(b - a, e - c) for op, a, b, c, e in sm.get_opcodes() if op != "equal")
    print(f"{os.path.basename(f):14s} word errors {bad:3d} of {len(R)}  {errs[:12]}", flush=True)
