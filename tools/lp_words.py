"""The words, with their times, of a stretch at the end of a recording (small.en): to set where each movement of the
Lord's Prayer begins in a pastor's prayer.   python tools/lp_words.py SRC SB E   (SB/E = seconds before the file's end)"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trim

src, sb, e = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
t = open(os.path.join(trim.HERE, "out", "site", "index.html"), encoding="utf-8").read()
D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
it = D["items"][src]
from faster_whisper import WhisperModel
model = WhisperModel("small.en", device="cpu", compute_type="int8")
data, whole = trim.fetch(it["audio"], tail=True, nbytes=trim.head_bytes(it["audio"], sb + 30, it.get("dur")))
pcm = trim.decode(data)
if whole: pcm = pcm[-int((sb + 30) * 16000):]
else: pcm = pcm[16000 * 2:]
TL = len(pcm) / 16000; lo = max(0, TL - sb - 3)
ws = trim.words_of(pcm[int(lo * 16000): int((TL - e + 2) * 16000)], model)
print(f"window {TL:.2f}s; times below are seconds BEFORE THE FILE'S END")
for a, b, w in ws: print(f"{TL - (a + lo):8.2f} {TL - (b + lo):8.2f}  {w}")
