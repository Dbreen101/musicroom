"""Green Room client — the app side of the GR builds.

Talks to a campus gr_server (see gr_server.py): join with an invite code,
browse the catalogue, borrow. A borrow downloads the file ENCRYPTED to
DATA_DIR/green_room/ and keeps its key in the local DB (gr_borrows), so the
file on disk only plays through the app — the Seinnteoir decrypts it in
memory (green_room.decrypt_file) and the plain audio never touches the disk.

Borrowed records ARE rows in `tracks` (GR1 brief, 2026-10-21) so they sit
in the room like any record — marked, filterable, with their cover. The
file row points at the encrypted .mrb with analysis_status='locked', and
tracks.gr_borrow_id links it to the borrow. The protection is a set of
guards: exports, tag-writing, analysis, organise and the integrity scan all
skip locked files, and audio only ever plays through the Seinnteoir.
Buying swaps the locked file for the plain one and clears gr_borrow_id —
the record is then simply theirs.

Uses its own sqlite connections (like seinnteoir_player) so it works from
both request handlers and the player thread.
"""

import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

import requests

from mr_paths import DATA_DIR, DB_PATH

GR_DIR = Path(DATA_DIR) / "green_room"
_TIMEOUT = 6            # seconds; the server is on the same LAN
_DL_TIMEOUT = 120       # a whole file download


class GRError(Exception):
    """A friendly, user-showable Green Room failure."""


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _get_setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                 (key, str(value)))
    conn.commit()


def default_server():
    """A build can carry its server (MR_GR_SERVER) so people never type it."""
    return (os.environ.get("MR_GR_SERVER") or "").strip().rstrip("/")


def _server_url(conn):
    return (_get_setting(conn, "gr_server_url") or default_server()).rstrip("/")


