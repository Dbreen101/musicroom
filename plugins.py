"""
plugins.py — plug-ins for exploring and discovering music.

Daithí, 2026-11-20, opening the code to the Green Room's fellows: "They should be
able to build plug ins for music exploration and make their own algorithms for
music discovery. They should not be able to access other user data or the
servers that host the music artists are selling."

A plug-in is a folder:

    plugins/<id>/plugin.json     who it is and what it may read (below)
    plugins/<id>/main.js         its code (the "entry")
    plugins/<id>/style.css       its look (optional)
    plugins/<id>/…               any pictures it carries

    {
      "id": "thread",                     a-z, 0-9 and -, the folder's own name
      "name": "Thread",
      "version": "1.0.0",
      "author": "The Music Room",
      "description": "Pick a record; follow it by label, seller, genre or year.",
      "entry": "main.js",
      "style": "style.css",
      "wants": ["catalogue"]              what it may read: catalogue · rooms · grupai · library
    }

Where plug-ins come from
  · BUILT IN — the `plugins/` folder of the app's own code. These reach people
    only through a pull request Daithí has approved, then a release.
  · YOUR OWN — `<app data>/plugins/<id>/`. They run only in your own app, are
    marked "yours — not reviewed", and are how a plug-in is made and tried.
    "Add a plug-in…" copies one in from any folder (and "Look again" copies it
    afresh), so its maker never has to touch the app's own folders.

How a plug-in is kept in its box
  It runs in Explore → Plug-ins, inside a frame that is sandboxed (scripts only,
  no origin of its own) and served with a content rule that lets it load
  nothing but its own files, the app's fonts and record covers — it can't send
  anything anywhere (no fetch, no form, no frame). Whatever it may read, the
  page around it hands it (static/js/plugins_host.js), and only what its
  `wants` named and its user agreed to when switching it on:

    catalogue   the records for sale in the Music Room: only what is printed on
                them and who sells them (the rooms server's /api/plugins/catalogue)
    rooms       the public rooms: names, kinds, places, how many records
    grupai      the public grúpaí: names, who made them, how many things
    library     YOUR OWN records on this laptop: title, artist, album, year,
                genres, tags, BPM, key — nothing of anyone else's, and never a
                file or its path

  And it can ask for a few things, each one the person can see happen:
  make a crate of up to 25 records for sale (one of their three a day, signed
  with the plug-in's name), open a music room, show a short line.

The app's own guard (`_own_pages_only` in app.py) refuses anything the frame
might still try to send the app.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

WANTS = {
    "catalogue": "the records for sale in the Music Room (what is printed on them, who sells them)",
    "rooms": "the public music rooms (names, kinds, places)",
    "grupai": "the public grúpaí (names, who made them)",
    "library": "your own records on this laptop (titles, artists, years, genres, tags, BPM, key)",
}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
FILE_TYPES = {".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png",
              ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp",
              ".woff2": "font/woff2", ".txt": "text/plain"}
MAX_FILE = 2 * 1024 * 1024
MAX_FILES = 200                 # in one plug-in, when it is added
MAX_TOTAL = 20 * 1024 * 1024
SETTING = "plugins_on"          # {id: {"on": bool, "granted": [wants…], "source": "built-in"|"yours"}}
FROM = "plugins_from"           # {id: the folder it was added from} — "Look again" takes a fresh copy from there


def builtin_root(base_dir):
    return Path(base_dir) / "plugins"


def mine_root(data_dir):
    return Path(data_dir) / "plugins"


def clean_manifest(raw, folder_name):
    """A plugin.json → (manifest, None) or (None, why it can't be used)."""
    if not isinstance(raw, dict):
        return None, "plugin.json isn't an object"
    pid = str(raw.get("id") or "").strip()
    if not ID_RE.match(pid):
        return None, "its id must be a-z, 0-9 and -"
    if pid != folder_name:
        return None, f"its id ({pid}) must be its folder's name ({folder_name})"
    name = " ".join(str(raw.get("name") or "").split())[:60]
    if not name:
        return None, "it needs a name"
    entry = str(raw.get("entry") or "main.js").strip()
    if not _safe_rel(entry) or not entry.endswith(".js"):
        return None, "its entry must be a .js file inside its folder"
    style = str(raw.get("style") or "").strip()
    if style and (not _safe_rel(style) or not style.endswith(".css")):
        return None, "its style must be a .css file inside its folder"
    wants = raw.get("wants") or []
    if not isinstance(wants, list) or any(w not in WANTS for w in wants):
        return None, "it may only want: " + ", ".join(WANTS)
    return {
        "id": pid, "name": name,
        "version": " ".join(str(raw.get("version") or "").split())[:20],
        "author": " ".join(str(raw.get("author") or "").split())[:80],
        "description": " ".join(str(raw.get("description") or "").split())[:400],
        "entry": entry, "style": style, "wants": sorted(set(wants), key=list(WANTS).index),
    }, None


def _safe_rel(rel):
    """A path inside a plug-in's folder: no leading /, no .., no hidden parts."""
    if not rel or rel.startswith(("/", "\\")) or "\\" in rel:
        return False
    parts = rel.split("/")
    return all(p and p not in (".", "..") and not p.startswith(".") for p in parts)


def discover(base_dir, data_dir):
    """Every plug-in there is: built in first, then your own. A folder that
    can't be used is listed with why."""
    out = []
    for source, root in (("built-in", builtin_root(base_dir)), ("yours", mine_root(data_dir))):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            mf = d / "plugin.json"
            if not mf.is_file():
                continue
            try:
                raw = json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                out.append({"id": d.name, "name": d.name, "source": source, "error": "plugin.json can't be read"})
                continue
            m, why = clean_manifest(raw, d.name)
            if why:
                out.append({"id": d.name, "name": d.name, "source": source, "error": why})
                continue
            if not (d / m["entry"]).is_file():
                out.append(dict(m, source=source, error=f"{m['entry']} isn't in its folder"))
                continue
            if any(p["id"] == m["id"] and not p.get("error") for p in out):
                out.append(dict(m, source=source, error="a built-in plug-in already has this id"))
                continue
            out.append(dict(m, source=source, folder=str(d)))
    return out


def find(base_dir, data_dir, pid):
    for p in discover(base_dir, data_dir):
        if p["id"] == pid and not p.get("error"):
            return p
    return None


def file_path(plugin, rel):
    """A file of a plug-in's own, or None (never anything outside its folder)."""
    if not plugin or not _safe_rel(rel):
        return None
    ext = os.path.splitext(rel)[1].lower()
    if ext not in FILE_TYPES:
        return None
    root = Path(plugin["folder"]).resolve()
    p = (root / rel).resolve()
    if root not in p.parents or not p.is_file() or p.stat().st_size > MAX_FILE:
        return None
    return p


def frame_csp(origin, pid):
    """The content rule of a plug-in's frame: its own files, the app's fonts,
    record covers — and nothing that sends anything anywhere."""
    own = f"{origin}/plugins/files/{pid}/"
    return "; ".join([
        "default-src 'none'",
        f"script-src {origin}/static/js/plugin_runtime.js {own}",
        f"style-src 'unsafe-inline' {origin}/static/css/ {own}",
        f"img-src data: blob: {origin}/api/gr/art/ {origin}/api/artwork/ {own}",
        f"font-src {origin}/static/fonts/ {own}",
        "connect-src 'none'", "media-src 'none'", "frame-src 'none'", "worker-src 'none'",
        "form-action 'none'", "base-uri 'none'", "object-src 'none'",
        "sandbox allow-scripts",
    ])


def state(get_setting):
    try:
        v = json.loads(get_setting(SETTING, "") or "{}")
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def listing(base_dir, data_dir, get_setting):
    on = state(get_setting)
    added = links(get_setting)
    out = []
    for p in discover(base_dir, data_dir):
        s = on.get(p["id"]) or {}
        is_on = bool(s.get("on")) and not p.get("error") and s.get("source") == p["source"] \
            and set(p.get("wants") or []) <= set(s.get("granted") or [])
        out.append({k: v for k, v in p.items() if k != "folder"} | {
            "on": is_on, "wants_said": [WANTS[w] for w in p.get("wants") or []],
            "added": p["source"] == "yours" and p["id"] in added,
        })
    return out


def granted(base_dir, data_dir, get_setting, pid, what):
    """May this plug-in, switched on, read `what` now?"""
    p = find(base_dir, data_dir, pid)
    s = state(get_setting).get(pid) or {}
    return bool(p and s.get("on") and s.get("source") == p["source"] and what in (p.get("wants") or [])
                and what in (s.get("granted") or []))


def library_rows(query):
    """Your own records, as a plug-in may read them (never a file or a path)."""
    rows = query(
        "SELECT t.id, t.title, t.artist_name AS artist, t.album, t.year, t.art_colour,"
        " f.bpm, f.key_note, f.key_scale,"
        " (SELECT GROUP_CONCAT(g.name, '|') FROM track_genres tg JOIN genres g ON g.id = tg.genre_id WHERE tg.track_id = t.id) AS genres,"
        " (SELECT GROUP_CONCAT(x.name, '|') FROM track_tags tt JOIN tags x ON x.id = tt.tag_id WHERE tt.track_id = t.id) AS tags,"
        " CASE WHEN COALESCE(t.artwork_path, '') != '' THEN 1 ELSE 0 END AS has_cover"
        " FROM tracks t LEFT JOIN files f ON f.track_id = t.id AND f.is_primary = 1 AND f.is_deleted = 0"
        " WHERE t.is_deleted = 0 AND COALESCE(t.is_recording, 0) = 0 AND t.gr_borrow_id IS NULL"
        " GROUP BY t.id ORDER BY t.artist_name COLLATE NOCASE, t.title COLLATE NOCASE")
    out = []
    for r in rows:
        r = dict(r)
        out.append({
            "id": r["id"], "title": r.get("title") or "", "artist": r.get("artist") or "", "album": r.get("album") or "",
            "year": r.get("year"), "bpm": round(r["bpm"], 1) if r.get("bpm") else None,
            "key": " ".join(x for x in (r.get("key_note"), r.get("key_scale")) if x),
            "colour": r.get("art_colour") or "",
            "genres": [g for g in (r.get("genres") or "").split("|") if g],
            "tags": [g for g in (r.get("tags") or "").split("|") if g],
            "has_cover": bool(r.get("has_cover")),
        })
    return out


def show_folder(data_dir):
    root = mine_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "READ ME.txt"
    if not readme.exists():
        readme.write_text(
            "Your own plug-ins live here, one folder each.\n"
            "A plug-in is a folder with plugin.json, main.js and (if you like) style.css.\n"
            "How to make one: docs/PLUGINS.md in the Music Room's code.\n"
            "These run only in your own app. To share one with everyone, send it to the\n"
            "Music Room's GitHub as a pull request.\n", encoding="utf-8")
    try:
        import mr_os
        mr_os.open_target(str(root))
    except OSError:
        pass
    return str(root)


# ---------- adding a plug-in from a folder (like dropping a device into Ableton) ----------
#
# Daithí, 2026-11-27: "i would like the app to function like ableton … i only want people
# to be able to make plug ins or import code to change the look of their … music rooms."
# A person (or their Claude, in a folder of its own) makes a plug-in anywhere on their
# computer; Explore → Plug-ins → "Add a plug-in…" takes a COPY of it into the app's own
# plug-ins folder, after the same checks as above. The app remembers where it came from,
# and "Look again" takes a fresh copy, so nobody has to touch the app's folders at all.

def links(get_setting):
    try:
        v = json.loads(get_setting(FROM, "") or "{}")
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def _plugin_folder(folder):
    """The plug-in in a chosen folder: the folder itself, or the one plug-in folder inside it
    (a zip unpacked into a folder of its own, a workshop's plugins/ with one in it)."""
    f = Path(str(folder or "")).expanduser()
    if not str(folder or "").strip() or not f.is_dir():
        return None, "that isn't a folder"
    if (f / "plugin.json").is_file():
        return f, None
    inner = sorted(d for d in f.iterdir()
                   if d.is_dir() and not d.name.startswith(".") and (d / "plugin.json").is_file())
    if len(inner) == 1:
        return inner[0], None
    if inner:
        return None, "that folder holds several plug-ins: choose the one to add"
    return None, "there is no plugin.json in that folder"


def _files_to_copy(src):
    """([(rel, path)], [what was left out], None) or (None, None, why it can't be added).
    Only the kinds of file a plug-in's page can use, none hidden, none a link, none too big."""
    take, left, total = [], [], 0
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = p.relative_to(src).as_posix()
            if not _safe_rel(rel):
                continue                                  # hidden: .DS_Store, .git…
            if p.is_symlink() or not p.is_file():
                left.append(rel)
                continue
            if p.suffix.lower() not in FILE_TYPES:
                left.append(rel)
                continue
            size = p.stat().st_size
            if size > MAX_FILE:
                left.append(rel)
                continue
            take.append((rel, p))
            total += size
            if len(take) > MAX_FILES:
                return None, None, f"it has more than {MAX_FILES} files"
            if total > MAX_TOTAL:
                return None, None, "it is bigger than 20 MB"
    return take, left, None


def _trash(path):
    import trash_util
    return trash_util.move_to_trash(path)


def add_from(base_dir, data_dir, folder, get_setting, set_setting, trash=None):
    """Copy the plug-in in `folder` into your own plug-ins folder → ({id, name, left_out}, None)
    or (None, why not). The folder it came from is remembered for "Look again"."""
    src, why = _plugin_folder(folder)
    if why:
        return None, why
    try:
        raw = json.loads((src / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "its plugin.json can't be read"
    pid = str(raw.get("id") or "").strip() if isinstance(raw, dict) else ""
    m, why = clean_manifest(raw, pid)
    if why:
        return None, why
    if (builtin_root(base_dir) / pid).is_dir():
        return None, f"a plug-in that comes with the app is already called {pid}: give yours another id"
    take, left, why = _files_to_copy(src)
    if why:
        return None, why
    have = {rel for rel, _ in take}
    for need in (m["entry"], m["style"]):
        if need and need not in have:
            return None, f"{need} isn't in its folder"
    root = mine_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / pid
    known = links(get_setting)
    if dest.exists() and dest.resolve() == src.resolve():
        known.pop(pid, None)                              # it is already the app's own folder: nothing to copy
        set_setting(FROM, json.dumps(known))
        return {"id": pid, "name": m["name"], "left_out": left}, None
    tmp = root / f".adding-{pid}"
    if tmp.exists():
        shutil.rmtree(tmp)                                # a copy of ours that was cut short
    try:
        for rel, p in take:
            d = tmp / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
        if dest.exists():
            if pid in known:
                shutil.rmtree(dest)                       # the app's own copy of the same plug-in, added before
            else:
                # a folder made here by hand may be the only copy there is: to the Trash, never deleted
                ok, err = (trash or _trash)(str(dest))
                if not ok:
                    raise OSError(f"the {pid} already here couldn't be moved to the Trash ({err})")
        os.replace(tmp, dest)
    except OSError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, str(e) or "it couldn't be copied"
    known[pid] = str(src.resolve())
    set_setting(FROM, json.dumps(known))
    return {"id": pid, "name": m["name"], "left_out": left}, None


def again(base_dir, data_dir, get_setting, set_setting, trash=None):
    """"Look again": a fresh copy of every plug-in that was added from a folder.
    → {id: what went wrong} — a plug-in whose folder is gone or broken keeps the copy it had."""
    notes = {}
    for pid, path in list(links(get_setting).items()):
        if not Path(path).is_dir():
            notes[pid] = "the folder it was added from isn't there any more; the copy from before still runs"
            continue
        out, why = add_from(base_dir, data_dir, path, get_setting, set_setting, trash=trash)
        if why:
            notes[pid] = f"its folder has a problem ({why}); the copy from before still runs"
        elif out["id"] != pid:                            # its id was changed in its folder: the old copy goes
            known = links(get_setting)
            known.pop(pid, None)
            set_setting(FROM, json.dumps(known))
            old = mine_root(data_dir) / pid
            if old.is_dir():
                shutil.rmtree(old)
    return notes


def remove(base_dir, data_dir, pid, get_setting, set_setting, trash=None):
    """Take one of your own plug-ins out of the app: its folder there goes to the Trash
    (the folder it was added from stays where it is). → (True, None) or (False, why)."""
    # (a folder that can't run is listed by its own name, which may not be a good id: it can go too)
    if not pid or pid != Path(pid).name or pid.startswith(".") or "\\" in pid:
        return False, "no such plug-in"
    folder = mine_root(data_dir) / pid
    if not folder.is_dir():
        return False, "no such plug-in"
    ok, err = (trash or _trash)(str(folder))
    if not ok:
        return False, err or "it couldn't be moved to the Trash"
    known = links(get_setting)
    known.pop(pid, None)
    set_setting(FROM, json.dumps(known))
    on = state(get_setting)
    if on.pop(pid, None) is not None:
        set_setting(SETTING, json.dumps(on))
    return True, None


# ---------- routes ----------

def register(app, base_dir, data_dir, get_setting, set_setting, query, green_room, track=None):
    from html import escape

    from flask import Response, jsonify, request, send_file

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    @app.route("/api/plugins")
    def api_plugins():
        return jsonify({"plugins": listing(base_dir, data_dir, get_setting), "wants": WANTS,
                        "folder": str(mine_root(data_dir))})

    @app.route("/api/plugins/<pid>", methods=["POST"])
    def api_plugin_set(pid):
        """Switch a plug-in on (agreeing to what it may read) or off."""
        d = request.get_json(silent=True) or {}
        p = find(base_dir, data_dir, pid)
        if not p:
            return no("no such plug-in", 404)
        on = state(get_setting)
        if d.get("on"):
            on[pid] = {"on": True, "granted": list(p.get("wants") or []), "source": p["source"],
                       "version": p.get("version") or ""}
        else:
            on.pop(pid, None)
        set_setting(SETTING, json.dumps(on))
        if track:
            try:
                track("plugin_" + ("on" if d.get("on") else "off"), {"id": pid, "source": p["source"]})
            except Exception:
                pass
        return jsonify({"plugins": listing(base_dir, data_dir, get_setting)})

    @app.route("/api/plugins/folder/show", methods=["POST"])
    def api_plugins_folder():
        return jsonify({"folder": show_folder(data_dir)})

    def told(kind, data):
        if track:
            try:
                track(kind, data)
            except Exception:
                pass

    @app.route("/api/plugins/folder/add", methods=["POST"])
    def api_plugins_add():
        """Add a plug-in: the computer's own "choose a folder" window, then a copy of what
        is chosen (checked like any plug-in) into your own plug-ins folder."""
        d = request.get_json(silent=True) or {}
        folder = str(d.get("folder") or "").strip()
        if not folder:
            import mr_os
            folder, why = mr_os.choose("folder", start=str(d.get("start") or ""),
                                       prompt="Choose the plug-in's folder (the one with plugin.json in it)")
            if not folder:
                if why == "cancelled":
                    return jsonify({"cancelled": True, "plugins": listing(base_dir, data_dir, get_setting)})
                return no(why or "the window to choose a folder didn't open")
        out, why = add_from(base_dir, data_dir, folder, get_setting, set_setting)
        if why:
            return no(why)
        told("plugin_added", {"id": out["id"], "left_out": len(out["left_out"])})
        return jsonify(dict(out, plugins=listing(base_dir, data_dir, get_setting)))

    @app.route("/api/plugins/folder/again", methods=["POST"])
    def api_plugins_again():
        notes = again(base_dir, data_dir, get_setting, set_setting)
        return jsonify({"plugins": listing(base_dir, data_dir, get_setting), "notes": notes})

    @app.route("/api/plugins/<pid>/remove", methods=["POST"])
    def api_plugin_remove(pid):
        ok, why = remove(base_dir, data_dir, pid, get_setting, set_setting)
        if not ok:
            return no(why, 404 if why == "no such plug-in" else 400)
        told("plugin_removed", {"id": pid})
        return jsonify({"plugins": listing(base_dir, data_dir, get_setting)})

    @app.route("/plugins/frame/<pid>")
    def plugin_frame(pid):
        """A plug-in's page, in its box (see frame_csp)."""
        p = find(base_dir, data_dir, pid)
        if not p or not (state(get_setting).get(pid) or {}).get("on"):
            return Response("This plug-in isn't switched on.", 404, mimetype="text/plain")
        origin = request.host_url.rstrip("/")
        own = f"{origin}/plugins/files/{pid}/"
        page = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<meta name=\"mr-origin\" content=\"{escape(origin)}\"><meta name=\"mr-plugin\" content=\"{escape(pid)}\">"
            f"<title>{escape(p['name'])}</title>"
            f"<link rel=\"stylesheet\" href=\"{origin}/static/css/deck_fonts.css\">"
            f"<link rel=\"stylesheet\" href=\"{origin}/static/css/record_fonts.css\">"
            f"<link rel=\"stylesheet\" href=\"{origin}/static/css/plugin_base.css\">"
            + (f"<link rel=\"stylesheet\" href=\"{own}{escape(p['style'])}\">" if p.get("style") else "")
            + "</head><body><main id=\"app\"></main>"
            f"<script src=\"{origin}/static/js/plugin_runtime.js\"></script>"
            f"<script src=\"{own}{escape(p['entry'])}\"></script></body></html>")
        resp = Response(page, mimetype="text/html")
        resp.headers["Content-Security-Policy"] = frame_csp(origin, pid)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/plugins/files/<pid>/<path:rel>")
    def plugin_file(pid, rel):
        p = find(base_dir, data_dir, pid)
        path = file_path(p, rel)
        if not path:
            return Response("not found", 404, mimetype="text/plain")
        resp = send_file(str(path), mimetype=FILE_TYPES[path.suffix.lower()])
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/api/plugins/<pid>/data/<what>")
    def plugin_data(pid, what):
        """What a plug-in may read — asked by the page around it, never by the plug-in."""
        if what not in WANTS:
            return no("a plug-in can't read that", 404)
        if not granted(base_dir, data_dir, get_setting, pid, what):
            return no("this plug-in wasn't given that", 403)
        try:
            if what == "catalogue":
                code, d = green_room.shop_call("GET", "/api/plugins/catalogue")
                if code != 200:
                    return no(d.get("error") or "the shop can't be read right now", 502)
                return jsonify({"records": d.get("records") or []})
            if what == "rooms":
                rooms = green_room.rooms() or []
                keep = ("handle", "name", "kind", "bio", "track_count", "place")
                return jsonify({"rooms": [{k: r.get(k) for k in keep} for r in rooms]})
            if what == "grupai":
                code, d = green_room.shop_call("GET", "/api/grupai")
                if code != 200:
                    return no(d.get("error") or "the grúpaí can't be read right now", 502)
                keep = ("id", "name", "description", "count", "updated_at")
                return jsonify({"grupai": [dict({k: g.get(k) for k in keep},
                                                owner={"name": (g.get("owner") or {}).get("name"),
                                                       "handle": (g.get("owner") or {}).get("handle")})
                                           for g in d.get("grupai") or []]})
            if what == "library":
                return jsonify({"records": library_rows(query)})
        except green_room.GRError as e:
            return no(str(e), 502)
        return no("nothing", 404)

    @app.route("/api/plugins/<pid>/crate", methods=["POST"])
    def plugin_crate(pid):
        """A plug-in hands its person a crate (one of their three today)."""
        p = find(base_dir, data_dir, pid)
        if not p or not granted(base_dir, data_dir, get_setting, pid, "catalogue"):
            return no("this plug-in can't make crates", 403)
        d = request.get_json(silent=True) or {}
        ids = [i for i in (d.get("ids") or []) if isinstance(i, int)][:200]
        try:
            code, out = green_room.shop_call("POST", "/api/shop/crates/pull",
                                             {"pick": {"ids": ids, "by": p["name"], "title": str(d.get("title") or "")[:80]}})
        except green_room.GRError as e:
            return no(str(e), 502)
        return jsonify(out), code
