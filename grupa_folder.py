"""grupa_folder.py — a grúpa as a FOLDER of files, to drag into Ableton, Serato,
rekordbox or anything else that takes audio files.

Daithí, 2026-11-16: "export all the tracks in a grupa that i own on my machine
to a folder called the name of the grupa… without moving the audio files from
their original place… and without also copying and duplicating the files… If
not then create a copy but notify the user that this will be the case."

So a grúpa's folder holds its records IN THE GRÚPA'S ORDER (each name begins
with its number), and each one is put there in the lightest way the disk
allows — tried in this order:

  "same"  the very same file, listed in the folder as well (a hard link).
          Nothing is copied or moved and no room is used; every program sees
          an ordinary file. Only possible when the folder and the file are on
          the same drive.
  "link"  a pointer to the file where it is (a symbolic link). Nothing is
          copied or moved; it works across drives. Most programs follow it;
          one that doesn't needs real copies.
  "copy"  a real second copy — only when asked for (mode="copy"), which is
          what the page offers when the disk can do neither of the above, or
          when a program won't take links. Where the disk can, the copy shares
          its room with the original until one of them is changed (APFS).

The folder lives BESIDE the Music Room Library on its drive
("Music Room — Grúpaí/<name>/", next to "Music Room Library" and "Music Room —
App Data"), so "same" is possible for everything in the library; or, when
there is no library folder to stand beside, inside the app's own exports
folder. It is never inside the library itself: nothing there is ever at risk
of being scanned, organised or backed up twice.

A small hidden list (.musicroom.json) remembers what this code put in the
folder. Making the folder again brings it in line with the grúpa and takes out
only what that list names; a file someone else put there is never touched, and
neither is a copy that has been changed since it was made. Nothing here ever
writes to, moves or deletes an original.

No Flask, no database: app.py works out which files a grúpa stands for and
hands them here (see _grupa_folder_tracks there). test_grupa.py exercises it.
"""

import json
import os
import shutil
import time
from pathlib import Path

MANIFEST = ".musicroom.json"
KIND = "grupa_folder"
BESIDE_LIBRARY = "Music Room — Grúpaí"      # next to "Music Room Library"
IN_EXPORTS = "Grúpaí"                        # inside the app's own exports folder
_ILLEGAL = '\\/:*?"<>|\0'


def clean(name, fallback="untitled"):
    """A name that can be a file or folder name on any disk."""
    out = "".join("_" if (c in _ILLEGAL or ord(c) < 32) else c for c in str(name or ""))
    out = " ".join(out.split()).strip(" .")
    return out[:180] or fallback


def root_for(library_dest, exports_dir):
    """Where grúpa folders live → (path, "library" | "own"): beside the Music
    Room Library when that folder is there to be reached, else in the app's own."""
    if library_dest and os.path.isdir(library_dest):
        return Path(library_dest).resolve().parent / BESIDE_LIBRARY, "library"
    return Path(exports_dir) / IN_EXPORTS, "own"


