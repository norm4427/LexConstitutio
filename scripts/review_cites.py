"""Keep citation counts off book reviews, and off articles only when they really are reviews.

A book review is usually titled with the reviewed book's title ("Introduction to the Study of the Law of the
Constitution", a one-page 1915 Harvard Law Review notice of Dicey's book), and citation databases match later
citations of the book to that record: OpenAlex credits the notice with ~900 citing works, nearly all from 2000 on.
Those counts belong to the book, so a review gets none (`cx: 1`; refresh_cites.py and merge_new.py respect it).

The build's old rule flagged every title that appears in more than one journal as a review. That also caught real
articles that were later reviewed under the same title (Thayer's 1893 "Origin and Scope of the American Doctrine
of Constitutional Law"; Powell, "The Original Understanding of Original Intent"; Sullivan, "Unconstitutional
Conditions"). Each candidate is checked against Open Library instead (cached in data/raw/reviewcheck2/):

  review   - a book with the same title by one of the listed authors exists, and the first listed name (the reviewer)
             is not among the book's authors; or
           - a book-length work (120+ pages, or several editions) with exactly that title had appeared by then (an
             article reissued as a short pamphlet, like Thayer's, does not count); or
           - the first listed name is initials only ("C. A. M.", an unsigned-review convention) or a journal
  article  - otherwise; its review flag is removed and its own citation count kept (or restored from the refresh cache)

Candidates: every item flagged as a review, and every unflagged item with two or more listed names and 30+ citations.
Run from the repo root:  python scripts/review_cites.py   (then sh scripts/stamp.sh)
"""
import json, os, re, sys, time, urllib.parse, urllib.request

PATH = 'docs/data/articles.js'
CACHE = 'data/raw/reviewcheck2'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build script)'}
os.makedirs(CACHE, exist_ok=True)


def nt(s):
    s = (s or '').lower()
    s = re.sub(r'^(the|a|an)\s+', '', s)
    return re.sub(r'[^a-z0-9]', '', s)


def main_title(t):
    t = re.sub(r'\s*[\[(].*$', '', t or '')
    return re.split(r':\s|\.\s+(?=[A-Z])', t)[0].strip().rstrip('.')


def last(n):
    n = re.sub(r',?\s+(jr|sr|ii|iii)\.?$', '', (n or '').strip(), flags=re.I)
    p = n.split()
    return re.sub(r'[^a-z]', '', (p[-1] if p else '').lower())


def initials_only(n):
    return bool(re.fullmatch(r'(?:[A-Z]\.\s?){1,4}', (n or '').strip()))


def ol_search(title):
    key = nt(title)[:80]
    p = f'{CACHE}/full_{key}.json'
    if not os.path.exists(p):
        url = 'https://openlibrary.org/search.json?' + urllib.parse.urlencode(
            {'title': title, 'limit': 12, 'fields': 'title,subtitle,author_name,first_publish_year,number_of_pages_median,edition_count'})
        d = None
        for attempt in range(4):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
                break
            except Exception:
                time.sleep(10 * (attempt + 1))
        if d is None:
            return None
        json.dump(d, open(p, 'w', encoding='utf-8'))
        time.sleep(0.8)
    return json.load(open(p, encoding='utf-8')).get('docs') or []


def books(t):
    """Open Library books whose title is this piece's title: the full title (with its subtitle) or, when the main title
    is distinctive (15+ letters) and the piece has no subtitle of its own, the main title."""
    full = nt(re.sub(r'\s*[\[(].*$', '', t))
    mt = nt(main_title(t))
    has_sub = full != mt
    docs = ol_search(re.sub(r'\s*[\[(].*$', '', t))
    if docs is None:
        return None
    if has_sub and len(mt) >= 15:
        more = ol_search(main_title(t))
        docs = docs + (more or [])
    out, seen = [], set()
    for b in docs:
        bt = nt(b.get('title'))
        bfull = nt((b.get('title') or '') + ' ' + (b.get('subtitle') or ''))
        ok = (bfull == full or (len(full) >= 20 and (bfull.startswith(full) or full.startswith(bfull) and len(bfull) >= 20))
              or (bt == mt and len(mt) >= 15 and (not has_sub or not b.get('subtitle'))))
        k = (bt, b.get('first_publish_year'))
        if ok and k not in seen:
            seen.add(k)
            out.append(b)
    return out


