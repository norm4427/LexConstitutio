"""Find free, legal copies of articles that only link to JSTOR (or another paywalled page), most-cited first.

Step 1 (lookup): for each article with a DOI and no `oa`, `pdf` or `pub`, not a book review, ask Unpaywall
  (api.unpaywall.org, a generic contact address, one request a second) for its open-access locations. Responses are cached in
  data/raw/unpaywall/<doi>.json, so reruns skip finished items.
Step 2 (apply): keep a location only when ALL of these hold, erring toward leaving a link out:
  - the host is the journal's own school or publisher (Yale's repository for the Yale Law Journal, Penn's for Penn Law
    Review, ...), the repository of an institution one of the authors belongs to (judged as open_copies.py does, from
    OpenAlex), or an established open repository (SSRN abstract pages and the like are NOT used: their pages can't be checked);
  - where the file name carries volume and first page (Yale's does: 115YaleLJ1346) they agree with ours, and the year is within
    one of ours when Unpaywall gives one;
  - the Unpaywall record's title matches our title (normalized) and its year is within one of ours.
Writes data/raw/free_copies.json {article id: {url, host, version, via}} and sets `oa` / `oav` on articles that lack a free
route. Articles already handled (including ones checked with no result) are logged in data/raw/free_copies.log.
Run from the repo root after open_copies.py (which clears and rebuilds `oa` and so must run first):
    python scripts/free_copies.py lookup [N]     # N = how many of the most-cited candidates to look up (default 500)
    python scripts/free_copies.py apply
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import open_copies as oc
from open_copies import norm, surname

CACHE = 'data/raw/unpaywall'
CR = 'data/raw/crossref_ssrn'
AUTH = {}
EMAIL = 'lexconstitutio-build@example.org'     # generic contact address; the site owner's address is never sent
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
ART = 'docs/data/articles.js'

# journal id -> host fragments for the journal's own school, publisher or archive
JOURNAL_HOSTS = {
    'ylj': ['yale.edu'], 'pennlr': ['upenn.edu'], 'calr': ['berkeley.edu', 'escholarship.org', 'californialawreview.org'],
    'colr': ['columbia.edu', 'columbialawreview.org'], 'hlr': ['harvard.edu', 'harvardlawreview.org'],
    'slr': ['stanford.edu', 'stanfordlawreview.org'], 'valr': ['virginia.edu', 'virginialawreview.org'],
    'scr': ['uchicago.edu'], 'mlr_mich': ['umich.edu'], 'mlr_minn': ['umn.edu'], 'clr': ['cornell.edu'],
    'nulr': ['northwestern.edu'], 'uclrev': ['uchicago.edu'], 'tlr': ['texaslrev.com', 'texaslawreview.org', 'utexas.edu'],
    'nyulr': ['nyulawreview.org', 'nyu.edu'], 'uclalr': ['uclalawreview.org', 'ucla.edu', 'escholarship.org'],
}


def load():
    raw = open(ART, encoding='utf-8').read()
    return raw, json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))


def candidates(arts):
    c = [a for a in arts if not (a.get('oa') or a.get('pdf') or a.get('pub')) and not a.get('rv')
         and (a.get('u') or '').startswith('https://doi.org/')]
    c.sort(key=lambda a: -(a.get('c') or 0))
    return c


def doi_of(a):
    return a['u'].split('doi.org/', 1)[1].lower()


def cache_path(doi):
    return os.path.join(CACHE, re.sub(r'[^a-z0-9._-]', '_', doi) + '.json')


def lookup(n):
    os.makedirs(CACHE, exist_ok=True)
    _, data = load()
    todo = [a for a in candidates(data['articles'])[:n] if not os.path.exists(cache_path(doi_of(a)))]
    print(f'{len(todo)} to look up', flush=True)
    stop = []

    def one(a):
        doi = doi_of(a)
        url = f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={EMAIL}'
        body = None
        for t in range(3):
            if stop:
                return
            try:
                time.sleep(0.5 + 4 * t)
                body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode('utf-8')
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    body = '{"error": "not found"}'
                    break
                if e.code == 429:
                    stop.append(1)
                    print('rate limited; stopping (cached so far)')
                    return
            except Exception:
                pass
        if body:
            open(cache_path(doi), 'w', encoding='utf-8').write(body)

    # Unpaywall's own limit is 100,000 calls a day; four requests in flight is about two a second
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        for k, _ in enumerate(ex.map(one, todo)):
            if k % 100 == 0:
                print(f'  {k}/{len(todo)}', flush=True)


def vol_page_ok(url, a):
    """Yale-style file names (115YaleLJ1346_...): when present, volume and first page must match ours."""
    m = re.search(r'/(\d{1,3})[A-Za-z]+LJ(\d{1,4})[_.]', url) or re.search(r'/(\d{1,3})YaleLJ(\d{1,4})', url)
    if not m:
        return True
    return int(m.group(1)) == a.get('v') and int(m.group(2)) == a.get('fp')


def ssrn_id(url):
    m = re.search(r'ssrn\.(\d+)', url) or re.search(r'abstract_?id=(\d+)', url, re.I) or re.search(r'abstract=(\d+)', url) or re.search(r'SSRN_ID(\d+)', url)
    return m.group(1) if m else None


def ssrn_ok(sid, a):
    """SSRN's own pages can't be fetched here, so the paper is checked against Crossref's record for its SSRN DOI:
    same title, first author's surname among its authors, year within five of ours."""
    os.makedirs(CR, exist_ok=True)
    p = os.path.join(CR, sid + '.json')
    if not os.path.exists(p):
        if '--cached' in sys.argv:
            return False
        body = '{}'
        try:
            time.sleep(0.3)
            body = urllib.request.urlopen(urllib.request.Request(
                f'https://api.crossref.org/works/10.2139/ssrn.{sid}?mailto={EMAIL}', headers=UA), timeout=60).read().decode('utf-8')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return False
        except Exception:
            return False
        open(p, 'w', encoding='utf-8').write(body)
    try:
        m = json.load(open(p, encoding='utf-8')).get('message') or {}
    except Exception:
        return False
    title = ' '.join(m.get('title') or [])
    same = norm(title) == norm(a['t']) or (len(norm(a['t'])) > 25 and (norm(a['t']) in norm(title) or norm(title) in norm(a['t'])))
    fam = [norm(x.get('family')) for x in m.get('author') or []]
    yr = ((m.get('posted') or m.get('issued') or {}).get('date-parts') or [[0]])[0][0] or 0
    return bool(same and a['a'] and surname(a['a'][0]) in ' '.join(fam).split() and abs(yr - (a.get('y') or 0)) <= 5)


