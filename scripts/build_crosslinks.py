"""Two-way links between law review articles and Supreme Court cases, precomputed for the article and case pages.

1. Articles naming cases (title > abstract > keywords): U.S. Reports citations ("410 U.S. 113"), docket numbers
   ("No. 19-1392"), full case names (both parties' first words, the way citedCases in app.js reads them; when several
   cases share the name, the one decided before the article, in its area, most cited) and, for landmark cases, the
   one-word short form ("after Dobbs"). Short forms keep app.js's safeguards (only names unique among the essential and
   most cited cases; not in the article's author list; not after "Justice", "Judge" or "Professor"; not followed by
   " v.") and add two: the case was decided before the article was published, and it shares an area with the article
   (or is on the essential list). Each link is scored by where it was found: title 3, abstract 2, keywords 1, plus 1
   for a citation or docket number.
2. The Supreme Court citing articles: law review citations ("88 Harv. L. Rev. 1", "Yale L. J.") in the opinion texts
   cached by cap_text_fetch.py (Caselaw Access Project, U.S. Reports vols 150-572 and S. Ct. 134-140), read with each
   journal's Bluebook abbreviation and its older names, matched to an indexed article by journal + volume + first page,
   or, where the index has no first page, by journal + volume and the article's title in the words before the citation.
   Each citation keeps the kind of opinion it sits in (majority, concurrence, dissent).
3. Articles citing articles: journal + volume + page citations in abstracts and keywords (rare; same matcher).

Output (loaded on demand): docs/data/xl/case/<year>.js -> window.XL_CASE[caseId] = {a: [[articleId, score], ...] strongest
first, ct: [[articleId, opinion type], ...]}; docs/data/xl/art/<journal>.js -> window.XL_ART[articleId] = {c: [[caseId,
score], ...], cb: [[caseId, opinion type], ...], aa: [articleId, ...]}; docs/data/xl-index.js lists the files.
Run from the repo root after cap_text_fetch.py:  python scripts/build_crosslinks.py
"""
import collections, glob, gzip, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_case_impact as bci  # noqa: E402

OUT = 'docs/data/xl'

# Bluebook abbreviations (and older titles), keyed with spaces, periods and ampersands removed, lower case
ABBR = {
    'harvlrev': 'hlr', 'yalelj': 'ylj', 'columlrev': 'colr', 'collrev': 'colr', 'michlrev': 'mlr_mich', 'uchilrev': 'uclrev',
    'cornelllrev': 'clr', 'cornelllq': 'clr', 'dukelj': 'dlj', 'notredamelrev': 'ndlr', 'notredamelaw': 'ndlr', 'notredamelawyer': 'ndlr',
    'vandlrev': 'vlr', 'minnlrev': 'mlr_minn', 'fordhamlrev': 'flr', 'nwulrev': 'nulr', 'nwunivlrev': 'nulr', 'illlrev': 'nulr',
    'emorylj': 'elj', 'wmmarylrev': 'wmlr', 'washleelrev': 'wlulr', 'byulrev': 'byulr', 'brighamyoungulrev': 'byulr',
    'constcomment': 'concomm', 'hastingsconstlq': 'hclq', 'wmmarybillrtsj': 'wmborj', 'nyulrev': 'nyulr', 'nyulqrev': 'nyulr',
    'texlrev': 'tlr', 'uclalrev': 'uclalr', 'valrev': 'valr', 'califlrev': 'calr', 'callrev': 'calr', 'upalrev': 'pennlr',
    'stanlrev': 'slr', 'geolj': 'glj', 'dukejconstlpubpoly': 'djclpp', 'nclrev': 'nclr', 'flalrev': 'uflr', 'galrev': 'galr',
    'cardozolrev': 'cardlr', 'pepplrev': 'pepplr', 'ucololrev': 'colr_cu', 'cololrev': 'colr_cu', 'umiamilrev': 'umialr',
    'marqlrev': 'marqlr', 'uilllrev': 'illlr', 'uilllf': 'illlr', 'supctrev': 'scr', 'harvjlpubpoly': 'hjlpp', 'washlrev': 'uwlr',
    'utahlrev': 'utahlr', 'smulrev': 'smulr', 'swlj': 'smulr', 'lawcontempprobs': 'lcp', 'jcrimlcriminology': 'jclc',
    'jcrimlc': 'jclc', 'jcriml': 'jclc', 'jcrimlcriminologypolicesci': 'jclc', 'jcrimlcrim': 'jclc',
}
CITE = re.compile(r"\b(\d{1,3}) ((?:[A-Z][A-Za-z'&]*\.?|&)(?:\s?(?:[A-Z][A-Za-z'&]*\.?|&|of)){0,7}) (\d{1,4})\b")
STOPW = set('the and for with from that this into upon what when after over under about between against their there which its are was were has have'.split())
WORD = re.compile(r"[a-z]{4,}")


