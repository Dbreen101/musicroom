"""Proves the user-curated sample lineage: MusicBrainz SUGGESTS, the user
CONFIRMS one (with a marked timestamp), DISMISSES another (it stops suggesting),
ADDS their own, and the reverse "sampled in" derives automatically. The MB call
is stubbed so the test is deterministic (no network). Temp DB + Flask client.

Run:  /opt/anaconda3/bin/python test_track_samples.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_tsamples_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")
db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'Track A','Sampler',0)")
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(2,'Funky Drummer','James Brown',0)")
db.commit(); db.close()

import app, sample_lookup
# Stub: MusicBrainz suggests two samples for Track A only.
def fake_find(artist, title, isrc=None):
    if title == "Track A":
        return {"mbid": "a-mbid", "sampled_in": [], "samples": [
            {"mbid": "jb1", "title": "Funky Drummer", "artist": "James Brown", "partial": True},
            {"mbid": "amen", "title": "Amen, Brother", "artist": "The Winstons", "partial": False},
        ]}
    return {"mbid": None, "samples": [], "sampled_in": []}
sample_lookup.find_samples = fake_find
c = app.app.test_client()

def get_A(): return c.get("/api/track/1/samples").get_json()

d = get_A()
chk(len(d["samples"]) == 2 and all(not s["confirmed"] for s in d["samples"]), "MB suggests 2 samples (unconfirmed)")

# confirm jb1 with a marked timestamp (47s here, sampled from 0:32 of the original)
c.post("/api/track/1/samples", json={"source_mbid": "jb1", "source_title": "Funky Drummer",
       "source_artist": "James Brown", "timestamp_sec": 47, "source_timestamp_sec": 32})
d = get_A()
conf = [s for s in d["samples"] if s["confirmed"]]
chk(len(conf) == 1 and conf[0]["timestamp_sec"] == 47 and conf[0]["source_timestamp_sec"] == 32,
    "confirmed sample stored with the marked timestamp")
chk(not any(s.get("mbid") == "jb1" and not s["confirmed"] for s in d["samples"]),
    "the confirmed one is no longer suggested")
chk(any(s.get("mbid") == "amen" and not s["confirmed"] for s in d["samples"]),
    "the other suggestion (amen) still shows")

# dismiss the amen suggestion → it stops appearing
c.post("/api/track/1/samples/dismiss", json={"source_mbid": "amen"})
d = get_A()
chk(not any(s.get("mbid") == "amen" for s in d["samples"]), "dismissed suggestion no longer appears")
chk(len([s for s in d["samples"] if s["confirmed"]]) == 1, "only the confirmed sample remains")

# add own: Track A samples local Track B (Funky Drummer, id 2) at 1:30
c.post("/api/track/1/samples", json={"source_track_id": 2, "timestamp_sec": 90})
d = get_A()
own = [s for s in d["samples"] if s["confirmed"] and s.get("local_track_id") == 2]
chk(own and own[0]["title"] == "Funky Drummer", "user-added sample links to the local original")

# reverse: Track B's panel shows it is sampled in Track A
b = c.get("/api/track/2/samples").get_json()
chk(any(x.get("local_track_id") == 1 and x["confirmed"] for x in b["sampled_in"]),
    "'sampled in' derives automatically on the original track")

# delete the user-added one
sid = own[0]["id"]
c.delete(f"/api/track/sample/{sid}")
chk(len([s for s in get_A()["samples"] if s["confirmed"]]) == 1, "a sample can be removed")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — MB suggests; user confirms (w/ timestamp) / dismisses / adds; reverse derives"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
