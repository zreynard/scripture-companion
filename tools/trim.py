"""Where the teaching starts and ends in every recording on the road, found by listening to each one's opening and
closing (speech recognition with word times). Cuts only what a publisher adds: music, announcers, sponsor and
fundraising messages, station IDs, podcast hand-offs, outros (thanks for listening, websites, phone numbers, next
time), and silence. A preacher's own opening and closing (welcome, "turn with me to", the closing prayer) stay.

Rules per source come from a survey of each feed (tools/intro_survey.py):
  start = after the sentence holding the LAST intro marker in the first 4 minutes (else the first spoken word);
  end   = at the start of the sentence holding the FIRST outro marker in the last 4 minutes, pulled back to right
          after an "Amen" that ends just before it; with no outro marker, after the last spoken word.
  An "Amen" alone never ends a recording: preachers say it and keep going.

    python tools/trim.py measure SHARD SHARDS   -> trim/<shard>.json   {id: [start, end_before_file_end]}
    python tools/trim.py merge                  -> data/intro_skip/trim_<source>.json and trim_<source>_end.json
Runs on GitHub's servers (ffmpeg + faster-whisper)."""
import glob, json, os, re, subprocess, sys, tempfile, wave
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
WIN = 240          # seconds of the opening / closing listened to
I = re.I

SKIPN = r"sk\w*p\s+h\w+"            # Skip Heitzig, as speech recognition spells it
PLATT = r"(?:david|dave)\s+pl\w+"
COMMON_OUT = [r"thank(s| you)( so much)? for (listening|joining us|tuning in|watching)", r"we hope you('ve| have) enjoyed this",
              r"(see you|join us|tune in|come back)( again)? (next time|next week)\b(?! night)", r"until next time", r"i'?m your host",
              r"for more resources from", r"visit (us )?(online )?at \w", r"\b(www\.|\.org\b|\.com\b|dot org|dot com)"]
