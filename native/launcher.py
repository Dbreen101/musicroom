"""
Music Room — native macOS app launcher.

This is the entry point inside the .app bundle. The whole Music Room source
is bundled alongside it (read-only), and the user's data lives in a writable
per-user folder, so the app is fully self-contained and distributable.

Three responsibilities:

  1. Wire up paths — find the bundled source, pick the writable data dir,
     put both on sys.path / env so app.py, importer.py, migrate.py etc. all
     agree on where things are.

  2. Worker mode — when the running app needs to import or analyse music it
     re-invokes its OWN executable with a `--mr-worker` flag (there's no venv
     inside the bundle to run importer.py the old way). We catch that here and
     dispatch into importer.main().

  3. GUI mode — make sure the database exists and is migrated, start Flask on
     a background thread, and open a native pywebview window pointed at it.

In development (not frozen) this still works: it falls back to the project
folder for both code and data, so `python native/launcher.py` behaves like
the old desktop.py.
"""
import logging
import os
import socket
import sys
import threading
import time
import urllib.request


# --- belt-and-braces so PyInstaller sees the indirect imports ---------------
if False:                                            # pragma: no cover
    import flask, jinja2, werkzeug                       # noqa
    import mutagen, librosa, numpy, scipy, soundfile, audioread  # noqa
    import pygame                                         # noqa
    from PIL import Image                                 # noqa
    import webview                                        # noqa


# Folder name must match mr_paths.DRIVE_APPDATA_FOLDER and app.py's backup.
_DRIVE_APPDATA_FOLDER = "Music Room — App Data"

def _find_drive_appdata():
    """A portable Music Room DB on a mounted drive, or None. Inlined here (not
    imported from mr_paths) so the env is set BEFORE mr_paths first resolves."""
    try:
        from pathlib import Path
        for vol in Path("/Volumes").iterdir():
            cand = vol / _DRIVE_APPDATA_FOLDER
            if (cand / "library.db").is_file():
                return str(cand)
    except OSError:
        pass
    return None


BAKED_KEYS = ("MR_FEEDBACK_ENDPOINT", "MR_FEEDBACK_SECRET",
              # a Green Room build: the trial switched on, its server's address, its own data folder
              "MR_GREEN_ROOM", "MR_GR_VERSION", "MR_GR_SERVER", "MR_DATA_NAME")


def _app_data(name):
    """Where the ready-made app keeps its data: ~/Library/Application Support/<name>
    on a Mac, %APPDATA%\\<name> on Windows."""
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming"), name)
    return os.path.expanduser(os.path.join("~/Library/Application Support", name))


def _bake(code_dir):
    """A build can carry settings baked in: the spec bundles native/baked_env.py
    (or MR_BAKED_ENV, e.g. native/baked_env_gr.py) into mrsrc. They are defaults:
    the environment still wins. Absent (dev) → nothing changes."""
    try:
        if code_dir not in sys.path:
            sys.path.insert(0, code_dir)
        import baked_env
        for k in BAKED_KEYS:
            v = getattr(baked_env, k, "")
            if v:
                os.environ.setdefault(k, v)
    except ImportError:
        pass


def _setup_paths():
    """Locate bundled source + writable data dir; wire sys.path + env.
    Returns (code_dir, data_dir). Idempotent."""
    frozen = getattr(sys, "frozen", False)
    if frozen:
        code_dir = os.path.join(sys._MEIPASS, "mrsrc")          # bundled source
        _bake(code_dir)
        data_dir = os.environ.get("MUSICROOM_DATA")
        own_name = os.environ.get("MR_DATA_NAME")               # a build with its own data folder (the Green Room's)
        if not data_dir and own_name:
            data_dir = _app_data(own_name)
        if not data_dir:
            data_dir = _app_data("Music Room")
            # Portable drive: if this Mac has no library yet but a Music Room
            # drive is plugged in (carrying 'Music Room — App Data/library.db'),
            # adopt the drive's data so the whole library is there. Inlined (no
            # mr_paths import) so MUSICROOM_DATA is set before mr_paths resolves.
            if not os.path.isfile(os.path.join(data_dir, "library.db")):
                drive = _find_drive_appdata()
                if drive:
                    data_dir = drive
    else:
        # dev: launcher lives in native/, source is the parent folder
        here = os.path.dirname(os.path.abspath(__file__))
        code_dir = os.environ.get("MUSICROOM_HOME") or os.path.dirname(here)
        data_dir = os.environ.get("MUSICROOM_DATA") or code_dir

    # The shipped app IS Prototype 1 (the 3D build). Without this the bundle
    # serves the legacy 2D forest and tools full-navigate away from the room.
    # setdefault so MUSICROOM_3D=0 in the environment can still force 2D.
    os.environ.setdefault("MUSICROOM_3D", "1")

    _bake(code_dir)

    os.environ["MUSICROOM_DATA"] = data_dir
    os.makedirs(data_dir, exist_ok=True)
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    try:
        os.chdir(code_dir)
    except Exception:
        pass
    return code_dir, data_dir


