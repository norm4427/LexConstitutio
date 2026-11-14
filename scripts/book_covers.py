"""Pick a verified, sharp cover image for each book in docs/data/books.js (run after build_books.pl).

Every candidate must belong to the book's own Open Library work (build_books.pl matches the work by title and whole-word
author surname):
  * the ISBN is checked first: each ISBN of the work is looked up at openlibrary.org/isbn/<isbn>.json until one whose
    edition carries the same title is found. That ISBN replaces the build's unchecked pick
    and drives the Amazon link; with none verified, the ISBN is dropped.
  * candidates: the work's own Open Library cover (from the build); Open Library's cover for the verified ISBN; Google
    Books' front cover for that ISBN when the Google volume has the same title and author; Amazon's catalog image for the
    ISBN-10; the Goodreads image (only set by the build when Goodreads matched title and author and Open Library had none).
Each candidate is downloaded and measured; placeholders (tiny, blank or oddly shaped images) are rejected and the
tallest real cover wins, ties keeping the current one. scripts/book_covers_manual.tsv overrides the result for covers
checked by eye (a URL, or "none" for the site's placeholder). Caches: data/raw/books/covers.json (image sizes),
isbn_check.json (ISBN -> edition), google.json (ISBN -> Google volume). Run from the repo root: python scripts/book_covers.py
"""
import json, os, re, struct, time, urllib.parse, urllib.request

CACHE = 'data/raw/books/covers.json'
ISBN_CACHE = 'data/raw/books/isbn_check.json'
GOOGLE_CACHE = 'data/raw/books/google.json'
MANUAL = 'scripts/book_covers_manual.tsv'
UA = {'User-Agent': 'Mozilla/5.0 (LexConstitutio static site build)'}


def dims(b):
    """(width, height) from image bytes, or None."""
    if b[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', b[16:24])
    if b[:6] in (b'GIF87a', b'GIF89a'):
        return struct.unpack('<HH', b[6:10])
    if b[:2] == b'\xff\xd8':
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack('>HH', b[i + 5:i + 9])
                return w, h
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            i += 2 + struct.unpack('>H', b[i + 2:i + 4])[0]
    return None


def isbn10(isbn13):
    d = re.sub(r'\D', '', isbn13 or '')
    if len(d) == 10:
        return d
    if len(d) != 13 or not d.startswith('978'):
        return None
    core = d[3:12]
    s = sum((10 - i) * int(c) for i, c in enumerate(core)) % 11
    chk = (11 - s) % 11
    return core + ('X' if chk == 10 else str(chk))


def norm(s):
    s = (s or '').lower().replace('&', 'and')
    s = re.sub(r'\b(the|a|an|of|inc|co|company)\b', '', s)
    return re.sub(r'[^a-z0-9]', '', s)


def same_title(a, b):
    """Main titles (before any subtitle) equal, or one begins the other (10+ characters)."""
    x, y = norm((a or '').split(':')[0]), norm((b or '').split(':')[0])
    if not x or not y:
        return False
    return x == y or (len(x) >= 10 and y.startswith(x)) or (len(y) >= 10 and x.startswith(y))


def surname(book):
    return re.sub(r',?\s+(Jr|Sr|II|III|IV)\.?$', '', book['authors'][0]).split()[-1]


def get_json(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))


def measure(url):
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
    except Exception:
        return None
    d = dims(data)
    if not d:
        return None
    w, h = d
    # placeholders: Amazon's 1x1 gif, Open Library's blank, Google's "image not available" (often 128x200-ish with little data)
    if w < 100 or h < 150 or len(data) < 4000 or not (0.45 <= w / h <= 0.95):
        return None
    return {'w': w, 'h': h, 'bytes': len(data)}


def isbn_edition(isbn, cache):
    """{'work', 'title'} for an ISBN from Open Library (cached; None if unknown)."""
    if isbn not in cache:
        try:
            e = get_json(f'https://openlibrary.org/isbn/{isbn}.json')
            cache[isbn] = {'work': ((e.get('works') or [{}])[0]).get('key'), 'title': e.get('title'), 'edition': e.get('key')}
        except urllib.error.HTTPError as err:
            if err.code != 404:
                return None   # transient: don't cache
            cache[isbn] = None
        except Exception:
            return None
        time.sleep(0.4)
    return cache[isbn]


def verified_isbn(b, cache):
    """First ISBN of the book's Open Library work whose edition carries the same title."""
    m = re.search(r'/works/(OL\d+W)', b.get('ol') or '')
    if not m:
        return None
    work = '/works/' + m.group(1)
    try:
        ol = json.load(open(f'data/raw/books/{b["id"]}.ol.json', encoding='utf-8'))
    except Exception:
        return None
    doc = next((d for d in ol.get('docs') or [] if d.get('key') == work), None)
    if not doc:
        return None
    isbns = [i for i in doc.get('isbn') or [] if re.fullmatch(r'97[89]\d{10}', i)]
    if b.get('isbn') in isbns:   # try the build's pick first
        isbns.remove(b['isbn'])
        isbns.insert(0, b['isbn'])
    for i in isbns[:8]:
        e = isbn_edition(i, cache)
        # the edition's own title must match too: Open Library sometimes files another book's edition under a work
        # (a "When China Rules the World" edition sits in the work for "Packing the Court")
        if e and same_title(e.get('title'), b['title']):
            return i
    return None


