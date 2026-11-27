"""Fill the gaps in docs/data/books.js after build_books.pl and books_impact_merge.pl. Only missing fields are filled;
curated values (scripts/books.json) are never replaced.

  publisher   Open Library: the publisher of the earliest dated edition of the book's work (the `ol` link)
  cover       Open Library: the work's cover, or the cover of its earliest edition that has one
  note        scripts/books_notes.tsv: a short neutral note written for the site (id <TAB> note)
  reviews     law-review book reviews in the article index (docs/data/articles.js, read only): an article flagged as a
              review (rv) whose title is the book's title, or that names the book in its title or abstract with the
              author's surname; added to the reviews build_books.pl matched
  oaReviews   reviews outside the index, from OpenAlex: journal articles published within six years of the book, titled
              with the book's title (the JSTOR form of a book review) or naming it and its author, not written by the author
  cites       OpenAlex: the citation count of the book's record (type book, title and author surname must match), for
              books that have none; ranks are recomputed over all books with counts
OpenAlex needs OPENALEX_KEY in .keys.env (scripts/local_keys.py); the key is never printed. Responses are cached in
data/raw/books/. Run from the repo root:  python scripts/books_enrich.py
"""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_keys  # noqa: F401,E402  (loads OPENALEX_KEY into the environment)

RAW = 'data/raw/books'
UA = {'User-Agent': 'LexConstitutio/1.0 (educational book index)'}


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def get(url, path, pause=1.0):
    """JSON from url, cached at path ({} on failure, not cached)."""
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            d = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print('  failed', re.sub(r'api_key=[^&]+', 'api_key=…', url)[:120], type(e).__name__)
        return {}
    json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(pause)
    return d


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if not unicodedata.combining(c))


def nt(s):
    """a title for comparison: lower case, no leading article, letters and digits only"""
    s = fold(s).lower().replace('&', 'and')
    s = re.sub(r'^(the|a|an)\s+', '', s.strip())
    return re.sub(r'[^a-z0-9]', '', s)


def surname(n):
    p = re.sub(r',?\s+(Jr|Sr|I{2,3}|IV)\.?$', '', n).split()
    return fold(p[-1]).lower() if p else ''


def year_of(s):
    m = re.search(r'\b(1[5-9]\d\d|20\d\d)\b', s or '')
    return int(m.group(1)) if m else None


PUB_FIX = [(r'\s*[,;:]\s*$', ''), (r'^\[|\]$', ''), (r',?\s+(Inc|Ltd|Co|Corp|LLC)\.?$', ''), (r'\s+', ' ')]


PUB_NAME = [(r'^Oxford University Press.*', 'Oxford University Press'), (r'^(?:W\. ?W\. )?Norton\b.*|.*Norton & Company.*', 'W. W. Norton'),
            (r'^Basic Books\b.*', 'Basic Books'), (r'^(?:Alfred A\. )?Knopf\b.*', 'Knopf'), (r'^Houghton Mifflin Harcourt\b.*', 'Houghton Mifflin Harcourt'),
            (r'^HarperCollins\b.*', 'HarperCollins'), (r'^Henry Holt\b.*', 'Henry Holt'), (r'^Farrar,? Straus (?:&|and) Giroux.*', 'Farrar, Straus and Giroux'),
            (r'^Simon (?:&|and) Schuster.*', 'Simon & Schuster'), (r'^Cambridge University Press.*', 'Cambridge University Press'),
            (r'^(?:The )?Belknap Press of Harvard University Press$', 'Harvard University Press'), (r'^Little,? Brown.*', 'Little, Brown and Company'),
            (r'^(?:H\. )?Holt\b.*|.*Henry Holt.*', 'Henry Holt'), (r'^Mac[Mm]illan\b.*', 'Macmillan'), (r'^(?:The )?Free Press$', 'Free Press'),
            (r'.*University of North Carolina Press$', 'University of North Carolina Press')]
# first-edition publishers checked by hand where Open Library's earliest dated edition is a foreign or reprint edition
PUB_OVERRIDE = {'law-s-empire': 'Harvard University Press', 'law-and-disagreement': 'Oxford University Press',
                'separation-of-church-and-state': 'Harvard University Press', 'justices-presidents-and-senators': 'Oxford University Press',
                'packing-the-court': 'Penguin Press', 'shielded': 'Viking', 'foreign-affairs-and-the-united-states-constituti': 'Oxford University Press',
                'election-meltdown': 'Yale University Press'}
NOT_PUB = re.compile(r'thorndike|large print|g\. ?k\. hall|wheeler publishing|audio|tantor|blackstone|brilliance|recorded books|^(?:new york|london|boston|chicago|cambridge|oxford|[A-Z][a-z]+, [A-Z]{2})$|unknown|s\.n\.', re.I)


