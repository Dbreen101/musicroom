"""
gr_sim_app.py — the app's side of the credits trial (gr_sim.py on the rooms
server; 2026-11-20).

    /api/gr/sim/me        credits, the room, the trial's numbers — and the
                          Spotify key the master gave this person, which the
                          app takes up by itself (no setup page): with a key,
                          "Sign in to Spotify" works and the deck plays whole
                          tracks in their own Spotify; without one, records
                          play in Spotify's own player on the page.
    /api/gr/sim/home|buy|out     bring home, buy, take out (passed to the server)
    /api/gr/sim/mine      everything this person has from the shop, as records
    /api/gr/sim/record/<key>     one record, whole, with what it would cost
    /api/gr/sim/played    "I pressed play on one of my shop records" (the log)
    /api/gr/sim/sync      the MASTER's app reads David's playlist and sends its
                          records to the server: every album / single a
                          playlist track is on, whole (a compilation: just the
                          track). Also every hour, by itself, while this app
                          is signed in as the master and a playlist is set.

Spotify's rules this leans on (checked 2026-11-20): an app in development mode
reads a playlist only if the signed-in person owns it or collaborates on it
(GET /playlists/{id}/items — /tracks was removed in Feb 2026); GET
/albums/{id}/tracks is still there.
"""

import re
import threading
import time

from flask import Response, jsonify, request

import green_room

_D = {}            # what app.py hands over: get_setting, set_setting, spotify (a function → SpotifyClient), is_gr
_me_cache = {"at": 0.0, "data": None}
_sync = {"running": False, "step": "", "done": 0, "total": 0, "result": None, "error": "", "at": 0.0}
_sync_lock = threading.Lock()
PLAYLIST_FIELDS = ("items(item(id,type,name,duration_ms,track_number,disc_number,artists(id,name),"
                   "album(id,name,album_type,total_tracks,release_date,images,artists(id,name)))),next,total")
SID = re.compile(r"^[0-9A-Za-z]{22}$")


def _call(method, path, payload=None, params=None):
    try:
        code, d = green_room.shop_call(method, path, payload, params)
    except green_room.GRError as e:
        return {"error": str(e)}, 502
    return d, code


# ---------- the Spotify key the master gave this person ----------

def adopt_key(me):
    """Take up (or let go of) the Spotify key the server says is this person's.
    A Client ID someone typed in themselves is never replaced."""
    cid = (me or {}).get("spotify_client_id") or ""
    get, put = _D["get_setting"], _D["set_setting"]
    cur = (get("spotify_client_id", "") or "").strip()
    ours = (get("spotify_client_id_from", "") or "") == "server"
    if cid == cur:
        return
    if cur and not ours:
        return                                   # their own key, typed in on /spotify
    try:
        if cur:
            _D["spotify"]().disconnect()          # a sign-in belongs to the key it was made with
    except Exception:
        pass
    put("spotify_client_id", cid)
    put("spotify_client_id_from", "server" if cid else "")


def me(fresh=False):
    now = time.time()
    if not fresh and _me_cache["data"] and now - _me_cache["at"] < 15:
        return _me_cache["data"], 200
    d, code = _call("GET", "/api/sim/me")
    if code == 200:
        _me_cache.update(at=now, data=d)
        try:
            adopt_key(d)
        except Exception:
            pass
    return d, code


# ---------- reading the playlist (the master's app) ----------

def _image(images):
    imgs = [i for i in (images or []) if isinstance(i, dict) and i.get("url")]
    imgs.sort(key=lambda i: -(i.get("width") or 0))
    best = next((i for i in imgs if (i.get("width") or 0) <= 800), imgs[0] if imgs else None)
    return best["url"] if best else ""


def _artists(xs):
    return [{"id": a["id"], "name": a.get("name") or ""} for a in (xs or []) if isinstance(a, dict) and SID.match(str(a.get("id") or ""))]


def _track(x):
    return {"id": x["id"], "name": x.get("name") or "", "track_number": x.get("track_number") or 0,
            "disc_number": x.get("disc_number") or 1, "duration_ms": x.get("duration_ms") or 0,
            "artists": _artists(x.get("artists"))}


