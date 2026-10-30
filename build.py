"""Assemble the ledger from data/catalog_verified.jsonl and write:
   out/platt_pam_bible_companion.xlsx
   out/roadmap.html
Run:  python run.py build
"""
from __future__ import annotations
import json, os, re, html
from datetime import datetime, timezone
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from canon import BOOKS, CHAPTERS, TESTAMENT, NAME_TO_INDEX
import config

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out")
VERIFIED = os.path.join(DATA, "catalog_verified.jsonl")
LOG = os.path.join(DATA, "verification_log.jsonl")
NARR = os.path.join(DATA, "narrative_order.json")
REPORT = os.path.join(DATA, "harvest_report.json")

FONT = "Arial"
HDR_FILL = PatternFill("solid", fgColor="1F3A4D")
TIER_FILL = {"V2": PatternFill("solid", fgColor="E3F1E6"), "V1": PatternFill("solid", fgColor="FFF4D6"),
             "GAP": PatternFill("solid", fgColor="F6E4E4")}

def _log(msg): print(f"[build] {msg}", flush=True)

# ---------------- data assembly ----------------
def load_entries() -> list[dict]:
    if not os.path.exists(VERIFIED):
        raise SystemExit("run verify first (data/catalog_verified.jsonl missing)")
    return [json.loads(l) for l in open(VERIFIED, encoding="utf-8")]

def preacher_label(e: dict) -> str:
    if e["speaker"] == "Platt":
        return "Platt"
    if e["speaker"] == "PAM":
        return "PAM (2819)" if e["era"] == "2819" else "PAM gap-fill (" + ("Victory-era" if e["era"] == "victory" else e["era"]) + ")"
    return e["speaker"]

def narrative_map() -> dict[tuple[str, int], int]:
    return {(o["book"], o["chapter"]): o["seq"] for o in json.load(open(NARR))}

def assemble(entries: list[dict]):
    """Return (chapter_entries, book_overviews, gaps, guests, review, status) structures."""
    usable = [e for e in entries if e["tier"] in ("V2", "V1")]
    guests = [e for e in entries if e["speaker"].startswith("guest:")]
    review = [e for e in usable if e["speaker"] == "unknown"]
    core = [e for e in usable if e["speaker"] in ("Platt", "PAM")]
    chapter_entries: dict[tuple[str, int], list[dict]] = defaultdict(list)
    book_overviews: dict[str, list[dict]] = defaultdict(list)
    for e in core:
        for book, d in e["refs"].items():
            # an overview covers a BOOK only when it is whole-book or ≥60% of it; a partial study (Elijah = 1 Kings 17–2 Kings 2)
            # attaches to the chapters it actually covers
            if e["track"] == "overview" and (d["whole_book"] or len(d["chapters"]) / CHAPTERS[book] >= 0.6):
                book_overviews[book].append(e)
            else:
                ce = e if e["track"] != "overview" else {**e, "track": "sermon", "series": (e.get("series") or "") + " (multi-session study)"}
                for c in d["chapters"]:
                    chapter_entries[(book, c)].append(ce)
    # PAM rule: Victory-era / other-era PAM only where 2819-era PAM has nothing for that chapter
    for key, lst in chapter_entries.items():
        has_2819 = any(e["speaker"] == "PAM" and e["era"] == "2819" and e["track"] == "sermon" for e in lst)
        if has_2819:
            lst[:] = [e for e in lst if not (e["speaker"] == "PAM" and e["era"] != "2819")]
    for book, lst in book_overviews.items():
        seen = set(); book_overviews[book] = [e for e in lst if not (e["id"] in seen or seen.add(e["id"]))]
    # per-chapter status
    status = {}
    for bi, book, c in ((NAME_TO_INDEX[b[0]], b[0], ch) for b in BOOKS for ch in range(1, b[2] + 1)):
        lst = chapter_entries.get((book, c), [])
        sermons = [e for e in lst if e["track"] == "sermon"]
        devs = [e for e in lst if e["track"] == "devotional"]
        best = "V2" if any(e["tier"] == "V2" for e in sermons) else ("V1" if sermons else "")
        if best == "V2": s = "Sermon V2"
        elif best == "V1": s = "Sermon V1"
        elif devs: s = "Devotional only"
        elif any(len(e["refs"]) <= 3 for e in book_overviews.get(book, [])): s = "Overview only"
        else: s = "Verified gap"
        status[(book, c)] = {"status": s, "sermons": len(sermons), "devotionals": len(devs),
                             "platt_sermons": sum(1 for e in sermons if e["speaker"] == "Platt"),
                             "pam_sermons": sum(1 for e in sermons if e["speaker"] == "PAM")}
    return chapter_entries, book_overviews, guests, review, status

