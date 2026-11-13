/* Lex Constitutio: client-side index of constitutional law review articles.
   Data comes from data/articles.js (window.CL_DATA), built by scripts/build.ps1. */
(function () {
  'use strict';

  const DATA = window.CL_DATA;
  const app = document.getElementById('app');
  if (!DATA) {
    app.innerHTML = '<div class="prose"><h1>No data yet</h1><p>Run <code>scripts/harvest.sh</code> and <code>scripts/build.ps1</code> to generate <code>site/data/articles.js</code>.</p></div>';
    return;
  }

  /* ------------------------------------------------------------ reference data */
  const ABBR = {
    mlr_mich: 'Mich. L. Rev.', uclrev: 'U. Chi. L. Rev.', clr: 'Cornell L. Rev.', dlj: 'Duke L.J.',
    ndlr: 'Notre Dame L. Rev.', vlr: 'Vand. L. Rev.', mlr_minn: 'Minn. L. Rev.', flr: 'Fordham L. Rev.',
    nulr: 'Nw. U. L. Rev.', elj: 'Emory L.J.', wmlr: 'Wm. & Mary L. Rev.', wlulr: 'Wash. & Lee L. Rev.',
    byulr: 'BYU L. Rev.', concomm: 'Const. Comment.', hclq: 'Hastings Const. L.Q.', wmborj: 'Wm. & Mary Bill Rts. J.',
    nyulr: 'N.Y.U. L. Rev.', tlr: 'Tex. L. Rev.', uclalr: 'UCLA L. Rev.',
    hlr: 'Harv. L. Rev.', ylj: 'Yale L.J.', colr: 'Colum. L. Rev.', valr: 'Va. L. Rev.', calr: 'Calif. L. Rev.',
    pennlr: 'U. Pa. L. Rev.', slr: 'Stan. L. Rev.', glj: 'Geo. L.J.'
  };
  const OPENALEX_JOURNALS = new Set(['hlr', 'ylj', 'colr', 'valr', 'calr', 'pennlr', 'slr', 'glj']);
  const SUGGESTIONS = ['originalism', 'nondelegation', 'qualified immunity', 'Bruen', 'shadow docket', 'Dobbs', 'free exercise', 'Article III standing'];
  const PAGE_SIZE = 20;
  const STOP = new Set('a an and are as at be by for from has have in is it its of on or that the this to was were with v vs law legal constitutional constitution article essay note review court courts rights right state states united american toward towards new after against between over under how why what'.split(' '));

  const journals = DATA.journals.filter(j => j.count > 0);
  const journalById = Object.fromEntries(DATA.journals.map(j => [j.id, j]));
  const topics = DATA.topics;
  const topicById = Object.fromEntries(topics.map(t => [t.id, t]));
  const parents = topics.filter(t => !t.parent);
  const childrenOf = id => topics.filter(t => t.parent === id);

  /* ------------------------------------------------------------ indexes */
  const articles = DATA.articles;
  const byId = new Map();
  const authorIndex = new Map();
  const topicCount = {};
  const yearCount = {};
  let minYear = 9999, maxYear = 0;
  const normName = s => s.toLowerCase().replace(/[.,]/g, '').replace(/\s+/g, ' ').trim();

  for (const a of articles) {
    a.a = a.a || []; a.tp = a.tp || []; a.kw = a.kw || [];
    a._t = a.t.toLowerCase();
    a._a = a.a.join(' ; ').toLowerCase();
    a._ab = (a.ab || '').toLowerCase();
    a._kw = a.kw.join(' ; ').toLowerCase();
    byId.set(a.id, a);
    for (const n of a.a) {
      const k = normName(n);
      if (!authorIndex.has(k)) authorIndex.set(k, { name: n, items: [] });
      authorIndex.get(k).items.push(a);
    }
    const seenParents = new Set();
    for (const t of a.tp) {
      topicCount[t] = (topicCount[t] || 0) + 1;
      const p = topicById[t] && topicById[t].parent;
      if (p && !seenParents.has(p)) { seenParents.add(p); topicCount[p] = (topicCount[p] || 0) + 1; }
    }
    if (a.y) {
      yearCount[a.y] = (yearCount[a.y] || 0) + 1;
      if (a.y < minYear) minYear = a.y;
      if (a.y > maxYear) maxYear = a.y;
    }
  }
  // the histogram starts where coverage becomes meaningful
  const HISTO_START = Math.max(minYear, 1950);

  // impact: citation percentile among articles from the same decade that have citation data
  const byDecade = {};
  for (const a of articles) if (a.c != null && a.y) (byDecade[Math.floor(a.y / 10) * 10] ||= []).push(a);
  for (const list of Object.values(byDecade)) {
    list.sort((x, y) => x.c - y.c);
    list.forEach((a, i) => { a._pct = list.length > 1 ? Math.round(100 * i / (list.length - 1)) : 50; });
  }
  const citedCount = articles.filter(a => a.c != null).length;
  function impactLabel(a) {
    if (a._pct == null) return '';
    const top = 100 - a._pct;
    return top <= 1 ? 'Top 1%' : top <= 5 ? 'Top 5%' : top <= 10 ? 'Top 10%' : top <= 25 ? 'Top 25%' : '';
  }

  /* ------------------------------------------------------------ saved list */
  const SAVE_KEY = 'cl-saved';
  let saved = new Set(JSON.parse(localStorage.getItem(SAVE_KEY) || '[]'));
  function persistSaved() {
    localStorage.setItem(SAVE_KEY, JSON.stringify([...saved]));
    const el = document.getElementById('saved-count');
    el.textContent = saved.size; el.dataset.zero = saved.size ? '0' : '1';
  }
  function toggleSave(id) {
    if (saved.has(id)) { saved.delete(id); toast('Removed from your list'); }
    else { saved.add(id); toast('Saved to your list'); }
    persistSaved();
    document.querySelectorAll(`.save-btn[data-id="${CSS.escape(id)}"]`).forEach(b => b.classList.toggle('on', saved.has(id)));
  }

  /* ------------------------------------------------------------ helpers */
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => n.toLocaleString('en-US');
  const authorHref = n => '#/author/' + encodeURIComponent(normName(n));
  const articleHref = a => '#/article/' + encodeURIComponent(a.id);
  function toast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), 1800);
  }
  function hashFor(path, params) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length)) p.set(k, Array.isArray(v) ? v.join(',') : v);
    const s = p.toString();
    return '#/' + path + (s ? '?' + s : '');
  }
  function initials(name) {
    const parts = name.replace(/,.*$/, '').split(/\s+/).filter(Boolean);
    return ((parts[0] || '')[0] || '') + ((parts[parts.length - 1] || '')[0] || '');
  }
  function authorList(a, link = true) {
    if (!a.a.length) return '<span class="muted">Author not listed</span>';
    return a.a.map(n => link ? `<a href="${authorHref(n)}">${esc(n)}</a>` : esc(n)).join(', ');
  }
  function citeLine(a) {
    const j = journalById[a.j];
    const parts = [];
    if (a.v) parts.push(`Vol. ${a.v}${a.i ? `, No. ${a.i}` : ''}`);
    if (a.y) parts.push(a.y);
    const il = impactLabel(a);
    const cites = a.c != null ? `<span class="cites" title="Citations recorded by OpenAlex${il ? ' · ' + il + ' of its decade' : ''}">${citeIcon}${fmt(a.c)}${il ? ` <b>${il}</b>` : ''}</span>` : '';
    return `<a class="jn" href="${hashFor('search', { j: a.j })}">${esc(j ? j.name : a.j)}</a>` + parts.map(p => `<span>${esc(p)}</span>`).join('') + cites + (a.rv ? '<span class="rv">Book review</span>' : '');
  }
  const citeIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h4v4H8c0 2 1 3 3 3v2c-3 0-4-2-4-5zM14 7h4v4h-3c0 2 1 3 3 3v2c-3 0-4-2-4-5z"/></svg>';

  /* ------------------------------------------------------------ search */
  function parseQuery(q) {
    const phrases = []; let rest = q;
    rest = rest.replace(/"([^"]+)"/g, (_, p) => { phrases.push(p.toLowerCase().trim()); return ' '; });
    const terms = rest.toLowerCase().split(/[^a-z0-9§'-]+/).map(s => s.replace(/^'+|'+$/g, '')).filter(t => t && (t.length > 1 || /\d/.test(t)));
    const whole = q.replace(/"/g, '').toLowerCase().trim();
    return { phrases, terms, whole: terms.length > 1 ? whole : '' };
  }
  function scoreArticle(a, pq) {
    let score = 0;
    for (const p of pq.phrases) {
      let s = 0;
      if (a._t.includes(p)) s += 12;
      if (a._a.includes(p)) s += 10;
      if (a._kw.includes(p)) s += 5;
      if (a._ab.includes(p)) s += 3;
      if (!s) return 0;
      score += s;
    }
    for (const t of pq.terms) {
      let s = 0;
      if (a._t.includes(t)) s += 6;
      if (a._a.includes(t)) s += 5;
      if (a._kw.includes(t)) s += 3;
      if (a._ab.includes(t)) s += 1;
      if (!s) return 0;
      score += s;
    }
    if (pq.whole) {
      if (a._t.includes(pq.whole)) score += 20;
      else if (a._kw.includes(pq.whole) || a._ab.includes(pq.whole)) score += 6;
    }
    return score;
  }
  function runSearch(st) {
    const pq = parseQuery(st.q || '');
    const hasQ = pq.terms.length || pq.phrases.length;
    const jset = st.j.length ? new Set(st.j) : null;
    const isParent = st.topic && !topicById[st.topic]?.parent;
    const tset = st.topic ? new Set(isParent ? [st.topic, ...childrenOf(st.topic).map(c => c.id)] : [st.topic]) : null;
    const out = [];
    for (const a of articles) {
      if (jset && !jset.has(a.j)) continue;
      if (tset && !a.tp.some(t => tset.has(t))) continue;
      if (st.from && (!a.y || a.y < st.from)) continue;
      if (st.to && (!a.y || a.y > st.to)) continue;
      let s = 1;
      if (hasQ) { s = scoreArticle(a, pq); if (!s) continue; }
      out.push({ a, s });
    }
    const sort = st.sort || (hasQ ? 'relevance' : 'newest');
    if (sort === 'relevance') out.sort((x, y) => y.s - x.s || (y.a.y || 0) - (x.a.y || 0));
    else if (sort === 'oldest') out.sort((x, y) => (x.a.y || 9999) - (y.a.y || 9999));
    else if (sort === 'cited') out.sort((x, y) => (y.a.c ?? -1) - (x.a.c ?? -1) || (y.a.y || 0) - (x.a.y || 0));
    else out.sort((x, y) => (y.a.y || 0) - (x.a.y || 0));
    return { results: out.map(o => o.a), pq, sort };
  }
  function highlight(text, pq) {
    let html = esc(text);
    const needles = [...pq.phrases, ...pq.terms].filter(n => n.length > 1).sort((a, b) => b.length - a.length);
    if (!needles.length) return html;
    const re = new RegExp('(' + needles.map(n => esc(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
    return html.replace(re, '<mark>$1</mark>');
  }

  /* ------------------------------------------------------------ components */
  const bookmarkSvg = '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>';
  function card(a, pq) {
    const H = pq ? (s => highlight(s, pq)) : esc;
    const tags = a.tp.map(t => topicById[t] ? `<a class="tag" href="${hashFor('search', { topic: t })}">${esc(topicById[t].name)}</a>` : '').join('');
    return `<article class="card">
      <button class="save-btn ${saved.has(a.id) ? 'on' : ''}" data-id="${esc(a.id)}" title="Save to my list" aria-label="Save to my list">${bookmarkSvg}</button>
      <div class="card-meta">${citeLine(a)}</div>
      <h3><a href="${articleHref(a)}">${H(a.t)}</a></h3>
      <div class="authors">${authorList(a)}</div>
      ${a.ab ? `<p class="abs">${H(a.ab)}</p>` : ''}
      ${tags ? `<div class="tags">${tags}</div>` : ''}
    </article>`;
  }
  function topicCard(p, maxChild) {
    const kids = childrenOf(p.id).sort((x, y) => (topicCount[y.id] || 0) - (topicCount[x.id] || 0));
    return `<section class="topic-card">
      <header><h3><a href="${hashFor('search', { topic: p.id })}">${esc(p.name)}</a></h3><span class="count">${fmt(topicCount[p.id] || 0)} articles</span></header>
      <p>${esc(p.desc || '')}</p>
      <ul class="subtopics">${kids.map(k => `<li><a href="${hashFor('search', { topic: k.id })}"><span style="flex:1">${esc(k.name)}<div class="bar"><i style="width:${Math.round(100 * (topicCount[k.id] || 0) / maxChild)}%"></i></div></span><span class="n">${fmt(topicCount[k.id] || 0)}</span></a></li>`).join('')}</ul>
    </section>`;
  }
  function pager(total, page, mk, size = PAGE_SIZE) {
    const pages = Math.ceil(total / size);
    if (pages <= 1) return '';
    const nums = new Set([1, pages, page, page - 1, page + 1, page - 2, page + 2].filter(n => n >= 1 && n <= pages));
    const sorted = [...nums].sort((a, b) => a - b);
    let html = `<button data-page="${page - 1}" ${page === 1 ? 'disabled' : ''} aria-label="Previous">‹</button>`;
    let prev = 0;
    for (const n of sorted) {
      if (n - prev > 1) html += '<span class="gap">…</span>';
      html += `<button data-page="${n}" class="${n === page ? 'on' : ''}">${n}</button>`;
      prev = n;
    }
    html += `<button data-page="${page + 1}" ${page === pages ? 'disabled' : ''} aria-label="Next">›</button>`;
    return `<nav class="pager" data-mk="${esc(mk)}">${html}</nav>`;
  }

  /* ------------------------------------------------------------ views */
  function viewHome() {
    const maxChild = Math.max(...topics.filter(t => t.parent).map(t => topicCount[t.id] || 0), 1);
    const recent = articles.filter(a => a.ab).slice(0, 6);
    const specialists = journals.filter(j => j.specialist);
    const general = journals.filter(j => !j.specialist);
    app.innerHTML = `<div class="fade-in">
      <section class="hero"><div class="hero-inner">
        <span class="eyebrow">An index of constitutional scholarship</span>
        <h1>The constitutional law literature, <em>in one place.</em></h1>
        <p class="lede">Search and browse ${fmt(articles.length)} constitutional law articles from ${journals.length} leading law reviews. Everything is organized by topic, author, and journal, and links back to the full text.</p>
        <form class="bigsearch" id="bigsearch">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          <input id="bigsearch-input" type="search" placeholder='Try "unitary executive" or Amar' autocomplete="off" aria-label="Search the index">
          <button class="btn btn-primary" type="submit">Search</button>
        </form>
        <div class="suggest"><span>Popular:</span>${SUGGESTIONS.map(s => `<a class="chip" href="${hashFor('search', { q: s })}">${esc(s)}</a>`).join('')}</div>
        <div class="stats">
          <div class="stat"><b>${fmt(articles.length)}</b><span>Articles</span></div>
          <div class="stat"><b>${fmt(authorIndex.size)}</b><span>Authors</span></div>
          <div class="stat"><b>${journals.length}</b><span>Law reviews</span></div>
          <div class="stat"><b>${topics.filter(t => t.parent).length}</b><span>Topics</span></div>
        </div>
      </div></section>

      <section class="section">
        <div class="features">
          <a class="feature" href="#/guide"><span class="f-icon">◎</span><b>Beginner's Guide</b><span>Twenty core topics for newcomers, then an advanced, doctrine-by-doctrine treatment with tests and excerpts from the opinions.</span><em>Start learning →</em></a>
          <a class="feature" href="#/corner"><span class="f-icon">❦</span><b>Originalist's Corner</b><span>Blackstone, The Federalist, the Convention debates, Story and the first Congresses' statutes, organized by topic.</span><em>Read the sources →</em></a>
          <a class="feature" href="#/scotus"><span class="f-icon">⚖</span><b>Supreme Court</b><span>Case summaries, opinion PDFs, and oral arguments you can play here with a synced transcript.</span><em>Browse decisions →</em></a>
          <a class="feature" href="#/impact"><span class="f-icon">↗</span><b>Most influential articles</b><span>The most-cited constitutional scholarship, by topic, decade and journal.</span><em>See rankings →</em></a>
        </div>
      </section>

      <section class="section">
        <div class="section-head"><div><h2>Most influential</h2><p>The most-cited articles in the index.</p></div><a class="link-arrow" href="#/impact">Full rankings →</a></div>
        <div class="cards">${articles.filter(a => a.c != null).sort((x, y) => y.c - x.c).slice(0, 4).map(a => card(a)).join('')}</div>
      </section>

      <section class="section">
        <div class="section-head"><div><h2>Browse by topic</h2><p>A taxonomy of constitutional law. Each article is tagged with up to four topics.</p></div><a class="link-arrow" href="#/topics">All topics →</a></div>
        <div class="topic-grid">${parents.map(p => topicCard(p, maxChild)).join('')}</div>
      </section>

      <section class="section">
        <div class="section-head"><div><h2>Recently published</h2><p>The newest articles in the index.</p></div><a class="link-arrow" href="${hashFor('search', { sort: 'newest' })}">See all →</a></div>
        <div class="cards">${recent.map(a => card(a)).join('')}</div>
      </section>

      <section class="section">
        <div class="section-head"><div><h2>Journals</h2><p>General law reviews and specialist constitutional law journals.</p></div><a class="link-arrow" href="#/journals">Journal directory →</a></div>
        <div class="journal-strip">${[...specialists, ...general].map(j => `<a href="${hashFor('search', { j: j.id })}">${esc(j.name)}<small>${fmt(j.count)}</small></a>`).join('')}</div>
      </section>
    </div>`;
    const f = document.getElementById('bigsearch');
    f.addEventListener('submit', e => { e.preventDefault(); location.hash = hashFor('search', { q: document.getElementById('bigsearch-input').value.trim() }); });
  }

  function viewTopics() {
    const maxChild = Math.max(...topics.filter(t => t.parent).map(t => topicCount[t.id] || 0), 1);
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Topics</span></div>
        <h1>Topics</h1><p>Five areas and ${topics.filter(t => t.parent).length} subtopics. Topics are assigned automatically from each article's title, abstract, and subject keywords, so an article can sit under more than one.</p>${articleTabs('topics')}</div>
      <section class="section" style="padding-top:28px"><div class="topic-grid">${parents.map(p => topicCard(p, maxChild)).join('')}</div></section>
    </div>`;
  }

  function readSearchState(params) {
    return {
      q: params.get('q') || '',
      topic: params.get('topic') || '',
      j: (params.get('j') || '').split(',').filter(Boolean),
      from: +params.get('from') || 0,
      to: +params.get('to') || 0,
      sort: params.get('sort') || '',
      page: Math.max(1, +params.get('page') || 1)
    };
  }
  function viewSearch(params) {
    const st = readSearchState(params);
    const { results, pq, sort } = runSearch(st);
    const page = Math.min(st.page, Math.max(1, Math.ceil(results.length / PAGE_SIZE)));
    const slice = results.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const go = patch => { location.hash = hashFor('search', Object.assign({}, st, { page: 1 }, patch)); };
    const t = topicById[st.topic];
    const hasQ = pq.terms.length || pq.phrases.length;

    let title = 'Browse the index', sub = `${fmt(articles.length)} articles across ${journals.length} law reviews.`, crumbs = '';
    if (t) {
      const par = t.parent ? topicById[t.parent] : null;
      title = t.name;
      sub = t.parent ? `A subtopic of ${par.name}.` : (t.desc || '');
      crumbs = `<a href="#/topics">Topics</a><span>/</span>` + (par ? `<a href="${hashFor('search', { topic: par.id })}">${esc(par.name)}</a><span>/</span>` : '') + `<span>${esc(t.name)}</span>`;
    } else if (hasQ) {
      title = `Results for “${st.q}”`; sub = ''; crumbs = '<span>Search</span>';
    } else if (st.j.length === 1 && journalById[st.j[0]]) {
      title = journalById[st.j[0]].name; sub = 'Constitutional law articles from this journal.'; crumbs = '<a href="#/journals">Journals</a><span>/</span><span>' + esc(title) + '</span>';
    } else crumbs = '<span>Browse</span>';

    // facets: counts reflect every filter except the facet itself
    const jCounts = {};
    for (const a of runSearch(Object.assign({}, st, { j: [] })).results) jCounts[a.j] = (jCounts[a.j] || 0) + 1;
    const tCounts = {};
    for (const a of runSearch(Object.assign({}, st, { topic: '' })).results) {
      const ps = new Set();
      for (const x of a.tp) { tCounts[x] = (tCounts[x] || 0) + 1; const p = topicById[x]?.parent; if (p && !ps.has(p)) { ps.add(p); tCounts[p] = (tCounts[p] || 0) + 1; } }
    }
    const yCounts = {};
    for (const a of runSearch(Object.assign({}, st, { from: 0, to: 0 })).results) if (a.y >= HISTO_START) yCounts[a.y] = (yCounts[a.y] || 0) + 1;
    const yMax = Math.max(1, ...Object.values(yCounts));
    const years = []; for (let y = HISTO_START; y <= maxYear; y++) years.push(y);

    const chips = [];
    if (hasQ) chips.push(`<button class="chip on" data-clear="q">“${esc(st.q)}” <span class="x">✕</span></button>`);
    if (t) chips.push(`<button class="chip on" data-clear="topic">${esc(t.name)} <span class="x">✕</span></button>`);
    for (const j of st.j) chips.push(`<button class="chip on" data-clear-j="${esc(j)}">${esc(journalById[j]?.name || j)} <span class="x">✕</span></button>`);
    if (st.from || st.to) chips.push(`<button class="chip on" data-clear="years">${st.from || '…'}–${st.to || '…'} <span class="x">✕</span></button>`);

    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span>${crumbs}</div><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ''}${articleTabs('all', st.topic)}</div>
      <div class="layout">
        <aside class="sidebar" id="sidebar">
          <div class="side-block"><h4>Search within</h4>
            <form id="refine"><input class="input" id="refine-q" type="search" value="${esc(st.q)}" placeholder="Keywords, author, "phrase"…"></form>
          </div>
          <div class="side-block"><h4>Topics</h4>
            <ul class="tree">
              <li><a href="${hashFor('search', Object.assign({}, st, { topic: '', page: 1 }))}" class="${!st.topic ? 'on' : ''}"><span>All topics</span></a></li>
              ${parents.map(p => `<li class="parent"><a href="${hashFor('search', Object.assign({}, st, { topic: p.id, page: 1 }))}" class="${st.topic === p.id ? 'on' : ''}"><span>${esc(p.name)}</span><span class="n">${fmt(tCounts[p.id] || 0)}</span></a>
                <ul>${childrenOf(p.id).map(c => `<li><a href="${hashFor('search', Object.assign({}, st, { topic: c.id, page: 1 }))}" class="${st.topic === c.id ? 'on' : ''}"><span>${esc(c.name)}</span><span class="n">${fmt(tCounts[c.id] || 0)}</span></a></li>`).join('')}</ul></li>`).join('')}
            </ul>
          </div>
          <div class="side-block"><h4>Year</h4>
            <div class="histo">${years.map(y => `<i title="${y}: ${yCounts[y] || 0}" class="${(!st.from || y >= st.from) && (!st.to || y <= st.to) ? 'in' : ''}" style="height:${Math.round(100 * Math.sqrt((yCounts[y] || 0) / yMax))}%"></i>`).join('')}</div>
            <div class="histo-axis"><span>${HISTO_START}</span><span>${maxYear}</span></div>
            <div class="row2">
              <input class="input" id="from" type="number" min="${minYear}" max="${maxYear}" placeholder="From" value="${st.from || ''}" aria-label="From year">
              <input class="input" id="to" type="number" min="${minYear}" max="${maxYear}" placeholder="To" value="${st.to || ''}" aria-label="To year">
            </div>
            <div class="suggest" style="margin-top:10px">
              <button class="chip" data-years="${maxYear - 4}-">Last 5 years</button><button class="chip" data-years="2010-">Since 2010</button><button class="chip" data-years="2000-">Since 2000</button>
            </div>
          </div>
          <div class="side-block"><h4>Journals</h4>
            <ul class="tree">${journals.slice().sort((x, y) => (jCounts[y.id] || 0) - (jCounts[x.id] || 0)).map(j => `<li><a href="#" data-j="${j.id}" class="${st.j.includes(j.id) ? 'on' : ''}"><span>${esc(j.name)}</span><span class="n">${fmt(jCounts[j.id] || 0)}</span></a></li>`).join('')}</ul>
          </div>
        </aside>
        <div>
          <div class="toolbar">
            <div class="count"><button class="btn btn-ghost btn-sm filter-toggle" id="filter-toggle">Filters</button> <b>${fmt(results.length)}</b> article${results.length === 1 ? '' : 's'}${results.length > PAGE_SIZE ? ` · page ${page} of ${Math.ceil(results.length / PAGE_SIZE)}` : ''}</div>
            <div class="seg" role="group" aria-label="Sort">
              ${hasQ ? `<button data-sort="relevance" class="${sort === 'relevance' ? 'on' : ''}">Relevance</button>` : ''}
              <button data-sort="newest" class="${sort === 'newest' ? 'on' : ''}">Newest</button>
              <button data-sort="oldest" class="${sort === 'oldest' ? 'on' : ''}">Oldest</button>
              <button data-sort="cited" class="${sort === 'cited' ? 'on' : ''}">Most cited</button>
            </div>
          </div>
          ${chips.length ? `<div class="active-filters">${chips.join('')}<a class="chip" href="#/search">Clear all</a></div>` : ''}
          ${slice.length ? `<div class="cards">${slice.map(a => card(a, hasQ ? pq : null)).join('')}</div>` : `<div class="empty"><h3>No articles found</h3><p>Try fewer keywords or remove a filter.</p></div>`}
          ${pager(results.length, page, 'search')}
        </div>
      </div></div>`;

    document.getElementById('refine').addEventListener('submit', e => { e.preventDefault(); go({ q: document.getElementById('refine-q').value.trim(), sort: '' }); });
    app.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () => go({ sort: b.dataset.sort })));
    app.querySelectorAll('[data-j]').forEach(b => b.addEventListener('click', e => {
      e.preventDefault(); const id = b.dataset.j;
      go({ j: st.j.includes(id) ? st.j.filter(x => x !== id) : [...st.j, id] });
    }));
    app.querySelectorAll('[data-clear]').forEach(b => b.addEventListener('click', () => {
      const k = b.dataset.clear; go(k === 'years' ? { from: 0, to: 0 } : { [k]: '' });
    }));
    app.querySelectorAll('[data-clear-j]').forEach(b => b.addEventListener('click', () => go({ j: st.j.filter(x => x !== b.dataset.clearJ) })));
    app.querySelectorAll('[data-years]').forEach(b => b.addEventListener('click', () => { const [f, t2] = b.dataset.years.split('-'); go({ from: +f || 0, to: +t2 || 0 }); }));
    const yr = () => go({ from: +document.getElementById('from').value || 0, to: +document.getElementById('to').value || 0 });
    document.getElementById('from').addEventListener('change', yr);
    document.getElementById('to').addEventListener('change', yr);
    document.getElementById('filter-toggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
    bindPager(n => { location.hash = hashFor('search', Object.assign({}, st, { page: n })); });
  }

  function related(a, n = 6) {
    const words = new Set(a._t.split(/[^a-z0-9]+/).filter(w => w.length > 3 && !STOP.has(w)));
    const tp = new Set(a.tp), kw = new Set(a.kw.map(k => k.toLowerCase()));
    const scored = [];
    for (const b of articles) {
      if (b === a) continue;
      let s = 0;
      for (const t of b.tp) if (tp.has(t)) s += 2;
      for (const k of b.kw) if (kw.has(k.toLowerCase())) s += 1.5;
      for (const w of b._t.split(/[^a-z0-9]+/)) if (words.has(w)) s += 2.5;
      if (s >= 4) scored.push([s, b]);
    }
    return scored.sort((x, y) => y[0] - x[0]).slice(0, n).map(x => x[1]);
  }
  function bluebook(a) {
    const au = a.a.length > 2 ? `${a.a[0]} et al.` : a.a.join(' & ');
    const vol = a.v ? a.v + ' ' : '';
    const ab = ABBR[a.j] || journalById[a.j]?.name || '';
    return `${au ? esc(au) + ', ' : ''}<i>${esc(a.t)}</i>, ${esc(vol)}<span style="font-variant:small-caps">${esc(ab)}</span> ${a.fp ? a.fp + ' ' : ''}${a.y ? '(' + a.y + ')' : ''}.`;
  }
  function bibtex(a) {
    const last = (a.a[0] || 'anon').split(/\s+/).pop().toLowerCase().replace(/[^a-z]/g, '');
    const word = (a._t.split(/[^a-z]+/).find(w => w.length > 3 && !STOP.has(w)) || 'article');
    const f = [
      ['author', a.a.join(' and ')], ['title', '{' + a.t + '}'], ['journal', journalById[a.j]?.name],
      ['volume', a.v], ['number', a.i], ['year', a.y], ['url', a.u]
    ].filter(x => x[1]);
    return `@article{${last}${a.y || ''}${word},\n` + f.map(([k, v]) => `  ${k} = {${v}}`).join(',\n') + '\n}';
  }
  function plainCite(a) {
    const au = a.a.length > 2 ? `${a.a[0]} et al.` : a.a.join(' & ');
    return `${au ? au + ', ' : ''}${a.t}, ${a.v ? a.v + ' ' : ''}${ABBR[a.j] || journalById[a.j]?.name || ''} ${a.fp ? a.fp + ' ' : ''}${a.y ? '(' + a.y + ')' : ''}.`.replace(/\s+\./, '.');
  }

  function viewArticle(id) {
    const a = byId.get(id);
    if (!a) return viewNotFound();
    const j = journalById[a.j];
    const rel = related(a);
    const moreBy = a.a.length ? (authorIndex.get(normName(a.a[0]))?.items || []).filter(b => b !== a).slice(0, 4) : [];
    app.innerHTML = `<div class="fade-in"><div class="article">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="${hashFor('search', { j: a.j })}">${esc(j?.name)}</a>${a.y ? `<span>/</span><span>${a.y}</span>` : ''}</div>
        <h1>${esc(a.t)}</h1>
        <div class="byline">${authorList(a)}</div>
        <div class="publine"><a href="${hashFor('search', { j: a.j })}">${esc(j?.name)}</a>${a.v ? ` · Volume ${a.v}` : ''}${a.i ? `, Issue ${a.i}` : ''}${a.y ? ` · ${a.y}` : ''}</div>
        <h2>Abstract</h2>
        ${a.ab ? `<div class="abstract">${esc(a.ab)}</div>` : '<p style="color:var(--ink-3)">No abstract is available for this article. Open the full text at the publisher.</p>'}
        <div class="actions">
          ${a.pdf ? `<a class="btn btn-primary" href="${esc(a.pdf)}" target="_blank" rel="noopener">Read the PDF ↗</a>` : ''}
          <a class="btn ${a.pdf ? 'btn-ghost' : 'btn-primary'}" href="${esc(a.u)}" target="_blank" rel="noopener">${/doi\.org\/10\.2307/.test(a.u) ? 'View on JSTOR' : /doi\.org/.test(a.u) ? 'View via DOI' : 'View at ' + esc(j?.name || 'publisher')} ↗</a>
          ${OPENALEX_JOURNALS.has(a.j) && j ? `<a class="btn btn-ghost" href="https://www.google.com/search?q=${encodeURIComponent('site:' + j.host + ' "' + a.t + '"')}" target="_blank" rel="noopener">Find on ${esc(j.host.replace(/^www\./, ''))} ↗</a>` : ''}
          <button class="btn btn-ghost" id="save-article">${saved.has(a.id) ? '★ Saved' : '☆ Save to my list'}</button>
          <a class="btn btn-ghost" href="https://scholar.google.com/scholar?q=${encodeURIComponent('"' + a.t + '"')}" target="_blank" rel="noopener">Google Scholar ↗</a>
        </div>
        ${a.tp.length ? `<h2>Topics</h2><div class="tags">${a.tp.map(t => `<a class="tag" href="${hashFor('search', { topic: t })}">${esc(topicById[t]?.parent ? topicById[topicById[t].parent].name + ' › ' : '')}${esc(topicById[t]?.name)}</a>`).join('')}</div>` : ''}
        ${a.kw.length ? `<h2>Keywords</h2><div class="tags">${a.kw.map(k => `<a class="tag" href="${hashFor('search', { q: '"' + k + '"' })}">${esc(k)}</a>`).join('')}</div>` : ''}
        ${rel.length ? `<h2>Related articles</h2><div class="cards">${rel.map(b => card(b)).join('')}</div>` : ''}
      </div>
      <aside>
        <div class="panel"><h4>Details</h4>
          <dl class="kv">
            <dt>Journal</dt><dd>${esc(j?.name)}</dd>
            ${a.v ? `<dt>Volume</dt><dd>${a.v}${a.i ? `, issue ${a.i}` : ''}</dd>` : ''}
            ${a.y ? `<dt>Year</dt><dd>${a.y}</dd>` : ''}
            <dt>Authors</dt><dd>${a.a.length ? a.a.map(esc).join('<br>') : '—'}</dd>
            <dt>Citations</dt><dd>${a.c != null ? `<b>${fmt(a.c)}</b>${a._pct != null ? `<div class="impact-meter" title="Citation percentile among ${Math.floor(a.y / 10) * 10}s articles"><i style="width:${a._pct}%"></i></div><small>${a._pct}th percentile for the ${Math.floor(a.y / 10) * 10}s${impactLabel(a) ? ' · ' + impactLabel(a) : ''}</small>` : ''}` : (a.rv ? 'Book review (citations belong to the reviewed book)' : '<span style="color:var(--ink-3)">Not tracked</span>')}</dd>
            <dt>Source</dt><dd><a href="${esc(a.u)}" target="_blank" rel="noopener" style="color:var(--accent);word-break:break-all">${esc(new URL(a.u).hostname)}</a></dd>
          </dl>
        </div>
        <div class="panel"><h4>Cite</h4>
          <div class="seg cite-tabs"><button class="on" data-cite="bb">Bluebook</button><button data-cite="bib">BibTeX</button></div>
          <div class="cite-box" id="cite-box">${bluebook(a)}</div>
          <button class="btn btn-ghost btn-sm" id="copy-cite">Copy citation</button>
        </div>
        ${moreBy.length ? `<div class="panel"><h4>More by ${esc(a.a[0])}</h4><ul class="mini-list">${moreBy.map(b => `<li><a class="t" href="${articleHref(b)}">${esc(b.t)}</a><div class="m">${esc(journalById[b.j]?.name)}${b.y ? ' · ' + b.y : ''}</div></li>`).join('')}</ul>
          <div style="margin-top:12px"><a class="link-arrow" href="${authorHref(a.a[0])}">All articles →</a></div></div>` : ''}
      </aside>
    </div></div>`;

    let mode = 'bb';
    app.querySelectorAll('[data-cite]').forEach(b => b.addEventListener('click', () => {
      mode = b.dataset.cite;
      app.querySelectorAll('[data-cite]').forEach(x => x.classList.toggle('on', x === b));
      const box = document.getElementById('cite-box');
      if (mode === 'bb') { box.innerHTML = bluebook(a); box.style.whiteSpace = ''; box.style.fontFamily = ''; }
      else { box.textContent = bibtex(a); box.style.whiteSpace = 'pre-wrap'; box.style.fontFamily = 'ui-monospace, Consolas, monospace'; box.style.fontSize = '12.5px'; }
    }));
    document.getElementById('copy-cite').addEventListener('click', () => {
      navigator.clipboard.writeText(mode === 'bb' ? plainCite(a) : bibtex(a)).then(() => toast('Citation copied'));
    });
    document.getElementById('save-article').addEventListener('click', e => { toggleSave(a.id); e.currentTarget.textContent = saved.has(a.id) ? '★ Saved' : '☆ Save to my list'; });
  }

  function viewAuthor(key, params) {
    const entry = authorIndex.get(decodeURIComponent(key));
    if (!entry) return viewNotFound();
    const items = entry.items.slice().sort((x, y) => (y.y || 0) - (x.y || 0));
    const page = Math.max(1, +params.get('page') || 1);
    const coauthors = new Map();
    const tcount = {};
    for (const a of items) {
      for (const n of a.a) if (normName(n) !== normName(entry.name)) coauthors.set(normName(n), (coauthors.get(normName(n)) || 0) + 1);
      for (const t of a.tp) tcount[t] = (tcount[t] || 0) + 1;
    }
    const years = items.map(a => a.y).filter(Boolean);
    const jset = [...new Set(items.map(a => a.j))];
    const topT = Object.entries(tcount).sort((x, y) => y[1] - x[1]).slice(0, 6);
    app.innerHTML = `<div class="fade-in"><div class="article">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><span>Authors</span></div>
        <div class="author-head"><div class="avatar">${esc(initials(entry.name))}</div>
          <div><h1 style="margin:0">${esc(entry.name)}</h1>
          <div class="publine" style="margin:4px 0 0">${items.length} article${items.length === 1 ? '' : 's'} in the index${years.length ? ` · ${Math.min(...years)}–${Math.max(...years)}` : ''}</div></div></div>
        <h2>Articles</h2>
        <div class="cards">${items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map(a => card(a)).join('')}</div>
        ${pager(items.length, page, 'author')}
      </div>
      <aside>
        ${topT.length ? `<div class="panel"><h4>Research areas</h4><div class="tags">${topT.map(([t, n]) => `<a class="tag" href="${hashFor('search', { topic: t, q: '"' + entry.name + '"' })}">${esc(topicById[t]?.name)} · ${n}</a>`).join('')}</div></div>` : ''}
        <div class="panel"><h4>Published in</h4><ul class="mini-list">${jset.map(j => `<li><a class="t" href="${hashFor('search', { j, q: '"' + entry.name + '"' })}">${esc(journalById[j]?.name)}</a><div class="m">${items.filter(a => a.j === j).length} article(s)</div></li>`).join('')}</ul></div>
        ${coauthors.size ? `<div class="panel"><h4>Co-authors</h4><ul class="mini-list">${[...coauthors.entries()].sort((x, y) => y[1] - x[1]).slice(0, 10).map(([k, n]) => `<li><a class="t" href="#/author/${encodeURIComponent(k)}">${esc(authorIndex.get(k)?.name || k)}</a><div class="m">${n} joint article(s)</div></li>`).join('')}</ul></div>` : ''}
      </aside>
    </div></div>`;
    bindPager(n => { location.hash = '#/author/' + key + '?page=' + n; });
  }

  function viewJournals() {
    const spec = journals.filter(j => j.specialist), gen = journals.filter(j => !j.specialist).sort((a, b) => b.count - a.count);
    const jc = j => `<a class="jcard" href="${hashFor('search', { j: j.id })}">
      <div class="abbr">${esc(ABBR[j.id] || '')}${j.specialist ? '<span class="badge">Con law</span>' : ''}</div>
      <h3>${esc(j.name)}</h3>
      <div class="foot"><span>${esc(j.host)}</span><b>${fmt(j.count)}</b></div></a>`;
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Journals</span></div>
        <h1>Journal directory</h1><p>${journals.length} law reviews currently indexed. Specialist journals contribute every article. General law reviews contribute only articles about constitutional law.</p></div>
      <section class="section" style="padding-top:28px">
        <div class="section-head"><div><h2 style="font-size:24px">Specialist constitutional law journals</h2></div></div>
        <div class="jgrid">${spec.map(jc).join('')}</div>
      </section>
      <section class="section" style="padding-top:36px">
        <div class="section-head"><div><h2 style="font-size:24px">General law reviews</h2></div></div>
        <div class="jgrid">${gen.map(jc).join('')}</div>
      </section>
    </div>`;
  }

  function viewSaved() {
    const items = [...saved].map(id => byId.get(id)).filter(Boolean);
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>My list</span></div>
        <h1>My list</h1><p>Articles you have saved. Your list is stored in this browser only.</p></div>
      <div class="layout" style="grid-template-columns:1fr">
        <div>
          ${items.length ? `<div class="toolbar"><div class="count"><b>${items.length}</b> saved article${items.length === 1 ? '' : 's'}</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btn-ghost btn-sm" id="exp-bb">Copy Bluebook list</button>
              <button class="btn btn-ghost btn-sm" id="exp-bib">Download BibTeX</button>
              <button class="btn btn-ghost btn-sm" id="clear-saved">Clear list</button>
            </div></div>
            <div class="cards">${items.map(a => card(a)).join('')}</div>`
          : `<div class="empty"><h3>Your list is empty</h3><p>Use the bookmark button on any article to save it here. You can export the list as Bluebook citations or BibTeX.</p><p style="margin-top:18px"><a class="btn btn-primary" href="#/search">Browse articles</a></p></div>`}
        </div>
      </div></div>`;
    if (!items.length) return;
    document.getElementById('exp-bb').addEventListener('click', () => navigator.clipboard.writeText(items.map(plainCite).join('\n\n')).then(() => toast('Citations copied')));
    document.getElementById('exp-bib').addEventListener('click', () => {
      const blob = new Blob([items.map(bibtex).join('\n\n')], { type: 'application/x-bibtex' });
      const u = URL.createObjectURL(blob); const l = document.createElement('a');
      l.href = u; l.download = 'conlaw-bibliography.bib'; l.click(); URL.revokeObjectURL(u);
    });
    document.getElementById('clear-saved').addEventListener('click', () => {
      if (!confirm('Remove all saved articles from your list?')) return;
      saved = new Set(); persistSaved(); viewSaved();
    });
  }

  function viewAbout() {
    app.innerHTML = `<div class="fade-in"><div class="prose">
      <div class="crumbs"><a href="#/">Home</a><span>/</span><span>About</span></div>
      <h1>About Lex Constitutio</h1>
      <p>Lex Constitutio is a topic-organized index of constitutional law scholarship, in the spirit of PhilPapers. It collects publicly available bibliographic metadata (titles, authors, abstracts, and subject keywords) from law review repositories. It keeps the articles about constitutional law and arranges them in a browsable taxonomy.</p>
      <h2>How articles are collected</h2>
      <p>Many journals publish through institutional repositories that expose an open <a href="https://www.openarchives.org/pmh/" target="_blank" rel="noopener">OAI-PMH</a> feed. A few others publish through public WordPress APIs. Articles from specialist journals (<em>Constitutional Commentary</em>, <em>Hastings Constitutional Law Quarterly</em>, the <em>William &amp; Mary Bill of Rights Journal</em>) are all included. From general law reviews, an article is included if:</p>
      <ul><li>the repository tags it with a constitutional law discipline, or</li><li>its title names a constitutional provision, doctrine, or institution, or</li><li>its abstract does so more than once.</li></ul>
      <h2>How topics are assigned</h2>
      <p>Each article is matched against the vocabulary of each subtopic. A match in the title counts most, then the subject keywords, then the abstract. An article receives up to four topics. The tagging is automatic, so expect some imperfect matches.</p>
      <h2>Coverage</h2>
      <table><thead><tr><th>Journal</th><th>Articles</th></tr></thead><tbody>
        ${journals.slice().sort((a, b) => b.count - a.count).map(j => `<tr><td>${esc(j.name)}</td><td>${fmt(j.count)}</td></tr>`).join('')}
      </tbody></table>
      <p>The <em>Harvard</em>, <em>Yale</em>, <em>Columbia</em>, <em>Virginia</em>, <em>California</em>, <em>Penn</em>, <em>Stanford</em>, and <em>Georgetown</em> law reviews block automated access to their own websites. Their articles are indexed from <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a> metadata instead, and link to the article through its DOI (usually JSTOR) or the journal's site. Coverage of Georgetown in OpenAlex is thin. Older volumes may lack abstracts. Index last rebuilt ${esc(DATA.generated)}.</p>
      <h2>Citations and impact</h2>
      <p>Citation counts come from OpenAlex and are available for ${fmt(citedCount)} articles. The percentile compares an article with others in the index published in the same decade. OpenAlex sometimes credits a reviewed book's citations to its review. Titles that appear in more than one journal are treated as book reviews and left unranked. Law review citation data is less complete than in the sciences, so treat the counts as a rough guide.</p>
      <h2>Advanced doctrine</h2>
      <p>The advanced half of the Beginner's Guide is an original doctrinal treatment written for this site. It is organized after the chapter structure of Erwin Chemerinsky's <em>Constitutional Law: Principles and Policies</em> and covers judicial power, legislative and executive power, federalism, state action, due process, economic liberties, equal protection, fundamental rights, speech and religion. Excerpts from opinions are public-domain text extracted from the official <em>United States Reports</em> (Library of Congress) and supremecourt.gov slip opinions, or from Wikisource transcriptions. The open casebooks at opencasebook.org (H2O, CC BY-NC-SA) are cited as further reading.</p>
      <p>The in-depth commentary in each section comes from the <em>Constitution of the United States of America: Analysis and Interpretation</em> ("Constitution Annotated"), prepared by the Congressional Research Service of the Library of Congress. The site uses the 2022 GPO edition, a public-domain U.S. government work. Essays are extracted from the official PDFs on GovInfo with their footnotes omitted.</p>
      <h2>Originalist's Corner</h2>
      <p>The Corner indexes the full texts of Blackstone's <em>Commentaries</em>, St. George Tucker's annotated Blackstone, Joseph Story's <em>Commentaries on the Constitution</em>, James Kent's <em>Commentaries</em>, Vattel's <em>Law of Nations</em> and Locke's <em>Two Treatises</em> (via the Lonang Institute). It also covers <em>The Federalist</em> (Project Gutenberg), Madison's Notes of the Convention debates and founding documents (the Avalon Project at Yale Law School), and the acts of the first five Congresses (<em>Statutes at Large</em>, vol. 1, via Wikisource). Passages are matched to topics automatically and should be read in context. The full texts of <em>The Federalist</em>, the founding documents and the statutes can be read in the site's library.</p>
      <h2>Supreme Court, lectures and guide</h2>
      <p>Case summaries, oral argument audio and synchronized transcripts are loaded from <a href="https://www.oyez.org" target="_blank" rel="noopener">Oyez</a> (CC BY-NC). Opinion PDFs link to supremecourt.gov for recent terms and to the Library of Congress's <em>United States Reports</em> collection for older ones. Lecture and explainer videos are embedded from the YouTube channels of the institutions that published them. Guide overviews are drawn from Wikipedia (CC BY-SA 4.0), with links to Cornell LII's Wex.</p>
    </div></div>`;
  }

  /* ------------------------------------------------------------ lazy data */
  const loading = {};
  function loadData(name, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    if (!loading[name]) loading[name] = new Promise((res, rej) => {
      const s = document.createElement('script'); s.src = `data/${name}.js`;
      s.onload = () => res(window[globalName]); s.onerror = () => { delete loading[name]; rej(new Error(`Couldn't load data/${name}.js`)); };
      document.body.appendChild(s);
    });
    return loading[name];
  }
  let routeToken = 0;
  function withData(specs, fn) {
    const token = routeToken;
    if (!specs.every(([, g]) => window[g])) app.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading…</p></div>';
    Promise.all(specs.map(([n, g]) => loadData(n, g)))
      .then(ds => { if (token === routeToken) fn(...ds); })
      .catch(e => {
        app.innerHTML = `<div class="prose"><h1>Couldn't load this section</h1><p>${esc(e.message)}. This is usually a temporary network or hosting hiccup.</p><p><button class="btn btn-primary" id="retry-load">Try again</button></p></div>`;
        document.getElementById('retry-load').addEventListener('click', route);
      });
  }
  // Oyez returns HTML; parse it inertly (no scripts, no image loads) and keep only paragraph text
  function htmlParas(html) {
    if (!html) return '';
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const ps = [...doc.querySelectorAll('p')].map(p => p.textContent.trim()).filter(Boolean);
    return (ps.length ? ps : [doc.body.textContent.trim()]).map(t => `<p>${esc(t)}</p>`).join('');
  }
  const fmtDate = iso => iso ? new Date(iso + 'T12:00:00Z').toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) : '';
  const fmtTime = s => { s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
  function topicOptions(selected) {
    return `<option value="">All topics</option>` + parents.map(p => `<optgroup label="${esc(p.name)}"><option value="${p.id}" ${selected === p.id ? 'selected' : ''}>All of ${esc(p.name)}</option>${childrenOf(p.id).map(c => `<option value="${c.id}" ${selected === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</optgroup>`).join('');
  }
  function topicSet(id) {
    if (!id) return null;
    return new Set(topicById[id]?.parent ? [id] : [id, ...childrenOf(id).map(c => c.id)]);
  }

  /* ------------------------------------------------------------ impact (a view within Articles) */
  function articleTabs(active, topic) {
    return `<div class="subtabs">
      <a href="${hashFor('search', topic ? { topic } : {})}" class="${active === 'all' ? 'on' : ''}">All articles</a>
      <a href="${hashFor('impact', topic ? { topic } : {})}" class="${active === 'impact' ? 'on' : ''}">Most influential</a>
      <a href="#/topics" class="${active === 'topics' ? 'on' : ''}">Topics</a>
    </div>`;
  }
  function viewImpact(params) {
    const topic = params.get('topic') || '', dec = +params.get('dec') || 0, j = params.get('j') || '';
    const page = Math.max(1, +params.get('page') || 1);
    const tset = topicSet(topic);
    const list = articles.filter(a => a.c != null && (!dec || Math.floor((a.y || 0) / 10) * 10 === dec) && (!j || a.j === j) && (!tset || a.tp.some(t => tset.has(t))))
      .sort((x, y) => y.c - x.c);
    const max = list[0]?.c || 1;
    const authorTotals = new Map();
    for (const a of list) for (const n of a.a) { const k = normName(n); const e = authorTotals.get(k) || { name: n, c: 0, n: 0 }; e.c += a.c; e.n++; authorTotals.set(k, e); }
    const topAuthors = [...authorTotals.values()].sort((x, y) => y.c - x.c).slice(0, 12);
    const decades = Object.keys(byDecade).map(Number).filter(d => d >= 1900).sort((a, b) => b - a);
    const go = patch => { location.hash = hashFor('impact', Object.assign({ topic, dec, j }, { page: 1 }, patch)); };
    const slice = list.slice((page - 1) * 25, page * 25);
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/search">Articles</a><span>/</span><span>Most influential</span></div>
        <h1>Most influential articles</h1>
        <p>Ranked by citations recorded in <a href="https://openalex.org" target="_blank" rel="noopener" style="color:var(--accent)">OpenAlex</a>, an open index of scholarly literature. ${fmt(citedCount)} of ${fmt(articles.length)} articles have citation data. The percentile badge compares an article with others from the same decade, so older work doesn't automatically dominate. Book reviews are excluded: OpenAlex often credits a review with the reviewed book's citations. Book impact is ranked separately on the <a href="${hashFor('books', { sort: 'cited' })}" style="color:var(--accent)">Books</a> tab.</p>${articleTabs('impact')}</div>
      <div class="layout">
        <aside class="sidebar">
          <div class="side-block"><h4>Topic</h4><select class="select" id="imp-topic">${topicOptions(topic)}</select></div>
          <div class="side-block"><h4>Decade</h4><div class="suggest" style="margin:0"><button class="chip ${!dec ? 'on' : ''}" data-dec="0">All time</button>${decades.map(d => `<button class="chip ${dec === d ? 'on' : ''}" data-dec="${d}">${d}s</button>`).join('')}</div></div>
          <div class="side-block"><h4>Journal</h4><select class="select" id="imp-j"><option value="">All journals</option>${journals.filter(x => articles.some(a => a.j === x.id && a.c != null)).map(x => `<option value="${x.id}" ${j === x.id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></div>
          <div class="side-block"><h4>Most cited authors</h4><ul class="mini-list">${topAuthors.map(x => `<li><a class="t" href="${authorHref(x.name)}">${esc(x.name)}</a><div class="m">${fmt(x.c)} citations · ${x.n} article${x.n === 1 ? '' : 's'}</div></li>`).join('') || '<li class="m">No data</li>'}</ul></div>
        </aside>
        <div>
          <div class="toolbar"><div class="count"><b>${fmt(list.length)}</b> ranked articles</div></div>
          ${slice.length ? `<ol class="rank">${slice.map((a, i) => `<li>
            <span class="rank-n">${(page - 1) * 25 + i + 1}</span>
            <div class="rank-body">
              <a class="rank-t" href="${articleHref(a)}">${esc(a.t)}</a>
              <div class="rank-m">${a.a.length ? a.a.slice(0, 3).map(n => `<a href="${authorHref(n)}">${esc(n)}</a>`).join(', ') + (a.a.length > 3 ? ' et al.' : '') + ' · ' : ''}${esc(journalById[a.j]?.name)}${a.y ? ' · ' + a.y : ''}</div>
              <div class="rank-bar"><i style="width:${Math.max(1, 100 * a.c / max)}%"></i></div>
            </div>
            <div class="rank-c"><b>${fmt(a.c)}</b><span>${impactLabel(a) || (a._pct != null ? a._pct + 'th pct' : '')}</span></div>
          </li>`).join('')}</ol>` : '<div class="empty"><h3>No ranked articles</h3><p>Try a different filter.</p></div>'}
          ${pager(list.length, page, 'impact', 25)}
        </div>
      </div></div>`;
    document.getElementById('imp-topic').addEventListener('change', e => go({ topic: e.target.value }));
    document.getElementById('imp-j').addEventListener('change', e => go({ j: e.target.value }));
    app.querySelectorAll('[data-dec]').forEach(b => b.addEventListener('click', () => go({ dec: +b.dataset.dec })));
    bindPager(n => { location.hash = hashFor('impact', { topic, dec, j, page: n }); });
  }

  /* ------------------------------------------------------------ supreme court */
  const ERAS = [
    { id: 'roberts', name: 'Roberts Court', from: 2005, to: 9999 },
    { id: 'rehnquist', name: 'Rehnquist Court', from: 1986, to: 2005 },
    { id: 'burger', name: 'Burger Court', from: 1969, to: 1986 },
    { id: 'warren', name: 'Warren Court', from: 1953, to: 1969 },
    { id: 'early', name: 'Before 1953', from: 0, to: 1953 }
  ];
  let caseById = null;
  function viewScotus(params) { withData([['scotus', 'SCOTUS']], S => renderScotus(S, params)); }
  function renderScotus(S, params) {
    const st = { q: params.get('q') || '', tag: params.get('tag') || '', era: params.get('era') || '', audio: params.get('audio') === '1', con: params.get('con') === '1', page: Math.max(1, +params.get('page') || 1) };
    const pq = parseQuery(st.q);
    const era = ERAS.find(e => e.id === st.era);
    const filt = (skipTag) => S.cases.filter(c => {
      if (era && !(c.y >= era.from && c.y < era.to)) return false;
      if (st.audio && !c.arg) return false;
      if (st.con && !c.con) return false;
      if (!skipTag && st.tag && !(c.tg || []).includes(st.tag)) return false;
      if (pq.terms.length || pq.phrases.length) {
        const hay = (c.n + ' ' + (c.q || '') + ' ' + (c.ds || '') + ' ' + (c.h || '') + ' ' + (c.d || '') + ' ' + (c.cit || '')).toLowerCase();
        if (!pq.terms.every(t => hay.includes(t)) || !pq.phrases.every(p => hay.includes(p))) return false;
      }
      return true;
    });
    const list = filt(false);
    const tagCounts = {}; for (const c of filt(true)) for (const t of c.tg || []) tagCounts[t] = (tagCounts[t] || 0) + 1;
    const page = Math.min(st.page, Math.max(1, Math.ceil(list.length / PAGE_SIZE)));
    const slice = list.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const go = patch => { const s = Object.assign({}, st, { page: 1 }, patch); location.hash = hashFor('scotus', { q: s.q, tag: s.tag, era: s.era, audio: s.audio ? 1 : '', con: s.con ? 1 : '', page: s.page > 1 ? s.page : '' }); };
    const tagName = t => topicById[t]?.name || t;
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Supreme Court</span></div>
        <h1>Supreme Court decisions</h1>
        <p>${fmt(S.cases.length)} cases with summaries, opinion PDFs, and oral argument audio you can play here, with a transcript that follows along. Summaries and audio come from <a href="https://www.oyez.org" target="_blank" rel="noopener" style="color:var(--accent)">Oyez</a>. Opinions come from supremecourt.gov and the Library of Congress.</p>${scotusTabs('decided')}</div>
      <div class="layout">
        <aside class="sidebar" id="sidebar">
          <div class="side-block"><h4>Search cases</h4><form id="sc-form"><input class="input" id="sc-q" type="search" value="${esc(st.q)}" placeholder="Case name, issue, docket…"></form></div>
          <div class="side-block"><h4>Show</h4>
            <label class="check"><input type="checkbox" id="sc-audio" ${st.audio ? 'checked' : ''}> Argued cases (audio)</label>
            <label class="check"><input type="checkbox" id="sc-con" ${st.con ? 'checked' : ''}> Constitutional questions</label>
          </div>
          <div class="side-block"><h4>Court</h4><ul class="tree">
            <li><a href="#" data-era="" class="${!st.era ? 'on' : ''}"><span>All eras</span></a></li>
            ${ERAS.map(e => `<li><a href="#" data-era="${e.id}" class="${st.era === e.id ? 'on' : ''}"><span>${e.name}</span><span class="n">${e.to === 9999 ? e.from + '–' : e.from ? e.from + '–' + e.to : ''}</span></a></li>`).join('')}
          </ul></div>
          <div class="side-block"><h4>Area</h4><ul class="tree">
            <li><a href="#" data-tag="" class="${!st.tag ? 'on' : ''}"><span>All areas</span></a></li>
            ${Object.entries(tagCounts).sort((a, b) => b[1] - a[1]).map(([t, n]) => `<li><a href="#" data-tag="${t}" class="${st.tag === t ? 'on' : ''}"><span>${esc(tagName(t))}</span><span class="n">${fmt(n)}</span></a></li>`).join('')}
          </ul></div>
        </aside>
        <div>
          <div class="toolbar"><div class="count"><button class="btn btn-ghost btn-sm filter-toggle" id="filter-toggle">Filters</button> <b>${fmt(list.length)}</b> case${list.length === 1 ? '' : 's'}</div></div>
          ${slice.length ? `<div class="cards">${slice.map(caseCard).join('')}</div>` : '<div class="empty"><h3>No cases found</h3><p>Try fewer keywords or another era.</p></div>'}
          ${pager(list.length, page, 'scotus')}
        </div>
      </div></div>`;
    document.getElementById('sc-form').addEventListener('submit', e => { e.preventDefault(); go({ q: document.getElementById('sc-q').value.trim() }); });
    document.getElementById('sc-audio').addEventListener('change', e => go({ audio: e.target.checked }));
    document.getElementById('sc-con').addEventListener('change', e => go({ con: e.target.checked }));
    app.querySelectorAll('[data-era]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); go({ era: a.dataset.era }); }));
    app.querySelectorAll('[data-tag]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); go({ tag: a.dataset.tag }); }));
    document.getElementById('filter-toggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
    bindPager(n => go({ page: n }));
  }
  function caseCard(c) {
    const summary = c.ds || c.h || c.q || '';
    return `<article class="card case-card">
      <div class="card-meta">${c.cit ? `<span class="jn">${esc(c.cit)}</span>` : ''}${c.dec ? `<span>Decided ${esc(fmtDate(c.dec))}</span>` : `<span>Term ${esc(c.t)}</span>`}${c.d ? `<span>No. ${esc(c.d)}</span>` : ''}</div>
      <h3><a href="#/case/${esc(c.id)}">${esc(c.n)}</a></h3>
      ${summary ? `<p class="abs">${esc(summary)}</p>` : ''}
      <div class="tags">${c.arg ? '<span class="tag tag-audio">▶ Argument audio</span>' : ''}${c.pdf ? '<span class="tag">Opinion PDF</span>' : ''}${c.tr ? '<span class="tag">Transcript PDF</span>' : ''}${(c.tg || []).slice(0, 3).map(t => `<a class="tag" href="${hashFor('scotus', { tag: t })}">${esc(topicById[t]?.name || t)}</a>`).join('')}</div>
    </article>`;
  }
  /* ---- current docket */
  function scotusTabs(active) {
    return `<div class="subtabs"><a href="#/docket" class="${active === 'docket' ? 'on' : ''}">Current docket</a><a href="#/scotus" class="${active === 'decided' ? 'on' : ''}">Decided cases</a></div>`;
  }
  const todayIso = () => new Date().toISOString().slice(0, 10);
  function docketStatus(e) {
    if (e.argued) return { k: 'argued', label: `Argued ${fmtDate(e.argued)} · awaiting decision` };
    if (e.sched) return { k: 'scheduled', label: `Argument scheduled ${fmtDate(e.sched)}` };
    if (e.granted) return { k: 'granted', label: `Granted ${fmtDate(e.granted)} · argument not yet scheduled` };
    return { k: 'pending', label: 'Pending' };
  }
  const BRIEF_LABEL = { petitioner: "Petitioner's merits brief", respondent: "Respondent's merits brief", 'united-states': 'Brief of the United States', reply: 'Reply brief', appendix: 'Joint appendix', petition: 'Petition for certiorari', opposition: 'Brief in opposition' };
  function viewDocket(params) { withData([['docket', 'DOCKET']], K => renderDocket(K, params)); }
  function renderDocket(K, params) {
    const f = params.get('f') || '';
    const today = todayIso();
    const isUp = e => !e.argued && e.sched && e.sched >= today;
    const filters = [['', 'All pending', () => true], ['argued', 'Argued, awaiting decision', e => !!e.argued], ['upcoming', 'Upcoming arguments', isUp], ['granted', 'Granted, not yet scheduled', e => !e.argued && !e.sched]];
    const [, , pred] = filters.find(x => x[0] === f) || filters[0];
    const list = K.cases.filter(pred);
    const byDk = new Map(K.cases.map(e => [e.d, e]));
    const nextDay = K.sittings.flatMap(s => s.days).map(d => d.date).filter(d => d >= today).sort()[0];
    const dayFmt = iso => { const d = new Date(iso + 'T12:00:00Z'); return { wd: d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }), md: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) }; };
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a><span>/</span><span>Current docket</span></div>
        <h1>The current docket</h1>
        <p>October Term ${K.term}: ${K.cases.length} cases awaiting decision, with the questions presented, the briefs, and argument audio and transcripts once a case has been argued. Updated ${esc(fmtDate(K.updated))} from supremecourt.gov and Oyez.</p>${scotusTabs('docket')}</div>
      <section class="section" style="padding-top:26px">
        <div class="section-head"><div><h2 style="font-size:26px">Argument calendar</h2><p>The Court's published sittings for the Term. ${nextDay ? `Next argument day: <b>${esc(fmtDate(nextDay))}</b>.` : ''}</p></div></div>
        <div class="cal">${K.sittings.map(s => `<div class="cal-sitting">
          <div class="cal-h">${esc(s.label)} sitting</div>
          <div class="cal-days">${s.days.map(d => { const df = dayFmt(d.date); const cls = d.date < today ? 'past' : d.date === nextDay ? 'next' : ''; return `<div class="cal-day ${cls}">
            <div class="cal-date"><span>${df.wd}</span><b>${df.md}</b>${cls === 'next' ? '<em>Next</em>' : ''}</div>
            <ul>${d.cases.map(dk => { const e = byDk.get(dk); return `<li>${e ? `<a href="#/case/${esc(e.id)}">${esc(e.n)}</a>` : esc(dk)}<span>No. ${esc(dk)}</span></li>`; }).join('')}</ul>
          </div>`; }).join('')}</div>
        </div>`).join('') || '<div class="empty"><h3>No calendar published yet</h3></div>'}</div>
      </section>
      <section class="section" style="padding-top:36px">
        <div class="section-head"><div><h2 style="font-size:26px">Cases</h2></div></div>
        <div class="suggest" style="margin:0 0 18px">${filters.map(([k, label, p]) => `<a class="chip ${f === k ? 'on' : ''}" href="${hashFor('docket', { f: k })}">${label} · ${K.cases.filter(p).length}</a>`).join('')}</div>
        <div class="cards">${list.map(e => { const st = docketStatus(e); const merits = e.briefs.filter(b => ['petitioner', 'respondent', 'united-states', 'reply'].includes(b.k)).length; return `<article class="card case-card">
          <div class="card-meta"><span class="status status-${st.k}">${esc(st.label)}</span><span>No. ${esc(e.d)}</span>${e.lower ? `<span>${esc(e.lower)}</span>` : ''}</div>
          <h3><a href="#/case/${esc(e.id)}">${esc(e.n)}</a></h3>
          ${e.q || e.ds ? `<p class="abs">${esc(e.q || e.ds)}</p>` : ''}
          <div class="tags">${e.argued ? '<span class="tag tag-audio">▶ Argument audio</span>' : ''}${e.qp ? '<span class="tag">Questions presented</span>' : ''}${merits ? `<span class="tag">${merits} merits brief${merits === 1 ? '' : 's'}</span>` : ''}${e.amici.length ? `<span class="tag">${e.amici.length} amicus brief${e.amici.length === 1 ? '' : 's'}</span>` : ''}</div>
        </article>`; }).join('') || '<div class="empty"><h3>No cases in this group</h3></div>'}</div>
      </section>
    </div>`;
  }

  /* ---- precedents: cases named in the Oyez summary, Oyez's related cases, and textual similarity */
  let simIndex = null;
  const SIM_STOP = new Set('whether under does that this with from have which court state states united federal case cases their there were been when what into than only also more such other made because after before against would could should them they same within upon held holds holding question questions decided decide district appeals circuit petitioner respondent petitioners respondents government statute section claim claims rule ruled reversed affirmed lower federal'.split(' '));
  const simTokens = c => new Set(((c.q || '') + ' ' + (c.ds || '') + ' ' + (c.h || '')).toLowerCase().match(/[a-z][a-z-]{3,}/g)?.filter(w => !SIM_STOP.has(w)) || []);
  function similarCases(S, c, n = 6) {
    if (!simIndex) {
      const docs = S.cases.map(simTokens), df = new Map();
      docs.forEach(s => s.forEach(w => df.set(w, (df.get(w) || 0) + 1)));
      simIndex = { docs, df, N: docs.length };
    }
    const toks = simTokens(c), tg = new Set(c.tg || guessTags((c.q || '') + ' ' + (c.ds || '')));
    if (!toks.size) return [];
    const { docs, df, N } = simIndex;
    const scored = [];
    S.cases.forEach((x, i) => {
      if (x.id === c.id || !x.dec) return;
      let s = 0; for (const w of docs[i]) if (toks.has(w)) s += Math.log(N / (df.get(w) + 1));
      if (!s) return;
      s = s / Math.sqrt(docs[i].size + 8);
      const shared = (x.tg || []).filter(t => tg.has(t)).length;
      s += 0.6 * shared;
      if (tg.size && x.tg && x.tg.length && !shared) s *= 0.5;   // different area of law
      if (x.con) s += 0.3;
      scored.push([s, x]);
    });
    return scored.sort((a, b) => b[0] - a[0]).slice(0, n).map(x => x[1]);
  }
  // same area tags as the build step (scripts/build_extras.pl), for cases not yet decided
  const CASE_TAGS = [
    ['speech', /first amendment|free speech|freedom of speech|freedom of the press|expressive|speech/i], ['religion', /establishment clause|free exercise|religio/i],
    ['guns', /second amendment|firearm|bear arms|\bguns?\b/i], ['equality', /equal protection|discriminat|\brace\b|racial|segregat|affirmative action|sex-based|gender/i],
    ['dueprocess', /due process|privacy|abortion|marriage|liberty interest|parental/i], ['crimpro', /fourth amendment|fifth amendment|sixth amendment|eighth amendment|\bsearch|seizure|miranda|counsel|\bjury\b|cruel and unusual|death penalty|self-incrimination|confrontation|double jeopardy/i],
    ['federalism', /tenth amendment|sovereign immunity|eleventh amendment|commerce clause|preempt|federalism|state sovereignty/i], ['seppowers', /separation of powers|appointments clause|removal|executive power|president|nondelegation|delegat/i],
    ['admin', /\bagency|administrative|chevron|regulation/i], ['article3', /standing|article iii|jurisdiction|\bmoot|justiciab/i], ['voting', /voting|election|ballot|redistricting|gerrymander|apportion|campaign/i],
    ['takings', /taking|just compensation|eminent domain/i], ['citizenship', /immigra|citizenship|deport|\balien|asylum|tribal|\bindian/i], ['security', /war powers|military|detain|guantanamo|national security|habeas/i]];
  const guessTags = text => CASE_TAGS.filter(([, rx]) => rx.test(text)).map(([t]) => t);
  let caseByShort = null;
  function citedCases(S, text, selfId) {
    if (!caseByShort) {
      caseByShort = new Map();
      for (const x of S.cases) {
        const m = x.n.match(/^(?:The )?([A-Z][\w'.&-]*)[^v]*? v\. (?:The )?([A-Z][\w'.&-]*)/);
        if (!m) continue;
        const k = (m[1] + '|' + m[2]).toLowerCase();
        const prev = caseByShort.get(k);
        if (!prev || (!prev.con && x.con) || (!prev.dec && x.dec)) caseByShort.set(k, x);
      }
    }
    const out = new Map();
    for (const m of text.matchAll(/(?:^|[^A-Za-z])([A-Z][\w'.&-]*)(?: [A-Z][\w'.&-]*){0,4} v\. (?:The )?([A-Z][\w'.&-]*)/g)) {
      const x = caseByShort.get((m[1] + '|' + m[2]).toLowerCase());
      if (x && x.id !== selfId) out.set(x.id, x);
    }
    return [...out.values()];
  }
  function precedentItem(x) {
    return `<li><a class="t" href="#/case/${esc(x.id)}">${esc(x.n)}</a><div class="m">${x.cit ? esc(x.cit) + ' · ' : ''}${x.y || x.t || ''}</div></li>`;
  }

  function viewCase(id) { withData([['scotus', 'SCOTUS'], ['docket', 'DOCKET']], (S, K) => renderCase(S, id, K)); }
  function renderCase(S, id, K) {
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const dk = (K && K.cases.find(e => e.id === id || id.endsWith('/' + e.d))) || null;
    let c = caseById.get(id);
    if (!c && dk) c = { id: dk.id, n: dk.n, t: dk.t, d: dk.d, q: dk.q, ds: dk.ds, pending: true };
    if (!c) return viewNotFound();
    const pend = dk && !c.dec ? dk : null;
    const caseName = c.n.toLowerCase().replace(/\s*\(\d\)$/, '');
    const relatedArticles = caseName.length < 10 ? [] : articles.filter(a => a._t.includes(caseName) || a._ab.includes(caseName))
      .sort((x, y) => (y.c ?? -1) - (x.c ?? -1)).slice(0, 6);
    app.innerHTML = `<div class="fade-in"><div class="article">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a>${pend ? '<span>/</span><a href="#/docket">Current docket</a>' : c.y ? `<span>/</span><a href="${hashFor('scotus', { era: (ERAS.find(e => c.y >= e.from && c.y < e.to) || {}).id })}">${c.y}</a>` : ''}</div>
        <h1>${esc(c.n)}</h1>
        <div class="publine">${c.cit ? esc(c.cit) + ' · ' : ''}${c.dec ? 'Decided ' + esc(fmtDate(c.dec)) : 'October Term ' + esc(c.t)}${c.d ? ' · No. ' + esc(c.d) : ''}${pend && pend.lower ? ' · from the ' + esc(pend.lower) : ''}</div>
        ${pend ? `<div class="pending-banner status-${docketStatus(pend).k}"><b>Pending</b><span>${esc(docketStatus(pend).label)}</span></div>` : ''}
        ${c.ds ? `<div class="abstract plain">${esc(c.ds)}</div>` : ''}
        ${pend ? `<h2>Briefs & filings</h2>
          <div class="briefs">
            ${pend.qp ? `<a class="brief brief-qp" href="${esc(pend.qp)}" target="_blank" rel="noopener"><b>Questions presented</b><span>The legal questions the Court agreed to decide</span><em>PDF ↗</em></a>` : ''}
            ${(() => {
              // merits briefs (after cert was granted) first, in filing order; then the cert-stage filings
              const g = pend.granted || '';
              const certStage = b => ['petition', 'opposition'].includes(b.k) || (b.k === 'reply' && g && b.date && b.date < g);
              const ORDER = { petitioner: 1, appendix: 2, 'united-states': 3, respondent: 4, reply: 5 };
              const merits = pend.briefs.filter(b => !certStage(b)).sort((a, b) => (a.date || '').localeCompare(b.date || '') || (ORDER[a.k] || 9) - (ORDER[b.k] || 9));
              const cert = pend.briefs.filter(certStage);
              const tile = (b, label) => `<a class="brief" href="${esc(b.url)}" target="_blank" rel="noopener"><b>${esc(label || BRIEF_LABEL[b.k] || b.k)}</b><span>${esc(b.label)}</span><em>${b.date ? esc(fmtDate(b.date)) + ' · ' : ''}PDF ↗</em></a>`;
              return merits.map(b => tile(b)).join('') + (cert.length ? `</div><div class="brief-sub">Certiorari stage</div><div class="briefs">${cert.map(b => tile(b, b.k === 'reply' ? 'Reply to brief in opposition' : null)).join('')}` : '');
            })()}
          </div>
          ${pend.amici.length ? `<details class="amici"><summary>${pend.amici.length} amicus brief${pend.amici.length === 1 ? '' : 's'}</summary><ul>${pend.amici.map(a => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.who)}</a>${a.side ? ` <span>supporting ${esc(a.side)}</span>` : ''}${a.date ? ` <em>${esc(fmtDate(a.date))}</em>` : ''}</li>`).join('')}</ul></details>` : ''}
          <p class="attrib">Filings from the <a href="${esc(pend.docket)}" target="_blank" rel="noopener" style="color:var(--accent)">Supreme Court docket for No. ${esc(pend.d)}</a>.</p>` : ''}
        <div class="actions">
          ${c.pdf ? `<a class="btn btn-primary" href="${esc(c.pdf)}" target="_blank" rel="noopener">Opinion PDF ↗</a>` : ''}
          ${c.tr ? `<a class="btn btn-ghost" href="${esc(c.tr)}" target="_blank" rel="noopener">Argument transcript PDF ↗</a>` : ''}
          ${!c.tr && pend && pend.tr ? `<a class="btn btn-primary" href="${esc(pend.tr)}" target="_blank" rel="noopener">Argument transcript PDF ↗</a>` : ''}
          ${pend ? `<a class="btn btn-ghost" href="${esc(pend.docket)}" target="_blank" rel="noopener">Docket ↗</a>` : ''}
          ${c.ju ? `<a class="btn btn-ghost" href="${esc(c.ju)}" target="_blank" rel="noopener">Full text on Justia ↗</a>` : ''}
          <a class="btn btn-ghost" href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Oyez ↗</a>
        </div>
        ${c.h ? `<h2>Holding <small>(supremecourt.gov)</small></h2><div class="callout">${esc(c.h)}</div>` : ''}
        <div id="case-live"><h2>Case summary</h2><p class="muted-line"><span class="spinner sm"></span> Loading facts, question and conclusion from Oyez…</p></div>
        <div id="case-audio"></div>
        ${relatedArticles.length ? `<h2>Law review articles discussing this case</h2><div class="cards">${relatedArticles.map(a => card(a)).join('')}</div>` : ''}
      </div>
      <aside>
        <div class="panel"><h4>Details</h4><dl class="kv">
          ${c.cit ? `<dt>Citation</dt><dd>${esc(c.cit)}</dd>` : ''}
          <dt>Term</dt><dd>${esc(c.t)}</dd>
          ${c.d ? `<dt>Docket</dt><dd>${esc(c.d)}</dd>` : ''}
          ${c.dec ? `<dt>Decided</dt><dd>${esc(fmtDate(c.dec))}</dd>` : ''}
          <dt>Areas</dt><dd>${(c.tg || []).map(t => `<a class="tag" href="${hashFor('scotus', { tag: t })}">${esc(topicById[t]?.name || t)}</a>`).join(' ') || '—'}</dd>
        </dl><div id="case-vote"></div></div>
        <div class="panel" id="case-opinions" hidden><h4>Opinions</h4><ul class="mini-list"></ul></div>
        <div class="panel"><h4>Find articles</h4><a class="link-arrow" href="${hashFor('search', { q: '"' + c.n.replace(/\s*\(\d\)$/, '') + '"' })}">Search the index for this case →</a></div>
        <div class="panel" id="case-precedents"><h4>Precedents</h4>
          <div id="prec-cited"></div>
          ${(() => { const sim = similarCases(S, c); return sim.length ? `<div class="prec-group"><div class="prec-h">Related decisions</div><ul class="mini-list">${sim.map(precedentItem).join('')}</ul></div>` : '<p class="muted-line" style="font-size:13px">No closely related decisions found.</p>'; })()}
        </div>
      </aside>
    </div></div>`;

    const token = routeToken;
    fetch(`https://api.oyez.org/cases/${c.id}`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(d => {
      if (token !== routeToken) return;
      const live = document.getElementById('case-live');
      live.innerHTML = [
        d.facts_of_the_case ? `<h2>Facts of the case</h2><div class="prose-sm">${htmlParas(d.facts_of_the_case)}</div>` : '',
        d.question ? `<h2>Question</h2><div class="prose-sm">${htmlParas(d.question)}</div>` : '',
        d.conclusion ? `<h2>Conclusion</h2><div class="prose-sm">${htmlParas(d.conclusion)}</div>` : ''
      ].join('') || '<p class="muted-line">Oyez has no written summary for this case.</p>';
      live.insertAdjacentHTML('beforeend', '<p class="attrib">Summary text © Oyez (oyez.org), used under CC BY-NC.</p>');
      // precedents named in Oyez's summary, plus Oyez's own related-case links
      const plain = [d.facts_of_the_case, d.question, d.conclusion].map(h => h ? new DOMParser().parseFromString(h, 'text/html').body.textContent : '').join(' ');
      const cited = citedCases(S, plain, c.id);
      for (const r of d.related_cases || []) { const rid = ((r && r.href) || '').match(/\/cases\/(.+)$/); const x = rid && caseById.get(rid[1]); if (x && x.id !== c.id && !cited.includes(x)) cited.push(x); }
      if (cited.length) document.getElementById('prec-cited').innerHTML = `<div class="prec-group"><div class="prec-h">Discussed in this case</div><ul class="mini-list">${cited.slice(0, 8).map(precedentItem).join('')}</ul></div>`;
      const dec = (d.decisions || [])[0];
      if (dec && dec.majority_vote != null) document.getElementById('case-vote').innerHTML = `<div class="vote"><b>${dec.majority_vote}–${dec.minority_vote}</b><span>${dec.winning_party ? 'for ' + esc(dec.winning_party) : 'decision'}</span></div>`;
      const ops = (d.written_opinion || []).filter(o => o && o.type);
      if (ops.length) {
        const p = document.getElementById('case-opinions'); p.hidden = false;
        p.querySelector('ul').innerHTML = ops.map(o => `<li><a class="t" href="${esc(o.justia_opinion_url || c.ju || '#')}" target="_blank" rel="noopener">${esc(o.type.label)}</a><div class="m">${esc(o.judge_full_name || 'Per curiam')}</div></li>`).join('');
      }
      const media = [...(d.oral_argument_audio || []).map(m => ({ ...m, kind: 'Oral argument' })), ...(d.opinion_announcement || []).map(m => ({ ...m, kind: 'Opinion announcement' }))].filter(m => m && m.href && !m.unavailable);
      if (media.length) mountAudio(document.getElementById('case-audio'), media, c);
      else courtAudioFallback();
    }).catch(() => {
      if (token !== routeToken) return;
      document.getElementById('case-live').innerHTML = `${c.q ? `<h2>Question</h2><div class="prose-sm"><p>${esc(c.q)}</p></div>` : ''}<p class="muted-line">${pend ? 'Oyez has not published a summary of this case yet.' : 'Live details from Oyez are unavailable right now.'} <a href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Open on Oyez ↗</a></p>`;
      courtAudioFallback();
    });
    // the Court posts argument audio within days; Oyez's synced versions follow later
    function courtAudioFallback() {
      if (!pend || !pend.argued || pend.argued > todayIso()) return;
      mountAudio(document.getElementById('case-audio'), [{ kind: 'Oral argument', title: fmtDate(pend.argued) + ' (supremecourt.gov)', direct: `https://www.supremecourt.gov/media/audio/mp3files/${pend.d}.mp3`, trPdf: pend.tr }], c);
    }
  }
  function mountAudio(el, media, c) {
    el.innerHTML = `<h2>Listen</h2>
      <div class="player">
        <div class="player-tabs">${media.map((m, i) => `<button data-m="${i}" class="${i === 0 ? 'on' : ''}"><small>${esc(m.kind)}</small>${esc((m.title || '').replace(/^(Oral Argument|Opinion Announcement)\s*-\s*/i, ''))}</button>`).join('')}</div>
        <div id="player-body"></div>
      </div>`;
    const tabs = el.querySelectorAll('[data-m]');
    tabs.forEach(b => b.addEventListener('click', () => { tabs.forEach(x => x.classList.toggle('on', x === b)); loadMedia(media[+b.dataset.m]); }));
    loadMedia(media[0]);
    function loadMedia(m) {
      const body = document.getElementById('player-body');
      const old = body.querySelector('audio'); if (old) old.pause();
      body.innerHTML = '<p class="muted-line" style="padding:18px"><span class="spinner sm"></span> Loading audio and transcript…</p>';
      (m.direct ? Promise.resolve({ media_file: [{ mime: 'audio/mpeg', href: m.direct }] }) : fetch(m.href).then(r => r.json())).then(x => {
        const file = (x.media_file || []).find(f => f && f.mime === 'audio/mpeg') || (x.media_file || []).find(f => f && f.href);
        const turns = [];
        for (const sec of (x.transcript && x.transcript.sections) || []) for (const t of sec.turns || []) {
          const text = (t.text_blocks || []).map(b => b.text).join(' ') || t.text || '';
          if (!text) continue;
          turns.push({ s: t.start, e: t.stop, sp: t.speaker ? t.speaker.name : 'Unknown speaker', j: !!(t.speaker && t.speaker.roles && t.speaker.roles.length), tx: text });
        }
        if (!file) { body.innerHTML = '<p class="muted-line" style="padding:18px">Audio file unavailable.</p>'; return; }
        body.innerHTML = `
          <div class="player-controls">
            <audio controls preload="metadata" src="${esc(file.href)}"></audio>
            <div class="player-opts">
              <div class="seg speed">${[1, 1.25, 1.5, 2].map(s => `<button data-speed="${s}" class="${s === 1 ? 'on' : ''}">${s}×</button>`).join('')}</div>
              ${turns.length ? '<label class="check"><input type="checkbox" id="follow" checked> Follow along</label>' : ''}
              <a class="link-arrow" href="${esc(file.href)}" target="_blank" rel="noopener">Download MP3</a>
            </div>
          </div>
          ${turns.length ? `<div class="transcript" id="transcript">${turns.map((t, i) => `<div class="turn ${t.j ? 'justice' : ''}" data-i="${i}" data-s="${t.s}"><div class="turn-h"><b>${esc(t.sp)}</b><span>${fmtTime(t.s)}</span></div><p>${esc(t.tx)}</p></div>`).join('')}</div>` : `<p class="muted-line" style="padding:0 18px 18px">${m.direct ? 'Audio from supremecourt.gov. A synchronized transcript will appear once Oyez publishes this argument.' : 'No synchronized transcript for this recording.'}${m.trPdf ? ` <a href="${esc(m.trPdf)}" target="_blank" rel="noopener">Read the official transcript (PDF) ↗</a>` : ''}</p>`}`;
        const audio = body.querySelector('audio');
        body.querySelectorAll('[data-speed]').forEach(b => b.addEventListener('click', () => { audio.playbackRate = +b.dataset.speed; body.querySelectorAll('[data-speed]').forEach(x => x.classList.toggle('on', x === b)); }));
        if (!turns.length) return;
        const tr = document.getElementById('transcript');
        const els = [...tr.querySelectorAll('.turn')];
        let cur = -1;
        tr.addEventListener('click', e => { const t = e.target.closest('.turn'); if (!t) return; audio.currentTime = +t.dataset.s + 0.05; audio.play(); });
        audio.addEventListener('timeupdate', () => {
          const now = audio.currentTime;
          let lo = 0, hi = turns.length - 1, idx = -1;
          while (lo <= hi) { const mid = (lo + hi) >> 1; if (turns[mid].s <= now) { idx = mid; lo = mid + 1; } else hi = mid - 1; }
          if (idx === cur) return;
          if (cur >= 0) els[cur].classList.remove('now');
          cur = idx;
          if (cur >= 0) {
            els[cur].classList.add('now');
            if (document.getElementById('follow')?.checked) tr.scrollTo({ top: els[cur].offsetTop - tr.offsetTop - 60, behavior: 'smooth' });
          }
        });
      }).catch(() => { body.innerHTML = '<p class="muted-line" style="padding:18px">Couldn\'t load this recording from Oyez.</p>'; });
    }
  }

  /* ------------------------------------------------------------ lectures */
  function viewLectures(params) { withData([['lectures', 'LECTURES']], L => renderLectures(L, params)); }
  function renderLectures(L, params) {
    const st = { cat: params.get('cat') || '', ch: params.get('ch') || '', q: params.get('q') || '' };
    const go = patch => { location.hash = hashFor('lectures', Object.assign({}, st, patch)); };
    const pq = parseQuery(st.q);
    const list = L.videos.filter(v => (!st.cat || v.cat.includes(st.cat)) && (!st.ch || v.ch === st.ch) &&
      (!pq.terms.length || pq.terms.every(t => (v.t + ' ' + v.ch).toLowerCase().includes(t))));
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Lectures</span></div>
        <h1>Lecture library</h1>
        <p>${fmt(L.videos.length)} constitutional law lectures, debates and conversations from ${L.channels.length} law schools, universities, think tanks and civic institutions. Click any video to watch it here.</p></div>
      <div class="wrap" style="padding-top:22px">
        <div class="lec-filters">
          <form id="lec-form" class="lec-search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="lec-q" type="search" placeholder="Search lectures…" value="${esc(st.q)}"></form>
          <select class="select" id="lec-ch" style="max-width:280px"><option value="">All institutions</option>${L.channels.map(c => `<option ${st.ch === c.name ? 'selected' : ''} value="${esc(c.name)}">${esc(c.name)} (${c.n})</option>`).join('')}</select>
        </div>
        <div class="suggest" style="margin:14px 0 22px"><button class="chip ${!st.cat ? 'on' : ''}" data-cat="">All</button>${L.categories.map(c => `<button class="chip ${st.cat === c ? 'on' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}</div>
        <div class="toolbar"><div class="count"><b>${fmt(list.length)}</b> video${list.length === 1 ? '' : 's'}</div></div>
        ${list.length ? `<div class="vgrid">${list.map(v => videoTile(v)).join('')}</div>` : '<div class="empty"><h3>No lectures match</h3></div>'}
      </div></div>`;
    document.getElementById('lec-form').addEventListener('submit', e => { e.preventDefault(); go({ q: document.getElementById('lec-q').value.trim() }); });
    document.getElementById('lec-ch').addEventListener('change', e => go({ ch: e.target.value }));
    app.querySelectorAll('[data-cat]').forEach(b => b.addEventListener('click', () => go({ cat: b.dataset.cat })));
  }
  // Uniform, generated thumbnails (title, creator, length, topic icon) instead of YouTube's images
  const LECTURE_ICON = {
    'Courses & Overviews': 'interpretation', 'Interpretation & Theory': 'interpretation', 'The Supreme Court': 'judicial-review',
    'Constitutional History': 'incorporation', 'Executive Power': 'executive-power', 'Administrative State': 'administrative-state',
    'Free Speech': 'free-speech', 'Federalism': 'federalism', 'Separation of Powers': 'separation-of-powers', 'Criminal Procedure': 'fourth-amendment',
    'Due Process & Privacy': 'due-process', 'Democracy & Elections': 'voting', 'Religious Liberty': 'religion', 'Equal Protection': 'equal-protection',
    'Second Amendment': 'second-amendment'
  };
  const cleanTitle = t => {
    let s = String(t || ''), prev;
    do { prev = s; s = s.replace(/\s*[|–—-]\s*(Constitution 101|US government and civics|Khan Academy|Crash Course[^|]*?#\d+|BRI's Homework Help Series)\s*$/i, '').replace(/:\s*Crash Course [^#]*#\d+$/i, ''); } while (s !== prev);
    return s.trim();
  };
  function videoThumb(v, iconKey, big) {
    const icon = GUIDE_ICONS[iconKey] || '<path d="M9 7.5v9l7.5-4.5z"/><circle cx="12" cy="12" r="9"/>';
    return `<span class="vthumb vthumb-gen${big ? ' big' : ''}">
      <span class="vg-top"><span class="vg-icon"><svg viewBox="0 0 24 24">${icon}</svg></span><span class="vg-brand">Lex <em>Constitutio</em></span></span>
      <span class="vg-title">${esc(cleanTitle(v.t))}</span>
      <span class="vg-ch">${esc(v.ch)}</span>
      ${v.len ? `<span class="vlen">${esc(v.len)}</span>` : ''}<span class="vplay">▶</span>
    </span>`;
  }
  function videoTile(v, iconKey) {
    return `<button class="vtile" data-video="${esc(v.id)}" data-title="${esc(v.t)}" data-ch="${esc(v.ch)}">
      ${videoThumb(v, iconKey || LECTURE_ICON[(v.cat || [])[0]])}
      <span class="vm">${[(v.cat || [])[0], v.v ? compact(v.v) + ' views' : ''].filter(Boolean).map(esc).join(' · ')}</span>
    </button>`;
  }
  // One video at a time with arrows and dots; the poster becomes the player on click
  function mountCarousel(videos, iconKey) {
    const el = document.getElementById('vcarousel');
    if (!el || !videos.length) return;
    const stage = el.querySelector('.vc-stage'), cap = document.querySelector('.vc-cap'), dots = [...document.querySelectorAll('.vc-dots button')];
    let i = 0;
    const show = (n, play) => {
      i = (n + videos.length) % videos.length;
      const v = videos[i];
      stage.innerHTML = play
        ? `<div class="embed"><iframe src="${embedSrc(v.id)}&autoplay=1" title="${esc(v.t)}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>`
        : `<button class="vc-poster" aria-label="Play ${esc(v.t)}">${videoThumb(v, iconKey, true)}</button>`;
      cap.innerHTML = `<b>${esc(cleanTitle(v.t))}</b> · ${esc(v.ch)}${v.len ? ' · ' + esc(v.len) : ''}${videos.length > 1 ? `<span class="vc-count">${i + 1} / ${videos.length}</span>` : ''}`;
      dots.forEach((d, k) => d.classList.toggle('on', k === i));
      const poster = stage.querySelector('.vc-poster');
      if (poster) poster.addEventListener('click', () => show(i, true));
    };
    el.querySelector('.vc-prev')?.addEventListener('click', () => show(i - 1));
    el.querySelector('.vc-next')?.addEventListener('click', () => show(i + 1));
    dots.forEach((d, k) => d.addEventListener('click', () => show(k)));
    el.tabIndex = 0;
    el.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') show(i - 1); if (e.key === 'ArrowRight') show(i + 1); });
    show(0);
  }
  const compact = n => n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'K' : String(n);
  const embedSrc = id => `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?rel=0&modestbranding=1`;
  function openVideo(id, title, ch) {
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = `<div class="modal-box" role="dialog" aria-label="${esc(title)}">
      <div class="modal-video"><iframe src="${embedSrc(id)}&autoplay=1" title="${esc(title)}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>
      <div class="modal-foot"><div><b>${esc(title)}</b><span>${esc(ch)}</span></div>
        <div style="display:flex;gap:8px"><a class="btn btn-ghost btn-sm" href="https://www.youtube.com/watch?v=${encodeURIComponent(id)}" target="_blank" rel="noopener">YouTube ↗</a><button class="btn btn-primary btn-sm" data-close>Close</button></div></div>
    </div>`;
    const close = () => { m.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = e => { if (e.key === 'Escape') close(); };
    m.addEventListener('click', e => { if (e.target === m || e.target.closest('[data-close]')) close(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(m);
  }

  /* ------------------------------------------------------------ beginner's guide */
  // Beginner topics -> Originalist's Corner topics and advanced doctrine sections
  const GUIDE_LINKS = {
    'judicial-review': [['judicial-review'], ['supremacy-review', 'political-question']],
    'interpretation': [['common-law', 'natural-rights'], ['interpretation']],
    'incorporation': [['due-process', 'privileges'], ['incorporation', 'p-or-i']],
    'separation-of-powers': [['separation'], ['separation-of-powers', 'youngstown']],
    'executive-power': [['executive', 'removal-appointments'], ['article-two', 'immunity-privilege']],
    'federalism': [['federalism', 'supremacy'], ['commerce', 'sovereign-immunity', 'preemption']],
    'commerce-clause': [['commerce', 'necessary-proper'], ['enumerated', 'commerce', 'dormant-commerce']],
    'standing': [['judicial-review'], ['standing', 'ripeness', 'mootness']],
    'administrative-state': [['separation', 'executive'], ['separation-of-powers']],
    'free-speech': [['speech-press'], ['content', 'forums', 'categories', 'special-contexts']],
    'religion': [['religion'], ['free-exercise', 'establishment', 'religion-interaction']],
    'second-amendment': [['arms', 'war'], ['other-fundamental']],
    'equal-protection': [['slavery', 'citizenship'], ['ep-framework', 'strict', 'intermediate', 'race-remedies']],
    'due-process': [['due-process', 'life-unborn', 'marriage-family'], ['identifying', 'privacy-family', 'pdp-interests', 'mathews']],
    'fourth-amendment': [['search'], ['incorporation']],
    'trial-rights': [['jury', 'criminal-process'], ['incorporation', 'mathews']],
    'punishment': [['punishment'], ['incorporation']],
    'takings': [['property'], ['takings', 'economic-sdp']],
    'voting': [['elections'], ['other-fundamental', 'political-question']],
    'war-powers': [['war', 'treaties'], ['article-two', 'youngstown']],
  };
  const CORNER_NAMES = {
    'judicial-review': 'Judicial Review & the Judiciary', separation: 'Separation of Powers', executive: 'Executive Power', 'removal-appointments': 'Appointments & Removal',
    war: 'War, Militia & Standing Armies', treaties: 'Treaties & Foreign Affairs', commerce: 'Commerce & Trade', taxing: 'Taxation & Spending', 'necessary-proper': 'Necessary & Proper',
    federalism: 'Federalism & State Sovereignty', supremacy: 'Supremacy of Federal Law', religion: 'Religion & Conscience', 'speech-press': 'Speech & Press', arms: 'Right to Bear Arms',
    search: 'Searches & Warrants', jury: 'Trial by Jury', habeas: 'Habeas Corpus', punishment: 'Punishment, Bail & Fines', 'criminal-process': 'Rights of the Accused',
    'due-process': 'Due Process & Law of the Land', property: 'Property & Takings', contracts: 'Contracts & Ex Post Facto', 'life-unborn': 'Life, the Unborn & Homicide',
    'marriage-family': 'Marriage & Family', citizenship: 'Citizenship & Naturalization', slavery: 'Slavery', elections: 'Elections & Representation', impeachment: 'Impeachment',
    amendment: 'Amendment', 'natural-rights': 'Natural Rights', 'common-law': 'Common Law & Precedent', privileges: 'Privileges & Immunities', 'bankruptcy-ip': 'Bankruptcy & IP',
    money: 'Money & Banking', indians: 'Indian Tribes', territories: 'Territories', guarantee: 'Republican Government'
  };
  // Line icons for the beginner topics (24×24 grid, drawn with the shared stroke style)
  const GUIDE_ICONS = {
    'judicial-review': '<path d="M14.5 3.5l6 6M12 6l6 6M10.5 7.5l6 6"/><path d="M13 4.5l-4 4 6.5 6.5 4-4z"/><path d="M11.2 12.8L4 20"/><path d="M3 21h9"/>',
    'interpretation': '<path d="M3 5.5C5.5 4.5 8.5 4.5 12 6.5c3.5-2 6.5-2 9-1v13c-2.5-1-5.5-1-9 1-3.5-2-6.5-2-9-1z"/><path d="M12 6.5v13"/><circle cx="17" cy="11" r="2.6"/><path d="M18.9 12.9l2.1 2.1"/>',
    'incorporation': '<path d="M7 3h7l4 4v8"/><path d="M14 3v4h4"/><path d="M9.5 9h5M9.5 12h3"/><path d="M7 3v12"/><path d="M4 21h16"/><path d="M6 21v-4h12v4"/><path d="M12 15v2"/>',
    'separation-of-powers': '<path d="M3 9l9-5 9 5"/><path d="M4 21h16"/><path d="M5.5 10v8M10 10v8M14 10v8M18.5 10v8"/><path d="M4 18h16"/>',
    'executive-power': '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.2l1.45 2.95 3.25.47-2.35 2.29.56 3.24L12 14.6l-2.91 1.55.56-3.24L7.3 10.62l3.25-.47z"/>',
    'federalism': '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3"/><path d="M12 3.5V9M12 15v5.5M3.5 12H9M15 12h5.5"/>',
    'commerce-clause': '<path d="M3 7.5l4-2.5 4 2.5v5l-4 2.5-4-2.5z"/><path d="M3 7.5l4 2.5 4-2.5M7 10v5"/><path d="M13.5 9.5h6m-2-2l2 2-2 2"/><path d="M20.5 16.5h-6m2 2l-2-2 2-2"/>',
    'standing': '<circle cx="9" cy="5.5" r="2.2"/><path d="M5.5 21v-6.5L4.5 11c0-1.5 1.5-2.6 3-2.6h3c1.5 0 3 1.1 3 2.6l-1 3.5V21"/><path d="M9 14.5V21"/><path d="M15.5 12l2 2 3.5-4"/>',
    'administrative-state': '<path d="M3 21h11"/><path d="M4 21V8l5-4 5 4v13"/><path d="M7 11h4M7 14.5h4M7 18h4"/><circle cx="18" cy="15" r="2.3"/><path d="M18 10.7v1.5M18 17.8v1.5M13.7 15h1.5M20.8 15h1.5M15 12l1 1M20 17l1 1M21 12l-1 1M16 17l-1 1"/>',
    'free-speech': '<path d="M4 5.5h16v10H10l-4.5 3.5v-3.5H4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    'religion': '<path d="M12 3c-2.5 3-4 5.2-4 7.6a4 4 0 0 0 8 0C16 8.2 14.5 6 12 3z"/><path d="M12 9.5c-.9 1.1-1.4 2-1.4 2.9a1.4 1.4 0 0 0 2.8 0c0-.9-.5-1.8-1.4-2.9z"/><path d="M6.5 21h11M8.5 21l1-6.4M15.5 21l-1-6.4"/>',
    'second-amendment': '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z"/><path d="M12 7.5v9M8.2 10.5h7.6"/>',
    'equal-protection': '<circle cx="6.5" cy="6.5" r="2.2"/><circle cx="17.5" cy="6.5" r="2.2"/><path d="M3 15c0-2.6 1.6-4.4 3.5-4.4S10 12.4 10 15M14 15c0-2.6 1.6-4.4 3.5-4.4S21 12.4 21 15"/><path d="M8 18.5h8M8 21h8"/>',
    'due-process': '<path d="M12 3v18M7.5 21h9"/><path d="M4.5 7h15"/><path d="M4.5 7L2 13a2.5 2.5 0 0 0 5 0zM19.5 7L17 13a2.5 2.5 0 0 0 5 0z"/><circle cx="12" cy="4.5" r="1.3"/>',
    'fourth-amendment': '<path d="M3 11l9-7 9 7"/><path d="M5 9.5V20h14V9.5"/><rect x="9.5" y="13" width="5" height="4.5" rx=".8"/><path d="M10.5 13v-1.3a1.5 1.5 0 0 1 3 0V13"/>',
    'trial-rights': '<circle cx="6" cy="8" r="1.9"/><circle cx="12" cy="6.5" r="1.9"/><circle cx="18" cy="8" r="1.9"/><path d="M3 15c.3-2 1.6-3.3 3-3.3s2.7 1.3 3 3.3M9 13.5c.3-2 1.6-3.3 3-3.3s2.7 1.3 3 3.3M15 15c.3-2 1.6-3.3 3-3.3s2.7 1.3 3 3.3"/><path d="M2.5 17.5h19v3.5h-19z"/>',
    'punishment': '<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M8.5 3.5v17M12 3.5v17M15.5 3.5v17"/><path d="M4 9.5h16"/>',
    'takings': '<path d="M2.5 12L10 5.5l7.5 6.5"/><path d="M4.5 10.5V20h11v-9.5"/><path d="M8.5 20v-5h3v5"/><circle cx="18.5" cy="17.5" r="3.5"/><path d="M18.5 15.6v3.8M17.4 16.4c.3-.4 2.2-.5 2.2.4s-2.2.6-2.2 1.5 1.9.8 2.2.4"/>',
    'voting': '<path d="M4 12h16v8.5H4z"/><path d="M8.5 15.5h7"/><path d="M8 12V3.5h8V12"/><path d="M10 8l1.6 1.6L14.5 6.5"/>',
    'war-powers': '<path d="M5 21V3.5"/><path d="M5 4.5c4.5-2 7.5 2.5 14 0v8.5c-6.5 2.5-9.5-2-14 0"/><path d="M8.5 7.5l.5 1 1 .2-.75.7.2 1.1-.95-.5-.95.5.2-1.1-.75-.7 1-.2z"/>',
  };
  const guideIcon = id => `<span class="guide-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${GUIDE_ICONS[id] || '<circle cx="12" cy="12" r="8"/>'}</svg></span>`;
  function viewGuide() { withData([['guide', 'GUIDE'], ['advanced', 'ADVANCED']], (G, A) => renderGuide(G, A)); }
  function renderGuide(G, A) {
    const groups = [...new Set(G.topics.map(t => t.group))];
    app.innerHTML = `<div class="fade-in">
      <section class="hero guide-hero"><div class="hero-inner" style="padding:64px 24px 54px">
        <span class="eyebrow">Beginner's Guide</span>
        <h1 style="max-width:18ch">The essential guide to <em>constitutional law.</em></h1>
        <p class="lede">Start with ${G.topics.length} core topics, each with a plain-English overview, short explainer videos, the landmark cases, and readable articles. Then go deeper in the <a href="#/guide" data-jump="advanced" style="color:var(--accent)">advanced doctrine</a> below: every major doctrine, test and case, with excerpts from the opinions themselves.</p>
        <div class="suggest" style="margin-top:22px"><a class="chip on" href="#/guide" data-jump="beginner">Beginner topics</a><a class="chip" href="#/guide" data-jump="advanced">Advanced doctrine</a><a class="chip" href="#/corner">Originalist's Corner</a></div>
      </div></section>
      <div id="beginner"></div>
      ${groups.map(g => `<section class="section" style="padding-top:44px">
        <div class="section-head"><div><h2>${esc(g)}</h2></div></div>
        <div class="guide-grid">${G.topics.filter(t => t.group === g).map((t, i) => `<a class="guide-card" href="#/guide/${t.id}">
          ${guideIcon(t.id)}
          <span class="guide-body"><b>${esc(t.title)}</b><span>${esc(t.tagline)}</span>
          <span class="guide-meta">${t.videos.length} videos · ${t.cases.length} cases · ${(t.books || []).length} book${(t.books || []).length === 1 ? '' : 's'} · ${t.articles.length} readings</span></span>
        </a>`).join('')}</div>
      </section>`).join('')}
      <section class="section advanced-intro" id="advanced" style="padding-top:70px">
        <div class="adv-banner">
          <span class="eyebrow">Advanced</span>
          <h2>Constitutional law in depth</h2>
          <p>A doctrine-by-doctrine treatment of American constitutional law in ${A.parts.length} parts, organized after the chapter structure of Chemerinsky's <em>Constitutional Law: Principles and Policies</em>. Each section explains the doctrine and sets out the black-letter tests. It links the controlling cases, quotes key passages from the opinions, and includes in-depth commentary from the Library of Congress&rsquo;s <em>Constitution Annotated</em> on how each doctrine developed and has been applied, along with related scholarship and founding-era sources.</p>
        </div>
        <div class="adv-grid">${A.parts.map((p, i) => `<a class="adv-card" href="#/doctrine/${p.id}">
          <span class="adv-num">${esc(p.title.split('.')[0])}</span>
          <span class="adv-body"><b>${esc(p.title.replace(/^[IVXL]+\.\s*/, ''))}</b><span>${esc(p.summary || '')}</span>
          <em>${p.sections.length} section${p.sections.length === 1 ? '' : 's'} · ${p.sections.reduce((n, s) => n + s.cases.length, 0)} cases</em></span>
        </a>`).join('')}</div>
      </section>
    </div>`;
    app.querySelectorAll('[data-jump]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); document.getElementById(a.dataset.jump).scrollIntoView({ behavior: 'smooth' }); }));
  }

  /* ------------------------------------------------------------ advanced doctrine */
  function viewDoctrine(partId, secId) { withData([['advanced', 'ADVANCED'], ['quizzes', 'QUIZZES'], ['commentary', 'COMMENTARY']], (A, Q, C) => renderDoctrine(A, partId, secId, Q, C)); }
  // In-depth commentary from the Constitution Annotated (CRS, Library of Congress; public domain)
  function commentaryHtml(C, secId) {
    const essays = (C && C.sections[secId]) || [];
    if (!essays.length) return '';
    const words = e => e.p.reduce((n, p) => n + p.replace(/<[^>]+>/g, '').split(/\s+/).length, 0);
    const total = essays.reduce((n, e) => n + words(e), 0);
    const depth = id => Math.max(0, id.split('.').length - Math.min(...essays.map(x => x.id.split('.').length)));
    return `<div class="doc-block commentary">
      <div class="commentary-h"><div><h3>In depth: how the doctrine has developed</h3>
        <p>${essays.length} essay${essays.length === 1 ? '' : 's'} from the <i>Constitution Annotated</i> tracing the history, the leading cases and how the Court has applied this doctrine (${fmt(Math.round(total / 230))} min read).</p></div>
        <button class="btn btn-ghost btn-sm" data-expand-all>Expand all</button></div>
      ${essays.map((e, i) => `<details class="essay" style="--d:${depth(e.id)}" ${i === 0 ? 'open' : ''}>
        <summary><span class="essay-id">${esc(e.id)}</span><b>${esc(e.title)}</b><em>${Math.max(1, Math.round(words(e) / 230))} min</em></summary>
        <div class="essay-body">${e.p.map(p => `<p>${p}</p>`).join('')}</div>
      </details>`).join('')}
      <p class="attrib">From <i>Constitution of the United States of America: Analysis and Interpretation</i> (the "Constitution Annotated"), prepared by the Congressional Research Service, Library of Congress (2022 ed.). A U.S. government work in the public domain. Footnotes are omitted; the annotated edition with full citations is at <a href="https://constitution.congress.gov/" target="_blank" rel="noopener">constitution.congress.gov</a>. Developments after 2022 are covered in the summaries above.</p>
    </div>`;
  }
  function renderDoctrine(A, partId, secId, Q, C) {
    const pi = A.parts.findIndex(p => p.id === partId);
    const p = A.parts[pi];
    if (!p) return viewNotFound();
    const prev = A.parts[pi - 1], next = A.parts[pi + 1];
    const excerpt = e => `<figure class="excerpt">
      <blockquote>${esc(e.t)}</blockquote>
      <figcaption>${e.id ? `<a href="#/case/${esc(e.id)}"><i>${esc(e.n)}</i></a>` : `<i>${esc(e.n)}</i>`}${e.cit ? `, ${esc(e.cit)}` : ''} (${e.y}) · <span>${esc(e.src || '')}</span>${e.pdf ? ` · <a href="${esc(e.pdf)}" target="_blank" rel="noopener">PDF ↗</a>` : ''}</figcaption>
    </figure>`;
    app.innerHTML = `<div class="fade-in"><div class="doctrine">
      <aside class="doc-toc">
        <a class="doc-back" href="#/guide">← Beginner's Guide</a>
        <h4>Advanced doctrine</h4>
        <ol>${A.parts.map(x => `<li class="${x.id === p.id ? 'cur' : ''}"><a href="#/doctrine/${x.id}">${esc(x.title)}</a>
          ${x.id === p.id ? `<ul>${x.sections.map(s => `<li><a href="#/doctrine/${x.id}/${s.id}" data-sec="${s.id}">${esc(s.title)}</a></li>`).join('')}</ul>` : ''}</li>`).join('')}</ol>
      </aside>
      <article class="doc-main">
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/guide">Beginner's Guide</a><span>/</span><a href="#/guide" data-adv>Advanced doctrine</a></div>
        <h1>${esc(p.title)}</h1>
        ${p.summary ? `<p class="guide-tagline">${esc(p.summary)}</p>` : ''}
        ${p.sections.map(s => `<section class="doc-sec" id="sec-${s.id}">
          <h2 class="doc-h">${esc(s.title)}</h2>
          <div class="doc-body">${s.html}</div>
          ${s.cases.length ? `<div class="doc-block"><h3>Key cases</h3><ul class="case-list">${s.cases.map(c => `<li>${c.id ? `<a href="#/case/${esc(c.id)}"><i>${esc(c.n)}</i></a>` : `<i>${esc(c.n)}</i>`}${c.cit ? ` <span class="cit">${esc(c.cit)}</span>` : ''} <span class="yr">(${c.y})</span><div>${esc(c.note || '')}</div></li>`).join('')}</ul></div>` : ''}
          ${s.excerpts.length ? `<div class="doc-block"><h3>From the opinions</h3>${s.excerpts.map(excerpt).join('')}</div>` : ''}
          ${commentaryHtml(C, s.id)}
          ${(s.corner.length || s.articles.length) ? `<div class="doc-block doc-more">
            ${s.corner.length ? `<div><h3>Originalist's Corner</h3><div class="tags">${s.corner.map(c => `<a class="tag corner-tag" href="#/corner/${esc(c)}">${esc(CORNER_NAMES[c] || c)}</a>`).join('')}</div></div>` : ''}
            ${s.articles.length ? `<div><h3>Scholarship</h3><ul class="mini-list">${s.articles.map(id => byId.get(id)).filter(Boolean).map(a => `<li><a class="t" href="${articleHref(a)}">${esc(a.t)}</a><div class="m">${esc(a.a.slice(0, 2).join(', '))}${a.a.length > 2 ? ' et al.' : ''} · ${esc(journalById[a.j]?.name || '')}${a.y ? ' · ' + a.y : ''}${a.c != null ? ' · ' + fmt(a.c) + ' citations' : ''}</div></li>`).join('')}</ul></div>` : ''}
          </div>` : ''}
        </section>`).join('')}
        ${quizHtml('doctrine:' + p.id, Q && Q.doctrine[p.id], 'Socratic review: ' + p.title.replace(/^[IVXL]+\.\s*/, ''), 'Questions in the style of a law school cold call: the facts, holdings and reasoning of the key cases, and how the rules apply to new hypotheticals.')}
        <p class="attrib" style="margin-top:28px">Doctrinal summaries written for Lex Constitutio, following the organization of Erwin Chemerinsky, <i>Constitutional Law: Principles and Policies</i> (7th ed. 2023). They are a study aid, not legal advice, and doctrine changes; check the current Term. Opinion excerpts are public-domain text from the <i>United States Reports</i> (Library of Congress), supremecourt.gov slip opinions, and Wikisource transcriptions. Open casebooks for edited cases and notes: <i>Constitutional Structures</i> (N. Gomez-Velez), <i>Constitutional Law II</i>, and other H2O casebooks at opencasebook.org (CC BY-NC-SA).</p>
        <div class="guide-nav">
          ${prev ? `<a href="#/doctrine/${prev.id}"><small>← Previous</small>${esc(prev.title)}</a>` : '<span></span>'}
          ${next ? `<a href="#/doctrine/${next.id}" style="text-align:right"><small>Next →</small>${esc(next.title)}</a>` : '<span></span>'}
        </div>
      </article>
    </div></div>`;
    const go = id => { const el = document.getElementById('sec-' + id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
    app.querySelectorAll('[data-sec]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); history.replaceState(null, '', `#/doctrine/${p.id}/${a.dataset.sec}`); go(a.dataset.sec); }));
    app.querySelector('[data-adv]').addEventListener('click', e => { e.preventDefault(); location.hash = '#/guide'; setTimeout(() => document.getElementById('advanced')?.scrollIntoView(), 300); });
    if (Q) mountQuiz(app, 'doctrine:' + p.id, Q.doctrine[p.id] || []);
    app.querySelectorAll('[data-expand-all]').forEach(b => b.addEventListener('click', () => {
      const ds = b.closest('.commentary').querySelectorAll('details.essay');
      const open = [...ds].some(d => !d.open);
      ds.forEach(d => { d.open = open; });
      b.textContent = open ? 'Collapse all' : 'Expand all';
    }));
    if (secId) setTimeout(() => go(secId), 60);
  }
  function doctrineHref(A, secId) {
    for (const p of A.parts) if (p.sections.some(s => s.id === secId)) return { href: `#/doctrine/${p.id}/${secId}`, title: p.sections.find(s => s.id === secId).title, part: p.title };
    return null;
  }
  function viewGuideTopic(id) { withData([['guide', 'GUIDE'], ['scotus', 'SCOTUS'], ['books', 'BOOKS'], ['advanced', 'ADVANCED'], ['quizzes', 'QUIZZES']], (G, S, B, A, Q) => renderGuideTopic(G, S, id, B, A, Q)); }
  function renderGuideTopic(G, S, id, B, A, Q) {
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const i = G.topics.findIndex(t => t.id === id);
    const t = G.topics[i];
    if (!t) return viewNotFound();
    const prev = G.topics[i - 1], next = G.topics[i + 1];
    const arts = t.articles.map(x => byId.get(x)).filter(Boolean);
    const [main, ...more] = t.videos;
    app.innerHTML = `<div class="fade-in"><div class="article guide-page">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/guide">Beginner's Guide</a><span>/</span><span>${esc(t.group)}</span></div>
        <div class="guide-title">${guideIcon(t.id)}<h1>${esc(t.title)}</h1></div>
        <p class="guide-tagline">${esc(t.tagline)}</p>
        ${t.wiki ? `<div class="explainer">
          <div class="explainer-h"><span>The short version</span><a href="${esc(t.wiki.url)}" target="_blank" rel="noopener">Wikipedia: ${esc(t.wiki.title)} ↗</a></div>
          <p>${esc(t.wiki.text)}</p>
          <div class="explainer-f">Text from Wikipedia, licensed CC BY-SA 4.0.${t.wex ? ` For a legal-dictionary definition, see <a href="${esc(t.wex)}" target="_blank" rel="noopener">Cornell LII Wex ↗</a>` : ''}</div>
        </div>` : ''}
        ${main ? `<h2>Watch</h2>
          <div class="vcarousel" id="vcarousel">
            <div class="vc-stage"></div>
            ${t.videos.length > 1 ? `<button class="vc-nav vc-prev" aria-label="Previous video">‹</button><button class="vc-nav vc-next" aria-label="Next video">›</button>` : ''}
          </div>
          <div class="vc-foot"><div class="embed-cap vc-cap"></div>${t.videos.length > 1 ? `<div class="vc-dots">${t.videos.map((_, i) => `<button data-vi="${i}" aria-label="Video ${i + 1}"></button>`).join('')}</div>` : ''}</div>` : ''}
        ${(t.books || []).length ? `<h2>Start with a book</h2>
        <div class="guide-books">${t.books.map(bid => B.books.find(x => x.id === bid)).filter(Boolean).map(b => `<a class="guide-book" href="#/book/${esc(b.id)}">
          ${bookCover(b, 'sm')}
          <span><b>${esc(b.title.split(':')[0])}</b><em>${esc(b.authors.join(', '))} · ${b.year}</em><span>${esc(b.note)}</span>
          ${b.gr ? `<small>${stars(b.gr.rating)} ${b.gr.rating.toFixed(2)} on Goodreads</small>` : ''}</span>
        </a>`).join('')}</div>` : ''}
        <h2>Essential cases</h2>
        <div class="cards">${t.cases.map(x => {
          const c = x.id && caseById.get(x.id);
          return c ? caseCard(c) : `<article class="card"><h3>${esc(x.n)}</h3><div class="card-meta"><span>${x.y}</span></div></article>`;
        }).join('')}</div>
        <h2>Start reading</h2>
        <p class="muted-line" style="margin-top:-4px">Widely cited, accessible articles from the index on this topic.</p>
        <div class="cards">${arts.map(a => card(a)).join('')}</div>
        ${(() => {
          const [cornerIds, secIds] = GUIDE_LINKS[t.id] || [[], []];
          const secs = secIds.map(s => doctrineHref(A, s)).filter(Boolean);
          if (!cornerIds.length && !secs.length) return '';
          return `<h2>Go deeper</h2>
          <div class="deeper">
            ${cornerIds.length ? `<div class="deeper-col"><div class="deeper-h"><span class="f-icon">❦</span><div><b>Originalist's Corner</b><span>What Blackstone, The Federalist, Story, the Convention debates and early statutes said.</span></div></div>
              <ul class="mini-list">${cornerIds.map(c => `<li><a class="t" href="#/corner/${c}">${esc(CORNER_NAMES[c] || c)}</a><div class="m">Founding-era sources →</div></li>`).join('')}</ul></div>` : ''}
            ${secs.length ? `<div class="deeper-col"><div class="deeper-h"><span class="f-icon">§</span><div><b>Advanced doctrine</b><span>The black-letter tests, the full case law, and excerpts from the opinions.</span></div></div>
              <ul class="mini-list">${secs.map(s => `<li><a class="t" href="${s.href}">${esc(s.title)}</a><div class="m">${esc(s.part)}</div></li>`).join('')}</ul></div>` : ''}
          </div>`;
        })()}
        ${quizHtml('guide:' + t.id, Q && Q.guide[t.id], 'Quiz: ' + t.title, 'Five questions on this page: the overview, the key ideas, and the landmark cases.')}
        <div class="guide-nav">
          ${prev ? `<a href="#/guide/${prev.id}"><small>← Previous</small>${esc(prev.title)}</a>` : '<span></span>'}
          ${next ? `<a href="#/guide/${next.id}" style="text-align:right"><small>Next →</small>${esc(next.title)}</a>` : '<span></span>'}
        </div>
      </div>
      <aside>
        <div class="panel"><h4>Go deeper</h4><ul class="mini-list">
          ${t.topics.map(tp => topicById[tp] ? `<li><a class="t" href="${hashFor('search', { topic: tp })}">${esc(topicById[tp].name)}</a><div class="m">${fmt(topicCount[tp] || 0)} articles in the index</div></li>` : '').join('')}
          <li><a class="t" href="${hashFor('impact', { topic: t.topics[0] })}">Most cited in this area</a><div class="m">Ranked by citations</div></li>
          ${t.wex ? `<li><a class="t" href="${esc(t.wex)}" target="_blank" rel="noopener">Cornell LII Wex entry ↗</a><div class="m">Legal encyclopedia</div></li>` : ''}
        </ul></div>
        <div class="panel"><h4>All beginner topics</h4><ul class="mini-list toc">${G.topics.map(x => `<li><a class="t ${x.id === id ? 'cur' : ''}" href="#/guide/${x.id}">${esc(x.title)}</a></li>`).join('')}</ul></div>
      </aside>
    </div></div>`;
    if (Q) mountQuiz(app, 'guide:' + t.id, Q.guide[t.id] || []);
    mountCarousel(t.videos, t.id);
  }

  /* ------------------------------------------------------------ books */
  function stars(r) {
    const pct = Math.max(0, Math.min(100, (r / 5) * 100));
    return `<span class="stars" aria-label="${r} out of 5"><span class="stars-fill" style="width:${pct}%">★★★★★</span>★★★★★</span>`;
  }
  function bookCover(b, cls = '') {
    return b.cover ? `<img class="cover ${cls}" loading="lazy" src="${esc(b.cover)}" alt="Cover of ${esc(b.title)}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'cover cover-fallback ${cls}',textContent:${esc(JSON.stringify(b.title.split(':')[0]))}}))">`
      : `<div class="cover cover-fallback ${cls}">${esc(b.title.split(':')[0])}</div>`;
  }
  function bookTile(b) {
    return `<a class="btile" href="#/book/${esc(b.id)}">
      ${bookCover(b)}
      <span class="bt">${esc(b.title.split(':')[0])}</span>
      <span class="ba">${esc(b.authors.join(', '))} · ${b.year}</span>
      <span class="bm">${b.gr ? `${stars(b.gr.rating)} <b>${b.gr.rating.toFixed(2)}</b>` : ''}${b.reviews.length ? `<span class="brev">${b.reviews.length} review${b.reviews.length === 1 ? '' : 's'}</span>` : ''}</span>
      ${b.cites ? `<span class="bcite" title="Scholarly citations (${esc(b.cites.src)})">${citeIcon}${fmt(b.cites.n)} citations</span>` : ''}
    </a>`;
  }
  function viewBooks(params) { withData([['books', 'BOOKS']], B => renderBooks(B, params)); }
  function renderBooks(B, params) {
    const st = { cat: params.get('cat') || '', sort: params.get('sort') || '', q: params.get('q') || '' };
    const go = patch => { location.hash = hashFor('books', Object.assign({}, st, patch)); };
    const pq = parseQuery(st.q);
    let list = B.books.filter(b => (!st.cat || b.cat === st.cat || (st.cat === 'Introductions & Primers' && b.intro)) &&
      (!pq.terms.length || pq.terms.every(t => (b.title + ' ' + b.authors.join(' ') + ' ' + b.note).toLowerCase().includes(t))));
    if (st.sort === 'rating') list = list.slice().sort((a, b) => (b.gr?.rating ?? 0) - (a.gr?.rating ?? 0));
    else if (st.sort === 'popular') list = list.slice().sort((a, b) => (b.gr?.count ?? 0) - (a.gr?.count ?? 0));
    else if (st.sort === 'cited') list = list.slice().sort((a, b) => (b.cites?.n ?? -1) - (a.cites?.n ?? -1));
    else if (st.sort === 'year') list = list.slice().sort((a, b) => a.year - b.year);
    const grouped = !st.sort && !st.q && !st.cat;
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Books</span></div>
        <h1>Essential books</h1>
        <p>${B.books.length} of the most important and influential books on American constitutional law, from founding-era classics to today's debates. Each book page links to law review book reviews, the publisher, and reader ratings.</p></div>
      <div class="wrap" style="padding-top:22px">
        <div class="lec-filters">
          <form id="bk-form" class="lec-search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="bk-q" type="search" placeholder="Search books or authors…" value="${esc(st.q)}"></form>
          <div class="seg" role="group" aria-label="Sort">
            <button data-sort="" class="${!st.sort ? 'on' : ''}">By topic</button>
            <button data-sort="rating" class="${st.sort === 'rating' ? 'on' : ''}">Top rated</button>
            <button data-sort="cited" class="${st.sort === 'cited' ? 'on' : ''}">Most cited</button>
            <button data-sort="popular" class="${st.sort === 'popular' ? 'on' : ''}">Most read</button>
            <button data-sort="year" class="${st.sort === 'year' ? 'on' : ''}">Chronological</button>
          </div>
        </div>
        <div class="suggest" style="margin:14px 0 26px"><button class="chip ${!st.cat ? 'on' : ''}" data-cat="">All</button>${B.categories.map(c => `<button class="chip ${st.cat === c ? 'on' : ''}" data-cat="${esc(c)}">${c === 'Introductions & Primers' ? '★ Good first reads' : esc(c)}</button>`).join('')}</div>
        ${grouped ? B.categories.map(c => {
          const items = B.books.filter(b => b.cat === c);
          return items.length ? `<section class="book-sec"><div class="section-head"><div><h2 style="font-size:26px">${esc(c)}</h2></div><span class="count" style="color:var(--ink-3);font-size:13px">${items.length} books</span></div><div class="bgrid">${items.map(bookTile).join('')}</div></section>` : '';
        }).join('') : (list.length ? `<div class="bgrid">${list.map(bookTile).join('')}</div>` : '<div class="empty"><h3>No books match</h3></div>')}
        <p class="attrib" style="margin-top:30px">Covers and metadata from Open Library. Ratings from Goodreads, which has no public API, so ratings are refreshed when the index is rebuilt.</p>
      </div></div>`;
    document.getElementById('bk-form').addEventListener('submit', e => { e.preventDefault(); go({ q: document.getElementById('bk-q').value.trim() }); });
    app.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () => go({ sort: b.dataset.sort })));
    app.querySelectorAll('[data-cat]').forEach(b => b.addEventListener('click', () => go({ cat: b.dataset.cat })));
  }
  function viewBook(id) { withData([['books', 'BOOKS']], B => renderBook(B, id)); }
  function renderBook(B, id) {
    const b = B.books.find(x => x.id === id);
    if (!b) return viewNotFound();
    const revs = b.reviews.map(r => byId.get(r)).filter(Boolean);
    const related = B.books.filter(x => x.cat === b.cat && x.id !== b.id).slice(0, 6);
    const authorLinks = b.authors.map(n => authorIndex.has(normName(n)) ? `<a href="${authorHref(n)}">${esc(n)}</a>` : esc(n)).join(', ');
    const inIndex = b.authors.filter(n => authorIndex.has(normName(n)));
    app.innerHTML = `<div class="fade-in"><div class="article book-page">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/books">Books</a><span>/</span><a href="${hashFor('books', { cat: b.cat })}">${esc(b.cat)}</a></div>
        <div class="book-head">
          ${bookCover(b, 'lg')}
          <div>
            <h1>${esc(b.title)}</h1>
            <div class="byline">${authorLinks}</div>
            <div class="publine">${esc(b.publisher)} · ${b.year}${b.pages ? ` · ${b.pages} pages` : ''}${b.isbn ? ` · ISBN ${esc(b.isbn)}` : ''}</div>
            ${b.gr ? `<a class="gr-box" href="${esc(b.gr.url)}" target="_blank" rel="noopener">${stars(b.gr.rating)}<b>${b.gr.rating.toFixed(2)}</b><span>${fmt(b.gr.count)} Goodreads ratings · read reviews ↗</span></a>` : ''}
            ${b.cites ? `<a class="gr-box cite-box-b" href="${esc(b.cites.url)}" target="_blank" rel="noopener"><span class="cites">${citeIcon}</span><b>${fmt(b.cites.n)}</b><span>scholarly citations · #${b.cites.rank} of ${B.citedBooks} books here · ${esc(b.cites.src)} ↗</span></a>` : ''}
            <div class="actions" style="margin-top:18px">
              <a class="btn btn-primary" href="${esc(b.amazon)}" target="_blank" rel="noopener">Amazon ↗</a>
              ${b.pubUrl ? `<a class="btn btn-ghost" href="${esc(b.pubUrl)}" target="_blank" rel="noopener">${b.id === 'federalist' ? 'Free full text (Library of Congress)' : esc(b.publisher)} ↗</a>` : ''}
              ${b.gr ? `<a class="btn btn-ghost" href="${esc(b.gr.url)}" target="_blank" rel="noopener">Goodreads ↗</a>` : ''}
              ${b.ol ? `<a class="btn btn-ghost" href="${esc(b.ol)}" target="_blank" rel="noopener">Open Library ↗</a>` : ''}
            </div>
          </div>
        </div>
        <h2>Why it matters</h2>
        <div class="callout">${esc(b.note)}</div>
        ${b.blurb ? `<h2>About the book</h2><p class="book-blurb">${esc(b.blurb)}</p><p class="attrib">Description via Goodreads (truncated). <a href="${esc(b.gr.url)}" target="_blank" rel="noopener" style="color:var(--accent)">Full description ↗</a></p>` : ''}
        <h2>Law review book reviews</h2>
        ${revs.length ? `<div class="cards">${revs.map(a => card(a)).join('')}</div>` : '<p class="muted-line">No reviews of this book are in the index yet. Try the searches below.</p>'}
        <div class="actions" style="margin-top:14px">
          <a class="btn btn-ghost btn-sm" href="${esc(b.scholar)}" target="_blank" rel="noopener">Find reviews on Google Scholar ↗</a>
          <a class="btn btn-ghost btn-sm" href="${esc(b.jstor)}" target="_blank" rel="noopener">Search JSTOR ↗</a>
          <a class="btn btn-ghost btn-sm" href="${hashFor('search', { q: '"' + b.title.split(':')[0] + '"' })}">Search this index</a>
        </div>
        ${related.length ? `<h2>More in ${esc(b.cat)}</h2><div class="bgrid small">${related.map(bookTile).join('')}</div>` : ''}
      </div>
      <aside>
        <div class="panel"><h4>Details</h4><dl class="kv">
          <dt>Author${b.authors.length > 1 ? 's' : ''}</dt><dd>${b.authors.map(esc).join('<br>')}</dd>
          <dt>Published</dt><dd>${b.year}</dd>
          <dt>Publisher</dt><dd>${esc(b.publisher)}</dd>
          ${b.pages ? `<dt>Pages</dt><dd>${b.pages}</dd>` : ''}
          ${b.isbn ? `<dt>ISBN</dt><dd>${esc(b.isbn)}</dd>` : ''}
          <dt>Topic</dt><dd><a class="tag" href="${hashFor('books', { cat: b.cat })}">${esc(b.cat)}</a>${b.intro ? ' <span class="tag tag-audio">Good first read</span>' : ''}</dd>
        </dl></div>
        ${b.guide ? `<div class="panel"><h4>Recommended in the guide</h4><ul class="mini-list">${b.guide.map(g => `<li><a class="t" href="#/guide/${esc(g.id)}">${esc(g.title)}</a></li>`).join('')}</ul></div>` : ''}
        ${inIndex.length ? `<div class="panel"><h4>Articles by the author</h4><ul class="mini-list">${inIndex.map(n => { const e = authorIndex.get(normName(n)); return `<li><a class="t" href="${authorHref(n)}">${esc(e.name)}</a><div class="m">${e.items.length} article${e.items.length === 1 ? '' : 's'} in the index</div></li>`; }).join('')}</ul></div>` : ''}
      </aside>
    </div></div>`;
  }

  /* ------------------------------------------------------------ originalist's corner */
  const SOURCE_ORDER = ['documents', 'madison', 'federalist', 'statutes', 'blackstone', 'tucker', 'story', 'kent', 'vattel', 'locke'];
  function viewCorner() { withData([['corner', 'CORNER']], C => renderCorner(C)); }
  function renderCorner(C) {
    const srcs = SOURCE_ORDER.map(id => C.sources.find(s => s.id === id)).filter(Boolean);
    app.innerHTML = `<div class="fade-in">
      <section class="hero corner-hero"><div class="hero-inner" style="padding:64px 24px 54px">
        <span class="eyebrow">Originalist's Corner</span>
        <h1 style="max-width:16ch">What the founding generation <em>actually said.</em></h1>
        <p class="lede">Choose a topic and read what Blackstone, the Convention debates, <i>The Federalist</i>, the acts of the first Congresses, Tucker, Story, Kent, Vattel and Locke said about it, side by side. The ${fmt(Object.keys(C.passages).length)} passages are drawn from the full texts of ${srcs.length} bodies of founding-era material.</p>
        <div class="suggest" style="margin-top:22px"><a class="chip" href="#/library">Browse the library →</a></div>
      </div></section>
      <section class="section" style="padding-top:44px">
        <div class="section-head"><div><h2>Topics</h2><p>Each topic gathers the most relevant passages from every source.</p></div></div>
        <div class="corner-grid">${C.topics.filter(t => t.n).map(t => `<a class="corner-card" href="#/corner/${t.id}">
          <b>${esc(t.name)}</b><span>${esc(t.desc)}</span><em>${t.n} passages · ${Object.keys(C.index[t.id] || {}).length} sources</em></a>`).join('')}</div>
      </section>
      <section class="section">
        <div class="section-head"><div><h2>The sources</h2><p>Public-domain texts, quoted from the original editions.</p></div><a class="link-arrow" href="#/library">Full-text library →</a></div>
        <div class="jgrid">${srcs.map(s => `<div class="jcard src-card">
          <div class="abbr">${esc(s.author)} · ${esc(s.year)}</div>
          <h3>${esc(s.name)}</h3>
          <p class="src-desc">${esc(s.desc)}</p>
          <div class="foot"><span>${fmt(s.n)} paragraphs indexed</span>${libraryLink(s.id)}</div>
        </div>`).join('')}</div>
      </section>
    </div>`;
  }
  function libraryLink(sid) {
    return { federalist: '<a class="link-arrow" href="#/library/federalist">Read →</a>', documents: '<a class="link-arrow" href="#/library/documents">Read →</a>', statutes: '<a class="link-arrow" href="#/library/statutes">Read →</a>' }[sid] || '';
  }
  function viewCornerTopic(id, params) { withData([['corner', 'CORNER']], C => renderCornerTopic(C, id, params)); }
  function renderCornerTopic(C, id, params) {
    const t = C.topics.find(x => x.id === id);
    if (!t) return viewNotFound();
    const only = params.get('s') || '';
    const idx = C.index[id] || {};
    const srcs = ((C.order && C.order[id]) || SOURCE_ORDER).map(sid => C.sources.find(s => s.id === sid)).filter(s => s && idx[s.id]);
    const shown = only ? srcs.filter(s => s.id === only) : srcs;
    const readLink = p => p.fed ? `<a href="#/library/federalist/${p.fed}">Read Federalist No. ${p.fed} →</a>`
      : p.doc ? `<a href="#/library/doc/${esc(p.doc)}">Read the full document →</a>`
      : p.st ? `<a href="#/library/statute/${esc(p.st)}">Read the full act →</a>`
      : p.u ? `<a href="${esc(p.u)}" target="_blank" rel="noopener">Source text ↗</a>` : '';
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><span>${esc(t.name)}</span></div>
        <h1>${esc(t.name)}</h1><p>${esc(t.desc)} ${t.n} passages from ${srcs.length} sources.</p>
        <div class="suggest" style="margin-top:16px"><a class="chip ${!only ? 'on' : ''}" href="#/corner/${id}">All sources</a>${srcs.map(s => `<a class="chip ${only === s.id ? 'on' : ''}" href="${hashFor('corner/' + id, { s: s.id })}">${esc(s.name.split(',')[0].replace(/^Acts of the First Congresses.*/, 'Early statutes').replace(/Founding Documents.*/, 'Founding documents').replace(/Madison's Notes.*/, "Madison's Notes"))} · ${idx[s.id].length}</a>`).join('')}</div>
      </div>
      <div class="layout">
        <aside class="sidebar"><div class="side-block"><h4>Topics</h4><ul class="tree">${C.topics.filter(x => x.n).map(x => `<li><a href="#/corner/${x.id}" class="${x.id === id ? 'on' : ''}"><span>${esc(x.name)}</span><span class="n">${x.n}</span></a></li>`).join('')}</ul></div></aside>
        <div>
          ${shown.map(s => `<section class="src-sec">
            <div class="src-h"><div><h2>${esc(s.name)}</h2><span>${esc(s.author)} · ${esc(s.year)}</span></div>${libraryLink(s.id)}</div>
            ${idx[s.id].map(pid => C.passages[pid]).filter(Boolean).map(p => `<figure class="passage">
              <figcaption>${esc(p.loc)}</figcaption>
              <blockquote>${esc(p.t)}</blockquote>
              <div class="passage-f">${readLink(p)}</div>
            </figure>`).join('')}
          </section>`).join('') || '<div class="empty"><h3>No passages for this topic</h3></div>'}
          <p class="attrib">Passages are selected automatically by matching each topic's vocabulary against the full texts, so read them in context. Sources: Lonang Institute (Blackstone, Tucker, Story, Kent, Vattel, Locke), Project Gutenberg (<i>The Federalist</i>), the Avalon Project at Yale Law School (Madison's Notes and founding documents), and Wikisource (<i>U.S. Statutes at Large</i>, vol. 1). All texts are in the public domain.</p>
        </div>
      </div></div>`;
  }

  /* ------------------------------------------------------------ library */
  function viewLibrary(seg, params) {
    const kind = seg[1] || '';
    if (!kind) return renderLibraryHome();
    if (kind === 'federalist') return withData([['library-federalist', 'LIB_FEDERALIST']], F => seg[2] ? renderFederalist(F, +seg[2]) : renderLibraryList('federalist', F, params));
    if (kind === 'documents' || kind === 'doc') return withData([['library-documents', 'LIB_DOCUMENTS']], D => seg[2] ? renderLibDoc(D, seg[2]) : renderLibraryList('documents', D, params));
    if (kind === 'statutes' || kind === 'statute') return withData([['library-statutes', 'LIB_STATUTES']], S => seg[2] ? renderStatute(S, seg[2]) : renderLibraryList('statutes', S, params));
    viewNotFound();
  }
  function renderLibraryHome() {
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><span>Library</span></div>
        <h1>The founding-era library</h1><p>Full texts you can read here: every number of <i>The Federalist</i>, the founding documents and early state constitutions, and every act of the first five Congresses.</p></div>
      <section class="section" style="padding-top:28px"><div class="jgrid">
        <a class="jcard" href="#/library/federalist"><div class="abbr">Hamilton, Madison & Jay · 1787–88</div><h3>The Federalist</h3><div class="foot"><span>85 essays</span><b>Read →</b></div></a>
        <a class="jcard" href="#/library/documents"><div class="abbr">1215–1802</div><h3>Founding documents & state constitutions</h3><div class="foot"><span>Magna Carta to the Danbury letter</span><b>Read →</b></div></a>
        <a class="jcard" href="#/library/statutes"><div class="abbr">1789–1799</div><h3>Acts of the First Congresses</h3><div class="foot"><span><i>Statutes at Large</i>, vol. 1</span><b>Read →</b></div></a>
      </div></section></div>`;
  }
  function renderLibraryList(kind, items, params) {
    const q = (params.get('q') || '').toLowerCase();
    const label = { federalist: 'The Federalist', documents: 'Founding documents', statutes: 'Acts of the First Congresses' }[kind];
    const rows = kind === 'federalist' ? items.map(f => ({ href: `#/library/federalist/${f.n}`, t: `No. ${f.n}. ${f.title}`, m: f.author, s: f.title + ' ' + f.author + ' ' + f.n }))
      : kind === 'documents' ? items.map(d => ({ href: `#/library/doc/${d.id}`, t: d.title, m: String(d.year), s: d.title }))
      : items.map(s => ({ href: `#/library/statute/${s.id}`, t: s.title, m: `${ordinal(s.cong)} Congress, ${ordinal(s.sess)} Session, ${s.chap}${s.date ? ' · ' + s.date : ''}`, s: s.title + ' ' + (s.date || '') }));
    const list = q ? rows.filter(r => r.s.toLowerCase().includes(q)) : rows;
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><a href="#/library">Library</a><span>/</span><span>${esc(label)}</span></div>
        <h1>${esc(label)}</h1></div>
      <div class="wrap" style="padding-top:20px">
        <form class="lec-search" id="lib-form" style="max-width:520px"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="lib-q" type="search" placeholder="Filter by title…" value="${esc(q)}"></form>
        <div class="toolbar" style="margin-top:14px"><div class="count"><b>${fmt(list.length)}</b> items</div></div>
        <ul class="lib-list">${list.map(r => `<li><a href="${r.href}"><b>${esc(r.t)}</b><span>${esc(r.m)}</span></a></li>`).join('')}</ul>
      </div></div>`;
    document.getElementById('lib-form').addEventListener('submit', e => { e.preventDefault(); location.hash = hashFor('library/' + kind, { q: document.getElementById('lib-q').value.trim() }); });
  }
  const ordinal = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');
  function readerPage(crumb, title, meta, paras, nav, extra) {
    app.innerHTML = `<div class="fade-in"><div class="reader">
      <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><a href="#/library">Library</a><span>/</span>${crumb}</div>
      <h1>${esc(title)}</h1>
      <div class="publine">${meta}</div>
      <div class="reader-body">${paras.map(p => `<p>${esc(p)}</p>`).join('')}</div>
      ${extra || ''}
      ${nav || ''}
    </div></div>`;
  }
  function renderFederalist(F, n) {
    const i = F.findIndex(f => f.n === n); const f = F[i];
    if (!f) return viewNotFound();
    const prev = F[i - 1], next = F[i + 1];
    readerPage('<a href="#/library/federalist">The Federalist</a>', `The Federalist No. ${f.n}`, `${esc(f.title)}${f.author ? ' · ' + esc(f.author) : ''}`, f.paras,
      `<div class="guide-nav">${prev ? `<a href="#/library/federalist/${prev.n}"><small>← No. ${prev.n}</small>${esc(prev.title)}</a>` : '<span></span>'}${next ? `<a href="#/library/federalist/${next.n}" style="text-align:right"><small>No. ${next.n} →</small>${esc(next.title)}</a>` : '<span></span>'}</div>`,
      '<p class="attrib">Text: Project Gutenberg eBook #1404 (public domain).</p>');
  }
  function renderLibDoc(D, id) {
    const d = D.find(x => x.id === id);
    if (!d) return viewNotFound();
    readerPage('<a href="#/library/documents">Founding documents</a>', d.title, String(d.year), d.paras, '', '<p class="attrib">Text: the Avalon Project at Yale Law School and Wikisource (public domain).</p>');
  }
  function renderStatute(S, id) {
    const s = S.find(x => x.id === id);
    if (!s) return viewNotFound();
    readerPage('<a href="#/library/statutes">Acts of the First Congresses</a>', s.title, `${ordinal(s.cong)} Congress, ${ordinal(s.sess)} Session, ${esc(s.chap)}${s.date ? ' · ' + esc(s.date) : ''} · 1 Stat.`, s.paras, '',
      `<p class="attrib">Text: <i>United States Statutes at Large</i>, vol. 1, transcribed on Wikisource (public domain).</p>`);
  }

  /* ------------------------------------------------------------ quizzes */
  // Multiple-choice quiz: answer each question to see whether you're right and why; best score kept locally.
  function quizHtml(key, qs, title, blurb) {
    if (!qs || !qs.length) return '';
    const best = localStorage.getItem('cl-quiz-' + key);
    return `<section class="quiz" data-quiz="${esc(key)}">
      <div class="quiz-h"><div><span class="eyebrow">Check your understanding</span><h2>${esc(title)}</h2><p>${esc(blurb)}</p></div>
        <div class="quiz-score" aria-live="polite">${best != null ? `Best: ${best}/${qs.length}` : `${qs.length} questions`}</div></div>
      <ol class="quiz-list"></ol>
      <div class="quiz-result" hidden></div>
    </section>`;
  }
  function mountQuiz(root, key, qs) {
    const el = root.querySelector(`[data-quiz="${CSS.escape(key)}"]`);
    if (!el) return;
    const list = el.querySelector('.quiz-list'), result = el.querySelector('.quiz-result'), scoreEl = el.querySelector('.quiz-score');
    const shuffle = a => { const b = a.slice(); for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
    let answered = 0, correct = 0;
    const render = () => {
      answered = 0; correct = 0; result.hidden = true;
      list.innerHTML = qs.map((q, qi) => `<li class="quiz-q" data-q="${qi}">
        <p class="quiz-text">${esc(q.q)}</p>
        <div class="quiz-opts">${shuffle(q.o.map((o, i) => [o, i])).map(([o, i]) => `<button class="quiz-opt" data-i="${i}"><span class="quiz-mark"></span>${esc(o)}</button>`).join('')}</div>
        <div class="quiz-exp" hidden></div>
      </li>`).join('');
    };
    render();
    list.addEventListener('click', e => {
      const btn = e.target.closest('.quiz-opt'); if (!btn) return;
      const li = btn.closest('.quiz-q'); if (li.classList.contains('done')) return;
      const q = qs[+li.dataset.q], pick = +btn.dataset.i, ok = pick === q.a;
      li.classList.add('done', ok ? 'right' : 'wrong');
      li.querySelectorAll('.quiz-opt').forEach(b => { b.disabled = true; const i = +b.dataset.i; if (i === q.a) b.classList.add('is-correct'); else if (i === pick) b.classList.add('is-wrong'); });
      const exp = li.querySelector('.quiz-exp'); exp.hidden = false;
      exp.innerHTML = `<b>${ok ? 'Correct.' : 'Not quite.'}</b> ${esc(q.e || '')}`;
      answered++; if (ok) correct++;
      scoreEl.textContent = `${correct}/${answered} correct`;
      if (answered === qs.length) {
        const prev = +(localStorage.getItem('cl-quiz-' + key) ?? -1);
        if (correct > prev) localStorage.setItem('cl-quiz-' + key, correct);
        const pct = Math.round(100 * correct / qs.length);
        result.hidden = false;
        result.innerHTML = `<div><b>${correct} of ${qs.length}</b> · ${pct}%</div><span>${pct === 100 ? 'Perfect score.' : pct >= 70 ? 'Solid. Review the explanations for the ones you missed.' : 'Worth another read of the section above, then try again.'}</span><button class="btn btn-ghost btn-sm" data-retake>Retake quiz</button>`;
        result.querySelector('[data-retake]').addEventListener('click', () => { render(); scoreEl.textContent = `${qs.length} questions`; el.scrollIntoView({ behavior: 'smooth' }); });
      }
    });
  }

  function viewNotFound() {
    app.innerHTML = `<div class="prose fade-in"><h1>Not found</h1><p>That page doesn't exist in the index. <a href="#/">Return home</a>.</p></div>`;
  }

  function bindPager(fn) {
    app.querySelectorAll('.pager button[data-page]').forEach(b => b.addEventListener('click', () => { if (!b.disabled) fn(+b.dataset.page); }));
  }

  /* ------------------------------------------------------------ router */
  function route() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, qs] = raw.split('?');
    const params = new URLSearchParams(qs || '');
    const seg = path.split('/');
    routeToken++;
    const navKey = { docket: 'scotus', impact: 'search', library: 'corner', doctrine: 'guide', case: 'scotus', article: 'search', author: 'search', topics: 'search', book: 'books' }[seg[0]] || seg[0] || 'home';
    document.querySelectorAll('.topnav a[data-nav]').forEach(a => a.classList.toggle('active', a.dataset.nav === navKey));
    document.querySelectorAll('audio').forEach(a => a.pause());
    const top = document.getElementById('topsearch-input');
    if (navKey === 'search') top.value = params.get('q') || ''; else if (navKey !== 'search') top.value = '';
    switch (seg[0]) {
      case '': case undefined: viewHome(); break;
      case 'topics': viewTopics(); break;
      case 'search': viewSearch(params); break;
      case 'article': viewArticle(decodeURIComponent(seg.slice(1).join('/'))); break;
      case 'author': viewAuthor(seg.slice(1).join('/'), params); break;
      case 'journals': viewJournals(); break;
      case 'saved': viewSaved(); break;
      case 'impact': viewImpact(params); break;
      case 'scotus': viewScotus(params); break;
      case 'docket': viewDocket(params); break;
      case 'case': viewCase(decodeURIComponent(seg.slice(1).join('/'))); break;
      case 'lectures': viewLectures(params); break;
      case 'books': viewBooks(params); break;
      case 'book': viewBook(decodeURIComponent(seg[1] || '')); break;
      case 'guide': seg[1] ? viewGuideTopic(seg[1]) : viewGuide(); break;
      case 'doctrine': viewDoctrine(seg[1], seg[2]); break;
      case 'corner': seg[1] ? viewCornerTopic(seg[1], params) : viewCorner(); break;
      case 'library': viewLibrary(seg, params); break;
      case 'about': viewAbout(); break;
      default: viewNotFound();
    }
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  /* ------------------------------------------------------------ global wiring */
  app.addEventListener('click', e => {
    const b = e.target.closest('.save-btn');
    if (b) { e.preventDefault(); toggleSave(b.dataset.id); return; }
    const v = e.target.closest('.vtile');
    if (v) { e.preventDefault(); openVideo(v.dataset.video, v.dataset.title, v.dataset.ch); }
  });
  // Open Library serves a 1×1 image when it has no cover; swap in the typographic fallback
  document.addEventListener('load', e => {
    const img = e.target;
    if (img.tagName === 'IMG' && img.classList.contains('cover') && img.naturalWidth < 10) img.dispatchEvent(new Event('error'));
  }, true);
  document.getElementById('topsearch').addEventListener('submit', e => {
    e.preventDefault();
    location.hash = hashFor('search', { q: document.getElementById('topsearch-input').value.trim() });
  });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !/input|textarea|select/i.test(document.activeElement.tagName)) {
      e.preventDefault(); document.getElementById('topsearch-input').focus();
    }
  });
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = t; localStorage.setItem('cl-theme', t);
  });
  document.getElementById('footer-updated').textContent = 'Updated ' + DATA.generated;
  window.addEventListener('hashchange', route);
  persistSaved();
  route();
})();
