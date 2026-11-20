// page_tones.js — the page's tones for the two 3D scenes (the room's cloud,
// the forest). The working document has paper, ink, a muted grey, a hairline
// rule and one red; the chosen theme (themes.py: Paper / Ink) says which is
// which. Read off the CSS tokens once the theme head has run, so a scene is
// drawn in exactly the page's colours and follows a theme switch on reload.
(function () {
  'use strict';
  const HEX = /^#[0-9a-fA-F]{6}$/;
  function mix(a, b, t) {
    const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    const m = (x, y) => Math.round(x + (y - x) * t);
    const r = m(pa >> 16, pb >> 16), g = m((pa >> 8) & 255, (pb >> 8) & 255), bl = m(pa & 255, pb & 255);
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + bl).toString(16).slice(1);
  }
  function token(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return HEX.test(v) ? v : fallback;
  }
  function read() {
    const bg   = token('--bg',    '#161513');
    const text = token('--text',  '#f2efe8');
    const muted = token('--muted', mix(text, bg, 0.45));
    const red  = token('--red',   '#e8554a');
    const dark = (parseInt(bg.slice(1, 3), 16) * 0.299 + parseInt(bg.slice(3, 5), 16) * 0.587 + parseInt(bg.slice(5, 7), 16) * 0.114) < 128;
    return {
      bg, text, muted, red, dark,
      rule:     mix(text, bg, 0.78),   // the hairline
      rule2:    mix(text, bg, 0.62),   // a firmer hairline
      surface:  mix(text, bg, 0.92),   // a sheet lying on the page
      surface2: mix(text, bg, 0.88),
      mix,
    };
  }
  window.MRTones = { read, mix };
})();
