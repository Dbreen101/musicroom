"""The credits trial on the rooms server (gr_sim.py): records brought in from
David's Spotify playlist become simulated artist accounts and their records;
listeners bring tracks home or buy them with credits; whole records cost less;
the room holds so many; a track taken out waits a week to come back; one play
in the shop streams from Spotify; the Spotify keys go to five people each; the
master reads what everyone did.
A fresh database, no network, no sound. Run:  ./venv/bin/python test_gr_sim.py"""
import os
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_sim_test.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")

import gr_server
import gr_master
import gr_sim

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
client = gr_server.app.test_client()
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def join(code, fp): return client.post("/api/join", json={"invite_code": code, "fingerprint": fp, "device_name": "laptop"}).get_json()["token"]
def code_of(handle):
    with closing(gr_server.db()) as c:
        return c.execute("SELECT invite_code FROM gr_accounts WHERE handle=?", (handle,)).fetchone()[0]
def sql(q, *p):
    with closing(gr_server.db()) as c:
        return c.execute(q, p).fetchall()
def sid(n): return (f"{n:0>22}")[-22:]          # a 22-letter Spotify id
def signup(name):
    gr_master._rate.clear()
    return client.post("/api/signup", json={"name": name, "fingerprint": "mac-" + name, "agreed": True}).get_json()["token"]

gr_master.make_master("David", handle="david")
david = join(code_of("david"), "mac-david")
aoife, bea = signup("Aoife"), signup("Bea")

# ── off until the master turns it on ──
chk(client.post("/api/sim/home", json={"track_id": 1}, headers=hdr(aoife)).status_code == 409,
    "the trial is off until the master switches it on")
chk(client.get("/api/master/sim", headers=hdr(aoife)).status_code == 403, "only the master reads the trial's page")
r = client.post("/api/master/sim/rules", json={"on": True, "room_space": 0}, headers=hdr(david))
chk(r.status_code == 400, "a room with no space is refused")
r = client.post("/api/master/sim/rules", json={"on": True}, headers=hdr(david))
chk(r.status_code == 200 and r.get_json()["rules"]["on"] and r.get_json()["rules"]["start_credits"] == 300,
    "the master switches it on; the numbers start at 300 credits, 1 to bring home, 3 to buy, 200 room")

# ── records from the playlist: albums and singles, whole ──
X, Y = {"id": sid("ax"), "name": "Moss Fen"}, {"id": sid("ay"), "name": "The Lantern"}
def trk(n, name, artists): return {"id": sid(f"t{n}"), "name": name, "track_number": n % 10, "disc_number": 1,
                                    "duration_ms": 200000 + n, "artists": artists}
ALBUM_A = {"key": sid("ra"), "name": "Low Field", "kind": "album", "release_date": "2019-05-03", "total_tracks": 3,
           "artists": [X], "image": "", "tracks": [trk(1, "One", [X]), trk(2, "Two", [X]), trk(3, "Three", [X, Y])]}
SINGLE_B = {"key": sid("rb"), "name": "Hum", "kind": "single", "release_date": "2021", "total_tracks": 1,
            "artists": [X], "image": "", "tracks": [trk(11, "Hum", [X])]}
ALBUM_C = {"key": sid("rc"), "name": "Night Bus", "kind": "album", "release_date": "2024-01-01", "total_tracks": 2,
           "artists": [Y], "image": "", "tracks": [trk(21, "Stop", [Y]), trk(22, "Go", [Y])]}
r = client.post("/api/master/sim/records", json={"records": [ALBUM_A, SINGLE_B, ALBUM_C], "done": True,
                                                  "name": "Green Room shop"}, headers=hdr(david))
d = r.get_json()
chk(r.status_code == 200 and d["artists"] == 2 and d["records"] == 3 and d["tracks"] == 6,
    "three records from the playlist: two artist accounts, six tracks")
again = client.post("/api/master/sim/records", json={"records": [ALBUM_A, SINGLE_B, ALBUM_C]}, headers=hdr(david)).get_json()
chk(again["tracks"] == 0 and again["seen"] == 6 and again["artists"] == 0, "bringing the same records in again adds nothing")
bad = client.post("/api/master/sim/records", json={"records": [{"key": "x", "tracks": [], "artists": []}, "nope"]},
                  headers=hdr(david)).get_json()
chk(bad["skipped"] == 2 and bad["tracks"] == 0, "anything that isn't a record from Spotify is passed over")
acc = sql("SELECT * FROM gr_accounts WHERE is_sim=1 ORDER BY id")
chk(len(acc) == 2 and all(a["kind"] == "artist" and a["is_public"] for a in acc) and acc[0]["name"] == "Moss Fen",
    "each record's first artist is a simulated artist account with a public room")
