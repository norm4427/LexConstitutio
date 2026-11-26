"""Free copies of public-domain articles: DOI-only (JSTOR) articles published before 1931, which are in the US public domain
as of 2026, get a link to a free scan on the Internet Archive.

Sources:
  jstor_ejc  JSTOR's Early Journal Content, mirrored on archive.org as one item per article named jstor-<JSTOR stable id>
             (collection jstor_ejc). Our DOI 10.2307/<id> names the item exactly. An item counts only when it is in the
             jstor_ejc collection, is not access-restricted, has a public PDF, and its date is within one year of ours.
             Links https://archive.org/details/jstor-<id>. (EJC covers what JSTOR published before 1923.)
  ia_scan    Whole-issue microfilm scans on archive.org (Serials in Microfilm, sim_<journal>_<date>_<vol>_<issue>), for the
             1923-1930 articles EJC lacks. Only Harvard Law Review has open issues for those years. An article is linked
             only when exactly one page of the volume's issues carries our first page as its printed page label
             (<item>_page_numbers.json) and the OCR text of that page contains most of the words of our title. Links
             https://archive.org/details/<item>/page/<first page>.
Not used: HathiTrust (full view for these volumes, but babel.hathitrust.org answers scripts with a Cloudflare browser
challenge, so no page could be verified) and Harvard DASH (a "Human Verification" page).
Caches are in data/raw/pd_copies/. Run from the repo root (after open_copies.py, which clears `oa`):
    python scripts/pd_copies.py lookup                # about one request a second to archive.org; resumable
    python scripts/pd_copies.py apply --dry-run       # counts per source and journal, 15 random matches; writes nothing
    python scripts/pd_copies.py apply
`apply` touches only articles with no `oa`, `pdf` or `pub` that are not book reviews, sets `oa` and `oav` = publishedVersion
(the site names the host from the URL: "Free copy at archive.org"), and keeps articles.js's serialization.
"""
import gzip, html, json, os, random, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
ART = 'docs/data/articles.js'
CACHE = 'data/raw/pd_copies'
CUTOFF = 1930                    # last year of publication in the US public domain in 2026
SIM = {'hlr': 'sim_harvard-law-review', 'ylj': 'sim_yale-law-journal', 'colr': 'sim_columbia-law-review',
       'valr': 'sim_virginia-law-review', 'calr': 'sim_california-law-review',
       'pennlr': 'sim_university-of-pennsylvania-law-review', 'mlr_mich': 'sim_michigan-law-review'}
_last = [0.0]


def get(url, binary=False):
    for t in range(4):
        wait = _last[0] + 1.0 - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
            return b if binary else b.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                raise
            time.sleep(10 * (t + 1))
        except Exception:
            time.sleep(10 * (t + 1))
    raise IOError('gave up on ' + url)


def cached(path, url, binary=False):
    path = os.path.join(CACHE, path)
    if os.path.exists(path):
        return open(path, 'rb').read() if binary else open(path, encoding='utf-8').read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        body = get(url, binary)
    except urllib.error.HTTPError as e:
        body = b'' if binary else ''
        if e.code not in (403, 404, 410):
            raise
    open(path, 'wb' if binary else 'w', **({} if binary else {'encoding': 'utf-8'})).write(body)
    return body


def search(q, fields, rows=500):
    u = 'https://archive.org/advancedsearch.php?' + urllib.parse.urlencode(
        {'q': q, 'fl[]': fields, 'rows': rows, 'output': 'json'}, doseq=True)
    return json.loads(get(u))['response']['docs']


def load():
    raw = open(ART, encoding='utf-8').read()
    return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def candidates(arts):
    return [a for a in arts if not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv')
            and (a.get('y') or 9999) <= CUTOFF and (a.get('u') or '').startswith('https://doi.org/10.2307/')]


def jstor_id(a):
    return a['u'].split('10.2307/', 1)[1]


# ---------------------------------------------------------------- lookup

