"""
Music Room — shared path resolver.

Single source of truth for WHERE things live, so the same code runs both:

  • in development  — `python app.py` / `./start.sh` from the project folder.
    Data lives right in the project dir, exactly as it always has. Nothing
    about the dev workflow changes.

  • as a bundled .app — distributed to other people. The code is read-only
    inside the bundle; user data must live in a writable per-user location.

Two distinct roots:

  CODE_DIR   where the source + templates + static assets live. Read-only
             when bundled. (app.py keeps using its own __file__ for this;
             this constant is provided for any module that wants it.)

  DATA_DIR   where the user's stuff is written: library.db, voice notes,
             recordings, exports, and uploaded media (moodboard / ambient /
             artwork / stickers / overlays under DATA_DIR/static/…).

Resolution order for DATA_DIR:
  1. $MUSICROOM_DATA            — explicit override (the bundle launcher sets
                                  this; power users can too).
  2. ~/Library/Application Support/Music Room   — when frozen (a real .app).
  3. the project folder          — in development (unchanged behaviour).
"""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running inside a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False))


# --- CODE_DIR: where this module (and the rest of the source) sits ---------
# In dev: the project folder. When frozen + imported from the unpacked source
# tree, this is that tree. (app.py still derives its own BASE_DIR from its own
# __file__, which is equivalent — kept for compatibility.)
CODE_DIR = os.path.dirname(os.path.abspath(__file__))


# The portable Music Room data folder the startup backup writes onto the
# library's drive, so the drive carries a current DB + metadata next to the
# music. Same string used by app.py's backup. Note the em-dash.
DRIVE_APPDATA_FOLDER = "Music Room — App Data"


def _find_drive_appdata(volumes_root: str = "/Volumes") -> str | None:
    """Look for a portable Music Room DB on any mounted external drive
    (/Volumes/*/Music Room — App Data/library.db). Used as the fallback when the
    LOCAL computer has no database — so plugging the drive into another machine
    'just works': music comes from the drive, and so does the DB + metadata.
    The drive selection normally lives in settings (inside the DB), which we
    can't read when there's no DB yet — so we discover the folder by name."""
    try:
        for vol in Path(volumes_root).iterdir():
            cand = vol / DRIVE_APPDATA_FOLDER
            if (cand / "library.db").is_file():
                return str(cand)
    except OSError:
        pass
    return None


# --- DATA_DIR: writable user data ------------------------------------------
def _resolve_data_dir() -> str:
    # 1. Explicit override is LITERAL — used exactly as given. Tools that set it
    #    (the bundle launcher, tests, power users) mean "this folder", and may be
    #    about to CREATE a DB there. The drive fallback must never hijack it; if a
    #    caller wants the drive, it points MUSICROOM_DATA at the drive itself.
    env = os.environ.get("MUSICROOM_DATA")
    if env:
        return os.path.expanduser(env)

    # 2. No override → the normal LOCAL location (App Support frozen, else dev).
    local = os.path.expanduser("~/Library/Application Support/Music Room") if is_frozen() else CODE_DIR
    if os.path.isfile(os.path.join(local, "library.db")):
        return local
    # 3. No local DB anywhere → adopt the database on a plugged-in Music Room
    #    drive, so a fresh machine 'just works' when the drive is connected.
    drive = _find_drive_appdata()
    return drive if drive else local


DATA_DIR = _resolve_data_dir()
os.makedirs(DATA_DIR, exist_ok=True)

# Writable data paths — all under DATA_DIR. In dev DATA_DIR == project dir,
# so these resolve to exactly the same places they always have.
DB_PATH            = os.path.join(DATA_DIR, "library.db")
VOICE_NOTES_DIR    = os.path.join(DATA_DIR, "voice_notes")
RECORDINGS_DIR     = os.path.join(DATA_DIR, "recordings")
EXPORTS_DIR        = os.path.join(DATA_DIR, "exports")

# User-uploaded media lives under DATA_DIR/static/… so the app's static
# overlay route (serves DATA_DIR/static first, code static second) finds it.
DATA_STATIC_DIR    = os.path.join(DATA_DIR, "static")
MOODBOARD_DIR      = os.path.join(DATA_STATIC_DIR, "moodboard")
AMBIENT_DIR        = os.path.join(DATA_STATIC_DIR, "ambient")
PLACE_BG_DIR       = os.path.join(DATA_STATIC_DIR, "place_bg")
STICKERS_DIR       = os.path.join(DATA_STATIC_DIR, "stickers")
OVERLAY_IMAGES_DIR = os.path.join(DATA_STATIC_DIR, "overlay_images")
ARTWORK_LOCAL_DIR  = os.path.join(DATA_STATIC_DIR, "artwork")


def ensure_data_dirs():
    """Create every writable directory. Safe to call repeatedly."""
    for d in (VOICE_NOTES_DIR, RECORDINGS_DIR, EXPORTS_DIR, DATA_STATIC_DIR,
              MOODBOARD_DIR, AMBIENT_DIR, PLACE_BG_DIR, STICKERS_DIR, OVERLAY_IMAGES_DIR,
              ARTWORK_LOCAL_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


def worker_command(extra_args, dev_base_dir=None):
    """Build the command that runs the importer / analyser as a child process.

    • Bundled: re-invoke our own executable with a --mr-worker sentinel; the
      launcher detects it and dispatches into importer.main() inside the same
      frozen environment (no venv needed).
    • Dev: prefer the project venv's python, else system python3, running
      importer.py directly — exactly as before.
    """
    if is_frozen():
        return [sys.executable, "--mr-worker", *extra_args]
    base = dev_base_dir or CODE_DIR
    venv_python = os.path.join(base, "venv", "bin", "python3")
    python_bin = venv_python if os.path.exists(venv_python) else "python3"
    return [python_bin, os.path.join(base, "importer.py"), *extra_args]
