// =============================================================
// mr_lightbox.js  —  window.MRLightbox
// =============================================================
// A self-contained port of place.html's artwork lightbox: the full-screen
// draw / sticker / post-it / text / image editor over a record's album art.
// The 3D room's NATIVE track panel (r3d_panel.js) calls this so it no longer
// needs the place.html iframe just to draw on a cover.
//
// IDENTICAL functionality + the SAME backend endpoints as place.html:
//   GET  /api/track/<id>/overlays?place_id=<pid>
//   POST /api/track/<id>/overlays           (postit/text/drawing/sticker/image)
//   PUT  /api/overlay/<oid>                  (position / size / content)
//   DELETE /api/overlay/<oid>
//   GET/POST /api/stickers · DELETE /api/sticker/<id>
//   POST /api/overlay-image-upload
//   POST /api/track/<id>/update             (cover colour for blank-art)
//
// It self-injects its CSS (the room doesn't load style.css) with the place
// palette baked in, so it looks exactly like the 2D version.
//
//   MRLightbox.open(trackId, { placeId, track, onClose })
//   MRLightbox.close()
// =============================================================
(function () {
'use strict';

let _ctx        = {};
let lbTrackId   = null;
let lbScope     = 'all';          // 'all' = global (place_id null) · 'place' = this place only
let lbPenMode   = false;
let lbPenColor  = '#1a1a1a';
let lbPenWidth  = 4;
let lbStrokeUndoStack = [];        // ids of recently-added drawing overlays
let _lbDrawing  = null;            // { points, svgEl, polyline, color, width }
let _lbHandlersOn = false;
let root        = null;            // the lightbox DOM root

const LB_PEN_PALETTE = ['#1a1a1a', '#cf4a3e', '#3a78c4', '#3e9b6a', '#e8c560', '#f4ede0'];

const $ = (id) => document.getElementById(id);
function _toast(msg, isErr) { try { if (window.showToast) window.showToast(msg, isErr); } catch (_) {} }
function _placeId() { return lbScope === 'place' ? (_ctx.placeId || null) : null; }

// ── CSS (place palette baked in; scoped under #mr-artwork-lightbox) ──────────
function _injectCSS() {
  if ($('mr-lightbox-css')) return;
  const s = document.createElement('style');
  s.id = 'mr-lightbox-css';
  s.textContent = `
  #mr-artwork-lightbox.artwork-lightbox{
    --text:#2e2718; --muted:#6c5d40; --muted2:#8a7a58; --accent:#4a7242;
    --accent-dim:rgba(74,114,66,0.15); --surface:#f1e7cb; --surface2:#f8f1dc;
    --border:#ccb98e; --bg:#e7d9ba; --danger:#9c3b2c; --warning:#b5832f;
    --radius:5px; --radius-lg:10px;
    --font-serif:'EB Garamond',Georgia,serif; --font-main:system-ui,sans-serif;
    --font-mono:'JetBrains Mono',monospace;
    display:none; position:fixed; inset:0; z-index:99990;
    background:rgba(8,12,9,0.94); backdrop-filter:blur(8px);
    flex-direction:column; color:var(--text); font-family:var(--font-main); }
  #mr-artwork-lightbox.artwork-lightbox.open{ display:flex; }
  #mr-artwork-lightbox .artwork-lightbox__header{ display:flex; align-items:center; gap:12px;
    padding:12px 18px; border-bottom:1px solid var(--border); flex-shrink:0; background:var(--surface); }
  #mr-artwork-lightbox .artwork-lightbox__track-title{ font-family:var(--font-serif); font-style:italic;
    font-size:1rem; color:var(--text); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  #mr-artwork-lightbox .artwork-lightbox__toolbar{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  #mr-artwork-lightbox .lb-tool-btn{ background:none; border:1px solid var(--border); border-radius:var(--radius);
    color:var(--muted); padding:5px 11px; font-size:0.8rem; cursor:pointer; transition:all 0.15s;
    font-family:var(--font-main); white-space:nowrap; }
  #mr-artwork-lightbox .lb-tool-btn:hover{ border-color:var(--accent); color:var(--accent); }
  #mr-artwork-lightbox .lb-tool-btn.active{ border-color:var(--accent); color:var(--accent); background:var(--accent-dim); }
  #mr-artwork-lightbox .artwork-lightbox__close{ position:static; width:auto; height:auto; border-radius:var(--radius);
    padding:5px 12px; font-size:0.8rem; flex-shrink:0; background:none; border:1px solid var(--border);
    color:var(--muted); cursor:pointer; font-family:var(--font-main); }
  #mr-artwork-lightbox .artwork-lightbox__close:hover{ color:var(--text); border-color:var(--text); }
  #mr-artwork-lightbox .lb-scope-toggle{ display:flex; border:1px solid var(--border); border-radius:var(--radius);
    overflow:hidden; flex-shrink:0; }
  #mr-artwork-lightbox .lb-scope-btn{ background:none; border:none; color:var(--muted2); padding:4px 10px;
    font-size:0.73rem; cursor:pointer; transition:all 0.12s; white-space:nowrap; font-family:var(--font-main); }
  #mr-artwork-lightbox .lb-scope-btn.active{ background:var(--accent-dim); color:var(--accent); }
  #mr-artwork-lightbox .lb-scope-btn + .lb-scope-btn{ border-left:1px solid var(--border); }
  #mr-artwork-lightbox .lb-pen-panel{ display:inline-flex; align-items:center; gap:8px; padding:4px 10px;
    border:1px solid var(--border); border-radius:var(--radius); }
  #mr-artwork-lightbox .lb-pen-swatches{ display:inline-flex; gap:5px; }
  #mr-artwork-lightbox .lb-pen-swatch{ width:18px; height:18px; border-radius:50%; border:1px solid rgba(255,255,255,0.18);
    cursor:pointer; padding:0; transition:transform 0.12s, box-shadow 0.12s; }
  #mr-artwork-lightbox .lb-pen-swatch:hover{ transform:scale(1.12); }
  #mr-artwork-lightbox .lb-pen-swatch.active{ box-shadow:0 0 0 2px var(--bg), 0 0 0 3px var(--accent); transform:scale(1.1); }
  #mr-artwork-lightbox .lb-pen-widths{ display:inline-flex; gap:3px; }
  #mr-artwork-lightbox .lb-pen-width{ background:none; border:1px solid var(--border); color:var(--muted);
    border-radius:var(--radius); width:26px; height:24px; cursor:pointer; font-size:0.85rem; line-height:1; transition:all 0.12s; }
  #mr-artwork-lightbox .lb-pen-width:hover{ border-color:var(--accent); color:var(--accent); }
  #mr-artwork-lightbox .lb-pen-width.active{ border-color:var(--accent); color:var(--accent); background:var(--accent-dim); }
  #mr-artwork-lightbox .artwork-lightbox__body{ flex:1; display:flex; align-items:center; justify-content:center;
    position:relative; overflow:hidden; padding:12px; }
  #mr-artwork-lightbox .cludach-canvas-wrap{ position:relative;
    width:min(calc(100vh - 80px), calc(100vw - 32px)); height:min(calc(100vh - 80px), calc(100vw - 32px)); flex-shrink:0; }
  #mr-artwork-lightbox .cludach-canvas-wrap img,
  #mr-artwork-lightbox .cludach-canvas-wrap .cludach-canvas-placeholder{ width:100%; height:100%; object-fit:cover;
    border-radius:var(--radius-lg); display:block; user-select:none; pointer-events:none; }
  #mr-artwork-lightbox .cludach-canvas-placeholder{ display:flex; align-items:center; justify-content:center;
    font-family:var(--font-serif); font-style:italic; font-size:5rem; color:rgba(255,255,255,0.15); }
  #mr-artwork-lightbox .cludach-canvas-wrap.pen-mode{ cursor:crosshair; touch-action:none; }
  #mr-artwork-lightbox .cludach-canvas-wrap.pen-mode .ov-layer{ pointer-events:none; }
  #mr-artwork-lightbox .ov-layer{ position:absolute; inset:0; pointer-events:none; }
  #mr-artwork-lightbox .ov-layer.editable{ pointer-events:auto; }
  #mr-artwork-lightbox .overlay-item{ position:absolute; cursor:move; user-select:none; box-sizing:border-box; }
  #mr-artwork-lightbox .overlay-item img{ width:100%; height:100%; object-fit:contain; display:block; pointer-events:none; }
  #mr-artwork-lightbox .overlay-postit{ background:#fef08a;
    box-shadow:2px 3px 8px rgba(0,0,0,0.4), inset 0 -1px 0 rgba(0,0,0,0.08); padding:8px 10px; border-radius:2px; overflow:hidden; }
  #mr-artwork-lightbox .overlay-postit .postit-text{ width:100%; height:100%; background:transparent; border:none; outline:none;
    resize:none; font-family:'Patrick Hand','Segoe UI',sans-serif; font-size:0.82rem; line-height:1.4; color:#2a2208; overflow:hidden; cursor:text; }
  #mr-artwork-lightbox .overlay-item .ov-delete{ position:absolute; top:-8px; right:-8px; width:18px; height:18px;
    background:var(--danger); border:none; border-radius:50%; color:#fff; font-size:0.6rem; cursor:pointer; display:none;
    align-items:center; justify-content:center; z-index:10; line-height:1; }
  #mr-artwork-lightbox .ov-layer.editable .overlay-item:hover .ov-delete{ display:flex; }
  #mr-artwork-lightbox .overlay-item .ov-resize{ position:absolute; bottom:-5px; right:-5px; width:12px; height:12px;
    background:var(--accent); border-radius:2px; cursor:se-resize; display:none; z-index:10; }
  #mr-artwork-lightbox .ov-layer.editable .overlay-item:hover .ov-resize{ display:block; }
  #mr-artwork-lightbox .overlay-item.overlay-drawing{ pointer-events:none; }
  #mr-artwork-lightbox .overlay-item.overlay-drawing svg{ width:100%; height:100%; display:block; pointer-events:none; }
  #mr-artwork-lightbox .overlay-item.overlay-drawing .ov-delete{ pointer-events:auto; }
  #mr-artwork-lightbox .ov-place-badge{ position:absolute; top:-8px; left:3px; font-size:0.54rem; background:var(--warning);
    color:var(--bg); padding:1px 4px; border-radius:2px; line-height:1.3; font-family:var(--font-mono); pointer-events:none; z-index:5; }
  #mr-artwork-lightbox .cludach-sidebar{ position:absolute; right:0; top:0; bottom:0; width:240px; background:var(--surface);
    border-left:1px solid var(--border); display:flex; flex-direction:column; transform:translateX(100%); transition:transform 0.22s ease; z-index:10; }
  #mr-artwork-lightbox .cludach-sidebar.open{ transform:translateX(0); }
  #mr-artwork-lightbox .cludach-sidebar__header{ display:flex; align-items:center; justify-content:space-between; padding:12px 14px;
    border-bottom:1px solid var(--border); font-family:var(--font-serif); font-style:italic; font-size:0.9rem; color:var(--muted); flex-shrink:0; }
  #mr-artwork-lightbox .cludach-sidebar__header button{ background:none; border:none; color:var(--muted); cursor:pointer; font-size:0.8rem; padding:2px; }
  #mr-artwork-lightbox .cludach-sidebar__grid{ flex:1; overflow-y:auto; padding:10px; display:grid; grid-template-columns:1fr 1fr; gap:8px; align-content:start; }
  #mr-artwork-lightbox .cludach-sticker-thumb{ aspect-ratio:1; border:1px solid var(--border); border-radius:var(--radius); overflow:hidden;
    cursor:pointer; transition:border-color 0.12s; background:var(--surface2); position:relative; }
  #mr-artwork-lightbox .cludach-sticker-thumb:hover{ border-color:var(--accent); }
  #mr-artwork-lightbox .cludach-sticker-thumb img{ width:100%; height:100%; object-fit:contain; padding:4px; }
  #mr-artwork-lightbox .cludach-sticker-thumb__del{ position:absolute; top:2px; right:2px; width:16px; height:16px;
    background:rgba(8,12,9,0.8); border:none; border-radius:50%; color:var(--muted); font-size:0.6rem; cursor:pointer; display:none; align-items:center; justify-content:center; }
  #mr-artwork-lightbox .cludach-sticker-thumb:hover .cludach-sticker-thumb__del{ display:flex; }
  #mr-artwork-lightbox .cludach-sidebar__upload{ padding:10px; border-top:1px solid var(--border); flex-shrink:0; }
  #mr-artwork-lightbox .cludach-upload-btn{ width:100%; background:none; border:1px dashed var(--border); border-radius:var(--radius);
    color:var(--muted); padding:8px; font-size:0.78rem; cursor:pointer; transition:all 0.15s; font-family:var(--font-main); }
  #mr-artwork-lightbox .cludach-upload-btn:hover{ border-color:var(--accent); color:var(--accent); }
  `;
  document.head.appendChild(s);
}

// ── markup (built once; wired with listeners, not inline onclick) ────────────
function _ensureDOM() {
  if (root) return;
  _injectCSS();
  root = document.createElement('div');
  root.className = 'artwork-lightbox';
  root.id = 'mr-artwork-lightbox';
  root.innerHTML = `
    <div class="artwork-lightbox__header">
      <div class="artwork-lightbox__track-title" id="lb-track-name">—</div>
      <div class="artwork-lightbox__toolbar">
        <div class="lb-scope-toggle" title="Where should this annotation appear?">
          <button class="lb-scope-btn active" id="lb-scope-all">All places</button>
          <button class="lb-scope-btn" id="lb-scope-place">This place</button>
        </div>
        <button class="lb-tool-btn" id="lb-add-postit">+ Post-it</button>
        <button class="lb-tool-btn" id="lb-add-text">+ Text</button>
        <label class="lb-tool-btn" id="lb-cover-colour-wrap" style="display:none; gap:6px; align-items:center; cursor:pointer;">
          cover colour <input type="color" id="lb-cover-colour" value="#253d28"
            style="width:24px; height:20px; border:none; background:none; padding:0; cursor:pointer;"></label>
        <button class="lb-tool-btn" id="lb-sticker-btn">+ Sticker</button>
        <button class="lb-tool-btn" id="lb-add-image">+ Image</button>
        <input type="file" id="lb-image-input" accept="image/*" style="display:none">
        <button class="lb-tool-btn" id="lb-pen-btn" title="Draw on the cover (stylus, mouse, trackpad)">✎ Draw</button>
        <div class="lb-pen-panel" id="lb-pen-panel" style="display:none;">
          <span class="lb-pen-swatches" id="lb-pen-swatches"></span>
          <span class="lb-pen-widths">
            <button class="lb-pen-width" data-w="2"  title="Thin">·</button>
            <button class="lb-pen-width active" data-w="4"  title="Medium">•</button>
            <button class="lb-pen-width" data-w="9"  title="Marker">●</button>
            <button class="lb-pen-width" data-w="16" title="Brush">⬤</button>
          </span>
          <button class="lb-pen-width" id="lb-pen-undo" title="Undo last stroke" style="width:auto;padding:0 10px;">↶ Undo</button>
          <button class="lb-pen-width" id="lb-pen-erase" title="Erase every drawing on this cover" style="width:auto;padding:0 10px;">Erase all</button>
        </div>
      </div>
      <button class="artwork-lightbox__close" id="lb-done">Done ✓</button>
    </div>
    <div class="artwork-lightbox__body">
      <div class="cludach-canvas-wrap" id="lightbox-canvas">
        <img id="lb-art-img" src="" alt="" style="display:none;">
        <div class="cludach-canvas-placeholder" id="lb-art-placeholder"></div>
        <div class="ov-layer editable" id="lightbox-ov-layer"></div>
      </div>
      <div class="cludach-sidebar" id="lb-sticker-sidebar">
        <div class="cludach-sidebar__header">Stickers <button id="lb-sticker-close">✕</button></div>
        <div class="cludach-sidebar__grid" id="lb-sticker-grid"></div>
        <div class="cludach-sidebar__upload">
          <button class="cludach-upload-btn" id="lb-sticker-add">+ Add sticker image</button>
          <input type="file" id="lb-sticker-file" accept="image/*" style="display:none">
        </div>
      </div>
    </div>`;
  document.body.appendChild(root);

  // wire the toolbar
  $('lb-scope-all').onclick   = () => lbSetScope('all');
  $('lb-scope-place').onclick = () => lbSetScope('place');
  $('lb-add-postit').onclick  = lbAddPostit;
  $('lb-add-text').onclick    = lbAddText;
  $('lb-cover-colour').oninput  = (e) => lbCoverColourLive(e.target.value);
  $('lb-cover-colour').onchange = (e) => lbCoverColourSave(e.target.value);
  $('lb-sticker-btn').onclick  = lbToggleStickerPanel;
  $('lb-add-image').onclick    = lbPickImage;
  $('lb-image-input').onchange = (e) => lbUploadImage(e.target);
  $('lb-pen-btn').onclick      = lbTogglePen;
  $('lb-pen-undo').onclick     = lbUndoStroke;
  $('lb-pen-erase').onclick    = lbEraseAllDrawings;
  root.querySelectorAll('.lb-pen-width[data-w]').forEach(b =>
    b.onclick = () => lbSetPenWidth(parseFloat(b.dataset.w)));
  $('lb-done').onclick         = close;
  $('lb-sticker-close').onclick = lbCloseStickerPanel;
  $('lb-sticker-add').onclick  = () => $('lb-sticker-file').click();
  $('lb-sticker-file').onchange = (e) => uploadSticker(e.target);
}

// ── open / close ────────────────────────────────────────────────────────────
async function open(trackId, ctx) {
  _ctx = ctx || {};
  lbTrackId = trackId;
  _ensureDOM();
  const t   = _ctx.track || {};
  const img = $('lb-art-img'), ph = $('lb-art-placeholder'), ovl = $('lightbox-ov-layer');
  $('lb-track-name').textContent = [t.title, t.artist_name].filter(Boolean).join(' — ') || ('Track ' + trackId);

  img.style.display = 'none';
  ph.style.display  = '';
  ph.textContent    = (t.artist_name || t.title || '?')[0].toUpperCase();
  ph.style.background = `linear-gradient(135deg, ${t.colour_code || '#253d28'}cc, ${t.colour_code || '#253d28'}44)`;
  if (t.artwork_path) {
    img.src = `/api/artwork/${trackId}?v=${t.art_v || Date.now()}`;
    img.onload  = () => { img.style.display = 'block'; ph.style.display = 'none'; };
    img.onerror = () => { img.style.display = 'none'; ph.style.display = ''; };
  }
  // blank-art records: pick the cover's colour, then draw/sticker/write on it
  const cw = $('lb-cover-colour-wrap');
  cw.style.display = t.artwork_path ? 'none' : 'inline-flex';
  if (!t.artwork_path) $('lb-cover-colour').value = t.colour_code || '#253d28';

  ovl.innerHTML = '';
  lbStrokeUndoStack = [];
  lbSetScope('all');
  try {
    const data = await fetch(`/api/track/${trackId}/overlays?place_id=${_ctx.placeId || ''}`).then(r => r.json());
    renderOverlaysEditable(ovl, data.overlays || []);
  } catch (_) {}

  root.classList.add('open');
  document.addEventListener('keydown', _lbEsc);
}

function close() {
  if (!root) return;
  root.classList.remove('open');
  document.removeEventListener('keydown', _lbEsc);
  lbCloseStickerPanel();
  if (lbPenMode) lbTogglePen();
  _lbDrawCancel();
  lbTrackId = null;
  try { if (_ctx.onClose) _ctx.onClose(); } catch (_) {}
}
function _lbEsc(e) { if (e.key === 'Escape') close(); }

function lbSetScope(scope) {
  lbScope = scope;
  $('lb-scope-all').classList.toggle('active',   scope === 'all');
  $('lb-scope-place').classList.toggle('active', scope === 'place');
}

// ── overlay render ───────────────────────────────────────────────────────────
function renderOverlaysEditable(layer, overlays) {
  layer.innerHTML = '';
  overlays.forEach(ov => {
    const el = _buildOverlayEl(ov);
    layer.appendChild(el);
    _initDrag(el, ov.id);
    _initResize(el, ov.id);
  });
}

function _buildOverlayEl(ov) {
  const el = document.createElement('div');
  el.className = 'overlay-item';
  el.dataset.ovid = ov.id;
  el.style.cssText = `left:${ov.pos_x_pct}%;top:${ov.pos_y_pct}%;width:${ov.width_pct}%;height:${ov.height_pct}%;transform:rotate(${ov.rotation || 0}deg);z-index:${ov.z_index || 1};position:absolute;`;

  if (ov.overlay_type === 'drawing') {
    el.classList.add('overlay-drawing');
    let stroke; try { stroke = JSON.parse(ov.content || '{}'); } catch { stroke = {}; }
    const pts = stroke.points || [], color = stroke.color || '#1a1a1a', width = stroke.width || 4;
    const pointsStr = pts.map(p => p[0].toFixed(2) + ',' + p[1].toFixed(2)).join(' ');
    el.innerHTML = `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="${pointsStr}" fill="none" stroke="${color}" stroke-width="${width / 2}"
        stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
    const del = document.createElement('button');
    del.className = 'ov-delete'; del.textContent = '✕'; del.title = 'Erase stroke';
    del.addEventListener('mousedown', e => { e.stopPropagation(); deleteOverlay(ov.id, el); });
    el.appendChild(del);
    if (ov.place_id) el.appendChild(_placeBadge());
    return el;
  }

  if (ov.overlay_type === 'text') {
    let tj; try { tj = JSON.parse(ov.content || '{}'); } catch { tj = {}; }
    el.classList.add('overlay-text');
    const inp = document.createElement('div');
    inp.className = 'ov-text-input';
    inp.contentEditable = 'false';
    inp.spellcheck = false;
    inp.textContent = tj.text || '';
    const applyStyle = () => {
      inp.style.cssText = `width:100%;height:100%;display:flex;align-items:center;justify-content:center;`
        + `text-align:center;outline:none;overflow:hidden;line-height:1.15;`
        + `font-size:${tj.size || 2}em;font-family:${tj.font || "'EB Garamond', serif"};color:${tj.color || '#2e2718'};`
        + `font-weight:${tj.bold ? '700' : '400'};font-style:${tj.italic ? 'italic' : 'normal'};`
        + `text-shadow:0 1px 4px rgba(255,255,255,.3);cursor:grab;`;
    };
    applyStyle();
    const save = () => _saveOverlayContent(ov.id, JSON.stringify({
      text: inp.textContent, font: tj.font || "'EB Garamond', serif",
      color: tj.color || '#2e2718', size: tj.size || 2, bold: !!tj.bold, italic: !!tj.italic }));
    inp.addEventListener('dblclick', e => {
      e.stopPropagation(); inp.contentEditable = 'true'; inp.style.cursor = 'text';
      inp.focus(); document.getSelection()?.selectAllChildren(inp);
    });
    inp.addEventListener('mousedown', e => { if (inp.isContentEditable) e.stopPropagation(); });
    inp.addEventListener('blur', () => { inp.contentEditable = 'false'; inp.style.cursor = 'grab'; save(); });
    const ctl = document.createElement('div');
    ctl.className = 'ov-text-ctl';
    ctl.style.cssText = 'position:absolute;top:-26px;left:0;display:flex;gap:4px;align-items:center;';
    const stopDown = e => e.stopPropagation();
    const fsel = document.createElement('select');
    fsel.style.cssText = 'font-size:10px;max-width:96px;';
    [["'EB Garamond', serif", "Garamond"], ["'Uncial Antiqua', cursive", "Uncial"],
     ["'Cinzel', serif", "Cinzel"], ["'IM Fell English', serif", "Fell"],
     ["'Inter', sans-serif", "Inter"], ["'JetBrains Mono', monospace", "Mono"],
     ["'MedievalSharp', cursive", "Medieval"]].forEach(([v, l]) => {
      const o = document.createElement('option'); o.value = v; o.textContent = l;
      if (v === (tj.font || "'EB Garamond', serif")) o.selected = true; fsel.appendChild(o); });
    fsel.addEventListener('mousedown', stopDown);
    fsel.addEventListener('change', () => { tj.font = fsel.value; applyStyle(); save(); });
    const ssel = document.createElement('select');
    ssel.title = 'Text size'; ssel.style.cssText = 'font-size:10px;';
    [0.8, 1, 1.3, 1.6, 2, 2.5, 3, 4, 5].forEach(v => {
      const o = document.createElement('option'); o.value = v; o.textContent = v + '×';
      if (v === (tj.size || 2)) o.selected = true; ssel.appendChild(o); });
    ssel.addEventListener('mousedown', stopDown);
    ssel.addEventListener('change', () => { tj.size = +ssel.value; applyStyle(); save(); });
    const mkToggle = (label, key, fontStyle) => {
      const b = document.createElement('button');
      b.textContent = label; b.title = label === 'B' ? 'Bold' : 'Italic';
      b.style.cssText = `font-size:10px;width:18px;height:18px;border-radius:3px;cursor:pointer;`
        + `border:1px solid rgba(0,0,0,.25);${fontStyle};`
        + `background:${tj[key] ? 'rgba(0,0,0,.65)' : 'rgba(255,255,255,.7)'};color:${tj[key] ? '#fff' : '#222'};`;
      b.addEventListener('mousedown', stopDown);
      b.addEventListener('click', e => {
        e.stopPropagation(); tj[key] = !tj[key];
        b.style.background = tj[key] ? 'rgba(0,0,0,.65)' : 'rgba(255,255,255,.7)';
        b.style.color = tj[key] ? '#fff' : '#222'; applyStyle(); save();
      });
      return b;
    };
    const col = document.createElement('input');
    col.type = 'color'; col.value = tj.color || '#2e2718';
    col.style.cssText = 'width:20px;height:18px;border:none;background:none;padding:0;cursor:pointer;';
    col.addEventListener('mousedown', stopDown);
    col.addEventListener('change', () => { tj.color = col.value; applyStyle(); save(); });
    ctl.appendChild(fsel); ctl.appendChild(ssel);
    ctl.appendChild(mkToggle('B', 'bold', 'font-weight:700'));
    ctl.appendChild(mkToggle('I', 'italic', 'font-style:italic'));
    ctl.appendChild(col);
    el.appendChild(ctl);
    el.appendChild(inp);
  } else if (ov.overlay_type === 'postit') {
    el.classList.add('overlay-postit');
    el.style.background = ov.color || '#fef08a';
    const ta = document.createElement('textarea');
    ta.className = 'postit-text'; ta.value = ov.content || '';
    ta.addEventListener('mousedown', e => e.stopPropagation());
    ta.addEventListener('blur',   () => _saveOverlayContent(ov.id, ta.value));
    ta.addEventListener('change', () => _saveOverlayContent(ov.id, ta.value));
    el.appendChild(ta);
  } else {
    const img = document.createElement('img');
    img.src = ov.content || ''; img.draggable = false;
    img.style.cssText = 'width:100%;height:100%;object-fit:contain;display:block;pointer-events:none;';
    el.appendChild(img);
  }

  const del = document.createElement('button');
  del.className = 'ov-delete'; del.textContent = '✕'; del.title = 'Remove';
  del.addEventListener('mousedown', e => { e.stopPropagation(); deleteOverlay(ov.id, el); });
  el.appendChild(del);
  const rh = document.createElement('div');
  rh.className = 'ov-resize';
  el.appendChild(rh);
  if (ov.place_id) el.appendChild(_placeBadge());
  return el;
}

function _placeBadge() {
  const badge = document.createElement('div');
  badge.className = 'ov-place-badge';
  badge.title = 'Visible in this place only'; badge.textContent = 'here';
  return badge;
}

// ── drag / resize (percent of the canvas) ────────────────────────────────────
function _initDrag(el, ovId) {
  el.addEventListener('mousedown', e => {
    if (e.target.classList.contains('ov-resize') || e.target.classList.contains('ov-delete') ||
        e.target.tagName === 'TEXTAREA') return;
    e.preventDefault();
    const rect = $('lightbox-canvas').getBoundingClientRect();
    const sx = e.clientX, sy = e.clientY;
    const ox = parseFloat(el.style.left), oy = parseFloat(el.style.top);
    function move(ev) {
      el.style.left = Math.max(0, Math.min(90, ox + (ev.clientX - sx) / rect.width * 100))  + '%';
      el.style.top  = Math.max(0, Math.min(90, oy + (ev.clientY - sy) / rect.height * 100)) + '%';
    }
    function up() {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
      _saveOverlayPos(ovId, parseFloat(el.style.left), parseFloat(el.style.top));
    }
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
}
function _initResize(el, ovId) {
  const h = el.querySelector('.ov-resize'); if (!h) return;
  h.addEventListener('mousedown', e => {
    e.preventDefault(); e.stopPropagation();
    const rect = $('lightbox-canvas').getBoundingClientRect();
    const sx = e.clientX, sy = e.clientY;
    const ow = parseFloat(el.style.width), oh = parseFloat(el.style.height);
    function move(ev) {
      el.style.width  = Math.max(8, ow + (ev.clientX - sx) / rect.width * 100)  + '%';
      el.style.height = Math.max(6, oh + (ev.clientY - sy) / rect.height * 100) + '%';
    }
    function up() {
      document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
      _saveOverlaySize(ovId, parseFloat(el.style.width), parseFloat(el.style.height));
    }
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  });
}
const _put = (id, body) => fetch(`/api/overlay/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const _saveOverlayPos     = (id, x, y) => _put(id, { pos_x_pct: x, pos_y_pct: y });
const _saveOverlaySize    = (id, w, h) => _put(id, { width_pct: w, height_pct: h });
const _saveOverlayContent = (id, content) => _put(id, { content });
async function deleteOverlay(ovId, el) { el.remove(); await fetch(`/api/overlay/${ovId}`, { method: 'DELETE' }); }

// ── add overlays ─────────────────────────────────────────────────────────────
async function _createOverlay(payload) {
  const d = await fetch(`/api/track/${lbTrackId}/overlays`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }).then(r => r.json());
  const layer = $('lightbox-ov-layer');
  const el = _buildOverlayEl(Object.assign({ id: d.id, rotation: 0, z_index: 1 }, payload));
  layer.appendChild(el);
  _initDrag(el, d.id); _initResize(el, d.id);
  return { d, el };
}
async function lbAddText() {
  if (!lbTrackId) return;
  const content = JSON.stringify({ text: '', font: "'EB Garamond', serif", color: '#2e2718' });
  const { el } = await _createOverlay({ overlay_type: 'text', content, pos_x_pct: 25, pos_y_pct: 40, width_pct: 50, height_pct: 16, place_id: _placeId() });
  el.querySelector('.ov-text-input')?.focus();
}
async function lbAddPostit() {
  if (!lbTrackId) return;
  const { el } = await _createOverlay({ overlay_type: 'postit', content: '', pos_x_pct: 10, pos_y_pct: 10, width_pct: 35, height_pct: 28, color: '#fef08a', place_id: _placeId() });
  el.querySelector('textarea')?.focus();
}
async function lbAddSticker(imageUrl) {
  if (!lbTrackId) return;
  lbCloseStickerPanel();
  await _createOverlay({ overlay_type: 'sticker', content: imageUrl, pos_x_pct: 20, pos_y_pct: 20, width_pct: 28, height_pct: 28, place_id: _placeId() });
}
function lbPickImage() { $('lb-image-input').click(); }
async function lbUploadImage(input) {
  if (!input.files[0] || !lbTrackId) return;
  const fd = new FormData(); fd.append('image', input.files[0]);
  const upData = await fetch('/api/overlay-image-upload', { method: 'POST', body: fd }).then(r => r.json());
  if (!upData.ok) { _toast('Upload failed', true); return; }
  await _createOverlay({ overlay_type: 'image', content: upData.url, pos_x_pct: 15, pos_y_pct: 15, width_pct: 40, height_pct: 40, place_id: _placeId() });
  input.value = '';
}

// ── cover colour (blank-art records) ─────────────────────────────────────────
function lbCoverColourLive(hex) {
  $('lb-art-placeholder').style.background = `linear-gradient(135deg, ${hex}cc, ${hex}44)`;
}
async function lbCoverColourSave(hex) {
  if (!lbTrackId) return;
  await fetch(`/api/track/${lbTrackId}/update`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ colour_code: hex }) });
  if (_ctx.track) _ctx.track.colour_code = hex;
}

