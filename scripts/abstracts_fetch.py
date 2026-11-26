"""Find abstracts and citation counts the article index lacks. Lookup and apply are separate steps.

  python scripts/abstracts_fetch.py lookup [--stage oa|crossref|landing|coci|all] [--limit N]
  python scripts/abstracts_fetch.py apply [--dry-run]
  python scripts/abstracts_fetch.py stats

Targets (read from docs/data/articles.js; `lookup` never writes it): articles with no abstract or one that ends in a cut-off
ellipsis, and articles with no citation count (`c`). Book reviews (`rv`/`cx`) are skipped for counts, as in refresh_cites.py.

Stages, each cached under data/raw/abstracts/ (resumable; re-run to continue):
  oa        OpenAlex, 50 DOIs a request (filter=doi:a|b|c, select=doi,cited_by_count,abstract_inverted_index): abstract
            (CC0) rebuilt from the inverted index, and the count. Uses OPENALEX_KEY if set; unkeyed it costs about 1 credit a request.
  crossref  Crossref REST API (CC0 metadata; polite pool via mailto). DOI articles still without an abstract: /works/{doi}.
            Articles without a DOI: query.bibliographic on title + first author, accepted only when the title matches, the
            year is within 2 and a surname is shared (the rule refresh_cites.py uses). Gives the DOI, the deposited abstract
            (if any) and is-referenced-by-count.
  landing   the article's own landing page: citation_abstract / DC.description / og:description / description meta, kept only
            when it reads like an abstract (long enough, not the title or site boilerplate). Polite: one request a second per host.
  coci      OpenCitations COCI citation counts (CC0) for DOI articles with no count after oa and crossref.
`apply` writes articles.js: `ab` is set where missing or cut off (never replacing a longer existing abstract), `c` where
a count was found and the article has none (an existing count is replaced only by a larger one from OpenAlex; Crossref and
COCI counts are lower bounds and only fill gaps). Run it when no other session is writing articles.js, then fix_text.py.
"""
import collections, datetime, html, json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from refresh_cites import norm, main_title, surnames   # same title-matching rules as the citation refresh

ART = 'docs/data/articles.js'
OUT = 'data/raw/abstracts'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build; mailto:lexconstitutio@users.noreply.github.com)'}
MAILTO = 'lexconstitutio@users.noreply.github.com'
KEY = os.environ.get('OPENALEX_KEY', '')
TODAY = datetime.date.today().isoformat()
lock = threading.Lock()


def load_articles():
    raw = open(ART, encoding='utf-8').read()
    return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def doi_of(a):
    u = a.get('u') or ''
    return u.split('doi.org/', 1)[1].lower() if 'doi.org/' in u else None


def cut_off(ab):
    return bool(ab) and ab.rstrip().endswith('…')


def need_ab(a):
    return not a.get('ab') or cut_off(a.get('ab'))


def need_c(a):
    return a.get('c') is None and not (a.get('rv') or a.get('cx'))


