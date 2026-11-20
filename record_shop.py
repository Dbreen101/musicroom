"""Record shopping — the app's side. (The rooms server's side is gr_shop.py.)

Explore → Record shopping is three ways to come across a record that can be
bought in the Music Room: CRATES (a small finite set to sift through, three a
day), THE COUNTER (ask in words; one person answers with one record), BLIND
(hear it with no name, decide, then see it). This file is the routes the page
talks to (app.py only calls `register(app)`):

  /api/gr/shop …            what the shop is like for me today, and everything
                            below it: pull a crate, the counter, blind, a
                            seller's own crates. Asks go through to the rooms
                            server and its answers come back as they are.
  /api/gr/shop/listen       a record's LISTENING COPY, played by the page while
                            the crate (or the answer, or the blind turn) is
                            open. Held in memory here, never written down:
                            outside the crate there is nothing to play.
  /api/gr/shop/wish         "note it for later": the record's name and who it
                            is by, with the shopper's own line of why, onto the
                            wishlist.

THE WISHLIST HOLDS 100 (David, 2026-11-16). A wish leaves by being taken out
or by the record being bought (green_room._wish_bought); bought ones stay on
show as "owned" and no longer count. In the trial every way of adding to the
wishlist is held to the 100 (app.py `_wish_full`).
"""

import io
import threading
import time
from collections import OrderedDict
from contextlib import closing
from datetime import date

WISH_MAX = 100
WISH_FULL = ("Your wishlist holds {n} records, and that is as many as it keeps. "
             "Take one out, or buy one, to make room.")
WHY_MAX = 500
LISTEN_KEEP = 3                 # listening copies held at once (the one playing, the one before, the next)

_listening = OrderedDict()      # (kind, ctx, track) → (day, bytes, mimetype)
_listening_lock = threading.Lock()
_news = {"at": 0.0, "n": 0}


# ---------- the wishlist: a wish can be for a Music Room record ----------

