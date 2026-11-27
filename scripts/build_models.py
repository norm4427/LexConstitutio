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
  oral argument  the justice's and the whole Court's questioning of each side (words, turns, question marks), the
              justice's and the Court's interruptions of counsel for each side, and who asked each side's first and
              last question, in the official transcript (build_arguments.py, 2004 on; Epstein, Landes & Posner 2010;
              Jacobi & Rozema 2018);
  ideology    the justice's Martin-Quinn score from the previous term (2021 release, the latest; imputed from the
              liberal-vote share where missing), relative to the other justices, and times the direction below.
Models, for each test term T, fitted only on terms before T:
  pooled  gradient-boosted trees over all justices' votes since 1946 (justice is a predictor, so effects can differ
          by justice);
  rf      a random forest over all justices' votes since 1986;
  ens     the average of the two: used for every justice;
  own     logistic regression on the justice's own votes; blend = average of pooled and own (shown for comparison).
The predictors and the model were chosen on the validation terms 2016-2021 (predicted the same way, term by term) by the
log loss of all justices' votes: the ensemble beat boosted trees, the random forest, regularized logistic regression
and a per-justice choice of model; interruptions/first-last questions and Martin-Quinn scores lowered it, together.
Test terms: 2022-2025 (all cases decided
since Justice Jackson joined), never used for fitting or choosing. Two versions: "SCDB-coded" (uses SCDB's coding of the
decision below and its issue) and "pending-case" (only what a pending case shows; this is the one applied to the docket).
Baselines on the same votes: always the petitioner, the justice's more common vote in earlier terms, the better
constant guess picked with hindsight, and the previous version of these models (logistic regression on the docket
predictors alone).
Combining the nine predictions (vote splits). Forecasters who predict each justice (Martin, Quinn, Ruger & Kim; Katz et
al.; FantasySCOTUS) call the case by the majority of the predicted votes; counting the justices above 50% as a split
would make most cases 6-3 on an ideologically sorted Court, and treating the votes as independent almost never yields
a unanimous decision (Guimera & Sales-Pardo 2011; Lee, Broedersz & Bialek 2015: the votes are strongly correlated and
unanimity is the commonest outcome). So:
  margins          the probability shown for each justice is that justice's own model; a recalibration (Platt, or the
                   Court-wide lean and the justice's difference from it scaled separately) is used only if it improves
                   the individual votes' log loss in 2-fold cross-validation over the validation terms without costing
                   accuracy;
  joint model      a mixture whose every component keeps those margins exactly: unanimous for the petitioner (weight
                   w+), unanimous for the respondent (w-), or contested, where votes follow a latent Court-wide factor
                   and a factor weighted by each justice's lean with margins m_j = (p_j - w+) / (1 - w+ - w-). The
                   unanimity weights are a share of their largest possible values (w+ <= min p_j, w- <= min (1 - p_j));
                   the share and the factor scales are fitted on the validation terms to the likelihood of the actual
                   split, the form (share constant or depending on the case) chosen by cross-validation;
  headline         the single most probable split, shown with its probability and each side's chance of winning;
  tested           on the test terms against the previous version (consensus/contested mixture with shrunk margins), the
                   margins with two factors but no unanimity part, independent votes and the historical split
                   frequencies: individual votes, winning side, probability of the actual split, P(unanimous)
                   calibration and the distribution of the likeliest split; check_splits() stops the build if any split
                   contradicts the probabilities shown (P(9-0 reverse) <= min P(reverse), P(9-0 affirm) <= min
                   P(affirm), expected votes = their sum).
Run from the repo root:  python scripts/build_models.py   (after build_arguments.py and build_case_facts.py)
"""
import json, os, pickle, re, sys, time, warnings
os.environ.setdefault("OMP_NUM_THREADS", "6")   # leave CPU for other jobs; oversubscribed OpenMP threads slow boosting badly
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
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
STAGE = path('data/raw/models_stage.pkl')   # cache of the per-justice predictions (written by every full build)
REUSE = '--reuse' in sys.argv

CASE_CAT = ['issueArea', 'srcGroup', 'petParty', 'resParty', 'jurisdiction']
SCDB_CAT = ['issue', 'lawType', 'caseSource', 'lcDisposition', 'certReason', 'petitioner', 'respondent', 'adminAny', 'threeJudgeFdc', 'lcDisagreement']
NUM = ['term', 'lcLib', 'ideoRev', 'ideoRevArea', 'jLib', 'jLibArea', 'jRev', 'jRevArea', 'jDis', 'usSide', 'usAmicus', 'usKnown', 'usIdeo', 'cvsg',
       'amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL', 'argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ', 'srcRev', 'courtRev']
ARG_EXTRA = ['argInt', 'argFirst', 'argLast', 'argCourtInt']   # interruptions, first and last question by side (build_arguments.py)
MQ_NUM = ['mqRel', 'mqDir']                                    # Martin-Quinn score relative to the Court, x direction below
ARG_COLS = ['argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ'] + ARG_EXTRA
NUM = NUM + ARG_EXTRA + MQ_NUM       # chosen on the validation terms (log loss of all justices' votes), not on the test terms
RF_START = 1986                      # the random forest is fitted on the votes of the last ~30+ terms (speed)
OLD_NUM = ['term']
GROUPS = {   # feature groups for importance, as shown on the profile
    "Lower court's direction x the justice's lean": ['lcLib', 'ideoRev', 'ideoRevArea'],
    "Justice's record in earlier terms": ['jLib', 'jLibArea', 'jRev', 'jRevArea', 'jDis'],
    'United States position': ['usSide', 'usAmicus', 'usKnown', 'usIdeo', 'cvsg'],
    'Amicus briefs': ['amKnown', 'amPetL', 'amResL', 'amDiff', 'amCertL'],
    'Oral argument questioning': ['argHas', 'argW', 'argT', 'argQ', 'argCourt', 'argCourtQ'],
    'Oral argument interruptions and first/last questions': ARG_EXTRA,
    'Martin-Quinn ideology x direction below': MQ_NUM,
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
     all justices' words (log ratio), all justices' questions (log ratio), justice's interruptions of counsel (log
     ratio), justice asked the first question (respondent's side minus petitioner's), asked the last question (same),
     all justices' interruptions (log ratio)]"""
    if not rec:
        return [0.0] * 10
    js = {k: v for k, v in rec.items() if not k.startswith('_')}
    own = js.get(surname, [0] * 12)
    own = list(own) + [0] * (12 - len(own))
    tot = [sum((list(v) + [0] * 12)[i] for v in js.values()) for i in range(12)]
    lr = lambda a, b: float(np.log1p(b) - np.log1p(a))
    return [1.0, lr(own[0], own[1]), float(own[3] - own[2]), lr(own[4], own[5]), lr(tot[0], tot[1]), lr(tot[4], tot[5]),
            lr(own[6], own[7]), float(own[9] - own[8]), float(own[11] - own[10]), lr(tot[6], tot[7])]


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
    # Martin-Quinn ideal point (positive = conservative) from the PREVIOUS term (the latest public release ends with
    # OT2021, so later terms use the last score); justices without one get it imputed from their liberal-vote share
    mq = mq_lookup(V.justiceName.values, V.term.astype(int).values, X.jLib.values)
    X['mq'] = mq
    mqr = mq - pd.Series(mq, index=V.index).groupby(V.caseId).transform('mean').values
    X['mqRel'] = mqr
    X['mqDir'] = mqr * (2 * lc - 1)      # conservative justice x liberal decision below -> reverse
    return X


