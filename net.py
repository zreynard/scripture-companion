"""HTTP helpers: polite and retrying. A site that refuses (bot check, sign-in) is reported, never worked around."""
from __future__ import annotations
import json, re, time, html as htmlmod
from dataclasses import dataclass
import xml.etree.ElementTree as ET

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}

_session = requests.Session()
_session.headers.update(HEADERS)

@dataclass
class Resp:
    url: str
    final_url: str
    status: int
    text: str
    ok: bool
    note: str = ""

def get(url: str, timeout: int = 25, retries: int = 2, sleep: float = 0.6) -> Resp:
    """GET with retries. 403/429/503 are retried after a pause, not worked around."""
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=timeout, allow_redirects=True)
            last = Resp(url, r.url, r.status_code, r.text, r.status_code < 400)
            if r.status_code < 400 or r.status_code in (404, 410):
                return last
        except requests.RequestException as e:
            last = Resp(url, url, 0, "", False, note=f"{type(e).__name__}: {e}")
        time.sleep(sleep * (attempt + 1))
    return last or Resp(url, url, 0, "", False, note="no response")

def get_json(url: str, **kw):
    r = get(url, **kw)
    if not r.ok:
        return None, r
    try:
        return json.loads(r.text), r
    except json.JSONDecodeError:
        return None, r

# ---------- RSS ----------
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
      "content": "http://purl.org/rss/1.0/modules/content/"}

def parse_rss(xml_text: str) -> list[dict]:
    """Return list of {title, link, enclosure, guid, pubdate, description, author, duration}."""
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        def t(tag, ns=None):
            el = it.find(f"{ns}:{tag}" if ns else tag, NS) if ns else it.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        enc = it.find("enclosure")
        desc = t("description") or t("summary", "itunes") or t("encoded", "content")
        items.append({
            "title": htmlmod.unescape(t("title") or t("title", "itunes")),
            "link": t("link"),
            "enclosure": enc.get("url", "") if enc is not None else "",
            "guid": t("guid"),
            "pubdate": t("pubDate"),
            "description": strip_tags(desc),
            "author": t("author", "itunes") or t("author"),
            "duration": t("duration", "itunes"),
            "episode_no": t("episode", "itunes"),
        })
    return items

TAG_RE = re.compile(r"<[^>]+>")
def strip_tags(s: str) -> str:
    return htmlmod.unescape(TAG_RE.sub(" ", s or "")).replace("\xa0", " ").strip()

# ---------- HTML title / meta ----------
def page_meta(html: str) -> dict:
    """Extract <title>, og:title, meta description, JSON-LD author/headline, canonical."""
    out = {"title": "", "og_title": "", "description": "", "author": "", "canonical": "", "headline": ""}
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m: out["title"] = strip_tags(m.group(1))
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)', html, re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']og:title["\']', html, re.I)
    if m: out["og_title"] = htmlmod.unescape(m.group(1))
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html, re.I) or \
        re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)', html, re.I)
    if m: out["description"] = htmlmod.unescape(m.group(1))
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', html, re.I)
    if m: out["canonical"] = m.group(1)
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph", [node])
            for g in graph:
                if not isinstance(g, dict):
                    continue
                if g.get("headline") and not out["headline"]:
                    out["headline"] = g["headline"]
                a = g.get("author")
                if a and not out["author"]:
                    if isinstance(a, list): a = a[0]
                    if isinstance(a, dict): out["author"] = a.get("name", "")
                    elif isinstance(a, str): out["author"] = a
    return out

def youtube_oembed(url: str):
    """Title + author of a YouTube video without an API key."""
    data, r = get_json("https://www.youtube.com/oembed?format=json&url=" + requests.utils.quote(url, safe=""))
    return data, r
