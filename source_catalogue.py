"""
source_catalogue.py — the ship-with, searchable catalogue of sources + discovery
tools the user browses when ADDING a source.

The point (Daithí, 2026-06-25): you shouldn't need to know a site's name. Search
the *vibe* — "photo discovery", "deep listening", "world map" — and the catalogue
surfaces matching publications, stations, blogs, newsletters and discovery tools,
each one-tap addable to your Explore. Link-out by default; a `feed_url` is present
only where a working feed is known.

Data ships in static/data/source_catalogue.json. Per-install state (user reports +
weekly link-health results) lives in DATA_DIR/catalogue_state.json — never shipped,
never uploaded. This module is the only thing that reads/writes either.
"""
import json
import os
import threading
import datetime
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
CATALOGUE_PATH = os.path.join(_HERE, "static", "data", "source_catalogue.json")

try:
    from mr_paths import DATA_DIR
    STATE_PATH = os.path.join(DATA_DIR, "catalogue_state.json")
except Exception:
    STATE_PATH = None

_UA = "MusicRoom/1.0 (personal DJ library tool; catalogue link-check)"
_lock = threading.RLock()
_cache = None          # parsed catalogue entries (list of dicts)
_cache_mtime = None


# ─── catalogue data (shipped, read-only) ────────────────────────────────────
def _load_entries():
    global _cache, _cache_mtime
    try:
        mt = os.path.getmtime(CATALOGUE_PATH)
    except Exception:
        return []
    with _lock:
        if _cache is not None and _cache_mtime == mt:
            return _cache
        try:
            with open(CATALOGUE_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            entries = data.get("entries") if isinstance(data, dict) else data
            _cache = [e for e in (entries or []) if e.get("id") and e.get("name") and e.get("url")]
            _cache_mtime = mt
        except Exception:
            _cache = _cache or []
        return _cache


def all_entries():
    return list(_load_entries())


def get(entry_id):
    return next((e for e in _load_entries() if e.get("id") == entry_id), None)


def all_tags():
    """Every distinct vibe/topic tag in the catalogue, for tag-chip suggestions."""
    seen = {}
    for e in _load_entries():
        for t in (e.get("tags") or []):
            seen[t.lower()] = t
    return sorted(seen.values(), key=str.lower)


# ─── search: name + tags + blurb + type, ranked ─────────────────────────────
def search(query="", type_filter=None, limit=40):
    """Rank catalogue entries against a free-text query. Matches the NAME, the
    vibe/topic TAGS, the blurb and the type — so 'photo discovery' finds are.na
    and 'world map' finds Radio Garden, without knowing either name. Empty query
    returns everything (optionally filtered by type), tools last so feeds lead."""
    q = (query or "").strip().lower()
    terms = [t for t in q.replace(",", " ").split() if t]
    entries = _load_entries()
    state = get_state()
    health = state.get("health", {})
    reports = state.get("reports", {})

    scored = []
    for e in entries:
        if type_filter and e.get("type") != type_filter:
            continue
        name = (e.get("name") or "").lower()
        blurb = (e.get("blurb") or "").lower()
        tags = [str(t).lower() for t in (e.get("tags") or [])]
        tagblob = " ".join(tags)
        # word-aware matching so "world" doesn't bleed into "worldwide" — the
        # literal vibe tag ("world map", "photo discovery") must win.
        name_words = set(name.replace("/", " ").split())
        tag_words = set(tagblob.split())
        blurb_words = set(blurb.split())
        score = 0
        if not terms:
            score = 1
        else:
            for term in terms:
                if term in name_words:                 score += 6     # whole word in name
                elif term in name:                     score += 2     # substring in name
                if term in tag_words:                  score += 5     # whole word across tags
                if term in blurb_words:                score += 2
                if term == (e.get("type") or ""):      score += 2
            # the user typed a literal vibe (e.g. "photo discovery", "world map"):
            # an exact tag is the strongest signal, a phrase-in-tags next.
            if q and q in tags:                        score += 20    # exact tag == query
            if q and q in tagblob:                     score += 8     # phrase present in tags
            elif q and q in blurb:                     score += 4
            if q and q in name:                        score += 6
        if score <= 0:
            continue
        out = dict(e)
        h = health.get(e["id"]) or {}
        out["health"] = h.get("status", "unknown")          # ok | broken | unknown
        out["health_checked_at"] = h.get("checked_at")
        out["report_count"] = len(reports.get(e["id"]) or [])
        out["_score"] = score
        scored.append(out)

    # rank: broken + reported sink first; then best SCORE wins (so a great vibe
    # match surfaces even if it's a tool); 'tool' + 'has feed' are only tiebreakers
    # among equal scores — which is what orders the no-query browse (feeds first).
    def keyf(o):
        broken = 1 if o["health"] == "broken" else 0
        reported = min(o["report_count"], 3)
        has_feed = 1 if (o.get("feed_url") or "").strip() else 0
        website = 1 if o.get("type") == "website" else 0
        return (broken, reported, -o["_score"], website, -has_feed, o["name"].lower())

    scored.sort(key=keyf)
    for o in scored:
        o.pop("_score", None)
    return scored[: max(1, limit)]


# ─── per-install state: reports + health (DATA_DIR, never shipped) ──────────
def get_state():
    if not STATE_PATH or not os.path.exists(STATE_PATH):
        return {"reports": {}, "health": {}}
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        d.setdefault("reports", {})
        d.setdefault("health", {})
        return d
    except Exception:
        return {"reports": {}, "health": {}}


def _save_state(state):
    if not STATE_PATH:
        return
    try:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def report(entry_id, reason=""):
    """User flags a catalogue entry as broken / not useful. Stored locally; it
    sinks the entry in search and feeds the health view. Returns the new count."""
    if not get(entry_id):
        return None
    with _lock:
        state = get_state()
        reps = state.setdefault("reports", {})
        lst = reps.setdefault(entry_id, [])
        lst.append({
            "reason": (reason or "").strip()[:200],
            "at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        })
        _save_state(state)
        return len(lst)


def clear_report(entry_id):
    with _lock:
        state = get_state()
        if entry_id in state.get("reports", {}):
            del state["reports"][entry_id]
            _save_state(state)
        return True


# ─── link-health: weekly automated success test ─────────────────────────────
def _check_one(entry):
    """Reachable? Returns 'ok' | 'broken'. Prefers the feed_url when present
    (and confirms it still looks like a feed), else checks the site URL."""
    target = (entry.get("feed_url") or "").strip() or (entry.get("url") or "").strip()
    is_feed = bool((entry.get("feed_url") or "").strip())
    if not target:
        return "broken"
    try:
        req = urllib.request.Request(target, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            code = getattr(r, "status", 200) or 200
            if code >= 400:
                return "broken"
            if is_feed:
                head = r.read(4096).decode("utf-8", "ignore").lower()
                try:
                    import feeds
                    if hasattr(feeds, "_looks_like_feed") and not feeds._looks_like_feed(head):
                        # not obviously a feed anymore, but reachable — be lenient
                        if not any(t in head for t in ("<rss", "<feed", "<rdf", "<?xml")):
                            return "broken"
                except Exception:
                    pass
            return "ok"
    except Exception:
        return "broken"


def run_health_check(limit=None):
    """Test every catalogue entry's link and store the result. Run weekly (or on
    demand). Polite + bounded; failures mark 'broken' so search can sink them and
    the user sees what's gone stale. Returns a summary."""
    entries = _load_entries()
    if limit:
        entries = entries[:limit]
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    results = {}
    ok = broken = 0
    for e in entries:
        status = _check_one(e)
        results[e["id"]] = {"status": status, "checked_at": now}
        if status == "ok":
            ok += 1
        else:
            broken += 1
    with _lock:
        state = get_state()
        state["health"] = results
        state["health_checked_at"] = now
        _save_state(state)
    return {"checked": len(entries), "ok": ok, "broken": broken, "at": now}


def health_last_run():
    return get_state().get("health_checked_at")