_MQ = {}


def mq_lookup(codes, terms, jlib):
    if not _MQ:
        p = path('data/raw/mq/justices.csv')
        m = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame(columns=['term', 'justiceName', 'post_mn'])
        _MQ['by'] = {c: g.sort_values('term')[['term', 'post_mn']].values for c, g in m.groupby('justiceName')}
        _MQ['last'] = int(m.term.max()) if len(m) else 0
    out = np.full(len(codes), np.nan)
    for i, (c, t) in enumerate(zip(codes, terms)):
        g = _MQ['by'].get(c)
        if g is not None:
            g = g[g[:, 0] <= min(t - 1, _MQ['last'])]
            if len(g):
                out[i] = g[-1, 1]
    ok = ~np.isnan(out)
    if ok.sum() > 50 and (~ok).any():   # impute: MQ ~ liberal-vote share (both measured before the term)
        b = np.polyfit(jlib[ok], out[ok], 1)
        out[~ok] = np.polyval(b, jlib[~ok])
    return np.nan_to_num(out)


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


def rf_model(cats, num):
    pre = ColumnTransformer([('c', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1, min_frequency=5, max_categories=250,
                                                  encoded_missing_value=-1), cats), ('n', 'passthrough', num)])
    return Pipeline([('p', pre), ('m', RandomForestClassifier(n_estimators=300, min_samples_leaf=20, max_features=0.33, n_jobs=6, random_state=SEED))])


class Avg:
    """The ensemble used for every justice: the average of the boosted trees and the random forest."""
    def __init__(self, *models):
        self.models = models

    def predict_proba(self, X):
        return np.mean([m.predict_proba(X) for m in self.models], axis=0)


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


def _nodes(ncase, s, theta, kind):
    """Quadrature nodes (U, V, weights) and per-case factor scales (su, sv)."""
    x, w = GH
    w = w / w.sum()
    if kind == 'indep':
        return np.zeros(1), np.zeros(1), np.ones(1), np.zeros(ncase), np.zeros(ncase)
    if kind == 'shift':
        su, sv = np.full(ncase, np.exp(theta[0])), np.zeros(ncase)
    elif kind == 'two':
        su, sv = np.full(ncase, np.exp(theta[0])), np.full(ncase, np.exp(theta[1]))
    else:
        m = s.shape[1]
        su = np.exp(theta[0] + s @ theta[2:2 + m])
        sv = np.exp(theta[1] + s @ theta[2 + m:2 + 2 * m])
    U, V = np.meshgrid(x, x if kind != 'shift' else np.zeros(1), indexing='ij')
    WW = np.outer(w, w if kind != 'shift' else np.ones(1))
    return U.ravel(), V.ravel(), WW.ravel(), su, sv


def _conditional(p, lean, s, theta, kind, eps=1e-4):
    """Each justice's vote probability conditional on the two shared factors, (cases, nodes, n), with the intercepts
    solved (Newton) so that averaging over the factors gives back exactly the justice's own predicted probability p.
    Latent-factor model: votes are independent given a shift shared by the whole Court (u) and a shift multiplied by
    the justice's lean (v); the marginals are pinned to the per-justice predictions."""
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    U, V, W, su, sv = _nodes(p.shape[0], s, theta, kind)
    shift = su[:, None, None] * U[None, :, None] + sv[:, None, None] * V[None, :, None] * lean[:, None, :]
    a = np.log(p / (1 - p))
    for _ in range(80):
        q = 1 / (1 + np.exp(-(a[:, None, :] + shift)))
        f = np.einsum('cnj,n->cj', q, W) - p
        fp = np.einsum('cnj,n->cj', q * (1 - q), W)
        step = np.clip(f / np.maximum(fp, 1e-12), -2, 2)
        a -= step
        if np.abs(f).max() < 1e-10:
            break
    return 1 / (1 + np.exp(-(a[:, None, :] + shift))), W


def split_probs(p, lean, s, theta, kind):
    """P(k of the n justices vote for the petitioner), k = 0..n, for each case; p: (cases, n) per-justice probabilities."""
    q, W = _conditional(p, lean, s, theta, kind)
    n = q.shape[2]
    pb = np.zeros(q.shape[:2] + (n + 1,))
    pb[..., 0] = 1
    for j in range(n):
        qj = q[..., j:j + 1]
        pb = np.concatenate([pb[..., :1] * (1 - qj), pb[..., 1:] * (1 - qj) + pb[..., :-1] * qj], axis=-1)
    return np.einsum('cnk,n->ck', pb, W)


