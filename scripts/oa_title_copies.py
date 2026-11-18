"""Third source for free copies: OpenAlex title search, for DOI-only articles still without a free route (most cited first).
Finds repository and SSRN records filed under a different DOI than JSTOR's. A record counts only when its title matches ours,
its first author's surname is among ours, its year is within five of ours (SSRN preprints), and the copy passes free_copies.choose():
the journal's own host, an author's institution's repository, or an SSRN paper confirmed by Crossref.
OpenAlex's free allowance is about 1,000 requests a day, so this takes the next N unchecked articles each day (cached in
data/raw/oa_title/<id>.json). Run after free_copies.py:  python scripts/oa_title_copies.py [N]
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import free_copies as fc
from open_copies import norm, surname

CACHE = 'data/raw/oa_title'


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 900
    os.makedirs(CACHE, exist_ok=True)
    fc.AUTH = fc.oc.author_insts()
    raw, data = fc.load()
    arts = data['articles']
    old = json.load(open('data/raw/free_copies.json', encoding='utf-8')) if os.path.exists('data/raw/free_copies.json') else {}
    cand = [a for a in fc.candidates(arts) if a['id'] not in old]
    todo = [a for a in cand if not os.path.exists(f'{CACHE}/{a["id"]}.json')][:n]
    print(len(todo), 'to search', flush=True)
    for k, a in enumerate(todo):
        title = re.sub(r'[^\w\s]', ' ', a['t'])
        url = 'https://api.openalex.org/works?' + urllib.parse.urlencode({
            'filter': 'title.search:' + title, 'per-page': 15, 'mailto': fc.EMAIL,
            'select': 'doi,title,publication_year,authorships,locations'})
        try:
            time.sleep(0.3)
            res = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=fc.UA), timeout=60))['results']
        except urllib.error.HTTPError as e:
            print('HTTP', e.code, 'stopping at', k)
            break
        except Exception:
            continue
        json.dump(res, open(f'{CACHE}/{a["id"]}.json', 'w', encoding='utf-8'))
    found = {}
    for a in cand:
        p = f'{CACHE}/{a["id"]}.json'
        if not os.path.exists(p):
            continue
        for w in json.load(open(p, encoding='utf-8')):
            if norm(w.get('title')) != norm(a['t']):
                continue
            names = ' '.join(norm((x.get('author') or {}).get('display_name')) for x in w.get('authorships') or []).split()
            if not a['a'] or surname(a['a'][0]) not in names or abs((w.get('publication_year') or 0) - (a.get('y') or 0)) > 5:
                continue
            locs = []
            for l in w.get('locations') or []:
                if not l.get('is_oa') or not (l.get('landing_page_url') or l.get('pdf_url')):
                    continue
                locs.append({'url': l.get('pdf_url') or l.get('landing_page_url'), 'url_for_pdf': l.get('pdf_url'),
                             'url_for_landing_page': l.get('landing_page_url'), 'host_type': (l.get('source') or {}).get('type'),
                             'version': l.get('version') or ''})
            ww = dict(w)
            fc.oc.SEEN.setdefault(fc.doi_of(a), ww)       # authors' institutions from this record when the DOI record is not cached
            best = fc.choose(a, {'is_oa': True, 'title': a['t'], 'year': a['y'], 'oa_locations': locs})
            if best and not (best['via'] == 'ssrn'):
                best['via'] += ' (title search)'
                found[a['id']] = best
                break
            if best:
                best['via'] += ' (title search)'
                found[a['id']] = best
                break
    old.update(found)
    json.dump(old, open('data/raw/free_copies.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    k = 0
    for a in arts:
        f = found.get(a['id'])
        if f and not (a.get('oa') or a.get('pdf') or a.get('pub')):
            a['oa'] = f['url']
            k += 1
    open(fc.ART, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{len(found)} free copies found, {k} set')


if __name__ == '__main__':
    main()
