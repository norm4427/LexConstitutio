"""Build the Authorities tab of the Supreme Court case pages: docs/data/auth/<docket>.js (one per case) and
docs/data/auth-index.js.

Inputs
  data/raw/briefs/<docket>/*.txt and manifest.json   merits briefs and slip opinion text (scripts/briefs_fetch.py)
  data/raw/transcripts/<term>/<docket>_*.txt         official argument transcripts (scripts/transcripts_fetch.py)
  data/raw/briefs/usc/<title>-<section>.html         U.S. Code sections, 2024 edition, from govinfo.gov
                                                     (fetched here, once, for each case's most-cited sections)
  docs/data/scotus.js, docs/data/docket.js           the site's cases (to link authorities to case pages)
  docs/data/constitution.js                          the Annotated Constitution (clause pages and text)

Method
  1. Table of Authorities. Each brief's table is the text from its "TABLE OF AUTHORITIES" heading to the first heading
     of the brief proper (Introduction, Opinions Below, Statement, Interest of Amicus, ...). Entries end with a dot leader
     and their page references ("Jones v. Bock, 549 U.S. 199 (2007) ......... 9, 21"); section headings (Cases,
     Statutes, ...) are read where they begin an entry. Entries are kept only when they parse as
       a case          a party name with "v." / "In re" / "Ex parte" and a reporter citation (U.S., S. Ct., F.3d, ...)
       the Constitution "U.S. Const." with an article or amendment (or "Art."/"Amend." entries under that heading)
       a federal statute a U.S. Code section ("15 U.S.C. § 77p(b)") or a public law number
       a regulation    C.F.R. sections and Federal Register pages
       a federal rule  Fed. R. Civ. P., Crim. P., Evid., App. P.
     Other entries (articles, books, legislative history, state statutes) are left out.
  2. Links. A case links to its page on this site when its U.S. Reports or Supreme Court Reporter citation is a case in
     docs/data/scotus.js (for U.S. citations whose page is not yet assigned, when the volume and both party names agree);
     other U.S. cases link to Justia, other reporters to CourtListener's citation lookup. Constitutional provisions link
     to the Annotated Constitution clause pages for that article/section/clause or amendment/section. Statutes link to
     Cornell LII (U.S. Code), govinfo (public laws, Federal Register) and eCFR (C.F.R.).
  3. Quotations, verbatim from the source, each attributed:
       briefs and the opinion  a passage in quotation marks immediately followed by a citation to the authority
                               ("... the reviewing court shall decide all relevant questions of law ..." 5 U.S.C. §706)
       oral argument           the sentence in which a speaker names the authority (the case's distinctive party name,
                               or "section <n>" when only one cited section has that number)
  4. Statutory text: the full section from the U.S. Code (govinfo, 2024 edition) for each case's most-cited sections.
Run from the repo root (after briefs_fetch.py):  python scripts/build_authorities.py [--no-fetch]
"""
import collections, glob, html, json, os, re, sys, time, urllib.parse, urllib.request

RAW = 'data/raw/briefs'
OUT = 'docs/data/auth'
UA = {'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0 (academic research index)'}
FETCH = '--no-fetch' not in sys.argv

ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10, 'XI': 11, 'XII': 12,
         'XIII': 13, 'XIV': 14, 'XV': 15, 'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20, 'XXI': 21, 'XXII': 22,
         'XXIII': 23, 'XXIV': 24, 'XXV': 25, 'XXVI': 26, 'XXVII': 27}
