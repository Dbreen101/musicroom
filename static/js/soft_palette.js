// Soft per-launch palette — every launch of a 3D page gets its own gentle
// colour cast. ONE seed per page load (never per-frame churn); the hue is
// muted and meant to be blended INTO each page's existing warm base, never
// to replace it. Saturation is clamped hard so it can never go neon, and
// green/cyan hues are dustied further (lab-green is rejected territory).
(function(){
  const hue = Math.random() * 360;                       // the launch's hue
  const drift = Math.random();                           // small per-launch variety
  const phase = Math.random() * Math.PI * 2;             // where the slow breath starts

  function hslToHex(h, s, l){
    const f = n => {
      const k = (n + h / 30) % 12;
      const a = s * Math.min(l, 1 - l);
      const c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
      return Math.round(255 * c).toString(16).padStart(2, '0');
    };
    return '#' + f(0) + f(8) + f(4);
  }
  // greens/cyans read clinical fast — keep them dustier than the warm hues
  const cool = (hue > 70 && hue < 210) ? 0.55 : 1;
  const sat = (0.26 + drift * 0.10) * cool;              // 0.14 … 0.36, clamped
  const tint = hslToHex(hue, sat, 0.30 + drift * 0.06);  // dark enough to sit behind art

  function mix(a, b, t){
    const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    const m = (sa, sb) => Math.round(sa + (sb - sa) * t);
    const r = m(pa >> 16, pb >> 16), g = m((pa >> 8) & 255, (pb >> 8) & 255), bl = m(pa & 255, pb & 255);
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + bl).toString(16).slice(1);
  }

  window.MRSoftPalette = { hue, phase, tint, mix };
})();
