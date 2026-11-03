"""Stephen Davey's teaching-series pages as the Internet Archive saved them: what each holds (lesson titles, passages, audio links),
and how many series pages and sermon pages the archive has. Honest user agent; archive.org only. Saves to probe3/."""
import json, os, re, requests, time
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
def get(u, t=120):
    for k in range(3):
        try:
            r = requests.get(u, headers=H, timeout=t); print(f"  {r.status_code} {u[:140]} ({len(r.content)} b)", flush=True)
            if r.status_code in (429, 503, 504): time.sleep(8 * (k + 1)); continue
            return r
        except Exception as e:
            print(f"  ! {u[:120]}: {type(e).__name__}"); time.sleep(5)
    return None
r = get("http://web.archive.org/web/2026id_/https://www.wisdomonline.org/teaching-series/genesis/")
if r is not None and r.ok:
    t = r.text; open("probe3/wb_genesis.html", "w").write(t)
    print("   mp3:", len(set(re.findall(r"https?://[^\"'\s<>]+\.mp3", t))), sorted(set(re.findall(r"https?://[^\"'\s<>]+\.mp3", t)))[:6])
    print("   lesson links:", len(set(re.findall(r'href="([^"]*teachings?-detail/[^"]+)"', t))), sorted(set(re.findall(r'href="([^"]*teachings?-detail/[^"]+)"', t)))[:5])
    print("   page links:", sorted(set(re.findall(r'href="([^"]*page[,=]\d+[^"]*)"', t)))[:5])
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)))
    i = txt.find("Genesis"); print("   text:", txt[:1500])
for q in ("wisdomonline.org/teaching-series/", "www.wisdomonline.org/teaching-series/", "wisdomonline.org/teachings-detail/", "www.wisdomonline.org/teachings-detail/", "www.wisdomonline.org/teaching-series-detail/"):
    x = get(f"https://web.archive.org/cdx/search/cdx?url={q}&matchType=prefix&output=json&fl=original,timestamp,statuscode&collapse=urlkey&limit=5000", 300)
    if x is not None and x.ok and x.text.strip().startswith("["):
        rows = x.json()[1:]; ok = [r for r in rows if r[2] == "200" and "lang=" not in r[0]]
        print(f"   {q}: {len(rows)} archived, {len(ok)} ok english; e.g. {[r[0] for r in ok[:5]]}")
        json.dump(ok, open("probe3/wb_" + q.replace("/", "_").replace(".", "_") + ".json", "w"))
