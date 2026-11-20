"""
=============================================================
MUSIC ROOM — artwork_fetcher.py
=============================================================
Album artwork pipeline — two-phase batch:

  Phase 1  Scan every track for embedded art (fast, local,
           no network). Reads the audio file with mutagen and
           pulls any APIC/FLAC picture/MP4 covr tag.  No sleep
           needed — it's just file I/O.

  Phase 2  Only the tracks still without artwork after Phase 1
           are sent to MusicBrainz + Cover Art Archive.  Each
           lookup is two HTTP requests (search + image), so a
           polite 1 s delay is kept between tracks here.

Stores artwork as {track_id}.jpg in the Artwork/ folder on the
external drive. Falls back to static/artwork/ if drive not mounted.
=============================================================
"""

import os
import re
import time
import json
import sqlite3
import urllib.request
import urllib.parse
import threading
from pathlib import Path

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
from mr_paths import DB_PATH, ARTWORK_LOCAL_DIR  # noqa: E402 (shared data dir)
USER_AGENT   = "MusicRoom/1.0 (personal DJ library)"

ARTWORK_DRIVE_PATH = Path("/Volumes/EXTERNAL HARD DRIVE 1/Music Room Library/Artwork")
# Local artwork now lives in the writable data dir (project folder in dev,
# Application Support when bundled) so it works on any machine.
ARTWORK_LOCAL_PATH = Path(ARTWORK_LOCAL_DIR)


# =============================================================
# Artwork directory
# =============================================================

def get_artwork_dir() -> Path:
    """Return the artwork directory. Drive preferred; local fallback."""
    if ARTWORK_DRIVE_PATH.parent.exists():
        return ARTWORK_DRIVE_PATH
    volumes = Path("/Volumes")
    if volumes.exists():
        for vol in volumes.iterdir():
            candidate = vol / "Music Room Library" / "Artwork"
            if candidate.parent.exists():
                return candidate
    return ARTWORK_LOCAL_PATH


def _save_artwork(data: bytes, track_id: int) -> str | None:
    art_dir = get_artwork_dir()
    try:
        art_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    path = art_dir / f"{track_id}.jpg"
    try:
        path.write_bytes(data)
        return str(path)
    except Exception:
        return None


# =============================================================
# Phase 1 — embedded art (mutagen)
# =============================================================

def _embedded_bytes(file_path: str) -> bytes | None:
    """Raw embedded cover-art bytes from an audio file, or None. Shared by
    extract_embedded (which saves) and the candidate-preview flow (which doesn't)."""
    try:
        from mutagen import File as MutagenFile
        af = MutagenFile(file_path)
        if af is None:
            return None
        data = None
        # ID3 APIC frame (MP3)
        if hasattr(af, "tags") and af.tags:
            for key in af.tags.keys():
                if key.startswith("APIC"):
                    raw = af.tags[key].data
                    if raw and len(raw) > 100:
                        data = raw
                        break
        # FLAC picture blocks
        if data is None and hasattr(af, "pictures") and af.pictures:
            raw = af.pictures[0].data
            if raw and len(raw) > 100:
                data = raw
        # MP4/M4A covr atom
        if data is None and hasattr(af, "tags") and af.tags:
            covr = af.tags.get("covr")
            if covr and len(covr) > 0:
                raw = bytes(covr[0])
                if len(raw) > 100:
                    data = raw
        return data
    except Exception:
        return None


def extract_embedded(file_path: str, track_id: int) -> str | None:
    """Pull embedded cover art from audio file. Returns saved path or None."""
    data = _embedded_bytes(file_path)
    return _save_artwork(data, track_id) if data else None


# =============================================================
# Phase 2 — iTunes Search API (primary) + MusicBrainz fallback
# =============================================================

