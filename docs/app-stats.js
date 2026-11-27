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
  // Dot strip: every eligible justice as a dot along one axis; `hi` highlighted, `ring` outlined. HTML, not SVG, so the
  // labels stay crisp at any width; each dot links to the justice's page and shows a tooltip on hover or focus.
  function strip(items, hi, ring, leftLabel, rightLabel, fmtV) {
    const vs = items.map(d => d.v), lo = Math.min(...vs), up = Math.max(...vs);
    const x = v => 1.5 + 97 * (v - lo) / ((up - lo) || 1);
    const sorted = items.slice().sort((a, b) => (a.id === hi) - (b.id === hi) || ring.has(a.id) - ring.has(b.id));
    return `<div class="st-strip2" role="group" aria-label="${esc(leftLabel)} to ${esc(rightLabel)}"><div class="st-track">
      ${sorted.map(d => { const p = x(d.v); const tip = `${d.name} · ${fmtV(d.v)}`;
        return `<a class="st-dot ${d.id === hi ? 'hi' : ring.has(d.id) ? 'ring' : ''} ${p > 70 ? 'tip-l' : p < 30 ? 'tip-r' : ''}" style="left:${p.toFixed(2)}%" href="#/justice/${esc(d.id)}" aria-label="${esc(tip)}"><span class="st-tip"><b>${esc(d.name)}</b>${esc(fmtV(d.v))}<em>Open profile →</em></span></a>`; }).join('')}
      </div><div class="st-ends"><span>${esc(leftLabel)}</span><span>${esc(rightLabel)}</span></div></div>`;
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
    return `<div class="st-bars">${rows.map(([lab, v, note, cls, ci, tip]) => `<div class="st-bar ${cls || ''}${tip ? ' has-tip" tabindex="0"' : `" title="${esc(lab + ': ' + fmtV(v) + (note ? ' — ' + note : ''))}"`}>
      <span class="lab">${esc(lab)}</span><span class="track"><i style="width:${Math.max(0.5, 100 * v / max).toFixed(1)}%"></i>${ci ? `<b class="ci" style="left:${(100 * ci[0] / max).toFixed(1)}%;width:${(100 * (ci[1] - ci[0]) / max).toFixed(1)}%"></b>` : ''}</span><span class="val">${esc(fmtV(v))}</span>${tip ? `<div class="st-tip" role="tooltip">${tip}</div>` : ''}</div>`).join('')}</div>`;
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
      ${r.elig ? `<div class="st-sub">Every justice with ${R.minVotes}+ votes, by liberal votes relative to colleagues · <span class="st-key"><i class="k-hi"></i>${esc(j.last || j.name)}</span> <span class="st-key"><i class="k-ring"></i>current Court</span></div>${strip(libItems, j.id, sitting, '← more liberal than colleagues', 'more conservative than colleagues →', v => Math.abs(v).toFixed(1) + (v <= 0 ? ' pts more liberal' : ' pts more conservative') + ' than colleagues')}` : ''}
      ${r.mqTerms ? `<div class="st-sub">Martin–Quinn score by term, with 95% interval (negative = liberal)</div>${line(r.mqTerms.map(t => [t[0], t[1], t[2], t[3]]), { ref: 0, label: 'Martin–Quinn score by term', fmtY: v => v.toFixed(1), fmtTip: p => p[1].toFixed(2) + ' (95% interval ' + p[2].toFixed(2) + ' to ' + p[3].toFixed(2) + ')' })}
        <div class="st-sub">All justices with Martin–Quinn scores, by career mean</div>${strip(mqItems, j.id, sitting, '← liberal', 'conservative →', v => 'career Martin–Quinn ' + v.toFixed(2))}` : ''}
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
      ${r.elig ? strip(instItems, j.id, sitting, '← less institutionalist', 'more institutionalist →', v => 'institutionalism index ' + v.toFixed(2)) : ''}
      <table class="st-table"><thead><tr><th>Component</th><th>Rate</th><th>vs. colleagues</th><th>More institutional if</th></tr></thead><tbody>
        ${comp.map(([lab, rate, rel, dir, n]) => `<tr><td>${esc(lab)}<div class="m">${esc(n)}</div></td><td>${pct(rate)}</td><td>${signed(rel)} pts</td><td>${dir}</td></tr>`).join('')}
      </tbody></table>
    </div>`;
    const method = `<details class="st-method"><summary>How these scores are computed</summary>
      <p><b>Data.</b> Every vote in the ${SCDB} (Spaeth et al., 2026 Release 01 and Legacy Release 07, 1791–2025) in cases decided with an opinion. Martin–Quinn scores: <a href="${esc(R.mqUrl)}" target="_blank" rel="noopener">${esc(R.mqSrc)}</a>; the latest public release ends with the 2021 Term, so later terms have none.</p>
      <p><b>Liberal–conservative.</b> SCDB codes each vote liberal or conservative by issue (for example, pro-defendant in criminal cases is liberal; pro-business in economic cases is conservative). The score is the share of liberal votes. Because the cases the Court takes change over time, the comparison that counts is against the colleagues who sat in the same cases: for each vote, the justice's vote minus the share of liberal votes among the others, averaged.</p>
      <p><b>Institutionalism.</b> Five measurable behaviors, each also measured against the colleagues in the same cases: voting with the majority; not writing separately; not concurring only in the judgment; not joining decisions that formally overrule precedent (SCDB <code>precedentAlteration</code>); and not joining decisions that declare a federal, state or local law unconstitutional (<code>declarationUncon</code>). The two last components count only decisions where the Court did overrule or strike down, so a vote to overrule or invalidate in dissent is not captured; they are shrunk toward zero when there are few such decisions (difference ÷ (decisions + ${R.shrink})). Each component is converted to a z-score across justices, signed so that higher is more institutional, and averaged; the result is shown as a percentile. SCDB has no variable for whether a ruling is narrow or broad, so that dimension is left out. The components are not independent of ideology: in a Court with a stable majority, members of the minority dissent more and join fewer overrulings.</p>
      <p class="attrib">These scores are this site's calculations from the data, not ratings published by the database's authors.</p>
    </details>`;
    el.innerHTML = `<h2 class="section-h">Ratings</h2><div class="st-two">${ideo}${inst}</div>${method}${M && M.j[j.id] ? modelPanel(M, M.j[j.id], j) : ''}`;
  }
  const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');

  const CHOICE = {
    ens: 'the Court-wide ensemble: the average of boosted trees and a random forest, each fitted on every justice’s votes with the justice as a predictor',
    pooled: 'the Court-wide boosted trees alone',
    rf: 'the Court-wide random forest alone',
    own: 'a model of this justice’s votes alone (logistic regression)',
    blend: 'the average of the boosted trees and a model of this justice’s votes alone'
  };
  function modelPanel(M, m, j) {
    const b = m.base, D = m.dock, F = m.full;
    const best = Math.max(b.majority, b.reverse, b.hindsight);
    // the current model and the strongest of the simple baselines
    const baseLab = best === b.majority ? `Baseline: always ${b.majorityLabel === 'petitioner' ? 'for the petitioner' : 'for the respondent'}, ${esc(j.last || j.name)}’s more common vote before 2022`
      : best === b.reverse ? 'Baseline: always for the petitioner (reverse)' : 'Baseline: best constant guess, picked with hindsight';
    const accRows = [
      ['Current model (used for the pending docket)', D.acc * 100, '', 'hi', D.ci.map(x => x * 100)],
      [baseLab, best * 100, '', 'base']
    ];
    const weak = m.verdict !== 'beats every baseline';
    const caseOf = Object.fromEntries(M.cases.map(c => [c.id, c]));
    const preds = (m.pred || []).map(([id, p]) => ({ c: caseOf[id], p })).filter(x => x.c).sort((a, b) => Math.abs(b.p - 0.5) - Math.abs(a.p - 0.5));
    const imp = (m.imp || []).filter(r => r[2] > 0.05).slice(0, 7);
    const impMax = Math.max(0.5, ...imp.map(r => r[2]));
    const LAB = { ens: 'ensemble', pooled: 'boosted trees', rf: 'random forest', own: 'own votes only', blend: 'trees + own' };
    const vals = Object.entries(D.val || {}).map(([k, v]) => `${LAB[k] || k} ${pct(v[0] * 100)}`).join(', ');
    const name = esc(j.last || j.name);
    return `<div class="panel st-panel st-model"><h4>Vote prediction model</h4>
      <p class="st-lead">Predicts whether ${name} votes for the petitioner (to reverse or vacate) or for the respondent (to affirm). Tested on ${name}’s ${fmt(m.nTest)} votes in the ${M.test[0]}–${M.test[1]} Terms (${esc(m.testSpan[0])} to ${esc(m.testSpan[1])}): each Term was predicted by models fitted only on earlier Terms, so no test vote was used to fit or choose the model.</p>
      <p class="st-verdict ${weak ? 'weak' : ''}"><b>Result.</b> ${esc(m.verdict.charAt(0).toUpperCase() + m.verdict.slice(1))}: ${pct(D.acc * 100)} of test votes called correctly, against ${pct(best * 100)} for the best simple baseline.${m.joint != null && M.calib.cal && M.calib.cal !== 'raw' ? ` After the recalibration used on the case pages: ${pct(m.joint * 100)}.` : ""}</p>
      <div class="st-sub">Test-vote accuracy (the bar on the model shows its 95% interval)</div>
      ${bars(accRows, 100, v => pct(v))}
      <div class="st-sub">Which model</div>
      <p class="st-lead">Every justice is predicted by ${esc(CHOICE[D.choice] || D.choice)}. Several models were compared on the ${M.val[0]}–${M.val[1]} Terms (predicted the same way, Term by Term): this one had the best log loss over all justices’ votes, and picking a different model for each justice did worse.${vals ? ` Validation accuracy for ${name}: ${vals}.` : ''}</p>
      <div class="st-sub">What moves ${name}’s predicted vote <span class="muted-line">(how much worse the test predictions get, in log loss, when a group of predictors is scrambled; hover or tap a row for what it measures and how it moves ${name})</span></div>
      ${imp.length ? bars(imp.map(r => { const dr = (m.dir || {})[r[0]] || {}; return [r[0], r[2], '', 'imp', null,
        `<b>${esc(r[0])}</b>${dr.how ? `<p><span>Measures</span>${esc(dr.how)}</p>` : ''}${dr.dir ? `<p><span>In ${name}’s votes</span>${esc(dr.dir)}</p>` : ''}<p class="m">Scrambling it makes the test predictions ${r[2].toFixed(1)}% worse in log loss (accuracy ${r[1] >= 0 ? '−' : '+'}${Math.abs(r[1]).toFixed(1)} pts).</p>`]; }), impMax, v => '+' + v.toFixed(1) + '%') : '<p class="muted-line">No predictor group improved the test predictions.</p>'}
      <div class="st-sub">Predicted votes in pending cases <span class="muted-line">(refitted on all votes through the ${M.test[1]} Term${M.calib.cal && M.calib.cal !== 'raw' ? ', then recalibrated' : ''}; the same probabilities as on each case page)</span></div>
      ${preds.length ? `<ul class="st-preds">${preds.map(({ c, p }) => `<li><a href="#/case/${esc(c.id)}">${esc(c.n)}</a><span class="muted-line">${esc(c.src)}${c.area ? ' · ' + esc(c.area) : ''}${c.arg ? ' · argued' : ''}</span><span class="st-pill ${p >= 0.5 ? 'rev' : 'aff'}" title="Predicted probability of voting for the petitioner: ${pct(p * 100, 0)}">${p >= 0.5 ? 'Reverse' : 'Affirm'} · ${pct((p >= 0.5 ? p : 1 - p) * 100, 0)}</span></li>`).join('')}</ul>` : '<p class="muted-line">No pending cases.</p>'}
      <details class="st-method"><summary>About the model</summary>
        <p><b>Predictors</b>, all fixed before the decision: issue area; lower court; whether each side is the federal government, a state, a local government or a private party; jurisdiction; whether the decision under review was liberal or conservative (Supreme Court Database coding; for pending cases estimated from the question presented, issue and parties by a classifier that is ${pct(M.lcClf.acc * 100, 0)} accurate on held-out recent cases, against ${pct(M.lcClf.base * 100, 0)} for a constant guess); ${name}’s record in earlier Terms (share of liberal votes and of votes for the petitioner, overall and in the issue area); ${name}’s lean relative to the other justices in the case, multiplied by the direction of the decision below and by the side of the United States and the President’s party; the side the United States supports as a party or amicus and whether the Solicitor General was invited to give views; the number of amicus briefs for each side and at the cert stage (supremecourt.gov docket pages, ${fmt(M.nFacts)} cases since 2004); how much ${name} and the Court as a whole questioned each side at oral argument, how often each interrupted counsel for each side, and who asked each side’s first and last question (official transcripts, ${fmt(M.nArg)} cases since 2004); ${name}’s Martin–Quinn score from the previous Term (latest public release, OT2021; imputed from the liberal-vote share where missing) relative to the other justices, multiplied by the direction of the decision below; and how often the Court has sided with petitioners recently and from the same lower court.</p>
        <p><b>Sources for the design:</b> Katz, Bommarito &amp; Blackman, <i>PLOS ONE</i> 2017 (one model across justices with each justice’s record, refitted Term by Term); Martin, Quinn, Ruger &amp; Kim, <i>Perspectives on Politics</i> 2004 (separate models per justice, led by the direction of the decision below); Epstein, Landes &amp; Posner, <i>J. Legal Stud.</i> 2010, Johnson et al. 2009 and Feldman, SCOTUSblog 2026 (questioning at argument); Jacobi &amp; Rozema, <i>B.C. L. Rev.</i> 2018 (interruptions); Martin &amp; Quinn, <i>Political Analysis</i> 2002 (ideal points); Solicitor General win rates (SCOTUSblog statistics); Kearney &amp; Merrill, <i>U. Pa. L. Rev.</i> 2000 (amicus briefs). Comparable published models call about 70% of votes correctly.</p>
        <p>A model is said to beat the baselines only if it is at least 2 points more accurate than the best of them and the lower end of its 95% interval is also above it.</p>
        <p class="attrib">Computed on ${esc(M.generated)}. Statistical predictions from past voting patterns, not forecasts by any expert.</p>
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
        <p class="attrib">All figures computed from the Supreme Court Database (Spaeth et al.), cases with SCDB decision types 1, 6 and 7 (decided with an opinion after oral argument). Format after <i>The Supreme Court, 2024 Term — The Statistics</i>, 139 Harv. L. Rev. 430 (2025); the numbers are this site's and will differ from the Review's, which are compiled from the opinions by hand.</p>
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

  /* ---------------------------------------------------------------- pending case: predicted votes and split odds */
  function casePrediction(el, id, M, J) {
    const c = M.cases.find(x => x.id === id || id.endsWith('/' + x.d));
    if (!c || !c.dist) { el.innerHTML = ''; return; }
    const byId = Object.fromEntries(J.justices.map(j => [j.id, j]));
    const votes = M.order.map(jid => { const r = (M.j[jid].pred || []).find(x => x[0] === c.id); return { j: byId[jid], p: r ? r[1] : 0.5 }; });
    const pRev = c.pRev, pAff = 1 - pRev, n = c.dist.length - 1;
    const cal = M.calib, emp = cal.emp || [];
    const outcomes = [];
    for (let r = n; r >= 0; r--) outcomes.push({ label: r * 2 > n ? `Reverse ${r}–${n - r}` : `Affirm ${n - r}–${r}`, side: r * 2 > n ? 'rev' : 'aff', p: c.dist[r], e: emp[r] });
    const top = Math.max(...outcomes.map(o => o.p)), scale = Math.max(top, ...outcomes.map(o => o.e || 0));
    const pc = x => (100 * x < 1 ? '<1' : Math.round(100 * x)) + '%';
    const gm = x => pct(100 * Math.exp(x), 1);
    const E = cal.eval || {}, me = E.joint || {}, hist = E['historical frequencies'] || {};
    const beats = me.splitLL > hist.splitLL;
    const unan = c.pUnan != null ? c.pUnan : c.dist[0] + c.dist[n], close = c.dist[4] + c.dist[5];
    const topK = c.top ? c.top[0] : c.dist.indexOf(Math.max(...c.dist));
    const topLab = topK * 2 > n ? `Reverse ${topK}–${n - topK}` : `Affirm ${n - topK}–${topK}`;
    const winRev = pRev >= 0.5, pWin = winRev ? pRev : pAff;
    const foldTxt = f => Object.entries(f || {}).filter(([, v]) => v).map(([k, v]) => `${k.replace('-', '–')} in ${v}`).join(', ');
    const f3 = x => x != null ? x.toFixed(3) : '—', p1 = x => x != null ? pct(100 * x, 1) : '—';
    const row = (lab, r, note, cls) => r ? `<tr class="${cls || ''}"><td>${lab}${note ? `<div class="m">${note}</div>` : ''}</td><td>${p1(r.win)}</td><td>${f3(r.winBrier)}</td><td>${p1(r.voteAcc)}</td><td>${f3(r.voteLL)}</td><td>${r.splitLL != null ? gm(r.splitLL) : '—'}</td><td>${r.unanPred != null ? pct(100 * r.unanPred, 0) : '—'}</td></tr>` : '';
    const H = cal.history || {}, HL = cal.headline || {}, REL = cal.reliability || {};
    const party = { federal: 'the federal government', state: 'a state', local: 'a local government', other: 'a private party' };
    const usTxt = c.us === 0 ? 'Not taking part (as far as the docket and transcript show)' : `Supports the ${c.us > 0 ? 'petitioner' : 'respondent'}${c.usAmicus ? ' as amicus curiae' : ' as a party'}`;
    const lc = c.lcLib;
    const facts = [
      ['Lower court', esc(c.lowerCourt || c.src)],
      ['Issue area', `${esc(c.area)} <span class="muted-line">(predicted from the question presented, ${pct(100 * c.areaP, 0)} confidence)</span>`],
      ['Parties', `${esc(party[c.pet] || c.pet)} v. ${esc(party[c.res] || c.res)}`],
      ['Decision below', `${lc >= 0.5 ? 'Liberal' : 'Conservative'} <span class="muted-line">(estimated, ${pct(100 * Math.max(lc, 1 - lc), 0)} likely, in the Supreme Court Database’s sense of the terms)</span>`],
      ['United States', esc(usTxt) + (c.cvsg ? ' <span class="muted-line">(Solicitor General invited to give views at the cert stage)</span>' : '')],
      ['Amicus briefs', c.am ? `${c.am[0]} for the petitioner, ${c.am[1]} for the respondent <span class="muted-line">(${c.am[2]} at the cert stage; side read from the briefing schedule)</span>` : '<span class="muted-line">Merits briefing not complete; not used</span>'],
      ['Oral argument', c.arg ? `The Court questioned the ${c.argCourt > 0 ? 'respondent' : 'petitioner'}’s side more <span class="muted-line">(log ratio of words ${signed(c.argCourt, 2)}; the side questioned more tends to lose)</span>` : '<span class="muted-line">Not argued yet (or no transcript); not used</span>']
    ];
    el.innerHTML = `<section class="st-pred"><h2>Predicted outcome <small>(statistical model)</small></h2>
      <div class="st-market">
        <p class="st-verdict"><b>Likeliest split: ${esc(topLab)}</b> · ${pc(c.dist[topK])} chance <span class="muted-line">(of the ten possible splits, the single most probable; ${winRev ? 'reversal' : 'affirmance'} by any margin: ${pc(pWin)})</span></p>
        <div class="st-mhead"><div><b>${pc(pRev)}</b><span>Reverse or vacate</span></div><div class="mid"><b>${pc(unan)}</b><span>Unanimous</span></div><div class="aff"><b>${pc(pAff)}</b><span>Affirm</span></div></div>
        <div class="st-split" role="img" aria-label="Chance of reversal ${pc(pRev)}"><i style="width:${(100 * pRev).toFixed(1)}%"></i></div>
        <div class="st-sub st-board-h"><span>Chance of each vote split</span><span>Model</span><span title="How often each split occurred in ${M.val[0]}–${M.val[1]} Term cases">Past</span></div>
        <div class="st-board">${outcomes.map(o => `<div class="st-row ${o.side} ${o.p === top ? 'top' : ''}" title="${esc(o.label)}: model ${pct(100 * o.p, 1)}${o.e != null ? '; occurred in ' + pct(100 * o.e, 1) + ' of ' + M.val[0] + '–' + M.val[1] + ' Term cases' : ''}"><span class="lab">${esc(o.label)}</span><span class="track"><i style="width:${(100 * o.p / scale).toFixed(1)}%"></i>${o.e != null ? `<b class="past" style="left:${(100 * o.e / scale).toFixed(1)}%"></b>` : ''}</span><span class="val">${pc(o.p)}</span><span class="val past">${o.e != null ? pc(o.e) : ''}</span></div>`).join('')}</div>
        <p class="st-note">The tick on each bar marks the “Past” share. Chance of a 5–4 split either way: ${pc(close)}. ${beats ? '' : `<b>Be cautious:</b> on the ${fmt(cal.nTest)} test cases these split odds did not beat the past frequencies.`}</p>
      </div>
      <div class="st-sub">What the model sees in this case</div>
      <dl class="st-facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
      <div class="st-sub">How each justice is predicted to vote</div>
      <div class="st-jv">${votes.map(v => `<a class="st-jrow" href="#/justice/${esc(v.j.id)}" title="${esc(v.j.name)}: ${pct(100 * v.p, 0)} chance of voting for the petitioner">
        <span class="nm">${esc(v.j.name)}</span>
        <span class="lean"><i class="mid"></i><i class="dot ${v.p >= 0.5 ? 'rev' : 'aff'}" style="left:${(100 * v.p).toFixed(1)}%"></i></span>
        <span class="st-pill ${v.p >= 0.5 ? 'rev' : 'aff'}">${v.p >= 0.5 ? 'Reverse' : 'Affirm'} · ${pct(100 * Math.max(v.p, 1 - v.p), 0)}</span></a>`).join('')}
        <div class="st-ends"><span>← affirm</span><span>reverse →</span></div></div>
      <details class="st-method"><summary>How this is estimated, and how well it has worked</summary>
        <p>Each justice’s model (see the justice’s profile) weighs the facts above together with that justice’s own record: for example, a justice who leans liberal relative to colleagues is predicted to affirm a liberal decision below and reverse a conservative one, to a degree learned from that justice’s past votes.</p>
        <p><b>The probabilities for each justice</b> are those justices’ own models${cal.cal && cal.cal !== 'raw' ? ', recalibrated on the ' + M.val[0] + '–' + M.val[1] + ' Terms because that made the individual predictions more accurate in probability on held-out Terms' : ', unchanged'}: combining them into split odds does not alter them.</p>
        <p><b>From nine votes to a split.</b> Counting the justices who are above 50% ignores how sure each prediction is and would rarely name a unanimous decision, and treating the nine votes as independent would almost never produce one. In fact the votes move together: ${pct(100 * cal.unanVal, 0)} of the ${M.val[0]}–${M.val[1]} cases and ${pct(100 * (me.unanAct || 0), 0)} of the ${M.test[0]}–${M.test[1]} cases were unanimous. The split odds therefore come from a model of how the nine votes move together, fitted on ${fmt(cal.nVal)} cases from the ${M.val[0]}–${M.val[1]} Terms to how those cases actually split, which keeps each justice’s probability exactly. Some cases are unanimous: the model gives unanimity a share of the most the nine probabilities allow (a unanimous reversal can never be likelier than the least likely justice’s vote to reverse)${/case-dependent/.test(cal.struct || '') ? ', a share that depends on how far the nine predictions agree, the amicus participation and the spread of questioning at argument' : ` — ${pct(100 * (1 / (1 + Math.exp(-cal.theta[0]))) * 0.995, 0)} of it in every case (letting the share depend on the case did not predict the ${M.val[0]}–${M.val[1]} splits better in cross-validation)`}. In the remaining cases the votes move together through a Court-wide factor and a factor weighted by each justice’s lean. The headline is the single most probable of the ten splits, with its probability and the chance of each side winning beside it. ${cal.pairMae != null ? `On the test cases, the agreement rate this implies for each pair of justices is off from the actual rate by ${(100 * cal.pairMae).toFixed(1)} percentage points on average (${(100 * cal.pairMaeIndep).toFixed(1)} if the votes were treated as independent).` : ''}</p>
        <p><b>Test</b> on the ${fmt(cal.nTest)} cases of the ${M.test[0]}–${M.test[1]} Terms, never used for fitting or choosing (average probability of the actual split: geometric mean; higher is better; vote log loss: lower is better):</p>
        <div class="st-scroll"><table class="st-table st-num"><thead><tr><th>Method</th><th>Winning side correct</th><th>Winning side Brier</th><th>Votes correct</th><th>Vote log loss</th><th>Actual split</th><th>Predicted unanimous (actual ${pct(100 * (me.unanAct || 0), 0)})</th></tr></thead><tbody>
          ${row('This model', me, 'boosted trees + random forest with argument interruptions, first/last questions and Martin–Quinn scores; joint split model', 'tot')}
          ${row('Version of Nov. 25', H['previous (Nov. 25)'], 'per-justice model choice, earlier predictors; same joint split model')}
          ${row('Version of Nov. 17', H['previous (Nov. 17)'], 'consensus/contested mixture that shrank the justices’ probabilities')}
          ${row('Always reverse', E['always reverse'], 'the Court reverses or vacates in about two thirds of argued cases')}
          ${row('Each justice’s past rate of voting to reverse', E['justice reversal rate'], 'before the test Terms')}
          ${row('Past split frequencies', hist, `${M.val[0]}–${M.val[1]} Terms, the same for every case`)}
        </tbody></table></div>
        <p>${beats ? '' : '<b>Be cautious:</b> on the test cases these split odds did not beat the past frequencies. '}Likeliest split across the test cases: ${esc(foldTxt(me.topFold))} (counting the justices above 50% would give ${esc(foldTxt((E['count above 50%'] || {}).topFold))}); the actual splits were ${esc(foldTxt(me.actFold))}. A good forecast names a unanimous result as likeliest more often than unanimity occurs, because divided outcomes split their probability over several margins; the likeliest split was the actual one in ${pct(100 * (me.topHit || 0), 0)} of the test cases${HL['likeliest divided split unless P(unanimous) >= 50%'] != null ? `, against ${pct(100 * HL['likeliest divided split unless P(unanimous) >= 50%'], 0)} for naming the likeliest divided split whenever unanimity is under 50% and ${pct(100 * HL['count of justices above 50%'], 0)} for counting the justices above 50%` : ''}.${REL.reverse ? ` Calibration of the chance of reversal on the test cases (predicted, actual, cases): ${REL.reverse.map(b => `${pct(100 * b[0], 0)}/${pct(100 * b[1], 0)} (${b[2]})`).join(', ')}.` : ''} ${me.unanCal ? `Predicted against actual unanimity, by band of predicted probability: ${me.unanCal.map(b => `${pct(100 * b[0], 0)} predicted, ${pct(100 * b[1], 0)} actual (${b[2]} cases)`).join('; ')}.` : ''}${cal.confN ? ` In the ${fmt(cal.confN)} test cases where one side had at least 75%, that side won ${pct(100 * cal.confHit, 0)} of the time.` : ''}</p>
        <p class="attrib">Computed on ${esc(M.generated)} from the Supreme Court Database, supremecourt.gov docket pages and argument transcripts. A statistical estimate, not a betting market and not anyone’s forecast; it ignores recusals.</p>
      </details></section>`;
  }

  window.LCX = { justiceRatings, viewStats, casePrediction };
})();
