"""Which audio hosts let the app process their audio in the browser (CORS)? For a few episodes per source,
follow redirects with an Origin header and report the final host and Access-Control-Allow-Origin."""
import json, os, random, requests
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
h = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
i = h.index("const D=") + 8; D, _ = json.JSONDecoder().raw_decode(h[i:])
cat = {}
for line in open(os.path.join(HERE, "data", "catalog_verified.jsonl"), encoding="utf-8"):
    e = json.loads(line); cat[e["id"]] = e.get("source")
by = {}
for it in D["items"].values():
    if it.get("audio"): by.setdefault(cat.get(it["id"]) or "?", []).append(it)
random.seed(3); out = {}
H = {"Origin": "https://zreynard.github.io", "Range": "bytes=0-1023", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
for src, items in sorted(by.items()):
    rows = []
    for it in random.sample(items, min(3, len(items))):
        try:
            r = requests.get(it["audio"], headers=H, timeout=40, stream=True, allow_redirects=True)
            hops = [x.headers.get("access-control-allow-origin") for x in r.history] + [r.headers.get("access-control-allow-origin")]
            rows.append({"final": r.url.split("/")[2], "status": r.status_code, "acao_each_hop": hops})
        except Exception as ex:
            rows.append({"error": str(ex)[:120]})
    out[src] = rows; print(src, json.dumps(rows), flush=True)
json.dump(out, open("cors.json", "w"), indent=1)
