"""A rooms server that people reach from outside the building (through a tunnel, or on a
hosted machine behind a relay): the master's page still answers only on the server's own
computer, limits count the visitor's real address, a new account can need an invite code,
the server can say it has moved and apps follow, and what a person plays in their own
room is never kept. Run:  ./venv/bin/python test_gr_hosted.py"""
import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import threading
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "hosted.db")
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")
os.environ.pop("MR_MASTER_ANYWHERE", None)
(TMP / "app_data").mkdir()

import gr_server
import gr_master

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
def hdr(tok, **more): return dict({"Authorization": f"Bearer {tok}"}, **more)
def sql(q, *p):
    with closing(gr_server.db()) as c:
        out = c.execute(q, p).fetchall(); c.commit(); return out

with closing(gr_server.db()) as c:
    gr_server.init_db(c)
gr_master.make_master("Master", handle="master")
import gr_signin; gr_signin.set_rules_here({"master_2fa": "off"})   # (the master's two-factor has its own test: test_gr_signin.py)
client = gr_server.app.test_client()
code = sql("SELECT invite_code FROM gr_accounts WHERE handle='master'")[0][0]
master = client.post("/api/join", json={"invite_code": code, "fingerprint": "mac-master", "device_name": "laptop"}).get_json()["token"]
FAR = {"REMOTE_ADDR": "203.0.113.9"}                 # a laptop somewhere else, straight in
def signup(name, **kw):
    body = dict({"name": name, "fingerprint": "fp-" + name, "agreed": True}, **kw.pop("json", {}))
    return client.post("/api/signup", json=body, **kw)

# ═══ the master's page: only on the server's own computer ═══
chk(client.get("/api/master/overview", headers=hdr(master)).status_code == 200,
    "the master's own app, beside the server, is answered")
chk(client.get("/api/master/overview", headers=hdr(master), environ_base=FAR).status_code == 403,
    "the master's code from another laptop is not")
for name, h in (("a tunnel or a proxy (X-Forwarded-For)", {"X-Forwarded-For": "198.51.100.7"}),
                ("a relay that says only which name was asked for", {"X-Forwarded-Host": "rooms.example.org"}),
                ("Cloudflare's tunnel", {"CF-Connecting-IP": "198.51.100.7"}),
                ("a relay naming itself (Via)", {"Via": "1.1 caddy"})):
    r = client.get("/api/master/overview", headers=hdr(master, **h))
    chk(r.status_code == 403, f"through {name}, a visitor arrives from 127.0.0.1 and is still not answered")
r = client.get("/api/master/overview", headers=hdr(master), base_url="https://rooms.example.org")
chk(r.status_code == 403, "nor is a request that asks for the server by an outside name, whatever it carries")
chk(client.get("/api/master/overview", headers=hdr(master), base_url="http://127.0.0.1:5300").status_code == 200
    and client.get("/api/master/overview", headers=hdr(master), base_url="http://[::1]:5300").status_code == 200,
    "asked for as 127.0.0.1:5300 or [::1]:5300, it is")
r = client.post("/api/master/door", json={"code": "let me in"}, headers=hdr(master, **{"X-Forwarded-For": "198.51.100.7"}))
chk(r.status_code == 403 and gr_master.door(gr_server.db())["code"] == "", "and nothing of the master's can be changed through a relay")
os.environ["MR_MASTER_ANYWHERE"] = "1"
chk(client.get("/api/master/overview", headers=hdr(master, **{"X-Forwarded-For": "198.51.100.7"})).status_code == 200,
    "MR_MASTER_ANYWHERE=1 lifts it, for a server whose master can't sit beside it")
os.environ.pop("MR_MASTER_ANYWHERE")

# ═══ whose address counts ═══
with gr_server.app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"},
                                        headers={"X-Forwarded-For": "10.0.0.1, 198.51.100.7"}):
    chk(gr_master.asker() == "198.51.100.7", "through a relay, the address is the one the relay itself wrote down (the last)")
with gr_server.app.test_request_context("/", environ_base=FAR, headers={"X-Forwarded-For": "127.0.0.1"}):
    chk(gr_master.asker() == "203.0.113.9", "a visitor who comes straight in can't claim another address")
