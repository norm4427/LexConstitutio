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
CHAPTER_END = re.compile(r'^\s*(.{4,140}?)\s*[-–—:|(\[]\s*((?:\d{1,2}:)?\d{1,2}:\d{2})[\])]?\s*$')
READING = re.compile(r'\(\d{4}\)|\b\d+ U\.\s?S\.|\b\d+ (?:S\. ?Ct|F\.\d?d?|F\. Supp)|Cir\.|\bet al\.|Order,|Brief|Opinion,|Petition|https?://|\bLII\b', re.I)

STARTERS = set('The A An In On At And Plus But About After Before With Why How What When Can Does Is Are Will Did Should Today This That '
               'Inside Breaking Episode Part Live Bonus Interview Also Then Meanwhile Finally Is Was'.split())


def sr_ok(sr, text, name):
    """A party name used alone counts only when it is not part of a longer proper name ("Amy Coney Barrett",
    "Follow Peter"): the words beside it must not be capitalized, unless they belong to the case name itself."""
    own = set(re.findall(r"[A-Za-z'’]+", name))
    for m in sr.finditer(text):
        before = re.findall(r"([A-Za-z'’@]+)\W*$", text[:m.start()])
        after = re.findall(r"^\W*([A-Za-z'’@(]+)", text[m.end():])
        b = before[0] if before else ''
        a = after[0] if after else ''
        cap = lambda w: bool(re.match(r"[A-Z@(]", w)) and w not in own
        if (b and cap(b) and b not in STARTERS and not re.search(r'[.!?:—–-]\s*$', text[:m.start()])) or (a and cap(a)):
            continue
        return True
    return False


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


