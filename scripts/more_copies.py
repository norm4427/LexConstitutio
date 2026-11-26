"""Third pass for free copies of articles that still have no free route (no `oa`, `pdf` or `pub`, not a book review), from
sources the earlier scripts (free_copies, open_copies, s2_copies, modern_copies, repo_copies, archive_copies, pd_copies)
did not cover in this checkout. It writes a match file only; it never edits docs/data/articles.js.

Sources (cached under data/raw/more_copies/, about one request a second per host, generic User-Agent and contact address):
  unpaywall  api.unpaywall.org record for each DOI: its open-access locations.
  s2         Semantic Scholar batch API (openAccessPdf), 500 DOIs a request.
  openalex   OpenAlex works (OPENALEX_KEY from .keys.env via local_keys.py; the key is never printed or cached): by DOI,
             50 a request, and by title for articles without a DOI; its open-access locations.
  sites      the article's own page on its journal's site (nyulawreview.org, uclalawreview.org, texaslawreview.org,
             harvardlawreview.org, ...), for a PDF of the piece on the same site.
Rules (err toward leaving a link out):
  - DOI sources: the record's title equals ours after normalizing (or, over 30 characters, one is a prefix of the other),
    its year is within one of ours, an author surname agrees where the record names authors, and the copy's host is an
    institutional or official one (.edu / .ac.xx / a university or law-school repository; never SSRN, ResearchGate,
    Academia, CORE, Semantic Scholar, JSTOR, HeinOnline, Google, or a publisher aggregator). The landing page is fetched and
    must show our title, unless the host answers with a bot check (then kept only for .edu repositories, marked so).
  - sites: our `u` is the piece's page on the journal's site; a PDF counts only when it is on the same site, the page
    links exactly one such PDF in the piece's body, and the PDF answers with application/pdf.
    python scripts/more_copies.py lookup [unpaywall|s2|openalex|sites ...]
    python scripts/more_copies.py match          # writes the match file (see OUT) and prints counts and a sample
"""
import hashlib, html, json, os, random, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from collections import Counter

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
EMAIL = 'lexconstitutio-build@example.org'     # generic contact address; nothing personal is sent
ART = 'docs/data/articles.js'
CACHE = 'data/raw/more_copies'
OUT = os.environ.get('MORE_COPIES_OUT', os.path.join(CACHE, 'matches.json'))
_last = {}
NEW_REPOS = {'alabama', 'mclaw', 'tulsa', 'fiu', 'wyoming', 'barry', 'ubc', 'dalhousie', 'pepperdine', 'nebraska', 'valpo',
             'rwu', 'denver', 'dayton', 'louisville', 'siu', 'niu', 'southcarolina', 'unm', 'unh', 'uconn', 'wayne',
             'duquesne', 'arkansas', 'hamline'}


def get(url, binary=False, gap=1.0, method=None, data=None, headers=None, head=False):
    host = urllib.parse.urlsplit(url).hostname
    for t in range(4):
        wait = _last.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data, method=method)
            r = urllib.request.urlopen(req, timeout=60)
            if head:
                return r.headers.get('Content-Type', ''), r.read(2048)
            b = r.read()
            return b if binary else b.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = e.headers.get('Retry-After')
                xr = e.headers.get('x-ratelimit-retry-after')
                if not wait and xr:
                    import datetime
                    until = datetime.datetime.fromisoformat(xr.replace('+0000', '+00:00'))
                    wait = (until - datetime.datetime.now(datetime.timezone.utc)).total_seconds() + 5
                time.sleep(max(5, float(wait or 30)))
                continue
            if e.code in (400, 401, 403, 404, 410, 451):
                raise
            time.sleep(5 * (t + 1))
        except Exception:
            time.sleep(5 * (t + 1))
    raise IOError('gave up on ' + url)


def load():
    raw = open(ART, encoding='utf-8').read()
    return json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def candidates(d):
    return [a for a in d['articles'] if not a.get('oa') and not a.get('pdf') and not a.get('pub') and not a.get('rv')]


def doi_of(a):
    u = a.get('u') or ''
    m = re.match(r'https?://(?:dx\.)?doi\.org/(10\..+)$', u)
    return urllib.parse.unquote(m.group(1)).lower() if m else None


def norm(s):
    s = html.unescape(s or '')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'&', ' and ', s)
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


