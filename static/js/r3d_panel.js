// =============================================================
// r3d_panel.js — the track detail panel, drawn NATIVELY inside the 3D room
// instead of an iframe over /place?panelonly=1 (the "2D pop-up over the world"
// feel Daithí rejected). Same backend contract as place.html: one payload from
// GET /api/track/<id>, edits as small POSTs to the SAME frozen endpoints.
//
// PORT (see project_native_panel memory). Behind window.MR_NATIVE_PANEL.
//   STEP 1 — native read-only render.
//   STEP 2 — editing: click-to-edit metadata + links, write-to-file, BPM/key
//     verify+edit+fix popover, the rekordbox flick.
//   STEP 3 — genres / tags (add / remove / suggest).
//   STEP 4 — native cover picker (◧ candidates + ↑ upload).
//   STEP 5 — file versions (play→room player, reveal, set-primary, delete),
//     Studio / DAW sessions, place membership (add / remove), track removal.
//     Play cues on the Seinnteoir via window.MRRoomSync.cueFile; removals call
//     window.MRRoomSync.trackGone.
//   STEP 6 (this) — timestamped NOTES + voice: render/add/delete notes, ⊙ stamp
//     reads the room player's playhead (/api/seinnteoir/state) when THIS record
//     is playing, and voice notes via MediaRecorder → /api/track/<id>/voice_note
//     (mic tested live, never headless).
//   STILL TODO: cover lightbox (7), de-dup the two copies into one shared module
//     then flip the flag ON + drop the iframe (8).
// =============================================================
(function () {
'use strict';

function injectStyles() {
  if (document.getElementById('r3dp-style')) return;
  const s = document.createElement('style'); s.id = 'r3dp-style';
  s.textContent = `
  .r3dp{ font-family:var(--font-sans,'Inter',system-ui,sans-serif); color:#e9dfca; height:100%;
    overflow-y:auto; -webkit-overflow-scrolling:touch; padding:56px 26px 120px;
    background:linear-gradient(180deg,#12100c,#0d0b07); }
  /* no big cover in the panel — the art lives on the left of the screen. Just a
     compact row of cover actions. */
  .r3dp__coverbar{ display:flex; flex-wrap:wrap; gap:7px; }
  .r3dp__coverbar label{ cursor:pointer; }
  /* in-panel player — wraps cleanly inside the panel, never spills past the edge */
  .r3dp__player{ display:flex; align-items:center; gap:9px 11px; flex-wrap:wrap; margin:18px 0 6px;
    padding:13px 15px; border-radius:13px; box-sizing:border-box; max-width:100%;
    background:rgba(245,230,176,.05); border:1px solid rgba(245,230,176,.12); }
  .r3dp__pbtn{ appearance:none; cursor:pointer; border:1px solid rgba(245,230,176,.2); border-radius:9px;
    background:rgba(255,255,255,.04); color:#e9dfca; font-family:inherit; font-size:1rem; line-height:1;
    width:38px; height:38px; display:inline-flex; align-items:center; justify-content:center; transition:all .15s; flex:0 0 auto; }
  .r3dp__pbtn:hover{ border-color:var(--gold,#d4a050); color:#f5e6b0; }
  .r3dp__pbtn.playing{ border-color:var(--gold,#d4a050); color:#f5e6b0; }
  .r3dp__pbtn--ho{ width:auto; padding:0 13px; font-size:.82rem; }
  .r3dp__ptime{ font-family:var(--font-mono,monospace); font-size:.72rem; color:#b9a878; min-width:74px;
    text-align:center; font-variant-numeric:tabular-nums; flex:0 0 auto; }
  .r3dp__pscrub{ flex:1 1 130px; min-width:80px; height:5px; accent-color:var(--gold,#d4a050); cursor:pointer; }
  .r3dp__pvol{ display:inline-flex; align-items:center; gap:5px; font-size:.74rem; color:#8a8067; flex:0 0 auto; }
  .r3dp__pvol input{ width:54px; height:3px; accent-color:var(--gold,#d4a050); cursor:pointer; }
  .r3dp__covers{ margin-top:11px; }
  .r3dp__covgrid{ display:grid; grid-template-columns:repeat(3,1fr); gap:7px; }
  .r3dp__cov{ cursor:pointer; padding:0; border-radius:8px; overflow:hidden; background:#1b1710;
    border:1px solid rgba(245,230,176,.14); position:relative; aspect-ratio:1; }
  .r3dp__cov img{ width:100%; height:100%; object-fit:cover; display:block; }
  .r3dp__cov.is-current{ border-color:rgba(245,230,176,.7); }
  .r3dp__cov__lbl{ position:absolute; left:0; right:0; bottom:0; font-size:.56rem; padding:3px 5px;
    background:rgba(8,6,4,.78); color:#cdbf9f; text-align:center; }
  .r3dp__covhint{ color:#8a8067; font-size:.76rem; font-style:italic; }
  .r3dp__t{ font-size:1.5rem; line-height:1.25; margin:18px 0 3px; color:#f3ead0; }
  .r3dp__a{ font-size:1.04rem; color:#b9ad93; }
  .r3dp__sec{ margin-top:28px; }
  .r3dp__h{ font-family:var(--font-mono,monospace); font-size:.67rem; letter-spacing:1.6px;
    text-transform:uppercase; color:#8a8067; margin:0 0 11px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  .r3dp__h button{ font-family:var(--font-mono,monospace); font-size:.64rem; letter-spacing:.6px; cursor:pointer;
    background:none; border:1px solid rgba(245,230,176,.22); color:#bcae8e; border-radius:7px; padding:4px 9px; }
  .r3dp__h button:hover{ color:#f5e6b0; border-color:rgba(245,230,176,.5); }
  .r3dp__row{ display:flex; gap:10px; padding:9px 0; border-bottom:1px solid rgba(245,230,176,.07); font-size:.93rem; }
  .r3dp__k{ color:#8a8067; flex:0 0 98px; }
  .r3dp__v{ color:#e4dac1; flex:1; min-width:0; word-break:break-word; }
  .r3dp__v a{ color:#d8b25a; text-decoration:none; } .r3dp__v a:hover{ text-decoration:underline; }
  .r3dp__edit{ cursor:text; border-bottom:1px dashed transparent; }
  .r3dp__edit:hover{ border-bottom-color:rgba(245,230,176,.35); }
  .r3dp__edit:empty::before{ content:'—'; color:#5f5747; }
  .r3dp__in{ width:100%; font:inherit; color:#f3ead0; background:rgba(28,22,15,.85);
    border:1px solid rgba(245,230,176,.45); border-radius:6px; padding:3px 7px; outline:none; }
  .r3dp__t .r3dp__in{ font-size:1.2rem; }
  .r3dp__chips{ display:flex; flex-wrap:wrap; gap:7px; }
  .r3dp__chip{ font-size:.82rem; padding:5px 13px; border-radius:20px; background:rgba(255,255,255,.05);
    border:1px solid rgba(245,230,176,.16); color:#d8cdb1; display:inline-flex; align-items:center; }
  .r3dp__cx{ background:none; border:0; color:#8a8067; cursor:pointer; margin-left:5px; font-size:.7rem; padding:0; line-height:1; }
  .r3dp__cx:hover{ color:#d99; }
  .r3dp__addchip{ font:inherit; font-size:.74rem; color:#e4dac1; background:rgba(28,22,15,.7);
    border:1px dashed rgba(245,230,176,.22); border-radius:20px; padding:4px 11px; outline:none; width:94px; }
  .r3dp__addchip:focus{ border-style:solid; border-color:rgba(245,230,176,.45); }
  .r3dp__sug{ display:flex; flex-wrap:wrap; gap:6px; margin-top:7px; }
  .r3dp__sug__c{ cursor:pointer; font-size:.72rem; padding:3px 10px; border-radius:20px; color:#bcae8e;
    background:rgba(255,255,255,.03); border:1px dashed rgba(245,230,176,.3); }
  .r3dp__sug__c:hover{ color:#f5e6b0; border-style:solid; }
  .r3dp__file{ padding:9px 0; border-bottom:1px solid rgba(245,230,176,.07); font-size:.82rem; }
  .r3dp__fmt{ font-family:var(--font-mono,monospace); font-size:.62rem; letter-spacing:.6px; color:#d8b25a; }
  .r3dp__filemeta{ color:#8a8067; font-size:.74rem; margin-top:2px; }
  .r3dp__bpmkey{ display:flex; gap:30px; }
  .r3dp__big{ font-size:1.5rem; color:#f3ead0; line-height:1; }
  .r3dp__acts{ display:flex; gap:8px; margin-top:8px; flex-wrap:wrap; }
  .r3dp__btn{ font-family:var(--font-mono,monospace); font-size:.7rem; letter-spacing:.5px; cursor:pointer;
    background:none; border:1px solid rgba(245,230,176,.22); color:#bcae8e; border-radius:8px; padding:5px 11px; }
  .r3dp__btn:hover{ color:#f5e6b0; border-color:rgba(245,230,176,.5); }
  .r3dp__btn--on{ color:#9bbf9e; border-color:rgba(155,191,158,.5); }
  .r3dp__sw{ display:inline-block; width:13px; height:13px; border-radius:3px; vertical-align:-2px; margin-right:6px;
    border:1px solid rgba(255,255,255,.2); }
  .r3dp__empty{ color:#6b6253; font-style:italic; font-size:.82rem; }
  .r3dp__wip{ margin-top:24px; font-size:.7rem; color:#6b6253; font-style:italic;
    border-top:1px solid rgba(245,230,176,.1); padding-top:12px; }
  .r3dp-pop{ position:fixed; z-index:140; width:248px; padding:13px; border-radius:13px;
    background:rgba(20,15,9,.99); border:1px solid rgba(245,230,176,.25); box-shadow:0 18px 50px rgba(0,0,0,.6);
    color:#e9dfca; font-size:.8rem; }
  .r3dp-pop__h{ color:#bcae8e; margin-bottom:9px; line-height:1.4; }
  .r3dp-pop__chips{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:9px; }
  .r3dp-pop__chip{ cursor:pointer; background:rgba(255,255,255,.05); border:1px solid rgba(245,230,176,.2);
    color:#e4dac1; border-radius:9px; padding:5px 9px; display:flex; flex-direction:column; align-items:center; gap:1px; }
  .r3dp-pop__chip:hover{ border-color:rgba(245,230,176,.55); }
  .r3dp-pop__chip b{ color:#f5e6b0; } .r3dp-pop__chip span{ font-size:.62rem; color:#8a8067; }
  .r3dp-pop__re{ width:100%; cursor:pointer; background:none; border:1px solid rgba(245,230,176,.2);
    color:#bcae8e; border-radius:8px; padding:6px; font-size:.74rem; }
  .r3dp-pop__re:hover{ color:#f5e6b0; }
  .r3dp__btn--danger{ color:#cf9a8e; border-color:rgba(207,154,142,.32); }
  .r3dp__btn--danger:hover{ color:#f0b8a8; border-color:rgba(207,154,142,.65); }
  .r3dp__filehead{ display:flex; align-items:center; gap:9px; }
  .r3dp__fileacts{ display:flex; gap:5px; margin-left:auto; flex-wrap:wrap; }
  .r3dp__filepath{ color:#6b6253; font-size:.66rem; margin-top:4px; word-break:break-all; line-height:1.4; }
  .r3dp__placerow{ display:flex; justify-content:space-between; align-items:center; gap:8px;
    padding:5px 0; border-bottom:1px solid rgba(245,230,176,.07); font-size:.84rem; color:#e4dac1; }
  .r3dp__placeacts{ display:flex; align-items:center; gap:8px; }
  .r3dp__addplace{ padding-top:9px; }
  .r3dp__addplace select{ width:100%; font:inherit; font-size:.8rem; color:#cdbf9f; cursor:pointer;
    background:rgba(28,22,15,.7); border:1px solid rgba(245,230,176,.18); border-radius:7px; padding:6px 8px; outline:none; }
  .r3dp-confirm{ position:fixed; inset:0; z-index:170; background:rgba(6,4,2,.62);
    display:flex; align-items:center; justify-content:center; padding:24px; }
  .r3dp-confirm__box{ width:340px; max-width:100%; padding:20px; border-radius:15px;
    background:rgba(20,15,9,.99); border:1px solid rgba(245,230,176,.22); box-shadow:0 24px 70px rgba(0,0,0,.7); color:#e9dfca; }
  .r3dp-confirm__t{ font-size:1.04rem; color:#f3ead0; margin-bottom:9px; }
  .r3dp-confirm__m{ font-size:.84rem; color:#bcae8e; line-height:1.55; }
  .r3dp-confirm__m em{ color:#e4dac1; font-style:normal; }
  .r3dp-confirm__acts{ display:flex; justify-content:flex-end; gap:9px; margin-top:18px; }
  .r3dp-confirm__acts .r3dp__btn{ font-size:.72rem; padding:6px 13px; }
  .r3dp__note{ display:grid; grid-template-columns:50px 1fr; gap:10px; padding:8px 0; border-bottom:1px solid rgba(245,230,176,.07); }
  .r3dp__note__ts{ font-family:var(--font-mono,monospace); font-size:.72rem; color:#d8b25a; padding-top:2px; }
  .r3dp__note__ts.is-none{ color:#5f5747; }
  .r3dp__note__body{ font-size:.86rem; color:#e4dac1; line-height:1.45; word-break:break-word; }
  .r3dp__note__trans{ font-size:.8rem; color:#bcae8e; font-style:italic; margin-top:3px; }
  .r3dp__note__vn{ display:flex; align-items:center; gap:8px; margin-top:5px; }
  .r3dp__note__meta{ display:flex; justify-content:space-between; align-items:center; margin-top:4px; }
  .r3dp__note__date{ font-size:.68rem; color:#6b6253; }
  .r3dp__note__del{ background:none; border:0; color:#8a8067; cursor:pointer; font-size:.7rem; padding:0; line-height:1; }
  .r3dp__note__del:hover{ color:#d99; }
  .r3dp__compose{ margin-top:11px; }
  .r3dp__compose textarea{ width:100%; font:inherit; font-size:.85rem; color:#f3ead0; background:rgba(28,22,15,.8);
    border:1px solid rgba(245,230,176,.2); border-radius:8px; padding:8px 10px; outline:none; resize:vertical; min-height:46px; }
  .r3dp__compose textarea:focus{ border-color:rgba(245,230,176,.5); }
  .r3dp__crow{ display:flex; gap:6px; margin-top:7px; align-items:center; flex-wrap:wrap; }
  .r3dp__tsin{ width:62px; font:inherit; font-family:var(--font-mono,monospace); font-size:.76rem; color:#f3ead0; text-align:center;
    background:rgba(28,22,15,.8); border:1px solid rgba(245,230,176,.2); border-radius:7px; padding:5px 7px; outline:none; }
  .r3dp__typesel{ font:inherit; font-size:.76rem; color:#cdbf9f; background:rgba(28,22,15,.7); cursor:pointer;
    border:1px solid rgba(245,230,176,.2); border-radius:7px; padding:5px 7px; outline:none; flex:1; min-width:84px; }
  .r3dp__btn--rec.is-rec{ color:#f0b8a8; border-color:rgba(207,154,142,.7); animation:r3dp-pulse 1.2s ease-in-out infinite; }
  @keyframes r3dp-pulse{ 0%,100%{ box-shadow:0 0 0 0 rgba(207,154,142,.4);} 50%{ box-shadow:0 0 0 6px rgba(207,154,142,0);} }`;
  document.head.appendChild(s);
}

const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const editSpan = (field, value, type) =>
  `<span class="r3dp__v r3dp__edit" data-edit="${field}" data-type="${type || 'text'}">${esc(value)}</span>`;
const row = (k, vHtml) => `<div class="r3dp__row"><span class="r3dp__k">${esc(k)}</span>${vHtml}</div>`;
const editRow = (k, field, value, type) => row(k, editSpan(field, value, type));
const linkRow = (k, field, url) => row(k, url
  ? `<span class="r3dp__v"><a href="${esc(url)}" target="_blank" rel="noopener" data-stop>${esc(url)}</a> ${editSpan(field, url, 'url').replace('r3dp__v ', '')}</span>`
  : editSpan(field, url, 'url'));
const editableChips = (label, arr, kind) =>
  `<div class="r3dp__sec"><div class="r3dp__h">${label}` +
    (kind === 'genre' ? `<button data-act="suggest">✦ suggest</button>` : '') + `</div>` +
  `<div class="r3dp__chips">` +
    arr.map(x => `<span class="r3dp__chip"${x.colour ? ` style="border-color:${esc(x.colour)}99;background:${esc(x.colour)}24;color:#ece1c6"` : ''}>${esc(x.name)}<button class="r3dp__cx" data-act="del-chip" data-kind="${kind}" data-id="${x.id}">✕</button></span>`).join('') +
    `<input class="r3dp__addchip" data-add="${kind}" placeholder="+ ${kind}">` +
  `</div><div class="r3dp__sug" data-sug="${kind}"></div></div>`;

// ── notes (STEP 6) ──────────────────────────────────────────────────────────
const NOTE_ICONS = { cue_point: '🎯', transition: '→', feeling: '✦', technical: '⚙', voice: '🎙', general: '' };
function formatTime(s) { s = +s || 0; return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0'); }
function noteDate(created) {
  try { return new Date(String(created).replace(' ', 'T') + 'Z').toLocaleDateString('en-IE', { day: 'numeric', month: 'short' }); }
  catch (e) { return ''; }
}
function renderNoteRow(n) {
  const icon = NOTE_ICONS[n.note_type] || '';
  const trans = n.whisper_transcript ? `<div class="r3dp__note__trans">${esc(n.whisper_transcript)}</div>`
    : (n.voice_note_path && !n.note_text ? `<div class="r3dp__note__trans">transcribing…</div>` : '');
  const vn = n.voice_note_path
    ? `<div class="r3dp__note__vn"><button class="r3dp__btn" data-act="vn-play" data-id="${n.id}">▶</button>` +
      `<audio id="r3dp-vn-${n.id}" src="/voice_note/${n.id}" preload="none"></audio></div>` : '';
  const body = n.note_text ? `${icon ? icon + ' ' : ''}${esc(n.note_text)}` : (n.voice_note_path ? `${icon} voice note` : '');
  return `<div class="r3dp__note" id="r3dp-note-${n.id}">` +
    `<div class="r3dp__note__ts ${n.audio_timestamp ? '' : 'is-none'}">${esc(n.audio_timestamp || '—')}</div>` +
    `<div><div class="r3dp__note__body">${body}</div>${trans}${vn}` +
    `<div class="r3dp__note__meta"><span class="r3dp__note__date">${esc(noteDate(n.created_at))}</span>` +
    `<button class="r3dp__note__del" data-act="del-note" data-id="${n.id}" title="Delete note">✕</button></div></div></div>`;
}

function render(host, data) {
  const t = data.track || {}, files = data.files || [], analysis = data.analysis || [];
  const genres = data.genres || [], tags = data.tags || [], places = data.places || [], notes = data.notes || [];
  host.dataset.tid = t.id;
  host.__track = t;                       // the lightbox reads art/colour/title from this
  const artV = t.art_v ? ('?v=' + t.art_v) : '';
  // No big cover here — the record's art is already the thing on the left of the
  // screen (click it to draw/annotate). Just the compact cover ACTIONS.
  const art =
    `<div class="r3dp__coverbar">` +
      `<button class="r3dp__btn" data-act="lightbox" title="Open the cover full-screen to draw, sticker & note on it">✎ draw / note on cover</button>` +
      `<button class="r3dp__btn" data-act="covers">◧ change cover</button>` +
      `<label class="r3dp__btn">↑ upload<input type="file" accept="image/*" data-act="upload" hidden></label>` +
      (t.artwork_path
        ? `<button class="r3dp__btn" data-act="cover-verify" title="${t.artwork_verified ? 'Cover already verified' : 'Mark this cover as correct'}">${t.artwork_verified ? '✓ verified' : '✓ verify cover'}</button>` +
          `<button class="r3dp__btn r3dp__btn--danger" data-act="cover-remove" title="Remove this cover">✕ cover</button>`
        : '') +
    `</div><div class="r3dp__covers" id="r3dp-covers" style="display:none"></div>`;

  const meta =
    editRow('Album', 'album', t.album) +
    editRow('Year', 'year', t.year, 'number') +
    editRow('Label', 'label', t.label) +
    editRow('Type', 'source_type', t.source_type) +
    editRow('Found via', 'discovered_via', t.discovered_via) +
    row('Colour', `<span class="r3dp__v"><span class="r3dp__sw" style="background:${esc(t.colour_code || 'transparent')}"></span>${editSpan('colour_code', t.colour_code, 'text').replace('r3dp__v ', '')}</span>`);

  const links =
    linkRow('Spotify', 'spotify_url', t.spotify_url) +
    linkRow('Bandcamp', 'bandcamp_url', t.bandcamp_url) +
    linkRow('SoundCloud', 'soundcloud_url', t.soundcloud_url) +
    linkRow('YouTube', 'youtube_url', t.youtube_url);

  // analysis — Music Room's own (on the primary file) + a rekordbox layer if present.
  const pf = files.find(f => f.is_primary) || files[0] || {};
  host.__pfid = pf.id || null;       // the file the panel player loads

  // the in-panel player (browser <audio>): play / scrub / stamp / hand off to the
  // persistent Player — same as the 2D panel. Only when there's a playable file.
  const playerHtml = pf.id ? `<div class="r3dp__player">` +
      `<button class="r3dp__pbtn" id="r3dp-ptoggle" data-act="p-toggle" title="Play / pause">▶</button>` +
      `<span class="r3dp__ptime" id="r3dp-ptime">0:00 / 0:00</span>` +
      `<input type="range" class="r3dp__pscrub" id="r3dp-pscrub" min="0" max="100" value="0" step="0.1" data-pseek title="Seek">` +
      `<button class="r3dp__pbtn" data-act="p-stamp" id="r3dp-pstamp" title="Stamp the playhead into a note">⊙</button>` +
      `<button class="r3dp__pbtn r3dp__pbtn--ho" data-act="p-handoff" title="Hand this off to the Player and keep it playing from right here — then browse freely while it plays">→ player</button>` +
      `<button class="r3dp__pbtn" data-act="p-cue" title="Cue this track into the Player without playing it here — it joins the queue and waits its turn">＋ cue</button>` +
      `<span class="r3dp__pvol">🔊<input type="range" min="0" max="1" step="any" value="0.8" data-pvol title="Volume"></span>` +
    `</div>` : '';
  const rb = analysis.find(a => a.source === 'rekordbox');
  const block = (src, bpm, keyNote, keyScale, verifiedB, verifiedK, editable) => {
    const fixBtn = editable ? `<button class="r3dp__btn" data-act="bpm-fix">fix</button>` : '';
    const bpmActs = editable ? `<div class="r3dp__acts">` +
        (verifiedB ? '' : `<button class="r3dp__btn" data-act="bpm-verify" data-bpm="${bpm || ''}">✓ verify</button>`) +
        `<button class="r3dp__btn" data-act="bpm-edit">✎</button>${fixBtn}</div>` : '';
    const keyActs = editable ? `<div class="r3dp__acts">` +
        (keyNote && !verifiedK ? `<button class="r3dp__btn" data-act="key-verify" data-note="${esc(keyNote)}" data-scale="${esc(keyScale || '')}">✓ verify</button>` : '') +
        `<button class="r3dp__btn" data-act="key-edit" title="Set the key by hand">✎</button></div>` : '';
    return `<div class="r3dp__bpmkey">
      <div><div class="r3dp__h" style="margin:0 0 3px">BPM${verifiedB ? ' ✓' : ''}</div><div class="r3dp__big">${bpm ? esc(Math.round(bpm)) : '—'}</div>${bpmActs}</div>
      <div><div class="r3dp__h" style="margin:0 0 3px">Key${verifiedK ? ' ✓' : ''}</div><div class="r3dp__big">${keyNote ? esc(keyNote) + (keyScale ? ' ' + esc(keyScale) : '') : '—'}</div>${keyActs}</div>
    </div>`;
  };
  let analysisHtml = '';
  if (rb || pf.bpm || pf.key_note) {
    const mrBlock = `<div id="r3dp-an-mr" style="display:${rb ? 'none' : ''}">${block('mr', pf.bpm, pf.key_note, pf.key_scale, pf.bpm_verified, pf.key_verified, true)}</div>`;
    const rbBlock = rb ? `<div id="r3dp-an-rb">${block('rb', rb.bpm, rb.key_note, rb.key_scale, true, true, false)}</div>` : '';
    const flick = rb ? `<button class="r3dp__btn" data-act="flick">⇄ <span id="r3dp-an-other">Music Room</span></button>` : '';
    analysisHtml = `<div class="r3dp__sec"><div class="r3dp__h">Analysis <span id="r3dp-an-badge">${rb ? 'rekordbox' : ''}</span>${flick}</div>${rbBlock}${mrBlock}</div>`;
  }

  // DSP confirm — when the streaming check found a probable match but it isn't
  // settled yet: confirm it's on a DSP, or mark it as only-here.
  let dspHtml = '';
  if (t.dsp_check_state === 'probable' && t.dsp_probable) {
    let cand = null; try { cand = JSON.parse(t.dsp_probable); } catch (_) {}
    if (cand) {
      const srcName = cand.source === 'itunes' ? 'Apple Music' : 'Deezer';
      dspHtml = `<div class="r3dp__sec"><div class="r3dp__h">On a DSP?</div>` +
        `<div class="r3dp__empty" style="margin-bottom:7px">Likely on ${esc(srcName)} as <span style="color:#e4dac1">${esc(cand.artist || '?')} — ${esc(cand.title || '?')}</span>.</div>` +
        `<div class="r3dp__acts"><button class="r3dp__btn" data-act="dsp-yes">✓ that’s it — on a DSP</button>` +
        `<button class="r3dp__btn" data-act="dsp-no">✕ not it — only here</button></div></div>`;
    }
  }

  // FILE VERSIONS — play (→ room player), reveal, session, set-primary, delete.
  const fileMeta = f => [f.file_size_mb ? f.file_size_mb + ' MB' : '', f.duration_sec ? Math.round(f.duration_sec) + 's' : '',
    f.bit_depth ? f.bit_depth + '-bit' : '', f.sample_rate ? (f.sample_rate / 1000).toFixed(1) + 'kHz' : '',
    f.bitrate_kbps ? f.bitrate_kbps + ' kbps' : ''].filter(Boolean).join(' · ');
  const filesHtml = files.length ? `<div class="r3dp__sec"><div class="r3dp__h">${files.length === 1 ? 'File' : files.length + ' versions'}</div>` +
    files.map(f => {
      const own = t.is_own_work || f.session_path;
      const sessBtn = own ? (f.session_path
        ? `<button class="r3dp__btn" data-act="open-session" data-path="${esc(f.session_path)}" title="Open this version’s Ableton session">♫</button>`
        : `<button class="r3dp__btn" data-act="link-session" data-fid="${f.id}" title="Link the session this version was bounced from">♫ link</button>`) : '';
      return `<div class="r3dp__file"><div class="r3dp__filehead">` +
        `<span class="r3dp__fmt">${esc((f.file_format || '?').toUpperCase())}${f.is_primary ? ' ★' : ''}</span>` +
        `<div class="r3dp__fileacts">` +
          `<button class="r3dp__btn" data-act="play-file" data-fid="${f.id}" title="Cue this version on the player">▶</button>` +
          `<button class="r3dp__btn" data-act="reveal" data-path="${esc(f.file_path || '')}" title="Show in Finder">⤢</button>` +
          sessBtn +
          (f.is_primary ? '' : `<button class="r3dp__btn" data-act="set-primary" data-fid="${f.id}" title="Set as primary">★</button>`) +
          `<button class="r3dp__btn r3dp__btn--danger" data-act="del-file" data-fid="${f.id}" data-fmt="${esc((f.file_format || '').toUpperCase())}" title="Move to Trash">🗑</button>` +
        `</div></div>` +
        `<div class="r3dp__filemeta">${esc(fileMeta(f))}</div>` +
        `<div class="r3dp__filepath">${esc(f.file_path || '')}</div></div>`;
    }).join('') + `</div>` : '';

  // STUDIO — own productions: link / open the DAW session (files are only linked, never moved).
  const studioHtml = t.is_own_work
    ? `<div class="r3dp__sec"><div class="r3dp__h">Studio · my own work</div>` +
      (t.daw_project_path
        ? `<div class="r3dp__filemeta" style="margin-bottom:8px">Project: <span style="color:#e4dac1">${esc(t.daw_project_path.split('/').pop())}</span></div>` +
          `<div class="r3dp__acts"><button class="r3dp__btn" data-act="open-session" data-path="${esc(t.daw_project_path)}">↗ open project</button>` +
          `<button class="r3dp__btn" data-act="link-daw">change…</button></div>`
        : `<div class="r3dp__acts"><span class="r3dp__empty">No project linked.</span><button class="r3dp__btn" data-act="link-daw">link a session</button></div>`) +
      `</div>`
    : `<div class="r3dp__sec"><button class="r3dp__btn" data-act="mark-own" title="Mark this as your own production and link its session">✦ this is my own work</button></div>`;

  // SAMPLES — lineage via MusicBrainz (any track, like the 2D panel).
  const samplesHtml = `<div class="r3dp__sec"><div class="r3dp__h">Samples</div>` +
    `<div class="r3dp__acts"><button class="r3dp__btn" data-act="find-samples" title="Find what this track samples, and what samples it (MusicBrainz, free)">✦ find samples</button></div>` +
    `<div id="r3dp-samples" style="display:none;margin-top:8px;font-size:.82rem"></div></div>`;

  // IN THE FOREST — which places hold this record; add to another, remove from one.
  const placeRows = places.map(p => `<div class="r3dp__placerow"><span style="color:${esc(p.colour_primary || '#e4dac1')}">${esc(p.name)}</span>` +
    `<span class="r3dp__placeacts">${p.moment ? `<span class="r3dp__empty">${esc(p.moment)}</span>` : ''}` +
    (p.is_well ? '' : `<button class="r3dp__cx" data-act="rm-place" data-pid="${p.id}" title="Remove from ${esc(p.name)}">✕</button>`) + `</span></div>`).join('');
  const placesHtml = `<div class="r3dp__sec"><div class="r3dp__h">In the forest</div>${placeRows || '<div class="r3dp__empty">Not placed yet.</div>'}` +
    `<div class="r3dp__addplace"><select data-act="add-place"><option value="">loading places…</option></select></div></div>`;

  // NOTES — timestamped text + voice (the stamp reads the room player's playhead).
  const notesHtml = `<div class="r3dp__sec"><div class="r3dp__h">Notes</div>` +
    `<div class="r3dp__notes" id="r3dp-notes">${notes.length ? notes.map(renderNoteRow).join('') : '<div class="r3dp__empty">No notes yet.</div>'}</div>` +
    `<div class="r3dp__compose">` +
      `<textarea id="r3dp-note-text" rows="2" placeholder="Write a note — ⊙ stamp pins the playhead"></textarea>` +
      `<div class="r3dp__crow">` +
        `<input class="r3dp__tsin" id="r3dp-note-ts" placeholder="0:00">` +
        `<button class="r3dp__btn" data-act="stamp" title="Pin the current playhead (when this record is the one playing)">⊙ stamp</button>` +
        `<select class="r3dp__typesel" id="r3dp-note-type">` +
          `<option value="general">General</option><option value="transition">Transition</option>` +
          `<option value="feeling">Feeling</option><option value="technical">Technical</option><option value="cue_point">Cue</option>` +
        `</select>` +
        `<button class="r3dp__btn r3dp__btn--rec" data-act="rec" title="Record a voice note">🎙</button>` +
        `<button class="r3dp__btn" data-act="add-note">save</button>` +
      `</div></div></div>`;

  // REMOVE — quarantine (recoverable) vs delete (Trash). Both → MRRoomSync.trackGone.
  const removeHtml = `<div class="r3dp__sec" style="margin-top:14px;border-top:1px solid rgba(245,230,176,.12);padding-top:16px">` +
    `<div class="r3dp__h">Remove</div><div class="r3dp__acts">` +
    `<button class="r3dp__btn r3dp__btn--danger" data-act="remove-track" title="Move files to a quarantine folder — not deleted">remove from Music Room</button>` +
    `<button class="r3dp__btn r3dp__btn--danger" data-act="delete-track" title="Move files to Trash">🗑 delete</button></div>` +
    `<div class="r3dp__empty" style="margin-top:7px;line-height:1.5"><em>Remove</em> keeps the file on your drive in a quarantine folder. <em>Delete</em> moves it to Trash.</div></div>`;

  host.innerHTML = art +
    `<div class="r3dp__t">${editSpan('title', t.title || '', 'text').replace('r3dp__v ', '')}</div>` +
    `<div class="r3dp__a">${editSpan('artist_name', t.artist_name || '', 'text').replace('r3dp__v ', '')}</div>` +
    playerHtml +
    `<div class="r3dp__sec"><div class="r3dp__h">Metadata <button data-act="write-tags">↓ write to file</button></div>${meta}</div>` +
    analysisHtml + dspHtml +
    `<div class="r3dp__sec"><div class="r3dp__h">Links</div>${links}</div>` +
    editableChips('Genres', genres, 'genre') + editableChips('Tags', tags, 'tag') +
    placesHtml + studioHtml + samplesHtml + filesHtml + notesHtml + removeHtml;
  fillPlaceOptions(host, places);
}

// ── edit machinery ──────────────────────────────────────────────────────────
function tid(host) { return +host.dataset.tid; }
async function reopen(host) { await open(tid(host), host); }
function roomSync(id) { try { window.MRRoomSync && window.MRRoomSync.trackChanged && window.MRRoomSync.trackChanged(id); } catch (e) {} }

async function save(host, field, value) {
  const id = tid(host);
  await fetch('/api/track/' + id + '/update', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ [field]: value === '' ? null : value }) }).catch(() => {});
  roomSync(id); await reopen(host);
}
async function verify(host, body) {
  const id = tid(host);
  await fetch('/api/track/' + id + '/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body) }).catch(() => {});
  roomSync(id); await reopen(host);
}
function enterEdit(host, span) {
  if (span.querySelector('input')) return;
  const field = span.dataset.edit, type = span.dataset.type || 'text', cur = span.textContent.trim();
  const inp = document.createElement('input'); inp.className = 'r3dp__in';
  inp.type = type === 'number' ? 'number' : (type === 'url' ? 'url' : 'text'); inp.value = (cur === '—' ? '' : cur);
  span.textContent = ''; span.appendChild(inp); inp.focus(); inp.select();
  let done = false;
  const commit = () => { if (done) return; done = true; const v = inp.value.trim();
    if (v !== cur && !(cur === '—' && v === '')) save(host, field, v); else span.textContent = (cur === '—' ? '' : cur); };
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
    if (e.key === 'Escape') { done = true; reopen(host); } });
  inp.addEventListener('blur', commit);
}

