"""Free full text from law-school faculty scholarship repositories (bepress Digital Commons, DSpace, Invenio), for articles
that still link only to a DOI (JSTOR): authors post their own law review articles there with the citation.

Step 1 (harvest): each repository's metadata is harvested over OAI-PMH, one request a second per host, following resumption
  tokens. Pages are cached in data/raw/repo_copies/<repo>/ and a run that stops picks up where it left off; a finished
  harvest is marked with a .done file (delete the repository's folder to harvest it again). Then each repository's pages are
  boiled down to data/raw/repo_copies/<repo>.json: title, authors, year, citation strings, full-text URL.
    Digital Commons: oai_dc (carries the viewcontent.cgi / .../viewcontent/ full-text link) + qualified-dublin-core
      (carries dc:source, the journal and first page, and sometimes the whole citation);
    DSpace 7 (Yale's openYLS): dim (dc.identifier.citation such as "31 THE YALE LAW JOURNAL 229 (1922)") + ore (the PDF);
    Invenio (Berkeley's lawCat): marcxml (773 journal / volume, 856 full text).
  Multi-school repositories harvest only their sets whose name or spec mentions law.
Step 2 (apply): a record is linked to an article only when it offers a full-text file on the repository's own host (records
  that are only metadata, or that point to JSTOR, SSRN or a publisher, are skipped) and, erring toward leaving a link out:
  - its citation names our journal and our volume, and the first page agrees when both sides give one (with no page to
    compare, one author's surname must also match and the titles must share most of their words); or its citation names our
    journal and our first page with no volume (Columbia's records do this), the year is within one and an author matches;
  - OR its normalized title equals ours, one author's surname matches and the year is within one of ours (and it does not
    cite a different volume or page of our journal).
  Only articles with no `oa`, `pdf` or `pub` that are not book reviews get a link: `oa` = the full-text URL and `oav` =
  publishedVersion unless the record calls itself a preprint / working paper (then no `oav`, as free_copies.py does).
  Nothing else in the file changes. Matches are also written to data/raw/repo_copies/matches.json.
  Penn Carey Law (Quartex, no OAI-PMH): sitemap title slugs matched to our titles, document page meta description parsed.
Run from the repo root (never before open_copies.py, which clears and rebuilds `oa`):
    python scripts/repo_copies.py harvest [repo ...]     # all repositories, or only the named ones
    python scripts/repo_copies.py apply --dry-run        # counts per journal and repository, 15 random matches; writes nothing
    python scripts/repo_copies.py apply
"""
import html, json, os, random, re, sys, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
ART = 'docs/data/articles.js'
CACHE = 'data/raw/repo_copies'