def pair_agreement(p, lean, s, theta, kind):
    """Model-implied probability that justices i and j vote on the same side, (cases, n, n)."""
    q, W = _conditional(p, lean, s, theta, kind)
    same = q[:, :, :, None] * q[:, :, None, :] + (1 - q[:, :, :, None]) * (1 - q[:, :, None, :])
    return np.einsum('cnij,n->cij', same, W)


def check_splits(dist, p, label):
    """The split distribution must agree with the per-justice probabilities: P(all for the petitioner) <= the smallest
    P(petitioner), P(all for the respondent) <= the smallest P(respondent), expected petitioner votes = their sum."""
    dist, p = np.asarray(dist, float), np.asarray(p, float)
    n = len(p)
    bad = []
    if abs(dist.sum() - 1) > 1e-6:
        bad.append(f'sums to {dist.sum():.6f}')
    if dist[n] > p.min() + 1e-6:
        bad.append(f'P({n}-0 reverse) {dist[n]:.4f} > min P(reverse) {p.min():.4f}')
    if dist[0] > (1 - p).min() + 1e-6:
        bad.append(f'P({n}-0 affirm) {dist[0]:.4f} > min P(affirm) {(1 - p).min():.4f}')
    ek = float(np.dot(np.arange(n + 1), dist))
    if abs(ek - p.sum()) > 1e-4:
        bad.append(f'expected reverse votes {ek:.5f} != sum of marginals {p.sum():.5f}')
    if bad:
        raise SystemExit(f'split check failed for {label}: ' + '; '.join(bad))


def split_fit(p, lean, s, k, kind):
    npar = {'indep': 0, 'shift': 1, 'two': 2, 'two+s': 2 + 2 * s.shape[1]}[kind]
    nll = lambda th: -np.mean(np.log(np.maximum(split_probs(p, lean, s, th, kind)[np.arange(len(k)), k], 1e-12)))
    if npar == 0:
        return np.zeros(0), nll(np.zeros(0))
    th0 = np.zeros(npar); th0[0] = np.log(2.0)
    if npar > 1:
        th0[1] = np.log(0.5)
    r = minimize(nll, th0, method='L-BFGS-B', bounds=[(-3, 2.5)] + [(-4, 2.5)] * (npar > 1) + [(-2, 2)] * max(0, npar - 2))
    return r.x, r.fun


# ------------------------------------------------------------- combining the nine predictions
# th = [a, b, g, log s_u, log s_v, a_r, b_r, a_pi]. Contested part: each justice's probability is first recalibrated
# jointly, logit m_j = a + b * c + g * (logit p_j - c), where c is the mean of the nine logits (the Court's lean in the
# case) and g < 1 shrinks the justices' differences; votes then share a Court-wide and a lean-weighted factor with m_j
# as marginals. Consensus part: with probability pi = logistic(a_pi) the case is decided unanimously, for the petitioner
# with probability r = logistic(a_r + b_r * c). Marginal shown for justice j: pi * r + (1 - pi) * m_j.
COMBOS = {'independent': [], 'pinned': [3, 4], 'recalibrated': [0, 1, 2, 3, 4], 'mixture': list(range(8))}
TH_BASE = np.array([0.0, 1.0, 1.0, -30.0, -30.0, 0.0, 1.0, -30.0])


def combo_th(kind, free):
    th = TH_BASE.copy()
    th[COMBOS[kind]] = free
    return th


def combo_parts(th, p, lean):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    Lg = np.log(p / (1 - p))
    c = Lg.mean(1)
    m = 1 / (1 + np.exp(-(th[0] + th[1] * c[:, None] + th[2] * (Lg - c[:, None]))))
    r = 1 / (1 + np.exp(-(th[5] + th[6] * c)))
    pi = np.full(len(p), 1 / (1 + np.exp(-th[7])))
    zero = np.zeros((len(p), 0))
    if th[3] < -20 and th[4] < -20:
        Q, W = _conditional(m, lean, zero, np.zeros(0), 'indep')
    else:
        Q, W = _conditional(m, lean, zero, th[3:5], 'two')
    return m, r, pi, Q, W


def combo_lik(th, p, lean, y):
    """Probability of the observed vote of every justice (not just the split)."""
    m, r, pi, Q, W = combo_parts(th, p, lean)
    f = np.prod(np.where(y[:, None, :] == 1, Q, 1 - Q), axis=2) @ W
    n = y.shape[1]
    return pi * (r * (y.sum(1) == n) + (1 - r) * (y.sum(1) == 0)) + (1 - pi) * f


def combo_dist(th, p, lean):
    """Split distribution (cases, n + 1) and the marginal probability for each justice (cases, n)."""
    m, r, pi, Q, W = combo_parts(th, p, lean)
    n = m.shape[1]
    pb = np.zeros(Q.shape[:2] + (n + 1,))
    pb[..., 0] = 1
    for j in range(n):
        qj = Q[..., j:j + 1]
        pb = np.concatenate([pb[..., :1] * (1 - qj), pb[..., 1:] * (1 - qj) + pb[..., :-1] * qj], axis=-1)
    d = (1 - pi)[:, None] * np.einsum('cnk,n->ck', pb, W)
    d[:, n] += pi * r
    d[:, 0] += pi * (1 - r)
    return d, pi[:, None] * r[:, None] + (1 - pi)[:, None] * m


def combo_pairs(th, p, lean):
    m, r, pi, Q, W = combo_parts(th, p, lean)
    same = Q[:, :, :, None] * Q[:, :, None, :] + (1 - Q[:, :, :, None]) * (1 - Q[:, :, None, :])
    return pi[:, None, None] + (1 - pi)[:, None, None] * np.einsum('cnij,n->cij', same, W)


