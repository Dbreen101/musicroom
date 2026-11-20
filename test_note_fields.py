"""Proves custom fields on moments (the 'model anything' lever): a moment can
carry any user-invented key:value pairs, they come back with the note, and can
be removed. Temp DB via Flask test client.

Run:  /opt/anaconda3/bin/python test_note_fields.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_fields_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'A','X',0)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted,duration_sec) VALUES(1,1,'/a.mp3',1,0,200)")
db.execute("INSERT INTO listening_sessions(id,track_id,started_at) VALUES(1,1,datetime('now'))")
db.execute("INSERT INTO listening_notes(id,session_id,track_id,timestamp_sec,note_text,note_category,is_voice) VALUES(1,1,1,47,'a lick','sound',0)")
db.commit(); db.close()

import app
c = app.app.test_client()

# add two custom fields the user invented (including a multi-value field)
c.post("/api/note/1/property", json={"name": "instrument", "value": "guitar"})
c.post("/api/note/1/property", json={"name": "instrument", "value": "bass"})
r = c.post("/api/note/1/property", json={"name": "decade", "value": "70s"}).get_json()
chk(r.get("ok") and r.get("name") == "decade", "custom field added")

# they come back attached to the moment
notes = c.get("/api/listen/notes").get_json()
props = notes[0]["properties"]
chk(len(props) == 3, f"all 3 fields returned with the moment (got {len(props)})")
chk(sum(1 for p in props if p["name"] == "instrument") == 2, "a field can hold multiple values (instrument: guitar AND bass)")

# distinct field names for the filter / autocomplete
names = c.get("/api/note-property-names").get_json()
chk(set(names) == {"instrument", "decade"}, "distinct field names listed for the filter")

# remove one value
pid = next(p["id"] for p in props if p["value"] == "bass")
c.delete(f"/api/note/property/{pid}")
notes2 = c.get("/api/listen/notes").get_json()
chk(len(notes2[0]["properties"]) == 2, "a field value can be removed")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — moments carry your own custom fields (model anything)"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
