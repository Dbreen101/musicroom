"""
=============================================================
MUSIC ROOM — organiser.py
=============================================================
What this file does:
    Moves your audio files from wherever they currently live
    on your hard drive into a clean, consistent folder
    structure under a single Music Room Library folder.

    After running this, all your music is in one place
    with a predictable structure, and the database is
    updated with the new file paths.

Target structure:
    /Volumes/EXTERNAL HARD DRIVE 1/Music Room Library/
        A/
            Aphex Twin/
                Selected Ambient Works Volume II/
                    01 - Aphex Twin - Radiator.flac
        B/
            Burial/
                Untrue/
                    01 - Burial - Archangel.flac
        Unsorted/
            unknown_track.mp3   ← files with no artist info

Rules:
    - Files with no artist go into Unsorted/
    - Files with no album go directly under the artist folder
    - Artist folders are grouped by first letter (A/, B/, etc)
    - Filenames are sanitised — no special characters that
      cause problems on different operating systems
    - The database file path is updated for every moved file
    - Progress is saved after every file — safe to interrupt
      and resume at any time with Ctrl+C

Safety:
    - Shows a full preview of what will be moved before
      touching anything
    - Requires your explicit confirmation before moving
    - Never deletes anything — only moves
    - If a destination file already exists, the source file
      is renamed with a suffix rather than overwritten

How to run:
    source venv/bin/activate
    python3 organiser.py

    To preview without moving anything:
        python3 organiser.py --dry-run

    To target a specific output folder:
        python3 organiser.py --dest "/Volumes/EXTERNAL HARD DRIVE 1/Music Room Library"
=============================================================
"""

import os
import re
import sys
import sqlite3
import shutil
import argparse

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
from mr_paths import DB_PATH  # noqa: E402  (shared data dir; see mr_paths.py)

# Default destination — where the organised library will live. Overridable
# with --dest; this is just the fallback when run with no argument.
DEFAULT_DEST = os.environ.get(
    "MUSICROOM_LIBRARY_DEST",
    "/Volumes/EXTERNAL HARD DRIVE 1/Music Room Library",
)


# =============================================================
# DATABASE
# =============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_all_files(conn):
    """
    Returns all non-deleted file records from the database.
    Each row has: id, file_path, track_id, file_format,
    and the track's title and artist_name for building paths.
    """
    cursor = conn.execute("""
        SELECT
            f.id,
            f.file_path,
            f.track_id,
            f.file_format,
            t.title,
            t.artist_name,
            t.album,
            t.track_number
        FROM files f
        JOIN tracks t ON t.id = f.track_id
        WHERE f.is_deleted = 0
          AND COALESCE(f.analysis_status, '') != 'locked'   -- Green Room borrows stay put
        ORDER BY t.artist_name ASC, t.album ASC, t.title ASC
    """)
    return [dict(row) for row in cursor.fetchall()]


def update_file_path(conn, file_id, new_path):
    """Updates the file path in the database after a file is moved."""
    conn.execute(
        "UPDATE files SET file_path = ?, updated_at = datetime('now') WHERE id = ?",
        (new_path, file_id)
    )
    conn.commit()


# =============================================================
# PATH BUILDING
# =============================================================

def sanitise(name):
    """
    Removes or replaces characters that cause problems in
    file paths on Mac, Windows, or Linux.
    Keeps the name readable — just strips the dangerous bits.
    """
    if not name:
        return "Unknown"
    # Replace characters that are problematic in file paths
    name = re.sub(r'[/\\:*?"<>|]', '_', name)
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)
    return name or "Unknown"


def first_letter_folder(artist_name):
    """
    Returns the single-letter folder for an artist.
    "Aphex Twin" → "A"
    "The XX" → "X"  (strips "The " prefix)
    "808 State" → "#" (numbers go in # folder)
    """
    if not artist_name or artist_name == "Unknown":
        return "Unsorted"

    name = artist_name.strip()

    # Strip common articles so "The Beatles" sorts under B
    for article in ("The ", "A ", "An "):
        if name.upper().startswith(article.upper()):
            name = name[len(article):]
            break

    first = name[0].upper() if name else "#"
    return first if first.isalpha() else "#"


