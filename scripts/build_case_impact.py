"""Build docs/data/case_impact.js: a citation-based impact measure for each Supreme Court case on the site.

Source: the Caselaw Access Project (Harvard Law School Library), fetched by cap_fetch.py.
  - pr:  the case's PageRank in CAP's citation graph of all American case law (federal and state courts). A case scores
         high when it is cited often, and especially when it is cited by cases that are themselves heavily cited.
  - pct: the PageRank percentile among all cases in that graph (0.9999 = top 0.01%).
  - n:   how many later Supreme Court opinions cite the case (from CAP's citation lists; decisions citing fewer than three
         cases, i.e. one-line orders, are not counted). This is the site's impact score and sort order.
CAP's data ends around 2020, so later decisions have no score yet.
Output: window.CASE_IMPACT = {src, c: {caseId: [pr (x1e9, integer), pct, n]}}
Run from the repo root after cap_fetch.py:  python scripts/build_case_impact.py
"""
import collections, json, re


def norm_cite(c):
    return re.sub(r'\s+', ' ', c.replace('U. S.', 'U.S.').replace('S. Ct.', 'S.Ct.').replace('S.Ct.', 'S. Ct.')).strip()


def main():
    cap = json.load(open('data/raw/cap/scotus_compact.json', encoding='utf-8'))
    by_cite, by_dk = {}, {}
    for c in cap:
        for ct in c['cites']:
            by_cite.setdefault(norm_cite(ct), c)
        m = re.search(r'(\d+[-–]\d+|\d+)', c.get('dk') or '')
        if m and c.get('date'):
            by_dk[(m.group(1).replace('–', '-'), c['date'][:4])] = c
    date_of = {c['id']: c.get('date') or '' for c in cap}
    cited_by = collections.Counter()
    for c in cap:
        if len(set(c['to'])) < 3:   # one-line orders (summary vacaturs, filing-restriction orders) are not opinions
            continue
        for t in set(c['to']):
            if t in date_of and date_of[t] <= (c.get('date') or ''):
                cited_by[t] += 1

    s = open('docs/data/scotus.js', encoding='utf-8').read()
    cases = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['cases']
    out, hit = {}, 0
    for c in cases:
        m = None
        if c.get('cit') and '___' not in c['cit']:
            m = by_cite.get(norm_cite(c['cit']))
        if not m and c.get('d') and c.get('dec'):
            m = by_dk.get((c['d'].strip(), c['dec'][:4]))
        if not m or m.get('pr') is None:
            continue
        hit += 1
        out[c['id']] = [round(m['pr'] * 1e9), round(m['pct'], 5), cited_by[m['id']]]
    data = {'src': 'Caselaw Access Project, Harvard Law School Library (citation PageRank across American case law)', 'c': out}
    open('docs/data/case_impact.js', 'w', encoding='utf-8').write('window.CASE_IMPACT=' + json.dumps(data, separators=(',', ':')) + ';')
    print(f'impact for {hit} of {len(cases)} cases')
    top = sorted(out.items(), key=lambda kv: -kv[1][0])[:15]
    names = {c['id']: c['n'] for c in cases}
    for k, v in top:
        print(f'  {names[k][:45]:45} pct {v[1]:.5f}  cited by {v[2]} later Supreme Court decisions')


if __name__ == '__main__':
    main()
