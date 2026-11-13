"""Fetch pronunciation sources for the narration lexicon (cached in data/raw/pron/).

1. Wikipedia articles for every case named in the narrated text (guide, advanced, commentary).
2. The Wikipedia pages of people those case articles link to whose name contains a party's name
   (e.g. "Lujan v. Defenders of Wildlife" links Manuel Lujan Jr., whose page gives /luːˈhɑːn/).
3. Every Supreme Court justice's page.
4. Wiktionary entries for legal Latin and other terms of art.
Run from the repo root:  python scripts/pronounce_fetch.py   then   python scripts/pronounce_build.py
"""
import json, os, re, time, urllib.parse, urllib.request

OUT = 'data/raw/pron'
UA = {'User-Agent': 'LexConstitutio-pronunciation-builder/1.0 (static site build script)'}
TERMS = ['certiorari', 'habeas corpus', 'mens rea', 'stare decisis', 'amicus curiae', 'per curiam', 'obiter dictum', 'dicta', 'sua sponte',
         'de novo', 'ex post facto', 'voir dire', 'res judicata', 'qui tam', 'quo warranto', 'mandamus', 'bona fide', 'certiorari', 'en banc',
         'pro se', 'in forma pauperis', 'ultra vires', 'parens patriae', 'amici', 'amicus', 'laches', 'subpoena', 'lex', 'nexus', 'ratio decidendi',
         'sui generis', 'inter alia', 'prima facie', 'de jure', 'de facto', 'bill of attainder', 'corpus', 'certworthy', 'imprimatur', 'carte blanche',
         'status quo', 'quid pro quo', 'mea culpa', 'non sequitur', 'a fortiori', 'ex parte', 'in camera', 'in rem', 'in personam', 'nolle prosequi',
         'pro bono', 'quorum', 'sine qua non', 'mutatis mutandis', 'ipso facto', 'jus', 'ius', 'dictum', 'fiat', 'nisi', 'vel non', 'supra', 'infra']


def api(host, params):
    params.update(format='json', formatversion='2')
    url = f'https://{host}/w/api.php?' + urllib.parse.urlencode(params)
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(url)


def wikitexts(titles, host='en.wikipedia.org', cache='pages.json'):
    """Fetch wikitext for titles (following redirects); returns {requested title: (final title, wikitext)}."""
    path = os.path.join(OUT, cache)
    have = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    todo = [t for t in dict.fromkeys(titles) if t not in have]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = api(host, {'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main', 'redirects': 1, 'titles': '|'.join(batch)})
        q = d.get('query', {})
        alias = {}
        for kind in ('normalized', 'redirects'):
            for x in q.get(kind, []):
                alias[x['from']] = x['to']
        final = {}
        for p in q.get('pages', []):
            final[p['title']] = p['revisions'][0]['slots']['main']['content'] if p.get('revisions') else None
        for t in batch:
            f = t
            while f in alias and alias[f] != f:
                f = alias[f]
            have[t] = [f, final.get(f)]
        json.dump(have, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'  {cache}: {min(i + 50, len(todo))}/{len(todo)}', flush=True)
        time.sleep(3)
    return have


def main():
    os.makedirs(OUT, exist_ok=True)
    names = set(json.load(open(f'{OUT}/cases.json', encoding='utf-8'))) | set(json.load(open(f'{OUT}/corpus_cases.json', encoding='utf-8')))
    print(f'{len(names)} case names')
    cases = wikitexts(sorted(names), cache='cases_wiki.json')

    # people linked from case articles whose page title contains a party word
    people = set()
    for name, (title, text) in cases.items():
        if not text:
            continue
        words = {w for w in re.findall(r"[A-Z][a-z'-]{2,}", name)}
        for target in re.findall(r'\[\[([^\]|#]+)', text[:15000]):
            target = target.strip()
            if ':' in target or ' v. ' in target:
                continue
            if any(re.search(r'\b' + re.escape(w) + r'\b', target) for w in words) and re.search(r'^[A-Z][a-z]+ ', target):
                people.add(target)
    # every justice
    lst = wikitexts(['List of justices of the Supreme Court of the United States'], cache='list.json')
    text = list(lst.values())[0][1]
    justices = {t.strip() for t in re.findall(r'\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]', text) if ':' not in t and re.match(r'^[A-Z][a-z]+(?: [A-Z][\w.]*)+$', t.strip())}
    print(f'{len(people)} linked people, {len(justices)} list links')
    wikitexts(sorted(people | justices), cache='people_wiki.json')
    json.dump(sorted(justices), open(f'{OUT}/justices.json', 'w', encoding='utf-8'))

    wikitexts(sorted(set(TERMS)), host='en.wiktionary.org', cache='terms_wikt.json')

    # other Wikipedia pages that give an IPA for each name word (e.g. "Lujan" -> Ben Ray Luján, /luːˈhɑːn/)
    import html as _html, collections
    corpus = ' '.join(_html.unescape(re.sub(r'<[^>]+>', ' ', open(f'docs/data/{x}.js', encoding='utf-8').read())) for x in ['guide', 'advanced', 'commentary'])
    cap = collections.Counter(re.findall(r"\b[A-Z][\w'-]+\b", corpus)); low = set(re.findall(r'\b[a-z][a-z]+\b', corpus))
    words = set()
    for n in names:
        words |= set(re.findall(r"[A-Z][a-z][\w'-]+", n))
    words = sorted(w for w in words if cap[w] and w.lower() not in low)
    path = f'{OUT}/surname_search.json'
    found = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    for i, w in enumerate(x for x in words if x not in found):
        d = api('en.wikipedia.org', {'action': 'query', 'list': 'search', 'srsearch': f'intitle:"{w}" insource:"IPAc-en"', 'srlimit': 5, 'srprop': ''})
        found[w] = [x['title'] for x in d.get('query', {}).get('search', [])]
        if i % 25 == 0:
            json.dump(found, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
            print(f'  surname search: {len(found)}/{len(words)}', flush=True)
        time.sleep(1)
    json.dump(found, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    wikitexts(sorted({t for v in found.values() for t in v}), cache='surname_wiki.json')


if __name__ == '__main__':
    main()
