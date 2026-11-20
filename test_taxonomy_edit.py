"""Proves RENAME + MERGE of tags/genres applies to every track and keeps the
graph clean: track_tags/track_genres re-pointed, structure_nodes re-pointed,
a rename-onto-an-existing-name folds into one. Run:
    venv/bin/python test_taxonomy_edit.py
"""
import os, sys, sqlite3, tempfile, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_taxo_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

db = sqlite3.connect(DB)
for i in (1, 2, 3):
    db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(?,?,?,0)", (i, f"T{i}", f"A{i}"))
db.commit(); db.close()

import app
c = app.app.test_client()

# tag track 1 + 2 with 'techo' (typo), track 3 with 'techno'
c.post("/api/track/1/tag", json={"name": "techo"})
c.post("/api/track/2/tag", json={"name": "techo"})
c.post("/api/track/3/tag", json={"name": "techno"})
# a structure node references the 'techo' tag — must survive the rename
st = c.post("/api/structures", json={"name": "S"}).get_json()
node = c.post(f"/api/structure/{st['id']}/nodes", json={"kind": "tag", "name": "techo"}).get_json()

def tag_id(name):
    r = sqlite3.connect(DB).execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    return r[0] if r else None
def names_on(track):
    cn = sqlite3.connect(DB)
    return sorted(x[0] for x in cn.execute(
        "SELECT tg.name FROM track_tags tt JOIN tags tg ON tg.id=tt.tag_id WHERE tt.track_id=?", (track,)))

techo = tag_id("techo")

# 1) plain rename — no collision (deep-houz is brand new)
c.post("/api/track/1/tag", json={"name": "deep-houz"})
dh = tag_id("deep-houz")
r = c.post("/api/taxonomy/rename", json={"kind": "tag", "id": dh, "name": "deep house"}).get_json()
chk(r.get("ok") and not r.get("merged") and r["id"] == dh, "plain rename keeps the same id")
chk(tag_id("deep-houz") is None and "deep house" in names_on(1), "rename shows on the track")

# 2) rename 'techo' -> 'techno' = MERGE into the existing 'techno'
techno = tag_id("techno")
r2 = c.post("/api/taxonomy/rename", json={"kind": "tag", "id": techo, "name": "techno"}).get_json()
chk(r2.get("merged") and r2["id"] == techno, "rename onto an existing name merges into it")
chk(tag_id("techo") is None, "the merged-away tag is gone")
chk("techno" in names_on(1) and "techno" in names_on(2) and "techno" in names_on(3),
    "all three tracks now carry the survivor")
chk(r2["track_count"] == 3, "survivor's track count is the union")

# structure node followed the merge (re-pointed to 'techno', not dangling)
sp = c.get(f"/api/structure/{st['id']}").get_json()
chk(len(sp["nodes"]) == 1 and sp["nodes"][0]["ref_id"] == techno
    and sp["nodes"][0]["n_tracks"] == 3, "structure node re-pointed to the survivor")

# 3) MERGE several into a brand-new name
c.post("/api/track/1/tag", json={"name": "acid"})
c.post("/api/track/2/tag", json={"name": "rave"})
a, rv = tag_id("acid"), tag_id("rave")
r3 = c.post("/api/taxonomy/merge", json={"kind": "tag", "ids": [a, rv], "name": "hard"}).get_json()
chk(r3.get("ok") and tag_id("acid") is None and tag_id("rave") is None, "merged sources removed")
chk("hard" in names_on(1) and "hard" in names_on(2) and r3["track_count"] == 2,
    "both tracks fold into the new 'hard' tag")

# 4) genres rename works the same
c.post("/api/track/1/genre", json={"name": "techhouse"})
gh = sqlite3.connect(DB).execute("SELECT id FROM genres WHERE name='techhouse'").fetchone()[0]
rg = c.post("/api/taxonomy/rename", json={"kind": "genre", "id": gh, "name": "tech house"}).get_json()
gn = sqlite3.connect(DB).execute(
    "SELECT g.name FROM track_genres tg JOIN genres g ON g.id=tg.genre_id WHERE tg.track_id=1").fetchall()
chk(rg.get("ok") and ("tech house",) in gn, "genre rename applies to the track")

# 5) validation
chk(c.post("/api/taxonomy/rename", json={"kind": "tag", "id": techno, "name": ""}).status_code == 400,
    "empty rename rejected")
chk(c.post("/api/taxonomy/merge", json={"kind": "tag", "ids": [techno], "name": "x"}).status_code == 400,
    "merge needs two or more ids")

print("")
print("  ALL PASS" if not fails else f"  {len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
