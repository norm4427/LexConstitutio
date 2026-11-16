"""Add recent pieces from journals whose index entries stop where their JSTOR archive does, read from each journal's own
website, with a direct link to the piece's page there (and its PDF). The same treatment hlr_site.py gives Harvard Law Review.

Journals: Yale Law Journal, University of Pennsylvania Law Review, Columbia Law Review, Virginia Law Review, California Law
Review, Stanford Law Review, Harvard Journal of Law & Public Policy. Each site is read through its own list of pieces (site
map, archive pages or volume tables of contents); each piece's page (or table-of-contents row) gives title, authors, volume,
issue, date, piece type, topic tags, a summary or abstract where the site has one, and the PDF. Pages are cached in
data/raw/journal_sites/<journal>/ (one request a second per site).

Pieces are kept and tagged with the same rules as every other journal (hlr_site.py / build.ps1). A piece already in the
index (same journal, title and volume) is not added twice: it gains `pub`, the link to its page on the journal's site.
Run from the repo root after hlr_site.py:  python scripts/journal_sites.py [journal ...] [--cached]
"""
import hashlib, html, json, os, re, sys, threading, time, unicodedata, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from hlr_site import CONLAW, SUBJECTS, JUNK, taxonomy, topics, norm

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
CACHED = '--cached' in sys.argv


def get(jid, url):
    d = f'data/raw/journal_sites/{jid}'
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, hashlib.md5(url.encode()).hexdigest() + '.html')
    if os.path.exists(f):
        return open(f, encoding='utf-8').read()
    if CACHED:
        return ''
    err = None
    for n in range(3):
        try:
            time.sleep(1 + 5 * n)
            s = urllib.request.urlopen(urllib.request.Request(urllib.parse.quote(url, safe=':/?&=%#+,;~'), headers=UA), timeout=60).read().decode('utf-8', 'ignore')
            open(f, 'w', encoding='utf-8').write(s)
            return s
        except Exception as e:
            err = e
            if getattr(e, 'code', 0) == 404:
                break
    print(f'  [{jid}] failed {url}: {err}')
    return ''


def text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def one(rx, s):
    m = re.search(rx, s, re.S)
    return m.group(1) if m else ''


def locs(xml):
    return [html.unescape(u) for u in re.findall(r'<loc>(?:<!\[CDATA\[)?([^<\]]+)', xml)]


def meta(page, prop):
    return html.unescape(one(r'<meta (?:property|name)="' + prop + r'"[^>]*content="([^"]*)"', page)).strip()


def year_of(s):
    m = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', s or '')
    return int(m.group(1)) if m else None


def split_authors(s):
    s = re.sub(r'^\s*by\s+', '', text(s), flags=re.I).replace('*', '').replace('†', '').replace('‡', '')
    parts = re.split(r'\s*(?:,\s*and\s+|\s+and\s+|\s*&\s*|,\s*)\s*', s)
    return [p.strip() for p in parts if p.strip() and not re.fullmatch(r'(Jr|Sr|II|III|IV)\.?', p.strip())]


# ------------------------------------------------------------------------------------------------ per-journal readers
def yale_list(jid):
    urls = set()
    for kind in ('article', 'essay', 'note', 'review', 'comment', 'feature', 'lecture', 'tribute', 'introduction', 'atkins-feature'):
        first = get(jid, f'https://yalelawjournal.org/issue/{kind}')
        last = max([int(n) for n in re.findall(r'[?&]page=(\d+)', first)] or [1])
        # every archive page up to the last one the pagination names (a page that fails is retried on the next run,
        # never taken as the end of the list)
        for page in range(1, last + 1):
            s = first if page == 1 else get(jid, f'https://yalelawjournal.org/issue/{kind}?page={page}')
            urls |= set(re.findall(r'href="(https://yalelawjournal\.org/(?:' + kind + r')/[^"/?#]+)"', s))
    return sorted(urls)


