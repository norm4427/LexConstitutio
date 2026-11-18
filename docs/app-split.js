/* Side-by-side view. A link in a page's text that leads to another part of the site opens beside the page instead of
   replacing it (navigation never does: the header, breadcrumbs, tab rows and the reader's toolbars behave as usual;
   right-click a header link and choose "Open side by side" to open a section beside the page on purpose):
   Originalist's Corner and library links from any other section, and justices, law review articles and other cases from
   a case page. Each side holds tabs, like a browser: links opened while side by side become tabs on the other side; tabs
   can be dragged between the sides or reordered, and closed; either side can be closed (when one page is left, the
   ordinary single page comes back). Ctrl/Cmd/Shift-click and middle-click keep their usual browser behaviour, and narrow
   screens (under 900px) don't split.
   Each tab is the site itself in a frame (index.html?embed=1#/route; the site header and footer are hidden there, and the
   frame borrows the article data from this page instead of loading it again). The layout is kept in sessionStorage
   (cl-ws), so a reload restores it. */
(function () {
  'use strict';
  if (window.self !== window.top) { document.documentElement.classList.add('embed'); return; }

  const MIN_W = 900;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const routeOf = h => String(h || '').replace(/^#\/?/, '');
  const S = { on: false, panes: [], focus: 0, ratio: 0.5, ws: null };
  let seq = 0;

  /* Which links open beside the page they are clicked on. */
  function sideRule(from, to) {
    const f = routeOf('#' + from).split('?')[0].split('/'), t = routeOf('#' + to).split('?')[0].split('/');
    const fs = f[0] || '', ts = t[0] || '';
    if ((ts === 'corner' || ts === 'library') && fs !== 'corner' && fs !== 'library') return true;
    if (fs === 'case' && (ts === 'justice' || ts === 'article' || (ts === 'case' && t.slice(1).join('/') !== f.slice(1).join('/')))) return true;
    return false;
  }
  // navigation, not text: these links always behave as ordinary links
  const NAV = '.topbar, .crumbs, .subtabs, .case-tabs, [role="tablist"], .seg, .chip-row, .filters, .pager, .pagination, .bk-bar, .bk-drawer, .bk-nav, .guide-nav, .lec-filters, .footer, .ws-bar, .oc-panel, .oc-menu, .np, .hl-pop';
  function linkTarget(e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return null;
    const a = e.target.closest && e.target.closest('a[href^="#/"]');
    if (!a || a.target || a.hasAttribute('download')) return null;
    return a.getAttribute('href');
  }
  const inText = e => !e.target.closest(NAV);
  // clicks on this page (before the site's own handlers)
  window.addEventListener('click', e => {
    const href = linkTarget(e);
    if (!href) return;
    if (S.on) {
      // the header's links (and anything else on this page) load in the focused side
      if (e.target.closest('.topbar')) { e.preventDefault(); e.stopImmediatePropagation(); loadInFocus(routeOf(href)); }
      return;
    }
    if (innerWidth < MIN_W || !inText(e) || !sideRule(routeOf(location.hash), routeOf(href))) return;
    e.preventDefault(); e.stopImmediatePropagation();
    enter(routeOf(location.hash), routeOf(href));
  }, true);

  /* Right-click a header link: open that section beside the page (or in a new browser tab). */
  let ctx = null;
  function closeCtx() { if (ctx) { ctx.remove(); ctx = null; } }
  document.addEventListener('contextmenu', e => {
    const a = e.target.closest && e.target.closest('.topbar a[href^="#/"]');
    closeCtx();
    if (!a || innerWidth < MIN_W) return;          // the browser's own menu elsewhere, and on small screens
    e.preventDefault();
    const href = a.getAttribute('href');
    ctx = document.createElement('div');
    ctx.className = 'ws-ctx';
    ctx.setAttribute('role', 'menu');
    ctx.innerHTML = `<button role="menuitem" data-act="side">Open side by side</button><button role="menuitem" data-act="here">Open here</button><button role="menuitem" data-act="tab">Open in a new browser tab</button><button role="menuitem" data-act="copy">Copy link</button>`;
    document.body.appendChild(ctx);
    ctx.style.left = Math.min(e.clientX, innerWidth - ctx.offsetWidth - 8) + 'px';
    ctx.style.top = Math.min(e.clientY, innerHeight - ctx.offsetHeight - 8) + 'px';
    ctx.addEventListener('click', ev => {
      const b = ev.target.closest('button'); if (!b) return;
      const url = location.origin + location.pathname + href;
      if (b.dataset.act === 'side') { if (S.on) openTab(routeOf(href), S.focus === 0 ? 1 : 0); else enter(routeOf(location.hash), routeOf(href)); }
      if (b.dataset.act === 'here') { if (S.on) loadInFocus(routeOf(href)); else location.hash = href; }
      if (b.dataset.act === 'tab') window.open(url, '_blank', 'noopener');
      if (b.dataset.act === 'copy' && navigator.clipboard) navigator.clipboard.writeText(url).catch(() => {});
      closeCtx();
    });
    ctx.querySelector('button').focus();
  });
  document.addEventListener('mousedown', e => { if (ctx && !ctx.contains(e.target)) closeCtx(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeCtx(); });
  addEventListener('scroll', closeCtx, { passive: true });
  addEventListener('blur', closeCtx);
  // the search box (and anything else that sets the address) while side by side: load it in the focused side
  window.addEventListener('hashchange', () => { if (S.on && !S.quiet) loadInFocus(routeOf(location.hash)); });

  /* ---------------------------------------------------------------- tabs and frames */
  const frameUrl = route => location.pathname + '?embed=1#/' + route;
  function newFrame(t) {
    t.frame = document.createElement('iframe');
    t.frame.title = 'Side-by-side page';
    t.frame.src = frameUrl(t.route);
    t.frame.addEventListener('load', () => hook(t));
  }
  function makeTab(route) {
    const t = { id: 't' + (++seq), route, title: '' };
    newFrame(t);
    return t;
  }
  function hook(t) {
    let w;
    try { w = t.frame.contentWindow; void w.document; } catch (e) { return; }
    w.addEventListener('click', e => {
      const href = linkTarget(e);
      if (!href || !inText(e) || !sideRule(routeOf(w.location.hash), routeOf(href))) return;
      e.preventDefault(); e.stopImmediatePropagation();
      const pi = paneIndexOf(t);
      openTab(routeOf(href), pi === 0 ? 1 : 0);
    }, true);
    w.addEventListener('pointerdown', () => setFocus(paneIndexOf(t)), true);
    w.addEventListener('hashchange', () => { t.route = routeOf(w.location.hash); save(); title(t); });
    w.document.documentElement.dataset.theme = document.documentElement.dataset.theme || '';
    t.route = routeOf(w.location.hash) || t.route;
    title(t);
  }
  function title(t) {
    let s = '';
    try {
      const d = t.frame.contentDocument;
      const h = d && (d.querySelector('.bk-chead h1') || d.querySelector('#app h1'));
      s = h ? h.textContent.trim().replace(/\s+/g, ' ') : '';
    } catch (e) { /* not loaded */ }
    s = s || t.route.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent).join(' · ') || 'Home';
    if (s !== t.title) {
      t.title = s;
      if (t.el) { t.el.querySelector('span').textContent = s; t.el.title = s; }
    }
  }
  setInterval(() => { if (S.on) S.panes.forEach(p => p.tabs.forEach(title)); }, 1200);
  // keep the frames' light/dark theme with this page's
  new MutationObserver(() => {
    S.panes.forEach(p => p.tabs.forEach(t => { try { t.frame.contentDocument.documentElement.dataset.theme = document.documentElement.dataset.theme || ''; } catch (e) { /* loading */ } }));
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  const paneIndexOf = t => S.panes.findIndex(p => p.tabs.includes(t));
  const findTab = id => { for (const p of S.panes) { const t = p.tabs.find(x => x.id === id); if (t) return [p, t]; } return [null, null]; };

  /* ---------------------------------------------------------------- the workspace */
  function enter(leftRoute, rightRoute) {
    S.on = true; S.panes = [{ tabs: [makeTab(leftRoute)], active: 0 }, { tabs: [makeTab(rightRoute)], active: 0 }];
    S.focus = 1;
    S.ratio = +(sessionStorage.getItem('cl-ws-ratio') || 0.5);
    build();
  }
  function openTab(route, pi) {
    if (!S.on) return enter(routeOf(location.hash), route);
    if (!S.panes[pi]) { S.panes[pi] = { tabs: [], active: 0 }; S.panes = S.panes.filter(Boolean); pi = S.panes.length - 1; }
    const p = S.panes[pi];
    p.tabs.push(makeTab(route)); p.active = p.tabs.length - 1;
    S.focus = pi;
    build();
  }
  function loadInFocus(route) {
    const p = S.panes[S.focus] || S.panes[0]; if (!p) return;
    const t = p.tabs[p.active];
    try { t.frame.contentWindow.location.hash = '#/' + route; } catch (e) { t.frame.src = frameUrl(route); }
    t.route = route; save();
  }
  function setFocus(i) {
    if (i < 0 || i === S.focus) return;
    S.focus = i;
    if (S.ws) S.ws.querySelectorAll('.ws-pane').forEach((el, k) => el.classList.toggle('focus', k === S.focus));
  }
  function exit(route) {
    S.on = false;
    S.panes.forEach(p => p.tabs.forEach(t => t.frame.remove()));
    S.panes = [];
    if (S.ws) S.ws.remove();
    S.ws = null;
    document.body.classList.remove('ws-on');
    sessionStorage.removeItem('cl-ws');
    if (route != null && routeOf(location.hash) !== route) location.hash = '#/' + route;
    window.scrollTo({ top: 0 });
  }
  function normalize() {
    S.panes = S.panes.filter(p => p.tabs.length);
    const all = S.panes.flatMap(p => p.tabs);
    if (all.length <= 1) return exit(all.length ? all[0].route : null), false;
    S.panes.forEach(p => { p.active = Math.max(0, Math.min(p.active, p.tabs.length - 1)); });
    S.focus = Math.max(0, Math.min(S.focus, S.panes.length - 1));
    return true;
  }
  function closeTab(id) {
    const [p, t] = findTab(id); if (!t) return;
    const i = p.tabs.indexOf(t);
    p.tabs.splice(i, 1); t.frame.remove();
    if (p.active >= i) p.active = Math.max(0, p.active - 1);
    if (normalize()) build();
  }
  function closePane(pi) {
    const p = S.panes[pi]; if (!p) return;
    p.tabs.forEach(t => t.frame.remove()); p.tabs = [];
    if (normalize()) build();
  }
  function moveTab(id, pi, before) {
    const [from, t] = findTab(id); if (!t) return;
    if (pi >= S.panes.length) { S.panes.push({ tabs: [], active: 0 }); pi = S.panes.length - 1; }
    const to = S.panes[pi];
    const sameSide = from === to;
    from.tabs.splice(from.tabs.indexOf(t), 1);
    let k = before ? to.tabs.findIndex(x => x.id === before) : -1;
    if (k < 0) k = to.tabs.length;
    to.tabs.splice(k, 0, t);
    to.active = k;
    if (!sameSide) {
      // a frame reloads when it moves in the page, so start it again at the page it was showing
      t.frame.remove();
      newFrame(t);
      if (from.active >= from.tabs.length) from.active = Math.max(0, from.tabs.length - 1);
    }
    S.focus = pi;
    if (normalize()) build();
  }
  function save() {
    if (!S.on) return;
    sessionStorage.setItem('cl-ws', JSON.stringify({ panes: S.panes.map(p => ({ tabs: p.tabs.map(t => t.route), active: p.active })), focus: S.focus }));
  }

  function build() {
    if (!S.ws) {
      S.ws = document.createElement('div');
      S.ws.className = 'ws';
      S.ws.setAttribute('aria-label', 'Pages side by side');
      document.getElementById('app').before(S.ws);
      wire(S.ws);
    }
    document.body.classList.add('ws-on');
    layout();
    // a frame reloads whenever it (or a box around it) moves in the page: sides are only ever added at the end or removed,
    // and each frame stays in its side's box
    [...S.ws.querySelectorAll('.ws-pane')].forEach(el => { if (!S.panes.some(p => p.el === el)) el.remove(); });
    S.panes.forEach((p, i) => {
      let el = p.el;
      if (!el) {
        el = p.el = document.createElement('section');
        el.className = 'ws-pane';
        el.innerHTML = '<div class="ws-bar" role="tablist"></div><div class="ws-body"></div>';
        S.ws.appendChild(el);
      }
      el.dataset.pane = i;
      el.classList.toggle('focus', i === S.focus);
      const body = el.querySelector('.ws-body');
      p.tabs.forEach((t, k) => {
        if (t.frame.parentNode !== body) body.appendChild(t.frame);
        t.frame.classList.toggle('on', k === p.active);
      });
      const other = S.panes.length > 1 ? (i === 0 ? 'right' : 'left') : 'other';
      el.querySelector('.ws-bar').innerHTML = p.tabs.map((t, k) => `<div class="ws-tab${k === p.active ? ' on' : ''}" role="tab" aria-selected="${k === p.active}" draggable="true" data-id="${t.id}" title="${esc(t.title || t.route)}"><span>${esc(t.title || 'Loading…')}</span><button class="ws-x" data-close="${t.id}" title="Close this tab" aria-label="Close this tab">×</button></div>`).join('')
        + `<div class="ws-sp"></div><button class="ws-btn" data-move="${i}" title="Move this tab to the ${other} side" aria-label="Move this tab to the ${other} side">⇄</button><button class="ws-btn" data-full="${i}" title="Show this page on its own" aria-label="Show this page on its own">⤢</button><button class="ws-btn ws-close" data-closepane="${i}" title="Close this side" aria-label="Close this side">×</button>`;
      p.tabs.forEach(t => { t.el = el.querySelector(`.ws-tab[data-id="${t.id}"]`); });
    });
    let div = S.ws.querySelector('.ws-div');
    if (S.panes.length > 1) {
      if (!div) { div = document.createElement('div'); div.className = 'ws-div'; div.setAttribute('role', 'separator'); div.title = 'Drag to resize'; }
      if (div.nextElementSibling !== S.panes[1].el) S.ws.insertBefore(div, S.panes[1].el);
    } else if (div) div.remove();
    S.ws.style.setProperty('--ws-r', S.panes.length > 1 ? S.ratio : 1);
    save();
  }
  function layout() {
    if (!S.ws) return;
    const bar = document.querySelector('.topbar');
    const top = bar ? bar.getBoundingClientRect().bottom : 0;
    S.ws.style.height = Math.max(300, innerHeight - Math.max(0, top)) + 'px';
  }
  addEventListener('resize', layout);

  function wire(ws) {
    ws.addEventListener('click', e => {
      const b = e.target.closest('button');
      const tab = e.target.closest('.ws-tab');
      if (b && b.dataset.close) return closeTab(b.dataset.close);
      if (b && b.dataset.closepane != null) return closePane(+b.dataset.closepane);
      if (b && b.dataset.full != null) { const p = S.panes[+b.dataset.full]; return exit(p.tabs[p.active].route); }
      if (b && b.dataset.move != null) {
        const pi = +b.dataset.move, p = S.panes[pi];
        return moveTab(p.tabs[p.active].id, S.panes.length > 1 ? (pi === 0 ? 1 : 0) : 1);
      }
      if (tab) {
        const [p, t] = findTab(tab.dataset.id);
        p.active = p.tabs.indexOf(t); setFocus(S.panes.indexOf(p)); build();
      }
    });
    ws.addEventListener('auxclick', e => { const tab = e.target.closest('.ws-tab'); if (tab && e.button === 1) { e.preventDefault(); closeTab(tab.dataset.id); } });
    // drag a tab to the other side (or along its own bar); with one side open, drop on the right half to split again
    let dragId = null;
    ws.addEventListener('dragstart', e => {
      const tab = e.target.closest('.ws-tab'); if (!tab) return;
      dragId = tab.dataset.id;
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', dragId);
      ws.classList.add('dragging');
      if (S.panes.length === 1) ws.insertAdjacentHTML('beforeend', '<div class="ws-new" data-newpane>Drop here to open side by side</div>');
    });
    const clear = () => { dragId = null; ws.classList.remove('dragging'); ws.querySelectorAll('.drop-before,.drop-pane').forEach(x => x.classList.remove('drop-before', 'drop-pane')); const n = ws.querySelector('[data-newpane]'); if (n) n.remove(); };
    ws.addEventListener('dragend', clear);
    ws.addEventListener('dragover', e => {
      if (!dragId) return;
      const zone = e.target.closest('[data-newpane], .ws-pane'); if (!zone) return;
      e.preventDefault(); e.dataTransfer.dropEffect = 'move';
      ws.querySelectorAll('.drop-before,.drop-pane').forEach(x => x.classList.remove('drop-before', 'drop-pane'));
      const tab = e.target.closest('.ws-tab');
      if (tab && tab.dataset.id !== dragId) tab.classList.add('drop-before');
      else if (!zone.dataset.newpane) zone.classList.add('drop-pane');
    });
    ws.addEventListener('drop', e => {
      if (!dragId) return;
      e.preventDefault();
      const id = dragId, nz = e.target.closest('[data-newpane]'), pane = e.target.closest('.ws-pane'), tab = e.target.closest('.ws-tab');
      clear();
      if (nz) return moveTab(id, S.panes.length);
      if (pane) moveTab(id, +pane.dataset.pane, tab && tab.dataset.id !== id ? tab.dataset.id : null);
    });
    // resize the two sides
    ws.addEventListener('pointerdown', e => {
      const d = e.target.closest('.ws-div'); if (!d) return;
      e.preventDefault(); d.setPointerCapture(e.pointerId); ws.classList.add('dragging');
      const r0 = ws.getBoundingClientRect();
      const move = ev => { S.ratio = Math.max(0.2, Math.min(0.8, (ev.clientX - r0.left) / r0.width)); ws.style.setProperty('--ws-r', S.ratio); };
      const up = () => { d.removeEventListener('pointermove', move); d.removeEventListener('pointerup', up); ws.classList.remove('dragging'); sessionStorage.setItem('cl-ws-ratio', S.ratio); };
      d.addEventListener('pointermove', move); d.addEventListener('pointerup', up);
    });
  }

  // a reload brings the side-by-side layout back
  function restore() {
    let st = null; try { st = JSON.parse(sessionStorage.getItem('cl-ws') || 'null'); } catch (e) { /* ignore */ }
    if (!st || !st.panes || innerWidth < MIN_W) return;
    const panes = st.panes.filter(p => p.tabs && p.tabs.length);
    if (panes.reduce((n, p) => n + p.tabs.length, 0) < 2) return sessionStorage.removeItem('cl-ws');
    S.on = true; S.ratio = +(sessionStorage.getItem('cl-ws-ratio') || 0.5);
    S.panes = panes.map(p => ({ tabs: p.tabs.map(makeTab), active: p.active || 0 }));
    S.focus = st.focus || 0;
    build();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restore); else restore();

  window.LexSplit = { open: route => openTab(route, S.on ? (S.focus === 0 ? 1 : 0) : 1), sideRule, state: S };
})();
