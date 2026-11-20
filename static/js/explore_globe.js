/* explore_globe.js — the Globe in Explore (and the small globe on /myroom).

   A third way to look at Explore. Everything there is to visit — public music
   rooms, and the publications, stations and websites of the source catalogue —
   on a globe. A thing that says where it is sits on the globe at that spot. A
   thing that doesn't is UNIVERSAL: it belongs to no one place, and goes round
   the globe on a ring.

   What the globe deliberately is (David, 2026-11-14: "a decolonised globe"):
     · no borders, no countries, no country names. Land and water only, read
       from a small land/water picture (static/data/globe_land.png)
     · land is an EQUAL-AREA lattice of dots (a Fibonacci spiral): every dot
       stands for the same amount of ground, wherever on the earth it is
     · no way up. It tumbles freely and never snaps back to north-at-the-top.
       It first opens facing where the things are, with south at the top
     · no first meridian: the grid lines carry no numbers and none is marked
     · the only place names are the ones owners typed themselves
   and what keeps it from clutter:
     · things near each other gather into one mark with a count; moving closer
       pulls them apart (a hierarchy of clusters worked out on the sphere, so
       it behaves the same at the poles as anywhere)
     · things at one spot, or nearer each other than the closest view can
       separate, open as a list in the sheet on the right
     · the panel on the left narrows by kind, by place / no place, by words
       and by tag — and the universal ring gathers into counted marks too

   window.ExploreGlobe = { mount(host, opts), picker(host, opts) }
   Part 1 is plain maths with no page in it: test_globe.py runs it under node.
   three.js (vendored, static/vendor/three) loads the first time a globe opens.
*/
(function (root) {
  'use strict';

  // ═══════════════ 1. plain maths: no page, no three.js ═══════════════
  const DEG = Math.PI / 180;
  const GOLDEN = Math.PI * (3 - Math.sqrt(5));        // the golden angle
  const KINDS = ['room', 'publication', 'station', 'website'];
  const FOV = 40;                                      // the view's vertical angle, degrees
  const MIN_DIST = 1.1, MAX_DIST = 7;                  // the eye's distance from the centre (the surface is at 1)
  const MERGE_PX = 56;                                 // marks nearer than this on screen are one mark
  const RADII = Array.from({ length: 10 }, (_, k) => 0.003 * Math.pow(2, k));   // each level's reach, radians (19 km … a quarter of the earth)
  const RING_R = 1.5;                                  // the universal ring's radius
  const OPEN_UP = [0, -1, 0];                          // which pole is drawn upward the first time: south

  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = v => { const n = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / n, v[1] / n, v[2] / n]; };

  // a place on the earth ⇄ a direction from its centre (y = the north pole; east is to the
  // right of someone looking at the globe from outside with north up — nothing is mirrored)
  function vecOf(lat, lon) { const p = lat * DEG, l = lon * DEG, c = Math.cos(p); return [c * Math.cos(l), Math.sin(p), -c * Math.sin(l)]; }
  function latLonOf(v) { const n = norm(v); return { lat: Math.asin(clamp(n[1], -1, 1)) / DEG, lon: Math.atan2(-n[2], n[0]) / DEG }; }

  // turns, as [x, y, z, w]
  const qNorm = q => { const n = Math.hypot(q[0], q[1], q[2], q[3]) || 1; return [q[0] / n, q[1] / n, q[2] / n, q[3] / n]; };
  const qConj = q => [-q[0], -q[1], -q[2], q[3]];
  function qMul(a, b) {                                // b first, then a
    return [a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
            a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
            a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
            a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
  }
  function qAxis(axis, angle) { const s = Math.sin(angle / 2); return [axis[0] * s, axis[1] * s, axis[2] * s, Math.cos(angle / 2)]; }
  function qRot(q, v) {
    const x = q[0], y = q[1], z = q[2], w = q[3];
    const tx = 2 * (y * v[2] - z * v[1]), ty = 2 * (z * v[0] - x * v[2]), tz = 2 * (x * v[1] - y * v[0]);
    return [v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx)];
  }
  function qMat(q) {                                   // the same turn as nine numbers, row by row
    const x = q[0], y = q[1], z = q[2], w = q[3];
    return [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
            2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
            2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)];
  }
  function qFromMat(m) {
    const tr = m[0] + m[4] + m[8]; let x, y, z, w;
    if (tr > 0) { const s = Math.sqrt(tr + 1) * 2; w = s / 4; x = (m[7] - m[5]) / s; y = (m[2] - m[6]) / s; z = (m[3] - m[1]) / s; }
    else if (m[0] > m[4] && m[0] > m[8]) { const s = Math.sqrt(1 + m[0] - m[4] - m[8]) * 2; w = (m[7] - m[5]) / s; x = s / 4; y = (m[1] + m[3]) / s; z = (m[2] + m[6]) / s; }
    else if (m[4] > m[8]) { const s = Math.sqrt(1 + m[4] - m[0] - m[8]) * 2; w = (m[2] - m[6]) / s; x = (m[1] + m[3]) / s; y = s / 4; z = (m[5] + m[7]) / s; }
    else { const s = Math.sqrt(1 + m[8] - m[0] - m[4]) * 2; w = (m[3] - m[1]) / s; x = (m[2] + m[6]) / s; y = (m[5] + m[7]) / s; z = s / 4; }
    return qNorm([x, y, z, w]);
  }
  // the turn that brings direction v to face the viewer (+z), with `up` drawn upward on screen
  function qFace(v, up) {
    const f = norm(v);
    let u = [up[0] - dot(up, f) * f[0], up[1] - dot(up, f) * f[1], up[2] - dot(up, f) * f[2]];
    if (Math.hypot(u[0], u[1], u[2]) < 1e-6) { const alt = Math.abs(f[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1]; u = [alt[0] - dot(alt, f) * f[0], alt[1] - dot(alt, f) * f[1], alt[2] - dot(alt, f) * f[2]]; }
    u = norm(u); const r = cross(u, f);
    return qFromMat([r[0], r[1], r[2], u[0], u[1], u[2], f[0], f[1], f[2]]);
  }
  // the shortest turn taking direction a onto direction b
  function qBetween(a, b) {
    const d = dot(a, b);
    if (d < -0.999999) { let ax = cross([1, 0, 0], a); if (Math.hypot(ax[0], ax[1], ax[2]) < 1e-6) ax = cross([0, 1, 0], a); ax = norm(ax); return [ax[0], ax[1], ax[2], 0]; }
    const c = cross(a, b); return qNorm([c[0], c[1], c[2], 1 + d]);
  }
  function qSlerp(a, b, t) {
    let c = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3], bb = b;
    if (c < 0) { c = -c; bb = [-b[0], -b[1], -b[2], -b[3]]; }
    if (c > 0.9995) return qNorm([a[0] + (bb[0] - a[0]) * t, a[1] + (bb[1] - a[1]) * t, a[2] + (bb[2] - a[2]) * t, a[3] + (bb[3] - a[3]) * t]);
    const th = Math.acos(c), s = Math.sin(th), wa = Math.sin((1 - t) * th) / s, wb = Math.sin(t * th) / s;
    return [a[0] * wa + bb[0] * wb, a[1] * wa + bb[1] * wb, a[2] * wa + bb[2] * wb, a[3] * wa + bb[3] * wb];
  }
  function mul3(a, b) {
    const o = new Array(9);
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) o[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c];
    return o;
  }

  // the middle of a set of directions (weighted), or null when they cancel out
  function middle(vs) {
    let x = 0, y = 0, z = 0;
    for (const v of vs) { x += v[0]; y += v[1]; z += v[2]; }
    const m = Math.hypot(x, y, z);
    return vs.length && m > 0.05 * vs.length ? [x / m, y / m, z / m] : null;
  }

  // The dots. An n-dot Fibonacci lattice covers the sphere evenly: each dot stands for the same
  // area. Dots i in [from, to) that fall on land are written into `out` (x, y, z); returns how
  // many numbers were written. mask = { bits, W, H }: one bit per cell of a plain lat/lon grid.
  function latticeLand(n, from, to, mask, out) {
    const bits = mask.bits, W = mask.W, H = mask.H; let c = 0;
    for (let i = from; i < to; i++) {
      const y = 1 - (2 * i + 1) / n, r = Math.sqrt(Math.max(0, 1 - y * y)), t = i * GOLDEN, x = r * Math.cos(t), z = r * Math.sin(t);
      let px = ((Math.atan2(-z, x) / Math.PI + 1) * 0.5 * W) | 0; if (px >= W) px = 0;
      let py = ((0.5 - Math.asin(y) / Math.PI) * H) | 0; if (py >= H) py = H - 1;
      if (bits[py * W + px]) { out[c++] = x; out[c++] = y; out[c++] = z; }
    }
    return c;
  }

  // Gathering. One pass: everything within `theta` (radians, along the surface) of a seed joins
  // it, heaviest seeds first. A 3D grid finds the neighbours, so there is no flat map in it and
  // nothing goes wrong at the poles or the date line.
  function mergeLevel(nodes, theta, k) {
    const chord = 2 * Math.sin(Math.min(theta, Math.PI) / 2), c2 = chord * chord, inv = 1 / chord;
    const dims = Math.floor(2 * inv) + 3, cell = new Int32Array(nodes.length * 3), grid = new Map();
    for (let i = 0; i < nodes.length; i++) {
      const v = nodes[i].v, ix = Math.floor((v[0] + 1) * inv), iy = Math.floor((v[1] + 1) * inv), iz = Math.floor((v[2] + 1) * inv);
      cell[i * 3] = ix; cell[i * 3 + 1] = iy; cell[i * 3 + 2] = iz;
      const key = ix + dims * (iy + dims * iz), b = grid.get(key);
      if (b) b.push(i); else grid.set(key, [i]);
    }
    const order = nodes.map((_, i) => i).sort((a, b) => nodes[b].n - nodes[a].n || a - b);
    const used = new Uint8Array(nodes.length), out = [];
    for (const i of order) {
      if (used[i]) continue;
      used[i] = 1;
      const a = nodes[i], av = a.v, ix = cell[i * 3], iy = cell[i * 3 + 1], iz = cell[i * 3 + 2];
      let kids = null, sx = av[0] * a.n, sy = av[1] * a.n, sz = av[2] * a.n, n = a.n;
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
        const X = ix + dx, Y = iy + dy, Z = iz + dz;
        if (X < 0 || Y < 0 || Z < 0) continue;
        const b = grid.get(X + dims * (Y + dims * Z));
        if (!b) continue;
        for (const j of b) {
          if (used[j]) continue;
          const o = nodes[j], ov = o.v, ex = ov[0] - av[0], ey = ov[1] - av[1], ez = ov[2] - av[2];
          if (ex * ex + ey * ey + ez * ez > c2) continue;
          used[j] = 1; (kids || (kids = [a])).push(o);
          sx += ov[0] * o.n; sy += ov[1] * o.n; sz += ov[2] * o.n; n += o.n;
        }
      }
      if (!kids) { out.push(a); continue; }
      const m = Math.hypot(sx, sy, sz);
      const c = { id: 'c' + k + '.' + a.id, v: m > 1e-9 ? [sx / m, sy / m, sz / m] : av.slice(), n, kids, lvl: k, up: null, thing: null };
      for (const kid of kids) kid.up = c;
      out.push(c);
    }
    return out;
  }
  // leaves: [{ id, v, thing }] → levels[k] = the marks to draw when the view calls for level k
  function buildHierarchy(leaves, radii) {
    let cur = leaves.map(l => ({ id: l.id, v: l.v, n: 1, kids: null, lvl: -1, up: null, thing: l.thing }));
    const first = cur, levels = [];
    for (let k = 0; k < radii.length; k++) { cur = mergeLevel(cur, radii[k], k); levels.push(cur); }
    return { levels, leaves: first };
  }
  function thingsOf(node) {
    if (node._t) return node._t;
    const out = [], stack = [node];
    while (stack.length) { const x = stack.pop(); if (x.kids) for (let i = x.kids.length - 1; i >= 0; i--) stack.push(x.kids[i]); else out.push(x.thing); }
    return (node._t = out);
  }
  // how far apart (radians) two marks are when they are MERGE_PX apart in the middle of the view
  const viewTheta = (d, f) => MERGE_PX * (d - 1) / f;
  function levelFor(theta, radii) { for (let k = 0; k < radii.length; k++) if (radii[k] >= theta) return k; return radii.length - 1; }
  // how close the eye must come for a gathered mark to come apart; null = it can't (it opens as a list)
  function splitDist(node, f, radii) {
    if (!node.kids || node.lvl < 1) return null;
    const d = 1 + 0.85 * radii[node.lvl - 1] * f / MERGE_PX;
    return d < MIN_DIST ? null : Math.min(d, MAX_DIST);
  }
  // how close for one thing to stand on its own — or, when it shares its spot with others that no
  // view can part it from, for that spot to stand clear of everything else. MAX_DIST = it already does.
  function aloneDist(leaf, f, radii) {
    let n = leaf;
    while (n.up && splitDist(n.up, f, radii) == null) n = n.up;
    return n.up ? splitDist(n.up, f, radii) : MAX_DIST;
  }

  // The ring. Universal things in a fixed order — by kind, then A to Z. When there are more than
  // the ring has room for (K marks), each kind's A–Z is cut into even runs, one counted mark each.
  function fold(s) { return String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function ringSlots(things, K) {
    const by = {};
    for (const t of things) (by[t.kind] || (by[t.kind] = [])).push(t);
    const kinds = KINDS.filter(k => by[k]);
    for (const k of Object.keys(by)) if (!kinds.includes(k)) kinds.push(k);
    const key = t => (t._fn != null ? t._fn : fold(t.name));
    for (const k of kinds) by[k].sort((a, b) => { const x = key(a), y = key(b); return x < y ? -1 : x > y ? 1 : (a.id < b.id ? -1 : a.id > b.id ? 1 : 0); });
    const slots = [], total = things.length;
    if (total <= K) { for (const k of kinds) for (const t of by[k]) slots.push({ kind: k, things: [t] }); return slots; }
    const share = kinds.map(k => Math.max(1, Math.floor(K * by[k].length / total)));
    let spare = K - share.reduce((a, b) => a + b, 0);
    while (spare > 0) {                                // spare marks go where a mark stands for the most things
      let best = -1, load = 0;
      kinds.forEach((k, i) => { const l = by[k].length / share[i]; if (share[i] < by[k].length && l > load) { load = l; best = i; } });
      if (best < 0) break; share[best]++; spare--;
    }
    while (spare < 0) {
      let best = -1, load = Infinity;
      kinds.forEach((k, i) => { const l = by[k].length / share[i]; if (share[i] > 1 && l < load) { load = l; best = i; } });
      if (best < 0) break; share[best]--; spare++;
    }
    kinds.forEach((k, i) => {
      const list = by[k], m = Math.min(share[i], list.length);
      for (let s = 0; s < m; s++) slots.push({ kind: k, things: list.slice(Math.floor(s * list.length / m), Math.floor((s + 1) * list.length / m)) });
    });
    return slots;
  }

  // Finding: every word typed must be somewhere in the thing's name, place, kind, tags or blurb.
  function hayOf(t) {
    return fold([t.name, t.place && t.place.name, t.kind === 'room' ? 'music room ' + (t.sub || '') : t.kind,
                 (t.tags || []).join(' '), t.blurb, t.handle].filter(Boolean).join(' · '));
  }
  function matches(hay, words) { for (const w of words) if (hay.indexOf(w) < 0) return false; return true; }

  // is a point out past the surface hidden behind the globe, seen from (0, 0, d)?
  function behindGlobe(x, y, z, d) {
    const dx = x, dy = y, dz = z - d, a = dx * dx + dy * dy + dz * dz, b = 2 * d * dz, c = d * d - 1, disc = b * b - 4 * a * c;
    if (disc <= 0) return false;
    const t = (-b - Math.sqrt(disc)) / (2 * a);
    return t > 0 && t < 1;
  }

  const pure = { DEG, KINDS, FOV, MIN_DIST, MAX_DIST, MERGE_PX, RADII, RING_R, vecOf, latLonOf, qMul, qAxis, qRot, qConj, qMat, qFace,
                 qBetween, qSlerp, middle, latticeLand, mergeLevel, buildHierarchy, thingsOf, viewTheta, levelFor, splitDist,
                 aloneDist, ringSlots, fold, hayOf, matches, behindGlobe };
  if (typeof module !== 'undefined' && module.exports) { module.exports = pure; return; }

  // ═══════════════ 2. the drawn globe (three.js) ═══════════════
  let threeP = null, maskP = null;
  const loadThree = () => threeP || (threeP = import('/static/vendor/three/three.module.js'));
  function loadMask() {
    return maskP || (maskP = new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => {
        try {
          const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
          const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(img, 0, 0);
          const d = g.getImageData(0, 0, c.width, c.height).data, bits = new Uint8Array(c.width * c.height);
          for (let i = 0, j = 0; i < bits.length; i++, j += 4) bits[i] = d[j] > 127 ? 1 : 0;
          res({ bits, W: c.width, H: c.height });
        } catch (e) { rej(e); }
      };
      img.onerror = () => rej(new Error('the land picture did not load'));
      img.src = '/static/data/globe_land.png';
    }));
  }

  // The page's own tones, read where they are painted. (MRTones.read() looks at <html>; Explore
  // leaves an older dark --bg there while the theme puts the real tokens on <body>, so the tones
  // are taken from inside the globe's own element and MRTones is only the fallback.)
  function readTones(el) {
    const probe = document.createElement('i');
    probe.style.cssText = 'position:absolute;width:0;height:0;visibility:hidden;pointer-events:none';
    el.appendChild(probe);
    const rgb = s => { const m = /rgba?\(([^)]+)\)/.exec(s || ''); if (!m) return null; const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return p.length >= 3 && p.slice(0, 3).every(x => x === x) ? [p[0] / 255, p[1] / 255, p[2] / 255] : null; };
    const tok = name => { probe.style.color = 'var(' + name + ', rgb(1, 2, 3))'; const c = rgb(getComputedStyle(probe).color); return c && !(Math.round(c[0] * 255) === 1 && Math.round(c[1] * 255) === 2 && Math.round(c[2] * 255) === 3) ? c : null; };
    const hex = s => (/^#[0-9a-f]{6}$/i.test(s || '') ? [parseInt(s.slice(1, 3), 16) / 255, parseInt(s.slice(3, 5), 16) / 255, parseInt(s.slice(5, 7), 16) / 255] : null);
    const base = root.MRTones ? root.MRTones.read() : {};
    const ink = tok('--text') || tok('--ink') || rgb(getComputedStyle(el).color) || hex(base.text) || [0, 0, 0];
    const bg = tok('--bg') || rgb(getComputedStyle(document.body).backgroundColor) || hex(base.bg) || [1, 1, 1];
    const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    const out = { ink, bg, muted: tok('--muted') || mix(ink, bg, 0.45), red: tok('--red') || hex(base.red) || ink };
    probe.remove();
    return out;
  }

  const DOT_VS = `
    uniform float uSize, uFocal, uMin, uMax, uRatio;
    varying float vFace;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vFace = dot(normalize(mat3(modelViewMatrix) * position), normalize(-mv.xyz));
      gl_Position = projectionMatrix * mv;
      gl_PointSize = clamp(uSize * uFocal / max(0.0001, -mv.z), uMin, uMax) * uRatio;
    }`;
  const DOT_FS = `
    uniform vec3 uColor; uniform float uAlpha, uBack, uRound;
    varying float vFace;
    void main() {
      float a = 1.0;
      if (uRound > 0.5) a = 1.0 - smoothstep(0.36, 0.5, length(gl_PointCoord - 0.5));
      float f = vFace >= 0.0 ? mix(0.4, 1.0, smoothstep(0.0, 0.45, vFace)) : uBack * smoothstep(0.0, 0.3, -vFace);
      a *= uAlpha * f;
      if (a < 0.004) discard;
      gl_FragColor = vec4(uColor, a);
    }`;
  const LINE_VS = `
    varying float vFace;
    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vFace = dot(normalize(mat3(modelViewMatrix) * normalize(position)), normalize(-mv.xyz));
      gl_Position = projectionMatrix * mv;
    }`;
  const LINE_FS = `
    uniform vec3 uColor; uniform float uAlpha, uBack;
    varying float vFace;
    void main() { gl_FragColor = vec4(uColor, uAlpha * (vFace >= 0.0 ? mix(0.3, 1.0, smoothstep(0.0, 0.4, vFace)) : uBack)); }`;
  const FLAT_VS = `void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
  const FLAT_FS = `uniform vec3 uColor; uniform float uAlpha; void main() { gl_FragColor = vec4(uColor, uAlpha); }`;

  async function createCore(stage, o) {
    o = o || {};
    const [THREE, mask] = await Promise.all([loadThree(), loadMask()]);
    const reduce = !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const canvas = document.createElement('canvas');
    canvas.className = 'gx-canvas'; canvas.setAttribute('aria-hidden', 'true');
    stage.insertBefore(canvas, stage.firstChild);
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'low-power' }); }
    catch (e) { canvas.remove(); const err = new Error('no-webgl'); err.code = 'no-webgl'; throw err; }
    const ratio = Math.min(root.devicePixelRatio || 1, o.lowPower ? 1.25 : 2);
    renderer.setPixelRatio(ratio);
    const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(FOV, 1, 0.02, 40), globe = new THREE.Group();
    scene.add(globe);
    const V3 = a => new THREE.Vector3(a[0], a[1], a[2]);
    let T = readTones(stage);

    // state
    let q = o.q ? qNorm(o.q) : [0, 0, 0, 1], d = clamp(o.d || 3.6, MIN_DIST, MAX_DIST), shift = 0, shiftTo = 0;
    let W = 0, H = 0, f = 900, dirty = true, running = false, raf = 0, last = 0, dead = false;
    let fly = null, vel = null, spin = false, lastTouch = 0, density = o.density || 'normal', dotAlpha = 0.9;
    const subs = {};
    const on = (ev, fn) => { (subs[ev] || (subs[ev] = [])).push(fn); };
    const emit = (ev, a, b) => { for (const fn of subs[ev] || []) fn(a, b); };

    // the globe's body, drawn into depth only: it hides the part of the ring that passes behind
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.994, 72, 48), new THREE.MeshBasicMaterial({ colorWrite: false }));
    body.renderOrder = -5; scene.add(body);

    // the dots: a few lattices, each four times finer than the last; the view picks one
    const sizes = o.lowPower ? [4096, 16384, 65536, 262144, 1048576] : [4096, 16384, 65536, 262144, 1048576, 4194304];
    const LV = sizes.map(n => ({ n, state: 0, pts: null, mat: null, a: 0 }));
    const dotMat = n => new THREE.ShaderMaterial({
      uniforms: { uColor: { value: V3(T.ink) }, uAlpha: { value: 0 }, uBack: { value: 0.14 }, uRound: { value: 1 }, uSize: { value: 0.42 * Math.sqrt(4 * Math.PI / n) },
                  uFocal: { value: f }, uMin: { value: 1.4 }, uMax: { value: 5.2 }, uRatio: { value: ratio } },
      vertexShader: DOT_VS, fragmentShader: DOT_FS, transparent: true, depthTest: false, depthWrite: false });
    let round = o.shape !== 'square';
    function build(i) {
      const L = LV[i];
      if (L.state) return;
      L.state = 1;
      const n = L.n, chunks = []; let from = 0, total = 0;
      const slice = () => {
        if (dead) return;
        const to = Math.min(n, from + 200000), buf = new Float32Array((to - from) * 3), c = latticeLand(n, from, to, mask, buf);
        chunks.push(buf.subarray(0, c)); total += c; from = to;
        if (from < n) { setTimeout(slice, 0); return; }
        const pos = new Float32Array(total); let at = 0;
        for (const ch of chunks) { pos.set(ch, at); at += ch.length; }
        const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        L.mat = dotMat(n); L.pts = new THREE.Points(g, L.mat);
        L.pts.frustumCulled = false; L.pts.renderOrder = 1; L.pts.visible = false; globe.add(L.pts);
        L.count = total / 3; L.state = 2; dirty = true;
      };
      slice();
    }
    function wantLevel() {
      // the finest lattice whose dots still sit about 6 pixels apart in the middle of the view;
      // "sparse" draws the lattice one step coarser than that (a quarter of the dots), "fine" one step finer (four times)
      const bound = 4 * Math.PI * Math.pow(f / ((d - 1) * 6.2), 2), top = LV.length - 2;
      let i = 1;
      for (let k = 1; k <= top; k++) if (LV[k].n <= bound) i = k;
      return density === 'sparse' ? i - 1 : density === 'fine' ? i + 1 : i;
    }
    function stepDots(dt) {
      const want = wantLevel(); build(want);
      let show = want;
      if (LV[want].state !== 2) {
        show = -1;
        for (let k = want - 1; k >= 0 && show < 0; k--) if (LV[k].state === 2) show = k;
        for (let k = want + 1; k < LV.length && show < 0; k++) if (LV[k].state === 2) show = k;
      }
      let moving = false; const rate = reduce ? 1 : Math.min(1, dt / 170);
      LV.forEach((L, k) => {
        if (L.state !== 2) return;
        const to = k === show ? 1 : 0;
        if (L.a !== to) { L.a += (to - L.a) * rate; if (Math.abs(to - L.a) < 0.02) L.a = to; moving = true; }
        L.pts.visible = L.a > 0.01;
        const u = L.mat.uniforms; u.uAlpha.value = L.a * dotAlpha; u.uFocal.value = f; u.uRound.value = round ? 1 : 0;
        u.uBack.value = 0.14 * clamp((d - 1.5) / 1.2, 0, 1);         // close in, the far side is only noise
      });
      return moving;
    }

    // the grid: meridians and parallels every 30°, unnumbered, none marked as first
    const lineMat = (a, back) => new THREE.ShaderMaterial({ uniforms: { uColor: { value: V3(T.ink) }, uAlpha: { value: a }, uBack: { value: back } },
      vertexShader: LINE_VS, fragmentShader: LINE_FS, transparent: true, depthTest: false, depthWrite: false });
    const flatMat = (a, depth) => new THREE.ShaderMaterial({ uniforms: { uColor: { value: V3(T.ink) }, uAlpha: { value: a } },
      vertexShader: FLAT_VS, fragmentShader: FLAT_FS, transparent: true, depthTest: !!depth, depthWrite: false });
    const geo = arr => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(arr), 3)); return g; };
    const mer = [], par = [];
    for (let lon = 0; lon < 360; lon += 30) for (let lat = -90; lat < 90; lat += 2) mer.push(...vecOf(lat, lon), ...vecOf(lat + 2, lon));
    for (let lat = -60; lat <= 60; lat += 30) for (let lon = 0; lon < 360; lon += 2) par.push(...vecOf(lat, lon), ...vecOf(lat, lon + 2));
    const merLines = new THREE.LineSegments(geo(mer), lineMat(0.2, 0.28)), parLines = new THREE.LineSegments(geo(par), lineMat(0.2, 0.28));
    for (const l of [merLines, parLines]) { l.frustumCulled = false; l.renderOrder = 2; l.scale.setScalar(1.0006); globe.add(l); }
    merLines.visible = o.meridians !== false; parLines.visible = o.parallels !== false;

    // the globe's edge: a hairline circle, so the water has a shape
    const edge = [];
    for (let a = 0; a < 360; a += 2) edge.push(Math.cos(a * DEG), Math.sin(a * DEG), 0, Math.cos((a + 2) * DEG), Math.sin((a + 2) * DEG), 0);
    const limb = new THREE.LineSegments(geo(edge), flatMat(0.42, false));
    limb.frustumCulled = false; limb.renderOrder = 3; scene.add(limb);

    // a ring round the globe (the universal things ride it). Drawn twice: plainly where it is in
    // front, and very faintly where it passes behind, like the dots on the far side.
    let ring = null;
    function setRing(qr, radius, show) {
      if (!ring) {
        const pts = [];
        for (let a = 0; a < 360; a += 1.5) pts.push(Math.cos(a * DEG), 0, Math.sin(a * DEG), Math.cos((a + 1.5) * DEG), 0, Math.sin((a + 1.5) * DEG));
        const g = geo(pts), grp = new THREE.Group();
        const front = new THREE.LineSegments(g, flatMat(0.5, true)), ghost = new THREE.LineSegments(g, flatMat(0.1, false));
        for (const l of [front, ghost]) { l.frustumCulled = false; l.renderOrder = 4; grp.add(l); }
        globe.add(grp); ring = { grp, front, ghost };
      }
      ring.grp.quaternion.set(qr[0], qr[1], qr[2], qr[3]); ring.grp.scale.setScalar(radius); ring.grp.visible = !!show; dirty = true;
    }

    function setTones() {
      T = readTones(stage);
      renderer.setClearColor(new THREE.Color().setRGB(T.bg[0], T.bg[1], T.bg[2], THREE.SRGBColorSpace), 1);
      const ink = V3(T.ink);
      for (const L of LV) if (L.mat) L.mat.uniforms.uColor.value = ink;
      for (const m of [merLines.material, parLines.material, limb.material]) m.uniforms.uColor.value = ink;
      if (ring) for (const l of [ring.front, ring.ghost]) l.material.uniforms.uColor.value = ink;
      dotAlpha = 0.92; dirty = true;
    }

    function measure() {
      const r = stage.getBoundingClientRect(), w = Math.round(r.width), h = Math.round(r.height);
      if (!w || !h) return false;
      if (w !== W || h !== H) { W = w; H = h; renderer.setSize(W, H, false); camera.aspect = W / H; f = (H / 2) / Math.tan(FOV * DEG / 2); dirty = true; emit('resize'); }
      return true;
    }
    function render() {
      globe.quaternion.set(q[0], q[1], q[2], q[3]);
      camera.position.set(0, 0, d);
      if (Math.abs(shift) > 0.5) camera.setViewOffset(W, H, shift, 0, W, H); else { if (camera.view) camera.clearViewOffset(); camera.updateProjectionMatrix(); }
      const rho = Math.sqrt(1 - 1 / (d * d)); limb.scale.set(rho, rho, 1); limb.position.z = 1 / d;
      renderer.render(scene, camera);
    }

    // one step of everything that moves. Also callable by hand: a pane that isn't showing gets no
    // animation frames, and the tests step it themselves.
    function step(now) {
      if (dead) return;
      now = now || performance.now();
      const dt = clamp(now - (last || now - 16), 0, 64); last = now;
      if (!measure()) return;
      let moved = false;
      if (fly) {
        if (!fly.t0) fly.t0 = now;
        const u = clamp((now - fly.t0) / fly.ms, 0, 1), e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
        q = qNorm(qSlerp(fly.a.q, fly.b.q, e));
        d = 1 + Math.exp(Math.log(fly.a.d - 1) + (Math.log(fly.b.d - 1) - Math.log(fly.a.d - 1)) * e);
        if (u >= 1) { q = fly.b.q; d = fly.b.d; fly = null; emit('settle'); }
        moved = true;
      } else if (vel) {
        rotatePx(vel[0] * dt, vel[1] * dt);
        const k = Math.pow(0.93, dt / 16); vel[0] *= k; vel[1] *= k;
        if (Math.hypot(vel[0], vel[1]) < 0.004) { vel = null; emit('settle'); }
        moved = true;
      } else if (spin && !reduce && !ptrs.size && now - lastTouch > 2500) {
        q = qNorm(qMul(qAxis([0, 1, 0], 0.035 * dt / 1000 * Math.PI), q)); moved = true;       // about whatever is upright on screen
      }
      if (Math.abs(shiftTo - shift) > 0.5) { shift += (shiftTo - shift) * (reduce ? 1 : Math.min(1, dt / 120)); moved = true; } else if (shift !== shiftTo) { shift = shiftTo; moved = true; }
      if (stepDots(dt)) moved = true;
      const extra = { moved: moved || dirty, dt, now };
      emit('before', extra);
      if (extra.moved || dirty) { dirty = false; render(); emit('frame', extra); }
    }
    function loop(now) { raf = 0; if (!running || dead) return; raf = requestAnimationFrame(loop); if (!document.hidden) step(now); }
    function start() { if (running || dead) return; running = true; last = 0; dirty = true; raf = requestAnimationFrame(loop); }
    function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }

    // moving it
    function still() { fly = null; vel = null; lastTouch = performance.now(); }
    function rotatePx(dx, dy) {
      const k = Math.min((d - 1) / f, 0.012);          // a drag moves the ground under the pointer by the same distance
      q = qNorm(qMul(qMul(qAxis([0, 1, 0], dx * k), qAxis([1, 0, 0], dy * k)), q)); dirty = true;
    }
    function rollBy(a) { q = qNorm(qMul(qAxis([0, 0, 1], a), q)); dirty = true; }
    function pickWorld(x, y) {
      const rx = (x - (W / 2 - shift)) / f, ry = -(y - H / 2) / f, a = rx * rx + ry * ry + 1, b = -2 * d, c = d * d - 1, disc = b * b - 4 * a * c;
      if (disc < 0) return null;
      const t = (-b - Math.sqrt(disc)) / (2 * a);
      return [rx * t, ry * t, d - t];
    }
    function pick(x, y) { const w = pickWorld(x, y); return w ? norm(qRot(qConj(q), w)) : null; }
    function zoomBy(factor, x, y) {
      const nd = clamp(1 + (d - 1) * factor, MIN_DIST, MAX_DIST);
      if (Math.abs(nd - d) < 1e-6) return;
      const held = x == null ? null : pick(x, y);
      d = nd;
      if (held) { const hit = pickWorld(x, y); if (hit) q = qNorm(qMul(qBetween(norm(qRot(q, held)), norm(hit)), q)); }   // what was under the pointer stays under it
      dirty = true;
    }
    function flyTo(t, ms) {
      const to = { q: t.q ? qNorm(t.q) : (t.v ? qNorm(qMul(qBetween(norm(qRot(q, t.v)), [0, 0, 1]), q)) : q), d: clamp(t.d || d, MIN_DIST, MAX_DIST) };
      still();
      if (reduce || ms === 0) { q = to.q; d = to.d; dirty = true; emit('settle'); return; }
      fly = { a: { q, d }, b: to, t0: 0, ms: ms || 760 }; dirty = true;
    }
    const facing = () => norm(qRot(qConj(q), [0, 0, 1]));       // the spot on the globe that looks straight at the viewer

    // pointer, wheel, keys
    const ptrs = new Map();
    let dragging = false, noClickUntil = 0, pinch = null, track = [], engaged = !o.wheelNeedsPress;
    const local = e => { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    stage.addEventListener('pointerdown', e => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (e.target.closest && e.target.closest('.gx-nodrag')) return;
      ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY });
      still(); engaged = true; track = [];
      if (ptrs.size === 2) { const p = [...ptrs.values()]; pinch = { dist: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y), ang: Math.atan2(p[1].y - p[0].y, p[1].x - p[0].x) }; dragging = true; }
    });
    stage.addEventListener('pointermove', e => {
      const p = ptrs.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      if (ptrs.size === 1) {
        if (!dragging) {
          if (Math.hypot(e.clientX - p.x0, e.clientY - p.y0) < 5) return;
          dragging = true; stage.classList.add('is-dragging');
          try { stage.setPointerCapture(e.pointerId); } catch (_) {}
        }
        if (e.shiftKey) {                                  // roll it about the line of sight
          const r = stage.getBoundingClientRect(), cx = r.left + W / 2 - shift, cy = r.top + H / 2;
          rollBy(-(Math.atan2(e.clientY - cy, e.clientX - cx) - Math.atan2(p.y - cy, p.x - cx)));
        } else {
          rotatePx(dx, dy);
          const now = performance.now(); track.push([now, dx, dy]); while (track.length && now - track[0][0] > 90) track.shift();
        }
        p.x = e.clientX; p.y = e.clientY;
      } else if (ptrs.size === 2 && pinch) {
        p.x = e.clientX; p.y = e.clientY;
        const a = [...ptrs.values()], dist = Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y), ang = Math.atan2(a[1].y - a[0].y, a[1].x - a[0].x);
        if (pinch.dist > 0 && dist > 0) zoomBy(pinch.dist / dist);
        rollBy(-(ang - pinch.ang)); pinch.dist = dist; pinch.ang = ang;
      }
      lastTouch = performance.now();
    });
    const lift = e => {
      const p = ptrs.get(e.pointerId);
      if (!p) return;
      ptrs.delete(e.pointerId);
      if (ptrs.size < 2) pinch = null;
      if (ptrs.size) return;
      stage.classList.remove('is-dragging');
      if (dragging) {
        dragging = false; noClickUntil = performance.now() + 320;
        if (!reduce && track.length > 1 && e.type === 'pointerup') {
          const span = Math.max(16, track[track.length - 1][0] - track[0][0]); let sx = 0, sy = 0;
          for (const t of track) { sx += t[1]; sy += t[2]; }
          if (Math.hypot(sx, sy) / span > 0.25) vel = [sx / span, sy / span];
        }
        if (!vel) emit('settle');
      } else if (e.type === 'pointerup' && !(e.target.closest && e.target.closest('button, a, input'))) {
        const xy = local(e); emit('tap', pick(xy[0], xy[1]), e);
      }
      lastTouch = performance.now();
    };
    stage.addEventListener('pointerup', lift);
    stage.addEventListener('pointercancel', lift);
    stage.addEventListener('click', e => { if (performance.now() < noClickUntil) { e.stopPropagation(); e.preventDefault(); } }, true);
    stage.addEventListener('pointerleave', () => { if (o.wheelNeedsPress && !ptrs.size) engaged = false; });
    stage.addEventListener('wheel', e => {
      if (!engaged) return;                                // (the small globe on a scrolling page: only once it has been pressed)
      e.preventDefault(); still();
      const xy = local(e);
      zoomBy(Math.exp(clamp(e.deltaY, -240, 240) * (e.ctrlKey ? 0.012 : e.deltaMode === 1 ? 0.05 : 0.0016)), xy[0], xy[1]);
      emit('settle');
    }, { passive: false });
    stage.addEventListener('dblclick', e => {
      if (e.target.closest && e.target.closest('button, a, input')) return;
      const xy = local(e), v = pick(xy[0], xy[1]);
      if (v) flyTo({ v, d: 1 + (d - 1) * 0.5 }, 520);
    });
    stage.addEventListener('keydown', e => {
      if (e.target !== stage) return;
      const k = e.key, s = 46;
      if (k === 'ArrowLeft') rotatePx(s, 0); else if (k === 'ArrowRight') rotatePx(-s, 0);
      else if (k === 'ArrowUp') rotatePx(0, s); else if (k === 'ArrowDown') rotatePx(0, -s);
      else if (k === '+' || k === '=') zoomBy(0.8, W / 2 - shift, H / 2); else if (k === '-' || k === '_') zoomBy(1.25, W / 2 - shift, H / 2);
      else return;
      e.preventDefault(); e.stopPropagation(); still(); emit('settle');
    });

    const ro = root.ResizeObserver ? new ResizeObserver(() => { dirty = true; if (!running) measure(); }) : null;
    if (ro) ro.observe(stage);
    setTones(); measure();

    return {
      stage, canvas, reduce, on, step, start, stop, flyTo, zoomBy, rotatePx, pick, facing, setRing, setTones,
      get q() { return q; }, get d() { return d; }, get f() { return f; }, get W() { return W; }, get H() { return H; }, get shift() { return shift; },
      get busy() { return !!fly || !!vel || dragging; },
      set(nq, nd) { if (nq) q = qNorm(nq); if (nd) d = clamp(nd, MIN_DIST, MAX_DIST); dirty = true; },
      poke() { dirty = true; },
      setShift(px) { shiftTo = px || 0; dirty = true; },
      mat: () => qMat(q),
      // a direction on the globe → where it is on screen. face: 1 at the middle, 0 at the edge, below 0 on the far side
      toScreen(M, v, out) {
        const wx = M[0] * v[0] + M[1] * v[1] + M[2] * v[2], wy = M[3] * v[0] + M[4] * v[1] + M[5] * v[2], wz = M[6] * v[0] + M[7] * v[1] + M[8] * v[2], zc = d - wz;
        out.x = W / 2 - shift + f * wx / zc; out.y = H / 2 - f * wy / zc; out.wz = wz; out.face = (d * wz - 1) / (d - 1);
        return out;
      },
      setGraticule(m, p) { merLines.visible = !!m; parLines.visible = !!p; dirty = true; },
      setDensity(v) { density = v; dirty = true; },
      setShape(v) { round = v !== 'square'; dirty = true; },
      setSpin(v) { spin = !!v; lastTouch = 0; dirty = true; },
      face(v, up, ms) { flyTo({ q: qFace(v, up) }, ms); },
      viewAll() { return clamp(RING_R * f / (0.45 * Math.min(W, H)), 2.4, MAX_DIST); },
      dots: () => LV.map(L => ({ n: L.n, state: L.state, a: +L.a.toFixed(2), land: L.count || 0 })),
      dispose() { dead = true; stop(); if (ro) ro.disconnect(); try { renderer.dispose(); } catch (_) {} canvas.remove(); },
    };
  }

  // ═══════════════ 3. small page helpers ═══════════════
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
  const PREFS_KEY = 'mr_globe';
  function loadPrefs() {
    let p = {};
    try { p = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') || {}; } catch (_) {}
    return { kinds: p.kinds || {}, subs: p.subs || {}, where: p.where || {}, mer: p.mer !== false, par: p.par !== false,
             dens: ['sparse', 'normal', 'fine'].includes(p.dens) ? p.dens : 'normal', shape: p.shape === 'square' ? 'square' : 'round', spin: !!p.spin,
             q: Array.isArray(p.q) && p.q.length === 4 && p.q.every(x => typeof x === 'number' && x === x) ? p.q : null,
             d: typeof p.d === 'number' && p.d === p.d ? p.d : null, shut: p.shut || { look: true }, hinted: !!p.hinted };
  }
  function savePrefs(p) { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch (_) {} }

  // ═══════════════ 4. the Globe view ═══════════════
  function mount(host, opts) {
    opts = opts || {};
    const prefs = loadPrefs();
    host.classList.add('gx'); host.textContent = '';
    const panel = h('aside', { class: 'gx-panel', 'aria-label': 'What the globe shows' });
    const stage = h('div', { class: 'gx-stage', tabindex: '0', role: 'application', 'aria-label': 'The globe. Drag to turn it; scroll to move closer or step back.' });
    const marksEl = h('div', { class: 'gx-marks' });
    const tip = h('div', { class: 'gx-tip', role: 'tooltip' });
    const note = h('div', { class: 'gx-note', role: 'status' });
    const keys = h('div', { class: 'gx-keys' }, 'Drag to turn · Shift-drag to roll · Scroll to move closer · Click a number to open it up');
    const ringTag = h('button', { class: 'gx-ringtag', type: 'button', title: 'List everything that has no place' });
    const sheet = h('aside', { class: 'gx-sheet', 'aria-label': 'Things here' });
    const drawer = h('button', { class: 'gx-drawer', type: 'button', 'aria-expanded': 'false', onclick: () => { const open = host.classList.toggle('gx--panelopen'); drawer.setAttribute('aria-expanded', String(open)); } }, 'Show and find');
    marksEl.append(ringTag);
    stage.append(marksEl, tip, note, keys);
    host.append(panel, stage, drawer, sheet);
    if (prefs.hinted) keys.classList.add('is-off');

    const S = { all: [], shown: [], H: { levels: [], leaves: [] }, leaf: new Map(), uni: [], slots: [], K: -1, find: '', words: [], tags: new Set(),
                sel: null, selIds: new Set(), roomsError: null, loadedAt: 0, loading: 0, level: 0, sheet: null, home: null, homeQ: null, ringQ: [0, 0, 0, 1], phase: 0, hold: false };
    let core = null, visible = false, dead = false, frameNo = 0, blocks = [], blocksAt = 0, saveT = 0, findT = 0;
    const marks = new Map();

    function setNote(text) { note.textContent = text || ''; note.classList.toggle('on', !!text); }

    // ── the data ──
    function adopt(list, part) {
      const keep = part ? S.all.filter(t => (part === 'rooms') !== (t.kind === 'room')) : [];
      const fresh = (list || []).filter(t => t && t.id && KINDS.includes(t.kind)).map(t => {
        const p = t.place && isFinite(t.place.lat) && isFinite(t.place.lon) ? { name: String(t.place.name || '').trim(), lat: +t.place.lat, lon: +t.place.lon } : null;
        const o = Object.assign({}, t, { place: p, v: p ? vecOf(p.lat, p.lon) : null, tags: Array.isArray(t.tags) ? t.tags.map(String) : [] });
        o._fn = fold(o.name); o._hay = hayOf(o);
        return o;
      });
      S.all = keep.concat(fresh).sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      const placed = S.all.filter(t => t.v);
      S.home = middle(placed.map(t => t.v));
      // with nothing placed there is no "where the things are": open on the date line, the seam flat maps cut along
      S.homeQ = qFace(S.home || vecOf(0, 180), OPEN_UP);
      // the ring's plane is set against that first view: seen a little from above, a little askew
      const tilt = 40 * DEG, roll = -11 * DEG, n = [-Math.sin(roll) * Math.cos(tilt), Math.cos(roll) * Math.cos(tilt), Math.sin(tilt)];
      S.ringQ = qNorm(qMul(qConj(S.homeQ), qBetween([0, 1, 0], n)));
      S.ringM = qMat(S.ringQ);
      refilter();
      if (core && !prefs.q && !S.touched) core.set(S.homeQ, core.viewAll());
    }
    async function load() {
      if (S.loading) return;
      S.loading = 2; S.roomsError = null; renderPanel();
      const get = async part => {
        try { const r = await fetch((opts.thingsUrl || '/api/globe/things') + '?part=' + part); if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }
        catch (e) { return { things: null, failed: true }; }
      };
      // the catalogue is on this laptop and answers at once; the rooms come from the rooms server and may take a moment
      get('sources').then(d => { if (dead) return; S.loading--; if (d.things) adopt(d.things, 'sources'); else { S.failed = true; renderPanel(); } });
      get('rooms').then(d => { if (dead) return; S.loading--; S.roomsError = d.failed ? "the list of rooms didn't load" : (d.rooms_error || null); if (d.things) adopt(d.things, 'rooms'); else renderPanel(); });
      S.loadedAt = Date.now();
    }

    // ── narrowing ──
    function passes(t, skip) {
      if (skip !== 'kind') { if (prefs.kinds[t.kind] === false) return false; if (t.kind === 'room' && prefs.subs[t.sub || 'listener'] === false) return false; }
      if (skip !== 'where' && prefs.where[t.v ? 'placed' : 'universal'] === false) return false;
      if (skip !== 'find' && S.words.length && !matches(t._hay, S.words)) return false;
      if (skip !== 'tags' && S.tags.size) { for (const g of S.tags) if (!t.tags.includes(g)) return false; }
      return true;
    }
    function refilter() {
      S.words = fold(S.find).split(/\s+/).filter(Boolean);
      S.shown = S.all.filter(t => passes(t));
      const placed = S.shown.filter(t => t.v);
      S.H = buildHierarchy(placed.map(t => ({ id: t.id, v: t.v, thing: t })), RADII);
      S.leaf = new Map(S.H.leaves.map(l => [l.id, l]));
      S.uni = S.shown.filter(t => !t.v);
      S.K = -1;
      clearMarks(); reselect(); renderPanel();
      if (S.sheet && S.sheet.live) S.sheet.live();
      if (core) { core.setRing(S.ringQ, RING_R, S.uni.length > 0); core.poke(); if (!visible) return; }
    }
    function reselect() {
      S.selIds = new Set();
      if (!S.sel) return;
      let n = S.leaf.get(S.sel);
      while (n) { S.selIds.add(n.id); n = n.up; }
    }
    function select(t) { S.sel = t ? t.id : null; reselect(); if (core) core.poke(); }

    // ── the marks: buttons laid over the drawing, one per thing or gathering in view ──
    function clearMarks() { for (const r of marks.values()) r.el.remove(); marks.clear(); hideTip(); }
    const countSize = n => Math.round(clamp(15 + 4.6 * Math.log2(n), 18, 40));
    function sameName(things) {                            // a gathering wears a place name only when every thing in it gave that same name
      const a = things[0].place && fold(things[0].place.name);
      if (!a) return '';
      for (let i = 1; i < things.length; i++) if (!things[i].place || fold(things[i].place.name) !== a) return '';
      return things[0].place.name;
    }
    function placeNames(things) {
      const by = {};
      for (const t of things) if (t.place && t.place.name) { const k = fold(t.place.name), e = by[k] || (by[k] = { name: t.place.name, n: 0 }); e.n++; }
      return Object.values(by).sort((a, b) => b.n - a.n || (fold(a.name) < fold(b.name) ? -1 : 1)).map(e => e.name);
    }
    const someNames = (names, max) => names.slice(0, max).join(' · ') + (names.length > max ? ' · and ' + (names.length - max) + ' more' : '');
    function describe(things) {
      const by = {};
      for (const t of things) by[t.kind] = (by[t.kind] || 0) + 1;
      return KINDS.filter(k => by[k]).map(k => plural(by[k], KIND_ONE[k])).join(', ');
    }
    function recFor(c, fresh) {
      let r = marks.get(c.id);
      if (r) return r;
      const things = c.nd ? thingsOf(c.nd) : c.slot.things, one = things.length === 1 ? things[0] : null;
      const el = h('button', { type: 'button', class: 'gx-m has-l ' + (one ? 'gx-m--' + one.kind : 'gx-m--n') + (c.sat ? ' gx-m--sat' : ''), 'data-id': c.id });
      const g = h('i', { class: 'gx-m__g', 'aria-hidden': 'true' }, one ? null : String(things.length));
      const text = one ? one.name : (c.nd ? sameName(things) : '');
      const l = text ? h('span', { class: 'gx-m__l' + (one ? '' : ' gx-m__l--place') }, text) : null;
      const say = one ? KIND_ONE[one.kind] + (one.place ? (one.place.name ? ', ' + one.place.name : '') : ', universal')
                      : plural(things.length, 'thing') + ': ' + describe(things) + '. ' + things.slice(0, 3).map(t => t.name).join(', ');
      el.append(g); if (l) el.append(l); el.append(h('span', { class: 'gx-sr' }, (one ? '' : ' ') + say));
      if (!one) el.style.setProperty('--s', countSize(things.length) + 'px');
      el.style.visibility = 'hidden';
      marksEl.append(el);
      r = { id: c.id, el, l, lw: 0, things, one, nd: c.nd || null, slot: c.slot || null, x: null, y: null, op: null, on: false, labelOn: true, sel: false, seen: 0, g: one ? 11 : countSize(things.length) / 2 };
      marks.set(c.id, r); fresh.push(r);
      return r;
    }
    function scanBlocks() {
      // Whatever floats over the globe — the deck, the corner buttons, an open drawer — is found by asking the
      // page what is on top at a grid of points. Marks under those things are not drawn (nobody could press
      // them), and the panel and the sheet stop short of whatever rests along the bottom.
      const hr = host.getBoundingClientRect(), sr = stage.getBoundingClientRect(), pr = panel.getBoundingClientRect();
      if (hr.width < 10 || hr.height < 10) return;
      const seen = new Set(), list = [];
      for (let y = hr.top + 6; y < Math.min(hr.bottom, innerHeight); y += 40) for (let x = hr.left + 6; x < Math.min(hr.right, innerWidth); x += 40) {
        const el = document.elementFromPoint(x, y);
        if (!el || host.contains(el)) continue;
        let top = null;
        for (let n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) if (getComputedStyle(n).position === 'fixed') top = n;
        if (!top || seen.has(top) || top.contains(host)) continue;
        seen.add(top);
        const r = top.getBoundingClientRect();
        if (r.width > innerWidth * 0.9 && r.height > innerHeight * 0.9) continue;      // a whole-page cover (an open room) is not something to dodge
        list.push(r);
      }
      let pb = 0, sb = 0, nb = 0;
      for (const r of list) {
        if (r.top < hr.top + hr.height * 0.4 || r.height > hr.height * 0.6) continue;      // only things resting along the bottom
        if (r.left < pr.right - 4) pb = Math.max(pb, hr.bottom - r.top + 10);
        if (r.right > hr.right - 348) sb = Math.max(sb, hr.bottom - r.top + 10);
        if (r.width > 120) nb = Math.max(nb, hr.bottom - r.top + 10);                      // (a wide thing: the deck, not a corner button)
      }
      const narrow = hr.width <= 860;
      panel.style.bottom = (narrow ? 0 : pb) + 'px'; sheet.style.bottom = (narrow ? 0 : sb) + 'px';
      // in a narrow window the drawer and the sheet run to the bottom, under the deck: their last rows get room to scroll clear of it
      host.style.setProperty('--gx-clear', (narrow ? nb : 0) + 'px');
      blocks = list.map(r => [r.left - sr.left - 8, r.top - sr.top - 8, r.right - sr.left + 8, r.bottom - sr.top + 8]);
      if (sheet.classList.contains('on')) { const r = sheet.getBoundingClientRect(); blocks.push([r.left - sr.left - 6, r.top - sr.top, r.right - sr.left, r.bottom - sr.top]); }
      blocksAt = performance.now();
    }
    const blocked = (x, y) => { for (const b of blocks) if (x > b[0] && x < b[2] && y > b[1] && y < b[3]) return true; return false; };

    const P = { x: 0, y: 0, wz: 0, face: 0 };
    const RING_STEPS = [6, 8, 12, 16, 20, 24, 28, 32, 36];    // how many marks the ring has room for, by how big it is drawn
    function updateMarks() {
      if (!core || !core.W) return;
      frameNo++;
      if (performance.now() - blocksAt > 700) scanBlocks();
      const W = core.W, Hh = core.H, M = core.mat(), d = core.d, f = core.f, cx = W / 2 - core.shift, cy = Hh / 2;
      const cand = [];
      // on the globe: the level the view calls for — and a coarser one if that would still be a crowd
      let k = levelFor(viewTheta(d, f), RADII);
      for (;;) {
        cand.length = 0;
        for (const nd of S.H.levels[k] || []) {
          core.toScreen(M, nd.v, P);
          if (P.face <= 0.02 || P.x < 6 || P.x > W - 6 || P.y < 6 || P.y > Hh - 6) continue;      // a mark half off the edge would show a cut-off name
          cand.push({ id: nd.id, nd, x: P.x, y: P.y, face: P.face, near: P.wz, n: nd.n, sat: false });
        }
        if (cand.length <= 170 || k >= RADII.length - 1) break;
        k++;
      }
      S.level = k;
      // on the ring
      let tag = null;
      if (S.uni.length) {
        const room = RING_STEPS.filter(s => s <= 2 * Math.PI * RING_R * f / d / 78).pop() || RING_STEPS[0];
        if (room !== S.K) {
          S.K = room;
          S.slots = ringSlots(S.uni, room);
          S.slots.forEach((s, i) => { s.a0 = 2 * Math.PI * i / S.slots.length; s.id = 'u:' + s.kind + ':' + s.things[0].id + ':' + s.things.length; });
        }
        const Mr = mul3(M, S.ringM);
        const at = a => { const lx = RING_R * Math.cos(a), lz = RING_R * Math.sin(a); return [Mr[0] * lx + Mr[2] * lz, Mr[3] * lx + Mr[5] * lz, Mr[6] * lx + Mr[8] * lz]; };
        for (const s of S.slots) {
          const w = at(s.a0 + S.phase), zc = d - w[2];
          if (zc < 0.06 || behindGlobe(w[0], w[1], w[2], d)) continue;
          const x = cx + f * w[0] / zc, y = cy - f * w[1] / zc;
          if (x < 6 || x > W - 6 || y < 6 || y > Hh - 6) continue;
          cand.push({ id: s.id, slot: s, x, y, face: 1, near: w[2], n: s.things.length, sat: true });
        }
        // the ring's name sits where the ring reaches furthest right, clear of the globe
        let bx = -Infinity; const disc = f / Math.sqrt(d * d - 1) + 6, tagW = ringTag.offsetWidth || 120;
        for (let i = 0; i < 60; i++) {
          const w = at(i * Math.PI / 30), zc = d - w[2];
          if (zc < 0.06 || behindGlobe(w[0], w[1], w[2], d)) continue;
          const x = cx + f * w[0] / zc, y = cy - f * w[1] / zc;
          if (x > bx && x > 4 && x < W - tagW - 18 && y > 14 && y < Hh - 14 && Math.hypot(x - cx, y - cy) > disc && !blocked(x + 12, y) && !blocked(x + tagW + 14, y)) { bx = x; tag = [x, y]; }
        }
      }
      // who gives way: the chosen mark first, then the bigger gathering, then whatever is nearer the eye
      for (const c of cand) c.sel = c.nd ? S.selIds.has(c.nd.id) : (!!S.sel && c.slot.things.some(t => t.id === S.sel));
      cand.sort((a, b) => (b.sel - a.sel) || (b.n - a.n) || (b.near - a.near) || (a.id < b.id ? -1 : 1));
      const fresh = [], placed = [], boxes = [];
      if (tag) boxes.push([tag[0] + 8, tag[1] - 10, tag[0] + 14 + (ringTag.offsetWidth || 120), tag[1] + 10]);
      for (const c of cand) {
        if (blocked(c.x, c.y)) continue;
        const g = c.n > 1 ? countSize(c.n) / 2 : 11;
        let free = true;
        for (const p of placed) if (Math.abs(p.x - c.x) < p.g + g - 3 && Math.abs(p.y - c.y) < p.g + g - 3) { free = false; break; }
        if (!free && !c.sel) continue;
        c.g = g; c.rec = recFor(c, fresh); placed.push(c); boxes.push([c.x - g, c.y - g, c.x + g, c.y + g]);
      }
      if (fresh.length) { for (const r of fresh) r.lw = r.l ? r.l.offsetWidth : 0; for (const r of fresh) { r.labelOn = false; r.el.classList.remove('has-l'); } }
      // names: the ones already showing keep their place, so nothing flickers as the globe turns
      const named = placed.filter(c => c.rec.lw > 0).sort((a, b) => (b.rec.labelOn - a.rec.labelOn));
      for (const c of named) {
        const x0 = c.x + c.g + 2, hh = Math.max(10, c.g), box = [x0, c.y - hh, x0 + c.rec.lw + 2, c.y + hh];   // the whole button is this tall, not just its words
        let ok = box[2] < W - 4 && !blocked(box[2], c.y) && c.face > 0.12;
        if (ok) for (const b of boxes) if (box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]) { ok = false; break; }
        c.label = ok; if (ok) boxes.push(box);
      }
      for (const c of placed) {
        const r = c.rec; r.seen = frameNo;
        const tx = Math.round(c.x * 10) / 10, ty = Math.round(c.y * 10) / 10;
        if (r.x !== tx || r.y !== ty) { r.x = tx; r.y = ty; r.el.style.transform = 'translate3d(' + tx + 'px,' + ty + 'px,0)'; }
        const op = c.sat ? 1 : Math.round(clamp(0.3 + c.face * 2.6, 0.3, 1) * 20) / 20;
        if (r.op !== op) { r.op = op; r.el.style.opacity = op; }
        if (r.labelOn !== !!c.label) { r.labelOn = !!c.label; r.el.classList.toggle('has-l', r.labelOn); }
        if (r.sel !== c.sel) { r.sel = c.sel; r.el.classList.toggle('is-sel', c.sel); }
        if (!r.on) { r.on = true; r.el.style.display = ''; r.el.style.visibility = ''; }
      }
      for (const r of marks.values()) {
        if (r.seen === frameNo) continue;
        if (r.on) { r.on = false; r.el.style.display = 'none'; if (tip._for === r) hideTip(); }
        else if (frameNo - r.seen > 300) { r.el.remove(); marks.delete(r.id); }
      }
      if (tag) { ringTag.style.transform = 'translate3d(' + Math.round(tag[0] + 12) + 'px,' + Math.round(tag[1]) + 'px,0)'; ringTag.textContent = 'Universal · ' + S.uni.length; }
      ringTag.style.display = tag ? '' : 'none';
      S.count = placed.length;
    }

    // ── hovering: what a mark is, and what a click on it will do ──
    function showTip(r) {
      tip.textContent = ''; tip._for = r;
      if (r.one) {
        const t = r.one;
        tip.append(h('b', null, t.name), h('span', null, (t.kind === 'room' ? (t.sub || 'listener') + ' · music room' : KIND_ONE[t.kind]) + ' · ' + (t.place ? (t.place.name || 'on the globe') : 'universal')));
      } else {
        const names = placeNames(r.things);
        tip.append(h('b', null, plural(r.things.length, 'thing')), h('span', null, describe(r.things)));
        if (r.nd && names.length) tip.append(h('span', null, someNames(names, 3)));
        if (r.slot) tip.append(h('span', null, 'universal · ' + initials(r.things)));
        const dd = r.nd && core ? splitDist(r.nd, core.f, RADII) : null;
        tip.append(h('em', null, dd != null && dd < core.d - 0.02 ? 'Click to move closer' : 'Click to list them'));
      }
      tip.classList.add('on');
      const w = tip.offsetWidth, hh = tip.offsetHeight, x = clamp(r.x - w / 2, 6, core.W - w - 6), y = r.y - r.g - hh - 8;
      tip.style.transform = 'translate3d(' + Math.round(x) + 'px,' + Math.round(y < 6 ? r.y + r.g + 8 : y) + 'px,0)';
    }
    function hideTip() { tip.classList.remove('on'); tip._for = null; }
    const initials = things => { const a = (things[0].name || '?').trim().charAt(0).toUpperCase(), b = (things[things.length - 1].name || '?').trim().charAt(0).toUpperCase(); return a === b ? a : a + ' to ' + b; };
    marksEl.addEventListener('pointerover', e => { const el = e.target.closest && e.target.closest('.gx-m'); const r = el && marks.get(el.dataset.id); if (r && core && !core.busy) { showTip(r); S.hold = !!r.slot; } });
    marksEl.addEventListener('pointerout', e => { const el = e.target.closest && e.target.closest('.gx-m'); if (el && !el.contains(e.relatedTarget)) { hideTip(); S.hold = false; } });
    marksEl.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('.gx-m'); const r = el && marks.get(el.dataset.id); if (r) showTip(r); });
    marksEl.addEventListener('focusout', hideTip);
    marksEl.addEventListener('click', e => {
      const el = e.target.closest && e.target.closest('.gx-m'), r = el && marks.get(el.dataset.id);
      if (!r) return;
      hideTip(); hinted();
      if (r.one) { select(r.one); openCard(r.one, null); return; }
      const dd = r.nd && core ? splitDist(r.nd, core.f, RADII) : null;
      if (dd != null && dd < core.d - 0.02) { core.flyTo({ v: r.nd.v, d: dd }, 700); return; }       // it can come apart: move closer
      openList(r.things, { title: plural(r.things.length, 'thing') + (r.slot ? '' : ' here'),
        sub: r.slot ? 'Universal · ' + initials(r.things) : someNames(placeNames(r.things), 4) });
    });
    ringTag.addEventListener('click', () => openList(S.uni, { title: plural(S.uni.length, 'universal thing'), sub: 'They have no place set, so they go round the globe.' }));
    function hinted() { if (prefs.hinted) return; prefs.hinted = true; keys.classList.add('is-off'); savePrefs(prefs); }

    // ── the sheet on the right: a list, or one thing ──
    function closeSheet() {
      if (!S.sheet) return false;
      S.sheet = null; sheet.classList.remove('on'); sheet.textContent = '';
      if (core) core.setShift(0);
      select(null); scanBlocks();
      return true;
    }
    function sheetFrame(kicker, back) {
      sheet.textContent = '';
      const head = h('div', { class: 'gx-sheet__head' },
        back ? h('button', { class: 'gx-link', type: 'button', onclick: back }, '‹ Back to the list') : h('span', { class: 'gx-kicker' }, kicker),
        h('button', { class: 'gx-x', type: 'button', 'aria-label': 'Close', title: 'Close', onclick: closeSheet }, '✕'));
      const body = h('div', { class: 'gx-sheet__body' });
      sheet.append(head, body); sheet.classList.add('on');
      if (core) core.setShift(host.getBoundingClientRect().width > 1100 ? 150 : 0);
      scanBlocks();
      return body;
    }
    const placeLine = t => (t.place ? (t.place.name || 'On the globe') : 'Universal');
    function openList(things, o) {
      o = o || {};
      const state = { things: things.slice(), q: '', o };
      const back = () => open();
      const draw = () => {
        const body = sheetFrame('List', null);
        body.append(h('h2', { class: 'gx-h' }, o.title || plural(state.things.length, 'thing')));
        if (o.sub) body.append(h('p', { class: 'gx-sub' }, o.sub));
        const rows = h('div', { class: 'gx-rows' });
        const fill = () => {
          rows.textContent = '';
          const words = fold(state.q).split(/\s+/).filter(Boolean);
          const list = state.things.filter(t => !words.length || matches(t._hay, words))
            .sort((a, b) => (KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind)) || (a._fn < b._fn ? -1 : a._fn > b._fn ? 1 : 0));
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
      body.append(h('p', { class: 'gx-where' }, glyph(t.kind), t.place ? (t.place.name || 'On the globe') : 'Universal: no place set'));
      if (t.kind === 'room' && t.covers && t.covers.length) {
        const strip = h('div', { class: 'gx-covers' });
        for (const id of t.covers.slice(0, 4)) { const img = h('img', { src: '/api/gr/art/' + encodeURIComponent(id), alt: '', loading: 'lazy' }); img.addEventListener('error', () => img.remove()); strip.append(img); }
        body.append(strip);
      }
      if (t.blurb) body.append(h('p', { class: 'gx-blurb' }, t.blurb));
      if (t.kind === 'room') body.append(h('p', { class: 'gx-sub' }, t.count ? plural(t.count, 'record') : 'No records for sale'));
      if (t.tags.length) body.append(h('div', { class: 'gx-chips' }, t.tags.map(g => h('button', { class: 'gx-chip' + (S.tags.has(g) ? ' on' : ''), type: 'button', title: 'Show only things tagged ' + g, onclick: () => { toggleTag(g); } }, g))));
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
      if (t.v) acts.append(h('button', { class: 'gx-btn', type: 'button', onclick: () => goTo(t) }, 'Show where it is'));
      // keep it in a grúpa: a room by its handle, anything else as its link (the page gives the way — opts.addToGrupa)
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
    // turn (by the shortest way, never re-levelling) so a thing faces the viewer, close enough for it to stand alone
    function goTo(t) {
      select(t);
      if (!core || !t.v) return;
      const leaf = S.leaf.get(t.id);
      core.flyTo({ v: t.v, d: Math.min(core.d, leaf ? aloneDist(leaf, core.f, RADII) : core.d) }, 800);
    }

    // ── the panel on the left ──
    const sum = h('p', { class: 'gx-sum', 'aria-live': 'polite' });
    const warn = h('p', { class: 'gx-warn' });
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
    panel.append(sum, warn);
    const showB = section('show', 'Show'), findB = section('find', 'Find'), quickB = section('quick', 'Quick views'), lookB = section('look', 'Look');
    const findBox = h('input', { class: 'gx-find', type: 'search', placeholder: 'name, place or tag', 'aria-label': 'Find by name, place or tag', autocomplete: 'off', spellcheck: 'false' });
    const findSay = h('div', { class: 'gx-findsay' }), tagBox = h('div', { class: 'gx-chips' });
    findBox.addEventListener('input', () => { clearTimeout(findT); findT = setTimeout(() => { S.find = findBox.value; refilter(); }, 130); });
    findBox.addEventListener('keydown', e => {
      if (e.key === 'Escape' && findBox.value) { e.stopPropagation(); findBox.value = ''; S.find = ''; refilter(); }
      if (e.key === 'Enter') { clearTimeout(findT); S.find = findBox.value; refilter(); listShown(); }
    });
    findB.append(findBox, findSay, tagBox);
    function listShown() {
      openList(S.shown, { title: plural(S.shown.length, 'thing'), sub: S.words.length || S.tags.size ? 'Everything that matches.' : 'Everything showing.', live: () => S.shown });
    }
    function toggleTag(g) { if (S.tags.has(g)) S.tags.delete(g); else S.tags.add(g); refilter(); if (S.sheet && S.sheet.kind === 'card') { /* the chips on the card follow */ sheet.querySelectorAll('.gx-chip').forEach(c => c.classList.toggle('on', S.tags.has(c.textContent))); } }
    function check(label, on, n, kind, click, small) {
      return h('button', { class: 'gx-check' + (small ? ' gx-check--sub' : ''), type: 'button', role: 'switch', 'aria-checked': String(on), onclick: click },
        h('i', { class: 'gx-check__box', 'aria-hidden': 'true' }), kind ? glyph(kind) : null, h('span', null, label), h('b', null, String(n)));
    }
    function renderPanel() {
      const total = S.all.length, shown = S.shown.length, placed = S.shown.filter(t => t.v).length;
      sum.textContent = total ? (shown === total ? plural(total, 'thing') : shown + ' of ' + plural(total, 'thing')) + ' · ' + placed + ' on the globe · ' + (shown - placed) + ' universal'
                              : (S.loading ? 'Loading…' : 'Nothing to show yet.');
      warn.textContent = S.roomsError ? 'Music rooms are missing: ' + S.roomsError + '. Everything else is here.' : (S.failed && !total ? "The list didn't load. Leave this view and come back to try again." : '');
      warn.style.display = warn.textContent ? '' : 'none';
      // Show: kinds, then on the globe / universal — each with how many there would be
      showB.textContent = '';
      for (const k of KINDS) {
        const n = S.all.filter(t => t.kind === k && passes(t, 'kind') && (k !== 'room' || prefs.subs[t.sub || 'listener'] !== false)).length;
        if (!S.all.some(t => t.kind === k)) continue;
        showB.append(check(KIND_MANY[k], prefs.kinds[k] !== false, n, k, () => { prefs.kinds[k] = prefs.kinds[k] === false; savePrefs(prefs); refilter(); }));
        if (k === 'room' && prefs.kinds.room !== false) {
          const subs = [...new Set(S.all.filter(t => t.kind === 'room').map(t => t.sub || 'listener'))].sort();
          if (subs.length > 1) for (const s of subs)
            showB.append(check(SUB_MANY[s] || s, prefs.subs[s] !== false, S.all.filter(t => t.kind === 'room' && (t.sub || 'listener') === s && passes(t, 'kind')).length, null,
              () => { prefs.subs[s] = prefs.subs[s] === false; savePrefs(prefs); refilter(); }, true));
        }
      }
      showB.append(h('div', { class: 'gx-rule' }));
      for (const w of ['placed', 'universal']) {
        const n = S.all.filter(t => (w === 'placed') === !!t.v && passes(t, 'where')).length;
        showB.append(check(w === 'placed' ? 'On the globe' : 'Universal (no place)', prefs.where[w] !== false, n, null, () => { prefs.where[w] = prefs.where[w] === false; savePrefs(prefs); refilter(); }));
      }
      // Find: how many match, and the tags worth trying
      findSay.textContent = '';
      findSay.append(h('span', null, S.words.length || S.tags.size ? plural(shown, 'match', 'matches') : plural(shown, 'thing') + ' showing'),
        h('button', { class: 'gx-link', type: 'button', onclick: listShown }, 'List them'));
      const counts = {};
      for (const t of S.all) if (passes(t, 'tags')) for (const g of t.tags) counts[g] = (counts[g] || 0) + 1;
      const top = Object.keys(counts).sort((a, b) => (S.tags.has(b) - S.tags.has(a)) || counts[b] - counts[a] || (a < b ? -1 : 1)).slice(0, 12);
      for (const g of S.tags) if (!top.includes(g)) top.unshift(g);
      tagBox.textContent = '';
      for (const g of top) tagBox.append(h('button', { class: 'gx-chip' + (S.tags.has(g) ? ' on' : ''), type: 'button', 'aria-pressed': String(S.tags.has(g)), onclick: () => toggleTag(g) }, g, h('b', null, String(counts[g] || 0))));
      // Quick views: nothing here names a continent or a country — only where the things are, and the names their owners gave
      quickB.textContent = '';
      quickB.append(h('div', { class: 'gx-btns' },
        h('button', { class: 'gx-btn', type: 'button', onclick: () => viewThings() }, 'Where the things are'),
        h('button', { class: 'gx-btn', type: 'button', onclick: () => core && core.flyTo({ q: qNorm(qMul(qAxis([0, 1, 0], Math.PI), core.q)) }, 900) }, 'The other side'),
        h('button', { class: 'gx-btn', type: 'button', onclick: () => core && core.flyTo({ d: core.viewAll() }, 700) }, 'Step back')));
      const names = {};
      for (const t of S.shown) if (t.v && t.place.name) { const key = fold(t.place.name), e = names[key] || (names[key] = { name: t.place.name, vs: [], n: 0 }); e.vs.push(t.v); e.n++; }
      const places = Object.values(names).sort((a, b) => b.n - a.n || (fold(a.name) < fold(b.name) ? -1 : 1)).slice(0, 7);
      if (places.length) {
        quickB.append(h('div', { class: 'gx-label' }, 'Places, as their owners named them'));
        for (const p of places) quickB.append(h('button', { class: 'gx-place', type: 'button', onclick: () => { const v = middle(p.vs) || p.vs[0]; if (core) core.flyTo({ v, d: Math.min(core.d, 1.7) }, 850); } }, h('span', null, p.name), h('b', null, String(p.n))));
      }
      // Look
      lookB.textContent = '';
      const press = (label, on, click) => h('button', { class: 'gx-btn' + (on ? ' on' : ''), type: 'button', 'aria-pressed': String(on), onclick: click }, label);
      const look = fn => () => { fn(); savePrefs(prefs); applyLook(); renderPanel(); };
      lookB.append(h('div', { class: 'gx-label' }, 'Grid lines'),
        h('div', { class: 'gx-btns' }, press('Meridians', prefs.mer, look(() => { prefs.mer = !prefs.mer; })), press('Parallels', prefs.par, look(() => { prefs.par = !prefs.par; }))),
        h('div', { class: 'gx-label' }, 'Dots'),
        h('div', { class: 'gx-btns' }, ['sparse', 'normal', 'fine'].map(v => press(v.charAt(0).toUpperCase() + v.slice(1), prefs.dens === v, look(() => { prefs.dens = v; })))),
        h('div', { class: 'gx-btns' }, press('Round', prefs.shape === 'round', look(() => { prefs.shape = 'round'; })), press('Square', prefs.shape === 'square', look(() => { prefs.shape = 'square'; }))),
        h('div', { class: 'gx-label' }, 'Which way is up'),
        h('div', { class: 'gx-btns' },
          h('button', { class: 'gx-btn', type: 'button', onclick: () => core && core.face(core.facing(), [0, -1, 0], 700) }, 'South up'),
          h('button', { class: 'gx-btn', type: 'button', onclick: () => core && core.face(core.facing(), [0, 1, 0], 700) }, 'North up')),
        h('div', { class: 'gx-label' }, 'Movement'),
        h('div', { class: 'gx-btns' }, press('Turn slowly', prefs.spin, look(() => { prefs.spin = !prefs.spin; }))));
    }
    function applyLook() { if (!core) return; core.setGraticule(prefs.mer, prefs.par); core.setDensity(prefs.dens); core.setShape(prefs.shape); core.setSpin(prefs.spin); }
    // face the middle of what is showing, from far enough back to hold all of it
    function viewThings(ms) {
      if (!core) return;
      const vs = S.shown.filter(t => t.v).map(t => t.v), mid = middle(vs);
      if (!mid) { core.flyTo({ d: core.viewAll() }, ms); return; }
      let far = 0;
      for (const v of vs) far = Math.max(far, Math.acos(clamp(dot(v, mid), -1, 1)));
      const room = 0.38 * Math.min(core.W, core.H), dd = far > 1.15 ? core.viewAll() : clamp(Math.cos(far) + core.f * Math.sin(far) / room, 1.5, core.viewAll());
      core.flyTo({ v: mid, d: dd }, ms == null ? 850 : ms);
    }

    // ── starting, showing, hiding ──
    async function boot() {
      setNote('Loading the globe…');
      load();
      try { core = await createCore(stage, { lowPower: opts.lowPower, q: prefs.q, d: prefs.d, density: prefs.dens, shape: prefs.shape, meridians: prefs.mer, parallels: prefs.par }); }
      catch (e) {
        host.classList.add('gx--flat');
        setNote(e && e.code === 'no-webgl' ? "This computer can't draw the globe. The lists still work: use Find, then List them." : "The globe didn't load. The lists still work: use Find, then List them.");
        return;
      }
      if (dead) { core.dispose(); return; }
      setNote('');
      applyLook();
      core.setRing(S.ringQ, RING_R, S.uni.length > 0);
      // the very first time: face where the things are, south at the top, far enough back to see the ring.
      // after that: the way it was left.
      if (!prefs.q) core.set(S.homeQ, core.viewAll());
      core.on('before', x => {
        // the ring turns slowly; it stops under the pointer, and for anyone who has asked for less motion
        if (!core.reduce && !S.hold && S.uni.length && !(opts.covered && opts.covered())) { S.phase = (S.phase + x.dt / 1000 * (2 * Math.PI / 420)) % (2 * Math.PI); x.moved = true; }
      });
      core.on('frame', updateMarks);
      core.on('settle', () => { S.touched = true; clearTimeout(saveT); saveT = setTimeout(() => { prefs.q = core.q.map(n => +n.toFixed(5)); prefs.d = +core.d.toFixed(4); savePrefs(prefs); }, 500); hinted(); });
      core.on('resize', () => { scanBlocks(); if (!prefs.q && !S.touched) core.set(S.homeQ, core.viewAll()); });   // (a window that had no size yet when it opened)
      core.on('tap', () => { if (S.sheet && S.sheet.kind === 'card') closeSheet(); });
      if (visible) core.start();
    }
    const onResize = () => { if (visible) place(); };
    function place() { if (opts.top) { const y = opts.top(); if (y > 0) host.style.top = Math.round(y) + 'px'; } scanBlocks(); if (core) core.poke(); }
    root.addEventListener('resize', onResize);
    const watch = setInterval(() => { if (visible && !document.hidden) { scanBlocks(); if (core) core.poke(); } }, 1000);

    const ctl = {
      show() {
        visible = true; place();
        if (!core && !ctl._booted) { ctl._booted = true; boot(); }
        else if (Date.now() - S.loadedAt > 45000) load();           // a room may have set its place since
        if (core) { core.setTones(); core.start(); }
        setTimeout(() => { if (visible) place(); }, 400);
      },
      hide() { visible = false; if (core) core.stop(); hideTip(); },
      escape() { if (S.sheet) { closeSheet(); return true; } if (host.classList.contains('gx--panelopen')) { host.classList.remove('gx--panelopen'); return true; } return false; },
      reload: load,
      // for checking it by hand: step one frame, swap the things for others, read what is drawn
      frame(now) { if (core) { core.poke(); core.step(now); } },
      setThings(list) { S.loadedAt = Date.now(); adopt(list, null); },
      state() { return { things: S.all.length, shown: S.shown.length, universal: S.uni.length, level: S.level, marks: S.count || 0, slots: S.slots.length, room: S.K, d: core ? core.d : null, q: core ? core.q : null,
                         f: core ? core.f : null, dots: core ? core.dots() : null, sheet: S.sheet ? S.sheet.kind : null, sel: S.sel, roomsError: S.roomsError }; },
      core: () => core,
      destroy() { dead = true; clearInterval(watch); root.removeEventListener('resize', onResize); if (core) core.dispose(); host.textContent = ''; },
    };
    renderPanel();
    return ctl;
  }

  // ═══════════════ 5. the small globe on /myroom: click it to say where your room is ═══════════════
  // opts: { value: {lat, lon} | null, onPick(lat, lon), lowPower }
  function picker(host, opts) {
    opts = opts || {};
    host.classList.add('gx', 'gx--pick'); host.textContent = '';
    const stage = h('div', { class: 'gx-stage', tabindex: '0', role: 'application', 'aria-label': 'A globe. Drag to turn it, then click the spot.' });
    const pin = h('i', { class: 'gx-pin', 'aria-hidden': 'true' });
    const note = h('div', { class: 'gx-note on' }, 'Loading the globe…');
    const bar = h('div', { class: 'gx-pickbar gx-nodrag' });
    stage.append(pin, note, bar); host.append(stage);
    let core = null, spot = opts.value && isFinite(opts.value.lat) && isFinite(opts.value.lon) ? vecOf(+opts.value.lat, +opts.value.lon) : null, dead = false;
    const P = { x: 0, y: 0, wz: 0, face: 0 };
    function draw() {
      if (!core) return;
      if (!spot) { pin.style.display = 'none'; return; }
      core.toScreen(core.mat(), spot, P);
      pin.style.display = P.face > 0.01 ? 'block' : 'none';       // (the stylesheet keeps it hidden until there is a spot)
      pin.style.transform = 'translate3d(' + P.x.toFixed(1) + 'px,' + P.y.toFixed(1) + 'px,0)';
    }
    (async () => {
      try { core = await createCore(stage, { lowPower: opts.lowPower, d: 3.1, wheelNeedsPress: true }); }
      catch (e) { note.textContent = "This computer can't draw the globe, so a spot can't be picked here."; return; }
      if (dead) { core.dispose(); return; }
      note.classList.remove('on'); note.textContent = '';
      // with a spot: face it. Without: face this computer's own longitude, worked out from its clock (nothing is looked up or sent)
      const lon = clamp(-new Date().getTimezoneOffset() / 4, -180, 180);
      core.set(qFace(spot || vecOf(0, lon), OPEN_UP), spot ? 2.4 : 3.1);
      const btn = (label, title, fn) => h('button', { class: 'gx-btn', type: 'button', title, onclick: fn }, label);
      bar.append(btn('+', 'Move closer', () => core.zoomBy(0.7)), btn('−', 'Step back', () => core.zoomBy(1.4)),
        btn('South up', 'Turn it so south is at the top', () => core.face(core.facing(), [0, -1, 0], 500)), btn('North up', 'Turn it so north is at the top', () => core.face(core.facing(), [0, 1, 0], 500)));
      core.on('frame', draw);
      core.on('tap', v => { if (!v) return; spot = v; const ll = latLonOf(v); core.poke(); if (opts.onPick) opts.onPick(+ll.lat.toFixed(4), +ll.lon.toFixed(4)); });
      core.start();
    })();
    return {
      set(place) { spot = place && isFinite(place.lat) && isFinite(place.lon) ? vecOf(+place.lat, +place.lon) : null; if (core) { if (spot) core.flyTo({ v: spot }, 500); core.poke(); } },
      get() { return spot ? latLonOf(spot) : null; },
      frame(now) { if (core) { core.poke(); core.step(now); } },
      core: () => core,
      destroy() { dead = true; if (core) core.dispose(); host.textContent = ''; },
    };
  }

  root.ExploreGlobe = { mount, picker, pure };
})(typeof window !== 'undefined' ? window : globalThis);