def title_ok(ours, theirs):
    a, b = norm(ours), norm(theirs)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) > 30 and len(b) > 30 and (a.startswith(b) or b.startswith(a)):
        return True
    return False


def surnames(names):
    out = set()
    for n in names or []:
        n = norm(n)
        if n:
            w = [x for x in n.split() if x not in ('jr', 'sr', 'ii', 'iii', 'iv')]
            if w:
                out.add(w[-1])
    return out


BAD = ('ssrn', 'researchgate', 'academia.edu', 'core.ac.uk', 'semanticscholar', 'jstor.org', 'heinonline', 'google',
       'doi.org', 'scholar.archive.org', 'europepmc', 'citeseerx', 'zenodo', 'figshare', 'philpapers', 'scite.ai',
       'hathitrust', 'archive.org', 'questia', 'proquest', 'ebsco', 'westlaw', 'lexis', 'wiley', 'tandfonline',
       'springer', 'cambridge.org', 'oup.com', 'sagepub', 'elsevier', 'sciencedirect', 'muse.jhu.edu')
REPO_WORDS = ('repository', 'scholarship', 'digitalcommons', 'commons.', 'dspace', 'eprints', 'escholarship.org',
              'lawcat', 'openyls', 'unbound', 'ir.', 'dash.harvard', 'deepblue', 'scholarworks', 'lawrepository',
              'researchonline', 'research-repository', 'works.bepress.com', 'hdl.handle.net', 'nellco')


def host_kind(url):
    h = (urllib.parse.urlsplit(url).hostname or '').lower()
    if not h or any(b in h for b in BAD):
        return None
    if h.endswith('.edu') or re.search(r'\.(ac|edu)\.[a-z]{2}$', h) or h.endswith('.edu.au'):
        return 'edu'
    if any(w in h for w in REPO_WORDS):
        return 'repo'
    return None


