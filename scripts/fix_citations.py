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
import csv, glob, json, os, re, time, urllib.error, urllib.request
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
            for d in re.split(r'[,\s]+', re.sub(r'<[^>]+>', ' ', td[2]).strip()):
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
