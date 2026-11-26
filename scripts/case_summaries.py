"""Fill holes in case-summary coverage: official text and Wikipedia leads for Supreme Court cases that have no Oyez
summary, no reporter's headnotes and no syllabus in docs/data/headnotes/ (built by build_headnotes.py).

Sources, in order of preference (each is only tried for cases that still lack a summary):
  cap   the reporter's headnotes from the U.S. Reports, from the Caselaw Access Project per-case files
        (static.case.law, public domain), read with a more tolerant parser than build_headnotes.py: many older head
        matters put the headnote before the "Appeal from ..." caption line, which the first pass skipped.
  loc   the official syllabus from the Library of Congress U.S. Reports PDF (same cache as loc_syllabus.py,
        data/raw/loc_syl/), read with a parser that does not stop at the "Opinion of the Court." running head of the
        second page and accepts syllabi that open with "1." (most 1930s-50s cases the first pass missed); a last
        reading takes the short block after the docket line (per curiam orders, decrees, "affirmed by an equally
        divided Court", "Decided on authority of ...").
  recite  cases whose first page on the site is wrong: the page CAP's volume metadata gives for the same decision date
        and party name, then the LoC PDF (and, through 1930, CAP's head matter) from that page.
  orders  memorandum decisions and short per curiam orders with no syllabus: their whole text (at most 700
        characters, a single opinion), from the CAP case file, shown as "Order" (src:'order').
  wiki  for important cases only (essential list, most cited, linked from the Guide, Corner, Constitution, statutes
        or articles): the lead section of the case's Wikipedia article (CC BY-SA 4.0, attributed and linked on the
        case page). The article is accepted only if its infobox carries the case's U.S. Reports volume and page.

Output: docs/data/summaries/<year>.js (merged into window.HEADNOTES, the format the case page already reads: {h, cite,
cap} for CAP headnotes, {h, cite, src:'loc'} for syllabi, {h, cite, cap, src:'order'} for order text, {h, src:'wiki', t, url, rev} for Wikipedia) and
docs/data/summaries-index.js. build_headnotes.py's files are not touched.

Caches (gitignored): data/raw/oyez/cases/ (Oyez records for every Oyez case on the site, to know which have no
summary), data/raw/cap/meta/, data/raw/cap/meta_full/, data/raw/cap/case/, data/raw/cap/order/, data/raw/loc_syl/,
data/raw/wiki_case/, data/raw/wiki_name/.

Run from the repo root:
  python scripts/case_summaries.py oyez        # refresh the Oyez cache for all Oyez cases (about 8,500 requests)
  python scripts/case_summaries.py cap         # CAP head matter for cases with no summary
  python scripts/case_summaries.py loc         # LoC syllabus pages for cases still without one
  python scripts/case_summaries.py wiki        # Wikipedia leads for important cases still without any summary
  python scripts/case_summaries.py wikiname    # Wikipedia by case name for any case still without one (slow; resumable)
  python scripts/case_summaries.py recite      # LoC/CAP at the right page for cases whose first page is wrong
  python scripts/case_summaries.py orders      # CAP text of short orders with no syllabus
  python scripts/case_summaries.py build       # write docs/data/summaries/
  python scripts/case_summaries.py coverage    # coverage table, overall, by era and for important cases
"""
import collections, glob, html, json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_headnotes as bh  # noqa: E402

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)', 'Accept': '*/*'}
OUT = 'docs/data/summaries'
OYEZ, CAPM, CAPC, LOC, WIKI = 'data/raw/oyez/cases', 'data/raw/cap/meta', 'data/raw/cap/case', 'data/raw/loc_syl', 'data/raw/wiki_case'


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def load_assign(pattern, var):
    out = {}
    for f in glob.glob(pattern):
        s = open(f, encoding='utf-8').read()
        i = s.index(var + ',') + len(var) + 1
        out.update(json.loads(s[i:].rstrip().rstrip(';').rstrip(')')))
    return out


def get(url, tries=4, **hdr):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **hdr}), timeout=120) as r:
                return r.read()
        except Exception as e:
            if getattr(e, 'code', None) in (403, 404):
                return None
            ra = getattr(e, 'headers', None) and e.headers.get('Retry-After')
            time.sleep(int(ra) if ra and ra.isdigit() else 30 * (attempt + 1) if getattr(e, 'code', None) == 429 else 10 * (attempt + 1))
    return None


def fname(cid):
    return cid.replace('/', '_')


def year(c):
    return int(str(c.get('y') or 0)[:4])


class Data:
    def __init__(self):
        self.cases = load_js('docs/data/scotus.js')['cases']
        self.by_id = {c['id']: c for c in self.cases}
        self.head = load_assign('docs/data/headnotes/*.js', 'Object.assign(window.HEADNOTES')
        self.ai = load_assign('docs/data/aibriefs/*.js', 'Object.assign(window.AIBRIEFS')
        self.mine = load_assign(f'{OUT}/*.js', 'Object.assign(window.HEADNOTES') if os.path.isdir(OUT) else {}
        self.oyez = {}
        for f in glob.glob(f'{OYEZ}/*.json'):
            d = json.load(open(f, encoding='utf-8'))
            self.oyez[os.path.basename(f)[:-5]] = bool((d.get('facts_of_the_case') or '').strip() or (d.get('conclusion') or '').strip())

    def has_oyez(self, c):
        return c.get('s') != 1 and self.oyez.get(fname(c['id']), True)

    def status(self, c, new=True):
        if self.has_oyez(c):
            return 'oyez'
        h = self.head.get(c['id']) or (self.mine.get(c['id']) if new else None)
        if h:
            return {'loc': 'syllabus', 'wiki': 'wikipedia', 'order': 'order'}.get(h.get('src'), 'headnotes')
        return 'ai brief' if c['id'] in self.ai else 'none'

    def need(self, c):
        """No Oyez summary and no official text yet (an AI brief does not count: official text is shown beside it)."""
        return not self.has_oyez(c) and c['id'] not in self.head and c['id'] not in self.mine


# ---------------------------------------------------------------- important cases
def short_index(cases):
    idx = {}
    for x in cases:
        m = re.match(r"^(?:The )?([A-Z][\w'.&-]*)[^v]*? v\. (?:The )?([A-Z][\w'.&-]*)", x['n'])
        if not m:
            continue
        k = (m.group(1) + '|' + m.group(2)).lower()
        p = idx.get(k)
        if not p or (not p.get('con') and x.get('con')) or (not p.get('dec') and x.get('dec')):
            idx[k] = x
    return idx


def mentioned(text, by_cit, idx):
    """Cases a text names, the way the site links them (app.js citedCases and articleMentions)."""
    out = set()
    for m in re.finditer(r'\b(\d{1,3}) U\.\s?S\. (\d{1,4})\b', text):
        c = by_cit.get(f'{m.group(1)} U.S. {m.group(2)}')
        if c:
            out.add(c['id'])
    for m in re.finditer(r"(?:^|[^A-Za-z])([A-Z][\w'.&-]*)(?: [A-Z][\w'.&-]*){0,4} v\. (?:The )?([A-Z][\w'.&-]*)", text):
        c = idx.get((m.group(1) + '|' + m.group(2)).lower())
        if c:
            out.add(c['id'])
    return out


def important(D):
    ids = set(D.by_id)
    by_cit = {}
    for c in D.cases:
        if c.get('cit'):
            by_cit.setdefault(c['cit'], c)
    idx = short_index(D.cases)
    raw_ids = lambda path: {m for m in re.findall(r'"([^"\s]{3,40})"', open(path, encoding='utf-8').read()) if m in ids}
    G = {}
    G['essential'] = set(load_js('docs/data/essential.js'))
    imp = load_js('docs/data/case_impact.js')['c']
    G['most cited (top 500)'] = set(sorted(imp, key=lambda k: -imp[k][0])[:500])
    G['guide'] = raw_ids('docs/data/guide.js')
    G['constitution'] = raw_ids('docs/data/constitution.js')
    G['statutes'] = raw_ids('docs/data/statutes.js')
    corner = load_js('docs/data/corner.js')
    G['corner'] = set().union(*[mentioned(p.get('t') or '', by_cit, idx) for p in corner['passages'].values()])
    arts = load_js('docs/data/articles.js')['articles']
    G['articles'] = set().union(*[mentioned(' . '.join([a.get('t') or '', a.get('ab') or '', '; '.join(a.get('kw') or [])]), by_cit, idx) for a in arts])
    for k in G:
        G[k] &= ids
    return G


# ---------------------------------------------------------------- coverage
ERAS = [(0, 1859, '1791-1859'), (1860, 1899, '1860-1899'), (1900, 1929, '1900-1929'), (1930, 1954, '1930-1954'),
        (1955, 1989, '1955-1989'), (1990, 9999, '1990-2026')]
COLS = ['oyez', 'headnotes', 'syllabus', 'order', 'wikipedia', 'ai brief', 'none']


def table(rows, D, new):
    t = collections.Counter(D.status(c, new) for c in rows)
    return t


def coverage(new=True):
    D = Data()
    print(f"{'':28}" + ''.join(f'{c:>11}' for c in COLS) + f"{'total':>8}")
    line = lambda name, t, n: print(f'{name:28}' + ''.join(f'{t[c]:>11}' for c in COLS) + f'{n:>8}')
    for a, b, name in ERAS:
        rows = [c for c in D.cases if a <= year(c) <= b]
        line(name, table(rows, D, new), len(rows))
    line('ALL', table(D.cases, D, new), len(D.cases))
    G = important(D)
    allimp = set().union(*G.values())
    print()
    for k, v in list(G.items()) + [('ALL IMPORTANT', allimp)]:
        rows = [D.by_id[i] for i in v]
        line(k, table(rows, D, new), len(rows))
    return D, G


# ---------------------------------------------------------------- Oyez cache refresh
def fetch_oyez():
    os.makedirs(OYEZ, exist_ok=True)
    D = Data()

    def one(cid):
        path = f'{OYEZ}/{fname(cid)}.json'
        if os.path.exists(path) and '--refresh' not in sys.argv:
            return
        raw = get('https://api.oyez.org/cases/' + cid)
        d = json.loads(raw) if raw else {}
        keep = {k: d.get(k) for k in ('name', 'facts_of_the_case', 'conclusion', 'decisions', 'written_opinion')}
        if keep['decisions']:
            keep['decisions'] = [{k: x.get(k) for k in ('majority_vote', 'minority_vote', 'winning_party', 'decision_type')} for x in keep['decisions']]
        if keep['written_opinion']:
            keep['written_opinion'] = [{'type': (x.get('type') or {}).get('value'), 'judge': x.get('judge_full_name')} for x in keep['written_opinion']]
        if raw:
            json.dump(keep, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(0.3)
    todo = [c['id'] for c in D.cases if c.get('s') != 1]
    with ThreadPoolExecutor(2) as ex:
        for i, _ in enumerate(ex.map(one, todo)):
            if i % 1000 == 0:
                print(i, '/', len(todo), flush=True)
    # Oyez cases the site does not list yet (new Terms): reported, not added (scotus.sh / merge_new.py add cases)
    have = set(D.by_id)
    terms = ['1789-1850', '1850-1900', '1900-1940', '1940-1955'] + [str(y) for y in range(1955, time.gmtime().tm_year + 1)]
    new = []
    for t in terms:
        raw = get(f'https://api.oyez.org/cases?filter=term:{t}&per_page=2000')
        for x in json.loads(raw) if raw else []:
            cid = x['href'].split('/cases/')[1]
            decided = any(e and e.get('event') == 'Decided' for e in x.get('timeline') or [])
            if cid not in have:
                new.append((cid, x.get('name'), decided))
        time.sleep(0.5)
    print(len(new), 'Oyez cases not on the site;', sum(1 for x in new if x[2]), 'of them decided')


# ---------------------------------------------------------------- OCR quality
WORD = re.compile(r"^[(\[\"'“‘]*([A-Za-z][a-z'’-]*|[A-Z][A-Z'’-]+|[A-Z]\.|\d+[a-z]{0,2}|\d+[.,:]\d+|§+|&|[A-Za-z]\.[A-Za-z]\.?)[.,;:)\]\"'”’?!]*$")


_VOCAB = None


def garbled(text, min_words=8):
    """True if the OCR is mostly noise: too few tokens look like words, or too few lower-case words are ones the
    existing headnotes and syllabi use (a vocabulary built from docs/data/headnotes/)."""
    global _VOCAB
    toks = text.split()
    if not toks or sum(1 for t in toks if WORD.match(t)) / len(toks) < 0.85:
        return True
    if _VOCAB is None:
        df = collections.Counter()
        for r in load_assign('docs/data/headnotes/*.js', 'Object.assign(window.HEADNOTES').values():
            df.update(set(re.findall(r"[a-z]+", r['h'])))
        _VOCAB = {w for w, n in df.items() if n >= 3}
    words = re.findall(r"(?<![A-Za-z])[a-z]{3,}(?![A-Za-z])", text)
    return len(words) < min_words or sum(1 for w in words if w in _VOCAB) / len(words) < 0.9


def drop_noise_lines(text):
    """Leave out single lines that are mostly scanning noise (a smudged first headnote, say)."""
    garbled('placeholder text so the vocabulary is loaded once')
    keep = []
    for l in text.split(chr(10)):
        w = re.findall(r"(?<![A-Za-z])[a-z]{3,}(?![A-Za-z])", l)
        t = l.split()
        if (len(w) >= 4 and sum(1 for x in w if x in _VOCAB) / len(w) < 0.85) or (t and sum(1 for x in t if WORD.match(x)) / len(t) < 0.8):
            continue
        keep.append(l)
    return chr(10).join(keep).strip()


# ---------------------------------------------------------------- Caselaw Access Project
DOCKET = re.compile(r'^No[s]?\.\s*[\dA-Za-z,\s&-]{1,40}\.?$', re.I)


def cap_extract(head):
    """Headnotes and statement of the case: skip the caption block (party names, court, docket, dates) only up to the
    first sentence-like line, so a headnote that precedes an 'Appeal from ...' line is kept."""
    t = bh.extract(head)
    if t:
        return t
    lines = [l.strip() for l in head.split('\n') if l.strip()][1:]
    body = []
    for l in lines:
        if bh.COUNSEL.match(l):
            break
        if re.match(r'^(The case is stated in the opinion|The facts are stated in the opinion|The case is sufficiently stated|'
                    r'The facts (of the case )?(are|sufficiently) (stated|appear))', l, re.I):
            break
        if not body and (bh.DATE.match(l) or DOCKET.match(l) or (l.isupper() and len(l) < 200) or len(l) < 40):
            continue
        body.append(bh.clean(l))
    text = '\n'.join(b for b in body if len(b) > 2)
    # a bare procedural line ("Appeal from the Circuit Court ...") is not a summary
    if len(text) < 80 or not re.search(r'[a-z]{3,}.*[.;:]', text) or all(bh.CAPTION.match(b) for b in body):
        return ''
    if len(text) > bh.LIMIT:
        cut = text[:bh.LIMIT]
        m = max(cut.rfind('. '), cut.rfind('.\n'))
        text = (cut[:m + 1] if m > bh.LIMIT // 2 else cut) + ' …'
    return text


def fetch_cap():
    os.makedirs(CAPM, exist_ok=True)
    os.makedirs(CAPC, exist_ok=True)
    D = Data()
    vols = collections.defaultdict(list)
    for c in D.cases:
        m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
        if m and D.need(c) and not os.path.exists(f'{CAPC}/{fname(c["id"])}.json'):
            vols[int(m.group(1))].append(c)
    print(sum(map(len, vols.values())), 'cases in', len(vols), 'volumes', flush=True)
    for v in sorted(vols):
        mp = f'{CAPM}/{v}.json'
        if not os.path.exists(mp):
            raw = get(f'https://static.case.law/us/{v}/CasesMetadata.json')
            if not raw:
                print('no metadata for volume', v, flush=True)
                continue
            meta = [{'f': x['file_name'], 'cites': [z.get('cite') for z in x.get('citations') or []], 'court': (x.get('court') or {}).get('id')} for x in json.loads(raw)]
            json.dump(meta, open(mp, 'w', encoding='utf-8'))
            time.sleep(0.5)
        meta = json.load(open(mp, encoding='utf-8'))
        for c in vols[v]:
            scdb = 'SCDB ' + c['id'][5:] if c['id'].startswith('scdb/') else None
            hit = [x for x in meta if scdb and scdb in x['cites']] or [x for x in meta if c['cit'] in x['cites'] and x['court'] == 9009]
            rec = {'head': ''}
            if len(hit) == 1:
                raw = get(f'https://static.case.law/us/{v}/cases/{hit[0]["f"]}.json')
                if raw:
                    d = json.loads(raw)
                    rec = {'cap': d.get('id'), 'cite': c['cit'], 'head': (d.get('casebody') or {}).get('head_matter') or ''}
                time.sleep(0.4)
            json.dump(rec, open(f'{CAPC}/{fname(c["id"])}.json', 'w', encoding='utf-8'), ensure_ascii=False)
        print('volume', v, len(vols[v]), flush=True)


# ---------------------------------------------------------------- Library of Congress syllabus
SYL_RUN = re.compile(r"^(OCTOBER TERM,? \d{4}\.?|Syllabus\.?|Opinion of the Court\.?|Per Curiam\.?|Statement of the Case\.?|\d+ U\. ?S\.?|\d+|"
                     r".{3,90} v\. .{2,90}[.,]? \d+|\d+ .{3,90} v\. .{2,90}\.?|\d{2,4} ?Stat\. .*|\d+ ?See .*)$")
SYL_END = re.compile(r"^(PER CURIAM\.?$|(MR\. )?(CHIEF )?JUSTICE [A-Z][A-Za-z]+.{0,60}(delivered|announced)|.{0,160}\bargued the cause|"
                     r".{0,160}\b(filed|submitted) (a |the )?briefs?\b|.{0,160}\bsubmitted (for|on behalf of) |.{0,120}\bby appointment of the Court|"
                     r"[A-Z][A-Za-z.,' -]{2,60}, pro se\b|(Messrs?|Mrs?)\. [A-Z].{0,160}\bfor (the )?(petitioners?|respondents?|appellants?|appellees?|the United States)\b)")


CITE = re.compile(r"\bStat\.( \(Supp\.\))? \d+|\b\d+ U\. ?S\. ?C\.( §+)? \d+|\b\d+ (U\. ?S\.|F\. ?(2d|3d|Supp\.)?|Stat\.|S\. ?Ct\.|L\. ?Ed\.|[A-Z][A-Za-z.]{0,14}( \(\w+\))?) \d+\b")


def strip_footnotes(t):
    """pdftotext puts footnote blocks (of this case or the one ending above it) between the syllabus paragraphs: drop
    blocks that open with a footnote mark or are mostly citations without the syllabus's 'P. 123' page references."""
    keep = []
    for l in t.replace('\f', '\n').split('\n'):
        s = l.strip()
        if re.match(r"^([*†‡]|\d{1,2}\s?\*|['‘’]?See,? |['‘’]?Cf\. |\d{1,2} ?[A-Z][a-z]+ v\. )", s):
            continue
        if len(CITE.findall(s)) >= 2 and not re.search(r'\bPp?\. \d+', s):
            continue
        keep.append(l)
    return '\n'.join(keep)


def polish(h):
    """Running heads and printer's marks that pdftotext leaves inside a paragraph."""
    h = re.sub(r"\s*\b\d{5,7}-+\d+-+\d+,?", '', h)
    h = re.sub(r"\s*\bOCTOBER TER[A-Z]*,? \d{4}\.?", '', h)
    h = re.sub(r"\s+[A-Z][A-Z0-9 .,&'’-]{2,60} v\. [A-Z][A-Z0-9 .,&'’-]{2,60}\.(?= [a-z(])", '', h)
    return re.sub(r'[ \t]{2,}', ' ', h).strip()


def loc_parse(t, c):
    t = bh.syllabus(t)
    return t or ''


def loc_parse2(t, c):
    """Tolerant reading: start after the case's own Argued/Decided line (the PDF may open with the end of the previous
    case), skip running heads, stop at counsel or the opinion's first line."""
    lines = [l.strip() for l in t.replace('\f', '\n').split('\n') if l.strip()]
    first = re.sub(r'[^a-z]', '', (c['n'].split(' v. ')[0].split(',')[0]).lower())[:10]
    dates = [i for i, l in enumerate(lines[:80]) if re.search(r'\b(Argued|Decided|Submitted)\b.*\d{4}', l)]
    if not dates:
        return ''
    start = dates[0] + 1
    for i in dates:   # prefer the date line that follows this case's own caption
        if any(first and first in re.sub(r'[^a-z]', '', lines[j].lower()) for j in range(max(0, i - 4), i)):
            start = i + 1
            break
    body = []
    for l in lines[start:]:
        if SYL_END.match(l):
            break
        if SYL_RUN.match(l) or l.startswith('*'):
            continue
        if body and body[-1].endswith('-') and l[:1].islower():
            body[-1] = body[-1][:-1] + l
        else:
            body.append(l)
    text = bh.clean(' '.join(body))
    text = re.sub(r'\s*\bHeld[:.]?(?=[\sA-Z])\s*', '\nHeld: ', text)
    text = re.sub(r'(?<=[.:]) (?=\d{1,2}\. [A-Z(])', '\n', text)
    text = re.sub(r'(?<=[.:]) (?=\([a-z]\) )', '\n', text)
    text = re.sub(r'(?<=[.]) (?=(CERTIORARI|APPEAL|ON WRIT|ON CERTIFICATE)\b)', '\n', text, flags=re.I)
    text = text.strip()
    if len(text) < 150 or not re.search(r'Held|^1\. |\n1\. |affirmed|reversed|dismissed|remanded|vacated', text, re.I):
        return ''
    if len(text) > 3200:
        cut = text[:3200]
        m = max(cut.rfind('. '), cut.rfind('.\n'))
        text = (cut[:m + 1] if m > 1600 else cut) + ' …'
    return text


DOCKET_LINE = re.compile(r"^[*†\s]*Nos?\.\s*[\w,\s&.-]{1,60}?\.\s*(Argued|Reargued|Submitted|Decided|Order entered|Certiorari granted|Motion|Per curiam|"
                         r"[A-Z][a-z]+ (granted|denied|dismissed|reversed|affirmed))?.{0,120}?\d{4}\.?", re.I)
DATE_LINE = re.compile(r"^((Re)?argued|Decided|Submitted)\b.{0,80}\d{4}[.-]*", re.I)
OUTCOME = re.compile(r"affirm|revers|dismiss|remand|vacat|grant|den(y|ied)|decree|decided on|on authority|authority of|followed|restored|overrul|held|equally divided", re.I)


def loc_parse3(t, c):
    """Last resort for short syllabi: the block between this case's docket line (any form: 'No. 100. Certiorari granted
    and judgment reversed, Nov. 17, 1952.', 'No. 87-107. Order entered ...') and counsel or the opinion, kept when it
    states an outcome. Picks up per curiam orders, decrees and 'Decided on authority of ...' syllabi."""
    lines = [l.strip() for l in t.replace('\f', '\n').split('\n') if l.strip()]
    words = [w for w in re.findall(r'[A-Za-z]{3,}', c['n'].split(' v. ')[0]) if w.lower() not in {'the', 'united', 'states', 'parte'}]
    first = (words or re.findall(r'[A-Za-z]{3,}', c['n']) or [''])[0].lower()   # 'School Bd. of ...' is 'SCHOOL BOARD OF ...' in the caption
    start = None
    for i, l in enumerate(lines[:120]):
        m = DOCKET_LINE.match(l) or DATE_LINE.match(l)
        if m and any(first and first in re.sub(r'[^a-z]', '', lines[j].lower()) for j in range(max(0, i - 4), i)):
            start, rest = i + 1, l[m.end():].strip()
            break
    if start is None:
        return ''
    body = [rest] if rest else []
    for l in lines[start:]:
        if SYL_END.match(l) or re.match(r"^(DECREE|OPINION|ORDER)\.?$|^(MR\. )?(CHIEF )?JUSTICE [A-Z]+", l):
            break
        if SYL_RUN.match(l) or l.startswith('*'):
            continue
        if body and body[-1].endswith('-') and l[:1].islower():
            body[-1] = body[-1][:-1] + l
        else:
            body.append(l)
        if sum(map(len, body)) > 3400:
            break
    text = bh.clean(' '.join(body))
    # the rest of a split 'Argued ...-Decided ...' line or a run of decree dates, then counsel or 'The facts are stated'
    lead = re.compile(r'^[-–—,\s]*((\w+ ){0,3}(entered|Entered|ENTERED|(Re)?argued|Argued|Decided|Submitted|certified)\b[^.]{0,60}?\d{4}|and [A-Z][a-z]+ \d{1,2}, \d{4})\.?\s*')
    while lead.match(text):
        text = lead.sub('', text, count=1)
    keep = []
    for sent in re.split(r'(?<=\.) (?=[A-Z])', text):
        if keep and (re.match(r"(Mr|Messrs|Mrs)\.", sent) or re.search(
                r"\bfor (the )?(petitioners?|respondents?|appellants?|appellees?|plaintiffs?|defendants?|movants?|applicants?|the United States|the State)\b|"
                r"\bwith whom\b|\bpro se\b|\bon the (motion|briefs?)\b|\bin opposition\b|\bwas on the brief|(?i:\bfacts a\w{1,3} (stated|sufficiently))", sent)):
            break
        keep.append(sent)
    text = re.sub(r"(?<=\.)\s+([A-Z][a-z]+ )+[A-Z]\.$", '', ' '.join(keep))   # 'John G.' of a counsel line split at the initial
    text = re.sub(r'(?<=[.:]) (?=\([a-z]\) )', '\n', re.sub(r'\s*\bHeld[:.]?(?=[\sA-Z])\s*', '\nHeld: ', text)).strip()
    if len(text) < 30 or not OUTCOME.search(text) or not re.search(r'[a-z]{2,} [a-z]{2,} [a-z]{2,}|, (\w+ )?(affirmed|reversed|vacated|dismissed)\b|^[A-Z][a-z]+( [a-z]+)? (dismissed|granted|denied|affirmed|reversed|vacated)\b', text):
        return ''
    if len(text) > 3200:
        cut = text[:3200]
        m = max(cut.rfind('. '), cut.rfind('.\n'))
        text = (cut[:m + 1] if m > 1600 else cut) + ' …'
    return text


def fetch_loc():
    import loc_syllabus as ls
    os.makedirs(LOC, exist_ok=True)
    D = Data()
    done_cap = {k: v for k, v in build_cap(D).items()}
    jobs = []
    for c in sorted(D.cases, key=lambda c: c.get('dec') or '', reverse=True):
        if not D.need(c) or c['id'] in done_cap or os.path.exists(f'{LOC}/{fname(c["id"])}.txt'):
            continue
        u = ls.pdf_url(c)
        if u:
            jobs.append((c['id'], u))
    print(len(jobs), 'LoC PDFs to read', flush=True)
    with ThreadPoolExecutor(3) as ex:
        for k, _ in enumerate(ex.map(ls.one, jobs)):
            if k % 200 == 0:
                print(k, '/', len(jobs), flush=True)


# ---------------------------------------------------------------- Wikipedia
WAPI = 'https://en.wikipedia.org/w/api.php?'


def wapi(**p):
    raw = get(WAPI + urllib.parse.urlencode({'format': 'json', 'formatversion': 2, **p}), tries=6)
    if not raw:
        raise RuntimeError('Wikipedia API unavailable')   # nothing is cached, so a re-run tries again
    time.sleep(1.0)
    return json.loads(raw)


_VOLS = {}


def volume_names(v):
    """Case names by first page from Wikipedia's 'List of United States Supreme Court cases, volume N' (SCOTUSRow rows)."""
    if v not in _VOLS:
        r = wapi(action='query', prop='revisions', titles=f'List of United States Supreme Court cases, volume {v}', rvprop='content', rvslots='main')
        pg = ((r.get('query') or {}).get('pages') or [{}])[0]
        wt = (((pg.get('revisions') or [{}])[0].get('slots') or {}).get('main') or {}).get('content') or ''
        _VOLS[v] = {}
        for row in re.findall(r'\{\{\s*SCOTUSRow(.*?)\}\}', wt, re.S):
            n, pgno = re.search(r'\|\s*case name\s*=\s*([^|\n]+)', row), re.search(r'\|\s*page\s*=\s*(\d+)', row)
            if n and pgno:
                _VOLS[v].setdefault(pgno.group(1), []).append(n.group(1).strip())
    return _VOLS[v]


def wiki_page(title, v, p):
    r = wapi(action='query', prop='revisions|extracts', titles=title, rvprop='content|ids', rvslots='main', exintro=1, explaintext=1, redirects=1)
    pg = ((r.get('query') or {}).get('pages') or [{}])[0]
    rev = (pg.get('revisions') or [{}])[0]
    wt = ((rev.get('slots') or {}).get('main') or {}).get('content') or ''
    if not re.search(r'\{\{\s*Infobox SCOTUS case', wt, re.I):
        return None
    if not (re.search(r'\|\s*USVol\s*=\s*' + v + r'\b', wt) and re.search(r'\|\s*USPage\s*=\s*' + p + r'\b', wt)):
        return None
    return {'t': pg['title'], 'rev': rev.get('revid'), 'x': pg.get('extract') or ''}


def wiki_one(c):
    """The case's Wikipedia article, accepted only if its infobox gives the same U.S. Reports volume and page. Candidates:
    the name Wikipedia's volume list gives for that page, then a search for the citation."""
    m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
    if not m:
        return None
    v, p = m.groups()
    for title in volume_names(v).get(p, []):
        r = wiki_page(title, v, p)
        if r:
            return r
    hits = (wapi(action='query', list='search', srsearch=f'"{v} U.S. {p}"', srlimit=8, srnamespace=0).get('query') or {}).get('search') or []
    words = [w for w in re.findall(r"[A-Za-z]{4,}", c['n']) if w.lower() not in {'united', 'states', 'company', 'state', 'city', 'county', 'commission'}]
    for h in hits:
        title = h['title']
        if title.startswith('List of') or (words and not any(w.lower() in title.lower() for w in words)):
            continue
        r = wiki_page(title, v, p)
        if r:
            return r
    return {}


def fetch_wiki():
    os.makedirs(WIKI, exist_ok=True)
    D = Data()
    imp = set().union(*important(D).values())
    cap, loc = build_cap(D), build_loc(D)
    todo = [D.by_id[i] for i in sorted(imp) if D.need(D.by_id[i]) and i not in cap and i not in loc and not os.path.exists(f'{WIKI}/{fname(i)}.json')]
    print(len(todo), 'important cases to look up on Wikipedia', flush=True)
    for k, c in enumerate(todo):
        try:
            r = wiki_one(c)
        except RuntimeError as e:
            print(' ', c['id'], e, flush=True)
            continue
        if r is not None:
            json.dump(r, open(f'{WIKI}/{fname(c["id"])}.json', 'w', encoding='utf-8'), ensure_ascii=False)
        if k % 50 == 0:
            print(k, '/', len(todo), flush=True)


WIKIN = 'data/raw/wiki_name'


def wiki_by_name(c):
    """Second pass for cases the citation lookup missed (the site's first page is sometimes wrong: Dellmuth v. Muth is
    491 U.S. 223, not 22): search Wikipedia for the case name; accept an article whose title shares both parties' first
    words and whose infobox gives the same volume and either the same page or the same decision year. The infobox page is
    kept, so the LoC syllabus PDF can be fetched at the right address."""
    m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
    if not m or ' v. ' not in c['n']:
        return {}
    v, p = m.groups()
    sides = [re.findall(r"[A-Za-z]{3,}", s) for s in c['n'].split(' v. ', 1)]
    skip = {'the', 'united', 'states', 'america', 'and', 'company', 'state', 'city', 'county', 'commission', 'commissioner', 'director', 'inc', 'corp', 'district', 'board'}
    keys = [next((w.lower() for w in s if w.lower() not in skip), (s[0].lower() if s else '')) for s in sides]
    q = re.sub(r',.*?(?= v\. )|,.*$', '', c['n'])
    hits = (wapi(action='query', list='search', srsearch=q, srlimit=6, srnamespace=0).get('query') or {}).get('search') or []
    yr = (c.get('dec') or '')[:4]
    for h in [{'title': q}] + hits:   # the name as a title (or redirect) first
        t = h['title']
        if ' v. ' not in t or t.startswith('List of') or not all(k and k in t.lower() for k in keys):
            continue
        r = wapi(action='query', prop='revisions|extracts', titles=t, rvprop='content|ids', rvslots='main', exintro=1, explaintext=1, redirects=1)
        pg = ((r.get('query') or {}).get('pages') or [{}])[0]
        rev = (pg.get('revisions') or [{}])[0]
        wt = ((rev.get('slots') or {}).get('main') or {}).get('content') or ''
        vol, page = re.search(r'\|\s*USVol\s*=\s*(\d+)', wt), re.search(r'\|\s*USPage\s*=\s*(\d+)', wt)
        dec = re.search(r'\|\s*DecideYear\s*=\s*(\d{4})', wt) or re.search(r'\|\s*DecideDate\s*=\s*[^|\n]*?(\d{4})', wt)
        if not (vol and page and vol.group(1) == v and (page.group(1) == p or (dec and dec.group(1) == yr))):
            continue
        return {'t': pg['title'], 'rev': rev.get('revid'), 'x': pg.get('extract') or '', 'page': page.group(1)}
    return {}


def fetch_wiki_name():
    """Name search for every case still without a summary (important ones first); where the infobox gives another first
    page, the LoC syllabus PDF is fetched from that page's address into the LoC cache."""
    import loc_syllabus as ls
    os.makedirs(WIKIN, exist_ok=True)
    D = Data()
    imp = set().union(*important(D).values())
    have = set(build_cap(D)) | set(build_loc(D)) | {os.path.basename(f)[:-5].replace('_', '/', 1) for f in glob.glob(f'{WIKI}/*.json') if os.path.getsize(f) > 2}
    todo = [c for c in D.cases if D.need(c) and c['id'] not in have and not os.path.exists(f'{WIKIN}/{fname(c["id"])}.json')]
    todo.sort(key=lambda c: (c['id'] not in imp, c.get('dec') or ''))
    print(len(todo), 'cases to look up on Wikipedia by name', flush=True)
    for k, c in enumerate(todo):
        try:
            r = wiki_by_name(c)
        except RuntimeError as e:
            print(' ', c['id'], e, flush=True)
            continue
        json.dump(r, open(f'{WIKIN}/{fname(c["id"])}.json', 'w', encoding='utf-8'), ensure_ascii=False)
        v = (c.get('cit') or '').split(' ')[0]
        if r.get('page') and r['page'] != c['cit'].split(' ')[-1] and v.isdigit() and int(v) <= 542 and not os.path.exists(f'{LOC}/{fname(c["id"])}.txt'):
            k2 = f'usrep{int(v):03d}{int(r["page"]):03d}'
            ls.one((c['id'], f'https://tile.loc.gov/storage-services/service/ll/usrep/usrep{int(v):03d}/{k2}/{k2}.pdf'))
        if k % 50 == 0:
            print(k, '/', len(todo), flush=True)


CAPF = 'data/raw/cap/meta_full'


def fetch_recite():
    """Cases whose first page on the site is wrong get no LoC PDF (the address is built from the page). For cases still
    without a summary and without a cached LoC page, find the case in the CAP volume metadata by decision date and a
    party's name, and fetch the LoC syllabus PDF from the page CAP gives. Pre-1931 cases also get CAP's head matter."""
    import loc_syllabus as ls
    os.makedirs(CAPF, exist_ok=True)
    D = Data()
    have = set(build_cap(D)) | set(build_loc(D))
    todo = collections.defaultdict(list)
    for c in D.cases:
        m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
        if m and D.need(c) and c['id'] not in have and not os.path.exists(f'{LOC}/{fname(c["id"])}.txt') and c.get('dec'):
            todo[int(m.group(1))].append(c)
    print(sum(map(len, todo.values())), 'cases in', len(todo), 'volumes', flush=True)
    found = 0
    for v in sorted(todo):
        mp = f'{CAPF}/{v}.json'
        if not os.path.exists(mp):
            raw = get(f'https://static.case.law/us/{v}/CasesMetadata.json')
            meta = [{'f': x['file_name'], 'n': x.get('name_abbreviation') or '', 'd': x.get('decision_date') or '', 'p': x.get('first_page'),
                     'court': (x.get('court') or {}).get('id')} for x in json.loads(raw)] if raw else []
            json.dump(meta, open(mp, 'w', encoding='utf-8'))
            time.sleep(0.5)
        meta = json.load(open(mp, encoding='utf-8'))
        for c in todo[v]:
            keys = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", c['n']) if w.lower() not in {'united', 'states', 'america', 'commissioner', 'internal', 'revenue', 'company', 'director'}][:3]
            score = lambda x: sum(k in x['n'].lower() for k in keys)
            hit = [x for x in meta if x['d'] == c['dec'] and x['court'] == 9009 and score(x)]
            best = max(map(score, hit), default=0)
            hit = [x for x in hit if score(x) == best]
            if len(hit) != 1 or not str(hit[0]['p'] or '').isdigit():
                continue
            pg = int(hit[0]['p'])
            if str(pg) == c['cit'].split(' ')[-1]:
                continue   # same address as before: the LoC has no PDF there
            if v <= 542:
                k = f'usrep{v:03d}{pg:03d}'
                ls.one((c['id'], f'https://tile.loc.gov/storage-services/service/ll/usrep/usrep{v:03d}/{k}/{k}.pdf'))
                found += os.path.exists(f'{LOC}/{fname(c["id"])}.txt')
            if v <= 281:   # 1930 and before: CAP head matter at the right page
                raw = get(f'https://static.case.law/us/{v}/cases/{hit[0]["f"]}.json')
                if raw:
                    d = json.loads(raw)
                    json.dump({'cap': d.get('id'), 'cite': f'{v} U.S. {pg}', 'head': (d.get('casebody') or {}).get('head_matter') or ''},
                              open(f'{CAPC}/{fname(c["id"])}.json', 'w', encoding='utf-8'), ensure_ascii=False)
                time.sleep(0.4)
    print(found, 'LoC pages fetched at corrected addresses', flush=True)


CAPO = 'data/raw/cap/order'


def fetch_orders():
    """Memorandum decisions and one-paragraph per curiam orders have no syllabus: their whole text is the summary. For
    cases still without one, fetch the CAP case file and keep the opinion text when it is short (build decides)."""
    os.makedirs(CAPO, exist_ok=True)
    D = Data()
    have = set(build_cap(D)) | set(build_loc(D))
    todo = collections.defaultdict(list)
    for c in D.cases:
        m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
        if m and D.need(c) and c['id'] not in have and not os.path.exists(f'{CAPO}/{fname(c["id"])}.json'):
            todo[int(m.group(1))].append(c)
    print(sum(map(len, todo.values())), 'cases in', len(todo), 'volumes', flush=True)
    for v in sorted(todo):
        full = json.load(open(f'{CAPF}/{v}.json', encoding='utf-8')) if os.path.exists(f'{CAPF}/{v}.json') else []
        meta = json.load(open(f'{CAPM}/{v}.json', encoding='utf-8')) if os.path.exists(f'{CAPM}/{v}.json') else []
        for c in todo[v]:
            scdb = 'SCDB ' + c['id'][5:] if c['id'].startswith('scdb/') else None
            hit = [x for x in meta if scdb and scdb in x['cites']] or [x for x in meta if c['cit'] in x['cites'] and x['court'] == 9009]
            if len(hit) != 1:
                keys = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", c['n']) if w.lower() not in {'united', 'states', 'america', 'commissioner', 'internal', 'revenue', 'company', 'director'}][:3]
                score = lambda x: sum(k in x['n'].lower() for k in keys)
                hit = [x for x in full if x['d'] == c.get('dec') and x['court'] == 9009 and score(x)]
                best = max(map(score, hit), default=0)
                hit = [x for x in hit if score(x) == best]
            rec = {}
            if len(hit) == 1:
                raw = get(f'https://static.case.law/us/{v}/cases/{hit[0]["f"]}.json')
                if raw:
                    d = json.loads(raw)
                    ops = (d.get('casebody') or {}).get('opinions') or []
                    rec = {'cap': d.get('id'), 'cite': (d.get('citations') or [{}])[0].get('cite') or c['cit'], 'name': d.get('name_abbreviation'),
                           'ops': [{'type': o.get('type'), 'author': o.get('author'), 'text': o.get('text') or ''} for o in ops]}
                time.sleep(0.4)
            json.dump(rec, open(f'{CAPO}/{fname(c["id"])}.json', 'w', encoding='utf-8'), ensure_ascii=False)


def build_orders(D):
    """The text of a short order (a single opinion of at most 700 characters, no dissent), from the CAP file."""
    out = {}
    for f in glob.glob(f'{CAPO}/*.json'):
        cid = os.path.basename(f)[:-5].replace('_', '/', 1)
        c = D.by_id.get(cid)
        r = json.load(open(f, encoding='utf-8'))
        if not c or not D.need(c) or len(r.get('ops') or []) != 1:
            continue
        t = re.sub(r'\s+', ' ', r['ops'][0]['text']).strip()
        t = re.sub(r'^(PER CURIAM|Per Curiam)[.:]?\s*|^M[Rr]\. (Chief )?Justice \w+ delivered the opinion of the [Cc]ourt\.\s*', '', t)
        keep = []   # counsel printed after the order
        for sent in re.split(r'(?<=\.)(?<!Mr\.)(?<!Messrs\.) (?=[A-Z])', t):
            if keep and re.search(r"\bwith whom\b|\bargued the cause|\bon the briefs?\b|\bfor (the )?(petitioners?|respondents?|appellants?|appellees?|plaintiffs?|defendants?)\b", sent):
                break
            keep.append(sent)
        t = ' '.join(keep)
        if 15 <= len(t) <= 700 and OUTCOME.search(t) and not garbled(t, 1):
            out[cid] = {'h': t, 'cite': r.get('cite') or c.get('cit'), 'cap': r.get('cap'), 'src': 'order'}
    return out


def wiki_text(x):
    paras = [re.sub(r'\s+', ' ', p).strip() for p in (x or '').split('\n')]
    paras = [p for p in paras if len(p) > 40]
    text, out = 0, []
    for p in paras:
        if text + len(p) > 2400 and out:
            break
        out.append(p)
        text += len(p)
    return '\n'.join(out)


# ---------------------------------------------------------------- build
NOT_SUMMARY = re.compile(r"\b(argued|reargued|submitted) the cause\b|\bon the briefs?\b|\bdelivered the opinion\b|\bfiled an? (dissenting|concurring) opinion|"
                         r"\bJJ\., joined\b|\btook no part\b|\bfor (the )?(appellants?|appellees?|petitioners?|respondents?|movants?|plaintiffs?|defendants?|"
                         r"complainants?|the United States|the State of [A-Z]\w+)\b|\bpro se\b|\bby appointment of the Court\b|\bAttorneys? General\b|"
                         r"\bamici curiae\b|\b(also )?on (appeal|certiorari|writ) (from|to) the same\b|^Together with No")


def build_cap(D):
    out = {}
    for f in glob.glob(f'{CAPC}/*.json'):
        cid = os.path.basename(f)[:-5].replace('_', '/', 1)
        c = D.by_id.get(cid)
        if not c or not D.need(c):
            continue
        r = json.load(open(f, encoding='utf-8'))
        h = drop_noise_lines(cap_extract(r.get('head') or ''))
        # later volumes keep only counsel and the line-up of opinions: those lines are not a summary
        h = '\n'.join(l for l in h.split('\n') if not NOT_SUMMARY.search(l) and not re.match(r'(?i)the (case|facts)\b.{0,12}\bstated\b', l)).strip()
        if year(c) <= 1930 and len(h) >= 80 and not garbled(h) and re.search(r'[a-z]{3,} [a-z]{3,} [a-z]{3,}', h):
            out[cid] = {'h': h, 'cite': r.get('cite') or c.get('cit'), 'cap': r.get('cap')}
            continue
        # a one-line headnote such as 'Sevier v. Haskell, 14 Wall. 12, followed.' or 'Decided on the authority of ...'
        short = [l.strip() for l in (r.get('head') or '').split('\n') if re.match(
            r"^[A-Z].{4,200}\b(followed|approved|affirmed|reaffirmed|governed by|controlled by|(up)?on (the )?authority of)\b.{0,120}\.$", l.strip())]
        if year(c) <= 1930 and short and not NOT_SUMMARY.search(short[0]) and not garbled(short[0], 1):
            out[cid] = {'h': bh.clean(short[0]), 'cite': r.get('cite') or c.get('cit'), 'cap': r.get('cap')}
    return out


LEAD = re.compile(r'^[-–—:,\s]*((\w+ ){0,3}(entered|Entered|ENTERED|(Re)?argued|Argued|Decided|Submitted|certified|denied)\s*.{0,40}?\d{4}|and [A-Z][a-z]+ \d{1,2}, \d{4})\.?[-–—\s]*')


def tidy(h):
    """Dates left over from the docket line at the start; 'The facts are stated in the opinion.' and counsel at the end."""
    for _ in range(4):
        h = LEAD.sub('', h, count=1)
    h = re.sub(r'^[-–—:,\s]+', '', h)
    m = re.search(r"\s(?i:the (facts|case) (are|is|axe) (stated|sufficiently))", h)
    return (h[:m.start()] if m and m.start() > 25 else h).strip()


def build_loc(D):
    out = {}
    for f in glob.glob(f'{LOC}/*.txt'):
        cid = os.path.basename(f)[:-4].replace('_', '/', 1)
        c = D.by_id.get(cid)
        if not c or not D.need(c):
            continue
        raw = open(f, encoding='utf-8', errors='replace').read()
        t = strip_footnotes(raw)
        for parse in (loc_parse, loc_parse2, loc_parse3):   # the first reading that is not scanning noise
            h = tidy(polish(parse(raw if parse is loc_parse3 else t, c)))   # a short syllabus may cite two cases: keep it whole
            if h and not garbled(h, 8 if len(h) > 300 else 3 if len(h) > 150 else 1):
                out[cid] = {'h': h, 'cite': c.get('cit'), 'src': 'loc'}
                break
    return out


def build():
    D = Data()
    D.mine = {}
    recs = build_cap(D)
    for k, v in build_loc(D).items():
        if k not in recs or len(recs[k]['h']) < 120 <= len(v['h']):   # a full syllabus beats a one-line CAP headnote
            recs[k] = v
    for k, v in build_orders(D).items():
        recs.setdefault(k, v)
    nw = 0
    for f in glob.glob(f'{WIKI}/*.json') + glob.glob(f'{WIKIN}/*.json'):
        cid = os.path.basename(f)[:-5].replace('_', '/', 1)
        r = json.load(open(f, encoding='utf-8'))
        if cid in recs or not r.get('t') or cid not in D.by_id or not D.need(D.by_id[cid]):
            continue
        h = wiki_text(r.get('x'))
        if len(h) < 120:
            continue
        recs[cid] = {'h': h, 'src': 'wiki', 't': r['t'], 'rev': r.get('rev'),
                     'url': 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(r['t'].replace(' ', '_'))}
        nw += 1
    by_year = collections.defaultdict(dict)
    for cid, r in recs.items():
        by_year[str(year(D.by_id[cid]))][cid] = r
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(f'{OUT}/*.js'):
        os.remove(f)
    for y, rr in by_year.items():
        open(f'{OUT}/{y}.js', 'w', encoding='utf-8').write('window.HEADNOTES=window.HEADNOTES||{};Object.assign(window.HEADNOTES,' +
                                                            json.dumps(rr, ensure_ascii=False, separators=(',', ':')) + ');')
    open('docs/data/summaries-index.js', 'w', encoding='utf-8').write('window.SUMMARIES_INDEX=' + json.dumps(sorted(by_year)) + ';')
    n = collections.Counter(r.get('src', 'cap') for r in recs.values())
    print(dict(n), 'summaries in', len(by_year), 'year files')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'coverage'
    {'oyez': fetch_oyez, 'cap': fetch_cap, 'loc': fetch_loc, 'wiki': fetch_wiki, 'wikiname': fetch_wiki_name, 'recite': fetch_recite, 'orders': fetch_orders, 'build': build,
     'coverage': coverage, 'before': lambda: coverage(new=False)}[cmd]()
