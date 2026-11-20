"""Proves STRUCTURES: a saved spatial arrangement of tag/genre nodes that the
user shapes by hand. Nodes are created by NAME (find-or-create the tag/genre),
positioned, coloured and connected; a structure exports to a USB as one folder
of files with a playlist PER NODE in the stick's rekordbox XML and Engine DJ
database. Run:  venv/bin/python test_structures.py
"""
import os, sys, sqlite3, tempfile, subprocess, json, xml.etree.ElementTree as ET

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_struct_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

AUD = os.path.join(TMP, "audio"); os.makedirs(AUD)
db = sqlite3.connect(DB)
for i in (1, 2, 3):
    p = os.path.join(AUD, f"t{i}.mp3")
    with open(p, "wb") as f: f.write(b"ID3" + bytes(64 * i))
    db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(?,?,?,0)",
               (i, f"Track {i}", f"Artist {i}"))
    db.execute("""INSERT INTO files(id,track_id,file_path,file_format,is_primary,is_deleted,
                  duration_sec,file_size_mb) VALUES(?,?,?,'mp3',1,0,180,0.001)""", (i, i, p))
db.commit(); db.close()

import app
c = app.app.test_client()

# build the structure: energy-3 / energy-4 (tags created on the fly) + a genre
r = c.post("/api/structures", json={"name": "club system"}).get_json()
sid = r["id"]
chk(r.get("ok") and sid, "structure created")
n3 = c.post(f"/api/structure/{sid}/nodes", json={"kind": "tag", "name": "energy 3", "x": -10, "y": 0, "colour": "#777"}).get_json()
n4 = c.post(f"/api/structure/{sid}/nodes", json={"kind": "tag", "name": "energy 4", "x": 10, "y": 0}).get_json()
ng = c.post(f"/api/structure/{sid}/nodes", json={"kind": "genre", "name": "techno", "x": 0, "y": 10}).get_json()
chk(n3.get("id") and n4.get("id") and ng.get("id"), "nodes created by name (tags + genre find-or-create)")

dup = c.post(f"/api/structure/{sid}/nodes", json={"kind": "tag", "name": "energy 3"}).get_json()
chk(dup.get("id") == n3["id"], "re-adding the same tag returns the same node")

# tag the records through the EXISTING tag/genre APIs (what drag-onto-node calls)
c.post("/api/track/1/tag", json={"name": "energy 3"})
c.post("/api/track/2/tag", json={"name": "energy 4"})
c.post("/api/track/2/genre", json={"name": "techno"})

s = c.get(f"/api/structure/{sid}").get_json()
byname = {n["name"]: n for n in s["nodes"]}
chk(byname["energy 3"]["n_tracks"] == 1 and byname["energy 4"]["n_tracks"] == 1
    and byname["techno"]["n_tracks"] == 1, "structure payload counts each node's records")
chk(byname["energy 3"]["x"] == -10 and byname["energy 3"]["colour"] == "#777",
    "positions and colour persist")

# move a node; connect two; label the line
c.patch(f"/api/structure/node/{n3['id']}", json={"x": -20, "y": 5})
l = c.post(f"/api/structure/{sid}/links", json={"from_node_id": n3["id"], "to_node_id": n4["id"], "label": "build"}).get_json()
s2 = c.get(f"/api/structure/{sid}").get_json()
chk(next(n for n in s2["nodes"] if n["id"] == n3["id"])["x"] == -20, "node move persists")
chk(len(s2["links"]) == 1 and s2["links"][0]["label"] == "build", "nodes connect with a labelled line")

# group the nodes into AXES: energy (3,4) × mood (techno stands in) — exports
# then cross them, so "energy 4" breaks down by mood on the player
c.patch(f"/api/structure/node/{n3['id']}", json={"group_name": "energy"})
c.patch(f"/api/structure/node/{n4['id']}", json={"group_name": "energy"})
c.patch(f"/api/structure/node/{ng['id']}", json={"group_name": "mood"})
sg = c.get(f"/api/structure/{sid}").get_json()
chk(all(n["group_name"] in ("energy", "mood") for n in sg["nodes"]),
    "nodes carry their axis (group_name)")

# export the structure to a stick: union of records, playlist per node
STICK = os.path.join(TMP, "stick"); os.makedirs(STICK)
sc = c.get("/api/usb/scopes").get_json()
chk(any(x["name"] == "club system" and x["n"] == 2 for x in sc.get("structures", [])),
    "structure appears in the export scopes with its union count")
pv = c.post("/api/usb/preview", json={"volume": STICK, "scope_type": "structure", "scope_id": sid}).get_json()
chk(pv["new"] == 2, "preview sees the union (track 2 counted once)")
app._run_usb_export_scoped(STICK, "structure", sid, False, False, True)
root = ET.parse(os.path.join(STICK, "musicroom_library.xml")).getroot()
pls = {n.get("Name"): [t.get("Key") for t in n.iter("TRACK")]
       for n in root.iter("NODE") if n.get("Type") == "1"}
chk({"club system · energy 3", "club system · energy 4", "club system · techno"} <= set(pls),
    f"stick XML carries one playlist per node ({sorted(pls)})")
chk(pls["club system · techno"] == ["2"], "node playlists hold the right records")
# the axis crossing: track 2 = energy 4 + techno → "energy 4 · techno" exists;
# energy 3 (track 1, no mood) crosses with nothing
chk(pls.get("club system · energy 4 · techno") == ["2"]
    and "club system · energy 3 · techno" not in pls,
    "axes cross: standing at energy 4 the moods sit beside each other")
e = sqlite3.connect(os.path.join(STICK, "Engine Library", "Database2", "m.db"))
epl = sorted(r[0] for r in e.execute("SELECT title FROM PlaylistEntity"))
n_tracks = e.execute("SELECT COUNT(*) FROM Track").fetchone()[0]
e.close()
chk(len(epl) == 4 and n_tracks == 2, "Engine db: 3 node + 1 crossing playlists over 2 deduped files")

# a structure can carry the filter set it was born from (saved view)
fr = c.post("/api/structures", json={"name": "filtered view",
    "filters": {"tags": ["techno"], "bpmMin": 120, "bpmMax": 130}}).get_json()
fs = c.get(f"/api/structure/{fr['id']}").get_json()
chk(fs["structure"]["filters"]["bpmMin"] == 120 and fs["structure"]["filters"]["tags"] == ["techno"],
    "structure carries its bound filters")
c.patch(f"/api/structure/{fr['id']}", json={"filters": None})
fs2 = c.get(f"/api/structure/{fr['id']}").get_json()
chk(fs2["structure"]["filters"] is None, "bound filters can be forgotten")
c.delete(f"/api/structure/{fr['id']}")

# deleting a node cleans its links; deleting the structure cascades
c.delete(f"/api/structure/node/{n4['id']}")
s3 = c.get(f"/api/structure/{sid}").get_json()
chk(len(s3["nodes"]) == 2 and not s3["links"], "removing a node removes its lines")
c.delete(f"/api/structure/{sid}")
chk(c.get(f"/api/structure/{sid}").status_code == 404, "structure deletes cleanly")

print("")
print("  ALL PASS" if not fails else f"  {len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
