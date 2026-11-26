"""
gr_apply.py — applying for an account that is more than a listener's (the rooms
server's side; 2026-11-26).

Everyone starts as a listener, and a listener's account works at once (their room
can be public without anyone's say). An artist, label, record shop, venue,
experience creator or business account is asked for with an APPLICATION, from the
listener account, at any time. The master reads it and approves or rejects it, with
a note if they like; who decided, when and why is kept. Approved, the account
becomes that kind. Until then it stays a listener: it can't put records up for
sale or make event pages.

    interest         at sign-up a person may say what they are ("a venue"). It is
                     only a note on the account: the app uses it to show them the
                     way to the application.
    the form         FIELDS (asked of every kind) + EXTRA[kind] (asked of that kind
                     only). To ask something new, add a line to one of them: the
                     app draws the form from what `GET /api/apply` says.
    the tier         one price for now, per month, in pounds for an application
                     from the UK and in euro from anywhere else. The numbers are
                     in gr_settings ("tier"); until they are set the price reads
                     "£x" / "€x".
    statuses         an application is pending → approved | rejected (or withdrawn
                     by its owner). An account the master has paused is
                     "suspended". `status_of` gives the one word for an account.

An older app asks for a kind at sign-up with no form: that becomes an application
with nothing filled in, so the master sees every request in one place.
"""

import json
from contextlib import closing

from flask import jsonify, request

import gr_master

S = None          # the gr_server module, given in register()

# every kind that is applied for, in the order the form offers them (a kind in
# gr_server.KINDS_OFF is left out)
KINDS = ("artist", "label", "shop", "venue", "experience creator", "business", "digital artist")
NAMES = {"artist": "Artist", "label": "Record label", "shop": "Record shop", "venue": "Venue",
         "experience creator": "Experience creator", "business": "Business", "digital artist": "Digital artist"}
# one plain line on who each kind is for
FOR = {
    "artist": "You make music and want to sell or lend your own records.",
    "label": "You release other people's records.",
    "shop": "You sell records.",
    "venue": "You run a place where music happens.",
    "experience creator": "You put on music events in person and you are not a venue: a promoter, a DJ collective, a club night.",
    "business": "Your business works with music in another way.",
    "digital artist": "You make visual work for music.",
}
# what the account can do today that a listener's can't (only what is built)
MEANS = {
    "artist": "You can put your records up, for people to borrow and buy.",
    "label": "You can put records up, for people to borrow and buy.",
    "shop": "You can put records up, for people to borrow and buy.",
    "venue": "You can make event pages, shown in your room and in what is coming up.",
    "experience creator": "You can make event pages, shown in your room and in what is coming up.",
    "business": "",
    "digital artist": "You can show and sell your works.",
}
REGIONS = {"ie": "Ireland", "uk": "United Kingdom", "other": "Somewhere else"}
STATUSES = ("pending", "approved", "rejected", "withdrawn")

# The form. kind: text | long | email | region | links. `need`: must be filled in.
FIELDS = [
    {"key": "name", "label": "Name", "kind": "text", "need": True, "max": 120},
    {"key": "email", "label": "Contact email", "kind": "email", "need": True, "max": 254},
    {"key": "location", "label": "Where you are based", "kind": "text", "need": True, "max": 120},
    {"key": "region", "label": "Region", "kind": "region", "need": True, "max": 10},
    {"key": "links", "label": "Links to your work", "kind": "links", "need": True, "max": 2000},
    {"key": "about", "label": "About", "kind": "long", "need": True, "max": 4000},
]
# Questions for one kind only, in the same shape, e.g.
#   EXTRA["venue"] = [{"key": "capacity", "label": "Capacity", "kind": "text", "need": False, "max": 40}]
EXTRA = {k: [] for k in KINDS}


def kinds():
    return tuple(k for k in KINDS if k not in getattr(S, "KINDS_OFF", ()))


