/* Highlights and notes for the library readers (the book reader and the Federalist / founding documents / statutes reader).
   Select text to highlight it (four colours), click a highlight to recolour it, add a short note or remove it. A side pane
   (toggle "Notes") holds free-form notes for the book with "Insert quote" from the current selection (with a citation),
   and a Highlights tab that lists every highlight in the book and jumps to it. Notes copy cleanly into OneNote (rich text)
   and download as .md or .html; highlights copy as text or download as Markdown.
   Everything stays in this browser's localStorage:
     cl-hl:<doc>         [{id, ch, chLabel, cite, p1, s, p2, e, c, t, note, at}]   p1/p2 = block indexes (#bk-<i>), s/e = character offsets
     cl-notes:<doc>      the notes (HTML), cl-notes-open:<doc> whether the pane is open, cl-notes-tab, cl-notes-w the pane width
   OneNote for the web can't be shown inside the page (it sends CSP frame-ancestors 'self'), so "Open OneNote" opens it in a
   separate window placed beside this one. */
(function () {
  'use strict';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const COLORS = [['y', 'Yellow'], ['g', 'Green'], ['b', 'Blue'], ['p', 'Pink']];
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { say('Couldn’t save: this browser’s storage is full or blocked.'); return false; } },
  };
  const hlKey = doc => 'cl-hl:' + doc;
  const loadHl = doc => ls.get(hlKey(doc), []);
  const saveHl = (doc, a) => ls.set(hlKey(doc), a);
  const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
  const absUrl = hash => location.origin + location.pathname + hash;
  function say(msg) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg; t.classList.add('show');
    clearTimeout(say._t); say._t = setTimeout(() => t.classList.remove('show'), 2000);
  }

  let ctx = null;          // the mounted reader: {doc, ch, chLabel, cite, title, author, href, textEl, root, toolsEl}
  let lastSel = null;      // the last selection made in the text: {p1, s, p2, e, t}
  let pop = null;

  /* ---------------------------------------------------------------- offsets <-> DOM */
  const blocks = () => ctx ? [...ctx.textEl.querySelectorAll('[id^="bk-"]')] : [];
  const blockIdx = b => +b.id.slice(3);
  function textLen(b) { return b.textContent.length; }
  function offsetIn(block, node, off) {
    const r = document.createRange(); r.setStart(block, 0);
    try { r.setEnd(node, off); } catch (e) { return 0; }
    return r.toString().length;
  }
  function selectionInfo() {
    const sel = window.getSelection();
    if (!ctx || !sel || sel.isCollapsed || !sel.rangeCount) return null;
    const r = sel.getRangeAt(0);
    if (!ctx.textEl.contains(r.commonAncestorContainer) && r.commonAncestorContainer !== ctx.textEl) return null;
    const bs = blocks().filter(b => r.intersectsNode(b));
    if (!bs.length) return null;
    const b1 = bs[0], b2 = bs[bs.length - 1];
    const s = b1.contains(r.startContainer) ? offsetIn(b1, r.startContainer, r.startOffset) : 0;
    const e = b2.contains(r.endContainer) ? offsetIn(b2, r.endContainer, r.endOffset) : textLen(b2);
    // snap to whole words
    const t1 = b1.textContent, t2 = b2.textContent, w = /[\p{L}\p{N}'’]/u;
    let ss = s, ee = e;
    while (ss > 0 && w.test(t1[ss - 1]) && w.test(t1[ss])) ss--;
    while (ss < t1.length && /\s/.test(t1[ss])) ss++;
    while (ee < t2.length && w.test(t2[ee - 1] || '') && w.test(t2[ee])) ee++;
    while (ee > 0 && /\s/.test(t2[ee - 1])) ee--;
    const info = { p1: blockIdx(b1), s: ss, p2: blockIdx(b2), e: ee };
    info.t = spanText(info) || norm(r.toString());
    if (!info.t || (info.p1 === info.p2 && info.e <= info.s)) return null;
    return info;
  }
  function spanText(h) {
    const out = [];
    for (let p = h.p1; p <= h.p2; p++) {
      const b = document.getElementById('bk-' + p); if (!b) return null;
      const tx = b.textContent;
      out.push(tx.slice(p === h.p1 ? h.s : 0, p === h.p2 ? h.e : tx.length));
    }
    return norm(out.join(' '));
  }
  function wrapBlock(block, s, e, h) {
    const w = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let pos = 0, t; const parts = [];
    while ((t = w.nextNode())) {
      const L = t.length, a = Math.max(s, pos), z = Math.min(e, pos + L);
      if (a < z) parts.push([t, a - pos, z - pos]);
      pos += L; if (pos >= e) break;
    }
    for (const [node0, a, z] of parts) {
      let node = node0;
      if (z < node.length) node.splitText(z);
      if (a > 0) node = node.splitText(a);
      const m = document.createElement('mark');
      m.className = 'hl hl-' + (h.c || 'y') + (h.note ? ' has-note' : '');
      m.dataset.hl = h.id;
      if (h.note) m.title = h.note;
      node.parentNode.insertBefore(m, node); m.appendChild(node);
    }
  }
  function paint(h) {
    for (let p = h.p1; p <= h.p2; p++) {
      const b = document.getElementById('bk-' + p); if (!b) continue;
      wrapBlock(b, p === h.p1 ? h.s : 0, p === h.p2 ? h.e : textLen(b), h);
    }
  }
  function unpaint(id) {
    const marks = ctx ? ctx.textEl.querySelectorAll(`mark[data-hl="${id}"]`) : [];
    const parents = new Set();
    marks.forEach(m => { parents.add(m.parentNode); while (m.firstChild) m.parentNode.insertBefore(m.firstChild, m); m.remove(); });
    parents.forEach(p => p.normalize());
  }
  function applyAll() {
    const all = loadHl(ctx.doc); let fixed = false;
    all.filter(h => String(h.ch) === String(ctx.ch)).sort((a, b) => a.p1 - b.p1 || a.s - b.s).forEach(h => {
      const bare = x => String(x || '').replace(/\s+/g, '');
      if (bare(spanText(h)) === bare(h.t)) { if (h.lost) { delete h.lost; fixed = true; } }
      else {
        // the text moved (an edition was rebuilt): look for the quote in its first paragraph
        const b = document.getElementById('bk-' + h.p1), i = b ? b.textContent.indexOf(h.t) : -1;
        if (i < 0 || h.p1 !== h.p2) { h.lost = 1; fixed = true; return; }
        h.s = i; h.e = i + h.t.length; delete h.lost; fixed = true;
      }
      paint(h);
    });
    if (fixed) saveHl(ctx.doc, all);
  }

  /* ---------------------------------------------------------------- the floating toolbar */
  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement('div');
    pop.className = 'hl-pop'; pop.hidden = true; pop.setAttribute('role', 'toolbar');
    // keep the text selection while the toolbar's buttons are pressed
    pop.addEventListener('mousedown', e => { if (!e.target.closest('textarea')) e.preventDefault(); });
    pop.addEventListener('click', onPopClick);
    document.body.appendChild(pop);
    return pop;
  }
  function hidePop() { if (pop) { pop.hidden = true; pop.dataset.mode = ''; } }
  function placePop(rect) {
    const p = ensurePop(); p.hidden = false;
    const coarse = matchMedia('(pointer: coarse)').matches;
    const pw = p.offsetWidth, ph = p.offsetHeight;
    let top = (coarse ? rect.bottom + 12 : rect.top - ph - 10) + scrollY;
    if (!coarse && rect.top - ph - 10 < 70) top = rect.bottom + 10 + scrollY;
    const left = Math.max(8 + scrollX, Math.min(scrollX + innerWidth - pw - 8, rect.left + rect.width / 2 - pw / 2 + scrollX));
    p.style.top = top + 'px'; p.style.left = left + 'px';
  }
  const swatches = cur => COLORS.map(([c, n]) => `<button class="hl-sw hl-${c}${cur === c ? ' on' : ''}" data-color="${c}" title="${n}" aria-label="Highlight ${n.toLowerCase()}"></button>`).join('');
  function showSelPop() {
    const info = selectionInfo();
    if (!info) { if (pop && pop.dataset.mode === 'sel') hidePop(); return; }
    lastSel = info;
    const p = ensurePop(); p.dataset.mode = 'sel';
    p.innerHTML = `${swatches('')}<span class="hl-sep"></span><button data-act="note" title="Highlight and add a note">Note</button><button data-act="quote" title="Insert this passage, with a citation, into your notes">Quote to notes</button><button data-act="copy" title="Copy the passage with a citation">Copy</button>`;
    placePop(window.getSelection().getRangeAt(0).getBoundingClientRect());
  }
  function showMarkPop(id, rect) {
    const h = loadHl(ctx.doc).find(x => x.id === id); if (!h) return;
    const p = ensurePop(); p.dataset.mode = 'mark'; p.dataset.id = id;
    p.innerHTML = `<div class="hl-row">${swatches(h.c)}<span class="hl-sep"></span><button data-act="copy-h">Copy</button><button data-act="quote-h">Quote to notes</button><button data-act="del" class="hl-del" title="Remove this highlight">Remove</button></div>
      <div class="hl-note"><textarea rows="2" maxlength="600" placeholder="Add a short note…">${esc(h.note || '')}</textarea><button data-act="save-note" class="hl-save">Save note</button></div>`;
    placePop(rect);
  }
  function create(info, color, note) {
    const all = loadHl(ctx.doc);
    const h = { id: uid(), ch: String(ctx.ch), chLabel: ctx.chLabel, cite: ctx.cite, p1: info.p1, s: info.s, p2: info.p2, e: info.e, c: color, t: info.t, at: Date.now() };
    if (note) h.note = note;
    all.push(h);
    if (!saveHl(ctx.doc, all)) return null;
    paint(h); refreshLists();
    return h;
  }
  function update(id, fn) {
    const all = loadHl(ctx.doc), h = all.find(x => x.id === id); if (!h) return;
    fn(h); saveHl(ctx.doc, all);
    unpaint(id); paint(h); refreshLists();
  }
  function removeHl(doc, id) {
    saveHl(doc, loadHl(doc).filter(x => x.id !== id));
    if (ctx && ctx.doc === doc) { unpaint(id); refreshLists(); }
  }
  const citeLine = (cite, hash) => `${cite}${hash ? ' — ' + absUrl(hash) : ''}`;
  function copyText(t) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(t).then(() => say('Copied'), () => fallbackCopy(t));
    fallbackCopy(t);
  }
  function fallbackCopy(t) {
    const ta = document.createElement('textarea'); ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); say('Copied'); } catch (e) { say('Couldn’t copy'); }
    ta.remove();
  }
  function onPopClick(e) {
    const b = e.target.closest('button'); if (!b || !ctx) return;
    const mode = pop.dataset.mode, id = pop.dataset.id;
    if (mode === 'sel') {
      const info = lastSel; if (!info) return hidePop();
      if (b.dataset.color) { create(info, b.dataset.color); window.getSelection().removeAllRanges(); hidePop(); return; }
      if (b.dataset.act === 'note') {
        const h = create(info, 'y'); window.getSelection().removeAllRanges();
        if (h) { const m = ctx.textEl.querySelector(`mark[data-hl="${h.id}"]`); showMarkPop(h.id, m.getBoundingClientRect()); pop.querySelector('textarea').focus(); }
        return;
      }
      if (b.dataset.act === 'quote') { insertQuote(info.t, ctx.cite, ctx.href(ctx.ch)); hidePop(); return; }
      if (b.dataset.act === 'copy') { copyText(`“${info.t}”\n— ${citeLine(ctx.cite, ctx.href(ctx.ch))}`); hidePop(); return; }
    }
    if (mode === 'mark') {
      const h = loadHl(ctx.doc).find(x => x.id === id); if (!h) return hidePop();
      if (b.dataset.color) { update(id, x => { x.c = b.dataset.color; }); pop.querySelectorAll('.hl-sw').forEach(s => s.classList.toggle('on', s.dataset.color === b.dataset.color)); return; }
      if (b.dataset.act === 'del') { removeHl(ctx.doc, id); hidePop(); say('Highlight removed'); return; }
      if (b.dataset.act === 'save-note') { const v = norm(pop.querySelector('textarea').value); update(id, x => { if (v) x.note = v; else delete x.note; }); hidePop(); say(v ? 'Note saved' : 'Note removed'); return; }
      if (b.dataset.act === 'copy-h') { copyText(`“${h.t}”${h.note ? '\nNote: ' + h.note : ''}\n— ${citeLine(h.cite, ctx.href(h.ch))}`); hidePop(); return; }
      if (b.dataset.act === 'quote-h') { insertQuote(h.t, h.cite, ctx.href(h.ch)); hidePop(); return; }
    }
  }
  let selTmr = 0;
  document.addEventListener('selectionchange', () => {
    if (!ctx) return;
    clearTimeout(selTmr); selTmr = setTimeout(showSelPop, matchMedia('(pointer: coarse)').matches ? 350 : 220);
  });
  document.addEventListener('mousedown', e => { if (pop && !pop.hidden && !pop.contains(e.target) && !e.target.closest('mark.hl')) hidePop(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hidePop(); });
  window.addEventListener('hashchange', () => { hidePop(); ctx = null; if (pane) { pane.remove(); pane = null; } });

  /* ---------------------------------------------------------------- highlight lists and exports */
  function groups(all) {
    const by = new Map();
    all.slice().sort((a, b) => (isNaN(a.ch) || isNaN(b.ch) ? String(a.ch).localeCompare(String(b.ch)) : a.ch - b.ch) || a.p1 - b.p1 || a.s - b.s)
      .forEach(h => { if (!by.has(h.ch)) by.set(h.ch, []); by.get(h.ch).push(h); });
    return [...by.entries()];
  }
  function listHtml(doc, opts) {
    const all = loadHl(doc);
    if (!all.length) return `<p class="hl-empty">No highlights yet. Select any passage in the text to highlight it.</p>`;
    return `<div class="hl-export"><button class="btn btn-ghost btn-sm" data-hlx="copy">Copy as text</button><button class="btn btn-ghost btn-sm" data-hlx="md">Download Markdown</button></div>
      ${groups(all).map(([ch, hs]) => `<div class="hl-grp"><h5>${esc(hs[0].chLabel || ch)}</h5><ul>${hs.map(h => `<li class="hl-item${h.lost ? ' lost' : ''}">
        <a href="${esc(opts.href(h.ch))}" data-hl-go="${esc(h.id)}" data-ch="${esc(h.ch)}"><i class="hl-dot hl-${esc(h.c || 'y')}"></i><span>${esc(h.t.length > 220 ? h.t.slice(0, 218) + '…' : h.t)}</span></a>
        ${h.note ? `<p class="hl-n">${esc(h.note)}</p>` : ''}${h.lost ? '<p class="hl-n">This passage is no longer found in the text.</p>' : ''}
        <button class="hl-x" data-hl-del="${esc(h.id)}" title="Remove this highlight" aria-label="Remove this highlight">×</button></li>`).join('')}</ul></div>`).join('')}`;
  }
  function exportText(doc, opts, md) {
    const all = loadHl(doc), L = [];
    L.push(md ? `# Highlights: ${opts.title}${opts.author ? ' (' + opts.author + ')' : ''}` : `Highlights: ${opts.title}${opts.author ? ' (' + opts.author + ')' : ''}`);
    L.push(`Exported from Lex Constitutio, ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}`, '');
    groups(all).forEach(([ch, hs]) => {
      L.push(md ? `## ${hs[0].chLabel || ch}` : `${hs[0].chLabel || ch}`, md ? '' : '-'.repeat(Math.min(60, String(hs[0].chLabel || ch).length)));
      hs.forEach(h => {
        L.push(md ? `> ${h.t}` : `“${h.t}”`);
        if (h.note) L.push(md ? '' : '', `Note: ${h.note}`);
        L.push(md ? '' : '', `— ${h.cite}${md ? ` ([link](${absUrl(opts.href(h.ch))}))` : ', ' + absUrl(opts.href(h.ch))}`, '');
      });
    });
    return L.join('\n').replace(/\n{3,}/g, '\n\n');
  }
  function download(name, text, type) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: type + ';charset=utf-8' }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  const slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'notes';
  function bindList(el, doc, opts) {
    if (!el || el._hlBound) return; el._hlBound = true;
    el.addEventListener('click', e => {
      const x = e.target.closest('[data-hlx]'), del = e.target.closest('[data-hl-del]'), go = e.target.closest('[data-hl-go]');
      if (x) {
        e.preventDefault();
        if (x.dataset.hlx === 'copy') copyText(exportText(doc, opts, false));
        else download(slug(opts.title) + '-highlights.md', exportText(doc, opts, true), 'text/markdown');
        return;
      }
      if (del) { e.preventDefault(); removeHl(doc, del.dataset.hlDel); if (!ctx || ctx.doc !== doc) el.innerHTML = listHtml(doc, opts); return; }
      if (go) {
        e.preventDefault();
        if (ctx && ctx.doc === doc && String(ctx.ch) === go.dataset.ch) { flash(go.dataset.hlGo); if (opts.onGo) opts.onGo(); return; }
        try { sessionStorage.setItem('cl-hl-go', go.dataset.hlGo); } catch (er) { /* private mode */ }
        location.hash = go.getAttribute('href');
      }
    });
  }
  function flash(id) {
    const m = ctx && ctx.textEl.querySelector(`mark[data-hl="${id}"]`); if (!m) return say('That passage is no longer found in the text');
    m.scrollIntoView({ behavior: 'smooth', block: 'center' });
    ctx.textEl.querySelectorAll(`mark[data-hl="${id}"]`).forEach(x => { x.classList.remove('hl-flash'); void x.offsetWidth; x.classList.add('hl-flash'); });
  }
  function refreshLists() {
    if (!ctx) return;
    const n = loadHl(ctx.doc).length;
    document.querySelectorAll('[data-hl-count]').forEach(x => { x.textContent = n ? ` (${n})` : ''; });
    document.querySelectorAll('[data-hl-list]').forEach(x => { x.innerHTML = listHtml(ctx.doc, ctx); bindList(x, ctx.doc, ctx); });
  }

  /* ---------------------------------------------------------------- the notes pane */
  let pane = null, saveTmr = 0, edRange = null;
  const notesKey = doc => 'cl-notes:' + doc;
  function paneHtml() {
    return `<div class="np-grip" title="Drag to resize" aria-hidden="true"></div>
      <div class="np-head"><div class="np-tabs" role="tablist"><button role="tab" data-tab="notes">Notes</button><button role="tab" data-tab="hl">Highlights<span data-hl-count></span></button></div>
        <button class="np-close" title="Close the notes pane" aria-label="Close the notes pane">×</button></div>
      <div class="np-body" data-panel="notes">
        <div class="np-tools">
          <button data-cmd="bold" title="Bold (Ctrl+B)"><b>B</b></button><button data-cmd="italic" title="Italic (Ctrl+I)"><i>I</i></button>
          <button data-cmd="insertUnorderedList" title="Bulleted list">• List</button><button data-cmd="h3" title="Heading">H</button>
          <span class="np-sp"></span>
          <button data-act="quote" class="np-q" title="Insert the passage selected in the text, with a citation">❝ Insert quote</button>
        </div>
        <div class="np-ed" contenteditable="true" spellcheck="true" aria-label="Your notes" data-ph="Your notes on this book. Select a passage in the text and choose “Quote to notes” (or “Insert quote” above) to bring it in with a citation."></div>
        <div class="np-actions">
          <button class="btn btn-primary btn-sm" data-act="onenote-copy" title="Copies your notes as formatted text: paste into a OneNote page with Ctrl+V">Copy for OneNote</button>
          <button class="btn btn-ghost btn-sm" data-act="dl-md">.md</button><button class="btn btn-ghost btn-sm" data-act="dl-html">.html</button>
          <button class="btn btn-ghost btn-sm" data-act="onenote-open" title="Opens OneNote for the web in its own window beside this one">Open OneNote ↗</button>
          <button class="btn btn-ghost btn-sm np-clear" data-act="clear">Clear</button>
        </div>
        <p class="np-foot">Saved in this browser only<span class="np-saved"></span>. OneNote can’t be shown inside this page (Microsoft doesn’t allow it to be embedded), so copy your notes across or open it in a window alongside.</p>
      </div>
      <div class="np-body" data-panel="hl" hidden><div data-hl-list></div></div>`;
  }
  function setTab(tab) {
    if (!pane) return;
    localStorage.setItem('cl-notes-tab', tab);
    pane.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    pane.querySelectorAll('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== tab; });
  }
  function paneWidth() { return Math.max(280, Math.min(Math.round(innerWidth * 0.6), +(localStorage.getItem('cl-notes-w') || 400))); }
  function layoutPane() {
    if (!ctx || !pane) return;
    const open = !pane.hidden;
    const top = ctx.topFn ? ctx.topFn() : 0;
    pane.style.setProperty('--np-top', top + 'px');
    ctx.root.style.setProperty('--np-w', paneWidth() + 'px');
    ctx.root.classList.toggle('np-open', open);
    document.querySelectorAll('[data-np-toggle]').forEach(b => { b.setAttribute('aria-pressed', String(open)); b.classList.toggle('on', open); });
  }
  function openPane(open, tab) {
    if (!ctx) return;
    if (!pane) buildPane();
    pane.hidden = !open;
    localStorage.setItem('cl-notes-open:' + ctx.doc, open ? '1' : '');
    if (tab) setTab(tab);
    layoutPane();
  }
  function buildPane() {
    pane = document.createElement('aside');
    pane.className = 'np'; pane.hidden = true; pane.setAttribute('aria-label', 'Notes and highlights');
    pane.innerHTML = paneHtml();
    document.body.appendChild(pane);   // not inside the page: an animated (transformed) ancestor would break position: fixed
    const ed = pane.querySelector('.np-ed');
    ed.innerHTML = localStorage.getItem(notesKey(ctx.doc)) || '';
    const saved = pane.querySelector('.np-saved');
    const save = () => {
      clearTimeout(saveTmr);
      saveTmr = setTimeout(() => {
        const v = ed.innerText.trim() ? ed.innerHTML : '';
        try { v ? localStorage.setItem(notesKey(ctx.doc), v) : localStorage.removeItem(notesKey(ctx.doc)); saved.textContent = ' · saved ' + new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); }
        catch (e) { saved.textContent = ' · not saved: storage full'; }
      }, 350);
    };
    pane._save = save;
    ed.addEventListener('input', save);
    // paste as plain text: keeps the notes clean (and free of anything a web page's markup could carry)
    ed.addEventListener('paste', e => { e.preventDefault(); const t = (e.clipboardData || window.clipboardData).getData('text/plain'); document.execCommand('insertText', false, t); });
    ed.addEventListener('drop', e => e.preventDefault());
    const keep = () => { const s = getSelection(); if (s.rangeCount && ed.contains(s.getRangeAt(0).commonAncestorContainer)) edRange = s.getRangeAt(0).cloneRange(); };
    ed.addEventListener('keyup', keep); ed.addEventListener('mouseup', keep); ed.addEventListener('blur', keep);
    pane.addEventListener('mousedown', e => { if (e.target.closest('.np-tools button')) e.preventDefault(); });
    pane.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.classList.contains('np-close')) return openPane(false);
      if (b.dataset.tab) return setTab(b.dataset.tab);
      if (b.dataset.cmd) {
        ed.focus();
        if (b.dataset.cmd === 'h3') document.execCommand('formatBlock', false, document.queryCommandValue('formatBlock').toLowerCase() === 'h3' ? 'p' : 'h3');
        else document.execCommand(b.dataset.cmd);
        save(); return;
      }
      const act = b.dataset.act;
      if (act === 'quote') {
        const info = selectionInfo() || lastSel;
        if (!info) return say('Select a passage in the text first');
        return insertQuote(info.t, ctx.cite, ctx.href(ctx.ch));
      }
      if (act === 'onenote-copy') return copyRich(ed);
      if (act === 'dl-md') return download(slug(ctx.title) + '-notes.md', `# Notes: ${ctx.title}\n\n` + htmlToMd(ed), 'text/markdown');
      if (act === 'dl-html') return download(slug(ctx.title) + '-notes.html', notesDoc(ed), 'text/html');
      if (act === 'onenote-open') return openOneNote();
      if (act === 'clear') { if (ed.innerText.trim() && confirm('Clear all your notes for this book? This can’t be undone.')) { ed.innerHTML = ''; save(); } }
    });
    // drag the left edge to resize
    const grip = pane.querySelector('.np-grip');
    grip.addEventListener('pointerdown', e => {
      e.preventDefault(); grip.setPointerCapture(e.pointerId); document.body.classList.add('np-dragging');
      const move = ev => { const w = Math.max(280, Math.min(Math.round(innerWidth * 0.6), innerWidth - ev.clientX)); ctx.root.style.setProperty('--np-w', w + 'px'); localStorage.setItem('cl-notes-w', w); };
      const up = () => { grip.removeEventListener('pointermove', move); grip.removeEventListener('pointerup', up); document.body.classList.remove('np-dragging'); };
      grip.addEventListener('pointermove', move); grip.addEventListener('pointerup', up);
    });
    setTab(localStorage.getItem('cl-notes-tab') || 'notes');
    refreshLists();
  }
  function insertQuote(text, cite, hash) {
    if (!ctx) return;
    if (!pane || pane.hidden) openPane(true);
    setTab('notes');
    const ed = pane.querySelector('.np-ed');
    const html = `<blockquote>“${esc(text)}”</blockquote><p class="np-cite">— ${esc(cite)} (<a href="${esc(absUrl(hash))}">Lex Constitutio</a>)</p><p><br></p>`;
    ed.focus();
    const s = getSelection();
    if (edRange && ed.contains(edRange.commonAncestorContainer)) { s.removeAllRanges(); s.addRange(edRange); }
    else { const r = document.createRange(); r.selectNodeContents(ed); r.collapse(false); s.removeAllRanges(); s.addRange(r); }
    if (!document.execCommand('insertHTML', false, html)) ed.insertAdjacentHTML('beforeend', html);
    keepCaret(ed); pane._save(); say('Quote added to your notes');
  }
  function keepCaret(ed) { const s = getSelection(); if (s.rangeCount && ed.contains(s.getRangeAt(0).commonAncestorContainer)) edRange = s.getRangeAt(0).cloneRange(); }
  function notesDoc(ed) {
    return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Notes: ${esc(ctx.title)}</title>
<style>body{font:16px/1.6 Georgia,serif;max-width:720px;margin:40px auto;padding:0 20px}blockquote{margin:1em 0;padding:.2em 1em;border-left:3px solid #999;color:#333}.np-cite{font-size:.9em;color:#555}</style></head>
<body><h1>Notes: ${esc(ctx.title)}</h1>${ed.innerHTML}<p style="color:#777;font-size:.85em">Exported from Lex Constitutio, ${esc(new Date().toLocaleDateString())}.</p></body></html>`;
  }
  function copyRich(ed) {
    if (!ed.innerText.trim()) return say('Your notes are empty');
    const html = `<h1>Notes: ${esc(ctx.title)}</h1>${ed.innerHTML}`;
    const text = `Notes: ${ctx.title}\n\n${ed.innerText}`;
    if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
      navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
        .then(() => say('Copied: paste into OneNote with Ctrl+V'), () => legacyRich(html));
    } else legacyRich(html);
  }
  function legacyRich(html) {
    const d = document.createElement('div'); d.innerHTML = html; d.style.position = 'fixed'; d.style.left = '-9999px';
    document.body.appendChild(d);
    const r = document.createRange(); r.selectNodeContents(d); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    try { document.execCommand('copy'); say('Copied: paste into OneNote with Ctrl+V'); } catch (e) { say('Couldn’t copy'); }
    s.removeAllRanges(); d.remove();
  }
  function htmlToMd(root) {
    const walk = n => {
      if (n.nodeType === 3) return n.nodeValue.replace(/\s+/g, ' ');
      if (n.nodeType !== 1) return '';
      const inner = () => [...n.childNodes].map(walk).join('');
      switch (n.tagName) {
        case 'B': case 'STRONG': return `**${inner().trim()}**`;
        case 'I': case 'EM': return `*${inner().trim()}*`;
        case 'A': return `[${inner().trim()}](${n.getAttribute('href') || ''})`;
        case 'BR': return '\n';
        case 'H1': case 'H2': case 'H3': case 'H4': return `\n\n### ${inner().trim()}\n\n`;
        case 'BLOCKQUOTE': return '\n\n' + inner().trim().split('\n').map(l => '> ' + l).join('\n') + '\n\n';
        case 'LI': return `\n- ${inner().trim()}`;
        case 'UL': case 'OL': return '\n' + inner() + '\n\n';
        case 'P': case 'DIV': return '\n\n' + inner().trim() + '\n\n';
        default: return inner();
      }
    };
    return walk(root).replace(/\n{3,}/g, '\n\n').trim() + '\n';
  }
  function openOneNote() {
    const sw = screen.availWidth || innerWidth, sh = screen.availHeight || innerHeight;
    const w = Math.round(sw / 2), left = (screen.availLeft || 0) + sw - w, top = screen.availTop || 0;
    const win = window.open('https://www.onenote.com/notebooks', 'lc-onenote', `popup=yes,width=${w},height=${sh},left=${left},top=${top}`);
    if (!win) return say('Your browser blocked the window: allow pop-ups for this site, or open onenote.com yourself');
    say('OneNote opened in its own window: snap this one to the left (Windows key + ←)');
  }

  /* ---------------------------------------------------------------- mounting */
  function mount(o) {
    // o: {doc, ch, chLabel, cite, title, author, href(ch) -> hash, textEl, root, toolsEl, topFn, drawerList}
    if (pane) pane.remove();
    ctx = o; lastSel = null; pane = null; edRange = null; hidePop();
    o.toolsEl.insertAdjacentHTML('afterbegin', `<button class="btn btn-ghost btn-sm" data-np-toggle aria-pressed="false" title="Notes and highlights side by side with the text">Notes</button>`);
    o.toolsEl.querySelector('[data-np-toggle]').addEventListener('click', () => openPane(!pane || pane.hidden));
    applyAll();
    o.textEl.addEventListener('click', e => {
      const m = e.target.closest('mark.hl');
      if (!m || !getSelection().isCollapsed) return;
      showMarkPop(m.dataset.hl, m.getBoundingClientRect());
    });
    if (localStorage.getItem('cl-notes-open:' + o.doc) === '1' && innerWidth >= 900) openPane(true);
    refreshLists();
    const root = o.root;
    const onResize = () => { if (!document.body.contains(root)) return removeEventListener('resize', onResize); layoutPane(); };
    addEventListener('resize', onResize);
    // a highlight picked from a list on another page
    let go = null; try { go = sessionStorage.getItem('cl-hl-go'); sessionStorage.removeItem('cl-hl-go'); } catch (e) { /* private mode */ }
    if (go) setTimeout(() => flash(go), 120);
    return { hasJump: !!go };
  }
  window.LexAnnot = {
    mount,
    count: doc => loadHl(doc).length,
    listHtml: (doc, opts) => listHtml(doc, opts),
    bindList,
    hasNotes: doc => !!localStorage.getItem(notesKey(doc)),
  };
})();