def clean_pub(p):
    p = p.strip()
    for a, b in PUB_FIX:
        p = re.sub(a, b, p).strip()
    for a, b in PUB_NAME:
        p = re.sub(a, b, p)
    return '' if NOT_PUB.search(p) else p


# ------------------------------------------------------------------ Open Library
def open_library(b):
    key = re.search(r'/works/(OL\d+W)', b.get('ol') or '')
    if not key:
        return None, None
    k = key.group(1)
    eds = get(f'https://openlibrary.org/works/{k}/editions.json?limit=200', f'{RAW}/{b["id"]}.oled.json').get('entries', [])
    eds = [e for e in eds if not re.search(r'audio|\bcd\b|mp3|cassette', e.get('physical_format') or '', re.I)]
    dated = sorted((e for e in eds if year_of(e.get('publish_date'))), key=lambda e: year_of(e.get('publish_date')))
    # the publisher of the first edition: the most common among editions dated within a year of the earliest
    pubs = [(year_of(e['publish_date']), clean_pub(e['publishers'][0])) for e in dated if e.get('publishers') and clean_pub(e['publishers'][0])]
    first = [p for y, p in pubs if y <= pubs[0][0] + 1] if pubs else []
    pub = max(first, key=first.count) if first else None
    cover = None
    if not b.get('cover'):
        w = get(f'https://openlibrary.org/works/{k}.json', f'{RAW}/{b["id"]}.olw.json')
        cid = next((c for c in w.get('covers') or [] if c and c > 0), None) or next((c for e in dated + eds for c in e.get('covers') or [] if c and c > 0), None)
        cover = f'https://covers.openlibrary.org/b/id/{cid}-L.jpg' if cid else None
    return pub, cover


# ------------------------------------------------------------------ reviews
_PRE = {}


def prepared(a):
    """an article's title key and folded title + abstract, computed once"""
    if a['id'] not in _PRE:
        text = fold(a['t'] + ' ' + (a.get('ab') or '')).lower()
        _PRE[a['id']] = (nt(a['t']), text, re.sub(r'[^a-z0-9]', '', re.sub(r'\b(the|a|an)\b', '', text)))
    return _PRE[a['id']]


def index_reviews(b, arts):
    main = b['title'].split(':')[0]
    mk, fk = nt(main), nt(b['title'])
    lasts = {surname(a) for a in b['authors']}
    out = []
    for a in arts:
        if (a.get('y') or 9999) < b['year'] - 1:
            continue
        t, text, squeezed = prepared(a)
        by_author = any(surname(x) in lasts for x in a.get('a') or [])
        if by_author:
            continue
        names = any(re.search(r'(?<![a-z])' + re.escape(l) + r'(?![a-z])', text) for l in lasts if l)
        exact = t == mk or t == fk or (len(mk) >= 14 and t.startswith(mk))
        mentions = len(mk) >= 14 and mk in squeezed
        if (a.get('rv') and (exact or (mentions and names))) or (exact and names):
            out.append(a['id'])
    return out


def openalex(params, path):
    key = os.environ.get('OPENALEX_KEY')
    if key:
        params = dict(params, api_key=key)
    return get('https://api.openalex.org/works?' + urllib.parse.urlencode(params), path, pause=0.2)


def oa_reviews(b, known_titles):
    main = b['title'].split(':')[0]
    mk = nt(main)
    if len(mk) < 6:
        return []
    lasts = {surname(a) for a in b['authors']}
    d = openalex({'filter': f'title.search:{main.replace(",", " ")},publication_year:{b["year"]}-{b["year"] + 6}', 'per_page': 50,
                  'select': 'id,doi,title,publication_year,type,authorships,primary_location'}, f'{RAW}/{b["id"]}.oarev.json')
    out, seen = [], set()
    for r in d.get('results') or []:
        t = r.get('title') or ''
        if len(t) > 220:
            continue                                  # run-together metadata, not a review's title
        letters = re.sub(r'[\s\d\W_]', '', t)
        if not letters or len(re.findall(r'[A-Za-z]', letters)) < 0.7 * len(letters):
            continue                                  # titles in other scripts (abstracting services)
        src = ((r.get('primary_location') or {}).get('source') or {})
        if r.get('type') in ('book', 'book-chapter', 'dissertation') or src.get('type') != 'journal':
            continue
        auth = [x['author']['display_name'] for x in r.get('authorships') or [] if x.get('author')]
        if not auth or any(surname(x) in lasts for x in auth):
            continue
        tn = nt(t)
        exact = tn == mk or tn == nt(b['title']) or (len(mk) >= 12 and tn.startswith(mk) and len(tn) <= len(nt(b['title'])) + 2)
        names = any(re.search(r'(?<![a-z])' + re.escape(l) + r'(?![a-z])', fold(t).lower()) for l in lasts if l)
        generic = len(mk) < 14
        if not ((exact and not generic) or (mk in tn and names) or (exact and names)):
            continue
        if tn in seen or tn in known_titles and False:
            continue
        seen.add(tn)
        out.append({'t': t, 'a': auth[:3], 'j': src.get('display_name') or '', 'y': r.get('publication_year'), 'url': r.get('doi') or r['id']})
    return sorted(out, key=lambda x: x['y'] or 0)[:8]


