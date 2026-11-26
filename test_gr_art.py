"""Digital artists on the rooms server (gr_art.py): a kind of account asked for at
sign-up; works (pictures) with a view and a small copy; open to work; artwork
credits on records that the artist must agree to; a work sold for credits, the
file handed only to its maker and its buyers; what a taken-down room hides.
A fresh database AND one from before this file existed. No network.
Run:  ./venv/bin/python test_gr_art.py"""
import io
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_art_test.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")

from PIL import Image

import gr_server
import gr_master
import gr_art

# digital artists are switched off for now (gr_server.KINDS_OFF): this test is of the code
# that waits behind the switch, so it turns them on for itself
gr_server.KINDS_OFF = ()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
client = gr_server.app.test_client()
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def join(code, fp): return client.post("/api/join", json={"invite_code": code, "fingerprint": fp, "device_name": "laptop"}).get_json()["token"]
def sql(q, *p):
    with closing(gr_server.db()) as c:
        out = c.execute(q, p).fetchall(); c.commit(); return out
def code_of(handle): return sql("SELECT invite_code FROM gr_accounts WHERE handle=?", handle)[0][0]
def signup(name, kind=""):
    gr_master._rate.clear()
    return client.post("/api/signup", json={"name": name, "fingerprint": "mac-" + name, "agreed": True, "kind_requested": kind}).get_json()
def picture(w=3000, h=2000, fmt="JPEG", colour=(200, 60, 40)):
    b = io.BytesIO(); Image.new("RGB", (w, h), colour).save(b, fmt); return b.getvalue()
def send(tok, raw, name="piece.jpg", **form):
    form = dict({"rights": "1"}, **form)
    return client.post("/api/my/works", data=dict(form, image=(io.BytesIO(raw), name)), headers=hdr(tok),
                       content_type="multipart/form-data")

gr_master.make_master("Daithí", handle="daithi")
import gr_signin; gr_signin.set_rules_here({"master_2fa": "off"})   # (the master's two-factor has its own test: test_gr_signin.py)
master = join(code_of("daithi"), "mac-daithi")

# ── the kind is asked for, and switched on by the master ──
d = signup("Sorcha Ní Bhriain", "digital artist")
sorcha = d["token"]
chk(d["kind"] == "listener" and d["kind_requested"] == "digital artist", "a digital artist starts as a listener, with the request waiting")
chk(send(sorcha, picture(400, 300)).status_code == 403, "works are refused until the kind is switched on")
aid = sql("SELECT id FROM gr_accounts WHERE handle=?", d["handle"])[0][0]
r = client.post(f"/api/master/accounts/{aid}", json={"request": "approve"}, headers=hdr(master))
chk(r.status_code == 200 and sql("SELECT kind FROM gr_accounts WHERE id=?", aid)[0][0] == "digital artist", "the master approves the request")
chk("digital artist" in client.get("/api/master/accounts", headers=hdr(master)).get_json()["kinds"], "the master's list of kinds has it")

# ── works ──
chk(send(sorcha, picture(400, 300), rights="").status_code == 400, "a work needs the rights tick")
chk(send(sorcha, b"not a picture at all").status_code == 400, "something that isn't a picture is refused")
raw = picture()
r = send(sorcha, raw, "Tide Table.jpg", year="2025", medium="3D render", note="Made for a record that never came out.",
         url="https://vimeo.com/123", price="12")
wid = r.get_json()["id"]
chk(r.status_code == 200 and r.get_json()["title"] == "Tide Table", "a work goes up; its name comes from the file when none is given")
w = sql("SELECT * FROM gr_works WHERE id=?", wid)[0]
chk(open(w["file_path"], "rb").read() == raw, "the file is kept exactly as it was sent")
v, t = Image.open(w["view_path"]), Image.open(w["thumb_path"])
chk(max(v.size) == gr_art.VIEW_PX and max(t.size) == gr_art.THUMB_PX, "a view (2400) and a small copy (640) are made")
r2 = send(sorcha, picture(800, 800, "PNG"), "second.png", title="Second")
wid2 = r2.get_json()["id"]
mine = client.get("/api/my/works", headers=hdr(sorcha)).get_json()
chk(mine["can"] and [x["id"] for x in mine["works"]] == [wid2, wid] and mine["works"][1]["price"] == 12
    and mine["works"][0]["price"] is None, "the artist's list: newest first, a price or none")
