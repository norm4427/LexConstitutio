"""Cache value labels for Supreme Court Database variables from the SCDB online codebook
(http://scdb.wustl.edu/documentation.php?var=<name>) into data/raw/scdb/codebook/<name>.json.
Run from the repo root:  python scripts/scdb_codebook.py
"""
import json, os, re, time, urllib.request, html

VARS = ['caseSource', 'caseOrigin', 'petitioner', 'respondent', 'certReason', 'lcDisposition', 'lcDispositionDirection',
        'jurisdiction', 'lawType', 'issueArea', 'issue', 'caseDisposition', 'decisionType', 'precedentAlteration',
        'declarationUncon', 'decisionDirection', 'vote', 'adminAction']
OUT = 'data/raw/scdb/codebook'


def fetch(var):
    path = f'{OUT}/{var}.json'
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    req = urllib.request.Request(f'http://scdb.wustl.edu/documentation.php?var={var}', headers={'User-Agent': 'LexConstitutio/1.0'})
    page = urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')
    part = page[page.find('Values:'):]
    vals = {}
    for a, b in re.findall(r'<tr>\s*<td[^>]*>\s*([0-9.]+)\s*</td>\s*<td[^>]*>(.*?)</td>', part, re.S):
        vals.setdefault(a, re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', b))).strip())
    json.dump(vals, open(path, 'w', encoding='utf-8'), indent=0, ensure_ascii=False)
    time.sleep(1)
    return vals


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for v in VARS:
        print(v, len(fetch(v)))
