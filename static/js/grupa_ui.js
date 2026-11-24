// =============================================================
// grupa_ui.js — the grúpa's face, wherever it shows.
//
// A grúpa is a playlist that holds anything: records from your room, labels,
// artists, places, sets, Spotify / SoundCloud links, other music rooms, any
// link, another grúpa. ONE piece of UI, two homes:
//   · the Grúpa page (/grupa, templates/grupa.html)
//   · the Grúpa view inside My Room (templates/room3d.html, beside Cloud ·
//     Grid · Blocks) — so grúpa live in the room with your own records.
// Both get the same thing: every grúpa as a card (its cover is its name in
// type, or a picture from something in it) — make a new one there, give them
// a shared look, select several to make them public or private or delete them
// — and, opened, one grúpa: name and description edited in place, its cover,
// its "public" switch, one line that takes a pasted link or a search (your
// records, labels, artists, sets, music rooms, and Spotify when it's
// connected), a note on every element, drag to reorder, play the lot as one cue.
//
//   GrupaUI.mount(host, { gid, inRoom, openTrack(id), openPage(href), onOpen(id) })
//   GrupaUI.coverHtml(g)                     — a grúpa's cover, to put in any square box
//   GrupaUI.pick(anchor, { title, has })     → Promise<{add:[{id,name}], remove:[…]} | null>
//   GrupaUI.addTo(thing, anchor)             — the "add to a grúpa" window, then do it:
//        {kind:'track', ref_id} · {url, title?, subtitle?, image?} · {kind:'room', ref_key, title?} · {tracks:[ids]}
//   GrupaUI.publicPanel(host, id, opts)      — someone's public grúpa, to read and play
//
// The words are functional; Daithí coins the real ones.
// =============================================================
window.GrupaUI = (function () {
'use strict';

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hostOf = u => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (_) { return ''; } };
const isLink = s => /^(https?:\/\/|spotify:|www\.)\S+$/i.test(s) || /^[\w-]+(\.[\w-]+)+\/\S*$/.test(s);
const grow = el => { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; };
const KIND = { track: 'Record', label: 'Label', artist: 'Artist', place: 'Place', set: 'Set', room: 'Music room', grupa: 'Grúpa', stream: 'Stream', link: 'Link' };
const AI_WHY = { list: 'Its artist is on a public list of accounts that release AI-made music (eye-wave/spotify-ai-blocklist).', mine: 'You marked this as AI-made.' };

async function call(url, method, body) {
    const r = await fetch(url, { method: method || 'GET', headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.hint || d.error || 'that did not work');
    return d;
}
const openUrl = url => fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) }).catch(() => {});
const changed = id => window.dispatchEvent(new CustomEvent('grupa-changed', { detail: { id } }));
const track = (kind, data) => { try { if (window.grTrack) window.grTrack(kind, data || {}); } catch (_) {} };

// links out of whatever was dropped or pasted
function linksIn(dt) {
    let raw = '';
    try { raw = dt.getData('text/uri-list') || dt.getData('text/plain') || ''; } catch (_) {}
    return [...new Set(raw.split(/[\s\n]+/).map(s => s.trim()).filter(s => s && s[0] !== '#' && /^(https?:\/\/|spotify:)/i.test(s)))];
}

// ───────────────────────── a grúpa's cover ─────────────────────────
// Its name set in type on a ground of colour (the look all grúpaí share, or
// its own), or a picture from something in it. The server has already worked
// out which (g.cover — see grupa.py cover_of); this only draws it, to fill
// whatever square box it is put in. The words size themselves to the box.
function coverHtml(g) {
    const c = (g && g.cover) || {};
    const name = ((g && g.name) || 'Untitled').trim() || 'Untitled', L = name.length;
    const size = L <= 5 ? 'xl' : L <= 10 ? 'l' : L <= 22 ? 'm' : L <= 44 ? 's' : 'xs';
    const css = [c.bg ? 'background:' + c.bg : '', c.ink ? 'color:' + c.ink : '', c.font ? "font-family:'" + String(c.font).replace(/[^\w ]/g, '') + "', Georgia, serif" : ''].filter(Boolean).join(';');
    // the words are always there; a picture, when there is one, lies over them (and leaves them showing if it can't load)
    return `<span class="gp-cv gp-cv--${size}" style="${esc(css)}"><span>${esc(name)}</span></span>`
        + (c.kind === 'image' && c.image ? `<img class="gp-cvimg" src="${esc(c.image)}" alt="" loading="lazy" onerror="this.remove()">` : '');
}

// ───────────────────────── the window: "add to a grúpa" ─────────────────────────
// It works the way adding to a playlist does in Spotify (Daithí, 2026-11-15):
// a small window with every grúpa and a box to tick beside each — tick as many
// as you like; the ones the thing is already in come ticked, and unticking one
// takes it out — a line to find one by name, "New grúpa" at the top (name it and
// the thing goes straight in), and Done.
//   pick(anchor, { title, has: 'track=12' | 'url=…' | 'room=…' })
//     → Promise<{ add: [{id, name}], remove: [{id, name}] } | null>
let pickEl = null, pickOff = null;
function closePick() {
    if (pickOff) { pickOff(); pickOff = null; }
    if (pickEl) { pickEl.remove(); pickEl = null; }
}
// anchor: an element · {x, y} · or {el, clear} = line up with `el` but keep
// clear of `clear` (the deck's key lines the picker up; the whole deck is
// what it mustn't cover)
function placeNear(el, anchor) {
    const w = el.offsetWidth, h = el.offsetHeight;
    let x, y;
    const at = anchor && anchor.el ? anchor.el : anchor;
    if (at && at.getBoundingClientRect) {
        const r = at.getBoundingClientRect();
        const c = (anchor.clear && anchor.clear.getBoundingClientRect) ? anchor.clear.getBoundingClientRect() : r;
        x = r.left;
        // above the thing when it sits low on the page, under it when it sits high — wherever there is more room
        y = (c.top + c.height / 2 > innerHeight / 2) ? c.top - h - 8 : c.bottom + 8;
    } else {
        x = (anchor && anchor.x) || innerWidth / 2 - w / 2;
        y = (anchor && anchor.y) || innerHeight / 2 - h / 2;
    }
    el.style.left = Math.max(8, Math.min(innerWidth - w - 8, x)) + 'px';
    el.style.top = Math.max(8, Math.min(innerHeight - h - 8, y)) + 'px';
}
function pick(anchor, o) {
    o = o || {};
    return new Promise((resolve) => {
        closePick();
        const el = pickEl = document.createElement('div');
        el.className = 'gp-pick';
        el.innerHTML = `<div class="gp-pick__h"><span>${esc(o.title || 'Add to a grúpa')}</span><button type="button" class="gp-pick__x" data-p="cancel" title="Close" aria-label="Close">✕</button></div>
            <input class="gp-pick__q" placeholder="Find a grúpa" autocomplete="off" spellcheck="false">
            <button type="button" class="gp-pick__newrow" data-p="new"><span class="gp-pick__plus">＋</span><span>New grúpa</span></button>
            <form class="gp-pick__new" hidden><input placeholder="Name the new grúpa" maxlength="200" autocomplete="off"><button type="submit">Make it</button></form>
            <div class="gp-pick__list"><div class="gp-pick__wait">…</div></div>
            <div class="gp-pick__foot"><span class="gp-pick__say"></span><button type="button" class="gp-pick__done" data-p="done">Done</button></div>`;
        document.body.appendChild(el);
        placeNear(el, anchor);
        let all = [];
        const was = new Set(), now = new Set();         // the ones it was in · the ones ticked now
        const list = el.querySelector('.gp-pick__list'), q = el.querySelector('.gp-pick__q');
        const sayEl = el.querySelector('.gp-pick__say'), form = el.querySelector('.gp-pick__new');
        const result = extra => {
            const by = id => all.find(g => g.id === id) || { id, name: '' };
            const add = [...now].filter(id => !was.has(id)).map(by).map(g => ({ id: g.id, name: g.name }));
            const remove = [...was].filter(id => !now.has(id)).map(by).map(g => ({ id: g.id, name: g.name }));
            if (extra) add.push(extra);
            return { add, remove };
        };
        const done = v => { closePick(); resolve(v); };
        const onDown = e => { if (!el.contains(e.target)) { const r = result(); done(r.add.length || r.remove.length ? r : null); } };   // clicking away keeps what was ticked
        const onKey = e => {
            if (e.key === 'Escape') { e.stopPropagation(); done(null); }
            else if (e.key === 'Enter' && e.target === q) { e.preventDefault(); done(result()); }
        };
        setTimeout(() => document.addEventListener('pointerdown', onDown, true), 0);
        document.addEventListener('keydown', onKey, true);
        pickOff = () => { document.removeEventListener('pointerdown', onDown, true); document.removeEventListener('keydown', onKey, true); };
        function tell() {
            const r = result(), bits = [];
            if (r.add.length) bits.push('into ' + r.add.length);
            if (r.remove.length) bits.push('out of ' + r.remove.length);
            sayEl.textContent = bits.join(' · ');
        }
        function draw() {
            const fold = s => String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/ø/g, 'o').replace(/ß/g, 'ss').replace(/ł/g, 'l').replace(/[đð]/g, 'd').replace(/æ/g, 'ae').replace(/œ/g, 'oe');      // "roisin" finds Róisín
            const f = fold(q.value.trim());
            const rows = all.filter(g => !f || fold(g.name).includes(f));
            list.innerHTML = rows.length ? rows.map(g => `<button type="button" class="gp-pick__row${now.has(g.id) ? ' on' : ''}" role="checkbox" aria-checked="${now.has(g.id)}" data-id="${g.id}">
                    <span class="gp-pick__box" aria-hidden="true"></span><span class="gp-pick__cov">${coverHtml(g)}</span>
                    <span class="gp-pick__n">${esc(g.name)}</span><i>${g.count}</i></button>`).join('')
                : `<div class="gp-pick__wait">${all.length ? 'No grúpa by that name.' : 'None yet.'}</div>`;
            placeNear(el, anchor);
        }
        call('/api/grupa' + (o.has ? '?' + o.has : '')).then(d => {
            if (pickEl !== el) return;
            all = d.grupa || [];
            all.forEach(g => { if (g.has) { was.add(g.id); now.add(g.id); } });
            draw();
            if (!('ontouchstart' in window)) q.focus({ preventScroll: true });
        }).catch(() => { list.innerHTML = '<div class="gp-pick__wait">could not load</div>'; });
        q.oninput = draw;
        list.onclick = e => {
            const b = e.target.closest('.gp-pick__row'); if (!b) return;
            const id = parseInt(b.dataset.id, 10);
            now.has(id) ? now.delete(id) : now.add(id);
            b.classList.toggle('on', now.has(id)); b.setAttribute('aria-checked', now.has(id));
            tell();
        };
        el.onclick = e => {
            const b = e.target.closest('[data-p]'); if (!b) return;
            if (b.dataset.p === 'cancel') done(null);
            else if (b.dataset.p === 'done') done(result());
            else if (b.dataset.p === 'new') { b.hidden = true; form.hidden = false; form.querySelector('input').focus(); placeNear(el, anchor); }
        };
        form.onsubmit = async e => {
            e.preventDefault();
            const name = form.querySelector('input').value.trim(); if (!name) return;
            form.querySelector('button').disabled = true;
            // a new grúpa: made, and the thing goes straight into it (with any others ticked)
            try { const r = await call('/api/grupa', 'POST', { name }); track('grupa_new', {}); done(result({ id: r.id, name, created: true })); }
            catch (err) { sayEl.textContent = err.message; form.querySelector('button').disabled = false; }
        };
    });
}

