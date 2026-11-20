"""Proves find_audio_files is safe to point at a whole drive/laptop:
- a stray .als at the SCAN ROOT no longer nukes the whole scan (the 2026-06-02
  bug: a loose .als at the drive root made a whole-drive import find 0 files);
- real Ableton project folders (a .als in a SUBfolder) are still skipped;
- system/app-bundle/junk/other-library folders are skipped;
- ordinary music is found.

Run:  /opt/anaconda3/bin/python test_find_audio_files.py
"""
import os, sys, tempfile, shutil

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ); os.chdir(PROJ)
os.environ.setdefault("MUSICROOM_DATA", tempfile.mkdtemp(prefix="mr_faf_"))
import importer

TMP = tempfile.mkdtemp(prefix="mr_faf_tree_")
fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))
def touch(*parts):
    p = os.path.join(TMP, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").close()
    return p

# scan root holds a STRAY .als + a real song
touch("stray project.als")
touch("root song.mp3")
# ordinary album — one of each supported format
touch("Album", "track.flac")
touch("Album", "take.wav")
touch("Album", "demo.m4a")
# a REAL ableton project folder (deeper) — should be skipped wholesale
touch("MyProject", "myproject.als")
touch("MyProject", "bounce.mp3")
touch("MyProject", "Samples", "kick.flac")
# app bundle, other-app library, dev junk, hidden — all skipped
touch("SomeApp.app", "Contents", "audio.mp3")
touch("Photos.photoslibrary", "originals", "clip.mp3")
touch("node_modules", "pkg", "beep.mp3")
touch(".hidden", "secret.flac")

found = set(os.path.relpath(p, TMP) for p in importer.find_audio_files(TMP))
print("found:", sorted(found))

chk("root song.mp3" in found, "song beside a stray .als at the scan root IS found (root not nuked)")
chk(os.path.join("Album", "track.flac") in found, "ordinary album track is found")
chk(not any("MyProject" in f for f in found), "real Ableton project folder (deep .als) is skipped wholesale")
chk(not any(".app" in f for f in found), "app bundle (*.app) is skipped")
chk(not any("photoslibrary" in f for f in found), "other app's media library (*.photoslibrary) is skipped")
chk(not any("node_modules" in f for f in found), "node_modules is skipped")
chk(not any(".hidden" in f for f in found), "hidden folder is skipped")
chk(os.path.join("Album", "take.wav") in found, "a .wav track is found")
chk(os.path.join("Album", "demo.m4a") in found, "an .m4a track is found")
chk(len(found) == 4, f"exactly the 4 real music files found (got {len(found)})")

# the format filter restricts discovery to the chosen subset
only = set(os.path.relpath(p, TMP) for p in importer.find_audio_files(TMP, formats={".wav", ".m4a"}))
chk(only == {os.path.join("Album", "take.wav"), os.path.join("Album", "demo.m4a")},
    f"formats={{wav,m4a}} returns only those two (got {sorted(only)})")

shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULT:", "ALL PASS — whole-disk scan only grabs music; stray-root-.als bug fixed"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
