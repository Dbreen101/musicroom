"""Proves Undo last import: the new tracks an import added get RETIRED
(is_deleted=1, recoverable — never hard-deleted) and any relinked file paths are
restored, and it's one-shot. Temp DB via Flask test client.

Run:  /opt/anaconda3/bin/python test_import_undo.py
"""
import os, sys, sqlite3, tempfile, subprocess, json

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_undo_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

db = sqlite3.connect(DB)
# track 1 = a NEW track the import added; track 2 = a track whose file was relinked
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'New One','Imported',0)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted) VALUES(1,1,'/lib/new.mp3',1,0)")
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(2,'Relinked','Recovered',0)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted) VALUES(2,2,'/found/copy.mp3',1,0)")
db.commit(); db.close()

# write the journal exactly as run_import would, and point the setting at it
jdir = os.path.join(TMP, "import_journals"); os.makedirs(jdir, exist_ok=True)
jpath = os.path.join(jdir, "20260603-120000.json")
json.dump({"at": "20260603-120000", "scan_path": "/some/folder",
           "new_track_ids": [1],
           "relinked": [{"file_id": 2, "old_path": "/was/missing.mp3"}],
           "count_new": 1, "count_relinked": 1, "undone": False}, open(jpath, "w"))
db = sqlite3.connect(DB)
db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('last_import_journal',?)", (jpath,))
db.commit(); db.close()

import app
client = app.app.test_client()

st = client.get("/api/import/undo-status").get_json()
chk(st.get("available") and st.get("count_new") == 1, "undo is offered for the last import")

r = client.post("/api/import/undo").get_json()
chk(r.get("ok") and r.get("retired_tracks") == 1 and r.get("restored_relinks") == 1,
    f"undo retired the new track + restored the relink (got {r})")

db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
t1 = db.execute("SELECT is_deleted FROM tracks WHERE id=1").fetchone()["is_deleted"]
f2 = db.execute("SELECT file_path FROM files WHERE id=2").fetchone()["file_path"]
db.close()
chk(t1 == 1, "the imported track was retired (is_deleted=1, recoverable — not hard-deleted)")
chk(f2 == "/was/missing.mp3", "the relinked file path was restored")

st2 = client.get("/api/import/undo-status").get_json()
chk(not st2.get("available"), "undo is one-shot (nothing left to undo after)")
r2 = client.post("/api/import/undo").get_json()
chk(not r2.get("ok"), "a second undo is refused")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — Undo retires new tracks + restores relinks, reversibly"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