def cache_path(*parts):
    p = os.path.join(CACHE, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def key(s):
    return hashlib.md5(s.encode()).hexdigest()


# ---------------------------------------------------------------- lookups
def lookup_unpaywall(cands):
    todo = [(a, doi_of(a)) for a in cands if doi_of(a)]
    n = 0
    for a, doi in todo:
        p = cache_path('unpaywall', key(doi) + '.json')
        if os.path.exists(p):
            continue
        url = f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={EMAIL}'
        try:
            body = get(url, gap=0.5)
        except urllib.error.HTTPError as e:
            body = json.dumps({'error': e.code})
        except IOError:
            continue
        open(p, 'w', encoding='utf-8').write(body)
        n += 1
        if n % 200 == 0:
            print('unpaywall', n, 'fetched', flush=True)
    print('unpaywall done', n)


OA_SELECT = 'id,doi,display_name,publication_year,authorships,locations,biblio'


def openalex(params):
    """One OpenAlex /works request with the key added; errors are reported without the URL (it holds the key)."""
    import local_keys  # noqa: F401  (loads OPENALEX_KEY from .keys.env)
    k = os.environ.get('OPENALEX_KEY', '')
    q = dict(params, **({'api_key': k} if k else {}))
    try:
        return json.loads(get('https://api.openalex.org/works?' + urllib.parse.urlencode(q), gap=0.15)).get('results', [])
    except urllib.error.HTTPError as e:
        print('openalex HTTP', e.code, flush=True)
    except Exception as e:
        print('openalex request failed', type(e).__name__, flush=True)
    return None


def lookup_openalex(cands):
    dois = sorted({doi_of(a) for a in cands if doi_of(a)})
    for i in range(0, len(dois), 50):
        chunk = dois[i:i + 50]
        p = cache_path('openalex', 'doi_' + key('|'.join(chunk)) + '.json')
        if os.path.exists(p):
            continue
        res = openalex({'filter': 'doi:' + '|'.join(chunk), 'per-page': 50, 'select': OA_SELECT})
        if res is None:
            continue
        json.dump({(w.get('doi') or '').replace('https://doi.org/', '').lower(): w for w in res}, open(p, 'w', encoding='utf-8'))
        if i % 1000 == 0:
            print('openalex doi', i + len(chunk), '/', len(dois), flush=True)
    rest = [a for a in cands if not doi_of(a) and len(norm(a['t']).split()) >= 2]
    for i in range(0, len(rest), 20):
        chunk = rest[i:i + 20]
        p = cache_path('openalex', 'title_' + key('|'.join(a['id'] for a in chunk)) + '.json')
        if os.path.exists(p):
            continue
        phrases = ['"' + ' '.join(norm(re.split(r'[:?]', a['t'])[0]).split()[:12]) + '"' for a in chunk]
        res = openalex({'filter': 'title.search:' + '|'.join(phrases), 'per-page': 200, 'select': OA_SELECT})
        if res is None:
            continue
        json.dump({'ids': [a['id'] for a in chunk], 'results': res}, open(p, 'w', encoding='utf-8'))
        if i % 400 == 0:
            print('openalex title', i + len(chunk), '/', len(rest), flush=True)
    print('openalex done')


def openalex_records():
    """doi -> work, and article id -> [works] from the title searches."""
    by_doi, by_id = {}, {}
    d = os.path.join(CACHE, 'openalex')
    for f in os.listdir(d) if os.path.isdir(d) else []:
        r = json.load(open(os.path.join(d, f), encoding='utf-8'))
        if f.startswith('doi_'):
            by_doi.update(r)
        else:
            for i in r['ids']:
                by_id[i] = r['results']
    return by_doi, by_id


def lookup_s2(cands):
    dois = sorted({doi_of(a) for a in cands if doi_of(a)})
    for i in range(0, len(dois), 500):
        chunk = dois[i:i + 500]
        p = cache_path('s2', key('|'.join(chunk)) + '.json')
        if os.path.exists(p):
            continue
        body = json.dumps({'ids': ['DOI:' + x for x in chunk]}).encode()
        url = 'https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,authors,openAccessPdf,externalIds'
        for t in range(6):
            try:
                res = get(url, gap=3, method='POST', data=body, headers={'Content-Type': 'application/json'})
                break
            except Exception as e:
                print('s2 retry', e, flush=True)
                time.sleep(30)
        else:
            continue
        out = dict(zip(chunk, json.loads(res)))
        json.dump(out, open(p, 'w', encoding='utf-8'))
        print('s2', i + len(chunk), flush=True)


def core_query(q, p):
    """One CORE v3 search (no key: 10 requests per 10 minutes, so one a minute), cached at p."""
    if os.path.exists(p):
        return
    url = 'https://api.core.ac.uk/v3/search/works/?' + urllib.parse.urlencode({'q': q, 'limit': 100})
    for t in range(5):
        try:
            body = get(url, gap=61)
            json.loads(body)
            open(p, 'w', encoding='utf-8').write(body)
            return
        except urllib.error.HTTPError as e:
            print('core', e.code, flush=True)
            if e.code in (400, 401, 403):
                open(p, 'w', encoding='utf-8').write(json.dumps({'error': e.code}))
                return
        except (IOError, ValueError) as e:
            print('core err', e, flush=True)
        time.sleep(120)


def lookup_core(cands):
    dois = sorted({doi_of(a) for a in cands if doi_of(a)})
    for i in range(0, len(dois), 40):
        chunk = dois[i:i + 40]
        core_query(' OR '.join(f'doi:"{x}"' for x in chunk), cache_path('core', 'doi_' + key('|'.join(chunk)) + '.json'))
        print('core doi', i + len(chunk), flush=True)
    # titles, most cited first; words only, so the query parser sees no stray operators
    order = sorted(cands, key=lambda a: -(a.get('c') or 0))
    ts = []
    for a in order:
        w = norm(a['t']).split()
        if len(w) >= 3:
            ts.append(' '.join(w[:12]))
    for i in range(0, len(ts), 30):
        chunk = ts[i:i + 30]
        core_query(' OR '.join(f'title:"{x}"' for x in chunk), cache_path('core', 'title_' + key('|'.join(chunk)) + '.json'))
        print('core title', i + len(chunk), flush=True)


def lookup_sites(cands):
    for a in cands:
        u = a.get('u') or ''
        if not u or 'doi.org' in u:
            continue
        p = cache_path('sites', key(u) + '.html')
        if os.path.exists(p):
            continue
        try:
            body = get(u)
        except urllib.error.HTTPError as e:
            body = f'<!-- HTTP {e.code} -->'
        except IOError:
            continue
        open(p, 'w', encoding='utf-8').write(body)


# ---------------------------------------------------------------- checks
def page_shows(url, title):
    """Fetch a landing page (cached) and say whether it shows our title: True, False, or 'blocked'."""
    p = cache_path('pages', key(url) + '.html')
    if os.path.exists(p):
        body = open(p, encoding='utf-8').read()
    else:
        try:
            ct, head = get(url, head=True) if re.search(r'\.pdf$|viewcontent\.cgi|/download/?$', url.lower().split('#')[0].split('?')[0] if 'viewcontent' not in url else url) else (None, None)
        except urllib.error.HTTPError as e:
            ct, head = f'HTTP {e.code}', b''
        except IOError:
            ct, head = 'ERR', b''
        if ct is not None:
            body = f'<!-- PDF {ct} {head[:5]!r} -->'
        else:
            try:
                body = get(url)
            except urllib.error.HTTPError as e:
                body = f'<!-- HTTP {e.code} -->'
            except IOError:
                body = '<!-- ERR -->'
        open(p, 'w', encoding='utf-8').write(body)
    if body.startswith('<!-- PDF'):
        return 'pdf' if "%PDF" in body else ('blocked' if 'HTTP 403' in body or 'text/html' in body else False)
    if body.startswith('<!-- HTTP 403') or 'challenge-platform' in body or 'Just a moment' in body[:3000] \
            or 'Human Verification' in body[:5000]:
        return 'blocked'
    n = norm(title)
    words = n.split()
    text = norm(re.sub(r'<[^>]+>', ' ', body))
    if n in text:
        return True
    if len(words) >= 6 and ' '.join(words[:6]) in text:
        return True
    return False


def core_records():
    out = {'doi': {}, 'title': {}}
    d = os.path.join(CACHE, 'core')
    for f in os.listdir(d) if os.path.isdir(d) else []:
        try:
            res = json.load(open(os.path.join(d, f), encoding='utf-8')).get('results') or []
        except ValueError:
            continue
        for r in res:
            if r.get('doi'):
                out['doi'].setdefault(r['doi'].lower(), []).append(r)
            out['title'].setdefault(norm(r.get('title')), []).append(r)
    return out


def doi_matches(cands):
    found = {}
    s2 = {}
    for f in os.listdir(os.path.join(CACHE, 's2')) if os.path.isdir(os.path.join(CACHE, 's2')) else []:
        s2.update(json.load(open(os.path.join(CACHE, 's2', f), encoding='utf-8')))
    core = core_records()
    oa_doi, oa_title = openalex_records()
    for a in cands:
        doi = doi_of(a)
        ours = surnames(a.get('a'))
        opts = []
        # CORE: by DOI, or by title when the title is distinctive and an author surname agrees
        nt = norm(a['t'])
        for r in core['doi'].get(doi, []) + (core['title'].get(nt, []) if len(nt) >= 20 and ours else []):
            if not title_ok(a['t'], r.get('title')) or not r.get('yearPublished') or abs(r['yearPublished'] - a['y']) > 1:
                continue
            theirs = surnames(x.get('name', '').split(',')[0] if ',' in x.get('name', '') else x.get('name') for x in r.get('authors') or [])
            if (r.get('doi') or '').lower() != doi and not (ours & theirs):
                continue
            if ours and theirs and not ours & theirs:
                continue
            for url in (r.get('sourceFulltextUrls') or []) + [l.get('url') for l in r.get('links') or [] if l.get('type') == 'display']:
                if url and host_kind(url):
                    opts.append(('core', url, '', ''))
        p = os.path.join(CACHE, 'unpaywall', key(doi) + '.json') if doi else ''
        if doi and os.path.exists(p):
            r = json.load(open(p, encoding='utf-8'))
            if r.get('title') and title_ok(a['t'], r['title']) and (not r.get('year') or abs(r['year'] - a['y']) <= 1):
                theirs = {norm(x.get('family') or '').split()[-1] for x in r.get('z_authors') or [] if norm(x.get('family') or '')}
                # a location filed under another journal's volume (Digital Commons /<journal>/volN/issN/ path) means
                # Unpaywall tied a same-titled piece to our DOI: drop the record's locations altogether
                urls = [x for l in r.get('oa_locations') or [] for x in (l.get('url_for_landing_page'), l.get('url'))]
                foreign = any((lambda jv: jv and int(jv.group(1)) != a.get('v'))(re.search(r'/[a-z_]+/vol(\d+)/iss\d+', x or ''))
                              for x in urls)
                if (not theirs or not ours or ours & theirs) and not foreign:
                    for loc in r.get('oa_locations') or []:
                        for url in (loc.get('url_for_landing_page'), loc.get('url_for_pdf')):
                            if url and host_kind(url):
                                opts.append(('unpaywall', url, loc.get('version') or '', loc.get('repository_institution') or ''))
        r = s2.get(doi) if doi else None
        if r and (r.get('openAccessPdf') or {}).get('url') and title_ok(a['t'], r.get('title')) \
                and (not r.get('year') or abs(r['year'] - a['y']) <= 1):
            theirs = surnames(x.get('name') for x in r.get('authors') or [])
            url = r['openAccessPdf']['url']
            if (not theirs or not ours or ours & theirs) and host_kind(url):
                opts.append(('s2', url, '', ''))
        # OpenAlex: the DOI record, or a title-search hit (title, year and an author surname must all agree)
        works = ([oa_doi[doi]] if doi in oa_doi else []) + ([w for w in oa_title.get(a['id'], [])] if not doi else [])
        for w in works:
            if not title_ok(a['t'], w.get('display_name')) or not w.get('publication_year')                     or abs(w['publication_year'] - a['y']) > 1:
                continue
            theirs = surnames((x.get('author') or {}).get('display_name') for x in w.get('authorships') or [])
            if not doi and not (ours and theirs and ours & theirs):
                continue
            if ours and theirs and not ours & theirs:
                continue
            urls = [x for l in w.get('locations') or [] for x in (l.get('landing_page_url'), l.get('pdf_url'))]
            if any((lambda jv: jv and int(jv.group(1)) != a.get('v'))(re.search(r'/[a-z_]+/vol(\d+)/iss\d+', x or '')) for x in urls):
                continue
            for l in w.get('locations') or []:
                if not l.get('is_oa'):
                    continue
                for url in (l.get('landing_page_url'), l.get('pdf_url')):
                    if url and host_kind(url):
                        opts.append(('openalex', url, l.get('version') or '', ''))
        seen = set()
        for src, url, ver, inst in opts:
            if url in seen:
                continue
            seen.add(url)
            if 'hdl.handle.net/2027/' in url:          # HathiTrust volume handles: a book, not this article
                continue
            jv = re.search(r'/[a-z_]+/vol(\d+)/iss\d+/', url) or re.search(r'/viewcontent/(\d+)_\d+_\d+_', url)
            if jv and int(jv.group(1)) != a.get('v'):  # another journal's (or volume's) piece with the same title
                continue
            ok = page_shows(url, a['t'])
            kind = host_kind(url)
            if 'escholarship.org' in url:              # the University of California's own repository
                kind = 'edu'
            if ok is True or ok == 'pdf' or (ok == 'blocked' and kind == 'edu'):
                found[a['id']] = {'url': url, 'source': src, 'host': urllib.parse.urlsplit(url).hostname,
                                  'version': {'publishedVersion': 'publishedVersion', 'acceptedVersion': 'acceptedVersion',
                                              'submittedVersion': 'submittedVersion'}.get(ver, 'publishedVersion'),
                                  'check': {True: 'page shows title', 'pdf': 'PDF served', 'blocked': 'bot check (.edu repository)'}[ok],
                                  'title': a['t'], 'j': a['j'], 'y': a['y']}
                break
    return found


PDF_SKIP = re.compile(r'submission|guideline|style|masthead|bylaws|application|policy|cover|factsheet', re.I)


def site_matches(cands):
    found = {}
    for a in cands:
        u = a.get('u') or ''
        if not u or 'doi.org' in u:
            continue
        p = os.path.join(CACHE, 'sites', key(u) + '.html')
        if not os.path.exists(p):
            continue
        body = open(p, encoding='utf-8').read()
        if body.startswith('<!-- HTTP'):
            continue
        host = urllib.parse.urlsplit(u).hostname.replace('www.', '')
        # the piece's body: its <article> element when it holds links, else the page without header, footer and menus
        scopes = [m.group(0) for m in [re.search(r'<article\b.*?</article>', body, re.S | re.I),
                                       re.search(r'<main\b.*?</main>', body, re.S | re.I)] if m]
        scopes.append(re.sub(r'<(header|footer|nav)\b.*?</\1>', ' ', body, flags=re.S | re.I))
        chosen = None
        for main in scopes:
            pdfs = site_pdfs(a, u, host, main)
            if len(pdfs) == 1:
                chosen = pdfs
                break
        if not chosen:
            continue
        pdfs = chosen
        if not title_ok(a['t'], a['t']) or norm(a['t'])[:40] not in norm(re.sub(r'<[^>]+>', ' ', body)):
            continue
        ok = page_shows(pdfs[0], a['t'])
        if ok != 'pdf':
            continue
        found[a['id']] = {'url': pdfs[0], 'source': 'site', 'host': host, 'version': 'publishedVersion',
                          'check': "one same-site PDF on the piece's page, named for it or labelled as its download; PDF served",
                          'title': a['t'], 'j': a['j'], 'y': a['y']}
    return found


def site_pdfs(a, u, host, main):
    pdfs = []
    for href in re.findall(r'href=["\']([^"\']+?(?:\.pdf(?:\?[^"\']*)?|viewcontent\.cgi\?[^"\']*|/download/?))["\']', main, re.I):
        full = urllib.parse.urljoin(u, html.unescape(href))
        if (urllib.parse.urlsplit(full).hostname or '').replace('www.', '') != host:
            continue
        if PDF_SKIP.search(full.rsplit('/', 1)[-1]):
            continue
        if full not in pdfs:
            pdfs.append(full)
    if True:
        # the piece's own PDF: its file name carries an author surname, a title word or the volume and first page
        sig = surnames(a.get('a')) | {w for w in norm(a['t']).split() if len(w) >= 6}
        if a.get('v') and a.get('fp'):
            sig.add(f"{a['v']} {a['fp']}")

        def fits(url):
            raw = urllib.parse.unquote(url.split('?')[0].rsplit('/', 1)[-1]).rsplit('.', 1)[0]
            name = ' ' + norm(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw).replace('_', ' ')) + ' '
            flat = name.replace(' ', '')
            if a.get('v') and re.match(r' %s [a-z ]*\bl rev \d+ $' % a['v'], name):     # 101-NYU-L-Rev-593.pdf
                return True
            return any(' ' + x + ' ' in name or (len(x) >= 6 and x.replace(' ', '') in flat) for x in sig)
        # or the page labels it as the piece's download (a "Download" / "download as a PDF" link or a class="pdf" button)
        labelled = set()
        for tag, inner in re.findall(r'(<a\b[^>]*>)(.{0,120}?)</a>', main, re.S | re.I):
            hm = re.search(r'''href=["']([^"']+)["']''', tag)
            if hm and (re.search(r'''class=["'][^"']*\bpdf\b''', tag) or re.search(r'download', inner, re.I)):
                labelled.add(urllib.parse.urljoin(u, html.unescape(hm.group(1))))
        return [x for x in pdfs if fits(x) or x in labelled]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'match'
    d = load()
    cands = candidates(d)
    print(len(cands), 'candidates')
    if cmd == 'lookup':
        which = sys.argv[2:] or ['s2', 'unpaywall', 'sites']
        for w in which:
            {'unpaywall': lookup_unpaywall, 's2': lookup_s2, 'sites': lookup_sites, 'core': lookup_core, 'openalex': lookup_openalex}[w](cands)
    elif cmd == 'match':
        found = site_matches(cands)
        # law-school repositories added to repo_copies.py for this pass (its `apply --dry-run` writes the matches):
        # a published copy there wins over an Unpaywall / Semantic Scholar one
        byid = {a['id']: a for a in cands}
        rp = 'data/raw/repo_copies/matches.json'
        for k, v in (json.load(open(rp, encoding='utf-8')).items() if os.path.exists(rp) else []):
            if k in byid and k not in found and v.get('repo') in NEW_REPOS:
                a = byid[k]
                found[k] = {'url': v['url'], 'source': 'repo:' + v['repo'], 'host': urllib.parse.urlsplit(v['url']).hostname,
                            'version': v.get('version') or 'publishedVersion',
                            'check': 'repo_copies.py ' + v.get('via', '') + ' match; record ' + v.get('page', ''),
                            'title': a['t'], 'j': a['j'], 'y': a['y']}
        for k, v in doi_matches(cands).items():
            found.setdefault(k, v)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        json.dump(found, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(len(found), 'matches ->', OUT)
        print(Counter(v['source'] for v in found.values()))
        print(Counter(v['host'] for v in found.values()).most_common(30))
        print(Counter(v['j'] for v in found.values()))
        print(Counter(v['check'] for v in found.values()))


if __name__ == '__main__':
    main()
