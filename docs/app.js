/* Lex Constitutio: client-side index of constitutional law review articles.
   Data comes from data/articles.js (window.CL_DATA), built by scripts/build.ps1. */
(function () {
  'use strict';

  const DATA = window.CL_DATA;
  const app = document.getElementById('app');
  if (!DATA) {
    app.innerHTML = '<div class="prose"><h1>No data yet</h1><p>The article index could not be loaded. Please try again later.</p></div>';
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
    const dd = document.getElementById('saved-count-dd');
    if (dd) dd.textContent = saved.size;
  }
  function toggleSave(id) {
    if (saved.has(id)) { saved.delete(id); toast('Removed from your list'); }
    else { saved.add(id); toast('Saved to your list'); }
    persistSaved();
    document.querySelectorAll(`.save-btn[data-id="${CSS.escape(id)}"]`).forEach(b => b.classList.toggle('on', saved.has(id)));
  }

  /* ------------------------------------------------------------ read articles (newest first, in this browser) */
  const READ_KEY = 'cl-read';
  let readList = []; try { readList = JSON.parse(localStorage.getItem(READ_KEY) || '[]'); } catch (e) {}
  let readSet = new Set(readList);
  function persistRead() {
    localStorage.setItem(READ_KEY, JSON.stringify(readList));
    readSet = new Set(readList);
    const el = document.getElementById('read-count');
    if (el) el.textContent = readList.length;
    const sc = document.getElementById('saved-count-dd');
    if (sc) sc.textContent = saved.size;
  }
  function toggleRead(id) {
    if (readSet.has(id)) { readList = readList.filter(x => x !== id); toast('Marked as unread'); }
    else { readList = [id, ...readList]; toast('Marked as read'); }
    persistRead();
    document.querySelectorAll(`.read-btn[data-id="${CSS.escape(id)}"]`).forEach(b => {
      b.classList.toggle('on', readSet.has(id));
      b.title = b.ariaLabel = readSet.has(id) ? 'Mark as unread' : 'Mark as read';
      const c = b.closest('.card'); if (c) c.classList.toggle('read', readSet.has(id));
    });
  }

  /* ------------------------------------------------------------ helpers */
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => n.toLocaleString('en-US');
  // counts quoted in the site's descriptions (data/site-stats.js, written by scripts/site_stats.py)
  const SS = window.SITE_STATS || {};
  const stat = (k, dflt) => (SS[k] != null ? SS[k] : dflt);
  const about = n => n >= 1000 ? fmt(Math.floor(n / 100) * 100) : fmt(n);
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
    const cset = st.clause && window.CLAUSE_ARTS ? new Set(window.CLAUSE_ARTS.ids[st.clause] || []) : null;
    const out = [];
    for (const a of articles) {
      if (st.unread && readSet.has(a.id)) continue;
      if (jset && !jset.has(a.j)) continue;
      if (cset && !cset.has(a.id)) continue;
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
  const checkSvg = '<svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
  function card(a, pq) {
    const H = pq ? (s => highlight(s, pq)) : esc;
    const tags = a.tp.map(t => topicById[t] ? `<a class="tag" href="${hashFor('search', { topic: t })}">${esc(topicById[t].name)}</a>` : '').join('');
    const rd = readSet.has(a.id);
    return `<article class="card${rd ? ' read' : ''}">
      <button class="save-btn ${saved.has(a.id) ? 'on' : ''}" data-id="${esc(a.id)}" title="Save to my list" aria-label="Save to my list">${bookmarkSvg}</button>
      <button class="read-btn ${rd ? 'on' : ''}" data-id="${esc(a.id)}" title="${rd ? 'Mark as unread' : 'Mark as read'}" aria-label="${rd ? 'Mark as unread' : 'Mark as read'}">${checkSvg}</button>
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
        <span class="eyebrow">Constitutional law, from the founding to today</span>
        <h1>The Constitution, its cases and its scholars, <em>in one place.</em></h1>
        <p class="lede">Search ${fmt(articles.length)} law review articles from ${journals.length} journals, read ${about(stat('cases', 29000))} Supreme Court decisions with summaries, opinions and argument audio, learn the doctrine topic by topic, and go back to what the founding generation actually said.</p>
        <form class="bigsearch" id="bigsearch">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          <input id="bigsearch-input" type="search" placeholder='Try "unitary executive" or Amar' autocomplete="off" aria-label="Search the index">
          <button class="btn btn-primary" type="submit">Search</button>
        </form>
        <div class="suggest"><span>Popular:</span>${SUGGESTIONS.map(s => `<a class="chip" href="${hashFor('search', { q: s })}">${esc(s)}</a>`).join('')}</div>
        <div class="stats">
          <div class="stat"><b>${fmt(articles.length)}</b><span>Articles</span></div>
          <div class="stat"><b>${fmt(stat('cases', 0))}</b><span>Supreme Court cases</span></div>
          <div class="stat"><b>${fmt(stat('libraryWorks', 0))}</b><span>Full texts in the library</span></div>
          <div class="stat"><b>${journals.length}</b><span>Law reviews</span></div>
        </div>
      </div></section>

      <section class="section">
        <div class="features">
          <a class="feature" href="#/scotus"><span class="f-icon">⚖</span><b>Supreme Court</b><span>${about(stat('cases', 29000))} decisions since ${stat('firstYear', 1791)}: summaries, opinions, argument audio with a transcript that follows along, the authorities cited, the parties and advocates, media coverage and predicted outcomes for pending cases.</span><em>Browse decisions →</em></a>
          <a class="feature" href="#/guide"><span class="f-icon">◎</span><b>Beginner's Guide</b><span>${stat('guideTopics', 20)} core topics with plain-English overviews, videos and lectures, then ${stat('doctrineSections', 50)} sections of advanced doctrine with the tests and excerpts from the opinions.</span><em>Start learning →</em></a>
          <a class="feature" href="#/corner"><span class="f-icon">❦</span><b>Originalist's Corner</b><span>What the founding generation said about each part of the Constitution: Blackstone, the Convention, <i>The Federalist</i> and the Anti-Federalists, the first Congresses and the early commentators, side by side.</span><em>Read the sources →</em></a>
          <a class="feature" href="#/library"><span class="f-icon">❧</span><b>Library</b><span>${stat('libraryWorks', 29)} full texts to read, highlight and annotate: founding-era treatises and pamphlets, later historical documents, the <i>Constitution Annotated</i> and ${fmt(stat('crsSidebars', 1400))} CRS Legal Sidebars.</span><em>Open the library →</em></a>
          <a class="feature" href="#/books"><span class="f-icon">❐</span><b>Books</b><span>${stat('books', 290)} books on constitutional law, history and the Court, ${stat('essentialBooks', 73)} of them marked essential, with law review book reviews.</span><em>Browse books →</em></a>
          <a class="feature" href="#/quiz"><span class="f-icon">✎</span><b>Learning Center</b><span>Flashcards on ${fmt(stat('flashcards', 1700))} cases and terms with spaced review, quizzes on every guide topic, and games.</span><em>Start studying →</em></a>
          <a class="feature" href="#/impact"><span class="f-icon">↗</span><b>Most influential articles</b><span>The most-cited constitutional scholarship, by topic, decade and journal.</span><em>See rankings →</em></a>
          <a class="feature" href="#/search"><span class="f-icon">⌕</span><b>Articles</b><span>${fmt(articles.length)} articles from ${journals.length} law reviews, tagged by topic and constitutional clause, with citation counts.</span><em>Search the index →</em></a>
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
      clause: params.get('clause') || '',
      j: (params.get('j') || '').split(',').filter(Boolean),
      from: +params.get('from') || 0,
      to: +params.get('to') || 0,
      sort: params.get('sort') || '',
      unread: params.get('unread') === '1' ? 1 : 0,
      page: Math.max(1, +params.get('page') || 1)
    };
  }
  function viewSearch(params) {
    const st = readSearchState(params);
    // filtering by a constitutional clause needs the clause tags (loaded on first use)
    if (st.clause && !window.CLAUSE_ARTS) return loadData('clause-articles', 'CLAUSE_ARTS').then(() => viewSearch(params)).catch(() => toast('The clause filter could not be loaded.'));
    const clauseName = st.clause && window.CLAUSE_ARTS ? window.CLAUSE_ARTS.names[st.clause] : '';
    const { results, pq, sort } = runSearch(st);
    const page = Math.min(st.page, Math.max(1, Math.ceil(results.length / PAGE_SIZE)));
    const slice = results.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const go = patch => { location.hash = hashFor('search', Object.assign({}, st, { page: 1 }, patch)); };
    const t = topicById[st.topic];
    const hasQ = pq.terms.length || pq.phrases.length;

    let title = 'Browse the index', sub = `${fmt(articles.length)} constitutional law articles from ${journals.length} law reviews and specialist journals, tagged by topic and clause, with citation counts and links to the full text.`, crumbs = '';
    if (clauseName && !t && !hasQ) {
      title = clauseName; sub = 'Articles about this clause: their title or subject keywords concern it, or their abstract names it.';
      crumbs = `<a href="#/corner/constitution">The Annotated Constitution</a><span>/</span><a href="${hashFor('corner/constitution', { c: st.clause })}">${esc(clauseName)}</a><span>/</span><span>Articles</span>`;
    } else if (t) {
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
    if (clauseName) chips.push(`<button class="chip on" data-clear="clause">${esc(clauseName)} <span class="x">✕</span></button>`);
    if (t) chips.push(`<button class="chip on" data-clear="topic">${esc(t.name)} <span class="x">✕</span></button>`);
    for (const j of st.j) chips.push(`<button class="chip on" data-clear-j="${esc(j)}">${esc(journalById[j]?.name || j)} <span class="x">✕</span></button>`);
    if (st.unread) chips.push(`<button class="chip on" data-clear="unread">Unread only <span class="x">✕</span></button>`);
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
            <label class="unread-toggle" title="Hide articles you have marked as read"><input type="checkbox" id="unread-only"${st.unread ? ' checked' : ''}> Unread only${readList.length ? '' : ' <span class="muted-line">(none marked read yet)</span>'}</label>
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
      const k = b.dataset.clear; go(k === 'years' ? { from: 0, to: 0 } : k === 'unread' ? { unread: 0 } : { [k]: '' });
    }));
    app.querySelectorAll('[data-clear-j]').forEach(b => b.addEventListener('click', () => go({ j: st.j.filter(x => x !== b.dataset.clearJ) })));
    app.querySelectorAll('[data-years]').forEach(b => b.addEventListener('click', () => { const [f, t2] = b.dataset.years.split('-'); go({ from: +f || 0, to: +t2 || 0 }); }));
    const yr = () => go({ from: +document.getElementById('from').value || 0, to: +document.getElementById('to').value || 0 });
    document.getElementById('from').addEventListener('change', yr);
    document.getElementById('to').addEventListener('change', yr);
    document.getElementById('filter-toggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
    document.getElementById('unread-only').addEventListener('change', e => go({ unread: e.target.checked ? 1 : 0 }));
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
        <h2>${a.abx ? 'Summary' : 'Abstract'}</h2>
        ${a.ab ? `<div class="abstract">${esc(a.ab)}</div>${a.abx ? `<p class="attrib" style="color:var(--ink-3);font-size:13px">From the piece's page on ${esc(j?.name || 'the journal')}'s website.</p>` : ''}` : '<p style="color:var(--ink-3)">No abstract is available for this article. Open the full text at the publisher.</p>'}
        <div class="actions">
          ${a.pdf ? `<a class="btn btn-primary" href="${esc(a.pdf)}" target="_blank" rel="noopener">Read the PDF ↗</a>` : ''}
          ${!a.pdf && a.oa ? `<a class="btn btn-primary" href="${esc(a.oa)}" target="_blank" rel="noopener" title="${a.oav === 'publishedVersion' ? 'The published version' : 'An author\'s version (manuscript), which may differ from the published text'}">Free copy at ${esc(a.oa.replace(/^https?:\/\/(www\.)?/, '').split('/')[0])}${a.oav && a.oav !== 'publishedVersion' ? ' (author\'s version)' : ''} ↗</a>` : ''}
          <a class="btn ${a.pdf || a.oa ? 'btn-ghost' : 'btn-primary'}" href="${esc(a.u)}" target="_blank" rel="noopener">${/doi\.org\/10\.2307/.test(a.u) ? 'View on JSTOR' : /doi\.org/.test(a.u) ? 'View via DOI' : 'View at ' + esc(j?.name || 'publisher')} ↗</a>
          ${a.pub ? `<a class="btn btn-ghost" href="${esc(a.pub)}" target="_blank" rel="noopener">View at ${esc(j?.name || 'the publisher')} ↗</a>` : ''}
          <button class="btn btn-ghost" id="save-article">${saved.has(a.id) ? '★ Saved' : '☆ Save to my list'}</button>
          <button class="btn btn-ghost" id="read-article">${readSet.has(a.id) ? '✓ Read' : 'Mark as read'}</button>
          <a class="btn btn-ghost" href="https://scholar.google.com/scholar?q=${encodeURIComponent('"' + a.t + '"')}" target="_blank" rel="noopener">Google Scholar ↗</a>
        </div>
        ${a.tp.length ? `<h2>Topics</h2><div class="tags">${a.tp.map(t => `<a class="tag" href="${hashFor('search', { topic: t })}">${esc(topicById[t]?.parent ? topicById[topicById[t].parent].name + ' › ' : '')}${esc(topicById[t]?.name)}</a>`).join('')}</div>` : ''}
        ${a.kw.length ? `<h2>Keywords</h2><div class="tags">${a.kw.map(k => `<a class="tag" href="${hashFor('search', { q: '"' + k + '"' })}">${esc(k)}</a>`).join('')}</div>` : ''}
        <div id="art-ftcites" hidden></div>
        ${rel.length ? `<h2>Related articles</h2><div class="cards">${rel.map(b => card(b)).join('')}</div>` : ''}
      </div>
      <aside>
        <div class="panel" id="art-mentions" hidden><h4>Mentioned in this article</h4><div class="art-mentions-body"></div></div>
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
    document.getElementById('read-article').addEventListener('click', e => { toggleRead(a.id); e.currentTarget.textContent = readSet.has(a.id) ? '✓ Read' : 'Mark as read'; });
    articleMentions(a);
    articleWorksCited(a);
  }
  // Supreme Court cases and indexed articles named in an article's title, abstract and keywords (the full text sits behind
  // the repositories' download protection, so it is not scanned)
  let artTitleIdx = null, landmarkShort = null;
  // precomputed links between articles and cases (scripts/build_crosslinks.py): one file per journal / per year
  const loadXL = (kind, key) => loadData('xl-index', 'XL_INDEX').catch(() => null)
    .then(ix => ix && (ix[kind] || []).includes(String(key)) ? loadScriptOnce(`data/xl/${kind}/${key}.js`).catch(() => {}) : null)
    .then(r => r === null ? null : (window[kind === 'art' ? 'XL_ART' : 'XL_CASE'] || {}));   // null: no index file to read
  // works cited / cases cited / cited by, read from the articles' footnotes (scripts/fulltext_cites.py): one file per decade
  // for articles (an article's own record also lists the articles citing it), one per year for cases
  const loadFT = (kind, key) => loadData('ft-index', 'FT_INDEX').catch(() => null)
    .then(ix => ix && (ix[kind] || []).includes(String(key)) ? loadScriptOnce(`data/ft/${kind}-${key}.js`).catch(() => {}) : null)
    .then(r => r === null ? null : (window[kind === 'art' ? 'FT_ART' : 'FT_CASE'] || {}));
  function articleWorksCited(a) {
    const token = routeToken;
    Promise.all([loadFT('art', Math.floor((a.y || 0) / 10) * 10), loadData('scotus', 'SCOTUS')]).then(([F, S]) => {
      const r = F && F[a.id], el = document.getElementById('art-ftcites');
      if (!r || !el || token !== routeToken) return;
      if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
      const cited = (r.a || []).map(([id, n]) => [byId.get(id), n]).filter(([b]) => b && b !== a);
      const cases = (r.c || []).map(([id, n]) => [caseById.get(id), n]).filter(([c]) => c);
      const by = (r.b || []).map(id => byId.get(id)).filter(b => b && b !== a);
      if (!cited.length && !cases.length && !by.length) return;
      const times = n => `<div class="muted-line" style="font-size:12px;margin:4px 2px 0">Cited ${n} times in the footnotes</div>`;
      const more = (id, n) => n > 0 ? `<p class="muted-line" style="font-size:13px"><button class="btn btn-ghost btn-sm" data-more="${id}">Show ${fmt(n)} more</button></p>` : '';
      const cardsOf = (xs, id, max) => `<div class="cards">${xs.slice(0, max).map(([b, n]) => n > 1 ? `<div>${card(b)}${times(n)}</div>` : card(b)).join('')}</div><div id="${id}-rest" hidden><div class="cards">${xs.slice(max).map(([b, n]) => n > 1 ? `<div>${card(b)}${times(n)}</div>` : card(b)).join('')}</div></div>` + more(id, xs.length - max);
      el.hidden = false;
      el.innerHTML = (cited.length ? `<h2>Works cited</h2><p class="muted-line" style="font-size:13px;margin:-4px 0 10px">${fmt(cited.length)} article${cited.length === 1 ? '' : 's'} in this index, of ${fmt(r.n || 0)} law review citation${r.n === 1 ? '' : 's'} in the footnotes.</p>${cardsOf(cited, 'ft-cited', 6)}` : '')
        + (cases.length ? `<h2>Cases cited</h2><ul class="mini-list">${cases.slice(0, 15).map(([c]) => precedentItem(c)).join('')}</ul>${cases.length > 15 ? `<div id="ft-cases-rest" hidden><ul class="mini-list">${cases.slice(15).map(([c]) => precedentItem(c)).join('')}</ul></div>${more('ft-cases', cases.length - 15)}` : ''}` : '')
        + (by.length ? `<h2>Cited by</h2><p class="muted-line" style="font-size:13px;margin:-4px 0 10px">${fmt(by.length)} later article${by.length === 1 ? '' : 's'} in this index cite${by.length === 1 ? 's' : ''} this one in ${by.length === 1 ? 'its' : 'their'} footnotes.</p>${cardsOf(by.map(b => [b, 0]), 'ft-by', 6)}` : '')
        + `<p class="attrib">Taken from the footnotes of the free full texts linked on this site.</p>`;
      el.querySelectorAll('[data-more]').forEach(b => b.addEventListener('click', () => { const x = document.getElementById(b.dataset.more + '-rest'); if (x) x.hidden = false; b.closest('p').remove(); }));
    }).catch(() => {});
  }
  const OPINION_KIND = { majority: 'Majority opinion', opinion: 'Opinions (the source does not separate majority and dissent)', concurrence: 'Concurrence', dissent: 'Dissent', separate: 'Separate opinion' };
  const normWords = t => t.toLowerCase().replace(/[’']/g, '').replace(/[^a-z0-9 ]+/g, ' ').split(/\s+/).filter(Boolean);
  function articleMentions(a) {
    const token = routeToken;
    const text = [a.t, a.ab || '', (a.kw || []).join('; ')].join(' . ');
    Promise.all([loadData('scotus', 'SCOTUS'), loadData('case_impact', 'CASE_IMPACT'), loadData('essential', 'ESSENTIAL'), loadXL('art', a.j)]).then(([S, I, E, XA]) => {
      if (token !== routeToken) return;
      if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
      const xl = (XA && XA[a.id]) || {};
      const byCite = new Map(S.cases.filter(c => c.cit).map(c => [c.cit, c]));
      const cases = new Map();
      for (const m of text.matchAll(/\b(\d{1,3}) U\.\s?S\. (\d{1,4})\b/g)) { const c = byCite.get(`${m[1]} U.S. ${m[2]}`); if (c) cases.set(c.id, c); }
      citedCases(S, text, null).forEach(c => cases.set(c.id, c));
      // landmark cases are often named by one party alone ("After Dobbs", "post-Bruen")
      if (!landmarkShort) {
        const STOP = new Set('United States State Board City County Department Commission Federal National American New People Bank Company Corporation Ex Parte Re In The Town School Village Trustees Railroad Pennsylvania Virginia California Texas Ohio Florida Georgia Alabama Arizona Kansas Michigan Missouri Nebraska Louisiana Maryland Massachusetts Minnesota Mississippi Montana Nevada Oklahoma Oregon Tennessee Washington Wisconsin Colorado Connecticut Illinois Indiana Iowa Kentucky Carolina Jersey York Hampshire Island Dakota Mexico Arkansas Delaware Hawaii Idaho Maine Utah Vermont Wyoming Alaska Thomas Kennedy Jackson Harlan Marshall Stevens Scalia Roberts Alito Gorsuch Kavanaugh Barrett Sotomayor Kagan Ginsburg Breyer Souter Brennan Rehnquist Burger Warren Black Douglas Frankfurter Holmes Brandeis Taft Story Taney Field Miller Johnson Smith Brown Jones Williams Davis Wilson Allen Martin Moore Hill Lee Young Clark Lewis White Gray Green Hall Wood Ward Ross Morgan'.split(' '));
        const ess = new Set(E);
        const top = S.cases.filter(c => /\sv\.\s/.test(c.n) && (ess.has(c.id) || I.c[c.id])).sort((x, y) => ess.has(y.id) - ess.has(x.id) || (I.c[y.id] || [0, 0, 0])[2] - (I.c[x.id] || [0, 0, 0])[2]).slice(0, ess.size + 200);
        const count = new Map(), pick = new Map();
        for (const c of top) {
          // the petitioner's name, or the respondent's when the petitioner is generic ("New York State Rifle ... v. Bruen")
          const ok = w => w && (w.length >= 4 || w === 'Roe') && !STOP.has(w);
          const [p1, p2] = c.n.replace(/\s*\(\d\)$/, '').split(/\s+v\.\s+/).map(x => (x.replace(/^(?:The|In re|Ex parte)\s+/, '').match(/^([A-Z][a-z’']+)/) || [])[1]);
          const w = ok(p1) ? p1 : ok(p2) && c.n.split(/\s+v\.\s+/)[1].trim().split(/\s+/).length <= 2 ? p2 : null;
          if (!w) continue;
          count.set(w, (count.get(w) || 0) + 1);
          if (!pick.has(w)) pick.set(w, c);
        }
        landmarkShort = [...pick].filter(([w]) => count.get(w) === 1).map(([w, c]) => [new RegExp(String.raw`(?<!Justice |Judge |Professor )\b` + w + String.raw`(?![\w’'-]| v\.)`), c]);
      }
      const authors = (a.a || []).join(' ');
      for (const [rx, c] of landmarkShort) if (!cases.has(c.id) && rx.test(text) && !rx.test(authors)) cases.set(c.id, c);
      if (!artTitleIdx) {
        artTitleIdx = new Map();
        for (const b of articles) {
          const w = normWords(b.t);
          if (w.length < 5 || w.filter(x => !/^(a|an|the|of|and|in|on|to|for|is|as|at|by|or|from|with)$/.test(x)).length < 3) continue;
          const k = w.slice(0, 4).join(' ');
          if (!artTitleIdx.has(k)) artTitleIdx.set(k, []);
          artTitleIdx.get(k).push([w, b]);
        }
      }
      const words = normWords(a.ab || ''), arts = new Map();
      for (let i = 0; i + 4 <= words.length; i++) for (const [w, b] of artTitleIdx.get(words.slice(i, i + 4).join(' ')) || []) if (b !== a && w.every((x, k) => words[i + k] === x)) arts.set(b.id, b);
      if (XA) { cases.clear(); for (const [cid] of xl.c || []) { const c = caseById.get(cid); if (c) cases.set(c.id, c); } }   // the index (every article was read), strongest first; the regex matching above only when it cannot load
      for (const bid of xl.aa || []) { const b = byId.get(bid); if (b && b !== a) arts.set(b.id, b); }
      const court = (xl.cb || []).map(([cid, k]) => [caseById.get(cid), k]).filter(([c]) => c);
      const el = document.getElementById('art-mentions');
      if (!el || (!cases.size && !arts.size && !court.length)) return;
      el.hidden = false;
      el.querySelector('.art-mentions-body').innerHTML = (court.length ? `<div class="prec-h">Cited by the Supreme Court</div><ul class="mini-list">${court.map(([c, k]) => `<li><a class="t" href="#/case/${esc(c.id)}">${esc(c.n)}</a><div class="m">${c.cit ? esc(c.cit) + ' · ' : ''}${c.y || ''}${OPINION_KIND[k] ? ' · ' + OPINION_KIND[k] : ''}</div></li>`).join('')}</ul><p class="muted-line" style="font-size:12px;margin:4px 0 10px">Law review citations in the opinions (Caselaw Access Project, to about 2020).</p>` : '')
        + (cases.size ? `<div class="prec-h">Supreme Court cases</div><ul class="mini-list">${[...cases.values()].map(precedentItem).join('')}</ul>` : '')
        + (arts.size ? `<div class="prec-h" style="margin-top:10px">Law review articles</div><ul class="mini-list">${[...arts.values()].map(b => `<li><a class="t" href="${articleHref(b)}">${esc(b.t)}</a><div class="m">${esc(journalById[b.j]?.name || '')}${b.y ? ' · ' + b.y : ''}</div></li>`).join('')}</ul>` : '')
        + (cases.size || arts.size ? `<p class="muted-line" style="font-size:12px;margin:10px 0 0">Found in the ${XA ? 'title, abstract and keywords, strongest first' : 'title and abstract'}.</p>` : '');
    }).catch(() => {});
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
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/search">Articles</a><span>/</span><span>Journals</span></div>
        <h1>Journal directory</h1><p>${journals.length} law reviews currently indexed. Specialist journals contribute every article. General law reviews contribute only articles about constitutional law.</p>${articleTabs('journals')}</div>
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

  function viewSaved(params) {
    const tab = params && params.get('tab') === 'read' ? 'read' : 'saved';
    const tabs = `<div class="seg mylist-tabs" role="tablist" aria-label="My list"><a role="tab" href="#/saved" class="${tab === 'saved' ? 'on' : ''}">Saved <span class="n">${saved.size}</span></a><a role="tab" href="#/saved?tab=read" class="${tab === 'read' ? 'on' : ''}">Read <span class="n">${readList.length}</span></a></div>`;
    const head = `<div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>My list</span></div>
        <h1>My list</h1><p>${tab === 'read' ? 'Articles you have marked as read, most recent first.' : 'Articles you have saved.'} Stored in this browser only.</p>${tabs}</div>`;
    if (tab === 'read') {
      const items = readList.map(id => byId.get(id)).filter(Boolean);
      app.innerHTML = `<div class="fade-in">${head}
        <div class="layout" style="grid-template-columns:1fr"><div>
          ${items.length ? `<div class="toolbar"><div class="count"><b>${items.length}</b> article${items.length === 1 ? '' : 's'} read</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-ghost btn-sm" id="clear-read">Clear read history</button></div></div>
            <div class="cards">${items.map(a => card(a)).join('')}</div>`
          : `<div class="empty"><h3>Nothing marked as read yet</h3><p>Use the check button on any article, or “Mark as read” on its page, to keep track of what you have read. In Articles you can then show only unread ones.</p><p style="margin-top:18px"><a class="btn btn-primary" href="#/search">Browse articles</a></p></div>`}
        </div></div></div>`;
      const c = document.getElementById('clear-read');
      if (c) c.addEventListener('click', () => { if (!confirm('Clear your read history?')) return; readList = []; persistRead(); viewSaved(params); });
      return;
    }
    const items = [...saved].map(id => byId.get(id)).filter(Boolean);
    app.innerHTML = `<div class="fade-in">${head}
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
      saved = new Set(); persistSaved(); viewSaved(params);
    });
  }

  function viewAbout() {
    app.innerHTML = `<div class="fade-in"><div class="prose">
      <div class="crumbs"><a href="#/">Home</a><span>/</span><span>About</span></div>
      <h1>About Lex Constitutio</h1>
      <p>Lex Constitutio brings together the materials of American constitutional law. It began as a topic-organized index of constitutional law scholarship, in the spirit of PhilPapers: ${fmt(articles.length)} articles from ${journals.length} law reviews, collected from the publicly available metadata (titles, authors, abstracts and subject keywords) in their repositories. Around it are ${fmt(stat('cases', 29000))} Supreme Court decisions, a beginner's guide and advanced doctrine, the Originalist's Corner and its library of ${stat('libraryWorks', 29)} full texts, ${stat('books', 290)} books, and a learning center with flashcards, quizzes and games. Articles and books remain with their publishers: follow the links to read them.</p>
      <h2>How articles are collected</h2>
      <p>Many journals publish through institutional repositories that expose an open <a href="https://www.openarchives.org/pmh/" target="_blank" rel="noopener">OAI-PMH</a> feed. A few others publish through public WordPress APIs. Articles from specialist journals (<em>Constitutional Commentary</em>, <em>Hastings Constitutional Law Quarterly</em>, the <em>William &amp; Mary Bill of Rights Journal</em>) are all included. From general law reviews, an article is included if:</p>
      <ul><li>the repository tags it with a constitutional law discipline, or</li><li>its title names a constitutional provision, doctrine, or institution, or</li><li>its abstract does so more than once.</li></ul>
      <h2>How topics are assigned</h2>
      <p>Each article is matched against the vocabulary of each subtopic. A match in the title counts most, then the subject keywords, then the abstract. An article receives up to four topics. The tagging is automatic, so expect some imperfect matches.</p>
      <h2>Coverage</h2>
      <table><thead><tr><th>Journal</th><th>Articles</th></tr></thead><tbody>
        ${journals.slice().sort((a, b) => b.count - a.count).map(j => `<tr><td>${esc(j.name)}</td><td>${fmt(j.count)}</td></tr>`).join('')}
      </tbody></table>
      <p>The <em>Harvard</em>, <em>Yale</em>, <em>Columbia</em>, <em>Virginia</em>, <em>California</em>, <em>Penn</em>, <em>Stanford</em>, and <em>Georgetown</em> law reviews block automated access to their own websites. Their articles are indexed from <a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a> metadata instead, and link to the article through its DOI (usually JSTOR) or the journal's site. Coverage of Georgetown in OpenAlex is thin. Older volumes may lack abstracts. Index last updated ${esc(DATA.generated)}.</p>
      <h2>Citations and impact</h2>
      <p>Citation counts come from OpenAlex and are available for ${fmt(citedCount)} articles. The percentile compares an article with others in the index published in the same decade. OpenAlex sometimes credits a reviewed book's citations to its review. Titles that appear in more than one journal are treated as book reviews and left unranked. Law review citation data is less complete than in the sciences, so treat the counts as a rough guide.</p>
      <h2>Advanced doctrine</h2>
      <p>The advanced half of the Beginner's Guide is an original doctrinal treatment written for this site. It is organized after the chapter structure of Erwin Chemerinsky's <em>Constitutional Law: Principles and Policies</em> and covers judicial power, legislative and executive power, federalism, state action, due process, economic liberties, equal protection, fundamental rights, speech and religion. Excerpts from opinions are public-domain text extracted from the official <em>United States Reports</em> (Library of Congress) and supremecourt.gov slip opinions, or from Wikisource transcriptions. The open casebooks at opencasebook.org (H2O, CC BY-NC-SA) are cited as further reading.</p>
      <p>The in-depth commentary in each section comes from the <em>Constitution of the United States of America: Analysis and Interpretation</em> ("Constitution Annotated"), prepared by the Congressional Research Service of the Library of Congress. The site uses the 2022 GPO edition, a public-domain U.S. government work. Essays appear without their footnotes.</p>
      <h2>Originalist's Corner and the library</h2>
      <p>The Originalist's Corner collects what the founding generation and the early commentators said about each part of the Constitution, for anyone who wants to read the Constitution as it was understood when it was adopted, and for its critics. It indexes the full texts of Blackstone's <em>Commentaries</em>, St. George Tucker's annotated Blackstone, Joseph Story's <em>Commentaries on the Constitution</em>, James Kent's <em>Commentaries</em>, Vattel's <em>Law of Nations</em> and Locke's <em>Two Treatises</em> (via the Lonang Institute). It also covers <em>The Federalist</em> (Project Gutenberg), Madison's Notes of the Convention debates and founding documents (the Avalon Project at Yale Law School), and the acts of the first five Congresses (<em>Statutes at Large</em>, vol. 1, via Wikisource). Passages are sorted by topic and should be read in context. The library holds ${stat('libraryWorks', 29)} full texts to read, highlight and take notes on (kept in your browser): <em>The Federalist</em>, the founding documents and the early statutes; the treatises, pamphlets, debates and state papers of the founding era from Wikisource (CC BY-SA), Project Gutenberg (public domain) and the Text Creation Partnership's transcriptions of early American and English imprints (CC0); later historical documents; and the <em>Constitution Annotated</em> and ${fmt(stat('crsSidebars', 1400))} Legal Sidebars of the Congressional Research Service (U.S. government works).</p>
      <h2>Supreme Court, lectures and guide</h2>
      <p>Case summaries, oral argument audio and synchronized transcripts come from <a href="https://www.oyez.org" target="_blank" rel="noopener">Oyez</a> (text licensed <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener">CC BY-NC 4.0</a>; flashcard and summary text is excerpted or adapted). Oyez is a registered trademark of Oyez, Inc. Vote splits and each justice’s vote come from the <a href="http://scdb.wustl.edu/" target="_blank" rel="noopener">Supreme Court Database</a> (Harold J. Spaeth et al., Version 2026 Release 01 and Legacy 07), and for later decisions from the lineup in the Court’s own opinion. The same database supplies the pre-1955 cases that Oyez does not cover, and the justice ratings, Statistics tables and vote models are calculated from it (ideal-point scores from <a href="https://mqscores.quantitative.emory.edu/" target="_blank" rel="noopener">Martin and Quinn</a>). Opinion PDFs link to supremecourt.gov for recent terms and to the Library of Congress's <em>United States Reports</em> collection for older ones. Lecture and explainer videos are embedded from the YouTube channels of the institutions that published them. Guide overviews are drawn from Wikipedia (CC BY-SA 4.0), with links to Cornell LII's Wex.</p>
    </div></div>`;
  }

  /* ------------------------------------------------------------ lazy data */
  const loading = {};
  function loadData(name, globalName) {
    if (window[globalName]) return Promise.resolve(window[globalName]);
    if (!loading[name]) loading[name] = new Promise((res, rej) => {
      const s = document.createElement('script'); s.src = `data/${name}.js?v=${window.LC_VER || ""}`;
      s.onload = () => res(globalName === 'SCOTUS' ? scdbLinks(window[globalName]) : window[globalName]); s.onerror = () => { delete loading[name]; rej(new Error(`Couldn't load data/${name}.js`)); };
      document.body.appendChild(s);
    });
    return loading[name];
  }
  /* Cases added from the Supreme Court Database (s: 1, scripts/add_scdb_cases.py) carry only the citation; the
     Library of Congress U.S. Reports PDF (vols. 1-576) and Justia links follow from it, as in build_extras.pl. */
  function scdbLinks(S) {
    for (const c of (S && S.cases) || []) {
      if (c.s !== 1 || !c.cit) continue;
      const m = c.cit.match(/^(\d+) U\.S\. (\d+)$/);
      if (!m) continue;
      const v = +m[1], p = +m[2], k = `usrep${String(v).padStart(3, '0')}${String(p).padStart(3, '0')}`;
      if (v <= 576) c.pdf = `https://tile.loc.gov/storage-services/service/ll/usrep/usrep${String(v).padStart(3, '0')}/${k}/${k}.pdf`;
      c.ju = `https://supreme.justia.com/cases/federal/us/${v}/${p}/`;
    }
    return S;
  }
  /* Ratings, vote models and the Statistics tab live in app-stats.js, loaded on first use. */
  let extLoading = null;
  function ext() {
    window.LC_API = window.LC_API || { esc, fmt, hashFor, withData, loadData, scotusTabs };
    if (window.LCX) return Promise.resolve(window.LCX);
    if (!extLoading) extLoading = new Promise((res, rej) => {
      const s = document.createElement('script'); s.src = `app-stats.js?v=${window.LC_VER || ''}`;
      s.onload = () => res(window.LCX); s.onerror = () => { extLoading = null; rej(new Error("Couldn't load app-stats.js")); };
      document.body.appendChild(s);
    });
    return extLoading;
  }
  let routeToken = 0;
  function withData(specs, fn) {
    const token = routeToken;
    if (!specs.every(([, g]) => window[g])) app.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading…</p></div>';
    Promise.all(specs.map(([n, g]) => loadData(n, g)))
      .then(ds => { if (token === routeToken) { fn(...ds); if (pendingScroll != null) { const yy = pendingScroll; pendingScroll = null; requestAnimationFrame(() => window.scrollTo({ top: Math.min(yy, document.documentElement.scrollHeight - innerHeight) })); } } })
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
      <a href="#/journals" class="${active === 'journals' ? 'on' : ''}">Journals</a>
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
    { id: 'hughes', name: 'Hughes, Stone & Vinson Courts', from: 1930, to: 1953 },
    { id: 'fuller', name: 'Fuller, White & Taft Courts', from: 1888, to: 1930 },
    { id: 'taney', name: 'Taney, Chase & Waite Courts', from: 1836, to: 1888 },
    { id: 'marshall', name: 'Jay through Marshall Courts', from: 0, to: 1836 },
    { id: 'early', name: 'Before 1953', from: 0, to: 1953, hide: true }   // kept for older links
  ];
  let caseById = null;
  function viewScotus(params) { withData([['scotus', 'SCOTUS'], ['case_impact', 'CASE_IMPACT']], (S, I) => renderScotus(S, params, I)); }
  function renderScotus(S, params, I) {
    const st = { q: params.get('q') || '', tag: params.get('tag') || '', era: params.get('era') || '', audio: params.get('audio') === '1', con: params.get('con') === '1', sort: params.get('sort') || 'newest', page: Math.max(1, +params.get('page') || 1) };
    const pq = parseQuery(st.q);
    const era = ERAS.find(e => e.id === st.era);
    const filt = (skipTag) => S.cases.filter(c => {
      if (era && !(c.y >= era.from && c.y < era.to)) return false;
      if (st.audio && !hasArgAudio(c)) return false;
      if (st.con && !c.con) return false;
      if (!skipTag && st.tag && !(c.tg || []).includes(st.tag)) return false;
      if (pq.terms.length || pq.phrases.length) {
        const hay = (c.n + ' ' + (c.q || '') + ' ' + (c.ds || '') + ' ' + (c.h || '') + ' ' + (c.d || '') + ' ' + (c.cit || '')).toLowerCase();
        if (!pq.terms.every(t => hay.includes(t)) || !pq.phrases.every(p => hay.includes(p))) return false;
      }
      return true;
    });
    const list = filt(false);
    const imp = id => (I && I.c[id]) || null;
    if (st.sort === 'oldest') list.reverse();
    else if (st.sort === 'cited') list.sort((a, b) => ((imp(b.id) || [0, 0, -1])[2] - (imp(a.id) || [0, 0, -1])[2]) || ((imp(b.id) || [0])[0] - (imp(a.id) || [0])[0]));
    const tagCounts = {}; for (const c of filt(true)) for (const t of c.tg || []) tagCounts[t] = (tagCounts[t] || 0) + 1;
    const page = Math.min(st.page, Math.max(1, Math.ceil(list.length / PAGE_SIZE)));
    const slice = list.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const go = patch => { const s = Object.assign({}, st, { page: 1 }, patch); location.hash = hashFor('scotus', { q: s.q, tag: s.tag, era: s.era, audio: s.audio ? 1 : '', con: s.con ? 1 : '', sort: s.sort !== 'newest' ? s.sort : '', page: s.page > 1 ? s.page : '', v: s.v }); };
    const tagName = t => topicById[t]?.name || t;
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Supreme Court</span></div>
        <h1>Supreme Court decisions</h1>
        <p>${fmt(S.cases.length)} decisions since ${stat('firstYear', 1791)}. About ${fmt(Math.round(S.cases.filter(c => c.s !== 1).length / 100) * 100)} have <a href="https://www.oyez.org" target="_blank" rel="noopener" style="color:var(--accent)">Oyez</a>'s summary and the question presented, with oral argument audio you can play here and a transcript that follows along. The rest, mostly from before 1955, come from the <a href="http://scdb.wustl.edu/" target="_blank" rel="noopener" style="color:var(--accent)">Supreme Court Database</a> with their citation, votes and opinion, the reporter's headnotes or the official syllabus from the <i>U.S. Reports</i>, and for ${fmt(stat('aiBriefs', 300))} landmark cases a case brief written by AI and labelled as such. Case pages add the authorities the briefs rely on, the parties and advocates, coverage in the media and, for pending cases, a predicted outcome. Opinions come from supremecourt.gov and the Library of Congress.</p>${scotusTabs('decided')}</div>
      <div class="layout">
        <aside class="sidebar" id="sidebar">
          <div class="side-block"><h4>Search cases</h4><form id="sc-form"><input class="input" id="sc-q" type="search" value="${esc(st.q)}" placeholder="Case name, issue, docket…"></form></div>
          <div class="side-block"><h4>Show</h4>
            <label class="check"><input type="checkbox" id="sc-audio" ${st.audio ? 'checked' : ''}> Argued cases (audio)</label>
            <label class="check"><input type="checkbox" id="sc-con" ${st.con ? 'checked' : ''}> Constitutional questions</label>
          </div>
          <div class="side-block"><h4>Court</h4><ul class="tree">
            <li><a href="#" data-era="" class="${!st.era ? 'on' : ''}"><span>All eras</span></a></li>
            ${ERAS.filter(e => !e.hide).map(e => `<li><a href="#" data-era="${e.id}" class="${st.era === e.id ? 'on' : ''}"><span>${e.name}</span><span class="n">${e.to === 9999 ? e.from + '–' : e.from ? e.from + '–' + e.to : ''}</span></a></li>`).join('')}
          </ul></div>
          <div class="side-block"><h4>Area</h4><ul class="tree">
            <li><a href="#" data-tag="" class="${!st.tag ? 'on' : ''}"><span>All areas</span></a></li>
            ${Object.entries(tagCounts).sort((a, b) => b[1] - a[1]).map(([t, n]) => `<li><a href="#" data-tag="${t}" class="${st.tag === t ? 'on' : ''}"><span>${esc(tagName(t))}</span><span class="n">${fmt(n)}</span></a></li>`).join('')}
          </ul></div>
        </aside>
        <div>
          <div class="toolbar"><div class="count"><button class="btn btn-ghost btn-sm filter-toggle" id="filter-toggle">Filters</button> <span id="sc-count"><b>${fmt(list.length)}</b> case${list.length === 1 ? '' : 's'}</span></div>
            <div class="sc-tools"><div class="seg" role="group" aria-label="Sort">
              <button data-sort="newest" class="${st.sort === 'newest' ? 'on' : ''}">Newest</button>
              <button data-sort="oldest" class="${st.sort === 'oldest' ? 'on' : ''}">Oldest</button>
              <button data-sort="cited" class="${st.sort === 'cited' ? 'on' : ''}" title="Cited most often by later Supreme Court opinions">Most cited</button>
            </div></div></div>
          ${st.sort === 'cited' ? '<p class="muted-line" style="margin:-4px 0 12px">Ranked by how many later Supreme Court opinions cite each case (Caselaw Access Project, Harvard Law School Library; its data runs to about 2020). Decisions since October 2019 are counted from <a href="https://www.courtlistener.com/" target="_blank" rel="noopener" style="color:var(--accent)">CourtListener</a> (Free Law Project).</p>' : ''}
          ${slice.length ? `<div class="cards">${slice.map(c => caseCard(c, imp(c.id))).join('')}</div>` : '<div class="empty"><h3>No cases found</h3><p>Try fewer keywords or another era.</p></div>'}
          ${pager(list.length, page, 'scotus')}
        </div>
      </div></div>`;
    document.getElementById('sc-form').addEventListener('submit', e => { e.preventDefault(); go({ q: document.getElementById('sc-q').value.trim() }); });
    document.getElementById('sc-audio').addEventListener('change', e => go({ audio: e.target.checked }));
    document.getElementById('sc-con').addEventListener('change', e => go({ con: e.target.checked }));
    app.querySelectorAll('[data-era]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); go({ era: a.dataset.era }); }));
    app.querySelectorAll('[data-tag]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); go({ tag: a.dataset.tag }); }));
    document.getElementById('filter-toggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
    app.querySelectorAll('[data-sort]').forEach(b => b.addEventListener('click', () => go({ sort: b.dataset.sort })));
    bindPager(n => go({ page: n }));
  }
  const topPct = m => { const v = (1 - m[1]) * 100; return v < 0.1 ? v.toFixed(2) : v.toFixed(1); };
  const impactTitle = m => m[3] ? `Cited in ${fmt(m[2])} later Supreme Court opinion${m[2] === 1 ? '' : 's'} (CourtListener citation data; decided after the Caselaw Access Project's data ends, so no PageRank)` : `Cited in ${fmt(m[2])} later Supreme Court opinion${m[2] === 1 ? '' : 's'}; citation PageRank in the top ${topPct(m)}% of American cases (Caselaw Access Project)`;
  function caseCard(c, m) {
    const summary = c.ds || c.h || c.q || '';
    return `<article class="card case-card">
      <div class="card-meta">${c.cit ? `<span class="jn">${esc(c.cit)}</span>` : ''}${c.dec ? `<span>Decided ${esc(fmtDate(c.dec))}</span>` : `<span>Term ${esc(c.t)}</span>`}${c.d ? `<span>No. ${esc(c.d)}</span>` : ''}${m ? `<span class="cites" title="${esc(impactTitle(m))}">${citeIcon}${fmt(m[2])}</span>` : ''}</div>
      <h3><a href="#/case/${esc(c.id)}">${esc(c.n)}</a></h3>
      ${summary ? `<p class="abs">${esc(summary)}</p>` : ''}
      <div class="tags">${hasArgAudio(c) ? '<span class="tag tag-audio">▶ Argument audio</span>' : ''}${c.pdf ? '<span class="tag">Opinion PDF</span>' : ''}${c.tr ? '<span class="tag">Transcript PDF</span>' : ''}${(c.tg || []).slice(0, 3).map(t => `<a class="tag" href="${hashFor('scotus', { tag: t })}">${esc(topicById[t]?.name || t)}</a>`).join('')}</div>
    </article>`;
  }
  /* ---- current docket */
  function scotusTabs(active) {
    return `<div class="subtabs"><a href="#/docket" class="${active === 'docket' ? 'on' : ''}">Current docket</a><a href="#/scotus" class="${active === 'decided' ? 'on' : ''}">Decided cases</a><a href="#/justices" class="${active === 'justices' ? 'on' : ''}">Justices</a><a href="#/statutes" class="${active === 'statutes' ? 'on' : ''}">Statutes</a><a href="#/stats" class="${active === 'stats' ? 'on' : ''}">Statistics</a></div>`;
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

  function viewCase(id, params) {
    withData([['scotus', 'SCOTUS'], ['docket', 'DOCKET'], ['case_impact', 'CASE_IMPACT']], (S, K, I) => {
      // the Authorities index is optional: the case page renders without it
      const tk = routeToken;
      Promise.all([loadData('auth-index', 'AUTH_INDEX').catch(() => null), loadData('parties-index', 'PARTIES_INDEX').catch(() => null), loadData('media-index', 'MEDIA_INDEX').catch(() => null)])
        .then(([AI]) => { if (tk === routeToken) renderCase(S, id, K, I, AI, params); });
    });
  }
  /* Authorities tab data: one file per docket (scripts/build_authorities.py) */
  const authLoading = {};
  function loadAuth(dk) {
    window.AUTH = window.AUTH || {};
    if (window.AUTH[dk]) return Promise.resolve(window.AUTH[dk]);
    if (!authLoading[dk]) authLoading[dk] = new Promise((res, rej) => {
      const s = document.createElement('script'); s.src = `data/auth/${encodeURIComponent(dk)}.js?v=${window.LC_VER || ''}`;
      s.onload = () => window.AUTH[dk] ? res(window.AUTH[dk]) : rej(new Error('No authorities data'));
      s.onerror = () => { delete authLoading[dk]; rej(new Error(`Couldn't load the authorities for No. ${dk}`)); };
      document.body.appendChild(s);
    });
    return authLoading[dk];
  }
  const BRIEF_SHORT = { petitioner: 'Pet.', respondent: 'Resp.', reply: 'Reply', 'united-states': 'U.S.' };
  const briefName = b => ({ petitioner: "Petitioner's brief", respondent: "Respondent's brief", reply: 'Reply brief', 'united-states': 'Brief of the United States' }[b.k] || 'Brief');
  function briefTiles(briefs) {
    return `<div class="briefs">${briefs.map(b => `<a class="brief" href="${esc(b.url)}" target="_blank" rel="noopener"><b>${esc(BRIEF_LABEL[b.k] || briefName(b))}</b><span>${esc(b.label)}</span><em>${b.date ? esc(fmtDate(b.date)) + ' · ' : ''}${esc(b.fmt || 'PDF')} ↗</em></a>`).join('')}</div>`;
  }
  // where a case's briefs come from: the Supreme Court docket (e-filed, from about 2017) and/or the Solicitor General's archive
  const briefSource = A => {
    const src = A.src || ['docket'];
    const parts = [];
    if (src.includes('docket')) parts.push(`the <a href="https://www.supremecourt.gov/docket/docketfiles/html/public/${esc(A.d)}.html" target="_blank" rel="noopener" style="color:var(--accent)">Supreme Court docket for No. ${esc(A.d)}</a>`);
    if (src.includes('osg')) parts.push(`the <a href="https://www.justice.gov/osg/supreme-court-briefs" target="_blank" rel="noopener" style="color:var(--accent)">Office of the Solicitor General’s brief archive</a>, which holds only the federal government’s briefs, those before about 2004 as OCR text of the printed brief`);
    return parts.join(' and ');
  };
  /* AI-generated case briefs (scripts/build_ai_briefs.py) for cases with no Oyez summary: the one place the site shows
     generated text, always under an unmistakable notice; quotations in them were checked against the opinion. */
  /* The reporter's headnotes from the U.S. Reports (Caselaw Access Project scan), for cases with no Oyez summary. */
  function headnotes(el, c) {
    const slot = document.createElement('div');
    el.appendChild(slot);
    const y = String(c.y || ''), tk = routeToken;
    // data/headnotes (build_headnotes.py) and data/summaries (case_summaries.py, holes the first left) share the format
    const year = (ixName, ixVar, dir) => loadData(ixName, ixVar).catch(() => []).then(ix => (ix || []).includes(y) ? loadScriptOnce(`data/${dir}/${y}.js`).catch(() => {}) : null);
    Promise.all([year('headnotes-index', 'HEADNOTES_INDEX', 'headnotes'), year('summaries-index', 'SUMMARIES_INDEX', 'summaries')]).then(() => (window.HEADNOTES || {})[c.id]).then(h => {
      if (!h || tk !== routeToken || !slot.isConnected) return;
      if (h.src === 'wiki') {
        slot.innerHTML = `<section class="headnotes" aria-label="Summary from Wikipedia"><h2>Summary <small>from Wikipedia</small></h2>
          <div class="prose-sm">${h.h.split('\n').map(p => `<p>${esc(p)}</p>`).join('')}</div>
          <p class="attrib">The opening of the Wikipedia article “<a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.t)}</a>”${h.rev ? ` (<a href="https://en.wikipedia.org/w/index.php?oldid=${esc(h.rev)}" target="_blank" rel="noopener">revision ${esc(h.rev)}</a>)` : ''}, by its contributors, under <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>. Not an official summary: check it against the opinion.</p></section>`;
        return;
      }
      if (h.src === 'gpo') {
        slot.innerHTML = `<section class="headnotes" aria-label="Syllabus"><h2>Syllabus <small>from the United States Reports</small></h2>
          <div class="prose-sm">${h.h.split('\n').map(p => `<p>${esc(p)}</p>`).join('')}</div>
          <p class="attrib">The syllabus prepared by the Reporter of Decisions and printed with the opinion${h.cite ? ' at ' + esc(h.cite) : ''} (public domain; it is not part of the Court's opinion), from the <a href="${esc(h.url || 'https://www.govinfo.gov/app/collection/usreports')}" target="_blank" rel="noopener">U.S. Reports on GovInfo</a> (U.S. Government Publishing Office).</p></section>`;
        return;
      }
      if (h.src === 'cl') {
        const K = { syllabus: ['Syllabus', 'the syllabus printed with the opinion'], headnotes: ['Headnotes', 'the headnotes printed with the opinion'], summary: ['Summary', 'the case summary'], order: ['Order', 'the whole text of this short order or per curiam'], opening: ['Opening of the opinion', 'the opening of the Court’s opinion (no syllabus or headnote is available)'] }[h.kind] || ['Summary', 'the case text'];
        slot.innerHTML = `<section class="headnotes" aria-label="${esc(K[0])}"><h2>${esc(K[0])} <small>from CourtListener</small></h2>
          <div class="prose-sm">${h.h.split('\n').map(p => `<p>${esc(p)}</p>`).join('')}</div>
          <p class="attrib">${K[1][0].toUpperCase() + K[1].slice(1)}${h.cite ? ' at ' + esc(h.cite) : ''}, from <a href="${esc(h.url || 'https://www.courtlistener.com/')}" target="_blank" rel="noopener">CourtListener</a> (Free Law Project; court opinions are public domain and CourtListener's data is free of known copyright restrictions).${h.kind === 'opening' ? ' Not a summary: read the full opinion.' : ''}</p></section>`;
        return;
      }
      if (h.src === 'order') {
        slot.innerHTML = `<section class="headnotes" aria-label="Text of the order"><h2>Order <small>full text, from the United States Reports</small></h2>
          <div class="prose-sm"><p>${esc(h.h)}</p></div>
          <p class="attrib">The whole text of this short order or per curiam${h.cite ? ' at ' + esc(h.cite) : ''} (public domain; no syllabus was printed), from the <a href="https://case.law/" target="_blank" rel="noopener">Caselaw Access Project</a> (Harvard Law School Library). Read from page scans by OCR, so it may contain scanning errors.</p></section>`;
        return;
      }
      const syl = h.src === 'loc';
      slot.innerHTML = `<section class="headnotes" aria-label="${syl ? 'Syllabus' : "Reporter's headnotes"}"><h2>${syl ? 'Syllabus' : 'Headnotes'} <small>from the United States Reports</small></h2>
        <div class="prose-sm">${h.h.split('\n').map(p => `<p>${esc(p)}</p>`).join('')}</div>
        ${syl ? `<p class="attrib">The syllabus prepared by the Reporter of Decisions and printed with the opinion${h.cite ? ' at ' + esc(h.cite) : ''} (public domain; it is not part of the Court's opinion), read by OCR from the <a href="${esc(c.pdf || 'https://www.loc.gov/collections/united-states-reports/')}" target="_blank" rel="noopener">Library of Congress scan</a>, so it may contain scanning errors.</p>` : `<p class="attrib">The reporter's headnotes and statement of the case printed with the opinion${h.cite ? ' at ' + esc(h.cite) : ''} (public domain), from the <a href="https://case.law/" target="_blank" rel="noopener">Caselaw Access Project</a> (Harvard Law School Library). The text was read from page scans by OCR and may contain scanning errors.</p>`}</section>`;
    }).catch(() => {});
  }
  function aiBrief(el, c) {
    const dec = String(Math.floor((c.y || 0) / 10) * 10);
    const tk = routeToken;
    loadData('aibriefs-index', 'AIBRIEFS_INDEX').catch(() => []).then(ix => {
      if (!(ix || []).includes(dec)) return null;
      return loadScriptOnce(`data/aibriefs/${dec}.js`).then(() => (window.AIBRIEFS || {})[c.id]);
    }).then(b => {
      if (!b || tk !== routeToken || !el.isConnected) return;
      const sec = (h, t) => t ? `<h3>${h}</h3><p>${esc(t)}</p>` : '';
      el.insertAdjacentHTML('beforeend', `<section class="ai-brief" aria-label="AI-generated case brief">
        <div class="ai-warn" role="note"><b>AI-generated</b><span>This brief was written by an AI model (${esc(b.model || 'Claude')}) from the Court's opinion, not by Oyez or an editor. It may contain errors or omissions: rely on the <a href="${esc(b.src || c.pdf || '#')}" target="_blank" rel="noopener">opinion itself</a>. Quoted words were checked against the opinion text.</span></div>
        <h2>Case brief <small>(AI-generated)</small></h2>
        <div class="prose-sm">${sec('Facts', b.facts)}${sec('Procedural history', b.procedure)}${sec('Question', b.question)}${sec('Holding', b.holding)}${sec('Reasoning', b.reasoning)}${sec('Separate opinions', b.separate)}${sec('Disposition', b.disposition)}</div>
        <p class="attrib">Generated ${esc(b.date || '')} from the opinion PDF. AI-generated content; not legal advice.</p></section>`);
    }).catch(() => {});
  }
  /* "In the media": podcast and video episodes about the case (starting where the episode turns to it), other videos
     that name it, and newspaper pages printed after the decision (Chronicling America, public domain). */
  function renderMedia(el, M, c) {
    M = M || {};
    M.videos = M.videos || []; M.print = M.print || [];
    const clock = s => { s = Math.floor(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
    const ICON_BY_TAG = { speech: 'free-speech', religion: 'religion', guns: 'second-amendment', equality: 'equal-protection', dueprocess: 'due-process', crimpro: 'fourth-amendment', federalism: 'federalism', seppowers: 'separation-of-powers', admin: 'administrative-state', voting: 'voting', security: 'executive-power' };
    const iconKey = ICON_BY_TAG[(c.tg || [])[0]] || 'judicial-review';
    // embedded YouTube videos get the site's thumbnail tile; everything else, podcast audio included, is a compact
    // link to the episode's own page (nothing is played on this site that the publisher has not offered for embedding)
    const embedded = v => !!(v.id && v.embed);
    const tile = v => {
      const meta = [v.date ? fmtDate(v.date) : '', v.start ? `starts at ${clock(v.start)}` : ''].filter(Boolean).join(' · ');
      const thumb = videoThumb({ t: v.t, ch: v.ch, len: v.sec ? clock(v.sec) : '' }, iconKey);
      return `<div class="md-v"><button class="vtile" data-video="${esc(v.id)}" data-title="${esc(v.t)}" data-ch="${esc(v.ch)}" data-start="${v.start || 0}">${thumb}<span class="vm">${esc(meta)}</span></button>${v.topic ? `<p class="md-topic">Chapter: ${esc(v.topic)}</p>` : ''}</div>`;
    };
    const SHOW_HOME = { 'Advisory Opinions': 'https://thedispatch.com/podcast/advisoryopinions/', 'We the People': 'https://constitutioncenter.org/news-debate/podcasts',
      'More Perfect': 'https://www.wnycstudios.org/podcasts/radiolabmoreperfect', '5-4': 'https://www.fivefourpod.com/', 'Strict Scrutiny': 'https://crooked.com/podcast-series/strict-scrutiny/',
      'Divided Argument': 'https://www.dividedargument.com/' };
    const linkOf = v => v.id ? `https://www.youtube.com/watch?v=${encodeURIComponent(v.id)}${v.start ? '&t=' + v.start + 's' : ''}`
      : /^https?:\/\//.test(v.link || '') ? v.link : SHOW_HOME[v.ch] || '';
    const where = v => v.id ? 'YouTube' : /^https?:\/\//.test(v.link || '') ? v.link.replace(/^https?:\/\/(www\.)?/, '').split('/')[0] : SHOW_HOME[v.ch] ? 'the show’s site' : '';
    const row = v => { const L = linkOf(v); return `<li>${L ? `<a href="${esc(L)}" target="_blank" rel="noopener"><b>${esc(v.t)}</b></a>` : `<b>${esc(v.t)}</b>`}
      <span class="md-lm">${esc(v.ch)}${v.date ? ' · ' + esc(fmtDate(v.date)) : ''}${v.start ? ' · discussion starts at ' + clock(v.start) : ''}${v.sec ? ' · ' + clock(v.sec) : ''}${L ? ` · <a href="${esc(L)}" target="_blank" rel="noopener">${esc(where(v))} ↗</a>` : ''}</span>
      ${v.topic ? `<span class="md-topic">${esc(v.topic)}</span>` : ''}</li>`; };
    const isShow = v => v.kind === 'pod' || /Advisory Opinions|SCOTUSblog|Strict Scrutiny|Divided Argument/.test(v.ch || '');
    const shows = M.videos.filter(isShow), others = M.videos.filter(v => !isShow(v));
    const block = (list, h, note) => {
      const em = list.filter(embedded), ln = list.filter(v => !embedded(v)).sort((x, y) => (y.date || '').localeCompare(x.date || ''));
      return list.length ? `<h2>${h}</h2>${em.length ? `<div class="vgrid md-grid">${em.map(tile).join('')}</div>` : ''}${ln.length ? `<ul class="md-links">${ln.map(row).join('')}</ul>` : ''}${note ? `<p class="attrib">${note}</p>` : ''}` : '';
    };
    // reference pages built from the case's citation (Justia, Cornell LII, Oyez, CourtListener, the U.S. Reports at the
    // Library of Congress), plus the Wikipedia article and SCOTUSblog case file when the build found them
    const um = (c.cit || '').match(/^(\d+) U\.S\. (\d+)$/), sct = (c.cit || '').match(/^(\d+) S\. Ct\. (\d+)$/);
    const refs = [];
    if (M.sb) refs.push([M.sb, 'SCOTUSblog case file']);
    if (c.ju) refs.push([c.ju, 'Justia']);
    // LII keys recent cases by docket (its pages by citation stop around 541 U.S., 2004) and older ones by citation
    // (its docket pages before about 2000 are empty)
    const lDk = c.d && /^\d{2}-\d+$/.test(c.d.trim()) ? c.d.trim() : '', lYr = +String(c.y || c.t || c.date || '').slice(0, 4);
    const lii = lDk && (lYr >= 2000 || !um) ? lDk : um ? `${um[1]}/${um[2]}` : '';
    if (lii) refs.push([`https://www.law.cornell.edu/supremecourt/text/${lii}`, 'Cornell LII']);
    if (c.s !== 1 && !c.pending) refs.push([`https://www.oyez.org/cases/${c.id}`, 'Oyez']);
    if (um) refs.push([`https://www.courtlistener.com/c/U.S./${um[1]}/${um[2]}/`, 'CourtListener']);
    else if (sct) refs.push([`https://www.courtlistener.com/c/S.%20Ct./${sct[1]}/${sct[2]}/`, 'CourtListener']);
    if (c.pdf && /loc\.gov/.test(c.pdf)) refs.push([c.pdf, 'U.S. Reports (Library of Congress)']);
    if (M.wiki) refs.push([M.wiki, 'Wikipedia']);
    el.innerHTML = `<section class="md">
      ${block(shows, 'Podcasts and shows', '')}
      ${block(others, 'Videos', 'Videos whose titles name this case: embedded through YouTube’s player when the owner allows it, otherwise linked.')}
      ${refs.length ? `<h2>Case pages</h2><div class="md-refs">${refs.map(([u, label]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(label)} <span class="md-pw free">Free</span></a>`).join('')}</div>` : ''}
      ${(M.web || []).length ? `<h2>Coverage and commentary</h2>
        <p class="md-legend"><span class="md-pw pw">Paywall</span> subscription needed for most readers (some sites allow a few free articles a month) <span class="md-pw free">Free</span> free to read, as far as we know</p>
        <ul class="md-web">${M.web.map(w => `<li><a href="${esc(w.u)}" target="_blank" rel="noopener nofollow">${esc(w.t)} <span class="ext">↗</span></a><div><span class="md-pw ${w.pw ? 'pw' : 'free'}">${w.pw ? 'Paywall' : 'Free'}</span><b>${esc(w.o)}</b>${w.d ? `<span>${esc(w.d.length === 10 ? fmtDate(w.d) : w.d)}</span>` : ''}</div></li>`).join('')}</ul>
        <p class="attrib">News and analysis cited or linked in the case's ${M.wiki ? `<a href="${esc(M.wiki)}" target="_blank" rel="noopener">Wikipedia article</a>` : 'Wikipedia article'}, and Congressional Research Service reports that discuss the case, linked to the original publishers; nothing is copied. Paywall labels come from a list of outlets that require subscriptions and may not reflect each article.</p>` : ''}
      ${M.print.length ? `<h2>In the newspapers</h2><div class="md-print">${M.print.map(p => `<a class="md-clip" href="${esc(p.url)}" target="_blank" rel="noopener">${p.img ? `<img src="${esc(p.img)}" alt="Page of ${esc(p.paper)}, ${esc(p.date)}" loading="lazy">` : ''}<b>${esc(p.paper)}</b><span>${esc(fmtDate(p.date))}${p.page ? ' · page ' + p.page : ''}</span><em>View the page ↗</em></a>`).join('')}</div>
        <p class="attrib">Newspaper pages printed in the weeks after the decision that name both parties and the Supreme Court, from <a href="https://www.loc.gov/collections/chronicling-america/" target="_blank" rel="noopener">Chronicling America</a> (Library of Congress; public domain). Search the page for the case name to find the story.</p>` : ''}
    </section>`;
  }
  const scriptLoading = {};
  function loadScriptOnce(src) {
    if (!scriptLoading[src]) scriptLoading[src] = new Promise((res, rej) => {
      const s = document.createElement('script'); s.src = `${src}?v=${window.LC_VER || ''}`;
      s.onload = res; s.onerror = () => { delete scriptLoading[src]; rej(new Error(`Couldn't load ${src}`)); };
      document.body.appendChild(s);
    });
    return scriptLoading[src];
  }
  /* The Parties & advocates tab: the parties as the docket and Oyez name them, who argued (the transcript's appearances
     page, or Oyez), and counsel of record on the briefs (docket). */
  function renderParties(el, P, d, c, pend) {
    const SIDE = { pet: "Petitioner's side", res: "Respondent's side", other: 'Amici curiae and others' };
    const lab = (x, dflt) => esc(x || dflt);
    const parties = [];
    if (d && (d.first_party || d.second_party)) parties.push(['Oyez', `<dl class="kv pa-kv"><dt>${lab(d.first_party_label, 'Petitioner')}</dt><dd>${esc(d.first_party || '—')}</dd><dt>${lab(d.second_party_label, 'Respondent')}</dt><dd>${esc(d.second_party || '—')}</dd>${d.lower_court && d.lower_court.name ? `<dt>Lower court</dt><dd>${esc(d.lower_court.name)}</dd>` : ''}</dl>`]);
    const title = (P && P.title) || (pend && pend.title);
    const lower = (P && P.lower) || (pend && pend.lower);
    if (title || lower) parties.push(['the Supreme Court docket', `<dl class="kv pa-kv">${title ? `<dt>Case title</dt><dd>${esc(title)}</dd>` : ''}${lower && !(d && d.lower_court) ? `<dt>Lower court</dt><dd>${esc(lower)}</dd>` : ''}</dl>`]);
    const argued = P && P.argued && P.argued.length ? P.argued.map(a => ({ name: a.name, desc: a.desc, side: a.side, src: 'tr' }))
      : ((d && d.advocates) || []).filter(a => a && a.advocate).map(a => ({ name: a.advocate.name, desc: a.advocate_description || '', side: /petitioner|appellant/i.test(a.advocate_description || '') ? 'pet' : /respondent|appellee/i.test(a.advocate_description || '') ? 'res' : 'other', src: 'oyez' }));
    const counsel = (P && P.counsel) || [];
    const bySide = k => counsel.filter(x => x.side === k);
    const person = x => `<li><b>${esc(x.name)}</b>${x.cor ? ' <span class="tag">Counsel of record</span>' : ''}${x.org ? `<span>${esc(x.org)}</span>` : ''}${x.party ? `<em>for ${esc(x.party)}</em>` : ''}</li>`;
    el.innerHTML = `<section class="pa">
      ${parties.length ? `<h2>The parties</h2>${parties.map(([src, h]) => `${h}<p class="attrib">From ${src}.</p>`).join('')}` : ''}
      <h2>Argued by</h2>
      ${argued.length ? `<ul class="pa-argued">${argued.map(a => `<li class="pa-${esc(a.side)}"><b>${esc(a.name)}</b><span>${esc(a.desc)}</span></li>`).join('')}</ul>
        <p class="attrib">${argued[0].src === 'tr' ? 'From the appearances page of the official argument transcript (supremecourt.gov).' : `From <a href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Oyez</a>.`}</p>`
        : `<p class="muted-line">${pend && !pend.argued ? 'Not yet argued.' : 'No record of the advocates for this case in the sources used here.'}</p>`}
      ${counsel.length ? `<h2>Counsel on the briefs</h2>
        <div class="pa-cols">${['pet', 'res'].map(k => bySide(k).length ? `<div><h3>${SIDE[k]}</h3><ul class="pa-counsel">${bySide(k).map(person).join('')}</ul></div>` : '').join('')}</div>
        ${bySide('other').length ? `<details class="amici"><summary>${bySide('other').length} lawyer${bySide('other').length === 1 ? '' : 's'} for amici curiae and others</summary><ul class="pa-counsel">${bySide('other').map(person).join('')}</ul></details>` : ''}
        <p class="attrib">Counsel listed on the <a href="${esc(P.docket)}" target="_blank" rel="noopener">Supreme Court docket for No. ${esc(P.d)}</a>${P.also ? ` (and No. ${P.also.map(esc).join(', ')})` : ''}, with the firm or office the docket gives. Contact details are left out.</p>` : ''}
    </section>`;
  }
  /* The Authorities tab: the cases and statutes the opinion and the argument discuss most, each with a short sourced
     summary, then everything the briefs cite (from their Tables of Authorities). */
  function renderAuthorities(el, A, c) {
    const B = A.briefs;
    const items = A.items;
    const shortOf = i => { const b = B[i]; const same = B.filter(x => x.k === b.k); return (BRIEF_SHORT[b.k] || 'Brief') + (same.length > 1 ? ' ' + (same.indexOf(b) + 1) : ''); };
    const sides = it => new Set(Object.keys(it.by).map(i => B[i].side));
    const authLink = (it, inner) => it.id ? `<a href="#/case/${esc(it.id)}">${inner}</a>` : it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${inner} <span class="ext">↗</span></a>` : inner;
    const title = it => it.t === 'case' ? `<i>${esc(it.label)}</i>` : esc(it.label + (it.subs && it.subs.length === 1 ? it.subs[0] : ''));
    const meta = it => it.t === 'case' ? [it.cite, it.court ? `${it.court} ${it.y || ''}`.trim() : it.y].filter(Boolean).map(esc).join(' · ') : it.subs && it.subs.length > 1 ? 'Subsections cited: ' + it.subs.slice(0, 8).map(esc).join(', ') + (it.subs.length > 8 ? '…' : '') : '';
    const chips = it => Object.entries(it.by).map(([i, p]) => `<span class="au-chip au-${esc(B[i].side)}" title="${esc(B[i].label || briefName(B[i]))}${p ? `, page${/[,–-]|passim/.test(p) ? 's' : ''} ${esc(p)}` : ''}">${esc(shortOf(i))}</span>`).join('');
    const clauseLinks = it => it.clauses ? `<div class="au-clauses">Annotated Constitution: ${it.clauses.map(([id, name]) => `<a href="${hashFor('corner/constitution', { c: id })}">${esc(name)}</a>`).join(' · ')}</div>` : '';
    const stextHtml = s => `<details class="au-stext"><summary>Text of ${esc(s.head || 'the section')} <small>U.S. Code${s.ed ? ', ' + esc(s.ed) + ' edition' : ''} (govinfo)</small></summary>
      <div class="au-stat">${s.paras.map(([ind, t]) => `<p style="margin-left:${ind * 1.1}em">${esc(t)}</p>`).join('')}${s.more ? '<p class="muted-line">…</p>' : ''}</div>
      <a class="link-arrow" href="${esc(s.src)}" target="_blank" rel="noopener">Full section at govinfo.gov ↗</a></details>`;
    const sumSource = it => { const x = it.sumSrc || ''; return x === 'opinion' ? 'as the Court’s opinion describes it' : x.startsWith('brief:') ? 'as ' + briefName(B[+x.slice(6)] || {}) + ' describes it' : x === 'AI-generated brief' ? 'AI-generated summary' : x.replace(/^Holding \((.+)\)$/, '$1').replace(/ \(U\.S\. Reports\)$/, ', U.S. Reports'); };
    const rel = it => 3 * (it.op || 0) + (it.ar || 0) + 0.5 * Object.keys(it.by).length;
    let top = items.filter(it => (it.op || 0) + (it.ar || 0) > 0 && it.t !== 'reg' && it.t !== 'rule').sort((a, b) => rel(b) - rel(a));
    const byMentions = top.length > 0;
    if (!byMentions) top = items.filter(it => Object.keys(it.by).length >= 2 && (it.t === 'case' || it.t === 'usc' || it.t === 'const')).sort((a, b) => rel(b) - rel(a));
    top = top.slice(0, 30);
    const mention = it => [it.op ? `named ${it.op} time${it.op === 1 ? '' : 's'} in the opinion` : '', it.ar ? `in ${it.ar} exchange${it.ar === 1 ? '' : 's'} at argument` : ''].filter(Boolean).join(' · ');
    const card = (it, i) => {
      const what = it.t === 'usc' ? [it.head, it.tname ? 'Title ' + (it.label.match(/^(\d+)/) || [, ''])[1] + ', ' + it.tname : ''].filter(Boolean).join(' — ') : '';
      return `<article class="au-card${i >= 10 ? ' au-more' : ''}"${i >= 10 ? ' hidden' : ''}>
        <header><h3>${authLink(it, title(it))}</h3><div class="au-meta">${meta(it)}${chips(it)}</div>${mention(it) ? `<div class="au-ment">${esc(mention(it))}</div>` : ''}</header>
        ${it.t === 'const' && it.text ? `<blockquote class="au-const">${esc(it.text)}</blockquote>${clauseLinks(it)}` : ''}
        ${what ? `<p class="au-sum"><span>Pertains to</span>${esc(what)}</p>` : ''}
        ${it.sum ? `<p class="au-sum${it.sumSrc === 'AI-generated brief' ? ' au-ai' : ''}"><span>${it.t === 'case' ? 'Held' : 'Summary'} <em>· ${esc(sumSource(it))}</em></span>${esc(it.sum)}</p>` : ''}
        ${it.stext ? stextHtml(it.stext) : ''}
      </article>`;
    };
    const groups = [['const', 'Constitutional provisions'], ['case', 'Cases'], ['usc', 'Statutes'], ['law', 'Public laws'], ['reg', 'Regulations'], ['rule', 'Federal rules']];
    const sorted = list => list.slice().sort((a, b) => (Object.keys(b.by).length - Object.keys(a.by).length) || (b.sc || 0) - (a.sc || 0) || a.label.localeCompare(b.label, 'en', { numeric: true }));
    const row = it => `<li data-sides="${[...sides(it)].join(' ')}"><div class="au-row-t">${authLink(it, title(it))}</div><div class="au-row-m">${meta(it) ? `<span>${meta(it)}</span>` : ''}${chips(it)}</div>
      ${it.t === 'const' ? clauseLinks(it) : ''}</li>`;
    const nOp = items.filter(it => it.op).length;
    el.innerHTML = `<section class="au">
      <p class="au-intro">${fmt(items.length)} authorities cited in ${B.every(b => b.toa === false) ? '' : 'the Tables of Authorities of '}${B.length} merits brief${B.length === 1 ? '' : 's'}${A.src && !A.src.includes('docket') ? ` of the United States` : ''}${A.opinion ? `; ${nOp} of them named in the Court's opinion` : ''}${A.tr ? '; ranked by how often the opinion and the oral argument discuss them' : ''}.</p>
      <div class="briefs au-briefs">${B.map((b, i) => `<a class="brief" href="${esc(b.url)}" target="_blank" rel="noopener"><b>${esc(briefName(b))}</b><span>${esc(b.label)}</span><em>${b.n ? `${b.n} authorities · ` : ''}${b.date ? esc(fmtDate(b.date)) + ' · ' : ''}${esc(b.fmt || 'PDF')} ↗</em></a>`).join('')}</div>
      ${top.length ? `<h2>Most relevant authorities</h2><p class="muted-line au-sub">${byMentions ? `The cases and statutes ${A.opinion ? 'the Court’s opinion' : ''}${A.opinion && A.tr ? ' and ' : ''}${A.tr ? 'the oral argument' : ''} discuss most` : 'Cited in more than one brief (no opinion or argument transcript yet)'}, with what each case held or what each statute covers.</p>
        <div class="au-cards">${top.map(card).join('')}</div>
        ${top.length > 10 ? `<button class="btn btn-ghost btn-sm" id="au-all">Show ${top.length - 10} more</button>` : ''}` : ''}
      <h2>Cited in the briefs</h2>
      <div class="au-tools"><div class="seg" role="group" aria-label="Side"><button data-side="" class="on">All</button><button data-side="both">Both sides</button><button data-side="pet">Petitioner's side</button><button data-side="res">Respondent's side</button></div>
        <span class="au-legend"><span class="au-chip au-pet">Pet.</span> petitioner <span class="au-chip au-res">Resp.</span> respondent <span class="au-chip au-us">U.S.</span> United States · hover a tag for page numbers</span></div>
      ${groups.map(([t, label]) => { const list = sorted(items.filter(it => it.t === t)); return list.length ? `<div class="au-group"><h3 class="au-gh">${label} <span>${list.length}</span></h3><ul class="au-list">${list.map(row).join('')}</ul></div>` : ''; }).join('')}
      <p class="attrib">Authorities listed in each brief's Table of Authorities${B.some(b => b.toa === false) ? ', or, for a brief printed without one, in the citations in its text (no page references)' : ''}. Briefs from ${briefSource(A)}. Secondary sources and entries that could not be identified with confidence are left out. Mentions: the authority's citation or distinctive party name (or "section <i>n</i>") in the opinion, and the argument exchanges that name it. Summaries: the opinion's own description of a cited case where it gives one ("holding that …"), otherwise the case's holding or summary on this site (supremecourt.gov, Oyez, the U.S. Reports syllabus, or an AI-generated brief, as labelled), otherwise a brief's description; statutes by their U.S. Code section heading. Statutory text: U.S. Code (govinfo.gov, public domain). Case links go to this site's page when the case is here, otherwise to Justia or CourtListener.</p>
    </section>`;
    const all = el.querySelector('#au-all');
    if (all) all.addEventListener('click', () => { el.querySelectorAll('.au-more').forEach(x => { x.hidden = false; }); all.remove(); });
    el.querySelector('.au-tools .seg').addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      b.parentNode.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
      const f = b.dataset.side;
      el.querySelectorAll('.au-list li').forEach(li => {
        const s = li.dataset.sides.split(' ');
        li.hidden = f === 'both' ? !(s.includes('pet') && s.includes('res')) : f ? !s.includes(f) : false;
      });
      el.querySelectorAll('.au-group').forEach(g => { const n = g.querySelectorAll('li:not([hidden])').length; g.hidden = !n; g.querySelector('.au-gh span').textContent = n; });
    });
  }
  /* The Court began recording oral arguments in October 1955 (the 1955 Term); earlier argued cases have no audio. */
  const hasArgAudio = c => !!c.arg && parseInt(String(c.t), 10) >= 1955;

  /* ------------------------------------------------------------ justices */
  const yearOf = d => ((d || '').match(/\d{4}/) || [''])[0];
  const servedLabel = j => `${yearOf(j.roles[0].start)}–${j.roles[j.roles.length - 1].end ? yearOf(j.roles[j.roles.length - 1].end) : 'present'}`;
  const isSitting = j => !j.roles[j.roles.length - 1].end;
  const isChiefNow = j => j.roles.some(r => r.pos === 'Chief Justice' && !r.end);
  function justiceTile(j) {
    return `<a class="justice-tile" href="#/justice/${esc(j.id)}">
      <span class="justice-portrait">${j.img ? `<img src="${esc(j.img)}" alt="${esc(j.name)}" loading="lazy">` : ''}</span>
      <b>${esc(j.name)}</b><span>${j.roles.some(r => r.pos === 'Chief Justice') ? 'Chief Justice · ' : ''}${servedLabel(j)}</span></a>`;
  }
  function viewJustices() { withData([['justices', 'JUSTICES']], J => renderJustices(J)); }
  function renderJustices(J) {
    const sitting = J.justices.filter(isSitting).sort((a, b) => isChiefNow(b) - isChiefNow(a));
    const former = J.justices.filter(j => !isSitting(j)).reverse();
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a><span>/</span><span>Justices</span></div>
        <h1>The Justices</h1><p>All ${J.justices.length} people who have served on the Supreme Court. Select a justice for a short biography, the most-cited opinions they wrote, and liberal–conservative and institutionalism ratings computed from their votes.</p>
        ${scotusTabs('justices')}</div>
      <div class="wrap" style="padding-bottom:48px">
      <h2 class="section-h">The current Court</h2><div class="justice-grid">${sitting.map(justiceTile).join('')}</div>
      <h2 class="section-h">Former justices <span class="muted-line" style="font-size:14px">most recent first</span></h2><div class="justice-grid">${former.map(justiceTile).join('')}</div>
      <p class="attrib" style="margin-top:28px">Portraits from Wikimedia Commons (credited on each justice's page). Names and dates from Wikipedia's list of justices.</p>
    </div></div>`;
  }
  function viewJustice(id) { withData([['justices', 'JUSTICES'], ['votes', 'VOTES'], ['scotus', 'SCOTUS'], ['case_impact', 'CASE_IMPACT']], (J, V, S, I) => renderJustice(J, V, S, I, id)); }
  /* appointment, education and career facts (scripts/justices_facts.py: Federal Judicial Center and senate.gov) */
  function apptLine(r) {
    const bits = [r.recess ? `recess appointment ${fmtDate(r.recess)}` : '', r.nom ? `nominated ${fmtDate(r.nom)}` : '',
      r.conf ? `confirmed ${fmtDate(r.conf)}${r.vote ? ` (${r.vote === 'voice vote' ? 'voice vote' : r.vote})` : ''}` : '',
      r.rejected ? `rejected by the Senate ${fmtDate(r.rejected)}${r.vote ? ` (${r.vote})` : ''}` : '', r.comm ? `commissioned ${fmtDate(r.comm)}` : ''].filter(Boolean);
    return bits.length ? `<br><span style="font-size:13px;color:var(--ink-3)">${esc(bits.join(' · ').replace(/^./, c => c.toUpperCase()))}</span>` : '';
  }
  function fjcRows(j) {
    const F = j.fjc;
    if (!F) return '';
    const list = (arr, n) => arr.length > n
      ? `${arr.slice(0, n).map(esc).join('<br>')}<details><summary class="muted-line" style="font-size:13px;cursor:pointer">${arr.length - n} more</summary>${arr.slice(n).map(esc).join('<br>')}</details>`
      : arr.map(esc).join('<br>');
    return (F.edu ? `<dt>Education</dt><dd>${list(F.edu.map(([s, d, y]) => [s, d, y].filter(Boolean).join(', ')), 6)}</dd>` : '')
      + (F.other ? `<dt>Other federal judicial service</dt><dd>${list(F.other, 4)}</dd>` : '')
      + (F.career ? `<dt>Career</dt><dd>${list(F.career, 5)}</dd>` : '')
      + (F.url ? `<dt>Source</dt><dd><a href="${esc(F.url)}" target="_blank" rel="noopener">Federal Judicial Center biography ↗</a><br><span class="muted-line" style="font-size:12px">Senate votes from senate.gov</span></dd>` : '');
  }
  function renderJustice(J, V, S, I, id) {
    const j = J.justices.find(x => x.id === id);
    if (!j) return viewNotFound();
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const mine = new Set(V.j.map((x, i) => (x[1] === id ? i : -1)).filter(i => i >= 0));
    const wrote = { maj: [], dis: [], con: [] };
    for (const [cid, r] of Object.entries(V.c)) {
      for (const [i, f] of r[2]) { if (mine.has(i) && f === 1) wrote.maj.push(cid); else if (mine.has(i) && f === 2) wrote.con.push(cid); }
      for (const [i, f] of r[3]) if (mine.has(i) && f === 3) wrote.dis.push(cid);
    }
    const n = cid => (I.c[cid] || [0, 0, -1])[2];
    const rank = arr => arr.filter(cid => caseById.get(cid)).sort((a, b) => (n(b) - n(a)) || ((I.c[b] || [0])[0] - (I.c[a] || [0])[0]));
    const item = cid => {
      const c = caseById.get(cid), m = I.c[cid];
      return `<li><a class="t" href="#/case/${esc(cid)}">${esc(c.n)}</a><div class="m">${esc(c.cit || '')}${c.y ? ' · ' + esc(c.y) : ''}${m ? ` · <span title="${esc(impactTitle(m))}">${fmt(m[2])} later Supreme Court citations</span>` : ''}</div></li>`;
    };
    const maj = rank(wrote.maj), dis = rank(wrote.dis);
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a><span>/</span><a href="#/justices">Justices</a><span>/</span><span>${esc(j.name)}</span></div></div>
      <div class="wrap" style="padding-top:22px;padding-bottom:48px">
      <div class="justice-head">
        <figure class="justice-photo">${j.img ? `<img src="${esc(j.img)}" alt="Portrait of ${esc(j.name)}">` : ''}<figcaption>${j.imgPage ? `<a href="${esc(j.imgPage)}" target="_blank" rel="noopener">Portrait</a>` : 'Portrait'}${j.imgLicense ? ' · ' + esc(j.imgLicense) : ''} · Wikimedia Commons</figcaption></figure>
        <div>
          <h1>${esc(j.name)}</h1>
          <p class="justice-years">${esc(j.born || '')}${j.died ? '–' + esc(j.died) : j.born ? ' (born)' : ''}</p>
          <dl class="kv">${j.roles.map(r => `<dt>${esc(r.pos)}</dt><dd>${esc(r.start || '')} – ${esc(r.end || 'present')}${r.appointer ? `<br><span class="muted-line" style="font-size:13px">Appointed by ${esc(r.appointer)}</span>` : ''}${apptLine(r)}</dd>`).join('')}${fjcRows(j)}
            <dt>Opinions written</dt><dd>${fmt(wrote.maj.length)} for the Court · ${fmt(wrote.con.length)} concurrence${wrote.con.length === 1 ? '' : 's'} · ${fmt(wrote.dis.length)} dissent${wrote.dis.length === 1 ? '' : 's'}<br><span class="muted-line" style="font-size:12px">Among the cases indexed on this site</span></dd></dl>
          ${j.bio ? `<div class="prose-sm"><p>${esc(j.bio)}</p></div><p class="attrib">From Wikipedia${j.wiki ? ` (<a href="${esc(j.wiki)}" target="_blank" rel="noopener">full article</a>)` : ''}, licensed <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>.</p>` : ''}
        </div>
      </div>
      <div class="justice-cols">
        <div class="panel"><h4>Most-cited opinions for the Court</h4>${maj.length ? `<ol class="mini-list ranked">${maj.slice(0, 15).map(item).join('')}</ol>` : '<p class="muted-line">No majority opinions among the cases indexed here.</p>'}</div>
        <div class="panel"><h4>Most-cited dissents</h4>${dis.length ? `<ol class="mini-list ranked">${dis.slice(0, 8).map(item).join('')}</ol>` : '<p class="muted-line">No written dissents among the cases indexed here.</p>'}</div>
      </div>
      <p class="attrib">Authorship from the Supreme Court Database (Spaeth et al.) and the Court's opinions. Ranked by later Supreme Court citations from the Caselaw Access Project (Harvard Law School Library), whose data runs to about 2020, and from CourtListener (Free Law Project) for later decisions.</p>
      <div id="justice-ratings"><p class="muted-line"><span class="spinner sm"></span> Loading ratings…</p></div>
    </div></div>`;
    const tk = routeToken;
    Promise.all([ext(), loadData('ratings', 'RATINGS'), isSitting(j) ? loadData('models', 'MODELS').catch(() => null) : Promise.resolve(null)])
      .then(([X, R, M]) => { const el = document.getElementById('justice-ratings'); if (tk === routeToken && el) X.justiceRatings(el, j, J, R, M); })
      .catch(() => { const el = document.getElementById('justice-ratings'); if (el) el.innerHTML = ''; });
  }

  /* ---- vote split: the number, a dot per justice, and a hover/focus panel naming each side ---- */
  const VOTE_FLAG = ['', 'wrote the opinion', 'concurred', 'wrote a dissent'];
  function voteHtml(v, src) {
    const nm = n => Array.isArray(n) ? (n[1] ? `<a href="#/justice/${esc(n[1])}">${esc(n[0])}</a>` : `<span>${esc(n[0])}</span>`) : `<span>${esc(n)}</span>`;
    const list = arr => arr.map(([n, f]) => `<li>${nm(n)}${f ? `<em>${VOTE_FLAG[f]}</em>` : ''}</li>`).join('');
    const who = v.maj.length > 0 || (v.eq && v.eq.length > 0);
    return `<div class="vote${who ? ' has-pop' : ''}"${who ? ' tabindex="0" aria-describedby="vote-pop"' : ''}>
      <b>${v.m}–${v.n}</b><span class="vote-for">${v.eq ? 'affirmed by an equally divided Court' : v.party ? 'for ' + esc(v.party) : 'decision'}</span>
      ${v.eq && who ? `<span class="vote-dots" aria-hidden="true"><small style="margin-left:0">Hover for the justices</small></span>
      <div class="vote-pop vote-pop-eq" id="vote-pop" role="tooltip"><div><h5>Participating · ${v.eq.length}</h5><ul>${list(v.eq.map(n => [n, 0]))}</ul></div>
        <div><p>When the Court divides evenly, the lower court's judgment stands and the Court does not say how each justice voted.</p></div></div>` : ''}
      ${who && !v.eq ? `<span class="vote-dots" aria-hidden="true">${v.maj.map(() => '<i class="on"></i>').join('')}${v.min.map(() => '<i></i>').join('')}<small>Hover for the justices</small></span>
      <div class="vote-pop" id="vote-pop" role="tooltip">
        <div><h5>Majority · ${v.maj.length}</h5><ul>${list(v.maj)}</ul></div>
        <div><h5>Dissent · ${v.min.length}</h5>${v.min.length ? `<ul>${list(v.min)}</ul>` : '<p>None (unanimous)</p>'}</div>
      </div>` : ''}
    </div><p class="vote-src">Votes: ${src}</p>`;
  }
  function oyezVote(dec) {
    const vs = (dec.votes || []).filter(x => x && x.member);
    const name = x => x.member.name || x.member.last_name;
    const op = x => String(x.opinion_type || '');
    const flag = x => x.vote === 'majority' ? (/majority|plurality/.test(op(x)) ? 1 : /concur/.test(op(x)) ? 2 : 0) : (/dissent/.test(op(x)) ? 3 : 0);
    return { m: dec.majority_vote, n: dec.minority_vote, party: dec.winning_party,
      maj: vs.filter(x => x.vote === 'majority').map(x => [name(x), flag(x)]), min: vs.filter(x => x.vote === 'minority').map(x => [name(x), flag(x)]) };
  }

  function renderCase(S, id, K, I, AI, params) {
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const dk = (K && K.cases.find(e => e.id === id || id.endsWith('/' + e.d))) || null;
    let c = caseById.get(id);
    if (!c && dk) c = { id: dk.id, n: dk.n, t: dk.t, d: dk.d, q: dk.q, ds: dk.ds, pending: true };
    if (!c) return viewNotFound();
    const pend = dk && !c.dec ? dk : null;
    const caseName = c.n.toLowerCase().replace(/\s*\(\d\)$/, '');
    const relatedArticles = caseName.length < 10 ? [] : articles.filter(a => a._t.includes(caseName) || a._ab.includes(caseName))
      .sort((x, y) => (y.c ?? -1) - (x.c ?? -1)).slice(0, 6);
    // tabs: the overview (summary, opinions, briefs, audio); the authorities the briefs rely on, ranked by discussion; and,
    // for pending cases, the predicted outcome. Switching tabs does not re-render the page, so argument audio keeps playing.
    const adk = (AI && (AI[c.id] || (pend && AI[pend.id]))) || null;
    const hasParties = c.s !== 1 || ((window.PARTIES_INDEX || []).includes(String(c.t)));
    const hasMedia = true;   // the case pages row is always there; podcasts, coverage and newspapers when found
    const TABS = [['', 'Overview'], adk ? ['authorities', 'Authorities'] : null, hasParties ? ['parties', 'Parties & advocates'] : null, hasMedia ? ['media', 'In the media'] : null, pend ? ['prediction', 'Predicted outcome'] : null].filter(Boolean);
    let tab = (params && params.get('tab')) || '';
    if (!TABS.some(t => t[0] === tab)) tab = '';
    const tabHref = k => `#/case/${c.id}${k ? '?tab=' + k : ''}`;
    app.innerHTML = `<div class="fade-in"><div class="article${tab ? ' article-wide' : ''}" id="case-article">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a>${pend ? '<span>/</span><a href="#/docket">Current docket</a>' : c.y ? `<span>/</span><a href="${hashFor('scotus', { era: (ERAS.find(e => c.y >= e.from && c.y < e.to) || {}).id })}">${c.y}</a>` : ''}</div>
        <h1>${esc(c.n)}</h1>
        <div class="publine">${c.cit ? esc(c.cit) + ' · ' : ''}${c.dec ? 'Decided ' + esc(fmtDate(c.dec)) : 'October Term ' + esc(c.t)}${c.d ? ' · No. ' + esc(c.d) : ''}${pend && pend.lower ? ' · from the ' + esc(pend.lower) : ''}</div>
        <div id="case-overruled"></div>
        ${pend ? `<div class="pending-banner status-${docketStatus(pend).k}"><b>Pending</b><span>${esc(docketStatus(pend).label)}</span></div>` : ''}
        ${TABS.length > 1 ? `<div class="subtabs case-tabs" role="tablist">${TABS.map(([k, l]) => `<a href="${esc(tabHref(k))}" data-tab="${k}" role="tab" class="${k === tab ? 'on' : ''}">${l}</a>`).join('')}</div>` : ''}
        ${adk ? `<div class="case-panel" data-panel="authorities"${tab === 'authorities' ? '' : ' hidden'}><p class="muted-line"><span class="spinner sm"></span> Loading the authorities…</p></div>` : ''}
        ${hasMedia ? `<div class="case-panel" data-panel="media"${tab === 'media' ? '' : ' hidden'}><p class="muted-line"><span class="spinner sm"></span> Loading…</p></div>` : ''}
        ${hasParties ? `<div class="case-panel" data-panel="parties"${tab === 'parties' ? '' : ' hidden'}><p class="muted-line"><span class="spinner sm"></span> Loading the parties and advocates…</p></div>` : ''}
        ${pend ? `<div class="case-panel" data-panel="prediction"${tab === 'prediction' ? '' : ' hidden'}><div id="case-prediction"><p class="muted-line"><span class="spinner sm"></span> Loading the prediction…</p></div></div>` : ''}
        <div class="case-panel" data-panel=""${tab ? ' hidden' : ''}>
        ${c.ds ? `<div class="abstract plain">${esc(c.ds)}</div>` : ''}
        ${!pend && adk ? '<div id="case-briefs"></div>' : ''}
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
          ${c.s === 1 ? '' : `<a class="btn btn-ghost" href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Oyez ↗</a>`}
        </div>
        ${c.h ? `<h2>Holding <small>(supremecourt.gov)</small></h2><div class="callout">${esc(c.h)}</div>` : ''}
        <div id="case-live"><h2>Case summary</h2><p class="muted-line"><span class="spinner sm"></span> Loading facts, question and conclusion from Oyez…</p></div>
        <div id="case-audio"></div>
        <div id="case-ftcites"></div>
        <div id="case-articles">${relatedArticles.length ? `<h2>Law review articles discussing this case</h2><div class="cards">${relatedArticles.map(a => card(a)).join('')}</div>` : ''}</div>
        </div>
      </div>
      <aside id="case-aside"${tab ? ' hidden' : ''}>
        <div class="panel"><h4>Details</h4><dl class="kv">
          ${c.cit ? `<dt>Citation</dt><dd>${esc(c.cit)}</dd>` : ''}
          <dt>Term</dt><dd>${esc(c.t)}</dd>
          ${c.d ? `<dt>Docket</dt><dd>${esc(c.d)}</dd>` : ''}
          ${c.dec ? `<dt>Decided</dt><dd>${esc(fmtDate(c.dec))}</dd>` : ''}
          ${(() => { const m = I && I.c[c.id]; return m ? `<dt>Impact</dt><dd title="${esc(impactTitle(m))}"><b>${fmt(m[2])}</b> later Supreme Court citations${m[3] ? '<span class="muted-line" style="font-size:12px">From CourtListener (Free Law Project)</span>' : `<div class="impact-meter"><i style="width:${Math.max(4, Math.round(m[1] * 100))}%"></i></div><span class="muted-line" style="font-size:12px">Top ${topPct(m)}% of American cases by citation PageRank</span>`}</dd>` : ''; })()}
          <dt>Areas</dt><dd>${(c.tg || []).map(t => `<a class="tag" href="${hashFor('scotus', { tag: t })}">${esc(topicById[t]?.name || t)}</a>`).join(' ') || '—'}</dd>
        </dl><div id="case-vote"></div></div>
        <div class="panel" id="case-opinions" hidden><h4>Opinions</h4><ul class="mini-list"></ul></div>
        <div class="panel"><h4>Find articles</h4><a class="link-arrow" href="${hashFor('search', { q: '"' + c.n.replace(/\s*\(\d\)$/, '') + '"' })}">Search the index for this case →</a></div>
        <div class="panel" id="case-precedents"><h4>Precedents</h4>
          <div id="prec-body"><p class="muted-line" style="font-size:13px"><span class="spinner sm"></span> Loading…</p></div>
        </div>
      </aside>
    </div></div>`;

    const token = routeToken;
    loadXL('case', parseInt(String(c.y || '').slice(0, 4), 10)).then(XC => {
      const x = XC && XC[c.id], el = document.getElementById('case-articles');
      if (!x || token !== routeToken || !el) return;
      const named = (x.a || []).map(([aid]) => byId.get(aid)).filter(Boolean);
      const cited = (x.ct || []).map(([aid, k]) => [byId.get(aid), k]).filter(([b]) => b);
      const groups = {}; for (const [b, k] of cited) (groups[k] = groups[k] || []).push(b);
      el.innerHTML = (cited.length ? `<h2>Law review articles cited by the Court</h2>${['majority', 'opinion', 'concurrence', 'separate', 'dissent'].filter(k => groups[k]).map(k => `<div class="prec-h" style="margin:10px 0 6px">${OPINION_KIND[k]}</div><div class="cards">${groups[k].map(b => card(b)).join('')}</div>`).join('')}<p class="attrib">Citations in the text of the opinions (Caselaw Access Project, Harvard Law School Library).</p>` : '')
        + (named.length ? `<h2>Law review articles discussing this case</h2><div class="cards">${named.slice(0, 6).map(b => card(b)).join('')}</div>${named.length > 6 ? `<p class="muted-line" style="font-size:13px">${fmt(named.length)} articles in the index name this case in the title, abstract or keywords; the strongest matches shown. <a href="${hashFor('search', { q: '"' + c.n.replace(/\s*\(\d\)$/, '') + '"' })}" style="color:var(--accent)">Search them all →</a></p>` : ''}` : el.innerHTML);
    }).catch(() => {});
    loadFT('case', parseInt(String(c.y || '').slice(0, 4), 10)).then(FC => {
      const xs = ((FC && FC[c.id]) || []).map(([aid, n]) => [byId.get(aid), n]).filter(([b]) => b), el = document.getElementById('case-ftcites');
      if (!xs.length || token !== routeToken || !el) return;
      const total = xs.reduce((t, [, n]) => t + n, 0);
      el.innerHTML = `<h2>Cited in law reviews</h2><p class="muted-line" style="font-size:13px;margin:-4px 0 10px">Cited ${fmt(total)} time${total === 1 ? '' : 's'} in the footnotes of ${fmt(xs.length)} indexed article${xs.length === 1 ? '' : 's'} whose full text could be read; most citations first.</p><div class="cards">${xs.slice(0, 6).map(([b]) => card(b)).join('')}</div>`;
    }).catch(() => {});
    // Precedents panel (scripts/build_precedents.py, one file per year): what the opinion cites, the later decisions
    // citing it, related decisions (shared citations), overruled by / overrules; Oyez's "discussed" cases are merged in.
    let precRec = null, precLoaded = false, oyezCited = [];
    const precLine = x => { const k = x && caseById.get(x[0]); return k ? precedentItem(k) : `<li><span class="t">${esc(x[1])}</span>${x[2] ? `<div class="m">${esc(x[2])}</div>` : ''}</li>`; };
    function drawPrecedents() {
      const el = document.getElementById('prec-body');
      if (!el || token !== routeToken || !precLoaded) return;
      const r = precRec || {}, ids = xs => (xs || []).map(i => caseById.get(i)).filter(Boolean);
      const group = (h, items, more) => items.length ? `<div class="prec-group"><div class="prec-h">${h}</div><ul class="mini-list">${items.join('')}</ul>${more ? `<p class="muted-line" style="font-size:12px;margin:4px 0 0">${more}</p>` : ''}</div>` : '';
      const relied = ids(r.c), seen = new Set([...relied.map(x => x.id), ...(r.ob || []).concat(r.ov || []).map(x => x[0]).filter(Boolean)]);
      const discussed = oyezCited.filter(x => !seen.has(x.id));
      const related = r.r ? ids(r.r) : similarCases(S, c).filter(x => !seen.has(x.id));
      el.innerHTML = [
        group('Overruled by', (r.ob || []).map(precLine)),
        group('Overrules', (r.ov || []).map(precLine)),
        group('Precedents relied on', relied.map(precedentItem), r.cn > relied.length ? `${fmt(r.cn)} Supreme Court decisions cited in all; those most closely related to this case shown.` : ''),
        group(relied.length ? 'Also discussed (Oyez)' : 'Discussed in this case', discussed.slice(0, 8).map(precedentItem)),
        group('Later decisions citing it', ids(r.b).map(precedentItem), r.bn > (r.b || []).length ? `${fmt(r.bn)} later Supreme Court decisions in all; those most closely related to this case shown.` : ''),
        group('Related decisions', related.slice(0, 6).map(precedentItem))
      ].join('') || '<p class="muted-line" style="font-size:13px">No related decisions found.</p>';
      if (r.c || r.b || r.r) el.insertAdjacentHTML('beforeend', '<p class="attrib" style="font-size:11.5px">From the citation graph of the Caselaw Access Project (Harvard Law School Library); related decisions share cited precedents or are cited together. Overrulings from Wikipedia’s list of overruled decisions.</p>');
      const flag = document.getElementById('case-overruled');
      if (flag) {
        const name = x => { const k = caseById.get(x[0]); return k ? `<a href="#/case/${esc(k.id)}">${esc(k.n)}</a>${k.y ? ' (' + esc(k.y) + ')' : ''}` : esc(x[1]); };
        flag.innerHTML = r.ob ? `<div class="pending-banner overruled"><b>Overruled</b><span>Overruled by ${r.ob.map(name).join('; ')}.</span></div>`
          : r.ov ? `<div class="pending-banner overrules"><b>Overrules</b><span>This decision overruled ${r.ov.map(name).join('; ')}.</span></div>`
          : r.pa ? '<div class="pending-banner overrules"><b>Precedent</b><span>The Supreme Court Database codes this decision as altering an earlier precedent.</span></div>' : '';
      }
    }
    {
      const decade = parseInt(String(c.y || '').slice(0, 4), 10);   // one file per year
      loadData('precedents-index', 'PRECEDENTS_INDEX').catch(() => []).then(ix => (ix || []).includes(String(decade)) ? loadScriptOnce(`data/precedents/${decade}.js`).catch(() => {}) : null)
        .then(() => { precRec = (window.PRECEDENTS || {})[c.id] || null; precLoaded = true; drawPrecedents(); });
    }
    loadData('votes', 'VOTES').then(V => {
      const ve = document.getElementById('case-vote'); const r = V && V.c[c.id];
      if (token !== routeToken || !ve || !r || ve.dataset.src) return;
      ve.dataset.src = 'scdb';
      ve.innerHTML = voteHtml({ m: r[0], n: r[1], maj: r[2].map(([i, f]) => [V.j[i], f]), min: r[3].map(([i, f]) => [V.j[i], f]), eq: r[5] ? r[5].map(i => V.j[i]) : null },
        r[4] === 2 ? `<a href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Oyez</a>` : r[4] ? `the Court's opinion${c.pdf ? ` (<a href="${esc(c.pdf)}" target="_blank" rel="noopener">PDF</a>)` : ''}` : '<a href="http://scdb.wustl.edu/" target="_blank" rel="noopener">Supreme Court Database</a>');
    }).catch(() => {});
    // Oyez's live record (summary, votes, audio; parties and advocates for the Parties tab)
    const oyezP = c.s === 1 ? Promise.resolve(null) : fetch(`https://api.oyez.org/cases/${c.id}`).then(r => r.ok ? r.json() : null).catch(() => null);
    const loaded = {};
    const showTab = k => {
      app.querySelectorAll('.case-tabs [data-tab]').forEach(a => a.classList.toggle('on', a.dataset.tab === k));
      app.querySelectorAll('.case-panel').forEach(p => { p.hidden = p.dataset.panel !== k; });
      document.getElementById('case-article').classList.toggle('article-wide', !!k);
      document.getElementById('case-aside').hidden = !!k;
      if (loaded[k]) return;
      loaded[k] = true;
      if (k === 'authorities') {
        const el = app.querySelector('[data-panel="authorities"]');
        loadAuth(adk).then(A => { if (token === routeToken) renderAuthorities(el, A, c); })
          .catch(e => { if (token === routeToken) el.innerHTML = `<p class="muted-line">${esc(e.message)}.</p>`; });
      } else if (k === 'media') {
        const el = app.querySelector('[data-panel="media"]');
        // cases in the media index load their term's file; every case gets its case pages row regardless (and a file
        // that fails to load just leaves that row)
        const draw = M => { if (token === routeToken) renderMedia(el, M, c); };
        if ((window.MEDIA_INDEX || []).includes(c.id)) loadScriptOnce(`data/media/${c.t}.js`).then(() => draw((window.MEDIA || {})[c.id])).catch(() => draw(null));
        else draw(null);
      } else if (k === 'parties') {
        const el = app.querySelector('[data-panel="parties"]');
        const pp = (window.PARTIES_INDEX || []).includes(String(c.t)) ? loadScriptOnce(`data/parties/${c.t}.js`).then(() => (window.PARTIES || {})[c.id] || null).catch(() => null) : Promise.resolve(null);
        Promise.all([pp, oyezP]).then(([P, d]) => { if (token === routeToken) renderParties(el, P, d, c, pend); });
      } else if (k === 'prediction') {   // pending case: per-justice predicted votes and split odds (app-stats.js, data/models.js)
        Promise.all([ext(), loadData('models', 'MODELS'), loadData('justices', 'JUSTICES')])
          .then(([X, M, J]) => { const el = document.getElementById('case-prediction'); if (token === routeToken && el) { X.casePrediction(el, c.id, M, J); if (!el.innerHTML) el.innerHTML = '<p class="muted-line">The model has no prediction for this case yet (it needs the questions presented and the docket facts).</p>'; } })
          .catch(() => { const el = document.getElementById('case-prediction'); if (el) el.innerHTML = '<p class="muted-line">The prediction could not be loaded.</p>'; });
      }
    };
    app.querySelectorAll('.case-tabs [data-tab]').forEach(a => a.addEventListener('click', e => {
      e.preventDefault();
      history.replaceState(null, '', a.getAttribute('href'));
      lastRoute = { path: location.hash.replace(/^#\/?/, '').split('?')[0], params: new URLSearchParams(a.getAttribute('href').split('?')[1] || '') };
      showTab(a.dataset.tab);
    }));
    showTab(tab);
    if (!pend && adk) loadAuth(adk).then(A => {
      const el = document.getElementById('case-briefs');
      if (token !== routeToken || !el || !A.briefs.length) return;
      el.innerHTML = `<h2>Merits briefs</h2>${briefTiles(A.briefs)}<p class="attrib">From ${briefSource(A)}. What the briefs cite, and the cases and statutes that matter most: <a href="${esc(tabHref('authorities'))}" data-goto-tab="authorities" style="color:var(--accent)">Authorities →</a></p>`;
      el.querySelector('[data-goto-tab]').addEventListener('click', e => { e.preventDefault(); app.querySelector('.case-tabs [data-tab="authorities"]').click(); window.scrollTo({ top: 0 }); });
    }).catch(() => {});
    if (c.s === 1) {   // listed from the Supreme Court Database only; Oyez has no record of it
      document.getElementById('case-live').innerHTML = `<p class="muted-line">This case is listed from the <a href="http://scdb.wustl.edu/" target="_blank" rel="noopener">Supreme Court Database</a> (Spaeth et al.), which records its name, citation, date and votes. No summary is available; read the opinion ${c.pdf ? 'in the <i>United States Reports</i> (Library of Congress) or ' : ''}on Justia.</p>`;
      headnotes(document.getElementById('case-live'), c);
      aiBrief(document.getElementById('case-live'), c);
      if (c.arg && !hasArgAudio(c)) document.getElementById('case-audio').innerHTML = '<p class="muted-line">No argument recording exists: the Court began recording oral arguments in October 1955.</p>';
      else if (hasArgAudio(c)) clAudio();
      return;
    }
    // CourtListener's copies of the Court's argument recordings: used when Oyez's live record has no argument audio or Oyez is unreachable
    function clAudio() {
      loadScriptOnce('data/cl_audio.js').then(() => {
        const recs = (window.CL_AUDIO || {})[c.id], el = document.getElementById('case-audio');
        if (!recs || !recs.length || token !== routeToken || !el) return;
        mountAudio(el, recs.map(r => ({ kind: 'Oral argument', title: fmtDate(r.d) + ' (recording via CourtListener)', direct: r.mp3 })), c);
        el.insertAdjacentHTML('beforeend', `<p class="attrib">Recording by the Supreme Court of the United States, from <a href="${esc(recs[0].url)}" target="_blank" rel="noopener">CourtListener</a> (Free Law Project). No synchronized transcript.</p>`);
      }).catch(() => {});
    }
    oyezP.then(d => { if (!d) throw new Error('no Oyez record');
      if (token !== routeToken) return;
      const live = document.getElementById('case-live');
      live.innerHTML = [
        d.facts_of_the_case ? `<h2>Facts of the case</h2><div class="prose-sm">${htmlParas(d.facts_of_the_case)}</div>` : '',
        d.question ? `<h2>Question</h2><div class="prose-sm">${htmlParas(d.question)}</div>` : '',
        d.conclusion ? `<h2>Conclusion</h2><div class="prose-sm">${htmlParas(d.conclusion)}</div>` : ''
      ].join('') || '<p class="muted-line">Oyez has no written summary for this case.</p>';
      if (!d.facts_of_the_case && !d.conclusion) { headnotes(live, c); aiBrief(live, c); }
      live.insertAdjacentHTML('beforeend', '<p class="attrib">Summary text © Oyez (oyez.org), used under <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener">CC BY-NC 4.0</a>.</p>');
      statutify([app.querySelector('.article .abstract'), app.querySelector('.article .callout'), live]);
      // precedents named in Oyez's summary, plus Oyez's own related-case links
      const plain = [d.facts_of_the_case, d.question, d.conclusion].map(h => h ? new DOMParser().parseFromString(h, 'text/html').body.textContent : '').join(' ');
      const cited = citedCases(S, plain, c.id);
      for (const r of d.related_cases || []) { const rid = ((r && r.href) || '').match(/\/cases\/(.+)$/); const x = rid && caseById.get(rid[1]); if (x && x.id !== c.id && !cited.includes(x)) cited.push(x); }
      oyezCited = cited; drawPrecedents();
      const dec = (d.decisions || [])[0];
      if (dec && dec.majority_vote != null) {
        const ve = document.getElementById('case-vote');
        if (ve.dataset.src === 'scdb') { const f = ve.querySelector('.vote-for'); if (f && dec.winning_party) f.textContent = 'for ' + dec.winning_party; }
        else { ve.dataset.src = 'oyez'; ve.innerHTML = voteHtml(oyezVote(dec), `<a href="https://www.oyez.org/cases/${esc(c.id)}" target="_blank" rel="noopener">Oyez</a>`); }
      }
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
      statutify([app.querySelector('.article .abstract'), app.querySelector('.article .callout'), document.getElementById('case-live')]);
      courtAudioFallback();
    });
    // the Court posts argument audio within days; Oyez's synced versions follow later
    function courtAudioFallback() {
      if (!pend && hasArgAudio(c)) { clAudio(); return; }
      if (!pend && c.arg && !hasArgAudio(c)) { document.getElementById('case-audio').innerHTML = '<p class="muted-line">No argument recording exists: the Court began recording oral arguments in October 1955.</p>'; return; }
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
    // A second recording on the same announcement day is a justice reading a separate opinion from the bench
    // (usually a dissent). Oyez titles both "Opinion Announcement", so name the speaker and say which it was.
    const seenDay = new Set();
    media.forEach((m, i) => {
      if (m.kind !== 'Opinion announcement' || !m.href) return;
      const day = m.title || '';
      if (!seenDay.has(day)) { seenDay.add(day); return; }
      fetch(m.href).then(r => r.ok ? r.json() : null).then(d => {
        const turns = ((d && d.transcript && d.transcript.sections) || []).flatMap(s => s.turns || []);
        const who = turns.map(t => t.speaker && t.speaker.name).find(Boolean);
        if (!who || !tabs[i]) return;
        const last = who.replace(/,?\s+(Jr|Sr)\.?$/, '').split(' ').pop().toLowerCase();
        return loadData('votes', 'VOTES').catch(() => null).then(V => {
          const r = V && c && V.c[c.id];
          const inMinority = r && r[3].some(([j]) => (V.j[j][0] || '').toLowerCase().split(' ').pop() === last);
          const label = inMinority ? 'Dissent read from the bench' : 'Statement from the bench';
          tabs[i].querySelector('small').textContent = label;
          m.kind = label;
          tabs[i].lastChild.textContent = `${who.replace(/,?\s+Jr\.?$/, '')} · ${day.replace(/^Opinion Announcement\s*-\s*/i, '')}`;
        });
      }).catch(() => {});
    });
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
        let cur = -1, seekedAt = 0;
        tr.addEventListener('click', e => { const t = e.target.closest('.turn'); if (!t) return; audio.currentTime = +t.dataset.s + 0.05; audio.play(); });
        audio.addEventListener('seeking', () => { seekedAt = Date.now(); });
        // the turn being spoken: the one whose span holds the current time. Oyez restarts or omits times in some
        // sections and the timestamps are not always in order, so this is a scan, not a binary search; and the transcript
        // never jumps backwards on its own (a speed-changing browser extension or a stray time update would otherwise
        // send it to the top) unless the listener seeked or clicked
        const findTurn = now => {
          let best = -1;
          for (let k = 0; k < turns.length; k++) {
            const t = turns[k];
            if (typeof t.s !== 'number') continue;
            if (t.s <= now && (typeof t.e !== 'number' || now < t.e)) best = k;
          }
          return best;
        };
        audio.addEventListener('timeupdate', () => {
          const idx = findTurn(audio.currentTime);
          if (idx < 0 || idx === cur) return;
          if (idx < cur && Date.now() - seekedAt > 1500) return;
          if (cur >= 0) els[cur].classList.remove('now');
          cur = idx;
          els[cur].classList.add('now');
          if (document.getElementById('follow')?.checked) {
            const top = tr.scrollTop + els[cur].getBoundingClientRect().top - tr.getBoundingClientRect().top - 60;
            tr.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
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
  function openVideo(id, title, ch, start) {
    const st = +start > 0 ? `&start=${Math.floor(+start)}` : '';
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = `<div class="modal-box" role="dialog" aria-label="${esc(title)}">
      <div class="modal-video"><iframe src="${embedSrc(id)}&autoplay=1${st}" title="${esc(title)}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>
      <div class="modal-foot"><div><b>${esc(title)}</b><span>${esc(ch)}</span></div>
        <div style="display:flex;gap:8px"><a class="btn btn-ghost btn-sm" href="https://www.youtube.com/watch?v=${encodeURIComponent(id)}${st ? `&t=${Math.floor(+start)}s` : ''}" target="_blank" rel="noopener">YouTube ↗</a><button class="btn btn-primary btn-sm" data-close>Close</button></div></div>
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
        <p class="lede">Start with ${G.topics.length} core topics, each with a plain-English overview, short explainer videos and longer lectures from law schools, the landmark cases, and readable articles. Then go deeper in the <a href="#/guide" data-jump="advanced" style="color:var(--accent)">advanced doctrine</a> below: every major doctrine, test and case, with excerpts from the opinions themselves.</p>
        <div class="suggest" style="margin-top:22px"><a class="chip on" href="#/guide" data-jump="beginner">Beginner topics</a><a class="chip" href="#/guide" data-jump="advanced">Advanced doctrine</a><a class="chip" href="#/corner">Originalist's Corner</a></div>
      </div></section>
      <div id="beginner"></div>
      ${groups.map(g => `<section class="section" style="padding-top:44px">
        <div class="section-head"><div><h2>${esc(g)}</h2></div></div>
        <div class="guide-grid">${G.topics.filter(t => t.group === g).map((t, i) => `<a class="guide-card" href="#/guide/${t.id}">
          ${guideIcon(t.id)}
          <span class="guide-body"><b>${esc(t.title)}</b><span>${esc(t.tagline)}</span>
          <span class="guide-meta">${t.videos.length + (t.lectures || []).length} videos · ${t.cases.length} cases · ${(t.books || []).length} book${(t.books || []).length === 1 ? '' : 's'} · ${t.articles.length} readings</span></span>
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
      ${essays.map((e, i) => `<details class="essay" data-essay="${esc(e.id)}" style="--d:${depth(e.id)}" ${i === 0 ? 'open' : ''}>
        <summary><span class="essay-id">${esc(e.id)}</span><b>${esc(e.title)}</b><em>${Math.max(1, Math.round(words(e) / 230))} min</em></summary>
        <div class="essay-body">${e.p.map(p => `<p>${p}</p>`).join('')}</div>
      </details>`).join('')}
      <p class="attrib">From <i>Constitution of the United States of America: Analysis and Interpretation</i> (the "Constitution Annotated"), prepared by the Congressional Research Service, Library of Congress (2022 ed.). A U.S. government work in the public domain. Footnotes are omitted; the annotated edition with full citations is at <a href="https://constitution.congress.gov/" target="_blank" rel="noopener">constitution.congress.gov</a>. Developments after 2022 are covered in the summaries above.</p>
    </div>`;
  }
  function renderDoctrine(A, partId, secId, Q, C) {
    if (!partId && A.parts[0]) { location.replace('#/doctrine/' + A.parts[0].id); return; }   // bare #/doctrine: open the first part
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
    if (Q) mountQuiz(app, 'doctrine:' + p.id, Q.doctrine[p.id] || [], [...p.sections.flatMap(s => [...s.cases.map(c => c.n), ...s.excerpts.map(e => e.n)])]);
    mountDoctrineNarration();
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
  function viewGuideTopic(id) { withData([['guide', 'GUIDE'], ['scotus', 'SCOTUS'], ['books', 'BOOKS'], ['advanced', 'ADVANCED'], ['quizzes', 'QUIZZES'], ['foundations', 'FOUNDATIONS'], ['constitution', 'CONSTITUTION']], (G, S, B, A, Q, F, K) => renderGuideTopic(G, S, id, B, A, Q, F, K)); }
  function renderGuideTopic(G, S, id, B, A, Q, F, K) {
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
        ${(() => {
          const f = F && F.topics[t.id];
          if (!f) return '';
          const cls = (f.clauses || []).map(cid => K && K.clauses.find(c => c.id === cid)).filter(Boolean);
          const ovClause = cls.find(c => c.conan && c.conan.overview);
          const ov = ovClause && ovClause.conan.overview;
          const [, secIds] = GUIDE_LINKS[t.id] || [[], []];
          const adv = secIds.map(x => doctrineHref(A, x)).filter(Boolean);
          const clip = q => q.length > 420 ? q.slice(0, 420).replace(/\s+\S*$/, '') + '…' : q;
          return `<section class="found glossable">
            ${f.basics.length ? `<h2>The basics</h2>${f.basics.map(sec => `${sec.h ? `<h3>${esc(sec.h)}</h3>` : ''}${sec.paras.map(p => `<p>${esc(p)}</p>`).join('')}`).join('')}
            <p class="attrib">Adapted from OpenStax, <i>American Government 3e</i>: ${f.src.map(x => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>`).join('; ')}. Licensed CC BY 4.0; access for free at openstax.org.</p>` : ''}
            ${cls.length ? `<h2>In the Constitution</h2><div class="found-clauses">${cls.map(c => `<a class="found-clause" href="#/corner/constitution?c=${esc(c.id)}"><span>${esc(c.loc)} · ${esc(c.name)}</span><q>${esc(clip(c.hl))}</q><em>Open the annotation →</em></a>`).join('')}</div>` : ''}
            ${ov ? `<h2>How the Court has read it</h2>${ov.paras.slice(0, 3).map(p => `<p>${p}</p>`).join('')}
            <p class="attrib">From the <i>Constitution Annotated</i> (Congressional Research Service), “${esc(ov.title)}”; public domain. <a href="#/corner/constitution?c=${esc(ovClause.id)}">Read the full annotation, the leading cases and founding-era commentary →</a></p>` : ''}
            ${adv.length ? `<div class="found-next"><span class="f-icon">§</span><div><b>Ready for more? Continue in the advanced section</b><ul>${adv.map(x => `<li><a href="${x.href}">${esc(x.title)}</a> <span>${esc(x.part || '')}</span></li>`).join('')}</ul></div></div>` : ''}
          </section>`;
        })()}
        ${main ? `<h2>Watch</h2>
          <div class="vcarousel" id="vcarousel">
            <div class="vc-stage"></div>
            ${t.videos.length > 1 ? `<button class="vc-nav vc-prev" aria-label="Previous video">‹</button><button class="vc-nav vc-next" aria-label="Next video">›</button>` : ''}
          </div>
          <div class="vc-foot"><div class="embed-cap vc-cap"></div>${t.videos.length > 1 ? `<div class="vc-dots">${t.videos.map((_, i) => `<button data-vi="${i}" aria-label="Video ${i + 1}"></button>`).join('')}</div>` : ''}</div>` : ''}
        ${(t.lectures || []).length ? `<h2>Lectures and debates</h2>
          <p class="muted-line" style="margin-top:-4px">Longer talks, debates and panels on this topic from law schools, universities and civic institutions.</p>
          <div class="vgrid guide-lectures">${t.lectures.map(v => videoTile(v, t.id)).join('')}</div>` : ''}
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
    if (Q) mountQuiz(app, 'guide:' + t.id, Q.guide[t.id] || [], t.cases.map(c => c.n));
    mountCarousel(t.videos, t.id);
    glossify(app.querySelectorAll('.glossable p, .guide-tagline'));
    mountGuideNarration(id);
  }

  /* ------------------------------------------------------------ glossary: hover definitions for legal terms */
  let glossRx = null, glossTerms = null;
  function glossify(nodes) {
    loadData('glossary', 'GLOSSARY').then(GL => {
      if (!glossRx) {
        glossTerms = Object.keys(GL.terms).sort((a, b) => b.length - a.length);
        const pat = glossTerms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s+')).join('|');
        glossRx = new RegExp('\\b(' + pat + ')(?:s|es)?\\b', 'gi');
      }
      const done = new Set();
      nodes.forEach(node => {
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, { acceptNode: n => n.parentElement.closest('a, .gloss, h1, h2, h3') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
        const texts = [];
        while (walker.nextNode()) texts.push(walker.currentNode);
        for (const tn of texts) {
          const txt = tn.nodeValue;
          let m, frag = null, last = 0;
          glossRx.lastIndex = 0;
          while ((m = glossRx.exec(txt))) {
            const key = glossTerms.find(t => t.toLowerCase() === m[1].toLowerCase().replace(/\s+/g, ' '));
            if (!key || done.has(key)) continue;
            done.add(key);
            frag = frag || document.createDocumentFragment();
            frag.append(txt.slice(last, m.index));
            const sp = document.createElement('span');
            sp.className = 'gloss'; sp.dataset.g = key; sp.tabIndex = 0; sp.textContent = m[0];
            frag.append(sp);
            last = m.index + m[0].length;
          }
          if (frag) { frag.append(txt.slice(last)); tn.replaceWith(frag); }
        }
      });
      let tip = document.getElementById('gloss-tip');
      if (!tip) { tip = document.createElement('div'); tip.id = 'gloss-tip'; tip.className = 'gloss-tip'; tip.hidden = true; document.body.append(tip); }
      let hideT;
      const show = el => {
        const g = GL.terms[el.dataset.g];
        if (!g) return;
        clearTimeout(hideT);
        tip.innerHTML = `<b>${esc(el.dataset.g)}</b><p>${esc(g.s)}</p><a href="${esc(g.url)}" target="_blank" rel="noopener">${g.src === 'wex' ? 'Full entry on Cornell LII Wex' : 'U.S. Courts glossary'} ↗</a><small>${g.src === 'wex' ? 'Wex, Legal Information Institute (CC BY-NC-SA)' : 'United States Courts'}</small>`;
        tip.hidden = false;
        const r = el.getBoundingClientRect();
        tip.style.left = Math.min(Math.max(10, r.left + scrollX), document.documentElement.clientWidth - tip.offsetWidth - 10) + 'px';
        tip.style.top = (r.bottom + scrollY + 6) + 'px';
      };
      const hide = () => { hideT = setTimeout(() => { tip.hidden = true; }, 180); };
      document.querySelectorAll('.gloss').forEach(el => {
        el.addEventListener('mouseenter', () => show(el)); el.addEventListener('focus', () => show(el));
        el.addEventListener('mouseleave', hide); el.addEventListener('blur', hide);
      });
      tip.onmouseenter = () => clearTimeout(hideT);
      tip.onmouseleave = hide;
    }).catch(() => {});
  }


  /* ------------------------------------------------------------ statutes in the Supreme Court */
  const STAT_TAGS = { labor: 'Labor & Employment', business: 'Business & Antitrust', environment: 'Environment & Energy', tax: 'Taxation', benefits: 'Social Welfare Programs',
    education: 'Education', health: 'Health', tech: 'Technology & Communications', ip: 'Intellectual Property' };
  const statTagName = t => STAT_TAGS[t] || topicById[t]?.name || t;
  function viewStatutes(id, params) {
    withData([['statutes', 'STATUTES'], ['scotus', 'SCOTUS'], ['case_impact', 'CASE_IMPACT']], (ST, S, I) => {
      if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
      if (id) return renderStatutePage(ST, decodeURIComponent(id), I, params);
      renderStatuteIndex(ST, params);
    });
  }
  function renderStatuteIndex(ST, params) {
    const tag = params.get('tag') || '', q = (params.get('q') || '').trim().toLowerCase();
    const tags = [...new Set(ST.statutes.flatMap(s => s.tags))].sort((a, b) => statTagName(a).localeCompare(statTagName(b)));
    const list = ST.statutes.filter(s => (!tag || s.tags.includes(tag)) && (!q || (s.n + ' ' + s.blurb).toLowerCase().includes(q)));
    const sort = params.get('sort') || 'cases';
    if (sort === 'cases') list.sort((a, b) => b.cases.length - a.cases.length);
    app.innerHTML = `<div class="fade-in"><div class="page-head">
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a><span>/</span><span>Statutes</span></div>
        <h1>Statutes</h1>
        <p>${ST.statutes.length} federal statutes the Supreme Court has interpreted or reviewed, each with a summary, a link to its text, and the cases on this site that turned on it or discuss it. Hover over a statute's name in a case summary to see a short description.</p>${scotusTabs('statutes')}</div>
      <section class="section" style="padding-top:22px">
        <form class="stat-search" data-stat-search><input type="search" name="q" value="${esc(params.get('q') || '')}" placeholder="Find a statute, e.g. Voting Rights Act" aria-label="Find a statute"></form>
        <div class="suggest" data-keep-scroll style="margin:14px 0 6px"><a class="chip ${!tag ? 'on' : ''}" href="${hashFor('statutes', { sort, q: q || undefined })}">All · ${ST.statutes.length}</a>${tags.map(t => `<a class="chip ${tag === t ? 'on' : ''}" href="${hashFor('statutes', { tag: t, sort, q: q || undefined })}">${esc(statTagName(t))} · ${ST.statutes.filter(s => s.tags.includes(t)).length}</a>`).join('')}</div>
        <div class="seg stat-sort" data-keep-scroll role="group" aria-label="Sort"><a class="${sort === 'cases' ? 'on' : ''}" href="${hashFor('statutes', { tag: tag || undefined, q: q || undefined, sort: 'cases' })}">Most cases</a><a class="${sort === 'az' ? 'on' : ''}" href="${hashFor('statutes', { tag: tag || undefined, q: q || undefined, sort: 'az' })}">A–Z</a></div>
        <div class="stat-grid">${list.map(s => `<a class="stat-card" href="#/statutes/${esc(s.id)}"><b>${esc(s.n)}</b><p>${esc(s.blurb)}</p><span>${s.cases.length ? `${fmt(s.cases.length)} case${s.cases.length === 1 ? '' : 's'}` : 'No cases on the site yet'} · ${s.tags.map(statTagName).map(esc).join(', ')}</span></a>`).join('') || '<p class="muted-line">No statutes match.</p>'}</div>
        <p class="attrib" style="margin-top:24px">${esc(ST.src)}</p>
      </section></div>`;
    app.querySelector('[data-stat-search]').addEventListener('submit', e => { e.preventDefault(); location.hash = hashFor('statutes', { tag: tag || undefined, sort, q: e.target.q.value.trim() || undefined }); });
  }
  /* A statute's legislative history: the enacting bill, its sponsor, and the key actions with the recorded votes
     (Congress.gov for laws since 1973, the Wikipedia infobox for older ones), and the public law as enacted. */
  function statuteHistory(s) {
    const L = s.leg;
    if (!L || (!L.actions?.length && !L.plaw)) return '';
    const fromCg = L.src === 'congress';
    const ord = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'));
    const head = [L.bill && (L.url ? `<a href="${esc(L.url)}" target="_blank" rel="noopener">${esc(L.bill)}</a>` : esc(L.bill)) + (L.congress ? `, ${ord(L.congress)} Congress` : ''),
      L.sponsor && `sponsored by ${esc(L.sponsor)}`, L.title && fromCg && `“${esc(L.title)}”`].filter(Boolean).join(' · ');
    const rows = (L.actions || []).map(a => `<dt>${esc(fmtDate(a.d))}</dt><dd>${esc(a.t)}${a.v ? ` <b>${esc(a.v)}</b>` : ''}${a.url ? ` · <a href="${esc(a.url)}" target="_blank" rel="noopener">${/govtrack/.test(a.url) ? 'vote' : 'roll call'} ↗</a>` : ''}${a.cr ? ` · <a href="${esc(a.cr.url)}" target="_blank" rel="noopener" title="Congressional Record, daily edition">Cong. Rec. ${esc(a.cr.pages)} ↗</a>` : ''}</dd>`).join('');
    return `<h2>Legislative history</h2>
        ${head ? `<p class="muted-line" style="margin-top:-6px">${head}</p>` : ''}
        ${rows ? `<dl class="kv" style="grid-template-columns:150px 1fr;margin:10px 0 6px">${rows}</dl>` : ''}
        ${L.plaw ? `<p><a href="${esc(L.plaw.url)}" target="_blank" rel="noopener">The law as enacted: ${esc(L.plaw.label)} ↗</a></p>` : ''}
        <p class="attrib">${rows ? (fromCg ? 'Bill, sponsor, key actions and recorded votes from <a href="https://www.congress.gov/" target="_blank" rel="noopener">Congress.gov</a> (Library of Congress); roll calls from the House Clerk and the Senate; Congressional Record pages on GovInfo.' : `Bill, sponsor and votes from the legislative-history box of the Wikipedia article <a href="${esc(s.wiki.url)}" target="_blank" rel="noopener">“${esc(s.wiki.title)}”</a> (CC BY-SA 4.0); Congress.gov has no bill record for laws this old.`) + ' ' : ''}${L.plaw ? 'Enacted text from GovInfo (U.S. Government Publishing Office).' : ''}</p>`;
  }

  function renderStatutePage(ST, id, I, params) {
    const s = ST.statutes.find(x => x.id === id);
    if (!s) return viewNotFound();
    const all = params.get('all') === '1';
    const cs = s.cases.map(cid => caseById.get(cid)).filter(Boolean);
    const shown = all ? cs : cs.slice(0, 25);
    let lastH = null;
    const body = s.paras.map(p => { const h = p.h && p.h !== lastH ? `<h3>${esc(p.h)}</h3>` : ''; lastH = p.h; return h + `<p>${esc(p.p)}</p>`; }).join('');
    const related = ST.statutes.filter(x => x.id !== s.id && x.tags.some(t => s.tags.includes(t))).sort((a, b) => b.tags.filter(t => s.tags.includes(t)).length - a.tags.filter(t => s.tags.includes(t)).length || b.cases.length - a.cases.length).slice(0, 8);
    app.innerHTML = `<div class="fade-in"><div class="article">
      <div>
        <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a><span>/</span><a href="#/statutes">Statutes</a></div>
        <h1>${esc(s.n)}</h1>
        <div class="publine">${[s.enacted && `Enacted by the ${s.enacted}`, s.publaw && `Pub. L. ${s.publaw.replace(/^Pub\.?\s*L\.?\s*(No\.)?\s*/i, '')}`, s.stat].filter(Boolean).map(esc).join(' · ') || 'Federal statute'}</div>
        <div class="abstract plain">${esc(s.blurb)}</div>
        <div class="actions">${s.link ? `<a class="btn btn-primary" href="${esc(s.link.url)}" target="_blank" rel="noopener">Read the statute ↗</a>` : ''}${s.wiki.url ? `<a class="btn btn-ghost" href="${esc(s.wiki.url)}" target="_blank" rel="noopener">Wikipedia ↗</a>` : ''}</div>
        <h2>About the statute</h2>
        <div class="prose-sm stat-body">${body}</div>
        <p class="attrib">Text adapted from the Wikipedia article <a href="${esc(s.wiki.url)}" target="_blank" rel="noopener">“${esc(s.wiki.title)}”</a>, licensed under <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>.${s.link ? ` Statute text: ${esc(s.link.label)}.` : ''}</p>
        ${statuteHistory(s)}
        <h2>Supreme Court cases <small>(${fmt(cs.length)})</small></h2>
        ${cs.length ? `<p class="muted-line" style="margin-top:-6px">Ranked by later citations. ${s.coded ? `${fmt(s.coded)} turned on this statute according to the Supreme Court Database; the rest name it in their summaries.` : 'Cases whose summaries name this statute.'}</p>
          <ul class="stat-cases">${shown.map(c => { const m = I.c[c.id]; return `<li><a href="#/case/${esc(c.id)}"><b>${esc(c.n)}</b> <span>${esc(c.cit || '')}${c.y ? ` (${c.y})` : ''}</span></a>${c.ds ? `<p>${esc(c.ds.length > 220 ? c.ds.slice(0, 220).replace(/\s+\S*$/, '') + '…' : c.ds)}</p>` : ''}${m ? `<em>${fmt(m[2])} later citations</em>` : ''}</li>`; }).join('')}</ul>
          ${!all && cs.length > 25 ? `<a class="btn btn-ghost" href="${hashFor('statutes/' + s.id, { all: 1 })}">Show all ${fmt(cs.length)} cases</a>` : ''}` : '<p class="muted-line">No cases on the site name this statute yet.</p>'}
      </div>
      <aside>
        <div class="panel"><h4>Details</h4><dl class="kv">
          ${s.enacted ? `<dt>Enacted by</dt><dd>${esc(s.enacted)}</dd>` : ''}
          ${s.publaw ? `<dt>Public law</dt><dd>${esc(s.publaw)}</dd>` : ''}
          ${s.stat ? `<dt>Statutes at Large</dt><dd>${esc(s.stat)}</dd>` : ''}
          ${s.link ? `<dt>Text</dt><dd><a href="${esc(s.link.url)}" target="_blank" rel="noopener">${esc(s.link.label)}</a></dd>` : ''}
          ${s.leg && s.leg.bill ? `<dt>Bill</dt><dd>${s.leg.url ? `<a href="${esc(s.leg.url)}" target="_blank" rel="noopener">${esc(s.leg.bill)}</a>` : esc(s.leg.bill)}</dd>` : ''}
          ${s.leg && s.leg.plaw && (!s.link || s.leg.plaw.url !== s.link.url) ? `<dt>As enacted</dt><dd><a href="${esc(s.leg.plaw.url)}" target="_blank" rel="noopener">${esc(s.leg.plaw.label)}</a></dd>` : ''}
          <dt>Areas</dt><dd>${s.tags.map(t => `<a class="tag" href="${hashFor('statutes', { tag: t })}">${esc(statTagName(t))}</a>`).join(' ')}</dd>
        </dl></div>
        ${related.length ? `<div class="panel"><h4>Related statutes</h4><ul class="mini-list">${related.map(x => `<li><a class="t" href="#/statutes/${esc(x.id)}">${esc(x.n)}</a><div class="m">${fmt(x.cases.length)} cases</div></li>`).join('')}</ul></div>` : ''}
      </aside></div></div>`;
  }
  // hover blurbs: wrap the first mention of each statute in a link to its page with a two-sentence tooltip
  let statRx = null;
  function statutify(nodes) {
    nodes = [...nodes].filter(Boolean);
    if (!nodes.length) return;
    loadData('statutes', 'STATUTES').then(ST => {
      if (!statRx) statRx = ST.statutes.map(s => { try { return [s, new RegExp(s.rx.replace(/\(\?i\)/g, ''), 'g')]; } catch (e) { return null; } }).filter(Boolean);
      const done = new Set();
      nodes.forEach(node => {
        if (!node.isConnected) return;
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, { acceptNode: n => n.parentElement.closest('a, .stat-ref, .gloss, h1, h2, h3, button') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
        const texts = [];
        while (walker.nextNode()) texts.push(walker.currentNode);
        for (const tn of texts) {
          const txt = tn.nodeValue;
          const hits = [];
          for (const [s, rx] of statRx) {
            if (done.has(s.id)) continue;
            rx.lastIndex = 0;
            const m = rx.exec(txt);
            if (m && m[0].length > 2 && !hits.some(h => m.index < h.end && m.index + m[0].length > h.start)) hits.push({ s, start: m.index, end: m.index + m[0].length });
          }
          if (!hits.length) continue;
          hits.sort((a, b) => a.start - b.start);
          const frag = document.createDocumentFragment();
          let last = 0;
          for (const h of hits) {
            done.add(h.s.id);
            frag.append(txt.slice(last, h.start));
            const a = document.createElement('a');
            a.className = 'stat-ref'; a.href = '#/statutes/' + h.s.id; a.dataset.s = h.s.id; a.textContent = txt.slice(h.start, h.end);
            frag.append(a);
            last = h.end;
          }
          frag.append(txt.slice(last));
          tn.replaceWith(frag);
        }
      });
      let tip = document.getElementById('gloss-tip');
      if (!tip) { tip = document.createElement('div'); tip.id = 'gloss-tip'; tip.className = 'gloss-tip'; tip.hidden = true; document.body.append(tip); }
      let hideT;
      const show = el => {
        const s = ST.statutes.find(x => x.id === el.dataset.s);
        if (!s) return;
        clearTimeout(hideT);
        tip.innerHTML = `<b style="text-transform:none">${esc(s.n)}</b><p>${esc(s.blurb)}</p><a href="#/statutes/${esc(s.id)}">Read more and see ${fmt(s.cases.length)} cases →</a><small>Summary from Wikipedia (CC BY-SA 4.0)</small>`;
        tip.hidden = false;
        const r = el.getBoundingClientRect();
        tip.style.left = Math.min(Math.max(10, r.left + scrollX), document.documentElement.clientWidth - tip.offsetWidth - 10) + 'px';
        tip.style.top = (r.bottom + scrollY + 6) + 'px';
      };
      const hide = () => { hideT = setTimeout(() => { tip.hidden = true; }, 180); };
      nodes.forEach(n => n.querySelectorAll('.stat-ref:not([data-tip])').forEach(el => {
        el.dataset.tip = 1;
        el.addEventListener('mouseenter', () => show(el)); el.addEventListener('focus', () => show(el));
        el.addEventListener('mouseleave', hide); el.addEventListener('blur', hide);
        el.addEventListener('click', () => { tip.hidden = true; });
      }));
      tip.onmouseenter = () => clearTimeout(hideT);
      tip.onmouseleave = hide;
    }).catch(() => {});
  }


  /* ------------------------------------------------------------ narration (Kokoro voice, follow-along highlighting) */
  // mountNarration(key, host, els): a Listen bar inserted after `host`; els[i] is the page element for timing index i
  let narrScrolledAt = 0;   // the page stops following the narration for a few seconds after the reader scrolls
  ['wheel', 'touchmove', 'keydown'].forEach(ev => addEventListener(ev, () => { narrScrolledAt = Date.now(); }, { passive: true }));
  const fmtClock = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

  /* ------------------------------------------------------------ audio dock: once any audio on the page starts (guide
     narration, Constitution Annotated essays, oral arguments), a bar fixed to the bottom of the window shows what is
     playing with play/pause, a seekable progress bar and the time, so the reader need not scroll back to the player */
  const dock = document.createElement('div');
  dock.className = 'audio-dock';
  dock.hidden = true;
  dock.innerHTML = `<button class="dock-play" aria-label="Pause"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="i-play" d="M8 5v14l11-7z"/><path class="i-pause" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg></button>
    <div class="dock-main"><div class="dock-title"></div><div class="dock-bar" role="slider" aria-label="Seek" tabindex="0"><i></i></div></div>
    <span class="dock-time">0:00</span>
    <button class="dock-close" aria-label="Stop and close">×</button>`;
  document.body.appendChild(dock);
  let dockAudio = null;
  const dockFill = dock.querySelector('.dock-bar i'), dockTime = dock.querySelector('.dock-time'), dockPlay = dock.querySelector('.dock-play');
  const dockHide = () => { dock.hidden = true; document.body.classList.remove('has-dock'); };
  const dockSync = () => {
    const a = dockAudio;
    if (!a || !a.isConnected) return dockHide();
    const d = isFinite(a.duration) ? a.duration : 0;
    dockFill.style.width = d ? (100 * a.currentTime / d) + '%' : '0';
    dockTime.textContent = fmtClock(a.currentTime) + (d ? ' / ' + fmtClock(d) : '');
    dock.classList.toggle('playing', !a.paused);
    dockPlay.setAttribute('aria-label', a.paused ? 'Play' : 'Pause');
  };
  const dockTitle = a => {
    const narr = a.closest('.narr');
    if (narr) {          // the section the Listen bar belongs to: the essay's title, or the page's heading
      const essay = narr.closest('details.essay');
      const h = essay ? essay.querySelector('summary') : null;
      return (h ? h.textContent : (app.querySelector('h1') || {}).textContent || 'Narration').trim().replace(/\s+/g, ' ');
    }
    if (a.dataset.dockTitle) return a.dataset.dockTitle;   // set by the player that owns it (podcast episodes)
    const tab = app.querySelector('.player-tabs .on');   // an oral argument: the case and the recording
    return [(app.querySelector('h1') || {}).textContent, tab && tab.lastChild.textContent].filter(Boolean).join(' · ').trim().replace(/\s+/g, ' ') || 'Audio';
  };
  document.addEventListener('play', e => {
    if (e.target.tagName !== 'AUDIO') return;
    dockAudio = e.target;
    dock.querySelector('.dock-title').textContent = dockTitle(e.target);
    dock.hidden = false;
    document.body.classList.add('has-dock');
    dockSync();
  }, true);
  ['pause', 'timeupdate', 'durationchange', 'seeked'].forEach(ev => document.addEventListener(ev, e => { if (e.target === dockAudio) dockSync(); }, true));
  document.addEventListener('ended', e => { if (e.target === dockAudio) { dockSync(); dockHide(); } }, true);
  addEventListener('hashchange', () => setTimeout(dockSync, 50));      // a new page removes its players (and stops them)
  dockPlay.addEventListener('click', () => { if (!dockAudio) return; dockAudio.paused ? dockAudio.play() : dockAudio.pause(); });
  dock.querySelector('.dock-close').addEventListener('click', () => { if (dockAudio) dockAudio.pause(); dockHide(); });
  const dockSeek = frac => { if (dockAudio && isFinite(dockAudio.duration)) dockAudio.currentTime = Math.max(0, Math.min(1, frac)) * dockAudio.duration; };
  dock.querySelector('.dock-bar').addEventListener('click', e => { const r = e.currentTarget.getBoundingClientRect(); dockSeek((e.clientX - r.left) / r.width); });
  dock.querySelector('.dock-bar').addEventListener('keydown', e => {
    if (!dockAudio) return;
    if (e.key === 'ArrowRight') dockAudio.currentTime += 10;
    else if (e.key === 'ArrowLeft') dockAudio.currentTime = Math.max(0, dockAudio.currentTime - 10);
    else if (e.key === ' ') { e.preventDefault(); dockPlay.click(); }
  });

  function mountNarration(key, host, els) {
    if (!host) return;
    loadData('narration', 'NARRATION').then(N => {
      const it = N.items[key];
      if (!it || (it.r2 && !N.r2) || !host.isConnected) return;
      const base = (it.r2 ? N.r2.replace(/\/$/, '') + '/' : '') + it.p;
      const bar = document.createElement('div');
      bar.className = 'narr';
      bar.innerHTML = `<button class="narr-play" aria-label="Listen to this section"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="i-play" d="M8 5v14l11-7z"/><path class="i-pause" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg><span>Listen</span></button>
        <div class="narr-track" hidden><div class="narr-bar"><i></i></div><span class="narr-time">0:00 / ${fmtClock(it.d)}</span><button class="narr-speed" title="Playback speed">1×</button></div>
        <span class="narr-len">${Math.max(1, Math.round(it.d / 60))} min</span>
        <audio preload="none" src="${esc(base)}.mp3"></audio>`;
      host.insertAdjacentElement('afterend', bar);
      const audio = bar.querySelector('audio'), play = bar.querySelector('.narr-play'), track = bar.querySelector('.narr-track');
      const fill = bar.querySelector('.narr-bar i'), time = bar.querySelector('.narr-time'), speedBtn = bar.querySelector('.narr-speed');
      let segs = null, cur = -1;
      const SPEEDS = [1, 1.25, 1.5, 2, 0.75];
      const loadSegs = () => segs ? Promise.resolve(segs) : fetch(base + '.json').then(r => r.json()).then(j => (segs = j.s));
      const mark = i => {
        if (i === cur) return;
        if (cur >= 0 && els[cur]) els[cur].classList.remove('narr-on');
        cur = i;
        const el = els[i];
        if (!el) return;
        el.classList.add('narr-on');
        const r = el.getBoundingClientRect();
        if (Date.now() - narrScrolledAt > 5000 && (r.top < 80 || r.bottom > innerHeight - 40)) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      };
      audio.addEventListener('timeupdate', () => {
        const t = audio.currentTime;
        fill.style.width = (100 * t / (audio.duration || it.d)) + '%';
        time.textContent = `${fmtClock(t)} / ${fmtClock(audio.duration || it.d)}`;
        if (!segs) return;
        let k = segs.findIndex(s => t < s[1]);
        if (k < 0) k = segs.length - 1;
        mark(segs[k][2]);
      });
      audio.addEventListener('play', () => { bar.classList.add('playing'); document.querySelectorAll('audio').forEach(a => a !== audio && a.pause()); });
      audio.addEventListener('pause', () => bar.classList.remove('playing'));
      audio.addEventListener('ended', () => { if (cur >= 0 && els[cur]) els[cur].classList.remove('narr-on'); cur = -1; });
      play.addEventListener('click', () => {
        if (!audio.paused) return audio.pause();
        track.hidden = false; bar.classList.add('started');
        // play inside the click itself (browsers refuse play() once the gesture has passed); the timing file for the
        // highlighting loads alongside, and its absence only turns the highlighting off
        audio.play().catch(() => toast('The audio could not be played.'));
        loadSegs().catch(() => {});
      });
      bar.querySelector('.narr-bar').addEventListener('click', e => {
        const r = e.currentTarget.getBoundingClientRect();
        audio.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (audio.duration || it.d);
      });
      speedBtn.addEventListener('click', () => {
        const nx = SPEEDS[(SPEEDS.indexOf(audio.playbackRate) + 1) % SPEEDS.length];
        audio.playbackRate = nx; speedBtn.textContent = nx + '×';
      });
      // click a paragraph while listening to jump to it
      els.forEach((el, i) => el && el.addEventListener('click', e => {
        if (!bar.classList.contains('started') || !segs || e.target.closest('a, button')) return;
        const s = segs.find(x => x[2] === i);
        if (s) { audio.currentTime = s[0] + 0.01; if (audio.paused) audio.play(); }
      }));
    }).catch(() => {});
  }
  function mountGuideNarration(id) {
    const h1 = app.querySelector('.guide-title h1'), tag = app.querySelector('.guide-tagline');
    const found = app.querySelector('section.found');
    const els = [h1, tag, ...(found ? found.querySelectorAll('h2, h3, p:not(.attrib), .found-clause') : [])];
    mountNarration('guide/' + id, tag || h1, els);
  }
  function mountDoctrineNarration() {
    app.querySelectorAll('section.doc-sec').forEach(sec => {
      const h = sec.querySelector('.doc-h'), body = sec.querySelector('.doc-body');
      mountNarration('doctrine/' + sec.id.replace(/^sec-/, ''), h, [h, ...(body ? body.querySelectorAll('p, li, .testbox-h') : [])]);
    });
    // Constitution Annotated essays (audio on Cloudflare R2): 0 is the essay title, then its paragraphs
    app.querySelectorAll('details.essay[data-essay]').forEach(d => {
      const sum = d.querySelector('summary'), body = d.querySelector('.essay-body');
      mountNarration('conan/' + d.dataset.essay, sum, [sum.querySelector('b'), ...(body ? body.querySelectorAll(':scope > p') : [])]);
    });
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
    const st = { cat: params.get('cat') || '', sort: params.get('sort') || '', q: params.get('q') || '', set: params.get('set') === 'all' ? 'all' : '' };
    const go = patch => { location.hash = hashFor('books', Object.assign({}, st, patch)); };
    const pq = parseQuery(st.q);
    const pool = st.set === 'all' ? B.books : B.books.filter(b => b.essential !== false);
    // influence: essentials first, then scholarly citations, then Goodreads readership
    const influence = b => (b.essential !== false ? 1e7 : 0) + (b.cites?.n ?? 0) * 50 + Math.min(b.gr?.count ?? 0, 200000) / 20;
    let list = pool.filter(b => (!st.cat || b.cat === st.cat || (st.cat === 'Introductions & Primers' && b.intro)) &&
      (!pq.terms.length || pq.terms.every(t => (b.title + ' ' + b.authors.join(' ') + ' ' + b.note).toLowerCase().includes(t))));
    if (st.sort === 'rating') list = list.slice().sort((a, b) => (b.gr?.rating ?? 0) - (a.gr?.rating ?? 0));
    else if (st.sort === 'popular') list = list.slice().sort((a, b) => (b.gr?.count ?? 0) - (a.gr?.count ?? 0));
    else if (st.sort === 'cited') list = list.slice().sort((a, b) => (b.cites?.n ?? -1) - (a.cites?.n ?? -1));
    else if (st.sort === 'year') list = list.slice().sort((a, b) => a.year - b.year);
    else list = list.slice().sort((a, b) => influence(b) - influence(a));
    const grouped = !st.sort && !st.q && !st.cat;
    const nEss = B.books.filter(b => b.essential !== false).length;
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Books</span></div>
        <h1>${st.set === 'all' ? 'Books' : 'Essential books'}</h1>
        <p>${st.set === 'all' ? `${fmt(B.books.length)} influential books on American constitutional law, including the ${nEss} essentials.` : `${nEss} essential books on American constitutional law, from founding-era classics to today's debates.`} Each book page links to law review book reviews, the publisher, and reader ratings.</p></div>
      <div class="wrap" style="padding-top:22px">
        <div class="lec-filters">
          <form id="bk-form" class="lec-search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="bk-q" type="search" placeholder="Search books or authors…" value="${esc(st.q)}"></form>
          <div class="seg" role="group" aria-label="Collection">
            <button data-set="" class="${st.set !== 'all' ? 'on' : ''}">Essential (${nEss})</button>
            <button data-set="all" class="${st.set === 'all' ? 'on' : ''}">All books (${fmt(B.books.length)})</button>
          </div>
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
          const items = list.filter(b => b.cat === c);
          return items.length ? `<section class="book-sec"><div class="section-head"><div><h2 style="font-size:26px">${esc(c)}</h2></div><a class="link-arrow" data-scroll-top href="${hashFor('books', { cat: c, set: st.set })}">View all ${items.length} →</a></div><div class="bgrid one-row">${items.slice(0, 12).map(bookTile).join('')}</div></section>` : '';
        }).join('') : (list.length ? `<div class="bgrid">${list.map(bookTile).join('')}</div>` : '<div class="empty"><h3>No books match</h3></div>')}
        <p class="attrib" style="margin-top:30px">Covers and metadata from Open Library. Ratings from Goodreads.</p>
      </div></div>`;
    document.getElementById('bk-form').addEventListener('submit', e => { e.preventDefault(); go({ q: document.getElementById('bk-q').value.trim() }); });
    app.querySelectorAll('[data-set]').forEach(b => b.addEventListener('click', () => go({ set: b.dataset.set })));
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
        ${b.note ? `<h2>Why it matters</h2>
        <div class="callout">${esc(b.note)}</div>` : ''}
        ${b.blurb ? `<h2>About the book</h2><p class="book-blurb">${esc(b.blurb)}</p><p class="attrib">Description via Goodreads (truncated). <a href="${esc(b.gr.url)}" target="_blank" rel="noopener" style="color:var(--accent)">Full description ↗</a></p>` : ''}
        <h2>Law review book reviews</h2>
        ${revs.length ? `<div class="cards">${revs.map(a => card(a)).join('')}</div>` : ''}
        ${b.oaReviews ? `${revs.length ? '<h3 style="margin-top:18px">More reviews</h3>' : ''}<ul class="mini-list">${b.oaReviews.map(r => `<li><a class="t" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.t)}</a><div class="m">${esc((r.a || []).join(', '))}${r.j ? ' · ' + esc(r.j) : ''}${r.y ? ' ' + r.y : ''}</div></li>`).join('')}</ul><p class="attrib">Reviews outside this index, found through OpenAlex; open a link to confirm it is about this book.</p>` : ''}
        ${!revs.length && !b.oaReviews ? '<p class="muted-line">No reviews of this book are in the index yet. Try the searches below.</p>' : ''}
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
  const SOURCE_ORDER = ['documents', 'madison', 'federalist', 'antifederalist', 'statutes', 'blackstone', 'tucker', 'story', 'rawle', 'kent', 'cooley', 'vattel', 'locke'];
  /* ------------------------------------------------------------ annotated Constitution (Originalist's Corner) */
  const SRC_LABEL = { story: 'Story, Commentaries (1833)', rawle: 'Rawle, View of the Constitution (1829)', tucker: "Tucker's Blackstone (1803)", federalist: 'The Federalist',
    madison: "Madison's Notes of Debates", kent: "Kent's Commentaries", cooley: "Cooley's General Principles", antifederalist: 'The Anti-Federalists', blackstone: "Blackstone's Commentaries",
    documents: 'Founding documents', vattel: "Vattel's Law of Nations", locke: 'Locke, Two Treatises' };
  function viewConstitution(params) {
    withData([['constitution', 'CONSTITUTION'], ['scotus', 'SCOTUS'], ['case_impact', 'CASE_IMPACT']], (K, S, I) => renderConstitution(K, S, I, params));
  }
  function renderConstitution(K, S, I, params) {
    if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
    const sel = params.get('c') || '';
    const mode = params.get('mode') === 'dict' ? 'dict' : 'clauses';
    const clause = K.clauses.find(c => c.id === sel);
    const byUnit = {};
    for (const c of K.clauses) (byUnit[c.unit] = byUnit[c.unit] || []).push(c);
    const go = patch => { const p = { c: sel, mode: mode === 'dict' ? 'dict' : '' }; Object.assign(p, patch); location.hash = hashFor('corner/constitution', p); };
    // a unit's text with its clauses marked (or, in dictionary mode, every word clickable)
    const unitHtml = u => {
      const t = u.text;
      if (mode === 'dict') return t.split(/([A-Za-z]+(?:['’][a-z]+)?)/).map((w, i) => i % 2 ? `<span class="ac-w">${w}</span>` : esc(w)).join('');
      const marks = [];
      for (const c of byUnit[u.id] || []) {
        const at = t.indexOf(c.hl);
        if (at >= 0 && !marks.some(m => at < m.end && at + c.hl.length > m.start)) marks.push({ start: at, end: at + c.hl.length, c });
      }
      marks.sort((a, b) => a.start - b.start);
      let out = '', pos = 0;
      for (const m of marks) {
        out += esc(t.slice(pos, m.start)) + `<a class="ac-cl${m.c.id === sel ? ' on' : ''}" href="${hashFor('corner/constitution', { c: m.c.id })}" data-c="${esc(m.c.id)}" title="${esc(m.c.name)}">${esc(t.slice(m.start, m.end))}</a>`;
        pos = m.end;
      }
      return out + esc(t.slice(pos));
    };
    const groups = [];
    for (const u of K.units) { const g = groups[groups.length - 1]; if (!g || g.name !== u.group) groups.push({ name: u.group, units: [u] }); else g.units.push(u); }
    // "Article I, Section 2, Clause 3" -> "Section 2, Clause 3"; "Amendment XIV, Section 1" -> "Section 1"; a lone clause
    // ("Article VII, Clause 1") or a whole amendment ("Amendment I") needs no small label under its heading
    // (u.alias marks a section or article with a single paragraph, which has no clause numbers)
    const shortLabel = u => u.label.replace(/^(Article [IVX]+|Amendment [IVX]+)(?:, ?|$)/, '').replace(/^Preamble$/, '').replace(u.alias ? /(?:, )?Clause 1$/ : /$^/, '');
    const closingHtml = () => {
      const C = K.closing;
      if (!C) return '';
      return `<section class="ac-group ac-closing"><h2>Attestation and signatures</h2>
        ${C.notes.map(n => `<p class="ac-note">${unitHtml({ id: '', text: n })}</p>`).join('')}
        <div class="ac-signers">${C.signers.map(s => `<div class="ac-signer${s.state ? '' : ' pres'}">${s.state ? `<h4>${esc(s.state)}</h4>` : ''}${s.names.map(n => typeof n === 'string' ? `<span>${esc(n)}</span>` : n.full ? `<span>${esc(n.full)}<small>signed “${esc(n.sig)}”</small></span>` : `<span>${esc(n.sig)}</span>`).join('')}${s.role ? `<em>${esc(s.role)}</em>` : ''}</div>`).join('')}</div>
      </section>`;
    };
    const textHtml = groups.map(g => `<section class="ac-group"><h2>${esc(g.name)}</h2>${g.units.map(u => `<div class="ac-unit" id="u-${u.id}">
        ${/^Amendment/.test(u.label) && g.name !== u.label && (!/Section/.test(u.label) || /Section 1$/.test(u.label)) ? `<h3>${esc(u.label.replace(/, Section \d+$/, ''))}</h3>` : ''}
        ${shortLabel(u) ? `<span class="ac-loc">${esc(shortLabel(u))}</span>` : ''}<p>${unitHtml(u)}</p></div>`).join('')}</section>${g.name === 'Article VII' ? closingHtml() : ''}`).join('');
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><span>The Annotated Constitution</span></div>
        <h1>The Annotated Constitution</h1>
        <p>${mode === 'dict' ? 'Select any word to see how period dictionaries defined it: Johnson (1755), Bailey (1755), Webster (1828), and the law dictionaries of Bouvier (1856), Burrill (1860) and Black (1891).' : `Select a highlighted clause to read what it means, how its interpretation has changed, the leading cases and scholarship, and what the founding generation wrote about it. ${K.clauses.length} clauses are annotated.`}</p>
        <div class="ac-tools">
          <div class="seg" role="group" aria-label="Mode"><button data-mode="clauses" class="${mode === 'clauses' ? 'on' : ''}">Clauses</button><button data-mode="dict" class="${mode === 'dict' ? 'on' : ''}">Period dictionaries</button></div>
          ${mode === 'clauses' ? `<select id="ac-jump" class="input" aria-label="Jump to a clause"><option value="">Jump to a clause…</option>${K.clauses.map(c => `<option value="${esc(c.id)}" ${c.id === sel ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select>` : ''}
        </div></div>
      <div class="ac-layout ${clause ? 'open' : ''}">
        <div class="ac-text ${mode === 'dict' ? 'dict' : ''}">${textHtml}<p class="attrib">Text: National Archives transcription, with original spelling and punctuation, checked word for word against Cornell LII and Wikisource's transcription of the 1787 printing. Passages in [brackets] were changed by later amendments. Signatures appear as written on the parchment, with full names from the National Archives' Founding Fathers pages.</p></div>
        ${clause ? `<aside class="ac-panel" id="ac-panel">${clausePanel(clause, I)}</aside>` : ''}
      </div>
      <div class="ac-pop" id="ac-pop" hidden></div>
    </div>`;
    app.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => go({ mode: b.dataset.mode === 'dict' ? 'dict' : '', c: b.dataset.mode === 'dict' ? '' : sel })));
    const jump = document.getElementById('ac-jump');
    if (jump) jump.addEventListener('change', () => { if (jump.value) go({ c: jump.value }); });
    const close = document.getElementById('ac-close');
    if (close) close.addEventListener('click', () => go({ c: '' }));
    if (clause) {
      const el = document.getElementById('u-' + clause.unit);
      if (el) setTimeout(() => { const r = el.getBoundingClientRect(); if (r.top < 120 || r.bottom > innerHeight) el.scrollIntoView({ block: 'center' }); }, 180);   // after the router restores scroll
      app.querySelectorAll('[data-sec]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); document.getElementById('acs-' + a.dataset.sec)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
    }
    if (mode === 'dict') mountWordInspector(K);
  }
  function clausePanel(c, I) {
    const A = window.CL_DATA, artById = new Map((A ? A.articles : []).map(a => [a.id, a]));
    const jname = id => (A && A.journals.find(j => j.id === id) || {}).name || '';
    const secs = [];
    if (c.wiki) secs.push(['overview', 'Overview', `${c.wiki.paras.map(p => `<p>${esc(p)}</p>`).join('')}<p class="attrib">From Wikipedia, <a href="${esc(c.wiki.url)}" target="_blank" rel="noopener">${esc(c.wiki.title)}</a> (CC BY-SA 4.0).</p>`]);
    if (c.conan && c.conan.overview) secs.push(['commentary', 'Commentary', `<h5>${esc(c.conan.overview.title)}</h5>${c.conan.overview.paras.map(p => `<p>${p}</p>`).join('')}
      ${c.conan.dev.length ? `<h5 style="margin-top:18px">How interpretation has developed</h5><div class="ac-dev">${c.conan.dev.map(d => `<details><summary>${esc(d.title)}</summary><p>${d.p}</p></details>`).join('')}</div>` : ''}
      <p class="attrib">From the <i>Constitution Annotated</i> (Congressional Research Service, 2022 ed.), essays ${esc(c.conan.overview.id)}${c.conan.dev.length ? ' and following' : ''}; public domain. <a href="#/library/book/conan/e/${encodeURIComponent(c.conan.overview.id)}">Read these essays in full in the library →</a></p>`]);
    if (c.cases.length) secs.push(['cases', `Leading cases <small>${c.nCases > c.cases.length ? `top ${c.cases.length} of ${fmt(c.nCases)}` : ''}</small>`, `<p class="ac-intro">Cases the Supreme Court Database classifies under this provision, ranked by how often later Supreme Court opinions cite them.</p>
      <ol class="mini-list ranked">${c.cases.map(id => { const k = caseById.get(id); if (!k) return ''; const m = I.c[id]; return `<li><a class="t" href="#/case/${esc(id)}">${esc(k.n)}</a><div class="m">${esc(k.cit || '')}${k.y ? ' · ' + k.y : ''}${m ? ` · ${fmt(m[2])} later Supreme Court citations` : ''}</div></li>`; }).join('')}</ol>`]);
    if (c.articles.length) secs.push(['scholarship', `Scholarship <small>${c.nArticles > c.articles.length ? `most cited ${c.articles.length} of ${fmt(c.nArticles)}` : ''}</small>`, `<ol class="mini-list ranked">${c.articles.map(id => { const a = artById.get(id); if (!a) return ''; return `<li><a class="t" href="${articleHref(a)}">${esc(a.t)}</a><div class="m">${esc((a.a || []).slice(0, 2).join(', '))}${a.a && a.a.length > 2 ? ' et al.' : ''} · ${esc(jname(a.j))}${a.y ? ' ' + a.y : ''}${a.c != null ? ` · ${fmt(a.c)} citations` : ''}</div></li>`; }).join('')}</ol>
      ${c.nArticles > c.articles.length ? `<a class="btn btn-ghost btn-sm ac-all" href="${hashFor('search', { clause: c.id, sort: 'cited' })}">See all ${fmt(c.nArticles)} articles →</a>` : ''}`]);
    if (c.founding.length) secs.push(['founding', 'Founding-era commentary', c.founding.map(p => `<blockquote class="ac-q"><p>${esc(p.t)}</p><footer>${esc(SRC_LABEL[p.s] || p.s)}${p.loc ? ', ' + esc(p.loc) : ''}</footer></blockquote>`).join('')]);
    if (c.statutes.length) secs.push(['statutes', 'Early statutes', `<p class="muted-line" style="margin:0 0 10px">Acts of the first Congresses that put the clause into practice or bear on its early meaning.</p>${c.statutes.map(p => `<blockquote class="ac-q"><p>${esc(p.t)}</p><footer>${esc(p.loc || 'Statutes at Large, vol. 1')}</footer></blockquote>`).join('')}<a class="link-arrow" href="#/library/statutes">All early statutes →</a>`]);
    if ((c.usc || []).length) secs.push(['usc', 'Federal statutes', `<p class="muted-line" style="margin:0 0 10px">Acts of Congress that implement the clause or that the Supreme Court has tested under it.</p><ul>${c.usc.map(s => `<li><a href="#/statutes/${esc(s.id)}">${esc(s.n)}</a></li>`).join('')}</ul>`]);
    return `<div class="ac-panel-head"><div><span class="eyebrow">${esc(c.loc)}</span><h2>${esc(c.name)}</h2></div><button class="icon-btn" id="ac-close" aria-label="Close" title="Close">✕</button></div>
      <blockquote class="ac-clause">“${esc(c.hl)}”</blockquote>
      ${c.lii ? `<a class="ac-lii" href="${esc(c.lii)}" target="_blank" rel="noopener">Read the full Constitution Annotated for this clause at Cornell LII ↗</a>` : ''}
      <nav class="ac-nav">${secs.map(([id, h]) => `<a href="#" data-sec="${id}">${h.replace(/<small>.*<\/small>/, '').trim()}</a>`).join('')}</nav>
      ${secs.map(([id, h, body]) => `<section class="ac-sec" id="acs-${id}"><h4>${h}</h4>${body}</section>`).join('')}`;
  }
  /* The period dictionaries (scripts/build_dictionaries.py): founding-dict.js holds the source list, Johnson, Webster,
     Bouvier and the multi-word terms; founding-dict-more.js adds Bailey, Burrill and Black. Both load together. */
  function loadFoundingDict() {
    return Promise.all([loadData('founding-dict', 'FOUNDING_DICT'), loadData('founding-dict-more', 'FOUNDING_DICT_MORE').catch(() => null)]).then(([D, M]) => {
      if (M && !D._more) {
        for (const [w, v] of Object.entries(M.words || {})) D.words[w] = Object.assign(D.words[w] || {}, v);
        D._more = true;
      }
      return D;
    });
  }
  function mountWordInspector(K) {
    const pop = document.getElementById('ac-pop');
    const text = app.querySelector('.ac-text');
    const hide = () => { pop.hidden = true; text.querySelectorAll('.ac-w.on').forEach(x => x.classList.remove('on')); };
    loadFoundingDict().then(Dct => {
      text.addEventListener('click', e => {
        const w = e.target.closest('.ac-w');
        if (!w) return hide();
        hide(); w.classList.add('on');
        const word = w.textContent.toLowerCase();
        const unit = w.closest('.ac-unit');
        const near = ' ' + (unit ? unit.textContent.toLowerCase() : '').replace(/[^a-z ]+/g, ' ').replace(/\s+/g, ' ') + ' ';
        const sing = s => s.split(' ').map(x => x.length > 4 && /[^s]s$/.test(x) ? x.slice(0, -1) : x).join(' ');
        // the multi-word terms around the word ("letters of marque and reprisal", "letters of marque"), longest first
        const phrases = Object.keys(Dct.phrases).filter(ph => ph.split(' ').some(x => x === word || sing(x) === sing(word)) && (near.includes(' ' + ph + ' ') || sing(near).includes(' ' + sing(ph) + ' '))).sort((a, b) => b.length - a.length);
        const rec = Dct.words[word] || {};
        const M = Dct.meta;
        const block = (label, r, ocr) => r ? `<div class="ac-def"><h5>${esc(label)}${ocr ? ' <small title="Text from OCR of the scanned book, cut at the first unreadable passage">· OCR</small>' : ''}</h5>${r.e.map(e => `<p>${r.hw !== word ? `<b>${esc(r.hw)}</b> ` : ''}${e.pos ? `<i>${esc(e.pos)}</i> ` : ''}${esc(e.t)}</p>`).join('')}</div>` : '';
        const body = phrases.map(ph => Dct.order.map(s => block(`${M[s].label}, ${M[s].year}`, Dct.phrases[ph][s], M[s].ocr)).join('')).join('')
          + Dct.order.map(s => block(`${M[s].label}, ${M[s].year}`, rec[s], M[s].ocr)).join('');
        const used = Dct.order.filter(s => rec[s] || phrases.some(ph => Dct.phrases[ph][s]));
        pop.innerHTML = `<div class="ac-pop-head"><b>${esc(w.textContent)}</b><button class="icon-btn" aria-label="Close">✕</button></div>${body || '<p class="muted-line">No entry in these dictionaries (often a proper name).</p>'}
          <p class="attrib">${used.map(s => esc(M[s].cite)).join('. ')}${used.length ? '.' : ''}</p>`;
        pop.hidden = false;
        const r = w.getBoundingClientRect();
        const left = Math.min(Math.max(12, r.left + scrollX - 40), document.documentElement.clientWidth - pop.offsetWidth - 12);
        pop.style.left = left + 'px';
        pop.style.top = (r.bottom + scrollY + 8) + 'px';
        pop.querySelector('button').addEventListener('click', hide);
      });
    });
  }

  function viewCorner() { withData([['corner', 'CORNER']], C => renderCorner(C)); }
  function renderCorner(C) {
    if (!window.LIB_INDEX) { loadScriptOnce('data/lib-index.js').then(() => { if (lastRoute.path === 'corner') renderCorner(C); }).catch(() => { window.LIB_INDEX = []; }); }
    const srcs = SOURCE_ORDER.map(id => C.sources.find(s => s.id === id)).filter(Boolean);
    app.innerHTML = `<div class="fade-in">
      <section class="hero corner-hero"><div class="hero-inner" style="padding:64px 24px 54px">
        <span class="eyebrow">Originalist's Corner</span>
        <h1 style="max-width:16ch">What the founding generation <em>actually said.</em></h1>
        <p class="lede">Choose a topic and read what Blackstone, the Convention debates, <i>The Federalist</i> and the Anti-Federalists, the acts of the first Congresses, Tucker, Story, Rawle, Kent, Cooley, Vattel and Locke said about it, side by side. The ${fmt(Object.keys(C.passages).length)} passages are drawn from the full texts of ${srcs.length} bodies of founding-era material.</p>
        <div class="suggest" style="margin-top:22px"><a class="chip on" href="#/corner/constitution">The Annotated Constitution →</a><a class="chip" href="#/corner/constitution?mode=dict">Period dictionaries →</a><a class="chip" href="#/library">Browse the library →</a></div>
      </div></section>
      <section class="section corner-what-sec"><div class="corner-what">
        <h2>What is the Originalist's Corner?</h2>
        <p><b>Originalism</b> reads the Constitution according to the meaning its words had when they were adopted. Originalists, and the judges and scholars who disagree with them, argue from the same evidence: the English law the framers inherited, the political philosophy they read, the debates at the Convention and over ratification, and how the first Congresses and early commentators applied the text. The Corner puts that evidence in one place.</p>
        <ul>
          <li><b>Topics.</b> For each of ${C.topics.filter(t => t.n).length} subjects, from judicial review to the right to bear arms, passages from every source side by side (${fmt(Object.keys(C.passages).length)} in all), each linked to its place in the full text.</li>
          <li><b>The Annotated Constitution.</b> Every clause with the founding-era commentary on it, the Constitution Annotated's overview, the leading cases, and period dictionaries for its words, from Johnson and Bailey (1755) and Webster (1828) to the law dictionaries of Bouvier, Burrill and Black.</li>
          <li><b>The library.</b> The full texts behind the passages, and more: Locke, Montesquieu and Sidney, Blackstone, the Revolutionary pamphlets, Madison's notes and Farrand's records, <i>The Federalist</i> and the Anti-Federalists, the first Congresses' acts and the early commentators, to read, highlight and annotate.</li>
        </ul>
        <p class="muted-line">Passages are sorted by topic, so read them in context. All texts are in the public domain or freely licensed.</p>
      </div></section>
      <section class="section" style="padding-top:28px">
        <div class="section-head"><div><h2>Topics</h2><p>Each topic gathers the most relevant passages from every source.</p></div></div>
        <div class="corner-grid">${C.topics.filter(t => t.n).map(t => `<a class="corner-card" href="#/corner/${t.id}">
          <b>${esc(t.name)}</b><span>${esc(t.desc)}</span><em>${t.n} passages · ${Object.keys(C.index[t.id] || {}).length} sources</em></a>`).join('')}</div>
      </section>
      <section class="section">
        <div class="section-head"><div><h2>The sources</h2><p>Public-domain texts, quoted from the original editions, grouped by the part they played. Sources marked “indexed” appear on the topic pages; the others can be read in full in the library.</p></div><a class="link-arrow" href="#/library">Full-text library →</a></div>
        ${SOURCE_SECTIONS.map(([key, name, desc, ids]) => {
          const cards = ids.map(id => {
            if (id.startsWith('lib:')) {
              const b = (window.LIB_INDEX || []).find(x => x.id === id.slice(4));
              return b ? `<div class="jcard src-card">
                <div class="abbr">${esc(b.author)} · ${esc(b.year)}</div>
                <h3>${esc(b.title)}</h3>
                <p class="src-desc">${esc(LIB_DESC[b.id] || '')}</p>
                <div class="foot"><span>Full text · ${fmt(b.chapters)} parts</span><a class="link-arrow" href="#/library/book/${esc(b.id)}">Read →</a></div></div>` : '';
            }
            const s = srcs.find(x => x.id === id);
            return s ? `<div class="jcard src-card">
              <div class="abbr">${esc(s.author)} · ${esc(s.year)}</div>
              <h3>${esc(s.name)}</h3>
              <p class="src-desc">${esc(s.desc)}</p>
              <div class="foot"><span>Indexed · ${fmt(s.n)} paragraphs</span>${libraryLink(s.id)}</div></div>` : '';
          }).filter(Boolean);
          return cards.length ? `<div class="src-group" data-sec="${key}">
            <div class="section-head"><div><h3 class="src-group-h">${esc(name)}</h3><p>${esc(desc)}</p></div>${cards.length > 3 ? `<button class="link-arrow src-more" type="button" data-more="${cards.length}">View all ${cards.length} →</button>` : ''}</div>
            <div class="jgrid${cards.length > 3 ? ' one-row' : ''}">${cards.join('')}</div></div>` : '';
        }).join('')}
      </section>
    </div>`;
    app.querySelectorAll('.src-more').forEach(b => b.addEventListener('click', () => {
      const g = b.closest('.src-group').querySelector('.jgrid'), open = g.classList.toggle('one-row');
      b.textContent = open ? `View all ${b.dataset.more} →` : 'Show fewer ↑';
    }));
    trimMoreButtons();
  }
  // a section whose cards all fit in one row needs no "View all" button
  function trimMoreButtons() {
    app.querySelectorAll('.src-group').forEach(g => {
      const grid = g.querySelector('.jgrid'), b = g.querySelector('.src-more');
      if (b && grid.classList.contains('one-row') && grid.scrollHeight <= grid.clientHeight + 4) { b.remove(); grid.classList.remove('one-row'); }
    });
  }
  // The Corner's sources, grouped. Plain ids are sources indexed for the topic pages (corner.js); "lib:" ids are full texts
  // in the library (lib-index.js), shown with a Read link, so more works can be added without crowding the legal sources.
  const SOURCE_SECTIONS = [
    ['philosophy', 'Philosophical foundations', 'The political philosophy the founders read: natural rights and the social contract, mixed government, the separation of powers and the law of nations.',
      ['locke', 'lib:spirit-of-laws', 'lib:sidney', 'lib:oceana', 'lib:grotius', 'vattel', 'lib:cato', 'lib:hume-political', 'lib:milton-areopagitica', 'lib:paine-rights']],
    ['precedents', 'English law and colonial precedents', 'The common law, charters and declarations of rights the founders inherited, and the first state constitutions built on them.',
      ['blackstone', 'documents', 'lib:mckechnie-magna-carta', 'lib:hallam-constitutional']],
    ['revolution', 'The Revolutionary argument', 'The pamphlets of the imperial crisis and independence, where the colonists worked out their constitutional claims.',
      ['lib:otis', 'lib:farmer-letters', 'lib:summary-view', 'lib:novanglus', 'lib:common-sense', 'lib:thoughts-government', 'lib:notes-virginia', 'lib:burke-america', 'lib:price-civil-liberty', 'lib:paine-crisis']],
    ['framing', 'Framing and ratification', 'The Convention’s debates and the public argument over ratification, for and against.',
      ['madison', 'federalist', 'antifederalist', 'lib:farrand-1-2', 'lib:farrand-3', 'lib:elliot-debates', 'lib:federalist-pamphlets', 'lib:ford-pamphlets', 'lib:ford-essays', 'lib:curtis-history']],
    ['practice', 'Early practice and commentary', 'How the first Congresses, the Virginia and Kentucky Resolutions and the early commentators applied and explained the Constitution.',
      ['statutes', 'lib:state-papers', 'tucker', 'rawle', 'story', 'kent', 'cooley', 'lib:annals-1', 'lib:wilson-lectures', 'lib:annual-messages', 'lib:marshall-washington', 'lib:tucker-slavery']],
  ];
  const LIB_DESC = {
    'spirit-of-laws': 'Montesquieu’s comparative study of laws and governments, the source of the founders’ separation of powers.',
    sidney: 'The republican classic, written against Filmer and published after Sidney’s execution; widely read in the colonies.',
    oceana: 'Harrington’s model commonwealth: balance of property, rotation in office and an empire of laws, not of men.',
    grotius: 'The founding treatise of the law of nature and nations, on just war, property, contracts and treaties.',
    cato: 'Trenchard and Gordon’s essays on liberty, free speech and the dangers of power, among the most quoted works in America.',
    otis: 'Otis’s argument that Parliament’s power is limited by natural law and the British constitution.',
    'farmer-letters': 'Dickinson’s letters against the Townshend duties: Parliament may regulate trade but not tax the colonies.',
    'summary-view': 'Jefferson’s instructions to Virginia’s delegates, denying Parliament any authority over the colonies.',
    novanglus: 'John Adams and Daniel Leonard’s newspaper debate over Parliament’s authority in America.',
    'common-sense': 'Paine’s case for independence and for republican government.',
    'thoughts-government': 'Adams’s plan for republican state constitutions: bicameralism, an independent judiciary and a separate executive.',
    'notes-virginia': 'Jefferson’s account of Virginia, including his critique of its constitution and his views on religious freedom.',
    'farrand-3': 'The delegates’ later letters, speeches and recollections of the Convention, collected by Max Farrand.',
    'federalist-pamphlets': 'James Wilson’s State House Yard speech, Tench Coxe’s Examination and Alexander Contee Hanson’s Remarks.',
    'state-papers': 'The amendments Congress sent to the states in 1789, the Kentucky Resolutions of 1799 and Madison’s Report of 1800.',
    antifederalists: 'Centinel, the Federal Farmer, the Pennsylvania Minority, Randolph, Mercy Otis Warren and James Monroe.',
    'hume-political': 'Hume’s essays on commerce, public credit, the original contract, parties and the idea of a perfect commonwealth, read closely by Madison.',
    'ford-pamphlets': 'Paul Leicester Ford’s collection of ratification pamphlets for and against: Jay, Noah Webster, Dickinson’s Fabius, Mason’s Objections and Iredell’s reply, the Federal Farmer and more.',
    'ford-essays': 'Ford’s collection of newspaper essays from the ratification debate: Agrippa, Cato, Sydney, Luther Martin, the Landholder, Sherman’s Countryman and others.',
    'milton-areopagitica': 'Milton’s plea to Parliament against licensing the press, the classic English argument for a free press.',
    'paine-rights': 'Paine’s reply to Burke: natural rights, the sovereignty of each generation, and written constitutions as acts of the people.',
    'mckechnie-magna-carta': 'A clause-by-clause commentary on the Great Charter, with the history of “the law of the land,” judgment of peers and the later charters.',
    'hallam-constitutional': 'The constitutional struggles from the Tudors to 1760: the Petition of Right, the Long Parliament, habeas corpus, the Revolution of 1688 and the Bill of Rights.',
    'burke-america': 'Burke’s speeches on American taxation and conciliation, his speech to the electors of Bristol on representation, and his letter on the war.',
    'price-civil-liberty': 'Richard Price’s defence of self-government and of the colonies’ cause, widely reprinted in America in 1776.',
    'paine-crisis': 'Paine’s wartime essays, from “These are the times that try men’s souls” to the peace.',
    'curtis-history': 'The first full history of the Confederation, the Convention and ratification, built on Madison’s notes and Elliot’s Debates.',
    'annual-messages': 'The annual messages of Washington, Adams, Jefferson and Madison to Congress: the early presidents’ own account of the Constitution in practice.',
    'marshall-washington': 'Chief Justice Marshall’s life of Washington; the last volumes cover the Confederation, the Constitution and the first administrations.',
    'tucker-slavery': 'St. George Tucker’s 1796 proposal for gradual abolition in Virginia, by the author of the first American commentary on the Constitution.',
    'farrand-1-2': 'Farrand’s day-by-day record of the Convention, May 14 to September 17, 1787: the Journal with Madison’s, Yates’s, King’s and others’ notes side by side.',
    'elliot-debates': 'The state ratifying conventions of Massachusetts, Connecticut, New Hampshire, New York, Pennsylvania, Maryland, Virginia and the Carolinas, with early congressional debates on constitutional questions.',
    'annals-1': 'The First Congress’s debates, March 1789 to February 1790: Madison’s amendments of June 8 and the House debates of August 1789 that became the Bill of Rights.',
    'wilson-lectures': 'Justice James Wilson’s Philadelphia lectures of 1790–91, by a framer and signer: natural law, the Constitution, judicial review, juries and crimes.',
  };
  function libraryLink(sid) {
    const fixed = { federalist: '#/library/federalist', documents: '#/library/documents', statutes: '#/library/statutes' }[sid];
    const book = (window.LIB_INDEX || []).find(b => b.corner === sid) || (window.LIB_INDEX || []).find(b => b.id === sid);
    const href = fixed || (book ? `#/library/book/${book.id}` : '');
    return href ? `<a class="link-arrow" href="${href}">Read →</a>` : '';
  }
  /* ------------------------------------------------------------ book reader (full texts from scripts/library_books.py) */
  const libPosKey = id => 'cl-lib-pos:' + id;
  const libPos = id => { try { return JSON.parse(localStorage.getItem(libPosKey(id)) || 'null'); } catch (e) { return null; } };
  const readerSize = () => +(localStorage.getItem('cl-reader-size') || 0);
  function loadLibBook(id) {
    return (window.LIB_BOOKS || {})[id] ? Promise.resolve(window.LIB_BOOKS[id]) : loadScriptOnce(`data/lib/${id}.js`).then(() => (window.LIB_BOOKS || {})[id]);
  }
  function loadLibChapter(id, n) {
    const k = id + '-' + n;
    return (window.LIB_CHS || {})[k] ? Promise.resolve(window.LIB_CHS[k]) : loadScriptOnce(`data/lib/${k}.js`).then(() => (window.LIB_CHS || {})[k]);
  }
  function viewLibBook(id, n) {
    app.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    const tk = routeToken;
    loadLibBook(id).then(B => {
      if (tk !== routeToken) return;
      if (!B) return viewNotFound();
      if (!n) return renderLibCover(B);
      loadLibChapter(id, n).then(C => { if (tk === routeToken) C ? renderLibChapter(B, C) : viewNotFound(); });
    }).catch(() => viewNotFound());
  }
  // a Constitution Annotated essay by its id: open the part that holds it and scroll to the essay
  function viewLibEssay(id, essay) {
    app.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    loadLibBook(id).then(B => {
      const n = B && B.essays && B.essays[essay];
      if (!n) return viewNotFound();
      try { sessionStorage.setItem('cl-bk-jump', essay); } catch (e) { /* private mode */ }
      location.replace(`#/library/book/${id}/${n}`);
    }).catch(() => viewNotFound());
  }
  const libCrumbs = B => B.shelf === 'gov' || LATER_IDS.includes(B.id) ? '<a href="#/">Home</a><span>/</span><a href="#/library">Library</a>' : `<a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><a href="#/library">Library</a>`;
  const fmtWords = w => w >= 1000 ? Math.round(w / 1000) + 'k words' : w + ' words';
  const readMins = w => Math.max(1, Math.round(w / 230));
  function renderLibCover(B) {
    const pos = libPos(B.id), total = B.toc.reduce((s, c) => s + c[1], 0);
    app.innerHTML = `<div class="fade-in"><div class="bk-cover">
      <div class="crumbs">${libCrumbs(B)}<span>/</span><span>${esc(B.title)}</span></div>
      <div class="bk-title"><span class="eyebrow">${esc(B.author)} · ${esc(B.year)}</span><h1>${esc(B.title)}</h1>
        <p class="muted-line">${B.toc.length} parts · ${fmtWords(total)} · about ${Math.round(readMins(total) / 60)} hours of reading</p>
        <div class="bk-actions">${pos ? `<a class="btn btn-primary" href="#/library/book/${esc(B.id)}/${pos.n}">Continue reading · ${esc((B.toc[pos.n - 1] || [''])[0])}</a><a class="btn btn-ghost" href="#/library/book/${esc(B.id)}/1">Start from the beginning</a>` : `<a class="btn btn-primary" href="#/library/book/${esc(B.id)}/1">Start reading</a>`}</div></div>
      <h2>Contents</h2>
      ${B.toc.length > 40 ? `<form class="lec-search bk-filter" onsubmit="return false"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="bk-filter" type="search" placeholder="Filter the ${B.toc.length} parts…" aria-label="Filter the contents"></form>` : ''}
      <ol class="bk-toc">${B.toc.map(([t, w], i) => `<li class="${pos && pos.n === i + 1 ? 'here' : ''}"><a href="#/library/book/${esc(B.id)}/${i + 1}"><span>${esc(t)}</span><em>${readMins(w)} min</em></a></li>`).join('')}</ol>
      ${window.LexAnnot && LexAnnot.count('book:' + B.id) ? `<h2>Your highlights</h2><div class="bk-hl bk-hl-cover" id="bk-hl-cover">${LexAnnot.listHtml('book:' + B.id, { href: k => `#/library/book/${B.id}/${k}`, title: B.title, author: B.author })}</div>` : ''}
      <p class="attrib">${esc(B.license)}. Source: <a href="${esc(B.src)}" target="_blank" rel="noopener">${esc(B.srcName)}</a>. Headers, page numbers and footnote markers are omitted.</p>
    </div></div>`;
    const flt = document.getElementById('bk-filter');
    if (flt) flt.addEventListener('input', () => { const q = flt.value.trim().toLowerCase(); app.querySelectorAll('.bk-toc li').forEach(li => { li.hidden = !!q && !li.textContent.toLowerCase().includes(q); }); });
    const hl = document.getElementById('bk-hl-cover');
    if (hl) LexAnnot.bindList(hl, 'book:' + B.id, { href: k => `#/library/book/${B.id}/${k}`, title: B.title, author: B.author });
  }
  function renderLibChapter(B, C) {
    const n = C.n, N = B.toc.length;
    const heads = C.b.map((x, i) => x[0] === 'h' ? [i, x[1]] : null).filter(Boolean);
    const words = C.b.reduce((s, x) => s + x[1].split(' ').length, 0);
    const chHref = k => `#/library/book/${B.id}/${k}`;
    app.innerHTML = `<div class="bk-read" style="--bk-size:${readerSize()}">
      <div class="bk-progress"><i id="bk-bar"></i></div>
      <div class="bk-bar">
        <a class="bk-home" href="#/library/book/${esc(B.id)}" title="Book contents"><b>${esc(B.title)}</b><span>${esc(B.author)}</span></a>
        <div class="bk-tools">
          <button class="btn btn-ghost btn-sm" id="bk-toc-btn" aria-expanded="false">Contents</button>
          <button class="btn btn-ghost btn-sm" data-size="-1" title="Smaller text" aria-label="Smaller text">A−</button>
          <button class="btn btn-ghost btn-sm" data-size="1" title="Larger text" aria-label="Larger text">A+</button>
        </div>
      </div>
      <aside class="bk-drawer" id="bk-drawer" hidden><div class="bk-drawer-in">
        <h4>Contents</h4><ol>${B.toc.map(([t, w], i) => `<li class="${i + 1 === n ? 'here' : ''}"><a href="${chHref(i + 1)}"><span>${esc(t)}</span><em>${readMins(w)} min</em></a></li>`).join('')}</ol>
        ${heads.length > 2 ? `<h4>In this part</h4><ol class="bk-sec">${heads.map(([i, t]) => `<li><a href="#" data-jump="${i}">${esc(t.length > 90 ? t.slice(0, 88) + '…' : t)}</a></li>`).join('')}</ol>` : ''}
        ${window.LexAnnot ? '<h4>Your highlights<span data-hl-count></span></h4><div class="bk-hl" data-hl-list></div>' : ''}
      </div></aside>
      <article class="bk-page">
        <div class="bk-chead"><span>Part ${n} of ${N} · ${readMins(words)} min read</span><h1>${esc(C.t)}</h1></div>
        <div class="bk-text">${C.b.map((x, i) => x[0] === 'h' ? `<h3 id="bk-${i}">${esc(x[1])}</h3>` : `<p id="bk-${i}">${esc(x[1])}</p>`).join('')}</div>
        <nav class="bk-nav">${n > 1 ? `<a href="${chHref(n - 1)}"><small>← Previous</small>${esc(B.toc[n - 2][0])}</a>` : '<span></span>'}${n < N ? `<a class="next" href="${chHref(n + 1)}"><small>Next →</small>${esc(B.toc[n][0])}</a>` : `<a class="next" href="#/library/book/${esc(B.id)}"><small>The end</small>Back to the contents</a>`}</nav>
        <p class="attrib">${esc(B.license)}. Source: <a href="${esc(B.src)}" target="_blank" rel="noopener">${esc(B.srcName)}</a>.</p>
      </article>
    </div>`;
    const root = app.querySelector('.bk-read'), drawer = document.getElementById('bk-drawer'), tb = document.getElementById('bk-toc-btn');
    const hdr = document.querySelector('header'); if (hdr && getComputedStyle(hdr).position === 'sticky') root.style.setProperty('--bk-top', hdr.getBoundingClientRect().height + 'px');
    tb.addEventListener('click', () => { drawer.hidden = !drawer.hidden; tb.setAttribute('aria-expanded', String(!drawer.hidden)); });
    drawer.addEventListener('click', e => { const j = e.target.closest('[data-jump]'); if (!j) return; e.preventDefault(); drawer.hidden = true; document.getElementById('bk-' + j.dataset.jump).scrollIntoView({ behavior: 'smooth', block: 'start' }); });
    root.querySelectorAll('[data-size]').forEach(b => b.addEventListener('click', () => {
      const v = Math.max(-2, Math.min(4, readerSize() + +b.dataset.size)); localStorage.setItem('cl-reader-size', v); root.style.setProperty('--bk-size', v);
    }));
    const bkTop = () => (parseFloat(root.style.getPropertyValue('--bk-top')) || 0) + 3 + root.querySelector('.bk-bar').offsetHeight;
    const ann = window.LexAnnot ? LexAnnot.mount({ doc: 'book:' + B.id, ch: String(n), chLabel: C.t, cite: `${B.author}, ${B.title}, ${C.t}`, title: B.title, author: B.author,
      href: k => chHref(k), textEl: root.querySelector('.bk-text'), root, toolsEl: root.querySelector('.bk-tools'), topFn: bkTop,
      onGo: () => { drawer.hidden = true; tb.setAttribute('aria-expanded', 'false'); } }) : {};
    // progress bar and saved place (part and how far into it)
    const pos = libPos(B.id);
    let essayJump = null; try { essayJump = sessionStorage.getItem('cl-bk-jump'); sessionStorage.removeItem('cl-bk-jump'); } catch (e) { /* private mode */ }
    const essayEl = essayJump && [...root.querySelectorAll('.bk-text h3')].find(h => h.textContent.startsWith(essayJump + ' '));
    if (essayEl) requestAnimationFrame(() => essayEl.scrollIntoView({ block: 'start' }));
    else if (ann.hasJump) { /* scrolled to the chosen highlight */ }
    else if (pos && pos.n === n && pos.f > 0.02) requestAnimationFrame(() => window.scrollTo({ top: pos.f * (document.documentElement.scrollHeight - innerHeight) }));
    else window.scrollTo({ top: 0 });
    const bar = document.getElementById('bk-bar'); let tmr = 0;
    const onScroll = () => {
      if (!document.body.contains(bar)) { window.removeEventListener('scroll', onScroll); document.removeEventListener('keydown', onKey); return; }
      const f = Math.min(1, scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight));
      bar.style.width = (f * 100).toFixed(1) + '%';
      clearTimeout(tmr); tmr = setTimeout(() => localStorage.setItem(libPosKey(B.id), JSON.stringify({ n, f: +f.toFixed(4) })), 250);
    };
    const onKey = e => {
      if (!document.body.contains(bar)) { document.removeEventListener('keydown', onKey); return; }
      if (e.target.closest('input,textarea,[contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'ArrowRight' && n < N) location.hash = chHref(n + 1);
      if (e.key === 'ArrowLeft' && n > 1) location.hash = chHref(n - 1);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('keydown', onKey);
    localStorage.setItem(libPosKey(B.id), JSON.stringify({ n, f: pos && pos.n === n ? pos.f : 0 }));
    onScroll();
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
      : p.lib ? `<a href="#/library/book/${esc(p.lib)}/${+p.n || 1}">Read in the library →</a>`
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
          <p class="attrib">Passages are chosen for each topic from the full texts, so read them in context; a few more, picked by hand from the library's convention records, ratification debates and treatises, link to their place in the library. Sources: Lonang Institute (Blackstone, Tucker, Story, Kent, Vattel, Locke), Project Gutenberg (<i>The Federalist</i>), the Avalon Project at Yale Law School (Madison's Notes and founding documents), and Wikisource (<i>U.S. Statutes at Large</i>, vol. 1). All texts are in the public domain.</p>
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
    if (kind === 'book' && seg[2] && seg[3] === 'e' && seg[4]) return viewLibEssay(seg[2], decodeURIComponent(seg[4]));
    if (kind === 'book' && seg[2]) return viewLibBook(seg[2], +seg[3] || 0);
    viewNotFound();
  }
  // later-period texts: listed apart from the founding era
  const LATER_IDS = ['tocqueville', 'union-slavery-war', 'lincoln-speeches', 'twentieth-century', 'webster-speeches', 'lincoln-douglas', 'douglass-writings', 'dred-scott', 'ross-impeachment', 'lynch-reconstruction', 'blaine-congress-2'];
  function renderLibraryHome() {
    const idx = window.LIB_INDEX || [], yr = b => +((String(b.year).match(/\d{4}/) || [9999])[0]);
    const card = b => `<a class="jcard" href="#/library/book/${esc(b.id)}"><div class="abbr">${esc(b.author)} · ${esc(b.year)}</div><h3>${esc(b.title)}</h3><div class="foot"><span>${fmt(b.chapters)} part${b.chapters === 1 ? "" : "s"} · ${fmtWords(b.words)}</span><b>Read →</b></div></a>`;
    const fixed = {
      framing: '<a class="jcard" href="#/library/federalist"><div class="abbr">Hamilton, Madison & Jay · 1787–88</div><h3>The Federalist</h3><div class="foot"><span>85 essays</span><b>Read →</b></div></a>',
      precedents: '<a class="jcard" href="#/library/documents"><div class="abbr">1215–1802</div><h3>Founding documents & state constitutions</h3><div class="foot"><span>Magna Carta to the Danbury letter</span><b>Read →</b></div></a>',
      practice: '<a class="jcard" href="#/library/statutes"><div class="abbr">1789–1799</div><h3>Acts of the First Congresses</h3><div class="foot"><span><i>Statutes at Large</i>, vol. 1</span><b>Read →</b></div></a>',
    };
    const gov = idx.filter(b => b.shelf === 'gov'), later = idx.filter(b => LATER_IDS.includes(b.id)).sort((a, b) => yr(a) - yr(b));
    const placed = new Set([...gov, ...later].map(b => b.id));
    const groups = SOURCE_SECTIONS.map(([key, name, desc, ids]) => {
      const books = idx.filter(b => !placed.has(b.id) && (ids.includes('lib:' + b.id) || (b.corner && ids.includes(b.corner))));
      books.forEach(b => placed.add(b.id));
      return [key, name, desc, [fixed[key] || '', ...books.sort((a, b) => yr(a) - yr(b)).map(card)].filter(Boolean)];
    });
    const rest = idx.filter(b => !placed.has(b.id));
    if (rest.length) groups.push(['other', 'More founding-era texts', '', rest.map(card)]);
    const group = ([key, name, desc, cards]) => cards.length ? `<div class="src-group" data-sec="${key}">
      <div class="section-head"><div><h3 class="src-group-h">${esc(name)}</h3>${desc ? `<p>${esc(desc)}</p>` : ''}</div>${cards.length > 3 ? `<button class="link-arrow src-more" type="button" data-more="${cards.length}">View all ${cards.length} →</button>` : ''}</div>
      <div class="jgrid${cards.length > 3 ? ' one-row' : ''}">${cards.join('')}</div></div>` : '';
    app.innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Library</span></div>
        <h1>The library</h1><p>Full texts you can read here, highlight and take notes on: the founding era’s philosophy, law, pamphlets, debates and early practice; later documents of American constitutional history; and the Library of Congress&rsquo;s <i>Constitution Annotated</i> and CRS Legal Sidebars. Everything here is in the public domain or freely licensed.</p></div>
      <section class="section" style="padding-top:28px"><div class="section-head"><div><h2>The founding era</h2><p>The sources behind the <a href="#/corner">Originalist's Corner</a> and the works that shaped the founders’ thinking, grouped as on the Corner.</p></div></div>
        ${groups.map(group).join('')}</section>
      ${later.length ? `<section class="section" style="padding-top:8px"><div class="section-head"><div><h2>Later historical documents</h2><p>Speeches, proclamations, declarations and executive orders from the nineteenth and twentieth centuries, and Tocqueville’s account of American democracy.</p></div></div><div class="jgrid">${later.map(card).join('')}</div></section>` : ''}
      ${gov.length ? `<section class="section" style="padding-top:8px"><div class="section-head"><div><h2>Congress&rsquo;s legal research</h2><p>U.S. government works from the Congressional Research Service at the Library of Congress: the annotated Constitution and the short legal analyses CRS writes for Congress.</p></div></div><div class="jgrid">${gov.map(card).join('')}</div></section>` : ''}
    </div>`;
    app.querySelectorAll('.src-more').forEach(b => b.addEventListener('click', () => {
      const g = b.closest('.src-group').querySelector('.jgrid'), open = g.classList.toggle('one-row');
      b.textContent = open ? `View all ${b.dataset.more} →` : 'Show fewer ↑';
    }));
    trimMoreButtons();
    if (!window.LIB_INDEX) loadScriptOnce('data/lib-index.js').then(() => { if (lastRoute.path === 'library') renderLibraryHome(); }).catch(() => { window.LIB_INDEX = []; });
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
  function readerPage(crumb, title, meta, paras, nav, extra, annot) {
    app.innerHTML = `<div class="fade-in rd-wrap"><div class="reader">
      <div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/corner">Originalist's Corner</a><span>/</span><a href="#/library">Library</a><span>/</span>${crumb}</div>
      <h1>${esc(title)}</h1>
      <div class="publine">${meta}</div>
      ${annot && window.LexAnnot ? '<div class="rd-tools"><span class="muted-line">Select text to highlight it or quote it into your notes.</span><div class="rd-tools-b"></div></div>' : ''}
      <div class="reader-body">${paras.map((p, i) => `<p id="bk-${i}">${esc(p)}</p>`).join('')}</div>
      ${extra || ''}
      ${nav || ''}
    </div></div>`;
    if (!annot || !window.LexAnnot) return;
    const root = app.querySelector('.rd-wrap');
    const hdr = document.querySelector('header');
    LexAnnot.mount(Object.assign({ textEl: root.querySelector('.reader-body'), root, toolsEl: root.querySelector('.rd-tools-b'),
      topFn: () => hdr && getComputedStyle(hdr).position === 'sticky' ? hdr.getBoundingClientRect().height : 0 }, annot));
  }
  function renderFederalist(F, n) {
    const i = F.findIndex(f => f.n === n); const f = F[i];
    if (!f) return viewNotFound();
    const prev = F[i - 1], next = F[i + 1];
    readerPage('<a href="#/library/federalist">The Federalist</a>', `The Federalist No. ${f.n}`, `${esc(f.title)}${f.author ? ' · ' + esc(f.author) : ''}`, f.paras,
      `<div class="guide-nav">${prev ? `<a href="#/library/federalist/${prev.n}"><small>← No. ${prev.n}</small>${esc(prev.title)}</a>` : '<span></span>'}${next ? `<a href="#/library/federalist/${next.n}" style="text-align:right"><small>No. ${next.n} →</small>${esc(next.title)}</a>` : '<span></span>'}</div>`,
      '<p class="attrib">Text: Project Gutenberg eBook #1404 (public domain).</p>',
      { doc: 'federalist', ch: String(f.n), chLabel: `No. ${f.n}. ${f.title}`, cite: `${f.author ? f.author + ', ' : ''}The Federalist No. ${f.n}`, title: 'The Federalist', author: 'Hamilton, Madison & Jay', href: k => `#/library/federalist/${k}` });
  }
  function renderLibDoc(D, id) {
    const d = D.find(x => x.id === id);
    if (!d) return viewNotFound();
    readerPage('<a href="#/library/documents">Founding documents</a>', d.title, String(d.year), d.paras, '', '<p class="attrib">Text: the Avalon Project at Yale Law School and Wikisource (public domain).</p>',
      { doc: 'documents', ch: d.id, chLabel: d.title, cite: `${d.title} (${d.year})`, title: 'Founding documents', author: '', href: k => `#/library/doc/${k}` });
  }
  function renderStatute(S, id) {
    const s = S.find(x => x.id === id);
    if (!s) return viewNotFound();
    readerPage('<a href="#/library/statutes">Acts of the First Congresses</a>', s.title, `${ordinal(s.cong)} Congress, ${ordinal(s.sess)} Session, ${esc(s.chap)}${s.date ? ' · ' + esc(s.date) : ''} · 1 Stat.`, s.paras, '',
      `<p class="attrib">Text: <i>United States Statutes at Large</i>, vol. 1, transcribed on Wikisource (public domain).</p>`,
      { doc: 'statutes', ch: s.id, chLabel: s.title, cite: `${s.title}, ${ordinal(s.cong)} Cong., ${ordinal(s.sess)} Sess., ${s.chap}, 1 Stat.`, title: 'Acts of the First Congresses', author: '', href: k => `#/library/statute/${k}` });
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
  // case names in quiz text are italicized: full names ("Marbury v. Madison") and the short names of the cases the page
  // discusses ("Marbury", "Lopez"), taken from its case list (first party, or the second when the first is a government)
  const GOV_PARTY = /^(?:United States|State|People|Commonwealth|City|County|Board|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New \w+|North \w+|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South \w+|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\b/;
  const caseShortNames = names => [...new Set(names.map(n => {
    const [a, b] = String(n || '').split(/\s+v\.\s+/);
    const pick = b && GOV_PARTY.test(a) ? b : a;
    return (pick || '').replace(/,.*$/, '').replace(/^(?:The|In re)\s+/, '').split(/\s+/).slice(0, 2).join(' ').replace(/\s+(?:of|the|and|for)$/i, '');
  }).filter(x => x && x.length > 3 && !GOV_PARTY.test(x)))];
  const italicCases = (html, shorts) => {
    // "Board of Regents v. Roth", "City of Los Angeles v. Lyons"; a sentence-opening word ("In", "Under") stays upright
    let t = html.replace(/\b[A-Z][\w.'’&-]+(?: (?:of |the |for |and |&amp; )?[A-Z][\w.'’&-]+)* v\. [A-Z][\w.'’&-]+(?: (?:of |the |for |and )?[A-Z][\w.'’&-]+)*/g, m => {
      const lead = (m.match(/^(?:(?:In|Under|After|Before|Unlike|Like|Compare|See|As|Applying|Following|Both|Why|How|When|Does|Did|The|A|An) )+/) || [''])[0];
      return lead + `<i>${m.slice(lead.length)}</i>`;
    });
    if (shorts && shorts.length) {
      const alt = shorts.map(x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
      const rx = new RegExp('(<i>.*?</i>)|\\b(' + alt + ")(?:'s|’s)?\\b", 'g');
      t = t.replace(rx, (m, inI) => inI ? m : `<i>${m}</i>`);
    }
    return t;
  };
  function mountQuiz(root, key, qs, caseNames) {
    const el = root.querySelector(`[data-quiz="${CSS.escape(key)}"]`);
    if (!el) return;
    const shorts = [...new Set([...caseShortNames(caseNames || []), ...((window.QUIZZES || {}).cases || [])])], I = s => italicCases(esc(s), shorts);
    const list = el.querySelector('.quiz-list'), result = el.querySelector('.quiz-result'), scoreEl = el.querySelector('.quiz-score');
    const shuffle = a => { const b = a.slice(); for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
    let answered = 0, correct = 0;
    const render = () => {
      answered = 0; correct = 0; result.hidden = true;
      list.innerHTML = qs.map((q, qi) => `<li class="quiz-q" data-q="${qi}">
        <p class="quiz-text">${I(q.q)}</p>
        <div class="quiz-opts">${shuffle(q.o.map((o, i) => [o, i])).map(([o, i]) => `<button class="quiz-opt" data-i="${i}"><span class="quiz-mark"></span>${I(o)}</button>`).join('')}</div>
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
      exp.innerHTML = `<b>${ok ? 'Correct.' : 'Not quite.'}</b> ${I(q.e || '')}`;
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

  /* ------------------------------------------------------------ Learning Center (spaced-repetition flashcards and games) */
  // Progress lives in this browser, per named profile: localStorage['cl-fc-profiles'] and ['cl-fc:<profile>'].
  const FC = {
    MIN: 60e3, DAY: 864e5,
    LEARN_STEPS: [1, 10],        // minutes
    RELEARN_STEPS: [10],         // minutes
    GRAD_IVL: 1, EASY_IVL: 4,    // days
    START_EASE: 2.5, MIN_EASE: 1.3,
  };
  const dayKey = (t = Date.now()) => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const startOfDay = (t = Date.now()) => { const d = new Date(t); d.setHours(0, 0, 0, 0); return d.getTime(); };
  function fcProfiles() {
    let p; try { p = JSON.parse(localStorage.getItem('cl-fc-profiles')); } catch (e) {}
    if (!p || !p.list || !p.list.length) p = { current: 'Default', list: ['Default'] };
    return p;
  }
  const fcSaveProfiles = p => localStorage.setItem('cl-fc-profiles', JSON.stringify(p));
  function fcLoad() {
    const prof = fcProfiles().current;
    let s; try { s = JSON.parse(localStorage.getItem('cl-fc:' + prof)); } catch (e) {}
    s = s || {};
    s.settings = Object.assign({ newPerDay: 20, reviewsPerDay: 200 }, s.settings || {});
    s.cards = s.cards || {}; s.log = s.log || [];
    if (!s.day || s.day.date !== dayKey()) s.day = { date: dayKey(), newDone: 0, revDone: 0 };
    s.profile = prof;
    return s;
  }
  const fcSave = s => { const { profile, ...rest } = s; localStorage.setItem('cl-fc:' + profile, JSON.stringify(rest)); };
  function fcState(s, id) { return s.cards[id] || { q: 'new' }; }
  // Anki-style scheduling: returns the next state for a rating 1=Again 2=Hard 3=Good 4=Easy
  function fcSchedule(st, r, now = Date.now()) {
    const n = Object.assign({ ease: FC.START_EASE, ivl: 0, reps: 0, lapses: 0, step: 0 }, st);
    n.reps++;
    const toReview = ivl => { n.q = 'review'; n.ivl = ivl; n.step = 0; n.due = startOfDay(now) + Math.round(ivl) * FC.DAY + 4 * 36e5; };
    if (n.q === 'new' || n.q === 'learn') {
      n.q = 'learn';
      if (r === 1) { n.step = 0; n.due = now + FC.LEARN_STEPS[0] * FC.MIN; }
      else if (r === 2) { n.due = now + (n.step === 0 ? (FC.LEARN_STEPS[0] + FC.LEARN_STEPS[1]) / 2 : FC.LEARN_STEPS[n.step]) * FC.MIN; }
      else if (r === 3) { n.step++; if (n.step >= FC.LEARN_STEPS.length) toReview(FC.GRAD_IVL); else n.due = now + FC.LEARN_STEPS[n.step] * FC.MIN; }
      else toReview(FC.EASY_IVL);
    } else if (n.q === 'relearn') {
      if (r <= 2) n.due = now + FC.RELEARN_STEPS[0] * FC.MIN;
      else toReview(Math.max(1, n.ivl) * (r === 4 ? 1.5 : 1));
    } else {
      if (r === 1) { n.lapses++; n.ease = Math.max(FC.MIN_EASE, n.ease - 0.2); n.q = 'relearn'; n.ivl = Math.max(1, Math.round(n.ivl * 0.2)); n.due = now + FC.RELEARN_STEPS[0] * FC.MIN; }
      else if (r === 2) { n.ease = Math.max(FC.MIN_EASE, n.ease - 0.15); toReview(Math.max(n.ivl + 1, n.ivl * 1.2)); }
      else if (r === 3) toReview(Math.max(n.ivl + 1, n.ivl * n.ease));
      else { n.ease += 0.15; toReview(Math.max(n.ivl + 1, n.ivl * n.ease * 1.3)); }
    }
    return n;
  }
  const fcIvlLabel = (st, now = Date.now()) => {
    const ms = st.due - now;
    if (ms < 3600e3) return Math.max(1, Math.round(ms / FC.MIN)) + 'm';
    if (ms < FC.DAY) return Math.round(ms / 3600e3) + 'h';
    const d = Math.round(st.ivl);
    return d < 30 ? d + 'd' : d < 365 ? (d / 30).toFixed(1).replace(/\.0$/, '') + 'mo' : (d / 365).toFixed(1).replace(/\.0$/, '') + 'y';
  };
  function fcDeckCards(F, deck) { return deck === 'all' ? F.cards : F.cards.filter(c => c.d.includes(deck)); }
  function fcCounts(F, s, deck, now = Date.now()) {
    const endToday = startOfDay(now) + FC.DAY + 4 * 36e5;
    let nw = 0, learn = 0, due = 0;
    for (const c of fcDeckCards(F, deck)) {
      const st = s.cards[c.id];
      if (!st || st.q === 'new') nw++;
      else if (st.q === 'learn' || st.q === 'relearn') { if (st.due <= now + 20 * FC.MIN) learn++; }
      else if (st.due <= endToday) due++;
    }
    return { nw: Math.min(nw, Math.max(0, s.settings.newPerDay - s.day.newDone)), nwTotal: nw, learn, due: Math.min(due, Math.max(0, s.settings.reviewsPerDay - s.day.revDone)) };
  }
  function fcNext(F, s, deck, now = Date.now()) {
    const cards = fcDeckCards(F, deck);
    const endToday = startOfDay(now) + FC.DAY + 4 * 36e5;
    let learn = null, rev = null, nw = null, nwSibling = null;
    const introduced = new Set(s.day.cases || []);   // cases that already had a new card today ("bury siblings")
    for (const c of cards) {
      const st = s.cards[c.id];
      if (!st || st.q === 'new') { if (!introduced.has(c.c)) { if (!nw) nw = c; } else if (!nwSibling) nwSibling = c; continue; }
      if ((st.q === 'learn' || st.q === 'relearn') && st.due <= now && (!learn || st.due < s.cards[learn.id].due)) learn = c;
      else if (st.q === 'review' && st.due <= endToday && (!rev || st.due < s.cards[rev.id].due)) rev = c;
    }
    if (learn) return learn;
    if (!nw && nwSibling && !cards.some(c => !s.cards[c.id] && !introduced.has(c.c))) nw = nwSibling;   // only siblings left in this deck
    const canRev = s.day.revDone < s.settings.reviewsPerDay, canNew = s.day.newDone < s.settings.newPerDay;
    // interleave: one new card after every few reviews
    if (rev && canRev && (!nw || !canNew || s.day.revDone % 4 !== 3)) return rev;
    if (nw && canNew) return nw;
    if (rev && canRev) return rev;
    // learn ahead: a learning card due within 20 minutes
    let soon = null;
    for (const c of cards) { const st = s.cards[c.id]; if (st && (st.q === 'learn' || st.q === 'relearn') && st.due <= now + 20 * FC.MIN && (!soon || st.due < s.cards[soon.id].due)) soon = c; }
    return soon;
  }
  const deckTitle = (F, id) => id === 'all' ? 'All decks' : (F.decks.find(d => d.id === id) || {}).title || id;
  const deckIconHtml = id => id === 'all' ? `<span class="guide-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="4" y="6" width="13" height="15" rx="2"/><path d="M7 3h13v15"/></svg></span>`
    : id === 'basics' ? `<span class="guide-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg></span>`
    : /^ot-/.test(id) ? `<span class="guide-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg></span>` : guideIcon(id);
  function quizTabs(active) {
    return `<div class="subtabs"><a href="#/quiz" class="${active === 'study' ? 'on' : ''}">Flashcards</a><a href="#/quiz/games" class="${active === 'games' ? 'on' : ''}">Games</a><a href="#/quiz/decks" class="${active === 'decks' ? 'on' : ''}">Decks &amp; settings</a><a href="#/quiz/stats" class="${active === 'stats' ? 'on' : ''}">Stats</a></div>`;
  }
  function quizHead(active, sub) {
    const p = fcProfiles();
    return `<div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><span>Learning Center</span></div>
      <div class="qm-head"><h1>Learning Center</h1><a class="qm-profile" href="#/quiz/decks" title="Switch profile"><span>Studying as</span><b>${esc(p.current)}</b></a></div>
      <p>${sub}</p>${quizTabs(active)}</div>`;
  }
  function viewQuiz(seg) {
    if (seg[1] === 'games') return viewGames(seg[2] || '');
    if (seg[1] === 'study' && /^ot-/.test(seg[2] || '')) return studyTermDeck(seg[2]);
    withData([['flashcards', 'FLASHCARDS'], ['fc-terms', 'FC_TERMS']], (F, T) => {
      const sub = seg[1] || '';
      if (sub === 'study') return renderStudy(F, seg[2] || 'all');
      if (sub === 'decks') return renderQuizDecks(F);
      if (sub === 'stats') return renderQuizStats(F);
      renderQuizHome(F, T);
    });
  }
  function renderQuizHome(F, T) {
    const s = fcLoad();
    const total = fcCounts(F, s, 'all');
    const tile = id => { const c = fcCounts(F, s, id); const d = F.decks.find(x => x.id === id); return `<a class="qm-deck" href="#/quiz/study/${id}">
      ${deckIconHtml(id)}
      <span class="qm-deck-body"><b>${esc(deckTitle(F, id))}</b><span>${id === 'all' ? `${fmt(F.cards.length)} cards from ${fmt(Object.keys(F.cases).length)} cases` : `${d.cards} cards · ${d.cases} cases`}</span></span>
      <span class="qm-counts"><i class="c-new" title="New">${c.nw}</i><i class="c-learn" title="Learning">${c.learn}</i><i class="c-due" title="Due">${c.due}</i></span>
    </a>`; };
    const groups = [...new Set(F.decks.map(d => d.group))];
    app.innerHTML = `<div class="fade-in">${quizHead('study', `Flashcards for ${fmt(Object.keys(F.cases).length)} essential Supreme Court cases, scheduled with spaced repetition: rate each card Again, Hard, Good or Easy, and the cards you find hard come back sooner.`)}
      <section class="section" style="padding-top:24px">
        <div class="qm-today"><div><b>${total.nw + total.learn + total.due}</b><span>cards to study today</span></div><div><b>${s.day.revDone + s.day.newDone}</b><span>studied today</span></div><div class="qm-legend"><i class="c-new"></i>New <i class="c-learn"></i>Learning <i class="c-due"></i>Due</div></div>
        <div class="qm-decks">${tile('all')}</div>
        ${groups.map(g => `<div class="qm-group"><h3>${g === 'The Basics' ? 'Start here: the basics' : esc(g)}</h3><div class="qm-decks">${F.decks.filter(d => d.group === g).map(d => tile(d.id)).join('')}</div></div>`).join('')}
        ${T ? termDeckHtml(T, s) : ''}
      </section></div>`;
  }
  function renderStudy(F, deck) {
    const s = fcLoad();
    const cardById = new Map(F.cards.map(c => [c.id, c]));
    let card = null, shown = false, startedAt = 0;
    const counts = () => fcCounts(F, s, deck);
    const KIND = { held: 'Holding', which: 'Identify the case', qp: 'Question presented', rule0: 'Rule or principle' };
    const draw = () => {
      card = fcNext(F, s, deck);
      const c = counts();
      if (!card) {
        app.innerHTML = `<div class="fade-in">${quizHead('study', 'Study session')}<div class="qm-study"><div class="qm-done">
          ${deckIconHtml(deck)}<h2>All done for now</h2><p>You've finished today's cards in <b>${esc(deckTitle(F, deck))}</b>${s.day.newDone + s.day.revDone ? ` (${s.day.newDone + s.day.revDone} studied today)` : ''}. Come back tomorrow, raise your daily limits, or study another deck.</p>
          <div class="actions" style="justify-content:center"><a class="btn btn-primary" href="#/quiz">Choose another deck</a><a class="btn btn-ghost" href="#/quiz/stats">See your stats</a><a class="btn btn-ghost" href="#/quiz/decks">Daily limits</a></div></div></div></div>`;
        return;
      }
      shown = false; startedAt = Date.now();
      const st = fcState(s, card.id);
      const info = F.cases[card.c] || {};
      const deckOfCard = deck === 'all' ? card.d[0] : deck;
      app.innerHTML = `<div class="fade-in">${quizHead('study', `Studying <b>${esc(deckTitle(F, deck))}</b>. Press <kbd>Space</kbd> to reveal the answer and <kbd>1</kbd>–<kbd>4</kbd> to grade.`)}
        <div class="qm-study">
          <div class="qm-bar"><a href="#/quiz" class="link-arrow">← Decks</a><span class="qm-counts big"><i class="c-new" title="New">${c.nw}</i><i class="c-learn" title="Learning">${c.learn}</i><i class="c-due" title="Due">${c.due}</i></span></div>
          <div class="qm-card ${st.q === 'new' ? 'is-new' : ''}">
            <div class="qm-card-top">${deckIconHtml(deckOfCard)}<span>${esc(deckTitle(F, deckOfCard))} · ${esc(KIND[card.k] || 'Card')}</span>${st.q === 'new' ? '<em>New</em>' : ''}</div>
            <div class="qm-front">${card.f}</div>
            <div class="qm-back" hidden>
              <div class="qm-answer">${card.b}</div>
              <a class="qm-case" href="#/case/${esc(card.c)}"><b>${esc(info.n || '')}</b><span>${esc(info.cit || '')}${info.y ? ' · ' + info.y : ''} · Open the case page →</span></a>
            </div>
          </div>
          <div class="qm-actions">
            <button class="btn btn-primary qm-show">Show answer <kbd>Space</kbd></button>
            <div class="qm-grades" hidden>${[1, 2, 3, 4].map(r => { const nx = fcSchedule(st, r); return `<button class="qm-grade g${r}" data-r="${r}"><b>${['Again', 'Hard', 'Good', 'Easy'][r - 1]}</b><span>${fcIvlLabel(nx)}</span><kbd>${r}</kbd></button>`; }).join('')}</div>
          </div>
          <p class="attrib" style="text-align:center">Card text is adapted from Oyez (oyez.org, <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener">CC BY-NC 4.0</a>), the Court’s official holdings, the <i>Constitution Annotated</i> (public domain), and this site’s doctrine notes.</p>
        </div></div>`;
      app.querySelector('.qm-show').addEventListener('click', reveal);
      app.querySelectorAll('.qm-grade').forEach(b => b.addEventListener('click', () => grade(+b.dataset.r)));
    };
    const reveal = () => {
      if (shown || !card) return; shown = true;
      app.querySelector('.qm-back').hidden = false;
      app.querySelector('.qm-show').hidden = true;
      app.querySelector('.qm-grades').hidden = false;
    };
    const grade = r => {
      if (!shown || !card) return;
      const before = fcState(s, card.id);
      const after = fcSchedule(before, r);
      s.cards[card.id] = after;
      if (before.q === 'new') { s.day.newDone++; (s.day.cases = s.day.cases || []).push(card.c); } else if (before.q === 'review') s.day.revDone++;
      s.log.push([Date.now(), card.id, r, before.q === 'new' ? 0 : before.q === 'review' ? 2 : 1, Math.round((Date.now() - startedAt) / 1000)]);
      if (s.log.length > 50000) s.log = s.log.slice(-50000);
      fcSave(s);
      draw();
    };
    const onKey = e => {
      if (!document.querySelector('.qm-study') || /input|textarea|select/i.test(document.activeElement.tagName)) return;
      if (e.code === 'Space' || e.key === 'Enter') { e.preventDefault(); if (!shown) reveal(); else grade(3); }
      else if (shown && /^[1-4]$/.test(e.key)) grade(+e.key);
    };
    document.addEventListener('keydown', onKey);
    const stop = () => { document.removeEventListener('keydown', onKey); window.removeEventListener('hashchange', stop); };
    window.addEventListener('hashchange', stop);
    draw();
  }
  /* ------------------------------------------------------------ Learning Center: term-by-term decks */
  function termDeckHtml(T, s) {
    return `<section class="qm-group qm-terms"><h3>Every case, term by term</h3>
      <p class="muted-line" style="margin:-4px 0 12px">Flashcards for ${fmt(T.courts.reduce((n, c) => n + c.cases, 0))} more decided cases with a summary, one deck per Term, grouped by Chief Justice. These are kept out of the topic decks and the games.</p>
      ${T.courts.map(c => `<details class="qm-court"><summary><b>${esc(c.name)}</b><span>${esc(c.years)} · ${fmt(c.cases)} cases · ${c.decks.length} term${c.decks.length === 1 ? '' : 's'}</span></summary>
        <div class="qm-term-list">${c.decks.map(d => `<a href="#/quiz/study/${esc(d.id)}"><b>${esc(d.title)}</b><span>${d.cases} case${d.cases === 1 ? '' : 's'} · ${d.cards} cards</span></a>`).join('')}</div></details>`).join('')}
    </section>`;
  }
  function studyTermDeck(deck) {
    withData([['fc-terms', 'FC_TERMS']], T => {
      const court = T.courts.find(c => c.decks.some(d => d.id === deck));
      if (!court) return viewNotFound();
      withData([['fc-court-' + court.id, 'FC_COURT_' + court.id.toUpperCase()]], C => {
        renderStudy({ decks: court.decks.map(d => ({ id: d.id, title: `${d.title} (${court.name})`, group: court.name })), cases: C.cases, cards: C.cards }, deck);
      });
    });
  }

  /* ------------------------------------------------------------ Learning Center: games (essential cases only) */
  const GAME_LIST = [
    ['match', 'Match-up', 'Pair five cases with what they decided. Clear the board in as few misses as you can.'],
    ['ruling', 'Choose the Ruling', 'Read the question the Court faced and pick its actual ruling from four convincing options.'],
    ['overruled', 'Overruled', 'See a precedent and its holding, then name the case that later overruled it.'],
    ['docket', 'Current Events', 'Identify a case on the Court’s current docket from clues revealed one at a time. Fewer clues, more points.'],
    ['author', 'Who Wrote It?', 'Name the justice who wrote the opinion of the Court in a landmark case.'],
    ['timeline', 'Timeline', 'Put four landmark cases in the order they were decided.'],
  ];
  const shuffle = a => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const gameBest = (g, v) => { let b = {}; try { b = JSON.parse(localStorage.getItem('cl-games') || '{}'); } catch (e) {} if (v != null && v > (b[g] || 0)) { b[g] = v; localStorage.setItem('cl-games', JSON.stringify(b)); } return b[g] || 0; };
  const plainText = h => { const d = document.createElement('div'); d.innerHTML = h || ''; return d.textContent.replace(/\s+/g, ' ').trim(); };
  const caseHolding = c => (c && c.ds || '').replace(/^A case in which the Court (held|decided|ruled|found|concluded|considered|addressed|examined|determined|established)/i, 'The Court $1').replace(/^A case (?:that|in which) the Court (?:that\s+)?(?=(?:the|a|an|he|she|both|[A-Z])\b)/, 'The Court held that ').replace(/^A case (?:that|in which) the Court that\s+/i, 'The Court held that ').replace(/^A case (?:that|in which) (?:the Court )?/i, 'The Court ');
  function viewGames(game) {
    withData([['flashcards', 'FLASHCARDS'], ['scotus', 'SCOTUS'], ['games', 'GAMES'], ['votes', 'VOTES'], ['docket', 'DOCKET']], (F, S, GM, V, K) => {
      if (!caseById) caseById = new Map(S.cases.map(c => [c.id, c]));
      if (!game) return renderGameHub();
      const fn = { match: gameMatch, ruling: gameRuling, overruled: gameOverruled, docket: gameDocket, author: gameAuthor, timeline: gameTimeline }[game];
      if (!fn) return viewNotFound();
      fn(F, GM, V, K);
    });
  }
  function renderGameHub() {
    app.innerHTML = `<div class="fade-in">${quizHead('games', 'Games for learning the essential cases. Each draws only on the essential-case decks, not the term-by-term decks.')}
      <section class="section" style="padding-top:24px"><div class="game-grid">${GAME_LIST.map(([id, name, desc]) => `<a class="game-card" href="#/quiz/games/${id}"><b>${esc(name)}</b><span>${esc(desc)}</span><em>${gameBest(id) ? `Best: ${gameBest(id)}` : 'Play →'}</em></a>`).join('')}</div></section></div>`;
  }
  // a game of N multiple-choice rounds: round(i) returns {prompt html, options [{html, ok}], after html}
  function mcGame(id, title, rounds, intro) {
    let i = 0, score = 0, streak = 0;
    const draw = () => {
      if (i >= rounds.length) {
        const best = gameBest(id, score);
        app.innerHTML = `<div class="fade-in">${quizHead('games', title)}<div class="qm-study"><div class="qm-done"><h2>${score} / ${rounds.length}</h2><p>${score === best ? 'A new best score.' : `Your best is ${best}.`}</p>
          <div class="actions" style="justify-content:center"><a class="btn btn-primary" href="#/quiz/games/${id}" data-replay>Play again</a><a class="btn btn-ghost" href="#/quiz/games">All games</a></div></div></div></div>`;
        app.querySelector('[data-replay]').addEventListener('click', e => { e.preventDefault(); route(); });
        return;
      }
      const r = rounds[i];
      const opts = shuffle(r.options);
      app.innerHTML = `<div class="fade-in">${quizHead('games', intro)}<div class="qm-study">
        <div class="qm-bar"><a href="#/quiz/games" class="link-arrow">← Games</a><span class="game-score">Round ${i + 1} of ${rounds.length} · Score ${score}${streak > 1 ? ` · Streak ${streak}` : ''}</span></div>
        <div class="qm-card"><div class="qm-card-top"><span>${esc(title)}</span></div><div class="game-prompt">${r.prompt}</div>
          <div class="game-opts">${opts.map((o, k) => `<button class="game-opt" data-k="${k}">${o.html}</button>`).join('')}</div>
          <div class="game-after" hidden>${r.after || ''}<button class="btn btn-primary game-next">${i + 1 < rounds.length ? 'Next' : 'See score'}</button></div></div></div></div>`;
      app.querySelectorAll('.game-opt').forEach(b => b.addEventListener('click', () => {
        if (app.querySelector('.game-opt.done')) return;
        const o = opts[+b.dataset.k];
        app.querySelectorAll('.game-opt').forEach((x, k) => { x.classList.add('done'); if (opts[k].ok) x.classList.add('right'); });
        if (o.ok) { score++; streak++; } else { b.classList.add('wrong'); streak = 0; }
        app.querySelector('.game-after').hidden = false;
      }));
      app.querySelector('.game-next').addEventListener('click', () => { i++; draw(); window.scrollTo(0, 0); });
    };
    draw();
  }
  const caseLabel = id => { const c = caseById.get(id); return c ? `<i>${esc(c.n.replace(/\s*\(\d\)$/, ''))}</i> (${c.y})` : ''; };
  const caseLink = id => `<a class="link-arrow" href="#/case/${esc(id)}" target="_blank">Read about ${caseLabel(id)} →</a>`;
  function gameRuling(F, GM) {
    const rounds = shuffle(GM.ruling).slice(0, 10).map(r => ({
      prompt: `<p class="game-case">${caseLabel(r.c)}</p><p class="game-q"><b>The question:</b> ${esc(r.q)}</p><p class="muted-line">What did the Court decide?</p>`,
      options: [{ html: esc(r.a), ok: true }, ...r.d.map(d => ({ html: esc(d), ok: false }))],
      after: caseLink(r.c),
    }));
    mcGame('ruling', 'Choose the Ruling', rounds, 'Read the question the Court faced and choose its actual ruling.');
  }
  function gameOverruled(F, GM) {
    const newer = [...new Set(GM.overruled.map(o => o.new))];
    const rounds = shuffle(GM.overruled).slice(0, 10).map(o => {
      const old = caseById.get(o.old), nw = caseById.get(o.new);
      const decoys = shuffle(newer.filter(x => x !== o.new && (caseById.get(x).y || 0) > (old.y || 0))).slice(0, 3);
      while (decoys.length < 3) { const x = shuffle(Object.keys(F.cases)).find(id => id !== o.new && !decoys.includes(id) && (caseById.get(id) || {}).y > old.y); if (!x) break; decoys.push(x); }
      return {
        prompt: `<p class="game-case">${caseLabel(o.old)}</p><p class="game-q">${(h => /^The Court\b/.test(h) ? esc(h) : `<b>Held:</b> ${esc(h)}`)(o.h || caseHolding(old))}</p><p class="muted-line">Which later case overruled it?</p>`,
        options: [{ html: caseLabel(o.new), ok: true }, ...decoys.map(d => ({ html: caseLabel(d), ok: false }))],
        after: `<p>${caseLabel(o.new)} overruled ${caseLabel(o.old)}.</p>${caseLink(o.new)}${o.src ? `<p class="attrib">Holding of ${caseLabel(o.old)} from <a href="${esc(o.src)}" target="_blank" rel="noopener">Wikipedia</a> (CC BY-SA 4.0).</p>` : ''}`,
      };
    });
    mcGame('overruled', 'Overruled', rounds, 'Name the case that overruled the precedent.');
  }
  function gameAuthor(F, GM, V) {
    const pool = Object.keys(F.cases).filter(id => V.c[id] && V.c[id][2].some(([, f]) => f === 1));
    const rounds = shuffle(pool).slice(0, 10).map(id => {
      const r = V.c[id];
      const author = r[2].find(([, f]) => f === 1)[0];
      const others = shuffle([...r[2], ...r[3]].map(([j]) => j).filter(j => j !== author)).slice(0, 3);
      return {
        prompt: `<p class="game-case">${caseLabel(id)}</p><p class="game-q">${esc(caseHolding(caseById.get(id)))}</p><p class="muted-line">Who wrote the opinion of the Court?</p>`,
        options: [{ html: esc(V.j[author][0]), ok: true }, ...others.map(j => ({ html: esc(V.j[j][0]), ok: false }))],
        after: `<p>${esc(V.j[author][0])} wrote for the Court, ${r[0]}–${r[1]}.</p>${caseLink(id)}`,
      };
    });
    mcGame('author', 'Who Wrote It?', rounds, 'Choose the justice who wrote the opinion of the Court.');
  }
  function gameMatch(F) {
    const which = F.cards.filter(c => c.k === 'which');
    let board = 0, misses = 0, total = 0;
    const draw = () => {
      if (board >= 3) {
        const score = Math.max(0, 15 - misses), best = gameBest('match', score);
        app.innerHTML = `<div class="fade-in">${quizHead('games', 'Match-up')}<div class="qm-study"><div class="qm-done"><h2>${total} matched, ${misses} miss${misses === 1 ? '' : 'es'}</h2><p>Score ${score} of 15. ${score === best ? 'A new best.' : `Your best is ${best}.`}</p>
          <div class="actions" style="justify-content:center"><a class="btn btn-primary" href="#" data-replay>Play again</a><a class="btn btn-ghost" href="#/quiz/games">All games</a></div></div></div></div>`;
        app.querySelector('[data-replay]').addEventListener('click', e => { e.preventDefault(); route(); });
        return;
      }
      const picks = shuffle(which).filter((c, i, a) => a.findIndex(x => x.c === c.c) === i).slice(0, 5);
      const names = shuffle(picks), descs = shuffle(picks);
      app.innerHTML = `<div class="fade-in">${quizHead('games', 'Pair each case with what it decided.')}<div class="qm-study wide">
        <div class="qm-bar"><a href="#/quiz/games" class="link-arrow">← Games</a><span class="game-score">Board ${board + 1} of 3 · Misses ${misses}</span></div>
        <div class="match-board"><div class="match-col">${names.map(c => `<button class="match-item" data-c="${esc(c.c)}">${caseLabel(c.c)}</button>`).join('')}</div>
        <div class="match-col">${descs.map(c => `<button class="match-item desc" data-c="${esc(c.c)}">${esc(plainText(c.f).replace(/^Which case\?\s*/, ''))}</button>`).join('')}</div></div></div></div>`;
      let sel = null, left = 5;
      app.querySelectorAll('.match-item').forEach(b => b.addEventListener('click', () => {
        if (b.classList.contains('matched')) return;
        if (!sel || sel.classList.contains('desc') === b.classList.contains('desc')) { app.querySelectorAll('.match-item.sel').forEach(x => x.classList.remove('sel')); sel = b; b.classList.add('sel'); return; }
        if (sel.dataset.c === b.dataset.c) { sel.classList.add('matched'); b.classList.add('matched'); sel.classList.remove('sel'); total++; left--; if (!left) setTimeout(() => { board++; draw(); }, 600); }
        else { misses++; b.classList.add('wrong'); sel.classList.add('wrong'); const a = sel; setTimeout(() => { a.classList.remove('wrong', 'sel'); b.classList.remove('wrong'); }, 500); app.querySelector('.game-score').textContent = `Board ${board + 1} of 3 · Misses ${misses}`; }
        sel = null;
      }));
    };
    draw();
  }
  function gameTimeline(F) {
    const ids = Object.keys(F.cases).filter(id => caseById.get(id) && caseById.get(id).y);
    let round = 0, score = 0;
    const draw = () => {
      if (round >= 5) {
        const best = gameBest('timeline', score);
        app.innerHTML = `<div class="fade-in">${quizHead('games', 'Timeline')}<div class="qm-study"><div class="qm-done"><h2>${score} / 5</h2><p>${score === best ? 'A new best.' : `Your best is ${best}.`}</p><div class="actions" style="justify-content:center"><a class="btn btn-primary" href="#" data-replay>Play again</a><a class="btn btn-ghost" href="#/quiz/games">All games</a></div></div></div></div>`;
        app.querySelector('[data-replay]').addEventListener('click', e => { e.preventDefault(); route(); });
        return;
      }
      let four;
      do { four = shuffle(ids).slice(0, 4); } while (new Set(four.map(id => caseById.get(id).y)).size < 4);
      const order = four.slice().sort((a, b) => caseById.get(a).y - caseById.get(b).y);
      const picked = [];
      app.innerHTML = `<div class="fade-in">${quizHead('games', 'Select the cases from earliest to latest.')}<div class="qm-study">
        <div class="qm-bar"><a href="#/quiz/games" class="link-arrow">← Games</a><span class="game-score">Round ${round + 1} of 5 · Score ${score}</span></div>
        <div class="qm-card"><div class="game-opts">${four.map(id => `<button class="game-opt" data-c="${esc(id)}"><span class="tl-n"></span>${esc(caseById.get(id).n.replace(/\s*\(\d\)$/, ''))}</button>`).join('')}</div>
        <div class="game-after" hidden><p class="tl-answer"></p><button class="btn btn-primary game-next">Next</button></div></div></div></div>`;
      app.querySelectorAll('.game-opt').forEach(b => b.addEventListener('click', () => {
        if (picked.includes(b.dataset.c) || picked.length === 4) return;
        picked.push(b.dataset.c); b.querySelector('.tl-n').textContent = picked.length; b.classList.add('sel');
        if (picked.length === 4) {
          const ok = picked.every((id, k) => id === order[k]);
          if (ok) score++;
          app.querySelectorAll('.game-opt').forEach(x => { x.classList.add('done'); x.classList.add(order.indexOf(x.dataset.c) === picked.indexOf(x.dataset.c) ? 'right' : 'wrong'); });
          app.querySelector('.tl-answer').innerHTML = (ok ? 'Correct. ' : 'The order: ') + order.map(id => `${esc(caseById.get(id).n.replace(/\s*\(\d\)$/, ''))} (${caseById.get(id).y})`).join(' → ');
          app.querySelector('.game-after').hidden = false;
        }
      }));
      app.querySelector('.game-next').addEventListener('click', () => { round++; draw(); });
    };
    draw();
  }
  function gameDocket(F, GM, V, K) {
    const pool = K.cases.filter(e => e.q && e.n);
    if (pool.length < 4) { app.innerHTML = `<div class="fade-in">${quizHead('games', 'Current Events')}<div class="qm-study"><p>Not enough cases on the current docket yet.</p></div></div>`; return; }
    let round = 0, score = 0;
    const N = Math.min(8, pool.length);
    const order = shuffle(pool).slice(0, N);
    const maskName = (txt, n) => n.split(/\s+v\.\s+/).flatMap(p => p.match(/[A-Z][a-z][\w'-]{3,}/g) || []).filter(w => !/^(United|States|County|Department|Commission|Board|Corporation|Company)$/.test(w)).reduce((t, w) => t.replace(new RegExp('\\b' + w + '\\b', 'g'), '———'), txt);
    const draw = () => {
      if (round >= N) {
        const best = gameBest('docket', score);
        app.innerHTML = `<div class="fade-in">${quizHead('games', 'Current Events')}<div class="qm-study"><div class="qm-done"><h2>${score} points</h2><p>out of ${N * 3} possible. ${score === best ? 'A new best.' : `Your best is ${best}.`}</p><div class="actions" style="justify-content:center"><a class="btn btn-primary" href="#" data-replay>Play again</a><a class="btn btn-ghost" href="#/docket">See the docket</a></div></div></div></div>`;
        app.querySelector('[data-replay]').addEventListener('click', e => { e.preventDefault(); route(); });
        return;
      }
      const e = order[round];
      const opts = shuffle([e, ...shuffle(pool.filter(x => x !== e)).slice(0, 3)]);
      const initials = e.n.split(/\s+v\.\s+/).map(p => p.replace(/^(The|In re)\s+/, '').split(/\s+/)[0]).map(w => w[0] + '_'.repeat(Math.max(2, Math.min(8, w.length - 1)))).join(' v. ');
      const amici = (e.amici || []).length;
      const clues = [
        `The question: ${esc(maskName(e.q, e.n))}`,
        `Cert granted ${e.granted ? fmtDate(e.granted) : 'this Term'}${e.argued ? `; argued ${fmtDate(e.argued)}` : e.sched ? `; argument set for ${fmtDate(e.sched)}` : '; not yet argued'}. ${amici ? `${amici} amicus brief${amici === 1 ? '' : 's'} filed so far.` : 'No amicus briefs filed yet.'}`,
        `The parties: ${esc(initials)}`,
      ];
      let shown = 1, done = false;
      const paint = () => {
        app.innerHTML = `<div class="fade-in">${quizHead('games', 'Identify the pending case from the clues. A correct guess after one clue earns 3 points, after two 2, after three 1.')}<div class="qm-study">
          <div class="qm-bar"><a href="#/quiz/games" class="link-arrow">← Games</a><span class="game-score">Case ${round + 1} of ${N} · ${score} points</span></div>
          <div class="qm-card"><div class="qm-card-top"><span>Current Events · this Term’s docket</span></div>
            <ol class="dd-clues">${clues.slice(0, shown).map(c => `<li>${c}</li>`).join('')}</ol>
            ${!done && shown < 3 ? '<button class="btn btn-ghost btn-sm dd-more">Reveal another clue</button>' : ''}
            <div class="game-opts">${opts.map((o, k) => `<button class="game-opt ${done ? 'done' : ''} ${done && o === e ? 'right' : ''}" data-k="${k}">${esc(o.n)}</button>`).join('')}</div>
            <div class="game-after" ${done ? '' : 'hidden'}><a class="link-arrow" href="#/case/${esc(e.id)}" target="_blank">Open the case page →</a><button class="btn btn-primary game-next">Next</button></div></div></div></div>`;
        const more = app.querySelector('.dd-more'); if (more) more.addEventListener('click', () => { shown++; paint(); });
        app.querySelectorAll('.game-opt').forEach(b => b.addEventListener('click', () => {
          if (done) return; done = true;
          if (opts[+b.dataset.k] === e) score += 4 - shown; else b.classList.add('wrong');
          const wrong = b.classList.contains('wrong'); paint(); if (wrong) app.querySelectorAll('.game-opt')[+b.dataset.k].classList.add('wrong');
        }));
        const nx = app.querySelector('.game-next'); if (nx) nx.addEventListener('click', () => { round++; draw(); });
      };
      paint();
    };
    draw();
  }

  function renderQuizDecks(F) {
    const s = fcLoad(), p = fcProfiles();
    const now = Date.now();
    const rows = ['all', ...F.decks.map(d => d.id)].map(id => {
      let nw = 0, learn = 0, young = 0, mature = 0;
      for (const c of fcDeckCards(F, id)) { const st = s.cards[c.id]; if (!st || st.q === 'new') nw++; else if (st.q !== 'review') learn++; else if (st.ivl >= 21) mature++; else young++; }
      const c = fcCounts(F, s, id, now);
      return `<tr><td><a class="qm-row-deck" href="#/quiz/study/${id}">${deckIconHtml(id)}<span>${esc(deckTitle(F, id))}</span></a></td><td>${fmt(nw)}</td><td>${fmt(learn)}</td><td>${fmt(young)}</td><td>${fmt(mature)}</td><td><b>${c.nw + c.learn + c.due}</b></td><td><a class="btn btn-ghost btn-sm" href="#/quiz/study/${id}">Study</a></td></tr>`;
    }).join('');
    app.innerHTML = `<div class="fade-in">${quizHead('decks', 'Choose a deck, set your daily limits, and manage study profiles.')}
      <section class="section" style="padding-top:24px">
        <div class="qm-settings">
          <div class="panel"><h4>Daily limits (${esc(p.current)})</h4>
            <label class="qm-field"><span>New cards per day</span><input class="input" type="number" min="0" max="500" id="fc-new" value="${s.settings.newPerDay}"></label>
            <label class="qm-field"><span>Maximum reviews per day</span><input class="input" type="number" min="0" max="5000" id="fc-rev" value="${s.settings.reviewsPerDay}"></label>
            <p class="muted-line" style="font-size:13px">Today: ${s.day.newDone} new and ${s.day.revDone} reviews done. Again repeats a card in about 1 minute, and Good on a new card twice graduates it to a 1-day interval. Each correct review then multiplies the interval by the card's ease (about 2.5×).</p>
          </div>
          <div class="panel"><h4>Profiles</h4>
            <p class="muted-line" style="font-size:13px;margin-top:-4px">Progress is stored in this browser. Each person can keep a separate profile, and export moves progress to another device.</p>
            <div class="qm-profiles">${p.list.map(n => `<button class="chip ${n === p.current ? 'on' : ''}" data-profile="${esc(n)}">${esc(n)}</button>`).join('')}</div>
            <div class="qm-profile-actions">
              <button class="btn btn-ghost btn-sm" id="fc-add">New profile</button>
              <button class="btn btn-ghost btn-sm" id="fc-export">Export progress</button>
              <label class="btn btn-ghost btn-sm" style="cursor:pointer">Import progress<input type="file" id="fc-import" accept="application/json" hidden></label>
              <button class="btn btn-ghost btn-sm" id="fc-reset">Reset this profile</button>
              ${p.list.length > 1 ? '<button class="btn btn-ghost btn-sm" id="fc-del">Delete this profile</button>' : ''}
            </div>
          </div>
        </div>
        <div class="section-head" style="margin-top:30px"><div><h2 style="font-size:26px">Decks</h2><p>Card counts by stage: new (never seen), learning (in short steps), young (interval under 21 days) and mature (21 days or more).</p></div></div>
        <div class="qm-table-wrap"><table class="qm-table"><thead><tr><th>Deck</th><th>New</th><th>Learning</th><th>Young</th><th>Mature</th><th>Today</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      </section></div>`;
    const saveLimits = () => { const s2 = fcLoad(); s2.settings.newPerDay = Math.max(0, +document.getElementById('fc-new').value || 0); s2.settings.reviewsPerDay = Math.max(0, +document.getElementById('fc-rev').value || 0); fcSave(s2); toast('Daily limits saved'); };
    document.getElementById('fc-new').addEventListener('change', saveLimits);
    document.getElementById('fc-rev').addEventListener('change', saveLimits);
    app.querySelectorAll('[data-profile]').forEach(b => b.addEventListener('click', () => { const pp = fcProfiles(); pp.current = b.dataset.profile; fcSaveProfiles(pp); renderQuizDecks(F); toast('Switched to ' + pp.current); }));
    document.getElementById('fc-add').addEventListener('click', () => {
      const name = (prompt('Name for the new profile:') || '').trim().slice(0, 40);
      if (!name) return; const pp = fcProfiles();
      if (!pp.list.includes(name)) pp.list.push(name);
      pp.current = name; fcSaveProfiles(pp); renderQuizDecks(F); toast('Created profile ' + name);
    });
    document.getElementById('fc-export').addEventListener('click', () => {
      const raw = localStorage.getItem('cl-fc:' + fcProfiles().current) || '{}';
      const blob = new Blob([JSON.stringify({ app: 'lex-constitutio-flashcards', profile: fcProfiles().current, exported: new Date().toISOString(), data: JSON.parse(raw) })], { type: 'application/json' });
      const u = URL.createObjectURL(blob); const l = document.createElement('a'); l.href = u; l.download = `flashcards-${fcProfiles().current.replace(/\W+/g, '-')}.json`; l.click(); URL.revokeObjectURL(u);
    });
    document.getElementById('fc-import').addEventListener('change', e => {
      const f = e.target.files[0]; if (!f) return;
      f.text().then(t => {
        const j = JSON.parse(t);
        if (j.app !== 'lex-constitutio-flashcards' || !j.data) throw new Error('not a flashcard export');
        const pp = fcProfiles(); const name = j.profile || 'Imported';
        if (!pp.list.includes(name)) pp.list.push(name);
        if (!confirm(`Import progress into profile "${name}"? Its current progress will be replaced.`)) return;
        localStorage.setItem('cl-fc:' + name, JSON.stringify(j.data)); pp.current = name; fcSaveProfiles(pp); renderQuizDecks(F); toast('Progress imported');
      }).catch(err => toast('Import failed: ' + err.message));
    });
    document.getElementById('fc-reset').addEventListener('click', () => {
      if (!confirm(`Reset all flashcard progress for "${fcProfiles().current}"? This cannot be undone.`)) return;
      localStorage.removeItem('cl-fc:' + fcProfiles().current); renderQuizDecks(F); toast('Progress reset');
    });
    document.getElementById('fc-del')?.addEventListener('click', () => {
      const pp = fcProfiles(); const name = pp.current;
      if (!confirm(`Delete the profile "${name}" and its progress?`)) return;
      localStorage.removeItem('cl-fc:' + name); pp.list = pp.list.filter(x => x !== name); pp.current = pp.list[0]; fcSaveProfiles(pp); renderQuizDecks(F);
    });
  }
  // Single-series bar chart (SVG) with a hover tooltip on every bar.
  function barChart(items, { h = 170, fmtTip, labelEvery = 1, horizontal = false, valueFmt = v => fmt(v), max } = {}) {
    if (horizontal) {
      const mx = max || Math.max(1, ...items.map(i => i.v));
      return `<div class="hbars">${items.map(i => `<div class="hbar" data-tip="${esc(fmtTip ? fmtTip(i) : i.label + ': ' + valueFmt(i.v))}">
        <span class="hbar-l">${i.icon || ''}${esc(i.label)}</span><span class="hbar-track"><i style="width:${!i.v ? 0 : Math.max(1.5, 100 * i.v / mx)}%"></i></span><span class="hbar-v">${i.v == null ? '—' : valueFmt(i.v)}</span></div>`).join('')}</div>`;
    }
    const W = 640, padL = 34, padB = 22, padT = 8, n = items.length, mx = max || Math.max(1, ...items.map(i => i.v));
    const step = (W - padL) / n, bw = Math.max(3, Math.min(22, step * 0.62));
    const nice = Math.ceil(mx / 4) * 4 || 4;
    const y = v => padT + (h - padT - padB) * (1 - v / nice);
    const grid = [0, nice / 2, nice].map(v => `<line x1="${padL}" x2="${W}" y1="${y(v)}" y2="${y(v)}" class="cg"/><text x="${padL - 6}" y="${y(v) + 4}" class="ct" text-anchor="end">${fmt(v)}</text>`).join('');
    const bars = items.map((i, k) => {
      const x = padL + k * step + (step - bw) / 2, top = y(i.v), base = y(0), hh = Math.max(0, base - top);
      const r = Math.min(4, bw / 2, hh);
      const path = hh > 0 ? `M${x},${base} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${base} Z` : '';
      return `<g class="cb" data-tip="${esc(fmtTip ? fmtTip(i) : i.label + ': ' + valueFmt(i.v))}"><rect x="${padL + k * step}" y="${padT}" width="${step}" height="${h - padT - padB}" fill="transparent"/>${path ? `<path d="${path}"/>` : ''}${k % labelEvery === 0 ? `<text x="${x + bw / 2}" y="${h - 6}" class="ct" text-anchor="middle">${esc(i.short || i.label)}</text>` : ''}</g>`;
    }).join('');
    return `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img">${grid}${bars}</svg>`;
  }
  function mountTips(root) {
    let tip = document.getElementById('chart-tip');
    if (!tip) { tip = document.createElement('div'); tip.id = 'chart-tip'; tip.className = 'chart-tip'; document.body.appendChild(tip); }
    root.querySelectorAll('[data-tip]').forEach(el => {
      el.addEventListener('mousemove', e => { tip.textContent = el.dataset.tip; tip.style.opacity = 1; tip.style.left = e.clientX + 14 + 'px'; tip.style.top = e.clientY - 10 + 'px'; el.classList.add('hover'); });
      el.addEventListener('mouseleave', () => { tip.style.opacity = 0; el.classList.remove('hover'); });
    });
  }
  function renderQuizStats(F) {
    const s = fcLoad();
    const cardById = new Map(F.cards.map(c => [c.id, c]));
    const now = Date.now(), today = dayKey();
    const byDay = {};
    for (const [t, id, r] of s.log) { const k = dayKey(t); const d = byDay[k] || (byDay[k] = { n: 0, ok: 0, secs: 0 }); d.n++; if (r > 1) d.ok++; }
    for (const e of s.log) { const d = byDay[dayKey(e[0])]; if (d) d.secs += Math.min(e[4] || 0, 120); }
    const days = []; for (let i = 29; i >= 0; i--) { const t = now - i * FC.DAY; days.push({ k: dayKey(t), d: new Date(t) }); }
    const series = days.map(({ k, d }) => ({ label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), short: String(d.getDate()), v: (byDay[k] || {}).n || 0, ok: (byDay[k] || {}).ok || 0 }));
    let streak = 0; for (let i = 0; ; i++) { const k = dayKey(now - i * FC.DAY); if (byDay[k]) streak++; else if (i === 0) continue; else break; }
    const t = byDay[today] || { n: 0, ok: 0, secs: 0 };
    const total = s.log.length, totalOk = s.log.filter(e => e[2] > 1).length;
    // retention on review cards (excludes first sightings and learning steps)
    const revLog = s.log.filter(e => e[3] === 2), revOk = revLog.filter(e => e[2] > 1).length;
    const deckStats = F.decks.map(d => {
      let n = 0, ok = 0; for (const e of s.log) { const c = cardById.get(e[1]); if (c && c.d.includes(d.id)) { n++; if (e[2] > 1) ok++; } }
      let seen = 0; for (const c of fcDeckCards(F, d.id)) if (s.cards[c.id] && s.cards[c.id].q !== 'new') seen++;
      return { id: d.id, label: d.title, icon: guideIcon(d.id), v: n ? Math.round(100 * ok / n) : null, n, seen, cards: d.cards };
    });
    const forecast = []; for (let i = 0; i < 14; i++) { const a = startOfDay(now) + i * FC.DAY, b = a + FC.DAY; const dd = new Date(a); let n = 0; for (const st of Object.values(s.cards)) if (st.q === 'review' && (i === 0 ? st.due < b : st.due >= a && st.due < b)) n++; forecast.push({ label: i === 0 ? 'Today' : dd.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }), short: i === 0 ? 'Today' : dd.toLocaleDateString('en-US', { weekday: 'narrow' }), v: n }); }
    const hardest = Object.entries(s.cards).filter(([, st]) => st.lapses).sort((a, b) => b[1].lapses - a[1].lapses || a[1].ease - b[1].ease).slice(0, 8).map(([id, st]) => ({ c: cardById.get(id), st })).filter(x => x.c);
    const ratings = [0, 0, 0, 0]; for (const e of s.log) ratings[e[2] - 1]++;
    const seenCases = new Set(Object.keys(s.cards).map(id => id.split('|')[0]));
    const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '—';
    app.innerHTML = `<div class="fade-in">${quizHead('stats', `Your progress as <b>${esc(s.profile)}</b>, kept in this browser.`)}
      <section class="section" style="padding-top:24px">
        ${!total ? `<div class="empty" style="margin-bottom:24px"><h3>No reviews yet</h3><p>Study a deck and your stats will appear here.</p><p style="margin-top:14px"><a class="btn btn-primary" href="#/quiz">Start studying</a></p></div>` : ''}
        <div class="qm-tiles">
          <div class="qm-tile"><span>Cards today</span><b>${fmt(t.n)}</b><em>${t.n ? pct(t.ok, t.n) + ' correct' : 'none yet'}</em></div>
          <div class="qm-tile"><span>Study streak</span><b>${streak}</b><em>day${streak === 1 ? '' : 's'} in a row</em></div>
          <div class="qm-tile"><span>Retention</span><b>${pct(revOk, revLog.length)}</b><em>on review cards</em></div>
          <div class="qm-tile"><span>Cases started</span><b>${fmt(seenCases.size)}</b><em>of ${fmt(Object.keys(F.cases).length)}</em></div>
          <div class="qm-tile"><span>All reviews</span><b>${fmt(total)}</b><em>${pct(totalOk, total)} correct</em></div>
        </div>
        <div class="qm-charts">
          <div class="panel qm-chart"><h4>Cards reviewed per day · last 30 days</h4>${barChart(series, { labelEvery: 5, fmtTip: i => `${i.label}: ${i.v} card${i.v === 1 ? '' : 's'}${i.v ? `, ${Math.round(100 * i.ok / i.v)}% correct` : ''}` })}</div>
          <div class="panel qm-chart"><h4>Review forecast · next 14 days</h4>${barChart(forecast, { labelEvery: 1, fmtTip: i => `${i.label}: ${i.v} review${i.v === 1 ? '' : 's'} due` })}</div>
        </div>
        <div class="qm-charts">
          <div class="panel"><h4>Accuracy by topic</h4><p class="muted-line" style="font-size:12.5px;margin:-6px 0 10px">Share of answers rated Hard, Good or Easy. Hover a bar for counts.</p>
            ${barChart(deckStats.filter(d => d.n).sort((a, b) => a.v - b.v).concat(deckStats.filter(d => !d.n)), { horizontal: true, max: 100, valueFmt: v => v + '%', fmtTip: i => i.n ? `${i.label}: ${i.v}% correct over ${i.n} answers · ${i.seen}/${i.cards} cards started` : `${i.label}: not studied yet` })}</div>
          <div>
            <div class="panel"><h4>How you rated cards</h4>${barChart(['Again', 'Hard', 'Good', 'Easy'].map((l, k) => ({ label: l, v: ratings[k] })), { horizontal: true, fmtTip: i => `${i.label}: ${i.v} (${pct(i.v, total)})` })}</div>
            <div class="panel"><h4>Cards to work on</h4>${hardest.length ? `<ul class="mini-list">${hardest.map(x => { const info = F.cases[x.c.c] || {}; return `<li><a class="t" href="#/case/${esc(x.c.c)}">${esc(info.n || x.c.c)}</a><div class="m">Forgotten ${x.st.lapses}× · next review ${x.st.due > now ? 'in ' + fcIvlLabel(x.st) : 'now'}</div></li>`; }).join('')}</ul>` : '<p class="muted-line" style="font-size:13px">Cards you forget will be listed here.</p>'}</div>
          </div>
        </div>
      </section></div>`;
    mountTips(app);
  }

  function viewNotFound() {
    app.innerHTML = `<div class="prose fade-in"><h1>Not found</h1><p>That page doesn't exist in the index. <a href="#/">Return home</a>.</p></div>`;
  }

  function bindPager(fn) {
    app.querySelectorAll('.pager button[data-page]').forEach(b => b.addEventListener('click', () => { if (!b.disabled) fn(+b.dataset.page); }));
  }

  /* ------------------------------------------------------------ router */
  /* Scroll handling: filters, sorts and sub-tabs keep the reader's place; real navigation and paging go to the top. */
  let lastRoute = { path: null, params: new URLSearchParams() }, keepScrollOnce = false, forceTopOnce = false, pendingScroll = null;
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#/"]');
    if (a && a.closest('.subtabs, .seg, .chip-row, .filters, [data-keep-scroll]')) keepScrollOnce = true;
    if (a && a.closest('[data-scroll-top]')) forceTopOnce = true;
  }, true);
  function sameViewToggle(path, params) {
    if (path !== lastRoute.path) return false;
    // moving to another page of results goes to the top; a missing page number means page 1
    return (params.get('page') || '1') === (lastRoute.params.get('page') || '1');
  }
  function route() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, qs] = raw.split('?');
    const params = new URLSearchParams(qs || '');
    const keepScroll = !forceTopOnce && (keepScrollOnce || sameViewToggle(path, params));
    forceTopOnce = false;
    const y = window.scrollY;
    keepScrollOnce = false; lastRoute = { path, params };
    const seg = path.split('/');
    routeToken++;
    const navKey = { docket: 'scotus', justices: 'scotus', justice: 'scotus', stats: 'scotus', impact: 'search', library: 'corner', doctrine: 'guide', case: 'scotus', article: 'search', author: 'search', topics: 'search', journals: 'search', book: 'books', notes: 'saved' }[seg[0]] || seg[0] || 'home';
    document.querySelectorAll('.topbar a[data-nav]').forEach(a => a.classList.toggle('active', a.dataset.nav === navKey));
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
      case 'saved': viewSaved(params); break;
      case 'notes': window.LexAnnot ? LexAnnot.renderNotesPage(app) : viewNotFound(); break;
      case 'impact': viewImpact(params); break;
      case 'scotus': viewScotus(params); break;
      case 'docket': viewDocket(params); break;
      case 'justices': viewJustices(); break;
      case 'justice': viewJustice(decodeURIComponent(seg[1] || '')); break;
      case 'statutes': viewStatutes(seg[1], params); break;
      case 'stats': { const tk = routeToken; ext().then(X => { if (tk === routeToken) X.viewStats(params); }).catch(e => { app.innerHTML = `<div class="prose"><h1>Couldn't load this section</h1><p>${esc(e.message)}</p></div>`; }); break; }
      case 'case': viewCase(decodeURIComponent(seg.slice(1).join('/')), params); break;
      case 'lectures': viewLectures(params); break;
      case 'books': viewBooks(params); break;
      case 'book': viewBook(decodeURIComponent(seg[1] || '')); break;
      case 'guide': seg[1] ? viewGuideTopic(seg[1]) : viewGuide(); break;
      case 'doctrine': viewDoctrine(seg[1], seg[2]); break;
      case 'quiz': viewQuiz(seg); break;
      case 'corner': seg[1] === 'constitution' ? viewConstitution(params) : seg[1] ? viewCornerTopic(seg[1], params) : viewCorner(); break;
      case 'library': viewLibrary(seg, params); break;
      case 'about': viewAbout(); break;
      default: viewNotFound();
    }
    pendingScroll = keepScroll ? y : null;   // applied again by withData once lazily loaded data has rendered
    if (keepScroll) {
      // re-renders replace the page; restore the position now and again once the new content has laid out
      const restore = () => window.scrollTo({ top: Math.min(y, document.documentElement.scrollHeight - innerHeight), behavior: 'instant' in window ? 'instant' : 'auto' });
      restore(); requestAnimationFrame(restore); setTimeout(restore, 120);
    } else window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  /* ------------------------------------------------------------ global wiring */
  app.addEventListener('click', e => {
    const b = e.target.closest('.save-btn');
    if (b) { e.preventDefault(); toggleSave(b.dataset.id); return; }
    const rb = e.target.closest('.read-btn');
    if (rb) { e.preventDefault(); toggleRead(rb.dataset.id); return; }
    const v = e.target.closest('.vtile');
    if (v && v.tagName !== 'A') { e.preventDefault(); openVideo(v.dataset.video, v.dataset.title, v.dataset.ch, v.dataset.start); }
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
  {
    const m = String(window.LC_VER || '').match(/^(\d{4})(\d{2})(\d{2})/);
    document.getElementById('footer-updated').textContent = 'Last updated ' + (m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) : DATA.generated);
  }
  window.addEventListener('hashchange', route);
  persistSaved();
  persistRead();
  route();
})();