ORD = {w: i + 1 for i, w in enumerate('first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split())}
ORD.update({'twenty-first': 21, 'twenty-second': 22, 'twenty-third': 23, 'twenty-fourth': 24, 'twenty-fifth': 25, 'twenty-sixth': 26, 'twenty-seventh': 27})
TOROMAN = {v: k for k, v in ROMAN.items()}


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def norm_ws(s):
    return re.sub(r'\s+', ' ', s).strip()


# ------------------------------------------------------------------ the site's cases
GENERIC = set('united states state states city county commissioner people secretary attorney general board department '
              'commonwealth town village school district government federal national american the of in re ex parte matter '
              'inc co corp llc ltd company corporation association'.split())


def party_key(name):
    """('loper', 'raimondo') from 'Loper Bright Enterprises, Inc. v. Raimondo': first word of each side."""
    m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+)$', name)
    if not m:
        return None
    w = lambda s: (re.findall(r"[A-Za-z][A-Za-z'’\-]*", s) or [''])[0].lower().replace('’', "'")
    return w(m.group(1)), w(m.group(2))


S = load_js('docs/data/scotus.js')
K = load_js('docs/data/docket.js')
CASES = [c for c in S['cases']]
by_us, by_sct, by_vol = {}, {}, collections.defaultdict(list)
for c in CASES:
    for cit in (c.get('cit'), c.get('citUS')):
        m = re.match(r'^(\d+) (U\.S\.|S\. Ct\.) (\d+|_+)$', cit or '')
        if not m:
            continue
        if m.group(3).isdigit():
            (by_us if m.group(2) == 'U.S.' else by_sct).setdefault(f'{m.group(1)}|{m.group(3)}', c)
        if m.group(2) == 'U.S.':
            by_vol[m.group(1)].append(c)
dk_case = {}
site_by_id = {c["id"]: c for c in CASES}
for c in CASES:
    for dk in re.split(r'[,;\s]+', (c.get('d') or '').lower()):
        if dk:
            dk_case.setdefault(dk, c)
for e in K['cases']:
    dk_case.setdefault(e['d'].lower(), {'id': e['id'], 'n': e['n'], 't': e.get('t'), 'pending': True})

CON = load_js('docs/data/constitution.js')
UNITS = {u['id']: u for u in CON['units']}
CLAUSES_BY_UNIT = collections.defaultdict(list)
for cl in CON['clauses']:
    CLAUSES_BY_UNIT[cl['unit']].append(cl)


# ------------------------------------------------------------------ table of authorities
TOA_START = re.compile(r'^[ \t\f]*(?:[ivx]+\s+)?TABLE OF (?:CITED )?AUTHORITIES(?![ \t]*(?:[.·…][ \t]?){2})(?![^\n]*(?:[Cc]ontinued|CONTINUED))', re.M | re.I)
TOA_END = re.compile(r'^[ \t]*(?:IN THE[ \t]*$|INTRODUCTION[ \t]*$|OPINIONS? BELOW|STATEMENT(?: OF (?:THE )?CASE)?[ \t]*$|SUMMARY OF (?:THE )?ARGUMENT'
                     r'|INTEREST OF|JURISDICTION(?:AL STATEMENT)?[ \t]*$|QUESTIONS? PRESENTED[ \t]*$|(?:REPLY )?BRIEF (?:FOR|OF) |REPLY BRIEF'
                     r'|.{0,60}PROVISIONS INVOLVED|PRELIMINARY STATEMENT|ARGUMENT[ \t]*$|STATEMENT OF INTEREST)', re.M)
CONTD = re.compile(r'^.*TABLE OF (?:CITED )?AUTHORITIES.*$|^\s*Page\(?s?\)?\s*$|^\s*[ivxlc]+\s*$|^\s*\d+\s*$|^\s*\(?[Cc]ontinued\)?\s*$', re.M | re.I)
PG = r'(?:passim|\d+(?:\s*[-–]\s*\d+)?(?:\s*(?:n|nn)\.?\s*\d+(?:\s*[-–,&]\s*\d+)*)?|[ivxl]+)'
ENTRY_END = re.compile(r'(?:\s*[.·…](?:\s*[.·…]){2,})\s*(%s(?:\s*,\s*%s)*)(?=\s|$)' % (PG, PG))
HEAD_WORDS = r'(?:supreme|court|circuit|federal|state|foreign|constitutional|constitution|provisions?|statutes?|statutory|regulations?|regulatory|rules?|legislative|materials|history|other|authorities|miscellaneous|treaties|executive|administrative|agency|cases|and|&|,|books|articles|secondary|sources|orders?)'
HEAD = re.compile(r'^\s*((?:%s\s*)+?)\s*(?:\(continued\)|—continued|-continued)?\s*:?\s*(?=[A-Z0-9§“"])' % HEAD_WORDS, re.I)
BODY_START = None


def toa_text(t):
    for m in TOA_START.finditer(t):
        nxt = t[m.end(): m.end() + 400]
        if re.match(r'\s*[.·…]{3}', nxt):
            continue
        e = TOA_END.search(t, m.end() + 200)
        end = e.start() if e and e.start() - m.end() < 80000 else m.end() + 30000
        return t[m.end(): end], end
    return '', 0


def toa_entries(t):
    """[(section heading, entry text, pages)] from the table's text."""
    body = norm_ws(CONTD.sub(' ', t))
    body = re.sub(r'\bPage\(?s?\)?(?=\s+(?:[A-Z]{3,}|Cases|Statutes|Constitution|Federal|Supreme|State)\b)|^\s*Page\(?s?\)?\s', ' ', body)
    out, pos, sec = [], 0, ''
    for m in ENTRY_END.finditer(body):
        txt = body[pos: m.start()].strip(' ,;')
        pos = m.end()
        h = HEAD.match(txt)
        if h and re.search(r'cases|constitution|statut|regulat|rules|legislat|authorit|miscell|treat|books|articles|sources|orders', h.group(1), re.I) \
                and (':' in txt[:h.end()] or h.group(1).strip().isupper() or len(h.group(1).split()) <= 4):
            sec = h.group(1).strip(' :,').lower()
            txt = txt[h.end():].strip()
        if txt:
            out.append((sec, txt, m.group(1)))
    return out


# ------------------------------------------------------------------ citations
REP = r"U\.\s?S\.|S\.\s?Ct\.|L\.\s?Ed\.(?:\s?2d)?|F\.\s?(?:2d|3d|4th)|F\.\s?Supp\.(?:\s?(?:2d|3d))?|F\.\s?App(?:’|')x|F\.|[A-Z][A-Za-z.]*(?:\s[A-Z][A-Za-z.]*){0,3}(?:\s?(?:2d|3d|4th|5th))?"
CASE = re.compile(r"^(?P<name>(?:(?!\d+\s+(?:%s)\s+\d).)+?(?:\sv\.\s|^In re\s|^Ex parte\s|^Matter of\s).*?),\s*(?P<vol>\d+)\s+(?P<rep>%s)\s+(?P<page>\d+|_{2,})(?P<rest>.*)$" % (REP, REP))
USC = re.compile(r'(\d+)\s+U\.\s?S\.\s?C\.(?:\s?A\.)?\s*(?:§§?|[Ss]ec(?:tion|s)?\.?|[Ss]ections?)?\s*(\d+[A-Za-z]*(?:[-–]\d+[A-Za-z]*)?)((?:\s?\([0-9A-Za-z]{1,6}\))*)')
PUBL = re.compile(r'Pub\.\s?L\.\s?(?:No\.\s?)?(\d{2,3})[-–](\d{1,4})')
STAT = re.compile(r'(\d{1,3})\s+Stat\.\s+(\d{1,5})')
CFR = re.compile(r'(\d+)\s+C\.\s?F\.\s?R\.\s*(?:§§?|[Pp]t\.|[Pp]art)?\s*(\d+(?:\.\d+[a-z]?(?:-\d+)?)?)((?:\([0-9a-z]{1,4}\))*)')
FEDREG = re.compile(r'(\d{1,3})\s+Fed\.\s?Reg\.\s+(\d[\d,]*)')
RULE = re.compile(r'Fed\.\s?R\.\s?(Civ|Crim|Evid|App)\.\s?(?:P\.\s?)?(\d+(?:\.\d)?)((?:\([0-9a-zA-Z]{1,4}\))*)')
RULE_LII = {'Civ': ('frcp', 'Fed. R. Civ. P.'), 'Crim': ('frcrmp', 'Fed. R. Crim. P.'), 'Evid': ('fre', 'Fed. R. Evid.'), 'App': ('frap', 'Fed. R. App. P.')}
CONST = re.compile(r'\bU\.\s?S\.\s?Const(?:itution)?\b\.?,?\s*(.*)$', re.I)
STATE_CONST = re.compile(r'\b(?:[A-Z][a-z]+\.?\s){1,2}Const\.', re.I)


def rep_norm(r):
    r = norm_ws(r.replace("'", '’'))
    r = re.sub(r'U\.\s?S\.', 'U.S.', r)
    r = re.sub(r'S\.\s?Ct\.', 'S. Ct.', r)
    r = re.sub(r'F\.\s?(2d|3d|4th)', r'F.\1', r)
    r = re.sub(r'F\.\s?Supp\.\s?', 'F. Supp. ', r).strip()
    return r


by_pk_year = collections.defaultdict(list)
for c in CASES:
    pk = party_key(c['n'])
    if pk and c.get('y'):
        by_pk_year[(pk, int(c['y']))].append(c)


def site_case(vol, rep, page, name, year=None):
    if rep == 'U.S.' and page.isdigit():
        c = by_us.get(f'{vol}|{page}')
        if c:
            return c
    if rep == 'S. Ct.' and page.isdigit():
        c = by_sct.get(f'{vol}|{page}')
        if c:
            return c
    pk = party_key(name)
    if rep == 'U.S.' and pk:     # volume known, page not yet assigned (or not recorded on the site): both party names must agree
        hits = [c for c in by_vol.get(vol, []) if party_key(c['n']) == pk]
        if len(hits) == 1:
            return hits[0]
    if rep in ('U.S.', 'S. Ct.') and pk and year:   # the site records another reporter: both party names and the year
        hits = by_pk_year.get((pk, year), [])
        if len(hits) == 1:
            return hits[0]
    return None


def parse_case(txt):
    m = CASE.match(txt)
    if not m:
        return None
    name = norm_ws(m.group('name'))
    name = re.sub(r'^(?:See\s+|Cf\.\s+|also\s+)', '', name)
    name = re.sub(r',\s*(?:Nos?\.|Civ\.|Case No\.|Civil Action).*$', '', name)
    if len(name) > 160 or len(name) < 5:
        return None
    vol, rep, page = m.group('vol'), rep_norm(m.group('rep')), m.group('page')
    yr = re.search(r'\((?:[^()]*?\s)?(1[7-9]\d\d|20\d\d)\)', m.group('rest'))
    court = re.search(r'\(([^()]*?)\s*(?:1[7-9]\d\d|20\d\d)\)', m.group('rest'))
    it = {'t': 'case', 'label': name, 'cite': f'{vol} {rep} {page}', 'vol': vol, 'rep': rep, 'page': page,
          'y': int(yr.group(1)) if yr else None}
    if court and court.group(1).strip(' ,'):
        it['court'] = court.group(1).strip(' ,')
    c = site_case(vol, rep, page, name, it['y'])
    if c:
        it['id'] = c['id']
        it['sc'] = 1
    elif rep in ('U.S.', 'S. Ct.') or (rep.startswith('L. Ed')):
        it['sc'] = 1
        if rep == 'U.S.' and page.isdigit():
            it['url'] = f'https://supreme.justia.com/cases/federal/us/{vol}/{page}/'
        elif page.isdigit():
            it['url'] = f'https://www.courtlistener.com/c/{urllib.parse.quote(rep)}/{vol}/{page}/'
    elif rep in ('WL', 'LEXIS', 'U.S. Dist. LEXIS', 'U.S. App. LEXIS') or 'LEXIS' in rep:
        pass
    elif page.isdigit():
        it['url'] = f'https://www.courtlistener.com/c/{urllib.parse.quote(rep)}/{vol}/{page}/'
    it['key'] = 'case:' + (it.get('id') or f'{vol} {rep} {page}')
    return it


def roman_or_int(s):
    s = s.strip().upper().rstrip('.')
    return int(s) if s.isdigit() else ROMAN.get(s)


def parse_const(txt, in_const_section):
    m = CONST.search(txt)
    rest = m.group(1) if m else (txt if in_const_section and not STATE_CONST.search(txt) else None)
    if rest is None:
        return None
    rest = rest.strip()
    am = re.match(r'(?:amend(?:ment|s?\.)?|Amdt\.)\s*([IVXL]+|\d+)\b', rest, re.I)
    ar = re.match(r'(?:art(?:icle|\.)?)\s*([IVX]+|\d+)\b', rest, re.I)
    ow = re.match(r'(%s)\s+Amendment' % '|'.join(sorted(ORD, key=len, reverse=True)), rest, re.I)
    sec = re.search(r'(?:§+|[Ss]ec(?:tion|\.)?)\s*(\d+)', rest)
    cl = re.search(r'\bcl(?:ause|s?\.)\s*(\d+)', rest, re.I)
    if am or ow:
        n = roman_or_int(am.group(1)) if am else ORD[ow.group(1).lower()]
        if not n:
            return None
        base = f'am{n}'
        label = f'Amendment {TOROMAN.get(n, n)}' + (f', Section {sec.group(1)}' if sec else '')
        units = [base] if base in UNITS else [u for u in UNITS if re.match(base + r's\d+$', u)]
        if sec:
            units = [u for u in units if u == f'{base}s{sec.group(1)}'] or ([base] if base in UNITS else [])
    elif ar:
        n = roman_or_int(ar.group(1))
        if not n or n > 7:
            return None
        base = f'a{n}'
        label = f'Article {TOROMAN.get(n, n)}' + (f', Section {sec.group(1)}' if sec else '') + (f', Clause {cl.group(1)}' if cl else '')
        pref = base + (f's{sec.group(1)}' if sec else '')
        if cl:
            units = [u for u in UNITS if u in (f'{pref}c{cl.group(1)}', f'{base}c{cl.group(1)}')] if (sec or n in (5, 6)) else []
        else:
            units = [u for u in UNITS if re.match(re.escape(pref) + (r'c\d+$' if sec else r'(?:s\d+)?c\d+$'), u)]
    else:
        return None
    it = {'t': 'const', 'label': label, 'key': 'const:' + label}
    clauses = [cl_ for u in units for cl_ in CLAUSES_BY_UNIT.get(u, [])]
    named = [c for c in clauses if re.search(re.escape(c['name'].split(' (')[0].replace(' Clause', '')), txt, re.I)]
    if named:
        clauses = named
    if clauses and len(clauses) <= 8:
        it['clauses'] = [[c['id'], c['name']] for c in clauses]
    if len(units) == 1:
        it['text'] = UNITS[units[0]]['text']
    elif 1 < len(units) <= 3:
        it['text'] = ' '.join(UNITS[u]['text'] for u in units)
    return it


def usc_section(sec):
    sec = sec.replace('–', '-')
    m = re.match(r'^(\d+)-(\d+)$', sec)
    if m and int(m.group(2)) > int(m.group(1)):     # a range of sections: the first
        return m.group(1)
    return sec


def parse_statutes(txt, sec_head):
    """Federal statutes, regulations and rules named in one table entry (one entry may list several)."""
    out = []
    for m in USC.finditer(txt):
        t, s = m.group(1), usc_section(m.group(2))
        sub = m.group(3).replace(' ', '')
        out.append({'t': 'usc', 'title': int(t), 'sec': s, 'sub': sub, 'key': f'usc:{t}:{s}',
                    'label': f'{t} U.S.C. § {s}', 'url': f'https://www.law.cornell.edu/uscode/text/{t}/{s}'})
    if not out:
        m = PUBL.search(txt)
        if m and int(m.group(1)) >= 80:
            nm = norm_ws(txt[:m.start()].strip(' ,;'))
            nm = nm if 3 < len(nm) < 120 and not re.search(r'\d{3,}', nm) else ''
            it = {'t': 'law', 'label': (nm + ', ' if nm else '') + f'Pub. L. No. {m.group(1)}-{m.group(2)}', 'key': f'law:{m.group(1)}-{m.group(2)}'}
            if int(m.group(1)) >= 104:
                it['url'] = f'https://www.govinfo.gov/link/plaw/{m.group(1)}/public/{m.group(2)}'
            else:
                st = STAT.search(txt)
                if st and 65 <= int(st.group(1)) <= 124:
                    it['url'] = f'https://www.govinfo.gov/link/statute/{st.group(1)}/{st.group(2)}'
            out.append(it)
    for m in CFR.finditer(txt):
        t, s = m.group(1), m.group(2)
        part = s.split('.')[0]
        url = f'https://www.ecfr.gov/current/title-{t}/section-{s}' if '.' in s else f'https://www.ecfr.gov/current/title-{t}/part-{part}'
        out.append({'t': 'reg', 'label': f'{t} C.F.R. § {s}' if '.' in s else f'{t} C.F.R. pt. {s}', 'key': f'cfr:{t}:{s}', 'url': url, 'sub': m.group(3)})
    if not any(x['t'] == 'reg' for x in out):
        for m in FEDREG.finditer(txt):
            v, p = m.group(1), m.group(2).replace(',', '')
            nm = norm_ws(txt[:m.start()].strip(' ,;'))
            out.append({'t': 'reg', 'label': (nm[:140] + ', ' if 3 < len(nm) < 200 else '') + f'{v} Fed. Reg. {m.group(2)}', 'key': f'fr:{v}:{p}',
                        'url': f'https://www.govinfo.gov/link/fr/{v}/{p}'})
            break
    for m in RULE.finditer(txt):
        code, lab = RULE_LII[m.group(1)]
        n = m.group(2)
        out.append({'t': 'rule', 'label': f'{lab} {n}', 'sub': m.group(3), 'key': f'rule:{code}:{n}', 'url': f'https://www.law.cornell.edu/rules/{code}/rule_{n}'})
    return out


def classify(sec, txt, prev_const):
    """Authorities in one table entry."""
    txt = re.sub(r'^(?:See,?\s+|Cf\.\s+)', '', txt)
    in_const = 'constitution' in sec or prev_const
    if re.search(r'\bConst\b|^(?:Art(?:icle|\.)\s*[IVX]+|Amend(?:ment|\.)\s*[IVXL]+|(?:%s)\s+Amendment\b)' % '|'.join(ORD), txt, re.I):
        c = parse_const(txt, in_const and re.match(r'^(?:art|amend|[a-z\-]+\s+amendment)', txt, re.I) is not None)
        if c:
            return [c]
        if re.search(r'\bConst\b', txt):
            return []
    if ' v. ' in txt or re.match(r'^(?:In re|Ex parte|Matter of)\s', txt):
        c = parse_case(txt)
        if c:
            return [c]
        if re.search(r'\d+\s+U\.\s?S\.\s?C\.', txt) is None:
            return []
    if 'case' in sec and 'statut' not in sec:
        return []
    return parse_statutes(txt, sec)


# ------------------------------------------------------------------ body text and quotations
def clean_body(t):
    t = t.replace('\f', '\n')
    t = re.sub(r'(?m)^\s*(?:\d+|[ivxl]+|\(\d+\))\s*$', '', t)
    t = re.sub(r'(?m)^.*TABLE OF (?:CITED )?AUTHORITIES.*$', '', t)
    t = re.sub(r'([a-z])-\n([a-z])', r'\1\2', t)
    return norm_ws(t)


def clean_opinion(t):
    t = t.replace('\f', '\n')
    t = re.sub(r'(?m)^\s*Cite as: .*$|^\s*\d+\s*$|^\s*Opinion of the Court\s*$|^\s*(?:Opinion of [A-Z]+, J\.|[A-Z]+, (?:C\. )?J\., (?:dissenting|concurring).*)\s*$|^\s*Syllabus\s*$', '', t)
    t = re.sub(r'(?m)^[A-Z][A-Z .,’\'&\-]+ v\. [A-Z][A-Z .,’\'&\-]+\s*$', '', t)
    t = re.sub(r'([a-z])-\n\s*([a-z])', r'\1\2', t)
    return t


OPINION_HEAD = re.compile(r'(?:(?:CHIEF |Chief )?(?:JUSTICE|Justice) ([A-Z][A-Za-z]+)(?:’S|’s)? delivered the opinion of the Court|(?:CHIEF |Chief )?(?:JUSTICE|Justice) ([A-Z][A-Za-z]+), (?:with whom [^,]{0,120}?, )?(dissenting|concurring(?: in (?:part|the judgment)[^.]{0,60})?)\.|PER CURIAM|Per Curiam\.)')


def opinion_parts(t):
    """[(start offset, label)] for the parts of a slip opinion (the Syllabus is not the Court's)."""
    parts = [(0, 'Syllabus')]
    for m in OPINION_HEAD.finditer(t):
        if m.group(1):
            parts.append((m.start(), f"Opinion of the Court ({'Chief Justice' if m.group(0)[:5].upper() == 'CHIEF' else 'Justice'} {m.group(1).title()})"))
        elif m.group(2):
            parts.append((m.start(), f"{'Chief Justice' if m.group(0)[:5].upper() == 'CHIEF' else 'Justice'} {m.group(2).title()}, {m.group(3)}"))
        else:
            parts.append((m.start(), 'Per curiam opinion'))
    return parts


def ws_rx(s):
    """A citation as a regex that allows any spacing ("U.S." vs "U. S.", "§706" vs "§ 706")."""
    out = []
    for ch in s:
        if ch == ' ':
            out.append(r'\s*')
        elif ch == '.':
            out.append(r'\.\s*')
        else:
            out.append(re.escape(ch))
    return ''.join(out)


QUOTE_BEFORE = re.compile(r'[“"](?P<q>[^“”"]{30,700}?)[”"]\s*(?:\((?:[^()]|\([^()]*\)){0,120}\)\s*)?[.,;:]?\s*(?P<lead>[^“”"]{0,180})$')


def cite_patterns(it):
    if it['t'] == 'case' and it['page'].isdigit():
        v, r, p = it['vol'], it['rep'], it['page']
        return [re.compile(ws_rx(f'{v} {r}') + r',?\s*(?:' + re.escape(p) + r'\b|at\s*\d)')]
    if it['t'] == 'usc':
        return [re.compile(ws_rx(f"{it['title']} U.S.C.") + r'\s*(?:§§?|[Ss]ec(?:tion|s)?\.?)?\s*' + re.escape(it['sec']) + r'(?![0-9A-Za-z])')]
    if it['t'] == 'rule':
        return [re.compile(ws_rx(it['label']) + r'(?![0-9])')]
    if it['t'] == 'reg' and it['key'].startswith('cfr:'):
        return [re.compile(ws_rx(it['label'].replace(' pt. ', ' ')).replace(r'§\ ', r'§?\s*'))]
    return []


def lead_ok(it, lead):
    """The text between the closing quotation mark and the citation must be only the authority's name and a signal
    ("See", "(quoting"), never another citation, a string-cite separator or a sentence of the brief's own."""
    lead = lead.strip()
    if re.search(r'\d+\s+(?:U\.\s?S\.|S\.\s?Ct\.|F\.\s?\dd|U\.\s?S\.\s?C\.)', lead) or lead.startswith(')'):
        return False                      # another citation in between: the quote belongs to it
    if it['t'] == 'case':
        if not lead:
            return False
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’\-]*", it['label']) if w.lower() not in ('v', 'the', 'in', 're', 'ex', 'parte')]
        if not words:
            return False
        pos = [m.start() for w in words[:3] + words[-2:] for m in re.finditer(r'\b' + re.escape(w) + r'\b', lead)]
        if not pos:
            return False
        pre = lead[:min(pos)]
        if len(pre) > 60 or ';' in pre or (')' in pre and '(quoting' not in pre) or ('(' in pre and '(quoting' not in pre):
            return False
        return len(lead) - min(pos) <= 170
    return len(lead) <= 40 and ';' not in lead and ')' not in lead and not re.search(r'[a-z]{4,}\s+[a-z]{4,}\s+[a-z]{4,}', lead)


