/* plugin_runtime.js — what a plug-in has to work with, inside its box.

   Loaded before a plug-in's own script, in its frame (plugins.py: plugin_frame).
   The frame can't reach the network or the app; everything comes through the
   page around it (static/js/plugins_host.js), and only what the plug-in's
   plugin.json asked for and its person agreed to.

     await MusicRoom.ready                  → { plugin, theme }   (also sets the theme's colours on :root)
     await MusicRoom.catalogue()            → [record for sale…]  (wants: "catalogue")
     await MusicRoom.rooms()                → [public room…]      (wants: "rooms")
     await MusicRoom.grupai()               → [public grúpa…]     (wants: "grupai")
     await MusicRoom.library()              → [your own record…]  (wants: "library")
     await MusicRoom.makeCrate(ids, title)  → { ok, count } — up to 25 records for sale become a crate in
                                              Record shopping (one of today's three), with your plug-in's name on it
     MusicRoom.openRoom(handle)             open someone's music room
     MusicRoom.say(text)                    a short line under the plug-in's bar
     MusicRoom.cover(record, size)          the address of a record's cover (for <img src>), or ''
     MusicRoom.el(tag, attrs, ...children)  a small helper for making elements (text is always text, never HTML)

   docs/PLUGINS.md says the rest. */
(function () {
    'use strict';
    const meta = n => (document.querySelector(`meta[name="${n}"]`) || {}).content || '';
    const ORIGIN = meta('mr-origin'), PLUGIN = meta('mr-plugin');
    let seq = 0;
    const waiting = new Map();
    let readyDone;
    const ready = new Promise(r => { readyDone = r; });

    function call(fn, args) {
        return new Promise((resolve, reject) => {
            const id = ++seq;
            waiting.set(id, { resolve, reject });
            parent.postMessage({ mr: 'plugin', type: 'call', plugin: PLUGIN, id, fn, args: args || {} }, '*');
            setTimeout(() => { if (waiting.has(id)) { waiting.delete(id); reject(new Error('The app didn’t answer.')); } }, 30000);
        });
    }
    addEventListener('message', e => {
        if (e.source !== parent) return;
        const m = e.data || {};
        if (m.mr !== 'host') return;
        if (m.type === 'hello') {
            const root = document.documentElement.style;
            for (const k of Object.keys(m.theme || {})) if (/^[a-z0-9-]+$/.test(k)) root.setProperty('--' + k, String(m.theme[k]));
            document.documentElement.dataset.scheme = m.scheme || '';
            readyDone({ plugin: m.plugin || {}, theme: m.theme || {} });
            return;
        }
        if (m.type === 'reply' && waiting.has(m.id)) {
            const w = waiting.get(m.id); waiting.delete(m.id);
            if (m.ok) w.resolve(m.data); else w.reject(new Error(m.error || 'That didn’t work.'));
        }
    });

    function el(tag, attrs) {
        const node = document.createElement(tag);
        if (attrs) for (const k of Object.keys(attrs)) {
            const v = attrs[k];
            if (v == null || v === false) continue;
            if (k === 'class') node.className = v;
            else if (k === 'text') node.textContent = v;
            else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
            else node.setAttribute(k, v === true ? '' : String(v));
        }
        for (let i = 2; i < arguments.length; i++) {
            const kid = arguments[i];
            if (kid == null || kid === false) continue;
            (Array.isArray(kid) ? kid : [kid]).forEach(x => { if (x != null && x !== false) node.append(x.nodeType ? x : document.createTextNode(String(x))); });
        }
        return node;
    }

    window.MusicRoom = Object.freeze({
        ready,
        catalogue: () => call('data', { what: 'catalogue' }).then(d => d.records || []),
        rooms: () => call('data', { what: 'rooms' }).then(d => d.rooms || []),
        grupai: () => call('data', { what: 'grupai' }).then(d => d.grupai || []),
        library: () => call('data', { what: 'library' }).then(d => d.records || []),
        makeCrate: (ids, title) => call('crate', { ids: (ids || []).filter(Number.isInteger).slice(0, 200), title: String(title || '') }),
        openRoom: handle => call('openRoom', { handle: String(handle || '') }),
        say: text => call('say', { text: String(text || '').slice(0, 200) }),
        cover: (r, size) => !r || !r.has_cover ? '' :
            (r.seller !== undefined || r.price_cents !== undefined) ? `${ORIGIN}/api/gr/art/${+r.id}`
                                                                     : `${ORIGIN}/api/artwork/${+r.id}${size ? '?size=' + (+size) : ''}`,
        el,
    });
    parent.postMessage({ mr: 'plugin', type: 'hello', plugin: PLUGIN }, '*');
})();
