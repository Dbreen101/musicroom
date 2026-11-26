"""
gr_behalf.py — letting another account manage yours (the rooms server's side;
2026-11-26).

An artist can let another account — their label, a manager — look after their
artist account, and can take that back at any time. Nobody shares a password: the
other person signs in as themselves, on their own laptop, and says on each request
whose account they are working on (the header `X-GR-For: <the artist's handle>`).

    scopes     "records"  the artist's records: put up, change, take down
               "full"     the records, the public room (words, designs, pictures)
                          and event pages
               Neither reaches the artist's sign-in, laptops, credits, borrowed or
               bought records, applications, or who else may manage the account.
    the check  `stand_in` is asked by gr_server._auth for every request that
               carries the header. Only the routes listed in PATHS can be used
               for someone else; anything else is refused, never quietly done on
               the asker's own account.
    the log    every change made for someone else is written to the activity log
               under the ARTIST's account as "behalf", with who did it, what was
               asked and how it was answered.
"""

from contextlib import closing

from flask import g, jsonify, request

S = None          # the gr_server module, given in register()

OWNER_KINDS = ("artist",)       # who can let another account manage theirs
SCOPES = {
    "records": "Manage releases",
    "full": "Full access",
}
# the routes each scope opens (the start of the path)
PATHS = {
    "records": ("/api/my/records",),
    "full": ("/api/my/records", "/api/my/room", "/api/my/happenings"),
}
HEADER = "X-GR-For"
MOST = 10                       # accounts one artist may let in


