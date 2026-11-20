"""Own-productions scan + reference-in-place import.

Proves: the scanner finds sessions + bounces per the convention and SKIPS
Ableton's Samples/Backup internals; the importer creates one own-work track per
project with its versions, links them to the session, adds them to The Well, and
— critically — NEVER moves, copies or renames a single file (reference in place).
Temp DB + temp fake project tree.

Run:  /opt/anaconda3/bin/python test_daw_scan.py
"""
import os, sys, sqlite3, tempfile, subprocess, hashlib

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_daw_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ── Build a fake productions tree ────────────────────────────────────────────
PROD = os.path.join(TMP, "My Productions")
def touch(*parts, data=b"x"):
    p = os.path.join(PROD, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)
    return p

# Track 1 — session + a Bounces folder of versions, plus Ableton internals to skip
als1   = touch("Smoke Signal", "Smoke Signal.als")
v1a    = touch("Smoke Signal", "Bounces", "Smoke Signal v1.wav")
v1b    = touch("Smoke Signal", "Bounces", "Smoke Signal final.wav")
junk1  = touch("Smoke Signal", "Samples", "Recorded", "internal-stem.wav")   # MUST be skipped
junk2  = touch("Smoke Signal", "Backup", "Smoke Signal [2026-01-01].als")    # MUST be skipped
# Track 2 — bounce sitting in the track folder top level (no Bounces subfolder)
als2   = touch("Aurora", "Aurora.als")
v2a    = touch("Aurora", "Aurora rough mix.wav")

import daw_projects
projs = daw_projects.scan_productions(PROD)
chk(len(projs) == 2, f"found 2 track folders (got {len(projs)})")
by = {p["name"]: p for p in projs}
chk("Smoke Signal" in by and "Aurora" in by, "track names = folder names")
ss = by.get("Smoke Signal", {})
chk(als1 in ss.get("sessions", []), "session (.als) found")
chk(set(ss.get("bounces", [])) == {v1a, v1b}, "both bounces found in Bounces/")
chk(junk1 not in ss.get("bounces", []), "Samples/ internal audio SKIPPED")
chk(all(not b.endswith(".als") for b in ss.get("bounces", [])), "no .als counted as a bounce")
au = by.get("Aurora", {})
chk(v2a in au.get("bounces", []), "top-level bounce found (no Bounces subfolder needed)")

# ── Import by reference + assert files are untouched ─────────────────────────
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)

def tree_snapshot(root):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            fp = os.path.join(dp, fn)
            out[fp] = os.path.getsize(fp)
    return out
before = tree_snapshot(PROD)

import app
c = app.app.test_client()
r = c.post("/api/studio/import", json={"path": PROD}).get_json()
chk(r.get("tracks_created") == 2, f"imported 2 own-work tracks (got {r.get('tracks_created')})")
chk(r.get("files_created") == 3, f"imported 3 versions total (got {r.get('files_created')})")

db = sqlite3.connect(os.path.join(TMP, "library.db")); db.row_factory = sqlite3.Row
ts = db.execute("SELECT * FROM tracks WHERE is_own_work=1 ORDER BY title").fetchall()
chk(len(ts) == 2 and all(t["is_own_work"] == 1 for t in ts), "tracks marked is_own_work")
chk(all((t["daw_project_path"] or "").endswith(".als") for t in ts), "tracks linked to their .als project")
smoke = next(t for t in ts if t["title"] == "Smoke Signal")
fs = db.execute("SELECT * FROM files WHERE track_id=? ORDER BY file_path", (smoke["id"],)).fetchall()
chk(len(fs) == 2, "Smoke Signal has its 2 versions")
chk(all(f["session_path"] == als1 for f in fs), "each version links to its session")
chk({f["file_path"] for f in fs} == {v1a, v1b}, "files reference the ORIGINAL paths (in place)")
chk(sum(f["is_primary"] for f in fs) == 1, "exactly one primary version")
# in The Well
well = db.execute("SELECT id FROM places WHERE is_well=1").fetchone()
inwell = db.execute("SELECT COUNT(*) FROM place_tracks WHERE place_id=? AND track_id=?",
                    (well["id"], smoke["id"])).fetchone()[0]
chk(inwell == 1, "own-work track added to The Well")
db.close()

after = tree_snapshot(PROD)
chk(before == after, "NOT ONE FILE moved, copied or renamed (reference in place)")

# re-import is idempotent (no duplicate versions)
r2 = c.post("/api/studio/import", json={"path": PROD}).get_json()
chk(r2.get("tracks_created") == 0 and r2.get("files_created") == 0, "re-import creates nothing (idempotent)")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — scan honours the convention; import links versions+sessions in place, never touches files"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
