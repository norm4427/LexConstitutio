"""Refine topics in docs/data/articles.js (mirrors the rules in build.ps1; run after build.ps1).

- Adds the subtopics "Jurisprudence & Legal Philosophy" and "Constitutionalism & Democratic Theory" (Theory &
  Interpretation) and "Taxation & Economic Regulation" (Structure & Powers), scored like build.ps1: title hits x3,
  keyword hits x2, abstract hits (up to 3) x1; an article needs a score of 2 or more.
- "General Theory & Doctrine" stays only on articles with no more specific topic. Its pattern matches phrases like
  "Constitutional Law" that open thousands of student-note titles, so it used to sit on most of the index.
"""
import json, re

NEW = [
    {'id': 'jurisprudence', 'name': 'Jurisprudence & Legal Philosophy', 'parent': 'theory', 'after': 'amendment',
     're': r'jurisprudential|philosophy of law|general jurisprudence|analytic jurisprudence|legal (philosophy|theory|positivism|realism|process)|natural (law|rights)|positivis|\bmorality\b|moral (theory|philosophy|reading)|philosoph|\bdworkin|\brawls|h\.\s?l\.\s?a\.\s?hart|liberalism|republicanism|political theory|theory of justice'},
    {'id': 'democratic', 'name': 'Constitutionalism & Democratic Theory', 'parent': 'theory', 'after': 'jurisprudence',
     're': r'democra(cy|tic theory|tic legitimacy)|legitimacy|constitutionalism|rule of law|popular sovereignty|self-government|consent of the governed|social contract|constitutional (culture|order|design|failure|crisis|crises|norms|hardball|rot)'},
    {'id': 'econreg', 'name': 'Taxation & Economic Regulation', 'parent': 'structure', 'after': 'federalism',
     're': r'\btax(es|ation|ing|payers?)?\b|income tax|public utilit|\butility rates?\b|\binsurance\b|\blicens(e|es|ing)\b|price (control|fixing|regulation)|minimum wage|\bwages?\b|labor (law|union|dispute|relations)|\bunions?\b|railroad|\bmonopol|antitrust|economic regulation|police power|business regulation|chain stores?|trading stamps|occupational'},
]


def main():
    path = 'docs/data/articles.js'
    s = open(path, encoding='utf-8').read()
    head = s[:s.index('=') + 1]
    d = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    topics = [t for t in d['topics'] if t['id'] not in {n['id'] for n in NEW}]
    for n in NEW:
        i = next((k for k, t in enumerate(topics) if t['id'] == n['after']), len(topics) - 1)
        topics.insert(i + 1, {'id': n['id'], 'name': n['name'], 'parent': n['parent']})
    d['topics'] = topics
    rx = {n['id']: re.compile(n['re'], re.I) for n in NEW}
    added = {k: 0 for k in rx}
    gen_before = sum('general' in (a.get('tp') or []) for a in d['articles'])
    for a in d['articles']:
        tp = [t for t in (a.get('tp') or []) if t not in rx]
        kw = ' '.join(a.get('kw') or [])
        for k, r in rx.items():
            score = 3 * len(r.findall(a.get('t') or '')) + 2 * len(r.findall(kw)) + min(3, len(r.findall(a.get('ab') or '')))
            if score >= 2:
                tp.append(k); added[k] += 1
        if 'general' in tp and len(tp) > 1:
            tp.remove('general')
        a['tp'] = tp or ['general']
    gen_after = sum('general' in a['tp'] for a in d['articles'])
    open(path, 'w', encoding='utf-8').write(head + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'added: {added}; "General Theory & Doctrine" {gen_before} -> {gen_after}')


if __name__ == '__main__':
    main()