def _headers(conn):
    tok = _get_setting(conn, "gr_token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _fingerprint(conn):
    """A stable id for THIS install — the server's device limit keys on it."""
    fp = _get_setting(conn, "gr_fingerprint")
    if not fp:
        fp = uuid.uuid4().hex
        _set_setting(conn, "gr_fingerprint", fp)
    return fp


def _get(conn, path, **kw):
    url = _server_url(conn)
    if not url:
        raise GRError("no Green Room server set — join first")
    try:
        r = requests.get(url + path, headers=_headers(conn),
                         timeout=kw.pop("timeout", _TIMEOUT), **kw)
    except requests.RequestException:
        raise GRError("the Green Room server can't be reached")
    return r


def _post(conn, path, payload):
    url = _server_url(conn)
    if not url:
        raise GRError("no Green Room server set — join first")
    try:
        r = requests.post(url + path, json=payload, headers=_headers(conn),
                          timeout=_TIMEOUT)
    except requests.RequestException:
        raise GRError("the Green Room server can't be reached")
    return r


def _err_of(r, fallback):
    try:
        return r.json().get("error") or fallback
    except Exception:
        return fallback


# ───────────────────────── account ─────────────────────────

def join(server_url, invite_code, device_name=""):
    """Join (or rejoin) the campus server. Saves the server + token."""
    server_url = (server_url or default_server()).strip().rstrip("/")
    invite_code = (invite_code or "").strip()
    if not server_url or not invite_code:
        raise GRError("a server address and an invite code are both needed")
    if not server_url.startswith("http"):
        server_url = "http://" + server_url
    with closing(_db()) as conn:
        fp = _fingerprint(conn)
        try:
            r = requests.post(server_url + "/api/join",
                              json={"invite_code": invite_code,
                                    "fingerprint": fp,
                                    "device_name": device_name or "laptop"},
                              timeout=_TIMEOUT)
        except requests.RequestException:
            raise GRError("that address didn't answer — is the server running?")
        if r.status_code != 200:
            raise GRError(_err_of(r, "the server refused the invite code"))
        d = r.json()
        _set_setting(conn, "gr_server_url", server_url)
        _set_setting(conn, "gr_token", d["token"])
        _set_setting(conn, "gr_name", d.get("name") or "")
        _set_setting(conn, "gr_invite_code", d.get("invite_code") or invite_code)
        return {"joined": True, "name": d.get("name"),
                "wallet_cents": d.get("wallet_cents")}


def status():
    """Everything the /greenroom page needs in one call. Never raises —
    unreachable servers are reported, not thrown."""
    with closing(_db()) as conn:
        out = {
            "server_url": _server_url(conn),
            "default_server": default_server(),
            "joined": bool(_get_setting(conn, "gr_token")),
            "name": _get_setting(conn, "gr_name"),
            "invite_code": _get_setting(conn, "gr_invite_code"),
            "reachable": False,
            "me": None,
        }
        out["borrowed"] = borrowed_list()
        if out["joined"] and out["server_url"]:
            try:
                r = _get(conn, "/api/me")
                if r.status_code == 200:
                    out["reachable"] = True
                    out["me"] = r.json()
            except GRError:
                pass
        return out


# ───────────────────────── catalogue + borrows ─────────────────────────

def catalogue():
    """The server's catalogue, with each track's local state attached."""
    with closing(_db()) as conn:
        r = _get(conn, "/api/catalogue")
        if r.status_code != 200:
            raise GRError(_err_of(r, "the server wouldn't share its catalogue"))
        tracks = r.json().get("tracks") or []
        local = {row["server_track_id"]: dict(row) for row in conn.execute(
            "SELECT * FROM gr_borrows WHERE returned_at IS NULL")}
        for t in tracks:
            mine = local.get(t["id"])
            t["local_id"] = mine["id"] if mine else None
            t["on_disk"] = bool(mine and mine["file_path"])
        return tracks


def _well_id(conn):
    row = conn.execute("SELECT id FROM places WHERE is_well=1").fetchone()
    return row["id"] if row else None


def _ensure_track_row(conn, borrow):
    """Give a borrow its place among the records: a tracks row + a files row
    pointing at the locked file. Reuses the rows if the same borrow was
    offloaded and is coming back."""
    if borrow["track_id"]:
        t = conn.execute("SELECT id FROM tracks WHERE id=?", (borrow["track_id"],)).fetchone()
        if t:
            conn.execute("UPDATE tracks SET is_deleted=0, deleted_at=NULL WHERE id=?",
                         (borrow["track_id"],))
            conn.execute("UPDATE files SET is_deleted=0, file_path=? WHERE track_id=?",
                         (borrow["file_path"], borrow["track_id"]))
            conn.commit()
            return borrow["track_id"]
    cur = conn.execute(
        "INSERT INTO tracks(title, artist_name, album, needs_review, gr_borrow_id, gr_track_id)"
        " VALUES(?,?,?,0,?,?)",
        (borrow["title"], borrow["artist"], borrow["album"], borrow["id"],
         borrow["server_track_id"]))
    tid = cur.lastrowid
    size_mb = round((borrow["size_bytes"] or 0) / (1024 * 1024), 3)
    conn.execute(
        "INSERT INTO files(track_id, file_path, file_format, file_size_mb, duration_sec,"
        " is_primary, has_analysis, analysis_status) VALUES(?,?,?,?,?,1,0,'locked')",
        (tid, borrow["file_path"], borrow["format"], size_mb, borrow["duration_s"]))
    well = _well_id(conn)
    if well:
        conn.execute("INSERT OR IGNORE INTO place_tracks(place_id, track_id) VALUES(?,?)",
                     (well, tid))
    conn.execute("UPDATE gr_borrows SET track_id=? WHERE id=?", (tid, borrow["id"]))
    conn.commit()
    return tid


def _set_track_cover(conn, track_id, server_track_id):
    try:
        cp = cover_path(server_track_id)
    except Exception:
        cp = None
    if cp:
        conn.execute("UPDATE tracks SET artwork_path=?, artwork_source='green_room'"
                     " WHERE id=? AND artwork_path IS NULL", (cp, track_id))
        conn.commit()


def _download_locked(conn, row):
    """Pull the encrypted bytes for a borrow row down to GR_DIR."""
    GR_DIR.mkdir(parents=True, exist_ok=True)
    dest = GR_DIR / f"borrow_{row['server_borrow_id']}.mrb"
    try:
        r = _get(conn, f"/api/download/{row['server_borrow_id']}",
                 timeout=_DL_TIMEOUT, stream=True)
    except GRError:
        raise
    if r.status_code != 200:
        raise GRError(_err_of(r, "the server wouldn't send the file"))
    tmp = dest.with_suffix(".part")
    with open(tmp, "wb") as fh:
        for chunk in r.iter_content(256 * 1024):
            fh.write(chunk)
    os.replace(tmp, dest)
    conn.execute("UPDATE gr_borrows SET file_path=? WHERE id=?",
                 (str(dest), row["id"]))
    conn.commit()
    return str(dest)


def borrow(server_track_id):
    """Borrow a track and download it. Idempotent server-side."""
    with closing(_db()) as conn:
        r = _post(conn, "/api/borrow", {"track_id": server_track_id})
        if r.status_code != 200:
            raise GRError(_err_of(r, "the server refused the borrow"))
        b = r.json()
        conn.execute(
            "INSERT INTO gr_borrows(server_borrow_id, server_track_id, title,"
            " artist, format, size_bytes, key_hex, nonce_hex)"
            " VALUES(?,?,?,?,?,?,?,?)"
            " ON CONFLICT(server_borrow_id) DO UPDATE SET"
            "   key_hex=excluded.key_hex, nonce_hex=excluded.nonce_hex,"
            "   returned_at=NULL",
            (b["borrow_id"], b["track_id"], b.get("title"), b.get("artist"),
             b.get("format"), b.get("size_bytes"), b["key"], b["nonce"]))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM gr_borrows WHERE server_borrow_id=?",
            (b["borrow_id"],)).fetchone()
        # fill in catalogue metadata the borrow payload doesn't carry
        try:
            cr = _get(conn, "/api/catalogue")
            for t in (cr.json().get("tracks") or []):
                if t["id"] == b["track_id"]:
                    conn.execute(
                        "UPDATE gr_borrows SET album=?, duration_s=?,"
                        " price_cents=? WHERE id=?",
                        (t.get("album"), t.get("duration_s"),
                         t.get("price_cents"), row["id"]))
                    conn.commit()
                    break
        except GRError:
            pass
        _download_locked(conn, row)
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=?", (row["id"],)).fetchone()
        tid = _ensure_track_row(conn, row)
        _set_track_cover(conn, tid, b["track_id"])
    return borrow_row(row["id"])


