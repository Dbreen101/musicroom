"""
=============================================================
MUSIC ROOM — desktop.py
=============================================================
Runs Music Room as a native macOS window instead of in Chrome.

What this does:
    1. Starts the Flask server in a background thread.
    2. Waits until it's reachable on http://127.0.0.1:5000.
    3. Opens a pywebview window pointed at the local server.

The window uses the system WebKit — no browser chrome, no tabs,
no URL bar. Resize like any Mac window. Right-click → Inspect
Element for DevTools while building.

How to run:
    source venv/bin/activate
    python3 desktop.py

For zero-friction launch, double-click "Music Room.command"
on the Desktop. That handles the venv activation for you.
=============================================================
"""

import os
import sys
import time
import socket
import threading
import urllib.request
import logging

# Silence the Flask request log inside the window — we don't
# want noisy console output flying past during normal use.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

import webview
from app import app, backup_to_drive

# The launch backup fired only under `python app.py` — the desktop shell
# bypassed __main__, so daily use never took one. (Same fix as the native
# launcher.)
try:
    backup_to_drive(block=False)
except Exception:
    pass

# Set the macOS application name so the menu bar shows "Music Room"
# instead of "Python". This only works when running from the .app bundle
# or when pyobjc is available — silently ignored otherwise.
try:
    from AppKit import NSApplication, NSBundle
    _app = NSApplication.sharedApplication()
    _bundle = NSBundle.mainBundle()
    if _bundle.bundleIdentifier() == 'org.python.python':
        # Running as bare python, not from a signed .app — patch the display name
        _app.setName_("Music Room")
except Exception:
    pass

HOST = "127.0.0.1"
# 5000 is grabbed by macOS AirPlay Receiver (Control Center) on Monterey+.
# MUSICROOM_PORT lets the 3D-only instance (start3d.sh) run alongside the
# regular app on its own port.
PORT = int(os.environ.get("MUSICROOM_PORT", "5177"))
IS_3D = os.environ.get("MUSICROOM_3D") == "1"
URL  = f"http://{HOST}:{PORT}/room"   # open straight into the 3D Music Room
# MR_GR_VERSION names a residency build ("GR1", see startgr.sh) — the window
# still just says Music Room: the trial should feel like the real thing.
_GR = os.environ.get("MR_GR_VERSION", "").strip()
TITLE = "Music Room" if _GR else ("Music Room 3D" if IS_3D else "Music Room")


def _port_open(host, port):
    """True if something is already listening on that port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _run_flask():
    """Run the Flask app in the current thread."""
    # use_reloader=False is required when Flask runs inside another thread.
    # threaded=True lets multiple requests overlap (audio + API at once).
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def _wait_for_server(timeout=10):
    """Block until Flask answers, or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=0.5).read(1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def _patch_mic_permission():
    """Enable microphone access in the WKWebView window.

    Two things need patching:
    1. WKWebView blocks navigator.mediaDevices on HTTP origins (even localhost).
       Setting 'allowMediaCaptureFromInsecureURLs' lifts that restriction.
    2. pywebview's BrowserDelegate doesn't implement the WKUIDelegate media-capture
       permission callback, so permission prompts are silently denied.
       We add the method to automatically grant permission.
    """
    try:
        import objc
        from webview.platforms.cocoa import BrowserView

        # 1. Patch __init__ to allow getUserMedia on HTTP localhost
        _orig_init = BrowserView.__init__

        def _patched_init(self, window):
            _orig_init(self, window)
            try:
                self.webview.configuration().preferences().setValue_forKey_(
                    True, 'allowMediaCaptureFromInsecureURLs'
                )
            except Exception:
                pass

        BrowserView.__init__ = _patched_init

        # 2. Add the WKUIDelegate media permission grant method
        def _grant_media(self, wv, origin, frame, kind, handler):
            handler(1)  # WKPermissionDecisionGrant = 1

        BrowserView.BrowserDelegate \
            .webView_requestMediaCapturePermissionForOrigin_initiatedByFrame_type_decisionHandler_ = \
            objc.selector(_grant_media, signature=b'v@:@@@Q@?')
    except Exception:
        pass  # non-macOS or API changed — fail silently


def main():
    # If something's already on :5000, assume an existing dev server
    # is up — open the window pointed at it instead of double-starting.
    if not _port_open(HOST, PORT):
        threading.Thread(target=_run_flask, daemon=True).start()
        if not _wait_for_server():
            print("Music Room: server didn't come up in 10s, aborting.")
            sys.exit(1)

    _patch_mic_permission()

    # Native macOS window. min_size keeps the layout sensible.
    webview.create_window(
        title=TITLE,
        url=URL,
        width=1400,
        height=900,
        min_size=(900, 600),
        background_color="#080c09",   # match the forest --bg
    )
    # GUI defaults to system WebKit on macOS — no extra config needed.
    webview.start(debug=False)


if __name__ == "__main__":
    main()
