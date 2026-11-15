"""Add Harvard Law Review pieces published on harvardlawreview.org (volume 120, 2006, onward) to the article index, each with
a direct link to its page on Harvard's site (and its PDF there), the way the index's older Harvard articles link to JSTOR.

Source: the site's own sitemaps (print and Forum pieces: /print/vol-N/... and /forum/vol-N/...), then each piece's page,
which states its title, authors, volume, issue, date, citation ("126 Harv. L. Rev. 1"), piece type (Article, Note, Book
Review ...), Harvard's topic tags and its summary (the page description; for some pieces the opening passage). Pages are cached in data/raw/hlr_site/ (one request a second).

Kept with the same rule build.ps1 applies to every journal: a constitutional-law subject (Harvard's topic tags stand in for
subjects), a constitutional-law term in the title, or two distinct ones in the opening text. Topics are scored the same way
(title x3, tags x2, opening text up to 3). A piece already in the index (same title and volume) is not added twice: it
gains `pub`, the link to its Harvard page, shown beside its JSTOR link.
The summary is stored in `ab` with `abx` set, so the page labels it as the journal site's summary, not an abstract.
Run from the repo root after build.ps1 and fix_indirect_links.py (before open_copies.py and fix_text.py):
    python scripts/hlr_site.py [--cached]
"""
import hashlib, html, json, os, re, sys, time, unicodedata, urllib.request

SITE = 'https://harvardlawreview.org/'
CACHE = 'data/raw/hlr_site'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
CONLAW = re.compile(r'constitution|first amendment|second amendment|fourth amendment|fifth amendment|sixth amendment|eighth amendment|ninth amendment|tenth amendment|eleventh amendment|thirteenth amendment|fourteenth amendment|fifteenth amendment|bill of rights|equal protection|due process|establishment clause|free exercise|commerce clause|spending clause|separation of powers|supreme court|judicial review|article iii|article ii\b|federalism|free speech|freedom of speech|takings clause|originalis|nondelegation|appointments clause|war powers|habeas|qualified immunity|section 1983|state action|gerrymander|voting rights|unitary executive|anticommandeering|sovereign immunity|justiciab|political question', re.I)
SUBJECTS = re.compile(r'Constitutional Law|First Amendment|Fourteenth Amendment|Supreme Court|Civil Rights|Election Law|Separation of Powers|Federalism|Equal Protection|Due Process|Second Amendment|Fourth Amendment|Free Speech|Freedom of Religion|Voting|Political Process|Federal Courts|Presidential Power|Executive Power|National Security', re.I)
JUNK = re.compile(r'^(front matter|back matter|table of contents|masthead|contents|index|errata|erratum|in memoriam|dedication|preface|announcement|staff|cover|title page|annual index|board of editors|volume information|books received|recent publications)\b', re.I)


def get(url, cached_only=False):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + '.html')
    if os.path.exists(f):
        return open(f, encoding='utf-8').read()
    if cached_only:
        return ''
    for n in range(3):
        try:
            time.sleep(1 + 5 * n)
            s = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode('utf-8', 'ignore')
            open(f, 'w', encoding='utf-8').write(s)
            return s
        except Exception as e:
            err = e
    print('  failed', url, err)
    return ''


def text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '', s)


def parse(url, page):
    one = lambda rx: (re.search(rx, page, re.S) or [None, ''])[1]
    title = text(one(r'<h1 class="single-article__title">(.*?)</h1>'))
    authors = [text(a) for a in re.findall(r'single-article__authors-link"[^>]*>(.*?)</a>', page, re.S)]
    vol = text(one(r'issue-data-list-item--volume">(.*?)</li>'))
    iss = text(one(r'issue-data-list-item--issue">(.*?)</li>'))
    date = text(one(r'issue-data-list-item--date">(.*?)</li>'))
    cite = text(one(r'single-article__citation[^>]*>(.*?)</span>'))
    kind = text(one(r'single-article__piece-type">(.*?)</span>'))
    tags = [text(t) for t in re.findall(r'single-article__topic">(.*?)</span>', page, re.S)]
    m = re.search(r'"keywords":\[(.*?)\]', page)
    if m:
        tags += [t for t in json.loads('[' + m.group(1) + ']') if t not in tags]
    desc = html.unescape(one(r'<meta property="og:description" content="(.*?)"'))
    pdf = re.findall(r'href="(https://harvardlawreview\.org/wp-content/uploads/[^"]+\.pdf)"', page)
    pdf = [p for p in pdf if 'Factsheet' not in p]
    y = re.search(r'(19|20)\d\d', date)
    fp = re.search(r'Rev\.(?: F\.)? (\d+)$', cite)
    return {'url': url, 't': title, 'a': authors, 'v': int(re.sub(r'\D', '', vol) or 0) or None,
            'i': int(re.sub(r'\D', '', iss) or 0) or None, 'y': int(y.group(0)) if y else None,
            'fp': int(fp.group(1)) if fp else None, 'kind': kind, 'tags': tags, 'ab': re.sub(r'\s+', ' ', desc).strip(),
            'pdf': pdf[0] if pdf else None, 'forum': '/forum/' in url}


