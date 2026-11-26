"""CourtListener (Free Law Project) data for the case pages: summaries for cases with none, citation counts for cases the
Caselaw Access Project graph does not reach, and oral-argument audio links.

CourtListener's bulk data and API data are "free of known copyright restrictions" (courtlistener.com/help/api/bulk-data/);
the opinions themselves are public domain. The token is read from .keys.env (COURTLISTENER_TOKEN, via local_keys.py) and
sent only in the Authorization header; it is never printed or written anywhere. Requests are spaced out
(CourtListener's documented limit is about 5,000 an hour, but this token gets 5 a minute and 125 a day: requests
are 13.5 s apart, and a run stops cleanly when the day's quota is gone; rerun the next day to continue).

  summaries  for every case case_summaries.py still leaves without a summary: the case's opinion cluster (by SCDB id,
             else by U.S. Reports citation) and the text of its lead opinion. case_summaries.py build turns them into
             src:'cl' entries: the cluster's syllabus, headnotes or summary field if there is one, else the whole text
             of a short order, else the opening paragraph(s) of the opinion.
  cites      for cases with no CAP impact entry decided after CAP's data ends (October 2019 on): the number of later
             Supreme Court decisions citing the case, from one sweep of CourtListener's search index (each opinion's
             cited opinions). build_case_impact.py merges them.
  audio      CourtListener's oral-argument recordings (which come from the Court), matched to argued cases by docket number
             and term, written to docs/data/cl_audio.js. The case page plays one only when Oyez's live record has no
             argument audio or Oyez cannot be reached. (Checked 2026-11-26: Oyez had audio for all 1,013 matched cases,
             so today this is a fallback only; the local Oyez cache keeps no audio fields, so it cannot tell.)

Caches (gitignored): data/raw/courtlistener/cluster/, data/raw/courtlistener/cites/ (search.json, counts.json),
data/raw/courtlistener/audio/.
Run from the repo root:  python scripts/courtlistener.py summaries|cites|audio
"""
import glob, html, json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_keys  # noqa: E402,F401  (loads .keys.env)

API = 'https://www.courtlistener.com/api/rest/v4/'
RAW = 'data/raw/courtlistener'
GAP = 13.5   # this token is limited to 5 requests a minute and 125 a day
_last = [0.0]


def get(path, **params):
    """GET an API path (or full URL); returns parsed JSON, None on 404. Backs off on 429/5xx."""
    url = path if path.startswith('http') else API + path
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    hdr = {'User-Agent': 'LexConstitutio/1.0 (static site build)', 'Accept': 'application/json',
           'Authorization': 'Token ' + os.environ.get('COURTLISTENER_TOKEN', '')}
    for attempt in range(6):
        wait = _last[0] + GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print('  HTTP', e.code, url.split('?')[0], flush=True)
            if e.code == 404:
                return None
            if e.code in (401, 403):
                raise SystemExit(f'CourtListener refused the request (HTTP {e.code}); check COURTLISTENER_TOKEN')
            wait = int(e.headers.get('Retry-After') or 30) if e.code == 429 else 10 * (attempt + 1)
            if wait > 600:   # the daily quota (125 requests for this token) is used up: stop, so nothing empty is cached
                raise SystemExit(f'CourtListener quota used up; rerun in about {wait // 3600 + 1} h (finished items are cached)')
            time.sleep(wait + 3)
        except Exception as e:
            print('  ', type(e).__name__, url.split('?')[0], flush=True)
            time.sleep(10 * (attempt + 1))
    return None


def fname(cid):
    return cid.replace('/', '_', 1)


def strip_html(t):
    t = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', t or '')
    t = re.sub(r'\s+', ' ', t)   # source line breaks inside paragraphs are not paragraph breaks
    t = re.sub(r'(?i)<a [^>]*class="footnote"[^>]*>.*?</a>|<span [^>]*class="star-pagination"[^>]*>.*?</span>|<footnotemark>.*?</footnotemark>', '', t)
    t = re.sub(r'(?i)</(p|div|h\d|li|blockquote)>|<br\s*/?>', '\n', t)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    t = re.sub(r'(?<=\w)\ufffd(?=\w)', '\u2019', t)   # damaged apostrophes and quotes in some sources
    t = re.sub(r'\ufffd(?=\s?\d)', '\u00a7', t)       # section signs
    t = re.sub(r'(^|(?<=[\s(]))\ufffd', '\u201c', t)
    t = t.replace('\ufffd', '\u201d')
    t = re.sub(r' ?\*\d{1,4} ', ' ', t)               # star paging left in plain text
    return '\n'.join(re.sub(r'[ \t\r\f\v]+', ' ', l).strip() for l in t.split('\n')).strip()


CL_FIELDS = 'id,absolute_url,case_name,scdb_id,date_filed,citation_count,citations,syllabus,headnotes,summary,sub_opinions'
OP_FIELDS = 'id,type,author_str,per_curiam,plain_text,html,html_lawbox,html_columbia,xml_harvard,html_with_citations'


