"""The Globe in Explore — what it is fed (explore_globe.py, the catalogue's
places) and the plain maths behind the drawing (the first part of
static/js/explore_globe.js, run under node: the equal-area dots, the gathering
of nearby things into counted marks, the universal ring, finding).
No browser, no network, no rooms server. Run:  ./venv/bin/python test_globe.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import explore_globe as eg

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ── a place is a name and a real spot, or it is nothing ──
chk(eg.clean_place({"name": "  Gaillimh ", "lat": "53.2707", "lon": -9.0568}) == {"name": "Gaillimh", "lat": 53.2707, "lon": -9.0568}, "a place: the owner's words, tidied, and the spot as numbers")
chk(all(eg.clean_place(p) is None for p in (None, "Dublin", {}, {"name": "x"}, {"name": "x", "lat": 91, "lon": 0}, {"name": "x", "lat": 0, "lon": 181}, {"name": "x", "lat": "n", "lon": 1})),
    "no spot, half a spot, or a spot off the globe is no place (the thing stays universal)")
chk(eg.clean_place({"lat": -90, "lon": 180}) == {"name": "", "lat": -90.0, "lon": 180.0}, "the poles and the date line are places; a spot needs no name")

# ── what the globe is fed ──
CAT = [{"id": "nts", "name": "NTS Radio", "url": "https://www.nts.live", "type": "station", "kind": "station", "tags": ["radio"], "blurb": "b",
        "place": {"name": "Dalston, London", "lat": 51.546, "lon": -0.075}, "feed_url": "https://x/feed"},
       {"id": "bc", "name": "Bandcamp Daily", "url": "https://daily.bandcamp.com", "type": "publication", "kind": "magazine"},
       {"id": "odd", "name": "Odd", "url": "https://odd.example", "type": "something-else"}]
OWN = [{"id": 1, "name": "NTS", "url": "https://nts.live/shows", "kind": "station", "description": "", "topics": ""},
       {"id": 2, "name": "My Blog", "url": "https://myblog.example/feed", "kind": "blog", "description": "notes", "topics": "ambient; dub, tape"},
       {"id": 3, "name": "No Address", "url": "", "kind": "magazine", "description": "", "topics": ""}]
ROOMS = [{"handle": "moss", "name": "Moss", "kind": "label", "bio": "slow", "track_count": 4, "cover_track_ids": [1, 2, 3, 4, 5],
          "place": {"name": "Corcaigh", "lat": 51.8985, "lon": -8.4756}},
         {"handle": "elder", "name": "", "kind": None, "bio": None},              # a server from before places: no "place" key at all
         {"name": "no handle"}]
out = eg.things(rooms_fn=lambda: ROOMS, catalogue_fn=lambda: CAT, sources_fn=lambda: OWN)
by = {t["id"]: t for t in out["things"]}
chk(out["rooms_error"] is None and set(by) == {"cat:nts", "cat:bc", "cat:odd", "src:2", "room:moss", "room:elder"}, "catalogue entries, the listener's own extra sources, and rooms — each once")
chk(by["cat:nts"]["kind"] == "station" and by["cat:nts"]["place"]["name"] == "Dalston, London" and by["cat:nts"]["added"] is True,
    "a catalogue entry keeps its kind and place, and knows the listener already follows it (matched by its address)")
chk(by["cat:bc"]["place"] is None and by["cat:bc"]["added"] is False and by["cat:odd"]["kind"] == "website", "no place = universal; an unknown type is shown as a website")
chk(by["src:2"]["kind"] == "publication" and by["src:2"]["place"] is None and by["src:2"]["tags"] == ["ambient", "dub", "tape"] and by["src:2"]["mine"],
    "a source the listener added by hand: universal, with its topics as tags")
chk("src:1" not in by and "src:3" not in by, "a source the catalogue already holds isn't shown twice; one with no address isn't shown")
chk(by["room:moss"]["sub"] == "label" and by["room:moss"]["place"]["name"] == "Corcaigh" and by["room:moss"]["count"] == 4 and len(by["room:moss"]["covers"]) == 4,
    "a room: what kind of room, its place, its records, four covers at most")
chk(by["room:elder"]["place"] is None and by["room:elder"]["sub"] == "listener" and by["room:elder"]["name"] == "elder", "a room from an older server: universal, and still listed")
def away(): raise RuntimeError("not signed in")
gone = eg.things(rooms_fn=away, catalogue_fn=lambda: CAT, sources_fn=lambda: [])
chk(gone["rooms_error"] == "not signed in" and len(gone["things"]) == 3, "with the rooms server away, everything else still shows and the reason is passed on")
chk([t["id"] for t in eg.things(rooms_fn=lambda: ROOMS, catalogue_fn=lambda: CAT, sources_fn=lambda: [], parts=("rooms",))["things"]] == ["room:moss", "room:elder"],
    "the two halves can be asked for separately (the rooms may take a moment)")

from flask import Flask
app = Flask(__name__)
eg.register(app)
real_src, real_rooms = eg._source_things, eg._room_things
eg._source_things = lambda *a, **k: [{"id": "cat:x", "kind": "station", "name": "X", "place": None}]
eg._room_things = lambda *a, **k: ([], "the rooms server is away")
c = app.test_client()
d = c.get("/api/globe/things?part=sources").get_json()
chk([t["id"] for t in d["things"]] == ["cat:x"] and d["rooms_error"] is None, "the route: ?part=sources answers without waiting on the rooms")
d = c.get("/api/globe/things").get_json()
chk(len(d["things"]) == 1 and d["rooms_error"] == "the rooms server is away", "the route: everything at once, saying why rooms are missing")
eg._source_things, eg._room_things = real_src, real_rooms

# ── the catalogue's own places ──
cat = json.load(open(ROOT / "static" / "data" / "source_catalogue.json", encoding="utf-8"))
entries = cat if isinstance(cat, list) else (cat.get("entries") or cat.get("sources") or [])
placed = [e for e in entries if e.get("place")]
chk(len(entries) >= 30 and 10 <= len(placed) < len(entries), f"the catalogue: {len(entries)} entries, {len(placed)} with a place, the rest universal")
chk(all(eg.clean_place(e["place"]) and eg.clean_place(e["place"])["name"] for e in placed), "every place in the catalogue has a name and a real spot")
universal = {e["name"] for e in entries if not e.get("place")}
chk({"Bandcamp Daily", "SoundCloud", "Discogs", "Mixcloud", "Radio Garden"} <= universal, "platforms that are for everywhere are left universal on purpose")
import source_catalogue
chk(any(e.get("place") for e in source_catalogue.all_entries()), "the catalogue hands its places on to the globe")

# ── the maths behind the drawing, under node ──
node = shutil.which("node")
if not node:
    print("  SKIP  node isn't installed: the drawing's maths was not run")
else:
    # the land/water picture as bits, and its share of land weighted by the true area of each row
    from PIL import Image
    im = Image.open(ROOT / "static" / "data" / "globe_land.png").convert("L")
    W, H = im.size
    px = im.tobytes()
    bits = [1 if b > 127 else 0 for b in px]
    import math
    num = den = 0.0
    for y in range(H):
        w = math.cos(math.radians(90 - (y + 0.5) * 180 / H))
        row = sum(bits[y * W:(y + 1) * W])
        num += w * row; den += w * W
    land_share = num / den
    tmp = Path(tempfile.mkdtemp())
    (tmp / "mask.json").write_text(json.dumps({"W": W, "H": H, "bits": bits}))
    js = r"""
