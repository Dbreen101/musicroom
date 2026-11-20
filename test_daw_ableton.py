"""Scan against a REAL Ableton layout (modelled on Daithí's actual drive):
- Ableton appends ' Project' to the folder it makes on Save → stripped to the
  track name;
- saved copies carry a ' [YYYY-MM-DD HHMMSS]' suffix; the un-stamped .als is the
  current session;
- internal folders 'Samples' / 'Ableton Project Info' / 'Ableton Folder Info' are
  skipped, so internal/recorded audio is never imported as a "version";
- '.alc' clips are not sessions; only '.als' is;
- renders exported to the project root (Ableton's default) are found as versions.

Run:  /opt/anaconda3/bin/python test_daw_ableton.py
"""
import os, sys, tempfile, subprocess, sqlite3

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_dawab_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

ROOT = os.path.join(TMP, "Productions")
def put(*parts, data=b"x"):
    p = os.path.join(ROOT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data); return p

# Track 1 — Ableton "<name> Project" folder, a stamped version + the current
# set, a render in the project root, plus internals that MUST be skipped.
cur1   = put("18 amrch Project", "18 amrch.als")
ver1   = put("18 amrch Project", "18 amrch [2026-05-19 230207].als")
ren1   = put("18 amrch Project", "18 amrch.wav")
put("18 amrch Project", "Samples", "Recorded", "take 1.wav")           # skip
put("18 amrch Project", "Ableton Project Info", "Project8.cfg")        # skip
# Track 2 — newer "Ableton Folder Info" name, render tucked in Bounces, a clip
cur2   = put("Seanchaí Project", "Seanchaí.als")
ren2   = put("Seanchaí Project", "Bounces", "Seanchaí master.wav")
put("Seanchaí Project", "Ableton Folder Info", "x.xmp")                # skip
put("Seanchaí Project", "idea.alc")                                    # ignore (clip)

import daw_projects
projs = {p["name"]: p for p in daw_projects.scan_productions(ROOT)}
chk(set(projs) == {"18 amrch", "Seanchaí"}, f"' Project' stripped → track names (got {set(projs)})")
a = projs.get("18 amrch", {})
chk(set(a.get("sessions", [])) == {cur1, ver1}, "both .als (current + stamped version) found as sessions")
chk(a.get("primary_session") == cur1, "current session = the un-stamped .als")
chk(a.get("bounces") == [ren1], "render in the project root found; Samples/internal skipped")
s = projs.get("Seanchaí", {})
chk(s.get("bounces") == [ren2], "render in Bounces/ found; Ableton Folder Info skipped")
chk(s.get("sessions") == [cur2], ".alc clip NOT counted as a session")

# Import → links the current session
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
import app
c = app.app.test_client()
r = c.post("/api/studio/import", json={"path": ROOT}).get_json()
chk(r.get("tracks_created") == 2, f"imported 2 tracks (got {r.get('tracks_created')})")
db = sqlite3.connect(os.path.join(TMP, "library.db")); db.row_factory = sqlite3.Row
t = db.execute("SELECT * FROM tracks WHERE title='18 amrch'").fetchone()
chk(t and t["daw_project_path"] == cur1, "track linked to the CURRENT session (not a stamped copy)")
db.close()

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — reads Ableton's own layout (Project folders, stamped versions, skipped internals)"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
