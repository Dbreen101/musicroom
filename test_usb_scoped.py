"""Proves the PRACTICE-STICK road: a place or pile exports to a USB volume —
files into "Music Room/<name>/", a manifest beside them, the stick's
rekordbox XML and Engine DJ database rebuilt from every manifest aboard.
Re-exports preview what's new/kept/dropped, and dropped tracks leave the
stick only when asked (ask-each-time). A plain directory stands in for the
stick. Run:  venv/bin/python test_usb_scoped.py
"""
import os, sys, sqlite3, tempfile, subprocess, json, xml.etree.ElementTree as ET

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_usb_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

# three real (tiny) audio files on disk so copies actually happen
AUD = os.path.join(TMP, "audio"); os.makedirs(AUD)
paths = []
for i in (1, 2, 3):
    p = os.path.join(AUD, f"t{i}.mp3")
    with open(p, "wb") as f: f.write(b"ID3" + bytes(100 * i))
    paths.append(p)

db = sqlite3.connect(DB)
for i in (1, 2, 3):
    db.execute("INSERT INTO tracks(id,title,artist_name,year,is_deleted) VALUES(?,?,?,?,0)",
               (i, f"Track {i}", f"Artist {i}", 2000 + i))
    db.execute("""INSERT INTO files(id,track_id,file_path,file_format,is_primary,is_deleted,
                  duration_sec,file_size_mb,bpm,key_note,key_scale)
                  VALUES(?,?,?,'mp3',1,0,180,0.001,128,'A','minor')""", (i, i, paths[i-1]))
db.execute("INSERT INTO places(id,name,is_well) VALUES(2,'Sunset Beach',0)")
db.execute("INSERT INTO place_tracks(place_id,track_id) VALUES(2,1)")
db.execute("INSERT INTO place_tracks(place_id,track_id) VALUES(2,2)")
db.execute("INSERT INTO room_piles(id,room_place_id,name) VALUES(1,1,'practice run')")
db.execute("INSERT INTO room_pile_tracks(pile_id,track_id) VALUES(1,2)")
db.execute("INSERT INTO room_pile_tracks(pile_id,track_id) VALUES(1,3)")
db.commit(); db.close()

import app
c = app.app.test_client()
STICK = os.path.join(TMP, "stick"); os.makedirs(STICK)

# scopes are listed for the picker
sc = c.get("/api/usb/scopes").get_json()
chk(any(p["name"] == "Sunset Beach" for p in sc["places"])
    and any(p["name"] == "practice run" and p["n"] == 2 for p in sc["piles"]),
    "scopes list places and piles with counts")

# preview before anything is aboard
pv = c.post("/api/usb/preview", json={"volume": STICK, "scope_type": "pile", "scope_id": 1}).get_json()
chk(pv["new"] == 2 and pv["kept"] == 0 and pv["dropped"] == 0 and pv["fits"],
    "preview: a fresh stick takes the whole pile as new")

# export the pile (run the worker synchronously)
app._run_usb_export_scoped(STICK, "pile", 1, False, False, True)
sdir = os.path.join(STICK, "Music Room", "practice run")
copied = sorted(f for f in os.listdir(sdir) if not f.startswith("."))
chk(len(copied) == 2, f"pile's two files landed in Music Room/practice run ({copied})")
mf = json.load(open(os.path.join(sdir, ".musicroom.json")))
chk(mf["scope_type"] == "pile" and len(mf["tracks"]) == 2, "manifest records the export")

xmlp = os.path.join(STICK, "musicroom_library.xml")
root = ET.parse(xmlp).getroot()
pl_names = [n.get("Name") for n in root.iter("NODE") if n.get("Type") == "1"]
locs = [t.get("Location") for t in root.find("COLLECTION").iter("TRACK")]
chk("practice run" in pl_names, "stick XML carries the pile as a playlist")
chk(all("stick" in (l or "") for l in locs), "stick XML Locations point AT the stick")

edb = os.path.join(STICK, "Engine Library", "Database2", "m.db")
chk(os.path.isfile(edb), "Engine DJ database written on the stick")
e = sqlite3.connect(edb)
ep = [r[0] for r in e.execute("SELECT path FROM Track")]
epl = [r[0] for r in e.execute("SELECT title FROM PlaylistEntity")]
n_links = e.execute("SELECT COUNT(*) FROM PlaylistTrackList").fetchone()[0]
e.close()
chk(all(p.startswith("../Music Room/practice run/") for p in ep),
    "Engine paths are stick-relative (../Music Room/…)")
chk("practice run" in epl and n_links == 2, "Engine playlist holds both tracks")

# re-export is calm: nothing new
pv2 = c.post("/api/usb/preview", json={"volume": STICK, "scope_type": "pile", "scope_id": 1}).get_json()
chk(pv2["new"] == 0 and pv2["kept"] == 2, "second preview: everything already aboard")

# drop track 3 from the pile → preview shows it; removal only when asked
db = sqlite3.connect(DB)
db.execute("DELETE FROM room_pile_tracks WHERE pile_id=1 AND track_id=3")
db.commit(); db.close()
pv3 = c.post("/api/usb/preview", json={"volume": STICK, "scope_type": "pile", "scope_id": 1}).get_json()
chk(pv3["dropped"] == 1 and pv3["dropped_names"], "preview names the dropped track")

app._run_usb_export_scoped(STICK, "pile", 1, False, False, True)   # add-only: keep it
still = [f for f in os.listdir(sdir) if f.endswith(".mp3")]
chk(len(still) == 2, "add-only export leaves the dropped file on the stick")

app._run_usb_export_scoped(STICK, "pile", 1, False, True, True)    # mirror: take it off
left = [f for f in os.listdir(sdir) if f.endswith(".mp3")]
chk(len(left) == 1 and "Artist 2" in left[0], "mirror export removes the dropped file")

# a second scope joins the same stick — both playlists in one catalogue
app._run_usb_export_scoped(STICK, "place", 2, False, False, True)
root2 = ET.parse(xmlp).getroot()
pl2 = [n.get("Name") for n in root2.iter("NODE") if n.get("Type") == "1"]
coll_n = len(list(ET.parse(xmlp).getroot().find("COLLECTION")))
chk("practice run" in pl2 and "Sunset Beach" in pl2, "two scopes = two playlists on one stick")
chk(coll_n == 2, f"collection deduped across scopes (track 2 shared; {coll_n} entries)")
e = sqlite3.connect(edb)
epl2 = [r[0] for r in e.execute("SELECT title FROM PlaylistEntity ORDER BY title")]
e.close()
chk(epl2 == ["Sunset Beach", "practice run"], "Engine db carries both playlists")

print("")
print("  ALL PASS" if not fails else f"  {len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
