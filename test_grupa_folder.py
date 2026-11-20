"""A grúpa as a folder of files (grupa_folder.py + the /api/grupa/<id>/folder
routes): the records go in the folder in the grúpa's order WITHOUT being copied
where the disk allows — the same file listed twice, else a link — and are only
copied when asked. Originals are never moved, changed or deleted.
Fresh database, made-up files, no sound. Run:  ./venv/bin/python test_grupa_folder.py"""
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name).resolve()
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.pop("MR_GREEN_ROOM", None)
(TMP / "app_data").mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import grupa_folder as gf

# ─── made-up records in a made-up library ───
LIB = TMP / "drive" / "Music Room Library"
(LIB / "Someone").mkdir(parents=True)
def rec(name, fill):
    p = LIB / "Someone" / name
    p.write_bytes(bytes([fill]) * 4096)
    return p
A, B, C, D = rec("alpha.flac", 1), rec("beta.mp3", 2), rec("gamma.wav", 3), rec("delta.flac", 4)
def sig(p): st = os.stat(p); return (st.st_size, int(st.st_mtime), hashlib.sha256(Path(p).read_bytes()).hexdigest())
BEFORE = {p: sig(p) for p in (A, B, C, D)}
T = lambda tid, title, artist, path: {"track_id": tid, "title": title, "artist": artist, "path": str(path), "duration_sec": 60 * tid}
tracks = [T(1, "Alpha", "Someone", A), T(2, "Beta: Part 1/2", "Someone", B), T(3, "", "", C)]

# ─── names, and where the folder lives ───
chk(gf.names_for(tracks) == ["01 Someone - Alpha.flac", "02 Someone - Beta_ Part 1_2.mp3", "03 gamma.wav"],
    "each name begins with its number in the grúpa; odd characters are made safe; a record the room can't name keeps its file's name")
chk(gf.names_for([T(1, "Same", "X", A), T(2, "Same", "X", A)]) == ["01 X - Same.flac", "02 X - Same.flac"]
    and gf.names_for([T(i, "t", "a", A) for i in range(1, 102)])[0].startswith("001 "), "a record twice is two names; a hundred records get three figures")
chk(gf.root_for(str(LIB), str(TMP / "app_data" / "exports")) == (LIB.parent / "Music Room — Grúpaí", "library")
    and gf.root_for(str(TMP / "nowhere"), str(TMP / "app_data" / "exports")) == (TMP / "app_data" / "exports" / "Grúpaí", "own")
    and gf.root_for("", "/x") == (Path("/x/Grúpaí"), "own"),
    "the folder lives beside the library on its drive, never inside it; with no library to stand beside, in the app's own folder")

# ─── nothing is copied: the same file, listed twice ───
F = LIB.parent / "Music Room — Grúpaí" / "Deep listening"
out = gf.build(F, "Deep listening", tracks, grupa_id=7)
made = sorted(n for n in os.listdir(F) if not n.startswith("."))
chk(out["files"] == 3 and out["same"] == 3 and out["linked"] == 0 and out["copied"] == 0 and out["bytes_copied"] == 0 and not out["failed"],
    "three records go in, none of them copied")
chk(made == ["01 Someone - Alpha.flac", "02 Someone - Beta_ Part 1_2.mp3", "03 gamma.wav", "Deep listening.m3u8"]
    and all(os.path.samefile(F / n, t["path"]) for n, t in zip(made[:3], tracks)) and not (F / made[0]).is_symlink()
    and os.stat(A).st_nlink == 2, "each is the very same file as the original, listed in the folder too")
chk({p: sig(p) for p in (A, B, C, D)} == BEFORE, "the originals are exactly as they were")
m3u = (F / "Deep listening.m3u8").read_text().splitlines()
chk(m3u[0] == "#EXTM3U" and [l for l in m3u if not l.startswith("#")] == [str(A), str(B), str(C)] and m3u[1] == "#EXTINF:60,Someone - Alpha",
    "a playlist beside them names the ORIGINAL files, in order")
man = gf.read_manifest(F)
chk(man["kind"] == "grupa_folder" and man["grupa_id"] == 7 and [e["how"] for e in man["files"]] == ["same"] * 3
    and gf.status(F)["how"] == {"same": 3} and gf.status(F)["here"] == 3, "the folder remembers what was put in it, and how")

