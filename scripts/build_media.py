"""Build the case pages' "In the media" tab: docs/data/media/<term>.js (window.MEDIA[<case id>]) and media-index.js.

Inputs (scripts/media_fetch.py): podcast episodes (data/raw/media/yt), YouTube searches for older cases
(data/raw/media/search, when run with an API key), Chronicling America newspaper pages (data/raw/media/loc), and the
site's own lecture videos (docs/data/lectures.js).

Matching errs on the side of leaving an episode out. An episode is attached to a case only when
  - a chapter line of its description (a timestamp followed by a topic) names the case: both distinctive party names
    with "v." between them, or a party name that no other case decided within three years shares (the episode then
    starts at that timestamp); or
  - its title names the case the same way (start at 0); or
  - its description names the case in full ("Loper Bright Enterprises v. Raimondo", or both party names joined by "v.");
and the episode was published between 18 months before and 15 months after the decision (pending cases: since the
grant, or the start of the Term). Videos whose owners disallow embedding are kept as links.
Other videos (searches, lectures) must name the case in full in their title.
Newspaper pages: Chronicling America pages printed in the weeks after the decision (two months before 1870) that contain
both party names and "supreme court"; the Library of Congress page and its scan are linked, nothing is copied.
Run from the repo root:  python scripts/build_media.py
"""
import collections, glob, json, os, re
from datetime import date, timedelta

RAW = 'data/raw/media'
OUT = 'docs/data/media'
GENERIC = set('united states state states city county commissioner people secretary attorney general board department commonwealth '
              'town village school district government federal national american the of in re ex parte matter inc co corp company '
              'corporation association et al new york california texas ohio pennsylvania virginia illinois georgia florida '
              'trump biden obama president first second little brown white black green young king long free'.split())
CHAPTER = re.compile(r'^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*[-–—:|]?\s*(.+?)\s*$')


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def secs(ts):
    p = [int(x) for x in ts.split(':')]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def sides(name):
    m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+?)(?:\s*\(\d\))?$', name)
    if not m:
        return None
    words = lambda s: [w for w in re.findall(r"[A-Z][A-Za-z'’\-]{3,}", s) if w.lower() not in GENERIC]
    return words(m.group(1)), words(m.group(2))


