"""Green Room server — join/device-limit/borrow/download round-trip checks."""
import os
import sys
import tempfile
import wave
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)   # (Windows: a file still open at exit can't be removed)
os.environ["MR_GR_DB"] = str(Path(_tmp.name) / "gr_test.db")
os.environ["MR_LIBRARY_DB"] = str(Path(_tmp.name) / "no_library.db")   # keep Daithí's library out

import gr_server
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))


# --- a tiny real wav the catalogue can hold ---
music = Path(_tmp.name) / "music"
music.mkdir()
wav = music / "test track.wav"
with wave.open(str(wav), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"\x01\x02" * 1600)

with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
result = gr_server.add_folder(str(music))
chk(result["added"] == 1, "add_folder found the wav")
code = gr_server.make_invite("Test Resident")
chk(code.startswith("gr-"), "invite code minted")

client = gr_server.app.test_client()
def join(fp, name="laptop", invite=code):
    return client.post("/api/join", json={"invite_code": invite, "fingerprint": fp, "device_name": name})
def hdr(tok): return {"Authorization": f"Bearer {tok}"}

# --- join + device limit ---
r1 = join("mac-aaa")
chk(r1.status_code == 200, "first device joins")
tok = r1.get_json()["token"]
chk(join("mac-aaa").get_json()["token"] == tok, "same device rejoining keeps its token")
chk(join("mac-bbb").status_code == 200, "a second device is allowed")
chk(join("mac-ccc").status_code == 403, f"a third device is refused (limit {gr_server.MAX_DEVICES})")
chk(join("mac-zzz", invite="gr-nope").status_code == 403, "an unknown invite code is refused")

# --- auth required everywhere ---
chk(client.get("/api/catalogue").status_code == 401, "catalogue needs a token")
chk(client.get("/api/me").status_code == 401, "me needs a token")
chk(client.post("/api/borrow", json={"track_id": 1}).status_code == 401, "borrow needs a token")

# --- catalogue ---
tracks = client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"]
chk(len(tracks) == 1, "catalogue lists the one track")
t = tracks[0]
chk(t["format"] == "wav" and t["price_cents"] == gr_server.DEFAULT_TRACK_PRICE_CENTS, "format + price carried")
chk("path" not in t, "server file paths never leak to clients")
chk(t["borrow_id"] is None, "not borrowed yet")

# --- plans: a borrow needs one first; picking one is free; the first borrow charges it ---
r = client.post("/api/borrow", json={"track_id": t["id"]}, headers=hdr(tok))
chk(r.status_code == 409 and r.get_json().get("need_plan") is True, "borrowing without a plan says: choose a subscription first")
plans = client.get("/api/plans", headers=hdr(tok)).get_json()["plans"]
chk([p["key"] for p in plans] == ["a", "b", "c"] and plans[0]["price_cents"] == 600, "the three plans are offered")
chk(client.post("/api/me/plan", json={"plan": "zzz"}, headers=hdr(tok)).status_code == 400, "an unknown plan is refused")
before = client.get("/api/me", headers=hdr(tok)).get_json()["wallet_cents"]
chk(client.post("/api/me/plan", json={"plan": "a"}, headers=hdr(tok)).get_json()["plan"] == "a", "plan A chosen")
chk(client.get("/api/me", headers=hdr(tok)).get_json()["wallet_cents"] == before, "choosing a plan costs nothing")
b = client.post("/api/borrow", json={"track_id": t["id"]}, headers=hdr(tok))
chk(b.status_code == 200, "borrow succeeds")
borrow = b.get_json()
me = client.get("/api/me", headers=hdr(tok)).get_json()
chk(before - me["wallet_cents"] == gr_server.PLANS["a"]["price_cents"], "first borrow charges exactly the monthly sub")
chk(me["sub_active"] and me["borrows_this_month"] == 1 and me["per_month"] == 20, "sub active, 1 of this month's 20 borrows used")

again = client.post("/api/borrow", json={"track_id": t["id"]}, headers=hdr(tok)).get_json()
chk(again["borrow_id"] == borrow["borrow_id"], "re-borrowing the same track is idempotent")
chk(client.get("/api/me", headers=hdr(tok)).get_json()["wallet_cents"] == me["wallet_cents"],
    "idempotent re-borrow charges nothing")

dl = client.get(borrow["url"], headers=hdr(tok))
original = wav.read_bytes()
chk(dl.status_code == 200, "download streams")
chk(dl.data != original, "the downloaded bytes are NOT the plain file")
dec = Cipher(algorithms.AES(bytes.fromhex(borrow["key"])),
             modes.CTR(bytes.fromhex(borrow["nonce"]))).decryptor()
chk(dec.update(dl.data) == original, "the key decrypts the download back byte-identical")

# --- return frees the borrow but the month still counts it (buyout credit) ---
r = client.post("/api/return", json={"borrow_id": borrow["borrow_id"]}, headers=hdr(tok))
chk(r.get_json().get("returned") is True, "return accepted")
chk(client.get(borrow["url"], headers=hdr(tok)).status_code == 404, "download link dies with the borrow")
chk(client.get("/api/me", headers=hdr(tok)).get_json()["borrows_this_month"] == 1,
    "a returned borrow still counts toward this month")

