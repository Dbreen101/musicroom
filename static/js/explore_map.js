/* explore_map.js — the Map in Explore: Ireland and Britain (and the small map
   on /myroom where a room's owner says where the room is).

   David, 2026-11-16: the Music Room starts in Ireland and the UK — independent
   artists and labels there — so Explore's globe gives way to a detailed map of
   the two islands. Everything there is to visit that says where it is (music
   rooms; the catalogue's publications, stations and websites) sits on the map
   at that spot. What has no place, or a place off this map, is not drawn: one
   line in the panel counts those and opens them as a list.

   What the map is:
     · the coast, the islands, the lakes and rivers, and towns by name — more
       of them the closer you go (static/data/isles.json, cut from Natural
       Earth by tools/make_isles_map.py)
     · land and water only. No borders are drawn and no countries are named
     · an equal-area drawing (Lambert's, centred between the two islands):
       a square of it stands for the same amount of ground anywhere on it
     · it opens with NORTH at the top (David, 2026-11-16: "you can make the map
       north and south orientation if we are not using the globe" — south-up was
       for the globe). One press still turns it (the key in the panel, or Look),
       and it stays how it was left
   and what keeps it from clutter:
     · things that would sit on top of each other gather into one mark with a
       count; going closer pulls them apart; things at one spot open as a list
     · the panel on the left narrows by kind and by words
   and how it is dressed (David, 2026-11-16: "the user should be able to have
   different skins/themes for the ireland uk map too"):
     · a SKIN is four colours — the sea, the land, the lines, the writing — and
       a way of filling the land (flat, in dots, ruled). Some skins follow the
       app's own look, some keep their own colours, and one is the listener's
       own. Chosen in the panel's Look; the small map on /myroom wears it too
     · the app remembers it (map_look.py), not only the page: the desktop
       window forgets what a page stores

   window.ExploreMap = { mount(host, opts), picker(host, opts), pure }
   — the same shape as ExploreGlobe (explore_globe.js), which it stands in for;
   it wears that file's styles (.gx-…) with a few of its own (.mx-…).
   Part 1 is plain maths with no page in it: test_isles_map.py runs it under node.
*/
(function (root) {
  'use strict';

  // ═══════════════ 1. plain maths: no page ═══════════════
  const DEG = Math.PI / 180, R_KM = 6371;
  const LAT0 = 54.8, LON0 = -4.4;                      // the middle of the drawing: between the two islands
  const BOX = { w: -11.2, s: 49.75, e: 2.3, n: 61.0 }; // what the map covers (tools/make_isles_map.py cuts to the same)
  const KINDS = ['room', 'publication', 'station', 'website'];
  const MERGE_PX = 46;                                 // marks nearer than this on screen are one mark
  const MIN_KM_PX = 0.01;                              // the closest view: ten metres to a pixel (two marks half a kilometre apart stand clear of each other)
  const SAME_KM = 0.5;                                 // things nearer each other than this open as a list, not by going closer

  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const s0 = Math.sin(LAT0 * DEG), c0 = Math.cos(LAT0 * DEG);
  // a place on the earth → a spot on the drawing, in "earth radii" (x east, y north of the middle)
  function project(lat, lon) {
    const p = lat * DEG, l = (lon - LON0) * DEG, sp = Math.sin(p), cp = Math.cos(p), cl = Math.cos(l);
    const k = Math.sqrt(2 / (1 + s0 * sp + c0 * cp * cl));
    return [k * cp * Math.sin(l), k * (c0 * sp - s0 * cp * cl)];
  }
  function unproject(x, y) {
    const rho = Math.hypot(x, y);
    if (rho < 1e-12) return { lat: LAT0, lon: LON0 };
    const c = 2 * Math.asin(Math.min(1, rho / 2)), sc = Math.sin(c), cc = Math.cos(c);
    return { lat: Math.asin(clamp(cc * s0 + y * sc * c0 / rho, -1, 1)) / DEG, lon: LON0 + Math.atan2(x * sc, rho * c0 * cc - y * s0 * sc) / DEG };
  }
  const inBox = (lat, lon) => lat >= BOX.s && lat <= BOX.n && lon >= BOX.w && lon <= BOX.e;
  // the box as the drawing has it (its edges curve a little: the widest reach of each)
  function extent() {
    let x0 = 9, x1 = -9, y0 = 9, y1 = -9;
    for (let i = 0; i <= 20; i++) {
      const lat = BOX.s + (BOX.n - BOX.s) * i / 20, lon = BOX.w + (BOX.e - BOX.w) * i / 20;
      for (const q of [project(lat, BOX.w), project(lat, BOX.e), project(BOX.s, lon), project(BOX.n, lon)]) {
        x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]);
      }
    }
    return { x0, x1, y0, y1 };
  }
  const kmBetween = (a, b) => Math.hypot(a.x - b.x, a.y - b.y) * R_KM;

  // Things that would sit on top of each other at this size gather into one
  // mark. `things` carry x, y (see project) and come in a settled order, so
  // the same view always gathers the same way. scale = pixels to one unit.
  function gather(things, scale, mergePx) {
    const r = (mergePx || MERGE_PX) / scale, out = [];
    for (const t of things) {
      let hit = null;
      for (const c of out) if (Math.hypot(c.x - t.x, c.y - t.y) <= r) { hit = c; break; }
      if (hit) { hit.things.push(t); const n = hit.things.length; hit.cx += (t.x - hit.cx) / n; hit.cy += (t.y - hit.cy) / n; }
      else out.push({ x: t.x, y: t.y, cx: t.x, cy: t.y, things: [t] });
    }
    for (const c of out) {
      c.id = c.things.length === 1 ? String(c.things[0].id) : 'n:' + c.things.map(t => t.id).sort().join('|');
      let far = 0;
      for (const t of c.things) far = Math.max(far, kmBetween(t, c.things[0]));
      c.spread = far;                                  // how far apart its things are, in km
    }
    return out;
  }
  // a round number of kilometres for the scale line, no longer than maxPx
  function niceKm(pxPerKm, maxPx) {
    let best = 0.1;
    for (const k of [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]) if (k * pxPerKm <= maxPx) best = k;
    return best;
  }
  // how small a town may be and still be named, by how close the view is. (Natural Earth's ranks, 0 the
  // largest: they are set for an even spread — Wick and Lerwick come early, Sheffield late — and of the 73
  // towns the file names, 15 are of rank 6 or less. A name is still left out where it would run into another.)
  // (a very small drawing — the place picker's — names only the three largest)
  function rankFor(kmPerPx) { return kmPerPx > 3.4 ? 3 : kmPerPx > 1.6 ? 6 : kmPerPx > 1.0 ? 7 : 12; }
  function fold(s) { return String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function hayOf(t) { return fold([t.name, t.blurb, t.kind, t.sub, t.place && t.place.name].concat(t.tags || []).filter(Boolean).join(' ')); }
  function matches(hay, words) { for (const w of words) if (hay.indexOf(w) < 0) return false; return true; }

  // ── skins: how the map is dressed ──
  // A skin is four colours — the sea, the land, the lines (coast, rivers), the writing (names, marks) — and a way
  // of filling the land: flat, in dots, or ruled. A colour is '#rrggbb'; or a NUMBER, "this far from the page's
  // ground (0) to its ink (1)", which is how a skin follows whatever look the app is in. `base` fixes the ground
  // and the ink instead of following the app. Everything finer (rivers, the far shore, towns' names, the scale
  // line, the slip a mark's name stands on) is worked out from the four, unless the skin says it itself.
  const FILLS = ['flat', 'dots', 'lines'];
  const SKINS = [
    { id: 'page', name: 'As the app', say: 'The same colours as the rest of the app', follow: true, sea: 0, land: 0.075, line: 0.86, text: 1, slip: 0 },
    { id: 'paper', name: 'Paper', say: 'Light, whatever the app is wearing', base: ['#f2efe8', '#161513'], sea: 0, land: 0.075, line: 0.86, text: 1, slip: 0, red: '#c9412f' },
    { id: 'ink', name: 'Ink', say: 'Dark, whatever the app is wearing', base: ['#161513', '#f2efe8'], sea: 0, land: 0.075, line: 0.86, text: 1, slip: 0, red: '#e8554a' },
    { id: 'land', name: 'Solid land', say: 'The land filled in', sea: 0, land: 0.9, line: 0.9, text: 0 },
    { id: 'sea', name: 'Solid sea', say: 'The sea filled in', sea: 0.9, land: 0, line: 0.9, text: 1 },
    { id: 'dots', name: 'Dotted', say: 'The land in dots', sea: 0, land: 0, line: 0.86, text: 1, fill: 'dots', coast: 0.36 },
    { id: 'ruled', name: 'Ruled', say: 'The land in ruled lines', sea: 0, land: 0, line: 0.86, text: 1, fill: 'lines' },
    { id: 'chart', name: 'Chart', say: 'A pale sea and a warm land', sea: '#d9e3e3', land: '#efe6cf', line: '#2a3439', text: '#1e272b', river: '#7fa1aa', lake: '#7fa1aa' },
    { id: 'blueprint', name: 'Blueprint', say: 'Light lines on blue', sea: '#1e3d6b', land: '#25497c', line: '#eef2f7', text: '#eef2f7', red: '#ff8a70' },
  ];
  const hexRgb = v => { const m = /^#?([0-9a-f]{6})$/i.exec(String(v == null ? '' : v).trim()); return m ? [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16)) : null; };
  const rgbHex = c => '#' + c.map(v => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('');
  const mixRgb = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  // how bright a colour is, and how far apart two are (the usual sum: 1 = the same, 21 = black on white)
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // the listener's own skin, as it is kept: four colours and a fill, or nothing
  function cleanOwn(o) {
    if (!o || typeof o !== 'object') return null;
    const out = {};
    for (const k of ['sea', 'land', 'line', 'text']) { const c = hexRgb(o[k]); if (!c) return null; out[k] = rgbHex(c); }
    out.fill = FILLS.indexOf(o.fill) >= 0 ? o.fill : 'flat';
    return out;
  }
  function skinFor(id, own) {
    if (id === 'own') { const o = cleanOwn(own); if (o) return Object.assign({ id: 'own', name: 'Your own' }, o); }
    for (const s of SKINS) if (s.id === id) return s;
    return SKINS[0];
  }
  // A skin on a page → every colour the drawing uses, as 'rgb(…)' (and as numbers, under .rgb).
  //   page = { bg, ink, red, map: { sea, land, line, text } } — each [r, g, b] or missing: the app's own colours,
  //   and the map's four where the app's theme says them itself (only the skin that follows the app listens)
  function tonesFor(skin, page) {
    skin = skin || SKINS[0]; page = page || {};
    const bg = (skin.base && hexRgb(skin.base[0])) || page.bg || [242, 239, 232], ink = (skin.base && hexRgb(skin.base[1])) || page.ink || [22, 21, 19];
    const col = v => typeof v === 'number' ? mixRgb(bg, ink, clamp(v, 0, 1)) : hexRgb(v);
    const said = (skin.follow && page.map) || {};
    const sea = said.sea || col(skin.sea) || bg, land = said.land || col(skin.land) || mixRgb(bg, ink, 0.075);
    const line = said.line || col(skin.line) || mixRgb(bg, ink, 0.86), text = said.text || col(skin.text) || ink;
    // the ground that writing is given where it needs one (a mark's name stands on a slip of it): the land, mostly
    const slip = (skin.slip != null && !said.sea && !said.land && col(skin.slip)) || land;
    // where the lines are the land's own colour (a land filled solid) the water in it is drawn in the sea's
    const water = contrast(line, land) < 1.3 ? mixRgb(land, sea, 0.45) : null;
    // a town's name: quieter than the marks, and always readable on its ground
    let t = 0.61, name = mixRgb(slip, text, t);
    while (contrast(name, slip) < 4.5 && t < 1) { t = Math.min(1, t + 0.03); name = mixRgb(slip, text, t); }
    // the scale line stands on the sea: the writing's colour if that shows there, else whatever shows best
    let scale = text;
    if (contrast(scale, sea) < 3) {
      scale = [slip, land, line].find(c => contrast(c, sea) >= 4.5) || (contrast([0, 0, 0], sea) > contrast([255, 255, 255], sea) ? [0, 0, 0] : [255, 255, 255]);
    }
    // the one red (the thing that is chosen): the skin's or the page's own where it shows, else a red that does, else the writing
    let red = text;
    for (const c of [hexRgb(skin.red), page.red, [201, 65, 47], [232, 85, 74], [255, 138, 112]]) if (c && contrast(c, slip) >= 3) { red = c; break; }
    const rgb = {
      sea, land, line, text, slip, name, scale, red,
      coast: (skin.coast != null && col(skin.coast)) || line,
      far: mixRgb(sea, land, 0.4), farEdge: mixRgb(sea, line, 0.3),
      lake: (skin.lake != null && col(skin.lake)) || water || mixRgb(land, line, 0.55),
      river: (skin.river != null && col(skin.river)) || water || mixRgb(land, line, 0.29),
      town: mixRgb(land, text, 0.92),
      tex: mixRgb(land, line, skin.fill === 'lines' ? 0.5 : 0.85),          // the dots, or the ruled lines
      border: mixRgb(slip, text, 0.2), border2: mixRgb(slip, text, 0.38),
    };
    // (tag: the slip is not the sea's colour, so a town's name that runs out over the water stands on a tag of it —
    //  as a mark's name does — where otherwise a thin edge of the slip round the letters is enough)
    const out = { fill: FILLS.indexOf(skin.fill) >= 0 ? skin.fill : 'flat', tag: Math.max.apply(null, slip.map((v, i) => Math.abs(v - sea[i]))) >= 12, rgb };
    for (const k in rgb) out[k] = 'rgb(' + rgb[k].map(v => clamp(Math.round(v), 0, 255)).join(',') + ')';
    return out;
  }
  // The land's dots, and its ruled lines, are fixed to the ground: they move with the map. Going closer spreads
  // them, so new ones come up in the gaps — and each grows as the view goes in, by just as much as keeps the land
  // one even tone. `steps` to a halving of the pitch: 1 (a new line between every two) or 2 (dots: first one in
  // the middle of every four, then one between every two).
  //   → { p: the pitch now, in the drawing's units · odd: the half-way dots are whole · grow: how much of a new
  //       one there is yet, 0 → 1 (of its area, or of a line's width) }
  const P0 = 0.064;                                    // the widest pitch (about 400 km): halved until it suits the view
  function lattice(s, px, steps) {
    const n = steps === 2 ? 2 : 1, lv = Math.max(0, n * Math.log2(s * P0 / px)), L = Math.floor(lv);
    return { p: P0 / Math.pow(2, Math.floor(L / n)), odd: n === 2 && L % 2 === 1, grow: Math.pow(2, lv - L) - 1 };
  }

  const pure = { DEG, R_KM, LAT0, LON0, BOX, KINDS, MERGE_PX, MIN_KM_PX, SAME_KM, project, unproject, inBox, extent, gather, niceKm, rankFor, fold, hayOf, matches,
                 SKINS, FILLS, P0, hexRgb, rgbHex, mixRgb, contrast, cleanOwn, skinFor, tonesFor, lattice };
  if (typeof module !== 'undefined' && module.exports) { module.exports = pure; return; }

  // ═══════════════ 2. small page helpers ═══════════════
  function h(tag, attrs) {
    const el = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v; else if (k === 'text') el.textContent = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (let i = 2; i < arguments.length; i++) {
      const kid = arguments[i];
      if (kid == null || kid === false) continue;
      if (Array.isArray(kid)) { for (const x of kid) if (x != null && x !== false) el.append(x.nodeType ? x : document.createTextNode(String(x))); }
      else el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const KIND_MANY = { room: 'Music rooms', publication: 'Publications', station: 'Stations', website: 'Websites' };
  const KIND_ONE = { room: 'music room', publication: 'publication', station: 'station', website: 'website' };
  const SUB_MANY = { artist: 'artists', label: 'labels', shop: 'record shops', venue: 'venues', business: 'businesses', listener: 'listeners' };
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  const glyph = kind => h('i', { class: 'gx-g gx-g--' + kind, 'aria-hidden': 'true' });
  const PREFS_KEY = 'mr_map';
  const LOOK_KEYS = ['skin', 'own', 'up', 'towns', 'rivers'];   // the part of what is remembered that is the map's look
  function loadPrefs() {
    let p = {};
    try { p = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') || {}; } catch (_) {}
    const num = v => typeof v === 'number' && v === v;
    // (the look — the skin, which way is up, what is drawn — is also kept by the app, and the app's word wins:
    //  the page that holds the map writes it in as MR_MAP_LOOK. The desktop window forgets what a page stores.)
    const kept = root.MR_MAP_LOOK && typeof root.MR_MAP_LOOK === 'object' ? root.MR_MAP_LOOK : {};
    for (const k of LOOK_KEYS) if (kept[k] != null) p[k] = kept[k];
    return { kinds: p.kinds || {}, subs: p.subs || {}, up: p.up === -1 ? -1 : 1, towns: p.towns !== false, rivers: p.rivers !== false,
             skin: typeof p.skin === 'string' && p.skin ? p.skin : 'page', own: cleanOwn(p.own),
             shut: p.shut || { look: true }, view: p.view && num(p.view.x) && num(p.view.y) && num(p.view.s) ? p.view : null };   // (view.whole: it was left showing all of the map)
  }
  function savePrefs(p) { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch (_) {} }
  // the look is kept twice: by the page, at once; and by the app, a moment later (so a colour being dragged is one saving)
  let lookT = 0;
  function saveLook(p) {
    savePrefs(p);
    const look = {}; for (const k of LOOK_KEYS) look[k] = p[k];
    root.MR_MAP_LOOK = look;
    clearTimeout(lookT);
    lookT = setTimeout(() => {
      try { fetch('/api/isles/look', { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(look) }).catch(() => {}); } catch (_) {}
    }, 350);
  }

  // the outline, read once and turned into shapes the canvas can draw at any size
  let dataP = null;
  function loadData() {
    return dataP || (dataP = fetch('/static/data/isles.json').then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
      const shape = (list, closed) => {
        const p = new Path2D();
        for (const r of list || []) {
          for (let i = 0; i + 1 < r.length; i += 2) { const q = project(r[i + 1], r[i]); if (i) p.lineTo(q[0], q[1]); else p.moveTo(q[0], q[1]); }
          if (closed) p.closePath();
        }
        return p;
      };
      return { land: shape(d.land, true), far: shape(d.far, true), lakes: shape(d.lakes, true), rivers: shape(d.rivers, false),
               places: (d.places || []).map(p => { const q = project(p[1], p[2]); return { name: p[0], x: q[0], y: q[1], rank: p[3] }; }),
               rough: !(d.places || []).length };
    }));
  }
  // the app's own colours where the map stands, as numbers (see tonesFor). `el` must be outside the drawing's
  // stage: the stage is given the skin's colours as its own tokens, and would answer with those.
  let probe = null;
  function pageOf(el) {
    const cs = getComputedStyle(el);
    probe = probe || document.createElement('canvas').getContext('2d');
    const read = name => {
      const raw = (cs.getPropertyValue(name) || '').trim();
      if (!raw) return null;
      probe.fillStyle = '#000001'; probe.fillStyle = raw; const a = probe.fillStyle;
      probe.fillStyle = '#000002'; probe.fillStyle = raw;
      if (probe.fillStyle !== a) return null;                       // not a colour: the probe kept its own
      const n = hexRgb(a) || (String(a).match(/[\d.]+/g) || []).map(Number).slice(0, 3);
      return n.length === 3 ? n : null;
    };
    const map = { sea: read('--map-sea'), land: read('--map-land'), line: read('--map-line'), text: read('--map-text') };
    return { bg: read('--bg') || [242, 239, 232], ink: read('--text') || [22, 21, 19], red: read('--red'),
             map: map.sea || map.land || map.line || map.text ? map : null };
  }

  // One drawing of the land and the water, in a skin's colours (T, from tonesFor).
  //   g = { W, H, dpr, cx, cy, s, up }: the picture's size, the spot of the drawing at its middle, pixels to a
  //   unit, which way is up. The big map and each skin's small picture are both drawn by this.
  const DOT_PX = 6, DOT = 2.1, RULE_PX = 5, RULE = 0.8;  // dots: this far apart at their closest, this wide · ruled lines the same
  function paint(ctx, D, T, g, o) {
    o = o || {};
    const s = g.s, up = g.up, dpr = g.dpr, thin = o.thin || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = T.sea; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    if (!D) return;
    const k = up * s * dpr, ox = (g.W / 2 - up * g.cx * s) * dpr, oy = (g.H / 2 + up * g.cy * s) * dpr;
    const ground = () => ctx.setTransform(k, 0, 0, -k, ox, oy);
    ground(); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.fillStyle = T.far; ctx.fill(D.far); ctx.strokeStyle = T.farEdge; ctx.lineWidth = thin / s; ctx.stroke(D.far);
    ctx.fillStyle = T.land; ctx.fill(D.land);
    if (T.fill !== 'flat') {
      ctx.save(); ctx.clip(D.land); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      (T.fill === 'dots' ? dots : rules)(ctx, T, g);
      ctx.restore();
    }
    const kmPx = R_KM / s;
    if (o.rivers !== false && kmPx < 1.6) { ctx.strokeStyle = T.river; ctx.lineWidth = (kmPx < 0.5 ? 1.2 : 0.8) * thin / s; ctx.stroke(D.rivers); }
    ctx.fillStyle = T.sea; ctx.fill(D.lakes); ctx.strokeStyle = T.lake; ctx.lineWidth = 0.7 * thin / s; ctx.stroke(D.lakes);
    ctx.strokeStyle = T.coast; ctx.lineWidth = 1.1 * thin / s; ctx.stroke(D.land);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  // (both are drawn in the picture's own pixels, inside the land's outline; see lattice() for how they hold still)
  function dots(ctx, T, g) {
    const L = lattice(g.s, DOT_PX, 2), p = L.p, s = g.s, young = DOT * Math.sqrt(L.grow);
    const hw = g.W / 2 / s + p, hh = g.H / 2 / s + p;
    const put = (fx, fy, side) => {
      if (side < 0.3) return;
      for (let j = Math.ceil((g.cy - hh) / p - fy); (j + fy) * p <= g.cy + hh; j++) {
        const y = g.H / 2 - g.up * ((j + fy) * p - g.cy) * s - side / 2;
        for (let i = Math.ceil((g.cx - hw) / p - fx); (i + fx) * p <= g.cx + hw; i++) ctx.rect(g.W / 2 + g.up * ((i + fx) * p - g.cx) * s - side / 2, y, side, side);
      }
    };
    ctx.beginPath();
    put(0, 0, DOT);
    if (L.odd) { put(0.5, 0.5, DOT); put(0.5, 0, young); put(0, 0.5, young); } else put(0.5, 0.5, young);
    ctx.fillStyle = T.tex; ctx.fill();
  }
  function rules(ctx, T, g) {
    const L = lattice(g.s, RULE_PX, 1), p = L.p, s = g.s, hh = g.H / 2 / s + p;
    const run = (f, w) => {
      if (w < 0.06) return;
      ctx.beginPath();
      for (let j = Math.ceil((g.cy - hh) / p - f); (j + f) * p <= g.cy + hh; j++) { const y = g.H / 2 - g.up * ((j + f) * p - g.cy) * s; ctx.moveTo(-2, y); ctx.lineTo(g.W + 2, y); }
      ctx.lineWidth = w; ctx.stroke();
    };
    ctx.lineCap = 'butt'; ctx.strokeStyle = T.tex;
    run(0, RULE); run(0.5, RULE * L.grow);
  }
  // a skin's small picture: the same stretch of both islands in each (the North Channel: Antrim, Galloway, Man),
  // with one mark on it, drawn as the map's marks are
  const THUMB = (() => { const q = project(54.42, -5.05), m = project(54.6, -5.93); return { x: q[0], y: q[1], mx: m[0], my: m[1], km: 390, W: 60, H: 45 }; })();
  function thumb(cv, D, T) {
    const W = THUMB.W, H = THUMB.H, dpr = Math.min(2, root.devicePixelRatio || 1), s = W / (THUMB.km / R_KM);
    if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const ctx = cv.getContext('2d');
    paint(ctx, D, T, { W, H, dpr, cx: THUMB.x, cy: THUMB.y, s, up: 1 }, { thin: 0.8, rivers: false });
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!D) return;
    const x = Math.round(W / 2 + (THUMB.mx - THUMB.x) * s), y = Math.round(H / 2 - (THUMB.my - THUMB.y) * s);
    ctx.fillStyle = T.slip; ctx.fillRect(x - 4.5, y - 4.5, 9, 9);
    ctx.fillStyle = T.text; ctx.fillRect(x - 2.5, y - 2.5, 5, 5);
  }

  // ═══════════════ 3. the drawing: one canvas that can be moved and gone into ═══════════════
  //   o: { up, view, onDraw(), onTap(lat, lon, x, y), onSettle(), taken() → [[x0,y0,x1,y1]…] (where marks are: no town name there),
  //        skin() → the skin it wears now, page: an element that has the app's own colours (not the stage),
  //        scale: false → no scale line (the small map's keys stand in that corner) }
  function createView(stage, o) {
    o = o || {};
    const canvas = h('canvas', { class: 'gx-canvas' });
    stage.prepend(canvas);
    const ctx = canvas.getContext('2d');
    const EXT = extent();
    let W = 0, H = 0, dpr = 1, cx = (EXT.x0 + EXT.x1) / 2, cy = (EXT.y0 + EXT.y1) / 2, s = 0, up = o.up === -1 ? -1 : 1;
    let D = null, T = null, raf = 0, fly = null, dead = false, show = { towns: true, rivers: true };
    // Its skin: the drawing's colours — and the marks', which are the page's own things (their names on slips,
    // the keys of the small map): the stage is given the skin's colours as its tokens, and they follow.
    function dress() {
      T = tonesFor(o.skin ? o.skin() : null, pageOf(o.page || stage.parentElement || stage));
      const st = stage.style;
      st.setProperty('--bg', T.slip); st.setProperty('--text', T.text); st.setProperty('--muted', T.name);
      st.setProperty('--border', T.border); st.setProperty('--border2', T.border2); st.setProperty('--red', T.red);
    }
    dress();
    const fit = () => Math.min(W / (EXT.x1 - EXT.x0), H / (EXT.y1 - EXT.y0)) * 0.96;
    const closest = () => R_KM / MIN_KM_PX;
    function tidy() {
      s = clamp(s || fit(), fit() * 0.85, closest());
      cx = clamp(cx, EXT.x0, EXT.x1); cy = clamp(cy, EXT.y0, EXT.y1);
    }
    const isWhole = () => s > 0 && Math.abs(s / fit() - 1) < 1e-6;
    function measure() {
      const r = stage.getBoundingClientRect(), first = !W;
      const whole = !first && isWhole();                    // it was showing all of the map: it still should, whatever size the page has become
      W = Math.max(1, r.width); H = Math.max(1, r.height); dpr = Math.min(2, root.devicePixelRatio || 1);
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      if (first && o.view && !o.view.whole) { cx = o.view.x; cy = o.view.y; s = o.view.s; }
      else if (first || whole) { s = fit(); if (whole || first) { cx = (EXT.x0 + EXT.x1) / 2; cy = (EXT.y0 + EXT.y1) / 2; } }
      tidy();
    }
    // is there land at this spot on the stage — or within a few pixels of it (the very shore, an island a few pixels wide)?
    function isLand(px, py) {
      if (!D) return true;
      const k = up * s * dpr;
      ctx.save();
      ctx.setTransform(k, 0, 0, -k, (W / 2 - up * cx * s) * dpr, (H / 2 + up * cy * s) * dpr);
      let hit = false;
      for (const d of [[0, 0], [5, 0], [-5, 0], [0, 5], [0, -5], [4, 4], [-4, 4], [4, -4], [-4, -4]])
        if (ctx.isPointInPath(D.land, (px + d[0]) * dpr, (py + d[1]) * dpr)) { hit = true; break; }
      ctx.restore();
      return hit;
    }
    const toScreen = (x, y) => [W / 2 + up * (x - cx) * s, H / 2 - up * (y - cy) * s];
    const toMap = (px, py) => [cx + up * (px - W / 2) / s, cy - up * (py - H / 2) / s];

    function draw() {
      if (dead) return;
      paint(ctx, D, T, { W, H, dpr, cx, cy, s, up }, { rivers: show.rivers });
      if (!D) return;
      const kmPx = R_KM / s;
      if (show.towns && D.places.length) towns(kmPx);
      if (o.scale !== false) scaleLine(kmPx);
    }
    function towns(kmPx) {
      const most = rankFor(kmPx), used = (o.taken ? o.taken() : []).slice();
      used.push([0, H - 34, 210, H]);                               // (the scale line's corner is kept clear of names)
      ctx.font = '10.5px "IBM Plex Mono", ui-monospace, Menlo, monospace'; ctx.textBaseline = 'middle';
      const free = b => { for (const u of used) if (b[0] < u[2] && b[2] > u[0] && b[1] < u[3] && b[3] > u[1]) return false; return true; };
      for (const p of D.places) {
        if (p.rank > most) break;                                   // (they come largest first)
        const q = toScreen(p.x, p.y), x = q[0], y = q[1];
        if (x < -40 || x > W + 40 || y < -12 || y > H + 12) continue;
        const text = p.name.toUpperCase(), w = ctx.measureText(text).width + 4;
        let box = [x + 6, y - 7, x + 8 + w, y + 7], lx = x + 7;
        if (!free(box)) { box = [x - 8 - w, y - 7, x - 6, y + 7]; lx = x - 5 - w; if (!free(box)) continue; }
        used.push(box, [x - 4, y - 4, x + 4, y + 4]);
        ctx.fillStyle = T.town; ctx.fillRect(Math.round(x) - 1.5, Math.round(y) - 1.5, 3, 3);
        if (T.tag) { ctx.fillStyle = T.slip; ctx.fillRect(lx - 3, y - 7, w + 2, 14); }
        else { ctx.lineWidth = 3; ctx.lineJoin = 'round'; ctx.strokeStyle = T.slip; ctx.strokeText(text, lx, y + 0.5); }
        ctx.fillStyle = T.name; ctx.fillText(text, lx, y + 0.5);
      }
    }
    function scaleLine(kmPx) {
      const km = niceKm(1 / kmPx, 120), len = km / kmPx, x = 16, y = H - 18, text = km < 1 ? km * 1000 + ' M' : km + ' KM';
      const line = () => { ctx.beginPath(); ctx.moveTo(x + 0.5, y - 4); ctx.lineTo(x + 0.5, y + 0.5); ctx.lineTo(x + len + 0.5, y + 0.5); ctx.lineTo(x + len + 0.5, y - 4); ctx.stroke(); };
      ctx.font = '9.5px "IBM Plex Mono", ui-monospace, Menlo, monospace'; ctx.textBaseline = 'alphabetic'; ctx.lineJoin = 'round'; ctx.lineCap = 'butt';
      // (it stands on a little of the sea's colour, so it reads over land, a coast or a filled sea alike)
      ctx.strokeStyle = T.sea; ctx.lineWidth = 4; line(); ctx.lineWidth = 3; ctx.strokeText(text, x + len + 8, y + 1);
      ctx.strokeStyle = T.scale; ctx.lineWidth = 1; line(); ctx.fillStyle = T.scale; ctx.fillText(text, x + len + 8, y + 1);
    }
    function frame() { raf = 0; if (dead) return; draw(); if (o.onDraw) o.onDraw(); }
    // (a page that isn't on show gets no animation frames: then it is drawn at once)
    function poke() { if (dead) return; if (document.hidden) return frame(); if (!raf) raf = requestAnimationFrame(frame); }
    function settle() { if (o.onSettle) o.onSettle(); }

    function zoomAt(factor, px, py) {
      if (px == null) { px = W / 2; py = H / 2; }
      const before = toMap(px, py);
      s = clamp(s * factor, fit() * 0.85, closest());
      const after = toMap(px, py);
      cx += before[0] - after[0]; cy += before[1] - after[1];
      tidy(); poke();
    }
    function flyTo(t, ms) {
      const to = { x: t.x != null ? t.x : cx, y: t.y != null ? t.y : cy, s: clamp(t.s || s, fit() * 0.85, closest()) };
      if (!ms || document.hidden || (root.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) { cx = to.x; cy = to.y; s = to.s; fly = null; tidy(); poke(); settle(); return; }
      const from = { x: cx, y: cy, s }, t0 = performance.now();
      fly = to;
      const step = now => {
        if (fly !== to || dead) return;
        const a = Math.min(1, (now - t0) / ms), e = a < .5 ? 2 * a * a : 1 - Math.pow(-2 * a + 2, 2) / 2;
        cx = from.x + (to.x - from.x) * e; cy = from.y + (to.y - from.y) * e; s = Math.exp(Math.log(from.s) + (Math.log(to.s) - Math.log(from.s)) * e);
        draw(); if (o.onDraw) o.onDraw();
        if (a < 1) requestAnimationFrame(step); else { fly = null; settle(); }
      };
      requestAnimationFrame(step);
    }

    // moving it: drag; going closer: scroll, pinch, double-click, + and −
    let down = null, dragging = false;
    const local = e => { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    stage.addEventListener('pointerdown', e => {
      if (e.button !== 0 || (e.target.closest && e.target.closest('button, a, input'))) return;
      down = { x: e.clientX, y: e.clientY, id: e.pointerId }; dragging = false; fly = null;
    });
    stage.addEventListener('pointermove', e => {
      if (!down || e.pointerId !== down.id) return;
      const dx = e.clientX - down.x, dy = e.clientY - down.y;
      if (!dragging) {
        if (Math.hypot(dx, dy) < 4) return;
        dragging = true; stage.classList.add('is-dragging');
        try { stage.setPointerCapture(e.pointerId); } catch (_) {}        // (only once it is a drag: capturing at the press would eat the click)
      }
      cx -= up * dx / s; cy += up * dy / s; down.x = e.clientX; down.y = e.clientY;
      tidy(); poke();
    });
    const lift = e => {
      if (!down || e.pointerId !== down.id) return;
      const was = dragging, xy = local(e);
      down = null; dragging = false; stage.classList.remove('is-dragging');
      try { stage.releasePointerCapture(e.pointerId); } catch (_) {}
      if (was) return settle();
      if (e.type === 'pointerup' && o.onTap && !(e.target.closest && e.target.closest('button, a, input'))) {
        const m = toMap(xy[0], xy[1]), ll = unproject(m[0], m[1]);
        o.onTap(ll.lat, ll.lon, xy[0], xy[1]);
      }
    };
    stage.addEventListener('pointerup', lift); stage.addEventListener('pointercancel', lift);
    let wheelT = 0;
    stage.addEventListener('wheel', e => {
      if (o.wheelNeedsPress && !(e.ctrlKey || e.metaKey)) return;       // (the small map lets the page scroll past it)
      e.preventDefault();
      const xy = local(e);
      zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0022)), xy[0], xy[1]);
      clearTimeout(wheelT); wheelT = setTimeout(settle, 160);
    }, { passive: false });
    stage.addEventListener('dblclick', e => {
      if (e.target.closest && e.target.closest('button, a, input')) return;
      const xy = local(e), m = toMap(xy[0], xy[1]);
      flyTo({ x: m[0], y: m[1], s: s * 2 }, 380);
    });
    stage.addEventListener('keydown', e => {
      if (e.target !== stage) return;
      const k = e.key, step = 70 / s;
      if (k === 'ArrowLeft') cx -= up * step; else if (k === 'ArrowRight') cx += up * step;
      else if (k === 'ArrowUp') cy += up * step; else if (k === 'ArrowDown') cy -= up * step;
      else if (k === '+' || k === '=') { zoomAt(1.5); settle(); e.preventDefault(); e.stopPropagation(); return; }
      else if (k === '-' || k === '_') { zoomAt(1 / 1.5); settle(); e.preventDefault(); e.stopPropagation(); return; }
      else return;
      e.preventDefault(); e.stopPropagation(); tidy(); poke(); settle();
    });
    const ro = root.ResizeObserver ? new ResizeObserver(() => { measure(); poke(); settle(); }) : null;
    measure();
    if (ro) ro.observe(stage);
    loadData().then(d => { D = d; if (o.onData) o.onData(d); poke(); }).catch(() => { if (o.onData) o.onData(null); });

    return {
      stage, toScreen, toMap, poke, frame, flyTo, zoomAt, measure, isLand,
      get s() { return s; }, get W() { return W; }, get H() { return H; }, get up() { return up; }, get kmPx() { return R_KM / s; },
      get view() { return { x: cx, y: cy, s, whole: isWhole() }; }, get fit() { return fit(); }, get closest() { return closest(); }, get data() { return D; },
      whole(ms) { flyTo({ x: (EXT.x0 + EXT.x1) / 2, y: (EXT.y0 + EXT.y1) / 2, s: fit() }, ms); },
      turn(v) { up = v === -1 ? -1 : 1; poke(); settle(); },
      look(v) { show = Object.assign(show, v); poke(); },
      tones() { dress(); poke(); }, get skin() { return T; },
      dispose() { dead = true; if (raf) cancelAnimationFrame(raf); if (ro) ro.disconnect(); canvas.remove(); },
    };
  }

  // ═══════════════ 4. the Map view ═══════════════
  function mount(host, opts) {
    opts = opts || {};
    const prefs = loadPrefs();
    host.classList.add('gx', 'mx'); host.textContent = '';
    const panel = h('aside', { class: 'gx-panel', 'aria-label': 'What the map shows' });
    const stage = h('div', { class: 'gx-stage', tabindex: '0', role: 'application', 'aria-label': 'A map of Ireland and Britain. Drag to move it; scroll to go closer or step back.' });
    const marksEl = h('div', { class: 'gx-marks' });
    const note = h('div', { class: 'gx-note', role: 'status' });
    const bar = h('div', { class: 'gx-btns mx-keys' });          // the map's own keys live in the panel: nothing but the map's marks is ever on the map
    const sheet = h('aside', { class: 'gx-sheet', 'aria-label': 'Things here' });
    const drawer = h('button', { class: 'gx-drawer', type: 'button', 'aria-expanded': 'false', onclick: () => { const open = host.classList.toggle('gx--panelopen'); drawer.setAttribute('aria-expanded', String(open)); drawer.textContent = open ? 'Close' : 'Show and find'; } }, 'Show and find');
    stage.append(marksEl, note);
    host.append(panel, stage, drawer, sheet);

    const S = { all: [], on: [], off: [], find: '', words: [], sel: null, roomsError: null, loading: 0, sheet: null, rough: false };
    const marks = new Map();
    let view = null, visible = false, booted = false, saveT = 0, findT = 0, lastLevel = null;

    function setNote(text) { note.textContent = text || ''; note.classList.toggle('on', !!text); }

    // ── what there is ──
    function adopt(list, part) {
      const keep = S.all.filter(t => (part === 'rooms') !== (t.kind === 'room'));
      for (const t of list || []) {
        t.tags = t.tags || []; t._hay = hayOf(t); t._fn = fold(t.name);
        const p = t.place;
        if (p && isFinite(p.lat) && isFinite(p.lon) && inBox(+p.lat, +p.lon)) { const q = project(+p.lat, +p.lon); t.x = q[0]; t.y = q[1]; t.here = true; }
        else t.here = false;
        keep.push(t);
      }
      keep.sort((a, b) => (KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind)) || (a._fn < b._fn ? -1 : a._fn > b._fn ? 1 : 0) || (String(a.id) < String(b.id) ? -1 : 1));
      S.all = keep;
    }
    async function load() {
      const mine = ++S.loading;
      const get = async part => { const r = await fetch((opts.thingsUrl || '/api/globe/things') + '?part=' + part); if (!r.ok) throw 0; return r.json(); };
      try { const d = await get('sources'); if (mine === S.loading) { adopt(d.things, 'sources'); refilter(); } } catch (_) {}
      try { const d = await get('rooms'); if (mine === S.loading) { adopt(d.things, 'rooms'); S.roomsError = d.rooms_error || null; refilter(); } }
      catch (_) { if (mine === S.loading) { S.roomsError = 'The directory of rooms can’t be read right now.'; refilter(); } }
    }
    function passes(t) {
      if (prefs.kinds[t.kind] === false) return false;
      if (t.kind === 'room' && prefs.subs[t.sub || 'listener'] === false) return false;
      return !S.words.length || matches(t._hay, S.words);
    }
    function refilter() {
      S.words = fold(S.find).split(/\s+/).filter(Boolean);
      const shown = S.all.filter(passes);
      S.on = shown.filter(t => t.here); S.off = shown.filter(t => !t.here);
      lastLevel = null; layout(); renderPanel();
      if (S.sheet && S.sheet.live) S.sheet.live();
    }

    // ── marks: one per thing, or one per gathering ──
    const countSize = n => n < 10 ? 20 : n < 100 ? 24 : 28;
    function describe(things) {
      const by = {}; for (const t of things) by[t.kind] = (by[t.kind] || 0) + 1;
      return KINDS.filter(k => by[k]).map(k => plural(by[k], KIND_ONE[k])).join(', ');
    }
    function layout() {
      if (!view) return;
      const level = Math.round(Math.log2(view.s) * 4);             // gather afresh only when the size has really changed
      if (level !== lastLevel) {
        lastLevel = level;
        const want = new Map();
        for (const c of gather(S.on, view.s, MERGE_PX)) want.set(c.id, c);
        for (const [id, r] of marks) if (!want.has(id)) { r.el.remove(); marks.delete(id); }
        for (const [id, c] of want) {
          let r = marks.get(id);
          if (r) { r.c = c; continue; }
          const one = c.things.length === 1 ? c.things[0] : null;
          const el = h('button', { type: 'button', class: 'gx-m has-l ' + (one ? 'gx-m--' + one.kind : 'gx-m--n'), 'data-id': id,
            title: one ? one.name + ' · ' + KIND_ONE[one.kind] + (one.place && one.place.name ? ' · ' + one.place.name : '') : plural(c.things.length, 'thing') + ' here: ' + describe(c.things) });
          const g = h('i', { class: 'gx-m__g', 'aria-hidden': 'true' }, one ? null : String(c.things.length));
          const l = one ? h('span', { class: 'gx-m__l' }, one.name) : null;
          el.append(g); if (l) el.append(l);
          el.append(h('span', { class: 'gx-sr' }, one ? ', ' + KIND_ONE[one.kind] : ' things: ' + describe(c.things)));
          if (!one) el.style.setProperty('--s', countSize(c.things.length) + 'px');
          el.addEventListener('click', () => tap(marks.get(id)));
          marksEl.append(el);
          marks.set(id, { id, el, l, lw: 0, c, one });
        }
      }
      position();
      view.poke();                                                 // the towns' names are set again round where the marks now are
    }
    // where each mark is now; a name is shown only where it runs into nothing
    let takenBoxes = [];
    function position() {
      if (!view) return;
      const W = view.W, H = view.H, used = [];
      // (while the sheet stands open — at the right, or along the foot of a narrow window — the map's
      //  marks stop at its edge: none is left under it or half under it, and no name runs into it)
      let block = null;
      if (S.sheet && sheet.offsetWidth) { const a = sheet.getBoundingClientRect(), b = stage.getBoundingClientRect(); block = [a.left - b.left - 16, a.top - b.top - 16, a.right - b.left, a.bottom - b.top]; used.push(block); }
      takenBoxes = [];
      const list = [...marks.values()];
      for (const r of list) {
        const q = view.toScreen(r.c.cx, r.c.cy); r.x = q[0]; r.y = q[1];
        r.on = r.x > -30 && r.x < W + 30 && r.y > -30 && r.y < H + 30 && !(block && r.x > block[0] && r.x < block[2] && r.y > block[1] && r.y < block[3]);
        r.el.style.visibility = r.on ? 'visible' : 'hidden';
        if (!r.on) continue;
        r.el.style.transform = 'translate(' + r.x.toFixed(1) + 'px,' + r.y.toFixed(1) + 'px)';
        const g = r.one ? 11 : countSize(r.c.things.length) / 2;
        const box = [r.x - g - 2, r.y - g - 2, r.x + g + 2, r.y + g + 2];
        used.push(box); takenBoxes.push(box);
        r.el.classList.toggle('is-sel', !!(S.sel && r.c.things.some(t => t.id === S.sel)));
      }
      used.push([0, H - 34, 210, H]);                                // (no name is set over the scale line in its corner)
      for (const r of list) {
        if (!r.on || !r.l) continue;
        if (!r.lw) r.lw = r.l.offsetWidth || (r.one.name.length * 8 + 10);
        const box = [r.x + 14, r.y - 10, r.x + 16 + r.lw, r.y + 10];        // (it starts just past its own mark)
        let free = box[2] < W - 4;
        if (free) for (const u of used) if (box[0] < u[2] && box[2] > u[0] && box[1] < u[3] && box[3] > u[1]) { free = false; break; }
        r.el.classList.toggle('has-l', free);
        if (free) { used.push(box); takenBoxes.push(box); }
      }
    }
    function tap(r) {
      if (!r) return;
      if (r.one) { select(r.one); openCard(r.one, null); return; }
      const c = r.c;
      if (c.spread < SAME_KM || view.s >= view.closest * 0.98) {        // nothing closer will part them
        openList(c.things, { title: plural(c.things.length, 'thing') + ' here', sub: describe(c.things) });
        return;
      }
      let x0 = 9, x1 = -9, y0 = 9, y1 = -9;
      for (const t of c.things) { x0 = Math.min(x0, t.x); x1 = Math.max(x1, t.x); y0 = Math.min(y0, t.y); y1 = Math.max(y1, t.y); }
      const span = Math.max(x1 - x0, y1 - y0, 1e-6);
      view.flyTo({ x: (x0 + x1) / 2, y: (y0 + y1) / 2, s: Math.max(view.s * 1.6, Math.min(view.W, view.H) * 0.42 / span) }, 520);
    }
    function select(t) { S.sel = t ? t.id : null; position(); }
    function goTo(t) {
      select(t);
      if (!view || !t.here) return;
      view.flyTo({ x: t.x, y: t.y, s: Math.max(view.s, view.fit * 3.2) }, 620);
    }

    // ── the sheet on the right: a list, or one thing ──
    function closeSheet() {
      if (!S.sheet) return false;
      S.sheet = null; sheet.classList.remove('on'); sheet.textContent = '';
      select(null); if (view) view.poke();
      return true;
    }
    function sheetFrame(kicker, back) {
      sheet.textContent = '';
      const head = h('div', { class: 'gx-sheet__head' },
        back ? h('button', { class: 'gx-link', type: 'button', onclick: back }, '‹ Back to the list') : h('span', { class: 'gx-kicker' }, kicker),
        h('button', { class: 'gx-x', type: 'button', 'aria-label': 'Close', title: 'Close', onclick: closeSheet }, '✕'));
      const body = h('div', { class: 'gx-sheet__body' });
      sheet.append(head, body); sheet.classList.add('on');
      // (in a narrow window the panel is a drawer: what was asked for from it takes its place)
      if (host.classList.contains('gx--panelopen')) { host.classList.remove('gx--panelopen'); drawer.setAttribute('aria-expanded', 'false'); drawer.textContent = 'Show and find'; }
      position();
      return body;
    }
    const placeLine = t => t.here ? (t.place.name || 'On the map') : (t.place && isFinite(t.place.lat) ? (t.place.name ? t.place.name + ' · not on this map' : 'Not on this map') : 'No place given');
    function openList(things, o) {
      o = o || {};
      const state = { things: things.slice(), q: '' };
      const back = () => open();
      const draw = () => {
        const body = sheetFrame('List', null);
        body.append(h('h2', { class: 'gx-h' }, o.title || plural(state.things.length, 'thing')));
        if (o.sub) body.append(h('p', { class: 'gx-sub' }, o.sub));
        const rows = h('div', { class: 'gx-rows' });
        const fill = () => {
          rows.textContent = '';
          const words = fold(state.q).split(/\s+/).filter(Boolean);
          const list = state.things.filter(t => !words.length || matches(t._hay, words));
          let kind = null, n = 0;
          for (const t of list) {
            if (n >= 300) { rows.append(h('p', { class: 'gx-sub' }, 'And ' + (list.length - n) + ' more. Narrow the list above to see them.')); break; }
            if (t.kind !== kind) { kind = t.kind; rows.append(h('div', { class: 'gx-rows__k' }, KIND_MANY[kind], h('b', null, String(list.filter(x => x.kind === kind).length)))); }
            rows.append(h('button', { class: 'gx-row', type: 'button', onclick: () => { goTo(t); openCard(t, back); } }, glyph(t.kind),
              h('span', { class: 'gx-row__n' }, t.name), h('span', { class: 'gx-row__s' }, (t.kind === 'room' ? (t.sub || 'listener') + ' · ' : '') + placeLine(t))));
            n++;
          }
          if (!list.length) rows.append(h('p', { class: 'gx-sub' }, 'Nothing here matches.'));
        };
        if (state.things.length > 10) {
          const box = h('input', { class: 'gx-find', type: 'search', placeholder: 'narrow this list', 'aria-label': 'Narrow this list', value: state.q });
          box.addEventListener('input', () => { state.q = box.value; fill(); });
          body.append(box);
        }
        body.append(rows); fill();
      };
      const open = () => { S.sheet = { kind: 'list', live: o.live ? () => { state.things = o.live(); if (S.sheet && S.sheet.kind === 'list') draw(); } : null }; select(null); draw(); };
      open();
    }
    function openCard(t, back) {
      const body = sheetFrame('One thing', back);
      S.sheet = { kind: 'card', live: null };
      body.append(h('p', { class: 'gx-kicker gx-kicker--kind' }, t.kind === 'room' ? (t.sub || 'listener') + ' · music room' : KIND_ONE[t.kind]));
      body.append(h('h2', { class: 'gx-h gx-h--big' }, t.name));
      body.append(h('p', { class: 'gx-where' }, glyph(t.kind), placeLine(t)));
      if (t.kind === 'room' && t.covers && t.covers.length) {
        const strip = h('div', { class: 'gx-covers' });
        for (const id of t.covers.slice(0, 4)) { const img = h('img', { src: '/api/gr/art/' + encodeURIComponent(id), alt: '', loading: 'lazy' }); img.addEventListener('error', () => img.remove()); strip.append(img); }
        body.append(strip);
      }
      if (t.blurb) body.append(h('p', { class: 'gx-blurb' }, t.blurb));
      if (t.kind === 'room') body.append(h('p', { class: 'gx-sub' }, t.count ? plural(t.count, 'record') : 'No records for sale'));
      if (t.tags.length) body.append(h('div', { class: 'gx-chips' }, t.tags.map(g => h('button', { class: 'gx-chip', type: 'button', title: 'Find things that say ' + g, onclick: () => { findBox.value = g; S.find = g; refilter(); } }, g))));
      const acts = h('div', { class: 'gx-acts' });
      if (t.kind === 'room') acts.append(h('button', { class: 'gx-btn gx-btn--go', type: 'button', onclick: () => { if (opts.openRoom) opts.openRoom(t.handle); } }, 'Open the room'));
      else {
        acts.append(h('button', { class: 'gx-btn gx-btn--go', type: 'button', onclick: e => openSite(t, e.currentTarget) }, 'Open the site ↗'));
        if (t.kind !== 'website') {
          const add = h('button', { class: 'gx-btn', type: 'button' }, t.added ? 'In your sources' : '+ Add to your sources');
          if (t.added) add.disabled = true; else add.addEventListener('click', () => addSource(t, add));
          acts.append(add);
        }
      }
      if (t.here) acts.append(h('button', { class: 'gx-btn', type: 'button', onclick: () => goTo(t) }, 'Show where it is'));
      if (opts.addToGrupa && (t.kind === 'room' ? t.handle : t.url))
        acts.append(h('button', { class: 'gx-btn', type: 'button', title: 'Add this to one or more of your grúpaí',
          onclick: e => opts.addToGrupa(t.kind === 'room' ? { kind: 'room', ref_key: t.handle, title: t.name, subtitle: (t.sub || 'listener') + ' · music room' }
                                                           : { url: t.url, title: t.name, subtitle: KIND_ONE[t.kind] || '' }, e.currentTarget) }, '＋ Grúpa'));
      body.append(acts);
      if (t.kind === 'website') body.append(h('p', { class: 'gx-sub' }, 'Websites turn up in your flow on their own.'));
      select(t);
    }
    function openSite(t, btn) {
      if (!t.url) return;
      fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: t.url }) })
        .then(r => { if (!r.ok) throw 0; }).catch(() => { btn.textContent = "It didn't open. Try again"; });
    }
    async function addSource(t, btn) {
      btn.disabled = true; btn.textContent = 'Adding…';
      try {
        const r = await fetch('/api/sources', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: t.name, url: t.url, kind: t.src_kind || 'magazine', feed_url: t.feed_url || '', description: t.blurb || '' }) });
        if (!r.ok) throw 0;
        t.added = true; btn.textContent = 'In your sources';
        if (opts.onSourcesChanged) opts.onSourcesChanged();
      } catch (e) { btn.disabled = false; btn.textContent = "It wasn't added. Try again"; }
    }

    // ── the panel on the left ──
    const sum = h('p', { class: 'gx-sum', 'aria-live': 'polite' });
    const warn = h('p', { class: 'gx-warn' });
    const offLine = h('button', { class: 'gx-link mx-off', type: 'button', onclick: () => openList(S.off, { title: plural(S.off.length, 'thing') + ' not on this map', sub: 'They gave no place, or a place beyond Ireland and Britain.', live: () => S.off }) });
    const secs = {};
    function section(key, title) {
      const body = h('div', { class: 'gx-sec__b' });
      const mark = h('i', { 'aria-hidden': 'true' }, prefs.shut[key] ? '+' : '−');
      const head = h('button', { class: 'gx-sec__h', type: 'button', 'aria-expanded': String(!prefs.shut[key]) }, h('span', null, title), mark);
      const sec = h('section', { class: 'gx-sec' + (prefs.shut[key] ? ' is-shut' : '') }, head, body);
      head.addEventListener('click', () => {
        const shut = !sec.classList.contains('is-shut');
        sec.classList.toggle('is-shut', shut); prefs.shut[key] = shut; mark.textContent = shut ? '+' : '−'; head.setAttribute('aria-expanded', String(!shut)); savePrefs(prefs);
      });
      secs[key] = body; panel.append(sec);
      return body;
    }
    panel.append(sum, offLine, bar, warn);
    const showB = section('show', 'Show'), findB = section('find', 'Find'), lookB = section('look', 'Look');
    const findBox = h('input', { class: 'gx-find', type: 'search', placeholder: 'name, place or tag', 'aria-label': 'Find by name, place or tag', autocomplete: 'off', spellcheck: 'false' });
    const findSay = h('div', { class: 'gx-findsay' });
    findBox.addEventListener('input', () => { clearTimeout(findT); findT = setTimeout(() => { S.find = findBox.value; refilter(); }, 130); });
    findBox.addEventListener('keydown', e => {
      if (e.key === 'Escape' && findBox.value) { e.stopPropagation(); findBox.value = ''; S.find = ''; refilter(); }
      if (e.key === 'Enter') { clearTimeout(findT); S.find = findBox.value; refilter(); listShown(); }
    });
    findB.append(findBox, findSay);
    function listShown() { openList(S.on.concat(S.off), { title: plural(S.on.length + S.off.length, 'thing'), sub: S.words.length ? 'Everything that matches.' : 'Everything showing.', live: () => S.on.concat(S.off) }); }
    function check(label, on, n, kind, click, small) {
      return h('button', { class: 'gx-check' + (small ? ' gx-check--sub' : ''), type: 'button', role: 'switch', 'aria-checked': String(on), onclick: click },
        h('i', { class: 'gx-check__box', 'aria-hidden': 'true' }), kind ? glyph(kind) : null, h('span', null, label), h('b', null, n == null ? '' : String(n)));
    }
    function renderPanel() {
      const on = S.on.length, off = S.off.length;
      sum.textContent = S.loading && !S.all.length ? 'Reading what there is…' : plural(on, 'thing') + ' on the map' + (S.rough ? ' · a rough outline for now' : '');
      offLine.textContent = off ? off + ' more not on this map' : '';
      offLine.style.display = off ? '' : 'none';
      warn.textContent = S.roomsError || ''; warn.style.display = S.roomsError ? '' : 'none';
      showB.textContent = '';
      const counted = k => S.all.filter(t => t.kind === k && (!S.words.length || matches(t._hay, S.words))).length;
      for (const k of KINDS) {
        showB.append(check(KIND_MANY[k], prefs.kinds[k] !== false, counted(k), k, () => { prefs.kinds[k] = prefs.kinds[k] === false; savePrefs(prefs); refilter(); }));
        if (k === 'room' && prefs.kinds.room !== false) {
          const subs = {}; for (const t of S.all) if (t.kind === 'room') subs[t.sub || 'listener'] = (subs[t.sub || 'listener'] || 0) + 1;
          for (const s of Object.keys(SUB_MANY)) if (subs[s])
            showB.append(check(SUB_MANY[s], prefs.subs[s] !== false, subs[s], null, () => { prefs.subs[s] = prefs.subs[s] === false; savePrefs(prefs); refilter(); }, true));
        }
      }
      findSay.textContent = '';
      if (S.words.length) findSay.append(h('span', null, plural(on + off, 'thing') + ' match' + (on + off === 1 ? 'es' : '')), h('button', { class: 'gx-link', type: 'button', onclick: listShown }, 'List them'));
      lookRest.textContent = '';
      lookRest.append(
        h('div', { class: 'gx-label' }, 'Which way is up'),
        h('div', { class: 'gx-btns' },
          h('button', { class: 'gx-btn' + (prefs.up === 1 ? ' on' : ''), type: 'button', 'aria-pressed': String(prefs.up === 1), onclick: () => turn(1) }, 'North'),
          h('button', { class: 'gx-btn' + (prefs.up === -1 ? ' on' : ''), type: 'button', 'aria-pressed': String(prefs.up === -1), onclick: () => turn(-1) }, 'South')),
        h('div', { class: 'gx-label' }, 'On the map'),
        check('Town names', prefs.towns, null, null, () => { prefs.towns = !prefs.towns; saveLook(prefs); applyLook(); renderPanel(); }),
        check('Rivers', prefs.rivers, null, null, () => { prefs.rivers = !prefs.rivers; saveLook(prefs); applyLook(); renderPanel(); }));
    }
    function applyLook() { if (view) view.look({ towns: prefs.towns, rivers: prefs.rivers }); }
    function turn(v) { prefs.up = v === -1 ? -1 : 1; saveLook(prefs); if (view) view.turn(prefs.up); upKey.textContent = prefs.up === 1 ? 'North is up' : 'South is up'; renderPanel(); }

    // ── the skin: a small picture of each, and the listener's own with its colours beneath ──
    // (built once and kept: the rest of the panel is drawn afresh whenever what it counts changes, and a colour
    //  being typed must not lose its place)
    const skinNow = () => skinFor(prefs.skin, prefs.own);
    const tiles = {};
    const skinsEl = h('div', { class: 'mx-skins', role: 'radiogroup', 'aria-label': 'The map’s skin' });
    const ownEl = h('div', { class: 'mx-own' });
    const lookRest = h('div');
    for (const sk of SKINS.concat([{ id: 'own', name: 'Your own', say: 'Colours you choose yourself' }])) {
      const cv = h('canvas', { class: 'mx-skin__c', 'aria-hidden': 'true' });
      const el = h('button', { class: 'mx-skin', type: 'button', role: 'radio', 'aria-checked': 'false', title: sk.say, onclick: () => setSkin(sk.id) }, cv, h('span', { class: 'mx-skin__n' }, sk.name));
      tiles[sk.id] = { el, cv }; skinsEl.append(el);
    }
    lookB.append(h('div', { class: 'gx-label' }, 'Skin'), skinsEl, ownEl, lookRest);
    // "your own" begins as the skin that was on, in colours that stay put
    function ownStart() {
      const now = skinNow(), c = tonesFor(now, pageOf(host)).rgb;
      return { sea: rgbHex(c.sea), land: rgbHex(c.land), line: rgbHex(c.line), text: rgbHex(c.text), fill: FILLS.indexOf(now.fill) >= 0 ? now.fill : 'flat' };
    }
    function paintSkins() {
      const page = pageOf(host), D = view && view.data;
      for (const id in tiles) {
        thumb(tiles[id].cv, D, tonesFor(id === 'own' ? skinFor('own', prefs.own || ownStart()) : skinFor(id), page));
        tiles[id].el.setAttribute('aria-checked', String(skinNow().id === id));
      }
    }
    function wear() { if (view) view.tones(); paintSkins(); }
    function setSkin(id) {
      if (id === 'own' && !prefs.own) prefs.own = ownStart();
      prefs.skin = id; saveLook(prefs); wear(); renderOwn();
    }
    const OWN_PARTS = [['sea', 'Sea'], ['land', 'Land'], ['line', 'Lines'], ['text', 'Writing']];
    const FILL_NAME = { flat: 'Plain', dots: 'Dotted', lines: 'Ruled' };
    function renderOwn() {
      const on = skinNow().id === 'own';
      ownEl.textContent = ''; ownEl.style.display = on ? '' : 'none';
      if (!on) return;
      const say = h('p', { class: 'gx-sub mx-own__say', role: 'status' });
      const judge = () => {
        const c = tonesFor(skinNow(), pageOf(host)).rgb;
        say.textContent = contrast(c.text, c.land) < 3 ? 'The writing is hard to read on that land.'
          : contrast(c.land, c.sea) < 1.12 && contrast(c.line, c.sea) < 1.6 && prefs.own.fill === 'flat' ? 'The land is hard to tell from the sea.' : '';
        say.style.display = say.textContent ? '' : 'none';
      };
      for (const part of OWN_PARTS) {
        const k = part[0], label = part[1];
        const sw = h('input', { type: 'color', class: 'mx-own__sw', value: prefs.own[k], title: label + ': pick a colour', 'aria-label': label + ': pick a colour' });
        const hex = h('input', { type: 'text', class: 'mx-own__hex', value: prefs.own[k], maxlength: '7', spellcheck: 'false', autocomplete: 'off', title: label + ': the colour’s code', 'aria-label': label + ': the colour’s code' });
        const set = (v, from) => {
          const c = hexRgb(v); if (!c) return;
          prefs.own[k] = rgbHex(c);
          if (from !== sw) sw.value = prefs.own[k];
          if (from !== hex) hex.value = prefs.own[k];
          saveLook(prefs); wear(); judge();
        };
        sw.addEventListener('input', () => set(sw.value, sw));
        hex.addEventListener('input', () => set(hex.value, hex));
        hex.addEventListener('blur', () => { hex.value = prefs.own[k]; });
        hex.addEventListener('keydown', e => { if (e.key === 'Enter') hex.blur(); e.stopPropagation(); });
        ownEl.append(h('div', { class: 'mx-own__row' }, h('span', null, label), sw, hex));
      }
      ownEl.append(h('div', { class: 'gx-label' }, 'The land is'),
        h('div', { class: 'gx-btns' }, FILLS.map(f => h('button', { class: 'gx-btn' + (prefs.own.fill === f ? ' on' : ''), type: 'button', 'aria-pressed': String(prefs.own.fill === f),
          onclick: () => { prefs.own.fill = f; saveLook(prefs); wear(); renderOwn(); } }, FILL_NAME[f]))), say);
      judge();
    }

    // keys on the map itself
    const key = (label, title, fn) => h('button', { class: 'gx-btn', type: 'button', title, 'aria-label': title, onclick: fn }, label);
    const upKey = key(prefs.up === 1 ? 'North is up' : 'South is up', 'Turn the map the other way up', () => turn(-prefs.up));
    bar.append(key('+', 'Go closer', () => { view.zoomAt(1.6); settle(); }), key('−', 'Step back', () => { view.zoomAt(1 / 1.6); settle(); }),
      key('All of it', 'Show the whole map', () => view.whole(480)), upKey);

    function settle() {
      layout();
      clearTimeout(saveT); saveT = setTimeout(() => { if (view) { prefs.view = view.view; savePrefs(prefs); } }, 400);
    }
    function place() {
      if (opts.top) { const y = opts.top(); if (y > 0) host.style.top = Math.round(y) + 'px'; }
      if (view) { view.measure(); lastLevel = null; view.poke(); layout(); }
    }
    const onResize = () => { if (visible) place(); };
    function boot() {
      if (booted) return; booted = true;
      setNote('Drawing the map…');
      view = createView(stage, { up: prefs.up, view: prefs.view, onDraw: position, onSettle: settle, taken: () => takenBoxes, skin: skinNow, page: host,
        onTap: () => { if (S.sheet && S.sheet.kind === 'card') closeSheet(); },
        onData: d => { setNote(d ? '' : 'The map’s outline could not be read.'); S.rough = !!(d && d.rough); renderPanel(); paintSkins(); } });
      applyLook();
      renderPanel(); renderOwn(); paintSkins();
      load();
      addEventListener('resize', onResize);
      addEventListener('snt-box', onResize);
      addEventListener('mr-theme-change', wear);                   // the app's look was changed: the skins that follow it follow
    }
    return {
      show() { visible = true; boot(); wear(); place(); },
      hide() { visible = false; },
      escape() { if (closeSheet()) return true; if (S.find) { findBox.value = ''; S.find = ''; refilter(); return true; } return false; },
      refresh: load,
      frame() { if (view) { view.frame(); layout(); } },
      skin: setSkin,
      state: () => ({ skin: skinNow().id, all: S.all.length, on: S.on.length, off: S.off.length, marks: [...marks.values()].map(r => ({ id: r.id, n: r.c.things.length, x: Math.round(r.x), y: Math.round(r.y), on: r.on, label: r.el.classList.contains('has-l') })),
                      view: view && view.view, kmPx: view && view.kmPx, up: prefs.up, sheet: S.sheet && S.sheet.kind, rough: S.rough }),
      view: () => view,
    };
  }

  // ═══════════════ 5. the small map on My Public Room: where is your room? ═══════════════
  function picker(host, opts) {
    opts = opts || {};
    const prefs = loadPrefs();
    host.classList.add('gx', 'gx--pick', 'mx'); host.textContent = '';
    const stage = h('div', { class: 'gx-stage', tabindex: '0', role: 'application', 'aria-label': 'A map of Ireland and Britain. Drag to move it, then click the spot.' });
    const pin = h('i', { class: 'gx-pin', 'aria-hidden': 'true' });
    const note = h('div', { class: 'gx-note on' }, 'Drawing the map…');
    const bar = h('div', { class: 'gx-pickbar' });
    stage.append(pin, note, bar); host.append(stage);
    const ok = p => p && isFinite(p.lat) && isFinite(p.lon);
    let spot = ok(opts.value) ? { lat: +opts.value.lat, lon: +opts.value.lon } : null, noteT = 0;
    const say = (text, ms) => { clearTimeout(noteT); note.textContent = text || ''; note.classList.toggle('on', !!text); if (text && ms) noteT = setTimeout(() => say(''), ms); };
    function draw() {
      if (!spot || !inBox(spot.lat, spot.lon)) { pin.style.display = 'none'; return; }
      const q = project(spot.lat, spot.lon), xy = view.toScreen(q[0], q[1]);
      pin.style.display = 'block';
      pin.style.transform = 'translate3d(' + xy[0].toFixed(1) + 'px,' + xy[1].toFixed(1) + 'px,0)';
    }
    const view = createView(stage, { up: prefs.up, wheelNeedsPress: true, onDraw: draw, skin: () => skinFor(prefs.skin, prefs.own), page: host, scale: false,
      onData: d => say(d ? (spot && !inBox(spot.lat, spot.lon) ? 'The place you set before is beyond this map. Click a spot to move it here.' : '') : 'The map could not be drawn, so a spot can’t be picked here.'),
      onTap: (lat, lon, x, y) => {
        if (!inBox(lat, lon)) return say('Click a spot inside the map.', 2200);
        if (view.data && !view.data.rough && !view.isLand(x, y)) return say('That is in the sea. Click on the land.', 2200);
        spot = { lat: +lat.toFixed(4), lon: +lon.toFixed(4) }; say(''); view.poke();
        if (opts.onPick) opts.onPick(spot.lat, spot.lon);
      } });
    const btn = (label, title, fn) => h('button', { class: 'gx-btn', type: 'button', title, 'aria-label': title, onclick: fn }, label);
    const upBtn = btn(prefs.up === 1 ? 'North is up' : 'South is up', 'Turn the map the other way up', () => { prefs.up = -prefs.up; saveLook(prefs); view.turn(prefs.up); upBtn.textContent = prefs.up === 1 ? 'North is up' : 'South is up'; });
    bar.append(btn('+', 'Go closer', () => view.zoomAt(1.7)), btn('−', 'Step back', () => view.zoomAt(1 / 1.7)), btn('All of it', 'Show the whole map', () => view.whole(400)), upBtn);
    if (spot && inBox(spot.lat, spot.lon)) { const q = project(spot.lat, spot.lon); view.flyTo({ x: q[0], y: q[1], s: view.fit * 2.6 }, 0); }
    const onTheme = () => view.tones();
    addEventListener('mr-theme-change', onTheme);
    return {
      set(place) { spot = ok(place) ? { lat: +place.lat, lon: +place.lon } : null; if (spot && inBox(spot.lat, spot.lon)) { const q = project(spot.lat, spot.lon); view.flyTo({ x: q[0], y: q[1] }, 400); } view.poke(); },
      get() { return spot; },
      frame() { view.frame(); },
      view: () => view,
      destroy() { removeEventListener('mr-theme-change', onTheme); view.dispose(); host.textContent = ''; },
    };
  }

  root.ExploreMap = { mount, picker, pure };
})(typeof window !== 'undefined' ? window : globalThis);
