"""Pray's recordings, looked at byte by byte.

    python tools/clip_probe.py probe
        every Pray recording's host: does it let the app read a byte range itself (CORS), and is the MP3 constant
        bitrate (sampled at five places) or variable (a phone jumps inside those inexactly)
    python tools/clip_probe.py slice SRC SB E
        the whole file read frame by frame: its true length, the exact bytes of the stretch SB..E seconds before its end
        (cut on frame boundaries), and those very bytes heard (small.en): what a phone playing just them would hear
"""
import json, os, re, subprocess, sys, tempfile
import requests
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
ORIGIN = "https://zreynard.github.io"
BR = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320], 2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}

def frame(b, i):
    """The MPEG audio frame header at b[i]: (bitrate kbps, sample rate, frame bytes, samples) or None."""
    if i + 4 > len(b) or b[i] != 0xFF or (b[i + 1] & 0xE0) != 0xE0: return None
    ver = (b[i + 1] >> 3) & 3; lay = (b[i + 1] >> 1) & 3; bri = b[i + 2] >> 4; sri = (b[i + 2] >> 2) & 3; pad = (b[i + 2] >> 1) & 1
    if ver == 1 or lay != 1 or bri in (0, 15) or sri == 3: return None      # layer III only
    kb = BR[1 if ver == 3 else 2][bri]; sr = SR[ver][sri]; spf = 1152 if ver == 3 else 576
    return kb, sr, (spf // 8 * kb * 1000) // sr + pad, spf

def sync(b, i=0):
    """The first real frame at or after i (two headers in a row)."""
    while i < len(b) - 4:
        f = frame(b, i)
        if f and frame(b, i + f[2]): return i, f
        i += 1
    return None, None

def id3len(b):
    return 10 + ((b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]) if b[:3] == b"ID3" else 0

def probe():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    P = D["pray"]; urls = {}
    for x in P["led"]: urls.setdefault(x["audio"], ("led", x["who"]))
    for x in P["med"]: urls.setdefault(x["audio"], ("med", x["who"]))
    if P.get("lp"): urls.setdefault(P["lp"]["audio"], ("lp", P["lp"]["who"]))
    by = {}
    for u, (kind, who) in urls.items():
        r = {"kind": kind, "who": who, "url": u}
        try:
            g = requests.get(u, headers={**UA, "Origin": ORIGIN, "Range": "bytes=0-131071"}, timeout=60, allow_redirects=True)
            r.update(status=g.status_code, host=g.url.split("/")[2], acao=g.headers.get("access-control-allow-origin"), ranges=g.headers.get("content-range"),
                     acah=g.headers.get("access-control-expose-headers"))
            tot = int((g.headers.get("content-range") or "/0").split("/")[-1] or 0)
            b = g.content; i, f = sync(b, id3len(b))
            if f:
                head = b[i:i + 200]
                r.update(first_kbps=f[0], rate=f[1], tag="Xing" if b"Xing" in head else "Info" if b"Info" in head else "VBRI" if b"VBRI" in head else "none")
                kbs = {f[0]}
                for frac in (0.2, 0.4, 0.6, 0.8):
                    if not tot: break
                    a = int(tot * frac); h = requests.get(u, headers={**UA, "Range": f"bytes={a}-{a + 65535}"}, timeout=60)
                    j, f2 = sync(h.content)
                    if f2:
                        k, n = j, 0
                        while n < 20 and frame(h.content, k): ff = frame(h.content, k); kbs.add(ff[0]); k += ff[2]; n += 1
                r.update(bitrates=sorted(kbs), cbr=len(kbs) == 1 and r["tag"] != "Xing", size=tot)
            else: r["format"] = "not MP3 (m4a?)"
        except Exception as ex: r["err"] = str(ex)[:100]
        print(json.dumps(r), flush=True)
        by.setdefault(r.get("host", "?"), []).append(r)
    print()
    for h, v in by.items():
        print(f"{h:45} {len(v):3} files  CORS {'yes' if all(x.get('acao') in ('*', ORIGIN) for x in v) else 'NO' if not any(x.get('acao') for x in v) else 'some'}"
              f"  constant bitrate {sum(1 for x in v if x.get('cbr'))}/{len(v)}  tags {sorted({x.get('tag', '-') for x in v})}  kbps {sorted({k for x in v for k in x.get('bitrates', [])})}")

def slice_(src, sb, e):
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    url = D["items"][src]["audio"]
    b = requests.get(url, headers=UA, timeout=600).content
    i0 = id3len(b); i, f = sync(b, i0)
    frames = []; k = i; tt = 0.0
    while k < len(b):
        ff = frame(b, k)
        if not ff:
            j, ff2 = sync(b, k + 1)
            if j is None: break
            k = j; continue
        frames.append((k, tt)); tt += ff[3] / ff[1]; k += ff[2]
    L = tt; kbs = sorted({frame(b, k)[0] for k, _ in frames[::200]})
    print(f"file {len(b)} bytes; frames {len(frames)}; true length {L:.3f}s; bitrates seen {kbs}; header-estimate length {(len(b) - i) * 8 / (frames and frame(b, frames[0][0])[0] * 1000):.3f}s")
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.mp3"), "wb").write(b)
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", os.path.join(d, "a.mp3")], capture_output=True, text=True).stdout.strip()
        print(f"ffprobe length {out}")
        t0, t1 = L - sb, L - e
        a = max(x for x in frames if x[1] <= t0); z = min((x for x in frames if x[1] >= t1), default=(len(b), L))
        print(f"stretch {t0:.3f}-{t1:.3f}s = bytes {a[0]}-{z[0] - 1} (frames from {a[1]:.3f}s to {z[1]:.3f}s; {z[0] - a[0]} bytes)")
        open(os.path.join(d, "s.mp3"), "wb").write(b[a[0]:z[0]])
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", os.path.join(d, "s.mp3"), "-ac", "1", "-ar", "16000", os.path.join(d, "s.wav")], check=True)
        sys.path.insert(0, os.path.join(HERE, "tools")); import trim
        pcm = trim.decode(open(os.path.join(d, "s.mp3"), "rb").read())
        from faster_whisper import WhisperModel
        ws = trim.words_of(pcm, WhisperModel("small.en", device="cpu", compute_type="int8"))
        print(f"the slice as a phone would play it ({len(pcm) / 16000:.2f}s): seconds from its start, word")
        for w in ws: print(f"  {w[0]:7.2f} {w[1]:7.2f}  {w[2]}")
        print(json.dumps({"src": src, "url": url, "bytes": [a[0], z[0] - 1], "slice_len": round(len(pcm) / 16000, 3), "file_len": round(L, 3), "frame_t0": round(a[1], 3)}))

if __name__ == "__main__":
    if sys.argv[1] == "probe": probe()
    else: slice_(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]))