// ── BPM correction popover (metrical ratios + re-analyse) ───────────────────
function closePop() { const p = document.getElementById('r3dp-bpm-pop'); if (p) { p.remove(); document.removeEventListener('pointerdown', popOutside, true); } }
function popOutside(e) { const p = document.getElementById('r3dp-bpm-pop'); if (p && !p.contains(e.target)) closePop(); }
function openBpmFix(host, bpm, ev) {
  if (ev) ev.stopPropagation();
  closePop(); bpm = parseFloat(bpm) || 0;
  const ratios = [['½', .5], ['⅔', 2 / 3], ['¾', .75], ['1⅓', 4 / 3], ['1½', 1.5], ['2×', 2]];
  const chips = bpm > 0 ? ratios.map(([l, r]) => { const v = Math.round(bpm * r * 10) / 10;
    return `<button class="r3dp-pop__chip" data-bpm="${v}"><b>${v}</b><span>${l}</span></button>`; }).join('')
    : '<span style="color:#8a8067">No tempo yet — re-analyse.</span>';
  const pop = document.createElement('div'); pop.id = 'r3dp-bpm-pop'; pop.className = 'r3dp-pop';
  pop.innerHTML = `<div class="r3dp-pop__h">Wrong tempo?${bpm ? ' Currently <strong>' + Math.round(bpm) + '</strong>.' : ''} Pick the real value:</div>` +
    `<div class="r3dp-pop__chips">${chips}</div><button class="r3dp-pop__re" data-act="reanalyse">↻ Re-analyse</button>`;
  document.body.appendChild(pop);
  const r = (ev && ev.currentTarget && ev.currentTarget.getBoundingClientRect) ? ev.currentTarget.getBoundingClientRect() : { bottom: 90, left: 90 };
  pop.style.top = Math.min(r.bottom + 6, innerHeight - pop.offsetHeight - 8) + 'px';
  pop.style.left = Math.max(8, Math.min(r.left - 120, innerWidth - pop.offsetWidth - 8)) + 'px';
  pop.addEventListener('click', e => {
    const c = e.target.closest('.r3dp-pop__chip'); if (c) { closePop(); verify(host, { bpm: +c.dataset.bpm }); return; }
    if (e.target.closest('[data-act="reanalyse"]')) { closePop(); reanalyse(host); }
  });
  setTimeout(() => document.addEventListener('pointerdown', popOutside, true), 0);
}
async function reanalyse(host) {
  const id = tid(host);
  const data = await fetch('/api/track/' + id).then(r => r.json()).catch(() => null);
  const pf = data && (data.files || []).find(f => f.is_primary);
  if (!pf) return;
  await fetch('/api/file/' + pf.id + '/analyse', { method: 'POST' }).catch(() => {});
  setTimeout(() => reopen(host), 1200);
}
function flick(host) {
  const rb = document.getElementById('r3dp-an-rb'), mr = document.getElementById('r3dp-an-mr');
  const badge = document.getElementById('r3dp-an-badge'), other = document.getElementById('r3dp-an-other');
  if (!rb || !mr) return;
  const rbVisible = rb.style.display !== 'none';
  rb.style.display = rbVisible ? 'none' : ''; mr.style.display = rbVisible ? '' : 'none';
  if (badge) badge.textContent = rbVisible ? 'Music Room' : 'rekordbox';
  if (other) other.textContent = rbVisible ? 'rekordbox' : 'Music Room';
}

