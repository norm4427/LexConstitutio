"""Government texts for the library reader (U.S. government works, not subject to copyright):
  conan          the Constitution Annotated (Constitution of the United States of America: Analysis and Interpretation,
                 Congressional Research Service, 2022 ed.), every essay, grouped into parts by clause; from
                 data/conan_essays.json (scripts/conan_extract.py, from the GovInfo PDFs in data/raw/conan/)
  crs-sidebars   every CRS Legal Sidebar downloaded by scripts/crs_fetch.py (data/raw/crs/html/LSB*.html, from
                 EveryCRSReport.com's mirror), newest first, page headers and footers removed; the author line and the CRS
                 disclaimer are kept, since CRS allows its reports to be reproduced in their entirety
Writes the same files as scripts/library_books.py (docs/data/lib/<id>.js, <id>-<n>.js) and adds the works to
docs/data/lib-index.js with shelf "gov" (the library page lists them apart from the founding-era texts).
Run from the repo root:  python scripts/library_gov.py [conan] [crs-sidebars]
"""
import csv, html, json, os, re, sys

sys.path.insert(0, 'scripts')
from library_books import write_book  # noqa: E402

ROMAN = 'I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI XXII XXIII XXIV XXV XXVI XXVII'.split()
ORD = ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth', 'Eleventh', 'Twelfth',
       'Thirteenth', 'Fourteenth', 'Fifteenth', 'Sixteenth', 'Seventeenth', 'Eighteenth', 'Nineteenth', 'Twentieth',
       'Twenty-First', 'Twenty-Second', 'Twenty-Third', 'Twenty-Fourth', 'Twenty-Fifth', 'Twenty-Sixth', 'Twenty-Seventh']


def strip(s):
    s = html.unescape(re.sub(r'<[^>]+>', '', s)).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def clause_label(pre):
    if pre == 'Intro':
        return 'Introduction'
    if pre in ('Pre', 'Preamble'):
        return 'Preamble'
    m = re.match(r'Art([IVX]+)(?:\.S(\d+))?(?:\.C(\d+))?$', pre)
    if m:
        return 'Article ' + m.group(1) + (f', Section {m.group(2)}' if m.group(2) else '') + (f', Clause {m.group(3)}' if m.group(3) else '')
    m = re.match(r'Amdt(\d+)(?:\.S(\d+))?(?:\.C(\d+))?$', pre)
    if m:
        return ORD[int(m.group(1)) - 1] + ' Amendment' + (f', Section {m.group(2)}' if m.group(2) else '') + (f', Clause {m.group(3)}' if m.group(3) else '')
    return pre


def topic(title):
    t = re.sub(r'^(Overview of( the)?|Overview:?)\s+', '', title).strip()
    return t[:1].upper() + t[1:]


def conan():
    E = json.load(open('data/conan_essays.json', encoding='utf-8'))
    head = re.compile(r'^(Intro|Pre(?:amble)?|Art[IVX]+(?:\.S\d+)?(?:\.C\d+)?|Amdt\d+(?:\.S\d+)?(?:\.C\d+)?)')
    groups, order = {}, []
    for e in E:
        m = head.match(e['id'])
        pre = m.group(1) if m else e['id']
        if pre not in groups:
            groups[pre] = []
            order.append(pre)
        groups[pre].append(e)
    words = lambda es: sum(len(' '.join(x['paras']).split()) for x in es)
    parts = []

    def blocks(es):
        out = []
        for e in es:
            out.append(['h', f"{e['id']} {strip(e['title'])}"])
            out.extend(['p', strip(p)] for p in e['paras'] if strip(p))
        return out

    def add(pre, es, label, depth=0):
        """A clause's essays as one part; a long clause (the Commerce Clause, Due Process...) is split at its essays' next
        level, again if a piece is still long."""
        if words(es) > 15000 and depth < 3:
            sub, sorder = {}, []
            for e in es:
                rest = e['id'][len(pre):].lstrip('.').split('.')
                k = rest[0] if rest and rest[0] else ''
                if k not in sub:
                    sub[k] = []
                    sorder.append(k)
                sub[k].append(e)
            if len(sorder) > 1:
                for k in sorder:
                    ses = sub[k]
                    t = topic(strip(ses[0]['title']))
                    if k and words(ses) > 15000:
                        add(pre + '.' + k, ses, f'{label} · {t}', depth + 1)
                    else:
                        parts.append((f'{label} · {t}', blocks(ses)))
                return
        first = next((x for x in es if x['paras']), es[0])
        t = topic(strip(first['title']))
        if t.startswith(label):
            t = t[len(label):].lstrip(' ,:')
        parts.append((label + (f': {t}' if t and depth == 0 and label not in ('Introduction', 'Preamble') else ''), blocks(es)))

    for pre in order:
        add(pre, groups[pre], clause_label(pre))
    # drop parts with no text (title-only essays)
    parts = [(n, b) for n, b in parts if sum(1 for x in b if x[0] == 'p')]
    # a very short piece (a one-paragraph overview) joins the next piece of the same clause
    merged = []
    for n, b in parts:
        if merged:
            pn, pb = merged[-1]
            if sum(len(x[1].split()) for x in pb) < 300 and pn.split(' · ')[0] == n.split(' · ')[0] and ' · ' in n:
                merged[-1] = (pn, pb + b)
                continue
        merged.append((n, b))
    parts = merged
    # essay id -> part, so other pages can link to an essay in the reader (#/library/book/conan/e/<essay id>)
    where = {}
    for n, (_, b) in enumerate(parts, 1):
        for x in b:
            if x[0] == 'h' and re.match(r'^(Intro|Pre|Art|Amdt)\S*\.', x[1] + '.'):
                where[x[1].split(' ', 1)[0]] = n
    return write_book({'essays': where, 'id': 'conan', 'title': 'The Constitution Annotated', 'author': 'Congressional Research Service',
                       'year': '2022 ed.', 'src': 'https://constitution.congress.gov/', 'srcName': 'Congress.gov (GovInfo print edition)',
                       'license': 'Constitution of the United States of America: Analysis and Interpretation, Congressional Research Service, Library of Congress (2022 ed.); a U.S. government work, in the public domain',
                       'corner': '', 'shelf': 'gov'}, parts)


