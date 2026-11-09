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
    "mclean_podcast": {"start": [], "end": [], "amen_end": 25},
    "mclean_oceans": {"start": [], "end": [], "amen_end": 25},
    "mclean_api": {"start": [], "end": [], "amen_end": 25},
    "brookhills": {"start": [], "end": []},
    "brookhills_ia": {"start": [], "end": COMMON_OUT},
    "2819_podcast": {"start": [], "anchor": r"(mighty|majestic|matchless).{0,30}name of (our )?soon[- ]?coming king",
                     "end": [r"give (him|god) (a )?(radical )?praise", r"take the roof off", r"put your hands together", r"on your feet",
                             r"overflow (room|seating)", r"lobby", r"gift for you", r"next steps", r"we don'?t do membership", r"baptism sunday",
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
                               r"now (let'?s turn to|we'?re in) [^.]{0,60} (as we join|with) skip",
                               r"here'?s today'?s (message|teaching) from pastor skip[^.?!]*[.?!]", r"as pastor skip (begins|continues) today'?s (teaching|message)[^.?!]*[.?!]",
                               r"(let'?s turn|we'?re turning|turning|we'?re in)\b[^.?!]{0,70}\btoday'?s (lesson|teaching|message)[^.?!]*[.?!]",
                               r"\bas we join (him|pastor skip|skip)\b[^.?!]*[.?!]", r"\blet'?s (join|go to) (pastor )?skip\b[^.?!]*[.?!]",
                               r"\bhere'?s pastor skip( to begin| now)?[.!]", r"pastor skip continues his (message|teaching)[^.?!]*30 ?,? ?000 feet[^.?!]*[.?!]"],
                     "end": [r"thank(s| you) for (listening to|joining us)( today)?( on)? connect", r"that (concludes|wraps up) " + SKIPN, r"that'?s " + SKIPN + r" with a message",
                             r"\b800[- ]?922", r"connect ?with ?sk\w*\.com", r"is a presentation of connection communications", r"(see you|join us|tune in) (next time|tomorrow)",
                             r"before you go,? don'?t forget", r"here'?s how to (pre-?order|get|request)", r"when you give \$? ?\d+ or more"]},
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
    "davey_archive": {"pre": [r"now,? here'?s stephen\.?"], "start_exact": True,   # "...visit wisdomonline.org" often runs straight into his first sentence
                      "start": [r"this (message|lesson|sermon) (is|comes) from the (\w+ )?ministry of (stephen|steven) \w+", r"for (more )?information,? (please )?visit wisdom ?online(?: ?\.? ?org)?"], "end": COMMON_OUT + [r"wisdom ?online", r"wisdom international"]},
}

# ---- from the November audit (tools/trim_audit.py: the words around every cut, read one by one) ----
RULES["skip_connect"]["start"] += [r"what skip has for us today[^.?!]*[.?!]( (we'?ll|we will) be in [^.?!]*[.?!])?",
    r"\bas (skip|he) begins( today'?s (lesson|study|teaching|message))?[^.?!]*[.?!]", r"\blet'?s get started with skip'?s teaching[^.?!]*[.?!]( we'?ll be in [^.?!]*[.?!])?",
    r"\b(now,? )?let'?s (get started with|get into|dive into|continue with) today'?s (message|teaching|study|lesson)\b[^.?!]*[.?!]( we'?ll be in [^.?!]*[.?!])?",
    r"\bas we join skip\b[^.?!]*[.?!]", r"\bas we continue in the bible from 30,?000 feet[^.?!]*[.?!]( here'?s pastor skip[.!])?",
    r"\blet'?s turn to [^.?!]{0,60}(today'?s teaching|as skip|what skip)[^.?!]*[.?!]"]
RULES["skip_connect"]["end"] += [r"we'?re (so )?glad you joined us", r"thanks so much for being with us", r"before (you go|we go|we let you go)", r"that concludes",
    r"pray(ing)? that god will provide the support", r"partner with me", r"make a connection", r"tune in tomorrow", r"come back (tomorrow|next time)",
    r"thank you for your generosity", r"thanks for listening to connect"]
RULES["skip_connect"]["tail"] = 330
RULES["skip_connect"]["end"] += [r"\bthat'?s sk\w*p h\w+\b", r"\b(this|his) message is from (the|his) series", r"a message from his series", r"find the full message",
    r"that'?s why we share these bible teachings", r"the scripture is vital if you'?re going to", r"through your generous support", r"consider a gift",
    r"here'?s how you can (do that|give)", r"now,? here'?s an opportunity", r"now,? here'?s skip to share"]
