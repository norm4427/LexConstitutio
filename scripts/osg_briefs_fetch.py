"""Cache the Solicitor General's merits briefs for argued Supreme Court cases from before e-filing (October Terms
1982-2017), for build_authorities.py.

Source: the Office of the Solicitor General's brief archive, https://www.justice.gov/osg/supreme-court-briefs
(works of the U.S. Government, not under copyright; robots.txt allows /osg/). It lists every brief the Office filed
from OT1982 on, by Term: the briefs of the United States (and federal agencies and officers) as a party, and as amicus
curiae. Briefs to about 2004 are plain-text OCR of the printed briefs (served as "PDF" but text/plain); later ones are
text PDFs. Other parties' briefs are not in it, so a case gets the federal government's side only, and only where the
government took part (about two thirds of argued cases).

Steps (each cached, so a run can be stopped and resumed):
  1. listing pages, all brief types, per Term   data/raw/osg/list/<term>-<page>.html
  2. rows matched to the site's argued cases of that Term (or the next) that have no authorities data yet, by docket
     number, or by both party names when the row has no number; merits-stage types only where the row is typed
  3. each matched brief's text                  data/raw/briefs/<docket>/osg-<media id>.txt
     classified from its cover (merits stage only: "On writ of certiorari" / "On appeal", not "in opposition",
     petitions, memoranda or supplemental briefs) into petitioner / respondent / reply / united-states (amicus)
  4. the opinion from the U.S. Reports (the site's tile.loc.gov PDF for the case)   data/raw/briefs/<docket>/opinion.txt
Output: data/raw/briefs/osg-manifest.json ({docket: {briefs: [...], opinion: url}}), read by build_authorities.py
alongside manifest.json. Cases are fetched most cited first (docs/data/case_impact.js).
User-Agent "LexConstitutio/1.0 (static site build)"; about one request per 1.5 s (justice.gov) and 3 s (loc.gov).
Run from the repo root:  python scripts/osg_briefs_fetch.py [--terms 1985-2017] [--limit N] [--no-opinions]
"""
import glob, html, json, os, re, subprocess, sys, time, urllib.request

LIST = 'data/raw/osg/list'
OUT = 'data/raw/briefs'
MAN = f'{OUT}/osg-manifest.json'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
BASE = 'https://www.justice.gov'
MERITS_TYPES = {'Merits Stage Brief', 'Merits Stage Reply Brief', 'Merits Stage Amicus Brief'}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


_last = {}


def get(url, timeout=120, pause=1.5):
    host = url.split('/')[2]
    wait = _last.get(host, 0) + pause - time.time()
    if wait > 0:
        time.sleep(wait)
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
    finally:
        _last[host] = time.time()


# ------------------------------------------------------------------ 1. listing
def cell(x):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', x))).strip()


def listing(term):
    """Rows (term, number, title, type, date, detail href, [media hrefs]) for one Term. Terms whose briefs are typed
    (about OT2003 on) are listed by the three merits-stage types; earlier ones, untyped, in full."""
    typed = list_type(term, 'merits_stage_brief')
    if typed:
        return typed + list_type(term, 'merits_stage_reply_brief') + list_type(term, 'merits_stage_amicus_brief')
    return list_type(term, 'All')


def list_type(term, typ):
    os.makedirs(LIST, exist_ok=True)
    rows, page = [], 0
    while True:
        p = f'{LIST}/{term}-{page}.html' if typ == 'All' else f'{LIST}/{term}-{typ}-{page}.html'
        if not os.path.exists(p):
            t = '2025_term' if term == 2025 else str(term)
            b = get(f'{BASE}/osg/supreme-court-briefs?sc_term={t}&type={typ}&subject=All&page={page}')
            open(p, 'wb').write(b)
        h = open(p, encoding='utf-8', errors='replace').read()
        got = 0
        for tr in re.findall(r'<tr>(.*?)</tr>', h, re.S):
            td = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
            if len(td) < 7:
                continue
            det = re.search(r'href="(/osg/brief/[^"]+)"', td[2])
            media = re.findall(r'href="(/osg/media/\d+/dl[^"]*)"', td[3])
            dt = re.search(r'datetime="(\d{4}-\d\d-\d\d)', td[6])
            got += 1
            rows.append({'term': term, 'no': cell(td[1]), 'title': cell(td[2]), 'type': cell(td[4]), 'date': dt.group(1) if dt else '',
                         'detail': det.group(1) if det else '', 'media': media})
        pages = [int(x) for x in re.findall(r'(?:[?&]|&amp;)page=(\d+)', h)]
        if not got or page >= max(pages or [0]):
            return rows
        page += 1


