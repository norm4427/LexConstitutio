"""Build term-by-term flashcard decks for every decided case on the site that has a summary, except the essential cases
already in flashcards.js (those stay in the topic decks). One deck per Term, grouped by Chief Justice era.

Cases without Oyez's one-sentence description use the opening of Oyez's written conclusion instead (cached in
data/raw/oyez/cases/ by oyez_fetch_all.py), up to three sentences.
Cards per case: "held" (Oyez's one-sentence description of the decision, the Court's official holding when there is
one, and the vote) and "which" (the description with the parties' names hidden; name the case).
Outputs: docs/data/fc-terms.js (the deck index) and docs/data/fc-court-<court>.js (cards for one era, loaded on demand).
Run from the repo root after build_flashcards.pl and build_votes.py:  python scripts/build_flashcards_terms.py
"""
import html, json, os, re

COURTS = [('jay', 'Jay, Rutledge & Ellsworth Courts', 1789, 1800), ('marshall', 'Marshall Court', 1801, 1835), ('taney', 'Taney Court', 1836, 1863),
          ('chase', 'Chase Court', 1864, 1873), ('waite', 'Waite Court', 1874, 1887), ('fuller', 'Fuller Court', 1888, 1909), ('white', 'White Court', 1910, 1920),
          ('taft', 'Taft Court', 1921, 1929), ('hughes', 'Hughes Court', 1930, 1940), ('stone', 'Stone Court', 1941, 1945), ('vinson', 'Vinson Court', 1946, 1952),
          ('warren', 'Warren Court', 1953, 1968), ('burger', 'Burger Court', 1969, 1985), ('rehnquist', 'Rehnquist Court', 1986, 2004), ('roberts', 'Roberts Court', 2005, 2100)]
COMMON = set('united states board education county city state department company corporation inc commission school district court town ohio texas york california america'.split())


def load(name):
    s = open(f'docs/data/{name}.js', encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def esc(s):
    return html.escape(re.sub(r'\s+', ' ', s or '').strip(), quote=False)


def holding_text(ds):
    s = re.sub(r'\s+', ' ', ds or '').strip()
    s = re.sub(r'^A case in which the Court (held|decided|ruled|found|concluded|considered|addressed|examined|determined|established)', r'The Court \1', s, flags=re.I)
    s = re.sub(r'^A case (?:that|in which) the Court (?:that\s+)?(?=(?:the|a|an|he|she|both|[A-Z])\b)', 'The Court held that ', s)   # Oyez dropped the verb
    s = re.sub(r'^A case (?:that|in which) the Court that\s+', 'The Court held that ', s, flags=re.I)
    return re.sub(r'^A case (?:that|in which) (?:the Court )?', 'The Court ', s, flags=re.I)


def oyez_conclusion(cid):
    """the first three sentences of Oyez's conclusion for a case, or ''."""
    f = f'data/raw/oyez/cases/{cid.replace("/", "_", 1)}.json'
    if not os.path.exists(f):
        return ''
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception:
        return ''
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', d.get('conclusion') or ''))).strip()
    if len(t) < 60:
        return ''
    parts = re.split(r'(?<=[a-z0-9)”"])\.\s+(?=[A-Z])', t)
    out = '. '.join(parts[:3]).rstrip('.') + '.'
    return out if len(out) < 900 else out[:900].rsplit(' ', 1)[0] + '…'


def mask(text, name):
    for w in re.findall(r"[A-Z][a-z][\w'-]+", name):
        if len(w) > 3 and w.lower() not in COMMON:
            text = re.sub(r'\b' + re.escape(w) + r'\b', '———', text)
    return text


def main():
    S = load('scotus')['cases']
    essential = set(load('flashcards')['cases'])
    V = load('votes')
    out_courts = {c[0]: {'id': c[0], 'name': c[1], 'years': f'{c[2]}–{c[3] if c[3] < 2100 else "present"}', 'decks': {}, 'cases': {}, 'cards': []} for c in COURTS}
    n = 0
    for c in S:
        if c['id'] in essential or not (c.get('dec') or c.get('y')):
            continue
        summary = c.get('ds') or oyez_conclusion(c['id'])
        if not summary:
            continue
        term = str(c.get('t') or '')
        year = int(term) if term.isdigit() else int(c.get('y') or 0)
        if not year:
            continue
        court = next(k for k, _, a, b in COURTS if a <= year <= b)
        name = re.sub(r'\s*\(\d\)$', '', c['n'])
        label = f'{name} ({c.get("y") or year})'
        deck = f'ot-{year}'
        held = esc(holding_text(summary))
        official = esc(c.get('h') or '')
        r = V['c'].get(c['id'])
        vote = ''
        if r:
            if len(r) > 5 and r[5]:
                vote = f'Affirmed by an equally divided Court ({r[0]}–{r[1]})'
            else:
                author = next((V['j'][i][0] for i, f in r[2] if f == 1), None)
                vote = f'Vote: {r[0]}–{r[1]}' + (f' · opinion by {author}' if author else '')
        back = held + (f'<span class="fc-sub">Official holding: {official}</span>' if official and official.lower() not in held.lower() else '')
        if vote:
            back += f'<span class="fc-vote">{esc(vote)}</span>'
        back += f'<p class="fc-src">Summary from <a href="https://www.oyez.org/cases/{esc(c["id"])}" target="_blank" rel="noopener">Oyez</a> (<a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener">CC BY-NC 4.0</a>).</p>'
        oc = out_courts[court]
        oc['cases'][c['id']] = {'n': name, 'y': c.get('y') or year, 'cit': c.get('cit')}
        oc['cards'].append({'id': f'x:{c["id"]}|held', 'c': c['id'], 'k': 'held', 'd': [deck], 'f': f'What did the Court decide in <i>{esc(label)}</i>?', 'b': back})
        if len(held) > 40:
            oc['cards'].append({'id': f'x:{c["id"]}|which', 'c': c['id'], 'k': 'which', 'd': [deck], 'f': 'Which case? ' + mask(held, name), 'b': f'<i>{esc(label)}</i>' + (f' · {esc(c["cit"])}' if c.get('cit') else '')})
        d = oc['decks'].setdefault(deck, {'id': deck, 'title': (f'October Term {year}' if year >= 1850 else f'{year} Term'), 'year': year, 'cases': 0, 'cards': 0})
        d['cases'] += 1
        n += 1
    index = []
    for k, _, a, b in COURTS:
        oc = out_courts[k]
        for card in oc['cards']:
            oc['decks'][card['d'][0]]['cards'] += 1
        decks = sorted(oc['decks'].values(), key=lambda d: -d['year'])
        if not decks:
            continue
        open(f'docs/data/fc-court-{k}.js', 'w', encoding='utf-8').write('window.FC_COURT_' + k.upper() + '=' + json.dumps({'cases': oc['cases'], 'cards': oc['cards']}, ensure_ascii=False, separators=(',', ':')) + ';')
        index.append({'id': k, 'name': oc['name'], 'years': oc['years'], 'cases': len(oc['cases']), 'cards': len(oc['cards']), 'decks': decks})
    index.reverse()   # most recent Court first
    open('docs/data/fc-terms.js', 'w', encoding='utf-8').write('window.FC_TERMS=' + json.dumps({'courts': index}, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{n} cases in {sum(len(c["decks"]) for c in index)} term decks across {len(index)} Courts')
    for c in index:
        print(f"  {c['name']:34} {c['cases']:5} cases {c['cards']:6} cards {len(c['decks']):3} terms")


if __name__ == '__main__':
    main()
