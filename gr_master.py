"""
gr_master.py — the master account, and the guardrails the rooms server keeps.

Daithí, 2026-11-20, launching to the Green Room's twenty fellows with the code
open: everyone makes their own account (a listener); there are also artist,
label, venue, business and shop accounts; and he has a MASTER account. People
may shape their own rooms and build plug-ins, but may not reach anyone else's
data or the records' audio, and may not put up music or pictures they have no
right to. This file is where the server holds those lines.

    the master       one or more accounts marked is_master (only from the
                     server's own Terminal: `gr_server.py master …`). Sees and
                     settles everything below, from the app's /master page.
    sign-up          always makes a LISTENER. "I'm also an artist / label /
                     venue / business / shop" is kept as a request
                     (kind_requested) for the master to approve. The house
                     rules must be agreed to (agreed_at).
    paused accounts  disabled_at set by the master → every sign-in of that
                     account fails until it is lifted.
    records          a record uploaded by an artist / label / shop needs a
                     rights declaration and goes in as PENDING: nobody but its
                     owner and the master can see it until the master
                     approves it (status live). The master can also refuse a
                     record or take a live one down (hidden). Records the
                     master adds from Terminal are live at once.
    reports          anyone signed in can report a room, a record or a public
                     grúpa ("it uses music or pictures they have no rights
                     to" …). The master settles each one, taking the thing
                     down or not.
    hidden rooms     the master can take a public room (and its public
                     grúpaí) down; its owner still sees it, with why.
    feedback         the in-app feedback and bug reports, with a done mark.
    the version      which release of the app everyone should be on, and where
                     to get it: the app shows "a new version is ready" when
                     its own differs. Pointing it back at an older release is
                     how a step back reaches everyone.
    plug-ins         plug-ins read the shop's records through one route that
                     gives out only what is printed on them (never a file,
                     never anyone's account), and can hand a shopper a crate
                     of up to 25 of them (gr_shop.make_pick).

gr_server hands this module itself at the bottom (like gr_shop), so it works
when the server is run as a script.
"""

import json
import os
import threading
import time
from contextlib import closing

from flask import jsonify, request, send_file

S = None          # the gr_server module, given in register()

# (the kinds a person can apply for now live in gr_apply.kinds(); this is kept for older callers)
KINDS_TO_ASK = ("artist", "label", "venue", "experience creator", "business", "shop")
STATUSES = ("pending", "live", "refused", "hidden")
REPORT_WHAT = ("room", "record", "grupa")
REPORT_REASONS = {
    "rights": "It uses music or pictures they have no rights to",
    "hurtful": "It is hurtful, hateful or unsafe",
    "private": "It shows someone's private details",
    "other": "Something else",
}
HOUSE_RULES_VERSION = "2026-11-26"
SIGNUPS_PER_HOUR = 6          # from one address; twenty fellows never come near it
SIGNUPS_PER_HOUR_WITH_CODE = 40   # …but with an invite code set the code is the lock, and a whole
                                  # building reaches a tunnel from ONE address (the Wi-Fi's own)

# the one way every query asks "may anyone see this record?"
LIVE = "COALESCE(t.status,'live')='live'"


def live(alias="t"):
    return f"COALESCE({alias}.status,'live')='live'"


# ---------- tables ----------

