"""Replace "584 U.S. ___" placeholders in docs/data/scotus.js with real citations where they are now known.

The Supreme Court assigns U.S. Reports page numbers only when a bound volume is finalized, often years after the
decision; until then the case is cited "584 U.S. ___". For each such case this script uses, in order:
  1. the U.S. Reports page from the Supreme Court Database (2026 Release 01), e.g. 607 U.S. 627;
  2. otherwise the Supreme Court Reporter citation, the standard substitute (e.g. 138 S. Ct. 1612);
  3. otherwise the placeholder stays (the decision is too recent for either).
It also corrects S. Ct. citations whose volume does not match the Term (a few SCDB typos).
It then fills missing links that follow from the docket number or the citation (never from the case name alone):
  opinion PDF   a real U.S. Reports citation gives the per-case PDF at the Library of Congress (usrep<vol><page>.pdf) or,
                for volumes it does not hold, at GovInfo (USREPORTS-<vol>-<page>.pdf); otherwise the Court's slip-opinion
                / preliminary-print index for the Term (supremecourt.gov/opinions/slipopinion/<yy>, cached in
                data/raw/scotus/slip-<yy>.html), matched by docket or citation. build_extras.pl set the PDF only when
                Oyez already had a page number, so cases whose page came later (from SCDB, above) had none. Every new
                link is checked (its first bytes must be a PDF; results cached in data/raw/scotus/pdf_check.json).
  transcript    the Court's argument-transcript index for each Term (data/raw/transcripts/list-<year>.html, cached by
                transcripts_fetch.py), matched by Term and docket. build_extras.pl read only the newer link format
                (../argument_transcripts/...), so Terms before 2010 (/pdfs/transcripts/...) were missed. A link is used
                only if that transcript was fetched successfully into the cache.
Run from the repo root after build_extras.pl:  python scripts/fix_citations.py   (then rebuild flashcards)
"""
import csv, glob, html, json, os, re, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

FILES = ['data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Docket.csv']


def dk(d):
    return (d or '').replace('â\u0080\u0093', '-').replace('–', '-').strip().lower()


UA = {'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0 (static site build script)'}
CHECK = 'data/raw/scotus/pdf_check.json'


def dk_key(d):
    """'No. 22-451' / '22–451' -> '22-451'; '129, Orig.' / '22O129' -> '129-orig'."""
    d = dk(d).replace('no. ', '')
    m = re.match(r'^(\d+),?\s*orig\.?$', d) or re.match(r'^\d{2}o(\d+)$', d) or re.match(r'^(\d+)-orig$', d)
    return f'{m.group(1)}-orig' if m else d


def pdf_ok(url, cache):
    """True if the link answers with a PDF (only its first kilobyte is fetched)."""
    if url not in cache:
        try:
            req = urllib.request.Request(url, headers=dict(UA, Range='bytes=0-1023'))
            cache[url] = urllib.request.urlopen(req, timeout=60).read(5).startswith(b'%PDF')
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) or e.code >= 500:   # throttled or down: unknown, so neither used nor recorded as broken
                return False
            cache[url] = False
        except Exception:
            return False
        time.sleep(0.3)
    return cache[url]


