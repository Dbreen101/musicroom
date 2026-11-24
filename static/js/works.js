// works.js — a digital artist's works, anywhere in the app (2026-11-24).
//
//   Works.open(id, opts)        one work, large, over the page: what it is, who made it, and
//                               (when it has a price) buying it with credits; once it is yours,
//                               "Save the file" puts the file on this computer and shows it.
//                               opts.openRoom(handle) → the maker's name becomes a way to their room.
//   Works.tile(w)               a work as a tile (a picture, its name, a line) — [data-work]
//   Works.mountBought(host, o)  the works this person has bought (My Room → From the shop)
//   event 'works-changed' on window after a work is bought
//
// Any [data-work="<id>"] on a page that loads this file opens that work when pressed.
// Styles: static/css/works.css (fetched here if the page hasn't it). The rooms server's side
// is gr_art.py; the app's routes are gr_art_app.py (/api/gr/works…).
(function () {
'use strict';
if (window.Works) return;

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cr = n => n + (n === 1 ? ' credit' : ' credits');
const img = (id, size) => `/api/gr/work-img/${id}?size=${size || 'view'}`;
const line = w => [w.year || '', w.medium || ''].filter(Boolean).join(' · ');

if (!document.querySelector('link[href*="/static/css/works.css"]')) {
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/static/css/works.css'; document.head.appendChild(l);
}

function tile(w) {
    const price = w.bought ? 'yours' : (w.for_sale && !w.mine ? cr(w.price) : '');
    return `<a href="#" class="wk-tile" data-work="${w.id}" title="${esc(w.title)}">
        <span class="wk-tile__pic"><img src="${img(w.id, 'thumb')}" alt="" loading="lazy"></span>
        <span class="wk-tile__t">${esc(w.title)}</span>
        <span class="wk-tile__s">${esc([line(w), price].filter(Boolean).join(' · '))}</span></a>`;
}

let box = null, OPTS = {};
function close() {
    if (!box) return;
    box.remove(); box = null;
    document.removeEventListener('keydown', onKey, true);
}
function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); close(); } }

async function open(id, opts) {
    OPTS = opts || OPTS || {};
    close();
    box = document.createElement('div');
    box.className = 'wk-view'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'A work');
    box.innerHTML = `<button type="button" class="wk-x" data-wk="close" aria-label="Close" title="Close">✕</button>
        <div class="wk-stage"><img src="${img(id, 'view')}" alt=""></div><aside class="wk-side"><p class="wk-p">Looking…</p></aside>`;
    document.body.appendChild(box);
    document.addEventListener('keydown', onKey, true);
    box.addEventListener('click', e => {
        const b = e.target.closest('[data-wk]');
        if (!b) { if (e.target === box || e.target.classList.contains('wk-stage')) close(); return; }
        e.preventDefault();
        const act = b.dataset.wk;
        if (act === 'close') close();
        else if (act === 'buy') buy(id, b);
        else if (act === 'save') save(id, b);
        else if (act === 'link') fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: b.dataset.url }) });
        else if (act === 'room') { const h = b.dataset.handle; close(); if (OPTS.openRoom) OPTS.openRoom(h); else location.href = '/rooms/' + encodeURIComponent(h); }
    });
    paint(id);
}

async function paint(id) {
    let w = null, err = '';
    try { const r = await fetch('/api/gr/works/' + id); w = await r.json(); if (!r.ok) { err = w.error || 'That work can’t be opened.'; w = null; } }
    catch (_) { err = 'The Music Room can’t be reached right now.'; }
    if (!box) return;
    const side = box.querySelector('.wk-side');
    if (!w) { side.innerHTML = `<p class="wk-p">${esc(err)}</p>`; return; }
    let act = '';
    if (w.mine) act = '';
    else if (w.bought) act = `<p class="wk-state">Yours</p><button type="button" class="wk-btn" data-wk="save">Save the file</button>`;
    else if (w.for_sale && w.selling) act = `<button type="button" class="wk-btn wk-btn--main" data-wk="buy" data-price="${w.price}">Buy · ${w.price}</button>
        <p class="wk-small">You have ${cr(w.credits || 0)}.</p>`;
    side.innerHTML = `
        <h2 class="wk-t">${esc(w.title)}</h2>
        ${w.by ? `<a href="#" class="wk-by" data-wk="room" data-handle="${esc(w.by.handle)}">${esc(w.by.name)}</a>` : ''}
        ${line(w) ? `<p class="wk-meta">${esc(line(w))}</p>` : ''}
        ${w.width && w.height ? `<p class="wk-meta">${w.width} × ${w.height}</p>` : ''}
        ${w.note ? `<p class="wk-note">${esc(w.note).replace(/\n/g, '<br>')}</p>` : ''}
        ${w.url ? `<p><a href="#" class="wk-link" data-wk="link" data-url="${esc(w.url)}">Open its link ↗</a></p>` : ''}
        <div class="wk-acts">${act}</div><p class="wk-say" aria-live="polite"></p>`;
}