with gr_server.app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
    chk(gr_master.asker() == "127.0.0.1", "with no relay, this computer is this computer")

gr_master._rate.clear()
via = lambda ip: {"headers": {"X-Forwarded-For": ip}}
got = [signup(f"Tunnel {i}", **via("198.51.100.7")).status_code for i in range(gr_master.SIGNUPS_PER_HOUR + 1)]
chk(got[:-1] == [200] * gr_master.SIGNUPS_PER_HOUR and got[-1] == 429,
    "through a relay, one address still gets only so many new accounts an hour")
chk(signup("Someone Else", **via("198.51.100.8")).status_code == 200,
    "and somebody at another address is not shut out by them (everyone used to share one count)")

# ═══ an invite code for new accounts ═══
gr_master._rate.clear()
v = client.get("/api/version").get_json()
chk(v["invite"] is False and v["moved_to"] == "", "a server says whether it needs an invite code, and whether it has moved")
r = client.post("/api/master/door", json={"code": "abc"}, headers=hdr(master))
chk(r.status_code == 400, "an invite code of three letters is refused")
r = client.post("/api/master/door", json={"code": "Green Room 2026"}, headers=hdr(master))
chk(r.status_code == 200 and r.get_json()["code"] == "Green Room 2026", "the master sets one")
v = client.get("/api/version")
chk(v.get_json()["invite"] is True and "Green Room" not in v.get_data(as_text=True),
    "the server then says one is needed, and never says what it is")
r = signup("No Code")
chk(r.status_code == 403 and r.get_json().get("need_code") is True, "no account is made without it")
r = signup("Wrong Code", json={"door_code": "green room 2025"})
chk(r.status_code == 403 and r.get_json().get("need_code") is True, "nor with a wrong one")
chk(not sql("SELECT 1 FROM gr_accounts WHERE name IN ('No Code','Wrong Code')"), "(and none was)")
r = signup("Right Code", json={"door_code": "  greenroom2026 "})
chk(r.status_code == 200 and r.get_json().get("token"), "with it — capitals and spaces aside — the account is made")
chk(client.post("/api/join", json={"invite_code": code, "fingerprint": "mac-master-2"}).status_code == 200,
    "someone who already has an account signs in with their own account code, as before")
gr_master._rate.clear()
got = [signup(f"Guess {i}", json={"door_code": f"guess-{i:04d}"}, **via("198.51.100.20")).status_code for i in range(13)]
chk(got[:12] == [403] * 12 and got[12] == 429, "guesses at the code are counted per address, twelve in ten minutes")
r = signup("Meanwhile", json={"door_code": "Green Room 2026"}, **via("198.51.100.21"))
chk(r.status_code == 200, "and a person elsewhere with the right code is not held up by them")
gr_master._rate.clear()
got = [signup(f"Fellow {i}", json={"door_code": "Green Room 2026"}, **via("198.51.100.40")).status_code for i in range(20)]
chk(got == [200] * 20, "twenty people with the right code behind ONE address (a building's Wi-Fi, through a tunnel) all get in")
chk(signup("One Slip", json={"door_code": "green room 2062"}, **via("198.51.100.40")).status_code == 403
    and signup("Then Right", json={"door_code": "Green Room 2026"}, **via("198.51.100.40")).status_code == 200,
    "only wrong codes are counted: a slip of the fingers doesn't use up the right ones")
client.post("/api/master/door", json={"code": ""}, headers=hdr(master))
gr_master._rate.clear()
chk(signup("Open Again").status_code == 200, "with the code cleared, anyone who reaches the server can make an account again")

# ═══ the server says it has moved ═══
r = client.post("/api/master/door", json={"moved_to": "http://plain.example.org"}, headers=hdr(master))
chk(r.status_code == 400, "a new address that isn't https:// is refused")
r = client.post("/api/master/door", json={"moved_to": "https://rooms.example.org/"}, headers=hdr(master))
chk(r.status_code == 200 and client.get("/api/version").get_json()["moved_to"] == "https://rooms.example.org",
    "the master says where the server lives now, and it tells every app that asks")