# ─── the importer never takes a grúpa's folder for new music ───
# (the importer won't look under /private at all, so this small tree stands inside the project folder for a moment)
_home = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent), prefix=".tmp-grupa-folder-")
H = Path(_home.name)
(H / "drive" / "Music Room Library").mkdir(parents=True)
ha = H / "drive" / "Music Room Library" / "one.flac"; ha.write_bytes(b"1" * 512)
hb = H / "drive" / "Music Room Library" / "two.mp3"; hb.write_bytes(b"2" * 512)
htracks = [T(1, "One", "X", ha), T(2, "Two", "X", hb)]
gf.build(H / "drive" / "Music Room — Grúpaí" / "A set", "A set", htracks)
gf.build(H / "drive" / "exports" / "Grúpaí" / "Another", "Another", htracks, mode="copy")
with contextlib.redirect_stdout(io.StringIO()):
    import importer
    found = importer.find_audio_files(str(H / "drive"))
    inside = importer.find_audio_files(str(H / "drive" / "exports" / "Grúpaí" / "Another"))
chk(sorted(found) == sorted([str(ha), str(hb)]) and inside == [],
    "a scan of the drive finds each record once: a grúpa's folder is passed over, wherever it lives, links or copies")
_home.cleanup()

# ─── made again after the grúpa changed: reordered, one out, one in ───
(F / "my own notes.txt").write_text("mine")                              # something of the user's, in the folder
out = gf.build(F, "Deep listening", [T(3, "", "", C), T(1, "Alpha", "Someone", A), T(4, "Delta", "Someone", D)], grupa_id=7)
now = sorted(n for n in os.listdir(F) if not n.startswith("."))
chk(now == ["01 gamma.wav", "02 Someone - Alpha.flac", "03 Someone - Delta.flac", "Deep listening.m3u8", "my own notes.txt"],
    "made again, the folder follows the grúpa's new order and contents; what the user put there is left alone")
chk({p: sig(p) for p in (A, B, C, D)} == BEFORE and os.stat(B).st_nlink == 1 and B.exists(),
    "taking a record out of the folder never touches the record: every original is still there, unchanged")
ino = os.stat(F / "02 Someone - Alpha.flac").st_ino
out = gf.build(F, "Deep listening", [T(3, "", "", C), T(1, "Alpha", "Someone", A), T(4, "Delta", "Someone", D)], grupa_id=7)
chk(os.stat(F / "02 Someone - Alpha.flac").st_ino == ino and out["same"] == 3, "made again with nothing changed, nothing is redone")
(F / "04 Someone - Beta.mp3").write_text("the user's own file under a name we will want")
out = gf.build(F, "Deep listening", [T(3, "", "", C), T(1, "Alpha", "Someone", A), T(4, "Delta", "Someone", D), T(2, "Beta", "Someone", B)], grupa_id=7)
chk((F / "04 Someone - Beta.mp3").read_text().startswith("the user's") and os.path.samefile(F / "04 Someone - Beta (2).mp3", B),
    "a file of the user's that has the name we want is not replaced: ours steps aside")

# ─── across disks: a link to the file, where it is ───
real_link = os.link
def no_link(*a, **k): raise OSError(18, "Cross-device link")
os.link = no_link
F2 = TMP / "laptop" / "Grúpaí" / "Across"
chk(gf.can_link(F2, str(A)) == "link", "where the same file can't be listed twice (another disk), a link can still be made")
out = gf.build(F2, "Across", tracks)
chk(out["linked"] == 3 and out["same"] == 0 and (F2 / "01 Someone - Alpha.flac").is_symlink()
    and os.readlink(F2 / "01 Someone - Alpha.flac") == str(A) and (F2 / "01 Someone - Alpha.flac").read_bytes() == A.read_bytes(),
    "…each one a link to the original, which reads as the record itself")
C.rename(C.with_suffix(".away"))
chk(gf.status(F2)["broken"] == 1 and gf.status(F2)["here"] == 3, "a link whose file has gone (the drive unplugged) is counted as out of reach")
C.with_suffix(".away").rename(C)
out = gf.build(F2, "Across", tracks[:2])
chk(not (F2 / "03 gamma.wav").is_symlink() and C.exists() and {p: sig(p) for p in (A, B, C, D)} == BEFORE,
    "a link taken out of the folder is only the link: the record stays")

# ─── a disk that can do neither: say so, and copy only when asked ───
real_symlink = os.symlink
def no_symlink(*a, **k): raise OSError(1, "Operation not permitted")
os.symlink = no_symlink
F3 = TMP / "stick" / "Grúpaí" / "Copies"
chk(gf.can_link(F3, str(A)) is None, "a disk that can hold neither is known before anything is done")
out = gf.build(F3, "Copies", tracks, mode="link")
chk(out["files"] == 0 and len(out["failed"]) == 3 and [n for n in os.listdir(F3) if n.endswith((".flac", ".mp3", ".wav"))] == [],
    "asked not to copy, it copies nothing")
