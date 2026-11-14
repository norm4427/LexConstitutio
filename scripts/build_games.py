"""Build docs/data/games.js: prepared rounds for the Learning Center games, drawn only from the essential cases
(flashcards.js). The other games (matching, timeline, who wrote it, docket detective) are assembled in the browser.

  ruling     question presented + the true ruling + three decoys. One decoy reverses the true ruling's outcome (so it
             reads like a real holding of the same case); two are true rulings of other cases in the same topic deck.
             Decoys are chosen to be about as long as the true answer (at least 85% of its length, and as close as
             possible), so length never gives the answer away.
  overruled  an overruled decision and the case that overruled it, from Wikipedia's "List of overruled United States
             Supreme Court decisions" (facts; cached in data/raw/games/overruled.json), with decoys from the same era.
Also writes docs/data/essential.js (the essential-case ids alone).
Run from the repo root after build_flashcards.pl:  python scripts/build_games.py
"""
import html, json, os, random, re, time, urllib.error, urllib.parse, urllib.request

random.seed(7)


def load(name):
    s = open(f'docs/data/{name}.js', encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def plain(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def holding(ds):
    s = plain(ds)
    s = re.sub(r'^A case in which the Court (held|decided|ruled|found|concluded|considered|addressed|examined|determined|established)', r'The Court \1', s, flags=re.I)
    s = re.sub(r'^A case (?:that|in which) the Court (?:that\s+)?(?=(?:the|a|an|he|she|both|[A-Z])\b)', 'The Court held that ', s)   # Oyez dropped the verb
    s = re.sub(r'^A case (?:that|in which) the Court that\s+', 'The Court held that ', s, flags=re.I)
    return re.sub(r'^A case (?:that|in which) (?:the Court )?', 'The Court ', s, flags=re.I)


FLIPS = [(r'\bdid not violate\b', 'violated'), (r'\bviolated\b', 'did not violate'), (r'\bdoes not violate\b', 'violates'), (r'\bviolates\b', 'does not violate'),
         (r'\bunconstitutional\b', 'constitutional'), (r'\bconstitutional\b', 'unconstitutional'), (r'\bupheld\b', 'struck down'), (r'\bstruck down\b', 'upheld'),
         (r'\bdid not require\b', 'required'), (r'\brequired\b', 'did not require'), (r'\bdoes not protect\b', 'protects'), (r'\bprotects\b', 'does not protect'),
         (r'\bwas not entitled\b', 'was entitled'), (r'\bwas entitled\b', 'was not entitled'), (r'\bcould not\b', 'could'), (r'\bcan not\b|\bcannot\b', 'can'),
         (r'\bcould\b', 'could not'), (r'\bmay not\b', 'may'), (r'\bmay\b', 'may not'), (r'\bexceeded\b', 'did not exceed'), (r'\bpermitted\b', 'prohibited'),
         (r'\bprohibited\b', 'permitted'), (r'\bvalid\b', 'invalid'), (r'\binvalid\b', 'valid'), (r'\bdid not\b', 'did'), (r'\bdoes not\b', 'does')]


STOP = set("""the a an of to in and or for on that this was is be by with as it its at from not did does whether which court held
case cases state states united law under any their were has have had who would could should may can than such other these those
because must than there they them his her he she been also only into upon about after before more most decided ruled found""".split())


def words(s):
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def flip(s):
    for pat, rep in FLIPS:
        if re.search(pat, s):
            return re.sub(pat, rep, s, count=1)
    return None


def oyez_conclusion(cid):
    """the first two sentences of Oyez's conclusion for a case (cached by oyez_fetch_all), or ''."""
    f = f'data/raw/oyez/cases/{cid.replace("/", "_", 1)}.json'
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception:
        return ''
    t = plain(d.get('conclusion'))
    if len(t) < 60:
        return ''
    parts = re.split(r'(?<=[a-z0-9)”"])\.\s+(?=[A-Z])', t)
    out = '. '.join(parts[:2]).rstrip('.') + '.'
    return out if len(out) < 600 else out[:600].rsplit(' ', 1)[0] + '…'


def wiki_get(url):
    """GET a Wikipedia API url politely (2.5 s apart, backing off on 429); None if it keeps failing (not cached)."""
    for n in range(5):
        time.sleep(2.5 + 20 * n)
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0 (static site build)'}), timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
        except Exception:
            pass
    return None


def wiki_holding(title):
    """the "Holding" field of the case's Wikipedia infobox (cached in data/raw/games/wiki_holdings.json), or ''."""
    path = 'data/raw/games/wiki_holdings.json'
    cache = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    if title not in cache:
        url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'parse', 'page': title, 'prop': 'wikitext', 'redirects': 1, 'format': 'json', 'formatversion': 2})
        d = wiki_get(url)
        if d is None:
            return ''
        try:
            m = re.search(r'\|\s*Holding\s*=\s*(.*?)(?=\n\s*\||\n\}\})', d['parse']['wikitext'], re.S | re.I)
            cache[title] = m.group(1) if m else ''
        except Exception:
            cache[title] = ''
        open(path, 'w', encoding='utf-8').write(json.dumps(cache, ensure_ascii=False, indent=1))
    s = cache[title]
    s = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', s, flags=re.S)
    s = re.sub(r'\{\{(?:ussc|USSC)\|([^|}]*)\|([^|}]*)\|([^|}]*)[^}]*\}\}', r'\1 U.S. \2 (\3)', s)
    s = re.sub(r'\{\{[^{}]*\}\}', '', s)
    s = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r"'{2,}", '', plain(s)).strip()
    # drop disposition lines ("The judgments are affirmed.") and precedent notes ("Shurtleff distinguished, Myers limited.")
    parts = [p.strip() for p in re.split(r'(?<=[a-z0-9)”"])\.\s+(?=[A-Z])', s)]
    parts = [p for p in parts if not re.fullmatch(r'(?:The )?(?:judgments?|decisions?|lower court) (?:is|are|was|were) (?:affirmed|reversed|vacated|remanded)[^.]*\.?', p, re.I)
             and not re.fullmatch(r'(?:[A-Z][\w.’\']*(?: v\. [\w.’\']+)? (?:distinguished|limited|overruled|followed|applied|affirmed|extended|questioned)[,;]?\s*)+\.?', p)]
    s = '. '.join(parts[:2]).rstrip('.') + '.' if parts else ''
    return s if len(s) >= 40 else ''


