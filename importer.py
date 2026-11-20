"""
=============================================================
MUSIC ROOM — importer.py
=============================================================
What this file does:
    Scans a folder for MP3 and FLAC files, extracts metadata
    and writes everything to the database.

    TWO MODES:

        Fast (default) — metadata only:
            Reads tags already embedded in each file.
            Artist, title, album, year, duration, bitrate.
            No audio decoding. ~3 tracks/second.
            Use this for all imports.

            python3 importer.py --path "/path/to/music"

        Full — metadata + audio analysis:
            Also runs librosa on each track.
            BPM, key, frequency bands, loudness etc.
            ~5-15 seconds per track. Run selectively
            or overnight on tracks you care about.

            python3 importer.py --path "/path/to/music" --analyse

        Analyse missing — run analysis on already-imported
        tracks that have no analysis data yet:

            python3 importer.py --analyse-missing

    Duplicate detection:
        1. Exact file path — skipped entirely (already imported)
        2. Same artist + title — new file linked to existing
           track rather than creating a new duplicate track
        3. No artist AND no title — imported but flagged
           needs_review = 1 so you can find them in the tool

    Metadata extraction strategy:
        1. mutagen easy=True — normalised tags (most reliable)
        2. Raw ID3 frames — fallback for non-standard tags
           e.g. TPE1 (artist), TIT2 (title), TPE2 (album artist)
        3. Filename parsing — last resort for files with no tags
           Handles "Artist - Title.mp3" and "01 - Artist - Title.mp3"

    Safe to re-run:
        Already-imported files are always skipped.
        Notes, tags, and placements are never overwritten.

How to run:
    source venv/bin/activate
    python3 importer.py --path "/Volumes/EXTERNAL HARD DRIVE 1/MUSIC"
=============================================================
"""

import os
import re
import sys
import sqlite3
import argparse

from mutagen import File as MutagenFile
from tqdm import tqdm


# =============================================================
# CONFIGURATION
# =============================================================

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
from mr_paths import DB_PATH, DATA_DIR  # noqa: E402  (shared data dir; see mr_paths.py)
# Just a fallback when no --path is given; the GUI always passes one (from
# the Music library setting). Overridable via env for headless use.
DEFAULT_SCAN_PATH = os.environ.get(
    "MUSICROOM_LIBRARY_PATH",
    "/Volumes/EXTERNAL HARD DRIVE 1",
)

# Formats to import.
# Edit this list to add or remove formats.
# Future versions will let you set this in the interface.
# .asd (Ableton analysis cache) and all other formats ignored.
AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
}


def true_container_format(path):
    """The real container by magic bytes → a canonical format string, falling
    back to the extension. Some files lie about their format (a YouTube/DASH
    MP4+AAC rip saved as ".mp3", or an MP3 saved as ".flac"); storing the TRUE
    container keeps the format badge, the format filter, analysis routing and
    exports honest, even when the filename doesn't."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except Exception:
        return ext
    if head[4:8] == b"ftyp":                                            return "m4a"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3",
                                          b"\xff\xf2", b"\xff\xfa"):    return "mp3"
    if head[:4] == b"fLaC":                                             return "flac"
    if head[:4] == b"OggS":                                             return "ogg"
    if head[:4] == b"RIFF":                                             return "wav"
    return ext

# v19 — perceptual 6-band split (sub / bass / low-mid / body / presence / brilliance).
# Presence (2–5 kHz) is where vocal formants live; its prominence is the
# strongest single signal for vocal-dominant tracks.
PERCEPTUAL_BANDS = [
    ("band_sub",        20,    60),
    ("band_bass",       60,   250),
    ("band_lowmid",    250,   500),
    ("band_body",      500,  2000),
    ("band_presence", 2000,  5000),
    ("band_brilliance", 5000, 11025),
]


def _a_weighting_db(f):
    """IEC 61672 A-weighting in dB at frequency f (Hz). Numpy-vectorised."""
    import numpy as np
    f = np.asarray(f, dtype=float)
    f2 = f * f
    num = (12200.0 ** 2) * (f2 ** 2)
    den = (f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12200.0 ** 2)
    # Avoid log(0) at DC
    ra = np.where(den > 0, num / den, 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 2.0 + 20.0 * np.log10(np.maximum(ra, 1e-12))


def _compute_band_fingerprint(stft_mag, freqs):
    """Given an STFT magnitude (bins x frames) and bin frequencies, returns
    A-weighted band loudness in dB per perceptual band, plus a vocal_score.

    Each band value is dB above an internal reference (relative — but
    comparable between tracks because the reference is fixed). Returned
    values typically range from ~-90 (silent) to ~-10 (very loud).
    """
    import numpy as np

    # A-weighting per bin (dB → linear power scale)
    a_db   = _a_weighting_db(freqs)
    a_lin2 = 10.0 ** (a_db / 10.0)  # power scale

    # Mean *power* per bin across frames (time-averaged), then A-weight
    power_per_bin = np.mean(stft_mag.astype(np.float64) ** 2, axis=1)
    weighted_per_bin = power_per_bin * a_lin2

    bin_width = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0

    out = {}
    band_dbs = {}
    for name, fmin, fmax in PERCEPTUAL_BANDS:
        mask = (freqs >= fmin) & (freqs < fmax)
        if not np.any(mask):
            out[name] = None
            continue
        # Integrate weighted power across the band (sum × bin width)
        band_power = float(np.sum(weighted_per_bin[mask]) * bin_width)
        # dB; floor protects against silent files
        db = 10.0 * np.log10(max(band_power, 1e-12))
        out[name] = round(db, 2)
        band_dbs[name] = db

    # (vocal_score removed — the heuristic didn't discriminate reliably)
    return out


# =============================================================
# DATABASE HELPERS
# =============================================================

def get_connection():
    """Opens and returns a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def file_already_exists(cursor, file_path):
    """
    Returns True if this file path is already in the files table.
    Prevents re-importing files already in the database.

    Path comparison is CASE-INSENSITIVE (COLLATE NOCASE). macOS volumes are
    case-insensitive, and the external drive mounts inconsistently as
    /Volumes/... or /volumes/... — a case-sensitive '=' missed those, so a
    file already in the library looked brand-new and could be re-processed or
    (with dup-policy=delete) trashed as a "duplicate" of itself. NOCASE makes
    a different-case path resolve to the existing row.
    """
    cursor.execute(
        "SELECT id FROM files WHERE file_path = ? COLLATE NOCASE AND is_deleted = 0",
        (file_path,),
    )
    return cursor.fetchone() is not None


def _same_physical_file(a, b):
    """True if two paths point at the SAME file on disk. Uses inode identity
    (os.path.samefile) when both exist; otherwise a case-insensitive path
    compare (macOS volumes are case-insensitive, so /Volumes == /volumes and
    File.mp3 == file.mp3). Guards against ever trashing the library's own file."""
    if not a or not b:
        return False
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normpath(a).lower() == os.path.normpath(b).lower()


def file_content_hash(path, _bufsize=1024 * 1024):
    """SHA-256 of the file's raw bytes — the definitive 'these are literally
    the same file' signal. Streamed in chunks so a big FLAC won't blow memory.
    Returns None if the file can't be read."""
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_bufsize), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _approx(a, b, tol):
    if a is None or b is None:
        return a == b
    try:
        return abs(a - b) <= tol
    except TypeError:
        return a == b


