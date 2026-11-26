"""Accounts, the app's side (green_room.py + gr_people_app.py against a real rooms
server): a new account is made with an email and a password and the laptop stays
signed in; the password is kept nowhere on the laptop and is never sent to an
address that isn't private; signing in again asks for what the account needs; a
label manages an artist's records as itself and only where it was let in; the
what's-new note shows once, and never on a new install.
Run:  ./venv/bin/python test_gr_people_app.py"""
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_server.db")
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")
os.environ.pop("MR_GR_SERVER", None)
(TMP / "app_data").mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import gr_server
import gr_master
import gr_signin

with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
def sql(q, *p):
    with closing(gr_server.db()) as c:
        return c.execute(q, p).fetchall()

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
def kept(key):
    with closing(appdb()) as x:
        r = x.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else ""
def leave():
    with closing(appdb()) as x:
        x.execute("DELETE FROM settings WHERE key IN ('gr_token','gr_name','gr_acting_for','gr_acting_name','gr_acting_scope')"); x.commit()

import green_room
import gr_people_app
PW = "a-long-enough-password"

# ── a new account: an email and a password; the laptop is signed in and stays so ──
for bad in ({"email": "", "password": PW}, {"email": "label@example.ie", "password": ""}):
    try:
        green_room.signup(SERVER, "Moss Records", "test laptop", agreed=True, **bad); chk(False, "sign-up needs both an email and a password")
    except green_room.GRError:
        chk(not kept("gr_token"), "sign-up needs both an email and a password")
out = green_room.signup(SERVER, "Moss Records", "test laptop", kind="label", agreed=True, email="label@example.ie", password=PW)
chk(out["joined"] and kept("gr_token") and not out["invite_code"] and not kept("gr_invite_code"), "the account is made and the laptop signed in; there is no account code to keep")
with closing(appdb()) as x:
    everything = " ".join(str(v) for row in x.execute("SELECT key, value FROM settings") for v in row)
chk(PW not in everything, "the password is kept nowhere on the laptop")
me = green_room.status()["me"]
chk(me["kind"] == "listener" and me["apply"]["interest"] == "label" and me["signin"]["has_password"] and me["apply"]["can_apply"],
    "saying 'a label' at the front door makes a listener, with the note the app uses to show the way to apply")
token = kept("gr_token")
chk(green_room.status()["joined"] and kept("gr_token") == token, "asked again later, the app is still signed in with the same sign-in (nothing to type)")

# ── a password never goes to an address that isn't private ──
for call, name in ((lambda: green_room.login("http://192.168.1.20:5300", "label@example.ie", PW), "sign-in"),
                   (lambda: green_room.signup("http://some-mac.local:5300", "X", agreed=True, email="x@example.ie", password=PW), "sign-up")):
    try:
        call(); chk(False, f"{name}: a password is not sent over plain http to another computer")
    except green_room.GRError as e:
        chk("not private" in str(e), f"{name}: a password is not sent over plain http to another computer")
chk(green_room._safe_for_a_password("https://musicroom.example") and green_room._safe_for_a_password("http://127.0.0.1:5300")
    and not green_room._safe_for_a_password("http://musicroom.example"), "https, or a server on this computer, and nothing else")

# ── signing in again ──
leave()
try:
    green_room.login(SERVER, "label@example.ie", "not-the-password"); chk(False, "a wrong password is refused")
except green_room.GRError as e:
    chk(not kept("gr_token") and "don't match" in str(e), "a wrong password is refused, in the server's words")
gr_master._rate.clear()
chk(green_room.login(SERVER, "Label@Example.ie", PW)["joined"] and kept("gr_token") == token, "the right one signs the laptop back in")

# ── two-factor at the front door ──
with closing(gr_server.db()) as c:
    lid = c.execute("SELECT id FROM gr_accounts WHERE name='Moss Records'").fetchone()[0]
    c.execute("UPDATE gr_accounts SET kind='label' WHERE id=?", (lid,)); c.commit()
