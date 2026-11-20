"""Two-level notes: a moment's brief note_text (quick capture) plus a long-form
detail_text (the "page beneath"); threads carry a detail_text too. Proves both
persist via PATCH and come back on the GETs the workspace reads. Temp DB.

Run:  /opt/anaconda3/bin/python test_detail_notes.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_detail_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")
db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'Track A','Artist',0)")
db.execute("INSERT INTO listening_sessions(id,track_id,started_at) VALUES(1,1,datetime('now'))")
db.execute("INSERT INTO listening_notes(id,session_id,track_id,timestamp_sec,note_text,note_category,is_voice) "
           "VALUES(7,1,1,16,'the guitar opens up here','melody',0)")
db.commit(); db.close()

import app
c = app.app.test_client()

# columns exist
cols_n = [r[1] for r in sqlite3.connect(DB).execute("PRAGMA table_info(listening_notes)")]
cols_t = [r[1] for r in sqlite3.connect(DB).execute("PRAGMA table_info(threads)")]
chk("detail_text" in cols_n, "listening_notes has detail_text")
chk("detail_text" in cols_t, "threads has detail_text")

# brief note is intact; no detail yet
note = next(n for n in c.get("/api/listen/notes").get_json() if n["id"] == 7)
chk(note["note_text"] == "the guitar opens up here", "brief note (note_text) preserved")
chk(not note.get("detail_text"), "no detail_text yet")

# write a long-form detail on the moment (brief note untouched)
long = "Longer thoughts.\n\nThe way the chord voicing sits under the vocal — like Durutti Column. Compare with 0:42."
r = c.patch("/api/listen/note/7", json={"detail_text": long})
chk(r.status_code == 200, "PATCH detail_text ok")
note = next(n for n in c.get("/api/listen/notes").get_json() if n["id"] == 7)
chk(note["detail_text"] == long, "detail_text persisted + returned by /api/listen/notes")
chk(note["note_text"] == "the guitar opens up here", "brief note still intact after detail edit")

# editing the brief note doesn't wipe the detail
c.patch("/api/listen/note/7", json={"note_text": "edited brief"})
note = next(n for n in c.get("/api/listen/notes").get_json() if n["id"] == 7)
chk(note["detail_text"] == long and note["note_text"] == "edited brief", "brief + detail are independent")

# clearing the detail
c.patch("/api/listen/note/7", json={"detail_text": ""})
note = next(n for n in c.get("/api/listen/notes").get_json() if n["id"] == 7)
chk(not note.get("detail_text"), "detail_text can be cleared")

# threads carry a detail_text too
tid = c.post("/api/threads", json={"name": "highlife guitar tone"}).get_json()["id"]
c.patch(f"/api/thread/{tid}", json={"detail_text": "A line through the West-African guitar lineage…"})
th = c.get(f"/api/thread/{tid}").get_json()["thread"]
chk(th.get("detail_text") == "A line through the West-African guitar lineage…", "thread detail_text persists + returns on GET /api/thread/<id>")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — quick note + detail page persist independently on moments and threads"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
