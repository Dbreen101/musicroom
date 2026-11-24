# static/js/

## OVERVIEW
33 plain browser scripts loaded by `<script src>`. Each one is an IIFE that publishes one `window.*` namespace (score 13: export count, cross-template centrality).

## WHERE TO LOOK
| Global | File | Consumers (approx) | Role |
|--------|------|--------------------|------|
| `Seinnteoir` | `seinnteoir.js` (1.5k) | 41 files | persistent server-side player / cassette bar / queue; lazy-loads `deeplisten.js`, `snt_embed.js` |
| `__mrThemeHost` | `theme.js` | 43 | theme switching host |
| (nav/footer), `grNavCount`, `grTrack` | `gr_nav.js` | 39 | shared nav + Green Room counters |
| `__mrFeedbackMounted` | `feedback.js` | 29 | feedback widget |
| `AudioCoord` | `audio_coord.js` | 23 | one audible player across tabs: localStorage `mr_audio_owner_v1` + BroadcastChannel `mr-audio-coord-v1` |
| `rtGo(href)` | `room_transition.js` | 17 | page-transition link interceptor; skip with `data-no-transition` |
| `MR_TIP` reader | `mr_tips.js` | 10 | guided tours; page sets `window.MR_TIP` |
| `GrupaUI` | `grupa_ui.js` (1.2k) | 7 | grúpa views: grupa, public_room, room3d, explore3d |
| `MRTones.read/mix` | `page_tones.js` | 4 | CSS tokens -> scene colours |
| `MRSoftPalette` | `soft_palette.js` | 3D scenes | per-launch tint, blended into the tones |
| `mrChoosePath`, `mrChooseInto` | `path_picker.js` | 5 | native chooser via `/api/choose-path` |
| `SimShop` | `sim_shop.js` | 4 | shop/room playback + quotes |
| `RecordShop` | `record_shop.js` | explore3d | record shopping (crates, tickets) |
| `ExploreGlobe`, `ExploreMap` | `explore_globe.js`, `explore_map.js` | explore3d, my_room | globe; Lambert isles map (`pure` = Node-testable) |
| `MRTrackPanel` | `r3d_panel.js` | room3d | native panel port, OFF (`MR_NATIVE_PANEL=false`) |
| `MRLightbox` | `mr_lightbox.js` | room3d, r3d_panel | artwork lightbox port of `place.html` |
| `MRRoomCanvas`, `RoomBlocks` | `room_canvas.js`, `room_blocks.js` | room3d / my_room, public_room | room layouts |
| `MRAtmosphere` | `r3d_atmosphere.js` | room3d | needs `window.MRRoom` host; mirrors `PLACE_MOODS` |
| `ForestTrees`, `ForestStructures` | `forest_trees.js`, `forest_structures.js` | forest pages | procedural scenery |
| `openEisteacht` | `deeplisten.js` | room3d, seinnteoir | deep listening; init guard `__deeplistenInit` |
| `MRExport`/`MRMenu`, `PluginsHost`, `MusicRoom` | `mr_export.js`, `plugins_host.js`, `plugin_runtime.js` | room3d / explore3d / plug-in frame | exports; plug-in host and runtime |

## CONVENTIONS
- No modules, no imports. Dependencies are implicit globals plus host-page DOM ids, so load order in the template matters.
- Idempotence guards (`__rtInstalled`, `__deeplistenInit`, `__mrFeedbackMounted`): scripts may be included twice or lazy-loaded.
- All calls are same-origin `/api/...` fetches. Playback state lives on the server (`/api/seinnteoir/*`); this file set only drives it.
- Desktop WebView localStorage may not survive a relaunch. Durable prefs go through `/api/settings` (or `map_look.py` for the map skin).
- Ports of `place.html` code (`r3d_panel.js`, `mr_lightbox.js`, `r3d_atmosphere.js`) are hand mirrors; edit both sides.

## PLUG-IN BOUNDARY
- `plugins_host.js` (in explore3d) creates `<iframe sandbox="allow-scripts">`, then answers `{mr:'plugin', type:'call'}` messages only for the plug-in's agreed `wants`.
- `plugin_runtime.js` runs inside the frame and exposes a frozen `MusicRoom` (`ready`, `catalogue`, `rooms`, `grupai`, `library`, `makeCrate`, `openRoom`, `say`, `cover`, `el`). Calls time out after 30s.
- The frame CSP comes from `plugins.py:frame_csp`. Covered by `tools/run_tests.py test_plugins`.

## ANTI-PATTERNS
- Cue = `autostart: false`; never start sound on queue.
- `/toggle` flips the real playback state, so never "toggle" twice to sync (`deeplisten.js` ~L419).
- Exports that Finder reveals must never use `<a download>` (`mr_export.js` ~L60).
- No literal hex in scene code; use `MRTones.read()`.

## TESTS
`tools/run_tests.py test_globe test_isles_map` run JS under Node. Also `test_plugins`, `test_grupa`, `test_deck_once`, `test_record_shop`. Everything else is checked in the browser.
