"""
=============================================================
MUSIC ROOM — engine_exporter.py
=============================================================
Exports a place or set as an Engine DJ-compatible USB library.

Output:
    A downloadable .zip containing:
        Engine Library/
            Database2/
                m.db    — track metadata + playlist, ready for Engine DJ

HOW TO USE ON THE SC LIVE 4:
    1. Export from Music Room (place or set page → Engine DJ export button)
    2. Unzip the downloaded archive
    3. Copy the "Engine Library" folder to the ROOT of a FAT32/exFAT USB drive
    4. Copy your audio files to the same drive preserving their relative paths
       (or just use the drive they already live on and point Engine DJ at it)
    5. Plug into the SC Live 4 — it reads the library from "Engine Library/Database2/m.db"

SCHEMA:
    Engine DJ v2.20 (Database2 format). Compatible with Engine OS 2.x+ and
    all current SC Live / SC6000 hardware.

    musicalKey uses Open Key integers (same wheel as Camelot, different numbers):
        1=C maj  2=G maj  3=D maj  4=A maj  5=E maj  6=B maj
        7=F# maj 8=Db maj 9=Ab maj 10=Eb maj 11=Bb maj 12=F maj
        13=A min 14=E min 15=B min 16=F# min 17=C# min 18=G# min
        19=D# min 20=Bb min 21=F min 22=C min 23=G min 24=D min
=============================================================
"""

import sqlite3
import os
import zipfile
import tempfile
import uuid as _uuid

# Open Key integer map keyed by "note scale" string
MUSICAL_KEY_MAP = {
    "C major":   1,  "G major":   2,  "D major":  3,  "A major":  4,
    "E major":   5,  "B major":   6,  "F# major": 7,  "Db major": 8,
    "Ab major":  9,  "Eb major": 10,  "Bb major": 11, "F major":  12,
    "A minor":  13,  "E minor":  14,  "B minor":  15, "F# minor": 16,
    "C# minor": 17,  "G# minor": 18,  "D# minor": 19, "Bb minor": 20,
    "F minor":  21,  "C minor":  22,  "G minor":  23, "D minor":  24,
}

FILE_TYPE_MAP = {
    "mp3": "mp3", "flac": "flac", "aiff": "aiff", "aif": "aiff",
    "wav": "wav", "ogg": "ogg", "m4a": "m4a", "alac": "alac",
}


