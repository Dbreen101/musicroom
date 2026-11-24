"""The backup made when the app starts copies the DATABASE the right way.

The app keeps its database open while it runs. Copied as a plain file it can be out of
date (what was saved last still sits in its -wal side file) or torn, and the side files
come and go under rsync: on 24 Nov 2026 a launch backup was skipped whole
("library.db-wal: No such file"). Found by Kristian Vastveit. So SQLite makes the copy
itself and rsync copies everything else. This proves:
- the copy holds everything saved so far, and nothing half-saved, while the app is writing;
- no side files travel, and old ones at the destination are cleared;
- stopped half-way, the copy from last time is still there;
- the rest of the folder is mirrored as before (no audio, deletions follow);
- a database is never copied onto itself.

Run:  ./venv/bin/python test_backup_database.py
"""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_backup_db_")
DATA = os.path.join(TMP, "data"); os.makedirs(DATA)
os.environ["MUSICROOM_DATA"] = DATA
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, PROJ); os.chdir(PROJ)
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
def sha(p):
    with open(p, "rb") as f: return hashlib.sha256(f.read()).hexdigest()
def setting_in(db, key):
    with closing(sqlite3.connect(db)) as x:
        r = x.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

import contextlib, io
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database(); migrate.run_migration()
open(os.path.join(DATA, "artwork.png"), "w").write("img")
open(os.path.join(DATA, "notes.txt"), "w").write("kept")
open(os.path.join(DATA, "song.mp3"), "w").write("AUDIO")

import app

DB = app.DB_PATH
chk(os.path.dirname(DB) == DATA, "(the test's database is in its own throwaway folder)")

# ── the app as it is while running: the database open, things saved that are still only in the side file ──
live = sqlite3.connect(DB)
live.execute("PRAGMA journal_mode = WAL")
live.execute("PRAGMA wal_autocheckpoint = 0")           # (nothing is folded into the main file behind our back)
live.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('saved_just_now', 'yes')")
live.commit()
writing = sqlite3.connect(DB)                           # … and something half-saved, in the middle of a write
writing.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('half_saved', 'not yet')")
chk(os.path.getsize(DB + "-wal") > 0, "(the app has saved something that is still only in the side file)")

# what the old way gave: the main file alone, as rsync took it
old_way = os.path.join(TMP, "old_way"); os.makedirs(old_way)
shutil.copy2(DB, os.path.join(old_way, "library.db"))
chk(setting_in(os.path.join(old_way, "library.db"), "saved_just_now") is None,
    "the old way (a plain copy of the file) misses what was saved last — the bug")

# ── the backup, to a folder that holds an older backup made the old way ──
dest = os.path.join(TMP, "backup"); os.makedirs(dest)
shutil.copy2(os.path.join(old_way, "library.db"), os.path.join(dest, "library.db"))
open(os.path.join(dest, "library.db-wal"), "wb").write(b"a side file from an older backup")
open(os.path.join(dest, "library.db-shm"), "wb").write(b"another")
open(os.path.join(dest, "library.db.copying"), "wb").write(b"a copy that was cut short")
open(os.path.join(dest, "left_behind.txt"), "w").write("deleted from the app since")

ok, err = app._rsync_data_to(dest)
chk(ok and err is None, f"the backup runs while the app is writing (err={err!r})")
there = set(os.listdir(dest))
copy = os.path.join(dest, "library.db")
chk("library.db" in there, "the database is in the backup")
chk(setting_in(copy, "saved_just_now") == "yes", "it holds what was saved last")
chk(setting_in(copy, "half_saved") is None, "and nothing that was only half-saved")
with closing(sqlite3.connect(copy)) as x:
    chk(x.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "the copy is a sound database")
there = set(os.listdir(dest))                           # (opening the copy above may make side files of its own)
chk(not [n for n in os.listdir(dest) if n.startswith("library.db.copying")], "nothing is left of a copy that was cut short")
chk({"artwork.png", "notes.txt"} <= there, "everything else in the folder is copied as before")
chk("song.mp3" not in there, "audio is still left out")
chk("left_behind.txt" not in there, "what is gone from the app is gone from the backup")

# a second run, with more saved since: the copy follows, and no side file of the LIVE database travels
for n in ("library.db-wal", "library.db-shm"):
    try: os.remove(os.path.join(dest, n))
    except FileNotFoundError: pass
writing.commit()
live.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('saved_later', 'yes')"); live.commit()
os.remove(os.path.join(DATA, "notes.txt"))
ok, err = app._rsync_data_to(dest)
there = set(os.listdir(dest))
chk(ok and not {"library.db-wal", "library.db-shm", "library.db-journal"} & there,
    "the live database's side files never travel (the ones whose coming and going stopped the backup)")
chk(setting_in(copy, "saved_later") == "yes" and setting_in(copy, "half_saved") == "not yet",
    "run again, the backup holds what has been saved since")
for n in ("library.db-wal", "library.db-shm"):
    try: os.remove(os.path.join(dest, n))
    except FileNotFoundError: pass
chk("notes.txt" not in set(os.listdir(dest)) and "library.db" in set(os.listdir(dest)),
    "a file deleted since is cleared from the backup, and the database is not cleared with it")

# ── stopped half-way: the copy from last time is still there ──
before = sha(copy)
real_backup = sqlite3.Connection.backup
class Cut(sqlite3.Connection):
    def backup(self, *a, **k): raise sqlite3.OperationalError("the drive was pulled out")
real_connect = sqlite3.connect
def cutting_connect(*a, **k):
    k.setdefault("factory", Cut); return real_connect(*a, **k)
app.sqlite3.connect = cutting_connect
try:
    ok, err = app._rsync_data_to(dest)
finally:
    app.sqlite3.connect = real_connect
chk(ok is False and "database" in (err or ""), f"a copy that can't be finished is reported, in words ({err!r})")
chk(os.path.exists(copy) and sha(copy) == before, "and the database copy from last time is untouched")
chk(not [n for n in os.listdir(dest) if n.startswith("library.db.copying")], "with nothing half-made left beside it")
chk(app._rsync_data_to(dest)[0] is True, "the next backup goes through")

# ── never onto itself (a library adopted from the drive has its data folder ON the drive) ──
mine = sha(DB)
live.close(); writing.close()
with closing(sqlite3.connect(DB)) as x:
    x.execute("PRAGMA wal_checkpoint(TRUNCATE)")
mine = sha(DB)
ok, err = app._copy_database_to(DATA)
chk(ok and sha(DB) == mine and not [n for n in os.listdir(DATA) if n.startswith("library.db.copying")],
    "asked to copy the database into its own folder, the app leaves it alone")

# ── no database yet (a first start): the rest is still mirrored, nothing fails ──
empty_dest = os.path.join(TMP, "first_start")
hold = DB + ".away"
os.rename(DB, hold)
for s in ("-wal", "-shm"):
    try: os.remove(DB + s)
    except FileNotFoundError: pass
try:
    ok, err = app._rsync_data_to(empty_dest)
finally:
    os.rename(hold, DB)
chk(ok and "artwork.png" in os.listdir(empty_dest) and "library.db" not in os.listdir(empty_dest),
    "with no database yet, the backup still copies the rest and does not fail")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
