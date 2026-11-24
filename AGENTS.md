# PROJECT KNOWLEDGE BASE

**Generated:** 2026-11-24T15:09Z
**Commit:** f9417fe
**Branch:** cleanup/optimise

## OVERVIEW
Music Room: local-first desktop music library (Flask + SQLite + Jinja/plain window-global JS, no bundler/npm), wrapped by pywebview/PyInstaller. Plus "Green Room" (GR): separate Flask rooms server (accounts, record shop, public rooms, grúpaí). AGPL-3.0; version in `VERSION`.

## STRUCTURE
```
musicroom/                # FLAT: all modules + all test_*.py at root (no src/, no tests/)
├── app.py                # desktop Flask app, 16k lines; core routes + 9 X.register(app, ...)
├── gr_server.py          # rooms server + CLI; registers gr_shop/gr_master/gr_sim/gr_art
├── green_room.py         # desktop-side HTTP client to rooms server (encrypted borrow cache)
├── migrate.py schema.py  # repeatable non-destructive migration / fresh DB
├── importer.py           # import + analysis CLI
├── desktop.py            # pywebview dev entry only
├── templates/            # 48 standalone Jinja pages -> templates/AGENTS.md
├── static/               # assets, CSS, vendored libs -> static/AGENTS.md
│   └── js/               # 33 IIFE scripts, each a window.X -> static/js/AGENTS.md
├── plugins/              # sandboxed example plug-ins (thread, shelves); spec in docs/PLUGINS.md
├── native/               # real entry launcher.py, PyInstaller specs, build scripts (see native/README.md)
├── tools/                # run_tests.py, release.sh, server.sh, publish_public.py, take_public.sh
└── docs/                 # DESIGN, PLUGINS, THEMES, SERVER, RECOMMENDATIONS (dated advice, not defaults)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Desktop route/page | app.py or a module's `register()` | extracted: plugins, structures, removed, record_shop, sound_out, gr_sim_app, gr_art_app, explore_globe, map_look |
| Rooms server endpoint | gr_server.py, gr_shop/gr_sim/gr_master/gr_art | `register(app, server)` + `ensure(conn)` |
| GR call from desktop | green_room.py | |
| Data paths / env | mr_paths.py | |
| Schema change | migrate.py (+ schema.py) | |
| Import/analysis | importer.py, key_detect.py, camelot.py | |
| Track panel / Mála tools | templates/place.html | also embedded in room via `?panelonly=1`/`?toolonly=1` |
| 3D room hub | templates/room3d.html | |
| Persistent player | static/js/seinnteoir.js, seinnteoir_player.py | `/api/seinnteoir/*` |
| Look/tokens | static/css/ui.css, themes.py, docs/DESIGN.md | |
| Plug-in API | docs/PLUGINS.md, plugins.py (`frame_csp`), static/js/plugin_runtime.js | |
| Packaging | native/*.spec, native/launcher.py | |
| Release/deploy | tools/release.sh, tools/server.sh, docs/SERVER.md | |

## CODE MAP
| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `app.app` | Flask app | app.py | most tests, launcher | `app.app.test_client()` in tests |
| `mr_paths.DATA_DIR/DB_PATH/CODE_DIR` | consts | mr_paths.py | ~26 files | only source of writable paths |
| `mr_text.fold/words/squeeze/slug/holds` | funcs | mr_text.py | 25+ | `fold` = SQLite UDF `mrfold` |
| `mr_ffmpeg.ffmpeg_path()` | func | mr_ffmpeg.py | ~8 | only ffmpeg resolver |
| `trash_util.move_to_trash()` | func | trash_util.py | app, importer | only file-removal gate |
| `green_room.*` | client API | green_room.py | app, gr_*_app, plugins, tests | GRError, borrow, buy, rooms |
| `migrate.run_migration` | func | migrate.py | launcher, tests | |
| `SeinnteoirPlayer` | class | seinnteoir_player.py | app | server-side player |
| `Seinnteoir` | window global | static/js/seinnteoir.js | 41 | |
| `MRTones` | window global | static/js/page_tones.js | all 3D scenes | scene colours |
| `_static_overlay` | Flask route | app.py ~L153 | all /static | data dir first, then code |

## CONVENTIONS
- Injection: desktop modules `register(app, <callbacks: query, query_one, execute, get_setting...>)`; server modules `register(app, server_module)` + `ensure(conn)`, server held as `S`.
- Code vs data: code from BASE_DIR/CODE_DIR (frozen: `mrsrc/`); writable data only via mr_paths. `MUSICROOM_DATA` is literal; portable-drive DB fallback only when no override and no local DB.
- Env: MUSICROOM_DATA, MUSICROOM_PORT, MUSICROOM_3D, MUSICROOM_HEADLESS, MUSICROOM_FFMPEG, MR_GREEN_ROOM=1, MR_GR_VERSION, MR_GR_SERVER, MR_GR_DB, MR_LIBRARY_DB, MR_DATA_NAME, MR_TEMPLATE_RELOAD=1.
- Tests: no pytest/unittest. Each test_*.py is a script (`fails=[]`/`chk()`, temp MUSICROOM_DATA, exit 1 on failure); runner runs them parallel in fresh subprocesses, SDL_AUDIODRIVER=dummy, 600 s each, no network.
- Underscore names are NOT private: tests/modules call `_helpers`; grep usages before renaming.
- Irish names (Seinnteoir, grúpa/grúpaí, Mála) are data contracts; keep them.

## ANTI-PATTERNS (THIS PROJECT)
- Never hard-delete user files: `trash_util.move_to_trash` (returns (False, err), no os.remove fallback). Removed files go to "Removed from Music Room", never re-imported or trashed by dedupe.
- Never call bare `ffmpeg`; use `mr_ffmpeg.ffmpeg_path()`, surface missing. No runtime imageio-ffmpeg (build only).
- No text normalising/slugging outside mr_text; accents fold to base letters.
- `strip_mix_suffix` strips only Original Mix/Version.
- Routine backup never copies audio; full backup only to mounted /Volumes drive.
- Organiser never strands a file at a path no DB row references; unplugged-drive records are marked `resting`, never dropped.
- No user data in checkout; never start a fresh data dir via desktop.py (use native/launcher.py or run_gr.sh).
- Never commit DBs, secrets, unlicensed media, or unrequested network traffic.
- GR listening uses tag-stripped 128 kbps copy, never source; borrow cache stays encrypted.
- No algorithmic "machine taste" recommendations in core; plug-ins must say why each record shows.

## UNIQUE STYLES
- "Working document" look: Paper/Ink tokens (`--bg --text --muted --border --red`), no literal hex (3D: `MRTones.read()`), Instrument Serif + IBM Plex Mono, hairlines, square corners, red only for emphasis. Plain-English UI copy.
- Env flags reshape UI (`MUSICROOM_3D=1` room hub, `MR_GREEN_ROOM=1` trimmed GR UI); details in templates/AGENTS.md.

## COMMANDS
```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python tools/run_tests.py                      # all
./venv/bin/python tools/run_tests.py test_os test_grupa   # named; --jobs 1 serial
./start.sh             # 2D: migrate + app.py (:5177)
./start3d.sh           # 3D (:5180)
./startgr.sh           # dev GR: gr_server :5301 + desktop :5181
./run_gr.sh            # user-style launch via native/launcher.py
python gr_server.py init|add <folder>|covers|invite <name>|accounts|listen-copies|usage|run --port 5301
./native/build.sh ; ./native/build-intel.sh               # arm64 / Rosetta (venv-x86)
tools/release.sh vYYYY.MM.DD "note" ; tools/server.sh deploy|rollback|status|log <tag>
python3 tools/publish_public.py --check
```

## NOTES
- PyInstaller specs (Mac + Win) bundle root *.py, plugins/, templates/, VERSION, HOUSE_RULES.md, docs/PLUGINS.md, static/{css,js,textures,fonts,vendor,data}: new static subdir or root data file -> edit BOTH specs; new dep may need `hiddenimports`.
- No test renders templates: UI changes need browser checks (`__contrast(3)`, `__chk()`, both `?theme=light|dark`).
- HOUSE_RULES.md renders at /house-rules, version-stamped by `gr_master.HOUSE_RULES_VERSION`.
- requirements-x86.txt lacks cryptography (drift risk); openai-whisper unpinned, lazy-loaded.
- CI: tests.yml (macOS, py3.12 + node20) on PR/main; windows.yml on `v*` tags runs a test subset only.
- Private repo -> public: tools/publish_public.py (PRIVATE list); merged public PRs return via tools/take_public.sh.
- feed_registry.py comments point to scripts/update_feed_registry.py; the file is at root.
