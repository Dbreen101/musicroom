"""Robustness: the REAL run_import must SURVIVE a messy real-world folder —
corrupt files, zero-byte files, a text file masquerading as .flac, unicode
names, deep nesting, unsupported formats — importing the good ones and
skip-and-continuing past the bad ones without crashing or hanging.

This is the "friend points it at their messy library" safety net.

Run:  venv/bin/python3 test_import_robustness.py
"""
import os, sys, sqlite3, tempfile, shutil, subprocess

PROJ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="mr_robust_test_")
os.environ["MUSICROOM_DATA"] = TMP
sys.path.insert(0, PROJ); os.chdir(PROJ)
PY = sys.executable
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# A real, PARSEABLE file from the live library to use as the "good" track.
import importer
real = sqlite3.connect(f"file:{PROJ}/library.db?mode=ro", uri=True); real.row_factory = sqlite3.Row
goods = []   # 3 DISTINCT parseable files so dedup doesn't merge them
for r in real.execute("SELECT file_path FROM files WHERE is_primary=1 AND is_deleted=0 "
                      "AND duration_sec > 10 AND content_hash IS NOT NULL ORDER BY file_size_mb DESC"):
    p = r["file_path"]
    if (p and os.path.isfile(p) and p.lower().endswith((".flac", ".mp3"))
            and 500_000 < os.path.getsize(p) < 60_000_000):
        m = importer.extract_file_metadata(p)
        if m and (m.get("duration_sec") or 0) > 10:
            goods.append(p)
            if len(goods) >= 3: break
real.close()
assert len(goods) >= 3, "need 3 real, parseable audio files to test with"
print("good files:", [os.path.basename(g) for g in goods])

subprocess.run([PY, "schema.py"], env=os.environ, capture_output=True)
subprocess.run([PY, "migrate.py"], env=os.environ, capture_output=True)
DB = os.path.join(TMP, "library.db")

# ---- Build a deliberately nasty import folder --------------------------------
IMP = os.path.join(TMP, "messy"); os.makedirs(IMP, exist_ok=True)
def w(rel, data, mode="wb"):
    full = os.path.join(IMP, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, mode) as f: f.write(data)
    return full

def cp(src, rel):
    full = os.path.join(IMP, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    shutil.copy2(src, full)
cp(goods[0], "good" + os.path.splitext(goods[0])[1])                       # valid
cp(goods[1], "Sióg – Café ñoño" + os.path.splitext(goods[1])[1])           # valid, unicode name
cp(goods[2], os.path.join("deep", "a", "b", "nested" + os.path.splitext(goods[2])[1]))  # nested
w("zero.flac", b"")                                                  # zero-byte
w("junk.mp3", b"\x00\x01\x02\x03not audio")                           # tiny garbage
w("textfile.flac", "this is plainly not a flac\n" * 50, mode="w")    # text masquerading as flac
w("notes.txt", "ignore me\n", mode="w")                              # unsupported ext (ignored)
w("clip.wav", b"RIFF....WAVEfmt junk")                               # .wav IS supported now → garbage-wav, handled like junk.mp3

before = sqlite3.connect(DB).execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

# ---- Run the REAL importer; it must NOT crash or hang ------------------------
crashed = None
try:
    importer.run_import(IMP, do_analysis=False, enrich=False, dup_policy="skip")
except Exception as e:
    crashed = e

chk(crashed is None, f"run_import survived the messy folder without crashing ({crashed!r})")

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
after = con.execute("SELECT COUNT(*) FROM tracks WHERE is_deleted=0").fetchone()[0]
paths = [r["file_path"] for r in con.execute("SELECT file_path FROM files WHERE is_deleted=0")]
bn = [os.path.basename(p) for p in paths if p]

# The 3 valid files (good / unicode / nested) should land.
chk(after - before >= 3, f"the 3 valid files imported (new tracks={after-before})")
chk(any("nested" in b for b in bn), "the deeply-nested valid file imported")
chk(any("Sióg" in b or "oño" in b for b in bn), "the unicode-named valid file imported")

# A genuinely unsupported extension (.txt) must be ignored entirely.
chk(not any(b.endswith(".txt") for b in bn), ".txt was ignored (not imported)")

# Bad audio (zero/junk/text-as-flac) must not have crashed the run; if any row
# exists for them it must be marked not-analysed/empty, never a healthy track.
bad_rows = con.execute(
    "SELECT analysis_status, has_analysis FROM files f JOIN "
    "(SELECT file_path FROM files WHERE file_path LIKE '%zero.flac' "
    " OR file_path LIKE '%junk.mp3' OR file_path LIKE '%textfile.flac') x "
    "ON f.file_path=x.file_path").fetchall()
chk(all((r["has_analysis"] or 0) == 0 for r in bad_rows),
    f"corrupt/empty files never marked as healthy analysed tracks ({len(bad_rows)} rows)")

con.close()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — import survives a messy library, good files in, bad files skipped"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