def slip_index(terms):
    """(term, docket) and U.S. citation -> PDF link, from the Court's slip-opinion / preliminary-print index pages."""
    by_dk, by_cite = {}, {}
    os.makedirs('data/raw/scotus', exist_ok=True)
    for t in sorted(terms):
        f = f'data/raw/scotus/slip-{t % 100:02d}.html'
        if not os.path.exists(f):
            try:
                req = urllib.request.Request(f'https://www.supremecourt.gov/opinions/slipopinion/{t % 100:02d}', headers=UA)
                open(f, 'wb').write(urllib.request.urlopen(req, timeout=90).read())
                time.sleep(1)
            except Exception as e:
                print('  slip index failed', t, e)
                continue
        h = open(f, encoding='utf-8', errors='replace').read()
        for row in re.findall(r'<tr>(.*?)</tr>', h, re.S):
            td = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            m = re.search(r"href='(/opinions/[^']+\.pdf(?:#page=\d+)?)'", row)
            if len(td) < 4 or not m:
                continue
            url = 'https://www.supremecourt.gov' + m.group(1)
            cell = re.sub(r'<[^>]+>', ' ', td[2]).strip()
            for o in re.findall(r'\b(\d+),?\s*Orig\b', cell, re.I):   # "141, Orig." is one docket, not "141" and "Orig."
                by_dk.setdefault((t, f'{o}-orig'), url)
            cell = re.sub(r'\b\d+,?\s*Orig\.?', ' ', cell, flags=re.I)
            for d in re.split(r'[,\s]+', cell):
                if d:
                    by_dk.setdefault((t, dk_key(d)), url)
            cm = re.search(r'(\d+) U\.S\. (\d+)', re.sub(r'<[^>]+>', ' ', row))
            if cm:
                by_cite.setdefault(f'{cm.group(1)} U.S. {cm.group(2)}', url)
    return by_dk, by_cite


def govinfo_index(terms, first_vol=578, last_vol=620):
    """(term, docket) -> GovInfo per-case PDF, for the bound volumes of the given Terms. GovInfo's metadata gives each
    case's U.S. Reports citation but no docket number, so the docket is read from the caption on the PDF's first page
    ("No. 16–1435", "Nos. 16–1466 and 16–1467", "No. 142, Orig."). Cached in data/raw/scotus/govinfo/."""
    D = 'data/raw/scotus/govinfo'
    os.makedirs(D, exist_ok=True)
    out = {}

    def get(url, path):
        if not os.path.exists(path):
            try:
                open(path, 'wb').write(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read())
            except Exception:
                open(path, 'wb').close()
            time.sleep(0.4)
        return open(path, 'rb').read()

    for v in range(first_vol, last_vol + 1):
        x = get(f'https://www.govinfo.gov/metadata/pkg/USREPORTS-{v}/mods.xml', f'{D}/{v}.xml').decode('utf-8', 'replace')
        m = re.search(r'October term, (\d{4})', x)
        if not m or int(m.group(1)) not in terms:
            continue
        t = int(m.group(1))
        for pg in sorted(set(re.findall(rf'id-USREPORTS-{v}-(\d+)"', x)), key=int):
            pdf = f'{D}/{v}-{pg}.pdf'
            url = f'https://www.govinfo.gov/content/pkg/USREPORTS-{v}/pdf/USREPORTS-{v}-{pg}.pdf'
            if not os.path.exists(pdf + '.txt'):
                b = get(url, pdf)
                txt = ''
                if b.startswith(b'%PDF'):
                    import subprocess
                    txt = subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', '-l', '2', pdf, '-'], capture_output=True).stdout.decode('utf-8', 'replace')
                open(pdf + '.txt', 'w', encoding='utf-8').write(txt)
                if os.path.exists(pdf):
                    os.remove(pdf)
            head = re.sub(r'[‐-—�]', '-', open(pdf + '.txt', encoding='utf-8').read()[:3000])   # dashes; U+FFFD from older Latin-1 caches
            for cap in re.findall(r'\bNos?\.\s+([0-9][0-9A-Za-z,\s\-]*?(?:Orig\.)?)(?:\.|\n\n|\s{2}|[A-Z]{3})', head)[:2]:
                for d in re.findall(r'\b(\d{2}-\d{1,5})\b', cap):
                    out.setdefault((t, d), url)
                o = re.search(r'\b(\d+),\s*Orig', cap)
                if o:
                    out.setdefault((t, f'{o.group(1)}-orig'), url)
    return out


GENERIC = set('''united states america inc corp co company corporation city county state board school district department
the and of for in et al ex rel re matter commission commissioner secretary director warden attorney general mayor council
coalition association services financial government national new north south east west'''.split())


