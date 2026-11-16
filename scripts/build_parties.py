"""Build the Parties & advocates tab of the case pages: docs/data/parties/<term>.js (window.PARTIES[<case id>]).

Sources (all already cached by other scripts):
  supremecourt.gov docket pages   data/raw/docket/hist/<docket>.html (dockets_fetch.py, argued cases since OT2004) and
                                  data/raw/docket/d-<docket>.html (docket.sh, pending cases):
                                  the case title (the parties as the Court styles them), the lower court, and counsel of
                                  record for each side with their firm or office and the party they represent.
                                  Email addresses, phone numbers and street addresses are left out.
  official argument transcripts   data/raw/transcripts/<term>/<docket>_*.txt (transcripts_fetch.py): the APPEARANCES page,
                                  i.e. each lawyer who argued, with the city and the side, verbatim.
The case page adds Oyez's party names and advocate list live, when Oyez has them.
Run from the repo root:  python scripts/build_parties.py
"""
import collections, glob, html, json, os, re

OUT = 'docs/data/parties'


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def txt(s):
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s)).replace('\xa0', ' ')
    return '\n'.join(re.sub(r'[ \t]+', ' ', ln).strip() for ln in s.split('\n') if ln.strip())


SIDE = lambda h: 'pet' if re.search(r'petitioner|appellant|plaintiff|movant|applicant', h, re.I) else 'res' if re.search(r'respondent|appellee|defendant', h, re.I) else 'other'


ADDRESSY = re.compile(r'^(?:\d|Suite\b|Ste\.?\b|P\.?\s?O\.?\s?Box|Post Office Box|Floor\b|\d+(?:st|nd|rd|th) Floor|Room\b)', re.I)


def docket_info(raw):
    out = {}
    m = re.search(r'Title:\s*</(?:span|td|TD)>\s*</?(?:td|TD)[^>]*>\s*(<Table.*?</Table>)', raw, re.S | re.I) or         re.search(r'Title:\s*</(?:span|td|TD)>.*?<(?:td|TD)[^>]*>(.*?)</(?:td|TD)>', raw, re.S)
    if m:
        out['title'] = re.sub(r'\s+', ' ', txt(m.group(1))).strip()
    m = re.search(r'Lower Ct:\s*</(?:span|td|TD)>.*?<(?:td|TD)[^>]*>(.*?)</(?:td|TD)>', raw, re.S)
    if m:
        lc = re.sub(r'\s+', ' ', txt(m.group(1))).strip()
        if lc:
            out['lower'] = lc
    counsel = []
    if 'class="ContactName"' in raw:                        # newer docket pages
        for card in re.finditer(r'<div class="card-heading">\s*(.*?)\s*</div>\s*<div class="card-body">(.*?)(?=<div class="card-heading">|\Z)', raw, re.S):
            head = txt(card.group(1))
            if not re.match(r'Attorneys|Other', head):
                continue
            side = SIDE(head)
            for c in re.finditer(r'<div class="ContactName">(.*?)</div>\s*<div class="ContactData2">(.*?)</div>', card.group(2), re.S):
                name_lines = txt(c.group(1)).split('\n')
                data = c.group(2)
                addr = re.search(r'<span class="address1">(.*?)</span>', data, re.S)
                org = txt(addr.group(1)).split('\n')[0] if addr else ''
                party = re.search(r'Party name:\s*([^<]+)', data)
                counsel.append({'side': side, 'name': name_lines[0], 'cor': any('Counsel of Record' in x for x in name_lines),
                                'org': org if org and not ADDRESSY.match(org) else '', 'party': html.unescape(party.group(1)).strip() if party else ''})
    else:                                                   # older pages: one table, rows per lawyer
        m = re.search(r'(<TR>\s*<TD>\s*<B>\s*Attorneys for .*?)(?:</TABLE>|</table>)', raw, re.S | re.I)
        if m:
            side, cur = 'other', None
            for row in re.findall(r'<TR>(.*?)</TR>', m.group(1), re.S | re.I):
                cells = [txt(x) for x in re.findall(r'<TD[^>]*>(.*?)</TD>', row, re.S | re.I)]
                if not cells:
                    continue
                first = cells[0]
                h = re.match(r'(?:Attorneys for (.*)|(Other)):?$', first)
                if h or re.search(r'<B>', row, re.I):
                    side = SIDE(first) if 'Other' not in first else 'other'
                    continue
                if first.startswith('Party name:'):
                    if cur:
                        cur['party'] = first.split(':', 1)[1].strip()
                    continue
                if 'Counsel of Record' in first.replace('\xa0', ' '):
                    if cur:
                        cur['cor'] = True
                    continue
                if first and not first.startswith('&') and len(cells) > 1:
                    org = cells[1].split('\n')[0] if len(cells) > 1 else ''
                    cur = {'side': side, 'name': re.sub(r'\s+', ' ', first), 'cor': False, 'org': org if org and not ADDRESSY.match(org) else '', 'party': ''}
                    counsel.append(cur)
    if counsel:
        out['counsel'] = counsel
    return out


