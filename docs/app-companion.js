/* The Originalist's Companion: a button in the bottom-right corner of every page that opens a compact Originalist's
   Corner: the text of the Constitution (searchable; select a word to look it up; each annotated clause links to its
   annotation) and one searchable dictionary combining the site's dictionaries: Johnson (1755), Webster (1828) and
   Bouvier's law dictionary (1856) from data/founding-dict.js, and the legal glossary (Wex and the U.S. Courts) from
   data/glossary.js. Data loads the first time the panel needs it. Links open beside the page when the side-by-side
   view is available (app-split.js), otherwise in place. */
(function () {
  'use strict';
  if (window.self !== window.top) return;   // not inside a side-by-side tab
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’']/g, "'").trim();
  const loaded = {};
  function load(name, global) {
    if (window[global]) return Promise.resolve(window[global]);
    if (!loaded[name]) loaded[name] = new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = `data/${name}.js?v=${window.LC_VER || ''}`;
      s.onload = () => res(window[global]);
      s.onerror = () => { delete loaded[name]; rej(new Error(`Couldn't load ${name}`)); };
      document.body.appendChild(s);
    });
    return loaded[name];
  }
  function go(route) {
    // open beside the current page when there's room for it, otherwise in place
    if (window.LexSplit && innerWidth >= 900) window.LexSplit.open(route.replace(/^#\/?/, ''));
    else location.hash = route;
  }

  /* ---------------------------------------------------------------- button, menu, panel */
  const btn = document.createElement('button');
  btn.className = 'oc-btn';
  btn.type = 'button';
  btn.setAttribute('aria-haspopup', 'menu');
  btn.setAttribute('aria-expanded', 'false');
  btn.title = "Originalist's Companion: the Constitution and the founding-era dictionaries";
  btn.innerHTML = '<span aria-hidden="true">§</span><b>Companion</b>';
  const menu = document.createElement('div');
  menu.className = 'oc-menu';
  menu.hidden = true;
  menu.setAttribute('role', 'menu');
  menu.innerHTML = `<div class="oc-menu-h">Originalist's Companion</div>
    <button role="menuitem" data-open="con"><b>The Constitution</b><span>The full text, searchable; select a word to look it up</span></button>
    <button role="menuitem" data-open="dict"><b>Dictionary</b><span>Johnson (1755), Webster (1828), Bouvier (1856) and a legal glossary, searched together</span></button>
    <a role="menuitem" href="#/corner" class="oc-menu-more">The full Originalist's Corner →</a>`;
  const panel = document.createElement('aside');
  panel.className = 'oc-panel';
  panel.hidden = true;
  panel.setAttribute('aria-label', "Originalist's Companion");
  panel.innerHTML = `<div class="oc-head"><div class="oc-tabs" role="tablist"><button role="tab" data-tab="con">Constitution</button><button role="tab" data-tab="dict">Dictionary</button></div>
      <button class="oc-x" title="Close" aria-label="Close the Companion">×</button></div>
    <div class="oc-search"><input type="search" autocomplete="off" spellcheck="false"></div>
    <div class="oc-body" tabindex="-1"></div>`;
  document.body.append(btn, menu, panel);
  const input = panel.querySelector('input'), body = panel.querySelector('.oc-body');
  let tab = 'con', current = null;   // current: the dictionary entry shown, if any

  function openMenu(open) {
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    if (open) panel.hidden = true;
  }
  function openPanel(which, word) {
    openMenu(false);
    panel.hidden = false;
    setTab(which);
    if (word != null) { input.value = word; current = null; }
    render();
    if (word == null) setTimeout(() => input.focus(), 30);
  }
  function setTab(which) {
    tab = which;
    panel.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    input.placeholder = tab === 'con' ? 'Find in the Constitution…' : 'Look up a word or phrase…';
    input.setAttribute('aria-label', input.placeholder);
  }
  btn.addEventListener('click', () => { if (!panel.hidden) { panel.hidden = true; return; } openMenu(menu.hidden); });
  menu.addEventListener('click', e => {
    const b = e.target.closest('[data-open]');
    if (b) { input.value = ''; current = null; openPanel(b.dataset.open); }
    else if (e.target.closest('a')) openMenu(false);
  });
  panel.addEventListener('click', e => {
    if (e.target.closest('.oc-x')) { panel.hidden = true; btn.focus(); return; }
    const t = e.target.closest('[data-tab]');
    if (t) { setTab(t.dataset.tab); input.value = ''; current = null; render(); input.focus(); return; }
    const w = e.target.closest('.oc-w');
    if (w) { openPanel('dict', w.textContent); return; }
    const r = e.target.closest('[data-entry]');
    if (r) { current = r.dataset.entry; render(); body.scrollTop = 0; return; }
    if (e.target.closest('[data-back]')) { current = null; render(); return; }
    const a = e.target.closest('a[href^="#/"]');
    if (a) { e.preventDefault(); e.stopPropagation(); go(a.getAttribute('href')); }
  });
  let tmr = 0;
  input.addEventListener('input', () => { clearTimeout(tmr); current = null; tmr = setTimeout(render, 120); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (!menu.hidden) openMenu(false); else if (!panel.hidden && document.activeElement && panel.contains(document.activeElement)) panel.hidden = true; } });
  document.addEventListener('mousedown', e => { if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) openMenu(false); });

  function render() {
    body.innerHTML = '<div class="oc-load">Loading…</div>';
    (tab === 'con' ? renderCon() : renderDict()).catch(err => { body.innerHTML = `<p class="oc-empty">${esc(err.message)}. Try again in a moment.</p>`; });
  }

  /* ---------------------------------------------------------------- the Constitution */
  const words = t => t.split(/([A-Za-z]+(?:['’][a-z]+)?)/).map((w, i) => (i % 2 ? `<span class="oc-w">${w}</span>` : esc(w))).join('');
  function mark(t, q) {
    if (!q) return words(t);
    const i = norm(t).indexOf(q);
    if (i < 0) return words(t);
    return words(t.slice(0, i)) + `<mark>${words(t.slice(i, i + q.length))}</mark>` + mark(t.slice(i + q.length), q);
  }
  function renderCon() {
    return load('constitution', 'CONSTITUTION').then(C => {
      if (tab !== 'con') return;
      const q = norm(input.value);
      const byUnit = {};
      (C.clauses || []).forEach(c => { if (c.unit && !byUnit[c.unit]) byUnit[c.unit] = c; });
      const units = C.units.filter(u => !q || norm(u.text).includes(q) || norm(u.label).includes(q));
      let group = '';
      const out = units.map(u => {
        const h = u.group !== group ? `<h4 class="oc-group">${esc(group = u.group)}</h4>` : '';
        const cl = byUnit[u.id];
        return `${h}<div class="oc-unit"><div class="oc-label"><span>${esc(u.label)}</span>${cl ? `<a href="#/corner/constitution?c=${esc(cl.id)}" title="${esc(cl.name)}: what it meant, the leading cases and founding-era commentary">Annotated →</a>` : ''}</div><p>${mark(u.text, q)}</p></div>`;
      }).join('');
      body.innerHTML = (q ? `<p class="oc-count">${units.length} ${units.length === 1 ? 'clause' : 'clauses'} contain “${esc(input.value.trim())}”</p>` : '<p class="oc-hint">Select any word to see how founding-era dictionaries defined it.</p>')
        + (out || '<p class="oc-empty">No clause contains that.</p>')
        + '<p class="oc-src">Text: National Archives transcription. <a href="#/corner/constitution">The Annotated Constitution →</a></p>';
    });
  }

  /* ---------------------------------------------------------------- the dictionary */
  let index = null;
  function buildIndex(D, G) {
    const m = new Map();
    const add = (hw, src, data) => {
      const k = norm(hw);
      if (!m.has(k)) m.set(k, { k, hw, src: {} });
      m.get(k).src[src] = data;
    };
    Object.entries(D.words || {}).forEach(([w, v]) => { ['j', 'w', 'b'].forEach(s => { if (v[s]) add(v[s].hw || w, s, v[s]); }); });
    Object.entries(D.phrases || {}).forEach(([p, v]) => add(v.hw || p, 'b', v));
    Object.entries((G && G.terms) || {}).forEach(([t, v]) => add(t, 'g', v));
    return [...m.values()].sort((a, b) => a.k.localeCompare(b.k));
  }
  const SRC = [['j', 'Johnson, 1755'], ['w', 'Webster, 1828'], ['b', 'Bouvier’s Law Dictionary, 1856'], ['g', 'Legal glossary (modern)']];
  function renderDict() {
    return Promise.all([load('founding-dict', 'FOUNDING_DICT'), load('glossary', 'GLOSSARY').catch(() => null)]).then(([D, G]) => {
      if (tab !== 'dict') return;
      if (!index) index = buildIndex(D, G);
      const q = norm(input.value);
      if (current) {
        const e = index.find(x => x.k === current);
        if (e) return showEntry(e, D, G);
      }
      if (!q) {
        const picks = ['commerce', 'militia', 'emolument', 'ex post facto', 'bill of attainder', 'due process', 'natural born', 'regulate', 'necessary', 'arms', 'habeas corpus', 'treason'].map(norm).filter(k => index.some(x => x.k === k));
        body.innerHTML = `<p class="oc-hint">${index.length.toLocaleString('en-US')} words and phrases: every word of the Constitution as Johnson (1755), Webster (1828) and Bouvier (1856) defined it, and a modern legal glossary. Try:</p>
          <div class="oc-chips">${picks.map(k => `<button class="chip" data-entry="${esc(k)}">${esc(index.find(x => x.k === k).hw)}</button>`).join('')}</div>`;
        return;
      }
      const exact = index.filter(x => x.k === q), starts = index.filter(x => x.k !== q && x.k.startsWith(q)), has = index.filter(x => !x.k.startsWith(q) && x.k.includes(q));
      const list = [...exact, ...starts, ...has].slice(0, 60);
      if (exact.length === 1 && !starts.length) return showEntry(exact[0], D, G);
      body.innerHTML = list.length ? `<ul class="oc-results">${list.map(x => `<li><button data-entry="${esc(x.k)}"><b>${esc(x.hw)}</b><span>${SRC.filter(([s]) => x.src[s]).map(([, n]) => esc(n.split(',')[0].replace('’s Law Dictionary', ''))).join(' · ')}</span></button></li>`).join('')}</ul>`
        : `<p class="oc-empty">No entry for “${esc(input.value.trim())}”. The founding-era dictionaries here cover the words that appear in the Constitution.</p>`;
    });
  }
  function showEntry(e, D, G) {
    const part = (s, name) => {
      const v = e.src[s];
      if (!v) return '';
      if (s === 'g') {
        const paras = (v.l && v.l.length ? v.l : [v.s]).filter(Boolean);
        const credit = (G && G.src && G.src[v.src]) || '';
        return `<section class="oc-def"><h5>${esc(name)}</h5>${paras.map(p => `<p>${esc(p)}</p>`).join('')}<p class="oc-src">${esc(credit)}${v.url ? ` · <a href="${esc(v.url)}" target="_blank" rel="noopener">Source ↗</a>` : ''}</p></section>`;
      }
      return `<section class="oc-def"><h5>${esc(name)}</h5>${(v.e || []).map(x => `<p>${x.pos ? `<i>${esc(x.pos)}</i> ` : ''}${esc(x.t)}</p>`).join('')}</section>`;
    };
    body.innerHTML = `<button class="oc-back" data-back>← Results</button><h3 class="oc-hw">${esc(e.hw)}</h3>${SRC.map(([s, n]) => part(s, n)).join('')}
      <p class="oc-src">${esc([D.src.j, D.src.w, D.src.b].join(' · '))}. <a href="#/corner/constitution?mode=dict">The dictionary beside the Constitution →</a></p>`;
  }
})();
