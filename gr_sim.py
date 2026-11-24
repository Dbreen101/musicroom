"""
gr_sim.py — the Green Room's simulation of the Music Room's shop (2026-11-20).

David: "We are going to simulate the record borrowing … The only model is going
to be [bringing] a record [home] and you can only play the record on the app …
'Bring home to Music Room' (need to change this phrasing later) … Users can buy
the audio file outright … we create fake artist accounts that are selling
records and these records will be streamed from the individual users' Spotify …
The user will be given a number of credits … they can only have space for 200
brought home records (tracks) at a time. We will then track how much money
users spend and if they buy tracks once their [room] fills up … adjust other
variables." Then: "you should be able to buy a record outright without having
to bring it home first. Bring home has replaced borrow." And: "you can
undownload and then redownload any time … when you undownload a record you
can't redownload it for a week."

    the records    come from ONE public Spotify playlist David owns. His own app
                   (signed in to Spotify, and to this server as the master)
                   reads it and sends each record it finds — the WHOLE album or
                   single a playlist track is on — here (/api/master/sim/records).
                   Each record's first artist becomes a simulated ARTIST account
                   (is_sim) with a public room; a record already here is left as
                   it is, a new one by a known artist joins their room.
                   A record here is a gr_tracks row per track: path
                   "spotify:track:<id>", spotify_uri, record_key (the album's
                   id), record_kind (album | single | compilation),
                   record_tracks, track_no, disc_no. No audio is ever kept:
                   each listener's own Spotify plays it (or Spotify's own
                   player, for people without the Music Room's key).
    credits        everyone starts with `start_credits` (300). Bring home a
                   track = `home_cost` (1); buy a track = `buy_cost` (3); buy one
                   already brought home = the difference. A whole record (two
                   tracks or more) costs `record_share` % (80) of its tracks.
    the room       holds `room_space` (200) brought-home tracks at a time.
                   Bought tracks don't take room. A full room refuses another
                   bring-home (logged: what people do when their room is full).
    taking out     a brought-home track can be taken out at any time: no credit
                   back; it can come back FREE after `wait_days` (7) days.
                   Bought tracks are yours: they can't be taken out.
    the ledger     every credit that moves is a row in gr_ledger, with the room
                   count, the room's space and whether it was full at the time,
                   so "do people buy once their room is full?" can be answered.
    Spotify keys   one developer key lets five people play Spotify from inside
                   the Music Room (Spotify's own rule for apps in development).
                   The master enters keys and gives each to up to five people;
                   their app picks its key up by itself (/api/sim/me).
                   Everyone else's app plays Spotify's own embedded player.

All numbers are the master's to change (master page → Simulation); every change
is logged (event sim_rules) so a week's numbers can be read against the rules of
that week. gr_server hands this module itself at the bottom, like gr_shop.
"""

import csv
import sqlite3
import io
import json
import math
import re
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta

from flask import Response, jsonify, request

import gr_master

S = None          # the gr_server module, given in register()

DEFAULTS = {"on": False, "start_credits": 300, "home_cost": 1, "buy_cost": 3,
            "room_space": 200, "wait_days": 7, "record_share": 80}
LIMITS = {"start_credits": (0, 100000), "home_cost": (0, 1000), "buy_cost": (0, 1000),
          "room_space": (1, 100000), "wait_days": (0, 365), "record_share": (1, 100)}
PEOPLE_PER_KEY = 5          # Spotify: an app in development mode, five people
MAX_TARGETS = 500           # tracks in one action
SPOTIFY_ID = re.compile(r"^[0-9A-Za-z]{22}$")
CLIENT_ID = re.compile(r"^[0-9a-f]{32}$")
KINDS = ("album", "single", "compilation")
WORDS = {
    "full": "Your room is full: {count} of {space}. Take something out to make room, or buy it — "
            "bought records don't take room.",
    "short": "That needs {cost} credits. You have {credits}.",
    "locked": "You took {what} out. It can come back on {day}.",
    "nothing_out": "Only records you've brought home can be taken out. Bought records stay yours.",
    "off": "The shop isn't running the credits trial now.",
}


# ---------- tables ----------