def raw_sides(name):
    """The first capitalized word of each side, common or short ones included ("Trump", "Roy"): for full-name patterns
    of a case that has at least one distinctive party name."""
    m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+?)(?:\s*\(\d\))?$', name)
    if not m:
        return None
    first = lambda s: next((w for w in re.findall(r"[A-Z][A-Za-z'’\-]{2,}", s) if w.lower() not in ('the', 'inc', 'ltd', 'llc', 'corp')), None)
    a, b = first(m.group(1)), first(m.group(2))
    return (a, b) if a and b else None


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
        ws = [w for w in (sd[0][:1] or sd[1][:1]) if unique_word(w, d)
              and not re.search(r'\b(?:City|County|Town|Village|Borough|Township|Parish|District|Port|State) of ' + re.escape(w), c['n'])]
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
                if fr.search(topic) or (sr and sr_ok(sr, topic, c['n']) and ' v. ' not in topic):
                    hit = (t, topic); break
            if not hit and (fr.search(v['t']) or (sr and sr_ok(sr, v['t'], c['n']))):
                hit = (0, '')
            if not hit and fr.search(v.get('desc', '')):
                hit = (0, '')
            if hit:
                media[c['id']]['videos'].append({'id': v['id'], 't': v['t'], 'ch': v.get('show') or v.get('ch'), 'by': v.get('ch'), 'date': v['date'],
                                                 'start': hit[0], 'topic': hit[1][:140], 'sec': v.get('sec') or 0, 'embed': v.get('embed', True)})
    # --- podcast feeds (media_fetch.py pod): every episode of each show
    import html as _html, xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd', 'content': 'http://purl.org/rss/1.0/modules/content/'}
    SHOWS = {'advisory-opinions': ('Advisory Opinions', 'The Dispatch'), 'strict-scrutiny': ('Strict Scrutiny', 'Crooked Media'),
             'divided-argument': ('Divided Argument', 'Will Baude & Dan Epps'), 'five-four': ('5-4', 'Prologue Projects'),
             'scotuscast': ('SCOTUScast', 'The Federalist Society'), 'scotustalk': ('SCOTUStalk', 'SCOTUSblog'),
             'we-the-people': ('We the People', 'National Constitution Center'), 'amaricas-constitution': ("Amarica's Constitution", 'Akhil Reed Amar'),
             'more-perfect': ('More Perfect', 'WNYC Studios'),
             'amicus': ('Amicus', 'Slate (Dahlia Lithwick)'),
             'landmark-cases': ('Landmark Cases', 'C-SPAN'),
             'make-no-law': ('Make No Law', 'Legal Talk Network (Ken White)'),
             'supreme-myths': ('Supreme Myths', 'Eric Segall'),
             'constitutional': ('Constitutional', 'The Washington Post'),
             'bound-by-oath': ('Bound By Oath', 'Institute for Justice'),
             'opening-arguments': ('Opening Arguments', 'Opening Arguments Media'),
             'citizens-guide': ("The Citizen's Guide to the Supreme Court", "The Citizen's Guide"),
             'landmark-decisions': ('Landmark Decisions in the U.S. Supreme Court', 'Aaron Larson')}
    yt_by_title = {re.sub(r'\W+', '', v['t'].lower()): v for v in vids}
    # every named case (Supreme Court Database-only ones too) can be matched by its full name
    every = {c['id']: c for c in S if c.get('dec') and ' v. ' in c['n']}
    every.update({c['id']: c for c in pend})
    word_idx = collections.defaultdict(set)
    sides_of = {}
    one_sided = {}
    for cid, c in every.items():
        sd = info[cid][0] if cid in info else sides(c['n'])
        raw = raw_sides(c['n'])
        if not sd or not raw or not (sd[0] or sd[1]):
            continue
        # one distinctive party name is enough when the other side's first word ("Trump", "Roy") completes the pattern
        left = sd[0][0] if sd[0] else raw[0]
        right = sd[1][0] if sd[1] else raw[1]
        if not (sd[0] and sd[1]) and len(raw[0]) + len(raw[1]) < 8:
            continue
        sides_of[cid] = ([left], [right])
        if not (sd[0] and sd[1]):
            m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+?)(?:\s*\(\d\))?$', c['n'])
            # the common-named side written out in full right beside "v." ("Trump v. Barbara", "United States v. Rahimi")
            gl = re.escape(re.sub(r',.*$', '', m.group(1)).strip())
            one_sided[cid] = re.compile(re.escape(re.sub(r'\s*\(\d\)$', '', c['n'])) + '|' + (
                r'\b' + gl + r'\s+v\.\s+(?:[\w.,&\'’-]+\s+){0,2}?' + re.escape(right) + r'\b' if not sd[0] else
                r'\b' + re.escape(left) + r'\b[^\n.]{0,40}?\s+v\.\s+' + re.escape(re.sub(r',.*$', '', m.group(2)).strip()) + r'\b'))
        for w in (sd[0][:1] + sd[1][:1]):
            word_idx[w].add(cid)
    rx_cache = {}
    short_cache = {}

    def rx_full(cid):
        if cid in one_sided:
            return one_sided[cid]
        if cid not in rx_cache:
            sd = sides_of[cid]
            rx_cache[cid] = re.compile(re.escape(re.sub(r'\s*\(\d\)$', '', every[cid]['n'])) + '|' + r'\b' + re.escape(sd[0][0]) +
                                       r'\b[^\n.]{0,60}?\bv(?:s)?\.?\s[^\n]{0,60}?\b' + re.escape(sd[1][0]) + r'\b')
        return rx_cache[cid]

    def dur(s):
        s = (s or '').strip()
        if re.fullmatch(r'\d+', s):
            return int(s)
        return secs(s) if re.fullmatch(r'(?:\d+:)?\d{1,2}:\d{2}', s) else 0

    n_ep = 0
    for path in sorted(glob.glob(f'{RAW}/pod/*.xml')):
        key = os.path.basename(path)[:-4]
        show, by = SHOWS.get(key, (key, ''))
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for it in root.iter('item'):
            title = (it.findtext('title') or '').strip()
            try:
                ed = parsedate_to_datetime(it.findtext('pubDate')).date()
            except Exception:
                continue
            enc = it.find('enclosure')
            audio = enc.get('url') if enc is not None else None
            notes = it.findtext('content:encoded', namespaces=NS) or it.findtext('description') or ''
            notes = _html.unescape(re.sub(r'<[^>]+>', '', re.sub(r'<br\s*/?>|</p>|</li>|</div>', '\n', notes)))
            lines = [l.strip(' \t—–-•*') for l in notes.split('\n') if l.strip()]
            short = [l for l in lines if len(l) < 160]                  # agenda / chapter lines
            chapters = [(secs(m.group(1)), m.group(2)) for m in (CHAPTER.match(l) for l in lines) if m]
            chapters += [(secs(m.group(2)), m.group(1)) for m in (CHAPTER_END.match(l) for l in lines) if m]
            words = set(re.findall(r"[A-Z][A-Za-z'’\-]{3,}", title + '\n' + notes))
            cands = set().union(*(word_idx[w] for w in words if w in word_idx)) if words else set()
            yt = yt_by_title.get(re.sub(r'\W+', '', title.lower()))
            n_ep += 1
            for cid in cands:
                c = every[cid]
                fr = rx_full(cid)
                d = date.fromisoformat(c['dec']) if c.get('dec') else date.fromisoformat(c['from'])
                in_window = (d - timedelta(days=30) <= ed <= d + timedelta(days=700)) if c.get('pending') else (d - timedelta(days=540) <= ed <= d + timedelta(days=460))
                if cid in one_sided and not in_window:            # a common name far from the decision: only the case's exact name
                    fr = re.compile(re.escape(re.sub(r'\s*\(\d\)$', '', c['n'])))
                if cid in rx:
                    sr = rx[cid][1]
                elif cid in info and in_window:
                    sr = short_cache[cid] if cid in short_cache else short_cache.setdefault(cid, short_rx(c))
                else:
                    sr = None
                hit = None
                for t, topic in chapters:                               # a chapter that names the case
                    if fr.search(topic) or (in_window and sr and sr_ok(sr, topic, c['n']) and ' v. ' not in topic):
                        hit = (t, topic); break
                if not hit and fr.search(title):                        # the title names the case
                    hit = (0, '')
                if not hit and in_window and sr and sr_ok(sr, title, c['n']) and ' v. ' not in title:   # or its one distinctive party name
                    hit = (0, '')
                if not hit and in_window and sr:                        # an agenda line names it by that party name
                    for l in short:
                        if sr_ok(sr, l, c['n']) and ' v. ' not in l and not READING.search(l):
                            hit = (0, l); break
                if not hit:
                    for l in short:                                     # an agenda line names it in full
                        if fr.search(l) and not READING.search(l):
                            hit = (0, l); break
                if not hit and in_window and fr.search(notes):          # the notes name it in full, around the decision
                    hit = (0, '')
                if not hit:
                    continue
                item = {'kind': 'pod', 't': title, 'ch': show, 'by': by, 'date': ed.isoformat(), 'start': hit[0], 'topic': hit[1][:140],
                        'sec': dur(it.findtext('itunes:duration', namespaces=NS)), 'audio': audio, 'link': it.findtext('link') or ''}
                if yt and yt.get('embed', True):
                    item.update({'id': yt['id'], 'embed': True})
                lst = media[cid]['videos']
                if not any(x.get('t') == title and x.get('ch') == show for x in lst):
                    lst.append(item)
    print('podcast episodes read:', n_ep)
    # a YouTube copy of a podcast episode replaces the separate video entry
    for m in media.values():
        pod_ids = {x.get('id') for x in m['videos'] if x.get('kind') == 'pod' and x.get('id')}
        m['videos'] = [x for x in m['videos'] if x.get('kind') == 'pod' or x['id'] not in pod_ids]
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
            if r.search(v['t']) and not any(x.get('id') == v['id'] for x in media[c['id']]['videos']):
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