def find_duplicate_file(cursor, file_path, meta):
    """Is this file a byte-for-byte copy of one already in the library?

    Robust AND conservative: we only ever call something a duplicate when the
    files are **byte-identical** (same SHA-256). To stay fast we don't hash
    everything — we first cheaply shortlist existing files that share the same
    format, size, duration, bitrate and sample-rate, and only hash those
    candidates (+ the incoming file). No candidate → no hashing → not a dup.
    A re-tagged or re-encoded copy (different bytes) is NOT treated as a dup,
    so genuine alternate versions are always kept.

    Returns (existing_match_or_None, incoming_hash_or_None). The hash is
    returned (when computed) so the caller can store it on the new file.
    """
    fmt  = meta.get("file_format")
    size = meta.get("file_size_mb")
    dur  = meta.get("duration_sec")
    br   = meta.get("bitrate_kbps")
    sr   = meta.get("sample_rate")

    rows = cursor.execute(
        """
        SELECT id, track_id, file_path, content_hash, bitrate_kbps, sample_rate
        FROM files
        WHERE is_deleted = 0
          AND file_format IS ?
          AND ABS(COALESCE(file_size_mb, -999) - COALESCE(?, -1)) < 0.02
          AND ABS(COALESCE(duration_sec,  -999) - COALESCE(?, -1)) < 1.0
        """,
        (fmt, size, dur),
    ).fetchall()

    candidates = [
        (fid, tid, fp, chash)
        for (fid, tid, fp, chash, brate, srate) in rows
        if _approx(brate, br, 1) and _approx(srate, sr, 1)
    ]
    if not candidates:
        return None, None

    incoming_hash = file_content_hash(file_path)
    if not incoming_hash:
        return None, None

    matches = []
    for (fid, tid, fp, chash) in candidates:
        ex_hash = chash
        if not ex_hash and fp and os.path.exists(fp):
            ex_hash = file_content_hash(fp)
            if ex_hash:
                cursor.execute(
                    "UPDATE files SET content_hash=?, hashed_at=datetime('now') WHERE id=?",
                    (ex_hash, fid),
                )
        if ex_hash and ex_hash == incoming_hash:
            matches.append({
                "id": fid, "track_id": tid, "file_path": fp,
                "present": bool(fp) and os.path.exists(fp),
                "same_physical": _same_physical_file(fp, file_path),
            })

    if not matches:
        return None, incoming_hash

    # The incoming file IS one of the library's own files (same physical file,
    # seen under a different-case path / remount). Already imported — flag it so
    # the caller SKIPS it. Never trash, never duplicate: that was the data-loss bug.
    for m in matches:
        if m["same_physical"]:
            return {**m, "already_imported": True}, incoming_hash

    # Prefer a row whose file is MISSING from disk → the caller RELINKS it
    # (recovery). Only fall back to a present copy (→ dedupe) when nothing is
    # missing. This stops a recovered file being trashed as a "duplicate" of a
    # still-present sibling while the broken track stays broken.
    missing_first = [m for m in matches if not m["present"]]
    return (missing_first[0] if missing_first else matches[0]), incoming_hash


def find_existing_track(cursor, artist_name, title):
    """
    Looks for an existing track with matching artist + title.
    Case-insensitive, whitespace-trimmed.

    Both fields must be present — we never merge tracks
    on missing metadata alone. Too risky.

    Returns track_id if found, None otherwise.
    """
    if not artist_name or not title:
        return None
    cursor.execute("""
        SELECT id FROM tracks
        WHERE LOWER(TRIM(artist_name)) = LOWER(TRIM(?))
        AND   LOWER(TRIM(title))       = LOWER(TRIM(?))
        LIMIT 1
    """, (artist_name, title))
    row = cursor.fetchone()
    return row[0] if row else None


