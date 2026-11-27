/* plugins_host.js — Explore → Plug-ins: the list of plug-ins, and the one that is open.

   A plug-in runs in a sandboxed frame (plugins.py serves it, with a content rule
   that lets it load only its own files and send nothing anywhere). This page is
   the only way it can learn or do anything: it asks by message, and this page
   answers — only with what the plug-in's plugin.json named and its person agreed
   to by switching it on (plugins.py checks that again on every answer).

   window.PluginsHost.mount(host, { openRoom(handle), openCrate(pull), helpUrl })
     → { refresh(), escape(), leave(), state() } */
window.PluginsHost = (function () {
    'use strict';
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    let host, opts, list = [], folder = '', open = null, frame = null, said = '', busy = false, note = '';
    const BIN = /Win/.test(navigator.platform || '') ? 'Recycle Bin' : 'Trash';

    async function call(url, method, body) {
        try {
            const r = await fetch(url, method ? { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) } : undefined);
            const d = await r.json().catch(() => ({}));
            return { ok: r.ok, status: r.status, d };
        } catch (_) { return { ok: false, status: 0, d: { error: 'The app can’t be reached.' } }; }
    }

    function theme() {
        const cs = getComputedStyle(document.body), out = {};
        for (const k of ['bg', 'text', 'muted', 'border', 'border2', 'red', 'surface', 'surface2'])
            out[k] = (cs.getPropertyValue('--' + k) || '').trim();
        return out;
    }
    function hello() {
        if (!frame || !open) return;
        frame.contentWindow.postMessage({ mr: 'host', type: 'hello', theme: theme(),
            scheme: getComputedStyle(document.documentElement).colorScheme || '',
            plugin: { id: open.id, name: open.name, version: open.version, wants: open.wants } }, '*');
    }

    async function load() {
        const r = await call('/api/plugins');
        list = r.ok ? (r.d.plugins || []) : [];
        folder = r.ok ? r.d.folder || '' : '';
        if (open && !list.some(p => p.id === open.id && p.on)) close();
        paint();
    }

    function card(p) {
        const mark = p.source === 'yours' ? '<span class="pl-mark pl-mark--yours">yours · not reviewed</span>' : '<span class="pl-mark">built in</span>';
        const out = p.source === 'yours' ? `<button type="button" class="pl-link pl-link--out" data-act="remove">Remove</button>` : '';
        if (p.error) return `<div class="pl-card is-broken" data-id="${esc(p.id)}"><div class="pl-card__n">${esc(p.name)}</div>${mark}
            <p class="pl-card__d">This one can’t run: ${esc(p.error)}.</p>${out ? `<div class="pl-card__acts">${out}</div>` : ''}</div>`;
        const reads = (p.wants_said || []).length ? `<p class="pl-card__w"><span>It may read</span>${p.wants_said.map(esc).join('; ')}.</p>`
                                                  : `<p class="pl-card__w"><span>It may read</span>nothing — it only shows things.</p>`;
        return `<div class="pl-card${p.on ? ' is-on' : ''}${open && open.id === p.id ? ' is-open' : ''}" data-id="${esc(p.id)}">
            <div class="pl-card__n">${esc(p.name)}</div>
            <div class="pl-card__s">${p.author ? 'by ' + esc(p.author) : ''}${p.version ? ' · ' + esc(p.version) : ''}</div>${mark}
            ${p.description ? `<p class="pl-card__d">${esc(p.description)}</p>` : ''}${reads}
            <div class="pl-card__acts">
              ${p.on ? `<button type="button" class="pl-btn pl-btn--go" data-act="open">Open</button>
                        <button type="button" class="pl-btn" data-act="off">Switch off</button>`
                     : `<button type="button" class="pl-btn" data-act="on" title="Switching it on lets it read what is listed above">Switch on</button>`}
              ${out}
            </div></div>`;
    }

    function paint() {
        const built = list.filter(p => p.source !== 'yours'), mine = list.filter(p => p.source === 'yours');
        const stage = host.querySelector('.pl-stage');
        if (open && frame && frame.isConnected && stage && stage.dataset.open === String(open.id)) {
            // the same plug-in is still open: only the list is drawn again — its frame stays where it is
            const side = document.createElement('div');
            side.innerHTML = listHtml(built, mine);
            host.querySelector('.pl-list').replaceWith(side.firstElementChild);
            const say = host.querySelector('.pl-bar__say'); if (say) say.textContent = said;
            return;
        }
        host.innerHTML = listHtml(built, mine) + `
          <section class="pl-stage" aria-label="The open plug-in" data-open="${open ? esc(String(open.id)) : ''}">
            ${open ? `<div class="pl-bar"><span class="pl-bar__n">${esc(open.name)}</span><span class="pl-bar__say" role="status">${esc(said)}</span>
                       <button type="button" class="pl-x" data-act="close" title="Close" aria-label="Close">✕</button></div>
                       <div class="pl-frame-wrap"></div>`
                   : ''}
          </section>`;
        if (open) {
            if (!frame) {
                frame = document.createElement('iframe');
                frame.className = 'pl-frame';
                frame.setAttribute('sandbox', 'allow-scripts');
                frame.setAttribute('referrerpolicy', 'no-referrer');
                frame.title = open.name;
                frame.src = '/plugins/frame/' + encodeURIComponent(open.id);
            }
            host.querySelector('.pl-frame-wrap').append(frame);
        }
    }

    function listHtml(built, mine) {
        return `
          <aside class="pl-list" aria-label="Plug-ins">
            ${built.length ? `<div class="pl-k">Built in</div>${built.map(card).join('')}` : ''}
            <div class="pl-k">Your own</div>
            ${mine.length ? mine.map(card).join('') : '<p class="pl-none">None yet.</p>'}
            <div class="pl-foot">
              <button type="button" class="pl-btn pl-btn--go" data-act="add" title="Choose a plug-in's folder: the app takes a copy of it">Add a plug-in…</button>
              <button type="button" class="pl-btn" data-act="again" title="Take a fresh copy of each plug-in you added">Look again</button>
              <button type="button" class="pl-btn" data-act="folder">Show the folder</button>
              ${opts.helpUrl ? `<button type="button" class="pl-link" data-act="help">How to make one${opts.helpUrl.charAt(0) === '/' ? '' : ' ↗'}</button>` : ''}
            </div>
            <p class="pl-note" role="status">${esc(note)}</p>
          </aside>`;
    }

    function close() {
        if (frame) frame.remove();
        frame = null; open = null; said = '';
    }
    function reopen() {                       // the open plug-in's files changed: start it again
        if (!open) return;
        open = list.find(x => x.id === open.id) || open;
        if (frame) { frame.remove(); frame = null; }
        const stage = host.querySelector('.pl-stage'); if (stage) stage.dataset.open = '';
    }
    function say(words) {
        note = words || '';
        const el = host.querySelector('.pl-note'); if (el) el.textContent = note;
    }

    async function onClick(e) {
        const b = e.target.closest('[data-act]');
        if (!b || busy) return;
        const cardEl = b.closest('[data-id]'), id = cardEl ? cardEl.dataset.id : null;
        const p = list.find(x => x.id === id);
        const act = b.dataset.act;
        if (act === 'open' && p) { if (!open || open.id !== p.id) { close(); open = p; } paint(); return; }
        if (act === 'close') { close(); paint(); return; }
        if (act === 'on' || act === 'off') {
            busy = true; b.disabled = true;
            const r = await call('/api/plugins/' + encodeURIComponent(id), 'POST', { on: act === 'on' });
            busy = false;
            if (r.ok) list = r.d.plugins || list;
            if (act === 'off' && open && open.id === id) close();
            if (act === 'on' && p) { close(); open = list.find(x => x.id === id) || null; }
            paint(); return;
        }
        if (act === 'folder') { await call('/api/plugins/folder/show', 'POST'); return; }
        if (act === 'add') {
            busy = true; b.disabled = true; say('Choose the plug-in’s folder…');
            const r = await call('/api/plugins/folder/add', 'POST', {});
            busy = false; b.disabled = false;
            if (r.ok && r.d.cancelled) { say(''); return; }
            if (!r.ok) { say('It wasn’t added: ' + (r.d.error || 'something went wrong') + '.'); return; }
            list = r.d.plugins || list;
            const left = r.d.left_out || [];
            say(`${r.d.name || r.d.id} is added.` + (left.length ? ` Left out, as a plug-in can’t use them: ${left.slice(0, 4).join(', ')}${left.length > 4 ? '…' : ''}.` : ''), true);
            if (open && open.id === r.d.id) reopen();
            paint(); return;
        }
        if (act === 'again') {
            busy = true;
            const r = await call('/api/plugins/folder/again', 'POST', {});
            busy = false;
            if (r.ok) {
                list = r.d.plugins || list;
                const notes = Object.entries(r.d.notes || {}).map(([id, why]) => `${(list.find(x => x.id === id) || {}).name || id}: ${why}.`);
                note = notes.join(' ');
                if (open && !list.some(x => x.id === open.id && x.on)) close(); else if (open) reopen();
                paint();
            } else await load();
            return;
        }
        if (act === 'remove' && id) {
            const name = p ? p.name : id;
            if (!confirm(p && p.added ? `Remove ${name} from the Music Room? The app’s copy goes to the ${BIN}; the folder you added it from stays where it is.`
                                      : `Remove ${name} from the Music Room? Its folder goes to the ${BIN}.`)) return;
            busy = true;
            const r = await call('/api/plugins/' + encodeURIComponent(id) + '/remove', 'POST', {});
            busy = false;
            if (open && open.id === id) close();
            if (r.ok) { list = r.d.plugins || list; say(''); paint(); } else say('It wasn’t removed: ' + (r.d.error || 'something went wrong') + '.');
            return;
        }
        if (act === 'help' && opts.helpUrl) {
            if (opts.helpUrl.charAt(0) === '/') (window.rtGo || (h => { location.href = h; }))(opts.helpUrl);   // a page of the app's own
            else call('/api/open-url', 'POST', { url: opts.helpUrl });
        }
    }

    function reply(m, ok, data, error) {
        if (frame) frame.contentWindow.postMessage({ mr: 'host', type: 'reply', id: m.id, ok, data, error }, '*');
    }
    async function onMessage(e) {
        if (!frame || e.source !== frame.contentWindow || !open) return;
        const m = e.data || {};
        if (m.mr !== 'plugin' || m.plugin !== open.id) return;
        if (m.type === 'hello') return hello();
        if (m.type !== 'call') return;
        const a = m.args || {}, pid = encodeURIComponent(open.id);
        if (m.fn === 'data') {
            const r = await call(`/api/plugins/${pid}/data/${encodeURIComponent(a.what || '')}`);
            return reply(m, r.ok, r.d, r.d.error);
        }
        if (m.fn === 'crate') {
            const r = await call(`/api/plugins/${pid}/crate`, 'POST', { ids: a.ids || [], title: a.title || '' });
            if (r.ok && r.d.pull) {
                reply(m, true, { ok: true, count: r.d.pull.count, left: r.d.left });
                if (opts.openCrate) opts.openCrate(r.d.pull);
                return;
            }
            return reply(m, false, null, r.d.error || 'No crate could be made.');
        }
        if (m.fn === 'openRoom') { if (opts.openRoom && /^[a-z0-9-]{1,80}$/.test(a.handle || '')) opts.openRoom(a.handle); return reply(m, true, {}); }
        if (m.fn === 'say') { said = String(a.text || '').slice(0, 200); const s = host.querySelector('.pl-bar__say'); if (s) s.textContent = said; return reply(m, true, {}); }
        reply(m, false, null, 'A plug-in can’t ask for that.');
    }

    function mount(h, o) {
        host = h; opts = o || {};
        host.classList.add('pl');
        host.addEventListener('click', onClick);
        addEventListener('message', onMessage);
        addEventListener('mr-theme-change', hello);
        load();
        return {
            refresh: load,
            escape: () => { if (open) { close(); paint(); return true; } return false; },
            leave: () => {},
            state: () => ({ open: open && open.id, list: list.map(p => ({ id: p.id, on: p.on, source: p.source, error: p.error || '' })) }),
        };
    }
    return { mount };
})();
