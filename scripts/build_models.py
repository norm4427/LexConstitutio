"""Build docs/data/models.js: predicted votes of each sitting justice (for the petitioner, i.e. to reverse or vacate,
versus for the respondent, i.e. to affirm) and the distribution of vote splits, for the undecided cases in
docs/data/docket.js, with an honest out-of-sample test.

Design (drawn from the forecasting literature):
  - Katz, Bommarito & Blackman, PLOS ONE 2017: one model over all justices' votes, with each justice's own record
    (reversal, direction and dissent rates from earlier terms) and the lower court's direction against the justice's
    record; refitted term by term so it only ever uses the past.
  - Martin, Quinn, Ruger & Kim, Perspectives on Politics 2004: separate trees per justice; the lower court's
    ideological direction is the first split for most justices.
  - Epstein, Landes & Posner, J. Legal Stud. 2010; Johnson et al. 2009; Feldman, SCOTUSblog 2026: the side asked more
    (and longer) questions at argument tends to lose, more so for some justices than others.
  - Solicitor General: the United States' side wins most cases, especially as amicus (about 75%; SCOTUSblog statistics).
  - Kearney & Merrill, U. Pa. L. Rev. 2000; Collins 2004/2008: amicus briefs by side (a weaker signal).
  - Guimera & Sales-Pardo, PLOS ONE 2011; Feldman 2025: votes in one case are correlated in blocs, so the split
    distribution needs a shared and an ideological component, not independent votes.

Data: Supreme Court Database (scdb_lib.py), orally argued cases with an opinion (decisionType 1, 6, 7) since the 1946
Term in which SCDB codes a winning party. Label: voted for the petitioner = (in the majority and the petitioner won) or
(in the minority and the petitioner lost).

Predictors (every one known before the decision; justice records use earlier terms only):
  case        issue area, lower-court group, coarse petitioner and respondent class (federal / state / local / other),
              jurisdiction, how often the Court sided with petitioners from that lower-court group and overall in the
              previous terms;
  lower-court direction  SCDB's coding of whether the decision under review was liberal or conservative. For pending
              cases (and, in the "pending-case" model, for the test terms) it is estimated by a classifier from the
              question presented, issue area and parties (held-out accuracy reported);
  justice record  share of liberal votes (overall and in the issue area), share of votes for the petitioner (overall
              and in the issue area), all from earlier terms, shrunk toward the Court's average; the justice's lean
              relative to the other justices in the case times the lower court's direction ("ideology x direction"), and
              times the United States' side and the President's party;
  United States  side supported by the United States as party or amicus (argument transcripts and docket pages,
              October Term 2004 on; as a party from SCDB before that), invitation to the Solicitor General (CVSG);
  amicus briefs  number of merits-stage amicus briefs on each side and at the cert stage (docket pages, 2004 on);
  oral argument  the justice's and the whole Court's questioning of each side (words, turns, question marks) in the
              official transcript (build_arguments.py, 2004 on).
Models, for each test term T, fitted only on terms before T:
  pooled  gradient-boosted trees over all justices' votes since 1946 (justice is a predictor, so effects can differ
          by justice);
  own     logistic regression on the justice's own votes;
  blend   the average of the two.
Each sitting justice gets the candidate with the best accuracy on the validation terms 2016-2021 (predicted the same
way, term by term); a justice with no validation votes gets the pooled model. Test terms: 2022-2025 (all cases decided
since Justice Jackson joined), never used for fitting or choosing. Two versions: "SCDB-coded" (uses SCDB's coding of the
decision below and its issue) and "pending-case" (only what a pending case shows; this is the one applied to the docket).
Baselines on the same votes: always the petitioner, the justice's more common vote in earlier terms, the better
constant guess picked with hindsight, and the previous version of these models (logistic regression on the docket
predictors alone).
Vote splits: logit P(justice j votes for the petitioner) = model log-odds + u + v * lean_j, with u ~ N(mu, s_u^2)
shared by all justices (cases where the Court is unanimous) and v ~ N(0, s_v^2) multiplying each justice's lean
(ideological splits); s_u and s_v may depend on case salience (amicus briefs, spread of the justices' questioning).
Fitted by maximum likelihood on the validation terms, compared on the test terms with independent votes, one shared
shift, and the historical split frequencies.
Run from the repo root:  python scripts/build_models.py   (after build_arguments.py and build_case_facts.py)
"""
import json, os, re, sys, time, warnings
os.environ.setdefault("OMP_NUM_THREADS", "6")   # leave CPU for other jobs; oversubscribed OpenMP threads slow boosting badly
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from scipy.sparse import hstack, csr_matrix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scdb_lib import load_votes, justice_ids, site_ids, source_group, load_js, write_js, path, dk_norm, FULL, ISSUE_AREA, SRC
import html

warnings.filterwarnings('ignore')
SEED = 20261114
CURRENT = ['JGRoberts', 'CThomas', 'SAAlito', 'SSotomayor', 'EKagan', 'NMGorsuch', 'BMKavanaugh', 'ACBarrett', 'KBJackson']
VAL = list(range(2016, 2022))
TEST = list(range(2022, 2026))
START = 1946

CASE_CAT = ['issueArea', 'srcGroup', 'petParty', 'resParty', 'jurisdiction']
SCDB_CAT = ['issue', 'lawType', 'caseSource', 'lcDisposition', 'certReason', 'petitioner', 'respondent', 'adminAny', 'threeJudgeFdc', 'lcDisagreement']
NUM = ['term', 'lcLib', 'ideoRev', 'ideoRevArea', 'jLib', 'jLibArea', 'jRev', 'jRevArea', 'jDis', 'usSide', 'usAmicus', 'usKnown', 'usIdeo', 'cvsg',
       'amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL', 'argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ', 'srcRev', 'courtRev']
