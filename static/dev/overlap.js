// Dev-only: eval this in a page, then call window.__chk(). Reports what is in
// the way of what:
//   covered      — a control you can see but can't fully press: some point on it
//                  (its middle, or just inside one of its corners) belongs to
//                  something else that lies on top
//   overlaps     — two controls drawn over each other
//   fixedOverlaps— two floating things (the deck, a panel, a bubble) over each other
//   offscreen    — a control of an open floating window that hangs outside the window
//   dupes        — the same label on more than one control
// Only what is actually on screen counts: a control that a scrolling box has
// scrolled half out of sight is measured by the half that shows.
// (2026-11-15: the middle-point-only check missed crosses that sat half under
// the top bar; five points per control now.)
window.__chk = (o) => {
  o = o || {};
  const shown = e => { const r = e.getBoundingClientRect();
    if (!(r.width > 4 && r.height > 4 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth)) return false;
    for (let n = e; n && n !== document.body; n = n.parentElement) { const cs = getComputedStyle(n);
      if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.05) return false; }
    return true; };
  const label = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (String(e.className || '').trim() ? '.' + String(e.className).trim().split(/\s+/).slice(0, 2).join('.') : '')
    + ':' + (e.textContent || e.title || e.value || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 18);
  // the part of a control that is really on screen: itself, cut by every box that scrolls or clips it, and by the window
  const seen = e => {
    const r = e.getBoundingClientRect(); const b = { l: Math.max(0, r.left), t: Math.max(0, r.top), r: Math.min(innerWidth, r.right), b: Math.min(innerHeight, r.bottom) };
    for (let n = e.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (/(auto|scroll|hidden|clip)/.test(cs.overflowX + ' ' + cs.overflowY)) { const q = n.getBoundingClientRect(); b.l = Math.max(b.l, q.left); b.t = Math.max(b.t, q.top); b.r = Math.min(b.r, q.right); b.b = Math.min(b.b, q.bottom); }
      if (cs.position === 'fixed') break;
    }
    return (b.r - b.l > 4 && b.b - b.t > 4) ? b : null; };
  const els = [...document.querySelectorAll('button, a[href], input, select, textarea, [role=button], [role=switch], [role=checkbox]')].filter(shown).filter(e => !e.disabled);
  // A thing that floats (the deck, a round key, a small window someone opened) and a thing that SCROLLS:
  // the scrolling one passes behind the floating one and can be scrolled clear of it. That is how a floating
  // player works, not a fault — unless the page can't scroll it clear, which `stuck` reports. o.passing = true
  // lists these anyway.
  const floater = e => { for (let n = e; n && n !== document.body; n = n.parentElement) { const cs = getComputedStyle(n);
      if (cs.position === 'fixed' || cs.position === 'sticky') { const r = n.getBoundingClientRect(); return (r.width * r.height < 0.45 * innerWidth * innerHeight) ? n : null; } } return null; };   // (a bar that sticks to the top counts: the page scrolls under it)
  const scroller = e => { for (let n = e.parentElement; n && n !== document.documentElement; n = n.parentElement) { const cs = getComputedStyle(n);
      if (/(auto|scroll)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 4) return n; if (cs.position === 'fixed') return null; }
    return document.documentElement.scrollHeight > innerHeight + 4 ? document.documentElement : null; };
  const passes = (e, top) => { const f = floater(top); return !!(f && !f.contains(e) && scroller(e)); };
  let passing = 0;
  const covered = [];
  for (const e of els) {
    const b = seen(e); if (!b) continue;
    const full = e.getBoundingClientRect();
    if ((b.r - b.l) * (b.b - b.t) < 0.35 * full.width * full.height) continue;       // mostly scrolled away: not this check's business
    const hits = {};
    for (const [fx, fy] of [[.5, .5], [.14, .22], [.86, .22], [.14, .78], [.86, .78]]) {
      const x = b.l + (b.r - b.l) * fx, y = b.t + (b.b - b.t) * fy;
      const top = document.elementFromPoint(x, y);
      if (!top || top === e || e.contains(top) || top.contains(e)) continue;
      if (top.closest('label') && top.closest('label').contains(e)) continue;          // a label drawn over its own input
      if (!o.passing && passes(e, top)) { passing++; continue; }
      const k = label(top); hits[k] = (hits[k] || 0) + 1;
    }
    for (const [k, n] of Object.entries(hits)) covered.push([label(e), 'under ' + k, n + '/5']);
  }
  const pairs = (list, min) => { const out = [];
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const a = list[i], b = list[j]; if (a.contains(b) || b.contains(a)) continue;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const ix = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), iy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
      if (ix > min && iy > min) out.push([label(a), label(b), Math.round(ix) + 'x' + Math.round(iy)]);
    } return out; };
  const overlaps = pairs(els.filter(e => seen(e)), 6).filter(() => true);
  // (the same goes for two controls: one on a floating thing, one in the scrolling page behind it)
  const elOf = lab => els.find(e => label(e) === lab);
  const overlapsReal = o.passing ? overlaps : overlaps.filter(([a, b]) => { const A = elOf(a), B = elOf(b); if (!A || !B) return true;
    return !((floater(A) && !floater(B) && scroller(B)) || (floater(B) && !floater(A) && scroller(A))); });
  // content that can NOT be scrolled clear of the deck: the last thing in a scrolling page, when the page's
  // foot is shorter than the deck is tall
  const stuck = [];
  const deck = document.querySelector('#seinnteoir-bar.visible, #seinnteoir-tab.visible');
  if (deck) { const d = deck.getBoundingClientRect();
    for (const sc of new Set(els.map(scroller).filter(Boolean))) {
      const box = sc === document.documentElement ? { top: 0, bottom: innerHeight, left: 0, right: innerWidth } : sc.getBoundingClientRect();
      if (box.bottom <= d.top || box.right <= d.left || box.left >= d.right) continue;           // this scroller doesn't reach under the deck
      const inside = els.filter(e => scroller(e) === sc && !floater(e));
      if (!inside.length) continue;
      const maxScroll = sc.scrollHeight - sc.clientHeight - sc.scrollTop;                        // how much further it can go
      let last = null; for (const e of inside) { const r = e.getBoundingClientRect(); if (r.right > d.left && r.left < d.right && (!last || r.bottom > last.getBoundingClientRect().bottom)) last = e; }
      if (last && last.getBoundingClientRect().bottom - maxScroll > d.top + 2) stuck.push([label(last), 'can only come up to ' + Math.round(last.getBoundingClientRect().bottom - maxScroll) + ', the deck starts at ' + Math.round(d.top)]);
    } }
  // floating things on top of other floating things (bubbles, pills, players, panels)
  const fixed = [...document.querySelectorAll('body *')].filter(e => getComputedStyle(e).position === 'fixed' && shown(e)
    && e.getBoundingClientRect().width < innerWidth * 0.9 && !(e.getBoundingClientRect().height > innerHeight * 0.9 && e.getBoundingClientRect().width > innerWidth * 0.6));
  const fixedOverlaps = pairs(fixed, 8);
  // a floating window's controls that hang outside the window
  const offscreen = [];
  for (const e of els) { const r = e.getBoundingClientRect();
    let f = null, scrolls = false;
    for (let n = e; n && n !== document.body; n = n.parentElement) { const cs = getComputedStyle(n);
      if (n !== e && /(auto|scroll|hidden)/.test(cs.overflowX + cs.overflowY)) scrolls = true;      // a list inside it scrolls: the rest can be reached
      if (cs.position === 'fixed') { f = n; break; } }
    if (f && !scrolls && (r.left < -1 || r.top < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1) && getComputedStyle(f).overflowY === 'visible')
      offscreen.push([label(e), 'in ' + label(f)]); }
  const texts = {}; els.forEach(e => { const t = (e.textContent || e.value || e.title || '').trim(); if (t && t.length < 30) (texts[t] = texts[t] || []).push(e); });
  const dupes = Object.entries(texts).filter(([t, l]) => l.length > 1).map(([t, l]) => t + ' ×' + l.length);
  const cap = o.all ? 999 : 14;
  return { page: location.pathname + location.search, size: innerWidth + 'x' + innerHeight, interactive: els.length,
           covered: covered.slice(0, cap), overlaps: overlapsReal.slice(0, cap), fixedOverlaps: fixedOverlaps.slice(0, cap), offscreen: offscreen.slice(0, cap),
           stuck, passing,
           dupes: o.dupes ? dupes.slice(0, 15) : undefined,
           // kept for older notes that read `blocked`
           blocked: covered.filter(c => c[2] !== '1/5' && c[2] !== '2/5').slice(0, cap) };
};
