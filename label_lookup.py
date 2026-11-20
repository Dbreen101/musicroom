"""
label_lookup.py — find a track's record label by querying MusicBrainz
and (optionally) Discogs.

Order:
  1. MusicBrainz — free, no auth needed. 1 req/sec rate limit; we
     enforce it ourselves so callers don't have to. Strong on commercial
     releases that made it into MB.
  2. Discogs — requires a user-supplied token (free at
     discogs.com/settings/developers). Best for electronic / dance /
     vinyl-era releases. Skipped silently if no token.

Bandcamp self-releases generally aren't in either database — those are
better handled via the "self released" toggle in the track panel.

Returns:
    {"label": "...", "source": "musicbrainz" | "discogs"}        — found
    {"error": "...", "source": "musicbrainz" | "discogs" | None}  — failure
    {"label": None, "source": None}                               — not found
"""

import json
import re
import threading
import time
import urllib.parse
import urllib.request


USER_AGENT = "MusicRoom/1.0 (personal DJ library tool)"

# Rate-limit gates. MusicBrainz documents a hard 1 req/sec ceiling;
# Discogs allows 60/min on authenticated requests.
_mb_lock        = threading.Lock()
_mb_last_call   = [0.0]
_disc_lock      = threading.Lock()
_disc_last_call = [0.0]
MB_MIN_INTERVAL   = 1.05   # seconds — bit of safety on top of 1.0
DISC_MIN_INTERVAL = 1.05   # ~57/min


def _http_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8") or "{}"
            return r.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") or "{}"
        try:    payload = json.loads(body)
        except Exception: payload = {"raw": body}
        return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


# ─── MusicBrainz ────────────────────────────────────────────────────

def _mb_query(artist, title):
    """Build a MB Lucene query that prefers exact-ish recording matches."""
    # Strip parenthetical / bracketed suffixes — they bias the search.
    def clean(s):
        s = re.sub(r"\(.*?\)|\[.*?\]", " ", s or "")
        return re.sub(r"\s+", " ", s).strip()
    a = clean(artist).replace('"', '\\"')
    t = clean(title).replace('"', '\\"')
    return f'artist:"{a}" AND recording:"{t}"'


def _first_label_from_recordings(recordings):
    """Each recording can list releases; each release lists label-info.
    Return the first non-empty label name, or None."""
    for rec in (recordings or []):
        for rel in (rec.get("releases") or []):
            for li in (rel.get("label-info") or []):
                name = ((li.get("label") or {}).get("name") or "").strip()
                if name and name.lower() != "[no label]":
                    return name
    return None


def _mb_wait():
    with _mb_lock:
        wait = MB_MIN_INTERVAL - (time.time() - _mb_last_call[0])
        if wait > 0: time.sleep(wait)
        _mb_last_call[0] = time.time()


def lookup_musicbrainz_isrc(isrc):
    """Exact label lookup by ISRC. The ISRC identifies the recording
    precisely, so this is far more reliable than the fuzzy name search.

    Two steps (MB's isrc resource can't include label-info directly):
      1. recording search by isrc → a release id
      2. release lookup with inc=labels → the label name
    Returns {label, source:'musicbrainz'} / {label:None} / {error}."""
    code = re.sub(r"[^A-Za-z0-9]", "", isrc or "").upper()
    if len(code) != 12:
        return {"label": None, "source": None}

    # Step 1 — ISRC → release id.
    _mb_wait()
    url1 = ("https://musicbrainz.org/ws/2/recording"
            f"?query=isrc:{code}&fmt=json&limit=5")
    status, data = _http_json(url1, headers={"User-Agent": USER_AGENT})
    if status != 200:
        return {"error": f"MusicBrainz HTTP {status}", "source": "musicbrainz"}
    rid = None
    for rec in (data.get("recordings") or []):
        for rel in (rec.get("releases") or []):
            if rel.get("id"):
                rid = rel["id"]
                break
        if rid:
            break
    if not rid:
        return {"label": None, "source": None}   # ISRC unknown to MB

    # Step 2 — release → label-info.
    _mb_wait()
    url2 = f"https://musicbrainz.org/ws/2/release/{rid}?fmt=json&inc=labels"
    status, rel = _http_json(url2, headers={"User-Agent": USER_AGENT})
    if status != 200:
        return {"error": f"MusicBrainz HTTP {status}", "source": "musicbrainz"}
    for li in (rel.get("label-info") or []):
        name = ((li.get("label") or {}).get("name") or "").strip()
        if name and name.lower() != "[no label]":
            return {"label": name, "source": "musicbrainz"}
    return {"label": None, "source": None}


