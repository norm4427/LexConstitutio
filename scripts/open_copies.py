"""Find free, legal full-text copies for articles whose only link is JSTOR or a DOI (e.g. Amar, "Intratextualism",
112 Harv. L. Rev. 747, has a copy in Yale Law School's repository).

Source: OpenAlex's record for the article's DOI, which lists every known copy ("locations"). A copy is kept only when all of
these hold, erring toward leaving a link out:
  - OpenAlex marks the copy open access and it sits in a repository (a law school or university repository, SSRN, DASH ...),
    not on a publisher or aggregator page that may be paywalled;
  - the OpenAlex record's title matches our title (after normalizing case and punctuation), its year is within one year
    of ours, and the first author's surname appears among its authors, so the DOI record is really this article;
  - the repository belongs to an institution one of the authors is affiliated with in OpenAlex (Yale's repository for a Yale
    author), or is a general-purpose scholarly repository (SSRN, arXiv, PhilPapers, Zenodo), so a copy attached to the
    record by mistake from an unrelated school is not used.
Writes data/raw/open_copies.json {article id: {url, host, version}} (cached OpenAlex responses in data/raw/openalex_oa/),
then sets `oa` (and `oav`, the version) on those articles in docs/data/articles.js.
Run from the repo root after build.ps1 (and before fix_text.py):  python scripts/open_copies.py
"""
import json, os, re, time, unicodedata, urllib.parse, urllib.request

CACHE = 'data/raw/openalex_oa'
GENERAL = ('ssrn.com', 'arxiv.org', 'philpapers.org', 'zenodo.org', 'papers.ssrn.com')


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def surname(name):
    parts = [p for p in re.split(r'[\s,]+', norm(name)) if p not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return parts[-1] if parts else ''


def fetch(dois):
    os.makedirs(CACHE, exist_ok=True)
    key = f'{CACHE}/{abs(hash(tuple(sorted(dois)))) % 10**12}.json'
    if os.path.exists(key):
        return json.load(open(key, encoding='utf-8'))
    flt = 'doi:' + '|'.join(dois)
    url = 'https://api.openalex.org/works?' + urllib.parse.urlencode({'filter': flt, 'per-page': 50,
          'select': 'doi,title,publication_year,authorships,locations'})
    for n in range(5):
        try:
            time.sleep(0.25 + 5 * n)
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0 (static site build)'}), timeout=60))
            json.dump(d['results'], open(key, 'w', encoding='utf-8'))
            return d['results']
        except Exception as e:
            err = e
    print('  OpenAlex failed:', err)
    return []


def inst_tokens(w):
    """distinctive words of the authors' institutions ("yale", "columbia", "pennsylvania" ...)."""
    stop = {'university', 'of', 'the', 'school', 'law', 'college', 'center', 'institute', 'and', 'at', 'state', 'new', 'in', 'for', 'de'}
    out = set()
    for a in w.get('authorships') or []:
        for i in a.get('institutions') or []:
            out |= {t for t in norm(i.get('display_name')).split() if t not in stop and len(t) > 2}
    return out


def host_ok(host, toks):
    if any(host.endswith(g) for g in GENERAL):
        return True
    words = set(re.split(r'[.\-]', host))
    # common abbreviations used in repository hostnames
    alias = {'upenn': 'pennsylvania', 'umich': 'michigan', 'uchicago': 'chicago', 'nyu': 'york', 'ucla': 'los', 'bu': 'boston',
             'wm': 'mary', 'umn': 'minnesota', 'wustl': 'washington', 'uga': 'georgia', 'unl': 'nebraska', 'uky': 'kentucky',
             'gwu': 'george', 'law': '', 'scholarship': '', 'repository': '', 'digitalcommons': '', 'edu': '', 'org': '', 'www': ''}
    words |= {alias[w] for w in words if alias.get(w)}
    return bool(words & toks)


def main():
    raw = open('docs/data/articles.js', encoding='utf-8').read()
    data = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    arts = data['articles']
    todo = [a for a in arts if (a.get('u') or '').startswith('https://doi.org/') and not a.get('pdf')]
    todo.sort(key=lambda a: -(a.get('c') or 0))           # most cited first
    by_doi = {a['u'].split('doi.org/', 1)[1].lower(): a for a in todo}
    found, checked, rejected = {}, 0, {'title': 0, 'host': 0, 'none': 0}
    dois = list(by_doi)
    for i in range(0, len(dois), 50):
        for w in fetch(dois[i:i + 50]):
            a = by_doi.get((w.get('doi') or '').replace('https://doi.org/', '').lower())
            if not a:
                continue
            checked += 1
            names = ' '.join(norm((au.get('author') or {}).get('display_name')) for au in w.get('authorships') or [])
            same = (norm(w.get('title')) == norm(a['t']) or (len(norm(a['t'])) > 25 and norm(a['t']) in norm(w.get('title'))))
            if not same or abs((w.get('publication_year') or 0) - (a.get('y') or 0)) > 1 or (a['a'] and surname(a['a'][0]) not in names.split()):
                rejected['title'] += 1
                continue
            toks = inst_tokens(w)
            best = None
            for l in w.get('locations') or []:
                src = l.get('source') or {}
                url = l.get('pdf_url') or l.get('landing_page_url') or ''
                if not l.get('is_oa') or not url.startswith('http') or 'doi.org' in url or 'jstor.org' in url:
                    continue
                if src.get('type') != 'repository' and 'repository' not in (src.get('display_name') or '').lower():
                    continue
                host = urllib.parse.urlparse(url).netloc.lower().removeprefix('www.')
                if not host_ok(host, toks):
                    rejected['host'] += 1
                    continue
                cand = {'url': url, 'host': host, 'version': l.get('version') or ''}
                if not best or (cand['version'] == 'publishedVersion' and best['version'] != 'publishedVersion'):
                    best = cand
            if best:
                found[a['id']] = best
            else:
                rejected['none'] += 1
        if i % 1000 == 0:
            print(f'{i}/{len(dois)} looked up, {len(found)} open copies so far', flush=True)
    json.dump(found, open('data/raw/open_copies.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for a in arts:
        a.pop('oa', None); a.pop('oav', None)
        if a['id'] in found:
            a['oa'] = found[a['id']]['url']
            if found[a['id']]['version']:
                a['oav'] = found[a['id']]['version']
    open('docs/data/articles.js', 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{len(todo)} JSTOR/DOI-only articles; {checked} matched in OpenAlex; {len(found)} open copies kept; rejected {rejected}')
    top = sorted((a for a in todo if a['id'] in found), key=lambda a: -(a.get('c') or 0))[:5]
    for a in top:
        print('  ', a['t'][:60], '->', found[a['id']]['url'])


if __name__ == '__main__':
    main()