RULES = {
    "platt_messages": {
        "start": [r"here(?:'?s| is) " + PLATT + r" with (a|the) (sermon|message)", r"here(?:'?s| is) (david|dave) with (a|the) (sermon|message)",
                  r"you are listening to .{0,60}(podcast|messages)", r"teacher,? " + PLATT, r"listen in as .{0,120}(episode|conversation)",
                  r"let'?s turn to (pastor )?david( now)?,?[^.?!]*[.?!]", r"here(?:'?s| is) (pastor )?(david|dave)[^.?!]{0,30} with (a|the) (sermon|message)( titled)?[^.?!]*[.?!]"],
        "promo": [r"^(well,? )?that'?s it for today'?s episode", r"^i'?m your host", r"^for additional articles", r"follow us on (facebook|instagram)"],
        "end": COMMON_OUT + [r"if you('ve| have) enjoyed this (sermon|message|episode)", r"that'?s it for today'?s episode",
                             r"you can find more episodes", r"for additional articles", r"join us for secret church",
                             r"secret ?church.{0,40}(registration|register)", r"secretchurch", r"urgent ?needs", r"(subscribed|rated|reviewed).{0,40}podcast",
                             r"download the free discussion", r"gender, sexuality, artificial intelligence", r"what does the bible say about all of these",
                             r"your inbox is filled", r"good news is on the way", r"that'?s all for today'?s episode", r"we hope you'?ve enjoyed this week'?s episode"]},
    "radical_message": {"start": [r"here(?:'?s| is) " + PLATT + r" with (a|the) (sermon|message)", r"join me in welcoming (dr\.? )?" + PLATT],
                        "end": COMMON_OUT + [r"secretchurch", r"join us for secret church"]},
    "secret_church_podcast": {"start": [r"this is (the )?secret church \w+,? episode \w+\.?", r"is a resource from radical ?\.? ?net\.?", r"radical ?\.? ?net (forward )?slash \w+\."],
                              "end": [r"thank you for listening", r"you can find more episodes", r"free resources.{0,40}radical"]},
    "mclean_podcast": {"start": [], "end": []},
    "brookhills": {"start": [], "end": []},
    "2819_podcast": {"start": [], "anchor": r"(mighty|majestic|matchless).{0,30}name of (our )?soon[- ]?coming king",
                     "end": [r"give (him|god) (a )?(radical )?praise", r"take the roof off", r"put your hands together", r"on your feet",
                             r"overflow", r"lobby", r"gift for you", r"next steps", r"we don'?t do membership", r"baptism sunday",
                             r"see you next week", r"pray over (all )?the givers", r"every giver"]},
    "street_preachers": {"start": [r"you'?re (listening to|watching) (this episode of )?the street preach\w*", r"we pray you'?re blessed by the content you'?re about to receive",
                                   r"stay locked", r"behind the scenes series", r"pause the podcast", r"pre-?order"],
                         "end": [r"thank you for (watching|tuning in|joining us)", r"if (this|you'?ve|you have).{0,30}(episode|message|ministry).{0,20}(blessing|enjoyed)",
                                 r"like,? (comment,? )?(and )?(share|subscribe)", r"streetpreach", r"invest ?fest", r"next episode",
                                 r"we pray you (are|were) blessed by this content", r"shut off the cameras"]},
    "fearless": {"start": [], "end": [r"let'?s (stand|worship)", r"worship team", r"see you next (week|saturday)", r"announcements?"]},
    "skip_archive": {"start": [r"this is expound\.?", r"interactive, enjoyable,? and congregational", r"grow (in|and) grace and (in )?the knowledge of our lord",
                               r"thank you for listening to this (service|message) from calvary"],
                     "end": [r"thank(s| you)( so much)? for listening to this (service|message|teaching)", r"for more resources from calvary",
                             r"visit (our website at )?(www\.)?calvary", r"prayer ?watch line", r"thank you and god bless",
                             r"this is the end of this message", r"further information on any of our products", r"free catalog", r"toll.?free", r"800 ?-? ?272",
                             r"let'?s stand\b", r"pastors are (down )?(here )?at the front"]},
    "skip_church": {"start": [r"in this message from pastor skip[^.?!]*[.?!]", r"this is expound\.?", r"welcome to calvary church with skip[^.?!]*[.?!]"],
                    "promo": [r"^(we'?ll|we will|we won'?t|you'?ll|you will|and (we'?ll|you'?ll|remember))\b(?!.*\b(turn|bibles?|open)\b)"],
                    "end": [r"thank(s| you)( so much)? for joining us (for|in) (this|today'?s) (message|teaching)", r"for more resources from calvary",
                            r"share your story", r"my ?story at", r"support this bible teaching ministry", r"visit (www\.)?calvary", r"give at calvary"]},
    "skip_connect": {"start": [r"let'?s (dive into|get started with) today'?s (teaching|message) from pastor skip", r"as we join skip( \w+)? for today'?s (teaching|message)",
                               r"now (let'?s turn to|we'?re in) [^.]{0,60} (as we join|with) skip"],
                     "end": [r"thank(s| you) for (listening to|joining us)( today)?( on)? connect", r"that (concludes|wraps up) " + SKIPN, r"that'?s " + SKIPN + r" with a message",
                             r"\b800[- ]?922", r"connect ?with ?sk\w*\.com", r"is a presentation of connection communications", r"(see you|join us|tune in) (next time|tomorrow)"]},
    # Stephen Davey. Both daily shows open with a ministry message ending "Now here's Stephen."
    "davey_journey": {"pre": [r"now,? here'?s stephen\.?"], "gap": (8, 40, 100), "floor": 80,
                      "start": [r"here'?s stephen with today'?s lesson", r"lesson (for you )?called [^.?!]*[.?!]", r"as we open god'?s word( now)?",
                                r"(?<!now )(?<!now, )here'?s stephen\.", r"keep listening to (learn|discover|find out|hear|see)[^.?!]*[.?!]",
                                r"let'?s get started with (your|today'?s) lesson[^.?!]*[.?!]", r"(lesson|message)[^.?!]{0,40} called [^.?!]*[.?!]",
                                r"(thanks|thank you) for joining us (today )?on (this|the) wisdom journey[^.?!]*[.?!]", r"^hello,? and thank you[^.?!]*[.?!]"],
                      "promo": [r"today on the wisdom journey", r"stephen dav\w*,? (president|walks|explores|opens|is)", r"stephen walks us", r"stay tuned", r"^discover", r"^learn why"],
                      "tail": 380, "amen_after": r"be with you all",
                      "end": [r"that was stephen dav", r"thanks for listening to the wisdom journey", r"today'?s lesson (from this wisdom journey )?is called", r"produced by wisdom international",
                              r"did you know that stephen", r"shepherd'?s theological seminary", r"wisdom ?online", r"\b866\b", r"p\.?o\.? box", r"heart to heart", r"join us (back here )?next (time|week)", r"see you then"],
                      "back_gap": (6, 60)},
    "davey_wfth": {"pre": [r"now,? here'?s stephen\.?"], "gap": (8, 55, 105),
                   "start": [r"here'?s stephen\.", r"(here'?s|you'?re) stephen with today'?s message", r"(this|the) message (is )?called [^.?!]*[.?!]", r"stephen called this message[^.?!]*[.?!]",
                             r"stephen'?s teaching from[^.?!]*[.?!]"],
                   "promo": [r"welcome to (this broadcast of )?wisdom for the heart", r"in today'?s message", r"^today,? stephen", r"we'?re currently in a series",
                             r"today on wisdom for the heart", r"thanks for joining us today here on wisdom for the heart", r"^putting jesus"],
                   "start_by": 170, "tail": 320,
                   "end": [r"(here )?on wisdom for the heart", r"you'?re listening to wisdom for the heart", r"thanks for joining us today", r"bible teaching ministry of stephen", r"stephen is the pastor of",
                           r"as we (wrap up|close) today'?s", r"glad you were able to join", r"wisdom ?online", r"\b866\b", r"p\.?o\.? box", r"companion study guide",
                           r"join us (back here )?next time", r"be with us next time", r"office staff",
                           r"shepherd'?s (theological )?seminary", r"\bsts\b", r"before we (end|leave you|close)", r"resources? we have for you", r"a book (that'?s )?based on this series",
                           r"hardback", r"order (yours|that set|the set)", r"that was stephen dav", r"stephen (davey )?is (examining|exploring|taking us|walking us)", r"discount", r"online store", r"free resources tab", r"free of charge", r"smartphone app", r"right back here next time"],
                   "back_gap": (8, 30)},
    "davey_sermons": {"pre": [r"now,? here'?s stephen\.?"], "start": [], "end": []},
}

