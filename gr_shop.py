"""Record shopping on the rooms server — crates, the counter, blind listening.

Three ways to come across a record, all of them only ever over records that
can be BOUGHT here (gr_tracks), Daithí 2026-11-16:

  CRATES   a small, finite set of records (25 at most). A crate is either made
           by someone who sells here (a label, an artist, a shop, the Music
           Room itself) or put together by the server from the shelves by a
           plain rule the shopper can read: anywhere, or a genre, a place, a
           span of years. No rule here ever says two records sound alike.
           A shopper is handed 3 a day. A crate stays open until the day ends.
  COUNTER  a shopper asks a question in words (3 a day). Someone else is handed
           the oldest open question (never one they skipped), and answers it
           with ONE record from the shop and a line of why (3 a day). A
           question only ever gets one answer.
  BLIND    a record plays with no name and no cover. The listener decides
           first; only then is it turned over.

LISTENING. A record that isn't yours can be heard only from inside one of
those three: a crate you were handed today, an answer waiting for you at the
counter, the blind record in front of you. What plays is the shop's LISTENING
COPY — a 128k MP3 made once from the real file, with every tag taken off — not
the file itself; that only ever leaves as a borrow (locked) or a purchase.

gr_server.py calls register(app, <itself>) at the bottom; everything it needs
from the server (db, auth, the clock) comes through that one handle, so this
works the same whether the server is imported or run as a script.
"""

import json
import os
import random
import re
import subprocess
import threading
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from flask import jsonify, request, send_file

# ---------- the numbers (Daithí's, 2026-11-16; blind's is a first guess) ----------
CRATE_MAX = 25            # records in one crate
CRATES_PER_DAY = 3        # crates one shopper is handed in a day
ASKS_PER_DAY = 3          # questions one person may put to the counter in a day
ANSWERS_PER_DAY = 3       # questions one person may answer in a day
BLIND_PER_DAY = 10        # records one person may hear blind in a day
HOLD_MINUTES = 10         # a question handed to someone is theirs alone this long
ANSWER_OPEN_DAYS = 14     # an answer can be listened to until it is settled, or this long
MADE_AGAIN_DAYS = 30      # the same made crate isn't handed to the same person again sooner
MADE_CHANCE = 0.6         # with a made crate that fits: how often it is handed over whole
MAKER_CRATES_MAX = 40     # crates one seller may keep
HOUSE_NAME = "The Music Room"
ASK_MAX, WHY_MAX, NAME_MAX, NOTE_MAX = 280, 280, 80, 400

S = None                  # the gr_server module — set by register()
_rng = random.Random()

_MIMES = {".mp3": "audio/mpeg", ".flac": "audio/flac", ".wav": "audio/wav", ".ogg": "audio/ogg",
          ".m4a": "audio/mp4", ".aiff": "audio/aiff", ".aif": "audio/aiff"}


# a record that is out on the shelves: approved by the master (gr_master.py), and its
# seller's room not taken down. Every query that hands records to shoppers asks this.
ON_SHELF = "COALESCE(t.status,'live')='live' AND (a.id IS NULL OR a.hidden_at IS NULL)"
PICK_BY_MAX = 60          # how long a plug-in's name may be on the crate it picked


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _txt(v, n):
    return " ".join(str(v if v is not None else "").split())[:n]


# ---------- tables ----------

