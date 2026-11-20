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
tools/server.sh master "David Breen"   # make the master account — it prints its code
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
   for a second that day), build the two apps, and put them on the release's
   page:
   ```bash
   tools/release.sh v2026.11.21 "what changed, in a line"
   ```
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

## If the fellows' apps can't reach it

Shared Wi-Fi sometimes stops laptops seeing each other. Check from another
laptop: `curl http://<the address>:5300/api/version`. If the name
(`….local`) doesn't work but the number does, have people press *change* on
the front door and type the number. If neither works, the Wi-Fi is keeping
laptops apart; the way round it is a tunnel (for example Cloudflare's), which
gives the server an address that works from anywhere.
