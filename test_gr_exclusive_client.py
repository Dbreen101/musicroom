"""Exclusive records, the app's side (green_room.py against a real rooms server): bought, an
exclusive record stays a LOCKED file in the room — never a plain one — and is marked as kept;
bought without bringing it home first, the locked copy arrives; an ordinary record still becomes
a plain file. Run:  ./venv/bin/python test_gr_exclusive_client.py"""
import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import threading
import wave
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_server.db")
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")
(TMP / "app_data").mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import gr_server
import gr_master

music = TMP / "music"; music.mkdir()
def make(name, fill):
    p = music / name
    with wave.open(str(p), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(fill * 2000)
    return p
a, b, c = make("only one.wav", b"\x01\x02"), make("only two.wav", b"\x03\x04"), make("plain.wav", b"\x05\x06")
with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
gr_server.add_folder(str(music))
gr_master.make_master("Master", handle="master")
with closing(gr_server.db()) as conn:
    conn.execute("UPDATE gr_settings SET value=value")      # (the table is there)
    ids = {r["filename"]: r["id"] for r in conn.execute("SELECT id, filename FROM gr_tracks")}
    conn.execute("UPDATE gr_tracks SET exclusive=1 WHERE filename LIKE 'only%'")
    conn.commit()
code = gr_server.make_invite("Listener")

from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, gr_server.app)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SERVER = f"http://127.0.0.1:{srv.server_port}"

import mr_paths
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database(); migrate.run_migration()
def appdb():
    x = sqlite3.connect(mr_paths.DB_PATH); x.row_factory = sqlite3.Row; return x

import green_room
green_room.join(SERVER, code, "test laptop")
green_room.choose_plan("a")

# ── brought home, then bought ──
one = ids["only one.wav"]
got = green_room.borrow(one)
chk(got["exclusive"] == 1 and got["kept"] == 0 and Path(got["file_path"]).read_bytes() != a.read_bytes(),
    "an exclusive record brought home: a locked file, marked exclusive")
locked_path = got["file_path"]
out = green_room.buy(got["id"])
chk(out["bought"] and out["exclusive"] and "path" not in out, "bought: nothing plain arrives")
with closing(appdb()) as x:
    row = x.execute("SELECT * FROM gr_borrows WHERE id=?", (got["id"],)).fetchone()
    t = x.execute("SELECT * FROM tracks WHERE id=?", (row["track_id"],)).fetchone()
    f = x.execute("SELECT * FROM files WHERE track_id=?", (row["track_id"],)).fetchone()
chk(row["kept"] == 1 and row["returned_at"] is None and row["file_path"] == locked_path and os.path.exists(locked_path),
    "the locked copy is still there, now kept")
chk(t["gr_borrow_id"] == got["id"] and f["analysis_status"] == "locked" and f["file_path"] == locked_path,
    "in the room it is still a locked record (so it can't be exported, tagged or played outside)")
chk(green_room.decrypt_file(locked_path, row["key_hex"], row["nonce_hex"]) == a.read_bytes(), "it still plays (the app can unlock it in memory)")
bought_dir = green_room._purchase_dir(appdb())
chk(not any(p.suffix == ".wav" for p in bought_dir.rglob("*")) if bought_dir.exists() else True, "no plain file was written anywhere")
info = green_room.borrow_of_track(row["track_id"])
chk(info["kept"] == 1 and info["exclusive"] == 1, "the record's panel is told: exclusive, yours")

# ── bought outright, never brought home ──
two = ids["only two.wav"]
out = green_room.buy_track(two)
chk(out["bought"] and out["exclusive"] and out["track_id"], "bought outright: it arrives in the room")
with closing(appdb()) as x:
    row2 = x.execute("SELECT * FROM gr_borrows WHERE server_track_id=? AND returned_at IS NULL", (two,)).fetchone()
    f2 = x.execute("SELECT * FROM files WHERE track_id=?", (row2["track_id"],)).fetchone()
chk(row2["kept"] == 1 and row2["exclusive"] == 1 and f2["analysis_status"] == "locked" and os.path.exists(row2["file_path"])
    and Path(row2["file_path"]).read_bytes() != b.read_bytes(), "…as a locked copy, kept, never the plain file")

# ── an ordinary record is as before ──
out = green_room.buy_track(ids["plain.wav"])
chk(out["bought"] and not out.get("exclusive") and Path(out["path"]).read_bytes() == c.read_bytes(), "an ordinary record still arrives as a plain file")

# ── a library from before the two columns ──
with closing(appdb()) as x:
    x.executescript("ALTER TABLE gr_borrows DROP COLUMN exclusive; ALTER TABLE gr_borrows DROP COLUMN kept;"); x.commit()
green_room.give_back(row2["id"])
again = green_room.borrow(two)
chk(again["kept"] == 1 and again["exclusive"] == 1, "an older library gets the columns; a bought exclusive comes back, free and kept")

srv.shutdown()
print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