RULES["davey_archive"]["end"] += [r"you('?ve| have) been listening to the teaching ministry", r"the preceding message by (dr\.? )?stephen", r"was produced by wisdom (for the heart|international)", r"this message is copyrighted", r"let'?s (close by )?sing\b", r"\bsing with me\b"]
RULES["skip_archive"]["start"] += [r"(?#exact)the bible from 30 ?,? ?000 feet,? soaring through the scriptures?,? from genesis to revelation[.,]?", r"welcome to expound[^.?!]*[.?!]",
    r"grow (in|and) grace,? and (in )?the knowledge of our lord[^.?!]*[.?!]",
    r"thank(s| you) for listening to (this|the|our) (service|message|teaching)[^.?!]*[.?!]"]
RULES["skip_archive"]["end"] = [p for p in RULES["skip_archive"]["end"] if p != r"let'?s stand\b"] + [r"thank(s| you)( so much)? for listening to (this|the|our) (service|message|teaching)",
    r"if you'?ve missed any of our expound", r"as skip pointed out", r"if you'?ve been following (along )?with us", r"may the lord watch over and keep you",
    r"welcome to god'?s family", r"we hope you enjoyed this message"]
RULES["skip_archive"]["tail"] = 330
RULES["skip_church"]["end"] += [r"read ahead"]
RULES["platt_messages"]["start"] += [r"today'?s episode is a rerun of[^.?!]*[.?!]", r"we hope you'?ve enjoyed this week'?s episode[^.?!]*[.?!]"]
RULES["platt_messages"]["end"] += [r"you are listening to (radical|david platt)"]
RULES["street_preachers"]["start"] += [r"\bstay locked[.!]?", r"you'?re now tuned into the street preach\w*[^.?!]*[.?!]", r"we pray that you'?re blessed by the content you'?re about to receive[.!]?",
    r"(?#at)\bwe('?re| are),? ((uh|um),? )*(walking (down )?through|continu\w+ to (track|walk)( through)?|in)(,? (uh|um),?)* (this text|(1|first|2|second|1st|2nd) peter|the book of \w+)"]
RULES["street_preachers"]["start_by"] = 420
RULES["davey_wfth"]["end"] += [r"with that (powerful )?illustration,? we bring today'?s message to a close", r"i hope this time in god'?s word today", r"this ministry exists to",
    r"you'?ve been listening to wisdom for the heart", r"this is wisdom for the heart with", r"as we close today"]
RULES["davey_wfth"]["back_gap"] = (8, 60)
RULES["davey_wfth"]["start"] += [r"(the )?message you'?re about to hear is called[^.?!]*[.?!]", r"stay with us for this message called[^.?!]*[.?!]",
    r"stephen'?s calling today'?s lesson[^.?!]*[.?!]", r"stephen dav\w* has a message for you called[^.?!]*[.?!]", r"today,? stephen dav\w* continues his series[^.?!]*[.?!]",
    r"here'?s stephen dav\w*[.!]"]
RULES["davey_journey"]["start"] += [r"stephen called this lesson[^.?!]*[.?!]", r"and this lesson is called[^.?!]*[.?!]", r"here'?s stephen with a lesson called[^.?!]*[.?!]",
    r"welcome to the wisdom journey[^.?!]*[.?!]"]
RULES["street_preachers"]["end"] += [r"\b(yo|hey|so),? street team\b", r"if you'?ve (been watching|enjoyed) this episode", r"if you'?re watching this (episode|podcast)",
    r"before we pray,? we want to shout out", r"we pray you were blessed by this behind the scenes", r"tim and i will be in investfest", r"grab a copy", r"shout out some of our sponsors"]

