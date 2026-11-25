// sim_shop.js — the credits trial wherever a record from the shop is shown
// (gr_sim.py on the rooms server, gr_sim_app.py in the app; 2026-11-20).
//
// Daithí: "Bring home to Music Room" replaces borrowing (the name is his working
// one — "need to change this phrasing later"); a record can also be bought
// outright, straight away or for the difference once it is home; everyone has
// credits; the room holds so many brought-home tracks; a track taken out comes
// back free after a week, and the person must know that before they do it.
//
//   SimShop.me(fresh)              → {on, credits, room:{count,space}, rules}
//   SimShop.trackActs(t)           the buttons for one track (t.sim from the server)
//   SimShop.recordsHtml(tracks, o) tracks grouped into their records (albums and
//                                  singles), each with "the whole record" buttons
//   SimShop.mountMine(host)        My Room's "Borrowed" tab: what is brought home, and nothing else
//   SimShop.bought(fresh)          → the tracks this person has BOUGHT, one after another
//   SimShop.mountBought(host)      those, as cards (a room with no records of its own)
//   SimShop.openBought(t, anchor)  a bought record's small window: play, cue, grúpa
//   SimShop.playTrack(id)          play one of your own shop records in the deck
//   event 'sim-changed' on window  after anything is brought home, bought or taken out
//
// The buttons work on any page: one listener below hears [data-sim-act].
(function () {
'use strict';
if (window.SimShop) return;

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const mmss = s => { if (!s) return ''; s = Math.round(s); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const cr = n => n + (n === 1 ? ' credit' : ' credits');
const day = iso => { try { const d = new Date(iso); return d.getDate() + ' ' + d.toLocaleString('en-GB', { month: 'short' }); } catch (_) { return iso || ''; } };
const canComeBack = s => !!(s && s.state === 'out' && s.back_after && new Date(s.back_after) <= new Date());
const KIND = { album: 'Album', single: 'Single', compilation: 'From a compilation' };

let ME = null, meAsk = null;
const REG = new Map();          // track id → the track as last drawn (to play it, to name it)
const RECS = new Map();         // record key → its tracks as last drawn

async function me(fresh) {
    if (ME && !fresh) return ME;
    if (!meAsk || fresh) meAsk = fetch('/api/gr/sim/me' + (fresh ? '?fresh=1' : '')).then(r => r.ok ? r.json() : null).catch(() => null);
    const d = await meAsk;
    if (d) { ME = d; window.dispatchEvent(new CustomEvent('sim-me', { detail: d })); }
    return ME;
}
const rules = () => (ME && ME.rules) || { home_cost: 1, buy_cost: 3, record_share: 80, wait_days: 7, room_space: 200 };

// what the whole of these tracks costs — the server's sums, so the button says what will be taken
function quote(tracks, what) {
    const r = rules();
    let cost = 0, n = 0, back = 0, locked = 0;
    for (const t of tracks) {
        const s = t.sim || {};
        if (what === 'home') {
            if (s.state === 'home' || s.state === 'bought') continue;
            if (s.state === 'out') { if (canComeBack(s)) back++; else locked++; continue; }
            cost += r.home_cost; n++;
        } else {
            if (s.state === 'bought') continue;
            cost += (s.buy_cost != null ? s.buy_cost : r.buy_cost); n++;
        }
    }
    if (n >= 2) cost = Math.ceil(cost * r.record_share / 100);
    return { cost, n, back, locked };
}

// ── one track's buttons ──
// what a record you hold can do, wherever it is shown: play, go in the cue, go in a grúpa
const heldActs = id => `<button type="button" class="sim-btn" data-sim-act="play" data-id="${id}" title="Play it">▶ Play</button>`
    + `<button type="button" class="sim-btn sim-btn--quiet" data-sim-act="cue" data-id="${id}" data-snt-keep title="Add it to the cue">＋ Cue</button>`
    + `<button type="button" class="sim-btn sim-btn--quiet" data-sim-act="grupa" data-id="${id}" title="Add it to a grúpa">＋ Grúpa</button>`;
function trackActs(t, o) {
    o = o || {};
    const s = t.sim; if (!s) return '';
    REG.set(t.id, t);
    const id = t.id;
    let h = '';
    if (s.state === 'bought') {
        h += `<span class="sim-state">Yours</span>`;
        if (!o.noPlay && s.url) h += heldActs(id);
    } else if (s.state === 'home') {
        h += `<span class="sim-state">At home</span>`;
        if (!o.noPlay && s.url) h += heldActs(id);
        h += `<button type="button" class="sim-btn" data-sim-act="buy" data-id="${id}" title="Buy it outright: it stays yours and takes no room">Buy · ${s.buy_cost}</button>`;
        if (!o.noOut) h += `<button type="button" class="sim-btn sim-btn--quiet" data-sim-act="out" data-id="${id}" title="Take it out of your room (no credit back; a week before it can come back)">Take out</button>`;
    } else if (s.state === 'out') {
        if (canComeBack(s)) h += `<button type="button" class="sim-btn" data-sim-act="home" data-id="${id}" title="It has waited its week: it comes back free">Bring back · free</button>`;
        else h += `<span class="sim-state" title="Taken out of your room">Back on ${esc(day(s.back_after))}</span>`;
        h += `<button type="button" class="sim-btn" data-sim-act="buy" data-id="${id}" title="Buy it outright">Buy · ${s.buy_cost}</button>`;
    } else {
        h += `<button type="button" class="sim-btn" data-sim-act="home" data-id="${id}" title="Bring it home to your Music Room: it plays only here">Bring home · ${s.home_cost}</button>`;
        h += `<button type="button" class="sim-btn" data-sim-act="buy" data-id="${id}" title="Buy it outright: yours for good, takes no room">Buy · ${s.buy_cost}</button>`;
    }
    return `<span class="sim-acts">${h}</span>`;
}

// ── the whole record's buttons ──
function recordActs(key, tracks) {
    RECS.set(key, tracks);
    const h = quote(tracks, 'home'), b = quote(tracks, 'buy');
    const all = tracks.length;
    let out = '';
    if (h.n) out += `<button type="button" class="sim-btn" data-sim-act="home" data-record="${esc(key)}" title="Bring all of it home${h.n >= 2 ? ' — ' + rules().record_share + '% of its tracks' : ''}">Bring ${h.n === all ? 'it all' : 'the rest'} home · ${h.cost}</button>`;
    else if (h.back) out += `<button type="button" class="sim-btn" data-sim-act="home" data-record="${esc(key)}">Bring back · free</button>`;
    if (b.n) out += `<button type="button" class="sim-btn" data-sim-act="buy" data-record="${esc(key)}" title="Buy all of it${b.n >= 2 ? ' — ' + rules().record_share + '% of its tracks' : ''}">Buy ${b.n === all ? 'it all' : 'the rest'} · ${b.cost}</button>`;
    else out += `<span class="sim-state">All yours</span>`;
    const held = tracks.filter(t => t.sim && (t.sim.state === 'home' || t.sim.state === 'bought') && t.sim.url);
    if (held.length) out = `<button type="button" class="sim-btn" data-sim-act="play-record" data-record="${esc(key)}">▶ Play</button>`
        + `<button type="button" class="sim-btn sim-btn--quiet" data-sim-act="cue-record" data-record="${esc(key)}" data-snt-keep title="Add what you hold of it to the cue">＋ Cue</button>` + out;
    return `<span class="sim-acts">${out}</span>`;
}

// ── tracks grouped into their records (a public room) ──
function recordsHtml(tracks, o) {
    o = o || {};
    const recs = new Map();
    for (const t of tracks) {
        const k = (t.sim && t.sim.record) || ('t' + t.id);
        if (!recs.has(k)) recs.set(k, []);
        recs.get(k).push(t);
    }
    let h = '';
    for (const [key, ts] of recs) {
        ts.sort((a, b) => ((a.sim.disc_no || 1) - (b.sim.disc_no || 1)) || ((a.sim.track_no || 0) - (b.sim.track_no || 0)));
        const f = ts[0], s = f.sim;
        const cov = f.has_art ? `<img class="sim-rec__cov" src="${o.cover ? o.cover(f) : '/api/gr/art/' + f.id + '?v=' + (f.art_v || 0)}" alt="" loading="lazy">`
                              : `<div class="sim-rec__cov sim-rec__cov--none"><span>${esc((s.record_title || f.title || '♪').trim().charAt(0).toUpperCase())}</span></div>`;
        const meta = [KIND[s.record_kind] || '', f.year || '', s.record_tracks > 1 ? s.record_tracks + ' tracks' : ''].filter(Boolean).join(' · ');
        h += `<div class="sim-rec" data-record="${esc(key)}">${cov}
            <div class="sim-rec__body">
              <div class="sim-rec__t">${esc(s.record_title || f.title)}</div>
              <div class="sim-rec__s">${esc(meta)}</div>
              ${ts.length > 1 ? `<div class="sim-rec__whole">${recordActs(key, ts)}</div>` : (RECS.set(key, ts), '')}
              <ol class="sim-rec__tracks">${ts.map(t => `<li class="sim-tr${t.sim.state ? ' is-' + t.sim.state : ''}">
                  <span class="sim-tr__n">${t.sim.track_no || ''}</span>
                  <span class="sim-tr__t">${esc(t.title)}${t.artist && t.artist !== o.artist ? `<em>${esc(t.artist)}</em>` : ''}</span>
                  <span class="sim-tr__d">${mmss(t.duration_s)}</span>
                  ${trackActs(t)}${o.extra ? o.extra(t) : ''}</li>`).join('')}</ol>
            </div></div>`;
    }
    return `<div class="sim-recs">${h}</div>`;
}

// ── a small window to be sure ──
function ask(anchor, a) {
    return new Promise(done => {
        document.querySelectorAll('.sim-ask').forEach(x => x.remove());
        const el = document.createElement('div');
        el.className = 'sim-ask';
        el.setAttribute('role', 'dialog');
        el.innerHTML = `<div class="sim-ask__t">${esc(a.title)}</div><div class="sim-ask__p">${a.html}</div>
            <div class="sim-ask__b"><button type="button" class="sim-btn${a.danger ? ' sim-btn--danger' : ' sim-btn--primary'}" data-y>${esc(a.yes)}</button>
            <button type="button" class="sim-btn" data-n>${esc(a.no || 'Keep it')}</button></div>`;
        document.body.appendChild(el);
        const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : null;
        const W = Math.min(360, innerWidth - 24);
        el.style.width = W + 'px';
        const clear = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--snt-clear')) || 0;
        let x = r ? Math.min(Math.max(12, r.left), innerWidth - W - 12) : (innerWidth - W) / 2;
        let y = r ? r.bottom + 8 : innerHeight / 3;
        el.style.left = x + 'px'; el.style.top = y + 'px';
        const hgt = el.getBoundingClientRect().height;
        if (y + hgt > innerHeight - clear - 12) el.style.top = Math.max(12, (r ? r.top : innerHeight / 2) - hgt - 8) + 'px';
        const end = v => { el.remove(); document.removeEventListener('keydown', key, true); document.removeEventListener('pointerdown', away, true); done(v); };
        const key = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); end(false); } };   // (only this question closes — not the crate or the page behind it)
        const away = e => { if (!el.contains(e.target)) end(false); };
        el.querySelector('[data-y]').onclick = () => end(true);
        el.querySelector('[data-n]').onclick = () => end(false);
        document.addEventListener('keydown', key, true);
        setTimeout(() => document.addEventListener('pointerdown', away, true), 0);
        el.querySelector(a.danger ? '[data-n]' : '[data-y]').focus();
    });
}

