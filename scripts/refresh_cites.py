"""Refresh citation counts (`c`, OpenAlex's cited_by_count) across the article index, newest articles first.

1. Articles with a DOI: looked up 50 at a time by DOI (1 credit a request), so every DOI article's count is current.
2. Articles without a DOI (repository and journal-site entries): searched by title, about 20 at a time with OR'd phrase
   filters (10 credits a request), newest first, until the day's budget is nearly spent. A match needs the same title (or
   the main title before a colon), a publication year within 2 years, and a shared author surname when both list authors
   (the rule cite_lookup.py uses).
OpenAlex's shared free budget is 1,000 credits a day (an API key, OPENALEX_KEY, gives more). Results are cached in
data/raw/cites_refresh.json with the date looked up; a count less than 30 days old is not looked up again, so the script
can be re-run daily until every article has been checked. `c` is written only when a count was found (a search that finds
nothing leaves an existing count alone).
Run from the repo root (before fix_text.py):  python scripts/refresh_cites.py [--titles-only|--dois-only]
"""
import datetime, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

CACHE = 'data/raw/cites_refresh.json'
KEY = os.environ.get('OPENALEX_KEY', '')
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
TODAY = datetime.date.today()
FRESH_DAYS = 30
RESERVE = 30            # credits left untouched


def norm(t):
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', (t or '').lower().replace('&', 'and'))).strip()


def main_title(t):
    m = norm(re.split(r'[:?]', t)[0])
    return m if len(m.split()) >= 4 else norm(t)


def surnames(names):
    out = set()
    for n in names:
        parts = (n or '').split(',')[0].split() or (n or '').split()
        if parts:
            out.add(re.sub(r'[^a-z]', '', parts[-1].lower()))
    return out - {''}


remaining = None


def call(params):
    global remaining
    if KEY:
        params['api_key'] = KEY
    url = 'https://api.openalex.org/works?' + urllib.parse.urlencode(params)
    for n in range(10):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                remaining = int(r.headers.get('X-RateLimit-Remaining') or 0)
                return json.load(r).get('results', [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # a 429 is either the per-second limit (credits remain: wait and retry) or the day's budget (none left)
                left = e.headers.get('X-RateLimit-Remaining')
                print('  429:', {k: v for k, v in e.headers.items() if 'ratelimit' in k.lower() or 'retry' in k.lower()}, flush=True)
                if left is not None and int(left) <= 0:
                    remaining = 0
                    return None
                time.sleep(float(e.headers.get("Retry-After") or 0) + 1 or 3 * (n + 1))
                continue
            time.sleep(5 * (n + 1))
        except Exception as e:
            print('  request error:', e, flush=True)
            time.sleep(5 * (n + 1))
    return None


def fresh(entry):
    return entry and (TODAY - datetime.date.fromisoformat(entry['d'])).days < FRESH_DAYS


def main():
    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    path = 'docs/data/articles.js'
    raw = open(path, encoding='utf-8').read()
    d = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    arts = sorted(d['articles'], key=lambda a: -(a.get('y') or 0))
    doi_of = lambda a: (a.get('u') or '').split('doi.org/', 1)[1].lower() if 'doi.org/' in (a.get('u') or '') else None

    if '--titles-only' not in sys.argv:
        todo = [a for a in arts if doi_of(a) and not fresh(cache.get(a['id']))]
        print(f'{len(todo)} DOI articles to refresh', flush=True)
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            res = call({'filter': 'doi:' + '|'.join(doi_of(a) for a in batch), 'per-page': 50, 'select': 'doi,cited_by_count'})
            if res is None:
                print('OpenAlex budget used up; re-run tomorrow', flush=True)
                break
            got = {(w.get('doi') or '').replace('https://doi.org/', '').lower(): w.get('cited_by_count') or 0 for w in res}
            for a in batch:
                cache[a['id']] = {'c': got.get(doi_of(a)), 'd': TODAY.isoformat()}
            if i % 1000 == 0:
                print(f'  {i + len(batch)}/{len(todo)} DOIs; credits left {remaining}', flush=True)
                json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
            if remaining is not None and remaining < RESERVE:
                break
            time.sleep(0.2)

    if '--dois-only' not in sys.argv:
        todo = [a for a in arts if not doi_of(a) and not fresh(cache.get(a['id'])) and len(main_title(a['t']).split()) >= 2]
        print(f'{len(todo)} articles without a DOI to search by title (newest first)', flush=True)
        for i in range(0, len(todo), 20):
            if remaining is not None and remaining < RESERVE + 10:
                print('stopping before the daily budget runs out; re-run tomorrow', flush=True)
                break
            batch = todo[i:i + 20]
            phrases = ['"' + ' '.join(main_title(a['t']).replace('"', '').split()[:12]) + '"' for a in batch]
            res = call({'filter': 'title.search:' + '|'.join(phrases), 'per_page': 200,
                        'select': 'display_name,cited_by_count,publication_year,authorships'})
            if res is None:
                print('OpenAlex budget used up; re-run tomorrow', flush=True)
                break
            cand = [(norm(x.get('display_name')), x.get('cited_by_count') or 0, x.get('publication_year'),
                     surnames([(au.get('author') or {}).get('display_name') or '' for au in x.get('authorships') or []])) for x in res]
            for a in batch:
                mt, full, y, au = main_title(a['t']), norm(a['t']), a.get('y'), surnames(a.get('a') or [])
                best = None
                for t, c, py, rau in cand:
                    if not (t == full or t.startswith(mt) or (full.startswith(t) and len(t) > 25)):
                        continue
                    if y and py and abs(py - y) > 2:
                        continue
                    if au and rau and not (au & rau):
                        continue
                    best = c if best is None else max(best, c)
                cache[a['id']] = {'c': best, 'd': TODAY.isoformat()}
            if (i // 20) % 10 == 0:
                print(f'  {i + len(batch)}/{len(todo)} searched; credits left {remaining}', flush=True)
                json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
            time.sleep(1.0)

    json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
    changed = 0
    for a in d['articles']:
        e = cache.get(a['id'])
        if e and e.get('c') is not None and a.get('c') != e['c']:
            a['c'] = e['c']
            changed += 1
    open(path, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    have = sum(1 for a in d['articles'] if a.get('c') is not None)
    print(f'{changed} citation counts updated; {have} of {len(d["articles"])} articles now have a count')


if __name__ == '__main__':
    main()