def read_manifest(folder):
    """What this code put in the folder before, or None if it isn't one of ours."""
    try:
        d = json.loads((Path(folder) / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("kind") == KIND else None


def names_for(tracks):
    """Each record's name in the folder: its number in the grúpa, then who it is
    by and what it is called (or the file's own name, when the room doesn't know)."""
    width = max(2, len(str(len(tracks))))
    out, used = [], set()
    for i, t in enumerate(tracks, 1):
        src = t["path"]
        ext = os.path.splitext(src)[1]
        artist, title = (t.get("artist") or "").strip(), (t.get("title") or "").strip()
        base = clean(f"{artist} - {title}" if (artist and title) else (title or os.path.splitext(os.path.basename(src))[0]))[:150]
        name = f"{i:0{width}d} {base}{ext}"
        n = 2
        while name.lower() in used:
            name = f"{i:0{width}d} {base} ({n}){ext}"; n += 1
        used.add(name.lower())
        out.append(name)
    return out


def _clone(src, dst):
    """A copy that shares its room with the original until one is changed (APFS,
    same drive). True if it was made."""
    try:
        import ctypes
        import ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        fn = libc.clonefile
        fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        fn.restype = ctypes.c_int
        return fn(os.fsencode(src), os.fsencode(dst), 0) == 0
    except (AttributeError, OSError, TypeError):
        return False


def place(src, dst, mode="link"):
    """Put one record in the folder → "same" | "link" | "copy" | "clone".
    Raises OSError when it can't be done that way."""
    if mode == "copy":
        if _clone(src, dst):
            return "clone"
        shutil.copy2(src, dst)
        return "copy"
    try:
        os.link(src, dst)                        # the same file, listed here too
        return "same"
    except OSError:
        os.symlink(src, dst)                     # a pointer to it, where it is
        return "link"


def can_link(folder, src):
    """Can this folder hold a record without copying it? → "same" | "link" | None."""
    folder = Path(folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    probe = folder / f".probe-{os.getpid()}-{int(time.time() * 1000)}"
    try:
        return place(src, str(probe), "link")
    except OSError:
        return None
    finally:
        try:
            if probe.is_symlink() or probe.exists():
                probe.unlink()
        except OSError:
            pass


def _ours_still(path, entry):
    """Is the thing at this name still what we put there? (A copy that was
    changed since — its tags written by a DJ program, say — is the user's now.)"""
    try:
        if entry.get("how") == "link":
            return path.is_symlink()
        if path.is_symlink() or not path.is_file():
            return False
        st = path.stat()
        if entry.get("how") == "same":
            return st.st_ino == entry.get("ino")
        return st.st_size == entry.get("size") and int(st.st_mtime) == entry.get("mtime")
    except OSError:
        return False


def _take_out(folder, entries):
    """Remove what we put there (and only that). → (removed, kept names)"""
    removed, kept = 0, []
    for e in entries or []:
        name = e.get("file") or ""
        if not name or os.sep in name or name in (".", ".."):
            continue
        p = Path(folder) / name
        if not (p.is_symlink() or p.exists()):
            continue
        if _ours_still(p, e):
            try:
                p.unlink()                       # the name in THIS folder only — never the original
                removed += 1
            except OSError:
                kept.append(name)
        else:
            kept.append(name)
    return removed, kept


def build(folder, grupa_name, tracks, mode="link", grupa_id=None):
    """Bring the folder in line with the grúpa. `tracks` = [{"track_id", "title",
    "artist", "path", "duration_sec"}] in order; `path` must exist.
    → {"folder", "files", "same", "linked", "copied", "bytes_copied", "kept", "failed", "playlist"}"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    old = read_manifest(folder) or {}
    names = names_for(tracks)
    want = {n: t for n, t in zip(names, tracks)}
    keep_as_is, stale = {}, []
    for e in old.get("files") or []:
        t = want.get(e.get("file"))
        p = folder / (e.get("file") or "")
        same_job = (t is not None and e.get("src") == t["path"] and _ours_still(p, e)
                    and ((mode == "copy") == (e.get("how") in ("copy", "clone"))))
        if same_job:
            keep_as_is[e["file"]] = e            # already there, already right
        else:
            stale.append(e)
    _removed, kept = _take_out(folder, stale)
    for old_list in (old.get("playlist"),):      # the playlist file we wrote last time, if its name changed
        if old_list and old_list != clean(grupa_name) + ".m3u8":
            try:
                (folder / old_list).unlink()
            except OSError:
                pass

    entries, failed = [], []
    counts = {"same": 0, "link": 0, "copy": 0, "clone": 0}
    bytes_copied = 0
    for name, t in zip(names, tracks):
        if name in keep_as_is:
            e = keep_as_is[name]
            entries.append(e); counts[e.get("how", "link")] = counts.get(e.get("how", "link"), 0) + 1
            continue
        dst = folder / name
        if dst.is_symlink() or dst.exists():     # something of the user's has this name: step aside, don't replace it
            stem, ext = os.path.splitext(name)
            n = 2
            while (folder / f"{stem} ({n}){ext}").exists() or (folder / f"{stem} ({n}){ext}").is_symlink():
                n += 1
            name = f"{stem} ({n}){ext}"; dst = folder / name
        try:
            how = place(t["path"], str(dst), mode)
        except OSError as err:
            failed.append({"title": t.get("title") or os.path.basename(t["path"]), "why": str(err.strerror or err)})
            continue
        e = {"file": name, "track_id": t.get("track_id"), "src": t["path"], "how": how}
        try:
            st = dst.stat()
            e.update(ino=st.st_ino, size=st.st_size, mtime=int(st.st_mtime))
            if how == "copy":
                bytes_copied += st.st_size
        except OSError:
            pass
        entries.append(e); counts[how] += 1

    # a playlist beside them: the ORIGINAL files, in order (rekordbox and others can read it;
    # pointing at the originals means a program that already knows your library sees no new files)
    playlist = clean(grupa_name) + ".m3u8"
    by_name = {n: t for n, t in zip(names, tracks)}
    lines = ["#EXTM3U"]
    for e in entries:
        t = by_name.get(e["file"]) or next((x for x in tracks if x["path"] == e.get("src")), None)
        if not t:
            continue
        who = " - ".join(x for x in ((t.get("artist") or "").strip(), (t.get("title") or "").strip()) if x)
        lines.append(f"#EXTINF:{int(t.get('duration_sec') or 0)},{who}")
        lines.append(t["path"])
    try:
        (folder / playlist).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        playlist = ""
    manifest = {"kind": KIND, "name": grupa_name, "grupa_id": grupa_id, "mode": mode,
                "made_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "playlist": playlist, "files": entries}
    try:
        (folder / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    except OSError:
        pass
    return {"folder": str(folder), "files": len(entries), "same": counts["same"], "linked": counts["link"],
            "copied": counts["copy"] + counts["clone"], "shared": counts["clone"], "bytes_copied": bytes_copied,
            "kept": kept, "failed": failed, "playlist": playlist}


def status(folder):
    """What is in a grúpa's folder now, by our own list → None if it isn't there (or isn't ours)."""
    folder = Path(folder)
    m = read_manifest(folder) if folder.is_dir() else None
    if not m:
        return None
    files = m.get("files") or []
    here = sum(1 for e in files if (folder / e.get("file", "")).exists() or (folder / e.get("file", "")).is_symlink())
    broken = sum(1 for e in files if (folder / e.get("file", "")).is_symlink() and not (folder / e.get("file", "")).exists())
    hows = {}
    for e in files:
        k = "copy" if e.get("how") in ("copy", "clone") else e.get("how", "link")
        hows[k] = hows.get(k, 0) + 1
    return {"folder": str(folder), "made_at": m.get("made_at"), "mode": m.get("mode") or "link", "files": len(files),
            "here": here, "broken": broken, "how": hows, "playlist": m.get("playlist") or ""}


def remove(folder, links_only=True):
    """Take a grúpa's folder away again: what we put there goes (copies stay unless
    asked), the folder too if nothing else is left in it. → True if the folder is gone."""
    folder = Path(folder)
    m = read_manifest(folder) if folder.is_dir() else None
    if not m:
        return False
    files = m.get("files") or []
    mine = [e for e in files if not (links_only and e.get("how") in ("copy", "clone"))]
    _take_out(folder, mine)
    left = [e for e in files if (folder / e.get("file", "")).exists() or (folder / e.get("file", "")).is_symlink()]
    if left:
        m["files"] = left
        try:
            (folder / MANIFEST).write_text(json.dumps(m, indent=1), encoding="utf-8")
        except OSError:
            pass
        return False
    for extra in (m.get("playlist"), MANIFEST, ".DS_Store"):
        if extra:
            try:
                (folder / extra).unlink()
            except OSError:
                pass
    try:
        folder.rmdir()                           # only if it is empty: anything else in it is the user's
        return True
    except OSError:
        return False
