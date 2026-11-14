"""Build docs/data/models.js: one model per sitting justice that predicts the justice's vote (for the petitioner, i.e.
to reverse or vacate, versus for the respondent, i.e. to affirm), evaluated on a held-out test set, and applied to
the undecided cases in docs/data/docket.js.

Training data: Supreme Court Database (scdb_lib.py), orally argued cases with an opinion (decisionType 1, 6, 7) in which
the justice voted and SCDB codes a winning party (partyWinning 0 or 1). Label: voted for the petitioner =
(in the majority and the petitioner won) or (in the minority and the petitioner lost).

Two models per justice, each chosen by 5-fold cross-validation on the training set only (logistic regression with
four penalty strengths, or gradient-boosted trees):
  full    every SCDB predictor known before the decision: issue area, issue, law type, source court (and its group),
          origin court group, lower-court disposition and its direction, reason for granting cert, jurisdiction,
          petitioner and respondent (SCDB code and a coarse class), administrative action, three-judge district court,
          lower-court dissent, term.
  docket  only predictors that can be read off a pending case: issue area, source-court group, coarse petitioner and
          respondent class (federal / state / local government / other), jurisdiction, term. Used for the docket.
Both models also use two added predictors (the page reports test accuracy with and without them):
  oral argument  how much the justice, and all justices together, questioned the respondent's side versus the
                 petitioner's (words and turns, log ratio) in the Court's official transcript (build_arguments.py;
                 October Term 2004 on, when transcripts began naming the justice speaking; 0 with a flag otherwise);
  lower-court history  how often the Court sided with petitioners in cases from the same lower-court group over the
                 five previous terms (from SCDB, smoothed toward 60% with 5 pseudo-cases).
Vote splits for pending cases: votes in one case move together, so each justice's log-odds get a shared case-level shift
u ~ Normal(0, sigma^2); sigma is fitted by maximum likelihood on the observed number of votes for the petitioner in cases
decided by all nine sitting justices, using out-of-fold predictions (5 folds grouped by case). The split distribution
is computed by Gauss-Hermite quadrature; its fit is compared with independent votes and with the historical split
frequencies.
Test set: the most recent 20% of each justice's votes by decision date (at least 40); the models never see them while
being fitted or tuned. A model is said to beat the baselines only if it is 2+ points better and the lower end of its 95% interval is
above the best one. Baselines on the same test set: the training set's more common vote, and always voting for the
petitioner (reverse), and the better of always-petitioner and always-respondent picked with hindsight on the test
set (a deliberately strict bar). Importance: drop in test accuracy when one predictor is shuffled (permutation importance, 10
repeats). After evaluation the docket model is refitted on all of the justice's votes.

Pending cases: source court from the "Lower Ct" line of the supremecourt.gov docket page; party class from the counsel
listed for each side on that page (the Solicitor General of the United States = federal; a state attorney general's or
solicitor general's office = state; a county, city, town or school-district party = local); jurisdiction from the
docket number ("Orig.") or a jurisdictional statement (appeal); issue area predicted from the question presented by a
TF-IDF + logistic-regression classifier trained on the Oyez questions of decided cases with their SCDB issue area
(its own held-out accuracy is reported).
Run from the repo root:  python scripts/build_models.py
"""
import html, json, os, re, warnings
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from scdb_lib import load_votes, justice_ids, site_ids, source_group, load_js, write_js, path, dk_norm, FULL, ISSUE_AREA, SRC

warnings.filterwarnings('ignore')
SEED = 20261114
CURRENT = ['JGRoberts', 'CThomas', 'SAAlito', 'SSotomayor', 'EKagan', 'NMGorsuch', 'BMKavanaugh', 'ACBarrett', 'KBJackson']
LABELS = {'issueArea': 'Issue area', 'issue': 'Specific issue', 'lawType': 'Type of law', 'srcGroup': 'Lower court (group)',
          'caseSource': 'Lower court', 'originGroup': 'Court of origin (group)', 'lcDisposition': 'Lower-court disposition',
          'lcDispositionDirection': 'Lower-court direction', 'certReason': 'Reason cert was granted', 'jurisdiction': 'Jurisdiction',
          'petParty': 'Petitioner class', 'resParty': 'Respondent class', 'petitioner': 'Petitioner type', 'respondent': 'Respondent type',
          'adminAny': 'Agency action under review', 'threeJudgeFdc': 'Three-judge district court', 'lcDisagreement': 'Dissent below',
          'term': 'Term', 'argHas': 'Argument transcript available', 'argW': "Justice's questioning, respondent vs. petitioner (words)",
          'argT': "Justice's questioning, respondent vs. petitioner (turns)", 'argCourt': "All justices' questioning, respondent vs. petitioner",
          'srcRev': 'How often the Court sided with petitioners from this lower court (prior 5 terms)'}