def _norm_match(s):
    """Loose normaliser for cross-source matching. Mirrors app.py's
    _norm_match — strips case, punctuation, and bracketed (feat …) /
    [Remix] tags so 'X (feat. Y)' matches 'X'."""
    if not s: return ""
    out = s.lower()
    out = re.sub(r"\(.*?\)|\[.*?\]", " ", out)
    out = re.sub(r"[^\w\s]", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out




def add_track_isrc(cursor, track_id, isrc, source):
    """Record an ISRC for a track. Writes to track_isrcs (multi-ISRC
    support — a recording can have several) and sets tracks.isrc as the
    primary if it isn't set yet. `cursor` is a sqlite cursor. Returns
    True if a new track_isrcs row was inserted. No-op on invalid ISRCs."""
    try:
        from dsp_lookup import normalise_isrc
        code = normalise_isrc(isrc)
    except Exception:
        code = None
    if not code:
        return False
    cursor.execute(
        "INSERT OR IGNORE INTO track_isrcs (track_id, isrc, source) VALUES (?, ?, ?)",
        (track_id, code, source)
    )
    inserted = cursor.rowcount > 0
    cursor.execute(
        "UPDATE tracks SET isrc = COALESCE(isrc, ?) WHERE id = ?",
        (code, track_id)
    )
    return inserted


def _try_fulfil_wishlist(cursor, track_id, artist, title):
    """If a 'wishing' wishlist row matches this newly-imported track,
    mark it 'supported' and back-link. Also copy any wishlist.spotify_id
    onto the new track so future DSP checks know it's on Spotify.

    Returns the wishlist row id we fulfilled, or None.
    """
    na, nt = _norm_match(artist), _norm_match(title)
    if not na or not nt:
        return None
    cursor.execute(
        "SELECT id, artist, title, spotify_id FROM wishlist WHERE status = 'wishing'"
    )
    rows = cursor.fetchall()
    for r in rows:
        # cursor rows are tuples by default; rely on positional access
        w_id, w_artist, w_title, w_spotify_id = r[0], r[1], r[2], r[3]
        if _norm_match(w_artist) == na and _norm_match(w_title) == nt:
            cursor.execute(
                "UPDATE wishlist SET status='supported', "
                "fulfilled_track_id=?, fulfilled_at=datetime('now'), "
                "last_visited_at=datetime('now') WHERE id=?",
                (track_id, w_id)
            )
            if w_spotify_id:
                # Best-effort: this won't overwrite an existing spotify_id
                cursor.execute(
                    "UPDATE tracks SET spotify_id = COALESCE(spotify_id, ?), "
                    "dsp_check_state = CASE WHEN dsp_check_state IS NULL OR dsp_check_state='untested' "
                    "THEN 'on_dsp' ELSE dsp_check_state END, "
                    "dsp_checked_at = COALESCE(dsp_checked_at, datetime('now')) "
                    "WHERE id=?",
                    (w_spotify_id, track_id)
                )
            return w_id
    return None


def get_well_id(cursor):
    """Returns the id of The Well. Every track goes here on import."""
    cursor.execute("SELECT id FROM places WHERE is_well = 1")
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("The Well not found. Run schema.py first.")
    return row[0]


# =============================================================
# FILE DISCOVERY
# =============================================================

# Files moved here via "Remove from Music Room" are NEVER re-imported. Resolve
# the REAL removed folder (settings removed_dir → DATA_DIR/'Removed from Music
# Room') PLUS the legacy hardcoded location; both folders + all their subfolders
# are skipped by find_audio_files. (Old code only matched the stale hardcoded
# path, so files in the real removed folder could have been re-imported.)
_LEGACY_REMOVED = os.path.join("/Volumes/EXTERNAL HARD DRIVE 1", "Music Room", "Removed from Music Room")

def _removed_dirs():
    configured = ""
    try:
        conn = get_connection(); cur = conn.cursor()
        row = cur.execute("SELECT value FROM settings WHERE key='removed_dir'").fetchone()
        conn.close()
        if row and row[0]:
            configured = str(row[0]).strip()
    except Exception:
        configured = ""
    real = configured or os.path.join(DATA_DIR, "Removed from Music Room")
    return [os.path.normpath(real), os.path.normpath(_LEGACY_REMOVED)]


# Directories we never descend into when sweeping a whole disk or home folder —
# they hold app guts, caches, OS files or other apps' media libraries, never the
# user's music collection. Matched by exact basename, bundle-style suffix, or
# absolute path prefix. This is what makes "point it at my whole Mac" safe.
_SKIP_DIR_BASENAMES = {"node_modules", "__pycache__", ".Trashes", "Backup",
                       "Ableton Project Info", "Library",
                       # grúpa folders (grupa_folder.py): the library's own records
                       # listed a second time, for dragging into other programs
                       "Music Room — Grúpaí"}
_SKIP_DIR_SUFFIXES = (".app", ".bundle", ".framework", ".plugin", ".component",
                      ".kext", ".photoslibrary", ".musiclibrary", ".tvlibrary",
                      ".aplibrary", ".pkg", ".mpkg", ".xcodeproj", ".logicx",
                      ".band")
_SKIP_ABS_PREFIXES = ("/System", "/private", "/usr", "/bin", "/sbin", "/dev",
                      "/cores", "/opt", "/Network", "/.vol")

def _is_grupa_folder(path):
    """Did the Music Room make this folder as a grúpa's folder of files?"""
    try:
        import json
        with open(os.path.join(path, ".musicroom.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        return isinstance(d, dict) and d.get("kind") == "grupa_folder"
    except (OSError, ValueError):
        return False


def _should_skip_dir(path, scan_root):
    """True if this directory should never be scanned for library music.
    `scan_root` is exempt from basename rules so the user can deliberately point
    the scan AT a folder named e.g. 'Library' without it being skipped."""
    np = os.path.normpath(path)
    if any(np == p or np.startswith(p + os.sep) for p in _SKIP_ABS_PREFIXES):
        return True
    if np == scan_root:
        return False
    base = os.path.basename(np)
    if base in _SKIP_DIR_BASENAMES:
        return True
    return base.lower().endswith(_SKIP_DIR_SUFFIXES)


def find_audio_files(scan_path, formats=None):
    """
    Walks every folder under scan_path recursively.
    Returns a sorted list of supported audio file paths.

    `formats` — an optional set of extensions (e.g. {".mp3", ".wav"}) to
    restrict discovery to a user-chosen subset. None = every supported format
    (AUDIO_EXTENSIONS). Any extensions outside AUDIO_EXTENSIONS are ignored.

    Skipped automatically (so a whole-drive / whole-laptop sweep is safe):
      - Hidden folders (starting with '.').
      - System / OS folders (/System, /usr, …), app bundles (*.app), and other
        apps' media libraries (*.photoslibrary, *.musiclibrary), node_modules,
        a 'Library' folder, etc. — see _SKIP_DIR_*.
      - The 'Removed from Music Room' quarantine folder(s).
      - Grúpa folders (grupa_folder.py): records already in the library, listed
        a second time for dragging into other programs.
      - Ableton project folders — any folder that directly contains a .als file
        (and all its subfolders). EXCEPTION: the top-level scan_path itself is
        never skipped for a stray .als — otherwise a single loose .als at a
        drive's root would make a whole-drive scan import NOTHING.
    """
    audio_files = []
    skipped_ableton = []
    removed_dirs = _removed_dirs()
    scan_root = os.path.normpath(scan_path)
    # restrict to the chosen subset, but never beyond what's actually supported
    exts = {e.lower() for e in (formats or AUDIO_EXTENSIONS)} & AUDIO_EXTENSIONS
    if not exts:
        exts = set(AUDIO_EXTENSIONS)
    print(f"\n  Scanning: {scan_path}")
    print(f"  Looking for {', '.join(sorted(e.lstrip('.').upper() for e in exts))} files...\n")

    for root, dirs, files in os.walk(scan_path):
        nroot = os.path.normpath(root)

        # Skip the quarantine folder(s) + their subfolders — files removed from
        # Music Room live here and must never be re-imported.
        if any(nroot == rd or nroot.startswith(rd + os.sep) for rd in removed_dirs):
            dirs[:] = []
            continue

        # Skip a grúpa's folder of files wherever it is (grupa_folder.py marks it
        # with a small list of its own): what is in it is already in the library —
        # the same files listed twice, links to them, or copies made for a DJ
        # program — and must never come in a second time.
        if ".musicroom.json" in files and _is_grupa_folder(root):
            dirs[:] = []
            continue

        # Skip Ableton project folders (a folder that directly contains a .als),
        # but NOT the scan root itself — a stray .als at the root must not nuke
        # the entire sweep.
        if nroot != scan_root and any(f.lower().endswith('.als') for f in files):
            skipped_ableton.append(root)
            dirs[:] = []  # don't recurse into Samples/, Backup/, etc.
            continue

        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in exts:
                audio_files.append(os.path.join(root, filename))

        # Control descent: drop hidden + system/app/junk dirs so we never walk
        # into them (cheaper than visiting then skipping, and prunes their trees).
        dirs[:] = [d for d in dirs
                   if not d.startswith('.')
                   and not _should_skip_dir(os.path.join(root, d), scan_root)]

    if skipped_ableton:
        print(f"  Skipped {len(skipped_ableton)} Ableton project folder(s).")
    print(f"  Found {len(audio_files)} files.\n")
    return sorted(audio_files)


# =============================================================
# FILENAME PARSING
# =============================================================

def parse_artist_title_from_filename(file_path):
    """
    Last-resort metadata extraction from the filename itself.
    Handles common Soulseek and download naming conventions:

        "Artist - Title.mp3"
        "01 - Artist - Title.mp3"
        "01. Artist - Title.mp3"
        "Artist_-_Title.mp3"

    Returns (artist, title) or (None, None) if no pattern matches.
    Does not guess blindly — only returns values when the pattern
    is clear enough to be useful.
    """
    filename = os.path.splitext(os.path.basename(file_path))[0]

    # Replace underscores with spaces for "_-_" style names
    filename = filename.replace('_-_', ' - ').replace('_', ' ')

    # Strip leading track numbers like "01 - " or "01. " or "(01) "
    filename = re.sub(r'^\d+[\.\-\)\s]+', '', filename).strip()

    # Now look for "Artist - Title" pattern
    # Must have exactly " - " as separator (with spaces)
    if ' - ' in filename:
        parts = filename.split(' - ', 1)  # split on first occurrence only
        artist = parts[0].strip()
        title  = parts[1].strip()

        # Sanity check — both parts must be at least 2 characters
        # and not look like numbers (track numbers slipping through)
        if len(artist) >= 2 and len(title) >= 2:
            if not artist.isdigit() and not title.isdigit():
                return artist, title

    return None, None


# =============================================================
# METADATA EXTRACTION
# =============================================================

def extract_file_metadata(file_path):
    """
    Reads tags embedded in the audio file using mutagen.
    Uses a three-tier fallback strategy:

    Tier 1 — mutagen easy=True
        Normalised interface, works for most well-tagged files.

    Tier 2 — raw ID3 frames
        Catches non-standard tag formats common in Soulseek downloads.
        Reads TIT2 (title), TPE1 (artist), TPE2 (album artist fallback),
        TALB (album), TDRC/TYER (year), TRCK (track number).

    Tier 3 — filename parsing
        Last resort for files with no usable tags at all.
        Parses "Artist - Title.mp3" style filenames.
        Flagged as needs_review so you can verify in the interface.

    Any unreadable field returns None — missing metadata never
    causes a crash or a lost track.
    """
    meta = {
        "title":          None,
        "artist_name":    None,
        "album":          None,
        "year":           None,
        "label":          None,
        "isrc":           None,
        "track_number":   None,
        "file_format":    None,
        "file_size_mb":   None,
        "duration_sec":   None,
        "sample_rate":    None,
        "bit_depth":      None,
        "bitrate_kbps":   None,
        "from_filename":  False,  # True if metadata came from filename parsing
    }

    try:
        meta["file_size_mb"] = round(
            os.path.getsize(file_path) / (1024 * 1024), 2
        )
        meta["file_format"] = true_container_format(file_path)

        # -------------------------------------------------------
        # TIER 1 — mutagen easy=True
        # Normalised tag interface — works for most files
        # -------------------------------------------------------
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return meta

        if hasattr(audio, 'info'):
            info = audio.info
            if hasattr(info, 'length'):
                meta["duration_sec"] = round(info.length, 2)
            if hasattr(info, 'sample_rate'):
                meta["sample_rate"] = info.sample_rate
            if hasattr(info, 'bitrate'):
                meta["bitrate_kbps"] = info.bitrate // 1000
            if hasattr(info, 'bits_per_sample'):
                meta["bit_depth"] = info.bits_per_sample

        for field, tag_key in [
            ("title",       "title"),
            ("artist_name", "artist"),
            ("album",       "album"),
            ("label",       "organization"),
        ]:
            try:
                if tag_key in audio:
                    meta[field] = str(audio[tag_key][0]).strip()
            except Exception:
                pass

        try:
            year_str = None
            if "date" in audio:
                year_str = str(audio["date"][0])
            elif "year" in audio:
                year_str = str(audio["year"][0])
            if year_str:
                meta["year"] = int(year_str[:4])
        except Exception:
            pass

        try:
            if "tracknumber" in audio:
                tn = str(audio["tracknumber"][0]).split("/")[0]
                meta["track_number"] = int(tn)
        except Exception:
            pass

        # -------------------------------------------------------
        # TIER 2 — raw ID3 frames
        # Fallback for files where easy=True misses tags.
        # Common with Soulseek downloads and older taggers.
        # Only fills in fields that are still missing after Tier 1.
        # -------------------------------------------------------
        raw_audio = MutagenFile(file_path)

        if raw_audio and raw_audio.tags:
            tags = raw_audio.tags

            # TIT2 = title
            if not meta["title"]:
                for frame_id in ["TIT2", "\xa9nam"]:
                    try:
                        if frame_id in tags:
                            val = str(tags[frame_id])
                            # ID3 frame objects have a text attribute
                            if hasattr(tags[frame_id], 'text'):
                                val = str(tags[frame_id].text[0])
                            if val.strip():
                                meta["title"] = val.strip()
                                break
                    except Exception:
                        pass

            # TPE1 = lead artist, TPE2 = album artist (use as fallback)
            if not meta["artist_name"]:
                for frame_id in ["TPE1", "TPE2", "\xa9ART", "aART"]:
                    try:
                        if frame_id in tags:
                            val = str(tags[frame_id])
                            if hasattr(tags[frame_id], 'text'):
                                val = str(tags[frame_id].text[0])
                            if val.strip():
                                meta["artist_name"] = val.strip()
                                break
                    except Exception:
                        pass

            # TALB = album
            if not meta["album"]:
                for frame_id in ["TALB", "\xa9alb"]:
                    try:
                        if frame_id in tags:
                            val = str(tags[frame_id])
                            if hasattr(tags[frame_id], 'text'):
                                val = str(tags[frame_id].text[0])
                            if val.strip():
                                meta["album"] = val.strip()
                                break
                    except Exception:
                        pass

            # TDRC or TYER = year
            if not meta["year"]:
                for frame_id in ["TDRC", "TYER", "\xa9day"]:
                    try:
                        if frame_id in tags:
                            val = str(tags[frame_id])
                            if hasattr(tags[frame_id], 'text'):
                                val = str(tags[frame_id].text[0])
                            year = int(str(val).strip()[:4])
                            if 1900 < year < 2100:
                                meta["year"] = year
                                break
                    except Exception:
                        pass

            # TRCK = track number
            if not meta["track_number"]:
                try:
                    if "TRCK" in tags:
                        val = str(tags["TRCK"])
                        if hasattr(tags["TRCK"], 'text'):
                            val = str(tags["TRCK"].text[0])
                        meta["track_number"] = int(val.split("/")[0].strip())
                except Exception:
                    pass

            # label — Tier 1 (easy=True) reads it for MP3/FLAC via 'organization',
            # but M4A keeps a custom label in an iTunes freeform atom the easy
            # interface doesn't expose. Fill it here if still missing, so M4A
            # imports the label like the other formats do.
            if not meta.get("label"):
                try:
                    if "TPUB" in tags:                       # ID3 publisher frame
                        val = tags["TPUB"]
                        val = str(val.text[0]) if hasattr(val, "text") else str(val)
                        if val.strip():
                            meta["label"] = val.strip()
                    else:
                        for atom in ("----:com.apple.iTunes:LABEL",
                                     "----:com.apple.iTunes:publisher"):
                            if atom in tags:
                                raw = tags[atom][0]
                                val = (raw.decode("utf-8", "replace")
                                       if isinstance(raw, (bytes, bytearray)) else str(raw))
                                if val.strip():
                                    meta["label"] = val.strip()
                                    break
                except Exception:
                    pass

        # -------------------------------------------------------
        # TIER 3 — filename parsing
        # Last resort — only used if both title AND artist are
        # still missing after checking all embedded tags.
        # Results flagged as from_filename so they can be shown
        # differently in the interface (needs_review = 1).
        # -------------------------------------------------------
        if not meta["title"] and not meta["artist_name"]:
            artist, title = parse_artist_title_from_filename(file_path)
            if artist and title:
                meta["artist_name"]   = artist
                meta["title"]         = title
                meta["from_filename"] = True

        # -------------------------------------------------------
        # ISRC — backend-only exact recording id (TSRC / Vorbis
        # isrc / MP4 atom). Never shown in the UI; used for exact
        # DSP / label / artwork lookups. Absent on most MP3s.
        # -------------------------------------------------------
        try:
            from dsp_lookup import extract_isrc
            meta["isrc"] = extract_isrc(file_path)
        except Exception:
            pass

    except Exception as e:
        print(f"\n  Warning: metadata failed for {file_path}: {e}\n")

    return meta


# =============================================================
# AUDIO ANALYSIS
# =============================================================

def estimate_bpm(y, sr):
    """Tempo estimate that is NOT stuck on librosa's coarse lattice.

    librosa's beat_track/tempo report tempo as 60*sr/(hop*lag) for an INTEGER
    autocorrelation lag — a whole library collapses onto ~47 distinct values
    (117.45, 123.05, 129.2, …), so real 120/128 BPM tracks read as neighbours
    of themselves. Fix: a finer hop (256) for a denser lag grid, then
    parabolic interpolation on the autocorrelation peak for sub-bin
    precision, with librosa's own log-normal 120-BPM prior so half/double
    choices match what beat_track would have picked.
    """
    import librosa
    import numpy as np

    hop = 256
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    if oenv is None or not np.any(oenv):
        return None
    tg = librosa.feature.tempogram(onset_envelope=oenv, sr=sr, hop_length=hop)
    ac = np.mean(tg, axis=1)
    freqs = librosa.tempo_frequencies(ac.shape[0], sr=sr, hop_length=hop)
    # log-normal prior centred on 120 BPM (librosa's default), zero outside
    # a sane musical range
    with np.errstate(divide="ignore", invalid="ignore"):
        prior = np.exp(-0.5 * ((np.log2(freqs) - np.log2(120.0)) / 1.0) ** 2)
    prior[~np.isfinite(prior)] = 0.0
    prior[(freqs < 40) | (freqs > 220)] = 0.0
    score = ac * prior
    if not np.any(score > 0):
        return None
    k = int(np.argmax(score))
    if k < 1:
        return None
    # parabolic interpolation over the LAG axis → continuous tempo
    d = 0.0
    if 1 <= k < ac.shape[0] - 1:
        a, b, c = float(ac[k - 1]), float(ac[k]), float(ac[k + 1])
        denom = a - 2 * b + c
        if abs(denom) > 1e-12:
            d = float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5))
    bpm = 60.0 * sr / (hop * (k + d))
    return round(float(bpm), 1)


def _load_via_ffmpeg(file_path, sr=22050, duration=120):
    """Decode audio via ffmpeg to float32 PCM.

    Fallback when libsndfile (soundfile) can't read the file — some FLACs
    trigger 'flac decoder lost sync' in older libsndfile builds even though
    the file itself is fine.  ffmpeg handles them without issue.
    """
    import subprocess, numpy as np
    from mr_ffmpeg import ffmpeg_path
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found (bundled, PATH, or Homebrew)")
    cmd = [
        ffmpeg, '-i', file_path,
        '-t', str(duration),
        '-ar', str(sr), '-ac', '1',
        '-f', 'f32le', '-',
        '-loglevel', 'error',
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode(errors='replace')[:300]}")
    return np.frombuffer(proc.stdout, dtype='float32'), sr


def analyse_audio(file_path):
    """
    Extracts acoustic features using librosa.
    Only called when --analyse or --analyse-missing is used.
    Loads first 2 minutes only — enough for accurate analysis.

    BPM and key are estimates. Both have _verified flags in
    the database (default 0). Confirm or correct in the
    interface — one click sets the flag to 1.

    Returns a dict of values. On failure, has_analysis stays 0
    and an 'error' key carries the reason so the caller can
    log it and mark the file appropriately.
    """
    import librosa
    import numpy as np

    analysis = {
        "bpm":               None,
        "key_note":          None,
        "key_scale":         None,
        "key_confidence":    None,
        "loudness_rms":      None,
        "dynamic_range":     None,
        "spectral_centroid": None,
        # v19 — perceptual A-weighted band loudness in dB (absolute, comparable)
        "band_sub":         None,  # 20-60 Hz
        "band_bass":        None,  # 60-250 Hz
        "band_lowmid":      None,  # 250-500 Hz
        "band_body":        None,  # 500-2000 Hz
        "band_presence":    None,  # 2000-5000 Hz (vocals)
        "band_brilliance":  None,  # 5000-11025 Hz
        "has_analysis":      0,
        "error":             None,
    }

    # Skip empty/corrupt files immediately — no point attempting to load them
    try:
        if os.path.getsize(file_path) < 1024:
            analysis["error"] = "File is empty or too small to analyse"
            analysis["status_override"] = "empty"
            return analysis
    except OSError:
        pass

    try:
        try:
            # MP4/AAC: librosa falls back to audioread, which decodes the WHOLE
            # file before truncating — crippling on long tracks (a 28-min m4a
            # took minutes). ffmpeg honours -t and seeks, so it decodes only the
            # 120 s window. Detect MP4 by the 'ftyp' magic (not just extension)
            # so a mislabelled .mp3 that's really MP4/AAC takes the fast path too.
            ext = os.path.splitext(file_path)[1].lower()
            is_mp4 = ext in (".m4a", ".m4b", ".mp4", ".aac", ".alac")
            if not is_mp4:
                try:
                    with open(file_path, "rb") as fh:
                        if fh.read(12)[4:8] == b"ftyp":
                            is_mp4 = True
                except Exception:
                    pass
            if is_mp4:
                y, sr = _load_via_ffmpeg(file_path)
            else:
                y, sr = librosa.load(file_path, mono=True, sr=22050, duration=120)
        except Exception as load_err:
            # libsndfile fails on some FLACs ("flac decoder lost sync") —
            # fall back to ffmpeg which handles them cleanly.
            try:
                y, sr = _load_via_ffmpeg(file_path)
            except Exception as ff_err:
                raise RuntimeError(
                    f"All loaders failed — librosa: {load_err}; ffmpeg: {ff_err}"
                ) from ff_err

        analysis["bpm"] = estimate_bpm(y, sr)

        # Key: Krumhansl–Schmuckler profile correlation on tuning-corrected,
        # percussion-removed chroma (Essentia 'edma' if installed) — far more
        # accurate than picking the loudest pitch-class. See key_detect.py.
        try:
            import key_detect
            _k = key_detect.detect_key(y, sr)
            analysis["key_note"]       = _k.get("key_note")
            analysis["key_scale"]      = _k.get("key_scale")
            analysis["key_confidence"] = _k.get("confidence")
        except Exception:
            analysis["key_note"]       = None
            analysis["key_scale"]      = None
            analysis["key_confidence"] = None

        rms = librosa.feature.rms(y=y)
        analysis["loudness_rms"]  = round(float(np.mean(rms)), 6)
        analysis["dynamic_range"] = round(
            float(np.max(rms)) - float(np.min(rms)), 6
        )

        stft  = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)

        # ── v19 perceptual 6-band fingerprint ──
        bands = _compute_band_fingerprint(stft, freqs)
        for k, v in bands.items():
            analysis[k] = v

        # v35 — single "brightness" number = cumulative HF dB across
        # Presence (2-5 kHz) + Brilliance (5-11 kHz). Stays in step with
        # whatever weight migrate.py's backfill uses.
        p = bands.get("band_presence")
        b = bands.get("band_brilliance")
        if p is not None and b is not None:
            analysis["brightness_score"] = round(0.40 * p + 0.60 * b, 3)
        else:
            analysis["brightness_score"] = None

        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        analysis["spectral_centroid"] = round(float(np.mean(centroid)), 2)

        analysis["has_analysis"] = 1

    except Exception as e:
        analysis["error"] = f"{type(e).__name__}: {e}"
        print(f"  ANALYSIS FAILED: {os.path.basename(file_path)}: {analysis['error']}", flush=True)

    return analysis


