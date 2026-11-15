"""Free full text for Law and Contemporary Problems articles: Duke Law School posts every issue of its journal free at
scholarship.law.duke.edu/lcp/. Each article in the index is looked up in its own volume and issue's table of contents there
(all issues of the volume when the index has no issue number) and linked only when an entry has the same title, so a copy
is never attached to the wrong article. Sets `oa` (the article's page in Duke's repository, which offers the PDF) and
`oav` = publishedVersion. Pages are cached in data/raw/lcp/.
Run from the repo root after open_copies.py (before fix_text.py):  python scripts/lcp_copies.py
"""
import hashlib, html, json, os, re, time, unicodedata, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
BASE = 'https://scholarship.law.duke.edu/lcp/'


def get(url):
    os.makedirs('data/raw/lcp', exist_ok=True)
    f = 'data/raw/lcp/' + hashlib.md5(url.encode()).hexdigest() + '.html'
    if os.path.exists(f):
        return open(f, encoding='utf-8').read()
    time.sleep(1.5)
    try:
        s = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode('utf-8', 'ignore')
    except Exception:
        return ''
    open(f, 'w', encoding='utf-8').write(s)
    return s


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', html.unescape(s or '')) if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '', s)


def main():
    path = 'docs/data/articles.js'
    raw = open(path, encoding='utf-8').read()
    d = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    found = missed = 0
    for a in d['articles']:
        if a['j'] != 'lcp' or not a.get('v'):
            continue
        hit = None
        for i in ([a['i']] if a.get('i') else [1, 2, 3, 4]):
            toc = get(f"{BASE}vol{a['v']}/iss{i}/")
            for u, t in re.findall(r'href="(' + re.escape(BASE) + r'vol\d+/iss\d+/\d+)/?"[^>]*title="([^"]*)"', toc):
                if norm(t) == norm(a['t']) or (len(norm(a['t'])) > 30 and norm(t).startswith(norm(a['t']))):
                    hit = u
                    break
            if hit:
                break
        if hit:
            a['oa'], a['oav'] = hit, 'publishedVersion'
            found += 1
        else:
            missed += 1
    open(path, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'Law and Contemporary Problems: {found} articles linked to their free copy at Duke; {missed} not matched')


if __name__ == '__main__':
    main()