OLD_NUM = ['term']
GROUPS = {   # feature groups for importance, as shown on the profile
    "Lower court's direction x the justice's lean": ['lcLib', 'ideoRev', 'ideoRevArea'],
    "Justice's record in earlier terms": ['jLib', 'jLibArea', 'jRev', 'jRevArea', 'jDis'],
    'United States position': ['usSide', 'usAmicus', 'usKnown', 'usIdeo', 'cvsg'],
    'Amicus briefs': ['amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL'],
    'Oral argument questioning': ['argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ'],
    'Issue area': ['issueArea'],
    'Lower court': ['srcGroup', 'srcRev'],
    'Parties': ['petParty', 'resParty'],
    'Jurisdiction': ['jurisdiction'],
    'Court trend': ['courtRev', 'term'],
}
SCDB_GROUP = {'SCDB coding (issue, law, disposition below, cert reason, parties)': SCDB_CAT}


# ------------------------------------------------------------- SCDB codes and pending docket features (from v2)
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



# ------------------------------------------------------------- predictors
def pres_dem(term):
    """1 if a Democratic President held office during most of the term (January-June of term + 1)."""
    y = int(term) + 1
    for a, b, v in [(1946, 1953, 1), (1953, 1961, 0), (1961, 1969, 1), (1969, 1977, 0), (1977, 1981, 1), (1981, 1993, 0),
                    (1993, 2001, 1), (2001, 2009, 0), (2009, 2017, 1), (2017, 2021, 0), (2021, 2025, 1), (2025, 2029, 0)]:
        if a <= y < b:
            return v
    return 0


def load_json(p):
    p = path(p)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def arg_feats(rec, surname):
    """Oral argument questioning (build_arguments.py); positive = more aimed at the respondent's side.
    [has transcript, justice words (log ratio), justice turns (difference), justice questions (log ratio),
     all justices' words (log ratio), all justices' questions (log ratio)]"""
    if not rec:
        return [0.0] * 6
    js = {k: v for k, v in rec.items() if not k.startswith('_')}
    own = js.get(surname, [0] * 6)
    own = list(own) + [0] * (6 - len(own))
    tot = [sum((list(v) + [0] * 6)[i] for v in js.values()) for i in range(6)]
    lr = lambda a, b: float(np.log1p(b) - np.log1p(a))
    return [1.0, lr(own[0], own[1]), float(own[3] - own[2]), lr(own[4], own[5]), lr(tot[0], tot[1]), lr(tot[4], tot[5])]


def arg_spread(rec):
    """Spread (standard deviation) of the justices' word log ratios: high when justices pressed different sides."""
    if not rec:
        return 0.0
    xs = [np.log1p(v[1]) - np.log1p(v[0]) for k, v in rec.items() if not k.startswith('_') and v[0] + v[1] >= 50]
    return float(np.std(xs)) if len(xs) >= 3 else 0.0


def us_feats(rec, fct, pet, res, term):
    """[side of the United States (+1 petitioner, -1 respondent, 0 none), as amicus, known (2004 on)]"""
    side = 1 if pet == 'federal' else -1 if res == 'federal' else 0
    amic, known = 0, 0
    if rec and '_us' in rec:
        known = 1
        if rec['_us'][0] >= 0:
            side, amic = (1 if rec['_us'][0] == 0 else -1), int(rec['_us'][1])
    if fct:
        known = 1
        if not amic and fct.get('usAmicus', -1) >= 0 and side == 0:
            side, amic = (1 if fct['usAmicus'] == 0 else -1), 1
    return side, amic, known


def amicus_feats(fct, decided=True):
    if not fct or not (decided or fct.get('resBrief')):
        return [0, 0.0, 0.0, 0.0, 0.0, 0]
    a, b, c = np.log1p(fct['amPet']), np.log1p(fct['amRes']), np.log1p(fct['amCert'])
    return [1, float(a), float(b), float(a - b), float(c), int(fct.get('cvsg', 0))]


def justice_history(d, queries):
    """For (justice, term[, issue area]) queries: the justice's record in all EARLIER terms, shrunk toward the Court.
    Returns dict (j, t) -> (jLib, jRev, jDis) and (j, area, t) -> (jLibArea, jRevArea)."""
    v = d[['justiceName', 'term', 'issueArea', 'direction', 'y', 'majority']].copy()
    v['lib'] = (v.direction == 2).astype(int)
    v['dirn'] = v.direction.isin([1, 2]).astype(int)
    v['dis'] = (v.majority == 1).astype(int)
    v['n'] = 1
    v['area'] = v.issueArea.fillna(-1).astype(int).astype(str)
    g = v.groupby(['justiceName', 'term'])[['lib', 'dirn', 'y', 'dis', 'n']].sum()
    ga = v.groupby(['justiceName', 'area', 'term'])[['lib', 'dirn', 'y', 'n']].sum()
    by_j = {j: (gj.index.get_level_values('term').values, gj.values) for j, gj in g.groupby(level=0)}
    by_ja = {k: (ga_.index.get_level_values('term').values, ga_.values) for k, ga_ in ga.groupby(level=[0, 1])}
    rec, reca = {}, {}
    for j, t, a in queries:
        if (j, t) not in rec:
            if j in by_j:
                ts, vals = by_j[j]
                s = vals[ts < t].sum(axis=0)
            else:
                s = np.zeros(5)
            lib, dirn, yy, dis, n = s
            rec[(j, t)] = ((lib + 20 * 0.5) / (dirn + 20), (yy + 20 * 0.6) / (n + 20), (dis + 20 * 0.12) / (n + 20))
        if (j, a, t) not in reca:
            jl, jr, _ = rec[(j, t)]
            if (j, a) in by_ja:
                ts, vals = by_ja[(j, a)]
                s = vals[ts < t].sum(axis=0)
            else:
                s = np.zeros(4)
            lib, dirn, yy, n = s
            reca[(j, a, t)] = ((lib + 10 * jl) / (dirn + 10), (yy + 10 * jr) / (n + 10))
    return rec, reca


