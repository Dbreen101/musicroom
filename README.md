# The Music Room.

[![Licence: AGPL-3.0](https://img.shields.io/badge/licence-AGPL--3.0-161513)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/Dbreen101/musicroom?label=release&color=161513)](https://github.com/Dbreen101/musicroom/releases)

A place for your records, and a way into everyone else's.

The Music Room is an open-source desktop app for people who own music. Your
files stay on your own laptop as a room of records you can arrange, tag, and
play, without an algorithm deciding for you what sounds like what. Beside your
room sits a shared rooms server where artists, labels, shops, venues, and
listeners put up public rooms, lend and sell records, and find music the way
you do in a record shop: digging through crates, asking at the counter, or
listening blind.

Twenty fellows are trying it first at the Green Room builder residency, with
the server running on one Mac on the residency's Wi-Fi and all money set to
play money.

---

## What you can do

- **Keep your own room of records.** Import MP3 and FLAC folders, edit metadata
  and write tags back into the files on disk, run local BPM, key, and Camelot
  wheel analysis, and play everything through one persistent deck that keeps
  going as you move from page to page.
- **Make grúpaí.** Build playlists that hold almost anything together: records
  from your room, labels, artists, places, sets, Spotify or SoundCloud links,
  other web links, or someone else's public room, each with your own note on
  why it belongs.
- **Shop like a record shop.** Open up to three crates of up to 25 records a
  day, ask or answer a question in plain words at the counter, or hear up to
  ten records a day blind before turning the sleeve over.
- **Borrow or buy records.** Borrow encrypted records to keep playing inside
  the Music Room, buy plain files to own outright, or collect records marked
  exclusive to the Music Room.
- **Open a public room.** Listeners, artists, labels, shops, venues,
  businesses, and digital artists can publish a room, share public grúpaí, and
  place their room on the map or globe.
- **Explore on your own terms.** Follow RSS feeds you choose with readable
  keyword weights and a daily wander slot ([docs/how-explore-works.md](docs/how-explore-works.md)),
  or switch on sandboxed plug-ins made by the community.

---

## Get it

### Ready-made app

Download the latest build from the [Releases](https://github.com/Dbreen101/musicroom/releases) page:

- **Mac**: *Music Room (Apple Silicon).zip* for Macs from late 2020 on, or
  *Music Room (Intel).zip* for older Macs (check Apple menu, About This Mac,
  Chip). Unzip, drag it to Applications, and open it. Because it isn't signed
  by Apple yet, macOS stops it the first time: open **System Settings**, go to
  **Privacy & Security**, scroll down, and press **Open Anyway**.
- **Windows PC** (Windows 10 or 11): *Music Room (Windows).zip*. Unzip it, open
  the *Music Room* folder, and double-click **Music Room.exe**. The first time,
  Windows may say *Windows protected your PC*: press **More info**, then **Run
  anyway**.

More on how the bundled app is built and launched lives in
[native/README.md](native/README.md).

### From source

If you want to change the app, build a plug-in, or send a fix, run it from the
code with Python 3.11 or 3.12:

```bash
git clone https://github.com/Dbreen101/musicroom.git
cd musicroom
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./run_gr.sh
```

On Windows:

```bat
py -3.12 -m venv venv
venv\Scripts\pip install -r requirements.txt
run_gr.bat
```

Your library, settings, and records are kept in
`~/Library/Application Support/Music Room GR/` on a Mac and
`%APPDATA%\Music Room GR` on Windows, never inside the code folder.

Run the test suite before sending changes:

```bash
venv/bin/python tools/run_tests.py
```

Every test creates its own throwaway data and needs no network.

### First sign-in

The first page is the front door: make an account (everyone starts as a
listener), read and agree to the [house rules](HOUSE_RULES.md), and you're in.
If the app can't find the server, press *change* under the form and type the
address you were given.

---

## How it fits together

| | runs on | holds |
|---|---|---|
| **the app** (`app.py`, `templates/`, `static/`) | your laptop, at `127.0.0.1` | your library, your grúpaí, your settings, your look |
| **the rooms server** (`gr_server.py`, `gr_shop.py`, `gr_master.py`) | one shared Mac | accounts, records for sale, public rooms and grúpaí, record shopping, reports, feedback |

Your app talks to the server with your account's key. In return, the server
answers only about your account and what other people have made public. On your
laptop, the app answers only its own pages, so another web page, a plug-in, or
someone else's public room can't make it touch your library.

Nobody else can see your wallet, borrows, library, or unpublished work.
Unbought records in the shop play only as tag-stripped 128k MP3 listening
copies inside a crate, at the counter, or blind. Artists, labels, and shops
must declare they hold the rights before putting a record up for sale, and the
master account checks every new record and every report.

Running a rooms server, cutting releases, and rolling back to an older release
are covered in [docs/SERVER.md](docs/SERVER.md).

---

## Make it yours

- **Themes and map skins.** Pick *Paper* or *Ink* from the `◐` button in the
  top bar, or export a theme JSON file, edit its colour tokens, and import it
  back ([docs/THEMES.md](docs/THEMES.md)). In Explore, open the Map's **Look**
  panel to dress the map in its own skin. Read [docs/DESIGN.md](docs/DESIGN.md)
  for the "working document" look behind Paper, Ink, Instrument Serif, and IBM
  Plex Mono.
- **Your own CSS.** Open **Settings** and go to **Your own look** to lay custom
  CSS over the whole app on your laptop.
- **Your public room.** Shape **My Public Room** with blocks, pictures, custom
  CSS, or a whole page of your own. Others view it inside a sealed frame that
  can play music only from the Music Room and the streaming services' own
  players, such as Spotify and SoundCloud.
- **Plug-ins.** Switch on discovery tools in **Explore**, **Plug-ins**, or
  build your own in `plugins/<your-plugin>/`. Each plug-in runs in a sealed box
  with no network access and sees only what its `wants` list asks for
  (`catalogue`, `rooms`, `grupai`, or `library`) after you agree. Start by
  copying [plugins/thread](plugins/thread) or [plugins/shelves](plugins/shelves),
  and read [docs/PLUGINS.md](docs/PLUGINS.md).

---

## Join in

The Music Room grows best when listeners, artists, designers, and programmers
build around it together. Read [CONTRIBUTING.md](CONTRIBUTING.md) before you
start, and keep to the [house rules](HOUSE_RULES.md).

### Good first contributions

1. **A plug-in.** Try a new way of browsing the catalogue or someone's own
   library without touching core server code. Put a folder in your local
   `plugins/` directory, test it live, and open a pull request to `plugins/`
   ([docs/PLUGINS.md](docs/PLUGINS.md)).
2. **A theme.** Export an existing colour file, tune the palette so text stays
   crisp and readable, and share the JSON ([docs/THEMES.md](docs/THEMES.md)).
3. **A fix with a test.** Pick something broken, fix the cause, and run
   `venv/bin/python tools/run_tests.py` to show it holds.

Changes to the heart of the Music Room (accounts, money, borrowing, file
storage, server rules, or what plug-ins may see) are looked at closely. Open an
issue to talk it through first.

### How pull requests flow

`main` is protected, so nobody pushes to it directly. Fork the repo, make your
change on a small branch, and open a pull request; GitHub runs the test suite
automatically on every PR. David (`@Dbreen101`) reviews and approves every
change before it merges, and approved work goes out in tagged releases that
keep older versions ready if a rollback is ever needed.

### Where to talk

- **Bugs and ideas:** press the feedback button inside the app, or open an
  [issue on GitHub](https://github.com/Dbreen101/musicroom/issues).
- **Security problems:** please don't post them in public. Send a private
  report as explained in [SECURITY.md](SECURITY.md).

---

## Principles

- **Plain English.** Everything a person reads uses short sentences and
  ordinary words. Labels say what a thing does.
- **No machine taste.** The Music Room never decides for you what sounds like
  what. Rules you can read ("same label", "within two years", or your own
  keyword weights) are welcome, and any plug-in with its own logic must say
  plainly how it chooses.
- **Nothing deleted for real.** Removing a record from the Music Room parks its
  files in a *Removed* folder, and you can bring it back any time. Duplicate
  files go to the Trash or Recycle Bin. When a file can't be moved safely, it
  stays where it is.
- **Privacy by default.** Your files and local listening history stay on your
  laptop. Off-device telemetry is off by default, gated behind separate opt-in
  consents, and limited to coarse monthly counts under an anonymous ID that
  changes every month. It never includes titles, file paths, search terms or
  IP addresses.

---

## Licence

Made by David (Daithí) Breen. The Music Room's code is open under the **GNU
AGPL-3.0** ([LICENSE](LICENSE)): you may read, use, and change it, and if you
run a changed version over a network for other people, you must share your
changes too.

Third-party code, map data, and fonts remain under their own licences, listed
in [THIRD_PARTY.md](THIRD_PARTY.md).
