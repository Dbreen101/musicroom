// room_blocks.js — the public room as a stack of BLOCKS.
//
// A room design is {theme:{…}, blocks:[{id, type, on, …settings}]}. Every
// block type lives in one registry entry: what it's called, the fields its
// editor shows, its defaults, and how it renders. The same file drives the
// public page (render) and the designer (schema). Adding a block type — by
// us, or later by the community — is one RoomBlocks.register(...) call:
// the editor grows a form for it, the room renders it. Nothing else changes.
//
// Field types the designer knows: text · textarea · number · select ·
// toggle · color · image (one uploaded asset) · images (several) ·
// records (pick from the room's own records) · places (a snapshot of the
// owner's places) · items (a small list, each with its own fields).

window.RoomBlocks = (function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const BLOCKS = {};
  const order = [];

  function register(type, def) {
    BLOCKS[type] = def;
    if (!order.includes(type)) order.push(type);
  }

  function newBlock(type) {
    const def = BLOCKS[type];
    const b = { id: 'b' + Math.random().toString(36).slice(2, 9), type, on: true };
    (def.schema || []).forEach(f => { b[f.key] = (f.default !== undefined) ? JSON.parse(JSON.stringify(f.default)) : (f.type === 'items' || f.type === 'images' || f.type === 'records' ? [] : (f.type === 'toggle' ? false : '')); });
    return b;
  }

  // the room a design gets before anyone has arranged it (and what older
  // designs — a flat 'items' list — turn into)
  function defaultBlocks(design, room) {
    const blocks = [newBlock('hero')];
    if ((room.tracks || []).length) blocks.push(Object.assign(newBlock('records'), { heading: design.records_heading || 'Records' }));
    if ((design.items || []).length) blocks.push(Object.assign(newBlock('picks'), { heading: design.picks_heading || 'Picks', items: design.items }));
    if (design.tagline) blocks[0].tagline = design.tagline;
    if (design.header_image_url) blocks[0].image_url = design.header_image_url;
    return blocks;
  }

  function assetUrl(ctx, id) { return id ? (ctx.assetUrl ? ctx.assetUrl(id) : `/api/gr/asset/${id}`) : ''; }
  function heading(b, fallback) { const h = (b.heading || '').trim() || fallback; return h ? `<h2 class="rb-h">${esc(h)}</h2>` : ''; }

  // ── the blocks ───────────────────────────────────────────────────────────

  register('hero', {
    label: 'Opening', hint: 'The top of the room: name, a line, an image.',
    schema: [
      { key: 'heading', type: 'text', label: 'Name (blank = your room\'s name)' },
      { key: 'tagline', type: 'text', label: 'A line under it' },
      { key: 'image', type: 'image', label: 'Image' },
      { key: 'layout', type: 'select', label: 'Layout', options: [['side', 'image beside the name'], ['cover', 'image behind the name'], ['plain', 'no image']], default: 'side' },
      { key: 'show_bio', type: 'toggle', label: 'Show the About text', default: true },
      { key: 'show_links', type: 'toggle', label: 'Show the links', default: true },
    ],
    render(b, ctx) {
      const r = ctx.room || {};
      const img = b.image ? assetUrl(ctx, b.image) : (b.image_url || '');
      const kind = r.kind ? `${esc(r.kind)}${r.kind !== 'listener' ? '’s music room' : ' · music room'}` : '';
      const links = (b.show_links !== false && (r.links || []).length)
        ? `<div class="rb-links">${r.links.map(l => `<a href="#" data-open="${esc(l.url)}">${esc(l.label || l.url)} ↗</a>`).join('')}</div>` : '';
      const text = `<div class="rb-hero__text">
          <div class="rb-eyebrow">${kind}</div>
          <h1 class="rb-name">${esc((b.heading || '').trim() || r.name || '')}</h1>
          ${b.tagline ? `<div class="rb-tag">${esc(b.tagline)}</div>` : ''}
          ${b.show_bio !== false && r.bio ? `<p class="rb-bio">${esc(r.bio)}</p>` : ''}
          ${links}</div>`;
      if (b.layout === 'cover' && img) return `<section class="rb rb-hero rb-hero--cover" style="--img:url('${esc(img)}')">${text}</section>`;
      if (b.layout === 'plain' || !img) return `<section class="rb rb-hero rb-hero--plain">${text}</section>`;
      return `<section class="rb rb-hero rb-hero--side">${text}<img class="rb-hero__img" src="${esc(img)}" alt=""></section>`;
    },
  });

  register('text', {
    label: 'Words', hint: 'A heading and a paragraph or two.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading' },
      { key: 'body', type: 'textarea', label: 'Text' },
      { key: 'width', type: 'select', label: 'Measure', options: [['narrow', 'a reading column'], ['wide', 'wide']], default: 'narrow' },
    ],
    render(b) { return `<section class="rb rb-text rb-text--${esc(b.width || 'narrow')}">${heading(b, '')}${b.body ? `<div class="rb-body">${esc(b.body).replace(/\n{2,}/g, '</p><p>').replace(/\n/g, '<br>')}</div>` : ''}</section>`; },
  });

  register('image', {
    label: 'Image', hint: 'One picture, any size.',
    schema: [
      { key: 'image', type: 'image', label: 'Image' },
      { key: 'caption', type: 'text', label: 'Caption' },
      { key: 'size', type: 'select', label: 'Size', options: [['small', 'small'], ['wide', 'wide'], ['full', 'edge to edge']], default: 'wide' },
    ],
    render(b, ctx) { const u = assetUrl(ctx, b.image); return u ? `<section class="rb rb-image rb-image--${esc(b.size || 'wide')}"><img src="${esc(u)}" alt="">${b.caption ? `<div class="rb-cap">${esc(b.caption)}</div>` : ''}</section>` : ''; },
  });

  register('gallery', {
    label: 'Gallery', hint: 'A row of pictures.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading' },
      { key: 'images', type: 'images', label: 'Images' },
    ],
    render(b, ctx) { const ids = (b.images || []).filter(Boolean); return ids.length ? `<section class="rb rb-gallery">${heading(b, '')}<div class="rb-gallery__row">${ids.map(id => `<img src="${esc(assetUrl(ctx, id))}" alt="" loading="lazy">`).join('')}</div></section>` : ''; },
  });

  register('records', {
    label: 'Records', hint: 'What you sell and lend. Artists, labels and shops.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading', default: 'Records' },
      { key: 'which', type: 'select', label: 'Which', options: [['all', 'all of them'], ['chosen', 'only the ones I pick']], default: 'all' },
      { key: 'ids', type: 'records', label: 'Pick records' },
      { key: 'layout', type: 'select', label: 'Layout', options: [['grid', 'grid'], ['large', 'large covers'], ['list', 'a list']], default: 'grid' },
    ],
    render(b, ctx) {
      let tracks = ctx.tracks || [];
      if (b.which === 'chosen') { const want = new Set((b.ids || []).map(Number)); tracks = tracks.filter(t => want.has(t.id)); }
      if (!tracks.length) return '';
      const cards = tracks.map(t => ctx.recordHtml ? ctx.recordHtml(t, b.layout) : `<div>${esc(t.title)}</div>`).join('');
      return `<section class="rb rb-records rb-records--${esc(b.layout || 'grid')}">${heading(b, 'Records')}<div class="rb-records__grid">${cards}</div></section>`;
    },
  });

  register('picks', {
    label: 'Picks', hint: 'Things you want people to know about — records, books, films, anything, with a line and a link. Words only, never audio.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading', default: 'Picks' },
      { key: 'items', type: 'items', label: 'Picks', fields: [['title', 'Title'], ['subtitle', 'Who / what'], ['note', 'A line about it'], ['url', 'Link']] , from_showcase: true },
    ],
    render(b) { const items = b.items || []; return items.length ? `<section class="rb rb-picks">${heading(b, 'Picks')}<div class="rb-picks__list">${items.map(p => `<div class="rb-pick"><div class="rb-pick__t">${esc(p.title || '')}</div>${p.subtitle ? `<div class="rb-pick__s">${esc(p.subtitle)}</div>` : ''}${p.note ? `<div class="rb-pick__n">${esc(p.note)}</div>` : ''}${p.url ? `<a href="#" data-open="${esc(p.url)}">open ↗</a>` : ''}</div>`).join('')}</div></section>` : ''; },
  });

  register('places', {
    label: 'Places', hint: 'The places from your forest — their names and colours, how many records live there.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading', default: 'Places' },
      { key: 'items', type: 'places', label: 'Places' },
    ],
    render(b) { const items = b.items || []; return items.length ? `<section class="rb rb-places">${heading(b, 'Places')}<div class="rb-places__grid">${items.map(p => `<div class="rb-place" style="--c:${esc(p.colour || '#5a4a3a')}"><i></i><div class="rb-place__n">${esc(p.name)}</div><div class="rb-place__c">${p.n != null ? `${p.n} record${p.n === 1 ? '' : 's'}` : ''}</div></div>`).join('')}</div></section>` : ''; },
  });

  // The grúpaí their owner has made public (each one's switch is inside it, in
  // My Room). ctx.grupai = the cards the rooms server sent with the room;
  // ctx.grupaCover(g) draws a cover (grupa_ui.js) — a plain name without it.
  // A room with public grúpaí shows them even if this block was never added
  // (see render below); adding it is how their owner chooses WHERE.
  register('grupai', {
    label: 'Grúpaí', hint: 'The grúpaí you have made public. Move this block to put them where you want them.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading', default: 'Grúpaí' },
      { key: 'layout', type: 'select', label: 'Layout', options: [['grid', 'covers'], ['list', 'a list']], default: 'grid' },
    ],
    render(b, ctx) {
      const list = ctx.grupai || [];
      if (!list.length) return '';
      const cover = ctx.grupaCover || (g => `<span class="rb-grupa__name">${esc(g.name)}</span>`);
      return `<section class="rb rb-grupai rb-grupai--${esc(b.layout || 'grid')}">${heading(b, 'Grúpaí')}<div class="rb-grupai__grid">${list.map(g =>
        `<a href="#" class="rb-grupa" data-grupa="${esc(g.id)}"><span class="rb-grupa__cover">${cover(g)}</span><span class="rb-grupa__main"><span class="rb-grupa__t">${esc(g.name)}</span>${g.description ? `<span class="rb-grupa__d">${esc(g.description)}</span>` : ''}<span class="rb-grupa__s">${esc(g.count)} in it</span></span></a>`).join('')}</div></section>`;
    },
  });

  register('links', {
    label: 'Links', hint: 'Where else to find you.',
    schema: [
      { key: 'heading', type: 'text', label: 'Heading' },
      { key: 'items', type: 'items', label: 'Links', fields: [['label', 'Label'], ['url', 'Link']] },
    ],
    render(b) { const items = (b.items || []).filter(i => i.url); return items.length ? `<section class="rb rb-linklist">${heading(b, '')}<div class="rb-links">${items.map(l => `<a href="#" data-open="${esc(l.url)}">${esc(l.label || l.url)} ↗</a>`).join('')}</div></section>` : ''; },
  });

  register('spacer', {
    label: 'Space', hint: 'Breathing room between things.',
    schema: [{ key: 'size', type: 'select', label: 'How much', options: [['small', 'a little'], ['large', 'a lot']], default: 'small' }],
    render(b) { return `<div class="rb rb-spacer rb-spacer--${esc(b.size || 'small')}"></div>`; },
  });

  register('custom', {
    label: 'Your own HTML', hint: 'A block of your own markup, kept in a box of its own (no scripts).',
    schema: [
      { key: 'html', type: 'textarea', label: 'HTML', code: true },
      { key: 'height', type: 'number', label: 'Height (px)', default: 320 },
    ],
    render(b, ctx) {
      if (!(b.html || '').trim()) return '';
      const css = ctx.css || '';
      const doc = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:transparent;color:inherit;font-family:inherit}${css}</style>${b.html}`;
      return `<section class="rb rb-custom"><iframe sandbox="" style="width:100%;height:${+b.height || 320}px;border:none" srcdoc="${esc(doc)}"></iframe></section>`;
    },
  });

  // ── rendering a whole design ─────────────────────────────────────────────
  function blocksOf(design, room) {
    const d = design || {};
    return Array.isArray(d.blocks) && d.blocks.length ? d.blocks : defaultBlocks(d, room || {});
  }
  function render(design, ctx) {
    let blocks = blocksOf(design, ctx.room);
    // public grúpaí are part of the room without being asked for: last, until
    // their owner places the Grúpaí block (or switches it off) in the builder
    if ((ctx.grupai || []).length && !blocks.some(b => b.type === 'grupai')) blocks = blocks.concat([newBlock('grupai')]);
    return blocks.filter(b => b.on !== false && BLOCKS[b.type]).map(b => {
      try { return BLOCKS[b.type].render(b, ctx); } catch (e) { return ''; }
    }).join('');
  }

  return { register, BLOCKS, order, newBlock, defaultBlocks, blocksOf, render, esc };
})();
