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
import collections, glob, json, os, re, urllib.parse
from datetime import date, timedelta

RAW = 'data/raw/media'
OUT = 'docs/data/media'
GENERIC = set('united states state states city county commissioner people secretary attorney general board department commonwealth '
              'town village school district government federal national american the of in re ex parte matter inc co corp company '
              'corporation association et al new york california texas ohio pennsylvania virginia illinois georgia florida '
              'trump biden obama president first second little brown white black green young king long free'.split())
# episode pages on the shows' own sites (for episodes whose feed item links only the show's home page)
EPISODE_PAGE = re.compile(r'^https?://(?:www\.)?(?:thedispatch\.com/podcast/[^/]+/[^/?#]+|constitutioncenter\.org/(?:news-debate/)?(?:podcasts?|we-the-people)/[^?#]+|crooked\.com/podcast/[^/?#]+|fedsoc\.org/(?:podcasts|multimedia)/[^?#]+|scotusblog\.com/\d{4}/\d\d/[^?#]+)', re.I)
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


YT_ID = re.compile(r'(?:youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|live/)|youtu\.be/)([\w-]{11})')
SHOW_CHANNELS = {'Advisory Opinions': ('dispatch', 'advisory'), 'Strict Scrutiny': ('crooked', 'strict scrutiny'),
                 'Divided Argument': ('divided',), '5-4': ('5-4', 'five four', 'prologue'), 'SCOTUScast': ('federalist',),
                 'SCOTUStalk': ('scotusblog',), 'We the People': ('constitution center', 'constitutioncenter'),
                 "Amarica's Constitution": ('amar',), 'Amicus': ('slate',), 'More Perfect': ('wnyc', 'more perfect'),
                 'Opening Arguments': ('opening arguments',), "The Citizen's Guide to the Supreme Court": ('citizen',),
                 'Bound By Oath': ('institute for justice',), 'Landmark Cases': ('c-span', 'cspan')}