# =============================================================
# DATABASE WRITING
# =============================================================

def insert_track_and_file(cursor, file_path, meta, analysis, well_id, content_hash=None):
    """
    Writes a track and file record to the database.

    1. Check for existing track with same artist + title.
       If found — link new file to it (duplicate or alternate version).
    2. If not found — create new track record, then file record.
    3. Add track to The Well automatically.
    4. First file for a track is set as primary automatically.

    Tracks where metadata came from filename parsing are flagged
    needs_review = 1 so they're easy to find and verify.

    Returns (track_id, file_id, is_duplicate)
    """
    # "(Original Mix)" / "Original Version" are noise tags that Spotify /
    # MusicBrainz / Discogs / iTunes don't carry — strip on import so the
    # DB title matches what API lookups will return.
    try:
        from text_clean import strip_mix_suffix
        if meta.get("title"):
            meta["title"] = strip_mix_suffix(meta["title"]) or meta["title"]
    except Exception:
        pass

    existing_track_id = find_existing_track(
        cursor, meta.get("artist_name"), meta.get("title")
    )
    is_duplicate = existing_track_id is not None

    if is_duplicate:
        track_id = existing_track_id
        # Backfill ISRC onto the existing track if it didn't have one
        # and this file format carries it (FLACs usually do).
        if meta.get("isrc"):
            cursor.execute(
                "UPDATE tracks SET isrc = COALESCE(isrc, ?), "
                "isrc_checked_at = COALESCE(isrc_checked_at, datetime('now')) "
                "WHERE id = ?",
                (meta.get("isrc"), track_id)
            )
    else:
        # Flag for review if:
        # - no title AND no artist (genuinely unknown)
        # - metadata came from filename parsing (unverified)
        needs_review = 1 if (
            (not meta.get("title") and not meta.get("artist_name"))
            or meta.get("from_filename")
        ) else 0

        is_oneshot = 1 if (meta.get("duration_sec") or 9999) < 5 else 0

        cursor.execute("""
            INSERT INTO tracks (
                title, artist_name, album, year,
                label, track_number, needs_review, is_oneshot,
                isrc, isrc_checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            meta.get("title"),
            meta.get("artist_name"),
            meta.get("album"),
            meta.get("year"),
            meta.get("label"),
            meta.get("track_number"),
            needs_review,
            is_oneshot,
            meta.get("isrc"),
        ))
        track_id = cursor.lastrowid

        cursor.execute("""
            INSERT OR IGNORE INTO place_tracks (place_id, track_id)
            VALUES (?, ?)
        """, (well_id, track_id))

        # If this newly-imported track matches a wishlist entry, mark it
        # supported and back-link. Match is loose (case, punctuation,
        # bracketed remix/feat tags stripped) — same normalisation we
        # use elsewhere for cross-source matching.
        _try_fulfil_wishlist(
            cursor, track_id, meta.get("artist_name"), meta.get("title")
        )

    # Record the embedded ISRC in the multi-ISRC table (and as primary
    # if the track doesn't have one yet).
    if meta.get("isrc"):
        add_track_isrc(cursor, track_id, meta.get("isrc"), "embedded")

    cursor.execute(
        "SELECT COUNT(*) FROM files WHERE track_id = ?", (track_id,)
    )
    is_primary = 1 if cursor.fetchone()[0] == 0 else 0

    a = analysis or {}

    cursor.execute("""
        INSERT INTO files (
            track_id, file_path, file_format, file_size_mb,
            duration_sec, sample_rate, bit_depth, bitrate_kbps,
            is_primary, bpm, key_note, key_scale, key_confidence,
            loudness_rms, dynamic_range, spectral_centroid,
            band_sub, band_bass, band_lowmid,
            band_body, band_presence, band_brilliance,
            brightness_score, has_analysis,
            content_hash, hashed_at
        ) VALUES (
            :track_id, :file_path, :file_format, :file_size_mb,
            :duration_sec, :sample_rate, :bit_depth, :bitrate_kbps,
            :is_primary, :bpm, :key_note, :key_scale, :key_confidence,
            :loudness_rms, :dynamic_range, :spectral_centroid,
            :band_sub, :band_bass, :band_lowmid,
            :band_body, :band_presence, :band_brilliance,
            :brightness_score, :has_analysis,
            :content_hash,
            CASE WHEN :content_hash IS NOT NULL THEN datetime('now') ELSE NULL END
        )
    """, {
        "track_id":          track_id,
        "content_hash":      content_hash,
        "file_path":         file_path,
        "file_format":       meta.get("file_format"),
        "file_size_mb":      meta.get("file_size_mb"),
        "duration_sec":      meta.get("duration_sec"),
        "sample_rate":       meta.get("sample_rate"),
        "bit_depth":         meta.get("bit_depth"),
        "bitrate_kbps":      meta.get("bitrate_kbps"),
        "is_primary":        is_primary,
        "bpm":               a.get("bpm"),
        "key_note":          a.get("key_note"),
        "key_scale":         a.get("key_scale"),
        "key_confidence":    a.get("key_confidence"),
        "loudness_rms":      a.get("loudness_rms"),
        "dynamic_range":     a.get("dynamic_range"),
        "spectral_centroid": a.get("spectral_centroid"),
        "band_sub":          a.get("band_sub"),
        "band_bass":         a.get("band_bass"),
        "band_lowmid":       a.get("band_lowmid"),
        "band_body":         a.get("band_body"),
        "band_presence":     a.get("band_presence"),
        "band_brilliance":   a.get("band_brilliance"),
        "brightness_score":  a.get("brightness_score"),
        "has_analysis":      a.get("has_analysis", 0),
    })

    return track_id, cursor.lastrowid, is_duplicate


# =============================================================
# ANALYSE MISSING
# =============================================================

def run_analyse_missing():
    """
    Finds all files in the database with has_analysis = 0
    and runs audio analysis on them.

    Marks each file's analysis_status as:
        'done'    — librosa succeeded, all features extracted
        'failed'  — librosa raised, file is still has_analysis=0
        'missing' — file not on disk
    """
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, file_path FROM files
        WHERE has_analysis = 0
        AND   is_deleted   = 0
        AND   (analysis_status IS NULL OR analysis_status NOT IN ('empty', 'missing', 'locked'))
        ORDER BY file_path
    """)
    rows = cursor.fetchall()

    if not rows:
        print("\n  All files already analysed.\n")
        conn.close()
        return

    total = len(rows)
    print(f"\n  {total} files need analysis.", flush=True)
    print("  ~5-15 seconds per track.", flush=True)
    print("  Ctrl+C to stop safely — progress is saved.\n", flush=True)

    count_done    = 0
    count_failed  = 0
    count_missing = 0

    # Plain progress lines (no tqdm) so the log captures every step
    # cleanly when run as a subprocess from the /analyse page.
    for i, (file_id, file_path) in enumerate(rows, 1):

        filename = os.path.basename(file_path)
        print(f"  [{i}/{total}] {filename}", flush=True)

        if not os.path.exists(file_path):
            print(f"  MISSING: file not on disk", flush=True)
            cursor.execute(
                "UPDATE files SET analysis_status='missing', updated_at=datetime('now') WHERE id=?",
                (file_id,)
            )
            count_missing += 1
        else:
            try:
                analysis = analyse_audio(file_path)
                a = analysis or {}
                ok = bool(a.get("has_analysis"))

                cursor.execute("""
                    UPDATE files SET
                        bpm               = :bpm,
                        key_note          = :key_note,
                        key_scale         = :key_scale,
                        key_confidence    = :key_confidence,
                        loudness_rms      = :loudness_rms,
                        dynamic_range     = :dynamic_range,
                        spectral_centroid = :spectral_centroid,
                        has_analysis      = :has_analysis,
                        analysis_status   = :analysis_status,
                        updated_at        = datetime('now')
                    WHERE id = :file_id
                """, {
                    "bpm":               a.get("bpm"),
                    "key_note":          a.get("key_note"),
                    "key_scale":         a.get("key_scale"),
                    "key_confidence":    a.get("key_confidence"),
                    "loudness_rms":      a.get("loudness_rms"),
                    "dynamic_range":     a.get("dynamic_range"),
                    "spectral_centroid": a.get("spectral_centroid"),
                    "has_analysis":      1 if ok else 0,
                    "analysis_status":   "done" if ok else a.get("status_override", "failed"),
                    "file_id":           file_id,
                })

                if ok:
                    count_done += 1
                else:
                    count_failed += 1

            except KeyboardInterrupt:
                # Ctrl+C / SIGTERM — commit progress and exit cleanly.
                print("\n  Interrupted. Saving progress and exiting.", flush=True)
                conn.commit()
                conn.close()
                return
            except Exception as e:
                count_failed += 1
                err = f"{type(e).__name__}: {e}"
                print(f"  FAILED ({err})", flush=True)
                cursor.execute(
                    "UPDATE files SET analysis_status='failed', updated_at=datetime('now') WHERE id=?",
                    (file_id,)
                )

        # Commit per-file — Ctrl+C / kill / power loss never costs more
        # than the file we were mid-flight on.
        conn.commit()

    conn.commit()
    conn.close()

    print("", flush=True)
    print("=============================================================", flush=True)
    print("  Analysis complete.", flush=True)
    print(f"  Analysed:  {count_done}", flush=True)
    print(f"  Failed:    {count_failed}", flush=True)
    print(f"  Missing:   {count_missing}", flush=True)
    print("=============================================================\n", flush=True)


