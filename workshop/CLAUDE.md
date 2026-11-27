# Music Room workshop

This folder is a workshop for making things that go **into** the Music Room app
this person already has on their computer (it's called "Music Room GR"). Read
all of this before you do anything.

## How the Music Room works: like Ableton

The Music Room is a finished app, the way Ableton Live is. Nobody makes their
own version of it. People add to it from outside, and the app takes what they
make in through its own buttons:

| what | what it is | how the person brings it in |
|---|---|---|
| **A plug-in** | a small folder (`plugin.json`, `main.js`, `style.css`) that runs in a sealed box in **Explore → Plug-ins** | **Explore → Plug-ins → Add a plug-in…**, then choose its folder |
| **The look of their music room** | CSS (or, rarely, a whole page of HTML) over the room other people visit. The room can be private or public; the look is the same | **My Public Room → Code → Open a file…** |
| **Their own look of the app** | CSS over the app itself, on their own computer only | **Settings → Your own look → Open a file…** |
| **A theme** | a small file of colours for the whole app | the **◐** key in the top bar → **Import a theme…** |

You make the files here, in this folder. The person brings them in. That's all.

Which one they mean: "my room", "my music room" or "my public room" is the look of
their music room (2). "The app", "everything" or "the Music Room itself" is a theme
when it's only colours (4), and their own look of the app when it's more (3). If
you can't tell, ask.

The app's buttons need **version 2026.11.27 or newer** (Settings shows the
version; the app offers "Update now" when there is a newer one). On an older app,
ask them to update first.

## The one rule: never build, copy or change the Music Room app

- Don't download, clone or fork the Music Room's code
  (github.com/Dbreen101/musicroom), and don't run it.
- Don't make a "version", copy, demo or mock-up of the Music Room: no web app, no
  Flask / Node / React / Vite project, no server, no `index.html` that imitates
  the app, no made-up catalogue of records to test against.
- Don't install anything (no pip, npm, npx, brew, winget, choco).
- Don't touch the installed app or its data folder. That folder holds their
  library, account and sign-in. You never need it: the app copies plug-ins in
  itself.
  - Mac: `/Applications/Music Room GR.app` and `~/Library/Application Support/Music Room GR`
  - Windows: `%LOCALAPPDATA%\Programs\Music Room GR` and `%APPDATA%\Music Room GR`
- Don't call the app's local web address (curl, a script, a browser) and don't
  open its database.

`.claude/settings.json` in this folder enforces most of this: Claude Code itself
refuses those commands and those folders. Don't try to get round a refusal; it
means you're doing the wrong thing.

**If they ask for something these four can't do** (a new button in the app, a
change to how the app works, a plug-in that sends things to the internet, a
change to someone else's room), don't work around it. Say plainly that it needs a
change to the app itself, which Daithí makes, and that they can suggest it to
him (the app has a Feedback key).

## How to work with the person

- They may not be a coder. Use plain words and keep it short.
- If what they want is unclear, ask one or two questions. Then make the smallest
  thing that does it, and grow it from there.
- You can't see the app. After each change, tell them exactly what to click. If
  anything looks wrong, ask for a screenshot; they can drag one into this chat.
- Keep everything in this folder:

```
plugins/<id>/          one folder per plug-in
room/room.css          their room's own CSS   (room/room.html for a whole page)
room/earlier/          what was there before, saved by the app ("Save as a file")
look/my-look.css       their own look of the app
look/earlier/          the look they had before
themes/<name>.json     a theme
```

---

## 1. Plug-ins

A plug-in is a new way of exploring or finding music in the Music Room. It runs
in a sealed box. It can read only what it asks for, and the person agrees to that
when they switch it on.

### The folder

```
plugins/<id>/
  plugin.json     required: who it is and what it may read
  main.js         required: its code
  style.css       optional: its look
  …               other files it carries: .js .css .json .png .jpg .jpeg .svg .webp .woff2 .txt
                  (each up to 2 MB, 200 files and 20 MB in all; anything else is left out)
```