def wish_ensure(conn):
    """wishlist.gr_track_id — the Music Room record a wish is for (empty for a
    wish from anywhere else). True when the column had to be added."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(wishlist)")}
    if not cols or "gr_track_id" in cols:
        return False
    conn.execute("ALTER TABLE wishlist ADD COLUMN gr_track_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_gr_track ON wishlist(gr_track_id)")
    return True


def _db():
    import green_room
    return green_room._db()


def wish_room(conn=None):
    """How full the wishlist is → {count, max, left, ids}. `ids` = the Music
    Room records on it (so a crate can show which ones are noted already)."""
    def read(c):
        if wish_ensure(c):
            c.commit()
        n = c.execute("SELECT COUNT(*) FROM wishlist WHERE status != 'supported'").fetchone()[0]
        ids = [r[0] for r in c.execute(
            "SELECT gr_track_id FROM wishlist WHERE gr_track_id IS NOT NULL AND status != 'supported'")]
        return {"count": n, "max": WISH_MAX, "left": max(0, WISH_MAX - n), "ids": ids}
    if conn is not None:
        return read(conn)
    with closing(_db()) as c:
        return read(c)


def wish_note(conn, rec, why, found=""):
    """Note a Music Room record for later, with the shopper's line of why.
    → (the wish as a dict, how) with how = "new" | "already" (it was on the
    list: the line of why is replaced) | "full" (the wish is None)."""
    if wish_ensure(conn):
        conn.commit()
    tid = int(rec.get("id"))
    why = " ".join(str(why or "").split())[:WHY_MAX]
    row = conn.execute("SELECT id FROM wishlist WHERE gr_track_id=? AND status != 'supported'"
                       " ORDER BY id LIMIT 1", (tid,)).fetchone()
    if row:
        if why:
            conn.execute("UPDATE wishlist SET notes=? WHERE id=?", (why, row[0]))
            conn.commit()
        return dict(conn.execute("SELECT * FROM wishlist WHERE id=?", (row[0],)).fetchone()), "already"
    if conn.execute("SELECT COUNT(*) FROM wishlist WHERE status != 'supported'").fetchone()[0] >= WISH_MAX:
        return None, "full"

    def s(v, n=300):
        return " ".join(str(v if v is not None else "").split())[:n] or None
    art = f"/api/gr/art/{tid}?v={int(rec.get('art_v') or 0)}" if rec.get("has_art") else None
    cur = conn.execute(
        "INSERT INTO wishlist (url, title, artist, source, notes, status, artwork_url, album, release_year,"
        " genre, label, provenance, gr_track_id) VALUES ('',?,?,?,?,'wishing',?,?,?,?,?,?,?)",
        (s(rec.get("title")) or "Untitled", s(rec.get("artist")), "Music Room", why or None, art,
         s(rec.get("album")), s(rec.get("year"), 8), s(rec.get("genre"), 120), s(rec.get("label"), 120),
         s(found, 200), tid))
    conn.commit()
    return dict(conn.execute("SELECT * FROM wishlist WHERE id=?", (cur.lastrowid,)).fetchone()), "new"


# ---------- listening copies, held in memory ----------

def _listen_bytes(kind, ctx, track):
    import green_room
    key, today = (kind, int(ctx), int(track) if track else 0), date.today().isoformat()
    with _listening_lock:
        for k in [k for k, v in _listening.items() if v[0] != today]:      # yesterday's are gone with the day
            _listening.pop(k, None)
        hit = _listening.get(key)
        if hit:
            _listening.move_to_end(key)
            return hit[1], hit[2]
    data, mime = green_room.shop_listen(kind, ctx, track)
    with _listening_lock:
        _listening[key] = (today, data, mime)
        while len(_listening) > LISTEN_KEEP:
            _listening.popitem(last=False)
    return data, mime


def _listen_forget(kind, ctx=None, keep=None):
    """Put listening copies down: an answer once it is settled, a blind record once the next is up."""
    with _listening_lock:
        for k in [k for k in _listening if k[0] == kind and (ctx is None or k[1] == int(ctx)) and k[1] != keep]:
            _listening.pop(k, None)


# ---------- routes ----------

def register(app):
    from flask import jsonify, request
    import green_room

    def relay(method, path, payload=None, params=None):
        """Ask the shop; its answer comes back as it is, refusals included."""
        try:
            status, data = green_room.shop_call(method, path, payload, params)
        except green_room.GRError as e:
            return jsonify({"error": str(e), "away": True}), 502
        return jsonify(data), status

    def body():
        return request.get_json(silent=True) or {}

    @app.route("/api/gr/shop")
    def api_shop():
        """The shop as I find it today, plus what is mine on this laptop: the
        basket and the wishlist (so a record can say it is in one already)."""
        try:
            status, data = green_room.shop_call("GET", "/api/shop")
        except green_room.GRError as e:
            return jsonify({"error": str(e), "away": True, "wish": wish_room()}), 502
        if status == 200:
            data["wish"] = wish_room()
            data["basket"] = {str(b["server_track_id"]): b["mode"] for b in green_room.basket()}
            _news.update(at=time.time(), n=int((data.get("counter") or {}).get("new") or 0))
        return jsonify(data), status

    @app.route("/api/gr/shop/news")
    def api_shop_news():
        """Answers waiting at the counter — asked by every page's top bar, so it
        only goes to the server now and then."""
        now = time.time()
        if now - _news["at"] > 45:
            _news["at"] = now
            try:
                status, data = green_room.shop_call("GET", "/api/shop/news")
                _news["n"] = int(data.get("answers") or 0) if status == 200 else 0
            except green_room.GRError:
                _news["n"] = 0
        return jsonify({"answers": _news["n"]})

    # ── crates ──
    @app.route("/api/gr/shop/pull", methods=["POST"])
    def api_shop_pull():
        return relay("POST", "/api/shop/crates/pull", body())

    @app.route("/api/gr/shop/pulls/<int:pid>")
    def api_shop_pull_get(pid):
        return relay("GET", f"/api/shop/pulls/{pid}")

    @app.route("/api/gr/shop/listen")
    def api_shop_listen():
        a = request.args
        kind = next((k for k in ("blind", "q", "pull") if a.get(k)), "")
        try:
            ctx = int(a.get(kind) or 0) if kind else 0
            track = int(a.get("track") or 0) if kind != "blind" else None
        except ValueError:
            ctx, track = 0, None
        if not ctx or (kind != "blind" and not track):
            return jsonify({"error": "records in the shop play from inside a crate, the counter or blind"}), 400
        try:
            data, mime = _listen_bytes(kind, ctx, track)
        except green_room.GRError as e:
            return jsonify({"error": str(e)}), 403
        # the page's player asks for it in pieces (that is how it seeks)
        total = len(data)
        start, end, status = 0, total - 1, 200
        rng = request.headers.get("Range") or ""
        if rng.startswith("bytes=") and "," not in rng:
            lo, _, hi = rng[6:].partition("-")
            try:
                if lo == "":                                  # the last N bytes
                    start = max(0, total - int(hi))
                else:
                    start = int(lo)
                    end = min(total - 1, int(hi)) if hi else total - 1
            except ValueError:
                start, end = 0, total - 1
            if start > end or start >= total:
                resp = app.response_class(status=416)
                resp.headers["Content-Range"] = f"bytes */{total}"
                return resp
            status = 206
        resp = app.response_class(data[start:end + 1], status=status, mimetype=mime)
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Cache-Control"] = "no-store"
        if status == 206:
            resp.headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return resp

    # ── finding a record in the shop by its words ──
    @app.route("/api/gr/shop/search")
    def api_shop_search():
        return relay("GET", "/api/shop/search", params={"q": request.args.get("q", "")})

    # ── a seller's own crates ──
    @app.route("/api/gr/shop/my/crates")
    def api_shop_my_crates():
        return relay("GET", "/api/my/crates")

    @app.route("/api/gr/shop/my/crates", methods=["POST"])
    def api_shop_my_crates_save():
        return relay("POST", "/api/my/crates", body())

    @app.route("/api/gr/shop/my/crates/<int:cid>", methods=["DELETE"])
    def api_shop_my_crates_delete(cid):
        return relay("DELETE", f"/api/my/crates/{cid}")

    @app.route("/api/gr/shop/crates/out")
    def api_shop_crates_out():
        return relay("GET", "/api/shop/crates/out")

    # ── the counter ──
    @app.route("/api/gr/shop/counter/ask", methods=["POST"])
    def api_shop_ask():
        return relay("POST", "/api/shop/counter/ask", body())

    @app.route("/api/gr/shop/counter/mine")
    def api_shop_mine():
        return relay("GET", "/api/shop/counter/mine")

    @app.route("/api/gr/shop/counter/<int:qid>", methods=["DELETE"])
    def api_shop_withdraw(qid):
        return relay("DELETE", f"/api/shop/counter/{qid}")

    @app.route("/api/gr/shop/counter/take", methods=["POST"])
    def api_shop_take():
        return relay("POST", "/api/shop/counter/take")

    @app.route("/api/gr/shop/counter/<int:qid>/<what>", methods=["POST"])
    def api_shop_counter_do(qid, what):
        if what not in ("skip", "answer", "seen", "settle"):
            return jsonify({"error": "no such thing to do at the counter"}), 404
        if what in ("seen", "settle"):
            _news["at"] = 0.0                               # the top bar's count is asked afresh
        if what == "settle":
            _listen_forget("q", qid)
        return relay("POST", f"/api/shop/counter/{qid}/{what}", body())

    # ── blind ──
    @app.route("/api/gr/shop/blind/next", methods=["POST"])
    def api_shop_blind_next():
        try:
            status, data = green_room.shop_call("POST", "/api/shop/blind/next")
        except green_room.GRError as e:
            return jsonify({"error": str(e), "away": True}), 502
        if status == 200:
            _listen_forget("blind", keep=int((data.get("blind") or {}).get("id") or 0))
        return jsonify(data), status

    @app.route("/api/gr/shop/blind/<int:bid>/decide", methods=["POST"])
    def api_shop_blind_decide(bid):
        return relay("POST", f"/api/shop/blind/{bid}/decide", body())

    # ── note it for later ──
    @app.route("/api/gr/shop/wish", methods=["POST"])
    def api_shop_wish():
        d = body()
        rec = d.get("record") if isinstance(d.get("record"), dict) else {}
        try:
            int(rec.get("id"))
        except (TypeError, ValueError):
            return jsonify({"error": "which record?"}), 400
        why = " ".join(str(d.get("why") or "").split())
        if len(why) < 2:
            return jsonify({"error": "Say in a few words why you are noting it."}), 400
        with closing(green_room._db()) as conn:
            wish, how = wish_note(conn, rec, why, d.get("found") or "")
            room = wish_room(conn)
        if how == "full":
            return jsonify({"error": WISH_FULL.format(n=WISH_MAX), "full": True, "wish": room}), 409
        green_room.track("wish_note", {"track_id": int(rec["id"]), "found": str(d.get("found") or "")[:80]})
        return jsonify({"noted": wish, "already": how == "already", "wish": room})

    @app.route("/api/gr/shop/wishes")
    def api_shop_wishes():
        return jsonify(wish_room())
