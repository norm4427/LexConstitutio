"""Replace links that pass through aggregators (Dialnet, Questia, CDN mirrors) with direct links, or drop the article.

Aggregator records can carry the wrong title (a Dialnet page showed a different name from the article on Harvard's site), and
Questia closed in 2020, so these links are never kept. For each such article, the OpenAlex record found by title, journal
and year is searched for a direct copy, kept only when it is independently confirmed:
  - a DOI whose Crossref record has the same title (Crossref is the DOI registry);
  - a page on the journal's own site (harvardlawreview.org, stanfordlawreview.org, journals.law.harvard.edu ...) whose
    address contains the words of the title (these sites build page addresses from article titles);
  - an author's SelectedWorks page (works.bepress.com) only when its address names an author of the article.
An article with no confirmed direct link is removed from the index (err on the side of exclusion).
Book-review titles that carry the reviewed book's bibliographic line ("TITLE. By Author. Cambridge, Mass.: Harvard
University Press. 2018. Pp. xii, 221. $39.95.") are cut to the review's own title.
Run from the repo root after build.ps1 (before open_copies.py and fix_text.py):  python scripts/fix_indirect_links.py
"""
import json, os, re, time, unicodedata, urllib.parse, urllib.request

BAD = ('dialnet.unirioja.es', 'questia.com', 'netdna-cdn.com', 'wpengine', 'semanticscholar.org', 'researchgate.net')
OWN_SITES = {'hlr': 'harvardlawreview.org', 'slr': 'stanfordlawreview.org', 'ylj': 'yalelawjournal.org',
             'hjlpp': 'journals.law.harvard.edu', 'colr': 'columbialawreview.org', 'valr': 'virginialawreview.org'}
JOURNAL_NAMES = {'hlr': 'harvard law review', 'slr': 'stanford law review', 'ylj': 'yale law journal',
                 'hjlpp': 'harvard journal of law', 'colr': 'columbia law review', 'valr': 'virginia law review'}
CACHE = 'data/raw/indirect_links.json'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}


def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s or '') if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def get(url, cache):
    if url in cache:
        return cache[url]
    for n in range(4):
        try:
            time.sleep(0.3 + 4 * n)
            cache[url] = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
            return cache[url]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                cache[url] = None
                return None
        except Exception:
            pass
    return None


def clean_review_title(t):
    """'Essay title: BOOK TITLE. By X. City: Press. 2018. Pp. 312. $30.' -> 'Essay title'; with no essay title,
    the reviewed book's title in title case."""
    m = re.match(r'^(.*?)\s+By\s+[^.]+\..*\bPp\.', t)
    if not m:
        return t
    head = m.group(1).strip().rstrip('.')
    caps = re.search(r'([A-Z][A-Z0-9’\'\-:,;&!? ]{6,})$', head)
    if caps and sum(ch.isupper() for ch in caps.group(1)) > 0.6 * sum(ch.isalpha() for ch in caps.group(1)):
        essay = head[:caps.start()].strip().rstrip(':').strip()
        if len(essay) > 8:
            return essay
        small = {'a', 'an', 'the', 'of', 'and', 'or', 'in', 'on', 'to', 'for', 'by', 'at', 'as', 'but', 'from', 'with', 'into'}
        words = caps.group(1).strip().lower().split(' ')
        return ' '.join(w if (i and w in small and not words[i - 1].endswith(':')) else w[:1].upper() + w[1:] for i, w in enumerate(words))
    return head


def slug_ok(url, title):
    path = norm(urllib.parse.unquote(urllib.parse.urlparse(url).path))
    words = [w for w in norm(title).split() if len(w) > 3]
    return len(words) >= 2 and sum(w in path for w in words) >= max(2, int(0.7 * len(words)))


def main():
    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    raw = open('docs/data/articles.js', encoding='utf-8').read()
    data = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    arts = data['articles']
    retitled = 0
    for a in arts:
        t = clean_review_title(a['t'])
        if t != a['t']:
            a['t'] = t; a['rv'] = 1; retitled += 1
    bad = [a for a in arts if any(h in (a.get('u') or '') for h in BAD) or any(h in (a.get('pdf') or '') for h in BAD)]
    fixed, dropped, unchecked = [], [], []
    for a in bad:
        if a.get('pdf') and any(h in a['pdf'] for h in BAD):
            a.pop('pdf')
        if not any(h in (a.get('u') or '') for h in BAD):
            continue
        q = urllib.parse.urlencode({'search': a['t'][:120], 'filter': f"publication_year:{(a.get('y') or 0) - 1}-{(a.get('y') or 0) + 1}",
                                    'per-page': 10, 'select': 'title,doi,publication_year,authorships,locations,primary_location'})
        resp = get('https://api.openalex.org/works?' + q, cache)
        if resp is None:            # lookup failed (rate limit, network): leave the article for the next run, never drop it
            unchecked.append(a)
            continue
        res = resp.get('results') or []
        surnames = {norm(n).split()[-1] for n in a['a'] if norm(n)}
        new = None
        for w in res:
            if norm(w.get('title')) != norm(a['t']):
                continue
            cands = []
            if w.get('doi'):
                cands.append(w['doi'])
            for l in w.get('locations') or []:
                cands += [l.get('landing_page_url') or '', l.get('pdf_url') or '']
            for u in cands:
                if not u or any(h in u for h in BAD):
                    continue
                if 'doi.org/' in u:
                    cr = get('https://api.crossref.org/works/' + urllib.parse.quote(u.split('doi.org/', 1)[1]), cache)
                    msg = (cr or {}).get('message') or {}
                    ct = msg.get('title') or ['']
                    jt = norm((msg.get('container-title') or [''])[0])
                    # the DOI must be the article in this journal, not the book a review of the same title is about
                    if norm(ct[0]) == norm(a['t']) and JOURNAL_NAMES.get(a['j'], '\0') in jt:
                        new = u; break
                elif OWN_SITES.get(a['j']) and OWN_SITES[a['j']] in u and slug_ok(u, a['t']):
                    new = u; break
                elif 'works.bepress.com' in u and any(s and s in norm(u) for s in surnames):
                    new = u; break
            if new:
                break
        if new:
            a['u'] = new; fixed.append(a)
        else:
            dropped.append(a)
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
    drop_ids = {a['id'] for a in dropped}
    data['articles'] = [a for a in arts if a['id'] not in drop_ids]
    open('docs/data/articles.js', 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f"book-review titles cleaned: {retitled}; aggregator links: {len(bad)}; replaced with direct links: {len(fixed)}; articles removed: {len(dropped)}; not checked (lookup failed, left as is): {len(unchecked)}")
    for a in fixed:
        print('  fixed  ', a['id'], a['t'][:60], '->', a['u'])
    for a in dropped:
        print('  removed', a['id'], a['t'][:70])


if __name__ == '__main__':
    main()