// a line that says what happened (or why not), beside the button pressed
function say(anchor, words, bad) {
    document.querySelectorAll('.sim-said').forEach(x => x.remove());
    const el = document.createElement('div');
    el.className = 'sim-said' + (bad ? ' sim-said--bad' : '');
    el.textContent = words;
    document.body.appendChild(el);
    const r = anchor && anchor.isConnected ? anchor.getBoundingClientRect() : null;
    const W = Math.min(340, innerWidth - 24);
    el.style.maxWidth = W + 'px';
    el.style.left = (r ? Math.min(Math.max(12, r.left), innerWidth - W - 12) : 12) + 'px';
    el.style.top = (r ? Math.max(12, r.top - 8 - 44) : 12) + 'px';
    setTimeout(() => el.classList.add('gone'), bad ? 6500 : 2800);
    setTimeout(() => el.remove(), bad ? 7200 : 3400);
}

function nameOf(btn) {
    if (btn.dataset.record) { const ts = RECS.get(btn.dataset.record) || []; const f = ts[0]; return f ? '“' + ((f.sim && f.sim.record_title) || f.title) + '”' : 'this record'; }
    const t = REG.get(+btn.dataset.id); return t ? '“' + t.title + '”' : 'this track';
}

async function act(btn) {
    const what = btn.dataset.simAct;
    const body = btn.dataset.record ? { record: btn.dataset.record } : { track_id: +btn.dataset.id };
    if (what === 'play') return playTrack(+btn.dataset.id);
    if (what === 'play-record') return playRecord(btn.dataset.record);
    if (what === 'cue' || what === 'cue-record') {
        const ts = (what === 'cue' ? [REG.get(+btn.dataset.id)] : (RECS.get(btn.dataset.record) || [])).filter(t => t && (t.sim ? t.sim.url : t.url));
        const d = deck();
        if (!d || !ts.length) return;
        const n = await d.add(ts.map(embedOf), { autostart: false });      // (＋ Cue never starts the deck: ▶ Play is beside it)
        return say(btn, n ? (n === 1 ? 'In the cue' : n + ' in the cue') : 'That couldn’t go in the cue');
    }
    if (what === 'grupa') {
        const t = REG.get(+btn.dataset.id); if (!t) return;
        const e = embedOf(t);
        return withGrupaUI(() => GrupaUI.addTo({ url: e.url, title: e.title, subtitle: e.artist, image: e.image_url }, btn));
    }
    const m = await me();
    if (what === 'out') {
        const r = rules();
        const back = new Date(Date.now() + r.wait_days * 864e5);
        const ok = await ask(btn, {
            title: 'Take ' + nameOf(btn) + ' out of your room?',
            html: `You won't get the credit back, and it can't come back for <b>${r.wait_days} days</b> — until <b>${esc(day(back.toISOString()))}</b>. After that, bringing it back is free.`,
            yes: 'Take it out', no: 'Keep it', danger: true });
        if (!ok) return;
    }
    if (what === 'buy') {
        const ts = btn.dataset.record ? (RECS.get(btn.dataset.record) || []) : [REG.get(+btn.dataset.id)].filter(Boolean);
        const q = quote(ts, 'buy');
        const ok = await ask(btn, { title: 'Buy ' + nameOf(btn) + '?',
            html: `${cr(q.cost)}${m ? ' of your ' + m.credits : ''}. ${q.n > 1 ? 'They stay' : 'It stays'} yours, and take${q.n > 1 ? '' : 's'} no room.`,
            yes: 'Buy · ' + q.cost, no: 'Not now' });
        if (!ok) return;
    }
    btn.disabled = true;
    let d = {}, code = 0;
    try { const r = await fetch('/api/gr/sim/' + what, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); code = r.status; d = await r.json(); }
    catch (_) { d = { error: 'The Music Room can’t be reached right now.' }; }
    btn.disabled = false;
    if (code !== 200 || d.error) { say(btn, d.error || 'That didn’t work.', true); return; }
    if (ME && d.credits != null) ME.credits = d.credits;
    if (ME && d.room) ME.room = d.room;
    let words = '';
    if (what === 'home') words = d.already ? 'It’s already in your room.' : (d.brought ? (d.brought === 1 ? 'Brought home' : d.brought + ' tracks brought home') + ' · ' + cr(d.spent) : '') + (d.back ? (words ? ' · ' : '') + (d.back === 1 ? 'Back in your room' : d.back + ' back in your room') : '');
    if (what === 'buy') words = d.already ? 'It’s yours already.' : (d.bought === 1 ? 'Bought' : d.bought + ' tracks bought') + ' · in your records · ' + cr(d.spent);
    if (what === 'out') words = (d.out === 1 ? 'Taken out' : d.out + ' tracks taken out') + ' · back on ' + day(d.back_after);
    if (d.room) words += ` · room ${d.room.count} of ${d.room.space}`;
    say(btn, words + (d.credits != null ? ' · ' + cr(d.credits) + ' left' : ''));
    window.dispatchEvent(new CustomEvent('sim-changed', { detail: Object.assign({ what }, d) }));
    window.dispatchEvent(new CustomEvent('sim-me', { detail: ME }));
}

