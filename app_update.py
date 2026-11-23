"""The app updating itself — one press on "Update now".

When the Music Room names a newer release than the one running, the app fetches that
release's ready-made app for this computer from the project's own page on GitHub, checks
it, puts it where the running app is, and opens it again. Nothing of the person's is
touched: their room, records and sign-in live in the data folder, not in the app.

What it will and won't do:
  • it only ever downloads from REPO's releases, over https — never from an address the
    rooms server (or anything else) hands it;
  • it checks the download's size, its SHA-256 when GitHub gives one, and that what came
    out IS this app (its bundle id on a Mac) at the version asked for;
  • the app it replaces is kept until the new one is in place, and put back if anything fails;
  • where it can't replace itself (run from the code, a folder it may not write to, a Mac
    app still being run from the download's own quarantine) it says so, and the release
    page is offered instead.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

REPO = "Dbreen101/musicroom"
BUNDLE_ID = "com.daithi.musicroom.gr"
WIN_FOLDER, WIN_EXE = "Music Room GR", "Music Room GR.exe"
PAGE = f"https://github.com/{REPO}/releases/latest"

_lock = threading.Lock()
_state = {"step": "idle", "done": 0, "total": 0, "error": "", "version": "", "staged": ""}


def _is_win():
    return sys.platform.startswith("win")


def asset_name():
    """The ready-made app for this computer, as it is called on the release page."""
    if _is_win():
        return "Music.Room.GR.Windows.zip"
    import platform
    return "Music.Room.GR.Apple.Silicon.zip" if platform.machine() == "arm64" else "Music.Room.GR.Intel.zip"


def where():
    """Where the running app sits, and whether it can replace itself there.
    → {"can": bool, "why": words when it can't, "app": the path that would be replaced}"""
    if not getattr(sys, "frozen", False):
        return {"can": False, "why": "This copy runs from the code: update it with git.", "app": ""}
    exe = os.path.realpath(sys.executable)
    if _is_win():
        app = os.path.dirname(exe)
    else:
        app = os.path.dirname(os.path.dirname(os.path.dirname(exe)))        # X.app/Contents/MacOS/music-room
        if not app.endswith(".app"):
            return {"can": False, "why": "This copy isn't an app that can be replaced.", "app": ""}
        if "/AppTranslocation/" in app:
            return {"can": False, "app": "",
                    "why": "Move Music Room GR into your Applications folder and open it from there; then it can update itself."}
    parent = os.path.dirname(app)
    if not os.access(parent, os.W_OK) or not os.access(app, os.W_OK):
        return {"can": False, "why": "This app is in a folder it may not change.", "app": app}
    return {"can": True, "why": "", "app": app}


def state():
    with _lock:
        return dict(_state)


def _set(**kw):
    with _lock:
        _state.update(kw)


def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "music-room-app"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _find_asset(version):
    """(download address, size, sha256 or '') of this computer's app in release v<version>."""
    rel = _get_json(f"https://api.github.com/repos/{REPO}/releases/tags/v{version}")
    want = asset_name()
    for a in rel.get("assets") or []:
        if a.get("name") == want:
            url = a.get("browser_download_url") or ""
            if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
                raise RuntimeError("the release's download address isn't the project's own")
            digest = str(a.get("digest") or "")
            return url, int(a.get("size") or 0), digest[7:] if digest.startswith("sha256:") else ""
    raise RuntimeError(f"release {version} has no app for this computer yet — try again in a few minutes")


def _download(url, dest, size, sha):
    h, done = hashlib.sha256(), 0
    _set(step="downloading", done=0, total=size)
    part = dest + ".part"
    if url.startswith("https://"):
        src = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "music-room-app"}), timeout=60)
    else:
        src = open(url, "rb")                       # (a file on this computer: the test's stand-in for the download)
    with src, open(part, "wb") as out:
        while True:
            chunk = src.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk); h.update(chunk); done += len(chunk)
            _set(done=done)
    if size and done != size:
        raise RuntimeError("the download stopped part-way — try again")
    if sha and h.hexdigest() != sha.lower():
        raise RuntimeError("the download didn't match the release's own fingerprint — nothing was changed")
    os.replace(part, dest)


def _unpack(zip_path, into, version):
    """→ the path of the new app inside `into`, checked to be this app at this version."""
    _set(step="unpacking")
    if _is_win():
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            base = os.path.realpath(into)
            for n in z.namelist():                   # nothing may land outside the folder
                if not os.path.realpath(os.path.join(into, n)).startswith(base):
                    raise RuntimeError("the download wasn't a plain app folder")
            z.extractall(into)
        new = os.path.join(into, WIN_FOLDER)
        if not os.path.isfile(os.path.join(new, WIN_EXE)):
            raise RuntimeError("the download didn't hold the app")
        return new
    # a Mac app is full of links and permissions a plain unzip loses: ditto keeps them
    subprocess.run(["/usr/bin/ditto", "-x", "-k", zip_path, into], check=True, capture_output=True, timeout=600)
    apps = [os.path.join(into, n) for n in os.listdir(into) if n.endswith(".app")]
    if len(apps) != 1:
        raise RuntimeError("the download didn't hold the app")
    import plistlib        # (here, not at the top: the Windows app is packed without it, and could not start)
    with open(os.path.join(apps[0], "Contents", "Info.plist"), "rb") as fh:
        info = plistlib.load(fh)
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise RuntimeError("the download isn't the Music Room GR app — nothing was changed")
    if str(info.get("CFBundleShortVersionString") or "").lstrip("v") != version:
        raise RuntimeError("the download isn't the version that was asked for — nothing was changed")
    return apps[0]


