"""Second pass for free copies of articles that still link only to a DOI (JSTOR), from sources the earlier scripts did not use.

Sources (each cached under data/raw/modern_copies/, fetched about one request a second; nothing personal is sent):
  openalex  OpenAlex work records for our DOIs, 50 per request (about 110 requests in all; OpenAlex's shared free budget is
            1,000 a day per IP). A location counts when it is open access, on a university or other institutional repository
            host (.edu, .ac.xx, Harvard DASH/NRS, eScholarship, PhilPapers, HAL, ...; never SSRN, ResearchGate, Academia, CORE,
            Semantic Scholar, the Internet Archive, JSTOR, HeinOnline or a publisher), the work's title matches ours and its
            year is within one. The landing page is then fetched and must show our title (pages behind a bot check are kept
            only when the host is a law school's own repository and are counted apart).
  repo      the faculty-repository records repo_copies.py already harvested (data/raw/repo_copies/<repo>.json, read only),
            with two rules repo_copies.py lacks: file-name citations spelled out ("97ColumbiaLawReview2334": our journal,
            volume and first page), and long titles that agree up to a subtitle (one a prefix of the other, over 30
            characters) with an author's surname matching and the year within one.
  sites     the journals' own sites (harvardlawreview.org, columbialawreview.org, virginialawreview.org,
            review.law.stanford.edu): their sitemaps' article slugs matched against our titles, then the page fetched and
            checked for the title. Their print archives start at volumes after the years still missing (Harvard vol. 120,
            Columbia 109, Virginia 90, Stanford 58), so this finds only the odd older piece posted outside the archive.
  hathi     HathiTrust full-view volumes (catalog API by ISSN) for articles published before 1931, now in the US public
            domain; HathiTrust's own rights code (pd) is the check. Links open the volume at the printed page
            (pt?id=...&num=<first page>). Not applied unless named with --with-hathi: HathiTrust's reader sits behind a
            Cloudflare check, so page-level links could not be confirmed from here.
Matching errs toward leaving a link out; only articles with no `oa`, `pdf` or `pub` that are not book reviews are touched, and
apply sets `oa` (+ `oav` publishedVersion, or acceptedVersion / none as the source says) and nothing else.

    python scripts/modern_copies.py lookup [source ...]      # openalex repo sites hathi (default: all)
    python scripts/modern_copies.py apply --dry-run [--with-hathi]
    python scripts/modern_copies.py apply [--with-hathi]
Run after open_copies.py and the other copy scripts. Matches are kept in data/raw/modern_copies/found.json.
"""
import glob, hashlib, html, json, os, random, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
ART = 'docs/data/articles.js'
RAW = 'data/raw/modern_copies'
REPO = 'data/raw/repo_copies'
_last = {}


def fetch(url, tries=3):
    """(status, text). One request a second per host."""
    host = urllib.parse.urlparse(url).netloc
    for t in range(tries):
        wait = _last.get(host, 0) + 1.0 - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)
            return r.status, r.read(3_000_000).decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and t < tries - 1:
                time.sleep(10 * (t + 1))
                continue
            try:
                body = e.read(200_000).decode('utf-8', 'ignore')
            except Exception:
                body = ''
            return e.code, body
        except Exception as e:
            if t == tries - 1:
                return 0, str(e)
            time.sleep(5)
    return 0, ''


def cached(sub, url, key=None):
    d = os.path.join(RAW, sub)
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, hashlib.md5((key or url).encode()).hexdigest() + '.json')
    if os.path.exists(f):
        return json.load(open(f, encoding='utf-8'))
    st, s = fetch(url)
    rec = {'url': url, 'status': st, 'body': s}
    if st in (200, 403, 404, 410) or (st and st < 500):
        json.dump(rec, open(f, 'w', encoding='utf-8'), ensure_ascii=False)
    return rec


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', html.unescape(s or '')) if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '', s)


def same_title(a, b, prefix=30):
    a, b = norm(a), norm(b)
    for x in ('the',):
        a, b = (a[3:] if a.startswith(x) and len(a) > 10 else a), (b[3:] if b.startswith(x) and len(b) > 10 else b)
    return bool(a and b) and (a == b or (min(len(a), len(b)) > prefix and (a.startswith(b) or b.startswith(a))))


