"""
gr_signin.py — how an account signs in, and what keeps it one person's (the rooms
server's side; 2026-11-26).

    email + password   a new account gives an email (one account per email) and a
                       password. The password is kept only as a salted hash
                       (werkzeug's scrypt). `POST /api/login` signs a laptop in.
                       Accounts from before this keep their account code until
                       they set a password in Settings; after that the code no
                       longer opens the account.
    laptops            an account registers a set number of laptops (`devices`),
                       and only so many may take music at the same time
                       (`at_once`): borrowing, fetching a borrowed file and the
                       shop's one play are refused on a second laptop while
                       another has just been used. A laptop stays signed in until
                       it is signed out. Every sign-in is written down
                       (gr_signins), new laptops marked.
    two-factor         six numbers from an authenticator app (TOTP, RFC 6238).
                       Optional for accounts that publish or sell, with a rule to
                       require it; required for the master. Switching it on signs
                       the account's other laptops out, so every laptop that is
                       signed in has given a code.
    email codes        a code sent to the account's email: to prove the email is
                       theirs, and to confirm a sign-in on a laptop the account
                       has not used before. Both need a mail server (MR_SMTP_*)
                       and the `email_check` rule; without them nothing is sent
                       and nothing is asked.
    the rules          every number and switch above is one entry of RULES, kept
                       in gr_settings ("account_rules") and changed from the
                       master page or `gr_server.py rules key=value`.

Nothing here writes a password, a code or a sign-in token to the activity log.
gr_server hands this module itself at the bottom, like gr_master.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time
from contextlib import closing

from flask import jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import gr_master

S = None          # the gr_server module, given in register()

RULES = {
    "devices": None,            # laptops one account may register (None = gr_server.MAX_DEVICES)
    "at_once": 1,               # laptops that may take music at the same time
    "at_once_window_s": 120,    # …"the same time" = another laptop took music this many seconds ago
    "need_password": False,     # a new account must give an email and a password
    "email_check": False,       # confirm a sign-in on a new laptop by a code sent to the account's email
    "maker_2fa": "optional",    # two-factor for accounts that publish or sell: off | optional | required
    "master_2fa": "required",   # two-factor for the master: off | optional | required
    "login_tries": 8,           # wrong passwords for one email before a wait
    "login_window_s": 600,
}
_CHOICES = {"maker_2fa": ("off", "optional", "required"), "master_2fa": ("off", "optional", "required")}
_BOUNDS = {"devices": (1, 20), "at_once": (1, 20), "at_once_window_s": (10, 3600),
           "login_tries": (3, 100), "login_window_s": (60, 86400)}

PASSWORD_MIN, PASSWORD_MAX = 10, 256
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_LIFE_S = 600           # an emailed code works for ten minutes
CODE_TRIES = 5
WORDS = {
    "login": "That email and password don't match an account here.",
    "wait": "Too many tries. Wait ten minutes.",
    "has_password": "This account signs in with its email and password now.",
    "need_password": "An email and a password are needed. If this app has no place for them, update it.",
    "email_bad": "That doesn't look like an email address.",
    "email_taken": "That email already has an account. Sign in instead.",
    "password_short": f"A password needs at least {PASSWORD_MIN} characters.",
    "password_long": "That password is too long.",
    "password_same": "A password can't be your email or your name.",
    "otp_need": "Enter the six numbers from your authenticator app.",
    "otp_wrong": "Those six numbers aren't right. Try the next ones.",
    "otp_setup": "Set up two-factor first, on your Account page.",
    "otp_not_for": "Two-factor is for accounts that publish or sell.",
    "otp_must": "This account must keep two-factor on.",
    "in_use": "This account is in use on another laptop. Wait a couple of minutes, or sign that laptop out in Settings.",
    "mail_off": "Email checks are not switched on here yet.",
    "code_need": "A code was sent to your email. Enter it to finish signing in.",
    "code_wrong": "That code isn't right, or it is too old.",
}


# ---------- tables ----------

def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


_seen = set()


def ensure(conn):
    """Columns and tables this file needs (asked once a run for each database)."""
    key = S.db_path() if S else None
    if key in _seen:
        return
    a = _cols(conn, "gr_accounts")
    for col, decl in (("email", "TEXT"), ("email_fold", "TEXT"), ("email_verified_at", "TEXT"),
                      ("password_hash", "TEXT"), ("password_at", "TEXT"),
                      ("totp_secret", "TEXT"), ("totp_pending", "TEXT"), ("totp_last", "INTEGER"),
                      ("totp_at", "TEXT")):
        if col not in a:
            conn.execute(f"ALTER TABLE gr_accounts ADD COLUMN {col} {decl}")
    d = _cols(conn, "gr_devices")
    for col, decl in (("twofa_at", "TEXT"), ("used_at", "REAL"), ("address", "TEXT")):
        if col not in d:
            conn.execute(f"ALTER TABLE gr_devices ADD COLUMN {col} {decl}")
    conn.executescript(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_gr_accounts_email ON gr_accounts(email_fold)
            WHERE email_fold IS NOT NULL;
        -- every sign-in, and every refused one that named a real account
        CREATE TABLE IF NOT EXISTS gr_signins(
            id INTEGER PRIMARY KEY,
            account_id INTEGER REFERENCES gr_accounts(id),
            device_id INTEGER,
            device_name TEXT,
            address TEXT,                 -- where it came from
            how TEXT NOT NULL,            -- password | code | signup
            new_device INTEGER NOT NULL DEFAULT 0,
            ok INTEGER NOT NULL DEFAULT 1,
            note TEXT,                    -- why not, when it was refused
            at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gr_signins_acct ON gr_signins(account_id, at);
        -- codes sent by email (only their hash is kept)
        CREATE TABLE IF NOT EXISTS gr_email_codes(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            purpose TEXT NOT NULL,        -- verify | signin
            fingerprint TEXT,             -- the laptop a sign-in code is for
            code_hash TEXT NOT NULL,
            tries INTEGER NOT NULL DEFAULT 0,
            made REAL NOT NULL,
            used_at TEXT
        );
        """
    )
    conn.commit()
    if key:
        _seen.add(key)