def find_quotes(text, it, limit=3):
    out = []
    for rx in cite_patterns(it):
        for m in rx.finditer(text):
            win = text[max(0, m.start() - 1000): m.start()]
            q = QUOTE_BEFORE.search(win)
            if not q or not lead_ok(it, q.group('lead')):
                continue
            quote = q.group('q').strip()
            if len(quote.split()) < 6 or quote.count('[') > 4:
                continue
            # the rest of the citation: pin pages, footnotes ("707 n.13"), subsections ("(a)(1)")
            cite_end = re.match(r'[\dA-Za-z]{0,3}(?:\([0-9A-Za-z]{1,4}\))*(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*(?:\s*,?\s*nn?\.\s*\d+(?:\s*[-–]\s*\d+)?)?',
                                text[m.end(): m.end() + 40]).group(0)
            out.append({'text': quote, 'cite': norm_ws((text[m.start(): m.end()] + cite_end).strip(' ,;')), 'pos': m.start()})
            if len(out) >= limit * 2:
                break
    seen, res = set(), []
    for o in out:
        k = o['text'][:60].lower()
        if k in seen:
            continue
        seen.add(k)
        res.append(o)
    return res[:limit]


# ------------------------------------------------------------------ transcripts
SPK = re.compile(r'(?:^|\n)\s*((?:CHIEF )?JUSTICE [A-Z][A-Z\'-]+|M[RS]S?\. [A-Z][A-Z\'-]+|GENERAL [A-Z][A-Z\'-]+|GEN\. [A-Z][A-Z\'-]+):', re.M)


