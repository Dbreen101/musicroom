// =============================================================
// wish_note.js — "Note it for later".
//
// A small window that asks one thing about a record you can't decide on yet:
// why this one? The record's name, who it is by, where you came across it and
// your own line go onto the wishlist (which holds 100 — record_shop.py).
// Stands on any page: it brings its own few styles and reads the page's
// colours where they are named (the app's, or a public room's own).
//
//   WishNote.open(anchor, { record, found })           → Promise<{noted, wish} | null>
//   WishNote.open(anchor, { blind: true, save(why) })  — the caller does the saving
//        (blind listening: the record is only turned over once it is noted);
//        save returns {ok, error?, full?}
//   WishNote.save(record, why, found)                  → {ok, noted?, wish?, error?, full?}
//   WishNote.close()
//
// The words are functional; David coins the real ones.
// =============================================================
window.WishNote = (function () {
'use strict';

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let box = null, done = null, cssDone = false;

function css() {
    if (cssDone) return; cssDone = true;
    const s = document.createElement('style');
    s.textContent = `
.wn, .wn * { box-sizing: border-box; border-radius: 0; }
.wn { --wn-bg: var(--bg, var(--pr-bg, #f2efe8)); --wn-ink: var(--text, var(--pr-ink, #161513)); --wn-muted: var(--muted, #6e6a61);
  --wn-line: var(--border, rgba(22,21,19,.22)); --wn-red: var(--red, #c9412f);
  position: fixed; z-index: 9500; width: 340px; max-width: calc(100vw - 16px); display: flex; flex-direction: column;
  background: var(--wn-bg); color: var(--wn-ink); border: 1px solid var(--wn-ink); box-shadow: 0 18px 50px var(--shadow, rgba(0,0,0,.28));
  font-family: var(--f-mono, "IBM Plex Mono", ui-monospace, Menlo, monospace); text-align: left; }
.wn__h { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 8px 10px 14px; border-bottom: 1px solid var(--wn-line);
  font-size: .64rem; letter-spacing: .12em; text-transform: uppercase; }
.wn__x { appearance: none; -webkit-appearance: none; width: 26px; height: 26px; padding: 0; background: none; border: 1px solid transparent; color: var(--wn-muted);
  font: inherit; font-size: .8rem; line-height: 1; cursor: pointer; }
.wn__x:hover { color: var(--wn-bg); background: var(--wn-ink); }
.wn__what { padding: 14px 14px 0; }
.wn__what b { display: block; font-family: var(--f-display, "Instrument Serif", Georgia, serif); font-weight: 400; font-size: 1.3rem; line-height: 1.15; overflow-wrap: anywhere; }
.wn__what span { display: block; margin-top: 4px; font-size: .62rem; letter-spacing: .1em; text-transform: uppercase; color: var(--wn-muted); }
.wn textarea.wn__why { display: block; width: calc(100% - 28px); margin: 14px 14px 0; min-height: 76px; resize: none; outline: none; appearance: none; -webkit-appearance: none;
  background: none !important; color: var(--wn-ink); border: 0 !important; border-bottom: 1px solid var(--wn-ink) !important; box-shadow: none !important; padding: 0 0 8px !important;
  font-family: var(--f-mono, "IBM Plex Mono", ui-monospace, Menlo, monospace) !important; font-size: .84rem; line-height: 1.5; }
.wn textarea.wn__why::placeholder { color: var(--wn-muted); opacity: 1; }
.wn__msg { min-height: 1.1em; margin: 8px 14px 0; font-size: .7rem; line-height: 1.45; color: var(--wn-red); }
.wn__foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px 14px; }
.wn__room { font-size: .6rem; letter-spacing: .1em; text-transform: uppercase; color: var(--wn-muted); font-variant-numeric: tabular-nums; }
.wn__go { appearance: none; -webkit-appearance: none; flex: none; background: var(--wn-ink); color: var(--wn-bg); border: 1px solid var(--wn-ink); cursor: pointer;
  font: inherit; font-size: .66rem; letter-spacing: .1em; text-transform: uppercase; padding: 9px 14px; }
.wn__go[disabled] { opacity: .4; cursor: default; }`;
    document.head.appendChild(s);
}

// beside what was pressed, inside the window, and clear of the deck where there is room
function place(anchor) {
    const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: innerWidth / 2 - 170, right: innerWidth / 2 + 170, top: innerHeight / 3, bottom: innerHeight / 3 };
    const w = box.offsetWidth, h = box.offsetHeight;
    const clear = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--snt-clear')) || 0;
    const floor = innerHeight - 8 - (clear && h + 16 < innerHeight - clear ? clear : 0);
    let y = r.bottom + 6;
    if (y + h > floor) y = r.top - h - 6;                   // no room under it: above it
    const roof = (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 0) + 8;
    y = Math.max(Math.min(roof, floor - h), Math.min(y, floor - h));     // never onto the deck, nor over the top bar where it can be helped
    y = Math.max(8, y);
    box.style.left = Math.min(innerWidth - w - 8, Math.max(8, r.left)) + 'px';
    box.style.top = y + 'px';
}

async function save(record, why, found) {
    try {
        const r = await fetch('/api/gr/shop/wish', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ record, why, found: found || '' }) });
        const d = await r.json().catch(() => ({}));
        return Object.assign({ ok: r.ok }, d);
    } catch (_) { return { ok: false, error: 'That could not be saved just now.' }; }
}