chk(gr_master.door(gr_server.db())["code"] == "", "(changing one thing at the door leaves the other as it was)")

# ═══ what you play in your own room is not kept ═══
tok = signup("Listener", **via("198.51.100.30")).get_json()["token"]
r = client.post("/api/events", headers=hdr(tok), json={"events": [
    {"kind": "play", "data": {"title": "A record of my own", "artist": "Me"}}, {"kind": "theme", "data": {"id": "ink"}}]})
kinds = [x[0] for x in sql("SELECT kind FROM gr_events WHERE account_id=(SELECT id FROM gr_accounts WHERE name='Listener')")]
chk(r.get_json()["stored"] == 1 and "play" not in kinds and "theme" in kinds,
    "an older app still sends each play: the server drops it and keeps the rest")

# ═══ a database from before any of this ═══
os.environ["MR_GR_DB"] = str(TMP / "older.db")
with closing(gr_server.db()) as c:
    gr_server.init_db(c)
    c.execute("DELETE FROM gr_settings WHERE key='door'"); c.commit()
gr_master._rate.clear()
chk(client.get("/api/version").get_json()["invite"] is False and signup("Early Bird").status_code == 200,
    "a server that was never given a code or a new address behaves as it always did")
os.environ["MR_GR_DB"] = str(TMP / "hosted.db")

# ═══ the app's side ═══
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
def app_setting(k):
    with closing(appdb()) as x:
        r = x.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        return r[0] if r else None

import green_room
client.post("/api/master/door", json={"code": "Green Room 2026", "moved_to": ""}, headers=hdr(master))
gr_master._rate.clear()
try:
    green_room.signup(SERVER, "App Person", "test laptop", agreed=True, email="app@example.ie", password="a-password-to-test")
    chk(False, "the app is told when a code is needed")
except green_room.GRError as e:
    chk(getattr(e, "need_code", False) is True and not app_setting("gr_token"),
        "the app is told when a code is needed, and is not signed in")
green_room.signup(SERVER, "App Person", "test laptop", agreed=True, door_code="green room 2026", email="app@example.ie", password="a-password-to-test")
chk(bool(app_setting("gr_token")) and app_setting("gr_server_url") == SERVER, "with the code, the app signs up")

green_room.track("play", {"title": "Mine"})
green_room.track("theme", {"id": "ink"})
with closing(appdb()) as x:
    waiting = [r[0] for r in x.execute("SELECT kind FROM gr_events_outbox")]
chk("play" not in waiting and "theme" in waiting, "the app no longer notes a play for the server at all")

# the server moves: the app follows only to an https address that accepts its own sign-in
NEW = "https://rooms.example.org"
real_get, asked = green_room.requests.get, []
def fake_get(url, **kw):
    asked.append(url)
    if url.startswith(NEW):
        return real_get(SERVER + url[len(NEW):], **kw)                # the same Music Room, at its new address
    if url.startswith("https://someone-else.example.org"):
        r = real_get(SERVER + "/api/me", **dict(kw, headers={}))       # a stranger's server: doesn't know this sign-in
        return r
    return real_get(url, **kw)
green_room.requests.get = fake_get
chk(green_room.follow_move(NEW) is False and app_setting("gr_server_url") == SERVER,
    "an app that talks to a server on its own computer stays where it is (the master's own app)")
with closing(appdb()) as x:
    x.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('gr_server_url', 'http://old-mac.local:5300')"); x.commit()
OLD = "http://old-mac.local:5300"
chk(green_room.follow_move("http://rooms.example.org") is False and app_setting("gr_server_url") == OLD,
    "the app never follows to an address that isn't https://")
chk(green_room.follow_move("https://someone-else.example.org") is False and app_setting("gr_server_url") == OLD,
    "nor to an address that doesn't know its sign-in")
chk(green_room.follow_move("https://nowhere.invalid") is False and app_setting("gr_server_url") == OLD,
    "nor to one that doesn't answer")