out = gf.build(F3, "Copies", tracks, mode="copy")
cp = F3 / "01 Someone - Alpha.flac"
chk(out["files"] == 3 and out["copied"] == 3 and not os.path.samefile(cp, A) and cp.read_bytes() == A.read_bytes() and not cp.is_symlink()
    and gf.status(F3)["how"] == {"copy": 3}, "asked to copy, it makes real second files")
chk({p: sig(p) for p in (A, B, C, D)} == BEFORE, "…and still the originals are exactly as they were")
os.link, os.symlink = real_link, real_symlink
cp.write_bytes(b"a DJ program wrote its own tags into this copy")
os.utime(cp, (1, 1))
out = gf.build(F3, "Copies", tracks[1:], mode="copy")
chk(cp.exists() and out["kept"] == ["01 Someone - Alpha.flac"] and (F3 / "01 Someone - Beta_ Part 1_2.mp3").exists(),
    "a copy that was changed since it was made is the user's now: it is left where it is")

# ─── taking a folder away ───
chk(gf.remove(F2) is True and not F2.exists() and A.exists() and B.exists(), "a folder of links goes away whole; the records stay")
chk(gf.remove(F3) is False and F3.exists(), "copies are not thrown away with it unless asked")
chk(gf.remove(F) is False and sorted(n for n in os.listdir(F) if not n.startswith(".")) == ["04 Someone - Beta.mp3", "my own notes.txt"]
    and all(os.stat(p).st_nlink == 1 for p in (A, B, C, D)) and {p: sig(p) for p in (A, B, C, D)} == BEFORE,
    "a folder that also holds the user's own files loses only what we put there; the records are listed once again, unchanged")
chk(gf.remove(TMP / "nothing-here") is False and gf.read_manifest(LIB) is None, "a folder this code didn't make is never touched")

# ─── the routes, on a fresh database ───
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database(); migrate.run_migration()
    import app as mr
c = mr.app.test_client()
from mr_paths import DB_PATH
locked = TMP / "borrowed.mrb"; locked.write_bytes(b"z" * 64)
db = sqlite3.connect(DB_PATH)
for tid, title, path, status in ((1, "Alpha", A, None), (2, "Beta", B, None), (3, "Gamma", C, None), (4, "Borrowed", locked, "locked"), (5, "Gone", TMP / "not-there.flac", None)):
    db.execute("INSERT INTO tracks (id, title, artist_name, label, artwork_source) VALUES (?, ?, 'Someone', 'Good Label', 'not_found')", (tid, title))
    db.execute("INSERT INTO files (id, track_id, file_path, is_primary, duration_sec, analysis_status) VALUES (?, ?, ?, 1, ?, ?)", (10 + tid, tid, str(path), 100.0 * tid, status))
db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('library_dest', ?)", (str(LIB),))
db.commit(); db.close()
J = lambda r: r.get_json()
gid = J(c.post("/api/grupa", json={"name": "Set: Tuesday"}))["id"]
ids = [J(c.post(f"/api/grupa/{gid}/items", json={"kind": "track", "ref_id": t}))["item"]["id"] for t in (1, 2, 3, 4, 5)]
c.post(f"/api/grupa/{gid}/items", json={"url": "https://soundcloud.com/forss/flickermood"})
d = J(c.get(f"/api/grupa/{gid}/folder"))
chk(d["folder"] is None and d["plan"]["count"] == 3 and d["plan"]["seconds"] == 600 and d["plan"]["bytes"] == 3 * 4096
    and d["plan"]["left_out"] == {"streams": 1, "borrowed": 1, "missing": 1, "other": 0} and d["plan"]["where"] == "library",
    "before: three of its records are files here; a stream, a borrowed record and a missing file are counted as left out")
WANT = LIB.parent / "Music Room — Grúpaí" / "Set_ Tuesday"
r = c.post(f"/api/grupa/{gid}/folder", json={})
o = J(r)
chk(r.status_code == 200 and o["folder"] == str(WANT) and o["same"] == 3 and o["copied"] == 0 and o["mode"] == "link"
    and sorted(n for n in os.listdir(WANT) if n[0].isdigit()) == ["01 Someone - Alpha.flac", "02 Someone - Beta.mp3", "03 Someone - Gamma.wav"],
    "made: beside the library, named after the grúpa, in order, nothing copied")