_TITLE_STRIP = re.compile(
    r'\s*[\(\[](original mix|radio edit|club mix|extended mix|extended version|'
    r'original version|original|album version|single version|lp version|'
    r'feat\.?[^)\]]*|ft\.?[^)\]]*|featuring[^)\]]*)[\)\]]\s*$',
    re.IGNORECASE,
)
_FEAT_INLINE = re.compile(r'\s+feat\.?\s+.+$', re.IGNORECASE)


def _clean_title(title: str) -> str:
    """Strip mix/version/feat suffixes for a cleaner iTunes search term."""
    t = _TITLE_STRIP.sub('', title.strip())
    t = _FEAT_INLINE.sub('', t).strip()
    return t


def _try_itunes_term(term: str, track_id: int) -> str | None:
    """One iTunes search attempt; returns saved artwork path or None."""
    url = (
        "https://itunes.apple.com/search?"
        + urllib.parse.urlencode({"term": term, "entity": "song", "limit": 5})
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None

    for result in data.get("results", []):
        art_url = result.get("artworkUrl100")
        if not art_url:
            continue
        art_url = art_url.replace("100x100bb", "600x600bb")
        try:
            req = urllib.request.Request(art_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                img_data = resp.read()
            if len(img_data) > 5000:
                return _save_artwork(img_data, track_id)
        except Exception:
            continue
    return None


def fetch_itunes(title: str, artist: str, track_id: int) -> str | None:
    """
    Search Apple's iTunes Search API for artwork.
    Tries the original title first, then a cleaned version (strips
    "(Original Mix)", "(Radio Edit)", feat. tags, etc.) for better hit rate.
    """
    if not title and not artist:
        return None

    # First attempt: full term
    term = f"{artist} {title}".strip()
    result = _try_itunes_term(term, track_id)
    if result:
        return result

    # Second attempt: cleaned title (strip mix/version/feat suffixes)
    if title:
        cleaned = _clean_title(title)
        if cleaned and cleaned.lower() != title.lower().strip():
            clean_term = f"{artist} {cleaned}".strip()
            result = _try_itunes_term(clean_term, track_id)
            if result:
                return result

    return None


def _mb_request(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _caa_fetch(mbid: str) -> bytes | None:
    """Fetch front cover from Cover Art Archive. Returns raw bytes or None."""
    url = f"https://coverartarchive.org/release/{mbid}/front-500"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) > 5000:
                return data
    except Exception:
        pass
    return None


# NOTE: a Spotify-search artwork source used to live here. Removed — the
# Spotify API is now used ONLY for the user's own library (saved tracks /
# playlists / wishlists), never for searching arbitrary tracks. Deezer
# (by ISRC) + iTunes + MusicBrainz + Discogs cover artwork.


def fetch_discogs(title: str, artist: str, track_id: int) -> str | None:
    """Search Discogs for a matching release and pull the primary image.
    Requires the discogs_token setting. Silent no-op if no token."""
    if not title or not artist:
        return None
    try:
        # Thread-safe variant — fetch_discogs runs inside the batch
        # worker thread which has no Flask request context. The regular
        # get_setting() crashes there. _get_setting_threadsafe opens its
        # own SQLite connection.
        from app import _get_setting_threadsafe
    except Exception:
        return None
    token = (_get_setting_threadsafe("discogs_token", "") or "").strip()
    if not token:
        return None
    qs = urllib.parse.urlencode({
        "artist": artist, "track": title, "type": "release",
        "token": token, "per_page": 5,
    })
    url = f"https://api.discogs.com/database/search?{qs}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Authorization": f"Discogs token={token}",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
    except Exception:
        return None
    for r in (payload.get("results") or []):
        # Cheap path: the search result itself often has cover_image
        cover = r.get("cover_image") or r.get("thumb")
        if cover and "spacer.gif" not in cover:
            try:
                ireq = urllib.request.Request(cover, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(ireq, timeout=10) as iresp:
                    data = iresp.read()
                if len(data) > 5000:
                    return _save_artwork(data, track_id)
            except Exception:
                continue
    return None


def fetch_musicbrainz(title: str, artist: str, track_id: int) -> str | None:
    """Search MusicBrainz and fetch artwork from Cover Art Archive."""
    if not title and not artist:
        return None

    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')
    q = urllib.parse.quote(" AND ".join(parts))
    url = f"https://musicbrainz.org/ws/2/recording?query={q}&fmt=json&limit=5"

    data = _mb_request(url)
    if not data:
        return None

    recordings = data.get("recordings", [])
    for rec in recordings:
        for release in rec.get("releases", []):
            mbid = release.get("id")
            if not mbid:
                continue
            art = _caa_fetch(mbid)
            if art:
                return _save_artwork(art, track_id)
            time.sleep(0.15)  # polite between CAA requests

    return None


def fetch_deezer_isrc(isrc: str, track_id: int) -> str | None:
    """Exact album-art lookup by ISRC via Deezer. No auth, generous
    limits, high-res covers. Returns saved path or None. Reuses the
    rate-gated Deezer client in dsp_lookup."""
    if not isrc:
        return None
    try:
        from dsp_lookup import deezer_track_by_isrc
        tr = deezer_track_by_isrc(isrc)
    except Exception:
        return None
    if not tr:
        return None
    album = tr.get("album") or {}
    img_url = album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium")
    if not img_url:
        return None
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        if len(data) > 5000:
            return _save_artwork(data, track_id)
    except Exception:
        pass
    return None


# =============================================================
# Single-track fetch (used by per-track button in place.html)
# =============================================================

def _open_db_wal():
    """Open a SQLite connection with WAL mode + busy_timeout — needed so
    the artwork worker doesn't bump heads with the DSP / Label batches
    that run alongside it."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _update_db(track_id: int, path: str, source: str, verified: int = 0):
    # Every committed cover gets its dominant colour at the same moment —
    # the Colour sort/wheel are otherwise invisibly empty for a fresh library.
    colour = None
    try:
        from art_colour import dominant_colour
        colour = dominant_colour(path)
    except Exception:
        pass
    with _open_db_wal() as conn:
        conn.execute(
            "UPDATE tracks SET artwork_path=?, artwork_source=?, artwork_verified=?, "
            "art_colour=COALESCE(?, art_colour) WHERE id=?",
            (path, source, verified, colour, track_id),
        )


def _mark_not_found(track_id: int):
    """Mark a track as searched but no artwork found — so the batch skips it next time."""
    with _open_db_wal() as conn:
        conn.execute(
            "UPDATE tracks SET artwork_source='not_found' WHERE id=? AND artwork_path IS NULL",
            (track_id,),
        )


# =============================================================
# Candidate previews — fetch raw bytes for ONE source WITHOUT committing, so the
# user can choose a primary cover in the panel (embedded vs online). Reuses the
# same HTTP as the committing fetchers above.
# =============================================================

def _itunes_bytes(title: str, artist: str) -> bytes | None:
    terms = [f"{artist} {title}".strip()]
    if title:
        cleaned = _clean_title(title)
        if cleaned and cleaned.lower() != title.lower().strip():
            terms.append(f"{artist} {cleaned}".strip())
    for term in terms:
        if not term:
            continue
        url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": term, "entity": "song", "limit": 5})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception:
            continue
        for result in data.get("results", []):
            art_url = result.get("artworkUrl100")
            if not art_url:
                continue
            art_url = art_url.replace("100x100bb", "600x600bb")
            try:
                req = urllib.request.Request(art_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    img = resp.read()
                if len(img) > 5000:
                    return img
            except Exception:
                continue
    return None


def _caa_bytes(title: str, artist: str) -> bytes | None:
    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')
    if not parts:
        return None
    q = urllib.parse.quote(" AND ".join(parts))
    data = _mb_request(f"https://musicbrainz.org/ws/2/recording?query={q}&fmt=json&limit=5")
    if not data:
        return None
    for rec in data.get("recordings", []):
        for release in rec.get("releases", []):
            mbid = release.get("id")
            if not mbid:
                continue
            art = _caa_fetch(mbid)
            if art:
                return art
            time.sleep(0.15)
    return None


def _discogs_bytes(title: str, artist: str) -> bytes | None:
    if not title or not artist:
        return None
    try:
        from app import _get_setting_threadsafe
    except Exception:
        return None
    token = (_get_setting_threadsafe("discogs_token", "") or "").strip()
    if not token:
        return None
    qs = urllib.parse.urlencode({"artist": artist, "track": title, "type": "release",
                                 "token": token, "per_page": 5})
    try:
        req = urllib.request.Request(f"https://api.discogs.com/database/search?{qs}",
            headers={"User-Agent": USER_AGENT, "Authorization": f"Discogs token={token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
    except Exception:
        return None
    for r in (payload.get("results") or []):
        cover = r.get("cover_image") or r.get("thumb")
        if cover and "spacer.gif" not in cover:
            try:
                ireq = urllib.request.Request(cover, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(ireq, timeout=10) as iresp:
                    data = iresp.read()
                if len(data) > 5000:
                    return data
            except Exception:
                continue
    return None


def candidate_bytes(source: str, *, file_path: str | None = None,
                    title: str | None = None, artist: str | None = None) -> bytes | None:
    """Raw cover-art bytes for one source, NOT saved/committed. For the cover picker."""
    if source == "embedded":
        return _embedded_bytes(file_path) if file_path else None
    if source == "itunes":
        return _itunes_bytes(title or "", artist or "")
    if source in ("musicbrainz", "caa"):
        return _caa_bytes(title or "", artist or "")
    if source == "discogs":
        return _discogs_bytes(title or "", artist or "")
    return None


def fetch_for_track(track_id: int) -> dict:
    """Fetch artwork for one track. Returns {ok, source, path}."""
    with _open_db_wal() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT t.id, t.title, t.artist_name, t.isrc, f.file_path
               FROM tracks t LEFT JOIN files f ON f.track_id=t.id AND f.is_primary=1
               WHERE t.id=? AND t.is_deleted=0""",
            (track_id,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "not found"}

    # 1. Embedded art (fast)
    if row["file_path"] and os.path.exists(row["file_path"]):
        path = extract_embedded(row["file_path"], track_id)
        if path:
            _update_db(track_id, path, "embedded")
            return {"ok": True, "source": "embedded", "path": path}

    # 1b. Deezer by ISRC — exact, free, high-res. Only when we have one.
    if row["isrc"]:
        path = fetch_deezer_isrc(row["isrc"], track_id)
        if path:
            _update_db(track_id, path, "deezer")
            return {"ok": True, "source": "deezer", "path": path}

    # 2. iTunes Search API (good coverage for commercial/electronic music)
    path = fetch_itunes(row["title"] or "", row["artist_name"] or "", track_id)
    if path:
        _update_db(track_id, path, "itunes")
        return {"ok": True, "source": "itunes", "path": path}

    # 3. MusicBrainz + Cover Art Archive (fallback)
    path = fetch_musicbrainz(row["title"] or "", row["artist_name"] or "", track_id)
    if path:
        _update_db(track_id, path, "musicbrainz")
        return {"ok": True, "source": "musicbrainz", "path": path}

    return {"ok": False, "source": None, "path": None}


# =============================================================
# Batch state
# =============================================================

_batch_lock         = threading.Lock()
_batch_running      = False
_batch_should_stop  = False   # set by request_stop() — checked each track
_batch_progress = {
    "running":       False,
    "phase":         0,       # 1 = local scan, 2 = online lookup
    "phase_label":   "",
    "phase_done":    0,
    "phase_total":   0,
    "total_done":    0,       # tracks fully processed (found + not_found)
    "found_count":   0,       # tracks that actually got artwork
    "grand_total":   0,       # all tracks that entered the batch
}


def request_stop():
    """Signal the running batch (if any) to halt after the current track.
    All completed work is already committed per-track via the with-connect
    pattern, so nothing is lost."""
    global _batch_should_stop
    _batch_should_stop = True


def get_batch_progress() -> dict:
    return dict(_batch_progress)


# =============================================================
# Two-phase batch
# =============================================================

def run_batch_fetch(phase_only: int | None = None, retry_not_found: bool = False):
    """
    Phase 1 — fast local scan
    ─────────────────────────
    Read every track's primary audio file with mutagen and save any
    embedded artwork.  No network, no sleep.  Typically completes in
    1–3 minutes for a library of ~2000 tracks.

    Phase 2 — online lookup (MusicBrainz only)
    ──────────────────────────────────────────
    Only the tracks that came out of Phase 1 with no artwork are sent
    to MusicBrainz.  Each lookup makes 1 search request + up to a few
    image requests.  A 1 s delay between tracks keeps us within
    MusicBrainz's rate-limit (1 req/sec).  With ~500 unknown tracks this
    takes roughly 8–15 minutes depending on hit-rate.
    """
    global _batch_running, _batch_progress, _batch_should_stop

    with _batch_lock:
        if _batch_running:
            return
        _batch_running = True
        _batch_should_stop = False   # fresh run — clear any prior stop signal

    # ── fetch tracks without artwork ──────────────────────────────────────────
    # phase_only=1 → embedded scan only; phase_only=2 → online only; None → both
    # By default skip tracks marked 'not_found' (we already tried + failed)
    # — retry_not_found=True opts back in. iTunes/MB/embedded/manual results
    # are always excluded (already found something).
    EXCLUDED_BASE = ('embedded', 'musicbrainz', 'itunes', 'manual', 'spotify', 'discogs', 'deezer')
    if retry_not_found:
        excluded = EXCLUDED_BASE
    else:
        excluded = EXCLUDED_BASE + ('not_found',)
    placeholders = ",".join("?" * len(excluded))

    with _open_db_wal() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""SELECT t.id, t.title, t.artist_name, t.isrc, f.file_path
               FROM tracks t
               LEFT JOIN files f ON f.track_id = t.id AND f.is_primary = 1
               WHERE t.artwork_path IS NULL
                 AND (t.artwork_source IS NULL OR t.artwork_source NOT IN ({placeholders}))
                 AND t.is_deleted = 0
               ORDER BY t.artist_name, t.title""",
            excluded,
        ).fetchall()

    all_tracks = [dict(r) for r in rows]
    grand_total = len(all_tracks)

    phase_label = ("Scanning files" if phase_only == 1
                   else "Searching online" if phase_only == 2
                   else "Scanning files for embedded art")
    _batch_progress = {
        "running":     True,
        "phase":       1 if phase_only != 2 else 2,
        "phase_label": phase_label,
        "phase_done":  0,
        "phase_total": grand_total,
        "total_done":  0,
        "found_count": 0,
        "grand_total": grand_total,
    }

    print(f"[artwork] batch start (phase_only={phase_only}) — {grand_total} tracks")

    # ── colour catch-up: covers that exist but never got an art_colour
    # (imports from before the colour system, or interrupted batches). Local
    # Pillow-only, so it's cheap; makes any library's Colour sort/wheel real.
    try:
        from art_colour import dominant_colour
        with _open_db_wal() as conn:
            conn.row_factory = sqlite3.Row
            stale = conn.execute(
                """SELECT id, artwork_path FROM tracks
                   WHERE artwork_path IS NOT NULL AND art_colour IS NULL
                     AND is_deleted = 0""").fetchall()
        fixed = 0
        for r in stale:
            if _batch_should_stop:
                break
            col = dominant_colour(r["artwork_path"]) if os.path.exists(r["artwork_path"] or "") else None
            if col:
                with _open_db_wal() as conn:
                    conn.execute("UPDATE tracks SET art_colour=? WHERE id=?", (col, r["id"]))
                fixed += 1
        if stale:
            print(f"[artwork] colour catch-up — {fixed}/{len(stale)} covers coloured")
    except Exception as exc:
        print(f"[artwork] colour catch-up skipped: {exc}")

    embedded_found = 0
    needs_online   = []   # track dicts that had no embedded art
    total_done     = 0    # tracks fully processed

    try:
        # ── PHASE 1: local embedded scan ──────────────────────────────
        phase1_tracks = all_tracks if phase_only != 2 else []
        if phase1_tracks:
            print(f"[artwork] Phase 1: scanning {len(phase1_tracks)} files for embedded art…")
        for idx, track in enumerate(phase1_tracks):
            if _batch_should_stop:
                break
            tid       = track["id"]
            file_path = track.get("file_path") or ""
            found     = False

            if file_path and os.path.exists(file_path):
                path = extract_embedded(file_path, tid)
                if path:
                    _update_db(tid, path, "embedded")
                    embedded_found += 1
                    found = True

            if found:
                total_done += 1
            else:
                needs_online.append(track)

            _batch_progress["phase_done"]  = idx + 1
            _batch_progress["found_count"] = embedded_found
            _batch_progress["total_done"]  = total_done

        if phase1_tracks:
            print(
                f"[artwork] Phase 1 done — {embedded_found} embedded, "
                f"{len(needs_online)} need online lookup"
            )

        # For phase_only=2, send ALL fetched tracks to online search
        if phase_only == 2:
            needs_online = all_tracks

        # ── PHASE 2: iTunes → MusicBrainz for the rest ────────────────
        if needs_online and phase_only != 1:
            online_total = len(needs_online)
            _batch_progress.update({
                "phase":       2,
                "phase_label": "Searching online (iTunes · MusicBrainz)",
                "phase_done":  0,
                "phase_total": online_total,
            })
            print(f"[artwork] Phase 2: searching online for {online_total} tracks…")

            online_found = 0
            for idx, track in enumerate(needs_online):
                if _batch_should_stop:
                    break
                tid    = track["id"]
                title  = track.get("title") or ""
                artist = track.get("artist_name") or ""

                art_found = False
                # Deezer by ISRC first — exact, free, high-res — when the
                # track carries one.
                if track.get("isrc"):
                    path = fetch_deezer_isrc(track["isrc"], tid)
                    if path:
                        _update_db(tid, path, "deezer")
                        online_found += 1
                        art_found = True
                        print(f"  [artwork] {tid} ({artist} — {title}) ← deezer (isrc)")
                if not art_found and (title or artist):
                    # Fallback chain. Each call is internally rate-limited
                    # where required (MB at 1 req/sec, Discogs at ~57/min).
                    # iTunes and Spotify are lighter.
                    for source_name, fn in (
                        ("itunes",      fetch_itunes),
                        ("musicbrainz", fetch_musicbrainz),
                        ("discogs",     fetch_discogs),
                    ):
                        path = fn(title, artist, tid)
                        if path:
                            _update_db(tid, path, source_name)
                            online_found += 1
                            art_found = True
                            print(f"  [artwork] {tid} ({artist} — {title}) ← {source_name}")
                            break
                        # Brief breath between calls inside one track so a
                        # heavy source doesn't pile up on the next.
                        time.sleep(0.3)

                # Mark as attempted whether or not we found anything
                if not art_found:
                    _mark_not_found(tid)

                total_done += 1
                _batch_progress["phase_done"]  = idx + 1
                _batch_progress["found_count"] = embedded_found + online_found
                _batch_progress["total_done"]  = total_done

                # Brief pause between tracks (iTunes is lenient; MB needs ~1 req/sec)
                time.sleep(0.5)

            print(
                f"[artwork] Phase 2 done — {online_found} found online, "
                f"{online_total - online_found} not found (marked 'not_found')"
            )

    finally:
        _batch_running = False
        _batch_progress["running"]     = False
        _batch_progress["phase_label"] = "Complete"
        found = _batch_progress["found_count"]
        done  = _batch_progress["total_done"]
        print(f"[artwork] batch complete — {found} covers fetched, {done} tracks processed")
