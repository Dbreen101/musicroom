"""Scan a folder of music productions (Ableton-first) and group them into
tracks + versions — WITHOUT touching, moving or parsing any files.

The Music Room links to your sessions and bounces *in place*. It never opens an
`.als` to read it, never moves a project, never renames anything. This module
only walks the filesystem and reports what it found, so the importer can store
paths.

── The convention (forgiving) ───────────────────────────────────────────────
Point the Music Room at a folder. Inside, organise it like this:

    My Productions/
      Smoke Signal/                ← one folder per track (folder name = track)
        Smoke Signal.als           ← the Ableton session(s)
        Bounces/                   ← versions / mixes go here
          Smoke Signal v1.wav
          Smoke Signal - rough.wav
          Smoke Signal final.wav
      Aurora/
        Aurora.als
        Aurora rough mix.wav       ← (or just drop bounces in the track folder)

Rules the scanner follows:
- one **folder = one track** (its name is the track name);
- **sessions** = any `.als` in the track folder (or a nested project subfolder);
- **versions/mixes** = audio in the track folder's top level OR a
  Bounces / Versions / Renders / Exports / Mixes subfolder;
- Ableton's **Samples/** and **Backup/** folders are ALWAYS skipped, so the
  project's internal stems and recordings never get imported as "versions".

If you point it straight at a single track folder (one that has an `.als`), it
imports just that one. Point it at a parent folder and it imports every track
folder inside.
"""
import os, re, shutil

AUDIO_EXT   = {".wav", ".aiff", ".aif", ".flac", ".mp3", ".m4a", ".ogg"}
SESSION_EXT = {".als"}                       # Ableton Live Set; other DAWs extend this
BOUNCE_DIRS = {"bounces", "bounce", "versions", "renders", "render",
               "exports", "export", "mixes", "mixdowns"}
# Ableton's own internal folders (never a "version") — both old + new names.
SKIP_DIRS   = {"samples", "backup", "ableton project info", "ableton folder info",
               "samplecapture", "__macosx", ".trash", "freeze"}

# Ableton stamps saved copies with " [YYYY-MM-DD HHMMSS]"; the file WITHOUT a
# stamp is the current set. Used to name tracks and pick the current session.
_TS_RE = re.compile(r"\s*\[\d{4}-\d{2}-\d{2} \d{6}\]\s*$")


def _ext(p):        return os.path.splitext(p)[1].lower()
def _is_audio(p):   return _ext(p) in AUDIO_EXT
def _is_session(p): return _ext(p) in SESSION_EXT
def _stem(p):       return os.path.splitext(os.path.basename(p))[0]
def _strip_ts(stem): return _TS_RE.sub("", stem).strip()


def track_name_from_folder(folder):
    """Track name from a project folder — Ableton appends ' Project' to the
    folder it makes on Save, so strip it."""
    name = os.path.basename(folder.rstrip(os.sep)) or folder
    if name.lower().endswith(" project"):
        name = name[:-len(" Project")].strip()
    return name or os.path.basename(folder.rstrip(os.sep))


def primary_session(sessions):
    """The current Live Set: prefer one with no ' [timestamp]' suffix; else the
    most recent timestamp (the format sorts lexically)."""
    if not sessions:
        return None
    plain = [s for s in sessions if not _TS_RE.search(_stem(s))]
    if plain:
        return sorted(plain, key=lambda s: len(_stem(s)))[0]
    return sorted(sessions)[-1]


def pair_versions(sessions, bounces):
    """A version = a bounce + the session it came from, matched by EXACT name
    (Daithí's convention: 'Track 1 v2.wav' is the bounce of 'Track 1 v2.als').
    A bounce with no same-named session still counts as a version (session=None).
    """
    by_stem = {}
    for s in sessions:
        by_stem.setdefault(_stem(s), s)          # first wins (e.g. the un-stamped one)
    return [{"bounce": b, "session": by_stem.get(_stem(b))} for b in bounces]


def _listdir(d):
    try:
        return sorted(os.listdir(d))
    except OSError:
        return []


