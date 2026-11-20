#!/bin/bash
# Music Room — build the native macOS .app bundle.
# Safe to run anytime; does NOT touch the rest of the project. Clean rebuild
# of native/dist/Music Room.app from the current venv + source.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x "../venv/bin/pyinstaller" ]; then
  echo "PyInstaller not found in the project venv — install it first:"
  echo "  ../venv/bin/pip install pyinstaller"
  exit 1
fi

# Stage the static ffmpeg the bundle ships (a clean Mac has none — without it
# m4a won't play and m4a/FLAC get no analysis). Source: the venv's
# imageio-ffmpeg wheel (PyPI static build; arm64, includes libvorbis).
mkdir -p bin
FFSRC="$(../venv/bin/python -c 'import imageio_ffmpeg,sys; sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)"
if [ -z "$FFSRC" ] || [ ! -f "$FFSRC" ]; then
  echo "imageio-ffmpeg not found in the venv — install it first:"
  echo "  ../venv/bin/pip install imageio-ffmpeg"
  exit 1
fi
cp -f "$FFSRC" bin/ffmpeg
chmod +x bin/ffmpeg
echo "Staged ffmpeg: $(bin/ffmpeg -version 2>/dev/null | head -1)"

echo "============================================================="
echo "  Building Music Room.app"
echo "============================================================="

../venv/bin/pyinstaller music-room.spec --clean --noconfirm \
    --distpath dist --workpath build

# Ship the install instructions next to the app (dist/ is gitignored;
# the tracked source is native/Read me first.txt).
cp -f "Read me first.txt" dist/

echo ""
echo "============================================================="
echo "  Built: $(pwd)/dist/Music Room.app"
du -sh "dist/Music Room.app" 2>/dev/null | awk '{print "  Size:  " $1}'
echo "============================================================="
echo ""
echo "  Drag it to /Applications, or run:"
echo "    open \"$(pwd)/dist/Music Room.app\""
echo ""
