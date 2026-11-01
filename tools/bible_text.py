"""Build the Bible text for the app from the Berean Standard Bible (public domain) USFM files.

python tools/bible_text.py [path-or-url-to-bsb_usfm.zip] [path-or-url-to-bsb.txt]
Writes data/bible/<Book>.json, one per book:
  {"book": "Genesis", "chapters": [[{"v": 1, "t": "In the beginning...", "h": "The Creation", "p": 1, "q": 0}, ...], ...]}
  v = verse number, t = text (poetry lines separated by \\n), h = section heading that opens before this verse,
  p = verse starts a paragraph, q = poetry indent level, d = psalm title (on verse 1).
The result is checked word for word against the official plain-text bsb.txt; nothing is written if any verse differs.
"""
from __future__ import annotations
import io, json, os, re, sys, urllib.request, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from canon import BOOKS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "bible")
USFM_URL = "https://bereanbible.com/bsb_usfm.zip"
TXT_URL = "https://bereanbible.com/bsb.txt"
CODES = ["GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST",
         "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON", "MIC", "NAM",
         "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL",
         "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"]
NAME = {code: b[0] for code, b in zip(CODES, BOOKS)}
HEADINGS = {"s", "s1", "s2", "s3", "ms", "ms1", "ms2", "mr", "sr", "r", "sp", "mt", "mt1", "mt2", "mt3", "h", "toc1", "toc2",
            "toc3", "ide", "rem", "cl", "sts", "usfm", "cd"}
PARAS = {"p", "m", "pi", "pi1", "pi2", "nb", "li", "li1", "li2", "pmo", "pc", "pr", "pm", "pmc", "mi", "cls", "pmr", "ph", "ph1"}

def strip_notes(s: str) -> str:
    s = re.sub(r"\\f .*?\\f\*", "", s)                     # footnotes
    s = re.sub(r"\\fe .*?\\fe\*", "", s)
    s = re.sub(r"\\x .*?\\x\*", "", s)                     # cross references
    s = re.sub(r"\\\+?w ([^|\\]*)(\|[^\\]*)?\\\+?w\*", r"\1", s)  # word-level markup keeps the word
    return s

def parse(usfm: str):
    chapters, cur = [], None
    st = {"h": None, "p": False, "q": 0, "d": None, "brk": None}   # pending heading / paragraph / poetry / title / break
    def text_to_verse(t: str):
        t = re.sub(r"\\\+?[a-z]+\d*\*?", "", t)                   # character markers (\wj \add \nd \qs ...) keep their text
        t = re.sub(r"\s+", " ", t).strip()
        if not t or cur is None or not cur:
            return
        v = cur[-1]
        if v["t"]:
            v["t"] += ("\n" if st["brk"] == "q" else " ") + t
        else:
            v["t"] = t
        st["brk"] = None; st["p"] = False   # a break inside a verse does not carry to the next verse
    for raw in usfm.splitlines():
        line = strip_notes(raw.strip())
        if not line:
            continue
        m = re.match(r"\\(\w+)\s?(.*)", line)
        tag = m.group(1) if m else None
        if tag == "c":
            cur = []; chapters.append(cur); st.update(h=None, p=True, q=0, d=None, brk=None); continue
        if tag in ("s", "s1", "s2", "s3", "ms", "ms1", "ms2"):
            st["h"] = re.sub(r"\\\+?[a-z]+\d*\*?", "", m.group(2)).strip() or st["h"]; continue
        if tag == "d":
            st["d"] = re.sub(r"\\\+?[a-z]+\d*\*?", "", m.group(2)).strip(); continue
        if tag in HEADINGS or tag in ("id", "b", "ie", "ip", "is", "is1"):
            continue
        # tokenize the line on structural markers; text between them belongs to the current verse
        for tok in re.split(r"(\\(?:v \d+(?:-\d+)?|q\d?|qm\d?|qc|qr|qa|" + "|".join(sorted(PARAS, key=len, reverse=True)) + r")\b\s?)", line):
            if not tok:
                continue
            mv = re.match(r"\\v (\d+)(?:-\d+)?\s?$", tok)
            if mv:
                v = {"v": int(mv.group(1)), "t": ""}
                if st["h"]: v["h"] = st["h"]; st["h"] = None
                if st["p"]: v["p"] = 1; st["p"] = False
                if st["q"]: v["q"] = st["q"]
                if st["d"]: v["d"] = st["d"]; st["d"] = None
                if cur is not None: cur.append(v)
                st["brk"] = None
                continue
            mq = re.match(r"\\(q\d?|qm\d?|qc|qr|qa)\s?$", tok)
            if mq:
                st["q"] = int(re.sub(r"\D", "", mq.group(1)) or 1); st["p"] = True; st["brk"] = "q"; continue
            mp = re.match(r"\\(\w+)\s?$", tok)
            if mp and mp.group(1) in PARAS:
                st["q"] = 0; st["p"] = True; st["brk"] = "p"; continue
            text_to_verse(tok)
    return chapters

def load(src):
    return urllib.request.urlopen(src).read() if src.startswith("http") else open(src, "rb").read()

def main():
    usfm_src = sys.argv[1] if len(sys.argv) > 1 else USFM_URL
    txt_src = sys.argv[2] if len(sys.argv) > 2 else TXT_URL
    z = zipfile.ZipFile(io.BytesIO(load(usfm_src)))
    books = {}
    for name in z.namelist():
        if not name.lower().endswith((".usfm", ".sfm")):
            continue
        text = z.read(name).decode("utf-8-sig")
        code = re.search(r"\\id (\w+)", text).group(1).upper()
        if code in NAME:
            books[NAME[code]] = parse(text)
    # check against the official plain text, word for word
    plain = {}
    alias = {"Psalm": "Psalms", "Song of Songs": "Song of Solomon"}
    for line in load(txt_src).decode("utf-8-sig").splitlines():
        m = re.match(r"(.+?) (\d+):(\d+)\t(.*)", line)
        if m:
            plain[(alias.get(m.group(1), m.group(1)), int(m.group(2)), int(m.group(3)))] = m.group(4).strip()
    mine = {(b, ci, v["v"]): v["t"] for b, chs in books.items() for ci, ch in enumerate(chs, 1) for v in ch}
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    missing = [k for k in plain if k not in mine]
    extra = [k for k in mine if k not in plain]
    differ = [k for k in plain if k in mine and norm(plain[k]) != norm(mine[k])]
    counts = [f"{b}: {len(chs)} ch, expected {n}" for b, _, n, _, _ in BOOKS for chs in [books.get(b, [])] if len(chs) != n]
    print(f"books {len(books)} | verses {len(mine)} (official {len(plain)}) | missing {len(missing)} | extra {len(extra)} | wording differs {len(differ)}")
    for k in (missing[:5] + extra[:5]): print("   ", k)
    for k in differ[:5]: print("   ", k, "\n      official:", plain[k][:110], "\n      built   :", mine[k][:110])
    for c in counts: print("   ", c)
    if len(books) != 66 or missing or extra or differ or counts:
        sys.exit("not written: the build does not match the official text")
    os.makedirs(OUT, exist_ok=True)
    for b, chs in books.items():
        json.dump({"book": b, "chapters": chs}, open(os.path.join(OUT, f"{b}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
    print("written: data/bible/ (66 books, matches the official text exactly)")

if __name__ == "__main__":
    main()