def transcript_turns(path):
    lines = open(path, encoding='utf-8', errors='replace').read().replace('\f', '\n').split('\n')
    # transcript pages number their lines 1-25, either on a line of their own or before the text; page numbers stand
    # alone too. A number is a line number only when it is the next one expected (or 1, on a new page).
    keep, L = [], 0
    for ln in lines:
        s = ln.strip()
        if re.fullmatch(r'\d+', s):
            n = int(s)
            if n <= 25 and n in (L + 1, 1):
                L = n
            continue
        if not s or re.search(r'Official - Subject to Final Review|Heritage Reporting|Alderson Reporting|^Official$|www\.|1111 14th Street|\(202\)', s):
            continue
        m = re.match(r'^(\d{1,2})\s+(\S.*)$', s)
        if m and int(m.group(1)) <= 25 and int(m.group(1)) in (L + 1, 1):
            L = int(m.group(1))
            s = m.group(2)
        keep.append(s)
    t = '\n'.join(keep)
    first = re.search(r'(?:CHIEF )?JUSTICE [A-Z]+:', t)
    if not first:
        return []
    body = t[first.start():]
    end = re.search(r'\(Whereupon', body)
    body = body[:end.start()] if end else body
    marks = list(SPK.finditer(body))
    turns = []
    for k, m in enumerate(marks):
        txt = norm_ws(body[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(body)])
        txt = re.sub(r'(\w)- (\w)', r'\1\2', txt) if False else txt
        who = m.group(1).replace('GEN.', 'GENERAL')
        who = ' '.join(w if w in ('MR.', 'MS.', 'MRS.') else w.title() for w in who.split()).replace('MR.', 'Mr.').replace('MS.', 'Ms.').replace('MRS.', 'Mrs.')
        turns.append((who, txt))
    return turns


