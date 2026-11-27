"""Works cited, cases cited and cited-by lists for article pages, read from the articles' own footnotes in the free full texts
the index already links (oa / pdf / pub).

Step 1 (fetch): for each article with a full text a script may download (journal sites' PDFs and HTML pages, Yale's openYLS,
  Berkeley's lawCat, Internet Archive scans; NOT Digital Commons' viewcontent files or HathiTrust, which answer scripts with a
  bot check that is not to be got round), the text is fetched (one request a second per host), read in memory (pdftotext for
  PDFs; Internet Archive: the scan's hOCR text cut to the article's pages), and only the citations found are kept, in
  data/raw/fulltext/<article id>.json. The text itself is never stored. Reruns skip articles already done.
Step 2 (extraction, during fetch):
  - law review citations "<vol> <Journal Abbrev.> <page>": every one counts toward the total (indexed journal or not); those
    to the 44 indexed journals (build_crosslinks.ABBR: Bluebook abbreviations and older names) are matched to an article
    with build_crosslinks.ArticleMatcher (journal + volume + first page; with no first page in the index, journal + volume
    and the article's title in the words just before the citation), never to the citing article itself (running heads);
  - U.S. Reports citations "<vol> U.S. <page>", matched to scotus.js by its `cit`.
Step 3 (build): docs/data/ft/art-<decade>.js -> window.FT_ART[articleId] = {a: [[citedArticleId, count], ...], c: [[caseId,
  count], ...], n: law review citations found, b: [citingArticleId, ...]} (b = cited by, on the cited article's own record,
  so an article page loads one file: its own decade); docs/data/ft/case-<year>.js -> window.FT_CASE[caseId] = [[articleId,
  count], ...]; docs/data/ft-index.js lists the files. Same shapes as build_crosslinks.py's XL_ART / XL_CASE lists.
    python scripts/fulltext_cites.py fetch [N] [--pilot]     # N articles at most (default all); --pilot: a spread sample
    python scripts/fulltext_cites.py check [N]                # print N random results for hand checking
    python scripts/fulltext_cites.py build
"""
import collections, glob, gzip, html, io, json, os, random, re, subprocess, sys, tempfile, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_crosslinks as bc  # noqa: E402

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
ART = 'docs/data/articles.js'
RAW = 'data/raw/fulltext'
OUT = 'docs/data/ft'
TMP = os.path.join(RAW, '_tmp')
BLOCK = re.compile(r'/viewcontent|viewcontent\.cgi|hathitrust|ssrn\.com|doi\.org|jstor\.org|nrs\.harvard|escholarship|'
                   r'dash\.harvard|scholarship\.law\.berkeley|digitalcommons\.law\.yale|pantheonsite|journals\.uchicago|'
                   r'repository\.law\.upenn\.edu|handle\.net')
# record pages that are not full texts (Digital Commons landing pages, faculty pages)
NOT_TEXT = re.compile(r'(scholarship|repository|scholarlycommons|digitalcommons|chicagounbound|dc\.law)\.[^/]+/(?!.*\.pdf)')
LR_ANY = re.compile(r"\b(\d{1,4}) ((?:[A-Z][A-Za-z'&]*\.?\s?){1,8}?(?i:L\.\s?Rev|L\.\s?J|L\.\s?Q|Rev|J|L\.\s?F|Q|Rptr|Comment|Probs?)\.?) (\d{1,5})\b")
US = re.compile(r'\b(\d{1,3}) U\.\s?S\.? (\d{1,4})\b')
SCT = re.compile(r'\b(\d{1,3}) S\.\s?Ct\. (\d{1,5})\b')
_last, _lock = {}, threading.Lock()
_ctx = []


def ssl_ctx():
    """The default trust store plus the intermediate certificate lawCat's server leaves out of its chain (fetched once from
    the address its own certificate names), so verification stays on."""
    if not _ctx:
        import ssl
        ctx = ssl.create_default_context()
        p = os.path.join(RAW, '_intermediate.pem')
        if not os.path.exists(p):
            try:
                der = urllib.request.urlopen(urllib.request.Request('http://crt.sectigo.com/InCommonRSAOVSSLCA3.crt', headers=UA), timeout=60).read()
                os.makedirs(RAW, exist_ok=True)
                open(p, 'w').write(ssl.DER_cert_to_PEM_cert(der))
            except Exception:
                pass
        if os.path.exists(p):
            ctx.load_verify_locations(cafile=p)
        _ctx.append(ctx)
    return _ctx[0]


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def source(a):
    for k in ('pdf', 'pub', 'oa'):
        u = a.get(k)
        if u and u.startswith('http') and not BLOCK.search(u) and not NOT_TEXT.search(u):
            m = re.match(r'https?://web\.archive\.org/web/(\d+)/(.*)', u)
            if m:                                   # the archived file itself, not the Wayback toolbar page
                u = f'https://web.archive.org/web/{m.group(1)}id_/{m.group(2)}'
            return u
    return None