def _run_worker():
    """Frozen exe re-invoked as `--mr-worker <importer args>`. Dispatch into
    the importer inside the same bundled environment.

    IMPORTANT: end with os._exit(), never a normal return. librosa's stack
    spawns a multiprocessing resource_tracker child inside the frozen bundle,
    and interpreter finalization then blocks forever in os.waitpid on it
    (seen on the Intel/Rosetta build: the import finished all its work but
    the worker never exited, so the app showed 'importing…' forever). All
    real work is committed to the DB before main() returns — skipping
    finalization loses nothing."""
    # The worker must be INVISIBLE. macOS registers the re-invoked bundle exe
    # as a second full "Music Room" (Dock icon + App Switcher entry) — a
    # tester saw "another app opened", closed it, and killed his own import
    # (day one of testing, 2026-07-13). Activation policy 'prohibited' =
    # background process: no Dock icon, no window, nothing to close.
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(2)  # NSApplicationActivationPolicyProhibited
    except Exception:
        pass
    _setup_paths()
    args = [a for a in sys.argv[1:] if a != "--mr-worker"]
    import importer
    code = 0
    try:
        importer.main(args)
    except SystemExit as e:                     # argparse / explicit exits
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def _ensure_database():
    """Create the schema on a fresh install, then run (idempotent) migrations.
    Uses the data dir's DB_PATH via mr_paths."""
    import mr_paths
    if not os.path.exists(mr_paths.DB_PATH):
        import schema
        schema.create_database()
    import migrate
    migrate.run_migration()


def _bail(msg: str):
    sys.stderr.write(f"Music Room: {msg}\n")
    try:
        import webview
        webview.create_window(
            "Music Room",
            html=("<style>body{font-family:-apple-system,Helvetica,sans-serif;"
                  "padding:40px;background:#e7d9ba;color:#2e2718;}"
                  "h1{font-family:Georgia,serif;font-style:italic;}"
                  "code{background:#d8c187;padding:1px 5px;border-radius:4px;}</style>"
                  f"<h1>Music Room couldn't start</h1><p>{msg}</p>"),
            width=640, height=380,
        )
        webview.start()
    except Exception:
        pass
    sys.exit(1)


def _free_port(preferred: int) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
            return preferred
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def _run_bt_connect():
    """Frozen exe re-invoked as `--mr-bt-connect <address>` by the deck's
    speaker list (sound_out.py): connect one paired Bluetooth speaker and
    exit. Its own process on purpose — macOS asks permission for Bluetooth,
    and that question must never be able to stop the app itself. Invisible,
    like the import worker; ends with os._exit()."""
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(2)  # no Dock icon, no window
    except Exception:
        pass
    code = 5
    try:
        _setup_paths()
        import sound_out
        i = sys.argv.index("--mr-bt-connect")
        code = sound_out._bt_connect_main(sys.argv[i + 1] if len(sys.argv) > i + 1 else "")
    except Exception:
        pass
    os._exit(code)


