"""Make static/data/isles.json — what the Map in Explore draws: the coast of
Ireland and Britain, their islands, lakes and rivers, and the names of towns.

  python tools/make_isles_map.py --from <folder>   the real thing, from Natural
        Earth's 1:10m files (public domain; github.com/nvkelso/natural-earth-vector,
        folder "geojson"): ne_10m_land, ne_10m_minor_islands, ne_10m_lakes,
        ne_10m_lakes_europe, ne_10m_rivers_lake_centerlines, ne_10m_rivers_europe,
        ne_10m_populated_places_simple (any that are missing are left out)
  python tools/make_isles_map.py --standin         a rough outline only, from the
        coarse world file the app already carries (static/vendor/map)

Everything is cut to one box round the two islands. Land that runs out of the
box (the corner of the continent) is kept apart as "far": drawn fainter, and
nothing is ever placed on it. No borders are read or written: there is only
land and water. Coordinates are kept to four places (about ten metres).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "data" / "isles.json"
BOX = (-11.2, 49.75, 2.3, 61.0)              # west, south, east, north
# names as they are said here, where the source says otherwise (the app's
# words are in English: two Irish county towns come in Irish with the accents
# dropped, so they are given their English names)
NAMES = {"Londonderry/Derry": "Derry", "Londonderry": "Derry", "Muineachan": "Monaghan", "Ros Comain": "Roscommon",
         "Kingston upon Hull": "Hull", "Dun Laoghaire": "Dún Laoghaire"}


def _clip_ring(ring, box):
    """A closed ring cut to the box (Sutherland–Hodgman). → (points, touched the edge?)"""
    w, s, e, n = box
    touched = False

    def cut(pts, inside, cross):
        nonlocal touched
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            ci, pi = inside(cur), inside(prev)
            if ci:
                if not pi:
                    out.append(cross(prev, cur)); touched = True
                out.append(cur)
            elif pi:
                out.append(cross(prev, cur)); touched = True
        return out

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    pts = [tuple(p[:2]) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    for inside, cross in ((lambda p: p[0] >= w, at_x(w)), (lambda p: p[0] <= e, at_x(e)),
                          (lambda p: p[1] >= s, at_y(s)), (lambda p: p[1] <= n, at_y(n))):
        if not pts:
            break
        pts = cut(pts, inside, cross)
    return pts, touched


def _clip_line(line, box):
    """A line cut to the box → the pieces of it that lie inside."""
    w, s, e, n = box
    pieces, cur = [], []
    for p in line:
        if w <= p[0] <= e and s <= p[1] <= n:
            cur.append((p[0], p[1]))
        else:
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


def _flat(pts):
    out = []
    for x, y in pts:
        out += [round(x, 4), round(y, 4)]
    return out


def _rings(geom):
    if not geom:
        return
    t, c = geom.get("type"), geom.get("coordinates") or []
    polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
    for poly in polys:
        if poly:
            yield poly[0]                    # the outer ring; holes are lakes, drawn from the lakes file


def _lines(geom):
    if not geom:
        return
    t, c = geom.get("type"), geom.get("coordinates") or []
    for line in ([c] if t == "LineString" else c if t == "MultiLineString" else []):
        yield line


def _load(folder, name):
    p = Path(folder) / name
    if not p.exists():
        print(f"  (no {name})")
        return []
    return json.loads(p.read_text()).get("features") or []


def build(folder=None):
    land, far, lakes, rivers, places = [], [], [], [], []
    w, s, e, n = BOX
    if folder is None:                                       # the stand-in: two rough outlines
        src = "a rough outline, from the coarse world file the app carries"
        world = json.loads((ROOT / "static" / "vendor" / "map" / "ne_110m_countries.json").read_text())
        for f in world.get("features") or []:
            p = f.get("properties") or {}
            if (p.get("ISO_A2") or p.get("iso_a2") or "") in ("GB", "IE") or (p.get("ADMIN") or p.get("admin")) in ("United Kingdom", "Ireland"):
                for ring in _rings(f.get("geometry")):
                    pts, _t = _clip_ring(ring, BOX)
                    if len(pts) >= 3:
                        land.append(_flat(pts))
    else:
        src = "Natural Earth 1:10m (public domain)"
        for name in ("ne_10m_land.geojson", "ne_10m_minor_islands.geojson"):
            for f in _load(folder, name):
                for ring in _rings(f.get("geometry")):
                    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
                    if max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n:
                        continue
                    pts, touched = _clip_ring(ring, BOX)
                    if len(pts) >= 3:
                        (far if touched else land).append(_flat(pts))
        for name in ("ne_10m_lakes.geojson", "ne_10m_lakes_europe.geojson"):
            for f in _load(folder, name):
                for ring in _rings(f.get("geometry")):
                    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
                    if max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n:
                        continue
                    pts, touched = _clip_ring(ring, BOX)
                    if len(pts) >= 3 and not touched:
                        lakes.append(_flat(pts))
        for name in ("ne_10m_rivers_lake_centerlines.geojson", "ne_10m_rivers_europe.geojson"):
            for f in _load(folder, name):
                for line in _lines(f.get("geometry")):
                    for piece in _clip_line(line, BOX):
                        rivers.append(_flat(piece))
        seen = set()
        for f in _load(folder, "ne_10m_populated_places_simple.geojson"):
            p = f.get("properties") or {}
            if (p.get("adm0name") or "") not in ("United Kingdom", "Ireland", "Isle of Man"):
                continue
            lat, lon = p.get("latitude"), p.get("longitude")
            if lat is None or lon is None or not (w <= lon <= e and s <= lat <= n):
                continue
            name = NAMES.get(p.get("name") or "", p.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            rank = p.get("scalerank")                                # 0 is the largest (London): "no rank" is a different thing
            places.append([name, round(lat, 4), round(lon, 4), 9 if rank is None else int(rank), int(p.get("pop_max") or 0)])
        places.sort(key=lambda x: (x[3], -x[4], x[0]))
        places = [p[:4] for p in places]
    land.sort(key=len, reverse=True)
    return {"v": 1, "source": src, "box": list(BOX), "land": land, "far": far, "lakes": lakes,
            "rivers": rivers, "places": places}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="folder", help="a folder holding Natural Earth's 10m geojson files")
    g.add_argument("--standin", action="store_true", help="a rough outline from the coarse world file the app carries")
    args = ap.parse_args()
    data = build(None if args.standin else args.folder)
    if not data["land"]:
        sys.exit("no land found: nothing written")
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    pts = sum(len(r) // 2 for k in ("land", "far", "lakes", "rivers") for r in data[k])
    print(f"written: {OUT.relative_to(ROOT)} — {OUT.stat().st_size / 1024:.0f} KB · {len(data['land'])} pieces of land, "
          f"{len(data['far'])} of the continent, {len(data['lakes'])} lakes, {len(data['rivers'])} river lines, "
          f"{len(data['places'])} towns · {pts} points · {data['source']}")


if __name__ == "__main__":
    main()