NUM_OLD = ['term']
NUM = ['term', 'argHas', 'argW', 'argT', 'argCourt', 'srcRev']
FULL_CAT = ['issueArea', 'issue', 'lawType', 'srcGroup', 'caseSource', 'originGroup', 'lcDisposition', 'lcDispositionDirection',
            'certReason', 'jurisdiction', 'petParty', 'resParty', 'petitioner', 'respondent', 'adminAny', 'threeJudgeFdc', 'lcDisagreement']
DOCKET_CAT = ['issueArea', 'srcGroup', 'petParty', 'resParty', 'jurisdiction']


def party_class(code, state):
    """SCDB petitioner/respondent code -> federal / state / local / other (coarse, from the SCDB codebook groupings)."""
    if code != code:
        return 'other'
    c = int(code)
    if c in (1, 14, 22, 23, 27) or 300 <= c <= 399:
        return 'federal'
    if c in (2, 4, 7, 17, 26, 28):
        return 'state'
    if c in (3, 5, 18, 21):
        return 'local'
    if c in (19, 6, 16, 20):
        return 'state' if state == state and state else 'federal'
    return 'other'


def prep(d):
    x = pd.DataFrame(index=d.index)
    for c in ['issueArea', 'issue', 'lawType', 'caseSource', 'lcDisposition', 'lcDispositionDirection', 'certReason', 'jurisdiction',
              'petitioner', 'respondent', 'threeJudgeFdc', 'lcDisagreement']:
        x[c] = d[c].fillna(-1).astype(int).astype(str)
    x['srcGroup'] = d.caseSource.map(source_group)
    x['originGroup'] = d.caseOrigin.map(source_group)
    x['adminAny'] = d.adminAction.notna().astype(int).astype(str)
    x['petParty'] = [party_class(a, b) for a, b in zip(d.petitioner, d.petitionerState)]
    x['resParty'] = [party_class(a, b) for a, b in zip(d.respondent, d.respondentState)]
    x['term'] = d.term.astype(float)
    return x


def candidates(cat, num=NUM):
    onehot = lambda: ColumnTransformer([('c', OneHotEncoder(handle_unknown='ignore', min_frequency=5), cat),
                                        ('n', StandardScaler(), num)])
    ordinal = lambda: ColumnTransformer([('c', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan,
                                                              min_frequency=5, encoded_missing_value=np.nan), cat),
                                         ('n', 'passthrough', num)])
    out = {f'logistic (C={C})': Pipeline([('p', onehot()), ('m', LogisticRegression(C=C, max_iter=3000, solver='liblinear'))]) for C in (0.03, 0.1, 0.3, 1.0)}
    out['gradient-boosted trees'] = Pipeline([('p', ordinal()), ('m', HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=1.0, random_state=SEED,
        categorical_features=list(range(len(cat)))))])
    return out


def fit_eval(Xtr, ytr, Xte, yte, cat, num=NUM, importance=True):
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    best, best_s, cvs = None, -1, {}
    cols = cat + num
    for name, m in candidates(cat, num).items():
        s = cross_val_score(m, Xtr[cols], ytr, cv=cv, scoring='accuracy').mean()
        cvs[name] = round(float(s), 4)
        if s > best_s:
            best, best_s = name, s
    m = candidates(cat, num)[best].fit(Xtr[cols], ytr)
    acc = float((m.predict(Xte[cols]) == yte).mean())
    imp = []
    if importance:
        pi = permutation_importance(m, Xte[cols], yte, n_repeats=10, random_state=SEED, scoring='accuracy')
        imp = sorted([[LABELS[c], round(float(pi.importances_mean[i]) * 100, 2)] for i, c in enumerate(cols)], key=lambda r: -r[1])
    return best, round(float(best_s), 4), cvs, round(acc, 4), imp, m


# ------------------------------------------------------------- added predictors
def load_arguments():
    p = path('data/raw/transcripts/features.json')
    return json.load(open(p)) if os.path.exists(p) else {}