d = J(c.get(f"/api/grupa/{gid}/folder"))
chk(d["folder"]["folder"] == str(WANT) and d["folder"]["stale"] is False and d["folder"]["how"] == {"same": 3}, "the grúpa knows its folder, and that it is up to date")
c.post(f"/api/grupa/{gid}/order", json={"ids": [ids[2], ids[0], ids[1], ids[3], ids[4]]})
chk(J(c.get(f"/api/grupa/{gid}/folder"))["folder"]["stale"] is True, "reordered, the folder is known to be behind")
c.post(f"/api/grupa/{gid}/folder", json={})
chk(sorted(n for n in os.listdir(WANT) if n[0].isdigit()) == ["01 Someone - Gamma.wav", "02 Someone - Alpha.flac", "03 Someone - Beta.mp3"]
    and J(c.get(f"/api/grupa/{gid}/folder"))["folder"]["stale"] is False, "made again, it follows the new order")
c.patch(f"/api/grupa/{gid}", json={"name": "Deep listening, Tuesday"})
chk(J(c.get(f"/api/grupa/{gid}/folder"))["folder"]["stale"] is True, "renamed, the folder is behind too")
o = J(c.post(f"/api/grupa/{gid}/folder", json={}))
NEW = WANT.parent / "Deep listening, Tuesday"
chk(o["folder"] == str(NEW) and NEW.is_dir() and not WANT.exists() and (NEW / "Deep listening, Tuesday.m3u8").exists() and not (NEW / "Set_ Tuesday.m3u8").exists(),
    "…and making it again moves the folder to the new name")
opened = []
real_popen = mr.subprocess.Popen
mr.subprocess.Popen = lambda cmd, **k: opened.append(cmd)
chk(c.post(f"/api/grupa/{gid}/folder/show").status_code == 200 and opened == [["open", str(NEW)]], "“Show the folder” opens it in Finder")
mr.subprocess.Popen = real_popen
g2 = J(c.post("/api/grupa", json={"name": "Taken"}))["id"]
c.post(f"/api/grupa/{g2}/items", json={"kind": "track", "ref_id": 1})
(NEW.parent / "Taken").mkdir(); (NEW.parent / "Taken" / "someone else's.txt").write_text("x")
r = c.post(f"/api/grupa/{g2}/folder", json={})
chk(r.status_code == 409 and "didn't make" in J(r)["error"] and os.listdir(NEW.parent / "Taken") == ["someone else's.txt"]
    and c.post(f"/api/grupa/{g2}/folder/show").status_code == 404, "a folder of that name that the app didn't make is left alone")
g3 = J(c.post("/api/grupa", json={"name": "Only streams"}))["id"]
c.post(f"/api/grupa/{g3}/items", json={"url": "https://soundcloud.com/forss/flickermood"})
chk(c.post(f"/api/grupa/{g3}/folder", json={}).status_code == 400 and J(c.get(f"/api/grupa/{g3}/folder"))["plan"]["count"] == 0,
    "a grúpa with no files of your own has nothing to put in a folder")
# the disk can't link: nothing is done until copies are asked for
real_can = gf.can_link
gf.can_link = lambda folder, src: None
g4 = J(c.post("/api/grupa", json={"name": "On a stick"}))["id"]
for t in (1, 2):
    c.post(f"/api/grupa/{g4}/items", json={"kind": "track", "ref_id": t})
r = c.post(f"/api/grupa/{g4}/folder", json={})
chk(r.status_code == 409 and J(r)["needs_copy"] is True and J(r)["count"] == 2 and J(r)["bytes"] == 2 * 4096 and not (NEW.parent / "On a stick").exists(),
    "a disk that can't hold a record without copying it: nothing is made, and the answer says how much copying it would be")
o = J(c.post(f"/api/grupa/{g4}/folder", json={"mode": "copy"}))
gf.can_link = real_can
chk(o["copied"] == 2 and o["mode"] == "copy" and J(c.get(f"/api/grupa/{g4}/folder"))["folder"]["how"] == {"copy": 2}
    and J(c.get(f"/api/grupa/{g4}/folder"))["folder"]["bytes"] == 2 * 4096, "asked for, the copies are made and counted")
# deleting a grúpa takes its folder of links with it — never a record
c.delete(f"/api/grupa/{gid}")
chk(not NEW.exists() and {p: sig(p) for p in (A, B, C, D)} == BEFORE and all(os.stat(p).st_nlink == 1 for p in (A, B, C)),
    "a deleted grúpa's folder goes with it; every record is still in the library, untouched, listed once")
c.delete(f"/api/grupa/{g4}")
chk((NEW.parent / "On a stick" / "01 Someone - Alpha.flac").exists(), "…but copies are left for the user to throw away")

print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
sys.stdout.flush()
os._exit(1 if fails else 0)
