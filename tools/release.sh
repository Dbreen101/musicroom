#!/bin/bash
# tools/release.sh — make a RELEASE of the Music Room: everything approved so far,
# under one name, with the two ready-made apps, kept for good.
#
#   tools/release.sh v2026.11.21 "what changed, in a line"
#   tools/release.sh v2026.11.21 "…" --no-build      (the code and its tag only; no apps)
#
# What it does, in order (it stops at the first thing that goes wrong):
#   1. writes the version (2026.11.21) into VERSION and commits it here
#   2. publishes the code to the public repo (tools/publish_public.py — nothing private goes)
#   3. tags the public repo (v2026.11.21) and this repo (gr-v2026.11.21)
#   4. builds the app for Apple Silicon and for Intel, with the rooms server's
#      address and the Green Room switched on, keeping its data in its own folder
#   5. puts both on the release's page on GitHub
# Then: tools/server.sh deploy <tag>, and name it on the master page → Version.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:-}"; NOTE="${2:-}"; BUILD=1
[ "${3:-}" = "--no-build" ] && BUILD=0
[[ "$TAG" =~ ^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}(-[0-9]+)?$ ]] || { echo "A release is called vYYYY.MM.DD (or vYYYY.MM.DD-2 …)"; exit 1; }
[ -n "$NOTE" ] || { echo "Say what changed, in a line."; exit 1; }
PUBLIC="${MR_PUBLIC_REPO:-$HOME/Projects/musicroom}"
REPO="${MR_PUBLIC_GITHUB:-Dbreen101/musicroom}"
SERVER="${MR_GR_SERVER_FOR_BUILD:-http://$(scutil --get LocalHostName).local:5300}"

git -C "$PUBLIC" rev-parse -q --verify "refs/tags/$TAG" >/dev/null && { echo "There is already a release called $TAG."; exit 1; }
# both repos must commit (and tag) as your own GitHub account — asked of GitHub, never guessed
python3 tools/publish_public.py --check-identity || exit 1

echo "── 1. the version"
printf '%s\n' "${TAG#v}" > VERSION
git add VERSION
git commit -q -m "Release $TAG: $NOTE" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" || true

echo "── 2. publishing the code"
python3 tools/publish_public.py -m "Release $TAG: $NOTE" --push

echo "── 3. tags"
git -C "$PUBLIC" tag -a "$TAG" -m "$NOTE"
git -C "$PUBLIC" push -q origin "$TAG"
git tag -a "gr-$TAG" -m "$NOTE"
git push -q origin "gr-$TAG" || echo "   (this repo's tag stays here; push it later with: git push origin gr-$TAG)"

ASSETS=()
if [ "$BUILD" = 1 ]; then
  echo "── 4. building the apps (a few minutes each)"
  BAKE="$(mktemp -d)"
  cat > "$BAKE/baked_env.py" <<PY
# baked into the Green Room release $TAG by tools/release.sh
MR_GREEN_ROOM = "1"
MR_GR_VERSION = "GR1"
MR_GR_SERVER = "$SERVER"
MR_DATA_NAME = "Music Room GR"
PY
  OUT="$(mktemp -d)/$TAG"; mkdir -p "$OUT"
  MR_BAKED_ENV="$BAKE/baked_env.py" ./native/build.sh
  ditto -c -k --sequesterRsrc --keepParent "native/dist/Music Room GR.app" "$OUT/Music Room GR (Apple Silicon).zip"
  if [ -x native/build-intel.sh ] && [ -d native/pyx86 ]; then
    MR_BAKED_ENV="$BAKE/baked_env.py" ./native/build-intel.sh
    ditto -c -k --sequesterRsrc --keepParent "native/dist-intel/Music Room GR.app" "$OUT/Music Room GR (Intel).zip"
  else
    echo "   (no Intel build here — native/pyx86 is missing; the release has the Apple Silicon app only)"
  fi
  cp "native/Read me first (GR).txt" "$OUT/Read me first.txt"
  ASSETS=("$OUT"/*)
  rm -rf "$BAKE"
fi

echo "── 5. the release page"
NOTES="$NOTE

**Mac**: download the zip for your Mac (Apple Silicon for Macs from late 2020 on; Intel for older ones), unzip, drag *Music Room GR* to Applications, open. The first time, macOS stops it: System Settings → Privacy & Security → Open Anyway.

**Windows PC**: download *Music Room GR (Windows).zip* (it arrives a few minutes after the Mac ones), unzip, open the Music Room GR folder, double-click Music Room GR.exe. The first time Windows may say it protected your PC: More info → Run anyway.

**From the code**: \`git checkout $TAG\`, then \`./run_gr.sh\` (Mac) or \`run_gr.bat\` (Windows)."
# (GitHub's Windows build may have made the page already: then add to it)
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release edit "$TAG" --repo "$REPO" --title "The Music Room $TAG" --notes "$NOTES"
  [ ${#ASSETS[@]} -gt 0 ] && gh release upload "$TAG" --repo "$REPO" --clobber "${ASSETS[@]}"
else
  gh release create "$TAG" --repo "$REPO" --title "The Music Room $TAG" --notes "$NOTES" "${ASSETS[@]}"
fi
echo "   The Windows app is being built on GitHub's machines: https://github.com/$REPO/actions"
URL="https://github.com/$REPO/releases/tag/$TAG"
echo ""
echo "Released: $URL"
echo "Next:  tools/server.sh deploy $TAG"
echo "Then:  master page → Version → ${TAG#v}, and paste $URL"