def court_rev_table(d):
    c = d.drop_duplicates('caseId')
    g = c.assign(won=(c.partyWinning == 1).astype(int)).groupby('term').won.agg(['sum', 'count'])
    return {t: float((g[(g.index >= t - 3) & (g.index < t)]['sum'].sum() + 6) / (g[(g.index >= t - 3) & (g.index < t)]['count'].sum() + 10))
            for t in range(int(c.term.min()), int(c.term.max()) + 2)}


def add_justice_features(V, d, lc_col, area_col, out_suffix=''):
    """Justice record + interactions for vote rows V (columns justiceName, term, caseId, area_col, lc_col, usSide)."""
    q = list(zip(V.justiceName, V.term.astype(int), V[area_col]))
    rec, reca = justice_history(d, q)
    r = np.array([rec[(j, t)] for j, t, a in q])
    ra = np.array([reca[(j, a, t)] for j, t, a in q])
    X = pd.DataFrame(index=V.index)
    X['jLib'], X['jRev'], X['jDis'] = r[:, 0], r[:, 1], r[:, 2]
    X['jLibArea'], X['jRevArea'] = ra[:, 0], ra[:, 1]
    lean = X.jLib - X.groupby(V.caseId).jLib.transform('mean')
    leanA = X.jLibArea - X.groupby(V.caseId).jLibArea.transform('mean')
    lc = V[lc_col]
    X['ideoRev'] = 10 * lean * (1 - 2 * lc)
    X['ideoRevArea'] = 10 * leanA * (1 - 2 * lc)
    X['usIdeo'] = V.usSide * np.where(V.term.map(pres_dem) == 1, 1, -1) * 10 * lean
    X['lean'] = lean
    return X


# ------------------------------------------------------------- classifiers for pending cases
def text_model(cats):
    return Pipeline([('p', ColumnTransformer([('t', TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words='english', max_features=40000), 'text'),
                                              ('c', OneHotEncoder(handle_unknown='ignore'), cats)])),
                     ('m', LogisticRegression(C=2, max_iter=2000, solver='liblinear'))])


def issue_estimates(C):
    """Issue area from the question presented (cases with text). Cases before 2022: SCDB issue (training); test-era
    cases: predicted by a classifier fitted before 2022; also returns the classifier fitted on all cases."""
    has = C.text.str.len() > 30
    tr = C[has & (C.term < TEST[0])]
    te = C[has & (C.term >= TEST[0])]
    m = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words='english'), LogisticRegression(C=5, max_iter=1000, solver='liblinear'))
    m.fit(tr.text, tr.issueArea)
    est = C.issueArea.copy()
    if len(te):
        est.loc[te.index] = m.predict(te.text)
    acc = float((est.loc[te.index] == C.issueArea.loc[te.index]).mean()) if len(te) else 0
    base = float((C.issueArea.loc[te.index] == tr.issueArea.mode()[0]).mean()) if len(te) else 0
    full = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words='english'), LogisticRegression(C=5, max_iter=1000, solver='liblinear'))
    full.fit(C[has].text, C[has].issueArea)
    return est, full, {'n': int(has.sum()), 'nTest': int(len(te)), 'acc': round(acc, 4), 'base': round(base, 4)}


def lc_estimates(C):
    """Probability that the decision under review was liberal (SCDB lcDispositionDirection), from the question text,
    issue area, parties, lower court and jurisdiction. Out-of-fold (5 folds) for cases before 2022; test-era cases from
    a model fitted before 2022; plus a model fitted on everything for pending cases."""
    cats = ['issueD', 'petParty', 'resParty', 'srcGroup', 'jurisdiction']
    lab = C.lcDirNum.isin([1, 2])
    y = (C.lcDirNum == 2).astype(int)
    est = pd.Series(0.5, index=C.index)
    pre = C[(C.term < TEST[0])]
    kf = KFold(5, shuffle=True, random_state=SEED)
    idx = pre.index.values
    for a, b in kf.split(idx):
        tr = pre.loc[idx[a]]
        tr = tr[lab.loc[tr.index]]
        m = text_model(cats).fit(tr[['text'] + cats], y.loc[tr.index])
        est.loc[idx[b]] = m.predict_proba(pre.loc[idx[b], ['text'] + cats])[:, 1]
    trp = pre[lab.loc[pre.index]]
    m = text_model(cats).fit(trp[['text'] + cats], y.loc[trp.index])
    post = C[C.term >= TEST[0]]
    if len(post):
        est.loc[post.index] = m.predict_proba(post[['text'] + cats])[:, 1]
    tl = post[lab.loc[post.index]]
    acc = float(((est.loc[tl.index] > 0.5).astype(int) == y.loc[tl.index]).mean()) if len(tl) else 0
    base = float((y.loc[tl.index] == int(round(y.loc[trp.index].mean()))).mean()) if len(tl) else 0
    vl = trp
    acc_val = float(((est.loc[vl.index] > 0.5).astype(int) == y.loc[vl.index]).mean())
    allc = C[lab]
    full = text_model(cats).fit(allc[['text'] + cats], y.loc[allc.index])
    return est, full, {'nTest': int(len(tl)), 'acc': round(acc, 4), 'base': round(base, 4), 'accOof': round(acc_val, 4), 'n': int(len(allc))}


