"""Add Stephen Davey sermon lists from a research spreadsheet (columns: Bible book / group, Series, Order, Sermon title, Scripture
passage, Date, ...) to data/davey_archive/<series>.json. Books already read from their own series-page PDFs are left alone.

    python3 tools/davey_xlsx.py FILE.xlsx
"""
import json, os, re, sys
from datetime import date
import openpyxl
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main(path):
    rows = list(openpyxl.load_workbook(path, read_only=True)["Sermon Records"].iter_rows(values_only=True))
    head = [str(h or "").strip().lower() for h in rows[0]]
    col = lambda name: next(i for i, h in enumerate(head) if h.startswith(name))
    by = {}
    for r in rows[1:]:
        if not r[col("series")]: continue
        by.setdefault(r[col("series")], []).append(r)
    for series, L in by.items():
        slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"^sermons in\s*", "", series.lower()).replace("&", "and")).strip("-")
        p = os.path.join(HERE, "data", "davey_archive", slug + ".json")
        if os.path.exists(p) and json.load(open(p)).get("from") != "spreadsheet":
            print(f"{slug}: already from its series page, left alone"); continue
        old = {x["n"]: x for x in (json.load(open(p))["sermons"] if os.path.exists(p) else [])}
        out = []
        for r in sorted(L, key=lambda r: int(r[col("order")] or 0)):
            n = int(r[col("order")]); d = r[col("date")]
            try: ds = date.fromisoformat(str(d)[:10]).strftime("%B %-d, %Y") if d else ""
            except ValueError: ds = ""
            passage = (r[col("scripture")] or "").strip()
            x = {"n": n, "title": f"{r[col('sermon title')].strip()} ({passage})" if passage else r[col("sermon title")].strip(),
                 "name": r[col("sermon title")].strip(), "title_passage": passage, "ref": passage, "date": ds, "speaker": r[col("speaker")] or "Stephen Davey", "series": series}
            o = old.get(n)
            if o and o.get("name") == x["name"]: x.update({k: v for k, v in o.items() if k in ("mp3", "tried")})
            out.append(x)
        json.dump({"series": series, "slug": slug, "from": "spreadsheet", "sermons": out}, open(p, "w"), indent=1, ensure_ascii=False)
        print(f"{slug}: {len(out)} sermons -> {os.path.relpath(p, HERE)}")

if __name__ == "__main__":
    main(sys.argv[1])
