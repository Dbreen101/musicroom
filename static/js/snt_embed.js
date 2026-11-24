// =============================================================
// snt_embed.js — streamed records in the deck.
//
// The deck's queue (seinnteoir_player.py) can hold a record that lives on a
// streaming service: kind 'embed', with the service and its link. No audio
// from a service ever reaches the Music Room's own player — each service only
// allows its music to be played by ITSELF. Two ways that happens:
//
//   state.embed_via === 'remote' — a Spotify record sounding in the listener's
//       OWN Spotify (the app, or Spotify open in a browser), told what to do
//       by the server (spotify_remote.py). Nothing plays in this page and
//       nothing is drawn here: the deck's own label carries a small Spotify
//       mark that says where the sound is and opens Spotify (seinnteoir.js —
//       Daithí, 2026-11-15: no bar above the player). The same goes for the
//       'guest': the listener's Spotify playing something of its own while
//       the deck rests — the deck's keys drive it.
//   state.embed_via === 'page' — the service's own player on a slip beside
//       the deck, driven from here: play, pause, seek, and — when it ends —
//       "next", so the cue moves on to whatever follows, owned or streamed.
//         SoundCloud — its widget; whole tracks, fully driven.
//         Spotify    — its embed, when the remote can't be used (not signed
//                      in, no Premium, Spotify not open): fully driven, but
//                      whole tracks only for a listener signed in to Spotify
//                      inside it (otherwise 30-second previews).
//   (Apple Music's player was taken out on 2026-11-14 — see streams.py.)
//
// seinnteoir.js loads this the first time a streamed record is current (or
// the listener's Spotify shows up) and calls SntEmbed.sync(state, api) after
// every poll.
// =============================================================
(function () {
'use strict';

const NAMES = { spotify: 'Spotify', soundcloud: 'SoundCloud' };
// why Spotify's page player is standing in for the listener's own Spotify
const WHY = {
    no_device: 'open Spotify on this computer for the whole track',
    premium:   'playing through your own Spotify needs Spotify Premium',
    signin:    'sign in to Spotify again on the Spotify page',
    busy:      'Spotify asked for a moment — this is its preview player',
    network:   'could not reach Spotify — this is its preview player',
};
let H = null;            // the live player: one at a time
let panel = null, api = null, last = null, placeT = null;
let folded = false;
try { folded = localStorage.getItem('mr_snt_embed_fold') === '1'; } catch (_) {}

const now = () => Date.now();
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function css() {
    if (document.getElementById('snt-embed-css')) return;
    const s = document.createElement('style');
    s.id = 'snt-embed-css';
    s.textContent = `
        #snt-embed { position: fixed; left: 18px; bottom: 150px; z-index: 8999; width: 478px; max-width: calc(100vw - 28px);
            background: var(--snt-shell, #e9e5db); color: var(--snt-ink, #161513); border: 1px solid var(--snt-edge, #a9a497); border-radius: 6px;
            box-shadow: 0 14px 40px rgba(0,0,0,.3); font-family: var(--f-mono, ui-monospace, monospace); overflow: hidden; }
        #snt-embed .sne-head { display: flex; align-items: center; gap: 10px; padding: 6px 8px 6px 12px; font-size: .58rem; letter-spacing: .14em; text-transform: uppercase; }
        #snt-embed .sne-src { font-weight: 600; white-space: nowrap; }
        #snt-embed .sne-note { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #55524b; letter-spacing: .08em; }
        #snt-embed .sne-note.warn { color: var(--snt-red, #c9412f); }
        #snt-embed button { appearance: none; background: none; border: 1px solid var(--snt-key-edge, #c8c3b6); color: inherit; font: inherit; letter-spacing: .1em;
            height: 20px; min-width: 22px; padding: 0 6px; border-radius: 3px; cursor: pointer; line-height: 1; }
        #snt-embed button:hover { background: #fff; }
        #snt-embed .sne-body { background: var(--snt-window, #161513); line-height: 0; }
        #snt-embed .sne-body iframe { display: block; width: 100%; border: 0; }
        #snt-embed.folded .sne-body { height: 0; overflow: hidden; }
        /* a page opened over the room hides the room's own chrome — the music keeps going */
        body.r3d-toolopen #snt-embed { opacity: 0; pointer-events: none; }
        body.panel-only #snt-embed { display: none !important; }
    `;
    document.head.appendChild(s);
}

function ensurePanel() {
    if (panel) return panel;
    css();
    panel = document.createElement('div');
    panel.id = 'snt-embed';
    panel.innerHTML = `<div class="sne-head"><span class="sne-src"></span><span class="sne-note"></span>
        <button class="sne-open" title="Open on the service">↗</button><button class="sne-fold" title="Fold this player away (the music keeps playing)">–</button></div>
        <div class="sne-body"></div>`;
    document.body.appendChild(panel);
    panel.querySelector('.sne-fold').onclick = () => {
        folded = !folded;
        try { localStorage.setItem('mr_snt_embed_fold', folded ? '1' : '0'); } catch (_) {}
        paint(); place();
    };
    panel.querySelector('.sne-open').onclick = () => {
        if (!H) return;
        fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: H.url }) }).catch(() => {});
    };
    addEventListener('resize', place);
    return panel;
}

