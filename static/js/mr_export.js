// =============================================================
// mr_export.js — one Export pop-up, reachable from anywhere, + a tiny
// generic right-click context menu. Both are REGISTRIES so we can add
// destinations / menu items over time without touching every page.
//
//   MRExport.open({type, id, label})   — open the Export hub for a thing
//   MRExport.registerDestination(dst)  — add an export target
//   MRMenu.open(x, y, items)           — show a context menu at x,y
//
// SAFETY: every built-in export COPIES. Originals always stay in the
// library. "Move" (removing from here) is deliberately NOT wired yet — it
// needs the copy→verify→recoverable-trash path + a backup, and is gated.
// =============================================================
(function () {
'use strict';

// ── exportable kinds the scoped backend (folder / USB) understands today ──
const SCOPES = ['place', 'pile', 'structure'];

// ── destination registry — extensible; order = display order ──────────────
const DESTS = [
  { id: 'folder', label: 'A folder on this laptop', sub: 'Copy, or move with safeguards',
    accepts: t => SCOPES.includes(t.type) || t.type === 'tracks',
    run: async (t, ui) => {
      if (typeof window.mrChoosePath !== 'function') { ui.error('folder picker unavailable here'); return; }
      const m = exportMode;
      const verb = m === 'copy' ? 'Copy' : (m === 'move_out' ? 'Move out of the Room' : 'Relocate');
      ui.status('Choose where to put it…');
      const dest = await window.mrChoosePath('folder', '', verb + ' “' + t.label + '” into…');
      if (!dest) { ui.status(''); return; }
      if (m !== 'copy') {           // a move touches originals — confirm in plain words first
        const msg = m === 'move_out'
          ? 'Move “' + t.label + '” OUT of your Music Room?\n\nThe files are copied to:\n' + dest +
            '\n\nThen the originals go to your recoverable “Removed from Music Room” folder, and these tracks leave your library (you can restore them anytime). Nothing is hard-deleted.'
          : 'Relocate “' + t.label + '”?\n\nThe files move to:\n' + dest +
            '\n\nThe tracks STAY in your library and keep playing — they just live in the new folder now.';
        if (!confirm(msg)) { ui.status('Cancelled — nothing was moved.'); return; }
      }
      ui.busy((m === 'copy' ? 'Copying' : 'Moving') + ' “' + t.label + '” → ' + dest + ' …');
      const base = t.type === 'tracks' ? { track_ids: t.ids, label: t.label } : { scope_type: t.type, scope_id: t.id };
      const r = await fetch('/api/export/folder', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign(base, { dest, mode: m, confirm: m !== 'copy' })) }).then(r => r.json()).catch(() => null);
      if (!r || !r.ok) { ui.error((r && r.error) || 'could not export'); return; }
      if (m === 'copy')
        ui.done('Copied ' + r.copied + ' file' + (r.copied === 1 ? '' : 's') + ' into ' + r.folder
          + (r.missing ? (' · ' + r.missing + ' not on this drive') : ''));
      else
        ui.done((m === 'move_out' ? 'Moved out ' : 'Relocated ') + r.moved + ' of ' + r.copied + ' → ' + r.folder
          + (r.verify_failed ? (' · ' + r.verify_failed + ' kept (copy unverified)') : '')
          + (r.missing ? (' · ' + r.missing + ' not on this drive') : ''));
    } },
  { id: 'usb', label: 'A USB stick', sub: 'rekordbox XML + Engine DJ, sized to the stick',
    accepts: t => SCOPES.includes(t.type),
    // never navigate away from what you were doing: overlay in the room, else a new tab
    run: t => { const url = '/usb?scope=' + t.type + ':' + t.id; close();
      if (typeof window.openRoomTool === 'function') window.openRoomTool(url);
      else window.open(url, '_blank'); } },
  { id: 'rekordbox', label: 'rekordbox XML', sub: 'A playlist file to import',
    accepts: t => t.type === 'place' || t.type === 'set',
    // Saved into the exports folder + revealed in Finder. NEVER an <a download>
    // click: the native WKWebView has no download handler, so that navigates
    // to the raw XML and blanks the whole app (David hit this 2026-07-07).
    run: (t, ui) => {
      const url = (t.type === 'set' ? '/api/set/' : '/api/place/') + t.id + '/export/rekordbox?save=1';
      fetch(url).then(r => r.json()).then(r => {
        if (!r || !r.ok) { ui.done('Couldn\'t write the file' + (r && r.error ? ' — ' + r.error : '') + '.'); return; }
        ui.done('Saved ' + r.filename + ' (' + r.tracks + ' tracks) — showing it in Finder.');
        fetch('/api/reveal-path', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ path: r.path }) }).catch(() => {});
      }).catch(() => ui.done('Couldn\'t write the file — is the app still running?')); } },
  // ── extension points — more destinations slot in here over time ──
  { id: 'ableton', label: 'Ableton Live', sub: 'soon', soon: true, accepts: t => SCOPES.includes(t.type) },
  { id: 'drive',   label: 'Google Drive', sub: 'soon', soon: true, accepts: () => true },
  { id: 'showcase', label: '＋ Your showcase', sub: 'Add these to the page you share (build it in Tools → Showcase)',
    accepts: t => SCOPES.includes(t.type) || t.type === 'tracks',
    run: (t, ui) => {
      ui.busy('Adding “' + t.label + '” to your showcase…');
      const body = t.type === 'tracks' ? { kind: 'tracks', track_ids: t.ids }
                                       : { kind: 'scope', scope_type: t.type, scope_id: t.id };
      fetch('/api/showcase/add', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) }).then(r => r.json()).then(r => {
        if (!r || !r.ok) { ui.error((r && r.error) || 'could not add to the showcase'); return; }
        ui.done(r.added ? ('Added ' + r.added + ' to your showcase — arrange + publish it in Tools → Showcase.')
                        : 'Already in your showcase.');
      }).catch(() => ui.error('could not add — is the app still running?'));
    } },
  { id: 'share', label: 'A shareable room page', sub: 'A folder to send or host — no audio, just the room',
    accepts: t => SCOPES.includes(t.type) || t.type === 'tracks',
    run: (t, ui) => {
      ui.busy('Making a room page for “' + t.label + '” …');
      const base = t.type === 'tracks' ? { track_ids: t.ids, label: t.label } : { scope_type: t.type, scope_id: t.id };
      fetch('/api/export/share', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(base) }).then(r => r.json()).then(r => {
        if (!r || !r.ok) { ui.error((r && r.error) || 'could not make the page'); return; }
        ui.done('Room page ready — ' + r.count + ' records, ' + r.with_art + ' covers → ' + r.folder + ' (showing it in Finder). Open index.html to see it; send or host the folder to share it.');
        fetch('/api/reveal-path', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ path: r.folder }) }).catch(() => {});
      }).catch(() => ui.error('could not make the page — is the app still running?'));
    } },
];

