#!/bin/bash
# run_gr.sh — run the Music Room from its code, as the Green Room's fellows use it.
#
#   ./run_gr.sh                                   uses the server address below
#   MR_GR_SERVER=http://192.168.1.20:5300 ./run_gr.sh
#
# First time only:  python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# (Python 3.11 or 3.12. Everything else — ffmpeg too — comes from requirements.txt.)
#
# Your own library, settings and records live in
#   ~/Library/Application Support/Music Room GR/
# never inside this code folder, so you can change the code (or pull a new
# release) without touching them.
cd "$(dirname "$0")" || exit 1
[ -x venv/bin/python ] || { echo "First: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"; exit 1; }
export MUSICROOM_3D=1
export MR_GREEN_ROOM=1
export MR_GR_VERSION=GR1
export MR_GR_SERVER="${MR_GR_SERVER:-http://Davids-MacBook-Pro-2.local:5300}"
export MUSICROOM_DATA="${MUSICROOM_DATA:-$HOME/Library/Application Support/Music Room GR}"
export MUSICROOM_PORT="${MUSICROOM_PORT:-5177}"
mkdir -p "$MUSICROOM_DATA"
exec venv/bin/python desktop.py
