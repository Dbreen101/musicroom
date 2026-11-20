"""An album becomes a Studio place: importing 'Album 1' creates a place named
Album 1 (is_studio_project), its tracks join it AND The Well, and /api/studio/
albums lists it. Re-import is idempotent (no duplicate album place).

Run:  /opt/anaconda3/bin/python test_studio_albums.py
"""
import os, sys, tempfile, subprocess, sqlite3

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_studioalb_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

def put(*parts):
    p = os.path.join(TMP, *parts); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(b"x"); return p

put("Album 1", "Track 1", "Track 1.als"); put("Album 1", "Track 1", "Track 1.wav")
put("Album 1", "Track 2", "Track 2.als"); put("Album 1", "Track 2", "Track 2.wav")
ALBUM = os.path.join(TMP, "Album 1")

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
import app
c = app.app.test_client()
r = c.post("/api/studio/import", json={"path": ALBUM}).get_json()
chk(r.get("tracks_created") == 2, "imported 2 tracks")
chk(r.get("album_place_id"), "an album place was created")

db = sqlite3.connect(os.path.join(TMP, "library.db")); db.row_factory = sqlite3.Row
ap = db.execute("SELECT * FROM places WHERE name='Album 1'").fetchone()
chk(ap and ap["is_studio_project"] == 1, "place 'Album 1' marked is_studio_project")
n_in_album = db.execute("SELECT COUNT(*) FROM place_tracks WHERE place_id=?", (ap["id"],)).fetchone()[0]
chk(n_in_album == 2, "both tracks added to the album place")
well = db.execute("SELECT id FROM places WHERE is_well=1").fetchone()
n_in_well = db.execute("""SELECT COUNT(*) FROM place_tracks pt JOIN tracks t ON t.id=pt.track_id
                          WHERE pt.place_id=? AND t.is_own_work=1""", (well["id"],)).fetchone()[0]
chk(n_in_well == 2, "the same tracks also live in The Well")
db.close()

alb = c.get("/api/studio/albums").get_json()["albums"]
chk(len(alb) == 1 and alb[0]["name"] == "Album 1" and alb[0]["track_count"] == 2,
    "/api/studio/albums lists the album with its track count")

# re-import → no duplicate album place, no duplicate tracks
c.post("/api/studio/import", json={"path": ALBUM})
db = sqlite3.connect(os.path.join(TMP, "library.db"))
chk(db.execute("SELECT COUNT(*) FROM places WHERE name='Album 1'").fetchone()[0] == 1,
    "re-import does not duplicate the album place")
db.close()

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — an album is a Studio place; tracks live in it and The Well"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