def ensure(conn):
    """The shop's tables and columns, made once; then any record whose file
    hasn't been read for its year / genre / label is read."""
    tcols = {r[1] for r in conn.execute("PRAGMA table_info(gr_tracks)")}
    acols = {r[1] for r in conn.execute("PRAGMA table_info(gr_accounts)")}
    # (asked by the NEWEST table: a server from before it gets the tables it lacks — 2026-11-20, gr_heard was
    #  skipped on a server that already had the shop, because this asked only for gr_blind)
    made = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gr_heard'").fetchone()
    if not (made and "meta_read_at" in tcols and "is_house" in acols):     # asked of the database itself: a server may be pointed at another one
        conn.executescript(
            """
            -- a crate somebody who sells here has made
            CREATE TABLE IF NOT EXISTS gr_crates(
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
                name TEXT NOT NULL,
                note TEXT,
                is_out INTEGER NOT NULL DEFAULT 0,      -- out on the shop floor: shoppers can be handed it
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gr_crate_items(
                id INTEGER PRIMARY KEY,
                crate_id INTEGER NOT NULL REFERENCES gr_crates(id),
                track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
                pos INTEGER NOT NULL,
                note TEXT,                              -- the maker's line on this record
                from_crate_id INTEGER,                  -- pulled in from another crate
                UNIQUE(crate_id, track_id)
            );
            -- a crate handed to a shopper: fixed the moment it is handed over
            CREATE TABLE IF NOT EXISTS gr_crate_pulls(
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
                day TEXT NOT NULL,
                kind TEXT NOT NULL,                     -- 'made' (someone's crate, whole) | 'mixed' (put together for this ask)
                crate_id INTEGER,
                title TEXT, by_name TEXT, by_handle TEXT, note TEXT,
                ask TEXT NOT NULL DEFAULT '{}',         -- JSON: what was asked for
                items TEXT NOT NULL DEFAULT '[]',       -- JSON: [{id, note, from}] in order
                sources TEXT NOT NULL DEFAULT '[]',     -- JSON: the crates a mixed one drew on
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gr_pulls_who ON gr_crate_pulls(account_id, day);
            -- the counter: one question, one answer
            CREATE TABLE IF NOT EXISTS gr_counter(
                id INTEGER PRIMARY KEY,
                asker_id INTEGER NOT NULL REFERENCES gr_accounts(id),
                text TEXT NOT NULL,
                day TEXT NOT NULL,
                created_at TEXT NOT NULL,
                held_by INTEGER, held_until TEXT,
                answered_at TEXT, answer_by INTEGER, answer_day TEXT,
                answer_track_id INTEGER, answer_text TEXT,
                seen_at TEXT,                           -- the asker has looked at the answer
                settled TEXT, settled_at TEXT           -- what the asker did with it: basket | note | pass
            );
            CREATE INDEX IF NOT EXISTS idx_gr_counter_open ON gr_counter(answered_at, created_at);
            CREATE TABLE IF NOT EXISTS gr_counter_skips(
                q_id INTEGER NOT NULL, account_id INTEGER NOT NULL, at TEXT NOT NULL,
                PRIMARY KEY(q_id, account_id)
            );
            -- blind: a record played with no name; what the listener decided
            CREATE TABLE IF NOT EXISTS gr_blind(
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
                day TEXT NOT NULL,
                track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
                choice TEXT,                            -- basket | note | pass
                created_at TEXT NOT NULL, decided_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_gr_blind_who ON gr_blind(account_id, day);
            -- one play (Daithí, 2026-11-20: "whole records but only one play. If they want to hear
            -- it again they have to buy or borrow it"): who has heard which record in the shop
            CREATE TABLE IF NOT EXISTS gr_heard(
                account_id INTEGER NOT NULL REFERENCES gr_accounts(id),
                track_id INTEGER NOT NULL REFERENCES gr_tracks(id),
                via TEXT,                               -- pull | q | blind
                at TEXT NOT NULL,
                PRIMARY KEY (account_id, track_id)
            );
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(gr_tracks)")}
        for col, typ in (("year", "INTEGER"), ("genre", "TEXT"), ("label", "TEXT"), ("meta_read_at", "TEXT")):
            if col not in cols:
                conn.execute(f"ALTER TABLE gr_tracks ADD COLUMN {col} {typ}")
        acols = {r[1] for r in conn.execute("PRAGMA table_info(gr_accounts)")}
        if "is_house" not in acols:
            # the Music Room's own account(s): their crates are signed "The Music Room"
            conn.execute("ALTER TABLE gr_accounts ADD COLUMN is_house INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    for row in conn.execute("SELECT id, path, year, genre, label FROM gr_tracks"
                            " WHERE meta_read_at IS NULL LIMIT 400").fetchall():
        read_tags(conn, row)
    conn.commit()


# ---------- what is printed on a record ----------

def _tags_of(path):
    """(year, genre, label) as the file's own tags give them; None where they say nothing."""
    try:
        import mutagen
        audio = mutagen.File(path, easy=True)
    except Exception:
        return None, None, None
    tags = getattr(audio, "tags", None) or {}

    def first(*keys):
        for k in keys:
            try:
                v = tags.get(k)
            except Exception:
                v = None
            if v:
                v = v[0] if isinstance(v, (list, tuple)) else v
                v = str(v).strip()
                if v:
                    return v
        return None

    return clean_year(first("originaldate", "date", "year")), first("genre"), \
        first("label", "organization", "publisher")


def clean_year(v):
    m = re.search(r"(1[5-9]\d\d|20\d\d)", str(v or ""))
    if not m:
        return None
    y = int(m.group(1))
    return y if 1500 <= y <= datetime.now().year + 1 else None


def read_tags(conn, track_row):
    """Fill a record's year / genre / label from its file, where the owner
    hasn't given one. Done once per record."""
    year = genre = label = None
    try:
        if track_row["path"] and os.path.exists(track_row["path"]):
            year, genre, label = _tags_of(track_row["path"])
    except Exception:
        pass
    conn.execute(
        "UPDATE gr_tracks SET year=COALESCE(year, ?), genre=COALESCE(NULLIF(genre,''), ?),"
        " label=COALESCE(NULLIF(label,''), ?), meta_read_at=? WHERE id=?",
        (year, _txt(genre, 120) or None, _txt(label, 120) or None, S._now(), track_row["id"]))


def genres_of(text):
    """A record's genre line as separate genres ("House; Techno" → two)."""
    out = []
    for g in re.split(r"[;,/|]", str(text or "")):
        g = _txt(g, 40)
        if g and g.casefold() not in [x.casefold() for x in out]:
            out.append(g)
    return out[:6]


def _display(row, prefix=""):
    """The name a seller is shown under."""
    try:
        if row[prefix + "is_house"]:
            return HOUSE_NAME
    except (IndexError, KeyError):
        pass
    return row[prefix + "name"] or ""


def _cards(conn, acct, ids):
    """What is printed on each of these records, and what this person already
    has of it. In the order asked; a record that has since gone is left out."""
    ids = [int(i) for i in ids]
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT t.*, a.handle AS o_handle, a.name AS o_name, a.kind AS o_kind, a.is_house AS o_is_house,"
        f" a.place_name AS o_place FROM gr_tracks t LEFT JOIN gr_accounts a ON a.id = t.owner_account_id"
        f" WHERE t.id IN ({q}) AND {ON_SHELF}", ids)}
    aid = acct["id"]
    held = {r["track_id"]: r["id"] for r in conn.execute(
        "SELECT id, track_id FROM gr_borrows WHERE account_id=? AND returned_at IS NULL", (aid,))}
    bought = {r["track_id"] for r in conn.execute(
        "SELECT track_id FROM gr_purchases WHERE account_id=?", (aid,))}
    this_month = {r["track_id"] for r in conn.execute(
        "SELECT track_id FROM gr_borrows WHERE account_id=? AND month=?", (aid, S._month()))}
    credit = S._credit_cents(conn, acct)
    heard = heard_ids(conn, aid, list(rows))
    import gr_sim
    sim = gr_sim.track_sim(conn, aid, list(rows.values()))
    bought |= gr_sim.owned_ids(conn, aid)
    out = []
    for i in ids:
        t = rows.get(i)
        if not t:
            continue
        art_ok = bool(t["art_path"]) and os.path.exists(t["art_path"])
        out.append({
            "id": t["id"], "title": t["title"], "artist": t["artist"], "album": t["album"],
            "year": t["year"], "genre": t["genre"] or "", "genres": genres_of(t["genre"]),
            "label": t["label"] or "", "duration_s": t["duration_s"],
            "price_cents": t["price_cents"],
            "buy_now_cents": max(0, (t["price_cents"] or 0) - (credit if t["id"] in this_month else 0)),
            "owner": ({"handle": t["o_handle"], "name": (HOUSE_NAME if t["o_is_house"] else t["o_name"]),
                       "kind": t["o_kind"]} if t["owner_account_id"] else None),
            "place": t["o_place"] or "",
            "has_art": art_ok,
            "art_v": int(os.path.getmtime(t["art_path"])) if art_ok else 0,
            "borrow_id": held.get(t["id"]),
            "purchased": t["id"] in bought,
            "mine": t["owner_account_id"] == aid,
            "heard": t["id"] in heard,
            "exclusive": S.is_exclusive(t),
        })
        if t["id"] in sim:
            out[-1]["sim"] = sim[t["id"]]
    return out


def _pool(conn, acct):
    """Every record this person could still buy here: not their own, not one
    they bought already."""
    import gr_sim
    bought = {r["track_id"] for r in conn.execute(
        "SELECT track_id FROM gr_purchases WHERE account_id=?", (acct["id"],))} | gr_sim.owned_ids(conn, acct["id"])
    return [r for r in conn.execute(
        "SELECT t.id, t.year, t.genre, t.owner_account_id, a.place_name FROM gr_tracks t"
        f" LEFT JOIN gr_accounts a ON a.id = t.owner_account_id WHERE {ON_SHELF}")
        if r["owner_account_id"] != acct["id"] and r["id"] not in bought]