```json
{
  "id": "by-year",
  "name": "By year",
  "version": "1.0.0",
  "author": "Their name",
  "description": "What it does and how it chooses what to show, in a sentence or two.",
  "entry": "main.js",
  "style": "style.css",
  "wants": ["catalogue"]
}
```

The app checks these rules when it is added. One that breaks a rule isn't added,
and the app says why:

- `id`: a–z, 0–9 and `-`, starting with a letter or number, at most 40
  characters. Name the folder the same. It can't be `thread` or `shelves`, which
  come with the app.
- `name`: required, at most 60 characters.
- `description`: at most 400 characters. Say plainly what it does **and how it
  chooses** what to show. The Music Room has no "machine taste": a plug-in shows
  why each record is there (its year, its label, the person's own tag…).
- `entry` must be a `.js` file inside the folder, and `style` a `.css` file inside it.
- `wants`: only from the four below. Ask for as little as it needs, because the
  person sees the list before switching it on.

### What it can read (`wants`)

| want | what it gives |
|---|---|
| `catalogue` | every record for sale in the Music Room: `{ id, title, artist, album, year, genres, label, duration_s, price_cents, has_cover, exclusive, seller: { handle, name, kind, place } }`. Here `place` is only the name the seller gave their place (like "Galway"), or `''` |
| `rooms` | the public music rooms: `{ handle, name, kind, bio, track_count, place }`. Here `place` is `{ name, lat, lon }`, or `null` if the room is nowhere in particular |
| `grupai` | the public grúpaí (collections people have made public): `{ id, name, description, count, owner: { name, handle } }` |
| `library` | the person's **own** records on their computer: `{ id, title, artist, album, year, genres, tags, bpm, key, colour, has_cover }` |

Nothing else is ever given: no files, no paths, no accounts, nobody's private
data. `catalogue`, `rooms` and `grupai` come from the Music Room's server, so the
person must be signed in and online. `library` is on their own computer.

**"Near me".** A plug-in can't know where the person is, so ask them, or let them
type a place. To measure distances, ask for `rooms` as well. A record's seller is
the room whose `handle` is the same as `seller.handle`, and that room's `place`
has `lat` and `lon`. Don't guess positions from a list of town names you made up.

### What its code can use

`main.js` runs after the app's runtime, which gives it one object, `MusicRoom`:

```js
await MusicRoom.ready                    // wait for this first; the theme's colours are then on :root
await MusicRoom.catalogue()              // [record for sale…]   (wants "catalogue")
await MusicRoom.rooms()                  // [public room…]       (wants "rooms")
await MusicRoom.grupai()                 // [public grúpa…]      (wants "grupai")
await MusicRoom.library()                // [their own record…]  (wants "library")
await MusicRoom.makeCrate(ids, title)    // → { ok, count }: records for sale become a crate in Record shopping
MusicRoom.openRoom(handle)               // open someone's music room
MusicRoom.say(text)                      // a short line in the bar above the plug-in (200 characters at most)
MusicRoom.cover(record)                  // a record's cover address for <img src>, or '' if it has none
MusicRoom.el(tag, attrs, ...children)    // make an element; text is always text, never HTML
                                         //   attrs: class, text, any attribute, and onclick/onchange/… as functions
```

- **Crates are how a plug-in lets people listen.** A plug-in can't play sound
  itself. `makeCrate` takes ids from `catalogue()` (only records for sale can go
  in a crate), uses at most 25, and cuts the title to 80 characters. Each crate
  uses one of the person's three crates for the day, and records in it play as
  in any crate.
- `MusicRoom.el` takes lists as children, but the page's own `append` doesn't.
  `app.append([a, b])` prints "[object HTMLDivElement]" on the page instead of
  the elements. Spread a list (`app.append(...list)`), or wrap it:
  `el('div', null, list)`.
- Every call can fail (not signed in, offline, not allowed). Catch the error and
  show its message in the page.
- A call that gets no answer in 30 seconds fails with "The app didn't answer."

### The page it draws in

The app makes the page. Your `main.js` only draws into `<main id="app">`.
Already loaded: the app's base look and its fonts.

- **Colours.** Use these, never fixed colours. They follow the person's theme,
  light or dark: `var(--bg)` `var(--surface)` `var(--text)` `var(--muted)`
  `var(--border)` `var(--border2)` `var(--red)`
- **Fonts.** `var(--f-display)` (Instrument Serif) and `var(--f-mono)` (IBM Plex
  Mono, the body text). These are also there by name: "Apfel Grotezk",
  "Bagnard", "Basteleur", "Bricolage Grotesque", "Fraunces", "Gloock",
  "Le Murmure", "League Gothic", "Nyght Serif", "Sorts Mill Goudy",
  "Young Serif".
- **Ready-made classes.** `.mr-btn`, `.mr-btn--go` (or `.mr-btn.on`),
  `.mr-input`, `.mr-label`, `.mr-grid`, `.mr-card` with `.mr-card__cover`
  `.mr-card__t` `.mr-card__s`, `.mr-muted`, `.mr-rule`. `h1`–`h3` are already
  styled.
- **The app's look.** It's like a working document: paper and ink, hairlines,
  square corners, and one red used only for emphasis. Fit in with it unless the
  person wants otherwise.

### The sealed box: what doesn't work there

These are blocked on purpose. Don't try them and don't work around them:

- **No network at all.** That means no `fetch`, XMLHttpRequest, WebSocket, forms
  or iframes, and nothing loaded from the internet (scripts, libraries from a CDN,
  fonts, pictures). If a library is truly needed, copy it into the folder with its
  licence, but prefer plain JavaScript.
- **No inline scripts and no `eval`.** No `onclick="…"` in HTML strings, no
  `new Function`, no `<script>` in `innerHTML`. Use `MusicRoom.el` with function
  handlers, or `addEventListener`.
- **No storage.** `localStorage`, `sessionStorage`, cookies and IndexedDB are
  unavailable. The plug-in starts fresh each time it opens.
- **No `alert`, `confirm` or `prompt`** (they do nothing). Draw in the page or use
  `MusicRoom.say`.
- **No sound or video.** Make a crate instead.
- **No opening web links.** `MusicRoom.openRoom(handle)` is its only way out.
- **Pictures in its own folder need their full address**, because the page
  doesn't live in the folder:

  ```js
  const OWN = document.querySelector('meta[name="mr-origin"]').content + '/plugins/files/<id>/';
  MusicRoom.el('img', { src: OWN + 'picture.png', alt: '' });
  ```

  Inside `style.css`, a plain `url(picture.png)` works.

### Bringing it in, and trying it

You never copy anything into the app. Tell the person:

1. In the app: **Explore → Plug-ins → Add a plug-in…** and choose this folder's
   `plugins/<id>` folder. (Choosing `plugins` itself works too when there is only
   one plug-in in it.) The app checks it, takes a copy, and lists it as
   "yours · not reviewed". If it says why it can't add it, fix that.
2. **Switch on** (it shows what the plug-in will read), then **Open**.
3. After each change you make here: **Look again**. The app takes a fresh copy
   from the same folder and starts the open plug-in again.
4. If `wants` changed, the plug-in switches itself off. They press **Switch on**
   again.
5. **Remove** (on its card) takes it out of the app. The folder here stays.

Their own plug-ins run only in their own app. Nobody else sees them.

### When it doesn't work

There are no developer tools in the app's window, so:

- Wrap the code in `try/catch` and write any error into the page, as the starter
  below does.
- Before they add it, check that `main.js` parses. If Node happens to be
  installed, use `node --check plugins/<id>/main.js`; if not, read it over
  carefully. Also check that `plugin.json` is valid JSON.
- Opens blank: something failed before it drew. Look for anything from the
  "sealed box" list above.
- "[object HTMLDivElement]" on the page: a list was handed to the page's own
  `append` (see above).

### A starter plug-in (tested against the app's own runtime)

This shows every record for sale from the years you choose. Tick up to 25 and
make a crate. Copy it, rename it, and change it into what the person wants.

`plugins/by-year/plugin.json`

```json
{
  "id": "by-year",
  "name": "By year",
  "version": "1.0.0",
  "author": "Your name",
  "description": "Every record for sale from the years you choose, oldest first. Each card says the year it is there for. Tick up to 25 to make a crate.",
  "entry": "main.js",
  "style": "style.css",
  "wants": ["catalogue"]
}
```

`plugins/by-year/main.js`

```js
/* By year — every record for sale from the years you choose, oldest first.
   Tick up to 25 and make a crate of them in Record shopping. */
(async function () {
    const { el } = MusicRoom;
    const app = document.getElementById('app');
    const show = text => { app.textContent = ''; app.append(el('p', { class: 'mr-muted' }, text)); };

    try {
        await MusicRoom.ready;
        show('Reading the shop…');
        const all = (await MusicRoom.catalogue()).filter(r => r.year);
        if (!all.length) return show('No record for sale has a year on it yet.');
        const years = all.map(r => r.year);
        let from = Math.min(...years), to = Math.max(...years);
        const ticked = new Set();

        function draw() {
            const recs = all.filter(r => r.year >= from && r.year <= to).sort((a, b) => a.year - b.year);
            app.textContent = '';
            app.append(
                el('h1', null, 'By year'),
                el('div', { class: 'by-bar' },
                    el('label', { class: 'mr-label' }, 'From',
                        el('input', { class: 'mr-input', type: 'number', value: from, onchange: e => { from = +e.target.value || from; draw(); } })),
                    el('label', { class: 'mr-label' }, 'to',
                        el('input', { class: 'mr-input', type: 'number', value: to, onchange: e => { to = +e.target.value || to; draw(); } })),
                    el('button', { class: 'mr-btn mr-btn--go', type: 'button', disabled: !ticked.size, onclick: makeCrate },
                        `Make a crate of ${ticked.size}`)),
                recs.length ? el('div', { class: 'mr-grid' }, recs.map(card))
                            : el('p', { class: 'mr-muted' }, 'Nothing for sale from those years.'));
        }

        function card(r) {
            const on = ticked.has(r.id), src = MusicRoom.cover(r);
            return el('div', { class: 'mr-card' },
                src ? el('img', { class: 'mr-card__cover', src, alt: '', loading: 'lazy' }) : el('div', { class: 'mr-card__cover' }),
                el('div', { class: 'mr-card__t' }, r.title || 'Untitled'),
                el('div', { class: 'mr-card__s' }, [r.artist, 'from ' + r.year].filter(Boolean).join(' · ')),   // why it is here
                el('div', { class: 'by-acts' },
                    el('button', { class: 'mr-btn' + (on ? ' on' : ''), type: 'button', 'aria-pressed': String(on), onclick: () => tick(r) },
                        on ? 'Ticked' : 'Tick'),
                    r.seller && r.seller.handle
                        ? el('button', { class: 'mr-btn', type: 'button', onclick: () => MusicRoom.openRoom(r.seller.handle) }, r.seller.name || 'Their room')
                        : null));
        }

        function tick(r) {
            if (ticked.has(r.id)) ticked.delete(r.id);
            else if (ticked.size >= 25) return MusicRoom.say('A crate holds 25 records.');
            else ticked.add(r.id);
            draw();
        }

        async function makeCrate(e) {
            e.target.disabled = true;
            try {
                const d = await MusicRoom.makeCrate([...ticked], `From ${from} to ${to}`);
                ticked.clear();
                MusicRoom.say(`A crate of ${d.count} is in Record shopping.`);
                draw();
            } catch (err) { MusicRoom.say(err.message); e.target.disabled = false; }
        }

        draw();
    } catch (err) {
        show('Something went wrong: ' + err.message);
    }
})();
```

`plugins/by-year/style.css`

```css
.by-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 0 0 18px; }
.by-bar .mr-input { width: 6.5em; margin-left: 6px; }
.by-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.by-acts .mr-btn { padding: 4px 8px; font-size: .7rem; }
```

### Sharing a plug-in

- **With a friend:** zip the `plugins/<id>` folder and send it. They unzip it and
  add it the same way (Add a plug-in…).
- **With everyone:** only if the person asks. A plug-in comes with the app only
  if Daithí accepts it, as a pull request to github.com/Dbreen101/musicroom that
  adds the one folder `plugins/<id>/` and changes nothing else. Read
  `CONTRIBUTING.md` there first. That is the only time anything goes near the
  app's code, and the person makes the pull request from their own fork on
  GitHub; you don't need the rest of the code to do it.

---

## 2. The look of their music room

Each person has a music room that others in the Music Room can visit. It starts
private (only they see it) and they can make it public; the look is the same
either way. They design it in the app: top bar → **My Public Room**. The editor
has tabs: Blocks · Look · Who · Images · Records · Crates · Code (some kinds of
account also see Works and Events). The preview on the right shows the room as
visitors see it.

**Start with what the editor already does without code**, and suggest it when
it's enough. It's easier for the person to change later:

- **Look:** background, text and accent colours, and fonts for titles and for
  body text.
- **Blocks:** the room is a stack of blocks, top to bottom. They can add, move or
  switch off any of these: Opening (name, a line, an image, the About text, links),
  Words, Image, Gallery, Records, Picks, Places, Grúpaí, Events, Works,
  On records, Links, Space, and Your own HTML.
- **Who:** name, handle, About, links, and where the room is.
- **Images:** upload pictures. Each one shows its address.

Then the **Code** tab adds what those can't. It has two boxes: their own CSS over
the blocks (the usual way), or a whole page of their own HTML.

### Their own CSS (the usual way)

The CSS goes over the standard room, so everything keeps working: visitors can
still borrow and buy records, open links and grúpaí, and report a room.

**What there is to style.** The room sits in `.pr` (`#pr`), at most 1100px wide.
The visitors' bar (`.pr-bar`) is above it, outside `.pr`. Each block is a
`<section class="rb rb-<kind>">` (Space is a `<div>`), and its heading is
`h2.rb-h`. Colours here are the person's own choice, so fixed colours are fine
in a room. The colour variables are for plug-ins.

| block | classes |
|---|---|
| Opening | `.rb-hero` plus `--side` (image beside), `--cover` (image behind, given as `--img`), or `--plain`; `.rb-hero__text`, `.rb-eyebrow` (the kind of room), `h1.rb-name`, `.rb-tag`, `p.rb-bio`, `.rb-links a`, `img.rb-hero__img` |
| Words | `.rb-text` plus `--narrow` or `--wide`, `.rb-body` |
| Image | `.rb-image` plus `--small`, `--wide` or `--full`, `img`, `.rb-cap` |
| Gallery | `.rb-gallery`, `.rb-gallery__row img` |
| Records | `.rb-records` plus `--grid`, `--large` or `--list`, `.rb-records__grid`. Each record is `.pr-rec`: `.pr-rec__cov` (an `img`, or a `div` with one letter in a `span`), `.pr-rec__t`, `.pr-rec__s`, `.pr-rec__act`, and buttons `.pr-btn` (`--on`, `--quiet`) |
| Records, as whole records | While the credits trial is on, records from the shop show as whole albums and singles inside `.rb-records--whole`: `.sim-recs`, then `.sim-rec` with `.sim-rec__cov`, `.sim-rec__body`, `.sim-rec__t`, `.sim-rec__s`, `.sim-rec__whole`, the track list `ol.sim-rec__tracks` with `li.sim-tr` (`.sim-tr__n`, `.sim-tr__t`, `.sim-tr__d`), and buttons `.sim-btn`. Records uploaded as files sit beside them as `.pr-rec` in a `.pr-grid` |
| Picks | `.rb-picks`, `.rb-picks__list`, `.rb-pick` (`__t`, `__s`, `__n`) |
| Places | `.rb-places`, `.rb-places__grid`, `.rb-place` (its colour is `--c`; `i`, `__n`, `__c`) |
| Grúpaí | `.rb-grupai` plus `--grid` or `--list`, `.rb-grupai__grid`, `.rb-grupa` (`__cover`, `__t`, `__d`, `__s`) |
| Events | `.rb-events`, `.rb-event` (`.is-past`; `__pic`, `__when`, `__t`, `__d`) |
| Works | `.rb-works`, `.wk-grid` plus `--grid`, `--large` or `--wall`, `.wk-tile` |
| On records | `.rb-credits`, `.wk-credits`, `.wk-credit` |
| Links | `.rb-linklist`, `.rb-links a` |
| Space | `.rb-spacer` plus `--small` or `--large` |
| Your own HTML | `.rb-custom iframe`. It's a sealed frame with no scripts. The room's CSS is copied inside it too |

**Colours and fonts as variables:** `--pr-bg`, `--pr-ink` (text), `--pr-muted`,
`--pr-accent`, `--pr-font-title`, `--pr-font-body`. You can set them in `:root`.
A colour or font set in the Look tab wins over `:root` in your CSS, so either
clear it there or add `!important`. If a rule doesn't take, make the selector more
specific (for example `.pr .rb-name`).

**Their own pictures.** A picture has to be uploaded on the Images tab first: a
file on their computer, in this folder or in this chat can't be used by the room.
Ask them to upload it and tell you its address (each picture has a **Copy
address** key). It looks like `/api/gr/asset/12`. Use it as it is:
`background-image: url(/api/gr/asset/12);`. Until they tell you, write a
placeholder and say which line to change.

**The page itself** is `html, body`, and its ground is `--pr-bg`.

**What the page allows.** Anything else is silently not loaded:

- **Pictures:** their own uploaded pictures (above), record covers, `data:`
  addresses, and the streaming services' picture servers. No pictures from other
  websites.
- **Fonts:** only the ones the app carries ("Instrument Serif", "Apfel Grotezk",
  "Bagnard", "Basteleur", "Bricolage Grotesque", "Fraunces", "Gloock",
  "Le Murmure", "League Gothic", "Nyght Serif", "Sorts Mill Goudy",
  "Young Serif": every one is loaded on the room's page, for every visitor),
  fonts already on the visitor's computer, or a font embedded as a `data:`
  address in `@font-face` (mind its licence). No Google Fonts, and no `@import`
  from the internet.
- **CSS only.** No scripts.
- At most 120,000 characters.
- Animations and transitions are fine. Calm them inside
  `@media (prefers-reduced-motion: reduce)`.

**Leave these working**, because visitors need them:

- the bar along the top (`.pr-bar`): it's the way back, and it has the report
  button
- the buttons on records (`.pr-btn`, `.sim-btn`): restyle them, but keep them
  visible and readable
- the grúpa panel that slides in from the right (`.pr-gsheet`)
- readable text: at least 4.5 : 1 contrast for body text against its background

### A whole page of their own HTML (rarely the right choice)

The second box in the Code tab replaces all the blocks with their own page.
Before choosing it, tell the person what it costs:

- It runs in a sealed frame with **no scripts**.
- Records appear where you write `<!--records-->` (the first one only). They
  come **without the borrow and buy buttons**, so visitors can look at them but
  can't borrow or buy from the room.
- Links in it don't open.
- Their Opening, links, grúpaí, events and works don't appear unless you write
  them in by hand.
- None of the app's look reaches inside, so bring your own `<style>`. Style the
  records too: `.pr-grid`, `.pr-rec`, `.pr-rec__cov` (an `img`, or a `div` with
  one letter in a `span`), `.pr-rec__t`, `.pr-rec__s`.
- The same rules for pictures apply. For fonts, don't count on the app's own
  inside the frame; use an embedded font or one already on the visitor's
  computer.

To go back to blocks, they empty that box. Save it as `room/room.html`.

### Bringing it in

1. **First, keep what is there.** Ask them: **My Public Room → Code → Save as a
   file**, and to save it into this folder's `room/earlier/` (the app names it
   after the design). If the boxes are empty, there's nothing to keep.
2. Write `room/room.css`.
3. Tell them: **My Public Room → Code → Open a file…** and choose
   `room/room.css`. It goes into the first box, saves itself within a second (the
   editor says "saved"), and the preview redraws. An `.html` file goes into the
   second box instead.
4. After each change: **Open a file…** again and choose the same file. Ask for a
   screenshot of the preview if they want changes.
5. To undo: **Open a file…** and choose the one in `room/earlier/`.

**Live or a draft.** The menu at the top left of the editor shows which design
they're editing. If it's the live one, visitors see each change as soon as it
saves. To try things where nobody sees them, they press **+ new** to make a draft
(it starts from the standard blocks, not a copy), open the file into the draft,
and press **Make this the live one** when they're happy. Whether anyone can see
the room at all is the Private / Public line at the top of the editor. That's
their own choice, so leave it to them.

---

## 3. Their own look of the app

**Settings → Your own look** is CSS over the whole app, on their computer only.
Nobody else sees it. Use it for things a theme can't do (spacing, type, a
texture), and a theme (below) for colours.