# ------------------------------------------------------------------ 2. matching
def dk_norm(s):
    s = s.lower().replace('–', '-').strip()
    m = re.match(r'^(\d{2,4})-0*(\d+)$', s)
    if m:
        return f'{m.group(1)}-{m.group(2)}'
    m = re.match(r'^(?:no\.\s*)?(\d+),?\s*-?\s*orig\.?$', s)
    if m:
        return f'{m.group(1)}-orig'
    return s


def row_dockets(no):
    return [dk_norm(x) for x in re.findall(r'\d{2}-0*\d{1,5}\b|\d{1,3},?\s+Orig\b', no, re.I)]


GOVWORDS = r'UNITED STATES|SECRETARY|COMMISSIONER|ATTORNEY GENERAL|FEDERAL|NATIONAL LABOR|DEPARTMENT|ADMINISTRATOR|DIRECTOR|INTERNAL REVENUE|AGENCY|COMMISSION\b|BOARD\b|\bSERVICE\b|POSTAL|BUREAU|CORPS|NAVY|ARMY|AIR FORCE|IMMIGRATION|OFFICE OF|SOCIAL SECURITY|ADMINISTRATION|AUTHORITY|SURFACE TRANSPORTATION|CHIEF|WARDEN'


def side_words(name):
    """First significant word of each side of a caption ("HENRY A. CROCKETT, PETITIONER V. UNITED STATES OF AMERICA")."""
    name = re.sub(r'\s*-\s*(?:Brief|Reply|Amicus|Opposition|Petition).*$', '', name, flags=re.I)
    m = re.match(r'^(.+?)\s+v(?:s)?\.?\s+(.+)$', name, re.I)
    if not m:
        return None
    skip = {'the', 'of', 'a', 'an', 'in', 're', 'et', 'al', 'inc', 'no'}

    def first(s):
        s = re.sub(r',?\s*(?:et al\.?,?\s*)?(?:petitioners?|respondents?|appellants?|appellees?)\b.*$', '', s, flags=re.I)
        w = [x.lower() for x in re.findall(r"[A-Za-z][A-Za-z'\-]+", s) if x.lower() not in skip and len(x) > 1]
        # a person's caption ("HENRY A. CROCKETT") is keyed by surname on the site; take the last word of a short name
        return w
    return first(m.group(1)), first(m.group(2))


def name_match(title, cand):
    sw = side_words(title)
    if not sw or not sw[0] or not sw[1]:
        return None
    hits = []
    for c in cand:
        m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+)$', c['n'])
        if not m:
            continue
        a = [x.lower() for x in re.findall(r"[A-Za-z][A-Za-z'\-]+", m.group(1))]
        b = [x.lower() for x in re.findall(r"[A-Za-z][A-Za-z'\-]+", m.group(2))]
        if not a or not b:
            continue
        # the site's first word of each side must appear among the row's words for that side
        if a[0] in sw[0] and b[0] in sw[1]:
            hits.append(c)
    return hits[0] if len(hits) == 1 else None


# ------------------------------------------------------------------ 3. briefs
def to_text(url, dest, pause=1.5):
    """Plain text of a brief or opinion (text/plain as served, or pdftotext of a PDF)."""
    if os.path.exists(dest):
        return True
    try:
        b = get(url, pause=pause)
    except Exception as e:
        print('  failed', url, e, flush=True)
        return False
    if b.startswith(b'%PDF'):
        pdf = dest[:-4] + '.pdf'
        open(pdf, 'wb').write(b)
        try:
            subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', pdf, dest], check=True)
        except Exception as e:
            print('  pdftotext failed', url, e, flush=True)
            return False
        finally:
            os.remove(pdf)
    elif b[:200].lstrip().startswith((b'<!DOCTYPE', b'<html', b'<HTML')):
        return False
    else:
        try:
            t = b.decode('utf-8')
        except UnicodeDecodeError:
            t = b.decode('cp1252', errors='replace')
        open(dest, 'w', encoding='utf-8').write(t)
    return os.path.exists(dest) and os.path.getsize(dest) > 500


