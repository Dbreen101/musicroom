"""
=============================================================
MUSIC ROOM — enricher.py
=============================================================
What this does:
    Fetches contextual data about artists and tracks from the
    Claude API and stores it in the database.

    This is a caching layer — each artist is fetched once and
    stored permanently. Re-running never re-fetches unless you
    pass --force.

    The data is used by:
        - The Learn page (quiz, stats, artist map)
        - The track panel (inline facts)
        - The quiz engine (generating questions and answers)

How to run:
    source venv/bin/activate

    # Enrich all artists in your library (unknown artists skipped)
    python3 enricher.py --artists

    # Enrich a specific artist
    python3 enricher.py --artist "Actress"

    # Re-fetch even if already enriched
    python3 enricher.py --artists --force

    # Show enrichment coverage stats
    python3 enricher.py --stats

Notes:
    - Each artist costs one API call (~200–400 tokens)
    - Runs at ~2 artists/second (rate limit headroom)
    - Skips artists with no name, or names that look like
      file metadata noise ("Unknown Artist", "Track 01", etc.)
    - Stores errors so you can see what failed and why

API key:
    The Claude API key is read from the ANTHROPIC_API_KEY
    environment variable. Flask's /api routes use the same
    key injected by claude.ai's artifact proxy — but this
    script runs outside that context so the env var must
    be set:
        export ANTHROPIC_API_KEY="sk-ant-..."
=============================================================
"""

import sqlite3
import os
import json
import time
import argparse
import re
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from mr_paths import DB_PATH  # noqa: E402  (shared data dir; see mr_paths.py)

# Artist names that are clearly not real artist names
SKIP_NAMES = {
    "", "unknown", "unknown artist", "various", "various artists",
    "va", "v.a.", "v/a", "untitled", "artist", "track", "unnamed",
}

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-sonnet-4-20250514"

# ------------------------------------------------------------
# How the quiz question format works:
# Claude returns a structured JSON object. This schema is also
# used by the Flask API when generating quiz questions on demand.
# ------------------------------------------------------------

