"""Proves the case-insensitive path fix that caused the 2026-06-02 data loss:
a file ALREADY in the library, re-scanned under a different-case path (the
external drive mounts as /Volumes or /volumes), must be recognised as the same
file and SKIPPED — never trashed as a "duplicate" of itself — even with
dup-policy=delete. Also proves find_duplicate_file prefers a MISSING-file row
(relink/recovery) over a present one. Temp DB + a generated audio file. Touches nothing
in the live library.

Run:  venv/bin/python test_import_casesafe.py
"""
import os, sys, sqlite3, tempfile, shutil, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_casesafe_test_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import importer

# ---- Part A: file_already_exists is case-insensitive (FS-independent) --------
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")
db = sqlite3.connect(DB)
db.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'T','A',0)")
db.execute("INSERT INTO files(id,track_id,file_path,is_primary,is_deleted) "
           "VALUES(1,1,'/Volumes/EXTERNAL HARD DRIVE 1/Music/Song.mp3',1,0)")
db.commit()
cur = db.cursor()
chk(importer.file_already_exists(cur, "/volumes/external hard drive 1/music/song.mp3"),
    "file_already_exists matches a different-case path (NOCASE)")
chk(not importer.file_already_exists(cur, "/Volumes/EXTERNAL HARD DRIVE 1/Music/Other.mp3"),
    "file_already_exists still rejects a genuinely different file")
db.close()

# ---- Part B: a PRESENT library file re-scanned under a different-case path,
#              dup-policy=delete  →  SKIPPED, file NOT trashed -----------------
import importer
from audio_fixture import make_flac
src = make_flac(os.path.join(TMP, "fixture.flac"))
assert (importer.extract_file_metadata(src) or {}).get("duration_sec", 0) > 10, "fixture audio didn't parse"
ext = os.path.splitext(src)[1]

# case-insensitive FS? (macOS boot vol default). If not, Part B is a no-op.
probe = os.path.join(TMP, "CaseProbe"); open(probe, "w").close()
ci_fs = os.path.exists(os.path.join(TMP, "caseprobe")); os.remove(probe)

if ci_fs:
    os.environ["MUSICROOM_DATA"] = TMP
    db2 = os.path.join(TMP, "lib2.db"); shutil.copy(DB, db2)  # fresh-ish
    # rebuild a clean DB for the run
    os.remove(DB)
    subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
    subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)

    IMP = os.path.join(TMP, "Library"); os.makedirs(IMP, exist_ok=True)
    present = os.path.join(IMP, "song" + ext); shutil.copy2(src, present)
    meta = importer.extract_file_metadata(present); h = importer.file_content_hash(present)

    d = sqlite3.connect(DB)
    if not d.execute("SELECT 1 FROM places WHERE is_well=1").fetchone():
        d.execute("INSERT INTO places(name,is_well) VALUES('The Well',1)")
    d.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'TestSong','TestArtist',0)")
    # store the row with an UPPERCASE filename — same physical file, different case
    stored = os.path.join(IMP, "SONG" + ext)
    d.execute("""INSERT INTO files(id,track_id,file_path,file_format,file_size_mb,duration_sec,
                 bitrate_kbps,sample_rate,content_hash,is_primary,is_deleted)
                 VALUES(1,1,?,?,?,?,?,?,?,1,0)""",
              (stored, meta.get("file_format"), meta.get("file_size_mb"), meta.get("duration_sec"),
               meta.get("bitrate_kbps"), meta.get("sample_rate"), h))
    d.commit(); d.close()

    importer.run_import(IMP, do_analysis=False, dup_policy="delete")

    d = sqlite3.connect(DB); d.row_factory = sqlite3.Row
    ntracks = d.execute("SELECT COUNT(*) n FROM tracks WHERE is_deleted=0").fetchone()["n"]
    d.close()
    chk(os.path.isfile(present), "the library's own file was NOT trashed (re-scanned under different case)")
    chk(ntracks == 1, f"no duplicate track created (tracks={ntracks})")
else:
    print("  SKIP  Part B — filesystem is case-sensitive here")

# ---- Part C: find_duplicate_file prefers a MISSING row (relink) over present -
subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
os.remove(DB); subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
IMP2 = os.path.join(TMP, "imp2"); os.makedirs(IMP2, exist_ok=True)
incoming = os.path.join(IMP2, "in" + ext); shutil.copy2(src, incoming)
present2 = os.path.join(TMP, "present" + ext); shutil.copy2(src, present2)
meta = importer.extract_file_metadata(incoming); h = importer.file_content_hash(incoming)
d = sqlite3.connect(DB)
d.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(1,'T','A',0)")
d.execute("INSERT INTO tracks(id,title,artist_name,is_deleted) VALUES(2,'T2','A2',0)")
common = (meta.get("file_format"), meta.get("file_size_mb"), meta.get("duration_sec"),
          meta.get("bitrate_kbps"), meta.get("sample_rate"), h)
# row 10 = PRESENT copy (track 1); row 20 = MISSING copy (track 2)
d.execute("""INSERT INTO files(id,track_id,file_path,file_format,file_size_mb,duration_sec,
             bitrate_kbps,sample_rate,content_hash,is_primary,is_deleted)
             VALUES(10,1,?,?,?,?,?,?,?,1,0)""", (present2,)+common)
d.execute("""INSERT INTO files(id,track_id,file_path,file_format,file_size_mb,duration_sec,
             bitrate_kbps,sample_rate,content_hash,is_primary,is_deleted)
             VALUES(20,2,?,?,?,?,?,?,?,1,0)""", (os.path.join(TMP,"GONE"+ext),)+common)
d.commit()
dup, _ = importer.find_duplicate_file(d.cursor(), incoming, meta)
d.close()
chk(dup is not None and dup["id"] == 20,
    f"find_duplicate_file returned the MISSING row for relink, not the present one (got id={dup and dup['id']})")
chk(dup is not None and dup.get("present") is False,
    "the chosen match is flagged not-present (caller will relink, not trash)")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — case-variant files are never trashed; recovery is preferred"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