def lookup():
    os.makedirs(CACHE, exist_ok=True)
    _, data = load()
    cand = candidates(data['articles'])
    print(len(cand), 'public-domain candidates', flush=True)
    # 1. which candidates have an EJC item (search in batches; checked ids are remembered)
    sp = os.path.join(CACHE, 'ejc_search.json')
    st = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {'checked': [], 'found': {}}
    checked = set(st['checked'])
    todo = ['jstor-' + jstor_id(a) for a in cand if 'jstor-' + jstor_id(a) not in checked]
    for i in range(0, len(todo), 40):
        part = todo[i:i + 40]
        for d in search('collection:jstor_ejc AND identifier:(' + ' OR '.join(part) + ')', ['identifier', 'title', 'date', 'volume'], 100):
            st['found'][d['identifier']] = d
        st['checked'] += part
        json.dump(st, open(sp, 'w', encoding='utf-8'))
    print(len(st['found']), 'EJC items', flush=True)
    # 2. metadata (access, files) of the EJC items of articles still without a free route
    mine = sorted({'jstor-' + jstor_id(a) for a in cand} & set(st['found']))
    for k, ident in enumerate(mine):
        cached(f'ia_meta/{ident}.json', f'https://archive.org/metadata/{ident}')
        if k % 200 == 0:
            print(f'  EJC metadata {k}/{len(mine)}', flush=True)
    # 3. microfilm issue scans for the volumes still needed
    ejc = set(st['found'])
    need = {}
    for a in cand:
        if 'jstor-' + jstor_id(a) not in ejc and a['j'] in SIM and a.get('v'):
            need.setdefault(a['j'], set()).add(a['v'])
    for j, vols in need.items():
        items = json.loads(cached(f'sim/{j}_items.json', 'https://archive.org/advancedsearch.php?' + urllib.parse.urlencode(
            {'q': f'identifier:{SIM[j]}_*', 'fl[]': ['identifier', 'volume', 'date'], 'rows': 5000, 'output': 'json'}, doseq=True)))
        items = items['response']['docs']
        got = 0
        for it in items:
            m = re.match(re.escape(SIM[j]) + r'_[\d-]+_(\d+)_(\d+|index)$', it['identifier'])
            if not m or int(m.group(1)) not in vols or m.group(2) == 'index':
                continue
            ident = it['identifier']
            meta = json.loads(cached(f'ia_meta/{ident}.json', f'https://archive.org/metadata/{ident}') or '{}')
            if (meta.get('metadata') or {}).get('access-restricted-item') in ('true', True):
                continue
            base = f'https://archive.org/download/{ident}/{ident}'
            cached(f'sim/{ident}/page_numbers.json', base + '_page_numbers.json')
            cached(f'sim/{ident}/pageindex.json.gz', base + '_hocr_pageindex.json.gz', binary=True)
            cached(f'sim/{ident}/searchtext.txt.gz', base + '_hocr_searchtext.txt.gz', binary=True)
            got += 1
        print(f'{j}: {len(items)} microfilm items listed, {got} open issues cached for volumes {sorted(vols)}', flush=True)


# ---------------------------------------------------------------- apply

def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', html.unescape(s or '')) if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


STOP = set('the and for from with that this into upon under over its their than which what when where were been have has '
           'shall will not but are was his her law laws'.split())


def title_words(t):
    return [w for w in norm(t).split() if len(w) > 3 and w not in STOP]


def ejc_ok(a, ident):
    p = os.path.join(CACHE, 'ia_meta', ident + '.json')
    if not os.path.exists(p):
        return False
    try:
        m = json.load(open(p, encoding='utf-8'))
    except Exception:
        return False
    md = m.get('metadata') or {}
    coll = md.get('collection') or []
    coll = [coll] if isinstance(coll, str) else coll
    if 'jstor_ejc' not in coll or md.get('access-restricted-item') in ('true', True):
        return False
    if not any(f.get('name', '').endswith('.pdf') and not f.get('private') for f in m.get('files') or []):
        return False
    y = re.match(r'(\d{4})', str(md.get('date') or ''))
    return bool(y and abs(int(y.group(1)) - a['y']) <= 1)


_issues = {}