# --- a short wallet never blocks: it tops itself up in €10 steps and the top-up is recorded ---
code2 = gr_server.make_invite("Skint Resident")
tok2 = join("mac-ddd", invite=code2).get_json()["token"]
client.post("/api/me/plan", json={"plan": "a"}, headers=hdr(tok2))
with closing(gr_server.db()) as conn:
    conn.execute("UPDATE gr_accounts SET wallet_cents=100 WHERE invite_code=?", (code2,))
    conn.commit()
chk(client.post("/api/borrow", json={"track_id": t["id"]}, headers=hdr(tok2)).status_code == 200,
    "a borrow goes through even when the wallet can't cover the sub")
me2 = client.get("/api/me", headers=hdr(tok2)).get_json()
chk(me2["topups_cents"] == 1000 and me2["wallet_cents"] == 100 + 1000 - 600, "…a €10 top-up was recorded and the sub taken from it")

# --- pay-as-you-go: no monthly charge, €0.50 per borrow, fully credited on a buy ---
code3 = gr_server.make_invite("Casual Resident")
tok3 = join("mac-eee", invite=code3).get_json()["token"]
client.post("/api/me/plan", json={"plan": "c"}, headers=hdr(tok3))
w3 = client.get("/api/me", headers=hdr(tok3)).get_json()["wallet_cents"]
client.post("/api/borrow", json={"track_id": t["id"]}, headers=hdr(tok3))
me3 = client.get("/api/me", headers=hdr(tok3)).get_json()
chk(w3 - me3["wallet_cents"] == 50 and me3["credit_cents"] == 50 and me3["per_month"] is None, "pay-as-you-go: €0.50 per borrow, €0.50 credit, no monthly cap")

# a returned borrow still counts against the month (the fee bought the borrows, not the holding)
with closing(gr_server.db()) as conn:
    conn.execute("UPDATE gr_accounts SET plan='b' WHERE invite_code=?", (code3,))   # 10 a month
    conn.commit()
for i in range(9):
    client.post("/api/borrow", json={"track_id": t["id"]}, headers=hdr(tok3)) if i == 0 else None
with closing(gr_server.db()) as conn:
    conn.execute("INSERT INTO gr_borrows(account_id, track_id, key_hex, nonce_hex, month, borrowed_at, returned_at)"
                 " SELECT account_id, track_id, key_hex, nonce_hex, month, borrowed_at, datetime('now') FROM gr_borrows"
                 " WHERE account_id=(SELECT id FROM gr_accounts WHERE invite_code=?) LIMIT 1", (code3,))
    for _ in range(8):
        conn.execute("INSERT INTO gr_borrows(account_id, track_id, key_hex, nonce_hex, month, borrowed_at, returned_at)"
                     " SELECT account_id, track_id, key_hex, nonce_hex, month, borrowed_at, datetime('now') FROM gr_borrows"
                     " WHERE account_id=(SELECT id FROM gr_accounts WHERE invite_code=?) LIMIT 1", (code3,))
    conn.commit()
chk(client.get("/api/me", headers=hdr(tok3)).get_json()["borrows_this_month"] == 10, "ten borrows this month (nine of them returned)")
with closing(gr_server.db()) as conn:
    conn.execute("INSERT INTO gr_tracks(path, filename, title, price_cents, added_at) VALUES(?,?,?,?,?)",
                 (str(wav) + ".other", "other.wav", "another record", 250, "2026-10-21"))
    conn.commit()
    other_id = conn.execute("SELECT id FROM gr_tracks WHERE title='another record'").fetchone()[0]
r = client.post("/api/borrow", json={"track_id": other_id}, headers=hdr(tok3))
chk(r.status_code == 403 and "next month" in r.get_json()["error"], "the eleventh is refused until next month — returning doesn't give borrows back")
with closing(gr_server.db()) as conn:
    conn.execute("DELETE FROM gr_tracks WHERE id=?", (other_id,)); conn.commit()

# --- the activity log: the server wrote its own lines; the app can add batches; feedback lands beside them ---
with closing(gr_server.db()) as conn:
    kinds = {r[0] for r in conn.execute("SELECT DISTINCT kind FROM gr_events")}
chk({"join", "plan", "borrow", "return"} <= kinds, "the server logged join / plan / borrow / return on its own")
ev = client.post("/api/events", json={"events": [{"kind": "page", "data": {"path": "/room"}, "at": "2026-10-21T10:00:00"},
                                                  {"kind": "theme", "data": {"id": "ink"}},
                                                  {"kind": "play", "data": {"title": "x"}}]}, headers=hdr(tok))
chk(ev.get_json()["stored"] == 2, "an app batch of events is stored (a play sent by an older app is dropped)")
with closing(gr_server.db()) as conn:
    row = conn.execute("SELECT * FROM gr_events WHERE kind='page' ORDER BY id DESC LIMIT 1").fetchone()
