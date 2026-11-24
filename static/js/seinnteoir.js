// =============================================================
// seinnteoir.js — remote control for the server-side player.
//
// The audio lives in the Flask process (seinnteoir_player.py).
// This file just renders the cassette UI, polls /api/seinnteoir/state
// for current track + position + queue, and sends commands.
//
// Because the browser is no longer responsible for playback, audio
// continues uninterrupted across every page navigation — the
// transport just keeps spinning on the server.
// =============================================================
(function () {
'use strict';

const POLL_MS = 800;

let state = {
    queue: [], idx: -1, position: 0, duration: 0,
    playing: false, volume: 0.8, mixer_ok: true,
};
let barEl, qpopEl, tabEl, volpopEl, outpopEl;   // outpopEl: the list of speakers (the trial deck)
let cardEl;                                     // the card behind the title (the trial deck)
let _pollTimer = null;
let _scrubLock = 0;       // suppress UI scrub updates briefly after user seek
let _lastPlaying = false; // for detecting playing↔paused transitions
// Three resting states for the player, all keeping the cue intact:
//   'open'   — the full control bar
//   'min'    — folded to a tiny tab (the ♫ N pill)
//   'closed' — gone from the screen; reopens when a track is cued or from the
//              Mála → Seinnteoir. Clearing the queue stays a separate, explicit
//              act (the qpop "clear").
let _mode = 'open';
// localStorage is the fast in-session memory, but the desktop shell WIPES it on
// every app relaunch — so the server remembers the mode too (state.ui_mode,
// stored with the cue) and the first poll adopts it when localStorage came up
// empty. Without this a put-away player reopened on every launch (Daithí,
// 2026-07-10).
let _modeFromStorage = false;
try {
    const stored = localStorage.getItem('mr_snt_mode')
        || (localStorage.getItem('mr_snt_putaway') === '1' ? 'min' : null);
    if (stored) { _mode = stored; _modeFromStorage = true; }
} catch (_) {}
if (!['open', 'min', 'closed'].includes(_mode)) { _mode = 'open'; _modeFromStorage = false; }
let _modeAdopted = false;   // the first poll's one-time server-mode adoption ran
// spot a fresh cue (queue grew) → reopen a closed player. null = no baseline
// yet this page load: the script reloads on every navigation, so the FIRST poll
// must only record the current length, never read a pre-existing cue as growth
// (that reopened a player the user had closed, every time they changed page).
let _prevQLen = null;
// when the user EXPLICITLY opens the player (Mála → Player, a handoff, etc.) it
// must appear even with an empty cue — otherwise clicking "Player" does nothing.
// Set by open(), cleared when put away / minimized.
let _forceShow = false;
// the user can drag the cassette anywhere — its position persists (one spot for
// bar + tab). Stored as {x,y}; null = wherever the page's CSS parks it.
let _sntPos = null, _tabDragged = false, _barDragged = false;
try { _sntPos = JSON.parse(localStorage.getItem('mr_snt_pos') || 'null'); } catch (_) {}
// skipped-track notices: the server keeps the LAST error with an 'at' stamp;
// we toast each new stamp once. On the first poll after a page load only a
// FRESH error (last few seconds) shows — older ones were toasted on the page
// that saw them happen.
let _lastErrAt = null, _errBaselined = false;

// ─── CSS ────────────────────────────────────────────────────────────
function _injectCSS() {
    if (document.getElementById('seinnteoir-css')) return;
    const s = document.createElement('style');
    s.id = 'seinnteoir-css';
    s.textContent = `
        :root{ --snt-shell:#e9e5db; --snt-face:#f2efe8; --snt-edge:#a9a497; --snt-ink:#161513;
               --snt-key:#f7f5f0; --snt-key-edge:#c8c3b6; --snt-paper:#f7f5f0; --snt-window:#161513;
               --snt-lcd:#c9c4b8; --snt-lcd-ink:#161513; --snt-tape:#2a2825; --snt-red:#c9412f; --snt-w:478px; }
        /* the trial build's deck carries one more key (＋ grúpa), so it is a little wider */
        html.is-gr{ --snt-w:522px; }
        #seinnteoir-bar {
            position: fixed; bottom: 18px; left: 18px; z-index: 9000;
            display: none; align-items: stretch; gap: 0;
            width: var(--snt-w); max-width: calc(100vw - 28px);
            background: var(--snt-shell);
            border: 1px solid var(--snt-edge); border-radius: 6px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.7), inset 0 -2px 0 rgba(0,0,0,.08), 0 18px 48px rgba(0,0,0,.35);
            color: var(--snt-ink); font-family: var(--f-grotesk, var(--font-main, system-ui, sans-serif));
            user-select: none;
        }
        #seinnteoir-bar.visible { display: flex; }
        /* four screws */
        #seinnteoir-bar::before, #seinnteoir-bar::after { content: ""; position: absolute; width: 5px; height: 5px; border-radius: 50%;
            background: radial-gradient(circle at 40% 35%, #fbfaf7, #9d9a92); box-shadow: inset 0 0 0 1px rgba(0,0,0,.25); }
        #seinnteoir-bar::before { left: 6px; top: 6px; box-shadow: inset 0 0 0 1px rgba(0,0,0,.25), calc(var(--snt-w) - 14px) 0 0 0 #c3c0b8; }
        #seinnteoir-bar::after  { left: 6px; bottom: 6px; box-shadow: inset 0 0 0 1px rgba(0,0,0,.25), calc(var(--snt-w) - 14px) 0 0 0 #c3c0b8; }
        /* ── the cassette: window + label ── */
        .snt-cassette { flex: 0 0 176px; margin: 12px 0 12px 14px; display: flex; flex-direction: column; gap: 0;
            background: var(--snt-face); border: 1px solid var(--snt-edge); border-radius: 4px; overflow: hidden;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.8); }
        .snt-window { position: relative; height: 58px; margin: 7px 7px 0; background: var(--snt-window); border-radius: 3px;
            display: flex; align-items: center; justify-content: space-between; padding: 0 16px;
            box-shadow: inset 0 2px 6px rgba(0,0,0,.6); overflow: hidden; }
        .snt-window::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 40%;
            background: linear-gradient(180deg, rgba(255,255,255,.08), transparent); pointer-events: none; }
        .snt-tape { position: absolute; left: 38px; right: 38px; top: 50%; height: 14px; margin-top: -7px;
            background: var(--snt-tape); opacity: .9; }
        .snt-reel { width: 40px; height: 40px; position: relative; z-index: 1; animation: snt-spin 2.2s linear infinite; animation-play-state: paused; }
        #seinnteoir-bar.playing .snt-reel { animation-play-state: running; }
        .snt-reel--r { animation-duration: 3.1s; }
        .snt-reel__tape { fill: var(--snt-tape); }
        .snt-reel__hub  { fill: #f1efe9; }
        .snt-reel__teeth rect { fill: var(--snt-window); }
        @keyframes snt-spin { to { transform: rotate(360deg); } }
        .snt-info { margin: 6px 7px 7px; padding: 5px 8px 6px; background: var(--snt-paper); border: 1px solid #d8d5cd; border-radius: 2px;
            min-height: 34px; overflow: hidden; line-height: 1.25; position: relative; }
        .snt-info::before { content: "A"; position: absolute; right: 7px; top: 4px; font-size: 1rem; font-weight: 700; color: #1b1b1b; opacity: .85; }
        .snt-info .snt-artist { display: block; font-size: .56rem; letter-spacing: .14em; text-transform: uppercase; color: #3a3a3a;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 16px; }
        .snt-info #snt-title { display: block; font-size: .78rem; font-weight: 600; color: var(--snt-ink);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 16px; }
        .snt-info.snt-info--link { cursor: pointer; }
        .snt-info.snt-info--link:hover #snt-title { text-decoration: underline; text-underline-offset: 2px; }
        /* ── the deck side: counter, tape line, keys ── */
        .snt-deck { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: space-between; padding: 12px 14px 12px 12px; gap: 6px; }
        .snt-deck__row { display: flex; align-items: center; gap: 10px; }
        .snt-time { font-family: var(--f-mono, ui-monospace, monospace); font-size: .78rem; letter-spacing: .06em;
            background: var(--snt-lcd); color: var(--snt-lcd-ink); border: 1px solid #8f978c; border-radius: 2px;
            padding: 4px 8px; min-width: 104px; text-align: center; font-variant-numeric: tabular-nums;
            box-shadow: inset 0 1px 3px rgba(0,0,0,.35); white-space: nowrap; }
        .snt-scrub { flex: 1; height: 14px; min-width: 60px; cursor: pointer; -webkit-appearance: none; appearance: none; background: transparent; margin: 0; }
        .snt-scrub::-webkit-slider-runnable-track { height: 3px; background: #8e8b83; border-radius: 2px; }
        .snt-scrub::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; margin-top: -4.5px; border-radius: 50%;
            background: #f5f4f0; border: 1px solid #6e6b64; box-shadow: 0 1px 2px rgba(0,0,0,.3); }
        .snt-scrub::-moz-range-track { height: 3px; background: #8e8b83; border-radius: 2px; }
        .snt-scrub::-moz-range-thumb { width: 12px; height: 12px; border-radius: 50%; background: #f5f4f0; border: 1px solid #6e6b64; }
        .snt-controls { display: flex; align-items: flex-end; gap: 4px; }
        .snt-controls .snt-gap { width: 6px; }
        .snt-key { display: inline-flex; flex-direction: column; align-items: center; gap: 3px; }
        .snt-key__cap { font-size: .46rem; letter-spacing: .12em; text-transform: uppercase; color: #4a4a4a; line-height: 1; }
        .snt-btn {
            background: var(--snt-key); border: 1px solid var(--snt-key-edge); color: var(--snt-ink);
            width: 32px; height: 26px; box-sizing: border-box; border-radius: 3px; cursor: pointer;
            font-size: .78rem; line-height: 1; font-family: inherit; padding: 0; flex-shrink: 0;
            display: inline-flex; align-items: center; justify-content: center;
            box-shadow: inset 0 1px 0 #fff, 0 2px 0 #b8b5ad; transition: transform .06s, box-shadow .06s;
        }
        .snt-btn:hover { background: #fff; }
        .snt-btn:active { transform: translateY(2px); box-shadow: inset 0 1px 0 #fff, 0 0 0 #b8b5ad; }
        .snt-btn:disabled { opacity: .4; cursor: not-allowed; }
        .snt-btn.snt-play { width: 40px; }
        .snt-btn.snt-play.playing { background: #e9e7e1; box-shadow: inset 0 2px 3px rgba(0,0,0,.18), 0 0 0 #b8b5ad; transform: translateY(2px); }
        .snt-btn.snt-play.playing::after { content: ""; position: absolute; width: 5px; height: 5px; border-radius: 50%; background: var(--snt-red);
            top: -8px; box-shadow: 0 0 6px var(--snt-red); animation: snt-lamp 2.4s ease-in-out infinite; }
        .snt-btn { position: relative; }
        @keyframes snt-lamp { 0%,100% { opacity: .55; } 50% { opacity: 1; } }
        .snt-btn#snt-q { width: auto; min-width: 32px; padding: 0 6px; }
        .snt-btn--icon svg { width: 15px; height: 15px; display: block; }
        #snt-qcount { margin-left: 4px; font-size: .58rem; font-family: var(--f-mono, monospace); font-variant-numeric: tabular-nums; }
        /* the volume pop-up — a small paper card floating off the deck */
        .snt-volpop { position: fixed; display: none; align-items: center; gap: 9px; z-index: 9002;
            background: var(--snt-paper); border: 1px solid var(--snt-edge); border-radius: 4px; padding: 9px 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,.3); color: var(--snt-ink); }
        .snt-volpop.visible { display: flex; }
        .snt-volpop input[type=range] { width: 122px; height: 4px; accent-color: #1b1b1b; cursor: pointer; }
        .snt-volpop .snt-vol-val { font-family: var(--f-mono, monospace); font-size: .64rem; min-width: 30px; text-align: right; font-variant-numeric: tabular-nums; }
        /* where the sound goes: a line on the deck that names the speaker, and its list */
        .snt-out { display: none; align-items: baseline; gap: 7px; min-width: 0; max-width: 100%; background: none; border: 0; padding: 0; margin: -1px 0;
            cursor: pointer; font-family: var(--f-mono, ui-monospace, monospace); font-size: .5rem; letter-spacing: .12em; text-transform: uppercase;
            color: #4a4a4a; text-align: left; line-height: 1.3; }
        .snt-out.on { display: flex; }
        .snt-out__n { color: var(--snt-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px dotted #8e8b83; }
        .snt-out:hover .snt-out__n, .snt-out.open .snt-out__n { border-bottom: 1px solid var(--snt-ink); }
        .snt-outpop { position: fixed; display: none; z-index: 9002; width: 318px; max-width: calc(100vw - 16px); max-height: min(440px, calc(100vh - 190px));
            overflow-y: auto; background: var(--snt-paper); border: 1px solid var(--snt-edge); border-radius: 4px; padding: 0 0 4px;
            box-shadow: 0 14px 40px rgba(0,0,0,.35); color: var(--snt-ink); font-family: var(--f-mono, ui-monospace, monospace); }
        .snt-outpop.visible { display: block; }
        .snt-outpop__h { padding: 10px 12px 8px; font-size: .56rem; letter-spacing: .14em; text-transform: uppercase; color: #3a3a3a; border-bottom: 1px solid #1b1b1b; }
        .snt-outpop__h + .snt-outpop__h, .snt-outrow + .snt-outpop__h, .snt-outpop__say + .snt-outpop__h { margin-top: 8px; }
        .snt-outrow { display: flex; align-items: baseline; gap: 9px; width: 100%; box-sizing: border-box; background: none; border: 0; border-bottom: 1px solid #e3e0d8;
            padding: 8px 12px; cursor: pointer; text-align: left; color: var(--snt-ink); font-family: inherit; font-size: .72rem; line-height: 1.3; }
        .snt-outrow:hover { background: #f1efe8; }
        .snt-outrow[disabled] { cursor: default; opacity: .55; }
        .snt-outrow__m { flex: 0 0 8px; width: 8px; height: 8px; border: 1px solid var(--snt-ink); align-self: center; box-sizing: border-box; }
        .snt-outrow.on .snt-outrow__m { background: var(--snt-ink); }
        .snt-outrow__n { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .snt-outrow__k { flex: none; font-size: .54rem; letter-spacing: .12em; text-transform: uppercase; color: #5a5a5a; }
        .snt-outrow--bt .snt-outrow__m { border-style: dotted; }
        .snt-outrow--more .snt-outrow__n { font-size: .6rem; letter-spacing: .1em; text-transform: uppercase; }
        .snt-outpop__say { padding: 8px 12px; font-size: .62rem; line-height: 1.5; color: #4a4a4a; }
        .snt-outpop__say.bad { color: var(--snt-red); }
        /* the queue — a paper tracklist, like the back of the box */
        .snt-qpop { position: fixed; bottom: 150px; left: 18px; display: none; z-index: 9001;
            background: var(--snt-paper); border: 1px solid var(--snt-edge); border-radius: 4px;
            min-width: 320px; max-width: 440px; max-height: 340px; overflow-y: auto; padding: 4px 0;
            box-shadow: 0 14px 40px rgba(0,0,0,.35); color: var(--snt-ink);
            font-family: var(--f-grotesk, var(--font-main, system-ui, sans-serif)); }
        .snt-qpop.visible { display: block; }
        .snt-qhead { padding: 9px 12px; font-size: .58rem; letter-spacing: .14em; text-transform: uppercase; color: #3a3a3a;
            border-bottom: 1px solid #1b1b1b; display: flex; justify-content: space-between; align-items: center; }
        .snt-qhead button { background: none; border: none; color: #3a3a3a; cursor: pointer; padding: 0; font: inherit; font-size: .58rem; letter-spacing: .14em; text-transform: uppercase; }
        .snt-qhead button:hover { color: var(--snt-red); }
        .snt-qrow { padding: 6px 10px; font-size: .78rem; display: flex; gap: 6px; align-items: center; border-bottom: 1px solid #e3e0d8; color: var(--snt-ink); }
        .snt-qrow:hover { background: #f1efe8; }
        .snt-qrow.active { background: #1b1b1b; color: #faf8f3; }
        .snt-qrow.snt-ghost { opacity: .35; }
        .snt-qrow.snt-chosen { background: #e6e3da; }
        .snt-qrow__handle { width: 14px; flex-shrink: 0; text-align: center; opacity: .45; font-size: .85rem; cursor: grab; user-select: none; line-height: 1; }
        .snt-qrow__handle:active { cursor: grabbing; }
        .snt-qrow__pos { width: 32px; flex-shrink: 0; background: transparent; border: 1px solid #c6c3bb; border-radius: 2px; color: inherit;
            font-family: var(--f-mono, monospace); font-size: .7rem; text-align: center; padding: 2px 0; line-height: 1; font-variant-numeric: tabular-nums; -moz-appearance: textfield; }
        .snt-qrow__pos::-webkit-outer-spin-button, .snt-qrow__pos::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
        .snt-qrow__pos:focus { outline: none; border-color: var(--snt-ink); }
        .snt-qrow__main { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; padding: 2px 0; }
        .snt-qrow__main:hover { text-decoration: underline; text-underline-offset: 2px; }
        .snt-qrow__play, .snt-qrow__x, .snt-qrow__nextup { background: none; border: none; padding: 0 4px; cursor: pointer; font-size: .78rem; flex-shrink: 0; line-height: 1; color: inherit; opacity: .55; }
        .snt-qrow__play:hover, .snt-qrow__nextup:hover { opacity: 1; }
        .snt-qrow__x:hover { opacity: 1; color: var(--snt-red); }
        .snt-qrow.active .snt-qrow__x:hover { color: #ff9a8e; }
        .snt-qrow__from { flex: 0 1 auto; font-size: .58rem; letter-spacing: .06em; text-transform: uppercase; opacity: .6; cursor: pointer; max-width: 92px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .snt-qrow__from:hover { opacity: 1; }
        /* ── minimised: the cassette's spine. Play, pause and skip stay a thumb away. ── */
        #seinnteoir-tab { position: fixed; bottom: 18px; left: 18px; z-index: 9000; display: none; align-items: center; gap: 6px;
            background: var(--snt-shell); border: 1px solid var(--snt-edge); border-radius: 4px; padding: 5px 10px 5px 6px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.7), 0 10px 28px rgba(0,0,0,.3); color: var(--snt-ink);
            font-family: var(--f-grotesk, var(--font-main, system-ui, sans-serif)); cursor: pointer; max-width: calc(100vw - 28px); }
        #seinnteoir-tab.visible { display: inline-flex; }
        .snt-tab__key { background: var(--snt-key); border: 1px solid var(--snt-key-edge); color: var(--snt-ink); width: 26px; height: 22px; border-radius: 3px;
            display: inline-flex; align-items: center; justify-content: center; font-size: .7rem; padding: 0; cursor: pointer; flex-shrink: 0;
            box-shadow: inset 0 1px 0 #fff, 0 2px 0 #b8b5ad; font-family: inherit; }
        .snt-tab__key:active { transform: translateY(2px); box-shadow: inset 0 1px 0 #fff; }
        .snt-tab__play.playing { background: #e9e7e1; box-shadow: inset 0 2px 3px rgba(0,0,0,.18); }
        .snt-tab__title { font-size: .7rem; font-weight: 600; max-width: 190px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-left: 4px; }
        .snt-tab__label { font-size: .58rem; letter-spacing: .1em; text-transform: uppercase; white-space: nowrap; opacity: .7; }
        .snt-tab__label b { font-variant-numeric: tabular-nums; font-weight: 700; }
        #snt-err-toast { position: fixed; bottom: 150px; left: 18px; z-index: 9001;
            background: var(--snt-paper); border: 1px solid var(--snt-edge); border-left: 3px solid var(--snt-red); border-radius: 4px;
            padding: 8px 12px; color: var(--snt-ink); font-family: var(--f-grotesk, system-ui, sans-serif); font-size: .78rem;
            max-width: min(420px, calc(100vw - 28px)); box-shadow: 0 10px 30px rgba(0,0,0,.3);
            opacity: 0; pointer-events: none; transform: translateY(4px); transition: opacity .25s ease, transform .25s ease; }
        #snt-err-toast.visible { opacity: 1; transform: none; }
        /* ── where the record is playing from: a mark on the label's corner (the trial deck).
           A disc = a file on this laptop · the service's own mark = playing there · ".web" = a website.
           It lights when the pointer is on it, and a click opens that place. ── */
        html.is-gr .snt-info::before { content: none; }
        html.is-gr .snt-info .snt-artist, html.is-gr .snt-info #snt-title { padding-right: 28px; }
        html.is-gr .snt-info.snt-info--link:hover #snt-title { text-decoration-style: dotted; }
        .snt-src { display: none; position: absolute; right: 4px; top: 50%; margin-top: -12px; width: 24px; height: 24px; box-sizing: border-box; padding: 0;
            align-items: center; justify-content: center; background: none; border: 1px solid transparent; border-radius: 3px;
            color: var(--snt-ink); --snt-src-cut: var(--snt-paper); cursor: default; font-family: var(--f-mono, ui-monospace, monospace);
            font-size: .5rem; font-weight: 600; letter-spacing: .02em; line-height: 1; transition: background .15s, color .15s, border-color .15s; }
        .snt-src.on { display: inline-flex; }
        .snt-src svg { width: 17px; height: 17px; display: block; }
        .snt-src--web { width: auto; min-width: 24px; padding: 0 3px; }
        .snt-src.can { cursor: pointer; border-color: #d8d5cd; }
        .snt-src.can:hover, .snt-src.can:focus-visible { background: var(--snt-ink); color: var(--snt-paper); border-color: var(--snt-ink);
            --snt-src-cut: var(--snt-ink); outline: none; }
        .snt-tab__src { display: none; align-items: center; justify-content: center; flex: none; margin-left: 3px; color: var(--snt-ink); --snt-src-cut: var(--snt-shell);
            font-family: var(--f-mono, ui-monospace, monospace); font-size: .5rem; font-weight: 600; line-height: 1; }
        .snt-tab__src.on { display: inline-flex; }
        .snt-tab__src svg { width: 14px; height: 14px; display: block; }
        /* ── the card behind the title: the back of the tape — the cover, and the
           whole title and who it is by, on ruled lines ── */
        .snt-card { position: fixed; display: none; z-index: 9001; width: var(--snt-w); max-width: calc(100vw - 28px); box-sizing: border-box;
            grid-template-columns: 22px auto minmax(0, 1fr); background: var(--snt-paper); color: var(--snt-ink);
            border: 1px solid var(--snt-edge); border-radius: 4px; box-shadow: 0 14px 40px rgba(0,0,0,.35); overflow: hidden;
            font-family: var(--f-mono, ui-monospace, monospace); text-align: left; }
        .snt-card.visible { display: grid; }
        .snt-card__spine { position: relative; background: var(--snt-ink); }
        /* the words run up the spine; they are laid out of the flow so a long title never makes the card taller */
        .snt-card__spine span { position: absolute; left: 0; right: 0; top: 10px; bottom: 10px; writing-mode: vertical-rl; transform: rotate(180deg);
            color: var(--snt-paper); font-size: .5rem; letter-spacing: .2em; text-transform: uppercase; line-height: 22px; text-align: center;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .snt-card__art { position: relative; align-self: start; width: 132px; height: 132px; margin: 12px 0 12px 12px; box-sizing: border-box;
            background: #e3e0d8; border: 1px solid var(--snt-key-edge); overflow: hidden; display: flex; align-items: center; justify-content: center; }
        .snt-card__art span { font-family: var(--f-display, "Instrument Serif", Georgia, serif); font-size: 3.2rem; line-height: 1; color: #8e8b83; }
        .snt-card__art img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
        .snt-card__back { min-width: 0; display: flex; flex-direction: column; padding: 8px 14px 12px 14px; }
        .snt-card__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 24px; }
        .snt-card__side { font-size: .5rem; letter-spacing: .2em; text-transform: uppercase; color: #5a574f; }
        .snt-card__x { appearance: none; -webkit-appearance: none; flex: none; width: 24px; height: 24px; padding: 0; box-sizing: border-box; background: none;
            border: 1px solid var(--snt-key-edge); border-radius: 3px; color: var(--snt-ink); font: inherit; font-size: .62rem; line-height: 1; cursor: pointer; }
        .snt-card__x:hover { background: var(--snt-ink); color: var(--snt-paper); border-color: var(--snt-ink); }
        .snt-card__row { display: grid; grid-template-columns: 50px minmax(0, 1fr); column-gap: 10px; align-items: baseline;
            padding: 6px 0 5px; border-bottom: 1px solid #d8d5cd; }
        .snt-card__k { font-size: .5rem; letter-spacing: .16em; text-transform: uppercase; color: #5a574f; }
        .snt-card__v { font-family: var(--f-display, "Instrument Serif", Georgia, serif); font-size: 1.02rem; line-height: 1.22; overflow-wrap: anywhere; }
        .snt-card__v--t { font-size: 1.3rem; line-height: 1.15; }
        .snt-card__v--m { font-family: inherit; font-size: .66rem; letter-spacing: .04em; line-height: 1.5; }
        /* the lines nobody has written on yet */
        .snt-card__rest { flex: 1; min-height: 0; background: repeating-linear-gradient(to bottom, transparent 0, transparent 25px, #d8d5cd 25px, #d8d5cd 26px); }
        @media (max-width: 460px) { .snt-card { grid-template-columns: 22px minmax(0, 1fr); } .snt-card__art { display: none; } }
        /* a chrome-less page inside the room (the track panel) never shows its own deck */
        body.panel-only #seinnteoir-bar, body.panel-only #seinnteoir-tab, body.panel-only #snt-qpop, body.panel-only #snt-card { display: none !important; }
    `;
    document.head.appendChild(s);
}

// ─── DOM ────────────────────────────────────────────────────────────
function _ensureBar() {
    if (barEl) return;
    _injectCSS();
    barEl = document.createElement('div');
    barEl.id = 'seinnteoir-bar';
    barEl.innerHTML = `
        <div class="snt-cassette">
            <div class="snt-window"><svg class="snt-reel snt-reel--l" viewBox="0 0 40 40" aria-hidden="true"><circle class="snt-reel__tape" cx="20" cy="20" r="18"/><circle class="snt-reel__hub" cx="20" cy="20" r="9.5"/><g class="snt-reel__teeth"><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(0 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(60 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(120 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(180 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(240 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(300 20 20)"/></g></svg><div class="snt-tape"></div><svg class="snt-reel snt-reel--r" viewBox="0 0 40 40" aria-hidden="true"><circle class="snt-reel__tape" cx="20" cy="20" r="18"/><circle class="snt-reel__hub" cx="20" cy="20" r="9.5"/><g class="snt-reel__teeth"><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(0 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(60 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(120 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(180 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(240 20 20)"/><rect x="18.6" y="10.5" width="2.8" height="4.5" rx=".6" transform="rotate(300 20 20)"/></g></svg></div>
            <div class="snt-info" id="snt-info"><span class="snt-artist">—</span><span id="snt-title">—</span><button type="button" class="snt-src" id="snt-src"></button></div>
        </div>
        <div class="snt-deck">
            <div class="snt-deck__row">
                <span class="snt-time" id="snt-time">0:00 / 0:00</span>
                <input type="range" class="snt-scrub" id="snt-scrub" min="0" max="1000" value="0" step="1" title="Where you are in the record">
            </div>
            <button class="snt-out" id="snt-out" title="Where the sound is going — choose a speaker"><span class="snt-out__k">out</span><span class="snt-out__n" id="snt-out-name"></span></button>
            <div class="snt-controls">
                <span class="snt-key"><button class="snt-btn" id="snt-prev" title="Previous">⏮</button><span class="snt-key__cap">prev</span></span>
                <span class="snt-key"><button class="snt-btn snt-play" id="snt-play" title="Play / pause">▶</button><span class="snt-key__cap">play</span></span>
                <span class="snt-key"><button class="snt-btn" id="snt-next" title="Next">⏭</button><span class="snt-key__cap">next</span></span>
                <span class="snt-gap"></span>
                <span class="snt-key"><button class="snt-btn" id="snt-q" title="The cue — what plays next">☰<span id="snt-qcount"></span></button><span class="snt-key__cap">cue</span></span>
                <span class="snt-key" id="snt-grupa-key" style="display:none"><button class="snt-btn" id="snt-grupa" title="Add what is playing to a grúpa">＋</button><span class="snt-key__cap">grúpa</span></span>
                <span class="snt-key"><button class="snt-btn" id="snt-vol" title="Volume">🔊</button><span class="snt-key__cap">vol</span></span>
                <span class="snt-key"><button class="snt-btn snt-btn--icon" id="snt-justlisten" title="Just Listen — sit back with the cue">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M7.5 10a4.5 4.5 0 0 1 9 0c0 2.4-1.7 3.3-2.6 4.4-.6.7-.9 1.4-.9 2.4a2 2 0 1 1-4 0"/>
                    <path d="M10 10a2 2 0 0 1 4 0c0 1-.7 1.4-1.2 2"/></svg></button><span class="snt-key__cap">listen</span></span>
                <span class="snt-key" id="snt-eist-key"><button class="snt-btn snt-btn--icon" id="snt-eist" title="Deep Listening — listen closely and take notes">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M5 10a4.3 4.3 0 0 1 8.6 0c0 2.3-1.6 3.1-2.5 4.2-.5.7-.8 1.3-.8 2.3a1.9 1.9 0 1 1-3.8 0"/>
                    <path d="M7.4 10a1.9 1.9 0 0 1 3.8 0"/>
                    <path d="M19.5 8.5l-5.4 5.4-.7 2.4 2.4-.7 5.4-5.4z"/><path d="M17.7 10.3l1.8 1.8"/></svg></button><span class="snt-key__cap">notes</span></span>
                <span class="snt-gap"></span>
                <span class="snt-key"><button class="snt-btn" id="snt-min" title="Fold the player down (the music keeps playing)">–</button><span class="snt-key__cap">fold</span></span>
                <span class="snt-key" id="snt-close-key"><button class="snt-btn" id="snt-close" title="Stop the music and put the player away (the cue is kept)">✕</button><span class="snt-key__cap">close</span></span>
            </div>
        </div>
    `;
    document.body.appendChild(barEl);
    qpopEl = document.createElement('div');
    qpopEl.id = 'snt-qpop'; qpopEl.className = 'snt-qpop';
    document.body.appendChild(qpopEl);
    volpopEl = document.createElement('div');
    volpopEl.id = 'snt-volpop'; volpopEl.className = 'snt-volpop';
    volpopEl.innerHTML =
        `<input type="range" id="snt-vol-slider" min="0" max="1" step="any" value="${state.volume}" title="Volume">` +
        `<span class="snt-vol-val" id="snt-vol-val"></span>`;
    document.body.appendChild(volpopEl);
    outpopEl = document.createElement('div');
    outpopEl.id = 'snt-outpop'; outpopEl.className = 'snt-outpop';
    document.body.appendChild(outpopEl);
    cardEl = document.createElement('div');
    cardEl.id = 'snt-card'; cardEl.className = 'snt-card';
    document.body.appendChild(cardEl);
    tabEl = document.createElement('div');
    tabEl.id = 'seinnteoir-tab';
    tabEl.innerHTML = `
        <button class="snt-tab__key" id="snt-tab-prev" title="Previous">⏮</button>
        <button class="snt-tab__key snt-tab__play" id="snt-tab-play" title="Play / pause">▶</button>
        <button class="snt-tab__key" id="snt-tab-next" title="Next">⏭</button>
        <span class="snt-tab__src" id="snt-tab-src"></span>
        <span class="snt-tab__title" id="snt-tab-title" title="Open the player">—</span>
        <span class="snt-tab__label" title="Open the player">♫ <b id="snt-tab-count">0</b></span>
    `;
    document.body.appendChild(tabEl);
    _makeDraggable(barEl);            // drag from the cassette body / between controls
    _makeDraggable(tabEl, true);
    _applySntPos();                   // restore where the user last parked it
    _bindUI();
}

function _setMode(m) {
    _mode = ['open', 'min', 'closed'].includes(m) ? m : 'open';
    if (GR() && _mode === 'closed') _mode = 'min';      // the trial build folds, never closes
    try { localStorage.setItem('mr_snt_mode', _mode); } catch (_) {}
    _modeFromStorage = true;                    // an explicit choice this session
    _post('ui_mode', { mode: _mode });          // …and it survives a relaunch
    if (_mode !== 'open' && qpopEl) qpopEl.classList.remove('visible');
    _render();
    // re-clamp into view with the now-visible element's real size: opening a
    // cassette parked near an edge shifts the full bar back on-screen; minimizing
    // lets the small tab return to where it was parked. _sntPos is never changed
    // by this, so the tab always comes home. Synchronous (reading offsetWidth
    // forces layout) + a deferred pass once fonts/layout fully settle. (Daithí)
    _applySntPos();
    requestAnimationFrame(_applySntPos);
}

// ─── drag the cassette anywhere ─────────────────────────────────────────────
// inline !important so a page-level position rule (e.g. the 3D room parks it on
// the left) is overridden once the user moves it; clamped into the viewport.
function _applySntPos() {
    if (!_sntPos) return;
    for (const el of [barEl, tabEl]) {
        if (!el) continue;
        const w = el.offsetWidth || 180, h = el.offsetHeight || 40;
        const x = Math.max(4, Math.min(innerWidth  - w - 4, _sntPos.x));
        const y = Math.max(4, Math.min(innerHeight - h - 4, _sntPos.y));
        el.style.setProperty('left', x + 'px', 'important');
        el.style.setProperty('top',  y + 'px', 'important');
        el.style.setProperty('right',  'auto', 'important');
        el.style.setProperty('bottom', 'auto', 'important');
        el.style.setProperty('transform', 'none', 'important');
    }
    _publishBox();
}
function _makeDraggable(el, isTab) {
    el.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        // never start a drag from an actual control (buttons, the scrubber)
        if (e.target.closest('button, input, .snt-btn, .snt-tab__play, .snt-scrub')) return;
        const sx = e.clientX, sy = e.clientY;
        const r = el.getBoundingClientRect();
        const offX = sx - r.left, offY = sy - r.top;
        let moved = false;
        const move = (ev) => {
            if (!moved && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 4) return;
            if (!moved) {   // first real movement → tuck any open pop-up away so it doesn't detach
                // …and only now hold the pointer. Holding it from the press made the
                // browser send the CLICK to the deck itself, so a press on the title
                // (or anything else on the label) was never heard by it.
                try { el.setPointerCapture(e.pointerId); } catch (_) {}
                if (qpopEl) qpopEl.classList.remove('visible');
                if (volpopEl) volpopEl.classList.remove('visible');
                if (cardEl) cardEl.classList.remove('visible');
                if (outpopEl && outpopEl.classList.contains('visible')) toggleOutPop(false);
            }
            moved = true;
            const w = el.offsetWidth, h = el.offsetHeight;
            _sntPos = {
                x: Math.max(4, Math.min(innerWidth  - w - 4, ev.clientX - offX)),
                y: Math.max(4, Math.min(innerHeight - h - 4, ev.clientY - offY)),
            };
            _applySntPos();
        };
        const up = () => {
            removeEventListener('pointermove', move);
            removeEventListener('pointerup', up);
            removeEventListener('pointercancel', up);
            try { el.releasePointerCapture(e.pointerId); } catch (_) {}
            if (moved) {
                try { localStorage.setItem('mr_snt_pos', JSON.stringify(_sntPos)); } catch (_) {}
                if (isTab) { _tabDragged = true; setTimeout(() => { _tabDragged = false; }, 60); }
                else       { _barDragged = true; setTimeout(() => { _barDragged = false; }, 60); }
            }
        };
        addEventListener('pointermove', move);
        addEventListener('pointerup', up);
        addEventListener('pointercancel', up);
    });
}

