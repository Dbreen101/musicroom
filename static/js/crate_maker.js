// =============================================================
// crate_maker.js — a seller's own crates (My Public Room → Crates).
//
// A crate is up to 25 records from the shop — the seller's own or anyone's —
// in the seller's order, with a line on any of them. Put OUT, shoppers in
// Explore → Record shopping may be handed it, whole, signed with the seller's
// name (record_shop.js shows it; gr_shop.py keeps it). A crate can be made of
// other crates: "pull in a crate" brings its records in, as many as fit.
// Every change is saved as it is made.
//
//   CrateMaker.mount(host)
//
// The words are functional; David coins the real ones.
// =============================================================
window.CrateMaker = (function () {
'use strict';
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const JSONH = { 'Content-Type': 'application/json' };
async function call(url, method, body) {
    try {
        const r = await fetch(url, { method: method || 'GET', headers: body ? JSONH : undefined, body: body ? JSON.stringify(body) : undefined });
        return { ok: r.ok, d: await r.json().catch(() => ({})) };
    } catch (_) { return { ok: false, d: { error: 'The app can’t be reached.' } }; }
}
const art = r => r.has_art ? `/api/gr/art/${r.id}?v=${r.art_v || 0}` : '';
const thumb = r => `<span class="rs-thumb">${art(r) ? `<img src="${esc(art(r))}" alt="" loading="lazy" onerror="this.remove()">` : ''}<span>${esc(((r.title || '?').trim()[0] || '?').toUpperCase())}</span></span>`;

let host = null, D = null, cur = null, found = [], out = null, said = '', saveTimer = 0, findTimer = 0, findSeq = 0, dragFrom = -1;

async function load() {
    const r = await call('/api/gr/shop/my/crates');
    D = r.ok ? r.d : { error: r.d.error || 'Your crates can’t be read just now.', crates: [], can_make: false, max: 25 };
    if (cur) cur = (D.crates || []).find(c => c.id === cur.id) || null;
    paint();
}
function paint() {
    if (!host) return;
    if (!D) { host.innerHTML = '<p class="rs-quiet">Reading your crates…</p>'; return; }
    if (D.error) { host.innerHTML = `<p class="rs-msg">${esc(D.error)}</p>`; return; }
    if (!D.can_make) { host.innerHTML = `<p class="rs-quiet">Crates are made by people who sell records here: artists, labels and record shops. Yours is a listener’s account.</p>`; return; }
    host.innerHTML = cur ? editor() : list();
    if (cur) paintFound();
}
function list() {
    const rows = (D.crates || []).map(c => `<button type="button" class="rs-pull" data-act="open" data-id="${c.id}">
        <span><span class="rs-pull__t">${esc(c.name)}</span><span class="rs-pull__s">${c.count} ${c.count === 1 ? 'record' : 'records'} · ${c.is_out ? 'out on the shop floor' : 'not out'}</span></span>
        <span class="rs-pull__go">Open</span></button>`).join('');
    return `<div class="rs-kicker">Your crates</div>
      <p class="rs-p" style="margin-top:8px">A crate is up to ${D.max} records from the shop, yours or anyone’s, in your order, with a line on any of them. Put it out and people shopping in Explore may be handed it, signed with your name.</p>
      ${rows ? `<div class="rs-pulls">${rows}</div>` : ''}
      <div class="rs-bar"><input class="rs-input" id="cm-new" type="text" maxlength="80" placeholder="Name a new crate" autocomplete="off" style="flex:1 1 160px">
        <button type="button" class="rs-btn rs-btn--primary" data-act="new">Make it</button></div>
      <div class="rs-msg">${esc(said)}</div>`;
}
function editor() {
    const n = cur.items.length;
    return `<button type="button" class="rs-link" data-act="back">← Your crates</button>
      <input class="rs-input" id="cm-name" type="text" maxlength="80" value="${esc(cur.name)}" aria-label="The crate’s name" style="font-family:var(--f-display, serif) !important;font-size:1.5rem;margin-top:8px">
      <textarea class="rs-input" id="cm-note" rows="2" maxlength="400" placeholder="A line about this crate (optional)">${esc(cur.note || '')}</textarea>
      <div class="rs-bar" style="justify-content:space-between">
        <button type="button" class="rs-btn${cur.is_out ? ' rs-btn--primary' : ''}" data-act="out" aria-pressed="${!!cur.is_out}">${cur.is_out ? 'Out on the shop floor' : 'Put it out'}</button>
        <span class="rs-state" id="cm-saved">${esc(said)}</span>
      </div>
      <div class="rs-kicker rs-gap" style="margin-top:26px">In this crate <span>${n} of ${D.max}</span></div>
      <div class="rs-maker rs-qs">${cur.items.map((r, i) => `<div class="rs-mk" draggable="true" data-i="${i}">
          <span class="rs-grip" title="Drag to move">⋮⋮</span>${thumb(r)}
          <span style="min-width:0"><span class="rs-ans__t" style="display:block;font-size:1.05rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.title || 'Untitled')}</span>
            <span class="rs-ans__a" style="display:block;font-size:.58rem;color:var(--muted)">${esc(r.artist || '')}</span>
            <input class="rs-input" data-note="${i}" type="text" maxlength="280" placeholder="Your line on it (optional)" value="${esc(r.note || '')}" style="font-size:.74rem;padding:5px 0 !important"></span>
          <button type="button" class="rs-link" data-act="drop" data-i="${i}" title="Take it out of the crate">Out</button></div>`).join('') || '<p class="rs-quiet">Nothing in it yet.</p>'}</div>
      ${n >= D.max ? `<p class="rs-quiet">That is a full crate.</p>` : `
      <div class="rs-kicker rs-gap" style="margin-top:26px">Add a record from the shop</div>
      <input class="rs-input" id="cm-find" type="text" autocomplete="off" placeholder="A title, an artist, a label, a genre…">
      <div class="rs-found" id="cm-found"></div>
      <div class="rs-kicker rs-gap" style="margin-top:26px">Or pull in a whole crate</div>
      <div id="cm-out" style="margin-top:8px"><button type="button" class="rs-btn rs-btn--small" data-act="showout">Show the crates that are out</button></div>`}
      <div class="rs-bar" style="margin-top:30px"><button type="button" class="rs-link" data-act="delete">Take this crate away</button></div>`;
}
function paintFound() {
    const box = host.querySelector('#cm-found'); if (!box) return;
    const have = new Set(cur.items.map(r => r.id));
    box.innerHTML = found.filter(r => !have.has(r.id)).slice(0, 12).map(r => `<button type="button" class="rs-rec" data-act="add" data-id="${r.id}">${thumb(r)}
        <span><b>${esc(r.title || 'Untitled')}</b><i>${esc([r.artist, r.owner && r.owner.name, r.year].filter(Boolean).join(' · '))}</i></span></button>`).join('');
    const ob = host.querySelector('#cm-out');
    if (ob && out) ob.innerHTML = out.filter(c => c.id !== cur.id).map(c => `<button type="button" class="rs-pull" data-act="pullin" data-id="${c.id}">
        <span><span class="rs-pull__t" style="font-size:1.1rem">${esc(c.name)}</span><span class="rs-pull__s">${c.mine ? 'yours' : 'by ' + esc(c.by)} · ${c.count}</span></span><span class="rs-pull__go">Pull in</span></button>`).join('')
        || '<p class="rs-quiet">No other crates are out yet.</p>';
}
function saveSoon() {
    clearTimeout(saveTimer);
    const el = host.querySelector('#cm-saved'); if (el) el.textContent = 'saving…';
    saveTimer = setTimeout(save, 450);
}
async function save() {
    if (!cur) return;
    const sent = cur;
    const r = await call('/api/gr/shop/my/crates', 'POST', { id: cur.id, name: cur.name, note: cur.note, is_out: !!cur.is_out,
        items: cur.items.map(x => ({ id: x.id, note: x.note || '', from_crate_id: x.from_crate_id || null })) });
    if (cur !== sent) return;
    const el = host.querySelector('#cm-saved');
    if (!r.ok) { said = r.d.error || 'That wasn’t saved.'; if (r.d.error && /empty crate/i.test(r.d.error)) cur.is_out = false; if (el) el.textContent = said; else paint(); return; }
    said = 'saved'; if (el) el.textContent = said;
    const i = D.crates.findIndex(c => c.id === cur.id); if (i >= 0) D.crates[i] = Object.assign({}, cur, { count: cur.items.length });
}
function find(q) {
    clearTimeout(findTimer);
    findTimer = setTimeout(async () => {
        const mine = ++findSeq, r = await call('/api/gr/shop/search?q=' + encodeURIComponent(q));
        if (mine !== findSeq || !cur) return;
        found = (r.ok && r.d.records) || []; paintFound();
    }, q ? 220 : 0);
}
const ACTS = {
    new: async () => {
        const inp = host.querySelector('#cm-new'), name = (inp.value || '').trim(); if (!name) { inp.focus(); return; }
        const r = await call('/api/gr/shop/my/crates', 'POST', { name, items: [] });
        if (!r.ok) { said = r.d.error || 'That crate wasn’t made.'; return paint(); }
        D.crates.unshift(r.d.crate); cur = r.d.crate; said = ''; found = []; out = null; paint(); find('');
    },
    open: (t) => { cur = D.crates.find(c => c.id === +t.dataset.id) || null; said = ''; found = []; out = null; paint(); if (cur) find(''); },
    back: async () => { clearTimeout(saveTimer); await save(); cur = null; said = ''; load(); },
    out: () => { if (!cur.items.length && !cur.is_out) { said = 'Put a record in it first.'; return paint(); } cur.is_out = !cur.is_out; said = ''; paint(); saveSoon(); },
    add: (t) => { const r = found.find(x => x.id === +t.dataset.id); if (!r || cur.items.length >= D.max) return; cur.items.push(Object.assign({}, r, { note: '' })); keepTyping(); },
    drop: (t) => { cur.items.splice(+t.dataset.i, 1); if (!cur.items.length) cur.is_out = false; keepTyping(); },
    showout: async () => { const r = await call('/api/gr/shop/crates/out'); out = (r.ok && r.d.crates) || []; paintFound(); },
    pullin: (t) => {
        const c = (out || []).find(x => x.id === +t.dataset.id); if (!c) return;
        const have = new Set(cur.items.map(r => r.id));
        for (const r of c.items) { if (cur.items.length >= D.max) break; if (!have.has(r.id)) { cur.items.push(Object.assign({}, r, { from_crate_id: c.id })); have.add(r.id); } }
        keepTyping();
    },
    delete: async () => {
        if (!confirm('Take “' + cur.name + '” away? The records in it stay in the shop.')) return;
        clearTimeout(saveTimer);
        await call('/api/gr/shop/my/crates/' + cur.id, 'DELETE'); cur = null; said = ''; load();
    },
};
// repaint the editor without losing what is typed in the find line
function keepTyping() {
    const q = (host.querySelector('#cm-find') || {}).value || '';
    paint(); saveSoon();
    const f = host.querySelector('#cm-find'); if (f) f.value = q;
    const sv = host.querySelector('#cm-saved'); if (sv) sv.textContent = 'saving…';
}
function mount(h) {
    host = h; host.classList.add('rs');
    host.addEventListener('click', e => { const t = e.target.closest('[data-act]'); if (t && host.contains(t) && ACTS[t.dataset.act]) ACTS[t.dataset.act](t); });
    host.addEventListener('input', e => {
        const t = e.target; if (!cur) return;
        if (t.id === 'cm-name') { cur.name = t.value; if (t.value.trim()) saveSoon(); }
        if (t.id === 'cm-note') { cur.note = t.value; saveSoon(); }
        if (t.id === 'cm-find') find(t.value);
        if (t.dataset.note != null) { cur.items[+t.dataset.note].note = t.value; saveSoon(); }
    });
    host.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'cm-new') { e.preventDefault(); ACTS.new(); } });
    // drag a record to another place in the crate
    host.addEventListener('dragstart', e => { const row = e.target.closest('.rs-mk'); if (!row) return; dragFrom = +row.dataset.i; row.classList.add('drag'); try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(dragFrom)); } catch (_) {} });
    host.addEventListener('dragover', e => { const row = e.target.closest('.rs-mk'); if (!row || dragFrom < 0) return; e.preventDefault(); host.querySelectorAll('.rs-mk.over').forEach(x => x.classList.remove('over')); row.classList.add('over'); });
    host.addEventListener('drop', e => { const row = e.target.closest('.rs-mk'); if (!row || dragFrom < 0) return; e.preventDefault(); const to = +row.dataset.i; if (to !== dragFrom) { const [it] = cur.items.splice(dragFrom, 1); cur.items.splice(to, 0, it); keepTyping(); } dragFrom = -1; });
    host.addEventListener('dragend', () => { dragFrom = -1; host.querySelectorAll('.rs-mk.drag, .rs-mk.over').forEach(x => x.classList.remove('drag', 'over')); });
    paint(); load();
    return { refresh: load };
}
return { mount };
})();
