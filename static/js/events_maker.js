// events_maker.js — event pages, in My Public Room → Events (2026-11-26).
// For experience creator and venue accounts (gr_happenings.py on the rooms server). A page is
// a draft until it is published; published, it shows in the public room and in what is
// coming up. Ticket sales and private events are not built: the two ticks are placeholders.
//
//   EventsMaker.mount(host, { assets: () => [...] })   → { refresh() }
window.EventsMaker = (function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const day = s => { const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString('en-IE', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) + ' · ' + d.toLocaleTimeString('en-IE', { hour: '2-digit', minute: '2-digit' }); };
  async function ask(sub, body, method) {
    const r = await fetch('/api/gr/people/' + sub, body === undefined && !method ? {} : { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    return { ok: r.ok, d: await r.json().catch(() => ({})) };
  }
  function mount(host, opts) {
    opts = opts || {};
    let list = [], cur = null, notYet = '';
    host.classList.add('pp');
    async function refresh() {
      const r = await ask('my/happenings');
      if (!r.ok || !r.d.can) { host.innerHTML = `<div class="hint">${esc(r.d.error || 'Event pages are for experience creator and venue accounts.')}</div>`; return; }
      list = r.d.happenings || []; notYet = r.d.not_yet || '';
      paint();
    }
    function paint(say, bad) {
      const e = cur || {}, assets = (opts.assets ? opts.assets() : []) || [];
      host.innerHTML = `
        <div class="sec-h">${cur && cur.id ? 'This event' : 'A new event'}</div>
        <div class="f"><label for="ev-title">Name</label><input type="text" id="ev-title" maxlength="160" value="${esc(e.title || '')}"></div>
        <div class="f"><label for="ev-start">Starts</label><input type="datetime-local" id="ev-start" value="${esc(e.starts_at || '')}"></div>
        <div class="f"><label for="ev-end">Ends (if you like)</label><input type="datetime-local" id="ev-end" value="${esc(e.ends_at || '')}"></div>
        <div class="f"><label for="ev-place">Where</label><input type="text" id="ev-place" maxlength="160" value="${esc(e.place || '')}"></div>
        <div class="f"><label for="ev-about">About it</label><textarea id="ev-about" maxlength="6000" style="min-height:90px">${esc(e.about || '')}</textarea></div>
        <div class="f"><label for="ev-link">Link (if you like)</label><input type="text" id="ev-link" placeholder="https://" value="${esc(e.link || '')}"></div>
        ${assets.length ? `<div class="f"><label for="ev-pic">Picture (from Images)</label><select id="ev-pic"><option value="">none</option>${assets.map(a =>
          `<option value="${a.id}"${a.id === e.asset_id ? ' selected' : ''}>${esc(a.label || 'picture ' + a.id)}</option>`).join('')}</select></div>` : ''}
        <div class="ev-soon"><label><input type="checkbox" disabled> Sell tickets</label><label><input type="checkbox" disabled> Private event</label>${esc(notYet)}</div>
        <div class="f pp-keys">
          <button class="gr-btn gr-btn--primary gr-btn--small" data-ev="publish">${e.status === 'published' ? 'Save' : 'Publish'}</button>
          <button class="gr-btn gr-btn--small" data-ev="draft">${e.status === 'published' ? 'Back to a draft' : 'Save as a draft'}</button>
          ${cur && cur.id ? '<button class="gr-btn gr-btn--small" data-ev="new">New event</button><button class="gr-btn gr-btn--small" data-ev="remove">Remove</button>' : ''}
          <span class="pp-say${bad ? ' bad' : ''}">${esc(say || '')}</span>
        </div>
        <div class="sec-h" style="margin-top: var(--gr-s4)">Your events</div>
        <div class="ev-list">${list.map(x => `<div class="ev-item"><div class="t" data-ev-open="${x.id}"><b>${esc(x.title)}</b><span>${esc(day(x.starts_at))}${x.place ? ' · ' + esc(x.place) : ''}</span></div>
          <span class="pp-mark${x.status === 'published' ? '' : ' red'}">${x.status === 'published' ? (x.past ? 'past' : 'published') : 'draft'}</span></div>`).join('') || '<div class="hint">None yet.</div>'}</div>`;
    }
    host.addEventListener('click', async ev => {
      const open = ev.target.closest('[data-ev-open]');
      if (open) { cur = list.find(x => String(x.id) === open.dataset.evOpen) || null; return paint(); }
      const b = ev.target.closest('[data-ev]'); if (!b) return;
      const what = b.dataset.ev;
      if (what === 'new') { cur = null; return paint(); }
      if (what === 'remove') {
        if (!confirm('Remove this event page?')) return;
        await ask('my/happenings/' + cur.id, undefined, 'DELETE'); cur = null; await refresh(); if (opts.changed) opts.changed(); return;
      }
      const v = id => { const el = host.querySelector('#' + id); return el ? el.value : ''; };
      const body = { title: v('ev-title'), starts_at: v('ev-start').slice(0, 16), ends_at: v('ev-end').slice(0, 16), place: v('ev-place'), about: v('ev-about'),
                     link: v('ev-link'), asset_id: v('ev-pic') || null, status: what === 'publish' ? 'published' : 'draft' };
      cur = Object.assign({}, cur || {}, body);            // (what was typed stays if the server says no)
      const r = await ask('my/happenings' + (cur.id ? '/' + cur.id : ''), body);
      if (!r.ok) return paint(r.d.error || 'That wasn’t saved.', true);
      cur = r.d.happening; await refresh();
      paint(cur.status === 'published' ? 'Published.' : 'Saved as a draft.');
      if (opts.changed) opts.changed();
    });
    refresh();
    return { refresh };
  }
  return { mount };
})();