// ── genres / tags ───────────────────────────────────────────────────────────
async function addChip(host, kind, name) {
  name = (name || '').trim(); if (!name) return;
  await fetch('/api/track/' + tid(host) + '/' + (kind === 'genre' ? 'genre' : 'tag'),
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function removeChip(host, kind, id) {
  await fetch('/api/track/' + tid(host) + '/' + (kind === 'genre' ? 'genre' : 'tag') + '/' + id, { method: 'DELETE' }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function suggestGenres(host) {
  const sug = host.querySelector('[data-sug="genre"]'); if (!sug) return;
  sug.innerHTML = '<span style="color:#8a8067;font-size:.72rem">finding…</span>';
  const d = await fetch('/api/track/' + tid(host) + '/genre-suggestions').then(r => r.json()).catch(() => null);
  const list = (d && (d.suggestions || d.genres || d.candidates)) || [];
  const names = (Array.isArray(list) ? list : []).map(x => typeof x === 'string' ? x : (x && (x.name || x.genre))).filter(Boolean);
  sug.innerHTML = names.length
    ? names.slice(0, 12).map(n => `<button class="r3dp__sug__c" data-act="apply-sug" data-name="${esc(n)}">+ ${esc(n)}</button>`).join('')
    : '<span style="color:#8a8067;font-size:.72rem">no suggestions found</span>';
}

// ── cover picker (native; replaces the mr-cover-changed postMessage) ────────
async function coversToggle(host, refresh) {
  const box = host.querySelector('#r3dp-covers'); if (!box) return;
  if (!refresh && box.style.display !== 'none' && box.dataset.loaded) { box.style.display = 'none'; box.dataset.loaded = ''; return; }
  box.style.display = ''; box.innerHTML = '<div class="r3dp__covhint">looking for covers — the file’s own art + online matches…</div>';
  const data = await fetch('/api/artwork/' + tid(host) + '/candidates' + (refresh ? '?refresh=1' : '')).then(r => r.json()).catch(() => null);
  const cands = (data && data.candidates) || [];
  if (!cands.length) { box.innerHTML = '<div class="r3dp__covhint">No covers found — try ↑ upload, or <button class="r3dp__btn" data-act="covers-refresh">search again</button>.</div>'; return; }
  box.innerHTML = '<div class="r3dp__covgrid">' + cands.map(c =>
    `<button class="r3dp__cov ${c.is_current ? 'is-current' : ''}" data-act="pick-cover" data-source="${esc(c.source)}" title="${c.is_current ? 'current' : 'make this the cover'}">` +
      `<img src="${esc(c.url)}" alt="" loading="lazy"><span class="r3dp__cov__lbl">${esc(c.label)}${c.is_current ? ' ✓' : ''}</span></button>`).join('') +
    '</div><button class="r3dp__btn" data-act="covers-refresh" style="margin-top:7px">↻ search online again</button>';
  box.dataset.loaded = '1';
}
function coverChanged(id, art_v, artwork_path) {
  try { window.MRRoomSync && window.MRRoomSync.coverChanged && window.MRRoomSync.coverChanged(id, art_v, artwork_path); } catch (e) {}
}
async function setCover(host, source) {
  const id = tid(host);
  const r = await fetch('/api/artwork/' + id + '/set-primary', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }) }).then(x => x.json()).catch(() => null);
  if (!r || r.error) return;
  coverChanged(id, r.art_v, r.artwork_path); await reopen(host);
}
async function uploadCover(host, file) {
  if (!file) return;
  const fd = new FormData(); fd.append('file', file);
  const r = await fetch('/api/artwork/' + tid(host), { method: 'POST', body: fd }).then(x => x.json()).catch(() => null);
  if (!r || r.error) return;
  coverChanged(tid(host), r.art_v, r.artwork_path); await reopen(host);
}

// ── files / studio / places / removal (STEP 5) ──────────────────────────────
let _allPlaces = null;
async function fillPlaceOptions(host, current) {
  const sel = host.querySelector('select[data-act="add-place"]'); if (!sel) return;
  if (!_allPlaces) { try { _allPlaces = await fetch('/api/places').then(r => r.json()); } catch (e) { _allPlaces = []; } }
  const taken = new Set((current || []).map(p => p.id));
  const avail = (_allPlaces || []).filter(p => !p.is_well && !taken.has(p.id));
  sel.innerHTML = '<option value="">+ add to another place…</option>' +
    avail.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
}
function roomGone(id) { try { window.MRRoomSync && window.MRRoomSync.trackGone && window.MRRoomSync.trackGone(id); } catch (e) {} }

async function choosePath(kind, message) {
  try {
    const r = await fetch('/api/choose-path', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, prompt: message }) }).then(r => r.json());
    return (r && !r.cancelled && r.path) ? r.path : null;
  } catch (e) { return null; }
}
function closeConfirm() { const x = document.getElementById('r3dp-confirm'); if (x) x.remove(); }
function confirmDialog(opts) {
  return new Promise(resolve => {
    closeConfirm();
    const ov = document.createElement('div'); ov.id = 'r3dp-confirm'; ov.className = 'r3dp-confirm';
    ov.innerHTML = `<div class="r3dp-confirm__box"><div class="r3dp-confirm__t">${esc(opts.title)}</div>` +
      `<div class="r3dp-confirm__m">${opts.message}</div><div class="r3dp-confirm__acts">` +
      `<button class="r3dp__btn" data-c="cancel">Cancel</button>` +
      `<button class="r3dp__btn ${opts.danger ? 'r3dp__btn--danger' : ''}" data-c="ok">${esc(opts.okLabel || 'OK')}</button></div></div>`;
    document.body.appendChild(ov);
    const done = v => { ov.remove(); resolve(v); };
    ov.addEventListener('click', e => {
      if (e.target === ov) return done(false);
      const b = e.target.closest('[data-c]'); if (!b) return; done(b.dataset.c === 'ok');
    });
  });
}