def yale_parse(url, p):
    head = one(r'(<h1.*?)(?:download-pdf-btn|content_html_wrap)', p)
    t = text(one(r'<h1[^>]*>(.*?)</h1>', p))
    a = [text(x) for x in re.findall(r'href="https://yalelawjournal\.org/author/[^"]+"[^>]*>(.*?)</a>', head)]
    v = one(r'text-lg uppercase">\s*(\d{2,3})\s*</div>', p)
    tags = [text(x) for x in re.findall(r'href="/explore/[^"]+"[^>]*>(.*?)</a>', head)]
    kind = text(one(r'href="https://yalelawjournal\.org/issue/[a-z-]+" class="hover:underline">(.*?)</a>', p))
    pdf = one(r'href="(https://yalelawjournal\.org/pdf/[^"]+\.pdf)"', p)
    ab = meta(p, 'og:description')
    if ab.endswith('...'):           # Yale's page description is its abstract cut at 160 characters: keep the whole sentences
        ab = re.sub(r'(?<=[.!?])[^.!?]*\.\.\.$', '', ab).strip() if re.search(r'[.!?]\s', ab) else ''
    return dict(t=t, a=a, v=int(v) if v else None, y=year_of(meta(p, 'article:published_time')), kind=kind, tags=tags, ab=ab, pdf=pdf)


def penn_list(jid):
    out = []
    for sm in ('post-sitemap', 'post-sitemap2'):
        out += [u for u in locs(get(jid, f'https://pennlawreview.com/{sm}.xml')) if re.search(r'/20\d\d/\d\d/\d\d/[^/]+/$', u)]
    return out


def penn_parse(url, p):
    t = text(one(r'class="wp-block-post-title">(.*?)</h1>', p))
    a = [text(x) for x in re.findall(r'<p class="article-author[^"]*">(.*?)</p>', p)]
    a = [n for x in a for n in split_authors(x)]
    data = text(one(r'<p class="article-data">(.*?)</p>', p))
    v, i = one(r'Volume (\d+)', data), one(r'Issue (\d+)', data)
    kind = text(one(r'</br>\s*<span>(.*?)</span>', one(r'<p class="article-data">(.*?)</p>', p)))
    pdf = html.unescape(one(r'<li class="view-pdf"><a href="([^"]+)"', p))
    return dict(t=t, a=a, v=int(v) if v else None, i=int(i) if i else None, y=year_of(data), kind=kind, tags=[],
                ab=meta(p, 'og:description'), pdf=pdf)


def col_list(jid):
    return [u for u in locs(get(jid, 'https://columbialawreview.org/content-sitemap.xml')) if re.search(r'/content/[^/]+/$', u)]


def col_parse(url, p):
    t = text(one(r'<h1 class="page-title">(.*?)</h1>', p))
    if t.isupper():
        from titlecase import titlecase
        t = titlecase(t)
    a = split_authors(one(r'<h3 class="single-content-author">(.*?)</h3>', p))
    v, i = one(r'class="vol-number">Vol\. (\d+)', p), one(r'class="issue-numb">No\. (\d+)', p)
    kind = text(one(r'<h5 class="content-type">(.*?)</h5>', p))
    ab = text(one(r'<div class="content-abstract">(.*?)</div>', p))
    ab = re.sub(r'^Abstract\s*', '', ab)
    real = bool(ab)
    pdf = one(r'href="(https://columbialawreview\.org/wp-content/uploads/[^"]+\.pdf)"', p)
    tags = [text(x) for x in re.findall(r'href="https://columbialawreview\.org/topic/[^"]+"[^>]*>(.*?)</a>', p)][:6]
    return dict(t=t, a=a, v=int(v) if v else None, i=int(i) if i else None, y=1900 + int(v) if v else None, kind=kind,
                tags=tags, ab=ab, pdf=pdf, real=real)


