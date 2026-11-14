/* Lex Constitutio: justice ratings, per-justice vote models and the Statistics tab.
   Loaded on demand by app.js (window.LC_API bridge). Data: data/ratings.js (build_ratings.py), data/models.js
   (build_models.py), data/stats.js and data/stcases-<decade>.js (build_stats.py), all from the Supreme Court Database. */
(function () {
  'use strict';
  const A = window.LC_API;
  const { esc, fmt, hashFor } = A;
  const pct = (x, d = 1) => x == null ? '—' : (+x).toFixed(d) + '%';
  const signed = (x, d = 1) => x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '±') + Math.abs(x).toFixed(d);
  const DIR = { L: 'Liberal', C: 'Conservative', U: 'Unspecifiable' };
  const SCDB = '<a href="http://scdb.wustl.edu/" target="_blank" rel="noopener">Supreme Court Database</a>';

  /* ---------------------------------------------------------------- small chart helpers */
  // Dot strip: every eligible justice as a dot along one axis; `hi` highlighted, `ring` outlined. Hover names each dot.
  function strip(items, hi, ring, leftLabel, rightLabel, fmtV) {
    const W = 640, H = 64, pad = 14;
    const vs = items.map(d => d.v), lo = Math.min(...vs), up = Math.max(...vs);
    const x = v => pad + (W - 2 * pad) * (v - lo) / ((up - lo) || 1);
    const sorted = items.slice().sort((a, b) => (a.id === hi) - (b.id === hi) || ring.has(a.id) - ring.has(b.id));
    return `<svg class="st-strip" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(leftLabel)} to ${esc(rightLabel)}">
      <line x1="${pad}" x2="${W - pad}" y1="30" y2="30" class="st-axis"/>
      ${sorted.map(d => `<g class="${d.id === hi ? 'hi' : ring.has(d.id) ? 'ring' : ''}"><circle cx="${x(d.v).toFixed(1)}" cy="30" r="${d.id === hi ? 7 : ring.has(d.id) ? 5 : 4}"/><circle class="hit" cx="${x(d.v).toFixed(1)}" cy="30" r="9"><title>${esc(d.name)}: ${esc(fmtV(d.v))}</title></circle></g>`).join('')}
      <text x="${pad}" y="58" class="st-lab">${esc(leftLabel)}</text><text x="${W - pad}" y="58" class="st-lab" text-anchor="end">${esc(rightLabel)}</text>
    </svg>`;
  }
  // One-series line chart over terms, optional band [lo, hi]; points carry hover titles.
  function line(points, opt) {
    const W = 640, H = opt.h || 150, L = 40, R = 10, T = 10, B = 24;
    const pts = points.filter(p => p[1] != null);
    if (pts.length < 2) return '<p class="muted-line">Too few terms to chart.</p>';
    const xs = pts.map(p => p[0]), x0 = Math.min(...xs), x1 = Math.max(...xs);
    const ys = pts.flatMap(p => p[2] != null ? [p[1], p[2], p[3]] : [p[1]]);
    const y0 = opt.yMin ?? Math.min(...ys), y1 = opt.yMax ?? Math.max(...ys);
    const X = v => L + (W - L - R) * (v - x0) / ((x1 - x0) || 1), Y = v => T + (H - T - B) * (1 - (v - y0) / ((y1 - y0) || 1));
    const ticks = opt.yTicks || [y0, (y0 + y1) / 2, y1];
    const xt = []; const step = Math.max(1, Math.ceil((x1 - x0) / 6 / 5) * 5); for (let v = Math.ceil(x0 / step) * step; v <= x1; v += step) xt.push(v);
    const band = pts[0][2] != null ? `<path class="st-band" d="M${pts.map(p => X(p[0]).toFixed(1) + ',' + Y(p[2]).toFixed(1)).join('L')}L${pts.slice().reverse().map(p => X(p[0]).toFixed(1) + ',' + Y(p[3]).toFixed(1)).join('L')}Z"/>` : '';
    const ref = opt.ref != null ? `<line class="st-ref" x1="${L}" x2="${W - R}" y1="${Y(opt.ref)}" y2="${Y(opt.ref)}"/>` : '';
    return `<svg class="st-line" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.label || '')}">
      ${ticks.map(t => `<line class="st-grid" x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}"/><text class="st-lab" x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${esc(opt.fmtY ? opt.fmtY(t) : t)}</text>`).join('')}
      ${xt.map(t => `<text class="st-lab" x="${X(t)}" y="${H - 6}" text-anchor="middle">${t}</text>`).join('')}
      ${ref}${band}<path class="st-path" d="M${pts.map(p => X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('L')}"/>
      ${pts.map(p => `<circle class="st-pt" cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="2.5"/><rect class="hit" x="${(X(p[0]) - (W - L - R) / pts.length / 2).toFixed(1)}" y="${T}" width="${Math.max(3, (W - L - R) / pts.length).toFixed(1)}" height="${H - T - B}"><title>${esc((opt.fmtX ? opt.fmtX(p[0]) : p[0]) + ': ' + (opt.fmtTip ? opt.fmtTip(p) : p[1]))}</title></rect>`).join('')}
    </svg>`;
  }
  // Horizontal bars with direct labels; rows: [label, value, note, cls, whisker [lo, hi]]
  function bars(rows, max, fmtV) {
    return `<div class="st-bars">${rows.map(([lab, v, note, cls, ci]) => `<div class="st-bar ${cls || ''}" title="${esc(lab + ': ' + fmtV(v) + (note ? ' — ' + note : ''))}">
      <span class="lab">${esc(lab)}</span><span class="track"><i style="width:${Math.max(0.5, 100 * v / max).toFixed(1)}%"></i>${ci ? `<b class="ci" style="left:${(100 * ci[0] / max).toFixed(1)}%;width:${(100 * (ci[1] - ci[0]) / max).toFixed(1)}%"></b>` : ''}</span><span class="val">${esc(fmtV(v))}</span></div>`).join('')}</div>`;
  }

  /* ---------------------------------------------------------------- justice profile: ratings + model */
  function justiceRatings(el, j, J, R, M) {
    const r = R.j[j.id];
    if (!r) { el.innerHTML = ''; return; }
    const sitting = new Set(J.justices.filter(x => !x.roles[x.roles.length - 1].end).map(x => x.id));
    const nameOf = Object.fromEntries(J.justices.map(x => [x.id, x.name]));
    const elig = Object.entries(R.j).filter(([, x]) => x.elig);
    const small = !r.elig ? `<p class="st-warn">${esc(j.name)} cast ${fmt(r.n)} votes in the database, fewer than the ${R.minVotes} needed to be ranked, so the scores below are shown without a ranking and are unreliable.</p>` : '';
    // ideology
    const libItems = elig.filter(([, x]) => x.libRel != null).map(([id, x]) => ({ id, name: nameOf[id], v: -x.libRel }));
    const mqItems = Object.entries(R.j).filter(([, x]) => x.mq != null).map(([id, x]) => ({ id, name: nameOf[id], v: x.mq }));
    const ideo = `<div class="panel st-panel"><h4>Liberal–conservative score</h4>${small}
      <div class="st-kpis">
        <div><b>${pct(r.lib)}</b><span>of ${fmt(r.nDir)} votes cast in the liberal direction</span></div>
        <div><b>${Math.abs(r.libRel).toFixed(1)}</b><span>points ${r.libRel >= 0 ? 'more liberal' : 'more conservative'} than the colleagues in the same cases${r.libRank ? ` · ${ordinal(r.libRank)} most liberal of ${R.nElig}` : ''}</span></div>
        ${r.mq != null ? `<div><b>${r.mq.toFixed(2)}</b><span>career mean Martin–Quinn score (negative = liberal) · ${ordinal(r.mqRank)} most liberal of ${R.nMq}</span></div>` : ''}
      </div>
      ${r.elig ? `<div class="st-sub">Every justice with ${R.minVotes}+ votes, by liberal votes relative to colleagues · <span class="st-key"><i class="k-hi"></i>${esc(j.last || j.name)}</span> <span class="st-key"><i class="k-ring"></i>current Court</span></div>${strip(libItems, j.id, sitting, '← more liberal than colleagues', 'more conservative than colleagues →', v => signed(-v) + ' pts liberal vs. colleagues')}` : ''}
      ${r.mqTerms ? `<div class="st-sub">Martin–Quinn score by term, with 95% interval (negative = liberal)</div>${line(r.mqTerms.map(t => [t[0], t[1], t[2], t[3]]), { ref: 0, label: 'Martin–Quinn score by term', fmtY: v => v.toFixed(1), fmtTip: p => p[1].toFixed(2) + ' (95% interval ' + p[2].toFixed(2) + ' to ' + p[3].toFixed(2) + ')' })}
        <div class="st-sub">All justices with Martin–Quinn scores, by career mean</div>${strip(mqItems, j.id, sitting, '← liberal', 'conservative →', v => v.toFixed(2))}` : ''}
      ${r.terms.length > 1 ? `<div class="st-sub">Share of votes in the liberal direction, by term (SCDB)</div>${line(r.terms.map(t => [t[0], t[1]]), { yMin: 0, yMax: 100, yTicks: [0, 50, 100], ref: 50, label: 'Liberal votes by term', fmtY: v => v + '%', fmtTip: p => pct(p[1]) })}` : ''}
    </div>`;
    // institutionalism
    const comp = [
      ['Voted with the majority', r.majRate, r.maj, 'higher', `${fmt(r.n)} votes`],
      ['Wrote a separate opinion (concurrence or dissent)', r.sepRate, r.sep, 'lower', `${fmt(r.n)} votes`],
      ['Concurred only in the judgment', r.specRate, r.spec, 'lower', `${fmt(r.n)} votes`],
      ['Joined decisions that overruled precedent', r.overrRate, r.overr, 'lower', `${fmt(r.nOverr)} such decisions`],
      ['Joined decisions striking down a law', r.strikeRate, r.strike, 'lower', `${fmt(r.nStrike)} such decisions (${fmt(r.nStrikeFed)} federal)`]
    ];
    const instItems = elig.map(([id, x]) => ({ id, name: nameOf[id], v: x.instRaw }));
    const inst = `<div class="panel st-panel"><h4>Institutionalism score</h4>${small}
      <div class="st-kpis"><div><b>${r.inst != null ? Math.round(r.inst) : '—'}</b><span>percentile among the ${R.nElig} justices with ${R.minVotes}+ votes${r.instRank ? ` · ranked ${ordinal(r.instRank)}` : ''} (100 = most institutionalist)</span></div></div>
      ${r.elig ? strip(instItems, j.id, sitting, '← less institutionalist', 'more institutionalist →', v => 'index ' + v.toFixed(2)) : ''}
      <table class="st-table"><thead><tr><th>Component</th><th>Rate</th><th>vs. colleagues</th><th>More institutional if</th></tr></thead><tbody>
        ${comp.map(([lab, rate, rel, dir, n]) => `<tr><td>${esc(lab)}<div class="m">${esc(n)}</div></td><td>${pct(rate)}</td><td>${signed(rel)} pts</td><td>${dir}</td></tr>`).join('')}
      </tbody></table>
    </div>`;
    const method = `<details class="st-method"><summary>How these scores are computed</summary>
      <p><b>Data.</b> Every vote in the ${SCDB} (Spaeth et al., 2026 Release 01 and Legacy Release 07, 1791–2025) in cases decided with an opinion. Martin–Quinn scores: <a href="${esc(R.mqUrl)}" target="_blank" rel="noopener">${esc(R.mqSrc)}</a>; the latest public release ends with the 2021 Term, so later terms have none.</p>
      <p><b>Liberal–conservative.</b> SCDB codes each vote liberal or conservative by issue (for example, pro-defendant in criminal cases is liberal; pro-business in economic cases is conservative). The score is the share of liberal votes. Because the cases the Court takes change over time, the comparison that counts is against the colleagues who sat in the same cases: for each vote, the justice's vote minus the share of liberal votes among the others, averaged.</p>
      <p><b>Institutionalism.</b> Five measurable behaviors, each also measured against the colleagues in the same cases: voting with the majority; not writing separately; not concurring only in the judgment; not joining decisions that formally overrule precedent (SCDB <code>precedentAlteration</code>); and not joining decisions that declare a federal, state or local law unconstitutional (<code>declarationUncon</code>). The two last components count only decisions where the Court did overrule or strike down, so a vote to overrule or invalidate in dissent is not captured; they are shrunk toward zero when there are few such decisions (difference ÷ (decisions + ${R.shrink})). Each component is converted to a z-score across justices, signed so that higher is more institutional, and averaged; the result is shown as a percentile. SCDB has no variable for whether a ruling is narrow or broad, so that dimension is left out. The components are not independent of ideology: in a Court with a stable majority, members of the minority dissent more and join fewer overrulings.</p>
      <p class="attrib">Computed by <code>scripts/build_ratings.py</code>; the scores are this site's calculations from the data, not ratings published by the database's authors.</p>
    </details>`;
    el.innerHTML = `<h2 class="section-h">Ratings</h2><div class="st-two">${ideo}${inst}</div>${method}${M && M.j[j.id] ? modelPanel(M, M.j[j.id], j) : ''}`;
  }
  const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');

  function modelPanel(M, m, j) {
    const b = m.base;
    const accRows = [
      ['Model: all pre-decision predictors', m.full.acc * 100, m.full.model, 'hi', m.full.ci.map(x => x * 100)],
      ['Model: docket predictors only', m.docket.acc * 100, m.docket.model, 'mid', m.docket.ci.map(x => x * 100)],
      [`Baseline: always the more common vote in training (${b.majorityLabel})`, b.majority * 100, '', 'base'],
      ['Baseline: always for the petitioner (reverse)', b.reverse * 100, '', 'base'],
      ['Baseline: best constant guess, picked with hindsight', b.hindsight * 100, '', 'base']
    ];
    const weak = m.verdict !== 'beats every baseline';
    const caseOf = Object.fromEntries(M.cases.map(c => [c.id, c]));
    const preds = m.pred.map(([id, p]) => ({ c: caseOf[id], p })).filter(x => x.c).sort((a, b) => Math.abs(b.p - 0.5) - Math.abs(a.p - 0.5));
    const imp = m.full.imp.filter(r => r[1] > 0).slice(0, 6), impD = m.docket.imp.filter(r => r[1] > 0).slice(0, 5);
    const impMax = Math.max(0.5, ...imp.map(r => r[1]), ...impD.map(r => r[1]));
    return `<div class="panel st-panel st-model"><h4>Vote prediction model</h4>
      <p class="st-lead">Predicts whether ${esc(j.last || j.name)} votes for the petitioner (to reverse or vacate) or for the respondent (to affirm). Trained on ${fmt(m.nTrain)} votes (${esc(m.trainSpan[0])} to ${esc(m.trainSpan[1])}) and tested on the ${fmt(m.nTest)} most recent (${esc(m.testSpan[0])} to ${esc(m.testSpan[1])}), which the model never saw.</p>
      <p class="st-verdict ${weak ? 'weak' : ''}"><b>Result.</b> Full model: ${esc(m.verdict)} (${pct(m.full.acc * 100)} vs. ${pct(Math.max(b.majority, b.reverse, b.hindsight) * 100)} for the best baseline). Docket-only model: ${esc(m.dverdict)} (${pct(m.docket.acc * 100)}).${m.dverdict !== 'beats every baseline' ? ' The pending-case predictions below come from the docket-only model, so treat them as weak.' : ''}</p>
      <div class="st-sub">Test-set accuracy (bars show the 95% interval for the models)</div>
      ${bars(accRows, 100, v => pct(v))}
      <div class="st-two st-two-tight">
        <div><div class="st-sub">Most important predictors, full model <span class="muted-line">(accuracy lost when shuffled, pts)</span></div>${imp.length ? bars(imp.map(r => [r[0], r[1], '', 'imp']), impMax, v => v.toFixed(1)) : '<p class="muted-line">No predictor improved test accuracy.</p>'}</div>
        <div><div class="st-sub">Docket model</div>${impD.length ? bars(impD.map(r => [r[0], r[1], '', 'imp']), impMax, v => v.toFixed(1)) : '<p class="muted-line">No predictor improved test accuracy.</p>'}</div>
      </div>
      <div class="st-sub">Predicted votes in pending cases <span class="muted-line">(docket model, refitted on all ${fmt(m.n)} votes)</span></div>
      ${preds.length ? `<ul class="st-preds">${preds.map(({ c, p }) => `<li><a href="#/case/${esc(c.id)}">${esc(c.n)}</a><span class="muted-line">${esc(c.src)}${c.area ? ' · ' + esc(c.area) : ''}</span><span class="st-pill ${p >= 0.5 ? 'rev' : 'aff'}" title="Predicted probability of voting for the petitioner: ${pct(p * 100, 0)}">${p >= 0.5 ? 'Reverse' : 'Affirm'} · ${pct((p >= 0.5 ? p : 1 - p) * 100, 0)}</span></li>`).join('')}</ul>` : '<p class="muted-line">No pending cases.</p>'}
      <details class="st-method"><summary>About the model</summary>
        <p>One model per justice, chosen by five-fold cross-validation on the training votes only (logistic regression at four penalty strengths, or gradient-boosted trees; this justice: <i>${esc(m.full.model)}</i> for the full model, <i>${esc(m.docket.model)}</i> for the docket model). Predictors are SCDB variables fixed before the decision: issue area and issue, law type, source and origin court, lower-court disposition and its ideological direction, the reason cert was granted, jurisdiction, petitioner and respondent type, agency involvement, three-judge court, a dissent below, and the term. A vote for the petitioner is a majority vote when the petitioner won, or a dissent when the petitioner lost.</p>
        <p>Pending cases have no SCDB coding yet, so the docket model uses only what can be read from the case: the lower court and the counsel for each side (Solicitor General, a state attorney general's office, a local government) from the supremecourt.gov docket page, and the issue area predicted from the question presented by a text classifier trained on decided cases (${pct(M.issueClf.acc * 100)} accurate on ${fmt(M.issueClf.nTest)} held-out cases, vs. ${pct(M.issueClf.base * 100)} for always guessing the commonest area). Probabilities near 50% mean the model has little to go on. Because the Court reverses most of the cases it hears, a model that has learned little predicts “reverse” almost everywhere.</p>
        <p>A model is said to beat the baselines only if it is at least 2 points more accurate than the best of them and the lower end of its 95% interval is also above it; with a small test set (a newer justice) even a large gap can fall inside the margin of error.</p>
        <p class="attrib">Computed by <code>scripts/build_models.py</code> on ${esc(M.generated)}. These are statistical predictions from past voting patterns, not forecasts by any expert.</p>
      </details>
    </div>`;
  }

  /* ---------------------------------------------------------------- Statistics tab */
  function viewStats(params) { A.withData([['stats', 'STATS']], S => renderStats(S, params)); }
  function renderStats(S, params) {
    const terms = S.terms;
    const t = +params.get('t') || terms[terms.length - 1].t;
    const T = terms.find(x => x.t === t) || terms[terms.length - 1];
    const R = T.roster, nm = i => R[i] ? R[i][1] : '?';
    const jlink = i => R[i] && R[i][2] ? `<a href="#/justice/${esc(R[i][2])}">${esc(R[i][1])}</a>` : esc(nm(i));
    const chiefTerms = terms.filter(x => x.chief === T.chief);
    const cnt = (n, d) => d ? `${fmt(n)} <span class="muted-line">(${(100 * n / d).toFixed(1)}%)</span>` : fmt(n);
    // I(A) + I(D)
    const tA = `<table class="st-table st-num"><thead><tr><th>Justice</th><th>Opinions of the Court</th><th>Concurrences</th><th>Dissents</th><th>Total written</th><th>Dissenting votes</th><th>Nonunanimous cases</th><th>Joined the Court's opinion</th><th>With the majority</th></tr></thead><tbody>
      ${T.A.map(a => `<tr><td>${jlink(a[0])}</td><td>${a[1]}</td><td>${a[2]}</td><td>${a[3]}</td><td><b>${a[1] + a[2] + a[3]}</b></td><td>${a[4]}</td><td>${a[6]}</td><td>${cnt(a[7], a[6])}</td><td>${cnt(a[8], a[6])}</td></tr>`).join('')}
      ${T.pc ? `<tr><td>Per curiam</td><td>${T.pc}</td><td colspan="7"></td></tr>` : ''}
    </tbody></table>`;
    const matrix = (B, cap) => {
      const vals = B.flat().filter(Boolean).filter(c => c[1]).map(c => 100 * c[0] / c[1]);
      const lo = Math.min(...vals, 100);
      return `<div class="st-scroll"><table class="st-matrix"><caption>${cap}</caption><thead><tr><th></th>${R.map((r, i) => `<th>${esc(nm(i))}</th>`).join('')}</tr></thead><tbody>
        ${R.map((r, i) => `<tr><th>${jlink(i)}</th>${R.map((s, k) => { const c = B[i][k]; if (i === k || !c) return '<td class="self">—</td>'; if (!c[1]) return '<td></td>'; const p = 100 * c[0] / c[1]; const a = (p - lo) / ((100 - lo) || 1); return `<td style="--a:${(0.08 + 0.72 * a).toFixed(2)}" title="${esc(nm(i))} and ${esc(nm(k))}: same side in ${c[0]} of ${c[1]} cases">${Math.round(p)}</td>`; }).join('')}</tr>`).join('')}
      </tbody></table></div>`;
    };
    const splitOrder = Object.entries(T.splits).sort((a, b) => (+a[0].split('-')[1]) - (+b[0].split('-')[1]) || (+b[0].split('-')[0]) - (+a[0].split('-')[0]));
    const coalRows = (rows) => rows.length ? `<table class="st-table"><thead><tr><th>Justices in the majority</th><th>Decisions</th></tr></thead><tbody>${rows.map(([m, n]) => `<tr><td>${m.map(i => esc(nm(i))).join(', ')}</td><td>${n}</td></tr>`).join('')}</tbody></table>` : '<p class="muted-line">None this Term.</p>';
    const dispTable = (disp, label) => {
      const order = ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth', 'Eleventh', 'D.C.', 'Federal'].map(x => x + ' Circuit').concat(['District courts', 'Old circuit courts', 'Armed Forces', 'State courts', 'Other federal or territorial', 'Other or none']);
      const rows = order.filter(k => disp[k]).map(k => [k, disp[k]]);
      const tot = [0, 1, 2, 3].map(i => rows.reduce((s, r) => s + r[1][i], 0));
      const row = (k, v, cls) => { const n = v[0] + v[1] + v[2] + v[3]; return `<tr class="${cls || ''}"><td>${esc(k)}</td><td>${v[0]}</td><td>${v[1]}</td><td>${v[2]}</td><td>${v[3]}</td><td>${n}</td><td>${n ? pct(100 * (v[0] + v[1]) / n) : '—'}</td></tr>`; };
      return rows.length ? `<table class="st-table st-num"><thead><tr><th>${label}</th><th>Reversed</th><th>Vacated</th><th>Affirmed</th><th>Other</th><th>Total</th><th>Reversed or vacated</th></tr></thead><tbody>${rows.map(r => row(r[0], r[1])).join('')}${row('Total', tot, 'tot')}</tbody></table>` : '<p class="muted-line">No cases on certiorari in the database for this Term.</p>';
    };
    const sumDisp = list => { const o = {}; for (const x of list) for (const [k, v] of Object.entries(x.disp)) { o[k] = o[k] || [0, 0, 0, 0]; v.forEach((n, i) => o[k][i] += n); } return o; };
    const subjRows = Object.entries(T.subj).sort((a, b) => (b[1][0] + b[1][1] + b[1][2]) - (a[1][0] + a[1][1] + a[1][2]));
    const I = T.inst;
    const series = S.series;
    app().innerHTML = `<div class="fade-in">
      <div class="page-head"><div class="crumbs"><a href="#/">Home</a><span>/</span><a href="#/scotus">Supreme Court</a><span>/</span><span>Statistics</span></div>
        <h1>The Statistics</h1><p>Term-by-term tables in the style of the <i>Harvard Law Review</i>'s annual “The Statistics” (for example, 139 Harv. L. Rev. 430 (2025)), computed from the ${SCDB} for every Term from 1791 to 2025, with each case classed by ideological direction and by an institutionalism index.</p>
        ${A.scotusTabs('stats')}</div>
      <div class="wrap" style="padding-bottom:48px">
        <form class="st-pick" id="st-pick"><label>Term <select id="st-term">${terms.slice().reverse().map(x => `<option value="${x.t}" ${x.t === T.t ? 'selected' : ''}>October Term ${x.t}${x.t >= 1791 ? '' : ''}</option>`).join('')}</select></label>
          <span class="muted-line">${esc(T.chief)} Court · ${fmt(T.n)} cases decided with an opinion after oral argument</span>
          <a class="btn btn-ghost btn-sm" href="${hashFor('stats', { t: Math.max(terms[0].t, T.t - 1) })}">← Earlier</a><a class="btn btn-ghost btn-sm" href="${hashFor('stats', { t: Math.min(terms[terms.length - 1].t, T.t + 1) })}">Later →</a></form>

        <div class="st-kpis st-kpis-wide">
          <div><b>${fmt(T.n)}</b><span>cases</span></div>
          <div><b>${pct(100 * T.C[0] / T.n)}</b><span>unanimous</span></div>
          <div><b>${T.splits['5-4'] || 0}</b><span>5–4 decisions</span></div>
          <div><b>${pct(100 * T.dir[0] / Math.max(1, T.dir[0] + T.dir[1]))}</b><span>liberal outcomes</span></div>
          <div><b>${I.overr}</b><span>overruled precedent</span></div>
          <div><b>${I.fed + I.state + I.local}</b><span>laws struck down</span></div>
        </div>

        <h2 class="section-h">I(A) Actions of individual justices · I(D) Nonunanimous cases</h2>${tA}
        <p class="st-note">Opinions written and dissenting votes in the ${T.n} cases. SCDB records at most one opinion per justice per case. “Joined the Court's opinion” counts votes with the majority or plurality opinion, including regular concurrences; “with the majority” also counts concurrences in the judgment only.</p>

        <h2 class="section-h">I(B) Voting alignments</h2>
        <div class="st-two">${matrix(T.Ball, 'All cases: % of shared cases on the same side')}${matrix(T.Bnon, 'Nonunanimous cases')}</div>
        <p class="st-note">Agreement here means voting on the same side of the disposition (both in the majority or both in dissent). The <i>Harvard Law Review</i> counts agreement as joining the same opinion, so its percentages run lower. Darker cells mean more agreement within this Term.</p>

        <div class="st-two">
          <div><h2 class="section-h">I(C) Unanimity</h2><table class="st-table st-num"><thead><tr><th></th><th>Cases</th></tr></thead><tbody>
            <tr><td>Unanimous</td><td>${cnt(T.C[0], T.n)}</td></tr><tr><td>Unanimous, with a concurrence in the judgment</td><td>${cnt(T.C[1], T.n)}</td></tr><tr><td>With a dissent</td><td>${cnt(T.C[2], T.n)}</td></tr></tbody></table>
            <h2 class="section-h">Vote splits</h2><table class="st-table st-num"><thead><tr><th>Split</th><th>Cases</th></tr></thead><tbody>${splitOrder.map(([k, n]) => `<tr><td>${esc(k.replace('-', '–'))}</td><td>${cnt(n, T.n)}</td></tr>`).join('')}</tbody></table></div>
          <div><h2 class="section-h">I(E) 5–4 decisions</h2>${coalRows(T.five4)}
            <h2 class="section-h">Most frequent majorities in divided cases</h2>${coalRows(T.coal)}</div>
        </div>

        <h2 class="section-h">II(D–E) Cases on certiorari by lower court</h2>
        <div class="st-two">${dispTable(T.disp, 'October Term ' + T.t)}${dispTable(sumDisp(chiefTerms), `${T.chief} Court, ${chiefTerms[0].t}–${chiefTerms[chiefTerms.length - 1].t}`)}</div>
        <p class="st-note">SCDB <code>caseDisposition</code>: reversed includes reversed in part; vacated includes vacated and remanded. Only cases reaching the Court on a writ of certiorari.</p>

        <h2 class="section-h">III Subject matter and direction</h2>
        <table class="st-table st-num"><thead><tr><th>Issue area</th><th>Cases</th><th>Liberal</th><th>Conservative</th><th>Unspecifiable</th></tr></thead><tbody>
          ${subjRows.map(([a, v]) => `<tr><td>${esc(S.areas[a] || 'Not coded')}</td><td>${v[0] + v[1] + v[2]}</td><td>${v[0]}</td><td>${v[1]}</td><td>${v[2]}</td></tr>`).join('')}
          <tr class="tot"><td>Total</td><td>${T.n}</td><td>${T.dir[0]}</td><td>${T.dir[1]}</td><td>${T.dir[2]}</td></tr></tbody></table>

        <h2 class="section-h">Institutionalism of the Term's decisions</h2>
        <div class="st-two"><div>
          <table class="st-table st-num"><thead><tr><th>Index (0–3)</th><th>Cases</th></tr></thead><tbody>${[3, 2, 1, 0].map(v => `<tr><td>${v}${v === 3 ? ' (no overruling, no law struck down, no dissent)' : v === 0 ? ' (overruled, struck down and divided)' : ''}</td><td>${cnt(I.idx[v], T.n)}</td></tr>`).join('')}</tbody></table></div>
          <div><table class="st-table st-num"><thead><tr><th></th><th>Cases</th></tr></thead><tbody>
            <tr><td>Formally altered precedent</td><td>${I.overr}</td></tr><tr><td>Declared an act of Congress unconstitutional</td><td>${I.fed}</td></tr><tr><td>Declared a state law unconstitutional</td><td>${I.state}</td></tr><tr><td>Declared a local ordinance unconstitutional</td><td>${I.local}</td></tr></tbody></table></div></div>
        <p class="st-note">One point each for not altering precedent (SCDB <code>precedentAlteration</code>), not declaring a law unconstitutional (<code>declarationUncon</code>) and deciding without a dissent.</p>

        <h2 class="section-h">Every case this Term</h2>
        <div class="st-filters" id="st-filters"><div class="seg" role="group" aria-label="Direction"><button data-dir="" class="on">All</button><button data-dir="L">Liberal</button><button data-dir="C">Conservative</button><button data-dir="U">Unspecifiable</button></div>
          <div class="seg" role="group" aria-label="Institutionalism"><button data-inst="" class="on">Any index</button><button data-inst="3">3</button><button data-inst="2">2</button><button data-inst="1">1</button><button data-inst="0">0</button></div></div>
        <div id="st-cases"><p class="muted-line"><span class="spinner sm"></span> Loading cases…</p></div>

        <h2 class="section-h">Across the Terms</h2>
        <div class="st-two">
          <div><div class="st-sub">Unanimous decisions (% of cases)</div>${line(series.map(s => [s[0], s[2]]), { yMin: 0, yMax: 100, yTicks: [0, 50, 100], label: 'Unanimity by term', fmtY: v => v + '%', fmtTip: p => pct(p[1]) })}</div>
          <div><div class="st-sub">Liberal outcomes (% of cases with a direction)</div>${line(series.map(s => [s[0], s[4]]), { yMin: 0, yMax: 100, yTicks: [0, 50, 100], ref: 50, label: 'Liberal outcomes by term', fmtY: v => v + '%', fmtTip: p => pct(p[1]) })}</div>
          <div><div class="st-sub">5–4 decisions (count)</div>${line(series.map(s => [s[0], s[3]]), { yMin: 0, label: '5–4 decisions by term', fmtY: v => Math.round(v), fmtTip: p => p[1] + ' decisions' })}</div>
          <div><div class="st-sub">Cert cases reversed or vacated (%)</div>${line(series.map(s => [s[0], s[5]]), { yMin: 0, yMax: 100, yTicks: [0, 50, 100], label: 'Reversal rate by term', fmtY: v => v + '%', fmtTip: p => pct(p[1]) })}</div>
        </div>
        <p class="attrib">All figures computed by <code>scripts/build_stats.py</code> from the Supreme Court Database (Spaeth et al.), cases with SCDB decision types 1, 6 and 7 (decided with an opinion after oral argument). Format after <i>The Supreme Court, 2024 Term — The Statistics</i>, 139 Harv. L. Rev. 430 (2025); the numbers are this site's and will differ from the Review's, which are compiled from the opinions by hand.</p>
      </div></div>`;
    document.getElementById('st-term').addEventListener('change', e => { location.hash = hashFor('stats', { t: e.target.value }); });
    const dec = Math.floor(T.t / 10) * 10;
    const st = { dir: '', inst: '' };
    const box = document.getElementById('st-cases');
    A.loadData(`stcases-${dec}`, `STCASES_${dec}`).then(rows => {
      const mine = rows.filter(r => r[0] === T.t);
      const draw = () => {
        const list = mine.filter(r => (!st.dir || r[7] === st.dir) && (st.inst === '' || r[8] === +st.inst));
        box.innerHTML = list.length ? `<div class="st-scroll"><table class="st-table st-cases"><thead><tr><th>Case</th><th>Decided</th><th>Vote</th><th>Area</th><th>Direction</th><th>Index</th></tr></thead><tbody>
          ${list.map(r => `<tr><td>${r[1] ? `<a href="#/case/${esc(r[1])}">${esc(r[2])}</a>` : esc(r[2])}<div class="m">${esc(r[3])}${r[9] ? ' · <b>altered precedent</b>' : ''}${r[10] ? ' · <b>struck down ' + ['', '', 'federal', 'state', 'local'][r[10]] + ' law</b>' : ''}</div></td><td>${esc(r[4])}</td><td>${r[5] != null ? r[5] + '–' + r[6] : '—'}</td><td>${esc(S.areas[r[11]] || '')}</td><td><span class="st-dir d-${r[7]}">${DIR[r[7]]}</span></td><td>${r[8]}</td></tr>`).join('')}
        </tbody></table></div><p class="muted-line">${list.length} of ${mine.length} cases.</p>` : '<p class="muted-line">No cases match.</p>';
      };
      document.getElementById('st-filters').addEventListener('click', e => {
        const b = e.target.closest('button'); if (!b) return;
        const k = 'dir' in b.dataset ? 'dir' : 'inst';
        st[k] = b.dataset[k];
        b.parentNode.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
        draw();
      });
      draw();
    }).catch(() => { box.innerHTML = '<p class="muted-line">Could not load the case list.</p>'; });
  }
  const app = () => document.getElementById('app');

  window.LCX = { justiceRatings, viewStats };
})();
