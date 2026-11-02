"""Narrator samples, round 3: real, clean voices instead of synthetic ones.

Round 2 sounded like an old radio because Chatterbox copies the sound of its reference recording, and the references
were synthetic. Here the references are clean recordings of real people who gave their voices for exactly this use
(Kyutai's voice-donation project, CC0; VCTK, CC BY 4.0, as a fallback). We can't listen on the runner, so the
British older men are found by two open classifiers: age and gender (audeering), and accent (CommonAccent).

  python tools/tts_round3.py pick         score every candidate voice -> refs/pick.json + refs/<n>.wav (best first)
  python tools/tts_round3.py read N       read the passage in candidate N with Chatterbox and Chatterbox Turbo
  python tools/tts_round3.py collect      gather the readings into data/voice_samples3 (+ voices.json)
"""
import glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = os.path.join(HERE, "refs")
PARTS = os.path.join(HERE, "parts")
OUT = os.path.join(HERE, "data", "voice_samples3")
REPO = "kyutai/tts-voices"
KEEP = 6                     # candidates read aloud
NAMES = ["Alistair", "Barnaby", "Callum", "Desmond", "Everett", "Fergus"]


def passage():
    d = json.load(open(os.path.join(HERE, "data", "bible", "Luke.json"), encoding="utf-8"))
    return " ".join(v["t"].replace("\n", " ") for v in d["chapters"][14][10:24])


def chunks(text, limit=300):
    """A few sentences at a time: longer pieces keep the rhythm of a storyteller instead of a list of lines."""
    parts = re.split(r"(?<=[.!?’”])\s+(?=[A-Z“‘])", text)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > limit:
            out.append(cur); cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur: out.append(cur)
    return out


def load16k(path):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def pick():
    from huggingface_hub import hf_hub_download
    chosen = os.path.join(HERE, "tools", "voice_pick3.json")
    if os.path.exists(chosen):  # chosen from an earlier scoring run (its log), so skip the slow scoring
        return save_refs(json.load(open(chosen)))
    import numpy as np, torch, torch.nn as nn
    from huggingface_hub import list_repo_files
    from transformers import Wav2Vec2Processor
    from transformers.models.wav2vec2.modeling_wav2vec2 import Wav2Vec2Model, Wav2Vec2PreTrainedModel
    from speechbrain.inference.classifiers import EncoderClassifier

    files = [f for f in list_repo_files(REPO) if f.endswith(".wav")]
    for top in sorted({f.split("/")[0] for f in files}):
        ex = [f for f in files if f.startswith(top + "/")]
        print(f"{top}: {len(ex)} clips, e.g. {ex[:3]}", flush=True)
    # one clip per speaker: the volunteer donations (cleaned version when there is one), then VCTK
    def best_of(group):
        enh = [f for f in group if f.endswith("_enhanced.wav")]
        return (enh or group)[0]
    cands = {}
    for f in files:
        top = f.split("/")[0]
        if top not in ("voice-donations", "vctk"): continue
        base = re.sub(r"_enhanced\.wav$", ".wav", f)
        cands.setdefault((top, base), []).append(f)
    cands = [(top, best_of(g)) for (top, _), g in sorted(cands.items())]
    print(len(cands), "candidate speakers", flush=True)

    class Head(nn.Module):
        def __init__(self, c, n):
            super().__init__()
            self.dense = nn.Linear(c.hidden_size, c.hidden_size); self.dropout = nn.Dropout(c.final_dropout)
            self.out_proj = nn.Linear(c.hidden_size, n)
        def forward(self, x):
            return self.out_proj(self.dropout(torch.tanh(self.dense(self.dropout(x)))))

    class AgeGender(Wav2Vec2PreTrainedModel):
        def __init__(self, c):
            super().__init__(c)
            self.wav2vec2 = Wav2Vec2Model(c); self.age = Head(c, 1); self.gender = Head(c, 3); self.init_weights()
        def forward(self, x):
            h = self.wav2vec2(x)[0].mean(1)
            return self.age(h), torch.softmax(self.gender(h), 1)

    ag_name = "audeering/wav2vec2-large-robust-24-ft-age-gender"
    proc = Wav2Vec2Processor.from_pretrained(ag_name)
    ag = AgeGender.from_pretrained(ag_name).eval()
    acc = EncoderClassifier.from_hparams(source="Jzuluaga/accent-id-commonaccent_ecapa", savedir="/tmp/accent")
    le = acc.hparams.label_encoder
    labels = [le.ind2lab[i] for i in range(len(le.ind2lab))]
    print("accents:", labels, flush=True)
    BRIT = {"england", "scotland", "wales", "ireland"}

    rows = []
    for top, f in cands:
        try:
            p = hf_hub_download(REPO, f)
            x = load16k(p)
            if len(x) < 16000 * 5: continue
            rms = float(np.sqrt((x ** 2).mean()))
            with torch.no_grad():
                age, g = ag(torch.tensor(proc(x, sampling_rate=16000).input_values[0])[None])
                out = acc.classify_batch(torch.tensor(x)[None])
            pr = torch.softmax(out[0][0], -1).tolist()
            accent = dict(zip(labels, pr))
            brit = sum(v for k, v in accent.items() if k in BRIT)
            r = {"file": f, "set": top, "age": round(float(age) * 100), "male": round(float(g[0][1]), 2),
                 "brit": round(brit, 2), "accent": max(accent, key=accent.get), "secs": round(len(x) / 16000, 1),
                 "level": round(rms, 3)}
            rows.append(r)
            print(r, flush=True)
        except Exception as e:
            print("skip", f, type(e).__name__, str(e)[:120], flush=True)

    def score(r):
        # British first, then older; volunteer donations before VCTK (they agreed to cloning in so many words)
        return r["brit"] * 2 + min(r["age"], 70) / 35 + (0.3 if r["set"] == "voice-donations" else 0)
    men = sorted([r for r in rows if r["male"] >= 0.8 and r["brit"] >= 0.4], key=score, reverse=True)
    print("\nbest British men:")
    for r in men[:25]: print(f"  {score(r):.2f}  {r}")
    save_refs(men[:KEEP])


