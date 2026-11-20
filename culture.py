"""
culture.py — cultural / biographical enrichment from free, open data.

NO AI. NO PAID SERVICES. Everything here comes from authoritative,
structured, free sources so the facts can be trusted for cultural mapping
(no hallucinated nationalities) and the tool runs on anyone's laptop with
zero setup:

  • MusicBrainz  — artist type/gender/area/country/begin + genres; label
                   area/founding/type. Free, 1 req/sec. The bridge to…
  • Wikidata     — the deep layer: birthplace (+ coordinates + its country),
                   citizenship, gender; label inception / HQ / founder.
                   Free Action API (wbgetentities) — deliberately NOT the
                   SPARQL endpoint, which gets rate-limited during WDQS
                   outages. Linked straight from each MusicBrainz entity.
  • Wikipedia    — a short human-written summary (the article lead, not AI).

Accuracy: where a track has an ISRC we resolve the EXACT MusicBrainz
artist via the recording, instead of fuzzy-matching a name (which collides
for underground acts). The match method is recorded in `data_source`.

Discogs (a free but registered token) is an OPTIONAL supplement only — the
core works with no keys at all.
"""

import json
import re
import threading
import time
import urllib.parse
import urllib.request

USER_AGENT = "MusicRoom/1.0 (personal DJ library; cultural mapping)"


# ─── per-host rate gates (be a good citizen) ────────────────────────
def _gate(lock, last, interval):
    with lock:
        wait = interval - (time.time() - last[0])
        if wait > 0:
            time.sleep(wait)
        last[0] = time.time()


_mb_lock, _mb_last, _MB = threading.Lock(), [0.0], 1.1   # MusicBrainz: 1 req/s
_wd_lock, _wd_last, _WD = threading.Lock(), [0.0], 0.34  # Wikidata Action API
_wp_lock, _wp_last, _WP = threading.Lock(), [0.0], 0.3   # Wikipedia (lenient)


def _get(url, lock=None, last=None, interval=None):
    if lock:
        _gate(lock, last, interval)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _year(s):
    m = re.match(r"\+?\s*(\d{4})", str(s or ""))
    return int(m.group(1)) if m else None


# ─── MusicBrainz ────────────────────────────────────────────────────

def mb_artist_mbid_by_isrc(isrc):
    """Exact: ISRC → recording → first artist MBID. None if not found."""
    code = re.sub(r"[^A-Za-z0-9]", "", isrc or "").upper()
    if len(code) != 12:
        return None
    try:
        d = _get(f"https://musicbrainz.org/ws/2/recording?query=isrc:{code}&fmt=json&limit=1",
                 _mb_lock, _mb_last, _MB)
    except Exception:
        return None
    recs = d.get("recordings") or []
    if not recs:
        return None
    for ac in (recs[0].get("artist-credit") or []):
        art = ac.get("artist") or {}
        if art.get("id"):
            return art["id"]
    return None


def mb_artist_search(name):
    if not name:
        return None
    try:
        d = _get("https://musicbrainz.org/ws/2/artist?query="
                 f"{urllib.parse.quote(name)}&fmt=json&limit=1", _mb_lock, _mb_last, _MB)
    except Exception:
        return None
    a = (d.get("artists") or [None])[0]
    return a.get("id") if a else None


def mb_artist(mbid):
    try:
        d = _get(f"https://musicbrainz.org/ws/2/artist/{mbid}?fmt=json&inc=url-rels+tags+genres",
                 _mb_lock, _mb_last, _MB)
    except Exception:
        return {}
    genres = [g["name"] for g in sorted(
        (d.get("genres") or []), key=lambda x: -(x.get("count") or 0))[:5] if g.get("name")]
    if not genres:
        genres = [t["name"] for t in sorted(
            (d.get("tags") or []), key=lambda x: -(x.get("count") or 0))[:5] if t.get("name")]
    return {
        "type":     d.get("type"),
        "gender":   d.get("gender"),
        "area":     (d.get("area") or {}).get("name"),
        "country":  d.get("country"),
        "begin":    (d.get("life-span") or {}).get("begin"),
        "end":      (d.get("life-span") or {}).get("end"),
        "genres":   genres,
        "wikidata": _wikidata_qid(d.get("relations")),
    }