def redownload(local_id):
    """Bring an offloaded borrow's bytes back onto this disk."""
    track("redownload", {"borrow": local_id})
    with closing(_db()) as conn:
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=? AND returned_at IS NULL",
                           (local_id,)).fetchone()
        if not row:
            raise GRError("no such borrow")
        _download_locked(conn, row)
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=?", (local_id,)).fetchone()
        _ensure_track_row(conn, row)
        return borrow_row(local_id)


def offload(local_id):
    """Take a borrow's bytes off this disk; the borrow — and its record in
    the room — are kept. The record shows as 'not downloaded'."""
    track("offload", {"borrow": local_id})
    with closing(_db()) as conn:
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=?", (local_id,)).fetchone()
        if not row:
            raise GRError("no such borrow")
        if row["file_path"] and os.path.exists(row["file_path"]):
            os.remove(row["file_path"])
        conn.execute("UPDATE gr_borrows SET file_path=NULL WHERE id=?", (local_id,))
        conn.commit()
        return borrow_row(local_id)


def _retire_track_row(conn, track_id):
    """A borrow's record leaves the room (returned). Soft-delete, like the
    app's own remove — nothing is ever hard-deleted."""
    if not track_id:
        return
    conn.execute("UPDATE tracks SET is_deleted=1, deleted_at=datetime('now') WHERE id=?",
                 (track_id,))
    conn.execute("UPDATE files SET is_deleted=1, deleted_at=datetime('now') WHERE track_id=?",
                 (track_id,))
    conn.execute("DELETE FROM place_tracks WHERE track_id=?", (track_id,))
    conn.execute("DELETE FROM set_tracks WHERE track_id=?", (track_id,))


def give_back(local_id):
    """Return a borrow: tell the server, delete the local file, retire the
    record from the room."""
    with closing(_db()) as conn:
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=? AND returned_at IS NULL",
                           (local_id,)).fetchone()
        if not row:
            raise GRError("no such borrow")
        r = _post(conn, "/api/return", {"borrow_id": row["server_borrow_id"]})
        if r.status_code not in (200, 404):   # 404 = the server already let it go
            raise GRError(_err_of(r, "the server wouldn't take it back"))
        if row["file_path"] and os.path.exists(row["file_path"]):
            os.remove(row["file_path"])
        conn.execute("UPDATE gr_borrows SET file_path=NULL,"
                     " returned_at=datetime('now') WHERE id=?", (local_id,))
        _retire_track_row(conn, row["track_id"])
        conn.commit()
        return {"returned": True, "track_id": row["track_id"]}


def _purchase_dir(conn):
    """Where bought files land: the Music Room Library if one is known,
    otherwise a folder under the app's data."""
    dest = (_get_setting(conn, "library_dest") or "").strip()
    if dest and os.path.isdir(dest):
        return Path(dest) / "Green Room"
    return GR_DIR / "bought"


def buy(local_id):
    """Buy a borrowed record outright. The server works out the price (minus
    this month's credit), delivers the PLAIN file, and the record simply
    becomes one of theirs: locked file gone, gr_borrow_id cleared, analysis
    free to run."""
    with closing(_db()) as conn:
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=?", (local_id,)).fetchone()
        if not row:
            raise GRError("no such borrow")
        r = _post(conn, "/api/buy", {"track_id": row["server_track_id"]})
        if r.status_code != 200:
            raise GRError(_err_of(r, "the server wouldn't sell it"))
        sale = r.json()
        try:
            dl = _get(conn, sale["url"], timeout=_DL_TIMEOUT, stream=True)
        except GRError:
            raise GRError("bought — but the file didn't arrive. Try 'download' again later.")
        if dl.status_code != 200:
            raise GRError(_err_of(dl, "bought, but the server wouldn't send the file"))
        folder = _purchase_dir(conn) / _safe_name(row["artist"], "Unknown artist")
        folder.mkdir(parents=True, exist_ok=True)
        fname = _safe_name(sale.get("filename"), f"{_safe_name(row['title'], 'record')}.{_safe_name(row['format'], 'mp3')}")
        dest = _inside(folder, fname)
        n = 2
        while dest.exists():
            dest = folder / f"{dest.stem} ({n}){dest.suffix}"
            n += 1
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in dl.iter_content(256 * 1024):
                fh.write(chunk)
        os.replace(tmp, dest)
        if row["file_path"] and os.path.exists(row["file_path"]):
            os.remove(row["file_path"])
        if row["track_id"]:
            conn.execute(
                "UPDATE files SET file_path=?, file_format=?, analysis_status=NULL"
                " WHERE track_id=?", (str(dest), dest.suffix.lstrip(".").lower(), row["track_id"]))
            conn.execute("UPDATE tracks SET gr_borrow_id=NULL, source_type=COALESCE(source_type,'green_room')"
                         " WHERE id=?", (row["track_id"],))
        conn.execute("UPDATE gr_borrows SET file_path=NULL, returned_at=datetime('now') WHERE id=?",
                     (local_id,))
        conn.commit()
        _wish_bought(conn, row["server_track_id"], row["track_id"])
        return {"bought": True, "paid_cents": sale.get("paid_cents", 0),
                "credit_cents": sale.get("credit_cents", 0),
                "artist_cents": sale.get("artist_cents"), "path": str(dest),
                "track_id": row["track_id"]}