def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure(conn):
    """Columns and tables this file needs. Safe to run again and again: it
    asks the database itself what is already there."""
    add = []
    a = _cols(conn, "gr_accounts")
    for col, decl in (("is_master", "INTEGER NOT NULL DEFAULT 0"), ("kind_requested", "TEXT"),
                      ("disabled_at", "TEXT"), ("disabled_note", "TEXT"), ("agreed_at", "TEXT"),
                      ("agreed_version", "TEXT"), ("hidden_at", "TEXT"), ("hidden_note", "TEXT")):
        if col not in a:
            add.append(f"ALTER TABLE gr_accounts ADD COLUMN {col} {decl}")
    t = _cols(conn, "gr_tracks")
    for col, decl in (("status", "TEXT NOT NULL DEFAULT 'live'"), ("rights_note", "TEXT"),
                      ("rights_at", "TEXT"), ("review_note", "TEXT"), ("reviewed_at", "TEXT")):
        if col not in t:
            add.append(f"ALTER TABLE gr_tracks ADD COLUMN {col} {decl}")
    f = _cols(conn, "gr_feedback")
    for col, decl in (("status", "TEXT NOT NULL DEFAULT 'open'"), ("done_at", "TEXT")):
        if col not in f:
            add.append(f"ALTER TABLE gr_feedback ADD COLUMN {col} {decl}")
    for sql in add:
        conn.execute(sql)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_reports(
            id INTEGER PRIMARY KEY,
            reporter_id INTEGER REFERENCES gr_accounts(id),
            what TEXT NOT NULL,              -- room | record | grupa
            ref TEXT NOT NULL,               -- a room's handle, a record's id, a public grúpa's id
            owner_id INTEGER,                -- whose it is
            title TEXT,                      -- what it was called when reported
            reason TEXT NOT NULL,            -- a key of REPORT_REASONS
            note TEXT,
            status TEXT NOT NULL DEFAULT 'open',   -- open | done
            action TEXT,                     -- what the master did: none | hidden
            resolved_note TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_gr_reports_status ON gr_reports(status, created_at);
        CREATE TABLE IF NOT EXISTS gr_settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    # the image uploads of public rooms carry a rights line too (their table is made lazily)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gr_assets'").fetchone():
        if "rights_at" not in _cols(conn, "gr_assets"):
            conn.execute("ALTER TABLE gr_assets ADD COLUMN rights_at TEXT")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gr_grupai'").fetchone():
        g = _cols(conn, "gr_grupai")
        if "hidden_at" not in g:
            conn.execute("ALTER TABLE gr_grupai ADD COLUMN hidden_at TEXT")
            conn.execute("ALTER TABLE gr_grupai ADD COLUMN hidden_note TEXT")
    conn.commit()


def _has(row, key):
    try:
        return key in row.keys()
    except Exception:
        return False


def is_master(acct):
    return bool(acct is not None and _has(acct, "is_master") and acct["is_master"])


def is_paused(acct):
    return bool(acct is not None and _has(acct, "disabled_at") and acct["disabled_at"])


def is_hidden(acct):
    return bool(acct is not None and _has(acct, "hidden_at") and acct["hidden_at"])


def record_visible(track, viewer):
    """May this person see this record at all? Live records: everyone signed in.
    Anything else: its owner and the master only."""
    if track is None:
        return False
    if (track["status"] if _has(track, "status") else "live") in (None, "live"):
        return True
    return viewer is not None and (is_master(viewer) or track["owner_account_id"] == viewer["id"])


# ---------- small things ----------

def setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM gr_settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return default


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO gr_settings(key, value) VALUES(?,?)", (key, json.dumps(value)))
    conn.commit()


_rate, _rate_lock = {}, threading.Lock()


# What a relay in front of the server (a tunnel, Caddy, any reverse proxy) adds
# to a request it passes on. The master's own app, on the server's own computer,
# talks to it directly and sends none of these.
PASSED_ON = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Forwarded-Port",
             "Forwarded", "Via", "X-Real-IP", "CF-Connecting-IP", "CF-Ray", "True-Client-IP",
             "Tailscale-User-Login", "Tailscale-Funnel-Request")
_HERE = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def passed_on():
    """True when this request reached the server through a relay."""
    return any(request.headers.get(h) for h in PASSED_ON)


def asker():
    """The address a request really came from. Through a relay on this
    computer every request arrives from 127.0.0.1, so there the relay's own
    note of who it took it from is used: the LAST address in X-Forwarded-For
    (the one the relay itself wrote; a visitor can't forge it). A request that
    came straight in is taken at its own address, whatever its headers say."""
    peer = request.remote_addr or "?"
    if peer in _HERE:
        for h in ("X-Forwarded-For", "CF-Connecting-IP", "True-Client-IP", "X-Real-IP"):
            last = (request.headers.get(h) or "").split(",")[-1].strip()
            if last:
                return last[:64]
    return peer


def master_here():
    """The master's routes answer only on the server's own computer (its app
    talks to the server at 127.0.0.1): even a master's code copied off somewhere
    can't be used from another laptop. Behind a tunnel or a reverse proxy every
    visitor ARRIVES from 127.0.0.1, so that alone is not enough: the request
    must also have come straight in (nothing a relay adds), asking for this
    computer by its own name. MR_MASTER_ANYWHERE=1 lifts all of it."""
    if os.environ.get("MR_MASTER_ANYWHERE") == "1":
        return True
    if (request.remote_addr or "") not in _HERE or passed_on():
        return False
    host = (request.host or "").lower()
    host = host.split("]")[0].lstrip("[") if host.startswith("[") else host.rsplit(":", 1)[0]   # [::1]:5300
    return host in ("127.0.0.1", "localhost", "::1")


