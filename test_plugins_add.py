"""Adding a plug-in from a folder, like dropping a device into Ableton (2026-11-27):
Explore → Plug-ins → Add a plug-in… copies a checked plug-in into the app's own
folder, "Look again" takes a fresh copy, "Remove" sends the app's copy to the
Trash — and a look laid over the app loads nothing from the internet.
A fresh data folder, no network, no sound, nothing really sent to the Trash.
Run:  ./venv/bin/python test_plugins_add.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.TemporaryDirectory()
TMP = Path(_tmp.name)
DATA = TMP / "app_data"
os.environ["MUSICROOM_DATA"] = str(DATA)
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["MR_GREEN_ROOM"] = "1"
os.environ["MUSICROOM_3D"] = "1"
os.environ.pop("MR_GR_SERVER", None)
DATA.mkdir()

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import plugins as P

SETTINGS = {}
get = lambda k, d="": SETTINGS.get(k, d)
def put(k, v): SETTINGS[k] = v
BIN = TMP / "bin"
BIN.mkdir()
binned = []
def trash(path):                       # a stand-in Trash: moves, never deletes
    binned.append(path)
    shutil.move(path, BIN / f"{len(binned)}-{Path(path).name}")
    return True, None
P._trash = trash                       # the routes use the module's own; never the real Trash here

def plugin(folder, pid="by-year", **more):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plugin.json").write_text(json.dumps(dict({"id": pid, "name": "By year", "wants": ["catalogue"],
                                                        "style": "style.css"}, **more)))
    (folder / "main.js").write_text("MusicRoom.say('one')")
    (folder / "style.css").write_text("h1{}")
    return folder

WS = TMP / "Music Room workshop"
src = plugin(WS / "plugins" / "by-year")
(src / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
(src / "sub").mkdir()
(src / "sub" / "more.js").write_text("")
(src / "README.md").write_text("notes")
(src / "notes.py").write_text("x")
(src / ".DS_Store").write_bytes(b"x")
(src / "big.js").write_bytes(b"x" * (P.MAX_FILE + 1))
os.symlink("/etc/hosts", src / "hosts.txt")
mine = P.mine_root(str(DATA))
dest = mine / "by-year"

# ── adding ──
out, why = P.add_from(ROOT, str(DATA), str(src), get, put)
chk(why is None and out["id"] == "by-year", f"a plug-in folder is added ({why})")
chk(all((dest / f).is_file() for f in ("plugin.json", "main.js", "style.css", "pic.png", "sub/more.js")),
    "its files are copied into the app's own plug-ins folder, folders inside it too")
chk(not any((dest / f).exists() for f in ("README.md", "notes.py", ".DS_Store", "big.js", "hosts.txt")),
    "nothing it can't use: no .md or .py, nothing hidden, nothing over 2 MB, no link to elsewhere")
chk(set(out["left_out"]) == {"README.md", "notes.py", "big.js", "hosts.txt"}, f"what was left out is said ({out['left_out']})")
chk((src / "notes.py").is_file() and (src / "main.js").is_file(), "the folder it came from is untouched")
found = {(p["id"], p["source"]): p for p in P.discover(ROOT, str(DATA))}
chk(("by-year", "yours") in found and not found[("by-year", "yours")].get("error"), "it is listed as one of your own and can run")
chk(P.links(get).get("by-year") == str(src.resolve()), "the app remembers where it came from")
lst = {p["id"]: p for p in P.listing(ROOT, str(DATA), get)}
chk(lst["by-year"]["added"] is True and lst["thread"]["added"] is False, "the list says which were added from a folder")
chk(not any(p.name.startswith(".adding") for p in mine.iterdir()), "no half-made copy is left behind")

# the folder above it, holding just the one, works too; two → choose
out2, why = P.add_from(ROOT, str(DATA), str(WS / "plugins"), get, put)
chk(why is None and out2["id"] == "by-year", "choosing the folder that holds it (and only it) works too")
plugin(WS / "plugins" / "second", "second")
_, why = P.add_from(ROOT, str(DATA), str(WS / "plugins"), get, put)
chk(why and "several" in why, f"a folder holding several says to choose one ({why})")
shutil.rmtree(WS / "plugins" / "second")

# the folder's own name doesn't matter; the copy is named by its id
odd = plugin(TMP / "Downloads" / "by-year-main (1)", "by-year-two")
out3, why = P.add_from(ROOT, str(DATA), str(odd), get, put)
chk(why is None and (mine / "by-year-two" / "main.js").is_file(), "a folder named anything is copied under its id")

# refused, and nothing written
for folder, said, what in [
    (TMP / "nothing-here", "isn't a folder", "a folder that isn't there"),
    (plugin(TMP / "t", "thread"), "comes with the app", "the name of a plug-in that comes with the app"),
    (plugin(TMP / "w", "greedy", wants=["accounts"]), "may only want", "asking for more than the four"),
    (plugin(TMP / "e", "noentry", entry="gone.js"), "gone.js", "an entry that isn't there"),
    (plugin(TMP / "s", "nostyle", style="gone.css"), "gone.css", "a style that isn't there"),
]:
    before = sorted(p.name for p in mine.iterdir())
    o, why = P.add_from(ROOT, str(DATA), str(folder), get, put)
    chk(o is None and said in (why or "") and sorted(p.name for p in mine.iterdir()) == before,
        f"refused, nothing written: {what} ({why})")
(TMP / "empty").mkdir()
_, why = P.add_from(ROOT, str(DATA), str(TMP / "empty"), get, put)
chk(why == "there is no plugin.json in that folder", "a folder with no plugin.json says so")
many = plugin(TMP / "many", "many")
for i in range(P.MAX_FILES + 1):
    (many / f"f{i}.js").write_text("")
o, why = P.add_from(ROOT, str(DATA), str(many), get, put)
chk(o is None and "more than" in why and not (mine / "many").exists(), "more than 200 files: refused")

# ── Look again ──
(src / "main.js").write_text("MusicRoom.say('two')")
notes = P.again(ROOT, str(DATA), get, put)
chk(not notes.get("by-year") and (dest / "main.js").read_text() == "MusicRoom.say('two')", "Look again takes a fresh copy")
(src / "sub" / "more.js").unlink()
P.again(ROOT, str(DATA), get, put)
chk(not (dest / "sub" / "more.js").exists(), "a file taken out of the folder goes from the copy too")
(src / "plugin.json").write_text("{ broken")
notes = P.again(ROOT, str(DATA), get, put)
chk("still runs" in notes.get("by-year", "") and (dest / "main.js").is_file(), "a broken folder: said, and the copy before stays")
(src / "plugin.json").write_text(json.dumps({"id": "by-year", "name": "By year", "style": "style.css", "wants": ["catalogue"]}))
shutil.move(str(odd), str(TMP / "moved"))
notes = P.again(ROOT, str(DATA), get, put)
chk("isn't there" in notes.get("by-year-two", "") and (mine / "by-year-two" / "main.js").is_file(),
    "a folder that is gone: said, and the copy before stays")
shutil.move(str(TMP / "moved"), str(odd))
pj = json.loads((odd / "plugin.json").read_text()); pj["id"] = "by-decade"
(odd / "plugin.json").write_text(json.dumps(pj))
P.again(ROOT, str(DATA), get, put)
chk((mine / "by-decade").is_dir() and not (mine / "by-year-two").exists()
    and "by-year-two" not in P.links(get) and "by-decade" in P.links(get), "its id changed: the old copy goes, the new one comes")

# ── a folder made in the app's folder by hand may be the only copy: it goes to the Trash, never deleted ──
plugin(mine / "handmade", "handmade")
(mine / "handmade" / "only-copy.js").write_text("mine")
binned.clear()
o, why = P.add_from(ROOT, str(DATA), str(plugin(TMP / "newer", "handmade")), get, put)
chk(why is None and len(binned) == 1 and any((p / "only-copy.js").is_file() for p in BIN.iterdir()),
    "replacing a folder made by hand sends it to the Trash first")
plugin(mine / "keepme", "keepme")
P._trash = lambda p: (False, "no Trash here")
o, why = P.add_from(ROOT, str(DATA), str(plugin(TMP / "k2", "keepme")), get, put)
chk(o is None and "Trash" in why and (mine / "keepme" / "main.js").is_file()
    and not any(p.name.startswith(".adding") for p in mine.iterdir()), "if the Trash can't take it: refused, the folder untouched")
P._trash = trash
# while a folder of the app's own is chosen (Show the folder → itself): nothing is copied
o, why = P.add_from(ROOT, str(DATA), str(mine / "keepme"), get, put)
chk(why is None and (mine / "keepme" / "main.js").is_file(), "choosing the app's own copy itself changes nothing")

# ── Remove ──
put(P.SETTING, json.dumps({"by-year": {"on": True, "granted": ["catalogue"], "source": "yours"}}))
binned.clear()
ok, why = P.remove(ROOT, str(DATA), "by-year", get, put)
chk(ok and binned and not dest.exists() and "by-year" not in P.links(get) and "by-year" not in P.state(get),
    "Remove: the app's copy to the Trash, forgotten, switched off")
chk((src / "main.js").is_file(), "…and the folder it was added from stays")
for bad in ("../app_data", "", ".hidden", "a/b", "thread"):
    ok, why = P.remove(ROOT, str(DATA), bad, get, put)
    chk(not ok, f"Remove refuses {bad!r} ({why})")
chk((ROOT / "plugins" / "thread" / "plugin.json").is_file(), "a plug-in that comes with the app is never removed")

# ── the routes ──
import schema, migrate
with contextlib.redirect_stdout(io.StringIO()):
    schema.create_database()
    migrate.run_migration()
    import app as mr
with mr.app.app_context():
    mr.set_setting("gr_token", "test-token")
c = mr.app.test_client()
for k in list(SETTINGS):
    SETTINGS.pop(k)
r = c.post("/api/plugins/folder/add", json={"folder": str(src)})
d = r.get_json()
chk(r.status_code == 200 and d["id"] == "by-year" and any(p["id"] == "by-year" and p["added"] for p in d["plugins"]),
    "POST /api/plugins/folder/add adds it and answers with the list")
r = c.post("/api/plugins/folder/add", json={"folder": str(src)}, headers={"Sec-Fetch-Site": "cross-site"})
chk(r.status_code == 403, "another web page can't add a plug-in")
r = c.post("/api/plugins/folder/add", json={"folder": str(TMP / "empty")})
chk(r.status_code == 400 and "plugin.json" in r.get_json()["error"], "a folder that isn't a plug-in: 400, in words")
(src / "main.js").write_text("MusicRoom.say('three')")
r = c.post("/api/plugins/folder/again", json={})
chk(r.status_code == 200 and r.get_json()["notes"] == {} and (dest / "main.js").read_text().endswith("'three')"),
    "POST /api/plugins/folder/again copies afresh")
r = c.post("/api/plugins/by-year/remove", json={})
chk(r.status_code == 200 and not dest.exists() and not any(p["id"] == "by-year" for p in r.get_json()["plugins"]),
    "POST /api/plugins/<id>/remove takes it out")
r = c.post("/api/plugins/nobody/remove", json={})
chk(r.status_code == 404, "removing one that isn't there: 404")

# ── your own look loads nothing from the internet ──
css = ("@import url(https://fonts.example.com/x.css); body{background:url('https://t.example.com/p.png') no-repeat}"
       " .a{background:url(//cdn.example.com/y.png)} .b{background:url(/api/gr/asset/12)}"
       " .c{background:url(data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'/>)}")
kept = mr._css_stays_here(css)
chk("example.com" not in kept and "@import url" not in kept, "your own look: no @import, no url() to another computer")
chk("url(/api/gr/asset/12)" in kept and "url(data:image/svg+xml" in kept, "…its own pictures and data: ones still work")
with mr.app.app_context():
    mr.set_setting("user_css", css)
with mr.app.test_request_context("/settings"):
    tag = mr._user_css_tag()
chk("example.com" not in tag and "/api/gr/asset/12" in tag, "the look laid over every page is the cleaned one")

print(f"\n{'ALL PASSED' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