const GR = () => !!window.MR_GR;   // the trial build: the player is always there (fold, never close)

function _bindUI() {
    if (GR()) { const ck = barEl.querySelector('#snt-close-key'); if (ck) ck.style.display = 'none'; }
    barEl.querySelector('#snt-prev').onclick  = () => _cmd('prev');
    barEl.querySelector('#snt-next').onclick  = () => _cmd('next');
    barEl.querySelector('#snt-play').onclick  = () => _cmd('toggle');
    // ＋ = keep what is playing: into a grúpa (an owned record, a streamed one,
    // or whatever the listener's own Spotify is on)
    if (GR()) {
        barEl.querySelector('#snt-grupa-key').style.display = '';
        barEl.querySelector('#snt-grupa').onclick = () => {
            const thing = _nowThing(); if (!thing) return;
            _withGrupaUI(() => window.GrupaUI.addTo(thing, { el: barEl.querySelector('#snt-grupa'), clear: barEl }));
        };
    }
    if (GR()) _outInit();                    // the line that names the speaker, and its list
    // – = minimize to the tab (keep the cue + music, small).
    barEl.querySelector('#snt-min').onclick   = () => _setMode('min');
    // ✕ = stop the music and put the player away (Daithí: no prompt — just stop +
    // close). The cue is kept; it reopens on the next cue or from the Tools bag.
    // MUST drop _forceShow: with an empty cue the render loop resets the mode
    // to 'open' ("fresh start"), and a lingering _forceShow made the bar
    // re-show itself instantly — the player was unclosable when nothing was
    // cued (Daithí, 2026-07-07).
    barEl.querySelector('#snt-close').onclick = () => { _forceShow = false; _post('pause').then(_pollOnce); _setMode('closed'); };
    // the folded-down tab: tap the body to bring the player back; the round
    // button still plays/pauses without reopening
    if (tabEl) {
        tabEl.querySelector('#snt-tab-play').onclick = (e) => { e.stopPropagation(); _cmd('toggle'); };
        tabEl.querySelector('#snt-tab-prev').onclick = (e) => { e.stopPropagation(); _cmd('prev'); };
        tabEl.querySelector('#snt-tab-next').onclick = (e) => { e.stopPropagation(); _cmd('next'); };
        tabEl.onclick = () => { if (_tabDragged) return; _setMode('open'); };   // a drag isn't a tap-to-open
    }
    // sit back with the cue in Just Listen — the server player keeps going, so
    // the music never pauses as the page changes
    barEl.querySelector('#snt-justlisten').onclick = () =>
        (window.rtGo || ((h) => { location.href = h; }))('/justlisten');
    // Deep Listening — the note-taking panel. It opens IN PLACE on ANY page (Daithí):
    // in the room it's already loaded; elsewhere deeplisten.js is fetched on demand
    // so you can jot a note on the playing track from anywhere. Flick between the
    // lenses from the cassette: 👂 Just Listen · 👂✎ Deep Listening · the cassette = player.
    barEl.querySelector('#snt-eist').onclick = _openDeepListen;
    if (GR()) barEl.querySelector('#snt-eist-key').style.display = 'none';   // no notes key on the deck in the trial (Daithí, 2026-10-27)
    barEl.querySelector('#snt-q').onclick     = toggleQpop;
    // click the now-playing title → open that record's full metadata panel.
    // Reuses the same path the queue rows use (keepAudio leaves the music
    // untouched); a drag of the cassette must NOT count as a click.
    const info = barEl.querySelector('#snt-info');
    // The trial deck (Daithí, 2026-11-15): the title opens a small card — the
    // cover, the whole title, who it is by — and the mark in the label's
    // corner says where the record is playing from and opens that place.
    if (info && GR()) {
        info.onclick = () => { if (!_barDragged) toggleCard(); };
        barEl.querySelector('#snt-src').onclick = (e) => { e.stopPropagation(); _srcOpen(); };
        cardEl.addEventListener('click', (e) => { if (e.target.closest('.snt-card__x')) toggleCard(false); });
        document.addEventListener('click', (e) => {
            if (!cardEl.classList.contains('visible') || cardEl.contains(e.target) || e.target.closest('#snt-info')) return;
            toggleCard(false);
        });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && cardEl.classList.contains('visible')) toggleCard(false); });
        addEventListener('resize', () => { if (cardEl.classList.contains('visible')) _cardPlace(); });
    } else if (info) info.onclick = () => {
        if (_barDragged) return;
        const g = _guest();
        if (g) { if (g.url) _post('../open-url', { url: g.url }); return; }
        const it = state.queue[state.idx] || state.queue[0] || {};
        if (it.track_id) _openTrackInPanel(it.track_id);
        else if (it.kind === 'embed' && it.url) _post('../open-url', { url: it.url });
    };
    // ── volume pop-up: a slider that floats away from the bar ──────────
    barEl.querySelector('#snt-vol').onclick = toggleVolPop;
    const vslider = volpopEl && volpopEl.querySelector('#snt-vol-slider');
    if (vslider) vslider.oninput = (e) => {
        const v = Math.max(0, Math.min(1, parseFloat(e.target.value) || 0));
        state.volume = v;                       // optimistic — the poll confirms it
        _updateVolIcon(); _updateVolVal();
        _postVol(v);
    };
    document.addEventListener('click', (e) => {
        if (!volpopEl || !volpopEl.classList.contains('visible')) return;
        if (volpopEl.contains(e.target)) return;
        if (e.target.closest('#snt-vol')) return;   // the toggle handles its own button
        volpopEl.classList.remove('visible');
    });
    const scrub = barEl.querySelector('#snt-scrub');
    scrub.oninput = (e) => {
        // While user drags, lock UI updates briefly so they don't fight
        _scrubLock = Date.now();
    };
    scrub.onchange = (e) => {
        const pct = e.target.value / 1000;
        const g = _guest();
        if (g) { _spotify('seek', (g.duration || 0) * pct); _scrubLock = Date.now() + 1000; setTimeout(_pollOnce, 900); return; }
        const sec = (state.duration || 0) * pct;
        _post('seek', { sec });
        _scrubLock = Date.now() + 1000;
        setTimeout(_pollOnce, 200);
    };
    document.addEventListener('click', (e) => {
        if (!qpopEl || !qpopEl.classList.contains('visible')) return;
        if (qpopEl.contains(e.target)) return;
        if (e.target.closest('#snt-q')) return;
        // adding to the queue is not "clicking away" — keep the queue open
        // (.gcard__cue = the 3D room's cue button; [data-snt-keep] = any other
        // add affordance; seinnteoir-build = the 2D tool's click-to-add mode)
        if (e.target.closest('.gcard__cue, [data-snt-keep]')) return;
        if (document.body.classList.contains('seinnteoir-build')) return;
        qpopEl.classList.remove('visible');
        if (barEl) barEl.classList.remove('expanded');
    });
}