def buy_track(server_track_id):
    """Buy a pool record outright. If it's borrowed, the borrow turns into
    ownership (see buy); if not, it's bought at full price and arrives as a
    new record in the room."""
    with closing(_db()) as conn:
        active = conn.execute(
            "SELECT id FROM gr_borrows WHERE server_track_id=? AND returned_at IS NULL",
            (server_track_id,)).fetchone()
    if active:
        return buy(active["id"])
    with closing(_db()) as conn:
        r = _post(conn, "/api/buy", {"track_id": server_track_id})
        if r.status_code != 200:
            raise GRError(_err_of(r, "the server wouldn't sell it"))
        sale = r.json()
        meta = {}
        try:
            for t in (_get(conn, "/api/catalogue").json().get("tracks") or []):
                if t["id"] == server_track_id:
                    meta = t
                    break
        except GRError:
            pass
        try:
            dl = _get(conn, sale["url"], timeout=_DL_TIMEOUT, stream=True)
        except GRError:
            raise GRError("bought — but the file didn't arrive. Try again later.")
        if dl.status_code != 200:
            raise GRError(_err_of(dl, "bought, but the server wouldn't send the file"))
        folder = _purchase_dir(conn) / _safe_name(meta.get("artist"), "Unknown artist")
        folder.mkdir(parents=True, exist_ok=True)
        fname = _safe_name(sale.get("filename"), f"{_safe_name(meta.get('title'), 'record')}.{_safe_name(sale.get('format'), 'mp3')}")
        dest = _inside(folder, fname)
        n = 2
        while dest.exists():
            dest = folder / f"{Path(fname).stem} ({n}){Path(fname).suffix}"
            n += 1
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in dl.iter_content(256 * 1024):
                fh.write(chunk)
        os.replace(tmp, dest)
        cur = conn.execute(
            "INSERT INTO tracks(title, artist_name, album, needs_review, gr_track_id, source_type)"
            " VALUES(?,?,?,0,?,'green_room')",
            (meta.get("title") or Path(fname).stem, meta.get("artist"), meta.get("album"),
             server_track_id))
        tid = cur.lastrowid
        conn.execute(
            "INSERT INTO files(track_id, file_path, file_format, file_size_mb, duration_sec,"
            " is_primary, has_analysis) VALUES(?,?,?,?,?,1,0)",
            (tid, str(dest), dest.suffix.lstrip(".").lower(),
             round(dest.stat().st_size / (1024 * 1024), 3), meta.get("duration_s")))
        well = _well_id(conn)
        if well:
            conn.execute("INSERT OR IGNORE INTO place_tracks(place_id, track_id) VALUES(?,?)",
                         (well, tid))
        conn.commit()
        _set_track_cover(conn, tid, server_track_id)
        _wish_bought(conn, server_track_id, tid)
        return {"bought": True, "paid_cents": sale.get("paid_cents", 0),
                "credit_cents": sale.get("credit_cents", 0),
                "artist_cents": sale.get("artist_cents"), "path": str(dest), "track_id": tid}


def _wish_bought(conn, server_track_id, track_id=None):
    """Buying a record takes it off the wishlist: its line there becomes
    "owned" (and stops counting toward the 100 the wishlist holds)."""
    try:
        conn.execute(
            "UPDATE wishlist SET status='supported', bought_via='music room', fulfilled_at=datetime('now'),"
            " fulfilled_track_id=COALESCE(?, fulfilled_track_id) WHERE gr_track_id=? AND status != 'supported'",
            (track_id, int(server_track_id)))
        conn.commit()
    except sqlite3.OperationalError:
        pass          # a library from before wishes could point at a Music Room record


# ───────────────────────── profiles + plans ─────────────────────────

def _safe_name(v, fallback):
    """A file or folder name that came from the server (or a seller) made safe to
    use on this laptop: one plain name, never a path, never '.' or '..'."""
    name = Path(str(v or "").replace("\\", "/")).name.strip().replace(":", "-")
    name = "".join(ch for ch in name if ch >= " ")[:180].strip(". ")
    return name if name and name not in (".", "..") else fallback


def _inside(folder, fname):
    """folder / fname, refusing anything that would land outside folder."""
    dest = Path(folder) / fname
    if dest.resolve().parent != Path(folder).resolve():
        raise GRError("the file's name from the server wasn't safe to use")
    return dest                          # (as the app writes paths elsewhere — not Windows' long form of it)