def sources_checked() -> str:
    if not os.path.exists(REPORT):
        return "see SOURCE GUIDE"
    rep = json.load(open(REPORT))
    return ", ".join(f"{k} ({v.get('count', 'error')})" for k, v in rep["sources"].items())

# ---------------- xlsx ----------------
def _hdr(ws, row, headers, widths=None):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF"); c.fill = HDR_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)

def _row(ws, r, values, link_col=None, fill=None):
    for i, v in enumerate(values, 1):
        c = ws.cell(row=r, column=i, value=v)
        c.font = Font(name=FONT, size=10)
        if fill: c.fill = fill
        if link_col and i == link_col and isinstance(v, str) and v.startswith("http"):
            c.hyperlink = v; c.font = Font(name=FONT, size=10, color="0563C1", underline="single")

def write_xlsx(entries, chapter_entries, book_overviews, guests, review, status, narr):
    os.makedirs(OUT, exist_ok=True)
    wb = Workbook()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    checked = sources_checked()

    # ---- CHAPTER STATUS (helper, drives dashboard formulas) ----
    st = wb.active; st.title = "CHAPTER STATUS"
    _hdr(st, 1, ["Canonical #", "Narrative seq", "Testament", "Book", "Chapter", "Status", "Sermon entries",
                 "Platt sermons", "PAM sermons", "Devotional entries", "Book overview entries"],
         [11, 12, 10, 16, 9, 16, 13, 12, 12, 16, 18])
    r = 2
    for bi, book, c in ((NAME_TO_INDEX[b[0]], b[0], ch) for b in BOOKS for ch in range(1, b[2] + 1)):
        s = status[(book, c)]
        _row(st, r, [r - 1, narr[(book, c)], TESTAMENT[book], book, c, s["status"], s["sermons"], s["platt_sermons"],
                     s["pam_sermons"], s["devotionals"], len(book_overviews.get(book, []))])
        r += 1
    last = r - 1

    # ---- DASHBOARD ----
    d = wb.create_sheet("DASHBOARD", 0)
    d["A1"] = "PLATT + PAM | BIBLE LISTENING COMPANION"; d["A1"].font = Font(name=FONT, bold=True, size=14)
    d["A2"] = f"Built {today}. Every link in this workbook was issued by the publisher's own catalog; tier V2 = fetched and title-confirmed, V1 = publisher-issued but the host blocked the check. Nothing is a search page."
    d["A2"].font = Font(name=FONT, size=9, italic=True)
    d["A4"] = "Chapter coverage (all 1,189 chapters)"; d["A4"].font = Font(name=FONT, bold=True)
    labels = [("Chapters total", f"=COUNTA('CHAPTER STATUS'!E2:E{last})"),
              ("Chapters with a fetch-verified sermon (V2)", f"=COUNTIF('CHAPTER STATUS'!F2:F{last},\"Sermon V2\")"),
              ("Chapters with a publisher-issued but unconfirmed sermon (V1)", f"=COUNTIF('CHAPTER STATUS'!F2:F{last},\"Sermon V1\")"),
              ("Chapters with only a Pray the Word devotional", f"=COUNTIF('CHAPTER STATUS'!F2:F{last},\"Devotional only\")"),
              ("Chapters with only a book overview", f"=COUNTIF('CHAPTER STATUS'!F2:F{last},\"Overview only\")"),
              ("Verified gaps (no Platt or PAM teaching found)", f"=COUNTIF('CHAPTER STATUS'!F2:F{last},\"Verified gap\")"),
              ("Chapters with a Platt sermon", f"=COUNTIF('CHAPTER STATUS'!H2:H{last},\">0\")"),
              ("Chapters with a PAM sermon", f"=COUNTIF('CHAPTER STATUS'!I2:I{last},\">0\")"),
              ("Chapters with a Pray the Word episode", f"=COUNTIF('CHAPTER STATUS'!J2:J{last},\">0\")")]
    for i, (lab, f) in enumerate(labels, 5):
        d.cell(row=i, column=1, value=lab).font = Font(name=FONT)
        d.cell(row=i, column=2, value=f).font = Font(name=FONT, bold=True)
    d["A15"] = "Teaching entries by tier"; d["A15"].font = Font(name=FONT, bold=True)
    tiers = defaultdict(int)
    for e in entries: tiers[e["tier"]] += 1
    rr = 16
    for t in ("V2", "V1", "PENDING", "FAIL"):
        d.cell(row=rr, column=1, value={"V2": "V2 fetch-verified", "V1": "V1 publisher-issued, unconfirmed", "PENDING": "Cataloged by publisher, episode link not yet captured (LINK PENDING sheet)", "FAIL": "FAIL (excluded: dead link or title mismatch)"}[t]).font = Font(name=FONT)
        d.cell(row=rr, column=2, value=f"=COUNTIF('TEACHING INDEX'!K:K,\"{t}\")").font = Font(name=FONT, bold=True); rr += 1
    d["A21"] = "Sources harvested: " + checked; d["A21"].font = Font(name=FONT, size=9)
    d.column_dimensions["A"].width = 62; d.column_dimensions["B"].width = 14
    # per-book table
    _hdr(d, 22, ["Book", "Chapters", "Sermon V2", "Sermon V1", "Devotional only", "Overview only", "Verified gaps", "% with any sermon"])
    for i, (book, abbr, n, t, _a) in enumerate(BOOKS, 23):
        d.cell(row=i, column=1, value=book).font = Font(name=FONT)
        d.cell(row=i, column=2, value=n).font = Font(name=FONT)
        for col, lab in zip("CDEFG", ["Sermon V2", "Sermon V1", "Devotional only", "Overview only", "Verified gap"]):
            d[f"{col}{i}"] = f"=COUNTIFS('CHAPTER STATUS'!$D$2:$D${last},$A{i},'CHAPTER STATUS'!$F$2:$F${last},\"{lab}\")"
            d[f"{col}{i}"].font = Font(name=FONT)
        d[f"H{i}"] = f"=IF(B{i}=0,0,(C{i}+D{i})/B{i})"; d[f"H{i}"].number_format = "0%"; d[f"H{i}"].font = Font(name=FONT)
    d.freeze_panes = None

    # ---- CHAPTER LEDGER ----
    led = wb.create_sheet("CHAPTER LEDGER", 1)
    headers = ["Canonical sort", "Narrative sort", "Testament", "Book", "Chapter", "Row type", "Preacher", "Era",
               "Title", "Passage (as the source shows it)", "Track", "Source", "Tier", "Link", "Verified on",
               "Duration (s)", "Published", "Progress", "Notes"]
    _hdr(led, 1, headers, [9, 9, 9, 14, 8, 13, 18, 10, 50, 26, 11, 14, 6, 52, 12, 9, 22, 11, 40])
    dv = DataValidation(type="list", formula1='"Not started,Listening,Done"', allow_blank=True)
    led.add_data_validation(dv)
    r = 2
    first_seq = {}
    for (book, c), seq in narr.items():
        first_seq[book] = min(first_seq.get(book, 10**9), seq)
    for bi, (book, abbr, n, t, _a) in enumerate(BOOKS):
        # overviews pinned above chapter 1
        def _ovkey(x):
            m = re.search(r"Secret Church\s+(\d+)", x["title"], re.I); ms = re.search(r"Session\s+(\d+)", x["title"], re.I)
            mm = re.match(r"\s*(\d+)\.(\d+)\s*[–-]", x["title"])
            scn = int(mm.group(1)) if mm else (int(m.group(1)) if m else 0); sen = int(mm.group(2)) if mm else (int(ms.group(1)) if ms else 0)
            return (x["speaker"] != "Platt", 0 if (m or mm) else 1, scn, sen, x["published"])
        for e in sorted(book_overviews.get(book, []), key=_ovkey):
            _row(led, r, [bi * 1000 + 0.5, first_seq[book] - 0.5, t, book, "Overview", "Book overview", preacher_label(e), e["era"],
                          e["title"], e["refs_text"], e["track"], e["source"], e["tier"], e.get("primary_url", e["url"]),
                          e.get("verified_at", "")[:10], e["duration"], e["published"][:25], "Not started",
                          e.get("verify_note", "")], link_col=14, fill=TIER_FILL.get(e["tier"]))
            dv.add(led.cell(row=r, column=18)); r += 1
        for c in range(1, n + 1):
            lst = chapter_entries.get((book, c), [])
            lst = sorted(lst, key=lambda x: (x["track"] != "sermon", x["speaker"] != "Platt", x["tier"] != "V2", x["published"]))
            if not any(e["track"] == "sermon" for e in lst):
                gap_note = "No full-length Platt or PAM sermon found in: " + checked
                _row(led, r, [bi * 1000 + c, narr[(book, c)], t, book, c, "VERIFIED GAP (sermon)", "", "", "", "", "", "", "", "", today, "", "", "Not started", gap_note],
                     fill=TIER_FILL["GAP"])
                dv.add(led.cell(row=r, column=18)); r += 1
            for e in lst:
                _row(led, r, [bi * 1000 + c, narr[(book, c)], t, book, c, "Sermon" if e["track"] == "sermon" else "Pray the Word",
                              preacher_label(e), e["era"], e["title"], e["refs_text"], e["track"], e["source"], e["tier"],
                              e.get("primary_url", e["url"]), e.get("verified_at", "")[:10], e["duration"], e["published"][:25],
                              "Not started", e.get("verify_note", "")], link_col=14, fill=TIER_FILL.get(e["tier"]))
                dv.add(led.cell(row=r, column=18)); r += 1
    led.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{r-1}"

    # ---- 66 BOOKS ----
    b66 = wb.create_sheet("66 BOOKS", 2)
    _hdr(b66, 1, ["#", "Testament", "Book", "Chapters", "Book overviews", "Chapters w/ Platt sermon", "Chapters w/ PAM sermon",
                  "Chapters w/ Pray the Word", "Verified gaps", "First overview", "Link"], [5, 10, 16, 9, 14, 18, 18, 18, 12, 46, 50])
    for i, (book, abbr, n, t, _a) in enumerate(BOOKS, 2):
        ov = book_overviews.get(book, [])
        _row(b66, i, [i - 1, t, book, n, len(ov),
                      f"=COUNTIFS('CHAPTER STATUS'!$D:$D,C{i},'CHAPTER STATUS'!$H:$H,\">0\")",
                      f"=COUNTIFS('CHAPTER STATUS'!$D:$D,C{i},'CHAPTER STATUS'!$I:$I,\">0\")",
                      f"=COUNTIFS('CHAPTER STATUS'!$D:$D,C{i},'CHAPTER STATUS'!$J:$J,\">0\")",
                      f"=COUNTIFS('CHAPTER STATUS'!$D:$D,C{i},'CHAPTER STATUS'!$F:$F,\"Verified gap\")",
                      ov[0]["title"] if ov else "", ov[0].get("primary_url", ov[0]["url"]) if ov else ""], link_col=11)

    # ---- TEACHING INDEX ----
    ti = wb.create_sheet("TEACHING INDEX", 3)
    _hdr(ti, 1, ["ID", "Preacher", "Era", "Track", "Title", "Passage (as the source shows it)", "Books", "Chapters covered",
                 "Source", "Published", "Tier", "Link", "Verified on", "Fetched title", "Note"],
         [10, 18, 9, 11, 50, 30, 18, 10, 14, 22, 6, 52, 12, 40, 30])
    for i, e in enumerate(sorted(entries, key=lambda x: (x["speaker"], x["source"], x["published"])), 2):
        _row(ti, i, [e["id"], preacher_label(e), e["era"], e["track"], e["title"], e["refs_text"], ", ".join(e["refs"].keys()),
                     sum(len(d["chapters"]) for d in e["refs"].values()), e["source"], e["published"][:25], e["tier"],
                     e.get("primary_url", e["url"]), e.get("verified_at", "")[:10], e.get("fetched_title", ""), e.get("verify_note", "")],
             link_col=12, fill=TIER_FILL.get(e["tier"]))
    ti.auto_filter.ref = f"A1:O{len(entries)+1}"

    # ---- SPEAKER AUDIT (2819 + PAM channels) ----
    sa = wb.create_sheet("SPEAKER AUDIT", 4)
    _hdr(sa, 1, ["Source", "Title", "Speaker", "Evidence", "Era", "Passage", "Tier", "Link", "Published"], [14, 60, 22, 16, 10, 24, 6, 52, 22])
    rows = [e for e in entries if e["source"] in ("youtube_2819", "youtube_pam", "youtube_victory", "2819_podcast", "victory_podcast", "pam_podcast")]
    for i, e in enumerate(sorted(rows, key=lambda x: (x["source"], x["published"])), 2):
        _row(sa, i, [e["source"], e["title"], e["speaker"], e["speaker_evidence"], e["era"], e["refs_text"], e["tier"], e["url"], e["published"][:25]], link_col=8)

    # ---- GUEST ----
    g = wb.create_sheet("GUEST", 5)
    _hdr(g, 1, ["Source", "Title", "Actual speaker", "Passage", "Tier", "Link", "Note"], [16, 60, 24, 24, 6, 52, 30])
    for i, e in enumerate(sorted(guests, key=lambda x: (x["source"], x["title"])), 2):
        _row(g, i, [e["source"], e["title"], e["speaker"].replace("guest:", ""), e["refs_text"], e["tier"], e["url"],
                    "Not PAM / not Platt — does not count toward coverage"], link_col=6)

    # ---- REVIEW (speaker unknown) ----
    rv = wb.create_sheet("REVIEW", 6)
    _hdr(rv, 1, ["Source", "Title", "Why", "Passage", "Tier", "Link"], [16, 60, 26, 24, 6, 52])
    for i, e in enumerate(sorted(review, key=lambda x: (x["source"], x["title"])), 2):
        _row(rv, i, [e["source"], e["title"], "speaker not stated by source (" + e["speaker_evidence"] + ")", e["refs_text"], e["tier"], e["url"]], link_col=6)

    # ---- LINK PENDING (cataloged by the publisher, episode URL not yet captured) ----
    lp = wb.create_sheet("LINK PENDING", 7)
    _hdr(lp, 1, ["Preacher", "Source", "Title (as published)", "Passage (from title)", "Published", "Why pending"], [18, 18, 70, 24, 12, 60])
    pend = [e for e in entries if e["tier"] == "PENDING"]
    for i, e in enumerate(sorted(pend, key=lambda x: (x["source"], x["published"]), reverse=True), 2):
        _row(lp, i, [preacher_label(e) if e["speaker"] in ("Platt", "PAM") else e["speaker"], e["source"], e["title"], e["refs_text"], e["published"][:10], e.get("verify_note", "")])
    lp.auto_filter.ref = f"A1:F{len(pend)+1}"

    # ---- VERIFICATION LOG ----
    vl = wb.create_sheet("VERIFICATION LOG", 7)
    _hdr(vl, 1, ["URL", "HTTP", "Tier", "Fetched title", "Match ratio", "Note", "Checked at", "Final URL"], [60, 6, 6, 50, 9, 28, 20, 50])
    if os.path.exists(LOG):
        recs = {}
        for line in open(LOG, encoding="utf-8"):
            rec = json.loads(line); recs[rec["url"]] = rec
        for i, rec in enumerate(sorted(recs.values(), key=lambda x: x["url"]), 2):
            _row(vl, i, [rec["url"], rec["status"], rec["tier"], rec.get("fetched_title", ""), rec.get("ratio", ""), rec.get("note", ""),
                         rec["checked_at"], rec.get("final_url", "")], link_col=1)

    # ---- SECRET CHURCH (all events in order, sessions in order) ----
    scs = wb.create_sheet("SECRET CHURCH", 8)
    _hdr(scs, 1, ["SC #", "Event", "Session", "Session title / link", "Scope (books)", "Tier", "Link", "Verified on", "Note"], [6, 42, 9, 60, 26, 6, 60, 12, 40])
    def sc_num(t):
        m = re.match(r"\s*(\d+)\.(\d+)\s*[–-]", t or "") or re.search(r"Secret Church\s+(\d+)", t or "", re.I); return int(m.group(1)) if m else None
    def sess_num(t):
        m = re.match(r"\s*(\d+)\.(\d+)\s*[–-]", t or "")
        if m: return int(m.group(2))
        m = re.search(r"Session\s+(\d+)", t or "", re.I); return int(m.group(1)) if m else 0
    sessions = defaultdict(list)
    for e in entries:
        if e["tier"] == "FAIL":
            continue
        if e.get("series", "").startswith("Secret Church") or "Secret Church" in e["title"]:
            n = e.get("sc_season") or sc_num(e["title"]) or sc_num(e.get("series", ""))
            if n and (e.get("sc_episode") or sess_num(e["title"])):
                sessions[n].append(e)
    r = 2
    for n, title, url, scope in config.SECRET_CHURCH_EVENTS:
        _row(scs, r, [n, f"Secret Church {n}: {title}", "Event", f"Secret Church {n}: {title} (event page)", scope, "V1", url, "2026-10-29", "Event page from radical.net's own Secret Church menu"], link_col=7); r += 1
        ss = sorted(sessions.get(n, []), key=lambda x: (x.get("sc_episode") or sess_num(x["title"]), x["tier"] == "PENDING"))
        if ss:
            for e in ss:
                _row(scs, r, [n, f"Secret Church {n}: {title}", e.get("sc_episode") or sess_num(e["title"]), e["title"], e["refs_text"] or scope, e["tier"], e.get("primary_url", e["url"]) or "(link pending)", e.get("verified_at", "")[:10], e.get("verify_note", "")], link_col=7, fill=TIER_FILL.get(e["tier"], TIER_FILL["GAP"] if e["tier"] == "PENDING" else None)); r += 1
        else:
            _row(scs, r, [n, f"Secret Church {n}: {title}", "1…", "Sessions not yet enumerated — filled from Radical's YouTube channel (yt-dlp pass) in Claude Code", scope, "", "", "", "pending"], fill=TIER_FILL["GAP"]); r += 1

    # ---- SOURCE GUIDE ----
    sg = wb.create_sheet("SOURCE GUIDE", 8)
    _hdr(sg, 1, ["Source", "What it is", "URL", "How it was used"], [18, 44, 60, 60])
    guide = [
        ("ptw", "Pray the Word with David Platt — official RSS (Buzzsprout)", config.PTW_FEED, "Every episode; passage parsed from the publisher's own title; radical.net mirror page used when it verifies"),
        ("platt_messages", "David Platt Messages — official sermon podcast RSS", config.PLATT_MESSAGES_FEED, "Full-length sermons; passage from title/description"),
        ("radical", "radical.net messages, Radical Podcast sermons, series pages", config.RADICAL_SCRIPTURE_INDEX, "Enumerated from the site's own sitemap / WP REST; each page fetched for author + passage"),
        ("secret_church", "Secret Church event pages (book studies and surveys)", config.SECRET_CHURCH_PAGES[0], "Overview track, pinned above chapter 1 of the books they cover"),
        ("mclean", "McLean Bible Church podcast (resolved via iTunes Search)", config.ITUNES_SEARCH + "McLean+Bible+Church", "Platt sermons kept; other speakers -> GUEST"),
        ("2819_podcast", "2819 Church official podcast (resolved via iTunes Search)", config.ITUNES_SEARCH + "2819+Church", "Speaker from title suffix; guests -> GUEST"),
        ("youtube_2819", "2819 Church YouTube channel (enumerated with yt-dlp; verified with oEmbed)", config.YOUTUBE_CHANNELS["2819"][0], "Primary PAM catalog; 2819-era"),
        ("youtube_pam", "Philip Anthony Mitchell YouTube channel", config.YOUTUBE_CHANNELS["pam"][0], "Gap-fill where 2819 has nothing for a chapter"),
        ("youtube_victory", "Victory World Church YouTube channel", config.YOUTUBE_CHANNELS["victory"][0], "Victory-era PAM; gap-fill only"),
    ]
    for i, row in enumerate(guide, 2):
        _row(sg, i, list(row), link_col=3)
    sg.cell(row=len(guide) + 3, column=1, value="Forbidden everywhere: search URLs, index/landing pages as a row's link, third-party transcript sites as the link, rows whose passage was inferred without opening the page.").font = Font(name=FONT, size=9, italic=True)

    path = os.path.join(OUT, "platt_pam_bible_companion.xlsx")
    wb.save(path)
    _log(f"wrote {path}")
    return path