# ---------- the rules ----------

def rules(conn):
    saved = gr_master.setting(conn, "account_rules", {}) or {}
    out = dict(RULES)
    out.update({k: v for k, v in saved.items() if k in RULES})
    if out["devices"] is None:
        out["devices"] = S.MAX_DEVICES
    return out


def set_rules(conn, changes):
    """Change some rules. → the rules, or raises ValueError with words for a person."""
    saved = gr_master.setting(conn, "account_rules", {}) or {}
    for k, v in (changes or {}).items():
        if k not in RULES:
            raise ValueError(f"there is no rule called {k}")
        if k in _CHOICES:
            if v not in _CHOICES[k]:
                raise ValueError(f"{k} is one of: {', '.join(_CHOICES[k])}")
        elif k in _BOUNDS:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} is a whole number")
            lo, hi = _BOUNDS[k]
            if not lo <= v <= hi:
                raise ValueError(f"{k} is between {lo} and {hi}")
        else:
            v = v in (True, 1, "1", "on", "true", "yes")
        saved[k] = v
    gr_master.set_setting(conn, "account_rules", saved)
    return rules(conn)


def set_rules_here(changes):
    """The same, on this server's own database (Terminal and tests)."""
    with closing(S.db()) as conn:
        S.init_db(conn)
        return set_rules(conn, changes)


# ---------- emails and passwords ----------

def fold_email(v):
    return " ".join(str(v or "").split()).lower()[:254]


def email_problem(conn, email, account_id=None):
    """Words when this email can't be used, else None."""
    e = fold_email(email)
    if not EMAIL_RE.match(e):
        return WORDS["email_bad"]
    row = conn.execute("SELECT id FROM gr_accounts WHERE email_fold=?", (e,)).fetchone()
    if row and row["id"] != account_id:
        return WORDS["email_taken"]
    return None


