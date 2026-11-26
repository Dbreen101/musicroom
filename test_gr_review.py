"""The rooms server — what the review of 2026-11-21 found, held by a check each.

Every one of these was a real fault before the fellows' release: starting credits given
twice, a download that died on a file name with a fada, a third sign-in refused for ever,
a deleted picture's number handed to the next one, a paused person "signing in", a
taken-down room still reaching people, a report that hid nothing, links that broke a room."""
import io
import json
import os
import sys
import tempfile
import threading
import unicodedata
import wave
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["MR_GR_DB"] = str(Path(_tmp.name) / "gr_test.db")
os.environ["MR_LIBRARY_DB"] = str(Path(_tmp.name) / "no_library.db")

import gr_server
import gr_master
import gr_shop
import gr_sim

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
def db(): return closing(gr_server.db())
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def wav_bytes(n=4000, b=1):
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(bytes([b, 1]) * n)
    return buf.getvalue()
def code_of(handle):
    with db() as c:
        return c.execute("SELECT invite_code FROM gr_accounts WHERE handle=?", (handle,)).fetchone()[0]

with db() as conn:
    gr_server.init_db(conn)
    gr_shop.ensure(conn); gr_sim.ensure(conn)
    gr_master.set_setting(conn, "sim", dict(gr_sim.DEFAULTS, on=True))        # the credits trial is on
client = gr_server.app.test_client()
def join(code, fp):
    gr_master._rate.clear()                    # (the sign-in limit per address is not what is tested here)
    return client.post("/api/join", json={"invite_code": code, "fingerprint": fp, "device_name": "laptop"})
def get(tok, path, **kw): return client.get(path, headers=hdr(tok), **kw)
def post(tok, path, body=None): return client.post(path, json=body or {}, headers=hdr(tok))

gr_master.make_master("The Master", handle="boss")
import gr_signin; gr_signin.set_rules_here({"master_2fa": "off"})   # (the master's two-factor has its own test: test_gr_signin.py)
mtok = join(code_of("boss"), "mac-boss").get_json()["token"]
gr_server.make_invite("Órla Artist", kind="artist", public=True)
otok = join(code_of("orla-artist"), "mac-orla").get_json()["token"]
START = int(gr_sim.DEFAULTS["start_credits"])

# ── the starting credits are given once, however many first requests arrive together ──
people = []
for i in range(12):
    gr_server.make_invite(f"New Person {i}")
    people.append(join(code_of(f"new-person-{i}"), f"mac-np{i}").get_json()["token"])
for tok in people:
    gate = threading.Barrier(4)
    def ask(path, tok=tok, gate=gate):
        gate.wait(); client.get(path, headers=hdr(tok))
    ts = [threading.Thread(target=ask, args=(p,)) for p in ("/api/me", "/api/sim/me", "/api/sim/mine", "/api/shop")]
    [t.start() for t in ts]; [t.join() for t in ts]
got = [get(tok, "/api/sim/me").get_json()["credits"] for tok in people]
with db() as c:
    starts = [r[0] for r in c.execute("SELECT COUNT(*) FROM gr_ledger WHERE what='start' GROUP BY account_id")]
chk(got == [START] * 12 and set(starts) == {1}, f"twelve new people, four first requests each at once: every one starts with {START}, once")

# ── a record whose FILE NAME has a fada typed the Mac's way, a long dash and a curly quote ──
nasty = unicodedata.normalize("NFD", "Róisín") + " – Don’t Go 🎵.wav"
r = client.post("/api/my/records", data={"rights": "1", "title": "Don't Go", "artist": "Órla Artist",
                                         "audio": (io.BytesIO(wav_bytes()), nasty)},
                headers=hdr(otok), content_type="multipart/form-data")
chk(r.status_code == 200, "an artist uploads a record with such a file name")
rid = r.get_json()["record"]["id"] if r.status_code == 200 and "record" in r.get_json() else None
if rid is None:
    with db() as c:
        rid = c.execute("SELECT MAX(id) FROM gr_tracks").fetchone()[0]
os.environ["MR_MASTER_ANYWHERE"] = "1"
chk(post(mtok, f"/api/master/records/{rid}", {"status": "live"}).status_code == 200, "the master lets it out")
lis = people[0]
b = post(lis, "/api/borrow", {"track_id": rid})
chk(b.status_code == 200 and get(lis, "/api/sim/me").get_json()["credits"] == START - int(gr_sim.DEFAULTS["home_cost"]),
    "a listener brings it home, for the credits it costs")