# ---------------- HTML roadmap ----------------
HTML_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Platt + PAM — Bible listening companion</title>
<style>
:root{color-scheme:light dark;--bg:#faf8f4;--ink:#1d1c1a;--mute:#6b665e;--line:#e3ded5;--v2:#2f7d4f;--v1:#b7850f;--gap:#c0392b;--dev:#4a6fa5;--ov:#7a5ea8;--card:#ffffff;--accent:#1f3a4d;
 box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#14151a;--ink:#ece9e2;--mute:#9a968d;--line:#2c2e36;--card:#1d1f26;--accent:#9fc3dd}}
:root[data-theme="dark"]{--bg:#14151a;--ink:#ece9e2;--mute:#9a968d;--line:#2c2e36;--card:#1d1f26;--accent:#9fc3dd}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
header{padding:28px 20px 10px;max-width:1040px;margin:0 auto}
h1{font-size:28px;font-weight:600;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:14px;margin:0 0 14px}
.spine{display:grid;grid-template-columns:repeat(auto-fill,minmax(5px,1fr));gap:1px;max-width:1040px;margin:0 auto 6px;padding:0 20px}
.spine i{display:block;height:14px;background:var(--line);cursor:pointer}
.spine i.V2{background:var(--v2)}.spine i.V1{background:var(--v1)}.spine i.dev{background:var(--dev)}.spine i.ov{background:var(--ov)}.spine i.gap{background:var(--gap);opacity:.55}
.legend{max-width:1040px;margin:0 auto 18px;padding:0 20px;font-size:12.5px;color:var(--mute)}
.legend b{display:inline-block;width:10px;height:10px;margin:0 4px 0 10px;vertical-align:-1px}
.controls{max-width:1040px;margin:0 auto 10px;padding:0 20px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:14px}
.controls select,.controls button{font:inherit;padding:5px 8px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:4px}
main{max-width:1040px;margin:0 auto;padding:0 20px 60px}
.book{border-top:1px solid var(--line);padding:10px 0}
.book>summary{cursor:pointer;display:flex;gap:12px;align-items:baseline;list-style:none}
.book>summary::-webkit-details-marker{display:none}
.book>summary .n{color:var(--mute);width:26px;font-size:13px}
.book>summary .name{font-size:19px;font-weight:600;flex:1}
.book>summary .stat{font-size:13px;color:var(--mute)}
.book>summary label{font-size:13px;color:var(--mute)}
.ov{margin:8px 0 4px 38px}
.ch{margin:6px 0 6px 38px;display:grid;grid-template-columns:52px 1fr;gap:8px;align-items:start}
.ch .num{color:var(--mute);font-size:14px;padding-top:2px}
.ch.narr .num::after{content:attr(data-seq);display:block;font-size:11px;color:var(--mute)}
.e{padding:3px 0;font-size:15px}
.e a{color:var(--accent);text-decoration:none}.e a:hover{text-decoration:underline}
.e .t{font-size:12px;color:var(--mute);margin-left:6px}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:3px;color:#fff;margin-right:6px;vertical-align:1px}
.badge.V2{background:var(--v2)}.badge.V1{background:var(--v1)}.badge.gap{background:var(--gap)}.badge.dev{background:var(--dev)}.badge.ov{background:var(--ov)}
.gapline{color:var(--gap);font-size:14px}
.done summary .name{text-decoration:line-through;color:var(--mute)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:600px){.ch{grid-template-columns:40px 1fr;margin-left:0}.ov{margin-left:0}h1{font-size:23px}}
</style></head><body>
<header><h1>Platt + PAM — Bible listening companion</h1>
<p class="sub">Every chapter of the Bible, with the David Platt and Philip Anthony Mitchell teaching that covers it. Built __DATE__.</p></header>
<div class="spine" id="spine" aria-label="Coverage by chapter, Genesis 1 to Revelation 22"></div>
<p class="legend">Each cell is one chapter. <b style="background:var(--v2)"></b>verified sermon <b style="background:var(--v1)"></b>unconfirmed sermon <b style="background:var(--dev)"></b>Pray the Word only <b style="background:var(--ov)"></b>book overview only <b style="background:var(--gap);opacity:.55"></b>verified gap</p>
<div class="controls">
 <select id="order"><option value="canon">Standard Bible order</option><option value="narr">Narrative order (your EPUB)</option></select>
 <select id="preacher"><option value="">All preachers</option><option value="Platt">Platt</option><option value="PAM">PAM</option></select>
 <select id="track"><option value="">All tracks</option><option value="sermon">Sermons</option><option value="devotional">Pray the Word</option><option value="overview">Overviews</option></select>
 <select id="tier"><option value="">V2 + V1</option><option value="V2">V2 only</option></select>
 <button id="expand">Expand all</button><button id="collapse">Collapse all</button>
 <span id="progress" style="color:var(--mute);font-size:13px"></span>
</div>
<main id="main"></main>
<script>
const DATA=__DATA__;
const $=s=>document.querySelector(s);
const store={get(k){try{return JSON.parse(localStorage.getItem('ppc:'+k))}catch(e){return null}},set(k,v){try{localStorage.setItem('ppc:'+k,JSON.stringify(v))}catch(e){}}};
let done=store.get('done')||{};
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function entryHTML(e){const b=e.track==='devotional'?'dev':(e.track==='overview'?'ov':e.tier);
 return `<div class="e"><span class="badge ${b}">${e.track==='devotional'?'PTW':(e.track==='overview'?'Overview':e.tier)}</span><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a><span class="t">${esc(e.preacher)}${e.passage?' · '+esc(e.passage):''}${e.duration?' · '+Math.round(e.duration/60)+' min':''}</span></div>`}
function filt(e){const p=$('#preacher').value,t=$('#track').value,tr=$('#tier').value;
 if(p&&!e.preacher.startsWith(p))return false; if(t&&e.track!==t)return false; if(tr&&e.tier!==tr)return false; return true}
function render(){const order=$('#order').value;const main=$('#main');main.innerHTML='';
 const books=DATA.books.slice(); if(order==='narr')books.sort((a,b)=>a.firstSeq-b.firstSeq);
 let finished=0;
 for(const bk of books){const isDone=!!done[bk.name]; if(isDone)finished++;
  const chs=bk.chapters.slice(); if(order==='narr')chs.sort((a,b)=>a.seq-b.seq);
  const ovs=bk.overviews.filter(filt);
  const det=document.createElement('details');det.className='book'+(isDone?' done':'');det.open=!!store.get('open:'+bk.name);
  det.innerHTML=`<summary><span class="n">${bk.idx}</span><span class="name">${esc(bk.name)}</span><span class="stat">${bk.n} ch · ${bk.v2} verified sermon ch · ${bk.gaps} gaps</span><label><input type="checkbox" ${isDone?'checked':''} data-book="${esc(bk.name)}"> finished</label></summary>`;
  const body=document.createElement('div');
  if(ovs.length)body.innerHTML+=`<div class="ov">${ovs.map(entryHTML).join('')}</div>`;
  for(const c of chs){const es=c.entries.filter(filt);
   let inner=es.length?es.map(entryHTML).join(''):(c.status==='Verified gap'||c.status==='Overview only'?`<div class="gapline">No Platt or PAM teaching found for this chapter</div>`:`<div class="gapline" style="color:var(--mute)">Nothing matches the current filters</div>`);
   body.innerHTML+=`<div class="ch ${order==='narr'?'narr':''}"><div class="num" data-seq="#${c.seq}">${c.ch}</div><div>${inner}</div></div>`}
  det.appendChild(body);det.addEventListener('toggle',()=>store.set('open:'+bk.name,det.open));main.appendChild(det)}
 $('#progress').textContent=`${finished} of 66 books marked finished`;
 main.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change',ev=>{done[cb.dataset.book]=cb.checked;store.set('done',done);render()}));
}
function spine(){const s=$('#spine');s.innerHTML='';for(const bk of DATA.books)for(const c of bk.chapters){const i=document.createElement('i');
 i.className={'Sermon V2':'V2','Sermon V1':'V1','Devotional only':'dev','Overview only':'ov','Verified gap':'gap'}[c.status]||'';
 i.title=`${bk.name} ${c.ch} — ${c.status}`;i.tabIndex=0;i.addEventListener('click',()=>{const d=[...document.querySelectorAll('.book')].find(x=>x.querySelector('.name').textContent===bk.name);if(d){d.open=true;d.scrollIntoView({behavior:'smooth'})}});s.appendChild(i)}}
['order','preacher','track','tier'].forEach(id=>$('#'+id).addEventListener('change',render));
$('#expand').onclick=()=>document.querySelectorAll('.book').forEach(d=>d.open=true);
$('#collapse').onclick=()=>document.querySelectorAll('.book').forEach(d=>d.open=false);
spine();render();
</script></body></html>"""

def write_html(chapter_entries, book_overviews, status, narr):
    os.makedirs(OUT, exist_ok=True)
    books = []
    for bi, (book, abbr, n, t, _a) in enumerate(BOOKS, 1):
        chs = []
        for c in range(1, n + 1):
            es = sorted(chapter_entries.get((book, c), []), key=lambda x: (x["track"] != "sermon", x["speaker"] != "Platt", x["tier"] != "V2"))
            chs.append({"ch": c, "seq": narr[(book, c)], "status": status[(book, c)]["status"],
                        "entries": [{"title": e["title"], "url": e.get("primary_url", e["url"]), "preacher": preacher_label(e),
                                     "track": e["track"], "tier": e["tier"], "passage": e["refs_text"],
                                     "duration": int(e["duration"]) if str(e["duration"]).isdigit() else 0} for e in es]})
        ovs = [{"title": e["title"], "url": e.get("primary_url", e["url"]), "preacher": preacher_label(e), "track": "overview",
                "tier": e["tier"], "passage": e["refs_text"], "duration": int(e["duration"]) if str(e["duration"]).isdigit() else 0}
               for e in book_overviews.get(book, [])]
        books.append({"idx": bi, "name": book, "n": n, "firstSeq": min(c["seq"] for c in chs),
                      "v2": sum(1 for c in chs if c["status"] == "Sermon V2"),
                      "gaps": sum(1 for c in chs if c["status"] in ("Verified gap", "Overview only")),
                      "overviews": ovs, "chapters": chs})
    data = {"books": books}
    page = HTML_TMPL.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")) \
                    .replace("__DATE__", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    path = os.path.join(OUT, "roadmap.html")
    open(path, "w", encoding="utf-8").write(page)
    _log(f"wrote {path}")
    return path

def run():
    entries = load_entries()
    narr = narrative_map()
    chapter_entries, book_overviews, guests, review, status = assemble(entries)
    x = write_xlsx(entries, chapter_entries, book_overviews, guests, review, status, narr)
    h = write_html(chapter_entries, book_overviews, status, narr)
    counts = defaultdict(int)
    for s in status.values(): counts[s["status"]] += 1
    _log("chapter status: " + json.dumps(dict(counts)))
    return x, h, dict(counts)

if __name__ == "__main__":
    run()