# Church services: the welcome, announcements, giving and promos come first; the teaching starts at the text or the series.
SERVICE = {"2819_podcast", "fearless"}          # long welcomes and announcements by the pastor himself before the text
# sources whose pastor sometimes says "before we dive into God's Word" and gives announcements first (start after them)
ANNOUNCE = {"mclean_podcast", "mclean_oceans", "mclean_api", "radical_message"}
NUMW = r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
TEXT_START = [r"\b(open|turn)( up)?( with me)?( (in|to) your bibles?)?( with me)? to\b", r"\bif you have (a|your|his) (bible|word)\b",
    r"\bour (text|passage|scripture) (today|this morning|tonight|for today)\b", r"\b(week|part|session) " + NUMW + r" (of|in) (our|a|the|this)\b",
    r"\bseries (called|entitled|titled)\b", r"\bwe('?re| are) (in|walking through|continuing|going through) (a series|the (book|gospel|letter) of|our (journey|series|study))",
    r"\bnote ?takers\b", r"\bthe word of the lord (reads|says)\b", r"\b(today|tonight|this morning),? we('?re| are) (continuing|beginning|starting|going to (look|study|be|dive))",
    r"\blet'?s dive (in|into)\b", r"\b(this is|today is) (week|part|the final message|the beginning)\b", r"\bjourney through\b", r"\bwe'?re (in|turning to) (the book of )?\w+ chapter\b",
    r"\blet'?s (worship the lord|hear from god) (through|in) (the study of )?his word\b", r"\blet'?s jump (right )?(back )?in\b",
    r"\b(back half|front half|final message|last message) of (a|our|the) series\b", r"\bseason (one|two|three|four|\d+)\b", r"\bwe('?re| are) in (a|our) (brand new )?series\b"]
PRE_STRONG = [r"\bbefore we (dive|jump|get|go|turn)( in| into| to)?\b", r"\b(sign up|register|registration|merchandise|online store|gift bag|membership class|baby dedications?|21 days of prayer)\b",
    r"\b(giving|offering|tithes?|generosity|give online|text to give|offering baskets?)\b", r"\b[a-z]+ ?\.(org|com|church)\b|\bdot (org|com|church)\b",
    r"\bthis (coming )?(sunday|saturday|wednesday|weekend)\b", r"\bnext (sunday|saturday|weekend)\b", r"\b(conference|retreat|trip to israel|israel trip|visiting israel)\b",
    r"\bthank you to (our|all) (staff|volunteers|worship)", r"\bstand up and say hi\b", r"\bdownload (the|our) app\b", r"\b(join us in|please) welcom(e|ing) (dr\.? |pastor |brother )?[a-z]+\b",
    r"\bdigital disciples\b", r"\boverflow\b", r"\bwelcome (to )?(the )?unbeliever", r"\bmy name is \w+", r"\bhonou?r (the|our|my) (pastor|shepherd|lead pastor|elders?)",
    r"\bwelcome (to )?(the )?(28|2819|twenty)", r"\b(be|you could be|go ahead and be) seated\b", r"\bhave a seat\b", r"\bshout ?out\b", r"\bgive it up for\b",
    r"\bbelong before you believe\b", r"\bwe('?re| are) a church rooted\b", r"\bnot playing church\b", r"\bwelcome our guests\b", r"\bjust a reminder\b",
    r"\b(couple|few) (of )?(things|announcements)\b", r"\bi want to (reference|mention|share) (a couple|two|a few|some)\b"]

def sents_of(ws):
    out, a = [], 0
    for k, w in enumerate(ws):
        if re.search(r"[.?!]$", w[2]) or k == len(ws) - 1:
            out.append((a, k, ws[a][0], " ".join(x[2] for x in ws[a:k + 1]).lower())); a = k + 1
    return out

def passage_pats(it):
    m = re.match(r"\s*((?:[1-3] )?[A-Za-z][A-Za-z ]*?)\s+(\d+)", (it.get("pass") or "").split(";")[0])
    if not m: return []
    book, ch = m.group(1).strip().lower(), m.group(2)
    nb = re.sub(r"^1 ", "(1|first|1st) ", re.sub(r"^2 ", "(2|second|2nd) ", re.sub(r"^3 ", "(3|third|3rd) ", book)))
    return [rf"\b{nb}(,? chapter)? {ch}\b", rf"\bbook of {nb}\b"]

