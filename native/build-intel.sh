#!/bin/bash
# Music Room — build the INTEL (x86_64) macOS .app, for testers on Intel Macs.
#
# Runs the whole PyInstaller build under Rosetta with the x86_64 toolchain:
#   native/pyx86/python  — standalone x86_64 CPython (astral-sh
#                          python-build-standalone, checksum-verified)
#   venv-x86/            — x86_64 venv with the same requirements.txt
# Output: native/dist-intel/Music Room.app (+ stage the zip yourself or let
# this script do it). The arm64 build (build.sh) is untouched.
set -euo pipefail

cd "$(dirname "$0")"

if ! arch -x86_64 /usr/bin/true 2>/dev/null; then
  echo "Rosetta 2 isn't installed — run: softwareupdate --install-rosetta"
  exit 1
fi
if [ ! -x "../venv-x86/bin/pyinstaller" ]; then
  echo "The x86_64 venv isn't ready — create it first:"
  echo "  arch -x86_64 native/pyx86/python/bin/python3.12 -m venv venv-x86"
  echo "  arch -x86_64 venv-x86/bin/pip install -r requirements.txt pyinstaller"
  exit 1
fi

echo "============================================================="
echo "  Building Music Room.app  (Intel / x86_64, via Rosetta)"
echo "============================================================="

# Stage the x86_64 static ffmpeg from the x86 venv's imageio-ffmpeg wheel.
mkdir -p bin-x86
FFSRC="$(arch -x86_64 ../venv-x86/bin/python -c 'import imageio_ffmpeg,sys; sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)"
if [ -z "$FFSRC" ] || [ ! -f "$FFSRC" ]; then
  echo "imageio-ffmpeg not found in venv-x86 — install it first:"
  echo "  arch -x86_64 ../venv-x86/bin/pip install imageio-ffmpeg"
  exit 1
fi
cp -f "$FFSRC" bin-x86/ffmpeg
chmod +x bin-x86/ffmpeg
echo "Staged ffmpeg ($(file -b bin-x86/ffmpeg | grep -o 'x86_64' || echo '?')): $(arch -x86_64 bin-x86/ffmpeg -version 2>/dev/null | head -1)"

MR_FFMPEG_STAGED="$(pwd)/bin-x86/ffmpeg" \
  arch -x86_64 ../venv-x86/bin/pyinstaller music-room.spec --clean --noconfirm \
    --distpath dist-intel --workpath build-intel

cp -f "Read me first.txt" dist-intel/

echo ""
echo "============================================================="
echo "  Built: $(pwd)/dist-intel/Music Room.app  (x86_64)"
du -sh "dist-intel/Music Room.app" 2>/dev/null | awk '{print "  Size:  " $1}'
lipo -archs "dist-intel/Music Room.app/Contents/MacOS/music-room" 2>/dev/null | awk '{print "  Arch:  " $0}'
echo "============================================================="
