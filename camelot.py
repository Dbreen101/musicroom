"""Canonical Camelot ↔ musical-key map + key comparison.

One source of truth so the Music Room can compare ANY two key notations and know
if they're the same — e.g. a key fetched online as Camelot "8A" vs one written as
"A minor" vs "Am" vs "Abm" (A♭ minor). Everything reduces to (pitch-class 0–11,
mode) which is unambiguous; enharmonics (Db=C#, Gb=F#, …) collapse correctly.

Public:
    to_camelot(note, scale)   -> "8A" | None
    from_camelot(code)        -> ("A", "minor") | None
    parse_key(any_string)     -> {"pc","mode","note","scale","camelot"} | None
    keys_match(a, b)          -> bool   (a, b are any notation, incl. Camelot)
"""
import re

# Canonical sharp spelling for display (Camelot convention mixes these; for
# *comparison* only the pitch-class matters).
PC_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# pitch-class of each natural note
_NAT = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Camelot code for each (pitch-class, mode). Built from the wheel:
#   major (B): C=8B then +1 every perfect fifth; minor (A): A=8A, relative pairs share a number.
_CAMELOT = {}
for pc, code in {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}.items():
    _CAMELOT[(pc, "major")] = f"{code}B"
for pc, code in {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}.items():
    _CAMELOT[(pc, "minor")] = f"{code}A"
_BY_CAMELOT = {v: k for k, v in _CAMELOT.items()}


def to_camelot(note, scale):
    p = parse_key(f"{note or ''} {scale or ''}")
    return p["camelot"] if p else None


def from_camelot(code):
    p = parse_key(code)
    return (p["note"], p["scale"]) if p else None


def _parse_note(token):
    """A note name like 'A', 'C#', 'Db', 'B♭' -> pitch-class 0–11, or None."""
    if not token:
        return None
    t = token.strip().replace("♯", "#").replace("♭", "b")
    m = re.match(r"^([A-Ga-g])([#b]{0,2})$", t)
    if not m:
        return None
    pc = _NAT[m.group(1).upper()]
    for acc in m.group(2):
        pc += 1 if acc == "#" else -1
    return pc % 12


def parse_key(s):
    """Parse any key notation → canonical dict, or None.
    Accepts Camelot ('8A', '10b'), and letter keys ('A minor', 'Am', 'F# maj',
    'Gb major', 'C'). A bare note with no mode is treated as major."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None

    # Camelot: 1–12 + A/B
    cm = re.match(r"^\s*(1[0-2]|[1-9])\s*([ABab])\s*$", t)
    if cm:
        code = f"{int(cm.group(1))}{cm.group(2).upper()}"
        if code in _BY_CAMELOT:
            pc, mode = _BY_CAMELOT[code]
            return {"pc": pc, "mode": mode, "note": PC_SHARP[pc], "scale": mode, "camelot": code}
        return None

    # Letter key: note + optional accidentals + optional mode word
    lm = re.match(r"^\s*([A-Ga-g][#b♯♭]{0,2})\s*[-_ ]?\s*(.*)$", t)
    if not lm:
        return None
    pc = _parse_note(lm.group(1))
    if pc is None:
        return None
    rest = lm.group(2).strip().lower()
    if rest in ("m", "min", "mins", "minor", "moll"):
        mode = "minor"
    elif rest in ("", "maj", "major", "dur"):
        mode = "major"
    elif rest.startswith("min"):
        mode = "minor"
    elif rest.startswith("maj"):
        mode = "major"
    else:
        # trailing 'm' with no space, e.g. handled above; otherwise assume major
        mode = "major"
    return {"pc": pc, "mode": mode, "note": PC_SHARP[pc], "scale": mode,
            "camelot": _CAMELOT.get((pc, mode))}


def keys_match(a, b):
    """True if two key notations denote the same key (enharmonics + Camelot-aware)."""
    pa, pb = parse_key(a), parse_key(b)
    if not pa or not pb:
        return False
    return pa["pc"] == pb["pc"] and pa["mode"] == pb["mode"]
