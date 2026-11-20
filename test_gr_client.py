"""Green Room app side — green_room.py against a real gr_server, end to end:
join → catalogue → borrow (encrypted download) → decrypt → offload →
redownload → return. Run:  ./venv/bin/python test_gr_client.py"""
import os
import sys
import tempfile
import threading
import wave
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_server.db")      # the server's db
os.environ["MUSICROOM_DATA"] = str(TMP / "app_data")    # the app's data dir
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")   # keep David's library out
(TMP / "app_data").mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# ─── the campus server, for real, on a local port ───
import gr_server

music = TMP / "music"; music.mkdir()
wav = music / "pool track.wav"
with wave.open(str(wav), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"\x03\x04" * 2000)
from PIL import Image
Image.new("RGB", (600, 600), (120, 60, 30)).save(music / "cover.jpg")
with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
gr_server.add_folder(str(music))
code = gr_server.make_invite("Client Test")

from werkzeug.serving import make_server
srv = make_server("127.0.0.1", 0, gr_server.app)
port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
SERVER = f"http://127.0.0.1:{port}"

# ─── the app side: a REAL fresh app database (schema + every migration),
#     because borrows now become track rows in the room ───
import contextlib
import io
import sqlite3

import mr_paths
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database()
    migrate.run_migration()

def appdb():
    c = sqlite3.connect(mr_paths.DB_PATH); c.row_factory = sqlite3.Row; return c

import green_room

# join: a dead address fails politely, the real one succeeds
try:
    green_room.join("http://127.0.0.1:1", code)
    chk(False, "a dead server address raises GRError")
except green_room.GRError:
    chk(True, "a dead server address raises GRError")
try:
    green_room.join(SERVER, "gr-wrong")
    chk(False, "a wrong invite code raises GRError")
except green_room.GRError as e:
    chk("invite" in str(e) or "refused" in str(e), "a wrong invite code raises GRError")
joined = green_room.join(SERVER, code, "test laptop")
chk(joined["joined"] and joined["name"] == "Client Test", "join succeeds and carries the name")
chk([p["key"] for p in green_room.plans()] == ["a", "b", "c"], "the plans read through the client")
chk(green_room.has_plan() is False, "no plan yet")
try:
    green_room.borrow(1)
    chk(False, "borrowing before choosing a plan is refused")
except green_room.GRError as e:
    chk("subscription" in str(e), "borrowing before choosing a plan is refused")
chk(green_room.choose_plan("a")["plan"] == "a" and green_room.has_plan() is True, "plan A chosen through the client")

st = green_room.status()
chk(st["joined"] and st["reachable"] and st["me"]["wallet_cents"] == gr_server.PLAY_MONEY_START_CENTS,
    "status reports joined + reachable + the full wallet")

cat = green_room.catalogue()
chk(len(cat) == 1 and cat[0]["local_id"] is None, "catalogue lists the pool, nothing borrowed")

# borrow: downloads encrypted, decrypts byte-identical, never plain on disk
b = green_room.borrow(cat[0]["id"])
chk(b is not None and b["file_path"], "borrow lands a local file")
enc = Path(b["file_path"]).read_bytes()
original = wav.read_bytes()
chk(enc != original, "the file on disk is NOT the plain audio")
chk(str(green_room.GR_DIR) in b["file_path"], "borrowed files live under DATA_DIR/green_room")
dec = green_room.decrypt_file(b["file_path"], b["key_hex"], b["nonce_hex"])
chk(dec == original, "decrypt_file recovers the original bytes exactly")
chk(b["duration_s"] and b["price_cents"] == gr_server.DEFAULT_TRACK_PRICE_CENTS,
    "catalogue metadata (duration, price) filled onto the borrow")

cat = green_room.catalogue()
chk(cat[0]["local_id"] == b["id"] and cat[0]["on_disk"], "catalogue shows it borrowed + on disk")

shelf = green_room.borrowed_list()
chk(len(shelf) == 1 and shelf[0]["on_disk"], "the shelf lists it on disk")
chk("key_hex" not in shelf[0] and "file_path" not in shelf[0], "keys and paths stay out of UI payloads")

