# Themes — the Music Room's skin

A theme is a small JSON file of colours. Like a skin for a controller: it
changes how the app looks, not what it does. Two come built in (Dark, Light);
anyone can make more and pass them around.

## Using one

The ◐ button in the top bar lists the themes. Pick one; it's remembered on
this machine. "Match the system" follows your Mac's light/dark setting.
"Import a theme…" takes a `.json` file; "Export this theme" writes the
current one out so you can change it.

## Making one

1. Export the theme closest to what you want.
2. Open the file in any text editor. It looks like this:

```json
{
  "name": "Seafoam",
  "author": "you",
  "scheme": "dark",
  "vars": {
    "bg": "#0b1412",
    "surface": "#101c19",
    "text": "#e6f0ec",
    "accent": "#7fd3b8",
    "gold": "#7fd3b8"
  }
}
```

3. Change any values. Leave out any you don't care about — the Dark theme's
   values stand in.
4. Import it. Same name → replaces the old version.

`scheme` is `light` or `dark` (it tells the system which way form controls
should go). If you leave it out, it's guessed from `bg`.

## The tokens

| token | what it colours |
|---|---|
| `bg`, `bg-floor` | the page, the deepest background |
| `surface`, `surface2` | cards and panels, raised panels |
| `border`, `border2` | hairlines, stronger hairlines |
| `text`, `muted`, `muted2` | words; quieter words; quietest |
| `accent`, `accent-dim` | the one highlight colour; its soft wash |
| `gold`, `gold-soft`, `well` | the room's gold, its pale version, the Well |
| `oxblood`, `lapis`, `ochre` | the old illuminated-manuscript accents, still used here and there |
| `danger`, `warning` | red and amber states |
| `sheet`, `nav-bg`, `pill-ink`, `shadow` | the content panel, the top bar, the text on an active pill, the shadow tint |
| `ink` | the 3D room's chrome text |
| `gr-bg`, `gr-surface`, `gr-line`, `gr-ink`, `gr-muted`, `gr-faint`, `gr-accent`, `gr-accent-ink` | the newer pages: login, intro, subscription, basket, public rooms, the designer |
| `map-sea`, `map-land`, `map-line`, `map-text` | the Map in Explore, while it wears the skin that follows the app: the sea, the land, the lines (coast, rivers), the writing (names, marks). Leave them out and the map is worked out from `bg` and `text` |

Colours can be hex, `rgb()`, `rgba()`, or `hsl()`. Fonts aren't part of a
theme yet — that's next.

## The map has skins of its own

The Map in Explore (Ireland and Britain) is dressed separately from the rest of
the app: open **Look** in the map's left panel and pick a **skin**. Each one is
shown as a small picture of the same stretch of coast.

| skin | what it is |
|---|---|
| As the app | the app's own colours — it changes when the theme does. This is the one a theme's `map-…` tokens colour |
| Paper, Ink | the app's two looks, kept whatever the app is wearing (a dark map in a light app, or the other way round) |
| Solid land, Solid sea | the land, or the sea, filled in with the app's ink |
| Dotted, Ruled | the land in dots, or in ruled lines. They are fixed to the ground: going closer, more come up in the gaps |
| Chart, Blueprint | colours of their own: a pale sea and a warm land; light lines on blue |
| Your own | four colours you choose — the sea, the land, the lines, the writing — and how the land is filled (plain, dotted, ruled). It starts as a copy of the skin you had on |

The choice is remembered by the app (not only by the page), together with
which way is up and whether towns and rivers are shown. The small map on My
Public Room, where a room's place is set, wears the same skin.

A skin only says four colours and a fill. Everything finer — rivers, loughs,
the far shore, the names of towns, the scale line, the slip a mark's name
stands on — is worked out from those four, and checked so that names and marks
stay readable (`static/js/explore_map.js`: `SKINS`, `tonesFor`). A skin of your
own that makes the writing hard to read says so under its colours; it is still
yours to keep.

## What a theme doesn't touch (yet)

The 3D room and forest keep their own look: a dark canvas with light writing
over it is a scene, not a page, and lightening its chrome alone would make it
unreadable. Theming the scene itself (floor, fog, sky) is a later piece. A
public music room is its owner's design, not the viewer's theme — it only
follows your theme where its owner left the colours unset.
