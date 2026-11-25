"""Free full text from the journals' own school-hosted back-issue archives, the way lcp_copies.py does for Duke's LCP.

Sources (each read from a structured listing, cached in data/raw/archive_copies/<source>/):
  calr    Berkeley Law's lawcat repository, OAI-PMH set berkeleylawjournals (MARC: journal, volume, issue, first page).
          Only records with a full-text file (MARC 856 .../files/...) count; about 30 main articles a volume, no notes.
          Links the lawcat record page (https://lawcat.berkeley.edu/record/N), which offers the PDF.
  ylj     Yale Law School's openyls repository, OAI-PMH collection "Yale Law Journal" (DSpace dim: volume and issue from
          the legacy ylj/volV/issI path, issue date). Links the item's handle page on openyls.
  pennlr  Penn Carey Law's repository (repository.law.upenn.edu, Quartex; no OAI-PMH). Its public sitemap lists every
          document by title slug; a document page is fetched only when its slug matches one of our titles, and its meta
          description gives the citation ("109 U. Pa. L. Rev. 992"). Links the document page.
  jclc, utahlr, smulr   Northwestern's, Utah's and SMU's bepress archives (OAI-PMH, dcq: volume and issue from the
          article path).
Matching errs toward leaving a link out: same journal and volume; same first page where the archive gives one (otherwise
the same issue when both sides have one); the normalized title equal (or, for titles over 30 characters, one a prefix of
the other); the year within one where the archive gives one; and exactly one archive record left after all of that.
Archives checked and not used are listed in the notes at the bottom of this file.

    python scripts/archive_copies.py lookup [source ...]   # fetch and cache the listings (about one request a second)
    python scripts/archive_copies.py apply --dry-run       # counts per journal and 15 random matches; writes nothing
    python scripts/archive_copies.py apply                 # sets oa / oav on DOI-only articles without a free route
`apply` touches only articles with no `oa`, `pdf` or `pub` that are not book reviews, sets `oa` and `oav` =
publishedVersion and nothing else, and keeps articles.js's serialization. Matches are also kept in
data/raw/archive_copies/found.json. Run after open_copies.py (which clears `oa`).
"""
import glob, hashlib, html, json, os, random, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
ART = 'docs/data/articles.js'
RAW = 'data/raw/archive_copies'
_last = [0.0]


def fetch(url, data=None):
    """One polite request (about one a second); returns text or '' on failure."""
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for t in range(3):
        try:
            _last[0] = time.time()
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA, data=data), timeout=120)
            return r.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return ''
            time.sleep(5 + 10 * t)
        except Exception:
            time.sleep(5 + 10 * t)
    return ''


def cached(sub, url):
    d = os.path.join(RAW, sub)
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, hashlib.md5(url.encode()).hexdigest() + '.html')
    if os.path.exists(f):
        return open(f, encoding='utf-8').read()
    s = fetch(url)
    if s:
        open(f, 'w', encoding='utf-8').write(s)
    return s


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', html.unescape(s or '')) if not unicodedata.combining(c)).lower()
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s[3:] if s.startswith('the') and len(s) > 10 else s


def same_title(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) > 30 and (a.startswith(b) or b.startswith(a)))


def num(s):
    m = re.search(r'\d+', str(s or ''))
    return int(m.group()) if m else None


# ---------------------------------------------------------------- OAI-PMH harvesting (resumable, page by page)