# =============================================================
# MAIN IMPORT FUNCTION
# =============================================================

def run_import(scan_path, do_analysis=False, enrich=False, dup_policy="skip", formats=None):
    """
    Main import function.
    formats:           optional set/list of extensions to restrict the scan to
                       (e.g. {".mp3", ".wav"}); None = every supported format.
    do_analysis=False: fast mode, metadata only
    do_analysis=True:  also runs librosa on each track (audio analysis)
    enrich=True:       after import, also fetch artwork + record label +
                       streaming presence + artist culture for the new
                       tracks (the "Full analysis" option). See run_enrichment.
    dup_policy:        how to handle an incoming file that is byte-identical to
                       a file ALREADY in the library and STILL ON DISK:
                         "skip"   — leave it, don't import (default)
                         "import" — add it as another version of the track
                         "delete" — move the incoming duplicate to the Trash
                       NOTE: if the matched library file is MISSING from disk,
                       the row is RELINKED to this copy regardless of policy —
                       that's pure recovery, never a deletion.
    """
    from trash_util import move_to_trash
    if not os.path.exists(DB_PATH):
        print(f"\n  Error: database not found at {DB_PATH}")
        print("  Run schema.py first.\n")
        sys.exit(1)

    if not os.path.exists(scan_path):
        print(f"\n  Error: path not found: {scan_path}")
        print("  Is your external drive plugged in?\n")
        sys.exit(1)

    audio_files = find_audio_files(scan_path, formats=formats)

    if not audio_files:
        print("  No matching audio files found.\n")
        sys.exit(0)

    conn    = get_connection()
    cursor  = conn.cursor()
    well_id = get_well_id(cursor)

    count_new        = 0
    count_duplicates = 0
    count_skipped    = 0
    count_identical  = 0
    count_relinked   = 0    # broken tracks whose missing file was repointed to a found copy
    count_trashed    = 0    # genuine duplicates moved to Trash (dup_policy="delete")
    count_failed     = 0
    new_track_ids    = []   # genuinely-new tracks, for the enrichment phase
    journal_relinked = []   # {file_id, old_path} repointed rows — for Undo

    if enrich:
        print("  Mode: full (metadata + audio analysis + artwork/label/culture)")
        print("  ~5-15s per track to analyse, then a network pass for the rest.\n")
    elif do_analysis:
        print("  Mode: file analysis (metadata + audio analysis)")
        print("  ~5-15 seconds per track.\n")
    else:
        print("  Mode: fast (metadata only)")
        print("  Run with --analyse-missing later to add audio analysis.\n")

    print("  Saves every 10 tracks. Ctrl+C to pause safely.\n")

    total_files = len(audio_files)
    for file_i, file_path in enumerate(tqdm(audio_files, unit="track", ncols=70), 1):
        # A machine-readable heartbeat for the app's import screen — tqdm's
        # \r bar never reaches its line reader, so without this the import
        # "looks frozen". flush=True: a piped child is block-buffered and
        # would otherwise deliver progress in late 8KB bursts.
        print(f"  [{file_i}/{total_files}] {os.path.basename(file_path)}", flush=True)

        if file_already_exists(cursor, file_path):
            count_skipped += 1
            continue

        try:
            meta = extract_file_metadata(file_path)

            # Byte-identical to a file already in the library?
            dup, inc_hash = find_duplicate_file(cursor, file_path, meta)
            if dup:
                # Same physical file as a library row (different-case path / a
                # remount) → already imported. Skip; NEVER trash our own file.
                if dup.get("already_imported"):
                    count_skipped += 1
                    conn.commit()
                    continue
                existing_present = bool(dup.get("file_path")) and os.path.exists(dup["file_path"])
                if not existing_present:
                    # RELINK (Option B): the library's recorded file for this is
                    # GONE from disk — repoint that row to this found copy. The
                    # broken track becomes playable. Never a deletion; always safe.
                    journal_relinked.append({"file_id": dup["id"], "old_path": dup.get("file_path")})
                    cursor.execute(
                        "UPDATE files SET file_path=?, is_deleted=0, updated_at=datetime('now') WHERE id=?",
                        (file_path, dup["id"]),
                    )
                    if inc_hash:
                        cursor.execute(
                            "UPDATE files SET content_hash=?, hashed_at=datetime('now') "
                            "WHERE id=? AND (content_hash IS NULL OR content_hash='')",
                            (inc_hash, dup["id"]),
                        )
                    count_relinked += 1
                    conn.commit()
                    continue
                # The matched library file is PRESENT → genuine duplicate copy.
                if dup_policy == "delete":
                    # Final safety net: never trash the matched library file itself.
                    if _same_physical_file(dup.get("file_path"), file_path):
                        count_skipped += 1
                        conn.commit()
                        continue
                    ok, _err = move_to_trash(file_path)   # recoverable; never hard-deletes
                    if ok:
                        count_trashed += 1
                    else:
                        count_identical += 1              # couldn't trash → leave it, don't claim removed
                    conn.commit()
                    continue
                if dup_policy != "import":                # "skip"/default: leave it, don't import
                    count_identical += 1
                    conn.commit()
                    continue
                # dup_policy == "import" → fall through and add it as another version.

            analysis = analyse_audio(file_path) if do_analysis else None

            track_id, _, is_duplicate = insert_track_and_file(
                cursor, file_path, meta, analysis, well_id, content_hash=inc_hash
            )

            if is_duplicate:
                count_duplicates += 1
            else:
                count_new += 1
                if track_id:
                    new_track_ids.append(track_id)

        except Exception as e:
            count_failed += 1
            print(f"\n  Failed: {file_path}: {e}\n")
            continue

        # Commit per-file — interrupted imports keep all the work done so far.
        conn.commit()

    conn.commit()
    conn.close()

    # Write an UNDO journal — what this run added/changed, so the app can offer
    # "Undo last import". Retiring (is_deleted=1) the new tracks + restoring the
    # relinked paths is fully reversible; nothing is hard-deleted.
    if new_track_ids or journal_relinked:
        try:
            import json as _json, datetime as _dt
            jdir = os.path.join(DATA_DIR, "import_journals")
            os.makedirs(jdir, exist_ok=True)
            ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            jpath = os.path.join(jdir, f"{ts}.json")
            with open(jpath, "w") as fh:
                _json.dump({"at": ts, "scan_path": scan_path,
                            "new_track_ids": new_track_ids,
                            "relinked": journal_relinked,
                            "count_new": count_new, "count_relinked": count_relinked,
                            "undone": False}, fh, indent=1)
            with sqlite3.connect(DB_PATH) as _c:
                _c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_import_journal', ?)", (jpath,))
                _c.commit()
        except Exception as _e:
            print(f"  (could not write undo journal: {_e})")

    # Flush OS write buffers to the disk now. An import that trashed duplicates
    # or moved files leaves data in the page cache; if the external drive is
    # then pulled WITHOUT ejecting, that un-flushed data is lost / files get
    # corrupted. os.sync() forces it to the platter so a yank is survivable.
    try:
        os.sync()
    except Exception:
        pass

    print("\n")
    print("=============================================================")
    print("  Import complete.")
    print(f"  New tracks:        {count_new}")
    print(f"  Alternate versions:{count_duplicates}")
    print(f"  Relinked (recovered):{count_relinked}")
    print(f"  Duplicates trashed:{count_trashed}")
    print(f"  Identical (skipped):{count_identical}")
    print(f"  Already imported:  {count_skipped}")
    print(f"  Failed:            {count_failed}")
    if not do_analysis:
        print("")
        print("  No audio analysis run.")
        print("  To analyse your library run:")
        print("    python3 importer.py --analyse-missing")
    print("=============================================================\n")

    # Full analysis — artwork + label + streaming + artist culture for the
    # tracks we just brought in. Runs as a separate phase so the import
    # summary lands first and a Ctrl+C during import skips it cleanly.
    if enrich and new_track_ids:
        run_enrichment(new_track_ids)