def sentences_around(txt, i, j):
    """The sentence holding txt[i:j], extended to a readable length."""
    bounds = [0] + [m.end() for m in re.finditer(r'(?<=[.?!])\s+(?=[A-Z“"])', txt)] + [len(txt)]
    k = max(n for n in range(len(bounds) - 1) if bounds[n] <= i)
    a, b = k, k + 1
    while bounds[b] < j and b < len(bounds) - 1:
        b += 1
    while bounds[b] - bounds[a] < 140 and (a > 0 or b < len(bounds) - 1):
        if b < len(bounds) - 1:
            b += 1
        elif a > 0:
            a -= 1
    s = txt[bounds[a]: bounds[b]].strip()
    if len(s) > 650:
        s0 = max(0, i - bounds[a] - 300)
        s = ('… ' if s0 else '') + s[s0: s0 + 600].strip() + ' …'
    return s


STOPNAMES = GENERIC | set('smith jones johnson brown davis miller wilson moore taylor anderson thomas jackson white harris martin thompson garcia '
                          'martinez robinson clark rodriguez lewis lee walker hall allen young king wright scott green baker adams nelson hill '
                          'campbell mitchell roberts carter phillips evans turner torres parker collins edwards stewart morris murphy cook rogers '
                          'morgan cooper peterson bailey reed kelly howard ward cox richardson wood watson brooks bennett gray james hughes price '
                          'sanders myers long ross foster alito kagan gorsuch kavanaugh barrett sotomayor breyer ginsburg kennedy scalia stevens '
                          'souter rehnquist o\'connor court congress section rule title act'.split())


