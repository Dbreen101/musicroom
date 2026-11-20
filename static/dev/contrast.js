// __contrast(min=3): every visible element with its own text, its text colour
// against the first opaque background behind it (walking up the tree), as a
// WCAG contrast ratio. Lists the ones under `min`. Gradients/images behind the
// text count as "unknown" and are skipped. Dev only.
window.__contrast = function (min) {
  min = min || 3;
  const lum = ([r, g, b]) => { const f = c => { c /= 255; return c <= .03928 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const parse = s => { const m = (s || '').match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(Number); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; };
  const blend = (fg, bg) => fg.rgb.map((c, i) => Math.round(c * fg.a + bg[i] * (1 - fg.a)));
  const bgOf = el => {
    let acc = null;   // stack of semi-transparent layers, bottom-most last
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        if (!/gradient/.test(cs.backgroundImage)) return null;          // a picture: unknowable
        const stops = [...cs.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map(m => parse(m[0])).filter(Boolean);
        if (!stops.length) return null;
        const top = stops.reduce((a, b) => (b.a > a.a ? b : a));
        if (top.a > 0) { layers.push(top); if (top.a >= 1) break; }
        continue;
      }
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    if (!layers.length || layers[layers.length - 1].a < 1) { const b = parse(getComputedStyle(document.body).backgroundColor); if (!b || b.a < 1) return null; layers.push(b); }
    let out = layers[layers.length - 1].rgb;
    for (let i = layers.length - 2; i >= 0; i--) out = blend(layers[i], out);
    return out;
  };
  const vis = el => { const r = el.getBoundingClientRect(); if (r.width <= 1.5 || r.height <= 1.5) return false;   /* (a pixel or less: words kept for screen readers only, never seen) */ const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') return false; for (let e = el; e; e = e.parentElement) { const c = getComputedStyle(e); if (c.display === 'none' || c.visibility === 'hidden' || (c.opacity !== '' && parseFloat(c.opacity) < .15)) return false; } return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'SVG', 'PATH', 'CANVAS', 'IFRAME'].includes(el.tagName)) continue;
    const text = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!text || !vis(el)) continue;
    const cs = getComputedStyle(el);
    const fg = parse(cs.color); if (!fg) continue;
    const bg = bgOf(el); if (!bg) continue;
    const f = fg.a < 1 ? blend(fg, bg) : fg.rgb;
    const l1 = lum(f), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
    if (ratio < min) out.push({ ratio: +ratio.toFixed(2), text: text.slice(0, 40), sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''), fg: cs.color, bg: 'rgb(' + bg.join(',') + ')' });
  }
  out.sort((a, b) => a.ratio - b.ratio);
  return { page: location.pathname + location.search, low: out.length, items: out.slice(0, 40) };
};
