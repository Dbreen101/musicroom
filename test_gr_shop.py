"""Record shopping on the rooms server — crates, the counter, blind listening,
and the shop's listening copies. Run:  ./venv/bin/python test_gr_shop.py"""
import json
import os
import random
import subprocess
import sys
import tempfile
import wave
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
os.environ["MR_GR_DB"] = str(TMP / "gr_shop_test.db")
os.environ["MR_LIBRARY_DB"] = str(TMP / "no_library.db")   # keep David's library out
os.environ.pop("MR_SHOP_PLAY_ORIGINALS", None)

import gr_server
import gr_shop

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

client = gr_server.app.test_client()
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def get(tok, path): return client.get(path, headers=hdr(tok))
def post(tok, path, body=None): return client.post(path, json=body or {}, headers=hdr(tok))
def db(): return closing(gr_server.db())


def tone(path, n=1600):
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(bytes(random.Random(str(path)).randrange(256) for _ in range(n * 2)))


# ─── the shelves: a label with 30 records, an artist with 6, 4 with no owner ───
with db() as conn:
    gr_server.init_db(conn)
codes = {
    "moss": gr_server.make_invite("Moss Records", kind="label", handle="moss", public=True),
    "tide": gr_server.make_invite("Tide", kind="artist", handle="tide", public=True),
    "house": gr_server.make_invite("David", handle="the-room"),
    "a": gr_server.make_invite("Aoife"), "b": gr_server.make_invite("Brendan"),
    "c": gr_server.make_invite("Ciara"), "d": gr_server.make_invite("Dara"),
}
tok = {k: client.post("/api/join", json={"invite_code": v, "fingerprint": "mac-" + k}).get_json()["token"]
       for k, v in codes.items()}
for who, n in (("moss", 30), ("tide", 6), (None, 4)):
    folder = TMP / (who or "loose"); folder.mkdir()
    for i in range(n):
        tone(folder / f"{who or 'loose'} {i:02d}.wav")
    gr_server.add_folder(str(folder), owner=who)
with db() as conn:
    gr_shop.ensure(conn)
    conn.execute("UPDATE gr_accounts SET place_name='Galway', lat=53.27, lon=-9.05 WHERE handle='moss'")
    moss_ids = [r[0] for r in conn.execute("SELECT t.id FROM gr_tracks t JOIN gr_accounts a ON a.id=t.owner_account_id"
                                           " WHERE a.handle='moss' ORDER BY t.id")]
    tide_ids = [r[0] for r in conn.execute("SELECT t.id FROM gr_tracks t JOIN gr_accounts a ON a.id=t.owner_account_id"
                                           " WHERE a.handle='tide' ORDER BY t.id")]
    loose_ids = [r[0] for r in conn.execute("SELECT id FROM gr_tracks WHERE owner_account_id IS NULL ORDER BY id")]
    for n, tid in enumerate(moss_ids):                       # 10 House (1990–99), 10 Techno; House (2000–09), 10 Ambient (1994)
        genre, year = (("House", 1990 + n) if n < 10 else ("Techno; House", 1990 + n) if n < 20 else ("Ambient", 1994))
        conn.execute("UPDATE gr_tracks SET genre=?, year=?, label='Moss' WHERE id=?", (genre, year, tid))
    for n, tid in enumerate(tide_ids):
        conn.execute("UPDATE gr_tracks SET genre='Ambient', year=? WHERE id=?", (2019 + n, tid))
    conn.commit()
ALL = set(moss_ids + tide_ids + loose_ids)
chk(len(moss_ids) == 30 and len(tide_ids) == 6 and len(loose_ids) == 4, "the shelves hold 40 records")

