"""Plug-ins (plugins.py) and the app's guardrails around them (2026-11-20):
what a plug-in folder must hold, that its files never reach outside its
folder, the box its page runs in, that it reads only what it was given, the
crate it can pick — and the app refusing requests from other web pages, the
public room's content rule, the house rules page, your own CSS, the version
line, and the master page's relay accepting only its own routes.
A fresh data folder, no network, no sound. Run:  ./venv/bin/python test_plugins.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["MR_GREEN_ROOM"] = "1"
os.environ["MUSICROOM_3D"] = "1"
os.environ.pop("MR_GR_SERVER", None)
(TMP / "app_data").mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import plugins as P

# ── what a plug-in folder must hold ──
ok, why = P.clean_manifest({"id": "thread", "name": "Thread", "wants": ["catalogue"]}, "thread")
chk(ok and ok["entry"] == "main.js" and ok["wants"] == ["catalogue"] and why is None, "a plain plugin.json is read, main.js by default")
for raw, folder, said in [
    ({"id": "../x", "name": "X"}, "x", "a-z"),
    ({"id": "thread", "name": "X"}, "other", "folder"),
    ({"id": "x", "name": ""}, "x", "name"),
    ({"id": "x", "name": "X", "entry": "../../app.py"}, "x", "entry"),
    ({"id": "x", "name": "X", "entry": "main.py"}, "x", "entry"),
    ({"id": "x", "name": "X", "style": "/etc/passwd.css"}, "x", "style"),
    ({"id": "x", "name": "X", "wants": ["accounts"]}, "x", "want"),
]:
    m, why = P.clean_manifest(raw, folder)
    chk(m is None and said in (why or ""), f"refused: {json.dumps(raw)[:60]} ({why})")

# your own plug-ins folder: one good, one broken, one trying to step outside
mine = P.mine_root(os.environ["MUSICROOM_DATA"])
(mine / "mine").mkdir(parents=True)
(mine / "mine" / "plugin.json").write_text(json.dumps({"id": "mine", "name": "Mine", "wants": ["library", "catalogue"]}))
(mine / "mine" / "main.js").write_text("MusicRoom.say('hello')")
(mine / "mine" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
(mine / "mine" / "secret.py").write_text("x")
(mine / "broken").mkdir()
(mine / "broken" / "plugin.json").write_text("{ not json")
(mine / "thread").mkdir()
(mine / "thread" / "plugin.json").write_text(json.dumps({"id": "thread", "name": "Copy of Thread"}))
(mine / "thread" / "main.js").write_text("")
found = {(p["id"], p["source"]): p for p in P.discover(ROOT, os.environ["MUSICROOM_DATA"])}
chk(("thread", "built-in") in found and ("shelves", "built-in") in found and not found[("thread", "built-in")].get("error"),
    "the two plug-ins that come with the app are found and can run")
chk(found[("mine", "yours")].get("folder") and found[("broken", "yours")].get("error") and "already" in found[("thread", "yours")].get("error", ""),
    "your own are found; a broken one says why; one can't take a built-in plug-in's name")
pm = P.find(ROOT, os.environ["MUSICROOM_DATA"], "mine")
chk(P.file_path(pm, "main.js") and P.file_path(pm, "pic.png"), "its own files can be served")
chk(not any(P.file_path(pm, x) for x in ("../../app.py", "/etc/passwd", "secret.py", ".hidden.js", "a/../../x.js", "")),
    "nothing outside its folder, nothing it isn't (a .py), nothing hidden")

# ── the app ──
import mr_paths
import sqlite3
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database()
    migrate.run_migration()
    import app as mr
def setting(k, v):
    with mr.app.app_context():
        mr.set_setting(k, v)
setting("gr_token", "test-token")                     # signed in, as far as the front door can tell
c = mr.app.test_client()

lst = c.get("/api/plugins").get_json()
chk(all(not p["on"] for p in lst["plugins"]) and lst["folder"].endswith("plugins"), "every plug-in starts switched off")
chk(c.get("/plugins/frame/thread").status_code == 404, "a plug-in that isn't switched on has no page")
chk(c.get("/api/plugins/thread/data/catalogue").status_code == 403, "nor anything to read")
r = c.post("/api/plugins/mine", json={"on": True})
chk(r.status_code == 200 and next(p for p in r.get_json()["plugins"] if p["id"] == "mine")["on"], "switching it on gives it what it said it wants")
f = c.get("/plugins/frame/mine")
csp = f.headers.get("Content-Security-Policy", "")
chk(f.status_code == 200 and "connect-src 'none'" in csp and "sandbox allow-scripts" in csp and "form-action 'none'" in csp
    and "frame-src 'none'" in csp and "/plugins/files/mine/" in csp and "'unsafe-eval'" not in csp,
    "its page runs in a box: its own files only, nothing sent anywhere, no frames, no forms")
chk('/static/js/plugin_runtime.js' in f.get_data(as_text=True) and '/plugins/files/mine/main.js' in f.get_data(as_text=True),
    "the box holds the runtime and the plug-in's own code")
chk(c.get("/plugins/files/mine/main.js").status_code == 200 and c.get("/plugins/files/mine/secret.py").status_code == 404
    and c.get("/plugins/files/mine/..%2F..%2Fapp.py").status_code == 404, "its files are served; nothing else is")
lib = c.get("/api/plugins/mine/data/library")
chk(lib.status_code == 200 and lib.get_json()["records"] == [], "it may read your own records (none in a fresh library)")
chk(c.get("/api/plugins/mine/data/rooms").status_code == 403, "but not what it didn't ask for")
chk(c.get("/api/plugins/mine/data/accounts").status_code == 404, "and never anything that isn't on the list")

# what goes to the server: the plug-in's name on the crate, the records it named — nothing else
import green_room
sent = []
def fake_shop(method, path, payload=None, params=None):
    sent.append((method, path, payload))
    if path == "/api/plugins/catalogue":
        return 200, {"records": [{"id": 1, "title": "A"}]}
    if path == "/api/shop/crates/pull":
        return 200, {"pull": {"id": 9, "count": 2}, "left": {"crates": 2}}
    return 404, {"error": "no"}
real_shop = green_room.shop_call
green_room.shop_call = fake_shop
chk(c.get("/api/plugins/mine/data/catalogue").get_json()["records"][0]["id"] == 1, "the shop's records come from the server's plug-in route")
r = c.post("/api/plugins/mine/crate", json={"ids": [3, 4, "5; drop", None, 4.5], "title": "x" * 200})
chk(r.status_code == 200 and sent[-1] == ("POST", "/api/shop/crates/pull", {"pick": {"ids": [3, 4], "by": "Mine", "title": "x" * 80}}),
    "a crate it picks carries its name and only whole record numbers")
c.post("/api/plugins/mine", json={"on": False})
chk(c.post("/api/plugins/mine/crate", json={"ids": [3]}).status_code == 403 and c.get("/plugins/frame/mine").status_code == 404,
    "switched off, it can do nothing")
green_room.shop_call = real_shop

# ── only the app's own pages may use the app ──
chk(c.post("/api/plugins/mine", json={"on": True}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403,
    "a request from another web page is refused")
chk(c.post("/api/plugins/mine", json={"on": True}, headers={"Origin": "null"}).status_code == 403,
    "and from a sealed box (a plug-in, or a room's own code)")
chk(c.post("/api/plugins/mine", json={"on": True}, headers={"Origin": "http://evil.example"}).status_code == 403,
    "and from a page that says it is elsewhere")
chk(c.get("/api/gr/status", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403,
    "another program on this laptop's other ports can't read your account either")
chk(c.post("/api/plugins/mine", json={"on": False}, headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://localhost"}).status_code == 200,
    "the app's own pages are let through")
chk(c.get("/static/css/plugin_base.css", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200
    and c.get("/plugins/files/mine/main.js", headers={"Origin": "null"}).status_code == 200,
    "pictures and a plug-in's own files can still be read from its box")
chk(c.get("/api/spotify/callback", headers={"Sec-Fetch-Site": "cross-site"}).status_code != 403, "Spotify's answer at sign-in still arrives")

# ── a public room's page: what it may load ──
room = c.get("/rooms/someone")
rcsp = room.headers.get("Content-Security-Policy", "")
chk(room.status_code == 200 and "media-src 'self' blob:" in rcsp and "connect-src 'self'" in rcsp and "font-src 'self' data:" in rcsp
    and "object-src 'none'" in rcsp and "https://w.soundcloud.com" in rcsp,
    "a public room can't play or load from just anywhere: the app, and the services' own players")

# ── the house rules, your own CSS, the version, the master's relay ──
hr = c.get("/house-rules?bare=1").get_data(as_text=True)
chk("Only put up music you made" in hr and "<li>" in hr and "<script" not in hr.split("<article")[1], "the house rules page shows HOUSE_RULES.md")
setting("gr_token", "")
chk(c.get("/house-rules").status_code == 200 and c.get("/master").status_code == 302, "the house rules can be read before signing in; the master page can't")
setting("gr_token", "test-token")
setting("user_css", ".nav{color:red}</style><script>alert(1)</script>")
page = c.get("/house-rules").get_data(as_text=True)
chk('<style id="mr-user-css">.nav{color:red}<\\/style><script>' in page and "</style><script>alert" not in page,
    "your own CSS is laid over every page, and can't break out of its style")
chk('mr-user-css' not in c.get("/house-rules?plain=1").get_data(as_text=True), "?plain=1 shows a page without it")
setting("user_css", "")
green_room.shop_call = lambda *a, **k: (200, {"version": "2099.01.01", "url": "https://github.com/x/y/releases/tag/v2099.01.01", "note": "new"})
v = c.get("/api/gr/version").get_json()
chk(v["mine"] == (ROOT / "VERSION").read_text().strip() and v["update"], "the app knows its own version and that a newer one is named")
mr._version_seen["at"] = 0
green_room.shop_call = lambda *a, **k: (200, {"version": "2099.01.01", "url": "javascript:alert(1)"})
chk(not c.get("/api/gr/version").get_json()["update"], "a version without a proper web address isn't offered")
green_room.shop_call = real_shop
chk(all(c.get("/api/gr/master/" + p).status_code == 404 for p in ("../me", "accounts/x", "records/1/audio/../../x", "wallets")),
    "the master page's relay reaches only the master's own routes")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
