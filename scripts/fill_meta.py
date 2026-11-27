"""Fill metadata gaps in docs/data/articles.js: missing authors (`a`), missing volumes (`v`) and abstracts cut off with an ellipsis.

Sources, cached in data/raw/fill_meta/ (crossref/, openalex/, pages/):
  crossref  Crossref work records for our DOIs (the article link, or the DOI a repository record gives for it), 50 a request
            with a generic contact address.
  openalex  OpenAlex work records for the same DOIs, 50 a request (OPENALEX_KEY from .keys.env via local_keys.py; never printed).
  pages     the article's own page on its journal's or school's site (non-DOI links), one request a second per host: its
            citation_author / citation_volume / citation_abstract / description meta and Digital Commons' abstract block.
Rules (erring toward leaving a gap):
  authors   only for articles with no `a`; the source's title must match ours (normalized, or one a prefix of the other) and
            its year be within one; names that are institutions or mastheads are dropped; "Last, First" becomes "First Last".
            Unsigned pieces stay empty: no author is invented.
  volumes   only for articles with no `v`; the source's title and year must match, and the volume must fit the journal's
            own volume/year pattern in the index (year minus volume within one of the journal's usual offset).
  abstracts only for abstracts ending in an ellipsis; the new text must start with the old text minus its ellipsis (compared
            normalized) and be longer; markup is stripped.
Serialization is kept byte-identical to the file's own (json.dumps, ensure_ascii=False, compact separators).
    python scripts/fill_meta.py lookup [crossref|openalex|pages ...]
    python scripts/fill_meta.py apply --dry-run
    python scripts/fill_meta.py apply
    python scripts/fill_meta.py topics [--dry-run]     # rescore pieces tagged only 'general' with build.ps1's rules + EXTRA
"""
import glob, hashlib, html, json, os, random, re, sys, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_keys  # noqa: F401  (loads OPENALEX_KEY into the environment)

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build; mailto:lexconstitutio-build@example.org)'}
ART = 'docs/data/articles.js'
RAW = 'data/raw/fill_meta'
REPO = 'data/raw/repo_copies'
_last, _lock = {}, threading.Lock()


def fetch(url, gap=1.0, tries=3):
    host = urllib.parse.urlparse(url).netloc
    for t in range(tries):
        with _lock:
            wait = _last.get(host, 0) + gap - time.time()
            _last[host] = max(time.time(), _last.get(host, 0) + gap)
        if wait > 0:
            time.sleep(wait)
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)
            return r.status, r.read(4_000_000).decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and t < tries - 1:
                time.sleep(15 * (t + 1))
                continue
            return e.code, ''
        except Exception as e:
            if t == tries - 1:
                return 0, ''
            time.sleep(5)
    return 0, ''


def load():
    raw = open(ART, encoding='utf-8').read()
    return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def dump(raw, data):
    return raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', html.unescape(s or '')) if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '', s)


def same_title(a, b):
    a, b = norm(a), norm(b)
    a, b = (a[3:] if a.startswith('the') else a), (b[3:] if b.startswith('the') else b)
    return bool(a and b) and (a == b or (min(len(a), len(b)) > 25 and (a.startswith(b) or b.startswith(a))))


ELL = re.compile(r'\s*(?:…|\.\.\.)\s*$')


def cut(a):
    return bool(ELL.search(a.get('ab') or ''))


def gaps(arts):
    return [a for a in arts if not a.get('a') or not a.get('v') or cut(a)]


def doi_map(arts):
    """{article id: doi} from the article link, or from the repository record (data/raw/repo_copies) for its page URL.
    The repository scan is slow (gigabytes of XML), so its result is kept in data/raw/fill_meta/doimap.json."""
    cache = os.path.join(RAW, 'doimap.json')
    if os.path.exists(cache):
        out = json.load(open(cache, encoding='utf-8'))
        for a in arts:
            if (a.get('u') or '').startswith('https://doi.org/'):
                out[a['id']] = a['u'].split('doi.org/', 1)[1].lower()
        return out
    out = _doi_map(arts)
    os.makedirs(RAW, exist_ok=True)
    json.dump(out, open(cache, 'w', encoding='utf-8'))
    return out