rooms = client.get("/api/rooms", headers=hdr(aoife)).get_json()["rooms"]
chk({x["name"] for x in rooms} >= {"Moss Fen", "The Lantern"}, "the artists' rooms are in the directory")
tr = {t["title"]: t for t in sql("SELECT * FROM gr_tracks WHERE spotify_uri IS NOT NULL")}
chk(tr["One"]["record_key"] == ALBUM_A["key"] and tr["One"]["record_kind"] == "album" and tr["One"]["year"] == 2019
    and tr["Hum"]["record_kind"] == "single" and tr["Three"]["artist"] == "Moss Fen, The Lantern",
    "a track knows its record, the record's kind and year, and everyone who made it")
pl = client.get("/api/master/sim", headers=hdr(david)).get_json()
chk(pl["counts"] == {"artists": 2, "records": 3, "tracks": 6} and set(pl["record_keys"]) == {ALBUM_A["key"], SINGLE_B["key"], ALBUM_C["key"]},
    "the master's page counts what came in, and knows which records are already here")
r = client.post("/api/master/sim/playlist", json={"url": "https://open.spotify.com/playlist/" + sid("pl") + "?si=abc"}, headers=hdr(david))
chk(r.get_json()["playlist"]["id"] == sid("pl"), "the playlist is known by its link")
chk(client.post("/api/master/sim/playlist", json={"url": "https://example.com"}, headers=hdr(david)).status_code == 400,
    "a link that isn't a Spotify playlist is refused")

# ── a listener's credits and room ──
me = client.get("/api/sim/me", headers=hdr(aoife)).get_json()
chk(me["on"] and me["credits"] == 300 and me["room"] == {"count": 0, "space": 200}, "a listener starts with 300 credits and an empty room of 200")
chk(client.get("/api/me", headers=hdr(aoife)).get_json()["sim"]["credits"] == 300, "/api/me carries the trial too")
cat = {t["title"]: t for t in client.get("/api/catalogue", headers=hdr(aoife)).get_json()["tracks"]}
s1 = cat["One"]["sim"]
chk(s1["home_cost"] == 1 and s1["buy_cost"] == 3 and s1["state"] == "" and s1["spotify_uri"] is None and s1["record_tracks"] == 3,
    "the catalogue says what bringing home and buying cost — and keeps the stream back until it is yours")
chk(client.post("/api/borrow", json={"track_id": tr["One"]["id"]}, headers=hdr(aoife)).status_code == 409,
    "a playlist record isn't borrowed the old way")

# ── bring home one track, then the whole record (80% of what's left) ──
r = client.post("/api/sim/home", json={"track_id": tr["One"]["id"]}, headers=hdr(aoife))
d = r.get_json()
chk(r.status_code == 200 and d["spent"] == 1 and d["credits"] == 299 and d["room"]["count"] == 1
    and d["tracks"][0]["spotify_uri"] == "spotify:track:" + sid("t1"), "bringing one track home: 1 credit, room 1, and its stream")
rec = client.get(f"/api/sim/record/{ALBUM_A['key']}", headers=hdr(aoife)).get_json()["record"]
chk(rec["home"] == {"cost": 2, "tracks": 2, "locked": 0} and rec["buy"]["cost"] == 7,
    "the rest of the record: 2 to bring home (80% of 2, rounded up); buying all 3 = (2+3+3) × 80%, rounded up = 7")
d = client.post("/api/sim/home", json={"record": ALBUM_A["key"]}, headers=hdr(aoife)).get_json()
chk(d["spent"] == 2 and d["credits"] == 297 and d["room"]["count"] == 3, "the whole record home: the two left for 2 credits")
d = client.post("/api/sim/home", json={"record": ALBUM_A["key"]}, headers=hdr(aoife)).get_json()
chk(d.get("already") and d["spent"] == 0, "bringing it home again costs nothing — it's already there")