# =============================================================
# FULL-ANALYSIS ENRICHMENT (artwork + label + streaming + culture)
# =============================================================

def _read_setting(cur, key, default=None):
    """Read one value from the settings table. Tolerant of a missing table."""
    try:
        row = cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row and row[0] not in (None, ""):
            return row[0]
    except Exception:
        pass
    return default


def _upsert_profile(cur, table, key_col, key_val, fields, now_iso):
    """Insert-or-update one row in artist_profiles / label_profiles. Mirrors
    the batch workers in app.py so import-time and on-demand enrichment write
    the exact same columns the maps read."""
    fields = {**fields, "enriched_at": now_iso, "updated_at": now_iso}
    cols = list(fields.keys())
    vals = [fields[c] for c in cols]
    cur.execute(
        f"UPDATE {table} SET {', '.join(c + '=?' for c in cols)} WHERE {key_col}=?",
        vals + [key_val])
    if cur.rowcount == 0:
        cur.execute(
            f"INSERT INTO {table} ({key_col}, {', '.join(cols)}) "
            f"VALUES (?, {', '.join('?' * len(cols))})", [key_val] + vals)


def _distinct_pending(cur, track_ids, track_col, profile_table, profile_key,
                      exclude=()):
    """Distinct, non-empty values of track_col among the given tracks that
    don't already have an enriched profile row. Same only-missing logic the
    culture batch workers use, just scoped to this import."""
    vals, seen = [], set()
    for tid in track_ids:
        r = cur.execute(f"SELECT {track_col} AS v FROM tracks WHERE id=?", (tid,)).fetchone()
        v = ((r["v"] if r else "") or "").strip()
        if not v or v.lower() in exclude or v.lower() in seen:
            continue
        seen.add(v.lower())
        vals.append(v)
    done = {r[profile_key] for r in cur.execute(
        f"SELECT {profile_key} FROM {profile_table} WHERE enriched_at IS NOT NULL").fetchall()}
    done_lower = {d.lower() for d in done if d}
    return [v for v in vals if v.lower() not in done_lower]


