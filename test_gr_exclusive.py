"""Exclusive records on the rooms server: a record FILE its owner marks as only in the Music
Room. It can be brought home; it can be bought and is then held for good — but the plain file is
never handed over; it takes no room once bought; it comes back free; it has no outside link; a
record people already hold as a file can't be made exclusive. With the credits trial on and off,
and on a database from before the columns. Run:  ./venv/bin/python test_gr_exclusive.py"""
import os
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "excl.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")

import gr_server
import gr_master

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def sql(q, *p):
    with closing(gr_server.db()) as c:
        out = c.execute(q, p).fetchall(); c.commit(); return out

def fresh(name):
    os.environ["MR_GR_DB"] = str(TMP / name)
    with closing(gr_server.db()) as c:
        gr_server.init_db(c)
    gr_master.make_master("Master", handle="master")
client = gr_server.app.test_client()
def join(handle, fp):
    code = sql("SELECT invite_code FROM gr_accounts WHERE handle=?", handle)[0][0]
    return client.post("/api/join", json={"invite_code": code, "fingerprint": fp, "device_name": "laptop"}).get_json()["token"]
def signup(name):
    gr_master._rate.clear()
    return client.post("/api/signup", json={"name": name, "fingerprint": "mac-" + name, "agreed": True}).get_json()["token"]
def record(owner_handle, title, **cols):
    f = TMP / f"{title}.flac"; f.write_bytes(os.urandom(4096))
    oid = sql("SELECT id FROM gr_accounts WHERE handle=?", owner_handle)[0][0]
    sql("INSERT INTO gr_tracks(path, filename, title, artist, album, duration_s, format, size_bytes, price_cents, added_at,"
        " owner_account_id, status, buy_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,'live',?)",
        str(f), f.name, title, "Bea", "EP", 200, "flac", 4096, 300, "2026-11-24T10:00:00", oid, cols.get("buy_url"))
    return sql("SELECT id FROM gr_tracks WHERE title=?", title)[0][0], f.read_bytes()