# ── buy: the difference for a track at home; outright for one that isn't ──
d = client.post("/api/sim/buy", json={"track_id": tr["One"]["id"]}, headers=hdr(aoife)).get_json()
chk(d["spent"] == 2 and d["credits"] == 295 and d["room"]["count"] == 2, "buying a track brought home costs the difference (2) and frees its room")
d = client.post("/api/sim/buy", json={"record": ALBUM_C["key"]}, headers=hdr(aoife)).get_json()
chk(d["spent"] == 5 and d["credits"] == 290 and d["room"]["count"] == 2, "a whole record bought outright, never brought home: 2×3×80% = 5")
cat = {t["title"]: t for t in client.get("/api/catalogue", headers=hdr(aoife)).get_json()["tracks"]}
chk(cat["Stop"]["sim"]["state"] == "bought" and cat["Stop"]["sim"]["spotify_uri"] and cat["Two"]["sim"]["buy_cost"] == 2,
    "the catalogue shows what is bought, and that a track at home costs the difference")

# ── a full room ──
client.post("/api/master/sim/rules", json={"room_space": 2}, headers=hdr(david))
r = client.post("/api/sim/home", json={"track_id": tr["Hum"]["id"]}, headers=hdr(aoife))
chk(r.status_code == 409 and r.get_json()["full"] and "2 of 2" in r.get_json()["error"], "a full room says so")
r = client.post("/api/sim/buy", json={"track_id": tr["Hum"]["id"]}, headers=hdr(aoife))
chk(r.status_code == 200 and r.get_json()["spent"] == 3, "buying still works with the room full (bought records take no room)")
row = sql("SELECT * FROM gr_ledger WHERE what='buy' ORDER BY id DESC LIMIT 1")[0]
chk(row["room_full"] == 1 and row["room_count"] == 2 and row["room_space"] == 2, "the ledger keeps that the room was full when they bought")

# ── take out: no credit back; a week before it can come back, free ──
r = client.post("/api/sim/out", json={"track_id": tr["Two"]["id"]}, headers=hdr(aoife))
d = r.get_json()
chk(r.status_code == 200 and d["credits"] == 287 and d["room"]["count"] == 1, "taking a track out frees its room; no credit back")
r = client.post("/api/sim/home", json={"track_id": tr["Two"]["id"]}, headers=hdr(aoife))
chk(r.status_code == 423 and r.get_json()["locked"] and "can come back on" in r.get_json()["error"], "it can't come back for a week")
chk(client.post("/api/sim/out", json={"track_id": tr["One"]["id"]}, headers=hdr(aoife)).status_code == 409,
    "a bought track can't be taken out")
with closing(gr_server.db()) as c:
    c.execute("UPDATE gr_home SET back_after='2000-01-01T00:00:00' WHERE track_id=?", (tr["Two"]["id"],)); c.commit()
d = client.post("/api/sim/home", json={"track_id": tr["Two"]["id"]}, headers=hdr(aoife)).get_json()
chk(d["spent"] == 0 and d["back"] == 1 and d["credits"] == 287, "after the week it comes back for nothing")
d = client.post("/api/sim/buy", json={"track_id": tr["Two"]["id"]}, headers=hdr(aoife)).get_json()
chk(d["spent"] == 2, "and buying it then still costs only the difference")

# ── not enough credits ──
client.post("/api/master/sim/credits", json={"account_id": sql("SELECT id FROM gr_accounts WHERE name='Bea'")[0]["id"],
                                             "credits": -299, "note": "test"}, headers=hdr(david))
chk(client.get("/api/sim/me", headers=hdr(bea)).get_json()["credits"] == 1, "the master can give or take credits")
r = client.post("/api/sim/buy", json={"track_id": tr["Hum"]["id"]}, headers=hdr(bea))
chk(r.status_code == 402 and r.get_json()["short"] and "needs 3 credits" in r.get_json()["error"], "too few credits: it says how many it needs")
client.post("/api/master/sim/credits", json={"everyone": True, "credits": 50}, headers=hdr(david))
chk(client.get("/api/sim/me", headers=hdr(bea)).get_json()["credits"] == 51, "credits for everyone at once")

# ── what Aoife has, as records ──
mine = client.get("/api/sim/mine", headers=hdr(aoife)).get_json()["records"]
by = {m["title"]: m for m in mine}
chk(set(by) == {"Low Field", "Night Bus", "Hum"} and by["Low Field"]["counts"] == {"home": 1, "bought": 2, "out": 0}
    and by["Low Field"]["tracks"][0]["track_no"] == 1, "her records, whole, in order, with what is home and what is bought")
chk(all(t["spotify_uri"] for m in mine for t in m["tracks"] if t["state"] in ("home", "bought")), "each held track carries its stream")