def words_of(pcm, model):
    segs, _ = model.transcribe(pcm, beam_size=1, language="en", vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or []) if w.word.strip()]

def fetch(url, tail=False, nbytes=4_000_000):
    """Bytes of the opening (or closing) of the file; a whole small file for formats that cannot be read in part."""
    whole = bool(re.search(r"\.(m4a|mp4|m4v)(\?|$)", url, I))
    hdr = {**H, **({"Range": f"bytes=-{nbytes}"} if tail and not whole else {})}
    r = requests.get(url, headers=hdr, timeout=180, stream=True)
    if r.status_code not in (200, 206): raise IOError(f"HTTP {r.status_code}")
    buf = bytearray()
    for ch in r.iter_content(262144):
        buf += ch
        if not whole and not tail and len(buf) > nbytes: break
        if not whole and tail and len(buf) > 3 * nbytes: del buf[:-nbytes]
        if len(buf) > 300_000_000: break
    r.close()
    return bytes(buf if whole else (buf[-nbytes:] if tail else buf)), whole

def decode(data):
    with tempfile.TemporaryDirectory() as d:
        a, w = os.path.join(d, "a"), os.path.join(d, "a.wav")
        open(a, "wb").write(data)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", a, "-ac", "1", "-ar", "16000", w], check=False)
        if not os.path.exists(w): raise IOError("no decode")
        with wave.open(w) as f:
            import numpy as np  # only the measuring machines need it
            return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768

def joined(ws):
    """The words as one lower-case string, with each word's character span."""
    text, spans = "", []
    for k, w in enumerate(ws):
        if text: text += " "
        spans.append((len(text), len(text) + len(w[2]))); text += w[2]
    return text.lower(), spans

def word_at(spans, pos):
    for k, (a, b) in enumerate(spans):
        if b > pos: return k
    return len(spans) - 1

def sentence_end(ws, k):
    """Index of the first word at or after k that ends a sentence."""
    for j in range(k, len(ws)):
        if re.search(r"[.?!]$", ws[j][2]): return j
    return len(ws) - 1

def sentence_start(ws, k):
    j = k
    while j > 0 and not re.search(r"[.?!]$", ws[j - 1][2]): j -= 1
    return j

def after_last(ws, text, spans, pats, lo, hi):
    """Index of the word after the sentence holding the last match (beginning between lo and hi seconds), or None."""
    last = None
    for pat in pats:
        for m in re.finditer(pat, text, I):
            k = word_at(spans, m.end() - 1)
            if lo <= ws[word_at(spans, m.start())][0] <= hi and (last is None or k > last): last = k
    return None if last is None else sentence_end(ws, last) + 1

