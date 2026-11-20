"""Sample-origin lookup via MusicBrainz recording↔recording "samples"
relationships — free, no key (rate-gated through genre_suggest._mb_get, ~1 req/s).

Finds, for a recording:
  - what it SAMPLES (the originals), and
  - what it is SAMPLED IN.

No timestamps: MusicBrainz doesn't store the moment a sample comes from (that's
WhoSampled, whose API isn't free). Coverage is community-contributed — strong for
well-documented samples, patchy for obscure ones. The app links each result to a
LOCAL track when the user owns it (so they can play the original), else to
MusicBrainz.
"""
import urllib.parse
from genre_suggest import _mb_get


def _artist_of(rec: dict):
    """Join a MusicBrainz artist-credit into a display string, or None."""
    ac = rec.get("artist-credit") or []
    names = []
    for a in ac:
        if isinstance(a, dict):
            names.append(a.get("name") or (a.get("artist") or {}).get("name") or "")
        elif isinstance(a, str):
            names.append(a)
    s = "".join(n for n in names if n).strip()
    return s or None


def _parse_sample_relations(relations):
    """Pure parser (testable without the network). Returns (samples, sampled_in)
    where each item is {mbid, title, artist, partial}.
    direction 'forward' → this recording samples the target (the original);
    direction 'backward' → this recording is sampled in the target."""
    samples, sampled_in = [], []
    for rel in (relations or []):
        if "sample" not in (rel.get("type") or "").lower():
            continue
        rec = rel.get("recording") or {}
        if not rec.get("id"):
            continue
        item = {
            "mbid":    rec.get("id"),
            "title":   rec.get("title"),
            "artist":  _artist_of(rec),
            "partial": "partial" in (rel.get("attributes") or []),
        }
        (sampled_in if rel.get("direction") == "backward" else samples).append(item)
    return samples, sampled_in


def _resolve_recording_mbid(artist, title, isrc):
    if isrc:
        d = _mb_get(f"/isrc/{urllib.parse.quote(isrc)}?inc=recordings")
        recs = (d or {}).get("recordings") or []
        if recs:
            return recs[0].get("id")
    if artist and title:
        q = f'artist:"{artist}" AND recording:"{title}"'
        d = _mb_get("/recording?query=" + urllib.parse.quote(q) + "&limit=1")
        recs = (d or {}).get("recordings") or []
        if recs:
            return recs[0].get("id")
    return None


def find_samples(artist, title, isrc=None):
    """{'mbid', 'samples': [...], 'sampled_in': [...]}. Never raises."""
    try:
        mbid = _resolve_recording_mbid(artist, title, isrc)
        if not mbid:
            return {"mbid": None, "samples": [], "sampled_in": []}
        d = _mb_get(f"/recording/{mbid}?inc=recording-rels+artist-credits")
        samples, sampled_in = _parse_sample_relations((d or {}).get("relations"))
        return {"mbid": mbid, "samples": samples, "sampled_in": sampled_in}
    except Exception:
        return {"mbid": None, "samples": [], "sampled_in": []}