# key -> (kind, OAI base URL, sets: None = whole repository, 'law' = its sets that mention law, or a list of set specs)
DC = lambda host, sets=None: ('dc', f'https://{host}/do/oai/', sets)
REPOS = {
    'columbia': DC('scholarship.law.columbia.edu'), 'chicago': DC('chicagounbound.uchicago.edu'),
    'georgetown': DC('scholarship.law.georgetown.edu'), 'michigan': DC('repository.law.umich.edu'),
    'duke': DC('scholarship.law.duke.edu'), 'cornell': DC('scholarship.law.cornell.edu'),
    'northwestern': DC('scholarlycommons.law.northwestern.edu'), 'gw': DC('scholarship.law.gwu.edu'),
    'bu': DC('scholarship.law.bu.edu'), 'fordham': DC('ir.lawnet.fordham.edu'), 'minnesota': DC('scholarship.law.umn.edu'),
    'wm': DC('scholarship.law.wm.edu'), 'notredame': DC('scholarship.law.nd.edu'), 'vanderbilt': DC('scholarship.law.vanderbilt.edu'),
    'cardozo': DC('larc.cardozo.yu.edu'), 'maryland': DC('digitalcommons.law.umaryland.edu'), 'emory': DC('scholarlycommons.law.emory.edu'),
    'indiana': DC('www.repository.law.indiana.edu'), 'georgia': DC('digitalcommons.law.uga.edu'), 'florida': DC('scholarship.law.ufl.edu'),
    'casewestern': DC('scholarlycommons.law.case.edu'), 'uclawsf': DC('repository.uclawsf.edu'),
    'dickinson': DC('insight.dickinsonlaw.psu.edu'), 'missouri': DC('scholarship.law.missouri.edu'),
    'wlu': DC('scholarlycommons.law.wlu.edu'), 'brooklyn': DC('brooklynworks.brooklaw.edu'), 'hofstra': DC('scholarlycommons.law.hofstra.edu'),
    'kent': DC('scholarship.kentlaw.iit.edu'), 'villanova': DC('digitalcommons.law.villanova.edu'), 'nyls': DC('digitalcommons.nyls.edu'),
    'buffalo': DC('digitalcommons.law.buffalo.edu'), 'colorado': DC('scholar.law.colorado.edu'), 'unc': DC('scholarship.law.unc.edu'),
    'tennessee': DC('ir.law.utk.edu'), 'lsu': DC('digitalcommons.law.lsu.edu'), 'smu': DC('scholar.smu.edu'),
    'santaclara': DC('digitalcommons.law.scu.edu'), 'american': DC('digitalcommons.wcl.american.edu'), 'catholic': DC('scholarship.law.edu'),
    'uw': DC('digitalcommons.law.uw.edu'), 'oklahoma': DC('digitalcommons.law.ou.edu'), 'byu': DC('digitalcommons.law.byu.edu'),
    'gsu': DC('readingroom.law.gsu.edu'), 'cincinnati': DC('scholarship.law.uc.edu'), 'stjohns': DC('scholarship.law.stjohns.edu'),
    'fsu': DC('ir.law.fsu.edu'), 'miami': DC('repository.law.miami.edu'), 'unlv': DC('scholars.law.unlv.edu'),
    'osgoode': DC('digitalcommons.osgoode.yorku.ca'), 'mitchellhamline': DC('open.mitchellhamline.edu'), 'loyolachicago': DC('lawecommons.luc.edu'),
    'slu': DC('scholarship.law.slu.edu'), 'tamu': DC('scholarship.law.tamu.edu'), 'marquette': DC('scholarship.law.marquette.edu'),
    'seattle': DC('digitalcommons.law.seattleu.edu'), 'utah': DC('dc.law.utah.edu'), 'cwsl': DC('scholarlycommons.law.cwsl.edu'),
    'campbell': DC('scholarship.law.campbell.edu'), 'mercer': DC('digitalcommons.law.mercer.edu'), 'idaho': DC('digitalcommons.law.uidaho.edu'),
    'baltimore': DC('scholarworks.law.ubalt.edu'), 'maine': DC('digitalcommons.mainelaw.maine.edu'), 'touro': DC('digitalcommons.tourolaw.edu'),
    'ualr': DC('lawrepository.ualr.edu'), 'uic': DC('repository.law.uic.edu'),
    # repositories shared with the rest of the university: law sets only
    'kentucky': DC('uknowledge.uky.edu', 'law'), 'wvu': DC('researchrepository.wvu.edu', 'law'),
    'csu': DC('engagedscholarship.csuohio.edu', 'law'), 'akron': DC('ideaexchange.uakron.edu', 'law'),
    'pace': DC('digitalcommons.pace.edu', 'law'), 'chapman': DC('digitalcommons.chapman.edu', 'law'),
    'lmu': DC('digitalcommons.lmu.edu', 'law'), 'sandiego': DC('digital.sandiego.edu', 'law'),
    'pacific': DC('scholarlycommons.pacific.edu', 'law'), 'richmond': DC('scholarship.richmond.edu', 'law'),
    'setonhall': DC('scholarship.shu.edu', 'law'), 'depaul': DC('via.library.depaul.edu', 'law'),
    'washu': DC('repository.library.washu.edu', 'law'), 'stmarys': DC('commons.stmarytx.edu', 'law'),
    'wne': DC('digitalcommons.wne.edu', 'law'), 'montana': DC('scholarworks.umt.edu', 'law'),
    # Yale: faculty scholarship, other scholarship and journals communities
    'yale': ('dspace', 'https://openyls.law.yale.edu/server/oai/request',
             ['com_20.500.13051_35', 'com_20.500.13051_37', 'com_20.500.13051_1']),
    # Harvard DASH (DSpace 7): Harvard Law School sets
    'harvard': ('dspace', 'https://dash.harvard.edu/server/oai/request', 'law'),
    'berkeley': ('invenio', 'https://lawcat.berkeley.edu/oai2d', ['ir']),
    # Penn Carey Law (Quartex, no OAI-PMH): public sitemap of documents by title slug; a document page is fetched only when its
    # slug matches one of our titles, and its meta description gives authors and citation. Links the document page.
    'penn': ('quartex', 'https://repository.law.upenn.edu', None),
}
FORMATS = {'dc': ['oai_dc', 'qualified-dublin-core'], 'dspace': ['dim', 'ore'], 'invenio': ['marcxml']}
# hosts that serve a repository's files under another name
FILE_HOSTS = {'yale': {'openyls.law.yale.edu', 'yls.dspace7.openrepository.com'}, 'harvard': {'dash.harvard.edu'}}