function _fmt(s) {
    if (!isFinite(s) || s == null) return '0:00';
    const m = Math.floor(s / 60), x = Math.floor(s % 60);
    return `${m}:${String(x).padStart(2,'0')}`;
}
function _esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── the room the deck takes ────────────────────────────────────────
// The deck floats over every page, low on the left. Pages keep their own
// bottom-anchored things clear of it by reading two numbers it publishes on
// <html> (2026-11-15 — a dock, a strip and a picture had been sitting under it):
//   --snt-clear  how far up from the bottom of the window it reaches (0px when
//                it isn't resting at the bottom: dragged elsewhere, or absent)
//   --snt-right  where its right edge is, measured from the window's left
// 'snt-box' is sent on window whenever they change.
let _pubClear = -1, _pubRight = -1;
function _publishBox() {
    const el = (barEl && barEl.classList.contains('visible')) ? barEl : (tabEl && tabEl.classList.contains('visible')) ? tabEl : null;
    let clear = 0, right = 0;
    if (el) {
        const r = el.getBoundingClientRect();
        if (r.width && r.bottom > innerHeight - 70) { clear = Math.round(innerHeight - r.top + 10); right = Math.round(r.right + 14); }
    }
    if (clear === _pubClear && right === _pubRight) return;
    _pubClear = clear; _pubRight = right;
    const root = document.documentElement.style;
    root.setProperty('--snt-clear', clear + 'px'); root.setProperty('--snt-right', right + 'px');
    try { window.dispatchEvent(new CustomEvent('snt-box', { detail: { clear, right } })); } catch (_) {}
}
addEventListener('resize', () => setTimeout(_publishBox, 0));