# ------------------------------------------------------------- vote models
def pooled_model(cats, num):
    pre = ColumnTransformer([('c', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan, min_frequency=5, max_categories=250,
                                                  encoded_missing_value=np.nan), cats), ('n', 'passthrough', num)])
    return Pipeline([('p', pre), ('m', HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40,
                                                                       l2_regularization=1.0, random_state=SEED, categorical_features=list(range(len(cats)))))])


def own_model(cats, num, C=0.1):
    pre = ColumnTransformer([('c', OneHotEncoder(handle_unknown='ignore', min_frequency=5), cats), ('n', StandardScaler(), num)])
    return Pipeline([('p', pre), ('m', LogisticRegression(C=C, max_iter=3000, solver='liblinear'))])


def acc_ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    y = np.asarray(y)
    return float(((p > 0.5) == y).mean()), float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def binom_ci(p, n):
    se = (p * (1 - p) / max(n, 1)) ** 0.5
    return [round(max(0, p - 1.96 * se), 4), round(min(1, p + 1.96 * se), 4)]


def verdict_of(acc, ci, best):
    if acc > best + 0.02:
        return 'beats every baseline' if ci[0] > best else 'beats every baseline on this test set, but by less than its margin of error'
    if acc > best + 0.005:
        return 'barely beats the best baseline'
    return 'no better than a baseline'


# ------------------------------------------------------------- vote splits
GH = np.polynomial.hermite_e.hermegauss(12)


def split_probs(lo, lean, s, theta, kind):
    """P(k votes for the petitioner), k = 0..n, for each case. lo, lean: (cases, n); s: (cases, m) salience.
    kind 'indep' | 'shift' | 'two' | 'two+s'. theta: parameter vector."""
    x, w = GH
    w = w / w.sum()
    ncase, n = lo.shape
    if kind == 'indep':
        U = np.zeros((1,)); V = np.zeros((1,)); W = np.ones(1)
        mu, su, sv = 0.0, np.zeros(ncase), np.zeros(ncase)
    else:
        mu = theta[0]
        if kind == 'shift':
            su, sv = np.full(ncase, np.exp(theta[1])), np.zeros(ncase)
        elif kind == 'two':
            su, sv = np.full(ncase, np.exp(theta[1])), np.full(ncase, np.exp(theta[2]))
        else:
            m = s.shape[1]
            su = np.exp(theta[1] + s @ theta[3:3 + m])
            sv = np.exp(theta[2] + s @ theta[3 + m:3 + 2 * m])
        U, V = np.meshgrid(x, x if kind != 'shift' else np.zeros(1), indexing='ij')
        WW = np.outer(w, w if kind != 'shift' else np.ones(1))
        U, V, W = U.ravel(), V.ravel(), WW.ravel()
    # logits: (cases, nodes, n)
    L = lo[:, None, :] + mu + su[:, None, None] * U[None, :, None] + sv[:, None, None] * V[None, :, None] * lean[:, None, :]
    q = 1 / (1 + np.exp(-L))
    pb = np.zeros(q.shape[:2] + (n + 1,))
    pb[..., 0] = 1
    for j in range(n):
        qj = q[..., j:j + 1]
        pb = np.concatenate([pb[..., :1] * (1 - qj), pb[..., 1:] * (1 - qj) + pb[..., :-1] * qj], axis=-1)
    return np.einsum('cnk,n->ck', pb, W)


def split_fit(lo, lean, s, k, kind):
    npar = {'indep': 0, 'shift': 2, 'two': 3, 'two+s': 3 + 2 * s.shape[1]}[kind]
    nll = lambda th: -np.mean(np.log(np.maximum(split_probs(lo, lean, s, th, kind)[np.arange(len(k)), k], 1e-12)))
    if npar == 0:
        return np.zeros(0), nll(np.zeros(0))
    th0 = np.zeros(npar); th0[1] = np.log(2.0)
    if npar > 2:
        th0[2] = np.log(0.5)
    r = minimize(nll, th0, method='L-BFGS-B', bounds=[(-3, 3), (-3, 2.5)] + [(-4, 2.5)] * (npar > 2) + [(-2, 2)] * max(0, npar - 3))
    return r.x, r.fun