# ─── what is printed on a record comes from its own tags ───
ff = gr_shop._ffmpeg()
if ff:
    tagged = TMP / "tagged"; tagged.mkdir()
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=1", "-metadata", "title=Printed",
                    "-metadata", "artist=Tagged Artist", "-metadata", "genre=House; Deep House", "-metadata", "date=1994-03-01",
                    "-metadata", "label=Warp", str(tagged / "printed.flac")], check=True)
    gr_server.add_folder(str(tagged), owner="tide")
    with db() as conn:
        row = conn.execute("SELECT * FROM gr_tracks WHERE title='Printed'").fetchone()
    chk(row and row["year"] == 1994 and row["label"] == "Warp" and gr_shop.genres_of(row["genre"]) == ["House", "Deep House"],
        "a new record's year, label and genres are read from its file")
    with db() as conn:                                          # (kept out of the counts below)
        conn.execute("DELETE FROM gr_tracks WHERE id=?", (row["id"],)); conn.commit()
else:
    print("  SKIP  no ffmpeg here: tag-reading and listening-copy checks are skipped")
chk(gr_shop.clean_year("released 2003") == 2003 and gr_shop.clean_year("soon") is None and gr_shop.clean_year(3020) is None,
    "a year is a year, or nothing")

# ─── the shop as someone finds it ───
chk(client.get("/api/shop").status_code == 401 and client.post("/api/shop/crates/pull", json={}).status_code == 401
    and client.post("/api/shop/blind/next").status_code == 401, "the shop needs a sign-in")
st = get(tok["a"], "/api/shop").get_json()
chk(st["left"] == {"crates": 3, "asks": 3, "answers": 3, "blind": gr_shop.BLIND_PER_DAY} and st["records"] == 40
    and st["limits"]["crate"] == 25, "a new day: three crates, three questions, three answers; 40 records to find")
chk(st["facets"]["genres"][:3] == ["House", "Ambient", "Techno"] and st["facets"]["places"] == ["Galway"]
    and st["facets"]["decades"] == [1990, 2000, 2010, 2020], "what can be asked for is only what the shelves hold")
chk(st["can_make"] is False and get(tok["moss"], "/api/shop").get_json()["can_make"] is True
    and get(tok["moss"], "/api/shop").get_json()["records"] == 10, "a label may make crates, and doesn't shop its own records")

# ─── a crate put together from the shelves ───
gr_shop.MADE_CHANCE = 0.0
r1 = post(tok["a"], "/api/shop/crates/pull")
p1 = r1.get_json()["pull"]
ids1 = [i["id"] for i in p1["items"]]
chk(r1.status_code == 200 and p1["kind"] == "mixed" and p1["title"] == "Anywhere" and p1["by"]["name"] == "The Music Room"
    and len(ids1) == 25 == len(set(ids1)) and set(ids1) <= ALL, "asked for anywhere: 25 different records off the shelves")
chk(r1.get_json()["left"]["crates"] == 2 and all(k in p1["items"][0] for k in ("title", "artist", "year", "genres", "price_cents", "owner", "place")),
    "it uses one of the day's three, and every record carries what is printed on it")
p2 = post(tok["a"], "/api/shop/crates/pull").get_json()["pull"]
ids2 = [i["id"] for i in p2["items"]]
chk(len(ids2) == 15 and not set(ids1) & set(ids2), "the second crate holds only what the first didn't")
r3 = post(tok["a"], "/api/shop/crates/pull")
chk(r3.status_code == 404 and r3.get_json().get("empty") and get(tok["a"], "/api/shop").get_json()["left"]["crates"] == 1,
    "with nothing new left, no crate is handed over and none is used up")
again = get(tok["a"], f"/api/shop/pulls/{p1['id']}").get_json()["pull"]
chk([i["id"] for i in again["items"]] == ids1 and again["open"], "a crate handed over stays as it was, in the same order")
chk(get(tok["b"], f"/api/shop/pulls/{p1['id']}").status_code == 404, "nobody else can open it")
chk([p["id"] for p in get(tok["a"], "/api/shop").get_json()["pulls"]] == [p1["id"], p2["id"]], "today's crates are listed")

