"""
feeds.py — tiny, dependency-free RSS/Atom reader for Explore.

Music Room's Explore should feel like a living magazine rack: open it and
there's fresh stuff from the sources you already trust (no algorithm, just
your chosen places). This module turns a source's website into a list of
recent items with an image, headline, excerpt and date.

No feedparser dependency — a compact stdlib parser handles RSS 2.0 + Atom,
which covers the WordPress-style music press. Feeds are discovered from the
site's <link rel="alternate"> tag, with a couple of common-path fallbacks.

Returns plain dicts; persistence + scheduling live in app.py.
"""

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

USER_AGENT = "MusicRoom/1.0 (personal DJ library tool)"


def _get(url, timeout=15):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT,
                      "Accept": "application/rss+xml, application/atom+xml, text/xml, text/html, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _ln(tag):
    """Local name of a (possibly namespaced) element tag, lowercased."""
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _abs(base, href):
    try:
        return urllib.parse.urljoin(base, href)
    except Exception:
        return href


# ─── feed discovery ─────────────────────────────────────────────────

# Known feeds for sites whose feed isn't auto-discoverable (JS-only homepages,
# non-standard paths). Keyed by netloc. Checked before autodiscovery.
SEED_FEEDS = {
    "ra.co":               "https://ra.co/xml/podcast.xml",   # RA Podcast / RA Exchange
    "residentadvisor.net": "https://ra.co/xml/podcast.xml",
}


def _resolve_youtube_feed(url):
    """A YouTube channel / user / playlist URL → its Atom feed (videos.xml).
    Channels and playlists publish a feed; @handle / custom / user URLs need a
    channelId, scraped from the page. Lets the user paste any YouTube link and
    get the channel's uploads in Explore (video items — no in-app audio)."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.netloc.lower().replace("www.", "")
        if "youtube.com" not in host and "youtu.be" not in host:
            return None
        qs = urllib.parse.parse_qs(parts.query)
        if qs.get("list"):                                   # explicit playlist
            return "https://www.youtube.com/feeds/videos.xml?playlist_id=" + qs["list"][0]
        m = re.search(r"/channel/(UC[\w-]+)", parts.path)    # /channel/UC…
        if m:
            return "https://www.youtube.com/feeds/videos.xml?channel_id=" + m.group(1)
        # /@handle, /c/Custom, /user/Name → scrape the channelId from the page
        page = _get(url).decode("utf-8", "ignore")
        cm = (re.search(r'"channelId":"(UC[\w-]+)"', page)
              or re.search(r'"externalId":"(UC[\w-]+)"', page)
              or re.search(r'/channel/(UC[\w-]+)', page))
        if cm:
            return "https://www.youtube.com/feeds/videos.xml?channel_id=" + cm.group(1)
    except Exception:
        pass
    return None


def _resolve_apple_podcast(url):
    """An Apple Podcasts / iTunes URL → the show's real RSS feed, via the public
    iTunes Lookup API (returns feedUrl). Dependency-free JSON; the resulting
    feed is a normal podcast RSS, so its episodes carry playable audio."""
    try:
        if "apple.com" not in urllib.parse.urlsplit(url).netloc.lower():
            return None
        m = re.search(r"/id(\d+)", url) or re.search(r"[?&]i=(\d+)", url)
        if not m:
            return None
        raw = _get("https://itunes.apple.com/lookup?id=" + m.group(1), timeout=12)
        data = json.loads(raw.decode("utf-8", "ignore"))
        for r in data.get("results", []):
            if r.get("feedUrl"):
                return r["feedUrl"]
    except Exception:
        pass
    return None


# Platform URLs that don't publish a discoverable <link rel=alternate> we can
# trust — resolved to their real feed by a dedicated function. Tried in order.
PLATFORM_RESOLVERS = (_resolve_youtube_feed, _resolve_apple_podcast)


def discover_feed(site_url):
    """Find a feed URL for a site. Tries a known-feeds map, platform-specific
    resolvers (YouTube/Apple), then <link rel=alternate> autodiscovery, then a
    few common paths. Returns a validated feed URL or None."""
    if not site_url:
        return None
    # 0. known hard-to-discover feeds
    try:
        host = urllib.parse.urlsplit(site_url).netloc.replace("www.", "")
        if host in SEED_FEEDS and _looks_like_feed(SEED_FEEDS[host]):
            return SEED_FEEDS[host]
    except Exception:
        pass
    # 0b. platform resolvers — YouTube channels, Apple Podcasts. These source
    # types are common but don't expose a feed the generic path can find.
    for resolve in PLATFORM_RESOLVERS:
        try:
            cand = resolve(site_url)
        except Exception:
            cand = None
        if cand and _looks_like_feed(cand):
            return cand
    # 1. autodiscovery from the homepage <head>
    try:
        page = _get(site_url).decode("utf-8", "ignore")
        for m in re.finditer(r"<link\b[^>]*>", page, re.I):
            tag = m.group(0)
            if re.search(r"""type\s*=\s*["'](?:application/(?:rss|atom)\+xml)""", tag, re.I):
                href = re.search(r"""href\s*=\s*["']([^"']+)""", tag, re.I)
                if href:
                    cand = _abs(site_url, href.group(1))
                    if _looks_like_feed(cand):
                        return cand
    except Exception:
        pass
    # 2. common WordPress / generic paths
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(site_url))
    base = site_url.rstrip("/")
    for cand in (base + "/feed/", base + "/feed", origin + "/feed/",
                 origin + "/rss", origin + "/rss.xml", base + "/rss"):
        if _looks_like_feed(cand):
            return cand
    return None