// ─── State render ──────────────────────────────────────────────────
function _render() {
    if (!barEl) return;
    try { return _renderNow(); } finally { _publishBox(); }
}
function _renderNow() {
    const hasQueue = state.queue && state.queue.length > 0;
    if (GR()) {
        if (_mode === 'closed') _mode = 'min';          // never gone in the trial build
    } else if (!hasQueue && _mode !== 'open') {
        // An empty cue is a fresh start — return to 'open' so the next cue shows the
        // full player, not a stale folded/closed state.
        _mode = 'open';
        try { localStorage.setItem('mr_snt_mode', 'open'); } catch (_) {}
        _post('ui_mode', { mode: 'open' });
    }
    // the listener's own Spotify, playing while the deck rests: the deck shows
    // it and its keys drive it (state.guest — see seinnteoir_player.py)
    const g = _guest();
    const sounding = g ? !!g.playing : !!state.playing;
    const showFull = GR() ? _mode === 'open' : ((hasQueue || _forceShow || !!g) && _mode === 'open');
    barEl.classList.toggle('visible', showFull);
    barEl.classList.toggle('playing', sounding);                 // the reels turn
    // the folded spine: in the trial build whenever folded; otherwise only with a cue
    if (tabEl) {
        const showTab = GR() ? _mode === 'min' : ((hasQueue || !!g) && _mode === 'min');
        tabEl.classList.toggle('visible', showTab);
        if (showTab) {
            const cur = g || state.queue[state.idx] || state.queue[0] || null;
            const cntEl = tabEl.querySelector('#snt-tab-count');
            if (cntEl) cntEl.textContent = state.queue.length;
            const tt = tabEl.querySelector('#snt-tab-title');
            const onT = _onNow();
            if (tt) tt.textContent = onT ? [onT.artist, onT.title].filter(Boolean).join(' · ')
                : (cur ? [cur.artist, cur.title].filter(Boolean).join(' · ') : 'nothing playing');
            const tp = tabEl.querySelector('#snt-tab-play');
            if (tp) {
                tp.textContent = sounding ? '⏸' : '▶';
                tp.classList.toggle('playing', sounding);
            }
        }
    }
    if (GR()) _paintSrc();
    if (!showFull) {
        if (qpopEl) qpopEl.classList.remove('visible');
        if (cardEl) cardEl.classList.remove('visible');
        return;
    }
    // Before play, idx is -1 (a silent cue) — show the track that WILL play
    // (queue[0]) rather than "Unknown · Untitled".
    const it = g ? { title: g.title, artist: g.artist, kind: 'embed', url: g.url, duration_sec: g.duration }
                 : (state.queue[state.idx] || state.queue[0] || {});
    const hasItem = !!(g || state.queue[state.idx] || state.queue[0]);
    // an album or playlist sounding in Spotify: the label shows the track it is on
    const on = _onNow();
    barEl.querySelector('#snt-title').textContent  = hasItem ? (on ? on.title : (it.title  || 'Untitled')) : 'nothing playing';
    barEl.querySelector('.snt-artist').textContent = hasItem ? (on ? (on.artist || it.title || '') : (it.artist || 'Unknown')) : '';
    // only a real library track (not a stream/mix) opens a metadata panel
    const infoEl = barEl.querySelector('#snt-info');
    if (infoEl && GR()) {
        // the trial deck: the label opens the card behind it (whatever is on)
        infoEl.classList.toggle('snt-info--link', hasItem);
        infoEl.title = hasItem ? 'Show the whole title and who it is by' : '';
        if (cardEl && cardEl.classList.contains('visible')) { if (hasItem) _cardRender(); else toggleCard(false); }
    } else if (infoEl) {
        infoEl.classList.toggle('snt-info--link', !!it.track_id || it.kind === 'embed');
        infoEl.title = it.track_id ? 'Open this track — full details'
            : (it.kind === 'embed' ? 'Open on ' + (g ? 'Spotify' : (_SERVICE[it.source] || 'the service')) : '');
    }

    const playBtn = barEl.querySelector('#snt-play');
    if (playBtn){
        playBtn.textContent = (state.buffering && !g) ? '⏳' : (sounding ? '⏸' : '▶');
        playBtn.classList.toggle('playing', sounding);          // the deck breathes while it plays
    }
    _updateVolIcon();                                           // 🔊/🔉/🔇 reflects the live volume
    const gk = barEl.querySelector('#snt-grupa');
    if (gk) gk.disabled = !_nowThing();

    const prev = barEl.querySelector('#snt-prev');
    const next = barEl.querySelector('#snt-next');
    if (prev) prev.disabled = g ? false : state.idx <= 0;
    if (next) next.disabled = g ? false : (state.idx < 0 || state.idx >= state.queue.length - 1);
    const qcount = barEl.querySelector('#snt-qcount');
    if (qcount) qcount.textContent = state.queue.length > 1 ? `${state.idx + 1}/${state.queue.length}` : '';

    // Scrub bar (skip if user is actively dragging)
    if (Date.now() > _scrubLock) {
        const scrub = barEl.querySelector('#snt-scrub');
        const dur = g ? (g.duration || 0) : (state.duration || it.duration_sec || 0);
        const pos = g ? (g.position || 0) : state.position;
        if (scrub && dur > 0) {
            scrub.value = Math.round((pos / dur) * 1000);
        } else if (scrub) {
            scrub.value = 0;
        }
        const tEl = barEl.querySelector('#snt-time');
        if (tEl) tEl.textContent = (state.buffering && !g) ? (state.embed_via === 'remote' ? 'starting…' : 'buffering…')
            : `${_fmt(pos)} / ${_fmt(dur)}`;
    }

    _renderQpop();
}