def _spaced(txt):
    """True if pdftotext -layout split the words into letters ("T E N N A N T"), as it does for some GovInfo PDFs."""
    toks = [t for t in txt[:20000].split() if t != '.']       # not the dot leaders of a table of cases
    return len(toks) > 200 and sum(len(t) == 1 and t.isalpha() for t in toks) > 0.6 * len(toks)


def _pdf_text(url, path, delay=0.4):
    """Text of a PDF (pages split by form feeds), cached as text at path; '' if it cannot be fetched."""
    if os.path.exists(path) and _spaced(open(path, encoding='utf-8').read(20000)):
        os.remove(path)        # cached letter-spaced text from an earlier run: extract again without -layout
    if not os.path.exists(path):
        import subprocess
        txt = ''
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()
            if b.startswith(b'%PDF'):
                open(path + '.pdf', 'wb').write(b)
                run = lambda *o: subprocess.run(['pdftotext', '-q', *o, '-enc', 'UTF-8', path + '.pdf', '-'],
                                                capture_output=True).stdout.decode('utf-8', 'replace')
                txt = run('-layout')
                if _spaced(txt):
                    txt = run()
                if _spaced(txt):       # the PDF places each letter on its own: keep the letters, drop the spaces in a line
                    txt = re.sub(r'[ \t]+', '', txt)
                os.remove(path + '.pdf')
            else:
                print('  not a PDF (throttled?)', url)
                time.sleep(5)
                return ''      # not cached: tried again next run
        except Exception as e:
            print('  fetch failed', url, e)
            return ''          # not cached: tried again next run
        open(path, 'w', encoding='utf-8').write(txt)
        time.sleep(delay)
    return re.sub(r'[‐-—−�]', '-', open(path, encoding='utf-8').read())   # dashes (U+FFFD: an unmapped one)


MONTHS = 'January February March April May June July August September October November December'.split()
DATE = re.compile(r'(%s)\s*(\d{1,2}),\s*(\d{4})' % '|'.join(MONTHS))   # \s*: letter-spaced PDFs are cached without spaces


DISPOSED = re.compile(r'(?:certiorari|appeal)\s+dismissed|dismissed\s+(?:under|as)|judgment\s+(?:is\s+)?(?:vacated|affirmed|reversed)|vacated\s+and\s+remanded|affirmed\s+by\s+an\s+equally', re.I)


def decided_here(gt, k, drx, dec, days=0):
    """True if the entry for the docket on PDF page k is the decision of `dec` (YYYY-MM-DD), not the grant of certiorari
    or a later order: an opinion's caption says "Decided <date>" just after the docket number; an order sits under the
    date heading of its day, which may be several pages back. With days > 0, an order that disposes of the case
    (certiorari dismissed, judgment vacated, ...) within that many days of `dec` is accepted too: the site's date for a
    case dismissed by stipulation is sometimes that of the stipulation, not of the Court's order."""
    from datetime import date
    pg = gt[k]
    iso = lambda m: f'{int(m.group(3)):04d}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}'
    gap = lambda a: abs((date.fromisoformat(a) - date.fromisoformat(dec)).days)
    for pos in sorted({m.start() for r in drx for m in re.finditer(r, pg)}):   # the docket may appear in several entries
        after = pg[pos:pos + 600]
        m = re.search(r'Decided\s*(?=%s)' % DATE.pattern, after)
        if m:
            if iso(DATE.match(after, m.end())) == dec:
                return True
            continue
        heads = list(DATE.finditer('\f'.join(gt[max(0, k - 12):k] + [pg[:pos]])))
        if heads and (iso(heads[-1]) == dec or (days and gap(iso(heads[-1])) <= days and DISPOSED.search(after[:500]))):
            return True
    return False


def _fold(s):
    """For matching names in GovInfo text, where the fi/fl ligatures are sometimes dropped ("Pacifc")."""
    return s.lower().replace('ﬁ', 'fi').replace('ﬂ', 'fl').replace('fi', 'f').replace('fl', 'f')