chk(client.post(f"/api/my/works/{wid2}", json={"price": 5, "title": "Second, renamed", "year": "abc"}, headers=hdr(sorcha)).status_code == 200
    and sql("SELECT title, price, year FROM gr_works WHERE id=?", wid2)[0][:] == ("Second, renamed", 5, None), "a work's words and price can be changed")
client.post(f"/api/my/works/{wid2}", json={"price": ""}, headers=hdr(sorcha))
chk(sql("SELECT price FROM gr_works WHERE id=?", wid2)[0][0] is None, "an empty price = not for sale")

# ── pictures are public; the file itself is not ──
chk(client.get(f"/api/works/{wid}/img?size=thumb").status_code == 200 and client.get(f"/api/works/{wid}/img").status_code == 200,
    "the view and the small copy need no sign-in (like a room's pictures)")
chk(client.get(f"/api/works/{wid}/file").status_code == 401, "the file needs a sign-in")
aoife = signup("Aoife")["token"]
chk(client.get(f"/api/works/{wid}/file", headers=hdr(aoife)).status_code == 403, "…and is refused to someone who hasn't bought it")
chk(client.get(f"/api/works/{wid}/file", headers=hdr(sorcha)).data == raw, "its maker can always fetch it")

# ── open to work, and the room ──
r = client.post("/api/my/works/profile", json={"open": True, "line": "Covers, visuals for live sets", "contact": "sorcha@example.com"}, headers=hdr(sorcha))
chk(r.get_json()["profile"] == {"open": True, "line": "Covers, visuals for live sets", "contact": "sorcha@example.com"}, "open to work, a line, an address")
client.post("/api/my/works/profile", json={"open": True, "line": "x", "contact": "javascript:alert(1)"}, headers=hdr(sorcha))
chk(sql("SELECT work_contact FROM gr_accounts WHERE id=?", aid)[0][0] == "", "a contact that isn't a web or email address is dropped")
client.post("/api/my/works/profile", json={"open": True, "line": "Covers, visuals for live sets", "contact": "sorcha.example"}, headers=hdr(sorcha))
chk(sql("SELECT work_contact FROM gr_accounts WHERE id=?", aid)[0][0] == "https://sorcha.example", "a web address written without https:// gets it")
chk(client.post("/api/my/works/profile", json={"open": True}, headers=hdr(aoife)).status_code == 403, "a listener has no work line")
client.post("/api/my/room/profile", json={"name": "Sorcha Ní Bhriain", "handle": d["handle"], "bio": "", "links": [], "is_public": True}, headers=hdr(sorcha))
room = client.get(f"/api/rooms/{d['handle']}", headers=hdr(aoife)).get_json()
chk([x["id"] for x in room["works"]] == [wid2, wid] and room["work"]["open"] and room["work"]["contact"] == "https://sorcha.example"
    and room["kind"] == "digital artist", "her room carries her works and her work line")
chk("file_name" not in room["works"][0] and "file" not in " ".join(room["works"][0].keys()), "a room's works name no file")
cards = client.get("/api/rooms?kind=digital%20artist", headers=hdr(aoife)).get_json()["rooms"]
chk(len(cards) == 1 and cards[0]["cover_work_ids"] == [wid2, wid] and cards[0]["open_to_work"] and cards[0]["work_count"] == 2,
    "the directory narrows to digital artists; the card shows her latest works")
chk(len(client.get("/api/rooms?open=1", headers=hdr(aoife)).get_json()["rooms"]) == 1
    and len(client.get("/api/rooms?q=visuals", headers=hdr(aoife)).get_json()["rooms"]) == 1, "…to those open to work, and finds her by what she does")
chk("works" not in client.get("/api/rooms/daithi", headers=hdr(master)).get_json(), "a room of another kind has no works")

