# Recommendations: hosting the pilots, and making the code easier to work on

From Kristian, a Green Room fellow, November 2026. Prices and free limits
were read from each provider's own pages on 24 November 2026. They change,
so check the linked page before relying on one.

## 1. Where to host the rooms server

**Today:** `gr_server.py` runs on one MacBook on the residency Wi-Fi, over
plain HTTP. When the Mac sleeps or leaves the network, every app loses the
server. During the trial its name stopped resolving and it timed out for hours
at a time.

**What the server needs:** to stay on all the time, HTTPS, a disk that
persists (SQLite plus the records, covers and listening copies), ffmpeg, and
outbound HTTPS for Spotify. It should cost nothing, or close to nothing.

### Recommended: one free VM, with SQLite kept as it is

**[Oracle Cloud Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
ARM VM.** It has 2 OCPUs, 12 GB of RAM and 200 GB of block storage, all of
which persists. It runs the server as it is today: SQLite and the files stay
on its disk, and ffmpeg installs with the package manager.

- Change little: run `gr_server.py` under a real WSGI server (gunicorn or
  waitress) instead of Flask's `app.run(threaded=True)`, and put Caddy in front
  of it for automatic HTTPS. Point `MR_GR_SERVER` at its `https://` address.
- `tools/server.sh` keeps working as it does now (deploy, backup, rollback),
  run on the VM instead of the Mac.
- Watch out for two things. Oracle can take back compute that sits idle, so
  keep the backups. And free ARM capacity is sometimes unavailable in a
  region.

### If you'd rather use managed services

Host the Flask server on any small always-on host, keep the database in
**[Neon Postgres](https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md)**
(1 GB free per project, scales to zero), and keep audio and pictures in
**[Cloudflare R2](https://developers.cloudflare.com/r2/pricing/)** (10 GB free,
and downloads are free). This takes moderate work: the SQLite-specific SQL has
to be ported, and file paths become object keys.

### Free options that don't fit, and why

| Option | The catch for this server |
|---|---|
| [Render free](https://render.com/docs/free) | sleeps after 15 min idle; disk is wiped on restart; free Postgres expires after 30 days |
| [Railway free](https://docs.railway.com/pricing/free-plan) | $1/month credit, 0.5 GB volume, sleeps when idle |
| [Koyeb free](https://www.koyeb.com/docs/faqs/pricing) | free Postgres has only 5 active hours |
| [Supabase free](https://supabase.com/pricing) | projects pause after a week of low activity; 50 MB upload cap |
| [PythonAnywhere free](https://help.pythonanywhere.com/pages/FreeAccountsFeatures) | 512 MiB disk, 100 CPU seconds, expires monthly |
| [Google Cloud e2-micro](https://docs.cloud.google.com/free/docs/free-cloud-features) | always free and on, but 1 GB/month of outbound traffic is too little for audio |
| [Fly.io](https://fly.io/docs/about/pricing/) | new $5/month free allowance, but volumes cost extra; check it first |

### A quick fix for the Mac, until then

A [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/)
gives the Mac's port 5300 a stable HTTPS address (a stable name needs a domain
on Cloudflare). That solves HTTPS and the changing `.local` name, but not
sleep: keep the Mac plugged in, with the lid open.

## 2. Making the code easier to work on

Measured on `v2026.11.24-2`.

| What | Now | Suggestion |
|---|---|---|
| `app.py` | 16,299 lines, 557 routes in one file | Move each `# ====` section into its own file with a `register(app, …)`, like `map_look.py`. This PR moves two (`removed.py`, `structures.py`) with the url_map unchanged. Next in line by size: rekordbox export (2,745 lines), wishlist (2,803), artwork (1,708), active listening (1,445). |
| Templates | `place.html` 9,736 lines, `room3d.html` 6,125 | Move inline `<script>` blocks into `static/js/` files, so they can be cached and read on their own. |
| three.js | two copies shipped (`three.module.js` 1.3 MB, `three.r128.min.js` 0.6 MB) | Use one version on every page. |
| App size | ~247 MB, mostly scipy, librosa and numpy | Check which librosa features are used; the BPM and key code may need much less. |
| Backup at launch | `_rsync_data_to` copies `library.db` with rsync while the app has it open in WAL mode. On 24 Nov the backup was skipped (`library.db-wal: No such file`), and a copy made mid-write can be out of date. | Copy the database with `sqlite3.Connection.backup()`, then rsync everything else without `library.db*`. |
| Server | Flask's development server, over plain HTTP | gunicorn or waitress, with HTTPS (see above). |
| Tests | 51 files, all passing; `test_grupa` takes ~40 s because it sleeps in real time | Drive the fake player's clock instead of sleeping. |
| Lint | 28 unused imports (some are imported on purpose, for their side effects) | Run `ruff --select F401` per file and keep the deliberate ones marked `# noqa`. |
| Speed | `import app` takes 0.16 s; pages answer in 1–6 ms | Nothing to do: the heavy libraries already load only when needed. |
