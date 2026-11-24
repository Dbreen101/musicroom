# templates/

## OVERVIEW
48 Jinja pages rendered by `app.py` routes; each is a standalone HTML document carrying its own inline CSS + JS (score 13: file count, symbol density, every route renders here).

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Track detail panel, Mála tools, artwork lightbox | `place.html` (9.7k lines) | `renderTrackPanel` ~L3560-6485; Mála ~L6924-8437; lightbox ~L8550-9228; iframe boot ~L9243-9328 |
| 3D room hub (Three.js, grid, filters, piles, structures) | `room3d.html` (6.1k) | inline ES module L1380-6064; `window.MRRoom`, `MRRoomSync`, `openTrack`, `MR_TIP` |
| Explore feed / wall / plug-ins tab | `explore3d.html` | mounts `RecordShop`, `ExploreGlobe`, `ExploreMap`, `PluginsHost` |
| Forest (2D / 3D) | `forest.html`, `forest3d.html` | use `ForestTrees`, `ForestStructures`, `place_illustration.js` |
| Listening desk / canvas / compose | `listening.html`, `listen_canvas.html`, `compose.html` | `/listen`, `/listen/canvas`, `/listen/compose` |
| Batch analysis jobs | `analyse.html` | start/stop/poll per batch |
| Help + deep-link anchors | `help.html` | `#room`, `#player`, `#mala`, `#glossary`...; linked from ~29 navs and `MR_TIP` steps |
| Green Room nav partial | `_gr_nav.html` | included by master, basket, subscribe, house_rules, grupa |
| Markdown-to-page shell | `house_rules.html` | `/house-rules` and `/plugins/how` (renders docs/PLUGINS.md) |

## CONVENTIONS
- No base template: only 6 files use `{% include %}`/`{% extends %}`. Shared chrome = script tags (`gr_nav.js`, `theme.js`, `feedback.js`, `seinnteoir.js`).
- Head order is load-bearing: `style.css` -> `{{ theme_head|safe }}` -> page `<style>` -> `ui.css` LAST (`place.html` also adds `panel_gr.css` after `ui.css`).
- Context processor (`app.py` ~L1110) gives every page `is_3d`, `is_gr`, `is_low_power`, `theme_head`. `theme_head` also sets `html.is-gr` + `window.MR_GR` in Green Room.
- Inline handlers (`onclick="fn()"`) call top-level page functions; renaming a function means grepping the markup and template-literal HTML.
- `place.html` doubles as embedded UI inside `room3d.html` iframes:
  - `?panelonly=1&track=<id>` = panel only; `loadTracks()` skipped, so `currentTracks` is empty -> use `_panelTrack`/`_panelFiles`.
  - `?mala=<tool>&toolonly=1` = one Mála tool; wrapped `close*` posts `mr-tool-closed`.
  - `?list=1` bypasses the `MUSICROOM_3D=1` redirect to `/room/<id>`.
- postMessage protocol `place.html` <-> `room3d.html`: `mr-open-lightbox`, `mr-handoff-if-playing`/`mr-handoff-done`, `mr-track-gone`, `mr-cover-changed`, `mr-lightbox-closed`, `mr-tool-closed`, `mr-open-room`. Change both sides together.
- Hand-kept mirrors (no import): `place.html` panel <-> `static/js/r3d_panel.js`; its lightbox <-> `mr_lightbox.js`; `PLACE_MOODS` <-> `r3d_atmosphere.js`; `RECORD_FONTS` <-> `record_fonts.css`; Camelot `NOTE_PC` <-> `camelot.py`.
- `window.MR_NATIVE_PANEL = false` in `room3d.html`: the room uses the iframe panel. The native port is a reverted experiment.
- Dates render `DD/MM/YYYY` (`toIeDate`). Sound cards show percentiles, never raw DSP numbers.
- Legacy palettes still live in explore/forest/place_map/learn/worldmap/my_room/popout pages. `ui.css` restyles them, so don't "fix" them piecemeal.

## ANTI-PATTERNS
- Cueing (`/api/seinnteoir/add`) must send `autostart: false`, both in the place panel and in the room.
- Never play borrowed Green Room records in page `<audio>`; route them through `playBorrowedInPlayer()` -> Seinnteoir.
- Never rewrite `#player-bar` innerHTML on audio error; update `#player-track-info` only.
- Keep the `<!-- LINKS -->`, `<!-- FILE VERSIONS -->`, `<!-- ANALYSIS -->`, `<!-- GENRES -->`, `<!-- SAMPLES`, `<!-- TAGS -->`, `<!-- LIVES IN -->`, `<!-- DANGER ZONE -->` comments in `renderTrackPanel`: `trimPanelForTrial()` slices on them.
- Drive unplugged: mark records `resting` (`audio_status='missing'`), never drop them from the room (`room3d.html` ~L2151).
- `MRRoom.applyTint`: mutate `_bgNow`/`_bgColor`, never `.copy()` into `scene.background` (it may be a texture).
- No-art sleeve colours: lerp in sRGB 0-255, not `THREE.Color` linear space.
- No literal hex in 3D scenes; read `MRTones.read()`.
- Studio DAW session files are linked, never moved. Removal = quarantine/Trash, never a hard delete.
- Known debt: `place.html` defines `deleteSticker` twice (L9224 is shadowed by L9235, which calls a missing `loadStickers()`), and `toggleCludach` (L9233) is a dead stub.

## VERIFY
No test renders templates. Run the backend tests for the APIs you touched (`tools/run_tests.py test_detail_notes test_covers test_structures ...`), then check the page in the browser in both themes (`?theme=light|dark`) with `__contrast(3)` and `__chk()`. Check `/place/<id>?list=1` and `/place/1?track=<tid>&panelonly=1`.