def password_problem(password, *not_these):
    p = str(password or "")
    if len(p) < PASSWORD_MIN:
        return WORDS["password_short"]
    if len(p) > PASSWORD_MAX:
        return WORDS["password_long"]
    if p.strip().lower() in {str(x or "").strip().lower() for x in not_these if x}:
        return WORDS["password_same"]
    return None


def set_password(conn, account_id, password):
    conn.execute("UPDATE gr_accounts SET password_hash=?, password_at=? WHERE id=?",
                 (generate_password_hash(str(password)), S._now(), account_id))


def set_email(conn, account_id, email):
    conn.execute("UPDATE gr_accounts SET email=?, email_fold=?, email_verified_at=NULL WHERE id=?",
                 (" ".join(str(email).split())[:254], fold_email(email), account_id))


_NOBODY = generate_password_hash(secrets.token_hex(16))     # checked against when no account matches


def password_ok(acct, password):
    """Does this password open this account? (Takes as long when there is no account.)"""
    h = acct["password_hash"] if acct is not None and _has(acct, "password_hash") else None
    return check_password_hash(h or _NOBODY, str(password or "")) and bool(h)


def _has(row, key):
    try:
        return key in row.keys()
    except Exception:
        return False


def signup_fields(conn, data, name):
    """What a sign-up says about email and password. → (email, password, None), or
    (None, None, (answer, status)) when it can't go on."""
    email, password = fold_email(data.get("email")), data.get("password") or ""
    if not email and not password:
        if rules(conn)["need_password"]:
            return None, None, (jsonify({"error": WORDS["need_password"], "need_password": True}), 400)
        return "", "", None
    why = email_problem(conn, email) or password_problem(password, email, name)
    if why:
        return None, None, (jsonify({"error": why, "need_password": True}), 409 if why == WORDS["email_taken"] else 400)
    return " ".join(str(data.get("email")).split())[:254], password, None


# ---------- two-factor (TOTP, RFC 6238: SHA-1, six digits, thirty seconds) ----------

def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def totp(secret, step):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(step)), hashlib.sha1).digest()
    at = mac[-1] & 15
    return f"{(struct.unpack('>I', mac[at:at + 4])[0] & 0x7fffffff) % 1000000:06d}"