def curl(url):
    """lawCat's chain ends in a root this Python's store lacks; Windows' own TLS (curl/schannel) fetches it, verified."""
    try:
        r = subprocess.run(['curl', '-s', '-L', '-m', '120', '-A', UA['User-Agent'], '-w', '\n%{http_code}', url], capture_output=True, timeout=150)
        body, _, code = r.stdout.rpartition(b'\n')
        return int(code or 0), '', body
    except Exception:
        return 0, '', b''


def fetch(url, binary=True):
    host = urllib.parse.urlparse(url).netloc
    if host.startswith('lawcat.berkeley.edu'):
        with _lock:
            wait = _last.get(host, 0) + 1.0 - time.time()
            _last[host] = max(time.time(), _last.get(host, 0) + 1.0)
        if wait > 0:
            time.sleep(wait)
        return curl(url)
    for t in range(3):
        with _lock:
            wait = _last.get(host, 0) + 1.0 - time.time()
            _last[host] = max(time.time(), _last.get(host, 0) + 1.0)
        if wait > 0:
            time.sleep(wait)
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90, context=ssl_ctx())
            return r.status, r.headers.get('content-type', ''), r.read(60_000_000)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and t < 2:
                time.sleep(20 * (t + 1))
                continue
            return e.code, '', b''
        except Exception:
            if t == 2:
                return 0, '', b''
            time.sleep(5)
    return 0, '', b''


def pdf_text(data):
    os.makedirs(TMP, exist_ok=True)
    fd, p = tempfile.mkstemp(suffix='.pdf', dir=TMP)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        r = subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', p, '-'], capture_output=True, timeout=180)
        return r.stdout.decode('utf-8', 'ignore')
    except Exception:
        return ''
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def html_text(data):
    s = data.decode('utf-8', 'ignore')
    s = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</div>', '\n', s)
    return html.unescape(re.sub(r'<[^>]+>', ' ', s))


def ia_text(url, a, fps):
    """The article's pages of an Internet Archive scan: hOCR search text cut with its page index, pages named by
    page_numbers.json; from the article's first page to the next indexed article's first page (at most 60 pages)."""
    m = re.match(r'https?://archive\.org/details/([^/]+)(?:/page/(\w+))?', url)
    if not m:
        return ''
    ident, start = m.group(1), m.group(2) or str(a.get('fp') or '')
    base = f'https://archive.org/download/{ident}/{ident}'
    st1, _, txt = fetch(base + '_hocr_searchtext.txt.gz')
    st2, _, idx = fetch(base + '_hocr_pageindex.json.gz')
    st3, _, pn = fetch(base + '_page_numbers.json')
    if 200 not in (st1,) or st2 != 200 or st3 != 200:
        return ''
    try:
        txt = gzip.decompress(txt).decode('utf-8', 'ignore')
        idx = json.loads(gzip.decompress(idx))
        pages = {p['leafNum']: p.get('pageNumber') or '' for p in json.loads(pn)['pages']}
    except Exception:
        return ''
    if not start.isdigit():
        return ''
    s = int(start)
    nxt = min([f for f in fps if f > s] + [s + 60])
    out = []
    for leaf, rng in enumerate(idx):
        pg = pages.get(leaf, '')
        if pg.isdigit() and s <= int(pg) < nxt:
            out.append(txt[rng[0]:rng[1]])
    return '\n'.join(out)


def citations(text, a, matcher, cases_by_cit):
    t = re.sub(r'-\s*\n\s*', '', text)                     # words split at line ends
    t = re.sub(r'\s+', ' ', t)
    n_any = sum(1 for _ in LR_ANY.finditer(t))
    arts, raw = collections.Counter(), collections.Counter()
    for j, v, p, at in bc.lr_cites(t):
        raw[(j, v, p)] += 1
        b = matcher.find(j, v, p, t[max(0, at - 320):at], (a.get('y') or 9999) + 1)
        if b and b['id'] != a['id']:
            arts[b['id']] += 1
    cs = collections.Counter()
    for v, p in US.findall(t):
        c = cases_by_cit.get(f'{int(v)} U.S. {int(p)}')
        if c:
            cs[c] += 1
    for v, p in SCT.findall(t):
        c = cases_by_cit.get(f'{int(v)} S. Ct. {int(p)}')
        if c:
            cs[c] += 1
    return {'n': max(n_any, sum(raw.values())), 'a': sorted(arts.items(), key=lambda x: -x[1]),
            'c': sorted(cs.items(), key=lambda x: -x[1]), 'raw': [[j, v, p, k] for (j, v, p), k in raw.items()],
            'chars': len(t)}


