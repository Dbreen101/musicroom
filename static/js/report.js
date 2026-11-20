/* report.js — "Report" on someone else's room, record or public grúpa (2026-11-20).
   A small window: why (one of four), a line if you like, Send. It goes to the
   Music Room's master page (gr_master.py on the rooms server), who looks at it
   and takes the thing down or not.

   MRReport.open({ what: 'room'|'record'|'grupa', ref, title }, anchorElement) */
window.MRReport = (function () {
    'use strict';
    const REASONS = [
        ['rights', 'It uses music or pictures they have no rights to'],
        ['hurtful', 'It is hurtful, hateful or unsafe'],
        ['private', 'It shows someone’s private details'],
        ['other', 'Something else'],
    ];
    let box = null;
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    function style() {
        if (document.getElementById('mr-report-css')) return;
        const css = document.createElement('style');
        css.id = 'mr-report-css';
        css.textContent = `
        .mr-rep{position:fixed;z-index:9600;width:min(360px,calc(100vw - 24px));padding:16px 16px 14px;background:var(--bg,#f2efe8);color:var(--text,#161513);
          border:1px solid var(--text,#161513);box-shadow:0 18px 50px var(--shadow,rgba(0,0,0,.18));font-family:var(--f-mono,"IBM Plex Mono",monospace);font-size:.74rem;line-height:1.5}
        .mr-rep h3{margin:0 0 4px;font-family:var(--f-display,"Instrument Serif",Georgia,serif);font-weight:400;font-size:1.35rem;line-height:1.1}
        .mr-rep p{margin:0 0 10px;color:var(--muted,#6e6a61);font-size:.66rem}
        .mr-rep label{display:flex;gap:8px;align-items:flex-start;margin:6px 0;cursor:pointer}
        .mr-rep label input{margin-top:2px}
        .mr-rep textarea{width:100%;box-sizing:border-box;margin:8px 0 10px;min-height:58px;padding:7px 8px;border:1px solid var(--border2,#a9a497);border-radius:0;
          background:none;color:inherit;font:inherit;resize:vertical}
        .mr-rep__acts{display:flex;gap:6px;align-items:center}
        .mr-rep button{appearance:none;padding:7px 10px;border:1px solid var(--border2,#a9a497);border-radius:0;background:none;color:inherit;font:inherit;
          font-size:.6rem;letter-spacing:.08em;text-transform:uppercase;cursor:pointer}
        .mr-rep button.go{background:var(--text,#161513);border-color:var(--text,#161513);color:var(--bg,#f2efe8)}
        .mr-rep__said{flex:1;font-size:.64rem;color:var(--muted,#6e6a61)}`;
        document.head.append(css);
    }
    function close() { if (box) { box.remove(); box = null; } removeEventListener('keydown', onKey, true); }
    function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); close(); } }

    function open(thing, anchor) {
        style(); close();
        box = document.createElement('div');
        box.className = 'mr-rep'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Report');
        box.innerHTML = `<h3>Report ${thing.what === 'grupa' ? 'this grúpa' : thing.what === 'record' ? 'this record' : 'this room'}</h3>
          <p>${esc(thing.title || '')}${thing.title ? ' · ' : ''}It goes to the Music Room, who looks at every report. Whoever made it isn’t told who you are.</p>
          ${REASONS.map(([k, l], i) => `<label><input type="radio" name="mr-rep-why" value="${k}" ${i === 0 ? 'checked' : ''}> ${esc(l)}</label>`).join('')}
          <textarea placeholder="Anything that would help (optional)" maxlength="1000"></textarea>
          <div class="mr-rep__acts"><span class="mr-rep__said" role="status"></span><button type="button" data-x>Cancel</button><button type="button" class="go" data-send>Send</button></div>`;
        document.body.append(box);
        const r = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : null;
        const w = box.offsetWidth, h = box.offsetHeight;
        const left = r ? Math.min(innerWidth - w - 12, Math.max(12, r.right - w)) : (innerWidth - w) / 2;
        const top = r ? (r.bottom + 8 + h < innerHeight ? r.bottom + 8 : Math.max(12, r.top - h - 8)) : (innerHeight - h) / 3;
        box.style.left = left + 'px'; box.style.top = top + 'px';
        box.querySelector('[data-x]').onclick = close;
        box.querySelector('[data-send]').onclick = async e => {
            const b = e.currentTarget, said = box.querySelector('.mr-rep__said');
            b.disabled = true; said.textContent = 'Sending…';
            const reason = (box.querySelector('input[name="mr-rep-why"]:checked') || {}).value || 'other';
            try {
                const res = await fetch('/api/gr/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ what: thing.what, ref: String(thing.ref), reason, note: box.querySelector('textarea').value }) });
                const d = await res.json().catch(() => ({}));
                if (!res.ok) { said.textContent = d.error || 'It wasn’t sent.'; b.disabled = false; return; }
                said.textContent = 'Sent. Thank you.';
                setTimeout(close, 1400);
            } catch (_) { said.textContent = 'It wasn’t sent.'; b.disabled = false; }
        };
        addEventListener('keydown', onKey, true);
        setTimeout(() => document.addEventListener('pointerdown', function out(ev) {
            if (box && !box.contains(ev.target)) { close(); document.removeEventListener('pointerdown', out); }
        }), 0);
    }
    return { open, close };
})();