let _lastQpopSig = '';
let _sortableDragging = false;
function _renderQpop() {
    if (!qpopEl) return;
    if (!state.queue || !state.queue.length) {
        qpopEl.innerHTML = ''; _lastQpopSig = ''; return;
    }
    // Don't re-render while the user is mid-drag or typing into a pos input —
    // we'd yank focus / interrupt the drag.
    if (_sortableDragging) return;
    const activeEl = document.activeElement;
    if (activeEl && activeEl.classList && activeEl.classList.contains('snt-qrow__pos')) return;
    const sig = JSON.stringify({
        idx: state.idx,
        ids: state.queue.map(q => q.track_id != null ? q.track_id : (q.qid || q.url || q.title)),
    });
    if (sig === _lastQpopSig && qpopEl.firstChild) return;
    _lastQpopSig = sig;
    const N = state.queue.length;
    const head = `<div class="snt-qhead">
        <span>Queue · ${N}</span>
        <button onclick="window.Seinnteoir.clear()">clear</button>
    </div>`;
    const rows = state.queue.map((it, i) => {
        const active = i === state.idx;
        const trackId = it.track_id != null ? it.track_id : '';
        const main = `${_esc(it.artist || 'Unknown')} — ${_esc(it.title || 'Untitled')}`;
        // where the cue came from: click the chip to open the record IN that
        // place; clicking the title still opens it right here (if it's here)
        const from = (it.place_name && it.place_id && !window.MR_GR)      // no places in the trial
            ? `<span class="snt-qrow__from" data-pid="${it.place_id}" data-tid="${trackId}"
                   title="Cued from ${_esc(it.place_name)} — open it there">@ ${_esc(it.place_name)}</span>`
            : '';
        // the full label as a tooltip — rows truncate, so hover reveals all of it
        const nextup = active ? '' :
            `<button class="snt-qrow__nextup" data-idx="${i}"
                     title="Play next — move right after the current track">⤴</button>`;
        return `<div class="snt-qrow ${active ? 'active' : ''}" data-idx="${i}" data-track-id="${trackId}" title="${main}">
            <span class="snt-qrow__handle" title="Drag to reorder">⋮⋮</span>
            <input class="snt-qrow__pos" type="number" min="1" max="${N}" value="${i + 1}"
                   data-idx="${i}" title="Type a position then Enter">
            <span class="snt-qrow__main" data-track-id="${trackId}" title="${main}">${main}</span>
            ${from}
            ${nextup}
            <button class="snt-qrow__play" data-idx="${i}" title="Play now">▶</button>
            <button class="snt-qrow__x" data-idx="${i}" title="Remove">✕</button>
        </div>`;
    }).join('');
    const rowsId = 'snt-qrows';
    qpopEl.innerHTML = head + `<div id="${rowsId}">${rows}</div>`;
    _bindQpopRows();
    _initSortable();
}

function _bindQpopRows() {
    if (!qpopEl) return;
    qpopEl.querySelectorAll('.snt-qrow__play').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            _playAt(parseInt(btn.dataset.idx, 10));
        };
    });
    qpopEl.querySelectorAll('.snt-qrow__x').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            _remove(parseInt(btn.dataset.idx, 10));
        };
    });
    qpopEl.querySelectorAll('.snt-qrow__nextup').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            _playNext(parseInt(btn.dataset.idx, 10));
        };
    });
    qpopEl.querySelectorAll('.snt-qrow__main').forEach(el => {
        el.onclick = (e) => {
            e.stopPropagation();
            const tid = parseInt(el.dataset.trackId, 10);
            if (tid) _openTrackInPanel(tid);
        };
    });
    qpopEl.querySelectorAll('.snt-qrow__from').forEach(el => {
        el.onclick = (e) => {
            e.stopPropagation();
            const pid = parseInt(el.dataset.pid, 10), tid = parseInt(el.dataset.tid, 10);
            if (!pid) return;
            const href = `/place/${pid}${tid ? `?track=${tid}` : ''}`;
            if (window.rtGo) window.rtGo(href); else location.href = href;
        };
    });
    qpopEl.querySelectorAll('.snt-qrow__pos').forEach(inp => {
        inp.onkeydown = (e) => {
            if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
            if (e.key === 'Escape') {
                inp.value = String(parseInt(inp.dataset.idx, 10) + 1);
                inp.blur();
            }
        };
        inp.onchange = () => _onPosInputChange(inp);
        // Don't bubble clicks to the row
        inp.onclick = (e) => e.stopPropagation();
    });
}

function _onPosInputChange(inp) {
    const fromIdx = parseInt(inp.dataset.idx, 10);
    const N       = state.queue.length;
    let toPos     = parseInt(inp.value, 10);
    if (!Number.isFinite(toPos)) { inp.value = String(fromIdx + 1); return; }
    toPos = Math.max(1, Math.min(N, toPos));
    const toIdx = toPos - 1;
    if (toIdx === fromIdx) { inp.value = String(fromIdx + 1); return; }
    _reorderByMove(fromIdx, toIdx);
}

function _reorderByMove(fromIdx, toIdx) {
    if (!state.queue || !state.queue.length) return;
    if (fromIdx < 0 || fromIdx >= state.queue.length) return;
    // Force qpop to rebuild with the new server state when the poll returns —
    // otherwise stale data-idx attributes from the pre-reorder DOM linger.
    _lastQpopSig = '';
    _post('move', { from: fromIdx, to: toIdx }).then(_pollOnce);
}

// Bump a cue to play next — land it right after the current track (or at the
// top when nothing is playing yet). The record keeps spinning; we just resequence.
function _playNext(fromIdx) {
    if (!state.queue || !state.queue.length) return;
    const c = state.idx;
    if (fromIdx === c) return;                  // already the current track
    if (fromIdx < 0 || fromIdx >= state.queue.length) return;
    // once the row is lifted out, the current track may have shifted left by one
    const insertAt = (c < 0) ? 0 : ((fromIdx < c ? c - 1 : c) + 1);
    _lastQpopSig = '';
    _post('move', { from: fromIdx, to: insertAt }).then(_pollOnce);
}

// ─── SortableJS — drag-reorder the queue popover rows ─────────────
let _sortableLoaded = false;
let _sortableInstance = null;
function _ensureSortable(cb) {
    if (window.Sortable) { _sortableLoaded = true; cb(); return; }
    if (document.querySelector('script[data-snt-sortable]')) {
        // Already injected by us; wait briefly
        const wait = () => window.Sortable ? cb() : setTimeout(wait, 50);
        wait(); return;
    }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
    s.setAttribute('data-snt-sortable', '1');
    s.onload = () => { _sortableLoaded = true; cb(); };
    document.head.appendChild(s);
}

function _initSortable() {
    const rowsEl = qpopEl && qpopEl.querySelector('#snt-qrows');
    if (!rowsEl) return;
    _ensureSortable(() => {
        if (_sortableInstance) {
            try { _sortableInstance.destroy(); } catch (_) {}
            _sortableInstance = null;
        }
        _sortableInstance = window.Sortable.create(rowsEl, {
            handle: '.snt-qrow__handle',
            animation: 140,
            ghostClass: 'snt-ghost',
            chosenClass: 'snt-chosen',
            onStart: () => { _sortableDragging = true; },
            onEnd: (e) => {
                _sortableDragging = false;
                if (e.oldIndex === e.newIndex) return;
                _reorderByMove(e.oldIndex, e.newIndex);
            },
        });
    });
}

// ─── Click-through from cassette row → open the track panel ───────
let _wellId = null;
async function _getWellId() {
    if (_wellId != null) return _wellId;
    try {
        const r = await fetch('/api/places');
        const places = await r.json();
        const well = places.find(p => p.is_well) || places[0];
        if (well) _wellId = well.id;
    } catch (_) {}
    return _wellId;
}

