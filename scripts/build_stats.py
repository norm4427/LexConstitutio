"""Build docs/data/stats.js (one summary per Term, 1791-2025) and docs/data/stcases-<decade>.js (every full-opinion case
with its direction and institutionalism class), modeled on the Harvard Law Review's annual "The Statistics"
(e.g. The Supreme Court, 2024 Term -- The Statistics, 139 Harv. L. Rev. 430 (2025)).

All figures are computed from the Supreme Court Database (scdb_lib.py). Cases counted: orally argued decisions with an
opinion (SCDB decisionType 1, 6, 7), the usual SCDB stand-in for HLR's "full opinions". Differences from HLR, which
codes the opinions itself: SCDB records at most one opinion per justice per case; "agreement" here means voting on the
same side of the disposition (HLR's tables count joining the same opinion); unanimous = no dissenting vote and no
concurrence in the judgment only (`vote` 4).

Tables per Term
  I(A)  opinions of the Court, concurrences, dissents written; dissenting votes       (majOpinWriter, opinion, vote, majority)
  I(B)  agreement in the disposition, every pair of justices, all cases and nonunanimous cases
  I(C)  unanimous / unanimous with a concurrence in the judgment / with a dissent
  I(D)  nonunanimous cases: joined the opinion of the Court (`vote` 1, 3 or 5) and voted with the majority
  I(E)  5-4 decisions by the justices in the majority, and the most frequent majorities in divided cases
  II(D/E) cases on certiorari (`jurisdiction` 1): reversed (incl. in part) / vacated / affirmed, by lower court
  III   subject matter (`issueArea`), with decision direction (`decisionDirection`)
  Case classes  direction: liberal / conservative / unspecifiable (decisionDirection)
                institutionalism index 0-3: one point each for not altering precedent (`precedentAlteration` 0),
                not declaring any law unconstitutional (`declarationUncon` 1) and deciding without dissent (`minVotes` 0)
Run from the repo root:  python scripts/build_stats.py
"""
import collections, glob, os
import numpy as np
from scdb_lib import load_votes, justice_ids, site_ids, source_group, write_js, load_js, path, FULL, ISSUE_AREA, SRC
from add_scdb_cases import case_name


def disp_class(x):
    if x in (3, 4, 6, 7): return 0    # reversed, incl. reversed in part
    if x in (5, 8): return 1          # vacated
    if x == 2: return 2               # affirmed
    return 3


