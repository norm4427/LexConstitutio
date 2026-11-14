"""Build docs/data/constitution.js: the annotated Constitution for the Originalist's Corner.

Text: National Archives transcriptions (public domain): data/raw/constitution/*.html.
For each named clause in clauses.py:
  overview    the lead of the clause's Wikipedia article (CC BY-SA 4.0), cached in data/raw/constitution/wiki.json
  commentary  the Constitution Annotated (Congressional Research Service, 2022 ed., public domain): the clause's overview
              essay in full, plus the titles and opening paragraphs of the essays tracing how doctrine developed
  cases       the Supreme Court Database's cases decided under the clause's provision codes (lawSupp), ranked by later
              Supreme Court citations (case_impact.js), top 10
  articles    law review articles whose title or keywords match the clause, or whose abstract names it, ranked by citations;
              5-15 shown, the full list in docs/data/clause-articles.js (the Articles page's clause filter)
  founding    passages from Story, Rawle, Tucker, Kent, The Federalist, Madison's notes, Blackstone (Originalist's Corner)
  statutes    early federal statutes from the Corner's Statutes at Large collection that touch the clause
Run from the repo root:  python scripts/build_constitution.py
"""
import collections, csv, glob, html, json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, 'scripts')
from clauses import C as CLAUSES

RAW = 'data/raw/constitution'
ROMAN = {v: i for i, v in enumerate('I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI XXII XXIII XXIV XXV XXVI XXVII'.split(), 1)}


def clip(text, n):
    """text cut to about n characters at the end of a sentence (never mid-word), with an ellipsis when something was cut;
    an <em>/<i> left open by the cut is closed."""
    if len(text) <= n:
        return text
    ends = [m.end() for m in re.finditer(r'(?<!\bv)(?<!\b[A-Z])(?<!\bNo)(?<!\bSt)(?<!\bMr)(?<!\bU\.S)(?<!\bId)(?<!\bJr)(?<!\bCo)(?<!\bArt)(?<!\bcl)'
                                         r'[.!?][”’"\')\]]?(?:</em>|</i>)?(?=\s+[“"(\[]?[A-Z<])', text[:n + 200])]
    good = [e for e in ends if e <= n] or ends[:1]
    out = text[:good[-1]] if good and good[-1] >= 0.4 * n else re.sub(r'\s+\S*$', '', text[:n])
    for tag in ('em', 'i'):
        out += f'</{tag}>' * max(0, out.count(f'<{tag}>') - out.count(f'</{tag}>'))
    return out.rstrip() + ('' if len(out) >= len(text) else ' …')