def harvest(src, base, prefix, oai_set):
    d = os.path.join(RAW, src)
    os.makedirs(d, exist_ok=True)
    if os.path.exists(os.path.join(d, 'DONE')):
        print(f'{src}: already harvested')
        return
    pages = sorted(glob.glob(os.path.join(d, 'p*.xml')))
    token = None
    if pages:
        m = re.search(r'<resumptionToken[^>]*>([^<]+)</resumptionToken>', open(pages[-1], encoding='utf-8').read())
        token = html.unescape(m.group(1)) if m else None
        if not token:
            open(os.path.join(d, 'DONE'), 'w').write('')
            return
    k = len(pages)
    while True:
        if token:
            url = f'{base}?verb=ListRecords&resumptionToken={urllib.parse.quote(token, safe="")}'
        else:
            url = f'{base}?verb=ListRecords&metadataPrefix={prefix}&set={urllib.parse.quote(oai_set, safe="")}'
        s = fetch(url)
        if 'badResumptionToken' in s and pages:
            print(f'{src}: resumption token expired; restarting the harvest')
            for p in glob.glob(os.path.join(d, 'p*.xml')):
                os.remove(p)
            token, k, pages = None, 0, []
            continue
        if '<OAI-PMH' not in s:
            print(f'{src}: failed at page {k}; rerun lookup to resume')
            return
        open(os.path.join(d, f'p{k:04d}.xml'), 'w', encoding='utf-8').write(s)
        k += 1
        m = re.search(r'<resumptionToken([^>]*)>([^<]*)</resumptionToken>', s)
        size = re.search(r'completeListSize="(\d+)"', m.group(1)) if m else None
        if k % 10 == 0:
            print(f'  {src}: page {k}' + (f' (of {size.group(1)} records)' if size else ''), flush=True)
        if not m or not m.group(2).strip():
            break
        token = html.unescape(m.group(2).strip())
    open(os.path.join(d, 'DONE'), 'w').write('')
    print(f'{src}: {k} pages harvested')


def records(src):
    for p in sorted(glob.glob(os.path.join(RAW, src, 'p*.xml'))):
        for r in re.findall(r'<record>.*?</record>', open(p, encoding='utf-8').read(), re.S):
            if 'status="deleted"' not in r:
                yield r


def berkeley():
    """California Law Review articles in lawcat: {v, i, fp, y, t, url}."""
    out = []
    for r in records('calr'):
        f = {}
        for tag, body in re.findall(r'<marc:datafield tag="(\d+)"[^>]*>(.*?)</marc:datafield>', r, re.S):
            sub = {c: html.unescape(v) for c, v in re.findall(r'<marc:subfield code="(.)">([^<]*)</marc:subfield>', body)}
            f.setdefault(tag, []).append(sub)
        j = (f.get('773') or [{}])[0]
        if (j.get('t') or '').strip() != 'California Law Review' or not any('/files/' in (x.get('u') or '') for x in f.get('856') or []):
            continue                  # other journals, and catalog-only records with no full-text file
        rid = re.search(r'<marc:controlfield tag="001">(\d+)<', r)
        t = (f.get('245') or [{}])[0]
        date = ((f.get('264') or f.get('269') or [{}])[0]).get('c') or ((f.get('269') or [{}])[0]).get('a') or ''
        y = re.search(r'(1[89]|20)\d\d', date)
        out.append({'v': num(j.get('j')), 'i': num(j.get('k')), 'fp': num(j.get('q')), 'y': int(y.group()) if y else None,
                    't': ' '.join(x for x in (t.get('a'), t.get('b')) if x).strip(' /:'),
                    'url': f'https://lawcat.berkeley.edu/record/{rid.group(1)}'})
    return out


def yale():
    out = []
    for r in records('ylj'):
        fld = lambda el, q=None: [html.unescape(v) for a, v in re.findall(r'<dim:field ([^>]*)>([^<]*)</dim:field>', r)
                                  if f'element="{el}"' in a and ((f'qualifier="{q}"' in a) if q else 'qualifier=' not in a)]
        path = next((x for x in fld('identifier') if re.match(r'ylj/vol\d+/iss\d+', x)), '')
        m = re.match(r'ylj/vol(\d+)/iss(\d+)', path)
        uri = next((x for x in fld('identifier', 'uri') if 'handle' in x), '')
        h = re.search(r'(20\.500\.13051/\d+)', uri)
        if not m or not h:
            continue
        fp = num((fld('citation', 'spage') or [''])[0])
        out.append({'v': int(m.group(1)), 'i': int(m.group(2)), 'fp': fp, 'y': num((fld('date', 'issued') or [''])[0][:4]),
                    't': (fld('title') or [''])[0], 'url': f'https://openyls.law.yale.edu/handle/{h.group(1)}'})
    return out


def bepress(src, host, path):
    out = []
    for r in records(src):
        ident = re.search(r'<dc:identifier>(https?://[^<]*/' + path + r'/vol(\d+)/iss(\d+)/\d+)</dc:identifier>', r)
        if not ident:
            continue
        t = re.search(r'<dc:title>([^<]*)</dc:title>', r)
        y = re.search(r'<dc:date(?:\.created)?>(\d{4})', r)
        out.append({'v': int(ident.group(2)), 'i': int(ident.group(3)), 'fp': None, 'y': int(y.group(1)) if y else None,
                    't': html.unescape(t.group(1)) if t else '', 'url': ident.group(1).replace('http://', 'https://') + '/'})
    return out


