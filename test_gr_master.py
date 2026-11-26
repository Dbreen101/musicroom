"""The master account and the guardrails of the rooms server (gr_master.py):
sign-up makes listeners only, other kinds are requests; the house rules must be
agreed; a paused account can't sign in; records wait for the master; reports
take things down; feedback can be marked done; the version everyone should be
on; what plug-ins may read, and the crate a plug-in can pick.
A fresh database, no network, no sound. Run:  ./venv/bin/python test_gr_master.py"""
import io
import os
import sys
import tempfile
import wave
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_master_test.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")

import gr_server
import gr_master
import gr_shop

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
def wav_bytes(n=4000, b=1):
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(bytes([b, 1]) * n)
    return buf.getvalue()

# ── sign-up: always a listener; another kind is a request; the house rules first ──
r = client.post("/api/signup", json={"name": "Aoife", "fingerprint": "mac-aoife"})
chk(r.status_code == 400 and r.get_json().get("need_agree"), "sign-up asks for the house rules to be agreed first")
r = client.post("/api/signup", json={"name": "Aoife", "fingerprint": "mac-aoife", "agreed": True, "kind": "label"})
d = r.get_json()
chk(r.status_code == 200 and d["kind"] == "listener" and d["kind_requested"] == "label",
    "asking to be a label makes a listener, with the label as a request")
aoife = d["token"]
me = client.get("/api/me", headers=hdr(aoife)).get_json()
chk(me["kind"] == "listener" and me["kind_requested"] == "label" and me["agreed"] and not me["is_master"],
    "the account knows its request and that the rules were agreed; it is not the master")
r = client.post("/api/signup", json={"name": "Bea", "fingerprint": "mac-bea", "agreed": True, "kind": "master"})
chk(r.get_json()["kind"] == "listener" and r.get_json()["kind_requested"] == "", "nobody can ask to be the master")
bea = r.get_json()["token"]
r = client.post("/api/my/records", data={"rights": "1", "audio": (io.BytesIO(wav_bytes()), "x.wav")}, headers=hdr(aoife),
                content_type="multipart/form-data")
chk(r.status_code == 403, "a listener whose request is waiting can't sell records yet")
gr_master._rate.clear()
codes = [client.post("/api/signup", json={"name": f"Many {i}", "fingerprint": f"mac-m{i}", "agreed": True}).status_code
         for i in range(gr_master.SIGNUPS_PER_HOUR + 1)]
chk(codes[:gr_master.SIGNUPS_PER_HOUR] == [200] * gr_master.SIGNUPS_PER_HOUR and codes[-1] == 429,
    f"one address makes at most {gr_master.SIGNUPS_PER_HOUR} accounts an hour")
gr_master._rate.clear()

# ── account codes can't be guessed; tries are limited ──
c = gr_server.new_code()
chk(len(c) == 22 and c.startswith("gr-") and c.count("-") == 4 and not set(c[3:].replace("-", "")) - set(gr_server.CODE_ALPHABET),
    "an account code is sixteen letters in four groups, none that look alike")
chk(len({gr_server.new_code() for _ in range(2000)}) == 2000, "no two codes alike in two thousand")
gr_master._rate.clear()
tries = [client.post("/api/join", json={"invite_code": f"gr-nope-{i}", "fingerprint": "mac-x"}).status_code for i in range(13)]
chk(tries[:12] == [403] * 12 and tries[12] == 429, "one address gets twelve tries in ten minutes, then waits")
gr_master._rate.clear()

# ── the master: made only from the server's own Terminal ──
said = gr_master.make_master("Daithí", handle="daithi")
import gr_signin; gr_signin.set_rules_here({"master_2fa": "off"})   # (the master's two-factor has its own test: test_gr_signin.py)
chk("master account" in said and code_of("daithi") in said, "the Terminal makes the master account and prints its code")
mtok = join(code_of("daithi"), "mac-daithi")
chk(client.get("/api/me", headers=hdr(mtok)).get_json()["is_master"], "the master signs in like anyone and is known as the master")
chk(client.get("/api/master/overview", headers=hdr(aoife)).status_code == 403 and client.get("/api/master/overview").status_code == 401,
    "nobody else can open the master's routes")
chk(client.get("/api/master/overview", headers=hdr(mtok), environ_base={"REMOTE_ADDR": "192.168.1.40"}).status_code == 403,
    "the master's routes answer only on the server's own Mac, even with the master's token")
ov = client.get("/api/master/overview", headers=hdr(mtok)).get_json()
chk(ov["requests"] == 1 and ov["pending"] == 0, "the master sees one request waiting")