def short_name(label):
    pk = party_key(label)
    if not pk:
        m = re.match(r'^(?:In re|Ex parte|Matter of)\s+([A-Z][A-Za-z\'’\-]+)', label)
        return m.group(1) if m and m.group(1).lower() not in STOPNAMES else None
    words = re.findall(r"[A-Z][A-Za-z'’\-]+", re.split(r'\s+v\.\s+', label)[0])
    for w in words:
        if w.lower() not in STOPNAMES and len(w) > 3:
            return w
    words = re.findall(r"[A-Z][A-Za-z'’\-]+", re.split(r'\s+v\.\s+', label)[1]) if ' v. ' in label else []
    for w in words:
        if w.lower() not in STOPNAMES and len(w) > 3:
            return w
    return None


# ------------------------------------------------------------------ U.S. Code text (govinfo)
def usc_text(title, sec):
    os.makedirs(f'{RAW}/usc', exist_ok=True)
    p = f'{RAW}/usc/{title}-{sec}.html'
    if not os.path.exists(p):
        if not FETCH:
            return None
        url = f'https://www.govinfo.gov/link/uscode/{title}/{sec}?type=usc&year=mostrecent&link-type=html'
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception:
            b = b''
        open(p, 'wb').write(b)
        time.sleep(0.6)
    h = open(p, encoding='utf-8', errors='replace').read()
    m = re.search(r'<!-- field-start:statute -->(.*?)<!-- field-end:statute -->', h, re.S)
    head = re.search(r'<h3 class="section-head">(.*?)</h3>', h, re.S)
    ed = re.search(r'United States Code, (\d{4}) Edition', h)
    if not m:
        return None
    paras = []
    for pm in re.finditer(r'<(p|h4)[^>]*class="([^"]*)"[^>]*>(.*?)</\1>', m.group(1), re.S):
        txt = norm_ws(html.unescape(re.sub(r'<[^>]+>', '', pm.group(3))))
        if not txt:
            continue
        ind = re.search(r'(\d)em', pm.group(2))
        paras.append([int(ind.group(1)) if ind else 0, txt])
    if not paras:
        return None
    total, keep = 0, []
    for p_ in paras:
        total += len(p_[1])
        keep.append(p_)
        if total > 9000:
            break
    return {'head': norm_ws(html.unescape(re.sub(r'<[^>]+>', '', head.group(1)))) if head else '', 'paras': keep,
            'more': len(keep) < len(paras), 'ed': ed.group(1) if ed else '',
            'src': f'https://www.govinfo.gov/link/uscode/{title}/{sec}?type=usc&year=mostrecent&link-type=html'}


# ------------------------------------------------------------------ relevance and summaries
USC_TITLES = {1: 'General Provisions', 2: 'The Congress', 3: 'The President', 4: 'Flag and Seal, Seat of Government, and the States',
              5: 'Government Organization and Employees', 6: 'Domestic Security', 7: 'Agriculture', 8: 'Aliens and Nationality',
              9: 'Arbitration', 10: 'Armed Forces', 11: 'Bankruptcy', 12: 'Banks and Banking', 13: 'Census', 14: 'Coast Guard',
              15: 'Commerce and Trade', 16: 'Conservation', 17: 'Copyrights', 18: 'Crimes and Criminal Procedure', 19: 'Customs Duties',
              20: 'Education', 21: 'Food and Drugs', 22: 'Foreign Relations and Intercourse', 23: 'Highways', 24: 'Hospitals and Asylums',
              25: 'Indians', 26: 'Internal Revenue Code', 27: 'Intoxicating Liquors', 28: 'Judiciary and Judicial Procedure', 29: 'Labor',
              30: 'Mineral Lands and Mining', 31: 'Money and Finance', 32: 'National Guard', 33: 'Navigation and Navigable Waters',
              34: 'Crime Control and Law Enforcement', 35: 'Patents', 36: 'Patriotic and National Observances', 37: 'Pay and Allowances of the Uniformed Services',
              38: "Veterans' Benefits", 39: 'Postal Service', 40: 'Public Buildings, Property, and Works', 41: 'Public Contracts',
              42: 'The Public Health and Welfare', 43: 'Public Lands', 44: 'Public Printing and Documents', 45: 'Railroads', 46: 'Shipping',
              47: 'Telecommunications', 48: 'Territories and Insular Possessions', 49: 'Transportation', 50: 'War and National Defense',
              51: 'National and Commercial Space Programs', 52: 'Voting and Elections', 54: 'National Park Service and Related Programs'}
PAREN = re.compile(r'\(\s*((?:holding|concluding|explaining|recognizing|finding|rejecting|observing|reasoning|declaring|upholding|striking down|'
                   r'invalidating|deciding|ruling|stating|noting|describing|construing|interpreting)\b(?:[^()]|\([^()]*\)){25,420})\)')


def parenthetical(text, it, limit=1):
    """The description a source attaches to a citation: "467 U.S. 837, 842-843 (1984) (holding that ...)"."""
    out = []
    for rx in cite_patterns(it):
        for m in rx.finditer(text):
            tail = text[m.end(): m.end() + 140]
            pm = PAREN.search(text, m.end(), m.end() + 600)
            if not pm or pm.start() - m.end() > 120 or re.search(r'\d+\s+(?:U\.\s*S\.|S\.\s*Ct\.|F\.)', text[m.end(): pm.start()]):
                continue
            t = norm_ws(pm.group(1))
            t = t[0].upper() + t[1:]
            out.append(t.rstrip(' .;,') + '.')
            if len(out) >= limit:
                return out
    return out


ABBR = re.compile(r'(?:\b[A-Z]|\b(?:Mr|Ms|Dr|Jr|Sr|St|No|v|Co|Inc|Corp|Ltd|Ass|Dept|Gov|Gen|Sec|U\.S|Stat|Cir|App))$')


def split_sents(t):
    out = []
    for piece in re.split(r'(?<=[.!?])\s+(?=[A-Z])', t):
        if out and ABBR.search(out[-1][:-1]):
            out[-1] += ' ' + piece
        else:
            out.append(piece)
    return out
HELD = re.compile(r'\b(held|holds|ruled|concluded|determined|found|reasoned|decided)\b')