def classify(a):
    names = a.get('a') or []
    t = a['t']
    if names and (initials_only(names[0]) or re.search(r'law review|journal|review$', names[0], re.I)) and len(names) >= 2:
        return 'review', 'unsigned or initialled reviewer'
    if re.match(r'^(The )?Supreme Court,? \d{4} Term', t, re.I) or re.search(r'\bv\.?\s', main_title(t)):
        return 'article', 'Term foreword or case name'
    if len(nt(main_title(t))) < 8 and len(nt(t)) < 15:
        return ('review', 'short title, kept as flagged') if a.get('rv') else ('article', 'short title')
    bs = books(t)
    if bs is None:
        return ('review', 'lookup failed, kept as flagged') if a.get('rv') else ('article', 'lookup failed')
    mine = [last(n) for n in names if last(n)]
    y = a.get('y') or 9999
    for b in bs:
        by = b.get('first_publish_year')
        if not by:
            continue
        bauth = {last(n) for n in b.get('author_name') or []}
        shared = [m for m in mine if m in bauth]
        others = [m for m in mine if m not in bauth]
        pages = b.get('number_of_pages_median') or 0
        long_ = pages >= 120 or (not pages and (b.get('edition_count') or 0) >= 2)
        if by > y + 1:
            continue
        if shared and others:
            # the book's author plus someone else (listed in either order): a review of a book out before the piece;
            # a same-year book by the first-listed author is the authors' own work reissued
            if by < y or (by == y and mine[0] not in bauth):
                return 'review', f"reviewer + author of {b.get('title')} ({by})"
            continue
        if shared and not others:
            # the sole listed author's own book: a review if a book-length edition was out before the piece
            if by < y and long_ and pages <= 1200:
                return 'review', f"author's book {b.get('title')} ({by}, {pages or '?'} pp.) predates it"
            continue
        if y - 5 <= by <= y and pages <= 1200 and (pages >= 120 or (not pages and (b.get('edition_count') or 0) >= 2)):
            # a book-length work of exactly this title appeared shortly before: the piece reviews it (an article
            # reissued as a short pamphlet, like Thayer's 1893 "Origin and Scope", does not count)
            return 'review', f"titled like {b.get('title')} ({by}, {pages or '?'} pp.)"
    # looser: a book with the same main title, by a listed author who is not listed first (reviewer + author)
    mt = main_title(t)
    if len(nt(mt)) >= 8 and len(mine) >= 2:
        for b in ol_search(mt) or []:
            by = b.get('first_publish_year')
            bauth = {last(n) for n in b.get('author_name') or []}
            if nt(b.get('title')) == nt(mt) and by and by <= y + 1 and mine[0] not in bauth and any(m in bauth for m in mine[1:]):
                return 'review', f"reviewer + author of {b.get('title')} ({by})"
    return 'article', 'no book of that title shortly before it'


def main():
    raw = open(PATH, encoding='utf-8').read()
    d = json.loads(raw[raw.index('=') + 1:].rstrip().rstrip(';'))
    arts = d['articles']
    refresh = json.load(open('data/raw/cites_refresh.json', encoding='utf-8')) if os.path.exists('data/raw/cites_refresh.json') else {}
    cand = [a for a in arts if a.get('rv') or (len(a.get('a') or []) >= 2 and (a.get('c') or 0) >= 30)]
    print(len(cand), 'items to check', flush=True)
    removed, unflagged, newrev = [], [], []
    twins = {}
    for x in arts:
        twins.setdefault(nt(x['t']), []).append(x.get('y') or 9999)
    for k, a in enumerate(cand):
        kind, why = classify(a)
        if kind == 'article' and a.get('rv'):
            # a flagged piece goes back to being an article only if no other piece has its title, or it is at least a
            # year older than every other piece within three years that does (Thayer's 1893 article, reviewed under its title in 1894)
            y0 = a.get('y') or 9999
            near = [o for o in twins.get(nt(a['t']), []) if abs(o - y0) <= 3]     # pieces on the same book come close together
            if len(near) > 1 and not (near.count(y0) == 1 and all(o > y0 for o in near if o != y0)):
                kind, why = 'review', 'same title as another piece of that year or earlier'
        if kind == 'review':
            if not a.get('rv'):
                a['rv'] = 1
                newrev.append((a.get('c') or 0, a['id'], a['y'], a['t'], why))
            if a.get('c') is not None:
                removed.append((a['c'], a['id'], a['y'], a['t'], why))
                del a['c']
            a['cx'] = 1
        elif a.get('rv'):
            del a['rv']
            a.pop('cx', None)
            if a.get('c') is None and (refresh.get(a['id']) or {}).get('c') is not None:
                a['c'] = refresh[a['id']]['c']
            unflagged.append((a.get('c') or 0, a['id'], a['y'], a['t'], why))
        if k % 100 == 0:
            print(f'  {k}/{len(cand)}', flush=True)
    open(PATH, 'w', encoding='utf-8').write(raw[:raw.index('=') + 1] + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
    for label, rows in (('citation counts removed from reviews', removed), ('newly identified reviews', newrev),
                        ('wrongly flagged reviews restored as articles', unflagged)):
        rows.sort(key=lambda x: -x[0])
        print(f'\n{len(rows)} {label}; largest:')
        for c, i, y, t, why in rows[:25]:
            print(f'  {c:5} {i:16} {y} {t[:58]}  ({why})')


if __name__ == '__main__':
    main()
