"""Start and end points for recordings hosted on Buzzsprout, from the transcripts their feeds publish for podcast apps
(<podcast:transcript type="application/json">: every word with its time and speaker). Buzzsprout refuses GitHub's
servers for the audio itself, so nothing is downloaded but the feed and the transcripts, one at a time, with pauses.

The words go through the same rules as tools/trim.py. The speaker labels add one check: when the words right after
the start belong to someone other than the preacher (the announcer), the start moves to where the preacher takes over.

    python tools/buzz_trim.py measure   -> trim/buzz.json {id: [start, end_before_file_end]} and audit/buzz.jsonl
Environment: IDS (comma list), SRCS (comma list), ALL=1 (measure again those already measured), DUMP=1 (print words).
"""
import glob, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trim, trim_audit
import requests

HERE = trim.HERE
PAUSE = 1.0

def show_ep(url):
    m = re.search(r"buzzsprout\.com/(\d+)/(?:episodes/)?(\d+)", url or "")
    return (m.group(1), m.group(2)) if m else (None, None)

def get(url, **kw):
    for a in range(3):
        try:
            r = requests.get(url, headers=trim.H, timeout=90, allow_redirects=True, **kw)
            if r.status_code == 200: return r
            if r.status_code in (403, 404, 410): return None
        except Exception: pass
        time.sleep(5 * (a + 1))
    return None

def with_transcripts(show):
    """Episode ids whose feed entry offers a JSON transcript."""
    r = get(f"https://feeds.buzzsprout.com/{show}.rss"); time.sleep(PAUSE)
    if not r: return set()
    return set(re.findall(rf"buzzsprout\.com/{show}/(\d+)/transcript\.json", r.text))

def words(show, ep):
    r = get(f"https://www.buzzsprout.com/{show}/{ep}/transcript.json"); time.sleep(PAUSE)
    if not r: return None
    try: segs = r.json().get("segments") or []
    except Exception: return None
    out = []
    for s in segs:
        b = (s.get("body") or "").strip()
        if not b or re.fullmatch(r"no-?transcript[.,]?", b, re.I): continue      # the transcript marking a stretch it did not transcribe
        st, en = float(s.get("startTime") or 0), float(s.get("endTime") or 0)
        if re.fullmatch(r"[^\w']+", b) and out:            # punctuation comes as its own token: it belongs to the word before
            a = out[-1]; out[-1] = (a[0], a[1], a[2] + b.replace(" ", ""), a[3]); continue
        out.append((st, min(en, st + 2.0), b, s.get("speaker") or ""))   # a word's end time can stretch over the music after it
    return out

def preacher_fix(ws, s, start_by):
    """If the minute after the start is someone other than the main speaker, start where the main speaker takes over."""
    if not ws: return s, ""
    count = {}
    for w in ws: count[w[3]] = count.get(w[3], 0) + 1
    main = max(count, key=count.get)
    after = [w for w in ws if w[0] >= s][:60]
    if not after or len(count) < 2: return s, ""
    other = sum(1 for w in after[:40] if w[3] != main)
    if other < 25: return s, ""
    said = " ".join(w[2] for w in after[:60] if w[3] != main).lower()   # only an announcer: not someone reading Scripture
    if not trim_audit.hits(trim_audit.ADD, said): return s, ""
    for k, w in enumerate(ws):            # the next run of 30+ words by the main speaker, starting at a sentence
        if w[0] < s or w[3] != main: continue
        run = ws[k:k + 30]
        if len(run) == 30 and all(x[3] == main for x in run) and w[0] <= start_by + 120:
            j = k
            return max(0.0, round(w[0] - 0.3, 1)), f"main speaker from {w[0]:.0f}s"
    return s, ""

