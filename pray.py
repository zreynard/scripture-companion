"""The Pray tab's guided prayer: the Lord's Prayer (Matthew 6:9-13, Berean Standard Bible) in six movements, each with
a short instruction and a set of supporting passages that rotate between prayer times. Every word of Scripture is
read from data/bible (the app's own text), never typed by hand; "a"/"b" refs keep only the first/last sentence."""
import json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
_B = {}
def _ch(book, c):
    book = {"Psalm": "Psalms"}.get(book, book)
    if book not in _B: _B[book] = json.load(open(os.path.join(HERE, "data", "bible", f"{book}.json"), encoding="utf-8"))["chapters"]
    return _B[book][c - 1]
def clean(t): return re.sub(r"\s+", " ", t.replace("\n", " ")).strip()
def text(ref):
    m = re.match(r"^(.+?) (\d+):(\d+)([ab]?)(?:-(\d+)([ab]?))?$", ref)
    book, c, v1, p1, v2, p2 = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), int(m.group(5) or m.group(3)), m.group(6)
    vs = [clean(v["t"]) for v in _ch(book, c) if v1 <= v["v"] <= v2]
    sent = lambda s: re.split(r"(?<=[.!?;:’”])\s+(?=[A-Z‘“])", s)
    if book in ("Psalm", "Psalms") and v1 == 1:   # the psalm's heading ("A Psalm of David.") is not part of the prayer
        ss = sent(vs[0])
        while len(ss) > 1 and re.match(r"^(A |An )?(Psalm|psalm|Song|song|Maskil|Miktam|Prayer|prayer)\b|^Of |^For the choirmaster|^According to|^To the|^With stringed|^For the director", ss[0]): ss = ss[1:]
        vs[0] = " ".join(ss)
    if p1 == "b": vs[0] = sent(vs[0])[-1]
    if (p2 or p1) == "a": vs[-1] = sent(vs[-1])[0]
    t = re.sub(r"\s+Selah$", "", " ".join(vs))
    if t.count("“") > t.count("”"): t += "”"      # the quotation runs on past the excerpt
    if t.count("”") > t.count("“"): t = "“" + t    # the excerpt starts inside a quotation
    return t
# The Lord's Prayer lines (from Matthew 6:9-13 in the app's text) and the movements built on them
MOVES = [
 {"k": "near", "label": "Draw near", "lp": ("Matthew 6:9", "Our Father in heaven,"), "ins": "Come before your Father.",
  "sup": ["James 4:8a", "Hebrews 4:16", "Romans 8:15", "Galatians 4:6", "Ephesians 2:18", "Hebrews 10:22a", "Psalm 145:18",
          "Matthew 6:6", "Jeremiah 29:12-13", "1 John 3:1a", "John 14:6"]},
 {"k": "worship", "label": "Worship", "lp": ("Matthew 6:9", "hallowed be Your name."), "ins": "Praise God for who He is.",
  "sup": ["Psalm 103:1", "Psalm 145:3", "Revelation 4:11", "Psalm 96:4", "Psalm 29:2", "Isaiah 6:3", "Psalm 95:6",
          "Psalm 34:3", "1 Chronicles 29:11", "Psalm 86:10", "John 4:24", "Psalm 63:3"]},
 {"k": "kingdom", "label": "Your kingdom", "lp": ("Matthew 6:10", None), "ins": "Seek His reign, and yield your will to His.",
  "sup": ["Matthew 6:33", "Luke 22:42", "Proverbs 3:5-6", "Romans 12:1", "Psalm 40:8", "Mark 1:15", "Luke 12:32",
          "Romans 14:17", "Psalm 145:13a", "Psalm 143:10", "Colossians 1:13", "Matthew 13:44"]},
 {"k": "bread", "label": "Daily bread", "lp": ("Matthew 6:11", None), "ins": "Depend on God for your needs, and on Christ for life.",
  "sup": ["John 6:35", "Deuteronomy 8:3", "Philippians 4:6-7", "Philippians 4:19", "Matthew 7:11", "Psalm 145:15-16",
          "1 Peter 5:7", "Psalm 23:1", "James 1:5", "John 6:51a", "Matthew 6:31-32"]},
 {"k": "forgive", "label": "Forgive", "lp": ("Matthew 6:12", None), "ins": "Confess your sins, and forgive others.",
  "sup": ["1 John 1:9", "Psalm 51:10", "Ephesians 4:32", "Colossians 3:13", "Psalm 32:5", "Psalm 103:12", "Matthew 6:14",
          "Psalm 139:23-24", "Micah 7:18", "Isaiah 1:18", "Mark 11:25"]},
 {"k": "deliver", "label": "Deliver us", "lp": ("Matthew 6:13", None), "ins": "Ask for His strength and protection.",
  "sup": ["1 Corinthians 10:13", "2 Thessalonians 3:3", "Ephesians 6:10-11", "Romans 8:26", "Psalm 91:1-2", "James 4:7",
          "Psalm 121:7-8", "1 Peter 5:8", "John 17:15", "Matthew 26:41", "Psalm 46:1"]},
]
def build():
    out = []
    for m in MOVES:
        ref, part = m["lp"]
        full = text(ref).replace("So then, this is how you should pray: ", "").strip("‘’ ")
        lp = part if part else full
        assert part is None or part in full, (part, full)
        sup = [{"r": r, "t": text(r)} for r in m["sup"]]
        out.append({"k": m["k"], "label": m["label"], "lp": lp, "lpr": ref, "ins": m["ins"], "sup": sup})
    return out
if __name__ == "__main__":
    for m in build():
        print(f"\n== {m['label']}: {m['lp']} ({m['lpr']}) — {m['ins']}")
        for s in m["sup"]: print(f"   [{len(s['t'].split()):2}] {s['r']}: {s['t']}")
