"""Applying for more than a listener's account (gr_apply.py), event pages
(gr_happenings.py) and letting another account manage yours (gr_behalf.py):
a listener's account works at once and its room can be public; an artist, label,
venue or experience creator account is applied for and waits for the master; until
then nothing can be published or sold; the queue is the master's alone and keeps
who decided, when and why; event pages belong to experience creators and venues;
an artist lets a label in, with a scope, and takes it back, and what the label
does is written down.
A fresh database, no network, no sound. Run:  ./venv/bin/python test_gr_apply.py"""
import io
import json
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
os.environ["MR_GR_DB"] = str(TMP / "gr_apply_test.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")

import gr_server
import gr_master
import gr_signin
import gr_apply
import gr_happenings
import gr_behalf

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
gr_signin.set_rules_here({"master_2fa": "off"})       # (the master's two-factor has its own test: test_gr_signin.py)
client = gr_server.app.test_client()
def hdr(tok, whose=None): return dict({"Authorization": f"Bearer {tok}"}, **({gr_behalf.HEADER: whose} if whose else {}))
def sql(q, *p):
    with closing(gr_server.db()) as c:
        return c.execute(q, p).fetchall()
def signup(name, **more):
    gr_master._rate.clear()
    return client.post("/api/signup", json=dict({"name": name, "fingerprint": "mac-" + name, "agreed": True}, **more)).get_json()
def get(tok, path, **kw): return client.get(path, headers=hdr(tok, kw.pop("whose", None)), **kw)
def post(tok, path, body=None, whose=None): return client.post(path, json=body or {}, headers=hdr(tok, whose))
def wav_bytes(n=4000, b=1):
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(bytes([b, 1]) * n)
    return buf.getvalue()
def upload(tok, whose=None, title="A Record"):
    return client.post("/api/my/records", data={"rights": "1", "title": title, "audio": (io.BytesIO(wav_bytes()), "x.wav")},
                       headers=hdr(tok, whose), content_type="multipart/form-data")
FORM = {"name": "Night Shapes", "email": "hello@nightshapes.example", "location": "Belfast", "region": "uk",
        "links": ["https://nightshapes.example"], "about": "A club night on the last Friday of the month."}
EVENT = {"title": "Night Shapes 12", "starts_at": "2099-12-05T22:00", "place": "The Menagerie, Belfast", "about": "Four hours, one room."}

gr_master.make_master("Daithí", handle="daithi")
master = client.post("/api/join", json={"invite_code": sql("SELECT invite_code FROM gr_accounts WHERE handle='daithi'")[0][0],
                                         "fingerprint": "mac-daithi"}).get_json()["token"]

# ── a listener: works at once, and may make their room public with nobody's say ──
d = signup("Lena")
lena = d["token"]
me = get(lena, "/api/me").get_json()
chk(me["kind"] == "listener" and me["apply"]["status"] == "approved" and me["apply"]["can_apply"] and not me["has_events"],
    "a listener's account is approved from the start")
r = post(lena, "/api/my/room/profile", {"is_public": True})
chk(r.status_code == 200 and r.get_json()["is_public"] and any(x["handle"] == "lena" for x in get(lena, "/api/rooms").get_json()["rooms"]),
    "a listener makes their room public without approval")

# ── saying what you are at sign-up is a note, not a request ──
d = signup("Night Shapes", interest="experience creator")
ns = d["token"]
me = get(ns, "/api/me").get_json()
chk(d["kind"] == "listener" and d["kind_requested"] == "" and me["apply"]["interest"] == "experience creator" and me["apply"]["application"] is None,
    "saying you are an experience creator at sign-up makes a listener, with the note kept and no application yet")
chk(sql("SELECT COUNT(*) FROM gr_applications")[0][0] == 0, "…and nothing in the master's queue")

# ── the form ──
form = get(ns, "/api/apply").get_json()
keys = [k["key"] for k in form["kinds"]]
chk(keys == ["artist", "label", "shop", "venue", "experience creator", "business"], "the kinds that can be applied for (digital artists are switched off)")
chk({"name", "email", "location", "links", "about"} <= {f["key"] for f in form["kinds"][0]["fields"]},
    "the form asks at least a name, a contact email, where, links to work, and an about")
