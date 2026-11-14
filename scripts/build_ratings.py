"""Build docs/data/ratings.js: a liberal-conservative score and an institutionalism score for every justice in the
Supreme Court Database (1791-2025), with the components behind each and a term-by-term series.

Inputs
  SCDB justice-centered data (see scdb_lib.py), decision types 1, 2, 6 and 7 (cases decided with an opinion).
  Martin-Quinn scores, data/raw/mq/justices.csv: Andrew D. Martin and Kevin M. Quinn, "Dynamic Ideal Point Estimation
  via Markov Chain Monte Carlo for the U.S. Supreme Court, 1953-1999," Political Analysis 10 (2002): 134-153;
  2021 release (terms 1937-2021), https://mqscores.quantitative.emory.edu/media/2021/justices.csv

Method (all computed; nothing hand-coded)
  Ideology
    lib     share of the justice's votes that SCDB codes liberal (vote-level `direction` 2) among votes coded
            liberal or conservative.
    libRel  the same, minus the share of liberal votes cast by the colleagues who sat in the same cases, averaged over
            the justice's votes (percentage points; positive = more liberal than colleagues). This removes the drift in
            what the Court decides and how SCDB codes direction across eras, so justices of different eras can be compared.
    mq      career mean of the Martin-Quinn posterior means (negative = liberal), and the per-term values.
  Institutionalism (each component also measured against the colleagues who sat in the same cases, in points):
    maj     voted with the majority (`majority` 2).                                      higher = more institutional
    sep     wrote a separate opinion (concurrence or dissent; `opinion` 2 or 3, not the majority author).  lower = more
    spec    concurred only in the judgment (`vote` 4, special concurrence).                lower = more
    overr   voted with the majority in decisions that formally altered precedent (`precedentAlteration` 1). lower = more
    strike  voted with the majority in decisions declaring a federal, state or local law unconstitutional
            (`declarationUncon` 2-4).                                                       lower = more deferential
    Components with few qualifying votes are shrunk toward zero (difference sum / (n + 10)).
    The index is the mean of the components' z-scores across justices (sign-adjusted so higher = more institutional),
    reported as a percentile among justices with at least 100 votes. SCDB has no variable for the breadth of a ruling,
    so narrow-versus-broad holdings are not part of the measure.
Run from the repo root:  python scripts/build_ratings.py
"""
import os
import numpy as np
import pandas as pd
from scdb_lib import load_votes, justice_ids, write_js, path, SRC

SHRINK = 10
MIN_VOTES = 100


def colleague_diff(d, own_col, mask=None):
    """Per vote: own value minus the mean of the other participating justices in the same case (NaN when alone)."""
    x = d if mask is None else d[mask]
    x = x[x[own_col].notna()]
    g = x.groupby('caseId')[own_col]
    s, n = g.transform('sum'), g.transform('count')
    other = (s - x[own_col]) / (n - 1)
    return (x[own_col] - other).where(n > 1), x


