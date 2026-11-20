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
    let host, opts, list = [], folder = '', open = null, frame = null, said = '', busy = false;

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
        if (p.error) return `<div class="pl-card is-broken"><div class="pl-card__n">${esc(p.name)}</div>${mark}
            <p class="pl-card__d">This one can’t run: ${esc(p.error)}.</p></div>`;
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
            </div></div>`;
    }

    function paint() {
        const built = list.filter(p => p.source !== 'yours'), mine = list.filter(p => p.source === 'yours');
        host.innerHTML = `
          <aside class="pl-list" aria-label="Plug-ins">
            <p class="pl-lede">Ways of exploring the music here, made by people who use the Music Room. Each one runs in a sealed box: it sees only what it says it reads, and it can’t send anything anywhere.</p>
            ${built.length ? `<div class="pl-k">Built in</div>${built.map(card).join('')}` : ''}
            <div class="pl-k">Your own</div>
            ${mine.length ? mine.map(card).join('') : '<p class="pl-none">None yet. A plug-in is a small folder; put it in your plug-ins folder and look again.</p>'}
            <div class="pl-foot">
              <button type="button" class="pl-btn" data-act="folder">Show the folder</button>
              <button type="button" class="pl-btn" data-act="again">Look again</button>
              ${opts.helpUrl ? `<button type="button" class="pl-link" data-act="help">How to make one ↗</button>` : ''}
            </div>
          </aside>
          <section class="pl-stage" aria-label="The open plug-in">
            ${open ? `<div class="pl-bar"><span class="pl-bar__n">${esc(open.name)}</span><span class="pl-bar__say" role="status">${esc(said)}</span>
                       <button type="button" class="pl-x" data-act="close" title="Close" aria-label="Close">✕</button></div>
                       <div class="pl-frame-wrap"></div>`
                   : `<div class="pl-empty">${list.some(p => p.on) ? 'Open a plug-in from the list.' : 'Switch a plug-in on to try it.'}</div>`}
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

    function close() {
        if (frame) frame.remove();
        frame = null; open = null; said = '';
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
        if (act === 'again') { await load(); return; }
        if (act === 'help' && opts.helpUrl) { call('/api/open-url', 'POST', { url: opts.helpUrl }); }
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
