"""Voice samples for the narrator: Psalm 23 (BSB) read by each British Kokoro voice (open-source, runs on GitHub).
Writes data/voice_samples/<voice>.mp3 and data/voice_samples/voices.json."""
import json, os, subprocess, sys
import numpy as np, soundfile as sf
from kokoro import KPipeline

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "voice_samples")
VOICES = [("bm_george", "George", "male"), ("bm_lewis", "Lewis", "male"), ("bm_daniel", "Daniel", "male"), ("bm_fable", "Fable", "male"),
          ("bf_emma", "Emma", "female"), ("bf_isabella", "Isabella", "female"), ("bf_alice", "Alice", "female"), ("bf_lily", "Lily", "female")]

def psalm23():
    d = json.load(open(os.path.join(HERE, "data", "bible", "Psalms.json"), encoding="utf-8"))
    vs = d["chapters"][22]
    return [vs[0].get("d", "")] + [v["t"].replace("\n", " ") for v in vs]

def main():
    os.makedirs(OUT, exist_ok=True)
    pipe = KPipeline(lang_code="b")  # British English
    parts = [p for p in psalm23() if p]
    meta = []
    for vid, name, sex in VOICES:
        audio = []
        for i, part in enumerate(parts):
            for _, _, a in pipe(part, voice=vid, speed=0.95):
                audio.append(np.asarray(a))
            audio.append(np.zeros(int(24000 * (0.7 if i == 0 else 0.45))))   # a breath between verses
        wav = os.path.join(OUT, f"{vid}.wav")
        sf.write(wav, np.concatenate(audio), 24000)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-b:a", "64k", wav[:-4] + ".mp3"], check=True)
        os.remove(wav)
        meta.append({"id": vid, "name": name, "voice": sex, "file": f"{vid}.mp3"})
        print("made", name, flush=True)
    json.dump(meta, open(os.path.join(OUT, "voices.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
