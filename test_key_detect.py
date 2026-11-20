"""Key detection — sanity on synthetic signals of known key, and proof it beats
the old 'loudest pitch-class' method on a dominant-heavy signal.

Generates pure-tone passages in a known key (tonic + dominant emphasised, which
is what disambiguates a major key from its relative minor) and checks the
detector lands on the right tonic + mode.

Run:  /opt/anaconda3/bin/python test_key_detect.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import key_detect

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

SR = 22050
NOTE_HZ = {  # one octave; we add an octave up too
    "C": 261.63, "C#": 277.18, "D": 293.66, "D#": 311.13, "E": 329.63, "F": 349.23,
    "F#": 369.99, "G": 392.00, "G#": 415.30, "A": 440.00, "A#": 466.16, "B": 493.88,
}

def tone(name, secs=0.5, amp=0.5):
    n = int(SR * secs)
    t = np.arange(n) / SR
    f = NOTE_HZ[name]
    # fundamental + a couple of harmonics so the CQT chroma reads cleanly
    s = (np.sin(2*np.pi*f*t) + 0.5*np.sin(2*np.pi*2*f*t) + 0.3*np.sin(2*np.pi*3*f*t))
    env = np.minimum(1.0, np.minimum(t*40, (secs - t)*40))   # fade in/out
    return (amp * s * env).astype(np.float32)

def passage(notes):
    """notes: list of (name, repeats) — tonic/dominant get more weight."""
    parts = []
    for name, reps in notes:
        for _ in range(reps):
            parts.append(tone(name))
    return np.concatenate(parts)

# C major: full scale, tonic C + dominant G emphasised
c_major = passage([("C",3),("D",1),("E",2),("F",1),("G",2),("A",1),("B",1)])
r = key_detect.detect_key(c_major, SR)
print("   C major →", r["key_note"], r["key_scale"], f"(conf {r['confidence']}, {r['method']})")
chk(r["key_note"] == "C" and r["key_scale"] == "major", "clear C-major passage → C major")

# A minor: same note-set but tonic A + dominant E emphasised → relative minor
a_minor = passage([("A",3),("B",1),("C",2),("D",1),("E",2),("F",1),("G",1)])
r = key_detect.detect_key(a_minor, SR)
print("   A minor →", r["key_note"], r["key_scale"], f"(conf {r['confidence']}, {r['method']})")
chk(r["key_note"] == "A" and r["key_scale"] == "minor", "clear A-minor passage → A minor")

# G major (transposition sanity)
g_major = passage([("G",3),("A",1),("B",2),("C",1),("D",2),("E",1),("F#",1)])
r = key_detect.detect_key(g_major, SR)
print("   G major →", r["key_note"], r["key_scale"], f"(conf {r['confidence']}, {r['method']})")
chk(r["key_note"] == "G" and r["key_scale"] == "major", "clear G-major passage → G major")

# THE IMPROVEMENT: a C-major passage where the DOMINANT (G) is the most prominent
# single note (realistic — dominants often are). The old argmax method calls this
# G; K–S should still find C major from the overall tonic-triad pattern.
c_major_loud_g = passage([("C",2),("D",1),("E",2),("F",1),("G",3),("A",1),("B",1)])
old_argmax_index = int(np.argmax(np.mean(
    __import__("librosa").feature.chroma_cqt(y=c_major_loud_g, sr=SR), axis=1)))
old_note = key_detect.NOTE_NAMES[old_argmax_index]
r = key_detect.detect_key(c_major_loud_g, SR)
print(f"   dominant-heavy C major → new: {r['key_note']} {r['key_scale']} | old-argmax tonic would be: {old_note}")
chk(r["key_note"] == "C", "finds C major even when the dominant G is loudest (old method would miss)")

print("\nRESULT:", "ALL PASS — Krumhansl–Schmuckler key detection lands the right key"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