def held_sentences(t, cap=420):
    """The sentences of a summary from the first one that says what the Court held, without the vote and author."""
    t = norm_ws(t)
    t = re.sub(r'^(?:Yes|No|Yes and no|No and yes)[.,:;]\s*', '', t)
    sents = [x.strip() for x in split_sents(t) if x.strip()]
    i = next((n for n, x in enumerate(sents) if HELD.search(x)), 0)
    out = ''
    for x in sents[i:]:
        if out and len(out) + len(x) > cap:
            break
        out = (out + ' ' + x.rstrip('.') + '.').strip()
    out = re.sub(r'^In an? (?:\d+-\d+ |unanimous |per curiam |plurality )?(?:opinion|decision)[^,]{0,90}, ', '', out)
    out = re.sub(r'^(?:Justice|Chief Justice) [A-Z][^,]{2,40}, writing for [^,]{3,60}, ', '', out)
    return (out[:1].upper() + out[1:]) if out else ''


def oyez_conclusion(cid):
    p = 'data/raw/oyez/cases/' + cid.replace('/', '_') + '.json'
    if not os.path.exists(p):
        return ''
    d = json.load(open(p, encoding='utf-8'))
    t = html.unescape(re.sub(r'<[^>]+>', ' ', d.get('conclusion') or ''))
    return held_sentences(t) if t.strip() else ''


HEADNOTES = {}


def headnote(cid):
    """The 'Held:' part of the official syllabus, or the first headnote, from docs/data/headnotes (build_headnotes.py)."""
    if not HEADNOTES:
        for p in glob.glob('docs/data/headnotes/*.js'):
            t = open(p, encoding='utf-8').read()
            HEADNOTES.update(json.loads(t[t.index('HEADNOTES,') + 10:-2]))
        HEADNOTES.setdefault('_', {})
    h = (HEADNOTES.get(cid) or {}).get('h') or ''
    if not h:
        return '', ''
    m = re.search(r'(?:^|\n)Held: (.+)', h)
    src = 'Syllabus (U.S. Reports)' if (HEADNOTES[cid].get('src') == 'loc') else 'Headnote (U.S. Reports)'
    first = (m.group(1) if m else h.split('\n')[0])
    first = re.sub(r'\s*Pp?\. \d+(?:-\d+)?\.?\s*$', '', first.split('\n')[0]).strip()
    if len(first) > 420:
        cut = first[:420]
        first = cut[:cut.rfind(' ')] + ' …'
    return first, src


AIB = {}


def ai_holding(cid):
    if not AIB and os.path.exists('data/raw/aibriefs/briefs.json'):
        AIB.update(json.load(open('data/raw/aibriefs/briefs.json', encoding='utf-8')))
        AIB.setdefault('_', {})
    return ((AIB.get(cid) or {}).get('holding') or '').strip()


def site_summary(cid):
    """What the site already says the case held: the official holding, Oyez's description or conclusion, the U.S. Reports
    syllabus or headnote, or (labelled) the AI brief's holding."""
    c = site_by_id.get(cid) or {}
    if c.get('h'):
        return c['h'], 'Holding (supremecourt.gov)'
    if c.get('ds'):
        t = re.sub(r'^A case in which the Court (held|considered|decided|determined|ruled|found|concluded)\s+',
                   lambda m: 'The Court ' + m.group(1) + ' ', c['ds'])
        return t, 'Oyez'
    t = oyez_conclusion(cid)
    if t:
        return t, 'Oyez'
    t, src = headnote(cid)
    if t:
        return t, src
    t = ai_holding(cid)
    if t:
        return t, 'AI-generated brief'
    return '', ''


# ------------------------------------------------------------------ per case
SIDE_LABEL = {'petitioner': 'Petitioner', 'respondent': 'Respondent', 'reply': 'Reply', 'united-states': 'United States'}


def brief_side(b):
    if b['k'] in ('petitioner', 'reply'):
        return 'pet'
    if b['k'] == 'respondent':
        return 'res'
    lab = b['label'].lower()
    if re.search(r'support(?:ing|s)? (?:of )?(?:the )?(?:petitioner|appellant|reversal|vacatur)', lab):
        return 'pet'
    if re.search(r'support(?:ing|s)? (?:of )?(?:the )?(?:respondent|appellee|affirmance)', lab):
        return 'res'
    return 'us'