# ── accounts: approve a request, pause, unpause ──
accts = {a["handle"]: a for a in client.get("/api/master/accounts", headers=hdr(mtok)).get_json()["accounts"]}
aid = accts["aoife"]["id"]
chk(accts["aoife"]["kind_requested"] == "label" and accts["daithi"]["is_master"], "the list shows requests and the master")
r = client.post(f"/api/master/accounts/{aid}", json={"request": "approve"}, headers=hdr(mtok))
chk(r.get_json()["account"]["kind"] == "label" and r.get_json()["account"]["kind_requested"] == "", "approving the request makes Aoife a label")
client.post(f"/api/master/accounts/{aid}", json={"paused": True, "note": "talk to me"}, headers=hdr(mtok))
chk(client.get("/api/me", headers=hdr(aoife)).status_code == 401, "a paused account can't sign in")
client.post(f"/api/master/accounts/{aid}", json={"paused": False}, headers=hdr(mtok))
chk(client.get("/api/me", headers=hdr(aoife)).status_code == 200, "unpaused, it signs in again")
mid = accts["daithi"]["id"]
chk(client.post(f"/api/master/accounts/{mid}", json={"paused": True}, headers=hdr(mtok)).status_code == 400
    and client.post(f"/api/master/accounts/{mid}", json={"master": False}, headers=hdr(mtok)).status_code == 400,
    "the master can't pause itself or leave the server without a master")
chk(client.post(f"/api/master/accounts/{aid}", json={"kind": "emperor"}, headers=hdr(mtok)).status_code == 400, "only real kinds")

# ── records: a rights line, then they wait ──
r = client.post("/api/my/records", data={"audio": (io.BytesIO(wav_bytes()), "Low Tide.wav")}, headers=hdr(aoife),
                content_type="multipart/form-data")
chk(r.status_code == 400 and r.get_json().get("need_rights"), "a record can't go up without saying the rights are held")
r = client.post("/api/my/records", data={"rights": "1", "audio": (io.BytesIO(wav_bytes()), "Low Tide.wav"), "title": "Low Tide",
                                         "genre": "Ambient", "year": "2024"}, headers=hdr(aoife), content_type="multipart/form-data")
rid = r.get_json()["id"]
mine = client.get("/api/my/records", headers=hdr(aoife)).get_json()
chk(mine["records"][0]["status"] == "pending" and mine["rights_text"], "the owner sees it waiting, and the words they agreed to")
cat = lambda tok: [t["id"] for t in client.get("/api/catalogue", headers=hdr(tok)).get_json()["tracks"]]
chk(rid not in cat(bea), "nobody else sees it while it waits")
chk(client.get(f"/api/master/records/{rid}/audio", headers=hdr(bea)).status_code == 403
    and client.get(f"/api/master/records/{rid}/audio", headers=hdr(mtok)).status_code == 200,
    "the master (only) can listen to it before deciding")
pend = client.get("/api/master/records", headers=hdr(mtok)).get_json()["records"]
chk([x["id"] for x in pend] == [rid] and pend[0]["rights_note"] and pend[0]["owner"]["handle"] == "aoife", "it is in the master's list, with the rights line")
chk(client.post(f"/api/master/records/{rid}", json={"status": "maybe"}, headers=hdr(mtok)).status_code == 400, "only real decisions")
client.post(f"/api/master/records/{rid}", json={"status": "live"}, headers=hdr(mtok))
chk(rid in cat(bea), "approved, it is on the shelves")
r_ed = client.post(f"/api/my/records/{rid}", json={"price_cents": 500}, headers=hdr(aoife)).get_json()
chk(r_ed["status"] == "live", "changing only the price leaves an approved record out")
r_ed = client.post(f"/api/my/records/{rid}", json={"title": "Low Tide (edit)", "buy_url": "javascript:alert(1)"}, headers=hdr(aoife)).get_json()
mine = {x["id"]: x for x in client.get("/api/my/records", headers=hdr(aoife)).get_json()["records"]}
chk(r_ed["status"] == "pending" and rid not in cat(bea) and mine[rid]["buy_url"] is None,
    "changing its name sends it back to the master; an outside link must be a web address")
client.post(f"/api/master/records/{rid}", json={"status": "live"}, headers=hdr(mtok))
# a second record, refused
r2 = client.post("/api/my/records", data={"rights": "1", "audio": (io.BytesIO(wav_bytes(b=2)), "Second.wav")}, headers=hdr(aoife),
                 content_type="multipart/form-data").get_json()["id"]