def service_start(ws, it, lo=0.0, horizon=330):
    """Where the teaching starts in a service: the first text/series line not followed by announcements (keeping a prayer
    just before it); None if there is no such line."""
    S = [x for x in sents_of(ws) if x[2] >= lo and x[2] < horizon]
    if not S: return None
    pre = lambda t: any(re.search(p, t, I) for p in PRE_STRONG)
    tx = TEXT_START + passage_pats(it)
    for i, (a, b, t0, txt) in enumerate(S):
        if not any(re.search(p, txt, I) for p in tx): continue
        if any(pre(x[3]) for x in S[i:] if x[2] < t0 + 75): continue          # announcements right after: not yet
        j = i
        while j > 0 and t0 - S[j - 1][2] <= 60 and re.search(r"\b(let'?s pray|pray|father|lord|amen)\b", S[j - 1][3]) and not pre(S[j - 1][3]): j -= 1
        return max(lo, round(S[j][2] - 0.3, 1))
    last = None
    for i, x in enumerate(S):
        if pre(x[3]): last = i
    if last is not None and last + 1 < len(S) and S[-1][2] - S[last][2] > 90 and S[last][2] < 240: return max(lo, round(S[last + 1][2] - 0.3, 1))
    return None

BEFORE_WE = r"\bbefore we (dive|jump|get|go) (in|into)\b|\bbefore we (do|begin|start)\b,? (i|let me|a couple|just|i want)|\bjust a reminder\b|\b(couple|few) (of )?(things|announcements)\b|\bstart praying about who you might invite\b"
BEFORE_WE_STRICT = r"\bbefore we (dive|jump|get|go) (in|into)\b|\bbefore we (do|begin|start)\b,? (i|let me|a couple|just|i want)"
def announce_start(ws, it, lo=0.0, horizon=330):
    """Only when the preacher says "before we dive into God's Word" and announces things: start at the next text/series line."""
    S = [x for x in sents_of(ws) if lo <= x[2] < horizon]
    mark = BEFORE_WE if it["src"].startswith("mclean") else BEFORE_WE_STRICT
    k = next((i for i, x in enumerate(S) if re.search(mark, x[3], I)), None)
    if k is None: return None
    pre = lambda t: any(re.search(p, t, I) for p in PRE_STRONG)
    tx = TEXT_START + passage_pats(it) + [r"\b(all right|alright|okay|ok),? (so )?(today|let'?s|we'?re)\b", r"\bwe'?re in week \w+\b"]
    for i in range(k + 1, len(S)):
        if any(re.search(p, S[i][3], I) for p in tx) and not any(pre(x[3]) for x in S[i:] if x[2] < S[i][2] + 45): return round(S[i][2] - 0.3, 1)
    return None

# After the sermon: songs, communion, praise breaks, dismissals, outros (a cut right after the final Amen when there is one)
POST = [r"we('?re| are) (going to|gonna) take a (short |quick )?break", r"\bcome on up here\b", r"put your hands together", r"give (god|him|the lord|your \w+|jesus) (some |a )?(radical )?praise", r"take the roof off", r"if you (received|receive) (that|this)",
    r"\b(let'?s|would you|will you|please) (all )?stand\b(?! and (let'?s )?pray)(?! with me (and|as) (we|i) pray)", r"stand to (your|our) feet", r"\b(let'?s|we'?re going to|we'?ll) sing\b",
    r"\bsing with me\b", r"\bworship team\b", r"\bthis song\b", r"lord'?s supper", r"\bcommunion\b", r"\bthe elements\b", r"\b(tables?|altar) (is|are) open\b", r"\bdismiss\b",
    r"\bour mcs?\b", r"\bnext week,? we\b", r"take a (stretch )?break", r"let'?s pause there", r"not (going to be|gonna be) on (the )?podcasts?", r"\bbaptiz", r"come back up (here )?on (the )?stage",
    r"\bthank you for coming\b", r"you'?ve been listening to", r"this message is copyrighted", r"welcome to god'?s family", r"\bread ahead\b"]

POST_STRONG = [r"you('?ve| have) been listening to", r"the preceding message by", r"this message is copyrighted", r"let'?s close by singing", r"\bsing with me\b", r"\bworship team\b (is|here is|are) (going to|gonna)",
    r"not (going to be|gonna be) on (the )?podcasts?", r"take a (stretch )?break", r"let'?s pause there", r"welcome to god'?s family", r"\bread ahead\b",
    r"put your hands together", r"take the roof off", r"if you (received|receive) (that|this)", r"\bour mcs?\b", r"\bdismiss (you|us)\b",
    r"\b(those|who are) serving the lord'?s supper\b", r"\b(tables?|altar) (is|are) open\b", r"come back up (here )?on (the )?stage"]