def openyls_pdf(url):
    """openYLS handle page (an app page, no text) -> its PDF, through the repository's REST API."""
    m = re.search(r'/(?:handle|bitstream)/(20\.500\.13051/\d+)', url)
    if not m:
        return url
    try:
        st, _, b = fetch('https://openyls.law.yale.edu/server/api/pid/find?id=' + m.group(1))
        item = json.loads(b)
        st, _, b = fetch(item['_links']['bundles']['href'])
        orig = [x for x in json.loads(b)['_embedded']['bundles'] if x['name'] == 'ORIGINAL']
        st, _, b = fetch(orig[0]['_links']['bitstreams']['href'])
        pdfs = [x['_links']['content']['href'] for x in json.loads(b)['_embedded']['bitstreams'] if x['name'].lower().endswith('.pdf')]
        return pdfs[0] if pdfs else url
    except Exception:
        return url


def one(a, matcher, cases_by_cit, fps):
    url = source(a)
    out = {'src': url}
    if re.search(r'openyls\.law\.yale\.edu/(handle|bitstream)/20\.500', url):
        url = openyls_pdf(url)
    if 'archive.org/details/' in url:
        text = ia_text(url, a, fps)
        out['kind'] = 'ia'
    else:
        st, ct, data = fetch(url)
        out['status'] = st
        if st != 200 or not data:
            return out
        if data[:5] == b'%PDF-':
            text, out['kind'] = pdf_text(data), 'pdf'
        elif b'<html' in data[:2000].lower() or 'html' in ct:
            text, out['kind'] = html_text(data), 'html'
        else:
            return out
    if len(text) < (12000 if out.get('kind') == 'html' else 2000):
        out['short'] = len(text)       # an HTML page this short is a landing page (abstract only), not the article
        return out
    out.update(citations(text, a, matcher, cases_by_cit))
    return out


def setup():
    d = load_js(ART)
    arts = d['articles']
    S = load_js('docs/data/scotus.js')
    cases_by_cit = {}
    for c in S['cases']:
        if c.get('cit'):
            cases_by_cit[re.sub(r'\s+', ' ', c['cit'].replace('U. S.', 'U.S.').replace('S.Ct.', 'S. Ct.'))] = c['id']
    fps = collections.defaultdict(list)
    for a in arts:
        if a.get('fp') and a.get('v'):
            fps[(a['j'], a['v'])].append(a['fp'])
    return d, arts, bc.ArticleMatcher(arts), cases_by_cit, fps


