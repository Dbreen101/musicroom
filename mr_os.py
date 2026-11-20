"""
mr_os.py — the few things the Music Room asks of the computer it runs on,
done the right way on a Mac and on Windows (2026-11-20: "there needs to be a
pc version as well as a Mac version").

    IS_MAC, IS_WIN
    app_data(name)             where an app keeps its own data:
                                 Mac      ~/Library/Application Support/<name>
                                 Windows  %APPDATA%\\<name>
    open_target(target, app)   open a web address, a file or a folder with what the
                               computer uses for it (`app`: a browser's name, Mac only)
    reveal(path)               show a file or folder in Finder / File Explorer, selected
    choose(kind, start, prompt) the computer's own "choose a folder / file" window
                               → (path, None) · (None, "cancelled") · (None, why it failed)

Nothing here needs anything installed: on Windows the choosing window is
PowerShell's (part of every Windows since 7), and nothing is shown in a console.
"""
import os
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
_NO_WINDOW = 0x08000000 if IS_WIN else 0        # CREATE_NO_WINDOW: no black console flashing up


def app_data(name="Music Room"):
    if IS_WIN:
        root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(root, name)
    if IS_MAC:
        return os.path.expanduser(os.path.join("~/Library/Application Support", name))
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), name)


def open_target(target, app=None):
    """Open it with what the computer uses for it. Raises OSError when it can't."""
    if IS_MAC:
        subprocess.Popen(["open", "-a", app, target] if app else ["open", target])
    elif IS_WIN:
        os.startfile(target)                     # (a browser's name can't be chosen this way: the default is used)
    else:
        subprocess.Popen(["xdg-open", target])


def reveal(path):
    """Show it in Finder / File Explorer, selected. Raises OSError when it can't."""
    if IS_MAC:
        subprocess.Popen(["open", "-R", path])
    elif IS_WIN:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], creationflags=_NO_WINDOW)
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or path])


# ── choosing a folder or a file ──
_PS_FOLDER = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = $env:MR_PROMPT
$d.ShowNewFolderButton = $true
if ($env:MR_START -and (Test-Path -LiteralPath $env:MR_START)) { $d.SelectedPath = $env:MR_START }
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($d.SelectedPath) } else { exit 2 }
"""
_PS_FILE = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Title = $env:MR_PROMPT
if ($env:MR_START -and (Test-Path -LiteralPath $env:MR_START)) { $d.InitialDirectory = $env:MR_START }
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($d.FileName) } else { exit 2 }
"""


def choose(kind="folder", start="", prompt=""):
    kind = "file" if kind == "file" else "folder"
    prompt = prompt or ("Choose a file" if kind == "file" else "Choose a folder")
    check = start if kind == "folder" else (os.path.dirname(start) if start else "")
    start = check if check and os.path.isdir(check) else ""
    if IS_WIN:
        env = dict(os.environ, MR_PROMPT=prompt, MR_START=start)   # (never put into the script itself)
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
                                "-Command", _PS_FILE if kind == "file" else _PS_FOLDER],
                               capture_output=True, timeout=600, env=env, creationflags=_NO_WINDOW)
        except Exception as e:
            return None, str(e)
        if r.returncode == 2:
            return None, "cancelled"
        if r.returncode != 0:
            return None, (r.stderr or b"").decode("utf-8", "replace").strip() or "the chooser didn't open"
        path = (r.stdout or b"").decode("utf-8", "replace").strip()
        return (path, None) if path else (None, "cancelled")
    if IS_MAC:
        safe = prompt.replace('"', "'").replace("\\", "")
        loc = f' default location (POSIX file "{start}")' if start and '"' not in start else ""
        script = ('tell application "System Events" to activate\n'
                  f'POSIX path of ({"choose file" if kind == "file" else "choose folder"} with prompt "{safe}"{loc})')
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
        except Exception as e:
            return None, str(e)
        if r.returncode != 0:
            err = (r.stderr or "").strip()
            return (None, "cancelled") if ("User canceled" in err or "-128" in err) else (None, err or "the chooser didn't open")
        path = (r.stdout or "").strip()
        return (path, None) if path else (None, "cancelled")
    return None, "there is no chooser on this computer — type the path instead"


# ── the Recycle Bin (Windows): a file moved there can be put back ──
def recycle(path):
    """Move a file or folder to the Recycle Bin. → (True, None) or (False, why)."""
    if not IS_WIN:
        return False, "not Windows"
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    FOF_WANTNUKEWARNING = 0x4000        # where there is no Recycle Bin (some drives), ask rather than delete for good
    op = SHFILEOPSTRUCTW(None, FO_DELETE, os.path.abspath(path) + "\0", None,
                         FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI | FOF_WANTNUKEWARNING,
                         False, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc == 0 and not op.fAnyOperationsAborted and not os.path.exists(path):
        return True, None
    return False, f"the Recycle Bin refused it (code {rc})"