def signup(server_url, name, device_name="", kind="listener", agreed=False):
    """Make a profile on the server (no invite) and sign this laptop in. Every
    new account is a listener; any other `kind` goes to the master as a
    request (gr_master.py). `agreed`: the house rules were read and agreed to."""
    server_url = (server_url or default_server()).strip().rstrip("/")
    name = (name or "").strip()
    if not server_url or not name:
        raise GRError("a server address and a name are both needed")
    if not server_url.startswith("http"):
        server_url = "http://" + server_url
    with closing(_db()) as conn:
        fp = _fingerprint(conn)
        try:
            r = requests.post(server_url + "/api/signup",
                              json={"name": name, "fingerprint": fp,
                                    "kind_requested": kind if kind and kind != "listener" else "",
                                    "agreed": bool(agreed), "device_name": device_name or "laptop"},
                              timeout=_TIMEOUT)
        except requests.RequestException:
            raise GRError("that address didn't answer — is the server running?")
        if r.status_code != 200:
            raise GRError(_err_of(r, "the server wouldn't make the profile"))
        d = r.json()
        _set_setting(conn, "gr_server_url", server_url)
        _set_setting(conn, "gr_token", d["token"])
        _set_setting(conn, "gr_name", d.get("name") or name)
        _set_setting(conn, "gr_invite_code", d.get("invite_code") or "")
        return {"joined": True, "name": d.get("name"), "handle": d.get("handle"),
                "invite_code": d.get("invite_code"), "wallet_cents": d.get("wallet_cents"),
                "kind_requested": d.get("kind_requested") or ""}


def plans():
    with closing(_db()) as conn:
        return _json_or_raise(_get(conn, "/api/plans"), "the plans can't be read").get("plans", [])


def choose_plan(key):
    with closing(_db()) as conn:
        return _json_or_raise(_post(conn, "/api/me/plan", {"plan": key}), "that plan wasn't set")


def has_plan():
    st = status()
    return bool(st.get("me") and st["me"].get("plan"))


# ───────────────────────── activity + feedback ─────────────────────────
# App-side events queue locally and go up in batches; the server logs its
# own (borrow, buy, room views…). Nothing here is sent unless signed in.

def track(kind, data=None):
    """Note something the person did. Never raises, never blocks."""
    import json
    try:
        with closing(_db()) as conn:
            conn.execute("INSERT INTO gr_events_outbox(kind, data) VALUES(?,?)",
                         (str(kind)[:40], json.dumps(data) if data is not None else None))
            conn.commit()
    except Exception:
        pass


def flush_events(limit=300):
    """Send queued events. Returns how many went. Quiet on any failure."""
    import json
    try:
        with closing(_db()) as conn:
            if not _get_setting(conn, "gr_token") or not _server_url(conn):
                return 0
            rows = conn.execute(
                "SELECT * FROM gr_events_outbox ORDER BY id LIMIT ?", (limit,)).fetchall()
            if not rows:
                return 0
            payload = {"events": [{"kind": r["kind"], "at": r["at"],
                                   "data": json.loads(r["data"]) if r["data"] else None}
                                  for r in rows]}
            r = _post(conn, "/api/events", payload)
            if r.status_code != 200:
                return 0
            conn.execute("DELETE FROM gr_events_outbox WHERE id <= ?", (rows[-1]["id"],))
            conn.commit()
            return len(rows)
    except Exception:
        return 0


def send_feedback(kind, note, page=None, context=None):
    """Forward an in-app feedback note to the server (best effort)."""
    try:
        with closing(_db()) as conn:
            if not _get_setting(conn, "gr_token"):
                return False
            r = _post(conn, "/api/feedback", {"kind": kind, "note": note, "page": page,
                                              "context": context})
            return r.status_code == 200
    except Exception:
        return False


# ───────────────────────── the basket ─────────────────────────

def basket():
    with closing(_db()) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM gr_basket ORDER BY added_at, id")]
    return rows


def basket_add(server_track_id, mode="borrow"):
    """Set a pool record aside. Looks its details up from the server so the
    line reads well; falls back to just the id if the server is away."""
    mode = "buy" if mode == "buy" else "borrow"
    track("basket_add", {"track_id": int(server_track_id), "mode": mode})
    meta = {}
    with closing(_db()) as conn:
        try:
            for t in (_get(conn, "/api/catalogue").json().get("tracks") or []):
                if t["id"] == int(server_track_id):
                    meta = t
                    break
        except GRError:
            pass
        conn.execute(
            "INSERT INTO gr_basket(server_track_id, mode, title, artist, owner_handle, owner_name,"
            " price_cents, has_art, art_v) VALUES(?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(server_track_id) DO UPDATE SET mode=excluded.mode",
            (int(server_track_id), mode, meta.get("title"), meta.get("artist"),
             meta.get("owner_handle"), meta.get("owner_name"), meta.get("price_cents"),
             1 if meta.get("has_art") else 0, meta.get("art_v") or 0))
        conn.commit()
    return basket()


def basket_mode(basket_id, mode):
    mode = "buy" if mode == "buy" else "borrow"
    with closing(_db()) as conn:
        conn.execute("UPDATE gr_basket SET mode=? WHERE id=?", (mode, basket_id))
        conn.commit()
    return basket()


def basket_remove(basket_id):
    track("basket_remove", {"basket_id": basket_id})
    with closing(_db()) as conn:
        conn.execute("DELETE FROM gr_basket WHERE id=?", (basket_id,))
        conn.commit()
    return basket()