async function playFile(host, fileId, btn) {
  if (!window.MRRoomSync || !window.MRRoomSync.cueFile) return;
  const was = btn.textContent;
  const r = await window.MRRoomSync.cueFile(tid(host), fileId);
  btn.textContent = (r && r.ok) ? '✓' : '✕';
  setTimeout(() => { btn.textContent = was; }, 900);
}
async function revealFile(path) {
  if (!path) return;
  await fetch('/api/reveal-path', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) }).catch(() => {});
}
async function openSession(path) {
  if (!path) return;
  await fetch('/api/open-daw', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) }).catch(() => {});
}
async function linkSession(host, fileId) {
  const path = await choosePath('file', 'Choose the session (.als) this version was bounced from'); if (!path) return;
  await fetch('/api/file/' + fileId + '/session', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_path: path }) }).catch(() => {});
  await reopen(host);
}
async function ownWork(host, daw_project_path) {
  const body = { is_own_work: true, daw_type: 'ableton' };
  if (daw_project_path) body.daw_project_path = daw_project_path;
  await fetch('/api/track/' + tid(host) + '/own-work', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body) }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function markOwn(host) {
  const path = await choosePath('file', "Choose this track's Ableton session (.als) — or Cancel to just mark it as your own work");
  await ownWork(host, path);
}
async function linkDaw(host) {
  const path = await choosePath('file', 'Choose the Ableton session (.als) for this track'); if (!path) return;
  await ownWork(host, path);
}
async function setPrimaryFile(host, fileId) {
  await fetch('/api/file/' + fileId + '/set_primary', { method: 'POST' }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function deleteFile(host, fileId, fmt) {
  const ok = await confirmDialog({ title: 'Delete this file?', danger: true, okLabel: 'Move to Trash',
    message: `The <em>${esc(fmt || 'file')}</em> version will be moved to your Trash — recoverable from there.` });
  if (!ok) return;
  const id = tid(host);
  const r = await fetch('/api/file/' + fileId, { method: 'DELETE' }).then(x => x.json()).catch(() => null);
  if (!r || r.error) return;
  const still = await fetch('/api/track/' + id).then(x => x.json()).catch(() => null);
  if (!still || still.error) { roomGone(id); return; }          // that was the last file → track gone
  roomSync(id); await reopen(host);
}
async function removeFromPlace(host, pid) {
  await fetch('/api/place/' + pid + '/track/' + tid(host), { method: 'DELETE' }).catch(() => {});
  await reopen(host);
}
async function addToPlace(host, pid) {
  if (!pid) return;
  await fetch('/api/place/' + pid + '/add_track', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_id: tid(host) }) }).catch(() => {});
  await reopen(host);
}
async function removeTrack(host) {
  const ok = await confirmDialog({ title: 'Remove from Music Room?', danger: true, okLabel: 'Remove',
    message: 'All files move to the <em>Removed from Music Room</em> folder on your drive — not deleted. The importer never picks them up again. Notes &amp; tags are removed.' });
  if (!ok) return;
  const id = tid(host);
  const r = await fetch('/api/track/' + id + '/remove', { method: 'POST' }).then(x => x.json()).catch(() => null);
  if (r && r.ok) roomGone(id);
}
async function deleteTrack(host) {
  const ok = await confirmDialog({ title: 'Delete from library?', danger: true, okLabel: 'Move to Trash',
    message: 'All files move to your Trash. Notes, tags &amp; placements are removed. This cannot be undone from within Music Room.' });
  if (!ok) return;
  const id = tid(host);
  const r = await fetch('/api/track/' + id, { method: 'DELETE' }).then(x => x.json()).catch(() => null);
  if (r && r.ok) roomGone(id);
}