# ─── asking for something ───
h = post(tok["b"], "/api/shop/crates/pull", {"genres": ["house"]}).get_json()["pull"]
chk(h["title"] == "house" and len(h["items"]) == 20 and all("House" in i["genres"] for i in h["items"]),
    "asked for a genre: every record in the crate is one (20 of them)")
y = post(tok["b"], "/api/shop/crates/pull", {"from": 2024, "to": 2019}).get_json()["pull"]
chk(y["title"] == "2019–2024" and sorted(i["id"] for i in y["items"]) == tide_ids, "asked for a span of years (either way round)")
g = post(tok["b"], "/api/shop/crates/pull", {"place": "galway", "genres": ["Ambient"]}).get_json()["pull"]
chk(g["title"] == "Ambient · galway" and sorted(i["id"] for i in g["items"]) == moss_ids[20:] and g["items"][0]["place"] == "Galway",
    "asked for a place and a genre together")
r = post(tok["b"], "/api/shop/crates/pull")
chk(r.status_code == 403 and r.get_json().get("limit"), "a fourth crate in a day is refused")
r = post(tok["c"], "/api/shop/crates/pull", {"genres": ["Gabber"]})
chk(r.status_code == 404 and r.get_json().get("empty") and get(tok["c"], "/api/shop").get_json()["left"]["crates"] == 3,
    "asking for what the shop doesn't hold hands over nothing and uses nothing up")
chk(gr_shop.clean_ask({"genres": "House", "place": 5, "from": "x"}) == {"genres": [], "place": "5", "from": None, "to": None}
    and gr_shop.ask_words(gr_shop.clean_ask({"from": 1999})) == "from 1999", "an odd ask is tidied, not trusted")

