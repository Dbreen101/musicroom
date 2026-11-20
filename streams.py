"""
streams.py — recognise a link to music on a streaming service.

The Music Room holds streamed music as LINKS, never as audio: a Spotify or
SoundCloud link is recognised here (which service, what kind of thing, its
title / who it's by / its cover), kept in a grúpa, and played by that service
itself — the listener's own Spotify app, or the service's player beside the
deck (static/js/snt_embed.js).

Everything here uses the services' public, key-less doors only:
  Spotify      — oEmbed (title, cover) + the page's own tags (artist, length)
  SoundCloud   — oEmbed
  Apple Music  — SWITCHED OFF (2026-11-14, David: "remove the apple music
                 integration for the moment"). The recogniser is kept behind
                 ENABLED; add "apple" back to bring it home. Its deck player
                 was taken out of snt_embed.js (git: fc4f880 has it).

No account, no API key, nothing of the listener's is sent — only the link.
"""

import html as _html
import json
import re
import urllib.parse as _up
import urllib.request

UA = {"User-Agent": "MusicRoom/1.0"}
SERVICES = {"spotify": "Spotify", "apple": "Apple Music", "soundcloud": "SoundCloud"}
ENABLED = ("spotify", "soundcloud")      # the services whose links are recognised as streams

_SPOTIFY_TYPES = ("track", "album", "playlist", "artist", "episode", "show")
_APPLE_TYPES = {"album": "album", "playlist": "playlist", "artist": "artist", "song": "track",
                "station": "station", "music-video": "video"}
_SC_RESERVED = {"discover", "stream", "you", "search", "charts", "upload", "settings", "messages",
                "notifications", "people", "pages", "tags", "terms-of-use", "feed", "library", "popular"}


def parse(url):
    """A link → {'source','type','id','url'} when it is a link to one of the
    ENABLED services (Spotify, SoundCloud), else None. `url` comes back tidied: tracking parameters
    dropped, so the same record always reads as the same link."""
    url = (url or "").strip()
    if not url:
        return None
    m = re.match(r"^spotify:(%s):([A-Za-z0-9]+)$" % "|".join(_SPOTIFY_TYPES), url)
    if m:
        return {"source": "spotify", "type": m.group(1), "id": m.group(2),
                "url": f"https://open.spotify.com/{m.group(1)}/{m.group(2)}"}
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        u = _up.urlsplit(url)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    host = re.sub(r"^(www|m)\.", "", host)
    parts = [p for p in u.path.split("/") if p]

    if host in ("open.spotify.com", "play.spotify.com"):
        if parts and re.match(r"^intl-[a-z-]+$", parts[0]):
            parts = parts[1:]
        if parts and parts[0] == "embed":
            parts = parts[1:]
        if len(parts) >= 4 and parts[0] == "user" and parts[2] == "playlist":   # the old long form
            parts = parts[2:]
        if len(parts) >= 2 and parts[0] in _SPOTIFY_TYPES and re.match(r"^[A-Za-z0-9]+$", parts[1]):
            return {"source": "spotify", "type": parts[0], "id": parts[1],
                    "url": f"https://open.spotify.com/{parts[0]}/{parts[1]}"}
        return None
    if host in ("spotify.link", "spotify.app.link"):
        return {"source": "spotify", "type": "", "id": "", "url": url, "short": True}

    if host in ("music.apple.com", "geo.music.apple.com", "embed.music.apple.com"):
        if "apple" not in ENABLED:
            return None
        if len(parts) >= 2 and re.match(r"^[a-z]{2}$", parts[0]):
            cc, rest = parts[0], parts[1:]
        else:
            cc, rest = "us", parts
        if not rest or rest[0] not in _APPLE_TYPES:
            return None
        kind, ident = _APPLE_TYPES[rest[0]], rest[-1]
        q = _up.parse_qs(u.query)
        song = (q.get("i") or [""])[0]
        path = "/" + "/".join([cc] + rest)
        out = {"source": "apple", "type": kind, "id": ident, "country": cc,
               "url": "https://music.apple.com" + path}
        if kind == "album" and re.match(r"^\d+$", song):      # one song on an album
            out.update(type="track", id=song, album_id=ident, url=out["url"] + "?i=" + song)
        return out

    if host in ("soundcloud.com",):
        if not parts or parts[0] in _SC_RESERVED:
            return None
        clean = "https://soundcloud.com/" + "/".join(parts)
        if len(parts) == 1:
            kind = "artist"
        elif parts[1] == "sets":
            kind = "playlist" if len(parts) >= 3 else "artist"
        elif parts[1] in ("tracks", "albums", "likes", "reposts", "popular-tracks", "toptracks", "followers", "following"):
            kind, clean = "artist", "https://soundcloud.com/" + parts[0]
        else:
            kind = "track"
        return {"source": "soundcloud", "type": kind, "id": "/".join(parts), "url": clean}
    if host in ("on.soundcloud.com", "soundcloud.app.goo.gl"):
        return {"source": "soundcloud", "type": "", "id": "", "url": url, "short": True}
    return None