// a short word that appears by the thing you pressed, then goes
function say(anchor, msg, bad) {
    const el = document.createElement('div');
    el.className = 'gp-say' + (bad ? ' bad' : '');
    el.textContent = msg;
    document.body.appendChild(el);
    placeNear(el, anchor);
    setTimeout(() => el.classList.add('go'), 2200);
    setTimeout(() => el.remove(), 2700);
}

async function addTo(thing, anchor) {
    if (!thing) return null;
    const many = Array.isArray(thing.tracks);
    const has = many ? '' : thing.kind === 'track' && thing.ref_id ? 'track=' + thing.ref_id
        : thing.kind === 'room' && thing.ref_key ? 'room=' + encodeURIComponent(thing.ref_key)
        : thing.url ? 'url=' + encodeURIComponent(thing.url) : '';
    const r = await pick(anchor, { has, title: many ? `Add ${thing.tracks.length} record${thing.tracks.length === 1 ? '' : 's'} to a grúpa` : 'Add to a grúpa' });
    if (!r || (!r.add.length && !r.remove.length)) return null;
    let added = 0, already = 0, out = 0, bad = '';
    for (const g of r.add) {
        try {
            if (many) { const d = await call(`/api/grupa/${g.id}/tracks`, 'POST', { ids: thing.tracks }); added += d.added ? 1 : 0; already += d.added ? 0 : 1; }
            else { const d = await call(`/api/grupa/${g.id}/items`, 'POST', Object.assign({ once: true }, thing)); d.already ? already++ : added++; }
            changed(g.id);
        } catch (e) { bad = e.message; }
    }
    for (const g of r.remove) {
        try { await call(`/api/grupa/${g.id}/remove`, 'POST', thing); out++; changed(g.id); } catch (e) { bad = e.message; }
    }
    const names = list => list.length === 1 ? list[0].name : list.length + ' grúpaí';
    const bits = [];
    if (added) bits.push('Added to ' + names(r.add));
    else if (already && !out) bits.push('Already in ' + names(r.add));
    if (out) bits.push('Taken out of ' + names(r.remove));
    say(anchor, bad || bits.join(' · ') || 'Done', !!bad);
    return r;
}

// Play: the whole grúpa goes to the deck as ONE cue — owned records and
// streamed ones together, in order. With an item: start from that row. cueOnly
// adds (that element, or everything) to the end of the cue instead.
async function playGrupa(gid, itemId, cueOnly) {
    const deck = window.Seinnteoir; if (!deck || !gid) return;
    if (cueOnly) {
        const d = await call(`/api/grupa/${gid}/queue` + (itemId ? `?item=${itemId}` : ''));
        if (d.items.length) deck.add(d.items);
        return d.items.length;
    }
    const d = await call(`/api/grupa/${gid}/queue`);
    if (!d.items.length) return 0;
    const start = itemId ? (d.starts[String(itemId)] || 0) : 0;
    // cue it silently, then start at the right row: the deck drops records
    // whose files can't be found (a drive not plugged in), so the row's place
    // in the cue is found by walking the two lists together
    await call('/api/seinnteoir/queue', 'POST', { items: d.items, idx: 0, autoplay: false });
    const q = (await call('/api/seinnteoir/state')).queue || [];
    const same = (a, b) => a.kind === 'embed' ? (b.kind === 'embed' && b.url === a.url) : (b.file_id === a.file_id);
    let idx = 0, j = 0;
    for (let i = 0; i < d.items.length && j < q.length; i++) {
        if (!same(d.items[i], q[j])) continue;
        if (i >= start) { idx = j; break; }
        j++;
    }
    if (!q.length) return 0;
    await call('/api/seinnteoir/play_at', 'POST', { idx });
    track('grupa_play', { n: q.length });
    return q.length;
}

// the small print under an element's name (shared by the surface and the panel)
function metaLine(it) {
    const bits = [];
    if (it.kind === 'stream') { if (it.subtitle) bits.push(esc(it.subtitle)); bits.push(esc(it.service + (it.stream_type && it.stream_type !== 'track' ? ' ' + it.stream_type : ''))); }
    else if (it.kind === 'track') { if (it.subtitle) bits.push(esc(it.subtitle)); if (it.borrowed) bits.push('borrowed'); }
    else if (it.kind === 'link') { if (it.subtitle) bits.push(esc(it.subtitle)); bits.push(esc(hostOf(it.url))); }
    else { bits.push(esc(it.subtitle || KIND[it.kind])); if (it.count != null) bits.push(it.count + (it.kind === 'grupa' ? ' in it' : (it.count === 1 ? ' record in your room' : ' records in your room'))); }
    if (it.gone) bits.push('<span class="gone">no longer here</span>');
    if (it.ai) bits.push(`<span class="gp-ai" title="${esc(AI_WHY[it.ai] || '')}">AI-made · not played here</span>`);
    return bits.filter(Boolean).join(' · ');
}