def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure(conn):
    """Columns and tables this file needs. Asks the database itself every time
    (never 'is the first of my tables there?' — an older database must still
    get everything that is new)."""
    add = []
    t = _cols(conn, "gr_tracks")
    for col, decl in (("spotify_uri", "TEXT"), ("record_key", "TEXT"), ("record_kind", "TEXT"),
                      ("record_tracks", "INTEGER"), ("track_no", "INTEGER"), ("disc_no", "INTEGER"),
                      ("art_url", "TEXT")):
        if col not in t:
            add.append(f"ALTER TABLE gr_tracks ADD COLUMN {col} {decl}")
    a = _cols(conn, "gr_accounts")
    for col, decl in (("credits", "INTEGER"), ("is_sim", "INTEGER NOT NULL DEFAULT 0"),
                      ("spotify_artist_id", "TEXT"), ("spotify_key", "TEXT")):
        if col not in a:
            add.append(f"ALTER TABLE gr_accounts ADD COLUMN {col} {decl}")
    for sql in add:
        conn.execute(sql)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_gr_tracks_record ON gr_tracks(record_key);
        CREATE TABLE IF NOT EXISTS gr_home(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
            state TEXT NOT NULL,          -- home | out | bought
            paid INTEGER NOT NULL DEFAULT 0,   -- credits paid to bring it home (what buying later takes off)
            home_at TEXT,
            out_at TEXT,
            back_after TEXT,              -- taken out: may come back (free) from this moment
            bought_at TEXT,
            UNIQUE(account_id, track_id)
        );
        CREATE INDEX IF NOT EXISTS idx_gr_home_acct ON gr_home(account_id, state);
        CREATE TABLE IF NOT EXISTS gr_ledger(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
            what TEXT NOT NULL,           -- start | home | back | buy | out | grant
            credits INTEGER NOT NULL,     -- + given, − spent
            balance INTEGER NOT NULL,     -- after
            n_tracks INTEGER NOT NULL DEFAULT 0,
            track_ids TEXT,               -- JSON
            record_key TEXT,              -- the whole record, when it was the whole record
            room_count INTEGER,           -- brought-home tracks in the room BEFORE this
            room_space INTEGER,
            room_full INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gr_ledger_acct ON gr_ledger(account_id, at);
        """
    )
    conn.commit()


# ---------- the rules ----------

def rules(conn):
    r = dict(DEFAULTS)
    saved = gr_master.setting(conn, "sim", {}) or {}
    for k in DEFAULTS:
        if k in saved:
            r[k] = saved[k]
    return r


def is_on(conn):
    return bool(rules(conn)["on"])


def clean_rules(raw, now):
    """The master's numbers, kept inside sensible bounds. → (rules, error)"""
    out = dict(now)
    for k, (lo, hi) in LIMITS.items():
        if k in raw:
            try:
                v = int(raw[k])
            except (TypeError, ValueError):
                return None, f"{k} must be a whole number"
            if not lo <= v <= hi:
                return None, f"{k} must be between {lo} and {hi}"
            out[k] = v
    if "on" in raw:
        out["on"] = bool(raw["on"])
    return out, None


def _now():
    return S._now()


def _day(iso):
    try:
        d = datetime.fromisoformat(iso)
        return f"{d.day} {d.strftime('%b')}"
    except (TypeError, ValueError):
        return iso or ""


# ---------- credits and the room ----------

def credits(conn, aid):
    """This account's credits; the first time it is asked, it starts with the
    trial's start_credits (a 'start' line in the ledger)."""
    row = conn.execute("SELECT credits FROM gr_accounts WHERE id=?", (aid,)).fetchone()
    if row is None:
        return 0
    if row["credits"] is None:
        start = int(rules(conn)["start_credits"])
        # (only the request that turns "none yet" into a number writes the starting line: a new
        #  person's first page asks four things at once, and two of them used to add the 300 each)
        cur = conn.execute("UPDATE gr_accounts SET credits=0 WHERE id=? AND credits IS NULL", (aid,))
        if cur.rowcount:
            _ledger(conn, aid, "start", start, [], note="the trial's starting credits")
        conn.commit()
        return int(conn.execute("SELECT credits FROM gr_accounts WHERE id=?", (aid,)).fetchone()[0] or 0)
    return int(row["credits"])


def room_count(conn, aid):
    """Brought-home tracks in this person's room: from the playlist shop, and
    any record file brought home (a borrow) that hasn't gone back."""
    n = conn.execute("SELECT COUNT(*) FROM gr_home WHERE account_id=? AND state='home'", (aid,)).fetchone()[0]
    # (an exclusive record that was bought is held for good, kept_at, and takes no room — like any bought record)
    try:
        n += conn.execute("SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND returned_at IS NULL AND kept_at IS NULL",
                          (aid,)).fetchone()[0]
    except sqlite3.OperationalError:        # a database from before exclusive records
        n += conn.execute("SELECT COUNT(*) FROM gr_borrows WHERE account_id=? AND returned_at IS NULL",
                          (aid,)).fetchone()[0]
    return n


def _ledger(conn, aid, what, delta, track_ids, record_key=None, note="", room_before=None):
    space = int(rules(conn)["room_space"])
    count = room_count(conn, aid) if room_before is None else room_before
    if delta:
        conn.execute("UPDATE gr_accounts SET credits = COALESCE(credits,0) + ? WHERE id=?", (delta, aid))
    bal = conn.execute("SELECT COALESCE(credits,0) FROM gr_accounts WHERE id=?", (aid,)).fetchone()[0]
    conn.execute(
        "INSERT INTO gr_ledger(account_id, what, credits, balance, n_tracks, track_ids, record_key,"
        " room_count, room_space, room_full, note, at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, what, delta, bal, len(track_ids), json.dumps(list(track_ids)), record_key,
         count, space, 1 if count >= space else 0, note or "", _now()))
    return bal


def me_json(conn, acct):
    r = rules(conn)
    key = spotify_key_of(conn, acct)
    return {
        "on": bool(r["on"]),
        "credits": credits(conn, acct["id"]),
        "room": {"count": room_count(conn, acct["id"]), "space": int(r["room_space"])},
        "rules": {k: r[k] for k in ("home_cost", "buy_cost", "record_share", "wait_days", "room_space")},
        "spotify_client_id": key["client_id"] if key else "",
        "spotify_key": key["id"] if key else "",
    }


# ---------- what a record costs ----------

def _whole(cost, n, r):
    """A whole record of two tracks or more: record_share % of its tracks, rounded up."""
    return int(math.ceil(cost * int(r["record_share"]) / 100.0)) if n >= 2 else cost


def _states(conn, aid, ids):
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {h["track_id"]: h for h in conn.execute(
        f"SELECT * FROM gr_home WHERE account_id=? AND track_id IN ({q})", [aid] + ids)}


def plan_home(conn, aid, tracks, whole):
    """→ {cost, new, back, locked, already, need} for bringing these home."""
    r = rules(conn)
    st = _states(conn, aid, [t["id"] for t in tracks])
    now = _now()
    new, back, locked, already = [], [], [], []
    for t in tracks:
        h = st.get(t["id"])
        if h and h["state"] in ("home", "bought"):
            already.append(t["id"])
        elif h and h["state"] == "out":
            if (h["back_after"] or "") <= now:
                back.append(t["id"])
            else:
                locked.append({"id": t["id"], "back_after": h["back_after"]})
        else:
            new.append(t["id"])
    cost = len(new) * int(r["home_cost"])
    if whole:
        cost = _whole(cost, len(new), r)
    return {"cost": cost, "new": new, "back": back, "locked": locked, "already": already,
            "need": len(new) + len(back)}


def plan_buy(conn, aid, tracks, whole):
    """→ {cost, ids, already} for buying these outright (the difference for any brought home)."""
    r = rules(conn)
    st = _states(conn, aid, [t["id"] for t in tracks])
    ids, already, cost = [], [], 0
    for t in tracks:
        h = st.get(t["id"])
        if h and h["state"] == "bought":
            already.append(t["id"])
            continue
        paid = int(h["paid"] or 0) if h and h["state"] in ("home", "out") else 0
        cost += max(0, int(r["buy_cost"]) - paid)
        ids.append(t["id"])
    if whole:
        cost = _whole(cost, len(ids), r)
    return {"cost": cost, "ids": ids, "already": already}