# the borrow is now a RECORD in the room: a tracks row + a locked files row, in the Well
with closing(appdb()) as c:
    trow = c.execute("SELECT * FROM tracks WHERE gr_borrow_id=?", (b["id"],)).fetchone()
    chk(trow is not None and trow["title"] == "pool track", "borrowing makes a tracks row, marked with gr_borrow_id")
    frow = c.execute("SELECT * FROM files WHERE track_id=?", (trow["id"],)).fetchone()
    chk(frow["file_path"] == b["file_path"] and frow["analysis_status"] == "locked" and frow["is_primary"] == 1,
        "its files row points at the locked file, analysis_status='locked'")
    chk(c.execute("SELECT 1 FROM place_tracks pt JOIN places p ON p.id=pt.place_id WHERE pt.track_id=? AND p.is_well=1",
                  (trow["id"],)).fetchone() is not None, "the record is in the Well")
    chk(trow["artwork_path"] and Path(trow["artwork_path"]).exists(), "the record wears the pool's cover")
    chk(c.execute("SELECT track_id FROM gr_borrows WHERE id=?", (b["id"],)).fetchone()[0] == trow["id"],
        "the borrow knows its track row")
TRACK_ID = trow["id"]
chk(green_room.borrow_of_track(TRACK_ID)["on_disk"] is True, "borrow_of_track finds the active borrow")

# the guards: no exporter/organiser/analysis pass may pick the locked file up
with closing(appdb()) as c:
    chk(c.execute("SELECT COUNT(*) FROM files WHERE has_analysis=0 AND is_deleted=0"
                  " AND (analysis_status IS NULL OR analysis_status NOT IN ('empty','missing','locked'))").fetchone()[0] == 0,
        "the analysis queue skips the locked file")
import organiser
with closing(sqlite3.connect(mr_paths.DB_PATH)) as c:
    c.row_factory = sqlite3.Row
    chk(all(f["file_path"] != b["file_path"] for f in organiser.get_all_files(c)),
        "the organiser never sees the locked file")

# covers: the borrow cached its cover locally, and it survives the server going away
art_cached = list((green_room.GR_DIR / "art").glob(f"{cat[0]['id']}_*.jpg"))
chk(len(art_cached) == 1, "borrowing caches the record's cover locally")
cp = green_room.cover_path(cat[0]["id"])
chk(cp and Path(cp).exists(), "cover_path returns the cached cover")
cat_now = green_room.catalogue()
chk(cat_now[0]["has_art"] and cat_now[0]["art_v"] > 0, "catalogue carries has_art + art_v through")
v = cat_now[0]["art_v"]
chk(green_room.cover_path(cat[0]["id"], v).endswith(f"{cat[0]['id']}_{v}.jpg"),
    "a versioned request lands on the versioned cache file")
chk(len(list((green_room.GR_DIR / "art").glob(f"{cat[0]['id']}_*.jpg"))) == 1,
    "older cached versions are cleaned up")

# the player-facing item resolution shape
row = green_room.borrow_row(b["id"])
chk(row and row["key_hex"] and row["nonce_hex"] and row["file_path"], "borrow_row carries key material for the player")

# offload: the bytes leave, the borrow — and the record — stay
off = green_room.offload(b["id"])
chk(not Path(b["file_path"]).exists(), "offload deletes the encrypted file")
chk(green_room.borrowed_list()[0]["on_disk"] is False, "the shelf shows it offloaded")
chk(green_room.borrow_row(b["id"])["file_path"] is None, "an offloaded borrow resolves to no playable path")
with closing(appdb()) as c:
    chk(c.execute("SELECT is_deleted FROM tracks WHERE id=?", (TRACK_ID,)).fetchone()[0] == 0,
        "the record stays in the room while offloaded")

# redownload: back on disk, still decrypts, same record (no duplicate row)
re = green_room.redownload(b["id"])
chk(re["file_path"] and Path(re["file_path"]).exists(), "redownload brings the bytes back")
chk(green_room.decrypt_file(re["file_path"], re["key_hex"], re["nonce_hex"]) == original,
    "a redownloaded file still decrypts byte-identical")
with closing(appdb()) as c:
    chk(c.execute("SELECT COUNT(*) FROM tracks WHERE gr_borrow_id=?", (b["id"],)).fetchone()[0] == 1,
        "redownload reuses the record row rather than making another")
    chk(c.execute("SELECT file_path FROM files WHERE track_id=?", (TRACK_ID,)).fetchone()[0] == re["file_path"],
        "the files row points at the fresh locked file")