def load_js(name):
    s = open(f'docs/data/{name}.js', encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def clean(h):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', h))).strip()


def framer_name(href):
    """a signer's full name from the National Archives "Founding Fathers" page the transcription links to
    (/founding-docs/founding-fathers-new-jersey#livingston -> "William Livingston"), cached in data/raw/constitution/framers/."""
    m = re.match(r'/founding-docs/(founding-fathers-[a-z-]+)#(\w+)', href or '')
    if not m:
        return ''
    os.makedirs(f'{RAW}/framers', exist_ok=True)
    path = f'{RAW}/framers/{m.group(1)}.html'
    if not os.path.exists(path):
        time.sleep(1.5)
        req = urllib.request.Request('https://www.archives.gov/founding-docs/' + m.group(1), headers={'User-Agent': 'Mozilla/5.0 (LexConstitutio static site build)'})
        open(path, 'w', encoding='utf-8').write(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
    n = re.search(r'id="' + m.group(2) + r'"[^>]*>\s*</a>\s*([^,<]+)', open(path, encoding='utf-8').read())
    return clean(n.group(1)) if n else ''


def closing():
    """what follows Article VII in the engrossed Constitution: the note on interlineations, the attestation, the
    "done in Convention" passage and the signatures, grouped by state as in the National Archives transcription.
    Each signature is kept as written on the parchment ("Wil: Livingston", checked against Wikisource's transcription of
    the 1787 printing) with the signer's full name from the Archives' Founding Fathers pages."""
    s = open(f'{RAW}/constitution-transcript.html', encoding='utf-8').read()
    s = s[s.index('<h2 id="7">'):]
    s = s[:s.index('<h2>On This Page')] if '<h2>On This Page' in s else s
    ps = [p for p in re.findall(r'<p>(.*?)</p>', s, re.S)]
    # the clerk's note on interlined and erased words (a record of corrections to the parchment, not text of the
    # Constitution) is left out; the attestation and the "done in Convention" passage are kept
    notes = [clean(p) for p in ps[1:4] if not re.search(r"<a ", p) and "interlined" not in p]

    def person(chunk):
        href = re.search(r'href="([^"]+)"', chunk)
        sig = clean(chunk)
        full = framer_name(href.group(1)) if href else ''
        # add the full name only where the signature abbreviates it and the surnames agree (the Archives pages mix up
        # the two Pinckneys' anchors, so a fully written signature is never "corrected")
        sur = lambda x: re.sub(r'\s+(?:jun|Jr\.?)$', '', x).split()[-1].lower()
        abbreviated = re.search(r'[:.°]|\b(?:Hu|Abr|B|Gouv)\b|\bjun\b|\bJr\b', sig)
        bare = re.sub(r'\s+(?:jun|Jr\.?)$', '', sig)
        return {'sig': sig, 'full': full if full and abbreviated and sur(full) == sur(sig) and full not in (sig, bare) else ''}
    pres = next(p for p in ps if 'washington' in p)
    pres_sig, pres_role = re.split(r'<br\s*/?>', pres, maxsplit=1)
    signers = [{'state': '', 'names': [person(pres_sig)], 'role': clean(pres_role)}]
    for st, body in re.findall(r'<h3[^>]*>.*?<strong>([^<]+)</strong>.*?</h3>\s*<p>(.*?)</p>', s, re.S):
        signers.append({'state': clean(st), 'names': [person(n) for n in re.split(r'<br\s*/?>', body) if clean(n)]})
    return {'notes': notes, 'signers': signers}


def parse_text():
    units = []
    s = open(f'{RAW}/constitution-transcript.html', encoding='utf-8').read()
    s = s[s.index('<strong>We the People'):]
    s = s[:s.index('<h2>On This Page')] if '<h2>On This Page' in s else s
    pre = s[:s.index('</p>')]          # the preamble paragraph we started inside
    units.append({'id': 'pre', 'label': 'Preamble', 'group': 'Preamble', 'text': clean(pre)})
    s = s[s.index('</p>') + 4:]
    art = sec = None
    para = 0
    for m in re.finditer(r'<h2 id="(\d+)">Article\. ([IVX]+)\.</h2>|<h3 id="\d+-(\d+)">Section\. (\d+)\.</h3>|<p>(.*?)</p>', s, re.S):
        if m.group(1):
            art, sec, para = int(m.group(1)), None, 0
        elif m.group(3):
            sec, para = int(m.group(3)), 0
        elif art and m.group(5) is not None:
            if art == 7 and para >= 1:
                break               # after Article VII's one clause come the closing notes and signatures (closing())
            t = clean(m.group(5))
            if not t or len(t) < 8 or t.startswith('done in Convention'):
                continue
            para += 1
            uid = f'a{art}' + (f's{sec}' if sec else '') + f'c{para}'
            label = f'Article {"I II III IV V VI VII".split()[art - 1]}' + (f', Section {sec}' if sec else '') + f', Clause {para}'
            units.append({'id': uid, 'label': label, 'group': f'Article {"I II III IV V VI VII".split()[art - 1]}', 'text': t})
    # single-paragraph sections are also addressable without the clause number (a2s3, a4s4, a5 ...)
    counts = collections.Counter(re.sub(r'c\d+$', '', u['id']) for u in units if u['id'] != 'pre')
    for u in units:
        base = re.sub(r'c\d+$', '', u['id'])
        if u['id'] != 'pre' and counts[base] == 1:
            u['alias'] = base
    b = open(f'{RAW}/bill-of-rights-transcript.html', encoding='utf-8').read()
    for m in re.finditer(r'<h3>Amendment ([IVX]+)</h3>\s*<p>(.*?)</p>', b, re.S):
        n = ROMAN[m.group(1)]
        units.append({'id': f'am{n}', 'label': f'Amendment {m.group(1)}', 'group': 'Bill of Rights', 'text': clean(m.group(2))})
    a = open(f'{RAW}/amendments-11-27.html', encoding='utf-8').read()
    blocks = re.split(r'<h[23]>(?:<em>)?<a id="([xvi]+)" name="[^"]*"></a>(?:</em>)?AMENDMENT ([IVX]+)</h[23]>', a)
    for i in range(1, len(blocks) - 2, 3):
        rn, body = blocks[i + 1], blocks[i + 2]
        n = ROMAN[rn]
        body = body.split('<h2')[0]
        secs = re.split(r'<h3>(?:<em>)?<a id="[^"]*" name="[^"]*"></a>(?:</em>)?Section (\d+)\.</h3>', body)
        if len(secs) == 1:
            t = ' '.join(clean(p) for p in re.findall(r'<p>(.*?)</p>', body, re.S) if not re.search(r'class="smaller"|Note:', p))
            ps = [clean(p) for p in re.findall(r'<p(?: class="[^"]*")?>(.*?)</p>', body, re.S)]
            t = ' '.join(p for p in ps if p and not p.startswith(('Passed by Congress', 'Note:')) and not re.match(r'^\*', p))
            units.append({'id': f'am{n}', 'label': f'Amendment {rn}', 'group': 'Later amendments', 'text': t})
        else:
            for j in range(1, len(secs) - 1, 2):
                ps = [clean(p) for p in re.findall(r'<p>(.*?)</p>', secs[j + 1], re.S)]
                t = ' '.join(p for p in ps if p and not p.startswith(('Passed by Congress', 'Note:')))
                units.append({'id': f'am{n}s{secs[j]}', 'label': f'Amendment {rn}, Section {secs[j]}', 'group': 'Later amendments', 'text': t})
    for u in units:
        t = u['text']
        t = re.sub(r'\s*Back to Constitution Main Page.*$', '', t)                  # the page's navigation (after Amendment XXVII)
        t = re.sub(r'^Originally proposed .*?Ratified [^.]*\d{4}\.\s*', '', t)      # Amendment XXVII's dates, not its text
        t = re.sub(r'\s*\*(?:Changed|Superseded|Repealed) by [^.]*\.', '', t)        # the Archives' footnotes on superseded text
        u['text'] = t.replace('*', '').strip()                                        # ...and their markers
    return units


def conan_essays():
    """Constitution Annotated essays: id -> [title, [paragraphs]]. Prefers data/conan_essays.json (conan_extract.py, which keeps
    only body text by font size); falls back to parsing the GovInfo PDF text in data/raw/conan/g*.txt."""
    if os.path.exists('data/conan_essays.json'):
        return {e['id']: [e['title'], e['paras']] for e in json.load(open('data/conan_essays.json', encoding='utf-8'))}
    head = re.compile(r'^((?:Art[IVX]+|Amdt\d+|Pmbl|Intro)(?:\.[A-Z]*\d+)+)\s+([A-Z“"][^.]{2,160}?)\s*$')
    junk = re.compile(r'^(?:ARTICLE [IVX]+|AMENDMENT [IVX]+|PREAMBLE|\d{2,4}$|[A-Z][A-Z ,—–\-]{12,}$)|\.{6,}')
    ess, cur = {}, None
    files = sorted(glob.glob('data/raw/conan/g*.txt'), key=lambda f: int(re.search(r'g(\d+)', f).group(1)))
    for f in files:
        for line in open(f, encoding='utf-8', errors='replace'):
            line = line.strip()
            if not line:
                continue
            m = head.match(line)
            if m and '....' not in line:
                cur = m.group(1)
                ess.setdefault(cur, [m.group(2).strip(), []])
                continue
            if cur is None or junk.search(line) or re.match(r'^\d+ ', line) or len(line.split()) < 12:
                continue
            line = re.sub(r'([a-z.,;:”’)])\d{1,3}(?=[\s,.;:]|$)', r'\1', line)    # footnote markers
            if re.match(r'^(Article|Amendment) [IVX]+(, Section \d+)?(, Clause \d+)?:', line):
                continue
            ess[cur][1].append(line)
    return ess


def wiki_extracts(titles):
    path = f'{RAW}/wiki.json'
    have = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    todo = [t for t in titles if t not in have]
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1,
              'exlimit': 20, 'inprop': 'url', 'redirects': 1, 'format': 'json', 'formatversion': 2, 'titles': '|'.join(batch)})
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0 (static site build script)'}), timeout=60))
        q = d.get('query', {})
        alias = {x['from']: x['to'] for k in ('normalized', 'redirects') for x in q.get(k, [])}
        pages = {p['title']: p for p in q.get('pages', [])}
        for t in batch:
            f = t
            for _ in range(3):
                f = alias.get(f, f)
            p = pages.get(f, {})
            have[t] = {'title': f, 'text': p.get('extract'), 'url': p.get('fullurl')}
        json.dump(have, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(1)
    return have


def scdb_cases():
    """lawSupp code -> set of site case ids."""
    s = load_js('scotus')['cases']
    by_cite = {c['cit']: c['id'] for c in s if c.get('cit')}
    by_dk = {(str(c['t']), (c.get('d') or '').lower()): c['id'] for c in s}
    out = collections.defaultdict(set)
    for f in ('data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv',
              'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Docket.csv'):
        for r in csv.DictReader(open(f, encoding='latin-1')):
            code = r['lawSupp']
            if not code.isdigit():
                continue
            cid = by_cite.get(r['usCite'].strip()) or by_cite.get(r['sctCite'].strip()) or by_dk.get((r['term'], r['docket'].replace('â\u0080\u0093', '-').strip().lower()))
            if cid:
                out[int(code)].add(cid)
    return out


def main():
    units = parse_text()
    uid = {u['id']: u for u in units}
    for u in units:
        if u.get('alias'):
            uid.setdefault(u['alias'], u)
    ess = conan_essays()
    wiki = wiki_extracts([c['wiki'] for c in CLAUSES])
    codes = scdb_cases()
    impact = load_js('case_impact')['c']
    sc = load_js('scotus')['cases']
    case_text = {c['id']: ' '.join(str(c.get(k) or '') for k in ('n', 'q', 'ds', 'h')) for c in sc}
    con = {c['id']: c.get('con') for c in sc}
    arts = load_js('articles')['articles']
    clause_arts = {}
    corner = load_js('corner')
    passages = corner['passages']
    out = []
    missing = []
    for c in CLAUSES:
        u = uid.get(c['unit']) or uid.get(c['unit'] + 's1')   # an amendment with sections: its first section
        if not u:
            missing.append(c['id']); continue
        rec = {'id': c['id'], 'name': c['name'], 'unit': u['id'], 'loc': u['label']}
        m = re.search(c['hl'], u['text'])
        rec['hl'] = (m.group(0) if m and c['hl'] != '.*' else u['text']).strip()
        w = wiki.get(c['wiki']) or {}
        if w.get('text'):
            # (a paragraph that led into a list Wikipedia's summary dropped ends in a comma or colon: left out)
            paras = [p.strip() for p in w['text'].split('\n') if len(p.strip()) > 60 and not re.search(r'[,:;]$', p.strip())][:4]
            rec['wiki'] = {'title': w['title'], 'url': w['url'], 'paras': paras}
        # Constitution Annotated
        ids = [k for k in ess if any(k == p or k.startswith(p + '.') for p in c['conan'])]
        if ids:
            ov = next((k for k in ids if ess[k][0].lower().startswith('overview') and ess[k][1]), None) or next((k for k in ids if ess[k][1]), None)
            dev = []
            for k in ids:
                if k == ov or not ess[k][1] or ess[k][0].lower().startswith('overview'):
                    continue
                dev.append({'id': k, 'title': re.sub(r'\s+[A-Z][a-z]+ Amendment:$|\s+(Article|Amendment) [IVX]+.*$', '', ess[k][0]), 'p': clip(ess[k][1][0], 2500)})
            if len(dev) > 16:   # sample the history evenly so later doctrine is not cut off
                dev = [dev[round(i * (len(dev) - 1) / 15)] for i in range(16)]
            rec['conan'] = {'overview': {'id': ov, 'title': ess[ov][0], 'paras': ess[ov][1][:6]} if ov else None, 'dev': dev}
        # cases, by later Supreme Court citations
        cs = set()
        for code in c['scdb']:
            cs |= codes.get(code, set())
        if c.get('cf'):   # provision code shared with another clause (press/speech): keep matching cases
            cf = re.compile(c['cf'], re.I)
            cs = {i for i in cs if cf.search(case_text.get(i, ''))}
        if len(cs) < 3:   # no or few coded cases: constitutional cases whose summary names the clause
            rx = re.compile(c.get('cr') or c['art'], re.I)
            cs |= {i for i, t in case_text.items() if con.get(i) and rx.search(t)}
        rec['cases'] = sorted(cs, key=lambda i: -(impact.get(i) or [0, 0, -1])[2])[:10]
        rec['nCases'] = len(cs)
        # articles
        # an article is about the clause when its title or subject keywords match the clause's pattern, or its abstract
        # names the clause outright ("the Takings Clause", "the Second Amendment")
        rx = re.compile(c['art'], re.I)
        name_rx = re.compile(r'\b' + re.escape(re.sub(r'\s*\(.*\)$', '', c['name'])) + r'\b', re.I)
        hits = [a for a in arts if not a.get('rv') and (rx.search(a['t']) or rx.search(' '.join(a.get('kw') or []))
                                                        or (len(c['name']) > 8 and name_rx.search(a.get('ab') or '')))]
        clause_arts[c['id']] = [a['id'] for a in sorted(hits, key=lambda a: -(a.get('c') or 0))]
        n = max(5, min(15, round(len(hits) ** 0.5))) if hits else 0
        rec['articles'] = [a['id'] for a in sorted(hits, key=lambda a: -(a.get('c') or 0))[:n]]
        rec['nArticles'] = len(hits)
        # founding-era passages and statutes from the Corner
        kw = re.compile(c['kw'], re.I)
        found, stat, seen = [], [], set()
        for topic in c['corner']:
            for src, pids in (corner['index'].get(topic) or {}).items():
                for pid in pids:
                    p = passages.get(pid)
                    if not p or pid in seen or not kw.search(p['t']):
                        continue
                    seen.add(pid)
                    (stat if src == 'statutes' else found).append({'id': pid, 's': src, 'loc': p.get('loc'), 't': clip(p['t'], 1100)})
        order = ['story', 'rawle', 'tucker', 'federalist', 'madison', 'kent', 'cooley', 'antifederalist', 'blackstone', 'documents', 'vattel', 'locke']
        found.sort(key=lambda p: (order.index(p['s']) if p['s'] in order else 99, -len(kw.findall(p['t']))))
        per = collections.Counter()
        keep = []
        for p in found:
            if per[p['s']] < 2:
                keep.append(p); per[p['s']] += 1
        rec['founding'] = keep[:10]
        rec['statutes'] = stat[:5]
        out.append(rec)
    data = {'src': 'Text: National Archives. Commentary: Constitution Annotated (CRS, public domain); overviews: Wikipedia (CC BY-SA 4.0).',
            'units': units, 'closing': closing(), 'clauses': out}
    open('docs/data/constitution.js', 'w', encoding='utf-8').write('window.CONSTITUTION=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    # every article tagged with the clauses it concerns, for the Articles page's clause filter ("See all" in the panel)
    names = {c['id']: c['name'] for c in CLAUSES if clause_arts.get(c['id'])}
    open('docs/data/clause-articles.js', 'w', encoding='utf-8').write('window.CLAUSE_ARTS=' + json.dumps({'names': names, 'ids': {k: v for k, v in clause_arts.items() if v}}, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f"clause tags: {sum(len(v) for v in clause_arts.values())} on {len({i for v in clause_arts.values() for i in v})} articles")
    print(f'{len(units)} text units; {len(out)} clauses; missing units: {missing}')
    print('no Constitution Annotated:', [r['id'] for r in out if not r.get('conan') or not r['conan'].get('overview')])
    print('no Wikipedia:', [r['id'] for r in out if not r.get('wiki')])
    print('cases per clause:', {r['id']: r['nCases'] for r in out})
    print(f"size {os.path.getsize('docs/data/constitution.js') / 1024:.0f} KB")


if __name__ == '__main__':
    main()
