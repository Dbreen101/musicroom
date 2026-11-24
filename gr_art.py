"""
gr_art.py — digital artists (the rooms server's side; 2026-11-24).

Daithí: "add a new account type - digital artists. my hope is that this platform
will allow musicians and digital artists to collaborate … like the way visual
artists would collaborate to create records … maybe this is more like their
advertisement page and they can collab and find work and sell digital art
through the platform."

A digital artist is a kind of account ("digital artist", asked for at sign-up
and switched on by the master like every other kind). What it adds:

    works        still pictures the artist made, each with a title, year, medium,
                 a note and an outside link (to the moving version, a shop, a
                 site). The server keeps three files of each: the file as it was
                 sent (what a buyer gets), a view (≤ 2400 px) and a small one
                 (≤ 640 px). Shown in their room and in Explore.
    open to work a switch, a line saying what they do, and how to reach them.
    credits      a record's owner can name a digital artist as the maker of its
                 artwork; it shows on the record, and in the artist's room, once
                 the artist says yes.
    selling      a work can carry a price in credits (the credits trial). Buying
                 takes the credits from the buyer and hands over the file as it
                 was sent. What an artist's works have earned is counted on its
                 own — it is NOT added to the credits they spend as a listener.

Pictures only: no video, no audio. Nothing here is looked at by the master
before it shows (like a room's pictures): the rights tick, reports on the room
and taking the room down are the guardrails.

gr_server hands this module itself at the bottom (like gr_shop / gr_master /
gr_sim), so it works when the server is run as a script.
"""

import io
import json
import os
import secrets
from contextlib import closing
from pathlib import Path

from flask import jsonify, request, send_file

import mr_text

S = None                      # the gr_server module, given in register()

KIND = "digital artist"
WORKS_MAX = 60                # works per account
WORK_MAX_BYTES = 25 * 1024 * 1024
VIEW_PX, THUMB_PX = 2400, 640
PRICE_MAX = 1000              # credits
ANIMATED_VIEW_MAX = 8 * 1024 * 1024    # a moving GIF / WebP this small is shown as it is
WORDS = {
    "kind": "Only digital artist accounts show works.",
    "full": f"A room holds {WORKS_MAX} works. Take one out first.",
    "off": "Works are bought with credits, and the credits trial is off.",
}


# ---------- tables ----------

