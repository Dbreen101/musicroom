"""Album covers — the sizes the room asks for, the laptop's own copies when the
drive that holds the covers is away, and the pass that makes those copies the
moment the drive comes back. Fresh database, a made-up "drive" folder, no
network, no sound. Run:  ./venv/bin/python test_covers.py"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_tmp = tempfile.TemporaryDirectory()
os.environ["MUSICROOM_DATA"] = _tmp.name            # a fresh data dir — Daithí's library stays out
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.pop("MR_GREEN_ROOM", None)

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import schema, migrate
schema.create_database(); migrate.run_migration()
import app as mr
from PIL import Image
import io, sqlite3
from mr_paths import DB_PATH

c = mr.app.test_client()
drive = Path(_tmp.name) / "drive"; drive.mkdir()
big = drive / "big.png"                               # a big cover that is not a JPEG
Image.effect_noise((2400, 2400), 60).convert("RGB").save(big, "PNG")
small = drive / "small.jpg"                           # a modest JPEG: kept byte for byte
Image.new("RGB", (600, 600), (200, 80, 40)).save(small, "JPEG", quality=95)
db = sqlite3.connect(DB_PATH)
db.execute("INSERT INTO tracks (id, title, artist_name, artwork_path) VALUES (1, 'Big', 'Someone', ?)", (str(big),))
db.execute("INSERT INTO tracks (id, title, artist_name, artwork_path) VALUES (2, 'Small', 'Someone', ?)", (str(small),))
db.commit(); db.close()

def size_of(resp):
    with Image.open(io.BytesIO(resp.data)) as im: return im.size
TH = Path(mr._THUMB_DIR)
mr._artwork_warm_state["last"] = time.time()   # no pass of its own yet: one racing the pass below left a size missing

# ── with the drive in: the sizes the room asks for ──
r = c.get("/api/artwork/1?s=300")
chk(r.status_code == 200 and max(size_of(r)) == 384, "a card that wants 300 gets the 384 size")
r = c.get("/api/artwork/1?s=900")
chk(r.status_code == 200 and max(size_of(r)) == 1280, "a big card (two or three across a sharp screen) gets 1280, not 768")
r = c.get("/api/artwork/1?s=5000")
chk(max(size_of(r)) == 1280, "anything bigger is capped at the largest size")
r = c.get("/api/artwork/2?s=900")
chk(max(size_of(r)) == 600, "a small cover is never blown up")
r = c.get("/api/artwork/1")
chk(r.status_code == 200 and size_of(r) == (2400, 2400), "no size asked = the original")

# ── the pass that keeps covers on the laptop ──
for p in TH.glob("*/*.jpg"): p.unlink()               # as on a laptop that never met the drive
st = mr._artwork_warm_state
st["last"] = time.time(); st["running"] = False       # the pass ran recently, found no drive, and is waiting out its ten minutes
real_listdir = os.listdir
vols = ["Macintosh HD"]
mr.os.listdir = lambda p: list(vols) if p == "/Volumes" else real_listdir(p)
try:
    c.get("/api/volumes/state")
    chk(not any(TH.glob("full/*.jpg")), "nothing is made while the wait is on")
    vols.append("EXTERNAL")                           # the drive appears
    s1 = c.get("/api/volumes/state").get_json()
    chk(st["last"] == 0.0, "a drive appearing ends the wait")
    c.get("/api/volumes/state")                       # the next request of any kind starts the pass
    end = time.time() + 20
    while time.time() < end and (st["running"] or st["done"] < 2): time.sleep(0.05)
    chk(st["done"] == 2 and st["total"] == 2 and not st["running"], "the pass makes copies of both covers and counts them")
    chk(all((TH / b / "1.jpg").is_file() for b in ("192", "384", "768", "full")), "each cover has its three small copies and a full-quality one")
    with Image.open(TH / "full" / "1.jpg") as im: full1 = im.size
    chk(full1 == (2000, 2000), "a huge cover's full copy is 2000 across")
    chk((TH / "full" / "2.jpg").read_bytes() == small.read_bytes(), "a modest JPEG's full copy is the very same bytes")
    chk("covers" not in c.get("/api/volumes/state").get_json(), "once done, the room is no longer told a pass is running")
    st["running"], st["done"], st["total"] = True, 1, 2
    chk(c.get("/api/volumes/state").get_json().get("covers") == {"done": 1, "total": 2}, "while it runs, the room hears how far along it is")
    st["running"] = False
finally:
    mr.os.listdir = real_listdir

# ── the drive goes away: the laptop's copies stand in ──
gone = Path(_tmp.name) / "drive-unplugged"; drive.rename(gone)
r = c.get("/api/artwork/1")
chk(r.status_code == 200 and size_of(r) == (2000, 2000), "drive away, no size asked: the full-quality copy")
r = c.get("/api/artwork/1?s=900")
chk(r.status_code == 200 and max(size_of(r)) == 2000, "drive away, a big card: the full copy stands in for the 1280 it never made")
r = c.get("/api/artwork/1?s=300")
chk(max(size_of(r)) == 384, "drive away, a small card: its own size")
(TH / "full" / "1.jpg").unlink(); (TH / "768" / "1.jpg").unlink()
r = c.get("/api/artwork/1?s=900")
chk(r.status_code == 200 and max(size_of(r)) == 384, "with only small copies left, the biggest of them is served (this is the blur Daithí saw)")
for b in ("192", "384"): (TH / b / "1.jpg").unlink()
chk(c.get("/api/artwork/1").status_code == 404, "no copy at all and no drive: nothing to show")

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: " + " | ".join(fails)))
sys.exit(1 if fails else 0)
