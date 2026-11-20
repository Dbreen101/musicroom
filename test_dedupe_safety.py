"""Proves dedupe.run_dedupe (the SHIPPING logic) never loses audio.

Runs the real function against throwaway files, including the exact case that
destroyed real data before: a byte-identical group where the *preferred keeper*
(a Music Room Library path) is ALREADY GONE from disk but still has a stored
content_hash, while the surviving copy is elsewhere. The old code kept the gone
file and trashed the survivor → track lost. This asserts that can't happen.

Run:  venv/bin/python test_dedupe_safety.py   (or /opt/anaconda3/bin/python)
"""
import os, sqlite3, tempfile, shutil, hashlib, sys
import dedupe

tmp = tempfile.mkdtemp(prefix="mr_dedupe_test_")
TRASH = os.path.join(tmp, "_trash")
os.makedirs(TRASH, exist_ok=True)
LIB = os.path.join(tmp, "Music Room Library")
ROOT = os.path.join(tmp, "root")
os.makedirs(LIB); os.makedirs(ROOT)

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh: fh.write(content)
    return path

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""): h.update(c)
    return h.hexdigest()

# injected deps that mimic production but are safe + observable
def isfile(p):
    try: return os.path.isfile(p)
    except OSError: return False
def file_hash(p): return sha(p) if isfile(p) else None
def real_trash(p):            # moves to a trash dir = recoverable, never destroys
    if not isfile(p): return True, None
    shutil.move(p, os.path.join(TRASH, os.path.basename(p))); return True, None
def failing_trash(p):         # simulates Trash being unavailable
    return False, "trash unavailable"

# --- build the dataset ---
AAA = b"AAAA"*100; CCC = b"CCCC"*100; BBB = b"BBBB"*100
# trackA: identical copies, one in Library (keeper) + one in root (redundant)
a_lib  = write(os.path.join(LIB, "A", "a.flac"), AAA)
a_root = write(os.path.join(ROOT, "a.flac"), AAA)
# trackB: a single unique file — must never be touched
b_one  = write(os.path.join(ROOT, "b.flac"), BBB)
# trackC: the DANGER. Library "keeper" path is gone but has a stored hash;
# the real surviving copy is in root. (c_lib intentionally NOT written.)
c_lib_path = os.path.join(LIB, "C", "c.flac")     # does NOT exist on disk
c_root = write(os.path.join(ROOT, "c.flac"), CCC)
# trackD: two identical copies but Trash fails — both file and rows must survive
d1 = write(os.path.join(ROOT, "d1.flac"), b"DDDD"*100)
d2 = write(os.path.join(ROOT, "d2.flac"), b"DDDD"*100)

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.execute("""CREATE TABLE files (id INTEGER PRIMARY KEY, track_id INT, file_path TEXT,
  content_hash TEXT, is_primary INT, is_deleted INT DEFAULT 0, hashed_at TEXT, updated_at TEXT)""")
def add(fid, tid, path, primary, h=None):
    conn.execute("INSERT INTO files(id,track_id,file_path,content_hash,is_primary,is_deleted) VALUES(?,?,?,?,?,0)",
                 (fid, tid, path, h, primary))
add(1, 10, a_lib,  1)
add(2, 10, a_root, 0)
add(3, 20, b_one,  1)
add(4, 30, c_lib_path, 1, h=sha(c_root))   # stale hash of the (gone) library copy
add(5, 30, c_root, 0, h=sha(c_root))
add(6, 40, d1, 1)
add(7, 40, d2, 0)
conn.commit()

def rows():
    return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM files")}
def group(ids):
    return [dict(conn.execute("SELECT * FROM files WHERE id=?", (i,)).fetchone()) for i in ids]

# run the REAL shipping logic, delete_files=True
dedupe.run_dedupe(conn, [group([1,2]), group([4,5])], True,
                  file_hash=file_hash, trash=real_trash, isfile=isfile)
# trackD group with a FAILING trash
dedupe.run_dedupe(conn, [group([6,7])], True,
                  file_hash=file_hash, trash=failing_trash, isfile=isfile)

r = rows()
fails = []
def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond: fails.append(msg)

print("=== trackA: identical Library + root copy ===")
check(isfile(a_lib), "Library keeper still on disk")
check(not isfile(a_root) and isfile(os.path.join(TRASH,"a.flac")), "redundant root copy moved to Trash (recoverable, not destroyed)")
check(r[1]["is_deleted"]==0 and r[2]["is_deleted"]==1, "DB: keeper active, redundant retired")

print("=== trackC: stale-hash keeper GONE, survivor in root (the bug that killed real data) ===")
check(isfile(c_root), "surviving copy still on disk — NOT trashed")
check(r[5]["is_deleted"]==0, "surviving copy's DB row still active")
check([x for x in (r[4],r[5]) if not x["is_deleted"] and isfile(x["file_path"])], "trackC still has a playable file")

print("=== trackB: single unique file ===")
check(isfile(b_one) and r[3]["is_deleted"]==0, "untouched")

print("=== trackD: duplicate but Trash FAILED ===")
check(isfile(d1) and isfile(d2), "both files still on disk (refused to delete)")
check(r[6]["is_deleted"]==0 and r[7]["is_deleted"]==0, "neither row marked removed when trash failed")

print("=== global invariant ===")
import collections
bytrack = collections.defaultdict(list)
for f in r.values(): bytrack[f["track_id"]].append(f)
orphaned = [t for t,fs in bytrack.items()
            if not any(x["is_deleted"]==0 and isfile(x["file_path"]) for x in fs)]
check(not orphaned, f"no track left without a playable file (orphaned tracks: {orphaned})")

shutil.rmtree(tmp, ignore_errors=True)
print("\nRESULT:", "ALL PASS — dedupe cannot lose audio" if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