BEPRESS = {   # our journal id -> (OAI base, set, path in the article URL)
    'jclc': ('https://scholarlycommons.law.northwestern.edu/do/oai/', 'publication:jclc', 'jclc'),
    'utahlr': ('https://dc.law.utah.edu/do/oai/', 'publication:ulr', 'ulr'),
    'smulr': ('https://scholar.smu.edu/do/oai/', 'publication:smulr', 'smulr'),
}

# ---------------------------------------------------------------- Penn (sitemap + document pages)

PENN = 'https://repository.law.upenn.edu'


def penn_sitemap():
    idx = cached('pennlr', PENN + '/sitemap.xml')
    docs = []
    for loc in re.findall(r'<loc>([^<]*type=DOCUMENT[^<]*)</loc>', idx):
        s = cached('pennlr', html.unescape(loc))
        docs += re.findall(r'<loc>(https://repository\.law\.upenn\.edu/Documents/Detail/([^/<]+)/\d+)</loc>', s)
    return docs                       # [(url, slug)]


def penn_page(url):
    """Citation from a document page's meta description: '..., University of Pennsylvania Law Review, 109 U. Pa. L. Rev. 992, UPLR 109.7'."""
    s = cached('pennlr', url)
    m = re.search(r'<meta name="description" content="([^"]*)"', s)
    if not m:
        return None
    desc = html.unescape(m.group(1))
    c = re.search(r'(\d+)\s+U\.\s*Pa\.\s*L\.\s*Rev\.\s+(\d+)', desc)
    t = re.search(r'\btitle:\s*"((?:[^"\\]|\\.)*)"', s)
    if not c or 'University of Pennsylvania Law Review' not in desc:
        return None
    iss = re.search(r'UPLR \d+\.(\d+)', desc)
    return {'v': int(c.group(1)), 'fp': int(c.group(2)), 'i': int(iss.group(1)) if iss else None, 'y': None,
            't': json.loads('"' + t.group(1) + '"') if t else desc.split(',')[0], 'url': url}


def penn_lookup(arts):
    docs = penn_sitemap()
    by = {}
    for url, slug in docs:
        by.setdefault(norm(slug.replace('-', ' ')), []).append(url)
    todo = set()
    for a in candidates(arts):
        if a['j'] != 'pennlr':
            continue
        n = norm(a['t'])
        hits = by.get(n, [])
        if not hits and len(n) > 30:
            hits = [u for k, us in by.items() if min(len(k), len(n)) > 30 and (k.startswith(n) or n.startswith(k)) for u in us]
        todo.update(hits[:8])
    print(f'pennlr: {len(docs)} documents in the sitemap; {len(todo)} pages to check', flush=True)
    for k, u in enumerate(sorted(todo)):
        penn_page(u)
        if k % 100 == 0:
            print(f'  pennlr: {k}/{len(todo)}', flush=True)


def penn():
    out = []
    d = os.path.join(RAW, 'pennlr')
    if not os.path.isdir(d):
        return out
    for url, _ in penn_sitemap():
        if os.path.exists(os.path.join(d, hashlib.md5(url.encode()).hexdigest() + '.html')):
            r = penn_page(url)
            if r:
                out.append(r)
    return out

# ---------------------------------------------------------------- matching and apply


def load():
    raw = open(ART, encoding='utf-8').read()
    return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def candidates(arts):
    return [a for a in arts if not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv')
            and (a.get('u') or '').startswith('https://doi.org/')]


def archive(j):
    if j == 'calr':
        return berkeley()
    if j == 'ylj':
        return yale()
    if j == 'pennlr':
        return penn()
    if j in BEPRESS:
        return bepress(j, BEPRESS[j][0], BEPRESS[j][2])
    return []