// the slip hangs off the deck: above it when the deck sits low, below when high
function place() {
    if (!panel || !H) return;
    const host = api && api.deck ? api.deck() : null;
    if (!host || !host.offsetWidth) {
        panel.style.left = '18px'; panel.style.bottom = '18px'; panel.style.top = 'auto';
        return;
    }
    const r = host.getBoundingClientRect();
    const w = Math.max(320, Math.min(540, r.width < 320 ? 360 : r.width));
    panel.style.width = w + 'px';
    const ph = panel.offsetHeight || 60;
    const above = (r.top + r.height / 2) >= innerHeight / 2;
    let top = above ? (r.top - ph - 6) : (r.bottom + 6);
    top = Math.max(6, Math.min(innerHeight - ph - 6, top));
    const left = Math.max(6, Math.min(innerWidth - w - 6, r.left));
    panel.style.left = left + 'px'; panel.style.top = top + 'px'; panel.style.bottom = 'auto';
}

function paint() {
    if (!panel || !H) return;
    panel.classList.toggle('folded', folded);
    panel.querySelector('.sne-src').textContent = NAMES[H.source] || H.source || 'stream';
    panel.querySelector('.sne-fold').textContent = folded ? '+' : '–';
    const n = panel.querySelector('.sne-note');
    let note = '', warn = false;
    if (H.error)        { note = 'this one would not load — skip it or open it on the service'; warn = true; }
    else if (!H.ready)  { note = 'loading…'; }
    else if (H.blocked) { note = 'press play to start'; warn = true; }
    else if (H.why)     { note = H.why; }
    else if (H.preview) { note = 'preview only — sign in to Spotify in this player for the whole track'; }
    n.textContent = note; n.classList.toggle('warn', warn);
}

function loadScript(src, onload) {
    const s = document.createElement('script');
    s.src = src; s.async = true; if (onload) s.onload = onload;
    s.onerror = () => { if (H) { H.error = true; paint(); } };
    document.head.appendChild(s);
}

function report(body) {
    if (!H || !api) return Promise.resolve();
    return api.post('embed', Object.assign({ qid: H.qid }, body));
}

// ── what the service's player tells us ──────────────────────────────────────
function onPlayState(playing) {
    if (!H) return;
    const was = H.playing;
    H.playing = playing; H.lastEvt = now();
    if (playing) { H.started = true; H.blocked = false; H.tries = 0; }
    // the listener pressed play/pause INSIDE the service's player → the deck follows
    if (was !== playing && now() - H.lastCmd > 1200 && last && !!last.playing !== playing)
        report({ paused: !playing, position: H.position }).then(api.poll);
    paint();
}
function onProgress(pos, dur) {
    if (!H) return;
    H.position = pos; if (dur) H.duration = dur;
    if (pos > H.maxPos) H.maxPos = pos;
    if (now() - H.lastReport > 2500) { H.lastReport = now(); report({ position: pos, duration: H.duration || null }); }
    if (api && api.tick && now() - H.lastTick > 450) { H.lastTick = now(); api.tick(); }
}
function onEnded() {
    if (!H || H.ended) return;
    H.ended = true; H.playing = false;
    report({ ended: true }).then(api.poll);
}

