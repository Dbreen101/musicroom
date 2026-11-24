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
SETTING = "plugins_on"          # {id: {"on": bool, "granted": [wants…], "source": "built-in"|"yours"}}


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
    out = []
    for p in discover(base_dir, data_dir):
        s = on.get(p["id"]) or {}
        is_on = bool(s.get("on")) and not p.get("error") and s.get("source") == p["source"] \
            and set(p.get("wants") or []) <= set(s.get("granted") or [])
        out.append({k: v for k, v in p.items() if k != "folder"} | {
            "on": is_on, "wants_said": [WANTS[w] for w in p.get("wants") or []],
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