def track_sim(conn, aid, rows):
    """The trial's facts for these records, for this person: {id: {...}}.
    Only records from the playlist shop (a spotify_uri) are in it."""
    sim_rows = [t for t in rows if _opt(t, "spotify_uri")]
    if not sim_rows:
        return {}
    r = rules(conn)
    st = _states(conn, aid, [t["id"] for t in sim_rows])
    out = {}
    for t in sim_rows:
        h = st.get(t["id"])
        state = h["state"] if h else ""
        paid = int(h["paid"] or 0) if h and state in ("home", "out") else 0
        held = state in ("home", "bought")
        out[t["id"]] = {
            "state": state,
            "back_after": h["back_after"] if h and state == "out" else None,
            "home_cost": None if state in ("home", "bought") else (
                0 if state == "out" else int(r["home_cost"])),
            "buy_cost": None if state == "bought" else max(0, int(r["buy_cost"]) - paid),
            "record": t["record_key"], "record_title": t["album"] or "",
            "record_kind": t["record_kind"] or "", "record_tracks": t["record_tracks"] or 1,
            "track_no": t["track_no"], "disc_no": t["disc_no"],
            # the stream itself only for what this person holds
            "spotify_uri": t["spotify_uri"] if held else None,
            "url": _open_url(t["spotify_uri"]) if held else None,
        }
    return out


def attach(conn, acct, rows_out, rows_db):
    """Add 'sim' to catalogue / room / crate rows (dicts with 'id') from the db rows."""
    facts = track_sim(conn, acct["id"], rows_db)
    for o in rows_out:
        f = facts.get(o["id"])
        if f:
            o["sim"] = f
    return rows_out


def owned_ids(conn, aid):
    return {r[0] for r in conn.execute("SELECT track_id FROM gr_home WHERE account_id=? AND state='bought'", (aid,))}


def _opt(row, key):
    try:
        return row[key] if key in row.keys() else None
    except Exception:
        return None


def _open_url(uri):
    m = re.match(r"^spotify:track:([0-9A-Za-z]{22})$", uri or "")
    return f"https://open.spotify.com/track/{m.group(1)}" if m else None


def listen_json(track):
    """What a one-play of a playlist-shop record hands over: where it streams.
    None for a record with a file (it has a listening copy instead)."""
    uri = _opt(track, "spotify_uri")
    if not uri:
        return None
    return {"spotify": uri, "url": _open_url(uri), "title": track["title"] or "",
            "artist": track["artist"] or "", "duration_s": track["duration_s"]}


# ---------- doing it ----------

TRACK_SQL = ("SELECT t.*, a.handle AS o_handle, a.name AS o_name FROM gr_tracks t"
             " LEFT JOIN gr_accounts a ON a.id = t.owner_account_id")
SHELF = "COALESCE(t.status,'live')='live' AND (a.id IS NULL OR a.hidden_at IS NULL)"


def targets(conn, body, any_state=False):
    """The tracks an action is about: a whole record (body.record) or some
    tracks (body.track_ids). Only playlist-shop records; only ones on the
    shelf unless any_state (taking out what you have, whatever became of it).
    → (rows, record_key or None)"""
    key = str(body.get("record") or "").strip()[:80]
    where = "t.spotify_uri IS NOT NULL" + ("" if any_state else f" AND {SHELF}")
    if key:
        rows = conn.execute(f"{TRACK_SQL} WHERE t.record_key=? AND {where}"
                            " ORDER BY COALESCE(t.disc_no,1), COALESCE(t.track_no,0), t.id", (key,)).fetchall()
        return rows, (key if rows else None)
    ids = body.get("track_ids")
    if not isinstance(ids, list):
        one = body.get("track_id")
        ids = [one] if one is not None else []
    try:
        ids = list(dict.fromkeys(int(i) for i in ids))[:MAX_TARGETS]
    except (TypeError, ValueError):
        ids = []
    if not ids:
        return [], None
    q = ",".join("?" * len(ids))
    rows = conn.execute(f"{TRACK_SQL} WHERE t.id IN ({q}) AND {where}", ids).fetchall()
    order = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda t: order.get(t["id"], 0)), None


def _what(rows, key):
    if key and rows:
        return f"“{rows[0]['album'] or rows[0]['title']}”"
    if len(rows) == 1:
        return f"“{rows[0]['title']}”"
    return f"{len(rows)} tracks"


def do_home(conn, acct, body):
    """→ (json, status)"""
    aid = acct["id"]
    rows, key = targets(conn, body)
    if not rows:
        return {"error": "that record isn't in the shop now"}, 404
    r = rules(conn)
    have = credits(conn, aid)
    p = plan_home(conn, aid, rows, bool(key))
    if not p["need"]:
        if p["locked"]:
            first = min(x["back_after"] for x in p["locked"])
            return {"error": WORDS["locked"].format(what=_what(rows, key), day=_day(first)),
                    "locked": True, "back_after": first}, 423
        return {"ok": True, "spent": 0, "credits": have, "already": True,
                "room": {"count": room_count(conn, aid), "space": int(r["room_space"])}}, 200
    count, space = room_count(conn, aid), int(r["room_space"])
    if count + p["need"] > space:
        S._event(conn, aid, "sim_full", {"tracks": p["need"], "room_count": count, "room_space": space,
                                         "record": key})
        return {"error": WORDS["full"].format(count=count, space=space), "full": True,
                "room": {"count": count, "space": space}, "need": p["need"]}, 409
    if p["cost"] > have:
        S._event(conn, aid, "sim_short", {"what": "home", "cost": p["cost"], "credits": have, "record": key})
        return {"error": WORDS["short"].format(cost=p["cost"], credits=have), "short": True,
                "cost": p["cost"], "credits": have}, 402
    now = _now()
    each = int(r["home_cost"])
    for tid in p["new"]:
        conn.execute("INSERT INTO gr_home(account_id, track_id, state, paid, home_at) VALUES(?,?,?,?,?)"
                     " ON CONFLICT(account_id, track_id) DO UPDATE SET state='home', paid=excluded.paid,"
                     " home_at=excluded.home_at, out_at=NULL, back_after=NULL",
                     (aid, tid, "home", each, now))
    for tid in p["back"]:
        conn.execute("UPDATE gr_home SET state='home', home_at=?, out_at=NULL, back_after=NULL"
                     " WHERE account_id=? AND track_id=?", (now, aid, tid))
    bal = have
    if p["new"]:
        bal = _ledger(conn, aid, "home", -p["cost"], p["new"], key, room_before=count)
    if p["back"]:
        bal = _ledger(conn, aid, "back", 0, p["back"], key, note="came back after the wait",
                      room_before=count + len(p["new"]))
    conn.commit()
    S._event(conn, aid, "sim_home", {"tracks": p["new"], "back": p["back"], "credits": p["cost"],
                                     "record": key, "room_count": count, "room_space": space})
    return {"ok": True, "spent": p["cost"], "credits": bal, "brought": len(p["new"]), "back": len(p["back"]),
            "locked": p["locked"], "room": {"count": room_count(conn, aid), "space": space},
            "tracks": _held_tracks(conn, aid, p["new"] + p["back"])}, 200


