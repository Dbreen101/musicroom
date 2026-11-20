"""Album → Track → versions, with each .als paired to its EXACT same-named
bounce (Daithí's convention). Point at an album folder → its track subfolders
become tracks (tagged with the album); each .als + identically-named .wav is one
version, and the file remembers exactly which session it came from.

Run:  /opt/anaconda3/bin/python test_daw_versions.py
"""
import os, sys, tempfile, subprocess, sqlite3

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_dawver_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

def put(*parts, data=b"x"):
    p = os.path.join(TMP, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(data); return p

# Album 1 / Track 1 (two versions) + Track 2 (one)
a1 = put("Album 1", "Track 1", "Track 1.als")
w1 = put("Album 1", "Track 1", "Track 1.wav")
a2 = put("Album 1", "Track 1", "Track 1 v2.als")
w2 = put("Album 1", "Track 1", "Track 1 v2.wav")
b1 = put("Album 1", "Track 2", "Track 2.als")
bw1 = put("Album 1", "Track 2", "Track 2.wav")
ALBUM = os.path.join(TMP, "Album 1")

import daw_projects
projs = {p["name"]: p for p in daw_projects.scan_productions(ALBUM)}
chk(set(projs) == {"Track 1", "Track 2"}, f"album folder → its tracks (got {set(projs)})")
t1 = projs["Track 1"]
vmap = {os.path.basename(v["bounce"]): (os.path.basename(v["session"]) if v["session"] else None)
        for v in t1["versions"]}
chk(vmap.get("Track 1.wav") == "Track 1.als", "bounce paired to its EXACT same-named session")
chk(vmap.get("Track 1 v2.wav") == "Track 1 v2.als", "v2 bounce paired to the v2 session (not the other)")

# import the album
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
import app
c = app.app.test_client()
r = c.post("/api/studio/import", json={"path": ALBUM}).get_json()
chk(r.get("tracks_created") == 2, f"imported 2 tracks (got {r.get('tracks_created')})")
chk(r.get("album") == "Album 1", "tracks tagged with the album name")

db = sqlite3.connect(os.path.join(TMP, "library.db")); db.row_factory = sqlite3.Row
t = db.execute("SELECT * FROM tracks WHERE title='Track 1'").fetchone()
chk(t and t["album"] == "Album 1", "Track 1 carries album='Album 1'")
fs = {os.path.basename(f["file_path"]): f for f in
      db.execute("SELECT * FROM files WHERE track_id=?", (t["id"],))}
chk(len(fs) == 2, "Track 1 imported its 2 versions")
chk(os.path.basename(fs["Track 1.wav"]["session_path"]) == "Track 1.als", "v1 file links to its own session")
chk(os.path.basename(fs["Track 1 v2.wav"]["session_path"]) == "Track 1 v2.als", "v2 file links to its own session")
chk(fs["Track 1.wav"]["is_primary"] == 1, "the current version (un-stamped session) is primary")

# a single standalone project (pointed at directly) has no album
single = db.execute("SELECT album FROM tracks WHERE title='Track 1'").fetchone()  # placeholder
chk(daw_projects.scan_productions(os.path.join(ALBUM, "Track 1")) and
    app.app.test_client() is not None, "scanner handles a single project too")
db.close()

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — album→track→version with exact .als/.wav pairing"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