# ── selling: off, short, bought once, the file handed over ──
chk(client.post(f"/api/works/{wid}/buy", headers=hdr(aoife)).status_code == 409, "nothing is sold while the credits trial is off")
client.post("/api/master/sim/rules", json={"on": True}, headers=hdr(master))
chk(client.post(f"/api/works/{wid2}/buy", headers=hdr(aoife)).status_code == 409, "a work with no price isn't for sale")
chk(client.post(f"/api/works/{wid}/buy", headers=hdr(sorcha)).status_code == 400, "her own work isn't sold to her")
r = client.post(f"/api/works/{wid}/buy", headers=hdr(aoife))
chk(r.status_code == 200 and r.get_json()["spent"] == 12 and r.get_json()["credits"] == 288, "Aoife buys it: 12 of her 300 credits")
r = client.post(f"/api/works/{wid}/buy", headers=hdr(aoife))
chk(r.get_json().get("already") and r.get_json()["credits"] == 288, "buying it again takes nothing")
chk(client.get(f"/api/works/{wid}/file", headers=hdr(aoife)).data == raw, "she is handed the file as it was sent")
led = sql("SELECT what, credits, balance FROM gr_ledger WHERE what='art'")
chk(len(led) == 1 and tuple(led[0]) == ("art", -12, 288), "one line in the ledger")
b = client.get("/api/works/bought", headers=hdr(aoife)).get_json()["works"]
chk(len(b) == 1 and b[0]["by"]["name"] == "Sorcha Ní Bhriain" and b[0]["paid"] == 12, "what she bought is listed, with who made it")
mine = client.get("/api/my/works", headers=hdr(sorcha)).get_json()
chk(mine["sold"] == 1 and mine["earned"] == 12 and sql("SELECT credits FROM gr_accounts WHERE id=?", aid)[0][0] in (None, 300),
    "the artist sees 1 sold, 12 earned — counted apart from her own spending credits")
bea = signup("Bea")["token"]
sql("UPDATE gr_accounts SET credits=5 WHERE handle='bea'")
r = client.post(f"/api/works/{wid}/buy", headers=hdr(bea))
chk(r.status_code == 402 and r.get_json()["short"], "too few credits is said plainly, and nothing is taken")
one = client.get(f"/api/works/{wid}", headers=hdr(aoife)).get_json()
chk(one["bought"] and one["by"]["handle"] == d["handle"] and one["selling"], "one work, as its buyer sees it")

# ── taking a work out ──
client.delete(f"/api/my/works/{wid}", headers=hdr(sorcha))
chk(client.get(f"/api/works/{wid}/file", headers=hdr(aoife)).data == raw and client.get(f"/api/works/{wid}", headers=hdr(bea)).status_code == 404
    and [x["id"] for x in client.get(f"/api/rooms/{d['handle']}", headers=hdr(bea)).get_json()["works"]] == [wid2],
    "a bought work that is taken out leaves the room, and its buyer keeps it")
p2 = sql("SELECT file_path, view_path FROM gr_works WHERE id=?", wid2)[0]
client.delete(f"/api/my/works/{wid2}", headers=hdr(sorcha))
chk(not os.path.exists(p2[0]) and not os.path.exists(p2[1]) and client.get(f"/api/works/{wid2}/img").status_code == 404,
    "an unsold work that is taken out is deleted, files and all")

# ── artwork credits on records ──
sql("UPDATE gr_accounts SET kind='artist' WHERE handle='bea'")
bea_id = sql("SELECT id FROM gr_accounts WHERE handle='bea'")[0][0]
sql("INSERT INTO gr_tracks(path, filename, title, artist, album, price_cents, added_at, owner_account_id, status)"
    " VALUES('/nowhere/a.flac','a.flac','Salt','Bea','Salt EP',250,'2026-11-24T10:00:00',?, 'live')", bea_id)
