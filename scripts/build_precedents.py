"""Build docs/data/precedents/<year>.js: the Precedents panel of each case page, from the citation graph.

For every Supreme Court case on the site that the Caselaw Access Project (Harvard Law School Library) matches
(build_case_impact.match: citation, docket and year, or decision date and party name):
  c, cn  precedents relied on: Supreme Court cases on the site that the opinion cites (CAP's cites_to lists, which
         include cases cited only in a dissent), the top 8 ranked by relevance to this case (see relevance(): shared
         citations and shared citing decisions, a mild log of impact, shared area tags), and how many there are in all.
  b, bn  later cases citing this one: the most relevant of the later Supreme Court decisions that cite it (same score), and the total
         (decisions citing fewer than three cases, i.e. one-line orders, are left out, as in build_case_impact.py).
  r      related decisions: bibliographic coupling (sharing cited precedents) blended with co-citation (being cited
         together by later decisions), each normalised (cosine), with shared area tags as a tie-breaker. Cases already
         listed under c or b are left out. Precedents cited by more than 400 decisions add nothing to coupling and
         opinions citing more than 120 cases add nothing to co-citation (too common to say anything).
  ob, ov overruled by / overrules: Wikipedia's "List of overruled United States Supreme Court decisions" (cached by
         build_games.py in data/raw/games/overruled.json; facts, linked on the page), as [id or null, name, cite].
  pa     1 when the Supreme Court Database codes the decision as altering precedent (precedentAlteration) and the
         Wikipedia list names no overruled case for it.
Decisions after CAP's data ends (October 2019 on) get edges from CourtListener's search index where
courtlistener.py cites has cached it (data/raw/courtlistener/cites/search.json).

Output: window.PRECEDENTS (Object.assign per year file, loaded when a case page opens) and docs/data/precedents-index.js
(the years present).
Run from the repo root after cap_fetch.py and build_case_impact.py:  python scripts/build_precedents.py
"""
import collections, csv, glob, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_case_impact as bci  # noqa: E402

OUT = 'docs/data/precedents'
TOP, REL = 8, 6
COMMON_CITED, BIG_CITER = 400, 120


def load_js(path, key=None):
    s = open(path, encoding='utf-8').read()
    d = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    return d[key] if key else d


def name_key(n):
    m = re.match(r"^(?:The )?([A-Z][\w'.&-]*)[^v]*? v\. (?:The )?([A-Z][\w'.&-]*)", n or '')
    return (m.group(1) + '|' + m.group(2)).lower() if m else None


def overruled(cases, imp):
    """Pairs ((overruled id or None, name, cite), (overruling id or None, name, cite)) from the Wikipedia list, matched by
    U.S. Reports citation, else by the parties' first words (the most cited case of that name: Brown I, not Brown II)."""
    import build_games
    by_cit = {c['cit']: c['id'] for c in cases if c.get('cit')}
    by_key = {}
    for c in cases:
        k = name_key(c['n'])
        if k and c.get('dec') and (k not in by_key or (imp.get(c['id']) or [0, 0, -1])[2] > (imp.get(by_key[k]) or [0, 0, -1])[2]):
            by_key[k] = c['id']
    find = lambda name, cit: by_cit.get(cit) or by_key.get(name_key(re.sub(r"[‘’�]", "'", name)))
    pairs = []
    for (a, acit, _), (b, bcit, _) in build_games.overruled_pairs():
        a, b = (re.sub(r"''+", '', x).replace('�', '’').strip() for x in (a, b))
        if a and b:
            pairs.append(((find(a, acit), a, acit), (find(b, bcit), b, bcit)))
    return pairs


def scdb_alteration(cases):
    """Site ids of decisions the Supreme Court Database codes as altering precedent."""
    by_cit = {c['cit']: c['id'] for c in cases if c.get('cit')}
    ids = {c['id'] for c in cases}
    out = set()
    for f in glob.glob('data/raw/scdb/csv/*Citation.csv'):
        seen = set()
        for row in csv.DictReader(open(f, encoding='latin-1')):
            if row['caseId'] in seen:
                continue
            seen.add(row['caseId'])
            if row.get('precedentAlteration') != '1':
                continue
            cid = 'scdb/' + row['caseId'] if 'scdb/' + row['caseId'] in ids else by_cit.get(re.sub(r'\s+', ' ', row.get('usCite') or '').replace('U. S.', 'U.S.'))
            if cid:
                out.add(cid)
    return out


