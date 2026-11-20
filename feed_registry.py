"""
Curated RSS-feed registry.

Maps a music SOURCE (by domain, or by the name the user typed) to a known-good
RSS/Atom feed — so when someone adds a source by LINK, we can hand them a feed
even when auto-discovery (feeds.discover_feed) can't find one (radio sites,
JS-heavy homepages, non-standard feed paths).

It is NOT shown in Explore and never makes a source appear on its own — it's a
lookup table consulted at add-time only. Seeded from the user's own working
feeds + a curated set of music publications (each verified with
feeds._looks_like_feed), refreshed monthly by scripts/update_feed_registry.py
and shipped as static/data/feed_registry.json (which overrides CURATED below).
"""
import json
import os
import re
from urllib.parse import urlsplit

_HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(_HERE, "static", "data", "feed_registry.json")

# Verified 2026-06-22 via feeds._looks_like_feed. Keyed by BARE netloc (no www).
# The first block is the user's own confirmed-working feeds; the rest is the
# curated starter set of electronic / dance / independent-music publications.
CURATED = {
    "ra.co":              "https://ra.co/xml/podcast.xml",
    "daily.bandcamp.com": "https://daily.bandcamp.com/feed/",
    "crackmagazine.net":  "https://crackmagazine.net/feed/",
    "factmag.com":        "https://www.factmag.com/feed/",
    "mixmag.net":         "https://mixmag.net/rss.xml",
    "thewire.co.uk":      "https://www.thewire.co.uk/home/rss",
    "trommelmusic.com":   "https://trommelmusic.com/feed/",
    "pitchfork.com":      "https://pitchfork.com/feed/feed-news/rss",
    "xlr8r.com":          "https://xlr8r.com/feed/",
    "attackmagazine.com": "https://www.attackmagazine.com/feed/",
    "inverted-audio.com": "https://www.inverted-audio.com/feed/",
    "5mag.net":           "https://5mag.net/feed/",
    "djmag.com":          "https://djmag.com/rss.xml",
    "stampthewax.com":    "https://stampthewax.com/feed/",
    "theransomnote.com":  "https://www.theransomnote.com/feed/",
    "thequietus.com":     "https://thequietus.com/feed/",
    "cdm.link":           "https://cdm.link/feed/",
}

# Name → netloc, so a name typed in the "add source" form resolves too.
NAME_ALIASES = {
    "resident advisor": "ra.co", "ra": "ra.co",
    "bandcamp daily": "daily.bandcamp.com",
    "crack magazine": "crackmagazine.net", "crack": "crackmagazine.net",
    "fact magazine": "factmag.com", "fact": "factmag.com", "fact mixes": "factmag.com",
    "mixmag": "mixmag.net",
    "the wire": "thewire.co.uk",
    "trommel": "trommelmusic.com",
    "pitchfork": "pitchfork.com",
    "xlr8r": "xlr8r.com",
    "attack magazine": "attackmagazine.com", "attack": "attackmagazine.com",
    "inverted audio": "inverted-audio.com",
    "5 magazine": "5mag.net", "5 mag": "5mag.net",
    "dj mag": "djmag.com", "djmag": "djmag.com",
    "stamp the wax": "stampthewax.com",
    "the ransom note": "theransomnote.com", "ransom note": "theransomnote.com",
    "the quietus": "thequietus.com", "quietus": "thequietus.com",
    "cdm": "cdm.link", "create digital music": "cdm.link",
}

_cache = None


def normalize_netloc(url):
    """A bare host key: lowercased, no scheme, no www, no port/userinfo."""
    if not url:
        return ""
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    host = (urlsplit(u).hostname or "").lower()   # .hostname drops port + credentials
    return host[4:] if host.startswith("www.") else host


def _norm_name(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def load_registry(force=False):
    """CURATED, overridden by the shipped/updated JSON (by_netloc)."""
    global _cache
    if _cache is not None and not force:
        return _cache
    by_netloc = dict(CURATED)
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in (data.get("by_netloc") or {}).items():
            if v:
                by_netloc[k.lower()] = v
    except Exception:
        pass
    _cache = by_netloc
    return _cache


def lookup(name="", url=""):
    """Best known feed for a source being added by link/name, or None.
    EXACT host only (+ typed-name alias). We deliberately do NOT map an arbitrary
    subdomain of a registry domain to its feed (evil.ra.co must not borrow ra.co's
    feed) — an unknown host just falls through to live discovery."""
    reg = load_registry()
    net = normalize_netloc(url)
    if net and net in reg:
        return reg[net]
    nn = _norm_name(name)
    if nn:
        alias = NAME_ALIASES.get(nn)
        if alias and alias in reg:
            return reg[alias]
    return None