chk([x["price"] for x in form["regions"]] == ["€x a month", "£x a month", "€x a month"], "one tier: £x a month from the UK, €x a month from anywhere else, until the price is set")
chk(post(ns, "/api/apply", {"kind": "experience creator", "fields": dict(FORM, about="")}).status_code == 400, "a form with a needed line empty is refused")
chk(post(ns, "/api/apply", {"kind": "experience creator", "fields": dict(FORM, links=["nightshapes"])}).status_code == 400, "a link has to be a link")
chk(post(ns, "/api/apply", {"kind": "master", "fields": FORM}).status_code == 400, "nobody applies to be the master")

# ── before applying, and while waiting: nothing published or sold ──
chk(upload(ns).status_code == 403 and post(ns, "/api/my/happenings", EVENT).status_code == 403, "a listener can't sell a record or make an event page")
r = post(ns, "/api/apply", {"kind": "experience creator", "fields": FORM})
chk(r.status_code == 200 and r.get_json()["status"] == "pending" and not r.get_json()["can_apply"], "the application goes in and waits")
chk(post(ns, "/api/apply", {"kind": "venue", "fields": FORM}).status_code == 409, "one application at a time")
me = get(ns, "/api/me").get_json()
chk(me["kind"] == "listener" and me["apply"]["status"] == "pending" and me["apply"]["application"]["price"] == "£x a month" and not me["has_events"],
    "waiting, the account is still a listener; the price shown is for where it applied from")
chk(upload(ns).status_code == 403 and post(ns, "/api/my/happenings", EVENT).status_code == 403,
    "a pending account can't publish: no record for sale, no event page")
chk(get(ns, "/api/my/happenings").get_json() == {"can": False, "happenings": [], "not_yet": gr_happenings.WORDS["not_yet"]}, "…and has no event pages to show")
chk("happenings" not in get(lena, "/api/rooms/night-shapes").get_json() if post(ns, "/api/my/room/profile", {"is_public": True}).status_code == 200 else False,
    "its room (a listener's) carries no events")

# ── the queue is the master's alone ──
chk(get(ns, "/api/master/applications").status_code == 403 and get(lena, "/api/master/applications").status_code == 403
    and post(lena, "/api/master/applications/1", {"decision": "approve"}).status_code == 403, "only the master reads the queue or decides")
chk(client.get("/api/master/applications").status_code == 401, "…and nobody who isn't signed in")
r = client.get("/api/master/applications", headers=hdr(master), environ_base={"REMOTE_ADDR": "203.0.113.9"})
chk(r.status_code == 403, "…and the master only on the server's own computer")
q = get(master, "/api/master/applications").get_json()["applications"]
chk(len(q) == 1 and q[0]["kind"] == "experience creator" and q[0]["fields"]["location"] == "Belfast" and q[0]["by"]["handle"] == "night-shapes"
    and q[0]["status"] == "pending", "the master sees the application whole: who, what kind, the form")
chk(get(master, "/api/master/overview").get_json()["applications"] == 1, "the master's front page counts it")
chk(post(master, "/api/master/applications/1", {"decision": "maybe"}).status_code == 400, "approve or reject, nothing else")

# ── rejected, with a note; then applied for again and approved ──
r = post(master, "/api/master/applications/1", {"decision": "reject", "note": "Send a link to a past night."})
row = sql("SELECT * FROM gr_applications WHERE id=1")[0]
chk(r.status_code == 200 and row["status"] == "rejected" and row["note"] == "Send a link to a past night." and row["decided_at"]
    and row["decided_by"] == sql("SELECT id FROM gr_accounts WHERE handle='daithi'")[0][0], "rejected: who decided, when and why are kept")
me = get(ns, "/api/me").get_json()
chk(me["kind"] == "listener" and me["apply"]["status"] == "rejected" and me["apply"]["application"]["note"] == "Send a link to a past night."
    and me["apply"]["can_apply"], "the applicant reads the note and can apply again")
chk(post(ns, "/api/my/happenings", EVENT).status_code == 403, "a rejected account still can't publish")
chk(post(master, "/api/master/applications/1", {"decision": "approve"}).status_code == 409, "a settled application isn't decided twice")
post(ns, "/api/apply", {"kind": "experience creator", "fields": dict(FORM, links=["https://nightshapes.example", "https://ra.example/night-shapes"])})
r = post(master, "/api/master/applications/2", {"decision": "approve", "note": "Welcome."})
me = get(ns, "/api/me").get_json()
chk(r.status_code == 200 and me["kind"] == "experience creator" and me["apply"]["status"] == "approved" and me["has_events"] and not me["apply"]["can_apply"],
    "approved: the listener account becomes an experience creator account")