def va_list(jid):
    out = []
    for sm in ('articles-sitemap', 'articles-sitemap2'):
        out += [u for u in locs(get(jid, f'https://virginialawreview.org/{sm}.xml')) if re.search(r'/articles/[^/]+/$', u)]
    return out


def va_parse(url, p):
    t = text(one(r'<h1 class="essay-title">(.*?)</h1>', p))
    a = split_authors(re.sub(r'<sup.*?</sup>', '', one(r'<h3 class="article-authors">(.*?)</h3>', p), flags=re.S))
    sub = text(one(r'<h3 class="article-sub-header">(.*?)</h3>', p))
    v, i = one(r'Volume (\d+)', sub), one(r'Issue (\d+)', sub)
    kind = sub.split('—')[0].strip() if '—' in sub else ''
    ref = text(one(r'<div class="article-reference">(.*?)</div>', p))
    fp = one(r'Rev\. (?:Online )?(\d+)$', ref)
    pdf = one(r'<div class="download-article-pdf">\s*<a href="([^"]+)"', p)
    return dict(t=t, a=a, v=int(v) if v else None, i=int(i) if i else None, fp=int(fp) if fp else None,
                y=int(v) + 1914 if v else None, kind=kind, tags=[],
                ab=meta(p, 'og:description'), pdf=pdf, online='online' in kind.lower())


def cal_list(jid):
    return [u for u in locs(get(jid, 'https://www.californialawreview.org/sitemap.xml'))
            if re.search(r'californialawreview\.org/(print|online)/[^/]+$', u) and '/category/' not in u]


def cal_parse(url, p):
    t = text(one(r'<h1 class="entry-title[^"]*"[^>]*>(.*?)</h1>', p))
    cats = [html.unescape(c) for c in re.findall(r'class="blog-item-category blog-item-category--([^"]+)"', p)]
    v = next((re.sub(r'\D', '', c) for c in cats if re.fullmatch(r'Volume \d+', c)), '')
    kinds = {'Article', 'Note', 'Essay', 'Book Review', 'Review', 'Comment', 'Symposium', 'Lecture', 'Response', 'Foreword', 'Tribute'}
    kind = next((c for c in cats if c in kinds), '')
    a = [c for c in cats if c not in kinds and not re.fullmatch(r'Volume \d+|(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}|Online|Print', c)
         and len(c.split()) in (2, 3, 4) and not re.search(r'\d|Issue|Symposium|Online|Law|Review', c)]
    pdf = one(r'href="(/s/[^"]+\.pdf)"', p)
    month = next((c for c in cats if re.fullmatch(r'[A-Z][a-z]+ \d{4}', c)), '')
    return dict(t=t, a=a, v=int(v) if v else None, y=year_of(month) or year_of(meta(p, 'datePublished') or one(r'"datePublished":"([^"]+)"', p)),
                kind=kind, tags=[], ab=meta(p, 'og:description'), pdf=('https://www.californialawreview.org' + pdf) if pdf else None,
                online='/online/' in url)


def slr_list(jid):
    out = [u for u in locs(get(jid, 'https://www.stanfordlawreview.org/print_issue-sitemap.xml')) if '/print/article/' in u]
    out += [u for u in locs(get(jid, 'https://www.stanfordlawreview.org/post-sitemap.xml')) if re.search(r'/online/[^/]+/$', u)]
    return out


