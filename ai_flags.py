"""
ai_flags.py — streams marked as AI-made are not played through the deck.

David, 2026-11-14: "flag AI streamed music and not allow it to be streamed
through the app … if you are able to do that then do it now."

Nothing here can HEAR whether a stream is AI-made: no stream audio ever
reaches the Music Room, and Spotify's rules forbid analysing its content
anyway. What can be done honestly is two things:

  1. A public, community-kept LIST of Spotify artist accounts known to put
     out AI-generated music (github.com/eye-wave/spotify-ai-blocklist — it
     gathers several such lists, Soul Over AI among them). A stream by an
     artist on it is marked "AI-made" and the deck will not cue it. The match
     is on Spotify's own artist ID — exact, never on a name — so a human
     artist is never caught for sharing a name with one. Most AI accounts are
     on no list: an unmarked stream is NOT thereby human.
  2. The listener's own marks (kept by the app, in settings): "AI-made" on
     any stream, keyed on who it is by, and "not AI" to lift a mark they think
     is wrong. app.py logs both as trial events, so the marks and disputes of
     the residency reach David.

The list is FETCHED by each copy into its own data folder and refreshed weekly
in the background — never bundled with the app (the source is GPL-3.0, parts
CC BY 4.0; the attribution is shown wherever a mark from it is shown).
"""

import os
import re
import threading
import time
import urllib.request

from mr_paths import DATA_DIR

LIST_URL  = "https://raw.githubusercontent.com/eye-wave/spotify-ai-blocklist/refs/heads/main/ai-list.txt"
LIST_NAME = "eye-wave/spotify-ai-blocklist"
LIST_PAGE = "https://github.com/eye-wave/spotify-ai-blocklist"
MAX_AGE_S = 7 * 24 * 3600
_FILE     = os.path.join(DATA_DIR, "ai_artists_spotify.txt")
_ID       = re.compile(r"open\.spotify\.com/artist/([A-Za-z0-9]{22})\b")

_lock     = threading.Lock()
_ids      = frozenset()
_mtime    = None          # the file's stamp when _ids was read
_fetching = False
_tried_at = 0.0           # the last attempt, so a failing fetch isn't retried every call


def _read():
    """The listed artist ids, re-read only when the file has changed."""
    global _ids, _mtime
    try:
        m = os.path.getmtime(_FILE)
    except OSError:
        _ids, _mtime = frozenset(), None
        return _ids
    if m != _mtime:
        try:
            with open(_FILE, encoding="utf-8", errors="ignore") as fh:
                _ids = frozenset(_ID.findall(fh.read()))
            _mtime = m
        except OSError:
            pass
    return _ids


def listed():
    with _lock:
        return _read()


def _fetch():
    global _fetching, _tried_at
    try:
        req = urllib.request.Request(LIST_URL, headers={"User-Agent": "MusicRoom/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            text = r.read(4_000_000).decode("utf-8", "ignore")
        if len(set(_ID.findall(text))) >= 200:      # a real list, not an error page
            tmp = _FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, _FILE)
            return True
    except Exception:
        pass
    finally:
        _fetching = False
        _tried_at = time.time()
    return False


def refresh(wait=False, force=False):
    """Fetch the list when this copy has none, or its copy is a week old.
    Never blocks unless asked (`wait`, used the very first time so the first
    Spotify link added is already checked). A failed fetch waits an hour."""
    global _fetching
    if not LIST_URL:
        return False
    with _lock:
        try:
            age = time.time() - os.path.getmtime(_FILE)
        except OSError:
            age = None
        due = force or age is None or age > MAX_AGE_S
        if not due or _fetching or (not force and time.time() - _tried_at < 3600):
            return False
        _fetching = True
    if wait:
        return _fetch()
    threading.Thread(target=_fetch, daemon=True, name="ai-list").start()
    return True


def status():
    ids = listed()
    try:
        at = os.path.getmtime(_FILE)
    except OSError:
        at = None
    return {"count": len(ids), "fetched_at": at, "source": LIST_NAME, "page": LIST_PAGE}


def keys_for(source, by_ids, url=""):
    """What a stream's marks hang on: who it is by, as the service names them
    ("spotify:<artist id>", "soundcloud:<uploader>"); a stream that names no
    one (a playlist) hangs on its own link."""
    ks = [f"{source}:{i.strip()}" for i in (by_ids or "").split(",") if i.strip()]
    return ks or ([f"link:{url}"] if url else [])


def verdict(source, by_ids, url="", marked=(), cleared=()):
    """None, or why this stream is treated as AI-made:
    'mine' — the listener marked it; 'list' — its artist is on the public list
    (and the listener hasn't lifted that)."""
    ks = keys_for(source, by_ids, url)
    if not ks:
        return None
    if any(k in marked for k in ks):
        return "mine"
    if source == "spotify":
        ids = listed()
        if any(k.startswith("spotify:") and k[8:] in ids and k not in cleared for k in ks):
            return "list"
    return None