// ── pen / draw — each stroke is its own 'drawing' overlay ────────────────────
function lbBuildPenSwatches() {
  const wrap = $('lb-pen-swatches');
  if (!wrap || wrap.dataset.built) return;
  wrap.innerHTML = '';
  LB_PEN_PALETTE.forEach(c => {
    const b = document.createElement('button');
    b.className = 'lb-pen-swatch' + (c === lbPenColor ? ' active' : '');
    b.dataset.c = c; b.style.background = c; b.title = c;
    b.onclick = () => lbSetPenColor(c);
    wrap.appendChild(b);
  });
  wrap.dataset.built = '1';
}
function lbSetPenColor(c) {
  lbPenColor = c;
  root.querySelectorAll('.lb-pen-swatch').forEach(s => s.classList.toggle('active', s.dataset.c === c));
}
function lbSetPenWidth(w) {
  lbPenWidth = w;
  root.querySelectorAll('.lb-pen-width[data-w]').forEach(b => b.classList.toggle('active', parseFloat(b.dataset.w) === w));
}
function lbTogglePen() {
  lbPenMode = !lbPenMode;
  lbBuildPenSwatches();
  const btn = $('lb-pen-btn'), panel = $('lb-pen-panel'), canvas = $('lightbox-canvas');
  if (!btn || !panel || !canvas) return;
  btn.classList.toggle('active', lbPenMode);
  panel.style.display = lbPenMode ? 'inline-flex' : 'none';
  canvas.classList.toggle('pen-mode', lbPenMode);
  if (lbPenMode) { lbCloseStickerPanel(); _lbAttachDrawHandlers(); }
  else { _lbDetachDrawHandlers(); }
}
function _lbCanvasPctFromEvent(ev) {
  const r = $('lightbox-canvas').getBoundingClientRect();
  return [
    Math.max(0, Math.min(100, ((ev.clientX - r.left) / r.width)  * 100)),
    Math.max(0, Math.min(100, ((ev.clientY - r.top)  / r.height) * 100)),
  ];
}
function _lbDrawStart(ev) {
  if (!lbPenMode || !lbTrackId) return;
  if (ev.button !== undefined && ev.button !== 0) return;
  ev.preventDefault();
  const canvas = $('lightbox-canvas');
  try { canvas.setPointerCapture && canvas.setPointerCapture(ev.pointerId); } catch (_) {}
  const [x, y] = _lbCanvasPctFromEvent(ev);
  const svgNS = 'http://www.w3.org/2000/svg';
  const svgEl = document.createElementNS(svgNS, 'svg');
  svgEl.setAttribute('viewBox', '0 0 100 100');
  svgEl.setAttribute('preserveAspectRatio', 'none');
  svgEl.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:9999;';
  const pl = document.createElementNS(svgNS, 'polyline');
  pl.setAttribute('fill', 'none'); pl.setAttribute('stroke', lbPenColor);
  pl.setAttribute('stroke-width', String(lbPenWidth / 2));
  pl.setAttribute('stroke-linecap', 'round'); pl.setAttribute('stroke-linejoin', 'round');
  pl.setAttribute('vector-effect', 'non-scaling-stroke');
  pl.setAttribute('points', `${x.toFixed(2)},${y.toFixed(2)}`);
  svgEl.appendChild(pl); canvas.appendChild(svgEl);
  _lbDrawing = { points: [[x, y]], svgEl, polyline: pl, color: lbPenColor, width: lbPenWidth };
}
function _lbDrawMove(ev) {
  if (!_lbDrawing) return;
  ev.preventDefault();
  const [x, y] = _lbCanvasPctFromEvent(ev);
  const pts = _lbDrawing.points, last = pts[pts.length - 1];
  if (Math.hypot(x - last[0], y - last[1]) < 0.25) return;
  pts.push([x, y]);
  _lbDrawing.polyline.setAttribute('points', pts.map(p => p[0].toFixed(2) + ',' + p[1].toFixed(2)).join(' '));
}
async function _lbDrawEnd() {
  if (!_lbDrawing) return;
  const stroke = _lbDrawing; _lbDrawing = null;
  if (stroke.points.length < 2) stroke.points.push([stroke.points[0][0] + 0.5, stroke.points[0][1] + 0.5]);
  if (stroke.svgEl && stroke.svgEl.parentNode) stroke.svgEl.parentNode.removeChild(stroke.svgEl);
  const content = JSON.stringify({ points: stroke.points, color: stroke.color, width: stroke.width });
  try {
    const { d } = await _createOverlay({ overlay_type: 'drawing', content, pos_x_pct: 0, pos_y_pct: 0, width_pct: 100, height_pct: 100, color: stroke.color, place_id: _placeId() });
    lbStrokeUndoStack.push(d.id);
  } catch (e) { _toast('Could not save stroke', true); }
}
function _lbDrawCancel() {
  if (!_lbDrawing) return;
  if (_lbDrawing.svgEl && _lbDrawing.svgEl.parentNode) _lbDrawing.svgEl.parentNode.removeChild(_lbDrawing.svgEl);
  _lbDrawing = null;
}
function _lbAttachDrawHandlers() {
  if (_lbHandlersOn) return;
  const c = $('lightbox-canvas'); if (!c) return;
  c.addEventListener('pointerdown', _lbDrawStart);
  c.addEventListener('pointermove', _lbDrawMove);
  c.addEventListener('pointerup',   _lbDrawEnd);
  c.addEventListener('pointercancel', _lbDrawCancel);
  c.addEventListener('pointerleave',  _lbDrawEnd);
  _lbHandlersOn = true;
}
function _lbDetachDrawHandlers() {
  if (!_lbHandlersOn) return;
  const c = $('lightbox-canvas'); if (!c) return;
  c.removeEventListener('pointerdown', _lbDrawStart);
  c.removeEventListener('pointermove', _lbDrawMove);
  c.removeEventListener('pointerup',   _lbDrawEnd);
  c.removeEventListener('pointercancel', _lbDrawCancel);
  c.removeEventListener('pointerleave',  _lbDrawEnd);
  _lbHandlersOn = false;
}
async function lbUndoStroke() {
  while (lbStrokeUndoStack.length) {
    const oid = lbStrokeUndoStack.pop();
    const el  = root.querySelector(`.overlay-item[data-ovid="${oid}"]`);
    if (el) { el.remove(); try { await fetch(`/api/overlay/${oid}`, { method: 'DELETE' }); } catch (_) {} return; }
  }
}
async function lbEraseAllDrawings() {
  const drawings = root.querySelectorAll('#lightbox-ov-layer .overlay-drawing');
  if (!drawings.length) return;
  if (!confirm(`Erase ${drawings.length} drawing${drawings.length === 1 ? '' : 's'} from this cover?`)) return;
  for (const el of drawings) {
    const oid = el.dataset.ovid; el.remove();
    try { await fetch(`/api/overlay/${oid}`, { method: 'DELETE' }); } catch (_) {}
  }
  lbStrokeUndoStack = [];
}

