// =============================================================
// r3d_atmosphere.js — "✦ make this place yours", drawn NATIVELY in the 3D room.
//
// The atmosphere designer used to be reachable only from place.html's edit
// modal — chrome the 3D build never shows, so in P1 the room felt
// un-personalisable (Daithí's actual complaint). This is the room-native door:
// mood + ground tint + ambient sound, LIVE-applied to the running scene via
// window.MRRoom (exposed in room3d.html) and persisted to the SAME place
// fields the 2D modal writes (PATCH /api/place/<id> + /ambient endpoints).
//
// Scope v1: the things the 3D room actually reflects today — the tint
// (PLACE.theme_bg → ROOM_BG) + the ambient loop. Fonts/background-image come
// later (see project_play_and_place). No new backend; frozen contract reused.
// =============================================================
(function () {
'use strict';

// Mirror of place.html's PLACE_MOODS (the named looks). Kept in sync by hand
// until the panels share one module (native-panel STEP 8). Only the fields the
// room uses — bg + the fonts we persist alongside — are needed here.
const MOODS = [
  { key: 'peat_fire',     label: 'Peat fire',       bg: '#3a2a1a', title: 'celtic',   body: 'garamond' },
  { key: 'forest_dawn',   label: 'Forest dawn',     bg: '#b5c2b3', title: 'cinzel',   body: 'garamond' },
  { key: 'midnight_rave', label: 'Midnight rave',   bg: '#1a1f3a', title: 'inter',    body: 'inter' },
  { key: 'candlelit',     label: 'Candlelit pub',   bg: '#3d2c18', title: 'imfell',   body: 'imfell' },
  { key: 'sea_cave',      label: 'Sea cave',        bg: '#1f3236', title: 'garamond', body: 'garamond' },
  { key: 'daylight',      label: 'Daylight',        bg: '#e7d9ba', title: 'celtic',   body: 'inter' },
  { key: 'cathedral',     label: 'Cathedral hush',  bg: '#272332', title: 'cinzel',   body: 'imfell' },
];
const MOOD_BY_KEY = Object.fromEntries(MOODS.map(m => [m.key, m]));

const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const isHex = h => h && /^#[0-9a-fA-F]{6}$/.test(h);

function injectStyles() {
  if (document.getElementById('r3da-style')) return;
  const s = document.createElement('style'); s.id = 'r3da-style';
  s.textContent = `
  .r3da{ position:fixed; inset:0; z-index:160; background:rgba(6,4,2,.55);
    display:flex; align-items:center; justify-content:center; padding:26px;
    font-family:var(--font-sans,'Inter',system-ui,sans-serif); }
  .r3da__card{ width:420px; max-width:100%; max-height:88vh; overflow-y:auto;
    padding:26px 26px 22px; border-radius:18px; color:#e9dfca;
    background:linear-gradient(180deg,#16120c,#100d09);
    border:1px solid rgba(245,230,176,.2); box-shadow:0 30px 80px rgba(0,0,0,.7); }
  .r3da__title{ font-family:"Uncial Antiqua","EB Garamond",serif; font-size:1.5rem; color:#f0d98a; margin:0 0 3px; }
  .r3da__sub{ font-size:.8rem; color:#8a8067; margin:0 0 20px; line-height:1.5; }
  .r3da__h{ font-family:var(--font-mono,monospace); font-size:.6rem; letter-spacing:1.6px;
    text-transform:uppercase; color:#8a8067; margin:20px 0 9px; }
  .r3da__moods{ display:grid; grid-template-columns:repeat(2,1fr); gap:7px; }
  .r3da__mood{ cursor:pointer; display:flex; align-items:center; gap:9px; text-align:left;
    padding:8px 10px; border-radius:10px; background:rgba(255,255,255,.03);
    border:1px solid rgba(245,230,176,.14); color:#e4dac1; font-size:.84rem; }
  .r3da__mood:hover{ border-color:rgba(245,230,176,.5); }
  .r3da__mood.is-on{ border-color:rgba(240,217,138,.85); background:rgba(240,217,138,.1); }
  .r3da__swatch{ width:20px; height:20px; border-radius:6px; flex:0 0 auto; border:1px solid rgba(255,255,255,.18); }
  .r3da__tint{ display:flex; align-items:center; gap:11px; }
  .r3da__tint input[type=color]{ width:46px; height:38px; padding:0; border:1px solid rgba(245,230,176,.2);
    border-radius:9px; background:none; cursor:pointer; }
  .r3da__hex{ flex:1; font:inherit; font-family:var(--font-mono,monospace); font-size:.82rem; color:#f3ead0;
    background:rgba(28,22,15,.8); border:1px solid rgba(245,230,176,.2); border-radius:8px; padding:8px 11px; outline:none; }
  .r3da__hex:focus{ border-color:rgba(245,230,176,.5); }
  .r3da__clearT{ background:none; border:1px solid rgba(245,230,176,.2); color:#bcae8e; cursor:pointer;
    border-radius:8px; padding:8px 10px; font-size:.74rem; } .r3da__clearT:hover{ color:#f5e6b0; }
  .r3da__amb{ font-size:.82rem; color:#cdbf9f; }
  .r3da__ambname{ color:#e4dac1; font-style:italic; }
  .r3da__ambrow{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
  .r3da__btn{ cursor:pointer; background:none; border:1px solid rgba(245,230,176,.22); color:#bcae8e;
    border-radius:8px; padding:7px 12px; font-size:.76rem; }
  .r3da__btn:hover{ color:#f5e6b0; border-color:rgba(245,230,176,.5); }
  .r3da__btn--danger{ color:#cf9a8e; border-color:rgba(207,154,142,.32); }
  .r3da__btn--danger:hover{ color:#f0b8a8; border-color:rgba(207,154,142,.65); }
  .r3da__urlin{ width:100%; margin-top:9px; font:inherit; font-family:var(--font-mono,monospace); font-size:.78rem;
    color:#f3ead0; background:rgba(28,22,15,.8); border:1px solid rgba(245,230,176,.2); border-radius:8px; padding:8px 11px; outline:none; }
  .r3da__vol{ display:flex; align-items:center; gap:11px; margin-top:12px; }
  .r3da__vol input[type=range]{ flex:1; accent-color:#d8b25a; }
  .r3da__vol span{ font-size:.74rem; color:#8a8067; }
  .r3da__foot{ display:flex; justify-content:flex-end; gap:9px; margin-top:24px;
    padding-top:16px; border-top:1px solid rgba(245,230,176,.12); }
  .r3da__save{ background:rgba(240,217,138,.14); border-color:rgba(240,217,138,.55); color:#f3ead0; }
  .r3da__save:hover{ background:rgba(240,217,138,.22); }`;
  document.head.appendChild(s);
}

function close() { const x = document.getElementById('r3da'); if (x) x.remove(); document.removeEventListener('keydown', onKey, true); }
function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); cancel(); } }