def _looks_like_feed(url):
    """Fetch a candidate and check it parses as RSS/Atom with at least one item."""
    try:
        raw = _get(url, timeout=12)
        root = ET.fromstring(raw)
    except Exception:
        return False
    return any(_ln(e.tag) in ("item", "entry") for e in root.iter())


# ─── parsing ────────────────────────────────────────────────────────

_IMG_IN_HTML = re.compile(r"""<img[^>]+src\s*=\s*["']([^"']+)""", re.I)
_TAG = re.compile(r"<[^>]+>")


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _clean_summary(raw, limit=280):
    if not raw:
        return ""
    txt = html.unescape(_TAG.sub(" ", raw))
    txt = re.sub(r"\s+", " ", txt).strip()
    return (txt[:limit].rstrip() + "…") if len(txt) > limit else txt


def _parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    # RSS: RFC-822  ·  Atom: ISO-8601
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return None


def _extract_image(item, base):
    """Pull a usable image URL from media:*/enclosure/itunes:image, or the
    first <img> in the content/description."""
    content_html = ""
    # flatten one level of media:group (YouTube/MRSS nest thumbnail+content there)
    children = []
    for c in item:
        children.append(c)
        if _ln(c.tag) == "group":
            children.extend(list(c))
    for child in children:
        ln = _ln(child.tag)
        attr = child.attrib
        if ln in ("thumbnail", "content") and ("medium" in attr or "type" in attr or "url" in attr):
            url = attr.get("url")
            typ = (attr.get("type") or attr.get("medium") or "").lower()
            if url and ("image" in typ or ln == "thumbnail" or re.search(r"\.(jpe?g|png|webp|gif)", url, re.I)):
                return _abs(base, url)
        if ln == "enclosure":
            url = attr.get("url")
            if url and "image" in (attr.get("type") or "").lower():
                return _abs(base, url)
        if ln == "image":  # itunes:image href, or RSS <image><url>
            if attr.get("href"):
                return _abs(base, attr["href"])
        if ln in ("encoded", "content", "summary", "description"):
            content_html += " " + (child.text or "")
    m = _IMG_IN_HTML.search(content_html or "")
    if m:
        return _abs(base, m.group(1))
    return None


def _parse_duration(raw):
    """itunes:duration → seconds. Accepts plain seconds, 'MM:SS' or 'HH:MM:SS'."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        if ":" in raw:
            sec = 0.0
            for p in raw.split(":"):
                sec = sec * 60 + float(p)
            return sec
        return float(raw)
    except Exception:
        return None


_AUDIO_EXT = re.compile(r"\.(mp3|m4a|aac|ogg|oga|opus|wav|flac)(\?|#|$)", re.I)


def _extract_audio(item, base):
    """A directly-playable audio URL from an item — the podcast/mix enclosure,
    so Explore can play it through the persistent Player. Prefers the RSS
    <enclosure type=audio/*>, then a media:content of an audio type/medium."""
    for child in item:                       # 1. RSS enclosure (the standard)
        if _ln(child.tag) == "enclosure":
            url = child.attrib.get("url")
            typ = (child.attrib.get("type") or "").lower()
            if url and (typ.startswith("audio/") or _AUDIO_EXT.search(url)):
                return _abs(base, url)
    for child in item:                       # 2. media:content / media:group
        ln = _ln(child.tag)
        if ln not in ("content", "group"):
            continue
        for c in ([child] if ln == "content" else list(child)):
            if _ln(c.tag) != "content":
                continue
            url = c.attrib.get("url")
            typ = (c.attrib.get("type") or "").lower()
            medium = (c.attrib.get("medium") or "").lower()
            if url and (typ.startswith("audio/") or medium == "audio"):
                return _abs(base, url)
    return None


def _parse_item(item, base):
    title = link = summary_raw = guid = published = duration_raw = None
    for child in item:
        ln = _ln(child.tag)
        if ln == "title" and not title:
            title = _text(child)
        elif ln == "link":
            # RSS: text node. Atom: href attr (prefer rel=alternate).
            href = child.attrib.get("href")
            if href:
                if child.attrib.get("rel", "alternate") == "alternate" or not link:
                    link = href
            elif child.text:
                link = child.text.strip()
        elif ln in ("guid", "id") and not guid:
            guid = _text(child)
        elif ln in ("pubdate", "published", "updated", "date") and not published:
            published = _parse_date(_text(child))
        elif ln == "duration" and not duration_raw:     # itunes:duration
            duration_raw = _text(child)
        elif ln in ("description", "summary", "encoded", "content") and not summary_raw:
            summary_raw = child.text or ""
    if not (title or link):
        return None
    return {
        "guid":         guid or link or title,
        "title":        html.unescape(title or "").strip() or "(untitled)",
        "url":          _abs(base, link) if link else None,
        "summary":      _clean_summary(summary_raw),
        "image_url":    _extract_image(item, base),
        "published_at": published,
        "audio_url":    _extract_audio(item, base),
        "audio_duration_sec": _parse_duration(duration_raw),
    }


def fetch_feed(feed_url, limit=40):
    """Fetch + parse a feed. Returns a list of item dicts (newest-ish first,
    as the feed orders them). Raises on network/parse failure."""
    raw = _get(feed_url)
    root = ET.fromstring(raw)
    base = feed_url
    items = []
    for node in root.iter():
        if _ln(node.tag) in ("item", "entry"):
            d = _parse_item(node, base)
            if d:
                items.append(d)
            if len(items) >= limit:
                break
    return items