INST_DOI = {'10.15779': ['calr'], '10.7916': ['colr']}   # Berkeley Law's and Columbia's own DOI prefixes, for their own journals


def choose(a, rec):
    if not rec or not rec.get('is_oa'):
        return None
    if norm(rec.get('title')) != norm(a['t']) and not (len(norm(a['t'])) > 25 and norm(a['t']) in norm(rec.get('title'))):
        return None
    if rec.get('year') and abs(rec['year'] - (a.get('y') or 0)) > 1:
        return None
    frags = JOURNAL_HOSTS.get(a['j'], [])
    w = oc.SEEN.get(doi_of(a))       # OpenAlex record from open_copies.py's cache: the authors' institutions
    toks = oc.inst_tokens(w) if w else set()
    for au in (w or {}).get('authorships') or []:
        toks |= AUTH.get((au.get('author') or {}).get('id'), set())
    best = None
    for l in rec.get('oa_locations') or []:
        urls = [u for u in (l.get('url_for_pdf'), l.get('url_for_landing_page'), l.get('url')) if u]
        if not urls:
            continue
        url = urls[0]
        host = urllib.parse.urlparse(url).netloc.lower().removeprefix('www.')
        landing = urllib.parse.urlparse(l.get('url_for_landing_page') or '').netloc.lower().removeprefix('www.')
        via = None
        if 'jstor.org' in host or not url.startswith('http'):
            continue
        sid = next((ssrn_id(u) for u in urls if 'ssrn' in u.lower()), None)
        if sid:
            if ssrn_ok(sid, a):
                url, host, via = f'https://papers.ssrn.com/abstract={sid}', 'papers.ssrn.com', 'ssrn'
        elif 'doi.org' in host:
            pre = url.split('doi.org/', 1)[1].split('/')[0]
            if a['j'] in INST_DOI.get(pre, []):
                via = 'journal doi'
        elif any(host.endswith(f) or landing.endswith(f) for f in frags):
            via = 'journal'
        elif l.get('host_type') == 'repository' and oc.host_ok(host, toks) and not re.search(r'handle\.net|hathitrust|zenodo|archive\.org|core\.ac\.uk', host):
            via = 'author institution'
        if not via or not vol_page_ok(url, a):
            continue
        cand = {'url': url, 'host': host, 'version': l.get('version') or '', 'via': via}
        if cand['version'] == 'submittedVersion':
            cand['version'] = ''       # not a version the site's buttons name
        rank = lambda c: ({'journal': 0, 'journal doi': 0, 'author institution': 1, 'ssrn': 2}[c['via']], c['version'] != 'publishedVersion')
        if not best or rank(cand) < rank(best):
            best = cand
    return best


def apply():
    global AUTH
    AUTH = oc.author_insts()          # also loads open_copies.py's cached OpenAlex records into oc.SEEN (no network)
    raw, data = load()
    arts = data['articles']
    found, checked = {}, 0
    for a in candidates(arts):
        p = cache_path(doi_of(a))
        if not os.path.exists(p):
            continue
        checked += 1
        try:
            rec = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        best = choose(a, rec)
        if best:
            found[a['id']] = best
    json.dump(found, open('data/raw/free_copies.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n = 0
    for a in arts:
        f = found.get(a['id'])
        if f and not (a.get('oa') or a.get('pdf') or a.get('pub')):
            a['oa'] = f['url']
            if f['version']:
                a['oav'] = f['version']
            n += 1
    open(ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    cand = candidates(arts)
    print(f'{checked} looked up; {len(found)} free copies found; {n} set on articles')
    by = {}
    for f in found.values():
        by[f['host']] = by.get(f['host'], 0) + 1
    print(sorted(by.items(), key=lambda x: -x[1])[:15])


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'apply'
    if cmd == 'lookup':
        lookup(int(sys.argv[2]) if len(sys.argv) > 2 else 500)
    else:
        apply()