def load_js(path, key=None):
    s = open(path, encoding='utf-8').read()
    d = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    return d[key] if key else d


def year(x):
    try:
        return int(str(x.get('y') or 0)[:4])
    except ValueError:
        return 0


def lr_cites(text):
    """(journal id, volume, page, start offset) for each law review citation of an indexed journal in a text."""
    for m in CITE.finditer(text):
        k = re.sub(r"[\s.&']", '', m.group(2)).lower()
        j = ABBR.get(k)
        if j:
            yield j, int(m.group(1)), int(m.group(3)), m.start()


class ArticleMatcher:
    def __init__(self, arts):
        self.by_jv = collections.defaultdict(list)
        for a in arts:
            if a.get('v') and str(a['v']).isdigit():
                self.by_jv[(a['j'], int(a['v']))].append(a)

    def find(self, j, v, page, context, before_year):
        cands = [a for a in self.by_jv.get((j, v), []) if not before_year or year(a) <= before_year]
        hit = [a for a in cands if str(a.get('fp') or '') == str(page)]
        if len(hit) == 1:
            return hit[0]
        if hit:
            cands = hit
        ctx = set(WORD.findall(context.lower()))
        best, bs = None, 0
        for a in cands:
            if a.get('fp') and not hit:   # its first page is known and differs: not this article
                continue
            w = [x for x in WORD.findall(a['t'].lower()) if x not in STOPW]
            if len(w) < 2:
                continue
            s = sum(x in ctx for x in w) / len(w)
            if s >= 0.75 and s > bs:
                best, bs = a, s
        return best


def name_index(cases, imp):
    """'first|second' (each party's first word) -> cases with that short name."""
    idx = collections.defaultdict(list)
    for c in cases:
        m = re.match(r"^(?:The )?([A-Z][\w'.&-]*)[^v]*? v\. (?:The )?([A-Z][\w'.&-]*)", c['n'])
        if m and c.get('dec'):
            idx[(m.group(1) + '|' + m.group(2)).lower()].append(c)
    return idx


NAMES = set('John Paul Jack Felix Aaron Dean Madison Bush Douglas Stevens Reagan Monroe Cleveland Webster Lawrence Morrison Robinson '
            'Philadelphia Puerto Atlantic Americans Christian Catholic Roman Wade Terry Brady Hall Holder Little Field Stop Joint Western Northern '
            'Railway Financial Parents Planned Good Home Agency Citizens Trade Standard Employment Powers Commonwealth District Thompson Lincoln '
            'Jefferson Hamilton Franklin Kennedy Nixon Clinton Obama Trump Biden Carter Ford Johnson Roosevelt Truman Eisenhower Wilson Taft Grant '
            'Marshall Story Holmes Brandeis Cardozo Frankfurter Black Warren Burger Rehnquist Roberts Scalia Thomas Ginsburg Breyer Souter Kennedy '
            'Alito Kagan Sotomayor Gorsuch Kavanaugh Barrett Brennan Blackmun Powell Stewart White Harlan Taney Chase Waite Fuller Hughes Stone '
            'Vinson Jackson Murphy Rutledge Burton Reed Clark Minton Whittaker Goldberg Fortas Gray Brewer Brown Shiras Peckham McKenna Day Moody '
            'Lurton Pitney McReynolds Clarke Sutherland Butler Sanford Roberts Byrnes Miller Bradley Strong Hunt Matthews Blatchford Lamar '
            'Mexico Texas Florida Puerto Indian Indians Chinese Japanese German Irish Christian Muslim Jewish Mormon Amish Catholic Protestant '
            'National International Federal Democratic Republican Union Southern Eastern Central Pacific American English British Great '
            'Mary Anne Ann James Joseph Thomas William Robert Richard Charles George Henry Edward Frank Walter Arthur Harry Martin Michael David '
            'Madrid Hans Hammer Marsh Pierce Quinn Randolph Reno Sims Frye Buck Dole Cohen Carr Glover Harper Kahn Fletcher Woodward Abrams'.split())