def oembed(vid):
    """YouTube's official oEmbed endpoint: title and channel of a public, embeddable video (None otherwise). Cached."""
    import urllib.request
    os.makedirs(f'{RAW}/oembed', exist_ok=True)
    p = f'{RAW}/oembed/{vid}.json'
    if not os.path.exists(p):
        try:
            d = json.load(urllib.request.urlopen(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json', timeout=30))
        except Exception as e:
            d = {'error': str(getattr(e, 'code', e))}
        json.dump(d, open(p, 'w', encoding='utf-8'))
    d = json.load(open(p, encoding='utf-8'))
    return None if d.get('error') else d


def same_episode(vid, title, show):
    """A YouTube video linked from an episode's notes is that episode's video only if its channel is the show's and its
    title is the episode's title (allowing the show name or episode number around it)."""
    import difflib
    d = oembed(vid)
    if not d:
        return False
    ch = (d.get('author_name') or '').lower()
    if show in SHOW_CHANNELS and not any(k in ch for k in SHOW_CHANNELS[show]):
        return False
    a = re.sub(r'\W+', ' ', title.lower()).strip()
    b = re.sub(r'\W+', ' ', (d.get('title') or '').lower()).strip()
    b = re.sub(r'\b(?:advisory opinions|strict scrutiny|divided argument|ep(?:isode)? ?\d+)\b', ' ', b).strip()
    b = re.sub(r'\s+', ' ', b)
    return bool(a) and (a in b or b in a and len(b) > 12 or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


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
        if v.get('show') == 'The Dispatch':         # the channel's other shows: used only to pair podcast episodes below
            continue
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
    # a podcast episode's own YouTube upload: same show channel, published within ten days, and the same title once
    # show names, episode numbers and "Interview:" style labels are set aside
    import difflib
    PAIR_CH = {'Advisory Opinions': ('dispatch', 'advisory'), 'Strict Scrutiny': ('strict scrutiny', 'crooked'), 'Divided Argument': ('divided',),
               'SCOTUStalk': ('scotusblog',)}
    def tnorm(t):
        t = t.lower()
        t = re.sub(r'\b(?:advisory opinions|strict scrutiny|divided argument|scotustalk|the dispatch|podcast|episode \d+|ep\.? ?\d+|interview|bonus|full episode)\b', ' ', t)
        return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]+', ' ', t)).strip()
    by_show = collections.defaultdict(list)
    for v in vids:
        if not v.get('date'):
            continue
        ch = (v.get('ch') or '').lower() + ' ' + (v.get('show') or '').lower()
        for show, keys in PAIR_CH.items():
            if any(k in ch for k in keys):
                by_show[show].append((date.fromisoformat(v['date']), tnorm(v['t']), v))

    def pair_yt(title, ed, show):
        a = tnorm(title)
        if len(a) < 6:
            return None
        best = None
        for vd, b, v in by_show.get(show, []):
            if abs((vd - ed).days) > 10 or not b:
                continue
            r = 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()
            if (a in b or b in a) and min(len(a), len(b)) >= 15:
                r = max(r, 0.9)
            if r >= 0.85 and (best is None or r > best[0]):
                best = (r, v)
        return best[1] if best else None

    DESC_STOP = set('sarah david isgur french advisory opinions dispatch strict scrutiny divided argument leah melissa kate podcast episode agenda notes supreme court their about which there today discuss justice judge would could after before other these those where while'.split())
    SHOW_MARK = {'Advisory Opinions': 'advisory opinions', 'Strict Scrutiny': 'strict scrutiny', 'Divided Argument': 'divided argument'}
    SHOW_PARENT = {'Advisory Opinions': 'The Dispatch'}

    def pair_by_length(ed, sec, show, notes=''):
        """The show retitles its YouTube uploads ("Why You Should Hate Oliver Wendell Holmes Jr." for the podcast's
        "Progressivism and Eugenics in the Court of Justice Holmes"), so failing a title match, take the show's upload
        published within two days whose running time is within 6% (at least 90 seconds) of the episode's."""
        if not sec or show not in SHOW_MARK:
            return None
        best = None
        for vd, b, v in by_show.get(show, []):
            if abs((vd - ed).days) > 2 or not v.get('sec'):
                continue
            own = v.get('show') == show or SHOW_MARK[show] in (v.get('t', '') + ' ' + v.get('desc', '')[:600]).lower() \
                or SHOW_MARK[show] in (v.get('ch') or '').lower()
            # the show's parent channel (The Dispatch posts Advisory Opinions episodes on its main channel, retitled and
            # without the show's name): accepted only when the description closely repeats the episode's notes
            parent = SHOW_PARENT.get(show) and (v.get('ch') or '') == SHOW_PARENT[show]
            if not (own or parent):
                continue
            # the YouTube cut drops the ads, so it runs up to ~10% shorter than the audio (never much longer)
            gap = abs(v['sec'] - sec)
            # and the video's description must echo the episode's notes (the show reuses them): 4+ shared distinctive words
            nw = set(re.findall(r'[a-z]{5,}', notes[:700].lower())) - DESC_STOP
            vw = set(re.findall(r'[a-z]{5,}', (v.get('desc') or '')[:900].lower())) - DESC_STOP
            if len(nw & vw) < 4:
                continue
            if v.get('show') != show:
                # any upload outside the show's own playlist must open with the episode's own summary, nearly word for word
                o1 = re.sub(r'\s+', ' ', notes).strip().lower()[:280]
                o2 = re.sub(r'\s+', ' ', v.get('desc') or '').strip().lower()[:280]
                if difflib.SequenceMatcher(None, o1, o2).ratio() < 0.75:
                    continue
            if sec - 0.10 * sec <= v['sec'] <= sec + 90 and (best is None or gap < best[0]):
                best = (gap, v)
        return best

    # one video per episode: pair every episode of the shows first (title matches, then the closest running time), so
    # two episodes released a day apart cannot both take the same upload
    PAIRED = {}
    cands = []
    for path in sorted(glob.glob(f'{RAW}/pod/*.xml')):
        show0 = SHOWS.get(os.path.basename(path)[:-4], ('', ''))[0]
        if show0 not in SHOW_MARK:
            continue
        try:
            root0 = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for it in root0.iter('item'):
            t0 = (it.findtext('title') or '').strip()
            try:
                e0 = parsedate_to_datetime(it.findtext('pubDate')).date()
            except Exception:
                continue
            v0 = yt_by_title.get(re.sub(r'\W+', '', t0.lower())) or pair_yt(t0, e0, show0)
            if v0:
                cands.append((-1, show0, t0, v0))
                continue
            d0 = (it.findtext('itunes:duration', namespaces=NS) or '').strip()
            d0 = int(d0) if d0.isdigit() else (secs(d0) if re.fullmatch(r'(?:\d+:)?\d{1,2}:\d{2}', d0) else 0)
            n0 = _html.unescape(re.sub(r'<[^>]+>', ' ', it.findtext('content:encoded', namespaces=NS) or it.findtext('description') or ''))
            got = pair_by_length(e0, d0, show0, n0)
            if got:
                cands.append((got[0], show0, t0, got[1]))
    used = set()
    for gap, show0, t0, v0 in sorted(cands, key=lambda x: x[0]):
        if v0['id'] in used or (show0, t0) in PAIRED:
            continue
        used.add(v0['id'])
        PAIRED[(show0, t0)] = v0
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
        # a link shared by many items is the show's home page, not the episode's
        feed_links = collections.Counter((i.findtext('link') or '').strip() for i in root.iter('item'))
        for it in root.iter('item'):
            title = (it.findtext('title') or '').strip()
            try:
                ed = parsedate_to_datetime(it.findtext('pubDate')).date()
            except Exception:
                continue
            enc = it.find('enclosure')
            audio = enc.get('url') if enc is not None else None
            notes = it.findtext('content:encoded', namespaces=NS) or it.findtext('description') or ''
            ep_link = (it.findtext('link') or '').strip()
            if feed_links[ep_link] > 3:
                ep_link = ''
            if not ep_link:                       # the episode's page on the show's own site, linked from its notes
                for u in re.findall(r'https?://[^\s"<>\']+', _html.unescape(notes)):
                    u = u.rstrip('.,);')
                    if EPISODE_PAGE.search(u):
                        ep_link = u
                        break
            note_vids = list(dict.fromkeys(YT_ID.findall(_html.unescape(notes + ' ' + (it.findtext('link') or '')))))
            notes = _html.unescape(re.sub(r'<[^>]+>', '', re.sub(r'<br\s*/?>|</p>|</li>|</div>', '\n', notes)))
            lines = [l.strip(' \t—–-•*') for l in notes.split('\n') if l.strip()]
            short = [l for l in lines if len(l) < 160]                  # agenda / chapter lines
            chapters = [(secs(m.group(1)), m.group(2)) for m in (CHAPTER.match(l) for l in lines) if m]
            chapters += [(secs(m.group(2)), m.group(1)) for m in (CHAPTER_END.match(l) for l in lines) if m]
            words = set(re.findall(r"[A-Z][A-Za-z'’\-]{3,}", title + '\n' + notes))
            cands = set().union(*(word_idx[w] for w in words if w in word_idx)) if words else set()
            yt = yt_by_title.get(re.sub(r'\W+', '', title.lower())) or pair_yt(title, ed, show)
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
                        'sec': dur(it.findtext('itunes:duration', namespaces=NS)), 'audio': audio, 'link': ep_link}
                if not (yt and yt.get('embed', True)):
                    for nv in note_vids[:3]:            # the episode's own YouTube video, linked from its notes
                        if same_episode(nv, title, show):
                            yt = {'id': nv, 'embed': True}
                            break
                if show in SHOW_MARK:
                    yt = PAIRED.get((show, title))
                if yt and yt.get('embed', True):
                    item.update({'id': yt['id'], 'embed': True})
                    if item['start'] and yt.get('sec') and item['sec'] and abs(yt['sec'] - item['sec']) > 60:
                        item['start'] = 0       # the video is cut differently from the audio: its chapter times would not line up
                lst = media[cid]['videos']
                if not any(x.get('t') == title and x.get('ch') == show for x in lst):
                    lst.append(item)
    print('podcast episodes read:', n_ep)
    # episodes still without a video or an episode page: what media_fetch.py epfind found for them (a YouTube video on
    # the show's channel, or the episode's Apple Podcasts page); the rest go to unlinked.json for the next epfind run
    YT_SINCE = {'Advisory Opinions': '2023-03-01', 'Strict Scrutiny': '2024-04-01', 'Divided Argument': '2025-01-01'}
    unlinked, seen_ep = [], set()
    for m in media.values():
        for x in m['videos']:
            if x.get('kind') != 'pod' or x.get('id'):
                continue
            k = re.sub(r'\W+', '-', (x['ch'] + '-' + x['t']).lower())[:120]
            fp = f'{RAW}/epfind/{k}.json'
            f = json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else {}
            if f.get('yt'):
                x.update({'id': f['yt'], 'embed': True})
                continue
            if not x.get('link') and f.get('apple'):
                x['link'] = f['apple']
            yt_possible = x['date'] >= YT_SINCE.get(x['ch'], '0000') and x['ch'] not in ('More Perfect',)
            if (show_key := (x['ch'], x['t'])) not in seen_ep and (not x.get('link') or (yt_possible and x['ch'] in YT_SINCE)) and ('yt' not in f or 'apple' not in f):
                seen_ep.add(show_key)
                unlinked.append({'show': x['ch'], 't': x['t'], 'date': x['date'], 'yt': yt_possible})
    unlinked.sort(key=lambda e: e['date'], reverse=True)          # newest first
    unlinked.sort(key=lambda e: not e['yt'])                      # episodes in the shows' YouTube eras before the rest
    json.dump(unlinked, open(f'{RAW}/unlinked.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('episodes without a video or page, queued for epfind:', len(unlinked))
    # a YouTube copy of a podcast episode replaces the separate video entry (on every case page)
    all_pod_ids = {x.get('id') for m in media.values() for x in m['videos'] if x.get('kind') == 'pod' and x.get('id')}
    for m in media.values():
        pod_ids = all_pod_ids
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
        media[c['id']]['print'] = media[c['id']]['print'][:12]
    # --- coverage and commentary on the web: the news and analysis cited in the case's Wikipedia article
    # (data/raw/media/wiki, media_fetch.py wiki). The article counts only when its Supreme Court case infobox gives the
    # case's U.S. Reports volume and page or its docket number. Primary sources (the Court, Oyez, Justia, Cornell LII...)
    # are left out: the case page links them already.
    PRIMARY = re.compile(r'(supremecourt\.gov|oyez\.org|justia\.com|law\.cornell\.edu|findlaw\.com|loc\.gov|govinfo\.gov|courtlistener\.com|'
                         r'casetext\.com|uscourts\.gov|wikipedia\.org|wikisource\.org|archive\.org|google\.com|scholar\.google|westlaw|lexis)', re.I)
    # outlets that require a subscription for most articles (hard paywalls and metered sites that cut off after a few)
    PAYWALL = re.compile(r'(?:^|\.)(nytimes\.com|wsj\.com|washingtonpost\.com|ft\.com|economist\.com|bloomberg\.com|bloomberglaw\.com|'
                         r'theatlantic\.com|newyorker\.com|latimes\.com|bostonglobe\.com|chicagotribune\.com|law360\.com|'
                         r'nationalreview\.com|thetimes\.co\.uk|telegraph\.co\.uk|businessinsider\.com|barrons\.com|wired\.com|'
                         r'newsweek\.com|thedispatch\.com|foreignaffairs\.com|'
                         r'harpers\.org|nybooks\.com|thenation\.com|newrepublic\.com|washingtonexaminer\.com|'
                         r'insidehighered\.com|chronicle\.com|startribune\.com|sfchronicle\.com|denverpost\.com|seattletimes\.com|'
                         r'dallasnews\.com|houstonchronicle\.com|ajc\.com|inquirer\.com|tampabay\.com|miamiherald\.com|'
                         r'baltimoresun\.com|post-gazette\.com|jsonline\.com|azcentral\.com|courant\.com|'
                         r'law\.com|nationaljournal\.com|rollcall\.com|theathletic\.com|vanityfair\.com|'
                         r'jstor\.org|tandfonline\.com|sciencedirect\.com|springer\.com|wiley\.com|heinonline\.org)$', re.I)
    from urllib.parse import urlparse

    def tparams(t):
        """{{cite news |a=b |c=[[x|y]] ...}} -> dict, splitting on top-level pipes only"""
        body = t[2:-2]
        parts, depth, cur = [], 0, ''
        i = 0
        while i < len(body):
            two = body[i:i + 2]
            if two in ('[[', '{{'):
                depth += 1; cur += two; i += 2; continue
            if two in (']]', '}}'):
                depth -= 1; cur += two; i += 2; continue
            if body[i] == '|' and depth == 0:
                parts.append(cur); cur = ''
            else:
                cur += body[i]
            i += 1
        parts.append(cur)
        out = {}
        for p_ in parts[1:]:
            if '=' in p_:
                k, v = p_.split('=', 1)
                out[k.strip().lower()] = v.strip()
        return out

    def plain(v):
        v = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', v or '')
        v = re.sub(r'\{\{[^{}]*\}\}', '', v)
        v = re.sub(r"'{2,}", '', v)
        return _html.unescape(re.sub(r'<[^>]+>', '', v)).strip()

    def iso(d):
        d = plain(d)
        for fmt in ('%B %d, %Y', '%d %B %Y', '%Y-%m-%d', '%b %d, %Y', '%d %b %Y', '%B %Y', '%Y'):
            try:
                from datetime import datetime
                return datetime.strptime(d, fmt).date().isoformat()[: 4 if fmt == '%Y' else 7 if fmt == '%B %Y' else 10]
            except ValueError:
                pass
        return ''

    wiki = {}
    for pth in glob.glob(f'{RAW}/wiki/*.json'):
        wiki.update(json.load(open(pth, encoding='utf-8')))
    n_wiki = 0
    for c in list(cases) + pend:
        name = re.sub(r'\s*\(\d\)$', '', c['n'])
        pg = wiki.get(name)
        if not pg:
            continue
        w = pg['text']
        ib = re.search(r'\{\{\s*Infobox SCOTUS case(.*?)\n\}\}', w, re.S | re.I)
        if not ib:
            continue
        box = ib.group(1)
        m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or c.get('citUS') or '')
        vol = re.search(r'\|\s*USVol\s*=\s*(\d+)', box)
        page = re.search(r'\|\s*USPage\s*=\s*(\d+)', box)
        dk = re.search(r'\|\s*Docket\s*=\s*([^\n|]+)', box)
        ok = (m and vol and page and vol.group(1) == m.group(1) and page.group(1) == m.group(2)) or \
             (c.get('d') and dk and c['d'].strip().lower() in dk.group(1).lower()) or \
             (m and vol and vol.group(1) == m.group(1) and not page)
        if not ok:
            continue
        links, seen_u = [], set()
        for t in re.findall(r'\{\{\s*cite\s+(?:news|web|magazine|journal|press release|podcast|av media)\b(?:[^{}]|\{\{[^{}]*\}\})*\}\}', w, re.I):
            p_ = tparams(t)
            u = (p_.get('url') or '').strip()
            if not u.startswith('http') or PRIMARY.search(u) or u in seen_u:
                continue
            host = urlparse(u).netloc.lower().removeprefix('www.')
            if (host.endswith('.gov') or host.endswith('.mil')) and not host.endswith('congress.gov'):
                continue                                    # government documents, not coverage (CRS reports stay)
            title = plain(p_.get('title', ''))
            if not title or len(title) > 300:
                continue
            outlet = plain(p_.get('work') or p_.get('newspaper') or p_.get('website') or p_.get('magazine') or p_.get('journal') or p_.get('publisher') or host)
            seen_u.add(u)
            links.append({'u': u, 't': title, 'o': outlet[:80], 'd': iso(p_.get('date', '')),
                          'pw': 1 if PAYWALL.search(host) else 0})
        if links:
            links.sort(key=lambda x: x['d'] or '0000', reverse=True)
            media[c['id']]['web'] = links[:30]
            media[c['id']]['wiki'] = 'https://en.wikipedia.org/wiki/' + urllib.parse.quote(pg['title'].replace(' ', '_'))
            n_wiki += 1
    print('cases with web coverage from Wikipedia citations:', n_wiki)
    # --- more coverage: every SCOTUSblog link in the case's Wikipedia article (case files, argument previews, opinion
    # analyses) and its other external links with a label; SCOTUSblog itself is not crawled (its robots.txt asks not to)
    for c in list(cases) + pend:
        name = re.sub(r'\s*\(\d\)$', '', c['n'])
        m_ = media.get(c['id'])
        pg = wiki.get(name)
        if not pg or not m_ or not m_.get('wiki'):
            continue                                   # only articles already verified against the case above
        w = pg['text']
        have = {x['u'].rstrip('/') for x in m_.get('web', [])}
        extra = []
        for u, label in re.findall(r'\[(https?://[^\s\]]+)\s+([^\]]{3,200})\]', w):
            u2 = u.rstrip('/')
            if u2 in have or PRIMARY.search(u):
                continue
            host = urlparse(u).netloc.lower().removeprefix('www.')
            if (host.endswith('.gov') or host.endswith('.mil')) and not host.endswith('congress.gov'):
                continue
            have.add(u2)
            extra.append({'u': u, 't': plain(label), 'o': 'SCOTUSblog' if 'scotusblog.com' in host else host, 'd': '', 'pw': 1 if PAYWALL.search(host) else 0})
        for u in re.findall(r'https?://(?:www\.)?scotusblog\.com/(?:case-files/cases|cases/case-files)/[^\s|\]}<]+', w):
            m_['sb'] = u.replace('http://', 'https://')
            break
        if extra:
            m_['web'] = (m_.get('web', []) + extra)[:40]
    # --- Congressional Research Service reports (public domain; cached by crs_fetch.py from EveryCRSReport.com) that
    # discuss the case: its full name, or both party names joined by "v.", at least twice (or once in the title)
    import csv
    crs_meta = {}
    if os.path.exists('data/raw/crs/reports.csv'):
        for row in csv.DictReader(open('data/raw/crs/reports.csv', encoding='utf-8')):
            crs_meta[row['number']] = row
    pairs = {}
    for cid, sd in sides_of.items():
        pairs.setdefault((sd[0][0], sd[1][0]), []).append(cid)
    n_crs = 0
    for fp in glob.glob('data/raw/crs/html/*.html'):
        num = os.path.basename(fp)[:-5]
        meta = crs_meta.get(num)
        if not meta:
            continue
        txt = _html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'<img[^>]*>', '', open(fp, encoding='utf-8', errors='replace').read())))
        found = collections.Counter()
        for m in re.finditer(r"([A-Z][\w.'’&-]+)(?:,? [A-Z][\w.'’&-]+){0,5},? v\.\s+(?:the\s+)?([A-Z][\w.'’&-]+)", txt):
            # map "First ... v. Second" to cases whose distinctive party names are the first such words
            left = [x for x in re.findall(r"[A-Z][A-Za-z'’\-]{3,}", m.group(0).split(' v.')[0]) if x.lower() not in GENERIC]
            right = [x for x in re.findall(r"[A-Z][A-Za-z'’\-]{3,}", m.group(0).split(' v.')[1]) if x.lower() not in GENERIC]
            if left and right:
                for cid in pairs.get((left[0], right[0]), []):
                    found[cid] += 1
        for cid, n in found.items():
            cands = pairs[(sides_of[cid][0][0], sides_of[cid][1][0])]
            if len(cands) > 1:
                continue                                   # two cases share those names: not sure which one
            if n >= 2 or (meta['title'] and every[cid]['n'].split(' v. ')[0] in meta['title']):
                url = f"https://www.congress.gov/crs-product/{num}"
                m_ = media[cid]
                if any(x['u'] == url for x in m_.get('web', [])):
                    continue
                m_.setdefault('web', []).append({'u': url, 't': meta['title'], 'o': 'Congressional Research Service', 'd': (meta.get('latestPubDate') or '')[:10], 'pw': 0, 'n': n})
                n_crs += 1
    for m_ in media.values():
        if m_.get('web'):
            crs = sorted([x for x in m_['web'] if x['o'] == 'Congressional Research Service'], key=lambda x: -x.get('n', 0))[:6]
            m_['web'] = [x for x in m_['web'] if x['o'] != 'Congressional Research Service'] + crs
            for x in m_['web']:
                x.pop('n', None)
    print('CRS report links:', n_crs)
    # --- write by term
    tmap = {c['id']: str(c.get('t')) for c in S}          # every case, Supreme Court Database-only ones included
    tmap.update({c['id']: str(c.get('t')) for c in pend})
    by_term = collections.defaultdict(dict)
    n = collections.Counter()
    for cid, m in media.items():
        if not (m['videos'] or m['print'] or m.get('web')):
            continue
        m['videos'].sort(key=lambda v: (v['date'] or '9999'), reverse=False)
        by_term[tmap.get(cid, 'x')][cid] = m
        n['cases'] += 1; n['videos'] += len(m['videos']); n['print'] += len(m['print']); n['web'] += len(m.get('web', []))
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(f'{OUT}/*.js'):
        os.remove(f)
    for t, recs in by_term.items():
        open(f'{OUT}/{t}.js', 'w', encoding='utf-8').write('window.MEDIA=window.MEDIA||{};Object.assign(window.MEDIA,' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');')
    open('docs/data/media-index.js', 'w', encoding='utf-8').write('window.MEDIA_INDEX=' + json.dumps(sorted(set(cid for r in by_term.values() for cid in r)), separators=(',', ':')) + ';')
    print(dict(n))


if __name__ == '__main__':
    main()
