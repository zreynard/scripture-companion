"""Common Crawl (the open public web dataset) for Stephen Davey's sermon and series pages on wisdomonline.org: index lookups one
crawl at a time with patience, then one sample record to see what the saved page holds. Honest user agent. Saves to probe3/."""
import gzip, json, os, re, requests, time
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3", exist_ok=True)
cols = [c["cdx-api"] for c in requests.get("https://index.commoncrawl.org/collinfo.json", headers=H, timeout=60).json()][:24]
pages = {}
for api in cols:
    for q in ("www.wisdomonline.org/teachings-detail/", "www.wisdomonline.org/teaching-series/"):
        for k in range(4):
            try:
                x = requests.get(f"{api}?url={q}&matchType=prefix&output=json&filter=status:200", headers=H, timeout=300)
            except Exception as e:
                x = None
            if x is not None and x.status_code == 200: break
            time.sleep(20 * (k + 1))
        code = x.status_code if x is not None else "err"
        rows = [json.loads(l) for l in x.text.splitlines() if l.strip().startswith("{")] if x is not None and x.status_code == 200 else []
        for o in rows:
            u = o["url"].split("?")[0]
            if "lang=" in o["url"]: continue
            pages.setdefault(u, o)
        print(f"  {api.split('/')[-1]} {q}: {code}, {len(rows)} rows; {len(pages)} distinct pages so far", flush=True)
        time.sleep(3)
json.dump(list(pages.values()), open("probe3/cc_pages.json", "w"))
det = [o for u, o in pages.items() if "teachings-detail" in u]; ser = [o for u, o in pages.items() if "teaching-series/" in u]
print("sermon pages:", len(det), "series pages:", len(ser))
for o in (det[:1] + ser[:1]):
    rng = f"bytes={int(o['offset'])}-{int(o['offset']) + int(o['length']) - 1}"
    w = requests.get("https://data.commoncrawl.org/" + o["filename"], headers={**H, "Range": rng}, timeout=120)
    body = gzip.decompress(w.content).decode("utf-8", "replace")
    print("sample", o["url"], w.status_code, "| mp3:", sorted(set(re.findall(r"https?://[^\"'\s<>]+\.mp3", body)))[:4], "| h1:", [re.sub(r"<[^>]+>|\s+", " ", h).strip() for h in re.findall(r"<h1[^>]*>(.*?)</h1>", body, re.S)][:2],
          "| lessons:", len(set(re.findall(r'teachings-detail/[a-z0-9-]+', body))))
    open("probe3/cc_sample_" + ("det" if "detail" in o["url"] else "ser") + ".html", "w").write(body)
