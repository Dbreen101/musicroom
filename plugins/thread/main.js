/* Thread — a plug-in that comes with the Music Room, and an example of one.
   Start from one record; follow a thread out from it by a rule you can read.
   No taste machine: every record it shows says exactly why it is there.

   It uses: MusicRoom.ready, .catalogue(), .makeCrate(), .cover(), .el()   (docs/PLUGINS.md) */
(async function () {
    const { el } = MusicRoom;
    const app = document.getElementById('app');
    await MusicRoom.ready;
    app.append(el('p', { class: 'mr-muted' }, 'Reading the shop…'));

    let all;
    try { all = await MusicRoom.catalogue(); }
    catch (e) { app.textContent = ''; app.append(el('p', null, e.message)); return; }

    const THREADS = [
        { key: 'label', name: 'Same label', test: (a, b) => a.label && b.label && a.label.toLowerCase() === b.label.toLowerCase() },
        { key: 'seller', name: 'Same seller', test: (a, b) => a.seller && b.seller && a.seller.handle === b.seller.handle },
        { key: 'genre', name: 'Same genre', test: (a, b) => a.genres.some(g => b.genres.map(x => x.toLowerCase()).includes(g.toLowerCase())) },
        { key: 'years', name: 'Within two years', test: (a, b) => a.year && b.year && Math.abs(a.year - b.year) <= 2 },
        { key: 'place', name: 'Same place', test: (a, b) => a.seller && b.seller && a.seller.place && a.seller.place === b.seller.place },
    ];
    let start = null, on = new Set(['label', 'seller', 'genre']);

    const fold = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const line = r => `${r.artist || 'Unknown'} — ${r.title || 'Untitled'}`;

    function found() {
        if (!start) return [];
        const out = [];
        for (const r of all) {
            if (r.id === start.id) continue;
            const why = THREADS.filter(t => on.has(t.key) && t.test(start, r)).map(t => t.name.toLowerCase());
            if (why.length) out.push({ r, why });
        }
        return out.sort((a, b) => b.why.length - a.why.length || fold(a.r.artist).localeCompare(fold(b.r.artist)));
    }

    function draw() {
        app.textContent = '';
        app.append(el('h1', null, 'Thread'));
        if (!all.length) { app.append(el('p', { class: 'mr-muted' }, 'There are no records in the shop yet.')); return; }
        if (!start) return drawPick();
        const hits = found();
        app.append(
            el('p', { class: 'mr-label' }, 'Starting from'),
            el('div', { class: 'th-start' }, cover(start), el('div', null, el('h2', null, start.title || 'Untitled'),
                el('p', { class: 'mr-muted' }, [start.artist, start.label, start.year, start.genres.join(', ')].filter(Boolean).join(' · ')),
                el('button', { class: 'mr-btn', type: 'button', onclick: () => { start = null; draw(); } }, 'Start from another'))),
            el('p', { class: 'mr-label' }, 'Follow it by'),
            el('div', { class: 'th-threads' }, THREADS.map(t => el('button', {
                class: 'mr-btn' + (on.has(t.key) ? ' on' : ''), type: 'button', 'aria-pressed': String(on.has(t.key)),
                onclick: () => { on.has(t.key) ? on.delete(t.key) : on.add(t.key); draw(); } }, t.name))),
            el('hr', { class: 'mr-rule' }));
        if (!hits.length) { app.append(el('p', { class: 'mr-muted' }, 'Nothing else shares that.')); return; }
        const take = hits.slice(0, 25);
        app.append(el('div', { class: 'th-head' },
            el('p', { class: 'mr-muted' }, `${hits.length} record${hits.length === 1 ? '' : 's'} on this thread` + (hits.length > 25 ? ' — a crate takes the first 25' : '')),
            el('button', { class: 'mr-btn mr-btn--go', type: 'button', onclick: async e => {
                e.target.disabled = true;
                try { const d = await MusicRoom.makeCrate(take.map(h => h.r.id), 'A thread from ' + (start.title || 'a record')); MusicRoom.say(`A crate of ${d.count} is in Record shopping.`); }
                catch (err) { MusicRoom.say(err.message); e.target.disabled = false; }
            } }, 'Make a crate of these')));
        app.append(el('div', { class: 'mr-grid' }, hits.map(h => el('div', { class: 'mr-card' }, cover(h.r),
            el('div', { class: 'mr-card__t' }, h.r.title || 'Untitled'),
            el('div', { class: 'mr-card__s' }, h.r.artist || ''),
            el('div', { class: 'th-why' }, h.why.join(' · '))))));
    }

    function drawPick() {
        const box = el('input', { class: 'mr-input th-find', type: 'search', placeholder: 'find a record to start from', 'aria-label': 'Find a record to start from' });
        const rows = el('div', { class: 'th-rows' });
        const fill = () => {
            rows.textContent = '';
            const words = fold(box.value).split(/\s+/).filter(Boolean);
            const list = all.filter(r => words.every(w => fold([r.title, r.artist, r.album, r.label, r.genres.join(' '), r.seller && r.seller.name].join(' ')).includes(w)));
            list.slice(0, 80).forEach(r => rows.append(el('button', { class: 'th-row', type: 'button', onclick: () => { start = r; draw(); } },
                cover(r), el('span', null, line(r)), el('span', { class: 'mr-muted' }, [r.label, r.year].filter(Boolean).join(' · ')))));
            if (!list.length) rows.append(el('p', { class: 'mr-muted' }, 'Nothing matches.'));
        };
        box.addEventListener('input', fill);
        app.append(box, rows);
        fill(); box.focus();
    }

    function cover(r) {
        const src = MusicRoom.cover(r);
        return src ? el('img', { class: 'mr-card__cover', src, alt: '', loading: 'lazy' }) : el('div', { class: 'mr-card__cover th-blank' });
    }
    draw();
})();
