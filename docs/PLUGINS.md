# Making a plug-in

A plug-in is a new way of exploring or discovering the music in the Music
Room. It shows up in **Explore → Plug-ins**; whoever uses it switches it on,
and it runs in its own sealed box beside the list.

Two come with the app, and are the best examples to copy:
[`plugins/thread`](../plugins/thread) (start from one record, follow a thread
by label, seller, genre or year) and [`plugins/shelves`](../plugins/shelves)
(every record for sale on shelves you choose).

## The folder

```
plugins/your-plugin/
  plugin.json     who it is and what it may read
  main.js         its code
  style.css       its look (optional)
  …               pictures it carries (png, jpg, svg, webp), other .js / .css files
```

```json
{
  "id": "your-plugin",
  "name": "Your Plug-in",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "One or two sentences on what it does, for the list.",
  "entry": "main.js",
  "style": "style.css",
  "wants": ["catalogue"]
}
```

`id` is the folder's name: a–z, 0–9 and `-`. `wants` lists what it may read,
from these four — ask only for what you need, because people see the list
before they switch it on:

| want | what it gives |
|---|---|
| `catalogue` | every record for sale in the Music Room: title, artist, album, year, genres, label, length, price, whether it has a cover, and who sells it (name, handle, kind, place) |
| `rooms` | the public music rooms: handle, name, kind, words about it, place, how many records |
| `grupai` | the public grúpaí: name, words about it, how many things, who made it |
| `library` | the person's **own** records on their laptop: title, artist, album, year, genres, tags, BPM, key, cover colour |

Nothing else is ever given: no files, no paths, no accounts, nobody's wallet,
borrows or private work.

## Trying it

Put the folder in **your own plug-ins folder** (Explore → Plug-ins → *Show the
folder*; it is `plugins/` inside the app's data folder), press *Look again*,
switch it on and open it. Change a file and press *Look again* (or close and
open the plug-in) to see the change. Your own plug-ins are marked *yours · not
reviewed* and run only in your app.

## What your code can use

Your `main.js` runs after `plugin_runtime.js`, which gives it one thing,
`MusicRoom`:

```js
await MusicRoom.ready                     // the page has said hello; the theme's colours are on :root
await MusicRoom.catalogue()               // [{ id, title, artist, album, year, genres, label, duration_s,
                                          //    price_cents, has_cover, seller: { handle, name, kind, place } }]
await MusicRoom.rooms()                   // [{ handle, name, kind, bio, track_count, place }]
await MusicRoom.grupai()                  // [{ id, name, description, count, owner: { name, handle } }]
await MusicRoom.library()                 // [{ id, title, artist, album, year, genres, tags, bpm, key, colour, has_cover }]
await MusicRoom.makeCrate(ids, title)     // up to 25 records for sale become a crate in Record shopping:
                                          // one of the person's three for today, with your plug-in's name on it
MusicRoom.openRoom(handle)                // open someone's music room
MusicRoom.say(text)                       // a short line in the bar above your plug-in
MusicRoom.cover(record)                   // a record's cover, for <img src>, or ''
MusicRoom.el(tag, attrs, ...children)     // make an element; text is always text, never HTML
```

Anything you didn't ask for in `wants` is refused. A crate is how a plug-in
lets people *listen*: records in it play exactly as in any crate.

## The look

Your page starts with the app's own look (`static/css/plugin_base.css`): the
theme's colours as `--bg`, `--text`, `--muted`, `--border`, `--border2`,
`--red`, `--surface`; the fonts as `--f-display` (Instrument Serif) and
`--f-mono` (IBM Plex Mono); and a few helpers — `.mr-btn`, `.mr-btn--go`,
`.mr-input`, `.mr-label`, `.mr-grid`, `.mr-card` (`__cover`, `__t`, `__s`),
`.mr-muted`, `.mr-rule`. Use the colour variables rather than fixed colours,
and your plug-in looks right in Paper and in Ink.

## The box it runs in

So that a plug-in can be trusted without reading its code, its page:

- can load only its own files, the app's fonts and stylesheets, and record covers;
- can't send anything anywhere — no `fetch`, no forms, no frames, no WebSockets,
  no loading pictures from the internet;
- has no origin of its own, so it can't read the app's storage or pages;
- learns things only by asking the page around it, which answers only what
  `wants` names and the person agreed to.

The app itself also refuses any request that doesn't come from its own pages.

## The rules for plug-ins that come with the app

To have yours come with the Music Room, send it as a pull request to
`plugins/` ([CONTRIBUTING.md](../CONTRIBUTING.md)). It will be read before it
goes in. Please:

- say plainly, in `description`, what it does and how it chooses;
- ask for as little as it needs;
- write what people read in plain English;
- keep it small, with no outside libraries it would have to load (it can't
  load them anyway — copy what you need into its folder, with its licence).
