// theme.js — the theme switch. A small ◐ in the nav opens a list: the built-in
// themes, "match the system", your own imported themes, import / export.
// The server already rendered the chosen theme into the page (no flash);
// this applies a change instantly and remembers it server-side (the desktop
// shell wipes localStorage, so settings are the memory).
(function () {
  let THEMES = null, CURRENT = 'dark';
  const $ = (s, r) => (r || document).querySelector(s);
  // a theme's name comes from a file someone else may have made: it goes on the page as text
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function applyVars(theme) {
    const root = document.documentElement;
    let style = document.getElementById('mr-theme');
    if (!theme || theme.id === 'dark') { if (style) style.remove(); dispatchEvent(new CustomEvent('mr-theme-change', { detail: theme })); return; }
    const base = Object.assign({}, (THEMES.find(t => t.id === 'dark') || {}).vars || {}, theme.vars || {});
    const body = Object.entries(base).map(([k, v]) => `--${k}:${v};`).join('');
    if (!style) { style = document.createElement('style'); style.id = 'mr-theme'; document.head.appendChild(style); }
    style.textContent = `:root:root,:root:root body{${body}color-scheme:${theme.scheme || 'dark'};}`;
    void root.offsetHeight;
    dispatchEvent(new CustomEvent('mr-theme-change', { detail: theme }));
  }
  function resolve(id) {
    if (id === 'system') id = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    return THEMES.find(t => t.id === id) || THEMES[0];
  }
  async function load() {
    let d = null;
    try { d = await (await fetch('/api/themes')).json(); } catch (_) {}
    if (!d || !Array.isArray(d.themes)) return;      // no list → no key (a key that opens nothing is worse)
    THEMES = d.themes; CURRENT = d.current || 'dark';
    if (CURRENT === 'system') applyVars(resolve('system'));
    matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (CURRENT === 'system') applyVars(resolve('system')); });
    mount();
  }
  async function choose(id) {
    CURRENT = id; applyVars(resolve(id)); render();
    await fetch('/api/themes/current', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
  }
  async function importFile(file) {
    let obj;
    try { obj = JSON.parse(await file.text()); } catch (_) { alert('That file is not JSON.'); return; }
    const r = await fetch('/api/themes/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) });
    const d = await r.json();
    if (!r.ok) { alert(d.error || 'That theme could not be read.'); return; }
    THEMES = d.themes; await choose(d.theme.id);
  }
  function exportCurrent() {
    const t = resolve(CURRENT);
    const out = { name: t.name + (t.id.startsWith('custom-') ? '' : ' (copy)'), scheme: t.scheme, author: '', vars: Object.assign({}, (THEMES.find(x => x.id === 'dark') || {}).vars, t.vars) };
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' }));
    a.download = ((t.name || 'theme').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'theme') + '.musicroom-theme.json';
    a.click();
  }
  async function remove(id) {
    if (!confirm('Delete this theme?')) return;
    const d = await (await fetch('/api/themes/' + encodeURIComponent(id), { method: 'DELETE' })).json().catch(() => ({}));
    if (!Array.isArray(d.themes)) return;          // refused (not signed in yet): the list stays as it is
    THEMES = d.themes; if (CURRENT === id) await choose('dark'); else render();
  }

  function mount() {
    const css = document.createElement('style');
    css.textContent = `
      .mr-theme{position:relative;display:inline-block;font-family:Inter,system-ui,sans-serif}
      .mr-theme__btn{appearance:none;cursor:pointer;width:30px;height:30px;border-radius:50%;border:1px solid var(--border,rgba(255,255,255,.15));background:none;color:var(--muted,#9a8c6c);font-size:.95rem;line-height:1;display:inline-flex;align-items:center;justify-content:center;transition:color .2s,border-color .2s}
      .mr-theme__btn:hover{color:var(--text,#efe6cf);border-color:var(--gold,#f5e6b0)}
      .mr-theme--fixed{position:fixed;top:14px;right:16px;z-index:9500}
      .mr-theme__menu{display:none;position:absolute;right:0;top:calc(100% + 8px);min-width:230px;background:var(--surface2,#221c15);border:1px solid var(--border2,rgba(255,255,255,.2));border-radius:12px;padding:6px;box-shadow:0 18px 46px rgba(0,0,0,.45);z-index:9600}
      .mr-theme.open .mr-theme__menu{display:block}
      .mr-theme__row{display:flex;align-items:center;gap:8px;width:100%;padding:8px 10px;border:none;border-radius:8px;background:none;color:var(--text,#efe6cf);font:inherit;font-size:.84rem;cursor:pointer;text-align:left}
      .mr-theme__row:hover{background:var(--accent-dim,rgba(255,255,255,.08))}
      .mr-theme__row .dot{width:9px;height:9px;border-radius:50%;border:1px solid var(--border2,rgba(255,255,255,.3));flex:none}
      .mr-theme__row.on .dot{background:var(--gold,#f5e6b0);border-color:var(--gold,#f5e6b0)}
      .mr-theme__row .sw{width:16px;height:16px;border-radius:4px;border:1px solid var(--border2,rgba(255,255,255,.2));flex:none}
      .mr-theme__row .x{margin-left:auto;color:var(--muted2,#7d7257);font-size:.8rem}
      .mr-theme__row .x:hover{color:var(--danger,#c4574a)}
      .mr-theme__sep{height:1px;background:var(--border,rgba(255,255,255,.1));margin:6px 4px}
      .mr-theme__lbl{font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted2,#7d7257);padding:6px 10px 2px}
      `;
    document.head.appendChild(css);
    const host = document.createElement('div');
    host.className = 'mr-theme';
    host.innerHTML = `<button class="mr-theme__btn" title="Theme" aria-label="Theme">◐</button><div class="mr-theme__menu"></div><input type="file" accept=".json,application/json" style="display:none">`;
    // where it lives: the nav; else a page's own top bar (public room, intro,
    // login); else nowhere — the 3D room is unthemed and already crowded
    // the front door has no bar: its key sits alone in the page's top corner, and offers the looks only
    const door = document.body.classList.contains('lg');
    const slot = door ? document.body : ($('.nav') || $('.pr-bar') || $('.in-top'));
    if (!slot) return;
    if (door) { host.classList.add('mr-theme--fixed'); host.dataset.plain = '1'; }
    else host.style.marginLeft = '14px';
    if (slot.classList.contains('in-top')) slot.insertBefore(host, slot.lastElementChild); else slot.appendChild(host);
    $('.mr-theme__btn', host).addEventListener('click', e => { e.stopPropagation(); host.classList.toggle('open'); });
    document.addEventListener('click', () => host.classList.remove('open'));
    $('input', host).addEventListener('change', e => { if (e.target.files[0]) importFile(e.target.files[0]); e.target.value = ''; });
    window.__mrThemeHost = host;
    render();
  }
  function render() {
    const host = window.__mrThemeHost; if (!host || !THEMES) return;
    const menu = $('.mr-theme__menu', host);
    const row = (id, name, sw, removable) => `<button class="mr-theme__row ${CURRENT === id ? 'on' : ''}" data-id="${esc(id)}"><span class="dot"></span>${sw ? `<span class="sw" style="background:${esc(sw)}"></span>` : ''}<span>${esc(name)}</span>${removable && !host.dataset.plain ? `<span class="x" data-del="${esc(id)}" title="delete">✕</span>` : ''}</button>`;
    const builtIn = THEMES.filter(t => !t.id.startsWith('custom-')), mine = THEMES.filter(t => t.id.startsWith('custom-'));
    menu.innerHTML = builtIn.map(t => row(t.id, t.name, t.vars.bg)).join('')
      + row('system', 'Match the system', null)
      + (mine.length ? `<div class="mr-theme__sep"></div><div class="mr-theme__lbl">Yours</div>` + mine.map(t => row(t.id, t.name, t.vars.bg, true)).join('') : '')
      + (host.dataset.plain ? '' : `<div class="mr-theme__sep"></div><button class="mr-theme__row" data-act="import">Import a theme…</button><button class="mr-theme__row" data-act="export">Export this theme</button>`);
    menu.querySelectorAll('[data-del]').forEach(x => x.addEventListener('click', e => { e.stopPropagation(); remove(x.dataset.del); }));
    menu.querySelectorAll('[data-id]').forEach(b => b.addEventListener('click', e => { e.stopPropagation(); choose(b.dataset.id); }));
    const imp = menu.querySelector('[data-act="import"]'), exp = menu.querySelector('[data-act="export"]');
    if (imp) imp.addEventListener('click', e => { e.stopPropagation(); $('input', host).click(); });
    if (exp) exp.addEventListener('click', e => { e.stopPropagation(); exportCurrent(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load); else load();
})();