def arg_feats(rec, surname):
    """Oral argument questioning (build_arguments.py): positive = more aimed at the respondent."""
    if not rec:
        return [0.0, 0.0, 0.0, 0.0]
    own = rec.get(surname, [0, 0, 0, 0])
    tw = [sum(v[0] for v in rec.values()), sum(v[1] for v in rec.values())]
    return [1.0, float(np.log1p(own[1]) - np.log1p(own[0])), float(own[3] - own[2]), float(np.log1p(tw[1]) - np.log1p(tw[0]))]


def src_rev_table(d):
    """(term, lower-court group) -> share of the Court's decisions for the petitioner in cases from that group over the
    five previous terms, smoothed toward 60% with 5 pseudo-cases."""
    c = d.drop_duplicates('caseId')
    g = c.assign(src=c.caseSource.map(source_group), won=(c.partyWinning == 1).astype(int)).groupby(['src', 'term']).won.agg(['sum', 'count'])
    out = {}
    terms = range(int(c.term.min()), int(c.term.max()) + 2)
    for src in g.index.get_level_values(0).unique():
        gs = g.loc[src]
        for t in terms:
            w = gs[(gs.index >= t - 5) & (gs.index < t)]
            out[(t, src)] = float((w['sum'].sum() + 3) / (w['count'].sum() + 5))
    return out


def outcome_dist(ps, sigma, mu=0.0, nodes=40):
    """P(k of the justices vote for the petitioner), k = 0..n, when each justice's log-odds are shifted by a shared
    case-level amount u ~ Normal(mu, sigma^2) (votes in one case move together), by Gauss-Hermite quadrature."""
    x, w = np.polynomial.hermite_e.hermegauss(nodes)
    w = w / w.sum()
    lo = np.log(np.clip(ps, 1e-6, 1 - 1e-6) / (1 - np.clip(ps, 1e-6, 1 - 1e-6)))
    dist = np.zeros(len(ps) + 1)
    for xi, wi in zip(x, w):
        q = 1 / (1 + np.exp(-(lo + mu + sigma * xi)))
        pb = np.array([1.0])
        for qj in q:
            pb = np.convolve(pb, [1 - qj, qj])
        dist += wi * pb
    return dist


def binom_ci(p, n):
    se = (p * (1 - p) / n) ** 0.5
    return [round(max(0, p - 1.96 * se), 4), round(min(1, p + 1.96 * se), 4)]


# ------------------------------------------------------------- pending docket features
STATES = '|'.join('Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming'.split() + ['New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Rhode Island', 'South Carolina', 'South Dakota', 'West Virginia'])


def strip(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s)))


def docket_features(case):
    dk = case['d']
    p = path(f'data/raw/docket/d-{dk}.html')
    f = {'srcGroup': 'Other or none', 'petParty': 'other', 'resParty': 'other', 'jurisdiction': '1', 'lowerCourt': ''}
    if 'orig' in dk.lower() or re.search(r'\bOrig', case.get('n', '')):
        f['jurisdiction'] = '9'
    if not os.path.exists(p):
        return f, False
    t = strip(open(p, encoding='utf-8', errors='replace').read())
    m = re.search(r'Lower Ct: (.*?)(?: Case Numbers:| Decision Date:| Questions Presented|$)', t)
    lc = (m.group(1).strip() if m else '')
    f['lowerCourt'] = lc
    circ = re.search(r'Court of Appeals for the (First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|District of Columbia|Federal) Circuit', lc)
    if circ:
        f['srcGroup'] = {'District of Columbia': 'D.C.'}.get(circ.group(1), circ.group(1)) + ' Circuit'
    elif re.search(r'United States District Court', lc):
        f['srcGroup'] = 'District courts'
    elif re.search(r'Armed Forces', lc):
        f['srcGroup'] = 'Armed Forces'
    elif lc and not re.search(r'United States', lc):
        f['srcGroup'] = 'State courts'
    if re.search(r'Statement as to jurisdiction|Jurisdictional Statement', t, re.I):
        f['jurisdiction'] = '2'
    sec_p = re.search(r'Attorneys for Petitioners?(.*?)(?:Attorneys for Respondents?|Other$|$)', t)
    sec_r = re.search(r'Attorneys for Respondents?(.*?)(?:Other Attorneys|Attorneys for Petitioners?|$)', t)

    def cls(sec):
        """Class of the side's lead party, from its counsel of record and party name (the first block in the section)."""
        if not sec:
            return 'other'
        m = re.search(r'^(.*?Party name: .{0,160})', sec.group(1))
        s = m.group(1) if m else sec.group(1)[:600]
        party = s.split('Party name:')[-1]
        if re.search(r'Solicitor General.{0,120}(United States|Department of Justice)', s) or re.match(r'\s*United States\b', party):
            return 'federal'
        if (re.search(r'\b(County|City|Town|Township|Village|Borough|School District|Board of Education)\b|\bCty\.', party)
                or re.search(r"(County|City) (Attorney|Counsel|Solicitor)|State'?s Attorney", s)):
            return 'local'
        if re.match(r'\s*(State of|Commonwealth of|People of the State of)', party) or re.match(r'\s*(' + STATES + r')(,| et al\.|\s*$)', party):
            return 'state'
        if re.search(r'(Office of (the )?(Attorney|Solicitor) General|Attorney General of|Solicitor General of|State Solicitor General|Department of Law)', s):
            return 'state'
        return 'other'
    f['petParty'], f['resParty'] = cls(sec_p), cls(sec_r)
    return f, True