def read_playlist(sp, pid):
    """→ (tracks on the playlist, the playlist's name, why it stopped or '')"""
    name = ""
    head = sp._api_get(f"/playlists/{pid}", {"fields": "name"})
    if isinstance(head, dict) and not head.get("error"):
        name = head.get("name") or ""
    out, offset = [], 0
    while True:
        d = sp._api_get(f"/playlists/{pid}/items", {"limit": 100, "offset": offset, "fields": PLAYLIST_FIELDS})
        if not isinstance(d, dict) or d.get("error"):
            st = (d or {}).get("status")
            if st in (403, 404):
                return out, name, ("Spotify won't let the Music Room read that playlist. It must be one you made "
                                   "(or collaborate on), with the Spotify account this app is signed in to.")
            return out, name, f"Spotify said: {(d or {}).get('error') or 'no answer'}"
        for it in d.get("items") or []:
            x = (it or {}).get("item") or (it or {}).get("track")
            if isinstance(x, dict) and x.get("type", "track") == "track" and SID.match(str(x.get("id") or "")):
                out.append(x)
        got = len(d.get("items") or [])
        if not d.get("next") or not got:
            return out, name, ""
        offset += got
        if offset > 10000:
            return out, name, ""


def album_tracks(sp, album_id):
    out, offset = [], 0
    while True:
        d = sp._api_get(f"/albums/{album_id}/tracks", {"limit": 50, "offset": offset})
        if not isinstance(d, dict) or d.get("error"):
            return None
        out += [x for x in (d.get("items") or []) if isinstance(x, dict) and SID.match(str(x.get("id") or ""))]
        if not d.get("next"):
            return out
        offset += 50
        if offset > 1000:
            return out


def records_from(sp, tracks, known, progress=None):
    """The playlist's tracks → whole records to send (only ones the server
    hasn't got). An album or single comes whole; a track off a compilation
    comes alone."""
    recs, order = {}, []
    for x in tracks:
        alb = x.get("album") or {}
        if not SID.match(str(alb.get("id") or "")):
            continue
        comp = alb.get("album_type") == "compilation"
        key = f"{alb['id']}:{x['id']}" if comp else alb["id"]
        if key in known or key in recs:
            continue
        artists = _artists(x.get("artists")) if comp else (_artists(alb.get("artists")) or _artists(x.get("artists")))
        recs[key] = {"key": key, "name": alb.get("name") or "", "kind": "compilation" if comp else
                     ("single" if alb.get("album_type") == "single" else "album"),
                     "release_date": alb.get("release_date") or "", "image": _image(alb.get("images")),
                     "total_tracks": 1 if comp else (alb.get("total_tracks") or 1), "artists": artists,
                     "tracks": [_track(x)], "_album": None if comp else alb["id"]}
        order.append(key)
    for n, key in enumerate(order):
        if progress:
            progress(n, len(order))
        rec = recs[key]
        if rec["_album"]:
            whole = album_tracks(sp, rec["_album"])
            if whole:                              # (else: the playlist's own tracks of it, as they are)
                rec["tracks"] = [_track(t) for t in whole]
        rec.pop("_album", None)
    return [recs[k] for k in order]


def run_sync(quiet=False):
    """Read the playlist set on the master page, send its new records."""
    with _sync_lock:
        if _sync["running"]:
            return False
        _sync.update(running=True, step="looking", done=0, total=0, result=None, error="", at=time.time())
    try:
        info, code = _call("GET", "/api/master/sim")
        if code != 200:
            raise RuntimeError(info.get("error") or "only the master's app can bring records in")
        pid = (info.get("playlist") or {}).get("id")
        if not pid:
            raise RuntimeError("Set the playlist first.")
        sp = _D["spotify"]()
        if not sp.is_connected():
            raise RuntimeError("Sign this app in to Spotify first (Settings → Spotify), with the account that owns the playlist.")
        _sync["step"] = "reading the playlist"
        tracks, name, why = read_playlist(sp, pid)
        if why and not tracks:
            raise RuntimeError(why)
        _sync["step"] = "reading its records"
        recs = records_from(sp, tracks, set(info.get("record_keys") or []),
                            progress=lambda n, t: _sync.update(done=n, total=t))
        _sync["step"] = "sending them to the server"
        made = {"artists": 0, "records": 0, "tracks": 0, "covers": 0}
        batches = [recs[i:i + 10] for i in range(0, len(recs), 10)] or [[]]
        for i, chunk in enumerate(batches):
            last = i == len(batches) - 1
            d, c = _call("POST", "/api/master/sim/records",
                         {"records": chunk, "done": last, "name": name,
                          "note": why or f"{len(tracks)} tracks on the playlist"})
            if c != 200:
                raise RuntimeError(d.get("error") or "the server wouldn't take them")
            for k in made:
                made[k] += int(d.get(k) or 0)
        _sync["result"] = dict(made, playlist_tracks=len(tracks), name=name)
    except Exception as e:
        _sync["error"] = str(e)
        if not quiet:
            _call("POST", "/api/master/sim/sync-note", {"note": str(e)})
    finally:
        _sync["running"] = False
        _sync["step"] = ""
    return True


