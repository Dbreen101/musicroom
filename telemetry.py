"""
telemetry.py — the data charter (VISION §4.14) expressed in code.

Phase-2 OFF-DEVICE telemetry. Every path here is OFF by default and gated behind
explicit, separate, per-purpose consent. Only AGGREGATE MONTHLY ROLLUPS of a small,
HARDCODED allowlist are ever built — never a per-event stream, never titles / artists
/ albums / which record / file paths / notes / search terms / precise timestamps /
a stable device id / an IP. The allowlist below is the ENTIRE off-device surface:
if a field is not named here, it structurally cannot leave the machine.

The anonymous id ROTATES MONTHLY (sha256(local-seed : YYYY-MM)) so a device can't be
linked across months; the seed is local-only and never transmitted. Counts are coarsened
into buckets at source (k-anonymity friendly; the server suppresses small cells too).
"""
import hashlib
import json
import urllib.request

SCHEMA_VERSION = 1
FIELD_LIST_VERSION = 1   # bump when the allowlist changes; shown to the user before they agree

# ── the field allowlist — the WHOLE surface, published here + shown in-app ──
# usage analytics (one consent) — coarse monthly buckets, one per metric:
USAGE_METRICS = [
    "plays", "active_days", "notes_made", "wishlist_adds",
    "imports_made", "library_size", "research_entities", "maps_made",
]
# purchase tracking (a SEPARATE consent) — the artist-impact signal:
PURCHASE_METRICS = ["buy_clicks", "bought"]
PURCHASE_STORES = ("bandcamp", "other")   # closed set — never a URL, never a record

# shown verbatim in the consent screen so the promise is legible:
NEVER_COLLECTED = [
    "track / artist / album titles",
    "your library contents or file paths",
    "the text of any note",
    "search queries (only a count of zero-result searches, never the terms)",
    "which record you clicked or bought (only a store name from a fixed list)",
    "precise timestamps (month only)",
    "a stable device id (the id rotates every month)",
    "your IP address (dropped at ingest, never stored)",
]
CHARTER_LINE = ("This exists only to design the app and measure whether it drives real "
                "support to artists. It will never be sold, shared for ads, used to profile "
                "your taste, used to push you to buy more, or used to train anything.")


def _bucket(n):
    """Coarsen a count so a single device's rollup can't be a fingerprint."""
    n = int(n or 0)
    if n <= 0:    return "0"
    if n < 10:    return "1-9"
    if n < 50:    return "10-49"
    if n < 200:   return "50-199"
    if n < 1000:  return "200-999"
    return "1000+"


def install_hash(seed, month):
    """A month-ROTATING anonymous id = sha256(seed : month), truncated. The seed is
    local-only and never sent; the hash cannot be linked across months. None if no seed."""
    if not seed:
        return None
    return hashlib.sha256(f"{seed}:{month}".encode("utf-8")).hexdigest()[:16]


def build_usage_rollup(install_id, month, raw):
    """raw = dict of raw counts. Emits ONLY allowlisted metrics, each bucketed — the
    dict-comprehension over USAGE_METRICS is what makes off-list data impossible to send."""
    return {
        "schema_v": SCHEMA_VERSION, "kind": "usage", "month": month, "install": install_id,
        "metrics": {m: _bucket(raw.get(m, 0)) for m in USAGE_METRICS},
    }


def build_purchase_rollup(install_id, month, raw, by_store):
    return {
        "schema_v": SCHEMA_VERSION, "kind": "purchase", "month": month, "install": install_id,
        "metrics": {m: _bucket(raw.get(m, 0)) for m in PURCHASE_METRICS},
        "by_store": {s: _bucket((by_store or {}).get(s, 0)) for s in PURCHASE_STORES},
    }


def build_rollups(*, usage_consent, purchase_consent, install_id, month, usage_raw, purchase_raw, by_store):
    """The complete set of rollups the device would send this month, gated by consent.
    Returns a list (possibly empty). This is the ONLY producer of off-device payloads."""
    out = []
    if usage_consent:
        out.append(build_usage_rollup(install_id, month, usage_raw))
    if purchase_consent:
        out.append(build_purchase_rollup(install_id, month, purchase_raw, by_store))
    return out


def send_rollup(ingest_url, rollup, timeout=12):
    """POST one rollup to the user's own ingest endpoint. Returns (status, body) or raises.
    No cookies, no extra headers, no identifiers beyond the rotating hash in the payload."""
    data = json.dumps(rollup, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        ingest_url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "MusicRoom-telemetry/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(300).decode("utf-8", "replace")


def field_manifest():
    """The full, honest field list for the consent screen + the published repo doc."""
    return {
        "field_list_version": FIELD_LIST_VERSION,
        "schema_version": SCHEMA_VERSION,
        "usage_metrics": USAGE_METRICS,
        "purchase_metrics": PURCHASE_METRICS,
        "purchase_stores": list(PURCHASE_STORES),
        "buckets": ["0", "1-9", "10-49", "50-199", "200-999", "1000+"],
        "never_collected": NEVER_COLLECTED,
        "charter_line": CHARTER_LINE,
        "rotating_id": "sha256(local-seed : YYYY-MM), truncated — rotates monthly, seed never sent",
    }