def cover(t):
    """The cover page: text up to the first page break, table of contents or Questions Presented."""
    t = t[:6000]
    m = re.search(r'-{5,}\s*Page Break|\f|QUESTIONS? PRESENTED|TABLE OF CONTENTS', t)
    return t[: m.start()] if m and m.start() > 200 else t[:2500]


def classify(t, title=''):
    """(kind, label) of a merits brief from its cover, or None for anything else."""
    c = cover(t)
    C = re.sub(r'\s+', ' ', c).upper()
    if re.search(r'IN OPPOSITION|ON PETITIONS? FOR (?:A )?WRITS? OF CERTIORARI|PETITION FOR (?:A )?WRIT OF CERTIORARI\b(?! TO)|MEMORANDUM|'
                 r'SUPPLEMENTAL|JURISDICTIONAL STATEMENT|MOTION|APPLICATION|ON BILL OF COMPLAINT|ON EXCEPTIONS|REPORT OF THE SPECIAL MASTER|'
                 r'PETITION FOR REHEARING|SUGGESTION', C):
        if not re.search(r'ON WRITS? OF CERTIORARI|ON APPEALS? FROM', C):
            return None
        if re.search(r'IN OPPOSITION|SUPPLEMENTAL|MEMORANDUM|MOTION', C):
            return None
    if not re.search(r'ON WRITS? OF CERTIORARI|ON APPEALS? FROM|ON CERTIFI', C):
        return None
    m = re.search(r'\b((?:REPLY )?BRIEFS? (?:FOR|OF) (?:THE )?[A-Z ,.\'\-]{3,200}?)(?=\s+(?:[A-Z][A-Z.]+ [A-Z]\.? ?[A-Z]+|[A-Z]+ [A-Z]+,?\s*(?:JR|III|II)\b|DREW|KENNETH|CHARLES|WALTER|SETH|THEODORE|PAUL|DONALD|ELENA|NOEL|DONALD|REX|ROBERT|WILLIAM|EDWIN|SOLICITOR|DEPARTMENT|ATTORNEYS?\b)|$)', C)
    label = m.group(1).strip(' ,.') if m else 'BRIEF FOR THE UNITED STATES'
    label = re.sub(r'\s+(?:[A-Z]\.\s*)?[A-Z]+,?\s*(?:JR|III|II)\.?$', '', label)
    label = label[:160]
    L = label.upper()
    if L.startswith('REPLY'):
        kind = 'reply'
    elif 'AMIC' in L:
        kind = 'united-states'
    elif re.search(r'FOR (?:THE )?(?:FEDERAL )?(?:PETITIONERS?|APPELLANTS?)\b', L):
        kind = 'petitioner'
    elif re.search(r'FOR (?:THE )?(?:FEDERAL )?(?:RESPONDENTS?|APPELLEES?)\b', L):
        kind = 'respondent'
    else:   # "Brief for the United States": the government's side in the caption
        cap = re.split(r'ON (?:WRITS? OF CERTIORARI|APPEALS? FROM)', C)[0]
        cap = re.sub(r'^.*?OCTOBER TERM,? \d{4}', '', cap)
        parts = re.split(r'\s+V\.?\s+', cap, 1)
        pet_gov = len(parts) == 2 and re.search(GOVWORDS, parts[0])
        kind = 'petitioner' if pet_gov else 'respondent'
    return kind, label[:1] + label[1:].lower().replace('united states', 'United States').replace('amicus curiae', 'amicus curiae')


def head_docket(t):
    m = re.search(r'Nos?\.\s*(\d{2}-\d{1,5})', t[:600])
    return dk_norm(m.group(1)) if m else None


