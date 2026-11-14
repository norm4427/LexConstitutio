"""Look up OpenAlex citation counts for harvested articles that arrived without one (Digital Commons and WordPress
journals), by title. Many law review articles are in OpenAlex but not attributed to their journal, so a title search
finds them. Titles are searched about 20 at a time with OR'd phrase filters (one request = 10 credits; the shared free
budget is 1,000 credits a day, an API key gives 10,000). Results are cached in data/raw/lrc/cites.json, so the script can
be re-run each day until done. A match needs the same title (or main title before a colon), a publication year within
2 years, and, when OpenAlex lists authors, a shared surname.
Usage: python scripts/cite_lookup.py [data/raw/new_articles.js]   (set OPENALEX_KEY to use a key)
"""
import json, os, re, sys, time, urllib.parse, urllib.request

SRC = sys.argv[1] if len(sys.argv) > 1 else 'data/raw/new_articles.js'
CACHE = 'data/raw/lrc/cites.json'
KEY = os.environ.get('OPENALEX_KEY', '')
BATCH = 20


def norm(t):
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', (t or '').lower().replace('&', 'and'))).strip()


def main_title(t):
    m = norm(t.split(':')[0])
    return m if len(m.split()) >= 4 else norm(t)


def surnames(names):
    return {re.sub(r'[^a-z]', '', n.split(',')[0].split()[-1].lower()) for n in names if n and n.split()}


def main():
    s = open(SRC, encoding='utf-8').read()
    arts = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['articles']
    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    todo = [a for a in arts if a.get('c') is None and a['id'] not in cache and len(main_title(a['t']).split()) >= 2]
    print(f'{len(todo)} articles to look up ({len(cache)} cached)', flush=True)
    remaining = None
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        phrases = []
        for a in batch:
            words = main_title(a['t']).split()[:12]          # long titles: the first 12 words are distinctive enough
            phrases.append('"' + ' '.join(words) + '"')
        params = {'filter': 'title.search:' + '|'.join(phrases), 'per_page': 200,
                  'select': 'display_name,cited_by_count,publication_year,authorships'}
        if KEY:
            params['api_key'] = KEY
        url = 'https://api.openalex.org/works?' + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0'}), timeout=90) as r:
                remaining = int(r.headers.get('X-RateLimit-Remaining') or 0)
                results = json.load(r).get('results', [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print('daily OpenAlex budget used up; re-run tomorrow (or set OPENALEX_KEY)', flush=True); break
            print('error', e.code, flush=True); time.sleep(10); continue
        except Exception as e:
            print('error', e, flush=True); time.sleep(10); continue
        res = [(norm(x.get('display_name')), x.get('cited_by_count') or 0, x.get('publication_year'),
                surnames([(au.get('author') or {}).get('display_name') or '' for au in x.get('authorships') or []])) for x in results]
        for a in batch:
            mt, full, y, au = main_title(a['t']), norm(a['t']), a.get('y'), surnames(a.get('a') or [])
            best = None
            for t, c, py, rau in res:
                if not (t == full or t.startswith(mt) or full.startswith(t) and len(t) > 25):
                    continue
                if y and py and abs(py - y) > 2:
                    continue
                if au and rau and not (au & rau):
                    continue
                best = c if best is None else max(best, c)
            cache[a['id']] = best      # None = searched, not found
        json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
        found = sum(1 for v in cache.values() if v is not None)
        print(f'{min(i + BATCH, len(todo))}/{len(todo)} searched; matched so far {found}; credits left {remaining}', flush=True)
        if remaining is not None and remaining < 25:
            print('stopping before the daily budget runs out; re-run tomorrow (or set OPENALEX_KEY)', flush=True); break
        time.sleep(0.3)


if __name__ == '__main__':
    main()