def _find_in_volumes(c, vols, words, drx, cache, term, days, D):
    for t in (term(c), term(c) + 1, term(c) - 1):
        for v, grs in vols.get(t, []):
            pages = []
            for g, ti in grs:        # a case granule's own title: "Tennant v. Jefferson County Comm'n, 567 U.S. 758 (2012)"
                if re.match(r'^USREPORTS-\d+-\d+$', g) and all(re.search(r'\b' + re.escape(_fold(w)) + r'\b', _fold(ti)) for w in words):
                    pages.append(int(g.rsplit('-', 1)[1]))
            toc = next((g for g, ti in grs if ti.startswith('Table of Cases')), None)
            if toc:
                txt = _pdf_text(f'https://www.govinfo.gov/content/pkg/USREPORTS-{v}/pdf/{toc}.pdf', f'{D}/gr/{toc}.txt')
                for ln in txt.splitlines():
                    if all(re.search(r'\b' + re.escape(_fold(w)) + r'\b', _fold(ln)) for w in words):
                        pm = re.search(r'[.\s]\s*(\d+(?:\s*,\s*\d+)*)\s*$', ln)
                        if pm:
                            pages += [int(q) for q in re.findall(r'\d+', pm.group(1))]
            starts = sorted((int(g.rsplit('-', 1)[1]), g) for g, _ in grs if re.match(r'^USREPORTS-\d+-\d+$', g))
            orders = [g for g, ti in grs if ti.startswith('Orders')]
            for p in sorted(set(pages), reverse=True):     # the later page is the decision, the earlier often the grant
                before = [g for s, g in starts if s <= p][-1:]
                for g in before + orders + [f'USREPORTS-{v}']:     # last, the whole volume (a few MB)
                    gt = _pdf_text(f'https://www.govinfo.gov/content/pkg/USREPORTS-{v}/pdf/{g}.pdf', f'{D}/gr/{g}.txt').split('\f')
                    for k, pg in enumerate(gt):
                        ls = pg.strip().splitlines()
                        head = '\n'.join(ls[:6] + ls[-3:])     # a section's first page has its number at the foot
                        at_p = re.search(rf'(?<![\d,]){p}(?![\d,])', head) or (k == 0 and g == f'USREPORTS-{v}-{p}')
                        if at_p and any(re.search(r, pg) for r in drx) and decided_here(gt, k, drx, c['dec'], days):
                            url = f'https://www.govinfo.gov/content/pkg/USREPORTS-{v}/pdf/{g}.pdf'
                            if pdf_ok(url, cache):
                                return url + (f'#page={k + 1}' if k else '')
                            return None
    return None