ev = [json.loads(e["data"]) for e in sql("SELECT data FROM gr_events WHERE kind='master_application' ORDER BY id")]
chk([e["decision"] for e in ev] == ["rejected", "approved"] and ev[1]["note"] == "Welcome.", "both decisions are in the activity log")
acc = [a for a in get(master, "/api/master/accounts").get_json()["accounts"] if a["handle"] == "night-shapes"][0]
chk(acc["status"] == "approved" and acc["kind"] == "experience creator" and "experience creator" in get(master, "/api/master/accounts").get_json()["kinds"],
    "the master's list of accounts shows it, and has the new kind")

# ── statuses: pending · approved · rejected · suspended ──
post(master, f"/api/master/accounts/{acc['id']}", {"paused": True, "note": "for a check"})
acc = [a for a in get(master, "/api/master/accounts").get_json()["accounts"] if a["handle"] == "night-shapes"][0]
chk(acc["status"] == "suspended" and get(ns, "/api/me").status_code == 401, "a paused account reads suspended, and its sign-in stops")
post(master, f"/api/master/accounts/{acc['id']}", {"paused": False})

# ── an older app asks at sign-up with no form: one queue all the same ──
d = signup("Old Label", kind="label")
chk(d["kind"] == "listener" and d["kind_requested"] == "label", "an older app's request still makes a listener with the request waiting")
q = get(master, "/api/master/applications").get_json()["applications"]
chk(len(q) == 1 and q[0]["bare"] and q[0]["kind"] == "label" and q[0]["fields"] == {}, "…and it is in the queue, marked as having no form")
oid = sql("SELECT id FROM gr_accounts WHERE name='Old Label'")[0][0]
post(master, f"/api/master/accounts/{oid}", {"request": "approve"})
row = sql("SELECT * FROM gr_applications WHERE account_id=?", oid)[0]
chk(row["status"] == "approved" and row["decided_by"] and get(d["token"], "/api/me").get_json()["kind"] == "label",
    "approved from the Accounts list, the application is settled too, with who decided")
label = d["token"]

# ── the form is easy to extend for one kind ──
gr_apply.EXTRA["venue"].append({"key": "capacity", "label": "Capacity", "kind": "text", "need": True, "max": 40})
d = signup("The Menagerie", interest="venue")
venue = d["token"]
chk("capacity" in [f["key"] for f in [k for k in get(venue, "/api/apply").get_json()["kinds"] if k["key"] == "venue"][0]["fields"]]
    and "capacity" not in [f["key"] for f in get(venue, "/api/apply").get_json()["kinds"][0]["fields"]], "a question added for venues is asked of venues only")
chk(post(venue, "/api/apply", {"kind": "venue", "fields": dict(FORM, name="The Menagerie")}).status_code == 400
    and post(venue, "/api/apply", {"kind": "venue", "fields": dict(FORM, name="The Menagerie", capacity="180")}).status_code == 200, "…and needed when it says so")
gr_apply.EXTRA["venue"].clear()
chk(post(venue, "/api/apply/withdraw").get_json()["can_apply"] and sql("SELECT status FROM gr_applications WHERE account_id=(SELECT id FROM gr_accounts WHERE name='The Menagerie')")[0][0] == "withdrawn",
    "an applicant can take their application back")
post(venue, "/api/apply", {"kind": "venue", "fields": dict(FORM, name="The Menagerie", region="ie")})
post(master, f"/api/master/applications/{sql('SELECT MAX(id) FROM gr_applications')[0][0]}", {"decision": "approve"})

# ── the price of the one tier ──
chk(post(lena, "/api/master/tier", {"gbp": 1, "eur": 1}).status_code == 403, "only the master sets the price")
chk(post(master, "/api/master/tier", {"gbp": 8, "eur": 9.5}).status_code == 200
    and [x["price"] for x in get(lena, "/api/apply").get_json()["regions"]] == ["€9.50 a month", "£8 a month", "€9.50 a month"], "set, it reads in pounds for the UK and euro elsewhere")