def edit(tok, tid, **d): return client.post(f"/api/my/records/{tid}", json=d, headers=hdr(tok))
def row(tok, tid): return next(t for t in client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"] if t["id"] == tid)

# ═══ with the credits trial on ═══
fresh("excl.db")
master = join("master", "mac-master")
client.post("/api/master/sim/rules", json={"on": True}, headers=hdr(master))
bea, aoife, cian = signup("Bea"), signup("Aoife"), signup("Cian")
sql("UPDATE gr_accounts SET kind='artist', is_public=1 WHERE handle='bea'")
only, raw = record("bea", "Only Here", buy_url="https://bea.bandcamp.com/only")
plain, _ = record("bea", "Everywhere")

chk(row(aoife, only)["exclusive"] is False, "a record is not exclusive until its owner says so")
chk(edit(aoife, only, exclusive=True).status_code == 404, "only its owner can mark it")
r = edit(bea, only, exclusive=True)
chk(r.status_code == 200 and row(aoife, only)["exclusive"] is True, "Bea marks it exclusive; everyone sees the mark")
chk(row(aoife, only)["buy_url"] is None and r.get_json()["status"] == "live", "its outside link is gone, and it stays out (no second approval)")
edit(bea, only, buy_url="https://elsewhere.example/only")
chk(row(aoife, only)["buy_url"] is None, "an exclusive record can't be given an outside link")
chk(any(t["id"] == only and t["exclusive"] for t in client.get("/api/my/records", headers=hdr(bea)).get_json()["records"]), "her own list shows it")
chk(any(t["id"] == only and t["exclusive"] for t in client.get("/api/plugins/catalogue", headers=hdr(aoife)).get_json()["records"]), "plug-ins can read the mark")

# bring it home: a locked file, as ever
b = client.post("/api/borrow", json={"track_id": only}, headers=hdr(aoife)).get_json()
chk(b.get("exclusive") is True and b.get("kept") is False and b.get("key"), "brought home: a locked copy, marked exclusive, not yet kept")
me = lambda tok: client.get("/api/sim/me", headers=hdr(tok)).get_json()
chk(me(aoife)["credits"] == 299 and me(aoife)["room"]["count"] == 1, "1 credit, and it takes a place in the room")

# buy it: held for good, never a plain file
r = client.post("/api/buy", json={"track_id": only}, headers=hdr(aoife)); d = r.get_json()
chk(r.status_code == 200 and d["exclusive"] is True and "url" not in d, "bought: no plain file is offered")
chk(d["credits_spent"] == 2 and me(aoife)["credits"] == 297, "the difference is charged (3 − 1)")
chk(me(aoife)["room"]["count"] == 0, "once bought it takes none of the room")
chk(sql("SELECT kept_at, returned_at FROM gr_borrows WHERE id=?", b["borrow_id"])[0]["kept_at"] is not None
    and sql("SELECT returned_at FROM gr_borrows WHERE id=?", b["borrow_id"])[0][0] is None, "the locked copy stays hers (the borrow is kept, not ended)")
r = client.get(f"/api/download-plain/{only}", headers=hdr(aoife))
chk(r.status_code == 403 and r.get_json().get("exclusive"), "the plain file is refused, even to its buyer")
chk(len(client.get(f"/api/download/{b['borrow_id']}", headers=hdr(aoife)).data) == len(raw)
    and client.get(f"/api/download/{b['borrow_id']}", headers=hdr(aoife)).data != raw, "what she can fetch is the locked copy (not the file itself)")
c = row(aoife, only)
chk(c["purchased"] and c["borrow_id"] == b["borrow_id"], "the shop shows it as hers and in her room")
again = client.post("/api/buy", json={"track_id": only}, headers=hdr(aoife)).get_json()
chk(again.get("already") and again.get("exclusive") and "url" not in again and me(aoife)["credits"] == 297, "buying it again takes nothing and offers no file")

# it comes back free
client.post("/api/return", json={"borrow_id": b["borrow_id"]}, headers=hdr(aoife))
b2 = client.post("/api/borrow", json={"track_id": only}, headers=hdr(aoife)).get_json()
chk(b2.get("kept") is True and b2["borrow_id"] != b["borrow_id"] and me(aoife)["credits"] == 297 and me(aoife)["room"]["count"] == 0,
    "taken off a laptop and fetched again: free, at once, and still no room taken")
sql("UPDATE gr_tracks SET status='hidden' WHERE id=?", only)
client.post("/api/return", json={"borrow_id": b2["borrow_id"]}, headers=hdr(aoife))
chk(client.post("/api/borrow", json={"track_id": only}, headers=hdr(aoife)).status_code == 200
    and client.post("/api/borrow", json={"track_id": only}, headers=hdr(cian)).status_code == 404,
    "after it leaves the shop its buyer can still fetch it; nobody new can")
sql("UPDATE gr_tracks SET status='live' WHERE id=?", only)

# bought straight away (never brought home first)
r = client.post("/api/buy", json={"track_id": only}, headers=hdr(cian)); d = r.get_json()
chk(d["exclusive"] and d["credits_spent"] == 3 and "url" not in d, "Cian buys it outright: 3 credits, no file offered")
b3 = client.post("/api/borrow", json={"track_id": only}, headers=hdr(cian)).get_json()
chk(b3.get("kept") is True and me(cian)["credits"] == 297 and me(cian)["room"]["count"] == 0, "…then his app fetches the locked copy free")

# an ordinary record is as before
client.post("/api/borrow", json={"track_id": plain}, headers=hdr(aoife))
d = client.post("/api/buy", json={"track_id": plain}, headers=hdr(aoife)).get_json()
chk(d.get("url") and not d.get("exclusive") and client.get(d["url"], headers=hdr(aoife)).status_code == 200,
    "an ordinary record still arrives as a plain file when bought")
r = edit(bea, plain, exclusive=True)
chk(r.status_code == 409 and "already bought" in r.get_json()["error"], "a record someone already holds as a file can't be made exclusive")

# switched off again
edit(bea, only, exclusive=False)
chk(row(aoife, only)["exclusive"] is False and client.get(f"/api/download-plain/{only}", headers=hdr(aoife)).status_code == 200,
    "if its owner lifts it, the people who bought it can have the file")
edit(bea, only, exclusive=True)
chk(row(cian, only)["exclusive"] is False, "…and after that it can't be made exclusive again")

# uploading one as exclusive
import io
up = client.post("/api/my/records", data={"audio": (io.BytesIO(os.urandom(2048)), "new.mp3"), "title": "Fresh", "rights": "1",
                                          "exclusive": "1", "buy_url": "https://x.example/fresh"},
                 headers=hdr(bea), content_type="multipart/form-data")
t = sql("SELECT exclusive, buy_url, status FROM gr_tracks WHERE title='Fresh'")
chk(up.status_code == 200 and t and tuple(t[0]) == (1, None, "pending"), "uploaded as exclusive: marked, no outside link, waiting for approval like any record")
recs = client.get("/api/master/records?status=pending", headers=hdr(master))
chk(recs.status_code != 200 or any(x.get("exclusive") for x in recs.get_json().get("records", [])), "the master sees the mark on a waiting record")

# a record from the playlist shop can never be exclusive
sql("UPDATE gr_tracks SET spotify_uri='spotify:track:x', exclusive=0 WHERE id=?", plain)
sql("DELETE FROM gr_purchases WHERE track_id=?", plain)
chk(edit(bea, plain, exclusive=True).status_code == 409, "a record that plays from Spotify can't be exclusive")

# ═══ with the trial off (the wallet) ═══
fresh("excl_wallet.db")
bea, aoife = signup("Bea"), signup("Aoife")
sql("UPDATE gr_accounts SET kind='artist' WHERE handle='bea'")
only, raw = record("bea", "Only Here")
edit(bea, only, exclusive=True)
d = client.post("/api/buy", json={"track_id": only}, headers=hdr(aoife)).get_json()
chk(d.get("exclusive") and "url" not in d and d["paid_cents"] == 300, "trial off: bought with the wallet, still no file")
b = client.post("/api/borrow", json={"track_id": only}, headers=hdr(aoife))
chk(b.status_code == 200 and b.get_json()["kept"] is True, "…and the locked copy comes without a plan or a charge")
chk(client.get(f"/api/download-plain/{only}", headers=hdr(aoife)).status_code == 403, "…and never the plain file")

# ═══ a database from before exclusive records ═══
fresh("older.db")
with closing(gr_server.db()) as c:
    c.executescript("ALTER TABLE gr_tracks DROP COLUMN exclusive; ALTER TABLE gr_borrows DROP COLUMN kept_at;")
    c.commit()
gr_server._excl_seen.clear()
old = join("master", "mac-old")
chk(client.get("/api/catalogue", headers=hdr(old)).status_code == 200 and client.get("/api/sim/me", headers=hdr(old)).status_code == 200
    and "exclusive" in {r[1] for r in sql("PRAGMA table_info(gr_tracks)")} and "kept_at" in {r[1] for r in sql("PRAGMA table_info(gr_borrows)")},
    "an older database gets the two columns on the first signed-in request")

print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
