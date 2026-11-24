# static/

## OVERVIEW
Bundled front-end assets: CSS layers, vendored libs, fonts, textures, map data, and dev QA probes. Served via the data-dir overlay route (subtree score 11, distinct domain). JS has its own file: `js/AGENTS.md`.

## STRUCTURE
```
static/
├── css/        # 17 sheets; style.css (base) + ui.css (design layer, loaded last)
├── js/         # 33 window-global page scripts (see js/AGENTS.md)
├── vendor/     # three (module + r128), three/addons, map, gsap, sortable - third-party, don't edit
├── fonts/      # 14 families + ui/; README lists record fonts
├── data/       # isles.json, globe_land.png, source_catalogue.json, feed_registry.json
├── dev/        # contrast.js (__contrast), overlap.js (__chk) - QA only
├── share/      # room_page.html: public room page app.py reads and serves
├── textures/ img/
└── analysis_section.html
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Global restyle / tokens / fonts | `css/ui.css` | linked in 47 files; "changes no behaviour" |
| Base page styles | `css/style.css` (2.7k lines) | linked in 46 files |
| Legacy Explore look | `css/explore-theme.css` | 33 pages still load it |
| Plug-in frame look | `css/plugin_base.css` | `.mr-btn`, `.mr-card`, `.mr-muted`... (docs/PLUGINS.md) |
| Record sleeve fonts | `css/record_fonts.css`, `fonts/README.md` | mirrored by `RECORD_FONTS` in room3d/place |
| Track panel GR overrides | `css/panel_gr.css` | loaded after ui.css by `place.html` |
| Isles map geometry | `data/isles.json` | used by `js/explore_map.js` |
| Contrast / overlap probes | `dev/contrast.js`, `dev/overlap.js` | run `__contrast(3)`, `__chk()` in the console |

## CONVENTIONS
- `/static/<path>` is served by `app.py:_static_overlay` (~L153): the data dir (`mr_paths` DATA_DIR/static: uploaded moodboards, ambient audio, artwork, stickers) wins, and bundled code assets are the fallback. In dev both roots are the same folder.
- No build, bundler, minifier or npm. Files ship as written; ES modules resolve `three` via inline import maps that point at `vendor/three/`.
- The CSS cascade per page is `style.css` -> theme tokens (`theme_head`, from `themes.py` Paper/Ink) -> page CSS -> `ui.css`. `ui.css` uses `:root:root` to outrank page tokens and remaps legacy font vars (`--font-main`, `--gr-serif`...) onto `--f-display`/`--f-mono`.
- Design tokens: `--bg --text --muted --border --border2 --red --surface`, `--f-display` (Instrument Serif), `--f-mono` (IBM Plex Mono), `--ui-r: 0`.
- Class prefixes are per feature (`.ws-*`, `.rec-*`, `.gx-*`, `.rc-*`, `.sh-*`, `.th-*`).

## ANTI-PATTERNS
- No fixed colours in themeable chrome; use the tokens so that Paper and Ink both work.
- No rounded corners, shadows or gradients in new document UI (`ui.css` forces square corners).
- Don't hand-edit `vendor/`. Upgrade a library by replacing the files and keep its licence.
- Media without a licence must not land here (CONTRIBUTING.md).
- Don't put user data in `static/`: uploads go to the data dir, and the overlay serves them.
