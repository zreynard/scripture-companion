#!/usr/bin/env python3
"""CLI.  python run.py harvest [--sources a,b,c] [--radical-limit N]
         python run.py verify  [--force] [--limit N] [--sources a,b] [--offline]
         python run.py build
         python run.py all     (harvest -> verify -> build)
         python run.py fixtures   (offline dry run on bundled sample data; proves the pipeline end to end)
"""
import argparse, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harvest, verify, build

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["harvest", "stamp", "verify", "build", "all", "fixtures"])
    ap.add_argument("--sources", default="")
    ap.add_argument("--radical-limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offline", action="store_true", help="stamp everything V1 without network (dry runs only)")
    a = ap.parse_args()
    srcs = [s for s in a.sources.split(",") if s] or None
    if a.cmd == "fixtures":
        shutil.copy(os.path.join("fixtures", "catalog.jsonl"), os.path.join("data", "catalog.jsonl"))
        a.offline = True; a.cmd = "all"; srcs = []
    if a.cmd == "stamp":
        stamp(); return
    if a.cmd in ("harvest", "all") and srcs != []:
        harvest.run(srcs or harvest.ALL_SOURCES, a.radical_limit)
    if a.cmd in ("verify", "all"):
        if a.offline:
            offline_stamp()
        else:
            verify.run(force=a.force, limit=a.limit, sources=srcs)
    if a.cmd in ("build", "all"):
        x, h, counts = build.run()
        print(json.dumps({"xlsx": x, "html": h, "chapter_status": counts}, indent=2))

def stamp():
    """Publish freshly harvested entries without waiting for the slow link check:
    entries already checked keep their tier; new ones are V1 (publisher-issued, not opened yet);
    placeholders with no link stay PENDING. `python run.py verify` upgrades/rejects them later."""
    old = {}
    if os.path.exists(verify.VERIFIED):
        for l in open(verify.VERIFIED, encoding="utf-8"):
            e = json.loads(l)
            if e.get("url"): old[e["url"]] = e
    keep = ("tier", "verify_note", "verified_at", "fetched_title", "primary_url")
    out = []
    for l in open(harvest.CATALOG, encoding="utf-8"):
        e = json.loads(l)
        if not e.get("url"):
            e.update({"tier": "PENDING", "primary_url": ""})
        elif e["url"] in old and old[e["url"]].get("tier"):
            e.update({k: old[e["url"]].get(k, "") for k in keep})
        else:
            e.update({"tier": "V1", "verify_note": "publisher feed; link not opened yet", "verified_at": "",
                      "fetched_title": "", "primary_url": e["url"]})
        out.append(e)
    with open(verify.VERIFIED, "w", encoding="utf-8") as f:
        for e in out: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    from collections import Counter
    from classify import remap
    for e in out: remap(e)  # current passage + speaker rules
    with open(verify.VERIFIED, "w", encoding="utf-8") as f:
        for e in out: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print("[stamp]", len(out), "entries", dict(Counter(e["tier"] for e in out)))

def offline_stamp():
    entries = [json.loads(l) for l in open(harvest.CATALOG, encoding="utf-8")]
    with open(verify.VERIFIED, "w", encoding="utf-8") as f:
        for e in entries:
            e.update({"tier": "V1", "verify_note": "offline dry run — not checked", "verified_at": "", "fetched_title": "", "primary_url": e["url"]})
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print("[verify] offline: stamped", len(entries), "entries V1")

if __name__ == "__main__":
    main()