def fields_for(kind):
    return FIELDS + list(EXTRA.get(kind) or [])


# ---------- tables ----------

def ensure(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gr_applications(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            kind TEXT NOT NULL,
            fields TEXT NOT NULL DEFAULT '{}',     -- JSON: the form as it was sent
            region TEXT,                           -- ie | uk | other
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER REFERENCES gr_accounts(id),
            note TEXT,                             -- the master's, shown to the applicant
            bare INTEGER NOT NULL DEFAULT 0        -- from an older app: a kind and no form
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_applications ON gr_applications(status, created_at)")
    if "interest" not in {r[1] for r in conn.execute("PRAGMA table_info(gr_accounts)")}:
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN interest TEXT")
    conn.commit()


# ---------- the tier ----------

def tier(conn):
    t = gr_master.setting(conn, "tier", {}) or {}
    return {"gbp": t.get("gbp"), "eur": t.get("eur")}


def price_words(conn, region):
    """"£x a month" / "€x a month": pounds for the UK, euro for everywhere else;
    an x until the number is set."""
    t = tier(conn)
    sign, n = ("£", t["gbp"]) if region == "uk" else ("€", t["eur"])
    if n in (None, ""):
        return f"{sign}x a month"
    n = float(n)
    return f"{sign}{int(n) if n == int(n) else f'{n:.2f}'} a month"


def set_tier(conn, gbp=None, eur=None):
    def num(v):
        if v in (None, ""):
            return None
        v = float(v)
        if not 0 <= v <= 10000:
            raise ValueError("a price is between 0 and 10,000")
        return v
    try:
        t = {"gbp": num(gbp), "eur": num(eur)}
    except (TypeError, ValueError) as e:
        raise ValueError(str(e) if "between" in str(e) else "a price is a number")
    gr_master.set_setting(conn, "tier", t)
    return t


# ---------- applications ----------

def _clean(kind, raw):
    """The form as sent → (fields, None) or (None, words)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for f in fields_for(kind):
        v = raw.get(f["key"])
        if f["kind"] == "links":
            v = [str(x).strip()[:500] for x in (v if isinstance(v, list) else str(v or "").splitlines()) if str(x).strip()][:12]
            if any(not x.startswith(("https://", "http://")) for x in v):
                return None, "A link starts with https://"
        else:
            v = " ".join(str(v or "").split()) if f["kind"] != "long" else str(v or "").strip()
            v = v[:f.get("max") or 400]
            if f["kind"] == "email" and v and "@" not in v:
                return None, "That doesn't look like an email address."
            if f["kind"] == "region" and v and v not in REGIONS:
                return None, "Choose a region."
        if f.get("need") and not v:
            return None, f"{f['label']} is needed."
        out[f["key"]] = v
    return out, None


def row_json(conn, r, full=False):
    out = {"id": r["id"], "kind": r["kind"], "kind_name": NAMES.get(r["kind"], r["kind"]), "status": r["status"],
           "at": r["created_at"], "decided_at": r["decided_at"], "note": r["note"] or "",
           "region": r["region"] or "", "price": price_words(conn, r["region"]), "bare": bool(r["bare"])}
    if full:
        out["fields"] = json.loads(r["fields"] or "{}")
        out["form"] = fields_for(r["kind"])
        a = conn.execute("SELECT name, handle, kind, created_at FROM gr_accounts WHERE id=?", (r["account_id"],)).fetchone()
        out["by"] = {"id": r["account_id"], "name": a["name"] if a else "", "handle": a["handle"] if a else "",
                     "kind": a["kind"] if a else "", "since": a["created_at"] if a else ""}
        if r["decided_by"]:
            m = conn.execute("SELECT name, handle FROM gr_accounts WHERE id=?", (r["decided_by"],)).fetchone()
            out["decided_by"] = {"name": m["name"], "handle": m["handle"]} if m else None
    return out


def latest(conn, account_id):
    return conn.execute("SELECT * FROM gr_applications WHERE account_id=? ORDER BY id DESC LIMIT 1",
                        (account_id,)).fetchone()


def status_of(conn, acct):
    """One word for where an account stands: suspended (the master paused it) ·
    pending / rejected (its latest application) · approved (a listener, or a kind
    the master said yes to)."""
    if gr_master.is_paused(acct):
        return "suspended"
    last = latest(conn, acct["id"])
    if last and last["status"] in ("pending", "rejected") and acct["kind"] == "listener":
        return last["status"]
    return "approved"


def me_json(conn, acct):
    ensure(conn)
    last = latest(conn, acct["id"])
    interest = acct["interest"] if "interest" in acct.keys() else None
    return {"status": status_of(conn, acct), "interest": interest if interest in kinds() else "",
            "application": row_json(conn, last) if last else None,
            "can_apply": acct["kind"] == "listener" and not (last and last["status"] == "pending")}


def from_old_app(conn, account_id, kind):
    """An older app asked for a kind at sign-up: an application with no form."""
    ensure(conn)
    conn.execute("INSERT INTO gr_applications(account_id, kind, created_at, bare) VALUES(?,?,?,1)",
                 (account_id, kind, S._now()))


def decide(conn, app_row, master, yes, note=None):
    """Approve or reject one application. Approved, the account becomes that kind."""
    note = (str(note or "").strip()[:1000]) or None
    conn.execute("UPDATE gr_applications SET status=?, decided_at=?, decided_by=?, note=? WHERE id=?",
                 ("approved" if yes else "rejected", S._now(), master["id"], note, app_row["id"]))
    if yes:
        conn.execute("UPDATE gr_accounts SET kind=?, kind_requested=NULL WHERE id=?",
                     (app_row["kind"], app_row["account_id"]))
    else:
        conn.execute("UPDATE gr_accounts SET kind_requested=NULL WHERE id=?", (app_row["account_id"],))
    conn.commit()
    S._event(conn, master["id"], "master_application",
             {"application": app_row["id"], "account": app_row["account_id"], "kind": app_row["kind"],
              "decision": "approved" if yes else "rejected", "note": note or ""})


def settle_for_account(conn, account_id, master, yes, note=None):
    """The master answered from the Accounts list: the waiting application (if
    there is one) is settled the same way, so the record of who decided is whole."""
    ensure(conn)
    row = conn.execute("SELECT * FROM gr_applications WHERE account_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                       (account_id,)).fetchone()
    if row:
        decide(conn, row, master, yes, note)
    return row


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
            if master:
                import gr_signin
                if not gr_master.is_master(acct):
                    return no("only the master account can do that", 403, master=False)
                if not gr_master.master_here():
                    return no("the master's page works only on the Mac the server runs on", 403, master=False)
                stop = gr_signin.need_two_factor(conn, acct)
                if stop:
                    return stop
            return fn(conn, acct)

    def body():
        return request.get_json(force=True, silent=True) or {}

    @app.get("/api/apply")
    def apply_form():
        """Everything the application page draws: the kinds, the form for each,
        the price, and where this account's own application stands."""
        def go(conn, acct):
            return jsonify({
                "kinds": [{"key": k, "name": NAMES[k], "for": FOR[k], "means": MEANS.get(k, ""), "fields": fields_for(k)} for k in kinds()],
                "regions": [{"key": k, "name": v, "price": price_words(conn, k)} for k, v in REGIONS.items()],
                "me": dict(me_json(conn, acct), kind=acct["kind"], name=acct["name"], email=acct["email"] or ""),
                "history": [row_json(conn, r) for r in conn.execute(
                    "SELECT * FROM gr_applications WHERE account_id=? ORDER BY id DESC LIMIT 10", (acct["id"],))],
            })
        return signed_in(go)

    @app.post("/api/apply")
    def apply_send():
        d = body()
        kind = str(d.get("kind") or "").strip().lower()

        def go(conn, acct):
            if kind not in kinds():
                return no("Choose what you are applying as.")
            if acct["kind"] != "listener":
                return no(f"This account is already more than a listener's ({NAMES.get(acct['kind'], acct['kind'])}).", 409)
            if conn.execute("SELECT 1 FROM gr_applications WHERE account_id=? AND status='pending'",
                            (acct["id"],)).fetchone():
                return no("Your application is already waiting.", 409)
            if not gr_master.rate_ok(f"apply:{acct['id']}", 5, 86400):
                return no("That's a lot of applications in one day. Try again tomorrow.", 429)
            fields, why = _clean(kind, d.get("fields"))
            if why:
                return no(why)
            cur = conn.execute("INSERT INTO gr_applications(account_id, kind, fields, region, created_at) VALUES(?,?,?,?,?)",
                               (acct["id"], kind, json.dumps(fields), fields.get("region"), S._now()))
            conn.execute("UPDATE gr_accounts SET kind_requested=? WHERE id=?", (kind, acct["id"]))
            conn.commit()
            S._event(conn, acct["id"], "application", {"application": cur.lastrowid, "kind": kind})
            acct = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()
            return jsonify(me_json(conn, acct))
        return signed_in(go)

    @app.post("/api/apply/withdraw")
    def apply_withdraw():
        def go(conn, acct):
            conn.execute("UPDATE gr_applications SET status='withdrawn', decided_at=? WHERE account_id=? AND status='pending'",
                         (S._now(), acct["id"]))
            conn.execute("UPDATE gr_accounts SET kind_requested=NULL WHERE id=?", (acct["id"],))
            conn.commit()
            acct = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()
            return jsonify(me_json(conn, acct))
        return signed_in(go)

    @app.post("/api/me/interest")
    def me_interest():
        """What a person says they are (or '' for a listener): a note, nothing more."""
        d = body()
        kind = str(d.get("kind") or "").strip().lower()

        def go(conn, acct):
            conn.execute("UPDATE gr_accounts SET interest=? WHERE id=?", (kind if kind in kinds() else None, acct["id"]))
            conn.commit()
            acct = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()
            return jsonify(me_json(conn, acct))
        return signed_in(go)

    # ── the master: the queue ──
    @app.get("/api/master/applications")
    def m_applications():
        status = request.args.get("status") or "pending"

        def go(conn, acct):
            where, params = ("", ()) if status == "all" else ("WHERE status=?", (status,))
            rows = conn.execute(f"SELECT * FROM gr_applications {where} ORDER BY"
                                " CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC LIMIT 500", params).fetchall()
            return jsonify({"applications": [row_json(conn, r, full=True) for r in rows], "tier": tier(conn)})
        return signed_in(go, master=True)

    @app.post("/api/master/applications/<int:pid>")
    def m_application_decide(pid):
        d = body()

        def go(conn, acct):
            r = conn.execute("SELECT * FROM gr_applications WHERE id=?", (pid,)).fetchone()
            if not r:
                return no("no such application", 404)
            if d.get("decision") not in ("approve", "reject"):
                return no("approve or reject")
            if r["status"] != "pending":
                return no("That one is already settled.", 409)
            decide(conn, r, acct, d["decision"] == "approve", d.get("note"))
            r = conn.execute("SELECT * FROM gr_applications WHERE id=?", (pid,)).fetchone()
            return jsonify({"application": row_json(conn, r, full=True)})
        return signed_in(go, master=True)

    @app.post("/api/master/tier")
    def m_tier():
        """The one tier's price a month: pounds (UK) and euro (everywhere else)."""
        d = body()

        def go(conn, acct):
            try:
                t = set_tier(conn, d.get("gbp"), d.get("eur"))
            except ValueError as e:
                return no(str(e))
            S._event(conn, acct["id"], "master_tier", t)
            return jsonify({"tier": t})
        return signed_in(go, master=True)
