"""Reporter's headnotes for case pages that have no Oyez summary: docs/data/headnotes/<year>.js
(window.HEADNOTES[<case id>] = {h: text, cite, cap}) and docs/data/headnotes-index.js (years present).

Source: the head matter of the United States Reports as digitized by the Caselaw Access Project (Harvard Law School
Library), cached by scripts/cap_headnotes.py in data/raw/cap/head/. The reporters' syllabi are public domain; CAP keeps
them for older volumes (to about 1930). The text is OCR: obvious scanning debris is removed, nothing is rewritten.

Kept: the headnote paragraphs and the reporter's statement of the case that follow the caption and dates, up to the
names of counsel, cut at a sentence end after about 2,400 characters. Cases are matched to the site by Supreme Court
Database id (CAP lists it among a case's citations) or by U.S. Reports citation. Only cases with no Oyez summary are
written (Supreme Court Database-only cases, or Oyez records with neither facts nor conclusion).
Run from the repo root:  python scripts/build_headnotes.py
"""
import collections, glob, json, os, re

OUT = 'docs/data/headnotes'
LIMIT = 2400
DATE = re.compile(r'^(Argued|Submitted|Decided|Reargued|Announced|Motion submitted|Petition for)\b.*\d{4}\.?\s*$', re.I)
CAPTION = re.compile(r'^(ERROR|APPEAL|APPEALS|CERTIORARI|ON (WRIT|CERTIFICATE|PETITION|MOTION)|CROSS|ORIGINAL|IN EQUITY|No[s]?\.\s|NO[S]?\.\s|BILL IN EQUITY)', re.I)
COUNSEL = re.compile(r"^(Mr\.|Messrs\.?|Mrs\.|Miss |Solicitor|The Solicitor|The Attorney|Attorney General|Assistant Attorney|Special Assistant|"
                     r"On the brief|With (him|them)|Briefs? (of|for|on behalf)|.{0,120}\b(argued|submitted) (the cause|for|on behalf)|"
                     r".{0,80}\bfor (the )?(appellants?|appellees?|plaintiffs? in error|defendants? in error|petitioners?|respondents?|complainants?|the United States)\.?\s*$)")
DEBRIS = str.maketrans({'•': '', '■': '', '□': '', '▪': '', '|': '', '¦': '', '«': '', '»': '', '♦': ''})


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def clean(s):
    s = s.translate(DEBRIS)
    s = re.sub(r"\s+([.,;:])", r'\1', s)
    s = re.sub(r'(\w)- (\w)', r'\1\2', s)          # "to- the" style hyphen debris inside lines
    s = re.sub(r"\s'(?=\s|$)", '', s)             # stray apostrophes left by specks on the page
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s.strip()