// ───────────────────────── a grúpa's panel ─────────────────────────
// Where a record's panel would be when the thing met in the room is a grúpa:
// what it is, what's in it (with the notes on why), play it or add it to the
// cue. Read-only — "Open" goes to where it can be changed.
//   GrupaUI.panel(host, gid, { openTrack(id), openPage(href), onEdit(gid), onGone() }) → { destroy }
function panel(host, gid, opts) {
    opts = opts || {};
    let alive = true;
    host.classList.add('gp', 'gp-panel');
    host.innerHTML = '<div class="gp-empty">…</div>';
    const go = opts.openPage || (href => { location.href = href; });
    async function draw() {
        let d;
        try { d = await call('/api/grupa/' + gid); }
        catch (_) { if (alive && opts.onGone) opts.onGone(); return; }
        if (!alive) return;
        const G = d.grupa, items = d.items, anyPlay = items.some(i => i.playable);
        host.innerHTML = `
            <div class="gp-panel__k">Grúpa</div>
            <h2 class="gp-name">${esc(G.name)}</h2>
            ${G.description ? `<p class="gp-panel__d">${esc(G.description)}</p>` : ''}
            <div class="gp-bar">
                <button class="gp-btn gp-btn--primary" data-do="play"${anyPlay ? '' : ' disabled'}>Play</button>
                <button class="gp-btn" data-do="cue" data-snt-keep${anyPlay ? '' : ' disabled'}>Add to the cue</button>
                <span class="gp-bar__count">${items.length ? items.length + ' in it' : ''}</span>
                ${opts.onEdit ? '<button class="gp-btn gp-btn--small" data-do="edit" title="Open it in Grúpaí to add to it or change it">Open</button>' : ''}
            </div>
            <div class="gp-items gp-items--read">${items.length ? items.map((it, i) => `
                <div class="gp-item${it.ai ? ' gp-item--ai' : ''}" data-id="${it.id}">
                    <span class="gp-n">${String(i + 1).padStart(2, '0')}</span>
                    <div class="gp-cov"><span>${esc((it.title || '·').trim().charAt(0).toUpperCase())}</span>${it.image ? `<img src="${esc(it.image)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</div>
                    <div class="gp-main">
                        ${(!it.gone && it.kind !== 'label' && it.kind !== 'artist') ? `<button type="button" class="gp-t" data-act="open">${esc(it.title || 'Untitled')}</button>` : `<span class="gp-t">${esc(it.title || 'Untitled')}</span>`}
                        <div class="gp-s">${metaLine(it)}</div>
                        ${it.note ? `<div class="gp-note gp-note--read">${esc(it.note)}</div>` : ''}
                    </div>
                    <div class="gp-acts">${it.playable ? `<button class="gp-act" data-act="play" title="Play from here">▶</button><button class="gp-act" data-act="cue" data-snt-keep title="Add to the cue">＋</button>` : ''}</div>
                </div>`).join('') : '<div class="gp-empty">Nothing in it yet.</div>'}</div>`;
        host.onclick = e => {
            const b = e.target.closest('[data-do]');
            if (b) {
                if (b.dataset.do === 'play') playGrupa(gid, null, false);
                else if (b.dataset.do === 'cue') playGrupa(gid, null, true).then(n => { if (n) say(b, n + ' added to the cue'); });
                else if (b.dataset.do === 'edit' && opts.onEdit) opts.onEdit(gid);
                return;
            }
            const a = e.target.closest('[data-act]'); if (!a) return;
            const id = parseInt(a.closest('.gp-item').dataset.id, 10), it = items.find(x => x.id === id);
            if (a.dataset.act === 'play') playGrupa(gid, id, false);
            else if (a.dataset.act === 'cue') playGrupa(gid, id, true);
            else if (a.dataset.act === 'open') {
                if (it.kind === 'track') { if (opts.openTrack) { try { opts.openTrack(it.ref_id); return; } catch (_) {} } go('/room?track=' + it.ref_id); }
                else if (it.kind === 'grupa') { gid = it.ref_id; draw(); }
                else if (it.kind === 'set') go('/set/' + it.ref_id);
                else if (it.kind === 'room') go('/rooms/' + encodeURIComponent(it.ref_key) + '?overlay=1');
                else if (it.url) openUrl(it.url);
            }
        };
    }
    const onChanged = e => { if (e.detail && e.detail.id === gid) draw(); };
    window.addEventListener('grupa-changed', onChanged);
    draw();
    return { destroy() { alive = false; window.removeEventListener('grupa-changed', onChanged); host.onclick = null; host.innerHTML = ''; } };
}

// ───────────────────────── someone's public grúpa ─────────────────────────
// Found in Explore, or on its owner's public room: what it is, who made it,
// what is in it with their notes — and, beside each thing, where it can be
// heard. A stream plays through your own deck. A record that lives on the
// rooms server points to the room it can be borrowed or bought in (and plays
// if you already hold it). A file that exists only on its owner's laptop says
// so, with a way to go looking for it. Read-only: it is theirs.
//   GrupaUI.publicPanel(host, id, { openRoom(handle), openTrack(id), onGone() }) → { destroy }
const bandcampSearch = it => 'https://bandcamp.com/search?q=' + encodeURIComponent([it.subtitle, it.title].filter(Boolean).join(' '));
async function playPublic(id, n, cueOnly) {
    const deck = window.Seinnteoir; if (!deck) return 0;
    if (cueOnly) {
        const d = await call(`/api/gr/grupai/${id}/queue` + (n != null ? '?item=' + n : ''));
        if (d.items.length) deck.add(d.items);
        return d.items.length;
    }
    const d = await call(`/api/gr/grupai/${id}/queue`);
    if (!d.items.length) return 0;
    await call('/api/seinnteoir/queue', 'POST', { items: d.items, idx: 0, autoplay: false });
    const q = (await call('/api/seinnteoir/state')).queue || [];
    if (!q.length) return 0;
    // the deck leaves out what it can't find; walk the two lists together to the row asked for
    const start = n != null ? (d.starts[String(n)] || 0) : 0;
    const same = (a, b) => a.kind === 'embed' ? (b.kind === 'embed' && b.url === a.url) : (b.file_id === a.file_id);
    let idx = 0, j = 0;
    for (let i = 0; i < d.items.length && j < q.length; i++) {
        if (!same(d.items[i], q[j])) continue;
        if (i >= start) { idx = j; break; }
        j++;
    }
    await call('/api/seinnteoir/play_at', 'POST', { idx });
    track('grupa_public_play', { n: q.length });
    return q.length;
}
function publicPanel(host, id, opts) {
    opts = opts || {};
    let alive = true;
    host.classList.add('gp', 'gp-panel', 'gp-public');
    host.innerHTML = '<div class="gp-empty">…</div>';
    const openRoom = opts.openRoom || (h => { location.href = '/rooms/' + encodeURIComponent(h); });
    // where a thing can be heard, in a few plain words (and what the row offers because of it)
    const poss = n => n + (/s$/i.test(n) ? '’' : '’s');          // Moss Records’ · Sandy’s
    function where(it, owner) {
        const who = owner || 'its owner', whose = owner ? poss(owner) : 'its owner’s';
        if (it.where === 'stream') return { cls: '', line: esc((it.service || it.source || '') + (it.stream_type && it.stream_type !== 'track' ? ' ' + it.stream_type : '')) + (it.ai ? ' · <span class="gp-ai">AI-made · not played here</span>' : '') };
        if (it.where === 'campus') {
            if (it.mine) return { cls: '', line: 'in your room' };
            if (it.room) return { cls: 'gp-item--away', line: `<button type="button" class="gp-where" data-act="room">in ${esc(poss(it.room.name))} music room →</button>` };
            return { cls: 'gp-item--away', line: 'on the rooms server' };
        }
        if (it.where === 'own') return { cls: 'gp-item--away gp-item--only', line: `<span class="gp-only">${esc(whose)} own work · only on their laptop</span>` };
        if (it.where === 'local') return { cls: 'gp-item--away gp-item--only', line: `<span class="gp-only">only on ${esc(whose)} laptop</span> · <button type="button" class="gp-where" data-act="bandcamp">look for it on Bandcamp ↗</button>` };
        if (it.where === 'room') return { cls: '', line: `<button type="button" class="gp-where" data-act="room">music room →</button>` };
        if (it.where === 'link') return { cls: '', line: esc(hostOf(it.url)) };
        return { cls: 'gp-item--away', line: esc(KIND[it.kind] || '') + (it.count != null ? ` · ${it.count} in ${esc(whose)} room` : '') };
    }
    async function draw() {
        let G;
        try { G = await call('/api/gr/grupai/' + id); }
        catch (err) { if (!alive) return; host.innerHTML = `<div class="gp-empty">${esc(err.message)}</div>`; if (opts.onGone) opts.onGone(err); return; }
        if (!alive) return;
        const items = G.items || [], canPlay = items.filter(i => i.playable).length, owner = (G.owner && G.owner.name) || '';
        host.innerHTML = `
            <div class="gp-panel__k">Grúpa${owner ? ' · by ' + (G.owner.handle ? `<button type="button" class="gp-where" data-do="owner">${esc(owner)}</button>` : esc(owner)) : ''}${G.mine ? ' · yours, as others see it' : ''}</div>
            <div class="gp-pubhead"><div class="gp-pubhead__cover">${coverHtml(G)}</div>
                <div class="gp-pubhead__main"><h2 class="gp-name">${esc(G.name)}</h2>${G.description ? `<p class="gp-panel__d">${esc(G.description)}</p>` : ''}</div></div>
            <div class="gp-bar">
                <button class="gp-btn gp-btn--primary" data-do="play"${canPlay ? '' : ' disabled'}>Play</button>
                <button class="gp-btn" data-do="cue" data-snt-keep${canPlay ? '' : ' disabled'}>Add to the cue</button>
                <span class="gp-bar__count">${items.length} in it${items.length && canPlay < items.length ? ` · ${canPlay} can be played here` : ''}</span>
                ${!G.mine && window.MRReport ? `<button class="gp-btn gp-btn--quiet" data-do="report" title="Tell the Music Room something is wrong with this grúpa">Report</button>` : ''}
            </div>
            ${G.hidden ? `<p class="gp-panel__d" style="color:var(--red)">The Music Room has taken this grúpa down${G.hidden.note ? ': ' + esc(G.hidden.note) : ''}. Only you can see it.</p>` : ''}
            <div class="gp-items gp-items--read">${items.length ? items.map((it, i) => { const w = where(it, owner); return `
                <div class="gp-item ${w.cls}${it.ai ? ' gp-item--ai' : ''}" data-n="${i}">
                    <span class="gp-n">${String(i + 1).padStart(2, '0')}</span>
                    <div class="gp-cov"><span>${esc((it.title || '·').trim().charAt(0).toUpperCase())}</span>${it.image ? `<img src="${esc(it.image)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</div>
                    <div class="gp-main">
                        <span class="gp-t">${esc(it.title || 'Untitled')}</span>
                        <div class="gp-s">${[it.subtitle ? esc(it.subtitle) : '', w.line].filter(Boolean).join(' · ')}</div>
                        ${it.note ? `<div class="gp-note gp-note--read">${esc(it.note)}</div>` : ''}
                    </div>
                    <div class="gp-acts">
                        ${it.playable ? `<button class="gp-act" data-act="play" title="Play from here">▶</button><button class="gp-act" data-act="cue" data-snt-keep title="Add to the cue">＋</button>` : ''}
                        ${it.url ? `<button class="gp-act" data-act="out" title="Open on ${esc(it.service || hostOf(it.url))}">↗</button>` : ''}
                        ${(it.url || (it.where === 'room' && it.handle)) ? `<button class="gp-act gp-act--word" data-act="keep" title="Add this to one of your own grúpaí">＋ grúpa</button>` : ''}
                    </div>
                </div>`; }).join('') : '<div class="gp-empty">Nothing in it yet.</div>'}</div>`;
        host.onclick = e => {
            const b = e.target.closest('[data-do]');
            if (b) {
                if (b.dataset.do === 'play') playPublic(id, null, false);
                else if (b.dataset.do === 'cue') playPublic(id, null, true).then(n => { if (n) say(b, n + ' added to the cue'); });
                else if (b.dataset.do === 'owner' && G.owner.handle) openRoom(G.owner.handle);
                else if (b.dataset.do === 'report' && window.MRReport) MRReport.open({ what: 'grupa', ref: G.id, title: G.name }, b);
                return;
            }
            const a = e.target.closest('[data-act]'); if (!a) return;
            const n = parseInt(a.closest('.gp-item').dataset.n, 10), it = items[n], act = a.dataset.act;
            if (act === 'play') playPublic(id, n, false);
            else if (act === 'cue') playPublic(id, n, true);
            else if (act === 'out') openUrl(it.url);
            else if (act === 'bandcamp') openUrl(bandcampSearch(it));
            else if (act === 'room') openRoom(it.room ? it.room.handle : it.handle);
            else if (act === 'keep') addTo(it.url ? { url: it.url, title: it.title, subtitle: it.subtitle, image: /^https?:/.test(it.image || '') ? it.image : '', by_ids: it.by_ids, duration_sec: it.duration_sec }
                                                  : { kind: 'room', ref_key: it.handle, title: it.title }, a);
        };
    }
    draw();
    return { destroy() { alive = false; host.onclick = null; host.innerHTML = ''; host.classList.remove('gp', 'gp-panel', 'gp-public'); } };
}

// ───────────────────────── the grúpa surface ─────────────────────────
function mount(host, opts) {
    opts = opts || {};
    const go = opts.openPage || (href => { location.href = href; });
    let LIST = [], LOOK = { font: '', bg: '' }, FONTS = [], SWATCHES = [];
    let G = null, ITEMS = [], OWN = null, CHOICES = [], gid = 0, SP = null, alive = true, nowT = null, sortable = null, dragging = false, nowUrl = '';
    let selecting = false, lookOpen = false, coverOpen = false;
    const sel = new Set();                       // the grúpaí ticked while selecting

    host.classList.add('gp');
    host.innerHTML = `
        <section class="gp-home">
            <header class="gp-home__head">
                <h1 class="gp-name gp-name--home">Grúpaí</h1>
                <span class="gp-home__n"></span>
                <span class="gp-home__sp"></span>
                <button type="button" class="gp-btn gp-btn--small" data-home="look" title="The cover every grúpa wears until it is given its own: its name, in a typeface and on a colour you choose">The shared look</button>
                <button type="button" class="gp-btn gp-btn--small" data-home="select" title="Choose several, then make them public or private, or delete them, all at once">Select</button>
            </header>
            <form class="gp-new"><input class="gp-input" placeholder="Name a new grúpa" autocomplete="off" maxlength="200"><button class="gp-btn gp-btn--primary" type="submit">Make it</button></form>
            <div class="gp-lookbox" hidden></div>
            <div class="gp-selbar" hidden></div>
            <div class="gp-cards"></div>
        </section>
        <section class="gp-one" hidden>
            <button type="button" class="gp-back" data-one="back">← All grúpaí</button>
            <div class="gp-open"></div>
        </section>`;
    const $ = (sel, root) => (root || host).querySelector(sel);
    const homeEl = $('.gp-home'), oneEl = $('.gp-one'), cards = $('.gp-cards'), pane = $('.gp-open');
    const lookBox = $('.gp-lookbox'), selBar = $('.gp-selbar');

    $('.gp-new').onsubmit = async e => {
        e.preventDefault();
        const inp = $('.gp-new input'), name = inp.value.trim(); if (!name) return;
        const d = await call('/api/grupa', 'POST', { name });
        inp.value = ''; track('grupa_new', {});
        await loadList(); await open(d.id);
        const q = $('.gp-q'); if (q) q.focus();
    };

    async function loadList() {
        try {
            const d = await call('/api/grupa');
            LIST = d.grupa || []; LOOK = d.look || LOOK; FONTS = d.fonts || FONTS; SWATCHES = d.swatches || SWATCHES;
        } catch (_) { LIST = []; }
        for (const id of [...sel]) if (!LIST.some(g => g.id === id)) sel.delete(id);
        drawCards();
    }

    // ── home: every grúpa as a card ──
    function drawCards() {
        $('.gp-home__n').textContent = LIST.length ? String(LIST.length) : '';
        $('[data-home=select]').hidden = !LIST.length;
        $('[data-home=look]').hidden = !LIST.length;
        homeEl.classList.toggle('gp-home--selecting', selecting);
        $('[data-home=select]').textContent = selecting ? 'Done' : 'Select';
        $('[data-home=select]').classList.toggle('gp-btn--primary', selecting);
        cards.innerHTML = LIST.length ? LIST.map(g => `
            <div class="gp-card${sel.has(g.id) ? ' sel' : ''}" data-id="${g.id}">
                <button type="button" class="gp-card__cover" aria-label="${esc(g.name)}">${coverHtml(g)}<span class="gp-card__tick" aria-hidden="true"></span></button>
                <div class="gp-card__t">${esc(g.name)}</div>
                <div class="gp-card__s">${g.count} in it${g.is_public ? ' · <span class="gp-pubmark">public</span>' : ''}${g.is_public && g.public_error ? ' · <span class="gp-warn" title="' + esc(g.public_error) + '">not sent yet</span>' : ''}</div>
            </div>`).join('') : '<div class="gp-empty">None yet.</div>';
        drawSelBar();
    }
    function drawSelBar() {
        selBar.hidden = !selecting;
        if (!selecting) return;
        const n = sel.size, all = n === LIST.length && n > 0;
        selBar.innerHTML = `<span class="gp-selbar__n">${n} selected</span>
            <button type="button" class="gp-btn gp-btn--small" data-sel="all">${all ? 'Select none' : 'Select all'}</button>
            <span class="gp-home__sp"></span>
            <button type="button" class="gp-btn gp-btn--small" data-sel="public"${n ? '' : ' disabled'}>Make public</button>
            <button type="button" class="gp-btn gp-btn--small" data-sel="private"${n ? '' : ' disabled'}>Make private</button>
            <button type="button" class="gp-btn gp-btn--small gp-btn--danger" data-sel="delete"${n ? '' : ' disabled'}>Delete</button>
            <span class="gp-selbar__say"></span>`;
    }
    cards.onclick = e => {
        const c = e.target.closest('.gp-card'); if (!c) return;
        const id = parseInt(c.dataset.id, 10);
        // ⌘ / ctrl / shift + click starts choosing without pressing Select first
        if (!selecting && (e.metaKey || e.ctrlKey || e.shiftKey)) selecting = true;
        if (selecting) { sel.has(id) ? sel.delete(id) : sel.add(id); drawCards(); return; }
        open(id);
    };
    selBar.onclick = async e => {
        const b = e.target.closest('[data-sel]'); if (!b) return;
        const what = b.dataset.sel, ids = [...sel];
        if (what === 'all') { if (sel.size === LIST.length) sel.clear(); else LIST.forEach(g => sel.add(g.id)); drawCards(); return; }
        if (!ids.length) return;
        if (what === 'delete' && !confirm(`Delete ${ids.length === 1 ? 'this grúpa' : 'these ' + ids.length + ' grúpaí'}? Nothing in your room is touched, only the grúpa${ids.length === 1 ? '' : 'í'}.`)) return;
        selBar.querySelectorAll('button').forEach(x => { x.disabled = true; });
        let msg = '', bad = false;
        try {
            const d = await call('/api/grupa/bulk', 'POST', { ids, action: what });
            msg = what === 'delete' ? d.n + ' deleted' : what === 'public' ? d.n + ' made public' : d.n + ' made private';
            if (d.public_error) { msg = d.public_error; bad = true; }
        } catch (err) { msg = err.message; bad = true; }
        if (what === 'delete') sel.clear();
        ids.forEach(changed);
        await loadList();
        const sayEl = $('.gp-selbar__say'); if (sayEl) { sayEl.textContent = msg; sayEl.classList.toggle('bad', bad); }
    };
    homeEl.querySelector('.gp-home__head').onclick = e => {
        const b = e.target.closest('[data-home]'); if (!b) return;
        if (b.dataset.home === 'select') { selecting = !selecting; if (!selecting) sel.clear(); drawCards(); }
        else if (b.dataset.home === 'look') { lookOpen = !lookOpen; drawLook(); }
    };

    // ── choosing a typeface and a ground: the same few controls for the shared look and for one grúpa's own ──
    function lookControls(cur, own) {
        const custom = cur.bg && !SWATCHES.includes(cur.bg);
        const inkOwn = cur.ink && !SWATCHES.includes(cur.ink);
        const inkRow = !own ? '' : `<div class="gp-pickrow"><span class="gp-pickrow__k">Writing</span><div class="gp-swatches">
                <button type="button" class="gp-sw gp-sw--page${cur.ink ? '' : ' on'}" data-ink="" title="Chosen to suit the colour behind it">Auto</button>
                ${SWATCHES.map(c => `<button type="button" class="gp-sw${c === cur.ink ? ' on' : ''}" data-ink="${c}" style="background:${c}" title="${c}" aria-label="${c}"></button>`).join('')}
                <label class="gp-sw gp-sw--own${inkOwn ? ' on' : ''}" title="Any other colour"${inkOwn ? ` style="background:${esc(cur.ink)}"` : ''}><span>＋</span><input type="color" data-inkpick value="${esc(inkOwn ? cur.ink : '#c9412f')}"></label>
            </div></div>`;
        return `<div class="gp-pickrow"><span class="gp-pickrow__k">Typeface</span><div class="gp-fonts">${FONTS.map(f =>
                `<button type="button" class="gp-font${f === cur.font ? ' on' : ''}" data-font="${esc(f)}" style="font-family:'${esc(f)}', Georgia, serif">${esc(f)}</button>`).join('')}</div></div>
            <div class="gp-pickrow"><span class="gp-pickrow__k">Colour</span><div class="gp-swatches">
                <button type="button" class="gp-sw gp-sw--page${cur.bg ? '' : ' on'}" data-bg="" title="The page's own colour. It follows the light and dark themes">Page</button>
                ${SWATCHES.map(c => `<button type="button" class="gp-sw${c === cur.bg ? ' on' : ''}" data-bg="${c}" style="background:${c}" title="${c}" aria-label="${c}"></button>`).join('')}
                <label class="gp-sw gp-sw--own${custom ? ' on' : ''}" title="Any other colour"${custom ? ` style="background:${esc(cur.bg)}"` : ''}><span>＋</span><input type="color" data-bgpick value="${esc(custom ? cur.bg : '#34557e')}"></label>
            </div></div>${inkRow}`;
    }
    // wire them: `set(patch)` is told {font} or {bg}
    function bindLook(box, set) {
        box.querySelectorAll('[data-font]').forEach(b => { b.onclick = () => set({ font: b.dataset.font }); });
        box.querySelectorAll('[data-bg]').forEach(b => { b.onclick = () => set({ bg: b.dataset.bg }); });
        const col = box.querySelector('input[data-bgpick]');
        if (col) col.onchange = () => set({ bg: col.value });
        box.querySelectorAll('[data-ink]').forEach(b => { b.onclick = () => set({ ink: b.dataset.ink }); });
        const ink = box.querySelector('input[data-inkpick]');
        if (ink) ink.onchange = () => set({ ink: ink.value });
    }
    function drawLook() {
        lookBox.hidden = !lookOpen;
        $('[data-home=look]').classList.toggle('gp-btn--primary', lookOpen);
        if (!lookOpen) { lookBox.innerHTML = ''; return; }
        lookBox.innerHTML = `<div class="gp-box__h"><span>The look your grúpaí share</span><button type="button" class="gp-btn gp-btn--small" data-look="done">Done</button></div>
            ${lookControls(LOOK)}`;
        bindLook(lookBox, async patch => {
            try { LOOK = (await call('/api/grupa/look', 'POST', patch)).look; } catch (_) {}
            await loadList(); drawLook(); changed(0);
        });
        $('[data-look=done]', lookBox).onclick = () => { lookOpen = false; drawLook(); };
    }

    function home() {
        gid = 0; G = null; ITEMS = []; coverOpen = false;
        oneEl.hidden = true; homeEl.hidden = false;
        pane.innerHTML = '';
        if (opts.onOpen) opts.onOpen(0, null);
        loadList();
    }
    $('[data-one=back]').onclick = home;

    async function open(id) {
        if (!id) { home(); return; }
        let d;
        try { d = await call('/api/grupa/' + id); }
        catch (_) { home(); return; }
        if (!alive) return;
        gid = id; G = d.grupa; ITEMS = d.items; OWN = d.cover_own; CHOICES = d.cover_choices || [];
        LOOK = d.look || LOOK; FONTS = d.fonts || FONTS; SWATCHES = d.swatches || SWATCHES;
        homeEl.hidden = true; oneEl.hidden = false; coverOpen = false;
        selecting = false; sel.clear();
        if (opts.onOpen) opts.onOpen(id, G);
        pane.innerHTML = `
            <header class="gp-head">
                <button type="button" class="gp-head__cover" data-do="cover" title="Change the cover"></button>
                <div class="gp-head__main">
                    <h1 class="gp-name" contenteditable="plaintext-only" spellcheck="false">${esc(G.name)}</h1>
                    <textarea class="gp-desc" rows="1" placeholder="What this grúpa is">${esc(G.description || '')}</textarea>
                </div>
            </header>
            <div class="gp-coverbox" hidden></div>
            <div class="gp-bar">
                <button class="gp-btn gp-btn--primary" data-do="play">Play</button>
                <button class="gp-btn" data-do="cue" data-snt-keep>Add to the cue</button>
                <button class="gp-btn" data-do="look" title="This grúpa's own look: its typeface, its colours, or a picture">Look</button>
                <span class="gp-bar__count"></span>
                <button type="button" class="gp-switch" data-do="public" role="switch" aria-checked="false"><span class="gp-switch__box" aria-hidden="true"></span><span class="gp-switch__t">Make public</span></button>
                <button class="gp-btn gp-btn--small gp-btn--danger" data-do="del">Delete</button>
            </div>
            <div class="gp-pubnote" hidden></div>
            <div class="gp-folder" hidden></div>
            <div class="gp-add">
                <input class="gp-input gp-q" autocomplete="off" placeholder="Paste a link, or type to find a record, label, artist, set or music room">
                <div class="gp-results"></div>
                <div class="gp-add__status"></div>
            </div>
            <div class="gp-now"></div>
            <div class="gp-items"></div>
            <section class="gp-sp"></section>`;
        const name = $('.gp-name', pane);
        name.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); name.blur(); } };
        name.onblur = async () => {
            const v = name.textContent.trim();
            if (!v) { name.textContent = G.name; return; }
            if (v !== G.name) { await call('/api/grupa/' + gid, 'PATCH', { name: v }); G.name = v; paintCover(); mine(() => changed(gid)); if (opts.onOpen) opts.onOpen(gid, G); }
        };
        const desc = $('.gp-desc', pane);
        grow(desc); desc.oninput = () => grow(desc);
        desc.onblur = async () => { const v = desc.value.trim(); if (v !== (G.description || '')) { await call('/api/grupa/' + gid, 'PATCH', { description: v }); G.description = v; mine(() => changed(gid)); } };
        $('[data-do=play]', pane).onclick = () => play(null, false);
        $('[data-do=cue]', pane).onclick = () => play(null, true);
        $('[data-do=del]', pane).onclick = async () => {
            if (!confirm(`Delete “${G.name}”? Nothing in your room is touched, only this grúpa.`)) return;
            const was = gid;
            await call('/api/grupa/' + gid, 'DELETE');
            changed(was);
            home();
        };
        $('[data-do=cover]', pane).onclick = () => {
            coverOpen = !coverOpen;
            if (coverOpen) coverTab = ({ text: 'text', item: 'item' })[(OWN && OWN.kind) || ''] || 'shared';
            drawCoverBox();
        };
        // "Look" opens straight on this grúpa's OWN look (nothing changes until something is chosen)
        $('[data-do=look]', pane).onclick = () => {
            coverOpen = !coverOpen;
            if (coverOpen) coverTab = (OWN && OWN.kind) === 'item' ? 'item' : 'text';
            drawCoverBox();
        };
        $('[data-do=public]', pane).onclick = togglePublic;
        paintCover(); paintPublic();
        bindAdd();
        renderItems();
        spotifyBits();
    }

    // ── this grúpa as a folder of files, to drag into Ableton, Serato, rekordbox… ──
    // Its own records, in this order, put in one folder WITHOUT copying them where the disk
    // allows (grupa_folder.py says how); copies only when asked, and said plainly first.
    let folderT = 0, folderSeq = 0, folderSaid = '';
    const hours = s => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? h + ' h ' + m + ' min' : m + ' min'; };
    const room = b => b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : Math.max(1, Math.round(b / 1e6)) + ' MB';
    const many = (n, one, more) => n + ' ' + (n === 1 ? one : (more || one + 's'));
    function leftOut(l) {
        const bits = [];
        if (l.streams) bits.push(many(l.streams, 'streamed thing'));
        if (l.borrowed) bits.push(many(l.borrowed, 'borrowed record') + ' (borrowed records play only here)');
        if (l.missing) bits.push(many(l.missing, 'file') + ' that can’t be found (is its drive plugged in?)');
        if (l.other) bits.push(many(l.other, 'link or room', 'links or rooms'));
        return bits.length ? 'Left out: ' + bits.join(', ') + '.' : '';
    }
    function folderSoon() { clearTimeout(folderT); folderT = setTimeout(paintFolder, 450); }
    async function paintFolder() {
        const box = $('.gp-folder', pane); if (!box || !gid) return;
        const mine = ++folderSeq, forGid = gid;
        let d; try { d = await call(`/api/grupa/${gid}/folder`); } catch (_) { box.hidden = true; return; }
        if (mine !== folderSeq || forGid !== gid || !alive) return;
        const P = d.plan, F = d.folder, out = leftOut(P.left_out || {});
        if (!P.count && !F) { box.hidden = true; box.innerHTML = ''; return; }
        box.hidden = false;
        let h = `<div class="gp-folder__k">Folder</div>`;
        if (!F) {
            h += `<p class="gp-folder__p">${many(P.count, 'record')} · ${hours(P.seconds)}. Nothing is copied or moved.</p>
                  <div class="gp-folder__bar"><button type="button" class="gp-btn" data-f="make">Make the folder</button></div>`;
        } else {
            const how = F.how || {}, n = F.files;
            const what = how.copy ? `${many(n, 'record')}, in order, as copies${F.bytes ? ' (' + room(F.bytes) + ')' : ''}.`
                : `${many(n, 'record')}, in order.`;
            h += `<p class="gp-folder__path" title="${esc(F.folder)}">${esc(F.folder)}</p>
                  <p class="gp-folder__p">${what}${F.broken ? ` ${many(F.broken, 'of them points', 'of them point')} at a file that can’t be reached right now (is its drive plugged in?).` : ''}</p>
                  ${F.stale ? `<p class="gp-folder__p gp-folder__p--now">The grúpa has changed since the folder was made.</p>` : ''}
                  <div class="gp-folder__bar">
                    <button type="button" class="gp-btn${F.stale ? '' : ' gp-btn--primary'}" data-f="show">Show the folder</button>
                    <button type="button" class="gp-btn${F.stale ? ' gp-btn--primary' : ''}" data-f="make" data-mode="${how.copy ? 'copy' : 'link'}">${F.stale ? 'Bring it up to date' : 'Make it again'}</button>
                    ${how.copy ? `<button type="button" class="gp-folder__link" data-f="make" data-mode="link">Use the files themselves, not copies</button>`
                               : `<button type="button" class="gp-folder__link" data-f="copy" title="For a program that won’t take them as they are">Copy the files instead (${room(P.bytes)})</button>`}
                  </div>`;
        }
        if (out) h += `<p class="gp-folder__p gp-folder__p--quiet">${esc(out)}</p>`;
        h += `<p class="gp-folder__say" aria-live="polite">${esc(folderSaid)}</p>`;
        box.innerHTML = h;
        folderSaid = '';                                   // (said once: it doesn't linger over later changes)
        const say = t => { folderSaid = t || ''; const el = $('.gp-folder__say', box); if (el) el.textContent = folderSaid; };
        const make = async (mode, btn) => {
            if (btn) btn.disabled = true;
            say(mode === 'copy' ? 'Copying…' : 'Making the folder…');
            const r = await fetch(`/api/grupa/${forGid}/folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) });
            const o = await r.json().catch(() => ({}));
            if (r.status === 409 && o.needs_copy) {
                say('');
                if (confirm(`This disk can’t hold your records without copying them.\n\nCopy ${many(o.count, 'file')} (${room(o.bytes)}) into the folder? The originals stay where they are.`)) return make('copy', btn);
                return paintFolder();
            }
            if (!r.ok) { say(o.error || 'The folder couldn’t be made.'); if (btn) btn.disabled = false; return; }
            folderSaid = (o.failed && o.failed.length ? many(o.failed.length, 'record') + ' couldn’t be put in it. ' : '')
                + (o.kept && o.kept.length ? many(o.kept.length, 'file') + ' in it had been changed, so ' + (o.kept.length === 1 ? 'it was' : 'they were') + ' left alone. ' : '') || 'Done.';
            paintFolder();
        };
        box.querySelectorAll('[data-f]').forEach(b => b.onclick = async () => {
            const f = b.dataset.f;
            if (f === 'show') { try { await call(`/api/grupa/${forGid}/folder/show`, 'POST'); say(''); } catch (e) { say(e.message); } }
            else if (f === 'make') make(b.dataset.mode || 'link', b);
            else if (f === 'copy') { if (confirm(`Make real copies instead?\n\n${many(P.count, 'file')}, ${room(P.bytes)}. The originals stay where they are; the folder will hold copies of them.`)) make('copy', b); }
        });
    }

    // ── one grúpa's cover: the shared look, a look of its own, or a picture from something in it ──
    function paintCover() {
        const b = $('.gp-head__cover', pane); if (b) b.innerHTML = coverHtml(G) + '<span class="gp-head__edit">Change</span>';
    }
    async function saveCover(cover) {
        try {
            const d = await call('/api/grupa/' + gid, 'PATCH', { cover });
            G = Object.assign(G, d.grupa);
            OWN = Object.assign(OWN || {}, cover.kind === 'shared' ? { kind: '' } : cover);
            if (cover.kind === 'text' && !('bg' in cover)) OWN.bg = '';
            if (cover.kind === 'text' && !('ink' in cover)) OWN.ink = '';
        } catch (err) { say($('.gp-head__cover', pane), err.message, true); }
        paintCover(); drawCoverBox(); changed(gid);
    }
    // which of the three is being looked at: 'shared' | 'text' | 'item'. Choosing
    // the first two takes effect at once; "A picture" only shows the pictures —
    // nothing changes until one of them is chosen.
    let coverTab = 'shared';
    function drawCoverBox() {
        const box = $('.gp-coverbox', pane); if (!box) return;
        box.hidden = !coverOpen;
        if (!coverOpen) { box.innerHTML = ''; return; }
        const saved = (OWN && OWN.kind) || '';
        const mine = { font: (OWN && OWN.font) || LOOK.font, bg: saved === 'text' ? ((OWN && OWN.bg) || '') : LOOK.bg,
                       ink: saved === 'text' ? ((OWN && OWN.ink) || '') : '' };
        const picked = G.cover && G.cover.kind === 'image' ? G.cover.item : null;
        box.innerHTML = `<div class="gp-box__h"><span>This grúpa's cover</span><button type="button" class="gp-btn gp-btn--small" data-c="done">Done</button></div>
            <div class="gp-seg">
                <button type="button" class="${coverTab === 'shared' ? 'on' : ''}" data-c="shared" title="Its name, in the look all your grúpaí share">The shared look</button>
                <button type="button" class="${coverTab === 'text' ? 'on' : ''}" data-c="text" title="Its name, in a typeface and on a colour of its own">Its own look</button>
                <button type="button" class="${coverTab === 'item' ? 'on' : ''}" data-c="item" title="The cover of a record in it, or the picture of anything else in it">A picture</button>
            </div>
            ${coverTab === 'text' ? lookControls(mine, true) : ''}
            ${coverTab === 'item' ? (CHOICES.length
                ? `<div class="gp-pics">${CHOICES.map(c => `<button type="button" class="gp-pic${picked === c.item ? ' on' : ''}" data-item="${c.item}" title="${esc(c.title)}"><img src="${esc(c.image)}" alt="" loading="lazy" onerror="this.parentNode.remove()"></button>`).join('')}</div>`
                : '<p class="gp-box__p">Nothing in it has a picture yet.</p>') : ''}`;
        box.querySelectorAll('[data-c]').forEach(b => { b.onclick = () => {
            const c = b.dataset.c;
            if (c === 'done') { coverOpen = false; drawCoverBox(); return; }
            coverTab = c;
            if (c === 'shared') saveCover({ kind: 'shared' });
            else if (c === 'text') saveCover({ kind: 'text', font: mine.font, bg: mine.bg, ink: mine.ink });
            else drawCoverBox();
        }; });
        box.querySelectorAll('[data-item]').forEach(b => { b.onclick = () => saveCover({ kind: 'item', item: parseInt(b.dataset.item, 10) }); });
        if (coverTab === 'text') bindLook(box, patch => saveCover(Object.assign({ kind: 'text', font: mine.font, bg: mine.bg, ink: mine.ink }, patch)));
    }

    // ── public: off until its owner turns it on ──
    function paintPublic() {
        const b = $('[data-do=public]', pane), note = $('.gp-pubnote', pane); if (!b) return;
        const on = !!G.is_public;
        b.classList.toggle('on', on); b.setAttribute('aria-checked', on);
        $('.gp-switch__t', b).textContent = on ? 'Public' : 'Make public';
        b.title = on ? 'Others can find this grúpa. Click to make it private again' : 'Let others find this grúpa in Explore and in your public room';
        note.hidden = !on;
        note.classList.toggle('bad', on && !!G.public_error);
        note.textContent = !on ? '' : G.public_error
            ? G.public_error
            : 'Shown in Explore and in your public room. No files are sent.';
    }
    async function togglePublic() {
        const b = $('[data-do=public]', pane), want = !G.is_public;
        b.disabled = true;
        try {
            const d = await call(`/api/grupa/${gid}/public`, 'POST', { on: want });
            G.is_public = d.is_public; G.public_error = d.public_error || '';
        } catch (err) { G.public_error = err.message; }
        b.disabled = false;
        paintPublic(); changed(gid);
    }

    function openItem(it) {
        if (it.gone) return;
        if (it.kind === 'track') {
            if (opts.openTrack) { try { opts.openTrack(it.ref_id); return; } catch (_) {} }
            go('/room?track=' + it.ref_id);
        }
        else if (it.kind === 'grupa') open(it.ref_id);
        else if (it.kind === 'place') (window.rtGo || (h => { location.href = h; }))('/room/' + it.ref_id);
        else if (it.kind === 'set') go('/set/' + it.ref_id);
        else if (it.kind === 'room') go('/rooms/' + encodeURIComponent(it.ref_key) + (opts.inRoom ? '?overlay=1' : ''));
        else if (it.url) openUrl(it.url);
    }

    function renderItems() {
        const box = $('.gp-items', pane); if (!box) return;
        folderSoon();
        $('.gp-bar__count', pane).textContent = ITEMS.length ? `${ITEMS.length} in it` : '';
        const anyPlay = ITEMS.some(i => i.playable);
        $('[data-do=play]', pane).disabled = !anyPlay; $('[data-do=cue]', pane).disabled = !anyPlay;
        if (sortable) { try { sortable.destroy(); } catch (_) {} sortable = null; }
        if (!ITEMS.length) { box.innerHTML = '<div class="gp-empty">Nothing in it yet.</div>'; return; }
        box.innerHTML = ITEMS.map((it, i) => {
            const title = esc(it.title || 'Untitled');
            const canOpen = !it.gone && (it.kind !== 'label' && it.kind !== 'artist');
            return `<div class="gp-item${it.ai ? ' gp-item--ai' : ''}" data-id="${it.id}">
                <span class="gp-handle" title="Drag to reorder">⋮⋮</span>
                <span class="gp-n">${String(i + 1).padStart(2, '0')}</span>
                <div class="gp-cov"><span>${esc((it.title || '·').trim().charAt(0).toUpperCase())}</span>${it.image ? `<img src="${esc(it.image)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</div>
                <div class="gp-main">
                    ${canOpen ? `<button type="button" class="gp-t gp-t--link" data-act="open">${title}</button>` : `<span class="gp-t">${title}</span>`}
                    <div class="gp-s">${metaLine(it)}</div>
                    <textarea class="gp-note" rows="1" placeholder="Add a note" data-id="${it.id}">${esc(it.note || '')}</textarea>
                </div>
                <div class="gp-acts">
                    ${it.playable ? `<button class="gp-act" data-act="play" title="Play from here">▶</button><button class="gp-act" data-act="cue" data-snt-keep title="Add to the cue">＋</button>` : ''}
                    ${it.url ? `<button class="gp-act" data-act="out" title="Open on ${esc(it.service || hostOf(it.url))}">↗</button>` : ''}
                    ${it.kind === 'stream' ? (it.ai
                        ? `<button class="gp-act gp-act--word" data-act="notai" title="Take the mark off. It will play here again.">not AI</button>`
                        : `<button class="gp-act gp-act--word" data-act="ai" title="Mark as AI-made. It will not be played here, and neither will anything else by the same artist.">AI?</button>`) : ''}
                    <button class="gp-act gp-act--x" data-act="remove" title="Take out of this grúpa">✕</button>
                </div>
            </div>`;
        }).join('');
        box.querySelectorAll('.gp-note').forEach(n => {
            grow(n); n.oninput = () => grow(n);
            n.onblur = async () => {
                const it = ITEMS.find(x => x.id == n.dataset.id); const v = n.value.trim();
                if (it && v !== (it.note || '')) { await call('/api/grupa/item/' + it.id, 'PATCH', { note: v }); it.note = v; }
            };
        });
        box.onclick = async (e) => {
            const b = e.target.closest('[data-act]'); if (!b) return;
            const id = parseInt(b.closest('.gp-item').dataset.id, 10), it = ITEMS.find(x => x.id === id);
            const act = b.dataset.act;
            if (act === 'play') play(id, false);
            else if (act === 'cue') play(id, true);
            else if (act === 'open') openItem(it);
            else if (act === 'out') openUrl(it.url);
            else if (act === 'ai' || act === 'notai') {
                b.disabled = true;
                try { await call(`/api/grupa/item/${id}/ai`, 'POST', { ai: act === 'ai' }); } catch (_) {}
                await reload();                       // the mark hangs on the artist: other rows may change too
            }
            else if (act === 'remove') { await call('/api/grupa/item/' + id, 'DELETE'); ITEMS = ITEMS.filter(x => x.id !== id); renderItems(); refreshCover(); }
        };
        // (a row is dragged by its handle, its number or its cover)
        if (window.Sortable) sortable = window.Sortable.create(box, { handle: '.gp-handle, .gp-n, .gp-cov', animation: 140, ghostClass: 'sortable-ghost',
            onStart: () => { dragging = true; },
            onEnd: async () => {
                dragging = false;
                const ids = [...box.querySelectorAll('.gp-item')].map(el => parseInt(el.dataset.id, 10));
                ITEMS.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
                box.querySelectorAll('.gp-n').forEach((n, i) => { n.textContent = String(i + 1).padStart(2, '0'); });
                await call(`/api/grupa/${gid}/order`, 'POST', { ids });
                folderSoon();
            } });
    }

    async function reload() {
        if (!gid) return;
        try {
            const d = await call('/api/grupa/' + gid);
            G = d.grupa; ITEMS = d.items; OWN = d.cover_own; CHOICES = d.cover_choices || [];
            renderItems(); paintNow(); paintCover(); paintPublic(); if (coverOpen) drawCoverBox();
        } catch (_) {}
    }
    // what is in it changed: the pictures its cover could wear may have too
    async function refreshCover() {
        if (!gid) return;
        try { const d = await call('/api/grupa/' + gid); G = d.grupa; OWN = d.cover_own; CHOICES = d.cover_choices || []; paintCover(); if (coverOpen) drawCoverBox(); } catch (_) {}
    }

    const play = (itemId, cueOnly) => playGrupa(gid, itemId, cueOnly);

    // ── adding: one line that takes a link or a search; links can be dropped in too ──
    // The search looks in two places at once: your own room (records by any
    // words in any order, artists, labels, places, sets, grúpa, music rooms)
    // and — when it's connected — Spotify (tracks, albums, artists). Every row
    // has its cover. Adding from a row leaves the list open, so several can go
    // in one after another; ↑ ↓ and Enter work from the line.
    let addOne = null;
    const mmss = s => { s = Math.round(s || 0); return s ? Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0') : ''; };
    const SP_KIND = { track: 'Track', album: 'Album', artist: 'Artist' };
    function bindAdd() {
        const q = $('.gp-q', pane), res = $('.gp-results', pane), st = $('.gp-add__status', pane);
        let t = null, t2 = null, seq = 0, sel = -1, asking = false, rows = { mine: [], spotify: [] };
        const sayLine = (msg, bad) => { st.textContent = msg || ''; st.classList.toggle('bad', !!bad); };
        addOne = async function (body, quiet) {
            if (!quiet) sayLine('adding…');
            try {
                const d = await call(`/api/grupa/${gid}/items`, 'POST', body);
                ITEMS.push(d.item); renderItems(); refreshCover(); paintNow();
                if (!quiet) {
                    q.value = ''; res.innerHTML = ''; rows = { mine: [], spotify: [] }; sel = -1; sayLine('');
                    const note = $(`.gp-item[data-id="${d.item.id}"] .gp-note`, pane); if (note) note.focus({ preventScroll: false });
                }
                return d.item;
            } catch (e) { sayLine(e.message, true); return null; }
        };
        const btns = () => [...res.querySelectorAll('.gp-res')];
        const mark = () => btns().forEach((b, i) => b.classList.toggle('on', i === sel));
        const inIt = (r, src) => src === 'spotify' ? ITEMS.some(x => x.url === r.url)
            : (r.kind === 'track' ? (r.have || ITEMS.some(x => x.kind === 'track' && x.ref_id === r.ref_id)) : false);
        // the small print under a result's name
        function under(r, src) {
            const bits = [];
            if (src === 'spotify') {
                if (r.ai) bits.push('<span class="gp-ai">AI-made</span>');
                if (r.stream_type === 'track') { if (r.subtitle) bits.push(esc(r.subtitle)); if (r.album) bits.push(esc(r.album)); const m = mmss(r.duration_sec); if (m) bits.push(m); }
                else if (r.stream_type === 'album') { if (r.subtitle) bits.push(esc(r.subtitle)); if (r.year) bits.push(esc(r.year)); if (r.tracks) bits.push(r.tracks + (r.tracks === 1 ? ' track' : ' tracks')); }
                else bits.push('on Spotify');
            } else if (r.free) bits.push('not in your room — add by name');
            else if (r.kind === 'track') { if (r.subtitle) bits.push(esc(r.subtitle)); if (r.album) bits.push(esc(r.album)); if (r.year) bits.push(esc(r.year)); }
            else if (r.count != null) bits.push(r.count + (r.count === 1 ? ' record in your room' : ' records in your room'));
            else if (r.kind === 'room') bits.push(esc(r.subtitle || ''));
            return bits.filter(Boolean).join(' · ');
        }
        function row(r, src, i) {
            const have = inIt(r, src), img = r.thumb || r.image || '';
            const kind = src === 'spotify' ? (r.stream_type === 'album' && r.album_type && r.album_type !== 'album' ? r.album_type : SP_KIND[r.stream_type] || 'Stream') : (KIND[r.kind] || r.kind);
            return `<button type="button" class="gp-res${have ? ' have' : ''}" data-src="${src}" data-i="${i}">
                <span class="gp-res__c"><span>${esc((r.title || '·').trim().charAt(0).toUpperCase())}</span>${img ? `<img src="${esc(img)}" alt="" onerror="this.remove()">` : ''}</span>
                <span class="gp-res__m"><span class="gp-res__t">${esc(r.title)}</span><span class="gp-res__s">${under(r, src)}</span></span>
                <span class="gp-res__k">${have ? 'in it' : esc(kind)}</span></button>`;
        }
        const draw = () => {
            const mine = rows.mine.map((r, i) => [r, i]).filter(x => !x[0].free), free = rows.mine.map((r, i) => [r, i]).filter(x => x[0].free);
            let html = '';
            if (mine.length) html += `<div class="gp-res__h">In your room</div>` + mine.map(x => row(x[0], 'mine', x[1])).join('');
            if (rows.spotify.length) html += `<div class="gp-res__h">On Spotify</div>` + rows.spotify.map((r, i) => row(r, 'spotify', i)).join('');
            else if (asking) html += `<div class="gp-res__h">On Spotify <i>looking…</i></div>`;
            if (free.length) html += `<div class="gp-res__h">Or by name</div>` + free.map(x => row(x[0], 'mine', x[1])).join('');
            res.innerHTML = html;
            if (sel >= btns().length) sel = -1;
            mark();
        };
        const close = () => { clearTimeout(t); clearTimeout(t2); seq++; asking = false; rows = { mine: [], spotify: [] }; sel = -1; res.innerHTML = ''; };
        q.oninput = () => {
            clearTimeout(t); clearTimeout(t2); sayLine('');
            const v = q.value.trim(), my = ++seq;
            rows = { mine: [], spotify: [] }; sel = -1; asking = false;
            if (v.length < 2) { res.innerHTML = ''; return; }
            if (isLink(v)) {
                res.innerHTML = `<button type="button" class="gp-res" data-link="1"><span class="gp-res__c"><span>↗</span></span>
                    <span class="gp-res__m"><span class="gp-res__t">Add this link</span><span class="gp-res__s">${esc(hostOf(/^https?:/i.test(v) ? v : 'https://' + v) || v)}</span></span>
                    <span class="gp-res__k">Link</span></button>`;
                return;
            }
            asking = !!(SP && SP.connected);
            t = setTimeout(async () => {
                let d; try { d = await call(`/api/grupa/search?gid=${gid}&q=` + encodeURIComponent(v)); } catch (_) { return; }
                if (my !== seq) return;
                rows.mine = d.results; draw();
            }, 200);
            if (asking) t2 = setTimeout(async () => {      // Spotify is asked once the typing rests
                let d; try { d = await call('/api/spotify/search?q=' + encodeURIComponent(v)); } catch (_) { d = { results: [] }; }
                if (my !== seq) return;
                asking = false; rows.spotify = d.results || []; draw();
            }, 420);
        };
        const choose = b => {
            if (!b) return;
            if (b.dataset.link) return addOne({ url: q.value.trim() });
            const r = (rows[b.dataset.src] || [])[parseInt(b.dataset.i, 10)]; if (!r) return;
            if (b.classList.contains('have')) return;                       // already in this grúpa
            const body = b.dataset.src === 'spotify'
                ? { url: r.url, title: r.title, subtitle: r.stream_type === 'artist' ? 'Artist' : r.subtitle, image: r.image, by_ids: r.by_ids, duration_sec: r.duration_sec }
                : { kind: r.kind, ref_id: r.ref_id, ref_key: r.ref_key, title: r.title, subtitle: r.subtitle };
            // it goes in, and the list stays: the row now reads "in it", the next one can follow
            b.classList.add('have'); const k = b.querySelector('.gp-res__k'); if (k) k.textContent = 'in it';
            addOne(body, true).then(it => { if (!it) { b.classList.remove('have'); if (k) k.textContent = '—'; } });
        };
        q.onkeydown = e => {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                const n = btns().length; if (!n) return;
                e.preventDefault();
                sel = e.key === 'ArrowDown' ? Math.min(n - 1, sel + 1) : Math.max(0, sel - 1);
                mark(); btns()[sel].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const v = q.value.trim();
                if (isLink(v)) addOne({ url: v }); else choose(btns()[sel >= 0 ? sel : 0]);
            } else if (e.key === 'Escape' && (q.value || res.innerHTML)) { e.preventDefault(); q.value = ''; close(); }
        };
        q.onpaste = e => {                                     // several links pasted at once go in one after another
            const links = linksIn(e.clipboardData || { getData: () => '' });
            if (links.length > 1) { e.preventDefault(); addMany(links); }
        };
        res.onclick = e => { const b = e.target.closest('.gp-res'); if (b) { choose(b); q.focus({ preventScroll: true }); } };
    }
    async function addMany(links) {
        const st = $('.gp-add__status', pane); let n = 0;
        for (const url of links) {
            if (!alive || !gid) break;
            if (st) { st.classList.remove('bad'); st.textContent = `adding ${++n} of ${links.length}…`; }
            await addOne({ url }, true);
        }
        if (st) st.textContent = '';
    }
    // drag tracks in — from the Spotify app, a browser tab, anywhere that hands over links
    pane.addEventListener('dragover', e => {
        if (!gid || dragging) return;
        const types = [...(e.dataTransfer && e.dataTransfer.types || [])];
        if (!types.includes('text/uri-list') && !types.includes('text/plain')) return;
        e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; pane.classList.add('gp-drop');
    });
    pane.addEventListener('dragleave', e => { if (!pane.contains(e.relatedTarget)) pane.classList.remove('gp-drop'); });
    pane.addEventListener('drop', e => {
        pane.classList.remove('gp-drop');
        if (!gid || dragging) return;
        const links = linksIn(e.dataTransfer);
        if (!links.length) return;
        e.preventDefault();
        addMany(links);
    });

    // ── Spotify: what it's playing now, the sign-in, your own playlists ──
    async function spotifyBits() {
        try { SP = await call('/api/spotify/status'); } catch (_) { SP = null; }
        if (!alive || !gid) return;
        const q = $('.gp-q', pane);
        if (q && SP && SP.connected) q.placeholder = 'Paste a link, or type to find a record, a track on Spotify, a label, artist, set or music room';
        paintNow();
        playlists();
    }
    async function signIn(btn) {
        if (!SP || !SP.client_id_set) { go('/spotify'); return; }          // first time: the set-up page
        btn.disabled = true;
        try {
            const d = await call('/api/spotify/auth/start', 'POST');
            await openUrl(d.auth_url);                                      // Spotify's own sign-in, in the browser
            btn.textContent = 'waiting for Spotify…';
            for (let i = 0; i < 90 && alive; i++) {                         // it comes back by itself once you've agreed
                await new Promise(r => setTimeout(r, 2000));
                const s = await call('/api/spotify/status').catch(() => null);
                if (s && s.connected && !s.needs_reconnect) { SP = s; spotifyBits(); return; }
            }
        } catch (_) { go('/spotify'); return; }
        btn.disabled = false; btn.textContent = 'Sign in to Spotify';
    }
    let nowState = null;
    function paintNow() {
        const box = $('.gp-now', pane); if (!box) return;
        let html = '';
        const s = nowState, g = s && s.guest;
        const cur = s && s.queue && s.queue[s.idx];
        // what Spotify is sounding right now: the listener's own listening, or a record of ours playing there
        const now = g ? { url: g.url, title: g.title, subtitle: g.artist, image: g.image_url, by_ids: g.by_ids, duration_sec: g.duration }
            : (cur && cur.kind === 'embed' && cur.source === 'spotify' && s.playing ? { url: cur.url, title: cur.title, subtitle: cur.artist } : null);
        nowUrl = now ? now.url : '';
        if (now && now.url && !ITEMS.some(i => i.url === now.url)) {
            html = `<div class="gp-now__row"><span class="gp-now__k">In Spotify now</span>
                <span class="gp-now__t">${esc(now.title || '')}${now.subtitle ? ' <i>— ' + esc(now.subtitle) + '</i>' : ''}</span>
                <button class="gp-btn gp-btn--small" data-now="add">Add</button></div>`;
        } else if (SP && !SP.connected && window.MR_GR && !SP.client_id_set) {
            // the trial: a key is given by the Music Room to five people at a time (gr_sim); no set-up page for anyone
            html = `<div class="gp-now__row"><span class="gp-now__t gp-now__t--note">Spotify plays here in its own small player.</span></div>`;
        } else if (SP && !SP.connected) {
            html = `<div class="gp-now__row"><span class="gp-now__t gp-now__t--note">Spotify isn't connected.</span>
                <button class="gp-btn gp-btn--small" data-now="signin">${SP.client_id_set ? 'Sign in to Spotify' : 'Set up Spotify'}</button></div>`;
        } else if (SP && SP.needs_reconnect) {
            html = `<div class="gp-now__row"><span class="gp-now__t gp-now__t--note">Spotify needs a fresh sign-in.</span>
                <button class="gp-btn gp-btn--small" data-now="signin">Sign in to Spotify</button></div>`;
        } else if (SP && SP.no_premium) {
            html = `<div class="gp-now__row"><span class="gp-now__t gp-now__t--note">Needs Spotify Premium. Links still play in Spotify's small player.</span></div>`;
        }
        if (box._html !== html) { box.innerHTML = html; box._html = html; }
        box._now = now;
        box.onclick = e => {
            const b = e.target.closest('[data-now]'); if (!b) return;
            if (b.dataset.now === 'add' && box._now) addOne(box._now, true);
            else if (b.dataset.now === 'signin') signIn(b);
        };
    }
    async function watchNow() {
        if (!alive) return;
        if (gid && document.visibilityState !== 'hidden' && host.offsetParent !== null) {
            try { nowState = await call('/api/seinnteoir/state'); paintNow(); } catch (_) {}
        }
        nowT = setTimeout(watchNow, 2500);
    }
    // Your own Spotify playlists: open one to see what's in it, and add from
    // there — a track at a time, all of them, or the playlist whole as one
    // element. (Spotify only lets an app read the playlists you made yourself;
    // one you merely follow can still go in whole.)
    function playlists() {
        const box = $('.gp-sp', pane); if (!box) return;
        if (!SP || !SP.connected) { box.innerHTML = ''; return; }
        box.innerHTML = `<div class="gp-sp__h"><span>Your Spotify playlists</span><button class="gp-btn gp-btn--small" data-sp="go">Show them</button></div><div class="gp-sp__body"></div>`;
        const body = $('.gp-sp__body', box), goBtn = $('[data-sp=go]', box);
        let lists = [], more = false, open = null, tracksOf = [];
        const has = url => ITEMS.some(x => x.url === url);
        const keep = t => ({ url: t.spotify_url || ('https://open.spotify.com/track/' + t.spotify_id), title: t.title || '', subtitle: t.artist || '',
            image: t.album_image_mid || t.album_image_url || '', by_ids: t.artist_ids || '', duration_sec: Math.round((t.duration_ms || 0) / 100) / 10 });
        function showLists() {
            open = null;
            body.innerHTML = `<div class="gp-sp__list">${lists.map((p, i) => `<button type="button" class="gp-res" data-pl="${i}">
                <span class="gp-res__c"><span>${esc((p.name || '·').trim().charAt(0).toUpperCase())}</span>${p.image_url ? `<img src="${esc(p.image_url)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</span>
                <span class="gp-res__m"><span class="gp-res__t">${esc(p.name || 'Untitled')}</span><span class="gp-res__s">${p.track_count != null ? p.track_count + (p.track_count === 1 ? ' track' : ' tracks') + ' · ' : ''}${esc(p.owner || '')}</span></span>
                <span class="gp-res__k">open</span></button>`).join('')}</div>
                ${more ? '<div class="gp-sp__more"><button class="gp-btn gp-btn--small" data-sp="more">Show more</button></div>' : ''}`;
        }
        async function loadLists(offset) {
            const d = await call('/api/spotify/playlists?limit=50&offset=' + offset);
            lists = lists.concat(d.items || []); more = !!d.has_more;
        }
        async function openList(p) {
            open = p; tracksOf = [];
            const head = (extra) => `<div class="gp-sp__open"><button type="button" class="gp-back" data-sp="back">← Your playlists</button>
                <div class="gp-sp__name">${esc(p.name || 'Untitled')}</div>${extra || ''}</div>`;
            const whole = p.url ? `<button class="gp-btn gp-btn--small" data-sp="whole" title="Put the playlist in as one element"${has(p.url) ? ' disabled' : ''}>${has(p.url) ? 'In it, whole' : 'Add it whole'}</button>` : '';
            if (!p.is_mine) {
                body.innerHTML = head(`<div class="gp-bar">${whole}</div>`) + `<div class="gp-sp__note">Spotify only lets an app read the playlists you made yourself, so the tracks in this one can't be listed here. It can still go in whole.</div>`;
                return;
            }
            body.innerHTML = head() + '<div class="gp-sp__note">asking Spotify…</div>';
            let d; try { d = await call(`/api/spotify/playlist/${encodeURIComponent(p.id)}/tracks`); }
            catch (err) { if (open === p) body.innerHTML = head(`<div class="gp-bar">${whole}</div>`) + `<div class="gp-sp__note">Spotify would not show the tracks in this one. It can still go in whole.</div>`; return; }
            if (open !== p) return;
            tracksOf = d.items || [];
            const left = tracksOf.filter(t => !has(keep(t).url)).length;
            body.innerHTML = head(`<div class="gp-bar"><button class="gp-btn gp-btn--small gp-btn--primary" data-sp="all"${left ? '' : ' disabled'}>${left ? 'Add all ' + left : 'All in it'}</button>${whole}
                    <span class="gp-bar__count">${tracksOf.length} track${tracksOf.length === 1 ? '' : 's'}</span></div>`)
                + `<div class="gp-sp__list">${tracksOf.map((t, i) => { const k = keep(t), inIt = has(k.url); const m = mmss(k.duration_sec);
                    return `<button type="button" class="gp-res${inIt ? ' have' : ''}" data-tr="${i}">
                    <span class="gp-res__c"><span>${esc((t.title || '·').trim().charAt(0).toUpperCase())}</span>${(t.album_image_small || t.album_image_url) ? `<img src="${esc(t.album_image_small || t.album_image_url)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</span>
                    <span class="gp-res__m"><span class="gp-res__t">${esc(t.title || 'Untitled')}</span><span class="gp-res__s">${[esc(t.artist || ''), esc(t.album || ''), m].filter(Boolean).join(' · ')}</span></span>
                    <span class="gp-res__k">${inIt ? 'in it' : 'add'}</span></button>`; }).join('')}</div>`;
        }
        goBtn.onclick = async () => {
            if (lists.length) { lists = []; body.innerHTML = ''; goBtn.textContent = 'Show them'; return; }      // fold it away again
            goBtn.disabled = true; body.innerHTML = '<div class="gp-sp__note">asking Spotify…</div>';
            try { await loadLists(0); showLists(); goBtn.textContent = 'Hide them'; }
            catch (err) { body.innerHTML = `<div class="gp-sp__note">${/not connected/i.test(err.message) ? 'Spotify wants a fresh sign-in before it will show your playlists.' : esc(err.message)}</div>`; }
            goBtn.disabled = false;
        };
        body.onclick = async (e) => {
            const b = e.target.closest('[data-sp], [data-pl], [data-tr]'); if (!b) return;
            if (b.dataset.pl != null) return openList(lists[parseInt(b.dataset.pl, 10)]);
            if (b.dataset.tr != null) {
                if (b.classList.contains('have')) return;
                const t = tracksOf[parseInt(b.dataset.tr, 10)]; if (!t) return;
                b.classList.add('have'); const k = b.querySelector('.gp-res__k'); k.textContent = 'in it';
                const it = await addOne(keep(t), true);
                if (!it) { b.classList.remove('have'); k.textContent = 'add'; }
                return;
            }
            const what = b.dataset.sp;
            if (what === 'back') return showLists();
            if (what === 'more') { b.disabled = true; try { await loadLists(lists.length); } catch (_) {} return showLists(); }
            if (what === 'whole' && open) {
                b.disabled = true;
                const it = await addOne({ url: open.url, title: open.name, subtitle: open.owner || '', image: open.image_url || '' }, true);
                b.textContent = it ? 'In it, whole' : 'Add it whole'; b.disabled = !!it;
                return;
            }
            if (what === 'all' && open) {
                b.disabled = true; b.textContent = 'adding…';
                try {
                    const r = await call(`/api/grupa/${gid}/streams`, 'POST', { items: tracksOf.map(keep) });
                    await reload(); changed(gid);
                    say(b, r.added ? r.added + ' added' + (r.already ? ' · ' + r.already + ' already there' : '') : 'All already in it');
                } catch (err) { say(b, err.message, true); }
                if (open) openList(open);
            }
        };
    }

    // something was added from elsewhere (the deck's ＋ key, a record's menu in the room)
    // (a change this surface made itself is told to the others, not answered here: rebuilding every
    //  row after saving the name or description took the cursor out of the note being clicked into)
    let selfChange = false;
    function mine(fn) { selfChange = true; try { fn(); } finally { selfChange = false; } }
    const onChanged = e => { if (selfChange) return; if (!gid) loadList(); else if (e.detail && e.detail.id === gid) reload(); };
    window.addEventListener('grupa-changed', onChanged);
    const onFocus = () => { if (alive && gid && SP && (!SP.connected || SP.needs_reconnect)) spotifyBits(); };
    window.addEventListener('focus', onFocus);

    (async function start() {
        await loadList();
        if (opts.gid && LIST.some(g => g.id === opts.gid)) await open(opts.gid);
        watchNow();
    })().catch(e => { cards.innerHTML = `<div class="gp-empty">${esc(e.message)}</div>`; });

    return {
        open, home, refresh: () => { if (gid) reload(); else loadList(); },
        destroy() { alive = false; clearTimeout(nowT); window.removeEventListener('grupa-changed', onChanged); window.removeEventListener('focus', onFocus); },
    };
}

return { mount, panel, publicPanel, coverHtml, pick, addTo, say, play: playGrupa };
})();
