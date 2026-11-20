"""Safe file removal — the ONE place that moves a file to the macOS Trash.

NEVER hard-deletes. If every Trash method fails it returns (False, err) and the
caller must treat the file as STILL PRESENT. Shared by app.py (delete endpoints,
dedupe) and importer.py (import-time duplicate handling) so there is a single,
verified implementation. (A previous app.py version fell back to os.remove(),
which permanently destroyed files when Finder-trash failed — never again.)
"""
import os
import subprocess


def move_to_trash(file_path):
    """Move a file to the macOS Trash (recoverable). Returns (ok, err)."""
    if not file_path or not os.path.exists(file_path):
        return True, None
    # 0) Windows: the Recycle Bin (recoverable, like the Trash)
    import mr_os
    if mr_os.IS_WIN:
        return mr_os.recycle(file_path)
    # 1) Finder — puts it in the volume's Trash, fully recoverable
    try:
        script = f'tell application "Finder" to delete POSIX file "{file_path}"'
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and not os.path.exists(file_path):
            return True, None
    except Exception:
        pass
    # 2) the `trash` CLI if the user has it
    try:
        r2 = subprocess.run(["trash", file_path], capture_output=True, timeout=15)
        if r2.returncode == 0 and not os.path.exists(file_path):
            return True, None
    except Exception:
        pass
    # 3) macOS Foundation trash API via PyObjC, if available (still the real Trash)
    try:
        from Foundation import NSURL, NSFileManager  # type: ignore
        url = NSURL.fileURLWithPath_(file_path)
        ok, _new, _err = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(url, None, None)
        if ok and not os.path.exists(file_path):
            return True, None
    except Exception:
        pass
    # Could NOT trash — refuse to delete. The file stays; report failure.
    return False, "could not move to Trash (refusing to delete permanently)"