// ── sticker library ──────────────────────────────────────────────────────────
function lbToggleStickerPanel() {
  const sb = $('lb-sticker-sidebar');
  if (sb.classList.contains('open')) lbCloseStickerPanel();
  else { sb.classList.add('open'); $('lb-sticker-btn').classList.add('active'); loadStickerGrid(); }
}
function lbCloseStickerPanel() {
  $('lb-sticker-sidebar')?.classList.remove('open');
  $('lb-sticker-btn')?.classList.remove('active');
}
async function loadStickerGrid() {
  const grid = $('lb-sticker-grid'); if (!grid) return;
  const data = await fetch('/api/stickers').then(r => r.json());
  const stickers = data.stickers || [];
  if (!stickers.length) {
    grid.innerHTML = `<div style="grid-column:span 2;font-size:0.78rem;color:var(--muted2);padding:10px;text-align:center;">No stickers yet.<br>Add one below.</div>`;
    return;
  }
  grid.innerHTML = '';
  stickers.forEach(s => {
    const d = document.createElement('div');
    d.className = 'cludach-sticker-thumb'; d.title = s.name;
    d.innerHTML = `<img src="${s.image_path}" alt=""><button class="cludach-sticker-thumb__del" title="Remove">✕</button>`;
    d.onclick = () => lbAddSticker(s.image_path);
    d.querySelector('.cludach-sticker-thumb__del').onclick = (e) => { e.stopPropagation(); deleteSticker(s.id); };
    grid.appendChild(d);
  });
}
async function uploadSticker(input) {
  if (!input.files[0]) return;
  const fd = new FormData();
  fd.append('image', input.files[0]);
  fd.append('name', input.files[0].name.replace(/\.[^.]+$/, ''));
  const res = await fetch('/api/stickers', { method: 'POST', body: fd });
  if (res.ok) { loadStickerGrid(); _toast('Sticker added'); }
  input.value = '';
}
async function deleteSticker(id) { await fetch(`/api/sticker/${id}`, { method: 'DELETE' }); loadStickerGrid(); }

window.MRLightbox = {
  open, close,
  isOpen: () => !!(root && root.classList.contains('open')),
};
})();
