# The Music Room

A place for your records, and a way into everyone else's.

The Music Room is a desktop app for people who own music. Your own files stay
on your own laptop: you see them as a room of records, tag them, make grúpaí
(playlists that hold anything — records, streams, links, other people's
rooms), and play them through one deck. Beside that, a shared **rooms server**
lets artists, labels, shops, venues and listeners make public rooms, sell and
lend records, and find music the way you would in a record shop: crates, the
counter, listening blind.

It is being tried first at the **Green Room**, a builder residency, by twenty
fellows, with the server running on one Mac on the residency's Wi-Fi. All
money in this trial is play money.

The code is open under the **GNU AGPL-3.0** (see [LICENSE](LICENSE)): you may
read, use and change it, and if you run a changed version for other people,
you must share your changes too.

---

## Get it

**The app, ready made** — from the [Releases](https://github.com/Dbreen101/musicroom/releases) page:

- **Mac**: *Music Room (Apple Silicon).zip* for Macs from late 2020 on, *Music
  Room (Intel).zip* for older ones (Apple menu → About This Mac → Chip). Unzip,
  drag it to Applications, open it. Because it isn't signed by Apple yet, the
  first time macOS stops it: open **System Settings → Privacy & Security**,
  scroll down, press **Open Anyway**.
- **Windows PC** (Windows 10 or 11): *Music Room (Windows).zip*. Unzip it, open
  the *Music Room* folder, double-click **Music Room.exe**. The first time,
  Windows may say *Windows protected your PC*: press **More info**, then **Run
  anyway**.

**From the code** (if you want to change it, or make plug-ins):

```bash
git clone https://github.com/Dbreen101/musicroom.git
cd musicroom
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./run_gr.sh
```

On Windows: `py -3.12 -m venv venv`, `venv\Scripts\pip install -r requirements.txt`,
then `run_gr.bat`.

Python 3.11 or 3.12. Your library and settings are kept in
`~/Library/Application Support/Music Room GR/` on a Mac and
`%APPDATA%\Music Room GR` on Windows — never in the code folder.

Either way, the first page is the front door: make an account (everyone starts
as a listener), read and agree to the [house rules](HOUSE_RULES.md), and
you're in. If the app can't find the server, press *change* under the form
and type the address you were given.

---

## How it is put together

| | runs on | holds |
|---|---|---|
| **the app** (`app.py`, `templates/`, `static/`) | your laptop, at `127.0.0.1` | your library, your grúpaí, your settings, your look |
| **the rooms server** (`gr_server.py`, `gr_shop.py`, `gr_master.py`) | one shared Mac | accounts, records for sale, public rooms and grúpaí, record shopping, reports, feedback |

The app talks to the server with your account's key; the server only ever
answers you about you, and about what others have made public. The app answers
only its own pages: another web page, a plug-in or someone's public room can't
make it do anything.

---

## What you can change

- **The look of your own app** — a theme (◐ in the top bar; a theme is a small
  file of colours, [docs/THEMES.md](docs/THEMES.md)), the map's skin (Explore →
  Map → Look), and your own CSS over the whole app (Settings → *Your own look*).
- **Your public room** — My Public Room: blocks, pictures, your own CSS, even a
  whole page of your own. It is shown to others in a sealed frame that can only
  play music from the Music Room and the streaming services' own players.
- **Plug-ins** — new ways of exploring and discovering music, in Explore →
  Plug-ins. Each runs in a sealed box and sees only what it asks for and you
  agree to. How to make one: [docs/PLUGINS.md](docs/PLUGINS.md).
- **The Music Room itself** — send a pull request. See below.

## What nobody can do

- See or change another person's account, library, wallet, borrows or
  unpublished work.
- Get the audio of a record they haven't borrowed or bought (record shopping
  plays a lower-quality copy, only inside a crate, the counter or blind).
- Put a record up for sale without saying they hold its rights — and it goes
  out only after the Music Room has looked at it.
- Change the Music Room for everyone without the maker's approval.

Anyone can report a room, a record or a public grúpa; the Music Room's master
account looks at every report.

---

## Helping

- Something broken, or an idea: the feedback button in the app, or an
  [issue](https://github.com/Dbreen101/musicroom/issues).
- Code, plug-ins, themes: [CONTRIBUTING.md](CONTRIBUTING.md).
- A security problem: [SECURITY.md](SECURITY.md) — please not in public.
- Running a rooms server, releases and stepping back to an older one:
  [docs/SERVER.md](docs/SERVER.md).

Third-party code and fonts, and their own licences: [THIRD_PARTY.md](THIRD_PARTY.md).
