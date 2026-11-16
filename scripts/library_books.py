"""Full texts for the library reader, from Wikisource (public-domain texts; Wikisource transcriptions are free to reuse,
CC BY-SA, credited on every page of the reader).

For each work in BOOKS: the root page's table of contents is read in order, each chapter page is fetched through the
MediaWiki API (one request every ~2 seconds; cached in data/raw/library/<id>/), headers, footnote markers and editing
links are dropped, and paragraphs and headings are kept. Output, one small file per chapter so the reader loads only
what is read:
  docs/data/lib/<id>.js        window.LIB_BOOKS[id] = {id, title, author, year, src, srcName, license, toc: [[title, words], ...]}
  docs/data/lib/<id>-<n>.js    window.LIB_CHS['<id>-<n>'] = {id, n, t, b: [[kind, text], ...]}  kind: 'h' heading, 'p' paragraph
  docs/data/lib-index.js       window.LIB_INDEX = [{id, title, author, year, corner, chapters, words}, ...]
Run from the repo root:  python scripts/library_books.py [book id ...]
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (educational static site)'}
RAW = 'data/raw/library'
OUT = 'docs/data/lib'
BOOKS = [
    # id, title, author, year, Wikisource root page, Originalist's Corner source id it stands for
    ('story', 'Commentaries on the Constitution of the United States', 'Joseph Story', '1833',
     'Commentaries on the Constitution of the United States', 'story'),
    ('blackstone', 'Commentaries on the Laws of England', 'William Blackstone', '1765–1769',
     'Commentaries on the Laws of England', 'blackstone'),
    ('locke', 'Two Treatises of Government', 'John Locke', '1689 (1764 ed.)', 'Two Treatises of Government (1764)', 'locke'),
]


def api(**p):
    p.update(format='json', formatversion=2)
    url = 'https://en.wikisource.org/w/api.php?' + urllib.parse.urlencode(p)
    for a in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90))
            time.sleep(2)
            return r
        except Exception as e:
            if getattr(e, 'code', 0) in (429, 503):
                time.sleep(20 * (a + 1))
                continue
            raise
    raise RuntimeError('Wikisource unavailable')


def page_html(bid, title):
    os.makedirs(f'{RAW}/{bid}', exist_ok=True)
    p = f"{RAW}/{bid}/{re.sub(r'[^A-Za-z0-9]+', '_', title)[-150:]}.html"
    if not os.path.exists(p):
        r = api(action='parse', page=title, prop='text', disableeditsection=1, redirects=1)
        open(p, 'w', encoding='utf-8').write(r.get('parse', {}).get('text', ''))
    return open(p, encoding='utf-8').read()


def toc(bid, root):
    """Chapter pages linked from the root page, in the order they appear; book-level pages are expanded the same way."""
    out, seen = [], set()

    def walk(title, depth):
        h = page_html(bid, title)
        for m in re.finditer(r'<a href="/wiki/([^"#?]+)"[^>]*>', h):
            t = urllib.parse.unquote(m.group(1)).replace('_', ' ')
            if not t.startswith(root + '/') or t in seen or re.search(r'/(Index|Contents|Table of Contents)$', t):
                continue
            seen.add(t)
            sub = page_html(bid, t)
            # a "Book I" page that is only a list of its chapters: follow it instead of keeping it
            kids = sum(1 for k in re.finditer(r'<a href="/wiki/([^"#?]+)"', sub) if urllib.parse.unquote(k.group(1)).replace('_', ' ').startswith(t + '/'))
            if depth < 2 and kids >= 2 and len(text_blocks(sub)) < 12:
                walk(t, depth + 1)
            else:
                out.append(t)
    walk(root, 0)
    return out


DROP = re.compile(r'<(?:sup class="reference|span class="mw-editsection|div class="(?:wst-header|ws-header|ws-noexport|licenseContainer|wst-license|mw-references|navbox))[^>]*>.*?</(?:sup|span|div)>', re.S)


def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def text_blocks(h):
    h = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', h, flags=re.S)
    h = re.sub(r'<table[^>]*>.*?</table>', '', h, flags=re.S)
    h = re.sub(r'<div[^>]*class="[^"]*(?:wst-header|ws-header|ws-noexport|licenseContainer|wst-license|reflist|references)[^"]*"[^>]*>.*?</div>\s*</div>', '', h, flags=re.S)
    h = re.sub(r'<sup[^>]*class="[^"]*reference[^"]*"[^>]*>.*?</sup>', '', h, flags=re.S)
    h = re.sub(r'<span[^>]*class="[^"]*(?:pagenum|ws-pagenum|mw-editsection)[^"]*"[^>]*>.*?</span>', '', h, flags=re.S)
    h = re.sub(r'<ol class="references">.*?</ol>', '', h, flags=re.S)
    out = []
    for m in re.finditer(r'<(h[2-5]|p|blockquote)[^>]*>(.*?)</\1>', h, re.S):
        t = clean(m.group(2))
        if not t or re.fullmatch(r'[\W\d]{0,4}', t):
            continue
        if re.fullmatch(r'Layout \d+', t):
            continue
        letters = [c for c in t if c.isalpha()]
        caps = letters and sum(c.isupper() for c in letters) > 0.85 * len(letters) and len(t) <= 120
        out.append(['h' if m.group(1).startswith('h') or caps else 'p', t])
    # the short title lines that open a chapter ("Book the first.", "Chapter the first.", "Of the Rights of Persons.")
    for x in out:
        if len(x[1]) > 140:
            break
        if len(x[1]) <= 90:
            x[0] = 'h'
    return out


def smart_title(s):
    small = {'a', 'an', 'the', 'of', 'and', 'or', 'in', 'on', 'to', 'for', 'by', 'at', 'as', 'with', 'from'}
    w = s.lower().rstrip('.').split()
    return ' '.join(x if i and x in small else x[:1].upper() + x[1:] for i, x in enumerate(w))


def build(bid, title, author, year, root, corner):
    chapters = toc(bid, root)
    if not chapters:
        chapters = [root]
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.startswith(bid + '-') or f == bid + '.js':
            os.remove(os.path.join(OUT, f))
    tocout, n, words = [], 0, 0
    for t in chapters:
        b = text_blocks(page_html(bid, t))
        w = sum(len(x[1].split()) for x in b)
        if w < 150:
            continue
        name = t[len(root) + 1:] if t.startswith(root + '/') else title
        name = name.replace('/', ' · ')
        if re.search(r'Chapter \d+$', name):          # "Book 3 · Chapter 8" -> "Book 3 · Chapter 8: The Legislature"
            hs = [x[1] for x in b[:6] if x[0] == 'h']
            k = next((i for i, h in enumerate(hs) if re.match(r'^CHAPTER\b', h, re.I)), None)
            if k is not None and k + 1 < len(hs) and not re.match(r'^(CHAPTER|BOOK)\b', hs[k + 1], re.I):
                name += ': ' + smart_title(hs[k + 1])
        n += 1
        words += w
        tocout.append([name, w])
        open(f'{OUT}/{bid}-{n}.js', 'w', encoding='utf-8').write('window.LIB_CHS=window.LIB_CHS||{};window.LIB_CHS[' + json.dumps(f'{bid}-{n}') + ']=' + json.dumps({'id': bid, 'n': n, 't': name, 'b': b}, ensure_ascii=False, separators=(',', ':')) + ';')
    src = 'https://en.wikisource.org/wiki/' + urllib.parse.quote(root.replace(' ', '_'))
    meta = {'id': bid, 'title': title, 'author': author, 'year': year, 'src': src, 'srcName': 'Wikisource',
            'license': 'Public-domain text; Wikisource transcription, CC BY-SA 4.0', 'corner': corner, 'toc': tocout}
    open(f'{OUT}/{bid}.js', 'w', encoding='utf-8').write('window.LIB_BOOKS=window.LIB_BOOKS||{};window.LIB_BOOKS[' + json.dumps(bid) + ']=' + json.dumps(meta, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{bid}: {n} chapters, {words:,} words', flush=True)
    return {'id': bid, 'title': title, 'author': author, 'year': year, 'corner': corner, 'chapters': n, 'words': words, 'srcName': 'Wikisource'}


def main():
    only = sys.argv[1:]
    idx_path = 'docs/data/lib-index.js'
    index = {}
    if os.path.exists(idx_path):
        s = open(idx_path, encoding='utf-8').read()
        index = {x['id']: x for x in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))}
    for b in BOOKS:
        if only and b[0] not in only:
            continue
        index[b[0]] = build(*b)
    open(idx_path, 'w', encoding='utf-8').write('window.LIB_INDEX=' + json.dumps(list(index.values()), ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
