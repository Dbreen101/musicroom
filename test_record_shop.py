"""Record shopping, app side — the app's own routes against a REAL rooms server
on a local port: the shop's state, a crate, the listening copy held in memory,
"note it" onto a wishlist that holds 100, buying clears a wish, the counter and
blind through the app, and an older server answered politely.
No sound. Run:  ./venv/bin/python test_record_shop.py"""
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_server.db")
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["MR_GREEN_ROOM"] = "1"                       # the trial: the wishlist's 100 is in force
os.environ.pop("MR_GR_SERVER", None)
(TMP / "app_data").mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ─── the rooms server, for real ───
import gr_server
import gr_shop

music = TMP / "music"; music.mkdir()
for i in range(8):
    with wave.open(str(music / f"shop record {i}.wav"), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(bytes([i + 1, 2]) * 2400)
from PIL import Image
Image.new("RGB", (600, 600), (40, 90, 60)).save(music / "cover.jpg")
with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
label_code = gr_server.make_invite("Moss Records", kind="label", handle="moss", public=True)
gr_server.add_folder(str(music), owner="moss")
with closing(gr_server.db()) as conn:
    conn.execute("UPDATE gr_tracks SET genre='House', year=1994"); conn.commit()
    IDS = [r[0] for r in conn.execute("SELECT id FROM gr_tracks ORDER BY id")]
code = gr_server.make_invite("Shopper")
other_code = gr_server.make_invite("Brendan")

from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, gr_server.app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
SERVER = f"http://127.0.0.1:{srv.server_port}"

# ─── the app: a fresh database, signed in ───
import mr_paths
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database()
    migrate.run_migration()
def appdb():
    c = sqlite3.connect(mr_paths.DB_PATH); c.row_factory = sqlite3.Row; return c
with closing(appdb()) as c:
    chk("gr_track_id" in {r[1] for r in c.execute("PRAGMA table_info(wishlist)")}, "a fresh library's wishlist can point at a Music Room record")

import green_room
green_room.join(SERVER, code, "test laptop")
with contextlib.redirect_stdout(io.StringIO()):
    import app as mr
import record_shop
client = mr.app.test_client()
J = lambda r: r.get_json()

import requests
other = requests.post(SERVER + "/api/join", json={"invite_code": other_code, "fingerprint": "mac-other"}).json()["token"]
OH = {"Authorization": f"Bearer {other}"}

# ─── the shop as the app shows it ───
st = J(client.get("/api/gr/shop"))
chk(st["left"]["crates"] == 3 and st["records"] == 8 and st["facets"]["genres"] == ["House"]
    and st["wish"] == {"count": 0, "max": 100, "left": 100, "ids": []} and st["basket"] == {},
    "the shop's state comes through, with the wishlist's room and the basket beside it")
r = client.post("/api/gr/shop/pull", json={"genres": ["House"]})
pull = J(r)["pull"]
chk(r.status_code == 200 and len(pull["items"]) == 8 and J(client.get(f"/api/gr/shop/pulls/{pull['id']}"))["pull"]["id"] == pull["id"],
    "a crate is pulled and opened again through the app")
r = client.post("/api/gr/shop/pull", json={"genres": ["Gabber"]})
chk(r.status_code == 404 and J(r).get("empty") and "Nothing in the shop" in J(r)["error"], "the shop's own refusals arrive as they are")
first = pull["items"][0]

# ─── listening: ONE PLAY of the whole record, by a one-time ticket, held in memory while it lasts ───
if gr_shop._ffmpeg():
    asked = []
    real_listen = green_room.shop_listen
    green_room.shop_listen = lambda *a: (asked.append(a), real_listen(*a))[1]
    r = client.post("/api/gr/shop/play", json={"kind": "pull", "ctx": pull["id"], "track": first["id"]})
    ticket = J(r)["play"]
    chk(r.status_code == 200 and J(r)["url"] == f"/api/gr/shop/play/{ticket}" and len(ticket) >= 16, "pressing Listen starts the one play, by a ticket")
    r = client.get(f"/api/gr/shop/play/{ticket}")
    whole = r.data
    chk(r.status_code == 200 and r.mimetype == "audio/mpeg" and r.headers["Accept-Ranges"] == "bytes" and len(whole) > 200
        and r.headers["Cache-Control"] == "no-store", "the whole record plays through the app")
    r = client.get(f"/api/gr/shop/play/{ticket}", headers={"Range": "bytes=100-199"})
    chk(r.status_code == 206 and r.data == whole[100:200] and r.headers["Content-Range"] == f"bytes 100-199/{len(whole)}",
        "…in pieces, so the page can pause, carry on and move through it")
    r = client.get(f"/api/gr/shop/play/{ticket}", headers={"Range": "bytes=-50"})
    chk(r.status_code == 206 and r.data == whole[-50:] and len(asked) == 1, "within the play it is fetched from the server once")
    chk(client.get(f"/api/gr/shop/play/{ticket}", headers={"Range": f"bytes={len(whole) + 5}-"}).status_code == 416, "a piece past the end is refused")
    client.post(f"/api/gr/shop/play/{ticket}/end")
    r = client.get(f"/api/gr/shop/play/{ticket}")
    chk(r.status_code == 410 and J(r)["heard"], "once the play ends its sound is put down: the ticket plays no more")
    r = client.post("/api/gr/shop/play", json={"kind": "pull", "ctx": pull["id"], "track": first["id"]})
    chk(r.status_code == 403 and J(r)["heard"] and "borrow" in J(r)["error"], "a second play is refused, with the way to hear it again: borrow or buy")
    chk(J(client.get(f"/api/gr/shop/pulls/{pull['id']}"))["pull"]["items"][0]["heard"], "the crate says it has been heard")
    tickets = [J(client.post("/api/gr/shop/play", json={"kind": "pull", "ctx": pull["id"], "track": it["id"]}))["play"] for it in pull["items"][1:5]]
    chk(len(record_shop._plays) == record_shop.PLAY_KEEP and tickets[0] not in record_shop._plays,
        f"only {record_shop.PLAY_KEEP} plays are held at once; starting another puts the oldest down")
    chk(not list((TMP / "app_data").rglob("*.mp3")), "no listening copy is ever written down on the laptop")
    green_room.shop_listen = real_listen
chk(client.post("/api/gr/shop/play", json={"kind": "pull", "ctx": pull["id"], "track": 99999}).status_code == 403
    and client.post("/api/gr/shop/play", json={"kind": "pull", "track": first["id"]}).status_code == 400
    and client.get(f"/api/gr/shop/listen?pull={pull['id']}&track={first['id']}").status_code == 410,
    "outside a crate nothing plays; the old way of asking is gone")

# ─── note it for later ───
chk(client.post("/api/gr/shop/wish", json={"record": first}).status_code == 400
    and client.post("/api/gr/shop/wish", json={"why": "the bassline"}).status_code == 400, "a note needs a record and a line of why")
r = client.post("/api/gr/shop/wish", json={"record": first, "why": "  the  bassline, for the end of a night ", "found": "a crate · House"})
w = J(r)["noted"]
chk(r.status_code == 200 and w["gr_track_id"] == first["id"] and w["notes"] == "the bassline, for the end of a night"
    and w["title"] == first["title"] and w["source"] == "Music Room" and w["provenance"] == "a crate · House" and w["status"] == "wishing"
    and J(r)["wish"]["count"] == 1 and J(r)["wish"]["ids"] == [first["id"]],
    "noted: the record's name, who it is by, where it was found and the line of why are on the wishlist")
r = client.post("/api/gr/shop/wish", json={"record": first, "why": "changed my mind about why"})
chk(J(r)["already"] is True and J(r)["noted"]["notes"] == "changed my mind about why" and J(r)["wish"]["count"] == 1,
    "noted twice is one wish, with the newer line")
chk(J(client.get("/api/gr/shop"))["wish"]["ids"] == [first["id"]] and J(client.get("/api/gr/shop/wishes"))["left"] == 99, "the shop knows which records are noted")

# ─── the wishlist holds 100 ───
with closing(appdb()) as c:
    for n in range(99):
        c.execute("INSERT INTO wishlist (url, title, status) VALUES ('', ?, 'wishing')", (f"filler {n}",))
    c.commit()
second = pull["items"][1]
r = client.post("/api/gr/shop/wish", json={"record": second, "why": "one too many"})
chk(r.status_code == 409 and J(r).get("full") and "100" in J(r)["error"], "the 101st is refused, in plain words")
r = client.post("/api/wishlist", json={"title": "typed in by hand"})
chk(r.status_code == 409 and J(r).get("full"), "…by every way in, not only the shop's")
chk(J(client.post("/api/discover/add", json={"items": [{"artist": "A", "title": "B"}]})) == {"added": 0, "skipped": 0, "no_room": 1},
    "a pasted tracklist says what didn't fit")
chk(client.post("/api/gr/shop/wish", json={"record": first, "why": "still allowed: it is on the list already"}).status_code == 200,
    "a wish already on the list can still be re-worded")
with closing(appdb()) as c:
    wid = c.execute("SELECT id FROM wishlist WHERE title='filler 0'").fetchone()[0]
client.delete(f"/api/wishlist/{wid}")
r = client.post("/api/gr/shop/wish", json={"record": second, "why": "now there is room"})
chk(r.status_code == 200 and J(r)["wish"]["left"] == 0, "taking one out makes room for one")

# ─── buying clears a wish ───
out = green_room.buy_track(first["id"])
with closing(appdb()) as c:
    row = c.execute("SELECT * FROM wishlist WHERE gr_track_id=?", (first["id"],)).fetchone()
chk(row["status"] == "supported" and row["bought_via"] == "music room" and row["fulfilled_track_id"] == out["track_id"],
    "bought, the wish becomes owned")
chk(J(client.get("/api/gr/shop/wishes"))["left"] == 1 and first["id"] not in J(client.get("/api/gr/shop/wishes"))["ids"],
    "…and no longer counts toward the 100")
green_room.basket_add(second["id"], "buy")
chk(J(client.get("/api/gr/shop"))["basket"] == {str(second["id"]): "buy"}, "what is in the basket shows in the shop")

# ─── the counter, through the app ───
r = client.post("/api/gr/shop/counter/ask", json={"text": "something for a long drive at night"})
qid = J(r)["question"]["id"]
chk(r.status_code == 200 and J(r)["left"]["asks"] == 2, "a question goes up")
took = requests.post(SERVER + "/api/shop/counter/take", headers=OH).json()["question"]
requests.post(SERVER + f"/api/shop/counter/{qid}/answer", headers=OH, json={"track_id": second["id"], "text": "it never hurries"})
chk(took["id"] == qid and took["asker"]["name"] == "Shopper", "someone else is handed it and answers")
record_shop._news["at"] = 0.0
chk(J(client.get("/api/gr/shop/news")) == {"answers": 1}, "the top bar hears there is an answer")
ans = J(client.get("/api/gr/shop/counter/mine"))["questions"][0]["answer"]
chk(ans["record"]["id"] == second["id"] and ans["by"]["name"] == "Brendan" and ans["text"] == "it never hurries", "the answer arrives with its record and who gave it")
if gr_shop._ffmpeg():
    r = client.post("/api/gr/shop/play", json={"kind": "q", "ctx": qid, "track": second["id"]})
    if second["id"] in [it["id"] for it in pull["items"][1:5]]:       # (heard already, in the crate above)
        chk(r.status_code == 403 and J(r)["heard"], "an answer already heard in a crate isn't played again: one play, wherever it was")
    else:
        chk(r.status_code == 200, "the answer can be heard")
client.post(f"/api/gr/shop/counter/{qid}/seen")
chk(J(client.get("/api/gr/shop/news")) == {"answers": 0}, "looked at, it is no longer news")
chk(J(client.post(f"/api/gr/shop/counter/{qid}/settle", json={"choice": "basket"})) == {"settled": "basket"}
    and client.post("/api/gr/shop/play", json={"kind": "q", "ctx": qid, "track": second["id"]}).status_code == 403
    and not [v for v in record_shop._plays.values() if v["key"][0] == "q" and v["key"][1] == qid],
    "settled, it doesn't play (and any play of it is put down)")
chk(client.post(f"/api/gr/shop/counter/{qid}/dance").status_code == 404, "the counter does only what it does")
requests.post(SERVER + "/api/shop/counter/ask", headers=OH, json={"text": "what is the best thing on Moss?"})
t = J(client.post("/api/gr/shop/counter/take"))["question"]
found = J(client.get("/api/gr/shop/search?q=shop+record+3"))["records"]
r = client.post(f"/api/gr/shop/counter/{t['id']}/answer", json={"track_id": found[0]["id"], "text": "the third one"})
chk(t["asker"]["name"] == "Brendan" and len(found) == 1 and r.status_code == 200 and J(r)["left"]["answers"] == 2, "the app's own person answers one, finding the record by its words")

# ─── blind, through the app ───
b = J(client.post("/api/gr/shop/blind/next"))["blind"]
chk(set(b) == {"id", "duration_s", "heard"} and not b["heard"], "a blind record comes with no name, not heard yet")
if gr_shop._ffmpeg():
    r = client.post("/api/gr/shop/play", json={"kind": "blind", "ctx": b["id"]})
    chk(r.status_code == 200 and client.get(J(r)["url"]).status_code == 200, "it plays by its turn alone")
    chk(client.post("/api/gr/shop/play", json={"kind": "blind", "ctx": b["id"]}).status_code == 403, "once")
d = J(client.post(f"/api/gr/shop/blind/{b['id']}/decide", json={"choice": "note"}))
chk(d["choice"] == "note" and d["record"]["title"], "decided, it is turned over")
b2 = J(client.post("/api/gr/shop/blind/next"))["blind"]
chk(b2["id"] != b["id"] and not [v for v in record_shop._plays.values() if v["key"][0] == "blind" and v["key"][1] == b["id"]],
    "the next one comes; the last one's play is put down")

# ─── a seller's crates, through the app ───
chk(J(client.get("/api/gr/shop/my/crates")) == {"crates": [], "can_make": False, "max": 25}
    and client.post("/api/gr/shop/my/crates", json={"name": "Mine"}).status_code == 403, "a listener is told plainly that crates are for sellers")

# ─── a rooms server from before record shopping ───
class Old:
    status_code = 404
    headers = {"Content-Type": "text/html; charset=utf-8"}
    content = b"<h1>Not Found</h1>"
    def json(self): raise ValueError
real_get, real_post = green_room._get, green_room._post
green_room._get = lambda *a, **k: Old()
green_room._post = lambda *a, **k: Old()
record_shop._news["at"] = 0.0
record_shop._plays.clear()
r = client.get("/api/gr/shop")
chk(r.status_code == 502 and J(r).get("away") and "needs one restart" in J(r)["error"] and J(r)["wish"]["max"] == 100,
    "an older server: the shop says it needs one restart, and the wishlist still answers")
chk(client.post("/api/gr/shop/pull", json={}).status_code == 502 and J(client.get("/api/gr/shop/news")) == {"answers": 0}
    and client.post("/api/gr/shop/play", json={"kind": "pull", "ctx": 1, "track": IDS[7]}).status_code == 403, "…and nothing else falls over")
green_room._get, green_room._post = real_get, real_post

srv.shutdown()
print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