def lookup_musicbrainz(artist, title):
    if not artist or not title:
        return {"label": None, "source": None}
    _mb_wait()
    q   = _mb_query(artist, title)
    url = ("https://musicbrainz.org/ws/2/recording"
           f"?query={urllib.parse.quote(q)}&fmt=json&limit=5&inc=releases+labels")
    status, data = _http_json(url, headers={"User-Agent": USER_AGENT})
    if status != 200:
        return {"error": f"MusicBrainz HTTP {status}", "source": "musicbrainz"}
    name = _first_label_from_recordings(data.get("recordings"))
    if name:
        return {"label": name, "source": "musicbrainz"}
    return {"label": None, "source": None}


# ─── Discogs ────────────────────────────────────────────────────────

def lookup_discogs(artist, title, token):
    if not (artist and title and token):
        return {"label": None, "source": None}
    with _disc_lock:
        wait = DISC_MIN_INTERVAL - (time.time() - _disc_last_call[0])
        if wait > 0: time.sleep(wait)
        _disc_last_call[0] = time.time()
    qs = urllib.parse.urlencode({
        "artist": artist,
        "track":  title,
        "type":   "release",
        "token":  token,
        "per_page": 5,
    })
    status, data = _http_json(
        f"https://api.discogs.com/database/search?{qs}",
        headers={"User-Agent": USER_AGENT,
                 "Authorization": f"Discogs token={token}"},
    )
    if status == 401:
        return {"error": "Discogs auth failed — check token", "source": "discogs"}
    if status != 200:
        return {"error": f"Discogs HTTP {status}", "source": "discogs"}
    for r in (data.get("results") or []):
        labels = r.get("label") or []
        if isinstance(labels, list) and labels:
            name = (labels[0] or "").strip()
            if name and name.lower() != "not on label":
                return {"label": name, "source": "discogs"}
    return {"label": None, "source": None}


# ─── orchestrator ───────────────────────────────────────────────────

def _deezer_label(isrc=None, artist=None, title=None):
    """Thin wrapper around dsp_lookup's Deezer label lookup. Deezer carries
    labels for a lot of modern/electronic releases MusicBrainz lacks, and
    we already hit Deezer for the DSP check, so it's a free, reliable
    source. Returns {label, source:'deezer'} or {label:None}."""
    try:
        from dsp_lookup import deezer_label
        lbl = deezer_label(isrc=isrc, artist=artist, title=title)
    except Exception:
        lbl = None
    return {"label": lbl, "source": "deezer"} if lbl else {"label": None, "source": None}


def lookup_label(artist, title, discogs_token=None, isrc=None):
    """Find a record label. Order favours exact (ISRC-keyed) sources first,
    then fuzzy ones:
      1. MusicBrainz by ISRC   (exact, canonical)
      2. Deezer by ISRC        (exact album label — strong for electronic)
      3. MusicBrainz fuzzy     (artist + title)
      4. Deezer fuzzy          (artist + title)
      5. Discogs               (if a token is set)
    Returns the first hit or {label: None}."""
    # ── exact, ISRC-based — no fuzzy risk ──
    if isrc:
        mbi = lookup_musicbrainz_isrc(isrc)
        if mbi.get("label"):
            return mbi
        dzi = _deezer_label(isrc=isrc)
        if dzi.get("label"):
            return dzi

    a = (artist or "").strip()
    t = (title  or "").strip()
    if not a or not t:
        return {"label": None, "source": None, "skipped": True,
                "reason": "no artist/title"}

    # ── fuzzy fallbacks ──
    mb = lookup_musicbrainz(a, t)
    if mb.get("label"):
        return mb
    dz = _deezer_label(artist=a, title=t)
    if dz.get("label"):
        return dz
    if discogs_token and (discogs_token or "").strip():
        dc = lookup_discogs(a, t, discogs_token.strip())
        if dc.get("label"):
            return dc
        # Surface a Discogs auth error if everything else came up empty —
        # useful when the user just pasted the wrong token.
        if dc.get("error"):
            return dc
    return {"label": None, "source": None}