def _doi_map(arts):
    out = {}
    for a in arts:
        u = a.get('u') or ''
        if u.startswith('https://doi.org/'):
            out[a['id']] = u.split('doi.org/', 1)[1].lower()
    want = {re.sub(r'^https?://(www\.)?', '', (a.get('u') or '').rstrip('/')): a['id'] for a in gaps(arts) if a['id'] not in out}
    dirs = []
    if want and os.path.isdir(REPO):
        import repo_copies                       # only the repositories that host our gap articles are read
        hosts = {k.split('/')[0] for k in want}
        dirs = [k for k, (_, base, _) in repo_copies.REPOS.items() if urllib.parse.urlparse(base).netloc.removeprefix('www.') in hosts]
    for key in dirs:
        for f in glob.glob(os.path.join(REPO, key, 'oai_dc-*.xml')):
            s = open(f, encoding='utf-8', errors='ignore').read()
            if 'info:doi/' not in s:
                continue
            for rec in re.findall(r'<record>.*?</record>', s, re.S):
                m = re.search(r'info:doi/(10\.[^<\s]+)', rec)
                if not m:
                    continue
                for u in re.findall(r'<dc:identifier\s*>(https?://[^<]+)</dc:identifier>', rec):
                    k = re.sub(r'^https?://(www\.)?', '', u.strip().rstrip('/'))
                    if k in want:
                        out[want[k]] = m.group(1).lower()
    return out

# ---------------------------------------------------------------- lookup


def batches(dois, sub):
    d = os.path.join(RAW, sub)
    os.makedirs(d, exist_ok=True)
    bs = [dois[i:i + 50] for i in range(0, len(dois), 50)]
    return d, [b for b in bs if not os.path.exists(os.path.join(d, hashlib.md5('|'.join(b).encode()).hexdigest() + '.json'))]


def lookup_crossref(dois):
    d, todo = batches(dois, 'crossref')
    print(f'crossref: {len(todo)} batches', flush=True)
    for k, b in enumerate(todo):
        url = 'https://api.crossref.org/works?' + urllib.parse.urlencode({
            'filter': ','.join('doi:' + x for x in b), 'rows': 100,
            'select': 'DOI,title,author,volume,issue,page,abstract,issued,container-title,type'})
        st, s = fetch(url, gap=1.0)
        if st != 200:
            print(f'  crossref HTTP {st} at batch {k}', flush=True)
            continue
        json.dump(json.loads(s)['message']['items'], open(os.path.join(d, hashlib.md5('|'.join(b).encode()).hexdigest() + '.json'), 'w', encoding='utf-8'))
        if k % 20 == 0:
            print(f'  crossref {k}/{len(todo)}', flush=True)


def lookup_openalex(dois):
    d, todo = batches(dois, 'openalex')
    key = os.environ.get('OPENALEX_KEY', '')
    print(f'openalex: {len(todo)} batches' + ('' if key else ' (no key found)'), flush=True)
    for k, b in enumerate(todo):
        q = {'filter': 'doi:' + '|'.join(b), 'per-page': 50,
             'select': 'doi,title,publication_year,authorships,biblio,abstract_inverted_index'}
        if key:
            q['api_key'] = key
        st, s = fetch('https://api.openalex.org/works?' + urllib.parse.urlencode(q), gap=0.5)
        if st != 200:
            print(f'  openalex HTTP {st} at batch {k}; stopping', flush=True)
            return
        json.dump(json.loads(s).get('results', []), open(os.path.join(d, hashlib.md5('|'.join(b).encode()).hexdigest() + '.json'), 'w', encoding='utf-8'))
        if k % 20 == 0:
            print(f'  openalex {k}/{len(todo)}', flush=True)


def page_path(url):
    return os.path.join(RAW, 'pages', hashlib.md5(url.encode()).hexdigest() + '.json')