def build_frames():
    d = load_votes()
    d = d[d.decisionType.isin(FULL) & d.partyWinning.isin([0, 1]) & d.majority.isin([1, 2]) & (d.term >= START)].copy()
    d['date'] = pd.to_datetime(d.dateDecision, format='%m/%d/%Y', errors='coerce')
    d['y'] = (((d.majority == 2) & (d.partyWinning == 1)) | ((d.majority == 1) & (d.partyWinning == 0))).astype(int)
    d['term'] = d.term.astype(int)
    code2id, jinfo = justice_ids()
    surname = {c: re.sub(r'[^A-Z]', '', jinfo[j]['last'].upper().replace('’', "'")) for c, j in code2id.items() if j in jinfo}
    ARG = load_json('data/raw/transcripts/features.json')
    FCT = load_json('data/raw/docket/facts.json')
    srev = src_rev_table(d)
    crev = court_rev_table(d)
    # ---- case table
    C = d.drop_duplicates('caseId').set_index('caseId')
    X0 = prep(C)
    C['lcDirNum'] = C.lcDispositionDirection
    for c in X0.columns:
        if c != 'term':
            C[c] = X0[c]
    sid = site_ids(d)
    S = {c['id']: (c.get('q') or '') + ' ' + (c.get('ds') or '') for c in load_js('scotus')['cases']}
    C['text'] = [S.get(sid.get(cid, ''), '') for cid in C.index]
    C['issueArea'] = X0.issueArea
    C['dk'] = [dk_norm(k) if isinstance(k, str) else '' for k in C.docket]
    C['argKey'] = [f'{t}/{k}' for t, k in zip(C.term, C.dk)]
    C['lcLib'] = np.where(C.lcDirNum == 2, 1.0, np.where(C.lcDirNum == 1, 0.0, 0.5))
    C['srcRev'] = [srev.get((t, g), 0.6) for t, g in zip(C.term, C.srcGroup)]
    C['courtRev'] = [crev.get(t, 0.6) for t in C.term]
    us = [us_feats(ARG.get(a), FCT.get(k), p, r, t) for a, k, p, r, t in zip(C.argKey, C.dk, C.petParty, C.resParty, C.term)]
    C['usSide'], C['usAmicus'], C['usKnown'] = zip(*us)
    am = np.array([amicus_feats(FCT.get(k)) for k in C.dk])
    for i, c in enumerate(['amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL', 'cvsg']):
        C[c] = am[:, i]
    C['argSpread'] = [arg_spread(ARG.get(a)) for a in C.argKey]
    t0 = time.time()
    C['issueD'], issue_full, issue_eval = issue_estimates(C)
    C['lcLibD'], lc_full, lc_eval = lc_estimates(C)
    print('issue classifier', issue_eval, '| lower-court direction classifier', lc_eval, f'{time.time() - t0:.0f}s', flush=True)
    return d, C, ARG, FCT, srev, crev, surname, code2id, issue_full, lc_full, issue_eval, lc_eval


def vote_rows(d, C, ARG, surname):
    V = d[['caseId', 'justiceName', 'term', 'y', 'date']].copy()
    for c in ['issueArea', 'issueD', 'srcGroup', 'petParty', 'resParty', 'jurisdiction', 'lcLib', 'lcLibD', 'srcRev', 'courtRev', 'usSide', 'usAmicus',
              'usKnown', 'amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL', 'cvsg', 'argKey', 'argSpread'] + SCDB_CAT:
        V[c] = C.loc[V.caseId, c].values
    af = np.array([arg_feats(ARG.get(k), surname.get(j, '')) for k, j in zip(V.argKey, V.justiceName)])
    for i, c in enumerate(['argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ']):
        V[c] = af[:, i]
    V['justice'] = V.justiceName
    return V


def design(V, d, ver):
    """Feature frame for version 'full' (SCDB-coded issue and lower-court direction) or 'dock' (what a pending case shows)."""
    lc, area = ('lcLib', 'issueArea') if ver == 'full' else ('lcLibD', 'issueD')
    J = add_justice_features(V, d, lc, area)
    X = pd.DataFrame(index=V.index)
    X['justice'] = V.justice
    X['issueArea'] = V[area]
    for c in ['srcGroup', 'petParty', 'resParty', 'jurisdiction'] + SCDB_CAT:
        X[c] = V[c]
    X['lcLib'] = V[lc]
    for c in J.columns:
        X[c] = J[c]
    for c in NUM:
        if c not in X.columns:
            X[c] = V[c].astype(float)
    return X


def cols_for(ver):
    cats = CASE_CAT + (SCDB_CAT if ver == 'full' else [])
    return cats, NUM


def grouped_importance(model, X, y, groups, cols, reps=10):
    rng = np.random.default_rng(SEED)
    base_acc, base_ll = acc_ll(model.predict_proba(X[cols])[:, 1], y)
    out = []
    for g, cs in groups.items():
        cs = [c for c in cs if c in cols]
        if not cs:
            continue
        da, dl = [], []
        for _ in range(reps):
            Xp = X[cols].copy()
            perm = rng.permutation(len(Xp))
            for c in cs:
                Xp[c] = Xp[c].values[perm]
            a, l = acc_ll(model.predict_proba(Xp)[:, 1], y)
            da.append(base_acc - a); dl.append(l - base_ll)
        out.append([g, round(float(np.mean(da)) * 100, 2), round(float(np.mean(dl)) / base_ll * 100, 2)])
    return sorted(out, key=lambda r: -r[2])