def govinfo_toc(cases, cache, term):
    """Cases still without a PDF whose bound volume is on GovInfo (through about OT2018) but has no per-case granule
    (orders, summary dispositions, decrees, and a few opinions GovInfo did not split out, e.g. Husted, 584 U.S. 756).
    The volume's Table of Cases Reported gives the page; the link is the GovInfo granule that holds that page (the case
    granule starting at or before it, an "Orders for ..." granule, or else the whole volume), opened at the PDF page that shows the U.S.
    Reports page number and the case's docket number. Nothing is linked unless both are found on that page.
    Caches: data/raw/scotus/govinfo/<vol>.xml (volume MODS), govinfo/gr/<granule>.txt (granule text)."""
    D = 'data/raw/scotus/govinfo'
    os.makedirs(f'{D}/gr', exist_ok=True)
    need = [c for c in cases if c.get('dec') and not c.get('pdf') and c.get('s') != 1 and 0 < term(c) <= 2019]
    if not need:
        return
    vols = {}
    for v in range(300, 600):
        p = f'{D}/{v}.xml'
        if not os.path.exists(p):
            try:
                b = urllib.request.urlopen(urllib.request.Request(f'https://www.govinfo.gov/metadata/pkg/USREPORTS-{v}/mods.xml', headers=UA), timeout=120).read()
            except Exception:
                b = b''
            open(p, 'wb').write(b)
            time.sleep(0.4)
        x = open(p, encoding='utf-8', errors='replace').read()
        m = re.search(r'October term, (\d{4})', x)
        if not m:
            continue
        grs = []
        for part in x.split('<relatedItem type="constituent" ID="id-')[1:]:
            gid = part.split('"', 1)[0]
            t = re.search(r'<title>(.*?)</title>', part)
            grs.append((gid, html.unescape(t.group(1)) if t else ''))
        vols.setdefault(int(m.group(1)), []).append((v, grs))
    filled = near = 0
    for c in need:
        sides = [re.sub(r'[(),.]', ' ', s) for s in re.split(r'\s+v\.\s+', c.get('n') or '', 1)]
        words = [next((w for w in re.findall(r"[A-Za-z][A-Za-z'’\-]+", s) if len(w) > 2 and w.lower() not in GENERIC), None) for s in sides]
        words = [w for w in words if w]
        dks = [d for d in re.split(r'[,\s]+', c.get('d') or '') if re.match(r'^\d', d)]
        drx = []
        for d in dks:
            o = re.match(r'^(\d+)-orig$', dk_key(d))
            drx.append(rf'\b{o.group(1)},\s*Orig' if o else rf'No(?:s?\.|\.)\s*(?:[\d\-]+,?\s*(?:and\s*)?)*(?<![\d\-]){re.escape(d)}(?![\d])')
        if not words or not drx:
            continue
        for days in (0, 120):
            u = _find_in_volumes(c, vols, words, drx, cache, term, days, D)
            if u:
                c['pdf'] = u
                filled += 1
                near += days > 0
                break
    print(f'GovInfo volumes, by the Table of Cases (no per-case granule): filled {filled} of {len(need)} ({near} by a disposing order near the date)')