ARTIST_PROFILE_PROMPT = """You are a music encyclopedia. Given an artist name, return a JSON object with factual information about them.

Artist: {artist_name}

Return ONLY valid JSON, no preamble, no markdown, no explanation. Use null for anything you're genuinely uncertain about — do not guess or hallucinate.

Schema:
{{
    "country": "Country of origin, e.g. Germany. null if unknown.",
    "city": "City most associated with them, e.g. Berlin. null if unknown.",
    "latitude": numeric latitude of that city, null if unknown,
    "longitude": numeric longitude of that city, null if unknown,
    "active_from": year they started (integer), null if unknown,
    "active_to": year they stopped, null if still active or unknown,
    "gender": "male | female | non-binary | duo | group | null",
    "ethnicity_notes": "Brief factual note e.g. 'Nigerian-British'. null if not publicly known.",
    "genres": "comma-separated genres, most specific first, e.g. 'dub techno, minimal techno, techno'",
    "labels": "comma-separated main labels e.g. 'Basic Channel, Chain Reaction'",
    "scene": "One sentence on their scene/era, e.g. 'Core figure of the Berlin minimal techno scene of the late 1990s.'",
    "influences": "comma-separated artists who influenced them",
    "bio_summary": "2-3 factual sentences. No hype. Focus on origin, sound, significance.",
    "notable_works": "comma-separated key releases (title, year if known)",
    "wikipedia_note": "Does a Wikipedia article exist? e.g. 'Yes' or 'Discogs only' or 'Limited online presence'"
}}"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def should_skip(name):
    if not name:
        return True
    clean = name.strip().lower()
    if clean in SKIP_NAMES:
        return True
    # Skip if it looks like a filename fragment or track number
    if re.match(r'^(track|file|audio|unknown|untitled)[\s_\-]?\d*$', clean):
        return True
    return False


def call_claude(prompt, api_key):
    """
    Makes a single call to the Claude API.
    Returns the text response or raises an exception.
    """
    payload = json.dumps({
        "model":      MODEL,
        "max_tokens": 800,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data    = payload,
        headers = {
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method = "POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["content"][0]["text"]


def enrich_artist(artist_name, api_key, conn, force=False):
    """
    Fetches and stores enrichment data for one artist.
    Returns True on success, False on skip/failure.
    """
    cursor = conn.cursor()

    if not force:
        cursor.execute(
            "SELECT enriched_at, fetch_error FROM artist_profiles WHERE artist_name = ?",
            (artist_name,)
        )
        existing = cursor.fetchone()
        if existing and existing["enriched_at"]:
            return True  # already done

    prompt   = ARTIST_PROFILE_PROMPT.format(artist_name=artist_name)
    raw_text = call_claude(prompt, api_key)

    # Strip any markdown fences Claude might add despite instructions
    raw_text = re.sub(r'^```[a-z]*\n?', '', raw_text.strip())
    raw_text = re.sub(r'\n?```$', '', raw_text.strip())

    data = json.loads(raw_text)

    cursor.execute("""
        INSERT INTO artist_profiles (
            artist_name, country, city, latitude, longitude,
            active_from, active_to, gender, ethnicity_notes,
            genres, labels, scene, influences, bio_summary,
            notable_works, wikipedia_note, enriched_at, fetch_error, updated_at
        ) VALUES (
            :artist_name, :country, :city, :latitude, :longitude,
            :active_from, :active_to, :gender, :ethnicity_notes,
            :genres, :labels, :scene, :influences, :bio_summary,
            :notable_works, :wikipedia_note, datetime('now'), NULL, datetime('now')
        )
        ON CONFLICT(artist_name) DO UPDATE SET
            country         = excluded.country,
            city            = excluded.city,
            latitude        = excluded.latitude,
            longitude       = excluded.longitude,
            active_from     = excluded.active_from,
            active_to       = excluded.active_to,
            gender          = excluded.gender,
            ethnicity_notes = excluded.ethnicity_notes,
            genres          = excluded.genres,
            labels          = excluded.labels,
            scene           = excluded.scene,
            influences      = excluded.influences,
            bio_summary     = excluded.bio_summary,
            notable_works   = excluded.notable_works,
            wikipedia_note  = excluded.wikipedia_note,
            enriched_at     = datetime('now'),
            fetch_error     = NULL,
            updated_at      = datetime('now')
    """, {
        "artist_name":    artist_name,
        "country":        data.get("country"),
        "city":           data.get("city"),
        "latitude":       data.get("latitude"),
        "longitude":      data.get("longitude"),
        "active_from":    data.get("active_from"),
        "active_to":      data.get("active_to"),
        "gender":         data.get("gender"),
        "ethnicity_notes":data.get("ethnicity_notes"),
        "genres":         data.get("genres"),
        "labels":         data.get("labels"),
        "scene":          data.get("scene"),
        "influences":     data.get("influences"),
        "bio_summary":    data.get("bio_summary"),
        "notable_works":  data.get("notable_works"),
        "wikipedia_note": data.get("wikipedia_note"),
    })
    conn.commit()
    return True


def store_error(artist_name, error_msg, conn):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO artist_profiles (artist_name, fetch_error, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(artist_name) DO UPDATE SET
            fetch_error = excluded.fetch_error,
            updated_at  = datetime('now')
    """, (artist_name, str(error_msg)))
    conn.commit()


