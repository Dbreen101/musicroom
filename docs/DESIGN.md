# The look — the working document

Daithí's deck (Oct 2026, "The Music Room — a working document") is the
reference for everything a person sees. The app is that document, page by page.

## The language

- **Paper and ink.** Light = paper `#f2efe8`, ink `#161513`, a muted grey
  `#6e6a61`, hairlines `#c8c3b6`, one red `#c9412f`. Dark = the same document
  turned over: `#161513`, `#f2efe8`, `#9b968a`, hairlines at 18% paper, red
  `#e8554a`. Nothing else. (themes.py `Paper` / `Ink`; every token the sheets
  read, incl. `--red`.)
- **Two faces.** Instrument Serif for every title and every big number
  (`--f-display`); IBM Plex Mono for labels, chrome and reading
  (`--f-mono`; `--f-grotesk` and `--f-body` both point at it). Labels are mono
  caps at `.68rem`, tracked `.1em`. Both bundled, SIL OFL.
- **Hairlines, not boxes.** Rows are divided by 1px rules. Cards are
  hairline-topped entries. The page is the sheet; nothing floats on it.
- **One fill.** The single primary on a view is ink on paper (paper on ink in
  the dark). Everything else is a hairline box or bare text. No shadows, no
  gradients, no rounded corners on anything a document holds. (The deck
  player, the help button and the feedback bubble keep their shapes — they are
  objects, not pages.)
- **Red is for emphasis only** — the deck's "red ink where I am unsure":
  errors, the one word in a heading, a warning label.
- **Furniture.** A page header carries its title at the left and its section
  name at the right in mono caps; a hairline under it. Every scrolling page
  ends in a foot line: THE MUSIC ROOM · the page's name (gr_nav.js). The
  wordmark reads "The Music Room." — the full stop is the deck's.
- **The cover.** The front door is the deck's first slide: the name huge, the
  meta lines in mono, the soft blurred dark shape (paper on dark).

## Where it lives

- `static/css/ui.css` — the one design layer, loaded LAST on every page.
- `static/css/deck_fonts.css` — Plex Mono; Instrument Serif is in
  `record_fonts.css`.
- `themes.py` — the two palettes; custom themes are JSON skins over them.
- `static/css/gr.css`, `explore-theme.css`, `room_canvas.css` — carry the
  same tokens and squared shapes; `room3d.html`/`explore3d.html` hold their
  own dark defaults in the same values.
- `static/js/gr_nav.js` — the section label and the foot line.
- `static/js/page_tones.js` — the page's tones for the two 3D scenes, read
  off the theme tokens (paper / ink / muted / rule / red, whichever way
  round the theme has them).

## The two scenes

The cloud (`room3d.html`) and the forest (`forest3d.html`) are drawn on the
page, not lit. The rule for both: the scene background IS the page colour,
distance is a wash toward the page (fog in the page colour), and everything
in the scene is one of the page's tones.

- **The cloud.** The ground is a ruled sheet (a hairline grid in the rule
  tone, fading into the page). A record with no cover is a sheet lying on
  the page: a hairline edge, its initial in the serif; up close, the artist
  as a mono-caps label and the title in the serif. Ticks in the space are
  mono, muted. The scrim behind an open record is the page colour.
- **The forest.** Sky and ground are the page. Trees are flat: a mid-grey
  canopy (text→bg .58), a lighter crown (rule), an ink trunk. No sun, moon,
  weather, clouds, rain or texture. Each place stands in a hairline ring
  (ink under the pointer). A structure is built as before, then `inkify()`
  reads it back into three tones — dark → ink, mid → muted, light → rule —
  and its lit windows are cut from the page; the Music Room's windows carry
  the one red (rowan and holly keep a few red berries). Labels sit on slips
  of the page: serif name, mono-caps count. Keys are square hairlines.
- Everything the scenes draw takes its colour from `MRTones.read()`; never a
  literal hex in a scene again.

## How to check a page

In the browser console: `__contrast(3)` (static/dev/contrast.js — text against
its first opaque backdrop, must be 0 low) and `__chk()` (static/dev/overlap.js —
blocked, overlapping, duplicated controls). Run both in BOTH themes
(`POST /api/themes/current {"id":"light"|"dark"}` then reload). Remove the `rt`
class from `<html>` before a screenshot, and `gsap.globalTimeline.progress(1)`
on GSAP pages. The front door can be seen while signed in at `/login?preview=1`.
