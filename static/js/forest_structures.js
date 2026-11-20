// =============================================================
// forest_structures.js — procedural 3D buildings for the places
// standing in the 3D forest (/forest3d).
//
// Each illustration kind becomes a real little structure instead of a
// billboard, built from primitive geometry (no model downloads). Every
// builder takes the SAME four colour roles as the 2D illustrations
// (light / structure / outline / detail — resolved upstream by
// placeIllustrationDefaults, so theme-aware auto-defaults and explicit
// overrides both arrive here as plain hex):
//
//   light      window / lamp / fire glow (emissive, toneMapped off)
//   structure  the main mass of the building/object
//   outline    roofs, trim, rails (mid-tone)
//   detail     secondary accent: chimneys, signs, stones
//
// build(THREE, place, kind, roles) → THREE.Group with:
//   .userData.pid    the place id (raycast picking walks up to this)
//   .userData.h      total height (label anchor)
//   .userData.smoke  [{m, base, ph, amp}] chimney smoke the frame loop drifts
//   .userData.water  [{m, ph}] water surfaces the frame loop shimmers
//
// Buildings face +Z (the default camera side). They do NOT billboard —
// that's the whole point. Scales are tuned to sit among the instanced
// trees (≈12–25 units tall).
// =============================================================
(function () {
'use strict';

const DARK_FIGURE = 0x14100c;   // people read as quiet silhouettes
const FOLIAGE     = 0x33492c;   // environmental green (matches the wood)

// ---- relevant surfaces for the building bodies -------------------------------
// Procedural canvas textures (offline, no files) so a structure reads as a real
// material instead of flat colour: STONE for the stony kinds (cathedral, the
// well, cottage, pub), CONCRETE for the industrial ones (club, warehouse, flat).
// Noise-based so they tolerate the stretch of box UVs; greyscale so the place's
// own structure colour still tints them. Cached — at most two textures exist.
const _KIND_SURFACE = { cathedral:'stone', well:'stone', cottage:'stone', pub:'stone',
                        club:'concrete', warehouse:'concrete', flat:'concrete' };
let _surfaceCache = null;
function structureTexture(THREE, kind) {
    const type = _KIND_SURFACE[kind];
    if (!type) return null;
    _surfaceCache = _surfaceCache || {};
    if (_surfaceCache[type]) return _surfaceCache[type];
    const N = 256, cv = document.createElement('canvas'); cv.width = cv.height = N;
    const x = cv.getContext('2d');
    const speckle = (count, lo, hi, a) => {
        for (let i = 0; i < count; i++) { const v = (lo + Math.random() * (hi - lo)) | 0;
            x.fillStyle = `rgba(${v},${v},${v},${a})`;
            x.fillRect(Math.random() * N, Math.random() * N, 1 + Math.random() * 2, 1 + Math.random() * 2); }
    };
    if (type === 'concrete') {
        x.fillStyle = '#aeaeae'; x.fillRect(0, 0, N, N);
        speckle(12000, 90, 160, 0.16); speckle(5000, 175, 225, 0.13);   // grain, dark + light
        for (let i = 0; i < 320; i++) {                                 // pitting — small dark pocks
            const r = 0.6 + Math.random() * 3.2;
            x.fillStyle = `rgba(56,54,50,${0.10 + Math.random() * 0.18})`;
            x.beginPath(); x.arc(Math.random() * N, Math.random() * N, r, 0, 7); x.fill();
        }
        for (let i = 0; i < 16; i++) {                                  // weather stains
            x.strokeStyle = `rgba(50,48,43,${0.08 + Math.random() * 0.14})`;
            x.lineWidth = 1 + Math.random() * 5; const sx = Math.random() * N;
            x.beginPath(); x.moveTo(sx, 0);
            x.bezierCurveTo(sx + 12, N / 3, sx - 12, 2 * N / 3, sx + (Math.random() * 18 - 9), N); x.stroke();
        }
        x.strokeStyle = 'rgba(58,56,51,0.28)'; x.lineWidth = 1.5;       // poured-panel seams
        for (let gy = 0; gy <= N; gy += 128) { x.beginPath(); x.moveTo(0, gy); x.lineTo(N, gy); x.stroke(); }
    } else {                                                            // stone — ashlar courses
        x.fillStyle = '#b6ae9e'; x.fillRect(0, 0, N, N);
        const rh = 40, cw = 52;                                         // course height / block width
        let y = 0, row = 0;
        while (y <= N) {                                                // per-block tonal variation
            const off = (row % 2) * (cw / 2);
            for (let bx = off - cw; bx <= N; bx += cw) {
                const tone = 150 + ((Math.random() * 70) | 0);
                x.fillStyle = `rgba(${tone},${tone - 6},${tone - 20},0.18)`;
                x.fillRect(bx + 1.5, y + 1.5, cw - 3, rh - 3);
            }
            y += rh; row++;
        }
        y = 0; row = 0;
        while (y <= N) {                                                // carved mortar: dark groove + lower highlight
            x.strokeStyle = 'rgba(42,38,31,0.62)'; x.lineWidth = 2.6;
            x.beginPath(); x.moveTo(0, y); x.lineTo(N, y); x.stroke();
            x.strokeStyle = 'rgba(226,219,200,0.18)'; x.lineWidth = 1;
            x.beginPath(); x.moveTo(0, y + 2.6); x.lineTo(N, y + 2.6); x.stroke();
            const off = (row % 2) * (cw / 2);
            x.strokeStyle = 'rgba(42,38,31,0.62)'; x.lineWidth = 2.6;
            for (let bx = off; bx <= N; bx += cw) { x.beginPath(); x.moveTo(bx, y); x.lineTo(bx, y + rh); x.stroke(); }
            y += rh; row++;
        }
        speckle(13000, 140, 195, 0.10); speckle(4000, 85, 125, 0.09);   // grain
        for (let i = 0; i < 9; i++) {                                   // weathering patches
            x.fillStyle = `rgba(64,60,50,${0.06 + Math.random() * 0.08})`;
            x.beginPath(); x.ellipse(Math.random() * N, Math.random() * N,
                18 + Math.random() * 32, 12 + Math.random() * 22, Math.random() * 3, 0, 7); x.fill();
        }
    }
    const t = new THREE.CanvasTexture(cv);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    const r = type === 'stone' ? 2.6 : 3.6; t.repeat.set(r, r);
    _surfaceCache[type] = t;
    return t;
}

window.ForestStructures = {

build(THREE, p, kind, roles) {
    // ---- tiny shared kit -------------------------------------------------
    const C = (hex) => new THREE.Color(hex);
    const mat = (hex, o = {}) => new THREE.MeshStandardMaterial(
        Object.assign({ color: C(hex), roughness: 1, flatShading: true }, o));
    // glowing surfaces ignore tone mapping so windows stay warm at twilight
    const glow = (hex, opacity) => new THREE.MeshBasicMaterial({
        color: C(hex), toneMapped: false,
        transparent: opacity !== undefined, opacity: opacity ?? 1,
        depthWrite: opacity === undefined });
    const g = new THREE.Group();
    const add = (mesh, x = 0, y = 0, z = 0, ry = 0) => {
        mesh.position.set(x, y, z); if (ry) mesh.rotation.y = ry;
        g.add(mesh); return mesh;
    };
    const box = (w, h, d, m, x, y, z, ry) =>
        add(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m), x, y, z, ry);
    const cyl = (r1, r2, h, seg, m, x, y, z) =>
        add(new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, seg), m), x, y, z);
    // gabled roof = triangle extruded along the building depth
    const gable = (w, h, d, m, x, y, z, ry) => {
        const s = new THREE.Shape();
        s.moveTo(-w / 2, 0); s.lineTo(w / 2, 0); s.lineTo(0, h); s.closePath();
        const geo = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false });
        geo.translate(0, 0, -d / 2);
        return add(new THREE.Mesh(geo, m), x, y, z, ry);
    };
    // a lit pane sitting just proud of a wall (z-fight-safe)
    const pane = (w, h, x, y, z, ry = 0, opacity) => {
        const m = add(new THREE.Mesh(new THREE.PlaneGeometry(w, h), glow(roles.light, opacity)), x, y, z, ry);
        return m;
    };
    // warm pool of light spilling on the ground in front of a doorway
    const pool = (r, x, z, opacity = 0.16) => {
        const m = add(new THREE.Mesh(new THREE.CircleGeometry(r, 20), glow(roles.light, opacity)), x, 0.07, z);
        m.rotation.x = -Math.PI / 2; return m;
    };
    const person = (x, z, scale = 1, ry = 0) => {
        const pm = mat('#14100c', { color: new THREE.Color(DARK_FIGURE) });
        const body = new THREE.Mesh(new THREE.ConeGeometry(0.55 * scale, 1.9 * scale, 6), pm);
        body.position.y = 0.95 * scale;
        const head = new THREE.Mesh(new THREE.SphereGeometry(0.34 * scale, 7, 6), pm);
        head.position.y = 2.15 * scale;
        const fig = new THREE.Group(); fig.add(body, head);
        fig.position.set(x, 0, z); fig.rotation.y = ry; g.add(fig); return fig;
    };
    const smoke = (x, y, z) => {
        g.userData.smoke = g.userData.smoke || [];
        for (let i = 0; i < 4; i++) {
            const m = new THREE.Mesh(new THREE.SphereGeometry(0.34 + i * 0.16, 6, 5),
                new THREE.MeshBasicMaterial({ color: 0xb9c2c8, transparent: true,
                    opacity: 0.26, depthWrite: false, toneMapped: false }));
            m.position.set(x, y + i * 1.1, z);
            g.add(m);
            g.userData.smoke.push({ m, base: m.position.clone(), ph: i * 1.6 + rnd() * 6, amp: 0.5 + i * 0.3 });
        }
    };
    const water = (m, ph = 0) => {
        g.userData.water = g.userData.water || [];
        g.userData.water.push({ m, ph });
    };
    // deterministic per-place randomness — the same place always builds the
    // same little scene (lit windows, people poses) across reloads
    let _s = ((p.id * 2654435761) >>> 0) || 1;
    const rnd = () => { _s = (_s * 1664525 + 1013904223) >>> 0; return _s / 4294967296; };

    const sMat = mat(roles.structure);
    // the 2D illustrations define near-black bodies with outline strokes;
    // 3D has no strokes, so a near-black mass gets a faint lift to keep its
    // form legible at twilight (explicitly mid/light colours pass through)
    const _hsl = {}; sMat.color.getHSL(_hsl);
    if (_hsl.l < 0.09) sMat.color.lerp(C('#3a332a'), 0.4);
    const sDark = mat(roles.structure); sDark.color.multiplyScalar(0.6);
    const oMat = mat(roles.outline);
    const dMat = mat(roles.detail);

    // give the body a relevant material — stone/concrete grain (see above), tinted
    // by the structure colour, with a touch of bump so the sun catches the surface.
    const _bodyTex = structureTexture(THREE, kind);
    if (_bodyTex) {
        sMat.map = _bodyTex; sMat.bumpMap = _bodyTex; sMat.bumpScale = 0.85;
        sMat.color.multiplyScalar(1.32);  // lift the colour so the mid-grey texture doesn't darken it
        sMat.needsUpdate = true;
    }

    // ---- the kinds ---------------------------------------------------------
    const K = {

    club() {
        // the dark slab with a lit doorway… and the smoking area outside
        box(15, 8.5, 11, sMat, 0, 4.25, 0);
        box(15.8, 0.8, 11.8, oMat, 0, 8.9, 0);                     // roof lip (mid-tone so the slab's edge reads)
        box(2.6, 4.6, 0.5, sDark, 0, 2.3, 5.55);                   // door recess
        pane(1.9, 4.2, 0, 2.2, 5.83);                              // the lit doorway
        pane(4.6, 0.8, -4.6, 6.6, 5.53, 0, 0.85);                  // window strip
        pane(4.6, 0.8, 4.6, 6.6, 5.53, 0, 0.85);
        pool(3.4, 0, 7.6);
        // smoking area: a low rail off the side, a wall lamp, people standing
        const railM = oMat;
        for (let i = 0; i < 3; i++) cyl(0.09, 0.09, 1.5, 5, railM, 9.6, 0.75, -3 + i * 3);
        box(0.16, 0.16, 6.2, railM, 9.6, 1.45, 0);
        pane(0.9, 0.6, 7.58, 5.4, 0, Math.PI / 2, 0.95);           // wall lamp
        pool(2.6, 9.8, 1.2, 0.1);
        person(9.1, 2.6, 1, -0.7); person(10.6, 0.6, 0.95, 2.3); person(9.4, -1.8, 1.05, 0.4);
        person(-2.6, 7.4, 1, 0.1);                                 // the bouncer
        return 9.7;
    },

    warehouse() {
        box(19, 7.5, 12, sMat, 0, 3.75, 0);
        // sawtooth roof — 4 teeth, glass on the steep faces
        const tw = 19 / 4;
        for (let i = 0; i < 4; i++) {
            const x = -19 / 2 + tw * (i + 0.5);
            gable(tw, 2.6, 12, sDark, x, 7.5, 0);
            pane(tw * 0.62, 1.5, x - tw * 0.16, 8.6, 6.01, 0, 0.8);
        }
        box(5.4, 5.2, 0.4, sDark, 0, 2.6, 6.05);                   // sliding door frame
        pane(4.4, 4.6, 0, 2.4, 6.3);                               // spilling-light doorway
        pool(4, 0, 8.6);
        person(3.6, 7.6, 1, -0.4);
        return 10.1;
    },

    pub() {
        box(12, 6, 9, sMat, 0, 3, 0);
        gable(12.8, 3.4, 9.8, oMat, 0, 6, 0);
        box(1.4, 3, 1.4, dMat, 3.6, 8.2, 0);                       // chimney
        smoke(3.6, 9.8, 0);
        pane(2.2, 1.8, -3.4, 3.1, 4.53);                           // two warm windows
        pane(2.2, 1.8, 3.4, 3.1, 4.53);
        pane(2, 1.6, 6.01, 3, 0, Math.PI / 2, 0.9);                // side window
        box(1.8, 3.4, 0.3, sDark, 0, 1.7, 4.6);                    // door
        pane(1.8, 0.35, 0, 3.5, 4.78);                             // lit fanlight
        // hanging sign on a bracket
        box(1.6, 0.12, 0.12, dMat, -4.6, 5.4, 4.7);
        box(1.3, 0.9, 0.1, mat(roles.detail, {}), -5.1, 4.7, 4.7);
        pool(3, 0, 6.4);
        person(1.9, 6.2, 0.95, -0.5);
        return 9.4;
    },

    cottage() {
        box(9, 4.2, 7, sMat, 0, 2.1, 0);
        const thatch = mat(roles.detail); thatch.color.multiplyScalar(0.62);
        gable(10.4, 3.6, 8.2, thatch, 0, 4.1, 0);
        box(1.1, 2.4, 1.1, dMat, 2.7, 6, 0);                       // chimney
        smoke(2.7, 7.3, 0);
        pane(1.6, 1.4, -2.5, 2.3, 3.53);
        pane(1.6, 1.4, 2.5, 2.3, 3.53);
        box(1.5, 2.8, 0.3, sDark, 0, 1.4, 3.6);                    // door
        pool(2.4, 0, 5);
        // a low front wall + a green tuft
        box(7, 0.7, 0.5, dMat, 0, 0.35, 5.6);
        cyl(0.9, 1.2, 1.1, 6, mat('#33492c', { color: new THREE.Color(FOLIAGE) }), -4.4, 0.55, 4.6);
        return 7.7;
    },

    flat() {
        box(8.5, 17, 8.5, sMat, 0, 8.5, 0);
        box(9.1, 0.7, 9.1, oMat, 0, 17.2, 0);                      // parapet
        // window grid front + sides; ~45% lit (deterministic per place)
        const off = mat(roles.structure); off.color.multiplyScalar(0.55);
        for (let fy = 0; fy < 5; fy++) for (let fx = 0; fx < 4; fx++) {
            const x = -3 + fx * 2, y = 3.4 + fy * 2.7;
            if (rnd() < 0.45) pane(1.1, 1.4, x, y, 4.27);
            else box(1.1, 1.4, 0.06, off, x, y, 4.27);
            if (rnd() < 0.3) pane(1.1, 1.4, 4.27, y, x, Math.PI / 2);
        }
        box(2.4, 2.6, 0.4, sDark, 0, 1.3, 4.4);                    // entrance
        pane(1.7, 2.1, 0, 1.15, 4.62);
        pool(2.6, 0, 6.2);
        return 17.9;
    },

    car() {
        const bodyM = sMat;
        box(7, 1.5, 3.2, bodyM, 0, 1.25, 0);
        box(3.8, 1.25, 2.9, bodyM, -0.4, 2.6, 0);                  // cabin
        pane(3.2, 0.85, -0.4, 2.65, 1.48, 0, 0.32);                // glazing glow
        const wheel = mat('#111', { color: new THREE.Color(0x16130f) });
        [[-2.3, 1.45], [2.3, 1.45], [-2.3, -1.45], [2.3, -1.45]].forEach(([x, z]) => {
            const w = cyl(0.62, 0.62, 0.5, 10, wheel, x, 0.62, z);
            w.rotation.x = Math.PI / 2;
        });
        pane(0.5, 0.4, 3.52, 1.3, 0.95, Math.PI / 2);              // headlights
        pane(0.5, 0.4, 3.52, 1.3, -0.95, Math.PI / 2);
        // headlight throw on the ground
        const cone = add(new THREE.Mesh(new THREE.CircleGeometry(3.4, 18, -0.5, 1), glow(roles.light, 0.13)), 4, 0.07, 0);
        cone.rotation.x = -Math.PI / 2;
        return 3.4;
    },

    bbq() {
        cyl(1.5, 1.2, 1, 10, sDark, 0, 2, 0);                      // bowl
        const ember = add(new THREE.Mesh(new THREE.CircleGeometry(1.25, 12), glow(roles.light, 0.95)), 0, 2.55, 0);
        ember.rotation.x = -Math.PI / 2;
        water(ember, 2);                                           // embers breathe like water shimmer
        for (let i = 0; i < 3; i++) {
            const a = i * 2.1;
            const leg = cyl(0.08, 0.08, 2.2, 5, oMat, Math.cos(a) * 1, 1, Math.sin(a) * 1);
            leg.rotation.z = Math.cos(a) * 0.25; leg.rotation.x = -Math.sin(a) * 0.25;
        }
        smoke(0, 3.2, 0);
        person(2.6, 1.2, 0.95, -1.9); person(-2.2, 2, 0.9, 0.9);
        pool(2, 0, 0, 0.1);
        return 5.5;
    },

    beach() {
        // a little shore diorama: sand, water, a driftwood fire
        const sand = mat(roles.detail); sand.color.lerp(new THREE.Color(0xcdbb96), 0.55);
        const sd = add(new THREE.Mesh(new THREE.CircleGeometry(8.5, 24), sand), 0, 0.05, 0);
        sd.rotation.x = -Math.PI / 2;
        const wm = new THREE.MeshStandardMaterial({ color: new THREE.Color(0x2a3c42),
            roughness: 0.25, metalness: 0.35, transparent: true, opacity: 0.92 });
        const wa = add(new THREE.Mesh(new THREE.CircleGeometry(7.8, 24, Math.PI, Math.PI), wm), 0, 0.16, -0.5);
        wa.rotation.x = -Math.PI / 2;
        water(wa);
        const wood = mat('#5a4632', { color: new THREE.Color(0x5a4632) });
        const l1 = cyl(0.22, 0.26, 3, 6, wood, 0.6, 0.45, 3.4); l1.rotation.z = 1.2;
        const l2 = cyl(0.2, 0.24, 2.6, 6, wood, -0.5, 0.4, 3.8); l2.rotation.z = -1.1; l2.rotation.y = 0.6;
        const fire = add(new THREE.Mesh(new THREE.CircleGeometry(0.9, 10), glow(roles.light, 0.95)), 0.1, 0.2, 3.6);
        fire.rotation.x = -Math.PI / 2;
        water(fire, 4);
        smoke(0.1, 0.8, 3.6);
        person(2.8, 4.6, 0.9, -2.2);
        return 4;
    },

    field() {
        // open ground, a rise, the speaker stack
        const mound = add(new THREE.Mesh(new THREE.SphereGeometry(7, 14, 10),
            mat('#2c3a22', { color: new THREE.Color(0x2c3a22) })), 0, -5.4, -2);
        mound.scale.set(1.4, 1, 1);
        const spk = sDark;
        box(2.6, 2.2, 2, spk, 0, 2.7, 0); box(2.2, 1.9, 1.8, spk, 0, 4.75, 0);
        pane(1.7, 1.2, 0, 2.7, 1.03, 0, 0.55); pane(1.4, 1, 0, 4.75, 0.93, 0, 0.55);
        cyl(0.09, 0.09, 7.4, 5, oMat, -1.6, 3.7, -0.4);
        cyl(0.09, 0.09, 7.4, 5, oMat, 1.6, 3.7, -0.4);
        pool(4.4, 0, 3.4, 0.12);
        person(2.4, 4.2, 0.95, -0.4); person(-3, 5, 0.9, 0.5); person(0.4, 6.4, 0.85, 0.1);
        return 8;
    },

    forest() {
        // its own grove: four small trees around a campfire
        const fol = mat('#33492c', { color: new THREE.Color(FOLIAGE) });
        const trunk = mat('#4a3825', { color: new THREE.Color(0x4a3825) });
        [[-4.5, -2, 1.15], [4.6, -1.4, 1.05], [-2.8, 3, 0.8], [3.4, 2.6, 0.9]].forEach(([x, z, s]) => {
            cyl(0.3 * s, 0.5 * s, 4 * s, 5, trunk, x, 2 * s, z);
            add(new THREE.Mesh(new THREE.IcosahedronGeometry(2.6 * s, 0), fol), x, 5.4 * s, z);
        });
        const wood = mat('#5a4632', { color: new THREE.Color(0x5a4632) });
        const l1 = cyl(0.18, 0.22, 2.4, 6, wood, 0.4, 0.4, 0.2); l1.rotation.z = 1.25;
        const l2 = cyl(0.18, 0.22, 2.4, 6, wood, -0.4, 0.4, -0.1); l2.rotation.z = -1.2; l2.rotation.y = 0.8;
        const fire = add(new THREE.Mesh(new THREE.CircleGeometry(1, 10), glow(roles.light, 0.95)), 0, 0.14, 0);
        fire.rotation.x = -Math.PI / 2;
        water(fire, 1);
        smoke(0, 0.9, 0);
        pool(2.6, 0, 0, 0.12);
        return 8.4;
    },

    cathedral() {
        box(11, 8.5, 17, sMat, 0, 4.25, -1);
        gable(11.8, 4, 17.8, sDark, 0, 8.5, -1);
        box(4.6, 13, 4.6, sMat, 0, 6.5, 8.2);                      // front tower
        add(new THREE.Mesh(new THREE.ConeGeometry(3.3, 5.4, 4), sDark), 0, 15.7, 8.2);
        // celtic cross
        box(0.3, 2.4, 0.3, oMat, 0, 19.4, 8.2);
        box(1.5, 0.3, 0.3, oMat, 0, 19.7, 8.2);
        const ring = add(new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.09, 6, 14), oMat), 0, 19.7, 8.2);
        ring.rotation.y = 0;
        // arched windows down the nave (tall pane + round head)
        for (let i = 0; i < 3; i++) {
            const z = 3 - i * 4.4;
            [[-5.51, Math.PI / 2 * -1], [5.51, Math.PI / 2]].forEach(([x, ry]) => {
                pane(1.3, 3.2, x, 4.4, z, ry, 0.85);
                const head = add(new THREE.Mesh(new THREE.CircleGeometry(0.65, 10, 0, Math.PI), glow(roles.light, 0.85)), x, 6, z, ry);
            });
        }
        pane(1.6, 3.6, 0, 2.6, 10.51, 0, 0.9);                     // arched door, lit
        add(new THREE.Mesh(new THREE.CircleGeometry(0.8, 10, 0, Math.PI), glow(roles.light, 0.9)), 0, 4.4, 10.51);
        pool(3.2, 0, 12.4);
        return 20.6;
    },

    well() {
        // THE MUSIC ROOM — a warm log cabin at the heart of the wood (was the
        // sacred well; David's call 2026-07-06). Stacked-log walls with crossed
        // corner ends, a gabled shingle roof, a stone chimney with smoke, lit
        // windows, a little porch, firewood by the door. Cosy, lived-in — the
        // one window in the gable is round, like a record.
        const W = 10, D = 8;                                       // footprint
        const logA = mat('#6b4e30'), logB = mat('#5c4128');        // alternating timber
        const logEnd = mat('#8a6a42');
        const roofM = mat('#3a3026');
        const stone = mat('#b6b1a2');
        if (_bodyTex) { stone.map = _bodyTex; stone.bumpMap = _bodyTex; stone.bumpScale = 0.85; }
        const R = 0.34, COURSE = R * 1.9;                          // log radius / course height
        const COURSES = 7;
        for (let i = 0; i < COURSES; i++) {
            const y = R + i * COURSE, m = i % 2 ? logA : logB;
            // front + back logs run along X, poking past the corners (notched look)
            for (const z of [D / 2, -D / 2]) {
                const l = cyl(R, R, W + 1.5, 7, m, 0, y, z);
                l.rotation.z = Math.PI / 2;
            }
            // side logs run along Z, half a course up — interlocked corners
            for (const x of [W / 2, -W / 2]) {
                const l = cyl(R, R, D + 1.5, 7, i % 2 ? logB : logA, x, y + COURSE / 2, 0);
                l.rotation.x = Math.PI / 2;
            }
        }
        const wallTop = R + (COURSES - 1) * COURSE + COURSE / 2;
        // gable ends (plank triangles) + the roof with a generous overhang
        gable(W + 0.4, 3.2, 0.9, logA, 0, wallTop, D / 2 - 0.15);
        gable(W + 0.4, 3.2, 0.9, logA, 0, wallTop, -D / 2 + 0.15);
        gable(W + 2.4, 3.6, D + 2.6, roofM, 0, wallTop + 0.05, 0);
        box(0.5, 0.5, D + 2.8, logEnd, 0, wallTop + 3.55, 0);      // ridge beam
        // stone chimney + hearth smoke
        box(1.6, 6.4, 1.6, stone, W / 2 - 1.2, 3.2, -D / 2 + 1.6);
        box(2, 0.5, 2, stone, W / 2 - 1.2, 6.55, -D / 2 + 1.6);
        smoke(W / 2 - 1.2, 7.4, -D / 2 + 1.6);
        // door — timber frame, warm light spilling out + onto the ground
        box(2.4, 3.6, 0.4, logEnd, 0, 1.8, D / 2 + 0.15);
        pane(1.7, 3.1, 0, 1.65, D / 2 + 0.42);
        pool(3.2, 0, D / 2 + 2.6);
        // two framed windows on the front + one on each side, all warm
        for (const x of [-3.2, 3.2]) {
            box(1.9, 1.7, 0.3, logEnd, x, 2.6, D / 2 + 0.1);
            pane(1.4, 1.2, x, 2.6, D / 2 + 0.32);
        }
        box(0.3, 1.7, 1.9, logEnd, -W / 2 - 0.1, 2.6, 0);
        pane(1.4, 1.2, -W / 2 - 0.28, 2.6, 0, -Math.PI / 2, 0.9);
        // the round gable window — a record, lit from inside
        add(new THREE.Mesh(new THREE.CircleGeometry(0.85, 18), mat('#241b12')), 0, wallTop + 1.5, D / 2 + 0.34);
        add(new THREE.Mesh(new THREE.CircleGeometry(0.62, 18), glow(roles.light, 0.95)), 0, wallTop + 1.5, D / 2 + 0.36);
        add(new THREE.Mesh(new THREE.CircleGeometry(0.14, 10), mat('#241b12')), 0, wallTop + 1.5, D / 2 + 0.38);
        // the porch: deck, two posts, its own little sloped roof
        box(5.6, 0.4, 2.6, logB, 0, 0.25, D / 2 + 1.6);
        for (const x of [-2.4, 2.4]) cyl(0.16, 0.18, 3.4, 6, logEnd, x, 2, D / 2 + 2.6);
        const porch = box(6.2, 0.28, 3.2, roofM, 0, 3.9, D / 2 + 1.7);
        porch.rotation.x = 0.18;
        // a lantern on a porch post
        add(new THREE.Mesh(new THREE.SphereGeometry(0.2, 8, 6), glow(roles.light)), 2.4, 2.9, D / 2 + 2.6);
        // firewood stacked by the door + ferns at the corners
        for (let i = 0; i < 8; i++) {
            const l = cyl(0.16, 0.16, 1.4, 6, i % 2 ? logEnd : logA,
                -3.6 + (i % 4) * 0.36, 0.22 + Math.floor(i / 4) * 0.34, D / 2 + 1.3);
            l.rotation.x = Math.PI / 2;
        }
        const fern = mat('#33492c', { color: new THREE.Color(FOLIAGE) });
        for (let i = 0; i < 6; i++) {
            const a = rnd() * Math.PI * 2, r = 6.4 + rnd() * 1.6;
            add(new THREE.Mesh(new THREE.ConeGeometry(0.5, 1 + rnd(), 5), fern),
                Math.cos(a) * r, 0.5, Math.sin(a) * r);
        }
        return wallTop + 4.2;                                      // label above the ridge
    },

    boat() {
        const wm = new THREE.MeshStandardMaterial({ color: new THREE.Color(0x26363c),
            roughness: 0.22, metalness: 0.35, transparent: true, opacity: 0.92 });
        const wa = add(new THREE.Mesh(new THREE.CircleGeometry(8, 24), wm), 0, 0.1, 0);
        wa.rotation.x = -Math.PI / 2;
        water(wa);
        // hull: a pointed deck plan extruded downward
        const s = new THREE.Shape();
        s.moveTo(-3.4, -1.1); s.lineTo(2.2, -1.1); s.quadraticCurveTo(4.3, 0, 2.2, 1.1);
        s.lineTo(-3.4, 1.1); s.quadraticCurveTo(-4.1, 0, -3.4, -1.1);
        const hullGeo = new THREE.ExtrudeGeometry(s, { depth: 1.3, bevelEnabled: false });
        hullGeo.rotateX(Math.PI / 2);
        add(new THREE.Mesh(hullGeo, sMat), 0, 1.5, 0);
        cyl(0.1, 0.12, 6.4, 6, oMat, 0, 4.5, 0);                   // mast
        const sailS = new THREE.Shape();
        sailS.moveTo(0, 0); sailS.lineTo(2.6, 0); sailS.lineTo(0, 4.4); sailS.closePath();
        const sail = new THREE.Mesh(new THREE.ShapeGeometry(sailS),
            new THREE.MeshStandardMaterial({ color: 0xcfd4d2, roughness: 0.9,
                side: THREE.DoubleSide, transparent: true, opacity: 0.9 }));
        sail.position.set(0.15, 2.9, 0); g.add(sail);
        pane(0.34, 0.34, 1.2, 1.05, 1.12); pane(0.34, 0.34, -0.4, 1.05, 1.12);  // portholes
        return 7.8;
    },

    kitchen() {
        // the 3am kitchen: an open-fronted room, lamp over the table
        box(10, 0.5, 8, sDark, 0, 0.25, 0);                        // floor slab
        box(10, 6, 0.5, sMat, 0, 3.25, -3.75);                     // back wall
        box(0.5, 6, 8, sMat, -4.75, 3.25, 0);                      // side walls
        box(0.5, 6, 8, sMat, 4.75, 3.25, 0);
        box(10.6, 0.6, 8.6, sDark, 0, 6.4, 0);                     // flat roof
        pane(2, 1.5, 2.2, 3.6, -3.49, 0, 0.5);                     // window on the back wall
        // hanging lamp
        cyl(0.04, 0.04, 1.6, 4, oMat, 0, 5.6, 0);
        add(new THREE.Mesh(new THREE.ConeGeometry(0.8, 0.7, 8), sDark), 0, 4.7, 0);
        add(new THREE.Mesh(new THREE.SphereGeometry(0.22, 8, 6), glow(roles.light)), 0, 4.35, 0);
        // table + light falling on it
        box(3.6, 0.25, 2.2, oMat, 0, 2.1, 0);
        [[-1.5, -0.85], [1.5, -0.85], [-1.5, 0.85], [1.5, 0.85]].forEach(([x, z]) =>
            box(0.18, 2, 0.18, oMat, x, 1, z));
        const spot = add(new THREE.Mesh(new THREE.CircleGeometry(1.7, 14), glow(roles.light, 0.3)), 0, 2.24, 0);
        spot.rotation.x = -Math.PI / 2;
        person(-2.9, 1.4, 0.92, 0.8); person(2.7, 1.7, 0.9, -0.9);
        pool(3, 0, 5.4, 0.1);
        return 7;
    },

    rooftop() {
        box(8, 15, 8, sMat, 0, 7.5, 0);
        box(8.7, 0.8, 8.7, sDark, 0, 15.3, 0);                     // parapet
        // a few lit windows below
        for (let fy = 0; fy < 4; fy++) if (rnd() < 0.5)
            pane(1.1, 1.3, -2 + rnd() * 4, 3 + fy * 3, 4.02);
        // roof: stair hut with a lit door + string of lights between two posts
        box(2.2, 2.2, 2.2, sDark, -2.2, 16.8, -2.2);
        pane(0.9, 1.5, -2.2, 16.5, -1.08);
        cyl(0.07, 0.07, 2.6, 5, oMat, -3, 17, 3); cyl(0.07, 0.07, 2.6, 5, oMat, 3.4, 17, 2);
        for (let i = 0; i < 6; i++) {
            const t = i / 5, sag = Math.sin(t * Math.PI) * 0.7;
            add(new THREE.Mesh(new THREE.SphereGeometry(0.13, 6, 5), glow(roles.light)),
                -3 + t * 6.4, 18.2 - sag, 3 - t * 1);
        }
        // two people up on the roof
        person(0.6, 0.8, 0.9, 0.3).position.y = 15.7;
        person(1.8, -0.6, 0.9, -2.4).position.y = 15.7;
        return 19;
    },

    cave() {
        const rock = mat('#5a5a52', { color: new THREE.Color(0x55524a) });
        const m1 = add(new THREE.Mesh(new THREE.IcosahedronGeometry(6, 1), rock), 0, 1.8, -1);
        m1.scale.set(1.35, 0.85, 1);
        const m2 = add(new THREE.Mesh(new THREE.IcosahedronGeometry(3.4, 1), rock), -5.4, 1, 0.6);
        m2.scale.set(1, 0.7, 0.9);
        const m3 = add(new THREE.Mesh(new THREE.IcosahedronGeometry(3, 1), rock), 5.2, 0.8, 0.4);
        m3.scale.set(1, 0.65, 0.9);
        // the mouth: dark arch with a warm glow deeper in
        const mouth = add(new THREE.Mesh(new THREE.CircleGeometry(2.6, 14, 0, Math.PI),
            new THREE.MeshBasicMaterial({ color: 0x070605 })), 0, 0.12, 3.9);
        const inner = add(new THREE.Mesh(new THREE.CircleGeometry(1.7, 12, 0, Math.PI), glow(roles.light, 0.5)), 0, 0.1, 3.55);
        pool(3, 0, 5.6, 0.1);
        return 7.4;
    },

    headphones() {
        // a resting sculpture: band arc + two cups, pads glowing
        const band = add(new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.42, 8, 22, Math.PI), oMat), 0, 3.4, 0);
        const cupM = sMat;
        [[-3.2, 1], [3.2, -1]].forEach(([x, dir]) => {
            const cup = cyl(1.5, 1.5, 1.2, 12, cupM, x * 1.02, 3.2, 0);
            cup.rotation.z = Math.PI / 2;
            const pad = add(new THREE.Mesh(new THREE.CircleGeometry(1.15, 12), glow(roles.light, 0.85)),
                x * 1.02 + 0.62 * -Math.sign(x), 3.2, 0);
            pad.rotation.y = -Math.sign(x) * Math.PI / 2;
        });
        pool(2.8, 0, 0, 0.1);
        return 7.2;
    },

    default() {
        // the lantern on a post — the quiet placeholder
        cyl(0.16, 0.22, 5.4, 6, sMat, 0, 2.7, 0);
        box(1.5, 1.6, 1.5, sDark, 0, 5.9, 0);
        pane(1, 1.1, 0, 5.9, 0.78); pane(1, 1.1, 0, 5.9, -0.78, Math.PI);
        pane(1, 1.1, 0.78, 5.9, 0, Math.PI / 2); pane(1, 1.1, -0.78, 5.9, 0, -Math.PI / 2);
        add(new THREE.Mesh(new THREE.ConeGeometry(1.3, 0.9, 4), sDark), 0, 7.15, 0);
        pool(2.8, 0, 0);
        return 7.6;
    },

    };

    const builder = K[kind] || K.default;
    const h = builder() || 8;
    g.userData.pid = p.id;
    g.userData.h = h;
    return g;
},

};
})();