def google_cover(b, isbn, cache):
    """Google Books front cover for the ISBN, if the volume has this title and author (cached)."""
    if isbn not in cache:
        try:
            url = 'https://www.googleapis.com/books/v1/volumes?' + urllib.parse.urlencode(
                {'q': 'isbn:' + isbn, 'fields': 'items(id,volumeInfo(title,authors,imageLinks))'})
            cache[isbn] = [{'id': it['id'], 'title': it['volumeInfo'].get('title'), 'authors': it['volumeInfo'].get('authors') or [],
                            'img': bool(it['volumeInfo'].get('imageLinks'))} for it in get_json(url).get('items') or []]
        except Exception:
            return None   # quota or network: try again next run
    last = surname(b).lower()
    for v in cache[isbn]:
        if v['img'] and same_title(v['title'], b['title']) and any(last in a.lower() for a in v['authors']):
            return f'https://books.google.com/books/content?id={v["id"]}&printsec=frontcover&img=1&zoom=0&source=gbs_api'
    return None


def candidates(b, isbn, gcache):
    out = []
    cur = b.get('cover') or ''
    # only the build's own picks (the work's Open Library cover, or a Goodreads image) or images derived from the verified ISBN
    if cur and ('/b/id/' in cur or 'gr-assets.com' in cur or (isbn and (isbn in cur or (isbn10(isbn) or '#') in cur))):
        out.append(cur)
        if 'gr-assets.com' in cur:
            out.append(re.sub(r'\._[A-Z]{2}\d+_(?=\.)', '', cur))
    if isbn:
        out.append(f'https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false')
        g = google_cover(b, isbn, gcache)
        if g:
            out.append(g)
        i10 = isbn10(isbn)
        if i10:
            out.append(f'https://images-na.ssl-images-amazon.com/images/P/{i10}.01._SCLZZZZZZZ_.jpg')
    seen = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def load(path):
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}


def main():
    path = 'docs/data/books.js'
    raw = open(path, encoding='utf-8').read()
    prefix = raw[:raw.index('=') + 1]
    D = json.loads(raw[raw.index('=') + 1:].rstrip().rstrip(';'))
    books = D if isinstance(D, list) else D['books']
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache, icache, gcache = load(CACHE), load(ISBN_CACHE), load(GOOGLE_CACHE)
    manual = {}
    if os.path.exists(MANUAL):
        for line in open(MANUAL, encoding='utf-8'):
            if line.strip() and not line.startswith('#'):
                f = line.rstrip('\n').split('\t')
                manual[f[0]] = f[1].strip()
    changed = dropped_isbn = 0
    for n, b in enumerate(books, 1):
        isbn = verified_isbn(b, icache)
        if isbn != b.get('isbn'):
            if not isbn:
                dropped_isbn += 1
            print(f"  isbn {b['id'][:40]:40} {b.get('isbn')} -> {isbn}")
        if isbn:
            b['isbn'] = isbn
            b['amazon'] = f'https://www.amazon.com/s?k={isbn}&i=stripbooks'
        elif b.get('isbn'):
            del b['isbn']
            b['amazon'] = 'https://www.amazon.com/s?k=' + urllib.parse.quote_plus(f"{b['title'].split(':')[0]} {surname(b)}") + '&i=stripbooks'
        res = {}
        for u in candidates(b, isbn, gcache):
            if u not in cache:
                cache[u] = measure(u)
                time.sleep(0.3)
            res[u] = cache[u]
        good = [(u, r) for u, r in res.items() if r]
        before = b.get('cover')
        if good:
            best_u, _ = max(good, key=lambda x: (x[1]['h'], x[0] == before))
            b['cover'] = best_u.replace('?default=false', '')
        else:
            b.pop('cover', None)
        if b['id'] in manual:
            if manual[b['id']] == 'none':
                b.pop('cover', None)
            else:
                b['cover'] = manual[b['id']]
        if b.get('cover') != before:
            changed += 1
        if n % 40 == 0:
            for c, p in ((cache, CACHE), (icache, ISBN_CACHE), (gcache, GOOGLE_CACHE)):
                json.dump(c, open(p, 'w', encoding='utf-8'))
            print(f'{n}/{len(books)}', flush=True)
    for c, p in ((cache, CACHE), (icache, ISBN_CACHE), (gcache, GOOGLE_CACHE)):
        json.dump(c, open(p, 'w', encoding='utf-8'))
    open(path, 'w', encoding='utf-8').write(prefix + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + ';')
    hs = sorted((cache.get(b.get('cover')) or {}).get('h', 0) for b in books)
    print(f'{changed} covers changed; {dropped_isbn} unverifiable ISBNs dropped; median height {hs[len(hs) // 2]}px; '
          f'{sum(1 for b in books if not b.get("cover"))} books use the placeholder')


if __name__ == '__main__':
    main()
