"""Look up what the leading open voice models ship with (file lists and model cards), for choosing narrators."""
from huggingface_hub import list_repo_files, hf_hub_download
REPOS = ["mistralai/Voxtral-4B-TTS-2603", "kyutai/tts-voices", "ResembleAI/chatterbox", "ResembleAI/chatterbox-turbo",
         "boson-ai/higgs-audio-v2-generation-3B-base", "canopylabs/orpheus-3b-0.1-ft", "nari-labs/Dia-1.6B-0626",
         "IndexTeam/IndexTTS-2", "fishaudio/openaudio-s1-mini", "microsoft/VibeVoice-1.5B", "hexgrad/Kokoro-82M"]
for r in REPOS:
    print("=" * 20, r, flush=True)
    try:
        fs = list_repo_files(r)
        print(len(fs), "files"); print("\n".join([f for f in fs if not f.startswith(".")][:400]))
        try:
            print(open(hf_hub_download(r, "README.md")).read()[:5000])
        except Exception as e: print("no readme", e)
    except Exception as e:
        print("ERR", type(e).__name__, str(e)[:200])
