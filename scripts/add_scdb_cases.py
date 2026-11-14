"""Add to docs/data/scotus.js every Supreme Court Database case (1791-2025) that the site does not list yet and that
has a case name, a U.S. Reports citation, a decision date and a recorded vote. Most are pre-1955 decisions that Oyez
does not cover; SCDB's Legacy Release 07 covers 1791-1945.

Each added case gets: id "scdb/<SCDB caseId>", name (SCDB caseName, in title case), citation (usCite), decision date,
term, docket number, `arg` if SCDB records an argument date, `con` if SCDB's law type is the Constitution
(lawType 1), and `s: 1` (from SCDB). The site builds the Library of Congress U.S. Reports PDF link (volumes 1-576) and
the Justia link from the citation. Votes come from build_votes.py, which matches SCDB rows by citation.

Re-runnable: earlier additions (ids starting "scdb/") are dropped first. Run after build_extras.pl / fix_citations.py
and before build_votes.py:  python scripts/add_scdb_cases.py
"""
import json, re
from scdb_lib import load_votes, load_js, path, dk_norm
from titlecase import titlecase


def case_name(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    t = titlecase(s.upper())
    t = re.sub(r'\bEt Al\.', 'et al.', t)
    t = re.sub(r'\bVersus\b', 'versus', t)
    t = re.sub(r'\bEx Parte\b', 'Ex parte', t)
    t = re.sub(r'\bIn Re\b', 'In re', t)
    t = re.sub(r"\bM'([a-z])", lambda m: "M'" + m.group(1).upper(), t)
    return t


def iso(mdY):
    m = re.match(r'(\d+)/(\d+)/(\d{4})', str(mdY))
    return f'{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}' if m else None


def main():
    S = load_js('scotus')
    cases = [c for c in S['cases'] if not str(c['id']).startswith('scdb/')]
    have_cit = {c['cit'] for c in cases if c.get('cit')}
    have_dk = {(str(c['t']), dk_norm(c['d'])) for c in cases if c.get('d')}
    d = load_votes()
    first = d.drop_duplicates('caseId')
    voted = set(d[d.majority.isin([1, 2]) | (d.vote == 8)].caseId)
    added, skipped = [], {'matched': 0, 'no citation': 0, 'no date': 0, 'no vote': 0, 'no name': 0, 'duplicate cite': 0}
    seen = set()
    for r in first.itertuples():
        cit = r.usCite.strip() if isinstance(r.usCite, str) else ''
        term = str(int(r.term))
        if cit in have_cit or (term, dk_norm(r.docket)) in have_dk:
            skipped['matched'] += 1; continue
        if not cit:
            skipped['no citation'] += 1; continue
        dec = iso(r.dateDecision)
        if not dec:
            skipped['no date'] += 1; continue
        if r.caseId not in voted or r.majVotes != r.majVotes:
            skipped['no vote'] += 1; continue
        if not isinstance(r.caseName, str) or not r.caseName.strip():
            skipped['no name'] += 1; continue
        if cit in seen:
            skipped['duplicate cite'] += 1; continue
        seen.add(cit)
        o = {'id': f'scdb/{r.caseId}', 'n': case_name(r.caseName), 't': term, 'y': int(dec[:4]), 'dec': dec, 'cit': cit,
             'd': str(r.docket) if r.docket == r.docket else '', 's': 1}
        if isinstance(r.dateArgument, str) and r.dateArgument.strip():
            o['arg'] = 1
        if r.lawType == 1:
            o['con'] = 1
        added.append(o)
    cases += added
    cases.sort(key=lambda c: c.get('dec') or '', reverse=True)
    S['cases'] = cases
    open(path('docs/data/scotus.js'), 'w', encoding='utf-8').write('window.SCOTUS=' + json.dumps(S, separators=(',', ':'), ensure_ascii=False) + ';')
    by_era = {}
    for o in added:
        by_era[o['y'] // 50 * 50] = by_era.get(o['y'] // 50 * 50, 0) + 1
    print(f'added {len(added)} SCDB cases (site now {len(cases)}); skipped {skipped}')
    print('added by half-century:', dict(sorted(by_era.items())))
    print('samples:', [o['n'] for o in added[:: max(1, len(added) // 8)]])


if __name__ == '__main__':
    main()