# a second borrow of the same track doesn't double-charge (server idempotence)
wallet_before = green_room.status()["me"]["wallet_cents"]
green_room.borrow(cat[0]["id"])
chk(green_room.status()["me"]["wallet_cents"] == wallet_before, "re-borrowing charges nothing")
chk(len(green_room.borrowed_list()) == 1, "re-borrowing doesn't duplicate the shelf row")

# return: server told, file gone, shelf empty, record retired from the room
out = green_room.give_back(b["id"])
chk(out["returned"] is True, "return accepted")
chk(green_room.borrowed_list() == [], "the shelf is empty after return")
chk(not Path(re["file_path"]).exists(), "the file left with the return")
with closing(appdb()) as c:
    chk(c.execute("SELECT is_deleted FROM tracks WHERE id=?", (TRACK_ID,)).fetchone()[0] == 1,
        "the returned record is retired (soft-deleted, never hard-deleted)")
    chk(c.execute("SELECT COUNT(*) FROM place_tracks WHERE track_id=?", (TRACK_ID,)).fetchone()[0] == 0,
        "…and leaves the Well")

# buy: borrow again, then buy outright → the plain file replaces the locked one and
# the record becomes an ordinary one of theirs (gr_borrow_id cleared, analysis free)
b3 = green_room.borrow(cat[0]["id"])
tid3 = green_room.borrow_of_track(b3["track_id"])["track_id"]
sale = green_room.buy(b3["id"])
chk(sale["bought"] is True, "buy accepted")
chk(Path(sale["path"]).exists() and Path(sale["path"]).read_bytes() == original,
    "the PLAIN file landed, byte-identical to the pool's original")
chk(str(green_room.GR_DIR / "bought") in sale["path"], "with no library folder set, bought files go under the app's data")
chk(not Path(b3["file_path"]).exists(), "the locked file is gone")
with closing(appdb()) as c:
    t3 = c.execute("SELECT * FROM tracks WHERE id=?", (tid3,)).fetchone()
    f3 = c.execute("SELECT * FROM files WHERE track_id=?", (tid3,)).fetchone()
    chk(t3["gr_borrow_id"] is None and t3["is_deleted"] == 0, "the record is no longer a borrow — it's theirs, still in the room")
    chk(f3["file_path"] == sale["path"] and f3["analysis_status"] is None, "its files row now points at the plain file, open to analysis")
chk(green_room.borrowed_list() == [], "a bought record leaves the borrowed shelf")
chk(green_room.catalogue()[0]["purchased"] is True, "the pool marks it purchased")