def match(a, recs):
    hits = []
    for r in recs:
        if r['v'] != a.get('v') or not same_title(r['t'], a['t']):
            continue
        if r['fp'] and a.get('fp'):
            if r['fp'] != a['fp']:
                continue
        elif r['i'] and a.get('i') and r['i'] != a['i']:
            continue
        if r['y'] and a.get('y') and abs(r['y'] - a['y']) > 1:
            continue
        hits.append(r)
    urls = {r['url'] for r in hits}
    if len(urls) > 1:                           # prefer the one whose first page agrees, if exactly one does
        fp = {r['url'] for r in hits if r['fp'] and r['fp'] == a.get('fp')}
        urls = fp if len(fp) == 1 else set()
    return next((r for r in hits if r['url'] in urls), None) if len(urls) == 1 else None


def lookup(srcs):
    _, data = load()
    arts = data['articles']
    want = {a['j'] for a in candidates(arts)}
    srcs = srcs or ['calr', 'ylj', 'pennlr'] + list(BEPRESS)
    for s in srcs:
        if s not in want:
            print(f'{s}: no DOI-only articles left; skipped')
        elif s == 'calr':
            harvest('calr', 'https://lawcat.berkeley.edu/oai2d', 'marcxml', 'berkeleylawjournals')
        elif s == 'ylj':
            harvest('ylj', 'https://openyls.law.yale.edu/server/oai/request', 'dim', 'col_20.500.13051_12')
        elif s == 'pennlr':
            penn_lookup(arts)
        elif s in BEPRESS:
            harvest(s, BEPRESS[s][0], 'dcq', BEPRESS[s][1])


def apply(dry):
    raw, data = load()
    arts = data['articles']
    cand = candidates(arts)
    js = sorted({a['j'] for a in cand})
    recs = {j: archive(j) for j in js}
    found, per, samples = {}, {}, []
    used = {}
    for a in cand:
        r = match(a, recs[a['j']]) if recs[a['j']] else None
        if not r:
            continue
        if r['url'] in used:                    # one archive record claimed by two of our articles: leave both out
            found.pop(used[r['url']], None)
            used[r['url']] = None
            continue
        used[r['url']] = a['id']
        found[a['id']] = {'url': r['url'], 'title': r['t'], 'j': a['j']}
    for a in cand:
        f = found.get(a['id'])
        if f:
            per[a['j']] = per.get(a['j'], 0) + 1
            samples.append((a, f))
    print('archive records:', {j: len(r) for j, r in recs.items() if r})
    for j in sorted({a['j'] for a in cand}, key=lambda j: -sum(1 for a in cand if a['j'] == j)):
        n = sum(1 for a in cand if a['j'] == j)
        print(f'  {j:8} {per.get(j, 0):5} matched of {n:5} DOI-only' + ('' if recs.get(j) else '   (no archive used)'))
    print(f'total: {len(found)}')
    random.seed(7)
    for a, f in random.sample(samples, min(15, len(samples))):
        print(f"\n  {a['id']}  {a.get('v')}:{a.get('fp')} ({a.get('y')})\n    ours:    {a['t']}\n    archive: {f['title']}\n    {f['url']}")
    json.dump(found, open(os.path.join(RAW, 'found.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if dry:
        same = raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
        print('\n(dry run: articles.js not written; serialization round-trip', 'identical)' if same == raw else 'DIFFERS: check before applying)')
        return
    n = 0
    for a in arts:
        f = found.get(a['id'])
        if f and not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv'):
            a['oa'], a['oav'] = f['url'], 'publishedVersion'
            n += 1
    open(ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{n} articles given a free copy from their journal\'s archive')


# Archives checked and not used (November 2026):
#   Harvard, Columbia, Virginia, Stanford Law Reviews: their own sites carry recent volumes only, no school-hosted back
#     archive of the years still missing here; Columbia's and Harvard's repositories hold faculty work, not the journal.
#   Supreme Court Review: published by the University of Chicago Press (paywalled); not in Chicago Unbound's archive.
#   scholarship.law.berkeley.edu (Berkeley's bepress site): TLS certificate expired 2026-11-20; lawcat holds the same
#     California Law Review files, so it is used instead.
#   digitalcommons.law.yale.edu: retired; its address now serves openyls (wrong certificate).

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'lookup':
        lookup([s for s in sys.argv[2:] if not s.startswith('-')])
    elif cmd == 'apply':
        apply('--dry-run' in sys.argv)
    else:
        print(__doc__)