chk(green_room.follow_move(NEW + "/") is True and app_setting("gr_server_url") == NEW
    and app_setting("gr_server_url_before") == OLD,
    "to the same Music Room at its new address, it moves (and remembers where it was)")
chk(green_room.follow_move(NEW) is False, "told again, there is nothing to do")

# ═══ the way back: the new address stops answering, the one before still does ═══
import requests as _rq
world = {"new": "up", "old": "same"}      # new: up | down    old: same | away | stranger | liar | yes-man | older
sent_old = []                             # everything asked of the address before, with its headers
def fake_world(url, **kw):
    if url.startswith(NEW):
        if world["new"] == "down":
            raise _rq.ConnectionError("the tunnel is down")
        return real_get(SERVER + url[len(NEW):], **kw)
    if url.startswith(OLD):
        sent_old.append((url[len(OLD):], dict(kw.get("headers") or {})))
        how = world["old"]
        if how == "away":
            raise _rq.ConnectionError("nothing at that name on this Wi-Fi")
        if how == "same":
            return real_get(SERVER + url[len(OLD):], **kw)
        if how == "older":                 # the same Music Room on a release from before /api/knows
            return real_get(SERVER + "/api/no-such-thing", **{k: v for k, v in kw.items() if k != "params"})
        r = real_get(SERVER + "/api/version", timeout=5)           # some other server answering at that name
        body = {"stranger": {"proofs": []}, "liar": {"proofs": ["0" * 64]}, "yes-man": {"proofs": "yes", "ok": True}}[how]
        r._content = __import__("json").dumps(body).encode()
        return r
    return real_get(url, **kw)
green_room.requests.get = fake_world
def where(): return app_setting("gr_server_url"), app_setting("gr_server_url_before")
def token_sent(): return any("Authorization" in h for _, h in sent_old)

chk(green_room.go_back() is False and where() == (NEW, OLD) and not sent_old,
    "while the new address answers, the app stays there and asks nothing of the old one")
world["new"] = "down"
for how, words in (("away", "the old address doesn't answer either (a laptop away from the building)"),
                   ("stranger", "another server answers at the old name and doesn't know this laptop"),
                   ("liar", "another server answers with a made-up proof"),
                   ("yes-man", "another server says yes to everything"),
                   ("older", "the old address runs a release from before the question existed")):
    world["old"] = how
    chk(green_room.go_back() is False and where() == (NEW, OLD), f"the new address is down and {words}: the app stays put")
chk(not token_sent(), "and through all of that the app's sign-in was never sent to the old address")
with closing(appdb()) as x:
    queued = x.execute("SELECT COUNT(*) FROM gr_events_outbox WHERE kind='server_back'").fetchone()[0]
chk(queued == 0, "and nothing was noted as a move")

world["old"] = "same"; sent_old.clear()
chk(green_room.go_back() is True and where() == (OLD, NEW),
    "the new address is down and the old one is the same Music Room: the app goes back (and remembers the new one)")
chk([p for p, _ in sent_old][:1] == ["/api/knows"] and "Authorization" not in sent_old[0][1] and token_sent(),
    "it asked for the proof first, without its sign-in, and used the sign-in only after the proof")
with closing(appdb()) as x:
    queued = x.execute("SELECT data FROM gr_events_outbox WHERE kind='server_back'").fetchall()
chk(len(queued) == 1 and NEW in queued[0][0] and OLD in queued[0][0], "going back is noted once, for the activity log")
chk(green_room.go_back() is False and where() == (OLD, NEW), "asked again while the tunnel is still down, it does not swing to and fro")
chk(green_room.follow_move(NEW) is False and where() == (OLD, NEW), "and it does not follow the server forward while the new address is down")
world["new"] = "up"
chk(green_room.follow_move(NEW) is True and where() == (NEW, OLD),
    "the tunnel comes back: the app follows the server forward again, as it did the first time")

# a call that gets no answer starts the look by itself, in the background, at most once a minute
world["new"] = "down"; sent_old.clear(); green_room._back["at"] = 0
try:
    green_room.shop_call("GET", "/api/version"); chk(False, "a call to a server that is down fails as before")
except green_room.GRError:
    chk(True, "a call to a server that is down fails as before")