def save_refs(keep):
    from huggingface_hub import hf_hub_download
    os.makedirs(REFS, exist_ok=True)
    for n, r in enumerate(keep):
        # up to 14 seconds, levelled, so every reference is comparable
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", hf_hub_download(REPO, r["file"]), "-t", "14",
                        "-ac", "1", "-ar", "24000", "-af", "loudnorm=I=-18:TP=-2", os.path.join(REFS, f"{n}.wav")], check=True)
    json.dump(keep, open(os.path.join(REFS, "pick.json"), "w"), indent=1)


def read(n):
    import numpy as np, soundfile as sf, torch
    n = int(n)
    keep = json.load(open(os.path.join(REFS, "pick.json")))
    if n >= len(keep): print("no candidate", n); return
    ref = os.path.join(REFS, f"{n}.wav")
    pieces = chunks(passage())
    os.makedirs(PARTS, exist_ok=True)

    def save(tag, audio, sr):
        wav = os.path.join(PARTS, f"{tag}_{n}.wav")
        sf.write(wav, np.concatenate(audio), sr)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-af", "loudnorm=I=-18:TP=-1.5",
                        "-b:a", "112k", wav[:-4] + ".mp3"], check=True)
        os.remove(wav); print("done", tag, n, flush=True)

    runs = []
    try:
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        runs.append(("turbo", lambda: ChatterboxTurboTTS.from_pretrained(device="cpu"), {}))
    except Exception as e:
        print("no turbo:", e, flush=True)
    from chatterbox.tts import ChatterboxTTS
    runs.append(("cb", lambda: ChatterboxTTS.from_pretrained(device="cpu"), {"exaggeration": 0.5, "cfg_weight": 0.4}))
    for tag, load, kw in runs:
        try:
            model = load()
            audio = []
            for p in pieces:
                torch.manual_seed(5)
                wav = model.generate(p, audio_prompt_path=ref, **kw).squeeze().cpu().numpy()
                audio += [wav, np.zeros(int(model.sr * 0.3), dtype=wav.dtype)]
            save(tag, audio, model.sr)
            del model
        except Exception as e:
            print("failed", tag, type(e).__name__, str(e)[:300], flush=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", ref, "-b:a", "112k", os.path.join(PARTS, f"ref_{n}.mp3")], check=True)


def collect():
    keep = json.load(open(os.path.join(REFS, "pick.json")))
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "*.mp3")): os.remove(f)
    meta = []
    for n, r in enumerate(keep):
        for tag, model in (("turbo", "Chatterbox Turbo"), ("cb", "Chatterbox")):
            src = os.path.join(PARTS, f"{tag}_{n}.mp3")
            if not os.path.exists(src): continue
            name = f"{tag}_{n}.mp3"
            os.replace(src, os.path.join(OUT, name))
            meta.append({"id": f"{tag}_{n}", "name": NAMES[n], "voice": "male", "file": name,
                         "about": f"{model} · a real man's voice, sounds about {r['age']}, {r['accent'].title()} accent",
                         "ref": f"ref_{n}.mp3", "scores": r})
        if os.path.exists(os.path.join(PARTS, f"ref_{n}.mp3")):
            os.replace(os.path.join(PARTS, f"ref_{n}.mp3"), os.path.join(OUT, f"ref_{n}.mp3"))
    json.dump(meta, open(os.path.join(OUT, "voices.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    {"pick": pick, "read": read, "collect": collect}[sys.argv[1]](*sys.argv[2:])