# ---------- the door: who may make an account, and where the server lives now ----------

def door(conn):
    """{code, moved_to}. `code`: with one set, a new account needs it (a server
    anyone on the internet can reach should have one). `moved_to`: the server's
    new address; apps that ask this one are told, and follow."""
    d = setting(conn, "door", {}) or {}
    return {"code": str(d.get("code") or ""), "moved_to": str(d.get("moved_to") or "")}


def door_code_ok(conn, given):
    want = door(conn)["code"]
    return (not want) or secrets_equal(_fold_code(given), _fold_code(want))


def _fold_code(v):
    return "".join(str(v or "").split()).lower()


def secrets_equal(a, b):
    import hmac
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def set_door(conn, code=None, moved_to=None):
    """Change the invite code and / or the new address ('' clears one; None
    leaves it). → the door, or raises ValueError with words for a person."""
    d = door(conn)
    if code is not None:
        code = " ".join(str(code).split())[:80]
        if code and len(_fold_code(code)) < 6:
            raise ValueError("an invite code needs at least six letters or numbers")
        d["code"] = code
    if moved_to is not None:
        moved_to = str(moved_to).strip().rstrip("/")[:300]
        if moved_to and not moved_to.startswith("https://"):
            raise ValueError("the new address should start with https://")
        d["moved_to"] = moved_to
    set_setting(conn, "door", d)
    return d


def rate_ok(key, most, window_s):
    """True while `key` has been seen fewer than `most` times in the last window."""
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate.get(key, []) if now - t < window_s]
        if len(hits) >= most:
            _rate[key] = hits
            return False
        hits.append(now)
        _rate[key] = hits
        return True


def rate_full(key, most, window_s):
    """True when `key` has already been seen `most` times in the last window
    (a look only: nothing is counted)."""
    now = time.time()
    with _rate_lock:
        return len([t for t in _rate.get(key, []) if now - t < window_s]) >= most


def proof_of(token, ask):
    """`ask` signed with a laptop's sign-in (HMAC-SHA256): only someone who holds
    the sign-in can make it, and it gives nothing of the sign-in away. The app
    makes the same sum itself (green_room._proof_of) and compares."""
    import hashlib
    import hmac
    return hmac.new(str(token).encode("utf-8"), str(ask).encode("utf-8"), hashlib.sha256).hexdigest()


def _txt(v, n):
    return str(v or "").strip()[:n]


# ---------- from the server's own Terminal ----------

def make_master(name, handle=None, off=False):
    """`gr_server.py master <name>`: make an account the master (a new one, or
    the one with this handle). Prints the account code to sign in with."""
    with closing(S.db()) as conn:
        S.init_db(conn)
        row = None
        if handle:
            row = conn.execute("SELECT * FROM gr_accounts WHERE handle=?", (handle,)).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM gr_accounts WHERE LOWER(name)=LOWER(?) AND is_master=1",
                               (name,)).fetchone()
        if off:
            if not row:
                return f"no account '{handle or name}'"
            conn.execute("UPDATE gr_accounts SET is_master=0 WHERE id=?", (row["id"],))
            conn.commit()
            return f"{row['name']} is no longer a master account"
        if not row:
            code = S.make_invite(name, kind="listener", handle=handle)
            row = conn.execute("SELECT * FROM gr_accounts WHERE invite_code=?", (code,)).fetchone()
        conn.execute("UPDATE gr_accounts SET is_master=1, agreed_at=COALESCE(agreed_at, ?),"
                     " agreed_version=COALESCE(agreed_version, ?) WHERE id=?",
                     (S._now(), HOUSE_RULES_VERSION, row["id"]))
        conn.commit()
        return (f"{row['name']} (@{row['handle']}) is a master account.\n"
                f"Sign in from the app: the front door → \"I have an account\" → the code  {row['invite_code']}")


# ---------- what the routes say about an account / a record ----------

