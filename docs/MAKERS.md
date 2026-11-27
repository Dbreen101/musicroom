# Making things for the Music Room

The Music Room works like Ableton Live. The app is finished, and you add to it.
Ableton takes devices and themes; the Music Room takes four things. You make them
anywhere on your computer, and the app takes them in with its own buttons. You
don't need the app's code to do it, and nobody makes their own version of the app.

| | what it is | who sees it | how it comes in |
|---|---|---|---|
| **A plug-in** | a folder: `plugin.json`, `main.js`, `style.css` | you, in Explore → Plug-ins | **Explore → Plug-ins → Add a plug-in…** |
| **The look of your music room** | CSS over your room (or a whole page of HTML) | everyone who visits your room | **My Public Room → Code → Open a file…** |
| **Your own look of the app** | CSS over the app | you, on this computer only | **Settings → Your own look → Open a file…** |
| **A theme** | a `.json` file of colours | you, on this computer only | the **◐** key in the top bar → **Import a theme…** |

These buttons are in Music Room GR **2026.11.27** and newer.

## With Claude Code: the workshop

Ask Claude Code for a plug-in in an empty folder and it may well build a whole new
music app. The workshop stops that.

1. Download **Music.Room.workshop.zip** from the
   [latest release](https://github.com/Dbreen101/musicroom/releases/latest) and
   unzip it anywhere (Documents is fine). If you have the code, the same folder is
   [`workshop/`](../workshop): copy it out of the code first.
2. Open Claude Code in that folder.
3. Say what you'd like: "a plug-in that shows every record for sale by where its
   seller is", "make my room feel like a late-night radio station", "a dark green
   theme".
4. Claude tells you which button to press to see it.

What is in it:

- **`CLAUDE.md`**: everything Claude needs. How plug-ins, room looks, your own
  look and themes work, what each may and may not do, a tested starter plug-in,
  and how to bring each into the app.
- **`.claude/settings.json`**: rules Claude Code itself enforces, whatever Claude
  decides. It can't download the Music Room's code, install anything, start a
  server, call the app's local address, or read or change the app or its data
  folder (your library, your account and your sign-in are there).
- **`How to use this.txt`**: the same steps as above.

Claude only ever writes in the workshop folder. Plug-ins are copied into the app
by the app itself, when you press Add a plug-in… or Look again.

## What each one can do, and what it can't

**A plug-in** runs in a sealed box. It reads only what its `plugin.json` asks for
(the records for sale, the public rooms, the public grúpaí, or your own records),
and only once you have switched it on and seen that list. It can't send anything
anywhere, load anything from the internet, play sound or open web pages. It can
make a crate of records for sale, open someone's music room, and show a line of
text. The full spec: [PLUGINS.md](PLUGINS.md).

- **Add a plug-in…** asks for its folder. The app checks it, copies the kinds of
  file a plug-in can use (up to 2 MB each, 200 files, 20 MB in all), and lists it
  as *yours · not reviewed*.
- **Look again** takes a fresh copy from the same folder and starts the open
  plug-in again: change a file, press it, see the change.
- **Remove** moves the app's copy to the Trash. Your folder stays where it is.

**The look of your music room** is CSS over the room's blocks, so visitors can
still borrow and buy records, open links and grúpaí, and report a room. The room's
page loads nothing from outside the app: pictures are your own uploads (each has
its address on the Images tab, like `/api/gr/asset/12`), record covers, `data:`
addresses and the streaming services' own pictures; fonts are the ones the app
carries or `data:` ones; no scripts; 120,000 characters at most. A whole page of
your own HTML replaces the blocks, runs sealed with no scripts, and shows your
records without the borrow and buy buttons. **Save as a file** keeps what you
have, before you open something new. Your room starts private; the line at the
top of the editor says which it is, and making it public is up to you.

**Your own look of the app** is CSS laid over every page of the app on your own
computer. Nobody else sees it. Nothing in it loads from the internet: the app
takes out `@import` and any `url()` that points at another computer. If a look
hides too much, ⌘⇧0 (Ctrl+Shift+0 on Windows) opens Settings without it.

**A theme** is colours only. The format and the names of the colours:
[THEMES.md](THEMES.md).

## Passing them on

- **A plug-in:** zip its folder and send it. The other person unzips it and
  presses Add a plug-in…. To have one come with the app for everyone, send a pull
  request that adds only `plugins/<id>/` ([CONTRIBUTING.md](../CONTRIBUTING.md));
  Daithí reads it before it goes in.
- **A room look or your own look:** Save as a file, send it, Open a file….
- **A theme:** ◐ → Export this theme, send it, ◐ → Import a theme….

## Changing the app itself

That is a different thing: fixing the Music Room or adding to it, sent to Daithí
as a pull request. Start with [CONTRIBUTING.md](../CONTRIBUTING.md) and
[AGENTS.md](../AGENTS.md).