def slr_parse(url, p):
    t = text(one(r'<h1 class="h1 page-title">(.*?)</h1>', p))
    a = [n for x in re.findall(r'<h3 class="hsa-author[^"]*"[^>]*>(.*?)</h3>', p, re.S) for n in split_authors(re.sub(r'\s\*\s*$', '', text(x)))]
    vi = text(one(r'<a href="/print/volume-\d+/[^"]*">(.*?)</a>', p))
    v, i = one(r'Volume (\d+)', vi), one(r'Issue (\d+)', vi)
    if not v:
        v = one(r'/online/category/(\d+)/', p) or one(r'/online/volume-(\d+)', p)
    real = text(one(r'<div class="article-abstract[^"]*">(.*?)</div>', p))
    ab = real or meta(p, 'og:description')
    pdf = one(r'href="(https?://(?:www\.stanfordlawreview\.org|review\.law\.stanford\.edu)/wp-content/uploads/[^"]+\.pdf)"', p)
    y = int(v) + 1948 if v else None
    kind = text(one(r'<h4 class="hsa-type">(.*?)</h4>', p))
    return dict(t=t, a=a, v=int(v) if v else None, i=int(i) if i else None, y=y, kind=kind,
                tags=[], ab=re.sub(r'^Abstract\s*', '', ab), pdf=pdf, online='/online/' in url, real=bool(real))