code, d = green_room.shop_call("POST", "/api/me/2fa/start", {})
key = d["key"]
code, d = green_room.shop_call("POST", "/api/me/2fa/confirm", {"code": gr_signin.totp(key, int(time.time() // 30))})
chk(code == 200 and d["two_factor"]["on"], "two-factor is switched on from the app")
with closing(gr_server.db()) as c:
    c.execute("DELETE FROM gr_devices WHERE account_id=?", (lid,)); c.execute("UPDATE gr_accounts SET totp_last=0 WHERE id=?", (lid,)); c.commit()
leave(); gr_master._rate.clear()
try:
    green_room.login(SERVER, "label@example.ie", PW); chk(False, "a new laptop is asked for the six numbers")
except green_room.GRError as e:
    chk(getattr(e, "need_2fa", False) and not kept("gr_token"), "a new laptop is asked for the six numbers, and the front door is told to ask")
chk(green_room.login(SERVER, "label@example.ie", PW, otp=gr_signin.totp(key, int(time.time() // 30)))["joined"], "with them, it is signed in")

# ── a label manages an artist's releases, as itself ──
gr_server.make_invite("Órla", kind="artist", handle="orla")
oid = sql("SELECT id FROM gr_accounts WHERE handle='orla'")[0][0]
try:
    green_room.act_for("orla"); chk(False, "the app can't be pointed at an account that hasn't let it in")
except green_room.GRError:
    chk(not kept("gr_acting_for"), "the app can't be pointed at an account that hasn't let it in")
with closing(gr_server.db()) as c:
    c.execute("INSERT INTO gr_behalf(owner_id, delegate_id, scope, granted_at) VALUES(?,?,?,?)", (oid, lid, "records", gr_server._now())); c.commit()
a = green_room.act_for("orla")
chk(a == {"handle": "orla", "name": "Órla", "scope": "records"} and green_room.acting_for() == a, "let in, the app switches to managing the artist's releases")
with closing(appdb()) as x:
    heads = {p: green_room._headers(x, p) for p in ("/api/my/records", "/api/my/records/7", "/api/my/room", "/api/me", "/api/my/happenings", "/api/borrow", "")}
chk(heads["/api/my/records"].get("X-GR-For") == "orla" and heads["/api/my/records/7"].get("X-GR-For") == "orla"
    and not any("X-GR-For" in heads[p] for p in ("/api/my/room", "/api/me", "/api/my/happenings", "/api/borrow", "")),
    "only the calls about records say they are for the artist; everything else is the label's own")
import audio_fixture
audio_fixture.make_flac(TMP / "one.flac", seed=3, seconds=1, title="Slow Tide", artist="Órla")
r = green_room.upload_record(("one.flac", (TMP / "one.flac").read_bytes(), "audio/flac"), None, {"rights": "1", "title": "Slow Tide"})
t = sql("SELECT owner_account_id, title FROM gr_tracks ORDER BY id DESC LIMIT 1")
chk(bool(t) and t[0]["owner_account_id"] == oid, "a record the label puts up while managing is the ARTIST's record")
chk([x["title"] for x in green_room.my_records()["records"]] == [t[0]["title"]] and green_room.my_room()["handle"] == "moss-records",
    "the Records list is the artist's; the room is still the label's own")
log = [json.loads(e["data"]) for e in sql("SELECT data FROM gr_events WHERE kind='behalf' AND account_id=?", oid)]
chk(len(log) == 1 and log[0]["by_handle"] == "moss-records" and log[0]["for"] == oid, "what the label did is in the artist's log, under the label's name")
green_room.act_for("")
chk(green_room.acting_for() is None and green_room.my_records()["records"] == [], "stopped, the app is back on the label's own records")
with closing(appdb()) as x:
    x.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('gr_acting_for', 'orla')"); x.commit()
leave()
chk(green_room.acting_for() is None, "signing out forgets whose account was being managed")

# ── which questions the pages may pass on ──
ok = ("me/security", "me/password", "me/devices/3/out", "me/2fa/start", "me/2fa/confirm", "me/2fa/off", "apply", "apply/withdraw",
      "me/interest", "my/happenings", "my/happenings/4", "my/behalf", "my/behalf/2", "happenings", "me/email/verify/confirm")
no = ("master/overview", "master/applications", "me", "borrow", "my/records", "me/devices/3", "apply/../master/rules", "sim/me", "")
chk(all(gr_people_app._SUB.match(s) for s in ok) and not any(gr_people_app._SUB.match(s) for s in no),
    "the account pages reach only their own questions on the server — never the master's")

# ── what's new: once, after an update, and never on a new install ──
base = TMP / "appcode"; (base / "static" / "data").mkdir(parents=True)
(base / "static" / "data" / "whats_new.json").write_text(json.dumps({"notes": [
    {"version": "2026.12.01", "title": "Experience creators", "words": ["A new kind of account."], "go": "/apply?kind=experience%20creator"},
    {"version": "2026.12.02", "title": "Outside", "words": [], "go": "https://elsewhere.example/"}]}), encoding="utf-8")
n = gr_people_app.whats_new(str(base), "2026.12.01", "2026.11.26")
chk(n and n["title"] == "Experience creators" and n["go"] == "/apply?kind=experience%20creator" and n["go_label"] == "Show me",
    "opened for the first time after an update, the version's note is there, with where it leads")
chk(gr_people_app.whats_new(str(base), "2026.12.01", "2026.12.01") is None, "once seen, it is not shown again")
chk(gr_people_app.whats_new(str(base), "2026.12.01", "") is None, "a new install is shown nothing: it has only known this version")
chk(gr_people_app.whats_new(str(base), "2026.12.03", "2026.12.01") is None, "a version with no note says nothing")
chk(gr_people_app.whats_new(str(base), "2026.12.02", "2026.12.01")["go"] == "", "a note can only lead to a page inside the app")
shipped = json.loads((Path(__file__).resolve().parent / "static" / "data" / "whats_new.json").read_text(encoding="utf-8"))
chk(shipped["notes"] == [], "the list the app ships with is empty for now: nothing is announced")

srv.shutdown()
print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
