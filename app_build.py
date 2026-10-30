"""Build out/scripture-companion.html — a single-file, installable web app:
podcast-style player (Media Session lock-screen controls, resume, speed, auto-advance),
books → chapters → episodes with progress bars, Secret Church in order, Pray the Word list.
Progress lives in localStorage; export/import as JSON. Run: python app_build.py
"""
from __future__ import annotations
import json, os, re
from collections import defaultdict
from canon import BOOKS, CHAPTERS, TESTAMENT
from refs import parse_refs
import config

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(HERE, "data", "catalog_verified.jsonl")
NARR = os.path.join(HERE, "data", "narrative_order.json")
VERSION = 22  # bump on every shipped build; also busts the service-worker cache
OUT = os.path.join(HERE, "out", f"scripture-companion-v{VERSION}.html")
SITE = os.path.join(HERE, "out", "site")  # deploy this folder (Netlify drop / GitHub Pages)
PWA = os.path.join(HERE, "pwa")

def audio_url(e: dict) -> str | None:
    """Publisher audio file for an entry. Buzzsprout serves <episode page>.mp3; the feeds confirmed the pattern."""
    if e.get("audio_override"):
        return e["audio_override"]
    for u in [e.get("primary_url") or e["url"]] + e.get("alt_urls", []):
        if re.search(r"buzzsprout\.com/\d+/episodes/\d+-[\w-]+$", u):
            return u + ".mp3"
    for u in [e["url"]] + e.get("alt_urls", []):
        m = re.search(r"buzzsprout\.com/(\d+)/(\d+)$", u)
        if m:  # short id form: Buzzsprout redirects the id-only mp3 to the full file
            return f"https://www.buzzsprout.com/{m.group(1)}/{m.group(2)}.mp3"
    return None

def iso_date(s) -> str:
    """'Sun, 04 Feb 2024 02:00:00 -0600' (RSS) or '2024-02-04…' -> '2024-02-04'."""
    s = (s or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s): return s[:10]
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return ""

