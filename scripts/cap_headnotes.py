"""Cache the reporter's head matter (headnotes / syllabus, statement of the case) for U.S. Reports cases from the
Caselaw Access Project (Harvard Law School Library, static.case.law; public domain data).

One zip per volume is read in memory; only the head matter, the official citation and the first part of the
majority opinion are kept, in data/raw/cap/head/<vol>.json. CAP keeps the reporter's headnotes for older volumes
(through roughly the 1920s) and drops the syllabus in later ones. Safe to re-run; finished volumes are skipped.
Run from the repo root:  python scripts/cap_headnotes.py [first_vol] [last_vol]
"""
import io, json, os, sys, time, urllib.request, zipfile

OUT = 'data/raw/cap/head'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build script)'}


def get(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception as e:
            if getattr(e, 'code', None) == 404:
                return None
            time.sleep(10 * (attempt + 1))
    return None


def main():
    a, b = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1, 300)
    os.makedirs(OUT, exist_ok=True)
    for v in range(a, b + 1):
        path = f'{OUT}/{v}.json'
        if os.path.exists(path):
            continue
        raw = get(f'https://static.case.law/us/{v}.zip')
        if not raw:
            print('failed', v, flush=True); continue
        keep = []
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for n in z.namelist():
                if not (n.startswith('json/') and n.endswith('.json')):
                    continue
                d = json.loads(z.read(n).decode('utf-8'))
                if (d.get('court') or {}).get('id') != 9009:
                    continue
                cb = d.get('casebody') or {}
                ops = cb.get('opinions') or []
                cite = next((c['cite'] for c in d.get('citations', []) if c.get('type') == 'official'), None)
                scdb = next((c['cite'][5:] for c in d.get('citations', []) if (c.get('cite') or '').startswith('SCDB ')), None)
                keep.append({'cap': d.get('id'), 'cite': cite, 'scdb': scdb, 'name': d.get('name_abbreviation'),
                             'date': d.get('decision_date'), 'head': cb.get('head_matter') or '',
                             'op0': (ops[0].get('text') or '')[:1500] if ops else ''})
        json.dump(keep, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        print(v, len(keep), flush=True)
        time.sleep(0.5)
    print('done', flush=True)


if __name__ == '__main__':
    main()
