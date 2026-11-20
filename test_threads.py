"""Proves the deep-listening research substrate: captured moments can be
gathered into THREADS (ordered lines of enquiry), filtered by thread in the
notes browser, fetched as a playable sequence, and connected with free LINKS
(the mind-map primitive). Temp DB via Flask test client.

Run:  /opt/anaconda3/bin/python test_threads.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_threads_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

# seed: two tracks (different years), a listening session, two moments
db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,year,is_deleted) VALUES(1,'A','X',1978,0)")
db.execute("INSERT INTO tracks(id,title,artist_name,year,is_deleted) VALUES(2,'B','Y',2009,0)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted,duration_sec) VALUES(1,1,'/a.mp3',1,0,200)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted,duration_sec) VALUES(2,2,'/b.mp3',1,0,200)")
db.execute("INSERT INTO listening_sessions(id,track_id,started_at) VALUES(1,1,datetime('now'))")
db.execute("INSERT INTO listening_sessions(id,track_id,started_at) VALUES(2,2,datetime('now'))")
db.execute("INSERT INTO listening_notes(id,session_id,track_id,timestamp_sec,note_text,note_category,is_voice) VALUES(1,1,1,47,'guitar lick','sound',0)")
db.execute("INSERT INTO listening_notes(id,session_id,track_id,timestamp_sec,note_text,note_category,is_voice) VALUES(2,2,2,12,'same tone','sound',0)")
db.commit(); db.close()

import app
c = app.app.test_client()

# create a thread
r = c.post("/api/threads", json={"name": "highlife guitar", "colour": "#a8822c"}).get_json()
tid = r.get("id")
chk(r.get("ok") and tid, "thread created")

# add both moments (note 2 first, then 1 — order should follow insertion position)
c.post(f"/api/thread/{tid}/moments", json={"note_id": 2})
c.post(f"/api/thread/{tid}/moments", json={"note_id": 1})

threads = c.get("/api/threads").get_json()
chk(len(threads) == 1 and threads[0]["moment_count"] == 2, "thread lists with 2 moments")

# the thread as a playable sequence (carries year, file_id for playback)
th = c.get(f"/api/thread/{tid}").get_json()
ms = th["moments"]
chk(len(ms) == 2 and all(m.get("file_id") for m in ms), "thread returns its moments, each playable")
chk(all("year" in m for m in ms), "moments carry musical context (year) for timeline/map lenses")

# reorder → note 1 first
c.post(f"/api/thread/{tid}/reorder", json={"note_ids": [1, 2]})
th2 = c.get(f"/api/thread/{tid}").get_json()
chk(th2["moments"][0]["id"] == 1, "thread moments reorder")

# the notes browser filters by thread
notes = c.get(f"/api/listen/notes?thread_id={tid}").get_json()
chk(len(notes) == 2 and all(any(t["id"] == tid for t in n["threads"]) for n in notes),
    "notes browser filters by thread + each note shows its threads")

# remove a moment
c.delete(f"/api/thread/{tid}/moments/1")
chk(c.get("/api/threads").get_json()[0]["moment_count"] == 1, "moment removed from thread")

# free link between two moments (mind-map primitive)
c.post("/api/note-links", json={"from_note_id": 1, "to_note_id": 2, "label": "echoes"})
links = c.get("/api/note-links?note_id=1").get_json()
chk(len(links) == 1 and links[0]["label"] == "echoes", "a free link connects two moments (mind-map)")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — moments → threads (ordered, playable, filterable) + free links"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
