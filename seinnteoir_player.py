"""
seinnteoir_player.py — server-side audio player.

The browser used to play audio with an <audio> tag, which dies on every
navigation. This module keeps the audio in the Flask process so it
genuinely persists across page loads. The browser becomes a remote that
posts commands and polls state.

Backed by pygame.mixer.music. Plays one file at a time, advances the
queue automatically when a track ends. Thread-safe; a background monitor
thread watches for the current file finishing and advances.
"""

import os
import json
import time
import hashlib
import threading
import collections
import re
import uuid
import urllib.request

try:
    from mr_paths import DATA_DIR
    _QUEUE_FILE = os.path.join(DATA_DIR, "seinnteoir_queue.json")
    # Remote Explore mixes/podcasts are downloaded here, then played as local
    # files (pygame can't stream a URL). Cached so a replay is instant; capped.
    _STREAM_CACHE_DIR = os.path.join(DATA_DIR, "explore_audio_cache")
    # Formats SDL_mixer (pygame) can't decode here — chiefly M4A/AAC — are
    # transcoded once to a small OGG and played from this cache. See
    # _pygame_can_decode / _load_transcoded_locked.
    _PLAYBACK_CACHE_DIR = os.path.join(DATA_DIR, "playback_transcode")
except Exception:                      # mr_paths unavailable (e.g. a bare test)
    _QUEUE_FILE = None
    _STREAM_CACHE_DIR = None
    _PLAYBACK_CACHE_DIR = None

_STREAM_CACHE_CAP = 2 * 1024 * 1024 * 1024   # 2 GB of cached mixes, then evict
_TRANSCODE_CACHE_CAP = 1 * 1024 * 1024 * 1024  # 1 GB of OGG transcodes, then evict
_STREAM_UA = "MusicRoom/1.0 (personal DJ library tool)"


def _pygame_can_decode(path):
    """Can pygame/SDL_mixer decode this file directly?

    SDL_mixer here handles MP3, WAV, FLAC and OGG, but NOT MP4/AAC (an .m4a
    load fails with 'ModPlug_Load failed'). Those are detected — by the MP4
    'ftyp' magic, or the extension — so the caller can transcode them to a
    playable OGG instead. Anything we can't sniff is assumed playable."""
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".m4a", ".m4b", ".mp4", ".aac", ".alac"):
            return False
        with open(path, "rb") as fh:
            head = fh.read(12)
        if head[4:8] == b"ftyp":        # MP4 container (m4a/aac/alac)
            return False
    except Exception:
        pass
    return True


class _NoMixer(Exception):
    pass