// ── styles (injected once; namespaced mrx-/mrm- so nothing collides) ──────
function ensureStyles() {
  if (document.getElementById('mrx-style')) return;
  const s = document.createElement('style'); s.id = 'mrx-style';
  s.textContent = `
  .mrx-back{ position:fixed; inset:0; z-index:3000; display:none; align-items:center; justify-content:center;
    background:rgba(8,6,4,.62); backdrop-filter:blur(2px); }
  .mrx-back.on{ display:flex; }
  .mrx{ width:min(440px,92vw); max-height:86vh; overflow:auto; border-radius:18px; padding:20px 20px 16px;
    background:linear-gradient(168deg,#211a12,#171109); border:1px solid rgba(245,230,176,.2);
    box-shadow:0 30px 80px rgba(0,0,0,.6); color:#efe6cf; font-family:inherit; }
  .mrx__h{ display:flex; align-items:baseline; gap:8px; margin-bottom:3px; }
  .mrx__h h3{ margin:0; font-size:1.18rem; font-weight:500; color:#f5e6b0; }
  .mrx__sub{ font-size:.82rem; color:#a99; opacity:.85; }
  .mrx__safe{ font-size:.74rem; color:#9bbf9e; margin:8px 0 12px; display:flex; gap:6px; align-items:flex-start; }
  .mrx__safe--warn{ color:#e0c08f; }
  .mrx-mode{ display:flex; gap:6px; margin:0 0 14px; }
  .mrx-mode__b{ flex:1; display:flex; flex-direction:column; gap:1px; align-items:flex-start; cursor:pointer;
    padding:8px 10px; border-radius:10px; color:#cbb; background:rgba(255,255,255,.03);
    border:1px solid rgba(255,255,255,.08); font-family:inherit; font-size:.84rem; transition:all .14s ease; }
  .mrx-mode__b:hover{ border-color:rgba(245,230,176,.3); }
  .mrx-mode__b.on{ color:#f5e6b0; border-color:rgba(245,230,176,.55); background:rgba(245,230,176,.08); }
  .mrx-mode__s{ font-size:.62rem; color:#988; }
  .mrx__list{ display:flex; flex-direction:column; gap:7px; }
  .mrx-d{ display:flex; align-items:center; gap:11px; width:100%; text-align:left; cursor:pointer;
    padding:11px 13px; border-radius:12px; color:#efe6cf; background:rgba(255,255,255,.035);
    border:1px solid rgba(255,255,255,.07); transition:all .15s ease; font-family:inherit; }
  .mrx-d:hover{ background:rgba(245,230,176,.08); border-color:rgba(245,230,176,.35); transform:translateY(-1px); }
  .mrx-d[disabled]{ opacity:.4; cursor:default; transform:none; }
  .mrx-d__main{ flex:1; min-width:0; }
  .mrx-d__lbl{ font-size:.93rem; }
  .mrx-d__sub{ font-size:.72rem; color:#a99; margin-top:1px; }
  .mrx-d__soon{ font-family:monospace; font-size:.56rem; letter-spacing:1.2px; text-transform:uppercase;
    color:#caa; border:1px solid rgba(245,230,176,.25); border-radius:20px; padding:2px 8px; }
  .mrx__status{ font-size:.8rem; margin-top:13px; min-height:1.1em; color:#cbb; }
  .mrx__status.err{ color:#e0a08f; } .mrx__status.ok{ color:#9bbf9e; }
  .mrx__foot{ display:flex; justify-content:space-between; align-items:center; margin-top:14px; gap:10px; }
  .mrx__note{ font-size:.68rem; color:#988; opacity:.8; }
  .mrx__x{ cursor:pointer; background:none; border:1px solid rgba(245,230,176,.25); color:#cbb;
    border-radius:9px; padding:6px 12px; font-family:inherit; font-size:.8rem; }
  .mrx__x:hover{ color:#efe6cf; border-color:rgba(245,230,176,.5); }
  .mrm{ position:fixed; z-index:3200; min-width:170px; padding:5px; border-radius:11px; display:none;
    background:rgba(20,15,9,.98); border:1px solid rgba(245,230,176,.22); box-shadow:0 16px 44px rgba(0,0,0,.55); }
  .mrm.on{ display:block; }
  .mrm__i{ display:flex; align-items:center; gap:8px; width:100%; text-align:left; cursor:pointer;
    padding:8px 11px; border-radius:7px; color:#efe6cf; background:none; border:0; font-family:inherit; font-size:.86rem; }
  .mrm__i:hover{ background:rgba(245,230,176,.12); color:#f5e6b0; }
  .mrm__i[disabled]{ opacity:.45; cursor:default; }
  .mrm__i--danger:hover{ background:rgba(156,59,44,.28); color:#e7b3a6; }`;
  document.head.appendChild(s);
}