def court_orders(cases, cache, term):
    """Cases still without a PDF that were decided by order (dismissed, vacated, ...) after GovInfo's bound volumes end:
    the Court's "opinions relating to orders" index for the Term (supremecourt.gov/opinions/relatingtoorders/<yy>),
    matched by docket and date, else the order list of the decision date (supremecourt.gov/orders/ordersofthecourt/<yy>),
    used only if its text has the docket number; the link opens at that page. Cached in data/raw/scotus/orders/."""
    D = 'data/raw/scotus/orders'
    os.makedirs(D, exist_ok=True)
    need = [c for c in cases if c.get('dec') and not c.get('pdf') and c.get('s') != 1 and term(c) >= 2005]

    def page(path, url):
        f = f'{D}/{path}'
        if not os.path.exists(f) or not os.path.getsize(f):
            try:
                open(f, 'wb').write(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read())
            except Exception as e:
                print('  orders index failed', url, e)
                return ''
            time.sleep(1)
        return open(f, encoding='utf-8', errors='replace').read()
    filled = 0
    for c in need:
        y, mo, d = c['dec'].split('-')
        dks = [dk_key(x) for x in re.split(r'[,\s]+', c.get('d') or '') if re.match(r'^\d', x)]
        found = None
        for t in (term(c), term(c) + 1, term(c) - 1):
            h = page(f'relating-{t % 100:02d}.html', f'https://www.supremecourt.gov/opinions/relatingtoorders/{t % 100:02d}')
            for row in re.findall(r'<tr>(.*?)</tr>', h, re.S):
                td = [re.sub(r'<[^>]+>', '', x).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
                m = re.search(r"href='(/opinions/[^']+\.pdf(?:#page=\d+)?)'", row)
                if m and len(td) >= 2 and td[0] == f'{int(mo)}/{int(d)}/{y[2:]}' and dk_key(td[1]) in dks:
                    found = 'https://www.supremecourt.gov' + m.group(1)
            if found:
                break
            h = page(f'ordersofthecourt-{t % 100:02d}.html', f'https://www.supremecourt.gov/orders/ordersofthecourt/{t % 100:02d}')
            for href in re.findall(r"href='(/orders/courtorders/%s%s%s[a-z]*_[^']+\.pdf)'" % (mo, d, y[2:]), h):
                gt = _pdf_text('https://www.supremecourt.gov' + href, f"{D}/{href.rsplit('/', 1)[1]}.txt", delay=1).split('\f')
                k = next((i for i, pg in enumerate(gt) if any(re.search(r'(?<![\d\-])' + re.escape(x) + r'(?![\d])', pg) for x in dks)), None)
                if k is not None:
                    found = 'https://www.supremecourt.gov' + href + (f'#page={k + 1}' if k else '')
                    break
            if found:
                break
        if found and pdf_ok(found.split('#')[0], cache):
            c['pdf'] = found
            filled += 1
    print(f"supremecourt.gov orders (relating-to-orders opinions, order lists): filled {filled} of {len(need)}")


def repair_loc(cases, cache, term):
    """Library of Congress per-page links already found broken (pdf_check.json): memorandum orders and some per curiams
    have no file of their own at the LoC. Try GovInfo's per-case PDF for the same volume and page, then the volume's
    orders file at the LoC (usrep<vol>orders or usrep<vol><first page>), used only if its text has the case's docket
    number; the link then opens at that page. Order files are cached as text in data/raw/scotus/loc_orders/."""
    D = 'data/raw/scotus/loc_orders'
    os.makedirs(D, exist_ok=True)
    base = 'https://tile.loc.gov/storage-services/service/ll/usrep/usrep{v:03d}/{k}/{k}.pdf'

    def pages(k, v):
        p = f'{D}/{k}.txt'
        if not os.path.exists(p):
            txt = ''
            try:
                b = urllib.request.urlopen(urllib.request.Request(base.format(v=v, k=k), headers=UA), timeout=300).read()
                if b.startswith(b'%PDF'):
                    import subprocess
                    open(p + '.pdf', 'wb').write(b)
                    txt = subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', p + '.pdf', '-'], capture_output=True).stdout.decode('utf-8', 'replace')
                    os.remove(p + '.pdf')
            except Exception:
                pass
            open(p, 'w', encoding='utf-8').write(txt)
            time.sleep(1)
        return re.sub(r'[‐-—�]', '-', open(p, encoding='utf-8').read()).split('\f')

    fixed = 0
    for c in cases:
        u = c.get('pdf') or ''
        m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
        if 'tile.loc.gov' not in u or cache.get(u) is not False or not m:
            continue
        v, pg = int(m.group(1)), int(m.group(2))
        gov = f'https://www.govinfo.gov/content/pkg/USREPORTS-{v}/pdf/USREPORTS-{v}-{pg}.pdf'
        if pdf_ok(gov, cache):
            c['pdf'] = gov; fixed += 1
            continue
        dks = [d for d in re.split(r'[,\s]+', c.get('d') or '') if re.match(r'^\d', d)]
        for k in [f'usrep{v:03d}orders'] + [f'usrep{v:03d}{s}' for s in range(pg - pg % 100 + 1, 700, -100)]:
            pp = pages(k, v)
            hits = [i for i, t in enumerate(pp) if any(re.search(r'No\.\s*' + re.escape(d) + r'\b', t) for d in dks)]
            # a docket can appear more than once (cert granted, then decided): prefer the page headed with the cited page
            hit = next((i for i in hits if re.search(rf'(?<![\d.,]){pg}(?![\d,])', pp[i][:300] + pp[i][-300:])), hits[-1] if hits else None)
            if hit is not None:
                c['pdf'] = base.format(v=v, k=k) + f'#page={hit + 1}'; fixed += 1
                break
    print(f'broken Library of Congress links repaired: {fixed}')


def tr_names(url, docket):
    """True if the cached transcript's cover page lists this docket: cases decided together are not always argued together
    (Bostock and Zarda were argued in one session, Harris Funeral Homes in another)."""
    m = re.search(r'/(\d{4})/([^/]+)\.pdf$', url)
    p = f'data/raw/transcripts/{m.group(1)}/{m.group(2)}.txt' if m else ''
    if not os.path.exists(p):
        return False
    head = re.sub(r'[‐-—�]', '-', open(p, encoding='utf-8', errors='replace').read()[:4000])
    return re.search(r'(?<![\d-])' + re.escape(docket) + r'(?![\d])', head) is not None


def fill_links(cases, siblings):
    term = lambda c: int(c['t']) if str(c.get('t') or '').isdigit() else 0
    cache = json.load(open(CHECK)) if os.path.exists(CHECK) else {}
    # ---- opinion PDFs (cases added from SCDB, s: 1, get theirs on the page from the citation)
    need = [c for c in cases if c.get('dec') and not c.get('pdf') and c.get('s') != 1]
    by_dk, by_cite = slip_index({term(c) for c in need if term(c) >= 2017})
    gov = govinfo_index({term(c) for c in need if term(c) >= 2015 and not re.match(r'^\d+ U\.S\. \d+$', c.get('cit') or '')})
    cands = {}
    for c in need:
        urls = []
        m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
        if m:
            v, pg = int(m.group(1)), int(m.group(2))
            k = f'usrep{v:03d}{pg:03d}'
            urls += [f'https://tile.loc.gov/storage-services/service/ll/usrep/usrep{v:03d}/{k}/{k}.pdf',
                     f'https://www.govinfo.gov/content/pkg/USREPORTS-{v}/pdf/USREPORTS-{v}-{pg}.pdf']
            if c['cit'] in by_cite:
                urls.append(by_cite[c['cit']])
        for d in re.split(r'[,\s]+', c.get('d') or ''):
            if d and (term(c), dk_key(d)) in gov:
                urls.append(gov[(term(c), dk_key(d))])
            if d and (term(c), dk_key(d)) in by_dk:
                urls.append(by_dk[(term(c), dk_key(d))])
        if urls:
            cands[c['id']] = list(dict.fromkeys(urls))
    todo = sorted({u.split('#')[0] for us in cands.values() for u in us} - set(cache))
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(lambda u: pdf_ok(u, cache), todo))
    json.dump(cache, open(CHECK, 'w'), indent=0)
    src = {}
    for c in need:
        for u in cands.get(c['id'], []):
            if cache.get(u.split('#')[0]):
                c['pdf'] = u
                host = 'loc.gov' if 'loc.gov' in u else 'govinfo.gov' if 'govinfo' in u else 'supremecourt.gov'
                src[host] = src.get(host, 0) + 1
                break
    print(f'opinion PDFs: {len(need)} cases lacked one; filled {sum(src.values())} {src}; checked {len(todo)} new links')
    govinfo_toc(cases, cache, term)
    court_orders(cases, cache, term)
    json.dump(cache, open(CHECK, 'w'), indent=0)
    repair_loc(cases, cache, term)
    # ---- argument transcripts
    tr = {}
    for f in glob.glob('data/raw/transcripts/list-*.html'):
        y = int(re.search(r'list-(\d+)', f).group(1))
        h = open(f, encoding='utf-8', errors='replace').read()
        for href, text in re.findall(r"href='([^']*(?:argument_transcripts|/pdfs/transcripts)/%d/[^']+\.pdf)'[^>]*>\s*([^<]+?)\s*<" % y, h):
            name = href.rsplit('/', 1)[1][:-4]
            if not os.path.exists(f'data/raw/transcripts/{y}/{name}.txt'):
                continue   # not fetched (or the fetch failed): don't link what was not seen to work
            url = ('https://www.supremecourt.gov' + href) if href.startswith('/') else 'https://www.supremecourt.gov/oral_arguments/' + href.replace('../', '')
            whole = re.sub(r'-question-\d+$', '', text.strip().lower())   # "105 Orig.", "126-Orig", "14-556-Question-1"
            for d in [whole] + re.split(r'[,\s]+', text):
                if re.match(r'^\d', d):
                    tr.setdefault((y, dk_key(d)), url)
    n_tr = 0
    for c in cases:
        if c.get('tr') or term(c) < 2004:
            continue
        for d in re.split(r'[,\s]+', c.get('d') or ''):
            u = tr.get((term(c), dk_key(d))) if d else None
            if u:
                c['tr'] = u
                n_tr += 1
                break
    print(f'argument transcripts: filled {n_tr}')
    # ---- consolidated cases: a case filed under a non-lead docket shares the opinion and the argument of the case it
    #      was decided with (SCDB's docket-organized file lists every docket of a decision under one caseId)
    by_key = {}
    for c in cases:
        for d in re.split(r'[,\s]+', c.get('d') or ''):
            if d:
                by_key.setdefault((term(c), dk_key(d)), []).append(c)
    sib = {'pdf': 0, 'tr': 0}
    for c in cases:
        for field in ('pdf', 'tr'):
            if c.get(field) or (field == 'pdf' and (not c.get('dec') or c.get('s') == 1)):
                continue
            for d in re.split(r'[,\s]+', c.get('d') or ''):
                for od in siblings.get((term(c), dk_key(d)), ()) if d else ():
                    donor = next((x for x in by_key.get((term(c), od), []) if x.get(field) and x.get('dec') == c.get('dec')
                                  and (field == 'pdf' or tr_names(x['tr'], d))), None)
                    if donor:
                        c[field] = donor[field]; sib[field] += 1
                        break
                if c.get(field):
                    break
    print(f'from the case decided with them (same decision date, docket listed under the same SCDB caseId): {sib}')