def find_cluster(c):
    """The case's cluster: by SCDB id, else by U.S. Reports citation (checked against a party name)."""
    if c['id'].startswith('scdb/'):
        r = get('clusters/', scdb_id=c['id'][5:], fields=CL_FIELDS) or {}
        if len(r.get('results') or []) == 1:
            return r['results'][0]
    m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
    if not m:
        return None
    r = get('clusters/', citations__volume=m.group(1), citations__reporter='U.S.', citations__page=m.group(2), fields=CL_FIELDS) or {}
    keys = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", c['n']) if w.lower() not in {'united', 'states', 'america', 'company', 'commissioner'}][:3]
    hits = [x for x in r.get('results') or [] if not keys or any(k in (x.get('case_name') or '').lower() for k in keys)]
    return hits[0] if len(hits) == 1 else None


def opinion_text(o):
    for k in ('html_with_citations', 'html_lawbox', 'html_columbia', 'xml_harvard', 'html'):
        if (o.get(k) or '').strip():
            return strip_html(o[k])
    return strip_html(re.sub(r'\n\s*\n', '</p>', o.get('plain_text') or ''))


def fetch_summaries():
    import case_summaries as cs
    os.makedirs(f'{RAW}/cluster', exist_ok=True)
    D = cs.Data()
    D.mine = {}
    have = set(cs.build_cap(D)) | set(cs.build_loc(D)) | set(cs.build_orders(D))
    todo = [c for c in D.cases if D.need(c) and c['id'] not in have and not os.path.exists(f'{RAW}/cluster/{fname(c["id"])}.json')]
    print(len(todo), 'cases to look up on CourtListener', flush=True)
    for k, c in enumerate(todo):
        cl = find_cluster(c)
        rec = {}
        if cl:
            rec = {k2: cl.get(k2) for k2 in ('id', 'absolute_url', 'case_name', 'scdb_id', 'date_filed', 'citation_count', 'syllabus', 'headnotes', 'summary')}
            rec['n_ops'] = len(cl.get('sub_opinions') or [])
            rec['ops'] = []
            for u in (cl.get('sub_opinions') or [])[:3]:
                o = get(u, fields=OP_FIELDS) or {}
                rec['ops'].append({'type': o.get('type'), 'author': o.get('author_str'), 'per_curiam': o.get('per_curiam'), 'text': opinion_text(o)[:12000]})
                if rec['ops'][-1]['type'] in ('010combined', '020lead', '025plurality'):
                    break
        json.dump(rec, open(f'{RAW}/cluster/{fname(c["id"])}.json', 'w', encoding='utf-8'), ensure_ascii=False)
        if k % 25 == 0:
            print(k, '/', len(todo), flush=True)


SINCE = '2019-10-01'   # CAP's citation data ends with the October 2019 Term


def fetch_cites():
    """Later Supreme Court opinions citing each case decided after CAP's data ends. One sweep of CourtListener's search
    index (every Supreme Court cluster filed since October 2019, 20 a page, with each opinion's cited opinions) instead
    of a request per case. n counts the later decisions that cite the case, leaving out decisions citing fewer than
    three cases (one-line orders), as build_case_impact.py does for CAP."""
    import case_summaries as cs
    os.makedirs(f'{RAW}/cites', exist_ok=True)
    path = f'{RAW}/cites/search.json'
    rows = json.load(open(path, encoding='utf-8')) if os.path.exists(path) and '--refresh' not in sys.argv else None
    if rows is None:   # resumable: progress is saved after every page (about 330 pages; 125 requests a day)
        part = path + '.partial'
        rows, url = json.load(open(part, encoding='utf-8')) if os.path.exists(part) else ([], None)
        url = url or (None if rows else API + 'search/?' + urllib.parse.urlencode({'type': 'o', 'court': 'scotus', 'filed_after': SINCE, 'order_by': 'dateFiled asc'}))
        while url:
            r = get(url)
            if r is None:
                raise SystemExit('search sweep failed; rerun to start again')
            for x in r.get('results') or []:
                rows.append({'id': x.get('cluster_id'), 'n': x.get('caseName'), 'date': x.get('dateFiled'), 'dk': x.get('docketNumber'),
                             'cit': x.get('citation') or [], 'scdb': x.get('scdb_id'), 'url': x.get('absolute_url'),
                             'ops': [{'id': o.get('id'), 'cites': o.get('cites') or []} for o in x.get('opinions') or []]})
            url = r.get('next')
            json.dump([rows, url], open(part, 'w', encoding='utf-8'))
            if len(rows) % 500 < 20:
                print(' ', len(rows), 'clusters', flush=True)
        json.dump(rows, open(path, 'w', encoding='utf-8'))
        os.remove(part)
    op_cluster = {o['id']: x['id'] for x in rows for o in x['ops']}
    date = {x['id']: x.get('date') or '' for x in rows}
    cited_by = {}
    for x in rows:
        to = {op_cluster.get(t, -t) for o in x['ops'] for t in o['cites']}
        if len(to) < 3:
            continue
        for t in to:
            if t > 0 and t != x['id'] and date.get(t, '') <= date.get(x['id'], ''):
                cited_by[t] = cited_by.get(t, 0) + 1
    by_us, by_scdb, by_dk = {}, {}, {}
    for x in rows:
        for ct in x['cit']:
            if re.match(r'^\d+ U\.S\. \d+$', ct):
                by_us[ct] = x
        if x.get('scdb'):
            by_scdb[x['scdb']] = x
        by_dk.setdefault((x.get('dk') or '').strip().lower(), []).append(x)
    cases = cs.load_js('docs/data/scotus.js')['cases']
    imp = cs.load_js('docs/data/case_impact.js')['c']
    out = {}
    for c in cases:
        if (c['id'] in imp and len(imp[c['id']]) == 3) or (c.get('dec') or '') < SINCE:
            continue
        x = by_scdb.get(c['id'][5:]) if c['id'].startswith('scdb/') else None
        x = x or by_us.get(c.get('cit') or '')
        if not x:
            hits = [y for y in by_dk.get((c.get('d') or '').strip().lower(), []) if y.get('date') == c.get('dec')]
            x = hits[0] if len(hits) == 1 else None
        if x:
            out[c['id']] = {'cl': x['id'], 'n': cited_by.get(x['id'], 0)}
    json.dump(out, open(f'{RAW}/cites/counts.json', 'w', encoding='utf-8'))
    print(len(rows), 'clusters since', SINCE, '->', len(out), 'cases matched')