function close(result) {
    if (!box) return;
    removeEventListener('pointerdown', onOut, true);
    removeEventListener('keydown', onKey, true);
    removeEventListener('resize', onMove);
    box.remove(); box = null;
    const d = done; done = null;
    if (d) d(result || null);
}
function onOut(e) { if (box && !box.contains(e.target)) close(); }
function onKey(e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); } }
let onMove = () => {};

function open(anchor, o) {
    o = o || {};
    close();
    css();
    const rec = o.record || {};
    box = document.createElement('div');
    box.className = 'wn'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Note it for later');
    box.innerHTML = `
      <div class="wn__h"><span>Note it for later</span><button type="button" class="wn__x" title="Close" aria-label="Close">✕</button></div>
      <div class="wn__what">${o.blind
        ? '<b>The record playing</b><span>You see what it is once it is noted</span>'
        : `<b>${esc(rec.title || 'Untitled')}</b><span>${esc(rec.artist || '')}</span>`}</div>
      <textarea class="wn__why" maxlength="500" placeholder="Why this one?" aria-label="Why this one?"></textarea>
      <div class="wn__msg" aria-live="polite"></div>
      <div class="wn__foot"><span class="wn__room"></span><button type="button" class="wn__go" disabled>Note it</button></div>`;
    document.body.appendChild(box);
    const why = box.querySelector('.wn__why'), go = box.querySelector('.wn__go'), msg = box.querySelector('.wn__msg'), room = box.querySelector('.wn__room');
    if (o.why) why.value = o.why;
    const ready = () => { go.disabled = why.value.trim().length < 2; };
    why.addEventListener('input', () => { msg.textContent = ''; ready(); });
    ready();
    fetch('/api/gr/shop/wishes').then(r => r.json()).then(w => {
        if (box && w && w.max) room.textContent = w.count + ' of ' + w.max + ' on your wishlist';
    }).catch(() => {});
    const submit = async () => {
        const words = why.value.trim();
        if (words.length < 2 || go.dataset.busy) return;
        go.dataset.busy = '1'; go.disabled = true; msg.textContent = '';
        const out = o.save ? await o.save(words) : await save(rec, words, o.found);
        if (!box) return;
        delete go.dataset.busy;
        if (out && out.ok) return close(Object.assign({ why: words }, out));
        msg.textContent = (out && out.error) || 'That could not be saved just now.';
        ready();
    };
    go.addEventListener('click', submit);
    why.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
    box.querySelector('.wn__x').addEventListener('click', () => close());
    onMove = () => { if (box && anchor && document.contains(anchor)) place(anchor); };
    place(anchor);
    setTimeout(() => {                                   // (not on the press that opened it)
        if (!box) return;
        addEventListener('pointerdown', onOut, true);
        addEventListener('keydown', onKey, true);
        addEventListener('resize', onMove);
        try { why.focus({ preventScroll: true }); } catch (_) { why.focus(); }
    }, 0);
    return new Promise(res => { done = res; });
}

return { open, save, close, isOpen: () => !!box };
})();