def totp_step(given, secret, after=None, now=None):
    """The time step this code belongs to (now, or the one either side), or None.
    A step at or before `after` is refused: a code works once."""
    code = "".join(ch for ch in str(given or "") if ch.isdigit())
    if len(code) != 6 or not secret:
        return None
    here = int((now if now is not None else time.time()) // 30)
    for step in (here, here - 1, here + 1):
        if hmac.compare_digest(totp(secret, step), code) and (after is None or step > after):
            return step
    return None


def otp_link(secret, who):
    from urllib.parse import quote
    return f"otpauth://totp/{quote('Music Room:' + who)}?secret={secret}&issuer={quote('Music Room')}"


def two_factor_rule(conn, acct):
    """off | optional | required, for this account."""
    r = rules(conn)
    if gr_master.is_master(acct):
        return r["master_2fa"]
    return r["maker_2fa"] if acct["kind"] != "listener" else "off"


def need_two_factor(conn, acct):
    """Before the master's routes and before publishing: None, or the refusal
    when this account must have two-factor and has not set it up."""
    if two_factor_rule(conn, acct) == "required" and not acct["totp_secret"]:
        return jsonify({"error": WORDS["otp_setup"], "need_2fa": "setup"}), 403
    return None


def _use_otp(conn, acct, given):
    """True when `given` is this account's next good code (and it is then spent)."""
    step = totp_step(given, acct["totp_secret"], acct["totp_last"])
    if step is None:
        return False
    conn.execute("UPDATE gr_accounts SET totp_last=? WHERE id=?", (step, acct["id"]))
    return True


# ---------- codes by email (asleep until there is a mail server) ----------

def mail_ready():
    return bool(os.environ.get("MR_SMTP_HOST"))


def send_mail(to, subject, body):
    """One plain email through the server named in MR_SMTP_HOST / _PORT / _USER /
    _PASS / _FROM. → True when it was handed over."""
    if not mail_ready():
        return False
    import smtplib
    from email.message import EmailMessage
    host, port = os.environ["MR_SMTP_HOST"], int(os.environ.get("MR_SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["From"] = os.environ.get("MR_SMTP_FROM") or os.environ.get("MR_SMTP_USER") or "musicroom@localhost"
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    try:
        with (smtplib.SMTP_SSL(host, port, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)) as s:
            if port != 465:
                s.starttls()
            if os.environ.get("MR_SMTP_USER"):
                s.login(os.environ["MR_SMTP_USER"], os.environ.get("MR_SMTP_PASS") or "")
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"[mail] not sent: {type(e).__name__}")
        return False


def _code_hash(row_salt, code):
    return hashlib.sha256(f"{row_salt}:{code}".encode("utf-8")).hexdigest()


def email_code_send(conn, acct, purpose, fingerprint=None):
    """Make a six-number code, keep its hash, send it. → True when it was sent."""
    if not mail_ready() or not acct["email"]:
        return False
    code = f"{secrets.randbelow(1000000):06d}"
    salt = secrets.token_hex(8)
    conn.execute("DELETE FROM gr_email_codes WHERE account_id=? AND purpose=?", (acct["id"], purpose))
    conn.execute("INSERT INTO gr_email_codes(account_id, purpose, fingerprint, code_hash, made) VALUES(?,?,?,?,?)",
                 (acct["id"], purpose, fingerprint, salt + ":" + _code_hash(salt, code), time.time()))
    conn.commit()
    return send_mail(acct["email"], "Your Music Room code",
                     f"{code}\n\nThis code works for ten minutes. If you didn't ask for it, ignore this email.")


def email_code_ok(conn, acct, purpose, given, fingerprint=None):
    row = conn.execute("SELECT * FROM gr_email_codes WHERE account_id=? AND purpose=? AND used_at IS NULL"
                       " ORDER BY id DESC LIMIT 1", (acct["id"], purpose)).fetchone()
    code = "".join(ch for ch in str(given or "") if ch.isdigit())
    if not row or time.time() - row["made"] > CODE_LIFE_S or row["tries"] >= CODE_TRIES:
        return False
    if purpose == "signin" and (row["fingerprint"] or "") != (fingerprint or ""):
        return False
    salt, want = row["code_hash"].split(":", 1)
    if not hmac.compare_digest(_code_hash(salt, code), want):
        conn.execute("UPDATE gr_email_codes SET tries=tries+1 WHERE id=?", (row["id"],))
        conn.commit()
        return False
    conn.execute("UPDATE gr_email_codes SET used_at=? WHERE id=?", (S._now(), row["id"]))
    return True


# ---------- signing a laptop in ----------

def _note(conn, acct_id, how, ok=True, device_id=None, device_name=None, new=False, note=None):
    conn.execute("INSERT INTO gr_signins(account_id, device_id, device_name, address, how, new_device, ok, note, at)"
                 " VALUES(?,?,?,?,?,?,?,?,?)",
                 (acct_id, device_id, (device_name or "")[:80] or None, gr_master.asker(), how,
                  1 if new else 0, 1 if ok else 0, note, S._now()))
    conn.commit()


def sign_in_device(conn, acct, fingerprint, device_name, how, data=None):
    """Sign this laptop in to this account, whose secret (password or account
    code) has already been checked. → (token, None), or (None, (answer, status)).

    A laptop the account already uses gets its sign-in back. A new one has to fit
    under the limit, give the two-factor numbers if the account has them, and —
    when email checks are on — the code sent to the account's email."""
    data = data or {}
    ensure(conn)
    if gr_master.is_paused(acct):
        note = (acct["disabled_note"] or "").strip()
        return None, (jsonify({"error": "This account is paused." + (" " + note if note else ""), "paused": True}), 403)
    dev = conn.execute("SELECT * FROM gr_devices WHERE account_id=? AND fingerprint=?",
                       (acct["id"], fingerprint)).fetchone()
    if dev:
        conn.execute("UPDATE gr_devices SET address=? WHERE id=?", (gr_master.asker(), dev["id"]))
        _note(conn, acct["id"], how, device_id=dev["id"], device_name=device_name)
        return dev["token"], None
    r = rules(conn)
    count = conn.execute("SELECT COUNT(*) FROM gr_devices WHERE account_id=?", (acct["id"],)).fetchone()[0]
    if how != "signup" and count >= r["devices"]:
        _note(conn, acct["id"], how, ok=False, device_name=device_name, new=True, note="devices full")
        return None, (jsonify({"error": f"this account already has {r['devices']} devices", "devices_full": True}), 403)
    passed = False
    if how != "signup" and acct["totp_secret"]:
        if not data.get("otp"):
            return None, (jsonify({"error": WORDS["otp_need"], "need_2fa": True}), 401)
        if not _use_otp(conn, acct, data.get("otp")):
            _note(conn, acct["id"], how, ok=False, device_name=device_name, new=True, note="two-factor wrong")
            return None, (jsonify({"error": WORDS["otp_wrong"], "need_2fa": True}), 403)
        passed = True
    if how != "signup" and r["email_check"] and mail_ready() and acct["email"]:
        if not data.get("email_code"):
            email_code_send(conn, acct, "signin", fingerprint)
            return None, (jsonify({"error": WORDS["code_need"], "need_email_code": True}), 401)
        if not email_code_ok(conn, acct, "signin", data.get("email_code"), fingerprint):
            _note(conn, acct["id"], how, ok=False, device_name=device_name, new=True, note="email code wrong")
            return None, (jsonify({"error": WORDS["code_wrong"], "need_email_code": True}), 403)
        conn.execute("UPDATE gr_accounts SET email_verified_at=COALESCE(email_verified_at, ?) WHERE id=?",
                     (S._now(), acct["id"]))
    token = secrets.token_hex(24)
    cur = conn.execute(
        "INSERT INTO gr_devices(account_id, name, fingerprint, token, created_at, last_seen, twofa_at, address)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (acct["id"], device_name, fingerprint, token, S._now(), S._now(), S._now() if passed else None,
         gr_master.asker()))
    conn.commit()
    _note(conn, acct["id"], how, device_id=cur.lastrowid, device_name=device_name, new=True)
    if how != "signup":
        S._event(conn, acct["id"], "new_device", {"device": device_name, "how": how, "from": gr_master.asker()},
                 cur.lastrowid)
    return token, None


def one_at_a_time(conn, acct, dev):
    """Before music is handed to a laptop: None, or the refusal when the account's
    other laptops have just been taking music (more of them than `at_once`)."""
    ensure(conn)
    r = rules(conn)
    since = time.time() - r["at_once_window_s"]
    busy = conn.execute("SELECT COUNT(*) FROM gr_devices WHERE account_id=? AND id!=? AND COALESCE(used_at,0)>?",
                        (acct["id"], dev["id"], since)).fetchone()[0]
    if busy >= r["at_once"]:
        return jsonify({"error": WORDS["in_use"], "in_use": True}), 409
    conn.execute("UPDATE gr_devices SET used_at=? WHERE id=?", (time.time(), dev["id"]))
    conn.commit()
    return None


# ---------- what the routes say ----------

def me_json(conn, acct):
    """The part of /api/me about signing in (no secrets)."""
    ensure(conn)
    acct = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()
    rule = two_factor_rule(conn, acct)
    return {"email": acct["email"] or "", "email_verified": bool(acct["email_verified_at"]),
            "has_password": bool(acct["password_hash"]),
            "two_factor": {"on": bool(acct["totp_secret"]), "rule": rule,
                           "missing": rule == "required" and not acct["totp_secret"]}}


def security_json(conn, acct, dev):
    r = rules(conn)
    out = me_json(conn, acct)
    out["devices"] = [{"id": d["id"], "name": d["name"] or "laptop", "since": d["created_at"],
                       "last_seen": d["last_seen"], "this": d["id"] == dev["id"]}
                      for d in conn.execute("SELECT * FROM gr_devices WHERE account_id=? ORDER BY id", (acct["id"],))]
    out["limits"] = {"devices": r["devices"], "at_once": r["at_once"]}
    out["signins"] = [{"at": s["at"], "device": s["device_name"] or "", "how": s["how"], "new": bool(s["new_device"]),
                       "ok": bool(s["ok"]), "note": s["note"] or ""}
                      for s in conn.execute("SELECT * FROM gr_signins WHERE account_id=? ORDER BY id DESC LIMIT 20",
                                            (acct["id"],))]
    out["email_checks"] = bool(r["email_check"] and mail_ready())
    return out


def temporary_password(conn, account_id):
    """A new password for an account that has an email, every laptop signed out.
    → the password (shown once), or raises ValueError."""
    a = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (account_id,)).fetchone()
    if not a:
        raise ValueError("no such account")
    if not a["email_fold"]:
        raise ValueError("This account has no email yet: it signs in with its account code.")
    new = "-".join(secrets.token_hex(3) for _ in range(4))
    set_password(conn, account_id, new)
    conn.execute("DELETE FROM gr_devices WHERE account_id=?", (account_id,))
    conn.commit()
    return new