def mb_label_search(name):
    if not name:
        return None
    try:
        d = _get("https://musicbrainz.org/ws/2/label?query="
                 f"{urllib.parse.quote(name)}&fmt=json&limit=1", _mb_lock, _mb_last, _MB)
    except Exception:
        return None
    lab = (d.get("labels") or [None])[0]
    return lab.get("id") if lab else None


def mb_label(mbid):
    try:
        d = _get(f"https://musicbrainz.org/ws/2/label/{mbid}?fmt=json&inc=url-rels",
                 _mb_lock, _mb_last, _MB)
    except Exception:
        return {}
    return {
        "type":     d.get("type"),
        "area":     (d.get("area") or {}).get("name"),
        "country":  d.get("country"),
        "begin":    (d.get("life-span") or {}).get("begin"),
        "wikidata": _wikidata_qid(d.get("relations")),
    }


def _wikidata_qid(relations):
    for rel in (relations or []):
        url = (rel.get("url") or {}).get("resource", "")
        if "wikidata.org" in url:
            return url.rstrip("/").split("/")[-1]
    return None


# ─── Wikidata via the Action API (wbgetentities) ────────────────────

def _wb_get(ids, props):
    if not ids:
        return {}
    url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
           f"&languages=en&props={props}&ids={urllib.parse.quote('|'.join(ids))}")
    try:
        d = _get(url, _wd_lock, _wd_last, _WD)
    except Exception:
        return {}
    return d.get("entities") or {}


def _claim_qid(ent, pid):
    try:
        return ent["claims"][pid][0]["mainsnak"]["datavalue"]["value"]["id"]
    except Exception:
        return None


def _claim_val(ent, pid):
    try:
        return ent["claims"][pid][0]["mainsnak"]["datavalue"]["value"]
    except Exception:
        return None


def _label(ent):
    try:
        return ent["labels"]["en"]["value"]
    except Exception:
        return None


def _enwiki_title(ent):
    try:
        return ent["sitelinks"]["enwiki"]["title"]
    except Exception:
        return None


def wd_artist(qid):
    ent = _wb_get([qid], "claims|sitelinks").get(qid)
    if not ent:
        return {}
    cit, bp, gen = _claim_qid(ent, "P27"), _claim_qid(ent, "P19"), _claim_qid(ent, "P21")
    enwiki = _enwiki_title(ent)
    res = _wb_get([x for x in {cit, bp, gen} if x], "labels|claims")
    lat = lon = bp_country_qid = None
    bp_ent = res.get(bp) if bp else None
    if bp_ent:
        coord = _claim_val(bp_ent, "P625")
        if isinstance(coord, dict):
            lat, lon = coord.get("latitude"), coord.get("longitude")
        bp_country_qid = _claim_qid(bp_ent, "P17")
    country = None
    if bp_country_qid:
        country = _label(_wb_get([bp_country_qid], "labels").get(bp_country_qid, {}))
    return {
        "citizenship": _label(res.get(cit, {})) if cit else None,
        "country":     country or (_label(res.get(cit, {})) if cit else None),
        "birthplace":  _label(res.get(bp, {})) if bp else None,
        "gender":      _label(res.get(gen, {})) if gen else None,
        "latitude":    lat, "longitude": lon,
        "enwiki":      enwiki,
    }


def wd_label(qid):
    ent = _wb_get([qid], "claims|sitelinks").get(qid)
    if not ent:
        return {}
    country, hq, founder = _claim_qid(ent, "P17"), _claim_qid(ent, "P159"), _claim_qid(ent, "P112")
    inception = _claim_val(ent, "P571")
    enwiki = _enwiki_title(ent)
    res = _wb_get([x for x in {country, hq, founder} if x], "labels|claims")
    lat = lon = None
    if hq and res.get(hq):
        coord = _claim_val(res[hq], "P625")
        if isinstance(coord, dict):
            lat, lon = coord.get("latitude"), coord.get("longitude")
    return {
        "country":   _label(res.get(country, {})) if country else None,
        "hq":        _label(res.get(hq, {})) if hq else None,
        "founder":   _label(res.get(founder, {})) if founder else None,
        "inception": _year(inception.get("time")) if isinstance(inception, dict) else None,
        "latitude":  lat, "longitude": lon,
        "enwiki":    enwiki,
    }