def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure(conn):
    """Everything this file needs, asked of the database itself every time
    (an older database must still get what is new)."""
    a = _cols(conn, "gr_accounts")
    for col, decl in (("open_to_work", "INTEGER NOT NULL DEFAULT 0"), ("work_line", "TEXT"), ("work_contact", "TEXT")):
        if col not in a:
            conn.execute(f"ALTER TABLE gr_accounts ADD COLUMN {col} {decl}")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_works(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            title TEXT NOT NULL,
            year INTEGER,
            medium TEXT,
            note TEXT,
            url TEXT,                     -- an outside link: the moving version, a site, a shop
            file_path TEXT NOT NULL,      -- the file as it was sent ('' once taken out for good)
            file_name TEXT,
            file_bytes INTEGER NOT NULL DEFAULT 0,
            mime TEXT,
            view_path TEXT,
            thumb_path TEXT,
            width INTEGER, height INTEGER,
            price INTEGER,                -- credits; NULL = not for sale
            withdrawn_at TEXT,            -- its maker took it out, but someone had bought it: they keep it
            hidden_at TEXT, hidden_note TEXT,
            rights_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gr_works_acct ON gr_works(account_id);
        CREATE TABLE IF NOT EXISTS gr_work_buys(
            id INTEGER PRIMARY KEY,
            work_id INTEGER NOT NULL REFERENCES gr_works(id),
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            credits INTEGER NOT NULL,
            at TEXT NOT NULL,
            UNIQUE(work_id, account_id)
        );
        -- "the artwork of this record is by …": asked by the record's owner, true once the artist says yes
        CREATE TABLE IF NOT EXISTS gr_art_credits(
            id INTEGER PRIMARY KEY,
            track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            by_account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            state TEXT NOT NULL DEFAULT 'asked',     -- asked | yes | no
            at TEXT NOT NULL,
            answered_at TEXT,
            UNIQUE(track_id)
        );
        CREATE INDEX IF NOT EXISTS idx_gr_art_credits_acct ON gr_art_credits(account_id, state);
        """
    )
    conn.commit()


def works_dir() -> Path:
    p = Path(S.db_path())
    return p.parent / f"{p.stem}_works"


# ---------- small things ----------

def _txt(v, n):
    return " ".join(str(v or "").split())[:n]


def _note(v, n=1200):
    return str(v or "").strip()[:n]


def _year(v):
    try:
        y = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return y if 1900 <= y <= 2100 else None


def _price(v):
    """→ credits (1…PRICE_MAX), or None for "not for sale"."""
    try:
        p = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return min(p, PRICE_MAX) if p > 0 else None


def _contact(v):
    """How to reach them: a web address or an email address, nothing else."""
    v = _txt(v, 200)
    if not v:
        return ""
    if "@" in v and " " not in v and "/" not in v and ":" not in v:
        return v
    if "://" not in v and ":" not in v and " " not in v and "." in v:
        v = "https://" + v                     # "sorcha.example/work", as people write it
    return S._web(v, 200) or ""


def is_artist(acct):
    return acct is not None and acct["kind"] == KIND


def _shown(alias="w"):
    """Works others may see."""
    return f"({alias}.file_path != '' AND {alias}.withdrawn_at IS NULL AND {alias}.hidden_at IS NULL)"


def work_json(w, viewer_id=None, bought=False, full=False):
    out = {
        "id": w["id"], "title": w["title"], "year": w["year"], "medium": w["medium"] or "",
        "note": w["note"] or "", "url": w["url"] or "", "width": w["width"], "height": w["height"],
        "price": w["price"], "for_sale": w["price"] is not None and not w["withdrawn_at"],
        "thumb": f"/api/works/{w['id']}/img?size=thumb", "view": f"/api/works/{w['id']}/img?size=view",
        "mine": viewer_id is not None and w["account_id"] == viewer_id,
        "bought": bool(bought),
    }
    if full:
        out.update(file_name=w["file_name"] or "", file_bytes=w["file_bytes"], withdrawn=bool(w["withdrawn_at"]),
                   hidden=bool(w["hidden_at"]), hidden_note=w["hidden_note"] or "", created_at=w["created_at"])
    return out


def _bought_ids(conn, aid):
    return {r[0] for r in conn.execute("SELECT work_id FROM gr_work_buys WHERE account_id=?", (aid,))}


def works_of(conn, account_id, viewer_id=None):
    mine = _bought_ids(conn, viewer_id) if viewer_id else set()
    rows = conn.execute(f"SELECT * FROM gr_works w WHERE w.account_id=? AND {_shown()} ORDER BY w.id DESC",
                        (account_id,)).fetchall()
    return [work_json(w, viewer_id, w["id"] in mine) for w in rows]


def profile_of(acct_row):
    """What a digital artist says about working with them (None for other kinds)."""
    if not is_artist(acct_row):
        return None
    keys = acct_row.keys()
    return {
        "open": bool(acct_row["open_to_work"]) if "open_to_work" in keys else False,
        "line": (acct_row["work_line"] or "") if "work_line" in keys else "",
        "contact": (acct_row["work_contact"] or "") if "work_contact" in keys else "",
    }


def credits_of(conn, account_id):
    """Records this artist made the artwork for (said by the record's owner, agreed by the artist)."""
    rows = conn.execute(
        "SELECT t.id, t.title, t.artist, t.album, t.art_path, o.handle AS owner_handle, o.name AS owner_name"
        " FROM gr_art_credits c JOIN gr_tracks t ON t.id=c.track_id"
        " LEFT JOIN gr_accounts o ON o.id=t.owner_account_id"
        " WHERE c.account_id=? AND c.state='yes' AND COALESCE(t.status,'live')='live'"
        " AND (o.id IS NULL OR o.hidden_at IS NULL) ORDER BY c.answered_at DESC", (account_id,)).fetchall()
    return [{"track_id": r["id"], "title": r["title"], "artist": r["artist"], "album": r["album"],
             "has_art": bool(r["art_path"]), "owner_handle": r["owner_handle"], "owner_name": r["owner_name"]}
            for r in rows]


# ---------- what gr_server adds to its own answers ----------

def attach_room(conn, acct_row, out, viewer=None):
    """A room as others see it: its works, the work line, the records it is credited on."""
    try:
        ensure(conn)
        if not is_artist(acct_row):
            return out
        out["works"] = works_of(conn, acct_row["id"], viewer["id"] if viewer is not None else None)
        out["work"] = profile_of(acct_row)
        out["art_credits"] = credits_of(conn, acct_row["id"])
    except Exception:
        pass
    return out


def attach_tracks(conn, rows):
    """Record rows gain art_by {handle, name} where an artwork credit was agreed."""
    try:
        ids = [r["id"] for r in rows if r.get("id")]
        if not ids:
            return rows
        ensure(conn)
        by = {}
        for i in range(0, len(ids), 400):
            part = ids[i:i + 400]
            for c in conn.execute(
                    "SELECT c.track_id, a.handle, a.name FROM gr_art_credits c JOIN gr_accounts a ON a.id=c.account_id"
                    f" WHERE c.state='yes' AND a.hidden_at IS NULL AND c.track_id IN ({','.join('?' * len(part))})", part):
                by[c["track_id"]] = {"handle": c["handle"], "name": c["name"]}
        for r in rows:
            if r.get("id") in by:
                r["art_by"] = by[r["id"]]
    except Exception:
        pass
    return rows


def room_card(conn, acct_row, card):
    """The directory's card for a digital artist: their latest works as its pictures."""
    try:
        if not is_artist(acct_row):
            return card
        ensure(conn)
        rows = conn.execute(f"SELECT w.id FROM gr_works w WHERE w.account_id=? AND {_shown()} ORDER BY w.id DESC LIMIT 4",
                            (acct_row["id"],)).fetchall()
        card["cover_work_ids"] = [r[0] for r in rows]
        card["work_count"] = conn.execute(f"SELECT COUNT(*) FROM gr_works w WHERE w.account_id=? AND {_shown()}",
                                          (acct_row["id"],)).fetchone()[0]
        p = profile_of(acct_row)
        card["open_to_work"] = p["open"]
        card["work_line"] = p["line"]
    except Exception:
        pass
    return card


# ---------- keeping a work's files ----------

def _save_files(aid, raw, img):
    """→ (file_path, view_path, thumb_path, mime, width, height)"""
    from PIL import Image

    fmt = (img.format or "").upper()
    ext, mime = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp"),
                 "GIF": ("gif", "image/gif")}.get(fmt, ("jpg", "image/jpeg"))
    folder = works_dir() / str(aid)
    folder.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(8)
    file_path = folder / f"{key}.{ext}"
    file_path.write_bytes(raw)
    width, height = img.width, img.height
    moving = bool(getattr(img, "is_animated", False))
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

    def small(px, q):
        im = img.copy() if not moving else Image.open(io.BytesIO(raw))
        im = im.convert("RGBA" if has_alpha else "RGB")
        im.thumbnail((px, px))
        out = folder / f"{key}_{px}.{'png' if has_alpha else 'jpg'}"
        if has_alpha:
            im.save(out, "PNG", optimize=True)
        else:
            im.save(out, "JPEG", quality=q)
        return out

    thumb = small(THUMB_PX, 84)
    if moving and len(raw) <= ANIMATED_VIEW_MAX:
        view = file_path                       # a small moving picture is shown moving
    else:
        view = small(VIEW_PX, 90)
    return str(file_path), str(view), str(thumb), mime, width, height


def _drop_files(w):
    for k in ("file_path", "view_path", "thumb_path"):
        p = w[k]
        if p:
            try:
                os.remove(p)
            except OSError:
                pass


# ---------- routes ----------

def register(app, server):
    global S
    S = server
    import gr_master
    import gr_sim

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    def signed_in(fn):
        with closing(S.db()) as conn:
            gr_master.ensure(conn)
            ensure(conn)
            acct, _dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            return fn(conn, acct)

    # ── the artist's own ──
    @app.get("/api/my/works")
    def my_works():
        def go(conn, acct):
            rows = conn.execute("SELECT * FROM gr_works WHERE account_id=? AND file_path != '' ORDER BY id DESC",
                                (acct["id"],)).fetchall()
            sold = {r["work_id"]: (r["n"], r["c"]) for r in conn.execute(
                "SELECT b.work_id, COUNT(*) AS n, SUM(b.credits) AS c FROM gr_work_buys b JOIN gr_works w ON w.id=b.work_id"
                " WHERE w.account_id=? GROUP BY b.work_id", (acct["id"],))}
            works = []
            for w in rows:
                j = work_json(w, acct["id"], full=True)
                j["sold"], j["earned"] = sold.get(w["id"], (0, 0))
                works.append(j)
            asks = conn.execute(
                "SELECT c.id, c.state, t.title, t.artist, t.album, o.name AS owner_name, o.handle AS owner_handle"
                " FROM gr_art_credits c JOIN gr_tracks t ON t.id=c.track_id JOIN gr_accounts o ON o.id=c.by_account_id"
                " WHERE c.account_id=? AND c.state IN ('asked','yes') ORDER BY c.state, c.at DESC", (acct["id"],)).fetchall()
            return jsonify({
                "can": is_artist(acct), "kind": acct["kind"], "works": works,
                "profile": profile_of(acct) or {"open": False, "line": "", "contact": ""},
                "sold": sum(v[0] for v in sold.values()), "earned": sum(v[1] or 0 for v in sold.values()),
                "credits": [dict(r) for r in asks],
                "selling": gr_sim.is_on(conn),
                "limits": {"works": WORKS_MAX, "bytes": WORK_MAX_BYTES, "price": PRICE_MAX},
            })
        return signed_in(go)

    @app.post("/api/my/works")
    def my_works_add():
        def go(conn, acct):
            if not is_artist(acct):
                return no(WORDS["kind"], 403)
            f = request.files.get("image")
            if not f:
                return no("choose a picture")
            if (request.form.get("rights") or "").lower() not in ("1", "true", "yes", "on"):
                return no("please confirm this work is yours to show and sell", need_rights=True)
            n = conn.execute("SELECT COUNT(*) FROM gr_works WHERE account_id=? AND file_path != '' AND withdrawn_at IS NULL",
                             (acct["id"],)).fetchone()[0]
            if n >= WORKS_MAX:
                return no(WORDS["full"], 409, full=True)
            raw = f.read(WORK_MAX_BYTES + 1)
            if len(raw) > WORK_MAX_BYTES:
                return no(f"that file is over {WORK_MAX_BYTES // (1024 * 1024)} MB", 413)
            try:
                img = S._open_picture(raw)
            except Exception:
                return no("that isn't a picture I can read (JPEG, PNG, WebP or GIF)")
            title = _txt(request.form.get("title"), 200) or _txt(os.path.splitext(f.filename or "")[0], 200) or "Untitled"
            file_path, view, thumb, mime, width, height = _save_files(acct["id"], raw, img)
            cur = conn.execute(
                "INSERT INTO gr_works(account_id, title, year, medium, note, url, file_path, file_name, file_bytes, mime,"
                " view_path, thumb_path, width, height, price, rights_at, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (acct["id"], title, _year(request.form.get("year")), _txt(request.form.get("medium"), 120),
                 _note(request.form.get("note")), S._web(request.form.get("url")) or None, file_path,
                 _txt(os.path.basename(f.filename or ""), 200), len(raw), mime, view, thumb, width, height,
                 _price(request.form.get("price")), S._now(), S._now()))
            conn.commit()
            S._event(conn, acct["id"], "work_add", {"work": cur.lastrowid, "bytes": len(raw), "w": width, "h": height,
                                                    "price": _price(request.form.get("price"))})
            return jsonify({"id": cur.lastrowid, "title": title})
        return signed_in(go)

    @app.post("/api/my/works/<int:wid>")
    def my_works_edit(wid):
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            w = conn.execute("SELECT * FROM gr_works WHERE id=? AND account_id=? AND file_path != ''", (wid, acct["id"])).fetchone()
            if not w:
                return no("not one of your works", 404)
            sets, params = [], []
            if "title" in d:
                sets.append("title=?"); params.append(_txt(d.get("title"), 200) or "Untitled")
            if "year" in d:
                sets.append("year=?"); params.append(_year(d.get("year")))
            if "medium" in d:
                sets.append("medium=?"); params.append(_txt(d.get("medium"), 120))
            if "note" in d:
                sets.append("note=?"); params.append(_note(d.get("note")))
            if "url" in d:
                sets.append("url=?"); params.append(S._web(d.get("url")) or None)
            if "price" in d:
                sets.append("price=?"); params.append(_price(d.get("price")))
            if sets:
                conn.execute(f"UPDATE gr_works SET {', '.join(sets)} WHERE id=?", params + [wid])
                conn.commit()
            return jsonify({"ok": True})
        return signed_in(go)

    @app.delete("/api/my/works/<int:wid>")
    def my_works_delete(wid):
        def go(conn, acct):
            w = conn.execute("SELECT * FROM gr_works WHERE id=? AND account_id=? AND file_path != ''", (wid, acct["id"])).fetchone()
            if not w:
                return no("not one of your works", 404)
            held = conn.execute("SELECT COUNT(*) FROM gr_work_buys WHERE work_id=?", (wid,)).fetchone()[0]
            if held:
                # someone bought it: it leaves the room and the shop, and they keep what they bought
                conn.execute("UPDATE gr_works SET withdrawn_at=?, price=NULL WHERE id=?", (S._now(), wid))
            else:
                _drop_files(w)
                conn.execute("UPDATE gr_works SET file_path='', view_path=NULL, thumb_path=NULL WHERE id=?", (wid,))
            conn.commit()
            S._event(conn, acct["id"], "work_out", {"work": wid, "held": held})
            return jsonify({"deleted": wid, "kept_for_buyers": held})
        return signed_in(go)

    @app.post("/api/my/works/profile")
    def my_works_profile():
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            if not is_artist(acct):
                return no(WORDS["kind"], 403)
            conn.execute("UPDATE gr_accounts SET open_to_work=?, work_line=?, work_contact=? WHERE id=?",
                         (1 if d.get("open") else 0, _txt(d.get("line"), 200), _contact(d.get("contact")), acct["id"]))
            conn.commit()
            a = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()
            S._event(conn, acct["id"], "work_profile", {"open": bool(d.get("open"))})
            return jsonify({"ok": True, "profile": profile_of(a)})
        return signed_in(go)

    # ── artwork credits ──
    @app.post("/api/my/records/<int:tid>/art-by")
    def record_art_by(tid):
        """A record's owner names the digital artist who made its artwork ('' takes the name off)."""
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            t = conn.execute("SELECT id FROM gr_tracks WHERE id=? AND owner_account_id=?", (tid, acct["id"])).fetchone()
            if not t:
                return no("not one of your records", 404)
            handle = str(d.get("handle") or "").strip().lstrip("@").lower()
            if not handle:
                conn.execute("DELETE FROM gr_art_credits WHERE track_id=?", (tid,))
                conn.commit()
                return jsonify({"ok": True, "art_by": None})
            who = conn.execute("SELECT * FROM gr_accounts WHERE handle=?", (handle,)).fetchone()
            if who is None:
                want = mr_text.words(handle)
                who = next((a for a in conn.execute("SELECT * FROM gr_accounts WHERE kind=?", (KIND,))
                            if mr_text.words(a["name"]) == want), None)
            if who is None or not is_artist(who):
                return no("no digital artist here has that address", 404)
            mine = who["id"] == acct["id"]
            conn.execute("DELETE FROM gr_art_credits WHERE track_id=?", (tid,))
            conn.execute("INSERT INTO gr_art_credits(track_id, account_id, by_account_id, state, at, answered_at)"
                         " VALUES(?,?,?,?,?,?)",
                         (tid, who["id"], acct["id"], "yes" if mine else "asked", S._now(), S._now() if mine else None))
            conn.commit()
            S._event(conn, acct["id"], "art_credit_ask", {"track": tid, "artist": who["handle"]})
            return jsonify({"ok": True, "art_by": {"handle": who["handle"], "name": who["name"],
                                                   "state": "yes" if mine else "asked"}})
        return signed_in(go)

    @app.get("/api/my/records/art-by")
    def records_art_by():
        """Every artwork credit on my records, whatever its state (the owner's list)."""
        def go(conn, acct):
            rows = conn.execute(
                "SELECT c.track_id, c.state, a.handle, a.name FROM gr_art_credits c JOIN gr_accounts a ON a.id=c.account_id"
                " WHERE c.by_account_id=?", (acct["id"],)).fetchall()
            return jsonify({"art_by": {str(r["track_id"]): {"handle": r["handle"], "name": r["name"], "state": r["state"]}
                                       for r in rows}})
        return signed_in(go)

    @app.post("/api/my/works/credits/<int:cid>")
    def credit_answer(cid):
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            c = conn.execute("SELECT * FROM gr_art_credits WHERE id=? AND account_id=?", (cid, acct["id"])).fetchone()
            if not c:
                return no("no such credit", 404)
            state = "yes" if d.get("yes") else "no"
            conn.execute("UPDATE gr_art_credits SET state=?, answered_at=? WHERE id=?", (state, S._now(), cid))
            conn.commit()
            S._event(conn, acct["id"], "art_credit_" + state, {"track": c["track_id"]})
            return jsonify({"ok": True, "state": state})
        return signed_in(go)

    # ── everyone ──
    @app.get("/api/works/<int:wid>/img")
    def work_img(wid):
        """Public, like a room's pictures: the view or the small one — never the file as it was sent."""
        size = "thumb" if request.args.get("size") == "thumb" else "view"
        with closing(S.db()) as conn:
            ensure(conn)
            w = conn.execute("SELECT w.*, a.hidden_at AS room_hidden FROM gr_works w"
                             " LEFT JOIN gr_accounts a ON a.id=w.account_id WHERE w.id=?", (wid,)).fetchone()
        path = w and (w["thumb_path"] if size == "thumb" else w["view_path"])
        if not w or w["hidden_at"] or w["room_hidden"] or not path or not os.path.exists(path):
            return no("no such picture", 404)
        ext = os.path.splitext(path)[1].lower()
        mime = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/jpeg")
        resp = send_file(path, mimetype=mime)
        resp.headers["Cache-Control"] = "public, max-age=2592000"
        return resp

    @app.get("/api/works/<int:wid>")
    def work_one(wid):
        def go(conn, acct):
            w = conn.execute("SELECT w.*, a.handle, a.name, a.hidden_at AS room_hidden FROM gr_works w"
                             " JOIN gr_accounts a ON a.id=w.account_id WHERE w.id=? AND w.file_path != ''", (wid,)).fetchone()
            bought = bool(w) and wid in _bought_ids(conn, acct["id"])
            mine = bool(w) and w["account_id"] == acct["id"]
            if not w or ((w["hidden_at"] or w["room_hidden"] or w["withdrawn_at"]) and not (mine or bought)):
                return no("no such work", 404)
            j = work_json(w, acct["id"], bought)
            j["by"] = {"handle": w["handle"], "name": w["name"]}
            j["selling"] = gr_sim.is_on(conn)
            if j["selling"]:
                j["credits"] = gr_sim.credits(conn, acct["id"])
            return jsonify(j)
        return signed_in(go)

    @app.post("/api/works/<int:wid>/buy")
    def work_buy(wid):
        def go(conn, acct):
            if not gr_sim.is_on(conn):
                return no(WORDS["off"], 409, off=True)
            have = gr_sim.credits(conn, acct["id"])          # (the starting credits first: that commits)
            conn.execute("BEGIN IMMEDIATE")                   # one at a time: read and spend with nothing in between
            try:
                w = conn.execute("SELECT w.*, a.hidden_at AS room_hidden FROM gr_works w JOIN gr_accounts a ON a.id=w.account_id"
                                 f" WHERE w.id=? AND {_shown()}", (wid,)).fetchone()
                if not w or w["room_hidden"]:
                    return no("that work isn't here now", 404)
                if w["account_id"] == acct["id"]:
                    return no("that one is yours already")
                if conn.execute("SELECT 1 FROM gr_work_buys WHERE work_id=? AND account_id=?", (wid, acct["id"])).fetchone():
                    return jsonify({"ok": True, "already": True, "spent": 0, "credits": have})
                if w["price"] is None:
                    return no("that work isn't for sale", 409)
                have = int(conn.execute("SELECT COALESCE(credits,0) FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()[0])
                if w["price"] > have:
                    return no(f"That costs {w['price']} credits and you have {have}.", 402, short=True,
                              cost=w["price"], credits=have)
                conn.execute("INSERT INTO gr_work_buys(work_id, account_id, credits, at) VALUES(?,?,?,?)",
                             (wid, acct["id"], w["price"], S._now()))
                bal = gr_sim._ledger(conn, acct["id"], "art", -w["price"], [], note=f"work {wid}: {w['title']}"[:200])
                conn.commit()
            finally:
                if conn.in_transaction:
                    conn.rollback()
            S._event(conn, acct["id"], "work_buy", {"work": wid, "credits": w["price"], "artist": w["account_id"]})
            return jsonify({"ok": True, "spent": w["price"], "credits": bal})
        return signed_in(go)

    @app.get("/api/works/<int:wid>/file")
    def work_file(wid):
        """The file as its maker sent it: for the maker and for whoever bought it."""
        def go(conn, acct):
            w = conn.execute("SELECT * FROM gr_works WHERE id=? AND file_path != ''", (wid,)).fetchone()
            if not w or w["hidden_at"]:
                return no("no such work", 404)
            if w["account_id"] != acct["id"] and wid not in _bought_ids(conn, acct["id"]):
                return no("that work isn't yours", 403)
            if not os.path.exists(w["file_path"]):
                return no("the file is away", 404)
            return send_file(w["file_path"], mimetype=w["mime"] or "application/octet-stream")
        return signed_in(go)

    @app.get("/api/works/bought")
    def works_bought():
        def go(conn, acct):
            rows = conn.execute(
                "SELECT w.*, a.handle, a.name, b.credits AS paid, b.at AS bought_at FROM gr_work_buys b"
                " JOIN gr_works w ON w.id=b.work_id JOIN gr_accounts a ON a.id=w.account_id"
                " WHERE b.account_id=? AND w.file_path != '' AND w.hidden_at IS NULL ORDER BY b.at DESC", (acct["id"],)).fetchall()
            out = []
            for w in rows:
                j = work_json(w, acct["id"], True)
                j.update(by={"handle": w["handle"], "name": w["name"]}, paid=w["paid"], bought_at=w["bought_at"],
                         file_name=w["file_name"] or "", mime=w["mime"] or "")
                out.append(j)
            return jsonify({"works": out})
        return signed_in(go)
