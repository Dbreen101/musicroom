"""Proves the REAL run_import (Option B): a broken track whose file is gone gets
its row relinked to a found copy, and a genuine duplicate is safely Trashed (not
hard-deleted), with no duplicate track created. Uses a temp DB + a real audio
file copied into a temp folder. Touches nothing in the live library.

Run:  /opt/anaconda3/bin/python test_import_relink.py
"""
import os, sys, sqlite3, tempfile, shutil, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_import_test_")
os.environ["MUSICROOM_DATA"] = TMP            # before importing importer/mr_paths
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# 1) a real, PARSEABLE present audio file from the LIVE library. The library
#    contains some empty stubs + files mutagen can't read (FLACs only ffmpeg
#    decodes); those make a bad fixture, so we verify metadata actually extracts.
import importer
real = sqlite3.connect(f"file:{PROJ}/library.db?mode=ro", uri=True); real.row_factory = sqlite3.Row
src = None
for r in real.execute("SELECT file_path FROM files WHERE is_primary=1 AND is_deleted=0 "
                      "AND duration_sec > 10 AND content_hash IS NOT NULL ORDER BY file_size_mb DESC"):
    p = r["file_path"]
    if not (p and os.path.isfile(p) and p.lower().endswith((".flac", ".mp3"))
            and 500_000 < os.path.getsize(p) < 60_000_000):
        continue
    m = importer.extract_file_metadata(p)
    if m and (m.get("duration_sec") or 0) > 10:
        src = p; break
real.close()
assert src, "no real, parseable audio file available to test with"
print("real test file:", os.path.basename(src))

# 2) temp DB schema (+ migrate for content_hash etc.)
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

# 3) import folder with TWO byte-identical copies
IMP = os.path.join(TMP, "import"); os.makedirs(IMP, exist_ok=True)
ext = os.path.splitext(src)[1]
a  = os.path.join(IMP, "song" + ext);      shutil.copy2(src, a)
a2 = os.path.join(IMP, "song_copy" + ext); shutil.copy2(src, a2)

import importer
meta = importer.extract_file_metadata(a)
h = importer.file_content_hash(a)

# 4) seed a track whose file is MISSING but whose row carries matching meta + hash
db = sqlite3.connect(DB)
if not db.execute("SELECT 1 FROM places WHERE is_well=1").fetchone():
    cols = [r[1] for r in db.execute("PRAGMA table_info(places)")]
    db.execute(f"INSERT INTO places(name,is_well) VALUES('The Well',1)")
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'TestSong','TestArtist',0)")
gone = os.path.join(TMP, "GONE", "song" + ext)
db.execute("""INSERT INTO files(id,track_id,file_path,file_format,file_size_mb,duration_sec,
              bitrate_kbps,sample_rate,content_hash,is_primary,is_deleted)
              VALUES(1,1,?,?,?,?,?,?,?,1,0)""",
           (gone, meta.get("file_format"), meta.get("file_size_mb"), meta.get("duration_sec"),
            meta.get("bitrate_kbps"), meta.get("sample_rate"), h))
db.commit(); db.close()
print("seeded track1 → missing file:", gone, "| exists:", os.path.isfile(gone))

# 5) run the REAL importer with delete-duplicates
importer.run_import(IMP, do_analysis=False, dup_policy="delete")

# 6) assertions
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
files = db.execute("SELECT * FROM files WHERE track_id=1 AND is_deleted=0").fetchall()
ntracks = db.execute("SELECT COUNT(*) n FROM tracks WHERE is_deleted=0").fetchone()["n"]
db.close()
paths = [f["file_path"] for f in files]
chk(any(os.path.isfile(p) for p in paths), "track1 now has a playable file on disk (relinked)")
chk(os.path.normpath(gone) not in [os.path.normpath(p) for p in paths], "row no longer points at the gone path")
chk(ntracks == 1, f"no duplicate track created (tracks={ntracks})")
remaining = [p for p in (a, a2) if os.path.isfile(p)]
chk(len(remaining) == 1, f"exactly one copy kept, the duplicate Trashed (remaining={len(remaining)})")
chk(not os.path.isfile(gone), "the gone path was never recreated")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — import relinks broken tracks + safely removes duplicates"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
