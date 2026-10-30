"""Request every audio file on the road (first bytes only) and record any that do not answer as audio.
Writes audio_check.json: {"checked": n, "ok": n, "bad": [{id, title, audio, status, type}]}.
"""
from __future__ import annotations
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
     "Range": "bytes=0-1023"}

def probe(it):
    try:
        r = requests.get(it["audio"], headers=H, timeout=40, allow_redirects=True, stream=True)
        chunk = next(r.iter_content(1024), b"")
        ct = r.headers.get("content-type", "")
        ok = r.status_code in (200, 206) and (ct.startswith("audio") or "octet-stream" in ct or chunk[:3] in (b"ID3",) or chunk[:2] == b"\xff\xfb"
                                              or b"ftyp" in chunk[:12])
        return {**it, "status": r.status_code, "type": ct, "ok": ok}
    except Exception as e:
        return {**it, "status": 0, "type": f"{type(e).__name__}", "ok": False}

def main():
    html = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r"const D=(\{.*?\}),I=D.items", html, re.S).group(1).replace("<\\/", "</"))
    I = D["items"]
    road = {i for b in D["books"] for c in b["ch"] for i in c["ids"]} | {i for b in D["books"] for i in b["ov"]} | \
           {x["id"] for b in D["books"] for x in b["spans"]}
    todo = [{"id": i, "title": I[i]["t"], "audio": I[i]["audio"]} for i in sorted(road) if I[i]["audio"]]
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(probe, todo))
    bad = [r for r in res if not r["ok"]]
    json.dump({"checked": len(res), "ok": len(res) - len(bad), "bad": bad}, open("audio_check.json", "w"), indent=1, ensure_ascii=False)
    print(f"checked {len(res)} audio files: {len(res) - len(bad)} answer as audio, {len(bad)} do not")
    for b in bad[:20]: print("  ", b["status"], b["type"][:30], b["title"][:60], b["audio"][:80])

if __name__ == "__main__":
    main()
