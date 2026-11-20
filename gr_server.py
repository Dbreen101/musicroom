"""Green Room server — the campus pool for Music Room GR builds.

Runs on David's laptop on the campus network. Holds the rights-cleared
catalogue, hands out borrows (encrypted downloads + a per-borrow key the
app keeps), and tracks play-money wallets for the residency's pricing
experiments. ALL money here is PLAY MONEY (cents of fake euro).

Usage:
  python gr_server.py init
  python gr_server.py add <folder> [--price 250] [--online-art]
  python gr_server.py covers [--online-art]
  python gr_server.py invite <name>
  python gr_server.py accounts
  python gr_server.py house <handle> [--off]     (the Music Room's own account: signs its crates)
  python gr_server.py listen-copies              (make every record's shop listening copy ahead of time)
  python gr_server.py run [--host 0.0.0.0] [--port 5301]

Covers, in order: the cover the Music Room library already holds for that
file (David's chosen art) → art embedded in the file → a cover image in the
file's folder → (only with --online-art) an online lookup. Re-running `add`
or `covers` fills in any track still missing one.

The lock is friction, not a fortress: files are AES-256-CTR encrypted in
transit and at rest on the borrower's laptop; the app holds the key and
decrypts in memory to play. A determined person can always extract audio —
the honest protections are the social deal, device limits, and (later)
per-account watermarking.
"""

import argparse
import os
import secrets
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ---------- Pricing experiment knobs (play money, fake-euro cents) ----------
PLAY_MONEY_START_CENTS = 2000    # every new account starts with €20
TOPUP_STEP_CENTS = 1000          # a short wallet tops itself up in €10 steps (recorded, never blocks)
DEFAULT_TRACK_PRICE_CENTS = 250  # default buy price shown in the catalogue
MAX_DEVICES = 2                  # devices one account may register

# The subscription plans a listener picks from the first time they borrow.
# Prices are the three residency variants from docs/PRICING_GR.md; the shape
# is David's (2026-10-21): a month's fee buys `per_month` borrows, and a
# borrowed record STAYS on your machine for good — it just only plays in the
# Music Room. Borrow 20 this month, listen for years, never pay again. A
# month with no borrows costs nothing. `per_borrow_cents` = pay-as-you-go.
PLANS = {
    "a": {"name": "Borrow", "price_cents": 600, "per_month": 20, "per_borrow_cents": 0,
          "blurb": "€6 for a month of borrowing — up to 20 records. They stay on your machine; they play only here."},
    "b": {"name": "Light", "price_cents": 400, "per_month": 10, "per_borrow_cents": 0,
          "blurb": "€4 for a month of borrowing — up to 10 records, yours to keep playing here."},
    "c": {"name": "Pay as you go", "price_cents": 0, "per_month": None, "per_borrow_cents": 50,
          "blurb": "No month fee. €0.50 a borrow, every cent of it credited if you buy the record."},
}
# kept for older callers; the real numbers live in PLANS
SUB_PRICE_CENTS = PLANS["a"]["price_cents"]
SUB_TRACK_LIMIT = PLANS["a"]["per_month"]

AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aiff", ".aif"}
MAX_RECORD_BYTES = 400 * 1024 * 1024        # one record's audio
MAX_IMAGE_BYTES = 25 * 1024 * 1024          # one picture for a room
MAX_BYTES_PER_ACCOUNT = 4 * 1024 ** 3        # all of one account's records (this is someone's laptop)
MAX_CODE_CHARS = 120_000                     # a room's own CSS, or its own whole page
# what an artist, label or shop says when they put a record up for sale
RIGHTS_TEXT = ("I made this record or hold the rights to sell it, and anything in it that isn't mine "
               "(samples, artwork, words) is cleared for this.")
CHUNK = 64 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 420 * 1024 * 1024   # no request bigger than one record and its cover


# ---------- database ----------