async function _openTrackInPanel(trackId) {
    if (!trackId) return;
    // If we're already on a place page (or in the room), openTrack is defined
    // globally; call it directly so we don't navigate away. keepAudio leaves
    // the Seinnteoir untouched.
    if (typeof window.openTrack === 'function') {
        try {
            window.openTrack(trackId, null, { keepAudio: true });
            return;
        } catch (_) { /* fall through — the record isn't in this room */ }
    }
    // anywhere else: go to the record, open, in the music room
    // (Daithí, 2026-10-27: "it should take me to the song open in the music room")
    if (GR()) { location.href = `/room?track=${trackId}`; return; }
    const wid = await _getWellId();
    if (wid) location.href = `/place/${wid}?track=${trackId}`;
}

// The queue opens AT THE PLAYER — wherever the user has dragged the cassette —
// and hangs BELOW it when the player sits in the top half of the screen, ABOVE
// it when it sits in the bottom half, so the cue is never clipped by an edge. (Daithí)
function _positionQpop() {
    if (!qpopEl || !barEl) return;
    const r = _deckBox();
    const qh = qpopEl.offsetHeight || 300, qw = qpopEl.offsetWidth || 320;
    const below = !r.above;
    let top = below ? (r.bottom + 8) : (r.top - qh - 8);
    top  = Math.max(8, Math.min(innerHeight - qh - 8, top));
    const left = Math.max(8, Math.min(innerWidth - qw - 8, r.left));
    qpopEl.style.setProperty('left', left + 'px', 'important');
    qpopEl.style.setProperty('top',  top  + 'px', 'important');
    qpopEl.style.setProperty('right',  'auto', 'important');
    qpopEl.style.setProperty('bottom', 'auto', 'important');
}
function toggleQpop() {
    if (!qpopEl) return;
    qpopEl.classList.toggle('visible');
    const open = qpopEl.classList.contains('visible');
    if (open){ if (cardEl) cardEl.classList.remove('visible'); _renderQpop(); _positionQpop(); }
    if (barEl) barEl.classList.toggle('expanded', open);
}

// ─── volume pop-up ──────────────────────────────────────────────────
// Opens AWAY from the bar so it never covers the player: above the button when
// the player sits in the bottom half of the screen, below when it's up top —
// and clamped on-screen either way. (Daithí: don't block the player.)
function _positionVolPop() {
    if (!volpopEl || !barEl) return;
    const btn = barEl.querySelector('#snt-vol');
    const br = _deckBox();                              // gap measured from the whole deck (and a player riding on it)
    const cr = (btn || barEl).getBoundingClientRect();  // centred on the speaker button
    const ph = volpopEl.offsetHeight || 44, pw = volpopEl.offsetWidth || 176;
    const above = br.above;
    let top = above ? (br.top - ph - 8) : (br.bottom + 8);
    top  = Math.max(8, Math.min(innerHeight - ph - 8, top));
    let left = cr.left + cr.width / 2 - pw / 2;
    left = Math.max(8, Math.min(innerWidth - pw - 8, left));
    volpopEl.style.setProperty('left', left + 'px', 'important');
    volpopEl.style.setProperty('top',  top  + 'px', 'important');
    volpopEl.style.setProperty('right',  'auto', 'important');
    volpopEl.style.setProperty('bottom', 'auto', 'important');
}
function toggleVolPop() {
    if (!volpopEl) return;
    const open = !volpopEl.classList.contains('visible');
    volpopEl.classList.toggle('visible', open);
    if (open) {
        if (cardEl) cardEl.classList.remove('visible');
        const vslider = volpopEl.querySelector('#snt-vol-slider');
        if (vslider) vslider.value = state.volume;     // reflect the live volume
        _updateVolVal(); _updateVolIcon();
        _positionVolPop();
    }
}
// ─── where the sound goes (the trial deck) ──────────────────────────
// Daithí, 2026-11-14: "connect to bluetooth and wifi devices such as speakers
// directly from in the app like the spotify app." Everything the app plays
// leaves by the Mac's one chosen output, so the deck names it ("out · …") and
// a click opens the list: what the Mac can play through now, the Bluetooth
// speakers it knows but isn't connected to, and a way into the Mac's own Sound
// settings for the rest. Server side: sound_out.py (/api/sound/*).
let _outState = null, _outBusy = '', _outSay = null;
const _outJson = (path, body) => fetch('/api/sound/' + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
async function _outLoad(paired) {
    try {
        const d = await _outJson('outputs' + (paired ? '?paired=1' : ''));
        if (!paired && _outState && _outState.bluetooth !== undefined) d.bluetooth = _outState.bluetooth;   // keep the list we have
        _outState = d;
    } catch (_) { /* leave what we had */ }
    _outPaint();
}
function _outPaint() {
    const line = barEl && barEl.querySelector('#snt-out');
    if (!line) return;
    const d = _outState, cur = d && (d.outputs || []).find(o => o.current);
    line.classList.toggle('on', !!(d && d.supported && cur));
    if (cur) barEl.querySelector('#snt-out-name').textContent = cur.name;
    if (outpopEl && outpopEl.classList.contains('visible')) _outRender();
}
function _outRender() {
    const d = _outState || {};
    const rows = (d.outputs || []).map(o =>
        `<button class="snt-outrow${o.current ? ' on' : ''}" data-uid="${_esc(o.uid)}"${_outBusy ? ' disabled' : ''}>
            <span class="snt-outrow__m"></span><span class="snt-outrow__n">${_esc(o.name)}</span><span class="snt-outrow__k">${_esc(o.kind || '')}</span></button>`).join('');
    let bt = '';
    if (d.bluetooth === undefined) bt = `<div class="snt-outpop__h">Bluetooth</div><div class="snt-outpop__say">Looking…</div>`;
    else if (d.bluetooth === null) bt = `<div class="snt-outpop__h">Bluetooth</div><div class="snt-outpop__say">Bluetooth is off on this computer.</div>`;
    else if (d.bluetooth.length) bt = `<div class="snt-outpop__h">Bluetooth · not connected</div>` + d.bluetooth.map(b =>
        `<button class="snt-outrow snt-outrow--bt" data-bt="${_esc(b.address)}" data-name="${_esc(b.name)}"${_outBusy ? ' disabled' : ''}>
            <span class="snt-outrow__m"></span><span class="snt-outrow__n">${_esc(b.name)}</span>
            <span class="snt-outrow__k">${_outBusy === b.address ? 'connecting…' : 'connect'}</span></button>`).join('');
    const say = _outSay ? `<div class="snt-outpop__say${_outSay.bad ? ' bad' : ''}">${_esc(_outSay.text)}</div>` : '';
    outpopEl.innerHTML = `<div class="snt-outpop__h">Sound goes to</div>${rows || '<div class="snt-outpop__say">No speaker found.</div>'}${say}${bt}
        <div class="snt-outpop__h">Not on the list?</div>
        <button class="snt-outrow snt-outrow--more" data-pane="sound"><span class="snt-outrow__n">Open the Mac's sound settings</span><span class="snt-outrow__k">↗</span></button>
        <button class="snt-outrow snt-outrow--more" data-pane="bluetooth"><span class="snt-outrow__n">Pair a new Bluetooth speaker</span><span class="snt-outrow__k">↗</span></button>`;
    _outPlace();
}
function _outPlace() {
    if (!outpopEl || !barEl) return;
    const br = _deckBox(), lr = barEl.querySelector('#snt-out').getBoundingClientRect();
    const ph = outpopEl.offsetHeight || 200, pw = outpopEl.offsetWidth || 318;
    const above = br.above;
    const top = Math.max(8, Math.min(innerHeight - ph - 8, above ? br.top - ph - 8 : br.bottom + 8));
    const left = Math.max(8, Math.min(innerWidth - pw - 8, lr.left - 12));
    for (const [k, v] of [['left', left + 'px'], ['top', top + 'px'], ['right', 'auto'], ['bottom', 'auto']]) outpopEl.style.setProperty(k, v, 'important');
}
const _OUT_WHY = { gone: 'That speaker is no longer there.', refused: 'The Mac would not switch to it.', unsupported: 'Not available on this computer.',
    failed: 'Could not connect. Is it switched on and close by?', slow: 'It connected, but the Mac has not offered it as a speaker yet. Try once more.', bad: 'Could not connect.' };
function toggleOutPop(force) {
    if (!outpopEl) return;
    const open = force === undefined ? !outpopEl.classList.contains('visible') : !!force;
    outpopEl.classList.toggle('visible', open);
    barEl.querySelector('#snt-out').classList.toggle('open', open);
    if (!open) return;
    _outSay = null;
    if (volpopEl) volpopEl.classList.remove('visible');
    if (cardEl) cardEl.classList.remove('visible');
    _outRender();
    _outLoad(true);                          // fresh outputs + the Bluetooth speakers this Mac knows
}
function _outInit() {
    barEl.querySelector('#snt-out').onclick = () => toggleOutPop();
    outpopEl.addEventListener('click', async e => {
        const row = e.target.closest('.snt-outrow'); if (!row || _outBusy) return;
        if (row.dataset.pane) { _outJson('settings', { pane: row.dataset.pane }).catch(() => {}); return; }
        _outSay = null;
        try {
            if (row.dataset.uid) {
                if (row.classList.contains('on')) return;
                _outBusy = 'out'; _outRender();
                const d = await _outJson('output', { uid: row.dataset.uid });
                if (d.outputs) _outState = Object.assign({}, _outState, { outputs: d.outputs, supported: d.supported });
                if (!d.ok) _outSay = { bad: true, text: _OUT_WHY[d.why] || 'Could not switch.' };
            } else if (row.dataset.bt) {
                _outBusy = row.dataset.bt; _outRender();
                const d = await _outJson('bluetooth/connect', { address: row.dataset.bt, name: row.dataset.name || '' });
                if (d.outputs) _outState = d;
                if (!d.ok) _outSay = { bad: true, text: _OUT_WHY[d.why] || 'Could not connect.' };
            }
        } catch (_) { _outSay = { bad: true, text: 'Could not reach the player.' }; }
        _outBusy = ''; _outPaint();
    });
    document.addEventListener('click', e => {
        if (!outpopEl.classList.contains('visible') || outpopEl.contains(e.target) || e.target.closest('#snt-out')) return;
        toggleOutPop(false);
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && outpopEl.classList.contains('visible')) toggleOutPop(false); });
    addEventListener('resize', () => { if (outpopEl.classList.contains('visible')) _outPlace(); });
    _outLoad(false);
    // headphones plugged in, a speaker switched off, a choice made in the Mac's own menu: keep the line true
    setInterval(() => { if (!document.hidden && !_outBusy) _outLoad(false); }, 15000);
}
function _updateVolIcon() {
    const btn = barEl && barEl.querySelector('#snt-vol');
    if (!btn) return;
    const v = state.volume || 0;
    btn.textContent = v <= 0.001 ? '🔇' : (v < 0.5 ? '🔉' : '🔊');
}
function _updateVolVal() {
    const val = volpopEl && volpopEl.querySelector('#snt-vol-val');
    if (val) val.textContent = Math.round((state.volume || 0) * 100) + '%';
}
// throttle the POSTs while dragging — send immediately, then the trailing value
let _volTimer = null, _volLatest = null;
function _postVol(v) {
    _volLatest = v;
    if (_volTimer) return;
    _post('volume', { volume: v });
    _volTimer = setTimeout(() => {
        _volTimer = null;
        if (_volLatest !== v) _post('volume', { volume: _volLatest });
    }, 90);
}

// ─── Server talk ───────────────────────────────────────────────────
async function _post(endpoint, body) {
    try {
        const init = { method: 'POST' };
        if (body !== undefined) {
            init.headers = { 'Content-Type': 'application/json' };
            init.body = JSON.stringify(body);
        }
        await fetch('/api/seinnteoir/' + endpoint, init);
    } catch (_) {}
}