def main():
    entries = [json.loads(l) for l in open(VERIFIED, encoding="utf-8")]
    narr = {(o["book"], o["chapter"]): o["seq"] for o in json.load(open(NARR))}
    usable = [e for e in entries if e["tier"] in ("V2", "V1") and e["speaker"] in ("Platt", "PAM")]
    items, by_chapter, by_book_ov, spans = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    item_books, title_states = {}, {}
    order = [b[0] for b in BOOKS]; OT = order[:39]; NT = order[39:]
    def span_label(bks):
        if set(bks) >= set(OT): return "the Old Testament"
        if set(bks) >= set(NT): return "the New Testament"
        lands = [("Genesis","Deuteronomy","The Law"),("Joshua","Esther","History"),("Job","Song of Solomon","Wisdom & Song"),("Isaiah","Daniel","Major Prophets"),("Hosea","Malachi","Minor Prophets"),("Matthew","John","The Gospels"),("Acts","Acts","The Church Begins"),("Romans","Philemon","Letters of Paul"),("Hebrews","Jude","General Letters")]
        for a, z, lab in lands:
            if set(bks) == set(order[order.index(a):order.index(z)+1]): return lab
        idx = sorted(order.index(b) for b in bks)
        return f"{order[idx[0]]}–{order[idx[-1]]}" if idx[-1]-idx[0] == len(idx)-1 else ", ".join(bks)
    for e in usable:
        it = {"id": e["id"], "t": e["title"], "who": "PAM" if e["speaker"] == "PAM" else "Platt",
              "era": e["era"], "tr": e["track"], "src": e["source"], "url": e.get("primary_url") or e["url"],
              "audio": audio_url(e), "dur": int(e["duration"]) if str(e["duration"]).isdigit() else 0,
              "date": iso_date(e.get("published")), "pass": e.get("refs_text", ""), "tier": e["tier"],
              "sc": [e.get("sc_season"), e.get("sc_episode")] if e.get("sc_season") else None}
        items[it["id"]] = it
        item_books[it["id"]] = set(e["refs"])
        title_states[it["id"]] = bool(parse_refs(e["title"]))
        ov_books = [b for b, d in e["refs"].items() if e["track"] == "overview" and (d["whole_book"] or len(d["chapters"]) / CHAPTERS[book] >= 0.6)] if False else \
                   [b for b, d in e["refs"].items() if e["track"] == "overview" and (d["whole_book"] or len(d["chapters"]) / CHAPTERS[b] >= 0.6)]
        if len(ov_books) > 1:
            ov_books.sort(key=order.index)
            spans[ov_books[0]].append({"label": span_label(ov_books), "id": it["id"], "books": ov_books})
        for book, d in e["refs"].items():
            if book in ov_books:
                if len(ov_books) == 1: by_book_ov[book].append(it["id"])
            else:
                for c in d["chapters"]:
                    by_chapter[(book, c)].append(it["id"])
    def core(t):  # title without episode numbers, "| Speaker" tails, or (Bible reference) brackets
        t = re.sub(r"^\s*#?[\d,]+\s*[\u2013\u2014-]\s*", "", t or "")
        t = re.sub(r"\s*\|.*$", "", t)
        t = re.sub(r"\(([^)]*)\)", lambda m: "" if parse_refs(m.group(1)) else " " + m.group(1), t)
        t = re.sub(r"[^a-z0-9]+", " ", t.lower().replace("\u2019", "'")).strip()
        return re.sub(r"\bpart (\w+)\b", r"part \1", t)
    SRC_PREF = {"platt_messages": 0, "ptw": 0, "2819_podcast": 0, "secret_church_podcast": 0, "twr360_secret_church": 1,
                "mclean_podcast": 2, "radical_message": 3, "victory_podcast": 3}
    for k, lst in by_chapter.items():  # one teaching, one entry: keep the best form of same-titled items
        best = {}
        for i in lst:
            key = (core(items[i]["t"]), items[i]["who"])
            score = (not items[i]["audio"], SRC_PREF.get(items[i]["src"], 5), i)
            if key not in best or score < best[key][0]: best[key] = (score, i)
        keep = {v[1] for v in best.values()}
        lst[:] = [i for i in lst if i in keep]
    for k, lst in by_chapter.items():  # 2819 first; Victory-era only where 2819 has nothing
        if any(items[i]["who"] == "PAM" and items[i]["era"] == "2819" and items[i]["tr"] == "sermon" for i in lst):
            lst[:] = [i for i in lst if not (items[i]["who"] == "PAM" and items[i]["era"] != "2819")]
    # Ranking inside a chapter: teaching from a run through this book first (a series), then teaching
    # whose own title names the passage, then the rest; newest first within each.
    from datetime import date as _d
    def _day(i):
        try: return _d.fromisoformat(items[i]["date"]).toordinal()
        except ValueError: return None
    by_book_sermons = defaultdict(list)
    for i, it in items.items():
        if it["tr"] == "sermon" and _day(i):
            for b in item_books[i]: by_book_sermons[(b, it["who"])].append(_day(i))
    def focus(i, book):
        it, d = items[i], _day(i)
        if it["tr"] == "sermon" and d and sum(1 for x in by_book_sermons[(book, it["who"])] if abs(x - d) <= 90) >= 3:
            return 2
        return 1 if title_states[i] else 0
    rank = lambda book: (lambda i: (items[i]["tr"] != "sermon", not items[i]["audio"], -focus(i, book),
                                    items[i]["who"] != "Platt", -(_day(i) or 0), i))
    books = []
    for name, abbr, n, t, _a in BOOKS:
        chs = []
        for c in range(1, n + 1):
            ids = sorted(set(by_chapter.get((name, c), [])), key=rank(name))
            chs.append({"c": c, "seq": narr[(name, c)], "ids": ids})
        ov = sorted(set(by_book_ov.get(name, [])), key=lambda i: (items[i]["sc"] or [99, 99], items[i]["date"], i))
        # drop a Secret Church event page when its podcast episodes or video sessions are present
        if any(items[i]["src"] in ("secret_church_podcast", "youtube_radical", "twr360_secret_church") for i in ov):
            ov = [i for i in ov if items[i]["src"] != "secret_church"]
        sp = sorted(spans.get(name, []), key=lambda x: (x["label"], items[x["id"]]["sc"] or [99, 99]))
        if any(items[x["id"]]["src"] in ("secret_church_podcast", "youtube_radical", "twr360_secret_church") for x in sp):
            sp = [x for x in sp if items[x["id"]]["src"] != "secret_church"]
        books.append({"name": name, "abbr": abbr, "n": n, "t": t, "ov": ov, "spans": sp, "ch": chs})
    sc_events = [{"n": n, "title": title, "url": url, "scope": scope} for n, title, url, scope in config.SECRET_CHURCH_EVENTS]
    sc_items = sorted([i for i in items.values() if i["sc"]], key=lambda i: (i["sc"][0], i["sc"][1]))
    ptw = sorted([i for i in items.values() if i["tr"] == "devotional"], key=lambda i: i["date"])
    data = {"built": __import__("datetime").date.today().isoformat(), "items": items, "books": books,
            "sc": {"events": sc_events, "ids": [i["id"] for i in sc_items]}, "ptw": [i["id"] for i in ptw]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    n_audio = sum(1 for i in items.values() if i["audio"])
    print(f"wrote {OUT}: {len(items)} items, {n_audio} with in-app audio")
    write_site(html)

def write_site(html: str):
    """out/site/: index.html + manifest + icons + service worker — the installable home-screen app."""
    import shutil
    os.makedirs(SITE, exist_ok=True)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(html)
    for f in os.listdir(PWA):
        if f == "sw.js":
            src = open(os.path.join(PWA, f), encoding="utf-8").read().replace("__VERSION__", str(VERSION))
            open(os.path.join(SITE, f), "w", encoding="utf-8").write(src)
        elif not f.startswith("."):
            shutil.copy(os.path.join(PWA, f), os.path.join(SITE, f))
    print(f"wrote {SITE}/ (deploy this folder)")

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#f4efe3"><title>Scripture Companion</title>
<link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="icon-180.png"><link rel="icon" href="icon.svg" type="image/svg+xml">
<meta name="apple-mobile-web-app-title" content="Companion"><meta name="mobile-web-app-capable" content="yes">
<style>
:root{color-scheme:light;--bg:#f4efe3;--ink:#1b2440;--mute:#6b7390;--line:rgba(27,36,64,.12);--gold:#c9a24a;--gold2:#a8812a;--card:rgba(255,255,255,.78)}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",Inter,system-ui,sans-serif;overflow-x:hidden}
.serif{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
/* world */
.world{position:relative;background:linear-gradient(180deg,#eef3fb 0%,#f4efe3 18%,#efe6d9 40%,#e9e4ef 58%,#f3e6d6 76%,#fbf0d4 90%,#fff7dc 100%)}
.world > svg{display:block;width:100%}.world svg svg{overflow:visible}
.land{font:600 10px -apple-system,system-ui,sans-serif;fill:rgba(168,129,42,.95);letter-spacing:.18em;text-transform:uppercase}
.bl{font:15px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;fill:rgba(27,36,64,.55)}.bl.big{font-size:19px;fill:rgba(27,36,64,.9)}.bl.here{fill:var(--gold2)}
.you{filter:drop-shadow(0 0 12px rgba(201,162,74,.9))}
.glow{filter:blur(28px);opacity:.55}
/* clearing: the chapter where you stand, placed in the world */
.clearing{position:absolute;width:min(340px,92vw);z-index:3;padding:14px 14px 16px;border-radius:22px;background:linear-gradient(180deg,rgba(255,255,255,.55),rgba(255,255,255,.92) 18%,rgba(255,255,255,.92) 85%,rgba(255,255,255,.55));backdrop-filter:blur(8px);box-shadow:0 10px 40px rgba(27,36,64,.10)}
.clearing .where{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--gold)}
.scene{font:italic 15px "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:var(--gold2);margin:-4px 0 10px;display:flex;align-items:center;gap:8px}
.clearing .ch{font-size:30px;line-height:1.05;margin:2px 0 8px}
.voice{display:flex;align-items:center;gap:10px;padding:8px 10px;margin:5px 0;background:var(--card);border:1px solid rgba(27,36,64,.08);border-radius:16px}
.voice .pb{width:42px;height:42px;border-radius:50%;flex:none;border:0;background:conic-gradient(var(--gold) var(--p,0deg),rgba(27,36,64,.10) 0);display:flex;align-items:center;justify-content:center;color:var(--ink);font-size:18px;cursor:pointer}
.voice .pb::before{content:"";position:absolute;width:35px;height:35px;border-radius:50%;background:#fff}
.voice .pb span{position:relative}
.voice .pb.playing span{color:var(--gold2)}.voice .pb.off{opacity:.35}
.voice .tx{flex:1;min-width:0}.voice .who{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute)}
.voice .ti{font-size:14px;line-height:1.25;margin:1px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.voice .ln{font-size:12px;color:var(--mute)}
.voice.done .ti{color:var(--mute)}.voice .ck{flex:none;background:none;border:1px solid rgba(27,36,64,.15);color:var(--mute);width:30px;height:30px;border-radius:50%;font-size:14px}
.voice.done .ck{background:var(--gold);color:#fff;border-color:var(--gold)}
.acts{display:flex;gap:10px;margin:12px 0 0}
.acts button{font:inherit;border-radius:22px;padding:10px 18px;border:1px solid rgba(27,36,64,.15);background:rgba(255,255,255,.6);color:var(--ink)}
.acts .go{background:var(--gold);color:#1b2440;border-color:var(--gold);font-weight:600}
.acts .read.on{background:rgba(201,162,74,.18);color:var(--gold2);border-color:var(--gold)}
.enter{margin:0 0 8px}.enter summary{list-style:none;cursor:pointer;font-size:13px;color:var(--mute)}.enter summary::-webkit-details-marker{display:none}
.empty{font-size:14px;color:var(--mute);padding:8px 2px}
.more{background:none;border:0;color:var(--gold2);font:inherit;font-size:13px;padding:6px 2px}
/* top */
.top{position:fixed;top:0;right:0;z-index:6;padding:calc(10px + env(safe-area-inset-top)) 14px 10px}
.top .pct{font-size:13px;color:var(--mute)}.top .pct b{color:var(--gold2);font-weight:600}
.top button{background:rgba(255,255,255,.7);border:1px solid rgba(27,36,64,.12);color:var(--ink);border-radius:16px;padding:6px 12px;font:inherit;font-size:13px}
/* now playing */
#np{position:fixed;left:0;right:0;bottom:0;z-index:9;transform:translateY(110%);transition:transform .35s cubic-bezier(.2,.8,.2,1);background:rgba(255,255,255,.86);backdrop-filter:blur(24px);border-top:1px solid rgba(27,36,64,.1);box-shadow:0 -10px 40px rgba(27,36,64,.12);border-radius:24px 24px 0 0;padding:14px 20px calc(16px + env(safe-area-inset-bottom))}
#np.on{transform:none}
#np .grab{width:40px;height:4px;border-radius:2px;background:rgba(27,36,64,.2);margin:0 auto 12px}
#np .t{font-size:20px;line-height:1.2;color:var(--ink)}#np .s{color:var(--mute);font-size:13px;margin-top:3px}
#np input[type=range]{width:100%;accent-color:var(--gold);margin:14px 0 2px}
#np .times{display:flex;justify-content:space-between;color:var(--mute);font-size:11px}
#np .ctl{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
#np .ctl button{background:none;border:0;color:var(--ink);font:inherit;font-size:15px;padding:10px}
#np .ctl .big{width:64px;height:64px;border-radius:50%;background:var(--gold);color:#1b2440;font-size:26px}
#np.mini{padding-top:10px}#np.mini .grab,#np.mini .times,#np.mini input,#np.mini .ctl .side{display:none}#np.mini .ctl{margin:0}#np.mini .t{font-size:15px}#np.mini .ctl .big{width:44px;height:44px;font-size:18px}
.settings{padding:calc(70px + env(safe-area-inset-top)) 20px 60px;max-width:560px}
.settings .note{color:var(--mute);font-size:14px;line-height:1.5}textarea{width:100%;height:110px;background:#fff;color:var(--ink);border:1px solid var(--line);border-radius:8px;font:12px/1.4 ui-monospace,monospace}
.btn{background:#fff;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:10px 14px;font:inherit;margin:4px 6px 4px 0}
</style></head><body>
<div class="top"><span id="pct" style="display:none"></span><button id="gear">⋯</button></div>
<div id="main"></div>
<div id="np"><div class="grab"></div><div class="t serif" id="np-t"></div><div class="s" id="np-s"></div>
<input type="range" id="seek" min="0" max="1000" value="0"><div class="times"><span id="cur">0:00</span><span id="rem">-0:00</span></div>
<div class="ctl"><button class="side" id="spd">1×</button><button class="side" id="bk">↺ 15</button><button class="big" id="pp" style="display:flex;align-items:center;justify-content:center"></button><button class="side" id="fw">30 ↻</button><button class="side" id="zz">Sleep off</button><button id="cls">✕</button></div></div>
<audio id="audio" preload="metadata"></audio>
<script>
const D=__DATA__,I=D.items;
const S={get(k,d){try{const v=localStorage.getItem('sc:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},set(k,v){try{localStorage.setItem('sc:'+k,JSON.stringify(v))}catch(e){}}};
let prog=S.get('prog',{}),read=S.get('read',{}),cfg=S.get('cfg',{order:'canon',who:''}),view=S.get('view','walk'),camp=S.get('camp',null);
const okWho=id=>!cfg.who||I[id].who===cfg.who;
// --- denser scenery: terrain everywhere, per-book motifs, more vignettes, celestial bodies, rivers ---
const MOTIF={'The Law':'palm','History':'town','Wisdom & Song':'olive','Major Prophets':'cedar','Minor Prophets':'town','The Gospels':'olive','The Church Begins':'sail','Letters of Paul':'column','General Letters':'fire','The New Beginning':'tree'};
function motif(kind,x,y,sc=1){const d=x<195?1:-1;return `<g transform="translate(${x} ${y}) scale(${d*sc} ${sc})" fill="none" stroke="${G}.28)" stroke-width="1" stroke-linecap="round"><path d="M0 0 c14 -10 30 -8 38 4 c6 10 -4 18 -12 12 c-6 -6 2 -14 8 -8 M0 0 c-8 -12 -8 -26 2 -36 c8 -8 20 -6 22 4 c2 8 -8 12 -12 6 c-3 -5 3 -10 8 -6"/><circle cx="26" cy="8" r="1.4" fill="${G}.5)" stroke="none"/><circle cx="4" cy="-30" r="1.4" fill="${G}.5)" stroke="none"/></g>`}
const I_='rgba(60,80,160,';function terrain(H){let out='';for(let y=160;y<H;y+=560){const k=y/560;out+=hills(y+40,20+(k%3)*6,.045,I_,k*137)+hills(y+140,14,.03,I_,k*89+200)}return out}
function celestial(H){return `<circle cx="195" cy="-60" r="420" fill="url(#dawn)"/><g stroke="${G}.10)" stroke-width="1">${[-70,-50,-30,-10,10,30,50,70].map(a=>`<line x1="195" y1="-40" x2="${195+Math.sin(a*Math.PI/180)*900}" y2="${-40+Math.cos(a*Math.PI/180)*900}"/>`).join('')}</g><circle cx="195" cy="${H-60}" r="700" fill="url(#glory)"/><g stroke="${G}.14)" stroke-width="1">${[-80,-60,-40,-20,0,20,40,60,80].map(a=>`<line x1="195" y1="${H-60}" x2="${195+Math.sin(a*Math.PI/180)*900}" y2="${H-60-Math.cos(a*Math.PI/180)*900}"/>`).join('')}</g>`}
function river(x,y,op=.22){return `<path d="M0 ${y-6} C 60 ${y-26} 120 ${y+14} 190 ${y} S 320 ${y-22} 390 ${y+4} v18 C 320 ${y+2} 260 ${y+26} 190 ${y+18} S 60 ${y-4} 0 ${y+12}z" fill="${B}${op})"/>`}
function vignette2(kind,x,y){const t=`transform="translate(${x} ${y})"`;
 switch(kind){
 case 'sun':return `<g ${t}><circle cx="0" cy="-60" r="34" fill="url(#halo)"/><circle cx="0" cy="-60" r="10" fill="${G}.7)"/>${[0,1,2,3,4,5,6,7].map(i=>`<line x1="${Math.cos(i*Math.PI/4)*16}" y1="${-60+Math.sin(i*Math.PI/4)*16}" x2="${Math.cos(i*Math.PI/4)*26}" y2="${-60+Math.sin(i*Math.PI/4)*26}" stroke="${G}.45)" stroke-width="1.4"/>`).join('')}</g>`;
 case 'serpent':return `<g ${t} stroke="${G}.4)" fill="${G}.10)" stroke-width="1.4"><path d="M-70 10 v-30"/><circle cx="-70" cy="-54" r="18"/><circle cx="-82" cy="-44" r="12"/><circle cx="-58" cy="-44" r="12"/><circle cx="-76" cy="-50" r="2.5" fill="${G}.9)"/><circle cx="-62" cy="-46" r="2.5" fill="${G}.9)"/><path d="M60 10 c6 -14 -8 -20 -4 -32 4 -8 14 -8 16 -2 2 8 -10 10 -12 2" fill="none"/></g>`;
 case 'tent':return `<g ${t} fill="${W_}.12)"><path d="M-100 10 l24 -28 24 28z M-40 10 l18 -20 18 20z M40 10 l28 -32 28 32z"/><path d="M110 10 v-50 M110 -40 c-16 -4 -26 -14 -28 -28 14 2 24 10 28 28 c4 -18 14 -26 28 -28 -2 14 -12 24 -28 28" stroke="${G}.35)" fill="none" stroke-width="1.5"/></g>`;
 case 'altar':return `<g ${t}><path d="M-90 10 L0 -70 L90 10Z" fill="${W_}.08)"/><rect x="-16" y="-20" width="32" height="12" fill="${W_}.2)"/><circle cx="0" cy="-30" r="16" fill="url(#ember)"/></g>`;
 case 'coat':return `<g ${t}><path d="M-120 10 q60 -20 120 0 t120 0" stroke="${G}.18)" fill="none" stroke-width="2"/>${[-70,-40,-10,20,50].map(cx=>`<path d="M${cx} 4 l6 -14 8 0 6 14z M${cx+6} -10 l4 -8 4 8" fill="${W_}.14)"/>`).join('')}</g>`;
 case 'flame':return `<g ${t}><circle cx="70" cy="-30" r="44" fill="url(#ember)"/><g stroke="${G}.4)" fill="none" stroke-width="1.3"><path d="M70 -6 c-14 -2 -22 -10 -22 -22 M70 -6 c14 -2 22 -10 22 -22 M70 -6 c-8 -10 -8 -20 -2 -30 M70 -6 c8 -10 8 -20 2 -30 M70 -6 v-12"/></g></g>`;
 case 'grapes':return `<g ${t} fill="${G}.22)" stroke="${G}.4)" stroke-width="1"><path d="M-80 10 c0 -30 20 -40 40 -40 M-40 -30 c20 0 40 10 40 40" fill="none"/>${[-50,-40,-30,-45,-35,-40].map((cx,i)=>`<circle cx="${cx}" cy="${-22+(i>2?10:0)+(i>4?10:0)}" r="5"/>`).join('')}</g>`;
 case 'pillars':return `<g ${t} fill="${W_}.12)"><rect x="-60" y="-70" width="14" height="70" transform="rotate(-10 -53 -35)"/><rect x="46" y="-70" width="14" height="70" transform="rotate(10 53 -35)"/><path d="M-70 -70 h140 l-10 -12 h-120z" transform="rotate(-3)"/></g>`;
 case 'wheat':return `<g ${t} stroke="${G}.35)" fill="none" stroke-width="1.2">${[-90,-75,-60,-45,-30,30,45,60,75,90].map((cx,i)=>`<path d="M${cx} 10 v-${28+(i%3)*6} M${cx} -${20+(i%3)*6} l-5 -6 M${cx} -${26+(i%3)*6} l5 -6 M${cx} -${30+(i%3)*6} l-5 -6"/>`).join('')}</g>`;
 case 'stone':return `<g ${t} fill="${W_}.12)"><path d="M-110 10 q60 -16 220 0z"/><path d="M40 10 v-50 l10 -26 10 26 v50z" /><circle cx="-40" cy="-14" r="6" fill="${W_}.3)"/><path d="M-40 -14 q30 -40 70 -40" stroke="${W_}.25)" fill="none" stroke-dasharray="3 4"/></g>`;
 case 'crown':return `<g ${t}><circle cx="0" cy="-30" r="70" fill="url(#halo)"/><path d="M-40 0 h80 l-6 -40 -18 14 -16 -30 -16 30 -18 -14z" fill="${G}.35)"/></g>`;
 case 'house':return `<g ${t} fill="${W_}.12)"><path d="M-80 10 v-30 l30 -22 30 22 v30z M-62 10 v-18 h22 v18z"/><path d="M20 10 v-24 l24 -18 24 18 v24z" opacity=".7"/><path d="M-120 10 h240" stroke="${W_}.2)"/></g>`;
 case 'wall':return `<g ${t} fill="${W_}.12)"><rect x="-130" y="-30" width="260" height="30"/>${[-130,-110,-90,-70,-50,-30,-10,10,30,50,70,90,110].map(cx=>`<rect x="${cx+3}" y="-40" width="12" height="10"/>`).join('')}<rect x="-20" y="-56" width="40" height="56" /><rect x="-24" y="-66" width="48" height="10"/></g>`;
 case 'wind':return `<g ${t} stroke="${W_}.25)" fill="none" stroke-width="1.6"><path d="M-110 -20 c30 -20 60 20 90 0 s60 -20 90 0 M-100 0 c30 -20 60 20 90 0 s60 -20 90 0 M-90 20 c30 -20 60 20 90 0 s60 -20 90 0"/></g>`;
 case 'staff':return `<g ${t}><path d="M-130 10 q65 -30 130 -10 t130 10z" fill="${W_}.08)"/>${[-60,-30,10,40,70].map(cx=>`<ellipse cx="${cx}" cy="-8" rx="9" ry="6" fill="${W_}.3)"/>`).join('')}<path d="M-90 0 v-50 a8 8 0 0 1 16 0" stroke="${G}.5)" fill="none" stroke-width="2"/></g>`;
 case 'eye':return `<g ${t}><circle cx="0" cy="-50" r="80" fill="url(#halo)"/>${[-60,-40,-20,0,20,40,60].map(a=>`<line x1="0" y1="-50" x2="${Math.sin(a*Math.PI/180)*150}" y2="${-50-Math.cos(a*Math.PI/180)*150}" stroke="${G}.2)"/>`).join('')}<path d="M-30 -30 h60 v30 h-60z" fill="${G}.3)"/></g>`;
 case 'lamb':return `<g ${t}><path d="M-120 10 q60 -20 240 0z" fill="${W_}.08)"/><path d="M-20 0 a20 14 0 0 1 40 0z M-14 0 v8 M14 0 v8 M18 -14 l8 -6" fill="${W_}.35)" stroke="${W_}.35)"/><path d="M60 0 v-60 M46 -44 h28" stroke="${W_}.3)" stroke-width="2"/></g>`;
 case 'scroll':return `<g ${t} fill="${W_}.12)"><path d="M-50 -60 h100 v70 h-100z"/><g stroke="${W_}.25)">${[-44,-32,-20,-8,4].map(yy=>`<line x1="-40" y1="${yy}" x2="40" y2="${yy}"/>`).join('')}</g><circle cx="-50" cy="-60" r="6"/><circle cx="50" cy="-60" r="6"/></g>`;
 case 'bones':return `<g ${t} stroke="${W_}.3)" stroke-width="3" stroke-linecap="round">${[[-90,0,-60,-14],[-40,4,-6,2],[20,-6,52,6],[70,2,100,-10],[-70,-30,-40,-26]].map(([a,b,c,d])=>`<line x1="${a}" y1="${b}" x2="${c}" y2="${d}"/>`).join('')}</g>`;
 case 'star':return `<g ${t}><circle cx="0" cy="-90" r="60" fill="url(#halo)"/><circle cx="0" cy="-90" r="2.5" fill="${G}.95)"/><path d="M0 -120 v60 M-30 -90 h60" stroke="${G}.35)"/><path d="M-120 10 q60 -24 120 -6 t120 6z" fill="${W_}.08)"/></g>`;
 case 'lamp':return `<g ${t}><circle cx="0" cy="-40" r="60" fill="url(#halo)"/><path d="M-40 0 h80 M0 0 v-40 M-30 -40 h60 M-30 -40 v-14 M-15 -40 v-20 M0 -40 v-26 M15 -40 v-20 M30 -40 v-14" stroke="${G}.5)" stroke-width="2" fill="none"/></g>`;
 case 'figure':return `<g ${t}><path d="M-140 10 q70 -30 280 0z" fill="${W_}.08)"/><path d="M-30 -2 l0 -22 M-30 -24 a4 4 0 1 1 .1 0 M-30 -18 l-8 10 M-30 -18 l10 8 M-30 -2 l-6 12 M-30 -2 l8 12" stroke="${W_}.45)" fill="none" stroke-width="1.6"/><path d="M60 -2 l0 -24 M60 -26 a4 4 0 1 1 .1 0 M60 -18 l-12 -6 M60 -18 l12 -6 M60 -2 l-6 12 M60 -2 l6 12" stroke="${G}.6)" fill="none" stroke-width="1.6"/></g>`;
 case 'tomb':return `<g ${t}><path d="M-60 10 v-40 a60 40 0 0 1 120 0 v40z" fill="${W_}.10)"/><circle cx="-30" cy="-10" r="22" fill="rgba(255,255,255,.9)" stroke="${W_}.2)"/></g>`;
 case 'lightning':return `<g ${t}><circle cx="0" cy="-60" r="70" fill="url(#halo)"/><path d="M10 -130 l-22 50 h20 l-16 60 l40 -74 h-20 l16 -36z" fill="${G}.55)"/></g>`;
 case 'dove':return `<g ${t}><path d="M-20 -40 c10 -16 30 -16 40 -4 8 -4 20 -2 26 4 l-10 2 c-10 10 -30 14 -46 8 -8 -2 -10 -6 -10 -10z" fill="${W_}.4)"/><path d="M-110 10 q110 -30 220 0z" fill="${W_}.06)"/></g>`;
 case 'heart':return `<g ${t}><circle cx="0" cy="-40" r="60" fill="url(#halo)"/><path d="M0 -10 s-30 -18 -30 -40 a16 16 0 0 1 30 -8 16 16 0 0 1 30 8c0 22 -30 40 -30 40z" fill="${G}.35)"/></g>`;
 }return vignette(kind,x,y,0)}

const G='rgba(168,129,42,',W_='rgba(27,36,64,',B='rgba(70,120,200,';
let HH=4000;function hills(y,amp,op,col,phase=0){let d=`M0 ${y+amp}`;for(let x=0;x<=390;x+=10){d+=` L${x} ${(y+amp*Math.sin((x+phase)/62)).toFixed(1)}`}return `<path d="${d}" fill="none" stroke="${col}${Math.min(.35,op*4)})" stroke-width="1"/>`}
function sceneSVG(kind,x,y){
 const sky=(c,r)=>`<circle cx="${x}" cy="${y-20}" r="${r}" fill="url(#halo)"/>`;
 switch(kind){
 case 'dunes':return sky(0,150)+hills(y+40,26,.10,G,0)+hills(y+90,18,.08,G,200)+hills(y+140,12,.06,W_,80)+`<path d="M${x+120} ${y+58} v-34 M${x+120} ${y+30} c-14 -6 -24 -18 -22 -30 12 2 22 10 22 30 c0 -20 10 -28 22 -30 2 12 -8 24 -22 30" fill="none" stroke="${G}.35)" stroke-width="1.6"/>`;
 case 'city':return `<path d="M0 ${y+120} h30 v-30 h22 v12 h18 v-40 l10 -14 10 14 v40 h26 v-20 h30 v20 h40 v-28 h24 v-12 h16 v12 h22 v28 h30 v-36 l12 -16 12 16 v36 h28 v-20 h30 v20 h30" fill="none" stroke="${G}.26)" stroke-width="1"/><path d="M0 ${y+128} H390" stroke="${G}.12)" stroke-width="1"/>`;
 case 'harp':return hills(y+60,30,.09,W_,40)+hills(y+120,20,.06,W_,300)+`<g stroke="${G}.22)" stroke-width="1">${[0,1,2,3,4,5].map(i=>`<line x1="${30+i*60}" y1="${y-40}" x2="${60+i*60}" y2="${y+200}"/>`).join('')}</g>`;
 case 'flame':return `<path d="M0 ${y+150} L40 ${y+60} L80 ${y+120} L130 ${y+20} L180 ${y+110} L230 ${y+50} L280 ${y+130} L330 ${y+70} L390 ${y+140}" fill="none" stroke="${G}.3)" stroke-width="1"/><path d="M0 ${y+170} L60 ${y+120} L120 ${y+160} L200 ${y+100} L270 ${y+165} L340 ${y+120} L390 ${y+160}" fill="none" stroke="${G}.18)" stroke-width="1"/><ellipse cx="195" cy="${y+150}" rx="150" ry="40" fill="url(#ember)"/>`;
 case 'star':return `<circle cx="${x}" cy="${y-30}" r="3" fill="${G}.95)"/><path d="M${x} ${y-70} v80 M${x-40} ${y-30} h80" stroke="${G}.35)" stroke-width="1"/><circle cx="${x}" cy="${y-30}" r="60" fill="url(#halo)"/>`+hills(y+80,24,.10,W_,120)+`<g fill="${W_}.08)">${[150,180,205,235].map((cx,i)=>`<rect x="${cx}" y="${y+66-(i%2)*8}" width="22" height="${30+(i%2)*8}"/>`).join('')}<path d="M148 ${y+66} l13 -12 13 12z M203 ${y+58} l13 -12 13 12z"/></g>`+`<path d="M0 ${y+200} Q 100 ${y+185} 200 ${y+200} T 390 ${y+195} V${HH} H0Z" fill="${B}.10)"/>`;
 case 'waves':return `<g fill="none" stroke="${B}.25)" stroke-width="1.5">${[0,1,2,3,4].map(i=>`<path d="M0 ${y+60+i*22} Q 40 ${y+48+i*22} 80 ${y+60+i*22} T 160 ${y+60+i*22} T 240 ${y+60+i*22} T 320 ${y+60+i*22} T 400 ${y+60+i*22}"/>`).join('')}</g><path d="M${x-50} ${y+150} h70 l-10 12 h-50z M${x-15} ${y+150} v-50 l40 40z" fill="${W_}.12)"/>`;
 case 'letters':return `<path d="M0 ${y+150} C 80 ${y+120} 140 ${y+170} 220 ${y+140} S 340 ${y+120} 390 ${y+150} V${HH} H0Z" fill="${B}.08)"/><g fill="${W_}.08)"><rect x="40" y="${y+60}" width="10" height="70"/><rect x="64" y="${y+60}" width="10" height="70"/><rect x="88" y="${y+60}" width="10" height="70"/><path d="M30 ${y+60} h78 l-8 -14 h-62z"/><rect x="30" y="${y+130}" width="78" height="8"/></g>`;
 case 'lamp':return hills(y+80,22,.08,W_,0)+`<g>${[60,140,230,320].map((cx,i)=>`<circle cx="${cx}" cy="${y+70+(i%2)*14}" r="26" fill="url(#ember)"/><circle cx="${cx}" cy="${y+70+(i%2)*14}" r="2" fill="${G}.9)"/>`).join('')}</g>`;
 case 'city2':return `<circle cx="195" cy="${y+60}" r="170" fill="url(#halo)"/><path d="M60 ${y+150} v-40 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v-50 l15 -22 15 22 v50 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v40" fill="none" stroke="${G}.45)" stroke-width="1.2"/><g stroke="${G}.22)" stroke-width="1">${[-60,-30,0,30,60].map(a=>`<line x1="195" y1="${y+40}" x2="${195+Math.sin(a*Math.PI/180)*220}" y2="${y+40-Math.cos(a*Math.PI/180)*220}"/>`).join('')}</g>`;
 }return ''}
function vignette(kind,x,y,i){const L=x<195;const side=L?1:-1;
 switch(kind){
 case 'waves':return `<g transform="translate(${x} ${y})"><path d="M-110 10 C -90 -40 -60 -50 -30 -60 L -30 40 L -110 40Z" fill="${B}.22)"/><path d="M110 10 C 90 -40 60 -50 30 -60 L 30 40 L 110 40Z" fill="${B}.22)"/><path d="M-30 -60 c-10 -12 -16 -24 -14 -40 M30 -60 c10 -12 16 -24 14 -40" stroke="${B}.35)" fill="none"/></g>`;
 case 'mountain':return `<g transform="translate(${x} ${y})"><path d="M-140 60 L-60 -120 L-20 -60 L20 -150 L70 -70 L140 60Z" fill="${W_}.10)"/><path d="M-40 -170 q30 -20 60 0 q30 20 60 0" stroke="${W_}.20)" fill="none" stroke-width="3"/><path d="M20 -150 l-14 40 l16 -8 l-18 48" stroke="${G}.6)" stroke-width="1.6" fill="none"/></g>`;
 case 'rain':return `<g transform="translate(${x} ${y})"><g stroke="${B}.35)" stroke-width="1">${[-90,-70,-50,-30,-10,10,30,50,70,90].map(d=>`<line x1="${d}" y1="-120" x2="${d-12}" y2="-50"/>`).join('')}</g><path d="M-70 -30 h140 l-16 26 h-108z M-25 -30 v-28 h50 v28" fill="${W_}.14)"/><path d="M-120 0 q60 -14 120 0 t120 0" stroke="${B}.3)" fill="none" stroke-width="2"/></g>`;
 case 'trumpet':return `<g transform="translate(${x} ${y})" fill="${W_}.12)"><rect x="-120" y="-70" width="60" height="70" transform="rotate(-8 -90 -35)"/><rect x="60" y="-80" width="60" height="80" transform="rotate(10 90 -40)"/><rect x="-150" y="-40" width="30" height="40" transform="rotate(-24 -135 -20)"/><rect x="120" y="-30" width="30" height="30" transform="rotate(20 135 -15)"/></g>`;
 case 'temple':return `<g transform="translate(${x} ${y})" fill="${G}.18)"><path d="M-80 -40 h160 l-10 -18 h-140z"/>${[-70,-45,-20,5,30,55].map(cx=>`<rect x="${cx}" y="-40" width="12" height="46"/>`).join('')}<rect x="-85" y="6" width="170" height="8"/><path d="M-140 40 L-80 14 L80 14 L140 40Z" fill="${W_}.06)"/></g>`;
 case 'ruins':return `<g transform="translate(${x} ${y})" fill="${W_}.10)"><path d="M-120 20 v-50 l16 10 v40z M-80 20 v-80 l18 -12 v92z M40 20 v-40 l16 -18 v58z M90 20 v-70 l14 8 v62z"/><ellipse cx="0" cy="-30" rx="110" ry="30" fill="url(#ember)"/></g>`;
 case 'cross':return `<g transform="translate(${x} ${y})"><path d="M-130 30 Q 0 -40 130 30Z" fill="${W_}.08)"/><g stroke="${W_}.45)" stroke-width="2.5" stroke-linecap="round"><path d="M0 -20 v-70 M-16 -70 h32"/><path d="M-45 -10 v-50 M-56 -46 h22"/><path d="M45 -10 v-50 M34 -46 h22"/></g></g>`;
 case 'sunrise':return `<g transform="translate(${x} ${y})"><circle cx="0" cy="-20" r="90" fill="url(#halo)"/><path d="M-50 10 a50 50 0 0 1 100 0z" fill="${W_}.10)"/><path d="M-22 10 a22 30 0 0 1 44 0z" fill="rgba(255,255,255,.9)"/></g>`;
 case 'manger':return `<g transform="translate(${x} ${y})"><circle cx="0" cy="-130" r="3" fill="${G}.95)"/><path d="M0 -127 L-26 10 M0 -127 L26 10" stroke="${G}.18)" fill="none"/><path d="M-60 10 v-40 l60 -36 60 36 v40z" fill="${W_}.10)"/></g>`;
 case 'city':return `<g transform="translate(${x} ${y})"><circle cx="0" cy="-60" r="160" fill="url(#halo)"/><path d="M-120 10 v-40 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v-50 l20 -26 20 26 v50 h20 v-24 h18 v-30 l12 -18 12 18 v30 h18 v24 h20 v40" fill="none" stroke="${G}.6)" stroke-width="1.4" stroke-linejoin="round"/><path d="M-130 10 h260" stroke="${G}.35)"/></g>`;
 case 'tent':return `<g transform="translate(${x} ${y})"><path d="M${side*90} 14 v-60 M${side*90} -46 c-18 -4 -30 -18 -30 -36 16 2 28 14 30 36 2 -22 14 -34 30 -36 0 18 -12 32 -30 36" stroke="${G}.4)" fill="none" stroke-width="1.6"/><path d="M${side*20} 14 l24 -30 24 30z" fill="${W_}.12)"/></g>`;
 case 'flame':return `<g transform="translate(${x} ${y})"><circle cx="${side*60}" cy="-30" r="50" fill="url(#ember)"/><path d="M${side*60} -10 c8 -14 2 -24 -2 -34 -3 8 -8 10 -8 2 -8 10 -6 24 10 32z" fill="${G}.45)"/></g>`;
 case 'lion':return `<g transform="translate(${x} ${y})"><path d="M-70 20 a70 60 0 0 1 140 0z" fill="rgba(27,36,64,.18)"/><path d="M-70 20 a70 60 0 0 1 140 0" stroke="${W_}.14)" fill="none"/></g>`;
 case 'whale':return `<g transform="translate(${x} ${y})"><path d="M-130 10 q60 -16 130 0 t130 0 v40 h-260z" fill="${B}.18)"/><path d="M-40 10 c20 -24 60 -24 80 0 l24 -16 -6 16 6 16 -24 -16" fill="rgba(27,36,64,.25)"/></g>`;
 default:return ''}}

const ICON={sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
serpent:'<path d="M4 17c3-5 6 5 9 0s4-6 7-2M20 15l-1-1"/>',rain:'<path d="M7 14h10a4 4 0 0 0 0-8 5 5 0 0 0-9.6 1A3.5 3.5 0 0 0 7 14zM9 17v3M13 17v3M17 17v3"/>',
tent:'<path d="M3 20h18L12 5zM12 5v15"/>',flame:'<path d="M12 3c3 4 6 6 6 11a6 6 0 0 1-12 0c0-3 1-4 2-6 1 2 2 3 3 3 0-3 0-5 1-8z"/>',
coat:'<path d="M8 4h8l3 4-3 1v11H8V9L5 8zM12 4v16"/>',waves:'<path d="M2 9c3-2 5-2 8 0s5 2 8 0 3-1 4 0M2 15c3-2 5-2 8 0s5 2 8 0 3-1 4 0"/>',
mountain:'<path d="M2 20L9 7l4 6 2-3 7 10z"/>',grapes:'<circle cx="12" cy="7" r="2"/><circle cx="9" cy="11" r="2"/><circle cx="15" cy="11" r="2"/><circle cx="12" cy="15" r="2"/><circle cx="9" cy="19" r="2"/><circle cx="15" cy="19" r="2"/><path d="M12 5V2"/>',
trumpet:'<path d="M3 10h8l9-5v14l-9-5H3z"/>',pillars:'<path d="M4 20h16M6 20V8M12 20V8M18 20V8M4 8h16"/>',
wheat:'<path d="M12 22V8M12 8C9 8 7 6 7 3c3 0 5 2 5 5zM12 8c3 0 5-2 5-5-3 0-5 2-5 5zM12 13c-3 0-5-2-5-5 3 0 5 2 5 5zM12 13c3 0 5-2 5-5-3 0-5 2-5 5z"/>',
stone:'<path d="M3 21c3-5 7-7 10-7M9 16a5 4 0 1 0 10 0 5 4 0 1 0-10 0"/>',crown:'<path d="M3 18h18l-2-10-5 4-2-6-2 6-5-4z"/>',
temple:'<path d="M4 20h16M5 8h14M7 8v12M12 8v12M17 8v12M4 8l8-5 8 5"/>',ruins:'<path d="M3 20h18M5 20V12l3 2v6M10 20V9l3-2v13M16 20v-6l3-3v9"/>',
wall:'<path d="M3 8h18v12H3zM3 12h18M3 16h18M8 8v4M14 8v4M11 12v4M6 16v4M16 16v4"/>',wind:'<path d="M3 8h11a3 3 0 1 0-3-3M3 13h15a3 3 0 1 1-3 3M3 18h8"/>',
staff:'<path d="M9 22V7a3 3 0 1 1 6 0v2"/>',eye:'<path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="3"/>',
scroll:'<path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h4"/>',bones:'<path d="M5 19L19 5M5 5l14 14"/><circle cx="5" cy="5" r="1.5"/><circle cx="19" cy="19" r="1.5"/><circle cx="19" cy="5" r="1.5"/><circle cx="5" cy="19" r="1.5"/>',
lion:'<circle cx="12" cy="12" r="7"/><path d="M9 11h.1M15 11h.1M9 15c2 2 4 2 6 0M12 2v3M5 5l2 2M19 5l-2 2"/>',fish:'<path d="M3 12c4-6 10-6 14 0-4 6-10 6-14 0zM17 12l4-4v8z"/>',
star:'<path d="M12 2l3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>',cross:'<path d="M12 3v18M6 9h12"/>',
sunrise:'<path d="M3 18h18M7 18a5 5 0 0 1 10 0M12 7V4M5 10L3 8M19 10l2-2"/>',manger:'<path d="M3 20h18M5 20l7-8 7 8M12 12V9M12 2l1.5 3 3.5.5-2.5 2.5.5 3.5-3-1.5-3 1.5.5-3.5L7 5.5 10.5 5z"/>',
figure:'<circle cx="12" cy="5" r="2"/><path d="M9 21l3-8 3 8M12 13V8M8 11l4-3 4 3"/>',lamp:'<path d="M9 18h6M10 21h4M12 3a6 6 0 0 1 3 11v4H9v-4a6 6 0 0 1 3-11z"/>',
tomb:'<path d="M4 20h16M6 20V10a6 6 0 0 1 12 0v10M9 20v-6h6v6"/>',dove:'<path d="M3 12c4 0 6-4 9-4 2 0 3 2 6 2l3-1-3 3c-2 4-6 6-9 6-3 0-4-2-6-6z"/>',
lightning:'<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',heart:'<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
city:'<path d="M3 20h18M4 20V9h5v11M9 20V5h6v15M15 20v-8h5v8"/>',play:'<path d="M8 5l12 7-12 7z" fill="currentColor" stroke="none"/>',pause:'<path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" stroke="none"/>',altar:'<path d="M4 20h16M6 20v-6h12v6M12 14c2-2 3-4 2-6-1 1-2 1-2-1-2 2-3 4-2 6"/>',goat:'<path d="M4 18l3-7h10l3 7M7 11c-2-2-3-4-2-7M17 11c2-2 3-4 2-7M9 18v3M15 18v3"/>',
whale:'<path d="M2 13c3-5 9-7 15-4l4-3-1 5 1 5-4-3c-6 3-12 1-15-4zM6 12h.1"/>',house:'<path d="M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6"/>',lamb:'<path d="M6 12a4 4 0 0 1 4-4h5a3 3 0 0 1 3 3v2a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3zM9 16v4M15 16v4M18 9l2-2"/>'};
const icon=(k,sz=14,st=1.6,color='var(--gold2)')=>`<svg viewBox="0 0 24 24" width="${sz}" height="${sz}" fill="none" stroke="${color}" stroke-width="${st}" stroke-linecap="round" stroke-linejoin="round">${ICON[k]||ICON.star}</svg>`;
const LANDMARKS={'Gen1':['sun','Creation'],'Gen3':['serpent','The Fall'],'Gen7':['rain','The Flood'],'Gen12':['tent','The call of Abram'],'Gen22':['altar','Moriah'],'Gen37':['coat','Joseph sold'],'Exo3':['flame','The burning bush'],'Exo14':['waves','The sea parts'],'Exo20':['mountain','Sinai'],'Lev16':['goat','The Day of Atonement'],'Num13':['grapes','The spies'],'Deu34':['mountain','Moses sees the land'],'Jos6':['trumpet','Jericho'],'Jdg16':['pillars','Samson'],'Rut1':['wheat','Ruth in the fields'],'1Sa17':['stone','David and Goliath'],'2Sa7':['crown','A throne forever'],'1Ki8':['temple','The Temple'],'1Ki18':['flame','Carmel'],'2Ki25':['ruins','Jerusalem falls'],'Ezr1':['house','The return'],'Neh2':['wall','The walls'],'Job38':['wind','Out of the whirlwind'],'Psa23':['staff','The Shepherd'],'Isa6':['eye','Holy, holy, holy'],'Isa53':['lamb','The suffering servant'],'Jer31':['scroll','A new covenant'],'Eze37':['bones','Dry bones'],'Dan6':['lion','The lions’ den'],'Jon2':['whale','Jonah'],'Mic5':['star','Bethlehem foretold'],'Mat2':['star','The star'],'Mat5':['mountain','The Sermon on the Mount'],'Mat27':['cross','The cross'],'Mat28':['sunrise','The empty tomb'],'Luk2':['manger','Bethlehem'],'Luk15':['figure','The prodigal'],'Joh1':['lamp','The Word'],'Joh11':['tomb','Lazarus'],'Act2':['flame','Pentecost'],'Act9':['lightning','The Damascus road'],'Rom8':['dove','No condemnation'],'1Co13':['heart','Love'],'Rev21':['city','The New Jerusalem']};
const SCENES={'The Law':'dunes','History':'city','Wisdom & Song':'harp','Major Prophets':'flame','Minor Prophets':'flame','The Gospels':'star','The Church Begins':'waves','Letters of Paul':'letters','General Letters':'lamp','The New Beginning':'city2'};

const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=s=>{s=Math.max(0,Math.round(s||0));const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(x).padStart(2,'0')};
const mins=s=>s?Math.round(s/60)+' min':'';
const isDone=id=>!!(prog[id]&&prog[id].done);
const LANDS=[['Genesis','The Law'],['Joshua','History'],['Job','Wisdom & Song'],['Isaiah','Major Prophets'],['Hosea','Minor Prophets'],['Matthew','The Gospels'],['Acts','The Church Begins'],['Romans','Letters of Paul'],['Hebrews','General Letters'],['Revelation','The End & the New Beginning']];
function books(){const b=[...D.books];if(cfg.order==='narr')b.sort((x,y)=>Math.min(...x.ch.map(c=>c.seq))-Math.min(...y.ch.map(c=>c.seq)));return b}
function walk(){const w=[];for(const b of books()){const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;for(const c of chs)w.push({b,c})}return w}
function teacher(i){return i.who==='PAM'?'Philip Anthony Mitchell':'David Platt'}
function voiceHTML(id){const i=I[id],p=prog[id]||{},deg=p.dur&&!isDone(id)?Math.round(360*(p.pos||0)/p.dur):0,playing=cur===id&&!audio.paused;
 return `<div class="voice ${isDone(id)?'done':''}"><button class="pb ${i.audio?'':'off'} ${playing?'playing':''}" style="--p:${deg}deg;position:relative" data-play="${id}"><span style="color:${playing?'var(--gold2)':'var(--ink)'}">${icon(playing?'pause':'play',18,0,'currentColor')}</span></button>
 <div class="tx"><div class="who">${teacher(i)}${i.tr==='devotional'?' · Pray the Word':i.tr==='overview'?' · Overview':''}</div><div class="ti">${esc(i.t)}</div><div class="ln">${mins(i.dur)||(i.audio?'':'audio soon')}</div></div>
 <button class="ck" data-done="${id}">✓</button></div>`}
let W=null; // cached world geometry
function render(){const m=$('#main');if(view==='settings'){m.innerHTML=settingsView();wire();return}
 const w=walk();let first=w.findIndex(x=>!read[x.b.abbr+x.c.c]);if(first<0)first=w.length-1;if(camp==null||camp>=w.length)camp=first;
 const rd=w.filter(x=>read[x.b.abbr+x.c.c]).length;$('#pct').innerHTML=`<b>${rd}</b> of 1,189 chapters · ${Math.round(1000*rd/1189)/10}%`;
 const rows=16,rowH=240,top=120,H=top+rows*rowH+200,x0=70,x1=320;let d=`M ${x0} ${top}`;for(let r=0;r<rows;r++){const f=r%2?x1:x0,t=r%2?x0:x1,y=top+r*rowH;d+=` C ${f} ${y+rowH*.55}, ${t} ${y+rowH*.45}, ${t} ${y+rowH}`}
 const POS=[];let acc=0;for(const b of books()){const wgt=6+2.2*Math.sqrt(b.n);const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;chs.forEach((c,k)=>POS.push(acc+wgt*(k+0.5)/b.n));acc+=wgt}
 render.POS=POS;render.TOT=acc;const fill=first>0?(POS[first-1]+POS[first])/2/acc:0;
 m.innerHTML=`<div class="world" id="world"><svg viewBox="0 0 390 ${H}" preserveAspectRatio="xMidYMin meet">
  <defs><radialGradient id="g"><stop offset="0" stop-color="#d9b15a" stop-opacity=".55"/><stop offset="1" stop-color="#d9b15a" stop-opacity="0"/></radialGradient>
  <radialGradient id="halo"><stop offset="0" stop-color="#e9c979" stop-opacity=".40"/><stop offset=".6" stop-color="#e9c979" stop-opacity=".10"/><stop offset="1" stop-color="#e9c979" stop-opacity="0"/></radialGradient>
  <radialGradient id="ember"><stop offset="0" stop-color="#e2a35a" stop-opacity=".30"/><stop offset="1" stop-color="#e2a35a" stop-opacity="0"/></radialGradient><radialGradient id="dawn"><stop offset="0" stop-color="#fff6d8" stop-opacity=".95"/><stop offset=".5" stop-color="#f6e7c0" stop-opacity=".35"/><stop offset="1" stop-color="#f6e7c0" stop-opacity="0"/></radialGradient><radialGradient id="glory"><stop offset="0" stop-color="#fffdf2" stop-opacity="1"/><stop offset=".35" stop-color="#fff3cc" stop-opacity=".85"/><stop offset=".7" stop-color="#f3dfa2" stop-opacity=".3"/><stop offset="1" stop-color="#f3dfa2" stop-opacity="0"/></radialGradient></defs>
  <g id="sky"></g><g id="lands"></g>
  <path id="road" d="${d}" fill="none" stroke="rgba(27,36,64,.10)" stroke-width="30" stroke-linecap="round"/>
  <path d="${d}" fill="none" stroke="var(--gold)" stroke-width="30" stroke-linecap="round" pathLength="1" stroke-dasharray="${fill} 1" opacity=".9"/>
  <path d="${d}" fill="none" stroke="rgba(255,255,255,.95)" stroke-width="3" stroke-dasharray="3 14" stroke-linecap="round"/>
  <path id="hit" d="${d}" fill="none" stroke="transparent" stroke-width="70"/>
  <g id="labels"></g><g id="marker" style="pointer-events:none"></g></svg>
  <div class="clearing" id="clearing"></div></div>`;
 decorate(w,first);wire()}
function decorate(w,first){const road=$('#road'),svg=road.ownerSVGElement,L=road.getTotalLength(),POS=render.POS,TOT=render.TOT,at=i=>road.getPointAtLength(L*POS[Math.max(0,Math.min(w.length-1,Math.round(i)))]/TOT);
 // labels with collision avoidance: short books alternate sides and get pushed apart, with leader lines back to the road
 const labs=[];let lands='',idx=0,prevSide=null,prevShort=false;
 for(const b of books()){const mid=at(idx+b.n/2),st=at(idx);let side=mid.x<195?'L':'R';if(b.n<10&&prevShort&&side===prevSide)side=side==='L'?'R':'L';
  const land=cfg.order==='canon'?LANDS.find(l=>l[0]===b.name):null;
  if(land){lands+=`<circle cx="${st.x}" cy="${st.y}" r="90" fill="url(#g)" class="glow"/>`;const txt=land[1].replace('The End & the New Beginning','The New Beginning');labs.push({kind:'land',side:st.x<195?'L':'R',x:st.x<195?st.x+40:st.x-40,y:st.y-48,txt})}
  labs.push({kind:'book',side,x:side==='L'?Math.min(mid.x+30,250):Math.max(mid.x-30,140),y:mid.y+5,px:mid.x,py:mid.y,txt:b.name,big:b.n>=20,here:w[camp].b===b,idx});
  prevSide=side;prevShort=b.n<10;idx+=b.n}
 labs.sort((a,b)=>a.y-b.y);const last={L:-1e9,R:-1e9};let lbl='';
 for(const l of labs){const gap=l.kind==='land'?30:24;const ref=l.kind==='land'?Math.max(last.L,last.R):last[l.side];if(l.y-ref<gap)l.y=ref+gap;if(l.kind==='land'){last.L=last.R=l.y}else last[l.side]=l.y;
  if(l.kind==='land'){lbl+=`<text x="${l.x}" y="${l.y}" text-anchor="${l.side==='L'?'start':'end'}" class="land">${l.txt}</text>`}
  else{const moved=Math.abs(l.y-5-l.py)>12;if(moved)lbl+=`<line x1="${l.px}" y1="${l.py}" x2="${l.side==='L'?l.x-6:l.x+6}" y2="${l.y-5}" stroke="rgba(241,237,228,.25)" stroke-width="1"/>`;
   lbl+=`<text x="${l.x}" y="${l.y}" text-anchor="${l.side==='L'?'start':'end'}" class="bl ${l.big?'big':''} ${l.here?'here':''}" data-camp="${l.idx}">${l.txt}</text>`}}
 // scenery: stars thin out toward the New Testament dawn; each land gets its horizon
 let sky='';const Hs=+svg.getAttribute('viewBox').split(' ')[3];HH=Hs;let seed=7;const rnd=()=>{seed=(seed*9301+49297)%233280;return seed/233280};
 for(let i=0;i<140;i++){const yy=rnd()*Hs;if(rnd()<1-yy/Hs)sky+=`<circle cx="${(rnd()*390).toFixed(0)}" cy="${yy.toFixed(0)}" r="${(0.6+rnd()*1.2).toFixed(1)}" fill="rgba(168,129,42,${(0.12+rnd()*0.25).toFixed(2)})"/>`}
 let scenes='';idx=0;for(const b of books()){const land=cfg.order==='canon'?LANDS.find(l=>l[0]===b.name):null;if(land){const st=at(idx);scenes+=`<g opacity=".7">${sceneSVG(SCENES[land[1]],st.x,st.y-40)}</g>`}idx+=b.n}
 // landmarks: where the great scenes stand
 let marks='',lastVy=-1e9;
 w.forEach((x,i)=>{const lm=LANDMARKS[x.b.abbr+x.c.c];if(!lm)return;const pt=at(i);if(pt.y-lastVy<110)return;lastVy=pt.y;marks+=`<g transform="translate(${pt.x} ${pt.y}) scale(.6) translate(${-pt.x} ${-pt.y})" opacity=".75">${vignette2(lm[0],pt.x,pt.y)}</g>`});
 // per-book motifs beside the road, alternating sides; rivers at the Jordan and the river of life
 let mot='';idx=0;for(const b of books()){const land=cfg.order==='canon'?(LANDS.slice().reverse().find(l=>books().indexOf(b)>=books().findIndex(bb=>bb.name===l[0]))||[,''])[1]:'';const mid=at(idx+b.n/2);const side=mid.x<195?1:-1;const kinds={'The Law':['palm','tent','palm'],'History':['town','town','palm'],'Wisdom & Song':['olive','olive','palm'],'Major Prophets':['cedar','town','cedar'],'Minor Prophets':['olive','town','olive'],'The Gospels':['olive','town','olive'],'The Church Begins':['sail','sail','town'],'Letters of Paul':['column','sail','column'],'General Letters':['fire','fire','town'],'The New Beginning':['tree','tree','tree']}[land];
  if(kinds){const ox=mid.x+side*(118+(b.n%3)*12);if(ox>30&&ox<360)mot+=motif('',ox,mid.y+12,b.n>=20?.9:.7)}
  if(b.name==='Joshua'){const st=at(idx);mot+=river(st.x,st.y+6)}if(b.name==='Revelation'){const st=at(idx+b.n-2);mot+=river(st.x,st.y+40,.18)}idx+=b.n}
 $('#sky').innerHTML=terrain(Hs)+celestial(Hs)+sky+scenes+mot;
 $('#lands').innerHTML=lands;$('#labels').innerHTML=lbl+marks;
 const m=at(camp),f=at(first);
 $('#marker').innerHTML=`${camp!==first?`<circle cx="${f.x}" cy="${f.y}" r="8" fill="var(--gold)" opacity=".7"/>`:''}<circle cx="${m.x}" cy="${m.y}" r="26" fill="rgba(240,215,154,.18)"/><circle cx="${m.x}" cy="${m.y}" r="13" fill="var(--gold)" class="you"/><circle cx="${m.x}" cy="${m.y}" r="5" fill="#fff"/>`;
 // clearing placed in the world beside the marker
 const sc=svg.getBoundingClientRect().width/390,cl=$('#clearing');const x=w[camp],b=x.b,c=x.c,ids=c.ids.filter(okWho),r=!!read[b.abbr+c.c],ov=(c===b.ch[0]?b.ov:[]).filter(okWho);
 let nextV=null;for(let i=camp+1;i<w.length;i++){if(w[i].c.ids.some(okWho)){nextV={i,x:w[i]};break}}
 cl.style.top=(m.y*sc+46)+'px';cl.style.right='auto';
 const land=cfg.order==='canon'?(LANDS.slice().reverse().find(l=>books().indexOf(b)>=books().findIndex(bb=>bb.name===l[0]))||[,''])[1]:'';
 const rdc=w.filter(x=>read[x.b.abbr+x.c.c]).length,lm=LANDMARKS[b.abbr+c.c];cl.innerHTML=`<div class="where">${land}<span style="float:right;letter-spacing:0;text-transform:none;color:var(--mute)">${rdc} of 1,189</span></div><div class="ch serif">${b.name} ${c.c}</div>${lm?`<div class="scene">${lm[1]}</div>`:''}
  ${(()=>{if(c!==b.ch[0])return '';const ord=books().map(x=>x.name);const groups={};(b.spans||[]).forEach(x=>{let lab=x.label;if(x.books&&!/Testament|Law|History|Wisdom|Prophets|Gospels|Church|Letters|Revelation/.test(lab)){const idxs=x.books.map(n=>ord.indexOf(n)).sort((p,q)=>p-q);const contig=idxs[idxs.length-1]-idxs[0]===idxs.length-1;lab=contig?`${ord[idxs[0]]}–${ord[idxs[idxs.length-1]]}`:x.books.join(', ')}(groups[lab]=groups[lab]||[]).push(x.id)});let h='';for(const [lab,ids2] of Object.entries(groups))h+=`<details class="enter"><summary>Entering ${lab} · ${ids2.length} survey${ids2.length>1?'s':''} ›</summary>${ids2.map(voiceHTML).join('')}</details>`;
   if(ov.length)h+=`<details class="enter"><summary>Enter ${b.name} with ${ov.length} overview${ov.length>1?'s':''} ›</summary>${ov.map(voiceHTML).join('')}</details>`;return h})()}
  ${(()=>{const all=[...ids.filter(i=>I[i].tr!=='devotional'),...ids.filter(i=>I[i].tr==='devotional')];const show=decorate.more?all:all.slice(0,3);return show.map(voiceHTML).join('')+(all.length>3&&!decorate.more?`<button class="more" id="more">${all.length-3} more voice${all.length-3>1?'s':''} on this stretch ›</button>`:'')})()}
  ${ids.length?'':'<div class="empty">No voice on this stretch — read it, mark it, walk on.</div>'}
  ${nextV?`<div class="empty" style="padding-top:2px">Next voice ahead: <b style="color:var(--gold2);cursor:pointer" data-camp="${nextV.i}" class="nv">${nextV.x.b.name} ${nextV.x.c.c}</b> · ${nextV.i-camp} stop${nextV.i-camp>1?'s':''} on</div>`:''}
  <div class="acts"><button class="read ${r?'on':''}" data-read="${b.abbr+c.c}">${r?'Read ✓':'Mark read'}</button><button class="go" data-camp="${Math.min(w.length-1,camp+1)}">Walk on ›</button>${camp!==first?`<button data-camp="${first}">My place</button>`:''}</div>`;
 const cw=cl.offsetWidth;cl.style.left=Math.max(10,Math.min(window.innerWidth-cw-10,m.x*sc-cw/2))+'px';
 // camera: keep you ~30% from top
 if(!decorate.moving){const y=m.y*sc+$('#world').offsetTop-window.innerHeight*0.30;window.scrollTo({top:Math.max(0,y),behavior:decorate.first?'auto':'smooth'});decorate.first=false}
 $('#hit').onclick=e=>{const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const p=pt.matrixTransform(svg.getScreenCTM().inverse());let best=0,bd=1e12;for(let i=0;i<w.length;i++){const q=at(i),dd=(q.x-p.x)**2+(q.y-p.y)**2;if(dd<bd){bd=dd;best=i}}go(best)};
 document.querySelectorAll('.bl[data-camp], #labels g[data-camp]').forEach(t=>t.onclick=e=>{e.stopPropagation();go(+t.dataset.camp)})}
function go(i){camp=i;decorate.more=false;S.set('camp',camp);render()}
function settingsView(){const unmapped=Object.values(I).filter(i=>!D.books.some(b=>b.ov.includes(i.id)||(b.spans||[]).some(x=>x.id===i.id)||b.ch.some(c=>c.ids.includes(i.id)))).length;const n=Object.keys(I).length,na=Object.values(I).filter(i=>i.audio).length;
 return `<div class="settings"><h2 class="serif" style="margin:0 0 8px">The road</h2><p class="note">${n} episodes, ${na} with audio in the app. Everything on the road sits at the chapter or book it teaches: sermons and Pray the Word at their chapters, Secret Church and other surveys at the books they cover. ${unmapped} episodes don't name a passage and wait off-road until the full import adds their Scripture. A new teacher is a new feed; their episodes land the same way.</p>
 <p><span class="btn" id="ord" style="display:inline-block;cursor:pointer">${cfg.order==='narr'?'Narrative order (your EPUB)':'Standard order'} — switch</span>
 <span class="btn" id="who" style="display:inline-block;cursor:pointer">Voices: ${cfg.who==='Platt'?'David Platt only':cfg.who==='PAM'?'Philip Anthony Mitchell only':'everyone'} — switch</span></p>
 <p class="note">Progress is stored on this device.</p><button class="btn" id="exp">Export</button><button class="btn" id="imp">Import</button><button class="btn" id="reset">Reset</button><textarea id="io" placeholder="Exported progress appears here; paste here to import."></textarea>
 <p class="note" id="envn">${location.protocol==='file:'||window!==window.top?'This viewer blocks audio. Serve the file from a web address and open it in Safari, then Add to Home Screen.':'Audio should stream here.'} <button class="btn" id="atest" style="padding:4px 10px">Test audio</button><span id="atest-out"></span></p>
 <button class="btn" id="back">‹ Back to the road</button></div>`}
/* player */
const audio=$('#audio');let cur=null,speed=S.get('speed',1);audio.playbackRate=speed;$('#spd').textContent=speed+'×';
function where(id){for(const b of D.books){if(b.ov.includes(id)||(b.spans||[]).some(x=>x.id===id))return b.name;for(const c of b.ch)if(c.ids.includes(id))return b.name+' '+c.c}return ''}
function play(id){const i=I[id];if(!i.audio)return;if(cur!==id){cur=id;audio.src=i.audio;const p=prog[id]||{};audio.addEventListener('loadedmetadata',()=>{if(p.pos&&p.pos<audio.duration-5)audio.currentTime=p.pos},{once:true});
  $('#np-t').textContent=i.t;$('#np-s').textContent=teacher(i)+' · '+where(id);$('#np').classList.add('on');$('#np').classList.remove('mini');setPP();
  if('mediaSession' in navigator){navigator.mediaSession.metadata=new MediaMetadata({title:i.t,artist:teacher(i),album:where(id)});['play',()=>audio.play(),'pause',()=>audio.pause(),'seekbackward',()=>audio.currentTime-=15,'seekforward',()=>audio.currentTime+=30,'nexttrack',next].reduce((a,v,k,arr)=>{if(k%2===0)navigator.mediaSession.setActionHandler(v,arr[k+1]);return a},0)}}
 audio.paused?audio.play():audio.pause()}
function next(){const seq=[];for(const b of books()){seq.push(...(b.spans||[]).map(x=>x.id),...b.ov);const chs=cfg.order==='narr'?[...b.ch].sort((x,y)=>x.seq-y.seq):b.ch;chs.forEach(c=>seq.push(...c.ids))}const k=seq.indexOf(cur);for(let j=k+1;j<seq.length;j++)if(I[seq[j]].audio&&!isDone(seq[j])&&okWho(seq[j])){play(seq[j]);return}}
audio.addEventListener('timeupdate',()=>{if(!cur)return;const d=audio.duration||0;$('#seek').value=d?1000*audio.currentTime/d:0;$('#cur').textContent=fmt(audio.currentTime);$('#rem').textContent='-'+fmt(d-audio.currentTime);
 if(Math.floor(audio.currentTime)%5===0){prog[cur]=Object.assign(prog[cur]||{},{pos:audio.currentTime,dur:d,at:Date.now()});if(d&&audio.currentTime/d>0.9)prog[cur].done=true;S.set('prog',prog)}});
audio.addEventListener('ended',()=>{prog[cur]=Object.assign(prog[cur]||{},{done:true,pos:0});S.set('prog',prog);render();next()});
const setPP=()=>{$('#pp').innerHTML=icon(audio.paused?'play':'pause',28,0,'#1b2440')};setPP();audio.addEventListener('play',()=>{setPP();render()});audio.addEventListener('pause',()=>{setPP();render()});
audio.addEventListener('error',()=>{$('#np-s').textContent=(location.protocol==='file:'||window!==window.top)?'Audio is blocked in this viewer — open in Safari from a web address.':'This file did not load.'});
$('#pp').onclick=()=>cur&&(audio.paused?audio.play():audio.pause());$('#bk').onclick=()=>audio.currentTime-=15;$('#fw').onclick=()=>audio.currentTime+=30;
$('#seek').oninput=e=>{if(audio.duration)audio.currentTime=audio.duration*e.target.value/1000};
$('#spd').onclick=()=>{const sp=[1,1.25,1.5,1.75,2];speed=sp[(sp.indexOf(speed)+1)%sp.length];audio.playbackRate=speed;$('#spd').textContent=speed+'×';S.set('speed',speed)};
let zz=0,zzT=null;$('#zz').onclick=()=>{const m=[0,15,30,60];zz=m[(m.indexOf(zz)+1)%m.length];$('#zz').textContent=zz?'Sleep '+zz+'m':'Sleep off';clearTimeout(zzT);if(zz)zzT=setTimeout(()=>{audio.pause();zz=0;$('#zz').textContent='Sleep off'},zz*60000)};
$('#cls').onclick=()=>{audio.pause();audio.removeAttribute('src');audio.load();cur=null;$('#np').classList.remove('on');render()};
$('#np').querySelector('.grab').onclick=()=>$('#np').classList.toggle('mini');$('#np-t').onclick=()=>$('#np').classList.toggle('mini');
/* wiring */
function wire(){document.querySelectorAll('[data-play]').forEach(b=>b.onclick=e=>{e.stopPropagation();play(b.dataset.play)});
 document.querySelectorAll('[data-done]').forEach(b=>b.onclick=e=>{e.stopPropagation();const id=b.dataset.done;prog[id]=Object.assign(prog[id]||{},{done:!isDone(id),at:Date.now()});S.set('prog',prog);render()});
 document.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>{const was=!!read[b.dataset.read];read[b.dataset.read]=!was;S.set('read',read);if(!was)camp=Math.min(walk().length-1,camp+1);S.set('camp',camp);render()});
 document.querySelectorAll('.acts [data-camp], .nv[data-camp]').forEach(b=>b.onclick=()=>{decorate.more=false;go(+b.dataset.camp)});const mo=$('#more');if(mo)mo.onclick=()=>{decorate.more=true;decorate.moving=true;render();decorate.moving=false};
 const g=$('#gear');g.onclick=()=>{view=view==='settings'?'walk':'settings';S.set('view',view);decorate.first=true;render();window.scrollTo(0,0)};
 const back=$('#back');if(back)back.onclick=g.onclick;const ord=$('#ord');if(ord)ord.onclick=()=>{cfg.order=cfg.order==='narr'?'canon':'narr';S.set('cfg',cfg);render()};const wh=$('#who');if(wh)wh.onclick=()=>{cfg.who=cfg.who===''?'Platt':cfg.who==='Platt'?'PAM':'';S.set('cfg',cfg);render()};
 const io=$('#io');if(io){$('#exp').onclick=()=>io.value=JSON.stringify({prog,read,cfg});$('#imp').onclick=()=>{try{const v=JSON.parse(io.value);prog=v.prog||prog;read=v.read||read;S.set('prog',prog);S.set('read',read);render()}catch(e){io.value='Could not read that JSON.'}};
  $('#reset').onclick=()=>{if(confirm('Erase all progress on this device?')){prog={};read={};camp=null;S.set('prog',prog);S.set('read',read);S.set('camp',null);render()}};
  $('#atest').onclick=()=>{const o=$('#atest-out');o.textContent=' testing…';const a=new Audio();a.src=Object.values(I).find(i=>i.audio).audio;a.addEventListener('loadedmetadata',()=>o.textContent=' ✓ streams ('+fmt(a.duration)+')');a.addEventListener('error',()=>o.textContent=' ✗ blocked here');a.load()}}}
decorate.first=true;render();window.addEventListener('resize',()=>{decorate.first=true;render()});
/* home-screen app: offline shell + keep progress from being evicted */
if('serviceWorker' in navigator&&isSecureContext)navigator.serviceWorker.register('sw.js').catch(()=>{});
if(navigator.storage&&navigator.storage.persist)navigator.storage.persist().catch(()=>{});
</script></body></html>"""

if __name__ == "__main__":
    main()