// ── notes: add / delete / stamp / voice (STEP 6) ────────────────────────────
function appendNote(host, n) {
  const list = host.querySelector('#r3dp-notes'); if (!list) return;
  const empty = list.querySelector('.r3dp__empty'); if (empty) empty.remove();
  list.insertAdjacentHTML('beforeend', renderNoteRow(n));
}
async function addNote(host) {
  const ta = host.querySelector('#r3dp-note-text'); const text = (ta.value || '').trim(); if (!text) return;
  const ts = (host.querySelector('#r3dp-note-ts').value || '').trim();
  const type = host.querySelector('#r3dp-note-type').value;
  const n = await fetch('/api/track/' + tid(host) + '/note', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note_text: text, audio_timestamp: ts, note_type: type }) }).then(r => r.json()).catch(() => null);
  if (!n || n.error) return;
  appendNote(host, n); ta.value = ''; host.querySelector('#r3dp-note-ts').value = ''; ta.focus();
}
async function deleteNote(host, id) {
  await fetch('/api/note/' + id, { method: 'DELETE' }).catch(() => {});
  const row = host.querySelector('#r3dp-note-' + id); if (row) row.remove();
  const list = host.querySelector('#r3dp-notes');
  if (list && !list.querySelector('.r3dp__note')) list.innerHTML = '<div class="r3dp__empty">No notes yet.</div>';
}
// the room player is the server-side Seinnteoir — a note's timestamp is only
// meaningful when THIS record is the one playing; otherwise prompt to play it.
async function stampNote(host, btn) {
  const st = await fetch('/api/seinnteoir/state').then(r => r.json()).catch(() => null);
  const cur = st && st.idx >= 0 && st.queue && st.queue[st.idx];
  if (cur && +cur.track_id === tid(host)) {
    const mmss = formatTime(st.position || 0);
    host.querySelector('#r3dp-note-ts').value = mmss;
    btn.textContent = '✓ ' + mmss; host.querySelector('#r3dp-note-text').focus();
  } else {
    btn.textContent = 'play this record';
  }
  // restore to a fixed label (not the live one) + cancel any prior timer, so a
  // rapid second click can't capture the transient label and stick it.
  clearTimeout(btn._restore); btn._restore = setTimeout(() => { btn.textContent = '⊙ stamp'; }, 1500);
}
// voice notes — wire the recorder (mic is tested live, never headless; reuse the
// deeplisten.js MediaRecorder pattern). Upload → server saves + transcribes async.
let _rec = null, _recStream = null;
async function toggleRec(host, btn) {
  if (_rec && _rec.state === 'recording') { _rec.stop(); return; }
  try { _recStream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch (e) { btn.textContent = 'no mic'; setTimeout(() => { btn.textContent = '🎙'; }, 1600); return; }
  const chunks = [];
  _rec = new MediaRecorder(_recStream);
  _rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
  _rec.onstop = async () => {
    try { _recStream.getTracks().forEach(t => t.stop()); } catch (e) {}
    const rb = host.querySelector('[data-act="rec"]') || btn;   // panel may have re-rendered mid-record
    rb.classList.remove('is-rec'); rb.textContent = '🎙';
    const blob = new Blob(chunks, { type: (chunks[0] && chunks[0].type) || 'audio/mp4' });
    const fd = new FormData(); fd.append('audio', blob, 'voice.mp4');
    const ts = (host.querySelector('#r3dp-note-ts').value || '').trim(); if (ts) fd.append('audio_timestamp', ts);
    const txt = (host.querySelector('#r3dp-note-text').value || '').trim(); if (txt) fd.append('note_text', txt);
    const n = await fetch('/api/track/' + tid(host) + '/voice_note', { method: 'POST', body: fd }).then(r => r.json()).catch(() => null);
    if (n && !n.error) { appendNote(host, n); host.querySelector('#r3dp-note-text').value = ''; host.querySelector('#r3dp-note-ts').value = ''; }
    _rec = null; _recStream = null;
  };
  _rec.start(); btn.classList.add('is-rec'); btn.textContent = '⏹ stop';
}
function toggleVoicePlay(host, id, btn) {
  const a = host.querySelector('#r3dp-vn-' + id); if (!a) return;
  if (a.paused) { a.play().catch(() => {}); btn.textContent = '⏸'; a.onended = () => { btn.textContent = '▶'; }; }
  else { a.pause(); btn.textContent = '▶'; }
}

// ── one delegated handler for the whole panel ───────────────────────────────
function wire(host) {
  if (host.__r3dpWired) return; host.__r3dpWired = true;
  host.addEventListener('click', e => {
    const link = e.target.closest('a[data-stop]'); if (link) return;       // let real links open
    const edit = e.target.closest('.r3dp__edit'); if (edit) { enterEdit(host, edit); return; }
    const act = e.target.closest('[data-act]'); if (!act) return;
    const a = act.dataset.act;
    if (a === 'write-tags') return writeTags(host, act);
    if (a === 'bpm-verify') return verify(host, { bpm: +act.dataset.bpm });
    if (a === 'key-verify') return verify(host, { key_note: act.dataset.note, key_scale: act.dataset.scale || null });
    if (a === 'bpm-edit') { const v = prompt('Correct BPM:'); const n = parseFloat(v); if (!isNaN(n)) verify(host, { bpm: n }); return; }
    if (a === 'key-edit') { const note = prompt('Key note (e.g. C, F#, Bb):'); if (!note) return; const scale = prompt('Major or minor?', 'major'); if (scale) verify(host, { key_note: note, key_scale: scale }); return; }
    if (a === 'cover-verify') return coverVerify(host);
    if (a === 'cover-remove') return coverRemove(host);
    if (a === 'dsp-yes') return dspConfirm(host, true);
    if (a === 'dsp-no') return dspConfirm(host, false);
    if (a === 'find-samples') return findSamples(host);
    if (a === 'p-toggle') return playerToggle();
    if (a === 'p-stamp') return playerStamp();
    if (a === 'p-handoff') return playerHandoff(host);
    if (a === 'p-cue') return playerCue(host, act);
    if (a === 'bpm-fix') return openBpmFix(host, (host.querySelector('#r3dp-an-mr .r3dp__big') || {}).textContent, e);
    if (a === 'flick') return flick(host);
    if (a === 'del-chip') return removeChip(host, act.dataset.kind, act.dataset.id);
    if (a === 'suggest') return suggestGenres(host);
    if (a === 'apply-sug') return addChip(host, 'genre', act.dataset.name);
    if (a === 'lightbox') return openCoverLightbox(host);
    if (a === 'covers') return coversToggle(host);
    if (a === 'covers-refresh') return coversToggle(host, true);
    if (a === 'pick-cover') return setCover(host, act.dataset.source);
    if (a === 'play-file') return playFile(host, act.dataset.fid, act);
    if (a === 'reveal') return revealFile(act.dataset.path);
    if (a === 'open-session') return openSession(act.dataset.path);
    if (a === 'link-session') return linkSession(host, act.dataset.fid);
    if (a === 'set-primary') return setPrimaryFile(host, act.dataset.fid);
    if (a === 'del-file') return deleteFile(host, act.dataset.fid, act.dataset.fmt);
    if (a === 'mark-own') return markOwn(host);
    if (a === 'link-daw') return linkDaw(host);
    if (a === 'rm-place') return removeFromPlace(host, act.dataset.pid);
    if (a === 'remove-track') return removeTrack(host);
    if (a === 'delete-track') return deleteTrack(host);
    if (a === 'add-note') return addNote(host);
    if (a === 'del-note') return deleteNote(host, act.dataset.id);
    if (a === 'stamp') return stampNote(host, act);
    if (a === 'rec') return toggleRec(host, act);
    if (a === 'vn-play') return toggleVoicePlay(host, act.dataset.id, act);
  });
  host.addEventListener('change', e => {
    const sel = e.target.closest('select[data-act="add-place"]');
    if (sel && sel.value) { const pid = sel.value; sel.value = ''; addToPlace(host, pid); }
  });
  host.addEventListener('keydown', e => {
    const add = e.target.closest('.r3dp__addchip');
    if (add && e.key === 'Enter') { e.preventDefault(); const v = add.value; add.value = ''; addChip(host, add.dataset.add, v); }
    const noteTa = e.target.closest('#r3dp-note-text');
    if (noteTa && e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); addNote(host); }
  });
  host.addEventListener('change', e => {
    const up = e.target.closest('[data-act="upload"]');
    if (up && up.files && up.files[0]) uploadCover(host, up.files[0]);
  });
  // player scrub + volume (range inputs → 'input' event)
  host.addEventListener('input', e => {
    if (e.target.hasAttribute('data-pseek') && _audio && _audio.duration) _audio.currentTime = (e.target.value / 100) * _audio.duration;
    if (e.target.hasAttribute('data-pvol') && _audio) _audio.volume = parseFloat(e.target.value);
  });
  // Own the wheel: the room captures wheel to zoom the camera, and WKWebView
  // (the desktop app) doesn't reliably scroll a nested div — so scroll the
  // panel ourselves and stop the event reaching the scene.
  host.addEventListener('wheel', e => {
    host.scrollTop += e.deltaY;
    e.stopPropagation(); e.preventDefault();
  }, { passive: false });
}
async function writeTags(host, btn) {
  const orig = btn.textContent; btn.textContent = 'writing…';
  const r = await fetch('/api/track/' + tid(host) + '/write_tags', { method: 'POST' }).then(x => x.json()).catch(() => ({ error: 'failed' }));
  btn.textContent = r && r.ok ? '✓ written' : '✗ ' + ((r && r.error) || 'failed');
  setTimeout(() => { btn.textContent = orig; }, 2200);
}