def do_buy(conn, acct, body):
    aid = acct["id"]
    rows, key = targets(conn, body)
    if not rows:
        return {"error": "that record isn't in the shop now"}, 404
    r = rules(conn)
    have = credits(conn, aid)
    p = plan_buy(conn, aid, rows, bool(key))
    if not p["ids"]:
        return {"ok": True, "spent": 0, "credits": have, "already": True}, 200
    if p["cost"] > have:
        S._event(conn, aid, "sim_short", {"what": "buy", "cost": p["cost"], "credits": have, "record": key})
        return {"error": WORDS["short"].format(cost=p["cost"], credits=have), "short": True,
                "cost": p["cost"], "credits": have}, 402
    count, space = room_count(conn, aid), int(r["room_space"])
    st = _states(conn, aid, p["ids"])
    was_home = [i for i in p["ids"] if st.get(i) is not None and st[i]["state"] in ("home", "out")]
    now = _now()
    for tid in p["ids"]:
        conn.execute("INSERT INTO gr_home(account_id, track_id, state, bought_at) VALUES(?,?,?,?)"
                     " ON CONFLICT(account_id, track_id) DO UPDATE SET state='bought',"
                     " bought_at=excluded.bought_at, out_at=NULL, back_after=NULL",
                     (aid, tid, "bought", now))
    bal = _ledger(conn, aid, "buy", -p["cost"], p["ids"], key, room_before=count,
                  note=f"{len(was_home)} had been brought home" if was_home else "")
    conn.commit()
    S._event(conn, aid, "sim_buy", {"tracks": p["ids"], "credits": p["cost"], "record": key,
                                    "were_home": len(was_home), "room_count": count, "room_space": space,
                                    "room_full": count >= space})
    return {"ok": True, "spent": p["cost"], "credits": bal, "bought": len(p["ids"]),
            "room": {"count": room_count(conn, aid), "space": space},
            "tracks": _held_tracks(conn, aid, p["ids"])}, 200


def do_out(conn, acct, body):
    aid = acct["id"]
    rows, key = targets(conn, body, any_state=True)
    st = _states(conn, aid, [t["id"] for t in rows])
    ids = [t["id"] for t in rows if st.get(t["id"]) is not None and st[t["id"]]["state"] == "home"]
    if not ids:
        return {"error": WORDS["nothing_out"]}, 409
    r = rules(conn)
    count = room_count(conn, aid)
    now = datetime.now()
    back = (now + timedelta(days=int(r["wait_days"]))).isoformat(timespec="seconds")
    q = ",".join("?" * len(ids))
    conn.execute(f"UPDATE gr_home SET state='out', out_at=?, back_after=? WHERE account_id=? AND track_id IN ({q})",
                 [now.isoformat(timespec="seconds"), back, aid] + ids)
    bal = _ledger(conn, aid, "out", 0, ids, key, room_before=count)
    conn.commit()
    S._event(conn, aid, "sim_out", {"tracks": ids, "record": key, "back_after": back, "room_count": count})
    return {"ok": True, "out": len(ids), "back_after": back, "credits": bal,
            "room": {"count": room_count(conn, aid), "space": int(r["room_space"])}}, 200


def _held_tracks(conn, aid, ids):
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT t.*, h.state FROM gr_tracks t JOIN gr_home h ON h.track_id=t.id AND h.account_id=?"
                        f" WHERE t.id IN ({q})", [aid] + list(ids)).fetchall()
    return [{"id": t["id"], "title": t["title"], "artist": t["artist"], "state": t["state"],
             "spotify_uri": t["spotify_uri"], "url": _open_url(t["spotify_uri"]),
             "duration_s": t["duration_s"]} for t in rows]


def _art_v(path):
    import os
    try:
        return int(os.path.getmtime(path)) if path and os.path.exists(path) else 0
    except OSError:
        return 0


def mine(conn, acct):
    """Everything this person has from the playlist shop, as records: what is
    home, what is bought, what is out (and when it can come back)."""
    aid = acct["id"]
    rows = conn.execute(
        "SELECT t.*, h.state, h.home_at, h.bought_at, h.out_at, h.back_after,"
        " a.handle AS o_handle, a.name AS o_name"
        " FROM gr_home h JOIN gr_tracks t ON t.id = h.track_id"
        " LEFT JOIN gr_accounts a ON a.id = t.owner_account_id"
        " WHERE h.account_id=? ORDER BY COALESCE(t.disc_no,1), COALESCE(t.track_no,0), t.id", (aid,)).fetchall()
    recs, order = {}, []
    for t in rows:
        key = t["record_key"] or f"t{t['id']}"
        if key not in recs:
            recs[key] = {"key": key, "title": t["album"] or t["title"] or "", "artist": t["artist"] or "",
                         "kind": t["record_kind"] or "", "tracks_total": t["record_tracks"] or 1,
                         "year": t["year"] if "year" in t.keys() else None,
                         "owner": {"handle": t["o_handle"], "name": t["o_name"]} if t["o_handle"] else None,
                         "cover_id": t["id"] if t["art_path"] else None, "art_v": _art_v(t["art_path"]),
                         "tracks": [], "latest": ""}
            order.append(key)
        rec = recs[key]
        if rec["cover_id"] is None and t["art_path"]:
            rec["cover_id"], rec["art_v"] = t["id"], _art_v(t["art_path"])
        held = t["state"] in ("home", "bought")
        rec["tracks"].append({
            "id": t["id"], "title": t["title"] or "", "artist": t["artist"] or "",
            "track_no": t["track_no"], "disc_no": t["disc_no"], "duration_s": t["duration_s"],
            "state": t["state"], "back_after": t["back_after"] if t["state"] == "out" else None,
            "spotify_uri": t["spotify_uri"] if held else None, "url": _open_url(t["spotify_uri"]) if held else None,
            "buy_cost": None,
        })
        rec["latest"] = max(rec["latest"], t["bought_at"] or "", t["home_at"] or "", t["out_at"] or "")
    r = rules(conn)
    out = sorted((recs[k] for k in order), key=lambda x: x["latest"], reverse=True)
    for rec in out:
        for tr in rec["tracks"]:
            if tr["state"] != "bought":
                h = conn.execute("SELECT paid FROM gr_home WHERE account_id=? AND track_id=?", (aid, tr["id"])).fetchone()
                tr["buy_cost"] = max(0, int(r["buy_cost"]) - int((h["paid"] if h else 0) or 0))
        rec["counts"] = {s: sum(1 for x in rec["tracks"] if x["state"] == s) for s in ("home", "bought", "out")}
    return out


