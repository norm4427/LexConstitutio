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
          <a class="feature" href="#/guide"><span class="f-icon">◎</span><b>Beginner's guide</b><span>Twenty core topics, each with an overview, explainer videos, landmark cases and first readings.</span><em>Start learning →</em></a>
          <a class="feature" href="#/scotus"><span class="f-icon">⚖</span><b>Supreme Court</b><span>Case summaries, opinion PDFs, and oral arguments you can play here with a synced transcript.</span><em>Browse decisions →</em></a>
          <a class="feature" href="#/lectures"><span class="f-icon">▶</span><b>Lecture library</b><span>Lectures and debates from law schools, universities and constitutional institutions.</span><em>Watch lectures →</em></a>
          <a class="feature" href="#/impact"><span class="f-icon">↗</span><b>Impact rankings</b><span>The most-cited constitutional scholarship, by topic, decade and journal.</span><em>See rankings →</em></a>
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
        <h1>Topics</h1><p>Five areas and ${topics.filter(t => t.parent).length} subtopics. Topics are assigned automatically from each article's title, abstract, and subject keywords, so an article can sit under more than one.</p></div>
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
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span>${crumbs}</div><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ''}</div>
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
      .catch(e => { app.innerHTML = `<div class="prose"><h1>Couldn't load this section</h1><p>${esc(e.message)}</p></div>`; });
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

  /* ------------------------------------------------------------ impact */
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
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Impact</span></div>
        <h1>Most influential articles</h1>
        <p>Ranked by citations recorded in <a href="https://openalex.org" target="_blank" rel="noopener" style="color:var(--accent)">OpenAlex</a>, an open index of scholarly literature. ${fmt(citedCount)} of ${fmt(articles.length)} articles have citation data. The percentile badge compares an article with others from the same decade, so older work doesn't automatically dominate.</p></div>
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
        <p>${fmt(S.cases.length)} cases with summaries, opinion PDFs, and oral argument audio you can play here, with a transcript that follows along. Summaries and audio come from <a href="https://www.oyez.org" target="_blank" rel="noopener" style="color:var(--accent)">Oyez</a>. Opinions come from supremecourt.gov and the Library of Congress.</p></div>
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
  function viewCase(id) { withData([['scotus', 'SCOTUS']], S => renderCase(S, id)); }
  function renderCase(S, id) {
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const c = caseById.get(id);
    if (!c) return viewNotFound();
    const caseName = c.n.toLowerCase().replace(/\s*\(\d\)$/, '');
    const relatedArticles = caseName.length < 10 ? [] : articles.filter(a => a._t.includes(caseName) || a._ab.includes(caseName))
      .sort((x, y) => (y.c ?? -1) - (x.c ?? -1)).slice(0, 6);
    app.innerHTML = `<div class="fade-in"><div class="article">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a>${c.y ? `<span>/</span><a href="${hashFor('scotus', { era: (ERAS.find(e => c.y >= e.from && c.y < e.to) || {}).id })}">${c.y}</a>` : ''}</div>
        <h1>${esc(c.n)}</h1>
        <div class="publine">${c.cit ? esc(c.cit) + ' · ' : ''}${c.dec ? 'Decided ' + esc(fmtDate(c.dec)) : 'Term ' + esc(c.t)}${c.d ? ' · No. ' + esc(c.d) : ''}</div>
        ${c.ds ? `<div class="abstract plain">${esc(c.ds)}</div>` : ''}
        <div class="actions">
          ${c.pdf ? `<a class="btn btn-primary" href="${esc(c.pdf)}" target="_blank" rel="noopener">Opinion PDF ↗</a>` : ''}
          ${c.tr ? `<a class="btn btn-ghost" href="${esc(c.tr)}" target="_blank" rel="noopener">Argument transcript PDF ↗</a>` : ''}
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
      const dec = (d.decisions || [])[0];
      if (dec && dec.majority_vote != null) document.getElementById('case-vote').innerHTML = `<div class="vote"><b>${dec.majority_vote}–${dec.minority_vote}</b><span>${dec.winning_party ? 'for ' + esc(dec.winning_party) : 'decision'}</span></div>`;
      const ops = (d.written_opinion || []).filter(o => o && o.type);
      if (ops.length) {
        const p = document.getElementById('case-opinions'); p.hidden = false;
        p.querySelector('ul').innerHTML = ops.map(o => `<li><a class="t" href="${esc(o.justia_opinion_url || c.ju || '#')}" target="_blank" rel="noopener">${esc(o.type.label)}</a><div class="m">${esc(o.judge_full_name || 'Per curiam')}</div></li>`).join('');
      }
      const media = [...(d.oral_argument_audio || []).map(m => ({ ...m, kind: 'Oral argument' })), ...(d.opinion_announcement || []).map(m => ({ ...m, kind: 'Opinion announcement' }))].filter(m => m && m.href && !m.unavailable);
      if (media.length) mountAudio(document.getElementById('case-audio'), media, c);
    }).catch(() => {
      if (token !== routeToken) return;
      document.getElementById('case-live').innerHTML = `${c.q ? `<h2>Question</h2><div class="prose-sm"><p>${esc(c.q)}</p></div>` : ''}<p class="muted-line">Live details from Oyez are unavailable right now. <a href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Open on Oyez ↗</a></p>`;
    });
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
      fetch(m.href).then(r => r.json()).then(x => {
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
          ${turns.length ? `<div class="transcript" id="transcript">${turns.map((t, i) => `<div class="turn ${t.j ? 'justice' : ''}" data-i="${i}" data-s="${t.s}"><div class="turn-h"><b>${esc(t.sp)}</b><span>${fmtTime(t.s)}</span></div><p>${esc(t.tx)}</p></div>`).join('')}</div>` : '<p class="muted-line" style="padding:0 18px 18px">No synchronized transcript for this recording.</p>'}`;
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
  function videoTile(v) {
    return `<button class="vtile" data-video="${esc(v.id)}" data-title="${esc(v.t)}" data-ch="${esc(v.ch)}">
      <span class="vthumb"><img loading="lazy" src="https://i.ytimg.com/vi/${esc(v.id)}/hqdefault.jpg" alt=""><span class="vlen">${esc(v.len || '')}</span><span class="vplay">▶</span></span>
      <span class="vt">${esc(v.t)}</span>
      <span class="vm">${esc(v.ch)}${v.v ? ' · ' + compact(v.v) + ' views' : ''}</span>
    </button>`;
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
  function viewGuide() { withData([['guide', 'GUIDE']], G => renderGuide(G)); }
  function renderGuide(G) {
    const groups = [...new Set(G.topics.map(t => t.group))];
    app.innerHTML = `<div class="fade-in">
      <section class="hero guide-hero"><div class="hero-inner" style="padding:64px 24px 54px">
        <span class="eyebrow">Start here</span>
        <h1 style="max-width:18ch">The essential guide to <em>constitutional law.</em></h1>
        <p class="lede">${G.topics.length} core topics, each with a plain-English overview, short explainer videos, the landmark Supreme Court cases, and a handful of readable law review articles to go deeper.</p>
      </div></section>
      ${groups.map(g => `<section class="section" style="padding-top:44px">
        <div class="section-head"><div><h2>${esc(g)}</h2></div></div>
        <div class="guide-grid">${G.topics.filter(t => t.group === g).map((t, i) => `<a class="guide-card" href="#/guide/${t.id}">
          ${t.videos[0] ? `<span class="guide-thumb"><img loading="lazy" src="https://i.ytimg.com/vi/${esc(t.videos[0].id)}/mqdefault.jpg" alt=""></span>` : ''}
          <span class="guide-body"><b>${esc(t.title)}</b><span>${esc(t.tagline)}</span>
          <span class="guide-meta">${t.videos.length} videos · ${t.cases.length} cases · ${(t.books || []).length} book${(t.books || []).length === 1 ? '' : 's'} · ${t.articles.length} readings</span></span>
        </a>`).join('')}</div>
      </section>`).join('')}
    </div>`;
  }
  function viewGuideTopic(id) { withData([['guide', 'GUIDE'], ['scotus', 'SCOTUS'], ['books', 'BOOKS']], (G, S, B) => renderGuideTopic(G, S, id, B)); }
  function renderGuideTopic(G, S, id, B) {
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const i = G.topics.findIndex(t => t.id === id);
    const t = G.topics[i];
    if (!t) return viewNotFound();
    const prev = G.topics[i - 1], next = G.topics[i + 1];
    const arts = t.articles.map(x => byId.get(x)).filter(Boolean);
    const [main, ...more] = t.videos;
    app.innerHTML = `<div class="fade-in"><div class="article guide-page">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/guide">Guide</a><span>/</span><span>${esc(t.group)}</span></div>
        <h1>${esc(t.title)}</h1>
        <p class="guide-tagline">${esc(t.tagline)}</p>
        ${t.wiki ? `<div class="explainer">
          <div class="explainer-h"><span>The short version</span><a href="${esc(t.wiki.url)}" target="_blank" rel="noopener">Wikipedia: ${esc(t.wiki.title)} ↗</a></div>
          <p>${esc(t.wiki.text)}</p>
          <div class="explainer-f">Text from Wikipedia, licensed CC BY-SA 4.0.${t.wex ? ` For a legal-dictionary definition, see <a href="${esc(t.wex)}" target="_blank" rel="noopener">Cornell LII Wex ↗</a>` : ''}</div>
        </div>` : ''}
        ${main ? `<h2>Watch</h2>
          <div class="embed"><iframe loading="lazy" src="${embedSrc(main.id)}" title="${esc(main.t)}" allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>
          <div class="embed-cap"><b>${esc(main.t)}</b> · ${esc(main.ch)} · ${esc(main.len)}</div>
          ${more.length ? `<div class="vgrid small" style="margin-top:16px">${more.map(v => videoTile(v)).join('')}</div>` : ''}` : ''}
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
        <div class="panel"><h4>All guide topics</h4><ul class="mini-list toc">${G.topics.map(x => `<li><a class="t ${x.id === id ? 'cur' : ''}" href="#/guide/${x.id}">${esc(x.title)}</a></li>`).join('')}</ul></div>
      </aside>
    </div></div>`;
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
    const navKey = { case: 'scotus', article: 'search', author: 'search', topics: 'search', book: 'books' }[seg[0]] || seg[0] || 'home';
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
      case 'case': viewCase(decodeURIComponent(seg.slice(1).join('/'))); break;
      case 'lectures': viewLectures(params); break;
      case 'books': viewBooks(params); break;
      case 'book': viewBook(decodeURIComponent(seg[1] || '')); break;
      case 'guide': seg[1] ? viewGuideTopic(seg[1]) : viewGuide(); break;
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