# citation forms of the journals still missing free copies, normalized as cnorm() does
ALIASES = {
    'hlr': ['harv l rev', 'harvard l rev', 'harvard law review', 'harv law rev'],
    'colr': ['colum l rev', 'columbia l rev', 'columbia law review', 'colum law rev'],
    'valr': ['va l rev', 'virginia l rev', 'virginia law review', 'va law rev'],
    'ylj': ['yale lj', 'yale l j', 'yale law journal', 'yale law j'],
    'pennlr': ['u pa l rev', 'univ pa l rev', 'u penn l rev', 'university of pennsylvania law review', 'u of pa l rev',
               'pennsylvania law review', 'u pa law rev'],
    'nyulr': ['nyu l rev', 'n y u l rev', 'ny u l rev', 'new york university law review', 'nyul rev', 'nyu law review',
              'nyu law rev'],
    'slr': ['stan l rev', 'stanford l rev', 'stanford law review', 'stan law rev'],
    'calr': ['calif l rev', 'cal l rev', 'california law review', 'california l rev', 'calif law rev'],
    'uclalr': ['ucla l rev', 'ucla law review', 'ucla law rev'],
    'scr': ['sup ct rev', 'supreme court review', 's ct rev', 'sup ct review'],
    'tlr': ['tex l rev', 'texas law review', 'texas l rev', 'tex law rev'],
    'glj': ['geo lj', 'geo l j', 'georgetown law journal', 'georgetown lj'],
    'ndlr': ['notre dame l rev', 'notre dame law review'],
    'utahlr': ['utah l rev', 'utah law review'],
    'illlr': ['u ill l rev', 'university of illinois law review'],
    'uwlr': ['wash l rev', 'washington law review'],
    'jclc': ['j crim l and criminology', 'journal of criminal law and criminology', 'j crim l criminology'],
    'smulr': ['smu l rev', 'smu law review'],
    'hjlpp': ['harv jl and pub pol', 'harv j l and pub pol', 'harvard journal of law and public policy', 'harv jl and pub poly'],
    'vlr': ['vand l rev', 'vanderbilt law review'],
    'mlr_mich': ['mich l rev', 'michigan law review'],
    'flr': ['fordham l rev', 'fordham law review'],
    'uclrev': ['u chi l rev', 'university of chicago law review', 'u chicago l rev'],
    'wmborj': ['wm and mary bill rts j', 'william and mary bill of rights journal', 'wm and mary bill of rts j'],
    'lcp': ['law and contemp probs', 'law and contemporary problems', 'law and contemp prob'],
}
ALIAS = {al: j for j, als in ALIASES.items() for al in als}

_last = {}
_lock = threading.Lock()


# ---------------------------------------------------------------- harvest

def fetch(url, host):
    """GET with one request a second per host; retries on errors and honours Retry-After (up to 20 minutes)."""
    for t in range(6):
        with _lock:
            wait = _last.get(host, 0) + 1.0 - time.time()
            _last[host] = max(time.time(), _last.get(host, 0) + 1.0)
        if wait > 0:
            time.sleep(wait)
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                ra = e.headers.get('Retry-After') or ''
                time.sleep(min(int(ra) if ra.isdigit() else 30 * (t + 1), 1200))
                continue
            if e.code in (404, 403, 401, 410):
                raise
            time.sleep(10 * (t + 1))
        except Exception:
            time.sleep(10 * (t + 1))
    raise IOError('gave up on ' + url)


def local(tag):
    return tag.rsplit('}', 1)[-1]


def oai_error(text):
    m = re.search(r'<error code="([^"]+)"[^>]*>([^<]*)', text)
    return m and (m.group(1), m.group(2))


def token_of(text):
    m = re.search(r'<resumptionToken[^>]*>([^<]+)</resumptionToken>', text)
    return html.unescape(m.group(1).strip()) if m else None