def courtlistener_edges(cases, ids_of_cap):
    """Edges among decisions since October 2019 from CourtListener's search index (site id -> set of cited site ids)."""
    path = 'data/raw/courtlistener/cites/search.json'
    if not os.path.exists(path):
        return {}
    rows = json.load(open(path, encoding='utf-8'))
    by_us, by_scdb, by_dk = {}, {}, {}
    for x in rows:
        for ct in x.get('cit') or []:
            if re.match(r'^\d+ U\.S\. \d+$', ct):
                by_us[ct] = x['id']
        if x.get('scdb'):
            by_scdb[x['scdb']] = x['id']
        by_dk.setdefault(((x.get('dk') or '').strip().lower(), x.get('date')), []).append(x['id'])
    site_of = {}
    for c in cases:
        cl = (by_scdb.get(c['id'][5:]) if c['id'].startswith('scdb/') else None) or by_us.get(c.get('cit') or '')
        if not cl:
            h = by_dk.get(((c.get('d') or '').strip().lower(), c.get('dec')), [])
            cl = h[0] if len(h) == 1 else None
        if cl:
            site_of[cl] = c['id']
    op_cluster = {o['id']: x['id'] for x in rows for o in x['ops']}
    out = {}
    for x in rows:
        src = site_of.get(x['id'])
        to = {site_of.get(op_cluster.get(t)) for o in x['ops'] for t in o['cites']} - {None, src}
        if src and to:
            out[src] = to
    return out


