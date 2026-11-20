"""Genre suggestion engine — multi-source, free APIs, no AI.

For a given track, pulls candidate genres from:
  - Discogs     (styles + genres on release search)   — DJ-grade sub-genres
  - MusicBrainz (recording + artist tags / genres)    — granular, community
  - Deezer      (track + album genre)                 — broad
  - iTunes      (primaryGenreName from search)        — coarse
  - Last.fm     (top tags — optional, needs API key)  — useful but noisy

Each source returns a list of (name, source, weight). The orchestrator
dedupes by normalised name and returns a ranked list with source
attribution so the UI shows where each suggestion came from.

No AI. All sources free; only Discogs (optional token) and Last.fm
(optional key) need credentials. ISRC bridge where available, artist+title
fallback otherwise.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "MusicRoom/1.0 (genre suggestion; https://github.com/local)"

# Source weights — higher = more trusted, mainly for sub-genre granularity.
SOURCE_WEIGHTS = {
    'discogs':     1.00,   # styles like "Deep House", "Italo Disco" — DJ gold
    'musicbrainz': 0.85,   # community-curated, often granular
    'lastfm':      0.65,   # noisy but catches real-world genre language
    'deezer':      0.55,   # broad
    'itunes':      0.40,   # broadest, primaryGenreName only
}

# Short codes for UI badges
SOURCE_CODES = {
    'discogs':     'D',
    'musicbrainz': 'MB',
    'lastfm':      'L',
    'deezer':      'Dz',
    'itunes':      'iT',
}

# ── Normalisation + filtering ─────────────────────────────────────────────

_NORM_PUNCT = re.compile(r'[-_/]+')
_NORM_SPACE = re.compile(r'\s+')

def _norm_genre(name: str) -> str:
    """Normalise a genre name for dedup: lowercase, hyphen→space, &→and,
    collapse whitespace."""
    if not name:
        return ''
    n = name.strip().lower()
    n = n.replace(' & ', ' and ').replace('&', ' and ')
    n = _NORM_PUNCT.sub(' ', n)
    n = _NORM_SPACE.sub(' ', n).strip()
    return n


# Lower-cased exact matches to drop (vibes / meta / country / decade tags)
_NON_GENRE = {
    'seen live', 'favourite', 'favourites', 'favorite', 'favorites',
    'love', 'loved', 'awesome', 'good', 'great', 'amazing', 'beautiful',
    'sexy', 'cool', 'epic', 'best', 'chillout',  # chillout is borderline; keep "chill" via fuzzy
    'female vocalist', 'female vocalists', 'male vocalist', 'male vocalists',
    'female vocals', 'male vocals', 'vocals', 'vocal', 'instrumental',
    'spotify', 'last.fm', 'lastfm', 'soundcloud',
    'all', 'mine', 'my own', 'my favourites',
    'classic', 'classics', 'oldies',
}
_NON_GENRE_PREFIXES = ('best of', 'top ', 'my ')
_NON_GENRE_RE = re.compile(
    r'^(19|20)\d0s$'                # decades: 1980s, 2010s
    r'|^\d{4}$'                     # specific years
    r'|^[a-z]{2,3}$'                # 2-3 letter country codes (en, usa, etc.)
)


def _is_genreish(name: str) -> bool:
    n = (name or '').strip().lower()
    if not n or len(n) > 40:
        return False
    if n in _NON_GENRE:
        return False
    if any(n.startswith(p) for p in _NON_GENRE_PREFIXES):
        return False
    if _NON_GENRE_RE.match(n):
        return False
    return True


# ── HTTP helper ──────────────────────────────────────────────────────────

def _get_json(url: str, headers: dict | None = None, timeout: int = 12):
    hdrs = {'User-Agent': USER_AGENT}
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return None
    except Exception:
        return None


# ── Per-host rate gates (conservative) ───────────────────────────────────

_MB_LOCK = threading.Lock(); _MB_LAST = [0.0]; _MB_INTERVAL = 1.05
_DC_LOCK = threading.Lock(); _DC_LAST = [0.0]; _DC_INTERVAL = 0.60
_DZ_LOCK = threading.Lock(); _DZ_LAST = [0.0]; _DZ_INTERVAL = 0.40
_IT_LOCK = threading.Lock(); _IT_LAST = [0.0]; _IT_INTERVAL = 0.30
_LF_LOCK = threading.Lock(); _LF_LAST = [0.0]; _LF_INTERVAL = 0.25


def _gate(lock, last, interval):
    with lock:
        wait = interval - (time.time() - last[0])
        if wait > 0:
            time.sleep(wait)
        last[0] = time.time()


# ── Discogs ──────────────────────────────────────────────────────────────

def discogs_genres(artist: str, title: str, token: str | None, isrc: str | None = None):
    """Search Discogs; pull `style` (granular: Deep House, Italo Disco) and
    `genre` (broad: Electronic, Hip Hop) from the top few release/master
    matches. Styles weight higher than broad genres.

    Discogs has no public ISRC search field — `barcode` on their API is the
    physical-release UPC, not an ISRC — so we just go straight to artist +
    track. (`isrc` is accepted for signature symmetry with the other source
    functions and ignored here.)"""
    if not token or not (artist and title):
        return []
    params = {
        'token':    token,
        'per_page': 5,
        'type':     'release',
        'artist':   artist,
        'track':    title,
    }
    _gate(_DC_LOCK, _DC_LAST, _DC_INTERVAL)
    url = 'https://api.discogs.com/database/search?' + urllib.parse.urlencode(params)
    data = _get_json(url, headers={'Authorization': f'Discogs token={token}'})
    if not data:
        return []
    out: list[tuple[str, str, float]] = []
    for res in (data.get('results') or [])[:3]:
        for s in (res.get('style') or []):
            out.append((s, 'discogs', 1.00))
        for g in (res.get('genre') or []):
            out.append((g, 'discogs', 0.65))
    return out


# ── MusicBrainz ──────────────────────────────────────────────────────────

def _mb_get(path: str):
    _gate(_MB_LOCK, _MB_LAST, _MB_INTERVAL)
    return _get_json('https://musicbrainz.org/ws/2' + path + ('&' if '?' in path else '?') + 'fmt=json')


def musicbrainz_genres(artist: str, title: str, isrc: str | None = None):
    """ISRC bridge → recording.tags + genres + artist tags. Falls back to
    artist+title recording search."""
    out: list[tuple[str, str, float]] = []

    recording_mbid = None
    artist_mbid = None

    if isrc:
        d = _mb_get(f'/isrc/{urllib.parse.quote(isrc)}?inc=recordings')
        recs = (d or {}).get('recordings') or []
        if recs:
            recording_mbid = recs[0].get('id')

    if not recording_mbid and artist and title:
        q = f'artist:"{artist}" AND recording:"{title}"'
        d = _mb_get('/recording?query=' + urllib.parse.quote(q) + '&limit=1')
        recs = (d or {}).get('recordings') or []
        if recs:
            recording_mbid = recs[0].get('id')

    if not recording_mbid:
        return out

    # Pull tags + genres + artist link in one call
    d = _mb_get(f'/recording/{recording_mbid}?inc=tags+genres+artist-credits')
    if not d:
        return out

    # Recording-level genres are curated; weight them highest of MB sources.
    for g in (d.get('genres') or []):
        n = g.get('name')
        if n:
            count = max(1, int(g.get('count') or 1))
            out.append((n, 'musicbrainz', min(0.95, 0.6 + 0.08 * count)))
    for t in (d.get('tags') or []):
        n = t.get('name')
        if n:
            count = max(1, int(t.get('count') or 1))
            out.append((n, 'musicbrainz', min(0.85, 0.5 + 0.07 * count)))

    # Artist-level genres add useful "this artist generally is X" signal.
    ac = (d.get('artist-credit') or [])
    if ac and isinstance(ac[0], dict):
        a = ac[0].get('artist') or {}
        artist_mbid = a.get('id')
    if artist_mbid:
        d = _mb_get(f'/artist/{artist_mbid}?inc=tags+genres')
        if d:
            for g in (d.get('genres') or []):
                n = g.get('name')
                if n:
                    count = max(1, int(g.get('count') or 1))
                    out.append((n, 'musicbrainz', min(0.80, 0.45 + 0.06 * count)))
            for t in (d.get('tags') or []):
                n = t.get('name')
                if n:
                    count = max(1, int(t.get('count') or 1))
                    out.append((n, 'musicbrainz', min(0.70, 0.35 + 0.05 * count)))
    return out


# ── Deezer ───────────────────────────────────────────────────────────────

def deezer_genres(artist: str, title: str, isrc: str | None = None):
    """Deezer: track → album → album.genres. ISRC fast path, then search."""
    track = None
    if isrc:
        _gate(_DZ_LOCK, _DZ_LAST, _DZ_INTERVAL)
        track = _get_json(f'https://api.deezer.com/track/isrc:{urllib.parse.quote(isrc)}')
    if not track and artist and title:
        _gate(_DZ_LOCK, _DZ_LAST, _DZ_INTERVAL)
        q = urllib.parse.quote(f'artist:"{artist}" track:"{title}"')
        res = _get_json(f'https://api.deezer.com/search?q={q}&limit=1')
        items = (res or {}).get('data') or []
        if items:
            track = items[0]
    if not track:
        return []
    album_id = (track.get('album') or {}).get('id')
    if not album_id:
        return []
    _gate(_DZ_LOCK, _DZ_LAST, _DZ_INTERVAL)
    album = _get_json(f'https://api.deezer.com/album/{album_id}')
    if not album:
        return []
    genres = ((album.get('genres') or {}).get('data')) or []
    return [(g.get('name'), 'deezer', 0.55)
            for g in genres if g.get('name')]


# ── iTunes ───────────────────────────────────────────────────────────────

def itunes_genre(artist: str, title: str):
    if not (artist and title):
        return []
    _gate(_IT_LOCK, _IT_LAST, _IT_INTERVAL)
    q = urllib.parse.quote(f'{artist} {title}')
    data = _get_json(f'https://itunes.apple.com/search?term={q}&entity=song&limit=3')
    if not data:
        return []
    out = []
    for r in (data.get('results') or []):
        g = r.get('primaryGenreName')
        if g:
            out.append((g, 'itunes', 0.40))
    return out


# ── Last.fm (optional) ───────────────────────────────────────────────────

def lastfm_tags(artist: str, title: str, api_key: str | None):
    if not (api_key and artist and title):
        return []
    _gate(_LF_LOCK, _LF_LAST, _LF_INTERVAL)
    qs = urllib.parse.urlencode({
        'method': 'track.gettoptags',
        'artist': artist,
        'track':  title,
        'api_key': api_key,
        'format': 'json',
    })
    data = _get_json(f'https://ws.audioscrobbler.com/2.0/?{qs}')
    if not data:
        return []
    tags = (data.get('toptags') or {}).get('tag') or []
    out = []
    for t in tags[:15]:
        n = t.get('name') or ''
        c = int(t.get('count') or 0)
        if not n:
            continue
        # Weight scales with tag popularity (0..100). Cap at 0.65.
        w = min(0.65, 0.20 + (c / 100.0) * 0.45)
        out.append((n, 'lastfm', w))
    return out


# ── Orchestrator ─────────────────────────────────────────────────────────

def suggest_genres(artist: str, title: str, *,
                   isrc: str | None = None,
                   discogs_token: str | None = None,
                   lastfm_key: str | None = None,
                   limit: int = 12) -> list[dict]:
    """Returns a ranked list of genre candidates.

    Each item: {
        name:    'Deep House',    # original casing from the highest-weight source
        sources: ['discogs', 'lastfm'],
        score:   1.62,            # sum of per-source weights
    }
    """
    candidates: list[tuple[str, str, float]] = []
    # Run sources sequentially — the per-host gates serialise anyway.
    for fn, args in (
        (discogs_genres,     (artist, title, discogs_token, isrc)),
        (musicbrainz_genres, (artist, title, isrc)),
        (deezer_genres,      (artist, title, isrc)),
        (itunes_genre,       (artist, title)),
        (lastfm_tags,        (artist, title, lastfm_key)),
    ):
        try:
            candidates.extend(fn(*args))
        except Exception:
            # Sources can fail (network, schema change, etc.) — keep going.
            continue

    # Dedupe by normalised name. Keep the prettiest original casing — prefer
    # the casing from the highest-weight source.
    bucket: dict[str, dict] = {}
    for name, source, weight in candidates:
        if not _is_genreish(name):
            continue
        key = _norm_genre(name)
        if not key:
            continue
        slot = bucket.setdefault(key, {
            'name': name,
            'sources': [],
            'score': 0.0,
            '_top_weight': 0.0,
        })
        if source not in slot['sources']:
            slot['sources'].append(source)
        slot['score'] += weight
        if weight > slot['_top_weight']:
            slot['name'] = name
            slot['_top_weight'] = weight

    out = sorted(bucket.values(), key=lambda x: x['score'], reverse=True)[:limit]
    # Strip the internal field before returning.
    for x in out:
        x.pop('_top_weight', None)
    return out