def record_json(conn, acct, key):
    """One whole record: its tracks, what this person has of each, and what
    bringing all of it home / buying all of it would cost."""
    rows, k = targets(conn, {"record": key})
    if not rows:
        return None
    facts = track_sim(conn, acct["id"], rows)
    first = rows[0]
    home = plan_home(conn, acct["id"], rows, True)
    buy = plan_buy(conn, acct["id"], rows, True)
    return {
        "key": k, "title": first["album"] or first["title"] or "", "artist": first["artist"] or "",
        "kind": first["record_kind"] or "", "tracks_total": first["record_tracks"] or len(rows),
        "owner": {"handle": first["o_handle"], "name": first["o_name"]} if first["o_handle"] else None,
        "cover_id": next((t["id"] for t in rows if t["art_path"]), None),
        "art_v": next((_art_v(t["art_path"]) for t in rows if t["art_path"]), 0),
        "tracks": [dict({"id": t["id"], "title": t["title"] or "", "artist": t["artist"] or "",
                         "duration_s": t["duration_s"]}, **facts.get(t["id"], {})) for t in rows],
        "home": {"cost": home["cost"], "tracks": home["need"], "locked": len(home["locked"])},
        "buy": {"cost": buy["cost"], "tracks": len(buy["ids"])},
    }


# ---------- a record FILE (an artist's upload) in the trial ----------

def file_home(conn, acct, track):
    """In the trial a record file brought home (gr_server's borrow) costs
    credits and takes room like any other; one given back can come back free
    after the wait. → a refusal (json, code), or None once charged."""
    aid, r = acct["id"], rules(conn)
    count, space = room_count(conn, aid), int(r["room_space"])
    last = conn.execute("SELECT returned_at FROM gr_borrows WHERE account_id=? AND track_id=?"
                        " AND returned_at IS NOT NULL ORDER BY id DESC LIMIT 1", (aid, track["id"])).fetchone()
    cost = int(r["home_cost"])
    if last:
        back = (datetime.fromisoformat(last[0]) + timedelta(days=int(r["wait_days"]))).isoformat(timespec="seconds")
        if back > _now():
            return {"error": WORDS["locked"].format(what=f"“{track['title']}”", day=_day(back)),
                    "locked": True, "back_after": back}, 423
        cost = 0
    if count + 1 > space:
        S._event(conn, aid, "sim_full", {"tracks": 1, "room_count": count, "room_space": space})
        return {"error": WORDS["full"].format(count=count, space=space), "full": True,
                "room": {"count": count, "space": space}}, 409
    have = credits(conn, aid)
    if cost > have:
        S._event(conn, aid, "sim_short", {"what": "home", "cost": cost, "credits": have})
        return {"error": WORDS["short"].format(cost=cost, credits=have), "short": True, "cost": cost,
                "credits": have}, 402
    _ledger(conn, aid, "home" if cost else "back", -cost, [track["id"]], room_before=count, note="a record file")
    return None             # (not committed here: the charge and the borrow it pays for are written together)


def file_buy(conn, acct, track):
    """Buying a record file in the trial: credits, not the play-money wallet;
    the difference if it is brought home. → (refusal or None, credits spent)"""
    aid, r = acct["id"], rules(conn)
    held = conn.execute("SELECT 1 FROM gr_borrows WHERE account_id=? AND track_id=? AND returned_at IS NULL",
                        (aid, track["id"])).fetchone()
    cost = max(0, int(r["buy_cost"]) - (int(r["home_cost"]) if held else 0))
    have = credits(conn, aid)
    if cost > have:
        S._event(conn, aid, "sim_short", {"what": "buy", "cost": cost, "credits": have})
        return ({"error": WORDS["short"].format(cost=cost, credits=have), "short": True, "cost": cost,
                 "credits": have}, 402), 0
    _ledger(conn, aid, "buy", -cost, [track["id"]], note="a record file" + (", had been brought home" if held else ""))
    return None, cost


# ---------- Spotify keys ----------

def spotify_keys(conn):
    keys = gr_master.setting(conn, "spotify_keys", []) or []
    return [k for k in keys if isinstance(k, dict) and k.get("id") and CLIENT_ID.match(str(k.get("client_id") or ""))]


def spotify_key_of(conn, acct):
    kid = _opt(acct, "spotify_key")
    if not kid:
        return None
    return next((k for k in spotify_keys(conn) if k["id"] == kid), None)


# ---------- bringing records in from the playlist ----------

def playlist_id(raw):
    """A playlist's id from its link, its spotify: name, or the id itself."""
    raw = str(raw or "").strip()
    m = re.search(r"playlist[/:]([0-9A-Za-z]{22})", raw) or re.match(r"^([0-9A-Za-z]{22})$", raw)
    return m.group(1) if m else None


def _unique_handle(conn, name):
    base = S._slug(name)[:40] or "artist"
    h, n = base, 2
    while conn.execute("SELECT 1 FROM gr_accounts WHERE handle=?", (h,)).fetchone():
        h, n = f"{base}-{n}", n + 1
    return h