def measure():
    t = open(os.path.join(HERE, "out", "site", "index.html"), encoding="utf-8").read()
    D, _ = json.JSONDecoder().raw_decode(t[t.index("const D=") + 8:])
    SR = {x for x in os.environ.get("SRCS", "").split(",") if x}; ID = {x for x in os.environ.get("IDS", "").split(",") if x}
    have = {}
    for f in glob.glob(os.path.join(HERE, "data", "intro_skip", "trim_*.json")):
        if not f.endswith("_end.json"): have.update(json.load(open(f)))
    todo = [it for it in D["items"].values() if isinstance(it.get("audio"), str) and "buzzsprout.com" in it["audio"] and not it.get("nar")
            and it["src"] in trim.RULES and (not SR or it["src"] in SR) and (not ID or it["id"] in ID)]
    if os.environ.get("ALL") != "1" and not ID: todo = [it for it in todo if it.get("aid", it["id"]) not in have]
    shows = sorted({show_ep(it["audio"])[0] for it in todo} - {None})
    avail = {}
    for sh in shows: avail[sh] = with_transcripts(sh); print(f"feed {sh}: {len(avail[sh])} episodes with transcripts", flush=True)
    os.makedirs(os.path.join(HERE, "trim"), exist_ok=True); os.makedirs(os.path.join(HERE, "audit"), exist_ok=True)
    out, af = {}, open(os.path.join(HERE, "audit", "buzz.jsonl"), "w")
    todo.sort(key=lambda i: i["id"]); n_no = 0
    print(f"{len(todo)} Buzzsprout recordings to look at", flush=True)
    for x, it in enumerate(todo, 1):
        sh, ep = show_ep(it["audio"])
        if not sh or ep not in avail.get(sh, set()): n_no += 1; continue
        ws4 = words(sh, ep)
        if not ws4: n_no += 1; continue
        if it.get("dur") and ws4[-1][1] < 0.85 * float(it["dur"]): n_no += 1; print(f"[{x}/{len(todo)}] {it['src']} {it['t'][:40]!r}: transcript ends at {ws4[-1][1]:.0f}s of {it['dur']}s (another episode's?), skipped", flush=True); continue
        rule = trim.RULES[it["src"]]; ws = [w[:3] for w in ws4]
        L = max(float(it.get("dur") or 0), ws[-1][1] + 1)
        sb = rule.get("start_by", trim.WIN)
        s = trim.find_start([w for w in ws if w[0] < max(trim.WIN, rule.get("start_by", trim.WIN))], rule)
        s2, why = preacher_fix(ws4, s, sb) if it["src"] in ("davey_wfth", "davey_journey") else (s, "")   # announcers' radio shows only
        if it["src"] in trim.SERVICE or it["src"] in trim.ANNOUNCE:
            ss = (trim.service_start if it["src"] in trim.SERVICE else trim.announce_start)(ws, it, lo=s2)
            if ss is not None and ss > s2: s2, why = ss, (why + "; " if why else "") + "service: teaching from the text line"
        T = rule.get("tail", trim.WIN); off = L - T
        tw = [(a - off, b - off, w) for a, b, w in ws if a >= off]
        e = trim.find_end(tw, rule, T); ewhy = getattr(trim.find_end, "why", "")
        if os.environ.get("DEBUG") == "1": print("  last tokens", ws4[-6:], "L", L, "T", T, "tw", len(tw), tw[-2:] if tw else None, "e", e, flush=True)
        if s2 > 900 or e > 400: s2, e = min(s2, 0), min(e, 0)
        out[it.get("aid", it["id"])] = [s2, e]
        rec = {"id": it["id"], "src": it["src"], "t": it["t"], "who": it["who"], "pass": it.get("pass", ""), "s": s2, "e": e, "dur": L,
               "old": [it.get("s") or 0, it.get("e") or 0], "rule_start": s, "speaker_fix": why, "end_why": ewhy, "via": "transcript",
               "before": trim_audit.sentences(ws, max(0, s2 - 75), s2), "after": trim_audit.sentences(ws, s2, s2 + 100),
               "end_before": trim_audit.sentences(ws, L - e - 90, L - e, off=-L), "end_after": trim_audit.sentences(ws, L - e, L, off=-L)}
        if s2 > 80: rec["opening"] = trim_audit.sentences(ws, 0, 45)
        aft = " ".join(z[1] for z in rec["after"] if z[0] < s2 + 60).lower(); bef = " ".join(z[1] for z in rec["before"]).lower()
        rec["flags"] = {"added_after_start": trim_audit.hits(trim_audit.ADD, aft), "teaching_before_start": trim_audit.hits(trim_audit.TEACH, bef) if s2 > 0 else [],
                        "added_before_end": trim_audit.hits(trim_audit.ADD, " ".join(z[1] for z in rec["end_before"][-4:]).lower())}
        af.write(json.dumps(rec) + "\n"); af.flush()
        print(f"[{x}/{len(todo)}] {it['src']:18} +{s2:6.1f}s (rules {s:6.1f}) -{e:5.1f}s  was +{rec['old'][0]} -{rec['old'][1]}  {it['t'][:40]!r}  {why}", flush=True)
        if x % 25 == 0: json.dump(out, open(os.path.join(HERE, "trim", "buzz.json"), "w"))
    json.dump(out, open(os.path.join(HERE, "trim", "buzz.json"), "w")); af.close()
    print(f"measured {len(out)}; no transcript {n_no}", flush=True)

if __name__ == "__main__":
    measure()