def cache_load(name):
    p = f'{OUT}/{name}.json'
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def cache_save(name, d):
    os.makedirs(OUT, exist_ok=True)
    with lock:
        json.dump(d, open(f'{OUT}/{name}.json.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(f'{OUT}/{name}.json.tmp', f'{OUT}/{name}.json')


def get(url, timeout=40, tries=4, as_json=True):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                body = r.read()
                return json.loads(body) if as_json else body.decode(r.headers.get_content_charset() or 'utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            if e.code == 429:
                time.sleep(float(e.headers.get('Retry-After') or 5 * (n + 1)))
            elif e.code in (401, 403):
                return None
            else:
                time.sleep(3 * (n + 1))
        except Exception:
            time.sleep(3 * (n + 1))
    return None


def clean_abstract(s):
    s = html.unescape(re.sub(r'<[^>]+>', ' ', html.unescape(s or '')))   # some feeds double-escape their markup
    s = re.sub(r'^\s*(abstract|summary)\s*[:.\-–—]?\s*', '', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()


def plausible(ab, title=''):
    if len(ab) < 200 or len(ab.split()) < 35:
        return False
    if norm(ab).startswith(norm(title)) and len(ab) < len(title) + 80:
        return False
    if not re.search(r'''[.?!)”"']\s*$''', ab) or re.search(r'<[a-z/]|&[a-z]+;', ab):   # cut off mid-sentence (OCR'd first page) or leftover markup
        return False
    low = ab.lower()
    return not any(b in low[:200] for b in ('skip to', 'download', 'sign in', 'cookies', 'all rights reserved', 'javascript',
                                              'this article is only available', 'log in', 'purchase'))


def inverted(ii):
    if not ii:
        return ''
    pos = {}
    for w, idx in ii.items():
        for i in idx:
            pos[i] = w
    return ' '.join(pos[i] for i in sorted(pos))


# --- stage 1: OpenAlex, 50 DOIs a request ------------------------------------------------------------------------------
def stage_oa(arts, limit):
    cache = cache_load('openalex')            # doi -> {'c': n|None, 'ab': str|None, 'd': date}
    todo = sorted({doi_of(a) for a in arts if doi_of(a) and (need_ab(a) or need_c(a))} - set(cache))
    todo = todo[:limit] if limit else todo
    print(f'openalex: {len(todo)} DOIs to look up (cached: {len(cache)})', flush=True)
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        p = {'filter': 'doi:' + '|'.join(batch), 'per-page': 50, 'select': 'doi,cited_by_count,abstract_inverted_index'}
        if KEY:
            p['api_key'] = KEY
        d = get('https://api.openalex.org/works?' + urllib.parse.urlencode(p), timeout=90, tries=6)
        if d is None:
            print('  OpenAlex refused (budget?); re-run later', flush=True)
            break
        got = {(w.get('doi') or '').replace('https://doi.org/', '').lower(): w for w in d.get('results', [])}
        for doi in batch:
            w = got.get(doi)
            cache[doi] = {'c': w.get('cited_by_count') if w else None, 'ab': clean_abstract(inverted(w.get('abstract_inverted_index'))) if w else None,
                          'd': TODAY}
        if (i // 50) % 10 == 0:
            print(f'  {i + len(batch)}/{len(todo)}', flush=True)
            cache_save('openalex', cache)
        time.sleep(0.3)
    cache_save('openalex', cache)


# --- stage 2: Crossref ------------------------------------------------------------------------------------------------
def crossref_item(it):
    return {'doi': (it.get('DOI') or '').lower(), 'ab': clean_abstract(it.get('abstract')), 'c': it.get('is-referenced-by-count')}


def stage_crossref(arts, limit, workers=4):
    cache = cache_load('crossref')            # article id -> {'doi','ab','c','d'} (or {'none':1})
    oa = cache_load('openalex')
    todo = []
    for a in arts:
        if a['id'] in cache or not (need_ab(a) or need_c(a)):
            continue
        d = doi_of(a)
        if d and (oa.get(d) or {}).get('ab') and not need_c(a):
            continue
        if not d and len(main_title(a['t']).split()) < 3:
            continue
        todo.append(a)
    todo.sort(key=lambda a: (-(a.get('c') or 0), -(a.get('y') or 0)))
    todo = todo[:limit] if limit else todo
    print(f'crossref: {len(todo)} articles to look up (cached: {len(cache)})', flush=True)
    done = [0]

    def one(a):
        d = doi_of(a)
        res = {'d': TODAY}
        if d:
            j = get(f'https://api.crossref.org/works/{urllib.parse.quote(d)}?mailto={MAILTO}')
            it = (j or {}).get('message')
            res.update(crossref_item(it) if it else {'none': 1})
        else:
            q = a['t'] + ' ' + ((a.get('a') or [''])[0])
            j = get('https://api.crossref.org/works?' + urllib.parse.urlencode(
                {'query.bibliographic': q, 'rows': 3, 'mailto': MAILTO,
                 'select': 'DOI,title,author,issued,abstract,is-referenced-by-count,container-title'}))
            mt, full, y, au = main_title(a['t']), norm(a['t']), a.get('y'), surnames(a.get('a') or [])
            best = None
            for it in ((j or {}).get('message') or {}).get('items', []):
                t = norm((it.get('title') or [''])[0])
                if not (t == full or t.startswith(mt) or (full.startswith(t) and len(t) > 25)):
                    continue
                py = ((it.get('issued') or {}).get('date-parts') or [[None]])[0][0]
                if y and py and abs(py - y) > 2:
                    continue
                rau = surnames([(x.get('family') or '') for x in it.get('author') or []])
                if au and rau and not (au & rau):
                    continue
                best = it
                break
            res.update(crossref_item(best) if best else {'none': 1})
        with lock:
            cache[a['id']] = res
            done[0] += 1
            n = done[0]
        if n % 200 == 0:
            print(f'  {n}/{len(todo)}', flush=True)
            cache_save('crossref', cache)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    cache_save('crossref', cache)


# --- stage 3: landing pages ---------------------------------------------------------------------------------------------
META = [r'citation_abstract', r'DC\.description(?:\.abstract)?', r'og:description', r'twitter:description', r'description']


def meta_abstract(page):
    for name in META:
        for m in re.finditer(r'<meta\s+[^>]*?(?:name|property)\s*=\s*["\']' + name + r'["\'][^>]*>', page, re.I):
            c = re.search(r'content\s*=\s*"([^"]*)"|content\s*=\s*\'([^\']*)\'', m.group(0), re.I)
            if c:
                return clean_abstract(c.group(1) or c.group(2))
    return ''


def stage_landing(arts, limit):
    cache = cache_load('landing')             # article id -> {'ab': str|None, 'd'}
    have = {}
    for n in ('openalex', 'crossref'):
        have[n] = cache_load(n)

    todo = [a for a in arts if need_ab(a) and a['id'] not in cache and a.get('u') and 'doi.org' not in a['u']
            and not plausible((have['crossref'].get(a['id']) or {}).get('ab') or '', a['t'])]
    todo.sort(key=lambda a: (-(a.get('c') or 0), -(a.get('y') or 0)))
    todo = todo[:limit] if limit else todo
    print(f'landing: {len(todo)} pages to read (cached: {len(cache)})', flush=True)
    last = collections.defaultdict(float)
    for i, a in enumerate(todo):
        host = urllib.parse.urlparse(a['u']).netloc
        wait = 1.0 - (time.time() - last[host])
        if wait > 0:
            time.sleep(wait)
        last[host] = time.time()
        page = get(a['u'], timeout=30, tries=2, as_json=False)
        ab = meta_abstract(page) if page else ''
        cache[a['id']] = {'ab': ab if plausible(ab, a['t']) else None, 'd': TODAY}
        if i % 100 == 99:
            print(f'  {i + 1}/{len(todo)}', flush=True)
            cache_save('landing', cache)
    cache_save('landing', cache)


# --- stage 4: OpenCitations COCI ----------------------------------------------------------------------------------------
def stage_coci(arts, limit):
    cache = cache_load('coci')                # doi -> count
    oa, cr = cache_load('openalex'), cache_load('crossref')
    todo = []
    for a in arts:
        d = doi_of(a)
        if not d or not need_c(a) or d in cache:
            continue
        if (oa.get(d) or {}).get('c') is not None or (cr.get(a['id']) or {}).get('c') is not None:
            continue
        todo.append(d)
    todo = todo[:limit] if limit else todo
    print(f'coci: {len(todo)} DOIs to count', flush=True)

    def one(d):
        j = get('https://opencitations.net/index/coci/api/v1/citation-count/' + urllib.parse.quote(d), timeout=30, tries=2)
        if j is not None:
            with lock:
                cache[d] = int((j[0] or {}).get('count') or 0) if j else 0

    with ThreadPoolExecutor(3) as ex:
        for i in range(0, len(todo), 300):
            list(ex.map(one, todo[i:i + 300]))
            cache_save('coci', cache)
            print(f'  {min(i + 300, len(todo))}/{len(todo)}', flush=True)
    cache_save('coci', cache)


# --- results ------------------------------------------------------------------------------------------------------------
def results(arts):
    """per article id: best abstract and count found, with the source."""
    oa, cr, ld, co = (cache_load(n) for n in ('openalex', 'crossref', 'landing', 'coci'))
    out = {}
    for a in arts:
        d = doi_of(a)
        r = {}
        cands = []
        if d and (oa.get(d) or {}).get('ab'):
            cands.append(('openalex', oa[d]['ab']))
        if (cr.get(a['id']) or {}).get('ab'):
            cands.append(('crossref', cr[a['id']]['ab']))
        if (ld.get(a['id']) or {}).get('ab'):
            cands.append(('landing', ld[a['id']]['ab']))
        for src, ab in cands:
            ab = clean_abstract(ab)   # cached text may predate a cleaning fix
            if plausible(ab, a['t']):
                r['ab'], r['ab_src'] = ab, src
                break
        counts = []
        if d and (oa.get(d) or {}).get('c') is not None:
            counts.append(('openalex', oa[d]['c']))
        if (cr.get(a['id']) or {}).get('c') is not None:
            counts.append(('crossref', cr[a['id']]['c']))
        if d and d in co:
            counts.append(('coci', co[d]))
        if counts:
            r['c_src'], r['c'] = max(counts, key=lambda x: x[1])
            r['c_oa'] = next((v for s, v in counts if s == 'openalex'), None)
        if (cr.get(a['id']) or {}).get('doi') and not d:
            r['doi'] = cr[a['id']]['doi']
        if r:
            out[a['id']] = r
    return out


def cmd_stats(arts):
    res = results(arts)
    new_ab = [a for a in arts if need_ab(a) and 'ab' in res.get(a['id'], {})]
    new_c = [a for a in arts if need_c(a) and 'c' in res.get(a['id'], {})]
    bigger = [a for a in arts if not need_c(a) and (res.get(a['id'], {}).get('c_oa') or -1) > (a.get('c') or 0)]
    print(f'articles: {len(arts)}; without/cut-off abstract: {sum(need_ab(a) for a in arts)}; without count: {sum(need_c(a) for a in arts)}')
    print(f'abstracts found: {len(new_ab)} (by source {dict(collections.Counter(res[a["id"]]["ab_src"] for a in new_ab))})')
    print(f'counts found for articles with none: {len(new_c)} (by source {dict(collections.Counter(res[a["id"]]["c_src"] for a in new_c))}); '
          f'OpenAlex counts above the stored one: {len(bigger)}')
    for a in new_ab[:3]:
        print('  AB', a['id'], a['t'][:60], '|', res[a['id']]['ab'][:140])
    for a in new_c[:3]:
        print('  C ', a['id'], a['t'][:60], '|', res[a['id']]['c'], res[a['id']]['c_src'])


def cmd_apply(raw, d, dry):
    res = results(d['articles'])
    n_ab = n_c = n_up = 0
    for a in d['articles']:
        r = res.get(a['id'])
        if not r:
            continue
        if 'ab' in r and need_ab(a) and len(r['ab']) > len(a.get('ab') or ''):
            a['ab'] = r['ab']
            n_ab += 1
        if 'c' in r and not (a.get('rv') or a.get('cx')):
            if a.get('c') is None:
                a['c'] = r['c']
                n_c += 1
            elif (r.get('c_oa') or -1) > a['c']:
                a['c'] = r['c_oa']
                n_up += 1
    print(f'{n_ab} abstracts set; {n_c} counts added; {n_up} counts raised (OpenAlex)')
    if not dry:
        open(ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
        print('wrote', ART, '(now run: python scripts/fix_text.py)')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'stats'
    arg = lambda k, dflt=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else dflt
    raw, d = load_articles()
    arts = d['articles']
    if cmd == 'lookup':
        limit = int(arg('--limit', 0) or 0)
        stage = arg('--stage', 'all')
        for name, fn in (('oa', stage_oa), ('crossref', stage_crossref), ('landing', stage_landing), ('coci', stage_coci)):
            if stage in ('all', name):
                fn(arts, limit)
        cmd_stats(arts)
    elif cmd == 'apply':
        cmd_apply(raw, d, '--dry-run' in sys.argv)
    else:
        cmd_stats(arts)


if __name__ == '__main__':
    main()