def main():
    S = load_js('docs/data/scotus.js')['cases']
    K = load_js('docs/data/docket.js')
    cases = [c for c in S if c.get('dec') and c.get('s') != 1 and ' v. ' in c['n']]
    pend = [{'id': e['id'], 'n': e['n'], 't': e.get('t'), 'pending': True, 'from': e.get('granted') or f"{int(e.get('t') or 2026)}-07-01"} for e in K['cases']]
    allc = cases + pend
    # distinctive words, and how many cases within three years share each
    info = {}
    by_word = collections.defaultdict(list)
    for c in allc:
        sd = sides(c['n'])
        if not sd:
            continue
        d = date.fromisoformat(c['dec']) if c.get('dec') else date.fromisoformat(c['from'])
        info[c['id']] = (sd, d)
        for w in set(sd[0][:1] + sd[1][:1]):
            by_word[w].append(d)
    # a party name used alone must not be an ordinary English word ("Justice", "Service", "Employee"): words that
    # occur in lower case in the merits briefs are excluded
    common = collections.Counter()
    for p in sorted(glob.glob('data/raw/briefs/*/petitioner.txt'))[::3]:
        common.update(re.findall(r'\b[a-z]{4,}\b', open(p, encoding='utf-8', errors='replace').read()))

    def unique_word(w, d):
        return len(w) >= 5 and common[w.lower()] < 3 and sum(1 for x in by_word[w] if abs((x - d).days) < 3 * 365) == 1

    def full_rx(c):
        sd, _ = info[c['id']]
        alts = [re.escape(re.sub(r'\s*\(\d\)$', '', c['n']))]
        if sd[0] and sd[1]:
            alts.append(r'\b' + re.escape(sd[0][0]) + r'\b[^\n.]{0,60}?\bv(?:s)?\.?\s[^\n]{0,60}?\b' + re.escape(sd[1][0]) + r'\b')
        return re.compile('|'.join(alts))

    def short_rx(c):
        sd, d = info[c['id']]
        ws = [w for w in (sd[0][:1] + sd[1][:1]) if unique_word(w, d)]
        return re.compile(r'\b(?:' + '|'.join(map(re.escape, ws)) + r")(?:['’]s)?\b") if ws else None

    media = collections.defaultdict(lambda: {'videos': [], 'print': []})
    # --- podcast episodes
    vids = [json.load(open(p, encoding='utf-8')) for p in glob.glob(f'{RAW}/yt/*.json')]
    recent = [c for c in allc if c['id'] in info and (c.get('pending') or c['dec'] >= '2015-01-01')]
    rx = {c['id']: (full_rx(c), short_rx(c)) for c in recent}
    for v in vids:
        if not v.get('date'):
            continue
        vd = date.fromisoformat(v['date'])
        chapters = [(secs(m.group(1)), m.group(2)) for m in (CHAPTER.match(l) for l in v.get('desc', '').split('\n')) if m]
        for c in recent:
            _, d = info[c['id']]
            lo, hi = (d - timedelta(days=30), d + timedelta(days=700)) if c.get('pending') else (d - timedelta(days=540), d + timedelta(days=460))
            if not (lo <= vd <= hi):
                continue
            fr, sr = rx[c['id']]
            hit = None
            for t, topic in chapters:
                if fr.search(topic) or (sr and sr.search(topic)):
                    hit = (t, topic); break
            if not hit and (fr.search(v['t']) or (sr and sr.search(v['t']))):
                hit = (0, '')
            if not hit and fr.search(v.get('desc', '')):
                hit = (0, '')
            if hit:
                media[c['id']]['videos'].append({'id': v['id'], 't': v['t'], 'ch': v.get('show') or v.get('ch'), 'by': v.get('ch'), 'date': v['date'],
                                                 'start': hit[0], 'topic': hit[1][:140], 'sec': v.get('sec') or 0, 'embed': v.get('embed', True)})
    # --- other videos: site lectures and searches, title must name the case in full
    older = [c for c in cases if c['id'] in info]
    orx = [(c, full_rx(c)) for c in older]
    L = load_js('docs/data/lectures.js')['videos']
    extra = [{'id': v['id'], 't': v['t'], 'ch': v['ch'], 'sec': v.get('sec') or 0, 'date': ''} for v in L]
    for p in glob.glob(f'{RAW}/search/*.json'):
        cid = os.path.basename(p)[:-5]
        for v in json.load(open(p, encoding='utf-8')):
            extra.append(dict(v, sec=0, only=cid))
    for v in extra:
        for c, r in orx:
            if v.get('only') and v['only'] != c['id'].replace('/', '_'):
                continue
            if r.search(v['t']) and not any(x['id'] == v['id'] for x in media[c['id']]['videos']):
                media[c['id']]['videos'].append({'id': v['id'], 't': v['t'], 'ch': v['ch'], 'by': v['ch'], 'date': v.get('date', ''), 'start': 0, 'topic': '', 'sec': v['sec'], 'embed': True})
    # --- newspapers
    S_by_key = {c['id'].replace('/', '_'): c for c in S}
    for p in glob.glob(f'{RAW}/loc/*.json'):
        r = json.load(open(p, encoding='utf-8'))
        c = S_by_key.get(os.path.basename(p)[:-5])
        if not c or not r.get('results'):
            continue
        for x in r['results']:
            if not x.get('date') or not (r['from'] <= x['date'] <= r['to']):
                continue
            paper = re.sub(r'\s+\d{4}-\d{4}$|\s+\d{4}-current$', '', (x.get('paper') or re.sub(r'^Image \d+ of ', '', x.get('title') or '')).strip())
            pg = re.match(r'Image (\d+) of', x.get('title') or '')
            media[c['id']]['print'].append({'date': x['date'], 'paper': paper.title() if paper.islower() else paper, 'page': int(pg.group(1)) if pg else None,
                                            'url': re.sub(r'&q=.*$', '', x['url']) if x.get('url') else None, 'img': x.get('img')})
        media[c['id']]['print'].sort(key=lambda x: x['date'])
        media[c['id']]['print'] = media[c['id']]['print'][:8]
    # --- write by term
    tmap = {c['id']: str(c.get('t')) for c in allc}
    by_term = collections.defaultdict(dict)
    n = collections.Counter()
    for cid, m in media.items():
        if not (m['videos'] or m['print']):
            continue
        m['videos'].sort(key=lambda v: (v['date'] or '9999'), reverse=False)
        by_term[tmap.get(cid, 'x')][cid] = m
        n['cases'] += 1; n['videos'] += len(m['videos']); n['print'] += len(m['print'])
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(f'{OUT}/*.js'):
        os.remove(f)
    for t, recs in by_term.items():
        open(f'{OUT}/{t}.js', 'w', encoding='utf-8').write('window.MEDIA=window.MEDIA||{};Object.assign(window.MEDIA,' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');')
    open('docs/data/media-index.js', 'w', encoding='utf-8').write('window.MEDIA_INDEX=' + json.dumps(sorted(set(cid for r in by_term.values() for cid in r)), separators=(',', ':')) + ';')
    print(dict(n))


if __name__ == '__main__':
    main()
