"""Merge high-impact articles from the additional journals (scripts/sources_new.tsv) into docs/data/articles.js.

Input: data/raw/new_articles.js (build.ps1 -SourcesFile scripts/sources_new.tsv -OutFile data/raw/new_articles.js)
       data/raw/lrc/cites.json  (cite_lookup.py)
High impact: an article is kept only if its OpenAlex citations reach the 75th percentile of the existing index's
articles from the same decade (and at least 3). Articles without a citation count are left out until one is found.
Each run first removes earlier merges of these journals, so it can be re-run as cite_lookup.py finds more counts.
Run from the repo root:  python scripts/merge_new.py
"""
import collections, json, sys

sys.path.insert(0, 'scripts')
from titlecase import titlecase


def load(path):
    s = open(path, encoding='utf-8').read()
    return s[:s.index('=') + 1], json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def main():
    head, d = load('docs/data/articles.js')
    _, n = load('data/raw/new_articles.js')
    cites = json.load(open('data/raw/lrc/cites.json', encoding='utf-8'))
    new_ids = {j['id'] for j in n['journals']}
    base = [a for a in d['articles'] if a['j'] not in new_ids]
    byd = collections.defaultdict(list)
    for a in base:
        if a.get('c') is not None and a.get('y') and not a.get('rv'):
            byd[a['y'] // 10 * 10].append(a['c'])
    p75 = {dec: sorted(v)[int(.75 * (len(v) - 1))] for dec, v in byd.items()}
    seen = {(a['j'], a['t'].lower()) for a in base}
    kept, unknown, low = [], 0, 0
    for a in n['articles']:
        c = a.get('c')
        if c is None:
            c = cites.get(a['id'])
        if c is None:
            unknown += 1; continue
        need = max(3, p75.get((a.get('y') or 2000) // 10 * 10, 3))
        if c < need or a.get('rv'):
            low += 1; continue
        a = dict(a, c=c, t=titlecase(a['t']))
        if (a['j'], a['t'].lower()) in seen:
            continue
        kept.append(a)
    counts = collections.Counter(a['j'] for a in kept)
    journals = [j for j in d['journals'] if j['id'] not in new_ids]
    for j in n['journals']:
        if counts[j['id']]:
            journals.append(dict(j, count=counts[j['id']], added=1))
    d['journals'] = journals
    d['articles'] = sorted(base + kept, key=lambda a: -(a.get('y') or 0))
    open('docs/data/articles.js', 'w', encoding='utf-8').write(head + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'kept {len(kept)} high-impact articles from {len(counts)} journals; below the bar {low}; no citation count yet {unknown}')
    print('  ' + '; '.join(f'{j["name"]} {counts[j["id"]]}' for j in n['journals'] if counts[j['id']]))


if __name__ == '__main__':
    main()
