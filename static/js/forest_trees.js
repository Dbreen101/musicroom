// =============================================================
// FOREST TREES — an old-Irish-woodland kit, drawn 3/4 / side-on
// so the forest reads from ~45° (trunks, branches, layered crowns,
// cast shadows) instead of top-down.
//
// Design notes
// ------------
// • Every "stamp" is anchored at its GROUND point (x, y) and grows
//   UPWARD (−y). It returns { shadow, body } so the compositor can lay
//   all shadows on the floor first, then paint bodies back-to-front
//   (painter's algorithm) for real depth.
// • No per-element filters. Soft shadows come from ONE shared radial
//   gradient; volume comes from layered blobs + a light-side highlight
//   and a shade-side darken. Cheap enough for a heavily-packed wood.
// • Atmospheric perspective: the compositor passes `haze` 0→1 (far) and
//   we mix colours toward the sky's mist tint + drop detail. Distant
//   trees go pale, cool and simple; near trees are saturated + detailed.
// • Species + size + lean + colour + crown fullness all jitter, so no
//   two trees read the same.
//
// Native Irish species included: sessile/pedunculate oak (the king of
// the wood), ash, silver birch, Scots pine (our only native conifer),
// holly, rowan, hawthorn (the lone "fairy tree"), hazel.
// =============================================================
(function () {
    'use strict';

    // ---- number + colour helpers -------------------------------------
    const f = (n) => (Math.round(n * 10) / 10);
    function _clamp8(n) { return Math.max(0, Math.min(255, Math.round(n))); }
    function hexToRgb(h) {
        h = h.replace('#', '');
        if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
        return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
    }
    function rgbToHex(r,g,b) {
        const x = (n) => _clamp8(n).toString(16).padStart(2,'0');
        return `#${x(r)}${x(g)}${x(b)}`;
    }
    // mix hex a→b by t (0..1)
    function mix(a, b, t) {
        const A = hexToRgb(a), B = hexToRgb(b);
        return rgbToHex(A[0]+(B[0]-A[0])*t, A[1]+(B[1]-A[1])*t, A[2]+(B[2]-A[2])*t);
    }
    // lighten (+) / darken (−) by amt (0..1)
    function shade(hex, amt) {
        return amt >= 0 ? mix(hex, '#ffffff', amt) : mix(hex, '#000000', -amt);
    }
    // small per-tree colour wobble so a stand never looks uniform
    function wobble(hex, rand, amt) {
        const d = (rand() - 0.5) * 2 * amt;
        return shade(hex, d);
    }
    // apply atmospheric haze: pull toward mist, lift lightness, lose punch
    function hazed(hex, haze, mistHex) {
        if (haze <= 0) return hex;
        return mix(hex, mistHex, haze * 0.85);
    }

    // ---- species palettes (Irish woodland) ---------------------------
    // dk = shade side, mid = body, lt = light side, hi = sun highlight
    const SPECIES = {
        oak:       { kind:'broad', dk:'#2c4424', mid:'#3d5a30', lt:'#557c40', hi:'#739353',
                     bark:'#4a3f31', barkLt:'#6a5b46', crown:1.06, fat:1.18, berry:null },
        ash:       { kind:'broad', dk:'#3a5232', mid:'#4f6b3e', lt:'#6a8a52', hi:'#86a268',
                     bark:'#564f44', barkLt:'#736a5b', crown:1.12, fat:0.86, berry:null },
        birch:     { kind:'birch', dk:'#5f7e44', mid:'#7aa256', lt:'#94ba6e', hi:'#b6d088',
                     bark:'#d9ddca', barkLt:'#eef0e4', crown:0.96, fat:0.74, berry:null },
        scotspine: { kind:'pine',  dk:'#274037', mid:'#33503f', lt:'#456a52', hi:'#5d8068',
                     bark:'#6e4a31', barkLt:'#8a6442', crown:0.9,  fat:0.8,  berry:null },
        holly:     { kind:'broad', dk:'#1f3a23', mid:'#2a4a2c', lt:'#3a5d3b', hi:'#4e7050',
                     bark:'#463b30', barkLt:'#5e5141', crown:0.8,  fat:1.05, berry:'#b3302a' },
        rowan:     { kind:'broad', dk:'#46603c', mid:'#56754a', lt:'#6c8b58', hi:'#88a06c',
                     bark:'#5a5044', barkLt:'#776a59', crown:0.92, fat:0.82, berry:'#d2641f' },
        hawthorn:  { kind:'twist', dk:'#3e5a30', mid:'#4f6b3a', lt:'#65824c', hi:'#839a5e',
                     bark:'#534838', barkLt:'#6f6150', crown:0.84, fat:1.0,  berry:'#c23a2a' },
        hazel:     { kind:'multi', dk:'#4a6638', mid:'#5f7d46', lt:'#789a5a', hi:'#94b272',
                     bark:'#5c4a36', barkLt:'#7a6446', crown:0.86, fat:1.0,  berry:null },
    };
    const SPECIES_WEIGHTS = [
        ['oak',30], ['birch',15], ['ash',13], ['hazel',10],
        ['holly',9], ['scotspine',9], ['rowan',8], ['hawthorn',6],
    ];
    const _wTotal = SPECIES_WEIGHTS.reduce((s, w) => s + w[1], 0);
    function pickSpecies(rand) {
        let r = rand() * _wTotal;
        for (const [k, w] of SPECIES_WEIGHTS) { if ((r -= w) <= 0) return k; }
        return 'oak';
    }

    // ---- shared primitives -------------------------------------------

    // Soft cast shadow on the floor, stretched away from the light.
    // Single SVG node (transform baked onto the ellipse) — at thousands of
    // stamps, shaving the wrapper <g> matters.
    function groundShadow(x, y, w, ctx, haze) {
        const L = ctx.light;
        const len = w * (L.len) * (1 - haze * 0.3);
        const rx = Math.max(6, w * 0.5);
        const ry = Math.max(2.5, w * 0.16);
        const cx = x + L.dx * len * 0.5;
        const cy = y + L.dy * len * 0.28 + ry * 0.2;
        const ang = Math.atan2(L.dy, L.dx) * 180 / Math.PI;
        const sx = 1 + len / Math.max(8, rx) * 0.5;
        const op = (L.alpha * (1 - haze * 0.5)).toFixed(3);
        return `<ellipse cx="0" cy="0" rx="${f(rx*sx)}" ry="${f(ry)}" fill="url(#ft-shadow)" opacity="${op}" transform="translate(${f(cx)} ${f(cy)}) rotate(${f(ang)})"/>`;
    }

    // Tapered, slightly-curved, slightly-leaning trunk (dark body + lit sliver).
    function trunkPath(x, y, h, w, lean, dk, lt) {
        const topX = x + lean, topY = y - h;
        const hb = w / 2, ht = w * 0.34 / 2;
        const body = `M ${f(x-hb)} ${f(y)} `
                   + `C ${f(x-hb*0.92)} ${f(y-h*0.42)}, ${f(topX-ht*1.3)} ${f(topY+h*0.34)}, ${f(topX-ht)} ${f(topY)} `
                   + `L ${f(topX+ht)} ${f(topY)} `
                   + `C ${f(x+hb*0.92)} ${f(y-h*0.42)}, ${f(x+hb*0.6)} ${f(y-h*0.2)}, ${f(x+hb)} ${f(y)} Z`;
        // lit sliver down the light-facing (left) side
        const sliv = `M ${f(x-hb)} ${f(y)} `
                   + `C ${f(x-hb*0.92)} ${f(y-h*0.42)}, ${f(topX-ht*1.3)} ${f(topY+h*0.34)}, ${f(topX-ht)} ${f(topY)} `
                   + `L ${f(topX-ht*0.2)} ${f(topY)} `
                   + `C ${f(x-hb*0.1)} ${f(y-h*0.4)}, ${f(x-hb*0.35)} ${f(y-h*0.15)}, ${f(x-hb*0.45)} ${f(y)} Z`;
        return `<path d="${body}" fill="${dk}"/><path d="${sliv}" fill="${lt}"/>`;
    }

    function ell(cx, cy, rx, ry, fill) {
        return `<ellipse cx="${f(cx)}" cy="${f(cy)}" rx="${f(rx)}" ry="${f(ry)}" fill="${fill}"/>`;
    }

    // A lobed "cloud" silhouette — the building block of foliage drawn the
    // way an illustrator does it (scalloped clumps), NOT a stack of concentric
    // ellipses (which read as a flat top-down "bullseye"). Walks a ring of
    // points and joins them with outward arcs so the outline bulges into
    // leaf-lobes. squash<1 flattens it; jit varies lobe reach. Returns `d`.
    function cloudPath(cx, cy, r, lobes, rand, squash, jit) {
        squash = squash == null ? 0.9 : squash;
        jit = jit == null ? 0.32 : jit;
        const N = Math.max(5, lobes | 0);
        const pts = [];
        for (let i = 0; i < N; i++) {
            const a = (i / N) * Math.PI * 2 - Math.PI / 2;
            const rad = r * (1 - jit * 0.5 + rand() * jit);
            pts.push([cx + Math.cos(a) * rad, cy + Math.sin(a) * rad * squash, rad]);
        }
        let d = `M ${f(pts[0][0])} ${f(pts[0][1])} `;
        for (let i = 0; i < N; i++) {
            const nxt = pts[(i + 1) % N];
            const lr = (pts[i][2] + nxt[2]) * 0.5 * 0.62;
            d += `A ${f(lr)} ${f(lr)} 0 0 1 ${f(nxt[0])} ${f(nxt[1])} `;
        }
        return d + 'Z';
    }

    // A broadleaf crown as layered foliage masses lit from the upper-left:
    // a dark back mass, a mid mass nudged toward the light, a lighter mass
    // nudged further, and (near only) sun-struck top-left lobes. Each layer
    // is its own lobed silhouette — no concentric rings.
    function broadCrown(cx, cy, r, sp, rand, ctx, haze, fat) {
        const nx = -ctx.light.dx, ny = -Math.abs(ctx.light.dy);   // toward the light
        const dk = hazed(wobble(sp.dk, rand, 0.04), haze, ctx.mistHex);
        const md = hazed(wobble(sp.mid, rand, 0.04), haze, ctx.mistHex);
        const lt = hazed(wobble(sp.lt, rand, 0.04), haze, ctx.mistHex);
        const hi = hazed(sp.hi, haze, ctx.mistHex);
        const lobes = 7 + Math.floor(rand() * 4);
        let s = '';
        s += `<path d="${cloudPath(cx, cy, r * fat, lobes, rand, 0.9, 0.34)}" fill="${dk}"/>`;
        s += `<path d="${cloudPath(cx + nx*r*0.12, cy + ny*r*0.12, r*fat*0.84, lobes, rand, 0.9, 0.34)}" fill="${md}"/>`;
        if (haze < 0.5)
            s += `<path d="${cloudPath(cx + nx*r*0.28, cy + ny*r*0.26, r*fat*0.56, lobes-1, rand, 0.88, 0.32)}" fill="${lt}"/>`;
        if (haze < 0.35)
            s += `<path d="${cloudPath(cx + nx*r*0.42, cy + ny*r*0.4, r*fat*0.3, 5, rand, 0.85, 0.4)}" fill="${hi}"/>`;
        // berries / haws for the species that carry them (near trees only)
        if (sp.berry && haze < 0.3) {
            const bcol = hazed(sp.berry, haze, ctx.mistHex);
            const clusters = 2 + Math.floor(rand()*2);
            for (let c = 0; c < clusters; c++) {
                const a = rand() * Math.PI * 2;
                const bx = cx + Math.cos(a) * r * 0.66;
                const by = cy + Math.abs(Math.sin(a)) * r * 0.46 + r*0.12;
                for (let k = 0; k < 3; k++)
                    s += `<circle cx="${f(bx+(rand()-0.5)*r*0.18)}" cy="${f(by+(rand()-0.5)*r*0.18)}" r="${f(r*0.052)}" fill="${bcol}"/>`;
            }
        }
        return s;
    }

    // ---- the tree (dispatch by species + LOD) ------------------------
    // x,y = ground anchor; h = total height (px); ctx = scene lighting.
    function tree(x, y, h, rand, ctx) {
        const key = ctx.species || pickSpecies(rand);
        const sp  = SPECIES[key] || SPECIES.oak;
        const haze = Math.max(0, Math.min(1, ctx.haze || 0));

        // FAR-DISTANCE LOD: through mist the far treeline reads as a soft
        // blue-grey mass — no visible trunks. So the densest (far) band is
        // nearly free: 2 hazed blobs + a faint shadow. This is the key trick
        // for "heavily populated" without the node cost.
        if (haze > 0.62) {
            const r = h * 0.34 * sp.crown;
            const cx = x + (rand() - 0.5) * h * 0.04, cy = y - h * 0.45;
            const dk = hazed(sp.dk, haze, ctx.mistHex);
            const md = hazed(sp.mid, haze, ctx.mistHex);
            const body = `<path d="${cloudPath(cx, cy + r*0.15, r*sp.fat, 7, rand, 0.92, 0.3)}" fill="${dk}"/>`
                       + `<path d="${cloudPath(cx - r*0.16, cy - r*0.06, r*0.58, 6, rand, 0.9, 0.3)}" fill="${md}"/>`;
            const op = (ctx.light.alpha * 0.4).toFixed(3);
            const shadow = `<ellipse cx="${f(x)}" cy="${f(y)}" rx="${f(r*0.7)}" ry="${f(r*0.16)}" fill="url(#ft-shadow)" opacity="${op}"/>`;
            return { shadow, body, y };
        }

        const flip = rand() < 0.5 ? -1 : 1;
        const lean = (rand() - 0.5) * h * 0.06 * flip;
        const crownW = h * 0.7;
        const shadow = groundShadow(x, y, crownW * sp.fat, ctx, haze);

        const bark   = hazed(wobble(sp.bark,   rand, 0.05), haze, ctx.mistHex);
        const barkLt = hazed(sp.barkLt, haze, ctx.mistHex);
        let body = '';

        if (sp.kind === 'pine') {
            // Scots pine: tall bare rusty trunk, dark blue-green layered tufts up top
            const th = h * 0.62, tw = h * 0.05;
            body += trunkPath(x, y, th, tw, lean, bark, barkLt);
            const topX = x + lean, topY = y - th;
            const layers = haze > 0.5 ? 2 : 4;
            const dk = hazed(sp.dk, haze, ctx.mistHex);
            const md = hazed(sp.mid, haze, ctx.mistHex);
            const lt = hazed(sp.lt, haze, ctx.mistHex);
            for (let i = 0; i < layers; i++) {
                const t = i / (layers - 1 || 1);
                const ly2 = topY - h * (0.30 + t * 0.30);
                const lw = h * (0.34 - t * 0.22) * sp.fat;
                // each tier = a flattened, downward-drooping lobed fan
                body += `<path d="${cloudPath(topX - lw*0.1, ly2, lw, 6, rand, 0.42, 0.5)}" fill="${dk}"/>`;
                body += `<path d="${cloudPath(topX - lw*0.18, ly2 - h*0.012, lw*0.8, 6, rand, 0.4, 0.5)}" fill="${md}"/>`;
                if (haze < 0.5) body += `<path d="${cloudPath(topX - lw*0.3, ly2 - h*0.02, lw*0.46, 5, rand, 0.4, 0.5)}" fill="${lt}"/>`;
            }
            // a crowning tuft
            body += `<path d="${cloudPath(topX, topY - h*0.62, h*0.09*sp.fat, 5, rand, 0.7, 0.4)}" fill="${md}"/>`;
        } else if (sp.kind === 'multi') {
            // hazel: 2–3 thin stems splaying from the base into one rounded crown
            const stems = 2 + Math.floor(rand()*2);
            const th = h * 0.5;
            for (let i = 0; i < stems; i++) {
                const sx = (i - (stems-1)/2) * h*0.05;
                body += trunkPath(x + sx*0.3, y, th*(0.85+rand()*0.2), h*0.03, sx + lean, bark, barkLt);
            }
            const r = h * 0.34 * sp.crown;
            body += broadCrown(x + lean, y - th - r*0.3, r, sp, rand, ctx, haze, sp.fat);
        } else if (sp.kind === 'birch') {
            // silver birch: pale slender leaning trunk w/ dark marks, airy crown
            const th = h * 0.6, tw = h * 0.035;
            body += trunkPath(x, y, th, tw, lean, bark, shade(bark, 0.12));
            if (haze < 0.5) {
                const topX = x + lean;
                for (let i = 0; i < 4; i++) {
                    const my = y - th * (0.2 + i*0.18);
                    const mw = tw * (0.7 - i*0.05) * 0.5 * (h/100);
                    body += `<rect x="${f(topX - mw)}" y="${f(my)}" width="${f(mw*1.6)}" height="${f(h*0.012)}" fill="${hazed('#3a3a32',haze,ctx.mistHex)}" rx="${f(h*0.006)}"/>`;
                }
            }
            // airy, upright birch crown — taller lobed silhouette, light up-left
            const r = h * 0.34 * sp.crown;
            const cx = x + lean, cy = y - th - r*0.1;
            const md = hazed(sp.mid, haze, ctx.mistHex), lt = hazed(sp.lt, haze, ctx.mistHex), hi = hazed(sp.hi, haze, ctx.mistHex);
            const dkb = hazed(sp.dk, haze, ctx.mistHex);
            body += `<path d="${cloudPath(cx, cy, r*0.82*sp.fat, 8, rand, 1.12, 0.42)}" fill="${dkb}"/>`;
            body += `<path d="${cloudPath(cx - r*0.1, cy - r*0.1, r*0.6*sp.fat, 7, rand, 1.1, 0.42)}" fill="${md}"/>`;
            if (haze < 0.5) body += `<path d="${cloudPath(cx - r*0.22, cy - r*0.22, r*0.4*sp.fat, 6, rand, 1.05, 0.4)}" fill="${lt}"/>`;
            if (haze < 0.4) body += `<path d="${cloudPath(cx - r*0.32, cy - r*0.32, r*0.22, 5, rand, 1.0, 0.4)}" fill="${hi}"/>`;
        } else if (sp.kind === 'twist') {
            // hawthorn: low twisted trunk, broad low crown, red haws / pale blossom
            const th = h * 0.36, tw = h * 0.06;
            const twist = lean + (rand()-0.5)*h*0.08;
            body += trunkPath(x, y, th, tw, twist, bark, barkLt);
            const r = h * 0.36 * sp.crown;
            body += broadCrown(x + twist, y - th - r*0.2, r * 1.1, sp, rand, ctx, haze, sp.fat * 1.15);
        } else {
            // broadleaf default: oak / ash / holly / rowan
            const th = h * (key === 'oak' ? 0.42 : 0.5);
            const tw = h * (key === 'oak' ? 0.07 : 0.05);
            body += trunkPath(x, y, th, tw, lean, bark, barkLt);
            // a couple of suggested branches reaching into the crown (near LOD)
            if (haze < 0.4) {
                const topX = x + lean, topY = y - th;
                for (let i = 0; i < 2; i++) {
                    const dir = i === 0 ? -1 : 1;
                    body += `<path d="M ${f(topX)} ${f(topY+th*0.15)} Q ${f(topX+dir*h*0.12)} ${f(topY-h*0.02)}, ${f(topX+dir*h*0.18)} ${f(topY-h*0.12)}" stroke="${bark}" stroke-width="${f(tw*0.35)}" fill="none" stroke-linecap="round"/>`;
                }
            }
            const r = h * 0.36 * sp.crown;
            body += broadCrown(x + lean, y - th - r*0.32, r, sp, rand, ctx, haze, sp.fat);
        }
        return { shadow, body, y };
    }

    // ---- undergrowth (forest floor detail) ---------------------------
    function fern(x, y, s, rand, ctx, haze) {
        const g1 = hazed('#3f5a30', haze, ctx.mistHex);
        const g2 = hazed('#56773c', haze, ctx.mistHex);
        const blades = 5 + Math.floor(rand()*3);
        let b = '';
        for (let i = 0; i < blades; i++) {
            const a = (-Math.PI/2) + (i - (blades-1)/2) * 0.34 + (rand()-0.5)*0.1;
            const len = s * (0.7 + rand()*0.5);
            const ex = x + Math.cos(a)*len, ey = y + Math.sin(a)*len;
            const mx = x + Math.cos(a)*len*0.5 + (rand()-0.5)*s*0.2;
            const my = y + Math.sin(a)*len*0.5;
            b += `<path d="M ${f(x)} ${f(y)} Q ${f(mx)} ${f(my)}, ${f(ex)} ${f(ey)}" stroke="${i%2?g2:g1}" stroke-width="${f(s*0.09)}" fill="none" stroke-linecap="round"/>`;
        }
        const shadow = `<ellipse cx="${f(x)}" cy="${f(y+s*0.05)}" rx="${f(s*0.5)}" ry="${f(s*0.12)}" fill="url(#ft-shadow)" opacity="${(ctx.light.alpha*0.6*(1-haze*0.5)).toFixed(3)}"/>`;
        return { shadow, body: b, y };
    }
    function grass(x, y, s, rand, ctx, haze) {
        const g = hazed('#5b7a40', haze, ctx.mistHex);
        let b = '';
        const n = 3 + Math.floor(rand()*3);
        for (let i = 0; i < n; i++) {
            const a = -Math.PI/2 + (rand()-0.5)*0.7;
            const len = s*(0.6+rand()*0.5);
            b += `<path d="M ${f(x+(rand()-0.5)*s*0.4)} ${f(y)} q ${f(Math.cos(a)*len*0.3)} ${f(-len*0.5)}, ${f(Math.cos(a)*len)} ${f(-len)}" stroke="${g}" stroke-width="${f(s*0.06)}" fill="none" stroke-linecap="round"/>`;
        }
        return { shadow:'', body:b, y };
    }
    function rock(x, y, s, rand, ctx, haze) {
        const base = hazed(wobble('#6f6e63', rand, 0.06), haze, ctx.mistHex);
        const moss = hazed('#4a6338', haze, ctx.mistHex);
        const body = ell(x, y - s*0.25, s*0.6, s*0.42, base)
                   + ell(x - s*0.18, y - s*0.42, s*0.34, s*0.26, shade(base,0.14))
                   + ell(x + s*0.1, y - s*0.12, s*0.5, s*0.22, moss);
        const shadow = `<ellipse cx="${f(x+s*0.15)}" cy="${f(y+s*0.04)}" rx="${f(s*0.6)}" ry="${f(s*0.16)}" fill="url(#ft-shadow)" opacity="${(ctx.light.alpha*(1-haze*0.5)).toFixed(3)}"/>`;
        return { shadow, body, y };
    }
    function log(x, y, s, rand, ctx, haze) {
        const bark = hazed('#5a4632', haze, ctx.mistHex);
        const ring = hazed('#7d6a4f', haze, ctx.mistHex);
        const w = s*1.4, h = s*0.34;
        const body = `<rect x="${f(x-w/2)}" y="${f(y-h)}" width="${f(w)}" height="${f(h)}" rx="${f(h/2)}" fill="${bark}"/>`
                   + ell(x-w/2, y-h/2, h*0.34, h*0.46, ring)
                   + ell(x+w/2, y-h/2, h*0.3, h*0.42, shade(bark,-0.12))
                   + `<rect x="${f(x-w/2)}" y="${f(y-h)}" width="${f(w)}" height="${f(h*0.34)}" rx="${f(h*0.17)}" fill="${shade(bark,0.1)}" opacity="0.5"/>`;
        const shadow = `<ellipse cx="${f(x+s*0.2)}" cy="${f(y+s*0.03)}" rx="${f(w*0.6)}" ry="${f(h*0.5)}" fill="url(#ft-shadow)" opacity="${(ctx.light.alpha*(1-haze*0.5)).toFixed(3)}"/>`;
        return { shadow, body, y };
    }
    function mushrooms(x, y, s, rand, ctx, haze) {
        const cap = hazed(rand() < 0.5 ? '#b0492e' : '#c98a3a', haze, ctx.mistHex);
        const stem = hazed('#e6ddc8', haze, ctx.mistHex);
        let b = '';
        const n = 2 + Math.floor(rand()*2);
        for (let i = 0; i < n; i++) {
            const mx = x + (i - (n-1)/2) * s*0.5, sc = s*(0.6+rand()*0.5);
            b += `<rect x="${f(mx-sc*0.08)}" y="${f(y-sc*0.4)}" width="${f(sc*0.16)}" height="${f(sc*0.4)}" rx="${f(sc*0.06)}" fill="${stem}"/>`;
            b += `<path d="M ${f(mx-sc*0.3)} ${f(y-sc*0.36)} a ${f(sc*0.3)} ${f(sc*0.26)} 0 0 1 ${f(sc*0.6)} 0 Z" fill="${cap}"/>`;
            if (haze < 0.4) b += `<circle cx="${f(mx-sc*0.08)}" cy="${f(y-sc*0.44)}" r="${f(sc*0.04)}" fill="#f3ead2"/>`;
        }
        return { shadow:'', body:b, y };
    }
    function bluebells(x, y, s, rand, ctx, haze) {
        // Irish woodland in spring — a carpet of bluebells. A little surreal joy.
        const col = hazed('#5a5ab0', haze, ctx.mistHex);
        const stem = hazed('#4a6338', haze, ctx.mistHex);
        let b = '';
        const n = 4 + Math.floor(rand()*4);
        for (let i = 0; i < n; i++) {
            const bx = x + (rand()-0.5)*s*1.6, by = y - rand()*s*0.2, hh = s*(0.5+rand()*0.4);
            b += `<path d="M ${f(bx)} ${f(by)} q ${f(s*0.1)} ${f(-hh*0.6)}, ${f(s*0.02)} ${f(-hh)}" stroke="${stem}" stroke-width="${f(s*0.05)}" fill="none"/>`;
            for (let k = 0; k < 3; k++)
                b += `<circle cx="${f(bx+s*0.02+(rand()-0.5)*s*0.1)}" cy="${f(by-hh*(0.6+k*0.15))}" r="${f(s*0.07)}" fill="${k%2?shade(col,0.12):col}"/>`;
        }
        return { shadow:'', body:b, y };
    }
    function stump(x, y, s, rand, ctx, haze) {
        const bark = hazed('#5a4836', haze, ctx.mistHex);
        const top  = hazed('#8a7355', haze, ctx.mistHex);
        const body = `<path d="M ${f(x-s*0.4)} ${f(y)} L ${f(x-s*0.34)} ${f(y-s*0.5)} L ${f(x+s*0.34)} ${f(y-s*0.5)} L ${f(x+s*0.4)} ${f(y)} Z" fill="${bark}"/>`
                   + ell(x, y-s*0.5, s*0.34, s*0.12, top)
                   + ell(x, y-s*0.5, s*0.18, s*0.06, shade(top,-0.15));
        const shadow = `<ellipse cx="${f(x+s*0.15)}" cy="${f(y+s*0.02)}" rx="${f(s*0.5)}" ry="${f(s*0.13)}" fill="url(#ft-shadow)" opacity="${(ctx.light.alpha*(1-haze*0.5)).toFixed(3)}"/>`;
        return { shadow, body, y };
    }

    // ---- critters (Irish birds + woodland animals) -------------------
    // Drawn small + recognisable by silhouette and one colour note.
    const CRITTERS = [
        ['robin',5], ['wren',5], ['blackbird',4], ['chaffinch',3],
        ['fox',3], ['redsquirrel',4], ['deer',2], ['hedgehog',3], ['badger',2], ['hare',3],
    ];
    const _cTotal = CRITTERS.reduce((s, c) => s + c[1], 0);
    function pickCritter(rand) {
        let r = rand() * _cTotal;
        for (const [k, w] of CRITTERS) { if ((r -= w) <= 0) return k; }
        return 'robin';
    }
    function critter(kind, x, y, s, rand, ctx, haze) {
        kind = kind || pickCritter(rand);
        const flip = rand() < 0.5 ? -1 : 1;
        const dark = hazed('#2a2620', haze, ctx.mistHex);
        const op = (ctx.light.alpha*0.9*(1-haze*0.4)).toFixed(3);
        const sh = `<ellipse cx="${f(x+s*0.1)}" cy="${f(y+s*0.04)}" rx="${f(s*0.55)}" ry="${f(s*0.13)}" fill="url(#ft-shadow)" opacity="${op}"/>`;
        let b = `<g transform="translate(${f(x)} ${f(y)}) scale(${flip} 1)">`;
        const c = (col) => hazed(col, haze, ctx.mistHex);
        switch (kind) {
            case 'robin':
                b += ell(0, -s*0.55, s*0.34, s*0.4, c('#6b5a44'))
                   + ell(s*0.18, -s*0.62, s*0.2, s*0.24, c('#c4502a'))   // red breast
                   + `<circle cx="${f(s*0.28)}" cy="${f(-s*0.92)}" r="${f(s*0.18)}" fill="${c('#6b5a44')}"/>`
                   + `<circle cx="${f(s*0.34)}" cy="${f(-s*0.95)}" r="${f(s*0.03)}" fill="#1a1a16"/>`
                   + `<path d="M ${f(s*0.4)} ${f(-s*0.9)} l ${f(s*0.16)} ${f(s*0.02)} l ${f(-s*0.14)} ${f(s*0.06)} Z" fill="${c('#caa24a')}"/>` // beak
                   + `<path d="M ${f(-s*0.3)} ${f(-s*0.5)} l ${f(-s*0.3)} ${f(s*0.1)} l ${f(s*0.05)} ${f(-s*0.22)} Z" fill="${c('#5a4a36')}"/>`; // tail
                break;
            case 'wren':
                b += ell(0, -s*0.4, s*0.26, s*0.3, c('#7a5a3a'))
                   + `<circle cx="${f(s*0.16)}" cy="${f(-s*0.6)}" r="${f(s*0.14)}" fill="${c('#7a5a3a')}"/>`
                   + `<circle cx="${f(s*0.22)}" cy="${f(-s*0.63)}" r="${f(s*0.025)}" fill="#15130f"/>`
                   + `<path d="M ${f(-s*0.18)} ${f(-s*0.4)} l ${f(-s*0.05)} ${f(-s*0.34)} l ${f(s*0.14)} ${f(s*0.1)} Z" fill="${c('#6a4a2e')}"/>`; // cocked tail
                break;
            case 'blackbird':
                b += ell(0, -s*0.5, s*0.36, s*0.4, dark)
                   + `<circle cx="${f(s*0.2)}" cy="${f(-s*0.82)}" r="${f(s*0.17)}" fill="${dark}"/>`
                   + `<path d="M ${f(s*0.32)} ${f(-s*0.82)} l ${f(s*0.16)} ${f(s*0.02)} l ${f(-s*0.14)} ${f(s*0.06)} Z" fill="${c('#e0a128')}"/>` // orange beak
                   + `<path d="M ${f(-s*0.34)} ${f(-s*0.44)} l ${f(-s*0.34)} ${f(s*0.14)} l ${f(s*0.06)} ${f(-s*0.26)} Z" fill="${dark}"/>`;
                break;
            case 'chaffinch':
                b += ell(0, -s*0.48, s*0.32, s*0.36, c('#9a6a4a'))
                   + ell(s*0.16, -s*0.55, s*0.18, s*0.2, c('#b98a5a'))
                   + `<circle cx="${f(s*0.2)}" cy="${f(-s*0.78)}" r="${f(s*0.16)}" fill="${c('#6a7fa0')}"/>`
                   + `<path d="M ${f(-s*0.3)} ${f(-s*0.42)} l ${f(-s*0.28)} ${f(s*0.12)} l ${f(s*0.05)} ${f(-s*0.22)} Z" fill="${c('#5a4636')}"/>`;
                break;
            case 'fox':
                b += `<path d="M ${f(-s*0.7)} ${f(0)} q ${f(-s*0.5)} ${f(-s*0.1)}, ${f(-s*0.55)} ${f(-s*0.5)} q ${f(s*0.2)} ${f(s*0.1)}, ${f(s*0.4)} ${f(s*0.05)} Z" fill="${c('#b85a26')}"/>` // tail
                   + ell(0, -s*0.4, s*0.6, s*0.34, c('#c4641f'))             // body
                   + ell(s*0.55, -s*0.6, s*0.22, s*0.22, c('#c4641f'))        // head
                   + `<path d="M ${f(s*0.42)} ${f(-s*0.78)} l ${f(s*0.06)} ${f(-s*0.18)} l ${f(s*0.12)} ${f(s*0.1)} Z" fill="${c('#9a4818')}"/>` // ear
                   + `<path d="M ${f(s*0.62)} ${f(-s*0.78)} l ${f(s*0.06)} ${f(-s*0.18)} l ${f(s*0.12)} ${f(s*0.1)} Z" fill="${c('#9a4818')}"/>`
                   + `<path d="M ${f(s*0.72)} ${f(-s*0.58)} l ${f(s*0.16)} ${f(s*0.04)} l ${f(-s*0.04)} ${f(s*0.08)} Z" fill="${c('#f0ead8')}"/>` // snout
                   + ell(s*0.18, -s*0.15, s*0.5, s*0.12, c('#f0e6d2'))        // chest/legs pale
                   + `<rect x="${f(-s*0.28)}" y="${f(-s*0.2)}" width="${f(s*0.08)}" height="${f(s*0.2)}" fill="${c('#7a3a14')}"/>` // legs
                   + `<rect x="${f(s*0.2)}" y="${f(-s*0.2)}" width="${f(s*0.08)}" height="${f(s*0.2)}" fill="${c('#7a3a14')}"/>`;
                break;
            case 'redsquirrel':
                b += `<path d="M ${f(-s*0.4)} ${f(-s*0.2)} q ${f(-s*0.5)} ${f(-s*0.2)}, ${f(-s*0.3)} ${f(-s*0.9)} q ${f(s*0.3)} ${f(s*0.2)}, ${f(s*0.2)} ${f(s*0.6)} Z" fill="${c('#a65a28')}"/>` // big bushy tail
                   + ell(0, -s*0.4, s*0.3, s*0.36, c('#b5642c'))
                   + `<circle cx="${f(s*0.18)}" cy="${f(-s*0.68)}" r="${f(s*0.18)}" fill="${c('#b5642c')}"/>`
                   + `<path d="M ${f(s*0.06)} ${f(-s*0.84)} l ${f(s*0.02)} ${f(-s*0.14)} l ${f(s*0.1)} ${f(s*0.08)} Z" fill="${c('#8a4418')}"/>` // tufted ear
                   + ell(s*0.12, -s*0.2, s*0.22, s*0.1, c('#efe3cc'));  // pale belly
                break;
            case 'deer':
                b += ell(0, -s*0.5, s*0.62, s*0.3, c('#9c6a40'))           // body
                   + `<rect x="${f(-s*0.4)}" y="${f(-s*0.5)}" width="${f(s*0.08)}" height="${f(s*0.5)}" fill="${c('#7a4e28')}"/>` // legs
                   + `<rect x="${f(-s*0.22)}" y="${f(-s*0.5)}" width="${f(s*0.08)}" height="${f(s*0.5)}" fill="${c('#7a4e28')}"/>`
                   + `<rect x="${f(s*0.2)}" y="${f(-s*0.5)}" width="${f(s*0.08)}" height="${f(s*0.5)}" fill="${c('#7a4e28')}"/>`
                   + `<rect x="${f(s*0.38)}" y="${f(-s*0.5)}" width="${f(s*0.08)}" height="${f(s*0.5)}" fill="${c('#7a4e28')}"/>`
                   + `<path d="M ${f(s*0.5)} ${f(-s*0.55)} q ${f(s*0.3)} ${f(s*0.0)}, ${f(s*0.34)} ${f(-s*0.4)}" stroke="${c('#9c6a40')}" stroke-width="${f(s*0.12)}" fill="none"/>` // neck
                   + ell(s*0.86, -s*0.95, s*0.16, s*0.13, c('#9c6a40'))       // head
                   + `<path d="M ${f(s*0.82)} ${f(-s*1.05)} l ${f(-s*0.06)} ${f(-s*0.35)} m ${f(s*0.06)} ${f(s*0.05)} l ${f(s*0.1)} ${f(-s*0.28)} m ${f(-s*0.04)} ${f(s*0.06)} l ${f(s*0.14)} ${f(-s*0.24)}" stroke="${c('#6a4a2a')}" stroke-width="${f(s*0.04)}" fill="none" stroke-linecap="round"/>`; // antlers
                break;
            case 'hedgehog':
                b += `<path d="M ${f(-s*0.5)} ${f(0)} a ${f(s*0.5)} ${f(s*0.46)} 0 0 1 ${f(s*0.95)} 0 Z" fill="${c('#5a4632')}"/>`
                   + (haze < 0.45 ? Array.from({length:8}, (_,i)=>{const t=i/7; return `<path d="M ${f(-s*0.42+t*s*0.84)} ${f(-s*0.1-Math.sin(t*Math.PI)*s*0.34)} l ${f(s*0.04)} ${f(-s*0.12)}" stroke="${c('#3e3022')}" stroke-width="${f(s*0.04)}" stroke-linecap="round"/>`;}).join('') : '')
                   + ell(s*0.48, -s*0.12, s*0.18, s*0.13, c('#7a6048'))       // snout
                   + `<circle cx="${f(s*0.56)}" cy="${f(-s*0.14)}" r="${f(s*0.03)}" fill="#15110c"/>`;
                break;
            case 'badger':
                b += ell(0, -s*0.34, s*0.6, s*0.3, c('#7a7468'))             // grey body
                   + ell(s*0.5, -s*0.42, s*0.26, s*0.2, c('#f0ece2'))         // white face
                   + `<path d="M ${f(s*0.46)} ${f(-s*0.52)} q ${f(s*0.1)} ${f(s*0.3)}, ${f(s*0.0)} ${f(s*0.34)}" stroke="#1c1814" stroke-width="${f(s*0.07)}" fill="none"/>` // black stripe
                   + `<path d="M ${f(s*0.66)} ${f(-s*0.52)} q ${f(-s*0.1)} ${f(s*0.3)}, ${f(s*0.0)} ${f(s*0.34)}" stroke="#1c1814" stroke-width="${f(s*0.07)}" fill="none"/>`
                   + `<circle cx="${f(s*0.72)}" cy="${f(-s*0.4)}" r="${f(s*0.03)}" fill="#15110c"/>`;
                break;
            case 'hare':
            default:
                b += ell(0, -s*0.34, s*0.46, s*0.28, c('#a17a4e'))           // body
                   + `<circle cx="${f(s*0.34)}" cy="${f(-s*0.56)}" r="${f(s*0.16)}" fill="${c('#a17a4e')}"/>`  // head
                   + `<path d="M ${f(s*0.3)} ${f(-s*0.7)} q ${f(-s*0.04)} ${f(-s*0.5)}, ${f(s*0.06)} ${f(-s*0.56)} q ${f(s*0.08)} ${f(s*0.1)}, ${f(s*0.02)} ${f(s*0.54)} Z" fill="${c('#9a734a')}"/>` // long ear
                   + `<path d="M ${f(s*0.4)} ${f(-s*0.7)} q ${f(s*0.04)} ${f(-s*0.48)}, ${f(s*0.14)} ${f(-s*0.5)} q ${f(s*0.06)} ${f(s*0.12)}, ${f(-s*0.02)} ${f(s*0.5)} Z" fill="${c('#9a734a')}"/>`
                   + `<rect x="${f(-s*0.34)}" y="${f(-s*0.2)}" width="${f(s*0.34)}" height="${f(s*0.1)}" rx="${f(s*0.05)}" fill="${c('#8a663e')}"/>`; // haunch
                break;
        }
        b += `</g>`;
        return { shadow: sh, body: b, y };
    }

    // ---- shared defs (one set, referenced everywhere) ----------------
    function defs(ctx) {
        const a = ctx.light.alpha;
        return `<defs>`
            + `<radialGradient id="ft-shadow" cx="50%" cy="50%" r="50%">`
            +   `<stop offset="0%" stop-color="rgba(0,0,0,1)"/>`
            +   `<stop offset="55%" stop-color="rgba(0,0,0,0.55)"/>`
            +   `<stop offset="100%" stop-color="rgba(0,0,0,0)"/>`
            + `</radialGradient>`
            + `<radialGradient id="ft-dapple" cx="50%" cy="40%" r="60%">`
            +   `<stop offset="0%" stop-color="${ctx.dappleHex || '#ffffff'}" stop-opacity="${ctx.night?0.0:0.10}"/>`
            +   `<stop offset="100%" stop-color="${ctx.dappleHex || '#ffffff'}" stop-opacity="0"/>`
            + `</radialGradient>`
            + `<filter id="ft-haze" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="1.1"/></filter>`
            + `</defs>`;
    }

    const DEFAULT_CTX = {
        haze: 0,
        mistHex: '#aab2ac',
        light: { dx: 0.55, dy: 0.34, len: 1.4, alpha: 0.22 },
        night: false,
    };

    window.ForestTrees = {
        defs, pickSpecies, pickCritter, tree,
        fern, grass, rock, log, mushrooms, bluebells, stump, critter,
        SPECIES_WEIGHTS, CRITTERS,
        // back-compat: old callers passed a crown-radius-ish scale
        randomTree: (x, y, scale, rand) => tree(x, y, scale * 4, rand, DEFAULT_CTX).body,
    };
})();
