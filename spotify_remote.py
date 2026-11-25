"""
spotify_remote.py — the listener's own Spotify, driven from the deck.

Spotify lets a signed-in Premium listener's apps be remote-controlled: "play
this track on that device", pause, skip, seek, volume, and "what is playing".
The Music Room uses that so a Spotify record in the cue plays as a WHOLE track
in the listener's own Spotify (the desktop app, or Spotify open in a browser),
while the deck stays the one set of buttons. No audio passes through the
Music Room — Spotify plays it, we only tell it what and when.

This file is the thin layer between the deck (seinnteoir_player.py, which owns
the timing and the cue) and the Spotify calls (spotify.py). It knows nothing
about the cue.

When it can't be used — not signed in, signed in before the playback
permission was asked for, no Premium, Spotify not open and not installed —
`can_take()` / `play()` say so and the deck falls back to Spotify's player in
the page (snt_embed.js), which needs none of that but plays 30-second previews
to a listener who isn't signed in inside it.

Spotify's rules for this (developer policy, read 2026-11-14) are in CLAUDE.md:
in short, fine for a private test, not allowed in a product that sells things.
"""

import re
import os
import socket
import subprocess
import sys
import time

_LINK = re.compile(r"open\.spotify\.com/(?:intl-[a-z-]+/)?(track|episode|album|playlist|artist|show)/([A-Za-z0-9]+)")
_OK = (200, 202, 204)


def uri_of(url):
    """A Spotify link → ('one' | 'many', 'spotify:<kind>:<id>'), or (None, None).
    'one' = a single track or episode; 'many' = something that plays on through
    its own tracks (an album, a playlist, an artist, a show)."""
    m = _LINK.search(url or "")
    if not m:
        return None, None
    kind, ident = m.group(1), m.group(2)
    return ("one" if kind in ("track", "episode") else "many"), f"spotify:{kind}:{ident}"


def _launch_spotify_app():
    """Open the Spotify desktop app quietly (behind, hidden) so it can be told
    to play. True when the system found and opened it. On Windows it is asked
    for by its own address (spotify:), which the Spotify app registers."""
    if sys.platform.startswith("win"):
        try:
            os.startfile("spotify:")
            return True
        except OSError:
            return False
    if sys.platform != "darwin":
        return False
    try:
        r = subprocess.run(["open", "-g", "-j", "-a", "Spotify"], capture_output=True, timeout=6)
        return r.returncode == 0
    except Exception:
        return False


def show_app(url="", _run=subprocess.run):
    """Bring the listener's Spotify to the front — what the Spotify mark on the
    deck does. Nothing is played, paused or skipped by it. → 'app' when the
    desktop app came forward; 'web' when there is no app on this computer and
    the record's own page was opened in the browser instead; '' when neither
    could be done."""
    if sys.platform == "darwin":
        try:
            if _run(["open", "-a", "Spotify"], capture_output=True, timeout=6).returncode == 0:
                return "app"
        except Exception:
            pass
    elif sys.platform.startswith("win"):
        try:
            os.startfile("spotify:")
            return "app"
        except OSError:
            pass
    url = (url or "").strip()
    if url.startswith("https://") and _LINK.search(url):
        try:
            if sys.platform == "darwin":
                if _run(["open", url], capture_output=True, timeout=6).returncode == 0:
                    return "web"
            else:
                import webbrowser
                if webbrowser.open(url):
                    return "web"
        except Exception:
            pass
    return ""


def spotify_app_here():
    """Is the Spotify app on this computer? True / False, or None when that can't be told."""
    if sys.platform == "darwin":
        if any(os.path.isdir(p) for p in ("/Applications/Spotify.app", os.path.expanduser("~/Applications/Spotify.app"))):
            return True
        try:
            r = subprocess.run(["/usr/bin/mdfind", "kMDItemCFBundleIdentifier == 'com.spotify.client'"],
                               capture_output=True, text=True, timeout=6)
            return bool(r.stdout.strip())
        except Exception:
            return None
    return None