def fetch_all(n, pilot):
    d, arts, matcher, cases_by_cit, fps = setup()
    os.makedirs(RAW, exist_ok=True)
    todo = [a for a in arts if source(a) and not os.path.exists(os.path.join(RAW, a['id'] + '.json'))]
    ids = next((x[4:] for x in sys.argv if x.startswith('ids=')), None)
    if ids:                                   # re-read only the articles listed in this file (one id a line)
        want = set(open(ids, encoding='utf-8').read().split())
        todo = [a for a in arts if a['id'] in want and source(a)]
    elif pilot:
        random.seed(13)
        groups = collections.defaultdict(list)
        for a in todo:
            groups[(source(a).split('/')[2], (a.get('y') or 0) // 25)].append(a)
        pick = []
        while len(pick) < (n or 300) and any(groups.values()):
            for k in list(groups):
                if groups[k]:
                    pick.append(groups[k].pop(random.randrange(len(groups[k]))))
        todo = pick[:n or 300]
    elif n:
        todo = todo[:n]
    by = collections.defaultdict(list)
    for a in todo:
        by[urllib.parse.urlparse(source(a)).netloc].append(a)
    print(f'{len(todo)} articles to read on {len(by)} hosts', flush=True)
    done = [0]

    def run(items):
        for a in items:
            try:
                r = one(a, matcher, cases_by_cit, fps.get((a['j'], a.get('v')), []))
            except Exception as e:
                r = {'src': source(a), 'error': str(e)[:200]}
            json.dump(r, open(os.path.join(RAW, a['id'] + '.json'), 'w', encoding='utf-8'))
            done[0] += 1
            if done[0] % 100 == 0:
                print(f'  {done[0]}/{len(todo)}', flush=True)
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(run, by.values()))


def results():
    out = {}
    for f in glob.glob(os.path.join(RAW, '*.json')):
        try:
            out[os.path.basename(f)[:-5]] = json.load(open(f, encoding='utf-8'))
        except Exception:
            pass
    return out


def check(n):
    d = load_js(ART)
    by_id = {a['id']: a for a in d['articles']}
    S = load_js('docs/data/scotus.js')
    case_n = {c['id']: c['n'] for c in S['cases']}
    R = results()
    ok = [k for k, r in R.items() if 'n' in r]
    print(f'{len(R)} read; {len(ok)} with text; kinds {collections.Counter(r.get("kind") for r in R.values())}; '
          f'failures {collections.Counter(r.get("status") for r in R.values() if "n" not in r)}')
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    for k in random.sample(ok, min(n, len(ok))):
        r, a = R[k], by_id.get(k, {})
        print(f"\n{k} ({a.get('y')}) {a.get('t', '')[:80]}\n  {r['src']}\n  LR cites {r['n']}, indexed-journal cites {sum(x[3] for x in r['raw'])}, matched {len(r['a'])}, cases {len(r['c'])}")
        for bid, c in r['a'][:6]:
            b = by_id.get(bid, {})
            print(f"    -> {bid} x{c}: {b.get('t', '')[:70]} ({b.get('j')} {b.get('v')}:{b.get('fp')}, {b.get('y')})")
        print('    cases: ' + '; '.join(f'{case_n.get(c, c)[:30]} x{k2}' for c, k2 in r['c'][:6]))


def build():
    d = load_js(ART)
    by_id = {a['id']: a for a in d['articles']}
    S = load_js('docs/data/scotus.js')
    cyear = {c['id']: str(c.get('y') or (c.get('dec') or '0000')[:4]) for c in S['cases']}
    R = results()
    fa = collections.defaultdict(dict)
    fc = collections.defaultdict(list)
    for aid, r in R.items():
        if 'n' not in r or aid not in by_id or (r.get('kind') == 'html' and r.get('chars', 0) < 12000):
            continue
        rec = {'n': r['n']}
        a_links = [[b, k] for b, k in r['a'] if b in by_id and b != aid]
        if a_links:
            rec['a'] = a_links
        if r['c']:
            rec['c'] = [[c, k] for c, k in r['c']]
        fa[aid].update(rec)
        for b, k in a_links:
            fa[b].setdefault('b', []).append(aid)
        for c, k in r['c']:
            fc[c].append([aid, k])
    for b, rec in fa.items():
        if 'b' in rec:
            rec['b'].sort(key=lambda x: -(by_id[x].get('y') or 0))
    for c in fc:
        fc[c].sort(key=lambda x: (-x[1], -(by_id[x[0]].get('c') or 0)))
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(os.path.join(OUT, '*.js')):
        os.remove(f)
    files = {'art': collections.defaultdict(dict), 'case': collections.defaultdict(dict)}
    for aid, rec in fa.items():
        files['art'][str((by_id[aid].get('y') or 0) // 10 * 10)][aid] = rec
    for c, lst in fc.items():
        files['case'][cyear.get(c, '0')][c] = lst
    size = {}
    for kind, var in (('art', 'FT_ART'), ('case', 'FT_CASE')):
        for k, recs in files[kind].items():
            s = f'window.{var}=window.{var}||{{}};Object.assign(window.{var},' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');'
            open(os.path.join(OUT, f'{kind}-{k}.js'), 'w', encoding='utf-8').write(s)
            size[f'{kind}-{k}'] = len(s.encode('utf-8'))
    open('docs/data/ft-index.js', 'w', encoding='utf-8').write('window.FT_INDEX=' + json.dumps({k: sorted(v) for k, v in files.items()}) + ';')
    read = [r for r in R.values() if 'n' in r and not (r.get('kind') == 'html' and r.get('chars', 0) < 12000)]
    print(f'{len(R)} articles tried, {len(read)} full texts read')
    print(f'articles with a works-cited list (indexed articles): {sum(1 for r in fa.values() if r.get("a"))}; '
          f'with cases cited: {sum(1 for r in fa.values() if r.get("c"))}')
    print(f'article->article links: {sum(len(r.get("a", [])) for r in fa.values())}; cited-by: {sum(1 for r in fa.values() if r.get("b"))} articles cited; '
          f'article->case links: {sum(len(r.get("c", [])) for r in fa.values())} to {len(fc)} cases; law review citations counted: {sum(r["n"] for r in read)}')
    print(f'{len(size)} files, {sum(size.values()) / 1e6:.2f} MB, largest {max(size.values()) / 1e3:.0f} KB ({max(size, key=size.get)})' if size else 'no files')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    num = next((int(x) for x in sys.argv[2:] if x.isdigit()), 0)
    if cmd == 'fetch':
        fetch_all(num, '--pilot' in sys.argv)
    elif cmd == 'check':
        check(num or 20)
    elif cmd == 'build':
        build()
    else:
        print(__doc__)