chk(row["at"] == "2026-10-21T10:00:00" and row["device_id"] is not None, "app events keep the app's time and the device")
fb = client.post("/api/feedback", json={"kind": "bug", "note": "the thing broke", "page": "/room"}, headers=hdr(tok))
chk(fb.status_code == 200, "feedback is stored on the server")
with closing(gr_server.db()) as conn:
    chk(conn.execute("SELECT note FROM gr_feedback").fetchone()[0] == "the thing broke", "…with its note")
chk(client.post("/api/feedback", json={"kind": "bug", "note": ""}, headers=hdr(tok)).status_code == 400, "feedback needs a note")

# --- signup: a profile without an invite, signed in on this device ---
su = client.post("/api/signup", json={"name": "New Resident", "fingerprint": "mac-fff", "device_name": "new laptop", "agreed": True})
chk(su.status_code == 200 and su.get_json()["handle"] == "new-resident" and su.get_json()["token"], "signup makes an account + handle and signs the device in")
su2 = client.post("/api/signup", json={"name": "New Resident", "fingerprint": "mac-ggg", "agreed": True})
chk(su2.get_json()["handle"] == "new-resident-2", "a second profile with the same name gets a distinct handle")
chk(client.get("/api/me", headers=hdr(su.get_json()["token"])).get_json()["name"] == "New Resident", "the signup token works")
chk(client.post("/api/signup", json={"name": "", "fingerprint": "x"}).status_code == 400, "signup needs a name")

# --- usage: Daithí's per-person view ---
rows = gr_server.usage_rows()
me_row = next(r for r in rows if r["name"] == "Test Resident")
chk(me_row["plan"] == "a" and me_row["borrows"] >= 1 and me_row["devices"] == 2 and me_row["last_seen"], "usage rows carry plan, borrows, devices, last seen")
chk("Skint Resident" in gr_server.usage_report() and "€10.00" in gr_server.usage_report(), "the usage report prints top-ups per person")

# --- covers: a folder image is found, served behind auth, flagged in the catalogue ---
from PIL import Image
covered = Path(_tmp.name) / "covered"
covered.mkdir()
with wave.open(str(covered / "has a cover.wav"), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"\x05\x06" * 1600)
Image.new("RGB", (1200, 1200), (180, 90, 40)).save(covered / "cover.jpg")
res = gr_server.add_folder(str(covered))
chk(res["added"] == 1 and res["covers_found"] == 1, "add_folder found the folder cover")
cat = client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"]
covered_t = next(x for x in cat if x["title"] == "has a cover")
plain_t = next(x for x in cat if x["title"] == "test track")
chk(covered_t["has_art"] and covered_t["art_v"] > 0, "catalogue flags the cover + carries a version")
chk(plain_t["has_art"] is False, "a track with no cover anywhere says so")
chk(client.get(f"/api/art/{covered_t['id']}").status_code == 401, "covers need a token too")
art = client.get(f"/api/art/{covered_t['id']}", headers=hdr(tok))
chk(art.status_code == 200 and art.mimetype == "image/jpeg", "the cover is served as a jpeg")
import io
chk(max(Image.open(io.BytesIO(art.data)).size) == 800, "covers are normalised to 800px")
chk(client.get(f"/api/art/{plain_t['id']}", headers=hdr(tok)).status_code == 404, "no cover → 404")

# a cover added AFTER the track was pooled is picked up by `covers`
Image.new("RGB", (400, 400), (20, 60, 90)).save(music / "folder.jpg")
chk(gr_server.fill_covers()["covers_found"] == 1, "fill_covers finds a cover added later")

# --- artists, rooms, buying ---
art_code = gr_server.make_invite("Moss Records", kind="artist", handle="moss", bio="slow music", public=True)
chk(art_code.startswith("gr-"), "an artist account is minted with a handle")
artist_music = Path(_tmp.name) / "artist"
artist_music.mkdir()
with wave.open(str(artist_music / "Tide.wav"), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"\x07\x08" * 1600)
gr_server.add_folder(str(artist_music), price_cents=250, owner="moss")
cat = client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"]
tide = next(x for x in cat if x["title"] == "Tide")
chk(tide["owner_handle"] == "moss" and tide["owner_kind"] == "artist", "a record carries its owner's room")
chk(tide["purchased"] is False and tide["buy_now_cents"] == 250, "unborrowed: buy price is the full price")

# the directory lists the public artist room, not the private listener
rooms = client.get("/api/rooms", headers=hdr(tok)).get_json()["rooms"]
chk([r["handle"] for r in rooms] == ["moss"], "the directory shows only public rooms")
chk(rooms[0]["track_count"] == 1 and rooms[0]["kind"] == "artist", "a room card carries kind + record count")
chk(client.get("/api/rooms?kind=venue", headers=hdr(tok)).get_json()["rooms"] == [], "kind filter narrows")
chk(client.get("/api/rooms?q=slow", headers=hdr(tok)).get_json()["rooms"][0]["handle"] == "moss", "search finds a room by its bio")
chk(client.get("/api/rooms/lookup?name=Moss%20Records", headers=hdr(tok)).get_json()["handle"] == "moss",
    "an artist name resolves to their room")