def lookup_pages(arts):
    os.makedirs(os.path.join(RAW, 'pages'), exist_ok=True)
    urls = sorted({a['u'] for a in gaps(arts) if (a.get('u') or '').startswith('http') and 'doi.org/' not in a['u']
                   and not os.path.exists(page_path(a['u']))})
    by = {}
    for u in urls:
        by.setdefault(urllib.parse.urlparse(u).netloc, []).append(u)
    print(f'pages: {len(urls)} on {len(by)} hosts: ' + ', '.join(f'{h} {len(v)}' for h, v in sorted(by.items(), key=lambda x: -len(x[1]))[:12]), flush=True)
    done = [0]

    def host_run(us):
        for u in us:
            st, s = fetch(u)
            if st in (200, 404, 410, 403):
                json.dump({'status': st, 'body': s}, open(page_path(u), 'w', encoding='utf-8'), ensure_ascii=False)
            done[0] += 1
            if done[0] % 250 == 0:
                print(f'  pages {done[0]}/{len(urls)}', flush=True)
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(host_run, by.values()))


def lookup(srcs):
    _, data = load()
    arts = data['articles']
    dm = doi_map(arts)
    dois = sorted({dm[a['id']] for a in gaps(arts) if a['id'] in dm})
    print(f'{len(gaps(arts))} articles with a gap; {len(dois)} with a DOI', flush=True)
    srcs = srcs or ['crossref', 'openalex', 'pages']
    if 'crossref' in srcs:
        lookup_crossref(dois)
    if 'openalex' in srcs:
        lookup_openalex(dois)
    if 'pages' in srcs:
        lookup_pages(arts)

# ---------------------------------------------------------------- records


