// The basket count in the nav, and a quiet note of each page opened (the
// trial's activity log). Nothing shows until something's in the basket.
async function grNavCount() {
  const els = document.querySelectorAll('[data-gr-basket-count]');
  if (!els.length) return;
  try {
    const d = await (await fetch('/api/gr/basket')).json();
    const n = (d.items || []).length;
    els.forEach(e => { e.textContent = n ? String(n) : ''; e.classList.toggle('on', n > 0); });
  } catch (_) {}
}
function grTrack(kind, data) {
  try {
    fetch('/api/gr/track', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, data }), keepalive: true });
  } catch (_) {}
}
// Answers waiting at the counter (Explore → Record shopping): a small count
// beside Explore in the top bar, and on Explore's own "Record shopping" door.
// While there is one, Explore's link leads straight to the counter.
function grShopNews(n) {
  n = Number(n) || 0;
  const link = document.querySelector('.nav__links a[href^="/explore3d"]');
  if (link) {
    let s = link.querySelector('[data-gr-shop-news]');
    if (!s) { s = document.createElement('span'); s.className = 'nav__count'; s.setAttribute('data-gr-shop-news', ''); link.appendChild(s); }
    s.textContent = n ? String(n) : ''; s.classList.toggle('on', n > 0);
    s.title = n ? n + (n === 1 ? ' answer' : ' answers') + ' waiting at the counter' : '';
    link.setAttribute('href', n ? '/explore3d?view=shop&tab=counter' : '/explore3d');
  }
  const door = document.getElementById('shop-news');
  if (door) door.textContent = n ? String(n) : '';
}
async function grShopNewsAsk() {
  if (!document.documentElement.classList.contains('is-gr') || !document.querySelector('.nav__links a[href^="/explore3d"]')) return;
  try { grShopNews((await (await fetch('/api/gr/shop/news')).json()).answers); } catch (_) {}
}
window.grShopNews = grShopNews;
window.grNavCount = grNavCount;
grNavCount();
grShopNewsAsk();
grTrack('page', { path: location.pathname + location.search, ref: document.referrer ? new URL(document.referrer).pathname : null });
window.grTrack = grTrack;

// The top bar stays put now (ui.css, html.is-gr — it used to hide and come down
// at the top edge, where the Mac's own menu bar comes down too). Grúpaí are no
// longer on it (David, 2026-11-15: "the user should access grúpa from within
// the music room"): they are a tab in My Room, and "add to a grúpa" is offered
// wherever there is something to keep.
// a page with no bar of its own doesn't keep room for one
if (!document.querySelector('.nav')) document.documentElement.classList.add('no-nav');

