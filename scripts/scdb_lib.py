"""Shared helpers for the Supreme Court Database (SCDB) build scripts:
build_ratings.py, build_stats.py, build_models.py and add_scdb_cases.py.

Source: Harold J. Spaeth et al., Supreme Court Database, Version 2026 Release 01 (terms 1946-2025) and
Legacy Release 07 (terms 1791-1945), justice-centered data organized by citation (data/raw/scdb/csv/).
Value labels come from the SCDB online codebook, cached by scdb_codebook.py in data/raw/scdb/codebook/.
"""
import json, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = ['data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Citation.csv',
       'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv']
SRC = 'Supreme Court Database, Version 2026 Release 01 and Legacy Release 07 (Spaeth et al.)'
NUM = ['term', 'decisionType', 'petitioner', 'respondent', 'jurisdiction', 'adminAction', 'threeJudgeFdc', 'caseOrigin',
       'caseSource', 'lcDisagreement', 'certReason', 'lcDisposition', 'lcDispositionDirection', 'declarationUncon',
       'caseDisposition', 'caseDispositionUnusual', 'partyWinning', 'precedentAlteration', 'issue', 'issueArea',
       'decisionDirection', 'lawType', 'lawSupp', 'majOpinWriter', 'majVotes', 'minVotes', 'justice', 'vote', 'opinion',
       'direction', 'majority', 'firstAgreement', 'secondAgreement', 'caseSourceState', 'petitionerState', 'respondentState']
# Orally argued decisions with an opinion: signed opinion of the Court (1), orally argued per curiam (6),
# judgment of the Court (7). The usual SCDB selection for "full opinion" cases.
FULL = {1, 6, 7}


def path(p):
    return os.path.join(ROOT, p)


def load_votes():
    """One row per (case, justice). The citation-organized files repeat a justice's vote for each legal issue
    and provision; only the first row is kept."""
    frames = [pd.read_csv(path(f), encoding='latin-1', low_memory=False) for f in CSV]
    d = pd.concat(frames, ignore_index=True)
    for c in NUM:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna(subset=['justiceName'])
    d = d.drop_duplicates(['caseId', 'justiceName'], keep='first').reset_index(drop=True)
    return d


def codebook(var):
    p = path(f'data/raw/scdb/codebook/{var}.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def load_js(name):
    s = open(path(f'docs/data/{name}.js'), encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def write_js(name, glob, data):
    out = f'window.{glob}=' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';'
    open(path(f'docs/data/{name}.js'), 'w', encoding='utf-8').write(out)
    return len(out)


def justice_ids():
    """SCDB justice code (e.g. 'JGRoberts') -> justice page id, from justices.js (build_justices.py)."""
    J = load_js('justices')
    return J['byCode'], {j['id']: j for j in J['justices']}


ISSUE_AREA = {1: 'Criminal Procedure', 2: 'Civil Rights', 3: 'First Amendment', 4: 'Due Process', 5: 'Privacy',
              6: 'Attorneys', 7: 'Unions', 8: 'Economic Activity', 9: 'Judicial Power', 10: 'Federalism',
              11: 'Interstate Relations', 12: 'Federal Taxation', 13: 'Miscellaneous', 14: 'Private Action'}


def dk_norm(d):
    """Docket numbers as one key (same rule as build_votes.py)."""
    import re
    d = (str(d) if d == d else '').replace('â', '-').replace('–', '-').replace('—', '-').strip().lower()
    m = re.match(r'^(?:no\.\s*)?(\d+),?\s*orig\.?$', d) or re.match(r'^\d{2}o(\d+)$', d) or re.match(r'^(\d+)-orig$', d)
    return f'{m.group(1)}-orig' if m else re.sub(r'^no\.\s*', '', d)


def site_ids(d):
    """SCDB caseId -> case id on the site (docs/data/scotus.js), matched by U.S. Reports citation, then term + docket."""
    cases = load_js('scotus')['cases']
    by_cite, by_dk = {}, {}
    for c in cases:
        if c.get('cit') and '___' not in c['cit']:
            by_cite.setdefault(c['cit'], c['id'])
        if c.get('d') and c.get('t'):
            by_dk.setdefault((str(c['t']), dk_norm(c['d'])), c['id'])
    out = {}
    first = d.drop_duplicates('caseId')
    for r in first.itertuples():
        cit = r.usCite.strip() if isinstance(r.usCite, str) else ''
        sid = by_cite.get(cit) or by_dk.get((str(int(r.term)), dk_norm(r.docket)))
        if sid:
            out[r.caseId] = sid
    return out


def source_group(code):
    """caseSource -> the rows of the Harvard Law Review's Table II(E) (circuits by name, district, state, other)."""
    if code != code:
        return 'Other or none'
    c = int(code)
    circ = {21: 'First', 22: 'Second', 23: 'Third', 24: 'Fourth', 25: 'Fifth', 26: 'Sixth', 27: 'Seventh', 28: 'Eighth',
            29: 'Ninth', 30: 'Tenth', 31: 'Eleventh', 32: 'D.C.', 8: 'Federal'}
    if c in circ:
        return circ[c] + ' Circuit'
    if 41 <= c <= 187 or c == 20:
        return 'District courts'
    if 300 <= c <= 302:
        return 'State courts'
    if 400 <= c <= 449:
        return 'Old circuit courts'
    if c in (4, 5):
        return 'Armed Forces'
    return 'Other federal or territorial'
