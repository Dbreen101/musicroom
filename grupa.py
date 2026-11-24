"""
grupa.py — the grúpa's storage.

A grúpa is a playlist that can hold anything: a record from your room, a
record label, an artist, a place, a set, a Spotify / SoundCloud link (a
track, an album, a playlist, an artist), someone else's music room, any
other link, even another grúpa. The grúpa has a description of what it
is; every element can carry a note on why it is there.

Two tables. `ensure()` creates them when missing — migrate.py calls it, and
so does the app the first time a grúpa is touched (the dev launchers don't
all run migrate.py).
"""

KINDS = ("track", "label", "artist", "place", "set", "room", "grupa", "stream", "link")

DDL = (
    """CREATE TABLE IF NOT EXISTS grupa (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS grupa_items (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        grupa_id    INTEGER NOT NULL REFERENCES grupa(id) ON DELETE CASCADE,
        position    INTEGER NOT NULL DEFAULT 0,
        kind        TEXT NOT NULL,   -- track | label | artist | place | set | room | grupa | stream | link
        ref_id      INTEGER,         -- the local row: a track, place, set or grúpa
        ref_key     TEXT,            -- a name or handle: a label, an artist, a room
        url         TEXT,            -- a stream or any other link
        source      TEXT,            -- spotify | soundcloud | youtube | …
        stream_type TEXT,            -- track | album | playlist | artist | …
        title       TEXT,            -- kept as it read when added (shown if the thing goes away)
        subtitle    TEXT,
        image       TEXT,
        note        TEXT DEFAULT '', -- why it is here
        added_at    TEXT DEFAULT (datetime('now')),
        by_ids      TEXT DEFAULT '', -- a stream: the service's ids for who it is by (the AI-made check)
        duration_sec REAL            -- a stream: its length, when the service says
    )""",
    "CREATE INDEX IF NOT EXISTS idx_grupa_items_g ON grupa_items(grupa_id, position)",
)


# columns added after the first release of the tables (2026-11-13)
ADDED = (
    ("grupa_items", "by_ids", "TEXT DEFAULT ''"), ("grupa_items", "duration_sec", "REAL"),
    # 2026-11-15 — a grúpa's own face, and whether others may see it
    ("grupa", "cover_kind", "TEXT DEFAULT ''"),      # '' = the look all grúpaí share · 'text' = its own type and colour · 'item' = a picture from one of its elements
    ("grupa", "cover_item", "INTEGER"),              # grupa_items.id, when cover_kind = 'item'
    ("grupa", "cover_font", "TEXT DEFAULT ''"),
    ("grupa", "cover_bg", "TEXT DEFAULT ''"),
    ("grupa", "cover_ink", "TEXT DEFAULT ''"),       # 2026-11-23 — its own colour of writing ('' = chosen to suit the ground)
    ("grupa", "is_public", "INTEGER DEFAULT 0"),     # off unless its owner turns it on
    ("grupa", "public_dirty", "INTEGER DEFAULT 0"),  # changed since it was last sent to the rooms server
    ("grupa", "public_error", "TEXT DEFAULT ''"),    # why the last send didn't go, in plain words
    ("grupa", "public_at", "TEXT"),                  # when the rooms server last took it
    # 2026-11-16 — a grúpa as a folder of files, to drag into other programs (grupa_folder.py)
    ("grupa", "folder_path", "TEXT"),                # where its folder was last made
    ("grupa", "folder_at", "TEXT"),                  # and when
)

# ── a grúpa's cover ──────────────────────────────────────────────────────────
# By default a grúpa's cover is its NAME, set in type on a ground of colour —
# one look shared by all of them (the app's display serif on the page's own
# paper, until its owner chooses otherwise). A grúpa can have a look of its own,
# or wear the picture of one of the things in it (Daithí, 2026-11-15).
# Only faces the app carries itself are offered, so a cover reads the same on
# every laptop (static/css/record_fonts.css, deck_fonts.css).
FONTS = ("Instrument Serif", "IBM Plex Mono", "Fraunces", "Young Serif", "Sorts Mill Goudy", "Nyght Serif",
         "Bagnard", "Basteleur", "Le Murmure", "League Gothic", "Bricolage Grotesque", "Apfel Grotezk")
SWATCHES = ("#f2efe8", "#161513", "#c9412f", "#d8c7a0", "#b4673f", "#7c8b69", "#34557e", "#5a3b49", "#c8c3b6")
_PAPER, _INK = "#f2efe8", "#161513"


def clean_hex(value):
    """'#abc' / 'AABBCC' / '#aabbcc' → '#aabbcc'; anything else → ''."""
    v = str(value or "").strip().lstrip("#").lower()
    if len(v) == 3 and all(c in "0123456789abcdef" for c in v):
        v = "".join(c * 2 for c in v)
    if len(v) == 6 and all(c in "0123456789abcdef" for c in v):
        return "#" + v
    return ""


def ink_for(bg):
    """The colour words are set in on this ground: ink on a light one, paper on
    a dark one (by how bright the ground looks, not by its hue)."""
    h = clean_hex(bg)
    if not h:
        return ""
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return _INK if lum > 0.18 else _PAPER      # 0.18 = where ink and paper read equally well; each side takes the clearer one


def clean_font(value):
    """A face from FONTS, or '' (never a name that came from outside)."""
    v = str(value or "").strip()
    return v if v in FONTS else ""


def cover_of(row, look, item_image=None):
    """How a grúpa's cover should be drawn → a dict the page can use as is.
    `row` = the grúpa (cover_kind / cover_item / cover_font / cover_bg);
    `look` = {'font', 'bg'}, the look they all share; `item_image(item_id)` →
    the picture of that element, or '' when it has none / it has gone.
      {'kind': 'image', 'image': url, 'item': id}
      {'kind': 'text', 'own': bool, 'font': str, 'bg': '#…' | '', 'ink': '#…' | ''}
    An empty 'bg' means the page's own paper (it follows the light / dark theme)."""
    kind = (row.get("cover_kind") or "").strip()
    if kind == "item" and row.get("cover_item") and item_image:
        img = item_image(row["cover_item"])
        if img:
            return {"kind": "image", "image": img, "item": row["cover_item"]}
    own = kind == "text"
    font = (clean_font(row.get("cover_font")) if own else "") or clean_font(look.get("font")) or FONTS[0]
    bg = (clean_hex(row.get("cover_bg")) if own else "") or clean_hex(look.get("bg"))
    ink = clean_hex(row.get("cover_ink")) if own else ""
    return {"kind": "text", "own": own, "font": font, "bg": bg, "ink": ink or ink_for(bg)}


def ensure(cursor):
    """Create the tables if they aren't there, and add any column a table made
    earlier is missing. Returns True when it made the tables."""
    had = cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='grupa'").fetchone()
    for sql in DDL:
        cursor.execute(sql)
    for table, col, decl in ADDED:
        cols = [r[1] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    return not had
