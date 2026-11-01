"""Build the app's map base from Natural Earth (public domain) and the journey from Theographic places (CC BY-SA 4.0).
python -I tools/map_build.py <land.geojson> <rivers.geojson> <lakes.geojson> <theographic-checkout>
Writes data/map/base.json: {view, land, rivers[], lakes[], journey[]} in map units (equirectangular around 33°N).
"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LON0, LON1, LAT0, LAT1 = 10.0, 58.0, 21.0, 45.5          # Rome to Persia, upper Egypt to the Black Sea
KX = math.cos(math.radians(33)) * 10                      # map units per degree
KY = 10.0
def xy(lon, lat): return (round((lon - LON0) * KX, 2), round((LAT1 - lat) * KY, 2))
RIVERS = {"Nile": "Nile", "Euphrates": "Euphrates", "Tigris": "Tigris", "Jordan": "Jordan", "Orontes": "Orontes", "Halys": "Kızılırmak"}

def simplify(pts, tol):
    if len(pts) < 3: return pts
    def d(p, a, b):
        if a == b: return math.dist(p, a)
        return abs((b[0]-a[0])*(a[1]-p[1]) - (a[0]-p[0])*(b[1]-a[1])) / math.dist(a, b)
    keep = [0, len(pts) - 1]; stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop(); best, idx = 0, None
        for k in range(i + 1, j):
            dd = d(pts[k], pts[i], pts[j])
            if dd > best: best, idx = dd, k
        if idx is not None and best > tol:
            keep.append(idx); stack += [(i, idx), (idx, j)]
    return [pts[k] for k in sorted(set(keep))]

def inside(lon, lat, pad=3): return LON0 - pad <= lon <= LON1 + pad and LAT0 - pad <= lat <= LAT1 + pad

def rings(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon": return c
    if t == "MultiPolygon": return [r for poly in c for r in poly]
    if t == "LineString": return [c]
    if t == "MultiLineString": return c
    return []

def clip_poly(ring, pad=1.0):
    """Sutherland-Hodgman: clip a polygon ring to the map frame (keeps coastlines intact, no straight jumps)."""
    x0, x1, y0, y1 = LON0 - pad, LON1 + pad, LAT0 - pad, LAT1 + pad
    def cut(pts, inside_f, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside_f(b):
                if not inside_f(a): out.append(inter(a, b))
                out.append(b)
            elif inside_f(a):
                out.append(inter(a, b))
        return out
    def ix(xv):
        return lambda a, b: (xv, a[1] + (b[1] - a[1]) * (xv - a[0]) / ((b[0] - a[0]) or 1e-12))
    def iy(yv):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yv - a[1]) / ((b[1] - a[1]) or 1e-12), yv)
    pts = [tuple(p[:2]) for p in ring]
    for f, g in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)), (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
        if not pts: break
        pts = cut(pts, f, g)
    return pts

def clip_line(line, pad=1.0):
    """Split a line where it leaves the frame."""
    parts, cur = [], []
    for lon, lat in (tuple(p[:2]) for p in line):
        if inside(lon, lat, pad): cur.append((lon, lat))
        elif cur: parts.append(cur); cur = []
    if cur: parts.append(cur)
    return [p for p in parts if len(p) > 1]

def path(ring_list, tol, closed=True):
    out = []
    for r in (ring_list if not closed else [clip_poly(r) for r in ring_list]):
        pts = [xy(lon, lat) for lon, lat in r]
        if len(pts) < 2: continue
        pts = simplify(pts, tol)
        if len(pts) < 2: continue
        out.append("M" + " L".join(f"{x},{y}" for x, y in pts) + (" Z" if closed else ""))
    return " ".join(out)

# the movement of the whole Bible: (place name in Theographic, book, chapter, caption)
JOURNEY = [
    ("Ur", "Genesis", 11, "Abram's family leaves Ur"), ("Haran", "Genesis", 11, "Haran"), ("Shechem", "Genesis", 12, "Into Canaan"),
    ("Egypt", "Genesis", 12, "Abram in Egypt"), ("Bethel", "Genesis", 13, "Back to Bethel"), ("Hebron", "Genesis", 13, "Hebron"),
    ("Beersheba", "Genesis", 21, "Beersheba"), ("Haran", "Genesis", 28, "Jacob flees to Haran"), ("Bethel", "Genesis", 35, "Jacob returns"),
    ("Goshen", "Genesis", 46, "Israel goes down to Egypt"), ("Rameses", "Exodus", 12, "The Exodus"),
    ("Pi-hahiroth", "Exodus", 14, "Through the sea"), ("Mount Sinai", "Exodus", 19, "Sinai"), ("Kadesh-barnea", "Numbers", 13, "Kadesh"),
    ("Mount Nebo", "Deuteronomy", 34, "The plains of Moab"), ("Jericho", "Joshua", 6, "Into the land"), ("Shiloh", "Joshua", 18, "Shiloh"),
    ("Jerusalem", "2 Samuel", 5, "David takes Jerusalem"), ("Samaria", "1 Kings", 16, "Samaria, the northern capital"),
    ("Nineveh", "2 Kings", 17, "Israel carried to Assyria"), ("Babylon", "2 Kings", 25, "Judah exiled to Babylon"),
    ("Susa", "Esther", 1, "Persia"), ("Jerusalem", "Ezra", 1, "The return"),
    ("Bethlehem", "Matthew", 2, "Jesus is born"), ("Egypt", "Matthew", 2, "Flight to Egypt"), ("Nazareth", "Matthew", 2, "Nazareth"),
    ("Capernaum", "Matthew", 4, "Ministry in Galilee"), ("Jerusalem", "Matthew", 21, "Jerusalem, the cross and the empty tomb"),
    ("Damascus", "Acts", 9, "Saul on the Damascus road"), ("Antioch", "Acts", 11, "Antioch"),
    ("Corinth", "Acts", 18, "Paul's journeys"), ("Ephesus", "Acts", 19, "Ephesus"), ("Caesarea", "Acts", 23, "Paul under arrest"),
    ("Rome", "Acts", 28, "Rome"), ("Patmos", "Revelation", 1, "John on Patmos"),
]

def main():
    land_f, rivers_f, lakes_f, theo = sys.argv[1:5]
    land = json.load(open(land_f, encoding="utf-8"))
    land_rings = [r for f in land["features"] for r in rings(f["geometry"]) if any(inside(lon, lat, 8) for lon, lat in r)]
    rivers = json.load(open(rivers_f, encoding="utf-8")); lakes = json.load(open(lakes_f, encoding="utf-8"))
    rv = {}
    for f in rivers["features"]:
        nm = (f["properties"].get("name") or f["properties"].get("name_en") or "")
        for key, want in RIVERS.items():
            if want.lower() in nm.lower() or key.lower() in nm.lower():
                rr = [r for r in rings(f["geometry"]) if any(inside(lon, lat, 0) for lon, lat in r)]
                if rr: rv.setdefault(key, []).extend(rr)
    lk = []
    for f in lakes["features"]:
        rr = [r for r in rings(f["geometry"]) if any(inside(lon, lat, 0) for lon, lat in r)]
        if rr:
            lk.append({"n": f["properties"].get("name") or "", "d": path(rr, 0.15)})
    places = json.load(open(os.path.join(theo, "json", "places.json"), encoding="utf-8"))
    byname = {}
    for r in places:
        f = r["fields"]; lat = f.get("openBibleLat") or f.get("latitude"); lon = f.get("openBibleLong") or f.get("longitude")
        if not (lat and lon): continue
        for nm in {f.get("esvName"), f.get("displayTitle"), f.get("kjvName")}:
            if nm and (nm not in byname or (f.get("verseCount") or 0) > byname[nm][2]):
                byname[nm] = (float(lon), float(lat), f.get("verseCount") or 0, f.get("slug"))
    journey, missing = [], []
    for nm, book, ch, cap in JOURNEY:
        hit = byname.get(nm) or next((v for k, v in byname.items() if k.lower().startswith(nm.lower())), None)
        if not hit: missing.append(nm); continue
        x, y = xy(hit[0], hit[1]); journey.append({"x": x, "y": y, "b": book, "c": ch, "cap": cap, "slug": hit[3]})
    paul = json.load(open(os.path.join(theo, "geo", "pauls_journeys_all.geojson"), encoding="utf-8"))
    pj = [{"n": f["properties"].get("name") or f["properties"].get("journey") or "", "d": path([seg for line in rings(f["geometry"]) for seg in clip_line(line)], 0.3, closed=False)}
          for f in paul["features"] if f["geometry"] and f["geometry"]["type"] in ("LineString", "MultiLineString")]
    w, h = xy(LON1, LAT0)
    out = {"view": [0, 0, w, h], "proj": {"lon0": LON0, "lat1": LAT1, "kx": KX, "ky": KY},
           "land": path(land_rings, 0.25), "rivers": [{"n": k, "d": path([seg for line in v for seg in clip_line(line)], 0.2, closed=False)} for k, v in rv.items()],
           "lakes": [l for l in lk if l["d"]], "journey": journey, "paul": [p for p in pj if p["d"]]}
    os.makedirs(os.path.join(HERE, "data", "map"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "data", "map", "base.json"), "w"), separators=(",", ":"))
    size = os.path.getsize(os.path.join(HERE, "data", "map", "base.json"))
    print(f"map base: {size//1024} KB | rivers {sorted(rv)} | lakes {len(out['lakes'])} | journey {len(journey)} stops | missing {missing} | paul routes {len(out['paul'])}")

if __name__ == "__main__":
    main()