bid = b.get_json().get("borrow_id") or b.get_json().get("id")
dl = get(lis, f"/api/download/{bid}")
ok_headers = True
for k, v in dl.headers.items():
    try:
        (k + v).encode("latin-1")
    except UnicodeEncodeError:
        ok_headers = False
chk(dl.status_code == 200 and ok_headers and len(dl.data) > 0, "…and the file comes down: nothing in the answer's headers that a server can't send")

# ── the one play is not spent when there is nothing to hand over ──
lis2 = people[1]
p2 = post(lis2, "/api/shop/crates/pull").get_json()["pull"]
real_copy = gr_shop.listen_copy
gr_shop.listen_copy = lambda track: (None, "the copy could not be made")
r1 = get(lis2, f"/api/shop/listen/{rid}?pull={p2['id']}")
gr_shop.listen_copy = real_copy
with db() as c:
    spent = c.execute("SELECT COUNT(*) FROM gr_heard WHERE track_id=?", (rid,)).fetchone()[0]
chk(r1.status_code == 503 and spent == 0, "a listen that could hand nothing over answers so, and the one play is still there")
if gr_shop._ffmpeg():
    r2 = get(lis2, f"/api/shop/listen/{rid}?pull={p2['id']}")
    r3 = get(lis2, f"/api/shop/listen/{rid}?pull={p2['id']}")
    chk(r2.status_code == 200 and r3.status_code == 403, "…the next try plays; the one after is refused (heard)")
    # the record's own file away (a drive unplugged): the copy already made still plays, for someone else
    with db() as c:
        path = c.execute("SELECT path FROM gr_tracks WHERE id=?", (rid,)).fetchone()[0]
    os.rename(path, path + ".away")
    p3 = post(people[2], "/api/shop/crates/pull").get_json()["pull"]
    chk(get(people[2], f"/api/shop/listen/{rid}?pull={p3['id']}").status_code == 200, "…and with the record's own file away, its listening copy still plays")
    os.rename(path + ".away", path)

# ── two spends at once from one account: charged once each, never below zero ──
with db() as c:
    c.execute("UPDATE gr_accounts SET credits=1 WHERE id=(SELECT account_id FROM gr_devices WHERE token=?)", (people[3],)); c.commit()
gate = threading.Barrier(2); out = []
def spend():
    gate.wait(); out.append(post(people[3], "/api/borrow", {"track_id": rid}).status_code)
ts = [threading.Thread(target=spend) for _ in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]
left = get(people[3], "/api/sim/me").get_json()["credits"]
with db() as c:
    held = c.execute("SELECT COUNT(*) FROM gr_borrows WHERE track_id=? AND returned_at IS NULL AND account_id="
                     "(SELECT account_id FROM gr_devices WHERE token=?)", (rid, people[3])).fetchone()[0]
chk(left >= 0 and held == 1, f"the same record brought home twice at once: held once, credits not below zero (left {left})")

# ── a third laptop: refused, until the master signs the account's devices out ──
gr_server.make_invite("Moved Twice")
c1 = join(code_of("moved-twice"), "laptop-1"); c2 = join(code_of("moved-twice"), "laptop-2"); c3 = join(code_of("moved-twice"), "laptop-3")
chk(c1.status_code == 200 and c2.status_code == 200 and c3.status_code == 403, "a third device is refused")
with db() as c:
    aid = c.execute("SELECT id FROM gr_accounts WHERE handle='moved-twice'").fetchone()[0]
r = post(mtok, f"/api/master/accounts/{aid}", {"devices": "free"})
chk(r.status_code == 200 and "2 devices signed out" in r.get_json()["did"], "the master signs its devices out")
chk(join(code_of("moved-twice"), "laptop-3").status_code == 200 and get(c1.get_json()["token"], "/api/me").status_code == 401,
    "…the third laptop signs in with the account's code; the old ones are signed out")

# ── a paused person is told so ──
post(mtok, f"/api/master/accounts/{aid}", {"paused": True, "note": "ask at the desk"})
r = join(code_of("moved-twice"), "laptop-3")
chk(r.status_code == 403 and r.get_json().get("paused") and "ask at the desk" in r.get_json()["error"], "a paused account's sign-in says it is paused, and why")
post(mtok, f"/api/master/accounts/{aid}", {"paused": False})

# ── a deleted picture's number is not handed to the next picture ──
from PIL import Image
def picture(colour):
    buf = io.BytesIO(); Image.new("RGB", (40, 40), colour).save(buf, "JPEG"); buf.seek(0); return buf
up = lambda colour: client.post("/api/my/room/assets", data={"rights": "1", "image": (picture(colour), "p.jpg")},
                                headers=hdr(otok), content_type="multipart/form-data").get_json()
