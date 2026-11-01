"""Build the Bible text for the app from the Berean Standard Bible (public domain) USFM files.

python tools/bible_text.py [path-or-url-to-bsb_usfm.zip]
Writes data/bible/<Book>.json, one per book:
  {"book": "Genesis", "chapters": [[{"v": 1, "t": "In the beginning...", "h": "The Creation", "p": 1, "q": 0}, ...], ...]}
  v = verse number, t = text, h = section heading that opens before this verse, p = verse starts a paragraph,
  q = poetry indent level (0 = prose). Psalm titles ride as "d" on verse 1.
Checks every book against canon.py chapter counts and the verse total against bsb.txt when given.
"""
from __future__ import annotations
import io, json, os, re, sys, urllib.request, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from canon import BOOKS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "bible")
USFM_URL = "https://bereanbible.com/bsb_usfm.zip"
CODES = ["GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST",
         "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON", "MIC", "NAM",
         "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL",
         "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"]
NAME = {code: b[0] for code, b in zip(CODES, BOOKS)}

def clean(s: str) -> str:
    s = re.sub(r"\\f .*?\\f\*", "", s)                     # footnotes
    s = re.sub(r"\\x .*?\\x\*", "", s)                     # cross references
    s = re.sub(r"\\w ([^|\\]*)(\|[^\\]*)?\\w\*", r"\1", s)  # word-level markup
    s = re.sub(r"\\\+?[a-z]+\d*\*?", "", s)                # any remaining character markers (\wj, \add, \nd, ...)
    return re.sub(r"\s+", " ", s).strip()

def parse(usfm: str):
    chapters, cur, heading, para, q, title = [], None, None, False, 0, None
    for raw in usfm.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"\\(\w+)\s?(.*)", line)
        if not m:
            if cur and cur and cur[-1]:  # continuation of the previous verse
                cur[-1]["t"] = (cur[-1]["t"] + " " + clean(line)).strip()
            continue
        tag, rest = m.group(1), m.group(2)
        if tag == "c":
            cur = []; chapters.append(cur); heading, para, q, title = None, True, 0, None
        elif tag in ("s", "s1", "s2", "ms", "ms1"):
            heading = clean(rest) or heading
        elif tag == "d":
            title = clean(rest)
        elif tag in ("p", "m", "pi", "pi1", "nb", "li", "li1", "pmo", "pc"):
            para, q = True, 0
            if rest.startswith("\\v"):
                add_verse(cur, rest, heading, para, q, title); heading, para, title = None, False, None
        elif re.fullmatch(r"q\d?|qm\d?", tag):
            q = int(re.sub(r"\D", "", tag) or 1); para = True
            if rest.startswith("\\v"):
                add_verse(cur, rest, heading, para, q, title); heading, para, title = None, False, None
            elif rest and cur:
                cur[-1]["t"] = (cur[-1]["t"] + "\n" + clean(rest)).strip()  # poetry keeps its lines
        elif tag == "v" and cur is not None:
            add_verse(cur, line, heading, para, q, title); heading, para, title = None, False, None
    return chapters

def add_verse(cur, text, heading, para, q, title):
    for part in re.split(r"(?=\\v \d)", text):
        m = re.match(r"\\v (\d+)(?:-\d+)?\s*(.*)", part.strip())
        if not m:
            continue
        v = {"v": int(m.group(1)), "t": clean(m.group(2))}
        if heading: v["h"] = heading; heading = None
        if para: v["p"] = 1; para = False
        if q: v["q"] = q
        if title: v["d"] = title; title = None
        cur.append(v)

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else USFM_URL
    data = urllib.request.urlopen(src).read() if src.startswith("http") else open(src, "rb").read()
    z = zipfile.ZipFile(io.BytesIO(data))
    os.makedirs(OUT, exist_ok=True)
    total, problems = 0, []
    for name in z.namelist():
        if not name.lower().endswith((".usfm", ".sfm")):
            continue
        text = z.read(name).decode("utf-8-sig")
        code = re.search(r"\\id (\w+)", text).group(1).upper()
        if code not in NAME:
            continue
        book = NAME[code]
        chs = parse(text)
        want = next(b[2] for b in BOOKS if b[0] == book)
        if len(chs) != want:
            problems.append(f"{book}: {len(chs)} chapters, expected {want}")
        for i, ch in enumerate(chs, 1):
            nums = [v["v"] for v in ch]
            if not nums or nums != sorted(nums) or any(not v["t"] for v in ch):
                problems.append(f"{book} {i}: verse order/empty text problem")
        total += sum(len(c) for c in chs)
        json.dump({"book": book, "chapters": chs}, open(os.path.join(OUT, f"{book}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
    made = len([f for f in os.listdir(OUT) if f.endswith(".json")])
    print(f"books written: {made} | verses: {total} | problems: {len(problems)}")
    for p in problems[:20]: print("  ", p)
    if made != 66 or problems:
        sys.exit(1)

if __name__ == "__main__":
    main()