def artist_account(conn, sp_id, name):
    """The simulated artist account for this Spotify artist: found, or made."""
    row = conn.execute("SELECT * FROM gr_accounts WHERE spotify_artist_id=?", (sp_id,)).fetchone()
    if row:
        return row, False
    cur = conn.execute(
        "INSERT INTO gr_accounts(name, invite_code, wallet_cents, created_at, kind, handle, is_public,"
        " is_sim, spotify_artist_id, bio) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (name[:120], S.new_code(), 0, _now(), "artist", _unique_handle(conn, name), 1, 1, sp_id, ""))
    return conn.execute("SELECT * FROM gr_accounts WHERE id=?", (cur.lastrowid,)).fetchone(), True


def _fetch_cover(url):
    """A record's cover from Spotify's own picture server (and nowhere else)."""
    if not re.match(r"^https://i\.scdn\.co/image/[0-9a-zA-Z]+$", url or ""):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MusicRoom/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read(6 * 1024 * 1024 + 1)
        return data if len(data) <= 6 * 1024 * 1024 else None
    except Exception:
        return None


def _save_record_cover(key, data):
    try:
        img = S._open_picture(data).convert("RGB")
        img.thumbnail((800, 800))
        S.art_dir().mkdir(parents=True, exist_ok=True)
        out = S.art_dir() / f"sim_{key}.jpg"
        img.save(out, "JPEG", quality=88)
        return str(out)
    except Exception:
        return None


def _txt(v, n):
    return str(v or "").strip()[:n]


def bring_in(conn, records, fetch_covers=True):
    """Records read from the playlist (by the master's app) → artist accounts
    and records here. A track already here is left as it is (the master may
    have hidden it). → counts"""
    made = {"artists": 0, "records": 0, "tracks": 0, "seen": 0, "covers": 0, "skipped": 0}
    for rec in records[:200]:
        if not isinstance(rec, dict):
            made["skipped"] += 1
            continue
        key = _txt(rec.get("key") or rec.get("id"), 80)
        tracks = [t for t in (rec.get("tracks") or []) if isinstance(t, dict) and SPOTIFY_ID.match(str(t.get("id") or ""))]
        artists = [a for a in (rec.get("artists") or []) if isinstance(a, dict) and SPOTIFY_ID.match(str(a.get("id") or ""))]
        if not re.match(r"^[0-9A-Za-z:]{22,45}$", key) or not tracks or not artists:
            made["skipped"] += 1
            continue
        kind = rec.get("kind") if rec.get("kind") in KINDS else "album"
        owner, new_owner = artist_account(conn, artists[0]["id"], _txt(artists[0].get("name"), 120) or "Unknown artist")
        made["artists"] += 1 if new_owner else 0
        title = _txt(rec.get("name"), 300)
        year = None
        m = re.match(r"^(\d{4})", str(rec.get("release_date") or ""))
        if m:
            year = int(m.group(1))
        art_url = _txt(rec.get("image"), 300)
        new_here = False
        for t in tracks[:MAX_TARGETS]:
            uri = f"spotify:track:{t['id']}"
            if conn.execute("SELECT 1 FROM gr_tracks WHERE path=?", (uri,)).fetchone():
                made["seen"] += 1
                continue
            by = ", ".join(_txt(a.get("name"), 120) for a in (t.get("artists") or []) if isinstance(a, dict)) \
                or _txt(artists[0].get("name"), 120)
            try:
                dur = round(float(t.get("duration_ms") or 0) / 1000.0, 1) or None
                tno, dno = int(t.get("track_number") or 0) or None, int(t.get("disc_number") or 1)
            except (TypeError, ValueError):
                dur, tno, dno = None, None, 1
            conn.execute(
                "INSERT INTO gr_tracks(path, filename, title, artist, album, duration_s, format, size_bytes,"
                " price_cents, added_at, owner_account_id, status, year, spotify_uri, record_key, record_kind,"
                " record_tracks, track_no, disc_no, art_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uri, _txt(t.get("name"), 300) or uri, _txt(t.get("name"), 300), by, title, dur, "spotify", 0,
                 0, _now(), owner["id"], "live", year, uri, key, kind,
                 int(rec.get("total_tracks") or len(tracks)), tno, dno, art_url))
            made["tracks"] += 1
            new_here = True
        made["records"] += 1 if new_here else 0
        conn.commit()            # (before any cover is fetched: a slow one must not hold everyone else's writes)
        has = conn.execute("SELECT art_path FROM gr_tracks WHERE record_key=? AND art_path IS NOT NULL LIMIT 1",
                           (key,)).fetchone()
        if has:
            conn.execute("UPDATE gr_tracks SET art_path=? WHERE record_key=? AND art_path IS NULL", (has[0], key))
        elif fetch_covers and art_url:
            data = _fetch_cover(art_url)
            path = _save_record_cover(re.sub(r"[^0-9A-Za-z]", "_", key), data) if data else None
            if path:
                conn.execute("UPDATE gr_tracks SET art_path=?, art_source='spotify' WHERE record_key=?", (path, key))
                made["covers"] += 1
        conn.commit()
    return made


# ---------- what the master reads ----------

def activity(conn):
    """One line per person: credits, what they spent it on, their room."""
    r = rules(conn)
    people = conn.execute("SELECT * FROM gr_accounts WHERE COALESCE(is_sim,0)=0 ORDER BY created_at").fetchall()
    out = []
    for a in people:
        aid = a["id"]
        one = lambda sql, *p: conn.execute(sql, (aid,) + p).fetchone()[0]
        spent = -one("SELECT COALESCE(SUM(credits),0) FROM gr_ledger WHERE account_id=? AND credits<0")
        out.append({
            "id": aid, "name": a["name"], "handle": a["handle"], "kind": a["kind"],
            "credits": a["credits"], "spent": spent,
            "spent_home": -one("SELECT COALESCE(SUM(credits),0) FROM gr_ledger WHERE account_id=? AND what='home'"),
            "spent_buy": -one("SELECT COALESCE(SUM(credits),0) FROM gr_ledger WHERE account_id=? AND what='buy'"),
            "given": one("SELECT COALESCE(SUM(credits),0) FROM gr_ledger WHERE account_id=? AND what='grant'"),
            "home_now": one("SELECT COUNT(*) FROM gr_home WHERE account_id=? AND state='home'"),
            "bought": one("SELECT COUNT(*) FROM gr_home WHERE account_id=? AND state='bought'"),
            "out_now": one("SELECT COUNT(*) FROM gr_home WHERE account_id=? AND state='out'"),
            "brought_ever": one("SELECT COALESCE(SUM(n_tracks),0) FROM gr_ledger WHERE account_id=? AND what='home'"),
            "taken_out": one("SELECT COALESCE(SUM(n_tracks),0) FROM gr_ledger WHERE account_id=? AND what='out'"),
            "room_count": room_count(conn, aid), "room_space": int(r["room_space"]),
            "full_refused": one("SELECT COUNT(*) FROM gr_events WHERE account_id=? AND kind='sim_full'"),
            "short_refused": one("SELECT COUNT(*) FROM gr_events WHERE account_id=? AND kind='sim_short'"),
            "buys_when_full": one("SELECT COUNT(*) FROM gr_ledger WHERE account_id=? AND what='buy' AND room_full=1"),
            "plays": one("SELECT COUNT(*) FROM gr_events WHERE account_id=? AND kind='sim_play'"),
            "one_plays": one("SELECT COUNT(*) FROM gr_events WHERE account_id=? AND kind='shop_listen'"),
            "last": one("SELECT MAX(at) FROM gr_ledger WHERE account_id=? AND what!='start'"),
            "spotify_key": a["spotify_key"] or "",
        })
    return out


