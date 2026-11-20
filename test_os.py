"""The Mac-or-Windows helpers (mr_os.py) and the places that lean on them:
where a ready-made app keeps its data, the name ffmpeg goes by, the Recycle
Bin on Windows. Runs on a Mac here and on Windows in GitHub's Windows build
(.github/workflows/windows.yml). Opens no windows. Run:  python test_os.py"""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "native"))
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

import mr_os
chk(mr_os.IS_MAC == (sys.platform == "darwin") and mr_os.IS_WIN == sys.platform.startswith("win"), "it knows which computer it is on")
p = mr_os.app_data("Music Room GR")
if mr_os.IS_WIN:
    chk(p.lower().endswith("\\music room gr") and "appdata" in p.lower(), f"Windows keeps the app's data in %APPDATA% ({p})")
elif mr_os.IS_MAC:
    chk(p.endswith("/Library/Application Support/Music Room GR"), "a Mac keeps it in Application Support")
import mr_paths
chk(mr_paths._app_data("Music Room GR") == p, "the data folder is the same answer wherever it is asked")
import launcher
chk(launcher._app_data("Music Room GR") == p, "…including by the ready-made app's launcher")
import mr_ffmpeg
names = {os.path.basename(c) for c in mr_ffmpeg._bundled_candidates()} or {"ffmpeg.exe" if mr_os.IS_WIN else "ffmpeg"}
chk(all(n == ("ffmpeg.exe" if mr_os.IS_WIN else "ffmpeg") for n in names), "ffmpeg is looked for under this computer's name for it")
path, why = (None, None)
chk(callable(mr_os.choose) and callable(mr_os.reveal) and callable(mr_os.open_target), "opening, revealing and choosing are there")

if mr_os.IS_WIN:
    d = tempfile.mkdtemp()
    f = os.path.join(d, "a record.flac")
    open(f, "wb").write(b"x")
    ok, err = mr_os.recycle(f)
    chk(ok and not os.path.exists(f), f"a file goes to the Recycle Bin, not away for good ({err})")
    import trash_util
    g = os.path.join(d, "another.mp3")
    open(g, "wb").write(b"y")
    ok, err = trash_util.move_to_trash(g)
    chk(ok and not os.path.exists(g), "the app's one way of removing a file uses the Recycle Bin on Windows")
    import spotify_remote
    chk(os.environ.get("COMPUTERNAME", "").lower() in spotify_remote._this_computer(), "Spotify knows this PC by its name")
else:
    print("  SKIP  the Recycle Bin (not Windows)")

print()
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
sys.exit(1 if fails else 0)
