"""
text_clean.py — small shared text-normalisation helpers.

Currently focused on stripping the meaningless "(Original Mix)" /
"(Original Version)" suffix that's a noise tag on most digital releases.
It's not on Spotify, MusicBrainz, Discogs, or iTunes — so leaving it on a
title means API lookups miss the real release.
"""

import re


# Matches every common encoding of an "Original Mix" suffix:
#   "Track (Original Mix)"     — parenthesised
#   "Track [Original Version]" — bracketed
#   "Track - Original Mix"     — dash-separated (en-dash and em-dash too)
#   "Track Original Mix"       — bare, at end of string only
# All case-insensitive. Other version tags (Album Version, Radio Edit,
# Extended Mix, Club Mix etc.) are NOT stripped — those carry actual
# meaning that distinguishes releases.
_MIX_SUFFIX_RE = re.compile(
    r"""
    \s*
    (?:
        [\(\[]\s*original\s+(?:mix|version)\s*[\)\]]      # (Original Mix) / [Original Version]
        | \s*[-–—]\s*original\s+(?:mix|version)\s*(?=$|\s) # - Original Mix
        | \s+original\s+(?:mix|version)\s*$               # bare " Original Mix"
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_mix_suffix(s):
    """Return s with any "Original Mix" / "Original Version" suffix removed.
    Idempotent. Empty/None input is returned unchanged."""
    if not s:
        return s
    out = _MIX_SUFFIX_RE.sub("", s).strip(" -–—\t")
    # Run again to absorb stacked tags like "Track (Original Mix) - Original Mix".
    out2 = _MIX_SUFFIX_RE.sub("", out).strip(" -–—\t")
    return out2 if out2 else out