// ── the document's furniture (David's deck, Oct 2026): a section label at the
// right of the page header, and a foot line on every scrolling page —
// "THE MUSIC ROOM" left, the page's name right, like the foot of a slide.
(function(){
  if (!document.documentElement.classList.contains('is-gr')) return;
  const run = () => {
    const b = document.body; if (!b) return;
    if (b.querySelector('#r3d-canvas-wrap, #forest3d-canvas, #map-canvas') || /\bview-(stream|wall|rooms|globe|grupai|shop)\b/.test(b.className) || b.classList.contains('lg') || b.classList.contains('in')) return;
    const active = document.querySelector('.nav__links a.active');
    const name = (active && !active.classList.contains('nav__icon') ? active.textContent : (document.title.split(' — ')[0] || '')).trim();
    if (!name) return;
    let head = document.querySelector('.gr-hero, .settings-header, .explore-header, .help-hero');
    if (!head) { const t = document.querySelector('.index-title, .usb-wrap h1, .mr-wrap h1, .analyse-layout h1, h1.page-title'); if (t) { head = t.parentElement; head.style.position = 'relative'; } }
    if (head && !head.querySelector('.mr-section-label')) {
      const l = document.createElement('span'); l.className = 'mr-section-label'; l.textContent = name; head.appendChild(l);
    }
    if (!b.querySelector('.mr-foot')) {
      const f = document.createElement('footer'); f.className = 'mr-foot';
      f.innerHTML = '<span>The Music Room</span><span></span>'; f.lastChild.textContent = name;
      b.appendChild(f);
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();

// ── a new version of the app (2026-11-20): the Music Room names the release everyone
// should be on (its master page); when this app's own differs, one line says so, under
// the top bar, until it is closed for this session. ──
(function(){
  if (window.self !== window.top) return;                 // (not inside an overlay or a plug-in's frame)
  async function look(){
    let v;
    try { v = await (await fetch('/api/gr/version')).json(); } catch (_) { return; }
    if (!v || !v.update) return;
    const key = 'mr_update_closed_' + v.want.version;
    try { if (sessionStorage.getItem(key)) return; } catch (_) {}
    const bar = document.createElement('div');
    bar.className = 'mr-update';
    bar.setAttribute('role', 'status');
    const say = document.createElement('span');
    say.textContent = `Version ${v.want.version} of the Music Room is ready${v.want.note ? ' — ' + v.want.note : ''}. `;
    const get = document.createElement('a');
    get.href = '#'; get.textContent = 'Get it';
    get.addEventListener('click', e => { e.preventDefault(); fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: v.want.url }) }); });
    const x = document.createElement('button');
    x.type = 'button'; x.textContent = '✕'; x.title = 'Not now'; x.setAttribute('aria-label', 'Not now');
    x.addEventListener('click', () => { bar.remove(); try { sessionStorage.setItem(key, '1'); } catch (_) {} });
    // "Update now": the app fetches the new version, puts it where this one is, and opens it again
    // (the person's room and sign-in are not in the app, so nothing of theirs is touched)
    const now = document.createElement('button');
    now.type = 'button'; now.className = 'mr-update__go'; now.textContent = 'Update now';
    const page = () => fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: v.want.url || v.page }) });
    const failed = why => { say.textContent = (why || 'The update could not be fetched.') + ' '; get.textContent = 'Get it by hand'; get.onclick = e => { e.preventDefault(); page(); }; now.remove(); bar.insertBefore(get, x); };
    now.addEventListener('click', async () => {
      now.disabled = true; now.textContent = 'Starting…';
      try { await fetch('/api/gr/update/start', { method: 'POST' }); } catch (_) { return failed(); }
      const tick = async () => {
        let s; try { s = await (await fetch('/api/gr/update')).json(); } catch (_) { return failed(); }
        if (s.step === 'error') return failed(s.error);
        if (s.step === 'ready') {
          now.textContent = 'Restarting…';
          try { await fetch('/api/gr/update/apply', { method: 'POST' }); } catch (_) {}
          say.textContent = `Version ${v.want.version} is going in. The Music Room will reopen by itself. `;
          return;
        }
        now.textContent = s.step === 'downloading' && s.total ? `Downloading ${Math.floor(100 * s.done / s.total)}%` : s.step === 'unpacking' ? 'Unpacking…' : 'Starting…';
        setTimeout(tick, 700);
      };
      tick();
    });
    if (v.self) bar.append(say, now, x);
    else if (v.want.url) bar.append(say, get, x); else bar.append(say, x);      // (no address given → no link that leads nowhere)
    const css = document.createElement('style');
    css.textContent = `.mr-update{position:fixed;left:50%;top:calc(var(--nav-h,54px) + 8px);transform:translateX(-50%);z-index:9400;display:flex;align-items:center;gap:10px;
      max-width:calc(100vw - 24px);padding:8px 10px 8px 14px;background:var(--text,#161513);color:var(--bg,#f2efe8);font-family:var(--f-mono,"IBM Plex Mono",monospace);font-size:.68rem;line-height:1.4}
      .mr-update a{color:inherit;text-decoration:underline;text-underline-offset:3px;white-space:nowrap}
      .mr-update__go{appearance:none;border:1px solid currentColor;background:none;color:inherit;font:inherit;text-transform:uppercase;letter-spacing:.08em;padding:4px 9px;cursor:pointer;white-space:nowrap}.mr-update__go:disabled{opacity:.75;cursor:default}
      .mr-update button{appearance:none;border:1px solid currentColor;border-radius:0;background:none;color:inherit;width:22px;height:22px;padding:0;cursor:pointer;font-size:.62rem}`;
    document.head.append(css);
    document.body.append(bar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', look); else look();
})();

// ── the credits trial (gr_sim, 2026-11-20): while the shop runs it, the top bar
// shows your credits where the basket was, and they lead to My Room → From the
// shop. Asking also lets the app pick up the Spotify key the master gave you.
(function () {
  if (!document.documentElement.classList.contains('is-gr')) return;
  const links = document.querySelector('.nav__links');
  if (!links) return;
  const need = () => window.SimShop ? Promise.resolve() : new Promise(res => {
    if (!document.querySelector('link[href^="/static/css/sim_shop.css"]')) {
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/static/css/sim_shop.css'; document.head.appendChild(l);
    }
    const s = document.createElement('script'); s.src = '/static/js/sim_shop.js'; s.onload = res; s.onerror = res; document.head.appendChild(s);
  });
  const paint = m => {
    if (!m || !m.on) return;
    const basket = links.querySelector('.nav__basket');
    if (basket && basket.parentElement) basket.parentElement.style.display = 'none';
    let a = links.querySelector('[data-gr-credits]');
    if (!a) {
      const li = document.createElement('li');
      li.innerHTML = '<a href="/room?shop=1" class="nav__credits" data-gr-credits></a>';
      const icons = links.querySelector('.nav__icons');
      links.insertBefore(li, icons || null);
      a = li.firstChild;
    }
    a.textContent = m.credits + (m.credits === 1 ? ' credit' : ' credits');
    a.title = 'Your room holds ' + m.room.count + ' of ' + m.room.space + ' brought-home tracks · your records from the shop';
  };
  const go = () => need().then(() => window.SimShop && window.SimShop.me().then(paint));
  window.addEventListener('sim-me', e => paint(e.detail));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
})();