const G = require(process.argv[2]), mask = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const out = {}, near = (a, b, e) => Math.abs(a - b) <= e;
// places and directions
const ll = G.latLonOf(G.vecOf(53.35, -6.26)); out.roundTrip = near(ll.lat, 53.35, 1e-9) && near(ll.lon, -6.26, 1e-9);
out.poles = near(G.vecOf(90, 0)[1], 1, 1e-12) && near(G.vecOf(-90, 77)[1], -1, 1e-12);
// facing: the spot comes to the middle of the view, and the chosen pole is drawn upward
const v = G.vecOf(51.5, -0.12), q = G.qFace(v, [0, -1, 0]), f = G.qRot(q, v), south = G.qRot(q, [0, -1, 0]);
out.faces = near(f[0], 0, 1e-9) && near(f[1], 0, 1e-9) && near(f[2], 1, 1e-9); out.southUp = south[1] > 0 && near(south[0], 0, 1e-9);
const qn = G.qFace(v, [0, 1, 0]); out.northUp = G.qRot(qn, [0, 1, 0])[1] > 0;
const b = G.qBetween(G.vecOf(0, 0), G.vecOf(0, 90)), moved = G.qRot(b, G.vecOf(0, 0)), want = G.vecOf(0, 90);
out.between = near(moved[0], want[0], 1e-9) && near(moved[1], want[1], 1e-9) && near(moved[2], want[2], 1e-9);
// the dots: an even lattice. With land everywhere every dot is drawn; equal bands of the sphere hold equal numbers of dots
const all = { W: 4, H: 2, bits: new Uint8Array(8).fill(1) }, N = 20000, buf = new Float32Array(N * 3);
out.allLand = G.latticeLand(N, 0, N, all, buf) === N * 3;
const bands = new Array(10).fill(0); for (let i = 0; i < N; i++) bands[Math.min(9, Math.floor((buf[i * 3 + 1] + 1) * 5))]++;
out.equalBands = Math.max(...bands) - Math.min(...bands) <= 2;
const lon8 = new Array(8).fill(0); for (let i = 0; i < N; i++) lon8[Math.floor(((Math.atan2(-buf[i * 3 + 2], buf[i * 3]) / Math.PI + 1) * 4)) % 8]++;
out.equalWedges = (Math.max(...lon8) - Math.min(...lon8)) / (N / 8) < 0.03;
// …so the share of dots that fall on land is the land's true share of the earth
const m = { W: mask.W, H: mask.H, bits: Uint8Array.from(mask.bits) }, M = 65536, big = new Float32Array(M * 3);
out.landDots = G.latticeLand(M, 0, M, m, big) / 3 / M;
const half = G.latticeLand(M, 0, M / 2, m, big) / 3 + G.latticeLand(M, M / 2, M, m, big) / 3; out.inSlices = near(half / M, out.landDots, 1e-12);
// gathering: nearby things become one counted mark; closer views pull them apart
const P = (id, lat, lon) => ({ id, v: G.vecOf(lat, lon), thing: { id } });
const leaves = [P('lon1', 51.507, -0.128), P('lon2', 51.507, -0.128), P('peck', 51.474, -0.069), P('dals', 51.546, -0.075), P('bris', 51.454, -2.588),
                P('dub', 53.35, -6.26), P('ber', 52.52, 13.405), P('nyc', 40.72, -73.95), P('chi', 41.88, -87.63)];