// ── the services' own players ──────────────────────────────────────────────────────
function buildSoundCloud(body) {
    const big = H.stream_type && H.stream_type !== 'track';
    const f = document.createElement('iframe');
    f.height = big ? 300 : 166; f.allow = 'autoplay; encrypted-media'; f.scrolling = 'no';
    f.src = 'https://w.soundcloud.com/player/?url=' + encodeURIComponent(H.url)
        + '&auto_play=false&hide_related=true&show_comments=false&show_user=true&show_reposts=false&show_teaser=false&visual=false&color=%23161513';
    body.appendChild(f);
    const qid = H.qid;
    const go = () => {
        if (!H || H.qid !== qid) return;
        const w = window.SC.Widget(f), E = window.SC.Widget.Events;
        const dur = () => w.getDuration(d => { if (H && H.qid === qid && d) H.duration = d / 1000; });
        w.bind(E.READY, () => { if (!H || H.qid !== qid) return; H.ready = true; dur(); w.setVolume(Math.round((H.vol == null ? 1 : H.vol) * 100)); paint(); kick(); });
        w.bind(E.PLAY, () => { if (H && H.qid === qid) { dur(); onPlayState(true); } });
        w.bind(E.PAUSE, () => { if (H && H.qid === qid) onPlayState(false); });
        w.bind(E.PLAY_PROGRESS, e => { if (H && H.qid === qid) onProgress((e.currentPosition || 0) / 1000); });
        w.bind(E.FINISH, () => {
            if (!H || H.qid !== qid) return;
            // a set plays through its own tracks; only the last one ends the item
            w.getSounds(list => w.getCurrentSoundIndex(i => {
                if (!H || H.qid !== qid) return;
                if (!list || list.length <= 1 || i >= list.length - 1) onEnded();
            }));
        });
        w.bind(E.ERROR, () => { if (H && H.qid === qid) { H.error = true; paint(); } });
        H.ctl = { play: () => w.play(), pause: () => w.pause(), seek: s => w.seekTo(Math.round(s * 1000)), volume: v => w.setVolume(Math.round(v * 100)), destroy() {} };
    };
    if (window.SC && window.SC.Widget) go(); else loadScript('https://w.soundcloud.com/player/api.js', go);
}

let spApi = null, spWaiting = [], spAsked = false;
function withSpotify(cb) {
    if (spApi) return cb(spApi);
    spWaiting.push(cb);
    if (spAsked) return;
    spAsked = true;
    const prev = window.onSpotifyIframeApiReady;
    window.onSpotifyIframeApiReady = (IFrameAPI) => {
        spApi = IFrameAPI;
        if (typeof prev === 'function') { try { prev(IFrameAPI); } catch (_) {} }
        spWaiting.splice(0).forEach(f => f(IFrameAPI));
    };
    loadScript('https://open.spotify.com/embed/iframe-api/v1');
}
function buildSpotify(body) {
    const single = !H.stream_type || H.stream_type === 'track' || H.stream_type === 'episode';
    const slot = document.createElement('div');
    body.appendChild(slot);
    const qid = H.qid;
    withSpotify((IFrameAPI) => {
        if (!H || H.qid !== qid) return;
        IFrameAPI.createController(slot, { url: H.url, width: '100%', height: single ? 152 : 352 }, (c) => {
            if (!H || H.qid !== qid) { try { c.destroy(); } catch (_) {} return; }
            c.addListener('ready', () => { if (H && H.qid === qid) { H.ready = true; paint(); kick(); } });
            c.addListener('playback_update', (e) => {
                if (!H || H.qid !== qid) return;
                const d = e.data || {};
                const pos = (d.position || 0) / 1000, dur = (d.duration || 0) / 1000;
                // a signed-out listener gets a 30-second preview of the track
                if (single && dur > 28 && dur <= 31 && !(H.known_dur && H.known_dur <= 31)) H.preview = true;
                if (!d.isPaused && !d.isBuffering) { if (!H.playing) onPlayState(true); onProgress(pos, dur); return; }
                if (d.isBuffering) return;
                // paused: by the listener, by us — or because it reached the end
                const atEnd = pos === 0 || (dur && pos >= dur - 0.6);
                if (atEnd && H.maxPos > 2 && now() - H.lastCmd > 1500) { onEnded(); return; }
                H.position = pos;
                if (H.playing) onPlayState(false);
            });
            H.ctl = {
                play: () => (H.started ? c.resume() : c.play()), pause: () => c.pause(),
                seek: s => c.seek(Math.max(0, Math.round(s))), volume() {}, destroy: () => { try { c.destroy(); } catch (_) {} },
            };
        });
    });
}

