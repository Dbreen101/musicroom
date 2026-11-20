"""A note_link can carry a note on *why* it was made: set on create, editable
via PATCH, cleared by PATCH with empty. Temp DB.

Run:  /opt/anaconda3/bin/python test_link_label.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_linklabel_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")
db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'A','x',0)")
db.execute("INSERT INTO listening_sessions(id,track_id,started_at) VALUES(1,1,datetime('now'))")
for nid, ts in ((1, 10), (2, 20)):
    db.execute("INSERT INTO listening_notes(id,session_id,track_id,timestamp_sec,note_text) VALUES(?,1,1,?,?)",
               (nid, ts, f"note {nid}"))
db.commit(); db.close()

import app
c = app.app.test_client()

def link_for(nid):
    rows = c.get(f"/api/note-links?note_id={nid}").get_json()
    return rows[0] if rows else None

# create a link WITH a reason
c.post("/api/note-links", json={"from_note_id": 1, "to_note_id": 2, "label": "same chord under the vocal"})
l = link_for(1)
chk(l and l["label"] == "same chord under the vocal", "link created with a why-note")
lid = l["id"]

# edit the reason
c.patch(f"/api/note-link/{lid}", json={"label": "actually: reused breakbeat"})
chk(link_for(1)["label"] == "actually: reused breakbeat", "why-note editable via PATCH")

# clear it
c.patch(f"/api/note-link/{lid}", json={"label": ""})
chk(link_for(1).get("label") in (None, ""), "why-note can be cleared")

# the link itself survives a label edit (still connects 1↔2)
l = link_for(1)
chk(l and l["from_note_id"] == 1 and l["to_note_id"] == 2, "link intact after label edits")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — link carries an editable note on why it was made"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