// the cover → the native draw/sticker/note lightbox (replaces the iframe's
// mr-open-lightbox postMessage round-trip). Same editor, same endpoints.
function openCoverLightbox(host) {
  if (!window.MRLightbox) return;
  const t = host.__track || { id: tid(host) };
  window.MRLightbox.open(t.id, {
    placeId: window.MR_WELL_ID || null,
    track: t,
    onClose: () => { roomSync(t.id); reopen(host); },   // reflect any cover-colour change
  });
}

async function coverVerify(host) {
  await fetch('/api/artwork/' + tid(host) + '/verify', { method: 'POST' }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function coverRemove(host) {
  if (!confirm('Remove this cover?')) return;
  await fetch('/api/artwork/' + tid(host), { method: 'DELETE' }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function dspConfirm(host, accept) {
  await fetch('/api/track/' + tid(host) + '/dsp-confirm', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accept }) }).catch(() => {});
  roomSync(tid(host)); await reopen(host);
}
async function findSamples(host) {
  const box = host.querySelector('#r3dp-samples'); if (!box) return;
  box.style.display = ''; box.innerHTML = '<span class="r3dp__empty">Asking MusicBrainz…</span>';
  let d;
  try { const r = await fetch('/api/track/' + tid(host) + '/samples'); d = await r.json(); if (!r.ok) throw new Error(d.error || 'Sample lookup failed'); }
  catch (e) { box.innerHTML = '<span class="r3dp__empty">' + esc(e.message || 'Could not look up samples.') + '</span>'; return; }
  const grp = (arr, label) => (arr && arr.length)
    ? '<div class="r3dp__h" style="margin:6px 0 3px">' + label + '</div>' +
      arr.map(it => '<div class="r3dp__empty" style="color:#cfc3a4">' +
        esc((it.artist ? it.artist + ' — ' : '') + (it.title || it.name || '?')) + '</div>').join('')
    : '';
  const html = grp(d.samples, 'Samples') + grp(d.sampled_by || d.sampledBy, 'Sampled by');
  box.innerHTML = html || '<span class="r3dp__empty">No sample lineage found.</span>';
}

// ── in-panel player (browser <audio>, module-scoped so it survives re-renders) ──
let _audio = null, _audioTid = null, _audioFid = null;
function _ensureAudio() {
  if (_audio) return _audio;
  _audio = document.createElement('audio');
  _audio.preload = 'metadata'; _audio.id = 'r3dp-audio';
  document.body.appendChild(_audio);
  _audio.addEventListener('timeupdate', _playerTick);
  _audio.addEventListener('play',  _playerState);
  _audio.addEventListener('pause', _playerState);
  _audio.addEventListener('ended', _playerState);
  return _audio;
}
function _playerTick() {
  const sc = document.getElementById('r3dp-pscrub'), tm = document.getElementById('r3dp-ptime');
  if (sc && document.activeElement !== sc) sc.value = _audio.duration ? (_audio.currentTime / _audio.duration) * 100 : 0;
  if (tm) tm.textContent = formatTime(_audio.currentTime) + ' / ' + formatTime(_audio.duration);
}
function _playerState() {
  const b = document.getElementById('r3dp-ptoggle');
  if (b) { b.textContent = (_audio && !_audio.paused) ? '⏸' : '▶'; b.classList.toggle('playing', !!(_audio && !_audio.paused)); }
}
// load the panel player onto this track's primary file (only when the track
// actually changed — re-renders for an edit must NOT restart playback).
function syncPlayer(host) {
  const t = host.__track || {}, fid = host.__pfid;
  if (!fid) return;
  _ensureAudio();
  if (_audioTid !== t.id) {
    _audio.src = '/audio/' + fid; _audio.load();
    _audioTid = t.id; _audioFid = fid;
  }
  _playerState(); _playerTick();
}
function stopAudio() { try { if (_audio) _audio.pause(); } catch (_) {} }
function playerToggle() {
  _ensureAudio();
  if (!_audio.src) return;
  if (_audio.paused) {
    // one-player-at-a-time: pause the Seinnteoir cassette first, then play here
    fetch('/api/seinnteoir/state').then(r => r.json()).then(st => {
      if (st && st.playing) return fetch('/api/seinnteoir/pause', { method: 'POST' });
    }).catch(() => {}).finally(() => _audio.play().catch(() => {}));
  } else _audio.pause();
}
function playerStamp() {
  const ts = formatTime(_audio ? _audio.currentTime : 0);
  const inp = document.getElementById('r3dp-note-ts'); if (inp) inp.value = ts;
  const b = document.getElementById('r3dp-pstamp');
  if (b) { const o = b.textContent; b.textContent = '✓'; setTimeout(() => { b.textContent = o; }, 1200); }
}
async function playerHandoff(host) {
  if (!_audio || !_audio.src || !_audioFid) return;
  const pos = _audio.currentTime || 0, t = host.__track || {};
  const item = { track_id: t.id || tid(host), file_id: _audioFid, title: t.title || '', artist: t.artist_name || '' };
  const J = { 'Content-Type': 'application/json' };
  try {
    await fetch('/api/seinnteoir/add', { method: 'POST', headers: J, body: JSON.stringify({ items: [item], autostart: false }) });
    const st = await fetch('/api/seinnteoir/state').then(r => r.json()).catch(() => ({}));
    let idx = -1; (st.queue || []).forEach((q, i) => { if (q.file_id == _audioFid) idx = i; });
    if (idx < 0) idx = Math.max(0, (st.queue || []).length - 1);
    await fetch('/api/seinnteoir/play_at', { method: 'POST', headers: J, body: JSON.stringify({ idx }) });
    await fetch('/api/seinnteoir/seek', { method: 'POST', headers: J, body: JSON.stringify({ sec: pos }) });
    _audio.pause();
    try { if (window.Seinnteoir && window.Seinnteoir.open) window.Seinnteoir.open(); } catch (_) {}
  } catch (_) {}
}

// Cue the OPEN track into the persistent Player WITHOUT playing it here and
// WITHOUT disturbing current playback — parity with place.html cueToPlayer.
// Cues the primary file (host.__pfid) with autostart:false. NB: room3d's
// MRRoomSync.cueFile posts autostart:true (it would START playback), so we POST
// directly with autostart:false instead. (Flag-gated OFF; no live effect.)
async function playerCue(host, btn) {
  const t = host.__track || {}, fid = host.__pfid;
  if (!fid) return;
  const item = { track_id: t.id || tid(host), file_id: fid,
                 title: t.title || '', artist: t.artist_name || '' };
  if (window.MR_WELL_ID) item.place_id = window.MR_WELL_ID;   // place provenance if the room exposes it
  const was = btn && btn.textContent;
  try {
    await fetch('/api/seinnteoir/add', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: [item], autostart: false }) });
    // the host room's cassette reopens on its own poll (the queue grew)
    if (btn) { btn.textContent = '✓ cued'; setTimeout(() => { btn.textContent = was; }, 1100); }
  } catch (_) {}
}

async function open(trackId, host) {
  injectStyles(); host.classList.add('r3dp');
  host.innerHTML = '<div class="r3dp__empty" style="padding:60px 22px">opening the record…</div>';
  let data = null;
  try { data = await fetch('/api/track/' + trackId).then(r => r.json()); } catch (e) {}
  if (!data || data.error) { host.innerHTML = '<div class="r3dp__empty" style="padding:60px 22px">Couldn’t load this record.</div>'; return; }
  render(host, data); wire(host); syncPlayer(host);
}

window.MRTrackPanel = { open, stopAudio };
})();