const Hh = G.buildHierarchy(leaves, G.RADII);
out.levels = Hh.levels.length === G.RADII.length;
out.keepsAll = Hh.levels.every(L => L.reduce((s, n) => s + n.n, 0) === leaves.length);
out.fewerFurther = Hh.levels.every((L, k) => k === 0 || L.length <= Hh.levels[k - 1].length);
out.fine = Hh.levels[0].length;                          // 19 km: the four in London are one, the rest stand alone
out.sizes = Hh.levels.map(L => L.length);                // how many marks at each level, closest view first
const london = Hh.levels[0].find(n => n.n === 4); out.londonIsFour = !!london && G.thingsOf(london).map(t => t.id).sort().join() === 'dals,lon1,lon2,peck';
out.londonOpensAsList = G.splitDist(london, 1000, G.RADII) === null;      // no view parts it: it opens as a list
const top = Hh.levels[G.RADII.length - 1].slice().sort((a, b) => b.n - a.n)[0];
const sd = G.splitDist(top, 1000, G.RADII); out.bigComesApart = sd !== null && sd >= G.MIN_DIST && sd <= G.MAX_DIST;
const leafDub = Hh.leaves.find(l => l.id === 'dub'), leafLon = Hh.leaves.find(l => l.id === 'lon1');
out.aloneOrdered = G.aloneDist(leafLon, 1000, G.RADII) >= G.MIN_DIST && G.aloneDist(leafDub, 1000, G.RADII) <= G.MAX_DIST;
// nothing goes wrong at the date line or the poles (there is no flat map in it)
const seam = G.buildHierarchy([P('a', 10, 179.95), P('b', 10, -179.95)], G.RADII); out.dateLine = seam.levels[0].length === 1;
const pole = G.buildHierarchy([P('a', 89.95, 0), P('b', 89.95, 180), P('c', 89.95, -90)], G.RADII); out.pole = pole.levels[0].length === 1;
const apart = G.buildHierarchy([P('a', 0, 0), P('b', 0, 180)], G.RADII); out.antipodes = apart.levels.every(L => L.length === 2);
// which level a view calls for: closer = finer
const lv = [7, 4, 2.5, 1.6, 1.2].map(d => G.levelFor(G.viewTheta(d, 1000), G.RADII));
out.closerIsFiner = lv.every((x, i) => i === 0 || x <= lv[i - 1]) && lv[0] > lv[lv.length - 1];
// the ring: by kind, then A to Z; when there are too many, counted runs — every thing in exactly one
const T = (kind, name) => ({ id: kind + ':' + name, kind, name });
const few = [T('website', 'Zed'), T('room', 'Éire Room'), T('room', 'Alpha'), T('station', 'Mid')];
out.ringFew = G.ringSlots(few, 12).map(s => s.things[0].name).join('|');
const many = []; for (let i = 0; i < 200; i++) many.push(T(i % 5 === 0 ? 'room' : i % 2 ? 'publication' : 'website', 'n' + String(i).padStart(3, '0')));
const slots = G.ringSlots(many, 16), seen = new Set(); for (const s of slots) for (const t of s.things) seen.add(t.id);
out.ringMany = slots.length <= 16 && seen.size === 200 && slots.reduce((a, s) => a + s.things.length, 0) === 200 && new Set(slots.map(s => s.kind)).size === 3;
out.ringRuns = slots.every(s => s.things.every((t, i) => i === 0 || s.things[i - 1].name <= t.name));
// finding: every word typed must be somewhere in it; accents don't matter
const hay = G.hayOf({ name: 'Raidió na Life', kind: 'station', place: { name: 'Baile Átha Cliath' }, tags: ['irish', 'radio'], blurb: 'community station' });
out.find = G.matches(hay, ['atha', 'radio']) && G.matches(hay, ['raidio']) && !G.matches(hay, ['atha', 'berlin']) && G.fold('Ünïcödé') === 'unicode';
out.roomHay = G.matches(G.hayOf({ name: 'Moss', kind: 'room', sub: 'label', handle: 'moss' }), ['music', 'room', 'label']);
// the ring passes behind the globe
out.behind = G.behindGlobe(0, 0, -1.5, 4) === true && G.behindGlobe(0, 0, 1.5, 4) === false && G.behindGlobe(1.5, 0, 0, 4) === false;
console.log(JSON.stringify(out));
"""
    (tmp / "run.js").write_text(js)
    r = subprocess.run([node, str(tmp / "run.js"), str(ROOT / "static" / "js" / "explore_globe.js"), str(tmp / "mask.json")], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        chk(False, "the drawing's maths runs under node: " + (r.stderr.strip().splitlines() or ["?"])[-1][:200])
    else:
        o = json.loads(r.stdout)
        chk(o["roundTrip"] and o["poles"], "a place ⇄ a direction from the earth's centre, and back")
        chk(o["faces"] and o["southUp"] and o["northUp"], "facing a spot brings it to the middle, with south (or north) drawn upward as asked")
        chk(o["between"], "the shortest turn takes one direction onto another")
        chk(o["allLand"] and o["equalBands"] and o["equalWedges"], "the dots are an even lattice: equal slices of the sphere hold equal numbers of dots")
        chk(abs(o["landDots"] - land_share) < 0.012, f"so the share of dots on land ({o['landDots']:.3f}) is the land's true share of the earth in the picture ({land_share:.3f}) — every dot stands for the same area")
        chk(0.24 < land_share < 0.34, "…and the land picture itself is about three-tenths land, as the earth is")
        chk(o["inSlices"], "the lattice can be built in slices and comes out the same")
        chk(o["levels"] and o["keepsAll"] and o["fewerFurther"], "gathering: every level accounts for every thing, and further back there are never more marks")
        chk(o["fine"] == 6 and o["londonIsFour"], "closest in: the four in London (one spot twice, Peckham, Dalston) are one mark; the other five stand alone")
        chk(o["sizes"] == sorted(o["sizes"], reverse=True) and o["sizes"][0] == 6 and 2 in o["sizes"] and o["sizes"][-1] == 1,
            f"stepping back: {o['sizes']} marks level by level — at one point two (one each side of the Atlantic), and from furthest back, one")
        chk(o["londonOpensAsList"] and o["bigComesApart"] and o["aloneOrdered"], "a mark no view can part opens as a list; a wide one comes apart by moving closer")
        chk(o["dateLine"] and o["pole"] and o["antipodes"], "neighbours across the date line and round a pole gather; opposite sides of the earth never do")
        chk(o["closerIsFiner"], "moving closer always calls for a finer level, never a coarser one")
        chk(o["ringFew"] == "Alpha|Éire Room|Mid|Zed", "the ring, when there is room: one mark each — by kind, then A to Z with accents folded")
        chk(o["ringMany"] and o["ringRuns"], "the ring, when there isn't: counted runs, every thing in exactly one, every kind still there")
        chk(o["find"] and o["roomHay"], "finding: every word must be in the name, place, kind, tags or blurb; accents don't matter")
        chk(o["behind"], "a mark on the ring is hidden while it passes behind the globe")
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