chk(client.get("/api/rooms/lookup?name=Nobody", headers=hdr(tok)).get_json()["handle"] is None,
    "an unknown name resolves to no room")
room = client.get("/api/rooms/moss", headers=hdr(tok)).get_json()
chk(room["name"] == "Moss Records" and room["tracks"][0]["title"] == "Tide" and room["design"] == {},
    "a room view carries its records + an empty design until one is published")

# designs: the artist signs in, saves two, makes one live, can't delete the live one
atok = join("mac-art", invite=art_code).get_json()["token"]
d1 = client.post("/api/my/room/designs", json={"name": "first", "design": {"bg": "#111"}}, headers=hdr(atok)).get_json()["id"]
d2 = client.post("/api/my/room/designs", json={"name": "draft", "design": {"bg": "#222"}, "css": "h1{color:red}"}, headers=hdr(atok)).get_json()["id"]
mine = client.get("/api/my/room", headers=hdr(atok)).get_json()
chk(len(mine["designs"]) == 2 and mine["designs"][0]["id"] == d1 and mine["designs"][0]["is_live"] == 1,
    "the first design saved becomes live; a second stays a draft")
chk(client.get("/api/rooms/moss", headers=hdr(tok)).get_json()["design"] == {"bg": "#111"},
    "others see the live design, not the draft")
chk(client.delete(f"/api/my/room/designs/{d1}", headers=hdr(atok)).status_code == 409, "the live design can't be deleted")
chk(client.get(f"/api/rooms/moss?design={d2}", headers=hdr(atok)).get_json()["design"] == {"bg": "#222"},
    "the owner can preview a draft design in place of the live one")
chk(client.get(f"/api/rooms/moss?design={d2}", headers=hdr(tok)).get_json()["design"] == {"bg": "#111"},
    "…but anyone else still gets the live one")
chk(client.get("/api/rooms/moss", headers=hdr(atok)).get_json()["mine"] is True
    and client.get("/api/rooms/moss", headers=hdr(tok)).get_json()["mine"] is False, "a room view says whether it's yours")
client.post(f"/api/my/room/designs/{d2}/live", headers=hdr(atok))
chk(client.get("/api/rooms/moss", headers=hdr(tok)).get_json()["css"] == "h1{color:red}", "making the draft live swaps what others see")
chk(client.delete(f"/api/my/room/designs/{d1}", headers=hdr(atok)).status_code == 200, "the old design can go once it isn't live")
client.post("/api/my/room/profile", json={"is_public": False}, headers=hdr(atok))
chk(client.get("/api/rooms", headers=hdr(tok)).get_json()["rooms"] == [], "going private removes the room from the directory")
chk(client.get("/api/rooms/moss", headers=hdr(tok)).status_code == 404, "a private room can't be opened by others")
chk(client.get("/api/rooms/moss", headers=hdr(atok)).status_code == 200, "…but its owner still can")
client.post("/api/my/room/profile", json={"is_public": True}, headers=hdr(atok))

# --- where a room is (Explore → Globe): its owner's own words + a spot; none = universal ---
def profile(tok_, **body): return client.post("/api/my/room/profile", json=body, headers=hdr(tok_))
def listed(): return client.get("/api/rooms", headers=hdr(tok)).get_json()["rooms"][0]
chk(client.get("/api/my/room", headers=hdr(atok)).get_json()["place"] is None, "a room starts nowhere in particular")
chk("place" in listed() and listed()["place"] is None, "the directory says so too (place: none)")
p = profile(atok, place={"name": "  Baile  Átha Cliath ", "lat": 53.3498, "lon": -6.2603})
chk(p.status_code == 200 and p.get_json()["place"] == {"name": "Baile Átha Cliath", "lat": 53.3498, "lon": -6.2603},
    "the owner sets a place: the name kept as typed (tidied spaces), the spot as picked")
chk(listed()["place"] == {"name": "Baile Átha Cliath", "lat": 53.3498, "lon": -6.2603}, "the directory carries the room's place")
chk(client.get("/api/rooms/moss", headers=hdr(tok)).get_json()["place"]["name"] == "Baile Átha Cliath", "so does the room itself")
p = profile(atok, bio="slower music")
chk(p.get_json()["place"] is not None and p.get_json()["bio"] == "slower music",
    "a profile save that doesn't mention the place leaves it alone (an older app can't wipe it)")
