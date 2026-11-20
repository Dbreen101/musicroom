"""
explore_globe.py — what the Globe in Explore shows.

Explore has a third way in beside "Music Rooms" and "The World": a globe
(static/js/explore_globe.js). This module gathers the THINGS that go on it and
keeps every route the globe needs (app.py only calls `register(app)`):

    GET /api/globe/things             every thing, each with its place or none
    GET /api/globe/things?part=sources  only what is on this laptop (answers at once)
    GET /api/globe/things?part=rooms    only the rooms (waits on the rooms server)

A thing is one of
    room         a public music room (the Green Room directory)
    publication  from the source catalogue, or a source the listener follows
    station      "
    website      "
and may carry a PLACE = {name, lat, lon}: a name in its owner's own words and
a spot on the globe. A thing with a place sits on the globe. A thing with no
place is UNIVERSAL — it belongs to nowhere in particular and orbits the globe.

Where places come from:
  · a room's owner sets it on /myroom ("Where is your room?") — kept by the
    Green Room server (gr_server.py: gr_accounts.place_name / lat / lon). A
    server from before places knew nothing of them: its rooms are universal.
  · a catalogue entry's place is written in static/data/source_catalogue.json,
    only where its home is well known. Platforms that are for everywhere
    (Bandcamp, SoundCloud, Discogs…) are left universal on purpose.
  · a source the listener added by hand has no place: universal.

Nothing here leaves the laptop; the rooms come from the server the listener is
already signed in to.
"""

import re
import sqlite3
from contextlib import closing

KINDS = ("room", "publication", "station", "website")
# the listener's own sources → the globe's kinds
_SOURCE_KIND = {"magazine": "publication", "blog": "publication", "mailing_list": "publication",
                "station": "station"}


def clean_place(p):
    """A place as stored → {name, lat, lon} or None. A place needs a real spot
    on the globe; a name alone is not one (the thing stays universal)."""
    if not isinstance(p, dict):
        return None
    try:
        lat, lon = float(p.get("lat")), float(p.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return {"name": str(p.get("name") or "").strip()[:120], "lat": round(lat, 5), "lon": round(lon, 5)}


def _host(url):
    m = re.match(r"^(?:https?://)?(?:www\.)?([^/?#]+)", (url or "").strip().lower())
    return m.group(1) if m else ""


def _own_sources():
    """The sources the listener follows (read straight from the library — this
    module must not import app.py)."""
    try:
        from mr_paths import DB_PATH
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT id, name, url, kind, description, topics FROM sources ORDER BY name COLLATE NOCASE")]
    except Exception:
        return []


PARTS = ("sources", "rooms")


def things(rooms_fn=None, catalogue_fn=None, sources_fn=None, parts=PARTS):
    """Everything the globe can show → {"things": [...], "rooms_error": str|None}.
    The three sources can be swapped for tests. `parts` picks which halves to
    gather: "sources" (the catalogue and the listener's own sources — on this
    laptop, instant) and "rooms" (asked of the rooms server — may take a moment,
    or fail, without holding the rest up)."""
    out = []
    if "sources" in parts:
        out.extend(_source_things(catalogue_fn, sources_fn))
    rooms_error = None
    if "rooms" in parts:
        rooms, rooms_error = _room_things(rooms_fn)
        out.extend(rooms)
    return {"things": out, "rooms_error": rooms_error}


def _source_things(catalogue_fn=None, sources_fn=None):
    out, seen_hosts = [], set()
    own = (sources_fn or _own_sources)()
    own_hosts = {_host(s.get("url")) for s in own if s.get("url")}

    if catalogue_fn is None:
        import source_catalogue
        catalogue_fn = source_catalogue.all_entries
    for e in catalogue_fn() or []:
        kind = e.get("type") if e.get("type") in KINDS else "website"
        h = _host(e.get("url"))
        seen_hosts.add(h)
        out.append({
            "id": "cat:" + str(e.get("id")), "kind": kind, "name": e.get("name") or "",
            "url": e.get("url") or "", "blurb": e.get("blurb") or "",
            "tags": [str(t) for t in (e.get("tags") or [])][:8],
            "place": clean_place(e.get("place")),
            "cat_id": e.get("id"), "src_kind": e.get("kind") or "", "feed_url": e.get("feed_url") or "",
            "added": bool(h and h in own_hosts),
        })

    for s in own:                       # the listener's own additions that the catalogue doesn't hold
        h = _host(s.get("url"))
        if not h or h in seen_hosts:
            continue
        seen_hosts.add(h)
        topics = [t.strip() for t in re.split(r"[,;]", s.get("topics") or "") if t.strip()][:8]
        out.append({
            "id": "src:" + str(s.get("id")), "kind": _SOURCE_KIND.get(s.get("kind") or "", "website"),
            "name": s.get("name") or h, "url": s.get("url") or "", "blurb": s.get("description") or "",
            "tags": topics, "place": None, "added": True, "mine": True,
        })
    return out


def _room_things(rooms_fn=None):
    """→ (rooms as things, None) or ([], why they couldn't be read)."""
    out = []
    try:
        if rooms_fn is None:
            import green_room
            rooms_fn = green_room.rooms
        for r in rooms_fn() or []:
            if not r.get("handle"):
                continue
            out.append({
                "id": "room:" + str(r["handle"]), "kind": "room", "sub": r.get("kind") or "listener",
                "name": r.get("name") or r["handle"], "handle": r["handle"], "blurb": r.get("bio") or "",
                "tags": [], "count": r.get("track_count") or 0,
                "covers": (r.get("cover_track_ids") or [])[:4],
                "place": clean_place(r.get("place")),      # absent on a server from before places → universal
            })
    except Exception as e:              # not signed in, the server is away: the rest still shows
        return [], (str(e) or "the directory of rooms can't be read right now")
    return out, None


def register(app):
    from flask import jsonify, request

    @app.route("/api/globe/things")
    def api_globe_things():
        part = (request.args.get("part") or "").strip().lower()
        return jsonify(things(parts=(part,) if part in PARTS else PARTS))