// ── the Export pop-up ─────────────────────────────────────────────────────
let _back, _modal;
let exportMode = 'copy';   // 'copy' (default, safe) | 'move_out' | 'relocate' — governs the folder export
function build() {
  ensureStyles();
  _back = document.createElement('div'); _back.className = 'mrx-back';
  _modal = document.createElement('div'); _modal.className = 'mrx';
  _back.appendChild(_modal);
  _back.addEventListener('pointerdown', e => { if (e.target === _back) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && _back.classList.contains('on')) close(); });
  document.body.appendChild(_back);
}
function close() { if (_back) _back.classList.remove('on'); }

function open(target) {
  if (!target || !target.type) return;
  target.label = target.label || target.type;
  if (!_back) build();
  exportMode = 'copy';                               // always reopen on the safe default
  const dests = DESTS.filter(d => { try { return d.accepts(target); } catch (e) { return false; } });
  _modal.innerHTML = '';
  const head = document.createElement('div'); head.className = 'mrx__h';
  head.innerHTML = `<h3>Export</h3><span class="mrx__sub">${esc(target.label)}</span>`;
  const safe = document.createElement('div'); safe.className = 'mrx__safe';
  const updateBanner = () => {
    if (exportMode === 'copy') { safe.className = 'mrx__safe';
      safe.innerHTML = '<span>✓</span><span>Exporting <b>copies</b> your files — the originals always stay in your library.</span>'; }
    else if (exportMode === 'move_out') { safe.className = 'mrx__safe mrx__safe--warn';
      safe.innerHTML = '<span>⚠</span><span><b>Move out:</b> after a verified copy, originals go to the recoverable <i>Removed from Music Room</i> folder and these tracks leave your library.</span>'; }
    else { safe.className = 'mrx__safe mrx__safe--warn';
      safe.innerHTML = '<span>⚠</span><span><b>Relocate:</b> after a verified copy, files move to the new folder — tracks stay in your library and keep playing.</span>'; }
  };
  updateBanner();
  // copy / move chooser — only when a move-capable destination (a folder) is offered
  let modeRow = null;
  if (dests.some(d => d.id === 'folder')) {
    modeRow = document.createElement('div'); modeRow.className = 'mrx-mode';
    [['copy', 'Copy', 'originals stay'], ['move_out', 'Move out', 'leaves the Room'], ['relocate', 'Relocate', 'stays in library']]
      .forEach(([k, lbl, sub]) => {
        const b = document.createElement('button'); b.className = 'mrx-mode__b' + (k === 'copy' ? ' on' : ''); b.dataset.k = k;
        b.innerHTML = '<span>' + lbl + '</span><span class="mrx-mode__s">' + sub + '</span>';
        b.addEventListener('click', () => { exportMode = k;
          modeRow.querySelectorAll('.mrx-mode__b').forEach(x => x.classList.toggle('on', x.dataset.k === k));
          updateBanner(); });
        modeRow.appendChild(b);
      });
  }
  const list = document.createElement('div'); list.className = 'mrx__list';
  const status = document.createElement('div'); status.className = 'mrx__status';
  const ui = {
    status: m => { status.className = 'mrx__status'; status.textContent = m || ''; },
    busy:   m => { status.className = 'mrx__status'; status.textContent = m || ''; },
    error:  m => { status.className = 'mrx__status err'; status.textContent = m || ''; },
    done:   m => { status.className = 'mrx__status ok'; status.textContent = m || ''; },
  };
  dests.forEach(d => {
    const b = document.createElement('button'); b.className = 'mrx-d'; if (d.soon) b.disabled = true;
    b.innerHTML = `<div class="mrx-d__main"><div class="mrx-d__lbl">${esc(d.label)}</div>` +
      `<div class="mrx-d__sub">${esc(d.sub || '')}</div></div>` +
      (d.soon ? `<span class="mrx-d__soon">soon</span>` : `<span class="mrx-d__sub">→</span>`);
    if (!d.soon) b.addEventListener('click', () => { try { d.run(target, ui); } catch (e) { ui.error('export failed'); } });
    list.appendChild(b);
  });
  const foot = document.createElement('div'); foot.className = 'mrx__foot';
  foot.innerHTML = `<span class="mrx__note">A move always verifies the copy before it touches an original — nothing is hard-deleted.</span>`;
  const x = document.createElement('button'); x.className = 'mrx__x'; x.textContent = 'Close';
  x.addEventListener('click', close); foot.appendChild(x);
  _modal.append(head, safe);
  if (modeRow) _modal.append(modeRow);
  _modal.append(list, status, foot);
  _back.classList.add('on');
}