def taxonomy():
    """the topic patterns from build.ps1, so topics are assigned exactly as for every other journal."""
    src = open('scripts/build.ps1', encoding='utf-8').read()
    out = []
    for m in re.finditer(r"@\{ id='(\w+)';.*?parent='\w+'; re='((?:[^']|'')*)' \}", src):
        rx = m.group(2).replace("''", "'").replace('(?<!(twenty|fifty)-)', '(?<!twenty-)(?<!fifty-)')
        out.append((m.group(1), re.compile(rx, re.I)))
    return out


def topics(tax, title, subj, ab):
    sc = {}
    for tid, rx in tax:
        s = 3 * len(rx.findall(title)) + 2 * len(rx.findall(subj)) + min(3, len(rx.findall(ab)))
        if s:
            sc[tid] = s
    best = sorted(sc.items(), key=lambda kv: -kv[1])
    tp = [k for k, v in best if v >= 2][:4] or [k for k, v in best[:1]] or ['general']
    if len(tp) > 1 and 'general' in tp:
        tp = [t for t in tp if t != 'general']
    return tp


def main():
    cached = '--cached' in sys.argv
    urls = []
    idx = get(SITE + 'sitemap_index.xml', cached)
    for sm in re.findall(r'<loc>([^<]+)</loc>', idx):
        if re.search(r'/(post|forum)-sitemap\d*\.xml$', sm):
            urls += [u for u in re.findall(r'<loc>([^<]+)</loc>', get(sm, cached)) if re.search(r'/(print|forum)/vol-\d+/[^/]+/$', u)]
    urls = sorted(set(urls))
    print(len(urls), 'print and Forum pieces in the sitemaps')
    pieces = []
    for k, u in enumerate(urls):
        p = parse(u, get(u, cached))
        if p['t']:
            pieces.append(p)
        if k % 250 == 0:
            print(f'  {k}/{len(urls)} pages read', flush=True)
    json.dump(pieces, open('data/raw/hlr_site.json', 'w', encoding='utf-8'), ensure_ascii=False)

    path = 'docs/data/articles.js'
    raw = open(path, encoding='utf-8').read()
    d = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    arts = [a for a in d['articles'] if not a['id'].startswith('hlrs-')]     # earlier runs' additions are rebuilt
    for a in arts:
        if a['j'] == 'hlr':
            a.pop('pub', None)
    have = {}
    for a in arts:
        if a['j'] == 'hlr':
            have[(norm(a['t']), a.get('v'))] = a
            have.setdefault((norm(a['t'].split(':')[0]), a.get('v')), a)
    tax = taxonomy()
    added = linked = skipped = 0
    for p in pieces:
        if JUNK.search(p['t']) or not p['v']:
            continue
        old = have.get((norm(p['t']), p['v'])) or have.get((norm(p['t'].split(':')[0]), p['v']))
        if old:
            if p['url'] not in (old.get('u') or ''):
                old['pub'] = p['url']
            linked += 1
            continue
        subj = ' | '.join(p['tags'] + [p['kind']])
        hits = {h.lower() for h in CONLAW.findall(p['ab'])}
        if not (SUBJECTS.search(subj) or CONLAW.search(p['t']) or len(hits) >= 2):
            skipped += 1
            continue
        a = {'a': p['a'], 'ab': p['ab'], 'abx': 1, 'id': 'hlrs-' + hashlib.md5(p['url'].encode()).hexdigest()[:8], 'j': 'hlr',
             't': p['t'], 'tp': topics(tax, p['t'], subj, p['ab']), 'u': p['url'], 'y': p['y'], 'v': p['v']}
        for k in ('i', 'fp', 'pdf'):
            if p[k]:
                a[k] = p[k]
        if re.search(r'book review|review essay', p['kind'], re.I):
            a['rv'] = 1
        if p['tags']:
            a['kw'] = p['tags'][:6]
        arts.append(a)
        added += 1
    d['articles'] = arts
    for j in d['journals']:
        if j['id'] == 'hlr':
            j['count'] = sum(1 for a in arts if a['j'] == 'hlr')
    open(path, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{len(pieces)} pieces read; {added} constitutional-law pieces added with direct links; {linked} already in the index '
          f'(given a link to their Harvard page); {skipped} on other subjects left out')


if __name__ == '__main__':
    main()
