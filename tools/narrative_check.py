"""Check the narrator's book and chapter introductions (data/narrative/<abbr>.txt, see data/narrative/STYLE.md).

    python3 tools/narrative_check.py            every book written so far
    python3 tools/narrative_check.py Exo Lev    these books

Reports missing or extra chapters, lengths (about 160 spoken words a minute), and things that read badly aloud
or break the style guide: digits, brackets, abbreviations, headings, stock phrases."""
import glob, os, re, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from canon import BOOKS

WPM = 160
BAN = [r"\bin this chapter,? we\b", r"\blet'?s dive\b", r"\bdelve", r"\btapestry", r"\ba testament to\b", r"\bit'?s worth noting\b",
       r"\bpivotal\b", r"\bsets the stage\b", r"\bbuckle up\b", r"\blittle did\b", r"\bshocking\b", r"\bincredible\b",
       r"\b(spiritual|faith|our|this) journey\b|\bjourney (with god|of faith)\b", r"\bwe (too|also) (must|should|need)\b",
       r"\bas believers\b", r"\bfor us today\b", r"\bin our lives\b", r"\bapplication\b", r"\blessons? (for|from) (us|this)\b"]


def sections(abbr):
    files = sorted(glob.glob(os.path.join(HERE, "data", "narrative", f"{abbr}.txt")) + glob.glob(os.path.join(HERE, "data", "narrative", f"{abbr}.[0-9].txt")))
    out, dup = {}, []
    for f in files:
        parts = re.split(r"^=== *(\S+) *\n", open(f, encoding="utf-8").read(), flags=re.M)
        for k, v in zip(parts[1::2], parts[2::2]):
            if k in out: dup.append(k)
            out[k] = v.strip()
    return out, dup, files


def check(abbr):
    name, n = next((b[0], b[2]) for b in BOOKS if b[1] == abbr)
    s, dup, files = sections(abbr)
    if not files: return None
    probs = []
    want = ["intro"] + [str(c) for c in range(1, n + 1)]
    missing = [k for k in want if k not in s or not s[k]]
    extra = [k for k in s if k not in want]
    if missing: probs.append(f"missing: {', '.join(missing[:20])}{' ...' if len(missing) > 20 else ''}")
    if extra: probs.append(f"unexpected sections: {extra}")
    if dup: probs.append(f"written twice: {dup}")
    words = {k: len(v.split()) for k, v in s.items()}
    if "intro" in words:
        lo = 250 if n <= 5 else 550
        if not lo <= words["intro"] <= 1050: probs.append(f"intro is {words['intro']} words (aim 650-900; small books may be shorter)")
    for k, v in s.items():
        if k == "intro": continue
        if not 60 <= words[k] <= 260: probs.append(f"chapter {k}: {words[k]} words (aim 110-190)")
        for pat, why in ((r"\d", "a digit (write numbers in words)"), (r"[()\[\]]", "brackets"), (r"\b(BC|AD|B\.C\.|A\.D\.|c\.|ca\.|cf\.|e\.g\.|i\.e\.|v\.|vv\.)(?=\W)", "an abbreviation"),
                         (r"^\s*(#|\*|-\s)", "a heading or bullet"), (r"—.*—", "an em-dash pair")):
            if re.search(pat, v, re.M): probs.append(f"chapter {k}: {why}")
    for k, v in s.items():
        for b in BAN:
            m = re.search(b, v, re.I)
            if m: probs.append(f"{k}: stock phrase '{m.group(0)}'")
    ch = [words[str(c)] for c in range(1, n + 1) if str(c) in words]
    spoken = sum(words.values()) / WPM
    print(f"{abbr:4} {name:16} intro {words.get('intro', 0):4} words ({words.get('intro', 0) / WPM:.1f} min) | {len(ch)}/{n} chapters, "
          f"avg {sum(ch) // max(1, len(ch))} words ({sum(ch) / max(1, len(ch)) / WPM * 60:.0f} s) | {spoken:.0f} min spoken")
    for p in probs: print("   -", p)
    return not probs


DEBATE = re.compile(r"debat|\b(many|some|most|modern|other|few) scholars\b|\bscholars\b(?! translated)|\bscholarly|"
                    r"interpreters|commentators|\bsome (readers|think|believe|suggest|have (suggested|seen|wondered|thought|argued)|take|see|hold|prefer|identify|link|connect)\b|"
                    r"\bothers (think|read|take|see|suggest|hold|prefer|believe)\b|\buncertain|\bnot certain|\bunclear\b|\bdisputed|\bno one (knows|can say)|"
                    r"\b(views?|opinions?|readings?) (differ|vary)|\bin different ways\b|\blong (been )?(debated|weighed|wondered|discussed|puzzled)|"
                    r"\bwe (cannot|can't|do not|don't) (be sure|know|tell)|\bcannot be (sure|certain|identified|located|settled)|\bthe question of\b|"
                    r"\bhard to (say|know|date|fit)\b|\bremains? a puzzle|\bpossibly\b|\bperhaps\b|\bprobably\b|\bmost likely\b|\bit seems\b|\bseems to\b|\bmay have been\b|\btraditionally\b|\bhypothes", re.I)


def debate(abbr):
    """Every sentence that reports a debate, an uncertainty or a hedge (some are fine in context: Jesus' 'no one knows the day')."""
    s, _, files = sections(abbr)
    n = 0
    for k, v in s.items():
        for sent in re.split(r"(?<=[.!?])\s+", v):
            if DEBATE.search(sent):
                n += 1; print(f"{abbr} {k}: {sent}")
    return n


if __name__ == "__main__":
    if sys.argv[1:2] == ["--debate"]:
        tot = sum(debate(a) for a in (sys.argv[2:] or [b[1] for b in BOOKS])); print(f"\n{tot} sentences to look at"); sys.exit()
    want = sys.argv[1:] or [b[1] for b in BOOKS]
    res = [check(a) for a in want]
    done = [r for r in res if r is not None]
    print(f"\n{len(done)} books written, {sum(1 for r in done if r)} with no problems")
