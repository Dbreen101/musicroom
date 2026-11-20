// =============================================================
// path_picker.js — "Choose…" buttons that open a native Finder dialog
// instead of making the user type a path. Works in the browser (dev) and
// the bundled app, because the local server pops a real macOS chooser.
// =============================================================
(function () {
'use strict';

async function mrChoosePath(kind, start, prompt) {
    try {
        const r = await fetch('/api/choose-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: kind || 'folder', start: start || '', prompt: prompt || '' }),
        });
        const d = await r.json();
        if (!d.ok || d.cancelled) return null;
        return d.path || null;
    } catch (e) {
        return null;
    }
}

// Pick a path and drop it into an input (firing input/change so any
// listeners — sticky settings, dependent fields — react). Optional callback.
async function mrChooseInto(inputId, kind, onPicked) {
    const el = document.getElementById(inputId);
    const start = (el && el.value && el.value.trim()) || '';
    const p = await mrChoosePath(kind || 'folder', start);
    if (!p) return;
    if (el) {
        el.value = p;
        el.dispatchEvent(new Event('input',  { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (typeof onPicked === 'function') onPicked(p);
}

window.mrChoosePath = mrChoosePath;
window.mrChooseInto = mrChooseInto;
})();
