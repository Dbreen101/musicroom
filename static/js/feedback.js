/* Tester feedback — a minimal, always-tucked corner button (testing phase). The
 * tester creates a LOCAL account once (a name → a fixed identity; no logging in as
 * anyone else). Then any moment they can log a reaction — like / dislike / confused
 * / bug / idea — WITH a required note (we need to know what). Custom thin-line
 * glyphs, not emoji. Saved to tester_feedback; collected for the master tracker.
 * Self-mounts on every page; collapsed to a small symbol when idle. */
(function () {
  if (window.__mrFeedbackMounted) return;
  window.__mrFeedbackMounted = true;

  const SW = 'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"';
  const ICON = {
    like:    `<svg viewBox="0 0 24 24" ${SW}><circle cx="12" cy="12" r="9"/><path d="M8.5 14.3c1 1.5 5.9 1.5 7 0"/><path d="M9 9.6h.01M15 9.6h.01"/></svg>`,
    dislike: `<svg viewBox="0 0 24 24" ${SW}><circle cx="12" cy="12" r="9"/><path d="M8.4 15.4q1.7-2 3.5-1t3.5-1"/><path d="M9 9.6h.01M15 9.6h.01"/></svg>`,
    confused:`<svg viewBox="0 0 24 24" ${SW}><circle cx="12" cy="12" r="9"/><path d="M8.7 14.7q1.1-1.4 2.2 0t2.2 0"/><path d="M9 10h.01"/><path d="M13.7 8.9q1.1-.9 2.2 0"/></svg>`,
    bug:     `<svg viewBox="0 0 24 24" ${SW}><ellipse cx="12" cy="13" rx="4" ry="5"/><path d="M12 8v9"/><path d="M10.5 6.4 9 4.7M13.5 6.4 15 4.7"/><path d="M8 10.6 6 9.6M8 13.4 6 13.4M8 16 6.3 17M16 10.6 18 9.6M16 13.4 18 13.4M16 16 17.7 17"/></svg>`,
    idea:    `<svg viewBox="0 0 24 24" ${SW}><path d="M12 3a6 6 0 0 1 4 10.5c-.6.6-1 1.3-1 2.2H9c0-.9-.4-1.6-1-2.2A6 6 0 0 1 12 3Z"/><path d="M9.6 18.4h4.8M10.6 21h2.8"/></svg>`,
  };
  const OPTS = [
    { kind: 'like', label: 'I like this' }, { kind: 'dislike', label: "I don't like this" },
    { kind: 'confused', label: "I'm confused" }, { kind: 'bug', label: 'Found a bug' }, { kind: 'idea', label: 'Had an idea' },
  ];
  const BUBBLE = `<svg viewBox="0 0 24 24" ${SW}><path d="M5 5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-6l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/></svg>`;

  const css = document.createElement('style');
  css.textContent = `
    /* (--mr-keys-right: a page moves this key and the "?" above it clear of a panel it has open on the right) */
    #mr-fb { position: fixed; right: var(--mr-keys-right, 16px); bottom: var(--mr-keys-bottom, 16px); z-index: 8500; }
    #mr-fb__btn { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--border, #3a352c);
      background: var(--surface, rgba(20,18,16,0.7)); color: var(--muted2, #6a6358); cursor: pointer;
      display: flex; align-items: center; justify-content: center; padding: 0; opacity: .55;
      backdrop-filter: blur(6px); transition: opacity .2s ease, color .2s ease, border-color .2s ease; }
    #mr-fb__btn:hover { opacity: 1; color: var(--accent, #c9a24b); border-color: var(--accent, #c9a24b); }
    #mr-fb__btn svg { width: 17px; height: 17px; }
    #mr-fb__panel { position: absolute; right: 0; bottom: 44px; width: 264px; display: none;
      background: var(--surface2, #1a1714); border: 1px solid var(--border, #3a352c); border-radius: 14px;
      padding: 14px; box-shadow: 0 10px 34px rgba(0,0,0,0.5); }
    #mr-fb.open #mr-fb__panel { display: block; animation: mr-fb-in .16s ease; }
    @keyframes mr-fb-in { from { opacity:0; transform: translateY(5px); } to { opacity:1; transform:none; } }
    #mr-fb__h, #mr-fb__acct .mr-fb__h { font-family: var(--font-serif, serif); font-style: italic; font-size: 0.96rem; color: var(--text, #d9cfb8); margin: 0 0 11px; }
    #mr-fb__opts { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
    .mr-fb__opt { display: flex; flex-direction: column; align-items: center; gap: 5px; padding: 11px 6px 9px;
      background: var(--surface, rgba(255,255,255,0.02)); border: 1px solid var(--border, #3a352c);
      border-radius: 10px; cursor: pointer; color: var(--muted, #8a8273); font-family: var(--font-main, system-ui); }
    .mr-fb__opt:hover { color: var(--text, #d9cfb8); border-color: var(--accent, #c9a24b); }
    .mr-fb__opt.sel { color: var(--accent, #c9a24b); border-color: var(--accent, #c9a24b); background: var(--accent-dim, rgba(201,162,75,0.1)); }
    .mr-fb__opt svg { width: 26px; height: 26px; }
    .mr-fb__opt span { font-size: 0.64rem; text-align: center; line-height: 1.2; }
    .mr-fb__opt:nth-child(5) { grid-column: span 2; flex-direction: row; gap: 9px; padding: 9px; }
    .mr-fb__opt:nth-child(5) svg { width: 22px; height: 22px; }
    .mr-fb__opt:nth-child(5) span { font-size: 0.72rem; }
    #mr-fb__note { width: 100%; box-sizing: border-box; margin-top: 10px; background: var(--bg, #14110e);
      border: 1px solid var(--border, #3a352c); border-radius: 8px; color: var(--text, #d9cfb8);
      padding: 8px 10px; font-size: 0.82rem; font-family: var(--font-main, system-ui); resize: vertical; min-height: 40px; outline: none; display: none; }
    #mr-fb__note:focus { border-color: var(--accent, #c9a24b); }
    #mr-fb__send { display: none; width: 100%; margin-top: 8px; padding: 8px; border-radius: 8px;
      background: var(--accent, #c9a24b); border: none; color: #14110e; font-weight: 600; cursor: pointer; font-family: var(--font-main, system-ui); font-size: 0.82rem; }
    #mr-fb__send:disabled { opacity: .4; cursor: not-allowed; }
    #mr-fb.has-sel #mr-fb__note, #mr-fb.has-sel #mr-fb__send { display: block; }
    #mr-fb__foot { margin-top: 11px; font-size: 0.68rem; color: var(--muted2, #6a6358); }
    #mr-fb__foot strong { color: var(--muted, #8a8273); }
    #mr-fb__thanks { display: none; text-align: center; color: var(--accent, #c9a24b); font-size: 0.9rem; padding: 18px 0; }
    #mr-fb.thanks #mr-fb__thanks { display: block; }
    #mr-fb.thanks #mr-fb__opts, #mr-fb.thanks #mr-fb__h, #mr-fb.thanks #mr-fb__foot, #mr-fb.thanks #mr-fb__note, #mr-fb.thanks #mr-fb__send { display: none; }
    /* account-create gate */
    #mr-fb__acct { display: none; }
    #mr-fb.acct #mr-fb__acct { display: block; }
    #mr-fb.acct #mr-fb__h, #mr-fb.acct #mr-fb__opts, #mr-fb.acct #mr-fb__note, #mr-fb.acct #mr-fb__send, #mr-fb.acct #mr-fb__foot, #mr-fb.acct #mr-fb__thanks { display: none; }
    #mr-fb__acct p { font-size: 0.78rem; color: var(--muted, #8a8273); line-height: 1.5; margin: 0 0 10px; }
    #mr-fb__acct input { width: 100%; box-sizing: border-box; background: var(--bg, #14110e); border: 1px solid var(--border, #3a352c);
      border-radius: 8px; color: var(--text, #d9cfb8); padding: 9px 11px; font-size: 0.9rem; font-family: var(--font-main, system-ui); outline: none; }
    #mr-fb__acct input:focus { border-color: var(--accent, #c9a24b); }
    #mr-fb__acct button { width: 100%; margin-top: 9px; padding: 8px; border-radius: 8px; background: var(--accent, #c9a24b);
      border: none; color: #14110e; font-weight: 600; cursor: pointer; font-family: var(--font-main, system-ui); font-size: 0.82rem; }
  `;
  document.head.appendChild(css);

  let tester = '', hasAccount = null, selected = null;

  const root = document.createElement('div');
  root.id = 'mr-fb';
  root.innerHTML =
    `<button id="mr-fb__btn" title="A quick thought about the app?">${BUBBLE}</button>` +
    `<div id="mr-fb__panel">
       <div id="mr-fb__acct">
         <div class="mr-fb__h">Your name</div>
         <input id="mr-fb__acct-name" placeholder="your name" spellcheck="false" maxlength="60">
         <button id="mr-fb__acct-go">Create account</button>
       </div>
       <div id="mr-fb__h">A quick thought?</div>
       <div id="mr-fb__opts">` +
         OPTS.map(o => `<button class="mr-fb__opt" data-kind="${o.kind}">${ICON[o.kind]}<span>${o.label}</span></button>`).join('') +
       `</div>
       <textarea id="mr-fb__note" placeholder="what is it? — required"></textarea>
       <button id="mr-fb__send" disabled>Send</button>
       <div id="mr-fb__foot"></div>
       <div id="mr-fb__thanks">Logged — thank you ✓</div>
     </div>`;

  function $(id) { return document.getElementById(id); }

  function mount() {
    document.body.appendChild(root);
    $('mr-fb__btn').addEventListener('click', toggle);
    root.querySelectorAll('.mr-fb__opt').forEach(b => b.addEventListener('click', () => pick(b)));
    $('mr-fb__send').addEventListener('click', send);
    $('mr-fb__note').addEventListener('input', () => { $('mr-fb__send').disabled = !$('mr-fb__note').value.trim(); });
    $('mr-fb__acct-go').addEventListener('click', createAccount);
    $('mr-fb__acct-name').addEventListener('keydown', e => { if (e.key === 'Enter') createAccount(); });
    document.addEventListener('click', e => { if (!root.contains(e.target) && root.classList.contains('open')) close(); });
  }

  function toggle() { root.classList.contains('open') ? close() : open(); }
  function open() {
    reset();
    root.classList.add('open');
    fetch('/api/feedback/me').then(r => r.json()).then(d => {
      tester = d.tester || ''; hasAccount = !!d.has_account;
      if (!hasAccount) { root.classList.add('acct'); $('mr-fb__acct-name').focus(); }
      else { renderFoot(); }
    }).catch(() => {});
  }
  function close() { root.classList.remove('open'); }
  function reset() {
    selected = null;
    root.classList.remove('has-sel', 'thanks', 'acct');
    root.querySelectorAll('.mr-fb__opt').forEach(b => b.classList.remove('sel'));
    $('mr-fb__note').value = ''; $('mr-fb__send').disabled = true;
  }

  function createAccount() {
    const name = $('mr-fb__acct-name').value.trim();
    if (!name) { $('mr-fb__acct-name').focus(); return; }
    fetch('/api/feedback/me', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tester: name }) })
      .then(r => r.json()).then(d => {
        if (d.ok) { tester = d.tester; hasAccount = true; root.classList.remove('acct'); renderFoot(); }
      }).catch(() => {});
  }

  function pick(btn) {
    selected = btn.dataset.kind;
    root.querySelectorAll('.mr-fb__opt').forEach(b => b.classList.toggle('sel', b === btn));
    root.classList.add('has-sel');
    const n = $('mr-fb__note'); n.focus(); $('mr-fb__send').disabled = !n.value.trim();
  }

  function send() {
    const note = $('mr-fb__note').value.trim();
    if (!selected || !note) return;                  // note is required
    fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: selected, note, page: location.pathname, context: { title: document.title } }) })
      .then(r => r.json()).then(res => {
        if (res.ok) { root.classList.add('thanks'); setTimeout(close, 1100); }
      }).catch(() => {});
  }

  function renderFoot() { $('mr-fb__foot').innerHTML = tester ? `logging as <strong>${esc(tester)}</strong>` : ''; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();