let _orig = null;          // snapshot for Cancel
let _imgTouched = false;   // did the user upload/clear a backdrop this session?
let _ambTouched = false;   // …or change the ambient sound? (both persist immediately)

function cancel() {
  const R = window.MRRoom;
  if (R && _orig) {                                  // put the running scene back
    R.applyTint(_orig.tint || null);
    R.applyAmbient(_orig.ambient || null, _orig.vol);
    if (R.applyBackdrop) R.applyBackdrop(_orig.image || null);
    R.previewAmbient(false);
    // the ambient/background upload+clear endpoints persist immediately, so a
    // true Cancel must also put the DB back — else the "cancelled" change
    // reappears on the next room load. (Volume/tint/mood only persist on Save.)
    const patch = {};
    if (_ambTouched) patch.ambient_audio_path = _orig.ambient || '';
    if (_imgTouched) patch.room_bg_path = _orig.image || '';
    if (_orig.id && Object.keys(patch).length)
      fetch('/api/place/' + _orig.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch) }).catch(() => {});
  }
  close();
}

function open() {
  const R = window.MRRoom; if (!R || !R.place) return;
  injectStyles();
  const p = R.place;
  const tint = R.currentTint();
  // prefer the saved mood; fall back to matching the tint to a preset so the
  // chip highlights correctly even if the payload didn't carry theme_mood
  let mood = p.theme_mood || '';
  if (!mood && isHex(tint)) { const hit = MOODS.find(m => m.bg.toLowerCase() === tint.toLowerCase()); if (hit) mood = hit.key; }
  _orig = { id: p.id, tint: isHex(tint) ? tint : null, ambient: p.ambient_audio_path || null,
            vol: (p.ambient_audio_volume == null) ? 0.35 : +p.ambient_audio_volume,
            mood: mood, image: p.room_bg_path || null };
  _imgTouched = false; _ambTouched = false;
  let chosenMood = _orig.mood;
  let curTint = _orig.tint;
  let curAmbient = _orig.ambient;
  let curImage = _orig.image;

  const ov = document.createElement('div'); ov.id = 'r3da'; ov.className = 'r3da';
  const ambName = a => a ? (a.split('/').pop() || a) : 'None set.';
  ov.innerHTML = `<div class="r3da__card">
    <h2 class="r3da__title">✦ make this place yours</h2>
    <p class="r3da__sub">The room takes on the colour and sound you give it. Changes show live; Save keeps them.</p>

    <div class="r3da__h">Mood</div>
    <div class="r3da__moods">
      ${MOODS.map(m => `<button class="r3da__mood${chosenMood === m.key ? ' is-on' : ''}" data-mood="${m.key}">
        <span class="r3da__swatch" style="background:${m.bg}"></span>${esc(m.label)}</button>`).join('')}
      <button class="r3da__mood${!chosenMood ? ' is-on' : ''}" data-mood=""><span class="r3da__swatch" style="background:#140f0a"></span>None</button>
    </div>

    <div class="r3da__h">Ground tint</div>
    <div class="r3da__tint">
      <input type="color" id="r3da-color" value="${isHex(curTint) ? curTint : '#3a2a1a'}">
      <input type="text" class="r3da__hex" id="r3da-hex" placeholder="(default dark)" value="${isHex(curTint) ? curTint : ''}">
      <button class="r3da__clearT" data-act="clear-tint" title="Back to the default dark">reset</button>
    </div>

    <div class="r3da__h">Ambient sound</div>
    <div class="r3da__amb">Now: <span class="r3da__ambname" id="r3da-ambname">${esc(ambName(curAmbient))}</span></div>
    <div class="r3da__ambrow">
      <label class="r3da__btn" style="cursor:pointer">↑ upload<input type="file" accept="audio/*" id="r3da-ambfile" hidden></label>
      <button class="r3da__btn" data-act="amb-preview" id="r3da-ambprev">▶ preview</button>
      <button class="r3da__btn r3da__btn--danger" data-act="amb-clear">clear</button>
    </div>
    <input type="text" class="r3da__urlin" id="r3da-amburl" placeholder="…or paste an audio URL, then Enter">
    <div class="r3da__vol"><span>Volume</span><input type="range" id="r3da-vol" min="0" max="1" step="any" value="${_orig.vol}"></div>

    <div class="r3da__h">Background image</div>
    <div class="r3da__amb">Now: <span class="r3da__ambname" id="r3da-bgname">${esc(curImage ? (curImage.split('/').pop() || curImage) : 'None set.')}</span></div>
    <div class="r3da__ambrow">
      <label class="r3da__btn" style="cursor:pointer">↑ upload<input type="file" accept="image/*" id="r3da-bgfile" hidden></label>
      <button class="r3da__btn r3da__btn--danger" data-act="bg-clear">clear</button>
    </div>

    <div class="r3da__foot">
      <button class="r3da__btn" data-act="cancel">Cancel</button>
      <button class="r3da__btn r3da__save" data-act="save">Save</button>
    </div>
  </div>`;
  document.body.appendChild(ov);
  document.addEventListener('keydown', onKey, true);

  const $ = sel => ov.querySelector(sel);
  const colorEl = $('#r3da-color'), hexEl = $('#r3da-hex'), prevBtn = $('#r3da-ambprev'), ambNameEl = $('#r3da-ambname');
  const bgNameEl = $('#r3da-bgname');
  let previewing = false;
  function setBackground(url) {
    curImage = url || null; _imgTouched = true;
    bgNameEl.textContent = curImage ? (curImage.split('/').pop() || curImage) : 'None set.';
    R.applyBackdrop(curImage);
  }

  function setMoodSelected(key) {
    chosenMood = key;
    ov.querySelectorAll('.r3da__mood').forEach(b => b.classList.toggle('is-on', (b.dataset.mood || '') === (key || '')));
  }
  function applyTint(hex) { curTint = isHex(hex) ? hex : null; R.applyTint(curTint); }
  function setAmbient(path) {
    curAmbient = path || null; _ambTouched = true; ambNameEl.textContent = ambName(curAmbient);
    R.applyAmbient(curAmbient, parseFloat($('#r3da-vol').value) || 0.35);
    if (!curAmbient) { previewing = false; prevBtn.textContent = '▶ preview'; }
  }

  // mood chips → fill the tint with the preset's bg (the room only reflects the
  // colour; fonts are persisted on Save for parity with the 2D theme)
  ov.addEventListener('click', e => {
    const mood = e.target.closest('[data-mood]');
    if (mood) {
      const key = mood.dataset.mood; const m = MOOD_BY_KEY[key];
      setMoodSelected(key);
      if (m) { colorEl.value = m.bg; hexEl.value = m.bg; applyTint(m.bg); }
      return;
    }
    const act = e.target.closest('[data-act]'); if (!act) return;
    const a = act.dataset.act;
    if (a === 'clear-tint') { colorEl.value = '#3a2a1a'; hexEl.value = ''; applyTint(null); setMoodSelected(''); }
    if (a === 'amb-clear') { fetch('/api/place/' + p.id + '/ambient', { method: 'DELETE' }).catch(() => {}); setAmbient(null); }
    if (a === 'bg-clear') { fetch('/api/place/' + p.id + '/background', { method: 'DELETE' }).catch(() => {}); setBackground(null); }
    if (a === 'amb-preview') {
      previewing = !previewing; prevBtn.textContent = previewing ? '⏸ stop' : '▶ preview';
      R.previewAmbient(previewing);
    }
    if (a === 'cancel') return cancel();
    if (a === 'save') return save();
    if (e.target === ov) return cancel();
  });
  ov.addEventListener('pointerdown', e => { if (e.target === ov) cancel(); });

  colorEl.addEventListener('input', () => { hexEl.value = colorEl.value; applyTint(colorEl.value); setMoodSelected(''); });
  hexEl.addEventListener('input', () => { if (isHex(hexEl.value)) { colorEl.value = hexEl.value; applyTint(hexEl.value); setMoodSelected(''); } });
  $('#r3da-vol').addEventListener('input', e => R.setAmbientVolume(parseFloat(e.target.value) || 0));
  $('#r3da-amburl').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); const u = e.target.value.trim(); if (u) setAmbient(u); }
  });
  $('#r3da-ambfile').addEventListener('change', async e => {
    const f = e.target.files && e.target.files[0]; if (!f) return;
    ambNameEl.textContent = 'uploading…';
    const fd = new FormData(); fd.append('audio', f);
    const r = await fetch('/api/place/' + p.id + '/ambient', { method: 'POST', body: fd }).then(x => x.json()).catch(() => null);
    if (r && r.ambient_audio_path) setAmbient(r.ambient_audio_path);
    else ambNameEl.textContent = ambName(curAmbient);
  });
  $('#r3da-bgfile').addEventListener('change', async e => {
    const f = e.target.files && e.target.files[0]; if (!f) return;
    bgNameEl.textContent = 'uploading…';
    const fd = new FormData(); fd.append('image', f);
    const r = await fetch('/api/place/' + p.id + '/background', { method: 'POST', body: fd }).then(x => x.json()).catch(() => null);
    if (r && r.image_path) setBackground(r.image_path);
    else bgNameEl.textContent = curImage ? (curImage.split('/').pop() || curImage) : 'None set.';
  });

  async function save() {
    R.previewAmbient(false);
    const m = MOOD_BY_KEY[chosenMood];
    const body = {
      theme_mood: chosenMood || '',
      theme_bg: curTint || '',
      ambient_audio_path: curAmbient || '',
      ambient_audio_volume: parseFloat($('#r3da-vol').value) || 0.35,
    };
    if (m) { body.theme_font_title = m.title; body.theme_font_body = m.body; }
    const saveBtn = $('[data-act="save"]'); saveBtn.textContent = 'saving…';
    const ok = await fetch('/api/place/' + p.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) }).then(r => r.ok).catch(() => false);
    if (ok) { _orig = null; close(); }          // committed → no revert
    else { saveBtn.textContent = '✗ failed'; setTimeout(() => { saveBtn.textContent = 'Save'; }, 1800); }
  }
}

window.MRAtmosphere = { open };
})();
