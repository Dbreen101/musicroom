#!/bin/bash
# tools/server.sh — run the Music Room's rooms server on this Mac, and choose
# which release of it is running.
#
# The rooms server (gr_server.py) keeps everyone's accounts, the records for
# sale, the public rooms and grúpaí, record shopping, reports and feedback.
# It runs from a FOLDER OF ITS OWN, never from the code you are working on:
#
#   ~/MusicRoomServer/
#     releases/<tag>/        the code of each release, exactly as tagged
#     current -> releases/…  the one that is running
#     data/green_room.db     everything people have made (plus *_uploads, *_art, … beside it)
#     backups/               a copy of the database before every change of release
#     logs/server.log
#
# Usage (from the code folder):
#   tools/server.sh deploy v2026.11.20     put that release in place and (re)start it
#   tools/server.sh rollback v2026.11.20   the same, for an older release (the data stays as it is)
#   tools/server.sh rollback v… --with-data backups/<file>.db
#                                          …and put the database back as it was then (newer accounts,
#                                          records and reports since are lost — a copy is kept first)
#   tools/server.sh install                start it at login, and again if it ever stops (a LaunchAgent)
#   tools/server.sh uninstall              stop doing that
#   tools/server.sh start | stop | restart | status | log
#   tools/server.sh backup                 a copy of the database now
#   tools/server.sh master "Your Name"     make the master account (prints its code)
#   tools/server.sh address                the address the fellows' apps use
#   tools/server.sh releases               which releases are here, and which is running
#
# Releases come from the public repo's tags (MR_PUBLIC_REPO, default
# ~/Projects/musicroom). Nothing is ever deleted: old releases and backups stay.
set -euo pipefail

HOME_DIR="${MR_SERVER_HOME:-$HOME/MusicRoomServer}"
PUBLIC_REPO="${MR_PUBLIC_REPO:-$HOME/Projects/musicroom}"
PY="${MR_SERVER_PYTHON:-$HOME/Projects/music-room/venv/bin/python}"
PORT="${MR_SERVER_PORT:-5300}"
LABEL="com.musicroom.rooms-server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DB="$HOME_DIR/data/green_room.db"

say() { printf '%s\n' "$*"; }
die() { printf 'server.sh: %s\n' "$*" >&2; exit 1; }
running_tag() { [ -L "$HOME_DIR/current" ] && basename "$(readlink "$HOME_DIR/current")" || echo ""; }
installed() { [ -f "$PLIST" ]; }

prepare() { mkdir -p "$HOME_DIR/releases" "$HOME_DIR/data" "$HOME_DIR/backups" "$HOME_DIR/logs"; }

backup() {
  prepare
  [ -f "$DB" ] || { say "no database yet — nothing to back up"; return 0; }
  local tag; tag="$(running_tag)"; tag="${tag:-none}"
  local out="$HOME_DIR/backups/$(date +%Y-%m-%d_%H%M%S)-${tag}.db"
  "$PY" - "$DB" "$out" <<'PYEOF'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
    a.backup(b)                      # a consistent copy, even while the server runs
PYEOF
  say "database copied to $out"
}

fetch_release() {
  local tag="$1"
  [ -d "$PUBLIC_REPO/.git" ] || die "no public repo at $PUBLIC_REPO (set MR_PUBLIC_REPO)"
  git -C "$PUBLIC_REPO" fetch --tags --quiet origin 2>/dev/null || true
  git -C "$PUBLIC_REPO" rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "no release called $tag in $PUBLIC_REPO"
  local dest="$HOME_DIR/releases/$tag"
  if [ ! -d "$dest" ]; then
    mkdir -p "$dest.part"
    git -C "$PUBLIC_REPO" archive "refs/tags/$tag" | tar -x -C "$dest.part"
    mv "$dest.part" "$dest"
    say "release $tag unpacked to $dest"
  fi
}

write_plist() {
  mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-s</string>
    <string>$PY</string><string>$HOME_DIR/current/gr_server.py</string>
    <string>run</string><string>--host</string><string>0.0.0.0</string><string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$HOME_DIR/current</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>MR_GR_DB</key><string>$DB</string>
    <key>MR_LIBRARY_DB</key><string>$HOME_DIR/data/no-library.db</string>
    <key>PYTHONDONTWRITEBYTECODE</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$HOME_DIR/logs/server.log</string>
  <key>StandardErrorPath</key><string>$HOME_DIR/logs/server.log</string>
</dict>
</plist>
EOF
}

