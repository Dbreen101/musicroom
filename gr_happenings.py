"""
gr_happenings.py — event pages (the rooms server's side; 2026-11-26).

An experience creator (a promoter, a DJ collective, a club night: someone who puts
on music events in person and is not a venue) and a venue can make EVENT PAGES:
a name, when, where, some words, a link out, a picture from the room's own
pictures. A page is a draft until its owner publishes it; published, it shows in
their public room and in the list of what is coming up.

The table is called gr_happenings because gr_events is the activity log.

Not built, on purpose: ticket sales and private events. The columns are there
(`tickets`, `is_private`) and the routes refuse to set them, so the pages can say
"not yet" and nothing has to move when they come.
"""

import re
from contextlib import closing
from datetime import datetime, timedelta

from flask import jsonify, request

import gr_master

S = None          # the gr_server module, given in register()

KINDS = ("experience creator", "venue")     # the kinds of account that have event pages
MOST = 200                                   # event pages one account may keep
_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
WORDS = {
    "kind": "Event pages are for experience creator and venue accounts.",
    "not_yet": "Ticket sales and private events are not here yet.",
}


def ensure(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gr_happenings(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            title TEXT NOT NULL,
            starts_at TEXT NOT NULL,          -- 2026-12-05T21:00, the place's own clock
            ends_at TEXT,
            place_name TEXT,                  -- where, in the owner's words
            about TEXT,
            link TEXT,                        -- a page out on the web
            asset_id INTEGER,                 -- one of the room's own pictures
            status TEXT NOT NULL DEFAULT 'draft',     -- draft | published
            tickets TEXT,                     -- (not yet) ticket sales
            is_private INTEGER NOT NULL DEFAULT 0,    -- (not yet) private events
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_happenings ON gr_happenings(account_id, starts_at)")
    conn.commit()


def can(acct):
    return acct is not None and acct["kind"] in KINDS


def _json(r, mine=False):
    out = {"id": r["id"], "title": r["title"], "starts_at": r["starts_at"], "ends_at": r["ends_at"] or "",
           "place": r["place_name"] or "", "about": r["about"] or "", "link": r["link"] or "",
           "asset_id": r["asset_id"], "past": _past(r)}
    if mine:
        out.update({"status": r["status"], "updated_at": r["updated_at"]})
    return out


def _past(r):
    return (r["ends_at"] or r["starts_at"]) < (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M")


def of_room(conn, account_id):
    """A room's published event pages: what is coming first, soonest first, then
    the last few that have been."""
    ensure(conn)
    rows = [_json(r) for r in conn.execute(
        "SELECT * FROM gr_happenings WHERE account_id=? AND status='published' ORDER BY starts_at", (account_id,))]
    return [e for e in rows if not e["past"]] + [e for e in reversed(rows) if e["past"]][:6]


def attach_room(conn, acct_row, out):
    if can(acct_row):
        out["happenings"] = of_room(conn, acct_row["id"])


def _fields(conn, acct, d, row=None):
    """What a request says about an event page → (values, None) or (None, words)."""
    def text(key, n, old=""):
        return (" ".join(str(d[key] or "").split()) if key != "about" else str(d[key] or "").strip())[:n] if key in d else old
    title = text("title", 160, row["title"] if row else "")
    starts = text("starts_at", 16, row["starts_at"] if row else "")
    ends = text("ends_at", 16, (row["ends_at"] or "") if row else "")
    if not title:
        return None, "An event needs a name."
    if not _WHEN.match(starts) or (ends and not _WHEN.match(ends)):
        return None, "Say when: a day and a time."
    try:
        datetime.strptime(starts, "%Y-%m-%dT%H:%M")
        if ends:
            datetime.strptime(ends, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None, "That day or time doesn't exist."
    if ends and ends < starts:
        return None, "It can't end before it starts."
    link = text("link", 500, (row["link"] or "") if row else "")
    if link and not link.startswith(("https://", "http://")):
        return None, "A link starts with https://"
    asset = d.get("asset_id", row["asset_id"] if row else None)
    if asset not in (None, "", 0):
        try:
            asset = int(asset)
        except (TypeError, ValueError):
            return None, "That picture isn't one of this room's."
        S._ensure_asset_tables(conn)
        mine = conn.execute("SELECT 1 FROM gr_assets WHERE id=? AND account_id=? AND COALESCE(path,'')!=''",
                            (asset, acct["id"])).fetchone()
        if not mine:
            return None, "That picture isn't one of this room's."
    else:
        asset = None
    status = d.get("status", row["status"] if row else "draft")
    if status not in ("draft", "published"):
        return None, "A page is a draft or published."
    return {"title": title, "starts_at": starts, "ends_at": ends or None,
            "place_name": text("place", 160, (row["place_name"] or "") if row else "") or None,
            "about": text("about", 6000, (row["about"] or "") if row else "") or None,
            "link": link or None, "asset_id": asset, "status": status}, None


def register(app, server):
    global S
    S = server

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    def signed_in(fn, maker=False):
        with closing(S.db()) as conn:
            ensure(conn)
            acct, dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            if maker:
                if not can(acct):
                    return no(WORDS["kind"], 403)
                import gr_signin
                stop = gr_signin.need_two_factor(conn, acct)
                if stop:
                    return stop
            return fn(conn, acct)

    def body():
        return request.get_json(force=True, silent=True) or {}

    @app.get("/api/my/happenings")
    def my_happenings():
        def go(conn, acct):
            rows = conn.execute("SELECT * FROM gr_happenings WHERE account_id=? ORDER BY starts_at DESC", (acct["id"],))
            return jsonify({"can": can(acct), "happenings": [_json(r, mine=True) for r in rows] if can(acct) else [],
                            "not_yet": WORDS["not_yet"]})
        return signed_in(go)

    @app.post("/api/my/happenings")
    def my_happening_new():
        d = body()

        def go(conn, acct):
            if d.get("tickets") or d.get("is_private"):
                return no(WORDS["not_yet"], 409, not_yet=True)
            if conn.execute("SELECT COUNT(*) FROM gr_happenings WHERE account_id=?", (acct["id"],)).fetchone()[0] >= MOST:
                return no(f"A room keeps {MOST} event pages. Take an old one out first.", 409)
            v, why = _fields(conn, acct, d)
            if why:
                return no(why)
            cur = conn.execute(
                "INSERT INTO gr_happenings(account_id, title, starts_at, ends_at, place_name, about, link, asset_id,"
                " status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (acct["id"], v["title"], v["starts_at"], v["ends_at"], v["place_name"], v["about"], v["link"],
                 v["asset_id"], v["status"], S._now(), S._now()))
            conn.commit()
            S._event(conn, acct["id"], "happening", {"id": cur.lastrowid, "status": v["status"]})
            r = conn.execute("SELECT * FROM gr_happenings WHERE id=?", (cur.lastrowid,)).fetchone()
            return jsonify({"happening": _json(r, mine=True)})
        return signed_in(go, maker=True)

    @app.post("/api/my/happenings/<int:hid>")
    def my_happening_set(hid):
        d = body()

        def go(conn, acct):
            if d.get("tickets") or d.get("is_private"):
                return no(WORDS["not_yet"], 409, not_yet=True)
            row = conn.execute("SELECT * FROM gr_happenings WHERE id=? AND account_id=?", (hid, acct["id"])).fetchone()
            if not row:
                return no("no such event page", 404)
            v, why = _fields(conn, acct, d, row)
            if why:
                return no(why)
            conn.execute(
                "UPDATE gr_happenings SET title=?, starts_at=?, ends_at=?, place_name=?, about=?, link=?, asset_id=?,"
                " status=?, updated_at=? WHERE id=?",
                (v["title"], v["starts_at"], v["ends_at"], v["place_name"], v["about"], v["link"], v["asset_id"],
                 v["status"], S._now(), hid))
            conn.commit()
            if v["status"] != row["status"]:
                S._event(conn, acct["id"], "happening", {"id": hid, "status": v["status"]})
            r = conn.execute("SELECT * FROM gr_happenings WHERE id=?", (hid,)).fetchone()
            return jsonify({"happening": _json(r, mine=True)})
        return signed_in(go, maker=True)

    @app.delete("/api/my/happenings/<int:hid>")
    def my_happening_out(hid):
        def go(conn, acct):
            n = conn.execute("DELETE FROM gr_happenings WHERE id=? AND account_id=?", (hid, acct["id"])).rowcount
            conn.commit()
            return jsonify({"removed": bool(n)})
        return signed_in(go, maker=True)

    @app.get("/api/happenings")
    def happenings():
        """What is coming up, across every public room that isn't taken down."""
        def go(conn, acct):
            rows = conn.execute(
                "SELECT h.*, a.handle, a.name, a.kind FROM gr_happenings h JOIN gr_accounts a ON a.id=h.account_id"
                " WHERE h.status='published' AND a.is_public=1 AND a.hidden_at IS NULL AND a.disabled_at IS NULL"
                " ORDER BY h.starts_at LIMIT 400").fetchall()
            out = []
            for r in rows:
                if r["kind"] not in KINDS or _past(r):
                    continue
                out.append(dict(_json(r), by={"handle": r["handle"], "name": r["name"], "kind": r["kind"]}))
            return jsonify({"happenings": out})
        return signed_in(go)