def oa_cites(b):
    main = b['title'].split(':')[0]
    mk = nt(main)
    lasts = {surname(a) for a in b['authors']}
    d = openalex({'search': f'{main} {surname(b["authors"][0])}', 'filter': 'type:book', 'per_page': 10,
                  'select': 'id,title,publication_year,cited_by_count,authorships'}, f'{RAW}/{b["id"]}.oa2.json')
    best = None
    for r in d.get('results') or []:
        t = nt((r.get('title') or '').split(':')[0])
        if not (t == mk or (len(mk) >= 12 and t.startswith(mk))):
            continue
        if not any(surname(x['author']['display_name']) in lasts for x in r.get('authorships') or [] if x.get('author')):
            continue
        if not best or (r.get('cited_by_count') or 0) > best['n']:
            best = {'n': r.get('cited_by_count') or 0, 'src': 'OpenAlex', 'url': r['id']}
    return best if best and best['n'] > 0 else None


def main():
    os.makedirs(RAW, exist_ok=True)
    B = load_js('docs/data/books.js')
    curated = {b['id']: b for b in json.load(open('scripts/books.json', encoding='utf-8'))}
    for b in B['books']:   # re-derive what this script filled on an earlier run (curated values stay)
        if not curated.get(b['id'], {}).get('publisher'):
            b.pop('publisher', None)
        if not curated.get(b['id'], {}).get('note'):
            b.pop('note', None)
    arts = load_js('docs/data/articles.js')['articles']
    notes = {}
    if os.path.exists('scripts/books_notes.tsv'):
        for line in open('scripts/books_notes.tsv', encoding='utf-8'):
            if line.strip() and not line.startswith('#') and '\t' in line:
                i, n = line.rstrip('\n').split('\t', 1)
                notes[i] = n.strip()
    count = lambda: {'publisher': sum(1 for b in B['books'] if b.get('publisher')), 'note': sum(1 for b in B['books'] if b.get('note')),
                     'reviews': sum(1 for b in B['books'] if b.get('reviews') or b.get('oaReviews')), 'cites': sum(1 for b in B['books'] if b.get('cites')),
                     'cover': sum(1 for b in B['books'] if b.get('cover'))}
    before = count()
    titles = {nt(a['t']) for a in arts}
    for n, b in enumerate(B['books']):
        if not b.get('publisher') or not b.get('cover'):
            pub, cover = open_library(b)
            pub = PUB_OVERRIDE.get(b['id']) or pub
            if pub and not b.get('publisher'):
                b['publisher'] = pub
            if cover and not b.get('cover'):
                b['cover'] = cover
        if not b.get('note') and notes.get(b['id']):
            b['note'] = notes[b['id']]
        rv = list(dict.fromkeys((b.get('reviews') or []) + index_reviews(b, arts)))
        byid = {a['id']: a for a in arts}
        b['reviews'] = sorted(rv, key=lambda i: (byid.get(i) or {}).get('y') or 0)[:12]
        idx_titles = {nt(byid[i]['t']) for i in b['reviews'] if i in byid}
        oar = [r for r in oa_reviews(b, titles) if nt(r['t']) not in idx_titles]
        if oar:
            b['oaReviews'] = oar
        else:
            b.pop('oaReviews', None)
        if not b.get('cites'):
            c = oa_cites(b)
            if c:
                b['cites'] = c
        if n % 25 == 0:
            print(f'  {n}/{len(B["books"])}', flush=True)
    ranked = sorted((b for b in B['books'] if b.get('cites')), key=lambda b: -b['cites']['n'])
    for i, b in enumerate(ranked):
        b['cites']['rank'] = i + 1
    B['citedBooks'] = len(ranked)
    open('docs/data/books.js', 'w', encoding='utf-8').write('window.BOOKS=' + json.dumps(B, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + ';')
    after = count()
    print('before', before)
    print('after ', after, 'of', len(B['books']))
    print('no publisher:', [b['id'] for b in B['books'] if not b.get('publisher')])
    print('no note:', len([b for b in B['books'] if not b.get('note')]))


if __name__ == '__main__':
    main()