def ledger_csv(conn):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["when", "person", "handle", "what", "credits", "balance after", "tracks", "whole record",
                "room before", "room space", "room was full", "note", "track ids"])
    for row in conn.execute(
            "SELECT l.*, a.name, a.handle FROM gr_ledger l JOIN gr_accounts a ON a.id = l.account_id ORDER BY l.id"):
        w.writerow([row["at"], row["name"], row["handle"] or "", row["what"], row["credits"], row["balance"],
                    row["n_tracks"], row["record_key"] or "", row["room_count"], row["room_space"],
                    "yes" if row["room_full"] else "", row["note"] or "", row["track_ids"] or ""])
    return buf.getvalue()


def activity_csv(conn):
    rows = activity(conn)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["name", "handle", "credits", "spent", "spent_home", "spent_buy", "given", "home_now", "bought",
            "out_now", "brought_ever", "taken_out", "room_count", "room_space", "full_refused", "short_refused",
            "buys_when_full", "plays", "one_plays", "last"]
    w.writerow(head)
    for r in rows:
        w.writerow([r[k] if r[k] is not None else "" for k in head])
    return buf.getvalue()


# ---------- routes ----------

def register(app, server):
    global S
    S = server

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    def signed_in(fn, master=False):
        with closing(S.db()) as conn:
            gr_master.ensure(conn)
            ensure(conn)
            acct, _dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            if master and not gr_master.is_master(acct):
                return no("only the master account can do that", 403, master=False)
            if master and not gr_master.master_here():
                return no("the master's page works only on the Mac the server runs on", 403, master=False)
            return fn(conn, acct)

    def acting(fn):
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            if not is_on(conn):
                return no(WORDS["off"], 409, off=True)
            credits(conn, acct["id"])           # (the starting credits first: that commits)
            conn.execute("BEGIN IMMEDIATE")     # one at a time: the balance is read and spent with nothing in between
            try:
                out, code = fn(conn, acct, body)
            finally:
                if conn.in_transaction:         # (a refusal part-way leaves nothing half-written)
                    conn.rollback()
            return jsonify(out), code
        return signed_in(go)

    # ── a listener's own ──
    @app.get("/api/sim/me")
    def sim_me():
        return signed_in(lambda conn, acct: jsonify(me_json(conn, acct)))

    @app.post("/api/sim/home")
    def sim_home():
        return acting(do_home)

    @app.post("/api/sim/buy")
    def sim_buy():
        return acting(do_buy)

    @app.post("/api/sim/out")
    def sim_out():
        return acting(do_out)

    @app.get("/api/sim/mine")
    def sim_mine():
        def go(conn, acct):
            return jsonify({"records": mine(conn, acct), "me": me_json(conn, acct)})
        return signed_in(go)

    @app.get("/api/sim/record/<key>")
    def sim_record(key):
        def go(conn, acct):
            rec = record_json(conn, acct, key[:80])
            return jsonify({"record": rec}) if rec else no("that record isn't in the shop now", 404)
        return signed_in(go)

    # ── the master's ──
    @app.get("/api/master/sim")
    def m_sim():
        def go(conn, acct):
            keys = spotify_keys(conn)
            people = conn.execute("SELECT id, name, handle, kind, spotify_key FROM gr_accounts"
                                  " WHERE COALESCE(is_sim,0)=0 ORDER BY name COLLATE NOCASE").fetchall()
            people.sort(key=lambda p: S.mr_text.fold(p["name"]))      # Áine with the As
            one = lambda sql: conn.execute(sql).fetchone()[0]
            return jsonify({
                "rules": rules(conn), "defaults": DEFAULTS, "limits": LIMITS,
                "playlist": gr_master.setting(conn, "sim_playlist", {}) or {},
                "keys": [dict(k, people=[{"id": p["id"], "name": p["name"], "handle": p["handle"]}
                                         for p in people if p["spotify_key"] == k["id"]]) for k in keys],
                "people": [{"id": p["id"], "name": p["name"], "handle": p["handle"], "kind": p["kind"],
                            "spotify_key": p["spotify_key"] or ""} for p in people],
                "per_key": PEOPLE_PER_KEY,
                "counts": {"artists": one("SELECT COUNT(*) FROM gr_accounts WHERE is_sim=1"),
                           "records": one("SELECT COUNT(DISTINCT record_key) FROM gr_tracks WHERE spotify_uri IS NOT NULL"),
                           "tracks": one("SELECT COUNT(*) FROM gr_tracks WHERE spotify_uri IS NOT NULL")},
                "record_keys": [r[0] for r in conn.execute(
                    "SELECT DISTINCT record_key FROM gr_tracks WHERE spotify_uri IS NOT NULL AND record_key IS NOT NULL")],
            })
        return signed_in(go, master=True)

    @app.post("/api/master/sim/rules")
    def m_sim_rules():
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            new, err = clean_rules(body, rules(conn))
            if err:
                return no(err)
            gr_master.set_setting(conn, "sim", new)
            S._event(conn, acct["id"], "sim_rules", new)
            return jsonify({"rules": new})
        return signed_in(go, master=True)

    @app.post("/api/master/sim/credits")
    def m_sim_credits():
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            try:
                delta = int(body.get("credits"))
            except (TypeError, ValueError):
                return no("credits must be a whole number")
            if not -100000 <= delta <= 100000 or not delta:
                return no("credits must be between −100000 and 100000, and not 0")
            note = _txt(body.get("note"), 200)
            if body.get("everyone"):
                ids = [r[0] for r in conn.execute("SELECT id FROM gr_accounts WHERE COALESCE(is_sim,0)=0")]
            else:
                row = conn.execute("SELECT id FROM gr_accounts WHERE id=? AND COALESCE(is_sim,0)=0",
                                   (body.get("account_id"),)).fetchone()
                if not row:
                    return no("no such person", 404)
                ids = [row[0]]
            for aid in ids:
                credits(conn, aid)                       # (the starting credits first, if never given)
                _ledger(conn, aid, "grant", delta, [], note=note or "from the master")
            conn.commit()
            S._event(conn, acct["id"], "sim_grant", {"to": ids, "credits": delta, "note": note})
            return jsonify({"ok": True, "people": len(ids)})
        return signed_in(go, master=True)

    @app.post("/api/master/sim/playlist")
    def m_sim_playlist():
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            raw = _txt(body.get("url"), 300)
            if not raw:
                gr_master.set_setting(conn, "sim_playlist", {})
                return jsonify({"playlist": {}})
            pid = playlist_id(raw)
            if not pid:
                return no("That isn't a Spotify playlist's link.")
            now = gr_master.setting(conn, "sim_playlist", {}) or {}
            pl = {"url": raw, "id": pid}
            if now.get("id") == pid:
                pl.update({k: now[k] for k in ("synced_at", "note", "name") if k in now})
            gr_master.set_setting(conn, "sim_playlist", pl)
            return jsonify({"playlist": pl})
        return signed_in(go, master=True)

    @app.post("/api/master/sim/records")
    def m_sim_records():
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            recs = body.get("records") if isinstance(body.get("records"), list) else []
            made = bring_in(conn, recs)
            pl = gr_master.setting(conn, "sim_playlist", {}) or {}
            if body.get("done"):
                pl.update({"synced_at": _now(), "note": _txt(body.get("note"), 300), "name": _txt(body.get("name"), 200)})
                gr_master.set_setting(conn, "sim_playlist", pl)
            if made["tracks"]:
                S._event(conn, acct["id"], "sim_records", made)
            return jsonify(made)
        return signed_in(go, master=True)

    @app.post("/api/master/sim/sync-note")
    def m_sim_sync_note():
        """The app's playlist reading couldn't finish: say so on the master page."""
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            pl = gr_master.setting(conn, "sim_playlist", {}) or {}
            pl["note"] = _txt(body.get("note"), 300)
            pl["tried_at"] = _now()
            gr_master.set_setting(conn, "sim_playlist", pl)
            return jsonify({"playlist": pl})
        return signed_in(go, master=True)

    @app.get("/api/master/sim/activity")
    def m_sim_activity():
        return signed_in(lambda conn, acct: jsonify({"people": activity(conn), "rules": rules(conn)}), master=True)

    @app.get("/api/master/sim/<what>.csv")
    def m_sim_csv(what):
        def go(conn, acct):
            if what == "ledger":
                text = ledger_csv(conn)
            elif what == "activity":
                text = activity_csv(conn)
            else:
                return no("no such table", 404)
            return Response(text, mimetype="text/csv",
                            headers={"Content-Disposition": f"attachment; filename=music-room-{what}.csv"})
        return signed_in(go, master=True)

    @app.post("/api/master/spotify-keys")
    def m_spotify_keys():
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            raw = body.get("keys") if isinstance(body.get("keys"), list) else []
            keys, seen = [], set()
            for n, k in enumerate(raw[:25]):
                if not isinstance(k, dict):
                    continue
                cid = _txt(k.get("client_id"), 64).lower()
                if not CLIENT_ID.match(cid):
                    return no(f"“{_txt(k.get('label'), 40) or cid}”: a Client ID is 32 letters and numbers "
                              "(from the app's page on developer.spotify.com).")
                if cid in seen:
                    continue
                seen.add(cid)
                kid = _txt(k.get("id"), 20) or f"k{n + 1}"
                if not re.match(r"^[a-z0-9-]{1,20}$", kid):
                    kid = f"k{n + 1}"
                while kid in {x["id"] for x in keys}:
                    kid += "x"
                keys.append({"id": kid, "label": _txt(k.get("label"), 60) or f"Key {n + 1}", "client_id": cid})
            gr_master.set_setting(conn, "spotify_keys", keys)
            known = {k["id"] for k in keys}
            # anyone given a key that has gone keeps none
            for p in conn.execute("SELECT id, spotify_key FROM gr_accounts WHERE spotify_key IS NOT NULL"):
                if p["spotify_key"] not in known:
                    conn.execute("UPDATE gr_accounts SET spotify_key=NULL WHERE id=?", (p["id"],))
            conn.commit()
            return jsonify({"keys": keys})
        return signed_in(go, master=True)

    @app.post("/api/master/spotify-keys/assign")
    def m_spotify_assign():
        body = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            person = conn.execute("SELECT * FROM gr_accounts WHERE id=? AND COALESCE(is_sim,0)=0",
                                  (body.get("account_id"),)).fetchone()
            if not person:
                return no("no such person", 404)
            kid = _txt(body.get("key"), 20)
            if kid:
                if kid not in {k["id"] for k in spotify_keys(conn)}:
                    return no("no such key", 404)
                n = conn.execute("SELECT COUNT(*) FROM gr_accounts WHERE spotify_key=? AND id!=?",
                                 (kid, person["id"])).fetchone()[0]
                if n >= PEOPLE_PER_KEY:
                    return no(f"That key already has {PEOPLE_PER_KEY} people — Spotify's limit for an app "
                              "in development. Add another key, or take someone off this one.", 409, full=True)
            conn.execute("UPDATE gr_accounts SET spotify_key=? WHERE id=?", (kid or None, person["id"]))
            conn.commit()
            S._event(conn, acct["id"], "spotify_key", {"to": person["id"], "key": kid or None})
            return jsonify({"ok": True})
        return signed_in(go, master=True)