for bad, why in (({"name": "x", "lat": 91, "lon": 0}, "a latitude off the globe"),
                 ({"name": "x", "lat": 0, "lon": -181}, "a longitude off the globe"),
                 ({"name": "x", "lat": "north", "lon": 3}, "words where the numbers go"),
                 ({"name": "x", "lat": True, "lon": 3}, "a yes/no where a number goes"),
                 ({"name": "somewhere"}, "a name with no spot"),
                 ({"name": "x", "lat": 12.5}, "half a spot"),
                 ("Dublin", "a bare word")):
    r = profile(atok, place=bad)
    chk(r.status_code == 400 and r.get_json().get("error"), f"refused with a plain reason: {why}")
chk(listed()["place"]["lat"] == 53.3498, "…and a refused place changes nothing")
p = profile(atok, place={"name": "n" * 300, "lat": -90, "lon": 180})
chk(p.status_code == 200 and len(p.get_json()["place"]["name"]) == gr_server.PLACE_NAME_MAX
    and p.get_json()["place"]["lat"] == -90 and p.get_json()["place"]["lon"] == 180, "the poles and the date line are places; a long name is cut")
p = profile(atok, place={"lat": 5.6037, "lon": -0.187})
chk(p.status_code == 200 and p.get_json()["place"] == {"name": "", "lat": 5.6037, "lon": -0.187}, "a spot with no name is allowed")
p = profile(atok, place=None)
chk(p.status_code == 200 and p.get_json()["place"] is None and listed()["place"] is None, "place: null takes the room off the globe again")
profile(atok, place={"name": "Corcaigh", "lat": 51.8985, "lon": -8.4756})
chk(client.get("/api/my/room", headers=hdr(tok)).get_json()["place"] is None, "one person's place is not another's")
profile(atok, is_public=False)
chk(client.get("/api/rooms", headers=hdr(tok)).get_json()["rooms"] == [], "a private room's place is in no listing")
profile(atok, is_public=True, place=None)

# a database from before places gains the three columns on start, and its rooms read as universal
import sqlite3 as _sq
_old = Path(_tmp.name) / "old_pool.db"
with closing(_sq.connect(_old)) as oc:
    oc.row_factory = _sq.Row
    oc.executescript("""CREATE TABLE gr_accounts(id INTEGER PRIMARY KEY, name TEXT NOT NULL, invite_code TEXT NOT NULL UNIQUE,
        wallet_cents INTEGER NOT NULL, sub_month TEXT, created_at TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'listener',
        handle TEXT, bio TEXT, links TEXT, is_public INTEGER NOT NULL DEFAULT 0, plan TEXT);
        INSERT INTO gr_accounts(name, invite_code, wallet_cents, created_at, kind, handle, is_public)
        VALUES('Old Room', 'gr-old', 0, '2026-10-01', 'artist', 'old-room', 1);""")
    before_cols = {r[1] for r in oc.execute("PRAGMA table_info(gr_accounts)")}
    gr_server.init_db(oc); oc.commit()
    after_cols = {r[1] for r in oc.execute("PRAGMA table_info(gr_accounts)")}
    row = oc.execute("SELECT * FROM gr_accounts WHERE handle='old-room'").fetchone()
    chk(not ({"place_name", "lat", "lon"} & before_cols) and {"place_name", "lat", "lon"} <= after_cols,
        "an older database gains place_name / lat / lon on start")
    chk(row["name"] == "Old Room" and gr_server._place_of(row) is None, "its rooms are kept and read as nowhere in particular")
    gr_server.init_db(oc)
    chk({r[1] for r in oc.execute("PRAGMA table_info(gr_accounts)")} == after_cols, "starting twice adds nothing twice")

# buying: borrow first → the per-track credit comes off the price; artist gets the full price
# (listener already paid this month's €5 sub above and has borrowed 1 track → credit €5)
b2 = client.post("/api/borrow", json={"track_id": tide["id"]}, headers=hdr(tok)).get_json()
me = client.get("/api/me", headers=hdr(tok)).get_json()
chk(me["borrows_this_month"] == 2 and me["credit_cents"] == 300, "two borrows on a €6 sub → €3.00 credit per track")
wallet_before = me["wallet_cents"]
buy = client.post("/api/buy", json={"track_id": tide["id"]}, headers=hdr(tok)).get_json()
chk(buy["bought"] and buy["paid_cents"] == 0 and buy["artist_cents"] == 250,
    "credit covers the €2.50 price: listener pays €0, artist is paid €2.50")
chk(client.get("/api/me", headers=hdr(tok)).get_json()["wallet_cents"] == wallet_before, "a free buyout takes nothing from the wallet")
chk(client.get(b2["url"], headers=hdr(tok)).status_code == 404, "buying ends the borrow (locked download gone)")
plain = client.get(buy["url"], headers=hdr(tok))
chk(plain.status_code == 200 and plain.data == (artist_music / "Tide.wav").read_bytes(),
    "the bought file arrives PLAIN, byte-identical to the original")
cat = client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"]
chk(next(x for x in cat if x["id"] == tide["id"])["purchased"] is True, "the catalogue marks it purchased")
chk(client.post("/api/buy", json={"track_id": tide["id"]}, headers=hdr(tok)).get_json().get("already") is True,
    "buying twice is harmless")