def strip(s):
    s = re.sub(r'<jats:title>.*?</jats:title>', ' ', s or '', flags=re.S | re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', html.unescape(html.unescape(s))).strip()


def inverted(ix):
    if not ix:
        return ''
    pos = sorted((p, w) for w, ps in ix.items() for p in ps)
    return ' '.join(w for _, w in pos)


BAD_NAME = re.compile(r'law review|editor|association|journal|board|staff|anonymous|unknown|harvard|columbia|yale|'
                      r'university|school|society|institute|committee|council|press|^note$|^comment$', re.I)


def person(name):
    name = re.sub(r'\s+', ' ', html.unescape(name or '')).strip(' ,;')
    if not name or BAD_NAME.search(name) or not re.search(r'[A-Za-z]{2}', name):
        return None
    if ',' in name:
        last, first = [x.strip() for x in name.split(',', 1)]
        suf = ''
        m = re.match(r'(.*?),\s*(Jr\.?|Sr\.?|II|III|IV)$', first)
        if m:
            first, suf = m.group(1), ', ' + m.group(2)
        name = f'{first} {last}{suf}'.strip()
    if len(name.split()) < 2:
        return None                   # one-word "authors" are site names or initials (e.g. Harvard's pages give "hlr")
    if name.isupper():
        name = ' '.join(w.capitalize() if len(w) > 2 else w for w in name.split())
    return name


def records():
    """{doi: [record]} with record = {src, title, year, authors, volume, abstract}."""
    out = {}
    for f in glob.glob(os.path.join(RAW, 'crossref', '*.json')):
        for w in json.load(open(f, encoding='utf-8')):
            yr = ((w.get('issued') or {}).get('date-parts') or [[None]])[0][0]
            au = [person(f"{x.get('family', '')}, {x.get('given', '')}" if x.get('given') else x.get('family') or x.get('name'))
                  for x in w.get('author') or []]
            out.setdefault(w['DOI'].lower(), []).append({'src': 'crossref', 'title': ' '.join(w.get('title') or []), 'year': yr,
                                                         'authors': [x for x in au if x], 'volume': w.get('volume'),
                                                         'abstract': strip(w.get('abstract'))})
    for f in glob.glob(os.path.join(RAW, 'openalex', '*.json')):
        for w in json.load(open(f, encoding='utf-8')):
            doi = (w.get('doi') or '').replace('https://doi.org/', '').lower()
            au = [person((x.get('author') or {}).get('display_name')) for x in w.get('authorships') or []]
            out.setdefault(doi, []).append({'src': 'openalex', 'title': w.get('title') or '', 'year': w.get('publication_year'),
                                            'authors': [x for x in au if x], 'volume': (w.get('biblio') or {}).get('volume'),
                                            'abstract': strip(inverted(w.get('abstract_inverted_index')))})
    return out


def meta(body, names):
    vals = []
    for n in names:
        vals += re.findall(r'<meta[^>]+(?:name|property)="' + n + r'"[^>]+content="([^"]*)"', body, re.I)
        vals += re.findall(r'<meta[^>]+content="([^"]*)"[^>]+(?:name|property)="' + n + r'"', body, re.I)
    return [html.unescape(v).strip() for v in vals if v.strip()]


def page_record(url):
    p = page_path(url)
    if not os.path.exists(p):
        return None
    rec = json.load(open(p, encoding='utf-8'))
    if rec['status'] != 200:
        return None
    b = rec['body']
    title = (meta(b, ['citation_title', 'bepress_citation_title', 'og:title', 'DC.title']) or [''])[0]
    if not title:
        m = re.search(r'<title[^>]*>(.*?)</title>', b, re.S | re.I)
        title = strip(m.group(1)).split(' | ')[0] if m else ''
    authors = meta(b, ['citation_author', 'bepress_citation_author', 'DC.creator', 'author'])
    vol = (meta(b, ['citation_volume', 'bepress_citation_volume']) or [None])[0]
    date = (meta(b, ['citation_date', 'citation_publication_date', 'bepress_citation_date', 'article:published_time']) or [''])[0]
    y = re.search(r'(1[89]|20)\d\d', date)
    abstracts = meta(b, ['citation_abstract', 'DC.description', 'description', 'og:description', 'twitter:description'])
    m = re.search(r'<div id="abstract"[^>]*>(.*?)</div>', b, re.S)          # Digital Commons
    if m:
        abstracts.insert(0, strip(m.group(1)).removeprefix('Abstract ').strip())
    for blk in re.findall(r'<p[^>]*>(.*?)</p>', b, re.S)[:60]:          # opening passages (journal sites' summaries)
        t = strip(blk)
        if len(t) > 150:
            abstracts.append(t)
    return {'src': 'page', 'title': strip(title), 'year': int(y.group()) if y else None,
            'authors': [x for x in (person(n) for n in authors) if x], 'volume': vol, 'abstract': abstracts}

# ---------------------------------------------------------------- apply


def vol_offsets(arts):
    by = {}
    for a in arts:
        if a.get('v') and a.get('y') and isinstance(a['v'], int):
            by.setdefault(a['j'], []).append(a['y'] - a['v'])
    return {j: sorted(x)[len(x) // 2] for j, x in by.items() if len(x) >= 5}


def better_abstract(old, cands):
    base = ELL.sub('', old).rstrip(' .,;:')
    nb = norm(base)
    if len(nb) < 40:
        return None
    best = None
    for c in cands:
        c = (c or '').strip()
        nc = norm(c)
        if not re.search(r'[.?!]["”’)\]]?$', c) or ELL.search(c):
            continue                  # only a complete text: one still cut off is not the full abstract
        if len(nc) <= len(nb) + 20 or not nc.startswith(nb) or len(c) > 3000:
            # over 3,000 characters is body text (OpenAlex's "abstracts" of old JSTOR pieces run on into footnotes)
            continue
        if best is None or len(c) > len(best):
            best = c
    return best


def apply(dry):
    raw, data = load()
    arts = data['articles']
    if dump(raw, data) != raw:
        sys.exit('articles.js does not round-trip; not touching it')
    recs = records()
    dm = doi_map(arts)
    off = vol_offsets(arts)
    # journals with no volumes in the index: the usual year-minus-volume offset of the sources' own volumes for them
    src_off = {}
    for a in arts:
        if a.get('v') or a['j'] in off or not a.get('y'):
            continue
        for r in recs.get(dm.get(a['id']), []):
            if r['volume'] and re.fullmatch(r'\d{1,4}', str(r['volume']).strip()) and same_title(r['title'], a['t']):
                src_off.setdefault(a['j'], []).append(a['y'] - int(r['volume']))
    for j, xs in src_off.items():
        if len(xs) >= 10:
            off[j] = sorted(xs)[len(xs) // 2]
            print(f'volume offset for {j} from the sources: year - volume = {off[j]} ({len(xs)} records)')
    stats = {'authors': [0, 0], 'volumes': [0, 0], 'abstracts': [0, 0]}
    by_src = {}
    changes = []
    for a in arts:
        if not (not a.get('a') or not a.get('v') or cut(a)):
            continue
        cands = list(recs.get(dm.get(a['id']), []))
        pr = page_record(a['u']) if (a.get('u') or '').startswith('http') and 'doi.org/' not in a['u'] else None
        if pr:
            cands.insert(0, pr)
        ok = [r for r in cands if same_title(r['title'], a['t']) and (not r['year'] or not a.get('y') or abs(r['year'] - a['y']) <= 1)]
        if not a.get('a'):
            stats['authors'][0] += 1
            for r in ok:
                if r['authors']:
                    changes.append((a['id'], 'a', a['a'], r['authors'][:12], r['src']))
                    a['a'] = r['authors'][:12]
                    stats['authors'][1] += 1
                    by_src[('authors', r['src'])] = by_src.get(('authors', r['src']), 0) + 1
                    break
        if not a.get('v'):
            stats['volumes'][0] += 1
            for r in ok:
                v = r['volume']
                if v and re.fullmatch(r'\d{1,4}', str(v).strip()):
                    v = int(v)
                    if a['j'] in off and a.get('y') and abs((a['y'] - v) - off[a['j']]) <= 1:
                        changes.append((a['id'], 'v', None, v, r['src']))
                        a['v'] = v
                        stats['volumes'][1] += 1
                        by_src[('volumes', r['src'])] = by_src.get(('volumes', r['src']), 0) + 1
                        break
        if cut(a):
            stats['abstracts'][0] += 1
            for r in ok:
                new = better_abstract(a['ab'], r['abstract'] if isinstance(r['abstract'], list) else [r['abstract']])
                if new:
                    changes.append((a['id'], 'ab', a['ab'], new, r['src']))
                    a['ab'] = new
                    stats['abstracts'][1] += 1
                    by_src[('abstracts', r['src'])] = by_src.get(('abstracts', r['src']), 0) + 1
                    break
    for k, (n, f) in stats.items():
        print(f'{k}: {n} gaps, {f} filled')
    print('by source:', sorted(by_src.items()))
    left = {'no a': sum(1 for a in arts if not a.get('a')), 'no v': sum(1 for a in arts if not a.get('v')),
            'cut ab': sum(1 for a in arts if cut(a))}
    print('after:', left)
    json.dump(changes, open(os.path.join(RAW, 'changes.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    random.seed(5)
    for kind in ('a', 'v', 'ab'):
        sub = [c for c in changes if c[1] == kind]
        for c in random.sample(sub, min(5, len(sub))):
            t = next(x['t'] for x in arts if x['id'] == c[0])
            if kind == 'ab':
                print(f"  {c[0]} [{c[4]}] {t[:60]}\n     old: ...{c[2][-90:]}\n     new: ...{c[3][len(c[2]) - 95:len(c[2]) + 120]}")
            else:
                print(f'  {c[0]} [{c[4]}] {t[:70]} -> {c[3]}')
    if dry:
        print('dry run: articles.js not written')
        return
    open(ART, 'w', encoding='utf-8').write(dump(raw, data))
    print('articles.js written')

# ---------------------------------------------------------------- topics (pieces tagged only 'general')

# Extra patterns for older vocabulary, used only when rescoring pieces whose sole topic is 'general' (build.ps1 untouched)
EXTRA = {
    'statecon': r'municipal corporations?|home rule|special (or local )?legislation|local legislation|special assessments?|local government',
    'court': r'unconstitutional (statutes?|acts?|laws?|legislation|clauses?|provisions?|exception)|declar\w* (an? )?(legislative )?(act|statute|law)s? unconstitutional|severab|separability|life of john marshall',
    'equality': r'\bnegro(es)?\b|colou?red (persons?|race|people)|jim crow|class legislation|equal access',
    'voting': r'political part(y|ies)|nineteenth amendment|suffrage|primary elections?|white primar',
    'executive': r'impoundment|tenure of office|\bveto(es|ed)?\b',
    'congress': r'\bsenate\b|\bsenators?\b|house of representatives|legislative investigations?|contempt of congress',
    'security': r'martial law|courts?-martial|constitutional dictatorship|state of siege',
    'econreg': r"eight[- ]hour|hours of (labor|work)|working day|corporate charters?|milk (business|control|prices?|industry)|right to earn|workmen'?s compensation|workers'? compensation|\bcarriers?\b|jitneys?|trade regulation",
    'federalism': r'full faith and credit|relations? between (state and federal|federal and state)|state and federal (law|courts)|privileges and immunities|suits? between states|suits? against (the|a) state|interstate compacts?',
    'takings': r'impair(s|ing|ment of)? (the obligations? of )?contracts?',
    'religion': r'parochial schools?|\bprayer\b|religio(n|us)\b',
    'citizenship': r'insular cases|unincorporated territor|puerto ric',
    'crimpro': r'trial by jury|jury trials?|grand jur|\bjur(y|ies)\b.{0,40}criminal|criminal.{0,40}\bjur(y|ies)\b',
    'history': r'\bcolonial\b|biograph',
}


def topic_rules():
    src = open('scripts/build.ps1', encoding='utf-8').read()
    out = {}
    for m in re.finditer(r"@\{ id='(\w+)';[^\n]*?re='((?:[^']|'')*)' \}", src):
        k, pat = m.group(1), m.group(2).replace("''", "'").replace('(?<!(twenty|fifty)-)', '(?<!twenty-)(?<!fifty-)')
        if k == 'general':
            continue
        out[k] = re.compile(pat + ('|' + EXTRA[k] if k in EXTRA else ''), re.I)
    return out


def topics(dry):
    raw, data = load()
    if dump(raw, data) != raw:
        sys.exit('articles.js does not round-trip; not touching it')
    rx = topic_rules()
    arts = data['articles']
    before = {}
    for a in arts:
        for t in a.get('tp') or []:
            before[t] = before.get(t, 0) + 1
    moved = []
    for a in arts:
        if a.get('tp') != ['general']:
            continue
        kw = ' '.join(a.get('kw') or [])
        sc = {k: 3 * len(r.findall(a.get('t') or '')) + 2 * len(r.findall(kw)) + min(3, len(r.findall(a.get('ab') or '')))
              for k, r in rx.items()}
        sc = {k: v for k, v in sc.items() if v > 0}
        order = sorted(sc, key=lambda k: -sc[k])
        tp = [k for k in order if sc[k] >= 2][:4]      # build.ps1's rule without its single-hit fallback (too weak here)
        if tp:
            moved.append((a['id'], a['t'], tp))
            a['tp'] = tp
    after = {}
    for a in arts:
        for t in a.get('tp') or []:
            after[t] = after.get(t, 0) + 1
    print(f"'general' only: {sum(1 for a in arts if a.get('tp') == ['general']) + len(moved)} -> {sum(1 for a in arts if a.get('tp') == ['general'])}")
    print('topic counts (articles tagged), before -> after:')
    for k in sorted(set(before) | set(after), key=lambda k: -after.get(k, 0)):
        if before.get(k, 0) != after.get(k, 0):
            print(f'  {k:13} {before.get(k, 0):6} -> {after.get(k, 0):6}')
    random.seed(9)
    for i, t, tp in random.sample(moved, min(12, len(moved))):
        print(f'  {i}: {t[:80]} -> {tp}')
    json.dump(moved, open(os.path.join(RAW, 'topics.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    if dry:
        print('dry run: articles.js not written')
        return
    open(ART, 'w', encoding='utf-8').write(dump(raw, data))
    print('articles.js written')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'lookup':
        lookup([s for s in sys.argv[2:] if not s.startswith('-')])
    elif cmd == 'apply':
        apply('--dry-run' in sys.argv)
    elif cmd == 'topics':
        topics('--dry-run' in sys.argv)
    else:
        print(__doc__)
