"""Names with fadas and other accents — addresses, searching, sorting.

Until 2026-11-21 an accented letter was thrown away with its accent wherever a name became an
address or was compared: Róisín Murphy's room was "r-is-n-murphy". These checks hold the fix:
the accent comes off, the letter stays, and a name typed without its accents still finds it."""
import os
import sys
import tempfile
from contextlib import closing
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["MR_GR_DB"] = str(Path(_tmp.name) / "gr_test.db")
os.environ["MR_LIBRARY_DB"] = str(Path(_tmp.name) / "no_library.db")

import mr_text
import gr_server

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# --- the letters themselves ---
for name, want in (("Daithí Breen", "daithi-breen"), ("Róisín Murphy", "roisin-murphy"), ("Seán Ó Briain", "sean-o-briain"),
                   ("Siobhán", "siobhan"), ("ÉABHA", "eabha"), ("Zoë", "zoe"), ("Björk", "bjork"), ("Søren Ødegård", "soren-odegard"),
                   ("Łukasz Żak", "lukasz-zak"), ("Straße", "strasse"), ("O'Brien & Sons", "o-brien-sons"), ("Plain Name", "plain-name")):
    chk(mr_text.slug(name) == want, f"{name} → {want}")
chk(mr_text.slug("мария") == "room" and mr_text.slug("") == "room" and mr_text.slug(None) == "room",
    "a name with no Latin letters has no address of its own — the stand-in is used")
chk(mr_text.words("мария") == "мария", "…but it still compares as itself (it is not flattened to nothing)")
chk(mr_text.words("Seán  Ó'Briain!") == "sean o briain" and mr_text.squeeze("Seán Ó Briain") == "seanobriain", "words and squeeze")
chk(mr_text.holds("Róisín Murphy — Overpowered", "roisin over") and mr_text.holds("Roisin Murphy", "RÓISÍN")
    and not mr_text.holds("Róisín Murphy", "roisin jones"), "a search holds whatever the accents, on either side")
chk(sorted(["Zebra", "Áine", "Órla", "Eoin", "Éabha", "aoife"], key=mr_text.fold) == ["Áine", "aoife", "Éabha", "Eoin", "Órla", "Zebra"],
    "names sort where a person would file them: Áine with the As, Órla with the Os")

# --- the rooms server: sign-up, the directory, the artist → room lookup ---
with closing(gr_server.db()) as conn:
    gr_server.init_db(conn)
client = gr_server.app.test_client()
def hdr(tok): return {"Authorization": f"Bearer {tok}"}
def signup(name, fp):
    return client.post("/api/signup", json={"name": name, "fingerprint": fp, "device_name": "laptop", "agreed": True})

r = signup("Róisín Murphy", "mac-1")
chk(r.status_code == 200, "Róisín Murphy signs up")
tok = r.get_json()["token"]
me = client.get("/api/me", headers=hdr(tok)).get_json()
chk(me["handle"] == "roisin-murphy" and me["name"] == "Róisín Murphy", "her room's address is roisin-murphy, and her name keeps its fadas")
r2 = signup("Róisín Murphy", "mac-2")
chk(client.get("/api/me", headers=hdr(r2.get_json()["token"])).get_json()["handle"] == "roisin-murphy-2", "a second Róisín Murphy gets roisin-murphy-2")
r3 = signup("Seán Ó Briain", "mac-3")
chk(client.get("/api/me", headers=hdr(r3.get_json()["token"])).get_json()["handle"] == "sean-o-briain", "Seán Ó Briain → sean-o-briain")

for name in ("Áine Ní Dhomhnaill", "Zebra Records", "Órla", "Eoin"):
    gr_server.make_invite(name, public=True)
with closing(gr_server.db()) as conn:
    conn.execute("UPDATE gr_accounts SET is_public=1"); conn.commit()
rooms = client.get("/api/rooms", headers=hdr(tok)).get_json()["rooms"]
names = [x["name"] for x in rooms]
chk(names.index("Áine Ní Dhomhnaill") < names.index("Eoin") < names.index("Órla") < names.index("Zebra Records"),
    "the directory files Áine before Eoin, and Órla before Zebra")
find = lambda q: [x["name"] for x in client.get("/api/rooms", query_string={"q": q}, headers=hdr(tok)).get_json()["rooms"]]
chk(sorted(find("roisin")) == ["Róisín Murphy", "Róisín Murphy"], "typing roisin finds both Róisíns")
chk(find("ORLA") == ["Órla"] and find("órla") == ["Órla"], "…with or without the fada, in capitals or not")
chk(find("ni dhomhnaill aine") == ["Áine Ní Dhomhnaill"], "…and by words in any order")
look = lambda n: client.get("/api/rooms/lookup", query_string={"name": n}, headers=hdr(tok)).get_json()["handle"]
chk(look("Órla") == "orla" and look("orla") == "orla" and look("ÓRLA") == "orla", "an artist's name leads to their room, capital Ó or none")
chk(look("Seán Ó Briain") == "sean-o-briain" and look("sean o briain") == "sean-o-briain", "…Seán Ó Briain too")
chk(look("Nobody Here") is None, "…and a name nobody has leads nowhere")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