document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('[data-sim-act]');
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    act(b);
}, true);

// the "add to a grúpa" window lives in grupa_ui.js: fetched the first time it is asked for
function withGrupaUI(cb) {
    if (window.GrupaUI) return cb();
    if (!document.querySelector('link[data-grupa-css]')) {
        const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/static/css/grupa.css'; l.setAttribute('data-grupa-css', '1');
        document.head.appendChild(l);
    }
    if (document.querySelector('script[data-grupa-ui]')) { const wait = () => window.GrupaUI ? cb() : setTimeout(wait, 50); return wait(); }
    const s = document.createElement('script');
    s.src = '/static/js/grupa_ui.js'; s.setAttribute('data-grupa-ui', '1'); s.onload = cb;
    document.head.appendChild(s);
}

// ── playing your own: through the deck (your own Spotify, or Spotify's player on the page) ──
const embedOf = t => ({ kind: 'embed', url: t.sim ? t.sim.url : t.url, source: 'spotify', stream_type: 'track',
    title: t.title || '', artist: t.artist || '', duration_sec: t.duration_s || 0,
    image_url: t.cover_id || t.has_art ? '/api/gr/art/' + (t.cover_id || t.id) + '?v=' + (t.art_v || 0) : '' });
const deck = () => window.Seinnteoir || (window.parent !== window && window.parent.Seinnteoir) || null;
function played(id, via) { try { fetch('/api/gr/sim/played', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ track_id: id, via }), keepalive: true }); } catch (_) {} }
async function playList(ts, start, via) {
    const d = deck();
    const list = ts.filter(t => (t.sim ? t.sim.url : t.url));
    if (!d || !list.length) return;
    const i = Math.max(0, list.findIndex(t => t.id === start));
    await d.playAll(list.map(embedOf), i);
    played(list[i].id, via || 'shop');
}
function playTrack(id) {
    const t = REG.get(id); if (!t) return;
    const key = t.sim && t.sim.record;
    const ts = key && RECS.get(key) ? RECS.get(key) : [t];
    return playList(ts, id, 'track');
}
function playRecord(key) { const ts = RECS.get(key) || []; return playList(ts, (ts.find(t => t.sim && t.sim.url) || {}).id, 'record'); }

