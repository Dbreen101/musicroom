"""
dsp_lookup.py — "is this track on a DSP?" without Spotify.

Spotify's post-Feb-2026 dev-mode rate limits made per-track /search
unusable for the "only here" check. This module answers the same
question against two free, no-auth, far-less-throttled catalogues:

  • Deezer  — public API, no key, generous limits. Crucially it can be
              queried by ISRC (api.deezer.com/track/isrc:<CODE>), which is
              an *exact* recording match — zero fuzzy-matching risk.
  • iTunes  — Apple's Search API (same one the artwork fetcher uses).
              No ISRC param, so fuzzy-only, used as a second opinion.

A positive match on either is a real match (no false positives). The
only failure mode is a false "only here" (it's on a DSP but both searches
missed it). That's acceptable here — the user knows the limitation.

Matching is deliberately TIGHT and cheap: plain string normalisation,
no edit-distance. The query is cleaned for recall ("(Original Mix)",
"feat." stripped); the confirmation requires a normalised title equality
plus an artist-token overlap so two different songs sharing a title
don't trigger a hit.

Nothing here touches the Spotify API or the database — callers handle
persistence and the free "already on Apple Music" shortcut.
"""

import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

from text_clean import strip_mix_suffix


USER_AGENT = "MusicRoom/1.0 (personal DJ library tool)"


class TransportError(Exception):
    """A network/HTTP failure — inconclusive, not a real 'not found'."""


class RateLimited(TransportError):
    """A 429/403 throttle response — back off this host for a while."""


# ─── ISRC extraction + validation ───────────────────────────────────

# ISRC = 2-letter country + 3-char registrant + 2-digit year + 5-digit
# designation. We accept it with or without the conventional dashes.
_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")


def normalise_isrc(raw):
    """Uppercase, strip separators, validate. Returns a clean 12-char
    ISRC or None if it doesn't look like one."""
    if not raw:
        return None
    s = re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()
    return s if _ISRC_RE.match(s) else None


def extract_isrc(file_path):
    """Read an embedded ISRC from an audio file's tags. Covers ID3
    (TSRC), Vorbis/FLAC (isrc), and MP4 (----:com.apple.iTunes:ISRC).
    Returns a normalised ISRC or None. Never raises."""
    try:
        from mutagen import File as MutagenFile
        m = MutagenFile(file_path)
    except Exception:
        return None
    if m is None:
        return None
    tags = getattr(m, "tags", None)
    if not tags:
        return None

    cand = None
    # ID3 (mp3 / aiff)
    try:
        if "TSRC" in tags:
            frame = tags["TSRC"]
            cand = str(frame.text[0]) if hasattr(frame, "text") else str(frame)
    except Exception:
        pass
    # Vorbis comments (flac / ogg) — mutagen lowercases keys
    if not cand:
        for k in ("isrc", "ISRC", "Isrc"):
            try:
                if k in tags:
                    v = tags[k]
                    cand = str(v[0] if isinstance(v, (list, tuple)) else v)
                    break
            except Exception:
                pass
    # MP4 / M4A freeform atom
    if not cand:
        for k in ("----:com.apple.iTunes:ISRC", "----:com.apple.iTunes:isrc"):
            try:
                if k in tags:
                    v = tags[k][0]
                    cand = v.decode("utf-8", "ignore") if isinstance(v, bytes) else str(v)
                    break
            except Exception:
                pass
    return normalise_isrc(cand)


# ─── matching ───────────────────────────────────────────────────────

_FEAT_RE = re.compile(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)