green_room._back["thread"].join(20)
chk(where() == (OLD, NEW), "and a moment later the app has gone back by itself")
world["new"] = "up"; green_room.follow_move(NEW); world["new"] = "down"; sent_old.clear()
try: green_room.shop_call("GET", "/api/version")
except green_room.GRError: pass
t = green_room._back["thread"]; t and t.join(20)
chk(where() == (NEW, OLD) and not sent_old, "a second failure inside the same minute does not ask the old address again")
green_room._back["at"] = 0
try: green_room.flush_events() ; green_room.shop_call("POST", "/api/report", {})
except green_room.GRError: pass
green_room._back["thread"].join(20)
chk(where() == (OLD, NEW), "after the minute, the next failed call (of any kind) does")
world["new"] = "up"; green_room.follow_move(NEW)
chk(where() == (NEW, OLD), "(forward again for what follows)")

# ═══ stuck on a Wi-Fi address it is not on: the app tries the address its own build carries ═══
# (a fellow signed in on the building's Wi-Fi, then went home; a new download keeps the address the old app remembered)
HOME = "https://home.example.org"
home = {"is": "same"}                     # same | away | stranger
sent_home = []
def fake_home(url, **kw):
    if url.startswith(HOME):
        sent_home.append((url[len(HOME):], dict(kw.get("headers") or {})))
        if home["is"] == "away":
            raise _rq.ConnectionError("no way out to the internet")
        if home["is"] == "stranger":
            r = real_get(SERVER + "/api/version", timeout=5)
            r._content = b'{"proofs": []}'
            return r
        return real_get(SERVER + url[len(HOME):], **kw)
    if url.startswith("http://127.0.0.1:1/"):
        raise _rq.ConnectionError("nothing there")
    return fake_world(url, **kw)
green_room.requests.get = fake_home
def put(url, before=""):
    with closing(appdb()) as x:
        x.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('gr_server_url', ?)", (url,))
        x.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('gr_server_url_before', ?)", (before,)); x.commit()
def noted(kind):
    with closing(appdb()) as x:
        return x.execute("SELECT COUNT(*) FROM gr_events_outbox WHERE kind=?", (kind,)).fetchone()[0]

put(OLD); world["old"] = "away"; world["new"] = "up"
os.environ.pop("MR_GR_SERVER", None)
chk(green_room.go_back() is False and where() == (OLD, "") and not sent_home,
    "an app whose build carries no address, on a Wi-Fi address that is away, has nowhere to look")
os.environ["MR_GR_SERVER"] = "http://home.example.org"
chk(green_room.go_back() is False and where() == (OLD, ""), "an address in the build that isn't https:// is never tried")
os.environ["MR_GR_SERVER"] = HOME + "/"
world["old"] = "same"
chk(green_room.go_back() is False and where() == (OLD, "") and not sent_home,
    "while the remembered address answers, the app stays on it and asks nothing of the build's address")
world["old"] = "away"
for how in ("away", "stranger"):
    home["is"] = how
    chk(green_room.go_back() is False and where() == (OLD, ""),
        f"the remembered address is away and the build's address is {how}: the app stays put")
chk(not any("Authorization" in h for _, h in sent_home), "and its sign-in was not sent there")
home["is"] = "same"; sent_home.clear(); was = noted("server_found")
chk(green_room.go_back() is True and where() == (HOME, OLD),
    "the remembered Wi-Fi address is away and the build's address is the same Music Room: the app goes there (and remembers the Wi-Fi one)")
chk([p for p, _ in sent_home][:1] == ["/api/knows"] and "Authorization" not in sent_home[0][1],
    "it asked for the proof first, without its sign-in")
chk(noted("server_found") == was + 1, "and the move is noted once, for the activity log")
chk(green_room.go_back() is False and where() == (HOME, OLD), "asked again, there is nothing to do")

put("http://127.0.0.1:1"); sent_home.clear()
chk(green_room.go_back() is False and where() == ("http://127.0.0.1:1", "") and not sent_home,
    "an app whose server is on its own computer never leaves for the build's address (the master's own app, while its server restarts)")