up("red"); up("blue")
ids = [a["id"] for a in get(otok, "/api/my/room/assets").get_json()["assets"]]
last = max(ids)
client.delete(f"/api/my/room/assets/{last}", headers=hdr(otok))
again = client.post("/api/my/room/assets", data={"rights": "1", "image": (picture("green"), "p.jpg")},
                    headers=hdr(otok), content_type="multipart/form-data").get_json()
now = [a["id"] for a in get(otok, "/api/my/room/assets").get_json()["assets"]]
chk(last not in now and max(now) > last and client.get(f"/api/assets/{last}", headers=hdr(lis)).status_code == 404,
    "a deleted picture's number is spent: the next picture gets a new one, the old address answers nothing")

# ── a removed record takes what was remembered about it with it ──
r = client.post("/api/my/records", data={"rights": "1", "title": "Short Lived", "audio": (io.BytesIO(wav_bytes(b=3)), "s.wav")},
                headers=hdr(otok), content_type="multipart/form-data")
with db() as c:
    sid = c.execute("SELECT MAX(id) FROM gr_tracks").fetchone()[0]
    c.execute("INSERT OR IGNORE INTO gr_heard(account_id, track_id, via, at) VALUES(?,?,?,?)", (aid, sid, "pull", gr_server._now())); c.commit()
chk(client.delete(f"/api/my/records/{sid}", headers=hdr(otok)).status_code == 200, "an artist removes a record nobody holds")
with db() as c:
    chk(c.execute("SELECT COUNT(*) FROM gr_heard WHERE track_id=?", (sid,)).fetchone()[0] == 0,
        "…and nobody is left marked as having heard its number")
chk(client.delete(f"/api/my/records/{rid}", headers=hdr(otok)).status_code == 409, "a record someone has brought home can't be removed")

# ── a room the master took down: its crate is not handed out, its records can't be had by number ──
with db() as c:
    oid = c.execute("SELECT id FROM gr_accounts WHERE handle='orla-artist'").fetchone()[0]
    c.execute("INSERT INTO gr_crates(account_id, name, note, is_out, created_at, updated_at) VALUES(?,?,?,1,?,?)",
              (oid, "Órla's crate", "", gr_server._now(), gr_server._now()))
    cid = c.execute("SELECT MAX(id) FROM gr_crates").fetchone()[0]
    c.execute("INSERT INTO gr_crate_items(crate_id, track_id, pos, note) VALUES(?,?,0,'')", (cid, rid)); c.commit()
    before = [x["id"] for x in gr_shop._out_crates(c)]
post(mtok, f"/api/master/accounts/{oid}", {"hidden": True, "note": "taken down"})
with db() as c:
    after = [x["id"] for x in gr_shop._out_crates(c)]
chk(cid in before and cid not in after, "a taken-down room's crate leaves the shop floor")
chk(post(people[5], "/api/borrow", {"track_id": rid}).status_code == 404 and post(people[5], "/api/buy", {"track_id": rid}).status_code == 404,
    "…and its records can't be brought home or bought by their number")
post(mtok, f"/api/master/accounts/{oid}", {"hidden": False})

# ── a reported room is taken down by whose it is, whatever its address is now ──
chk(post(lis, "/api/report", {"what": "room", "ref": "orla-artist", "reason": "rights"}).status_code == 200, "a room is reported")
client.patch("/api/my/room/profile", json={"handle": "orla-moved"}, headers=hdr(otok))
client.post("/api/my/room/profile", json={"handle": "orla-moved"}, headers=hdr(otok))
rep = get(mtok, "/api/master/reports").get_json()["reports"][0]
post(mtok, f"/api/master/reports/{rep['id']}", {"action": "hide"})
with db() as c:
    row = c.execute("SELECT handle, hidden_at FROM gr_accounts WHERE id=?", (oid,)).fetchone()
chk(bool(row["hidden_at"]), f"the room is down (its address is now “{row['handle']}”)")

# ── twenty long links don't break the room ──
links = [{"label": "L" * 300, "url": "https://example.org/" + "x" * 900} for _ in range(30)]
for method in (client.patch, client.post, client.put):
    r = method("/api/my/room/profile", json={"links": links}, headers=hdr(otok))
    if r.status_code == 200:
        break
with db() as c:
    stored = c.execute("SELECT links FROM gr_accounts WHERE id=?", (oid,)).fetchone()[0]
try:
    kept = json.loads(stored or "[]")
except ValueError:
    kept = None
chk(kept is not None and len(kept) <= 20 and all(len(l["url"]) <= 500 and len(l["label"]) <= 120 for l in kept),
    "links are kept readable: twenty at most, each one bounded")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