def main():
    found, groups = {}, {}
    for f in FILES:
        for r in csv.DictReader(open(f, encoding='latin-1')):
            if r['term'].isdigit():
                groups.setdefault((int(r['term']), r['caseId']), set()).add(dk_key(r['docket']))
            key = (r['term'], dk(r['docket']))
            us, sct = r['usCite'].strip(), r['sctCite'].strip()
            prev = found.get(key, ('', ''))
            found[key] = (us if us and '_' not in us else prev[0], sct or prev[1])
    path = 'docs/data/scotus.js'
    s = open(path, encoding='utf-8').read()
    data = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    us_n = sct_n = left = 0
    for c in data['cases']:
        cit = c.get('cit') or ''
        if '___' not in cit and not re.match(r'^\d+ U\.S\.\s*$', cit):   # "545 U.S. " (no page) is a placeholder too
            continue
        us, sct = found.get((str(c.get('t')), dk(c.get('d'))), ('', ''))
        if us:
            c['cit'] = us; us_n += 1
        elif sct:
            c['cit'] = sct; c['citUS'] = cit; sct_n += 1
        else:
            left += 1
    # a few SCDB rows carry a mistyped S. Ct. volume (e.g. Bruen as 141 S. Ct. 2111; it is 142). Since the 1990 Term each
    # Term has had one volume, numbered Term - 1879, so a recent S. Ct. citation whose volume disagrees is corrected.
    vol_fixed = 0
    for c in data['cases']:
        m = re.match(r'^(\d+) S\. Ct\. (\d+)$', c.get('cit') or '')
        t = str(c.get('t') or '')
        if m and t.isdigit() and int(t) >= 1990 and int(m.group(1)) != int(t) - 1879:
            c['cit'] = f'{int(t) - 1879} S. Ct. {m.group(2)}'; vol_fixed += 1
    print(f'S. Ct. volumes corrected: {vol_fixed}')
    siblings = {}
    for (t, _), dks in groups.items():
        for d in dks:
            siblings.setdefault((t, d), set()).update(dks - {d})
    fill_links(data['cases'], siblings)
    open(path, 'w', encoding='utf-8').write('window.SCOTUS=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'U.S. Reports pages filled: {us_n}; cited to S. Ct. instead: {sct_n}; placeholders left (too recent): {left}')


if __name__ == '__main__':
    main()