put(NEW, OLD); world["new"] = "down"; world["old"] = "same"; sent_home.clear()
chk(green_room.go_back() is True and where() == (OLD, NEW) and not sent_home,
    "with an address from before that answers, that one is taken first")
put(NEW, OLD); world["old"] = "away"
chk(green_room.go_back() is True and where() == (HOME, NEW),
    "the address from before is away too: the build's address is next")

# signing in with an account code on a laptop that remembers a Wi-Fi address it is not on
real_post = green_room.requests.post
def fake_post(url, **kw):
    if url.startswith(OLD):
        raise _rq.ConnectionError("nothing at that name on this Wi-Fi")
    if url.startswith(HOME):
        return real_post(SERVER + url[len(HOME):], **kw)
    return real_post(url, **kw)
green_room.requests.post = fake_post
code = gr_server.make_invite("Code Person")      # (an account from before passwords: it still signs in with its code)
put(OLD)
try:
    green_room.join(OLD, "gr-not-a-real-code"); chk(False, "a wrong account code is refused through the build's address too")
except green_room.GRError as e:
    chk("didn't answer" not in str(e) and app_setting("gr_server_url") == OLD,
        "a wrong account code is refused through the build's address too, in the server's words")
gr_master._rate.clear()
chk(bool(code) and green_room.join(OLD, code).get("joined") is True and app_setting("gr_server_url") == HOME,
    "the right account code signs the laptop in through the build's address, and the app keeps that address")
os.environ.pop("MR_GR_SERVER", None)
try:
    green_room.join(OLD, code); chk(False, "with no address in the build, an address that doesn't answer says so")
except green_room.GRError as e:
    chk("didn't answer" in str(e), "with no address in the build, an address that doesn't answer says so")
green_room.requests.post = real_post
green_room.requests.get = fake_world
put(NEW, OLD); world["new"] = "up"; world["old"] = "same"; gr_master._rate.clear()

# the server's side of the question
with closing(appdb()) as x:
    fp, tok = (x.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()[0] for k in ("gr_fingerprint", "gr_token"))
gr_master._rate.clear()
ask = "a" * 32
r = client.get("/api/knows", query_string={"device": fp, "ask": ask}, environ_base=FAR)
# (this laptop has signed in to two accounts by now, so there are two proofs: the app's own sign-in makes one of them)
chk(r.status_code == 200 and gr_master.proof_of(tok, ask) == green_room._proof_of(tok, ask) and gr_master.proof_of(tok, ask) in r.get_json()["proofs"]
    and len(r.get_json()["proofs"]) == 2,
    "the server signs the words it is sent with that laptop's sign-in, and the app makes the same sum")
chk(tok not in r.get_data(as_text=True), "the answer does not hold the sign-in itself")
chk(client.get("/api/knows", query_string={"device": "nobody-knows-me", "ask": ask}, environ_base=FAR).get_json() == {"proofs": []},
    "a laptop the server doesn't know gets an empty answer")
chk(client.get("/api/knows", query_string={"device": fp, "ask": "short"}, environ_base=FAR).status_code == 400
    and client.get("/api/knows", query_string={"ask": ask}, environ_base=FAR).status_code == 400,
    "too few words to sign, or no laptop named, is refused")
codes = [client.get("/api/knows", query_string={"device": fp, "ask": ask}, environ_base=FAR).status_code for _ in range(40)]
chk(codes[0] == 200 and codes[-1] == 429, "one address may ask only so many times in ten minutes")
gr_master._rate.clear()
with closing(appdb()) as x:
    x.execute("DELETE FROM settings WHERE key='gr_token'"); x.commit()
    x.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('gr_server_url', ?)", (OLD,)); x.commit()
chk(green_room.follow_move(NEW) is False and app_setting("gr_server_url") == OLD,
    "an app that isn't signed in is not moved")
world["new"] = "down"; world["old"] = "same"; sent_old.clear(); green_room._back["at"] = 0
chk(green_room.go_back() is False and not sent_old, "nor does an app that isn't signed in go back anywhere")
green_room.requests.get = real_get
srv.shutdown()

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)