def surname(name):
    name = html.unescape(name or '')
    if ',' in name:
        name = name.split(',')[0]
    parts = [p for p in re.sub(r'[^a-z ]', ' ', ''.join(c for c in unicodedata.normalize('NFD', name.lower())
                                                       if not unicodedata.combining(c))).split()
             if p not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return parts[-1] if parts else ''


def load():
    for t in range(5):      # another script may be rewriting the file: retry a half-written read
        raw = open(ART, encoding='utf-8').read()
        try:
            return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
        except ValueError:
            time.sleep(5)
    sys.exit('articles.js could not be parsed')


def candidates(arts):
    return [a for a in arts if not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv')
            and (a.get('u') or '').startswith('https://doi.org/')]


def doi_of(a):
    return a['u'].split('doi.org/', 1)[1].lower()


def page_title_ok(body, title):
    """Our title appears in the page's <title>, citation_title / og:title / DC.title meta, or first heading."""
    bits = re.findall(r'<title[^>]*>(.*?)</title>', body, re.S | re.I)
    bits += re.findall(r'<meta[^>]+(?:name|property)="(?:citation_title|og:title|DC\.title|dc\.title|twitter:title)"[^>]+content="([^"]*)"', body, re.I)
    bits += re.findall(r'<meta[^>]+content="([^"]*)"[^>]+(?:name|property)="(?:citation_title|og:title|DC\.title)"', body, re.I)
    bits += [re.sub(r'<[^>]+>', ' ', x) for x in re.findall(r'<h1[^>]*>(.*?)</h1>', body, re.S | re.I)[:2]]
    t = norm(title)
    for b in bits:
        n = norm(b)
        if same_title(b, title) or (len(t) > 15 and t in n):
            return True
    return False

# ---------------------------------------------------------------- openalex


BAD_HOST = re.compile(r'ssrn\.com|researchgate|academia\.edu|core\.ac\.uk|semanticscholar|archive\.org|jstor\.org|heinonline|'
                      r'doi\.org|europepmc|ncbi\.nlm|books\.google|scholar\.google|zenodo|figshare|osf\.io|base-search|'
                      r'scite\.ai|unpaywall|openalex|crossref|wiley|springer|tandfonline|sagepub|oup\.com|cambridge\.org/core|'
                      r'journals\.uchicago\.edu|harvardlawreview\.org|columbialawreview\.org|virginialawreview\.org|'
                      r'stanfordlawreview\.org|yalelawjournal\.org|hathitrust|handle\.net$')
INST_HOST = re.compile(r'(\.|^)edu$|\.edu\.[a-z]{2}$|\.ac\.[a-z]{2}$|(^|\.)(dash|nrs)\.harvard\.edu$|escholarship\.org$|'
                       r'philpapers\.org$|philarchive\.org$|(^|\.)hal\.science$|hal\.archives-ouvertes\.fr$|'
                       r'(^|\.)uni-[a-z-]+\.de$|(^|\.)(eur|uu|rug|leidenuniv|uva|ru|vu|tilburguniversity)\.nl$|'
                       r'(^|\.)(utoronto|ubc|mcgill|uottawa|yorku|queensu|ualberta|dal|usask|umanitoba|uwo|mcmaster)\.ca$|'
                       r'(^|\.)(ox|cam|lse|ucl|kcl|ed|gla|manchester|bristol|warwick|nottingham|soton|leeds|qmul)\.ac\.uk$|'
                       r'(^|\.)(anu|unimelb|sydney|unsw|monash|uq|adelaide)\.edu\.au$|(^|\.)eui\.eu$|(^|\.)cadmus\.eui\.eu$|'
                       r'(^|\.)(ethz|uzh|unibe|unige|unil)\.ch$|(^|\.)(huji|tau|biu)\.ac\.il$|(^|\.)nus\.edu\.sg$')


def openalex_lookup(arts):
    cand = candidates(arts)
    dois = sorted({doi_of(a) for a in cand})
    d = os.path.join(RAW, 'openalex')
    os.makedirs(d, exist_ok=True)
    todo = [dois[i:i + 50] for i in range(0, len(dois), 50)]
    todo = [b for b in todo if not os.path.exists(os.path.join(d, hashlib.md5('|'.join(b).encode()).hexdigest() + '.json'))]
    print(f'openalex: {len(dois)} DOIs, {len(todo)} batches to fetch', flush=True)
    for k, b in enumerate(todo):
        url = 'https://api.openalex.org/works?' + urllib.parse.urlencode({
            'filter': 'doi:' + '|'.join(b), 'per-page': 50,
            'select': 'id,doi,title,publication_year,authorships,locations', 'mailto': 'lexconstitutio-build@example.org'})
        st, s = fetch(url)
        if st != 200:
            print(f'  openalex: HTTP {st} at batch {k}; stopping (rerun lookup tomorrow to continue)', flush=True)
            return
        json.dump(json.loads(s).get('results', []), open(os.path.join(d, hashlib.md5('|'.join(b).encode()).hexdigest() + '.json'), 'w', encoding='utf-8'))
        if k % 20 == 0:
            print(f'  openalex: {k}/{len(todo)}', flush=True)
    # landing pages of the candidate locations
    pages = sorted({l['url'] for _, l in openalex_choices(arts)})
    print(f'openalex: {len(pages)} landing pages to check', flush=True)
    for k, u in enumerate(pages):
        cached('pages', u)
        if k % 50 == 0:
            print(f'  pages: {k}/{len(pages)}', flush=True)


def openalex_works():
    out = {}
    for f in glob.glob(os.path.join(RAW, 'openalex', '*.json')):
        for w in json.load(open(f, encoding='utf-8')):
            out[(w.get('doi') or '').replace('https://doi.org/', '').lower()] = w
    return out


def openalex_choices(arts):
    """[(article, location)] for OpenAlex locations that pass the host, title and year rules (landing page not yet checked)."""
    works = openalex_works()
    out = []
    for a in candidates(arts):
        w = works.get(doi_of(a))
        if not w or not same_title(w.get('title'), a['t']) or abs((w.get('publication_year') or 0) - (a.get('y') or 0)) > 1:
            continue
        for l in w.get('locations') or []:
            if not l.get('is_oa'):
                continue
            url = l.get('landing_page_url') or l.get('pdf_url')
            if not url or not url.startswith('http'):
                continue
            host = urllib.parse.urlparse(url).netloc.lower().split(':')[0].removeprefix('www.')
            if BAD_HOST.search(host) or not INST_HOST.search(host):
                continue
            out.append((a, {'url': url, 'pdf': l.get('pdf_url'), 'host': host, 'version': l.get('version') or '',
                            'source': (l.get('source') or {}).get('display_name') or ''}))
    return out


JOURNAL_NAMES = {'hlr': ['harvard law review', 'harv l rev'], 'colr': ['columbia law review', 'colum l rev'],
                 'valr': ['virginia law review', 'va l rev'], 'ylj': ['yale law journal', 'yale l j', 'yale lj'],
                 'calr': ['california law review', 'calif l rev', 'cal l rev'], 'slr': ['stanford law review', 'stan l rev'],
                 'pennlr': ['university of pennsylvania law review', 'u pa l rev'],
                 'scr': ['supreme court review', 'sup ct rev']}


def journal_ok(body, j):
    """A journal named in the page's citation_journal_title / DC.source meta must be ours (pages that name none pass)."""
    named = re.findall(r'<meta[^>]+name="(?:bepress_citation_journal_title|citation_journal_title|DC\.source|dc\.source|citation_publisher)"[^>]+content="([^"]*)"', body, re.I)
    named = [re.sub(r'[^a-z ]+', ' ', html.unescape(x).lower()) for x in named]
    named = [' '.join(x.split()) for x in named if re.search(r'law|journal|review|rev', x)]
    if not named:
        return True
    ours = JOURNAL_NAMES.get(j, [])
    return any(any(o in x for o in ours) for x in named)


LAW_REPO_HOSTS = None


def law_repo_hosts():
    global LAW_REPO_HOSTS
    if LAW_REPO_HOSTS is None:
        LAW_REPO_HOSTS = set()
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import repo_copies
            for kind, base, _ in repo_copies.REPOS.values():
                LAW_REPO_HOSTS.add(urllib.parse.urlparse(base).netloc.removeprefix('www.'))
        except Exception:
            pass
    return LAW_REPO_HOSTS


def openalex_matches(arts):
    found = {}
    for a, l in openalex_choices(arts):
        if a['id'] in found and found[a['id']]['check'] == 'page':
            continue
        p = os.path.join(RAW, 'pages', hashlib.md5(l['url'].encode()).hexdigest() + '.json')
        if not os.path.exists(p):
            continue
        rec = json.load(open(p, encoding='utf-8'))
        if re.search(r'/vol\d+/iss\d+/', l['url']) or not journal_ok(rec['body'], a['j']):
            continue                  # another journal's issue page: OpenAlex merged two works with one title
        if rec['status'] == 200 and page_title_ok(rec['body'], a['t']):
            check = 'page'
        elif rec['status'] in (202, 403) and l['host'] in law_repo_hosts():
            check = 'bot check (law repository)'
        else:
            continue
        v = l['version'] if l['version'] in ('publishedVersion', 'acceptedVersion') else ''
        found[a['id']] = {'url': l['url'], 'version': v, 'source': 'openalex', 'host': l['host'], 'check': check,
                          'title': a['t']}
    return found

# ---------------------------------------------------------------- repo (repo_copies cache, extra rules)


SPELLED = {'harvardlawreview': 'hlr', 'harvlrev': 'hlr', 'columbialawreview': 'colr', 'columlrev': 'colr',
           'virginialawreview': 'valr', 'valrev': 'valr', 'stanfordlawreview': 'slr', 'stanlrev': 'slr',
           'yalelawjournal': 'ylj', 'yalelj': 'ylj', 'californialawreview': 'calr', 'califlrev': 'calr',
           'supremecourtreview': 'scr', 'supctrev': 'scr', 'universityofpennsylvanialawreview': 'pennlr', 'upalrev': 'pennlr'}


def file_cites(url):
    name = urllib.parse.unquote(url.rsplit('/', 1)[-1]).rsplit('.', 1)[0]
    out = set()
    for vol, mid, pg in re.findall(r'(?<!\d)(\d{1,4})[ _.-]*([A-Za-z][A-Za-z._ -]{4,40}?)[ _.-]*(\d{1,4})(?!\d)', name):
        j = SPELLED.get(re.sub(r'[^a-z]', '', mid.lower()).removeprefix('the'))
        if j:
            out.add((j, int(vol), int(pg)))
    return out


def words_close(a, b):
    w = lambda s: {x for x in re.sub(r'[^a-z0-9 ]', ' ', html.unescape(s or '').lower()).split() if len(x) > 3}
    wa, wb = w(a), w(b)
    return bool(wa and wb) and len(wa & wb) >= 0.5 * min(len(wa), len(wb))


def repo_matches(arts):
    cand = candidates(arts)
    by_j = {}
    for a in cand:
        by_j.setdefault(a['j'], []).append(a)
    titles = {}
    for a in cand:
        titles.setdefault(norm(a['t'])[:30], []).append(a)
    found = {}
    for p in sorted(glob.glob(os.path.join(REPO, '*.json'))):
        key = os.path.basename(p)[:-5]
        if key in ('status', 'matches'):
            continue
        try:
            recs = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            f = r.get('file')
            if not f:
                continue
            for j, vol, pg in file_cites(f):
                for a in by_j.get(j, []):
                    if a.get('v') == vol and a.get('fp') == pg and a['id'] not in found and words_close(a['t'], r.get('title')):
                        found[a['id']] = {'url': f, 'version': 'publishedVersion', 'source': 'repo', 'host': key,
                                          'check': 'file-name citation', 'title': r.get('title')}
            n = norm(r.get('title'))
            if len(n) <= 30:
                continue
            for a in titles.get(n[:30], []):
                if a['id'] in found or norm(a['t']) == n or not same_title(r.get('title'), a['t']):
                    continue          # exact titles are repo_copies.py's own rule
                au = {surname(x) for x in a.get('a') or []} - {''}
                ru = {surname(x) for x in r.get('authors') or []} - {''}
                if au & ru and r.get('year') and a.get('y') and abs(r['year'] - a['y']) <= 1:
                    found[a['id']] = {'url': f, 'version': 'publishedVersion', 'source': 'repo', 'host': key,
                                      'check': 'title prefix + author + year', 'title': r.get('title')}
    return found

# ---------------------------------------------------------------- sites (journals' own sites)


SITES = {   # journal -> sitemap index
    'hlr': 'https://harvardlawreview.org/sitemap_index.xml',
    'colr': 'https://columbialawreview.org/sitemap_index.xml',
    'valr': 'https://virginialawreview.org/sitemap.xml',
    'slr': 'https://review.law.stanford.edu/sitemap_index.xml',
}


def site_urls(j):
    idx = cached('sites', SITES[j])
    subs = [html.unescape(u) for u in re.findall(r'<loc>([^<]+)</loc>', idx['body']) if u.endswith('.xml') or 'sitemap' in u]
    subs = [u for u in subs if re.search(r'post|content|article|print|page-sitemap|wp-sitemap-posts', u)] or subs
    urls = []
    for u in subs[:40]:
        urls += [html.unescape(x) for x in re.findall(r'<loc>([^<]+)</loc>', cached('sites', u)['body'])]
    return urls


def site_choices(arts):
    out = []
    for j in SITES:
        cand = [a for a in candidates(arts) if a['j'] == j]
        if not cand:
            continue
        by = {}
        for u in site_urls(j):
            slug = u.rstrip('/').rsplit('/', 1)[-1]
            by.setdefault(norm(slug.replace('-', ' ')), []).append(u)
        for a in cand:
            n = norm(a['t'])
            if len(n) > 12:
                for u in by.get(n, [])[:3]:
                    out.append((a, u))
    return out


def site_matches(arts):
    found = {}
    for a, u in site_choices(arts):
        p = os.path.join(RAW, 'pages', hashlib.md5(u.encode()).hexdigest() + '.json')
        if not os.path.exists(p):
            continue
        rec = json.load(open(p, encoding='utf-8'))
        body = rec['body']
        if rec['status'] != 200 or not page_title_ok(body, a['t']):
            continue
        # a volume named on the page must be ours
        vols = {int(v) for v in re.findall(r'\b(?:Vol(?:ume)?\.?\s*|vol-)(\d{2,3})\b', body + u)}
        if vols and a.get('v') not in vols:
            continue
        found[a['id']] = {'url': u, 'version': 'publishedVersion', 'source': 'sites',
                          'host': urllib.parse.urlparse(u).netloc, 'check': 'page', 'title': a['t']}
    return found

# ---------------------------------------------------------------- hathi (pre-1931 volumes)


ISSN = {'hlr': '0017-811X', 'ylj': '0044-0094', 'colr': '0010-1958', 'valr': '0042-6601', 'calr': '0008-1221',
        'pennlr': '0041-9907'}


def hathi_items(j):
    rec = cached('hathi', f'https://catalog.hathitrust.org/api/volumes/brief/issn/{ISSN[j]}.json')
    try:
        return json.loads(rec['body']).get('items', [])
    except Exception:
        return []


def hathi_matches(arts):
    found = {}
    for j in ISSN:
        vols = {}
        for it in hathi_items(j):
            ec = it.get('enumcron') or ''
            m = re.match(r'\s*v\.?\s*(\d{1,3})\b(?![-/]\d)', ec)
            if not m or re.search(r'index|suppl|pt\.|no\.|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec', ec, re.I)                     or it.get('rightsCode') != 'pd':      # month ranges mark half volumes: the page may be in the other half
                continue
            years = [int(y) for y in re.findall(r'\b(1[89]\d\d)\b', ec)]
            if years and max(years) >= 1931:
                continue
            vols.setdefault(int(m.group(1)), []).append(it)
        for a in candidates(arts):
            if a['j'] != j or not a.get('y') or a['y'] >= 1931 or not a.get('v') or not a.get('fp'):
                continue
            items = sorted(vols.get(a['v'], []), key=lambda it: (it.get('orig') != 'Harvard University', it['htid']))
            if items:
                found[a['id']] = {'url': f"https://babel.hathitrust.org/cgi/pt?id={items[0]['htid']}&num={a['fp']}",
                                  'version': 'publishedVersion', 'source': 'hathi', 'host': 'babel.hathitrust.org',
                                  'check': f"pd volume ({items[0].get('enumcron')})", 'title': a['t']}
    return found

# ---------------------------------------------------------------- lookup / apply


def lookup(srcs):
    _, data = load()
    arts = data['articles']
    srcs = srcs or ['openalex', 'repo', 'sites', 'hathi']
    if 'openalex' in srcs:
        openalex_lookup(arts)
    if 'sites' in srcs:
        ch = site_choices(arts)
        print(f'sites: {len(ch)} pages to check', flush=True)
        for a, u in ch:
            cached('pages', u)
    if 'hathi' in srcs:
        for j in ISSN:
            print(f'hathi {j}: {len(hathi_items(j))} items', flush=True)
    if 'repo' in srcs:
        print('repo: reads data/raw/repo_copies (nothing to fetch)')


def apply(dry, with_hathi):
    raw, data = load()
    arts = data['articles']
    cand = candidates(arts)
    ids = {a['id']: a for a in arts}
    srcs = [('repo', repo_matches), ('sites', site_matches), ('openalex', openalex_matches)]
    if with_hathi or dry:
        srcs.append(('hathi', hathi_matches))
    found, per = {}, {}
    for name, fn in srcs:
        got = fn(arts)
        per[name] = got
        for k, v in got.items():
            if k not in found and (name != 'hathi' or with_hathi):
                found[k] = v
    print(f'{len(cand)} DOI-only articles without a free route')
    js = sorted({a['j'] for a in cand}, key=lambda j: -sum(1 for a in cand if a['j'] == j))
    print('source     ' + ' '.join(f'{j:>6}' for j in js) + '   total')
    for name, got in per.items():
        row = [sum(1 for k in got if ids[k]['j'] == j) for j in js]
        print(f'{name:10} ' + ' '.join(f'{n:6}' for n in row) + f'   {len(got)}' + ('   (not applied without --with-hathi)' if name == 'hathi' and not with_hathi else ''))
    top = sorted(cand, key=lambda a: -(a.get('c') or 0))[:500]
    post = [a for a in cand if (a.get('y') or 0) >= 1931]
    print(f'applied set: {len(found)}; of the 500 most cited: {sum(1 for a in top if a["id"] in found)}; '
          f'1931 and later: {sum(1 for a in post if a["id"] in found)} of {len(post)}')
    for name, got in per.items():
        checks = {}
        for v in got.values():
            checks[v['check'] if name != 'hathi' else 'pd volume'] = checks.get(v['check'] if name != 'hathi' else 'pd volume', 0) + 1
        hosts = {}
        for v in got.values():
            hosts[v['host']] = hosts.get(v['host'], 0) + 1
        print(f'  {name}: {checks}; hosts {sorted(hosts.items(), key=lambda x: -x[1])[:12]}')
    os.makedirs(RAW, exist_ok=True)
    allm = {k: v for got in per.values() for k, v in got.items()}
    json.dump({k: dict(v, applied=k in found and found[k] is v) for k, v in allm.items()},
              open(os.path.join(RAW, 'found.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if dry:
        random.seed(11)
        pool = sorted(allm)
        for k in random.sample(pool, min(15, len(pool))):
            a, f = ids[k], allm[k]
            print(f"\n  {k} [{f['source']}: {f['check']}] {a.get('v')}:{a.get('fp')} ({a.get('y')}) c={a.get('c')}\n"
                  f"    ours:   {a['t']}\n    source: {' '.join(str(f['title']).split())}\n    {f['url']}")
        same = raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
        print('\n(dry run: articles.js not written; serialization round-trip', 'identical)' if same == raw else 'DIFFERS: check before applying)')
        return
    n = 0
    for a in arts:
        f = found.get(a['id'])
        if f and not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv'):
            a['oa'] = f['url']
            if f['version']:
                a['oav'] = f['version']
            n += 1
    open(ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{n} articles given a free copy')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'lookup':
        lookup([s for s in sys.argv[2:] if not s.startswith('-')])
    elif cmd == 'apply':
        apply('--dry-run' in sys.argv, '--with-hathi' in sys.argv)
    else:
        print(__doc__)