async function buy(id, btn) {
    const price = +btn.dataset.price;
    if (!confirm(`Buy this work for ${cr(price)}? You get the file.`)) return;
    btn.disabled = true;
    const say = box && box.querySelector('.wk-say');
    let d = {}, ok = false;
    try { const r = await fetch(`/api/gr/works/${id}/buy`, { method: 'POST' }); d = await r.json(); ok = r.ok; } catch (_) { d = { error: 'The Music Room can’t be reached right now.' }; }
    if (!ok) { btn.disabled = false; if (say) say.textContent = d.error || 'That didn’t go through.'; return; }
    if (window.SimShop) SimShop.me(true);
    window.dispatchEvent(new CustomEvent('works-changed', { detail: { id } }));
    paint(id);
}

async function save(id, btn) {
    const say = (btn.closest('.wk-side, .wk-mine__row') || document).querySelector('.wk-say');
    btn.disabled = true;
    let d = {}, ok = false;
    try { const r = await fetch(`/api/gr/works/${id}/save`, { method: 'POST' }); d = await r.json(); ok = r.ok; } catch (_) { d = { error: 'That was interrupted. Try again.' }; }
    btn.disabled = false;
    if (say) say.textContent = ok ? `Saved as “${d.name}”.` : (d.error || 'It couldn’t be saved.');
}

// what this person has bought: a row each — picture, name, who made it, Save the file
function mountBought(host, opts) {
    opts = opts || {};
    const load = async () => {
        let works = [];
        try { const r = await fetch('/api/gr/works/bought'); if (r.ok) works = (await r.json()).works || []; } catch (_) {}
        if (!works.length) { host.innerHTML = ''; return; }
        host.innerHTML = `<div class="wk-mine"><h2 class="wk-mine__h">Art</h2>${works.map(w => `<div class="wk-mine__row">
            <a href="#" class="wk-mine__pic" data-work="${w.id}"><img src="${img(w.id, 'thumb')}" alt="" loading="lazy"></a>
            <div class="wk-mine__body"><div class="wk-mine__t">${esc(w.title)}</div>
              <div class="wk-mine__s">${esc([w.by && w.by.name, line(w)].filter(Boolean).join(' · '))}</div>
              <div class="wk-mine__acts"><button type="button" class="wk-btn" data-wk-save="${w.id}">Save the file</button>
                ${w.by && w.by.handle ? `<a class="wk-btn wk-btn--quiet" href="/rooms/${encodeURIComponent(w.by.handle)}?overlay=1" data-room="${esc(w.by.handle)}">${esc(w.by.name)}’s room ↗</a>` : ''}</div>
              <p class="wk-say" aria-live="polite"></p></div></div>`).join('')}</div>`;
        host.querySelectorAll('[data-wk-save]').forEach(b => b.addEventListener('click', () => save(+b.dataset.wkSave, b)));
        if (opts.openPage) host.querySelectorAll('[data-room]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); opts.openPage(a.getAttribute('href')); }));
    };
    const onChange = () => load();
    window.addEventListener('works-changed', onChange);
    load();
    return { refresh: load, destroy() { window.removeEventListener('works-changed', onChange); host.innerHTML = ''; } };
}

document.addEventListener('click', e => {
    const a = e.target.closest('[data-work]');
    if (!a) return;
    e.preventDefault();
    open(+a.dataset.work);
});

window.Works = { open, close, tile, mountBought, img, setOptions(o) { OPTS = o || {}; } };
})();