def _this_computer():
    """Names Spotify is likely to know this computer by (its device name is
    the computer's name unless the listener changed it)."""
    names = set()
    try:
        names.add(socket.gethostname().split(".")[0].lower())
    except Exception:
        pass
    if os.environ.get("COMPUTERNAME"):                 # Windows
        names.add(os.environ["COMPUTERNAME"].lower())
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, timeout=3, text=True)
            if r.returncode == 0 and r.stdout.strip():
                names.add(r.stdout.strip().lower())
        except Exception:
            pass
    return {n for n in names if n}


class SpotifyRemote:
    def __init__(self, get_client, launcher=_launch_spotify_app, sleep=time.sleep, local_names=None):
        self._get = get_client          # () → spotify.SpotifyClient
        self._launch = launcher
        self._sleep = sleep
        self._local = local_names       # found on first use (a subprocess call)
        self.device_id = None           # the Spotify WE play on: one on this computer
        self.device_name = ""
        self.supports_volume = True
        self._flags = (0.0, False, False)   # (asked at, can control, can see)

    # ── what the sign-in allows (asked of the settings at most every few seconds) ──
    def _allowed(self):
        at, ctl, see = self._flags
        if time.time() - at > 4.0:
            try:
                c = self._get()
                ctl, see = bool(c.can_control()), bool(c.can_see_playing())
            except Exception:
                ctl = see = False
            self._flags = (time.time(), ctl, see)
        return ctl, see

    def forget(self):
        """The sign-in changed — ask again next time."""
        self._flags = (0.0, False, False)

    def ready(self):
        return self._allowed()[0]

    def can_see(self):
        return self._allowed()[1]

    def can_take(self, item):
        return bool(item and item.get("kind") == "embed" and item.get("source") == "spotify"
                    and uri_of(item.get("url"))[1] and self.ready())

    # ── devices ──
    # A record played from the deck should sound from THIS computer — not from
    # the listener's phone because that happened to be the last Spotify they
    # used. So only a computer is ever chosen: the one with this computer's
    # name first, then any other open Spotify on a computer.
    def _pick_device(self, c):
        if self._local is None:
            self._local = _this_computer()
        devs = [d for d in c.player_devices()
                if d.get("id") and not d.get("is_restricted") and d.get("type") == "Computer"]
        if not devs:
            return None
        devs.sort(key=lambda d: ((d.get("name") or "").lower() not in self._local, not d.get("is_active")))
        return devs[0]

    def _find_device(self, c):
        """An open Spotify on a computer — opening the app if there is none."""
        dev = self._pick_device(c)
        if not dev and self._launch and self._launch():
            for _ in range(10):
                self._sleep(1.0)
                dev = self._pick_device(c)
                if dev:
                    break
        return dev

    def _remember(self, dev):
        if dev:
            self.device_id = dev.get("id") or self.device_id
            self.device_name = dev.get("name") or self.device_name
            self.supports_volume = bool(dev.get("supports_volume", True))

    def _reason(self, c, status, data):
        why = c._why(data).upper() if hasattr(c, "_why") else ""
        if status == 0:
            return "network"
        if status == 401:
            return "signin"
        if status == 429:
            return "busy"
        if status == 403 and "REGISTER" in why:            # "User not registered in the Developer Dashboard"
            return "unlisted"
        if status == 403 and "PREMIUM" in why:
            try:
                from spotify import KEY_NO_PREMIUM
                c.s.set(KEY_NO_PREMIUM, "1")        # don't keep asking: Spotify only lets Premium do this
            except Exception:
                pass
            self.forget()
            return "premium"
        if status == 404 or "DEVICE" in why:
            return "no_device"
        return "refused"

    def _why_no_device(self, c):
        """No Spotify to play on. Usually none is open — but a listener the key's owner has not
        listed, or one without Premium, gets the same empty answer: ask Spotify which it is."""
        try:
            step = c.checkup().get("step") if hasattr(c, "checkup") else ""
        except Exception:
            step = ""
        return {"unlisted": "unlisted", "free": "premium", "signed_out": "signin", "reconnect": "signin"}.get(step, "no_device")

    # ── the commands ──
    def play(self, item, position_sec=0.0):
        """Start this record in the listener's Spotify, on this computer →
        (ok, why). why: '' · no_device · premium · unlisted · signin · network · busy · refused"""
        c = self._get()
        how, uri = uri_of(item.get("url"))
        if not uri:
            return False, "refused"
        kw = {"uris": [uri]} if how == "one" else {"context_uri": uri}
        if how == "one" and position_sec and position_sec > 0.5:
            kw["position_ms"] = int(position_sec * 1000)
        status, data = 404, {}
        if self.device_id:                                 # where we played last time
            status, data = c.player_play(device_id=self.device_id, **kw)
            if status in _OK:
                return True, ""
            why = self._reason(c, status, data)
            if why != "no_device":
                return False, why
            self.device_id = None                          # it has gone — look again
        dev = self._find_device(c)
        if not dev:
            return False, self._why_no_device(c)
        for attempt in range(3):                           # a just-opened app can take a moment to listen
            status, data = c.player_play(device_id=dev["id"], **kw)
            if status in _OK:
                self._remember(dev)
                return True, ""
            if status not in (404, 502, 503):
                break
            self._sleep(1.0)
        return False, self._reason(c, status, data)

    def pause(self):
        status, _ = self._get().player_pause()
        return status in _OK

    def resume(self):
        status, _ = self._get().player_play()
        return status in _OK

    def next(self):
        status, _ = self._get().player_next()
        return status in _OK

    def previous(self):
        status, _ = self._get().player_previous()
        return status in _OK

    def seek(self, sec):
        status, _ = self._get().player_seek(int(max(0.0, sec) * 1000))
        return status in _OK

    def volume(self, v):
        """v = 0..1, the deck's dial. Only ever sent when the listener moves
        the dial while a Spotify record is playing — never on its own, so a
        record never arrives louder than the listener left their Spotify."""
        if not self.supports_volume:
            return False
        status, _ = self._get().player_volume(max(0.0, min(1.0, float(v))) * 100)
        return status in _OK

    def state(self):
        """What the listener's Spotify is doing now.
        None = couldn't ask (no network, told to slow down, not signed in).
        Otherwise a dict; 'nothing' is True when Spotify has nothing loaded."""
        status, d = self._get().player_state()
        if status == 204:
            return {"playing": False, "nothing": True}
        if status != 200 or not isinstance(d, dict):
            return None
        item = d.get("item") or {}
        dev = d.get("device") or {}
        if dev.get("id") and dev.get("id") == self.device_id:
            self._remember(dev)                     # our own device: keep its name and abilities fresh
        artists = item.get("artists") or []
        images = (item.get("album") or {}).get("images") or item.get("images") or []
        return {
            "playing":     bool(d.get("is_playing")),
            "nothing":     not item,
            "uri":         item.get("uri") or "",
            "context_uri": (d.get("context") or {}).get("uri") or "",
            "position":    (d.get("progress_ms") or 0) / 1000.0,
            "duration":    (item.get("duration_ms") or 0) / 1000.0,
            "title":       item.get("name") or "",
            "artist":      ", ".join(a["name"] for a in artists if a.get("name")) or (item.get("show") or {}).get("name") or "",
            "artist_ids":  ",".join(a["id"] for a in artists if a.get("id")),
            "image_url":   (images[0].get("url") if images else "") or "",
            "url":         (item.get("external_urls") or {}).get("spotify") or "",
            "device":      dev.get("name") or "",
            "device_type": dev.get("type") or "",
            "kind":        d.get("currently_playing_type") or "track",
        }
