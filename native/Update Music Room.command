#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  Music Room — one-click update.
#
#  Double-click this file. It closes Music Room, swaps in the new
#  version sitting next to this file, and opens it again.
#
#  Your music, notes, tags and sets are NOT touched — they live in
#  their own folder outside the app, and updating never goes near it.
# ─────────────────────────────────────────────────────────────────
cd "$(dirname "$0")"
echo ""
echo "  Updating Music Room…"

NEW="$PWD/Music Room.app"
if [ ! -d "$NEW" ]; then
  echo "  ✗ Couldn't find the new Music Room.app next to this file."
  echo "    Keep this file inside the update folder and try again."
  read -r -p "  (press return to close)"; exit 1
fi

# close the running app gently
osascript -e 'tell application "Music Room" to quit' >/dev/null 2>&1
sleep 2

# find the installed copy (never the new one we're holding)
TARGET=""
while IFS= read -r cand; do
  [ "$cand" = "$NEW" ] && continue
  case "$cand" in "$PWD"/*) continue;; esac
  TARGET="$cand"; break
done < <(mdfind 'kMDItemCFBundleIdentifier == "com.daithi.musicroom"' 2>/dev/null)
if [ -z "$TARGET" ]; then
  for c in "/Applications/Music Room.app" "$HOME/Applications/Music Room.app" "$HOME/Desktop/Music Room.app"; do
    [ -d "$c" ] && TARGET="$c" && break
  done
fi
if [ -z "$TARGET" ]; then
  TARGET="/Applications/Music Room.app"
  echo "  No existing copy found — installing fresh to Applications."
fi

echo "  Replacing: $TARGET"
rm -rf "$TARGET"
ditto "$NEW" "$TARGET"
# clear the "downloaded from the internet" flag so it opens without the
# security warning — you already approved Music Room once
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null

echo "  ✓ Updated. Opening Music Room…"
open "$TARGET"
echo ""
echo "  Everything you've built — music, notes, sets — is exactly as you left it."
sleep 3