def post_cut(ws, L, region=100):
    text, spans = joined(ws)
    first, why = None, ""
    amen_t = [w[1] for w in ws if re.fullmatch(r"amen[.!,?]?", w[2], I)]
    for strong, pats in ((True, POST_STRONG), (False, POST)):
        for p in pats:
            for m in re.finditer(p, text, I):
                k = word_at(spans, m.start())
                if ws[k][0] < L - region: continue
                if not strong and not any(0 <= ws[k][0] - a <= 60 for a in amen_t): continue   # a weak word counts only right after the closing Amen
                if first is None or k < first: first, why = k, m.group(0)[:40]
                break
    if first is None: return None, ""
    j = sentence_start(ws, first); c = ws[j][0] - 0.2
    for a in range(j - 1, -1, -1):
        if c - ws[a][1] > 40: break
        if re.fullmatch(r"amen[.!,?]?", ws[a][2], I): c = ws[a][1] + 0.6; break
    return c, why

def loop_cut(ws, L, region=100):
    """Speech recognition repeating one line over music (four times or more, two words or more): cut where the repeats begin."""
    S = [x for x in sents_of(ws) if x[2] >= L - region]
    n = lambda x: re.sub(r"[^a-z ]", "", x[3]).strip()
    for i in range(len(S) - 4):
        t = n(S[i])
        if i + 4 < len(S) and len(t.split()) >= 2 and len(t) < 60 and t == n(S[i + 1]) == n(S[i + 2]) == n(S[i + 3]) == n(S[i + 4]): return S[i][2] - 0.2
    return None

def words_of(pcm, model):
    segs, _ = model.transcribe(pcm, beam_size=1, language="en", vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or []) if w.word.strip()]

def head_bytes(url, secs, dur):
    """Enough of a file's opening to hold `secs` seconds (from its size and length)."""
    try:
        r = requests.head(url, headers=H, timeout=60, allow_redirects=True); n = int(r.headers.get("content-length") or 0)
    except Exception: n = 0
    try: dur = float(dur or 0)
    except Exception: dur = 0
    if n and dur: return min(n, int(n * min(1.0, (secs + 30) / dur) * 1.15) + 400_000)
    return int((secs + 30) * 24_000)

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
        t = w[2].replace("\u2019", "'").replace("\u2018", "'")
        spans.append((len(text), len(text) + len(t))); text += t
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

def after_last(ws, text, spans, pats, lo, hi, exact=False):
    """Index of the word after the sentence holding the last match (beginning between lo and hi seconds), or None.
    exact: the word right after the match itself, for an announcer line speech recognition runs into the sermon."""
    last = None
    for pat in pats:
        for m in re.finditer(pat, text, I):
            k = word_at(spans, m.end() - 1)
            if lo <= ws[word_at(spans, m.start())][0] <= hi and (last is None or k > last):
                last, lx = k, ("at" if pat.startswith("(?#at)") else "exact" if pat.startswith("(?#exact)") else "")
                if lx == "at": at = sentence_start(ws, word_at(spans, m.start()))
    if last is None: return None
    if lx == "at": return at                       # the teaching starts with this very sentence
    return last + 1 if exact or lx == "exact" else sentence_end(ws, last) + 1

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
    j = after_last(ws, text, spans, rule.get("start", []), t0 if jp else 0, rule.get("start_by", WIN), rule.get("start_exact", False))
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
    pc, pwhy = post_cut(ws, L)
    if pc is not None and (cut is None or pc < cut): cut = pc; find_end.why = "after the sermon: " + pwhy
    lc = loop_cut(ws, L)
    if lc is not None and (cut is None or lc < cut): cut = lc; find_end.why = "repeating line (music)"
    if rule.get("amen_end"):                                   # the service's last Amen, near the end: stop right after it
        am = [w for w in ws if re.fullmatch(r"amen[.!,?]?", w[2], I) and w[1] >= L - rule["amen_end"]]
        if am and (cut is None or am[-1][1] + 0.8 < cut): cut = am[-1][1] + 0.8; find_end.why = "last amen"
    if cut is None:
        for k in range(len(ws) - 1, max(0, len(ws) - 5), -1):      # <= 3 words after an 8 s silence near the end: music heard as words
            if ws[k][0] - ws[k - 1][1] >= 8 and ws[k][0] >= L - 60 and len(ws) - k <= 3: cut = ws[k - 1][1] + 0.6; find_end.why = "silence, then stray words"; break
    if cut is None: cut = ws[-1][1] + 0.6 if L - ws[-1][1] > 3 else L
    for w in ws:                                                   # an Amen just after the cut belongs to the prayer
        if cut - 0.5 <= w[0] <= cut + 2.5 and re.fullmatch(r"amen[.!,?]?", w[2], I): cut = max(cut, w[1] + 0.5)
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
    # Stephen Davey's recordings everywhere in the app (the Library, search), not only on the road: his intros are in all of them
    road |= {i for i, it in D["items"].items() if it["src"] in ("davey_archive", "davey_sermons", "davey_wfth", "davey_journey")}
    # and every Bible from 30,000 Feet flight, the radio versions in parts too
    road |= {i for i, it in D["items"].items() if it["src"].startswith("skip_") and re.match(r"\s*Flight\b", it["t"] or "")}
    road |= set(D["items"])   # every recording: the Library and search too, not only the road
    return sorted([D["items"][i] for i in road if i in D["items"] and D["items"][i].get("audio") and not D["items"][i].get("nar") and D["items"][i]["src"] in RULES], key=lambda i: i["id"])

