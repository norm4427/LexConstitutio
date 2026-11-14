"""Fetch Supreme Court citation data from the Caselaw Access Project (Harvard Law School Library, static.case.law; public).

For every case in the U.S. Reports (vols 1-572) and the Supreme Court Reporter (vols 134-140, about 2014-2020) keep:
CAP id, citations, decision date, docket, PageRank (raw and percentile, computed by CAP over the citation graph of all
American case law), and the CAP ids of the cases it cites. Output: data/raw/cap/scotus_compact.json (raw volume files
are not kept). Safe to re-run; finished volumes are cached in data/raw/cap/vol/.
Run from the repo root:  python scripts/cap_fetch.py
"""
import json, os, time, urllib.request

OUT = 'data/raw/cap'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build script)'}
VOLS = [('us', v) for v in range(1, 573)] + [('s-ct', v) for v in range(134, 141)]


def get(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, 'code', None) == 404:
                return []
            time.sleep(10 * (attempt + 1))
    return None


def main():
    os.makedirs(f'{OUT}/vol', exist_ok=True)
    for i, (rep, v) in enumerate(VOLS):
        path = f'{OUT}/vol/{rep}-{v}.json'
        if os.path.exists(path):
            continue
        d = get(f'https://static.case.law/{rep}/{v}/CasesMetadata.json')
        if d is None:
            print('failed', rep, v, flush=True); continue
        keep = []
        for c in d:
            if (c.get('court') or {}).get('id') != 9009:      # Supreme Court of the United States
                continue
            pr = (c.get('analysis') or {}).get('pagerank') or {}
            keep.append({'id': c['id'], 'n': c.get('name_abbreviation'), 'date': c.get('decision_date'), 'dk': c.get('docket_number'),
                         'cites': [x['cite'] for x in c.get('citations', []) if x.get('type') in ('official', 'parallel')],
                         'pr': pr.get('raw'), 'pct': pr.get('percentile'),
                         'to': sorted({i for x in c.get('cites_to', []) for i in (x.get('case_ids') or [])})})
        json.dump(keep, open(path, 'w', encoding='utf-8'))
        if i % 25 == 0:
            print(f'{i}/{len(VOLS)} {rep} {v}', flush=True)
        time.sleep(0.3)
    allc = []
    for rep, v in VOLS:
        p = f'{OUT}/vol/{rep}-{v}.json'
        if os.path.exists(p):
            allc += json.load(open(p, encoding='utf-8'))
    json.dump(allc, open(f'{OUT}/scotus_compact.json', 'w', encoding='utf-8'))
    print(f'done: {len(allc)} Supreme Court cases')


if __name__ == '__main__':
    main()