client.post(f"/api/master/records/{r2}", json={"status": "refused", "note": "the sample isn't cleared"}, headers=hdr(mtok))
mine = {x["id"]: x for x in client.get("/api/my/records", headers=hdr(aoife)).get_json()["records"]}
chk(mine[r2]["status"] == "refused" and mine[r2]["review_note"] == "the sample isn't cleared" and r2 not in cat(bea),
    "a refused record stays off the shelves and its owner is told why")
# the master's own uploads go out at once
client.post(f"/api/master/accounts/{mid}", json={"kind": "label"}, headers=hdr(mtok))
r3 = client.post("/api/my/records", data={"rights": "1", "audio": (io.BytesIO(wav_bytes(b=3)), "House.wav"), "title": "House"},
                 headers=hdr(mtok), content_type="multipart/form-data").get_json()["id"]
chk(r3 in cat(bea), "the master's own records go out without waiting")

# ── the shop sees only what is on the shelves; a plug-in can pick a crate ──
st = client.get("/api/shop", headers=hdr(bea)).get_json()
chk(st["records"] == 2, "the shop holds the two approved records, not the refused one")
pc = client.get("/api/plugins/catalogue", headers=hdr(bea)).get_json()["records"]
keys = set().union(*[set(x) for x in pc]) | set().union(*[set(x["seller"] or {}) for x in pc])
chk({x["id"] for x in pc} == {rid, r3} and not keys & {"path", "art_path", "filename", "invite_code", "token", "wallet_cents", "owner_account_id"},
    "plug-ins read only approved records, and only what is printed on them")
chk(next(x for x in pc if x["id"] == rid)["genres"] == ["Ambient"] and next(x for x in pc if x["id"] == rid)["seller"]["handle"] == "aoife",
    "with their genres and who sells them")
r = client.post("/api/shop/crates/pull", json={"pick": {"ids": [r2, 999, r3, rid, rid], "by": "Thread", "title": "From one record"}}, headers=hdr(bea))
pull = r.get_json()["pull"]
chk(r.status_code == 200 and [i["id"] for i in pull["items"]] == [r3, rid] and pull["kind"] == "plugin" and pull["by"]["name"] == "Thread",
    "a plug-in's pick becomes a crate: in its order, only what is on the shelves, once each, with its name on it")
chk(r.get_json()["left"]["crates"] == 2, "it is one of today's three crates")
r = client.post("/api/shop/crates/pull", json={"pick": {"ids": [r3], "by": "Thread"}}, headers=hdr(mtok))
chk(r.status_code == 404 and r.get_json().get("empty"), "a pick of only your own records hands you nothing (and uses none up)")
chk(client.get(f"/api/shop/listen/{rid}?pull={pull['id']}", headers=hdr(bea)).status_code in (200, 503),
    "a record in a plug-in's crate can be listened to like any crate's (503 only where the server has no ffmpeg)")

# ── reports: anyone can report; the master settles ──
client.post("/api/my/room/profile", json={"is_public": True}, headers=hdr(aoife))
rooms = lambda tok: [x["handle"] for x in client.get("/api/rooms", headers=hdr(tok)).get_json()["rooms"]]
chk("aoife" in rooms(bea), "Aoife's room is public")
chk(client.post("/api/report", json={"what": "room", "ref": "aoife", "reason": "rights"}, headers=hdr(aoife)).status_code == 400,
    "you can't report your own room")
r = client.post("/api/report", json={"what": "room", "ref": "aoife", "reason": "rights", "note": "uses a film still"}, headers=hdr(bea))
chk(r.status_code == 200, "Bea reports Aoife's room")
client.post("/api/report", json={"what": "record", "ref": str(rid), "reason": "rights"}, headers=hdr(bea))
chk(client.post("/api/report", json={"what": "record", "ref": "424242", "reason": "rights"}, headers=hdr(bea)).status_code == 404,
    "a report of something that isn't there is refused")
reps = client.get("/api/master/reports", headers=hdr(mtok)).get_json()["reports"]
chk(len(reps) == 2 and reps[-1]["by"]["handle"] == "bea" and reps[-1]["owner"]["handle"] == "aoife" and reps[-1]["reason_label"],
    "the master sees both reports: who, whose, why")
room_rep = next(x for x in reps if x["what"] == "room")
client.post(f"/api/master/reports/{room_rep['id']}", json={"action": "hide", "note": "the picture isn't hers"}, headers=hdr(mtok))
chk("aoife" not in rooms(bea) and client.get("/api/rooms/aoife", headers=hdr(bea)).status_code == 404, "a room taken down leaves the directory")
own = client.get("/api/rooms/aoife", headers=hdr(aoife)).get_json()
chk(own.get("hidden", {}).get("note") == "the picture isn't hers" and client.get("/api/me", headers=hdr(aoife)).get_json()["room_hidden"],
    "its owner still sees it, and why it was taken down")