# ── event pages: experience creators and venues ──
r = post(ns, "/api/my/happenings", EVENT)
hid = r.get_json()["happening"]["id"]
chk(r.status_code == 200 and r.get_json()["happening"]["status"] == "draft", "an experience creator makes an event page; it starts as a draft")
chk(get(lena, "/api/rooms/night-shapes").get_json()["happenings"] == [] and get(lena, "/api/happenings").get_json()["happenings"] == [], "a draft is not shown to anyone")
chk(post(ns, f"/api/my/happenings/{hid}", {"status": "published"}).status_code == 200
    and [e["title"] for e in get(lena, "/api/rooms/night-shapes").get_json()["happenings"]] == ["Night Shapes 12"], "published, it is in their public room")
up = get(lena, "/api/happenings").get_json()["happenings"]
chk(len(up) == 1 and up[0]["by"]["handle"] == "night-shapes" and up[0]["by"]["kind"] == "experience creator" and up[0]["place"] == "The Menagerie, Belfast",
    "…and in the list of what is coming up, with whose it is")
chk(post(venue, "/api/my/happenings", dict(EVENT, title="Sunday Session", status="published")).status_code == 200, "a venue has event pages too")
chk(post(label, "/api/my/happenings", EVENT).status_code == 403 and post(lena, "/api/my/happenings", EVENT).status_code == 403, "a label and a listener do not")
chk(post(ns, "/api/my/happenings", dict(EVENT, starts_at="next friday")).status_code == 400 and post(ns, "/api/my/happenings", dict(EVENT, title="")).status_code == 400
    and post(ns, "/api/my/happenings", dict(EVENT, ends_at="2099-12-05T20:00")).status_code == 400 and post(ns, "/api/my/happenings", dict(EVENT, link="javascript:alert(1)")).status_code == 400,
    "an event needs a name, a real day and time, an end after its start, and a real link")
r1, r2 = post(ns, "/api/my/happenings", dict(EVENT, tickets="10")), post(ns, f"/api/my/happenings/{hid}", {"is_private": True})
chk(r1.status_code == r2.status_code == 409 and r1.get_json()["not_yet"], "ticket sales and private events are placeholders: asked for, they answer 'not yet'")
chk(post(venue, f"/api/my/happenings/{hid}", {"title": "Mine now"}).status_code == 404 and client.delete(f"/api/my/happenings/{hid}", headers=hdr(venue)).get_json() == {"removed": False},
    "nobody changes or removes someone else's event page")
post(ns, "/api/my/happenings", dict(EVENT, title="Night Shapes 1", starts_at="2020-01-31T22:00", status="published"))
chk([e["title"] for e in get(lena, "/api/rooms/night-shapes").get_json()["happenings"]] == ["Night Shapes 12", "Night Shapes 1"]
    and [e["title"] for e in get(lena, "/api/happenings").get_json()["happenings"]] == ["Night Shapes 12"],
    "a room shows what is coming first, then what has been; the coming-up list leaves out the past, and the venue's event while its room is private")
post(venue, "/api/my/room/profile", {"is_public": True})
chk(len(get(lena, "/api/happenings").get_json()["happenings"]) == 2, "the venue's room made public, its event joins the list")
post(master, f"/api/master/accounts/{acc['id']}", {"hidden": True})
chk(all(e["by"]["handle"] != "night-shapes" for e in get(lena, "/api/happenings").get_json()["happenings"]), "a room the master took down has its events off the list")
post(master, f"/api/master/accounts/{acc['id']}", {"hidden": False})

# ── an artist lets a label manage their account ──
gr_server.make_invite("Órla", kind="artist", handle="orla", public=True)
orla = client.post("/api/join", json={"invite_code": sql("SELECT invite_code FROM gr_accounts WHERE handle='orla'")[0][0], "fingerprint": "mac-orla"}).get_json()["token"]
n0 = sql("SELECT COUNT(*) FROM gr_tracks")[0][0]
chk(upload(label, whose="orla").status_code == 403 and get(label, "/api/my/records", whose="orla").status_code == 403, "a label not let in can do nothing on the artist's account")
chk(post(label, "/api/my/behalf", {"handle": "orla", "scope": "full"}).status_code == 403, "only an artist account lets another in")
chk(post(orla, "/api/my/behalf", {"handle": "orla", "scope": "full"}).status_code == 400 and post(orla, "/api/my/behalf", {"handle": "nobody-here", "scope": "full"}).status_code == 404
    and post(orla, "/api/my/behalf", {"handle": "old-label", "scope": "everything"}).status_code == 400, "…a real other account, with a real scope")
