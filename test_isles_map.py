"""The Map in Explore (Ireland and Britain) — the plain maths behind the
drawing (the first part of static/js/explore_map.js, run under node: the
equal-area drawing, there and back; gathering nearby things into counted
marks; the scale line; finding) and the outline file it draws
(static/data/isles.json, made by tools/make_isles_map.py) — and its SKINS:
the colours each one works out (readable in both of the app's looks), the
listener's own skin, the dots and ruled lines that hold still on the ground,
and the app keeping the choice (map_look.py).
No browser, no network. Run:  ./venv/bin/python test_isles_map.py"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ── the outline file ──
import make_isles_map as mk
data = json.loads((ROOT / "static" / "data" / "isles.json").read_text())
w, s, e, n = data["box"]
chk([w, s, e, n] == list(mk.BOX) and data["land"] and all(len(r) >= 6 and len(r) % 2 == 0 for r in data["land"]), "the outline file holds land, cut to the map's box")
chk(all(w - 1e-6 <= r[i] <= e + 1e-6 and s - 1e-6 <= r[i + 1] <= n + 1e-6 for k in ("land", "far", "lakes", "rivers") for r in data[k] for i in range(0, len(r), 2)),
    "nothing in it lies outside the box")
chk(not any(k in json.dumps(data).lower() for k in ("border", "admin", "country")), "it holds land and water only: no borders, no countries")
sq = [(-20, 50), (-20, 55), (0, 55), (0, 50)]                       # a square half in, half out of the box (west edge at -11.2)
pts, touched = mk._clip_ring(sq, mk.BOX)
chk(touched and min(p[0] for p in pts) == w and max(p[0] for p in pts) == 0, "land that runs out of the box is cut at its edge, and known to have been (it is drawn as the far shore)")
pts, touched = mk._clip_ring([(-8, 52), (-8, 54), (-6, 54), (-6, 52)], mk.BOX)
chk(not touched and len(pts) == 4, "land inside the box is left whole")
chk(mk._clip_line([(-12, 53), (-10, 53), (-9, 53.5), (5, 53)], mk.BOX) == [[(-10, 53), (-9, 53.5)]], "a river is kept where it runs inside the box")
chk(mk.NAMES.get("Londonderry/Derry") == "Derry" and mk.NAMES.get("Muineachan") == "Monaghan", "Derry is called Derry, and Monaghan by its English name")
names = [p[0] for p in data["places"]]
if names:                                                            # (the real outline, not the stand-in)
    chk(names[0] == "London" and "Dublin" in names[:3] and "Derry" in names and "Monaghan" in names and not any("/" in x for x in names),
        "the towns come largest first: London, then Dublin; none carries two names")
    chk(len(data["land"]) > 50 and len(data["lakes"]) > 5 and len(data["rivers"]) > 5 and len(data["land"][0]) > 4000,
        "the outline is the detailed one: the coast in thousands of points, islands, lakes and rivers")
    chk(len(data["far"]) >= 1 and all(k not in json.dumps(data["places"]) for k in ("Calais", "Dieppe")), "the corner of the continent is drawn as the far shore, and nothing on it is named")

# ── the maths, under node ──
node = shutil.which("node")
if not node:
    print("  SKIP  no node here: the drawing's maths is not checked")
else:
    JS = r"""
    const M = require(process.argv[process.argv.length - 1]);
    const out = {};
    const near = (a, b, t) => Math.abs(a - b) <= (t || 1e-9);
    // there and back, all over the box
    let worst = 0;
    for (let lat = M.BOX.s; lat <= M.BOX.n; lat += 0.7) for (let lon = M.BOX.w; lon <= M.BOX.e; lon += 0.9) {
      const p = M.project(lat, lon), b = M.unproject(p[0], p[1]);
      worst = Math.max(worst, Math.abs(b.lat - lat), Math.abs(b.lon - lon));
    }
    out.roundtrip = worst;
    const mid = M.project(M.LAT0, M.LON0); out.middle = Math.hypot(mid[0], mid[1]);
    // north is +y, east is +x
    out.north = M.project(58, M.LON0)[1] > M.project(52, M.LON0)[1];
    out.east = M.project(53, 0)[0] > M.project(53, -8)[0];
    // equal-area: a small square of ground covers the same amount of drawing in Kerry as in Shetland
    const area = (lat, lon) => { const d = 0.05, a = M.project(lat, lon), b = M.project(lat, lon + d), c = M.project(lat + d, lon + d), e = M.project(lat + d, lon);
      const sh = Math.abs((a[0]*b[1]-b[0]*a[1]) + (b[0]*c[1]-c[0]*b[1]) + (c[0]*e[1]-e[0]*c[1]) + (e[0]*a[1]-a[0]*e[1])) / 2;
      const DEG = Math.PI / 180, ground = (d * DEG) * (Math.sin((lat + d) * DEG) - Math.sin(lat * DEG));   // on the sphere
      return sh / ground; };
    out.areas = [area(51.9, -10.2), area(60.3, -1.2), area(53.3, -6.3), area(51.5, 0.9)];
    // distances are true near the middle: Dublin to Holyhead is about 106 km
    const dub = M.project(53.3498, -6.2603), hol = M.project(53.3090, -4.6330);
    out.dubHol = Math.hypot(dub[0] - hol[0], dub[1] - hol[1]) * M.R_KM;
    const e = M.extent(); out.size = [(e.x1 - e.x0) * M.R_KM, (e.y1 - e.y0) * M.R_KM];
    out.inBox = [M.inBox(53.35, -6.26), M.inBox(51.5, -0.12), M.inBox(60.39, -1.15), M.inBox(52.52, 13.4), M.inBox(48.85, 2.35), M.inBox(5.6, -0.19)];
    // gathering
    const T = (id, lat, lon) => { const p = M.project(lat, lon); return { id, x: p[0], y: p[1] }; };
    const things = [T('dublin-a', 53.3498, -6.2603), T('dublin-b', 53.3498, -6.2603), T('dublin-c', 53.3461, -6.2710), T('galway', 53.2707, -9.0568), T('london', 51.5074, -0.1278), T('belfast', 54.5973, -5.9301)];
    const far = M.gather(things, M.R_KM / 2.0), mid2 = M.gather(things, M.R_KM / 0.2), close = M.gather(things, M.R_KM / 0.01);
    out.far = far.map(c => c.things.length).sort(); out.mid = mid2.map(c => c.things.length).sort(); out.close = close.map(c => c.things.length).sort();
    out.sameSpot = close.find(c => c.things.length === 2).spread; out.dubSpread = mid2.find(c => c.things.length === 3).spread;
    out.ids = [far.find(c => c.things.length === 1).id, close.find(c => c.things.length === 2).id];
    out.again = JSON.stringify(M.gather(things, M.R_KM / 2.0).map(c => c.id)) === JSON.stringify(far.map(c => c.id));
    out.centre = (c => [c.cx, c.cy, c.x, c.y])(M.gather([T('a', 53, -6), T('b', 53, -6.1)], M.R_KM / 2.0)[0]);
    out.ab = [M.project(53, -6), M.project(53, -6.1)];
    out.nice = [M.niceKm(1 / 2.0, 120), M.niceKm(1 / 0.2, 120), M.niceKm(1 / 0.01, 120), M.niceKm(1 / 40, 120)];
    out.ranks = [M.rankFor(5), M.rankFor(2.2), M.rankFor(1.5), M.rankFor(0.8), M.rankFor(0.05)];
    out.find = [M.matches(M.hayOf({ name: 'Éire Óg Records', kind: 'room', sub: 'label', tags: ['Trad'], place: { name: 'Gaillimh' } }), ['eire', 'label', 'gaillimh', 'trad']), M.matches(M.hayOf({ name: 'x', tags: [] }), ['y'])];
    // ── skins ──
    const PAGES = { paper: { bg: [242, 239, 232], ink: [22, 21, 19], red: [201, 65, 47] }, ink: { bg: [22, 21, 19], ink: [242, 239, 232], red: [232, 85, 74] } };
    const mine = M.skinFor('own', { sea: '#12312B', land: '#f3ead8', line: '#c9412f', text: '#1e272b', fill: 'dots' });
    out.skinIds = M.SKINS.map(s => s.id);
    out.skins = [];
    for (const pn in PAGES) for (const sk of M.SKINS.concat([mine])) {
      const T = M.tonesFor(sk, PAGES[pn]), c = T.rgb;
      out.skins.push({ id: sk.id, page: pn, fill: T.fill, name: M.contrast(c.name, c.slip), text: Math.min(M.contrast(c.text, c.slip), M.contrast(c.text, c.land)), scale: M.contrast(c.scale, c.sea),
        red: M.contrast(c.red, c.slip), edge: Math.max(M.contrast(c.coast, c.sea), M.contrast(c.land, c.sea)), town: M.contrast(c.town, c.land),
        valid: Object.keys(c).every(k => /^rgb\(\d+,\d+,\d+\)$/.test(T[k])) });
    }
    const asApp = M.tonesFor(M.skinFor('page'), PAGES.paper);
    out.asBefore = [asApp.sea, asApp.land, asApp.coast, asApp.slip, asApp.text];
    out.follows = [M.tonesFor(M.skinFor('page'), PAGES.ink).sea, M.tonesFor(M.skinFor('land'), PAGES.paper).land !== M.tonesFor(M.skinFor('land'), PAGES.ink).land,
                   M.tonesFor(M.skinFor('paper'), PAGES.ink).sea, M.tonesFor(M.skinFor('ink'), PAGES.paper).sea, M.tonesFor(M.skinFor('chart'), PAGES.ink).sea === M.tonesFor(M.skinFor('chart'), PAGES.paper).sea];
    // an app theme that says the map's colours itself: the skin that follows the app listens, a skin with its own colours does not
    const themed = Object.assign({ map: { sea: [207, 224, 220], land: [251, 243, 223], line: null, text: null } }, PAGES.paper);
    out.themed = [M.tonesFor(M.skinFor('page'), themed).sea, M.tonesFor(M.skinFor('page'), themed).slip, M.tonesFor(M.skinFor('page'), themed).coast, M.tonesFor(M.skinFor('chart'), themed).sea];
    out.tags = M.SKINS.filter(s => M.tonesFor(s, PAGES.paper).tag).map(s => s.id);
    // the listener's own
    out.own = [M.cleanOwn({ sea: '#ABCDEF', land: '000000', line: '#111111', text: '#ffffff', fill: 'zigzag', extra: 1 }), M.cleanOwn({ sea: '#abcdef', land: '#000000', line: 'red', text: '#ffffff' }), M.cleanOwn(null),
               mine.id, mine.sea, M.skinFor('own', null).id, M.skinFor('own', { sea: '#fff' }).id, M.skinFor('no-such-skin').id, M.tonesFor(mine, PAGES.ink).sea, M.tonesFor(mine, PAGES.ink).fill];
    out.hex = [M.hexRgb('#F2EFE8'), M.hexRgb('nope'), M.rgbHex([242.4, 239, 300]), M.contrast([0, 0, 0], [255, 255, 255])];
    // the dots and the ruled lines: fixed to the ground, more of them the closer the view, one even tone throughout
    let dotLo = 9, dotHi = 0, dotTone = [9, 0], lineLo = 9, lineHi = 0, lineTone = [9, 0], pitches = new Set(), growBad = 0;
    for (let s = 700; s < 700000; s *= 1.013) {
      const d = M.lattice(s, 6, 2), near = d.odd ? d.p * s / Math.SQRT2 : d.p * s, tone = (d.odd ? 2 : 1) * (1 + d.grow) / (d.p * s * d.p * s);
      dotLo = Math.min(dotLo, near); dotHi = Math.max(dotHi, near); dotTone = [Math.min(dotTone[0], tone), Math.max(dotTone[1], tone)];
      const r = M.lattice(s, 5, 1), t2 = (1 + r.grow) / (r.p * s);
      lineLo = Math.min(lineLo, r.p * s); lineHi = Math.max(lineHi, r.p * s); lineTone = [Math.min(lineTone[0], t2), Math.max(lineTone[1], t2)];
      pitches.add(Math.round(Math.log2(M.P0 / d.p) * 1e6) / 1e6); pitches.add(Math.round(Math.log2(M.P0 / r.p) * 1e6) / 1e6);
      if (d.grow < 0 || d.grow >= 1 || r.grow < 0 || r.grow >= 1) growBad++;
    }
    out.lattice = { dotLo, dotHi, dotTone, lineLo, lineHi, lineTone, whole: [...pitches].every(v => Number.isInteger(v)), growBad, far: M.lattice(1, 6, 2) };
    console.log(JSON.stringify(out));
    """
    r = subprocess.run([node, "-e", JS, "--", str(ROOT / "static" / "js" / "explore_map.js")], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        chk(False, "the map's maths runs under node: " + r.stderr.strip()[-300:])
    else:
        o = json.loads(r.stdout)
        chk(o["roundtrip"] < 1e-9 and o["middle"] < 1e-12, "a place drawn and read back is the same place, everywhere on the map")
        chk(o["north"] and o["east"], "north is up the drawing and east is to its right (before it is turned)")
        chk(max(o["areas"]) - min(o["areas"]) < 2e-4 and abs(o["areas"][0] - 1) < 2e-4, "equal-area: the same ground is the same size on the drawing in Kerry, Shetland, Dublin and Kent")
        chk(100 < o["dubHol"] < 112, "distances read true: Dublin to Holyhead is about 106 km")
        chk(900 < o["size"][0] < 1050 and 1200 < o["size"][1] < 1350, "the map is about 970 km across and 1270 km tall")
        chk(o["inBox"] == [True, True, True, False, False, False], "Dublin, London and Shetland are on the map; Berlin, Paris and Accra are not")
        chk(o["far"] == [1, 1, 1, 3] and o["mid"] == [1, 1, 1, 3] and o["close"] == [1, 1, 1, 1, 2], "things in one town gather; going closer pulls them apart; two at one spot stay together")
        chk(o["sameSpot"] < 0.001 and 0.5 < o["dubSpread"] < 1.2, "a gathering knows how far apart its things are (so one spot opens as a list)")
        chk(o["ids"][0] in ("galway", "london", "belfast") and o["ids"][1] == "n:dublin-a|dublin-b" and o["again"], "a mark is known by what is in it, the same way every time")
        chk(abs(o["centre"][0] - (o["ab"][0][0] + o["ab"][1][0]) / 2) < 1e-12 and o["centre"][2] == o["ab"][0][0], "a gathering is drawn at the middle of its things")
        chk(o["nice"] == [200, 20, 1, 500], "the scale line is a round number of kilometres that fits")
        chk(o["ranks"] == [3, 6, 7, 12, 12], "more towns are named the closer the view")
        chk(o["find"] == [True, False], "finding ignores accents and case, across name, kind, place and tags")
        # skins
        sk = o["skins"]
        chk(o["skinIds"] == ["page", "paper", "ink", "land", "sea", "dots", "ruled", "chart", "blueprint"] and len(sk) == 20 and all(x["valid"] for x in sk),
            "nine skins come with the map; each works out every colour of the drawing, in either of the app's looks")
        worst = lambda k: min(sk, key=lambda x: x[k])
        chk(worst("name")["name"] >= 4.5, f"a town's name can be read on its ground in every skin (the hardest: {worst('name')['id']} on {worst('name')['page']}, {worst('name')['name']:.1f} to 1)")
        chk(worst("text")["text"] >= 7 and worst("town")["town"] >= 4.5, f"the marks and their names stand out from the land in every skin (the hardest: {worst('text')['id']}, {worst('text')['text']:.1f} to 1)")
        chk(worst("scale")["scale"] >= 3, f"the scale line shows on the sea in every skin, a filled sea too (the hardest: {worst('scale')['id']}, {worst('scale')['scale']:.1f} to 1)")
        chk(worst("red")["red"] >= 3, f"the red of the thing that is chosen shows in every skin (the hardest: {worst('red')['id']}, {worst('red')['red']:.1f} to 1)")
        chk(worst("edge")["edge"] >= 2, f"the land can be told from the sea in every skin (the hardest: {worst('edge')['id']}, {worst('edge')['edge']:.1f} to 1)")
        chk({x["id"]: x["fill"] for x in sk}["dots"] == "dots" and {x["id"]: x["fill"] for x in sk}["ruled"] == "lines" and {x["id"]: x["fill"] for x in sk}["page"] == "flat",
            "the land is filled flat, in dots, or ruled")
        chk(o["asBefore"] == ["rgb(242,239,232)", "rgb(226,223,216)", "rgb(53,52,49)", "rgb(242,239,232)", "rgb(22,21,19)"], "the skin that follows the app is the map as it was: the page, a faint land, an ink coast")
        chk(o["follows"] == ["rgb(22,21,19)", True, "rgb(242,239,232)", "rgb(22,21,19)", True],
            "skins that follow the app turn over with its look; Paper stays light, Ink stays dark, and a skin with its own colours keeps them")
        chk(o["themed"][:3] == ["rgb(207,224,220)", "rgb(251,243,223)", "rgb(53,52,49)"] and o["themed"][3] == "rgb(217,227,227)",
            "an app theme may say the map's colours itself: the skin that follows the app takes them (and works out the rest), another skin does not")
        chk(o["tags"] == ["land", "sea", "chart", "blueprint"], "where the land is not the sea's colour, a name out over the water stands on a tag of the land's")
        own = o["own"]
        chk(own[0] == {"sea": "#abcdef", "land": "#000000", "line": "#111111", "text": "#ffffff", "fill": "flat"} and own[1] is None and own[2] is None,
            "a skin of your own is four colours and a fill, tidied; with a colour missing it is no skin")
        chk(own[3:8] == ["own", "#12312b", "page", "page", "page"] and own[8] == "rgb(18,49,43)" and own[9] == "dots",
            "your own skin keeps its colours whatever the app wears; with none made (or a name nobody knows) the map falls back to following the app")
        chk(o["hex"][0] == [242, 239, 232] and o["hex"][1] is None and o["hex"][2] == "#f2efff" and abs(o["hex"][3] - 21) < 1e-9, "colours are read and written as #rrggbb, and compared the usual way (black on white is 21 to 1)")
        la = o["lattice"]
        chk(6 - 1e-9 <= la["dotLo"] and la["dotHi"] < 6 * 2 ** 0.5 + 1e-9 and 5 - 1e-9 <= la["lineLo"] and la["lineHi"] < 10 + 1e-9,
            "going closer, dots stay between 6 and 8.5 pixels apart and ruled lines between 5 and 10: new ones come up in the gaps")
        chk(la["dotTone"][1] - la["dotTone"][0] < 1e-12 and abs(la["dotTone"][0] - 1 / 36) < 1e-12 and la["lineTone"][1] - la["lineTone"][0] < 1e-12 and abs(la["lineTone"][0] - 1 / 5) < 1e-12,
            "a new dot or line grows in by just as much as keeps the land one even tone, at every distance")
        chk(la["whole"] and la["growBad"] == 0 and la["far"]["grow"] == 0 and abs(la["far"]["p"] - 0.064) < 1e-12,
            "each finer pitch is half the one before, so a dot that is there stays where it is on the ground")

# ── the app keeps the look (map_look.py) ──
import map_look
OWN = {"sea": "#D9E3E3", "land": "#efe6cf", "line": "#2a3439", "text": "#1e272b", "fill": "dots", "x": "<script>"}
chk(map_look.clean({"skin": "chart", "up": -1, "towns": False, "rivers": True}) == {"skin": "chart", "up": -1, "towns": False, "rivers": True}, "a look is a skin, which way is up, and what is drawn")
chk(map_look.clean({"skin": "own", "own": OWN}) == {"skin": "own", "own": {"sea": "#d9e3e3", "land": "#efe6cf", "line": "#2a3439", "text": "#1e272b", "fill": "dots"}},
    "your own skin is kept as four colours and a fill, and nothing else that was sent with it")
chk(map_look.clean({"skin": "own"}) == {} and map_look.clean({"skin": "own", "own": {"sea": "#fff"}}) == {}, "'your own' with no colours, or not all four, is not kept as the skin")
chk(map_look.clean({"skin": "<b>x</b>", "up": 5, "towns": "yes", "own": "red"}, {"skin": "ink", "up": -1}) == {"skin": "ink", "up": -1}, "what makes no sense leaves what was kept as it was")
chk(map_look.clean({"skin": "ruled"}, {"skin": "own", "own": map_look.clean_own(OWN)})["own"]["fill"] == "dots", "choosing another skin keeps your own for later")
try:
    from flask import Flask
except ImportError:
    Flask = None
    print("  SKIP  no Flask here: the look's two addresses are not checked")
if Flask:
    kept, said = {}, []
    fl = Flask("look-test")
    map_look.register(fl, lambda k, d="": kept.get(k, d), lambda k, v: kept.__setitem__(k, v), track=lambda name, data: said.append((name, data)))
    c = fl.test_client()
    chk(c.get("/api/isles/look").get_json() == {} and fl.jinja_env.globals["map_look"]() == {}, "before anything is chosen the app keeps no look (the page's own memory, then the plain map, stand in)")
    r = c.post("/api/isles/look", json={"skin": "dots", "up": 1, "towns": True, "rivers": False})
    chk(r.get_json() == {"skin": "dots", "up": 1, "towns": True, "rivers": False} and c.get("/api/isles/look").get_json()["skin"] == "dots" and said == [("map_skin", {"id": "dots"})],
        "a chosen skin is kept by the app and comes back; the trial's log notes the choice")
    c.post("/api/isles/look", json={"rivers": True}); c.post("/api/isles/look", json={"skin": "dots"})
    chk(len(said) == 1 and c.get("/api/isles/look").get_json() == {"skin": "dots", "up": 1, "towns": True, "rivers": True}, "changing one thing leaves the rest; the same skin again is not noted twice")
    r = c.post("/api/isles/look", json={"skin": "own", "own": OWN})
    chk(r.get_json()["skin"] == "own" and r.get_json()["own"]["sea"] == "#d9e3e3" and "x" not in r.get_json()["own"] and fl.jinja_env.globals["map_look"]()["skin"] == "own" and said[-1] == ("map_skin", {"id": "own"}),
        "your own skin is kept too, and the pages that hold a map are handed it as they are made")
    r = c.post("/api/isles/look", data="not json", content_type="text/plain")
    chk(r.status_code == 200 and r.get_json()["skin"] == "own", "nonsense sent to it changes nothing")
    kept[map_look.KEY] = "{broken"
    chk(c.get("/api/isles/look").get_json() == {}, "a look that can't be read is no look, not an error")
import themes
t, err = themes.validate({"name": "Sea green", "vars": {"bg": "#101418", "map-sea": "#203040", "map-land": "#f0e0c0", "map-nonsense": "#fff"}})
chk(err is None and t["vars"].get("map-sea") == "#203040" and "map-nonsense" not in t["vars"] and "--map-sea:#203040" in themes.css_for(t) and "--map-" not in themes.css_for(themes.LIGHT),
    "an app theme may carry the map's colours (map-sea, map-land, map-line, map-text); the two built-in themes leave them to be worked out")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
