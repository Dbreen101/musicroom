// =============================================================
// place_illustration.js — choose & render an illustration for a place
//
// Each illustration takes FOUR colour roles so every place can paint its
// own icon (not just one accent) :
//   light      warm window / lamp / fire glow            (was the accent)
//   structure  the main dark mass of the building/object
//   outline    strokes and roof edges (mid-tone)
//   detail     secondary accent: chimneys, signs, strips
//
// Defaults derive from the place's theme_bg + colour_primary so the icon
// automatically sits in the place's mood; explicit illustration_* hex
// columns override any role.
//
// Picked from data (illustration_kind > image_path > size + inside/outside
// > keyword scan > fallback) — see pickKind() below.
// =============================================================
(function () {
'use strict';

// -----------------------------------------------------------------
// Colour helpers — small, dependency-free
// -----------------------------------------------------------------
function _hexToRgb(h) {
    if (!h) return null;
    h = h.replace('#', '');
    if (h.length === 3) h = h.split('').map(c => c + c).join('');
    if (h.length !== 6) return null;
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function _rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(c => Math.max(0, Math.min(255, Math.round(c))).toString(16).padStart(2, '0')).join('');
}
function _mix(a, b, t) {
    const A = _hexToRgb(a), B = _hexToRgb(b);
    if (!A || !B) return a;
    return _rgbToHex(A[0] * (1 - t) + B[0] * t, A[1] * (1 - t) + B[1] * t, A[2] * (1 - t) + B[2] * t);
}
function _relLum(hex) {
    const rgb = _hexToRgb(hex);
    if (!rgb) return 0.5;
    const ch = rgb.map(c => { c /= 255; return c < 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

// -----------------------------------------------------------------
// Four colour roles per illustration
// -----------------------------------------------------------------
function lightOf(p) {
    return p.illustration_light || p.colour_primary || '#c89a55';
}
function structureOf(p) {
    if (p.illustration_structure) return p.illustration_structure;
    // Derive a deep version of the place's ground colour so the building
    // sits IN the place's mood rather than fighting it. On a light theme
    // we want a clearly-dark building; on a dark theme a deeper-still mass.
    const bg = p.theme_bg;
    if (bg) {
        const dark = _relLum(bg) < 0.42;
        return dark ? _mix(bg, '#000000', 0.45) : '#1a140e';
    }
    return '#1a140e';
}
function outlineOf(p) {
    if (p.illustration_outline) return p.illustration_outline;
    return _mix(structureOf(p), '#ffffff', 0.22);
}
function detailOf(p) {
    // Default to the warm light — keeps the illustration coherent. Set
    // illustration_detail explicitly if you want a distinct secondary
    // accent (e.g. stone-tan rim with gold light, or vice versa).
    return p.illustration_detail || lightOf(p);
}

// -----------------------------------------------------------------
// Choose the illustration kind from place data
// -----------------------------------------------------------------
const KEYWORDS = [
    // [kind,         regex of words to look for in description/crowd_notes/moods/name]
    ['pub',           /\b(pub|bar|tavern|local|sn[aá]g)\b/i],
    ['cathedral',     /\b(cathedral|church|chapel|temple|monastery|abbey)\b/i],
    ['warehouse',     /\b(warehouse|basement|berghain|tresor|tresour|loft)\b/i],
    ['club',          /\b(club|rave|disco|nightclub|techno|fabric|panorama|sub\s*club)\b/i],
    ['cottage',       /\b(cottage|cabin|house|home|sitting room|living room)\b/i],
    ['flat',          /\b(flat|apartment|tower|block|highrise|high\s*rise)\b/i],
    ['car',           /\b(car|taxi|driver|drive|backseat)\b/i],
    ['bbq',           /\b(bbq|barbecue|barbeque|grill|cookout|garden party)\b/i],
    ['beach',         /\b(beach|shore|coast|seaside|tide|sand|donegal\s+beach)\b/i],
    ['boat',          /\b(boat|fjord|sail|ferry|yacht|ship)\b/i],
    ['kitchen',       /\b(kitchen|3am|after\s*party|after-party|afters)\b/i],
    ['field',         /\b(field|festival|outdoor|open[\s-]?air|park|meadow|hill)\b/i],
    ['forest',        /\b(forest|wood|grove|trees|clearing)\b/i],
    ['rooftop',       /\b(rooftop|terrace|balcony|roof)\b/i],
    ['cave',          /\b(cave|underground|tunnel|crypt)\b/i],
    ['headphones',    /\b(headphones?|alone|solo|listening|home\s*listening)\b/i],
];

function pickKind(place) {
    if (!place) return 'default';
    // The Well is always a well — its shape isn't user-changeable. Only the
    // colours and theme are. This makes sure the well can't get "stuck" on
    // some other kind if illustration_kind ever holds a stale value.
    if (place.is_well) return 'well';
    if (place.illustration_kind && place.illustration_kind !== 'auto') {
        return place.illustration_kind;
    }
    if (place.image_path) return 'custom';

    const size = (place.size || '').toLowerCase();
    const io   = (place.inside_outside || '').toLowerCase();
    if (size === 'headphones')                                                return 'headphones';
    if (size === 'open air')                                                  return 'field';
    if (io   === 'outside' && size === 'large venue')                         return 'field';

    const haystack = [
        place.name, place.description, place.moods, place.crowd_notes, place.notes,
    ].filter(Boolean).join(' ');
    for (const [kind, re] of KEYWORDS) {
        if (re.test(haystack)) return kind;
    }

    if (io === 'outside')         return 'field';
    if (size === 'large venue')   return 'club';
    if (size === 'small venue')   return 'pub';
    if (size === 'intimate')      return 'kitchen';
    return 'default';
}

// Public catalogue — for building the picker dropdown. Labels describe
// what's actually visible at icon size, not every tiny element drawn.
const KINDS_CATALOGUE = [
    { key: 'auto',        label: 'Auto (from data)' },
    { key: 'club',        label: 'Club (dark slab, lit door)' },
    { key: 'warehouse',   label: 'Warehouse (sawtooth roof)' },
    { key: 'pub',         label: 'Pub (gable + chimney smoke)' },
    { key: 'cottage',     label: 'Cottage (thatched roof)' },
    { key: 'flat',        label: 'Apartment block (lit windows)' },
    { key: 'car',         label: 'Car (headlights at night)' },
    { key: 'bbq',         label: 'Grill (embers + smoke)' },
    { key: 'beach',       label: 'Beach (water + shore)' },
    { key: 'field',       label: 'Festival field (speaker stack)' },
    { key: 'forest',      label: 'Forest (campfire in trees)' },
    { key: 'cathedral',   label: 'Cathedral (cross spire)' },
    { key: 'well',        label: 'Well (stone rim + water)' },
    { key: 'boat',        label: 'Sailing boat' },
    { key: 'kitchen',     label: 'Kitchen (hanging lamp + table)' },
    { key: 'rooftop',     label: 'Rooftop (city skyline)' },
    { key: 'cave',        label: 'Cave mouth (interior glow)' },
    { key: 'headphones',  label: 'Headphones' },
    { key: 'default',     label: 'Lantern (minimal)' },
];

// -----------------------------------------------------------------
// Small reusable parts
// -----------------------------------------------------------------
function warmWindow(x, y, w, h, light) {
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${light}" opacity="0.85" rx="0.6"/>`;
}
function person(x, y, scale = 1) {
    const r = 2 * scale;
    return `
        <circle cx="${x}" cy="${y - 3 * scale}" r="${r}" fill="#0a0806"/>
        <path d="M ${x - r * 1.4} ${y + 5 * scale}
                 Q ${x} ${y - r}
                 ${x + r * 1.4} ${y + 5 * scale} Z"
              fill="#0a0806"/>`;
}
function smokePlume(x, y) {
    return `
        <path d="M ${x} ${y}
                 Q ${x - 3} ${y - 8} ${x + 1} ${y - 16}
                 Q ${x + 5} ${y - 22} ${x - 2} ${y - 30}"
              stroke="rgba(200,210,220,0.4)" stroke-width="2"
              fill="none" stroke-linecap="round"/>`;
}

// Foliage / water tones are environmental — kept stable so trees stay
// reading as trees and water as water across themes.
const FOLIAGE_DARK  = '#1a2418';
const FOLIAGE_LIGHT = '#1c2a1c';
const WATER         = '#1a262a';
const WATER_RIPPLE  = 'rgba(200,210,220,0.30)';

// -----------------------------------------------------------------
// Illustrations — each returns the inner SVG markup (no <svg> wrapper).
// viewBox is 0 0 120 120; ground line at y=92.
// -----------------------------------------------------------------
const ILLUSTRATIONS = {

club(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <rect x="22" y="48" width="76" height="44" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <rect x="20" y="46" width="80" height="4"  fill="${_mix(s, '#000', 0.3)}"/>
        <!-- lit doorway -->
        <rect x="54" y="64" width="12" height="28" fill="${l}" opacity="0.55"/>
        <rect x="54" y="64" width="12" height="28" fill="none" stroke="${o}" stroke-width="0.8"/>
        <!-- upper window strips -->
        ${warmWindow(30, 56, 22, 4, l)}
        ${warmWindow(68, 56, 22, 4, l)}
        <!-- light bleed above (the building thumps) -->
        <line x1="20" y1="44" x2="100" y2="44" stroke="${l}" stroke-width="0.8" opacity="0.45"/>
        <ellipse cx="60" cy="46" rx="38" ry="2" fill="${l}" opacity="0.18"/>
        <!-- the bouncer -->
        ${person(46, 90, 1)}
    `;
},

warehouse(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p), d = detailOf(p);
    return `
        <rect x="14" y="54" width="92" height="38" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <!-- sawtooth roof -->
        <path d="M 14 54 L 24 44 L 24 54 L 38 44 L 38 54
                 L 52 44 L 52 54 L 66 44 L 66 54
                 L 80 44 L 80 54 L 94 44 L 94 54 L 106 54 Z"
              fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <!-- glowing strips along the sawtooth -->
        <line x1="26" y1="46" x2="36" y2="46" stroke="${l}" stroke-width="1" opacity="0.8"/>
        <line x1="54" y1="46" x2="64" y2="46" stroke="${l}" stroke-width="1" opacity="0.8"/>
        <line x1="82" y1="46" x2="92" y2="46" stroke="${l}" stroke-width="1" opacity="0.8"/>
        <!-- spilling-light doorway -->
        <rect x="56" y="74" width="10" height="18" fill="${l}" opacity="0.62"/>
        <rect x="56" y="74" width="10" height="18" fill="none" stroke="${o}" stroke-width="0.8"/>
        <ellipse cx="61" cy="92" rx="14" ry="2" fill="${l}" opacity="0.22"/>
        <!-- detail trim along the wall -->
        <line x1="14" y1="74" x2="106" y2="74" stroke="${d}" stroke-width="0.4" opacity="0.5"/>
    `;
},

pub(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p), d = detailOf(p);
    return `
        <rect x="26" y="56" width="68" height="36" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <!-- gable -->
        <path d="M 24 56 L 60 38 L 96 56 Z" fill="${_mix(s, '#000', 0.25)}" stroke="${o}" stroke-width="1.2"/>
        <!-- chimney + curling smoke -->
        <rect x="76" y="42" width="6" height="10" fill="${s}"/>
        ${smokePlume(79, 42)}
        <!-- two warm windows -->
        ${warmWindow(34, 64, 12, 10, l)}
        ${warmWindow(74, 64, 12, 10, l)}
        <!-- door with lit threshold -->
        <rect x="56" y="72" width="8" height="20" fill="${_mix(s, '#000', 0.3)}"/>
        <rect x="56" y="72" width="8" height="2"  fill="${l}" opacity="0.7"/>
        <!-- hanging sign (small detail accent) -->
        <line x1="38" y1="58" x2="62" y2="58" stroke="${d}" stroke-width="0.8"/>
        <rect x="44" y="64" width="12" height="6" fill="${_mix(s, '#ffffff', 0.15)}" stroke="${d}" stroke-width="0.5"/>
    `;
},

cottage(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p), d = detailOf(p);
    const thatch = _mix(d, '#000', 0.4);
    return `
        <rect x="32" y="62" width="56" height="30" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <!-- thatched pitched roof -->
        <path d="M 30 62 L 60 42 L 90 62 Z" fill="${_mix(d, '#000', 0.2)}" stroke="${o}" stroke-width="1.2"/>
        <path d="M 30 62 L 60 42 L 90 62 Z" fill="url(#thatch)"/>
        <defs>
            <pattern id="thatch" width="6" height="2" patternUnits="userSpaceOnUse">
                <line x1="0" y1="1" x2="6" y2="1" stroke="${thatch}" stroke-width="0.4" opacity="0.55"/>
            </pattern>
        </defs>
        <!-- chimney with peat smoke -->
        <rect x="72" y="48" width="5" height="10" fill="${s}"/>
        ${smokePlume(74, 48)}
        <!-- door -->
        <rect x="56" y="74" width="8" height="18" fill="${_mix(s, '#000', 0.2)}"/>
        <!-- windows -->
        ${warmWindow(38, 70, 10, 8, l)}
        ${warmWindow(72, 70, 10, 8, l)}
        <!-- planter -->
        <ellipse cx="35" cy="92" rx="6" ry="2" fill="${FOLIAGE_DARK}"/>
    `;
},

flat(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    const off = _mix(s, '#000', 0.2);
    return `
        <rect x="40" y="34" width="40" height="58" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        ${[40, 50, 60, 70, 80].map(y =>
            [44, 52, 60, 68, 76].map(x => {
                const lit = Math.random() < 0.45;
                return lit
                    ? warmWindow(x, y, 4, 4, l)
                    : `<rect x="${x}" y="${y}" width="4" height="4" fill="${off}"/>`;
            }).join('')
        ).join('')}
        <!-- entrance -->
        <rect x="56" y="84" width="8" height="8" fill="${off}"/>
        <rect x="56" y="84" width="8" height="1" fill="${l}" opacity="0.8"/>
    `;
},

car(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <!-- headlight cone -->
        <path d="M 32 80 L 4 70 L 4 90 Z" fill="${l}" opacity="0.22"/>
        <path d="M 36 78
                 Q 42 60 60 60
                 L 84 60
                 Q 96 60 100 78
                 L 100 86
                 L 36 86 Z"
              fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <path d="M 46 74
                 Q 50 64 60 64
                 L 80 64
                 Q 92 64 94 74 Z"
              fill="${l}" opacity="0.30"/>
        <circle cx="50" cy="88" r="5" fill="${_mix(s, '#000', 0.4)}" stroke="${o}" stroke-width="1"/>
        <circle cx="86" cy="88" r="5" fill="${_mix(s, '#000', 0.4)}" stroke="${o}" stroke-width="1"/>
        <line x1="0" y1="92" x2="120" y2="92" stroke="${o}" stroke-width="0.6"/>
    `;
},

bbq(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <rect x="48" y="68" width="24" height="14" rx="3" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <line x1="50" y1="68" x2="70" y2="68" stroke="${_mix(o, '#000', 0.3)}" stroke-width="0.6"/>
        <line x1="50" y1="71" x2="70" y2="71" stroke="${_mix(o, '#000', 0.3)}" stroke-width="0.6"/>
        <line x1="50" y1="82" x2="46" y2="92" stroke="${o}" stroke-width="2"/>
        <line x1="70" y1="82" x2="74" y2="92" stroke="${o}" stroke-width="2"/>
        <!-- ember glow -->
        <ellipse cx="60" cy="68" rx="10" ry="2" fill="${l}" opacity="0.75"/>
        ${smokePlume(56, 66)}
        ${smokePlume(64, 66)}
        <!-- grass tufts -->
        <path d="M 18 92 L 16 88 M 22 92 L 24 87 M 96 92 L 98 87 M 102 92 L 100 88"
              stroke="#3a4d2a" stroke-width="1" fill="none"/>
    `;
},

beach(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <!-- sea -->
        <rect x="0" y="68" width="120" height="14" fill="${WATER}" opacity="0.7"/>
        <!-- ripples -->
        <path d="M 10 74 Q 20 72 30 74 T 50 74 T 70 74 T 90 74 T 110 74"
              stroke="${l}" stroke-width="0.6" fill="none" opacity="0.5"/>
        <path d="M 10 78 Q 20 76 30 78 T 50 78 T 70 78 T 90 78 T 110 78"
              stroke="${WATER_RIPPLE}" stroke-width="0.5" fill="none"/>
        <!-- shore -->
        <path d="M 0 82 Q 30 86 60 84 T 120 86 L 120 92 L 0 92 Z"
              fill="${_mix(s, '#ffffff', 0.1)}" opacity="0.9"/>
        <!-- driftwood + fire -->
        <line x1="62" y1="88" x2="74" y2="84" stroke="${s}" stroke-width="1.2"/>
        <line x1="64" y1="86" x2="76" y2="86" stroke="${s}" stroke-width="1.2"/>
        <ellipse cx="68" cy="86" rx="5" ry="2" fill="${l}" opacity="0.8"/>
    `;
},

field(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <!-- rolling hill -->
        <path d="M 0 84 Q 30 70 60 78 T 120 74 L 120 92 L 0 92 Z"
              fill="${FOLIAGE_DARK}" stroke="${_mix(FOLIAGE_DARK, '#fff', 0.15)}" stroke-width="0.6"/>
        <!-- speaker stack -->
        <line x1="60" y1="48" x2="60" y2="80" stroke="${s}" stroke-width="2"/>
        <rect x="55" y="56" width="10" height="6" fill="${s}" stroke="${o}" stroke-width="0.6"/>
        <rect x="55" y="64" width="10" height="6" fill="${s}" stroke="${o}" stroke-width="0.6"/>
        <line x1="60" y1="48" x2="48" y2="42" stroke="${s}" stroke-width="1"/>
        <line x1="60" y1="48" x2="72" y2="42" stroke="${s}" stroke-width="1"/>
        <!-- glow from speakers -->
        <ellipse cx="60" cy="62" rx="26" ry="4" fill="${l}" opacity="0.32"/>
    `;
},

forest(p) {
    const l = lightOf(p), s = structureOf(p);
    return `
        <!-- 4 trees forming a clearing -->
        <g transform="translate(20,82)">
            <rect x="-2" y="-12" width="4" height="14" fill="${s}"/>
            <ellipse cx="0" cy="-18" rx="14" ry="14" fill="${FOLIAGE_DARK}"/>
        </g>
        <g transform="translate(96,84)">
            <rect x="-2" y="-12" width="4" height="14" fill="${s}"/>
            <ellipse cx="0" cy="-18" rx="13" ry="13" fill="${FOLIAGE_DARK}"/>
        </g>
        <g transform="translate(38,86)">
            <rect x="-1.5" y="-10" width="3" height="12" fill="${s}"/>
            <ellipse cx="0" cy="-16" rx="10" ry="10" fill="${FOLIAGE_LIGHT}"/>
        </g>
        <g transform="translate(80,84)">
            <rect x="-1.5" y="-10" width="3" height="12" fill="${s}"/>
            <ellipse cx="0" cy="-16" rx="11" ry="11" fill="${FOLIAGE_LIGHT}"/>
        </g>
        <!-- campfire -->
        <line x1="56" y1="88" x2="64" y2="84" stroke="${s}" stroke-width="1.2"/>
        <line x1="58" y1="86" x2="66" y2="86" stroke="${s}" stroke-width="1.2"/>
        <ellipse cx="60" cy="86" rx="6" ry="2" fill="${l}" opacity="0.85"/>
        ${smokePlume(60, 84)}
    `;
},

cathedral(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <rect x="34" y="58" width="52" height="34" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <!-- pitched roof -->
        <path d="M 32 58 L 60 38 L 88 58 Z" fill="${_mix(s, '#000', 0.25)}" stroke="${o}" stroke-width="1.2"/>
        <!-- spire -->
        <path d="M 56 38 L 60 22 L 64 38 Z" fill="${_mix(s, '#000', 0.25)}" stroke="${o}" stroke-width="1"/>
        <!-- celtic cross -->
        <line x1="60" y1="20" x2="60" y2="14" stroke="${o}" stroke-width="1.4"/>
        <line x1="56" y1="17" x2="64" y2="17" stroke="${o}" stroke-width="1.4"/>
        <circle cx="60" cy="17" r="2.4" fill="none" stroke="${o}" stroke-width="0.8"/>
        <!-- arched windows -->
        <path d="M 42 72 Q 42 66 47 66 Q 52 66 52 72 L 52 78 L 42 78 Z"
              fill="${l}" opacity="0.65"/>
        <path d="M 68 72 Q 68 66 73 66 Q 78 66 78 72 L 78 78 L 68 78 Z"
              fill="${l}" opacity="0.65"/>
        <!-- arched door -->
        <path d="M 56 80 Q 56 74 60 74 Q 64 74 64 80 L 64 92 L 56 92 Z"
              fill="${_mix(s, '#000', 0.35)}" stroke="${o}" stroke-width="0.8"/>
    `;
},

boat(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <rect x="0" y="74" width="120" height="18" fill="${WATER}" opacity="0.7"/>
        <path d="M 0 78 Q 20 76 40 78 T 80 78 T 120 78"
              stroke="${WATER_RIPPLE}" stroke-width="0.5" fill="none"/>
        <path d="M 0 84 Q 20 82 40 84 T 80 84 T 120 84"
              stroke="${l}" stroke-width="0.5" fill="none" opacity="0.5"/>
        <!-- hull -->
        <path d="M 34 76 L 86 76 L 78 84 L 42 84 Z"
              fill="${s}" stroke="${o}" stroke-width="1"/>
        <!-- mast + sail -->
        <line x1="60" y1="76" x2="60" y2="42" stroke="${o}" stroke-width="1.4"/>
        <path d="M 60 44 L 76 70 L 60 70 Z" fill="rgba(200,210,220,0.32)" stroke="rgba(200,210,220,0.6)" stroke-width="0.7"/>
        <!-- portholes -->
        <circle cx="62" cy="80" r="1.6" fill="${l}" opacity="0.9"/>
        <circle cx="70" cy="80" r="1.6" fill="${l}" opacity="0.9"/>
    `;
},

kitchen(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <rect x="20" y="36" width="80" height="50" fill="${s}" opacity="0.88"/>
        <!-- hanging lamp -->
        <line x1="60" y1="36" x2="60" y2="50" stroke="${o}" stroke-width="1"/>
        <path d="M 50 50 L 70 50 L 66 60 L 54 60 Z" fill="${s}" stroke="${o}" stroke-width="0.7"/>
        <ellipse cx="60" cy="64" rx="26" ry="7" fill="${l}" opacity="0.62"/>
        <!-- table -->
        <rect x="36" y="76" width="48" height="3" fill="${o}"/>
        <line x1="40" y1="79" x2="40" y2="92" stroke="${o}" stroke-width="2"/>
        <line x1="80" y1="79" x2="80" y2="92" stroke="${o}" stroke-width="2"/>
        <!-- glass on the table -->
        <rect x="56" y="71" width="4" height="5" fill="${l}" opacity="0.6"/>
        <rect x="56" y="71" width="4" height="5" fill="none" stroke="${o}" stroke-width="0.5"/>
    `;
},

rooftop(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    const farther = _mix(s, '#000', 0.2);
    return `
        <!-- skyline -->
        <rect x="0"  y="46" width="20" height="46" fill="${farther}"/>
        <rect x="22" y="42" width="14" height="50" fill="${_mix(s, '#000', 0.1)}"/>
        <rect x="98" y="50" width="22" height="42" fill="${farther}"/>
        ${warmWindow(4,  60, 4, 4, l)}
        ${warmWindow(28, 58, 4, 4, l)}
        ${warmWindow(104, 62, 4, 4, l)}
        ${warmWindow(112, 70, 4, 4, l)}
        <!-- foreground rooftop -->
        <rect x="36" y="72" width="48" height="20" fill="${s}" stroke="${o}" stroke-width="1"/>
        <!-- parapet -->
        <rect x="36" y="68" width="48" height="4" fill="${_mix(s, '#000', 0.25)}"/>
    `;
},

cave(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <!-- cave mouth -->
        <path d="M 14 92 Q 14 50 60 38 Q 106 50 106 92 Z"
              fill="${_mix(s, '#000', 0.4)}" stroke="${o}" stroke-width="1.2"/>
        <!-- interior glow -->
        <ellipse cx="60" cy="78" rx="22" ry="10" fill="${l}" opacity="0.45"/>
        <!-- figure inside -->
        ${person(60, 86, 1)}
        <!-- stalactites -->
        <path d="M 30 56 L 34 64 L 38 56 Z" fill="${s}"/>
        <path d="M 78 54 L 82 62 L 86 54 Z" fill="${s}"/>
        <path d="M 56 50 L 60 60 L 64 50 Z" fill="${s}"/>
    `;
},

headphones(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <path d="M 36 70 Q 36 38 60 38 Q 84 38 84 70"
              fill="none" stroke="${o}" stroke-width="3.5" stroke-linecap="round"/>
        <rect x="28" y="62" width="14" height="22" rx="3" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <rect x="78" y="62" width="14" height="22" rx="3" fill="${s}" stroke="${o}" stroke-width="1.2"/>
        <rect x="32" y="66" width="6" height="14" rx="2" fill="${l}" opacity="0.7"/>
        <rect x="82" y="66" width="6" height="14" rx="2" fill="${l}" opacity="0.7"/>
    `;
},

default(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p);
    return `
        <rect x="58" y="62" width="3" height="30" fill="${s}"/>
        <line x1="52" y1="62" x2="68" y2="62" stroke="${s}" stroke-width="2"/>
        <path d="M 52 50 L 68 50 L 66 62 L 54 62 Z"
              fill="${_mix(s, '#000', 0.3)}" stroke="${o}" stroke-width="0.8"/>
        <rect x="55" y="52" width="10" height="9" fill="${l}" opacity="0.9"/>
        <path d="M 52 50 L 60 44 L 68 50 Z" fill="${_mix(s, '#000', 0.3)}" stroke="${o}" stroke-width="0.8"/>
        <ellipse cx="60" cy="92" rx="18" ry="3" fill="${l}" opacity="0.42"/>
    `;
},

// The Well — an aerial Irish stone well: water reflecting at the top,
// stone rim, stones in the descending wall, moss on the rim, ferns at
// the base. Uses the same 4 colour roles as every other illustration
// (the water surface tints from `detail`; the bright highlight is `light`;
// the deep shaft is `structure`; rim + stone seams are `outline`).
well(p) {
    const l = lightOf(p), s = structureOf(p), o = outlineOf(p), d = detailOf(p);
    const water = _mix(d, '#cfe0d0', 0.55);
    const stoneDark = _mix(d, '#000', 0.22);
    return `
        <!-- mossy clearing around the well -->
        <ellipse cx="60" cy="70" rx="52" ry="36" fill="rgba(40,50,30,0.18)"/>
        <!-- outer stone rim -->
        <ellipse cx="60" cy="58" rx="34" ry="10" fill="${d}"/>
        <ellipse cx="60" cy="58" rx="34" ry="10" fill="none" stroke="${o}" stroke-width="1.4"/>
        <!-- the dark shaft going down -->
        <ellipse cx="60" cy="58" rx="28" ry="7" fill="${s}"/>
        <!-- water surface, tinted from detail -->
        <ellipse cx="60" cy="57" rx="26" ry="6" fill="${water}" opacity="0.78"/>
        <!-- water reflection highlights (light is the bright accent) -->
        <ellipse cx="60" cy="56" rx="14" ry="2" fill="${l}" opacity="0.55"/>
        <ellipse cx="60" cy="55" rx="8"  ry="1" fill="${l}" opacity="0.9"/>
        <!-- descending side wall of the well -->
        <path d="M 26 60 C 24 88 32 102 38 104 L 82 104 C 88 102 96 88 94 60"
              fill="${s}" stroke="${o}" stroke-width="1.6"/>
        <!-- stones in the side wall — two rows, alternating tones -->
        <path d="M 30 70 Q 35 69 40 71 L 39 78 Q 34 79 31 76 Z" fill="${d}"         opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <path d="M 42 71 Q 48 70 54 72 L 53 79 Q 48 80 43 77 Z" fill="${stoneDark}" opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <path d="M 56 72 Q 62 71 68 73 L 67 80 Q 62 81 57 78 Z" fill="${d}"         opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <path d="M 70 73 Q 76 72 82 74 L 81 81 Q 76 82 71 79 Z" fill="${stoneDark}" opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <path d="M 34 84 Q 40 83 46 85 L 45 92 Q 40 93 35 90 Z" fill="${stoneDark}" opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <path d="M 48 85 Q 54 84 60 86 L 59 93 Q 54 94 49 91 Z" fill="${d}"         opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <path d="M 62 86 Q 68 85 74 87 L 73 94 Q 68 95 63 92 Z" fill="${stoneDark}" opacity="0.9" stroke="${o}" stroke-width="0.4"/>
        <!-- moss tufts along the rim -->
        <path d="M 28 58 Q 32 54 36 58 M 44 58 Q 48 53 52 58 M 68 58 Q 72 53 76 58 M 84 58 Q 88 54 92 58"
              stroke="rgba(110,150,100,0.85)" stroke-width="1.4" fill="none" stroke-linecap="round"/>
        <!-- ferns / grass at the base -->
        <path d="M 22 102 L 20 94 M 26 102 L 25 96 M 96 102 L 98 94 M 100 102 L 101 96"
              stroke="rgba(110,140,90,0.85)" stroke-width="1.4" fill="none" stroke-linecap="round"/>
        <path d="M 18 102 Q 14 96 10 92 M 102 102 Q 106 96 110 92"
              stroke="rgba(90,120,80,0.85)" stroke-width="1.4" fill="none" stroke-linecap="round"/>
    `;
},

custom(p) {
    const url = (p.image_path || '').replace(/"/g, '&quot;');
    return `<image href="${url}" x="10" y="10" width="100" height="100" preserveAspectRatio="xMidYMid meet"/>`;
},

};

// -----------------------------------------------------------------
// Public entrypoint
// -----------------------------------------------------------------
function renderPlaceIllustration(place, opts) {
    const kind  = pickKind(place);
    const inner = (ILLUSTRATIONS[kind] || ILLUSTRATIONS.default)(place);
    const size  = (opts && opts.size) || 120;
    return `<svg viewBox="0 0 120 120" width="${size}" height="${size}" aria-hidden="true"
                 class="place-illustration" data-kind="${kind}">${inner}</svg>`;
}

window.placeIllustrationKind     = pickKind;
window.renderPlaceIllustration   = renderPlaceIllustration;
window.PLACE_ILLUSTRATION_KINDS  = KINDS_CATALOGUE;
// Exposed so the edit modal can build colour preview / reset-to-auto behaviour.
window.placeIllustrationDefaults = function (place) {
    return {
        light:     lightOf(place),
        structure: structureOf(place),
        outline:   outlineOf(place),
        detail:    detailOf(place),
    };
};

})();
