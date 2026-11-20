// =============================================================
// record_shop.js — Record shopping (Explore's fifth door).
//
// Three ways to come across a record, and only ever a record that can be
// bought in the Music Room (David, 2026-11-16):
//
//   CRATES   — you are handed a crate: up to 25 records that a seller put
//              together, or that the shop put together from its shelves by a
//              rule you chose (anywhere, or a genre, a place, some years).
//              You go through it one record at a time. Three crates a day;
//              a crate stays open until the day ends.
//   COUNTER  — ask for something in your own words (three a day). One person
//              answers with one record and a line of why. And you can be
//              handed someone else's question to answer (three a day).
//   BLIND    — a record plays with no name and no cover. You decide, and only
//              then is it turned over.
//
// In all three a record can only do three things: be listened to (here, and
// nowhere else, as the shop's listening copy), go in the basket (to borrow or
// to buy), or be noted for later with a line of why (wish_note.js → the
// wishlist, which holds 100).
//
//   RecordShop.mount(host, { tab, openWishlist() })  → the thing itself
//   RecordShop.open(tab) · .leave() (stops the sound) · .escape() (closes what is open; true if it did)
//
// record_shop.py is the app's side; gr_shop.py is the rooms server's.
// The words are functional; David coins the real ones.
// =============================================================
window.RecordShop = (function () {
'use strict';

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const euro = c => '€' + ((c || 0) / 100).toFixed(2);
const clock = s => { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const poss = n => { n = (n || '').trim(); return n ? n + (/s$/i.test(n) ? '’' : '’s') : 'someone’s'; };
const JSONH = { 'Content-Type': 'application/json' };
async function call(url, method, body) {
    try {
        const r = await fetch(url, { method: method || 'GET', headers: body ? JSONH : undefined, body: body ? JSON.stringify(body) : undefined });
        const d = await r.json().catch(() => ({}));
        return { ok: r.ok, status: r.status, d };
    } catch (_) { return { ok: false, status: 0, d: { error: 'The app can’t be reached.' } }; }
}

let host = null, opts = {}, bodyEl = null;
let S = null;                       // the shop as it is for me today (null until first read)
let tab = 'crates';
let ask = { genres: [], place: '', decades: [] };
let crate = null, idx = 0, seen = new Set();
let C = null, Q = null, A = null;   // the counter: my questions · the question in my hand · my answer in the making
let fresh = new Set();              // answers I am seeing for the first time on this visit
let B = null;                       // blind: { id, duration_s, record?, choice?, mode? }
let draftAsk = '';
let note = '';                      // one line to say back (a refusal, a thing done)
const REC = new Map();              // every record painted, by its number

// ───────────────────────── listening ─────────────────────────
// One player for the whole shop, in the page: it stops when you move to the
// next record, leave the crate, or leave the shop. Its loudness follows the
// deck's dial, and starting it quiets the deck.
// ONE PLAY (David, 2026-11-20: "whole records but only one play. If they want to
// hear it again they have to buy or borrow it"): pressing Listen starts the one
// play of that record — the whole of it, paused and carried on and moved through
// as you like — and once it ends, or you move on, it is heard. The rooms server
// keeps count (gr_shop.py); the app holds the sound only while the play lasts.
const audio = new Audio(); audio.preload = 'none';
let playing = null;                 // { key, spec, play, state: loading | playing | paused | error, err }
const heardTracks = new Set(), heardBlind = new Set();
let HEARD_LINE = 'You’ve heard this one. To hear it again, borrow it or buy it.';
// the credits trial (gr_sim; sim_shop.js): bring home / buy with credits instead of the basket
const simOn = () => !!(S && S.sim && S.sim.on && window.SimShop);
const isSim = r => !!(simOn() && r && r.sim);
const ONE_PLAY = 'Each record plays once here — all of it, if you like.';
function isHeard(spec, r) { return spec.kind === 'blind' ? heardBlind.has(+spec.ctx) || !!(B && B.heard && +spec.ctx === B.id) : heardTracks.has(+spec.track) || !!(r && r.heard); }
function markHeard(spec) { if (spec.kind === 'blind') heardBlind.add(+spec.ctx); else heardTracks.add(+spec.track); }
function endPlay(ticket) { if (ticket) fetch('/api/gr/shop/play/' + encodeURIComponent(ticket) + '/end', { method: 'POST' }).catch(() => {}); }

function deckState() { try { return (window.Seinnteoir && Seinnteoir.getState && Seinnteoir.getState()) || null; } catch (_) { return null; } }
function deckVolume() { const st = deckState(); return st && typeof st.volume === 'number' ? Math.max(0, Math.min(1, st.volume)) : null; }
function quietDeck() {
    const st = deckState(); if (!st) return;
    if (st.playing) fetch('/api/seinnteoir/pause', { method: 'POST', headers: JSONH, body: JSON.stringify({ fade_ms: 200 }) }).catch(() => {});
    else if (st.guest && st.guest.playing && st.guest.control) fetch('/api/spotify/control', { method: 'POST', headers: JSONH, body: JSON.stringify({ action: 'pause' }) }).catch(() => {});
}
setInterval(() => { if (!playing) return; const v = deckVolume(); if (v != null && Math.abs(audio.volume - v) > .004) audio.volume = v; }, 600);

function stop() {
    if (!playing && !audio.getAttribute('src')) return;
    try { audio.pause(); } catch (_) {}
    audio.removeAttribute('src');
    try { audio.load(); } catch (_) {}
    if (playing && playing.play) { endPlay(playing.play); markHeard(playing.spec); }      // moving on ends the one play
    playing = null; paintListen();
}
async function listen(key, spec) {
    if (playing && playing.key === key && playing.play && playing.state !== 'error') {   // the same play: pause it, or carry on
        if (audio.paused) audio.play().catch(() => {}); else audio.pause();
        return;
    }
    if (isHeard(spec)) { paintListen(); return; }
    stop();
    const p = playing = { key, spec, state: 'loading' };
    paintListen();
    quietDeck();
    let v = deckVolume();
    if (v == null) { try { v = (await (await fetch('/api/seinnteoir/state', { cache: 'no-store' })).json()).volume; } catch (_) { v = null; } }
    const r = await call('/api/gr/shop/play', 'POST', spec);
    if (playing !== p) { if (r.ok) { endPlay(r.d.play); markHeard(spec); } paintListen(); return; }
    if (!r.ok) {
        p.state = 'error'; p.err = r.d.heard ? HEARD_LINE : (r.d.error ? r.d.error.charAt(0).toUpperCase() + r.d.error.slice(1).replace(/\.?$/, '.') : 'That record can’t be played right now.');
        if (r.d.heard) { markHeard(spec); playing = null; }
        paintListen(); return;
    }
    if (r.d.stream) {
        // a record from the playlist shop (gr_sim): its one play streams from the listener's own
        // Spotify through the deck, and leaves the deck's cue as soon as it stops playing
        const st = r.d.stream, rec = spec.kind !== 'blind' ? REC.get(spec.track) : null;
        markHeard(spec);
        const d = window.Seinnteoir;
        if (d && d.playOnce) await d.playOnce({ kind: 'embed', url: st.url, source: 'spotify', stream_type: 'track',
            title: spec.kind === 'blind' ? 'Blind · the record in front of you' : (st.title || ''), artist: spec.kind === 'blind' ? '' : (st.artist || ''),
            duration_sec: st.duration_s || 0, image_url: rec && rec.has_art ? art(rec) : '' });
        playing = null;
        p.state = 'deck';
        paintListen();
        const m = host && host.querySelector(`[data-listenmsg="${CSS.escape(key)}"]`);
        if (m) { m.textContent = 'Playing once, in your deck. To hear it again, bring it home or buy it.'; m.classList.remove('rs-listenmsg--quiet'); }
        return;
    }
    p.play = r.d.play;
    audio.volume = typeof v === 'number' ? Math.max(0, Math.min(1, v)) : .8;
    audio.src = r.d.url;
    audio.play().catch(() => {});                                            // (a refusal arrives as the 'error' below)
}
audio.addEventListener('playing', () => { if (playing) { playing.state = 'playing'; paintListen(); } });
audio.addEventListener('pause', () => { if (playing && playing.state !== 'error') { playing.state = 'paused'; paintListen(); } });
audio.addEventListener('waiting', () => { if (playing && playing.state === 'playing') { playing.state = 'loading'; paintListen(); } });
audio.addEventListener('timeupdate', paintTime);
audio.addEventListener('durationchange', paintTime);
audio.addEventListener('ended', () => { if (playing && playing.play) stop(); });   // the whole record: heard
audio.addEventListener('error', () => {
    const p = playing; if (!p || !p.play || !audio.getAttribute('src')) return;
    p.state = 'error'; p.err = 'That play has ended. To hear it again, borrow it or buy it.';
    endPlay(p.play); markHeard(p.spec); p.play = null;
    paintListen();
});

function listenRow(key, spec, total, r) {
    const off = S && S.listening === false;
    if (isSim(r) && (r.sim.state === 'home' || r.sim.state === 'bought'))
        return `<div class="rs-listen rs-listen--yours"><span class="rs-state">It’s in your room</span>${r.sim.url ? `<button type="button" class="sim-btn" data-sim-act="play" data-id="${r.id}">▶ Play</button>` : ''}</div>`;
    if (r && (r.purchased || r.borrow_id)) return `<div class="rs-listen rs-listen--yours"><span class="rs-state">It’s in your room — play it there</span></div>`;
    return `<div class="rs-listen" data-listen="${esc(key)}" data-kind="${esc(spec.kind)}" data-ctx="${+spec.ctx || 0}" data-track="${+spec.track || 0}" data-total="${Number(total) || 0}">
        <button type="button" class="rs-btn rs-btn--primary rs-play" data-act="listen"${off ? ' disabled' : ''}>Listen</button>
        <div class="rs-seek" data-act="seek" title="Move through the record"><i></i></div>
        <span class="rs-time">0:00 / ${clock(total)}</span>
      </div><div class="rs-listenmsg" data-listenmsg="${esc(key)}">${off ? 'The shop can’t play records on this server yet.' : ''}</div>`;
}
function specOf(row) { return { kind: row.dataset.kind, ctx: +row.dataset.ctx || 0, track: +row.dataset.track || 0 }; }
function paintListen() {
    if (!host) return;
    host.querySelectorAll('.rs-listen').forEach(row => {
        const mine = playing && playing.key === row.dataset.listen, st = mine ? playing.state : 'idle';
        const spec = specOf(row), heard = !mine && isHeard(spec, spec.kind !== 'blind' ? REC.get(spec.track) : null);
        const b = row.querySelector('.rs-play');
        if (b) {
            b.textContent = heard ? 'Heard' : st === 'loading' ? 'Fetching…' : st === 'playing' ? 'Pause' : st === 'paused' ? 'Carry on' : 'Listen';
            b.disabled = heard || (S && S.listening === false);
            b.title = heard ? HEARD_LINE : ONE_PLAY;
        }
        row.classList.toggle('on', !!mine);
        row.classList.toggle('is-heard', heard);
        const m = host.querySelector(`[data-listenmsg="${CSS.escape(row.dataset.listen)}"]`);
        if (m && !(S && S.listening === false)) {
            m.textContent = mine && st === 'error' ? playing.err : heard ? HEARD_LINE : (!mine ? ONE_PLAY : '');
            m.classList.toggle('rs-listenmsg--quiet', !heard && !(mine && st === 'error'));
        }
        if (!mine) { const i = row.querySelector('.rs-seek i'); if (i) i.style.width = '0'; const t = row.querySelector('.rs-time'); if (t) t.textContent = '0:00 / ' + clock(+row.dataset.total); }
    });
    paintTime();
}
function paintTime() {
    if (!host || !playing) return;
    const row = host.querySelector(`.rs-listen[data-listen="${CSS.escape(playing.key)}"]`); if (!row) return;
    const total = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : +row.dataset.total || 0;
    const i = row.querySelector('.rs-seek i'), t = row.querySelector('.rs-time');
    if (i) i.style.width = total ? Math.min(100, 100 * audio.currentTime / total) + '%' : '0';
    if (t) t.textContent = clock(audio.currentTime) + ' / ' + clock(total);
}

// ───────────────────────── small pieces ─────────────────────────
const art = r => (r && r.has_art) ? `/api/gr/art/${r.id}?v=${r.art_v || 0}` : '';
const initial = r => esc(((r && (r.title || r.artist)) || '?').trim().charAt(0).toUpperCase() || '?');
function thumb(r) { const a = art(r); return `<span class="rs-thumb">${a ? `<img src="${esc(a)}" alt="" loading="lazy" onerror="this.remove()">` : ''}<span>${initial(r)}</span></span>`; }
function keep(list) { (list || []).forEach(r => { if (r && r.id != null) REC.set(r.id, r); }); return list; }
const inBasket = id => (S && S.basket && S.basket[String(id)]) || '';
// (the credits trial: what is brought home or bought, where the basket was)
const kept = r => simOn() ? !!(r && ((r.sim && (r.sim.state === 'home' || r.sim.state === 'bought')) || r.purchased || r.borrow_id)) : !!inBasket(r && r.id);
const isNoted = id => !!(S && S.wish && (S.wish.ids || []).includes(id));
const leftLine = (n, of) => `${n} of ${of} left today`;

// what you can do with a record: basket (to borrow, to buy), note it. Nothing else.
function simActs(r) {
    // bring home / buy with credits; the whole record when it has more than this track
    let h = SimShop.trackActs(r, { noOut: true, noPlay: true });      // (Play sits on the listening line)
    if (r.sim.record_tracks > 1 && r.sim.record) h += `<button type="button" class="sim-btn sim-btn--quiet" data-act="record" data-key="${esc(r.sim.record)}" title="Every track of “${esc(r.sim.record_title)}”">The whole record · ${r.sim.record_tracks} tracks</button>`;
    return h;
}
function fileActs(r) {
    // a record FILE (an artist's own upload) while the trial runs: brought home or bought with credits too
    if (r.purchased) return `<span class="rs-state">Yours already</span>`;
    const R = (S.sim && S.sim.rules) || { home_cost: 1, buy_cost: 3 };
    return (r.borrow_id ? `<span class="rs-state">At home</span>` : `<button type="button" class="sim-btn" data-act="file-home" data-id="${r.id}">Bring home · ${R.home_cost}</button>`)
        + `<button type="button" class="sim-btn" data-act="file-buy" data-id="${r.id}">Buy · ${r.borrow_id ? Math.max(0, R.buy_cost - R.home_cost) : R.buy_cost}</button>`;
}
function actsFor(r, more) {
    const b = inBasket(r.id), price = r.buy_now_cents != null ? r.buy_now_cents : r.price_cents;
    let h = '';
    if (simOn()) {
        h += isSim(r) ? simActs(r) : fileActs(r);
        h += `<button type="button" class="rs-btn${isNoted(r.id) ? ' on' : ''}" data-act="note" data-id="${r.id}" title="Keep its name and why you liked it on your wishlist">${isNoted(r.id) ? 'Noted' : 'Note it'}</button>`;
        return `<div class="rs-acts">${h}${more || ''}</div>`;
    }
    if (r.purchased) h += `<span class="rs-state">Yours already</span>`;
    else {
        if (r.borrow_id) h += `<span class="rs-state">Borrowed · in your room</span>`;
        else h += `<button type="button" class="rs-btn${b === 'borrow' ? ' on' : ''}" data-act="basket" data-mode="borrow" data-id="${r.id}" title="Put it in your basket, to borrow">${b === 'borrow' ? 'In basket · to borrow' : 'Borrow'}</button>`;
        h += `<button type="button" class="rs-btn${b === 'buy' ? ' on' : ''}" data-act="basket" data-mode="buy" data-id="${r.id}" title="Put it in your basket, to buy">${b === 'buy' ? 'In basket · to buy' : 'Buy ' + euro(price)}</button>`;
    }
    h += `<button type="button" class="rs-btn${isNoted(r.id) ? ' on' : ''}" data-act="note" data-id="${r.id}" title="Keep its name and why you liked it on your wishlist">${isNoted(r.id) ? 'Noted' : 'Note it'}</button>`;
    return `<div class="rs-acts">${h}${more || ''}</div>`;
}
function facts(r) {
    const rows = [['Label', r.label], ['Year', r.year], ['Genre', (r.genres || []).join(', ')], ['From', r.place], ['Sold by', r.owner && r.owner.name],
        ['Album', r.album && r.album !== r.title ? r.album : ''], ['Length', r.duration_s ? clock(r.duration_s) : '']].filter(x => x[1]);
    return rows.length ? `<dl class="rs-facts">${rows.map(x => `<div><dt>${x[0]}</dt><dd>${esc(x[1])}</dd></div>`).join('')}</dl>` : '';
}

// ───────────────────────── painting ─────────────────────────
function paint() {
    if (!host) return;
    const news = (S && S.counter && S.counter.new) || 0, w = (S && S.wish) || null;
    host.innerHTML = `
      <div class="rs-head">
        <div class="rs-tabs" role="tablist">
          <button type="button" role="tab" data-tab="crates" class="${tab === 'crates' ? 'on' : ''}">Crates</button>
          <button type="button" role="tab" data-tab="counter" class="${tab === 'counter' ? 'on' : ''}">The counter${news ? `<i class="rs-dot" title="${news} answered">${news}</i>` : ''}</button>
          <button type="button" role="tab" data-tab="blind" class="${tab === 'blind' ? 'on' : ''}">Blind</button>
        </div>
        ${w ? `<button type="button" class="rs-wish" data-act="wishlist" title="Open your wishlist">Wishlist <b>${w.count}</b> of ${w.max}</button>` : ''}
      </div>
      <div class="rs-body"></div>`;
    bodyEl = host.querySelector('.rs-body');
    if (!S) { bodyEl.innerHTML = `<p class="rs-quiet">Opening the shop…</p>`; return; }
    if (S.away) { bodyEl.innerHTML = `<section class="rs-sec"><div class="rs-kicker">Record shopping</div><h2 class="rs-h">The shop is shut.</h2><p class="rs-p">${esc(S.error || 'The rooms server can’t be reached.')}</p><div class="rs-bar"><button type="button" class="rs-btn" data-act="again">Try again</button></div></section>`; return; }
    bodyEl.innerHTML = tab === 'crates' ? (crate ? crateView() : cratesHome()) : tab === 'counter' ? counterView() : blindView();
    paintListen();
    fitSleeve();
    if (tab === 'counter' && A) paintFound();
}
// The record in front is seen whole: its sleeve is as big as the room between
// where it starts and where the shop's page ends (above the deck) — measured,
// because the crate's own heading may run to one line or four.
function fitSleeve() {
    if (!host) return;
    const view = host.closest('.rs-view'), st = host.querySelector('.rs-stack');
    if (!view || !st || !view.clientHeight) return;
    host.style.removeProperty('--rs-sleeve');
    const top = st.getBoundingClientRect().top - view.getBoundingClientRect().top + view.scrollTop;
    host.style.setProperty('--rs-sleeve', Math.max(170, Math.min(380, Math.floor(view.clientHeight - top - 20))) + 'px');
}

// ── crates: asking for one ──
function askOf() {
    const o = { genres: ask.genres.slice(), place: ask.place };
    if (ask.decades.length) { o.from = Math.min(...ask.decades); o.to = Math.max(...ask.decades) + 9; }
    return o;
}
function askWords() {
    const bits = ask.genres.slice(); if (ask.place) bits.push(ask.place);
    if (ask.decades.length) bits.push(Math.min(...ask.decades) + '–' + (Math.max(...ask.decades) + 9));
    return bits.join(' · ') || 'Anywhere';
}
function cratesHome() {
    const L = S.left.crates, F = S.facets || {}, any = !(ask.genres.length || ask.place || ask.decades.length);
    const chips = (key, list, label, isOn) => list.map(v => `<button type="button" class="rs-chip${isOn(v) ? ' on' : ''}" data-ask="${key}" data-v="${esc(v)}" aria-pressed="${isOn(v)}">${esc(label(v))}</button>`).join('');
    const rows = [];
    if ((F.genres || []).length) rows.push(['Genre', chips('genre', F.genres, v => v, v => ask.genres.some(g => g.toLowerCase() === String(v).toLowerCase()))]);
    if ((F.places || []).length) rows.push(['Place', chips('place', F.places, v => v, v => ask.place.toLowerCase() === String(v).toLowerCase())]);
    if ((F.decades || []).length) rows.push(['Years', chips('decade', F.decades, v => v + 's', v => ask.decades.includes(+v))]);
    const pulls = (S.pulls || []).map(p => `<button type="button" class="rs-pull" data-act="open" data-id="${p.id}">
          <span><span class="rs-pull__t">${esc(p.title || 'A crate')}</span><span class="rs-pull__s">${p.kind === 'made' ? 'A crate by ' + esc(p.by.name) : p.kind === 'plugin' ? 'Picked by the plug-in ' + esc(p.by.name) : 'Put together from the shelves'} · ${p.count} ${p.count === 1 ? 'record' : 'records'}</span></span>
          <span class="rs-pull__go">Open</span></button>`).join('');
    return `
      <section class="rs-sec">
        <div class="rs-kicker">Crates <span>${leftLine(L, S.limits.crates)}</span></div>
        <h2 class="rs-h">Pull a crate</h2>
        <p class="rs-p">Up to ${S.limits.crate} records from the shop, to go through one at a time. Take one from anywhere, or say what you are after.</p>
        ${!S.records ? `<p class="rs-msg">There are no records in the shop for you yet.</p>` : `
        <div class="rs-ask">
          <div class="rs-askrow"><span class="rs-k">From</span><div class="rs-chips"><button type="button" class="rs-chip${any ? ' on' : ''}" data-ask="any" aria-pressed="${any}">Anywhere</button></div></div>
          ${rows.map(r => `<div class="rs-askrow"><span class="rs-k">${r[0]}</span><div class="rs-chips">${r[1]}</div></div>`).join('')}
        </div>
        <div class="rs-bar">
          <button type="button" class="rs-btn rs-btn--primary" data-act="pull"${L ? '' : ' disabled'}>Pull a crate</button>
          <span class="rs-asked">${esc(askWords())}</span>
        </div>
        <div class="rs-msg" id="rs-pullmsg">${esc(note || (L ? '' : `That’s your ${S.limits.crates} crates for today. More tomorrow.`))}</div>`}
      </section>
      <section class="rs-sec">
        <div class="rs-kicker">Today’s crates <span>open until the day ends</span></div>
        ${pulls ? `<div class="rs-pulls">${pulls}</div>` : `<p class="rs-quiet">None yet.</p>`}
      </section>`;
}

// ── crates: going through one ──
function crateKey() { return 'mr_crate_' + (crate ? crate.id : 0); }
function crateRemember() { try { sessionStorage.setItem(crateKey(), JSON.stringify({ idx, seen: [...seen] })); } catch (_) {} }
function crateView() {
    const items = keep(crate.items), n = items.length, end = idx >= n;
    const by = crate.kind === 'made' ? `A crate by ${esc(crate.by.name)}` : crate.kind === 'plugin' ? `Picked by the plug-in ${esc(crate.by.name)}` : 'Put together from the shelves' +
        ((crate.sources || []).length ? ' · with records from ' + crate.sources.map(s => `${esc(s.crate)} (${esc(s.by)})`).join(', ') : '');
    const ticks = !n ? '' : `<div class="rs-ticks" role="group" aria-label="The records in this crate">${items.map((r, i) =>
        `<button type="button" data-act="jump" data-i="${i}" class="${[i === idx ? 'on' : '', seen.has(i) ? 'seen' : '', kept(r) ? 'b' : '', isNoted(r.id) ? 'w' : ''].join(' ').trim()}" title="Record ${i + 1}" aria-label="Record ${i + 1}"></button>`).join('')}</div>
        <div class="rs-legend"><span><i class="b"></i>${simOn() ? 'brought home or bought' : 'in your basket'}</span><span><i></i>noted</span><span class="rs-legend__r">open until the day ends</span></div>`;
    const top = `<div class="rs-crate__top">
        <div>
          <button type="button" class="rs-link" data-act="back">← Crates</button>
          <div class="rs-crate__name">${esc(crate.title || 'A crate')}</div>
          <div class="rs-crate__by">${by}</div>
          ${crate.note ? `<div class="rs-crate__note">${esc(crate.note)}</div>` : ''}
        </div>
        ${n ? `<div class="rs-step">
          <button type="button" data-act="prev" title="The record before (←)" aria-label="The record before"${idx ? '' : ' disabled'}>‹</button>
          <span>${end ? 'the end' : (idx + 1) + ' of ' + n}</span>
          <button type="button" data-act="next" title="${idx >= n - 1 ? 'The end of the crate' : 'The next record'} (→)" aria-label="The next record"${end ? ' disabled' : ''}>›</button>
        </div>` : ''}
      </div>${ticks}`;
    if (!n) return top + `<p class="rs-quiet">The records in this crate have left the shop.</p>`;
    if (end) {
        const nb = items.filter(r => kept(r)).length, nw = items.filter(r => isNoted(r.id)).length;
        return top + `<div class="rs-end">
            <div class="rs-kicker">The end of the crate</div>
            <h2 class="rs-h">That is all ${n}.</h2>
            <p class="rs-p">${nb} ${simOn() ? 'brought home or bought' : 'in your basket'} · ${nw} noted for later.</p>
            <div class="rs-bar">
              <button type="button" class="rs-btn" data-act="jump" data-i="0">Back to the first</button>
              <button type="button" class="rs-btn rs-btn--primary" data-act="back">Crates</button>
              ${nb ? (simOn() ? `<a class="rs-btn" href="/room?shop=1">Your records from the shop</a>` : `<a class="rs-btn" href="/basket">Open the basket</a>`) : ''}
            </div></div>`;
    }
    const r = items[idx], a = art(r);
    seen.add(idx); crateRemember();
    const said = r.note ? `<div class="rs-said"><p>${esc(r.note)}</p><span>${esc(r.from ? r.from.by + ', in ' + r.from.crate : crate.by.name)}</span></div>`
        : (r.from ? `<div class="rs-said"><span>From ${esc(r.from.crate)}, a crate by ${esc(r.from.by)}</span></div>` : '');
    return top + `<div class="rs-sift">
        <div class="rs-left">
          <div class="rs-stack" data-behind="${Math.min(2, n - 1 - idx)}"><div class="rs-sleeve">${a ? `<img src="${esc(a)}" alt="" onerror="this.remove()">` : ''}<span class="rs-sleeve__none">${initial(r)}</span></div></div>
        </div>
        <div class="rs-right">
          <div class="rs-title">${esc(r.title || 'Untitled')}</div>
          <div class="rs-artist">${esc(r.artist || '')}</div>
          ${said}
          ${listenRow('pull:' + crate.id + ':' + r.id, { kind: 'pull', ctx: crate.id, track: r.id }, r.duration_s, r)}
          ${actsFor(r)}
          ${facts(r)}
        </div>
      </div>`;
}

// ── the counter ──
function qCard(q) {
    const a = q.answer;
    if (!a) return `<div class="rs-q"><div class="rs-q__t">${esc(q.text)}</div>
        <div class="rs-q__s"><span>Waiting for an answer</span><button type="button" class="rs-link" data-act="withdraw" data-id="${q.id}">Take it back</button></div></div>`;
    const r = a.record; if (r) keep([r]);
    const settled = { basket: simOn() ? 'You kept it' : 'In your basket', note: 'Noted for later', pass: 'Not for you' }[a.settled] || '';
    return `<div class="rs-q"><div class="rs-q__t">${esc(q.text)}${fresh.has(q.id) ? '<i class="rs-new">new</i>' : ''}</div>
        <div class="rs-q__s"><span>Answered by ${esc(a.by.name || 'someone')}</span>${settled ? `<span>${settled}</span>` : ''}</div>
        ${r ? `<div class="rs-ans">${thumb(r)}
          <div>
            <div class="rs-ans__t">${esc(r.title || 'Untitled')}</div>
            <div class="rs-ans__a">${esc(r.artist || '')}${r.label ? ' · ' + esc(r.label) : ''}${r.year ? ' · ' + r.year : ''}</div>
            <div class="rs-said"><p>${esc(a.text)}</p><span>${esc(a.by.name || '')}</span></div>
            ${a.settled ? '' : (a.can_listen ? listenRow('q:' + q.id + ':' + r.id, { kind: 'q', ctx: q.id, track: r.id }, r.duration_s, r) : '')
                + `<div class="rs-acts" data-q="${q.id}">
                 ${simOn() ? (isSim(r) ? simActs(r) : fileActs(r)) : r.purchased ? '<span class="rs-state">Yours already</span>' : (r.borrow_id ? '<span class="rs-state">Borrowed · in your room</span>'
                    : `<button type="button" class="rs-btn" data-act="settle" data-choice="basket" data-mode="borrow" data-q="${q.id}" data-id="${r.id}">Borrow</button>`)
                    + `<button type="button" class="rs-btn" data-act="settle" data-choice="basket" data-mode="buy" data-q="${q.id}" data-id="${r.id}">Buy ${euro(r.buy_now_cents != null ? r.buy_now_cents : r.price_cents)}</button>`}
                 <button type="button" class="rs-btn" data-act="settle" data-choice="note" data-q="${q.id}" data-id="${r.id}">Note it</button>
                 <button type="button" class="rs-btn" data-act="settle" data-choice="pass" data-q="${q.id}" data-id="${r.id}">Not for me</button>
               </div>`}
          </div></div>` : `<p class="rs-quiet">The record has since left the shop.</p>`}
      </div>`;
}
function answerBox() {
    const L = C.left.answers;
    if (!Q) return `<h2 class="rs-h">Answer a question</h2>
        <p class="rs-p">You are handed the question that has waited longest. Answer it with one record from the shop and a line of why, or skip it. A question only ever gets one answer.</p>
        <div class="rs-bar">
          <button type="button" class="rs-btn rs-btn--primary" data-act="take"${L && C.open ? '' : ' disabled'}>Take a question</button>
          <span class="rs-state">${C.open ? C.open + (C.open === 1 ? ' question is' : ' questions are') + ' waiting' : 'No questions are waiting'}</span>
        </div>
        <div class="rs-msg" id="rs-takemsg">${esc(note || (L ? '' : `That’s your ${S.limits.answers} answers for today. More tomorrow.`))}</div>`;
    const r = A.record;
    return `<div class="rs-asker">Asked by ${esc(Q.asker.name || 'someone')}</div>
        <div class="rs-question">${esc(Q.text)}</div>
        ${r ? `<div class="rs-kicker">Your answer</div><div class="rs-picked">${thumb(r)}<div><div class="rs-ans__t">${esc(r.title || 'Untitled')}</div>
               <div class="rs-ans__a">${esc(r.artist || '')}</div><button type="button" class="rs-link" data-act="unpick" style="margin-top:8px">Choose another</button></div></div>`
            : `<div class="rs-kicker">Find a record in the shop</div>
               <input class="rs-input" id="rs-find" type="text" autocomplete="off" placeholder="A title, an artist, a label, a genre…" value="${esc(A.query)}">
               <div class="rs-found" id="rs-found"></div>`}
        <input class="rs-input" id="rs-why" type="text" maxlength="280" autocomplete="off" placeholder="Why this one?" value="${esc(A.text)}" style="margin-top:14px">
        <div class="rs-bar">
          <button type="button" class="rs-btn rs-btn--primary" data-act="answer" id="rs-answer"${r && A.text.trim().length >= 3 ? '' : ' disabled'}>Answer</button>
          <button type="button" class="rs-btn" data-act="skip">Skip it</button>
        </div>
        <div class="rs-msg" id="rs-answermsg">${esc(note)}</div>`;
}
function paintFound() {
    const box = host && host.querySelector('#rs-found'); if (!box || !A) return;
    box.innerHTML = keep(A.results || []).map(r => `<button type="button" class="rs-rec" data-act="pick" data-id="${r.id}">${thumb(r)}
        <span><b>${esc(r.title || 'Untitled')}</b><i>${esc([r.artist, r.label, r.year].filter(Boolean).join(' · '))}</i></span></button>`).join('')
        || (A.query && A.searched ? `<p class="rs-quiet">Nothing in the shop by those words.</p>` : '');
}
function counterView() {
    if (!C) return `<p class="rs-quiet">Asking at the counter…</p>`;
    const L = C.left.asks;
    return `<div class="rs-two">
        <section class="rs-sec">
          <div class="rs-kicker">Ask the counter <span>${leftLine(L, S.limits.asks)}</span></div>
          <h2 class="rs-h">Ask for a record</h2>
          <p class="rs-p">Say what you are after in your own words. One person answers, with one record from the shop and a line of why.</p>
          <textarea class="rs-input" id="rs-ask" rows="2" maxlength="280" placeholder="What are you looking for?">${esc(draftAsk)}</textarea>
          <div class="rs-bar"><button type="button" class="rs-btn rs-btn--primary" data-act="ask" id="rs-askgo"${L && draftAsk.trim().length >= 3 ? '' : ' disabled'}>Ask</button></div>
          <div class="rs-msg" id="rs-askmsg">${L ? '' : `That’s your ${S.limits.asks} questions for today. More tomorrow.`}</div>
          <div class="rs-kicker rs-gap">Your questions</div>
          ${(C.questions || []).length ? `<div class="rs-qs">${C.questions.map(qCard).join('')}</div>` : `<p class="rs-quiet">You haven’t asked anything yet.</p>`}
        </section>
        <section class="rs-sec">
          <div class="rs-kicker">Answer one <span>${leftLine(C.left.answers, S.limits.answers)}</span></div>
          ${answerBox()}
        </section>
      </div>`;
}

// ── blind ──
function blindView() {
    const L = S.left.blind, of = S.limits.blind;
    if (!B) return `<section class="rs-sec">
        <div class="rs-kicker">Blind <span>${leftLine(L, of)}</span></div>
        <h2 class="rs-h">Hear it before you know what it is</h2>
        <p class="rs-p">A record from the shop plays with no name and no cover. Decide what to do with it. Only then is it turned over.</p>
        <div class="rs-bar"><button type="button" class="rs-btn rs-btn--primary" data-act="blind-next"${L ? '' : ' disabled'}>Play one</button></div>
        <div class="rs-msg" id="rs-blindmsg">${esc(note || (L ? '' : `That’s your ${of} for today. More tomorrow.`))}</div>
      </section>`;
    const key = 'blind:' + B.id, spec = { kind: 'blind', ctx: B.id }, r = B.record;
    if (!r) return `<div class="rs-kicker">Blind <span>${leftLine(L, of)}</span></div>
      <div class="rs-blind" style="margin-top:18px">
        <div class="rs-left"><div class="rs-stack"><div class="rs-sleeve rs-sleeve--blind"><span>No name<br>No cover</span></div></div></div>
        <div class="rs-right">
          <div class="rs-title">What is this one?</div>
          <div class="rs-artist">Listen first</div>
          ${listenRow(key, spec, B.duration_s)}
          <div class="rs-acts">
            <button type="button" class="rs-btn" data-act="blind-decide" data-choice="basket">${simOn() ? 'I’d keep it' : 'Put it in my basket'}</button>
            <button type="button" class="rs-btn" data-act="blind-decide" data-choice="note">Note it</button>
            <button type="button" class="rs-btn" data-act="blind-decide" data-choice="pass">Not for me</button>
          </div>
          <div class="rs-msg" id="rs-blindmsg">${esc(note)}</div>
        </div>
      </div>`;
    keep([r]);
    const a = art(r), b = inBasket(r.id);
    const did = B.choice === 'basket' ? (simOn() ? 'You’d keep it' : 'You put it in your basket') : B.choice === 'note' ? (isNoted(r.id) ? 'You noted it for later' : 'You chose to note it') : 'You passed on it';
    return `<div class="rs-kicker">Blind <span>${leftLine(L, of)}</span></div>
      <div class="rs-blind" style="margin-top:18px">
        <div class="rs-left"><div class="rs-stack"><div class="rs-sleeve rs-turn">${a ? `<img src="${esc(a)}" alt="" onerror="this.remove()">` : ''}<span class="rs-sleeve__none">${initial(r)}</span></div></div></div>
        <div class="rs-right">
          <div class="rs-kicker"><span>${did}</span></div>
          <div class="rs-title" style="margin-top:10px">${esc(r.title || 'Untitled')}</div>
          <div class="rs-artist">${esc(r.artist || '')}</div>
          ${listenRow(key, spec, r.duration_s)}
          ${B.choice === 'basket' && simOn() ? `<div class="rs-acts">${isSim(r) ? simActs(r) : fileActs(r)}</div>` : ''}
          ${B.choice === 'basket' && !simOn() ? `<div class="rs-acts">
              <button type="button" class="rs-btn${b === 'borrow' ? ' on' : ''}" data-act="basket" data-mode="borrow" data-id="${r.id}">${b === 'borrow' ? 'In basket · to borrow' : 'Borrow instead'}</button>
              <button type="button" class="rs-btn${b === 'buy' ? ' on' : ''}" data-act="basket" data-mode="buy" data-id="${r.id}">${b === 'buy' ? 'In basket · to buy' : 'Buy instead · ' + euro(r.buy_now_cents != null ? r.buy_now_cents : r.price_cents)}</button></div>` : ''}
          ${B.choice === 'note' && !isNoted(r.id) ? `<div class="rs-acts"><button type="button" class="rs-btn" data-act="note" data-id="${r.id}">Note it</button></div>` : ''}
          <div class="rs-bar"><button type="button" class="rs-btn rs-btn--primary" data-act="blind-next"${L ? '' : ' disabled'}>Next record</button>
            ${L ? '' : `<span class="rs-state">That’s your ${of} for today</span>`}</div>
          <div class="rs-msg" id="rs-blindmsg">${esc(note)}</div>
          ${facts(r)}
        </div>
      </div>`;
}

// ───────────────────────── doing things ─────────────────────────
async function refresh() {
    const r = await call('/api/gr/shop');
    S = r.ok ? r.d : Object.assign({ away: true }, r.d);
    HEARD_LINE = simOn() ? 'You’ve heard this one. To hear it again, bring it home or buy it.' : 'You’ve heard this one. To hear it again, borrow it or buy it.';
    if (!r.ok && r.d && r.d.wish) S.wish = r.d.wish;
    if (r.ok && S.counter && window.grShopNews) window.grShopNews(S.counter.new);    // the top bar and the door hear it too
    paint();
}
function say(words) { note = words || ''; }
async function setTab(t) {
    if (!['crates', 'counter', 'blind'].includes(t)) t = 'crates';
    stop(); say('');
    tab = t;
    try { sessionStorage.setItem('mr_shop_tab', t); } catch (_) {}
    paint();
    if (t === 'counter') await loadCounter();
}
async function loadCounter() {
    if (!S || S.away) return;
    const r = await call('/api/gr/shop/counter/mine');
    if (!r.ok) { C = { questions: [], left: S.left, open: 0 }; say(r.d.error); paint(); return; }
    C = r.d; S.left = Object.assign(S.left, r.d.left);
    const unseen = (C.questions || []).filter(q => q.answer && !q.answer.seen);
    unseen.forEach(q => { fresh.add(q.id); call(`/api/gr/shop/counter/${q.id}/seen`, 'POST'); });
    if (unseen.length && S.counter) { S.counter.new = 0; window.grShopNews && window.grShopNews(0); }
    if (tab === 'counter') paint();
}
async function addToBasket(id, mode) {
    const r = await call('/api/gr/basket', 'POST', { track_id: id, mode });
    if (!r.ok) { say(r.d.error || 'That didn’t reach the basket.'); return false; }
    S.basket = S.basket || {}; S.basket[String(id)] = mode;
    if (window.grNavCount) window.grNavCount();
    return true;
}
async function noteIt(btn, rec, found) {
    if (!window.WishNote) return null;
    const out = await WishNote.open(btn, { record: rec, found });
    if (out && out.wish) S.wish = out.wish;
    return out;
}

const ACTS = {
    again: () => { S = null; paint(); refresh(); },
    wishlist: () => { stop(); if (opts.openWishlist) opts.openWishlist(); },

    // crates
    pull: async (t) => {
        t.disabled = true; say('');
        const r = await call('/api/gr/shop/pull', 'POST', askOf());
        if (!r.ok) { say(r.d.error || 'No crate could be pulled just now.'); if (r.d.limit) S.left.crates = 0; return paint(); }
        S.left = r.d.left; crate = r.d.pull; idx = 0; seen = new Set();
        S.pulls = (S.pulls || []).concat([Object.assign({}, crate, { items: undefined })]);
        paint(); host.closest('.rs-view, body').scrollTop = 0;
    },
    open: async (t) => {
        const r = await call('/api/gr/shop/pulls/' + t.dataset.id);
        if (!r.ok) { say(r.d.error || 'That crate can’t be opened.'); if (r.d.closed) await refresh(); return paint(); }
        crate = r.d.pull; idx = 0; seen = new Set(); say('');
        try { const m = JSON.parse(sessionStorage.getItem(crateKey()) || 'null'); if (m) { idx = Math.min(m.idx || 0, crate.items.length); seen = new Set(m.seen || []); } } catch (_) {}
        paint(); host.closest('.rs-view, body').scrollTop = 0;
    },
    back: () => { stop(); crate = null; say(''); paint(); },
    prev: () => step(-1),
    next: () => step(1),
    jump: (t) => { stop(); idx = +t.dataset.i || 0; crateRemember(); paint(); },
    listen: (t) => { const row = t.closest('.rs-listen'); if (row && row.dataset.kind) listen(row.dataset.listen, specOf(row)); },
    seek: (t, e) => {
        const row = t.closest('.rs-listen'); if (!row || !playing || playing.key !== row.dataset.listen) return;
        const box = t.getBoundingClientRect(), total = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
        if (total && box.width) { try { audio.currentTime = Math.max(0, Math.min(total - .2, total * (e.clientX - box.left) / box.width)); } catch (_) {} }
    },
    basket: async (t) => { t.disabled = true; await addToBasket(+t.dataset.id, t.dataset.mode); repaintKeepingSound(); },
    record: (t) => openRecord(t.dataset.key, t),
    'file-home': (t) => fileDo(t, 'home'),
    'file-buy': (t) => fileDo(t, 'buy'),
    note: async (t) => {
        const rec = REC.get(+t.dataset.id); if (!rec) return;
        const found = crate && tab === 'crates' ? 'a crate · ' + crate.title + (crate.kind === 'made' ? ' by ' + crate.by.name : crate.kind === 'plugin' ? ' (plug-in ' + crate.by.name + ')' : '') : tab === 'blind' ? 'blind' : 'record shopping';
        if (await noteIt(t, rec, found)) repaintKeepingSound();
    },

    // the counter
    ask: async (t) => {
        const text = (host.querySelector('#rs-ask') || {}).value || ''; if (text.trim().length < 3) return;
        t.disabled = true;
        const r = await call('/api/gr/shop/counter/ask', 'POST', { text });
        if (!r.ok) { const m = host.querySelector('#rs-askmsg'); if (m) m.textContent = r.d.error || 'That didn’t go up.'; t.disabled = false; return; }
        draftAsk = ''; await loadCounter();
    },
    withdraw: async (t) => { await call('/api/gr/shop/counter/' + t.dataset.id, 'DELETE'); await loadCounter(); },
    take: async (t) => {
        t.disabled = true; say('');
        const r = await call('/api/gr/shop/counter/take', 'POST');
        if (!r.ok) { say(r.d.error || 'No question could be handed over.'); if (r.d.limit) C.left.answers = 0; return paint(); }
        if (r.d.none) { C.open = 0; say('No questions are waiting just now.'); return paint(); }
        Q = r.d.question; A = { record: null, text: '', query: '', results: [], searched: false };
        paint(); findRecords('');
    },
    pick: (t) => { const rec = REC.get(+t.dataset.id); if (!rec || !A) return; A.record = rec; say(''); paint(); const w = host.querySelector('#rs-why'); if (w) w.focus(); },
    unpick: () => { if (!A) return; A.record = null; paint(); findRecords(A.query); },
    skip: async () => { if (!Q) return; await call(`/api/gr/shop/counter/${Q.id}/skip`, 'POST'); Q = A = null; say(''); await loadCounter(); },
    answer: async (t) => {
        if (!Q || !A || !A.record) return;
        t.disabled = true;
        const r = await call(`/api/gr/shop/counter/${Q.id}/answer`, 'POST', { track_id: A.record.id, text: A.text });
        if (!r.ok) {
            if (r.d.taken) { Q = A = null; say((r.d.error || 'Someone answered it first.') + ' Take another.'); return loadCounter(); }
            say(r.d.error || 'That answer didn’t go.'); return paint();
        }
        const to = Q.asker.name; Q = A = null; say('Sent to ' + (to || 'them') + '.'); await loadCounter();
    },
    settle: async (t) => {
        const qid = +t.dataset.q, choice = t.dataset.choice, rec = REC.get(+t.dataset.id);
        if (choice === 'basket') { t.disabled = true; if (!rec || !(await addToBasket(rec.id, t.dataset.mode))) return paint(); }
        if (choice === 'note') { const q = (C.questions || []).find(x => x.id === qid); if (!rec || !(await noteIt(t, rec, 'the counter · ' + poss(q && q.answer && q.answer.by.name) + ' answer'))) return; }
        if (playing && playing.key.indexOf('q:' + qid + ':') === 0) stop();
        await call(`/api/gr/shop/counter/${qid}/settle`, 'POST', { choice });
        await loadCounter();
    },

    // blind
    'blind-next': async (t) => {
        t.disabled = true; stop(); say('');
        const r = await call('/api/gr/shop/blind/next', 'POST');
        if (!r.ok) { say(r.d.error || 'Nothing could be played just now.'); if (r.d.limit) S.left.blind = 0; B = null; return paint(); }
        S.left = r.d.left; B = { id: r.d.blind.id, duration_s: r.d.blind.duration_s, heard: !!r.d.blind.heard };
        paint();
        if (!B.heard) listen('blind:' + B.id, { kind: 'blind', ctx: B.id });   // the press that asked for it starts it
    },
    'blind-decide': async (t) => {
        if (!B || B.record) return;
        const choice = t.dataset.choice;
        const decide = async () => {
            const r = await call(`/api/gr/shop/blind/${B.id}/decide`, 'POST', { choice });
            if (!r.ok || !r.d.record) return { ok: false, error: r.d.error || 'That didn’t work.' };
            B.record = r.d.record; B.choice = r.d.choice; S.left = r.d.left || S.left;
            return { ok: true };
        };
        if (choice === 'note') {
            if (S.wish && S.wish.left <= 0) { say(`Your wishlist holds ${S.wish.max} records. Take one out, or buy one, to make room.`); return paint(); }
            const out = await WishNote.open(t, { blind: true, save: async (why) => {
                const d = B.record ? { ok: true } : await decide();           // turned over the moment it is noted
                if (!d.ok) return d;
                const w = await WishNote.save(B.record, why, 'blind');
                if (w.wish) S.wish = w.wish;
                return w.ok ? w : { ok: false, error: w.error };
            } });
            if (!out) { if (B.record) repaintKeepingSound(); return; }
            return repaintKeepingSound();
        }
        t.disabled = true;
        const d = await decide();
        if (!d.ok) { say(d.error); return paint(); }
        if (choice === 'basket' && !simOn()) await addToBasket(B.record.id, 'borrow');
        repaintKeepingSound();
    },
};
function repaintKeepingSound() { paint(); }
// ── the credits trial ──
// a record file brought home or bought (the old borrow / buy, paid in credits while the trial runs)
async function fileDo(t, what) {
    const id = +t.dataset.id, rec = REC.get(id);
    if (what === 'buy' && !(await SimShop.ask(t, { title: 'Buy “' + ((rec && rec.title) || 'this record') + '”?', html: 'It comes to you as a plain file, yours for good, and takes no room.', yes: 'Buy', no: 'Not now' }))) return;
    t.disabled = true;
    const r = await call(what === 'home' ? '/api/gr/borrow' : '/api/gr/buy-track', 'POST', { track_id: id });
    if (!r.ok) { SimShop.say(t, r.d.error || 'That didn’t work.', true); t.disabled = false; return; }
    if (rec) { if (what === 'home') rec.borrow_id = r.d.borrow_id || 1; else rec.purchased = true; }
    SimShop.say(t, what === 'home' ? 'Brought home — it’s in your room.' : 'Bought — the file is in your room.');
    SimShop.me(true);
    settleKept(id);
    paint();
}
// the whole record a track is on, over the shop: every track, with what each costs
let recSheet = null;
async function openRecord(key, anchor) {
    closeRecord();
    const r = await call('/api/gr/sim/record/' + encodeURIComponent(key));
    if (!r.ok || !r.d.record) { SimShop.say(anchor, (r.d && r.d.error) || 'That record can’t be opened.', true); return; }
    const rec = r.d.record;
    const el = recSheet = document.createElement('div');
    el.className = 'rs-recsheet';
    const ts = rec.tracks.map(t => Object.assign({}, t, { has_art: !!rec.cover_id, art_v: rec.art_v, year: null, sim: Object.assign({}, t, { record: rec.key, record_title: rec.title }) }));
    el.innerHTML = `<div class="rs-recsheet__in" role="dialog" aria-label="${esc(rec.title)}">
        <button type="button" class="rs-recsheet__x" aria-label="Close">✕</button>
        <div class="rs-kicker"><span>${esc(rec.owner ? 'Sold by ' + rec.owner.name : '')}</span></div>
        ${SimShop.recordsHtml(ts, { cover: () => '/api/gr/art/' + rec.cover_id + '?v=' + (rec.art_v || 0), artist: rec.artist })}
      </div>`;
    document.body.appendChild(el);
    el.addEventListener('click', e => { if (e.target === el || e.target.closest('.rs-recsheet__x')) closeRecord(); });
}
function closeRecord() { if (recSheet) { recSheet.remove(); recSheet = null; } }
// after something is brought home or bought: the shop's cards learn it, and an open answer at the counter is settled as kept
function settleKept(ids) {
    ids = [].concat(ids || []);
    if (tab !== 'counter' || !C) return;
    (C.questions || []).forEach(q => {
        const a = q.answer; if (!a || a.settled || !a.record || !ids.includes(a.record.id)) return;
        call(`/api/gr/shop/counter/${q.id}/settle`, 'POST', { choice: 'basket' }).then(loadCounter);
    });
}
window.addEventListener('sim-changed', async e => {
    const d = e.detail || {};
    const ids = (d.tracks || []).map(t => t.id);
    ids.forEach(id => { const rec = REC.get(id); const t = (d.tracks || []).find(x => x.id === id);
        if (rec && rec.sim && t) { rec.sim.state = t.state; rec.sim.url = t.url; rec.sim.spotify_uri = t.spotify_uri;
            if (t.state === 'bought') rec.sim.buy_cost = null; else if (t.state === 'home') { rec.sim.home_cost = null; rec.sim.buy_cost = Math.max(0, ((S.sim.rules || {}).buy_cost || 3) - ((S.sim.rules || {}).home_cost || 1)); } } });
    if (d.credits != null && S && S.sim) S.sim.credits = d.credits;
    settleKept(ids);
    if (recSheet && d.what !== 'play') { const k = recSheet.querySelector('[data-record]'); if (k) openRecord(k.dataset.record, null); }
    if (host && host.isConnected) paint();
});                                   // (the player isn't in the page's markup: it carries on)
function step(d) {
    if (!crate) return;
    const n = crate.items.length, to = Math.max(0, Math.min(n, idx + d));
    if (to === idx) return;
    stop(); idx = to; crateRemember(); paint();
}
let findTimer = 0, findSeq = 0;
function findRecords(q) {
    if (!A) return;
    A.query = q;
    clearTimeout(findTimer);
    findTimer = setTimeout(async () => {
        const mine = ++findSeq;
        const r = await call('/api/gr/shop/search?q=' + encodeURIComponent(q));
        if (mine !== findSeq || !A) return;
        A.results = (r.ok && r.d.records) || []; A.searched = true;
        paintFound();
    }, q ? 220 : 0);
}

function onClick(e) {
    const t = e.target.closest('[data-tab],[data-act],[data-ask]');
    if (!t || !host.contains(t) || t.disabled) return;
    if (t.dataset.tab) return void setTab(t.dataset.tab);
    if (t.dataset.ask) {
        const k = t.dataset.ask, v = t.dataset.v;
        if (k === 'any') ask = { genres: [], place: '', decades: [] };
        if (k === 'genre') { const i = ask.genres.findIndex(g => g.toLowerCase() === v.toLowerCase()); if (i >= 0) ask.genres.splice(i, 1); else if (ask.genres.length < 5) ask.genres.push(v); }
        if (k === 'place') ask.place = ask.place.toLowerCase() === v.toLowerCase() ? '' : v;
        if (k === 'decade') { const n = +v, i = ask.decades.indexOf(n); if (i >= 0) ask.decades.splice(i, 1); else ask.decades.push(n); }
        say(''); return paint();
    }
    const act = ACTS[t.dataset.act];
    if (act) act(t, e);
}
function onInput(e) {
    const t = e.target;
    if (t.id === 'rs-ask') { draftAsk = t.value; const b = host.querySelector('#rs-askgo'); if (b) b.disabled = !(S.left.asks && draftAsk.trim().length >= 3); }
    if (t.id === 'rs-find') findRecords(t.value);
    if (t.id === 'rs-why' && A) { A.text = t.value; const b = host.querySelector('#rs-answer'); if (b) b.disabled = !(A.record && A.text.trim().length >= 3); }
}
function onKey(e) {
    if (!host || !host.offsetParent) return;                                  // the shop isn't on show
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || '');
    if (typing) {
        if (e.key === 'Enter' && !e.shiftKey && e.target.id === 'rs-ask') { e.preventDefault(); const b = host.querySelector('#rs-askgo'); if (b && !b.disabled) ACTS.ask(b); }
        if (e.key === 'Enter' && e.target.id === 'rs-why') { e.preventDefault(); const b = host.querySelector('#rs-answer'); if (b && !b.disabled) ACTS.answer(b); }
        return;
    }
    if (window.WishNote && WishNote.isOpen()) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (tab === 'crates' && crate) {
        if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
        if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    }
    if (e.key === ' ' && e.target === document.body) {                        // space: the record in front of you
        const row = host.querySelector('.rs-listen'); const b = row && row.querySelector('.rs-play');
        if (b && !b.disabled && (tab !== 'counter')) { e.preventDefault(); listen(row.dataset.listen, specOf(row)); }
    }
}

function mount(h, o) {
    host = h; opts = o || {};
    host.classList.add('rs');
    host.addEventListener('click', onClick);
    host.addEventListener('input', onInput);
    addEventListener('keydown', onKey);
    addEventListener('pagehide', stop);
    addEventListener('resize', fitSleeve);
    addEventListener('snt-box', fitSleeve);                                   // the deck moved, folded or opened
    let t = opts.tab; try { t = t || sessionStorage.getItem('mr_shop_tab'); } catch (_) {}
    tab = ['crates', 'counter', 'blind'].includes(t) ? t : 'crates';
    paint();
    refresh().then(() => { if (tab === 'counter') loadCounter(); });
    return api;
}
const api = {
    mount,
    open: t => { if (host) setTab(t); },
    // a crate handed over from elsewhere (a plug-in's pick): show it at once, inside Crates
    openPull: pull => {
        if (!host || !pull) return;
        stop(); setTab('crates');
        crate = pull; idx = 0; seen = new Set(); say('');
        if (S) S.pulls = (S.pulls || []).filter(p => p.id !== pull.id).concat([Object.assign({}, pull, { items: undefined })]);
        refresh();                                   // (it paints when the shop's state comes; the crate stays open)
    },
    refresh: () => { if (host) return refresh().then(() => { if (tab === 'counter') return loadCounter(); }); },
    leave: stop,
    // Escape: put the note down, then come out of the crate. True if something closed.
    escape: () => {
        if (window.WishNote && WishNote.isOpen()) { WishNote.close(); return true; }
        if (host && tab === 'crates' && crate) { ACTS.back(); return true; }
        if (host && tab === 'counter' && Q) { Q = A = null; say(''); paint(); return true; }
        return false;
    },
    state: () => ({ tab, crate: crate && crate.id, idx, playing: playing && Object.assign({}, playing), S }),
};
return api;
})();