def build_case(dk, man, transcripts):
    items, order = {}, []
    briefs = []
    texts = {}
    for b in man['briefs']:
        p = f"{RAW}/{dk}/{b['f']}.txt"
        if not os.path.exists(p):
            continue
        raw = open(p, encoding='utf-8', errors='replace').read()
        toa, end = toa_text(raw)
        bi = len(briefs)
        briefs.append({'k': b['k'], 'label': b['label'], 'date': b['date'], 'url': b['url'], 'side': brief_side(b)})
        texts[bi] = clean_body(raw[end:] if end else raw)
        prev_const = False
        n_ok = 0
        for sec, txt, pages in toa_entries(toa):
            got = classify(sec, txt, prev_const)
            prev_const = bool(got) and got[0]['t'] == 'const'
            for it in got:
                k = it['key']
                if k not in items:
                    items[k] = dict(it, by={}, q=[])
                    order.append(k)
                else:
                    if it.get('sub') and it['sub'] not in items[k].get('subs', []):
                        pass
                cur = items[k]
                if it.get('sub'):
                    cur.setdefault('subs', [])
                    if it['sub'] not in cur['subs']:
                        cur['subs'].append(it['sub'])
                if it['t'] == 'case' and not cur.get('y') and it.get('y'):
                    cur['y'] = it['y']
                prev = cur['by'].get(bi)
                cur['by'][bi] = (prev + ', ' + pages) if prev else pages
                n_ok += 1
        briefs[-1]['n'] = n_ok
    if not items:
        return None
    case = dk_case.get(dk)
    for k in list(items):     # the case itself (a reply brief may cite the decision below or this case's own report)
        if case and items[k].get('id') == case.get('id'):
            del items[k]
            order.remove(k)
    # quotations in the briefs
    for k in order:
        it = items[k]
        for bi in sorted(it['by']):
            for q in find_quotes(texts[bi], it, limit=2):
                it['q'].append({'src': 'brief', 'b': bi, 'text': q['text'], 'cite': q['cite']})
    # distinctive short names (party name of a case, "section <n>" of a statute) for counting mentions
    shorts = collections.Counter()
    names = {}
    for k in order:
        it = items[k]
        if it['t'] == 'case':
            sn = short_name(it['label'])
            if sn:
                names[k] = sn
                shorts[sn] += 1
        elif it['t'] == 'usc':
            names[k] = 'sec:' + it['sec']
            shorts['sec:' + it['sec']] += 1
    own = set(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'’\-]+", (case or {}).get('n', '')))
    # a name that is also a party in another cited case (Laitram v. Deepsouth / Deepsouth v. Laitram) is ambiguous
    anywhere = collections.Counter(w for k in order if items[k]['t'] == 'case'
                                   for w in set(re.findall(r"[A-Z][A-Za-z'’\-]+", items[k]['label'])))
    name_rx = {}
    for k, sn in names.items():
        if shorts[sn] > 1 or (not sn.startswith('sec:') and (sn.lower() in own or anywhere[sn] > 1)):
            continue
        name_rx[k] = re.compile(r'(?:\b[Ss]ection\s+|§\s*)' + re.escape(sn[4:]) + r'\b(?![(\w])' if sn.startswith('sec:') else r'\b' + re.escape(sn) + r'(?:[’\']s)?\b')

    def mentions(text, it, k):
        n = sum(len(rx.findall(text)) for rx in cite_patterns(it))
        if k in name_rx:
            n = max(n, len(name_rx[k].findall(text)))
        return n
    for k in order:
        items[k]['op'] = items[k]['ar'] = 0
    # the opinion
    op_path = f'{RAW}/{dk}/opinion.txt'
    has_op = os.path.exists(op_path) and man.get('opinion')
    if has_op:
        ot = clean_opinion(open(op_path, encoding='utf-8', errors='replace').read())
        parts = opinion_parts(ot)
        flat, offs = [], []          # normalized text with a map back to the part labels
        for i, (start, label) in enumerate(parts):
            seg = norm_ws(ot[start: parts[i + 1][0] if i + 1 < len(parts) else len(ot)])
            offs.append((sum(len(x) + 1 for x in flat), label))
            flat.append(seg)
        otext = ' '.join(flat)
        part_at = lambda pos: [lab for o, lab in offs if o <= pos][-1]
        body_at = next((o for o, lab in offs if lab != 'Syllabus'), 0)
        obody = otext[body_at:]
        for k in order:
            it = items[k]
            it['op'] = mentions(obody, it, k)
            if it['t'] in ('case', 'usc') and it['op']:
                ph = parenthetical(obody, it)
                if ph:
                    it['sum'], it['sumSrc'] = ph[0], 'opinion'
            for q in find_quotes(otext, it, limit=4):
                lab = part_at(q['pos'])
                if lab == 'Syllabus':
                    continue
                it['q'].append({'src': 'opinion', 'who': lab, 'text': q['text'], 'cite': q['cite']})
            it['q'] = it['q'][:8]
    # oral argument
    turns = []
    for tp in transcripts:
        turns += transcript_turns(tp)
    if turns:
        for k, rx in name_rx.items():
            items[k]['ar'] = sum(1 for who, txt in turns if rx.search(txt))
    # what each relevant case held: the opinion's own description (above), else the site's summary of the case,
    # else a brief's description of it
    for k in order:
        it = items[k]
        if it['t'] != 'case' or it.get('sum'):
            continue
        if it.get('id'):
            t, src = site_summary(it['id'])
            if t:
                it['sum'], it['sumSrc'] = t, src
                continue
        for bi in sorted(it['by']):
            ph = parenthetical(texts[bi], it)
            if ph:
                it['sum'], it['sumSrc'] = ph[0], 'brief:' + str(bi)
                break
    # statutes: section heading and text for the most relevant sections
    usc = [k for k in order if items[k]['t'] == 'usc']
    rank = lambda k: (3 * items[k]['op'] + items[k]['ar'] + len(items[k]['by']), -len(items[k]['label']))
    for k in sorted(usc, key=rank, reverse=True)[:15]:
        it = items[k]
        if not (it['op'] or it['ar'] or len(it['by']) >= 2):
            continue
        tx = usc_text(it['title'], it['sec'])
        if tx:
            it['stext'] = tx
            it['head'] = tx['head']
        it['tname'] = USC_TITLES.get(int(it['title']) if str(it['title']).isdigit() else 0, '')
    out_items = []
    for k in order:
        it = items[k]
        o = {x: it[x] for x in ('t', 'label', 'cite', 'y', 'court', 'id', 'url', 'subs', 'clauses', 'text', 'stext', 'sc', 'op', 'ar',
                                'sum', 'sumSrc', 'head', 'tname') if it.get(x)}
        o['by'] = {str(b): p for b, p in it['by'].items()}
        o['label'] = re.sub(r'^\s*(?:CASES|Cases|STATUTES|Statutes|AUTHORITIES)\s+', '', o['label']).strip()
        out_items.append(o)
    return {'d': dk, 'id': (case or {}).get('id'), 'n': (case or {}).get('n'), 'briefs': briefs, 'opinion': man.get('opinion') if has_op else None,
            'tr': bool(turns), 'items': out_items}


def main():
    man = json.load(open(f'{RAW}/manifest.json'))
    trs = collections.defaultdict(list)
    for p in glob.glob('data/raw/transcripts/*/*.txt'):
        dk = re.sub(r'_[a-z0-9]+$', '', os.path.basename(p)[:-4]).lower()
        dk = re.sub(r'-(monday|tuesday|wednesday|thursday|friday|day\d)$', '', dk)
        trs[dk].append(p)
    os.makedirs(OUT, exist_ok=True)
    index, stats = {}, collections.Counter()
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    for dk in sorted(man):
        if only and dk not in only:
            continue
        r = build_case(dk, man[dk], trs.get(dk, []))
        if not r:
            stats['no-authorities'] += 1
            continue
        case = dk_case.get(dk)
        if not case:
            stats['no-site-case'] += 1
        js = 'window.AUTH=window.AUTH||{};window.AUTH[' + json.dumps(dk) + ']=' + json.dumps(r, ensure_ascii=False, separators=(',', ':')) + ';'
        open(f'{OUT}/{dk}.js', 'w', encoding='utf-8').write(js)
        if case:
            index[case['id']] = dk
        stats['cases'] += 1
        stats['briefs'] += len(r['briefs'])
        stats['authorities'] += len(r['items'])
        for it in r['items']:
            stats['t:' + it['t']] += 1
            stats['linked to site'] += bool(it.get('id'))
            for q in it.get('q', []):
                stats['q:' + q['src']] += 1
            stats['statute text'] += bool(it.get('stext'))
    if not only:
        open('docs/data/auth-index.js', 'w', encoding='utf-8').write('window.AUTH_INDEX=' + json.dumps(index, separators=(',', ':')) + ';')
    print(dict(stats))


if __name__ == '__main__':
    main()