def law_sets(base, host, kind):
    sets, tok = [], None
    while True:
        q = {'verb': 'ListSets'} if not tok else {'verb': 'ListSets', 'resumptionToken': tok}
        text = fetch(base + '?' + urllib.parse.urlencode(q), host)
        for spec, name in re.findall(r'<setSpec>([^<]*)</setSpec>\s*<setName>([^<]*)</setName>', text):
            name = html.unescape(name)
            if kind == 'dc' and not spec.startswith('publication:'):
                continue
            if re.search(r'\blaw\b|_law|law_|lawreview|lawfac', spec + ' ' + name, re.I) and not re.search(r'student|thesis|theses|dissert|etd|news|magazine|event|honors', spec + ' ' + name, re.I):
                sets.append(spec)
        tok = token_of(text)
        if not tok:
            return sets


def harvest_penn(key):
    kind, base, _ = REPOS[key]
    host = urllib.parse.urlparse(base).netloc
    d = os.path.join(CACHE, key)
    os.makedirs(d, exist_ok=True)

    def cached(name, url):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            open(p, 'w', encoding='utf-8').write(fetch(url, host))
        return open(p, encoding='utf-8').read()
    try:
        idx = cached('sitemap.xml', base + '/sitemap.xml')
        docs = []
        for k, loc in enumerate(re.findall(r'<loc>([^<]*type=DOCUMENT[^<]*)</loc>', idx)):
            docs += re.findall(r'<loc>(' + re.escape(base) + r'/Documents/Detail/([^/<]+)/(\d+))</loc>', cached(f'sitemap-{k}.xml', html.unescape(loc)))
        by = {}
        for url, slug, num in docs:
            by.setdefault(norm(slug.replace('-', ' ')), []).append((url, num))
        _, data = load()
        todo = set()
        for a in data['articles']:
            if a.get('oa') or a.get('pdf') or a.get('pub') or a.get('rv'):
                continue
            n = norm(a['t'])
            hits = by.get(n, [])
            if not hits and len(n) > 30:
                hits = [h for k2, hs in by.items() if min(len(k2), len(n)) > 30 and (k2.startswith(n) or n.startswith(k2)) for h in hs]
            todo.update(hits[:8])
        urls = {}
        for url, num in sorted(todo):
            cached(f'page-{num}.html', url)
            urls[num] = url
        json.dump(urls, open(os.path.join(d, 'urls.json'), 'w', encoding='utf-8'), indent=0)
        open(os.path.join(d, '.done'), 'w').close()
        return key, f'harvested ({len(docs)} documents in the sitemap, {len(todo)} pages checked)'
    except Exception as e:
        return key, f'FAILED: {e}'


