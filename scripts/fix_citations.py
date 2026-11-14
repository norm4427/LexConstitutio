"""Replace "584 U.S. ___" placeholders in docs/data/scotus.js with real citations where they are now known.

The Supreme Court assigns U.S. Reports page numbers only when a bound volume is finalized, often years after the
decision; until then the case is cited "584 U.S. ___". For each such case this script uses, in order:
  1. the U.S. Reports page from the Supreme Court Database (2026 Release 01), e.g. 607 U.S. 627;
  2. otherwise the Supreme Court Reporter citation, the standard substitute (e.g. 138 S. Ct. 1612);
  3. otherwise the placeholder stays (the decision is too recent for either).
It also corrects S. Ct. citations whose volume does not match the Term (a few SCDB typos).
Run from the repo root after build_extras.pl:  python scripts/fix_citations.py   (then rebuild flashcards)
"""
import csv, json, re

FILES = ['data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Docket.csv']


def dk(d):
    return (d or '').replace('â\u0080\u0093', '-').replace('–', '-').strip().lower()


def main():
    found = {}
    for f in FILES:
        for r in csv.DictReader(open(f, encoding='latin-1')):
            key = (r['term'], dk(r['docket']))
            us, sct = r['usCite'].strip(), r['sctCite'].strip()
            prev = found.get(key, ('', ''))
            found[key] = (us if us and '_' not in us else prev[0], sct or prev[1])
    path = 'docs/data/scotus.js'
    s = open(path, encoding='utf-8').read()
    data = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    us_n = sct_n = left = 0
    for c in data['cases']:
        cit = c.get('cit') or ''
        if '___' not in cit:
            continue
        us, sct = found.get((str(c.get('t')), dk(c.get('d'))), ('', ''))
        if us:
            c['cit'] = us; us_n += 1
        elif sct:
            c['cit'] = sct; c['citUS'] = cit; sct_n += 1
        else:
            left += 1
    # a few SCDB rows carry a mistyped S. Ct. volume (e.g. Bruen as 141 S. Ct. 2111; it is 142). Since the 1990 Term each
    # Term has had one volume, numbered Term - 1879, so a recent S. Ct. citation whose volume disagrees is corrected.
    vol_fixed = 0
    for c in data['cases']:
        m = re.match(r'^(\d+) S\. Ct\. (\d+)$', c.get('cit') or '')
        t = str(c.get('t') or '')
        if m and t.isdigit() and int(t) >= 1990 and int(m.group(1)) != int(t) - 1879:
            c['cit'] = f'{int(t) - 1879} S. Ct. {m.group(2)}'; vol_fixed += 1
    print(f'S. Ct. volumes corrected: {vol_fixed}')
    open(path, 'w', encoding='utf-8').write('window.SCOTUS=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'U.S. Reports pages filled: {us_n}; cited to S. Ct. instead: {sct_n}; placeholders left (too recent): {left}')


if __name__ == '__main__':
    main()