def find_start(ws, rule):
    if not ws: return 0.0
    text, spans = joined(ws)
    j0 = after_last(ws, text, spans, rule.get("pre", []), 0, 60) or 0            # the ministry/station message
    if rule.get("gap") and j0 < len(ws):                                          # a teaser clip, then music: start after it
        mn, lo, hi = rule["gap"]
        for k in range(max(j0, 1), len(ws)):
            if ws[k][0] - ws[k - 1][1] >= mn and lo <= ws[k][0] <= hi: j0 = k; break
            if ws[k][0] > hi: break
    jp = after_last(ws, text, spans, rule.get("pre", []), 0, 60) or 0
    gapped = j0 > 0 and rule.get("gap") and j0 != jp
    t0 = ws[jp][0] if jp < len(ws) else WIN                    # hand-offs count from the end of the ministry message
    j = after_last(ws, text, spans, rule.get("start", []), t0 if jp else 0, rule.get("start_by", WIN))
    if j is None and gapped and rule.get("floor"):             # teaser, music, then an announcer with no hand-off line
        j = next((k for k in range(j0, len(ws)) if ws[k][0] >= rule["floor"] and (k == 0 or re.search(r"[.?!]$", ws[k - 1][2]))), j0)
    j = j0 if j is None else j
    while j < len(ws) and rule.get("promo"):                                      # announcer sentences before the teacher
        e = sentence_end(ws, j); sent = " ".join(w[2] for w in ws[j:e + 1])
        if ws[j][0] > rule.get("start_by", WIN) or not any(re.search(p, sent, I) for p in rule["promo"]): break
        j = e + 1
    if j >= len(ws): return 0.0
    st = ws[j][0]
    return max(0.0, round(st - 0.3, 1)) if st > 1.5 else 0.0

def find_end(ws, rule, L):
    """Seconds before the end of the window (= end of file) where the teaching stops."""
    if not ws: return 0.0
    text, spans = joined(ws)
    cut = None
    if rule.get("anchor"):
        ms = list(re.finditer(rule["anchor"], text, I))
        if ms:
            k = word_at(spans, ms[-1].end() - 1)
            j = k
            while j < len(ws) - 1 and not re.search(r"(christ|amen)[.,!]?$", ws[j][2], I) and ws[j][0] - ws[k][0] < 12: j += 1
            cut = ws[j][1] + 0.4
    if rule.get("amen_after"):                                  # "...be with you all. Amen." closes the lesson
        ms = list(re.finditer(rule["amen_after"] + r"[.,]?\s+amen", text, I))
        if ms:
            k = word_at(spans, ms[-1].end() - 1); find_end.why = "closing blessing"
            return max(0.0, round(L - (ws[k][1] + 0.7), 1))
    first = None
    find_end.why = "anchor" if cut is not None else ""
    for pat in ([] if cut is not None else rule.get("end", [])):
        for m in re.finditer(pat, text, I):
            k = word_at(spans, m.start())
            if ws[k][0] >= L - rule.get("tail", WIN) and (first is None or k < first): first = k; find_end.why = m.group(0)[:40]; break
    if first is not None and (cut is None or ws[first][0] < cut):
        j = sentence_start(ws, first)
        c = ws[j][0] - 0.2
        for a in range(j - 1, -1, -1):       # an Amen just before the outro: end right after it
            if c - ws[a][1] > 8: break
            if re.fullmatch(r"amen[.!,]?", ws[a][2], I): c = ws[a][1] + 0.4; break
        if rule.get("back_gap"):                                 # the teaching, then music, then the announcer: cut at the music
            mn, within = rule["back_gap"]
            for a in range(j - 1, 0, -1):
                if c - ws[a][1] > within: break
                if ws[a + 1][0] - ws[a][1] >= mn: c = ws[a][1] + 0.6; break
        cut = c if cut is None else min(cut, c)
    if cut is None: cut = ws[-1][1] + 0.6 if L - ws[-1][1] > 3 else L
    return max(0.0, round(L - cut, 1))

def items():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    road = set(D["sc"]["ids"])
    for b in D["books"]:
        road |= set(b["ov"]) | {s["id"] for s in b.get("spans", [])}
        for c in b["ch"]: road |= set(c["ids"])
    for s in D.get("bp", []):
        for _, ids in s["parts"]: road |= set(ids)
    return sorted([D["items"][i] for i in road if i in D["items"] and D["items"][i].get("audio") and D["items"][i]["src"] in RULES], key=lambda i: i["id"])