// ── build, drive, take down ─────────────────────────────────────────────────
function build(cur, state) {
    teardown();
    ensurePanel();
    H = {
        qid: cur.qid, via: 'page', source: cur.source, url: cur.url, stream_type: cur.stream_type || '',
        why: (cur.source === 'spotify' && state.remote && WHY[state.remote.note]) || '',
        known_dur: cur.duration_sec || 0, ctl: null, ready: false, manual: false, playing: false, started: false,
        position: 0, duration: cur.duration_sec || 0, maxPos: 0, seq: state.embed_seq, startAt: state._srvPos || 0,
        lastCmd: 0, lastEvt: 0, lastReport: 0, lastTick: 0, tries: 0, blocked: false, ended: false, error: false, preview: false, vol: state.volume,
    };
    const body = panel.querySelector('.sne-body');
    body.innerHTML = '';
    panel.style.display = '';
    if (H.source === 'soundcloud') buildSoundCloud(body);
    else if (H.source === 'spotify') buildSpotify(body);
    else { H.error = true; }
    paint(); place();
    clearInterval(placeT); placeT = setInterval(place, 300);
}

// the first push once a player is ready: pick up where the cue says we are
function kick() {
    if (!H || !H.ctl || !last) return;
    if (H.startAt > 2) { H.lastCmd = now(); H.ctl.seek(H.startAt); }
    if (last.playing) { H.lastCmd = now(); H.tries = 1; H.ctl.play(); }
}

function teardown() {
    clearInterval(placeT); placeT = null;
    if (H && H.ctl) { try { H.ctl.pause(); } catch (_) {} try { H.ctl.destroy(); } catch (_) {} }
    H = null;
    if (panel) { panel.querySelector('.sne-body').innerHTML = ''; panel.style.display = 'none'; }
}

function sync(state, a) {
    api = a; last = state;
    const cur = state.queue && state.queue[state.idx];
    const embed = !!(cur && cur.kind === 'embed');
    // sounding in the listener's own Spotify (a record of ours, or their own
    // listening): no player here, and no slip — the deck's label says so
    if ((embed && state.embed_via === 'remote') || !embed) { if (H) teardown(); return; }
    // a streamed record that hasn't been started yet (a cue brought back when the
    // app opens rests on it, nobody has pressed play): no player until it is —
    // only then is it known whether the listener's Spotify or the page plays it
    if (state.embed_via !== 'page') { if (H) teardown(); return; }
    if (!H || H.qid !== cur.qid || H.via !== 'page') { build(cur, state); return; }
    if (!H.ready || !H.ctl || H.ended) return;
    const t = now();
    if (state.volume !== H.vol) { H.vol = state.volume; try { H.ctl.volume(state.volume); } catch (_) {} }
    // the deck asked for another point in the record (the scrubber, "previous")
    if (state.embed_seq !== H.seq) {
        H.seq = state.embed_seq; H.lastCmd = t; H.maxPos = 0;
        H.ctl.seek(state._srvPos || 0);
        if (state.playing) H.ctl.play();
        return;
    }
    if (t - H.lastCmd < 900 || t - H.lastEvt < 700) return;      // let the last move settle
    if (state.playing && !H.playing) {
        if (H.tries >= 3 && !H.started) {
            // the window won't let it start without a press — say so, and rest the deck
            H.blocked = true; H.tries = 0; paint();
            report({ paused: true, position: H.position }).then(api.poll);
            return;
        }
        H.lastCmd = t; H.tries++; H.ctl.play();
    } else if (!state.playing && H.playing) {
        H.lastCmd = t; H.ctl.pause();
    }
}

// what the deck should show for the current streamed record
function live(qid) {
    if (!H || H.qid !== qid) return null;                  // no player in the page: the server keeps the clock
    return { position: H.position, duration: H.duration, ready: H.ready, name: NAMES[H.source] || H.source };
}

window.SntEmbed = { sync, live, teardown };
})();