def jlpp_rows(jid):
    """the Journal's site has no page per article: each volume's page is a table of contents (first page, title linked
    to the PDF, authors). Returns parsed pieces directly."""
    arch = get(jid, 'https://journals.law.harvard.edu/jlpp/print-archive/')
    vols = sorted(set(re.findall(r'https://journals\.law\.harvard\.edu/jlpp/volume-[0-9-]+/', arch)))
    out = []
    for vu in vols:
        v = int(re.search(r'volume-(\d+)', vu).group(1))
        s = get(jid, vu)
        for row in re.findall(r'<tr>(.*?)</tr>', s, re.S):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(cells) < 3:
                continue
            m = re.search(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', cells[1], re.S)
            if not m:
                continue
            fp = re.sub(r'\D', '', text(cells[0]))
            out.append(dict(url=m.group(1).replace('http://', 'https://'), t=text(m.group(2)), a=split_authors(cells[2]), v=v,
                            fp=int(fp) if fp else None, y=v + 1977, kind='', tags=[], ab='', pdf=m.group(1).replace('http://', 'https://')))
    return out


JOURNALS = {
    'ylj': (yale_list, yale_parse), 'pennlr': (penn_list, penn_parse), 'colr': (col_list, col_parse),
    'valr': (va_list, va_parse), 'calr': (cal_list, cal_parse), 'slr': (slr_list, slr_parse), 'hjlpp': (jlpp_rows, None),
}


def clr_list(jid):
    """Cornell Law Review's site (its repository stops in 2020): every post in its WordPress site map."""
    base = 'https://publications.lawschool.cornell.edu/lawreview/'
    idx = get(jid, base + 'wp-sitemap.xml')
    out = []
    for sm in [u for u in locs(idx) if 'wp-sitemap-posts-post-' in u]:
        out += [u for u in locs(get(jid, sm)) if re.search(r'/lawreview/20\d\d/\d\d/\d\d/[^/]+/$', u)]
    return out


def clr_parse(url, p):
    head = one(r'<div class="article-head">(.*?)<div class="share">', p)
    cats = re.findall(r'category-([a-z0-9-]+)', one(r'(<article id="post-\d+" class="[^"]*")', p))
    kinds = {'articles': 'Article', 'notes': 'Note', 'essay': 'Essay', 'essays': 'Essay', 'symposium': 'Symposium',
             'book-reviews': 'Book Review', 'responses': 'Response'}
    kind = next((kinds[c] for c in cats if c in kinds), '')
    if not head or not kind:
        return dict(t='')                # news, mastheads, announcements and the like
    vol = next((re.findall(r'\d+', c)[-1] for c in cats if re.fullmatch(r'(?:issue-\d+-)?(?:print|online)-volume-\d+', c)), None)
    t = text(one(r'<h2>(.*?)</h2>', head))
    # the author block is either bold names, or one paragraph per author ("Name, title and school"), sometimes with the
    # title in its own paragraph: keep the names, never the job titles
    block = one(r'<p class="author">(.*?)<p class="tags">', head) or ''
    a = [text(x) for x in re.findall(r'<strong>(.*?)</strong>', block, re.S)]
    if not a:
        a = [text(x).split(',')[0].strip() for x in re.findall(r'<p>(.*?)</p>', block, re.S)]
    a = [x for x in a if 2 <= len(x.split()) <= 5 and not re.search(
        r'Professor|Law\b|University|School|Candidate|Class of|J\.D\.|Fellow|Dean|Director|Chair|Judge|Partner|Associate|Lecturer|Counsel|Editor', x)]
    tags = [text(x) for x in re.findall(r'rel="tag">(.*?)</a>', head)][:6]
    pdf = one(r'href="(https://publications\.lawschool\.cornell\.edu/lawreview/wp-content/uploads/[^"]+\.pdf)"', p)
    return dict(t=t, a=a, v=int(vol) if vol else None, y=year_of(text(one(r'<p class="date">(.*?)</p>', head))) or year_of(url),
                kind=kind, tags=tags, ab=meta(p, 'og:description'), pdf=pdf, online='online-volume' in ' '.join(cats))


def clip_sentences(s, n):
    """a long opening cut at the last full sentence before n characters (with an ellipsis), never mid-sentence."""
    if len(s) <= n:
        return s
    ends = [m.end() for m in re.finditer(r'(?<!\bv)(?<!\b[A-Z])(?<!\bNo)(?<!\bU\.S)[.!?]["”’)]?(?=\s)', s[:n])]
    return (s[:ends[-1]] + ' …') if ends and ends[-1] > n // 3 else ''


def glj_list(jid):
    """Georgetown Law Journal: each piece is a page under in-print/volume-N/<issue>/ in its WordPress site map."""
    base = 'https://www.law.georgetown.edu/georgetown-law-journal/'
    out = []
    for sm in [u for u in locs(get(jid, base + 'wp-sitemap.xml')) if 'wp-sitemap-posts-page-' in u]:
        out += [u for u in locs(get(jid, sm)) if re.search(r'/in-print/volume-\d+/[^/]+/[^/]+/$', u)]
    return out


def glj_parse(url, p):
    t = text(one(r'class="abstract_alt_volume_title">(.*?)</h1>', p))
    a = split_authors(one(r'<div class="published_author">(.*?)</div>', p))
    v = one(r'is_volume">\s*<div class="journal_meta_box_content">\s*Volume (\d+)', p) or one(r'/in-print/volume-(\d+)/', url)
    i = one(r'Issue</div>\s*</div>\s*<div class="journal_meta_box_content">\s*(\d+)', p)
    y = one(r'Date</div>\s*</div>\s*<div class="journal_meta_box_content">\s*(\d{4})', p)
    body = re.sub(r"<span class='js-footnote footnote'>.*?</cite>\s*</span>", '', one(r'<div class="abstract_alt_description[^"]*">(.*?)</section>', p), flags=re.S)
    ab = text(body)
    pdf = one(r'href="(https://www\.law\.georgetown\.edu/georgetown-law-journal/wp-content/uploads/[^"]+\.pdf)"', p)
    return dict(t=t, a=a, v=int(v) if v else None, i=int(i) if i else None, y=int(y) if y else (int(v) + 1912 if v else None),
                kind='', tags=[], ab=clip_sentences(ab, 1200), pdf=pdf)


JOURNALS.update({'clr': (clr_list, clr_parse), 'glj': (glj_list, glj_parse)})
NO_VOLUMES = {'clr'}       # sites that give no volume: pieces are matched to the index by title alone


def harvest(jid, results):
    lister, parser = JOURNALS[jid]
    if parser is None:
        results[jid] = lister(jid)
    else:
        urls = sorted(set(lister(jid)))
        print(f'[{jid}] {len(urls)} pieces listed', flush=True)
        out = []
        for k, u in enumerate(urls):
            p = get(jid, u)
            if not p:
                continue
            try:
                d = parser(u, p)
            except Exception as e:
                print(f'  [{jid}] could not read {u}: {e}')
                continue
            d['url'] = u
            d['t'] = re.sub(r"\s+(?=[’']s\b)", '', d.get('t') or '')
            if d['t']:
                out.append(d)
            if k and k % 250 == 0:
                print(f'  [{jid}] {k}/{len(urls)} pages read', flush=True)
        results[jid] = out
    print(f'[{jid}] {len(results[jid])} pieces read', flush=True)


def main():
    want = [a for a in sys.argv[1:] if not a.startswith('--')] or list(JOURNALS)
    results = {}
    threads = [threading.Thread(target=harvest, args=(j, results)) for j in want]   # one polite stream per site
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    os.makedirs('data/raw/journal_sites', exist_ok=True)
    json.dump(results, open('data/raw/journal_sites/pieces.json', 'w', encoding='utf-8'), ensure_ascii=False)

    path = 'docs/data/articles.js'
    raw = open(path, encoding='utf-8').read()
    d = json.loads(raw.split('=', 1)[1].rstrip().rstrip(';'))
    prefix = {j: f'{j}s-' for j in want}
    arts = [a for a in d['articles'] if not any(a['id'].startswith(p) for p in prefix.values())]
    tax = taxonomy()
    for jid in want:
        have = {}
        for a in arts:
            if a['j'] == jid:
                a.pop('pub', None)
                vk = None if jid in NO_VOLUMES else a.get('v')
                have[(norm(a['t']), vk)] = a
                have.setdefault((norm(re.split(r'[:.?]', a['t'])[0]), vk), a)
        added = linked = skipped = 0
        seen = set()
        for p in results.get(jid, []):
            if JUNK.search(p['t']) or (not p.get('v') and jid not in NO_VOLUMES) or not p.get('y') or len(p['t']) < 6:
                continue
            pv = None if jid in NO_VOLUMES else p.get('v')
            key = (norm(p['t']), pv)
            if key in seen:
                continue
            seen.add(key)
            old = have.get(key) or have.get((norm(re.split(r'[:.?]', p['t'])[0]), pv))
            if old:
                if p['url'] not in (old.get('u') or '') and p['url'] != old.get('pdf'):
                    if 'doi.org/' in (old.get('u') or ''):
                        old['pub'] = p['url']        # shown beside the JSTOR/DOI link
                    else:
                        old['u'] = p['url']          # a stray page (a faculty profile ...) gives way to the journal's own
                linked += 1
                continue
            subj = ' | '.join(p.get('tags', []) + [p.get('kind') or ''])
            hits = {h.lower() for h in CONLAW.findall(p.get('ab') or '')}
            if not (SUBJECTS.search(subj) or CONLAW.search(p['t']) or len(hits) >= 2):
                skipped += 1
                continue
            a = {'a': p['a'], 'ab': p.get('ab') or '', 'id': prefix[jid] + hashlib.md5(p['url'].encode()).hexdigest()[:8], 'j': jid,
                 't': p['t'], 'tp': topics(tax, p['t'], subj, p.get('ab') or ''), 'u': p['url'], 'y': p['y']}
            if p.get('v'):
                a['v'] = p['v']
            if a['ab'] and not p.get('real'):      # a site summary or page description, not the piece's abstract
                a['abx'] = 1
            for k in ('i', 'fp', 'pdf'):
                if p.get(k):
                    a[k] = p[k]
            if re.search(r'book review|review essay', p.get('kind') or '', re.I):
                a['rv'] = 1
            if p.get('tags'):
                a['kw'] = p['tags'][:6]
            arts.append(a)
            added += 1
        print(f'{jid}: {len(results.get(jid, []))} pieces read; {added} constitutional-law pieces added; {linked} already in the index; {skipped} on other subjects left out')
    d['articles'] = arts
    for j in d['journals']:
        j['count'] = sum(1 for a in arts if a['j'] == j['id'])
    open(path, 'w', encoding='utf-8').write(raw.split('=', 1)[0] + '=' + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
