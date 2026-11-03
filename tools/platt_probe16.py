"""Stephen Davey's own archive (wisdomonline.org/teaching-series, by book). Honest user agent; a refusal is reported and left alone.
Saves the pages it can read to probe3/ (pushed to the diag branch) so they can be studied offline."""
import os, re, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
os.makedirs("probe3", exist_ok=True)
def get(u, save=None):
    try:
        r = requests.get(u, headers=H, timeout=45); print(f"  {r.status_code} {u} ({len(r.content)} bytes)", flush=True)
        if save and r.ok: open(os.path.join("probe3", save), "w").write(r.text)
        return r
    except Exception as e:
        print(f"  ! {u}: {type(e).__name__} {str(e)[:120]}"); return None
B = "https://www.wisdomonline.org"
get(B + "/sitemap", "sitemap.html")
r = get(B + "/teaching-series", "index.html")
if r is not None and r.ok:
    links = list(dict.fromkeys(re.findall(r'href="(/teaching-series/[^"?#]+)"', r.text)))
    print("  series links:", len(links), links[:80])
for p in ("james", "romans", "1-samuel"):
    r = get(B + "/teaching-series/" + p, f"series-{p}.html")
    if r is not None and r.ok:
        t = r.text
        sl = list(dict.fromkeys(re.findall(r'href="([^"]*(?:/sermon|/sermons|/lesson|/blog)[^"]*)"', t)))
        print("  sermon links:", len(sl), sl[:12])
        print("  mp3:", re.findall(r'https?://[^"\'\s]+\.mp3[^"\'\s]*', t)[:5], "| audio:", len(re.findall(r"<audio", t)))
        if sl:
            u = sl[0] if sl[0].startswith("http") else B + sl[0]
            s = get(u, f"sermon-{p}.html")
            if s is not None and s.ok:
                print("   sermon mp3:", re.findall(r'https?://[^"\'\s]+\.mp3[^"\'\s]*', s.text)[:5], "| audio:", len(re.findall(r"<audio", s.text)),
                      "| media hosts:", sorted(set(re.findall(r'https?://([a-z0-9.-]*(?:media|cdn|cloudfront|amazonaws|buzzsprout|vimeo|youtube)[a-z0-9.-]*)', s.text)))[:10])