def db_path() -> str:
    return os.environ.get(
        "MR_GR_DB", str(Path(__file__).resolve().parent / "green_room.db")
    )


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_tracks(
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            title TEXT,
            artist TEXT,
            album TEXT,
            duration_s REAL,
            format TEXT,
            size_bytes INTEGER,
            price_cents INTEGER NOT NULL,
            added_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gr_accounts(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            invite_code TEXT NOT NULL UNIQUE,
            wallet_cents INTEGER NOT NULL,
            sub_month TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gr_devices(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            name TEXT,
            fingerprint TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gr_borrows(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
            key_hex TEXT NOT NULL,
            nonce_hex TEXT NOT NULL,
            month TEXT NOT NULL,
            borrowed_at TEXT NOT NULL,
            returned_at TEXT
        );
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(gr_tracks)")}
    if "art_path" not in cols:
        conn.execute("ALTER TABLE gr_tracks ADD COLUMN art_path TEXT")
        conn.execute("ALTER TABLE gr_tracks ADD COLUMN art_source TEXT")
    if "owner_account_id" not in cols:
        # the artist (or label) whose room sells/lends this record
        conn.execute("ALTER TABLE gr_tracks ADD COLUMN owner_account_id INTEGER")
        conn.execute("ALTER TABLE gr_tracks ADD COLUMN buy_url TEXT")
    acols = {r[1] for r in conn.execute("PRAGMA table_info(gr_accounts)")}
    if "kind" not in acols:
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN kind TEXT NOT NULL DEFAULT 'listener'")
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN handle TEXT")
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN bio TEXT")
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN links TEXT")      # JSON [{label,url}]
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_gr_accounts_handle"
                     " ON gr_accounts(handle)")
    acols = {r[1] for r in conn.execute("PRAGMA table_info(gr_accounts)")}
    if "plan" not in acols:
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN plan TEXT")       # a key of PLANS, once chosen
    if "place_name" not in acols:
        # where a room is, if its owner says: a name in their own words + a spot
        # on the globe (Explore → Globe). All three empty = nowhere in
        # particular ("universal"). Nothing here is looked up or corrected.
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN place_name TEXT")
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN lat REAL")
        conn.execute("ALTER TABLE gr_accounts ADD COLUMN lon REAL")
    dcols = {r[1] for r in conn.execute("PRAGMA table_info(gr_devices)")}
    if "last_seen" not in dcols:
        conn.execute("ALTER TABLE gr_devices ADD COLUMN last_seen TEXT")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_topups(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            cents INTEGER NOT NULL,
            reason TEXT,
            at TEXT NOT NULL
        );
        -- what people do: the server logs its own events (borrow, buy, room
        -- views…) and the app sends the rest (pages, plays, searches…)
        CREATE TABLE IF NOT EXISTS gr_events(
            id INTEGER PRIMARY KEY,
            account_id INTEGER REFERENCES gr_accounts(id),
            device_id INTEGER,
            kind TEXT NOT NULL,
            data TEXT,            -- JSON
            at TEXT NOT NULL,     -- when it happened (the app's clock for app events)
            received_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gr_events_kind ON gr_events(kind, at);
        CREATE INDEX IF NOT EXISTS idx_gr_events_acct ON gr_events(account_id, at);
        -- in-app feedback and bug reports, beside everything else
        CREATE TABLE IF NOT EXISTS gr_feedback(
            id INTEGER PRIMARY KEY,
            account_id INTEGER REFERENCES gr_accounts(id),
            kind TEXT NOT NULL,   -- like / dislike / confused / bug / idea
            note TEXT NOT NULL,
            page TEXT,
            context TEXT,         -- JSON
            at TEXT NOT NULL
        );
        """
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_rooms(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            name TEXT NOT NULL,
            design TEXT NOT NULL DEFAULT '{}',   -- JSON: colours, type, header, sections, items
            css TEXT,                            -- code mode: own CSS over the default structure
            html TEXT,                           -- code mode: a whole page (sandboxed)
            is_live INTEGER NOT NULL DEFAULT 0,  -- the one others see
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gr_purchases(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
            paid_cents INTEGER NOT NULL,
            artist_cents INTEGER NOT NULL,
            bought_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    gr_shop.ensure(conn)      # record shopping: crates, the counter, blind (gr_shop.py)
    gr_master.ensure(conn)    # the master account, approvals, reports, the version (gr_master.py)


ACCOUNT_KINDS = ("listener", "artist", "label", "shop", "venue", "business")


CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"     # no 0/o, 1/l/i: read aloud and typed by hand


def new_code() -> str:
    """An account code: the one secret that signs a laptop in. Sixteen letters
    from 31 (about 79 bits), in four groups so it can be read out — far past
    guessing, even by a laptop trying all night."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return "gr-" + "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _slug(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "room"


def art_dir() -> Path:
    """Covers live beside the db: green_room.db → green_room_art/."""
    p = Path(db_path())
    return p.parent / f"{p.stem}_art"


# ---------- covers ----------

_FOLDER_COVER_NAMES = ("cover", "folder", "front", "album", "artwork")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _library_dbs():
    """The Music Room libraries to borrow covers from: MR_LIBRARY_DB alone
    when set; otherwise the native app's library (David's daily one), then
    the dev project's. Existing files only, no repeats."""
    out = []
    explicit = os.environ.get("MR_LIBRARY_DB")
    candidates = [explicit] if explicit else [
        str(Path.home() / "Library/Application Support/Music Room/library.db"),
        str(Path(__file__).resolve().parent / "library.db"),
    ]
    for c in candidates:
        if c and os.path.exists(c) and c not in out:
            out.append(c)
    return out


def _resolve_moved(stored: str):
    """A stored /Volumes/<drive>/… path, found again if the drive's name changed."""
    if not stored:
        return None
    if os.path.exists(stored):
        return stored
    parts = Path(stored).parts
    if "Volumes" in parts:
        rel = Path(*parts[parts.index("Volumes") + 2:])
        vols = Path("/Volumes")
        if vols.exists():
            for vol in vols.iterdir():
                cand = vol / rel
                if cand.exists():
                    return str(cand)
    return None


def _library_cover(path: Path):
    """The cover the Music Room library already holds for this exact file
    (matched by path, then by filename + size)."""
    size_mb = path.stat().st_size / (1024 * 1024)
    for lib in _library_dbs():
        try:
            with closing(sqlite3.connect(f"file:{lib}?mode=ro", uri=True, timeout=3)) as conn:
                row = conn.execute(
                    "SELECT t.artwork_path FROM files f JOIN tracks t ON t.id = f.track_id"
                    " WHERE f.file_path = ? COLLATE NOCASE AND t.artwork_path IS NOT NULL"
                    " LIMIT 1", (str(path),)).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT t.artwork_path FROM files f JOIN tracks t ON t.id = f.track_id"
                        " WHERE f.file_path LIKE ? AND ABS(f.file_size_mb - ?) < 0.02"
                        " AND t.artwork_path IS NOT NULL LIMIT 1",
                        ("%/" + path.name, size_mb)).fetchone()
        except sqlite3.Error:
            continue
        if row:
            found = _resolve_moved(row[0])
            if found:
                return Path(found).read_bytes()
    return None


def _folder_cover(path: Path):
    """A cover image sitting beside the file: cover/folder/front.jpg etc., or
    the folder's only image."""
    try:
        images = [p for p in path.parent.iterdir()
                  if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
                  and not p.name.startswith(".")]
    except OSError:
        return None
    for img in images:
        if img.stem.lower() in _FOLDER_COVER_NAMES:
            return img.read_bytes()
    if len(images) == 1:
        return images[0].read_bytes()
    return None


def find_cover(path: Path, title=None, artist=None, online=False):
    """(image bytes, source) for a pool file, or (None, None)."""
    try:
        data = _library_cover(path)
        if data:
            return data, "library"
    except Exception:
        pass
    try:
        from artwork_fetcher import _embedded_bytes
        data = _embedded_bytes(str(path))
        if data:
            return data, "embedded"
    except Exception:
        pass
    data = _folder_cover(path)
    if data:
        return data, "folder"
    if online and (title or artist):
        try:
            from artwork_fetcher import _caa_bytes, _itunes_bytes
            data = _itunes_bytes(title or "", artist or "") or _caa_bytes(title or "", artist or "")
            if data:
                return data, "online"
        except Exception:
            pass
    return None, None


def _open_picture(data: bytes):
    """Open an uploaded picture safely: only JPEG / PNG / WebP / GIF, and never
    one so big it would take the server's memory (a "picture bomb")."""
    import io
    import warnings

    from PIL import Image

    Image.MAX_IMAGE_PIXELS = 40_000_000
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        img = Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP", "GIF"])
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("too big")
        img.load()
    return img


def _save_cover(track_id: int, data: bytes):
    """Normalise to an 800px JPEG in art_dir(); returns the path or None."""
    import io

    from PIL import Image

    try:
        img = _open_picture(data)
        img = img.convert("RGB")
        img.thumbnail((800, 800))
        art_dir().mkdir(parents=True, exist_ok=True)
        out = art_dir() / f"{track_id}.jpg"
        img.save(out, "JPEG", quality=88)
        return str(out)
    except Exception:
        return None


def attach_cover(conn, track_row, online=False) -> bool:
    data, source = find_cover(Path(track_row["path"]), track_row["title"],
                              track_row["artist"], online)
    if not data:
        return False
    saved = _save_cover(track_row["id"], data)
    if not saved:
        return False
    conn.execute("UPDATE gr_tracks SET art_path=?, art_source=? WHERE id=?",
                 (saved, source, track_row["id"]))
    conn.commit()
    return True


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _month() -> str:
    return datetime.now().strftime("%Y-%m")


# ---------- auth ----------

def _auth(conn):
    """Resolve the request's bearer token to (account, device), or (None, None)."""
    tok = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    if not tok:
        return None, None
    dev = conn.execute("SELECT * FROM gr_devices WHERE token=?", (tok,)).fetchone()
    if not dev:
        return None, None
    acct = conn.execute(
        "SELECT * FROM gr_accounts WHERE id=?", (dev["account_id"],)
    ).fetchone()
    if gr_master.is_paused(acct):          # the master has paused this account
        return None, None
    conn.execute("UPDATE gr_devices SET last_seen=? WHERE id=?", (_now(), dev["id"]))
    conn.commit()
    return acct, dev


def _plan_of(acct):
    return PLANS.get(acct["plan"] or "")


def _event(conn, account_id, kind, data=None, device_id=None, at=None):
    """One line in the activity log."""
    import json
    conn.execute(
        "INSERT INTO gr_events(account_id, device_id, kind, data, at, received_at)"
        " VALUES(?,?,?,?,?,?)",
        (account_id, device_id, kind, json.dumps(data) if data is not None else None,
         at or _now(), _now()))
    conn.commit()


def _charge(conn, acct, cents, reason):
    """Take play money from the wallet. A short wallet tops itself up in
    TOPUP_STEP_CENTS steps first — recorded in gr_topups, never refused:
    during the residency nobody is stopped, and the top-ups show what each
    person would have paid. Returns the cents topped up."""
    if cents <= 0:
        return 0
    wallet = conn.execute("SELECT wallet_cents FROM gr_accounts WHERE id=?",
                          (acct["id"],)).fetchone()[0]
    topped = 0
    if wallet < cents:
        short = cents - wallet
        topped = ((short + TOPUP_STEP_CENTS - 1) // TOPUP_STEP_CENTS) * TOPUP_STEP_CENTS
        conn.execute("INSERT INTO gr_topups(account_id, cents, reason, at) VALUES(?,?,?,?)",
                     (acct["id"], topped, reason, _now()))
        conn.execute("UPDATE gr_accounts SET wallet_cents = wallet_cents + ? WHERE id=?",
                     (topped, acct["id"]))
    conn.execute("UPDATE gr_accounts SET wallet_cents = wallet_cents - ? WHERE id=?",
                 (cents, acct["id"]))
    conn.commit()
    return topped


def _unauthorized():
    return jsonify({"error": "not signed in — join with your invite code first"}), 401


# ---------- play-money subscription ----------

def _ensure_sub(conn, acct):
    """Before a borrow: the account needs a plan (→ 409 need_plan so the app
    shows the subscription page); a monthly plan charges its price on the
    month's first borrow; pay-as-you-go charges per borrow. Returns an error
    response or None."""
    plan = _plan_of(acct)
    if not plan:
        return jsonify({"error": "choose a subscription first", "need_plan": True}), 409
    if plan["per_borrow_cents"]:
        _charge(conn, acct, plan["per_borrow_cents"], "borrow")
        return None
    if acct["sub_month"] == _month():
        return None
    _charge(conn, acct, plan["price_cents"], f"subscription {acct['plan']} {_month()}")
    conn.execute("UPDATE gr_accounts SET sub_month=? WHERE id=?", (_month(), acct["id"]))
    conn.commit()
    return None


# ---------- API ----------

@app.post("/api/join")
def api_join():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("invite_code") or "").strip()
    fingerprint = (data.get("fingerprint") or "").strip()
    device_name = (data.get("device_name") or "").strip() or None
    if not code or not fingerprint:
        return jsonify({"error": "invite_code and fingerprint are required"}), 400
    if not gr_master.rate_ok("join:" + (request.remote_addr or "?"), 12, 600):
        return jsonify({"error": "too many tries from here — wait ten minutes"}), 429
    with closing(db()) as conn:
        acct = conn.execute(
            "SELECT * FROM gr_accounts WHERE invite_code=?", (code.lower(),)
        ).fetchone()
        if not acct:
            return jsonify({"error": "that invite code isn't known here"}), 403
        dev = conn.execute(
            "SELECT * FROM gr_devices WHERE account_id=? AND fingerprint=?",
            (acct["id"], fingerprint),
        ).fetchone()
        if not dev:
            count = conn.execute(
                "SELECT COUNT(*) FROM gr_devices WHERE account_id=?", (acct["id"],)
            ).fetchone()[0]
            if count >= MAX_DEVICES:
                return (
                    jsonify({"error": f"this account already has {MAX_DEVICES} devices"}),
                    403,
                )
            token = secrets.token_hex(24)
            conn.execute(
                "INSERT INTO gr_devices(account_id, name, fingerprint, token, created_at)"
                " VALUES(?,?,?,?,?)",
                (acct["id"], device_name, fingerprint, token, _now()),
            )
            conn.commit()
        else:
            token = dev["token"]
        _event(conn, acct["id"], "join", {"device": device_name, "new_device": dev is None})
        return jsonify(
            {"token": token, "name": acct["name"], "wallet_cents": acct["wallet_cents"],
             "invite_code": acct["invite_code"]}
        )


@app.get("/api/me")
def api_me():
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        borrows_this_month = conn.execute(
            "SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND month=?",
            (acct["id"], _month()),
        ).fetchone()[0]
        devices = conn.execute(
            "SELECT COUNT(*) FROM gr_devices WHERE account_id=?", (acct["id"],)
        ).fetchone()[0]
        plan = _plan_of(acct)
        held = conn.execute(
            "SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND returned_at IS NULL",
            (acct["id"],)).fetchone()[0]
        topups = conn.execute(
            "SELECT COALESCE(SUM(cents),0) FROM gr_topups WHERE account_id=?",
            (acct["id"],)).fetchone()[0]
        return jsonify(
            {
                "name": acct["name"],
                "kind": acct["kind"],
                "handle": acct["handle"],
                "is_public": bool(acct["is_public"]),
                "wallet_cents": acct["wallet_cents"],
                "topups_cents": topups,
                "plan": acct["plan"],
                "plan_name": plan["name"] if plan else None,
                "sub_active": bool(plan) and (bool(plan["per_borrow_cents"]) or acct["sub_month"] == _month()),
                "sub_price_cents": plan["price_cents"] if plan else None,
                "per_borrow_cents": plan["per_borrow_cents"] if plan else None,
                "borrows_this_month": borrows_this_month,
                "per_month": plan["per_month"] if plan else None,
                "held": held,
                "credit_cents": _credit_cents(conn, acct),
                "devices": devices,
                "is_master": gr_master.is_master(acct),
                "kind_requested": (acct["kind_requested"] if "kind_requested" in acct.keys() else None) or "",
                "room_hidden": gr_master.is_hidden(acct),
                "room_hidden_note": (acct["hidden_note"] if "hidden_note" in acct.keys() else None) or "",
                "agreed": bool(acct["agreed_at"]) if "agreed_at" in acct.keys() else False,
            }
        )


@app.get("/api/plans")
def api_plans():
    return jsonify({"plans": [dict(key=k, **v) for k, v in PLANS.items()]})


@app.post("/api/me/plan")
def api_me_plan():
    """Pick (or change) the subscription plan. No money moves here — the
    residency runs on play money; the first borrow charges it."""
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        key = (data.get("plan") or "").strip().lower()
        if key not in PLANS:
            return jsonify({"error": "that's not one of the plans"}), 400
        conn.execute("UPDATE gr_accounts SET plan=? WHERE id=?", (key, acct["id"]))
        conn.commit()
        _event(conn, acct["id"], "plan", {"plan": key, "was": acct["plan"]})
        return jsonify({"plan": key, "plan_name": PLANS[key]["name"]})


@app.post("/api/events")
def api_events():
    """A batch of app-side events: {events:[{kind, data, at}]}."""
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, dev = _auth(conn)
        if not acct:
            return _unauthorized()
        n = 0
        for e in (data.get("events") or [])[:500]:
            kind = (e.get("kind") or "").strip()[:40]
            if not kind:
                continue
            _event(conn, acct["id"], kind, e.get("data"), dev["id"], e.get("at"))
            n += 1
        return jsonify({"stored": n})


@app.post("/api/feedback")
def api_feedback():
    """In-app feedback / bug reports, kept beside the activity log."""
    import json
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, dev = _auth(conn)
        if not acct:
            return _unauthorized()
        note = (data.get("note") or "").strip()[:2000]
        if not note:
            return jsonify({"error": "a note is needed"}), 400
        conn.execute(
            "INSERT INTO gr_feedback(account_id, kind, note, page, context, at) VALUES(?,?,?,?,?,?)",
            (acct["id"], (data.get("kind") or "idea")[:20], note, (data.get("page") or "")[:200],
             json.dumps(data.get("context")) if data.get("context") is not None else None,
             data.get("at") or _now()))
        conn.commit()
        _event(conn, acct["id"], "feedback", {"kind": data.get("kind"), "page": data.get("page")}, dev["id"])
        return jsonify({"stored": True})


@app.post("/api/signup")
def api_signup():
    """Make a profile yourself — no invite needed. The server mints the
    account and signs this device in."""
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    fingerprint = (data.get("fingerprint") or "").strip()
    device_name = (data.get("device_name") or "").strip() or None
    asked = (data.get("kind_requested") or data.get("kind") or "").strip().lower()
    kind = "listener"                     # everyone starts as a listener (David, 2026-11-20);
    asked = asked if asked in gr_master.KINDS_TO_ASK else None   # any other kind waits for the master
    if not name or not fingerprint:
        return jsonify({"error": "a name is needed"}), 400
    if len(name) > 80:
        return jsonify({"error": "that name is too long"}), 400
    if not data.get("agreed"):
        return jsonify({"error": "please read and agree to the house rules first", "need_agree": True}), 400
    if not gr_master.rate_ok("signup:" + (request.remote_addr or "?"), gr_master.SIGNUPS_PER_HOUR, 3600):
        return jsonify({"error": "too many new accounts from here in one hour — try again later"}), 429
    with closing(db()) as conn:
        init_db(conn)
        base = _slug(name)
        handle, n = base, 2
        while conn.execute("SELECT 1 FROM gr_accounts WHERE handle=?", (handle,)).fetchone():
            handle = f"{base}-{n}"
            n += 1
        code = new_code()
        cur = conn.execute(
            "INSERT INTO gr_accounts(name, invite_code, wallet_cents, created_at, kind, handle,"
            " is_public) VALUES(?,?,?,?,?,?,0)",
            (name, code, PLAY_MONEY_START_CENTS, _now(), kind, handle))
        aid = cur.lastrowid
        conn.execute("UPDATE gr_accounts SET kind_requested=?, agreed_at=?, agreed_version=? WHERE id=?",
                     (asked, _now(), gr_master.HOUSE_RULES_VERSION, aid))
        token = secrets.token_hex(24)
        conn.execute(
            "INSERT INTO gr_devices(account_id, name, fingerprint, token, created_at, last_seen)"
            " VALUES(?,?,?,?,?,?)", (aid, device_name, fingerprint, token, _now(), _now()))
        conn.commit()
        _event(conn, aid, "signup", {"kind": kind, "asked": asked, "device": device_name})
        return jsonify({"token": token, "name": name, "handle": handle, "kind": kind,
                        "kind_requested": asked or "",
                        "invite_code": code, "wallet_cents": PLAY_MONEY_START_CENTS})


def _credit_cents(conn, acct):
    """The per-track buyout credit this month. Monthly plans: the sub ÷
    tracks borrowed this month (zero until the month's sub is paid).
    Pay-as-you-go: what a borrow cost, every cent of it."""
    plan = _plan_of(acct)
    if not plan:
        return 0
    if plan["per_borrow_cents"]:
        return plan["per_borrow_cents"]
    if acct["sub_month"] != _month():
        return 0
    n = conn.execute(
        "SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND month=?",
        (acct["id"], _month()),
    ).fetchone()[0]
    return plan["price_cents"] // n if n else 0


def _catalogue_rows(conn, acct, owner_id=None, everything=False):
    """Catalogue items with this account's borrow/purchase state attached."""
    mine = {
        r["track_id"]: r["id"]
        for r in conn.execute(
            "SELECT id, track_id FROM gr_borrows WHERE account_id=? AND returned_at IS NULL",
            (acct["id"],),
        )
    }
    bought = {
        r["track_id"]
        for r in conn.execute(
            "SELECT track_id FROM gr_purchases WHERE account_id=?", (acct["id"],)
        )
    }
    credit = _credit_cents(conn, acct)
    borrowed_this_month = {
        r["track_id"]
        for r in conn.execute(
            "SELECT track_id FROM gr_borrows WHERE account_id=? AND month=?",
            (acct["id"], _month()),
        )
    }
    where = "WHERE t.owner_account_id=?" if owner_id else "WHERE 1"
    params = (owner_id,) if owner_id else ()
    if not everything:          # waiting for the master, refused or taken down: not for others
        where += f" AND {gr_master.LIVE}"
        if not owner_id:        # (a room the master took down: its records leave the shelves too)
            where += " AND (a.id IS NULL OR a.hidden_at IS NULL)"
    out = []
    for t in conn.execute(
        f"SELECT t.*, a.handle AS owner_handle, a.name AS owner_name, a.kind AS owner_kind"
        f" FROM gr_tracks t LEFT JOIN gr_accounts a ON a.id = t.owner_account_id"
        f" {where} ORDER BY t.artist, t.album, t.title", params
    ):
        c = credit if t["id"] in borrowed_this_month else 0
        out.append(
            {
                "id": t["id"],
                "title": t["title"],
                "artist": t["artist"],
                "album": t["album"],
                "duration_s": t["duration_s"],
                "format": t["format"],
                "size_bytes": t["size_bytes"],
                "price_cents": t["price_cents"],
                "buy_now_cents": max(0, (t["price_cents"] or 0) - c),
                "buy_url": t["buy_url"],
                "borrow_id": mine.get(t["id"]),
                "purchased": t["id"] in bought,
                "owner_handle": t["owner_handle"],
                "owner_name": t["owner_name"],
                "owner_kind": t["owner_kind"],
                "has_art": bool(t["art_path"]),
                "art_v": int(os.path.getmtime(t["art_path"]))
                         if t["art_path"] and os.path.exists(t["art_path"]) else 0,
                "year": _opt(t, "year"), "genre": _opt(t, "genre"), "label": _opt(t, "label"),
            }
        )
    return out


def _opt(row, key):
    """A column that a database from before record shopping may not have yet."""
    return row[key] if key in row.keys() else None


@app.get("/api/catalogue")
def api_catalogue():
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        return jsonify({"tracks": _catalogue_rows(conn, acct)})


@app.get("/api/art/<int:track_id>")
def api_art(track_id):
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute(
            "SELECT art_path, status, owner_account_id FROM gr_tracks WHERE id=?", (track_id,)).fetchone()
        if row and not gr_master.record_visible(row, acct):
            row = None
    if not row or not row["art_path"] or not os.path.exists(row["art_path"]):
        return jsonify({"error": "no cover"}), 404
    return send_file(row["art_path"], mimetype="image/jpeg")


@app.post("/api/borrow")
def api_borrow():
    data = request.get_json(force=True, silent=True) or {}
    track_id = data.get("track_id")
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        track = conn.execute(
            "SELECT * FROM gr_tracks WHERE id=?", (track_id,)
        ).fetchone()
        if not track:
            return jsonify({"error": "no such track"}), 404
        already_held = conn.execute(
            "SELECT 1 FROM gr_borrows WHERE account_id=? AND track_id=? AND returned_at IS NULL",
            (acct["id"], track_id)).fetchone()
        if not already_held and (track["status"] or "live") != "live":
            return jsonify({"error": "that record isn't in the shop right now"}), 404

        def _payload(borrow_row):
            return jsonify(
                {
                    "borrow_id": borrow_row["id"],
                    "key": borrow_row["key_hex"],
                    "nonce": borrow_row["nonce_hex"],
                    "track_id": track["id"],
                    "title": track["title"],
                    "artist": track["artist"],
                    "format": track["format"],
                    "size_bytes": track["size_bytes"],
                    "url": f"/api/download/{borrow_row['id']}",
                }
            )

        existing = conn.execute(
            "SELECT * FROM gr_borrows WHERE account_id=? AND track_id=?"
            " AND returned_at IS NULL",
            (acct["id"], track_id),
        ).fetchone()
        if existing:
            return _payload(existing)

        err = _ensure_sub(conn, acct)
        if err:
            return err
        plan = _plan_of(acct)
        if plan and plan["per_month"]:
            used = conn.execute(
                "SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND month=?",
                (acct["id"], _month()),
            ).fetchone()[0]
            if used >= plan["per_month"]:
                return (
                    jsonify({"error": f"that's this month's {plan['per_month']} borrows used — more next month"}),
                    403,
                )
        key_hex = secrets.token_hex(32)
        nonce_hex = secrets.token_hex(16)
        cur = conn.execute(
            "INSERT INTO gr_borrows(account_id, track_id, key_hex, nonce_hex, month,"
            " borrowed_at) VALUES(?,?,?,?,?,?)",
            (acct["id"], track_id, key_hex, nonce_hex, _month(), _now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM gr_borrows WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        _event(conn, acct["id"], "borrow", {"track_id": track["id"], "title": track["title"],
                                             "owner": track["owner_account_id"], "plan": acct["plan"]})
        return _payload(row)


@app.post("/api/return")
def api_return():
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute(
            "SELECT * FROM gr_borrows WHERE id=? AND account_id=? AND returned_at IS NULL",
            (data.get("borrow_id"), acct["id"]),
        ).fetchone()
        if not row:
            return jsonify({"error": "no such active borrow"}), 404
        conn.execute(
            "UPDATE gr_borrows SET returned_at=? WHERE id=?", (_now(), row["id"])
        )
        conn.commit()
        _event(conn, acct["id"], "return", {"track_id": row["track_id"]})
        return jsonify({"returned": True})


@app.get("/api/download/<int:borrow_id>")
def api_download(borrow_id):
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute(
            "SELECT * FROM gr_borrows WHERE id=? AND account_id=? AND returned_at IS NULL",
            (borrow_id, acct["id"]),
        ).fetchone()
        if not row:
            return jsonify({"error": "no such active borrow"}), 404
        track = conn.execute(
            "SELECT * FROM gr_tracks WHERE id=?", (row["track_id"],)
        ).fetchone()
    path = Path(track["path"])
    if not path.exists():
        return jsonify({"error": "the file is missing on the server"}), 410

    key = bytes.fromhex(row["key_hex"])
    nonce = bytes.fromhex(row["nonce_hex"])

    def stream():
        enc = Cipher(algorithms.AES(key), modes.CTR(nonce)).encryptor()
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                yield enc.update(chunk)

    headers = {
        "Content-Length": str(track["size_bytes"]),
        "X-GR-Filename": track["filename"],
        "X-GR-Format": track["format"] or "",
        "X-GR-Nonce": row["nonce_hex"],
    }
    return Response(stream(), mimetype="application/octet-stream", headers=headers)


# ---------- buying ----------

@app.post("/api/buy")
def api_buy():
    """Buy a record outright: price − this month's per-track credit (free when
    the credit covers it). The artist is paid the full price either way."""
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        track = conn.execute(
            "SELECT * FROM gr_tracks WHERE id=?", (data.get("track_id"),)
        ).fetchone()
        if not track:
            return jsonify({"error": "no such track"}), 404
        if (track["status"] or "live") != "live":       # waiting for the master, refused or taken down
            return jsonify({"error": "that record isn't in the shop right now"}), 404
        already = conn.execute(
            "SELECT id FROM gr_purchases WHERE account_id=? AND track_id=?",
            (acct["id"], track["id"]),
        ).fetchone()
        if already:
            return jsonify({"bought": True, "paid_cents": 0, "already": True,
                            "url": f"/api/download-plain/{track['id']}"})
        price = track["price_cents"] or 0
        borrowed_this_month = conn.execute(
            "SELECT 1 FROM gr_borrows WHERE account_id=? AND track_id=? AND month=?",
            (acct["id"], track["id"], _month()),
        ).fetchone()
        credit = _credit_cents(conn, acct) if borrowed_this_month else 0
        to_pay = max(0, price - credit)
        _charge(conn, acct, to_pay, f"buy track {track['id']}")
        conn.execute(
            "INSERT INTO gr_purchases(account_id, track_id, paid_cents, artist_cents, bought_at)"
            " VALUES(?,?,?,?,?)", (acct["id"], track["id"], to_pay, price, _now()))
        # the borrow ends with the purchase — the plain file replaces it
        conn.execute(
            "UPDATE gr_borrows SET returned_at=? WHERE account_id=? AND track_id=?"
            " AND returned_at IS NULL", (_now(), acct["id"], track["id"]))
        conn.commit()
        _event(conn, acct["id"], "buy", {"track_id": track["id"], "title": track["title"],
                                          "paid_cents": to_pay, "credit_cents": credit,
                                          "artist_cents": price, "owner": track["owner_account_id"]})
        return jsonify({"bought": True, "paid_cents": to_pay, "credit_cents": credit,
                        "artist_cents": price, "format": track["format"],
                        "filename": track["filename"],
                        "url": f"/api/download-plain/{track['id']}"})


@app.get("/api/download-plain/<int:track_id>")
def api_download_plain(track_id):
    """The unlocked file, for a record this account has bought. Free to
    redownload forever — it's theirs."""
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        owned = conn.execute(
            "SELECT 1 FROM gr_purchases WHERE account_id=? AND track_id=?",
            (acct["id"], track_id),
        ).fetchone()
        track = conn.execute("SELECT * FROM gr_tracks WHERE id=?", (track_id,)).fetchone()
    if not owned or not track:
        return jsonify({"error": "you haven't bought this record"}), 403
    path = Path(track["path"])
    if not path.exists():
        return jsonify({"error": "the file is missing on the server"}), 410
    return send_file(str(path), mimetype="application/octet-stream",
                     as_attachment=True, download_name=track["filename"])


# ---------- public rooms ----------

PLACE_NAME_MAX = 120


def _place_of(acct_row):
    """Where this room is, as its owner put it → {name, lat, lon}, or None when
    they left it nowhere in particular (the globe shows those as universal)."""
    try:
        lat, lon = acct_row["lat"], acct_row["lon"]
    except (IndexError, KeyError):
        return None
    if lat is None or lon is None:
        return None
    return {"name": acct_row["place_name"] or "", "lat": lat, "lon": lon}


def _place_from_request(raw):
    """A place sent by the owner → (place_name, lat, lon), or (None, None, None)
    for "nowhere in particular". Raises ValueError with a plain reason."""
    if raw is None or raw == "" or raw == {}:
        return None, None, None
    if not isinstance(raw, dict):
        raise ValueError("a place is a name and a spot on the globe")
    lat, lon = raw.get("lat"), raw.get("lon")
    if lat is None and lon is None:
        if str(raw.get("name") or "").strip():
            raise ValueError("pick the spot on the globe as well as naming it")
        return None, None, None
    try:
        if isinstance(lat, bool) or isinstance(lon, bool):
            raise TypeError
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError("the spot on the globe isn't a pair of numbers")
    if lat != lat or lon != lon or not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError("that spot isn't on the globe")
    name = " ".join(str(raw.get("name") or "").split())[:PLACE_NAME_MAX]
    return name, round(lat, 5), round(lon, 5)


def _room_public(conn, acct_row, include_tracks_for=None, design_id=None):
    """A public room as others see it: the account's live design + its
    records (with the viewer's own borrow/purchase state when given).
    design_id lets the OWNER preview a draft in place of the live one."""
    if design_id:
        live = conn.execute(
            "SELECT * FROM gr_rooms WHERE account_id=? AND id=?", (acct_row["id"], design_id)
        ).fetchone()
    else:
        live = conn.execute(
            "SELECT * FROM gr_rooms WHERE account_id=? AND is_live=1", (acct_row["id"],)
        ).fetchone()
    import json
    out = {
        "handle": acct_row["handle"],
        "name": acct_row["name"],
        "kind": acct_row["kind"],
        "bio": acct_row["bio"] or "",
        "links": json.loads(acct_row["links"] or "[]"),
        "place": _place_of(acct_row),
        "grupai": _grupai_of(conn, acct_row["id"]),      # the grúpaí its owner has made public
        "design": json.loads(live["design"]) if live else {},
        "css": live["css"] if live else None,
        "html": live["html"] if live else None,
        "updated_at": live["updated_at"] if live else None,
    }
    if include_tracks_for is not None:
        out["tracks"] = _catalogue_rows(conn, include_tracks_for, owner_id=acct_row["id"])
    return out


@app.get("/api/rooms")
def api_rooms():
    """The directory of public rooms. ?q= searches name/handle/bio, ?kind=
    narrows to artist/label/shop/venue/business/listener."""
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        q = (request.args.get("q") or "").strip().lower()
        kind = (request.args.get("kind") or "").strip().lower()
        rows = conn.execute(
            f"SELECT a.*, (SELECT COUNT(*) FROM gr_tracks t WHERE t.owner_account_id=a.id AND {gr_master.LIVE})"
            "  AS track_count,"
            " (SELECT updated_at FROM gr_rooms r WHERE r.account_id=a.id AND r.is_live=1)"
            "  AS room_updated_at"
            " FROM gr_accounts a WHERE a.is_public=1 AND a.handle IS NOT NULL AND a.hidden_at IS NULL"
            " ORDER BY room_updated_at DESC, a.name"
        ).fetchall()
        rooms = []
        for a in rows:
            if kind and a["kind"] != kind:
                continue
            hay = f"{a['name']} {a['handle']} {a['bio'] or ''}".lower()
            if q and q not in hay:
                continue
            cover = conn.execute(
                "SELECT id, art_path FROM gr_tracks t WHERE owner_account_id=? AND art_path IS NOT NULL"
                f" AND {gr_master.LIVE} ORDER BY added_at DESC LIMIT 4", (a["id"],)).fetchall()
            rooms.append({
                "handle": a["handle"], "name": a["name"], "kind": a["kind"],
                "bio": a["bio"] or "", "track_count": a["track_count"],
                "updated_at": a["room_updated_at"],
                "cover_track_ids": [c["id"] for c in cover],
                "place": _place_of(a),
            })
        return jsonify({"rooms": rooms})


@app.get("/api/rooms/lookup")
def api_rooms_lookup():
    """Which public room, if any, belongs to this artist/label name? Lets the
    app turn a record's artist into a link into their room."""
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        name = (request.args.get("name") or "").strip().lower()
        if not name:
            return jsonify({"handle": None})
        row = conn.execute(
            "SELECT handle FROM gr_accounts WHERE is_public=1 AND handle IS NOT NULL AND hidden_at IS NULL"
            " AND (LOWER(name)=? OR handle=?)", (name, _slug(name))).fetchone()
        if not row:
            # a record they own, under this artist name
            row = conn.execute(
                "SELECT a.handle FROM gr_tracks t JOIN gr_accounts a ON a.id=t.owner_account_id"
                f" WHERE a.is_public=1 AND a.hidden_at IS NULL AND {gr_master.LIVE} AND LOWER(t.artist)=? LIMIT 1",
                (name,)).fetchone()
        return jsonify({"handle": row["handle"] if row else None})


@app.get("/api/rooms/<handle>")
def api_room(handle):
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        a = conn.execute("SELECT * FROM gr_accounts WHERE handle=?", (handle,)).fetchone()
        if not a or (not a["is_public"] and a["id"] != acct["id"]):
            return jsonify({"error": "no such room"}), 404
        if gr_master.is_hidden(a) and a["id"] != acct["id"] and not gr_master.is_master(acct):
            return jsonify({"error": "no such room"}), 404
        design_id = request.args.get("design")
        if design_id and a["id"] != acct["id"]:
            design_id = None      # only the owner previews drafts
        out = _room_public(conn, a, include_tracks_for=acct,
                           design_id=int(design_id) if design_id and design_id.isdigit() else None)
        out["mine"] = a["id"] == acct["id"]
        if gr_master.is_hidden(a):
            out["hidden"] = {"note": a["hidden_note"] or ""}
        if not out["mine"]:
            _event(conn, acct["id"], "room_view", {"room": handle, "kind": a["kind"]})
        return jsonify(out)


# ---------- my room (designs) ----------

@app.get("/api/my/room")
def api_my_room():
    """My account's room settings + every saved design (live or not)."""
    import json
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        designs = [dict(r) for r in conn.execute(
            "SELECT * FROM gr_rooms WHERE account_id=? ORDER BY is_live DESC, updated_at DESC",
            (acct["id"],))]
        for d in designs:
            d["design"] = json.loads(d["design"] or "{}")
        return jsonify({
            "handle": acct["handle"], "name": acct["name"], "kind": acct["kind"],
            "bio": acct["bio"] or "", "links": json.loads(acct["links"] or "[]"),
            "is_public": bool(acct["is_public"]), "designs": designs,
            "place": _place_of(acct),          # None = nowhere in particular
        })


@app.post("/api/my/room/profile")
def api_my_room_profile():
    """Name / handle / bio / links / public toggle — and, only when the request
    carries a "place" key, where the room is: {name, lat, lon} sets it, null
    clears it. A request without the key (an older app) leaves the place alone."""
    import json
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        handle = _slug(data.get("handle") or acct["handle"] or acct["name"])
        clash = conn.execute(
            "SELECT id FROM gr_accounts WHERE handle=? AND id!=?", (handle, acct["id"])).fetchone()
        if clash:
            return jsonify({"error": f"the handle '{handle}' is taken"}), 409
        if "place" in data:
            try:
                place = _place_from_request(data.get("place"))
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            conn.execute("UPDATE gr_accounts SET place_name=?, lat=?, lon=? WHERE id=?",
                         (*place, acct["id"]))
        conn.execute(
            "UPDATE gr_accounts SET name=?, handle=?, bio=?, links=?, is_public=? WHERE id=?",
            ((data.get("name") or acct["name"]).strip(), handle,
             (str(data.get("bio"))[:4000] if data.get("bio") is not None else acct["bio"]),
             json.dumps(data["links"][:20] if isinstance(data["links"], list) else [])[:8000] if "links" in data else acct["links"],
             1 if data.get("is_public", bool(acct["is_public"])) else 0,
             acct["id"]))
        conn.commit()
        return api_my_room()


@app.post("/api/my/room/designs")
def api_my_room_design_save():
    """Create or update a design. {id?, name, design{}, css?, html?}"""
    import json
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        design_json = json.dumps(data.get("design") or {})
        if len(design_json) > MAX_CODE_CHARS * 2 or any(len(str(data.get(k) or "")) > MAX_CODE_CHARS for k in ("css", "html")):
            return jsonify({"error": "that design is too long to keep"}), 413
        did = data.get("id")
        if did:
            own = conn.execute("SELECT id FROM gr_rooms WHERE id=? AND account_id=?",
                               (did, acct["id"])).fetchone()
            if not own:
                return jsonify({"error": "no such design"}), 404
            conn.execute(
                "UPDATE gr_rooms SET name=?, design=?, css=?, html=?, updated_at=? WHERE id=?",
                (data.get("name") or "Untitled", design_json, data.get("css"),
                 data.get("html"), _now(), did))
        else:
            first = conn.execute("SELECT COUNT(*) FROM gr_rooms WHERE account_id=?",
                                 (acct["id"],)).fetchone()[0] == 0
            cur = conn.execute(
                "INSERT INTO gr_rooms(account_id, name, design, css, html, is_live,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (acct["id"], data.get("name") or "Untitled", design_json,
                 data.get("css"), data.get("html"), 1 if first else 0, _now(), _now()))
            did = cur.lastrowid
        conn.commit()
        _event(conn, acct["id"], "design_save", {"design": did, "code": bool(data.get("css") or data.get("html"))})
        return jsonify({"id": did})


@app.post("/api/my/room/designs/<int:did>/live")
def api_my_room_design_live(did):
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        own = conn.execute("SELECT id FROM gr_rooms WHERE id=? AND account_id=?",
                           (did, acct["id"])).fetchone()
        if not own:
            return jsonify({"error": "no such design"}), 404
        conn.execute("UPDATE gr_rooms SET is_live=0 WHERE account_id=?", (acct["id"],))
        conn.execute("UPDATE gr_rooms SET is_live=1, updated_at=? WHERE id=?", (_now(), did))
        conn.commit()
        _event(conn, acct["id"], "design_live", {"design": did})
        return jsonify({"live": did})


@app.delete("/api/my/room/designs/<int:did>")
def api_my_room_design_delete(did):
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute("SELECT * FROM gr_rooms WHERE id=? AND account_id=?",
                           (did, acct["id"])).fetchone()
        if not row:
            return jsonify({"error": "no such design"}), 404
        if row["is_live"]:
            return jsonify({"error": "that design is live — make another live first"}), 409
        conn.execute("DELETE FROM gr_rooms WHERE id=?", (did,))
        conn.commit()
        return jsonify({"deleted": did})


# ---------- room assets (images people upload for their public room) ----------

def assets_dir() -> Path:
    p = Path(db_path())
    return p.parent / f"{p.stem}_assets"


def uploads_dir() -> Path:
    """Records artists upload from the app."""
    p = Path(db_path())
    return p.parent / f"{p.stem}_uploads"


def _ensure_asset_tables(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_assets(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            path TEXT NOT NULL,
            mime TEXT NOT NULL,
            width INTEGER, height INTEGER,
            label TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@app.get("/api/my/room/assets")
def api_my_assets():
    with closing(db()) as conn:
        _ensure_asset_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        rows = conn.execute("SELECT id, mime, width, height, label, created_at FROM gr_assets"
                            " WHERE account_id=? ORDER BY id DESC", (acct["id"],)).fetchall()
        return jsonify({"assets": [dict(r, url=f"/api/assets/{r['id']}") for r in rows]})


@app.post("/api/my/room/assets")
def api_my_assets_upload():
    """An image for a room: resized to at most 1800px on the long side,
    served publicly at /api/assets/<id> (rooms are public pages)."""
    import io

    from PIL import Image

    with closing(db()) as conn:
        _ensure_asset_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        f = request.files.get("image")
        if not f:
            return jsonify({"error": "no image"}), 400
        if (request.form.get("rights") or "").lower() not in ("1", "true", "yes", "on"):
            return jsonify({"error": "please confirm you have the right to show this picture", "need_rights": True}), 400
        raw = f.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            return jsonify({"error": f"that picture is over {MAX_IMAGE_BYTES // (1024 * 1024)} MB"}), 413
        try:
            img = _open_picture(raw)
        except Exception:
            return jsonify({"error": "that isn't an image I can read"}), 400
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if has_alpha else "RGB")
        img.thumbnail((1800, 1800))
        folder = assets_dir() / str(acct["id"])
        folder.mkdir(parents=True, exist_ok=True)
        ext, mime = ("png", "image/png") if has_alpha else ("jpg", "image/jpeg")
        name = f"{secrets.token_hex(8)}.{ext}"
        out = folder / name
        if has_alpha:
            img.save(out, "PNG", optimize=True)
        else:
            img.save(out, "JPEG", quality=86)
        cur = conn.execute(
            "INSERT INTO gr_assets(account_id, path, mime, width, height, label, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (acct["id"], str(out), mime, img.width, img.height,
             (request.form.get("label") or f.filename or "")[:120], _now()))
        gr_master.ensure(conn)
        conn.execute("UPDATE gr_assets SET rights_at=? WHERE id=?", (_now(), cur.lastrowid))
        conn.commit()
        _event(conn, acct["id"], "asset_upload", {"asset": cur.lastrowid, "w": img.width, "h": img.height})
        return jsonify({"id": cur.lastrowid, "url": f"/api/assets/{cur.lastrowid}",
                        "width": img.width, "height": img.height, "mime": mime})


@app.delete("/api/my/room/assets/<int:aid>")
def api_my_assets_delete(aid):
    with closing(db()) as conn:
        _ensure_asset_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute("SELECT * FROM gr_assets WHERE id=? AND account_id=?",
                           (aid, acct["id"])).fetchone()
        if not row:
            return jsonify({"error": "no such image"}), 404
        try:
            os.remove(row["path"])
        except OSError:
            pass
        conn.execute("DELETE FROM gr_assets WHERE id=?", (aid,))
        conn.commit()
        return jsonify({"deleted": aid})


@app.get("/api/assets/<int:aid>")
def api_asset(aid):
    """Public: a room's images need no sign-in (the room is for everyone)."""
    with closing(db()) as conn:
        _ensure_asset_tables(conn)
        row = conn.execute("SELECT g.path, g.mime, a.hidden_at FROM gr_assets g"
                           " LEFT JOIN gr_accounts a ON a.id=g.account_id WHERE g.id=?", (aid,)).fetchone()
    if not row or row["hidden_at"] or not os.path.exists(row["path"]):
        return jsonify({"error": "no such image"}), 404
    resp = send_file(row["path"], mimetype=row["mime"])
    resp.headers["Cache-Control"] = "public, max-age=2592000"
    return resp


# ---------- public grúpaí ----------
# A grúpa is a playlist that holds anything; it is made in its owner's own app
# and is private there. Its owner can make one PUBLIC: the app then sends a
# copy here — its name, what it is, how its cover is drawn, and what is in it
# as WORDS AND LINKS ONLY (titles, who they are by, the owner's notes, links to
# Spotify / SoundCloud / anywhere, small cover pictures). Never audio, never a
# file path. Others find it in Explore and on its owner's public room.
# Each element says where it can be heard: "stream" (a link a listener can play
# through their own Spotify / SoundCloud), "campus" (a record that lives on
# this server: its owner's room is where to borrow or buy it), "local" (a file
# on the owner's laptop only), "own" (the owner's own work, on their laptop
# only), "link", "room", "name" (a label, an artist, a set — a name and no more).

GRUPA_MAX_ITEMS = 500
GRUPA_MAX_ART = 320                # pictures per grúpa (its cover + one per element)
GRUPA_MAX_ART_BYTES = 160_000      # each, as sent (a small JPEG)
_GRUPA_KINDS = ("track", "label", "artist", "place", "set", "room", "grupa", "stream", "link")
_GRUPA_WHERE = ("stream", "campus", "local", "own", "link", "room", "name")


def grupa_art_dir() -> Path:
    p = Path(db_path())
    return p.parent / f"{p.stem}_grupa_art"


def _ensure_grupa_tables(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gr_grupai(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            local_id INTEGER NOT NULL,            -- its number in its owner's own app
            name TEXT NOT NULL,
            description TEXT,
            cover TEXT NOT NULL DEFAULT '{}',     -- JSON: how its cover is drawn
            items TEXT NOT NULL DEFAULT '[]',     -- JSON: what is in it (words and links)
            item_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(account_id, local_id)
        );
        """
    )
    if "hidden_at" not in {r[1] for r in conn.execute("PRAGMA table_info(gr_grupai)")}:
        # the master can take a public grúpa down (gr_master.py)
        conn.execute("ALTER TABLE gr_grupai ADD COLUMN hidden_at TEXT")
        conn.execute("ALTER TABLE gr_grupai ADD COLUMN hidden_note TEXT")
    conn.commit()


def _s(v, n):
    return " ".join(str(v if v is not None else "").split())[:n]


def _web(v, n=1000):
    """A link is kept only if it is a plain web address."""
    v = str(v or "").strip()
    return v[:n] if v.startswith(("https://", "http://")) and " " not in v and "\n" not in v else ""


def _art_key(v):
    import re
    v = str(v or "")
    return v if re.fullmatch(r"[a-z0-9]{1,12}", v) else ""


def _hex6(v):
    import re
    v = str(v or "").strip().lower()
    return v if re.fullmatch(r"#[0-9a-f]{6}", v) else ""


def _grupa_cover_in(raw, art_keys):
    """The cover as its owner's app drew it → only the fields we know."""
    raw = raw if isinstance(raw, dict) else {}
    if raw.get("kind") == "image":
        if _art_key(raw.get("art")) in art_keys:
            return {"kind": "image", "art": raw["art"]}
        if _web(raw.get("url")):
            return {"kind": "image", "url": _web(raw.get("url"))}
    return {"kind": "text", "font": _s(raw.get("font"), 60), "bg": _hex6(raw.get("bg")), "ink": _hex6(raw.get("ink"))}


def _grupa_item_in(raw, art_keys):
    """One element as sent → only the fields we know, each cut to a sane length.
    Anything else in the request is dropped: a file path can't arrive by accident."""
    if not isinstance(raw, dict) or raw.get("kind") not in _GRUPA_KINDS:
        return None
    it = {"kind": raw["kind"], "title": _s(raw.get("title"), 300), "subtitle": _s(raw.get("subtitle"), 300),
          "note": str(raw.get("note") or "").strip()[:2000],
          "where": raw.get("where") if raw.get("where") in _GRUPA_WHERE else "name"}
    for key, n in (("album", 300), ("label", 200), ("source", 40), ("stream_type", 40), ("handle", 80), ("by_ids", 400), ("ai", 12)):
        if raw.get(key):
            it[key] = _s(raw.get(key), n)
    for key in ("url", "image"):
        if _web(raw.get(key)):
            it[key] = _web(raw.get(key))
    if _art_key(raw.get("art")) in art_keys:
        it["art"] = raw["art"]
    for key in ("year", "count", "server_track_id"):
        try:
            if raw.get(key) not in (None, "", False):
                it[key] = int(raw[key])
        except (TypeError, ValueError):
            pass
    try:
        if raw.get("duration_sec"):
            it["duration_sec"] = round(float(raw["duration_sec"]), 1)
    except (TypeError, ValueError):
        pass
    if it["where"] in ("stream", "link") and not it.get("url"):
        it["where"] = "name"
    return it


def _grupa_card(conn, row, viewer_id=None):
    """A public grúpa as a card: enough to show it in a list."""
    import json
    owner = conn.execute("SELECT id, name, handle, kind, is_public FROM gr_accounts WHERE id=?",
                         (row["account_id"],)).fetchone()
    cover = json.loads(row["cover"] or "{}")
    if cover.get("kind") == "image" and cover.get("art"):
        cover["image"] = f"/api/grupai/{row['id']}/art/{cover['art']}"
    elif cover.get("kind") == "image":
        cover["image"] = cover.get("url") or ""
    return {
        "id": row["id"], "name": row["name"], "description": row["description"] or "",
        "count": row["item_count"], "updated_at": row["updated_at"], "cover": cover,
        "owner": {"name": owner["name"] if owner else "", "kind": owner["kind"] if owner else "",
                  # the way to its owner's room, only when that room is public
                  "handle": owner["handle"] if owner and owner["is_public"] and owner["handle"] else None},
        "mine": bool(owner and viewer_id is not None and owner["id"] == viewer_id),
    }


def _grupai_of(conn, account_id, viewer_id=None):
    _ensure_grupa_tables(conn)
    rows = conn.execute("SELECT * FROM gr_grupai WHERE account_id=? AND (hidden_at IS NULL OR ?=account_id)"
                        " ORDER BY updated_at DESC, id DESC", (account_id, viewer_id)).fetchall()
    return [_grupa_card(conn, r, viewer_id) for r in rows]


@app.get("/api/my/grupai")
def api_my_grupai():
    """What this account has public here — so its app can tell what it has sent."""
    with closing(db()) as conn:
        _ensure_grupa_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        rows = conn.execute("SELECT id, local_id, name, item_count, updated_at FROM gr_grupai"
                            " WHERE account_id=? ORDER BY updated_at DESC", (acct["id"],)).fetchall()
        return jsonify({"grupai": [dict(r) for r in rows]})


@app.post("/api/my/grupai")
def api_my_grupai_save():
    """Make a grúpa public, or send it again after it changed.
    {local_id, name, description, cover{…}, items[…], art{key: base64 JPEG}}"""
    import base64
    import json
    import shutil
    data = request.get_json(force=True, silent=True) or {}
    with closing(db()) as conn:
        _ensure_grupa_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        try:
            local_id = int(data.get("local_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "which grúpa?"}), 400
        name = _s(data.get("name"), 200)
        if not name:
            return jsonify({"error": "a grúpa needs a name"}), 400
        # the pictures: small JPEGs, checked before anything is kept
        art = {}
        raw_art = data.get("art") if isinstance(data.get("art"), dict) else {}
        for key, b64 in list(raw_art.items())[:GRUPA_MAX_ART]:
            if not _art_key(key) or not isinstance(b64, str) or len(b64) > GRUPA_MAX_ART_BYTES * 4 // 3 + 8:
                continue
            try:
                blob = base64.b64decode(b64, validate=True)
            except Exception:
                continue
            if blob[:3] == b"\xff\xd8\xff" and len(blob) <= GRUPA_MAX_ART_BYTES:
                art[key] = blob
        raw_items = data.get("items") if isinstance(data.get("items"), list) else []
        items = [i for i in (_grupa_item_in(r, art) for r in raw_items[:GRUPA_MAX_ITEMS]) if i]
        cover = _grupa_cover_in(data.get("cover"), art)
        now = _now()
        row = conn.execute("SELECT id FROM gr_grupai WHERE account_id=? AND local_id=?",
                           (acct["id"], local_id)).fetchone()
        if row:
            gid = row["id"]
            conn.execute("UPDATE gr_grupai SET name=?, description=?, cover=?, items=?, item_count=?, updated_at=?"
                         " WHERE id=?", (name, str(data.get("description") or "").strip()[:2000],
                                         json.dumps(cover), json.dumps(items), len(items), now, gid))
        else:
            gid = conn.execute(
                "INSERT INTO gr_grupai(account_id, local_id, name, description, cover, items, item_count,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (acct["id"], local_id, name, str(data.get("description") or "").strip()[:2000],
                 json.dumps(cover), json.dumps(items), len(items), now, now)).lastrowid
        conn.commit()
        folder = grupa_art_dir() / str(gid)
        shutil.rmtree(folder, ignore_errors=True)          # the pictures are sent whole each time
        if art:
            folder.mkdir(parents=True, exist_ok=True)
            for key, blob in art.items():
                (folder / f"{key}.jpg").write_bytes(blob)
        _event(conn, acct["id"], "grupa_public", {"grupa": gid, "n": len(items), "new": not row})
        return jsonify({"id": gid, "updated_at": now, "count": len(items)})


@app.delete("/api/my/grupai/<int:local_id>")
def api_my_grupai_delete(local_id):
    """Make it private again: it leaves this server altogether."""
    import shutil
    with closing(db()) as conn:
        _ensure_grupa_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute("SELECT id FROM gr_grupai WHERE account_id=? AND local_id=?",
                           (acct["id"], local_id)).fetchone()
        if row:
            conn.execute("DELETE FROM gr_grupai WHERE id=?", (row["id"],))
            conn.commit()
            shutil.rmtree(grupa_art_dir() / str(row["id"]), ignore_errors=True)
            _event(conn, acct["id"], "grupa_private", {"grupa": row["id"]})
        return jsonify({"private": True, "was_public": bool(row)})


@app.get("/api/grupai")
def api_grupai():
    """Every public grúpa, newest first. ?q= looks in the name, what it is and
    who made it; ?handle= narrows to one room's."""
    with closing(db()) as conn:
        _ensure_grupa_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        q = (request.args.get("q") or "").strip().lower()
        handle = (request.args.get("handle") or "").strip().lower()
        rows = conn.execute(
            "SELECT g.*, a.name AS owner_name, a.handle AS owner_handle FROM gr_grupai g"
            " JOIN gr_accounts a ON a.id=g.account_id"
            " WHERE (g.hidden_at IS NULL AND a.hidden_at IS NULL) OR g.account_id=?"
            " ORDER BY g.updated_at DESC, g.id DESC", (acct["id"],)).fetchall()
        out = []
        for r in rows:
            if handle and (r["owner_handle"] or "").lower() != handle:
                continue
            if q and not all(w in f"{r['name']} {r['description'] or ''} {r['owner_name']}".lower() for w in q.split()):
                continue
            out.append(_grupa_card(conn, r, acct["id"]))
        return jsonify({"grupai": out})


@app.get("/api/grupai/<int:gid>")
def api_grupa_public(gid):
    """One public grúpa, with what is in it. A record that lives on this server
    comes with the way to the room it can be borrowed or bought in."""
    import json
    with closing(db()) as conn:
        _ensure_grupa_tables(conn)
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute("SELECT g.*, a.hidden_at AS owner_hidden FROM gr_grupai g"
                           " LEFT JOIN gr_accounts a ON a.id=g.account_id WHERE g.id=?", (gid,)).fetchone()
        if not row or ((row["hidden_at"] or row["owner_hidden"]) and row["account_id"] != acct["id"]
                       and not gr_master.is_master(acct)):
            return jsonify({"error": "no such grúpa"}), 404
        out = _grupa_card(conn, row, acct["id"])
        if row["hidden_at"]:
            out["hidden"] = {"note": row["hidden_note"] or ""}
        items = json.loads(row["items"] or "[]")
        for it in items:
            if it.get("art"):
                it["image"] = f"/api/grupai/{gid}/art/{it['art']}"
            if it.get("where") == "campus" and it.get("server_track_id"):
                t = conn.execute(
                    "SELECT t.id, a.handle, a.name, a.is_public, a.hidden_at, t.status FROM gr_tracks t"
                    " LEFT JOIN gr_accounts a ON a.id=t.owner_account_id WHERE t.id=?",
                    (it["server_track_id"],)).fetchone()
                if t and (t["status"] or "live") != "live":
                    t = None                             # not in the shop (now): as if it had left
                if t and t["handle"] and t["is_public"] and not t["hidden_at"]:
                    it["room"] = {"handle": t["handle"], "name": t["name"]}
                elif not t:
                    it["where"] = "local"            # it has left the server since
        out["items"] = items
        if not out["mine"]:
            _event(conn, acct["id"], "grupa_view", {"grupa": gid})
        return jsonify(out)


@app.get("/api/grupai/<int:gid>/art/<key>")
def api_grupa_art(gid, key):
    """Public, like a room's images: a small cover picture of a public grúpa."""
    if not _art_key(key):
        return jsonify({"error": "no such picture"}), 404
    path = grupa_art_dir() / str(gid) / f"{key}.jpg"
    if not path.exists():
        return jsonify({"error": "no such picture"}), 404
    resp = send_file(str(path), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# ---------- my records (artists / labels upload what they sell and lend) ----------

def _owner_kind_ok(acct):
    return acct["kind"] in ("artist", "label", "shop")


@app.get("/api/my/records")
def api_my_records():
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        gr_shop.ensure(conn)
        rows = conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM gr_borrows b WHERE b.track_id=t.id) AS borrows,"
            " (SELECT COUNT(*) FROM gr_purchases p WHERE p.track_id=t.id) AS purchases"
            " FROM gr_tracks t WHERE t.owner_account_id=? ORDER BY t.added_at DESC", (acct["id"],)).fetchall()
        return jsonify({"records": [{
            "id": r["id"], "title": r["title"], "artist": r["artist"], "album": r["album"],
            "duration_s": r["duration_s"], "format": r["format"], "size_bytes": r["size_bytes"],
            "price_cents": r["price_cents"], "buy_url": r["buy_url"], "has_art": bool(r["art_path"]),
            "art_v": int(os.path.getmtime(r["art_path"])) if r["art_path"] and os.path.exists(r["art_path"]) else 0,
            "borrows": r["borrows"], "purchases": r["purchases"], "added_at": r["added_at"],
            "year": r["year"], "genre": r["genre"] or "", "label": r["label"] or "",
            "status": r["status"] or "live", "review_note": r["review_note"] or "",
        } for r in rows], "can_sell": _owner_kind_ok(acct), "rights_text": RIGHTS_TEXT})


@app.post("/api/my/records")
def api_my_records_upload():
    """An artist's record: the audio (mp3/flac/wav/ogg — not m4a, which can't
    play as a borrow), a cover, a price. Lives under uploads_dir()."""
    import mutagen

    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        if not _owner_kind_ok(acct):
            return jsonify({"error": "only artist, label and shop accounts sell records"}), 403
        if (request.form.get("rights") or "").lower() not in ("1", "true", "yes", "on"):
            return jsonify({"error": "please confirm you hold the rights to sell this record", "need_rights": True}), 400
        f = request.files.get("audio")
        if not f or not f.filename:
            return jsonify({"error": "no audio file"}), 400
        ext = Path(f.filename).suffix.lower()
        if ext not in (".mp3", ".flac", ".wav", ".ogg", ".aiff", ".aif"):
            return jsonify({"error": "mp3, flac, wav, ogg or aiff please (m4a can't play as a borrow)"}), 400
        folder = uploads_dir() / str(acct["id"])
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{secrets.token_hex(8)}{ext}"
        f.save(str(dest))
        held = conn.execute("SELECT COALESCE(SUM(size_bytes),0) FROM gr_tracks WHERE owner_account_id=?",
                            (acct["id"],)).fetchone()[0]
        if held + dest.stat().st_size > MAX_BYTES_PER_ACCOUNT and not gr_master.is_master(acct):
            dest.unlink(missing_ok=True)
            return jsonify({"error": f"your records already take {held // (1024 * 1024)} MB here — "
                                     f"the most one account can hold is {MAX_BYTES_PER_ACCOUNT // (1024 ** 3)} GB"}), 413
        if dest.stat().st_size > MAX_RECORD_BYTES:
            dest.unlink(missing_ok=True)
            return jsonify({"error": f"that file is over {MAX_RECORD_BYTES // (1024 * 1024)} MB"}), 413
        title = (request.form.get("title") or "").strip()
        artist = (request.form.get("artist") or "").strip() or acct["name"]
        album = (request.form.get("album") or "").strip() or None
        duration = None
        try:
            audio = mutagen.File(str(dest), easy=True)
            if audio is not None:
                tags = audio.tags or {}
                title = title or (tags.get("title") or [None])[0] or Path(f.filename).stem
                if audio.info is not None:
                    duration = round(float(audio.info.length), 2)
        except Exception:
            pass
        title = title or Path(f.filename).stem
        try:
            price = int(request.form.get("price_cents") or DEFAULT_TRACK_PRICE_CENTS)
        except ValueError:
            price = DEFAULT_TRACK_PRICE_CENTS
        cur = conn.execute(
            "INSERT INTO gr_tracks(path, filename, title, artist, album, duration_s, format,"
            " size_bytes, price_cents, added_at, owner_account_id, buy_url)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(dest), Path(f.filename).name, title, artist, album, duration, ext.lstrip("."),
             dest.stat().st_size, max(0, price), _now(), acct["id"],
             _web(request.form.get("buy_url")) or None))
        tid = cur.lastrowid
        # it waits for the master before anyone else can see it (the master's own go straight out)
        conn.execute("UPDATE gr_tracks SET status=?, rights_note=?, rights_at=? WHERE id=?",
                     ("live" if gr_master.is_master(acct) else "pending",
                      (request.form.get("rights_note") or RIGHTS_TEXT).strip()[:500], _now(), tid))
        conn.commit()
        # what is printed on it (record shopping asks by these): the owner's
        # own words first, then whatever the file's tags say for the rest
        gr_shop.ensure(conn)
        conn.execute("UPDATE gr_tracks SET year=?, genre=?, label=? WHERE id=?",
                     (gr_shop.clean_year(request.form.get("year")),
                      gr_shop._txt(request.form.get("genre"), 120) or None,
                      gr_shop._txt(request.form.get("label"), 120) or None, tid))
        gr_shop.read_tags(conn, conn.execute("SELECT * FROM gr_tracks WHERE id=?", (tid,)).fetchone())
        conn.commit()
        cover = request.files.get("cover")
        row = conn.execute("SELECT * FROM gr_tracks WHERE id=?", (tid,)).fetchone()
        if cover and cover.filename:
            saved = _save_cover(tid, cover.read())
            if saved:
                conn.execute("UPDATE gr_tracks SET art_path=?, art_source='upload' WHERE id=?", (saved, tid))
                conn.commit()
        else:
            attach_cover(conn, row, online=False)
        _event(conn, acct["id"], "record_upload", {"track_id": tid, "title": title, "price_cents": price})
        return jsonify({"id": tid, "title": title})


@app.post("/api/my/records/<int:tid>")
def api_my_records_edit(tid):
    """Change price / title / artist / album / year / genre / label / outside link, or the cover."""
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute("SELECT * FROM gr_tracks WHERE id=? AND owner_account_id=?",
                           (tid, acct["id"])).fetchone()
        if not row:
            return jsonify({"error": "not one of your records"}), 404
        data = request.form if request.form else (request.get_json(force=True, silent=True) or {})
        sets, params = [], []
        changed_face = False
        for col in ("title", "artist", "album", "buy_url"):
            if col in data:
                v = _web(data.get(col)) if col == "buy_url" else (data.get(col) or "").strip()[:300]
                sets.append(f"{col}=?"); params.append(v or None)
                changed_face = changed_face or (v or None) != row[col]
        if "price_cents" in data:
            try:
                sets.append("price_cents=?"); params.append(max(0, int(data.get("price_cents") or 0)))
            except ValueError:
                pass
        gr_shop.ensure(conn)
        for col in ("genre", "label"):
            if col in data:
                sets.append(f"{col}=?"); params.append(gr_shop._txt(data.get(col), 120) or None)
        if "year" in data:
            sets.append("year=?"); params.append(gr_shop.clean_year(data.get("year")))
        if sets:
            conn.execute(f"UPDATE gr_tracks SET {', '.join(sets)} WHERE id=?", params + [tid])
            conn.commit()
        cover = request.files.get("cover")
        if cover and cover.filename:
            saved = _save_cover(tid, cover.read())
            if saved:
                conn.execute("UPDATE gr_tracks SET art_path=?, art_source='upload' WHERE id=?", (saved, tid))
                conn.commit()
                changed_face = True
        # what a record is called, its cover or its outside link changed after approval → the master looks again
        back = changed_face and (row["status"] or "live") == "live" and not gr_master.is_master(acct)
        if back:
            conn.execute("UPDATE gr_tracks SET status='pending', review_note=NULL WHERE id=?", (tid,))
            conn.commit()
        return jsonify({"ok": True, "status": "pending" if back else (row["status"] or "live")})


@app.delete("/api/my/records/<int:tid>")
def api_my_records_delete(tid):
    with closing(db()) as conn:
        acct, _dev = _auth(conn)
        if not acct:
            return _unauthorized()
        row = conn.execute("SELECT * FROM gr_tracks WHERE id=? AND owner_account_id=?",
                           (tid, acct["id"])).fetchone()
        if not row:
            return jsonify({"error": "not one of your records"}), 404
        taken = conn.execute(
            "SELECT (SELECT COUNT(*) FROM gr_borrows WHERE track_id=?) +"
            " (SELECT COUNT(*) FROM gr_purchases WHERE track_id=?)", (tid, tid)).fetchone()[0]
        if taken:
            return jsonify({"error": "people have borrowed or bought this — it can't be removed, only unlisted"}), 409
        for p in (row["path"], row["art_path"]):
            if p and str(uploads_dir()) in p or (p and str(art_dir()) in p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        conn.execute("DELETE FROM gr_tracks WHERE id=?", (tid,))
        conn.commit()
        return jsonify({"deleted": tid})


# ---------- CLI ----------

def _owner_id(conn, handle):
    if not handle:
        return None
    row = conn.execute("SELECT id FROM gr_accounts WHERE handle=?", (handle,)).fetchone()
    if not row:
        raise SystemExit(f"no account with the handle '{handle}' — invite one first")
    return row["id"]


def add_folder(folder: str, price_cents: int = DEFAULT_TRACK_PRICE_CENTS,
               online_art: bool = False, owner: str | None = None) -> dict:
    """Add every audio file under a folder to the catalogue (files stay in
    place), with covers, owned by the artist/label account `owner` (a
    handle). Tracks already in the pool get a cover if they still lack one,
    and take the owner if given."""
    import mutagen

    added, skipped, failed, covers = 0, 0, 0, 0
    with closing(db()) as conn:
        init_db(conn)
        owner_id = _owner_id(conn, owner)
        for path in sorted(Path(folder).rglob("*")):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
                continue
            if path.name.startswith("."):
                continue
            full = str(path.resolve())
            exists = conn.execute(
                "SELECT * FROM gr_tracks WHERE path=?", (full,)
            ).fetchone()
            if exists:
                skipped += 1
                if not exists["art_path"] and attach_cover(conn, exists, online_art):
                    covers += 1
                if owner_id and exists["owner_account_id"] != owner_id:
                    conn.execute("UPDATE gr_tracks SET owner_account_id=? WHERE id=?",
                                 (owner_id, exists["id"]))
                continue
            title = artist = album = None
            duration = None
            try:
                audio = mutagen.File(full, easy=True)
                if audio is not None:
                    tags = audio.tags or {}
                    title = (tags.get("title") or [None])[0]
                    artist = (tags.get("artist") or [None])[0]
                    album = (tags.get("album") or [None])[0]
                    if audio.info is not None:
                        duration = round(float(audio.info.length), 2)
            except Exception:
                failed += 1
            conn.execute(
                "INSERT INTO gr_tracks(path, filename, title, artist, album,"
                " duration_s, format, size_bytes, price_cents, added_at, owner_account_id)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    full,
                    path.name,
                    title or path.stem,
                    artist,
                    album,
                    duration,
                    path.suffix.lower().lstrip("."),
                    path.stat().st_size,
                    price_cents,
                    _now(),
                    owner_id,
                ),
            )
            added += 1
            row = conn.execute("SELECT * FROM gr_tracks WHERE path=?", (full,)).fetchone()
            gr_shop.read_tags(conn, row)          # year / genre / label, for record shopping
            if attach_cover(conn, row, online_art):
                covers += 1
        conn.commit()
    return {"added": added, "already_there": skipped, "tag_read_failed": failed,
            "covers_found": covers}


def fill_covers(online_art: bool = False) -> dict:
    """Try again for every pool track still without a cover."""
    found, still_missing = 0, 0
    with closing(db()) as conn:
        init_db(conn)
        for row in conn.execute("SELECT * FROM gr_tracks WHERE art_path IS NULL").fetchall():
            if attach_cover(conn, row, online_art):
                found += 1
            else:
                still_missing += 1
    return {"covers_found": found, "still_missing": still_missing}


def make_invite(name: str, kind: str = "listener", handle: str | None = None,
                bio: str | None = None, public: bool = False) -> str:
    if kind not in ACCOUNT_KINDS:
        raise SystemExit(f"kind must be one of {', '.join(ACCOUNT_KINDS)}")
    code = new_code()
    handle = _slug(handle or name)
    with closing(db()) as conn:
        init_db(conn)
        if conn.execute("SELECT 1 FROM gr_accounts WHERE handle=?", (handle,)).fetchone():
            raise SystemExit(f"the handle '{handle}' is taken — pass --handle")
        conn.execute(
            "INSERT INTO gr_accounts(name, invite_code, wallet_cents, created_at,"
            " kind, handle, bio, is_public) VALUES(?,?,?,?,?,?,?,?)",
            (name, code, PLAY_MONEY_START_CENTS, _now(), kind, handle, bio,
             1 if public else 0),
        )
        conn.commit()
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p_add = sub.add_parser("add")
    p_add.add_argument("folder")
    p_add.add_argument("--price", type=int, default=DEFAULT_TRACK_PRICE_CENTS)
    p_add.add_argument("--online-art", action="store_true",
                       help="also look covers up online when nothing local is found")
    p_add.add_argument("--owner", help="handle of the artist/label account these records belong to")
    p_cov = sub.add_parser("covers")
    p_cov.add_argument("--online-art", action="store_true")
    p_inv = sub.add_parser("invite")
    p_inv.add_argument("name")
    p_inv.add_argument("--kind", default="listener", choices=ACCOUNT_KINDS)
    p_inv.add_argument("--handle", help="the room's address, e.g. 'moss-records' (default: from the name)")
    p_inv.add_argument("--bio")
    p_inv.add_argument("--public", action="store_true", help="room visible in the directory from the start")
    sub.add_parser("accounts")
    p_master = sub.add_parser("master", help="make (or name) the master account: it approves records and accounts, settles reports")
    p_master.add_argument("name")
    p_master.add_argument("--handle")
    p_master.add_argument("--off", action="store_true", help="stop this account being a master")
    p_house = sub.add_parser("house", help="mark an account as the Music Room's own: its crates are signed 'The Music Room'")
    p_house.add_argument("handle")
    p_house.add_argument("--off", action="store_true")
    sub.add_parser("listen-copies", help="make every record's shop listening copy now, not on first listen")
    sub.add_parser("usage", help="what each person has done: plan, borrows, buys, play money")
    p_ev = sub.add_parser("events", help="the activity log (latest first)")
    p_ev.add_argument("--kind", help="only this kind, e.g. play / borrow / page")
    p_ev.add_argument("--who", help="only this handle")
    p_ev.add_argument("-n", type=int, default=60)
    p_ev.add_argument("--csv", help="write EVERYTHING to this csv file instead")
    sub.add_parser("feedback", help="in-app feedback and bug reports, latest first")
    p_run = sub.add_parser("run")
    p_run.add_argument("--host", default="0.0.0.0")
    p_run.add_argument("--port", type=int, default=5301)
    args = parser.parse_args(argv)

    if args.cmd == "init":
        with closing(db()) as conn:
            init_db(conn)
        print(f"ready — {db_path()}")
    elif args.cmd == "add":
        result = add_folder(args.folder, args.price, args.online_art, args.owner)
        print(result)
    elif args.cmd == "covers":
        print(fill_covers(args.online_art))
    elif args.cmd == "invite":
        code = make_invite(args.name, args.kind, args.handle, args.bio, args.public)
        print(f"{args.name} ({args.kind}, @{_slug(args.handle or args.name)}): {code}")
    elif args.cmd == "accounts":
        with closing(db()) as conn:
            init_db(conn)
            for a in conn.execute("SELECT * FROM gr_accounts ORDER BY id"):
                print(
                    f"{a['id']:>3}  {a['name']:<20} {a['kind']:<9} @{a['handle'] or '—':<18}"
                    f" {a['invite_code']}  €{a['wallet_cents'] / 100:.2f}"
                    f"  sub:{a['sub_month'] or '—'}  {'public' if a['is_public'] else 'private'}"
                )
    elif args.cmd == "master":
        print(gr_master.make_master(args.name, args.handle, args.off))
    elif args.cmd == "house":
        print(gr_shop.set_house(args.handle, not args.off))
    elif args.cmd == "listen-copies":
        print(gr_shop.make_listen_copies())
    elif args.cmd == "usage":
        print(usage_report())
    elif args.cmd == "events":
        with closing(db()) as conn:
            init_db(conn)
            where, params = [], []
            if args.kind:
                where.append("e.kind=?"); params.append(args.kind)
            if args.who:
                where.append("a.handle=?"); params.append(args.who)
            sql = ("SELECT e.at, a.name, e.kind, e.data FROM gr_events e"
                   " LEFT JOIN gr_accounts a ON a.id=e.account_id"
                   + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY e.at DESC")
            if args.csv:
                import csv
                with open(args.csv, "w", newline="") as fh:
                    w = csv.writer(fh); w.writerow(["at", "who", "kind", "data"])
                    for r in conn.execute(sql, params):
                        w.writerow([r["at"], r["name"], r["kind"], r["data"]])
                print(f"written: {args.csv}")
            else:
                for r in conn.execute(sql + " LIMIT ?", params + [args.n]):
                    print(f"{r['at'][:19]}  {(r['name'] or '—')[:16]:<16} {r['kind']:<12} {(r['data'] or '')[:90]}")
    elif args.cmd == "feedback":
        with closing(db()) as conn:
            init_db(conn)
            for r in conn.execute("SELECT f.*, a.name FROM gr_feedback f LEFT JOIN gr_accounts a ON a.id=f.account_id"
                                  " ORDER BY f.at DESC LIMIT 200"):
                print(f"{r['at'][:16]}  {(r['name'] or '—')[:16]:<16} {r['kind']:<9} {r['page'] or '':<22} {r['note'][:110]}")
    elif args.cmd == "run":
        with closing(db()) as conn:
            init_db(conn)
        app.run(host=args.host, port=args.port, threaded=True)


def usage_rows():
    """Per-account activity — David's view of the experiment."""
    with closing(db()) as conn:
        init_db(conn)
        out = []
        for a in conn.execute("SELECT * FROM gr_accounts ORDER BY id"):
            g = lambda sql, *p: conn.execute(sql, (a["id"],) + p).fetchone()[0]
            out.append({
                "name": a["name"], "kind": a["kind"], "handle": a["handle"],
                "plan": a["plan"], "public": bool(a["is_public"]),
                "wallet_cents": a["wallet_cents"],
                "topups_cents": g("SELECT COALESCE(SUM(cents),0) FROM gr_topups WHERE account_id=?"),
                "borrows": g("SELECT COUNT(*) FROM gr_borrows WHERE account_id=?"),
                "held": g("SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND returned_at IS NULL"),
                "bought": g("SELECT COUNT(*) FROM gr_purchases WHERE account_id=?"),
                "spent_cents": g("SELECT COALESCE(SUM(paid_cents),0) FROM gr_purchases WHERE account_id=?"),
                "devices": g("SELECT COUNT(*) FROM gr_devices WHERE account_id=?"),
                "last_seen": conn.execute(
                    "SELECT MAX(last_seen) FROM gr_devices WHERE account_id=?", (a["id"],)).fetchone()[0],
                "designs": g("SELECT COUNT(*) FROM gr_rooms WHERE account_id=?"),
            })
        return out


def usage_report():
    rows = usage_rows()
    if not rows:
        return "no accounts yet"
    head = f"{'name':<20} {'kind':<9} {'plan':<5} {'borrows':>7} {'held':>5} {'bought':>6} {'spent':>7} {'topped up':>9} {'wallet':>7}  last seen"
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['name'][:20]:<20} {r['kind']:<9} {(r['plan'] or '—'):<5} {r['borrows']:>7} {r['held']:>5}"
            f" {r['bought']:>6} {'€%.2f' % (r['spent_cents'] / 100):>7} {'€%.2f' % (r['topups_cents'] / 100):>9}"
            f" {'€%.2f' % (r['wallet_cents'] / 100):>7}  {(r['last_seen'] or '—')[:16]}")
    return "\n".join(lines)


# record shopping — crates, the counter, blind listening — lives in gr_shop.py
# and is handed this module itself (which may be running as a script)
import gr_shop  # noqa: E402

gr_shop.register(app, sys.modules[__name__])

# the master account and the guardrails (approvals, reports, paused accounts,
# the version everyone should be on, what plug-ins may read) live in gr_master.py
import gr_master  # noqa: E402

gr_master.register(app, sys.modules[__name__])


if __name__ == "__main__":
    main()