def two_factor_off(conn, account_id):
    conn.execute("UPDATE gr_accounts SET totp_secret=NULL, totp_pending=NULL, totp_last=NULL, totp_at=NULL WHERE id=?",
                 (account_id,))
    conn.execute("UPDATE gr_devices SET twofa_at=NULL WHERE account_id=?", (account_id,))
    conn.commit()


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
                if not gr_master.is_master(acct):
                    return no("only the master account can do that", 403, master=False)
                if not gr_master.master_here():
                    return no("the master's page works only on the Mac the server runs on", 403, master=False)
                stop = need_two_factor(conn, acct)
                if stop:
                    return stop
            return fn(conn, acct, dev)

    def body():
        return request.get_json(force=True, silent=True) or {}

    @app.post("/api/login")
    def login():
        """Sign a laptop in with the account's email and password."""
        d = body()
        email, fingerprint = fold_email(d.get("email")), str(d.get("fingerprint") or "").strip()
        if not email or not d.get("password") or not fingerprint:
            return no("an email, a password and this laptop's name are needed")
        with closing(S.db()) as conn:
            S.init_db(conn)
            ensure(conn)
            r = rules(conn)
            by_addr, by_mail = "login:" + gr_master.asker(), "login-e:" + email
            if gr_master.rate_full(by_addr, 20, 600) or gr_master.rate_full(by_mail, r["login_tries"], r["login_window_s"]):
                return no(WORDS["wait"], 429)
            acct = conn.execute("SELECT * FROM gr_accounts WHERE email_fold=?", (email,)).fetchone()
            if not password_ok(acct, d.get("password")):
                gr_master.rate_ok(by_addr, 20, 600)
                gr_master.rate_ok(by_mail, r["login_tries"], r["login_window_s"])
                if acct:
                    _note(conn, acct["id"], "password", ok=False, device_name=d.get("device_name"), note="wrong password")
                return no(WORDS["login"], 403)
            token, stop = sign_in_device(conn, acct, fingerprint, (d.get("device_name") or "").strip() or None,
                                         "password", d)
            if stop:
                return stop
            S._event(conn, acct["id"], "login", {"device": d.get("device_name")})
            return jsonify({"token": token, "name": acct["name"], "handle": acct["handle"], "kind": acct["kind"],
                            "wallet_cents": acct["wallet_cents"]})

    @app.get("/api/me/security")
    def me_security():
        return signed_in(lambda conn, acct, dev: jsonify(security_json(conn, acct, dev)))

    @app.post("/api/me/email")
    def me_email():
        d = body()

        def go(conn, acct, dev):
            if acct["password_hash"] and not password_ok(acct, d.get("password")):
                return no("Your password is needed to change your email.", 403, need_password=True)
            why = email_problem(conn, d.get("email"), acct["id"])
            if why:
                return no(why, 409 if why == WORDS["email_taken"] else 400)
            set_email(conn, acct["id"], d.get("email"))
            conn.commit()
            S._event(conn, acct["id"], "email_set", None, dev["id"])
            return jsonify(security_json(conn, acct, dev))
        return signed_in(go)

    @app.post("/api/me/password")
    def me_password():
        """Set a password (an account from before passwords: it needs an email
        too), or change it. Changing it signs the account's other laptops out."""
        d = body()

        def go(conn, acct, dev):
            had = bool(acct["password_hash"])
            if had:
                if not gr_master.rate_ok(f"pw:{acct['id']}", 10, 600):
                    return no(WORDS["wait"], 429)
                if not password_ok(acct, d.get("old")):
                    return no("Your password now isn't that.", 403)
            email = acct["email"]
            if d.get("email") and fold_email(d.get("email")) != (acct["email_fold"] or ""):
                if had:
                    return no("Change your email on its own line.")
                why = email_problem(conn, d.get("email"), acct["id"])
                if why:
                    return no(why, 409 if why == WORDS["email_taken"] else 400)
                email = d.get("email")
            if not email:
                return no("An email is needed with a password: it is what you sign in with.", need_email=True)
            why = password_problem(d.get("new"), email, acct["name"])
            if why:
                return no(why)
            if email != acct["email"]:
                set_email(conn, acct["id"], email)
            set_password(conn, acct["id"], d.get("new"))
            out = 0
            if had:
                out = conn.execute("DELETE FROM gr_devices WHERE account_id=? AND id!=?", (acct["id"], dev["id"])).rowcount
            conn.commit()
            S._event(conn, acct["id"], "password_set", {"changed": had, "signed_out": out}, dev["id"])
            return jsonify(dict(security_json(conn, acct, dev), signed_out=out))
        return signed_in(go)

    @app.post("/api/me/devices/<int:did>/out")
    def me_device_out(did):
        """Sign one of this account's laptops out (it can sign in again)."""
        def go(conn, acct, dev):
            n = conn.execute("DELETE FROM gr_devices WHERE id=? AND account_id=?", (did, acct["id"])).rowcount
            conn.commit()
            if n:
                S._event(conn, acct["id"], "device_out", {"device": did, "self": did == dev["id"]})
            return jsonify({"out": bool(n), "self": did == dev["id"]})
        return signed_in(go)

    # ── email: proving it is theirs (asleep until there is a mail server) ──
    @app.post("/api/me/email/verify")
    def me_email_verify():
        def go(conn, acct, dev):
            if not mail_ready() or not rules(conn)["email_check"]:
                return no(WORDS["mail_off"], 409, off=True)
            if not acct["email"]:
                return no("Add an email first.")
            if not gr_master.rate_ok(f"mail:{acct['id']}", 5, 3600):
                return no(WORDS["wait"], 429)
            return jsonify({"sent": email_code_send(conn, acct, "verify")})
        return signed_in(go)

    @app.post("/api/me/email/verify/confirm")
    def me_email_verify_confirm():
        d = body()

        def go(conn, acct, dev):
            if not email_code_ok(conn, acct, "verify", d.get("code")):
                return no(WORDS["code_wrong"], 403)
            conn.execute("UPDATE gr_accounts SET email_verified_at=? WHERE id=?", (S._now(), acct["id"]))
            conn.commit()
            return jsonify(security_json(conn, acct, dev))
        return signed_in(go)

    # ── two-factor ──
    @app.post("/api/me/2fa/start")
    def twofa_start():
        """A new key for the authenticator app. Nothing is on until a code made
        with it comes back (…/confirm)."""
        def go(conn, acct, dev):
            if two_factor_rule(conn, acct) == "off":
                return no(WORDS["otp_not_for"], 403)
            if acct["totp_secret"]:
                return no("Two-factor is already on.", 409)
            secret = new_secret()
            conn.execute("UPDATE gr_accounts SET totp_pending=? WHERE id=?", (secret, acct["id"]))
            conn.commit()
            return jsonify({"key": secret, "link": otp_link(secret, acct["email"] or acct["handle"] or acct["name"])})
        return signed_in(go)

    @app.post("/api/me/2fa/confirm")
    def twofa_confirm():
        d = body()

        def go(conn, acct, dev):
            if not acct["totp_pending"]:
                return no("Start again: there is no new key waiting.")
            step = totp_step(d.get("code"), acct["totp_pending"])
            if step is None:
                return no(WORDS["otp_wrong"], 403)
            conn.execute("UPDATE gr_accounts SET totp_secret=totp_pending, totp_pending=NULL, totp_last=?, totp_at=?"
                         " WHERE id=?", (step, S._now(), acct["id"]))
            out = conn.execute("DELETE FROM gr_devices WHERE account_id=? AND id!=?", (acct["id"], dev["id"])).rowcount
            conn.execute("UPDATE gr_devices SET twofa_at=? WHERE id=?", (S._now(), dev["id"]))
            conn.commit()
            S._event(conn, acct["id"], "two_factor", {"on": True, "signed_out": out}, dev["id"])
            return jsonify(dict(security_json(conn, acct, dev), signed_out=out))
        return signed_in(go)

    @app.post("/api/me/2fa/off")
    def twofa_off():
        d = body()

        def go(conn, acct, dev):
            if not acct["totp_secret"]:
                return jsonify(security_json(conn, acct, dev))
            if two_factor_rule(conn, acct) == "required":
                return no(WORDS["otp_must"], 403)
            if not gr_master.rate_ok(f"otp:{acct['id']}", 10, 600):
                return no(WORDS["wait"], 429)
            if not _use_otp(conn, acct, d.get("code")):
                conn.commit()
                return no(WORDS["otp_wrong"], 403)
            two_factor_off(conn, acct["id"])
            S._event(conn, acct["id"], "two_factor", {"on": False}, dev["id"])
            return jsonify(security_json(conn, acct, dev))
        return signed_in(go)

    # ── the master ──
    @app.get("/api/master/rules")
    def m_rules():
        return signed_in(lambda conn, acct, dev: jsonify({"rules": rules(conn), "mail": mail_ready()}), master=True)

    @app.post("/api/master/rules")
    def m_rules_set():
        d = body()

        def go(conn, acct, dev):
            try:
                out = set_rules(conn, d.get("rules") or {})
            except ValueError as e:
                return no(str(e))
            S._event(conn, acct["id"], "master_rules", d.get("rules") or {})
            return jsonify({"rules": out, "mail": mail_ready()})
        return signed_in(go, master=True)

    @app.post("/api/master/accounts/<int:aid>/password")
    def m_password(aid):
        """A forgotten password: a new one to pass on, once. Every laptop of that
        account is signed out."""
        def go(conn, acct, dev):
            try:
                new = temporary_password(conn, aid)
            except ValueError as e:
                return no(str(e))
            S._event(conn, acct["id"], "master_account", {"account": aid, "did": ["new password"]})
            return jsonify({"password": new})
        return signed_in(go, master=True)

    @app.post("/api/master/accounts/<int:aid>/two-factor")
    def m_two_factor_off(aid):
        """Someone lost their authenticator: take two-factor off their account."""
        def go(conn, acct, dev):
            two_factor_off(conn, aid)
            S._event(conn, acct["id"], "master_account", {"account": aid, "did": ["two-factor off"]})
            return jsonify({"account": aid, "two_factor": False})
        return signed_in(go, master=True)

    @app.get("/api/master/signins")
    def m_signins():
        def go(conn, acct, dev):
            rows = conn.execute(
                "SELECT s.*, a.name, a.handle FROM gr_signins s LEFT JOIN gr_accounts a ON a.id=s.account_id"
                " ORDER BY s.id DESC LIMIT 300").fetchall()
            return jsonify({"signins": [{
                "at": s["at"], "name": s["name"], "handle": s["handle"], "device": s["device_name"] or "",
                "from": s["address"] or "", "how": s["how"], "new": bool(s["new_device"]), "ok": bool(s["ok"]),
                "note": s["note"] or ""} for s in rows]})
        return signed_in(go, master=True)
