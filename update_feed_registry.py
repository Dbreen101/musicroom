#!/usr/bin/env python3
"""Regenerate the curated RSS-feed registry (static/data/feed_registry.json).

Run monthly: merges the user's own confirmed-working feeds (from the live
`sources` table) on top of the curated set in feed_registry.CURATED, optionally
re-validates every feed, and writes the shipped JSON stamped with today's date.
Then commit + tag (e.g. feed-registry-2026-07) so users pick it up on update —
it never adds sources to anyone's Explore, it just lets a pasted link find a
known feed.

    python3 update_feed_registry.py             # merge + write (no network)
    python3 update_feed_registry.py --validate  # also drop feeds that no longer parse
"""
import datetime
import json
import os
import sqlite3
import sys

import feed_registry
import mr_paths

OUT = feed_registry.REGISTRY_PATH


def _live_source_feeds():
    """netloc -> feed_url for every source the user has that carries a feed."""
    out = {}
    try:
        db = sqlite3.connect(mr_paths.DB_PATH)
        db.row_factory = sqlite3.Row
        for r in db.execute("SELECT url, feed_url FROM sources "
                            "WHERE feed_url IS NOT NULL AND TRIM(feed_url) != ''"):
            net = feed_registry.normalize_netloc(r["url"])
            if net and r["feed_url"]:
                out[net] = r["feed_url"].strip()
        db.close()
    except Exception as e:
        print(f"  (no live DB to read your sources from: {e})")
    return out


def main():
    validate = "--validate" in sys.argv
    by_netloc = dict(feed_registry.CURATED)
    live = _live_source_feeds()
    added = {k: v for k, v in live.items() if k not in by_netloc}
    by_netloc.update(live)                      # the user's own confirmed feeds win

    if validate:
        import feeds
        kept = {}
        for net, url in by_netloc.items():
            try:
                ok = feeds._looks_like_feed(url)
            except Exception:
                ok = False
            if ok:
                kept[net] = url
            else:
                print(f"  drop (no longer a feed): {net}  {url}")
        by_netloc = kept

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {
        "updated": datetime.date.today().isoformat(),
        "count": len(by_netloc),
        "by_netloc": dict(sorted(by_netloc.items())),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {OUT}  ({len(by_netloc)} feeds; {len(added)} new from your sources)")
    if added:
        print("  new from your sources: " + ", ".join(sorted(added)))


if __name__ == "__main__":
    main()