def account_json(conn, a):
    one = lambda sql: conn.execute(sql, (a["id"],)).fetchone()[0]
    return {
        "id": a["id"], "name": a["name"], "handle": a["handle"], "kind": a["kind"],
        "kind_requested": a["kind_requested"] or "", "is_master": bool(a["is_master"]),
        "is_public": bool(a["is_public"]), "created_at": a["created_at"],
        "paused": bool(a["disabled_at"]), "paused_note": a["disabled_note"] or "",
        "hidden": bool(a["hidden_at"]), "hidden_note": a["hidden_note"] or "",
        "agreed": bool(a["agreed_at"]),
        "status": S.gr_apply.status_of(conn, a),      # approved | pending | rejected | suspended
        "email": a["email"] or "", "has_password": bool(a["password_hash"]), "two_factor": bool(a["totp_secret"]),
        "devices": one("SELECT COUNT(*) FROM gr_devices WHERE account_id=?"),
        "last_seen": conn.execute("SELECT MAX(last_seen) FROM gr_devices WHERE account_id=?",
                                  (a["id"],)).fetchone()[0],
        "records": one("SELECT COUNT(*) FROM gr_tracks WHERE owner_account_id=?"),
        "pending": one("SELECT COUNT(*) FROM gr_tracks WHERE owner_account_id=? AND status='pending'"),
        "borrows": one("SELECT COUNT(*) FROM gr_borrows WHERE account_id=?"),
        "bought": one("SELECT COUNT(*) FROM gr_purchases WHERE account_id=?"),
        "feedback": one("SELECT COUNT(*) FROM gr_feedback WHERE account_id=?"),
    }


def record_json(r):
    return {
        "id": r["id"], "title": r["title"], "artist": r["artist"], "album": r["album"],
        "year": r["year"] if _has(r, "year") else None,
        "genre": (r["genre"] if _has(r, "genre") else "") or "",
        "label": (r["label"] if _has(r, "label") else "") or "",
        "duration_s": r["duration_s"], "format": r["format"], "size_bytes": r["size_bytes"],
        "price_cents": r["price_cents"], "added_at": r["added_at"],
        "status": r["status"] or "live", "rights_note": r["rights_note"] or "", "rights_at": r["rights_at"],
        "exclusive": bool(r["exclusive"]) if _has(r, "exclusive") else False,
        "review_note": r["review_note"] or "", "reviewed_at": r["reviewed_at"],
        "has_art": bool(r["art_path"]) and os.path.exists(r["art_path"]),
        "owner": {"handle": r["o_handle"], "name": r["o_name"], "kind": r["o_kind"]} if _has(r, "o_handle") else None,
    }


def plugin_catalogue(conn):
    """Every live record, as plug-ins may see it: only what is printed on it
    and who sells it — never a file, a path, a price paid, or anyone else's
    account."""
    rows = conn.execute(
        "SELECT t.id, t.title, t.artist, t.album, t.year, t.genre, t.label, t.duration_s, t.price_cents, t.exclusive,"
        " t.added_at, t.art_path, a.handle AS o_handle, a.name AS o_name, a.kind AS o_kind,"
        " a.place_name AS o_place, a.lat AS o_lat, a.lon AS o_lon, a.is_house AS o_is_house"
        " FROM gr_tracks t LEFT JOIN gr_accounts a ON a.id = t.owner_account_id"
        f" WHERE {LIVE} AND (a.id IS NULL OR a.hidden_at IS NULL)"
        " ORDER BY t.artist COLLATE NOCASE, t.album COLLATE NOCASE, t.title COLLATE NOCASE").fetchall()
    import mr_text
    rows.sort(key=lambda r: (mr_text.fold(r["artist"]), mr_text.fold(r["album"]), mr_text.fold(r["title"])))
    import gr_shop
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "title": r["title"] or "", "artist": r["artist"] or "", "album": r["album"] or "",
            "exclusive": bool(r["exclusive"]) if _has(r, "exclusive") else False,
            "year": r["year"], "genres": gr_shop.genres_of(r["genre"]), "label": r["label"] or "",
            "duration_s": r["duration_s"], "price_cents": r["price_cents"], "added": (r["added_at"] or "")[:10],
            "has_cover": bool(r["art_path"]),
            "seller": ({"handle": r["o_handle"], "name": gr_shop.HOUSE_NAME if r["o_is_house"] else r["o_name"],
                        "kind": r["o_kind"], "place": r["o_place"] or "",
                        "lat": r["o_lat"], "lon": r["o_lon"]} if r["o_handle"] else None),
        })
    return out


# ---------- routes ----------

