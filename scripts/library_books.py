"""Full texts for the library reader, from Wikisource and Project Gutenberg (public-domain texts; Wikisource
transcriptions are CC BY-SA, Project Gutenberg texts are public domain in the U.S.; the source is credited on every page
of the reader).

Wikisource works (WIKISOURCE): the root page's table of contents is read in order, each chapter page is fetched through
the MediaWiki API (one request every ~2 seconds; cached in data/raw/library/<id>/), headers, footnote markers and
editing links are dropped, and paragraphs and headings are kept.
Project Gutenberg works (GUTENBERG): the HTML edition of each eBook is downloaded once (from gutenberg.org, or from one
of Project Gutenberg's official mirrors when the main site is down; cached in data/raw/library/gutenberg/<n>.html), the
licence header and footer, tables of contents, footnotes and page numbers are dropped, and the text is split into parts
at its chapter headings.
Output, one small file per part so the reader loads only what is read:
  docs/data/lib/<id>.js        window.LIB_BOOKS[id] = {id, title, author, year, src, srcName, license, toc: [[title, words], ...]}
  docs/data/lib/<id>-<n>.js    window.LIB_CHS['<id>-<n>'] = {id, n, t, b: [[kind, text], ...]}  kind: 'h' heading, 'p' paragraph
  docs/data/lib-index.js       window.LIB_INDEX = [{id, title, author, year, corner, chapters, words, srcName}, ...]
Run from the repo root:  python scripts/library_books.py [book id ...]
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (educational static site)'}
RAW = 'data/raw/library'
OUT = 'docs/data/lib'
WIKISOURCE = [
    # id, title, author, year, Wikisource root page, Originalist's Corner source id it stands for ('' if none)
    ('story', 'Commentaries on the Constitution of the United States', 'Joseph Story', '1833',
     'Commentaries on the Constitution of the United States', 'story'),
    ('blackstone', 'Commentaries on the Laws of England', 'William Blackstone', '1765–1769',
     'Commentaries on the Laws of England', 'blackstone'),
    ('locke', 'Two Treatises of Government', 'John Locke', '1689 (1764 ed.)', 'Two Treatises of Government (1764)', 'locke'),
    ('spirit-of-laws', 'The Spirit of Laws', 'Montesquieu', '1748 (Nugent trans., 1758 ed.)', 'The Spirit of Laws (1758)', ''),
    ('notes-virginia', 'Notes on the State of Virginia', 'Thomas Jefferson', '1785 (1802 ed.)', 'Notes on the State of Virginia (1802)', ''),
    ('cato', "Cato's Letters", 'John Trenchard and Thomas Gordon', '1720–1723', "Cato's Letters", '', "Cato's Letter No. "),
    ('otis', 'The Rights of the British Colonies Asserted and Proved', 'James Otis', '1764',
     'The Rights of the British Colonies Asserted and Proved', ''),
    ('thoughts-government', 'Thoughts on Government', 'John Adams', '1776', 'Thoughts on Government', ''),
    ('summary-view', 'A Summary View of the Rights of British America', 'Thomas Jefferson', '1774',
     'A Summary View of the Rights of British America', ''),
]
GUTENBERG = [
    # id, title, author, year, eBook numbers (volumes in order), Corner source id, options
    ('madison', 'The Journal of the Debates in the Convention which Framed the Constitution', 'James Madison',
     '1787 (Hunt ed., 1908)', [40861, 41095], 'madison',
     {'title_re': r'^((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[\s,]+\w+\.?\s+\d+(?:st|nd|rd|th|d)?)'}),
    ('tocqueville', 'Democracy in America', 'Alexis de Tocqueville', '1835–1840 (Reeve trans.)', [815, 816], '', {}),
    ('common-sense', 'Common Sense', 'Thomas Paine', '1776', [147], '', {}),
    ('farmer-letters', 'Letters from a Farmer in Pennsylvania', 'John Dickinson', '1767–1768', [47111], '', {}),
    ('novanglus', 'Novanglus and Massachusettensis', 'John Adams and Daniel Leonard', '1774–1775', [45205], '', {}),
    ('grotius', 'The Rights of War and Peace', 'Hugo Grotius', '1625 (Campbell trans.)', [46564], '', {}),
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


def toc(bid, root, prefix=None):
    """Chapter pages linked from the root page, in the order they appear; book-level pages are expanded the same way."""
    out, seen = [], set()

    def walk(title, depth):
        h = page_html(bid, title)
        for m in re.finditer(r'<a href="/wiki/([^"#?]+)"[^>]*>', h):
            t = urllib.parse.unquote(m.group(1)).replace('_', ' ')
            if not t.startswith(prefix or root + '/') or t in seen or re.search(r'/(Index|Contents|Table of Contents)$', t):
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
    roman = re.compile(r'^(?=[ivxlc]+\W*$)(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})\W*$')
    return ' '.join(x.upper() if roman.match(x) else x if i and x in small else x[:1].upper() + x[1:] for i, x in enumerate(w))


def write_book(meta, parts):
    """parts: [(name, blocks)]; writes the per-part files and the book file, returns the index entry."""
    bid = meta['id']
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if re.fullmatch(re.escape(bid) + r'(-\d+)?\.js', f):
            os.remove(os.path.join(OUT, f))
    tocout, words = [], 0
    for n, (name, b0) in enumerate(parts, 1):
        b = []
        for kind, t in b0:
            t = t.replace('ſ', 's')            # the long s of 18th-century printing
            # a paragraph cut by a page break (it goes on in lower case after one that doesn't end a sentence)
            if b and kind == 'p' and b[-1][0] == 'p' and re.match(r'^[a-z]', t) and not re.search(r'[.!?:"”’)\]]$', b[-1][1]):
                b[-1][1] += ' ' + t
                continue
            b.append([kind, t])
        w = sum(len(x[1].split()) for x in b)
        words += w
        tocout.append([name, w])
        open(f'{OUT}/{bid}-{n}.js', 'w', encoding='utf-8').write('window.LIB_CHS=window.LIB_CHS||{};window.LIB_CHS[' + json.dumps(f'{bid}-{n}') + ']=' + json.dumps({'id': bid, 'n': n, 't': name, 'b': b}, ensure_ascii=False, separators=(',', ':')) + ';')
    meta = dict(meta, toc=tocout)
    open(f'{OUT}/{bid}.js', 'w', encoding='utf-8').write('window.LIB_BOOKS=window.LIB_BOOKS||{};window.LIB_BOOKS[' + json.dumps(bid) + ']=' + json.dumps(meta, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{bid}: {len(parts)} parts, {words:,} words', flush=True)
    return {'id': bid, 'title': meta['title'], 'author': meta['author'], 'year': meta['year'], 'corner': meta['corner'],
            'chapters': len(parts), 'words': words, 'srcName': meta['srcName']}


def build(bid, title, author, year, root, corner, prefix=None):
    chapters = toc(bid, root, prefix) or [root]
    parts = []
    for t in chapters:
        b = text_blocks(page_html(bid, t))
        if sum(len(x[1].split()) for x in b) < 150:
            continue
        name = t[len(root) + 1:] if t.startswith(root + '/') else t[len(prefix) - 4:] if prefix and t.startswith(prefix) else title
        name = name.replace('/', ' · ')
        if re.search(r'Chapter \d+$', name):          # "Book 3 · Chapter 8" -> "Book 3 · Chapter 8: The Legislature"
            hs = [x[1] for x in b[:6] if x[0] == 'h']
            k = next((i for i, h in enumerate(hs) if re.match(r'^CHAPTER\b', h, re.I)), None)
            if k is not None and k + 1 < len(hs) and not re.match(r'^(CHAPTER|BOOK)\b', hs[k + 1], re.I):
                name += ': ' + smart_title(hs[k + 1])
        parts.append((name, b))
    src = 'https://en.wikisource.org/wiki/' + urllib.parse.quote(root.replace(' ', '_'))
    return write_book({'id': bid, 'title': title, 'author': author, 'year': year, 'src': src, 'srcName': 'Wikisource',
                       'license': 'Public-domain text; Wikisource transcription, CC BY-SA 4.0', 'corner': corner}, parts)


# ---------------------------------------------------------------------------------------------- Project Gutenberg
MIRRORS = ['https://www.gutenberg.org/cache/epub/{n}/pg{n}-images.html',
           'http://mirrors.xmission.com/gutenberg/{p}/{n}/{n}-h/{n}-h.htm',
           'https://gutenberg.pglaf.org/{p}/{n}/{n}-h/{n}-h.htm']


def gutenberg_html(n):
    os.makedirs(f'{RAW}/gutenberg', exist_ok=True)
    path = f'{RAW}/gutenberg/{n}.html'
    if not os.path.exists(path):
        s = str(n)
        p = '/'.join(s[:-1]) if len(s) > 1 else '0'
        for m in MIRRORS:
            try:
                data = urllib.request.urlopen(urllib.request.Request(m.format(n=n, p=p), headers=UA), timeout=120).read()
                if b'START OF TH' in data:
                    open(path, 'wb').write(data)
                    break
            except Exception as e:
                print(f'  {n}: {m.split("/")[2]}: {e}', flush=True)
            time.sleep(2)
        else:
            raise RuntimeError(f'eBook {n}: no copy found')
    raw = open(path, 'rb').read()
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000])
    enc = (m.group(1).decode() if m else 'utf-8').lower()
    try:
        return raw.decode(enc)
    except (LookupError, UnicodeDecodeError):
        return raw.decode('cp1252', errors='replace')


def drop_elements(h, tag, cls):
    """Remove every <tag class="...cls..."> element with its contents (nesting-aware)."""
    opener = re.compile(r'<%s\b[^>]*class="[^"]*\b(?:%s)\b[^"]*"[^>]*>' % (tag, cls), re.I)
    tok = re.compile(r'<(/?)%s\b[^>]*>' % tag, re.I)
    while True:
        m = opener.search(h)
        if not m:
            return h
        depth, i = 1, m.end()
        while depth:
            t = tok.search(h, i)
            if not t:
                i = len(h)
                break
            depth += -1 if t.group(1) else 1
            i = t.end()
        h = h[:m.start()] + h[i:]


def gutenberg_blocks(h):
    a = re.search(r'\*\*\* ?START OF TH[^*]*\*\*\*', h)
    z = re.search(r'\*\*\* ?END OF TH[^*]*\*\*\*', h)
    h = h[a.end() if a else 0: z.start() if z else len(h)]
    h = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', h, flags=re.S | re.I)
    h = re.sub(r'<table[^>]*>.*?</table>', '', h, flags=re.S | re.I)
    for tag in ('div', 'p', 'span'):
        h = drop_elements(h, tag, 'footnotes?|pagenum|toc|transnote|tnote|figcenter|caption|blockquot-toc')
    h = re.sub(r'<a\b[^>]*(?:fnanchor|#Footnote|#FN|#fn)[^>]*>.*?</a>', '', h, flags=re.S | re.I)
    h = re.sub(r'<br\s*/?>', ' ', h, flags=re.I)
    out = []
    for m in re.finditer(r'<(h[1-4]|p)\b[^>]*>(.*?)</\1>', h, re.S | re.I):
        t = clean(m.group(2))
        t = re.sub(r'\[(?:\d+|[a-z])\]', '', t).strip()
        if not t or re.fullmatch(r'[\W\d]{0,4}', t):
            continue
        out.append([m.group(1).lower(), t])
    return out


SKIP_PART = re.compile(r'^(contents|table of contents|list of|index|footnotes?|notes?|illustrations|transcriber|errata|advertisements?)\b', re.I)


def part_title(t, opt):
    t = re.sub(r'\s*[—–-]+\s*$', '', t).strip()
    if opt.get('title_re'):
        m = re.match(opt['title_re'], t)
        if m:
            return m.group(1)
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > 0.85 * len(letters):
        t = smart_title(t)
    if len(t) > 80:
        t = t[:78].rsplit(' ', 1)[0] + '…'
    return t.rstrip('.')


def build_gutenberg(bid, title, author, year, nums, corner, opt):
    parts = []
    for v, num in enumerate(nums, 1):
        blocks = gutenberg_blocks(gutenberg_html(num))
        levels = [x[0] for x in blocks if x[0] != 'p']
        # split at the highest heading level used at least three times (h1 is usually only the title page)
        split = next((l for l in ('h1', 'h2', 'h3', 'h4') if levels.count(l) >= 3), None)
        cur, name, vparts = [], 'Front matter', []
        for kind, t in blocks:
            if kind == split:
                vparts.append((name, cur))
                cur, name = [], part_title(t, opt)
                cur.append(['h', t])
            else:
                cur.append(['p' if kind == 'p' else 'h', t])
        vparts.append((name, cur))
        merged = []
        for name, b in vparts:
            w = sum(len(x[1].split()) for x in b)
            if SKIP_PART.match(name) or not b:
                continue
            # a part that is only headings or a few lines (a "Book I" divider, a half-title) joins the next one
            if merged and merged[-1][2] < 120:
                pn, pb, pw = merged.pop()
                name, b, w = (pn if pn != 'Front matter' else name), pb + b, pw + w
            merged.append((name, b, w))
        if merged and merged[-1][2] < 120 and len(merged) > 1:
            pn, pb, pw = merged.pop()
            merged[-1] = (merged[-1][0], merged[-1][1] + pb, merged[-1][2] + pw)
        for name, b, w in merged:
            if w < 60:
                continue
            parts.append(((f'Vol. {"I" * v if v < 4 else v} · ' if len(nums) > 1 else '') + name, b))
    src = f'https://www.gutenberg.org/ebooks/{nums[0]}'
    lic = 'Public-domain text from Project Gutenberg (eBook' + ('s ' if len(nums) > 1 else ' ') + ', '.join(f'#{n}' for n in nums) + ')'
    return write_book({'id': bid, 'title': title, 'author': author, 'year': year, 'src': src, 'srcName': 'Project Gutenberg',
                       'license': lic, 'corner': corner}, parts)


def main():
    only = sys.argv[1:]
    idx_path = 'docs/data/lib-index.js'
    index = {}
    if os.path.exists(idx_path):
        s = open(idx_path, encoding='utf-8').read()
        index = {x['id']: x for x in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))}
    for b in WIKISOURCE:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    for b in GUTENBERG:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build_gutenberg(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    open(idx_path, 'w', encoding='utf-8').write('window.LIB_INDEX=' + json.dumps(list(index.values()), ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