def appearances(path):
    t = open(path, encoding='utf-8', errors='replace').read().replace('\f', '\n')
    m = re.search(r'APPEARANCES:?(.*?)(?:C\s*O\s*N\s*T\s*E\s*N\s*T\s*S|ORAL ARGUMENT OF)', t, re.S)
    if not m:
        return []
    lines = []
    for ln in m.group(1).split('\n'):
        s = ln.strip()
        if not s or re.fullmatch(r'\d{1,2}', s) or re.search(r'Heritage Reporting|Alderson Reporting|Official|www\.|\(202\)', s):
            continue
        s = re.sub(r'^\d{1,2}\s+', '', s)
        lines.append(s)
    block = ' '.join(lines)
    out = []
    # each appearance: "NAME, ESQ., City, State; on behalf of the Petitioner." (or "Solicitor General, ...; for the United States, as amicus curiae, supporting ...")
    for a in re.finditer(r'((?:GEN(?:ERAL|\.)\s+)?[A-Z][A-Z.\'’ -]+[A-Z.](?:,\s*(?:JR|SR|III|II)\.?)?)(,\s*(?:ESQ\.?|ESQUIRE)?,?)?\s*(.*?)(?=(?:\s(?:GEN(?:ERAL|\.)\s+)?[A-Z][A-Z.\'’-]+(?:\s[A-Z][A-Z.\'’-]+)+(?:,\s*(?:JR|SR|III|II)\.?)?,)|$)', block):
        name, rest = a.group(1).strip(' ,'), re.sub(r'\s+', ' ', a.group(3)).strip(' ,.')
        if len(name) < 5 or not rest or not re.search(r'behalf|for the|supporting|amicus|appointed', rest, re.I):
            continue
        side = 'pet' if re.search(r'(?:behalf of|for|supporting)\s+(?:the\s+)?(?:petitioner|appellant|reversal|vacatur)', rest, re.I) else \
               'res' if re.search(r'(?:behalf of|for|supporting)\s+(?:the\s+)?(?:respondent|appellee|affirmance|judgment)', rest, re.I) else 'other'
        out.append({'name': name.title().replace('Gen. ', 'General ').replace("'S", "'s"), 'desc': rest, 'side': side})
    return out


def main():
    S = load_js('docs/data/scotus.js')
    K = load_js('docs/data/docket.js')
    by_dk = {}
    for c in S['cases']:
        for dk in re.split(r'[,;\s]+', (c.get('d') or '').lower()):
            if dk and c.get('s') != 1:
                by_dk.setdefault(dk, c)
    for e in K['cases']:
        by_dk.setdefault(e['d'].lower(), {'id': e['id'], 't': e.get('t')})
    pages = {os.path.basename(p)[:-5].lower(): p for p in glob.glob('data/raw/docket/hist/*.html')}
    pages.update({os.path.basename(p)[2:-5].lower(): p for p in glob.glob('data/raw/docket/d-*.html')})
    trs = collections.defaultdict(list)
    for p in glob.glob('data/raw/transcripts/*/*.txt'):
        dk = re.sub(r'_[a-z0-9]+$', '', os.path.basename(p)[:-4]).lower()
        trs[re.sub(r'-(monday|tuesday|wednesday|thursday|friday|day\d)$', '', dk)].append(p)
    by_term = collections.defaultdict(dict)
    n = collections.Counter()
    for dk in set(pages) | set(trs):
        c = by_dk.get(dk)
        if not c:
            continue
        rec = {}
        if dk in pages:
            rec = docket_info(open(pages[dk], encoding='utf-8', errors='replace').read())
            raw_new = 'ContactName' in open(pages[dk], encoding='utf-8', errors='replace').read()
            rec['docket'] = (f'https://www.supremecourt.gov/docket/docketfiles/html/public/{dk}.html' if raw_new
                             else f'https://www.supremecourt.gov/search.aspx?filename=/docketfiles/{dk}.htm')
        ap = [a for p in sorted(trs.get(dk, [])) for a in appearances(p)]
        if ap:
            seen, uniq = set(), []
            for a in ap:
                if a['name'] not in seen:
                    seen.add(a['name']); uniq.append(a)
            rec['argued'] = uniq
            rec['tr'] = 1
        if not (rec.get('counsel') or rec.get('argued') or rec.get('title')):
            continue
        rec['d'] = dk
        prev = by_term[str(c.get('t'))].get(c['id'])
        if prev:                      # consolidated dockets: merge counsel
            prev.setdefault('counsel', []).extend(x for x in rec.get('counsel', []) if x not in prev.get('counsel', []))
            prev.setdefault('also', []).append(dk)
            continue
        by_term[str(c.get('t'))][c['id']] = rec
        n['cases'] += 1; n['counsel'] += len(rec.get('counsel', [])); n['argued'] += len(rec.get('argued', []))
    os.makedirs(OUT, exist_ok=True)
    for t, recs in by_term.items():
        open(f'{OUT}/{t}.js', 'w', encoding='utf-8').write('window.PARTIES=window.PARTIES||{};Object.assign(window.PARTIES,' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');')
    open('docs/data/parties-index.js', 'w', encoding='utf-8').write('window.PARTIES_INDEX=' + json.dumps(sorted(by_term), separators=(',', ':')) + ';')
    print(dict(n), 'terms', sorted(by_term))


if __name__ == '__main__':
    main()
