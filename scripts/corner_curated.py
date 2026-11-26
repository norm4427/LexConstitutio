"""Hand-picked Originalist's Corner passages from the library's full texts (scripts/corner_curated.json), merged into
docs/data/corner.js. Run after build_corner.pl (which rebuilds corner.js from data/raw/corner); safe to re-run: the
passages added last time (ids "q1", "q2", ...) and the sources added for them are replaced.

Each passage's text is read from the library itself (docs/data/lib/<book>-<part>.js, block <block>) or from an Internet
Archive OCR file (data/raw/library/ia/<id>.txt), cut to the span "from".."to" if given, with the OCR misreadings listed
in "fix" corrected; so every quotation is the source's own words. A passage that can't be found stops the run.
Run from the repo root:  python scripts/corner_curated.py
"""
import json, re, sys

CORNER = 'docs/data/corner.js'
DATA = 'scripts/corner_curated.json'


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def lib_block(book, part, block):
    s = open(f'docs/data/lib/{book}-{part}.js', encoding='utf-8').read()
    c = json.loads(s[s.index(']=') + 2:].rstrip().rstrip(';'))
    return c['b'][block][1], c['t']


def ia_text(ident):
    t = open(f'data/raw/library/ia/{ident}.txt', encoding='utf-8', errors='replace').read().replace('\r', '')
    t = re.sub(r'(\w)[-¬]\s*\n\s*(?=[a-z])', r'\1', t)        # words broken at a line end
    t = re.sub(r'[\^»]', '', t)                                  # note marks
    return re.sub(r'\s+', ' ', t)


def passage_text(p):
    if p.get('ia'):
        text = ia_text(p['ia'])
    else:
        text = lib_block(p['book'], p['part'], p['block'])[0]
    for bad, good in p.get('fix', []):
        if bad not in text:
            raise ValueError(f'fix {bad!r} not found')
        text = text.replace(bad, good)
    a = text.index(p['from']) if p.get('from') else 0
    z = text.index(p['to'], a) + len(p['to']) if p.get('to') else len(text)
    text = re.sub(r'\s+', ' ', text[a:z]).strip()
    text = re.sub(r'\s+([,.;:?!])', r'\1', text)
    if a > 0 or z < len(text):
        pass
    return text


def main():
    data = json.load(open(DATA, encoding='utf-8'))
    C = load_js(CORNER)
    # drop what an earlier run added
    old = {k for k in C['passages'] if k.startswith('q')}
    for k in old:
        del C['passages'][k]
    for tid, srcs in C['index'].items():
        for sid in list(srcs):
            srcs[sid] = [x for x in srcs[sid] if x not in old]
            if not srcs[sid]:
                del srcs[sid]
    C['sources'] = [s for s in C['sources'] if not s.get('cur')]
    known = {s['id'] for s in C['sources']}
    for tid in C['order']:
        C['order'][tid] = [s for s in C['order'][tid] if s in known and s in C['index'].get(tid, {})]
    # sources for the new passages
    lib = {x['id']: x for x in load_js('docs/data/lib-index.js')}
    for sid, meta in data['sources'].items():
        if sid in known:
            continue
        url = meta.get('url') or (f'#/library/book/{sid}' if sid in lib else '')
        C['sources'].append({'id': sid, 'name': meta['name'], 'author': meta['author'], 'year': meta['year'], 'desc': meta['desc'],
                             'url': url, 'n': 0, 'cur': True})
        known.add(sid)
    errors, n = [], 0
    for p in data['passages']:
        try:
            text = passage_text(p)
        except (ValueError, IndexError, FileNotFoundError) as e:
            errors.append(f"{p['topic']} / {p['s']} / {p.get('book') or p.get('ia')} {p.get('part', '')}:{p.get('block', '')}: {e}")
            continue
        n += 1
        pid = f'q{n}'
        o = {'s': p['s'], 'loc': p['loc'], 't': text}
        if p.get('book'):
            o['lib'], o['n'] = p['book'], p['part']
        if p.get('ia'):
            o['u'] = f"https://archive.org/details/{p['ia']}"
        C['passages'][pid] = o
        C['index'].setdefault(p['topic'], {}).setdefault(p['s'], []).append(pid)
        order = C['order'].setdefault(p['topic'], [])
        if p['s'] not in order:
            order.append(p['s'])
    if errors:
        print('passages not found:\n  ' + '\n  '.join(errors))
        sys.exit(1)
    for s in C['sources']:
        if s.get('cur'):
            s['n'] = sum(1 for x in C['passages'].values() if x['s'] == s['id'])
    for t in C['topics']:
        t['n'] = sum(len(v) for v in C['index'].get(t['id'], {}).values())
    open(CORNER, 'w', encoding='utf-8').write('window.CORNER=' + json.dumps(C, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + ';')
    print(f'{n} curated passages merged into {CORNER}')


if __name__ == '__main__':
    main()