# ------------------------------------------------------------------ main
def main():
    lo, hi = (int(x) for x in arg('--terms', '1982-2017').split('-'))
    limit = int(arg('--limit', '0'))
    S = load_js('docs/data/scotus.js')['cases']
    have = set(load_js('docs/data/auth-index.js').values())     # dockets already covered (e-filed briefs)
    imp = load_js('docs/data/case_impact.js')['c']
    by_term, by_dk = {}, {}
    for c in S:
        if not str(c.get('t', '')).isdigit() or not (lo <= int(c['t']) <= hi + 1) or not c.get('d'):
            continue
        if not c.get('arg') and c.get('s') == 1:
            continue
        for dk in re.split(r'[,;\s]+', c['d']):
            dk = dk_norm(dk)
            if dk and dk not in have:
                by_dk.setdefault(dk, c)
        by_term.setdefault(int(c['t']), []).append(c)
    man = json.load(open(MAN)) if os.path.exists(MAN) else {}
    rows = []
    for term in range(lo, hi + 1):
        r = listing(term)
        print('term', term, len(r), 'listed', flush=True)
        rows += r
    # match rows to cases
    want = {}       # case id -> [(row, docket)]
    for r in rows:
        if r['type'] and r['type'] not in MERITS_TYPES:
            continue
        if re.search(r'\((?:Opposition|Petition|Invitation|Response|Supplemental)\)|\bOpposition\b', r['title'], re.I):
            continue
        if not r['media']:
            continue
        c, dk = None, None
        for d in row_dockets(r['no']):
            if d in by_dk:
                c, dk = by_dk[d], d
                break
        if not c and not r['no'].strip():
            c = name_match(r['title'], by_term.get(r['term'], []) + by_term.get(r['term'] + 1, []))
            if c:
                dk = next((dk_norm(d) for d in re.split(r'[,;\s]+', c['d']) if dk_norm(d) in by_dk), None)
                if not dk:
                    c = None
        if c:
            want.setdefault(c['id'], []).append((r, dk))
    order = sorted(want, key=lambda cid: -(imp.get(cid) or [0, 0])[1])
    print(len(rows), 'rows;', sum(len(v) for v in want.values()), 'matched to', len(want), 'cases', flush=True)
    stats = {'briefs': 0, 'skipped': 0, 'cases': 0}
    for n, cid in enumerate(order):
        if limit and n >= limit:
            break
        entries = want[cid]
        dk = entries[0][1]
        os.makedirs(f'{OUT}/{dk}', exist_ok=True)
        prev = man.get(dk, {})
        done = {b['url'] for b in prev.get('briefs', [])} | set(prev.get('skipped', []))
        briefs, skipped = list(prev.get('briefs', [])), list(prev.get('skipped', []))
        for r, _ in entries:
            for mh in r['media']:
                url = BASE + mh.split('?')[0] + '?inline'
                if url in done:
                    continue
                mid = re.search(r'/media/(\d+)/', mh).group(1)
                dest = f'{OUT}/{dk}/osg-{mid}.txt'
                if not to_text(url, dest):
                    skipped.append(url)
                    continue
                t = open(dest, encoding='utf-8', errors='replace').read()
                hd = head_docket(t)
                got = classify(t, r['title'])
                if not got or (hd and hd != dk and hd not in [dk_norm(x) for x in re.split(r'[,;\s]+', by_dk[dk]['d'])]):
                    skipped.append(url)
                    os.remove(dest)
                    stats['skipped'] += 1
                    continue
                kind, label = got
                briefs.append({'k': kind, 'f': f'osg-{mid}', 'label': label, 'date': r['date'], 'url': url,
                               'detail': BASE + r['detail'] if r['detail'] else '', 'src': 'osg',
                               'fmt': 'PDF' if 'Page Break' not in t[:20000] and '\f' in t else 'Text'})
                stats['briefs'] += 1
        # one brief per kind at most for petitioner / respondent (a re-listed duplicate); replies and amici may repeat
        seen, keep = set(), []
        for b in sorted(briefs, key=lambda b: b['date']):
            key = (b['k'], b['label'])
            if key in seen:
                continue
            seen.add(key)
            keep.append(b)
        entry = {'briefs': keep, 'skipped': skipped, 'id': cid, 'opinion': prev.get('opinion')}
        case = by_dk[dk]
        if keep and '--no-opinions' not in sys.argv and not entry['opinion'] and re.match(r'https://tile\.loc\.gov/', case.get('pdf') or ''):
            if to_text(case['pdf'], f'{OUT}/{dk}/opinion.txt', pause=3):
                entry['opinion'] = case['pdf']
        man[dk] = entry
        stats['cases'] += bool(keep)
        if n % 10 == 0:
            print(n, '/', len(order), dk, case['n'][:50], len(keep), 'briefs', flush=True)
            json.dump(man, open(MAN, 'w'), indent=0)
    json.dump(man, open(MAN, 'w'), indent=0)
    print('done', stats, flush=True)


if __name__ == '__main__':
    main()