def measure(k, n):
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    have = {}
    for f in glob.glob(os.path.join(HERE, "data", "intro_skip", "trim_*.json")):
        if not f.endswith("_end.json"): have.update(json.load(open(f)))
    SR = {x for x in os.environ.get("SRCS", "").split(",") if x}; ID = {x for x in os.environ.get("IDS", "").split(",") if x}
    todo = [i for i in items() if (not SR or i["src"] in SR) and (not ID or i["id"] in ID) and (os.environ.get("ALL") == "1" or ID or i["id"] not in have)][k::n]
    os.makedirs(os.path.join(HERE, "trim"), exist_ok=True)
    out, path = {}, os.path.join(HERE, "trim", f"{k}.json")
    print(f"shard {k}/{n}: {len(todo)} recordings", flush=True)
    for x, it in enumerate(todo, 1):
        rule = RULES[it["src"]]
        try:
            head, whole = fetch(it["audio"])
            pcm = decode(head)
            if whole:
                L = len(pcm) / 16000
                hw = words_of(pcm[: WIN * 16000], model)
                tl = pcm[-rule.get("tail", WIN) * 16000:]
            else:
                hw = words_of(pcm[: WIN * 16000], model)
                tail, _ = fetch(it["audio"], tail=True, nbytes=7_000_000)
                tl = decode(tail)[-rule.get("tail", WIN) * 16000:]
            tw = words_of(tl, model); TL = len(tl) / 16000
            s, e = find_start(hw, rule), find_end(tw, rule, TL)
            if os.environ.get("DUMP") == "1":                    # the words with their times, to write rules from
                def lines(ws, off=0):
                    row, t = [], None
                    for w in ws:
                        if t is None: t = w[0]
                        row.append(w[2])
                        if re.search(r"[.?!]$", w[2]): print(f"    {t + off:7.1f}  {' '.join(row)}"); row, t = [], None
                    if row: print(f"    {t + off:7.1f}  {' '.join(row)}")
                print(f"=== {it['id']} {it['src']} {it['t']!r}  start={s} end_before={e}  (tail window {TL:.0f}s)\n  HEAD"); lines([w for w in hw if w[0] < 240])
                print("  TAIL (seconds from the window start)"); lines(tw)
            if s > 300 or e > 300: s, e = min(s, 0), min(e, 0)   # never cut more than a publisher's intro/outro could be
            out[it["id"]] = [s, e]
            nxt = " ".join(w[2] for w in hw if w[0] >= s)[:70]
            prv = " ".join(w[2] for w in tw if w[1] <= TL - e)[-70:]
            print(f"[{x}/{len(todo)}] {it['src']:20} +{s:5.1f}s -{e:5.1f}s  {it['t'][:40]!r}  starts: {nxt!r}  ends: {prv!r}  why: {getattr(find_end, 'why', '')!r}", flush=True)
        except Exception as ex:
            print(f"[{x}/{len(todo)}] {it['src']} {it['t'][:40]!r}: {type(ex).__name__} {str(ex)[:80]}", flush=True)
        if x % 20 == 0: json.dump(out, open(path, "w"))
    json.dump(out, open(path, "w"))

def merge():
    by = {}
    srcs = {i["id"]: i["src"] for i in items()}
    for f in glob.glob(os.path.join(HERE, "trim", "*.json")):
        for k, v in json.load(open(f)).items():
            if k in srcs: by.setdefault(srcs[k], {})[k] = v
    d = os.path.join(HERE, "data", "intro_skip")
    for src, m in by.items():
        old_s = json.load(open(os.path.join(d, f"trim_{src}.json"))) if os.path.exists(os.path.join(d, f"trim_{src}.json")) else {}
        old_e = json.load(open(os.path.join(d, f"trim_{src}_end.json"))) if os.path.exists(os.path.join(d, f"trim_{src}_end.json")) else {}
        old_s.update({k: v[0] for k, v in m.items()}); old_e.update({k: v[1] for k, v in m.items()})
        json.dump(old_s, open(os.path.join(d, f"trim_{src}.json"), "w"), indent=0, sort_keys=True)
        json.dump(old_e, open(os.path.join(d, f"trim_{src}_end.json"), "w"), indent=0, sort_keys=True)
        print(src, len(m), "measured;", sum(1 for v in m.values() if v[0] > 0), "start later;", sum(1 for v in m.values() if v[1] > 0), "end sooner")

if __name__ == "__main__":
    if sys.argv[1] == "measure": measure(int(sys.argv[2]), int(sys.argv[3]))
    else: merge()
