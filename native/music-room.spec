# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the distributable Music Room .app.

Self-contained: bundles Python, every dependency, AND the Music Room source
(into mrsrc/) so it runs on a machine that has never seen the project. The
launcher points the app at a per-user data folder (~/Library/Application
Support/Music Room) for the database + uploaded media, so each person gets a
clean install and the developer's personal library is never shipped.

Build:   cd native && ../venv/bin/pyinstaller music-room.spec --clean --noconfirm
Output:  native/dist/Music Room.app
"""
import os
import glob
from PyInstaller.utils.hooks import collect_all

PROJ = os.path.dirname(SPECPATH)            # the project root (native/ is the spec dir)

block_cipher = None

# --- bundle the Music Room source as data (loaded at runtime from mrsrc/) ---
# Only CODE assets — never the developer's personal data (library.db,
# moodboard/ambient/artwork/stickers/overlays, voice_notes, exports).
datas = []

for py in glob.glob(os.path.join(PROJ, "*.py")):
    datas.append((py, "mrsrc"))

# Baked tester-build config (feedback endpoint) — gitignored; optional.
# (MR_BAKED_ENV points at another one — tools/release.sh writes the Green Room's;
#  it must be called baked_env.py, which is what the launcher imports)
BAKED = os.environ.get("MR_BAKED_ENV") or os.path.join(SPECPATH, "baked_env.py")
if os.path.isfile(BAKED):
    if os.path.basename(BAKED) != "baked_env.py":
        raise SystemExit("[spec] MR_BAKED_ENV must point at a file called baked_env.py")
    datas.append((BAKED, "mrsrc"))
    print("[spec] baking native/baked_env.py into the bundle")
else:
    print("[spec] no baked_env.py — building without a baked feedback endpoint")

# the plug-ins that come with the app, the version and the house rules (2026-11-20)
for root, _dirs, files in os.walk(os.path.join(PROJ, "plugins")):
    for fn in files:
        if not fn.startswith("."):
            datas.append((os.path.join(root, fn), os.path.join("mrsrc", os.path.relpath(root, PROJ))))
for fn in ("VERSION", "HOUSE_RULES.md"):
    if os.path.isfile(os.path.join(PROJ, fn)):
        datas.append((os.path.join(PROJ, fn), "mrsrc"))

for root, _dirs, files in os.walk(os.path.join(PROJ, "templates")):
    for fn in files:
        if fn.startswith("."):
            continue
        full = os.path.join(root, fn)
        rel  = os.path.relpath(root, PROJ)        # e.g. "templates"
        datas.append((full, os.path.join("mrsrc", rel)))

STATIC_CODE = ["css", "js", "textures", "fonts", "vendor", "data"]   # NOT moodboard/ambient/artwork/etc.
for sub in STATIC_CODE:
    base = os.path.join(PROJ, "static", sub)
    if not os.path.isdir(base):
        continue
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if fn.startswith("."):
                continue
            full = os.path.join(root, fn)
            rel  = os.path.relpath(root, PROJ)     # e.g. "static/css"
            datas.append((full, os.path.join("mrsrc", rel)))

# --- bundle a static ffmpeg (m4a playback + analysis on a clean Mac) --------
# build.sh stages it to native/bin/ffmpeg from the venv's imageio-ffmpeg
# (build-intel.sh stages the x86_64 one and points MR_FFMPEG_STAGED at it).
# mr_ffmpeg.ffmpeg_path() finds it at sys._MEIPASS/ffmpeg at runtime.
FFMPEG_BIN = os.environ.get("MR_FFMPEG_STAGED") or os.path.join(SPECPATH, "bin", "ffmpeg")
if not os.path.isfile(FFMPEG_BIN):
    raise SystemExit(
        "[spec] native/bin/ffmpeg is missing — run ./native/build.sh (it stages "
        "the static binary from the venv's imageio-ffmpeg). Refusing to build a "
        "bundle where m4a playback/analysis silently breaks.")

# --- pull in data files for the heavy science libs --------------------------
binaries = [(FFMPEG_BIN, ".")]
hiddenimports = [
    # Flask stack
    "flask", "jinja2", "werkzeug", "click", "itsdangerous", "markupsafe",
    "blinker",
    # Audio tags
    "mutagen", "mutagen.mp3", "mutagen.flac", "mutagen.id3", "mutagen.mp4",
    "mutagen.oggvorbis", "mutagen.wave", "mutagen.aiff",
    # Analysis
    "numpy", "scipy", "scipy.signal", "scipy.io", "soundfile", "audioread",
    "pkg_resources",
    # Playback
    "pygame", "pygame.mixer", "pygame.locals",
    # Images / textures
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFilter",
    # Spreadsheet export (openpyxl) + progress bars (tqdm)
    "openpyxl", "tqdm",
    # pywebview + macOS bridge
    "webview", "webview.platforms.cocoa", "objc",
    "AppKit", "Foundation", "WebKit", "PyObjCTools", "PyObjCTools.AppHelper",
    # stdlib stragglers PyInstaller sometimes drops
    "sqlite3", "urllib.request", "urllib.error", "urllib.parse",
    "ssl", "json", "xml.etree.ElementTree", "wave", "struct",
    "http.client", "email.utils", "secrets", "hashlib", "unicodedata",
]

for pkg in ("librosa", "soundfile", "audioread", "numba", "llvmlite",
            "lazy_loader", "pooch", "soxr", "joblib", "scipy"):
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
    excludes=[
        # Voice-note transcription (huge); falls back to "not configured".
        "whisper", "torch", "torchaudio",
        "matplotlib", "tkinter", "IPython", "jupyter", "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="music-room",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="music-room",
)

app = BUNDLE(
    coll,
    name="Music Room.app",
    icon="AppIcon.icns",
    bundle_identifier="com.daithi.musicroom",
    version="0.3",
    info_plist={
        "CFBundleName":               "Music Room",
        "CFBundleDisplayName":        "Music Room",
        "CFBundleIdentifier":         "com.daithi.musicroom",
        "CFBundleVersion":            "0.3",
        "CFBundleShortVersionString": "0.3",
        "CFBundlePackageType":        "APPL",
        "CFBundleExecutable":         "music-room",
        "LSMinimumSystemVersion":     "11.0",
        "NSHighResolutionCapable":    True,
        "LSUIElement":                False,
        "NSMicrophoneUsageDescription":
            "Music Room records voice notes you attach to tracks.",
        "NSBluetoothAlwaysUsageDescription":
            "Music Room connects to a Bluetooth speaker when you pick one in the player.",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