def clean_conclusion(t):
    """drop Oyez's yes/no answer to its own question and sentences that only report the vote or the author."""
    t = re.sub(r'^(?:(?:Yes|No)(?:,? and (?:yes|no))*|No decision|Yes in part[^.]*|No in part[^.]*)[.,]\s*', '', t, flags=re.I)
    parts = [p for p in re.split(r'(?<=[a-z0-9)”"])\.\s+(?=[A-Z])', t)
             if not re.fullmatch(r'(?:In an? [^,]*(?:decision|opinion)[^,]*, )?(?:Justice|Chief Justice)[^.]*(?:wrote|delivered|writing)[^.]*(?:revers|affirm|remand|vacat)[^.]*\.?', p.strip())]
    out = '. '.join(parts[:2]).rstrip('.') + '.' if parts else ''
    return out if len(out) >= 60 else ''


def wiki_lead(title):
    """the first two sentences of a Wikipedia article's lead (cached in data/raw/games/wiki_leads.json), or ''."""
    path = 'data/raw/games/wiki_leads.json'
    cache = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    if title not in cache:
        url = 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title.replace(' ', '_'))
        d = wiki_get(url)
        if d is None:
            return ''
        cache[title] = d.get('extract') or ''
        open(path, 'w', encoding='utf-8').write(json.dumps(cache, ensure_ascii=False, indent=1))
    parts = re.split(r'(?<=[a-z0-9)”"])\.\s+(?=[A-Z])', cache[title])
    return '. '.join(parts[:2]).rstrip('.') + '.' if cache[title] else ''


def overruled_pairs():
    path = 'data/raw/games/overruled.json'
    os.makedirs('data/raw/games', exist_ok=True)
    if not os.path.exists(path):
        url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'parse', 'page': 'List of overruled United States Supreme Court decisions', 'prop': 'wikitext', 'format': 'json', 'formatversion': 2})
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0 (static site build)'}), timeout=60))
        open(path, 'w', encoding='utf-8').write(json.dumps(d['parse']['wikitext'], ensure_ascii=False))
    text = json.load(open(path, encoding='utf-8'))
    pairs = []
    for row in re.split(r'\n\|-', text):
        cells = [c for c in re.split(r'\n\|', row) if "[[" in c]
        if len(cells) >= 2:
            def parse(c):
                l = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", c)
                cit = re.search(r'(\d+) U\.\s?S\. (\d+)', c)
                return ((l.group(2) or l.group(1)).strip() if l else '', f'{cit.group(1)} U.S. {cit.group(2)}' if cit else '', l.group(1).strip() if l else '')
            pairs.append((parse(cells[0]), parse(cells[1])))
    return pairs