- The app's colours are variables on `:root`; changing them is the safest way to
  restyle it: `--bg`, `--surface`, `--surface2`, `--text`, `--muted`, `--border`,
  `--border2`, `--accent`, `--red`, `--sheet`, `--nav-bg`, and for the newer
  pages `--gr-bg`, `--gr-surface`, `--gr-line`, `--gr-ink`, `--gr-muted`,
  `--gr-faint`, `--gr-accent`. The top bar is `.nav`.
- Beyond the variables you can't see the app's pages, so keep rules general, ask
  for screenshots, and change one thing at a time.
- Nothing in it loads from the internet: the app takes out `@import` and any
  `url()` that points at another computer. `data:` addresses still work.
- At most 60,000 characters.
- A look that hides too much can't lock them out: **⌘⇧0** (Ctrl+Shift+0 on
  Windows) opens Settings without it.

Bringing it in: first **Settings → Your own look → Save as a file** into
`look/earlier/` if there is anything there; then write `look/my-look.css`, and
tell them **Settings → Your own look → Open a file…** and choose it. It shows on
the next page they open.

## 4. A theme

A theme is a small JSON file of colours for the whole app, light or dark:

```json
{
  "name": "Seafoam",
  "author": "Their name",
  "scheme": "dark",
  "vars": { "bg": "#0b1412", "surface": "#101c19", "text": "#e6f0ec", "accent": "#7fd3b8" }
}
```

