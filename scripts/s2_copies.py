"""Second source for free copies: Semantic Scholar's batch API (openAccessPdf), asked for each DOI-only article without a free route.
Responses are cached in data/raw/s2/<n>.json (500 DOIs per request). A copy is kept under the same rules as free_copies.py: title
matches ours, year within one, first author's surname among the authors, and the host is the journal's own, an author's institution
(from the OpenAlex cache) or SSRN checked through Crossref. Findings are merged into data/raw/free_copies.json and set as `oa`.
Run after free_copies.py:  python scripts/s2_copies.py
"""
import hashlib, json, os, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import free_copies as fc
from open_copies import norm, surname

CACHE = 'data/raw/s2'


def batch(dois):
    key = hashlib.md5('|'.join(dois).encode()).hexdigest()
    p = f'{CACHE}/{key}.json'
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    body = json.dumps({'ids': ['DOI:' + d for d in dois]}).encode()
    url = 'https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,authors,openAccessPdf,externalIds'
    for n in range(4):
        try:
            time.sleep(2 + 10 * n)
            r = urllib.request.urlopen(urllib.request.Request(url, body, {**fc.UA, 'Content-Type': 'application/json'}), timeout=120)
            res = json.load(r)
            json.dump({'dois': dois, 'res': res}, open(p, 'w', encoding='utf-8'))
            return {'dois': dois, 'res': res}
        except urllib.error.HTTPError as e:
            print('  HTTP', e.code, flush=True)
            if e.code not in (429, 500, 502, 503):
                break
        except Exception as e:
            print('  ', e, flush=True)
    return None


def main():
    os.makedirs(CACHE, exist_ok=True)
    fc.AUTH = fc.oc.author_insts()
    raw, data = fc.load()
    arts = data['articles']
    cand = [a for a in fc.candidates(arts)]
    old = json.load(open('data/raw/free_copies.json', encoding='utf-8')) if os.path.exists('data/raw/free_copies.json') else {}
    cand = [a for a in cand if a['id'] not in old]
    found = {}
    for i in range(0, len(cand), 500):
        part = cand[i:i + 500]
        b = batch([fc.doi_of(a) for a in part])
        if not b:
            print('stopped at', i)
            break
        for a, r in zip(part, b['res']):
            if not r or not (r.get('openAccessPdf') or {}).get('url'):
                continue
            if norm(r.get('title')) != norm(a['t']) and not (len(norm(a['t'])) > 25 and norm(a['t']) in norm(r.get('title'))):
                continue
            if abs((r.get('year') or 0) - (a.get('y') or 0)) > 1:
                continue
            names = ' '.join(norm(x.get('name')) for x in r.get('authors') or []).split()
            if not a['a'] or surname(a['a'][0]) not in names:
                continue
            url = r['openAccessPdf']['url']
            # reuse free_copies.choose() by presenting this as an Unpaywall-style record
            rec = {'is_oa': True, 'title': r['title'], 'year': r.get('year'),
                   'oa_locations': [{'url': url, 'url_for_pdf': url, 'url_for_landing_page': url, 'host_type': 'repository', 'version': ''}]}
            best = fc.choose(a, rec)
            if best:
                best['via'] += ' (s2)'
                found[a['id']] = best
        print(f'{min(i + 500, len(cand))}/{len(cand)} checked, {len(found)} kept', flush=True)
    old.update(found)
    json.dump(old, open('data/raw/free_copies.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n = 0
    for a in arts:
        f = found.get(a['id'])
        if f and not (a.get('oa') or a.get('pdf') or a.get('pub')):
            a['oa'] = f['url']
            n += 1
    open(fc.ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{len(found)} free copies found, {n} set')


if __name__ == '__main__':
    main()