def issue_classifier(d, sid):
    """TF-IDF + logistic regression: Oyez question text -> SCDB issue area. Test = the most recent 20% of cases."""
    cases = load_js('scotus')['cases']
    q = {c['id']: (c.get('q') or '') + ' ' + (c.get('ds') or '') for c in cases}
    first = d.drop_duplicates('caseId')
    rows = [(q[sid[r.caseId]], int(r.issueArea), r.date) for r in first.itertuples()
            if r.caseId in sid and r.issueArea == r.issueArea and len(q.get(sid[r.caseId], '').strip()) > 30]
    df = pd.DataFrame(rows, columns=['q', 'a', 'date']).sort_values('date')
    cut = int(len(df) * 0.8)
    tr, te = df.iloc[:cut], df.iloc[cut:]
    m = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words='english'), LogisticRegression(C=5, max_iter=1000, solver='liblinear'))
    m.fit(tr.q, tr.a)
    acc = float((m.predict(te.q) == te.a).mean())
    base = float((te.a == tr.a.mode()[0]).mean())
    m.fit(df.q, df.a)
    return m, {'n': len(df), 'nTest': len(te), 'acc': round(acc, 4), 'base': round(base, 4)}


def verdict_of(acc, ci, best):
    """Plain-language result. 'Beats' needs at least 2 points over the best baseline; it is called certain only when the
    lower end of the 95% interval is also above that baseline."""
    if acc > best + 0.02:
        return 'beats every baseline' if ci[0] > best else 'beats every baseline on this test set, but by less than its margin of error'
    if acc > best + 0.005:
        return 'barely beats the best baseline'
    return 'no better than a baseline'


def fit_shift(cal):
    """Maximum-likelihood (mu, sigma) of the shared case-level shift: coarse grid, then a finer one around the best."""
    ll = lambda m, sg: float(np.mean([np.log(max(outcome_dist(ps, sg, m, nodes=24)[k], 1e-12)) for ps, k in cal]))
    best = max(((ll(m, sg), m, sg) for m in np.arange(-1.5, 1.51, 0.25) for sg in np.arange(0, 4.01, 0.25)))
    _, m0, s0 = best
    best = max(((ll(m, sg), m, sg) for m in np.arange(m0 - 0.2, m0 + 0.21, 0.05) for sg in np.arange(max(0, s0 - 0.2), s0 + 0.21, 0.05)))
    _, m1, s1 = best
    final = float(np.mean([np.log(max(outcome_dist(ps, s1, m1)[k], 1e-12)) for ps, k in cal]))
    return round(float(m1), 2), round(float(s1), 2), final


