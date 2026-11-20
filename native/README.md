# Music Room — native macOS app build

A self-contained `Music Room.app` produced by PyInstaller. Embeds Python
and every PyPI dependency the project uses (Flask, pywebview, librosa,
pygame, mutagen, numpy / scipy / Pillow). The user's project source and
data still live in the project folder, so:

- **No code changes** in the rest of the repo
- **No risk to library.db**, voice notes, moodboard, ambient, etc.
- Upgrades to the `.app` and upgrades to the source happen independently

If the build fails or breaks, the existing `./start.sh` /
`~/Desktop/Music Room.command` / current `~/Applications/Music Room.app`
shell wrapper all keep working unchanged.

## What's in the bundle

```
Music Room.app/
├── Contents/
│   ├── Info.plist                         macOS app metadata
│   ├── MacOS/music-room                   the launcher (arm64 native)
│   ├── Frameworks/                        embedded Python + every PyPI dep
│   └── Resources/                         icon (none yet), data files
```

What is **not** in the bundle and stays in `~/Projects/music-room/`:

- `app.py` and every other Music Room `.py` module
- `templates/`, `static/`
- `library.db`, `voice_notes/`, `static/moodboard/`, `static/ambient/`
- `exports/`, any user-added audio

The launcher (`launcher.py`) `cd`s into the project folder before importing
`app`, so every relative path inside `app.py` resolves exactly as it does
when you run `./start.sh`.

## Build

```bash
# from the project root
cd native
../venv/bin/pyinstaller music-room.spec --clean --noconfirm
```

Produces:

- `native/dist/Music Room.app` — the bundle (drag to `/Applications` to install)
- `native/build/` — PyInstaller scratch, safe to delete after a successful build

Build time on Apple Silicon: ~45 seconds. Output bundle: ~247 MB
(dominated by scipy + librosa + numpy).

## Override the project location

By default the launcher looks for the project at `~/Projects/music-room`.
Override with an environment variable:

```bash
MUSICROOM_HOME=/path/to/music-room open native/dist/Music\ Room.app
```

## Override the port

```bash
MUSICROOM_PORT=5180 open native/dist/Music\ Room.app
```

If the preferred port is already taken, the launcher falls back to a free
ephemeral port automatically (so two copies of the app won't fight each
other).

## Known limitations

- **Code signing is ad-hoc.** Gatekeeper will warn on first launch from
  Finder (right-click → Open the first time). Distributing to other Macs
  needs a Developer ID and proper signing/notarisation.
- **No icon yet.** Bundle ships with the default app icon. Drop a
  `.icns` next to the spec, set `icon=` in the `BUNDLE()` block, rebuild.
- **Whisper / Torch excluded.** Voice-note transcription falls back to
  "not configured" inside the bundled app. Remove those names from the
  `excludes` list in `music-room.spec` if you want them — at the cost of
  ~2 GB more in the bundle.
- **Project folder still required.** The app bundles Python + deps but
  reads source + data from the project folder. Truly portable distribution
  (one Mac → another with no source checkout) would need bundling the
  Music Room source too and pointing `app.py`'s paths at
  `~/Library/Application Support/Music Room/`.

## Clean a stale build

```bash
rm -rf native/build native/dist
```

## How it actually starts

1. macOS Launch Services double-clicks `Contents/MacOS/music-room`.
2. PyInstaller's bootloader unpacks the embedded Python.
3. `launcher.main()` runs:
   - `cd ~/Projects/music-room` (or `$MUSICROOM_HOME`).
   - Adds it to `sys.path`.
   - `from app import app` — imports the real Flask object.
   - Starts Flask on a background thread on port 5177 (or any free port).
   - Polls `http://127.0.0.1:<port>/` until it responds.
   - Calls `webview.create_window(...)` then `webview.start()`.
4. The window is a real macOS WebKit view — Cmd+Q quits, dock icon
   appears, AppleScript `tell application "Music Room" to quit` works.