def ensure(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gr_behalf(
            id INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES gr_accounts(id),      -- whose account it is
            delegate_id INTEGER NOT NULL REFERENCES gr_accounts(id),   -- who may manage it
            scope TEXT NOT NULL,                                       -- a key of SCOPES
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            revoked_by INTEGER
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_behalf ON gr_behalf(delegate_id, revoked_at)")
    conn.commit()


def grant_of(conn, owner_id, delegate_id):
    return conn.execute("SELECT * FROM gr_behalf WHERE owner_id=? AND delegate_id=? AND revoked_at IS NULL"
                        " ORDER BY id DESC LIMIT 1", (owner_id, delegate_id)).fetchone()


def _covers(scope, path):
    return any(path == p or path.startswith(p + "/") for p in PATHS.get(scope, ()))


def stand_in(conn, acct, dev, handle):
    """The request says it is made for `handle`. → that account, when the signed-in
    one may do THIS for them; else None, with the reason left in g.gr_refused."""
    ensure(conn)
    owner = conn.execute("SELECT * FROM gr_accounts WHERE handle=?", ((handle or "").strip().lower(),)).fetchone()
    grant = grant_of(conn, owner["id"], acct["id"]) if owner else None
    if not grant or owner["disabled_at"]:
        g.gr_refused = "You don't manage that account."
        return None
    if not _covers(grant["scope"], request.path):
        g.gr_refused = "That isn't part of what you may manage for them."
        return None
    g.gr_behalf = {"owner": owner["id"], "by": acct["id"], "by_handle": acct["handle"], "by_name": acct["name"],
                   "scope": grant["scope"], "device": dev["id"]}
    return owner


def _row(conn, r, side):
    other = conn.execute("SELECT name, handle, kind FROM gr_accounts WHERE id=?",
                         (r["delegate_id"] if side == "given" else r["owner_id"],)).fetchone()
    return {"id": r["id"], "scope": r["scope"], "scope_name": SCOPES.get(r["scope"], r["scope"]), "since": r["granted_at"],
            "name": other["name"] if other else "", "handle": other["handle"] if other else "",
            "kind": other["kind"] if other else ""}


def me_json(conn, acct):
    """For /api/me: whose accounts this one may manage (the app's switch)."""
    ensure(conn)
    return [_row(conn, r, "got") for r in conn.execute(
        "SELECT b.* FROM gr_behalf b JOIN gr_accounts o ON o.id=b.owner_id"
        " WHERE b.delegate_id=? AND b.revoked_at IS NULL AND o.disabled_at IS NULL ORDER BY b.id", (acct["id"],))]


def register(app, server):
    global S
    S = server

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    def signed_in(fn):
        with closing(S.db()) as conn:
            ensure(conn)
            acct, dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            return fn(conn, acct)

    @app.after_request
    def _write_down(resp):
        """A change made for someone else goes in their activity log."""
        b = getattr(g, "gr_behalf", None)
        if b and request.method != "GET":
            try:
                with closing(S.db()) as conn:
                    S._event(conn, b["owner"], "behalf",
                             {"by": b["by"], "by_handle": b["by_handle"], "by_name": b["by_name"], "for": b["owner"],
                              "scope": b["scope"], "did": f"{request.method} {request.path}", "answer": resp.status_code},
                             b["device"])
            except Exception as e:
                print(f"[behalf] not written down: {type(e).__name__}")
        return resp

    @app.get("/api/my/behalf")
    def my_behalf():
        def go(conn, acct):
            given = conn.execute("SELECT * FROM gr_behalf WHERE owner_id=? AND revoked_at IS NULL ORDER BY id", (acct["id"],))
            log = conn.execute("SELECT at, data FROM gr_events WHERE account_id=? AND kind='behalf' ORDER BY id DESC LIMIT 40",
                               (acct["id"],)).fetchall()
            import json
            return jsonify({"can_give": acct["kind"] in OWNER_KINDS,
                            "scopes": [{"key": k, "name": v} for k, v in SCOPES.items()],
                            "given": [_row(conn, r, "given") for r in given],
                            "got": me_json(conn, acct),
                            "log": [dict(json.loads(e["data"] or "{}"), at=e["at"]) for e in log]})
        return signed_in(go)

    @app.post("/api/my/behalf")
    def my_behalf_give():
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            if acct["kind"] not in OWNER_KINDS:
                return no("Only an artist account can let another account manage it.", 403)
            scope = d.get("scope") if d.get("scope") in SCOPES else None
            if not scope:
                return no("Choose what they may manage.")
            other = conn.execute("SELECT * FROM gr_accounts WHERE handle=?",
                                 (S._slug(str(d.get("handle") or "").lstrip("@")),)).fetchone()
            if not other or other["disabled_at"]:
                return no("No account here has that address.", 404)
            if other["id"] == acct["id"]:
                return no("That is your own account.")
            had = grant_of(conn, acct["id"], other["id"])
            if had and had["scope"] == scope:
                return my_behalf()
            if not had and conn.execute("SELECT COUNT(*) FROM gr_behalf WHERE owner_id=? AND revoked_at IS NULL",
                                        (acct["id"],)).fetchone()[0] >= MOST:
                return no(f"An account lets {MOST} others in at most.", 409)
            if had:
                conn.execute("UPDATE gr_behalf SET revoked_at=?, revoked_by=? WHERE id=?", (S._now(), acct["id"], had["id"]))
            conn.execute("INSERT INTO gr_behalf(owner_id, delegate_id, scope, granted_at) VALUES(?,?,?,?)",
                         (acct["id"], other["id"], scope, S._now()))
            conn.commit()
            S._event(conn, acct["id"], "behalf_given", {"to": other["id"], "to_handle": other["handle"], "scope": scope})
            return my_behalf()
        return signed_in(go)

    @app.delete("/api/my/behalf/<int:bid>")
    def my_behalf_take_back(bid):
        """The artist takes it back, or the other account gives it up."""
        def go(conn, acct):
            r = conn.execute("SELECT * FROM gr_behalf WHERE id=? AND revoked_at IS NULL AND (owner_id=? OR delegate_id=?)",
                             (bid, acct["id"], acct["id"])).fetchone()
            if not r:
                return no("That isn't there any more.", 404)
            conn.execute("UPDATE gr_behalf SET revoked_at=?, revoked_by=? WHERE id=?", (S._now(), acct["id"], bid))
            conn.commit()
            S._event(conn, r["owner_id"], "behalf_taken_back", {"from": r["delegate_id"], "by": acct["id"]})
            return my_behalf()
        return signed_in(go)
