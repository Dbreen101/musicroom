"""
=============================================================
MUSIC ROOM — migrate.py
=============================================================
Safe to run multiple times. Only adds what doesn't exist.
Never destroys data.

Migration history:
    v1  places, place_tracks — context and colour columns
    v2  notes.voice_note_path, files.analysis_status
    v3  set_tracks.transition_note
    v4  artist_profiles — enriched artist data (AI-fetched, cached)
    v5  track_enrichment — per-track context data
    v6  quiz_sessions + quiz_questions — quiz history and scoring
    v7  notes.whisper_transcript — Whisper auto-transcription of voice notes
    v9  bosca — persistent DJ crate, per-track notes
    v10 sets.set_type — 'charted' or 'freestyle'
    v12 artwork fields on tracks, track_overlays, stickers
    v13 tracks.is_oneshot; artwork_source 'not_found' backfill
    v26 tracks.isrc + isrc_checked_at; DSP states renamed to on_dsp/not_on_dsp
    v27 track_isrcs (multi-ISRC per track), seeded from tracks.isrc
    v28 Explore feed — sources.feed_url/feed_checked_at + feed_items table
    v29 one-time: reset stale 'not_on_dsp' (old Spotify era) → untested
    v30 Explore curation — interests table + sources.topics + serendipity
    v31 cultural enrichment — artist_profiles cols + label_profiles table
    v32 place customization — places.ambient_audio_volume
    v33 place themes — bg/text/title-font/body-font/mood per place
    v34 illustration colours — light/structure/outline/detail per place
    v35 files.brightness_score — combined Presence + Brilliance dB
    v36 files.content_hash + index — byte-identical duplicate detection
=============================================================
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DB lives in the shared data dir (project folder in dev, Application Support
# when bundled). See mr_paths.py.
from mr_paths import DB_PATH  # noqa: E402


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]


def table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"\n  Error: database not found at {DB_PATH}")
        print("  Run schema.py first.\n")
        return

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("")
    print("=============================================================")
    print("  Music Room — running migration")
    print("=============================================================")

    changes = 0

    # ------------------------------------------------------------------
    # v1 — places
    # ------------------------------------------------------------------
    for col, typ in [
        ("inside_outside",   "TEXT"),
        ("moods",            "TEXT"),
        ("time_start",       "TEXT"),
        ("time_end",         "TEXT"),
        ("crowd_notes",      "TEXT"),
        ("colour_primary",   "TEXT"),
        ("colour_secondary", "TEXT"),
        ("moodboard_images", "TEXT"),
        ("reference_mixes",  "TEXT"),
    ]:
        if not column_exists(cursor, "places", col):
            cursor.execute(f"ALTER TABLE places ADD COLUMN {col} {typ}")
            print(f"  + places.{col}")
            changes += 1
        else:
            print(f"  ✓ places.{col}")

    for col, typ in [("moment", "TEXT"), ("moment_order", "INTEGER")]:
        if not column_exists(cursor, "place_tracks", col):
            cursor.execute(f"ALTER TABLE place_tracks ADD COLUMN {col} {typ}")
            print(f"  + place_tracks.{col}")
            changes += 1
        else:
            print(f"  ✓ place_tracks.{col}")

    # ------------------------------------------------------------------
    # v2 — notes voice_note_path, files analysis_status
    # ------------------------------------------------------------------
    if not column_exists(cursor, "notes", "voice_note_path"):
        cursor.execute("ALTER TABLE notes ADD COLUMN voice_note_path TEXT")
        print("  + notes.voice_note_path")
        changes += 1
    else:
        print("  ✓ notes.voice_note_path")

    if not column_exists(cursor, "files", "analysis_status"):
        cursor.execute("ALTER TABLE files ADD COLUMN analysis_status TEXT DEFAULT 'none'")
        cursor.execute("UPDATE files SET analysis_status = 'done' WHERE has_analysis = 1")
        print("  + files.analysis_status")
        changes += 1
    else:
        print("  ✓ files.analysis_status")

    # ------------------------------------------------------------------
    # v3 — set_tracks transition_note
    # ------------------------------------------------------------------
    if table_exists(cursor, "set_tracks"):
        if not column_exists(cursor, "set_tracks", "transition_note"):
            cursor.execute("ALTER TABLE set_tracks ADD COLUMN transition_note TEXT")
            print("  + set_tracks.transition_note")
            changes += 1
        else:
            print("  ✓ set_tracks.transition_note")

    # ------------------------------------------------------------------
    # v4 — artist_profiles
    # ------------------------------------------------------------------
    if not table_exists(cursor, "artist_profiles"):
        cursor.execute("""
            CREATE TABLE artist_profiles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_name     TEXT NOT NULL UNIQUE,
                country         TEXT,
                city            TEXT,
                latitude        REAL,
                longitude       REAL,
                active_from     INTEGER,
                active_to       INTEGER,
                gender          TEXT,
                ethnicity_notes TEXT,
                genres          TEXT,
                labels          TEXT,
                scene           TEXT,
                influences      TEXT,
                influenced_by   TEXT,
                bio_summary     TEXT,
                notable_works   TEXT,
                wikipedia_note  TEXT,
                enriched_at     TEXT,
                fetch_error     TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: artist_profiles")
        changes += 1
    else:
        print("  ✓ table: artist_profiles")

    # ------------------------------------------------------------------
    # v5 — track_enrichment
    # ------------------------------------------------------------------
    if not table_exists(cursor, "track_enrichment"):
        cursor.execute("""
            CREATE TABLE track_enrichment (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id        INTEGER NOT NULL UNIQUE REFERENCES tracks(id),
                label_confirmed TEXT,
                year_confirmed  INTEGER,
                catalogue_no    TEXT,
                release_format  TEXT,
                subgenre        TEXT,
                scene           TEXT,
                cultural_notes  TEXT,
                compatible_track_ids TEXT,
                enriched_at     TEXT,
                fetch_error     TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: track_enrichment")
        changes += 1
    else:
        print("  ✓ table: track_enrichment")

    # ------------------------------------------------------------------
    # v6 — quiz_sessions + quiz_questions
    # ------------------------------------------------------------------
    if not table_exists(cursor, "quiz_sessions"):
        cursor.execute("""
            CREATE TABLE quiz_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                mode        TEXT,
                scope       TEXT,
                score       INTEGER DEFAULT 0,
                total       INTEGER DEFAULT 0,
                completed   INTEGER DEFAULT 0,
                started_at  TEXT DEFAULT (datetime('now')),
                finished_at TEXT
            )
        """)
        print("  + table: quiz_sessions")
        changes += 1
    else:
        print("  ✓ table: quiz_sessions")

    if not table_exists(cursor, "quiz_questions"):
        cursor.execute("""
            CREATE TABLE quiz_questions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER REFERENCES quiz_sessions(id),
                track_id        INTEGER REFERENCES tracks(id),
                question_type   TEXT,
                question_text   TEXT,
                correct_answer  TEXT,
                user_answer     TEXT,
                is_correct      INTEGER,
                explanation     TEXT,
                asked_at        TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: quiz_questions")
        changes += 1
    else:
        print("  ✓ table: quiz_questions")

    # ------------------------------------------------------------------
    # v7 — notes.whisper_transcript
    # Populated by background Whisper transcription after voice note save.
    # Empty string means not yet transcribed; NULL means no voice note.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "notes", "whisper_transcript"):
        cursor.execute("ALTER TABLE notes ADD COLUMN whisper_transcript TEXT")
        print("  + notes.whisper_transcript")
        changes += 1
    else:
        print("  ✓ notes.whisper_transcript")

    # ------------------------------------------------------------------
    # v8 — shows + show_sets
    # Radio show mode: a show links to one or more sets, has a recording.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "shows"):
        cursor.execute("""
            CREATE TABLE shows (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT NOT NULL,
                show_date       TEXT,
                series          TEXT,
                episode_number  INTEGER,
                description     TEXT,
                recording_path  TEXT,
                recording_url   TEXT,
                duration_sec    INTEGER,
                is_published    INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: shows")
        changes += 1
    else:
        print("  \u2713 table: shows")

    if not table_exists(cursor, "show_sets"):
        cursor.execute("""
            CREATE TABLE show_sets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                show_id     INTEGER NOT NULL REFERENCES shows(id),
                set_id      INTEGER NOT NULL REFERENCES sets(id),
                position    INTEGER DEFAULT 1
            )
        """)
        print("  + table: show_sets")
        changes += 1
    else:
        print("  \u2713 table: show_sets")

    # ------------------------------------------------------------------
    # v9 — bosca (DJ crate)
    # Persistent record box carried between places. Notes live in the
    # bosca context only — they're not permanent track notes.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "bosca"):
        cursor.execute("""
            CREATE TABLE bosca (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id    INTEGER NOT NULL UNIQUE REFERENCES tracks(id),
                position    INTEGER NOT NULL DEFAULT 0,
                note        TEXT,
                added_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: bosca")
        changes += 1
    else:
        print("  ✓ table: bosca")

    # ------------------------------------------------------------------
    # v10 — sets.set_type
    # 'charted' = programmed, ordered set with transitions.
    # 'freestyle' = unordered pool of records for a live improv set.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "sets", "set_type"):
        cursor.execute("ALTER TABLE sets ADD COLUMN set_type TEXT DEFAULT 'charted'")
        print("  + sets.set_type")
        changes += 1
    else:
        print("  ✓ sets.set_type")

    # ------------------------------------------------------------------
    # v11 — settings table + active listening (sessions + notes)
    # ------------------------------------------------------------------
    if not table_exists(cursor, "settings"):
        cursor.execute("""
            CREATE TABLE settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        cursor.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [
                ("export_dir", ""),
                ("listening_shortcuts",
                 '{"1":"Rhythm","2":"Melody","3":"Energy","4":"Texture","5":"Set placement","6":"Reference","7":"Production","8":"Vocals"}'),
            ]
        )
        print("  + table: settings (with defaults)")
        changes += 1
    else:
        print("  ✓ table: settings")

    if not table_exists(cursor, "listening_sessions"):
        cursor.execute("""
            CREATE TABLE listening_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id   INTEGER NOT NULL REFERENCES tracks(id),
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at   TEXT
            )
        """)
        print("  + table: listening_sessions")
        changes += 1
    else:
        print("  ✓ table: listening_sessions")

    if not table_exists(cursor, "listening_notes"):
        cursor.execute("""
            CREATE TABLE listening_notes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    INTEGER NOT NULL REFERENCES listening_sessions(id),
                track_id      INTEGER NOT NULL REFERENCES tracks(id),
                timestamp_sec REAL DEFAULT 0,
                note_text     TEXT NOT NULL,
                note_category TEXT DEFAULT '',
                is_voice      INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: listening_notes")
        changes += 1
    else:
        print("  ✓ table: listening_notes")

    # ------------------------------------------------------------------
    # v12 — artwork + overlays + stickers
    # artwork_path/source/verified on tracks; overlay canvas per track;
    # sticker library for reusable image stamps.
    # ------------------------------------------------------------------
    for col_name, col_def in [
        ("artwork_path",     "TEXT"),
        ("artwork_source",   "TEXT"),
        ("artwork_verified", "INTEGER DEFAULT 0"),
    ]:
        if not column_exists(cursor, "tracks", col_name):
            cursor.execute(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_def}")
            print(f"  + tracks.{col_name}")
            changes += 1
        else:
            print(f"  ✓ tracks.{col_name}")

    if not table_exists(cursor, "track_overlays"):
        cursor.execute("""
            CREATE TABLE track_overlays (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id     INTEGER NOT NULL REFERENCES tracks(id),
                place_id     INTEGER REFERENCES places(id),
                overlay_type TEXT NOT NULL DEFAULT 'postit',
                content      TEXT,
                pos_x_pct    REAL DEFAULT 10.0,
                pos_y_pct    REAL DEFAULT 10.0,
                width_pct    REAL DEFAULT 30.0,
                height_pct   REAL DEFAULT 25.0,
                rotation     REAL DEFAULT 0.0,
                z_index      INTEGER DEFAULT 1,
                color        TEXT DEFAULT '#fef08a',
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: track_overlays")
        changes += 1
    else:
        print("  ✓ table: track_overlays")

    # place_id on track_overlays (added in v12b — scope overlays to a place)
    if table_exists(cursor, "track_overlays") and not column_exists(cursor, "track_overlays", "place_id"):
        cursor.execute("ALTER TABLE track_overlays ADD COLUMN place_id INTEGER REFERENCES places(id)")
        print("  + track_overlays.place_id")
        changes += 1
    else:
        if table_exists(cursor, "track_overlays"):
            print("  ✓ track_overlays.place_id")

    if not table_exists(cursor, "stickers"):
        cursor.execute("""
            CREATE TABLE stickers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL DEFAULT '',
                image_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  + table: stickers")
        changes += 1
    else:
        print("  ✓ table: stickers")

    # ------------------------------------------------------------------
    # v13 — is_oneshot on tracks; artwork_source 'not_found' backfill
    # ------------------------------------------------------------------
    if not column_exists(cursor, "tracks", "is_oneshot"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN is_oneshot INTEGER DEFAULT 0")
        cursor.execute("""
            UPDATE tracks SET is_oneshot = 1
            WHERE id IN (
                SELECT track_id FROM files
                WHERE is_primary = 1 AND duration_sec > 0 AND duration_sec < 5
            )
        """)
        n = cursor.rowcount
        print(f"  + tracks.is_oneshot ({n} marked as one-shots from duration < 5s)")

        # One-time backfill: mark tracks that have no artwork and no source as
        # 'not_found' — the user has confirmed the batch has already run.
        cursor.execute("""
            UPDATE tracks
            SET artwork_source = 'not_found'
            WHERE artwork_path IS NULL
              AND (artwork_source IS NULL OR artwork_source = '')
              AND is_deleted = 0
        """)
        nf = cursor.rowcount
        print(f"  + artwork_source backfill — {nf} tracks marked 'not_found'")
        changes += 1
    else:
        print("  ✓ tracks.is_oneshot")

    # ------------------------------------------------------------------
    # v14 — sources (Explore — curated outside-world music links)
    # ------------------------------------------------------------------
    if not table_exists(cursor, "sources"):
        cursor.execute("""
            CREATE TABLE sources (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                url             TEXT NOT NULL,
                kind            TEXT NOT NULL DEFAULT 'magazine',
                description     TEXT,
                colour          TEXT,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                last_visited_at TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        # Seed with a few well-known publications — user can edit/delete freely.
        seeds = [
            ("Resident Advisor",  "https://ra.co/",                      "magazine", "Reviews, news, mixes — the long-standing dance-music journal."),
            ("FACT Magazine",     "https://www.factmag.com/",            "magazine", "Mixes, interviews, deep features."),
            ("The Wire",          "https://www.thewire.co.uk/",          "magazine", "Adventurous music in print and online — long-form, archival."),
            ("Crack Magazine",    "https://crackmagazine.net/",          "magazine", "Contemporary culture, mixes, reviews."),
            ("Mixmag",            "https://mixmag.net/",                 "magazine", "Charts, mixes, festival coverage."),
            ("NTS Radio",         "https://www.nts.live/",               "station",  "Independent online radio — wide curation, archived shows."),
            ("Rinse FM",          "https://rinse.fm/",                   "station",  "Live and archived shows from DJs across UK and beyond."),
            ("Worldwide FM",      "https://worldwidefm.net/",            "station",  "Gilles Peterson's station — global curation."),
            ("Boiler Room",       "https://boilerroom.tv/",              "station",  "Live recorded sets from around the world."),
            ("Bandcamp Daily",    "https://daily.bandcamp.com/",         "blog",     "Editorial digging into artists and scenes on Bandcamp."),
            # ("Fact Mixes", …/category/podcasts-and-mixes/) removed 2026-07-04:
            # the category page 404s now, and FACT Magazine is already seeded.
            ("All Hands Records", "https://allhandsrecords.bandcamp.com/", "label",  "Example: track a label whose taste you trust."),
        ]
        cursor.executemany(
            "INSERT INTO sources (name,url,kind,description,sort_order) VALUES (?,?,?,?,?)",
            [(n, u, k, d, i) for i, (n, u, k, d) in enumerate(seeds)]
        )
        print(f"  + table: sources ({len(seeds)} seeded)")
        changes += 1
    else:
        print("  ✓ table: sources")

    # ------------------------------------------------------------------
    # v15 — place positions (x_pct, y_pct) for the draggable forest map
    # ------------------------------------------------------------------
    if not column_exists(cursor, "places", "x_pct"):
        cursor.execute("ALTER TABLE places ADD COLUMN x_pct REAL")
        print("  + places.x_pct")
        changes += 1
    else:
        print("  ✓ places.x_pct")
    if not column_exists(cursor, "places", "y_pct"):
        cursor.execute("ALTER TABLE places ADD COLUMN y_pct REAL")
        print("  + places.y_pct")
        changes += 1
    else:
        print("  ✓ places.y_pct")

    # ------------------------------------------------------------------
    # v15 — articles (saved-for-later links / inspo)
    # ------------------------------------------------------------------
    if not table_exists(cursor, "articles"):
        cursor.execute("""
            CREATE TABLE articles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT NOT NULL,
                title           TEXT,
                description     TEXT,
                source_name     TEXT,
                place_id        INTEGER REFERENCES places(id) ON DELETE SET NULL,
                tags            TEXT,
                is_read         INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now')),
                last_visited_at TEXT
            )
        """)
        cursor.execute("CREATE INDEX idx_articles_place ON articles(place_id)")
        cursor.execute("CREATE INDEX idx_articles_created ON articles(created_at DESC)")
        print("  + table: articles")
        changes += 1
    else:
        print("  ✓ table: articles")

    # ------------------------------------------------------------------
    # v16 — places.illustration_kind (manual override of auto-pick)
    # ------------------------------------------------------------------
    if not column_exists(cursor, "places", "illustration_kind"):
        cursor.execute("ALTER TABLE places ADD COLUMN illustration_kind TEXT")
        print("  + places.illustration_kind")
        changes += 1
    else:
        print("  ✓ places.illustration_kind")

    # ------------------------------------------------------------------
    # v19 — perceptual 6-band loudness + vocal score for files
    # Replaces the old bass/mid/treble fractional bars (which always read
    # ~85% bass because raw FFT bins decay with frequency). New columns
    # store A-weighted dB per band (absolute, comparable across tracks)
    # plus a vocal_score in 0..1.
    # ------------------------------------------------------------------
    for col in (
        "band_sub", "band_bass", "band_lowmid",
        "band_body", "band_presence", "band_brilliance",
        "vocal_score",
    ):
        if not column_exists(cursor, "files", col):
            cursor.execute(f"ALTER TABLE files ADD COLUMN {col} REAL")
            print(f"  + files.{col}")
            changes += 1
        else:
            print(f"  ✓ files.{col}")

    # ------------------------------------------------------------------
    # v18 — genres + track_genres (first-class genre data per track)
    # ------------------------------------------------------------------
    if not table_exists(cursor, "genres"):
        cursor.execute("""
            CREATE TABLE genres (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT NOT NULL UNIQUE
            )
        """)
        print("  + table: genres")
        changes += 1
    else:
        print("  ✓ table: genres")
    if not table_exists(cursor, "track_genres"):
        cursor.execute("""
            CREATE TABLE track_genres (
                track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                genre_id INTEGER NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
                PRIMARY KEY (track_id, genre_id)
            )
        """)
        cursor.execute("CREATE INDEX idx_track_genres_genre ON track_genres(genre_id)")
        print("  + table: track_genres")
        changes += 1
    else:
        print("  ✓ table: track_genres")

    # ------------------------------------------------------------------
    # v17 — wishlist (tracks/records to buy; bandcamp/spotify/youtube links etc.)
    # ------------------------------------------------------------------
    if not table_exists(cursor, "wishlist"):
        cursor.execute("""
            CREATE TABLE wishlist (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT NOT NULL,
                title           TEXT,
                artist          TEXT,
                source          TEXT,
                notes           TEXT,
                place_id        INTEGER REFERENCES places(id) ON DELETE SET NULL,
                tags            TEXT,
                status          TEXT NOT NULL DEFAULT 'wishing',
                created_at      TEXT DEFAULT (datetime('now')),
                last_visited_at TEXT
            )
        """)
        cursor.execute("CREATE INDEX idx_wishlist_place ON wishlist(place_id)")
        cursor.execute("CREATE INDEX idx_wishlist_status ON wishlist(status)")
        cursor.execute("CREATE INDEX idx_wishlist_created ON wishlist(created_at DESC)")
        print("  + table: wishlist")
        changes += 1
    else:
        print("  ✓ table: wishlist")

    # ------------------------------------------------------------------
    # v20 — resources (Learn → Resources tab)
    # Flexible store for websites, PDFs, own notes, videos, books, etc.
    # `kind` is free-text so new kinds can be added without schema changes.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "resources"):
        cursor.execute("""
            CREATE TABLE resources (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                kind            TEXT NOT NULL DEFAULT 'link',
                title           TEXT NOT NULL,
                url             TEXT,
                file_path       TEXT,
                body            TEXT,
                description     TEXT,
                category        TEXT,
                tags            TEXT,
                place_id        INTEGER REFERENCES places(id) ON DELETE SET NULL,
                is_pinned       INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT,
                last_visited_at TEXT
            )
        """)
        cursor.execute("CREATE INDEX idx_resources_kind     ON resources(kind)")
        cursor.execute("CREATE INDEX idx_resources_category ON resources(category)")
        cursor.execute("CREATE INDEX idx_resources_created  ON resources(created_at DESC)")
        print("  + table: resources")
        changes += 1
    else:
        print("  ✓ table: resources")

    # ------------------------------------------------------------------
    # v21 — Spotify bridge: cache of remote tracks + ID links into local
    # tables so we can dedupe re-syncs and recognise when a wishlist /
    # library track originated on Spotify.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "spotify_tracks"):
        cursor.execute("""
            CREATE TABLE spotify_tracks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                spotify_id      TEXT NOT NULL UNIQUE,
                title           TEXT,
                artist          TEXT,
                album           TEXT,
                album_image_url TEXT,
                duration_ms     INTEGER,
                is_saved        INTEGER NOT NULL DEFAULT 0,
                in_playlist_ids TEXT,        -- comma-separated Spotify playlist IDs
                added_at        TEXT,        -- when Spotify says the user saved it
                last_seen_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("CREATE INDEX idx_spotify_tracks_artist ON spotify_tracks(artist)")
        cursor.execute("CREATE INDEX idx_spotify_tracks_title  ON spotify_tracks(title)")
        print("  + table: spotify_tracks")
        changes += 1
    else:
        print("  ✓ table: spotify_tracks")

    if not column_exists(cursor, "wishlist", "spotify_id"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN spotify_id TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_spotify_id ON wishlist(spotify_id)")
        print("  + wishlist.spotify_id")
        changes += 1
    else:
        print("  ✓ wishlist.spotify_id")

    if not column_exists(cursor, "tracks", "spotify_id"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN spotify_id TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_spotify_id ON tracks(spotify_id)")
        print("  + tracks.spotify_id")
        changes += 1
    else:
        print("  ✓ tracks.spotify_id")

    # ------------------------------------------------------------------
    # v22 — DSP availability check.
    #   dsp_check_state:
    #     'untested'        → never checked (default)
    #     'on_spotify'      → confirmed found via /search (spotify_id populated)
    #     'not_on_spotify'  → searched and got 0 results
    #     'error'           → API call failed; retry later
    #     'skipped'         → no artist/title to search with — don't pressure
    #   dsp_checked_at: ISO timestamp of the last successful check.
    # tracks.spotify_id (v21) holds the matched ID when on_spotify.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "tracks", "dsp_check_state"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN dsp_check_state TEXT NOT NULL DEFAULT 'untested'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_dsp_state ON tracks(dsp_check_state)")
        print("  + tracks.dsp_check_state")
        changes += 1
    else:
        print("  ✓ tracks.dsp_check_state")
    if not column_exists(cursor, "tracks", "dsp_checked_at"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN dsp_checked_at TEXT")
        print("  + tracks.dsp_checked_at")
        changes += 1
    else:
        print("  ✓ tracks.dsp_checked_at")

    # ------------------------------------------------------------------
    # v23 — wishlist: 'bought' → 'supported' (pro-artist framing) +
    #        fulfilled_track_id link so a track imported after a wish
    #        carries the back-reference. fulfilled_at = when it landed.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "wishlist", "fulfilled_track_id"):
        cursor.execute(
            "ALTER TABLE wishlist ADD COLUMN fulfilled_track_id INTEGER REFERENCES tracks(id) ON DELETE SET NULL"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_fulfilled ON wishlist(fulfilled_track_id)")
        print("  + wishlist.fulfilled_track_id")
        changes += 1
    else:
        print("  ✓ wishlist.fulfilled_track_id")
    if not column_exists(cursor, "wishlist", "fulfilled_at"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN fulfilled_at TEXT")
        print("  + wishlist.fulfilled_at")
        changes += 1
    else:
        print("  ✓ wishlist.fulfilled_at")
    # Rename status. Idempotent.
    cursor.execute("UPDATE wishlist SET status='supported' WHERE status='bought'")
    n_renamed = cursor.rowcount
    if n_renamed:
        print(f"  + renamed {n_renamed} wishlist 'bought' rows → 'supported'")
        changes += 1

    # (v24 — content_hash work was reverted at user's request. The
    #  columns may exist on older DBs but no code reads or writes them.)

    # ------------------------------------------------------------------
    # v25 — purge the old fractional bass/mid/treble representation.
    # Replaced by the v19 6-band perceptual fingerprint. No code reads
    # or writes the old columns anymore; this clears the data so it
    # can't leak back into any view. The columns themselves stay (SQLite
    # DROP COLUMN is messy) but they're permanently NULL going forward.
    # ------------------------------------------------------------------
    if column_exists(cursor, "files", "bass_energy"):
        cursor.execute(
            "UPDATE files SET bass_energy = NULL, mid_energy = NULL, treble_energy = NULL "
            "WHERE bass_energy IS NOT NULL OR mid_energy IS NOT NULL OR treble_energy IS NOT NULL"
        )
        n_purged = cursor.rowcount
        if n_purged:
            print(f"  + purged legacy bass/mid/treble values from {n_purged} files")
            changes += 1

    # ------------------------------------------------------------------
    # v26 — ISRC storage + DSP-check relabel.
    #   tracks.isrc            → embedded ISRC (backend only, never shown).
    #                            Exact recording id; used for exact DSP /
    #                            label / artwork lookups (Deezer, MusicBrainz).
    #   tracks.isrc_checked_at → when we last probed the file for an ISRC
    #                            (NULL = never probed; lets the backfill skip
    #                            files it has already read).
    # The DSP check no longer uses Spotify (rate-limited) — it now hits
    # Deezer + iTunes, so the state values are renamed to be DSP-neutral:
    #   on_spotify     → on_dsp
    #   not_on_spotify → not_on_dsp
    # ------------------------------------------------------------------
    if not column_exists(cursor, "tracks", "isrc"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN isrc TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc)")
        print("  + tracks.isrc")
        changes += 1
    else:
        print("  ✓ tracks.isrc")
    if not column_exists(cursor, "tracks", "isrc_checked_at"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN isrc_checked_at TEXT")
        print("  + tracks.isrc_checked_at")
        changes += 1
    else:
        print("  ✓ tracks.isrc_checked_at")
    # Relabel the DSP-check states. Idempotent.
    cursor.execute("UPDATE tracks SET dsp_check_state='on_dsp'  WHERE dsp_check_state='on_spotify'")
    n_on = cursor.rowcount
    cursor.execute("UPDATE tracks SET dsp_check_state='not_on_dsp' WHERE dsp_check_state='not_on_spotify'")
    n_off = cursor.rowcount
    if n_on or n_off:
        print(f"  + relabelled DSP states ({n_on} → on_dsp, {n_off} → not_on_dsp)")
        changes += 1

    # ------------------------------------------------------------------
    # v27 — multi-ISRC support. A recording can have more than one ISRC
    # (re-releases, different masters, territory variants) — same idea as
    # a track having multiple files. track_isrcs holds them all; the
    # convenience column tracks.isrc stays as the "primary" for fast
    # single-value reads and existing code paths.
    #   source: 'embedded' (from the file tag) | 'deezer' (discovered
    #           during the DSP check) | 'manual' | …
    # ------------------------------------------------------------------
    if not table_exists(cursor, "track_isrcs"):
        cursor.execute("""
            CREATE TABLE track_isrcs (
                id         INTEGER PRIMARY KEY,
                track_id   INTEGER NOT NULL,
                isrc       TEXT NOT NULL,
                source     TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(track_id, isrc)
            )
        """)
        cursor.execute("CREATE INDEX idx_track_isrcs_track ON track_isrcs(track_id)")
        cursor.execute("CREATE INDEX idx_track_isrcs_isrc  ON track_isrcs(isrc)")
        print("  + table: track_isrcs")
        changes += 1
    else:
        print("  ✓ table: track_isrcs")
    # Seed the table from the existing primary ISRCs so it's consistent
    # from day one. Idempotent (UNIQUE + OR IGNORE).
    cursor.execute("""
        INSERT OR IGNORE INTO track_isrcs (track_id, isrc, source)
        SELECT id, isrc, 'embedded' FROM tracks
        WHERE isrc IS NOT NULL AND TRIM(isrc) != ''
    """)
    n_seed = cursor.rowcount
    if n_seed:
        print(f"  + seeded {n_seed} ISRC(s) into track_isrcs")
        changes += 1

    # ------------------------------------------------------------------
    # v28 — Explore feed (living magazine rack). Stores fetched RSS/Atom
    # items from the user's sources so Explore opens to fresh content
    # instead of a list of links. sources.feed_url is the discovered (or
    # user-set) feed; feed_checked_at is the last fetch attempt.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "sources", "feed_url"):
        cursor.execute("ALTER TABLE sources ADD COLUMN feed_url TEXT")
        print("  + sources.feed_url")
        changes += 1
    else:
        print("  ✓ sources.feed_url")
    if not column_exists(cursor, "sources", "feed_checked_at"):
        cursor.execute("ALTER TABLE sources ADD COLUMN feed_checked_at TEXT")
        print("  + sources.feed_checked_at")
        changes += 1
    else:
        print("  ✓ sources.feed_checked_at")
    if not table_exists(cursor, "feed_items"):
        cursor.execute("""
            CREATE TABLE feed_items (
                id           INTEGER PRIMARY KEY,
                source_id    INTEGER NOT NULL,
                guid         TEXT NOT NULL,
                title        TEXT,
                url          TEXT,
                summary      TEXT,
                image_url    TEXT,
                published_at TEXT,
                fetched_at   TEXT DEFAULT (datetime('now')),
                is_hidden    INTEGER NOT NULL DEFAULT 0,
                UNIQUE(source_id, guid)
            )
        """)
        cursor.execute("CREATE INDEX idx_feed_items_published ON feed_items(published_at)")
        cursor.execute("CREATE INDEX idx_feed_items_source ON feed_items(source_id)")
        print("  + table: feed_items")
        changes += 1
    else:
        print("  ✓ table: feed_items")

    # ------------------------------------------------------------------
    # v29 — one-time DSP re-check reset. v26 renamed the old Spotify-based
    # 'not_on_spotify' results to 'not_on_dsp', but "not on Spotify" is NOT
    # "not on any DSP" (Spotify ≠ Deezer/Apple, and the old dev-mode check
    # missed plenty). That produced false "only here" labels. Reset every
    # 'not_on_dsp' back to 'untested' so the new Deezer+iTunes+ISRC check
    # re-evaluates them. Guarded by a flag so it runs exactly once and
    # never wipes legitimate new results on later launches.
    # ------------------------------------------------------------------
    cursor.execute("SELECT 1 FROM settings WHERE key='dsp_recheck_v29_done'")
    if not cursor.fetchone():
        cursor.execute(
            "UPDATE tracks SET dsp_check_state='untested', dsp_checked_at=NULL "
            "WHERE dsp_check_state='not_on_dsp'"
        )
        n_reset = cursor.rowcount
        cursor.execute("INSERT INTO settings (key, value) VALUES ('dsp_recheck_v29_done', '1')")
        print(f"  + reset {n_reset} stale 'only here' tracks to untested for a clean re-check")
        changes += 1

    # ------------------------------------------------------------------
    # v30 — Explore curation ("your own algorithm"). Interests are
    # user-defined channels (keywords + a weight); feed items are scored
    # against them so Explore can rank "For you" while reserving a slice
    # for serendipity (anti-bubble). sources.topics tags a whole source so
    # its items inherit a signal even when a single headline doesn't.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "sources", "topics"):
        cursor.execute("ALTER TABLE sources ADD COLUMN topics TEXT")
        print("  + sources.topics")
        changes += 1
    else:
        print("  ✓ sources.topics")

    if not table_exists(cursor, "interests"):
        cursor.execute("""
            CREATE TABLE interests (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                keywords    TEXT,
                weight      INTEGER NOT NULL DEFAULT 3,
                is_active   INTEGER NOT NULL DEFAULT 1,
                is_wildcard INTEGER NOT NULL DEFAULT 0,
                sort_order  INTEGER NOT NULL DEFAULT 0
            )
        """)
        seeds = [
            ("Electronic",             "electronic, techno, house, electro, IDM, electronica, breakbeat, ambient", 5),
            ("Underground electronic", "underground, dub techno, raw techno, electro, bass music, club, white label, dubplate", 5),
            ("Experimental",           "experimental, avant-garde, avant garde, noise, sound art, musique concrète, drone, abstract", 5),
            ("Deep listening & sound", "deep listening, field recording, sound design, acousmatic, spatial audio, sonic, listening", 4),
            ("Audio documentaries",    "documentary, audio doc, radio doc, archive, oral history, soundscape", 4),
            ("Trad Irish music",       "irish trad, traditional irish, sean-nós, sean nos, uilleann, bodhrán, bodhran, fiddle, tin whistle", 4),
            ("Irish music scene",      "irish, ireland, dublin, cork, belfast, galway", 4),
            ("Music industry",         "music industry, record label, royalties, streaming, distribution, copyright, music business", 3),
            ("Music technology",       "synth, synthesizer, modular, eurorack, drum machine, hardware, gear, plugin", 4),
            ("Music-making tech",      "ableton, max msp, production, sampling, daw, sound design, music making, studio", 4),
            ("Radio shows & mixes",    "radio, mix, dj mix, residency, broadcast, NTS, boiler room, podcast", 4),
            ("Emerging genres",        "emerging, microgenre, new genre, hyperpop, scene report, subgenre", 3),
            ("Underground & DIY",      "underground, DIY, independent, small label, self-released, cassette, tape label", 4),
        ]
        for i, (name, kw, wt) in enumerate(seeds):
            cursor.execute(
                "INSERT INTO interests (name, keywords, weight, sort_order) VALUES (?, ?, ?, ?)",
                (name, kw, wt, i)
            )
        print(f"  + table: interests (seeded {len(seeds)})")
        changes += 1
    else:
        print("  ✓ table: interests")

    # Tag sources with topics — only fills blanks so it never clobbers edits.
    SOURCE_TOPICS = {
        "Resident Advisor":     "electronic, underground, radio, industry, club, techno",
        "NTS Radio":            "radio, electronic, experimental, eclectic, mix",
        "The Wire":             "experimental, avant-garde, jazz, sound art, underground",
        "FACT Magazine":        "electronic, experimental, industry, culture",
        "Fact Mixes":           "mix, dj mix, electronic, radio",
        "Bandcamp Daily":       "underground, electronic, experimental, emerging, diy",
        "Crack Magazine":       "electronic, underground, culture, club",
        "Mixmag":               "electronic, club, industry, dance",
        "Boiler Room":          "electronic, club, underground, mix",
        "Dublin Digital Radio": "radio, irish, electronic, experimental",
        "Rinse FM":             "radio, electronic, club, bass",
        "Worldwide FM":         "radio, electronic, global, mix",
        "All Hands Records":    "label, electronic, underground",
    }
    for nm, tp in SOURCE_TOPICS.items():
        cursor.execute(
            "UPDATE sources SET topics=? WHERE name=? AND (topics IS NULL OR TRIM(topics)='')",
            (tp, nm)
        )

    # RA's news/features RSS was retired; the RA Podcast feed is the
    # reliable RA source. Set it only if no feed is configured.
    cursor.execute(
        "UPDATE sources SET feed_url=? WHERE name='Resident Advisor' "
        "AND (feed_url IS NULL OR TRIM(feed_url)='')",
        ("https://ra.co/xml/podcast.xml",)
    )

    # Serendipity quota (% of the For-you feed reserved for outside-the-bubble).
    cursor.execute("SELECT 1 FROM settings WHERE key='feed_serendipity_pct'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO settings (key, value) VALUES ('feed_serendipity_pct', '12')")
        print("  + setting: feed_serendipity_pct = 12")
        changes += 1

    # ------------------------------------------------------------------
    # v31 — cultural enrichment (no AI, free sources). Extends the existing
    # artist_profiles with the entity ids + provenance, and adds a parallel
    # label_profiles table. Populated by culture.py from MusicBrainz +
    # Wikidata + Wikipedia (+ optional Discogs). Feeds the world map and
    # future cultural-mapping views (origin / gender / label geography).
    # ------------------------------------------------------------------
    for col, typ in [("mbid", "TEXT"), ("wikidata_qid", "TEXT"),
                     ("artist_type", "TEXT"), ("data_source", "TEXT")]:
        if not column_exists(cursor, "artist_profiles", col):
            cursor.execute(f"ALTER TABLE artist_profiles ADD COLUMN {col} {typ}")
            print(f"  + artist_profiles.{col}")
            changes += 1
    if not table_exists(cursor, "label_profiles"):
        cursor.execute("""
            CREATE TABLE label_profiles (
                id            INTEGER PRIMARY KEY,
                label_name    TEXT NOT NULL UNIQUE,
                country       TEXT,
                city          TEXT,
                latitude      REAL,
                longitude     REAL,
                founded_year  INTEGER,
                founder       TEXT,
                parent_label  TEXT,
                mbid          TEXT,
                wikidata_qid  TEXT,
                bio_summary   TEXT,
                wikipedia_url TEXT,
                data_source   TEXT,
                enriched_at   TEXT,
                fetch_error   TEXT,
                created_at    TEXT DEFAULT (datetime('now')),
                updated_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("CREATE INDEX idx_label_profiles_country ON label_profiles(country)")
        print("  + table: label_profiles")
        changes += 1
    else:
        print("  ✓ table: label_profiles")

    # ------------------------------------------------------------------
    # v32 — place customization: ambient sound volume. The path columns
    # (ambient_audio_path, image_path, video_path, moodboard_notes) and
    # colour_primary/secondary + moodboard_images already exist from
    # earlier versions; this just adds a per-place ambient volume so a
    # place can carry its own atmosphere at a chosen level.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "places", "ambient_audio_volume"):
        cursor.execute("ALTER TABLE places ADD COLUMN ambient_audio_volume REAL DEFAULT 0.35")
        print("  + places.ambient_audio_volume")
        changes += 1
    else:
        print("  ✓ places.ambient_audio_volume")

    # ------------------------------------------------------------------
    # v33 — per-place themes. Daithí wants each place to feel like its own
    # room: pick a mood + colours + fonts and have it actually re-skin the
    # place page. theme_bg drives the ground colour (tints the forest
    # texture); theme_text overrides ink (auto-derived from bg luminance
    # when null); theme_font_title/body pick fonts from a curated set; and
    # theme_mood stores the preset key for the "named look" entry point.
    # The existing colour_primary stays in charge of the accent.
    # ------------------------------------------------------------------
    for col, typ in [
        ("theme_bg",         "TEXT"),
        ("theme_text",       "TEXT"),
        ("theme_font_title", "TEXT"),
        ("theme_font_body",  "TEXT"),
        ("theme_mood",       "TEXT"),
    ]:
        if not column_exists(cursor, "places", col):
            cursor.execute(f"ALTER TABLE places ADD COLUMN {col} {typ}")
            print(f"  + places.{col}")
            changes += 1
        else:
            print(f"  ✓ places.{col}")

    # ------------------------------------------------------------------
    # v34 — illustration colours. Every place's icon takes four colour
    # roles: warm light (windows/fire/lamps — falls back to colour_primary),
    # structure (main building/object mass), outline (strokes + roof
    # edges), and detail (secondary accent: chimneys, signs, glowing
    # strips). All optional — when null, the renderer derives sensible
    # defaults from the place's theme_bg + colour_primary so the
    # illustration always sits in the place's mood.
    # ------------------------------------------------------------------
    for col, typ in [
        ("illustration_light",     "TEXT"),
        ("illustration_structure", "TEXT"),
        ("illustration_outline",   "TEXT"),
        ("illustration_detail",    "TEXT"),
    ]:
        if not column_exists(cursor, "places", col):
            cursor.execute(f"ALTER TABLE places ADD COLUMN {col} {typ}")
            print(f"  + places.{col}")
            changes += 1
        else:
            print(f"  ✓ places.{col}")

    # ------------------------------------------------------------------
    # v35 — files.brightness_score. The Sound-card slider used to read
    # spectral_centroid (raw FFT, no A-weighting) which disagreed with
    # the Brilliance bar. Switched to band_brilliance, then Daithí
    # pointed out brightness perceptually is the CUMULATIVE energy in
    # the upper bands, not one band alone. Store a single weighted
    # combination of Presence (2-5 kHz) + Brilliance (5-11 kHz) so the
    # slider matches that intuition. Backfill from existing band data.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "files", "brightness_score"):
        cursor.execute("ALTER TABLE files ADD COLUMN brightness_score REAL")
        print("  + files.brightness_score")
        changes += 1
    else:
        print("  ✓ files.brightness_score")
    # Idempotent backfill — recompute every time so re-weighting is one
    # script run away. Cheap; only touches rows with both bands present.
    cursor.execute("""
        UPDATE files
           SET brightness_score = 0.40 * band_presence + 0.60 * band_brilliance
         WHERE band_presence IS NOT NULL AND band_brilliance IS NOT NULL
    """)
    print(f"  ✓ brightness_score backfilled for {cursor.rowcount} files")

    # ------------------------------------------------------------------
    # v36 — content hashing for byte-identical duplicate detection on
    # import. The columns existed on some older DBs (the reverted v24) but
    # not on fresh schema.py databases, so ensure they're present, then
    # index for fast lookups. The importer fills them lazily (only hashes
    # files that are size/duration/format candidates).
    # ------------------------------------------------------------------
    for col, typ in [("content_hash", "TEXT"), ("hashed_at", "TEXT")]:
        if not column_exists(cursor, "files", col):
            cursor.execute(f"ALTER TABLE files ADD COLUMN {col} {typ}")
            print(f"  + files.{col}")
            changes += 1
        else:
            print(f"  ✓ files.{col}")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files(content_hash)")
    print("  ✓ index: idx_files_content_hash")

    # ------------------------------------------------------------------
    # v37 — per-file audio INTEGRITY, for the live audio-health readout.
    # `integrity`: 'ok' / 'corrupt' / 'zero' / NULL (unchecked). Set by the
    # decode-integrity scan (flac -t / ffmpeg). The live present/missing
    # status is computed fresh on demand (it changes when a drive is
    # plugged/unplugged); only the expensive decode result is persisted.
    # ------------------------------------------------------------------
    for col, typ in [("integrity", "TEXT"), ("integrity_checked_at", "TEXT")]:
        if not column_exists(cursor, "files", col):
            cursor.execute(f"ALTER TABLE files ADD COLUMN {col} {typ}")
            print(f"  + files.{col}")
            changes += 1
        else:
            print(f"  ✓ files.{col}")

    # ------------------------------------------------------------------
    # v38 — deep-listening RESEARCH substrate. Captured moments
    # (listening_notes) are the atoms; on top of them:
    #   threads         — a named, coloured line of enquiry ("highlife
    #                     guitar tone"). A moment can be in many.
    #   thread_moments  — ordered membership (position) → the Thread lens
    #                     (trace it through history, sequence it for a show).
    #   note_links      — a free connection between two moments (+ optional
    #                     label) → powers the non-linear Mind-map lens later.
    # All views (feed / thread / timeline / map / mind-map) read these.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            colour      TEXT,
            description TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thread_moments (
            thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            note_id   INTEGER NOT NULL REFERENCES listening_notes(id) ON DELETE CASCADE,
            position  REAL DEFAULT 0,
            added_at  TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (thread_id, note_id)
        )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_moments_note ON thread_moments(note_id)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS note_links (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            from_note_id INTEGER NOT NULL REFERENCES listening_notes(id) ON DELETE CASCADE,
            to_note_id   INTEGER NOT NULL REFERENCES listening_notes(id) ON DELETE CASCADE,
            label        TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            UNIQUE (from_note_id, to_note_id)
        )""")
    print("  ✓ research substrate: threads / thread_moments / note_links")

    # ------------------------------------------------------------------
    # v39 — CUSTOM FIELDS on a moment. The "model anything" lever: a moment
    # can carry any user-invented key:value pairs (instrument: guitar,
    # decade: 70s, mood: melancholy …). No fixed schema — the user defines
    # their own columns and can filter/group by them. Multiple values per
    # field are allowed (instrument: guitar AND instrument: bass).
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS note_properties (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id    INTEGER NOT NULL REFERENCES listening_notes(id) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            value      TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_note_properties_note ON note_properties(note_id)")
    print("  ✓ custom fields: note_properties")

    # ------------------------------------------------------------------
    # v40 — SAMPLE lineage, user-curated (seeded by MusicBrainz suggestions).
    # A directional row: track_id SAMPLES the source. The user confirms a MB
    # suggestion (status='confirmed') at a marked timestamp, dismisses it
    # (status='dismissed', so it stops being suggested), or adds their own.
    # The reverse ("sampled in") derives for free: rows where source_track_id=X.
    # MusicBrainz has no timestamps — this is where they live.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS track_samples (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id             INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            source_track_id      INTEGER REFERENCES tracks(id) ON DELETE SET NULL,
            source_title         TEXT,
            source_artist        TEXT,
            source_mbid          TEXT,
            timestamp_sec        REAL,   -- where in track_id the sample appears
            source_timestamp_sec REAL,   -- where in the original it came from
            note                 TEXT,
            status               TEXT DEFAULT 'confirmed',   -- 'confirmed' | 'dismissed'
            source               TEXT DEFAULT 'user',        -- 'user' | 'musicbrainz'
            created_at           TEXT DEFAULT (datetime('now'))
        )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_samples_track ON track_samples(track_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_samples_source ON track_samples(source_track_id)")
    print("  ✓ sample lineage: track_samples")

    # v41 — LONG-FORM detail on a moment / thread. The brief note (note_text)
    # is the quick capture made while listening; detail_text is the "page
    # beneath" for longer thoughts. Threads carry one too (a write-up of the
    # line of enquiry).
    if table_exists(cursor, "listening_notes") and not column_exists(cursor, "listening_notes", "detail_text"):
        cursor.execute("ALTER TABLE listening_notes ADD COLUMN detail_text TEXT")
        print("  ✓ detailed notes: listening_notes.detail_text")
    if table_exists(cursor, "threads") and not column_exists(cursor, "threads", "detail_text"):
        cursor.execute("ALTER TABLE threads ADD COLUMN detail_text TEXT")
        print("  ✓ detailed notes: threads.detail_text")

    # v42 — OWN PRODUCTIONS: a track can be the user's own work, linked to its
    # DAW project; each version (file) remembers the session it was bounced from.
    # The Music Room only ever *links* — it never moves or parses project files.
    for col, typ in (("is_own_work", "INTEGER DEFAULT 0"),
                     ("daw_project_path", "TEXT"),
                     ("daw_type", "TEXT")):
        if table_exists(cursor, "tracks") and not column_exists(cursor, "tracks", col):
            cursor.execute(f"ALTER TABLE tracks ADD COLUMN {col} {typ}")
            print(f"  ✓ own productions: tracks.{col}")
    if table_exists(cursor, "files") and not column_exists(cursor, "files", "session_path"):
        cursor.execute("ALTER TABLE files ADD COLUMN session_path TEXT")
        print("  ✓ own productions: files.session_path")

    # v43 — STUDIO: an album is a place (your own productions). Marks the
    # album-places so the Studio screen can list them; they otherwise behave
    # exactly like any other place.
    if table_exists(cursor, "places") and not column_exists(cursor, "places", "is_studio_project"):
        cursor.execute("ALTER TABLE places ADD COLUMN is_studio_project INTEGER DEFAULT 0")
        print("  ✓ studio: places.is_studio_project")

    # v44 — KEY: per-file confidence (0–1) from the Krumhansl–Schmuckler
    # detector (key_detect.py). Lets the track panel flag low-confidence keys
    # — mostly relative-major/minor ambiguities — for human review/relabel.
    if table_exists(cursor, "files") and not column_exists(cursor, "files", "key_confidence"):
        cursor.execute("ALTER TABLE files ADD COLUMN key_confidence REAL")
        print("  ✓ key: files.key_confidence")

    # v45 — MIND-MAP CANVAS: a moment's user-placed position on the idea canvas
    # (/listen/canvas). NULL = never placed (the canvas spawns it deterministically
    # until the user drags it somewhere — only the USER's placement is saved).
    if table_exists(cursor, "listening_notes") and not column_exists(cursor, "listening_notes", "canvas_x"):
        cursor.execute("ALTER TABLE listening_notes ADD COLUMN canvas_x REAL")
        cursor.execute("ALTER TABLE listening_notes ADD COLUMN canvas_y REAL")
        print("  ✓ canvas: listening_notes.canvas_x / canvas_y")

    # v46 — PILES: the user's loose piles & clusters in a 3D room. A pile has a
    # user-given name + position; it may be TIED to a real place/set/bosca
    # (membership then lives in that thing) or stand alone ('loose', membership
    # in room_pile_tracks). The USER makes and places every pile — never auto.
    if not table_exists(cursor, "room_piles"):
        cursor.execute("""
            CREATE TABLE room_piles (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                room_place_id INTEGER NOT NULL REFERENCES places(id),
                name          TEXT NOT NULL,
                kind          TEXT DEFAULT 'loose',
                ref_id        INTEGER,
                x REAL DEFAULT 0, y REAL DEFAULT 0, z REAL DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE room_pile_tracks (
                pile_id  INTEGER NOT NULL REFERENCES room_piles(id) ON DELETE CASCADE,
                track_id INTEGER NOT NULL REFERENCES tracks(id),
                added_at TEXT DEFAULT (datetime('now')),
                UNIQUE (pile_id, track_id)
            )
        """)
        cursor.execute("CREATE INDEX idx_room_piles_room ON room_piles(room_place_id)")
        print("  ✓ piles: room_piles + room_pile_tracks")

    # v47 — LISTENING PROJECTS: containers for moments (behave like places —
    # a full list of listening notes, and each note can live in many projects).
    # The curator works inside a project exactly like in all-notes, scoped.
    if not table_exists(cursor, "listening_projects"):
        cursor.execute("""
            CREATE TABLE listening_projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE project_notes (
                project_id INTEGER NOT NULL REFERENCES listening_projects(id) ON DELETE CASCADE,
                note_id    INTEGER NOT NULL REFERENCES listening_notes(id) ON DELETE CASCADE,
                added_at   TEXT DEFAULT (datetime('now')),
                UNIQUE (project_id, note_id)
            )
        """)
        cursor.execute("CREATE INDEX idx_project_notes_note ON project_notes(note_id)")
        print("  ✓ projects: listening_projects + project_notes")

    # v48 — SET RECORDINGS: recorded/uploaded takes of a set (many versions per
    # set), linkable to a DAW project, optionally added to the Music Room as a
    # clearly-marked record (tracks.is_set_recording, filtered out by default).
    if not table_exists(cursor, "set_recordings"):
        cursor.execute("""
            CREATE TABLE set_recordings (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                set_id           INTEGER NOT NULL REFERENCES sets(id),
                name             TEXT,
                file_path        TEXT NOT NULL,
                daw_project_path TEXT,
                room_track_id    INTEGER REFERENCES tracks(id),
                recorded_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  ✓ set recordings: set_recordings")
    if table_exists(cursor, "tracks") and not column_exists(cursor, "tracks", "is_set_recording"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN is_set_recording INTEGER DEFAULT 0")
        print("  ✓ set recordings: tracks.is_set_recording")

    # v49 — SET INTERLUDES: short audio between a set's tracks (the radio DJ
    # talking between records) — recorded in the app or dropped in as a file.
    # after_position 0 = before the first track; N = after track at position N.
    if not table_exists(cursor, "set_interludes"):
        cursor.execute("""
            CREATE TABLE set_interludes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                set_id         INTEGER NOT NULL REFERENCES sets(id),
                after_position INTEGER NOT NULL DEFAULT 0,
                name           TEXT,
                file_path      TEXT NOT NULL,
                created_at     TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  ✓ set interludes: set_interludes")

    # v50 — BPM REFINEMENT: librosa's beat_track snapped every tempo onto a
    # ~47-value lattice (117.45/123.05/129.2…), so real 120/128 BPM tracks
    # read as neighbours of themselves. estimate_bpm() (tempogram + parabolic
    # lag interpolation) fixes the analyser; this marker makes the library-
    # wide re-estimate batch resumable.
    if table_exists(cursor, "files") and not column_exists(cursor, "files", "bpm_refined_at"):
        cursor.execute("ALTER TABLE files ADD COLUMN bpm_refined_at TEXT")
        print("  ✓ bpm refinement marker: files.bpm_refined_at")

    # v51 — DSP PROBABLE MATCHES: when the exact matcher misses but a close
    # candidate exists (inexact user metadata), the candidate is held here as
    # JSON {artist, title, source, score} with dsp_check_state='probable'
    # until the user confirms or rejects it on the track panel.
    if not column_exists(cursor, "tracks", "dsp_probable"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN dsp_probable TEXT")
        print("  ✓ dsp probable-match holding column: tracks.dsp_probable")

    # v52 — PLAY TRACKING: raw play EVENTS (the analytics-grade approach —
    # every start is logged with its source/context/duration, so any future
    # metric stays computable: recency/frequency, completion rate, plays by
    # hour, place affinity…) + fast denormalised counters on tracks.
    if not table_exists(cursor, "play_events"):
        cursor.execute("""
            CREATE TABLE play_events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id          INTEGER NOT NULL REFERENCES tracks(id),
                file_id           INTEGER,
                source            TEXT NOT NULL DEFAULT 'unknown',  -- seinnteoir|panel|set|canvas
                place_id          INTEGER,
                started_at        TEXT DEFAULT (datetime('now')),
                duration_listened REAL,           -- seconds actually heard (when known)
                completed         INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX idx_play_events_track ON play_events(track_id)")
        cursor.execute("CREATE INDEX idx_play_events_started ON play_events(started_at)")
        print("  ✓ play tracking: play_events")
    if not column_exists(cursor, "tracks", "play_count"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN play_count INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE tracks ADD COLUMN last_played_at TEXT")
        print("  ✓ play tracking: tracks.play_count + last_played_at")

    # Re-backfill is_oneshot with the correct threshold (< 5 s).
    # Safe to run repeatedly — resets all then reapplies.
    cursor.execute("UPDATE tracks SET is_oneshot = 0")
    cursor.execute("""
        UPDATE tracks SET is_oneshot = 1
        WHERE id IN (
            SELECT track_id FROM files
            WHERE is_primary = 1 AND duration_sec > 0 AND duration_sec < 5
        )
    """)
    n5 = cursor.rowcount
    print(f"  ✓ is_oneshot recomputed at < 5 s threshold ({n5} tracks)")

    # ------------------------------------------------------------------
    # v53 — SAVED ARTICLES AS REFERENCE NOTES. A saved Explore article /
    # video becomes a listening_notes row with kind='reference' and NO
    # track/session — so threads, projects, note_links, properties and
    # the canvas all work on it with zero extra plumbing (one substrate,
    # many lenses). That needs session_id/track_id NULLABLE → SQLite
    # table rebuild, in the ORDER the SQLite docs prescribe: create the
    # new table under a temp name, copy, DROP the old, then rename the
    # new into place. The final RENAME is what rewrites child REFERENCES
    # clauses — done this way they end up pointing at "listening_notes".
    # (Renaming the OLD table away first rewrites children to the temp
    # name and strands them — learned the hard way on 2026-06-12.)
    # ------------------------------------------------------------------
    if not column_exists(cursor, "listening_notes", "kind"):
        old_cols = [r[1] for r in cursor.execute("PRAGMA table_info(listening_notes)").fetchall()]
        cursor.execute("""
            CREATE TABLE listening_notes_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    INTEGER REFERENCES listening_sessions(id),
                track_id      INTEGER REFERENCES tracks(id),
                timestamp_sec REAL DEFAULT 0,
                note_text     TEXT NOT NULL,
                note_category TEXT DEFAULT '',
                is_voice      INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now')),
                detail_text   TEXT,
                canvas_x      REAL,
                canvas_y      REAL,
                kind          TEXT NOT NULL DEFAULT 'moment',   -- moment | reference
                ref_url       TEXT,
                ref_title     TEXT,
                ref_source    TEXT,
                ref_image_url TEXT
            )
        """)
        cols = ", ".join(old_cols)
        cursor.execute(f"INSERT INTO listening_notes_new ({cols}) SELECT {cols} FROM listening_notes")
        cursor.execute("DROP TABLE listening_notes")
        cursor.execute("ALTER TABLE listening_notes_new RENAME TO listening_notes")
        print("  ✓ reference notes: listening_notes rebuilt (nullable session/track + kind/ref_*)")
        changes += 1

    # ------------------------------------------------------------------
    # v54 — STRUCTURES: the user's own spatial arrangement of tags/genres.
    # A structure is a saved mind-map of tag/genre NODES (each positioned,
    # coloured, connectable); applying one in the 3D room arranges the
    # records into that shape (centroid of a record's matching nodes), and
    # exporting one turns each node into a playlist on the stick. The user
    # places every node — nothing is ever auto-arranged.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "structures"):
        cursor.execute("""
            CREATE TABLE structures (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE structure_nodes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                structure_id INTEGER NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
                kind         TEXT NOT NULL DEFAULT 'tag',     -- tag | genre
                ref_id       INTEGER NOT NULL,                -- tags.id | genres.id
                x            REAL DEFAULT 0,
                y            REAL DEFAULT 0,
                colour       TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                UNIQUE (structure_id, kind, ref_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE structure_links (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                structure_id INTEGER NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
                from_node_id INTEGER NOT NULL REFERENCES structure_nodes(id) ON DELETE CASCADE,
                to_node_id   INTEGER NOT NULL REFERENCES structure_nodes(id) ON DELETE CASCADE,
                label        TEXT
            )
        """)
        print("  ✓ structures: structures + structure_nodes + structure_links")
        changes += 1

    # ------------------------------------------------------------------
    # v55 — STRUCTURE GROUPS (axes): the user names which pills belong
    # together ("energy" 1–5, "mood" black/grey/white). Exports then cross
    # the groups: standing at energy 4 on the player, the three moods sit
    # beside each other as "4 · black / 4 · grey / 4 · white".
    # ------------------------------------------------------------------
    if table_exists(cursor, "structure_nodes") and not column_exists(cursor, "structure_nodes", "group_name"):
        cursor.execute("ALTER TABLE structure_nodes ADD COLUMN group_name TEXT")
        print("  ✓ structure groups: structure_nodes.group_name")
        changes += 1

    # ------------------------------------------------------------------
    # v56 — STRUCTURES REMEMBER THEIR FILTERS: a structure created while
    # the room is filtered (tags/genres/BPM/year/key/format) keeps that
    # filter set as its working base — applying the structure re-applies
    # the filters. Saved views = filters + layout, in one gesture.
    # ------------------------------------------------------------------
    if table_exists(cursor, "structures") and not column_exists(cursor, "structures", "filters"):
        cursor.execute("ALTER TABLE structures ADD COLUMN filters TEXT")
        print("  ✓ structure filters: structures.filters (JSON)")
        changes += 1

    # ------------------------------------------------------------------
    # v57 — COMPOSE: the research OUTPUT (VISION §4.4, research/04). A
    # composition is a structured document of ordered BLOCKS — prose/headings
    # the user writes, plus embedded listening MOMENTS (track + timestamp +
    # note) and saved REFERENCES (articles/videos) pulled from the existing
    # listening substrate. Blocks live as a JSON array; moment/reference blocks
    # store only the note_id and are resolved live on read, so a composition
    # always reflects the current substrate and tolerates a deleted moment.
    # capture→organise→PRODUCE: a notebook/thread becomes a radio script, an
    # essay, a track-by-track review or liner notes — exportable, with an
    # auto-built Sources list. The user composes; nothing is auto-written (§3.7).
    # ------------------------------------------------------------------
    if not table_exists(cursor, "compositions"):
        cursor.execute("""
            CREATE TABLE compositions (
                id          INTEGER PRIMARY KEY,
                title       TEXT NOT NULL,
                kind        TEXT NOT NULL DEFAULT 'piece',
                subtitle    TEXT,
                blocks      TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        print("  ✓ compose: compositions (research output — VISION §4.4)")
        changes += 1

    # ------------------------------------------------------------------
    # v58 — REFERENCE FILES: research materials aren't only web URLs. A
    # reference note can now also point at an UPLOADED file (a PDF paper, a
    # scan of liner notes, a photo of a sleeve/venue) saved under the data
    # dir's static root and served at /static/research/<name>. ref_file_path
    # holds that served path; the media kind (image / pdf / video / page) is
    # inferred from the path or ref_url at render time. So a curator can link
    # videos, articles, PDFs and pictures as first-class research atoms.
    # ------------------------------------------------------------------
    if table_exists(cursor, "listening_notes") and not column_exists(cursor, "listening_notes", "ref_file_path"):
        cursor.execute("ALTER TABLE listening_notes ADD COLUMN ref_file_path TEXT")
        print("  ✓ reference files: listening_notes.ref_file_path")
        changes += 1

    # ------------------------------------------------------------------
    # v59 — CUE SEEDING GUARD: timestamped notes are seeded into rekordbox as
    # memory cues at most ONCE per track, so a re-export never clobbers cues the
    # user has snapped to the grid in rekordbox. cues_seeded_at stamps a track
    # the first time its cues are exported. EXISTING tracks are backfilled as
    # already-seeded (treated as already-in-rekordbox), so only tracks added
    # from here on bring their cues across.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "tracks", "cues_seeded_at"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN cues_seeded_at TEXT")
        cursor.execute("UPDATE tracks SET cues_seeded_at = datetime('now') WHERE cues_seeded_at IS NULL")
        print("  ✓ cue seeding guard: tracks.cues_seeded_at (existing tracks marked already-seeded)")
        changes += 1

    # ------------------------------------------------------------------
    # v60 — ANALYSIS LAYERS: BPM/key can come from more than one analyser. The
    # Music Room's own analysis stays in files.bpm/key (the "musicroom" layer);
    # this table holds EXTERNAL layers — one row per (track, source), e.g.
    # rekordbox's industry-leading detection, later Mixed In Key. The track
    # panel shows the preferred source (rekordbox when present) and flicks
    # between them; new sources slot in with no schema change.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "track_analysis"):
        cursor.execute("""
            CREATE TABLE track_analysis (
                id          INTEGER PRIMARY KEY,
                track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                source      TEXT NOT NULL,
                bpm         REAL,
                key_note    TEXT,
                key_scale   TEXT,
                analysed_at TEXT DEFAULT (datetime('now')),
                UNIQUE (track_id, source)
            )
        """)
        print("  ✓ analysis layers: track_analysis (external BPM/key sources — rekordbox, etc.)")
        changes += 1

    # ------------------------------------------------------------------
    # v61 — PLAYABLE FEED AUDIO: a podcast/mix RSS item carries a directly
    # playable audio enclosure. We now mine it so Explore can play a mix
    # through the persistent Player instead of only linking out. audio_url =
    # the enclosure; audio_duration_sec = itunes:duration when given.
    # ------------------------------------------------------------------
    if table_exists(cursor, "feed_items") and not column_exists(cursor, "feed_items", "audio_url"):
        cursor.execute("ALTER TABLE feed_items ADD COLUMN audio_url TEXT")
        cursor.execute("ALTER TABLE feed_items ADD COLUMN audio_duration_sec REAL")
        print("  ✓ playable feed audio: feed_items.audio_url / audio_duration_sec")
        changes += 1

    # ------------------------------------------------------------------
    # v62 — BANDCAMP / PURCHASE TRACKER: when you click a record's buy link
    # from inside the app we log a purchase INTENT (a click anchored to a
    # record/wishlist item). The buy happens off-site, so the intent stays
    # 'pending' until confirmed — either by you (✓ I bought it) or by the
    # Bandcamp collection sync, which matches your owned releases to intents.
    # This turns "Supported the artist" from a free toggle into something
    # anchored to a real click + (optionally) a verified collection match.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "purchase_intents"):
        cursor.execute("""
            CREATE TABLE purchase_intents (
                id          INTEGER PRIMARY KEY,
                url         TEXT NOT NULL,
                store       TEXT,                 -- 'bandcamp', 'beatport', 'discogs'…
                track_id    INTEGER REFERENCES tracks(id)   ON DELETE SET NULL,
                wishlist_id INTEGER REFERENCES wishlist(id) ON DELETE SET NULL,
                artist      TEXT,                 -- best-effort, for display + matching
                title       TEXT,
                status      TEXT NOT NULL DEFAULT 'pending',  -- pending | bought | dismissed
                created_at  TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                resolved_by TEXT                  -- 'user' | 'collection-sync'
            )
        """)
        cursor.execute("CREATE INDEX idx_purchase_intents_status ON purchase_intents(status)")
        print("  ✓ bandcamp/purchase tracker: purchase_intents")
        changes += 1

    # ------------------------------------------------------------------
    # v63 — ALBUM-ART COLOUR: the cover's representative dominant colour
    # (a "#rrggbb"), extracted from the image (art_colour.py). The library
    # stored no visual colour for covers, so the grid couldn't sort by it;
    # this column holds it. Populated by a backfill + on artwork fetch.
    # ------------------------------------------------------------------
    if not column_exists(cursor, "tracks", "art_colour"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN art_colour TEXT")
        print("  ✓ album-art colour: tracks.art_colour")
        changes += 1

    # ------------------------------------------------------------------
    # v64 — WHERE a purchase was made: when the user confirms they bought a
    # record they clicked, they can say whether it was on Bandcamp (the link
    # they followed) or elsewhere. Feeds the conversion / artist-impact view.
    # ------------------------------------------------------------------
    if table_exists(cursor, "purchase_intents") and not column_exists(cursor, "purchase_intents", "bought_via"):
        cursor.execute("ALTER TABLE purchase_intents ADD COLUMN bought_via TEXT")  # 'bandcamp' | 'other'
        print("  ✓ purchase channel: purchase_intents.bought_via")
        changes += 1

    # ------------------------------------------------------------------
    # Wishlist also carries WHERE it was supported, so "Supported · Bandcamp"
    # shows on the item itself (not just in the pending "did you buy?" prompt).
    # ------------------------------------------------------------------
    if table_exists(cursor, "wishlist") and not column_exists(cursor, "wishlist", "bought_via"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN bought_via TEXT")  # 'bandcamp' | 'other'
        print("  ✓ purchase channel: wishlist.bought_via")
        changes += 1
    # provenance — the human-readable origin of a saved track ("Axel Boman — NTS mix",
    # "Shazam · 2026-05-12", "Article: …"), so the wishlist remembers WHERE you found it.
    if table_exists(cursor, "wishlist") and not column_exists(cursor, "wishlist", "provenance"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN provenance TEXT")
        print("  ✓ wishlist.provenance")
        changes += 1

    # ------------------------------------------------------------------
    # WISHLIST BUCKETS — David's three boxes replace the single list. They sort
    # by FEELING, orthogonal to status (the buy-funnel: wishing/supported/passed):
    #   'another_listen' — "I'll have another listen" (the staple; the default)
    #   'need_now'       — "I need this now!"
    #   'have_a_think'   — "I didn't know what to make of this… let's have a think"
    # Every existing wish lands in 'another_listen'. buy_reason captures, in the
    # user's own words, WHY a track moved to need_now in the play game (optional).
    # ------------------------------------------------------------------
    if table_exists(cursor, "wishlist") and not column_exists(cursor, "wishlist", "bucket"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN bucket TEXT NOT NULL DEFAULT 'another_listen'")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_bucket ON wishlist(bucket)")
        print("  ✓ wishlist.bucket (the three boxes)")
        changes += 1
    if table_exists(cursor, "wishlist") and not column_exists(cursor, "wishlist", "buy_reason"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN buy_reason TEXT")
        print("  ✓ wishlist.buy_reason (why this one)")
        changes += 1
    # buy_reason is now a CATEGORY key (sentimental/djing/research/support/collection/other)
    # so the "why you buy" report can count clean buckets; buy_reason_note holds the
    # free-text the user types for 'other' (or any extra words they want to add).
    if table_exists(cursor, "wishlist") and not column_exists(cursor, "wishlist", "buy_reason_note"):
        cursor.execute("ALTER TABLE wishlist ADD COLUMN buy_reason_note TEXT")
        print("  ✓ wishlist.buy_reason_note (their own words)")
        changes += 1

    # ENRICHMENT — a wish carries cover art + the metadata we can muster for free
    # (one iTunes Search call gives artwork, album, year and genre; no API key).
    for col in ("artwork_url", "album", "release_year", "genre", "label"):
        if table_exists(cursor, "wishlist") and not column_exists(cursor, "wishlist", col):
            cursor.execute(f"ALTER TABLE wishlist ADD COLUMN {col} TEXT")
            print(f"  ✓ wishlist.{col} (enrichment)")
            changes += 1

    # THE HUNT — a wish can be a rare/unreleased record you're chasing. Attach the
    # research: notes ("Jyoty, Dekmantel 2024"), links (a forum thread, a YouTube
    # comment), and screenshots of comment sections. So the wishlist manages the
    # whole record-finding process, not just a list of names.
    if not table_exists(cursor, "wishlist_research"):
        cursor.execute("""
            CREATE TABLE wishlist_research (
                id          INTEGER PRIMARY KEY,
                wishlist_id INTEGER NOT NULL REFERENCES wishlist(id) ON DELETE CASCADE,
                kind        TEXT NOT NULL,        -- 'note' | 'link' | 'image'
                text        TEXT,                 -- note body, or a label for a link/image
                url         TEXT,                 -- the link
                image_path  TEXT,                 -- /static/hunt/<name> (a screenshot)
                created_at  TEXT DEFAULT (datetime('now'))
            )""")
        cursor.execute("CREATE INDEX idx_wishlist_research_wid ON wishlist_research(wishlist_id)")
        print("  ✓ wishlist_research (the record hunt)")
        changes += 1

    # Phase-2 telemetry outbox (VISION §4.14): the exact aggregate rollups that were
    # built / sent, kept locally so the user can review and withdraw. No raw events.
    if not table_exists(cursor, "telemetry_outbox"):
        cursor.execute("""
            CREATE TABLE telemetry_outbox (
                id        INTEGER PRIMARY KEY,
                month     TEXT NOT NULL,
                kind      TEXT NOT NULL,          -- 'usage' | 'purchase'
                payload   TEXT NOT NULL,          -- the exact JSON that was/would be sent
                built_at  TEXT DEFAULT (datetime('now')),
                sent_at   TEXT,
                response  TEXT
            )""")
        cursor.execute("CREATE INDEX idx_telemetry_outbox_month ON telemetry_outbox(month)")
        print("  ✓ telemetry_outbox (data charter Phase 2)")
        changes += 1

    # ------------------------------------------------------------------
    # THE RESEARCH DESK — artists / labels / venues / genres as structured,
    # CONNECTABLE entities. Each is a PAGE (a running research log + meta +
    # image) AND a card you can place + connect on the canvas. research_links
    # is the generalized association graph: it joins anything to anything
    # (entity<->entity, entity<->listening-note) with a labelled edge — the
    # "connect disparate things the way a human does" substrate.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "research_entities"):
        cursor.execute("""
            CREATE TABLE research_entities (
                id         INTEGER PRIMARY KEY,
                kind       TEXT NOT NULL,                 -- artist | label | venue | genre
                name       TEXT NOT NULL,
                body       TEXT,                          -- the running research log (long form)
                image_path TEXT,                          -- uploaded image (/static/research/…)
                image_url  TEXT,                          -- or a remote image
                country    TEXT,
                city       TEXT,
                founded    TEXT,                          -- year / era of origin
                links      TEXT,                          -- JSON [{label,url}]
                canvas_x   REAL,
                canvas_y   REAL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""")
        cursor.execute("CREATE UNIQUE INDEX idx_research_entities_kind_name ON research_entities(kind, name)")
        print("  ✓ research desk: research_entities")
        changes += 1
    if not table_exists(cursor, "research_links"):
        cursor.execute("""
            CREATE TABLE research_links (
                id         INTEGER PRIMARY KEY,
                from_kind  TEXT NOT NULL,                 -- 'entity' | 'note'
                from_id    INTEGER NOT NULL,
                to_kind    TEXT NOT NULL,
                to_id      INTEGER NOT NULL,
                label      TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(from_kind, from_id, to_kind, to_id)
            )""")
        print("  ✓ research desk: research_links")
        changes += 1

    # ------------------------------------------------------------------
    # SAVED MAPS — a map the curator MAKES on the canvas (a focused mind-map,
    # e.g. how a city's artists connect through ex-partners) is itself a piece
    # of research. A map = a named set of cards with per-MAP positions; the
    # connections shown are the global research graph among those cards.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "research_maps"):
        cursor.execute("""
            CREATE TABLE research_maps (
                id          INTEGER PRIMARY KEY,
                title       TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ research desk: research_maps")
        changes += 1
    # a mind map can carry its own background — a tone and/or an uploaded image —
    # so each saved map remembers its atmosphere (free canvas uses settings instead).
    for col, typ in (("bg_colour", "TEXT"), ("bg_image", "TEXT")):
        if not column_exists(cursor, "research_maps", col):
            cursor.execute(f"ALTER TABLE research_maps ADD COLUMN {col} {typ}")
            print(f"  ✓ research_maps.{col}")
            changes += 1
    if not table_exists(cursor, "research_map_nodes"):
        cursor.execute("""
            CREATE TABLE research_map_nodes (
                id        INTEGER PRIMARY KEY,
                map_id    INTEGER NOT NULL,
                node_kind TEXT NOT NULL,                  -- 'entity' | 'note'
                node_ref_id INTEGER NOT NULL,
                x         REAL,
                y         REAL,
                UNIQUE(map_id, node_kind, node_ref_id)
            )""")
        print("  ✓ research desk: research_map_nodes")
        changes += 1

    # ------------------------------------------------------------------
    # RESEARCH PROJECTS — a curated subset of the desk (a hand-picked group of
    # artists/labels/venues/genres + maps) the user is exploring. Opening one
    # scopes the rail to just its things; the full library returns on exit.
    # ------------------------------------------------------------------
    if not table_exists(cursor, "research_projects"):
        cursor.execute("""
            CREATE TABLE research_projects (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ research desk: research_projects")
        changes += 1
    if not table_exists(cursor, "research_project_items"):
        cursor.execute("""
            CREATE TABLE research_project_items (
                id         INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                item_kind  TEXT NOT NULL,                 -- 'entity' | 'map'
                item_ref_id INTEGER NOT NULL,
                added_at   TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, item_kind, item_ref_id)
            )""")
        print("  ✓ research desk: research_project_items")
        changes += 1

    # nested FOLDERS inside a project — the user organises a project's things into
    # their own folders (which can nest). An item carries an optional folder_id
    # (NULL = the project root).
    if not table_exists(cursor, "research_folders"):
        cursor.execute("""
            CREATE TABLE research_folders (
                id         INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                parent_id  INTEGER,                       -- NULL = top level in the project
                name       TEXT NOT NULL,
                position   REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ research desk: research_folders")
        changes += 1
    if table_exists(cursor, "research_project_items") and not column_exists(cursor, "research_project_items", "folder_id"):
        cursor.execute("ALTER TABLE research_project_items ADD COLUMN folder_id INTEGER")
        print("  ✓ research desk: research_project_items.folder_id")
        changes += 1

    # v61 — READER MODE: cache of extracted article reading-views (Safari-Reader
    # style). Keyed by url; stores the cleaned body + metadata so re-opening an
    # article is instant + works offline. ok=0 caches a miss (JS-only page) so we
    # don't re-hammer it; refresh re-fetches.
    if not table_exists(cursor, "article_cache"):
        cursor.execute("""
            CREATE TABLE article_cache (
                url        TEXT PRIMARY KEY,
                ok         INTEGER DEFAULT 1,
                title      TEXT,
                byline     TEXT,
                image_url  TEXT,
                published  TEXT,
                source     TEXT,
                body_html  TEXT,
                fetched_at TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ reader: article_cache")
        changes += 1

    # v60 — ROOM BACKDROP: the 3D room renders this image behind the records
    # (the "✦ make this place yours" panel). Kept SEPARATE from places.image_path,
    # which the FOREST illustration pipeline already uses to flip a place to a flat
    # "custom" billboard — reusing it would silently change a place's forest look.
    if table_exists(cursor, "places") and not column_exists(cursor, "places", "room_bg_path"):
        cursor.execute("ALTER TABLE places ADD COLUMN room_bg_path TEXT")
        print("  ✓ room backdrop: places.room_bg_path")
        changes += 1

    # RECORDINGS: captured laptop-audio recordings are tracks flagged
    # is_recording=1 — a DISTINCT category with their own list, kept OUT of the
    # Well grid + the rekordbox library export, but still attachable to sets /
    # Listen / Research through the normal track plumbing.
    if not column_exists(cursor, "tracks", "is_recording"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN is_recording INTEGER DEFAULT 0")
        print("  ✓ recordings: tracks.is_recording")
        changes += 1

    # TESTER FEEDBACK: in-app "log a thought" button (testing phase). Each kind is
    # a quick reaction (like/dislike/confused/bug/idea) + an optional note + the
    # page they were on. Per-install; the tester_name setting labels whose it is.
    if not table_exists(cursor, "tester_feedback"):
        cursor.execute("""
            CREATE TABLE tester_feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kind        TEXT NOT NULL,
                note        TEXT,
                page        TEXT,
                context     TEXT,
                tester      TEXT,
                app_version TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ tester feedback: tester_feedback")
        changes += 1

    # tester_feedback identity: a globally-unique per-feedback `uid` (so rows from
    # different testers' installs merge without colliding) + the local `account_id`
    # they came from. The tester creates a local account once; that account is the
    # identity, not a free-text name they can change at will.
    if table_exists(cursor, "tester_feedback") and not column_exists(cursor, "tester_feedback", "uid"):
        cursor.execute("ALTER TABLE tester_feedback ADD COLUMN uid TEXT")
        print("  ✓ tester feedback: uid")
        changes += 1
    if table_exists(cursor, "tester_feedback") and not column_exists(cursor, "tester_feedback", "account_id"):
        cursor.execute("ALTER TABLE tester_feedback ADD COLUMN account_id TEXT")
        print("  ✓ tester feedback: account_id")
        changes += 1
    # outbox: when set, the row has been pushed to David's collection endpoint
    if table_exists(cursor, "tester_feedback") and not column_exists(cursor, "tester_feedback", "sent_at"):
        cursor.execute("ALTER TABLE tester_feedback ADD COLUMN sent_at TEXT")
        print("  ✓ tester feedback: sent_at (outbox)")
        changes += 1

    # RADIO SHOWS: a set can be a radio show (set_type='radio') — written in
    # the Music Room: the running order (set_tracks), a SCRIPT, research
    # (existing sets.research), show links, and a per-track PUBLIC note for
    # the published descriptive tracklist (who made it, why it's here —
    # David talks over nothing on air; the tracklist does the telling).
    if not column_exists(cursor, "sets", "script"):
        cursor.execute("ALTER TABLE sets ADD COLUMN script TEXT")
        print("  ✓ radio shows: sets.script")
        changes += 1
    if not column_exists(cursor, "sets", "show_links"):
        cursor.execute("ALTER TABLE sets ADD COLUMN show_links TEXT")   # JSON [{url,title}]
        print("  ✓ radio shows: sets.show_links")
        changes += 1
    if not column_exists(cursor, "set_tracks", "public_note"):
        cursor.execute("ALTER TABLE set_tracks ADD COLUMN public_note TEXT")
        print("  ✓ radio shows: set_tracks.public_note")
        changes += 1

    # SHOWCASE: the user's shop-front page — a CURATED mix of things they chose
    # to show (tracks, whole albums, links, saved articles, listening notes),
    # in their own order. Published as the static shareable room page. One
    # showcase per install for now; a showcase_id column is the later path to
    # several. Kinds: track (track_id) · album (album + album_artist) ·
    # link (url/title/subtitle/image_url) · article (note_id → listening_notes
    # reference) · note (note_id → listening_notes moment).
    if not table_exists(cursor, "showcase_items"):
        cursor.execute("""
            CREATE TABLE showcase_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kind         TEXT NOT NULL,
                track_id     INTEGER,
                note_id      INTEGER,
                album        TEXT,
                album_artist TEXT,
                url          TEXT,
                title        TEXT,
                subtitle     TEXT,
                image_url    TEXT,
                position     INTEGER DEFAULT 0,
                added_at     TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ showcase: showcase_items")
        changes += 1

    # GREEN ROOM: tracks borrowed from a campus gr_server (the GR builds).
    # The borrowed file sits encrypted under DATA_DIR/green_room and only the
    # key here can play it (decrypted in memory by the Seinnteoir, never
    # written plain). file_path NULL = offloaded: the borrow is kept but its
    # bytes are off this disk until redownloaded.
    if not table_exists(cursor, "gr_borrows"):
        cursor.execute("""
            CREATE TABLE gr_borrows (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                server_borrow_id INTEGER NOT NULL UNIQUE,
                server_track_id  INTEGER,
                title            TEXT,
                artist           TEXT,
                album            TEXT,
                duration_s       REAL,
                format           TEXT,
                size_bytes       INTEGER,
                price_cents      INTEGER,
                key_hex          TEXT NOT NULL,
                nonce_hex        TEXT NOT NULL,
                file_path        TEXT,
                borrowed_at      TEXT DEFAULT (datetime('now')),
                returned_at      TEXT
            )""")
        print("  ✓ green room: gr_borrows")
        changes += 1

    # GREEN ROOM, round two (GR1 brief, 2026-10-21): borrowed records live IN
    # the room as ordinary track rows, marked. tracks.gr_borrow_id links the
    # row to its borrow (NULL again once bought — the plain file replaces the
    # locked one); gr_track_id is the server's record id (cover, artist room).
    if not column_exists(cursor, "tracks", "gr_borrow_id"):
        cursor.execute("ALTER TABLE tracks ADD COLUMN gr_borrow_id INTEGER")
        cursor.execute("ALTER TABLE tracks ADD COLUMN gr_track_id INTEGER")
        print("  ✓ green room: tracks.gr_borrow_id / gr_track_id")
        changes += 1
    if table_exists(cursor, "gr_borrows") and not column_exists(cursor, "gr_borrows", "track_id"):
        cursor.execute("ALTER TABLE gr_borrows ADD COLUMN track_id INTEGER")
        print("  ✓ green room: gr_borrows.track_id")
        changes += 1

    # GREEN ROOM BASKET: pool records set aside to borrow or buy later. One
    # basket; each line remembers which. Snapshots title/artist/price so the
    # basket reads even with the server out of reach.
    if not table_exists(cursor, "gr_basket"):
        cursor.execute("""
            CREATE TABLE gr_basket (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                server_track_id  INTEGER NOT NULL UNIQUE,
                mode             TEXT NOT NULL DEFAULT 'borrow',   -- 'borrow' | 'buy'
                title            TEXT,
                artist           TEXT,
                owner_handle     TEXT,
                owner_name       TEXT,
                price_cents      INTEGER,
                has_art          INTEGER DEFAULT 0,
                art_v            INTEGER DEFAULT 0,
                added_at         TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ green room: gr_basket")
        changes += 1

    # ACTIVITY OUTBOX: app-side events (pages, plays, searches…) queue here
    # and go to the server in batches — nothing is lost offline.
    if not table_exists(cursor, "gr_events_outbox"):
        cursor.execute("""
            CREATE TABLE gr_events_outbox (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                kind  TEXT NOT NULL,
                data  TEXT,
                at    TEXT DEFAULT (datetime('now'))
            )""")
        print("  ✓ activity: gr_events_outbox")
        changes += 1

    # GRÚPA: a playlist that holds anything — records, labels, artists, places,
    # sets, streaming links, other music rooms — each with a note (grupa.py).
    import grupa as _grupa
    if _grupa.ensure(cursor):
        print("  ✓ grúpa: grupa + grupa_items")
        changes += 1

    # A wish can be for a record sold in the Music Room (record shopping: "note it").
    import record_shop as _record_shop
    if _record_shop.wish_ensure(cursor):
        print("  ✓ wishlist.gr_track_id")
        changes += 1

    conn.commit()
    conn.close()

    print("")
    if changes > 0:
        print(f"  {changes} change(s) applied.")
    else:
        print("  Database already up to date.")
    print("=============================================================")
    print("")


if __name__ == "__main__":
    run_migration()
