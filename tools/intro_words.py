"""What is said in the first minutes of an episode, with times: to see where the teaching itself begins.

    SOURCE=davey_journey N=16 python tools/intro_words.py [id ...]
Runs on GitHub's servers (ffmpeg + faster-whisper). Fetches each episode's opening with plain requests under the
app's own name; a refusal is logged and left alone. Prints timed lines and saves probe3/intro_words.json."""
import json, os, re, subprocess, sys, tempfile
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
SOURCE = os.environ.get("SOURCE", "davey_journey")
N = int(os.environ.get("N", "16"))
SECS = int(os.environ.get("SECS", "150"))


def main():
    from faster_whisper import WhisperModel
    rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8")]
    eps = sorted([e for e in rows if e["source"] == SOURCE and (e.get("audio_override") or "").endswith(".mp3")], key=lambda e: e["id"])
    skips = json.load(open(os.path.join(HERE, "data", "intro_skip", f"{SOURCE}.json")))
    want = [e for e in eps if e["id"] in sys.argv[1:]]
    want += [e for e in eps[:: max(1, len(eps) // N)] if e not in want][:N]
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    out = {}
    tmp = tempfile.mkdtemp()
    for e in want:
        mp3, wav = os.path.join(tmp, "a.mp3"), os.path.join(tmp, "a.wav")
        try:
            r = requests.get(e["audio_override"], headers=H, timeout=90, stream=True)
            if r.status_code not in (200, 206):
                print(f"\n## {e['title']}: refused ({r.status_code})", flush=True); continue
            with open(mp3, "wb") as f:
                got = 0
                for chunk in r.iter_content(65536):
                    f.write(chunk); got += len(chunk)
                    if got > 4_000_000: break
            r.close()
        except requests.RequestException as x:
            print(f"\n## {e['title']}: {type(x).__name__}", flush=True); continue
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", str(SECS), "-i", mp3, "-ac", "1", "-ar", "16000", wav], check=False)
        if not os.path.exists(wav): print(f"\n## {e['title']}: no audio"); continue
        segs, _ = model.transcribe(wav, beam_size=1, language="en", vad_filter=True, word_timestamps=False)
        lines = [(round(s.start, 1), round(s.end, 1), s.text.strip()) for s in segs]
        out[e["id"]] = {"title": e["title"], "skip": skips.get(e["id"]), "lines": lines}
        print(f"\n## {e['id']} {e['title']}  (skip now {skips.get(e['id'])})", flush=True)
        for a, b, t in lines: print(f"  {a:6.1f}-{b:6.1f}  {t}", flush=True)
        os.remove(wav)
    os.makedirs("probe3", exist_ok=True)
    json.dump(out, open("probe3/intro_words.json", "w"), indent=1)


if __name__ == "__main__":
    main()