// ─── skipped-track notice ───────────────────────────────────────────
// A track the player couldn't play used to vanish from under the needle with
// only a server-side print. Show why, briefly, wherever the cassette lives.
function _showErrToast(err) {
    _injectCSS();                      // idempotent — the toast can fire before the bar exists
    let el = document.getElementById('snt-err-toast');
    if (!el) {
        el = document.createElement('div');
        el.id = 'snt-err-toast';
        document.body.appendChild(el);
    }
    el.textContent = `skipped “${err.title}” — ${err.reason}`;
    el.classList.add('visible');
    clearTimeout(el._hideT);
    el._hideT = setTimeout(() => el.classList.remove('visible'), 7000);
}

function _checkErr() {
    const err = state.last_error;
    if (err && err.at !== _lastErrAt) {
        // first poll of a page load: only toast an error from the last few
        // seconds — anything older already showed on the page that saw it.
        const fresh = (Date.now() / 1000 - err.at) < 6;
        if (_errBaselined || fresh) _showErrToast(err);
        _lastErrAt = err.at;
    }
    _errBaselined = true;
}

async function _pollOnce() {
    try {
        const r = await fetch('/api/seinnteoir/state', { cache: 'no-store' });
        if (!r.ok) return;
        const prevPlaying = _lastPlaying;
        const prevQLen = _prevQLen;
        state = await r.json();
        _embedTick();
        _checkErr();
        // ONE-TIME on the first poll: if localStorage held no mode (the desktop
        // shell wipes it on relaunch), take the server's remembered one — a
        // player put away before quitting STAYS put away after a relaunch.
        if (!_modeAdopted) {
            _modeAdopted = true;
            if (!_modeFromStorage && ['open', 'min', 'closed'].includes(state.ui_mode)) {
                _mode = state.ui_mode;
                try { localStorage.setItem('mr_snt_mode', _mode); } catch (_) {}
            }
        }
        // a freshly cued track reopens a put-away player (Daithí: "open it again
        // by cueing tracks or from the Mála")
        const qlen = state.queue ? state.queue.length : 0;
        // only a genuine growth from a known baseline is a "fresh cue" — never
        // the first poll (prevQLen === null), which just adopts the current cue.
        if (prevQLen !== null && _mode === 'closed' && qlen > prevQLen) {
            _mode = 'open';
            try { localStorage.setItem('mr_snt_mode', 'open'); } catch (_) {}
            _post('ui_mode', { mode: 'open' });
        }
        _prevQLen = qlen;
        _ensureBar();
        _render();
        // One-player-at-a-time: when the Seinnteoir transitions from not-
        // playing → playing, pause any browser <audio> on this page so we
        // don't get music layered on music. The place ambient loop is
        // exempt — it's quiet atmosphere meant to sit UNDER the music.
        if (state.playing && !prevPlaying) {
            document.querySelectorAll('audio:not(.place-ambient)').forEach((a) => {
                try { if (!a.paused) a.pause(); } catch (_) {}
            });
        }
        _lastPlaying = !!state.playing;
    } catch (_) {}
}

// ─── streamed records (Spotify / SoundCloud) ────────────────────────────────
// They sit in the same cue as owned records, but only their own service may
// play them: the listener's own Spotify (driven by the server), or the
// service's player on a slip beside the deck (snt_embed.js, driven from
// here). Loaded the first time a streamed record comes up.
const _SERVICE = { spotify: 'Spotify', soundcloud: 'SoundCloud' };
// the listener's own Spotify, when the deck is at rest and it is on something
// (only when its keys would work: a listener without Premium can't be driven)
function _guest() { return (!state.playing && state.guest && state.guest.control) ? state.guest : null; }
function _spotify(action, value) {
    return fetch('/api/spotify/control', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, value }) }).catch(() => {});
}
// a transport key: the deck's own cue — or, while the deck shows the
// listener's Spotify, that
function _cmd(name) {
    const g = _guest();
    if (!g) return _post(name).then(_pollOnce);
    if (name === 'toggle') { g.playing = !g.playing; _render(); }     // answer at once; the poll confirms
    return _spotify(name).then(() => setTimeout(_pollOnce, name === 'toggle' ? 150 : 900));
}
// an album / playlist of ours sounding in the listener's Spotify: its current track
function _onNow() {
    const r = state.remote;
    return (!_guest() && state.embed_via === 'remote' && r && r.title && state.idx >= 0) ? r : null;
}
// what "＋ grúpa" would keep right now
function _nowThing() {
    const g = _guest();
    if (g) return g.url ? { url: g.url, title: g.title, subtitle: g.artist, image: g.image_url, by_ids: g.by_ids, duration_sec: g.duration } : null;
    const it = state.queue[state.idx] || state.queue[0];
    if (!it) return null;
    if (it.track_id) return { kind: 'track', ref_id: it.track_id };
    if (it.url) return { url: it.url };          // a streamed record, or a mix's own page
    return null;
}
function _withGrupaUI(cb) {
    if (window.GrupaUI) return cb();
    if (!document.querySelector('link[href*="/static/css/grupa.css"]')) {
        const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/static/css/grupa.css';
        document.head.appendChild(l);
    }
    if (document.querySelector('script[data-grupa-ui]')) {
        const wait = () => window.GrupaUI ? cb() : setTimeout(wait, 50);
        return wait();
    }
    const s = document.createElement('script');
    s.src = '/static/js/grupa_ui.js'; s.setAttribute('data-grupa-ui', '1'); s.onload = cb;
    document.head.appendChild(s);
}