# ─── listening: only from inside a crate handed over today, and only the listening copy ───
if ff:
    r = get(tok["a"], f"/api/shop/listen/{ids1[0]}?pull={p1['id']}")
    chk(r.status_code == 200 and r.mimetype == "audio/mpeg" and r.data[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xfa"),
        "a record in my crate plays, as an MP3")
    copy = gr_shop.listen_dir() / f"{ids1[0]}.mp3"
    import mutagen
    tags = mutagen.File(str(copy), easy=True).tags
    chk(copy.exists() and not (tags or {}).get("title"), "what plays is the shop's listening copy, with no name written in it")
    # one play (David, 2026-11-20): the whole record, once; asked again — even for a piece of it — it is refused
    r = client.get(f"/api/shop/listen/{ids1[0]}?pull={p1['id']}", headers=dict(hdr(tok["a"]), Range="bytes=10-19"))
    chk(r.status_code == 403 and r.get_json().get("heard") and "borrow" in r.get_json()["error"],
        "a record plays once: asked for again, even a piece of it, it is refused, with the way to hear it again")
    pulled = get(tok["a"], f"/api/shop/pulls/{p1['id']}").get_json()["pull"]["items"]
    chk(next(i for i in pulled if i["id"] == ids1[0])["heard"] and not next(i for i in pulled if i["id"] == ids1[1])["heard"],
        "the crate says which of its records you have heard")
    with db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM gr_heard WHERE track_id=?", (ids1[0],)).fetchone()[0]
    chk(n == 1, "heard is kept for that person and that record only")
    chk(gr_shop.make_listen_copies()["could_not"] == 0, "every record's listening copy can be made ahead of time")
chk(get(tok["a"], f"/api/shop/listen/{ids2[0]}?pull={p1['id']}").status_code == 403, "a record that isn't in that crate does not play")
chk(get(tok["b"], f"/api/shop/listen/{ids1[0]}?pull={p1['id']}").status_code == 403, "nor does my crate play for someone else")
chk(get(tok["a"], f"/api/shop/listen/{ids1[0]}").status_code == 403, "nor does anything play from outside a crate")
real_today = gr_shop._today
gr_shop._today = lambda: "2099-01-01"
chk(get(tok["a"], f"/api/shop/pulls/{p1['id']}").status_code == 410
    and get(tok["a"], f"/api/shop/listen/{ids1[0]}?pull={p1['id']}").status_code == 403
    and get(tok["a"], "/api/shop").get_json()["left"]["crates"] == 3 and get(tok["a"], "/api/shop").get_json()["pulls"] == [],
    "the next day yesterday's crates are closed, silent and gone, and there are three new ones to pull")
gr_shop._today = real_today

# ─── what is yours already is not in the shop for you ───
bought = moss_ids[0]
post(tok["c"], "/api/buy", {"track_id": bought})
c1 = post(tok["c"], "/api/shop/crates/pull").get_json()["pull"]
c2 = post(tok["c"], "/api/shop/crates/pull").get_json()["pull"]
got = [i["id"] for i in c1["items"] + c2["items"]]
chk(len(got) == 39 and bought not in got, "a record you bought is never in a crate again")
m = post(tok["moss"], "/api/shop/crates/pull").get_json()["pull"]
chk(len(m["items"]) == 10 and not set(i["id"] for i in m["items"]) & set(moss_ids), "a label is never handed its own records")

# ─── crates somebody made ───
chk(post(tok["a"], "/api/my/crates", {"name": "Mine"}).status_code == 403, "someone who sells nothing can't make a crate")
chk(post(tok["tide"], "/api/my/crates", {"name": "  "}).status_code == 400, "a crate needs a name")
chk(post(tok["tide"], "/api/my/crates", {"name": "Too many", "items": [{"id": i} for i in list(ALL)[:26]]}).status_code == 400,
    "26 records don't fit")
chk(post(tok["tide"], "/api/my/crates", {"name": "Empty", "is_out": True}).status_code == 400, "an empty crate can't go out")
picks = [{"id": tide_ids[0], "note": "the first one I made"}, {"id": moss_ids[5]}, {"id": tide_ids[1], "note": "for the morning"},
         {"id": 99999}, {"id": tide_ids[0]}, {"id": moss_ids[6], "note": "x" * 400}]
crate = post(tok["tide"], "/api/my/crates", {"name": "Low tide", "note": "slow ones", "items": picks}).get_json()["crate"]
chk([i["id"] for i in crate["items"]] == [tide_ids[0], moss_ids[5], tide_ids[1], moss_ids[6]] and crate["items"][0]["note"] == "the first one I made"
    and len(crate["items"][3]["note"]) == 280 and crate["is_out"] is False,
    "a crate keeps its maker's order and notes; a record twice or one that doesn't exist is left out")
gr_shop.MADE_CHANCE = 1.0
d1 = post(tok["d"], "/api/shop/crates/pull").get_json()["pull"]
chk(d1["kind"] == "mixed", "a crate that isn't out is never handed to anyone")
crate = post(tok["tide"], "/api/my/crates", dict(id=crate["id"], name="Low tide", note="slow ones", is_out=True,
                                                   items=[{"id": tide_ids[2], "note": "newest"}] + picks[:3])).get_json()["crate"]
chk(crate["is_out"] and [i["id"] for i in crate["items"]] == [tide_ids[2], tide_ids[0], moss_ids[5], tide_ids[1]], "saved whole again, and put out")
chk(get(tok["tide"], "/api/my/crates").get_json()["crates"][0]["id"] == crate["id"]
    and [c["name"] for c in get(tok["moss"], "/api/shop/crates/out").get_json()["crates"]] == ["Low tide"]
    and get(tok["a"], "/api/shop/crates/out").status_code == 403, "its maker sees it; other sellers can pull from it")

# David's own account signs as the Music Room
gr_shop.set_house("the-room")
hc = post(tok["house"], "/api/my/crates", {"name": "This week", "is_out": True, "items": [{"id": loose_ids[0], "note": "start here"}, {"id": loose_ids[1]}]})
chk(hc.status_code == 200, "the Music Room's own account can make crates")
with db() as conn:
    conn.execute("DELETE FROM gr_crate_pulls WHERE account_id=(SELECT id FROM gr_accounts WHERE name='Dara')"); conn.commit()
seen_kinds = {}
for _ in range(3):
    p = post(tok["d"], "/api/shop/crates/pull").get_json()["pull"]
    seen_kinds[p["title"]] = p
low, week = seen_kinds.get("Low tide"), seen_kinds.get("This week")
chk(low and low["kind"] == "made" and low["by"] == {"name": "Tide", "handle": "tide"} and low["note"] == "slow ones"
    and [i["id"] for i in low["items"]] == [tide_ids[2], tide_ids[0], moss_ids[5], tide_ids[1]] and low["items"][0]["note"] == "newest",
    "a made crate comes back whole: its name, its maker, their order, their notes")
chk(week and week["by"]["name"] == "The Music Room" and week["items"][0]["note"] == "start here", "the Music Room's crate is signed The Music Room")
chk(len(seen_kinds) == 3 and "Anywhere" in seen_kinds, "the same made crate is not handed to the same person twice; then the shelves")
t1 = post(tok["tide"], "/api/shop/crates/pull").get_json()["pull"]
chk(t1["title"] != "Low tide", "a maker is never handed their own crate")

# asked for something: a made crate only comes back if at least half of it fits
with db() as conn:
    conn.execute("DELETE FROM gr_crate_pulls"); conn.commit()
p = post(tok["a"], "/api/shop/crates/pull", {"genres": ["Techno"]}).get_json()["pull"]
chk(p["kind"] == "mixed" and len(p["items"]) == 10, "asked for techno, a crate of ambient is not handed over")
p = post(tok["a"], "/api/shop/crates/pull", {"genres": ["Ambient"]}).get_json()["pull"]
chk(p["kind"] == "made" and p["title"] == "Low tide", "asked for ambient, the ambient crate is")

# a crate put together from the shelves is made of other crates where they hold the same records
gr_shop.MADE_CHANCE = 0.0
p = post(tok["b"], "/api/shop/crates/pull", {"from": 2019, "to": 2024}).get_json()["pull"]
by_id = {i["id"]: i for i in p["items"]}
chk(by_id[tide_ids[0]].get("from") == {"crate": "Low tide", "by": "Tide"} and by_id[tide_ids[0]]["note"] == "the first one I made"
    and "from" not in by_id[tide_ids[4]] and p["sources"] == [{"crate": "Low tide", "by": "Tide"}],
    "a record that sits in someone's crate keeps their note and says whose crate it is from")
chk(client.delete(f"/api/my/crates/{crate['id']}", headers=hdr(tok["a"])).status_code == 404
    and client.delete(f"/api/my/crates/{crate['id']}", headers=hdr(tok["tide"])).status_code == 200
    and get(tok["tide"], "/api/my/crates").get_json()["crates"] == [], "only its maker can take a crate away")

# finding a record by its words
found = get(tok["tide"], "/api/shop/search?q=moss+techno").get_json()["records"]
chk(len(found) == 10 and all("Techno" in r["genres"] for r in found) and len(get(tok["tide"], "/api/shop/search?q=").get_json()["records"]) == 40,
    "records are found by words in any order (genre, label, who sells them…)")

# ─── the counter ───
chk(post(tok["a"], "/api/shop/counter/ask", {"text": "hi"}).status_code == 400, "a question needs a few words")
qs = [post(tok["a"], "/api/shop/counter/ask", {"text": f"something slow for a night train {n}"}).get_json()["question"]["id"] for n in (1, 2, 3)]
r = post(tok["a"], "/api/shop/counter/ask", {"text": "and a fourth"})
chk(r.status_code == 403 and r.get_json().get("limit"), "a fourth question in a day is refused")
chk(post(tok["a"], "/api/shop/counter/take").get_json().get("none") is True, "nobody is handed their own question")
t = post(tok["b"], "/api/shop/counter/take").get_json()["question"]
chk(t["id"] == qs[0] and t["asker"]["name"] == "Aoife" and t["text"].endswith("1"), "the oldest open question is handed over, with who asked")
chk(post(tok["b"], "/api/shop/counter/take").get_json()["question"]["id"] == qs[0], "asking again gives the one already in hand")
chk(post(tok["c"], "/api/shop/counter/take").get_json()["question"]["id"] == qs[1], "someone else is handed the next one, not the one in hand")
chk(post(tok["d"], f"/api/shop/counter/{qs[0]}/answer", {"track_id": tide_ids[0], "text": "trust me"}).status_code == 409,
    "a question in someone's hand can't be answered by another")
post(tok["b"], f"/api/shop/counter/{qs[0]}/skip")
chk(post(tok["b"], "/api/shop/counter/take").get_json()["question"]["id"] == qs[2], "skipped, it never comes back to that person")
chk(post(tok["d"], "/api/shop/counter/take").get_json()["question"]["id"] == qs[0], "…and is free for the next person")
chk(post(tok["b"], f"/api/shop/counter/{qs[2]}/answer", {"track_id": tide_ids[3]}).status_code == 400
    and post(tok["b"], f"/api/shop/counter/{qs[2]}/answer", {"track_id": 99999, "text": "this one"}).status_code == 404
    and post(tok["b"], f"/api/shop/counter/{qs[2]}/answer", {"text": "this one"}).status_code == 400,
    "an answer is one record from the shop and a line of why")
chk(get(tok["a"], "/api/shop/news").get_json() == {"answers": 0}, "no news yet")
r = post(tok["b"], f"/api/shop/counter/{qs[2]}/answer", {"track_id": tide_ids[3], "text": "it sounds like rain on a window"})
chk(r.status_code == 200 and r.get_json()["left"]["answers"] == 2, "answered: one of the day's three answers used")
chk(post(tok["d"], f"/api/shop/counter/{qs[2]}/answer", {"track_id": tide_ids[4], "text": "or this"}).status_code == 409,
    "a question only ever gets one answer")
chk(get(tok["a"], "/api/shop/news").get_json() == {"answers": 1} and get(tok["a"], "/api/shop").get_json()["counter"] == {"waiting": 2, "new": 1, "open": 0},
    "the asker is told")
mine = get(tok["a"], "/api/shop/counter/mine").get_json()["questions"]
ans = next(q for q in mine if q["id"] == qs[2])["answer"]
chk(ans["by"]["name"] == "Brendan" and ans["text"].startswith("it sounds like rain") and ans["record"]["id"] == tide_ids[3]
    and ans["can_listen"] and not ans["seen"] and [q["answered"] for q in mine] == [True, False, False],
    "the answer is the record, the line of why and who gave it")
if ff:
    chk(get(tok["a"], f"/api/shop/listen/{tide_ids[3]}?q={qs[2]}").status_code == 200
        and get(tok["b"], f"/api/shop/listen/{tide_ids[3]}?q={qs[2]}").status_code == 403
        and get(tok["a"], f"/api/shop/listen/{tide_ids[4]}?q={qs[2]}").status_code == 403, "the asker, and only the asker, can hear the answer")
post(tok["a"], f"/api/shop/counter/{qs[2]}/seen")
chk(get(tok["a"], "/api/shop/news").get_json() == {"answers": 0}, "looked at, it is no longer news")
chk(post(tok["a"], f"/api/shop/counter/{qs[2]}/settle", {"choice": "maybe"}).status_code == 400
    and post(tok["a"], f"/api/shop/counter/{qs[2]}/settle", {"choice": "note"}).get_json() == {"settled": "note"}
    and get(tok["a"], f"/api/shop/listen/{tide_ids[3]}?q={qs[2]}").status_code == 403, "once the asker has decided, it stops playing")
chk(client.delete(f"/api/shop/counter/{qs[2]}", headers=hdr(tok["a"])).status_code == 409
    and client.delete(f"/api/shop/counter/{qs[1]}", headers=hdr(tok["b"])).status_code == 409
    and client.delete(f"/api/shop/counter/{qs[1]}", headers=hdr(tok["a"])).status_code == 200, "an unanswered question can be taken back, by its asker only")
# an answer can't be a record the asker has, or sells
for n in (1, 2, 3):
    post(tok["c"], "/api/shop/counter/ask", {"text": f"what should I hear next {n}"})
post(tok["moss"], "/api/shop/counter/ask", {"text": "something not on my own label"})
with db() as conn:
    cq = [r[0] for r in conn.execute("SELECT id FROM gr_counter WHERE asker_id=(SELECT id FROM gr_accounts WHERE name='Ciara') ORDER BY id")]
    mq = conn.execute("SELECT id FROM gr_counter WHERE asker_id=(SELECT id FROM gr_accounts WHERE handle='moss')").fetchone()[0]
chk(post(tok["a"], f"/api/shop/counter/{cq[0]}/answer", {"track_id": bought, "text": "a classic"}).status_code == 409,
    "an answer can't be a record the asker already bought")
chk(post(tok["a"], f"/api/shop/counter/{mq}/answer", {"track_id": moss_ids[3], "text": "your own best one"}).status_code == 409,
    "…nor one of the asker's own records")
# three answers a day
with db() as conn:
    conn.execute("UPDATE gr_counter SET held_by=NULL, held_until=NULL"); conn.commit()
for q in (cq[0], cq[1]):
    post(tok["b"], f"/api/shop/counter/{q}/answer", {"track_id": tide_ids[5], "text": "play it loud"})
r = post(tok["b"], f"/api/shop/counter/{cq[2]}/answer", {"track_id": tide_ids[5], "text": "play it loud"})
chk(r.status_code == 403 and r.get_json().get("limit") and post(tok["b"], "/api/shop/counter/take").status_code == 403,
    "a fourth answer in a day is refused")
# a question someone was handed and left comes free again
with db() as conn:
    conn.execute("UPDATE gr_counter SET held_by=(SELECT id FROM gr_accounts WHERE name='Brendan'), held_until='2000-01-01T00:00:00' WHERE id=?", (cq[2],)); conn.commit()
chk(post(tok["a"], "/api/shop/counter/take").get_json()["question"]["id"] in (qs[0], cq[2], mq), "a question left lying comes free again")

# ─── blind ───
gr_shop.BLIND_PER_DAY = 3
b1 = post(tok["a"], "/api/shop/blind/next").get_json()
chk(set(b1["blind"]) == {"id", "duration_s", "heard"} and not b1["blind"]["heard"] and b1["left"]["blind"] == 2,
    "a blind record arrives with no name, no cover and no number of its own — and is one you haven't heard")
with db() as conn:
    bt1 = conn.execute("SELECT track_id FROM gr_blind WHERE id=?", (b1["blind"]["id"],)).fetchone()[0]
    heard_a = {r[0] for r in conn.execute("SELECT track_id FROM gr_heard WHERE account_id=(SELECT id FROM gr_accounts WHERE name='Aoife')")}
chk(not heard_a or bt1 not in heard_a, "blind never hands you a record you have already heard")
chk(post(tok["a"], "/api/shop/blind/next").get_json()["blind"]["id"] == b1["blind"]["id"], "undecided, the same one comes back: nothing is used up")
if ff:
    r = get(tok["a"], f"/api/shop/blind/{b1['blind']['id']}/listen")
    chk(r.status_code == 200 and r.mimetype == "audio/mpeg" and get(tok["b"], f"/api/shop/blind/{b1['blind']['id']}/listen").status_code == 403,
        "it plays for the person it is in front of, and nobody else")
    r = get(tok["a"], f"/api/shop/blind/{b1['blind']['id']}/listen")
    chk(r.status_code == 403 and r.get_json().get("heard") and post(tok["a"], "/api/shop/blind/next").get_json()["blind"]["heard"],
        "blind plays once too; brought back undecided, it says it has been heard")
chk(post(tok["a"], f"/api/shop/blind/{b1['blind']['id']}/decide", {"choice": "keep"}).status_code == 400, "the choice is basket, note or pass")
d = post(tok["a"], f"/api/shop/blind/{b1['blind']['id']}/decide", {"choice": "pass"}).get_json()
chk(d["choice"] == "pass" and d["record"]["id"] in ALL and d["record"]["title"], "decided, it is turned over")
chk(post(tok["a"], f"/api/shop/blind/{b1['blind']['id']}/decide", {"choice": "basket"}).get_json()["choice"] == "pass", "the decision stands")
b2 = post(tok["a"], "/api/shop/blind/next").get_json()
with db() as conn:
    t2 = conn.execute("SELECT track_id FROM gr_blind WHERE id=?", (b2["blind"]["id"],)).fetchone()[0]
chk(b2["blind"]["id"] != b1["blind"]["id"] and t2 != d["record"]["id"], "the next one is another record")
chk(get(tok["a"], f"/api/shop/blind/{b1['blind']['id']}/listen").status_code == 403, "the last one has gone back on the shelf")
post(tok["a"], f"/api/shop/blind/{b2['blind']['id']}/decide", {"choice": "note"})
b3 = post(tok["a"], "/api/shop/blind/next").get_json()
post(tok["a"], f"/api/shop/blind/{b3['blind']['id']}/decide", {"choice": "basket"})
r = post(tok["a"], "/api/shop/blind/next")
chk(r.status_code == 403 and r.get_json().get("limit"), "the day's blind records run out")
with db() as conn:
    conn.execute("DELETE FROM gr_blind"); conn.commit()
gr_shop.BLIND_PER_DAY = 60
heard = set()
for _ in range(45):
    r = post(tok["moss"], "/api/shop/blind/next")
    if r.status_code != 200:
        break
    with db() as conn:
        heard.add(conn.execute("SELECT track_id FROM gr_blind WHERE id=?", (r.get_json()["blind"]["id"],)).fetchone()[0])
    post(tok["moss"], f"/api/shop/blind/{r.get_json()['blind']['id']}/decide", {"choice": "pass"})
chk(heard == set(tide_ids + loose_ids) and r.status_code == 404 and r.get_json().get("empty"),
    "blind never plays your own records, never the same one twice in a day, and says when the shop is used up")

# ─── a record's owner can say what is printed on it ───
client.post(f"/api/my/records/{tide_ids[0]}", json={"genre": "Dub; Ambient", "year": "1987", "label": "Tide Recordings"}, headers=hdr(tok["tide"]))
mine = {r["id"]: r for r in get(tok["tide"], "/api/my/records").get_json()["records"]}
cat = {t["id"]: t for t in get(tok["a"], "/api/catalogue").get_json()["tracks"]}
chk(mine[tide_ids[0]]["year"] == 1987 and mine[tide_ids[0]]["genre"] == "Dub; Ambient" and cat[tide_ids[0]]["label"] == "Tide Recordings",
    "year, genre and label can be set by the record's owner, and show in the catalogue")

# ─── a server that already had the shop gets the tables added since (gr_heard was once skipped) ───
with db() as conn:
    conn.execute("DROP TABLE gr_heard"); conn.commit()
    gr_shop.ensure(conn)
    chk(conn.execute("SELECT 1 FROM sqlite_master WHERE name='gr_heard'").fetchone() is not None,
        "a server that already had record shopping gets the one-play table when it starts")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