def scan_project_folder(folder):
    """One track folder → {name, folder, sessions:[…], bounces:[…]} or None
    if it holds neither a session nor any audio."""
    if not os.path.isdir(folder):
        return None
    name = track_name_from_folder(folder)
    sessions, bounces = [], []
    for e in _listdir(folder):
        if e.startswith("."):
            continue
        full = os.path.join(folder, e)
        if os.path.isfile(full):
            if _is_session(full):
                sessions.append(full)
            elif _is_audio(full):
                bounces.append(full)
        elif os.path.isdir(full):
            low = e.lower()
            if low in SKIP_DIRS:
                continue
            if low in BOUNCE_DIRS:
                for f in _listdir(full):
                    fp = os.path.join(full, f)
                    if not f.startswith(".") and os.path.isfile(fp) and _is_audio(fp):
                        bounces.append(fp)
            else:
                # a nested "<name> Project/" subfolder may hold the .als
                for f in _listdir(full):
                    fp = os.path.join(full, f)
                    if not f.startswith(".") and os.path.isfile(fp) and _is_session(fp):
                        sessions.append(fp)
    if not sessions and not bounces:
        return None
    return {"name": name, "folder": folder, "sessions": sessions,
            "bounces": bounces, "primary_session": primary_session(sessions),
            "versions": pair_versions(sessions, bounces)}


def _has_top_level_project_file(folder):
    """True if `folder` directly contains a session or audio file (so it is
    itself a track folder, not a parent of track folders)."""
    for e in _listdir(folder):
        if e.startswith("."):
            continue
        full = os.path.join(folder, e)
        if os.path.isfile(full) and (_is_session(full) or _is_audio(full)):
            return True
    return False


def _has_top_level_session(folder):
    """True if a .als sits DIRECTLY in `folder` (so it is itself one project)."""
    for e in _listdir(folder):
        if e.startswith(".."):
            continue
        full = os.path.join(folder, e)
        if not e.startswith(".") and os.path.isfile(full) and _is_session(full):
            return True
    return False


def _place_dir(src, dst, mode, summary):
    """Move/copy a whole folder as a unit. Never overwrites."""
    if os.path.exists(dst):
        summary["skipped"] += 1
        return
    if mode == "move":
        shutil.move(src, dst)
    else:
        shutil.copytree(src, dst)
    summary["projects_filed"] += 1


def _place_file(src, dst, mode, summary):
    if os.path.exists(dst):
        summary["skipped"] += 1
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if mode == "move":
        shutil.move(src, dst)
    else:
        shutil.copy2(src, dst)
    summary["loose_filed"] += 1


def organise_productions(source, dest, mode="copy"):
    """Tidy a messy `source` into the convention at `dest`.

    SAFE BY DESIGN: COPY is the default (your originals are never touched); MOVE
    frees the source. A whole project folder is always placed as a UNIT so
    Ableton's internal references can't break — we never reorganise inside a
    project. Loose renders are filed into <track>/Bounces. Never overwrites an
    existing target. Returns a summary; the caller then imports `dest`.
    """
    if not os.path.isdir(source):
        return {"error": "source not found"}
    src_abs, dst_abs = os.path.abspath(source).rstrip(os.sep), os.path.abspath(dest).rstrip(os.sep)
    if dst_abs == src_abs or dst_abs.startswith(src_abs + os.sep):
        return {"error": "destination must be outside the source"}
    os.makedirs(dest, exist_ok=True)
    summary = {"dest": dest, "mode": mode, "projects_filed": 0, "loose_filed": 0, "skipped": 0}

    # Source is itself one Ableton project (has a .als at its top) → place the
    # whole folder, intact, as a single track.
    if _has_top_level_session(source):
        _place_dir(source, os.path.join(dest, os.path.basename(src_abs)), mode, summary)
        try: os.sync()
        except Exception: pass
        return summary

    # Otherwise it's a parent: each project subfolder moves as a UNIT; loose
    # renders sitting at the top get filed into <track>/Bounces.
    for e in _listdir(source):
        if e.startswith(".") or e.lower() in SKIP_DIRS:
            continue
        full = os.path.join(source, e)
        if os.path.isdir(full):
            if scan_project_folder(full):
                _place_dir(full, os.path.join(dest, e), mode, summary)
        elif os.path.isfile(full) and _is_audio(full):
            track = _strip_ts(_stem(full)) or _stem(full)
            _place_file(full, os.path.join(dest, track, "Bounces", os.path.basename(full)), mode, summary)

    try: os.sync()
    except Exception: pass
    return summary


def scan_productions(root):
    """A folder → a list of project dicts.
    - If `root` itself is a track folder (a session/audio file sits at its top
      level), returns just it.
    - Otherwise treats each immediate subfolder as a track folder.
    """
    if not os.path.isdir(root):
        return []
    if _has_top_level_project_file(root):
        p = scan_project_folder(root)
        return [p] if p else []
    out = []
    for e in _listdir(root):
        if e.startswith(".") or e.lower() in SKIP_DIRS:
            continue
        full = os.path.join(root, e)
        if os.path.isdir(full):
            p = scan_project_folder(full)
            if p:
                out.append(p)
    return out
