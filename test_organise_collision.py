"""Proves the organiser never STRANDS a file when its destination is already
claimed by another (dangling duplicate) DB row — the 2026-06-02 bug that left 32
files moved to the Library with their rows still pointing at the empty staging
folder. On a DB UNIQUE collision the move is now rolled back so the file stays
where a valid row points at it.

Run:  /opt/anaconda3/bin/python test_organise_collision.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_orgcol_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")
import organiser

LIB = os.path.join(TMP, "Library")
STAGE = os.path.join(TMP, "staging"); os.makedirs(STAGE, exist_ok=True)
src = os.path.join(STAGE, "Artist - Song.flac")
open(src, "w").write("AUDIO")

rec = {"artist_name": "Artist", "album": "Album", "title": "Song",
       "file_format": "flac", "track_number": None, "file_path": src}
dest = organiser.build_destination_path(LIB, rec)   # where file1 would land

db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,album,is_deleted) VALUES(1,'Song','Artist','Album',0)")
db.execute("INSERT INTO tracks(id,title,artist_name,album,is_deleted) VALUES(2,'Song','Artist','Album',0)")
# file 1 = the real file in staging, to be organised
db.execute("INSERT INTO files(id,track_id,file_path,file_format,is_primary,is_deleted) VALUES(1,1,?, 'flac',1,0)", (src,))
# file 2 = a DANGLING duplicate row already claiming the destination path (file missing)
db.execute("INSERT INTO files(id,track_id,file_path,file_format,is_primary,is_deleted) VALUES(2,2,?, 'flac',1,0)", (dest,))
db.commit(); db.close()

summary = organiser.organise_library(LIB, mode="move", only_under=STAGE)
print("summary:", summary)

# the real file must NOT be stranded: it stays at src, and file 1's row still points there
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
p1 = db.execute("SELECT file_path FROM files WHERE id=1").fetchone()["file_path"]
db.close()
chk(os.path.isfile(src), "the file was NOT stranded — it stays at the source on a DB collision")
chk(os.path.isfile(p1), "file 1's row points at an existing file (track still plays)")
chk(os.path.normpath(p1) == os.path.normpath(src), "file 1's row was rolled back to the source, not left dangling")
chk(not os.path.isfile(dest), "no orphan file left at the collided destination")
chk(summary.get("collided") == 1, f"collision counted (collided={summary.get('collided')})")
chk(summary.get("done") == 0 and summary.get("failed") == 0, "nothing falsely reported as moved/failed")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — organiser never strands a file on a DB-path collision"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
