"""Camelot ↔ key map + cross-notation comparison."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camelot

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# canonical wheel anchors
chk(camelot.to_camelot("A", "minor") == "8A", "A minor → 8A")
chk(camelot.to_camelot("C", "major") == "8B", "C major → 8B")
chk(camelot.to_camelot("E", "major") == "12B", "E major → 12B")
chk(camelot.to_camelot("D", "minor") == "7A", "D minor → 7A")
chk(camelot.from_camelot("8A") == ("A", "minor"), "8A → A minor")
chk(camelot.from_camelot("3B") == ("C#", "major"), "3B → C#/Db major")

# enharmonics collapse
chk(camelot.to_camelot("Db", "major") == camelot.to_camelot("C#", "major") == "3B", "Db major == C# major == 3B")
chk(camelot.to_camelot("Gb", "minor") == camelot.to_camelot("F#", "minor") == "11A", "Gb minor == F# minor == 11A")
chk(camelot.to_camelot("Ab", "minor") == "1A", "Ab minor → 1A")
chk(camelot.to_camelot("Bb", "minor") == "3A", "Bb minor (A# minor) → 3A")

# THE KEY ASK: compare a fetched Camelot vs a fetched letter key
chk(camelot.keys_match("8A", "A minor"), "Camelot 8A matches 'A minor'")
chk(camelot.keys_match("8A", "Am"), "8A matches 'Am'")
chk(camelot.keys_match("3B", "Db major"), "3B matches 'Db major'")
chk(camelot.keys_match("3B", "C# major"), "3B matches 'C# major' (enharmonic)")
chk(camelot.keys_match("F# minor", "Gb min"), "'F# minor' matches 'Gb min'")
chk(camelot.keys_match("A minor", "A major") is False, "A minor ≠ A major")
chk(camelot.keys_match("8A", "8B") is False, "8A ≠ 8B")
chk(camelot.keys_match("C", "C major"), "bare 'C' == 'C major'")
chk(camelot.keys_match("Am", "8a"), "'Am' matches lowercase camelot '8a'")

# garbage in → no false match
chk(camelot.parse_key("") is None and camelot.parse_key("xyz") is None, "garbage parses to None")
chk(camelot.keys_match("", "A minor") is False, "empty never matches")

# every pitch-class round-trips both modes
ok = all(camelot.from_camelot(camelot.to_camelot(camelot.PC_SHARP[pc], mode)) is not None
         for pc in range(12) for mode in ("major", "minor"))
chk(ok, "all 24 keys round-trip note→camelot→note")

print("\nRESULT:", "ALL PASS — one canonical Camelot↔key map; any notation compares correctly"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