def _norm(s):
    """Tight match key: drop accents, case, 'Original Mix', feat-credits,
    and punctuation; collapse whitespace. Keeps remix/edit words (they
    distinguish recordings) so 'Track (X Remix)' won't match 'Track'."""
    if not s:
        return ""
    out = unicodedata.normalize("NFKD", str(s))
    out = "".join(c for c in out if not unicodedata.combining(c))
    out = out.lower()
    out = strip_mix_suffix(out) or out
    out = _FEAT_RE.sub("", out)
    out = re.sub(r"[^\w\s]", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _artist_overlap(a, b):
    """True if either artist string is contained in the other after
    normalisation — handles 'A, B' vs 'A' and featuring credits."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def _is_match(our_artist, our_title, cand_artist, cand_title):
    nt, ct = _norm(our_title), _norm(cand_title)
    if not nt or not ct or nt != ct:
        return False
    return _artist_overlap(our_artist, cand_artist)


# ── the "probable" tier ──────────────────────────────────────────────
# The exact matcher above stays the source of truth ("a positive match is
# a real match"). But user metadata isn't always exact, and a near-miss
# used to fall straight to "only here". Now a close-but-not-exact
# candidate comes back as PROBABLE — the user confirms or rejects it on
# the track panel. Cheap difflib ratio, no new dependencies.

def _similar(a, b):
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    import difflib
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _near_score(our_artist, our_title, cand_artist, cand_title):
    """0..1 likelihood that cand is the same recording. Only consulted
    AFTER exact matching failed. 0 = not worth showing the user."""
    ts = _similar(our_title, cand_title)
    if ts < 0.72:
        return 0.0
    if _artist_overlap(our_artist, cand_artist):
        return 0.55 + 0.45 * ts                  # right artist, near title
    asim = _similar(our_artist, cand_artist)
    if asim < 0.55:
        return 0.0
    return 0.40 * asim + 0.60 * ts               # both fuzzy → demand more


def _scan_candidates(artist, title, cands):
    """cands = [(cand_artist, cand_title, raw)] → (exact_raw|None, best_near|None).
    best_near = {"artist","title","score"} — the user-confirm tier."""
    best = None
    for ca, ct, raw in cands:
        if _is_match(artist, title, ca, ct):
            return raw, None
        s = _near_score(artist, title, ca, ct)
        if s > 0 and (best is None or s > best["score"]):
            best = {"artist": ca or "", "title": ct or "", "score": round(s, 2)}
    return None, best


# ─── HTTP + per-host rate gates ─────────────────────────────────────

# Per-host pacing + backoff. These free APIs have undocumented anti-abuse
# limits that return 403/429 under sustained batch load; when that happens
# we park the host for a cooldown so the batch paces itself instead of
# hammering (which only prolongs the block). State is module-shared so all
# callers + the artwork fetcher serialise through the same gate.
_dz_lock = threading.Lock()
_dz_last = [0.0]
_dz_block = [0.0]            # wall-clock; don't call Deezer again until then
_DZ_MIN_INTERVAL = 0.4      # ~2.5/s sustained (Deezer tolerates ~50/5s but
                            # bursts get blocked — stay well under)

_it_lock = threading.Lock()
_it_last = [0.0]
_it_block = [0.0]
_IT_MIN_INTERVAL = 3.0      # iTunes Search throttles hard (~20/min) — slow,
                            # but it's only the fallback after Deezer

_mb_lock = threading.Lock()
_mb_last = [0.0]
_mb_block = [0.0]
_MB_MIN_INTERVAL = 1.1      # MusicBrainz documents a hard 1 req/sec ceiling

_BLOCK_COOLDOWN_S = 60      # how long to park a host after a 403/429


def _gate(lock, last, interval, block):
    """Wait until the host is allowed: the larger of the per-call interval
    and any active backoff window."""
    with lock:
        now = time.time()
        wait = max(interval - (now - last[0]), block[0] - now)
        if wait > 0:
            time.sleep(wait)
        last[0] = time.time()


def _get_json(url, block=None):
    """GET + parse JSON. Raises RateLimited on 403/429 (and parks the host
    for a cooldown) or TransportError on any other network failure, so the
    caller leaves a track 'untested' rather than mislabelling it."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            if block is not None:
                block[0] = max(block[0], time.time() + _BLOCK_COOLDOWN_S)
            raise RateLimited(f"HTTP {e.code} (rate-limited)")
        raise TransportError(f"HTTP {e.code}")
    except Exception as e:
        raise TransportError(str(e))


# ─── Deezer ─────────────────────────────────────────────────────────

def deezer_track_by_isrc(isrc):
    """Exact recording lookup by ISRC. Returns the Deezer track dict
    (includes album.cover_xl etc.) or None. Network errors → None
    (inconclusive — caller falls through to fuzzy search)."""
    code = normalise_isrc(isrc)
    if not code:
        return None
    _gate(_dz_lock, _dz_last, _DZ_MIN_INTERVAL, _dz_block)
    try:
        data = _get_json(f"https://api.deezer.com/track/isrc:{code}", _dz_block)
    except TransportError:
        return None
    if isinstance(data, dict) and data.get("id") and not data.get("error"):
        return data
    return None


def deezer_search_candidates(artist, title):
    """Raw Deezer search → [(cand_artist, cand_title, raw_dict)]. Raises
    TransportError on network failure."""
    a, t = (artist or "").strip(), strip_mix_suffix((title or "").strip()) or ""
    if not a or not t:
        return []
    _gate(_dz_lock, _dz_last, _DZ_MIN_INTERVAL, _dz_block)
    q = urllib.parse.quote(f'artist:"{a}" track:"{t}"')
    data = _get_json(f"https://api.deezer.com/search?q={q}&limit=5", _dz_block)
    return [((item.get("artist") or {}).get("name"), item.get("title"), item)
            for item in (data.get("data") or [])]


def deezer_search_present(artist, title):
    """Fuzzy presence check on Deezer. Returns a matched track dict, or
    None for a clean no-match. Raises TransportError on network failure."""
    for cand_artist, cand_title, item in deezer_search_candidates(artist, title):
        if _is_match(artist, title, cand_artist, cand_title):
            return item
    return None


def deezer_track_by_id(track_id):
    """Fetch a full Deezer track (which always carries `isrc`). Returns
    the dict or None. Network errors → None."""
    if not track_id:
        return None
    _gate(_dz_lock, _dz_last, _DZ_MIN_INTERVAL, _dz_block)
    try:
        data = _get_json(f"https://api.deezer.com/track/{track_id}", _dz_block)
    except TransportError:
        return None
    if isinstance(data, dict) and data.get("id") and not data.get("error"):
        return data
    return None


def deezer_album_label(album_id):
    """Read a Deezer album's record label. Returns the label string or None."""
    if not album_id:
        return None
    _gate(_dz_lock, _dz_last, _DZ_MIN_INTERVAL, _dz_block)
    try:
        data = _get_json(f"https://api.deezer.com/album/{album_id}", _dz_block)
    except TransportError:
        return None
    if isinstance(data, dict):
        lbl = (data.get("label") or "").strip()
        return lbl or None
    return None


def deezer_label(isrc=None, artist=None, title=None):
    """Best-effort record label via Deezer: find the recording (by ISRC if
    we have one, else a tight fuzzy search), then read its album's label.
    Deezer carries labels for a lot of modern / electronic releases that
    never made it into MusicBrainz. Returns a label string or None."""
    tr = None
    if isrc:
        tr = deezer_track_by_isrc(isrc)
    if not tr and artist and title:
        try:
            tr = deezer_search_present(artist, title)
        except TransportError:
            tr = None
    if not tr:
        return None
    return deezer_album_label((tr.get("album") or {}).get("id"))


# ─── iTunes ─────────────────────────────────────────────────────────

def itunes_search_candidates(artist, title):
    """Raw iTunes search → [(cand_artist, cand_title, raw_dict)]. Raises
    TransportError on network failure."""
    a, t = (artist or "").strip(), strip_mix_suffix((title or "").strip()) or ""
    if not a or not t:
        return []
    _gate(_it_lock, _it_last, _IT_MIN_INTERVAL, _it_block)
    qs = urllib.parse.urlencode({"term": f"{a} {t}", "entity": "song", "limit": 5})
    data = _get_json(f"https://itunes.apple.com/search?{qs}", _it_block)
    return [(item.get("artistName"), item.get("trackName"), item)
            for item in (data.get("results") or [])]


def itunes_search_present(artist, title):
    """Fuzzy presence check on Apple's iTunes Search API. Returns a
    matched result dict, or None for a clean no-match. Raises
    TransportError on network failure."""
    for cand_artist, cand_title, item in itunes_search_candidates(artist, title):
        if _is_match(artist, title, cand_artist, cand_title):
            return item
    return None


# ─── Apple (iTunes) record label, via the album copyright field ─────

def _label_from_copyright(c):
    """Pull a label name out of an iTunes copyright string, e.g.
    '℗ 2024 Dreams On Wax' → 'Dreams On Wax'."""
    if not c:
        return None
    s = re.sub(r"^[\s℗©Ⓟⓒ]*(\((?:p|c)\))?\s*", "", str(c), flags=re.I)  # drop ℗/© markers
    s = re.sub(r"^\s*(?:19|20)\d{2}\s+", "", s)                          # drop leading year
    s = re.split(r"\s+under exclusive|,\s*under|\s+/\s+|;", s, maxsplit=1, flags=re.I)[0]
    s = s.strip().strip(".,").strip()
    return s or None


def itunes_label(artist, title):
    """Best-effort record label via Apple's iTunes Search API: match the
    song, then read its album's copyright line. Two calls (gated), used
    only as a fallback. Returns a label string or None."""
    a = (artist or "").strip()
    t = strip_mix_suffix((title or "").strip()) or ""
    if not a or not t:
        return None
    _gate(_it_lock, _it_last, _IT_MIN_INTERVAL, _it_block)
    qs = urllib.parse.urlencode({"term": f"{a} {t}", "entity": "song", "limit": 5})
    try:
        data = _get_json(f"https://itunes.apple.com/search?{qs}", _it_block)
    except TransportError:
        return None
    cid = None
    for it in (data.get("results") or []):
        if _is_match(artist, title, it.get("artistName"), it.get("trackName")):
            cid = it.get("collectionId")
            break
    if not cid:
        return None
    _gate(_it_lock, _it_last, _IT_MIN_INTERVAL, _it_block)
    try:
        al = _get_json(f"https://itunes.apple.com/lookup?id={cid}&entity=album", _it_block)
    except TransportError:
        return None
    for r in (al.get("results") or []):
        lab = _label_from_copyright(r.get("copyright"))
        if lab:
            return lab
    return None


# ─── MusicBrainz ISRC (fallback ISRC source) ────────────────────────

def _mb_get(url):
    _gate(_mb_lock, _mb_last, _MB_MIN_INTERVAL, _mb_block)
    return _get_json(url, _mb_block)


def musicbrainz_isrc(artist, title):
    """Find an ISRC for a recording via MusicBrainz (it stores them for
    many recordings). Two calls (gated 1/s). Returns a normalised ISRC or
    None. Used as a fallback when the track wasn't matched on Deezer."""
    a = (artist or "").strip()
    t = (title or "").strip()
    if not a or not t:
        return None
    qa = a.replace('"', '\\"')
    qt = re.sub(r"\(.*?\)|\[.*?\]", " ", t).strip().replace('"', '\\"')
    q = urllib.parse.quote(f'artist:"{qa}" AND recording:"{qt}"')
    try:
        data = _mb_get(f"https://musicbrainz.org/ws/2/recording?query={q}&fmt=json&limit=1")
        recs = data.get("recordings") or []
        if not recs:
            return None
        rid = recs[0].get("id")
        if not rid:
            return None
        full = _mb_get(f"https://musicbrainz.org/ws/2/recording/{rid}?fmt=json&inc=isrcs")
        for code in (full.get("isrcs") or []):
            n = normalise_isrc(code)
            if n:
                return n
    except TransportError:
        return None
    return None


# ─── orchestrator ───────────────────────────────────────────────────

def check_dsp(artist, title, isrc=None):
    """Decide whether a track is on a major DSP.

    Order: ISRC-exact (Deezer) → fuzzy Deezer → fuzzy iTunes.

    Returns one of:
      {"state": "on_dsp",  "source": "isrc"|"deezer"|"itunes", "isrc": <code|None>}
      {"state": "probable", "source": "deezer"|"itunes",
       "match_artist": ..., "match_title": ..., "score": 0..1}
          ← a near-miss the USER confirms or rejects on the track panel
      {"state": "not_on_dsp"}
      {"state": "error",   "message": "..."}   ← transient; retry later
      {"state": "skipped", "reason": "no artist/title"}

    On a Deezer match the matched recording's ISRC is returned in "isrc"
    (Deezer exposes it for free) so callers can enrich the library — we
    "ask its ISRC while we're there". iTunes carries no ISRC.
    """
    norm = normalise_isrc(isrc)

    # 1. Exact match by ISRC (no fuzzy risk, no false positives).
    if norm:
        tr = deezer_track_by_isrc(norm)
        if tr:
            return {"state": "on_dsp", "source": "isrc", "isrc": norm}

    a, t = (artist or "").strip(), (title or "").strip()
    if not a or not t:
        return {"state": "skipped", "reason": "no artist/title"}

    near_best = None      # best close-but-not-exact candidate across sources

    # 2. Fuzzy Deezer — and grab the matched recording's ISRC for free.
    try:
        hit, near = _scan_candidates(artist, title, deezer_search_candidates(artist, title))
        if hit:
            found = normalise_isrc(hit.get("isrc"))
            if not found and hit.get("id"):
                # Lighter search payloads occasionally omit isrc — one
                # cheap full-track fetch fills it in.
                full = deezer_track_by_id(hit.get("id"))
                if full:
                    found = normalise_isrc(full.get("isrc"))
            return {"state": "on_dsp", "source": "deezer", "isrc": found}
        if near:
            near["source"] = "deezer"
            near_best = near
        deezer_failed = False
        deezer_err = None
    except TransportError as e:
        deezer_failed = True
        deezer_err = str(e)

    # 3. Fuzzy iTunes. Apple's free API has no ISRC, so if it matches we
    #    ask MusicBrainz for one — a targeted fallback, only for the few
    #    tracks Deezer missed.
    try:
        hit, near = _scan_candidates(artist, title, itunes_search_candidates(artist, title))
        if hit:
            return {"state": "on_dsp", "source": "itunes",
                    "isrc": musicbrainz_isrc(artist, title)}
        if near and (near_best is None or near["score"] > near_best["score"]):
            near["source"] = "itunes"
            near_best = near
    except TransportError as e:
        if deezer_failed:
            return {"state": "error", "message": deezer_err or str(e)}
        return {"state": "error", "message": str(e)}

    if deezer_failed:
        return {"state": "error", "message": deezer_err or "lookup failed"}
    if near_best:
        return {"state": "probable", "source": near_best["source"],
                "match_artist": near_best["artist"],
                "match_title": near_best["title"],
                "score": near_best["score"]}
    return {"state": "not_on_dsp"}