# rooms: an artist's public room is listed, opened, found by name; buying straight
# from it (no borrow first) lands a NEW plain record in the room
art_code = gr_server.make_invite("Moss Records", kind="artist", handle="moss", bio="slow music", public=True)
amusic = TMP / "artist"; amusic.mkdir()
with wave.open(str(amusic / "Tide.wav"), "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"\x09\x0a" * 2000)
gr_server.add_folder(str(amusic), price_cents=300, owner="moss")
rooms = green_room.rooms()
chk([r["handle"] for r in rooms] == ["moss"] and rooms[0]["kind"] == "artist", "the directory lists the artist's public room")
chk(green_room.rooms(kind="venue") == [], "the kind filter reaches the server")
chk(green_room.room_lookup("Moss Records") == "moss" and green_room.room_lookup("nobody") is None, "an artist name resolves to a room (or not)")
rm = green_room.room("moss")
chk(rm["name"] == "Moss Records" and rm["tracks"][0]["title"] == "Tide" and rm["mine"] is False, "a room opens with its records")
tide = rm["tracks"][0]
me0 = green_room.status()["me"]
sale2 = green_room.buy_track(tide["id"])
chk(sale2["bought"] and sale2["paid_cents"] == 300, "buying an unborrowed record pays the full price")
me1 = green_room.status()["me"]
chk(me1["wallet_cents"] - me0["wallet_cents"] == (me1["topups_cents"] - me0["topups_cents"]) - 300,
    "…from the wallet (topping up in €10 steps if it was short)")

# the basket: set records aside, flip a line between borrow and buy, check out
chk(green_room.basket() == [], "the basket starts empty")
green_room.basket_add(tide["id"], "borrow")
green_room.basket_add(cat[0]["id"], "buy")
bk = green_room.basket()
chk(len(bk) == 2 and bk[0]["title"] == "Tide" and bk[0]["owner_handle"] == "moss" and bk[0]["mode"] == "borrow",
    "basket lines carry title, owner and mode")
green_room.basket_add(tide["id"], "buy")
chk(len(green_room.basket()) == 2 and green_room.basket()[0]["mode"] == "buy", "adding the same record again just updates its mode")
green_room.basket_mode(bk[0]["id"], "borrow")
chk(green_room.basket()[0]["mode"] == "borrow", "a line flips back to borrow")
green_room.basket_remove(bk[1]["id"])
chk(len(green_room.basket()) == 1, "a line can be removed")
out = green_room.basket_checkout()
chk(out["results"][0]["ok"] is True and out["results"][0]["mode"] == "borrow" and out["basket"] == [],
    "checkout borrows the line and empties the basket")
chk(any(b["title"] == "Tide" for b in green_room.borrowed_list()), "the checked-out record is now borrowed")

# activity: app-side events queue locally and flush to the server in a batch
with closing(appdb()) as c:
    queued_before = c.execute("SELECT COUNT(*) FROM gr_events_outbox").fetchone()[0]
chk(queued_before >= 3, "basket / offload / redownload activity queued along the way")
green_room.track("page", {"path": "/room"})
green_room.track("play", {"title": "Tide", "kind": "borrow"})
with closing(appdb()) as c:
    chk(c.execute("SELECT COUNT(*) FROM gr_events_outbox").fetchone()[0] == queued_before + 2, "two more events queued locally")
chk(green_room.flush_events() == queued_before + 2, "flush sends everything queued")
with closing(appdb()) as c:
    chk(c.execute("SELECT COUNT(*) FROM gr_events_outbox").fetchone()[0] == 0, "…and empties the queue")
with closing(gr_server.db()) as c:
    chk(c.execute("SELECT COUNT(*) FROM gr_events WHERE kind IN ('page','play')").fetchone()[0] == 2, "the server has the page + play")
    chk(c.execute("SELECT COUNT(*) FROM gr_events WHERE kind='basket_add'").fetchone()[0] >= 1, "…and the basket activity")
chk(green_room.send_feedback("idea", "a thought from the app", "/room") is True, "feedback forwards to the server")
with closing(gr_server.db()) as c:
    chk(c.execute("SELECT note FROM gr_feedback ORDER BY id DESC LIMIT 1").fetchone()[0] == "a thought from the app", "…and is stored there")
chk(Path(sale2["path"]).read_bytes() == (amusic / "Tide.wav").read_bytes(), "the plain file arrived byte-identical")
with closing(appdb()) as c:
    t = c.execute("SELECT * FROM tracks WHERE id=?", (sale2["track_id"],)).fetchone()
    f = c.execute("SELECT * FROM files WHERE track_id=?", (t["id"],)).fetchone()
    chk(t["title"] == "Tide" and t["artist_name"] is None and t["gr_borrow_id"] is None and t["source_type"] == "green_room",
        "it's a new ordinary record, marked as coming from the Green Room")
    chk(f["file_path"] == sale2["path"] and f["analysis_status"] != "locked", "with a plain file row, open to analysis")
    chk(c.execute("SELECT 1 FROM place_tracks pt JOIN places p ON p.id=pt.place_id WHERE pt.track_id=? AND p.is_well=1",
                  (t["id"],)).fetchone() is not None, "and it's in the Well")
chk(green_room.room("moss")["tracks"][0]["purchased"] is True, "the room now shows it as yours")

# my room: profile + designs round-trip through the client
atok_join = green_room.join(SERVER, art_code, "artist laptop")      # switch this laptop to the artist account
mine = green_room.my_room()
chk(mine["handle"] == "moss" and mine["designs"] == [], "my room reads back, no designs yet")
d = green_room.save_design({"name": "first", "design": {"bg": "#101010", "items": [{"title": "A pick"}]}, "css": "h1{}"})
mine = green_room.my_room()
chk(mine["designs"][0]["id"] == d["id"] and mine["designs"][0]["is_live"] == 1 and mine["designs"][0]["design"]["items"][0]["title"] == "A pick",
    "a saved design comes back live, with its picks")
chk(green_room.my_room_profile({"bio": "slower music", "is_public": False})["is_public"] is False, "the profile updates (public off)")
chk(green_room.room("moss")["mine"] is True and green_room.room("moss")["bio"] == "slower music", "the owner still opens their private room")
d2 = green_room.save_design({"name": "draft", "design": {"bg": "#202020"}})
chk(green_room.room("moss", d2["id"])["design"]["bg"] == "#202020", "a draft previews for its owner")
chk(green_room.design_live(d2["id"])["live"] == d2["id"], "the draft goes live")
chk(green_room.design_delete(d["id"])["deleted"] == d["id"], "the old design can be deleted once not live")

# where the room is (Explore → Globe): set it, read it back, see it in the directory + on the globe's list
import explore_globe
green_room.my_room_profile({"is_public": True})
chk(green_room.server_keeps_places(green_room.my_room()) and green_room.my_room()["place"] is None,
    "this server keeps places; the room starts nowhere in particular")
out = green_room.set_my_place({"name": "Gaillimh", "lat": 53.2707, "lon": -9.0568})
chk(out["place"] == {"name": "Gaillimh", "lat": 53.2707, "lon": -9.0568} and out["bio"] == "slower music" and out["handle"] == "moss",
    "set_my_place puts the room on the globe and leaves the rest of the profile as it was")
chk(next(r for r in green_room.rooms() if r["handle"] == "moss")["place"]["name"] == "Gaillimh", "the directory carries it")
th = explore_globe.things(catalogue_fn=lambda: [], sources_fn=lambda: [])
moss = next(t for t in th["things"] if t["id"] == "room:moss")
chk(th["rooms_error"] is None and moss["kind"] == "room" and moss["sub"] == "artist"
    and moss["place"] == {"name": "Gaillimh", "lat": 53.2707, "lon": -9.0568}, "the globe's list shows the room at its place")
try:
    green_room.set_my_place({"name": "nowhere", "lat": 200, "lon": 0})
    chk(False, "a spot off the globe raises GRError")
except green_room.GRError as e:
    chk("globe" in str(e), "a spot off the globe raises GRError with the server's plain reason")
chk(green_room.set_my_place(None)["place"] is None, "set_my_place(None) takes it off again")
moss = next(t for t in explore_globe.things(catalogue_fn=lambda: [], sources_fn=lambda: [])["things"] if t["id"] == "room:moss")
chk(moss["place"] is None, "…and the globe's list has it as universal")

# a server from before places: it ignores the key and answers without one — everything reads as universal
from flask import Flask as _Flask, jsonify as _jsonify
old_pool = _Flask("old_pool")
@old_pool.get("/api/rooms")
def _old_rooms(): return _jsonify({"rooms": [{"handle": "elder", "name": "Elder", "kind": "label", "bio": "", "track_count": 3,
                                              "updated_at": None, "cover_track_ids": []}]})
@old_pool.post("/api/my/room/profile")
def _old_profile(): return _jsonify({"handle": "moss", "name": "Moss Records", "kind": "artist", "bio": "", "links": [],
                                     "is_public": True, "designs": []})
old_srv = make_server("127.0.0.1", 0, old_pool)
threading.Thread(target=old_srv.serve_forever, daemon=True).start()
with closing(appdb()) as c:
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gr_server_url', ?)", (f"http://127.0.0.1:{old_srv.server_port}",)); c.commit()
ans = green_room.set_my_place({"name": "Gaillimh", "lat": 53.2707, "lon": -9.0568})
chk(not green_room.server_keeps_places(ans), "an older server answers without a place: the app can tell, and say so")
elder = next(t for t in explore_globe.things(catalogue_fn=lambda: [], sources_fn=lambda: [])["things"] if t["id"] == "room:elder")
chk(elder["place"] is None and elder["count"] == 3, "its rooms still show — as universal")
old_srv.shutdown()
with closing(appdb()) as c:
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gr_server_url', ?)", ("http://127.0.0.1:1",)); c.commit()
gone = explore_globe.things(catalogue_fn=lambda: [{"id": "x", "name": "X", "url": "https://x.example", "type": "station"}], sources_fn=lambda: [])
chk(gone["rooms_error"] and [t["id"] for t in gone["things"]] == ["cat:x"], "with the rooms server away the rest still shows, and the reason is passed on")
with closing(appdb()) as c:
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gr_server_url', ?)", (SERVER,)); c.commit()

# ─── public grúpaí, through the app's own client (2026-11-15) ───
import base64
_b = io.BytesIO(); Image.new("RGB", (40, 40), (52, 85, 126)).save(_b, "JPEG")
PAY = {"local_id": 3, "name": "Tide tables", "description": "low water",
       "cover": {"kind": "text", "font": "Fraunces", "bg": "#34557e", "ink": "#f2efe8"},
       "items": [{"kind": "stream", "where": "stream", "title": "A stream", "subtitle": "Someone", "url": "https://soundcloud.com/a/b", "source": "soundcloud", "stream_type": "track"},
                 {"kind": "track", "where": "local", "title": "Only here", "subtitle": "Nobody", "art": "1"}],
       "art": {"1": base64.b64encode(_b.getvalue()).decode("ascii")}}
up = green_room.grupa_publish(PAY)
chk(up["id"] and up["count"] == 2, "a grúpa goes up through the client")
lst = green_room.public_grupai()
chk([g["name"] for g in lst] == ["Tide tables"] and lst[0]["mine"] is True and lst[0]["owner"]["handle"] == "moss" and lst[0]["cover"]["font"] == "Fraunces",
    "it is in the list others see, with its cover and the way to its maker's room")
chk(green_room.public_grupai(q="water")[0]["id"] == up["id"] and green_room.public_grupai(q="nothing like it") == [] and green_room.public_grupai(handle="moss")[0]["id"] == up["id"],
    "it can be found by a word, or by its room")
one = green_room.public_grupa(up["id"])
chk([i["title"] for i in one["items"]] == ["A stream", "Only here"] and one["items"][1]["image"] == f"/api/grupai/{up['id']}/art/1", "opened, it has what is in it")
pic = green_room.grupa_art_bytes(up["id"], "1", one["updated_at"])
kept = list((green_room.GR_DIR / "grupa_art" / str(up["id"])).glob("1.*.jpg"))
chk(pic and pic[:3] == b"\xff\xd8\xff" and len(kept) == 1, "its small picture is fetched once and kept on this laptop")
chk(green_room.grupa_art_bytes(up["id"], "../../x", "") is None and green_room.grupa_art_bytes(up["id"], "nope", "") is None, "a picture that isn't there (or a made-up address) gives nothing")
chk(green_room.room("moss")["grupai"][0]["id"] == up["id"], "the room carries it")
chk(green_room.grupa_unpublish(3) == {"private": True, "was_public": True} and green_room.public_grupai() == [], "made private, it is gone from the list")
try:
    green_room.public_grupa(up["id"]); chk(False, "a grúpa that has gone says so")
except green_room.GRError as e:
    chk("no such" in str(e), "a grúpa that has gone says so")
# a rooms server from before grúpaí: said plainly on the way up; taking down is simply fine
old_srv2 = make_server("127.0.0.1", 0, old_pool)
threading.Thread(target=old_srv2.serve_forever, daemon=True).start()
with closing(appdb()) as c:
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gr_server_url', ?)", (f"http://127.0.0.1:{old_srv2.server_port}",)); c.commit()
try:
    green_room.grupa_publish(PAY); chk(False, "an older rooms server: the reason is given in plain words")
except green_room.GRError as e:
    chk(str(e) == green_room.GRUPA_OLD_SERVER and "restart" in str(e), "an older rooms server: the reason is given in plain words")
chk(green_room.grupa_unpublish(3) == {"private": True, "was_public": False}, "…and making one private there is simply fine")
try:
    green_room.public_grupai(); chk(False, "…and Explore is told why there are none")
except green_room.GRError as e:
    chk(str(e) == green_room.GRUPA_NO_SERVER and "restart" in str(e), "…and Explore is told why there are none")
old_srv2.shutdown()
with closing(appdb()) as c:
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gr_server_url', ?)", (SERVER,)); c.commit()

srv.shutdown()
print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
