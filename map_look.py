"""
map_look.py — how the listener has dressed the Map in Explore.

The Map of Ireland and Britain (static/js/explore_map.js) can wear different
SKINS — Daithí, 2026-11-16: "the user should be able to have different
skins/themes for the ireland uk map too". The skins themselves are drawn by
the page. This file keeps the CHOICE:

    skin     which skin is on: one of the page's own ("page", "paper", "ink",
             "land", "sea", "dots", "ruled", "chart", "blueprint") or "own"
    own      the listener's own skin, if they made one: four colours and how
             the land is filled — {sea, land, line, text, fill}
    up       which way is up: 1 north, -1 south
    towns    town names shown
    rivers   rivers drawn

It is kept in the app's settings (key "map_look"), not only by the page: the
desktop window forgets what a page stores each time it is closed (the same
reason the theme is kept there — static/js/theme.js). The pages that hold a
map write it in before the map's script: `window.MR_MAP_LOOK = {{ map_look()|tojson }}`.

    GET  /api/isles/look     → the look, or {} when none was ever chosen
    POST /api/isles/look     any of the five keys → the whole look as kept

Nothing gets in that isn't one of those: a skin's name is a short slug, a
colour is #rrggbb, a fill is one of three words.
"""

import json
import re

KEY = "map_look"
FILLS = ("flat", "dots", "lines")
OWN_PARTS = ("sea", "land", "line", "text")
_SKIN = re.compile(r"^[a-z][a-z0-9-]{0,23}$")
_HEX = re.compile(r"^#[0-9a-f]{6}$")


def clean_own(o):
    """The listener's own skin → {sea, land, line, text, fill}, or None when it
    isn't whole (a skin with a colour missing can't be drawn)."""
    if not isinstance(o, dict):
        return None
    out = {}
    for k in OWN_PARTS:
        v = str(o.get(k) or "").strip().lower()
        if not _HEX.match(v):
            return None
        out[k] = v
    out["fill"] = o.get("fill") if o.get("fill") in FILLS else "flat"
    return out


def clean(obj, base=None):
    """What a page sent, laid over what was kept → the look to keep. Keys that
    are missing or make no sense leave what was there."""
    out = dict(base or {})
    if not isinstance(obj, dict):
        return out
    skin = obj.get("skin")
    if isinstance(skin, str) and _SKIN.match(skin):
        out["skin"] = skin
    if "own" in obj:
        own = clean_own(obj.get("own"))
        if own:
            out["own"] = own
        elif obj.get("own") is None:
            out.pop("own", None)
    if obj.get("up") in (1, -1):
        out["up"] = obj["up"]
    for k in ("towns", "rivers"):
        if isinstance(obj.get(k), bool):
            out[k] = obj[k]
    if out.get("skin") == "own" and not out.get("own"):     # "your own" with nothing in it is no skin
        out.pop("skin")
    return out


def read(get_setting):
    """The look as kept ({} when none was ever chosen: the page's own memory,
    and then the plain map, stand in)."""
    try:
        kept = json.loads(get_setting(KEY, "") or "{}")
    except (TypeError, ValueError):
        kept = {}
    return clean(kept)


def register(app, get_setting, set_setting, track=None):
    from flask import jsonify, request

    @app.route("/api/isles/look")
    def api_isles_look():
        return jsonify(read(get_setting))

    @app.route("/api/isles/look", methods=["POST"])
    def api_isles_look_set():
        was = read(get_setting)
        now = clean(request.get_json(silent=True) or {}, was)
        if now != was:
            set_setting(KEY, json.dumps(now, sort_keys=True))
            if track and now.get("skin") != was.get("skin"):
                try:
                    track("map_skin", {"id": now.get("skin") or "page"})
                except Exception:
                    pass
        return jsonify(now)

    # the pages that hold a map write the look in themselves, so it is there before the map draws
    app.jinja_env.globals["map_look"] = lambda: read(get_setting)