def main():
    d = load_votes()
    d = d[d.decisionType.isin([1, 2, 6, 7])].copy()
    code2id, jinfo = justice_ids()
    d['lib'] = np.where(d.direction == 2, 1.0, np.where(d.direction == 1, 0.0, np.nan))
    d['inmaj'] = np.where(d.majority == 2, 1.0, np.where(d.majority == 1, 0.0, np.nan))
    d['sepw'] = (((d.opinion == 2) | (d.opinion == 3)) & (d.justice != d.majOpinWriter)).astype(float)
    d['specc'] = (d.vote == 4).astype(float)

    comps = {}
    diff, x = colleague_diff(d, 'lib'); comps['libRel'] = (diff, x)
    diff, x = colleague_diff(d, 'inmaj'); comps['maj'] = (diff, x)
    diff, x = colleague_diff(d, 'sepw'); comps['sep'] = (diff, x)
    diff, x = colleague_diff(d, 'specc'); comps['spec'] = (diff, x)
    diff, x = colleague_diff(d, 'inmaj', d.precedentAlteration == 1); comps['overr'] = (diff, x)
    diff, x = colleague_diff(d, 'inmaj', d.declarationUncon.isin([2, 3, 4])); comps['strike'] = (diff, x)

    rows = {}
    for code, g in d.groupby('justiceName'):
        r = {'code': code, 'n': int(len(g)), 'first': int(g.term.min()), 'last': int(g.term.max())}
        lib = g.lib.dropna()
        r['nDir'] = int(len(lib)); r['lib'] = round(100 * lib.mean(), 1) if len(lib) else None
        r['majRate'] = round(100 * g.inmaj.dropna().mean(), 1)
        r['sepRate'] = round(100 * g.sepw.mean(), 1)
        r['specRate'] = round(100 * g.specc.mean(), 1)
        ov = g[g.precedentAlteration == 1].inmaj.dropna(); r['nOverr'] = int(len(ov)); r['overrRate'] = round(100 * ov.mean(), 1) if len(ov) else None
        st = g[g.declarationUncon.isin([2, 3, 4])].inmaj.dropna(); r['nStrike'] = int(len(st)); r['strikeRate'] = round(100 * st.mean(), 1) if len(st) else None
        stf = g[g.declarationUncon == 2].inmaj.dropna(); r['nStrikeFed'] = int(len(stf)); r['strikeFedRate'] = round(100 * stf.mean(), 1) if len(stf) else None
        rows[code] = r
    for k, (diff, x) in comps.items():
        k_shr = SHRINK if k in ('overr', 'strike') else 0
        agg = pd.DataFrame({'j': x.justiceName, 'v': diff}).dropna().groupby('j').v.agg(['sum', 'count'])
        for code, a in agg.iterrows():
            rows[code][k] = round(100 * a['sum'] / (a['count'] + k_shr), 2)

    # MQ scores
    mq = {}
    if os.path.exists(path('data/raw/mq/justices.csv')):
        m = pd.read_csv(path('data/raw/mq/justices.csv'))
        for code, g in m.groupby('justiceName'):
            mq[code] = g.sort_values('term')
    # per-term series
    tl = d.groupby(['justiceName', 'term']).agg(lib=('lib', 'mean'), maj=('inmaj', 'mean'), n=('caseId', 'count')).reset_index()

    # institutionalism index
    sign = {'maj': 1, 'sep': -1, 'spec': -1, 'overr': -1, 'strike': -1}
    elig = [c for c, r in rows.items() if r['n'] >= MIN_VOTES]
    for k, sg in sign.items():
        vals = np.array([rows[c].get(k, 0.0) for c in elig])
        mu, sd = vals.mean(), vals.std() or 1
        for c, r in rows.items():
            r['z_' + k] = round(sg * (r.get(k, 0.0) - mu) / sd, 3)
    for r in rows.values():
        r['instRaw'] = round(float(np.mean([r['z_' + k] for k in sign])), 3)
    for key, field in (('instRaw', 'inst'), ('libRel', 'libPct')):
        ev = np.array([rows[c][key] for c in elig if rows[c].get(key) is not None])
        for r in rows.values():
            if r.get(key) is not None:
                r[field] = round(100 * float((ev < r[key]).mean() + 0.5 * (ev == r[key]).mean()), 1)
    rank = sorted(elig, key=lambda c: -rows[c]['instRaw'])
    for i, c in enumerate(rank):
        rows[c]['instRank'] = i + 1
    rank = sorted([c for c in elig if rows[c].get('libRel') is not None], key=lambda c: -rows[c]['libRel'])
    for i, c in enumerate(rank):
        rows[c]['libRank'] = i + 1

    out = {}
    for code, r in rows.items():
        jid = code2id.get(code)
        if not jid:
            print('no justice page for', code); continue
        t = tl[tl.justiceName == code]
        r['terms'] = [[int(a.term), round(100 * a.lib, 1) if a.lib == a.lib else None, round(100 * a.maj, 1) if a.maj == a.maj else None, int(a.n)] for a in t.itertuples()]
        if code in mq:
            g = mq[code]
            r['mq'] = round(float(g.post_mn.mean()), 3)
            r['mqTerms'] = [[int(a.term), round(float(a.post_mn), 3), round(float(a.post_025), 3), round(float(a.post_975), 3)] for a in g.itertuples()]
        r['elig'] = r['n'] >= MIN_VOTES
        out[jid] = r    # a justice with two SCDB codes would overwrite; none exist in SCDB
    # Martin-Quinn ranking among justices with scores
    withmq = sorted([j for j in out if 'mq' in out[j]], key=lambda j: out[j]['mq'])
    for i, j in enumerate(withmq):
        out[j]['mqRank'] = i + 1
    data = {'src': SRC, 'mqSrc': 'Martin-Quinn scores, 2021 release (terms 1937-2021), Andrew D. Martin and Kevin M. Quinn',
            'mqUrl': 'https://mqscores.quantitative.emory.edu/measures.php', 'minVotes': MIN_VOTES, 'nElig': len(elig),
            'nMq': len(withmq), 'shrink': SHRINK, 'j': out}
    kb = write_js('ratings', 'RATINGS', data) / 1024
    print(f'ratings for {len(out)} justices ({len(elig)} with >= {MIN_VOTES} votes); {kb:.0f} KB')
    for c in ['JGRoberts', 'CThomas', 'SAAlito', 'SSotomayor', 'EKagan', 'NMGorsuch', 'BMKavanaugh', 'ACBarrett', 'KBJackson', 'WJBrennan', 'AScalia', 'JMarshall', 'OWHolmes']:
        r = rows[c]
        print(f"{c:12} n={r['n']:5} lib={r['lib']} libRel={r['libRel']:+.1f} libPct={r.get('libPct')} maj={r['maj']:+.1f} sep={r['sep']:+.1f} spec={r['spec']:+.1f} overr={r.get('overr',0):+.1f}({r['nOverr']}) strike={r.get('strike',0):+.1f}({r['nStrike']}) inst={r.get('inst')} rank={r.get('instRank')}")


if __name__ == '__main__':
    main()