def landmark_short(cases, imp, ess, arts):
    """One-word short forms of landmark cases ("after Dobbs"), with safeguards against common words and names."""
    STOP = set('United States State Board City County Department Commission New People Bank Company Corporation Ex Parte Re In The Town '
               'School Village Trustees Railroad Pennsylvania Virginia California Texas Ohio Florida Michigan Illinois Washington Georgia '
               'Alabama Arizona Louisiana Mississippi Missouri Tennessee Kentucky Maryland Massachusetts Minnesota Wisconsin Oregon Colorado '
               'Oklahoma Kansas Nebraska Iowa Indiana Carolina Jersey York Connecticut Nevada Utah Idaho Montana Wyoming Dakota Alaska Hawaii '
               'Maine Vermont Hampshire Delaware Arkansas Chicago Boston Baltimore Detroit Cedar Santa Florence Montgomery Comptroller Textile '
               'Smith Johnson Jones Williams Miller Davis Wilson Taylor Moore White Thomas Jackson Harris Martin Clark Lewis Allen Young King '
               'Wright Hill Green Baker Adams Nelson Carter Mitchell Roberts Turner Phillips Campbell Parker Evans Edwards Collins Stewart '
               'Morris Rogers Reed Cook Morgan Bell Murphy Bailey Cooper Richardson Cox Howard Ward Peterson Gray Ramirez James Watson Brooks '
               'Kelly Sanders Price Bennett Wood Barnes Ross Henderson Coleman Jenkins Perry Powell Long Patterson Hughes Flores Butler '
               'Simmons Foster Gonzales Bryant Alexander Russell Griffin Hayes Myers Ford Hamilton Graham Sullivan Wallace West Cole Jordan '
               'Reynolds Marshall Owens Fisher Ellis Harrison Gibson Kennedy Wells Warren Grant Hunt Stone Garcia Martinez Rodriguez Torres '
               'Lopez Gonzalez Hernandez Anderson Walker Lynch Reid Riley Stanley Craig Chapman Lambert Shaw Townsend Norris Pena Mendoza '
               'Jacobs Carroll Bartlett Bowen Bowman Benton Collins Gore Snyder Pearson Manuel Garrison Mallory Ramos Salinas Haaland '
               'Free First Second Third Common General Public'.split()) | NAMES
    texts = [(a.get('t') or '') + ' . ' + (a.get('ab') or '') + ' . ' + '; '.join(a.get('kw') or []) for a in arts]
    lower = collections.Counter(w for t in texts for w in set(re.findall(r'\b[a-z]{4,}\b', t)))
    big = '\n'.join(texts)
    top = sorted([c for c in cases if ' v. ' in c['n'] and (c['id'] in ess or c['id'] in imp)],
                 key=lambda c: (c['id'] not in ess, -(imp.get(c['id']) or [0, 0, 0])[2]))[:len(ess) + 300]
    by_word = collections.defaultdict(list)
    for c in top:
        parts = [re.sub(r'^(?:The|In re|Ex parte)\s+', '', x) for x in re.sub(r'\s*\(\d\)$', '', c['n']).split(' v. ')]
        p = [(re.match(r"^([A-Z][a-z’']+)", x) or [None, None])[1] for x in parts]
        ok = lambda w: w and (len(w) >= 4 or w == 'Roe') and w not in STOP and lower[w.lower()] <= 10
        w = p[0] if ok(p[0]) else (p[1] if len(p) > 1 and ok(p[1]) and len(parts[1].split()) <= 2 else None)
        if not w:
            continue
        # the case is discussed in this corpus under its full name ("Dobbs v. Jackson", "District of Columbia v. Heller")
        k1, k2 = p[0] or '', p[1] if len(p) > 1 and p[1] else ''
        if len(re.findall(re.escape(k1) + r"[^.;\n]{0,60}? v\. (?:The )?" + re.escape(k2), big)) < 2:
            continue
        by_word[w].append(c)
    out = {}
    n = lambda c: (imp.get(c['id']) or [0, 0, 0])[2]
    for w, cs in by_word.items():
        cs.sort(key=n, reverse=True)
        if len(cs) == 1 or n(cs[0]) >= 3 * max(1, n(cs[1])):
            out[w] = cs[0]
    rx = re.compile(r"(?<!Justice )(?<!Judge )(?<!Professor )(?<!President )\b(" + '|'.join(sorted(map(re.escape, out), key=len, reverse=True)) + r")(?![\w’'-]| v\.)")
    return rx, out