`scheme` is `light` or `dark`. Leave out any colour they don't care about. The
names you can use: `bg`, `bg-floor`, `surface`, `surface2`, `border`, `border2`,
`text`, `muted`, `muted2`, `accent`, `accent-dim`, `gold`, `gold-soft`, `well`,
`oxblood`, `lapis`, `ochre`, `danger`, `warning`, `red`, `sheet`, `nav-bg`,
`pill-ink`, `shadow`, `ink`, `gr-bg`, `gr-surface`, `gr-line`, `gr-ink`,
`gr-muted`, `gr-faint`, `gr-accent`, `gr-accent-ink`, and `map-sea`, `map-land`, `map-line`, `map-text` for the map
in Explore. Colours are hex, `rgb()`, `rgba()` or `hsl()`.

Most of the app reads `bg`, `surface`, `text`, `muted`, `border`, `accent` and
`red`: set those first, and leave the rest out unless something looks wrong. Keep
`text` against `bg` and `surface` at 4.5 : 1 or more, and `muted` at 3 : 1 or more.

Write `themes/<name>.json`, then tell them: the **◐** key in the top bar →
**Import a theme…** and choose it. The same name replaces the old one.

---

## Before you say it's done

**Plug-in**
- `plugin.json` is valid JSON, its `id` is the folder's name, `wants` is as small
  as it can be, and the description says how it chooses
- `main.js` parses, draws into `#app`, and catches errors; it has no network
  calls, eval, inline handlers, alert or storage, and it never hands a list to
  the page's own `append`
- it uses the colour variables, so it works in light and dark
- nothing was copied into the app's folders: the person adds it (Add a plug-in…)
  and refreshes it (Look again)

**Room**
- no `url()` or `@import` pointing outside the app (their pictures' own
  addresses, covers and `data:` only)
- fonts from the list, already on the visitor's computer, or embedded
- the top bar and the record buttons are still visible and readable
- under 120,000 characters
- what was there before is saved in `room/earlier/`
- the person has been told: Code → Open a file…

**Your own look / a theme**
- the earlier look is saved; the file opens with Settings → Your own look → Open a file…, or ◐ → Import a theme…
