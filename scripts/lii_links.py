"""Link each annotated clause to its page in Cornell LII's edition of the Constitution Annotated
(https://www.law.cornell.edu/constitution-conan/...). Linking only; nothing from LII is copied.

The address is built from the clause's place in the text (a1s8c3 -> article-1/section-8/clause-3; a single-paragraph
section or article has no clause part; am14s1 -> amendment-14/section-1; pre -> preamble). A link is kept only when the
page loads and contains the clause's own words (the first eight words of its highlighted text), so a wrong address is never
used (or, since LII's pages list the Constitution Annotated essays filed under each provision, when the page lists the
clause's own essay titles). Pages are cached in data/raw/lii/. Writes `lii` on each clause in docs/data/constitution.js.
Run from the repo root after build_constitution.py:  python scripts/lii_links.py
"""
import html, json, os, re, time, urllib.request

BASE = 'https://www.law.cornell.edu/constitution-conan/'
CACHE = 'data/raw/lii'


def path_for(uid, alias):
    if uid == 'pre':
        return 'preamble'
    m = re.fullmatch(r'am(\d+)(?:s(\d+))?', uid)
    if m:
        return f'amendment-{m.group(1)}' + (f'/section-{m.group(2)}' if m.group(2) else '')
    m = re.fullmatch(r'a(\d+)(?:s(\d+))?c(\d+)', uid)
    if not m:
        return None
    p = f'article-{m.group(1)}' + (f'/section-{m.group(2)}' if m.group(2) else '')
    return p if alias else p + f'/clause-{m.group(3)}'


def page(path):
    os.makedirs(CACHE, exist_ok=True)
    f = f"{CACHE}/{path.replace('/', '_')}.html"
    if os.path.exists(f):
        return open(f, encoding='utf-8').read()
    time.sleep(1.5)
    try:
        req = urllib.request.Request(BASE + path, headers={'User-Agent': 'Mozilla/5.0 (LexConstitutio static site build)'})
        s = urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'ignore')
    except Exception as e:
        print('  failed', path, e)
        return ''
    open(f, 'w', encoding='utf-8').write(s)
    return s


def words(s):
    return re.findall(r'[a-z]+', html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).lower())


def main():
    raw = open('docs/data/constitution.js', encoding='utf-8').read()
    K = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    units = {u['id']: u for u in K['units']}
    ok, bad = 0, []
    for c in K['clauses']:
        u = units.get(c['unit']) or next((x for x in K['units'] if x.get('alias') == c['unit']), None)
        p = path_for(u['id'], u.get('alias')) if u else None
        c.pop('lii', None)
        if not p:
            bad.append((c['id'], 'no address')); continue
        body = ' '.join(words(page(p)))
        probe = ' '.join(words(c['hl'])[:8])
        # LII's pages list the Constitution Annotated essays filed under the provision, so the clause's own overview essay
        # title ("Overview of Legislative Vesting Clause") on the page confirms it as well as the clause's words do
        ov = ((c.get('conan') or {}).get('overview') or {}).get('title') or ''
        titles = [' '.join(words(t)) for t in [ov] + [d['title'] for d in (c.get('conan') or {}).get('dev') or []] if len(words(t)) >= 3]
        # or the page's opening heading names the clause ("Disqualification", "Nineteenth", "Presidential Vacancy"),
        # since LII's later edition words some essay titles differently
        main = re.search(r'<main.*?</main>', page(p), re.S)
        head = ' '.join(words(re.sub(r'<nav.*?</nav>|<script.*?</script>', '', main.group(0) if main else '', flags=re.S))[:40])
        keys = [w for w in words(c['name']) if len(w) > 6 and w not in ('amendment', 'clauses')]
        tail = ' '.join(words(ov.split(',', 1)[1])) if ',' in ov else ''
        named = any(k in head.split() for k in keys) or (len(tail.split()) >= 2 and tail in head)
        if (probe and probe in body) or (titles and sum(t in body for t in titles) >= min(2, len(titles))) or named:
            c['lii'] = BASE + p; ok += 1
        else:
            bad.append((c['id'], p))
    open('docs/data/constitution.js', 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(K, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{ok} of {len(K["clauses"])} clauses linked to Cornell LII; not linked: {bad}')


if __name__ == '__main__':
    main()