// ── My Room → Borrowed ──
// Daithí, 2026-11-25: "change 'from the shop' to 'borrowed'. this should only contain borrowed
// records. When a record is bought it lives in the records section." So this tab is what has been
// brought home (and what was taken out and waits its week — where it comes back from); a bought
// record is among Your records (bought(), mountBought(), and the room's own grid).
// the works this person has bought from digital artists, under their records (works.js draws them)
let worksAsk = null;
function mountArt(el, opts) {
    if (!el) return;
    if (!worksAsk) worksAsk = window.Works ? Promise.resolve() : new Promise(done => {
        const s = document.createElement('script'); s.src = '/static/js/works.js'; s.onload = done; s.onerror = done; document.head.appendChild(s);
    });
    worksAsk.then(() => { if (window.Works && el.isConnected) Works.mountBought(el, opts); });
}

// one record from /api/gr/sim/mine → its tracks as the buttons and the deck want them
function tracksOf(r) {
    const ts = r.tracks.map(t => Object.assign({}, t, { sim: { state: t.state, back_after: t.back_after, url: t.url, buy_cost: t.buy_cost, home_cost: t.state === 'out' ? 0 : null, record: r.key, record_title: r.title, track_no: t.track_no, disc_no: t.disc_no },
        cover_id: r.cover_id, art_v: r.art_v, record_artist: r.artist, record_year: r.year, owner: r.owner }));
    ts.forEach(t => REG.set(t.id, t));
    RECS.set(r.key, ts);
    return ts;
}

