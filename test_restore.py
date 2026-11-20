"""Proves /api/removed/restore: un-deletes the track, moves the parked file OUT
of the Removed folder into Library/Restored, relinks it, re-adds to The Well.
Temp DB + a real audio file copy. Live library untouched.

Run: /opt/anaconda3/bin/python test_restore.py
"""
import os, sys, sqlite3, tempfile, shutil, subprocess
PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_restore_test_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

rdb = sqlite3.connect(f"file:{PROJ}/library.db?mode=ro", uri=True); rdb.row_factory = sqlite3.Row
real = None
for r in rdb.execute("SELECT file_path FROM files WHERE is_primary=1 AND is_deleted=0"):
    p = r["file_path"]
    if p and os.path.isfile(p) and p.lower().endswith((".flac", ".mp3")) and os.path.getsize(p) < 60_000_000:
        real = p; break
rdb.close()
assert real, "no real audio file to test with"

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")
LIB = os.path.join(TMP, "Library"); os.makedirs(LIB, exist_ok=True)
REMOVED = os.path.join(TMP, "Removed from Music Room"); os.makedirs(REMOVED, exist_ok=True)
ext = os.path.splitext(real)[1]
parked = os.path.join(REMOVED, f"7_song{ext}"); shutil.copy2(real, parked)

db = sqlite3.connect(DB)
if not db.execute("SELECT 1 FROM places WHERE is_well=1").fetchone():
    db.execute("INSERT INTO places(name,is_well) VALUES('The Well',1)")
db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('library_dest',?)", (LIB,))
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(7,'Draft','',1)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted) VALUES(1,7,?,1,1)",
           (os.path.join(TMP, "OLD", "song" + ext),))
db.commit(); db.close()

import app
c = app.app.test_client()
before = c.get("/api/removed").get_json()
res = c.post("/api/removed/restore", json={"track_ids": [7]}).get_json()
after = c.get("/api/removed").get_json()

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
t = db.execute("SELECT is_deleted FROM tracks WHERE id=7").fetchone()
f = db.execute("SELECT file_path,is_deleted FROM files WHERE track_id=7").fetchone()
inwell = db.execute("SELECT 1 FROM place_tracks pt JOIN places p ON p.id=pt.place_id AND p.is_well=1 WHERE pt.track_id=7").fetchone()
db.close()

chk(any(x["track_id"] == 7 for x in before["removed"]), "track 7 listed as removed before")
chk(res.get("count") == 1, "restore reported 1")
chk(t and t["is_deleted"] == 0, "track un-deleted")
chk(f and f["is_deleted"] == 0 and os.path.isfile(f["file_path"]), "file relinked + exists on disk")
chk(f and "Removed from Music Room" not in f["file_path"], "file moved OUT of the Removed folder")
chk(not os.path.isfile(parked), "parked copy gone from the Removed folder")
chk(bool(inwell), "back in The Well")
chk(not any(x["track_id"] == 7 for x in after["removed"]), "no longer listed as removed")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — restore brings a removed track back cleanly"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