def _work(version, work_dir):
    try:
        shutil.rmtree(work_dir, ignore_errors=True)
        os.makedirs(work_dir, exist_ok=True)
        _set(step="looking", error="", version=version, staged="")
        local = os.environ.get("MR_UPDATE_ZIP")      # (tests: a zip on this computer instead of the release page)
        if local:
            url, size, sha = local, os.path.getsize(local), ""
        else:
            url, size, sha = _find_asset(version)
        z = os.path.join(work_dir, "app.zip")
        _download(url, z, size, sha)
        new = _unpack(z, os.path.join(work_dir, "new"), version)
        os.remove(z)
        _set(step="ready", staged=new)
    except Exception as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        _set(step="error", error=str(e) or "the update couldn't be fetched")


def start(version, data_dir):
    """Fetch and check release `version` in the background. → False if one is already under way."""
    version = str(version or "").strip().lstrip("v")
    if not version or any(c not in "0123456789.-" for c in version):
        _set(step="error", error="no version to update to")
        return False
    if not where()["can"]:
        _set(step="error", error=where()["why"])
        return False
    with _lock:
        if _state["step"] in ("looking", "downloading", "unpacking", "restarting"):
            return False
        _state.update(step="looking", error="", done=0, total=0, version=version, staged="")
    threading.Thread(target=_work, args=(version, os.path.join(data_dir, "update")), daemon=True).start()
    return True


_MAC = r"""#!/bin/sh
# Music Room: put the new app where the old one is, once the old one has closed.
PID="$1"; OLD="$2"; NEW="$3"; WORK="$4"; OPEN="$5"
n=0; while kill -0 "$PID" 2>/dev/null && [ $n -lt 100 ]; do sleep 0.3; n=$((n+1)); done
BAK="$OLD.before-update"
rm -rf "$BAK"
if mv "$OLD" "$BAK" && mv "$NEW" "$OLD"; then
  xattr -dr com.apple.quarantine "$OLD" 2>/dev/null
  [ "$OPEN" = no ] || open "$OLD"
  rm -rf "$BAK" "$WORK"
else
  [ -e "$OLD" ] || mv "$BAK" "$OLD"        # anything went wrong: the app that was there is there again
  [ "$OPEN" = no ] || open "$OLD"
fi
"""

_WIN = r"""@echo off
rem Music Room: put the new app where the old one is, once the old one has closed.
set "PID=%~1"
set "OLD=%~2"
set "NEW=%~3"
set "WORK=%~4"
set /a n=0
:wait
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
if not errorlevel 1 if %n% lss 60 (set /a n+=1 & ping -n 2 127.0.0.1 >nul & goto wait)
set "BAK=%OLD%.before-update"
if exist "%BAK%" rmdir /s /q "%BAK%"
move "%OLD%" "%BAK%" >nul 2>&1
if errorlevel 1 goto back
move "%NEW%" "%OLD%" >nul 2>&1
if errorlevel 1 (move "%BAK%" "%OLD%" >nul 2>&1 & goto back)
start "" "%OLD%\Music Room GR.exe"
rmdir /s /q "%BAK%"
rmdir /s /q "%WORK%"
exit /b 0
:back
start "" "%OLD%\Music Room GR.exe"
exit /b 1
"""


def apply():
    """Hand over to a small helper that swaps the apps once this one has closed, and close.
    → False (with the reason in state()) when there is nothing ready to put in."""
    st, w = state(), where()
    if st["step"] != "ready" or not st["staged"] or not os.path.exists(st["staged"]) or not w["can"]:
        _set(step="error", error=w["why"] or "the new version isn't ready")
        return False
    work = os.path.dirname(os.path.dirname(st["staged"]))                  # …/update
    helper_dir = os.path.join(os.path.dirname(work), "update-helper")       # (outside what the helper removes)
    os.makedirs(helper_dir, exist_ok=True)
    args = [str(os.getpid()), w["app"], st["staged"], work,
            "no" if os.environ.get("MR_UPDATE_NO_OPEN") == "1" else "yes"]      # (tests: swap, don't reopen)
    if _is_win():
        script = os.path.join(helper_dir, "swap.bat")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(_WIN)
        subprocess.Popen(["cmd", "/c", script] + args, close_fds=True,
                         creationflags=0x00000008 | 0x00000200 | 0x08000000)   # detached · its own group · no window
    else:
        script = os.path.join(helper_dir, "swap.sh")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(_MAC)
        os.chmod(script, 0o755)
        subprocess.Popen(["/bin/sh", script] + args, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _set(step="restarting")
    threading.Timer(1.0, lambda: os._exit(0)).start()       # (the page hears "restarting" first)
    return True