chk(rid not in cat(bea) and client.get("/api/shop", headers=hdr(bea)).get_json()["records"] == 1,
    "a taken-down room's records leave the shelves with it")
rec_rep = next(x for x in reps if x["what"] == "record")
client.post(f"/api/master/reports/{rec_rep['id']}", json={"action": "none"}, headers=hdr(mtok))
chk(client.get("/api/master/reports", headers=hdr(mtok)).get_json()["reports"] == [], "both reports are settled")
client.post(f"/api/master/accounts/{aid}", json={"hidden": False}, headers=hdr(mtok))
chk("aoife" in rooms(bea) and rid in cat(bea), "the master can put the room back up")

# ── images for a room need the rights line ──
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (40, 40), (1, 2, 3)).save(buf, "JPEG")
r = client.post("/api/my/room/assets", data={"image": (io.BytesIO(buf.getvalue()), "x.jpg")}, headers=hdr(bea), content_type="multipart/form-data")
chk(r.status_code == 400 and r.get_json().get("need_rights"), "a picture for a room needs the rights line")
r = client.post("/api/my/room/assets", data={"rights": "1", "image": (io.BytesIO(buf.getvalue()), "x.jpg")}, headers=hdr(bea), content_type="multipart/form-data")
chk(r.status_code == 200, "with it, the picture goes up")

import zlib, struct
def _png_bomb(side=20000):
    raw = zlib.compress(b"\x00" * (side + 1) * 1, 9)            # (only the header matters: it is refused before decoding)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")
r = client.post("/api/my/room/assets", data={"rights": "1", "image": (io.BytesIO(_png_bomb()), "bomb.png")}, headers=hdr(bea), content_type="multipart/form-data")
chk(r.status_code == 400, "a picture far too big to open is refused, not opened")

# ── feedback ──
client.post("/api/feedback", json={"kind": "bug", "note": "the deck froze", "page": "/room"}, headers=hdr(bea))
fb = client.get("/api/master/feedback", headers=hdr(mtok)).get_json()["feedback"]
chk(len(fb) == 1 and fb[0]["by"]["handle"] == "bea" and fb[0]["kind"] == "bug", "the master reads feedback and bug reports, and who sent them")
client.post(f"/api/master/feedback/{fb[0]['id']}", json={"status": "done"}, headers=hdr(mtok))
chk(client.get("/api/master/feedback", headers=hdr(mtok)).get_json()["feedback"] == []
    and len(client.get("/api/master/feedback?status=all", headers=hdr(mtok)).get_json()["feedback"]) == 1, "marked done, it leaves the open list")
chk(client.get("/api/master/feedback", headers=hdr(bea)).status_code == 403, "nobody else reads other people's feedback")

# ── the version everyone should be on ──
chk(client.get("/api/version").get_json()["version"] == "", "no version is named to begin with (and the question needs no sign-in)")
chk(client.post("/api/master/version", json={"version": "2026.11.20", "url": "javascript:alert(1)"}, headers=hdr(mtok)).status_code == 400,
    "the download address must be a web address")
client.post("/api/master/version", json={"version": "2026.11.20", "url": "https://github.com/x/y/releases/tag/v2026.11.20", "note": "first"}, headers=hdr(mtok))
v = client.get("/api/version").get_json()
chk(v["version"] == "2026.11.20" and v["url"].startswith("https://github.com") and v["house_rules"], "everyone can ask which version to be on")
chk(client.post("/api/master/version", json={"version": "x"}, headers=hdr(bea)).status_code == 403, "only the master names it")

# ── a public grúpa can be taken down too ──
client.post("/api/my/grupai", json={"local_id": 1, "name": "Late", "items": [{"kind": "link", "title": "A", "url": "https://example.com"}]}, headers=hdr(aoife))
gid = client.get("/api/grupai", headers=hdr(bea)).get_json()["grupai"][0]["id"]
client.post("/api/report", json={"what": "grupa", "ref": str(gid), "reason": "hurtful"}, headers=hdr(bea))
rep = client.get("/api/master/reports", headers=hdr(mtok)).get_json()["reports"][0]
client.post(f"/api/master/reports/{rep['id']}", json={"action": "hide"}, headers=hdr(mtok))
chk(client.get("/api/grupai", headers=hdr(bea)).get_json()["grupai"] == [] and client.get(f"/api/grupai/{gid}", headers=hdr(bea)).status_code == 404
    and client.get(f"/api/grupai/{gid}", headers=hdr(aoife)).get_json().get("hidden") is not None,
    "a reported grúpa taken down is gone for others; its owner still sees it, marked")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