def run_enrichment(track_ids):
    """
    The "Full analysis" pass. Runs AFTER import + audio analysis, over just
    the tracks brought in this run. Five network-bound, resumable phases
    (committed per item — a Stop/Ctrl+C keeps everything done so far):

      1. Artwork        — embedded → Deezer(ISRC) → iTunes → MusicBrainz/CAA
      2. Streaming+ISRC — DSP presence (Deezer/iTunes) + any ISRC it exposes
      3. Record label   — canonical label_lookup (MB/Deezer ISRC-first → Discogs)
      4. Artist culture — origin / decade (MusicBrainz + Wikidata + Wikipedia)
      5. Label culture  — origin / founding decade (same sources)

    This is *every* stored enrichment in Music Room. Audio analysis (the bands
    /fingerprint) and embedded-ISRC extraction already ran during import, so
    they're not repeated. Genres stay an interactive suggestion (a curatorial
    pick, not stored data) and the "(Original Mix)" tidy-up renames files on
    disk, so both remain separate, deliberate actions.

    All free, no-key APIs (a Discogs token is used only if you've set one).
    MusicBrainz is rate-limited to ~1 req/sec, so the culture phases are slow.
    """
    if not track_ids:
        return
    import datetime as _dt

    # Lazy imports — only the Full path pays for these network deps.
    try:
        import artwork_fetcher
        from dsp_lookup import check_dsp
        from label_lookup import lookup_label
        from culture import enrich_artist, enrich_label
    except Exception as e:
        print(f"\n  Skipping full analysis — could not load enrichment modules: {e}\n")
        return

    now_iso = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000")
    cur = conn.cursor()
    token = _read_setting(cur, "discogs_token")

    n = len(track_ids)
    print("")
    print("=============================================================")
    print(f"  Full analysis — enriching {n} new track{'' if n == 1 else 's'}")
    print("=============================================================\n")

    # ── 1. Artwork ────────────────────────────────────────────────
    print("  [1/5] Fetching cover art…")
    art_found = 0
    for i, tid in enumerate(track_ids, 1):
        try:
            if artwork_fetcher.fetch_for_track(tid).get("ok"):
                art_found += 1
        except Exception as e:
            print(f"    artwork failed for track {tid}: {e}")
        if i % 5 == 0 or i == n:
            print(f"    {i}/{n} — {art_found} with art")
    print(f"  Cover art found: {art_found}/{n}\n")

    # ── 2+3. Streaming presence (+ ISRC) and record label ─────────
    print("  [2/5] Streaming presence + ISRC, then [3/5] record label…")
    dsp_found = lab_found = 0
    for i, tid in enumerate(track_ids, 1):
        try:
            row = cur.execute(
                "SELECT id, title, artist_name, isrc, label FROM tracks "
                "WHERE id=? AND is_deleted=0", (tid,)).fetchone()
            if not row or not ((row["title"] or "").strip() and (row["artist_name"] or "").strip()):
                continue
            res = check_dsp(row["artist_name"], row["title"], isrc=row["isrc"])
            state = res.get("state")
            if state in ("on_dsp", "not_on_dsp", "skipped"):
                cur.execute(
                    "UPDATE tracks SET dsp_check_state=?, dsp_checked_at=? WHERE id=?",
                    (state, now_iso, tid))
            isrc = row["isrc"]
            if state == "on_dsp":
                dsp_found += 1
                if res.get("isrc"):
                    isrc = res["isrc"]
                    add_track_isrc(
                        cur, tid, res["isrc"],
                        "deezer" if res.get("source") in ("deezer", "isrc") else "musicbrainz")
            # Record label — canonical lookup (ISRC-first), only fill if empty.
            if not (row["label"] or "").strip():
                lr = lookup_label(row["artist_name"], row["title"],
                                  discogs_token=token, isrc=isrc)
                if lr.get("label"):
                    cur.execute(
                        "UPDATE tracks SET label=?, updated_at=datetime('now') WHERE id=?",
                        (lr["label"], tid))
                    lab_found += 1
            conn.commit()
        except Exception as e:
            print(f"    streaming/label failed for track {tid}: {e}")
        if i % 5 == 0 or i == n:
            print(f"    {i}/{n} — {dsp_found} on streaming, {lab_found} labels found")
    print(f"  On streaming: {dsp_found}/{n} · record labels found: {lab_found}\n")

    # ── 4. Artist culture (origin / decade) ───────────────────────
    artists = _distinct_pending(cur, track_ids, "artist_name", "artist_profiles", "artist_name")
    m = len(artists)
    print(f"  [4/5] Enriching {m} new artist{'' if m == 1 else 's'} "
          f"(origin / decade) — MusicBrainz is ~1/sec, so this is the slow part…")
    art_cult = consec = 0
    for i, nm in enumerate(artists, 1):
        try:
            ir = cur.execute(
                "SELECT ti.isrc FROM track_isrcs ti JOIN tracks t ON t.id=ti.track_id "
                "WHERE t.artist_name=? AND ti.isrc IS NOT NULL LIMIT 1", (nm,)).fetchone()
            res = enrich_artist(nm, isrc=(ir["isrc"] if ir else None), discogs_token=token)
            _upsert_profile(cur, "artist_profiles", "artist_name", nm, {
                "country": res.get("country"), "city": res.get("city"),
                "latitude": res.get("latitude"), "longitude": res.get("longitude"),
                "gender": res.get("gender"), "active_from": res.get("active_from"),
                "active_to": res.get("active_to"), "genres": res.get("genres"),
                "bio_summary": res.get("bio_summary"), "wikipedia_note": res.get("wikipedia_note"),
                "mbid": res.get("mbid"), "wikidata_qid": res.get("wikidata_qid"),
                "artist_type": res.get("artist_type"), "data_source": res.get("data_source"),
                "fetch_error": res.get("error"),
            }, now_iso)
            consec = consec + 1 if res.get("error") else 0
            if not res.get("error"):
                art_cult += 1
            conn.commit()
            if consec >= 8:
                print("    (pausing artist culture — too many consecutive misses; "
                      "saved so far, rerun later to resume)")
                break
        except Exception as e:
            print(f"    artist culture failed for {nm}: {e}")
        if i % 3 == 0 or i == m:
            print(f"    {i}/{m} — {art_cult} placed")
    print(f"  Artists enriched: {art_cult}/{m}\n")

    # ── 5. Label culture (origin / founding decade) ───────────────
    labels = _distinct_pending(cur, track_ids, "label", "label_profiles", "label_name",
                               exclude={"self released"})
    k = len(labels)
    print(f"  [5/5] Enriching {k} new label{'' if k == 1 else 's'} (origin / founding)…")
    lab_cult = consec = 0
    for i, lb in enumerate(labels, 1):
        try:
            res = enrich_label(lb, discogs_token=token)
            _upsert_profile(cur, "label_profiles", "label_name", lb, {
                "country": res.get("country"), "city": res.get("city"),
                "latitude": res.get("latitude"), "longitude": res.get("longitude"),
                "founded_year": res.get("founded_year"), "founder": res.get("founder"),
                "bio_summary": res.get("bio_summary"), "wikipedia_url": res.get("wikipedia_url"),
                "mbid": res.get("mbid"), "wikidata_qid": res.get("wikidata_qid"),
                "data_source": res.get("data_source"), "fetch_error": res.get("error"),
            }, now_iso)
            consec = consec + 1 if res.get("error") else 0
            if not res.get("error"):
                lab_cult += 1
            conn.commit()
            if consec >= 8:
                print("    (pausing label culture — too many consecutive misses; "
                      "saved so far, rerun later to resume)")
                break
        except Exception as e:
            print(f"    label culture failed for {lb}: {e}")
        if i % 3 == 0 or i == k:
            print(f"    {i}/{k} — {lab_cult} placed")
    print(f"  Labels enriched: {lab_cult}/{k}\n")

    conn.commit()
    conn.close()
    print("=============================================================")
    print("  Full analysis complete.")
    print("=============================================================\n")


