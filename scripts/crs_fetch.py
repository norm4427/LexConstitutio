"""Download Congressional Research Service reports (public domain, U.S. government works) used for the flashcards'
"Importance" section: every Legal Sidebar (LSB) plus other reports whose titles concern the Supreme Court.
Source: EveryCRSReport.com's mirror of CRS products (reports.csv + HTML files). Cached in data/raw/crs/; safe to re-run.
Run from the repo root:  python scripts/crs_fetch.py
"""
import csv, os, re, time, urllib.request

OUT = 'data/raw/crs'
BASE = 'https://www.everycrsreport.com/'
UA = {'User-Agent': 'LexConstitutio-flashcards/1.0 (static site build script)'}


def get(url, path):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                open(path, 'wb').write(r.read())
            return True
        except Exception as e:
            if getattr(e, 'code', None) == 404:
                return False
            time.sleep(10 * (attempt + 1))
    return False


def main():
    os.makedirs(f'{OUT}/html', exist_ok=True)
    if not os.path.exists(f'{OUT}/reports.csv'):
        get(BASE + 'reports.csv', f'{OUT}/reports.csv')
    rows = list(csv.DictReader(open(f'{OUT}/reports.csv', encoding='utf-8')))
    want = [r for r in rows if r['latestHTML'] and (r['number'].startswith('LSB') or re.search(r'Supreme Court|Justice|v\. ', r['title']))]
    print(f'{len(want)} reports to fetch', flush=True)
    for i, r in enumerate(want):
        path = f"{OUT}/html/{r['number']}.html"
        if not os.path.exists(path):
            get(BASE + r['latestHTML'], path)
            time.sleep(0.25)
        if i % 200 == 0:
            print(f'{i}/{len(want)}', flush=True)
    print('done', flush=True)


if __name__ == '__main__':
    main()