def _get(url, timeout=10, limit=600_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(limit).decode("utf-8", "ignore")


def _meta(page, prop):
    p = re.escape(prop)
    m = (re.search(r'<meta[^>]+(?:property|name)=["\']' + p + r'["\'][^>]+content=["\']([^"\']*)', page, re.I)
         or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']' + p + r'["\']', page, re.I))
    return _html.unescape(m.group(1)).strip() if m else ""


def resolve(url):
    """A streaming link → what it is, ready to keep:
        {'ok', 'source', 'type', 'url', 'title', 'subtitle', 'image',
         'by_ids', 'duration_sec'}
    `subtitle` is who it's by (a track / album) or what it is (a playlist).
    `by_ids` = the service's own ids for who it's by, comma-joined (Spotify
    artist ids; the SoundCloud uploader) — what the AI-made check keys on.
    Returns None when the link isn't a recognised service. Never raises: a
    service that can't be reached leaves title empty and ok False, and the
    link is still kept."""
    info = parse(url)
    if not info:
        return None
    if info.get("short"):                       # a share-sheet short link: follow it once
        try:
            final, _ = _get(info["url"], timeout=8, limit=2000)
            again = parse(final)
            if again and not again.get("short"):
                info = again
        except Exception:
            pass
    src, kind, link = info["source"], info.get("type") or "", info["url"]
    title = subtitle = image = ""
    extra = {}
    try:
        if src == "spotify":
            title, subtitle, image, extra = _spotify(link, kind)
        elif src == "apple":
            title, subtitle, image = _apple(info)
        elif src == "soundcloud":
            title, subtitle, image = _soundcloud(link, kind)
    except Exception:
        pass
    return {"ok": bool(title), "source": src, "type": kind, "url": link,
            "title": title, "subtitle": subtitle, "image": image,
            "by_ids": extra.get("by_ids") or by_ids_of(src, link),
            "duration_sec": extra.get("duration_sec") or 0}


def by_ids_of(source, url):
    """Who a link is by, as far as the link alone says: a SoundCloud link names
    its uploader; a Spotify artist link is its own answer."""
    try:
        parts = [p for p in _up.urlsplit(url).path.split("/") if p]
    except ValueError:
        return ""
    if source == "soundcloud" and parts:
        return parts[0].lower()
    if source == "spotify" and len(parts) >= 2 and parts[0] == "artist":
        return parts[1]
    return ""


def _metas(page, prop):
    """Every value of a repeated tag (a track by three artists has three)."""
    p = re.escape(prop)
    return [_html.unescape(v).strip() for v in
            re.findall(r'<meta[^>]+(?:property|name)=["\']' + p + r'["\'][^>]+content=["\']([^"\']*)', page, re.I)]


def _spotify(link, kind):
    title = subtitle = image = ""
    extra = {}
    try:
        _, body = _get("https://open.spotify.com/oembed?url=" + _up.quote(link, safe=""))
        d = json.loads(body)
        title, image = (d.get("title") or "").strip(), d.get("thumbnail_url") or ""
    except Exception:
        pass
    try:                                        # who it's by lives in the page's own tags
        _, page = _get(link, timeout=12)
        desc = _meta(page, "og:description")    # "Artist · Album · Song · 1987" / "Playlist · Owner · 50 items"
        title = title or _meta(page, "og:title")
        image = image or _meta(page, "og:image")
        bits = [b.strip() for b in desc.split("·") if b.strip()]
        if kind in ("track", "album", "episode") and bits:
            subtitle = bits[0]
        elif kind == "playlist":
            subtitle = ""
        elif kind == "artist":
            subtitle = "Artist"
        ids = [m.rsplit("/", 1)[-1] for m in _metas(page, "music:musician") if "/artist/" in m]
        if ids:
            extra["by_ids"] = ",".join(dict.fromkeys(ids))
        secs = _meta(page, "music:duration")
        if secs.isdigit():
            extra["duration_sec"] = int(secs)
    except Exception:
        pass
    return title, subtitle, image, extra


def _apple(info):
    kind, ident, cc = info["type"], info["id"], info.get("country") or "us"
    if re.match(r"^\d+$", ident or ""):
        _, body = _get(f"https://itunes.apple.com/lookup?id={ident}&country={cc}")
        res = (json.loads(body).get("results") or [None])[0]
        if res:
            art = (res.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
            name = {"track": res.get("trackName"), "album": res.get("collectionName"),
                    "artist": res.get("artistName")}.get(kind)
            if name:
                return name, ("Artist" if kind == "artist" else res.get("artistName") or ""), ("" if kind == "artist" else art)
    _, page = _get(info["url"], timeout=12)     # playlists, stations: the page's own tags
    title = re.sub(r"\s+on Apple Music$", "", _meta(page, "og:title"))
    return title, "", _meta(page, "og:image")


def _soundcloud(link, kind):
    _, body = _get("https://soundcloud.com/oembed?format=json&url=" + _up.quote(link, safe=""))
    d = json.loads(body)
    raw, author = (d.get("title") or "").strip(), (d.get("author_name") or "").strip()
    image = d.get("thumbnail_url") or ""
    if kind == "artist":
        return raw or author, "Artist", image
    title = raw
    if author and raw.lower().endswith(" by " + author.lower()):   # "Flickermood by Forss"
        title = raw[: -len(" by " + author)].strip()
    return title, author, image