def issues(j, v):
    """[(item, [page labels], page texts)] for the open microfilm issues of volume v."""
    if (j, v) in _issues:
        return _issues[(j, v)]
    out = []
    d = os.path.join(CACHE, 'sim')
    for ident in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.match(re.escape(SIM.get(j, '-')) + r'_(\d{4})[\d-]*_(\d+)_(\d+)$', ident)
        if not m or int(m.group(2)) != v or int(m.group(1)) > CUTOFF:      # only issues published in the public-domain years
            continue
        try:
            pn = json.load(open(os.path.join(d, ident, 'page_numbers.json'), encoding='utf-8'))['pages']
            pi = json.load(gzip.open(os.path.join(d, ident, 'pageindex.json.gz')))
            st = gzip.open(os.path.join(d, ident, 'searchtext.txt.gz')).read().decode('utf-8', 'replace')
        except Exception:
            continue
        if len(pn) != len(pi):
            continue
        out.append((ident, [p.get('pageNumber') or '' for p in pn], [st[x[0]:x[1]] for x in pi]))
    _issues[(j, v)] = out
    return out


def scan_match(a):
    if a['j'] not in SIM or not a.get('v') or not a.get('fp'):
        return None
    hits = [(ident, k, texts[k]) for ident, labels, texts in issues(a['j'], a['v'])
            for k, lab in enumerate(labels) if lab == str(a['fp'])]
    if len(hits) != 1:
        return None
    ident, k, text = hits[0]
    words = title_words(a['t'])
    page = set(norm(text).split())
    if not words:
        return None
    have = sum(1 for w in words if w in page)
    if have < max(2, -(-len(words) * 6 // 10)) and not (len(words) <= 2 and have == len(words)):
        return None
    return f'https://archive.org/details/{ident}/page/{a["fp"]}'


def apply(dry):
    raw, data = load()
    arts = data['articles']
    sp = os.path.join(CACHE, 'ejc_search.json')
    ejc = json.load(open(sp, encoding='utf-8'))['found'] if os.path.exists(sp) else {}
    found = {}
    cand = candidates(arts)
    for a in cand:
        ident = 'jstor-' + jstor_id(a)
        if ident in ejc and ejc_ok(a, ident):
            found[a['id']] = {'url': f'https://archive.org/details/{ident}', 'source': 'jstor_ejc', 'title': ejc[ident].get('title')}
            continue
        u = scan_match(a)
        if u:
            found[a['id']] = {'url': u, 'source': 'ia_scan', 'title': ''}
    json.dump(found, open(os.path.join(CACHE, 'matches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ids = {a['id']: a for a in arts}
    by_s, by_j = {}, {}
    for aid, f in found.items():
        by_s[f['source']] = by_s.get(f['source'], 0) + 1
        k = (ids[aid]['j'], f['source'])
        by_j[k] = by_j.get(k, 0) + 1
    print(f'{len(cand)} public-domain candidates (published {CUTOFF} or earlier); {len(found)} matched')
    print('by source:', by_s)
    print('by journal:', sorted(by_j.items()))
    left = [a for a in cand if a['id'] not in found]
    dec = {}
    for a in left:
        dec[(a['j'], a['y'] // 10 * 10)] = dec.get((a['j'], a['y'] // 10 * 10), 0) + 1
    print('unmatched by journal and decade:', sorted(dec.items()))
    if dry:
        random.seed(5)
        for aid in random.sample(sorted(found), min(15, len(found))):
            a, f = ids[aid], found[aid]
            print(f'\n{aid} [{f["source"]}] v{a.get("v")} p{a.get("fp")} ({a["y"]})\n  ours: {a["t"]}\n  IA:   {f["title"]}\n  {f["url"]}')
        print('\ndry run: articles.js not changed')
        return
    n = 0
    for a in cand:
        f = found.get(a['id'])
        if f:
            a['oa'], a['oav'] = f['url'], 'publishedVersion'
            n += 1
    open(ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{n} articles given a free copy')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'lookup':
        lookup()
    elif cmd == 'apply':
        apply('--dry-run' in sys.argv)
    else:
        sys.exit(__doc__)
