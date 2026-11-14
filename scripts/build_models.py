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
import html, os, re, warnings
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from scdb_lib import load_votes, justice_ids, site_ids, source_group, load_js, write_js, path, FULL, ISSUE_AREA, SRC

warnings.filterwarnings('ignore')
SEED = 20261114
CURRENT = ['JGRoberts', 'CThomas', 'SAAlito', 'SSotomayor', 'EKagan', 'NMGorsuch', 'BMKavanaugh', 'ACBarrett', 'KBJackson']
LABELS = {'issueArea': 'Issue area', 'issue': 'Specific issue', 'lawType': 'Type of law', 'srcGroup': 'Lower court (group)',
          'caseSource': 'Lower court', 'originGroup': 'Court of origin (group)', 'lcDisposition': 'Lower-court disposition',
          'lcDispositionDirection': 'Lower-court direction', 'certReason': 'Reason cert was granted', 'jurisdiction': 'Jurisdiction',
          'petParty': 'Petitioner class', 'resParty': 'Respondent class', 'petitioner': 'Petitioner type', 'respondent': 'Respondent type',
          'adminAny': 'Agency action under review', 'threeJudgeFdc': 'Three-judge district court', 'lcDisagreement': 'Dissent below',
          'term': 'Term'}
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


def candidates(cat):
    onehot = lambda: ColumnTransformer([('c', OneHotEncoder(handle_unknown='ignore', min_frequency=5), cat),
                                        ('n', StandardScaler(), ['term'])])
    ordinal = lambda: ColumnTransformer([('c', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan,
                                                              min_frequency=5, encoded_missing_value=np.nan), cat),
                                         ('n', 'passthrough', ['term'])])
    out = {f'logistic (C={C})': Pipeline([('p', onehot()), ('m', LogisticRegression(C=C, max_iter=3000, solver='liblinear'))]) for C in (0.03, 0.1, 0.3, 1.0)}
    out['gradient-boosted trees'] = Pipeline([('p', ordinal()), ('m', HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=1.0, random_state=SEED,
        categorical_features=list(range(len(cat)))))])
    return out


def fit_eval(Xtr, ytr, Xte, yte, cat):
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    best, best_s, cvs = None, -1, {}
    for name, m in candidates(cat).items():
        s = cross_val_score(m, Xtr[cat + ['term']], ytr, cv=cv, scoring='accuracy').mean()
        cvs[name] = round(float(s), 4)
        if s > best_s:
            best, best_s = name, s
    m = candidates(cat)[best].fit(Xtr[cat + ['term']], ytr)
    acc = float((m.predict(Xte[cat + ['term']]) == yte).mean())
    pi = permutation_importance(m, Xte[cat + ['term']], yte, n_repeats=10, random_state=SEED, scoring='accuracy')
    imp = sorted([[LABELS[c], round(float(pi.importances_mean[i]) * 100, 2)] for i, c in enumerate(cat + ['term'])], key=lambda r: -r[1])
    return best, round(float(best_s), 4), cvs, round(acc, 4), imp, m


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


def main():
    d = load_votes()
    d = d[d.decisionType.isin(FULL) & d.partyWinning.isin([0, 1]) & d.majority.isin([1, 2])].copy()
    d['date'] = pd.to_datetime(d.dateDecision, format='%m/%d/%Y', errors='coerce')   # SCDB dates are m/d/yyyy strings
    d['y'] = (((d.majority == 2) & (d.partyWinning == 1)) | ((d.majority == 1) & (d.partyWinning == 0))).astype(int)
    X = prep(d)
    code2id, jinfo = justice_ids()
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
        pending.append((c, f, ok))
    P = pd.DataFrame([f for _, f, _ in pending])

    out = {}
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
        db, dcv, dcvs, dacc, dimp, _ = fit_eval(Xtr, ytr, Xte, yte, DOCKET_CAT)
        base_hind = max(base_rev, 1 - base_rev)   # the better constant guess, chosen with hindsight on the test set
        best_base = max(base_major, base_rev, base_hind)
        verdict = verdict_of(facc, binom_ci(facc, nte), best_base)
        final = candidates(DOCKET_CAT)[db].fit(Xj[DOCKET_CAT + ['term']], y)
        pr = final.predict_proba(P[DOCKET_CAT + ['term']])[:, 1] if len(P) else []
        jid = code2id[code]
        out[jid] = {
            'code': code, 'n': int(len(dj)), 'nTrain': int(len(ytr)), 'nTest': int(nte),
            'trainSpan': [dj.date.iloc[0].strftime('%Y-%m-%d'), dj.date.iloc[-nte - 1].strftime('%Y-%m-%d')],
            'testSpan': [dj.date.iloc[-nte].strftime('%Y-%m-%d'), dj.date.iloc[-1].strftime('%Y-%m-%d')],
            'revRateTrain': round(float(ytr.mean()), 4),
            'base': {'majority': round(base_major, 4), 'majorityLabel': 'petitioner' if maj_cls else 'respondent', 'reverse': round(base_rev, 4), 'hindsight': round(base_hind, 4)},
            'dverdict': verdict_of(dacc, binom_ci(dacc, nte), best_base),
            'full': {'model': fb, 'cv': fcv, 'cvAll': fcvs, 'acc': facc, 'ci': binom_ci(facc, nte), 'imp': fimp[:8]},
            'docket': {'model': db, 'cv': dcv, 'cvAll': dcvs, 'acc': dacc, 'ci': binom_ci(dacc, nte), 'imp': dimp[:6]},
            'verdict': verdict,
            'pred': [[c['id'], round(float(p), 3)] for (c, _, _), p in zip(pending, pr)],
        }
        print(f"{code:12} n={len(dj):5} test={nte:4} base maj={base_major:.3f} rev={base_rev:.3f} hind={base_hind:.3f} | full {fb:24} cv={fcv:.3f} test={facc:.3f} | docket {db:24} test={dacc:.3f} -> {verdict}", flush=True)
        print('   top:', fimp[:4])
    # Court-level prediction for each pending case: the majority of the nine predicted votes
    cases = []
    for k, (c, f, ok) in enumerate(pending):
        ps = [out[j]['pred'][k][1] for j in out]
        nrev = sum(p >= 0.5 for p in ps)
        cases.append({'id': c['id'], 'n': c['n'], 'd': c['d'], 'lowerCourt': f['lowerCourt'], 'src': f['srcGroup'],
                      'pet': f['petParty'], 'res': f['resParty'], 'jur': f['jurisdiction'], 'area': ISSUE_AREA.get(int(f['issueArea']), ''),
                      'areaP': f['issueP'], 'page': ok, 'rev': nrev, 'aff': len(ps) - nrev})
    data = {'src': SRC, 'generated': pd.Timestamp.now().strftime('%Y-%m-%d'), 'issueClf': clf_eval, 'labels': LABELS,
            'j': out, 'cases': cases}
    kb = write_js('models', 'MODELS', data) / 1024
    print(f'models.js {kb:.0f} KB; {len(cases)} pending cases')
    for c in cases:
        print(f"  {c['d']:10} {c['n'][:55]:55} {c['src']:16} pet={c['pet']:8} res={c['res']:8} {c['area']:20} -> {c['rev']}-{c['aff']} reverse")


if __name__ == '__main__':
    main()