def build_destination_path(dest_root, file_record):
    """
    Builds the full destination path for a file based on its
    artist, album, track number, and title.

    Structure:
        dest_root/
            {letter}/
                {artist}/
                    {album}/
                        {track_number} - {artist} - {title}.{ext}

    If album is missing, the file goes directly under the artist folder.
    If artist is missing, the file goes in Unsorted/.
    """
    artist = sanitise(file_record.get("artist_name") or "")
    album  = sanitise(file_record.get("album") or "")
    title  = sanitise(file_record.get("title") or "")
    ext    = file_record.get("file_format") or "mp3"
    num    = file_record.get("track_number")

    # Build filename
    if num and title:
        filename = f"{int(num):02d} - {artist} - {title}.{ext}"
    elif title:
        filename = f"{artist} - {title}.{ext}"
    else:
        # Fall back to original filename if no title
        original = os.path.basename(file_record["file_path"])
        filename = original

    # Sanitise filename
    filename = sanitise(filename.replace('/', '_'))

    # Build folder path
    if not artist or artist == "Unknown":
        folder = os.path.join(dest_root, "Unsorted")
    elif not album or album == "Unknown":
        letter = first_letter_folder(file_record.get("artist_name") or "")
        folder = os.path.join(dest_root, letter, artist)
    else:
        letter = first_letter_folder(file_record.get("artist_name") or "")
        folder = os.path.join(dest_root, letter, artist, album)

    return os.path.join(folder, filename)


def unique_path(dest_path):
    """
    If dest_path already exists, adds a numeric suffix.
    e.g. track.flac → track (2).flac → track (3).flac
    Prevents any file from being silently overwritten.
    """
    if not os.path.exists(dest_path):
        return dest_path

    base, ext = os.path.splitext(dest_path)
    counter   = 2
    while True:
        candidate = f"{base} ({counter}){ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


# =============================================================
# MAIN
# =============================================================

def organise_library(dest_root, mode="move", progress=None, should_stop=None, only_under=None):
    """Programmatic organiser used by the app / onboarding wizard (no input()).

    Sorts every file in the DB into dest_root/<Letter>/<Artist>/<Album>/… and
    repoints the database at the new location.

      mode="move"  — relocate the file (frees the old spot). Original is gone.
      mode="copy"  — duplicate into the library; the DB points at the tidy
                     copy, the user's original stays exactly where it was.

    `progress(dict)` is called as it goes; `should_stop()` lets a caller halt
    it cleanly between files. Returns a summary dict.
    """
    mode = "copy" if mode == "copy" else "move"
    only_under = os.path.expanduser(only_under) if only_under else None
    conn = get_connection()
    try:
        files = get_all_files(conn)
        plan, already, missing = [], 0, 0
        for f in files:
            src = f["file_path"]
            if not src or not os.path.exists(src):
                missing += 1
                continue
            # Scope to a source folder (e.g. organise only what was just
            # imported from the laptop, leaving the rest of the library alone).
            if only_under and not os.path.normpath(src).startswith(os.path.normpath(only_under)):
                continue
            dest = unique_path(build_destination_path(dest_root, f))
            if os.path.normpath(src) == os.path.normpath(dest) or src.startswith(dest_root):
                already += 1
                continue
            plan.append((f, src, dest))

        total = len(plan)
        if progress:
            progress({"phase": "planned", "mode": mode, "total": total,
                      "done": 0, "failed": 0, "already": already, "missing": missing})

        done = failed = collided = 0
        for i, (rec, src, dest) in enumerate(plan, 1):
            if should_stop and should_stop():
                break
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if mode == "copy":
                    shutil.copy2(src, dest)
                else:
                    shutil.move(src, dest)
                # The DB update can fail with UNIQUE if another (usually dangling
                # duplicate) row already claims `dest`. unique_path only checks
                # disk, not the DB. Make this ATOMIC: if the update fails, undo
                # the move so the file is NEVER stranded at a path no row points
                # at (the 2026-06-02 organiser bug that left 32 files orphaned).
                try:
                    update_file_path(conn, rec["id"], dest)
                    done += 1
                except sqlite3.IntegrityError:
                    if mode == "copy":
                        try: os.remove(dest)
                        except OSError: pass
                    else:
                        try: shutil.move(dest, src)
                        except OSError: pass
                    collided += 1
                    print(f"[organise] dest already claimed in DB, left in place: {src}")
            except Exception as e:
                failed += 1
                print(f"[organise] failed {src}: {e}")
            if progress and (i % 10 == 0 or i == total):
                progress({"phase": "working", "mode": mode, "total": total,
                          "done": done, "failed": failed, "collided": collided,
                          "already": already, "missing": missing})

        # Flush moved/copied files to disk so an un-ejected drive pull can't
        # lose buffered writes or corrupt the just-relocated files.
        try:
            os.sync()
        except Exception:
            pass

        summary = {"phase": "done", "mode": mode, "total": total, "done": done,
                   "failed": failed, "collided": collided, "already": already,
                   "missing": missing}
        if progress:
            progress(summary)
        return summary
    finally:
        conn.close()