chk(client.get(buy["url"], headers=hdr(tok2)).status_code == 403, "someone who didn't buy it can't fetch the plain file")

# an unborrowed buy pays the full price
cat_t = next(x for x in cat if x["title"] == "test track")
w0 = client.get("/api/me", headers=hdr(tok)).get_json()["wallet_cents"]
client.post("/api/return", json={"borrow_id": cat_t["borrow_id"]}, headers=hdr(tok)) if cat_t["borrow_id"] else None
buy2 = client.post("/api/buy", json={"track_id": cat_t["id"]}, headers=hdr(tok)).get_json()
chk(buy2["paid_cents"] == 0 and buy2["credit_cents"] == 300,
    "a track borrowed this month keeps its credit even after being returned")
chk(client.get("/api/me", headers=hdr(tok)).get_json()["wallet_cents"] == w0, "…so that buyout was free too")


# --- the one switch at the top of My Public Room sends ONLY "public or not": the rest of the profile stays ---
_me0 = client.get("/api/my/room", headers=hdr(atok)).get_json()
_on = client.post("/api/my/room/profile", json={"is_public": not _me0["is_public"]}, headers=hdr(atok)).get_json()
chk(_on["is_public"] == (not _me0["is_public"]) and all(_on.get(k) == _me0.get(k) for k in ("name", "handle", "bio", "links")),
    "public or private can be switched by itself: name, address, words and links stay as they were")
client.post("/api/my/room/profile", json={"is_public": _me0["is_public"]}, headers=hdr(atok))

# --- room images: upload, serve publicly, list, delete ---
import io as _io
buf = _io.BytesIO(); Image.new("RGB", (2400, 1200), (90, 60, 30)).save(buf, "JPEG"); buf.seek(0)
up = client.post("/api/my/room/assets", data={"rights": "1", "image": (buf, "big.jpg"), "label": "a wide one"}, headers=hdr(atok),
                 content_type="multipart/form-data")
chk(up.status_code == 200 and up.get_json()["width"] == 1800, "an image uploads and is resized to 1800px on the long side")
aid = up.get_json()["id"]
pub = client.get(f"/api/assets/{aid}")
chk(pub.status_code == 200 and pub.mimetype == "image/jpeg", "the image is served publicly (rooms are for everyone)")
chk(client.get("/api/my/room/assets", headers=hdr(atok)).get_json()["assets"][0]["label"] == "a wide one", "it's listed with its label")
chk(client.delete(f"/api/my/room/assets/{aid}", headers=hdr(atok)).status_code == 200 and client.get(f"/api/assets/{aid}").status_code == 404, "deleted images are gone")
bad = client.post("/api/my/room/assets", data={"rights": "1", "image": (_io.BytesIO(b"not an image"), "x.jpg")}, headers=hdr(atok), content_type="multipart/form-data")
chk(bad.status_code == 400, "a non-image is refused politely")
side = Image.new("RGB", (600, 400), (10, 120, 200)); ex = side.getexif(); ex[0x0112] = 6
buf = _io.BytesIO(); side.save(buf, "JPEG", exif=ex); buf.seek(0)
up = client.post("/api/my/room/assets", data={"rights": "1", "image": (buf, "phone.jpg")}, headers=hdr(atok), content_type="multipart/form-data")
chk(up.status_code == 200 and (up.get_json()["width"], up.get_json()["height"]) == (400, 600),
    "a phone photo stored on its side is kept the right way up")
client.delete(f"/api/my/room/assets/{up.get_json()['id']}", headers=hdr(atok))

# --- an artist uploads a record from the app; a listener can't ---
wbuf = _io.BytesIO()
with wave.open(wbuf, "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\x01\x01" * 4000)
wbuf.seek(0)
wav_bytes = wbuf.getvalue()          # the test client closes uploaded files — keep the bytes
cbuf = _io.BytesIO(); Image.new("RGB", (500, 500), (20, 90, 70)).save(cbuf, "JPEG"); cbuf.seek(0)
r = client.post("/api/my/records", data={"rights": "1", "audio": (wbuf, "Low Tide.wav"), "cover": (cbuf, "c.jpg"), "title": "Low Tide",
                                          "price_cents": "350", "buy_url": "https://example.bandcamp.com"},
                headers=hdr(atok), content_type="multipart/form-data")
chk(r.status_code == 200 and r.get_json()["title"] == "Low Tide", "an artist uploads a record with a cover and a price")
rid = r.get_json()["id"]
mine = client.get("/api/my/records", headers=hdr(atok)).get_json()
rec = next(x for x in mine["records"] if x["id"] == rid)
chk(mine["can_sell"] and rec["price_cents"] == 350 and rec["has_art"] and rec["artist"] == "Moss Records" and rec["duration_s"] == 0.5,
    "it's listed with price, cover, the artist's name, and its length")
