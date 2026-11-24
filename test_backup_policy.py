"""Proves the backup policy Daithí asked for:
- the routine (laptop) backup copies the database + metadata but NEVER audio
  ('I don't want music files on my laptop');
- the full backup REFUSES any destination that isn't a mounted external volume
  (so it can never silently dump music onto the laptop).

Run:  /opt/anaconda3/bin/python test_backup_policy.py
"""
import os, sys, tempfile, subprocess, shutil

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_backup_")
DATA = os.path.join(TMP, "data"); os.makedirs(DATA)
os.environ["MUSICROOM_DATA"] = DATA
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# seed a data dir: a DB, an artwork file, and an AUDIO file (must NOT be backed up)
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
open(os.path.join(DATA, "artwork.png"), "w").write("img")
os.makedirs(os.path.join(DATA, "Removed from Music Room"), exist_ok=True)
open(os.path.join(DATA, "Removed from Music Room", "old beat.flac"), "w").write("AUDIO")
open(os.path.join(DATA, "song.mp3"), "w").write("AUDIO")

import app

# 1) routine backup → excludes audio
dest = os.path.join(TMP, "laptop_backup")
app._run_backup(dest_dir=dest)
backed = set()
for dp, _d, files in os.walk(dest):
    for f in files: backed.add(f)
chk("library.db" in backed, "routine backup includes the database")
chk("artwork.png" in backed, "routine backup includes metadata (artwork)")
chk("song.mp3" not in backed, "routine backup EXCLUDES audio (.mp3)")
chk("old beat.flac" not in backed, "routine backup EXCLUDES audio in the Removed folder (.flac)")

# 2) full backup refuses a non-external-volume destination (never the laptop)
app._run_full_backup(os.path.join(TMP, "not_a_volume"))
st = app._full_backup_state
chk(st["phase"] == "error" and "mounted" in st["error"].lower(),
    f"full backup REFUSES a non-/Volumes destination (state={st['phase']}, err={st['error'][:60]!r})")
chk(not os.path.exists(os.path.join(TMP, "not_a_volume")),
    "full backup wrote nothing to the rejected destination")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — DB/metadata backs up without audio; full backup is drive-only"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