class SeinnteoirPlayer:
    def __init__(self, resolve_path=None):
        self._lock         = threading.RLock()
        self.queue         = []     # list of dicts
        self.idx           = -1
        self.position      = 0.0    # seconds; only authoritative while paused
        self.is_paused     = True
        self.volume        = 0.8
        self.duration_sec  = 0.0    # current track length, best-effort
        self._wall_start   = 0.0    # wall-clock when current run-from-offset started
        self._offset_start = 0.0    # position within track at _wall_start
        self._mixer_ok     = False
        # Resolver: takes the raw stored path and returns the actual playable
        # path (handles drive-name remapping etc.). If None, paths are used
        # as-is. Wire app.py's _resolve_audio_path here at startup.
        self._resolve_path = resolve_path or (lambda p: p if os.path.exists(p) else None)
        self._needs_load   = False  # set on restore: the cue is loaded but no
                                    # file is in the mixer yet, so the first
                                    # play() must do a fresh load, not unpause
        self._buffering    = False  # a remote stream item is downloading
        self._downloading  = set()  # audio_urls currently being fetched
        self._transcoding  = set()  # source paths currently being transcoded (m4a→ogg)
        self._last_error   = None   # {'title','reason','at'} — the UI surfaces
                                    # this; a silent skip reads as "broken,
                                    # won't tell me why" to a tester
        self._embed_seq    = 0      # bumps on every load/seek of a streamed
                                    # ('embed') item — the page's player follows it
        # ── the listener's own Spotify (spotify_remote.py), when it can be driven ──
        self._remote        = None  # the driver; None = streamed records play in the page
        self._remote_thread = None
        self._via           = ''    # how the CURRENT streamed record sounds:
                                    # 'remote' (in the listener's Spotify) | 'page'
                                    # (the service's player beside the deck) | ''
        self._rq            = collections.deque()   # commands waiting for the remote worker
        self._rq_evt        = threading.Event()
        self._r_live        = False # something we started may be sounding in Spotify
        self._r_starting    = False # the play command is still on its way
        self._r_started     = False # …and it landed, for the current record
        self._r_qid         = None
        self._r_uri         = ''    # what Spotify should be on, if it is on ours
        self._r_many        = False # an album / playlist: plays on through its own tracks
        self._r_adopted     = False
        self._r_seen        = False # Spotify has been seen on this record since we asked
        self._r_now         = None  # an album / playlist: the track it is on right now
        self._r_cmd_at      = 0.0   # when we last told Spotify something (let it settle)
        self._r_poll_at     = 0.0
        self._r_maxpos      = 0.0
        self._r_tight       = False
        self._r_dev         = ''    # the device it is sounding on (shown on the slip)
        self._r_note        = ''    # why the page's player was used instead
        self._r_vol_sent    = None
        self._guest         = None  # what the listener's Spotify is playing on its own
        self._guest_poll_at = 0.0
        self._seen_at       = 0.0   # the last time a page asked for the deck's state
        self.ui_mode       = 'open' # the cassette's open/min/closed — kept HERE
                                    # (not just localStorage) because the desktop
                                    # shell wipes localStorage on every relaunch,
                                    # which reopened a put-away player each boot
        if _STREAM_CACHE_DIR:
            try: os.makedirs(_STREAM_CACHE_DIR, exist_ok=True)
            except Exception: pass
        self._init_mixer()
        self._restore_locked()      # bring back the last cue — ALWAYS paused
        self._start_monitor()

    # ─── persistence: the cue survives an app restart ───────────────
    # Written on every queue/idx change; restored on boot. We never resume
    # playback automatically — audio is audible on the user's machine, so a
    # relaunch must come up silent with the cue ready to press play.
    def _persist_locked(self):
        if not _QUEUE_FILE:
            return
        try:
            data = {"queue": self.queue, "idx": self.idx, "ui_mode": self.ui_mode}
            tmp = _QUEUE_FILE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, _QUEUE_FILE)
        except Exception:
            pass

    def _restore_locked(self):
        if not _QUEUE_FILE or not os.path.exists(_QUEUE_FILE):
            return
        try:
            with open(_QUEUE_FILE) as fh:
                data = json.load(fh)
            # the cassette's open/min/closed comes back with the cue — read it
            # BEFORE the empty-queue early-return so a put-away player stays
            # put away even when nothing is cued
            if data.get("ui_mode") in ("open", "min", "closed"):
                self.ui_mode = data["ui_mode"]
            # …but the app never LAUNCHES with the full bar covering the room
            # (David, 2026-07-10): a cue remembered from last time comes back
            # as the folded ♫-tab. Opening it is the user's gesture — the tab,
            # cueing a track, or Tools → Player.
            if self.ui_mode == "open":
                self.ui_mode = "min"
            # Re-coerce: re-resolves paths (drive may have remapped) + drops any
            # files that have since vanished. The stored items already carry a
            # resolved file_path, which _coerce re-validates.
            coerced = [c for c in (self._coerce(i) for i in (data.get("queue") or [])) if c]
            if not coerced:
                return
            self.queue     = coerced
            idx            = int(data.get("idx", 0))
            self.idx       = max(0, min(idx, len(coerced) - 1))
            self.position  = 0.0
            self.is_paused = True       # come up silent
            self._needs_load = True     # first play() loads fresh, never unpause
        except Exception:
            pass

    # ─── mixer setup ───────────────────────────────────────────────
    def _init_mixer(self):
        try:
            import pygame
            # buffer=4096 frames (~93 ms at 44.1 kHz) — was 2048 (~46 ms). The
            # library lives on an EXTERNAL drive and pygame STREAMS + decodes the
            # file off it live on the audio thread; a transient drive read-stall
            # (USB bus contention, a brief seek, Spotlight/Time Machine touching
            # the bus) longer than the buffer's headroom starves CoreAudio and you
            # hear a light, quick gap. Doubling the buffer doubles the slack so a
            # hiccup is absorbed before it's audible. Cost: ~+46 ms latency on
            # play/pause/seek — imperceptible for a background, navigation-
            # surviving player. (Fixed at init; needs an app restart to apply.)
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
            pygame.mixer.music.set_volume(self.volume)
            self._mixer_ok = True
        except Exception as e:
            print(f"[seinnteoir] mixer init failed: {e}")
            self._mixer_ok = False

    def _start_monitor(self):
        def loop():
            import pygame
            while True:
                time.sleep(0.4)
                with self._lock:
                    if not self._mixer_ok:           continue
                    if self.idx < 0 or self.idx >= len(self.queue): continue
                    if self.is_paused:                continue
                    if self.queue[self.idx].get('kind') == 'embed':
                        continue                     # the page reports its end
                    try:
                        if not pygame.mixer.music.get_busy():
                            # Distinguish "just paused" from "track ended" —
                            # paused covered above, so this is end-of-track.
                            self._advance_locked()
                    except Exception:
                        pass
        t = threading.Thread(target=loop, daemon=True, name="snt-monitor")
        t.start()

    # ─── helpers ───────────────────────────────────────────────────
    def _coerce(self, item):
        if not item: return None
        # Remote stream item (Explore mix/podcast): no local file — it's
        # downloaded to cache at play time. Survives the exist-on-disk check.
        if item.get('kind') == 'stream' or (item.get('audio_url') and not (item.get('file_path') or item.get('path'))):
            url = item.get('audio_url')
            if not url:
                return None
            return {
                'kind':       'stream',
                'track_id':   None,
                'file_id':    None,
                'audio_url':  url,
                'title':      item.get('title')  or '',
                'artist':     item.get('artist') or '',
                'duration_sec': item.get('duration_sec'),
                'image_url':  item.get('image_url') or '',
                'url':        item.get('url') or '',     # the page to open ↗
                'place_id':   None,
                'place_name': '',
            }
        # A streamed item (Spotify / SoundCloud / Apple Music): no audio ever
        # reaches this process. The service's own player in the page plays it;
        # this queue only holds its place so owned and streamed records sit in
        # one cue and skip through together.
        if item.get('kind') == 'embed':
            url = (item.get('url') or '').strip()
            if not url.startswith(('http://', 'https://')):
                return None
            return {
                'kind':        'embed',
                'qid':         item.get('qid') or uuid.uuid4().hex[:12],
                'track_id':    None,
                'file_id':     None,
                'url':         url,
                'source':      item.get('source') or '',
                'stream_type': item.get('stream_type') or '',
                'title':       item.get('title')  or '',
                'artist':      item.get('artist') or '',
                'duration_sec': item.get('duration_sec'),
                'image_url':   item.get('image_url') or '',
                'place_id':    None,
                'place_name':  '',
            }
        # Green Room borrow: an encrypted local file + the key that plays it.
        # Survives restore as long as the encrypted file is still on disk
        # (offloading it drops the item from a restored cue, by design).
        if item.get('kind') == 'borrow' or (item.get('gr_path') and not (item.get('file_path') or item.get('path'))):
            p = item.get('gr_path')
            if not p or not os.path.exists(p) or not item.get('gr_key'):
                return None
            return {
                'kind':         'borrow',
                'track_id':     None,
                'file_id':      None,
                'gr_borrow_id': item.get('gr_borrow_id'),
                'gr_path':      p,
                'gr_key':       item.get('gr_key'),
                'gr_nonce':     item.get('gr_nonce'),
                'gr_format':    item.get('gr_format') or '',
                'title':        item.get('title')  or '',
                'artist':       item.get('artist') or '',
                'duration_sec': item.get('duration_sec'),
                'image_url':    item.get('image_url') or '',
                'place_id':     None,
                'place_name':   'Green Room',
            }
        path = item.get('file_path') or item.get('path')
        resolved = self._resolve_path(path) if path else None
        if not resolved or not os.path.exists(resolved):
            return None
        return {
            'kind':     'track',
            'track_id': item.get('track_id'),
            'file_id':  item.get('file_id'),
            'file_path': resolved,
            'title':    item.get('title')  or '',
            'artist':   item.get('artist') or '',
            'duration_sec': item.get('duration_sec'),
            'place_id':   item.get('place_id'),       # where this cue came from
            'place_name': item.get('place_name') or '',
        }

    def _current_position_locked(self):
        if self.idx < 0:        return 0.0
        if self.is_paused:      return self.position
        if self._r_starting:    return self._offset_start   # Spotify hasn't started it yet
        elapsed = time.time() - self._wall_start
        pos = self._offset_start + elapsed
        return max(0.0, pos)

    # ─── play tracking: every start is an EVENT; listened time is accumulated
    # precisely (pauses excluded), completion = >=80% of the track heard ────
    def _evt_close_locked(self):
        e = getattr(self, "_evt", None)
        if not e:
            return
        self._evt = None
        listened = e["listened"]
        if e.get("resumed_at") is not None:
            listened += time.time() - e["resumed_at"]
        dur = e.get("track_dur") or 0
        completed = 1 if (dur and listened >= 0.8 * dur) else 0
        try:
            import sqlite3
            from mr_paths import DB_PATH
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("UPDATE play_events SET duration_listened=?, completed=? WHERE id=?",
                         (round(listened, 1), completed, e["id"]))
            conn.commit(); conn.close()
        except Exception:
            pass

    def _evt_open_locked(self, item):
        # the trial's activity log (server-side, per person): every start
        try:
            from green_room import track as _gr_track
            _gr_track("play", {"track_id": item.get("track_id"), "title": item.get("title"),
                               "artist": item.get("artist"), "kind": item.get("kind") or "track",
                               "source": item.get("source") or None,
                               "via": (self._via or None) if item.get("kind") == "embed" else None,
                               "place": item.get("place_name") or None})
        except Exception:
            pass
        # Remote stream items aren't library tracks — nothing to log against.
        if not item or item.get("kind") == "stream" or not item.get("track_id"):
            self._evt = None
            return
        try:
            import sqlite3
            from mr_paths import DB_PATH
            conn = sqlite3.connect(DB_PATH, timeout=5)
            cur = conn.execute(
                "INSERT INTO play_events (track_id, file_id, source) VALUES (?,?,'seinnteoir')",
                (item.get("track_id"), item.get("file_id")))
            conn.execute(
                "UPDATE tracks SET play_count=COALESCE(play_count,0)+1, "
                "last_played_at=datetime('now') WHERE id=?", (item.get("track_id"),))
            conn.commit()
            eid = cur.lastrowid
            conn.close()
            self._evt = {"id": eid, "listened": 0.0, "resumed_at": time.time(),
                         "track_dur": float(item.get("duration_sec") or 0.0)}
        except Exception:
            self._evt = None

    def _note_error_locked(self, item, reason):
        """Record why a track was skipped so the UI can say so. Never cleared
        on a later success — the frontend dedupes by the 'at' stamp."""
        it = item or {}
        title = (it.get('title')
                 or os.path.basename(str(it.get('file_path') or '')) or 'track')
        self._last_error = {'title': title, 'reason': reason,
                            'at': round(time.time(), 2)}

    def _load_and_play_locked(self, start_sec=0.0):
        self._needs_load = False         # we're loading a real file now
        if not self._mixer_ok:  return
        if self.idx < 0 or self.idx >= len(self.queue): return
        import pygame
        item = self.queue[self.idx]
        if item.get('kind') == 'embed':             # plays in its own service, not here
            self._load_embed_locked(item, start_sec)
            return
        self._via = ''
        self._r_starting = False
        self._remote_release_locked()               # nothing of ours stays sounding in Spotify
        if item.get('kind') == 'stream':            # remote Explore mix/podcast
            self._load_stream_locked(item, start_sec)
            return
        if item.get('kind') == 'borrow':            # Green Room encrypted borrow
            self._load_borrow_locked(item, start_sec)
            return
        path = item.get('file_path')
        if not path or not os.path.exists(path):
            self._note_error_locked(item, "file missing — is its drive connected?")
            self._advance_locked()
            return
        if not _pygame_can_decode(path):             # M4A/AAC — play an OGG transcode
            self._load_transcoded_locked(item, path, start_sec)
            return
        try:
            self._evt_close_locked()                 # the previous listen ends here
            pygame.mixer.music.load(path)
            # pygame's `start=` arg works for MP3/OGG; FLAC seek is buggy in
            # SDL_mixer so on FLAC the seek may snap to 0.
            pygame.mixer.music.play(start=float(max(0.0, start_sec)))
            self._wall_start    = time.time()
            self._offset_start  = float(max(0.0, start_sec))
            self.position       = float(max(0.0, start_sec))
            self.is_paused      = False
            self._buffering     = False
            self.duration_sec   = float(item.get('duration_sec') or 0.0)
            self._evt_open_locked(item)              # …and this one begins
        except Exception as e:
            print(f"[seinnteoir] failed to load {path}: {e}")
            self._note_error_locked(item, "couldn't decode this file")
            self._advance_locked()

    # ─── streamed items: the mixer goes quiet and the service takes over ──────
    # Two ways one can sound. 'remote': a Spotify record, in the listener's own
    # Spotify, told what to do from here (whole tracks; needs their sign-in and
    # Premium). 'page': the service's own player on a slip beside the deck
    # (snt_embed.js) — SoundCloud always, Spotify when the remote can't.
    def _load_embed_locked(self, item, start_sec=0.0):
        self._evt_close_locked()
        try:
            import pygame; pygame.mixer.music.stop()
        except Exception:
            pass
        start_sec = float(max(0.0, start_sec))
        was_paused = self.is_paused
        remote = bool(self._remote and self._remote.can_take(item))
        # the same record, already sounding in Spotify: move within it, don't restart it
        same = bool(remote and self._via == 'remote' and self._r_started and self._r_live
                    and self._r_qid == item.get('qid'))
        if not remote:
            self._remote_release_locked()
        self._via          = 'remote' if remote else 'page'
        self._r_note       = ''
        self._wall_start   = time.time()
        self._offset_start = start_sec
        self.position      = start_sec
        self.is_paused     = False
        self._buffering    = False
        self.duration_sec  = float(item.get('duration_sec') or 0.0)
        self._embed_seq   += 1
        if same:
            self._r_maxpos = 0.0
            self._r_tight  = False
            self._rq_put(('seek', start_sec, was_paused))
        elif remote:
            self._guest      = None
            self._r_live     = True
            self._r_starting = True
            self._r_started  = False
            self._r_adopted  = False
            self._r_seen     = False
            self._r_now      = None
            self._r_qid      = item.get('qid')
            self._r_maxpos   = 0.0
            self._r_tight    = False
            self._rq_put(('play', item.get('qid'), start_sec))
        else:
            self._r_starting = False
        self._evt_open_locked(item)

    def _cur_embed_locked(self):
        if 0 <= self.idx < len(self.queue) and self.queue[self.idx].get('kind') == 'embed':
            return self.queue[self.idx]
        return None

    def embed_report(self, qid, position=None, duration=None, paused=None, ended=False):
        """The page's player telling us where a streamed item really is — its
        clock is the truth, ours is a guess. `ended` moves the cue on."""
        with self._lock:
            item = self._cur_embed_locked()
            if not item or item.get('qid') != qid:
                return False
            if self._via == 'remote':
                return False                # Spotify itself is the clock for this one
            if ended:
                self._advance_locked()
                return True
            if duration:
                self.duration_sec = float(duration)
                item['duration_sec'] = round(float(duration), 1)
            if paused is not None:
                self.is_paused = bool(paused)
            if position is not None:
                self.position      = float(max(0.0, position))
                self._offset_start = self.position
                self._wall_start   = time.time()
            return True

    # ─── Green Room borrows: the file on disk is encrypted; decrypt to memory
    # and hand pygame the bytes. The plain audio never touches the disk — that
    # is the whole point of the lock. ─────────────────────────────────────────
    def _load_borrow_locked(self, item, start_sec=0.0):
        import io
        import pygame
        fmt = (item.get('gr_format') or '').lower()
        if fmt in ('m4a', 'aac', 'mp4'):
            # decrypt→transcode would write plain audio to the cache dir —
            # keep m4a out of the Green Room pool instead.
            self._note_error_locked(item, "m4a can't play as a borrow yet")
            self._advance_locked()
            return
        try:
            from green_room import decrypt_file
            data = decrypt_file(item['gr_path'], item['gr_key'], item['gr_nonce'])
        except Exception as e:
            print(f"[seinnteoir] borrow decrypt failed: {e}")
            self._note_error_locked(item, "couldn't unlock this borrowed track")
            self._advance_locked()
            return
        try:
            self._evt_close_locked()                 # the previous listen ends here
            # namehint tells SDL_mixer which decoder the bytes want
            pygame.mixer.music.load(io.BytesIO(data), f"borrow.{fmt or 'mp3'}")
            pygame.mixer.music.play(start=float(max(0.0, start_sec)))
            self._wall_start    = time.time()
            self._offset_start  = float(max(0.0, start_sec))
            self.position       = float(max(0.0, start_sec))
            self.is_paused      = False
            self._buffering     = False
            self.duration_sec   = float(item.get('duration_sec') or 0.0)
            self._evt = None    # borrows aren't library tracks — no play_events row
        except Exception as e:
            print(f"[seinnteoir] failed to load borrow {item.get('title')}: {e}")
            self._note_error_locked(item, "couldn't decode this borrowed track")
            self._advance_locked()

    # ─── remote streams: pygame can't play a URL, so download to cache first,
    # then play the cached file. The persistent player otherwise behaves the
    # same (pause/skip/seek), so a mix lives in the one continuous queue. ────
    def _cache_path_for(self, url):
        if not _STREAM_CACHE_DIR or not url:
            return None
        h = hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()[:20]
        ext = ".mp3"
        for e in (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac"):
            if e in url.lower():
                ext = e
                break
        return os.path.join(_STREAM_CACHE_DIR, h + ext)

    def _play_file_locked(self, path, start_sec=0.0):
        """Load + play a ready local file (a cached stream, here)."""
        import pygame
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(start=float(max(0.0, start_sec)))
            self._wall_start   = time.time()
            self._offset_start = float(max(0.0, start_sec))
            self.position      = float(max(0.0, start_sec))
            self.is_paused     = False
            self._buffering    = False
        except Exception as e:
            print(f"[seinnteoir] failed to play cached stream {path}: {e}")
            if 0 <= self.idx < len(self.queue):
                self._note_error_locked(self.queue[self.idx], "couldn't play this")
            self._advance_locked()

    def _load_stream_locked(self, item, start_sec=0.0):
        self._evt_close_locked()                     # the previous listen ends here
        self._evt = None                             # streams aren't logged
        url   = item.get('audio_url')
        cache = self._cache_path_for(url)
        self.duration_sec = float(item.get('duration_sec') or 0.0)
        # already cached → play immediately, exactly like a library file
        if cache and os.path.exists(cache) and os.path.getsize(cache) > 0 and url not in self._downloading:
            self._play_file_locked(cache, start_sec)
            return
        # not cached → buffer; a worker downloads it then begins playback
        self._buffering = True
        self.is_paused  = True                       # silent until the file lands
        self.position   = float(max(0.0, start_sec))
        if not url or url in self._downloading:
            return
        self._downloading.add(url)
        threading.Thread(
            target=self._download_then_play,
            args=(url, cache, self.idx, float(max(0.0, start_sec))),
            daemon=True, name="snt-stream-dl").start()

    def _download_then_play(self, url, cache, target_idx, start_sec):
        ok = False
        try:
            if cache and os.path.exists(cache) and os.path.getsize(cache) > 0:
                ok = True
            elif cache:
                tmp = cache + ".part"
                req = urllib.request.Request(url, headers={"User-Agent": _STREAM_UA})
                with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as fh:
                    total = 0
                    while True:
                        chunk = r.read(262144)
                        if not chunk:
                            break
                        fh.write(chunk)
                        total += len(chunk)
                        if total > 500 * 1024 * 1024:        # 500 MB cap per mix
                            break
                os.replace(tmp, cache)
                ok = os.path.getsize(cache) > 0
        except Exception as e:
            print(f"[seinnteoir] stream download failed {url}: {e}")
            try:
                if cache and os.path.exists(cache + ".part"):
                    os.remove(cache + ".part")
            except Exception:
                pass
        finally:
            self._downloading.discard(url)
        with self._lock:
            # only act if the user hasn't moved on to a different item meanwhile
            if self.idx != target_idx or not (0 <= self.idx < len(self.queue)):
                return
            if self.queue[self.idx].get('audio_url') != url:
                return
            self._buffering = False
            if not ok:
                self._note_error_locked(self.queue[self.idx],
                                        "download failed — is the internet up?")
                self._advance_locked()
                return
            self._play_file_locked(cache, start_sec)
            self._evict_cache()

    def _evict_cache(self):
        """Keep the stream cache under the cap — oldest evicted first, never a
        file that's in the live queue."""
        if not _STREAM_CACHE_DIR:
            return
        try:
            live = {self._cache_path_for(q.get('audio_url'))
                    for q in self.queue if q.get('kind') == 'stream'}
            files, total = [], 0
            for n in os.listdir(_STREAM_CACHE_DIR):
                p = os.path.join(_STREAM_CACHE_DIR, n)
                if not os.path.isfile(p) or p.endswith(".part"):
                    continue
                st = os.stat(p)
                files.append((st.st_mtime, st.st_size, p))
                total += st.st_size
            for _, size, p in sorted(files):
                if total <= _STREAM_CACHE_CAP:
                    break
                if p in live:
                    continue
                try:
                    os.remove(p)
                    total -= size
                except Exception:
                    pass
        except Exception:
            pass

    # ─── M4A / AAC: transcode once to a playable OGG ─────────────────────────
    # SDL_mixer can't decode MP4/AAC, so a library .m4a is decoded by ffmpeg to
    # a small OGG (cached, keyed by path+mtime) which pygame plays + seeks
    # perfectly. The first play shows "buffering…" while ffmpeg runs; replays
    # are instant. Mirrors the remote-stream download flow.
    def _transcode_cache_path(self, path):
        if not _PLAYBACK_CACHE_DIR or not path:
            return None
        try:
            mt = int(os.path.getmtime(path))
        except Exception:
            mt = 0
        h = hashlib.sha1(f"{path}:{mt}".encode("utf-8", "ignore")).hexdigest()[:20]
        return os.path.join(_PLAYBACK_CACHE_DIR, h + ".ogg")

    def _load_transcoded_locked(self, item, path, start_sec=0.0):
        cache = self._transcode_cache_path(path)
        self.duration_sec = float(item.get('duration_sec') or 0.0)
        # already transcoded (and not mid-transcode) → play immediately
        if cache and os.path.exists(cache) and os.path.getsize(cache) > 0 \
                and path not in self._transcoding:
            self._evt_close_locked()
            self._play_file_locked(cache, start_sec)
            self._evt_open_locked(item)
            return
        # not yet → buffer; a worker transcodes then begins playback
        self._evt_close_locked()
        self._buffering = True
        self.is_paused  = True
        self.position   = float(max(0.0, start_sec))
        if not cache:
            self._buffering = False
            self._note_error_locked(item, "couldn't convert this file")
            self._advance_locked()
            return
        # one transcode per source at a time — a seek/play_at mid-buffer must NOT
        # spawn a second ffmpeg racing on the same cache file. The in-flight
        # worker plays the result when it lands (mirrors the stream _downloading
        # guard).
        if path in self._transcoding:
            return
        self._transcoding.add(path)
        threading.Thread(
            target=self._transcode_then_play,
            args=(path, cache, self.idx, float(max(0.0, start_sec))),
            daemon=True, name="snt-transcode").start()

    def _transcode_then_play(self, path, cache, target_idx, start_sec):
        import subprocess
        ok = False
        err_reason = "couldn't convert this file"
        try:
            if cache and os.path.exists(cache) and os.path.getsize(cache) > 0:
                ok = True
            elif cache:
                from mr_ffmpeg import ffmpeg_path
                ffmpeg = ffmpeg_path()
                if not ffmpeg:
                    raise RuntimeError(
                        "ffmpeg not found — m4a/AAC playback needs it")
                os.makedirs(_PLAYBACK_CACHE_DIR, exist_ok=True)
                # per-job temp name so even a future double-entry can't collide
                tmp = cache + f".{os.getpid()}.{threading.get_ident()}.part"
                r = subprocess.run(
                    [ffmpeg, "-y", "-i", path, "-vn",
                     "-c:a", "libvorbis", "-q:a", "6",
                     "-f", "ogg", tmp],   # explicit muxer — the .part ext can't infer it
                    capture_output=True, timeout=600)
                if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                    os.replace(tmp, cache)
                    ok = True
                else:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[seinnteoir] transcode failed {path}: {e}")
            if "ffmpeg not found" in str(e):
                err_reason = "ffmpeg missing — this format needs it"
        with self._lock:
            self._transcoding.discard(path)      # clear the guard atomically with play
            # only act if the user hasn't moved on to a different item meanwhile
            if self.idx != target_idx or not (0 <= self.idx < len(self.queue)):
                return
            if self.queue[self.idx].get('file_path') != path:
                return
            self._buffering = False
            if not ok:
                self._note_error_locked(self.queue[self.idx], err_reason)
                self._advance_locked()
                return
            self._play_file_locked(cache, start_sec)
            self._evt_open_locked(self.queue[self.idx])
            self._evict_transcode_cache()

    def _evict_transcode_cache(self):
        """Keep the transcode cache under its cap — oldest first, never a file
        whose source is in the live queue."""
        if not _PLAYBACK_CACHE_DIR:
            return
        try:
            live = {self._transcode_cache_path(q.get('file_path'))
                    for q in self.queue if q.get('kind') != 'stream' and q.get('file_path')}
            files, total = [], 0
            for n in os.listdir(_PLAYBACK_CACHE_DIR):
                p = os.path.join(_PLAYBACK_CACHE_DIR, n)
                if not os.path.isfile(p) or p.endswith(".part"):
                    continue
                st = os.stat(p)
                files.append((st.st_mtime, st.st_size, p))
                total += st.st_size
            for _, size, p in sorted(files):
                if total <= _TRANSCODE_CACHE_CAP:
                    break
                if p in live:
                    continue
                try:
                    os.remove(p)
                    total -= size
                except Exception:
                    pass
        except Exception:
            pass

    def _advance_locked(self):
        if self.idx + 1 < len(self.queue):
            self.idx += 1
            self.position = 0.0
            self._load_and_play_locked(0.0)
        else:
            # End of queue — stop cleanly (and close the final listen)
            self._evt_close_locked()
            import pygame
            try: pygame.mixer.music.stop()
            except Exception: pass
            self._r_starting = False
            self._remote_release_locked()
            self.is_paused = True
            self.position  = 0.0
        self._persist_locked()

    # ─── public API (called from Flask routes) ─────────────────────
    def _fade_if_playing_locked(self):
        """Quick fade-OUT before a user-chosen switch mid-play. The next track
        starts at full volume — never fade in."""
        try:
            import pygame
            if self.idx >= 0 and not self.is_paused and pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(300)
                time.sleep(0.32)
        except Exception:
            pass

    def _coerce_all_locked(self, items):
        """Coerce a batch; a track whose file can't be found on disk is dropped
        — but VISIBLY (it used to vanish with no trace, reading as 'clicking
        does nothing' when the drive is unplugged)."""
        coerced, dropped = [], []
        for i in (items or []):
            c = self._coerce(i)
            if c:
                coerced.append(c)
            elif i:
                dropped.append(i)
        if dropped:
            first = dropped[0] if isinstance(dropped[0], dict) else {}
            title = first.get('title') or 'track'
            if len(dropped) > 1:
                title += f" (+{len(dropped) - 1} more)"
            self._note_error_locked({'title': title},
                                    "file missing — is its drive connected?")
        return coerced

    def set_queue(self, items, idx=0, autoplay=True):
        with self._lock:
            coerced = self._coerce_all_locked(items)
            if coerced and autoplay:
                self._fade_if_playing_locked()
            self.queue = coerced
            self.idx   = max(0, min(idx, len(coerced) - 1)) if coerced else -1
            self.position = 0.0
            if self.idx >= 0 and autoplay:
                self._load_and_play_locked(0.0)
            else:
                try:
                    import pygame; pygame.mixer.music.stop()
                except Exception: pass
                self._via = ''
                self._r_starting = False
                self._remote_release_locked()
                self.is_paused = True
            self._persist_locked()

    def add(self, items, autostart=True):
        """Append to the queue. autostart=False cues silently even when the
        queue was empty — the 3D room's cue-up flow (never autoplay there)."""
        with self._lock:
            coerced = self._coerce_all_locked(items)
            if not coerced: return 0
            was_empty = (len(self.queue) == 0)
            self.queue.extend(coerced)
            if was_empty and autostart:
                self.idx = 0
                self._load_and_play_locked(0.0)
            # (cued silently: idx stays -1, so a later play() loads track 0)
            self._persist_locked()
            return len(coerced)

    def play(self):
        with self._lock:
            import pygame
            if self._buffering:           # a stream is downloading; nothing to unpause
                return
            if self.idx < 0 and self.queue:
                self.idx = 0
                self._load_and_play_locked(0.0)
                return
            if self.idx < 0: return
            if self._needs_load:
                # restored cue: nothing in the mixer yet → load fresh, not unpause
                self._load_and_play_locked(self.position)
                return
            if self._cur_embed_locked():       # its own service resumes it; we keep time
                if self.is_paused:
                    self._wall_start   = time.time()
                    self._offset_start = self.position
                    self.is_paused     = False
                    if self._via == 'remote':
                        self._guest  = None
                        self._r_live = True
                        self._rq_put(('resume', self._cur_embed_locked().get('qid'), self.position))
                return
            if self.is_paused:
                try:
                    pygame.mixer.music.unpause()
                except Exception:
                    # Sometimes after stop() we need a fresh load+play
                    self._load_and_play_locked(self.position)
                    return
                self._wall_start   = time.time()
                self._offset_start = self.position
                self.is_paused     = False
                e = getattr(self, "_evt", None)        # the listen clock resumes
                if e and e.get("resumed_at") is None:
                    e["resumed_at"] = time.time()

    def pause(self, fade_ms=0):
        with self._lock:
            if self.is_paused or self.idx < 0: return
            self.position = self._current_position_locked()
            if self._cur_embed_locked():
                self.is_paused = True
                if self._via == 'remote':
                    self._rq_put(('pause',))
                return
            try:
                import pygame
                if fade_ms:
                    # fade DOWN to the pause (volume ramp, then restore the
                    # dial for the next play) — the record never overlaps
                    v0 = self.volume
                    steps = 6
                    for s in range(steps):
                        pygame.mixer.music.set_volume(v0 * (1 - (s + 1) / steps))
                        time.sleep(fade_ms / 1000.0 / steps)
                    pygame.mixer.music.pause()
                    pygame.mixer.music.set_volume(v0)
                else:
                    pygame.mixer.music.pause()
            except Exception: pass
            self.is_paused = True
            e = getattr(self, "_evt", None)            # the listen clock holds
            if e and e.get("resumed_at") is not None:
                e["listened"] += time.time() - e["resumed_at"]
                e["resumed_at"] = None

    def toggle(self):
        with self._lock:
            if self.is_paused: self.play()
            else:              self.pause()

    def next(self):
        with self._lock:
            self._advance_locked()

    def prev(self):
        with self._lock:
            # Same UX as most players: if past 3 s into the track, restart;
            # otherwise jump to previous.
            cur = self._current_position_locked()
            if cur > 3.0 or self.idx <= 0:
                self._load_and_play_locked(0.0)
            else:
                self.idx -= 1
                self.position = 0.0
                self._load_and_play_locked(0.0)
            self._persist_locked()

    def seek(self, sec):
        with self._lock:
            if self.idx < 0: return
            self._load_and_play_locked(float(max(0.0, sec)))

    def set_volume(self, v):
        with self._lock:
            v = max(0.0, min(1.0, float(v)))
            self.volume = v
            try:
                import pygame; pygame.mixer.music.set_volume(v)
            except Exception: pass
            if self._via == 'remote' and self._r_live:
                self._rq_put(('volume', v))        # Spotify's own dial follows the deck's

    def play_at(self, i):
        with self._lock:
            if 0 <= i < len(self.queue):
                self._fade_if_playing_locked()   # user picked a different record → fade out, then play
                self.idx = i
                self.position = 0.0
                self._load_and_play_locked(0.0)
                self._persist_locked()

    def remove(self, i):
        with self._lock:
            if not (0 <= i < len(self.queue)): return
            was_current = (i == self.idx)
            del self.queue[i]
            if i < self.idx: self.idx -= 1
            if not self.queue:
                self.clear(); return
            if was_current:
                self.idx = min(self.idx, len(self.queue) - 1)
                self.position = 0.0
                self._load_and_play_locked(0.0)
            self._persist_locked()

    def clear(self):
        with self._lock:
            self._evt_close_locked()
            try:
                import pygame; pygame.mixer.music.stop()
            except Exception: pass
            self._via = ''
            self._r_starting = False
            self._remote_release_locked()
            self.queue    = []
            self.idx      = -1
            self.position = 0.0
            self.is_paused = True
            self._persist_locked()

    def move(self, from_idx, to_idx):
        """Move one cue row to another position. By index, so it works for any
        mix of owned, borrowed and streamed items (reorder() keys on track_id,
        which streamed items don't have)."""
        with self._lock:
            n = len(self.queue)
            if not (0 <= from_idx < n): return
            to_idx = max(0, min(n - 1, int(to_idx)))
            if to_idx == from_idx: return
            cur = self.queue[self.idx] if 0 <= self.idx < n else None
            it = self.queue.pop(from_idx)
            self.queue.insert(to_idx, it)
            if cur is not None:
                for k, q in enumerate(self.queue):
                    if q is cur:
                        self.idx = k
                        break
            self._persist_locked()

    def reorder(self, order_track_ids):
        """Replace the queue order to match the given list of track_ids."""
        with self._lock:
            if not self.queue or not order_track_ids: return
            # reorder keys on track_id; remote stream items have none → leave a
            # mixed queue untouched (mixes are played, not reordered, for now).
            if any(q.get('track_id') is None for q in self.queue): return
            current_id = self.queue[self.idx]['track_id'] if self.idx >= 0 else None
            by_id = {q['track_id']: q for q in self.queue}
            new_q = [by_id[tid] for tid in order_track_ids if tid in by_id]
            # Append any items not in the order list (shouldn't happen but safe)
            for q in self.queue:
                if q['track_id'] not in set(order_track_ids):
                    new_q.append(q)
            self.queue = new_q
            if current_id is not None:
                for n, q in enumerate(self.queue):
                    if q['track_id'] == current_id:
                        self.idx = n
                        break
            self._persist_locked()

    def get_state(self):
        with self._lock:
            # Serialize queue without the resolved file_path (browser doesn't need it)
            queue_out = [{
                'track_id': q.get('track_id'),
                'file_id':  q.get('file_id'),
                'kind':     q.get('kind') or 'track',
                'title':    q.get('title'),
                'artist':   q.get('artist'),
                'duration_sec': q.get('duration_sec'),
                'place_id':   q.get('place_id'),
                'place_name': q.get('place_name') or '',
                'image_url':  q.get('image_url') or '',   # stream art (Explore)
                'url':        q.get('url') or '',          # stream page to open ↗
                'qid':        q.get('qid') or '',          # a streamed item's identity
                'source':     q.get('source') or '',       # spotify | soundcloud
                'stream_type': q.get('stream_type') or '', # track | album | playlist | …
            } for q in self.queue]
            self._seen_at = time.time()
            streamed = self._cur_embed_locked() is not None
            deck_playing = (not self.is_paused) and self.idx >= 0
            guest = None
            if self._guest and not deck_playing:
                g = self._guest
                guest = {'source': 'spotify', 'title': g.get('title') or '', 'artist': g.get('artist') or '',
                         'image_url': g.get('image_url') or '', 'url': g.get('url') or '',
                         'by_ids': g.get('artist_ids') or '', 'playing': bool(g.get('playing')),
                         'position': round(self._guest_pos_locked(), 2),
                         'duration': round(g.get('duration') or 0.0, 2), 'device': g.get('device') or '',
                         # can the deck's keys drive it? (no for a listener without Premium:
                         # then it is only shown where it can be kept — the grúpa's "now" line)
                         'control': bool(self._remote is not None and self._remote.ready())}
            return {
                'queue':    queue_out,
                'idx':      self.idx,
                'position': round(self._current_position_locked(), 2),
                'duration': round(self.duration_sec, 2),
                'playing':  (not self.is_paused) and self.idx >= 0,
                'buffering': self._buffering or self._r_starting,
                'volume':   self.volume,
                'mixer_ok': self._mixer_ok,
                'last_error': self._last_error,
                'ui_mode':  self.ui_mode,   # survives relaunch (localStorage doesn't)
                'embed_seq': self._embed_seq,
                # a streamed record: 'remote' = sounding in the listener's own
                # Spotify (no player in the page), 'page' = the service's player
                'embed_via': self._via if streamed else '',
                'remote':   ({'device': self._r_dev, 'note': self._r_note,
                              # an album / playlist playing in Spotify: the track it is on
                              'title':  (self._r_now or {}).get('title', '') if self._via == 'remote' else '',
                              'artist': (self._r_now or {}).get('artist', '') if self._via == 'remote' else ''}
                             if streamed else None),
                # the listener's Spotify playing something of its own while the
                # deck is at rest — the deck shows it and its keys drive it
                'guest':    guest,
            }

    # ═══════════════════════════════════════════════════════════════════
    # THE LISTENER'S OWN SPOTIFY
    # A worker thread carries the deck's wishes to Spotify (network calls
    # never run under the deck's lock) and keeps the deck's clock true to
    # what Spotify is really doing. Three jobs:
    #   · a Spotify record in the cue → play it there, follow it, and hand
    #     over to whatever is next a breath before it ends (so Spotify's own
    #     "autoplay" never gets to choose the next song);
    #   · notice when the listener pauses, resumes or changes it in Spotify;
    #   · when the deck is at rest and Spotify is playing on its own, show
    #     that on the deck ('guest') so the same keys drive it.
    # ═══════════════════════════════════════════════════════════════════
    def set_remote(self, driver):
        with self._lock:
            self._remote = driver
        if driver is not None and self._remote_thread is None:
            def loop():
                while True:
                    self._rq_evt.wait(0.25)
                    self._rq_evt.clear()
                    try:
                        self._remote_step()
                    except Exception as e:
                        print(f"[seinnteoir] remote: {e}")
            self._remote_thread = threading.Thread(target=loop, daemon=True, name="snt-remote")
            self._remote_thread.start()

    def _rq_put(self, cmd):
        """Queue a command for Spotify (the lock is held). A newer wish replaces
        the older ones it makes pointless."""
        if self._remote is None:
            return
        kind = cmd[0]
        drop = {'play': ('play', 'resume', 'pause', 'stop', 'seek', 'quiet'),
                'resume': ('play', 'resume', 'pause', 'stop', 'quiet'),
                'stop': ('play', 'resume', 'pause', 'seek', 'stop', 'quiet'),
                'quiet': ('quiet',),
                'pause': ('pause',), 'seek': ('seek',), 'volume': ('volume',)}.get(kind, ())
        if drop:
            self._rq = collections.deque(c for c in self._rq if c[0] not in drop)
        self._rq.append(cmd)
        self._rq_evt.set()

    def _remote_release_locked(self):
        """What plays next isn't in Spotify: quiet it there — a record of ours
        still sounding, or the listener's own listening the deck is about to
        play over. (A listener without Premium can't be quieted from here.)"""
        # (the listener's own listening is only quieted when it is on a computer —
        # never their phone or a speaker in another room)
        g = self._guest
        if self._r_live or (g and g.get('playing') and (g.get('device_type') or 'Computer') == 'Computer'):
            self._rq_put(('stop',))
        elif g is None and self._remote is not None and self._remote.ready():
            self._rq_put(('quiet',))            # not seen playing — look once, and quiet it if it is
        self._r_live = False
        self._r_started = False
        self._guest = None

    def _guest_pos_locked(self):
        g = self._guest
        if not g:
            return 0.0
        p = g.get('position') or 0.0
        if g.get('playing'):
            p += time.time() - (g.get('at') or time.time())
        d = g.get('duration') or 0.0
        return max(0.0, min(p, d) if d else p)

    def _remote_step(self):
        drv = self._remote
        if drv is None:
            return
        while True:
            with self._lock:
                cmd = self._rq.popleft() if self._rq else None
            if cmd is None:
                break
            self._remote_do(drv, cmd)
        self._remote_clock(drv)

    @staticmethod
    def _remote_log(msg):
        """One line per thing the deck tells Spotify (never the polling) — in
        the server log, so a tester's "it played the wrong thing" can be read
        back afterwards."""
        print(f"[spotify-remote] {msg}", flush=True)

    def _remote_do(self, drv, cmd):
        what = cmd[0]
        if what in ('play', 'resume'):
            qid, start = cmd[1], float(cmd[2] or 0.0)
            with self._lock:
                cur = self._cur_embed_locked()
                if not cur or cur.get('qid') != qid or self._via != 'remote':
                    self._r_starting = False
                    return                          # the cue moved on before we got to it
                item = dict(cur)
            from spotify_remote import uri_of
            how, uri = uri_of(item.get('url'))
            ok, why = False, ''
            if what == 'resume':
                # pick it up where it rests — unless Spotify has moved to something else
                st = drv.state()
                with self._lock:
                    self._r_uri, self._r_many = (self._r_uri or uri), (how == 'many')
                    ours = bool(st) and self._remote_is_ours_locked(st)
                if ours:
                    ok = drv.resume()
                    self._remote_log(f"resume “{item.get('title')}” → {'ok' if ok else 'no'}")
            if not ok:
                ok, why = drv.play(item, start)
                self._remote_log(f"play “{item.get('title')}” {uri} from {start:.0f}s → {'ok' if ok else why}")
            now = time.time()
            with self._lock:
                self._r_starting = False
                cur = self._cur_embed_locked()
                still = bool(cur and cur.get('qid') == qid and self._via == 'remote')
                if ok:
                    self._r_cmd_at  = now
                    self._r_poll_at = now + 1.2
                    self._r_dev     = drv.device_name or self._r_dev
                    if still:
                        self._r_started = True
                        self._r_live    = True
                        if what == 'play' or not self._r_uri:
                            self._r_uri, self._r_many, self._r_adopted = uri, (how == 'many'), False
                        if self.is_paused:
                            self._rq_put(('pause',))            # paused while it was starting
                        else:
                            self._wall_start   = now            # it is sounding from now
                            self._offset_start = self.position = (start if (what == 'play' and how == 'one') or what == 'resume' else 0.0)
                    elif not (cur and self._via == 'remote'):
                        self._rq_put(('stop',))                 # nothing of ours wants Spotify any more
                elif still:
                    # Spotify can't take it (not open, no Premium, …): the page's player does
                    self._via, self._r_live, self._r_started = 'page', False, False
                    self._r_note = why or 'refused'
                    self._wall_start = now
                    self._embed_seq += 1
            return
        if what == 'quiet':
            # the deck is starting something of its own: if the listener's Spotify
            # is sounding on a computer, quiet it (a phone or a speaker is left be)
            st = drv.state()
            if st and st.get('playing') and (st.get('device_type') or 'Computer') == 'Computer':
                r = drv.pause()
                self._remote_log(f"your Spotify was playing — quieted for the deck → {'ok' if r else 'no'}")
            return
        if what in ('pause', 'stop'):
            r = drv.pause()
            self._remote_log(f"{what} → {'ok' if r else 'no (already quiet?)'}")
        elif what == 'seek':
            r = drv.seek(cmd[1])
            self._remote_log(f"seek to {cmd[1]:.0f}s → {'ok' if r else 'no'}")
            if len(cmd) > 2 and cmd[2]:
                drv.resume()                        # a seek on a resting deck starts it (as for files)
        elif what == 'volume':
            drv.volume(cmd[1])
            self._r_vol_sent = cmd[1]
        elif what == 'guest':
            act, val = cmd[1], (cmd[2] if len(cmd) > 2 else None)
            if   act == 'pause': r = drv.pause()
            elif act == 'play':  r = drv.resume()
            elif act == 'next':  r = drv.next()
            elif act == 'prev':  r = drv.previous()
            elif act == 'seek':  r = drv.seek(float(val or 0.0))
            else:                r = False
            self._remote_log(f"your Spotify: {act} → {'ok' if r else 'no'}")
            with self._lock:
                self._guest_poll_at = time.time() + (0.8 if act in ('next', 'prev', 'seek') else 1.5)
            return
        with self._lock:
            self._r_cmd_at = time.time()

    def _remote_is_ours_locked(self, st):
        if self._r_many:
            if st.get('context_uri'):
                return st.get('context_uri') == self._r_uri
            # an ARTIST element: Spotify plays that artist's tracks but names no
            # context at all (seen against the real thing) — it is ours while
            # what is playing is by that artist
            if self._r_uri.startswith('spotify:artist:'):
                return self._r_uri.rsplit(':', 1)[1] in (st.get('artist_ids') or '').split(',')
            return False
        if st.get('uri') and st.get('uri') == self._r_uri:
            return True
        # Spotify sometimes plays the same recording under another id (a
        # regional copy). The first look after our own "play", with no playlist
        # behind it, the clock where ours is AND the same name or length, is
        # ours. (Name/length matter: Spotify can also answer "yes" to a play
        # and carry on with a different record altogether — that is not ours.)
        if (not self._r_adopted and st.get('uri') and not st.get('context_uri') and st.get('playing')
                and time.time() - self._r_cmd_at < 9.0
                and abs((st.get('position') or 0.0) - self._current_position_locked()) < 6.0
                and self._remote_same_record_locked(st)):
            self._r_uri, self._r_adopted = st['uri'], True
            return True
        return False

    def _remote_same_record_locked(self, st):
        cur = self._cur_embed_locked() or {}
        norm = lambda x: re.sub(r'[^a-z0-9]+', '', (x or '').lower())
        mine, theirs = norm(cur.get('title')), norm(st.get('title'))
        want, got = float(cur.get('duration_sec') or 0.0), float(st.get('duration') or 0.0)
        if mine and theirs and (mine == theirs or (min(len(mine), len(theirs)) >= 4 and (mine.startswith(theirs) or theirs.startswith(mine)))):
            return True
        if want and got:
            return abs(want - got) <= 2.0
        return not (mine and theirs)            # nothing to compare by: take its word

    def _remote_clock(self, drv):
        now = time.time()
        with self._lock:
            if self._rq:
                return                              # a wish is waiting; act on it first
            cur = self._cur_embed_locked()
            # ours to follow: a Spotify record of ours that is sounding, or resting
            # where we (or the listener) paused it. Once Spotify has gone on to
            # something else (_r_live False) it is the listener's own listening
            # again — the guest watch below takes over.
            mine = bool(cur and self._via == 'remote' and self._r_started
                        and ((not self.is_paused) or self._r_live))
            qid = cur.get('qid') if cur else None
            playing = mine and not self.is_paused
            left = (self.duration_sec - self._current_position_locked()) if (mine and self.duration_sec > 0) else None
            settled = now - self._r_cmd_at > 1.0
            deck_playing = (not self.is_paused) and self.idx >= 0
            watched = now - self._seen_at < 6.0
            look = False
            if mine:
                # hand over a breath before a single track ends: the next record
                # starts (or Spotify is quieted) before its autoplay can choose
                if playing and settled and not self._r_many and left is not None and left <= 0.30:
                    self._advance_locked()
                    return
                look = now >= self._r_poll_at
                if playing and not self._r_many and left is not None and 2.2 <= left <= 3.4 and not self._r_tight:
                    look, self._r_tight = True, True    # one close look, to time the hand-over
                if look:
                    self._r_poll_at = now + 3.0
            else:
                if deck_playing:
                    self._guest = None
                    return
                if not watched or now < self._guest_poll_at:
                    return
                self._guest_poll_at = now + (5.0 if self._guest else 15.0)
        if mine:
            if look:
                self._remote_apply(qid, drv.state())
            return
        if not drv.can_see():
            with self._lock:
                self._guest = None
            return
        self._guest_apply(drv.state())

    def _remote_apply(self, qid, st):
        """Spotify's answer about a record of ours → the deck's clock and state."""
        now = time.time()
        with self._lock:
            cur = self._cur_embed_locked()
            if not cur or cur.get('qid') != qid or self._via != 'remote' or st is None:
                return                              # moved on, or couldn't ask: keep our own count
            if st.get('device'):
                self._r_dev = st['device']
            settling = now - self._r_cmd_at < 1.6
            pos_now = self._current_position_locked()
            if self._remote_is_ours_locked(st):
                self._r_seen = True
                if self._r_many:                    # an album / playlist: say which of its tracks is on
                    self._r_now = {'title': st.get('title') or '', 'artist': st.get('artist') or ''}
                dur = st.get('duration') or 0.0
                p = st.get('position') or 0.0
                if dur:
                    self.duration_sec = dur
                    if not self._r_many:
                        cur['duration_sec'] = round(dur, 1)
                if st.get('playing'):
                    self._r_maxpos = max(self._r_maxpos, p)
                    if self.is_paused:
                        if settling:
                            return                  # our pause hasn't landed yet
                        self.is_paused = False      # started again from Spotify itself
                    self.position = self._offset_start = p
                    self._wall_start = now
                    return
                if self.is_paused:
                    if not settling:
                        self.position = p
                    return
                if settling:
                    return                          # our play hasn't landed yet
                if (p < 1.0 and self._r_maxpos > 2.0) or (dur and p >= dur - 1.0):
                    self._advance_locked()          # it played out
                else:
                    self.position, self.is_paused = p, True     # paused from Spotify itself
                return
            # Spotify is on something else, or on nothing
            if settling:
                self._r_poll_at = now + 0.9         # look again soon: has our record taken?
                return
            if self.is_paused:
                self._r_live = False
                return
            if not self._r_seen:
                # Spotify said yes to our "play" but has not been on this record
                # at all. Give it a few seconds, then move on — and quiet
                # whatever it did start instead.
                if now - self._r_cmd_at < 3.5:
                    self._r_poll_at = now + 1.0
                    return
                self._remote_log(f"“{cur.get('title')}” never started (Spotify is on “{st.get('title') or 'nothing'}”) — moving on")
                self._note_error_locked(cur, "Spotify wouldn't play this one")
                if st.get('playing'):
                    self._rq_put(('stop',))
                self._advance_locked()
                return
            ended = (st.get('nothing') and self._r_maxpos > 2.0) or \
                    (self.duration_sec > 0 and pos_now >= self.duration_sec - 4.0)
            if ended:
                self._advance_locked()              # ours finished and Spotify went its own way
            else:
                # the listener chose something else in Spotify: the deck rests on its record
                self.position, self.is_paused, self._r_live = pos_now, True, False

    def _guest_apply(self, st):
        now = time.time()
        with self._lock:
            if (not self.is_paused) and self.idx >= 0:
                self._guest = None
                return
            if st is None:
                return                              # couldn't ask — leave it as it was
            if st.get('nothing') or st.get('kind') == 'ad' or not st.get('title'):
                self._guest = None
                return
            old = self._guest
            if st.get('playing'):
                self._guest = dict(st, at=now, paused_at=None)
            elif old and old.get('uri') == st.get('uri') and now - (old.get('paused_at') or now) < 900:
                # paused (from the deck or in Spotify): it stays on the deck a
                # while, so "play" picks it back up
                self._guest = dict(st, at=now, paused_at=old.get('paused_at') or now)
            else:
                self._guest = None

    def guest_control(self, action, value=None):
        """The deck's keys, while it is showing the listener's own Spotify."""
        with self._lock:
            if self._remote is None:
                return False
            g = self._guest
            if action == 'toggle':
                action = 'pause' if (g and g.get('playing')) else 'play'
            if action not in ('play', 'pause', 'next', 'prev', 'seek'):
                return False
            if g:                                   # answer on the deck at once; the next look confirms
                now = time.time()
                if action == 'pause':
                    g['position'], g['playing'], g['at'], g['paused_at'] = self._guest_pos_locked(), False, now, now
                elif action == 'play':
                    g['playing'], g['at'], g['paused_at'] = True, now, None
                elif action == 'seek':
                    g['position'], g['at'] = float(value or 0.0), now
            self._rq_put(('guest', action, value))
            return True

    def set_ui_mode(self, mode):
        """Remember the cassette's open/min/closed across app relaunches."""
        if mode not in ("open", "min", "closed"):
            return
        with self._lock:
            if self.ui_mode == mode:
                return
            self.ui_mode = mode
            self._persist_locked()