def main():
    t0 = time.time()
    d, C, ARG, FCT, srev, crev, surname, code2id, issue_full, lc_full, issue_eval, lc_eval = build_frames()
    V = vote_rows(d, C, ARG, surname)
    XS = {ver: design(V, d, ver) for ver in ('full', 'dock')}
    print(f'{len(V)} votes in {V.caseId.nunique()} cases; features built {time.time() - t0:.0f}s', flush=True)
    y = V.y.values
    pred = {ver: {k: pd.Series(np.nan, index=V.index) for k in ('pooled', 'own', 'blend', 'old')} for ver in ('full', 'dock')}
    keep = {}
    for T in VAL + TEST:
        tr = V.term < T
        te = (V.term == T).values
        for ver in ('full', 'dock'):
            cats, num = cols_for(ver)
            X = XS[ver]
            cols = ['justice'] + cats + num
            pm = pooled_model(['justice'] + cats, num).fit(X.loc[tr, cols], y[tr.values])
            pred[ver]['pooled'][te] = pm.predict_proba(X.loc[te, cols])[:, 1]
            if T == TEST[0]:
                keep[(ver, 'pooled')] = pm
            for code in CURRENT:
                mj = (V.justiceName == code).values
                trj, tej = tr.values & mj, te & mj
                if tej.sum() == 0:
                    continue
                if trj.sum() >= 60:
                    om = own_model(cats, num).fit(X.loc[trj, cats + num], y[trj])
                    pred[ver]['own'][tej] = om.predict_proba(X.loc[tej, cats + num])[:, 1]
                    if T == TEST[0]:
                        keep[(ver, 'own', code)] = om
                    if ver == 'dock':
                        oc = ['issueD', 'srcGroup', 'petParty', 'resParty', 'jurisdiction']
                        Xo = V.loc[:, oc + ['term', 'argHas', 'argW', 'argT', 'argCourt', 'srcRev']].copy()
                        old = own_model(oc, ['term', 'argHas', 'argW', 'argT', 'argCourt', 'srcRev']).fit(Xo.loc[trj], y[trj])
                        pred[ver]['old'][tej] = old.predict_proba(Xo.loc[tej])[:, 1]
                else:
                    pred[ver]['own'][tej] = pred[ver]['pooled'][tej]
                pred[ver]['blend'][tej] = (pred[ver]['own'][tej].values + pred[ver]['pooled'][tej].values) / 2
        print(f'  term {T} done {time.time() - t0:.0f}s', flush=True)

    # ---- choose per justice on validation terms, report on test terms
    out, choice = {}, {}
    val = V.term.isin(VAL).values
    tst = V.term.isin(TEST).values
    for code in CURRENT:
        mj = (V.justiceName == code).values
        jid = code2id[code]
        r = {'code': code}
        for ver in ('dock', 'full'):
            vs = {}
            for k in ('pooled', 'own', 'blend'):
                m = val & mj & pred[ver][k].notna().values
                if m.sum() >= 40:
                    vs[k] = acc_ll(pred[ver][k][m], y[m])
            best = max(vs, key=lambda k: (round(vs[k][0], 3), -vs[k][1])) if vs else 'pooled'
            choice[(ver, code)] = best
            mt = tst & mj
            yt = y[mt]
            res = {k: acc_ll(pred[ver][k][mt], yt) for k in ('pooled', 'own', 'blend')}
            acc, ll = res[best]
            r[ver] = {'choice': best, 'acc': round(acc, 4), 'll': round(ll, 4), 'ci': binom_ci(acc, mt.sum()),
                      'val': {k: [round(a, 4), round(l, 4)] for k, (a, l) in vs.items()}, 'nVal': int((val & mj).sum()),
                      'all': {k: round(a, 4) for k, (a, l) in res.items()}}
            if ver == 'dock':
                r['old'] = round(acc_ll(pred['dock']['old'][mt], yt)[0], 4) if pred['dock']['old'][mt].notna().all() else None
        mt = tst & mj
        yt = y[mt]
        prior = (V.justiceName == code) & (V.term < TEST[0])
        maj_cls = int(round(V.y[prior].mean())) if prior.sum() else 1
        base = {'majority': round(float((yt == maj_cls).mean()), 4), 'majorityLabel': 'petitioner' if maj_cls else 'respondent',
                'reverse': round(float(yt.mean()), 4), 'hindsight': round(float(max(yt.mean(), 1 - yt.mean())), 4)}
        best_base = max(base['majority'], base['reverse'], base['hindsight'])
        r.update({'n': int(mj.sum()), 'nTest': int(mt.sum()), 'base': base,
                  'testSpan': [str(V.date[mt].min().date()), str(V.date[mt].max().date())],
                  'verdict': verdict_of(r['dock']['acc'], r['dock']['ci'], best_base),
                  'fverdict': verdict_of(r['full']['acc'], r['full']['ci'], best_base)})
        # what matters for this justice: grouped permutation importance of the term-2022 model on the test votes
        ver = 'dock'
        cats, num = cols_for(ver)
        mdl = keep.get((ver, 'own', code)) if choice[(ver, code)] == 'own' and (ver, 'own', code) in keep else keep[(ver, 'pooled')]
        cols = (cats + num) if mdl is not keep[(ver, 'pooled')] else ['justice'] + cats + num
        r['imp'] = grouped_importance(mdl, XS[ver].loc[mt], yt, GROUPS, cols)
        import model_directions as MD      # hover notes: what each group measures, which way it moves this justice
        r['dir'] = MD.directions(V, code, surname.get(code, code).title())
        out[jid] = r
        print(f"{code:12} test={mt.sum():4} base={best_base:.3f} | pending-case model [{r['dock']['choice']:6}] {r['dock']['acc']:.3f} "
              f"(pooled {r['dock']['all']['pooled']:.3f} own {r['dock']['all']['own']:.3f} blend {r['dock']['all']['blend']:.3f}; previous {r['old']}) "
              f"| SCDB-coded [{r['full']['choice']:6}] {r['full']['acc']:.3f} -> {r['verdict']}", flush=True)
        print('    matters most:', r['imp'][:4], flush=True)

    # ---- case-level winner accuracy and vote-split model (pending-case version)
    pj = pd.Series(np.nan, index=V.index)
    for code in CURRENT:
        mj = (V.justiceName == code).values
        pj[mj] = pred['dock'][choice[('dock', code)]][mj]
    other = pj.isna() & V.term.isin(VAL + TEST)
    pj[other] = pred['dock']['pooled'][other]
    XL = XS['dock']
    W = V.assign(p=pj.values, lean=XL['lean'].values)[V.term.isin(VAL + TEST)]
    W = W[W.p.notna()]
    g = W.groupby('caseId')
    nine = g.size()
    cases = nine[nine == 9].index
    W9 = W[W.caseId.isin(cases)].sort_values(['caseId', 'justiceName'])
    lo = np.log(np.clip(W9.p.values, 1e-4, 1 - 1e-4) / (1 - np.clip(W9.p.values, 1e-4, 1 - 1e-4))).reshape(-1, 9)
    ln = W9.lean.values.reshape(-1, 9)
    ln = ln / np.std(ln)
    lean_sd = float(np.std(W9.lean.values))
    kk = W9.y.values.reshape(-1, 9).sum(1)
    cid = W9.caseId.values.reshape(-1, 9)[:, 0]
    terms = C.loc[cid, 'term'].values
    amt = np.log1p(np.expm1(C.loc[cid, 'amPetL'].values) + np.expm1(C.loc[cid, 'amResL'].values))
    spread = C.loc[cid, 'argSpread'].values
    sal_mu = [float(amt[C.loc[cid, 'amKnown'].values == 1].mean()), float(spread[spread > 0].mean())]
    sal_sd = [float(amt[C.loc[cid, 'amKnown'].values == 1].std()), float(spread[spread > 0].std())]
    S = np.c_[np.where(C.loc[cid, 'amKnown'].values == 1, (amt - sal_mu[0]) / sal_sd[0], 0), np.where(spread > 0, (spread - sal_mu[1]) / sal_sd[1], 0)]
    iv = np.isin(terms, VAL); it = np.isin(terms, TEST)
    emp = (np.bincount(kk[iv], minlength=10) + 0.5) / (iv.sum() + 5)
    kinds = ['indep', 'shift', 'two', 'two+s']
    # choose the form by 2-fold cross-validation over the validation terms
    h1, h2 = np.isin(terms, VAL[:3]), np.isin(terms, VAL[3:])
    cvll = {}
    for kd in kinds:
        tot = 0
        for a, b in ((h1, h2), (h2, h1)):
            th, _ = split_fit(lo[a], ln[a], S[a], kk[a], kd)
            pr = split_probs(lo[b], ln[b], S[b], th, kd)
            tot += np.mean(np.log(np.maximum(pr[np.arange(b.sum()), kk[b]], 1e-12))) / 2
        cvll[kd] = round(float(tot), 4)
    best_kind = max(cvll, key=cvll.get)
    fits = {kd: split_fit(lo[iv], ln[iv], S[iv], kk[iv], kd)[0] for kd in kinds}
    test_ll = {}
    for kd in kinds:
        pr = split_probs(lo[it], ln[it], S[it], fits[kd], kd)
        test_ll[kd] = round(float(np.mean(np.log(np.maximum(pr[np.arange(it.sum()), kk[it]], 1e-12)))), 4)
    test_ll['historical frequencies'] = round(float(np.mean(np.log(emp[kk[it]]))), 4)
    prt = split_probs(lo[it], ln[it], S[it], fits[best_kind], best_kind)
    win_hit = float(((prt[:, 5:].sum(1) >= 0.5) == (kk[it] >= 5)).mean())
    rev_base = float(max((kk[it] >= 5).mean(), (kk[it] < 5).mean()))
    unan_pred = float((prt[:, 0] + prt[:, 9]).mean())
    unan_act = float(((kk[it] == 0) | (kk[it] == 9)).mean())
    # cases where the model is confident
    conf = np.abs(prt[:, 5:].sum(1) - 0.5) >= 0.25
    calib = {'kind': best_kind, 'theta': [round(float(x), 4) for x in fits[best_kind]], 'cv': cvll, 'test': test_ll,
             'nVal': int(iv.sum()), 'nTest': int(it.sum()), 'emp': [round(float(x), 4) for x in emp],
             'hit': round(win_hit, 4), 'revBase': round(rev_base, 4), 'unanPred': round(unan_pred, 4), 'unanAct': round(unan_act, 4),
             'confN': int(conf.sum()), 'confHit': round(float(((prt[conf, 5:].sum(1) >= 0.5) == (kk[it][conf] >= 5)).mean()), 4) if conf.any() else None,
             'testDist': [round(float(x), 4) for x in prt.mean(0)], 'testEmp': [round(float(x), 4) for x in np.bincount(kk[it], minlength=10) / it.sum()],
             'salience': {'mu': sal_mu, 'sd': sal_sd}, 'leanSd': lean_sd}
    print('splits: cv', cvll, '| test', test_ll, '| chosen', best_kind, fits[best_kind], flush=True)
    print(f'  winner hit {win_hit:.3f} vs always-majority-side {rev_base:.3f}; predicted unanimity {unan_pred:.3f} vs actual {unan_act:.3f}; confident cases {conf.sum()} hit {calib["confHit"]}', flush=True)

    # ---- pending cases: refit on everything and predict
    K = load_js('docket')
    pend, seen = [], set()
    for c in K['cases']:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        if not c.get('n'):
            c = dict(c, n='No. ' + c['d'])
        f, ok = docket_features(c)
        text = (c.get('q') or '') + ' ' + (c.get('ds') or '')
        pr_issue = issue_full.predict_proba([text])[0]
        f['issueD'] = int(issue_full.classes_[pr_issue.argmax()])
        f['issueP'] = round(float(pr_issue.max()), 3)
        f['term'] = int(c.get('t') or K.get('term') or 2026)
        f['text'] = text
        trn = (c.get('tr') or '').rsplit('/', 1)[-1][:-4]
        f['argKey'] = f"{f['term']}/{re.sub(r'_[a-z0-9]+$', '', trn).lower()}" if trn else ''
        f['dk'] = c['d'].lower()
        f['ok'] = ok
        f['c'] = c
        pend.append(f)
    P = pd.DataFrame(pend)
    P['issueD'] = P.issueD.astype(str)
    P['lcLibD'] = lc_full.predict_proba(P[['text', 'issueD', 'petParty', 'resParty', 'srcGroup', 'jurisdiction']])[:, 1]
    P['srcRev'] = [srev.get((t, g), 0.6) for t, g in zip(P.term, P.srcGroup)]
    P['courtRev'] = [crev.get(t, crev[max(crev)]) for t in P.term]
    us = [us_feats(ARG.get(a), FCT.get(k), p, r, t) for a, k, p, r, t in zip(P.argKey, P.dk, P.petParty, P.resParty, P.term)]
    P['usSide'], P['usAmicus'], P['usKnown'] = zip(*us)
    am = np.array([amicus_feats(FCT.get(k), decided=False) for k in P.dk])
    for i, c in enumerate(['amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL', 'cvsg']):
        P[c] = am[:, i]
    P['cvsg'] = [int((FCT.get(k) or {}).get('cvsg', 0)) for k in P.dk]
    P['argSpread'] = [arg_spread(ARG.get(a)) for a in P.argKey]
    P['caseId'] = P.dk
    rows = []
    for _, r in P.iterrows():
        for code in CURRENT:
            rr = r.to_dict()
            rr['justiceName'] = rr['justice'] = code
            rows.append(rr)
    PV = pd.DataFrame(rows)
    af = np.array([arg_feats(ARG.get(k), surname.get(j, '')) for k, j in zip(PV.argKey, PV.justiceName)])
    for i, c in enumerate(['argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ']):
        PV[c] = af[:, i]
    J = add_justice_features(PV.assign(lcLib=PV.lcLibD), d, 'lcLibD', 'issueD')
    XP = pd.DataFrame(index=PV.index)
    XP['justice'] = PV.justice
    XP['issueArea'] = PV.issueD
    for c in ['srcGroup', 'petParty', 'resParty', 'jurisdiction']:
        XP[c] = PV[c]
    XP['lcLib'] = PV.lcLibD
    for c in J.columns:
        XP[c] = J[c]
    for c in NUM:
        if c not in XP.columns:
            XP[c] = PV[c].astype(float)
    cats, num = cols_for('dock')
    X = XS['dock']
    pm = pooled_model(['justice'] + cats, num).fit(X[['justice'] + cats + num], y)
    pp = pm.predict_proba(XP[['justice'] + cats + num])[:, 1]
    final = np.array(pp)
    for code in CURRENT:
        mj = (V.justiceName == code).values
        mp = (PV.justiceName == code).values
        ch = choice[('dock', code)]
        if ch in ('own', 'blend') and mj.sum() >= 60:
            om = own_model(cats, num).fit(X.loc[mj, cats + num], y[mj])
            po = om.predict_proba(XP.loc[mp, cats + num])[:, 1]
            final[mp] = po if ch == 'own' else (po + pp[mp]) / 2
    PV['p'] = final
    for jid_code in CURRENT:
        out[code2id[jid_code]]['pred'] = [[cid, round(float(p), 3)] for cid, p in zip(PV.loc[PV.justiceName == jid_code, 'c'].map(lambda c: c['id']), PV.loc[PV.justiceName == jid_code, 'p'])]
    leanP = PV['lean'] if 'lean' in PV else J['lean']
    cases_out = []
    for i, r in P.iterrows():
        m = (PV.caseId == r.caseId).values
        sub = PV[m].set_index('justiceName').loc[CURRENT]
        lo_c = np.log(np.clip(sub.p.values, 1e-4, 1 - 1e-4) / (1 - np.clip(sub.p.values, 1e-4, 1 - 1e-4)))[None, :]
        ln_c = (J.loc[PV.index[m], 'lean'].values / lean_sd)[None, :]
        amt_c = np.log1p(np.expm1(r.amPetL) + np.expm1(r.amResL))
        S_c = np.array([[(amt_c - sal_mu[0]) / sal_sd[0] if r.amKnown else 0, (r.argSpread - sal_mu[1]) / sal_sd[1] if r.argSpread > 0 else 0]])
        dist = split_probs(lo_c, ln_c, S_c, fits[best_kind], best_kind)[0]
        c = r.c
        cases_out.append({'id': c['id'], 'n': c['n'], 'd': c['d'], 'lowerCourt': r.lowerCourt, 'src': r.srcGroup, 'pet': r.petParty, 'res': r.resParty,
                          'jur': r.jurisdiction, 'area': ISSUE_AREA.get(int(r.issueD), ''), 'areaP': r.issueP, 'page': bool(r.ok),
                          'lcLib': round(float(r.lcLibD), 3), 'us': int(r.usSide), 'usAmicus': int(r.usAmicus), 'cvsg': int(r.cvsg),
                          'am': [int(round(np.expm1(r.amPetL))), int(round(np.expm1(r.amResL))), int(round(np.expm1(r.amCertL)))] if r.amKnown else None,
                          'arg': bool(r.argKey and r.argKey in ARG), 'argCourt': round(float(sub.argCourt.iloc[0]), 3),
                          'dist': [round(float(x), 4) for x in dist], 'pRev': round(float(dist[5:].sum()), 4)})
    data = {'src': SRC, 'generated': pd.Timestamp.now().strftime('%Y-%m-%d'), 'version': 3, 'issueClf': issue_eval, 'lcClf': lc_eval,
            'val': [VAL[0], VAL[-1]], 'test': [TEST[0], TEST[-1]], 'calib': calib, 'order': [code2id[c] for c in CURRENT],
            'nArg': int(len(ARG)), 'nFacts': int(len(FCT)), 'j': out, 'cases': cases_out}
    kb = write_js('models', 'MODELS', data) / 1024
    print(f'models.js {kb:.0f} KB; {len(cases_out)} pending cases; {time.time() - t0:.0f}s')
    for c in cases_out:
        top = int(np.argmax(c['dist']))
        print(f"  {c['d']:10} {c['n'][:44]:44} arg={int(c['arg'])} lcLib={c['lcLib']:.2f} us={c['us']:+d} P(rev)={c['pRev']:.2f} likeliest {top}-{9 - top} ({max(c['dist']):.2f})")


if __name__ == '__main__':
    main()