def key(n):
    m = re.match(r"^(?:The )?([A-Z][\w'.&-]+)[^v]*? v\. (?:The )?([A-Z][\w'.&-]+)", n or '')
    return (m.group(1).lower(), m.group(2).lower()) if m else (n or '').lower()


def main():
    F = load('flashcards')
    S = {c['id']: c for c in load('scotus')['cases']}
    deck_of = {}
    for c in F['cards']:
        deck_of.setdefault(c['c'], [d for d in c['d'] if d != 'basics'])
    ess = [cid for cid in F['cases'] if S.get(cid, {}).get('ds') and not re.search(r'will decide|will consider|whether', S[cid]['ds'], re.I)]
    hold = {cid: holding(S[cid]['ds']) for cid in ess}
    ruling = []
    for cid in ess:
        q = plain(S[cid].get('q'))
        a = hold[cid]
        if not q or len(a) < 60 or len(q) > 600:
            continue
        decoys = []
        f = flip(a)
        if f and f != a:
            decoys.append(f)
        tw = words(q + ' ' + a)
        same = [o for o in ess if o != cid and set(deck_of.get(o, [])) & set(deck_of.get(cid, [])) and 0.85 * len(a) <= len(hold[o]) <= 1.6 * len(a)]
        # most topical first: share the most content words with the question and true ruling (so decoys are about the
        # same subject), then closest in length
        same.sort(key=lambda o: (-len(tw & words(hold[o] + ' ' + plain(S[o].get('q')))), abs(len(hold[o]) - len(a))))
        for o in same:
            if len(decoys) >= 3:
                break
            if hold[o] not in decoys:
                decoys.append(hold[o])
        if len(decoys) == 3:
            ruling.append({'c': cid, 'q': q, 'a': a, 'd': decoys})
    # overruled
    by_key, by_cit = {}, {}
    for cid, c in S.items():
        by_key.setdefault(key(re.sub(r'\s*\(\d\)$', '', c['n'])), cid)
        if c.get('cit'):
            by_cit.setdefault(c['cit'], cid)
        if c.get('citUS'):
            by_cit.setdefault(c['citUS'], cid)
    over = []
    for (a, acit, awiki), (b, bcit, _) in overruled_pairs():
        ca = by_cit.get(acit) or by_key.get(key(a))
        cb = by_cit.get(bcit) or by_key.get(key(b))
        if ca and cb and ca != cb and (ca in F['cases'] or cb in F['cases']):
            over.append({'old': ca, 'new': cb, 'wiki': awiki})
    seen = set()
    over = [o for o in over if not (o['old'] in seen or seen.add(o['old']))]
    # what the overruled decision held, from sourced text: the Oyez summary, else the Holding line of the case's Wikipedia
    # infobox (CC BY-SA), else Oyez's conclusion (minus its yes/no answer and vote-only sentences), else the lead of
    # the case's Wikipedia article (CC BY-SA); a round with none of these is dropped
    kept = []
    for o in over:
        c = S[o['old']]
        h, src = (holding(c['ds']), '') if c.get('ds') else ('', '')
        if not h and o['wiki']:
            h, src = wiki_holding(o['wiki']), 'wiki'
        if not h:
            h, src = clean_conclusion(oyez_conclusion(o['old'])), ''
        if not h and o['wiki']:
            h, src = wiki_lead(o['wiki']), 'wiki'
        wiki = o.pop('wiki')
        if not h:
            print(f"  overruled: no description for {c['n']}, round dropped")
            continue
        o['h'] = h
        if src:
            o['src'] = 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(wiki.replace(' ', '_'))
        kept.append(o)
    over = kept
    data = {'ruling': ruling, 'overruled': over}
    open('docs/data/games.js', 'w', encoding='utf-8').write('window.GAMES=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    # the essential-case ids on their own (small), for pages that need the list without the flashcards
    open('docs/data/essential.js', 'w', encoding='utf-8').write('window.ESSENTIAL=' + json.dumps(sorted(F['cases']), separators=(',', ':')) + ';')
    ratio = [min(len(d) for d in r['d']) / len(r['a']) for r in ruling]
    print(f'ruling rounds: {len(ruling)} (shortest decoy averages {sum(ratio) / len(ratio):.0%} of the true answer); overruled pairs: {len(over)}')
    for r in ruling[:2]:
        print('Q:', r['q'][:150]); print('  A:', r['a'][:160]); [print('  D:', d[:160]) for d in r['d']]


if __name__ == '__main__':
    main()