def extract(head):
    lines = [l.strip() for l in head.split('\n') if l.strip()]
    if len(lines) < 2:
        return ''
    start = 1                                      # line 0 is the case name
    for i, l in enumerate(lines[:10]):
        if DATE.match(l) or CAPTION.match(l) or (i and l.isupper() and len(l) < 200):
            start = i + 1
    body = []
    for l in lines[start:]:
        if COUNSEL.match(l):
            break
        if re.match(r'^(The case is stated in the opinion|The facts are stated in the opinion|The case is sufficiently stated)', l, re.I):
            break
        body.append(clean(l))
    text = '\n'.join(b for b in body if len(b) > 2)
    if len(text) < 80:
        return ''
    if len(text) > LIMIT:
        cut = text[:LIMIT]
        m = max(cut.rfind('. '), cut.rfind('.\n'))
        text = (cut[:m + 1] if m > LIMIT // 2 else cut) + ' …'
    return text


# ---- official syllabus from the Library of Congress U.S. Reports PDFs (scripts/loc_syllabus.py), 1930s on
RUNHEAD = re.compile(r"^(OCTOBER TERM,? \d{4}\.?|Syllabus\.?|\d+ U\. ?S\.?|\d+|.{3,90} v\. .{2,90}[.,]? \d+|\d+ .{3,90} v\. .{2,90}\.?)$")
SYL_STOP = re.compile(r"^(Opinion of the Court\.?$|PER CURIAM|Per Curiam\.?$|(MR\. )?(CHIEF )?JUSTICE [A-Z][A-Za-z]+.{0,60}(delivered|announced)|"
                      r".{0,160}\bargued the cause|.{0,160}\b(filed|submitted) (a |the )?briefs?\b|.{0,120}\bby appointment of the Court|[A-Z][A-Za-z.,' -]{2,60}, pro se\b)")


def syllabus(t):
    lines = [l.strip() for l in t.replace('\f', '\n').split('\n') if l.strip()]
    start = None
    for i, l in enumerate(lines[:40]):
        if re.search(r'\b(Argued|Decided|Submitted)\b.*\d{4}', l):
            start = i + 1
            break
    if start is None:
        return ''
    body = []
    for l in lines[start:]:
        if SYL_STOP.match(l):
            break
        if RUNHEAD.match(l) or l.startswith('*'):
            continue
        if body and body[-1].endswith('-') and l[:1].islower():
            body[-1] = body[-1][:-1] + l
        else:
            body.append(l)
    text = clean(' '.join(body))
    text = re.sub(r'\s*\bHeld[:.]?(?=[\sA-Z])\s*', '\nHeld: ', text)
    text = re.sub(r'(?<=[.:]) (?=\d{1,2}\. [A-Z(])', '\n', text)
    text = re.sub(r'(?<=[.:]) (?=\([a-z]\) )', '\n', text)
    text = re.sub(r"(?<=\.) (?=[A-Z][A-Za-z'’]+, (C\. )?J\., (delivered|announced|filed))", '\n', text)
    if len(text) < 150 or not re.search(r'Held|\n1\. |affirmed|reversed|dismissed|remanded|vacated', text, re.I):
        return ''
    if len(text) > 3200:
        cut = text[:3200]
        m = max(cut.rfind('. '), cut.rfind('.\n'))
        text = (cut[:m + 1] if m > 1600 else cut) + ' …'
    return text


def main():
    S = load_js('docs/data/scotus.js')['cases']
    by_scdb = {c['id'][5:]: c for c in S if c['id'].startswith('scdb/')}
    by_cit = {}
    for c in S:
        if c.get('cit'):
            by_cit.setdefault(c['cit'], c)
    summ = {}
    for f in glob.glob('data/raw/oyez/cases/*.json'):
        d = json.load(open(f, encoding='utf-8'))
        summ[os.path.basename(f)[:-5]] = bool((d.get('facts_of_the_case') or '').strip() or (d.get('conclusion') or '').strip())
    need = lambda c: c.get('s') == 1 or summ.get(c['id'].replace('/', '_')) is False
    out = collections.defaultdict(dict)
    n = 0
    for f in glob.glob('data/raw/cap/head/*.json'):
        for r in json.load(open(f, encoding='utf-8')):
            c = by_scdb.get(r.get('scdb') or '') or by_cit.get(r.get('cite') or '')
            if not c or not need(c) or c['id'] in out[str(c['y'])]:
                continue
            h = extract(r['head'])
            if not h:
                continue
            out[str(c['y'])][c['id']] = {'h': h, 'cite': r.get('cite'), 'cap': r.get('cap')}
            n += 1
    by_id = {c['id']: c for c in S}
    n2 = 0
    for f in glob.glob('data/raw/loc_syl/*.txt'):
        k = os.path.basename(f)[:-4]
        cid = k.replace('_', '/', 1)
        c = by_id.get(cid)
        if not c or not need(c) or cid in out[str(c['y'])]:
            continue
        h = syllabus(open(f, encoding='utf-8', errors='replace').read())
        if h:
            out[str(c['y'])][cid] = {'h': h, 'cite': c.get('cit'), 'src': 'loc'}
            n2 += 1
    print(n2, 'syllabi from Library of Congress PDFs')
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(f'{OUT}/*.js'):
        os.remove(f)
    for y, recs in out.items():
        if recs:
            open(f'{OUT}/{y}.js', 'w', encoding='utf-8').write('window.HEADNOTES=window.HEADNOTES||{};Object.assign(window.HEADNOTES,' +
                                                               json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');')
    open('docs/data/headnotes-index.js', 'w', encoding='utf-8').write('window.HEADNOTES_INDEX=' + json.dumps(sorted(y for y in out if out[y])) + ';')
    print(n, 'headnotes in', len([y for y in out if out[y]]), 'year files')


if __name__ == '__main__':
    main()
