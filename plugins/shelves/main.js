/* Shelves — a plug-in that comes with the Music Room, and an example of one.
   Every record for sale, on shelves you choose. Tick up to 25 and make a crate.

   It uses: MusicRoom.ready, .catalogue(), .makeCrate(), .openRoom(), .cover(), .el()   (docs/PLUGINS.md) */
(async function () {
    const { el } = MusicRoom;
    const app = document.getElementById('app');
    await MusicRoom.ready;
    app.append(el('p', { class: 'mr-muted' }, 'Reading the shop…'));
    let all;
    try { all = await MusicRoom.catalogue(); }
    catch (e) { app.textContent = ''; app.append(el('p', null, e.message)); return; }

    const BY = {
        seller: { name: 'Seller', of: r => r.seller ? [r.seller.name] : ['No seller'] },
        label: { name: 'Label', of: r => [r.label || 'No label'] },
        genre: { name: 'Genre', of: r => r.genres.length ? r.genres : ['No genre'] },
        decade: { name: 'Decade', of: r => [r.year ? Math.floor(r.year / 10) * 10 + 's' : 'No year'] },
        place: { name: 'Place', of: r => [r.seller && r.seller.place || 'No place'] },
    };
    let by = 'seller';
    const ticked = new Set();

    function shelves() {
        const map = new Map();
        for (const r of all) for (const k of BY[by].of(r)) { if (!map.has(k)) map.set(k, []); map.get(k).push(r); }
        return [...map.entries()].sort((a, b) => a[0].startsWith('No ') - b[0].startsWith('No ') || a[0].localeCompare(b[0]));
    }

    function draw() {
        app.textContent = '';
        app.append(el('h1', null, 'Shelves'));
        if (!all.length) { app.append(el('p', { class: 'mr-muted' }, 'There are no records in the shop yet.')); return; }
        app.append(el('div', { class: 'sh-bar' },
            el('span', { class: 'mr-label' }, 'Shelved by'),
            Object.keys(BY).map(k => el('button', { class: 'mr-btn' + (k === by ? ' on' : ''), type: 'button', 'aria-pressed': String(k === by),
                onclick: () => { by = k; draw(); } }, BY[k].name)),
            el('span', { class: 'sh-count mr-muted' }, `${ticked.size} of 25 ticked`),
            el('button', { class: 'mr-btn mr-btn--go', type: 'button', disabled: !ticked.size, onclick: async e => {
                e.target.disabled = true;
                try { const d = await MusicRoom.makeCrate([...ticked], 'From the shelves'); ticked.clear(); MusicRoom.say(`A crate of ${d.count} is in Record shopping.`); draw(); }
                catch (err) { MusicRoom.say(err.message); e.target.disabled = false; }
            } }, 'Make a crate')));
        for (const [name, recs] of shelves()) {
            app.append(el('section', { class: 'sh-shelf' },
                el('h2', null, name, el('span', { class: 'mr-muted sh-n' }, ` ${recs.length}`)),
                el('div', { class: 'sh-row' }, recs.map(card))));
        }
    }

    function card(r) {
        const on = ticked.has(r.id);
        const src = MusicRoom.cover(r);
        return el('button', { class: 'sh-card mr-card' + (on ? ' on' : ''), type: 'button', 'aria-pressed': String(on),
            title: on ? 'Untick' : 'Tick, to put it in a crate',
            onclick: () => {
                if (on) ticked.delete(r.id);
                else if (ticked.size >= 25) return MusicRoom.say('A crate holds 25 records.');
                else ticked.add(r.id);
                draw();
            } },
            src ? el('img', { class: 'mr-card__cover', src, alt: '', loading: 'lazy' }) : el('div', { class: 'mr-card__cover sh-blank' }),
            el('div', { class: 'mr-card__t' }, r.title || 'Untitled'),
            el('div', { class: 'mr-card__s' }, [r.artist, r.year].filter(Boolean).join(' · ')));
    }
    draw();
})();