def basket_checkout():
    """Borrow and buy everything in the basket. Needs a plan if anything is
    to be borrowed (the page sends people to /subscribe first). Each line
    reports its own outcome; the ones that worked leave the basket."""
    rows = basket()
    if any(r["mode"] == "borrow" for r in rows) and not has_plan():
        raise GRError("choose a subscription before borrowing")
    results = []
    for r in rows:
        try:
            if r["mode"] == "buy":
                out = buy_track(r["server_track_id"])
                results.append({"id": r["id"], "title": r["title"], "mode": "buy", "ok": True,
                                "paid_cents": out.get("paid_cents", 0)})
            else:
                out = borrow(r["server_track_id"])
                results.append({"id": r["id"], "title": r["title"], "mode": "borrow", "ok": True})
            basket_remove(r["id"])
        except GRError as e:
            results.append({"id": r["id"], "title": r["title"], "mode": r["mode"], "ok": False,
                            "error": str(e)})
    return {"results": results, "basket": basket()}


# ───────────────────────── rooms (other people's, and mine) ─────────────────────────

def _json_or_raise(r, fallback):
    if r.status_code != 200:
        raise GRError(_err_of(r, fallback))
    return r.json()


def rooms(q="", kind=""):
    with closing(_db()) as conn:
        r = _get(conn, "/api/rooms", params={"q": q or "", "kind": kind or ""})
        return _json_or_raise(r, "the directory can't be read right now").get("rooms", [])


def room_lookup(name):
    with closing(_db()) as conn:
        try:
            r = _get(conn, "/api/rooms/lookup", params={"name": name or ""})
        except GRError:
            return None
        if r.status_code != 200:
            return None
        return r.json().get("handle")


def room(handle, design_id=None):
    with closing(_db()) as conn:
        params = {"design": design_id} if design_id else None
        r = _get(conn, f"/api/rooms/{handle}", params=params)
        return _json_or_raise(r, "that room can't be opened")


def my_room():
    with closing(_db()) as conn:
        return _json_or_raise(_get(conn, "/api/my/room"), "your room can't be read right now")


def my_room_profile(data):
    with closing(_db()) as conn:
        out = _json_or_raise(_post(conn, "/api/my/room/profile", data), "the profile wasn't saved")
        if out.get("name"):
            _set_setting(conn, "gr_name", out["name"])
        return out


def set_my_place(place):
    """Where my room is, for the Globe in Explore: {"name", "lat", "lon"} puts
    it on the globe (the name is the owner's own words; nothing is looked up),
    None takes it off — nowhere in particular, "universal". Only the place is
    sent, so the rest of the profile stays as it is. Returns the profile as the
    server now has it; a server from before places ignores the key and answers
    without one (see server_keeps_places)."""
    return my_room_profile({"place": place})


def server_keeps_places(profile):
    """Did this answer come from a server that knows about places?"""
    return isinstance(profile, dict) and "place" in profile


# ───────────────────────── public grúpaí ─────────────────────────
# A grúpa is private until its owner makes it public; then a copy of what it
# is — words, links, small cover pictures, never audio — goes to the rooms
# server, where others find it in Explore and on the owner's public room.

GRUPA_NO_SERVER = "The rooms server here doesn't keep grúpaí yet. It needs one restart."      # said to someone looking
GRUPA_OLD_SERVER = GRUPA_NO_SERVER[:-1] + "; this grúpa will go up by itself after that."        # said to someone making one public


def _grupa_server_too_old(r):
    """A rooms server from before public grúpaí answers their addresses with a
    plain "not found" page rather than with an answer of its own."""
    return r.status_code in (404, 405) and "json" not in (r.headers.get("Content-Type") or "")


def grupa_publish(payload):
    """Send a grúpa up (the first time, or again after it changed). → {id, updated_at, count}"""
    with closing(_db()) as conn:
        r = _post(conn, "/api/my/grupai", payload)
        if _grupa_server_too_old(r):
            raise GRError(GRUPA_OLD_SERVER)
        return _json_or_raise(r, "the grúpa couldn't be made public")


def grupa_unpublish(local_id):
    """Take it down again. Fine if it was never up; fine on a server from before grúpaí."""
    with closing(_db()) as conn:
        r = _delete(conn, f"/api/my/grupai/{int(local_id)}")
        if _grupa_server_too_old(r):
            return {"private": True, "was_public": False}
        return _json_or_raise(r, "the grúpa couldn't be made private")


def public_grupai(q="", handle=""):
    """Every public grúpa (newest first), or one room's. An older server → []."""
    with closing(_db()) as conn:
        r = _get(conn, "/api/grupai", params={"q": q or "", "handle": handle or ""})
        if _grupa_server_too_old(r):
            raise GRError(GRUPA_NO_SERVER)
        return _json_or_raise(r, "the grúpaí can't be read right now").get("grupai", [])


def public_grupa(gid):
    with closing(_db()) as conn:
        r = _get(conn, f"/api/grupai/{int(gid)}")
        if _grupa_server_too_old(r):
            raise GRError(GRUPA_NO_SERVER)
        return _json_or_raise(r, "that grúpa can't be opened")