def combo_fit(kind, p, lean, y):
    idx = COMBOS[kind]
    nll = lambda free: -np.mean(np.log(np.maximum(combo_lik(combo_th(kind, free), p, lean, y), 1e-300)))
    if not idx:
        return combo_th(kind, []), nll([])
    start = np.array([0.0, 0.8, 0.6, np.log(2.0), 0.0, 0.0, 1.0, -1.0])[idx]
    r = minimize(nll, start, method='L-BFGS-B')
    return combo_th(kind, r.x), r.fun


# ------------------------------------------------------------- individual calibration (margins shown)
# Optional recalibration of each justice's probability, fitted to the INDIVIDUAL votes (log loss of each vote on its
# own), never to the joint outcome: logit q_j = a + b * c + g * (logit p_j - c), c the mean of the nine logits.
# 'raw' keeps the model's probability; 'scale' is Platt scaling (b = g); 'court' lets the Court-wide lean and the
# justice's difference from it be scaled separately. Chosen by 2-fold cross-validation over the validation terms.
CAL_KINDS = {'raw': [], 'scale': [0, 1], 'court': [0, 1, 2]}


def cal_apply(kind, th, p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    if kind == 'raw':
        return p
    L = np.log(p / (1 - p))
    c = L.mean(1, keepdims=True)
    a, b = th[0], th[1]
    g = th[2] if kind == 'court' else th[1]
    return 1 / (1 + np.exp(-(a + b * c + g * (L - c))))


def cal_fit(kind, p, y):
    if kind == 'raw':
        return np.zeros(0)
    nll = lambda th: acc_ll(cal_apply(kind, th, p).ravel(), y.ravel())[1]
    return minimize(nll, np.array([0.0, 1.0, 1.0])[:len(CAL_KINDS[kind])], method='L-BFGS-B').x


# ------------------------------------------------------------- joint vote model with the shown margins
# A mixture whose every component keeps the margins: with weight w+ all nine vote for the petitioner, with weight w-
# all nine vote for the respondent, otherwise the case is contested and votes follow the latent two-factor model (a
# Court-wide factor and a factor weighted by each justice's lean) with margins m_j = (p_j - w+) / (1 - w+ - w-), so
# that P(justice j for the petitioner) = w+ + (1 - w+ - w-) m_j = p_j exactly. The unanimity weights are a share kappa
# of their largest possible values (Frechet bounds: w+ <= min_j p_j, w- <= min_j (1 - p_j)); kappa depends on the case
# (logistic in the spread of the nine predictions, the Court's lean, amicus participation and the spread of questioning
# at argument). Parameters th = [k0, k_spread, k_lean, k_amicus, k_argument, log s_u, log s_v], fitted on the validation
# terms to the likelihood of the actual split (joint_fit).
KMAX = 0.995
# The two earlier versions scored on the same 2022-2025 cases (from their cached per-justice predictions; see the README):
# fa90a18 = consensus/contested mixture that shrank the justices' probabilities; d20d0c8 = joint model keeping them.
HISTORY = {
    'previous (Nov. 17)': {'voteAcc': 0.7026, 'voteLL': 0.5831, 'voteBrier': 0.199, 'win': 0.7124, 'winLL': 0.5832, 'winBrier': 0.1985,
                           'splitLL': -1.9784, 'unanPred': 0.3443, 'unanAct': 0.4513, 'unanBrier': 0.2547, 'topHit': 0.354,
                           'topFold': {'9-0': 209, '8-1': 0, '7-2': 0, '6-3': 17, '5-4': 0}},
    'previous (Nov. 25)': {'voteAcc': 0.6927, 'voteLL': 0.5753, 'voteBrier': 0.1964, 'win': 0.6814, 'winLL': 0.5827, 'winBrier': 0.1986,
                           'splitLL': -1.9689, 'unanPred': 0.3454, 'unanAct': 0.4513, 'unanBrier': 0.2441, 'topHit': 0.3407,
                           'topFold': {'9-0': 160, '8-1': 9, '7-2': 8, '6-3': 43, '5-4': 6}},
}
JOINT_START = np.array([1.0, 0.0, 0.0, 0.0, 0.0, np.log(1.5), np.log(0.5)])


def joint_feats(p, S):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    L = np.log(p / (1 - p))
    return np.c_[L.std(1) - 1.0, np.abs(L.mean(1)) - 0.8, S]


def joint_parts(th, p, lean, S):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    F = joint_feats(p, S)
    kap = KMAX / (1 + np.exp(-(th[0] + F @ th[1:1 + F.shape[1]])))
    w1, w0 = kap * p.min(1), kap * (1 - p).min(1)
    m = (p - w1[:, None]) / (1 - w0 - w1)[:, None]
    Q, W = _conditional(m, lean, np.zeros((len(p), 0)), th[-2:], 'two', eps=1e-7)
    return w1, w0, Q, W


def joint_lik(th, p, lean, S, y):
    w1, w0, Q, W = joint_parts(th, p, lean, S)
    f = np.prod(np.where(y[:, None, :] == 1, Q, 1 - Q), axis=2) @ W
    n = y.shape[1]
    return w1 * (y.sum(1) == n) + w0 * (y.sum(1) == 0) + (1 - w1 - w0) * f


def joint_dist(th, p, lean, S):
    """Split distribution (cases, n + 1); its margins are p."""
    w1, w0, Q, W = joint_parts(th, p, lean, S)
    n = Q.shape[2]
    pb = np.zeros(Q.shape[:2] + (n + 1,))
    pb[..., 0] = 1
    for j in range(n):
        qj = Q[..., j:j + 1]
        pb = np.concatenate([pb[..., :1] * (1 - qj), pb[..., 1:] * (1 - qj) + pb[..., :-1] * qj], axis=-1)
    d = (1 - w1 - w0)[:, None] * np.einsum('cnk,n->ck', pb, W)
    d[:, n] += w1
    d[:, 0] += w0
    return d


def joint_pairs(th, p, lean, S):
    w1, w0, Q, W = joint_parts(th, p, lean, S)
    same = Q[:, :, :, None] * Q[:, :, None, :] + (1 - Q[:, :, :, None]) * (1 - Q[:, :, None, :])
    return (w1 + w0)[:, None, None] + (1 - w1 - w0)[:, None, None] * np.einsum('cnij,n->cij', same, W)


def joint_fit(p, lean, S, y, free=None, objective='split'):
    """free: indices of th to fit (the others stay at JOINT_START, slopes 0). objective 'split': likelihood of the actual
    split (the outcome the page shows, so the dependence is fitted to the unanimity share and the split frequencies);
    'votes': likelihood of every justice's actual vote."""
    free = list(range(len(JOINT_START))) if free is None else free
    k = y.sum(1)
    def full(x):
        th = JOINT_START.copy(); th[1:5] = 0
        th[free] = x
        return th
    if objective == 'split':
        nll = lambda x: -np.mean(np.log(np.maximum(joint_dist(full(x), p, lean, S)[np.arange(len(k)), k], 1e-12)))
    else:
        nll = lambda x: -np.mean(np.log(np.maximum(joint_lik(full(x), p, lean, S, y), 1e-300)))
    r = minimize(nll, JOINT_START[free], method='L-BFGS-B', bounds=[(-6, 8)] + [(-4, 4)] * (len(free) - 3) + [(-3, 2.5), (-4, 2.5)])
    return full(r.x), r.fun


def split_label(k, n=9):
    return f'Reverse {k}–{n - k}' if 2 * k > n else f'Affirm {n - k}–{k}'


def split_eval(dist, marg, Y, vote_lik=None):
    """Test metrics for a split distribution (cases, 10) with margins marg (cases, 9) against the actual votes Y."""
    kk = Y.sum(1)
    n = Y.shape[1]
    N = len(kk)
    acc, ll = acc_ll(marg.ravel(), Y.ravel())
    pk = dist[np.arange(N), kk]
    unan = dist[:, 0] + dist[:, n]
    ua = ((kk == 0) | (kk == n)).astype(float)
    fold = lambda k: max(k, n - k)
    top = dist.argmax(1)
    r = {'voteAcc': round(acc, 4), 'voteLL': round(ll, 4), 'splitLL': round(float(np.mean(np.log(np.maximum(pk, 1e-12)))), 4),
         'win': round(float(((dist[:, (n + 1) // 2:].sum(1) >= 0.5) == (kk * 2 > n)).mean()), 4),
         'winLL': round(acc_ll(dist[:, (n + 1) // 2:].sum(1), (kk * 2 > n).astype(int))[1], 4),
         'winBrier': round(float(np.mean((dist[:, (n + 1) // 2:].sum(1) - (kk * 2 > n)) ** 2)), 4),
         'voteBrier': round(float(np.mean((marg - Y) ** 2)), 4),
         'unanPred': round(float(unan.mean()), 4), 'unanAct': round(float(ua.mean()), 4),
         'unanBrier': round(float(np.mean((unan - ua) ** 2)), 4),
         'topHit': round(float((top == kk).mean()), 4),
         'topFold': {f'{m}-{n - m}': int(sum(fold(k) == m for k in top)) for m in range(n, (n - 1) // 2, -1)},
         'actFold': {f'{m}-{n - m}': int(sum(fold(k) == m for k in kk)) for m in range(n, (n - 1) // 2, -1)}}
    if vote_lik is not None:
        r['vectorLL'] = round(float(np.mean(np.log(np.maximum(vote_lik, 1e-300)))), 4)
    # calibration of P(unanimous) in four bins
    bins = [0, 0.3, 0.45, 0.6, 1.01]
    r['unanCal'] = [[round(float(unan[(unan >= a) & (unan < b)].mean()), 3), round(float(ua[(unan >= a) & (unan < b)].mean()), 3), int(((unan >= a) & (unan < b)).sum())]
                    for a, b in zip(bins, bins[1:]) if ((unan >= a) & (unan < b)).any()]
    return r



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
    for i, c in enumerate(ARG_COLS):
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
    for c in NUM + ARG_EXTRA:
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
    if REUSE and os.path.exists(STAGE):      # --reuse: skip the term-by-term fits (cached by the last full build)
        with open(STAGE, 'rb') as fh:
            pred, choice, out, final_cached = pickle.load(fh)
        print('reused the cached per-justice predictions', STAGE, flush=True)
    else:
        final_cached = None
        pred = {ver: {k: pd.Series(np.nan, index=V.index) for k in ('pooled', 'rf', 'ens', 'own', 'blend', 'old')} for ver in ('full', 'dock')}
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
                trr = tr.values & (V.term >= RF_START).values
                rm = rf_model(['justice'] + cats, num).fit(X.loc[trr, cols], y[trr])
                pred[ver]['rf'][te] = rm.predict_proba(X.loc[te, cols])[:, 1]
                pred[ver]['ens'][te] = (pred[ver]['pooled'][te].values + pred[ver]['rf'][te].values) / 2
                if T == TEST[0]:
                    keep[(ver, 'pooled')] = pm
                    keep[(ver, 'ens')] = Avg(pm, rm)
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
                for k in ('ens', 'pooled', 'rf', 'own', 'blend'):
                    m = val & mj & pred[ver][k].notna().values
                    if m.sum() >= 40:
                        vs[k] = acc_ll(pred[ver][k][m], y[m])
                # the same model for every justice: the ensemble had the lowest log loss on the validation votes of all
                # justices; choosing a model per justice by validation accuracy did worse there (noisier)
                best = 'ens'
                choice[(ver, code)] = best
                mt = tst & mj
                yt = y[mt]
                res = {k: acc_ll(pred[ver][k][mt], yt) for k in ('ens', 'pooled', 'rf', 'own', 'blend')}
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
            mdl = keep[(ver, 'ens')]
            cols = ['justice'] + cats + num
            r['imp'] = grouped_importance(mdl, XS[ver].loc[mt], yt, GROUPS, cols)
            import model_directions as MD      # hover notes: what each group measures, which way it moves this justice
            r['dir'] = MD.directions(V, code, surname.get(code, code).title())
            out[jid] = r
            print(f"{code:12} test={mt.sum():4} base={best_base:.3f} | pending-case model [{r['dock']['choice']:6}] {r['dock']['acc']:.3f} "
                  f"(boosted {r['dock']['all']['pooled']:.3f} forest {r['dock']['all']['rf']:.3f} own {r['dock']['all']['own']:.3f}; previous {r['old']}) "
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
    lo = W9.p.values.reshape(-1, 9)      # per-justice probabilities (the split model keeps them as its marginals)
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
    Yv = W9.y.values.reshape(-1, 9)
    emp = (np.bincount(kk[iv], minlength=10) + 0.5) / (iv.sum() + 5)
    names = W9.justiceName.values.reshape(-1, 9)[it][0]
    h1, h2 = np.isin(terms, VAL[:3]), np.isin(terms, VAL[3:])
    folds = ((h1, h2), (h2, h1))
    if os.environ.get('LC_SPLIT_DUMP'):          # development: the arrays the combination step needs
        np.savez(os.environ['LC_SPLIT_DUMP'], lo=lo, ln=ln, S=S, Yv=Yv, terms=terms, cid=cid, names=names)

    # 1. margins shown: each justice's own model, recalibrated only if that improves the individual votes' log loss in
    #    2-fold cross-validation over the validation terms without costing accuracy
    cal_cv = {}
    for ck in CAL_KINDS:
        ll_, ac_ = 0, 0
        for a, b in folds:
            pc = cal_apply(ck, cal_fit(ck, lo[a], Yv[a]), lo[b])
            r_ = acc_ll(pc.ravel(), Yv[b].ravel())
            ac_ += r_[0] / 2; ll_ += r_[1] / 2
        cal_cv[ck] = [round(ac_, 4), round(ll_, 4)]
    ok_cal = [ck for ck in CAL_KINDS if cal_cv[ck][0] >= cal_cv['raw'][0] - 0.005]
    cal_kind = min(ok_cal, key=lambda ck: cal_cv[ck][1])
    cal_th = {ck: cal_fit(ck, lo[iv], Yv[iv]) for ck in CAL_KINDS}
    pv = cal_apply(cal_kind, cal_th[cal_kind], lo)
    cal_test = {ck: [round(x, 4) for x in acc_ll(cal_apply(ck, cal_th[ck], lo[it]).ravel(), Yv[it].ravel())] for ck in CAL_KINDS}
    print('individual calibration: cv [acc, logloss]', cal_cv, '| test', cal_test, '| chosen', cal_kind, np.round(cal_th[cal_kind], 3), flush=True)

    # 2. dependence: the joint model keeps those margins; its parameters are fitted on the validation terms to the
    #    likelihood of the actual split, and its form (unanimity share constant or case-dependent) is chosen by 2-fold
    #    cross-validation over the validation terms
    STRUCT = {'joint (constant unanimity share)': [0, 5, 6], 'joint (case-dependent unanimity share)': list(range(7))}
    split_ll = lambda d_, k_: float(np.mean(np.log(np.maximum(d_[np.arange(len(k_)), k_], 1e-12))))
    jcv = {}
    for nm_, fr in STRUCT.items():
        tot = 0
        for a, b in folds:
            th_, _ = joint_fit(pv[a], ln[a], S[a], Yv[a], fr)
            tot += split_ll(joint_dist(th_, pv[b], ln[b], S[b]), kk[b]) / 2
        jcv[nm_] = round(tot, 4)
    for kd in ('pinned', 'independent'):     # the earlier forms, with the same margins, for comparison
        tot = 0
        for a, b in folds:
            th_, _ = combo_fit(kd, pv[a], ln[a], Yv[a])
            tot += split_ll(combo_dist(th_, pv[b], ln[b])[0], kk[b]) / 2
        jcv[kd] = round(tot, 4)
    best_struct = max(STRUCT, key=lambda k: jcv[k])
    th_j, _ = joint_fit(pv[iv], ln[iv], S[iv], Yv[iv], STRUCT[best_struct])
    th_jv, _ = joint_fit(pv[iv], ln[iv], S[iv], Yv[iv], STRUCT[best_struct], objective='votes')
    print('joint structure: cv split log lik', jcv, '| chosen', best_struct, np.round(th_j, 3), flush=True)

    # 3. test on the test terms against the earlier methods and baselines
    Yt, kt = Yv[it], kk[it]
    nt = int(it.sum())
    prt = joint_dist(th_j, pv[it], ln[it], S[it])
    for i in range(nt):
        check_splits(prt[i], pv[it][i], f'test case {cid[it][i]}')
    ev = {'joint': split_eval(prt, pv[it], Yt, joint_lik(th_j, pv[it], ln[it], S[it], Yt)),
          'joint fitted to votes': split_eval(joint_dist(th_jv, pv[it], ln[it], S[it]), pv[it], Yt, joint_lik(th_jv, pv[it], ln[it], S[it], Yt))}
    for kd, lab in (('independent', 'independent'), ('pinned', 'pinned'), ('mixture', 'previous')):
        thk, _ = combo_fit(kd, lo[iv], ln[iv], Yv[iv])
        dk_, mk_ = combo_dist(thk, lo[it], ln[it])
        ev[lab] = split_eval(dk_, mk_, Yt, combo_lik(thk, lo[it], ln[it], Yt))
    ev['historical frequencies'] = split_eval(np.tile(emp, (nt, 1)), np.full((nt, 9), 0.5), Yt)
    for k_ in ('voteAcc', 'voteLL', 'win', 'topFold'):
        ev['historical frequencies'].pop(k_, None)
    ev['historical frequencies']['win'] = round(float((kt >= 5).mean() if emp[5:].sum() >= 0.5 else (kt < 5).mean()), 4)
    ev['historical frequencies']['topFold'] = {f'{m}-{9 - m}': (nt if m == max(int(np.argmax(emp)), 9 - int(np.argmax(emp))) else 0) for m in range(9, 4, -1)}
    cnt = (pv[it] > 0.5).sum(1)                # the naive headline: how many justices are above 50%
    ev['count above 50%'] = {'topHit': round(float((cnt == kt).mean()), 4), 'topFold': {f'{m}-{9 - m}': int(sum(max(k_, 9 - k_) == m for k_ in cnt)) for m in range(9, 4, -1)},
                             'win': round(float(((cnt >= 5) == (kt >= 5)).mean()), 4)}
    # baselines: always reverse (probability: the validation-era share of reversals) and, for votes, each justice's
    # share of votes for the petitioner before the test terms
    p_rev = float((kk[iv] >= 5).mean())
    ev['always reverse'] = {'win': round(float((kt >= 5).mean()), 4), 'winLL': round(acc_ll(np.full(nt, p_rev), (kt >= 5).astype(int))[1], 4),
                            'winBrier': round(float(np.mean((p_rev - (kt >= 5)) ** 2)), 4)}
    rate = V[V.term < TEST[0]].groupby('justiceName').y.mean()
    pr_ = np.array([[rate.get(nm_, 0.6) for nm_ in row] for row in W9.justiceName.values.reshape(-1, 9)[it]])
    a_, l_ = acc_ll(pr_.ravel(), Yt.ravel())
    ev['justice reversal rate'] = {'voteAcc': round(a_, 4), 'voteLL': round(l_, 4), 'voteBrier': round(float(np.mean((pr_ - Yt) ** 2)), 4)}
    # headline rules, scored by how often the named split is the actual one
    unan_t = prt[:, 0] + prt[:, 9]
    pwin_t = prt[:, 5:].sum(1)
    div = prt.copy(); div[:, [0, 9]] = 0
    alt = np.where(unan_t >= 0.5, prt.argmax(1), div.argmax(1))
    calib_headline = {'likeliest split': round(float((prt.argmax(1) == kt).mean()), 4),
                      'likeliest divided split unless P(unanimous) >= 50%': round(float((alt == kt).mean()), 4),
                      'count of justices above 50%': ev['count above 50%']['topHit'],
                      'unanimous in the direction of the likelier side': round(float((np.where(pwin_t >= 0.5, 9, 0) == kt).mean()), 4)}
    print('  headline rules (share of test cases where the named split was the actual one):', calib_headline, flush=True)
    def reliability(p_, t_, bins=(0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.01)):
        return [[round(float(p_[(p_ >= a) & (p_ < b)].mean()), 3), round(float(t_[(p_ >= a) & (p_ < b)].mean()), 3), int(((p_ >= a) & (p_ < b)).sum())]
                for a, b in zip(bins, bins[1:]) if ((p_ >= a) & (p_ < b)).any()]
    calib_rel = {'votes': reliability(pv[it].ravel(), Yt.ravel()), 'reverse': reliability(pwin_t, (kt >= 5).astype(float))}
    print('  reliability [predicted, actual, n]:', calib_rel, flush=True)
    for nm_, r_ in ev.items():
        print(f'  test {nm_:24}', r_, flush=True)
    for j, nm in enumerate(names):
        if code2id.get(nm) in out:
            out[code2id[nm]]['joint'] = round(float(((pv[it][:, j] > 0.5) == Yt[:, j]).mean()), 4)
    # pairwise agreement: model-implied vs actual, on the test cases (the same nine justices throughout)
    ag = joint_pairs(th_j, pv[it], ln[it], S[it]).mean(0)
    ag0 = combo_pairs(combo_th('independent', []), pv[it], ln[it]).mean(0)
    act = np.array([[float((Yt[:, i] == Yt[:, j]).mean()) for j in range(9)] for i in range(9)])
    iu = np.triu_indices(9, 1)
    pair_mae = float(np.abs(ag - act)[iu].mean()); pair_mae0 = float(np.abs(ag0 - act)[iu].mean())
    pairs = sorted([[code2id[names[i]], code2id[names[j]], round(float(ag[i, j]), 3), round(float(act[i, j]), 3)] for i, j in zip(*iu)], key=lambda r: -r[3])
    print(f'  pairwise agreement on test cases: mean abs error {pair_mae:.3f} (independent votes {pair_mae0:.3f})', flush=True)
    pwin = prt[:, 5:].sum(1)
    conf = np.abs(pwin - 0.5) >= 0.25
    kap_v = KMAX / (1 + np.exp(-(th_j[0] + joint_feats(pv[iv], S[iv]) @ th_j[1:5])))
    w_v = kap_v * (pv[iv].min(1) + (1 - pv[iv]).min(1))
    calib = {'kind': 'joint', 'struct': best_struct, 'headline': calib_headline, 'history': HISTORY, 'reliability': calib_rel, 'theta': [round(float(x), 4) for x in th_j], 'cv': jcv,
             'cal': cal_kind, 'calTheta': [round(float(x), 4) for x in cal_th[cal_kind]], 'calCv': cal_cv, 'calTest': cal_test,
             'eval': ev, 'nVal': int(iv.sum()), 'nTest': nt, 'emp': [round(float(x), 4) for x in emp],
             'unanVal': round(float(((kk[iv] == 0) | (kk[iv] == 9)).mean()), 4), 'kappa': round(float(kap_v.mean()), 4), 'wUnan': round(float(w_v.mean()), 4),
             'boundUnan': round(float((pv[it].min(1) + (1 - pv[it]).min(1)).mean()), 4),
             'revBase': round(float(max((kt >= 5).mean(), (kt < 5).mean())), 4),
             'confN': int(conf.sum()), 'confHit': round(float(((pwin[conf] >= 0.5) == (kt[conf] >= 5)).mean()), 4) if conf.any() else None,
             'testDist': [round(float(x), 4) for x in prt.mean(0)], 'testEmp': [round(float(x), 4) for x in np.bincount(kt, minlength=10) / nt],
             'leanSd': lean_sd, 'salMu': sal_mu, 'salSd': sal_sd, 'pairMae': round(pair_mae, 4), 'pairMaeIndep': round(pair_mae0, 4), 'pairs': pairs}

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
    for i, c in enumerate(ARG_COLS):
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
    for c in NUM + ARG_EXTRA:
        if c not in XP.columns:
            XP[c] = PV[c].astype(float)
    cats, num = cols_for('dock')
    X = XS['dock']
    if final_cached is not None and len(final_cached) == len(PV):
        final = final_cached
    else:
        pm = pooled_model(['justice'] + cats, num).fit(X[['justice'] + cats + num], y)
        pp = pm.predict_proba(XP[['justice'] + cats + num])[:, 1]
        rsel = (V.term >= RF_START).values
        rm = rf_model(['justice'] + cats, num).fit(X.loc[rsel, ['justice'] + cats + num], y[rsel])
        pp = (pp + rm.predict_proba(XP[['justice'] + cats + num])[:, 1]) / 2     # the ensemble ('ens')
        final = np.array(pp)
        for code in CURRENT:
            mj = (V.justiceName == code).values
            mp = (PV.justiceName == code).values
            ch = choice[('dock', code)]
            if ch in ('own', 'blend') and mj.sum() >= 60:
                om = own_model(cats, num).fit(X.loc[mj, cats + num], y[mj])
                po = om.predict_proba(XP.loc[mp, cats + num])[:, 1]
                final[mp] = po if ch == 'own' else (po + pp[mp]) / 2
        with open(STAGE, 'wb') as fh:
            pickle.dump((pred, choice, out, final), fh)
    PV["p"] = np.clip(final, 0.001, 0.999)
    shown = {}        # (justice, case id) -> (probability shown, the model's raw probability)
    cases_out = []
    for i, r in P.iterrows():
        m = (PV.caseId == r.caseId).values
        sub = PV[m].set_index('justiceName').loc[CURRENT]
        ln_c = (J.loc[PV.index[m], 'lean'].values / lean_sd)[None, :]
        amt_c = np.log1p(np.expm1(r.amPetL) + np.expm1(r.amResL))
        S_c = np.array([[(amt_c - sal_mu[0]) / sal_sd[0] if r.amKnown else 0.0, (r.argSpread - sal_mu[1]) / sal_sd[1] if r.argSpread > 0 else 0.0]])
        mg = cal_apply(cal_kind, cal_th[cal_kind], sub.p.values[None, :])
        dist = joint_dist(th_j, mg, ln_c, S_c)[0]
        mg = mg[0]
        check_splits(dist, mg, r.c['id'])
        for code, raw, q in zip(CURRENT, sub.p.values, mg):
            shown[(code, r.c['id'])] = (round(float(q), 3), round(float(raw), 3))
        top = int(np.argmax(dist))
        c = r.c
        cases_out.append({'id': c['id'], 'n': c['n'], 'd': c['d'], 'lowerCourt': r.lowerCourt, 'src': r.srcGroup, 'pet': r.petParty, 'res': r.resParty,
                          'jur': r.jurisdiction, 'area': ISSUE_AREA.get(int(r.issueD), ''), 'areaP': r.issueP, 'page': bool(r.ok),
                          'lcLib': round(float(r.lcLibD), 3), 'us': int(r.usSide), 'usAmicus': int(r.usAmicus), 'cvsg': int(r.cvsg),
                          'am': [int(round(np.expm1(r.amPetL))), int(round(np.expm1(r.amResL))), int(round(np.expm1(r.amCertL)))] if r.amKnown else None,
                          'arg': bool(r.argKey and r.argKey in ARG), 'argCourt': round(float(sub.argCourt.iloc[0]), 3),
                          'dist': [round(float(x), 4) for x in dist], 'pRev': round(float(dist[5:].sum()), 4),
                          'top': [top, round(float(dist[top]), 4)], 'pUnan': round(float(dist[0] + dist[9]), 4)})
    for code in CURRENT:
        ids = [c['id'] for c in P.c]
        out[code2id[code]]['pred'] = [[cid, shown[(code, cid)][0]] for cid in ids]
        out[code2id[code]]['predRaw'] = [[cid, shown[(code, cid)][1]] for cid in ids]
    data = {'src': SRC, 'generated': pd.Timestamp.now().strftime('%Y-%m-%d'), 'version': 3, 'issueClf': issue_eval, 'lcClf': lc_eval,
            'val': [VAL[0], VAL[-1]], 'test': [TEST[0], TEST[-1]], 'calib': calib, 'order': [code2id[c] for c in CURRENT],
            'nArg': int(len(ARG)), 'nFacts': int(len(FCT)), 'j': out, 'cases': cases_out}
    kb = write_js('models', 'MODELS', data) / 1024
    print(f'models.js {kb:.0f} KB; {len(cases_out)} pending cases; {time.time() - t0:.0f}s')
    for c in cases_out:
        top = c['top'][0]
        print(f"  {c['d']:10} {c['n'][:40]:40} P(rev)={c['pRev']:.2f} likeliest {split_label(top)} ({c['top'][1]:.2f}) P(unan)={c['pUnan']:.2f} | "
              f"split {[round(x, 2) for x in c['dist']]} | shown {[q for (cd, cid_), (q, _) in shown.items() if cid_ == c['id']]}")
    hd = {}
    for c in cases_out:
        hd[split_label(c['top'][0])] = hd.get(split_label(c['top'][0]), 0) + 1
    print('  headline (likeliest split) on pending cases:', hd)


if __name__ == '__main__':
    main()
