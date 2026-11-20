"""One place that answers "where is ffmpeg?" for the whole Music Room.

Everything that shells out to ffmpeg (m4a→ogg transcode for the player,
decode fallbacks for analysis, voice-note webm→wav) must go through
ffmpeg_path() instead of calling a bare "ffmpeg". Resolution order:

  1. the binary bundled inside the native .app (native/bin/ffmpeg via the
     PyInstaller spec) — a clean Mac has no ffmpeg of its own
  2. MUSICROOM_FFMPEG env override
  3. whatever is on PATH (dev: the Homebrew install)
  4. the usual Homebrew/MacPorts locations, in case the .app was launched
     from Finder where PATH is bare

Returns None when nothing is found — callers treat that as "this feature
is unavailable" and must say so visibly, never fail silently.
"""
import os
import shutil
import sys

_cached = None
_resolved = False


def _bundled_candidates():
    """Places the PyInstaller bundle could hold the binary."""
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(os.path.join(meipass, "ffmpeg"))
        cands.append(os.path.join(meipass, "bin", "ffmpeg"))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands.append(os.path.join(exe_dir, "ffmpeg"))
    return cands


def ffmpeg_path():
    """Absolute path to a runnable ffmpeg, or None. Cached after first call."""
    global _cached, _resolved
    if _resolved:
        return _cached
    found = None
    for cand in _bundled_candidates():
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            found = cand
            break
    if not found:
        env = os.environ.get("MUSICROOM_FFMPEG")
        if env and os.path.isfile(env) and os.access(env, os.X_OK):
            found = env
    if not found:
        found = shutil.which("ffmpeg")
    if not found:
        for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
                     "/opt/local/bin/ffmpeg"):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                found = cand
                break
    _cached, _resolved = found, True
    return _cached


def have_ffmpeg():
    return ffmpeg_path() is not None
