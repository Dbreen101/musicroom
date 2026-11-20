/* ============================================================
   BPM Tapper — a Mála/Tools utility for estimating tempo by ear.
   Tap on the beat (click the pad or hit space); it averages the
   recent intervals into a BPM. Self-contained, like deeplisten.js:
   injects its own CSS + markup, exposes window.openBpmTapper().
   Explore-desk register, hardcoded so it reads right on any page.
   ============================================================ */
(function () {
  if (window.openBpmTapper) return;   // already loaded

  const CSS = `
  .bpmt-ov{ position:fixed; inset:0; z-index:9000; display:none;
    align-items:center; justify-content:center; background:rgba(8,7,4,.86);
    font-family:'Inter',-apple-system,system-ui,sans-serif; }
  .bpmt-ov.open{ display:flex; }
  .bpmt-card{ width:min(420px,92vw); background:#161310; border:1px solid rgba(245,230,176,.16);
    border-radius:18px; padding:26px 26px 22px; box-shadow:0 24px 70px rgba(0,0,0,.6);
    text-align:center; position:relative; }
  .bpmt-h{ font-family:'JetBrains Mono',monospace; font-size:.62rem; letter-spacing:.16em;
    text-transform:uppercase; color:#f5e6b0; margin:0 0 14px; }
  .bpmt-x{ position:absolute; top:12px; right:14px; background:none; border:none; cursor:pointer;
    color:#7d7257; font-size:1rem; line-height:1; }
  .bpmt-x:hover{ color:#efe6cf; }
  .bpmt-read{ display:flex; align-items:baseline; justify-content:center; gap:2px;
    color:#efe6cf; line-height:1; margin:4px 0 2px; }
  .bpmt-int{ font-size:4.6rem; font-weight:600; font-variant-numeric:tabular-nums; }
  .bpmt-dec{ font-size:1.9rem; color:#9a8c6c; font-variant-numeric:tabular-nums; }
  .bpmt-unit{ font-family:'JetBrains Mono',monospace; font-size:.7rem; letter-spacing:.18em;
    color:#7d7257; text-transform:uppercase; margin-bottom:18px; }
  .bpmt-pad{ width:100%; padding:30px 0; border-radius:14px; cursor:pointer; user-select:none;
    background:rgba(245,230,176,.06); border:1px solid rgba(245,230,176,.22);
    color:#efe6cf; font-family:'EB Garamond',Georgia,serif; font-style:italic; font-size:1.15rem;
    transition:background .06s ease, transform .06s ease; -webkit-user-select:none; }
  .bpmt-pad:hover{ background:rgba(245,230,176,.1); }
  .bpmt-pad.hit{ background:rgba(245,230,176,.26); transform:scale(.985); }
  .bpmt-meta{ display:flex; align-items:center; justify-content:space-between; margin-top:14px;
    font-size:.78rem; color:#9a8c6c; }
  .bpmt-btn{ background:none; border:1px solid rgba(245,230,176,.24); color:#efe6cf;
    border-radius:100px; padding:6px 14px; font-size:.78rem; cursor:pointer; font-family:inherit;
    transition:all .15s; }
  .bpmt-btn:hover{ border-color:#f5e6b0; color:#f5e6b0; }
  .bpmt-count{ font-family:'JetBrains Mono',monospace; font-size:.72rem; color:#7d7257; }
  .bpmt-apply{ width:100%; margin-top:12px; border-color:rgba(245,230,176,.5)!important; color:#f5e6b0!important;
    background:rgba(245,230,176,.1); padding:9px 0; }
  .bpmt-apply:hover{ background:rgba(245,230,176,.2); }
  .bpmt-hint{ margin-top:14px; font-family:'EB Garamond',serif; font-style:italic;
    font-size:.78rem; color:#7d7257; }
  `;

  const MARKUP = `
  <div class="bpmt-card" role="dialog" aria-label="BPM tapper">
    <button class="bpmt-x" title="Close (Esc)">✕</button>
    <div class="bpmt-h">BPM Tapper</div>
    <div class="bpmt-read"><span class="bpmt-int" id="bpmt-int">—</span><span class="bpmt-dec" id="bpmt-dec"></span></div>
    <div class="bpmt-unit">beats per minute</div>
    <div class="bpmt-pad" id="bpmt-pad">tap on the beat</div>
    <div class="bpmt-meta">
      <button class="bpmt-btn" id="bpmt-reset">↺ Reset</button>
      <span class="bpmt-count" id="bpmt-count">0 taps</span>
      <button class="bpmt-btn" id="bpmt-copy">Copy</button>
    </div>
    <button class="bpmt-btn bpmt-apply" id="bpmt-apply" style="display:none;">Apply</button>
    <div class="bpmt-hint">Click the pad or tap the spacebar in time — a few bars settles it.</div>
  </div>`;

  let ov, padEl, intEl, decEl, countEl, applyEl, onApply = null;
  let taps = [];
  const WINDOW = 16;        // average the last N taps
  const RESET_GAP = 2000;   // a pause longer than this starts a fresh count

  function build() {
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    ov = document.createElement('div'); ov.className = 'bpmt-ov'; ov.innerHTML = MARKUP;
    document.body.appendChild(ov);
    padEl = ov.querySelector('#bpmt-pad');
    intEl = ov.querySelector('#bpmt-int');
    decEl = ov.querySelector('#bpmt-dec');
    countEl = ov.querySelector('#bpmt-count');
    applyEl = ov.querySelector('#bpmt-apply');

    padEl.addEventListener('pointerdown', e => { e.preventDefault(); tap(); });
    ov.querySelector('.bpmt-x').addEventListener('click', close);
    ov.querySelector('#bpmt-reset').addEventListener('click', reset);
    ov.querySelector('#bpmt-copy').addEventListener('click', copy);
    applyEl.addEventListener('click', () => {
      const b = bpm(); if (b == null || !onApply) return;
      onApply(Math.round(b * 10) / 10); close();
    });
    ov.addEventListener('pointerdown', e => { if (e.target === ov) close(); });   // click backdrop
  }

  function now() { return (window.performance && performance.now) ? performance.now() : Date.now(); }

  function bpm() {
    if (taps.length < 2) return null;
    const span = taps[taps.length - 1] - taps[0];
    if (span <= 0) return null;
    return 60000 / (span / (taps.length - 1));
  }

  function render() {
    const b = bpm();
    if (b == null) { intEl.textContent = '—'; decEl.textContent = ''; }
    else {
      const r = Math.round(b * 10) / 10;
      intEl.textContent = String(Math.floor(r));
      decEl.textContent = '.' + Math.round((r - Math.floor(r)) * 10);
    }
    countEl.textContent = taps.length + (taps.length === 1 ? ' tap' : ' taps');
  }

  function pulse() {
    padEl.classList.add('hit');
    setTimeout(() => padEl.classList.remove('hit'), 70);
  }

  function tap() {
    const t = now();
    if (taps.length && (t - taps[taps.length - 1]) > RESET_GAP) taps = [];   // fresh count
    taps.push(t);
    if (taps.length > WINDOW) taps.shift();
    render(); pulse();
  }

  function reset() { taps = []; render(); padEl.textContent = 'tap on the beat'; }

  function copy() {
    const b = bpm(); if (b == null) return;
    const val = String(Math.round(b * 10) / 10);
    if (navigator.clipboard) navigator.clipboard.writeText(val).catch(() => {});
    const btn = ov.querySelector('#bpmt-copy'); const was = btn.textContent;
    btn.textContent = 'Copied ✓'; setTimeout(() => { btn.textContent = was; }, 1100);
  }

  function onKey(e) {
    if (!ov.classList.contains('open')) return;
    if (e.key === 'Escape') { close(); return; }
    if (e.code === 'Space' || e.key === ' ' || e.key === 'Enter') {
      e.preventDefault(); tap();
    } else if (e.key === 'r' || e.key === 'R') { reset(); }
  }

  function open(opts) {
    if (!ov) build();
    reset();
    onApply = (opts && typeof opts.onApply === 'function') ? opts.onApply : null;
    applyEl.style.display = onApply ? '' : 'none';
    applyEl.textContent = (opts && opts.applyLabel) || 'Apply';
    ov.classList.add('open');
    document.addEventListener('keydown', onKey);
  }
  function close() {
    if (!ov) return;
    ov.classList.remove('open');
    document.removeEventListener('keydown', onKey);
  }

  window.openBpmTapper = open;
  window.closeBpmTapper = close;
})();