def grupa_art_bytes(gid, key, v=""):
    """A public grúpa's small picture, kept locally once fetched. `v` is the
    grúpa's own "last changed" stamp: a changed grúpa asks again."""
    import re
    if not re.fullmatch(r"[a-z0-9]{1,12}", str(key or "")):
        return None
    tag = re.sub(r"[^0-9a-zA-Z]", "", str(v or ""))[:20] or "0"
    cache = GR_DIR / "grupa_art" / str(int(gid))
    hit = cache / f"{key}.{tag}.jpg"
    if hit.exists():
        return hit.read_bytes()
    with closing(_db()) as conn:
        url = _server_url(conn)
    if not url:
        return None
    try:
        r = requests.get(url + f"/api/grupai/{int(gid)}/art/{key}", timeout=_TIMEOUT)
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.content.startswith(b"\xff\xd8\xff"):
        return None
    try:
        cache.mkdir(parents=True, exist_ok=True)
        for old in cache.glob(f"{key}.*.jpg"):          # an earlier picture under this key
            old.unlink(missing_ok=True)
        hit.write_bytes(r.content)
    except OSError:
        pass
    return r.content


def save_design(data):
    with closing(_db()) as conn:
        return _json_or_raise(_post(conn, "/api/my/room/designs", data), "the design wasn't saved")


def design_live(design_id):
    with closing(_db()) as conn:
        return _json_or_raise(_post(conn, f"/api/my/room/designs/{design_id}/live", {}),
                              "couldn't make that design live")


def _delete(conn, path):
    url = _server_url(conn)
    if not url:
        raise GRError("no server set — sign in first")
    try:
        return requests.delete(url + path, headers=_headers(conn), timeout=_TIMEOUT)
    except requests.RequestException:
        raise GRError("the server can't be reached")


def _post_files(conn, path, files, data=None):
    url = _server_url(conn)
    if not url:
        raise GRError("no server set — sign in first")
    try:
        return requests.post(url + path, files=files, data=data or {}, headers=_headers(conn),
                             timeout=_DL_TIMEOUT)
    except requests.RequestException:
        raise GRError("the server can't be reached")


def my_assets():
    with closing(_db()) as conn:
        return _json_or_raise(_get(conn, "/api/my/room/assets"), "your images can't be read").get("assets", [])


def upload_asset(filename, data, mime, label="", rights=""):
    with closing(_db()) as conn:
        r = _post_files(conn, "/api/my/room/assets", {"image": (filename, data, mime)}, {"label": label, "rights": rights})
        out = _json_or_raise(r, "the image wasn't accepted")
        track("asset_upload", {"asset": out.get("id")})
        return out


def delete_asset(asset_id):
    with closing(_db()) as conn:
        return _json_or_raise(_delete(conn, f"/api/my/room/assets/{asset_id}"), "couldn't delete that image")


def asset_bytes(asset_id):
    """A room image, cached locally so rooms still look right offline."""
    cache = GR_DIR / "assets"
    hit = next(iter(cache.glob(f"{int(asset_id)}.*")), None) if cache.exists() else None
    if hit:
        return hit.read_bytes(), ("image/png" if hit.suffix == ".png" else "image/jpeg")
    with closing(_db()) as conn:
        url = _server_url(conn)
        if not url:
            return None, None
        try:
            r = requests.get(url + f"/api/assets/{int(asset_id)}", timeout=_TIMEOUT)
        except requests.RequestException:
            return None, None
    if r.status_code != 200:
        return None, None
    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    cache.mkdir(parents=True, exist_ok=True)
    (cache / f"{int(asset_id)}.{'png' if mime == 'image/png' else 'jpg'}").write_bytes(r.content)
    return r.content, mime


def my_records():
    with closing(_db()) as conn:
        return _json_or_raise(_get(conn, "/api/my/records"), "your records can't be read")


def upload_record(audio, cover=None, fields=None):
    """audio / cover = (filename, bytes, mime)."""
    files = {"audio": audio}
    if cover:
        files["cover"] = cover
    with closing(_db()) as conn:
        r = _post_files(conn, "/api/my/records", files, fields or {})
        return _json_or_raise(r, "the record wasn't accepted")


def edit_record(track_id, fields, cover=None):
    with closing(_db()) as conn:
        if cover:
            r = _post_files(conn, f"/api/my/records/{track_id}", {"cover": cover}, fields)
        else:
            r = _post(conn, f"/api/my/records/{track_id}", fields)
        return _json_or_raise(r, "the record wasn't changed")


def delete_record(track_id):
    with closing(_db()) as conn:
        return _json_or_raise(_delete(conn, f"/api/my/records/{track_id}"), "couldn't remove that record")


def design_delete(design_id):
    with closing(_db()) as conn:
        url = _server_url(conn)
        if not url:
            raise GRError("no Green Room server set — join first")
        try:
            r = requests.delete(url + f"/api/my/room/designs/{design_id}",
                                headers=_headers(conn), timeout=_TIMEOUT)
        except requests.RequestException:
            raise GRError("the Green Room server can't be reached")
        return _json_or_raise(r, "couldn't delete that design")


def borrow_of_track(track_id):
    """The active borrow behind a record in the room, or None."""
    with closing(_db()) as conn:
        row = conn.execute(
            "SELECT * FROM gr_borrows WHERE track_id=? AND returned_at IS NULL",
            (track_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["on_disk"] = bool(d["file_path"] and os.path.exists(d["file_path"]))
        return d


def borrowed_list():
    """The local shelf: active borrows with on-disk state."""
    with closing(_db()) as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM gr_borrows WHERE returned_at IS NULL"
            " ORDER BY borrowed_at DESC")]
    for r in rows:
        r["on_disk"] = bool(r["file_path"] and os.path.exists(r["file_path"]))
        r.pop("key_hex", None)       # keys stay out of API payloads
        r.pop("nonce_hex", None)
        r.pop("file_path", None)
    return rows