def main():
    d = load_votes()
    d = d[d.decisionType.isin(FULL) & d.partyWinning.isin([0, 1]) & d.majority.isin([1, 2])].copy()
    d['date'] = pd.to_datetime(d.dateDecision, format='%m/%d/%Y', errors='coerce')   # SCDB dates are m/d/yyyy strings
    d['y'] = (((d.majority == 2) & (d.partyWinning == 1)) | ((d.majority == 1) & (d.partyWinning == 0))).astype(int)
    X = prep(d)
    code2id, jinfo = justice_ids()
    surname = {c: re.sub(r'[^A-Z]', '', jinfo[j]['last'].upper().replace('’', "'")) for c, j in code2id.items() if j in jinfo}
    # added predictors: lower-court history and oral argument questioning
    srev = src_rev_table(d)
    X['srcRev'] = [srev.get((int(t), g), 0.6) for t, g in zip(d.term, X.srcGroup)]
    ARG = load_arguments()
    keys = [f'{int(t)}/{dk_norm(k)}' for t, k in zip(d.term, d.docket)]
    af = np.array([arg_feats(ARG.get(k), surname.get(j, '')) for k, j in zip(keys, d.justiceName)])
    X['argHas'], X['argW'], X['argT'], X['argCourt'] = af[:, 0], af[:, 1], af[:, 2], af[:, 3]
    print(f'argument transcripts matched for {int(X.argHas.sum())} of {len(X)} votes', flush=True)
    sid = site_ids(d)
    clf, clf_eval = issue_classifier(d, sid)
    print('issue-area classifier', clf_eval, flush=True)

    K = load_js('docket')
    pending = []
    seen = set()
    for c in K['cases']:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        if not c.get('n'):
            c = dict(c, n='No. ' + c['d'])
        f, ok = docket_features(c)
        qtext = (c.get('q') or '') + ' ' + (c.get('ds') or '')
        probs = clf.predict_proba([qtext])[0]
        f['issueArea'] = str(int(clf.classes_[probs.argmax()]))
        f['issueP'] = round(float(probs.max()), 3)
        f['term'] = float(c.get('t') or K.get('term') or 2026)
        f['srcRev'] = srev.get((int(f['term']), f['srcGroup']), 0.6)
        trn = (c.get('tr') or '').rsplit('/', 1)[-1][:-4]
        f['argKey'] = f"{int(f['term'])}/{re.sub(r'_[a-z0-9]+$', '', trn).lower()}" if trn else ''
        pending.append((c, f, ok))
    P = pd.DataFrame([f for _, f, _ in pending])

    out, oof = {}, {}
    for code in CURRENT:
        m = d.justiceName == code
        dj = d[m].sort_values(['date', 'caseId'], kind='stable'); Xj = X.loc[dj.index]
        y = dj.y.values
        nte = max(40, int(round(len(dj) * 0.2)))
        Xtr, Xte, ytr, yte = Xj.iloc[:-nte], Xj.iloc[-nte:], y[:-nte], y[-nte:]
        maj_cls = int(round(ytr.mean()))
        base_major = float((yte == maj_cls).mean())
        base_rev = float((yte == 1).mean())
        fb, fcv, fcvs, facc, fimp, _ = fit_eval(Xtr, ytr, Xte, yte, FULL_CAT)
        ob, _, _, oacc, _, _ = fit_eval(Xtr, ytr, Xte, yte, FULL_CAT, NUM_OLD, importance=False)   # without the added predictors
        db, dcv, dcvs, dacc, dimp, _ = fit_eval(Xtr, ytr, Xte, yte, DOCKET_CAT)
        base_hind = max(base_rev, 1 - base_rev)   # the better constant guess, chosen with hindsight on the test set
        best_base = max(base_major, base_rev, base_hind)
        verdict = verdict_of(facc, binom_ci(facc, nte), best_base)
        cols = DOCKET_CAT + NUM
        # out-of-fold predictions (5 folds by case) for calibrating how votes move together
        oof[code] = pd.Series(cross_val_predict(candidates(DOCKET_CAT)[db], Xj[cols], y, groups=dj.caseId.values,
                                                cv=GroupKFold(5), method='predict_proba')[:, 1], index=dj.caseId.values)
        final = candidates(DOCKET_CAT)[db].fit(Xj[cols], y)
        Pj = P.copy()
        a = np.array([arg_feats(ARG.get(k), surname.get(code, '')) for k in Pj.argKey]) if len(Pj) else np.zeros((0, 4))
        Pj['argHas'], Pj['argW'], Pj['argT'], Pj['argCourt'] = (a[:, i] for i in range(4))
        pr = final.predict_proba(Pj[cols])[:, 1] if len(Pj) else []
        jid = code2id[code]
        out[jid] = {
            'code': code, 'n': int(len(dj)), 'nTrain': int(len(ytr)), 'nTest': int(nte),
            'trainSpan': [dj.date.iloc[0].strftime('%Y-%m-%d'), dj.date.iloc[-nte - 1].strftime('%Y-%m-%d')],
            'testSpan': [dj.date.iloc[-nte].strftime('%Y-%m-%d'), dj.date.iloc[-1].strftime('%Y-%m-%d')],
            'revRateTrain': round(float(ytr.mean()), 4), 'testArg': round(float(Xte.argHas.mean()), 3),
            'base': {'majority': round(base_major, 4), 'majorityLabel': 'petitioner' if maj_cls else 'respondent', 'reverse': round(base_rev, 4), 'hindsight': round(base_hind, 4)},
            'dverdict': verdict_of(dacc, binom_ci(dacc, nte), best_base),
            'full': {'model': fb, 'cv': fcv, 'cvAll': fcvs, 'acc': facc, 'ci': binom_ci(facc, nte), 'imp': fimp[:8]},
            'fullOld': {'model': ob, 'acc': oacc},
            'docket': {'model': db, 'cv': dcv, 'cvAll': dcvs, 'acc': dacc, 'ci': binom_ci(dacc, nte), 'imp': dimp[:6]},
            'verdict': verdict,
            'pred': [[c['id'], round(float(p), 3)] for (c, _, _), p in zip(pending, pr)],
        }
        print(f"{code:12} n={len(dj):5} test={nte:4} base={best_base:.3f} | full {fb:24} test={facc:.3f} (without added predictors {oacc:.3f}) | docket {db:24} test={dacc:.3f} -> {verdict}", flush=True)
        print('   top:', fimp[:4], flush=True)

    # ---- how the nine votes move together: fit sigma of a shared case-level shift on cases all nine decided
    jids = [code2id[c] for c in CURRENT]
    common = set.intersection(*[set(oof[c].index) for c in CURRENT])
    cases_k = d[d.caseId.isin(common) & d.justiceName.isin(CURRENT)].groupby('caseId').y.sum()
    cal = [(np.array([float(oof[c].loc[cid]) if np.ndim(oof[c].loc[cid]) == 0 else float(oof[c].loc[cid].iloc[0]) for c in CURRENT]), int(k)) for cid, k in cases_k.items()]
    json.dump({'cases': [[ps.tolist(), k] for ps, k in cal]}, open(path('data/raw/models_cal.json'), 'w'))
    mu, sigma, best = fit_shift(cal)
    ll0 = float(np.mean([np.log(max(outcome_dist(ps, 0.0)[k], 1e-12)) for ps, k in cal]))
    emp = np.bincount([k for _, k in cal], minlength=10) / max(1, len(cal))
    ll_emp = float(np.mean([np.log(max(emp[k], 1e-12)) for _, k in cal]))
    hits = np.mean([(outcome_dist(ps, sigma, mu)[5:].sum() >= 0.5) == (k >= 5) for ps, k in cal]) if cal else 0
    rev_base = np.mean([k >= 5 for _, k in cal]) if cal else 0
    calib = {'n': len(cal), 'sigma': float(sigma), 'mu': float(mu), 'll': round(best, 4), 'llIndep': round(ll0, 4), 'llEmp': round(ll_emp, 4),
             'emp': [round(float(x), 4) for x in emp],
             'hit': round(float(hits), 4), 'revBase': round(float(max(rev_base, 1 - rev_base)), 4),
             'span': [str(d[d.caseId.isin(common)].date.min().date()), str(d[d.caseId.isin(common)].date.max().date())] if cal else []}
    print('calibration', calib, flush=True)

    cases = []
    for k, (c, f, ok) in enumerate(pending):
        ps = np.array([out[j]['pred'][k][1] for j in jids])
        dist = outcome_dist(ps, sigma, mu)
        cases.append({'id': c['id'], 'n': c['n'], 'd': c['d'], 'lowerCourt': f['lowerCourt'], 'src': f['srcGroup'],
                      'pet': f['petParty'], 'res': f['resParty'], 'jur': f['jurisdiction'], 'area': ISSUE_AREA.get(int(f['issueArea']), ''),
                      'areaP': f['issueP'], 'page': ok, 'arg': bool(f['argKey'] and f['argKey'] in ARG),
                      'dist': [round(float(x), 4) for x in dist], 'pRev': round(float(dist[5:].sum()), 4)})
    data = {'src': SRC, 'generated': pd.Timestamp.now().strftime('%Y-%m-%d'), 'issueClf': clf_eval, 'labels': LABELS,
            'calib': calib, 'order': jids, 'nArg': int(len(ARG)), 'j': out, 'cases': cases}
    kb = write_js('models', 'MODELS', data) / 1024
    print(f'models.js {kb:.0f} KB; {len(cases)} pending cases')
    for c in cases:
        top = int(np.argmax(c['dist']))
        print(f"  {c['d']:10} {c['n'][:50]:50} arg={int(c['arg'])} P(rev)={c['pRev']:.2f} likeliest {top}-{9 - top}")


if __name__ == '__main__':
    main()