def main():
    d = load_votes()
    d = d[d.decisionType.isin(FULL)].copy()
    code2id, jinfo = justice_ids()
    sid = site_ids(d)
    site_name = {c['id']: c['n'] for c in load_js('scotus')['cases']}
    names = {}
    for code, jid in code2id.items():
        names[code] = [jinfo[jid]['last'], jid]
    terms, series, cases_by_dec = [], [], collections.defaultdict(list)
    for term, T in d.groupby('term'):
        term = int(term)
        cs = T.drop_duplicates('caseId').set_index('caseId')
        # roster: chief first, then by SCDB justice number (assigned in order of appointment)
        chief_name = cs.chief.mode().iloc[0] if len(cs) else ''
        jn = T.groupby('justiceName').justice.min().sort_values()
        roster = list(jn.index)
        chief_code = next((c for c in roster if c.endswith(chief_name) or chief_name in c), None)
        if chief_code:
            roster.remove(chief_code); roster.insert(0, chief_code)
        ri = {c: i for i, c in enumerate(roster)}
        # case-level flags
        spec = T[T.vote == 4].groupby('caseId').size()
        dis = T[T.majority == 1].groupby('caseId').size()
        cs['nspec'] = spec.reindex(cs.index).fillna(0)
        cs['ndis'] = dis.reindex(cs.index).fillna(0)
        cs['unan'] = (cs.ndis == 0) & (cs.nspec == 0)
        cs['unanConc'] = (cs.ndis == 0) & (cs.nspec > 0)
        n = len(cs)
        # I(A)
        A = []
        for c in roster:
            v = T[T.justiceName == c]
            own = v.set_index('caseId')
            opc = int((cs.majOpinWriter == v.justice.iloc[0]).sum())
            wrote = own[(own.opinion.isin([2, 3])) & (own.justice != cs.majOpinWriter.reindex(own.index))]
            conc = int(wrote.vote.isin([3, 4]).sum()); diss = int(wrote.vote.isin([2, 6, 7]).sum())
            dvotes = int((own.majority == 1).sum())
            nonun = own[~cs.unan.reindex(own.index).astype(bool)]
            A.append([ri[c], opc, conc, diss, dvotes, int(len(own)), int(len(nonun)), int(nonun.vote.isin([1, 3, 5]).sum()), int((nonun.majority == 2).sum())])
        pc = int((cs.decisionType == 6).sum())
        # I(B)
        side = T.pivot_table(index='caseId', columns='justiceName', values='majority', aggfunc='first').reindex(columns=roster)
        nonunan_ids = cs.index[~cs.unan]
        k = len(roster)
        Ball = [[None] * k for _ in range(k)]; Bnon = [[None] * k for _ in range(k)]
        S = side.values
        nmask = side.index.isin(nonunan_ids)
        for i in range(k):
            for j in range(k):
                if i == j: continue
                both = (S[:, i] == S[:, i]) & (S[:, j] == S[:, j]) & np.isin(S[:, i], [1, 2]) & np.isin(S[:, j], [1, 2])
                agree = both & (S[:, i] == S[:, j])
                Ball[i][j] = [int(agree.sum()), int(both.sum())]
                Bnon[i][j] = [int((agree & nmask).sum()), int((both & nmask).sum())]
        # I(C)
        C = [int(cs.unan.sum()), int(cs.unanConc.sum()), int((cs.ndis > 0).sum())]
        # splits and coalitions
        splits = collections.Counter()
        five4, coal = collections.Counter(), collections.Counter()
        majsets = T[T.majority == 2].groupby('caseId').justiceName.apply(lambda s: tuple(sorted(ri[x] for x in s)))
        for cid, r in cs.iterrows():
            if r.majVotes == r.majVotes:
                splits[f'{int(r.majVotes)}-{int(r.minVotes if r.minVotes == r.minVotes else 0)}'] += 1
            ms = majsets.get(cid)
            if ms is None: continue
            if r.ndis > 0: coal[ms] += 1
            if r.majVotes == 5 and r.minVotes == 4: five4[ms] += 1
        # II(D/E)
        cert = cs[cs.jurisdiction == 1]
        disp = collections.defaultdict(lambda: [0, 0, 0, 0])
        for r in cert.itertuples():
            disp[source_group(r.caseSource)][disp_class(r.caseDisposition)] += 1
        # III and direction
        subj = collections.defaultdict(lambda: [0, 0, 0])
        for r in cs.itertuples():
            a = int(r.issueArea) if r.issueArea == r.issueArea else 0
            subj[a][0 if r.decisionDirection == 2 else 1 if r.decisionDirection == 1 else 2] += 1
        dirc = [int((cs.decisionDirection == 2).sum()), int((cs.decisionDirection == 1).sum()), int((~cs.decisionDirection.isin([1, 2])).sum())]
        # institutionalism classes
        cs['overr'] = cs.precedentAlteration == 1
        cs['strike'] = cs.declarationUncon.where(cs.declarationUncon.isin([2, 3, 4]), 0).astype(int)
        cs['inst'] = (~cs.overr).astype(int) + (cs.strike == 0).astype(int) + (cs.ndis == 0).astype(int)
        inst = [int((cs.inst == v).sum()) for v in range(4)]
        I = {'overr': int(cs.overr.sum()), 'fed': int((cs.strike == 2).sum()), 'state': int((cs.strike == 3).sum()), 'local': int((cs.strike == 4).sum()), 'idx': inst}
        for cid, r in cs.sort_values('dateDecision').iterrows():
            a = int(r.issueArea) if r.issueArea == r.issueArea else 0
            dd = 'L' if r.decisionDirection == 2 else 'C' if r.decisionDirection == 1 else 'U'
            cases_by_dec[term // 10 * 10].append([term, sid.get(cid, ''), site_name.get(sid.get(cid)) or (case_name(r.caseName) if isinstance(r.caseName, str) else ''), r.usCite if isinstance(r.usCite, str) else '',
                                                  r.dateDecision, int(r.majVotes) if r.majVotes == r.majVotes else None, int(r.minVotes) if r.minVotes == r.minVotes else 0,
                                                  dd, int(r.inst), int(r.overr), int(r.strike), a, cid])
        rev = [sum(v[0] for v in disp.values()), sum(v[1] for v in disp.values()), sum(v[2] for v in disp.values())]
        terms.append({'t': term, 'n': n, 'pc': pc, 'chief': chief_name, 'roster': [[c] + names.get(c, [c, '']) for c in roster],
                      'A': A, 'Ball': Ball, 'Bnon': Bnon, 'C': C, 'splits': dict(splits),
                      'five4': [[list(m), c] for m, c in five4.most_common()], 'coal': [[list(m), c] for m, c in coal.most_common(5)],
                      'disp': dict(disp), 'subj': {str(k): v for k, v in sorted(subj.items())}, 'dir': dirc, 'inst': I})
        cert_n = sum(rev)
        series.append([term, n, round(100 * C[0] / n, 1) if n else None, five4.total() if hasattr(five4, 'total') else sum(five4.values()),
                       round(100 * dirc[0] / max(1, dirc[0] + dirc[1]), 1), round(100 * (rev[0] + rev[1]) / cert_n, 1) if cert_n else None,
                       I['overr'], I['fed'] + I['state'] + I['local']])
    for f in glob.glob(path('docs/data/stcases-*.js')):
        os.remove(f)
    for dec, rows in cases_by_dec.items():
        write_js(f'stcases-{dec}', f'STCASES_{dec}', rows)
    data = {'src': SRC, 'areas': {str(k): v for k, v in ISSUE_AREA.items()},
            'series': series, 'terms': terms}
    kb = write_js('stats', 'STATS', data) / 1024
    print(f'{len(terms)} terms ({terms[0]["t"]}-{terms[-1]["t"]}); stats.js {kb:.0f} KB; {sum(len(v) for v in cases_by_dec.values())} cases in {len(cases_by_dec)} decade files')
    last = terms[-1]
    print('OT', last['t'], 'cases', last['n'], 'unan', last['C'], 'splits', last['splits'], 'dir', last['dir'], 'inst', last['inst'])
    print('5-4', last['five4']); print('disp', last['disp'])
    print([(last['roster'][a[0]][1], a[1:]) for a in last['A']])


if __name__ == '__main__':
    main()
