"""Cache the Solicitor General's merits briefs for argued Supreme Court cases from before e-filing (October Terms
1982-2017), for build_authorities.py.

Source: the Office of the Solicitor General's brief archive, https://www.justice.gov/osg/supreme-court-briefs
(works of the U.S. Government, not under copyright; robots.txt allows /osg/). It lists every brief the Office filed
from OT1982 on, by Term: the briefs of the United States (and federal agencies and officers) as a party, and as amicus
curiae. Briefs to about 2004 are plain-text OCR of the printed briefs (served as "PDF" but text/plain); later ones are
text PDFs. Other parties' briefs are not in it, so a case gets the federal government's side only, and only where the
government took part (about two thirds of argued cases).

Steps (each cached, so a run can be stopped and resumed):
  1. for each argued case without authorities data, the archive rows whose title contains a distinctive party name
     (its title filter; the table's further pages are disallowed by robots.txt)   data/raw/osg/list/<word>-<term>.html
  2. rows matched to the case by docket number, or by both party names when the row has no number, filed in the
     case's Term or the one before or after; merits-stage types only where the row is typed
  3. each matched brief's text                  data/raw/briefs/<docket>/osg-<media id>.txt
     classified from its cover (merits stage only: "On writ of certiorari" / "On appeal", not "in opposition",
     petitions, memoranda or supplemental briefs) into petitioner / respondent / reply / united-states (amicus)
  4. (--opinions, a separate process: another host) the opinion from the U.S. Reports, the site's tile.loc.gov PDF of
     the case                                    data/raw/briefs/<docket>/opinion.txt, data/raw/briefs/osg-opinions.json
Output: data/raw/briefs/osg-manifest.json ({docket: {briefs: [...]}}) and osg-opinions.json ({docket: url}), read by
build_authorities.py alongside manifest.json. Cases are fetched in order: the site's essential cases, then the most cited (docs/data/case_impact.js).
User-Agent "LexConstitutio/1.0 (static site build)"; about one request per 1.5 s (justice.gov) and 3 s (loc.gov).
Run from the repo root:  python scripts/osg_briefs_fetch.py [--terms 1982-2017] [--limit N]
                    and, at the same time,  python scripts/osg_briefs_fetch.py --opinions [--follow]
                    (--relabel re-reads the cached briefs' covers after a change to classify(); no fetching)
"""
import html, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

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
# The archive's table pages past the first (?page=n) are disallowed by justice.gov's robots.txt and refused (403) to
# non-browser clients, so it is read through its title filter instead: for each case, the briefs whose title contains a
# distinctive party name, first in all Terms and, when that fills the 25-row first page, in the case's Term and the one
# before (when merits briefs of a case granted late in a Term are filed).
def cell(x):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', x))).strip()


def query(word, term='All'):
    os.makedirs(LIST, exist_ok=True)
    p = f"{LIST}/{re.sub(r'[^a-z0-9]+', '_', word.lower())}-{term}.html"
    if not os.path.exists(p):
        t = '2025_term' if term == 2025 else str(term)
        b = get(f'{BASE}/osg/supreme-court-briefs?sc_term={t}&type=All&subject=All&text={urllib.parse.quote(word)}')
        open(p, 'wb').write(b)
    h = open(p, encoding='utf-8', errors='replace').read()
    rows = []
    for tr in re.findall(r'<tr>(.*?)</tr>', h, re.S):
        td = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(td) < 7:
            continue
        det = re.search(r'href="(/osg/brief/[^"]+)"', td[2])
        media = re.findall(r'href="(/osg/media/\d+/dl[^"]*)"', td[3])
        dt = re.search(r'datetime="(\d{4}-\d\d-\d\d)', td[6])
        tm = re.match(r'(\d{4})', cell(td[0]))
        rows.append({'term': int(tm.group(1)) if tm else 0, 'no': cell(td[1]), 'title': cell(td[2]), 'type': cell(td[4]),
                     'date': dt.group(1) if dt else '', 'detail': det.group(1) if det else '', 'media': media})
    return rows


GENERIC = set('''united states state states city county commissioner people secretary attorney general board department
commonwealth town village school district government federal national american the of in re ex parte matter inc co corp
llc ltd company corporation association international commission service services authority administrator director
warden superintendent bureau office trust bank et al and motor'''.split()) | set(w.lower() for w in '''Alabama Alaska Arizona
Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana
Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Hampshire Jersey Mexico York Carolina
Dakota Ohio Oklahoma Oregon Pennsylvania Rhode Island Tennessee Texas Utah Vermont Virginia Washington West Wisconsin Wyoming
North South'''.split())