# =============================================================
# ENTRY POINT
# =============================================================

def main(argv=None):
    """Entry point for both `python importer.py …` and the bundled-app
    worker (the .app re-invokes itself with --mr-worker, and the launcher
    dispatches here). Parses args, runs import or analysis."""
    # When run as a subprocess (from /analyse or /import), Flask sends
    # SIGTERM to stop us. Convert it to KeyboardInterrupt so the loop can
    # commit progress and exit cleanly instead of being abruptly killed.
    import signal as _signal
    def _term_handler(*_):
        raise KeyboardInterrupt
    try:
        _signal.signal(_signal.SIGTERM, _term_handler)
    except (ValueError, OSError):
        pass  # not on the main thread — fine

    parser = argparse.ArgumentParser(
        description="Import audio files into Music Room"
    )
    parser.add_argument(
        "--path",
        type=str,
        default=DEFAULT_SCAN_PATH,
        help=f"Folder to scan (default: {DEFAULT_SCAN_PATH})"
    )
    parser.add_argument(
        "--analyse",
        action="store_true",
        help="Run full audio analysis during import (slow — 5-15s per track)"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Full analysis: after import, also fetch artwork + record label "
             "+ streaming presence + artist culture (implies --analyse)"
    )
    parser.add_argument(
        "--analyse-missing",
        action="store_true",
        dest="analyse_missing",
        help="Run analysis on already-imported tracks with no analysis yet"
    )
    parser.add_argument(
        "--formats",
        type=str,
        default=None,
        help="Comma-separated audio formats to import (mp3,flac,wav,m4a). "
             "Default: all supported formats.",
    )
    parser.add_argument(
        "--dup-policy",
        type=str,
        default="skip",
        choices=["skip", "import", "delete"],
        dest="dup_policy",
        help="Genuine duplicates (byte-identical to a file already present): "
             "skip (default) / import as a version / delete (→ Trash). "
             "A missing library file is always relinked regardless."
    )
    args = parser.parse_args(argv)

    print("")
    print("=============================================================")
    print("  Music Room — importer")
    print("=============================================================")

    if args.analyse_missing:
        run_analyse_missing()
    else:
        # --formats mp3,wav → {".mp3", ".wav"}; absent → all supported formats
        formats = None
        if args.formats:
            formats = {"." + f.strip().lower().lstrip(".")
                       for f in args.formats.split(",") if f.strip()}
        # Full analysis (--enrich) always includes audio analysis.
        run_import(args.path, do_analysis=args.analyse or args.enrich, enrich=args.enrich,
                   dup_policy=args.dup_policy, formats=formats)


if __name__ == "__main__":
    main()