function mountMine(host, opts) {
    opts = opts || {};
    let want = 'home', data = null;
    const paint = () => {
        if (!data) { host.innerHTML = `<div class="sim-mine"><p class="sim-p">Looking…</p></div>`; return; }
        if (data.error) { host.innerHTML = `<div class="sim-mine"><p class="sim-p">${esc(data.error)}</p></div>`; return; }
        const m = data.me || {}, recs = data.records || [];
        if (!m.on) { host.innerHTML = `<div class="sim-mine"><h2 class="sim-h">Borrowed</h2><p class="sim-p">The shop isn’t running the credits trial right now.</p></div>`; return; }
        const n = s => recs.reduce((a, r) => a + (r.counts[s] || 0), 0);
        if (want === 'out' && !n('out')) want = 'home';
        const shown = recs.filter(r => r.counts[want]);
        let h = `<div class="sim-mine">
          <div class="sim-head"><h2 class="sim-h">Borrowed</h2>
            <div class="sim-meter"><span><b>${m.credits}</b> credits</span><span>room <b>${m.room.count}</b> of ${m.room.space}</span></div></div>`;
        if (n('out')) h += `<div class="sim-tabs" role="tablist">${[['home', 'In your room', n('home')], ['out', 'Taken out', n('out')]]
            .map(([k, l, c]) => `<button type="button" class="sim-tab${want === k ? ' on' : ''}" data-want="${k}">${l}<span>${c}</span></button>`).join('')}</div>`;
        if (!shown.length) h += `<p class="sim-p sim-empty">Nothing borrowed yet.</p>
            <p><a class="sim-btn" href="/explore3d?view=shop" ${opts.openPage ? 'data-page' : ''}>Go record shopping</a></p>`;
        for (const r of shown) {
            const ts = tracksOf(r);
            const cov = r.cover_id ? `<img class="sim-rec__cov" src="/api/gr/art/${r.cover_id}?v=${r.art_v || 0}" alt="" loading="lazy">` : `<div class="sim-rec__cov sim-rec__cov--none"><span>${esc((r.title || '♪').charAt(0).toUpperCase())}</span></div>`;
            const mineTs = ts.filter(t => t.state === want);
            const meta = [KIND[r.kind] || '', r.year || '', r.tracks_total > 1 ? `${mineTs.length} of ${r.tracks_total} tracks` : ''].filter(Boolean).join(' · ');
            const whole = [];
            if (want === 'home') {
                whole.push(`<button type="button" class="sim-btn" data-sim-act="play-record" data-record="${esc(r.key)}">▶ Play</button>`);
                whole.push(`<button type="button" class="sim-btn sim-btn--quiet" data-sim-act="cue-record" data-record="${esc(r.key)}" data-snt-keep title="Add what you hold of it to the cue">＋ Cue</button>`);
            }
            if (r.owner && r.owner.handle) whole.push(`<a class="sim-btn sim-btn--quiet" href="/rooms/${encodeURIComponent(r.owner.handle)}?overlay=1" data-room="${esc(r.owner.handle)}" title="The rest of the record, and more of theirs">${esc(r.owner.name || r.owner.handle)}’s room ↗</a>`);
            if (want === 'home' && mineTs.length > 1) whole.push(`<button type="button" class="sim-btn sim-btn--quiet" data-sim-act="out" data-record="${esc(r.key)}">Take it all out</button>`);
            h += `<div class="sim-rec">${cov}<div class="sim-rec__body">
                <div class="sim-rec__t">${esc(r.title)}</div>
                <div class="sim-rec__s">${esc([r.artist, meta].filter(Boolean).join(' · '))}</div>
                <div class="sim-rec__whole"><span class="sim-acts">${whole.join('')}</span></div>
                <ol class="sim-rec__tracks">${mineTs.map(t => `<li class="sim-tr is-${t.state}">
                    <span class="sim-tr__n">${t.track_no || ''}</span>
                    <span class="sim-tr__t">${esc(t.title)}${t.artist && t.artist !== r.artist ? `<em>${esc(t.artist)}</em>` : ''}</span>
                    <span class="sim-tr__d">${mmss(t.duration_s)}</span>${trackActs(t)}</li>`).join('')}</ol>
              </div></div>`;
        }
        h += `<div class="sim-art" data-sim-art></div></div>`;
        host.innerHTML = h;
        mountArt(host.querySelector('[data-sim-art]'), opts);       // works bought from digital artists (works.js)
        host.querySelectorAll('[data-want]').forEach(b => b.onclick = () => { want = b.dataset.want; paint(); });
        if (opts.openPage) host.querySelectorAll('[data-room], [data-page]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); opts.openPage(a.getAttribute('href')); }));
    };
    const load = async () => {
        try { const r = await fetch('/api/gr/sim/mine'); const d = await r.json(); data = r.ok ? d : { error: d.error || 'What you have borrowed can’t be read right now.' }; }
        catch (_) { data = { error: 'The Music Room can’t be reached right now.' }; }
        if (data && data.me) { ME = data.me; window.dispatchEvent(new CustomEvent('sim-me', { detail: ME })); }
        paint();
    };
    const onChange = () => load();
    window.addEventListener('sim-changed', onChange);
    paint(); load();
    return { refresh: load, destroy() { window.removeEventListener('sim-changed', onChange); host.innerHTML = ''; } };
}

// ── bought: among Your records ──
// A bought record from the playlist shop has no file (it plays from Spotify), so it is not a row
// in the library. It is shown with the records all the same: the room's grid leads with these, and
// a room with no records of its own shows them as its records (mountBought).
let boughtAsk = null, BOUGHT = [];
function bought(fresh) {
    if (!boughtAsk || fresh) boughtAsk = fetch('/api/gr/sim/mine').then(r => r.ok ? r.json() : null).catch(() => null).then(d => {
        if (!d || !d.me || !d.me.on) return (BOUGHT = []);
        const out = [];
        for (const r of d.records || []) for (const t of tracksOf(r)) if (t.state === 'bought' && t.url) out.push(t);
        return (BOUGHT = out);
    });
    return boughtAsk;
}
window.addEventListener('sim-changed', () => { boughtAsk = null; });

const coverOf = (t, cls) => t.cover_id ? `<img class="${cls}" src="/api/gr/art/${t.cover_id}?v=${t.art_v || 0}" alt="" loading="lazy">`
    : `<div class="${cls} ${cls}--none"><span>${esc((t.title || '♪').trim().charAt(0).toUpperCase())}</span></div>`;

// a bought record's small window: what it is, and what can be done with it
function openBought(t, anchor, opts) {
    opts = opts || {};
    t = (t && t.id != null && REG.get(t.id)) || t; if (!t) return;
    REG.set(t.id, t);
    document.querySelectorAll('.sim-held').forEach(x => x.remove());
    const el = document.createElement('div');
    el.className = 'sim-held'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', t.title || 'A record of yours');
    const rec = t.sim && t.sim.record_title && t.sim.record_title !== t.title ? t.sim.record_title : '';
    const o = t.owner && t.owner.handle ? t.owner : null;
    el.innerHTML = `<button type="button" class="sim-held__x" aria-label="Close" title="Close">✕</button>
        <div class="sim-held__top">${coverOf(t, 'sim-held__cov')}
          <div class="sim-held__names"><div class="sim-held__t">${esc(t.title)}</div>
            <div class="sim-held__s">${esc(t.artist || t.record_artist || '')}</div>
            <div class="sim-held__s">${esc([rec, t.record_year || '', mmss(t.duration_s)].filter(Boolean).join(' · '))}</div>
            <div class="sim-held__s"><span class="sim-state">Yours</span> plays from Spotify</div></div></div>
        <div class="sim-held__acts"><span class="sim-acts">${heldActs(t.id)}</span>
          ${o ? `<a class="sim-btn sim-btn--quiet" href="/rooms/${encodeURIComponent(o.handle)}?overlay=1" data-room="${esc(o.handle)}">${esc(o.name || o.handle)}’s room ↗</a>` : ''}</div>`;
    document.body.appendChild(el);
    const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : null;
    const W = Math.min(400, innerWidth - 24);
    el.style.width = W + 'px';
    const clear = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--snt-clear')) || 0;
    const top0 = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 0;
    const hgt = el.getBoundingClientRect().height;
    let x = r ? Math.min(Math.max(12, r.left), innerWidth - W - 12) : (innerWidth - W) / 2;
    let y = r ? r.top + Math.min(r.height, 120) : innerHeight / 3;
    y = Math.max(top0 + 8, Math.min(y, innerHeight - clear - hgt - 12));
    el.style.left = x + 'px'; el.style.top = y + 'px';
    const end = () => { el.remove(); document.removeEventListener('keydown', key, true); document.removeEventListener('pointerdown', away, true); };
    const key = e => { if (e.key === 'Escape' && !document.querySelector('.gp-pick, .sim-ask')) { e.preventDefault(); e.stopPropagation(); end(); } };
    const away = e => { if (!el.contains(e.target) && !(e.target.closest && e.target.closest('.gp-pick, .sim-said'))) end(); };
    el.querySelector('.sim-held__x').onclick = end;
    const room = el.querySelector('[data-room]');
    if (room && opts.openPage) room.addEventListener('click', e => { e.preventDefault(); end(); opts.openPage(room.getAttribute('href')); });
    document.addEventListener('keydown', key, true);
    setTimeout(() => document.addEventListener('pointerdown', away, true), 0);
    return el;
}

// the bought records as cards — for a room with no records of its own, where they ARE the records
function mountBought(host, opts) {
    opts = opts || {};
    let list = [];
    const paint = () => {
        if (!list.length) { host.innerHTML = ''; if (opts.onCount) opts.onCount(0); return; }
        host.innerHTML = `<div class="sim-own">${list.map(t => `<div class="sim-own__card" data-own="${t.id}" tabindex="0" role="button" aria-label="${esc(t.title)}">
              <div class="sim-own__covbox">${coverOf(t, 'sim-own__cov')}
                <button type="button" class="sim-own__cue" data-sim-act="cue" data-id="${t.id}" data-snt-keep title="Add it to the cue">+▶</button></div>
              <div class="sim-own__t">${esc(t.title)}</div><div class="sim-own__a">${esc(t.artist || t.record_artist || '')}</div></div>`).join('')}</div>`;
        host.querySelectorAll('[data-own]').forEach(c => {
            const go = () => openBought(REG.get(+c.dataset.own), c, opts);
            c.addEventListener('click', e => { if (!e.target.closest('[data-sim-act]')) go(); });
            c.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
        });
        if (opts.onCount) opts.onCount(list.length);
    };
    const load = async fresh => { list = (await bought(fresh)) || []; paint(); };
    const onChange = () => load(true);
    window.addEventListener('sim-changed', onChange);
    load();
    return { refresh: () => load(true), count: () => list.length, destroy() { window.removeEventListener('sim-changed', onChange); host.innerHTML = ''; } };
}

window.SimShop = { me, on: () => !!(ME && ME.on), rules, quote, trackActs, recordActs, recordsHtml, mountMine, bought, mountBought, openBought, playTrack, playRecord, ask, say, embedOf, cr };
})();