def load_cites():
    p = f'{RAW}/cites/counts.json'
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def fetch_audio():
    """Every Supreme Court oral-argument recording CourtListener holds (a few thousand rows, 20 a page), cached whole;
    then docs/data/cl_audio.js for the argued cases whose Oyez record has no argument audio."""
    os.makedirs(f'{RAW}/audio', exist_ok=True)
    path = f'{RAW}/audio/scotus.json'
    rows = json.load(open(path, encoding='utf-8')) if os.path.exists(path) and '--refresh' not in sys.argv else None
    if rows is None:
        rows, url = [], API + 'audio/?' + urllib.parse.urlencode({'docket__court': 'scotus', 'order_by': 'date_created',
                                                                   'fields': 'id,absolute_url,case_name,download_url,local_path_mp3,duration,docket'})
        while url:
            r = get(url) or {}
            rows += r.get('results') or []
            url = r.get('next')
            if len(rows) % 500 < 20:
                print(len(rows), 'recordings', flush=True)
        json.dump(rows, open(path, 'w', encoding='utf-8'))
    import case_summaries as cs
    cases = cs.load_js('docs/data/scotus.js')['cases']
    by_dk = {}
    for x in rows:
        m = re.search(r'/(\d{2,4}-\d+|\d+(?:[-_ ]?orig)?)(?:[_-]\d{4}-\d\d-\d\d)?\.mp3$', x.get('download_url') or '', re.I)
        lp = re.match(r'mp3/(\d{4})/(\d\d)/(\d\d)/', x.get('local_path_mp3') or '')
        if not m or not lp or not x.get('local_path_mp3'):
            continue
        dk = m.group(1).lower().replace('_', '-').replace(' ', '-')
        by_dk.setdefault(dk, []).append({'d': '-'.join(lp.groups()), 'mp3': 'https://storage.courtlistener.com/' + x['local_path_mp3'],
                                         'url': 'https://www.courtlistener.com' + (x.get('absolute_url') or ''), 'dur': x.get('duration'), 'n': x.get('case_name')})
    out = {}
    for c in cases:
        if not c.get('arg') or not c.get('d') or int(str(c.get('t') or 0)[:4]) < 2009:
            continue
        f = f'{cs.OYEZ}/{fname(c["id"])}.json'
        if os.path.exists(f):
            d = json.load(open(f, encoding='utf-8'))
            if [m for m in d.get('oral_argument_audio') or [] if m and m.get('href') and not m.get('unavailable')]:
                continue
        recs = by_dk.get(c['d'].strip().lower())
        if not recs:
            continue
        # a docket number is reused across terms: keep recordings argued within the case's term (Oct of t to Sep of t+1)
        t = int(str(c['t'])[:4])
        recs = [r for r in recs if f'{t}-09-01' <= r['d'] <= (c.get('dec') or f'{t + 1}-09-30')]
        if recs:
            out[c['id']] = [{k: r[k] for k in ('d', 'mp3', 'url', 'dur')} for r in sorted(recs, key=lambda r: r['d'])]
    open('docs/data/cl_audio.js', 'w', encoding='utf-8').write(
        '/* Oral-argument recordings from CourtListener (Free Law Project; recordings by the Supreme Court of the United States). */\n'
        'window.CL_AUDIO=' + json.dumps(out, separators=(',', ':')) + ';')
    print(len(rows), 'recordings;', len(out), 'argued cases matched to a CourtListener recording (played only when Oyez has none)')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    {'summaries': fetch_summaries, 'cites': fetch_cites, 'audio': fetch_audio}[cmd]()
