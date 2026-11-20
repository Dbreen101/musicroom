"""Organise (tidy) a messy productions folder into the convention.

Proves COPY leaves every original untouched, a whole project folder is placed as
a UNIT (Ableton refs intact), loose renders are filed into <track>/Bounces and
grouped by name (timestamp stripped), the tidy result imports, and MOVE frees the
source. Temp dirs only.

Run:  /opt/anaconda3/bin/python test_daw_organise.py
"""
import os, sys, tempfile, subprocess, sqlite3

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_daworg_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

def put(root, *parts, data=b"x"):
    p = os.path.join(root, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(data); return p

# Messy source: a real project folder + two loose renders (one stamped) of "Aurora"
SRC = os.path.join(TMP, "Messy")
put(SRC, "Smoke Signal Project", "Smoke Signal.als")
put(SRC, "Smoke Signal Project", "Smoke Signal.wav")
put(SRC, "Smoke Signal Project", "Samples", "Recorded", "internal.wav")   # must travel WITH the project, never imported
put(SRC, "Aurora.wav")
put(SRC, "Aurora [2026-01-01 120000].wav")
src_files_before = sorted(os.path.relpath(os.path.join(dp, fn), SRC)
                          for dp, _, fns in os.walk(SRC) for fn in fns)

import daw_projects
DEST = os.path.join(TMP, "Tidy")
r = daw_projects.organise_productions(SRC, DEST, mode="copy")
chk(r.get("projects_filed") == 1, f"placed the project folder as a unit (got {r.get('projects_filed')})")
chk(r.get("loose_filed") == 2, f"filed 2 loose renders (got {r.get('loose_filed')})")

# COPY → originals untouched
after = sorted(os.path.relpath(os.path.join(dp, fn), SRC)
               for dp, _, fns in os.walk(SRC) for fn in fns)
chk(after == src_files_before, "COPY left every original file in place")
# tidy structure built
chk(os.path.isfile(os.path.join(DEST, "Smoke Signal Project", "Smoke Signal.als")), "project folder placed intact")
chk(os.path.isfile(os.path.join(DEST, "Smoke Signal Project", "Samples", "Recorded", "internal.wav")), "Samples travelled WITH the project")
chk(os.path.isfile(os.path.join(DEST, "Aurora", "Bounces", "Aurora.wav")), "loose render filed into <track>/Bounces")
chk(os.path.isfile(os.path.join(DEST, "Aurora", "Bounces", "Aurora [2026-01-01 120000].wav")), "stamped render grouped to the same track")

# import the tidy result
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
import app
c = app.app.test_client()
imp = c.post("/api/studio/import", json={"path": DEST}).get_json()
chk(imp.get("tracks_created") == 2, f"tidy result imported 2 tracks (got {imp.get('tracks_created')})")
db = sqlite3.connect(os.path.join(TMP, "library.db")); db.row_factory = sqlite3.Row
aurora = db.execute("SELECT id FROM tracks WHERE title='Aurora'").fetchone()
nver = db.execute("SELECT COUNT(*) FROM files WHERE track_id=?", (aurora["id"],)).fetchone()[0]
chk(nver == 2, "Aurora imported with both versions")
smoke_files = db.execute("SELECT COUNT(*) FROM files f JOIN tracks t ON t.id=f.track_id WHERE t.title='Smoke Signal'").fetchone()[0]
chk(smoke_files == 1, "Smoke Signal imported its render only (internal Samples audio excluded)")
db.close()

# MOVE frees the source
SRC2 = os.path.join(TMP, "Messy2"); put(SRC2, "Tune Project", "Tune.als"); put(SRC2, "Tune Project", "Tune.wav")
DEST2 = os.path.join(TMP, "Tidy2")
daw_projects.organise_productions(SRC2, DEST2, mode="move")
chk(not os.path.exists(os.path.join(SRC2, "Tune Project")), "MOVE removed the project from the source")
chk(os.path.isfile(os.path.join(DEST2, "Tune Project", "Tune.als")), "MOVE placed it at the destination")

# refuses a destination inside the source
bad = daw_projects.organise_productions(SRC, os.path.join(SRC, "inside"), mode="copy")
chk(bad.get("error"), "refuses a destination inside the source")

import shutil; shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — tidy is safe: copy keeps originals, projects move as a unit, loose renders grouped + imported"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
