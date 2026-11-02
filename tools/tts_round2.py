"""Narrator samples, round 2: the most natural open models that run on GitHub's free machines (no keys).

Two steps, each in its own environment (their libraries clash):
  python tools/tts_round2.py design     Parler-TTS builds each narrator's voice from a written description
                                        (made-up voices, so no real person's voice is copied) -> refs/<id>.wav
  python tools/tts_round2.py read       Chatterbox reads the passage in each designed voice -> data/voice_samples2/<id>.mp3
The passage is the prodigal son (Luke 15:11-24, BSB): storytelling, with dialogue.
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = os.path.join(HERE, "refs")
OUT = os.path.join(HERE, "data", "voice_samples2")

# made-up narrators, described in words (Parler-TTS turns a description into a voice)
NARRATORS = [
    ("arthur", "Arthur", "An older British man with a deep, warm, slightly gravelly voice tells a story slowly and gently, "
                         "like a wise grandfather by the fire. The recording is very clear and close-up, with no background noise."),
    ("edmund", "Edmund", "A British man in his fifties with a rich, resonant baritone voice reads in a calm, measured and expressive way. "
                         "The recording is very clear, studio quality, with no background noise."),
    ("hugh", "Hugh", "A soft-spoken British man with a gentle, thoughtful, low voice narrates at a relaxed pace with natural pauses. "
                     "The recording is very clear and intimate, with no background noise."),
]
REF_LINE = ("In the beginning God created the heavens and the earth. And the earth was without form, and void; "
            "and the Spirit of God was hovering over the face of the waters.")


def passage():
    d = json.load(open(os.path.join(HERE, "data", "bible", "Luke.json"), encoding="utf-8"))
    return " ".join(v["t"].replace("\n", " ") for v in d["chapters"][14][10:24])


def sentences(text, limit=260):
    """Split into sentence-sized pieces (the models read short pieces best), never splitting inside a quote mark pair."""
    parts = re.split(r"(?<=[.!?’”])\s+(?=[A-Z“‘])", text)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > limit:
            out.append(cur); cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur: out.append(cur)
    return out


def design():
    import torch, soundfile as sf
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer
    name = "parler-tts/parler-tts-large-v1"
    model = ParlerTTSForConditionalGeneration.from_pretrained(name)
    tok = AutoTokenizer.from_pretrained(name)
    os.makedirs(REFS, exist_ok=True)
    for vid, _, desc in NARRATORS:
        torch.manual_seed(7)
        ids = tok(desc, return_tensors="pt").input_ids
        prompt = tok(REF_LINE, return_tensors="pt").input_ids
        audio = model.generate(input_ids=ids, prompt_input_ids=prompt).cpu().numpy().squeeze()
        sf.write(os.path.join(REFS, f"{vid}.wav"), audio, model.config.sampling_rate)
        print("designed", vid, round(len(audio) / model.config.sampling_rate, 1), "s", flush=True)


def read():
    import numpy as np, soundfile as sf, torch
    from chatterbox.tts import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained(device="cpu")
    os.makedirs(OUT, exist_ok=True)
    pieces = sentences(passage())
    meta = []
    voices = [(vid, nm, os.path.join(REFS, f"{vid}.wav")) for vid, nm, _ in NARRATORS] + [("default", "Chatterbox default", None)]
    for vid, nm, ref in voices:
        if ref and not os.path.exists(ref):
            print("no reference for", vid, flush=True); continue
        audio = []
        for k, p in enumerate(pieces):
            torch.manual_seed(11)
            kw = {"exaggeration": 0.45, "cfg_weight": 0.35}
            if ref: kw["audio_prompt_path"] = ref
            wav = model.generate(p, **kw).squeeze().cpu().numpy()
            audio += [wav, np.zeros(int(model.sr * 0.35))]
        path = os.path.join(OUT, f"cb_{vid}.wav")
        sf.write(path, np.concatenate(audio), model.sr)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-ac", "1", "-b:a", "96k", path[:-4] + ".mp3"], check=True)
        os.remove(path)
        meta.append({"id": f"cb_{vid}", "name": nm, "voice": "male", "file": f"cb_{vid}.mp3",
                     "about": "Chatterbox" + (", voice designed with Parler-TTS" if ref else ", its built-in voice")})
        print("read", vid, flush=True)
    # also keep each designed voice's own short reading, so the voice itself can be judged
    for vid, nm, _ in NARRATORS:
        ref = os.path.join(REFS, f"{vid}.wav")
        if os.path.exists(ref):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", ref, "-ac", "1", "-b:a", "96k", os.path.join(OUT, f"parler_{vid}.mp3")], check=True)
    json.dump(meta, open(os.path.join(OUT, "voices.json"), "w"), indent=1)


if __name__ == "__main__":
    {"design": design, "read": read}[sys.argv[1]]()