// ── a tiny generic context menu (right-click) — also a registry ───────────
let _menu;
function menuOpen(x, y, items) {
  ensureStyles();
  if (!_menu) {
    _menu = document.createElement('div'); _menu.className = 'mrm';
    document.body.appendChild(_menu);
    document.addEventListener('pointerdown', e => { if (_menu && !_menu.contains(e.target)) menuClose(); }, true);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') menuClose(); });
    window.addEventListener('blur', menuClose);
  }
  _menu.innerHTML = '';
  (items || []).filter(Boolean).forEach(it => {
    const b = document.createElement('button');
    b.className = 'mrm__i' + (it.danger ? ' mrm__i--danger' : ''); if (it.soon) b.disabled = true;
    b.textContent = it.label;
    if (!it.soon && typeof it.onClick === 'function') b.addEventListener('click', () => { menuClose(); it.onClick(); });
    _menu.appendChild(b);
  });
  _menu.style.left = '0px'; _menu.style.top = '0px'; _menu.classList.add('on');
  const r = _menu.getBoundingClientRect();
  _menu.style.left = Math.min(x, innerWidth - r.width - 8) + 'px';
  _menu.style.top  = Math.min(y, innerHeight - r.height - 8) + 'px';
}
function menuClose() { if (_menu) _menu.classList.remove('on'); }

function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

window.MRExport = { open, close, destinations: DESTS,
  registerDestination(d) { DESTS.push(d); } };
window.MRMenu = { open: menuOpen, close: menuClose };
})();