def register(app, server):
    global S
    S = server

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    def signed_in(fn, master=False):
        with closing(S.db()) as conn:
            ensure(conn)
            acct, dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            if master and not is_master(acct):
                return no("only the master account can do that", 403, master=False)
            if master and not master_here():
                return no("the master's page works only on the Mac the server runs on", 403, master=False)
            if master:
                stop = S.gr_signin.need_two_factor(conn, acct)     # (the master must have two-factor: gr_signin.py)
                if stop:
                    return stop
            return fn(conn, acct)

    # ── open to anyone: which version of the app everyone should be on ──
    @app.get("/api/version")
    def version_now():
        with closing(S.db()) as conn:
            ensure(conn)
            v = setting(conn, "app_version", {}) or {}
            d = door(conn)
        return jsonify({"version": v.get("version") or "", "url": v.get("url") or "",
                        "note": v.get("note") or "", "at": v.get("at") or "",
                        "house_rules": HOUSE_RULES_VERSION,
                        # (never the code itself: only that one is needed)
                        "invite": bool(d["code"]), "moved_to": d["moved_to"]})

    # ── open to anyone: proof that this server holds a laptop's sign-in ──
    @app.get("/api/knows")
    def knows():
        """An app that is thinking of coming (back) to this address asks first: do you
        hold my sign-in? It names its laptop and sends words it made up; the answer is
        those words signed with that laptop's sign-in. So the app never has to send
        the sign-in itself to an address it is not sure of, and a stranger's server
        can't answer. A laptop nobody knows gets an empty answer."""
        device = _txt(request.args.get("device"), 80)
        ask = _txt(request.args.get("ask"), 80)
        if not device or len(ask) < 16:
            return jsonify({"error": "name the laptop and send at least 16 letters to sign"}), 400
        if not rate_ok("knows:" + asker(), 30, 600):
            return jsonify({"error": "Too many tries. Wait ten minutes."}), 429
        with closing(S.db()) as conn:
            rows = conn.execute("SELECT token FROM gr_devices WHERE fingerprint=? LIMIT 5", (device,)).fetchall()
        return jsonify({"proofs": [proof_of(r["token"], ask) for r in rows if r["token"]]})

    # ── anyone signed in: report something ──
    @app.post("/api/report")
    def report():
        d = request.get_json(force=True, silent=True) or {}
        what, ref = _txt(d.get("what"), 10), _txt(d.get("ref"), 80)
        reason = d.get("reason") if d.get("reason") in REPORT_REASONS else "other"

        def go(conn, acct):
            if what not in REPORT_WHAT or not ref:
                return no("say what is being reported")
            if not rate_ok(f"report:{acct['id']}", 20, 3600):
                return no("That's a lot of reports in one hour. Try again later.", 429)
            owner, title = None, ""
            if what == "room":
                a = conn.execute("SELECT id, name FROM gr_accounts WHERE handle=?", (ref,)).fetchone()
                owner, title = (a["id"], a["name"]) if a else (None, "")
            elif what == "record" and ref.isdigit():
                t = conn.execute("SELECT owner_account_id, title, artist FROM gr_tracks WHERE id=?", (int(ref),)).fetchone()
                owner, title = (t["owner_account_id"], f"{t['artist'] or ''} — {t['title'] or ''}") if t else (None, "")
            elif what == "grupa" and ref.isdigit():
                S._ensure_grupa_tables(conn)
                g = conn.execute("SELECT account_id, name FROM gr_grupai WHERE id=?", (int(ref),)).fetchone()
                owner, title = (g["account_id"], g["name"]) if g else (None, "")
            if not title and owner is None:
                return no("that isn't here any more", 404)
            if owner == acct["id"]:
                return no("that one is yours — change or remove it yourself")
            cur = conn.execute(
                "INSERT INTO gr_reports(reporter_id, what, ref, owner_id, title, reason, note, created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (acct["id"], what, ref, owner, title[:200], reason, _txt(d.get("note"), 1000), S._now()))
            conn.commit()
            S._event(conn, acct["id"], "report", {"what": what, "ref": ref, "reason": reason})
            return jsonify({"reported": cur.lastrowid})
        return signed_in(go)

    @app.get("/api/report/reasons")
    def report_reasons():
        return jsonify({"reasons": [{"key": k, "label": v} for k, v in REPORT_REASONS.items()]})

    # ── plug-ins: the shop's records, as plug-ins may see them ──
    @app.get("/api/plugins/catalogue")
    def catalogue_for_plugins():
        return signed_in(lambda conn, acct: jsonify({"records": plugin_catalogue(conn)}))

    # ── the master ──
    @app.get("/api/master/overview")
    def m_overview():
        def go(conn, acct):
            one = lambda sql: conn.execute(sql).fetchone()[0]
            return jsonify({
                "me": {"name": acct["name"], "handle": acct["handle"]},
                "accounts": one("SELECT COUNT(*) FROM gr_accounts"),
                "requests": one("SELECT COUNT(*) FROM gr_accounts WHERE COALESCE(kind_requested,'')!=''"),
                "applications": one("SELECT COUNT(*) FROM gr_applications WHERE status='pending'"),
                "pending": one("SELECT COUNT(*) FROM gr_tracks WHERE status='pending'"),
                "reports": one("SELECT COUNT(*) FROM gr_reports WHERE status='open'"),
                "feedback": one("SELECT COUNT(*) FROM gr_feedback WHERE COALESCE(status,'open')='open'"),
                "version": setting(conn, "app_version", {}) or {},
                "door": door(conn),
            })
        return signed_in(go, master=True)

    @app.post("/api/master/door")
    def m_door():
        """The invite code new accounts need, and the server's new address."""
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            try:
                out = set_door(conn, d.get("code") if "code" in d else None,
                               d.get("moved_to") if "moved_to" in d else None)
            except ValueError as e:
                return no(str(e))
            S._event(conn, acct["id"], "master_door", {"code": bool(out["code"]), "moved_to": out["moved_to"]})
            return jsonify(out)
        return signed_in(go, master=True)

    @app.get("/api/master/accounts")
    def m_accounts():
        def go(conn, acct):
            rows = conn.execute("SELECT * FROM gr_accounts ORDER BY COALESCE(kind_requested,'')='' ,"
                                " created_at DESC").fetchall()
            return jsonify({"accounts": [account_json(conn, a) for a in rows],
                            "kinds": list(S.kinds_on())})
        return signed_in(go, master=True)

    @app.post("/api/master/accounts/<int:aid>")
    def m_account_set(aid):
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            a = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (aid,)).fetchone()
            if not a:
                return no("no such account", 404)
            said = []
            if "kind" in d:
                kind = d.get("kind")
                if kind not in S.kinds_on():
                    return no("that isn't a kind of account")
                conn.execute("UPDATE gr_accounts SET kind=?, kind_requested=NULL WHERE id=?", (kind, aid))
                # (a waiting application is settled with it, so who decided is on record)
                S.gr_apply.settle_for_account(conn, aid, acct, kind == a["kind_requested"], _txt(d.get("note"), 1000))
                conn.execute("UPDATE gr_accounts SET kind=? WHERE id=?", (kind, aid))
                said.append(f"kind → {kind}")
            if d.get("request") == "approve" and a["kind_requested"]:
                conn.execute("UPDATE gr_accounts SET kind=?, kind_requested=NULL WHERE id=?", (a["kind_requested"], aid))
                S.gr_apply.settle_for_account(conn, aid, acct, True, _txt(d.get("note"), 1000))
                said.append(f"request approved → {a['kind_requested']}")
            elif d.get("request") == "refuse":
                conn.execute("UPDATE gr_accounts SET kind_requested=NULL WHERE id=?", (aid,))
                S.gr_apply.settle_for_account(conn, aid, acct, False, _txt(d.get("note"), 1000))
                said.append("request refused")
            if "paused" in d:
                if aid == acct["id"] and d.get("paused"):
                    return no("you can't pause your own account")
                conn.execute("UPDATE gr_accounts SET disabled_at=?, disabled_note=? WHERE id=?",
                             (S._now() if d.get("paused") else None, _txt(d.get("note"), 300) or None, aid))
                said.append("paused" if d.get("paused") else "unpaused")
            if "master" in d:
                if not d.get("master"):
                    others = conn.execute("SELECT COUNT(*) FROM gr_accounts WHERE is_master=1 AND id!=?",
                                          (aid,)).fetchone()[0]
                    if not others:
                        return no("there must always be one master account")
                conn.execute("UPDATE gr_accounts SET is_master=? WHERE id=?", (1 if d.get("master") else 0, aid))
                said.append("master" if d.get("master") else "not master")
            if d.get("devices") == "free":
                # each account signs in on two devices; a wiped laptop or a move used one up for good.
                # This signs the account out everywhere — its person signs in again with their code.
                n = conn.execute("DELETE FROM gr_devices WHERE account_id=?", (aid,)).rowcount
                said.append(f"{n} device{'' if n == 1 else 's'} signed out")
            if "hidden" in d:
                conn.execute("UPDATE gr_accounts SET hidden_at=?, hidden_note=? WHERE id=?",
                             (S._now() if d.get("hidden") else None, _txt(d.get("note"), 300) or None, aid))
                said.append("room taken down" if d.get("hidden") else "room back up")
            conn.commit()
            S._event(conn, acct["id"], "master_account", {"account": aid, "did": said})
            a = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (aid,)).fetchone()
            return jsonify({"account": account_json(conn, a), "did": said})
        return signed_in(go, master=True)

    @app.get("/api/master/records")
    def m_records():
        status = request.args.get("status") or "pending"

        def go(conn, acct):
            where, params = ("", ()) if status == "all" else ("WHERE COALESCE(t.status,'live')=?", (status,))
            rows = conn.execute(
                "SELECT t.*, a.handle AS o_handle, a.name AS o_name, a.kind AS o_kind FROM gr_tracks t"
                f" LEFT JOIN gr_accounts a ON a.id = t.owner_account_id {where}"
                " ORDER BY t.added_at DESC LIMIT 500", params).fetchall()
            return jsonify({"records": [record_json(r) for r in rows]})
        return signed_in(go, master=True)

    @app.post("/api/master/records/<int:tid>")
    def m_record_set(tid):
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            if d.get("status") not in STATUSES:
                return no("approve (live), refuse, or take down (hidden)")
            t = conn.execute("SELECT * FROM gr_tracks WHERE id=?", (tid,)).fetchone()
            if not t:
                return no("no such record", 404)
            conn.execute("UPDATE gr_tracks SET status=?, review_note=?, reviewed_at=? WHERE id=?",
                         (d["status"], _txt(d.get("note"), 500) or None, S._now(), tid))
            conn.commit()
            S._event(conn, acct["id"], "master_record", {"record": tid, "status": d["status"]})
            return jsonify({"id": tid, "status": d["status"]})
        return signed_in(go, master=True)

    @app.get("/api/master/records/<int:tid>/audio")
    def m_record_audio(tid):
        """The master listens to a record before approving it."""
        with closing(S.db()) as conn:
            ensure(conn)
            acct, _dev = S._auth(conn)
            if not acct or not is_master(acct) or not master_here() or S.gr_signin.need_two_factor(conn, acct):
                return no("only the master account can do that", 403)
            t = conn.execute("SELECT path, format FROM gr_tracks WHERE id=?", (tid,)).fetchone()
        if not t or not t["path"] or not os.path.isfile(t["path"]):
            return no("the file isn't there", 404)
        return send_file(t["path"], conditional=True)

    @app.get("/api/master/records/<int:tid>/art")
    def m_record_art(tid):
        with closing(S.db()) as conn:
            acct, _dev = S._auth(conn)
            if not acct or not is_master(acct) or not master_here():
                return no("only the master account can do that", 403)
            t = conn.execute("SELECT art_path FROM gr_tracks WHERE id=?", (tid,)).fetchone()
        if not t or not t["art_path"] or not os.path.isfile(t["art_path"]):
            return no("no cover", 404)
        return send_file(t["art_path"], mimetype="image/jpeg")

    @app.get("/api/master/reports")
    def m_reports():
        status = request.args.get("status") or "open"

        def go(conn, acct):
            where, params = ("", ()) if status == "all" else ("WHERE r.status=?", (status,))
            rows = conn.execute(
                "SELECT r.*, a.name AS reporter_name, a.handle AS reporter_handle,"
                " o.name AS owner_name, o.handle AS owner_handle FROM gr_reports r"
                " LEFT JOIN gr_accounts a ON a.id=r.reporter_id LEFT JOIN gr_accounts o ON o.id=r.owner_id"
                f" {where} ORDER BY r.created_at DESC LIMIT 500", params).fetchall()
            return jsonify({"reports": [{
                "id": r["id"], "what": r["what"], "ref": r["ref"], "title": r["title"] or "",
                "reason": r["reason"], "reason_label": REPORT_REASONS.get(r["reason"], r["reason"]),
                "note": r["note"] or "", "status": r["status"], "action": r["action"] or "",
                "resolved_note": r["resolved_note"] or "", "at": r["created_at"], "resolved_at": r["resolved_at"],
                "by": {"name": r["reporter_name"], "handle": r["reporter_handle"]},
                "owner": {"name": r["owner_name"], "handle": r["owner_handle"]},
            } for r in rows]})
        return signed_in(go, master=True)

    @app.post("/api/master/reports/<int:rid>")
    def m_report_settle(rid):
        """Settle a report: take the thing down ('hide') or leave it ('none')."""
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            r = conn.execute("SELECT * FROM gr_reports WHERE id=?", (rid,)).fetchone()
            if not r:
                return no("no such report", 404)
            action = "hidden" if d.get("action") == "hide" else "none"
            note = _txt(d.get("note"), 500) or None
            if action == "hidden":
                if r["what"] == "room":
                    # (by whose room it is: its owner may have changed its address since the report)
                    if r["owner_id"]:
                        conn.execute("UPDATE gr_accounts SET hidden_at=?, hidden_note=? WHERE id=?",
                                     (S._now(), note or REPORT_REASONS.get(r["reason"]), r["owner_id"]))
                    else:
                        conn.execute("UPDATE gr_accounts SET hidden_at=?, hidden_note=? WHERE handle=?",
                                     (S._now(), note or REPORT_REASONS.get(r["reason"]), r["ref"]))
                elif r["what"] == "record" and r["ref"].isdigit():
                    conn.execute("UPDATE gr_tracks SET status='hidden', review_note=?, reviewed_at=? WHERE id=?",
                                 (note or REPORT_REASONS.get(r["reason"]), S._now(), int(r["ref"])))
                elif r["what"] == "grupa" and r["ref"].isdigit():
                    conn.execute("UPDATE gr_grupai SET hidden_at=?, hidden_note=? WHERE id=?",
                                 (S._now(), note or REPORT_REASONS.get(r["reason"]), int(r["ref"])))
            conn.execute("UPDATE gr_reports SET status='done', action=?, resolved_note=?, resolved_at=? WHERE id=?",
                         (action, note, S._now(), rid))
            # the same thing reported again by others is settled with it
            conn.execute("UPDATE gr_reports SET status='done', action=?, resolved_note=?, resolved_at=?"
                         " WHERE status='open' AND what=? AND ref=?", (action, note, S._now(), r["what"], r["ref"]))
            conn.commit()
            S._event(conn, acct["id"], "master_report", {"report": rid, "action": action})
            return jsonify({"id": rid, "action": action})
        return signed_in(go, master=True)

    @app.post("/api/master/grupai/<int:gid>")
    def m_grupa_set(gid):
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            S._ensure_grupa_tables(conn)
            ensure(conn)
            conn.execute("UPDATE gr_grupai SET hidden_at=?, hidden_note=? WHERE id=?",
                         (S._now() if d.get("hidden") else None, _txt(d.get("note"), 300) or None, gid))
            conn.commit()
            return jsonify({"id": gid, "hidden": bool(d.get("hidden"))})
        return signed_in(go, master=True)

    @app.get("/api/master/feedback")
    def m_feedback():
        status = request.args.get("status") or "open"

        def go(conn, acct):
            where, params = ("", ()) if status == "all" else ("WHERE COALESCE(f.status,'open')=?", (status,))
            rows = conn.execute(
                "SELECT f.*, a.name AS a_name, a.handle AS a_handle FROM gr_feedback f"
                f" LEFT JOIN gr_accounts a ON a.id=f.account_id {where} ORDER BY f.at DESC LIMIT 500",
                params).fetchall()
            return jsonify({"feedback": [{
                "id": r["id"], "kind": r["kind"], "note": r["note"], "page": r["page"] or "",
                "at": r["at"], "status": r["status"] or "open", "done_at": r["done_at"],
                "by": {"name": r["a_name"], "handle": r["a_handle"]},
            } for r in rows]})
        return signed_in(go, master=True)

    @app.post("/api/master/feedback/<int:fid>")
    def m_feedback_set(fid):
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            done = d.get("status") == "done"
            conn.execute("UPDATE gr_feedback SET status=?, done_at=? WHERE id=?",
                         ("done" if done else "open", S._now() if done else None, fid))
            conn.commit()
            return jsonify({"id": fid, "status": "done" if done else "open"})
        return signed_in(go, master=True)

    @app.post("/api/master/version")
    def m_version():
        """Which release everyone should be on. An older one here is how a step
        back reaches everyone."""
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            v = {"version": _txt(d.get("version"), 40), "url": _txt(d.get("url"), 400),
                 "note": _txt(d.get("note"), 600), "at": S._now()}
            if v["url"] and not v["url"].startswith(("https://", "http://")):
                return no("the address should start with https://")
            set_setting(conn, "app_version", v)
            S._event(conn, acct["id"], "master_version", {"version": v["version"]})
            return jsonify(v)
        return signed_in(go, master=True)
