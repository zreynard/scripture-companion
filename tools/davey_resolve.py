"""Find each Stephen Davey sermon's audio on Wisdom International's media server, from the lesson number and passage its series
page publishes (data/davey_archive/<series>.json, made by tools/davey_pdf.py). Files are named <Series><NN>-<Book><passage>.mp3,
e.g. Genesis08-Genesis6_1-9_17.mp3: a few candidate names per sermon, each checked with one tiny request. Runs on GitHub."""
import glob, json, os, re, time, requests
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)", "Range": "bytes=0-1"}
B = "https://wisdomonline-a.atl1.cdn.digitaloceanspaces.com/"
ABBR = {"Gen": "Genesis", "Ex": "Exodus", "Lev": "Leviticus", "Num": "Numbers", "Deut": "Deuteronomy", "Josh": "Joshua", "Judg": "Judges", "Ruth": "Ruth",
        "1 Sam": "1Samuel", "2 Sam": "2Samuel", "1 Kgs": "1Kings", "2 Kgs": "2Kings", "1 Chr": "1Chronicles", "2 Chr": "2Chronicles", "Ezra": "Ezra", "Neh": "Nehemiah",
        "Esth": "Esther", "Job": "Job", "Ps": "Psalm", "Psalms": "Psalms", "Prov": "Proverbs", "Eccl": "Ecclesiastes", "Song": "Song", "Isa": "Isaiah", "Jer": "Jeremiah", "Lam": "Lamentations",
        "Ezek": "Ezekiel", "Dan": "Daniel", "Hos": "Hosea", "Joel": "Joel", "Amos": "Amos", "Obad": "Obadiah", "Jonah": "Jonah", "Mic": "Micah", "Nah": "Nahum", "Hab": "Habakkuk",
        "Zeph": "Zephaniah", "Hag": "Haggai", "Zech": "Zechariah", "Mal": "Malachi", "Matt": "Matthew", "Mark": "Mark", "Luke": "Luke", "John": "John", "Acts": "Acts",
        "Rom": "Romans", "1 Cor": "1Corinthians", "2 Cor": "2Corinthians", "Gal": "Galatians", "Eph": "Ephesians", "Phil": "Philippians", "Col": "Colossians",
        "1 Thess": "1Thessalonians", "2 Thess": "2Thessalonians", "1 Tim": "1Timothy", "2 Tim": "2Timothy", "Titus": "Titus", "Phlm": "Philemon", "Heb": "Hebrews",
        "Jas": "James", "1 Pet": "1Peter", "2 Pet": "2Peter", "1 John": "1John", "2 John": "2John", "3 John": "3John", "Jude": "Jude", "Rev": "Revelation"}


def passages(x):
    """See below; Psalms files may say Psalm or Psalms."""
    return _passages(x) + [(b.replace("Psalms", "Psalm"), p) for b, p in _passages(x) if b == "Psalms"]


def _passages(x):
    """Passage strings as the file names write them: 'Genesis 6:1-9:17' -> ('Genesis', '6_1-9_17'), plus looser forms."""
    out = []
    for raw in (x.get("title_passage", ""), x.get("ref", "")):
        r = raw.replace("–", "-").replace("—", "-").replace(" & ", "&")
        m = re.match(r"^\s*((?:[123] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?)\.?\s+(.*)$", r)
        if not m: continue
        book, rest = m.group(1), m.group(2).split(";")[0].strip()
        book = ABBR.get(book, book.replace(" ", ""))
        rest = re.sub(r"\s*-\s*", "-", rest).replace(" ", "")
        for v in (rest.replace(":", "_"), rest.split("-")[0].replace(":", "_"), rest.split(":")[0].split("-")[0], rest.replace(":", "_").replace("-", "_")):
            out.append((book, v))
    return list(dict.fromkeys(out))


def candidates(prefix, n, x):
    nn = f"{n:02d}" if n < 100 else str(n)
    c = [f"{prefix}{nn}-{b}{p}" for b, p in passages(x)]
    if x.get("ref") == "" or "Introduction" in x.get("title_passage", ""):
        c += [f"{prefix}{nn}-{prefix}1_1", f"{prefix}{nn}-{prefix}1"]
    return list(dict.fromkeys(c))


def prefix_of(series):
    s = re.sub(r"^(Sermons in|Series:|Topic:)\s*", "", series).strip()
    return list(dict.fromkeys([s.replace(" ", ""), s.split()[0], s.replace(" ", "-"), s.replace(" & ", "and").replace(" ", ""), s.replace(" & ", "And").replace(" ", "")]))


def main():
    for f in sorted(glob.glob(os.path.join(HERE, "data", "davey_archive", "*.json"))):
        d = json.load(open(f)); changed = 0
        used = {x["mp3"] for x in d["sermons"] if x.get("mp3")}
        for x in d["sermons"]:
            if x.get("mp3") or x.get("tried", 0) >= 3: continue
            hit = None
            # a list made from another source can number the lessons a few places off: the series' own number first, then nearby
            # the offsets this series' found files already show (file number minus list number), most common first
            seen = {}
            for y in d["sermons"]:
                m = re.search(r"/[A-Za-z0-9&-]*?(\d+)-", y.get("mp3") or "")
                if m: seen[int(m.group(1)) - y["n"]] = seen.get(int(m.group(1)) - y["n"], 0) + 1
            learned = [o for o, _ in sorted(seen.items(), key=lambda kv: -kv[1])]
            offs = list(dict.fromkeys([0] + learned + ([1, -1, 2, -2, 3, -3] if x.get("tried", 0) >= 1 or d.get("from") == "spreadsheet" else [])))[:7]
            budget = [40]
            pres = list(dict.fromkeys(prefix_of(d["series"])[:2] + [b for b, _ in passages(x)][:2]))
            for off in offs:
                if x["n"] + off < 1: continue
                for pre in pres:
                    for c in candidates(pre, x["n"] + off, x)[:4]:
                        u = B + c + ".mp3"
                        if u in used: continue
                        if budget[0] <= 0: break
                        budget[0] -= 1
                        r = requests.get(u, headers=H, timeout=30)
                        if r.status_code in (200, 206): hit = u; break
                        time.sleep(0.03)
                    if hit: break
                if hit: break
            if hit: used.add(hit)
            if hit: x["mp3"] = hit
            else: x["tried"] = x.get("tried", 0) + 1
            changed += 1
        json.dump(d, open(f, "w"), indent=1, ensure_ascii=False)
        print(f"{d['slug']}: {sum(1 for x in d['sermons'] if x.get('mp3'))} of {len(d['sermons'])} found", flush=True)
        for x in d["sermons"]:
            if not x.get("mp3"): print("   not found:", x["n"], x["title"][:60], "|", x["ref"])


if __name__ == "__main__":
    main()
