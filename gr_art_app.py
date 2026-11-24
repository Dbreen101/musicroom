"""
gr_art_app.py — the app's side of digital artists (gr_art.py on the rooms
server; 2026-11-24).

    /api/gr/works/mine              the artist's own works, work line, credits asked of them
    /api/gr/works/mine  (POST)      a new work (the picture goes straight through)
    /api/gr/works/mine/<id>         change its words or price · DELETE takes it out
    /api/gr/works/profile           open to work, what I do, how to reach me
    /api/gr/works/credits/<id>      yes / no to "the artwork of this record is by you"
    /api/gr/my/records/art-by       a record's owner: the credits on my records
    /api/gr/my/records/<id>/art-by  …name the digital artist (or take the name off)
    /api/gr/works/<id>              one work, as this person sees it
    /api/gr/works/<id>/buy          buy it with credits
    /api/gr/works/<id>/save         put the bought file on this computer and show it
    /api/gr/works/bought            what this person has bought
    /api/gr/work-img/<id>?size=     a work's picture (view | thumb), kept on this laptop once seen
"""

import mimetypes
import os
from contextlib import closing
from pathlib import Path

import requests
from flask import Response, jsonify, request

import green_room
import mr_os

_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def _call(method, path, payload=None, params=None):
    try:
        code, d = green_room.shop_call(method, path, payload, params)
    except green_room.GRError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(d), code


def _img_cache():
    return green_room.GR_DIR / "works"


def work_img(wid, size):
    """→ (bytes, mime) of a work's picture; kept on this laptop after the first look."""
    size = "thumb" if size == "thumb" else "view"
    cache = _img_cache()
    hit = next(iter(cache.glob(f"{int(wid)}_{size}.*")), None) if cache.exists() else None
    if hit:
        return hit.read_bytes(), mimetypes.guess_type(hit.name)[0] or "image/jpeg"
    with closing(green_room._db()) as conn:
        url = green_room._server_url(conn)
    if not url:
        return None, None
    try:
        r = requests.get(url + f"/api/works/{int(wid)}/img", params={"size": size}, timeout=30)
    except requests.RequestException:
        return None, None
    if r.status_code != 200:
        return None, None
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{int(wid)}_{size}{_EXT.get(mime, '.jpg')}").write_bytes(r.content)
    return r.content, mime


def save_file(wid):
    """Fetch a bought work's file and keep it on this computer. → the path."""
    code, info = green_room.shop_call("GET", f"/api/works/{int(wid)}")
    if code != 200:
        raise green_room.GRError(info.get("error") or "that work can't be found")
    with closing(green_room._db()) as conn:
        r = green_room._get(conn, f"/api/works/{int(wid)}/file", timeout=300)
        if r.status_code != 200:
            raise green_room.GRError(green_room._err_of(r, "the file couldn't be fetched"))
        folder = green_room._purchase_dir(conn) / "Art"
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    by = green_room._safe_name((info.get("by") or {}).get("name"), "artist")
    name = green_room._safe_name(f"{by} - {info.get('title') or 'work'}", f"work-{int(wid)}") + _EXT.get(mime, ".jpg")
    folder.mkdir(parents=True, exist_ok=True)
    dest = green_room._inside(folder, name)
    dest.write_bytes(r.content)
    return str(dest)


def register(app):

    @app.route("/api/gr/works/mine")
    def api_gr_works_mine():
        return _call("GET", "/api/my/works")

    @app.route("/api/gr/works/mine", methods=["POST"])
    def api_gr_works_add():
        f = request.files.get("image")
        if not f:
            return jsonify({"error": "choose a picture"}), 400
        data = f.read()
        fields = {k: request.form.get(k) or "" for k in ("title", "year", "medium", "note", "url", "price", "rights")}
        try:
            with closing(green_room._db()) as conn:
                r = green_room._post_files(conn, "/api/my/works", {"image": (f.filename or "work", data, f.mimetype or "image/jpeg")}, fields)
            try:
                out = r.json()
            except ValueError:
                out = {"error": "the work wasn't accepted"}
            if r.status_code == 200:
                green_room.track("work_add", {"work": out.get("id")})
            return jsonify(out), r.status_code
        except green_room.GRError as e:
            return jsonify({"error": str(e)}), 502

    @app.route("/api/gr/works/mine/<int:wid>", methods=["POST", "DELETE"])
    def api_gr_works_edit(wid):
        if request.method == "DELETE":
            return _call("DELETE", f"/api/my/works/{wid}")
        return _call("POST", f"/api/my/works/{wid}", request.get_json(silent=True) or {})

    @app.route("/api/gr/works/profile", methods=["POST"])
    def api_gr_works_profile():
        return _call("POST", "/api/my/works/profile", request.get_json(silent=True) or {})

    @app.route("/api/gr/works/credits/<int:cid>", methods=["POST"])
    def api_gr_works_credit(cid):
        return _call("POST", f"/api/my/works/credits/{cid}", request.get_json(silent=True) or {})

    @app.route("/api/gr/my/records/art-by")
    def api_gr_records_art_by():
        return _call("GET", "/api/my/records/art-by")

    @app.route("/api/gr/my/records/<int:tid>/art-by", methods=["POST"])
    def api_gr_record_art_by(tid):
        return _call("POST", f"/api/my/records/{tid}/art-by", request.get_json(silent=True) or {})

    @app.route("/api/gr/works/bought")
    def api_gr_works_bought():
        return _call("GET", "/api/works/bought")

    @app.route("/api/gr/works/<int:wid>")
    def api_gr_work(wid):
        return _call("GET", f"/api/works/{wid}")

    @app.route("/api/gr/works/<int:wid>/buy", methods=["POST"])
    def api_gr_work_buy(wid):
        out = _call("POST", f"/api/works/{wid}/buy", {})
        try:
            import gr_sim_app
            gr_sim_app._me_cache["at"] = 0.0          # (the credits in the top bar are asked for afresh)
        except Exception:
            pass
        return out

    @app.route("/api/gr/works/<int:wid>/save", methods=["POST"])
    def api_gr_work_save(wid):
        try:
            path = save_file(wid)
        except green_room.GRError as e:
            return jsonify({"error": str(e)}), 502
        except OSError:
            return jsonify({"error": "That was interrupted. Try again."}), 502
        try:
            mr_os.reveal(path)
        except OSError:
            pass
        return jsonify({"ok": True, "path": path, "name": os.path.basename(path), "folder": str(Path(path).parent)})

    @app.route("/api/gr/work-img/<int:wid>")
    def api_gr_work_img(wid):
        data, mime = work_img(wid, request.args.get("size") or "view")
        if not data:
            return jsonify({"error": "no such picture"}), 404
        resp = Response(data, mimetype=mime)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