def borrow_row(local_id):
    """One borrow row WITH its key material — for the player, never the UI."""
    with closing(_db()) as conn:
        row = conn.execute("SELECT * FROM gr_borrows WHERE id=? AND returned_at IS NULL",
                           (local_id,)).fetchone()
        return dict(row) if row else None


# ───────────────────────── record shopping ─────────────────────────
# Crates, the counter and blind listening live on the rooms server (gr_shop.py)
# and are only ever over records that can be bought there. The app passes the
# shopper's asks through and plays the shop's listening copies.

SHOP_OLD_SERVER = "The rooms server here doesn't have record shopping yet. It needs one restart."


def shop_call(method, path, payload=None, params=None):
    """Ask the rooms server's shop something. → (status, answer as a dict).
    The server's own refusals come back as they are (a plain "error", and a
    mark saying why: limit / empty / closed / taken) so the page can say the
    right thing; GRError only when the server can't be reached or is from
    before record shopping."""
    with closing(_db()) as conn:
        if method == "GET":
            r = _get(conn, path, params=params)
        elif method == "DELETE":
            r = _delete(conn, path)
        else:
            r = _post(conn, path, payload or {})
    if _grupa_server_too_old(r):
        raise GRError(SHOP_OLD_SERVER)
    try:
        data = r.json()
    except ValueError:
        raise GRError("the shop gave an answer that can't be read")
    return r.status_code, data if isinstance(data, dict) else {"data": data}


def master_file(track_id, what, range_header=None):
    """A record's sound ('audio') or cover ('art') for the master, streamed
    from the server as it comes. → the server's streaming response."""
    with closing(_db()) as conn:
        headers = {"Range": range_header} if range_header else {}
        url = _server_url(conn)
        if not url:
            raise GRError("no server set")
        try:
            return requests.get(f"{url}/api/master/records/{int(track_id)}/{what}",
                                headers=dict(_headers(conn), **headers), timeout=_DL_TIMEOUT, stream=True)
        except requests.RequestException:
            raise GRError("the server can't be reached")


def shop_listen(kind, ctx_id, server_track_id=None):
    """The shop's listening copy of a record → (bytes, mimetype). `kind` says
    from where it is being heard: "pull" (a crate handed over today) or "q" (an
    answer at the counter) with the record's number, or "blind" with the turn's
    number alone. The bytes are held in memory by the caller and never written
    down: outside the crate there is nothing to play."""
    if kind == "blind":
        path, params = f"/api/shop/blind/{int(ctx_id)}/listen", None
    elif kind in ("pull", "q"):
        path, params = f"/api/shop/listen/{int(server_track_id)}", {kind: int(ctx_id)}
    else:
        raise GRError("records in the shop play from inside a crate, the counter or blind")
    with closing(_db()) as conn:
        r = _get(conn, path, params=params, timeout=_DL_TIMEOUT)
    if _grupa_server_too_old(r):
        raise GRError(SHOP_OLD_SERVER)
    if r.status_code != 200:
        raise GRError(_err_of(r, "that record can't be played right now"))
    return r.content, (r.headers.get("Content-Type") or "audio/mpeg").split(";")[0].strip()


# ───────────────────────── covers ─────────────────────────
# Cached under GR_DIR/art as <server_track_id>_<art_v>.jpg: a borrowed
# record keeps its cover with the server out of reach, and a replaced cover
# (new art_v) is fetched fresh.

def _art_cache():
    return GR_DIR / "art"


def cover_path(server_track_id, art_v=None):
    """Local path to a pool record's cover, fetching it once if needed.
    None when the record has no cover (or the server can't be reached and
    nothing is cached)."""
    sid = int(server_track_id)
    cache = _art_cache()
    existing = sorted(cache.glob(f"{sid}_*.jpg"),
                      key=lambda p: p.stat().st_mtime, reverse=True) if cache.exists() else []
    if art_v is not None:
        want = cache / f"{sid}_{int(art_v)}.jpg"
        if want.exists():
            return str(want)
    elif existing:
        return str(existing[0])
    with closing(_db()) as conn:
        try:
            r = _get(conn, f"/api/art/{sid}")
        except GRError:
            return str(existing[0]) if existing else None
    if r.status_code != 200 or not r.content:
        return str(existing[0]) if existing else None
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{sid}_{int(art_v or 0)}.jpg"
    out.write_bytes(r.content)
    for old in existing:
        if old != out:
            old.unlink(missing_ok=True)
    return str(out)


# ───────────────────────── the lock ─────────────────────────

def decrypt_file(path, key_hex, nonce_hex):
    """Decrypt a borrowed file to bytes IN MEMORY (AES-256-CTR). The player
    feeds these straight to pygame; nothing plain is ever written out."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    dec = Cipher(algorithms.AES(bytes.fromhex(key_hex)),
                 modes.CTR(bytes.fromhex(nonce_hex))).decryptor()
    with open(path, "rb") as fh:
        return dec.update(fh.read()) + dec.finalize()
