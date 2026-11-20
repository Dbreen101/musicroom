# Helping with the Music Room

Thank you. A few things first.

## How changes go in

- The Music Room's `main` branch is protected. Nobody pushes to it directly:
  every change is a **pull request**, and it goes in only once David (the
  Music Room's maker) has approved it.
- Approved changes reach people in a **release** — a tagged version with the
  apps on the Releases page. Every release is kept, so any of them can be
  brought back if a newer one goes wrong.
- So: fork the repo, make your change on a branch, open a pull request. Small
  ones are easiest to say yes to.

## What is most welcome

1. **Plug-ins** (`plugins/<your-plugin>/`) — new ways of exploring and
   discovering music. Read [docs/PLUGINS.md](docs/PLUGINS.md). A plug-in that
   comes with the app is reviewed like any code.
2. **Themes** — a theme is a small JSON file of colours ([docs/THEMES.md](docs/THEMES.md)).
3. **Fixes** — something that's broken, with a test that shows it fixed.

Changes to the heart of the Music Room — accounts, money, borrowing, the
rooms server, how files are stored, what plug-ins may see — need a good reason
and will be looked at closely. Please open an issue and talk about it first.

## The house style

- **Plain English** in everything a person reads: short sentences, ordinary
  words, no jargon. Labels say what a thing does.
- **The look is "the working document"**: the page's paper, ink, hairlines,
  square corners, one red for what is chosen; Instrument Serif for names, IBM
  Plex Mono for everything else. Use the theme's colours (`var(--bg)`,
  `var(--text)`, `var(--muted)`, `var(--border)`, `var(--red)`), never fixed
  ones, so Paper and Ink both hold.
- **No machine taste in the Music Room itself.** It never decides for you what
  sounds like what. Rules you can read ("same label", "within two years") are
  fine. A plug-in may do things its own way — and must say what it does.
- **Nothing is deleted for real** when it can be moved aside instead.

## Running the tests

```bash
./venv/bin/python test_gr_server.py      # the rooms server
./venv/bin/python test_gr_master.py      # accounts, approvals, reports
./venv/bin/python test_plugins.py        # plug-ins and the app's guards
```

Each test file makes its own throwaway data and needs no network. Run the ones
that touch what you changed, and say which in your pull request.

## Never put in a pull request

- Music, pictures or words you don't have the rights to share.
- Passwords, keys, account codes, or anyone's personal details.
- Code that sends data anywhere the person using the app didn't ask for.

By sending a pull request you agree that your change is shared under the
project's licence, the GNU AGPL-3.0, and that you have the right to share it.
Everyone taking part follows the [house rules](HOUSE_RULES.md).
