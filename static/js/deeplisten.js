// ── Deep Listening — the deep-listening note-taking panel ─────────────────
// Extracted verbatim from the 3D room so it opens on ANY page (the cassette's
// Deep Listening button), functioning exactly the same. Self-contained: injects
// its own CSS + markup, drives the shared server player, exposes window.openEisteacht.
(function(){
  'use strict';
  if (window.__deeplistenInit) return; window.__deeplistenInit = true;
  if (!document.getElementById('deeplisten-css')){
    var _st = document.createElement('style'); _st.id = 'deeplisten-css';
    _st.textContent = `#r3d-eist{ --spring:cubic-bezier(.34,1.45,.5,1); }
  /* ── Éisteacht — the deep-listening lens, NATIVE in the room (no iframe).
     Worn in the EXPLORE register (Inter type, the content-surface palette) with
     the track panel's PRESSABLE controls: things fill, breathe, lift and squash.
     Timestamps come off the server player's live position — moving between the
     lenses never pauses the music. */
  /* Éisteacht fills the whole screen (David). The cassette hides while it's open
     — Éisteacht IS the player here (its own transport + cue). */
  #r3d-eist{ position:fixed; inset:0; z-index:16;
    --eg:#f5e6b0; --ei:#efe6cf; --em:#9a8c6c; --eline:rgba(255,255,255,.08); --efill:rgba(255,255,255,.06);
    display:flex; justify-content:center;
    background:linear-gradient(180deg, rgba(18,16,12,.985), rgba(11,9,6,.99));
    backdrop-filter:blur(22px);
    opacity:0; pointer-events:none; transform:scale(1.012); transition:opacity .3s ease, transform .34s var(--spring);
    font-family:var(--font-main,'Inter',system-ui,sans-serif); color:var(--ei); }
  #r3d-eist.open{ opacity:1; pointer-events:auto; transform:none; }
  body.r3d-eist-open #seinnteoir-bar,
  body.r3d-eist-open #seinnteoir-tab,
  body.r3d-eist-open #snt-qpop{ display:none !important; }   /* the cassette fuses into Éisteacht */
  /* the readable centred column the listening content lives in */
  .eis-col{ display:flex; flex-direction:column; width:100%; max-width:860px; height:100%; }
  .eis-head__acts{ display:flex; align-items:center; gap:8px; }
  .eis-icon{ appearance:none; cursor:pointer; font-family:inherit; font-size:.8rem; color:var(--em);
    background:var(--efill); border:1px solid var(--eline); border-radius:100px; padding:6px 12px;
    transition:all .18s var(--spring); white-space:nowrap; }
  .eis-icon:hover{ color:var(--ei); border-color:rgba(245,230,176,.35); transform:translateY(-1px); }
  .eis-icon.active{ background:var(--eg); color:#1d160d; border-color:var(--eg); }
  .eis-tbtn{ appearance:none; cursor:pointer; font-family:inherit; font-size:.9rem; color:var(--ei);
    background:var(--efill); border:1px solid var(--eline); border-radius:50%; width:38px; height:38px;
    flex-shrink:0; transition:all .18s var(--spring); }
  .eis-tbtn:hover{ color:var(--eg); border-color:rgba(245,230,176,.4); transform:translateY(-1px); }
  .eis-tbtn:active{ transform:scale(.9); }
  .eis-head{ padding:22px 22px 16px; border-bottom:1px solid var(--eline); flex-shrink:0; }
  .eis-head__top{ display:flex; align-items:center; justify-content:space-between; }
  .eis-title{ font-family:var(--font-serif,'EB Garamond',serif); font-style:italic; font-weight:400;
    color:var(--eg); font-size:1.5rem; letter-spacing:.2px; }
  .eis-close{ appearance:none; border:1px solid var(--eline); background:var(--efill); cursor:pointer; color:var(--em);
    width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    font-size:.88rem; transition:all .22s var(--spring); }
  .eis-close:hover{ color:var(--ei); border-color:rgba(245,230,176,.35); transform:translateY(-1px); }
  .eis-close:active{ transform:scale(.9); }
  .eis-now{ display:flex; gap:13px; align-items:center; margin-top:16px; }
  .eis-now__art{ width:50px; height:50px; border-radius:10px; object-fit:cover; background:#1d1812; flex-shrink:0;
    display:flex; align-items:center; justify-content:center; color:rgba(245,230,176,.4); font-style:italic;
    box-shadow:0 6px 20px rgba(0,0,0,.4); }
  .eis-now__meta{ min-width:0; flex:1; }
  .eis-now__title{ font-size:1.05rem; font-weight:700; letter-spacing:-.01em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .eis-now__artist{ font-size:.82rem; color:var(--em); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
  .eis-transport{ display:flex; align-items:center; gap:12px; margin-top:16px; }
  /* the play FILLS while sound is moving + breathes — straight off the track panel */
  .eis-play{ appearance:none; border:1px solid var(--eline); background:var(--efill); color:var(--ei);
    width:42px; height:42px; border-radius:50%; cursor:pointer; flex-shrink:0; display:flex; align-items:center;
    justify-content:center; font-size:1rem; transition:all .22s var(--spring); }
  .eis-play:hover{ color:var(--eg); border-color:var(--eg); transform:scale(1.12); box-shadow:0 3px 14px rgba(245,230,176,.22); }
  .eis-play:active{ transform:scale(.9); }
  .eis-play.playing{ background:var(--eg); border-color:var(--eg); color:#1d160d; animation:eis-breathe 2.6s ease-in-out infinite; }
  /* the glyph must never swallow the click — WebKit can hit-test the inline text node
     instead of the button, so a press dead-centre on the icon did nothing (only the ring
     worked). pointer-events:none makes every press land on the button itself. */
  .eis-play__ico, .eis-tbtn__ico{ pointer-events:none; line-height:1; }
  @keyframes eis-breathe{ 0%,100%{ box-shadow:0 0 5px rgba(245,230,176,.35);} 50%{ box-shadow:0 0 18px rgba(245,230,176,.65);} }
  .eis-scrub{ -webkit-appearance:none; appearance:none; flex:1; height:6px; border-radius:3px;
    background:rgba(255,255,255,.12); cursor:pointer; outline:none; transition:height .2s var(--spring); }
  .eis-scrub:hover{ height:9px; }
  .eis-scrub::-webkit-slider-thumb{ -webkit-appearance:none; width:15px; height:15px; border-radius:50%;
    background:var(--eg); cursor:pointer; transition:transform .2s var(--spring), box-shadow .2s; }
  .eis-scrub:hover::-webkit-slider-thumb{ transform:scale(1.35); box-shadow:0 0 0 5px rgba(245,230,176,.16); }
  .eis-time{ font-family:var(--font-mono,monospace); font-size:.7rem; color:var(--em); white-space:nowrap;
    font-variant-numeric:tabular-nums; letter-spacing:.3px; }
  /* volume — drives the shared server player, like the cassette + Just Listen */
  .eis-vol{ display:inline-flex; align-items:center; gap:7px; flex:0 0 auto; }
  .eis-vol__ic{ font-size:.8rem; color:var(--em); }
  .eis-vol__slider{ -webkit-appearance:none; appearance:none; width:74px; height:5px; border-radius:3px;
    background:rgba(255,255,255,.12); cursor:pointer; outline:none; }
  .eis-vol__slider::-webkit-slider-thumb{ -webkit-appearance:none; width:12px; height:12px; border-radius:50%;
    background:var(--eg); cursor:pointer; }
  .eis-notes{ flex:1; overflow-y:auto; padding:10px 14px; }
  .eis-note{ display:flex; gap:11px; align-items:flex-start; padding:9px; border-radius:12px; transition:background .18s; }
  .eis-note:hover{ background:rgba(255,255,255,.04); }
  .eis-note__ts{ font-family:var(--font-mono,monospace); font-size:.7rem; color:var(--eg); cursor:pointer; flex-shrink:0;
    padding-top:3px; min-width:36px; font-variant-numeric:tabular-nums; transition:color .15s; }
  .eis-note__ts:hover{ color:#fff0c4; text-decoration:underline; }
  .eis-note__body{ flex:1; min-width:0; }
  .eis-note__cat{ display:inline-block; font-family:var(--font-mono,monospace); font-size:.58rem; letter-spacing:1.2px;
    text-transform:uppercase; color:var(--em); cursor:pointer; margin-bottom:4px; transition:color .15s; }
  .eis-note__cat:hover{ color:var(--eg); }
  .eis-note__cat.voice::before{ content:'🎙 '; }
  .eis-note__text{ font-size:.9rem; color:var(--ei); line-height:1.45; word-break:break-word; }
  .eis-note__del{ appearance:none; border:none; background:none; cursor:pointer; color:var(--em); opacity:0;
    font-size:.85rem; flex-shrink:0; transition:opacity .18s,color .18s; }
  .eis-note:hover .eis-note__del{ opacity:.55; }
  .eis-note__del:hover{ color:#d99; opacity:1; }
  .eis-empty{ padding:30px 20px; text-align:center; color:var(--em); font-size:.86rem; line-height:1.6; }
  .eis-bottom{ border-top:1px solid var(--eline); padding:12px 16px 16px; flex-shrink:0;
    background:linear-gradient(180deg, transparent, rgba(0,0,0,.2)); }
  .eis-input-row{ display:none; align-items:center; gap:9px; margin-bottom:11px; }
  .eis-input-row.show{ display:flex; }
  .eis-active-cat{ font-family:var(--font-mono,monospace); font-size:.6rem; text-transform:uppercase; letter-spacing:1.2px;
    color:var(--eg); white-space:nowrap; }
  .eis-input{ flex:1; min-width:0; background:rgba(0,0,0,.28); border:1px solid var(--eline); border-radius:11px;
    color:var(--ei); font-family:inherit; font-size:.9rem; padding:9px 13px; outline:none; transition:border-color .2s; }
  .eis-input:focus{ border-color:rgba(245,230,176,.5); }
  .eis-input::placeholder{ color:var(--em); }
  /* the action buttons: inviting + pressable like the track panel's controls */
  .eis-save,.eis-dismiss{ appearance:none; cursor:pointer; font-family:inherit; font-weight:600; flex-shrink:0;
    border-radius:12px; padding:9px 13px; font-size:.82rem; transition:all .22s var(--spring); }
  .eis-save{ background:var(--eg); color:#1d160d; border:1px solid var(--eg); }
  .eis-save:hover{ background:#fff0c4; transform:translateY(-2px); }
  .eis-save:active{ transform:scale(.94); }
  .eis-dismiss{ background:var(--efill); color:var(--em); border:1px solid var(--eline); }
  .eis-dismiss:hover{ color:#d99; border-color:rgba(217,153,153,.5); transform:translateY(-1px); }
  .eis-dismiss:active{ transform:scale(.94); }
  .eis-chips{ display:flex; flex-wrap:wrap; gap:6px; }
  .eis-chip{ appearance:none; cursor:pointer; font-family:inherit; font-size:.78rem; font-weight:500; color:var(--em);
    background:var(--efill); border:1px solid var(--eline); border-radius:100px; padding:6px 12px;
    display:flex; align-items:center; gap:6px; transition:all .22s var(--spring); }
  .eis-chip:hover{ color:var(--ei); border-color:rgba(245,230,176,.35); transform:translateY(-1px); }
  .eis-chip:active{ transform:scale(.95); }
  .eis-chip.active{ background:var(--eg); color:#1d160d; border-color:var(--eg); }
  .eis-chip__key{ font-family:var(--font-mono,monospace); font-size:.6rem; opacity:.6; }
  .eis-chip.active .eis-chip__key{ opacity:.85; }
  /* voice = a dashed → solid invite, like the cue button */
  .eis-chip--voice{ color:var(--eg); border-style:dashed; }
  .eis-chip--voice:hover{ border-style:solid; transform:translateY(-1px) scale(1.04); }
  .eis-chip--voice.recording{ background:#9c3b2c; color:#fff; border-color:#9c3b2c; border-style:solid;
    animation:eis-pulse 1.2s ease-in-out infinite; }
  @keyframes eis-pulse{ 0%,100%{ box-shadow:0 0 0 0 rgba(156,59,44,.5);} 50%{ box-shadow:0 0 0 8px rgba(156,59,44,0);} }

  /* the cue panel (right side of the full-screen Éisteacht) */
  .eis-queue{ position:absolute; right:0; top:0; height:100%; width:min(360px,86vw); z-index:3;
    display:flex; flex-direction:column; background:rgba(14,12,8,.97); border-left:1px solid var(--eline);
    box-shadow:-24px 0 60px rgba(0,0,0,.5); transform:translateX(101%); transition:transform .3s var(--spring);
    opacity:0; pointer-events:none; }
  .eis-queue.show{ transform:none; opacity:1; pointer-events:auto; }
  .eis-queue__head{ padding:18px 18px 12px; border-bottom:1px solid var(--eline); display:flex;
    align-items:center; justify-content:space-between; font-family:var(--font-mono,monospace); font-size:.66rem;
    letter-spacing:1.2px; text-transform:uppercase; color:var(--em); }
  .eis-queue__list{ flex:1; overflow-y:auto; padding:8px; }
  .eis-qrow{ display:flex; gap:9px; align-items:center; padding:9px 10px; border-radius:10px; cursor:pointer;
    transition:background .15s; }
  .eis-qrow:hover{ background:rgba(255,255,255,.05); }
  .eis-qrow.active{ background:rgba(245,230,176,.1); }
  .eis-qrow__grip{ color:var(--em); font-size:.8rem; cursor:grab; flex-shrink:0; opacity:.5; line-height:1; user-select:none; }
  .eis-qrow__grip:active{ cursor:grabbing; } .eis-qrow:hover .eis-qrow__grip{ opacity:.85; }
  .eis-qghost{ opacity:.4; }
  .eis-qrow__n{ font-family:var(--font-mono,monospace); font-size:.66rem; color:var(--em); width:18px; flex-shrink:0; }
  .eis-qrow.active .eis-qrow__n{ color:var(--eg); }
  .eis-qrow__main{ flex:1; min-width:0; }
  .eis-qrow__t{ font-size:.84rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .eis-qrow__a{ font-size:.7rem; color:var(--em); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .eis-qrow__x{ appearance:none; border:none; background:none; cursor:pointer; color:var(--em); opacity:0;
    font-size:.8rem; flex-shrink:0; transition:opacity .15s,color .15s; }
  .eis-qrow:hover .eis-qrow__x{ opacity:.6; } .eis-qrow__x:hover{ color:#d99; opacity:1; }

  /* the 1–0 tag shortcuts + presets editor (a centred card over the panel) */
  .eis-presets{ position:absolute; inset:0; z-index:4; display:none; align-items:center; justify-content:center;
    background:rgba(8,7,4,.6); }
  .eis-presets.show{ display:flex; }
  .eis-presets__card{ width:min(540px,92vw); max-height:86vh; overflow-y:auto; background:rgba(20,18,13,.99);
    border:1px solid var(--eline); border-radius:18px; padding:22px; box-shadow:0 30px 80px rgba(0,0,0,.6); }
  .eis-presets__title{ font-family:var(--font-serif,'EB Garamond',serif); font-style:italic; font-size:1.4rem;
    color:var(--eg); margin-bottom:4px; }
  .eis-presets__hint{ font-size:.78rem; color:var(--em); margin-bottom:16px; line-height:1.5; }
  .eis-preset-bar{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:16px; }
  .eis-preset-chip{ display:inline-flex; align-items:center; background:var(--efill); border:1px solid var(--eline);
    border-radius:100px; overflow:hidden; transition:all .16s var(--spring); }
  .eis-preset-chip:hover{ border-color:rgba(245,230,176,.35); }
  .eis-preset-chip.active{ background:var(--eg); border-color:var(--eg); }
  .eis-preset-use{ appearance:none; cursor:pointer; border:none; background:none; font-family:inherit; font-size:.78rem;
    color:var(--em); padding:6px 6px 6px 13px; }
  .eis-preset-chip:hover .eis-preset-use{ color:var(--ei); }
  .eis-preset-chip.active .eis-preset-use{ color:#1d160d; }
  .eis-preset-x{ appearance:none; cursor:pointer; border:none; background:none; font-size:.66rem; color:var(--em);
    padding:6px 11px 6px 5px; opacity:.5; transition:opacity .14s,color .14s; }
  .eis-preset-x:hover{ opacity:1; color:#d99; }
  .eis-preset-chip.active .eis-preset-x{ color:#1d160d; opacity:.6; }
  .eis-preset-chip.active .eis-preset-x:hover{ color:#7a1d12; opacity:1; }
  .eis-map-row{ display:flex; align-items:center; gap:11px; margin-bottom:8px; }
  .eis-map-key{ font-family:var(--font-mono,monospace); font-size:.86rem; color:var(--eg); width:20px; text-align:center; flex-shrink:0; }
  .eis-map-in{ flex:1; background:rgba(0,0,0,.28); border:1px solid var(--eline); border-radius:10px;
    color:var(--ei); font-family:inherit; font-size:.9rem; padding:8px 12px; outline:none; }
  .eis-map-in:focus{ border-color:rgba(245,230,176,.5); }
  .eis-presets__foot{ display:flex; gap:9px; align-items:center; margin-top:18px; flex-wrap:wrap; }
  .eis-presets__foot input{ flex:1; min-width:120px; background:rgba(0,0,0,.28); border:1px solid var(--eline);
    border-radius:10px; color:var(--ei); font-family:inherit; font-size:.84rem; padding:8px 12px; outline:none; }
  .eis-btn{ appearance:none; cursor:pointer; font-family:inherit; font-weight:600; font-size:.84rem; flex-shrink:0;
    border-radius:10px; padding:9px 16px; transition:all .18s var(--spring); }
  .eis-btn--save{ background:var(--eg); color:#1d160d; border:1px solid var(--eg); }
  .eis-btn--save:hover{ background:#fff0c4; transform:translateY(-1px); }
  .eis-btn--ghost{ background:var(--efill); color:var(--em); border:1px solid var(--eline); }
  .eis-btn--ghost:hover{ color:var(--ei); border-color:rgba(245,230,176,.35); }`;
    document.head.appendChild(_st);
  }
  if (!document.getElementById('r3d-eist')){
    var _w = document.createElement('div'); _w.innerHTML = `  <!-- Éisteacht — deep listening, NATIVE in the room. Notes are timed off the
       Seinnteoir's live position; the music plays on, the scene stays alive. -->
  <div id="r3d-eist" aria-hidden="true">
   <div class="eis-col">
    <div class="eis-head">
      <div class="eis-head__top">
        <span class="eis-title">Deep Listening</span>
        <div class="eis-head__acts">
          <button class="eis-icon" id="eis-queue-btn" title="The cue — change what's lined up">☰ cue</button>
          <button class="eis-icon" id="eis-presets-btn" title="Your 1–0 tag shortcuts (presets)">⊞ tags</button>
          <button class="eis-close" id="eis-close" title="Back to the player (the music keeps playing)">✕</button>
        </div>
      </div>
      <div class="eis-now" id="eis-now">
        <div class="eis-now__art" id="eis-art">♪</div>
        <div class="eis-now__meta">
          <div class="eis-now__title" id="eis-now-title">—</div>
          <div class="eis-now__artist" id="eis-now-artist"></div>
        </div>
      </div>
      <div class="eis-transport" id="eis-transport">
        <button class="eis-tbtn" id="eis-prev" title="Previous track"><span class="eis-tbtn__ico">⏮</span></button>
        <button class="eis-play" id="eis-play" title="Play / pause"><span class="eis-play__ico">▶</span></button>
        <button class="eis-tbtn" id="eis-next" title="Next track"><span class="eis-tbtn__ico">⏭</span></button>
        <input type="range" class="eis-scrub" id="eis-scrub" min="0" max="1000" value="0">
        <span class="eis-time" id="eis-time">0:00 / 0:00</span>
        <span class="eis-vol"><span class="eis-vol__ic" id="eis-vol-ic">🔊</span><input type="range" class="eis-vol__slider" id="eis-vol" min="0" max="1" step="any" value="0.8" title="Volume"></span>
      </div>
    </div>
    <div class="eis-notes" id="eis-notes"></div>
    <div class="eis-bottom">
      <div class="eis-input-row" id="eis-input-row">
        <span class="eis-active-cat" id="eis-active-cat"></span>
        <input class="eis-input" id="eis-input" placeholder="type a note…" autocomplete="off"
               autocorrect="off" spellcheck="false">
        <button class="eis-save" id="eis-save" title="Save (↵)">↵</button>
        <button class="eis-dismiss" id="eis-dismiss" title="Dismiss (Esc)">✕</button>
      </div>
      <div class="eis-chips" id="eis-chips"></div>
    </div>
   </div>
   <!-- the cue, slid in from the right — change what's lined up without leaving -->
   <div class="eis-queue" id="eis-queue" aria-hidden="true"></div>
   <!-- your 1–0 tag shortcuts + named presets -->
   <div class="eis-presets" id="eis-presets" aria-hidden="true"></div>
  </div>`;
    while (_w.firstChild) document.body.appendChild(_w.firstChild);
  }
// ============================================================================
// ÉISTEACHT — the deep-listening lens, native in the room (no iframe).
// A session attaches to whatever the Seinnteoir is playing; note timestamps
// come off the server player's LIVE position (interpolated between polls), so
// the three lenses share one clock and moving between them never pauses audio.
// ============================================================================
(function(){
  const $ = id => document.getElementById(id);
  // active = a listening session is engaged (poll runs, follows the cue);
  // panelOpen = the full-screen panel is showing. Minimized = active && !panelOpen.
  let active=false, panelOpen=false, sid=null, eTrackId=null, eNotes=[], activeCat='', cats={}, presets=[],
      recorder=null, recording=false, qLast='', qState=null, eisSortable=null, eisQDragging=false,
      pos=0, dur=0, playing=false, lastPollAt=0, pollTimer=null, curTrack=null, scrubbing=false;

  const efmt = s => { if(!isFinite(s)||s==null) return '0:00'; const m=Math.floor(s/60),x=Math.floor(s%60); return m+':'+String(x).padStart(2,'0'); };
  const eesc = s => String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  async function loadCats(){
    try { const d = await fetch('/api/listen/categories').then(r=>r.json());
      cats = d.shortcuts || {}; presets = Array.isArray(d.presets) ? d.presets : []; }
    catch(_){ cats = {}; }
    if (!Object.keys(cats).length)            // first run → a sensible default mapping
      cats = {"1":"Rhythm","2":"Melody","3":"Energy","4":"Texture","5":"Set placement","6":"Reference","7":"Production","8":"Vocals"};
  }
  function renderChips(){
    const el=$('eis-chips'); if(!el) return;
    let html='';
    for (const k of ['1','2','3','4','5','6','7','8','9','0']){   // 1–9 then 0, only the mapped ones
      const name=cats[k]; if (name==null) continue;
      html += `<button class="eis-chip ${activeCat===name?'active':''}" data-cat="${eesc(name)}"><span class="eis-chip__key">${eesc(k)}</span>${eesc(name)}</button>`;
    }
    html += `<button class="eis-chip eis-chip--voice ${recording?'recording':''}" id="eis-voice"><span class="eis-chip__key">V</span>${recording?'recording…':'voice'}</button>`;
    el.innerHTML = html;
    el.querySelectorAll('.eis-chip[data-cat]').forEach(b=> b.onclick=()=> setCat(b.dataset.cat));
    const vb=$('eis-voice'); if(vb) vb.onclick=toggleVoice;
  }
  function setCat(cat){
    activeCat=cat; renderChips();
    $('eis-input-row').classList.add('show'); $('eis-active-cat').textContent=cat; $('eis-input').focus();
  }
  function dismiss(){ $('eis-input-row').classList.remove('show'); activeCat=''; renderChips(); }

  // the current track from the Seinnteoir: the one playing, or the one cued next
  const curFromState = st => { const q=st.queue||[]; return q[(st.idx>=0?st.idx:0)] || null; };

  async function poll(){
    if(!active) return;
    try{
      const st = await fetch('/api/seinnteoir/state',{cache:'no-store'}).then(r=>r.json());
      qState = st;
      const t = curFromState(st);
      playing = !!st.playing; dur = st.duration || (t&&t.duration_sec) || 0;
      if (!scrubbing){ pos = st.position||0; lastPollAt = performance.now(); }
      curTrack = t;
      const newId = t ? t.track_id : null;
      if (newId !== eTrackId) await switchTrack(t);
      if (panelOpen){ renderNow(); updateTransport(); renderQueue(); }   // keep the ▶/❚❚ honest, not only on the rAF tick
    }catch(_){}
  }
  function tick(){
    if (panelOpen && playing && !scrubbing){ pos = Math.min(dur||1e9, pos + (performance.now()-lastPollAt)/1000); lastPollAt = performance.now(); }
    if (panelOpen) updateTransport();
    requestAnimationFrame(tick);
  }
  function updateTransport(){
    const pb=$('eis-play'); if(pb){ const ic=pb.querySelector('.eis-play__ico')||pb; ic.textContent = playing ? '❚❚' : '▶'; pb.classList.toggle('playing', playing); }
    if(!scrubbing){ const sc=$('eis-scrub'); if(sc) sc.value = dur>0 ? Math.min(1000,(pos/dur)*1000) : 0; }
    const tEl=$('eis-time'); if(tEl) tEl.textContent = `${efmt(pos)} / ${efmt(dur)}`;
    const vEl=$('eis-vol');
    if (vEl && qState && document.activeElement !== vEl){
      const v = (qState.volume==null?0.8:qState.volume); vEl.value = v;
      const vi=$('eis-vol-ic'); if(vi) vi.textContent = v<=0.001?'🔇':(v<0.5?'🔉':'🔊');
    }
  }
  function renderNow(){
    const t=curTrack, has=!!(t && t.track_id);
    $('eis-now-title').textContent  = has ? (t.title||'Untitled') : '—';
    $('eis-now-artist').textContent = has ? (t.artist||'') : '';
    const art=$('eis-art');
    if (has){
      if (art.dataset.tid !== String(t.track_id)){
        art.dataset.tid = String(t.track_id);
        const url=`/api/artwork/${t.track_id}?s=192`;
        const img=new Image();
        img.onload=()=>{ art.textContent=''; art.style.backgroundImage=`url("${url}")`; art.style.backgroundSize='cover'; art.style.backgroundPosition='center'; };
        img.onerror=()=>{ art.style.backgroundImage='none'; art.textContent='♪'; };
        img.src=url;
      }
    } else { art.style.backgroundImage='none'; art.textContent='♪'; art.dataset.tid=''; }
  }

  async function switchTrack(t){
    if (sid){ fetch(`/api/listen/session/${sid}/end`,{method:'POST'}).catch(()=>{}); sid=null; }
    eNotes=[]; eTrackId = t ? t.track_id : null;
    if (!eTrackId){ renderNotes(); return; }
    try{ const r = await fetch('/api/listen/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_id:eTrackId})}).then(x=>x.json()); sid=r.id; }
    catch(_){ sid=null; }
    try{ const ex = await fetch(`/api/listen/notes?track_id=${eTrackId}`).then(x=>x.json());
      eNotes = (Array.isArray(ex)?ex:(ex.notes||[])).map(n=>({id:n.id, timestamp_sec:n.timestamp_sec, note_text:n.note_text, note_category:n.note_category, is_voice:n.is_voice})); }
    catch(_){ eNotes=[]; }
    renderNotes();
  }

  function renderNotes(){
    const el=$('eis-notes'); if(!el) return;
    if (!eTrackId){ el.innerHTML=`<div class="eis-empty">Cue a record on the player to begin deep listening.</div>`; return; }
    if (!eNotes.length){ el.innerHTML=`<div class="eis-empty">No notes yet.<br>Press 1–0 to tag a moment, or V to speak one.</div>`; return; }
    const sorted = eNotes.slice().sort((a,b)=>(a.timestamp_sec||0)-(b.timestamp_sec||0));
    el.innerHTML = sorted.map(n=>`
      <div class="eis-note" data-id="${n.id}">
        <span class="eis-note__ts" data-ts="${n.id}" title="Edit the time">${efmt(n.timestamp_sec||0)}</span>
        <div class="eis-note__body">
          ${(n.note_category||n.is_voice) ? `<span class="eis-note__cat ${n.is_voice?'voice':''}" data-cat="${n.id}">${eesc(n.note_category||'')}</span>` : ''}
          <div class="eis-note__text">${eesc(n.note_text||'')}</div>
        </div>
        <button class="eis-note__del" data-del="${n.id}" title="Delete">✕</button>
      </div>`).join('');
    el.querySelectorAll('.eis-note__del').forEach(b=> b.onclick=()=> delNote(+b.dataset.del));
    el.querySelectorAll('.eis-note__ts').forEach(b=> b.onclick=()=> editTs(+b.dataset.ts));
    el.querySelectorAll('.eis-note__cat').forEach(b=> b.onclick=()=> editCat(+b.dataset.cat));
  }

  async function saveNote(text, isVoice){
    const input=$('eis-input'); const txt = text || (input?input.value.trim():'');
    if (!txt || !sid) return;
    if (input && !text) input.value='';
    const body={ note_text:txt, note_category:activeCat, timestamp_sec:Math.max(0,pos), is_voice:isVoice?1:0 };
    try{ const n = await fetch(`/api/listen/session/${sid}/note`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());
      if (n && n.id){ eNotes.push(n); renderNotes(); } }catch(_){}
  }
  function delNote(id){ fetch(`/api/listen/note/${id}`,{method:'DELETE'}).catch(()=>{}); eNotes=eNotes.filter(n=>n.id!==id); renderNotes(); }
  function editTs(id){
    const n=eNotes.find(x=>x.id===id); if(!n) return;
    const v=prompt('Time (m:ss or seconds):', efmt(n.timestamp_sec||0)); if(v==null) return;
    let sec; const m=v.trim().match(/^(\d+):(\d{1,2})$/); if(m) sec=(+m[1])*60+(+m[2]); else sec=parseFloat(v);
    if(!isFinite(sec)||sec<0) return;
    fetch(`/api/listen/note/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({timestamp_sec:sec})}).catch(()=>{});
    n.timestamp_sec=sec; renderNotes();
  }
  function editCat(id){
    const n=eNotes.find(x=>x.id===id); if(!n) return;
    const v=prompt('Category:', n.note_category||''); if(v==null) return;
    fetch(`/api/listen/note/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({note_category:v.trim()})}).catch(()=>{});
    n.note_category=v.trim(); renderNotes();
  }

  async function toggleVoice(){
    if (recording){ if (recorder && recorder.state!=='inactive') recorder.stop(); return; }
    if (!sid) return;
    try{
      const stream = await navigator.mediaDevices.getUserMedia({audio:true});
      const chunks=[]; recorder = new MediaRecorder(stream);
      recorder.ondataavailable = e=>{ if(e.data.size) chunks.push(e.data); };
      recorder.onstop = async ()=>{
        stream.getTracks().forEach(t=>t.stop()); recording=false; renderChips();
        const vb=$('eis-voice'); if(vb) vb.textContent='transcribing…';
        const blob=new Blob(chunks,{type:chunks[0]?.type||'audio/mp4'});
        const fd=new FormData(); fd.append('audio', blob, 'voice.mp4');
        try{ const d=await fetch('/api/listen/transcribe',{method:'POST',body:fd}).then(r=>r.json()); if(d.transcript) saveNote(d.transcript, true); }catch(_){}
        renderChips();
      };
      recording=true; renderChips(); recorder.start();
    }catch(_){ recording=false; renderChips(); }
  }

  // transport drives the SAME server player — full control from inside Éisteacht
  const _after = ()=> setTimeout(poll,100);
  // /toggle flips the SERVER's real state, so a press ALWAYS changes playback — it can
  // never be a silent no-op the way an explicit play/pause can when our local `playing`
  // flag has briefly lagged the server. We flip the icon optimistically for instant feel;
  // poll() (which always reads the server truth, line 295) reconciles it 150ms later.
  $('eis-play').onclick = ()=>{
    playing = !playing; lastPollAt = performance.now(); updateTransport();
    fetch('/api/seinnteoir/toggle', {method:'POST'}).then(()=>setTimeout(poll,150)); };
  $('eis-prev').onclick = ()=> fetch('/api/seinnteoir/prev',{method:'POST'}).then(_after);
  $('eis-next').onclick = ()=> fetch('/api/seinnteoir/next',{method:'POST'}).then(_after);
  const _sc=$('eis-scrub');
  _sc.addEventListener('input', ()=>{ scrubbing=true; const sec=(_sc.value/1000)*(dur||0); $('eis-time').textContent=`${efmt(sec)} / ${efmt(dur)}`; });
  _sc.addEventListener('change', ()=>{ const sec=(_sc.value/1000)*(dur||0);
    fetch('/api/seinnteoir/seek',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sec})}).then(()=>setTimeout(()=>{scrubbing=false;poll();},150)); });
  // volume — drives the SAME server player, so it controls the audio in Deep
  // Listening just like the cassette (throttled: immediate + the trailing value)
  const _vol=$('eis-vol');
  let _evolT=null,_evolLatest=null;
  function _postEVol(v){ _evolLatest=v; if(_evolT) return;
    fetch('/api/seinnteoir/volume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volume:v})}).catch(()=>{});
    _evolT=setTimeout(()=>{ _evolT=null; if(_evolLatest!==v) fetch('/api/seinnteoir/volume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volume:_evolLatest})}).catch(()=>{}); },90); }
  if(_vol) _vol.addEventListener('input', ()=>{ const v=Math.max(0,Math.min(1,parseFloat(_vol.value)||0));
    if(qState) qState.volume=v; const vi=$('eis-vol-ic'); if(vi) vi.textContent=v<=0.001?'🔇':(v<0.5?'🔉':'🔊'); _postEVol(v); });

  // ── the cue, changeable from inside Éisteacht ───────────────────────────────
  function toggleQueue(){
    const q=$('eis-queue'); const show=!q.classList.contains('show');
    if (show) $('eis-presets').classList.remove('show');
    q.classList.toggle('show', show); $('eis-queue-btn').classList.toggle('active', show);
    if (show){ qLast=''; renderQueue(); }
  }
  function ensureSortable(cb){           // share the one CDN load with seinnteoir.js (same marker)
    if (window.Sortable) return cb();
    if (document.querySelector('script[data-snt-sortable]')){ const w=()=>window.Sortable?cb():setTimeout(w,60); return w(); }
    const s=document.createElement('script'); s.src='https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
    s.setAttribute('data-snt-sortable','1'); s.onload=cb; document.head.appendChild(s);
  }
  function renderQueue(){
    const q=$('eis-queue'); if(!q || !q.classList.contains('show') || eisQDragging) return;   // don't yank a drag
    const st=qState||{}, queue=st.queue||[], idx=st.idx;
    const sig=JSON.stringify({ids:queue.map(x=>x.track_id), idx}); if(sig===qLast && q.firstChild) return; qLast=sig;
    const rows = queue.length ? queue.map((it,i)=>`
      <div class="eis-qrow ${i===idx?'active':''}" data-i="${i}" data-tid="${it.track_id}">
        <span class="eis-qrow__grip" title="Drag to reorder">⋮⋮</span>
        <span class="eis-qrow__n">${i+1}</span>
        <div class="eis-qrow__main"><div class="eis-qrow__t">${eesc(it.title||'Untitled')}</div><div class="eis-qrow__a">${eesc(it.artist||'')}</div></div>
        <button class="eis-qrow__x" data-x="${i}" title="Remove">✕</button>
      </div>`).join('') : `<div class="eis-empty">The cue is empty.<br>Close, line up records, then come back.</div>`;
    q.innerHTML = `<div class="eis-queue__head"><span>the cue · ${queue.length}</span><button class="eis-icon" id="eis-queue-x">✕</button></div><div class="eis-queue__list" id="eis-qlist">${rows}</div>`;
    $('eis-queue-x').onclick = toggleQueue;
    q.querySelectorAll('.eis-qrow__main').forEach(el=> el.onclick=()=>{ const i=+el.closest('.eis-qrow').dataset.i;
      fetch('/api/seinnteoir/play_at',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idx:i})}).then(()=>{qLast='';_after();}); });
    q.querySelectorAll('.eis-qrow__x').forEach(el=> el.onclick=(e)=>{ e.stopPropagation(); const i=+el.dataset.x;
      fetch('/api/seinnteoir/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idx:i})}).then(()=>{qLast='';_after();}); });
    // drag-to-reorder the cue (David)
    const listEl=$('eis-qlist');
    if (listEl && queue.length>1) ensureSortable(()=>{
      if (eisSortable){ try{eisSortable.destroy();}catch(_){} eisSortable=null; }
      eisSortable = window.Sortable.create(listEl, {
        handle:'.eis-qrow__grip', animation:140, ghostClass:'eis-qghost',
        onStart:()=>{ eisQDragging=true; },
        onEnd:(e)=>{ eisQDragging=false; if(e.oldIndex===e.newIndex) return;
          const ids=queue.map(x=>x.track_id); const [m]=ids.splice(e.oldIndex,1); ids.splice(e.newIndex,0,m);
          qLast=''; fetch('/api/seinnteoir/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order:ids})}).then(_after); }
      });
    });
  }

  // ── 1–0 tag shortcuts + named presets ───────────────────────────────────────
  const PKEYS = ['1','2','3','4','5','6','7','8','9','0'];
  function openPresets(){ const p=$('eis-queue'); p.classList.remove('show'); $('eis-queue-btn').classList.remove('active'); renderPresets(); $('eis-presets').classList.add('show'); }
  const _sameMap = (a,b)=>{ a=a||{}; b=b||{}; const ka=Object.keys(a), kb=Object.keys(b);
    return ka.length===kb.length && ka.every(k=> a[k]===b[k]); };
  function renderPresets(){
    const rows = PKEYS.map(k=>`<div class="eis-map-row"><span class="eis-map-key">${k}</span><input class="eis-map-in" data-k="${k}" value="${eesc(cats[k]||'')}" placeholder="a tag for ${k}…" autocomplete="off" spellcheck="false"></div>`).join('');
    const chips = presets.map((p,i)=>`<span class="eis-preset-chip ${_sameMap(p.shortcuts,cats)?'active':''}"><button class="eis-preset-use" data-p="${i}" title="Use this preset">${eesc(p.name)}</button><button class="eis-preset-x" data-del="${i}" title="Delete preset">✕</button></span>`).join('');
    $('eis-presets').innerHTML = `<div class="eis-presets__card">
        <div class="eis-presets__title">Your tag shortcuts</div>
        <div class="eis-presets__hint">Map keys 1–0 to your own tags — press a key while listening to stamp a note. These tags carry through to the listening section. Click a preset to switch to it, or save the current set as a new one.</div>
        ${presets.length?`<div class="eis-preset-bar"><span style="font-family:var(--font-mono,monospace);font-size:.62rem;letter-spacing:1px;color:var(--em);text-transform:uppercase;margin-right:2px;">presets</span>${chips}</div>`:''}
        ${rows}
        <div class="eis-presets__foot">
          <input id="eis-preset-name" placeholder="save these as a preset…" maxlength="40" autocomplete="off">
          <button class="eis-btn eis-btn--ghost" id="eis-preset-save">＋ save</button>
          <button class="eis-btn eis-btn--save" id="eis-map-apply">Apply</button>
        </div>
      </div>`;
    $('eis-presets').querySelector('.eis-presets__card').onclick = e=>e.stopPropagation();
    $('eis-presets').onclick = ()=> $('eis-presets').classList.remove('show');   // click the backdrop to close
    $('eis-map-apply').onclick = applyMapping;
    $('eis-preset-save').onclick = savePreset;
    $('eis-presets').querySelectorAll('.eis-preset-use').forEach(b=> b.onclick=(e)=>{ e.stopPropagation(); applyPreset(+b.dataset.p); });
    $('eis-presets').querySelectorAll('.eis-preset-x').forEach(b=> b.onclick=(e)=>{ e.stopPropagation(); deletePreset(+b.dataset.del); });
  }
  function readMapping(){ const m={}; $('eis-presets').querySelectorAll('.eis-map-in').forEach(inp=>{ const v=inp.value.trim(); if(v) m[inp.dataset.k]=v; }); return m; }
  async function persistCats(){ try{ await fetch('/api/listen/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shortcuts:cats, presets})}); }catch(_){} }
  async function applyMapping(){ cats = readMapping(); renderChips(); $('eis-presets').classList.remove('show'); await persistCats(); }
  async function savePreset(){
    const name=$('eis-preset-name').value.trim(); if(!name) return;
    cats = readMapping();
    presets = presets.filter(p=>p.name!==name).concat([{name, shortcuts:{...cats}}]);
    renderChips(); renderPresets(); await persistCats();
  }
  // clicking a preset SELECTS it: it becomes the active 1–0 mapping right away
  async function applyPreset(i){ const p=presets[i]; if(!p) return; cats={...p.shortcuts}; renderChips(); renderPresets(); await persistCats(); }
  async function deletePreset(i){ if(i<0||i>=presets.length) return; presets.splice(i,1); renderPresets(); await persistCats(); }

  // ── open / close ────────────────────────────────────────────────────────────
  // No minimize: you flick between Just Listen / Éisteacht / Seinnteoir from the
  // CASSETTE itself, so exiting Éisteacht simply closes it and leaves the
  // cassette. (David)
  function _fuse(){ document.body.classList.toggle('r3d-eist-open', panelOpen); }   // hide the cassette while open
  async function eisOpen(){
    if (panelOpen) return; panelOpen=true; active=true;
    const el=$('r3d-eist'); el.classList.add('open'); el.setAttribute('aria-hidden','false'); _fuse();
    const ex=$('r3d-explore'); if(ex) ex.classList.remove('show');
    if (!Object.keys(cats).length) await loadCats(); else loadCats();   // refresh presets in the background
    if (!pollTimer) pollTimer = setInterval(poll, 450);
    renderChips(); lastPollAt = performance.now(); await poll();
  }
  function eisClose(){
    if (!active && !panelOpen) return; panelOpen=false; active=false;
    const el=$('r3d-eist'); el.classList.remove('open'); el.setAttribute('aria-hidden','true'); _fuse();
    $('eis-queue').classList.remove('show'); $('eis-presets').classList.remove('show');
    if (pollTimer){ clearInterval(pollTimer); pollTimer=null; }
    if (sid){ fetch(`/api/listen/session/${sid}/end`,{method:'POST'}).catch(()=>{}); sid=null; }
    eTrackId=null;
    if (recording && recorder && recorder.state!=='inactive'){ try{recorder.stop();}catch(_){} }
    dismiss();
    if (window.Seinnteoir && window.Seinnteoir.open) window.Seinnteoir.open();   // the cassette is left
  }

  $('eis-close').onclick = eisClose;
  $('eis-queue-btn').onclick = toggleQueue;
  $('eis-presets-btn').onclick = openPresets;
  $('eis-save').onclick = ()=> saveNote();
  $('eis-dismiss').onclick = dismiss;
  $('eis-input').addEventListener('keydown', e=>{
    if (e.key==='Enter' && !e.shiftKey){ e.preventDefault(); saveNote(); }
    if (e.key==='Escape'){ e.preventDefault(); dismiss(); }
    e.stopPropagation();                       // keep digits/space off the scene
  });
  // 1–0 tag a moment, V speaks one — while the panel is open
  document.addEventListener('keydown', e=>{
    if (!panelOpen) return;
    if ($('eis-presets').classList.contains('show')) return;   // editing the mappings — keys are text
    const typing = document.activeElement && document.activeElement.id==='eis-input';
    const mod = e.metaKey || e.ctrlKey;
    if (/^[0-9]$/.test(e.key) && (!typing||mod)){ if (cats[e.key]){ e.preventDefault(); e.stopPropagation(); setCat(cats[e.key]); } }
    else if ((e.key==='v'||e.key==='V') && (!typing||mod)){ e.preventDefault(); e.stopPropagation(); toggleVoice(); }
    else if (e.key==='Escape' && !typing){ e.preventDefault(); e.stopPropagation();
      if ($('eis-queue').classList.contains('show')) toggleQueue(); else eisClose(); }
  }, true);
  requestAnimationFrame(tick);

  window.openEisteacht = eisOpen;            // the cassette's Éisteacht button + the Mála call this
})();
})();
