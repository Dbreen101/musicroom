"""Proves the optional 'also add to places' import feature: after an import,
the run's NEW tracks (from the import journal) can be added to chosen places,
non-destructively (The Well membership is untouched; nothing about the import
changes). Temp DB via Flask test client.

Run:  /opt/anaconda3/bin/python test_import_to_places.py
"""
import os, sys, sqlite3, tempfile, subprocess, json

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_imp2places_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

db = sqlite3.connect(DB)
if not db.execute("SELECT 1 FROM places WHERE is_well=1").fetchone():
    db.execute("INSERT INTO places(name,is_well) VALUES('The Well',1)")
db.execute("INSERT INTO places(id,name,is_well) VALUES(2,'Sunset Beach',0)")
db.execute("INSERT INTO places(id,name,is_well) VALUES(3,'3am Kitchen',0)")
# two freshly-imported tracks + one older one that should NOT be touched
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(10,'New A','X',0)")
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(11,'New B','Y',0)")
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(99,'Old',  'Z',0)")
db.commit()
# write an import journal naming the new tracks, point the setting at it
journal = os.path.join(TMP, "journal.json")
json.dump({"at": "now", "new_track_ids": [10, 11], "relinked": []}, open(journal, "w"))
db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('last_import_journal',?)", (journal,))
db.commit(); db.close()

import app
c = app.app.test_client()

# add the import's new tracks to Sunset Beach + 3am Kitchen
r = c.post("/api/import/add-to-places", json={"place_ids": [2, 3]}).get_json()
chk(r.get("ok") and r.get("added") == 2 and r.get("places") == 2, f"added 2 new tracks to 2 places (got {r})")

db = sqlite3.connect(DB)
def members(pid): return sorted(x[0] for x in db.execute("SELECT track_id FROM place_tracks WHERE place_id=?", (pid,)))
chk(members(2) == [10, 11], f"Sunset Beach got exactly the 2 new tracks (got {members(2)})")
chk(members(3) == [10, 11], f"3am Kitchen got exactly the 2 new tracks (got {members(3)})")
chk(99 not in members(2) and 99 not in members(3), "the older track was NOT added")
db.close()

# empty selection is a clean no-op (default behaviour — unticked)
r2 = c.post("/api/import/add-to-places", json={"place_ids": []}).get_json()
chk(r2.get("ok") and r2.get("added") == 0, "no places chosen → no-op (default, not required)")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — imported tracks optionally join chosen places, non-destructively"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
