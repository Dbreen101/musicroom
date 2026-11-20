"""Proves the duplicate-track audit: two tracks that are the same recording are
detected as one group and merged into a single keeper, with the duplicate's
note + place membership re-parented and the duplicate retired (is_deleted=1, not
gone). Temp DB via Flask test client. Never touches the live library.

Run:  /opt/anaconda3/bin/python test_dedupe_merge.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_dedupe_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

# seed: keeper (track 1, has a place membership) + duplicate (track 2, has a note)
db = sqlite3.connect(DB)
if not db.execute("SELECT 1 FROM places WHERE is_well=1").fetchone():
    db.execute("INSERT INTO places(name,is_well) VALUES('The Well',1)")
well = db.execute("SELECT id FROM places WHERE is_well=1").fetchone()[0]
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'Brekete','Gafacci',0)")
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(2,'Brekete','Gafacci',0)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted,duration_sec) VALUES(1,1,'/x/keeper.mp3',1,0,202)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted,duration_sec) VALUES(2,2,'/x/dupe.mp3',1,0,202)")
db.execute("INSERT INTO place_tracks(place_id,track_id) VALUES(?,1)", (well,))
db.execute("INSERT INTO notes(track_id,note_type,note_text) VALUES(2,'general','keep me')")
db.commit(); db.close()

import app
client = app.app.test_client()

g = client.get("/api/tracks/duplicate-groups").get_json()
chk(g["group_count"] == 1, f"one duplicate group detected (got {g['group_count']})")
chk(g["extra_tracks"] == 1, "one extra (duplicate) track")

r = client.post("/api/tracks/dedupe-merge").get_json()
chk(r.get("ok") and r.get("merged") == 1, f"merge applied (merged={r.get('merged')})")

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
actives = [r["id"] for r in db.execute("SELECT id FROM tracks WHERE is_deleted=0")]
retired = db.execute("SELECT COUNT(*) n FROM tracks WHERE is_deleted=1").fetchone()["n"]
keeper = actives[0] if len(actives) == 1 else None
note_owner = db.execute("SELECT track_id FROM notes WHERE note_text='keep me'").fetchone()["track_id"]
place_owner = db.execute("SELECT track_id FROM place_tracks").fetchone()["track_id"]
files_on_keeper = db.execute("SELECT COUNT(*) n FROM files WHERE track_id=? AND is_deleted=0", (keeper,)).fetchone()["n"] if keeper else -1
db.close()
chk(len(actives) == 1, f"exactly one active track remains (got {len(actives)})")
chk(retired == 1, "the duplicate was retired (is_deleted=1, recoverable)")
chk(note_owner == keeper, "the note ended up on the surviving track")
chk(place_owner == keeper, "the place membership ended up on the surviving track")
chk(files_on_keeper == 2, "both files now belong to the keeper (alternate version kept)")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — duplicate tracks merge cleanly, nothing lost"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