// ─── where it is playing from: the mark on the label, and the card behind the title ───
// (the trial deck — Daithí, 2026-11-15: no bar above the player saying "this is
// in Spotify"; a small Spotify mark on the player instead, which opens Spotify;
// a disc when the record is a file on this laptop; ".web" for a website; and so
// on for whatever is added later.) One entry here per place a record can sound.
const _SRC_ICON = {
    spotify: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10.5" fill="currentColor"/><g fill="none" stroke="var(--snt-src-cut, #f7f5f0)" stroke-linecap="round"><path d="M6.9 9.3c3.5-1.1 7.4-.8 10.5 1" stroke-width="1.9"/><path d="M7.6 12.6c2.9-.9 6-.6 8.6.9" stroke-width="1.6"/><path d="M8.3 15.7c2.3-.7 4.6-.5 6.6.7" stroke-width="1.3"/></g></svg>',
    soundcloud: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.4 14.1v2.8M4.9 12.5v4.4M7.4 13.3v3.6M9.9 10.3v6.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path fill="currentColor" d="M11.9 16.9V8.3c.7-.4 1.5-.6 2.3-.6 2.5 0 4.5 1.9 4.8 4.3.3-.1.6-.1.9-.1 1.4 0 2.5 1.1 2.5 2.5s-1.1 2.5-2.5 2.5z"/></svg>',
    cd: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3.3"/><circle cx="12" cy="12" r=".8" fill="currentColor" stroke="none"/><path d="M14.2 8.2l2.5-4.3M15.6 9.5l4.1-2.9M9.8 15.8l-2.5 4.3M8.4 14.5l-4.1 2.9" stroke-width="1.1" stroke-linecap="round"/></svg>',
    web: '.web',
};
const _host = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (_) { return ''; } };
// → { k: which mark, tip: what the pointer is told, can: a click goes somewhere, url?, track_id? }
function _srcNow() {
    const g = _guest();
    if (g) return { k: 'spotify', can: true, url: g.url || '',
        tip: 'In your Spotify' + (g.device ? ' · ' + g.device : '') + (g.playing ? '' : ' · paused') + '. Click to open Spotify.' };
    const it = state.queue && (state.queue[state.idx] || state.queue[0]);
    if (!it) return null;
    if (it.kind === 'embed') {
        if (it.source === 'spotify') {
            const dev = state.remote && state.remote.device;
            const where = state.embed_via === 'remote' ? 'In your Spotify' + (dev ? ' · ' + dev : '')
                : (state.embed_via === 'page' ? "In Spotify's own player, above" : 'On Spotify');
            return { k: 'spotify', can: true, url: it.url || '', tip: where + '. Click to open Spotify.' };
        }
        if (it.source === 'soundcloud') return { k: 'soundcloud', can: !!it.url, url: it.url || '', tip: 'On SoundCloud. Click to open it there.' };
        return { k: 'web', can: !!it.url, url: it.url || '', tip: 'From ' + (_host(it.url) || 'a website') + (it.url ? '. Click to open the page.' : '') };
    }
    if (it.kind === 'stream') return { k: 'web', can: !!it.url, url: it.url || '', tip: 'From ' + (_host(it.url) || 'a website') + (it.url ? '. Click to open the page.' : '') };
    if (it.kind === 'borrow') return { k: 'cd', can: false, tip: 'A borrowed record, playing from this laptop' };
    return { k: 'cd', can: !!it.track_id, track_id: it.track_id, tip: 'A file on this laptop' + (it.track_id ? '. Click to open the record.' : '') };
}
function _paintSrc() {
    if (!barEl) return;
    const s = _srcNow(), sig = s ? [s.k, s.tip, s.can ? 1 : 0].join('|') : '';
    const b = barEl.querySelector('#snt-src'), t = tabEl && tabEl.querySelector('#snt-tab-src');
    if (b && b._sig !== sig) {
        b._sig = sig;
        b.className = 'snt-src' + (s ? ' on' : '') + (s && s.k === 'web' ? ' snt-src--web' : '') + (s && s.can ? ' can' : '');
        b.innerHTML = s ? _SRC_ICON[s.k] : '';
        b.title = s ? s.tip : ''; b.setAttribute('aria-label', s ? s.tip : '');
        b.tabIndex = s && s.can ? 0 : -1;
    }
    if (t && t._sig !== sig) {
        t._sig = sig;
        t.className = 'snt-tab__src' + (s ? ' on' : '');
        t.innerHTML = s ? _SRC_ICON[s.k] : '';
        t.title = s ? s.tip.replace(/\. Click.*$/, '') : '';
    }
}
function _srcOpen() {
    const s = _srcNow(); if (!s || !s.can) return;
    if (s.k === 'spotify') {            // bring Spotify forward — nothing is played, paused or skipped
        fetch('/api/spotify/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: s.url }) }).catch(() => {});
        return;
    }
    if (s.track_id) { toggleCard(false); _openTrackInPanel(s.track_id); return; }
    if (s.url) _post('../open-url', { url: s.url });
}

// The deck and anything riding on it (the service's own player on its slip):
// a pop-up opens clear of both, above when the deck sits low, below when high.
function _deckBox() {
    const host = (barEl && barEl.classList.contains('visible')) ? barEl : tabEl;
    const r = host.getBoundingClientRect();
    let top = r.top, bottom = r.bottom;
    const slip = document.getElementById('snt-embed');
    if (slip && slip.style.display !== 'none' && slip.offsetHeight) {
        const s = slip.getBoundingClientRect();
        top = Math.min(top, s.top); bottom = Math.max(bottom, s.bottom);
    }
    return { left: r.left, width: r.width, top, bottom, above: (r.top + r.height / 2) >= innerHeight / 2 };
}

// ── the card behind the title ──
// "A little info card that looks like the back of a tape": the spine, the
// cover, and ruled lines carrying the whole title, who it is by, and what else
// is known (the album, the year and the label of a record in the room).
const _cardMeta = {};                     // track id → { album, year, label } once asked ('' while asking)
function _cardThing() {
    const g = _guest();
    if (g) return { key: 'g|' + g.url, title: g.title, artist: g.artist, image: g.image_url, from: 'Spotify' + (g.device ? ' · ' + g.device : '') };
    const it = state.queue && (state.queue[state.idx] || state.queue[0]);
    if (!it) return null;
    if (it.kind === 'embed') {
        const on = _onNow();              // an album or a playlist: the track it is on
        const dev = state.embed_via === 'remote' && state.remote && state.remote.device;
        const set = on && it.title && it.title !== on.title ? it.title : '';
        return { key: 'e|' + it.qid + '|' + (on ? on.title : ''), title: on ? on.title : it.title, artist: on ? (on.artist || '') : it.artist, image: it.image_url,
                 set, setKind: set ? (it.stream_type === 'playlist' ? 'Playlist' : it.stream_type === 'album' ? 'Album' : 'In') : '',
                 from: (_SERVICE[it.source] || _host(it.url) || 'A stream') + (dev ? ' · ' + dev : '') };
    }
    if (it.kind === 'stream') return { key: 's|' + (it.url || it.title), title: it.title, artist: it.artist, image: it.image_url, from: _host(it.url) || 'A website' };
    if (it.kind === 'borrow') return { key: 'b|' + it.title + '|' + it.artist, title: it.title, artist: it.artist, image: it.image_url, from: 'Borrowed · this laptop' };
    return { key: 't|' + it.track_id, title: it.title, artist: it.artist, track_id: it.track_id,
             image: it.track_id ? '/api/artwork/' + it.track_id + '?s=384' : '', from: 'This laptop' };
}
function _cardRender() {
    if (!cardEl) return;
    const c = _cardThing(); if (!c) return;
    const more = c.track_id ? _cardMeta[c.track_id] : null;
    if (c.track_id && more === undefined) {          // a record in the room: ask once for its album, year and label
        _cardMeta[c.track_id] = '';
        fetch('/api/track/' + c.track_id).then(r => r.json()).then(d => {
            const t = (d && d.track) || {};
            _cardMeta[c.track_id] = { album: t.album || '', year: t.year || '', label: t.label || '', title: t.title || '', artist: t.artist_name || '' };
            if (cardEl.classList.contains('visible')) _cardRender();
        }).catch(() => { _cardMeta[c.track_id] = {}; });
    }
    const m = more || {};
    const title = (m.title || c.title || 'Untitled'), artist = (m.artist || c.artist || '');
    const sig = [c.key, title, artist, c.image, c.set, c.from, m.album, m.year, m.label].join('|');
    if (cardEl._sig === sig) return;
    cardEl._sig = sig;
    const row = (k, v, cls) => v ? `<div class="snt-card__row"><span class="snt-card__k">${k}</span><span class="snt-card__v${cls ? ' ' + cls : ''}">${_esc(v)}</span></div>` : '';
    cardEl.innerHTML = `
        <div class="snt-card__spine"><span>${_esc([artist, title].filter(Boolean).join(' — '))}</span></div>
        <div class="snt-card__art"><span>${_esc((title.trim()[0] || '·').toUpperCase())}</span>${c.image ? `<img src="${_esc(c.image)}" alt="" onerror="this.remove()">` : ''}</div>
        <div class="snt-card__back">
            <div class="snt-card__head"><span class="snt-card__side">Side A</span><button type="button" class="snt-card__x" title="Close" aria-label="Close">✕</button></div>
            ${row('Title', title, 'snt-card__v--t')}
            ${row('Artist', artist)}
            ${row(c.setKind || 'In', c.set)}
            ${row('Album', m.album)}
            ${row('Year', m.year ? String(m.year) : '')}
            ${row('Label', m.label)}
            ${row('From', c.from, 'snt-card__v--m')}
            <div class="snt-card__rest"></div>
        </div>`;
    _cardPlace();
    const img = cardEl.querySelector('img'); if (img) img.addEventListener('load', _cardPlace);
}
function _cardPlace() {
    if (!cardEl || !barEl) return;
    const d = _deckBox(), h = cardEl.offsetHeight || 170, w = cardEl.offsetWidth || 522;
    const top = Math.max(8, Math.min(innerHeight - h - 8, d.above ? d.top - h - 8 : d.bottom + 8));
    const left = Math.max(8, Math.min(innerWidth - w - 8, d.left));
    for (const [k, v] of [['left', left + 'px'], ['top', top + 'px'], ['right', 'auto'], ['bottom', 'auto']]) cardEl.style.setProperty(k, v, 'important');
}
function toggleCard(force) {
    if (!cardEl) return;
    const open = force === undefined ? !cardEl.classList.contains('visible') : !!force;
    if (open && !_cardThing()) return;
    cardEl.classList.toggle('visible', open);
    if (!open) return;
    if (qpopEl) { qpopEl.classList.remove('visible'); barEl.classList.remove('expanded'); }   // one thing open above the deck at a time
    if (volpopEl) volpopEl.classList.remove('visible');
    if (outpopEl && outpopEl.classList.contains('visible')) toggleOutPop(false);
    cardEl._sig = '';
    _cardRender();
}

let _embedLive = null, _embedAsked = false;
function _embedTick() {
    _embedLive = null;
    const cur = state.queue && state.queue[state.idx];
    const isEmbed = !!(cur && cur.kind === 'embed');
    if (_overlaid) return;                       // the page behind has the deck
    if (!window.SntEmbed) {
        if ((isEmbed || _guest()) && !_embedAsked) {
            _embedAsked = true;
            const s = document.createElement('script');
            s.src = '/static/js/snt_embed.js'; s.onload = _pollOnce;
            document.head.appendChild(s);
        }
        return;
    }
    state._srvPos = state.position;
    window.SntEmbed.sync(state, {
        post: _post, poll: _pollOnce,
        deck: () => (barEl && barEl.classList.contains('visible')) ? barEl
                  : (tabEl && tabEl.classList.contains('visible')) ? tabEl : null,
        tick: _embedPaint,
    });
    if (isEmbed) _embedPaint(true);
}
// the service's player knows where the record really is — show its clock
function _embedPaint(quiet) {
    const cur = state.queue && state.queue[state.idx];
    const live = window.SntEmbed && cur ? window.SntEmbed.live(cur.qid) : null;
    _embedLive = live;
    if (!live) return;
    state.position = live.position || 0;
    if (live.duration) state.duration = live.duration;
    if (quiet !== true) _render();
}

function _startPolling() {
    if (_pollTimer) return;
    _pollOnce();
    _pollTimer = setInterval(_pollOnce, POLL_MS);
}

// ─── Public API ─────────────────────────────────────────────────────
// pages that ARE a place set window.MR_PLACE_CTX = {id, name} so every cue
// remembers where it came from (the queue shows it + offers the jump back)
function _placeCtx(t) {
    if (t.place_id) return { place_id: t.place_id, place_name: t.place_name || '' };
    const c = window.MR_PLACE_CTX;
    return c && c.id ? { place_id: c.id, place_name: c.name || '' } : {};
}

async function add(tracks) {
    const items = (tracks || []).filter(t => t && (t.file_id || _isEmbed(t))).map(t => _isEmbed(t) ? _embedItem(t) : Object.assign({
        track_id: t.track_id ?? t.id ?? null,
        file_id:  t.file_id,
        title:    t.title || '',
        artist:   t.artist || t.artist_name || '',
    }, _placeCtx(t)));
    if (!items.length) return 0;
    await _post('add', { items });
    _pollOnce();
    return items.length;
}

const _isEmbed = t => !!(t && t.kind === 'embed' && t.url);
function _embedItem(t) {
    return { kind: 'embed', url: t.url, source: t.source || '', stream_type: t.stream_type || '',
             title: t.title || '', artist: t.artist || '', image_url: t.image_url || '', duration_sec: t.duration_sec || 0,
             once: !!t.once };
}
// record shopping's one play of a streamed record: it plays now, straight after
// the record playing, and leaves the cue as soon as the deck moves off it
async function playOnce(t) {
    if (!_isEmbed(t)) return 0;
    await _post('add', { items: [Object.assign(_embedItem(t), { once: true })], play_now: true });
    _ensureBar(); _setMode('open'); _pollOnce();
    return 1;
}
async function playAll(tracks, startIdx) {
    const items = (tracks || []).filter(t => t && (t.file_id || _isEmbed(t))).map(t => _isEmbed(t) ? _embedItem(t) : Object.assign({
        track_id: t.track_id ?? t.id ?? null,
        file_id:  t.file_id,
        title:    t.title || '',
        artist:   t.artist || t.artist_name || '',
    }, _placeCtx(t)));
    if (!items.length) return 0;
    await _post('queue', { items, idx: startIdx || 0, autoplay: true });
    _pollOnce();
    return items.length;
}

// ─── remote audio from Explore (a mix / podcast) ────────────────────────────
// Plays through the SAME persistent server player as library tracks, so the
// mix keeps going as you move around the app. The server downloads it to cache,
// then plays — so there's a brief "buffering…" before sound.
function _streamItem(s) {
    return {
        audio_url:    s.audio_url,
        title:        s.title || '',
        artist:       s.artist || s.source || s.source_name || '',
        duration_sec: s.duration_sec || s.audio_duration_sec || 0,
        image_url:    s.image_url || '',
        url:          s.url || '',
        feed_item_id: s.feed_item_id || s.id || null,
    };
}
async function playStream(s) {       // play now (replaces the cue)
    if (!s || !s.audio_url) return;
    await _post('queue', { items: [_streamItem(s)], idx: 0, autoplay: true });
    _ensureBar(); _setMode('open'); _pollOnce();
}
async function cueStream(s) {        // add to the end of the cue, play if idle
    if (!s || !s.audio_url) return;
    await _post('add', { items: [_streamItem(s)], autostart: true });
    _ensureBar(); _setMode('open'); _pollOnce();
}

function clear()       { _post('clear').then(_pollOnce); }
function togglePlay()  { _post('toggle').then(_pollOnce); }
function next()        { _post('next').then(_pollOnce); }
function prev()        { _post('prev').then(_pollOnce); }
function _playAt(i)    { _post('play_at', { idx: i }).then(_pollOnce); }
function _remove(i)    { _post('remove', { idx: i }).then(_pollOnce); }
function isActive()    { return state.queue && state.queue.length > 0; }
function getState()    { return JSON.parse(JSON.stringify(state)); }
// bring the player back (Tools → Player, or any "show the player" affordance)
function open()        { _forceShow = true;  _ensureBar(); _setMode('open'); }
function minimize()    { _forceShow = false; _ensureBar(); _setMode('min'); }
function putAway()     { _forceShow = false; _ensureBar(); _setMode('closed'); }

// open the Deep Listening panel from anywhere — loads deeplisten.js on demand
// (the 3D room already has it) so the note-taking panel works on every page
function _openDeepListen() {
    if (typeof window.openEisteacht === 'function') return window.openEisteacht();
    if (document.querySelector('script[data-deeplisten]')) {
        const wait = () => window.openEisteacht ? window.openEisteacht() : setTimeout(wait, 50);
        return wait();
    }
    const s = document.createElement('script');
    s.src = '/static/js/deeplisten.js'; s.setAttribute('data-deeplisten', '1');
    s.onload = () => { if (window.openEisteacht) window.openEisteacht(); };
    document.head.appendChild(s);
}

window.Seinnteoir = {
    add, playAll, playOnce, playStream, cueStream, clear, togglePlay, next, prev,
    isActive, getState, open, minimize, putAway,
    _playAt, _remove,
};

// a page opened INSIDE another (the room's overlay, Explore's room window)
// brings no deck of its own — the page behind it has one
const _overlaid = /[?&](overlay|panelonly|toolonly)=1/.test(location.search) || window.self !== window.top;
if (_overlaid) {
    // still answer the API (add/playAll from inside the overlay reach the same server player)
} else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _startPolling);
} else {
    _startPolling();
}

})();
