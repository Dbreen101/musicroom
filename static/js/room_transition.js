/* Music Room — page-to-page "travel" transition.
 *
 * A short, warm dim-and-reveal between pages so that navigating from one section
 * to another feels like moving through the room rather than a hard page jump.
 *
 * SAFE / ADDITIVE: this only paints a non-interactive overlay (a fixed pseudo-
 * element) and intercepts plain same-origin <a> clicks to delay the jump by a
 * few hundred ms. It changes NO page behaviour or data. To remove it entirely,
 * delete the <script src=".../room_transition.js"> include — nothing else.
 */
(function () {
  if (window.__rtInstalled) return; window.__rtInstalled = true;

  var COVER = '#120d08';        // warm dark — the connective dark between sections
  var ENTER = 440, EXIT = 300;  // ms

  var css =
    '@keyframes rt-reveal { from { opacity: 1 } to { opacity: 0 } }' +
    '@keyframes rt-cover  { from { opacity: 0 } to { opacity: 1 } }' +
    'html.rt::before, html.rt-leaving::after {' +
    '  content: ""; position: fixed; inset: 0; z-index: 2147483646;' +
    '  pointer-events: none; background: ' + COVER + '; }' +
    'html.rt::before        { animation: rt-reveal ' + ENTER + 'ms cubic-bezier(.22,.61,.36,1) forwards; }' +
    'html.rt-leaving::after { animation: rt-cover  ' + EXIT  + 'ms ease forwards; }';

  var style = document.createElement('style');
  style.textContent = css;
  (document.head || document.documentElement).appendChild(style);
  document.documentElement.classList.add('rt');   // play the arrival reveal now

  function go(href) {
    if (!href) return;
    document.documentElement.classList.add('rt-leaving');
    setTimeout(function () { window.location.href = href; }, EXIT - 20);
  }
  // expose for JS-driven navigations (e.g. entering a place from the 3D scene)
  window.rtGo = go;

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('download') || a.hasAttribute('data-no-transition')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || /^(mailto:|tel:|javascript:)/i.test(href)) return;
    var url; try { url = new URL(href, location.href); } catch (_) { return; }
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && (url.hash || url.search === location.search)) return; // in-page
    e.preventDefault();
    go(url.href);
  }, true);

  // If the page is restored from the bfcache (back/forward), re-reveal cleanly.
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      document.documentElement.classList.remove('rt-leaving');
      document.documentElement.classList.remove('rt');
      void document.documentElement.offsetWidth;        // reflow so the animation can replay
      document.documentElement.classList.add('rt');
    }
  });
})();
