# The ready-made app

PyInstaller turns the Music Room into an app that needs nothing else on the
computer: Python, every library, ffmpeg and the Music Room's own code (as
`mrsrc`, read-only) are all inside it.

| | builds | with |
|---|---|---|
| Mac, Apple Silicon | `native/build.sh` | `music-room.spec` |
| Mac, Intel | `native/build-intel.sh` (under Rosetta, its own x86_64 venv) | `music-room.spec` |
| Windows | GitHub Actions, on every release tag (`.github/workflows/windows.yml`) | `music-room-win.spec` |

For a release, `tools/release.sh` runs the two Mac builds itself
([docs/SERVER.md](../docs/SERVER.md)). First time on a Mac:
`venv/bin/pip install pyinstaller`.

## How it starts

`launcher.py` is the app's entry point:

- **Data** lives in `~/Library/Application Support/<name>` on a Mac and
  `%APPDATA%\<name>` on Windows. `<name>` is "Music Room", or the build's own
  (`MR_DATA_NAME`, "Music Room GR" for the Green Room). `MUSICROOM_DATA`
  overrides it.
- **Baked settings**: a build can carry defaults (`baked_env.py`: the Green
  Room switched on, its server's address). The environment still wins.
- It makes or updates the database, starts Flask on port 5177 (or the next
  free one; `MUSICROOM_PORT` to choose) and opens the window.
  `MUSICROOM_HEADLESS=1` serves without a window (CI uses it).
- Importing and analysing run as `--mr-worker`: the app starts itself again,
  invisibly, with no Dock icon.

From the code, `./run_gr.sh` (or `run_gr.bat`) goes through the same launcher.

## Known limits

- Not signed by Apple or Microsoft yet: macOS and Windows warn the first time
  (`Read me first*.txt` says how to open it anyway).
- Voice-note transcription (Whisper) is left out; it would add about 2 GB.
