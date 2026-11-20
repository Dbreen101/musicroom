# How Explore actually works — the plain-language construction notes

_2026-07-04. Written for David — the first of the "understand everything you
built" notes. No syntax needed; every claim checked against the code that day._

## The one-paragraph version

Explore is three databases and a ranking loop. You keep a list of **sources**
(each ideally carrying an RSS feed URL). A **refresh** walks those feeds and
files every post into a big table of **feed items**. When you open the page,
the **tuner** scores every recent item against your **interests** (keyword
lists with weights), shows the highest-scoring ones first, and deliberately
weaves in a few unmatched "wander" items so you never end up in a bubble.
Nothing is learned about you, nothing is a black box, and nothing leaves your
machine — the only network traffic is the app *fetching* the feeds you chose.

## The pieces, in order

**1. Sources** (`sources` table; the Sources panel in Explore).
A source = a name + a website + ideally a `feed_url` (RSS/Atom). Three ways one
gets added: you add it by hand; you add it from the **catalogue** (the
vibe-searchable list of ~35 curated publications/stations/tools that ships with
the app — `static/data/source_catalogue.json`); or a fresh install seeds 11
starters. When you add a source *without* a feed, the app tries to find one in
the background: first the **feed registry** (a ship-with lookup of sites whose
feeds aren't discoverable — `static/data/feed_registry.json`), then live
discovery (reading the site's HTML for a feed link; YouTube channels and Apple
Podcasts pages get special handling — `feeds.py`). If nothing is found, the
source keeps `feed_url = NULL` and its row shows **"no feed"** in the panel —
it's a bookmark, not a stream, until a feed is attached.

**2. Fetching** (`feeds.py`, `/api/feed/refresh`).
A refresh loops over every source that HAS a feed, downloads it, and parses
each entry into: title, link, summary (HTML stripped), image, published date,
and — for podcasts/mixes — the **audio enclosure** (that's why some items can
play in the persistent player). Items land in `feed_items`, de-duplicated by
each entry's guid, so re-fetching never duplicates. Refresh runs when you press
it, and quietly on opening Explore if the feed is more than 20 minutes stale.

**3. The tuner** (`/api/feed`, the "For you" order).
Your **interests** live in the Tuner: each is a name, comma-separated keywords,
and a weight slider. Scoring is honest and dumb on purpose: each interest's
keywords become a whole-word, case-insensitive text match; every item is
checked against its **title + summary + source name + source topics** (not the
full article); its score = the sum of the weights of the interests that hit.
"For you" = matched items sorted by score, then:

- **Wander/serendipity**: a percentage of slots (default ~12%, a Settings dial)
  is reserved for *unmatched* items, shuffled with a seed that changes daily so
  the page is stable within a day. The anti-bubble.
- **New-source guarantee** (added 2026-07-04, after your bug report): items
  from a source added in the **last 14 days** get woven into the first page —
  up to 2 per source, 6 total, at positions 2/6/10… — regardless of score.
  Before this, a new source's items almost never matched your interests yet,
  so they fell into the wander lottery and the source looked broken. Adding a
  source IS an expression of interest; now the feed proves it took.
- "Newest" order skips all of this and is purely chronological.

**4. Reading/listening in place.** Articles open in **reader mode** (the app
extracts the article text itself — `reader.py`, cached); YouTube items embed;
podcast/mix items with an audio enclosure play through the persistent player
(the server downloads to a local cache first). Items that can't be handled
in-app offer "Open in Browser" only.

**5. The wishlist** hangs off Explore but is its own thing: records you want,
in three feeling-boxes (need now / another listen / have a think), with the
sorting game, link-paste recognition, and buy-links that always route out to
the artist. It reads `wishlist` + `purchase_intents`, not the feed tables.

## Where it can genuinely fail (the honest list)

- **A source with no discoverable feed surfaces nothing** — by design it shows
  "no feed", but that's easy to miss. (Vision gap §4.7-1: wire more source
  types — SoundCloud/Mixcloud channels still have no special handling.)
- **A feed that moved/died** stays silent until the weekly link-health pass
  marks it in the catalogue state; the Sources panel report button exists.
- **Sites that block bots** (Bandcamp, RA) still usually serve their *feeds* —
  blocking hits the page fetch, not necessarily the RSS.
- **published_at is only as good as the feed** — undated items sort to the
  bottom of the working window and can age out of it (the scorer only looks at
  the ~600 most recent items).