r = post(orla, "/api/my/behalf", {"handle": "@old-label", "scope": "records"})
g = r.get_json()
chk(r.status_code == 200 and [(x["handle"], x["scope"]) for x in g["given"]] == [("old-label", "records")] and len(g["scopes"]) == 2,
    "the artist lets the label manage releases")
chk([(x["handle"], x["scope"]) for x in get(label, "/api/me").get_json()["manages"]] == [("orla", "records")], "the label sees whose account it may manage")
r = upload(label, whose="orla", title="For Órla")
oid_ = sql("SELECT id FROM gr_accounts WHERE handle='orla'")[0][0]
lid = sql("SELECT id FROM gr_accounts WHERE name='Old Label'")[0][0]
t = sql("SELECT * FROM gr_tracks ORDER BY id DESC LIMIT 1")[0]
chk(r.status_code == 200 and t["owner_account_id"] == oid_ and t["status"] == "pending", "signed in as itself, the label puts a record up FOR the artist (it waits for the master like any other)")
chk([x["title"] for x in get(label, "/api/my/records", whose="orla").get_json()["records"]] == [t["title"]] and get(label, "/api/my/records").get_json()["records"] == [],
    "the record is the artist's, not the label's")
log = [json.loads(e["data"]) for e in sql("SELECT data FROM gr_events WHERE kind='behalf' AND account_id=?", oid_)]
chk(len(log) == 1 and log[0]["by"] == lid and log[0]["by_handle"] == "old-label" and log[0]["for"] == oid_ and log[0]["did"] == "POST /api/my/records" and log[0]["answer"] == 200,
    "it is written down: who did it, for whom, what, and how it was answered")
chk(get(orla, "/api/my/behalf").get_json()["log"][0]["by_handle"] == "old-label", "the artist can read that log")
r = post(label, "/api/my/room/profile", {"bio": "written by the label"}, whose="orla")
chk(r.status_code == 403 and "written by the label" not in str(sql("SELECT bio FROM gr_accounts WHERE handle IN ('orla','old-label')")),
    "'manage releases' doesn't reach the artist's room — and the change does NOT land on the label's own room instead")
for path in ("/api/me", "/api/my/behalf", "/api/me/security", "/api/sim/me", "/api/catalogue"):
    chk(get(label, path, whose="orla").status_code == 403, f"never for someone else: {path}")
chk(post(label, "/api/me/password", {"new": "a-password-for-orla", "email": "orla@example.ie"}, whose="orla").status_code == 403
    and not sql("SELECT password_hash FROM gr_accounts WHERE handle='orla'")[0][0], "a manager can't touch the artist's sign-in")
post(orla, "/api/my/behalf", {"handle": "old-label", "scope": "full"})
r = post(label, "/api/my/room/profile", {"bio": "Órla, from Derry."}, whose="orla")
chk(r.status_code == 200 and sql("SELECT bio FROM gr_accounts WHERE handle='orla'")[0][0] == "Órla, from Derry." and len(get(orla, "/api/my/behalf").get_json()["given"]) == 1,
    "given full access instead, the label can change the artist's room (one grant, not two)")
chk(get(master, "/api/master/overview", whose="orla").status_code == 403, "full access is not the master's page")
bid = get(orla, "/api/my/behalf").get_json()["given"][0]["id"]
chk(client.delete(f"/api/my/behalf/{bid}", headers=hdr(lena)).status_code == 404, "a stranger can't take the grant away")
r = client.delete(f"/api/my/behalf/{bid}", headers=hdr(orla))
chk(r.status_code == 200 and r.get_json()["given"] == [] and get(label, "/api/me").get_json()["manages"] == [], "the artist takes it back")
chk(upload(label, whose="orla").status_code == 403 and post(label, "/api/my/room/profile", {"bio": "again"}, whose="orla").status_code == 403
    and sql("SELECT COUNT(*) FROM gr_tracks")[0][0] == n0 + 1, "taken back, the label is refused at once")
chk(sql("SELECT revoked_at, revoked_by FROM gr_behalf WHERE id=?", bid)[0]["revoked_by"] == oid_, "who took it back, and when, is kept")

print()
if fails:
    print(f"{len(fails)} FAILED:"); [print("   ", f) for f in fails]; sys.exit(1)
print("all passed")
