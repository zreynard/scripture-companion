"""Stephen Davey's sermon audio on Wisdom International's media server (DigitalOcean Spaces): does it serve the app's honest
requests, and does the server publish its own file index? Honest user agent; a refusal is reported and left alone."""
import os, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
B = "https://wisdomonline-a.atl1.cdn.digitaloceanspaces.com"
def get(u, save=None, **kw):
    try:
        r = requests.get(u, headers={**H, **kw.pop("headers", {})}, timeout=60, **kw); print(f"  {r.status_code} {u} ({len(r.content)} b, {r.headers.get('content-type','')[:30]}) range={r.headers.get('content-range')} cors={r.headers.get('access-control-allow-origin')}", flush=True)
        if save and r.ok: open("probe3/" + save, "w").write(r.text)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:100]}"); return None
get(B + "/Genesis01-Genesis1_1.mp3", headers={"Range": "bytes=0-1023"})
get("https://wisdomonline-a.atl1.digitaloceanspaces.com/Genesis01-Genesis1_1.mp3", headers={"Range": "bytes=0-1023"})
for u in (B + "/", "https://wisdomonline-a.atl1.digitaloceanspaces.com/", B + "/?list-type=2&max-keys=1000"):
    r = get(u, "do_index.xml")
    if r is not None and r.ok:
        keys = re.findall(r"<Key>([^<]+)</Key>", r.text); print("   keys:", len(keys), keys[:15], "| truncated:", re.findall(r"<IsTruncated>([^<]+)", r.text), "| next:", re.findall(r"<NextContinuationToken>([^<]+)|<NextMarker>([^<]+)", r.text)[:1])
        if keys: break
