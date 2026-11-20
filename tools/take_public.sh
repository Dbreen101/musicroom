#!/bin/bash
# tools/take_public.sh — bring a pull request you merged on GitHub into this
# working copy, so the next publish keeps it (and doesn't undo it).
#
#   tools/take_public.sh 12        take in pull request 12 (merged on the public repo)
#   tools/take_public.sh --sync    say "this copy already has everything on the public repo"
set -euo pipefail
cd "$(dirname "$0")/.."
PUBLIC="${MR_PUBLIC_REPO:-$HOME/Projects/musicroom}"
REPO="${MR_PUBLIC_GITHUB:-Dbreen101/musicroom}"
git -C "$PUBLIC" fetch -q origin
if [ "${1:-}" = "--sync" ]; then
  git config musicroom.publichead "$(git -C "$PUBLIC" rev-parse origin/main)"
  echo "Noted: this copy has everything on the public repo up to $(git -C "$PUBLIC" rev-parse --short origin/main)."
  exit 0
fi
N="${1:-}"; [[ "$N" =~ ^[0-9]+$ ]] || { echo "Which pull request? tools/take_public.sh <number>"; exit 1; }
STATE="$(gh pr view "$N" --repo "$REPO" --json state -q .state)"
[ "$STATE" = "MERGED" ] || { echo "Pull request $N isn't merged (it is $STATE). Merge it on GitHub first, or not at all."; exit 1; }
gh pr diff "$N" --repo "$REPO" | git apply --index --whitespace=nowarn
FILES="$(git diff --cached --name-only)"
git commit -q -m "Take in pull request $N from the public repo" -m "$(gh pr view "$N" --repo "$REPO" --json title,author -q '.title + " — by @" + .author.login')" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git config musicroom.publichead "$(git -C "$PUBLIC" rev-parse origin/main)"
echo "Taken in: pull request $N"
echo "$FILES" | sed 's/^/   /'
