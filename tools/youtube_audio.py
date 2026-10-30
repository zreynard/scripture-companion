"""Pull audio for teaching that exists only on YouTube, and host it beside the app.

Runs on GitHub Actions (needs yt-dlp, ffmpeg and the gh CLI with GH_TOKEN):
  1. list the official channels (Radical, 2819 Church, PAM) -> data/youtube_index.json
  2. choose targets: Secret Church 22-26 sessions, and 2819/PAM sermons that name a passage,
     are preached by PAM or a 2819 preacher in config.PAM_CHURCH_PREACHERS, and are not already
     in the app with audio
  3. download each target's audio as small mono MP3, upload it to a GitHub Release
     (audio-1, audio-2, ... at most 900 files each) and record it in data/youtube_audio.json
Resumable: targets already recorded are skipped. --limit caps downloads per run.
Prints how many targets remain, and writes it to remaining.txt for the workflow.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from classify import make_entry

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(HERE, "data", "youtube_index.json")
MAP = os.path.join(HERE, "data", "youtube_audio.json")
CATALOG = os.path.join(HERE, "data", "catalog_verified.jsonl")
CHANNELS = {  # key: (listing urls, catalog source)
    "radical": (["https://www.youtube.com/channel/UCTP7mGxH9LFTaMO2Kw9nZ7g/videos",
                 "https://www.youtube.com/channel/UCTP7mGxH9LFTaMO2Kw9nZ7g/streams"], "youtube_radical"),
    "2819": (["https://www.youtube.com/@2819Church/videos", "https://www.youtube.com/@2819Church/streams"], "youtube_2819"),
    "pam": (["https://www.youtube.com/@PhilipAnthonyMitchell/videos"], "youtube_pam"),
}
SC_RE = re.compile(r"secret church\s*(2[2-6])\b|secret church.*\b(jonah|ruth|elijah|who am i)\b|"
                   r"\b(jonah|ruth|elijah|who am i)\b.*secret church|secret church.*gospel of matthew", re.I)
MIN_SECONDS = 15 * 60

def log(m): print(f"[youtube] {m}", flush=True)

def ytdlp(*args, timeout=3600):
    return subprocess.run(["yt-dlp", "--no-warnings", *args], capture_output=True, text=True, timeout=timeout)

def list_channels() -> list[dict]:
    vids = {}
    for key, (urls, src) in CHANNELS.items():
        for u in urls:
            p = ytdlp("--flat-playlist", "--ignore-errors", "-J", u, timeout=1800)
            if not p.stdout.strip():
                log(f"{u}: nothing listed ({p.stderr.strip()[:200]})"); continue
            n = 0
            data = json.loads(p.stdout) or {}
            if not data.get("entries"):
                log(f"{u}: no videos (channel not found?)"); continue
            for e in data["entries"]:
                if e and e.get("id") and e["id"] not in vids:
                    vids[e["id"]] = {"id": e["id"], "title": e.get("title") or "", "channel": key, "source": src,
                                     "duration": int(e.get("duration") or 0), "upload_date": e.get("upload_date") or ""}
                    n += 1
            log(f"{u}: {n} videos")
    json.dump(list(vids.values()), open(INDEX, "w"), indent=0, ensure_ascii=False)
    return list(vids.values())

def _core(t):
    t = re.sub(r"\s*\|.*$", "", t or ""); t = re.sub(r"\([^)]*\)", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()

def choose(vids: list[dict]) -> list[dict]:
    have = set()  # titles already playable in the app
    for l in open(CATALOG, encoding="utf-8"):
        e = json.loads(l)
        if e.get("audio_override") or "buzzsprout.com" in e.get("url", ""):
            have.add(_core(e["title"]))
            for seg in e["title"].split("|")[1:-1]:
                have.add(_core(seg))
    team = {"PAM"} | {f"guest:{n}" for n in config.PAM_CHURCH_PREACHERS}
    out = []
    for v in vids:
        if v["duration"] and v["duration"] < MIN_SECONDS:
            continue  # clips, promos, shorts
        if v["channel"] == "radical":
            if SC_RE.search(v["title"]):
                out.append(v)
            continue
        e = make_entry(source=v["source"], source_url="", url=f"https://www.youtube.com/watch?v={v['id']}",
                       title=v["title"], era="2819" if v["channel"] == "2819" else "pam-channel",
                       channel_default="PAM" if v["channel"] == "pam" else None)
        if e["speaker"] not in team or not e["refs"]:
            continue
        name = [_core(x) for x in v["title"].split("|")[1:-1]] or [_core(v["title"])]
        if _core(v["title"]) in have or any(n and n in have for n in name):
            continue  # already in the app from the podcast feed
        out.append(v)
    return out

def release_tag(done: dict) -> str:
    n = sum(1 for d in done.values() if d.get("asset"))
    tag = f"audio-{n // 900 + 1}"
    if subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode != 0:
        subprocess.run(["gh", "release", "create", tag, "--title", f"Teaching audio ({tag})",
                        "--notes", "Audio of teaching published only on YouTube, for the Scripture Companion app."],
                       capture_output=True)
    return tag

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--minutes", type=int, default=300, help="stop starting new downloads after this long")
    a = ap.parse_args()
    t0 = time.time()
    done = json.load(open(MAP)) if os.path.exists(MAP) else {}
    vids = list_channels()
    targets = [v for v in choose(vids) if v["id"] not in done or not done[v["id"]].get("asset")]
    log(f"{len(vids)} videos listed; {len(targets)} need audio")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    os.makedirs("/tmp/yta", exist_ok=True)
    got = 0
    for v in targets[:a.limit]:
        if time.time() - t0 > a.minutes * 60:
            break
        out = f"/tmp/yta/{v['id']}.mp3"
        p = ytdlp("-f", "bestaudio", "-x", "--audio-format", "mp3",
                  "--postprocessor-args", "ffmpeg:-ac 1 -b:a 40k -ar 22050",
                  "-o", f"/tmp/yta/{v['id']}.%(ext)s", f"https://www.youtube.com/watch?v={v['id']}", timeout=2400)
        if p.returncode != 0 or not os.path.exists(out):
            err = (p.stderr or "").strip().splitlines()[-1:] or ["no file"]
            done[v["id"]] = {**v, "error": err[0][:300], "tried": time.strftime("%Y-%m-%d")}
            log(f"FAIL {v['id']} {v['title'][:60]}: {err[0][:160]}")
            continue
        tag = release_tag(done)
        up = subprocess.run(["gh", "release", "upload", tag, out, "--clobber"], capture_output=True, text=True)
        if up.returncode != 0:
            log(f"upload failed {v['id']}: {up.stderr[:200]}"); os.remove(out); continue
        done[v["id"]] = {**v, "asset": f"https://github.com/{repo}/releases/download/{tag}/{v['id']}.mp3",
                         "bytes": os.path.getsize(out)}
        os.remove(out); got += 1
        log(f"ok {got}: {v['title'][:70]}")
        json.dump(done, open(MAP, "w"), indent=0, ensure_ascii=False)  # save as we go
    json.dump(done, open(MAP, "w"), indent=0, ensure_ascii=False)
    remaining = len([v for v in targets if not done.get(v["id"], {}).get("asset") and not done.get(v["id"], {}).get("error")])
    fails = sum(1 for d in done.values() if d.get("error") and not d.get("asset"))
    log(f"downloaded {got} this run; {remaining} still to do; {fails} failed")
    open("remaining.txt", "w").write(str(remaining))

if __name__ == "__main__":
    main()