def search_words(name):
    """A distinctive word of each side of the case name, petitioner's first ("Burwell v. Hobby Lobby Stores" ->
    Burwell, Hobby): the archive titles a case by its name when the brief was filed, which may name another officer."""
    m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+)$', name)
    out = []
    for side in ([m.group(1), m.group(2)] if m else [name]):
        w = next((w for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", side) if len(w) >= 3 and w.lower() not in GENERIC), None)
        if w and w not in out:
            out.append(w)
    return out


def search_word(name):
    return (search_words(name) or [None])[0]


def rows_for(case, w):
    rows = query(w)
    if len(rows) >= 25:
        t = int(case['t'])
        rows = query(w, t) + query(w, t - 1)
    return rows


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
    lines = [norm(x) for x in c.splitlines() if x.strip()]
    label = ''
    for i, ln in enumerate(lines):
        m = re.search(r'\b(?:REPLY )?BRIEFS? (?:FOR|OF)\b.*$', ln.upper())
        if m and not re.search(r'COURT OF|^ON ', ln.upper()):
            label = ln[m.start():]
            for nx in lines[i + 1: i + 3]:     # "BRIEF FOR THE UNITED STATES AS AMICUS CURIAE" / "SUPPORTING RESPONDENTS"
                if re.match(r'^(?:AS|SUPPORTING|IN SUPPORT|URGING|FOR|OF|AND|ON BEHALF|AMICUS|AMICI|CURIAE|PETITIONERS?|RESPONDENTS?)\b', nx.upper()) and len(label) < 200:
                    label += ' ' + nx
                else:
                    break
            break
    # a cover read as one line runs on into the Solicitor General's name
    label = re.split(r'\s+(?=[A-Z][A-Za-z.]*(?: [A-Z][A-Za-z.]*){0,3},? (?:Jr\.,? |III,? |II,? )?(?:Solicitor|Acting Solicitor|Attorney|Assistant|Deputy|Counsel)\b)|\s+(?:Solicitor General|Counsel of Record)\b', label)[0]
    label = (label or 'BRIEF FOR THE UNITED STATES')[:200].strip(' ,.')
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
        cap = re.sub(r'^.*?(?:OCTOBER TERM,? \d{4}|SUPREME COURT OF THE UNITED STATES)', '', cap)
        parts = re.split(r'\s+V\.?\s+', cap, 1)
        pet_gov = len(parts) == 2 and re.search(GOVWORDS, parts[0])
        kind = 'petitioner' if pet_gov else 'respondent'
    lab = label[:1].upper() + label[1:].lower()
    for w in ('United States', 'Secretary', 'Commissioner', 'Attorney General'):
        lab = re.sub(r'\b' + w.lower() + r'\b', w, lab)
    return kind, lab


def norm(s):
    return re.sub(r'\s+', ' ', s).strip()


def head_docket(t):
    m = re.search(r'Nos?\.\s*(\d{2}-\d{1,5})', t[:600])
    return dk_norm(m.group(1)) if m else None


# ------------------------------------------------------------------ 4. opinions (a separate pass, another host)
OPS = f'{OUT}/osg-opinions.json'


def opinions(follow=False):
    """The U.S. Reports text of each case that has briefs here: the site's tile.loc.gov PDF of the case, to
    data/raw/briefs/<docket>/opinion.txt, listed in osg-opinions.json ({docket: url}). Runs alongside the briefs pass
    (it only reads osg-manifest.json); with --follow it keeps picking up new cases until the manifest stops growing."""
    S = {c['id']: c for c in load_js('docs/data/scotus.js')['cases']}
    ops = json.load(open(OPS)) if os.path.exists(OPS) else {}
    idle = 0
    while True:
        try:
            man = json.load(open(MAN))
        except (OSError, ValueError):
            man = {}
        todo = [dk for dk, v in man.items() if not dk.startswith('_') and v.get('briefs') and dk not in ops
                and re.match(r'https://tile\.loc\.gov/', (S.get(v.get('id')) or {}).get('pdf') or '')]
        for dk in todo:
            url = S[man[dk]['id']]['pdf']
            if to_text(url, f'{OUT}/{dk}/opinion.txt', pause=3):
                ops[dk] = url
            else:
                ops[dk] = None
            if len(ops) % 20 == 0:
                json.dump(ops, open(OPS, 'w'), indent=0)
                print('opinions', len(ops), dk, flush=True)
        json.dump(ops, open(OPS, 'w'), indent=0)
        if not follow:
            return
        idle = 0 if todo else idle + 1
        if idle >= 20:
            return
        time.sleep(30)


def relabel():
    """Re-read the cover of every cached brief (no fetching), after a change to classify()."""
    man = json.load(open(MAN))
    n = 0
    for dk, v in man.items():
        if dk.startswith('_'):
            continue
        for b in v['briefs']:
            p = f"{OUT}/{dk}/{b['f']}.txt"
            got = classify(open(p, encoding='utf-8', errors='replace').read()) if os.path.exists(p) else None
            if got and (b['k'], b['label']) != got:
                b['k'], b['label'] = got
                n += 1
    json.dump(man, open(MAN + '.tmp', 'w'), indent=0)
    os.replace(MAN + '.tmp', MAN)
    print('relabelled', n)


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
    cases = {}
    for dk, c in by_dk.items():
        if lo <= int(c['t']) <= hi:
            cases[c['id']] = c
    ess = set(load_js('docs/data/essential.js'))     # the site's essential cases first, then the most cited
    order = sorted(cases, key=lambda cid: (cid not in ess, -(imp.get(cid) or [0, 0])[1]))
    print(len(order), 'argued cases without authorities in OT', lo, '-', hi, flush=True)

    def matches(c):
        """[(row, docket)] of the archive's merits-stage rows for this case."""
        dks = [dk_norm(d) for d in re.split(r'[,;\s]+', c['d']) if d]
        out = []
        for w in search_words(c['n']):
            out = matches_word(c, w, dks)
            if out:
                break
        return out

    def matches_word(c, w, dks):
        out = []
        for r in rows_for(c, w):
            if r['type'] and r['type'] not in MERITS_TYPES:
                continue
            if re.search(r'\((?:Opposition|Petition|Invitation|Response|Supplemental)\)|\bOpposition\b|- Petition\b', r['title'], re.I):
                continue
            if not r['media'] or not (int(c['t']) - 1 <= r['term'] <= int(c['t']) + 1):
                continue
            rd = row_dockets(r['no'])
            if rd:
                hit = next((d for d in rd if d in dks), None)
                if hit:
                    out.append((r, hit))
            elif name_match(r['title'], [c]):
                out.append((r, next((d for d in dks if d in by_dk), dks[0])))
        return out
    stats = {'briefs': 0, 'skipped': 0, 'cases': 0}
    done_ids = set(man.get('_none2', [])) | {v.get('id') for k, v in man.items() if k != '_none' and v.get('done')}
    for n, cid in enumerate(order):
        if limit and n >= limit:
            break
        case = cases[cid]
        if cid in done_ids:
            continue
        try:
            entries = matches(case)
        except Exception as e:
            print('  query failed', case['n'], e, flush=True)
            continue
        if not entries:
            man['_none2'] = sorted(set(man.get('_none2', [])) | {cid})     # tried with both sides' names
            if len(man['_none2']) % 10 == 0:
                json.dump(man, open(MAN + '.tmp', 'w'), indent=0)
                os.replace(MAN + '.tmp', MAN)
            continue
        dk = entries[0][1]
        os.makedirs(f'{OUT}/{dk}', exist_ok=True)
        prev = man.get(dk, {})
        done = {b['url'] for b in prev.get('briefs', [])} | set(prev.get('skipped', []))
        briefs, skipped = list(prev.get('briefs', [])), list(prev.get('skipped', []))
        for b in briefs:        # re-read the covers of briefs fetched before (the classifier may have improved)
            p = f"{OUT}/{dk}/{b['f']}.txt"
            got = classify(open(p, encoding='utf-8', errors='replace').read()) if os.path.exists(p) else None
            if got:
                b['k'], b['label'] = got
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
                if not got or (hd and hd != dk and hd not in [dk_norm(x) for x in re.split(r'[,;\s]+', case['d'])]):
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
        entry = {'briefs': keep, 'skipped': skipped, 'id': cid, 'done': True}
        man[dk] = entry
        stats['cases'] += bool(keep)
        if n % 10 == 0:
            print(n, '/', len(order), dk, case['n'][:50], len(keep), 'briefs', flush=True)
        tmp = MAN + '.tmp'      # written every case, atomically (the opinions pass reads it meanwhile)
        json.dump(man, open(tmp, 'w'), indent=0)
        os.replace(tmp, MAN)
    json.dump(man, open(MAN, 'w'), indent=0)
    print('done', stats, flush=True)


if __name__ == '__main__':
    if '--relabel' in sys.argv:
        relabel()
    elif '--opinions' in sys.argv:
        opinions(follow='--follow' in sys.argv)
    else:
        main()