def _create_schema(cur):
    cur.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS Information (
            id                                    INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid                                  TEXT,
            schemaVersionMajor                    INTEGER,
            schemaVersionMinor                    INTEGER,
            schemaVersionPatch                    INTEGER,
            currentPlayedIndiciator               INTEGER,
            lastRekordboxLibraryImportReadCounter INTEGER
        );

        CREATE TABLE IF NOT EXISTS AlbumArt (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            hash     TEXT,
            albumArt BLOB
        );

        CREATE TABLE IF NOT EXISTS Track (
            id                                        INTEGER PRIMARY KEY AUTOINCREMENT,
            playOrder                                 INTEGER,
            length                                    INTEGER,
            lengthCalculated                          INTEGER,
            bpm                                       INTEGER,
            year                                      INTEGER,
            path                                      TEXT,
            filename                                  TEXT,
            bitrate                                   INTEGER,
            bpmAnalyzed                               REAL,
            albumArtId                                INTEGER,
            fileBytes                                 INTEGER,
            title                                     TEXT,
            artist                                    TEXT,
            album                                     TEXT,
            genre                                     TEXT,
            comment                                   TEXT,
            label                                     TEXT,
            composer                                  TEXT,
            remixer                                   TEXT,
            key                                       INTEGER,
            rating                                    INTEGER,
            albumArt                                  TEXT,
            timeLastPlayed                            TEXT,
            isPlayed                                  INTEGER,
            fileType                                  TEXT,
            isAnalyzed                                TEXT,
            dateCreated                               TEXT,
            dateAdded                                 TEXT,
            isAvailable                               INTEGER,
            isMetadataOfPackedTrackChanged            INTEGER,
            isPerfomanceDataOfPackedTrackChanged      INTEGER,
            playedIndicator                           INTEGER,
            isMetadataImported                        INTEGER,
            pdbImportKey                              INTEGER,
            streamingSource                           TEXT,
            uri                                       TEXT,
            isBeatGridLocked                          INTEGER,
            originDatabaseUuid                        TEXT,
            originTrackId                             INTEGER,
            trackData                                 BLOB,
            overviewWaveFormData                      BLOB,
            beatData                                  BLOB,
            quickCues                                 BLOB,
            loops                                     BLOB,
            thirdPartySourceId                        INTEGER,
            streamingFlags                            INTEGER,
            explicitLyrics                            INTEGER,
            activeOnLoadLoops                         INTEGER
        );

        CREATE TABLE IF NOT EXISTS PlaylistEntity (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            title                TEXT,
            parentListId         INTEGER,
            isPersisted          INTEGER,
            nextListId           INTEGER,
            lastEditTime         TEXT,
            isExplicitlyExported INTEGER
        );

        CREATE TABLE IF NOT EXISTS PlaylistTrackList (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            playlistId                  INTEGER,
            trackId                     INTEGER,
            trackIdInOriginDatabase     INTEGER,
            databaseUuid                TEXT,
            trackNumber                 INTEGER
        );

        CREATE TABLE IF NOT EXISTS Historylist (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            title                TEXT,
            parentListId         INTEGER,
            isPersisted          INTEGER,
            nextListId           INTEGER,
            lastEditTime         TEXT,
            isExplicitlyExported INTEGER
        );

        CREATE TABLE IF NOT EXISTS HistorylistTrackList (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            historylistId               INTEGER,
            trackId                     INTEGER,
            trackIdInOriginDatabase     INTEGER,
            databaseUuid                TEXT,
            date                        TEXT,
            trackNumber                 INTEGER
        );

        CREATE TABLE IF NOT EXISTS Preparelist (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        );

        CREATE TABLE IF NOT EXISTS PreparelistTrackList (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            playlistId                  INTEGER,
            trackId                     INTEGER,
            trackIdInOriginDatabase     INTEGER,
            databaseUuid                TEXT,
            trackNumber                 INTEGER
        );
    """)


def write_engine_db(db_path, tracks, playlists, path_for=None):
    """
    Write an Engine DJ Database2 m.db at db_path (the file must not exist yet
    or will be replaced).

    tracks:    list of track dicts — keys: id, title, artist_name, album, year,
               label, file_path, file_format, duration_sec, bpm, key_note,
               key_scale, has_analysis, bitrate_kbps, file_size_mb
    playlists: [{"name": str, "track_ids": [music-room track ids]}] — each
               becomes an Engine playlist, in order.
    path_for:  fn(track) -> the string stored in Track.path. Default = the
               absolute file_path; a USB export passes stick-relative paths
               ("../Music Room/<scope>/<file>", relative to "Engine Library"
               as Engine OS expects on a stick).

    Returns missing_files (paths not found on disk — informational).
    """
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        _create_schema(cur)

        # Information row — schema 2.20.0
        db_uuid = str(_uuid.uuid4())
        cur.execute("""
            INSERT INTO Information
                (uuid, schemaVersionMajor, schemaVersionMinor, schemaVersionPatch,
                 currentPlayedIndiciator, lastRekordboxLibraryImportReadCounter)
            VALUES (?, 2, 20, 0, 0, 0)
        """, (db_uuid,))

        # Default no-art entry (required — track albumArtId=1 means no art)
        cur.execute("INSERT INTO AlbumArt (id, hash, albumArt) VALUES (1, NULL, NULL)")

        missing_files = []
        engine_id_by_mr = {}    # music room track id -> engine db row id

        for i, t in enumerate(tracks):
            fp       = t.get("file_path") or ""
            filename = os.path.basename(fp)
            fmt      = (t.get("file_format") or "").lower().lstrip(".")
            stored   = path_for(t) if path_for else fp

            # Check file exists on disk
            if fp and not os.path.exists(fp):
                missing_files.append(fp)

            # Duration in milliseconds
            dur_ms = int((t.get("duration_sec") or 0) * 1000)

            # BPM — Engine DJ stores as integer × 100 in the bpm column
            # and as float in bpmAnalyzed
            bpm_raw      = t.get("bpm")
            bpm_int      = int(round(float(bpm_raw) * 100)) if bpm_raw else 0
            bpm_analyzed = float(bpm_raw) if bpm_raw else 0.0

            # Key — convert "A minor" → Open Key integer
            key_note  = t.get("key_note")
            key_scale = t.get("key_scale") or "major"
            key_int   = 0
            if key_note:
                key_str = f"{key_note} {key_scale}"
                key_int = MUSICAL_KEY_MAP.get(key_str, 0)

            # File type string Engine DJ expects
            file_type = FILE_TYPE_MAP.get(fmt, fmt or "mp3")

            # isAnalyzed: "1" if we have analysis data, "0" otherwise
            is_analyzed = "1" if t.get("has_analysis") else "0"

            # Bitrate (Engine DJ stores as bits per second)
            bitrate = int((t.get("bitrate_kbps") or 0)) * 1000

            # File size in bytes
            file_bytes = int((t.get("file_size_mb") or 0) * 1024 * 1024)

            cur.execute("""
                INSERT INTO Track (
                    playOrder, length, lengthCalculated, bpm, year, path, filename,
                    bitrate, bpmAnalyzed, albumArtId, fileBytes,
                    title, artist, album, genre, comment, label,
                    composer, remixer, key, rating, albumArt,
                    timeLastPlayed, isPlayed, fileType, isAnalyzed,
                    dateCreated, dateAdded, isAvailable,
                    isMetadataOfPackedTrackChanged, isPerfomanceDataOfPackedTrackChanged,
                    playedIndicator, isMetadataImported, pdbImportKey,
                    streamingSource, uri, isBeatGridLocked,
                    originDatabaseUuid, originTrackId,
                    trackData, overviewWaveFormData, beatData, quickCues, loops,
                    thirdPartySourceId, streamingFlags, explicitLyrics, activeOnLoadLoops
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, 1, ?,
                    ?, ?, ?, '', '', ?,
                    '', '', ?, 0, NULL,
                    NULL, 0, ?, ?,
                    NULL, NULL, 1,
                    0, 0,
                    0, 1, 0,
                    NULL, NULL, 0,
                    NULL, 0,
                    NULL, NULL, NULL, NULL, NULL,
                    0, 0, 0, 0
                )
            """, (
                i + 1,          # playOrder
                dur_ms,         # length (ms)
                dur_ms,         # lengthCalculated (ms)
                bpm_int,        # bpm (integer × 100)
                t.get("year") or 0,
                stored,         # path (absolute, or stick-relative via path_for)
                filename,
                bitrate,
                bpm_analyzed,   # bpmAnalyzed (float)
                file_bytes,
                (t.get("title") or "").strip() or "Untitled",
                (t.get("artist_name") or "").strip() or "Unknown",
                (t.get("album") or "").strip(),
                (t.get("label") or "").strip(),
                key_int,
                file_type,
                is_analyzed,
            ))

            engine_id_by_mr[t["id"]] = cur.lastrowid

        # Playlists — each a PlaylistEntity + ordered track links
        for pl in playlists:
            cur.execute("""
                INSERT INTO PlaylistEntity
                    (title, parentListId, isPersisted, nextListId, lastEditTime, isExplicitlyExported)
                VALUES (?, 0, 1, 0, datetime('now'), 1)
            """, (pl["name"],))
            playlist_id = cur.lastrowid
            pos = 0
            for mr_id in pl["track_ids"]:
                eid = engine_id_by_mr.get(mr_id)
                if eid is None:
                    continue
                pos += 1
                cur.execute("""
                    INSERT INTO PlaylistTrackList
                        (playlistId, trackId, trackIdInOriginDatabase, databaseUuid, trackNumber)
                    VALUES (?, ?, ?, ?, ?)
                """, (playlist_id, eid, eid, db_uuid, pos))

        conn.commit()
        return missing_files
    finally:
        conn.close()


def build_engine_library(tracks, playlist_name):
    """
    Build a complete Engine DJ library ZIP (one playlist, absolute paths) —
    the downloadable flavour used by the place/set export buttons.
    Returns (zip_bytes, missing_files).
    """
    tmpdir = tempfile.mkdtemp(prefix="musicroom_engine_")
    try:
        db2_dir = os.path.join(tmpdir, "Engine Library", "Database2")
        os.makedirs(db2_dir, exist_ok=True)
        missing_files = write_engine_db(
            os.path.join(db2_dir, "m.db"), tracks,
            [{"name": playlist_name, "track_ids": [t["id"] for t in tracks]}])

        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(tmpdir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arcname = os.path.relpath(full, tmpdir)
                    zf.write(full, arcname)
        return buf.getvalue(), missing_files
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
