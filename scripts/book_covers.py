"""Pick the sharpest available cover image for each book in docs/data/books.js.

Candidates per book: the current cover; Open Library's large cover for the book's ISBN and for its edition (OLID);
Google Books' front cover at full zoom; and Amazon's catalog image for the ISBN-10. Each candidate is downloaded and
measured (pixel size read from the JPEG/PNG/GIF header), placeholders are rejected (tiny images, blank "no cover"
images, or shapes nothing like a book cover), and the tallest real cover wins; ties keep the current source.
Results are cached in data/raw/books/covers.json. Run from the repo root:  python scripts/book_covers.py
"""
import json, os, re, struct, time, urllib.parse, urllib.request

CACHE = 'data/raw/books/covers.json'
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


def google_cover(isbn):
    try:
        url = 'https://www.googleapis.com/books/v1/volumes?' + urllib.parse.urlencode({'q': 'isbn:' + isbn, 'fields': 'items(id,volumeInfo/imageLinks)'})
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        for it in d.get('items') or []:
            if (it.get('volumeInfo') or {}).get('imageLinks'):
                return f'https://books.google.com/books/content?id={it["id"]}&printsec=frontcover&img=1&zoom=0&source=gbs_api'
    except Exception:
        pass
    return None


def candidates(b):
    out = []
    if b.get('cover'):
        out.append(b['cover'])
        if 'gr-assets.com' in b['cover']:
            out.append(re.sub(r'\._[A-Z]{2}\d+_(?=\.)', '', b['cover']))
    isbn = re.sub(r'\D', '', b.get('isbn') or '')
    if isbn:
        out.append(f'https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false')
    if b.get('ol'):
        olid = re.search(r'(OL\d+[MW])', str(b['ol']))
        if olid and olid.group(1).endswith('M'):
            out.append(f'https://covers.openlibrary.org/b/olid/{olid.group(1)}-L.jpg?default=false')
    if isbn:
        g = google_cover(isbn)
        if g:
            out.append(g)
        i10 = isbn10(isbn)
        if i10:
            out.append(f'https://images-na.ssl-images-amazon.com/images/P/{i10}.01._SCLZZZZZZZ_.jpg')
    seen = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def main():
    path = 'docs/data/books.js'
    raw = open(path, encoding='utf-8').read()
    prefix = raw[:raw.index('=') + 1]
    D = json.loads(raw[raw.index('=') + 1:].rstrip().rstrip(';'))
    books = D if isinstance(D, list) else D['books']
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    changed = upgraded = 0
    for n, b in enumerate(books, 1):
        cands = candidates(b)
        res = {}
        for u in cands:
            if u not in cache:
                cache[u] = measure(u)
                time.sleep(0.3)
            res[u] = cache[u]
        good = [(u, r) for u, r in res.items() if r]
        cur = res.get(b.get('cover'))
        if good:
            best_u, best = max(good, key=lambda x: (x[1]['h'], x[0] == b.get('cover')))
            if best_u != b.get('cover') and (not cur or best['h'] >= cur['h'] * 1.25):
                print(f"  {b.get('title', '')[:60]:60} {cur['h'] if cur else 'none':>5} -> {best['h']}px")
                b['cover'] = best_u.replace('?default=false', '')
                changed += 1
                upgraded += 1 if cur else 0
        if n % 40 == 0:
            json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
            print(f'{n}/{len(books)}', flush=True)
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
    open(path, 'w', encoding='utf-8').write(prefix + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + ';')
    hs = sorted((cache.get(b.get('cover')) or {}).get('h', 0) for b in books)
    print(f'{changed} covers replaced ({upgraded} sharper, {changed - upgraded} newly found); median height now {hs[len(hs) // 2]}px; {sum(1 for h in hs if 0 < h < 400)} still under 400px; {sum(1 for h in hs if not h)} without a measurable cover')


if __name__ == '__main__':
    main()
