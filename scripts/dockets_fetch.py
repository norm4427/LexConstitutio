"""Cache the supremecourt.gov docket page of every orally argued case decided since October Term 2004 (the period
covered by the argument transcripts), for the amicus and Solicitor General predictors in build_case_facts.py.

Source: https://www.supremecourt.gov/docket/docketfiles/html/public/<docket>.html (newer dockets) or
https://www.supremecourt.gov/search.aspx?filename=/docketfiles/<docket>.htm (older ones).
Output: data/raw/docket/hist/<docket>.html. Resumable; about 1 request per second.
Run from the repo root:  python scripts/dockets_fetch.py
"""
import os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scdb_lib import load_votes, dk_norm, FULL

OUT = 'data/raw/docket/hist'
UA = {'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0 (academic research index)'}


def get(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90)
        return r.read()
    except Exception:
        return None


def main():
    os.makedirs(OUT, exist_ok=True)
    d = load_votes()
    d = d[(d.term >= 2004) & d.decisionType.isin(FULL)].drop_duplicates('caseId')
    dks = sorted({dk_norm(k) for k in d.docket if isinstance(k, str) and k.strip()})
    n = ok = 0
    for dk in dks:
        dest = f'{OUT}/{dk}.html'
        if os.path.exists(dest):
            continue
        n += 1
        new = f'https://www.supremecourt.gov/docket/docketfiles/html/public/{dk}.html'
        old = f'https://www.supremecourt.gov/search.aspx?filename=/docketfiles/{dk}.htm'
        yy = dk.split('-')[0]
        for url in ((new, old) if yy.isdigit() and 17 <= int(yy) < 90 else (old, new)):
            b = get(url)
            time.sleep(0.9)
            if b and len(b) > 5000 and b'Docketed' in b or (b and b'DOCKETED' in b.upper()[:200000] and len(b) > 5000):
                open(dest, 'wb').write(b)
                ok += 1
                break
        if n % 50 == 0:
            print(n, 'tried', ok, 'saved', flush=True)
    print('done', n, 'tried', ok, 'saved of', len(dks), flush=True)


if __name__ == '__main__':
    main()