def main():
    # Windows: a helper process (the analysis libraries start some) runs this same
    # program again — without this it would open a second Music Room.
    import multiprocessing
    multiprocessing.freeze_support()
    # Worker mode short-circuits everything else.
    if "--mr-worker" in sys.argv:
        _run_worker()
        return
    if "--mr-bt-connect" in sys.argv:
        _run_bt_connect()
        return

    code_dir, data_dir = _setup_paths()
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    if not os.path.isfile(os.path.join(code_dir, "app.py")):
        _bail(f"Bundled source not found (looked in <code>{code_dir}</code>).")

    # Fresh install → build schema; always run migrations (safe, idempotent).
    try:
        _ensure_database()
    except Exception as e:
        _bail(f"Couldn't set up the database: {e!r}")

    try:
        from app import app, backup_to_drive
    except Exception as e:
        _bail(f"Couldn't load Music Room: {e!r}")

    # The launch backup (DATA_DIR → laptop backup + the drive's portable
    # "Music Room — App Data" in external mode) fired only under `python
    # app.py` — the bundle bypassed __main__, so testers never got it.
    try:
        backup_to_drive(block=False)
    except Exception:
        pass

    port = _free_port(int(os.environ.get("MUSICROOM_PORT", "5177")))
    url  = f"http://127.0.0.1:{port}"

    def _serve():
        app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)

    threading.Thread(target=_serve, daemon=True).start()

    if not _wait_for(url):
        _bail("The Music Room server didn't come up in time.")

    # Harness mode: MUSICROOM_HEADLESS=1 serves WITHOUT opening a window (and
    # without a Dock icon) — the automated pre-flight sweep boots the real
    # bundle on David's machine, and its windows popping up were being closed
    # by hand, which read as crashes (2026-07-14). Normal launches unaffected.
    if os.environ.get("MUSICROOM_HEADLESS") == "1":
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().setActivationPolicy_(2)  # prohibited
        except Exception:
            pass
        while True:
            time.sleep(3600)

    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(0)
    except Exception:
        pass

    _patch_mic_permission()

    import webview
    webview.create_window(
        "Music Room",
        url + "/room",                 # open straight into the 3D Music Room
        width=1400, height=900,
        min_size=(900, 600),
    )
    if sys.platform.startswith("win"):
        # Windows: the window is Microsoft Edge's (WebView2 — on every Windows 11, and on
        # Windows 10 with Edge kept up to date). Where it is missing, the Music Room
        # opens in the computer's own browser instead, and keeps running until closed
        # from the taskbar's hidden icons… or the window below.
        try:
            webview.start(gui="edgechromium")
        except Exception:
            import webbrowser
            webbrowser.open(url + "/room")
            _hold_open_without_window(url)
    else:
        webview.start()
    # Quit = quit. Same finalization hang risk as the worker (multiprocessing
    # resource_tracker spawned inside the frozen bundle blocks Py_FinalizeEx
    # in waitpid) — the window would close but the process linger, holding the
    # port + DB so the next launch misbehaves. Nothing needs a graceful exit
    # here: SQLite commits per request, the queue file persists on change.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def _hold_open_without_window(url):
    """Windows without Edge's WebView2: the app runs in the browser. A small
    window says so and quitting it quits the Music Room (tkinter comes with Python)."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("Music Room")
        root.geometry("420x150")
        tk.Label(root, text="The Music Room is open in your browser.\n\n" + url + "/room\n\n"
                 "Close this window to quit it.", justify="center", padx=20, pady=20).pack()
        root.mainloop()
    except Exception:
        while True:
            time.sleep(3600)


def _patch_mic_permission():
    """Enable microphone access in the WKWebView window (same patch as
    desktop.py — voice notes / set recording say "mic unavailable" without it):
    1. WKWebView blocks navigator.mediaDevices on HTTP origins, even
       localhost — 'allowMediaCaptureFromInsecureURLs' lifts that.
    2. pywebview's BrowserDelegate doesn't implement the WKUIDelegate
       media-capture permission callback, so prompts are silently denied —
       add the method and grant.
    """
    try:
        import objc
        from webview.platforms.cocoa import BrowserView

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

        def _grant_media(self, wv, origin, frame, kind, handler):
            handler(1)  # WKPermissionDecisionGrant

        BrowserView.BrowserDelegate \
            .webView_requestMediaCapturePermissionForOrigin_initiatedByFrame_type_decisionHandler_ = \
            objc.selector(_grant_media, signature=b'v@:@@@Q@?')
    except Exception:
        pass  # non-macOS or API changed — fail silently


if __name__ == "__main__":
    main()