FURNITURE = re.compile(r'^(Congressional Research Service|https?://crsreports\.congress\.gov|Legal Sidebar\w?|LSB\d+\w*( · .*)?|\d{1,3}|'
                       r'Prepared for Members and Comm?i?t?t?e?e?s? ?o?f? ?C?o?n?g?r?e?s?s?|ittees of Congress|Updated .{0,30}\d{4})$', re.I)
DATE = re.compile(r'^((?:Updated )?(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})\s*(.*)$')


def sidebar(path):
    h = open(path, encoding='utf-8', errors='replace').read()
    h = re.sub(r'<img[^>]*>', '', h)
    h = re.sub(r'<a\b[^>]*>|</a>', '', h)
    h = re.sub(r'<hr/?>', '\n', h)
    lines = []
    for raw in h.split('\n'):
        bold = bool(re.fullmatch(r'\s*<b>.*</b>\s*(<br/>\s*)*', raw.strip(), re.S))
        t = strip(raw.replace('<br/>', ' '))
        if not t or FURNITURE.match(t) or re.fullmatch(r'\(LSB\d+\w*\)', t):
            continue
        lines.append([bold, t])
    # the text starts at the date line (the title above it is in the report list)
    k = next((i for i, (_, t) in enumerate(lines) if DATE.match(t)), None)
    date = ''
    if k is not None:
        date, rest = DATE.match(lines[k][1]).groups()
        lines = ([[False, rest]] if rest else []) + lines[k + 1:]
    out = []
    for bold, t in lines:
        if out and out[-1][0] == 'p' and not bold and not re.search(r'[.?!:;”"’)\]]$', out[-1][1]) and re.match(r'^[a-z(“"0-9—–-]', t):
            out[-1][1] += ' ' + t           # a paragraph broken by a page break
            continue
        kind = 'h' if bold and len(t) < 140 else 'p'
        out.append([kind, t])
    # keep "Author Information" and the disclaimer together at the end, drop stray blanks
    return date, [x for x in out if x[1] and x[1] != '*']


def sidebars():
    meta = {r['number']: r for r in csv.DictReader(open('data/raw/crs/reports.csv', encoding='utf-8'))}
    items = []
    for f in sorted(os.listdir('data/raw/crs/html')):
        if not f.startswith('LSB'):
            continue
        num = f[:-5]
        r = meta.get(num)
        date, b = sidebar(os.path.join('data/raw/crs/html', f))
        if sum(len(x[1].split()) for x in b) < 120:
            continue
        title = strip(r['title']) if r else num
        d = (r or {}).get('latestPubDate', '') or ''
        items.append((d, num, title, date, b))
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    parts = []
    for d, num, title, date, b in items:
        b = [['p', f'CRS Legal Sidebar {num}' + (f' · {date}' if date else '')]] + b
        parts.append((title, b))
    return write_book({'id': 'crs-sidebars', 'title': 'CRS Legal Sidebars', 'author': 'Congressional Research Service',
                       'year': '2017–2026', 'src': 'https://crsreports.congress.gov/', 'srcName': 'EveryCRSReport.com (CRS reports)',
                       'license': 'Congressional Research Service reports are U.S. government works, not subject to copyright; the text is reproduced in full, without the page headers, images and links',
                       'corner': '', 'shelf': 'gov'}, parts)


def main():
    only = sys.argv[1:] or ['conan', 'crs-sidebars']
    idx_path = 'docs/data/lib-index.js'
    s = open(idx_path, encoding='utf-8').read()
    index = {x['id']: x for x in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))}
    for k, fn in (('conan', conan), ('crs-sidebars', sidebars)):
        if k in only:
            index[k] = dict(fn(), shelf='gov')
    open(idx_path, 'w', encoding='utf-8').write('window.LIB_INDEX=' + json.dumps(list(index.values()), ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
