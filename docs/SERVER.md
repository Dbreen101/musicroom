# The rooms server: running it, releases, and stepping back

The rooms server (`gr_server.py`, with `gr_shop.py` and `gr_master.py`) is
the shared part of the Music Room: accounts, records for sale, public rooms
and grúpaí, record shopping, reports and feedback. For the Green Room it runs
on one Mac on the residency's Wi-Fi, on port **5300**.

`tools/server.sh` does everything below. It keeps the server in a folder of
its own, **never** the code you are working on:

```
~/MusicRoomServer/
  releases/<tag>/        the code of each release, exactly as tagged on GitHub
  current -> releases/…  the one that is running
  data/green_room.db     everything people have made (records, pictures and covers sit beside it)
  backups/               a copy of the database before every change of release
  logs/server.log
  releases.log           which release ran when
```

## The first time

```bash
tools/server.sh deploy v2026.11.20     # put the first release in place and start it
tools/server.sh install                # start it whenever this Mac starts, and again if it stops
tools/server.sh master "Daithí Breen"   # make the master account — it prints its code
tools/server.sh address                # the address the fellows' apps use
```

Sign your own app in with the master's code, using the server address
`http://127.0.0.1:5300` (the master page only answers on this Mac). Then
Settings → Account → *Open the master page*.

Keep the Mac plugged in and its lid open: the server keeps it awake while
plugged in, but a closed lid sends a MacBook to sleep.

## Approving changes, and releasing them

Nothing reaches the fellows without you:

1. Changes arrive as **pull requests** on GitHub. `main` is protected: only you
   can merge, and only after looking.
2. Take a merged pull request into your working copy:
   `tools/take_public.sh <number>`. Your own work goes the other way:
   `python3 tools/publish_public.py -m "what changed" --push` (it refuses to
   publish anything private, and refuses to run over a merged pull request you
   haven't taken in yet).
3. When you're happy, make a **release**: tag it (`vYYYY.MM.DD`, with `-2`, `-3`
   for a second that day), build the two Mac apps, and put them on the
   release's page:
   ```bash
   tools/release.sh v2026.11.21 "what changed, in a line"
   ```
   The **Windows** app builds itself: the tag starts GitHub's Windows machines
   (`.github/workflows/windows.yml`), which run the tests on Windows, build
   *Music Room (Windows).zip*, check it starts, and add it to the same page
   (about 15 minutes; watch it under the repo's **Actions** tab). For a release
   that already exists: Actions → *Windows app* → *Run workflow* → its tag.
4. Move the server to it: `tools/server.sh deploy v2026.11.21`.
5. Tell everyone's app: master page → **Version** → name it and paste the
   release's address. Each app says "a new version is ready" within ten
   minutes.

## Stepping back

Every release stays in `releases/`, every database copy in `backups/`.

```bash
tools/server.sh releases                    # what is here, and which is running
tools/server.sh rollback v2026.11.20        # run that release again; everyone's data stays as it is
```

Then on the master page → Version, name the older release so the apps follow.

Only if a newer release damaged the data itself:

```bash
tools/server.sh rollback v2026.11.20 --with-data ~/MusicRoomServer/backups/<the file>.db
```

That puts the database back as it was then. Anything made since — new
accounts, records, reports — is lost (the database as it was is copied to
`backups/` first, so even this can be undone).

## Day to day

```bash
tools/server.sh status       # is it running, which release
tools/server.sh log          # the last lines of its log
tools/server.sh backup       # a copy of the database now
tools/server.sh restart
```

From the server's own Terminal (with `MR_GR_DB=~/MusicRoomServer/data/green_room.db`):
`python gr_server.py usage` (what each person has done), `feedback`, `events`.

## The credits trial (records from a Spotify playlist)

While it is on, everyone brings records home or buys them with credits — no
basket, no plans, no wallet. The shop's records come from one public Spotify
playlist you made: every track on it brings in its whole album or single, and
each record's first artist gets a simulated artist account with a public room.
Nothing is ever downloaded: each person's own Spotify plays them inside the
Music Room.

```bash
tools/server.sh sim on        # or: master page → Credits trial → The trial is on
```

Then, on the master page (your own app, signed in to the master):

1. **Credits trial** → paste the playlist's link → *Save* → *Bring records in
   now*. Your app must be signed in to Spotify (Settings → Spotify) with the
   account that made the playlist. It looks again every hour while your app is
   open; records already in the shop stay as they are.
2. **Spotify keys** → add your app's Client ID (developer.spotify.com → your app
   → Settings). Give it to up to five people. On developer.spotify.com add each of
   them too (User Management: name + the email of their Spotify account). Their
   apps pick the key up by themselves; they sign in to Spotify once and hear whole
   tracks (Spotify Premium). Everyone else hears Spotify's own small player.
3. **Activity** → what everyone spent, their room, what they did when it was full;
   both tables as spreadsheets.

The numbers (credits to start, what bringing home and buying cost, the whole
record's share, the room's space, the days before a track taken out comes back)
are on the Credits trial tab. Every change is logged with the time, so a week's
numbers can be read against that week's rules.

## If the fellows' apps can't reach it

Shared Wi-Fi sometimes stops laptops seeing each other. Check from another
laptop: `curl http://<the address>:5300/api/version`. If the name
(`….local`) doesn't work but the number does, have people press *change* on
the front door and type the number. If neither works, the Wi-Fi is keeping
laptops apart; the way round it is a tunnel, which gives the server an address
that works from anywhere (next section).

## Reaching the server from outside the building

A tunnel (Tailscale Funnel, Cloudflare Tunnel) or a hosted machine behind a
relay (Caddy) gives the server an `https://` address anyone can reach. Before
that address is handed out:

1. **Set an invite code.** Without one, anybody who finds the address can make
   an account. Master page → Version → *Invite code for new accounts*, or
   `gr_server.py door --code "some words"`. People who already have an account
   are not asked for it.
2. **Check the master's page stays shut.** It answers only the master's own app,
   on the server's own computer, talking straight to `http://127.0.0.1:5300`.
   A request that comes through a tunnel or a relay is refused, even with the
   master's code. Try it: from another computer, open
   `https://<the new address>/api/master/overview`. It must say no.
   (A server on a rented machine has no app beside it. There the master's
   routes need `MR_MASTER_ANYWHERE=1`, and then the master's code is the only
   lock: think before using it.)
3. **Tell the apps.** Master page → Version → *The server's new address*, or
   `gr_server.py door --moved-to https://…`. Every signed-in app that asks the
   old address is told within ten minutes, checks that the new address knows
   its sign-in, and moves. Nobody signs up again. New builds should carry the
   new address (`MR_GR_SERVER` in `tools/release.sh`, and the repo variable of
   the same name for the Windows build).

Limits on sign-ups and wrong codes count each visitor's own address, also
through a relay on the same computer (the relay's note of who it took the
request from is used; a visitor who comes straight in can't claim another
address).

`tools/server.sh` starts the server with macOS's own tools (a LaunchAgent,
`caffeinate`). On a Linux machine it needs a systemd unit instead; that is not
written yet. Run the server as ONE process there (limits and holds are kept
in its memory).