def _hourly():
    time.sleep(90)
    while True:
        try:
            if _D["is_gr"] and green_room.status().get("joined"):
                info, code = _call("GET", "/api/master/sim")
                if code == 200 and (info.get("playlist") or {}).get("id") and info.get("rules", {}).get("on"):
                    if _D["spotify"]().is_connected():
                        run_sync(quiet=True)
        except Exception:
            pass
        time.sleep(3600)


# ---------- routes ----------

def register(app, get_setting, set_setting, spotify, is_gr):
    _D.update(get_setting=get_setting, set_setting=set_setting, spotify=spotify, is_gr=is_gr)

    @app.route("/api/gr/sim/me")
    def api_gr_sim_me():
        d, code = me(fresh=request.args.get("fresh") == "1")
        return jsonify(d), code

    def act(what):
        d = request.get_json(silent=True) or {}
        body = {k: d[k] for k in ("track_id", "track_ids", "record") if k in d}
        out, code = _call("POST", f"/api/sim/{what}", body)
        _me_cache["at"] = 0.0
        return jsonify(out), code

    @app.route("/api/gr/sim/home", methods=["POST"])
    def api_gr_sim_home():
        return act("home")

    @app.route("/api/gr/sim/buy", methods=["POST"])
    def api_gr_sim_buy():
        return act("buy")

    @app.route("/api/gr/sim/out", methods=["POST"])
    def api_gr_sim_out():
        return act("out")

    @app.route("/api/gr/sim/mine")
    def api_gr_sim_mine():
        d, code = _call("GET", "/api/sim/mine")
        return jsonify(d), code

    @app.route("/api/gr/sim/record/<key>")
    def api_gr_sim_record(key):
        if not re.match(r"^[0-9A-Za-z:]{1,80}$", key):
            return jsonify({"error": "no such record"}), 404
        d, code = _call("GET", f"/api/sim/record/{key}")
        return jsonify(d), code

    @app.route("/api/gr/sim/played", methods=["POST"])
    def api_gr_sim_played():
        d = request.get_json(silent=True) or {}
        try:
            green_room.track("sim_play", {"track_id": int(d.get("track_id") or 0),
                                          "via": str(d.get("via") or "")[:20]})
        except Exception:
            pass
        return jsonify({"ok": True})

    @app.route("/api/gr/sim/sync", methods=["GET", "POST"])
    def api_gr_sim_sync():
        if request.method == "POST":
            if not _sync["running"]:
                threading.Thread(target=run_sync, daemon=True).start()
                time.sleep(0.05)
        return jsonify({k: _sync[k] for k in ("running", "step", "done", "total", "result", "error", "at")})

    @app.route("/api/gr/sim-csv/<what>")
    def api_gr_sim_csv(what):
        """The ledger / the activity as a spreadsheet, for the master."""
        if what not in ("ledger", "activity"):
            return jsonify({"error": "no such table"}), 404
        try:
            r = green_room.master_csv(what)
        except green_room.GRError as e:
            return jsonify({"error": str(e)}), 502
        if r.status_code != 200:
            return Response(r.content, status=r.status_code, mimetype="application/json")
        return Response(r.content, mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=music-room-{what}.csv"})

    if is_gr:
        threading.Thread(target=_hourly, daemon=True, name="sim-playlist").start()