def get_unique_artists(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT artist_name
        FROM tracks
        WHERE artist_name IS NOT NULL
          AND artist_name != ''
          AND is_deleted = 0
        ORDER BY artist_name
    """)
    return [row["artist_name"] for row in cursor.fetchall()]


def run_enrich_all(api_key, force=False):
    conn    = get_db()
    artists = get_unique_artists(conn)
    artists = [a for a in artists if not should_skip(a)]

    if not force:
        # Filter out already enriched
        cursor = conn.cursor()
        cursor.execute(
            "SELECT artist_name FROM artist_profiles WHERE enriched_at IS NOT NULL"
        )
        done = {row["artist_name"] for row in cursor.fetchall()}
        artists = [a for a in artists if a not in done]

    print(f"\n  {len(artists)} artists to enrich.")
    if not artists:
        print("  Nothing to do. Use --force to re-fetch.\n")
        conn.close()
        return

    print("  Press Ctrl+C to stop — progress is saved.\n")

    done_count = 0
    fail_count = 0

    for i, artist in enumerate(artists):
        try:
            print(f"  [{i+1}/{len(artists)}] {artist}... ", end="", flush=True)
            enrich_artist(artist, api_key, conn, force=force)
            print("✓")
            done_count += 1
            time.sleep(0.5)  # gentle rate limiting
        except json.JSONDecodeError as e:
            print(f"✗ JSON parse error")
            store_error(artist, f"JSON parse error: {e}", conn)
            fail_count += 1
        except urllib.error.HTTPError as e:
            print(f"✗ HTTP {e.code}")
            store_error(artist, f"HTTP {e.code}: {e.reason}", conn)
            fail_count += 1
            if e.code == 429:
                print("  Rate limited — sleeping 10s...")
                time.sleep(10)
        except Exception as e:
            print(f"✗ {e}")
            store_error(artist, str(e), conn)
            fail_count += 1

    conn.close()
    print(f"\n  Done. Enriched: {done_count}  Failed: {fail_count}\n")


def run_stats():
    conn    = get_db()
    cursor  = conn.cursor()

    total_artists = cursor.execute(
        "SELECT COUNT(DISTINCT artist_name) as n FROM tracks WHERE artist_name IS NOT NULL AND artist_name != '' AND is_deleted = 0"
    ).fetchone()["n"]

    enriched = cursor.execute(
        "SELECT COUNT(*) as n FROM artist_profiles WHERE enriched_at IS NOT NULL"
    ).fetchone()["n"]

    failed = cursor.execute(
        "SELECT COUNT(*) as n FROM artist_profiles WHERE fetch_error IS NOT NULL AND enriched_at IS NULL"
    ).fetchone()["n"]

    with_geo = cursor.execute(
        "SELECT COUNT(*) as n FROM artist_profiles WHERE latitude IS NOT NULL"
    ).fetchone()["n"]

    print(f"""
  Artist enrichment stats:
    Total unique artists in library: {total_artists}
    Enriched:                        {enriched}
    Failed:                          {failed}
    Remaining:                       {total_artists - enriched - failed}
    With geographic data:            {with_geo}
    Coverage:                        {round(enriched/total_artists*100) if total_artists else 0}%
""")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich Music Room artist data")
    parser.add_argument("--artists",     action="store_true", help="Enrich all unenriched artists")
    parser.add_argument("--artist",      type=str,            help="Enrich a single artist by name")
    parser.add_argument("--force",       action="store_true", help="Re-fetch even if already enriched")
    parser.add_argument("--stats",       action="store_true", help="Show enrichment coverage")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if args.stats:
        run_stats()
    elif args.artist:
        if not api_key:
            print("\n  Error: ANTHROPIC_API_KEY env var not set.\n")
        else:
            conn = get_db()
            try:
                print(f"\n  Enriching: {args.artist}... ", end="", flush=True)
                enrich_artist(args.artist, api_key, conn, force=args.force)
                print("✓\n")
            except Exception as e:
                print(f"✗ {e}\n")
            conn.close()
    elif args.artists:
        if not api_key:
            print("\n  Error: ANTHROPIC_API_KEY env var not set.\n")
        else:
            run_enrich_all(api_key, force=args.force)
    else:
        parser.print_help()
