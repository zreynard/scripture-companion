"""Read a Wisdom International teaching-series page saved as a PDF (Safari's Share > PDF or Print) into a list of sermons:
lesson number (its place in the list), title, the passage in the title, the page's Scripture reference, and the date.

    python3 tools/davey_pdf.py FILE.pdf [...]   -> data/davey_archive/<series-slug>.json (merged with what is there)
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def text_of(pdf):
    t = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    t = re.sub(r"[\ue000-\uf8ff]", " ", t)
    keep = []
    for line in t.splitlines():
        s = line.strip()
        if re.match(r"^https?://\S+", s) or re.search(r"Page \d+ of \d+$", s) or len(s) <= 2 or s == "Back to Teaching Series":
            continue
        keep.append(s)
    t = re.sub(r"\s+", " ", " ".join(keep))
    return re.sub(r"(?<=\d{4}) [A-Za-z:] (?=Scripture Reference)|(?<=\S) [:gs] (?=[A-Z(])", " ", t)   # a stray letter from the page edge


def parse(pdf):
    """Each sermon on the page ends with "Series: <name>": split there, then read title, speaker, date and reference."""
    t = text_of(pdf).replace("Back to Teaching Series", " ").strip()
    m = re.search(r"Series: (.+?)(?=\s+\S)", t)
    names = re.findall(r"Series: ((?:Sermons in |Topic: )?[A-Z0-9][A-Za-z0-9&',.:-]*(?: [A-Z0-9&][A-Za-z0-9&',.:-]*)*)", t)
    series = max(set(names), key=names.count) if names else os.path.basename(pdf)
    blocks = [b.strip() for b in t.split("Series: " + series)]
    head = blocks[0]
    if head.startswith(series): blocks[0] = head[len(series):].strip()   # the page heading repeats the series name
    out = []
    FOREIGN = re.compile(r"[ãõçêâáéíóúñ¿¡]|\b(?:e|de|da|do|dos|das|la|el|los|las|y|que|para|uma?|um)\b", re.I)
    for blk in blocks:
        if not blk: continue
        mm = re.match(rf"^(.*?)\s*(?:By ([A-Z][A-Za-z.]+(?: [A-Z][A-Za-z.]+)+)\s*)?· ((?:{MONTHS}) \d{{1,2}}, \d{{4}})\s*(?:Scripture Reference: (.*))?$", blk)
        if not mm: continue
        title, who, date, ref = (x.strip() if x else "" for x in mm.groups())
        title = re.sub(r"^[^A-Za-z0-9(]+", "", title)
        if title.startswith(series): title = title[len(series):].strip()
        if "(" not in title and len(FOREIGN.findall(title)) >= 1 and not re.search(r"\b(the|and|of|a|to|in)\b", title, re.I): continue  # a translation listed with the English
        tp = re.search(r"\(([^)]*)\)", title)
        out.append({"n": len(out) + 1, "title": re.sub(r"\s+", " ", title), "name": re.sub(r"\s*\([^)]*\)\s*", " ", title).strip(),
                    "title_passage": tp.group(1).strip() if tp else "", "ref": ref, "date": date, "speaker": who or "Stephen Davey", "series": series})
    return series, out


if __name__ == "__main__":
    for pdf in sys.argv[1:]:
        series, L = parse(pdf)
        slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"^(sermons in|series:|topic:)\s*", "", series.lower())).strip("-")
        p = os.path.join(HERE, "data", "davey_archive", slug + ".json")
        key = lambda x: (re.sub(r"[^a-z0-9]+", "", x["title"].lower()), x["date"])
        old = {key(x): x for x in (json.load(open(p))["sermons"] if os.path.exists(p) else [])}
        for x in L:   # audio already found stays with its sermon (matched by title and date), never by position
            o = old.get(key(x))
            if o and o["n"] == x["n"]: x.update({k: v for k, v in o.items() if k in ("mp3", "tried")})
        json.dump({"series": series, "slug": slug, "sermons": L}, open(p, "w"), indent=1, ensure_ascii=False)
        print(f"{slug}: {len(L)} sermons -> {os.path.relpath(p, HERE)}")
        for x in L[:3] + L[-2:]: print("   ", x["n"], "|", x["title"][:60], "|", x["ref"], "|", x["date"], "|", x["speaker"])