def measure(k, n):
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    have = {}
    for f in glob.glob(os.path.join(HERE, "data", "intro_skip", "trim_*.json")):
        if not f.endswith("_end.json"): have.update(json.load(open(f)))
    SR = {x for x in os.environ.get("SRCS", "").split(",") if x}; ID = {x for x in os.environ.get("IDS", "").split(",") if x}
    todo = [i for i in items() if "buzzsprout.com" not in str(i["audio"]) and (not SR or i["src"] in SR) and (not ID or i["id"] in ID) and (os.environ.get("ALL") == "1" or ID or i.get("aid", i["id"]) not in have)][k::n]
    os.makedirs(os.path.join(HERE, "trim"), exist_ok=True)
    out, path = {}, os.path.join(HERE, "trim", f"{k}.json")
    print(f"shard {k}/{n}: {len(todo)} recordings", flush=True)
    for x, it in enumerate(todo, 1):
        rule = RULES[it["src"]]
        try:
            svc = it["src"] in SERVICE or it["src"] in ANNOUNCE
            head, whole = fetch(it["audio"], nbytes=head_bytes(it["audio"], 330, it.get("dur")) if svc else 4_000_000)
            pcm = decode(head)
            sw = words_of(pcm[: (330 if svc else WIN) * 16000], model)
            hw = [w for w in sw if w[0] < WIN]
            if whole:
                L = len(pcm) / 16000
                tl = pcm[-rule.get("tail", WIN) * 16000:]
            else:
                tail, _ = fetch(it["audio"], tail=True, nbytes=7_000_000)
                tl = decode(tail)[-rule.get("tail", WIN) * 16000:]
            tw = words_of(tl, model); TL = len(tl) / 16000
            s, e = find_start(hw, rule), find_end(tw, rule, TL)
            if it["src"] in SERVICE:                                 # a service: past the welcome and announcements to the text
                ss = service_start(sw, it, lo=s)
                if ss is not None: s = ss
            elif it["src"] in ANNOUNCE:                              # "before we dive into God's Word ..." announcements
                ss = announce_start(sw, it, lo=s)
                if ss is not None: s = ss
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
            if s > (330 if svc else 300) or e > 400: s, e = min(s, 0), min(e, 0)   # never cut more than an intro/outro (or a service's opening) could be
            if os.environ.get("AUDIT") == "1":                    # the words around the new cuts, to read and compare
                import trim_audit as TA
                rec = {"id": it["id"], "src": it["src"], "t": it["t"], "who": it["who"], "pass": it.get("pass", ""), "s": s, "e": e, "dur": it.get("dur"),
                       "old": [it.get("s") or 0, it.get("e") or 0], "end_why": getattr(find_end, "why", ""),
                       "before": TA.sentences(sw, max(0, s - 75), s), "after": TA.sentences(sw, s, s + 100),
                       "end_before": TA.sentences(tw, TL - e - 90, TL - e, off=-TL), "end_after": TA.sentences(tw, TL - e, TL, off=-TL)}
                os.makedirs(os.path.join(HERE, "audit"), exist_ok=True)
                with open(os.path.join(HERE, "audit", f"{k}.jsonl"), "a") as af: af.write(json.dumps(rec) + "\n")
            out[it.get("aid", it["id"])] = [s, e]   # by recording: a recording moved to another title (audio_fixes.json) keeps its points
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if __name__ == "__main__":
    if sys.argv[1] == "measure": measure(int(sys.argv[2]), int(sys.argv[3]))
    else: merge()
