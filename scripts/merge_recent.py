"""Add the pieces the repository and WordPress journals published since the last full build.

Input: data/raw/recent_articles.js, built by build.ps1 from the records harvest_recent.sh fetched
       (powershell -File scripts/build.ps1 -SourcesFile data/raw/recent_sources.tsv -OutFile data/raw/recent_articles.js)
A piece is added only when the index has nothing from the same journal with the same title (case and punctuation aside);
pieces already there are left exactly as they are. Ids get an "r" suffix so they never collide with the full build's.
Run from the repo root, then hlr_site.py / journal_sites.py / the fix steps as usual:  python scripts/merge_recent.py
"""
import json, re, unicodedata


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '', s)


def load(p):
    s = open(p, encoding='utf-8').read()
    return s.split('=', 1)[0], json.loads(s.split('=', 1)[1].rstrip().rstrip(';'))


def main():
    head, d = load('docs/data/articles.js')
    _, n = load('data/raw/recent_articles.js')
    have = {(a['j'], norm(a['t'])) for a in d['articles']}
    ids = {a['id'] for a in d['articles']}
    added = {}
    for a in n['articles']:
        k = (a['j'], norm(a['t']))
        if k in have or len(norm(a['t'])) < 6:
            continue
        have.add(k)
        a = dict(a)
        a['id'] = a['id'] + 'r'
        while a['id'] in ids:
            a['id'] += 'r'
        ids.add(a['id'])
        d['articles'].append(a)
        added[a['j']] = added.get(a['j'], 0) + 1
    for j in d['journals']:
        j['count'] = sum(1 for a in d['articles'] if a['j'] == j['id'])
    open('docs/data/articles.js', 'w', encoding='utf-8').write(head + '=' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{sum(added.values())} new pieces added:', ', '.join(f'{j} {c}' for j, c in sorted(added.items(), key=lambda x: -x[1])))


if __name__ == '__main__':
    main()