start() {
  [ -L "$HOME_DIR/current" ] || die "no release in place yet — tools/server.sh deploy <tag>"
  if installed; then
    launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl kickstart -k "gui/$(id -u)/$LABEL"
  else
    if [ -f "$HOME_DIR/server.pid" ] && kill -0 "$(cat "$HOME_DIR/server.pid")" 2>/dev/null; then say "already running"; return 0; fi
    ( cd "$HOME_DIR/current" && MR_GR_DB="$DB" MR_LIBRARY_DB="$HOME_DIR/data/no-library.db" PYTHONDONTWRITEBYTECODE=1 \
        nohup /usr/bin/caffeinate -s "$PY" gr_server.py run --host 0.0.0.0 --port "$PORT" >> "$HOME_DIR/logs/server.log" 2>&1 &
      echo $! > "$HOME_DIR/server.pid" )
  fi
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    curl -s -m 1 -o /dev/null "http://127.0.0.1:$PORT/api/version" && { say "the rooms server is running ($(running_tag)) on port $PORT"; return 0; }
    sleep 1
  done
  die "it didn't answer — see tools/server.sh log"
}

stop() {
  if installed; then launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true; fi
  if [ -f "$HOME_DIR/server.pid" ]; then kill "$(cat "$HOME_DIR/server.pid")" 2>/dev/null || true; rm -f "$HOME_DIR/server.pid"; fi
  say "stopped"
}

switch_to() {
  local tag="$1"
  prepare
  fetch_release "$tag"
  backup
  local was; was="$(running_tag)"
  stop >/dev/null || true
  ln -sfn "releases/$tag" "$HOME_DIR/current"
  [ -n "$was" ] && say "was $was → now $tag" || say "now $tag"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $was -> $tag" >> "$HOME_DIR/releases.log"
  if installed; then write_plist; fi
  start
}

cmd="${1:-status}"; shift || true
case "$cmd" in
  deploy|rollback)
    [ -n "${1:-}" ] || die "which release? e.g. tools/server.sh $cmd v2026.11.20"
    tag="$1"; shift
    if [ "${1:-}" = "--with-data" ]; then
      [ -f "${2:-}" ] || die "--with-data needs a backup file"
      restore="$2"
      switch_to "$tag"
      stop >/dev/null
      cp "$restore" "$DB"
      say "database put back from $restore (the one before it was copied to backups/ first)"
      start
    else
      switch_to "$tag"
    fi ;;
  install)   prepare; [ -L "$HOME_DIR/current" ] || die "deploy a release first"; stop >/dev/null || true; write_plist; start
             say "it now starts at login, and again by itself if it ever stops" ;;
  uninstall) stop; rm -f "$PLIST"; say "it no longer starts by itself" ;;
  start)     start ;;
  stop)      stop ;;
  restart)   stop >/dev/null; start ;;
  backup)    backup ;;
  log)       tail -n "${1:-60}" "$HOME_DIR/logs/server.log" ;;
  master)    [ -n "${1:-}" ] || die "a name, please: tools/server.sh master \"Your Name\""
             ( cd "$HOME_DIR/current" && MR_GR_DB="$DB" MR_LIBRARY_DB="$HOME_DIR/data/no-library.db" "$PY" gr_server.py master "$@" ) ;;
  releases)  ls -1 "$HOME_DIR/releases" 2>/dev/null | grep -v '\.part$' | while read -r r; do [ "$r" = "$(running_tag)" ] && echo "$r   ← running" || echo "$r"; done ;;
  address)   ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '?')"
             say "On this Wi-Fi:      http://$ip:$PORT"
             say "By this Mac's name: http://$(scutil --get LocalHostName 2>/dev/null).local:$PORT"
             say "(this Mac's own app uses http://127.0.0.1:$PORT — the master page answers only there)" ;;
  status)    tag="$(running_tag)"
             if curl -s -m 1 -o /dev/null "http://127.0.0.1:$PORT/api/version"; then say "running · release ${tag:-?} · port $PORT"; else say "not running · release in place: ${tag:-none}"; fi
             installed && say "starts at login: yes" || say "starts at login: no (tools/server.sh install)" ;;
  *) sed -n '2,32p' "$0"; exit 1 ;;
esac
