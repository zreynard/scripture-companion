"""Score narrator samples without listening: UTMOS (a model trained to predict how natural listeners rate speech, 1-5)
over 10-second windows, and how closely each reading matches its reference voice (ECAPA speaker similarity, 0-1)."""
import glob, os, subprocess, sys
import numpy as np, torch
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "data/voice_samples3")

def load(f):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", f, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768

mos = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True).eval()
from speechbrain.inference.speaker import EncoderClassifier
spk = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir="/tmp/ecapa")
emb = lambda x: torch.nn.functional.normalize(spk.encode_batch(torch.tensor(x)[None]).squeeze(), dim=0)

print(f"{'file':14s} {'natural':>7s} {'worst 10s':>9s} {'like him':>8s}")
for f in sorted(glob.glob(os.path.join(D, "*.mp3"))):
    name = os.path.basename(f); x = load(f)
    w = [x[i:i + 160000] for i in range(0, max(1, len(x) - 80000), 160000)]
    with torch.no_grad():
        s = [float(mos(torch.tensor(c)[None], 16000)) for c in w if len(c) > 48000]
    sim = ""
    n = name.split("_")[-1][:-4]
    ref = os.path.join(D, f"ref_{n}.mp3")
    if not name.startswith("ref_") and os.path.exists(ref):
        with torch.no_grad(): sim = f"{float(emb(x) @ emb(load(ref))):8.2f}"
    print(f"{name:14s} {np.mean(s):7.2f} {min(s):9.2f} {sim}", flush=True)