def main():
    cases = load_js('docs/data/scotus.js', 'cases')
    by_id = {c['id']: c for c in cases}
    imp = load_js('docs/data/case_impact.js', 'c')
    cap = bci.load_cap()
    m = bci.match(cases, cap)
    site_of = {}
    for cid, r in m.items():
        site_of.setdefault(r['id'], cid)
    date = {cid: by_id[cid].get('dec') or '' for cid in by_id}
    cites = {}   # site id -> set of site ids it cites
    for cid, r in m.items():
        to = {site_of.get(t) for t in set(r['to'])} - {None, cid}
        cites[cid] = {t for t in to if date[t] <= date[cid] or not date[t]}
    real = {cid for cid, r in m.items() if len(set(r['to'])) >= 3}   # one-line orders are not counted as citing
    ncl = 0
    for cid, to in courtlistener_edges(cases, site_of).items():
        new = {t for t in to if t not in cites.get(cid, set())}
        if new:
            cites.setdefault(cid, set()).update(new)
            real.add(cid) if len(to) >= 3 else None
            ncl += 1
    citers = collections.defaultdict(set)
    for cid, to in cites.items():
        if cid in real:
            for t in to:
                citers[t].add(cid)
    rank = lambda x: (-(imp.get(x) or [0, 0, 0])[2], -(imp.get(x) or [0])[0], date.get(x) or '')
    tags = {c['id']: set(c.get('tg') or []) for c in cases}

    def relevance(a, x):
        """How closely precedent (or citing decision) x belongs to case a's own subject: the two share cited precedents
        (bibliographic coupling) and are cited by the same later decisions (co-citation), each a cosine; scaled by a mild
        log of x's impact (so landmarks win ties, but foundational cases cited in passing do not lead) and by shared area
        tags. A precedent no later decision cites alongside a, and that shares nothing with it, keeps a small base."""
        ca, cx, ba, bx = cites.get(a, set()), cites.get(x, set()), citers.get(a, set()), citers.get(x, set())
        coup = len(ca & cx) / math.sqrt(len(ca) * len(cx)) if ca and cx else 0
        coc = len(ba & bx) / math.sqrt(len(ba) * len(bx)) if ba and bx else 0
        n = (imp.get(x) or [0, 0, 0])[2]
        shared = len(tags[a] & tags.get(x, set()))
        return (0.05 + coup + coc) * (1 + 0.15 * math.log1p(n)) * (1 + 0.5 * min(shared, 2))

    pairs = overruled(cases, imp)
    ob, ov = collections.defaultdict(list), collections.defaultdict(list)
    for (a_id, a, acit), (b_id, b, bcit) in pairs:
        if a_id:
            ob[a_id].append([b_id, b, bcit])
        if b_id:
            ov[b_id].append([a_id, a, acit])
    alt = scdb_alteration(cases)

    out = {}
    stats = collections.Counter()
    for c in cases:
        cid = c['id']
        rec = {}
        cs, bs = cites.get(cid, set()), citers.get(cid, set())
        if cs:
            rec['c'] = sorted(cs, key=lambda x: (-relevance(cid, x), rank(x)))[:TOP]
            rec['cn'] = len(cs)
            stats['c'] += 1
        if bs:
            rec['b'] = sorted(bs, key=lambda x: (-relevance(cid, x), rank(x)))[:TOP]
            rec['bn'] = len(bs)
            stats['b'] += 1
        # related: coupling + co-citation
        coup, cocit = collections.Counter(), collections.Counter()
        for p in cs:
            if len(citers.get(p, ())) <= COMMON_CITED:
                for x in citers.get(p, ()):
                    coup[x] += 1
        for d in bs:
            if len(cites.get(d, ())) <= BIG_CITER:
                for x in cites[d]:
                    cocit[x] += 1
        shown = set(rec.get('c', [])) | set(rec.get('b', [])) | {cid}
        score = {}
        for x in set(coup) | set(cocit):
            if x in shown or (coup[x] < 2 and cocit[x] < 2):
                continue
            s = 0.0
            if coup[x]:
                s += 0.5 * coup[x] / math.sqrt(len(cs) * max(1, len(cites.get(x, ()))))
            if cocit[x]:
                s += 0.5 * cocit[x] / math.sqrt(len(bs) * max(1, len(citers.get(x, ()))))
            s += 0.02 * len(tags[cid] & tags.get(x, set()))
            score[x] = s
        if score:
            rec['r'] = sorted(score, key=lambda x: (-score[x], rank(x)))[:REL]
            stats['r'] += 1
        if ob.get(cid):
            rec['ob'] = ob[cid]
            stats['ob'] += 1
        if ov.get(cid):
            rec['ov'] = ov[cid]
            stats['ov'] += 1
        elif cid in alt:
            rec['pa'] = 1
            stats['pa'] += 1
        if rec:
            out[cid] = rec
    by_dec = collections.defaultdict(dict)
    for cid, rec in out.items():
        by_dec[str(int(str(by_id[cid].get('y') or 0)[:4]))][cid] = rec
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(f'{OUT}/*.js'):
        os.remove(f)
    total = 0
    for d, recs in by_dec.items():
        s = 'window.PRECEDENTS=window.PRECEDENTS||{};Object.assign(window.PRECEDENTS,' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');'
        open(f'{OUT}/{d}.js', 'w', encoding='utf-8').write(s)
        total += len(s.encode('utf-8'))
    open('docs/data/precedents-index.js', 'w', encoding='utf-8').write('window.PRECEDENTS_INDEX=' + json.dumps(sorted(by_dec)) + ';')
    print(f'{len(m)} cases matched to CAP; {ncl} with CourtListener edges; {len(pairs)} overruled pairs in the Wikipedia list')
    print(f"relied on {stats['c']}, cited by {stats['b']}, related {stats['r']}, overruled by {stats['ob']}, overrules {stats['ov']}, "
          f"SCDB precedent alteration only {stats['pa']} of {len(cases)} cases")
    print(f'{len(by_dec)} year files, {total / 1e6:.1f} MB in all, largest {max(os.path.getsize(f) for f in glob.glob(OUT + "/*.js")) / 1e6:.2f} MB')


if __name__ == '__main__':
    main()
