"""Cache the opinion text of Supreme Court cases from the Caselaw Access Project's static volume zips (static.case.law,
Harvard Law School Library; the opinions are public domain). One gzipped JSON per volume:
data/raw/cap/text/<reporter>-<vol>.json.gz = [{id, cite, date, name, ops: [{type, author, text}]}], where type is CAP's
opinion type (majority, concurrence, dissent, concurring-in-part-and-dissenting-in-part, ...). The zips are not kept.
Default range: U.S. Reports vols 150-572 (1893-2014) and S. Ct. vols 134-140 (2014-2020), the years in which the Court
cites law reviews. Safe to re-run; finished volumes are skipped.
Run from the repo root:  python scripts/cap_text_fetch.py [first_us_vol last_us_vol]
"""
import gzip, io, json, os, sys, time, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor

OUT = 'data/raw/cap/text'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}


def one(rv):
    rep, v = rv
    path = f'{OUT}/{rep}-{v}.json.gz'
    if os.path.exists(path):
        return rv, 'cached'
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(f'https://static.case.law/{rep}/{v}.zip', headers=UA), timeout=300) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            break
        except Exception as e:
            if getattr(e, 'code', None) == 404:
                return rv, 'missing'
            time.sleep(15 * (attempt + 1))
    else:
        return rv, 'failed'
    out = []
    for n in z.namelist():
        if not (n.startswith('json/') and n.endswith('.json')):
            continue
        d = json.loads(z.read(n))
        if (d.get('court') or {}).get('id') != 9009:
            continue
        cb = d.get('casebody') or {}
        out.append({'id': d.get('id'), 'cite': next((c['cite'] for c in d.get('citations') or [] if c.get('type') == 'official'), ''),
                    'date': d.get('decision_date'), 'name': d.get('name_abbreviation'),
                    'ops': [{'type': o.get('type'), 'author': o.get('author'), 'text': o.get('text') or ''} for o in cb.get('opinions') or []]})
    with gzip.open(path + '.tmp', 'wt', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(path + '.tmp', path)
    time.sleep(0.5)
    return rv, len(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    a, b = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (150, 572)
    vols = [('us', v) for v in range(a, b + 1)] + ([('s-ct', v) for v in range(134, 141)] if len(sys.argv) <= 2 else [])
    done = 0
    with ThreadPoolExecutor(3) as ex:
        for rv, r in ex.map(one, vols):
            done += 1
            if r in ('failed', 'missing') or done % 25 == 0:
                print(done, '/', len(vols), rv, r, flush=True)
    print('done', flush=True)


if __name__ == '__main__':
    main()