# a new record waits for the master (gr_master.py; the master's own side is tested in test_gr_master.py)
chk(rec["status"] == "pending" and not any(t["id"] == rid for t in client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"])
    and client.get(f"/api/art/{rid}", headers=hdr(tok)).status_code == 404
    and client.post("/api/borrow", json={"track_id": rid}, headers=hdr(tok)).status_code == 404,
    "a new record waits for the master: nobody else can see, hear or borrow it yet")
with closing(gr_server.db()) as _c:
    _c.execute("UPDATE gr_tracks SET status='live' WHERE id=?", (rid,)); _c.commit()
chk(any(t["id"] == rid and t["owner_handle"] == "moss" for t in client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"]),
    "the record is in the pool under the artist's room")
chk(client.get(f"/api/art/{rid}", headers=hdr(tok)).status_code == 200, "its cover serves")
client.post(f"/api/my/records/{rid}", json={"price_cents": 400}, headers=hdr(atok))
chk(next(x for x in client.get("/api/my/records", headers=hdr(atok)).get_json()["records"] if x["id"] == rid)["price_cents"] == 400, "the price can change")
l = client.post("/api/my/records", data={"rights": "1", "audio": (_io.BytesIO(b"x"), "y.mp3")}, headers=hdr(tok), content_type="multipart/form-data")
chk(l.status_code == 403, "a listener can't upload records")
m4a = client.post("/api/my/records", data={"rights": "1", "audio": (_io.BytesIO(b"x"), "y.m4a")}, headers=hdr(atok), content_type="multipart/form-data")
chk(m4a.status_code == 400, "m4a is refused (it can't play as a borrow)")
client.post("/api/borrow", json={"track_id": rid}, headers=hdr(tok))
chk(client.delete(f"/api/my/records/{rid}", headers=hdr(atok)).status_code == 409, "a record someone has borrowed can't be deleted")
r2 = client.post("/api/my/records", data={"rights": "1", "audio": (_io.BytesIO(wav_bytes), "Spare.wav")}, headers=hdr(atok), content_type="multipart/form-data")
chk(client.delete(f"/api/my/records/{r2.get_json()['id']}", headers=hdr(atok)).status_code == 200, "an untouched record can be removed")

# --- public grúpaí (2026-11-15): words, links and small covers — never audio, never a path ---
import base64
def jpeg(side=48, colour=(180, 103, 63)):
    b = _io.BytesIO(); Image.new("RGB", (side, side), colour).save(b, "JPEG"); return b.getvalue()
b64 = lambda blob: base64.b64encode(blob).decode("ascii")
chk(client.get("/api/grupai").status_code == 401 and client.post("/api/my/grupai", json={"local_id": 1, "name": "x"}).status_code == 401,
    "public grúpaí need a token, to read and to send")
chk(client.get("/api/grupai", headers=hdr(tok)).get_json() == {"grupai": []}, "none to begin with")
PAY = {
    "local_id": 7, "name": "  Slow  mornings ", "description": "for the first hour", "file_path": "/Users/someone/secret",
    "cover": {"kind": "image", "art": "cover", "path": "/Users/someone/cover.jpg"},
    "items": [
        {"kind": "stream", "where": "stream", "title": "A stream", "subtitle": "Someone", "url": "https://open.spotify.com/track/abc", "source": "spotify",
         "stream_type": "track", "image": "https://i.scdn.co/image/x", "duration_sec": "201.26", "note": "why it is here"},
        {"kind": "track", "where": "campus", "title": "Low Tide", "subtitle": "Moss Records", "server_track_id": rid, "art": "0", "file_path": "/Volumes/X/low tide.flac"},
        {"kind": "track", "where": "local", "title": "Only Mine", "subtitle": "Nobody", "album": "An Album", "year": "1994", "path": "/Users/someone/only mine.mp3"},
        {"kind": "track", "where": "own", "title": "My Own", "subtitle": "Me"},
        {"kind": "label", "where": "name", "title": "Good Label", "count": 4},
        {"kind": "room", "where": "room", "title": "Moss", "handle": "moss"},
        {"kind": "link", "where": "link", "title": "Bad link", "url": "javascript:alert(1)"},
        {"kind": "virus", "title": "not a kind"},
        "not even a thing",
    ],
    "art": {"cover": b64(jpeg(64)), "0": b64(jpeg()), "bad key!": b64(jpeg()), "notjpeg": b64(b"GIF89a" + b"0" * 40),
            "huge": b64(b"\xff\xd8\xff" + b"0" * (gr_server.GRUPA_MAX_ART_BYTES + 10)), "junk": "%%%not base64%%%"},
}
r = client.post("/api/my/grupai", json=PAY, headers=hdr(tok))
gid = r.get_json().get("id")
chk(r.status_code == 200 and gid and r.get_json()["count"] == 7, "a grúpa goes up; things of no known kind are left out")
cards = client.get("/api/grupai", headers=hdr(tok)).get_json()["grupai"]
card = cards[0] if cards else {}
chk(len(cards) == 1 and card["name"] == "Slow mornings" and card["count"] == 7 and card["mine"] is True
    and card["cover"] == {"kind": "image", "art": "cover", "image": f"/api/grupai/{gid}/art/cover"} and card["owner"]["name"] == "Test Resident",
    "it is listed: its name tidied, its cover's address, who made it")
chk(card["owner"]["handle"] is None, "its maker's room is offered only if that room is public (this one isn't)")
chk(client.get("/api/grupai", headers=hdr(atok)).get_json()["grupai"][0]["mine"] is False, "to someone else it is not theirs")
one = client.get(f"/api/grupai/{gid}", headers=hdr(atok)).get_json()
its = {i["title"]: i for i in one["items"]}
flat = repr(one)
chk("/Users/" not in flat and "/Volumes/" not in flat and "file_path" not in flat and "path" not in {k for i in one["items"] for k in i},
    "nothing that looks like a file path was kept, anywhere")
chk(its["A stream"]["url"] == "https://open.spotify.com/track/abc" and its["A stream"]["duration_sec"] == 201.3 and its["A stream"]["note"] == "why it is here",
    "a stream keeps its link, its length and the note")
chk(its["Low Tide"]["room"] == {"handle": "moss", "name": "Moss Records"} and its["Low Tide"]["image"] == f"/api/grupai/{gid}/art/0",
    "a record that lives here points to the room it can be borrowed or bought in, and has its small cover")
chk(its["Only Mine"]["where"] == "local" and its["Only Mine"]["year"] == 1994 and its["My Own"]["where"] == "own", "a file on its owner's laptop only, and their own work, say so")
chk(its["Bad link"]["where"] == "name" and "url" not in its["Bad link"], "a link that isn't a web address is dropped (the name stays)")
chk(client.get(f"/api/grupai/{gid}/art/cover").status_code == 200 and client.get(f"/api/grupai/{gid}/art/0").data[:3] == b"\xff\xd8\xff",
    "its pictures serve without a token, like a room's images")
chk(all(client.get(f"/api/grupai/{gid}/art/{k}").status_code == 404 for k in ("notjpeg", "huge", "junk", "nope", "..%2f..%2fgr_test")),
    "only small JPEGs under plain keys were kept")
PAY2 = dict(PAY, name="Slow mornings", items=PAY["items"][:1], art={}, cover={"kind": "text", "font": "Fraunces", "bg": "#34557E", "ink": "#f2efe8"})
r2 = client.post("/api/my/grupai", json=PAY2, headers=hdr(tok)).get_json()
card = client.get("/api/grupai", headers=hdr(tok)).get_json()["grupai"][0]
chk(r2["id"] == gid and card["count"] == 1 and card["cover"] == {"kind": "text", "font": "Fraunces", "bg": "#34557e", "ink": "#f2efe8"}
    and client.get(f"/api/grupai/{gid}/art/cover").status_code == 404,
    "sent again it is the same grúpa, changed: one thing in it, a cover in type, the old pictures gone")
gm = client.post("/api/my/grupai", json={"local_id": 7, "name": "Moss picks", "description": "tides", "items": [PAY["items"][0]]}, headers=hdr(atok)).get_json()["id"]
chk(gm != gid, "the same number in two people's apps is two grúpaí")
chk([g["id"] for g in client.get("/api/grupai?handle=moss", headers=hdr(tok)).get_json()["grupai"]] == [gm]
    and [g["id"] for g in client.get("/api/grupai?q=tides", headers=hdr(tok)).get_json()["grupai"]] == [gm]
    and [g["id"] for g in client.get("/api/grupai?q=resident", headers=hdr(tok)).get_json()["grupai"]] == [gid],
    "they can be narrowed to one room, or found by a word in the name, what it is, or who made it")
room = client.get("/api/rooms/moss", headers=hdr(tok)).get_json()
chk([g["id"] for g in room["grupai"]] == [gm] and room["grupai"][0]["owner"]["handle"] == "moss", "a room carries its owner's public grúpaí")
chk(client.delete("/api/my/grupai/7", headers=hdr(atok)).get_json() == {"private": True, "was_public": True}
    and [g["id"] for g in client.get("/api/grupai", headers=hdr(tok)).get_json()["grupai"]] == [gid],
    "made private, it leaves — and only its owner's, though the numbers match")
chk(client.delete("/api/my/grupai/7", headers=hdr(atok)).get_json() == {"private": True, "was_public": False}, "taking down one that isn't up is fine")
chk(client.get(f"/api/grupai/{gm}", headers=hdr(tok)).status_code == 404, "…and it can no longer be opened")
chk(client.post("/api/my/grupai", json={"local_id": "x", "name": "n"}, headers=hdr(tok)).status_code == 400
    and client.post("/api/my/grupai", json={"local_id": 9, "name": "   "}, headers=hdr(tok)).status_code == 400, "one with no number or no name is refused")
client.delete("/api/my/grupai/7", headers=hdr(tok))
chk(not (gr_server.grupa_art_dir() / str(gid)).exists() and client.get("/api/grupai", headers=hdr(tok)).get_json() == {"grupai": []}, "nothing is left behind")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