def main():
    cases = load_js('docs/data/scotus.js', 'cases')
    by_id = {c['id']: c for c in cases}
    imp = load_js('docs/data/case_impact.js', 'c')
    ess = set(load_js('docs/data/essential.js'))
    D = load_js('docs/data/articles.js')
    arts = D['articles']
    art_by_id = {a['id']: a for a in arts}
    by_cit = {c['cit']: c for c in cases if c.get('cit')}
    by_dk = collections.defaultdict(list)
    for c in cases:
        if c.get('d'):
            by_dk[c['d'].strip()].append(c)
    nidx = name_index(cases, imp)
    short_rx, shorts = landmark_short(cases, imp, ess, arts)
    n_of = lambda cid: (imp.get(cid) or [0, 0, 0])[2]

    # ---- 1. articles naming cases
    a2c = {}
    for a in arts:
        ay, atp, authors = year(a) or 9999, set(a.get('tp') or []), ' '.join(a.get('a') or [])
        found = collections.Counter()
        for text, w in ((a.get('t') or '', 3), (a.get('ab') or '', 2), ('; '.join(a.get('kw') or []), 1)):
            if not text:
                continue
            hits = {}
            for m in re.finditer(r'\b(\d{1,3}) U\.\s?S\. (\d{1,4})\b', text):
                c = by_cit.get(f'{m.group(1)} U.S. {m.group(2)}')
                if c:
                    hits[c['id']] = max(hits.get(c['id'], 0), w + 1)
            for m in re.finditer(r'\bNo\. (\d{1,2}-\d{1,5})\b', text):
                cs = [c for c in by_dk.get(m.group(1), []) if year(c) <= ay]
                if len(cs) == 1:
                    hits[cs[0]['id']] = max(hits.get(cs[0]['id'], 0), w + 1)
            for m in re.finditer(r"(?:^|[^A-Za-z])([A-Z][\w'.&-]*)(?: [A-Z][\w'.&-]*){0,4} v\. (?:The )?([A-Z][\w'.&-]*)", text):
                cs = nidx.get((m.group(1) + '|' + m.group(2)).lower(), [])
                cs = [c for c in cs if year(c) <= ay] or []
                if not cs:
                    continue
                c = max(cs, key=lambda c: (bool(atp & set(c.get('tg') or [])), c['id'] in ess, n_of(c['id'])))
                hits[c['id']] = max(hits.get(c['id'], 0), w)
            for m in short_rx.finditer(text):
                c = shorts[m.group(1)]
                if c['id'] in hits or year(c) > ay or m.group(1) in authors:
                    continue
                if c['id'] in ess or atp & set(c.get('tg') or []):
                    hits[c['id']] = max(hits.get(c['id'], 0), w)
            for cid, s in hits.items():
                found[cid] += s
        if found:
            a2c[a['id']] = found

    # ---- 2. the Court citing articles (opinion texts)
    am = ArticleMatcher(arts)
    capm = bci.match(cases, bci.load_cap())
    site_of = {}
    for cid, r in capm.items():
        site_of.setdefault(r['id'], cid)
    court = collections.defaultdict(dict)   # caseId -> {articleId: opinion type}
    nvol = 0
    for f in sorted(glob.glob('data/raw/cap/text/*.json.gz')):
        nvol += 1
        for x in json.load(gzip.open(f, 'rt', encoding='utf-8')):
            cid = site_of.get(x['id']) or (by_cit.get(re.sub(r'\s+', ' ', x.get('cite') or '').replace('U. S.', 'U.S.')) or {}).get('id')
            if not cid:
                continue
            cy = year(by_id[cid]) or 9999
            for o in x['ops']:
                t = o['text']
                kind = {'majority': 'majority', 'concurrence': 'concurrence', 'dissent': 'dissent'}.get(o['type'], 'separate')
                if o['type'] == 'majority' and len(x['ops']) == 1:
                    kind = 'opinion'   # one text holds every opinion (older volumes): the split is unknown
                for j, v, p, at in lr_cites(t):
                    a = am.find(j, v, p, t[max(0, at - 320):at], cy)
                    if a:
                        prev = court[cid].get(a['id'])
                        if prev in (None, 'opinion', 'separate') or (prev != 'majority' and kind == 'majority'):
                            court[cid][a['id']] = kind

    # ---- 3. articles citing articles (abstracts and keywords)
    a2a = collections.defaultdict(set)
    for a in arts:
        text = (a.get('ab') or '') + ' ; ' + '; '.join(a.get('kw') or [])
        for j, v, p, at in lr_cites(text):
            b = am.find(j, v, p, text[max(0, at - 320):at], year(a) or 9999)
            if b and b['id'] != a['id']:
                a2a[a['id']].add(b['id'])

    # ---- write
    xc, xa = collections.defaultdict(dict), collections.defaultdict(dict)
    for aid, found in a2c.items():
        for cid, s in found.items():
            xc[cid].setdefault('a', []).append([aid, s])
        xa[aid]['c'] = sorted(([cid, s] for cid, s in found.items()), key=lambda r: (-r[1], -n_of(r[0])))
    for cid, d in court.items():
        xc[cid]['ct'] = sorted(([aid, k] for aid, k in d.items()), key=lambda r: (['majority', 'opinion', 'concurrence', 'separate', 'dissent'].index(r[1]), -(art_by_id[r[0]].get('c') or 0)))
        for aid, k in d.items():
            xa[aid].setdefault('cb', []).append([cid, k])
    for aid, bs in a2a.items():
        xa[aid]['aa'] = sorted(bs)
    for cid, d in xc.items():
        if 'a' in d:
            d['a'].sort(key=lambda r: (-r[1], -(art_by_id[r[0]].get('c') or 0)))
    for aid, d in xa.items():
        if 'cb' in d:
            d['cb'].sort(key=lambda r: by_id[r[0]].get('dec') or '')
    os.makedirs(f'{OUT}/case', exist_ok=True)
    os.makedirs(f'{OUT}/art', exist_ok=True)
    for f in glob.glob(f'{OUT}/*/*.js'):
        os.remove(f)
    files = {'case': collections.defaultdict(dict), 'art': collections.defaultdict(dict)}
    for cid, d in xc.items():
        files['case'][str(year(by_id[cid]))][cid] = d
    for aid, d in xa.items():
        files['art'][art_by_id[aid]['j']][aid] = d
    size = {}
    for kind, var in (('case', 'XL_CASE'), ('art', 'XL_ART')):
        for k, recs in files[kind].items():
            s = f'window.{var}=window.{var}||{{}};Object.assign(window.{var},' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');'
            open(f'{OUT}/{kind}/{k}.js', 'w', encoding='utf-8').write(s)
            size[f'{kind}/{k}'] = len(s.encode('utf-8'))
    open('docs/data/xl-index.js', 'w', encoding='utf-8').write('window.XL_INDEX=' + json.dumps({k: sorted(v) for k, v in files.items()}) + ';')

    # ---- report
    def before():
        """The old client-side matching, for comparison: case pages took articles whose title or abstract holds the full
        case name; article pages took U.S. citations, both-party names and unique landmark short names (no year or area check)."""
        case_side = 0
        low = [((a.get('t') or '') + ' ' + (a.get('ab') or '')).lower() for a in arts]
        names = collections.defaultdict(list)
        for c in cases:
            n = re.sub(r'\s*\(\d\)$', '', c['n']).lower()
            if len(n) >= 10:
                names[n].append(c['id'])
        joined = '\n'.join(low)
        for n in names:
            if n in joined:
                case_side += len(names[n])
        return case_side
    print(f'{nvol} opinion-text volumes read')
    print(f'cases with linked articles: {sum(1 for d in xc.values() if d.get("a"))}  (old full-name substring rule: {before()})')
    print(f'articles naming cases: {len(a2c)} of {len(arts)}')
    print(f'Court-cited articles: {len({a for d in court.values() for a in d})} cited in {len(court)} cases; '
          f'{sum(len(d) for d in court.values())} case-article citations; by opinion: {dict(collections.Counter(k for d in court.values() for k in d.values()))}')
    print(f'articles citing indexed articles: {len(a2a)}')
    print(f'{len(size)} files, {sum(size.values()) / 1e6:.2f} MB, largest {max(size.values()) / 1e3:.0f} KB ({max(size, key=size.get)})')
    if '--sample' in sys.argv:
        random.seed(7)
        links = [(aid, cid, s) for aid, f in a2c.items() for cid, s in f.items()]
        for aid, cid, s in random.sample(links, 20):
            a, c = art_by_id[aid], by_id[cid]
            print(f'  [{s}] {c["n"][:40]} ({c.get("y")}) <- {a["t"][:90]} ({a.get("y")})')
        cl = [(cid, aid, k) for cid, d in court.items() for aid, k in d.items()]
        for cid, aid, k in random.sample(cl, min(10, len(cl))):
            a, c = art_by_id[aid], by_id[cid]
            print(f'  COURT {c["n"][:36]} ({c.get("y")}, {k}) -> {a["t"][:70]} ({a["j"]} {a.get("v")}, {a.get("y")})')


if __name__ == '__main__':
    main()