def _facets(pool):
    """What a shopper can ask for: only what the shelves really hold."""
    genres, places, years = {}, {}, []
    for r in pool:
        for g in genres_of(r["genre"]):
            k = g.casefold()
            genres.setdefault(k, [g, 0])[1] += 1
        p = (r["place_name"] or "").strip()
        if p:
            places.setdefault(p.casefold(), p)
        if r["year"]:
            years.append(r["year"])
    decades = sorted({(y // 10) * 10 for y in years})
    return {
        "genres": [g for g, _n in sorted(genres.values(), key=lambda x: (-x[1], x[0].casefold()))][:40],
        "places": sorted(places.values(), key=str.casefold)[:60],
        "decades": decades,
        "years": {"min": min(years), "max": max(years)} if years else None,
    }


# ---------- asking for a crate ----------

def clean_ask(raw):
    """What a shopper asked for, tidied: {"genres": [...], "place": "", "from": year|None, "to": year|None}.
    All empty = anywhere."""
    raw = raw if isinstance(raw, dict) else {}
    genres = []
    for g in (raw.get("genres") or []) if isinstance(raw.get("genres"), (list, tuple)) else []:
        g = _txt(g, 40)
        if g and g.casefold() not in [x.casefold() for x in genres]:
            genres.append(g)

    def yr(v):
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        return v if 1000 <= v <= 2999 else None
    a, b = yr(raw.get("from")), yr(raw.get("to"))
    if a and b and a > b:
        a, b = b, a
    return {"genres": genres[:5], "place": _txt(raw.get("place"), 120), "from": a, "to": b}


def asked_for(ask):
    return bool(ask["genres"] or ask["place"] or ask["from"] or ask["to"])


def ask_words(ask):
    """The rule a mixed crate was put together by, in words the shopper can read."""
    bits = list(ask["genres"])
    if ask["place"]:
        bits.append(ask["place"])
    if ask["from"] and ask["to"]:
        bits.append(str(ask["from"]) if ask["from"] == ask["to"] else f"{ask['from']}–{ask['to']}")
    elif ask["from"]:
        bits.append(f"from {ask['from']}")
    elif ask["to"]:
        bits.append(f"up to {ask['to']}")
    return " · ".join(bits) or "Anywhere"


def _matches(row, ask):
    """Does this record fit the ask? A record that doesn't say (no year, no
    genre, no place) fits no ask on that point."""
    if ask["genres"]:
        have = {g.casefold() for g in genres_of(row["genre"])}
        if not have & {g.casefold() for g in ask["genres"]}:
            return False
    if ask["place"] and (row["place_name"] or "").strip().casefold() != ask["place"].casefold():
        return False
    if ask["from"] or ask["to"]:
        y = row["year"]
        if not y or (ask["from"] and y < ask["from"]) or (ask["to"] and y > ask["to"]):
            return False
    return True


def _out_crates(conn, not_by=None):
    """The crates out on the shop floor, each with what is in it, in its maker's order."""
    out = []
    for c in conn.execute(
            "SELECT c.*, a.name AS a_name, a.handle AS a_handle, a.is_house AS a_is_house"
            " FROM gr_crates c JOIN gr_accounts a ON a.id = c.account_id"
            " WHERE c.is_out=1 AND a.hidden_at IS NULL ORDER BY c.id").fetchall():
        if not_by is not None and c["account_id"] == not_by:
            continue
        items = [{"id": i["track_id"], "note": i["note"] or ""} for i in conn.execute(
            "SELECT i.track_id, i.note FROM gr_crate_items i JOIN gr_tracks t ON t.id = i.track_id"
            f" LEFT JOIN gr_accounts a ON a.id = t.owner_account_id WHERE i.crate_id=? AND {ON_SHELF}"
            " ORDER BY i.pos, i.id", (c["id"],))]
        if items:
            out.append({"id": c["id"], "name": c["name"], "note": c["note"] or "", "account_id": c["account_id"],
                        "by_name": _display(c, "a_"), "by_handle": c["a_handle"] or "", "items": items})
    return out


def make_pull(conn, acct, ask, rng=None, made_chance=None):
    """Hand this shopper a crate. → (pull id, None) or (None, (why, words)) with
    why = 'limit' (today's crates are used) or 'empty' (nothing to hand over —
    that doesn't use one up).

    Either a crate somebody made comes back whole, in its maker's order with
    their notes; or one is put together from the shelves: up to 25 records
    that fit the ask and that this shopper hasn't been handed today, in no
    order at all. A record that also sits in someone's crate keeps their note
    and says whose crate it is from — that is how a crate comes to be made of
    several."""
    rng = rng or _rng
    today = _today()
    aid = acct["id"]
    used = conn.execute("SELECT COUNT(*) FROM gr_crate_pulls WHERE account_id=? AND day=?",
                        (aid, today)).fetchone()[0]
    if used >= CRATES_PER_DAY:
        return None, ("limit", f"That's your {CRATES_PER_DAY} crates for today. More tomorrow.")
    pool = _pool(conn, acct)
    if not pool:
        return None, ("empty", "There are no records in the shop yet.")
    matching = [r for r in pool if _matches(r, ask)]
    if not matching:
        return None, ("empty", "Nothing in the shop fits that. Try asking for less.")
    seen = set()
    for p in conn.execute("SELECT items FROM gr_crate_pulls WHERE account_id=? AND day=?", (aid, today)):
        seen |= {i.get("id") for i in json.loads(p["items"] or "[]")}
    fresh = [r for r in matching if r["id"] not in seen]
    if not fresh:
        return None, ("empty", "You have been through everything that fits that today.")
    pool_ids, match_ids, fresh_ids = ({r["id"] for r in x} for x in (pool, matching, fresh))

    out = _out_crates(conn, not_by=aid)
    since = (datetime.now() - timedelta(days=MADE_AGAIN_DAYS)).isoformat(timespec="seconds")
    had = {r["crate_id"] for r in conn.execute(
        "SELECT crate_id FROM gr_crate_pulls WHERE account_id=? AND kind='made' AND created_at >= ?", (aid, since))}
    fits = []
    for c in out:
        if c["id"] in had:
            continue
        its = [i for i in c["items"] if i["id"] in pool_ids][:CRATE_MAX]
        if not its:
            continue
        if sum(1 for i in its if i["id"] in fresh_ids) * 2 < len(its):      # mostly gone through today already
            continue
        if asked_for(ask) and sum(1 for i in its if i["id"] in match_ids) * 2 < len(its):
            continue                                                         # less than half of it is what was asked for
        fits.append((c, its))

    chance = MADE_CHANCE if made_chance is None else made_chance
    if fits and rng.random() < chance:
        c, its = rng.choice(fits)
        pull = {"kind": "made", "crate_id": c["id"], "title": c["name"], "by_name": c["by_name"],
                "by_handle": c["by_handle"], "note": c["note"],
                "items": [{"id": i["id"], "note": i["note"]} for i in its], "sources": []}
    else:
        chosen = rng.sample(fresh, min(CRATE_MAX, len(fresh)))
        noted = {}
        for c in out:
            for i in c["items"]:
                noted.setdefault(i["id"], (i["note"], c))
        items, sources = [], {}
        for r in chosen:
            it = {"id": r["id"], "note": ""}
            if r["id"] in noted:
                note, c = noted[r["id"]]
                it["note"] = note
                it["from"] = {"crate": c["name"], "by": c["by_name"]}
                sources[c["id"]] = {"crate": c["name"], "by": c["by_name"]}
            items.append(it)
        pull = {"kind": "mixed", "crate_id": None, "title": ask_words(ask), "by_name": HOUSE_NAME,
                "by_handle": "", "note": "", "items": items, "sources": list(sources.values())}
    cur = conn.execute(
        "INSERT INTO gr_crate_pulls(account_id, day, kind, crate_id, title, by_name, by_handle, note, ask,"
        " items, sources, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, today, pull["kind"], pull["crate_id"], pull["title"], pull["by_name"], pull["by_handle"],
         pull["note"], json.dumps(ask), json.dumps(pull["items"]), json.dumps(pull["sources"]), S._now()))
    conn.commit()
    S._event(conn, aid, "crate_pull", {"pull": cur.lastrowid, "kind": pull["kind"], "crate": pull["crate_id"],
                                       "ask": ask, "count": len(pull["items"])})
    return cur.lastrowid, None


def make_pick(conn, acct, ids, by, title=""):
    """A crate a PLUG-IN picked for this shopper (docs/PLUGINS.md): the records
    it named, in its order, as many as are on the shelves and still for this
    person (not their own, not bought) — up to 25. It is one of today's three
    crates, and plays like any other (listening, the basket, notes). The
    plug-in's name is on it, so the shopper knows whose rule made it.
    → (pull id, None) or (None, (why, words)) like make_pull."""
    today, aid = _today(), acct["id"]
    used = conn.execute("SELECT COUNT(*) FROM gr_crate_pulls WHERE account_id=? AND day=?",
                        (aid, today)).fetchone()[0]
    if used >= CRATES_PER_DAY:
        return None, ("limit", f"That's your {CRATES_PER_DAY} crates for today. More tomorrow.")
    ok = {r["id"] for r in _pool(conn, acct)}
    chosen, seen = [], set()
    for i in ids or []:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if i in ok and i not in seen:
            seen.add(i)
            chosen.append({"id": i, "note": ""})
        if len(chosen) >= CRATE_MAX:
            break
    if not chosen:
        return None, ("empty", "None of the records it picked are in the shop for you.")
    by = _txt(by, PICK_BY_MAX) or "a plug-in"
    cur = conn.execute(
        "INSERT INTO gr_crate_pulls(account_id, day, kind, crate_id, title, by_name, by_handle, note, ask,"
        " items, sources, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, today, "plugin", None, _txt(title, 80) or f"Picked by {by}", by, "", "",
         json.dumps({"plugin": by}), json.dumps(chosen), "[]", S._now()))
    conn.commit()
    S._event(conn, aid, "crate_pull", {"pull": cur.lastrowid, "kind": "plugin", "by": by, "count": len(chosen)})
    return cur.lastrowid, None


def _pull_json(conn, acct, row, cards=True):
    items = json.loads(row["items"] or "[]")
    out = {
        "id": row["id"], "kind": row["kind"], "title": row["title"] or "",
        "by": {"name": row["by_name"] or "", "handle": row["by_handle"] or ""},
        "note": row["note"] or "", "ask": json.loads(row["ask"] or "{}"),
        "day": row["day"], "open": row["day"] == _today(), "count": len(items),
        "sources": json.loads(row["sources"] or "[]"), "at": row["created_at"],
    }
    if cards:
        by_id = {c["id"]: c for c in _cards(conn, acct, [i.get("id") for i in items])}
        out["items"] = [dict(by_id[i["id"]], note=i.get("note") or "", **({"from": i["from"]} if i.get("from") else {}))
                        for i in items if i.get("id") in by_id]
        out["count"] = len(out["items"])
    return out


# ---------- the listening copy ----------

_ff = [False, None]
_listen_locks, _listen_guard = {}, threading.Lock()


def _ffmpeg():
    if not _ff[0]:
        found = None
        try:
            import mr_ffmpeg
            found = mr_ffmpeg.ffmpeg_path()
        except Exception:
            found = None
        if not found:
            try:
                import imageio_ffmpeg
                found = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                found = None
        _ff[0], _ff[1] = True, found
    return _ff[1]


def listen_dir() -> Path:
    p = Path(S.db_path())
    return p.parent / f"{p.stem}_listen"


def listen_copy(track_row):
    """→ (path, mimetype) of what the shop plays for this record, or (None, why).
    A 128k MP3 with every tag taken off, made once and kept beside the db; made
    again if the real file is newer. The real file itself is only played when
    the server was started with MR_SHOP_PLAY_ORIGINALS=1 and can't make copies."""
    src = Path(track_row["path"] or "")
    dest = listen_dir() / f"{track_row['id']}.mp3"
    if not src.exists():
        # (the record's own file is away — a drive not plugged in — but its listening copy was
        #  made before: that is all the shop ever plays)
        try:
            if dest.stat().st_size > 0:
                return str(dest), "audio/mpeg"
        except OSError:
            pass
        return None, "the file is missing on the server"

    def good():
        try:
            return dest.stat().st_size > 0 and dest.stat().st_mtime >= src.stat().st_mtime
        except OSError:
            return False
    if good():
        return str(dest), "audio/mpeg"
    ff = _ffmpeg()
    if ff:
        with _listen_guard:
            lock = _listen_locks.setdefault(track_row["id"], threading.Lock())
        with lock:
            if not good():
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.stem + ".part.mp3")
                try:
                    subprocess.run(
                        [ff, "-nostdin", "-v", "error", "-y", "-i", str(src), "-vn", "-map_metadata", "-1",
                         "-ac", "2", "-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "128k", str(tmp)],
                        check=True, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    os.replace(tmp, dest)
                except Exception:
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
        if good():
            return str(dest), "audio/mpeg"
    if os.environ.get("MR_SHOP_PLAY_ORIGINALS") == "1":
        return str(src), _MIMES.get(src.suffix.lower(), "application/octet-stream")
    return None, "the shop can't make its listening copies on this server (ffmpeg is missing)"


def make_listen_copies():
    """Every record's listening copy, ahead of time (CLI: listen-copies)."""
    made = failed = 0
    with closing(S.db()) as conn:
        S.init_db(conn)
        rows = conn.execute("SELECT * FROM gr_tracks t WHERE COALESCE(t.status,'live')='live'").fetchall()
    for r in rows:
        path, _why = listen_copy(r)
        if path and path.endswith(".mp3") and "_listen" in path:
            made += 1
        else:
            failed += 1
    return {"listening_copies": made, "could_not": failed}


# ---------- one play ----------
# A record for sale plays ONCE for each person, whole, from inside a crate, the
# counter or blind. Asking for its listening copy IS the play: the server marks it
# heard as it hands the copy over, and never hands it to that person again. The
# app holds the copy only while that one play lasts (record_shop.py). To hear it
# again: borrow it or buy it.
HEARD_WORDS = "You've heard this one. To hear it again, borrow it or buy it."


def heard_ids(conn, aid, ids=None):
    if ids is not None:
        ids = [int(i) for i in ids]
        if not ids:
            return set()
        q = ",".join("?" * len(ids))
        return {r[0] for r in conn.execute(f"SELECT track_id FROM gr_heard WHERE account_id=? AND track_id IN ({q})",
                                           [aid] + ids)}
    return {r[0] for r in conn.execute("SELECT track_id FROM gr_heard WHERE account_id=?", (aid,))}


def _first_play(conn, acct, track, via):
    """None if this is the person's one play of it (and it is now marked heard); else
    the refusal. Someone who has borrowed or bought it hears it in their own room."""
    aid, tid = acct["id"], track["id"]
    if conn.execute("SELECT 1 FROM gr_heard WHERE account_id=? AND track_id=?", (aid, tid)).fetchone():
        words = HEARD_WORDS
        return no_json(words, 403, heard=True)
    conn.execute("INSERT OR IGNORE INTO gr_heard(account_id, track_id, via, at) VALUES(?,?,?,?)", (aid, tid, via, S._now()))
    conn.commit()
    S._event(conn, aid, "shop_listen", {"track_id": tid, "via": via, "owner": track["owner_account_id"]})
    return None


def _sim_me(conn, acct):
    import gr_sim
    return gr_sim.me_json(conn, acct)


def no_json(words, code=400, **more):
    return jsonify(dict({"error": words}, **more)), code


def _may_listen(conn, acct, tid, args):
    """None when this person may hear this record now; else the reason not."""
    aid, today = acct["id"], _today()
    pull = args.get("pull", type=int)
    if pull:
        row = conn.execute("SELECT * FROM gr_crate_pulls WHERE id=? AND account_id=?", (pull, aid)).fetchone()
        if not row:
            return "that isn't one of your crates"
        if row["day"] != today:
            return "that crate has closed"
        if tid not in {i.get("id") for i in json.loads(row["items"] or "[]")}:
            return "that record isn't in this crate"
        return None
    q = args.get("q", type=int)
    if q:
        row = conn.execute("SELECT * FROM gr_counter WHERE id=? AND asker_id=?", (q, aid)).fetchone()
        if not row or row["answer_track_id"] != tid:
            return "that isn't an answer to one of your questions"
        if row["settled"]:
            return "you have already decided on this one"
        until = (datetime.now() - timedelta(days=ANSWER_OPEN_DAYS)).isoformat(timespec="seconds")
        if (row["answered_at"] or "") < until:
            return "that answer has closed"
        return None
    # (a blind record is asked for by its turn, never by its own number: blind_listen)
    return "records in the shop play from inside a crate, the counter or blind"


# ---------- who may make crates ----------

def can_make(conn, acct):
    """Crates are made by people who sell here: artist, label and shop accounts,
    anyone with a record of their own on the shelves, and the Music Room itself."""
    if acct["kind"] in ("artist", "label", "shop"):
        return True
    try:
        if acct["is_house"]:
            return True
    except (IndexError, KeyError):
        pass
    return bool(conn.execute("SELECT 1 FROM gr_tracks WHERE owner_account_id=? LIMIT 1", (acct["id"],)).fetchone())


def _crate_json(conn, acct, c, cards=True):
    rows = conn.execute("SELECT * FROM gr_crate_items WHERE crate_id=? ORDER BY pos, id", (c["id"],)).fetchall()
    out = {"id": c["id"], "name": c["name"], "note": c["note"] or "", "is_out": bool(c["is_out"]),
           "count": len(rows), "updated_at": c["updated_at"]}
    if cards:
        by_id = {x["id"]: x for x in _cards(conn, acct, [r["track_id"] for r in rows])}
        out["items"] = [dict(by_id[r["track_id"]], note=r["note"] or "", from_crate_id=r["from_crate_id"])
                        for r in rows if r["track_id"] in by_id]
        out["count"] = len(out["items"])
    return out


def set_house(handle, on=True):
    """Mark an account as the Music Room's own (CLI: house <handle> [--off])."""
    with closing(S.db()) as conn:
        S.init_db(conn)
        row = conn.execute("SELECT id, name FROM gr_accounts WHERE handle=?", (handle,)).fetchone()
        if not row:
            raise SystemExit(f"no account with the handle '{handle}'")
        conn.execute("UPDATE gr_accounts SET is_house=? WHERE id=?", (1 if on else 0, row["id"]))
        conn.commit()
        return f"{row['name']} (@{handle}) {'now signs crates as ' + HOUSE_NAME if on else 'is an ordinary account again'}"


# ---------- routes ----------

def register(app, server):
    global S
    S = server

    def signed_in(fn):
        """Run fn(conn, acct) for the person asking; 401 when nobody is."""
        with closing(S.db()) as conn:
            acct, _dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            ensure(conn)
            acct = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (acct["id"],)).fetchone()
            return fn(conn, acct)

    def no(words, code=400, **more):
        return jsonify(dict({"error": words}, **more)), code

    def counts(conn, acct):
        aid, today = acct["id"], _today()
        one = lambda sql, *p: conn.execute(sql, p).fetchone()[0]
        return {
            "crates": max(0, CRATES_PER_DAY - one(
                "SELECT COUNT(*) FROM gr_crate_pulls WHERE account_id=? AND day=?", aid, today)),
            "asks": max(0, ASKS_PER_DAY - one(
                "SELECT COUNT(*) FROM gr_counter WHERE asker_id=? AND day=?", aid, today)),
            "answers": max(0, ANSWERS_PER_DAY - one(
                "SELECT COUNT(*) FROM gr_counter WHERE answer_by=? AND answer_day=?", aid, today)),
            "blind": max(0, BLIND_PER_DAY - one(
                "SELECT COUNT(*) FROM gr_blind WHERE account_id=? AND day=?", aid, today)),
        }

    def open_for(conn, acct):
        """How many questions this person could still be handed."""
        return conn.execute(
            "SELECT COUNT(*) FROM gr_counter q WHERE q.answered_at IS NULL AND q.asker_id != ?"
            " AND NOT EXISTS (SELECT 1 FROM gr_counter_skips s WHERE s.q_id = q.id AND s.account_id = ?)",
            (acct["id"], acct["id"])).fetchone()[0]

    # ── the shop, as this person finds it today ──
    @app.get("/api/shop")
    def shop_state():
        def go(conn, acct):
            aid, today = acct["id"], _today()
            pool = _pool(conn, acct)
            pulls = conn.execute("SELECT * FROM gr_crate_pulls WHERE account_id=? AND day=? ORDER BY id",
                                 (aid, today)).fetchall()
            one = lambda sql, *p: conn.execute(sql, p).fetchone()[0]
            return jsonify({
                "limits": {"crates": CRATES_PER_DAY, "crate": CRATE_MAX, "asks": ASKS_PER_DAY,
                           "answers": ANSWERS_PER_DAY, "blind": BLIND_PER_DAY},
                "left": counts(conn, acct),
                "records": len(pool),
                "facets": _facets(pool),
                "pulls": [_pull_json(conn, acct, p, cards=False) for p in pulls],
                "counter": {
                    "waiting": one("SELECT COUNT(*) FROM gr_counter WHERE asker_id=? AND answered_at IS NULL", aid),
                    "new": one("SELECT COUNT(*) FROM gr_counter WHERE asker_id=? AND answered_at IS NOT NULL"
                               " AND seen_at IS NULL", aid),
                    "open": open_for(conn, acct),
                },
                "can_make": can_make(conn, acct),
                "listening": bool(_ffmpeg()) or os.environ.get("MR_SHOP_PLAY_ORIGINALS") == "1"
                             or bool(conn.execute("SELECT 1 FROM gr_tracks WHERE spotify_uri IS NOT NULL LIMIT 1").fetchone()),
                "sim": _sim_me(conn, acct),
                "day": today,
            })
        return signed_in(go)

    @app.get("/api/shop/news")
    def shop_news():
        """Light enough to ask often: answers waiting to be looked at."""
        def go(conn, acct):
            n = conn.execute("SELECT COUNT(*) FROM gr_counter WHERE asker_id=? AND answered_at IS NOT NULL"
                             " AND seen_at IS NULL", (acct["id"],)).fetchone()[0]
            return jsonify({"answers": n})
        return signed_in(go)

    # ── crates ──
    @app.post("/api/shop/crates/pull")
    def shop_pull():
        body = request.get_json(force=True, silent=True) or {}
        pick = body.get("pick") if isinstance(body.get("pick"), dict) else None
        ask = clean_ask(body)

        def go(conn, acct):
            if pick:                           # a plug-in's pick (make_pick)
                ids = pick.get("ids") if isinstance(pick.get("ids"), list) else []
                pid, why = make_pick(conn, acct, ids[:200], pick.get("by"), pick.get("title"))
            else:
                pid, why = make_pull(conn, acct, ask)
            if why:
                return no(why[1], 403 if why[0] == "limit" else 404, **{why[0]: True})
            row = conn.execute("SELECT * FROM gr_crate_pulls WHERE id=?", (pid,)).fetchone()
            return jsonify({"pull": _pull_json(conn, acct, row), "left": counts(conn, acct)})
        return signed_in(go)

    @app.get("/api/shop/pulls/<int:pid>")
    def shop_pull_get(pid):
        def go(conn, acct):
            row = conn.execute("SELECT * FROM gr_crate_pulls WHERE id=? AND account_id=?",
                               (pid, acct["id"])).fetchone()
            if not row:
                return no("that isn't one of your crates", 404)
            if row["day"] != _today():
                return no("That crate has closed. A crate stays open until the end of the day it was pulled.",
                          410, closed=True)
            return jsonify({"pull": _pull_json(conn, acct, row)})
        return signed_in(go)

    @app.get("/api/shop/listen/<int:tid>")
    def shop_listen(tid):
        with closing(S.db()) as conn:
            acct, _dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            ensure(conn)
            why = _may_listen(conn, acct, tid, request.args)
            if why:
                return no(why, 403, closed=True)
            track = conn.execute("SELECT * FROM gr_tracks WHERE id=?", (tid,)).fetchone()
            if not track or (track["status"] or "live") != "live":
                return no("that record isn't in the shop now", 404)
            import gr_sim
            streamed = gr_sim.listen_json(track)
            path = mime = None
            if not streamed:
                # the copy FIRST, the play counted after: a copy that couldn't be made used to cost
                # the person their one play — "try again" answered "you've heard this one"
                path, mime = listen_copy(track)
                if not path:
                    return no(mime, 503)
            refused = _first_play(conn, acct, track, next((k for k in ("pull", "q") if request.args.get(k)), ""))
            if refused:
                return refused
            if streamed:                       # (no file: it plays once from the listener's own Spotify)
                return jsonify(streamed)
        resp = send_file(path, mimetype=mime, conditional=True)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ── finding a record in the shop by its words (for making a crate, for answering at the counter) ──
    @app.get("/api/shop/search")
    def shop_search():
        words = [w for w in _txt(request.args.get("q"), 80).casefold().split() if w]

        def go(conn, acct):
            rows = conn.execute(
                "SELECT t.id, t.title, t.artist, t.album, t.label, t.genre, a.name AS o_name FROM gr_tracks t"
                f" LEFT JOIN gr_accounts a ON a.id = t.owner_account_id WHERE {ON_SHELF}"
                " ORDER BY t.added_at DESC, t.id DESC").fetchall()
            hits = []
            for r in rows:
                hay = " ".join(str(r[k] or "") for k in ("title", "artist", "album", "label", "genre", "o_name")).casefold()
                if all(w in hay for w in words):
                    hits.append(r["id"])
                    if len(hits) >= 40:
                        break
            return jsonify({"records": _cards(conn, acct, hits)})
        return signed_in(go)

    # ── making crates (sellers) ──
    @app.get("/api/my/crates")
    def my_crates():
        def go(conn, acct):
            rows = conn.execute("SELECT * FROM gr_crates WHERE account_id=? ORDER BY updated_at DESC, id DESC",
                                (acct["id"],)).fetchall()
            return jsonify({"crates": [_crate_json(conn, acct, c) for c in rows],
                            "can_make": can_make(conn, acct), "max": CRATE_MAX})
        return signed_in(go)

    @app.post("/api/my/crates")
    def my_crates_save():
        """Make a crate or save one whole: {id?, name, note, is_out, items:[{id, note, from_crate_id?}]}."""
        d = request.get_json(force=True, silent=True) or {}

        def go(conn, acct):
            if not can_make(conn, acct):
                return no("Crates are made by people who sell records here.", 403)
            name = _txt(d.get("name"), NAME_MAX)
            if not name:
                return no("Give the crate a name.")
            raw = d.get("items") if isinstance(d.get("items"), list) else []
            items, seen = [], set()
            for it in raw:
                it = it if isinstance(it, dict) else {"id": it}
                try:
                    tid = int(it.get("id"))
                except (TypeError, ValueError):
                    continue
                if tid in seen:
                    continue
                seen.add(tid)
                try:
                    src = int(it.get("from_crate_id")) if it.get("from_crate_id") else None
                except (TypeError, ValueError):
                    src = None
                items.append((tid, _txt(it.get("note"), WHY_MAX), src))
            if len(items) > CRATE_MAX:
                return no(f"A crate holds {CRATE_MAX} records at most. Take {len(items) - CRATE_MAX} out.")
            if items:
                q = ",".join("?" * len(items))
                have = {r[0] for r in conn.execute(
                    f"SELECT t.id FROM gr_tracks t LEFT JOIN gr_accounts a ON a.id = t.owner_account_id"
                    f" WHERE t.id IN ({q}) AND {ON_SHELF}", [i[0] for i in items])}
                items = [i for i in items if i[0] in have]
            is_out = 1 if d.get("is_out") else 0
            if is_out and not items:
                return no("An empty crate can't go out. Put a record in it first.")
            cid = d.get("id")
            now = S._now()
            if cid:
                row = conn.execute("SELECT * FROM gr_crates WHERE id=? AND account_id=?",
                                   (cid, acct["id"])).fetchone()
                if not row:
                    return no("not one of your crates", 404)
                conn.execute("UPDATE gr_crates SET name=?, note=?, is_out=?, updated_at=? WHERE id=?",
                             (name, _txt(d.get("note"), NOTE_MAX), is_out, now, cid))
            else:
                n = conn.execute("SELECT COUNT(*) FROM gr_crates WHERE account_id=?", (acct["id"],)).fetchone()[0]
                if n >= MAKER_CRATES_MAX:
                    return no(f"You have {MAKER_CRATES_MAX} crates. Take one away to make another.")
                cid = conn.execute(
                    "INSERT INTO gr_crates(account_id, name, note, is_out, created_at, updated_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (acct["id"], name, _txt(d.get("note"), NOTE_MAX), is_out, now, now)).lastrowid
            conn.execute("DELETE FROM gr_crate_items WHERE crate_id=?", (cid,))
            for pos, (tid, note, src) in enumerate(items):
                conn.execute("INSERT INTO gr_crate_items(crate_id, track_id, pos, note, from_crate_id)"
                             " VALUES(?,?,?,?,?)", (cid, tid, pos, note or None, src))
            conn.commit()
            S._event(conn, acct["id"], "crate_save", {"crate": cid, "count": len(items), "out": bool(is_out)})
            row = conn.execute("SELECT * FROM gr_crates WHERE id=?", (cid,)).fetchone()
            return jsonify({"crate": _crate_json(conn, acct, row)})
        return signed_in(go)

    @app.delete("/api/my/crates/<int:cid>")
    def my_crates_delete(cid):
        def go(conn, acct):
            row = conn.execute("SELECT id FROM gr_crates WHERE id=? AND account_id=?", (cid, acct["id"])).fetchone()
            if not row:
                return no("not one of your crates", 404)
            conn.execute("DELETE FROM gr_crate_items WHERE crate_id=?", (cid,))
            conn.execute("DELETE FROM gr_crates WHERE id=?", (cid,))
            conn.commit()
            return jsonify({"deleted": cid})
        return signed_in(go)

    @app.get("/api/shop/crates/out")
    def shop_crates_out():
        """The crates out on the floor — for a seller pulling one into their own."""
        def go(conn, acct):
            if not can_make(conn, acct):
                return no("Crates are made by people who sell records here.", 403)
            return jsonify({"crates": [
                {"id": c["id"], "name": c["name"], "note": c["note"], "by": c["by_name"],
                 "mine": c["account_id"] == acct["id"], "count": len(c["items"]),
                 "items": [dict(card, note=next((i["note"] for i in c["items"] if i["id"] == card["id"]), ""))
                           for card in _cards(conn, acct, [i["id"] for i in c["items"]])]}
                for c in _out_crates(conn)]})
        return signed_in(go)

    # ── the counter ──
    def q_json(conn, acct, q, card=True):
        out = {"id": q["id"], "text": q["text"], "asked_at": q["created_at"], "answered": bool(q["answered_at"])}
        if q["answered_at"]:
            who = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (q["answer_by"],)).fetchone()
            until = (datetime.now() - timedelta(days=ANSWER_OPEN_DAYS)).isoformat(timespec="seconds")
            out["answer"] = {
                "text": q["answer_text"] or "", "at": q["answered_at"],
                "by": {"name": _display(who) if who else "", "handle": (who["handle"] if who else "") or ""},
                "seen": bool(q["seen_at"]), "settled": q["settled"] or "",
                "can_listen": not q["settled"] and (q["answered_at"] or "") >= until,
            }
            if card:
                cards = _cards(conn, acct, [q["answer_track_id"]])
                out["answer"]["record"] = cards[0] if cards else None
        return out

    @app.post("/api/shop/counter/ask")
    def counter_ask():
        text = _txt((request.get_json(force=True, silent=True) or {}).get("text"), ASK_MAX)

        def go(conn, acct):
            if len(text) < 3:
                return no("Ask in a few words.")
            if counts(conn, acct)["asks"] <= 0:
                return no(f"That's your {ASKS_PER_DAY} questions for today. More tomorrow.", 403, limit=True)
            qid = conn.execute("INSERT INTO gr_counter(asker_id, text, day, created_at) VALUES(?,?,?,?)",
                               (acct["id"], text, _today(), S._now())).lastrowid
            conn.commit()
            S._event(conn, acct["id"], "counter_ask", {"q": qid, "text": text})
            row = conn.execute("SELECT * FROM gr_counter WHERE id=?", (qid,)).fetchone()
            return jsonify({"question": q_json(conn, acct, row), "left": counts(conn, acct)})
        return signed_in(go)

    @app.get("/api/shop/counter/mine")
    def counter_mine():
        def go(conn, acct):
            rows = conn.execute("SELECT * FROM gr_counter WHERE asker_id=? ORDER BY id DESC LIMIT 80",
                                (acct["id"],)).fetchall()
            return jsonify({"questions": [q_json(conn, acct, q) for q in rows], "left": counts(conn, acct),
                            "open": open_for(conn, acct)})
        return signed_in(go)

    @app.delete("/api/shop/counter/<int:qid>")
    def counter_withdraw(qid):
        """Take back a question nobody has answered yet."""
        def go(conn, acct):
            cur = conn.execute("DELETE FROM gr_counter WHERE id=? AND asker_id=? AND answered_at IS NULL",
                               (qid, acct["id"]))
            conn.commit()
            if not cur.rowcount:
                return no("That question is answered already, or isn't yours.", 409)
            conn.execute("DELETE FROM gr_counter_skips WHERE q_id=?", (qid,))
            conn.commit()
            return jsonify({"withdrawn": qid})
        return signed_in(go)

    def held_question(conn, acct):
        return conn.execute(
            "SELECT * FROM gr_counter WHERE held_by=? AND held_until > ? AND answered_at IS NULL"
            " ORDER BY created_at, id LIMIT 1", (acct["id"], S._now())).fetchone()

    @app.post("/api/shop/counter/take")
    def counter_take():
        """Be handed a question: the oldest one still open that isn't yours,
        that you haven't skipped, and that nobody else is holding right now."""
        def go(conn, acct):
            left = counts(conn, acct)
            if left["answers"] <= 0:
                return no(f"That's your {ANSWERS_PER_DAY} answers for today. More tomorrow.", 403, limit=True)
            q = held_question(conn, acct)
            if not q:
                now = S._now()
                q = conn.execute(
                    "SELECT * FROM gr_counter q WHERE q.answered_at IS NULL AND q.asker_id != ?"
                    " AND (q.held_by IS NULL OR q.held_until <= ? OR q.held_by = ?)"
                    " AND NOT EXISTS (SELECT 1 FROM gr_counter_skips s WHERE s.q_id = q.id AND s.account_id = ?)"
                    " ORDER BY q.created_at, q.id LIMIT 1",
                    (acct["id"], now, acct["id"], acct["id"])).fetchone()
                if not q:
                    return jsonify({"none": True, "left": left})
                until = (datetime.now() + timedelta(minutes=HOLD_MINUTES)).isoformat(timespec="seconds")
                conn.execute("UPDATE gr_counter SET held_by=?, held_until=? WHERE id=?", (acct["id"], until, q["id"]))
                conn.commit()
            asker = conn.execute("SELECT * FROM gr_accounts WHERE id=?", (q["asker_id"],)).fetchone()
            return jsonify({"question": {"id": q["id"], "text": q["text"], "asked_at": q["created_at"],
                                         "asker": {"name": _display(asker) if asker else "",
                                                   "handle": (asker["handle"] if asker else "") or ""}},
                            "left": left})
        return signed_in(go)

    @app.post("/api/shop/counter/<int:qid>/skip")
    def counter_skip(qid):
        def go(conn, acct):
            q = conn.execute("SELECT * FROM gr_counter WHERE id=?", (qid,)).fetchone()
            if not q or q["asker_id"] == acct["id"]:
                return no("no such question", 404)
            conn.execute("INSERT OR IGNORE INTO gr_counter_skips(q_id, account_id, at) VALUES(?,?,?)",
                         (qid, acct["id"], S._now()))
            conn.execute("UPDATE gr_counter SET held_by=NULL, held_until=NULL WHERE id=? AND held_by=?",
                         (qid, acct["id"]))
            conn.commit()
            return jsonify({"skipped": qid})
        return signed_in(go)

    @app.post("/api/shop/counter/<int:qid>/answer")
    def counter_answer(qid):
        d = request.get_json(force=True, silent=True) or {}
        why = _txt(d.get("text"), WHY_MAX)

        def go(conn, acct):
            q = conn.execute("SELECT * FROM gr_counter WHERE id=?", (qid,)).fetchone()
            if not q or q["asker_id"] == acct["id"]:
                return no("no such question", 404)
            if q["answered_at"]:
                return no("Someone answered this one a moment ago.", 409, taken=True)
            if q["held_by"] and q["held_by"] != acct["id"] and (q["held_until"] or "") > S._now():
                return no("Someone else has this question in hand.", 409, taken=True)
            if counts(conn, acct)["answers"] <= 0:
                return no(f"That's your {ANSWERS_PER_DAY} answers for today. More tomorrow.", 403, limit=True)
            try:
                tid = int(d.get("track_id"))
            except (TypeError, ValueError):
                return no("Choose a record from the shop.")
            track = conn.execute("SELECT * FROM gr_tracks WHERE id=?", (tid,)).fetchone()
            if not track or (track["status"] or "live") != "live":
                return no("That record isn't in the shop.", 404)
            if len(why) < 3:
                return no("Say in a line why this one.")
            if track["owner_account_id"] == q["asker_id"]:
                return no("That is one of their own records. Choose another.", 409)
            if conn.execute("SELECT 1 FROM gr_purchases WHERE account_id=? AND track_id=?",
                            (q["asker_id"], tid)).fetchone():
                return no("They have that one already. Choose another.", 409)
            now = S._now()
            cur = conn.execute(
                "UPDATE gr_counter SET answered_at=?, answer_by=?, answer_day=?, answer_track_id=?, answer_text=?,"
                " held_by=NULL, held_until=NULL WHERE id=? AND answered_at IS NULL",
                (now, acct["id"], _today(), tid, why, qid))
            conn.commit()
            if not cur.rowcount:
                return no("Someone answered this one a moment ago.", 409, taken=True)
            S._event(conn, acct["id"], "counter_answer", {"q": qid, "track_id": tid, "asker": q["asker_id"],
                                                          "owner": track["owner_account_id"]})
            return jsonify({"answered": qid, "left": counts(conn, acct)})
        return signed_in(go)

    @app.post("/api/shop/counter/<int:qid>/seen")
    def counter_seen(qid):
        def go(conn, acct):
            conn.execute("UPDATE gr_counter SET seen_at=COALESCE(seen_at, ?) WHERE id=? AND asker_id=?"
                         " AND answered_at IS NOT NULL", (S._now(), qid, acct["id"]))
            conn.commit()
            return jsonify({"seen": qid})
        return signed_in(go)

    @app.post("/api/shop/counter/<int:qid>/settle")
    def counter_settle(qid):
        """What the asker did with the answer: basket | note | pass. Listening to it ends here."""
        choice = (request.get_json(force=True, silent=True) or {}).get("choice")

        def go(conn, acct):
            if choice not in ("basket", "note", "pass"):
                return no("basket, note or pass")
            cur = conn.execute(
                "UPDATE gr_counter SET settled=?, settled_at=?, seen_at=COALESCE(seen_at, ?) WHERE id=?"
                " AND asker_id=? AND answered_at IS NOT NULL", (choice, S._now(), S._now(), qid, acct["id"]))
            conn.commit()
            if not cur.rowcount:
                return no("no such answer", 404)
            S._event(conn, acct["id"], "counter_settle", {"q": qid, "choice": choice})
            return jsonify({"settled": choice})
        return signed_in(go)

    # ── blind ──
    @app.post("/api/shop/blind/next")
    def blind_next():
        """The next record to hear with no name on it. One left undecided today
        comes back again rather than a new one being used up."""
        def go(conn, acct):
            aid, today = acct["id"], _today()
            row = conn.execute("SELECT * FROM gr_blind WHERE account_id=? AND day=? AND choice IS NULL"
                               " ORDER BY id DESC LIMIT 1", (aid, today)).fetchone()
            if not row:
                if counts(conn, acct)["blind"] <= 0:
                    return no(f"That's your {BLIND_PER_DAY} for today. More tomorrow.", 403, limit=True)
                heard = heard_ids(conn, aid)
                pool = [r["id"] for r in _pool(conn, acct) if r["id"] not in heard]       # (a record heard can't play again)
                had = {r[0] for r in conn.execute("SELECT track_id FROM gr_blind WHERE account_id=?", (aid,))}
                had_today = {r[0] for r in conn.execute(
                    "SELECT track_id FROM gr_blind WHERE account_id=? AND day=?", (aid, today))}
                fresh = [i for i in pool if i not in had] or [i for i in pool if i not in had_today]
                if not fresh:
                    return no("There is nothing left in the shop to hear blind today.", 404, empty=True)
                bid = conn.execute("INSERT INTO gr_blind(account_id, day, track_id, created_at) VALUES(?,?,?,?)",
                                   (aid, today, _rng.choice(fresh), S._now())).lastrowid
                conn.commit()
                row = conn.execute("SELECT * FROM gr_blind WHERE id=?", (bid,)).fetchone()
            dur = conn.execute("SELECT duration_s FROM gr_tracks WHERE id=?", (row["track_id"],)).fetchone()
            was_heard = bool(conn.execute("SELECT 1 FROM gr_heard WHERE account_id=? AND track_id=?",
                                          (aid, row["track_id"])).fetchone())
            # nothing here says what it is: the record's own number is not sent either
            return jsonify({"blind": {"id": row["id"], "duration_s": dur["duration_s"] if dur else None, "heard": was_heard},
                            "left": counts(conn, acct)})
        return signed_in(go)

    @app.get("/api/shop/blind/<int:bid>/listen")
    def blind_listen(bid):
        """The blind record's sound, asked for by the turn's number alone — the
        page never learns which record it is until it is turned over."""
        with closing(S.db()) as conn:
            acct, _dev = S._auth(conn)
            if not acct:
                return S._unauthorized()
            ensure(conn)
            row = conn.execute("SELECT * FROM gr_blind WHERE id=? AND account_id=?", (bid, acct["id"])).fetchone()
            if not row:
                return no("that isn't the record in front of you", 403, closed=True)
            last = conn.execute("SELECT MAX(id) FROM gr_blind WHERE account_id=?", (acct["id"],)).fetchone()[0]
            if row["day"] != _today() or row["id"] != last:
                return no("that one has gone back on the shelf", 403, closed=True)
            track = conn.execute("SELECT * FROM gr_tracks WHERE id=?", (row["track_id"],)).fetchone()
            if not track or (track["status"] or "live") != "live":
                return no("that record has left the shop", 404)
            import gr_sim
            streamed = gr_sim.listen_json(track)
            path = mime = None
            if not streamed:                   # (the copy first, the play counted after — as in a crate)
                path, mime = listen_copy(track)
                if not path:
                    return no(mime, 503)
            refused = _first_play(conn, acct, track, "blind")
            if refused:
                return refused
            if streamed:
                return jsonify(streamed)
        resp = send_file(path, mimetype=mime, conditional=True)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/shop/blind/<int:bid>/decide")
    def blind_decide(bid):
        """Decide first — basket | note | pass — and only then is it turned over."""
        choice = (request.get_json(force=True, silent=True) or {}).get("choice")

        def go(conn, acct):
            if choice not in ("basket", "note", "pass"):
                return no("basket, note or pass")
            row = conn.execute("SELECT * FROM gr_blind WHERE id=? AND account_id=?", (bid, acct["id"])).fetchone()
            if not row:
                return no("no such record in front of you", 404)
            if not row["choice"]:
                conn.execute("UPDATE gr_blind SET choice=?, decided_at=? WHERE id=?", (choice, S._now(), bid))
                conn.commit()
                S._event(conn, acct["id"], "blind_decide", {"blind": bid, "track_id": row["track_id"],
                                                            "choice": choice})
            cards = _cards(conn, acct, [row["track_id"]])
            return jsonify({"choice": row["choice"] or choice, "record": cards[0] if cards else None,
                            "left": counts(conn, acct)})
        return signed_in(go)
