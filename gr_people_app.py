"""
gr_people_app.py — the app's side of accounts (gr_signin.py, gr_apply.py,
gr_happenings.py and gr_behalf.py on the rooms server; 2026-11-26).

    /account                     the page: sign-in (email, password, two-factor, laptops),
                                 the kind of account, who manages it
    /apply                       applying for an artist / label / venue… account
    /api/gr/login                sign this laptop in with an email and a password
    /api/gr/people/<what>        the page's questions, passed on to the server — only the
                                 ones listed in _SUB, each with the method it takes
    /api/gr/acting               whose account this app is managing (GET) · switch (POST)
    /api/gr/whats-new            what to tell a person the first time they open a new version

A password typed into one of these pages goes from the page to this app (on the same
computer) and from the app to the server, and only over https or to a server on this
computer. It is never written to this laptop: what the app keeps is the sign-in the
server hands back.
"""

import json
import os
import re
from contextlib import closing

from flask import jsonify, render_template, request

import green_room

_SUB = re.compile(r"^(me/security|me/email|me/password|me/devices/\d+/out|me/2fa/(start|confirm|off)"
                  r"|me/email/verify(/confirm)?|me/interest|apply(/withdraw)?"
                  r"|my/happenings(/\d+)?|my/behalf(/\d+)?|happenings)$")
_WITH_PASSWORD = ("me/password", "me/email")


def whats_new(base_dir, version, seen):
    """The notes for this version, if the person has not been shown them: the entry
    of static/data/whats_new.json whose "version" is the app's own. A new install
    (nothing seen yet) is shown nothing: it has only ever known this version."""
    if not version or not seen or seen == version:
        return None
    try:
        with open(os.path.join(base_dir, "static", "data", "whats_new.json"), encoding="utf-8") as f:
            notes = json.load(f).get("notes") or []
    except (OSError, ValueError):
        return None
    hit = next((n for n in notes if isinstance(n, dict) and n.get("version") == version and n.get("title")), None)
    if not hit:
        return None
    return {"version": version, "title": str(hit["title"])[:120], "words": [str(w)[:600] for w in (hit.get("words") or [])][:6],
            "go": str(hit.get("go") or "")[:200] if str(hit.get("go") or "").startswith("/") else "",
            "go_label": str(hit.get("go_label") or "Show me")[:40]}


def register(app, get_setting, set_setting, app_version, base_dir):

    def guard(fn):
        try:
            return jsonify(fn())
        except green_room.GRError as e:
            more = {k: True for k in ("need_code", "need_2fa", "need_email_code", "need_password", "has_password",
                                      "devices_full") if getattr(e, k, False)}
            return jsonify(dict({"error": str(e)}, **more)), 502
        except OSError as e:
            print(f"[accounts] {type(e).__name__}: {e}")
            return jsonify({"error": "That was interrupted. Try again."}), 502

    @app.route("/account")
    def account_page():
        return render_template("account.html")

    @app.route("/apply")
    def apply_page():
        return render_template("apply.html")

    @app.route("/api/gr/login", methods=["POST"])
    def api_gr_login():
        d = request.get_json(silent=True) or {}
        if d.get("invite_code"):       # an account from before passwords: its account code
            return guard(lambda: green_room.join(d.get("server_url") or "", d.get("invite_code") or "",
                                                 d.get("device_name") or "", otp=d.get("otp") or ""))
        return guard(lambda: green_room.login(d.get("server_url") or "", d.get("email") or "", d.get("password") or "",
                                              d.get("device_name") or "", otp=d.get("otp") or "",
                                              email_code=d.get("email_code") or ""))

    @app.route("/api/gr/people/<path:sub>", methods=["GET", "POST", "DELETE"])
    def api_gr_people(sub):
        if not _SUB.match(sub):
            return jsonify({"error": "no such thing"}), 404
        body = request.get_json(silent=True) or {}
        if sub in _WITH_PASSWORD and request.method == "POST":
            with closing(green_room._db()) as conn:
                if not green_room._safe_for_a_password(green_room._server_url(conn)):
                    return jsonify({"error": green_room.PLAIN_ADDRESS}), 400
        try:
            if request.method == "GET":
                code, d = green_room.shop_call("GET", "/api/" + sub, params=dict(request.args))
            else:
                code, d = green_room.shop_call(request.method, "/api/" + sub, body)
        except green_room.GRError as e:
            return jsonify({"error": str(e)}), 502
        if sub.endswith("/out") and code == 200 and d.get("self"):
            for k in ("gr_token", "gr_name"):        # this laptop signed itself out
                set_setting(k, "")
        return jsonify(d), code

    @app.route("/api/gr/acting", methods=["GET", "POST"])
    def api_gr_acting():
        if request.method == "POST":
            d = request.get_json(silent=True) or {}
            return guard(lambda: {"acting": green_room.act_for(d.get("handle") or "")})
        return jsonify({"acting": green_room.acting_for()})

    @app.route("/api/gr/whats-new", methods=["GET", "POST"])
    def api_gr_whats_new():
        """GET: the notes for this version, once. POST: they have been read."""
        seen = get_setting("whats_new_seen", "")
        if request.method == "POST" or not seen:
            set_setting("whats_new_seen", app_version or "")
            return jsonify({"note": None})
        return jsonify({"note": whats_new(base_dir, app_version, seen)})
