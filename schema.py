"""
=============================================================
MUSIC ROOM — schema.py
=============================================================
What this file does:
    Creates the SQLite database and every table inside it.
    Run this once at the start to set up the whole structure.
    If you run it again it won't destroy your data — it only
    creates tables that don't exist yet.

The world this builds:
    The Music Room is the tool — the whole system.
    Inside it lives The Forest — all your places and spaces.
    The Forest contains many places: rooms, events, moods,
    moments, venues, shows. One of those places is The Well.
    The Well is one place among many in the forest — but
    every track lives there by default when imported.
    A track can exist in The Well and in many other places
    simultaneously. The Well is where everything is.
    The rest of the forest is where things belong.

Key design decision — tracks vs files:
    A TRACK is a piece of music. It has one identity.
    It carries all your notes, tags, placements, and history.

    A FILE is a physical version of that track on disk.
    One track can have many files — an MP3 and a FLAC,
    multiple quality versions, a vinyl rip alongside a
    digital download. You designate one file as primary.
    That's the one used for playback and DJ exports.

    This means your notes follow the music, not the file.
    If you upgrade from MP3 to FLAC, your notes survive.

How to run:
    source venv/bin/activate
    python3 schema.py

If you already have a database and just need to add new
columns, run migrate.py instead — it won't touch your data.
=============================================================
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DB lives in the shared data dir (project folder in dev, Application Support
# when bundled). See mr_paths.py.
from mr_paths import DB_PATH  # noqa: E402


def create_database():

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")


    # =============================================================
    # TABLE: places
    # =============================================================
    # A place is any context you'd play music in.
    # The Well (id=1) is created automatically at the bottom.
    # All other places are created by you as needed.
    #
    # A place can span multiple moods and times of night.
    # Each track assigned to a place can carry a 'moment' —
    # where in the arc of that place it belongs.
    #
    # Visual identity fields (colour_primary, colour_secondary,
    # moodboard_images) drive how the place looks in the interface.
    # Atmosphere fields (ambient_audio_path, video_path) are for
    # later stage immersive experience.
    #
    # Examples:
    #   "The After Midnight Club" — inside, 01:00–06:00, hypnotic
    #   "Sunset in a Hilly City Park" — outside, 18:00–21:00, warm
    #   "Bathroom with a Bluetooth Speaker" — inside, any, intimate
    #   "Irish Wedding" — inside+outside, 20:00–03:00, celebratory

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            description         TEXT,

            -- PHYSICAL CHARACTER
            inside_outside      TEXT,   -- 'inside', 'outside', 'both'
            size                TEXT,   -- 'intimate', 'small venue', 'large venue',
                                        -- 'open air', 'headphones'
            crowd_notes         TEXT,   -- free text: who is here, what do they want

            -- TIME & MOOD
            -- A place can span a range of times and hold multiple moods.
            -- moods is comma-separated free text — your vocabulary entirely.
            time_start          TEXT,   -- e.g. "22:00"
            time_end            TEXT,   -- e.g. "06:00"
            moods               TEXT,   -- e.g. "euphoric, hypnotic, melancholic"
            energy              TEXT,   -- 'low', 'medium', 'high', 'variable'
            notes               TEXT,

            -- VISUAL IDENTITY
            -- These drive how this place looks in the interface.
            colour_primary      TEXT,   -- hex e.g. "#1a1a2e" — dominant colour
            colour_secondary    TEXT,   -- hex e.g. "#e94560" — accent colour

            -- MOODBOARD & ATMOSPHERE
            -- Reference material that defines the feel of this place.
            -- Used now for context, used later for immersive entry experience.
            moodboard_images    TEXT,   -- comma-separated file paths to images
            reference_mixes     TEXT,   -- comma-separated URLs to reference sets/mixes
            moodboard_notes     TEXT,   -- free text: links, thoughts, references
            ambient_audio_path  TEXT,   -- path to background audio (later stage)
            image_path          TEXT,   -- path to background image (later stage)
            video_path          TEXT,   -- path to background video (later stage)

            -- IDENTITY
            is_well             INTEGER DEFAULT 0,  -- 1 = this is The Well
            created_at          TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: artists
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            country     TEXT,
            city        TEXT,
            latitude    REAL,
            longitude   REAL,
            bio_link    TEXT,
            bandcamp    TEXT,
            soundcloud  TEXT,
            spotify     TEXT,
            instagram   TEXT,
            website     TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: tracks
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (

            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            title               TEXT,
            artist_id           INTEGER REFERENCES artists(id),
            artist_name         TEXT,
            album               TEXT,
            year                INTEGER,
            label               TEXT,
            track_number        INTEGER,

            source_type         TEXT,   -- 'commercial', 'personal_recording',
                                        -- 'found_sound', 'sound_effect',
                                        -- 'dj_tool', 'acapella', 'sample'
            discovered_via      TEXT,
            discovery_date      TEXT,

            spotify_url         TEXT,
            soundcloud_url      TEXT,
            youtube_url         TEXT,
            bandcamp_url        TEXT,
            other_url           TEXT,

            vinyl_owned         INTEGER DEFAULT 0,
            vinyl_notes         TEXT,

            album_art_path      TEXT,
            custom_image_path   TEXT,
            colour_code         TEXT,

            has_artist          INTEGER DEFAULT 0,
            has_image           INTEGER DEFAULT 0,
            is_placed           INTEGER DEFAULT 0,
            needs_review        INTEGER DEFAULT 0,

            is_deleted          INTEGER DEFAULT 0,
            deleted_at          TEXT,

            date_added          TEXT DEFAULT (datetime('now')),
            last_played         TEXT,
            updated_at          TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: files
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (

            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id        INTEGER NOT NULL REFERENCES tracks(id),

            file_path       TEXT NOT NULL UNIQUE,
            file_format     TEXT,
            file_size_mb    REAL,
            duration_sec    REAL,
            sample_rate     INTEGER,
            bit_depth       INTEGER,
            bitrate_kbps    INTEGER,

            is_primary      INTEGER DEFAULT 0,

            bpm             REAL,
            bpm_verified    INTEGER DEFAULT 0,
            key_note        TEXT,
            key_scale       TEXT,
            key_verified    INTEGER DEFAULT 0,
            loudness_rms    REAL,
            dynamic_range   REAL,
            spectral_centroid REAL,
            bass_energy     REAL,
            mid_energy      REAL,
            treble_energy   REAL,
            has_analysis    INTEGER DEFAULT 0,

            is_deleted      INTEGER DEFAULT 0,
            deleted_at      TEXT,

            date_added      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: place_tracks
    # =============================================================
    # Joins tracks to places. Many-to-many.
    # Every track auto-joins The Well on import.
    #
    # moment: where in the arc of this place this track belongs.
    # Free text, your vocabulary — "opening", "3am", "peak time",
    # "sunrise", "after the crowd thins". Optional.
    #
    # moment_order: optional numeric ordering within a moment
    # so you can sort tracks within e.g. "peak time".

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS place_tracks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id        INTEGER NOT NULL REFERENCES places(id),
            track_id        INTEGER NOT NULL REFERENCES tracks(id),
            moment          TEXT,       -- time/mood within this place
            moment_order    INTEGER,    -- ordering within a moment
            added_at        TEXT DEFAULT (datetime('now')),
            UNIQUE(place_id, track_id)
        )
    """)


    # =============================================================
    # TABLE: tags
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            colour      TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: track_tags
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS track_tags (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id    INTEGER NOT NULL REFERENCES tracks(id),
            tag_id      INTEGER NOT NULL REFERENCES tags(id),
            added_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(track_id, tag_id)
        )
    """)


    # =============================================================
    # TABLE: notes
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id        INTEGER NOT NULL REFERENCES tracks(id),
            note_text       TEXT NOT NULL,
            audio_timestamp TEXT,
            note_type       TEXT,   -- 'general', 'cue_point', 'transition',
                                    -- 'technical', 'feeling'
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: sets
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            place_id        INTEGER REFERENCES places(id),
            set_date        TEXT,
            duration_min    INTEGER,
            notes           TEXT,
            research        TEXT,
            external_link   TEXT,
            vinyl_required  INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # TABLE: set_tracks
    # =============================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS set_tracks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id          INTEGER NOT NULL REFERENCES sets(id),
            track_id        INTEGER NOT NULL REFERENCES tracks(id),
            position        INTEGER,
            transition_note TEXT,
            vinyl_needed    INTEGER DEFAULT 0,
            added_at        TEXT DEFAULT (datetime('now'))
        )
    """)


    # =============================================================
    # CREATE THE WELL
    # =============================================================

    cursor.execute("""
        INSERT OR IGNORE INTO places (id, name, description, is_well)
        VALUES (
            1,
            'Music Room',
            'Every track lives here by default. One place among many in the forest — but the one that holds everything.',
            1
        )
    """)

    conn.commit()
    conn.close()

    print("")
    print("=============================================================")
    print("  Music Room — database created.")
    print(f"  {DB_PATH}")
    print("")
    print("  Tables:")
    print("    places        the forest — rooms, events, moods, venues")
    print("    artists       people behind the music")
    print("    tracks        musical identity — notes, tags, history")
    print("    files         physical files linked to tracks")
    print("    place_tracks  which tracks live in which places + moments")
    print("    tags          your vocabulary — genre, mood, context")
    print("    track_tags    tags applied to tracks")
    print("    notes         timestamped notes, cue ideas, feelings")
    print("    sets          DJ sets and radio shows")
    print("    set_tracks    tracks within sets, transition notes")
    print("")
    print("  The Well has been created.")
    print("=============================================================")
    print("")


if __name__ == "__main__":
    create_database()
