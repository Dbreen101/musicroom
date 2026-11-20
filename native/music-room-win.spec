# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller recipe for the WINDOWS Music Room (2026-11-20: "there needs to be a
pc version as well as a Mac version"). The Mac's is music-room.spec; this one
packs the same app into a folder with "Music Room.exe" in it.

It is built on Windows — by GitHub's own Windows machines (.github/workflows/
windows.yml), since a Mac can't make a Windows program:

    cd native && pyinstaller music-room-win.spec --clean --noconfirm

Output: native/dist/Music Room/  (Music Room.exe + everything beside it)

Same rules as the Mac's: only the app's code and assets go in — never anyone's
data. A settings file baked in by the build (baked_env.py: the Green Room's
server and switches) is picked up from MR_BAKED_ENV, as on the Mac.
"""
import glob
import os

from PyInstaller.utils.hooks import collect_all

PROJ = os.path.dirname(SPECPATH)
block_cipher = None
datas = []


def add_tree(rel_dir):
    base = os.path.join(PROJ, rel_dir)
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if fn.startswith(".") or fn.endswith((".pyc", ".DS_Store")):
                continue
            datas.append((os.path.join(root, fn), os.path.join("mrsrc", os.path.relpath(root, PROJ))))


for py in glob.glob(os.path.join(PROJ, "*.py")):
    datas.append((py, "mrsrc"))
for fn in ("VERSION", "HOUSE_RULES.md"):
    if os.path.isfile(os.path.join(PROJ, fn)):
        datas.append((os.path.join(PROJ, fn), "mrsrc"))
BAKED = os.environ.get("MR_BAKED_ENV") or os.path.join(SPECPATH, "baked_env.py")
if os.path.isfile(BAKED):
    if os.path.basename(BAKED) != "baked_env.py":
        raise SystemExit("[spec] MR_BAKED_ENV must point at a file called baked_env.py")
    datas.append((BAKED, "mrsrc"))
    print("[spec] baking", BAKED)
add_tree("templates")
add_tree("plugins")
for sub in ("css", "js", "textures", "fonts", "vendor", "data", "img"):
    add_tree(os.path.join("static", sub))

# ffmpeg.exe: from imageio-ffmpeg's Windows wheel, staged by the workflow (MR_FFMPEG_STAGED)
FFMPEG = os.environ.get("MR_FFMPEG_STAGED") or os.path.join(SPECPATH, "bin", "ffmpeg.exe")
if not os.path.isfile(FFMPEG):
    raise SystemExit("[spec] ffmpeg.exe is missing — stage it first (see .github/workflows/windows.yml)")
binaries = [(FFMPEG, ".")]

hiddenimports = [
    "flask", "jinja2", "werkzeug", "click", "itsdangerous", "markupsafe", "blinker",
    "mutagen", "mutagen.mp3", "mutagen.flac", "mutagen.id3", "mutagen.mp4", "mutagen.oggvorbis",
    "mutagen.wave", "mutagen.aiff",
    "numpy", "scipy", "scipy.signal", "scipy.io", "soundfile", "audioread",
    "pygame", "pygame.mixer", "pygame.locals",
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFilter",
    "openpyxl", "tqdm", "cryptography",
    # the window: pywebview with Microsoft Edge's WebView2 (through pythonnet)
    "webview", "webview.platforms.edgechromium", "webview.platforms.winforms", "clr", "clr_loader",
    "sqlite3", "urllib.request", "urllib.error", "urllib.parse", "ssl", "json", "xml.etree.ElementTree",
    "wave", "struct", "http.client", "email.utils", "secrets", "hashlib", "unicodedata", "ctypes.wintypes",
    "tkinter",
]
for pkg in ("librosa", "soundfile", "audioread", "numba", "llvmlite", "lazy_loader", "pooch", "soxr",
            "joblib", "scipy", "webview", "pythonnet", "clr_loader"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:
        print(f"[spec] collect_all({pkg!r}) skipped: {exc}")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["whisper", "torch", "torchaudio", "matplotlib", "IPython", "jupyter", "notebook", "AppKit", "objc"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Music Room",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                      # a window, no black console behind it
    icon=os.path.join(SPECPATH, "AppIcon.ico") if os.path.isfile(os.path.join(SPECPATH, "AppIcon.ico")) else None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="Music Room")