# ── one play in the shop: from Spotify, once ──
r = client.post("/api/shop/crates/pull", json={}, headers=hdr(bea))
items = r.get_json()["pull"]["items"] if r.status_code == 200 else []
pull = r.get_json()["pull"]["id"] if r.status_code == 200 else 0
sim_item = next((x for x in items if x.get("sim")), None)
chk(sim_item is not None and sim_item["sim"]["spotify_uri"] is None, "a crate holds playlist records, their stream kept back")
if sim_item:
    r = client.get(f"/api/shop/listen/{sim_item['id']}?pull={pull}", headers=hdr(bea))
    chk(r.status_code == 200 and r.get_json()["spotify"].startswith("spotify:track:"), "its one play hands over where it streams")
    r = client.get(f"/api/shop/listen/{sim_item['id']}?pull={pull}", headers=hdr(bea))
    chk(r.status_code == 403 and r.get_json().get("heard"), "a second play is refused")
st = client.get("/api/shop", headers=hdr(bea)).get_json()
chk(st["listening"] and st["sim"]["on"], "the shop can be listened to with no listening copies made, and knows the trial is on")

# ── Spotify keys: five people each ──
r = client.post("/api/master/spotify-keys", json={"keys": [{"label": "David's", "client_id": "nope"}]}, headers=hdr(david))
chk(r.status_code == 400, "a Client ID that isn't one is refused")
K1, K2 = "0123456789abcdef0123456789abcdef", "fedcba9876543210fedcba9876543210"
keys = client.post("/api/master/spotify-keys", json={"keys": [{"label": "David's", "client_id": K1}, {"label": "Second", "client_id": K2.upper()}]},
                   headers=hdr(david)).get_json()["keys"]
chk([k["id"] for k in keys] == ["k1", "k2"] and keys[1]["client_id"] == K2, "two keys kept")
aid = lambda name: sql("SELECT id FROM gr_accounts WHERE name=?", name)[0]["id"]
chk(client.post("/api/master/spotify-keys/assign", json={"account_id": aid("Aoife"), "key": "k1"}, headers=hdr(david)).status_code == 200,
    "Aoife is given the first key")
me = client.get("/api/sim/me", headers=hdr(aoife)).get_json()
chk(me["spotify_client_id"] == K1 and me["spotify_key"] == "k1", "her app is told its key")
chk(client.get("/api/sim/me", headers=hdr(bea)).get_json()["spotify_client_id"] == "", "Bea has none: her app plays Spotify's own player")
more = [signup(f"P{i}") for i in range(5)]
codes = [client.post("/api/master/spotify-keys/assign", json={"account_id": aid(f"P{i}"), "key": "k1"}, headers=hdr(david)).status_code for i in range(5)]
chk(codes == [200, 200, 200, 200, 409], "a sixth person on one key is refused (Spotify's five)")
client.post("/api/master/spotify-keys", json={"keys": [{"id": "k2", "label": "Second", "client_id": K2}]}, headers=hdr(david))
chk(client.get("/api/sim/me", headers=hdr(aoife)).get_json()["spotify_client_id"] == "", "a key taken away leaves its people with none")

# ── what the master reads ──
act = {p["name"]: p for p in client.get("/api/master/sim/activity", headers=hdr(david)).get_json()["people"]}
a = act["Aoife"]
chk(a["spent"] == 1 + 2 + 2 + 5 + 3 + 2 and a["bought"] == 5 and a["home_now"] == 1 and a["buys_when_full"] >= 1
    and a["full_refused"] == 1 and a["taken_out"] == 1, "per person: spent, bought, at home, taken out, refused when full, bought when full")
csv_text = client.get("/api/master/sim/ledger.csv", headers=hdr(david)).get_data(as_text=True)
chk(csv_text.startswith("when,person") and "Aoife" in csv_text and ",buy," in csv_text, "the whole ledger as a spreadsheet")
chk(client.get("/api/master/sim/activity.csv", headers=hdr(david)).get_data(as_text=True).startswith("name,handle"), "and the activity")
chk(client.get("/api/master/sim/ledger.csv", headers=hdr(aoife)).status_code == 403, "nobody else gets the ledger")
ev = {r["kind"] for r in sql("SELECT kind FROM gr_events")}
chk({"sim_home", "sim_buy", "sim_out", "sim_full", "sim_short", "sim_rules", "sim_records"} <= ev, "every move is in the activity log")

# ── an older database gets everything new ──
with closing(gr_server.db()) as c:
    c.execute("DROP TABLE gr_ledger"); c.commit()
    gr_sim.ensure(c)
    chk(bool(c.execute("SELECT 1 FROM sqlite_master WHERE name='gr_ledger'").fetchone()), "ensure() remakes a missing table even when the others are there")

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