def run_organiser(dest_root, dry_run=False):

    if not os.path.exists(DB_PATH):
        print(f"\n  Error: database not found at {DB_PATH}")
        print("  Run schema.py and importer.py first.\n")
        sys.exit(1)

    conn  = get_connection()
    files = get_all_files(conn)

    if not files:
        print("\n  No files in database.\n")
        conn.close()
        return

    print(f"\n  Found {len(files)} files in database.")
    print(f"  Destination: {dest_root}\n")

    # ==========================================================
    # BUILD PLAN
    # Preview every move before touching anything
    # ==========================================================

    plan           = []   # list of (file_record, src, dest) tuples
    already_there  = 0    # files already in the right place
    missing        = 0    # files not found on disk

    for f in files:
        src = f["file_path"]

        # Skip files that don't exist on disk
        if not os.path.exists(src):
            missing += 1
            continue

        dest = build_destination_path(dest_root, f)
        dest = unique_path(dest)

        # Skip files that are already in the destination
        if os.path.normpath(src) == os.path.normpath(dest):
            already_there += 1
            continue

        # Skip files already inside dest_root that just need
        # a minor rename — flag them as already organised
        if src.startswith(dest_root):
            already_there += 1
            continue

        plan.append((f, src, dest))

    print(f"  Already organised: {already_there}")
    print(f"  Not found on disk: {missing}")
    print(f"  To be moved:       {len(plan)}\n")

    if not plan:
        print("  Nothing to do.\n")
        conn.close()
        return

    # Show a sample of what will happen
    sample_size = min(10, len(plan))
    print(f"  Preview (first {sample_size} moves):")
    print(f"  {'—' * 60}")
    for f, src, dest in plan[:sample_size]:
        # Show relative paths for readability
        src_short  = src.replace("/Volumes/EXTERNAL HARD DRIVE 1/", "…/")
        dest_short = dest.replace("/Volumes/EXTERNAL HARD DRIVE 1/", "…/")
        print(f"  FROM: {src_short}")
        print(f"    TO: {dest_short}")
        print()

    if len(plan) > sample_size:
        print(f"  ... and {len(plan) - sample_size} more.\n")

    if dry_run:
        print("  DRY RUN — nothing was moved.\n")
        conn.close()
        return

    # ==========================================================
    # CONFIRM
    # ==========================================================

    print(f"  This will move {len(plan)} files into:")
    print(f"  {dest_root}\n")
    print("  The database will be updated with new paths.")
    print("  Your original files will be moved, not copied.")
    print("  This cannot be undone automatically.\n")

    confirm = input("  Type YES to proceed: ").strip()
    if confirm != "YES":
        print("\n  Cancelled.\n")
        conn.close()
        return

    # ==========================================================
    # MOVE FILES
    # ==========================================================

    print(f"\n  Moving {len(plan)} files...\n")

    moved  = 0
    failed = 0

    for i, (file_record, src, dest) in enumerate(plan, 1):
        try:
            # Create destination folder if it doesn't exist
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            # Move the file
            shutil.move(src, dest)

            # Update the database with the new path
            update_file_path(conn, file_record["id"], dest)

            moved += 1

            # Print progress every 50 files
            if i % 50 == 0 or i == len(plan):
                print(f"  {i}/{len(plan)} moved...")

        except Exception as e:
            failed += 1
            print(f"\n  Failed: {src}")
            print(f"  Reason: {e}\n")
            continue

    conn.close()

    print("\n")
    print("=============================================================")
    print("  Organiser complete.")
    print(f"  Moved:   {moved}")
    print(f"  Failed:  {failed}")
    print(f"  Library: {dest_root}")
    print("=============================================================\n")


# =============================================================
# ENTRY POINT
# =============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Organise Music Room library into a clean folder structure"
    )
    parser.add_argument(
        "--dest",
        type=str,
        default=DEFAULT_DEST,
        help=f"Destination folder (default: {DEFAULT_DEST})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Preview what would be moved without moving anything"
    )
    args = parser.parse_args()

    print("")
    print("=============================================================")
    print("  Music Room — organiser")
    print("=============================================================")

    run_organiser(args.dest, dry_run=args.dry_run)