def wikipedia_summary(title):
    """Short, human-written article lead (NOT AI), by Wikipedia title."""
    if not title:
        return None
    t = urllib.parse.quote(title.replace(" ", "_"))
    try:
        d = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}",
                 _wp_lock, _wp_last, _WP)
    except Exception:
        return None
    return (d.get("extract") or "").strip() or None


def _enwiki_url(title):
    return "https://en.wikipedia.org/wiki/" + title.replace(" ", "_") if title else None


# ─── Discogs (OPTIONAL supplement — free token, degrades gracefully) ─

def discogs_label_founding(name, token):
    if not (name and token):
        return {}
    try:
        s = _get("https://api.discogs.com/database/search?"
                 + urllib.parse.urlencode({"q": name, "type": "label", "token": token, "per_page": 1}))
        res = (s.get("results") or [None])[0]
        if not res:
            return {}
        d = _get(f"https://api.discogs.com/labels/{res['id']}?token={token}")
    except Exception:
        return {}
    m = re.search(r"(?:founded|established|est\.?|formed)\D{0,12}((?:18|19|20)\d{2})",
                  d.get("profile") or "", re.I)
    return {"founded_year": int(m.group(1))} if m else {}


# ─── orchestrators ──────────────────────────────────────────────────

def enrich_artist(name, isrc=None, discogs_token=None):
    """Cultural facts for an artist, or {error}. Prefers birthplace/origin
    for mapping; falls back to MusicBrainz area."""
    mbid, method = None, None
    if isrc:
        mbid = mb_artist_mbid_by_isrc(isrc)
        if mbid:
            method = "isrc"
    if not mbid:
        mbid = mb_artist_search(name)
        if mbid:
            method = "name-search"
    if not mbid:
        return {"error": "no MusicBrainz match"}

    mb = mb_artist(mbid)
    wd = wd_artist(mb["wikidata"]) if mb.get("wikidata") else {}
    bio = wikipedia_summary(wd.get("enwiki")) if wd.get("enwiki") else None

    src = [f"musicbrainz({method})"]
    if mb.get("wikidata"):
        src.append("wikidata")
    if bio:
        src.append("wikipedia")

    return {
        "mbid":           mbid,
        "wikidata_qid":   mb.get("wikidata"),
        "artist_type":    mb.get("type"),
        "country":        wd.get("country") or mb.get("country") or mb.get("area"),
        "city":           wd.get("birthplace") or mb.get("area"),
        "latitude":       wd.get("latitude"),
        "longitude":      wd.get("longitude"),
        "gender":         mb.get("gender") or wd.get("gender"),
        "active_from":    mb.get("begin"),
        "active_to":      mb.get("end"),
        "genres":         ", ".join(mb.get("genres") or []) or None,
        "bio_summary":    bio,
        "wikipedia_note": _enwiki_url(wd.get("enwiki")),
        "data_source":    ", ".join(src),
    }


def enrich_label(name, discogs_token=None):
    mbid = mb_label_search(name)
    mb = mb_label(mbid) if mbid else {}
    wd = wd_label(mb["wikidata"]) if mb.get("wikidata") else {}
    bio = wikipedia_summary(wd.get("enwiki")) if wd.get("enwiki") else None

    founded = wd.get("inception") or _year(mb.get("begin"))
    src = []
    if mbid:
        src.append("musicbrainz")
    if mb.get("wikidata"):
        src.append("wikidata")
    if bio:
        src.append("wikipedia")
    if not founded and discogs_token:
        dc = discogs_label_founding(name, discogs_token)
        if dc.get("founded_year"):
            founded = dc["founded_year"]
            src.append("discogs")

    if not src:
        return {"error": "no match"}
    return {
        "mbid":          mbid,
        "wikidata_qid":  mb.get("wikidata"),
        "country":       wd.get("country") or mb.get("country") or mb.get("area"),
        "city":          wd.get("hq"),
        "latitude":      wd.get("latitude"),
        "longitude":     wd.get("longitude"),
        "founded_year":  founded,
        "founder":       wd.get("founder"),
        "bio_summary":   bio,
        "wikipedia_url": _enwiki_url(wd.get("enwiki")),
        "data_source":   ", ".join(src),
    }