def parse_penn(key):
    d = os.path.join(CACHE, key)
    urls = json.load(open(os.path.join(d, 'urls.json'), encoding='utf-8'))
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.startswith('page-') or fn[5:-5] not in urls:
            continue
        s = open(os.path.join(d, fn), encoding='utf-8').read()
        if 'This document contains no images' in s:          # a citation record without the text
            continue
        m = re.search(r'<meta name="description" content="([^"]*)"', s)
        u = re.match(r'(.*)', urls[fn[5:-5]])
        t = re.search(r'<title>(.*?) - Intellectual Life @ PCL</title>', s, re.S)
        if not (m and t and u):
            continue
        title, desc = html.unescape(t.group(1)).strip(), html.unescape(m.group(1))
        rest = desc[len(title):].lstrip(', ') if desc.startswith(title) else desc
        authors = []
        for part in rest.split(', '):
            if re.fullmatch(r'Article|Essay|Book Review|Review|Chapter|Book|Comment|Note|Lecture|Other|Speech|Response|Reply|Symposium', part.strip()):
                break
            authors.append(part.strip())
        out.append({'id': fn, 'title': title, 'authors': authors[:8], 'cites': [desc], 'year': year_of([desc]),
                    'file': html.unescape(u.group(1)), 'page': html.unescape(u.group(1))})
    json.dump(out, open(os.path.join(CACHE, key + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    return len(out), len(out)


def harvest_one(key):
    kind, base, sets = REPOS[key]
    if kind == 'quartex':
        return harvest_penn(key)
    host = urllib.parse.urlparse(base).netloc
    d = os.path.join(CACHE, key)
    os.makedirs(d, exist_ok=True)
    if os.path.exists(os.path.join(d, '.done')):
        return key, 'cached'
    try:
        if sets == 'law':
            sp = os.path.join(d, 'sets.json')
            if os.path.exists(sp):
                sets = json.load(open(sp, encoding='utf-8'))
            else:
                sets = law_sets(base, host, kind)
                json.dump(sets, open(sp, 'w', encoding='utf-8'))
            if not sets:
                return key, 'no law sets'
        total, skipped = 0, []
        for fmt in FORMATS[kind]:
            for s in (sets or [None]):
                slug = fmt + ('-' + re.sub(r'[^A-Za-z0-9_.-]', '_', s) if s else '')
                if os.path.exists(os.path.join(d, slug + '.done')):
                    continue
                n, tok = 0, None
                while os.path.exists(os.path.join(d, f'{slug}-{n:05d}.xml')):     # resume after the last cached page
                    tok = token_of(open(os.path.join(d, f'{slug}-{n:05d}.xml'), encoding='utf-8').read())
                    n += 1
                if n and not tok:
                    open(os.path.join(d, slug + '.done'), 'w').close()
                    continue
                try:
                    while True:
                        q = {'verb': 'ListRecords', 'resumptionToken': tok} if tok else \
                            dict({'verb': 'ListRecords', 'metadataPrefix': fmt}, **({'set': s} if s else {}))
                        text = fetch(base + '?' + urllib.parse.urlencode(q), host)
                        err = oai_error(text)
                        if err and err[0] == 'noRecordsMatch':
                            break
                        if err and err[0] == 'badResumptionToken' and n:       # expired token: start this list again
                            for f in os.listdir(d):
                                if f.startswith(slug + '-'):
                                    os.remove(os.path.join(d, f))
                            n, tok = 0, None
                            continue
                        if err:
                            raise IOError(f'OAI error {err[0]}: {err[1]} ({fmt} {s or ""})')
                        open(os.path.join(d, f'{slug}-{n:05d}.xml'), 'w', encoding='utf-8').write(text)
                        n += 1
                        total += text.count('<record>') + text.count('<record ')
                        tok = token_of(text)
                        if n % 25 == 0:
                            print(f'  {key} {slug}: {n} pages', flush=True)
                        if not tok:
                            break
                except Exception as e:
                    if not s:
                        raise
                    skipped.append(f'{fmt} {s}')         # one broken set (HTTP 500, dead token) does not sink the repository
                    print(f'  {key}: skipped set {s} ({fmt}): {e}', flush=True)
                    continue
                open(os.path.join(d, slug + '.done'), 'w').close()
        open(os.path.join(d, '.done'), 'w').close()
        return key, f'harvested ({total} records this run)' + (f'; skipped sets: {", ".join(skipped)}' if skipped else '')
    except Exception as e:
        return key, f'FAILED: {e}'


# ---------------------------------------------------------------- parse

def records_in(path):
    """(identifier, deleted, {field: [values]}) for each record in a cached page; field names are local tag names, with
    dim fields as element.qualifier and MARC as tag+code, e.g. 773j."""
    text = open(path, encoding='utf-8').read()
    try:
        root = ET.fromstring(text.encode('utf-8'))
    except ET.ParseError:
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        text = re.sub(r'<(/?)dc:(\d)', r'<\1dc:n\2', text)          # Kentucky's qualified DC has tags such as <dc:1>
        try:
            root = ET.fromstring(text.encode('utf-8'))
        except ET.ParseError:
            print('  unreadable page', path)
            return
    for rec in root.iter():
        if local(rec.tag) != 'record' or rec.find('./{*}header') is None:
            continue
        h = rec.find('./{*}header')
        ident = (h.findtext('./{*}identifier') or '').strip()
        if h.get('status') == 'deleted':
            yield ident, True, {}
            continue
        f = {}
        md = rec.find('./{*}metadata')
        for el in (md.iter() if md is not None else []):
            tag = local(el.tag)
            if tag == 'field':           # DSpace dim
                k = el.get('element', '') + ('.' + el.get('qualifier') if el.get('qualifier') else '')
                f.setdefault(k, []).append((el.text or '').strip())
            elif tag == 'datafield':     # MARC
                for sf in el:
                    f.setdefault(el.get('tag', '') + sf.get('code', ''), []).append((sf.text or '').strip())
            elif tag == 'link' and el.get('href'):          # ORE atom links
                if (el.get('rel') or '').endswith('aggregates'):
                    f.setdefault('ore_file', []).append((el.get('href'), el.get('type') or '', el.get('title') or ''))
            elif len(el) == 0 and (el.text or '').strip():
                f.setdefault(tag, []).append(el.text.strip())
        if md is not None and 'open.access' in ''.join(md.itertext()):
            f['open_access'] = [1]
        yield ident, False, f


def year_of(vals):
    for v in vals or []:
        m = re.search(r'\b(1[89]\d\d|20\d\d)\b', str(v))
        if m:
            return int(m.group(1))
    return None


def parse_repo(key):
    kind, base, _ = REPOS[key]
    if kind == 'quartex':
        return parse_penn(key)
    d = os.path.join(CACHE, key)
    host = urllib.parse.urlparse(base).netloc
    hosts = FILE_HOSTS.get(key, set()) | {host, host.removeprefix('www.')}
    recs = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.xml'):
            continue
        fmt = fn.split('-')[0] if not fn.startswith('qualified-dublin-core') else 'qualified-dublin-core'
        for ident, deleted, f in records_in(os.path.join(d, fn)):
            r = recs.setdefault(ident, {'id': ident})
            if deleted:
                r['deleted'] = True
                continue
            if fmt == 'oai_dc':
                r['title'] = (f.get('title') or [''])[0]
                r['authors'] = f.get('creator', [])
                r['year'] = r.get('year') or year_of(f.get('date'))
                for u in f.get('identifier', []):
                    uh = urllib.parse.urlparse(u).netloc.lower()
                    if uh in hosts and ('viewcontent.cgi' in u or '/viewcontent/' in u):
                        r['file'] = u
                    elif uh in hosts and not r.get('page'):
                        r['page'] = u
                r.setdefault('cites', []).extend(f.get('source', []) + f.get('description', [])[:3])
                r.setdefault('types', []).extend(f.get('type', []))
            elif fmt == 'qualified-dublin-core':
                r['qsource'] = f.get('source', [])
                r['year'] = year_of(f.get('date.created')) or r.get('year')
                r.setdefault('cites', []).extend(v for k, vs in f.items() if 'citation' in k.lower() for v in vs)
                r.setdefault('types', []).extend(f.get('type', []))
                r['title'] = r.get('title') or (f.get('title') or [''])[0]
                r['authors'] = r.get('authors') or f.get('creator', [])
            elif fmt == 'dim':
                r['title'] = (f.get('title') or [''])[0]
                r['authors'] = f.get('contributor.author', []) or f.get('creator', [])
                r['year'] = year_of(f.get('date.issued'))
                r['cites'] = f.get('identifier.citation', []) + f.get('source.journaltitle', []) + f.get('relation.ispartof', []) \
                    + f.get('identifier.bibliographicCitation', [])
                r['open'] = bool(f.get('open_access'))
                r['version'] = ' '.join(f.get('version', []) + f.get('type.version', []) + f.get('description.version', []))
                r['types'] = f.get('type', [])
                r['page'] = next((u for u in f.get('identifier.uri', []) if 'hdl.handle.net' in u), None)
            elif fmt == 'ore':
                for href, typ, name in f.get('ore_file', []):
                    if typ == 'application/pdf' and urllib.parse.urlparse(href).netloc in hosts and not r.get('file'):
                        r['file'] = href.replace('yls.dspace7.openrepository.com', 'openyls.law.yale.edu')
            elif fmt == 'marcxml':
                r['title'] = ' '.join((f.get('245a') or [''])[:1] + (f.get('245b') or [])[:1]).strip()
                r['authors'] = f.get('100a', []) + f.get('700a', [])
                r['year'] = year_of(f.get('264c', []) + f.get('269a', []) + f.get('260c', []))
                j = (f.get('773p') or f.get('773t') or [''])[0]
                vol = (f.get('773j') or f.get('773v') or [''])[0]
                pg = (f.get('773g') or f.get('773c') or [''])[0]
                r['cites'] = [f'{vol} {j} {pg}'] + f.get('773t', []) + f.get('500a', []) + f.get('524a', [])
                r['jvp'] = [j, vol, pg]
                r['types'] = f.get('655a', [])
                for u in f.get('856u', []):
                    if urllib.parse.urlparse(u).netloc in hosts and '/files/' in u and u.lower().endswith('.pdf'):
                        r['file'] = r.get('file') or u
    out = [r for r in recs.values() if not r.get('deleted') and r.get('title')]
    if kind == 'dspace':
        for r in out:          # DSpace: a file counts only when the record is open access
            if not r.get('open'):
                r.pop('file', None)
    json.dump(out, open(os.path.join(CACHE, key + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    return len(out), sum(1 for r in out if r.get('file'))


def harvest(keys):
    keys = keys or list(REPOS)
    bad = [k for k in keys if k not in REPOS]
    if bad:
        sys.exit('unknown repositories: ' + ', '.join(bad))
    os.makedirs(CACHE, exist_ok=True)
    status = {}
    sp = os.path.join(CACHE, 'status.json')
    if os.path.exists(sp):
        status = json.load(open(sp, encoding='utf-8'))
    with ThreadPoolExecutor(16) as ex:
        for key, st in ex.map(harvest_one, keys):
            if os.path.exists(os.path.join(CACHE, key, '.done')):
                n, nf = parse_repo(key)
                st += f'; {n} records, {nf} with full text'
            status[key] = st
            print(f'{key}: {st}', flush=True)
            json.dump(status, open(sp, 'w', encoding='utf-8'), indent=1)


# ---------------------------------------------------------------- apply

def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', html.unescape(s or '')) if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def surname(name):
    """Surname from 'Last, First' (repository style) or 'First Last' (ours)."""
    name = html.unescape(name or '')
    if ',' in name:
        parts = [p for p in name.split(',') if norm(p) not in ('jr', 'sr', 'ii', 'iii', 'iv', '')]
        return norm(parts[0]).split()[-1] if parts and norm(parts[0]) else ''
    parts = [p for p in norm(name).split() if p not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return parts[-1] if parts else ''


def cnorm(s):
    s = html.unescape(s or '').replace('&', ' and ').replace('_', ' ')
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’,:;()\[\]]", ' ', s)
    s = re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def cites_of(r):
    """{(journal id, volume or None, first page or None)} from the record's citation strings, file name and sources."""
    out = set()
    texts = list(r.get('cites') or []) + list(r.get('qsource') or [])
    if r.get('file'):
        texts.append(urllib.parse.unquote(r['file'].rsplit('/', 1)[-1]).rsplit('.', 1)[0])
    for t in texts:
        c = cnorm(t)
        for vol, mid, pg in re.findall(r'(?<![a-z0-9])(\d{1,4}) ((?:[a-z]+ ){0,9}?[a-z]+) (\d{1,5})(?![0-9])', c):
            mid = re.sub(r'^the ', '', mid)
            mid = re.sub(r' (no|number|iss|issue|vol|p|pp|at)$', '', mid)
            if mid in ALIAS:
                out.add((ALIAS[mid], int(vol), int(pg)))
        # "Harvard Law Review, vol. 115, no. 3, p. 1234"
        m = re.search(r'\bvol(?:ume)? (\d{1,3})\b', c)
        if m:
            for al, j in ALIAS.items():
                if len(al) > 8 and al in c and re.search(r'(?<![a-z])' + al + r'(?![a-z])', c):
                    p = re.search(r'\b(?:p|pp|page|pages) (\d{1,5})\b', c)
                    out.add((j, int(m.group(1)), int(p.group(1)) if p else None))
        # Yale-style file names: 31YaleLJ229
        for vol, ab, pg in re.findall(r'(\d{1,3})(YaleLJ|HarvLRev|ColumLRev|StanLRev|VaLRev|UPaLRev|CalifLRev|TexLRev|SupCtRev)(\d{1,4})', t):
            j = {'YaleLJ': 'ylj', 'HarvLRev': 'hlr', 'ColumLRev': 'colr', 'StanLRev': 'slr', 'VaLRev': 'valr', 'UPaLRev': 'pennlr',
                 'CalifLRev': 'calr', 'TexLRev': 'tlr', 'SupCtRev': 'scr'}[ab]
            out.add((j, int(vol), int(pg)))
    # Digital Commons qualified DC: one dc:source is the journal, another the first page (no volume)
    qs = [cnorm(x) for x in r.get('qsource') or []]
    js = [ALIAS[re.sub(r'^the ', '', x)] for x in qs if re.sub(r'^the ', '', x) in ALIAS]
    pgs = [int(x) for x in qs if re.fullmatch(r'\d{1,5}', x)]
    for j in js:
        for p in pgs or [None]:
            out.add((j, None, p))
    if r.get('jvp'):
        j, vol, pg = (cnorm(x) for x in r['jvp'])
        j = re.sub(r'^the ', '', j)
        if j in ALIAS and vol.isdigit():
            out.add((ALIAS[j], int(vol), int(re.match(r'\d+', pg).group()) if re.match(r'\d+', pg) else None))
    return out


def words(s):
    return set(w for w in norm(s).split() if len(w) > 2 and w not in ('the', 'and', 'for', 'from', 'with', 'essay', 'article'))


def match(a, r, cites):
    """'citation' / 'title' / None."""
    au = {surname(x) for x in a.get('a') or []} - {''}
    ru = {surname(x) for x in r.get('authors') or []} - {''}
    author = bool(au & ru)
    yr = r.get('year')
    near = yr is not None and a.get('y') and abs(yr - a['y']) <= 1
    fp = a.get('fp')
    mine = [c for c in cites if c[0] == a['j']]
    for j, vol, pg in mine:
        if vol is not None and vol == a.get('v'):
            if pg is not None and fp:
                if pg == fp:
                    return 'citation'
                continue
            aw, rw = words(a['t']), words(r.get('title'))
            if author and aw and len(aw & rw) >= 0.6 * max(len(aw), len(rw)):
                return 'citation'
        elif vol is None and pg is not None and fp and pg == fp and near and author:
            return 'citation'
    conflict = any((vol is not None and a.get('v') and vol != a['v']) or (pg is not None and fp and pg != fp) for j, vol, pg in mine)
    if not conflict and norm(r.get('title')) == norm(a['t']) and len(norm(a['t'])) > 8 and author and near:
        return 'title'
    return None


def version_of(r):
    t = ' '.join([r.get('version') or ''] + list(r.get('types') or [])).lower()
    if re.search(r'preprint|working paper|submitted', t):
        return ''
    if re.search(r'accepted', t):
        return 'acceptedVersion'
    return 'publishedVersion'


def load():
    raw = open(ART, encoding='utf-8').read()
    return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def apply(dry):
    raw, data = load()
    arts = data['articles']
    cand = [a for a in arts if not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv')]
    by_title, by_cite = {}, {}
    nrec = 0
    for key in REPOS:
        p = os.path.join(CACHE, key + '.json')
        if not os.path.exists(p):
            continue
        for r in json.load(open(p, encoding='utf-8')):
            if not r.get('file'):
                continue
            nrec += 1
            r['repo'] = key
            cs = cites_of(r)
            r['_cites'] = cs
            by_title.setdefault(norm(r['title']), []).append(r)
            for j, vol, pg in cs:
                by_cite.setdefault((j, vol), []).append(r)
                by_cite.setdefault((j, None), []).append(r)
    found = {}
    order = {k: i for i, k in enumerate(REPOS)}
    for a in cand:
        pool = {id(r): r for r in by_title.get(norm(a['t']), []) + by_cite.get((a['j'], a.get('v')), []) + by_cite.get((a['j'], None), [])}
        best = None
        for r in pool.values():
            if r['repo'] == 'penn' and a['j'] == 'pennlr':      # Penn Law Review itself is archive_copies.py's (stricter) job
                continue
            how = match(a, r, r['_cites'])
            if how:
                rank = (how != 'citation', order[r['repo']])
                if not best or rank < best[0]:
                    best = (rank, how, r)
        if best:
            _, how, r = best
            found[a['id']] = {'url': r['file'], 'version': version_of(r), 'repo': r['repo'], 'via': how,
                              'title': r['title'], 'rec': r['id'], 'page': r.get('page')}
    json.dump(found, open(os.path.join(CACHE, 'matches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ids = {a['id']: a for a in arts}
    per_j, per_r, per_via = {}, {}, {}
    for aid, f in found.items():
        j = ids[aid]['j']
        per_j[j] = per_j.get(j, 0) + 1
        per_r[f['repo']] = per_r.get(f['repo'], 0) + 1
        per_via[f['via']] = per_via.get(f['via'], 0) + 1
    print(f'{nrec} repository records with full text; {len(cand)} articles without a free route; {len(found)} matched')
    print('by match rule:', per_via)
    print('by journal:', sorted(per_j.items(), key=lambda x: -x[1]))
    print('by repository:', sorted(per_r.items(), key=lambda x: -x[1]))
    if dry:
        random.seed(7)
        for aid in random.sample(sorted(found), min(15, len(found))):
            a, f = ids[aid], found[aid]
            print(f'\n{aid} [{f["via"]}, {f["repo"]}] {a.get("v")}:{a.get("fp")} ({a.get("y")})\n  ours: {a["t"]}\n  repo: {" ".join(f["title"].split())}\n  {f["url"]}')
        print('\ndry run: articles.js not changed')
        return
    n = 0
    for a in cand:
        f = found.get(a['id'])
        if f:
            a['oa'] = f['url']
            if f['version']:
                a['oav'] = f['version']
            n += 1
    open(ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{n} articles given a free copy')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'harvest':
        harvest(sys.argv[2:])
    elif cmd == 'apply':
        apply('--dry-run' in sys.argv)
    else:
        sys.exit(__doc__)