tid = sql("SELECT id FROM gr_tracks WHERE title='Salt'")[0][0]
chk(client.post(f"/api/my/records/{tid}/art-by", json={"handle": "aoife"}, headers=hdr(bea)).status_code == 404, "only a digital artist can be named")
chk(client.post(f"/api/my/records/{tid}/art-by", json={"handle": d["handle"]}, headers=hdr(aoife)).status_code == 404, "only the record's owner can name one")
r = client.post(f"/api/my/records/{tid}/art-by", json={"handle": "@" + d["handle"]}, headers=hdr(bea))
chk(r.status_code == 200 and r.get_json()["art_by"]["state"] == "asked", "Bea names Sorcha as the maker of the artwork")
rec = lambda who: next(t for t in client.get("/api/rooms/bea", headers=hdr(who)).get_json()["tracks"] if t["id"] == tid)
sql("UPDATE gr_accounts SET is_public=1 WHERE handle='bea'")
chk("art_by" not in rec(aoife), "it doesn't show until Sorcha agrees")
ask = client.get("/api/my/works", headers=hdr(sorcha)).get_json()["credits"]
chk(len(ask) == 1 and ask[0]["state"] == "asked" and ask[0]["title"] == "Salt", "Sorcha is asked")
client.post(f"/api/my/works/credits/{ask[0]['id']}", json={"yes": True}, headers=hdr(sorcha))
chk(rec(aoife).get("art_by") == {"handle": d["handle"], "name": "Sorcha Ní Bhriain"}, "agreed: the record says who made its artwork")
chk([c["title"] for c in client.get(f"/api/rooms/{d['handle']}", headers=hdr(aoife)).get_json()["art_credits"]] == ["Salt"], "…and her room lists the record")
chk(client.get("/api/my/records/art-by", headers=hdr(bea)).get_json()["art_by"][str(tid)]["state"] == "yes", "the owner sees the state of each credit")
client.post(f"/api/my/records/{tid}/art-by", json={"handle": ""}, headers=hdr(bea))
chk("art_by" not in rec(aoife), "the owner can take the name off again")

# ── a room taken down hides its works ──
r3 = send(sorcha, picture(600, 600), "third.jpg", price="3")
wid3 = r3.get_json()["id"]
sql("UPDATE gr_accounts SET hidden_at='2026-11-24T12:00:00' WHERE id=?", aid)
chk(client.get(f"/api/works/{wid3}/img").status_code == 404 and client.post(f"/api/works/{wid3}/buy", headers=hdr(aoife)).status_code == 404,
    "a taken-down room's works are neither shown nor sold")
sql("UPDATE gr_accounts SET hidden_at=NULL WHERE id=?", aid)

# ── the limit ──
old = gr_art.WORKS_MAX
gr_art.WORKS_MAX = 1
chk(send(sorcha, picture(300, 300)).status_code == 409, "a room holds only so many works")
gr_art.WORKS_MAX = old

# ── switched off (as the server ships now): nobody can ask to be one, or be made one ──
gr_server.KINDS_OFF = ("digital artist",)
gr_master._rate.clear()
d = signup("Niamh Off", "digital artist")
chk(d["kind"] == "listener" and d["kind_requested"] == "", "switched off: a digital artist can't be asked for")
r = client.post("/api/apply", json={"kind": "digital artist", "fields": {}}, headers=hdr(d["token"]))
chk(r.status_code == 400 and "digital artist" not in [k["key"] for k in client.get("/api/apply", headers=hdr(d["token"])).get_json()["kinds"]],
    "…nor applied for")
aid_off = sql("SELECT id FROM gr_accounts WHERE name='Niamh Off'")[0][0]
r = client.post(f"/api/master/accounts/{aid_off}", json={"kind": "digital artist"}, headers=hdr(master))
chk(r.status_code == 400 and "digital artist" not in client.get("/api/master/accounts", headers=hdr(master)).get_json()["kinds"],
    "…nor given by the master")
gr_server.KINDS_OFF = ()

# ── a database from before digital artists ──
os.environ["MR_GR_DB"] = str(TMP / "older.db")
with closing(gr_server.db()) as c:
    gr_server.init_db(c)
    c.executescript("DROP TABLE gr_works; DROP TABLE gr_work_buys; DROP TABLE gr_art_credits;"
                    "ALTER TABLE gr_accounts DROP COLUMN open_to_work; ALTER TABLE gr_accounts DROP COLUMN work_line;"
                    "ALTER TABLE gr_accounts DROP COLUMN work_contact;")
    c.commit()
gr_master.make_master("Old", handle="old")
import gr_signin; gr_signin.set_rules_here({"master_2fa": "off"})   # (the master's two-factor has its own test: test_gr_signin.py)
old_tok = join(code_of("old"), "mac-old")
chk(client.get("/api/my/works", headers=hdr(old_tok)).status_code == 200 and client.get("/api/rooms", headers=hdr(old_tok)).status_code == 200
    and client.get("/api/rooms/old", headers=hdr(old_tok)).status_code == 200,
    "an older database gets the new tables and columns the first time they are needed")

print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
