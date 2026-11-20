"""Proves the portable-drive DB resolution David asked for:
- if the LOCAL computer has a database, use it;
- if it has NONE, fall back to the database on a plugged-in Music Room drive
  (/Volumes/*/Music Room — App Data/library.db) — so the drive is portable:
  plug it into another machine and the library is there.
Music files already resolve from the drive separately (_resolve_audio_path).

Run:  /opt/anaconda3/bin/python test_db_fallback.py
"""
import os, sys, tempfile, importlib

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import mr_paths

# a fake "/Volumes" with one drive carrying a portable Music Room
vols = tempfile.mkdtemp(prefix="mr_vols_")
drive = os.path.join(vols, "BACKUP DRIVE", mr_paths.DRIVE_APPDATA_FOLDER)
os.makedirs(drive)
open(os.path.join(drive, "library.db"), "w").write("db")

# 1. discovery finds the drive's app-data folder
found = mr_paths._find_drive_appdata(volumes_root=vols)
chk(found == drive, f"discovers the drive's Music Room — App Data folder (got {found})")

# 2. no drive present → None
empty_vols = tempfile.mkdtemp(prefix="mr_vols_empty_")
chk(mr_paths._find_drive_appdata(volumes_root=empty_vols) is None,
    "returns None when no Music Room drive is mounted")

# 3. resolution prefers a LOCAL db when present
local = tempfile.mkdtemp(prefix="mr_local_")
open(os.path.join(local, "library.db"), "w").write("db")
os.environ["MUSICROOM_DATA"] = local
importlib.reload(mr_paths)
chk(mr_paths.DATA_DIR == local, "uses the LOCAL database when the computer has one")

# 4. an EXPLICIT data dir with no DB is used literally — NEVER hijacked by a
#    mounted drive (so creating a fresh DB / the tests / power users work). This
#    is the regression the suite caught: the drive fallback must only apply to
#    the DEFAULT location, never to an explicit MUSICROOM_DATA.
no_db = tempfile.mkdtemp(prefix="mr_nodb_")
os.environ["MUSICROOM_DATA"] = no_db
importlib.reload(mr_paths)
chk(mr_paths.DATA_DIR == no_db,
    "explicit MUSICROOM_DATA is literal (a real plugged-in drive does NOT hijack DB creation)")

import shutil
for d in (vols, empty_vols, local, no_db): shutil.rmtree(d, ignore_errors=True)
print("\nRESULT:", "ALL PASS — local DB preferred, drive DB adopted when none local (portable)"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
