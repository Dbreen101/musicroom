// =============================================================
// mr_tips.js — a first-visit WALKTHROUGH for an area of the app,
// plus a permanent "?" button that replays it any time.
//
// A page declares its steps, then includes this file:
//   <script>window.MR_TIP = { key:'room', title:'The Music Room', steps:[
//     { title:'…', body:'…' },                       // centered card
//     { sel:'#r3d-bar', title:'…', body:'…' },       // spotlights the element
//     { title:'…', body:'…', link:'/help#room', linkText:'the full guide' },
//   ]};</script>
//   <script src="/static/js/mr_tips.js"></script>
//
// Sequential + interactive: each step rings the REAL control it talks about
// (a step whose element is missing or hidden simply shows centered), with
// Back / Next, step dots, ←/→ keys, Esc to leave. Steps can deep-link into
// the full guide (/help#…) for the longer story.
//
// Shows once per install: "seen" persists SERVER-SIDE as the setting
// `<key>_tour_seen` (the desktop shell wipes localStorage each launch;
// localStorage is only a same-session cache). The welcome walkthrough marks
// every area seen up front; the light path leaves them so each area
// introduces itself once. The "?" button replays regardless.
//
// Legacy shape still works: { items:[[strong, rest], …] } becomes one card.
// =============================================================
(function () {
'use strict';
var TIP = window.MR_TIP;
if (!TIP || !TIP.key) return;
var SETTING = TIP.key + '_tour_seen';
var LSKEY   = 'mr_tip_' + TIP.key;

// legacy one-card shape → a single centered step
var STEPS = TIP.steps && TIP.steps.length ? TIP.steps.slice() : [{
    title: TIP.title,
    html: '<ul>' + (TIP.items || []).map(function (it) {
        return '<li><strong>' + it[0] + '</strong> — ' + it[1] + '</li>';
    }).join('') + '</ul>',
}];

function markSeen() {
    try { localStorage.setItem(LSKEY, 'done'); } catch (e) {}
    fetch('/api/settings', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify((function (o) { o[SETTING] = '1'; return o; })({})),
    }).catch(function () {});
}

var CSS =
    '#mr-tip-scrim{position:fixed;inset:0;z-index:9500;background:rgba(8,6,4,.6);' +
      'opacity:0;transition:opacity .3s ease;}' +
    '#mr-tip-scrim.in{opacity:1;}' +
    // the spotlight ring — a hole punched in the dark by its box-shadow
    '#mr-tip-ring{position:fixed;z-index:9501;border:2px solid rgba(245,230,176,.85);' +
      'border-radius:12px;pointer-events:none;box-shadow:0 0 0 9999px rgba(8,6,4,.6),' +
      '0 0 22px rgba(245,230,176,.35);transition:all .34s ease;display:none;}' +
    '#mr-tip-card{position:fixed;z-index:9502;max-width:400px;width:min(400px,calc(100vw - 48px));' +
      'background:#1a1610;border:1px solid rgba(245,230,176,.22);border-radius:14px;' +
      'padding:18px 22px 14px;color:#efe6cf;box-shadow:0 16px 48px rgba(0,0,0,.62);' +
      'font-family:var(--font-main,Inter,sans-serif);transition:top .34s ease,left .34s ease;}' +
    '#mr-tip-card .mr-tip__kicker{font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;' +
      'color:rgba(245,230,176,.55);margin-bottom:4px;}' +
    '#mr-tip-card h4{margin:0 0 8px;font-family:var(--font-serif,"EB Garamond",serif);' +
      'font-style:italic;font-weight:400;font-size:1.28rem;color:#f5e6b0;}' +
    '#mr-tip-card .mr-tip__body{line-height:1.55;font-size:.88rem;margin:0 0 6px;}' +
    '#mr-tip-card .mr-tip__body ul{margin:0;padding-left:18px;}' +
    '#mr-tip-card .mr-tip__body li{margin:6px 0;}' +
    '#mr-tip-card .mr-tip__body strong,#mr-tip-card .mr-tip__body b{color:#f5e6b0;font-weight:600;}' +
    '#mr-tip-card .mr-tip__more{display:inline-block;margin:2px 0 8px;font-size:.8rem;' +
      'color:rgba(245,230,176,.8);text-decoration:none;border-bottom:1px dotted rgba(245,230,176,.45);}' +
    '#mr-tip-card .mr-tip__more:hover{color:#f5e6b0;}' +
    '#mr-tip-card .mr-tip__foot{display:flex;align-items:center;gap:10px;margin-top:8px;}' +
    '#mr-tip-card .mr-tip__dots{display:flex;gap:5px;flex:1;}' +
    '#mr-tip-card .mr-tip__dot{width:6px;height:6px;border-radius:50%;background:rgba(245,230,176,.25);}' +
    '#mr-tip-card .mr-tip__dot.on{background:#f5e6b0;}' +
    '#mr-tip-card button{cursor:pointer;font-family:inherit;font-size:.82rem;border-radius:100px;}' +
    '#mr-tip-card .mr-tip__back{padding:6px 13px;background:transparent;color:rgba(245,230,176,.7);' +
      'border:1px solid rgba(245,230,176,.3);}' +
    '#mr-tip-card .mr-tip__back[disabled]{opacity:.3;cursor:default;}' +
    '#mr-tip-card .mr-tip__next{padding:6px 16px;background:#f5e6b0;color:#1d160d;border:1px solid #f5e6b0;}' +
    '#mr-tip-card .mr-tip__next:hover{transform:translateY(-1px);}' +
    '#mr-tip-card .mr-tip__skip{position:absolute;top:10px;right:12px;width:24px;height:24px;padding:0;' +
      'background:transparent;color:rgba(245,230,176,.5);border:none;font-size:.95rem;}' +
    '#mr-tip-card .mr-tip__skip:hover{color:#f5e6b0;}' +
    '#mr-tip-q{position:fixed;z-index:8400;width:34px;height:34px;border-radius:50%;cursor:pointer;' +
      'background:rgba(26,22,16,.88);border:1px solid rgba(245,230,176,.3);color:rgba(245,230,176,.75);' +
      'font-family:var(--font-serif,serif);font-size:1.02rem;line-height:1;' +
      'box-shadow:0 4px 14px rgba(0,0,0,.4);transition:all .18s ease;}' +
    '#mr-tip-q:hover{color:#1d160d;background:#f5e6b0;border-color:#f5e6b0;}';

var styleEl = null;
function ensureCss() {
    if (styleEl) return;
    styleEl = document.createElement('style');
    styleEl.textContent = CSS;
    document.head.appendChild(styleEl);
}

var scrim = null, ring = null, card = null, at = 0, keyHandler = null;
var heldCls = null;   // [el, className, wasAlreadyThere] — a class a step holds open

// a step may declare cls:['#r3d-dock','open'] — the class stays on while the
// step shows (e.g. holding the room's dock open so its bar can be spotlit)
function applyCls(step) {
    if (heldCls) { if (!heldCls[2]) heldCls[0].classList.remove(heldCls[1]); heldCls = null; }
    if (!step || !step.cls) return;
    var el = null;
    try { el = document.querySelector(step.cls[0]); } catch (e) {}
    if (!el) return;
    heldCls = [el, step.cls[1], el.classList.contains(step.cls[1])];
    el.classList.add(step.cls[1]);
}

function targetOf(step) {
    if (!step.sel) return null;
    var el = null;
    try { el = document.querySelector(step.sel); } catch (e) {}
    if (!el) return null;
    var r = el.getBoundingClientRect();
    // hidden / collapsed / off-screen → treat as no target (show centered)
    if (r.width < 8 || r.height < 8 || r.bottom < 0 || r.top > innerHeight) return null;
    return r;
}

function place(step) {
    var r = targetOf(step);
    if (r) {
        var pad = 7;
        ring.style.display = 'block';
        ring.style.left   = (r.left - pad) + 'px';
        ring.style.top    = (r.top - pad) + 'px';
        ring.style.width  = (r.width + pad * 2) + 'px';
        ring.style.height = (r.height + pad * 2) + 'px';
        scrim.style.background = 'transparent';         // the ring's shadow does the dimming
        // card below the target if there's room, else above, clamped on-screen
        var ch = card.offsetHeight || 200, cw = card.offsetWidth || 380;
        var top = (r.bottom + 18 + ch < innerHeight) ? r.bottom + 18
                : (r.top - 18 - ch > 0) ? r.top - 18 - ch
                : Math.max(16, Math.min(innerHeight - ch - 16, r.bottom + 12));
        var left = Math.max(16, Math.min(innerWidth - cw - 16, r.left + r.width / 2 - cw / 2));
        // …and never on the deck (it floats over every page, low on the left, above this card): if the card
        // would cross it, the card goes above it — or, where there's no room above, beside it
        var deck = document.querySelector('#seinnteoir-bar.visible, #seinnteoir-tab.visible');
        if (deck) {
            var d = deck.getBoundingClientRect();
            if (left < d.right + 8 && left + cw > d.left - 8 && top + ch > d.top - 8 && top < d.bottom) {
                if (d.top - ch - 12 >= 16) top = d.top - ch - 12;
                else if (d.right + 12 + cw <= innerWidth - 16) left = d.right + 12;
            }
        }
        card.style.top = top + 'px';
        card.style.left = left + 'px';
        card.style.transform = 'none';
    } else {
        ring.style.display = 'none';
        scrim.style.background = 'rgba(8,6,4,.6)';
        card.style.top = '50%'; card.style.left = '50%';
        card.style.transform = 'translate(-50%,-50%)';
    }
}

function render() {
    var step = STEPS[at], last = at === STEPS.length - 1;
    applyCls(step);
    var body = step.html ? step.html : '<p style="margin:0">' + (step.body || '') + '</p>';
    card.innerHTML =
        '<button class="mr-tip__skip" title="Close — the ? brings this back">✕</button>' +
        '<div class="mr-tip__kicker">' + (TIP.title || '') +
          (STEPS.length > 1 ? ' · ' + (at + 1) + ' of ' + STEPS.length : '') + '</div>' +
        '<h4>' + (step.title || '') + '</h4>' +
        '<div class="mr-tip__body">' + body + '</div>' +
        (step.link ? '<a class="mr-tip__more" href="' + step.link + '">' +
            (step.linkText || 'more in the guide') + ' →</a>' : '') +
        '<div class="mr-tip__foot">' +
          '<div class="mr-tip__dots">' + STEPS.map(function (_, i) {
              return '<span class="mr-tip__dot' + (i === at ? ' on' : '') + '"></span>';
          }).join('') + '</div>' +
          (STEPS.length > 1 ? '<button class="mr-tip__back"' + (at === 0 ? ' disabled' : '') + '>back</button>' : '') +
          '<button class="mr-tip__next">' + (last ? 'done' : 'next') + '</button>' +
        '</div>';
    place(step);
    // placement needs the rendered size — settle again after layout, and once
    // more after CSS transitions (a dock sliding open) have finished
    requestAnimationFrame(function () { place(step); });
    var myAt = at;
    setTimeout(function () { if (card && at === myAt) place(step); }, 420);
    // stopPropagation: pages have their own document-level click closers
    // (menus, the room's dock) that must not react to the card's buttons
    var back = card.querySelector('.mr-tip__back');
    if (back) back.addEventListener('click', function (e) { e.stopPropagation(); if (at > 0) { at--; render(); } });
    card.querySelector('.mr-tip__next').addEventListener('click', function (e) {
        e.stopPropagation();
        if (last) close(); else { at++; render(); }
    });
    card.querySelector('.mr-tip__skip').addEventListener('click', function (e) { e.stopPropagation(); close(); });
    var more = card.querySelector('.mr-tip__more');
    if (more) more.addEventListener('click', function () { markSeen(); });  // leaving for the guide still counts as seen
}

function close() {
    markSeen();
    applyCls(null);                          // let go of any held-open class
    if (keyHandler) { removeEventListener('keydown', keyHandler, true); keyHandler = null; }
    if (scrim) { scrim.classList.remove('in'); }
    var s = scrim, rg = ring, c = card;
    scrim = ring = card = null;
    setTimeout(function () {
        if (s) s.remove(); if (rg) rg.remove(); if (c) c.remove();
    }, 320);
}

function show() {
    if (scrim) return;                       // already open
    ensureCss();
    at = 0;
    scrim = document.createElement('div'); scrim.id = 'mr-tip-scrim';
    ring  = document.createElement('div'); ring.id  = 'mr-tip-ring';
    card  = document.createElement('div'); card.id  = 'mr-tip-card';
    card.setAttribute('role', 'dialog');
    document.body.appendChild(scrim);
    document.body.appendChild(ring);
    document.body.appendChild(card);
    requestAnimationFrame(function () { scrim.classList.add('in'); });
    scrim.addEventListener('click', close);
    keyHandler = function (e) {
        if (e.key === 'Escape') { e.stopPropagation(); close(); }
        else if (e.key === 'ArrowRight' && at < STEPS.length - 1) { e.stopPropagation(); at++; render(); }
        else if (e.key === 'ArrowLeft'  && at > 0) { e.stopPropagation(); at--; render(); }
    };
    addEventListener('keydown', keyHandler, true);
    addEventListener('resize', function () { if (scrim) place(STEPS[at]); });
    render();
}

// ── the "?" — always there, brings the walkthrough back ─────────────────────
function addHelpButton() {
    if (document.getElementById('mr-tip-q')) return;
    ensureCss();
    var q = document.createElement('button');
    q.id = 'mr-tip-q';
    q.textContent = '?';
    q.title = 'Show this page’s introduction again';
    document.body.appendChild(q);
    function position() {
        // sit just above the feedback bubble when it's there; else the corner
        var fb = document.getElementById('mr-fb');
        if (fb) {
            var r = fb.getBoundingClientRect();
            // (the same variable the bubble reads, so the two move together when a page shifts them)
            // …and the same height, plus the bubble's own, so it stays just above it wherever they stand
            if (r.height) { q.style.right = 'var(--mr-keys-right, 16px)';
                            q.style.bottom = 'calc(var(--mr-keys-bottom, 16px) + ' + Math.round(r.height + 10) + 'px)'; return; }
        }
        q.style.right = 'var(--mr-keys-right, 16px)'; q.style.bottom = 'var(--mr-keys-bottom, 16px)';
    }
    position();
    setTimeout(position, 900);              // the bubble builds itself after load
    addEventListener('resize', position);
    q.addEventListener('click', show);
}

if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', addHelpButton);
else addHelpButton();

var seenLocal; try { seenLocal = localStorage.getItem(LSKEY); } catch (e) {}
if (!seenLocal) {
    fetch('/api/settings').then(function (r) { return r.json(); }).then(function (d) {
        if (d && d[SETTING] === '1') {
            try { localStorage.setItem(LSKEY, 'done'); } catch (e) {}
            return;
        }
        setTimeout(show, 1100);              // let the page settle first
    }).catch(function () {});
}
})();
