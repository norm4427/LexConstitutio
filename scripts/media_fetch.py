"""Cache the sources for the case pages' "In the media" tab (build_media.py).

1. Podcast/video episodes about recent cases, from these YouTube playlists: Advisory Opinions (The Dispatch), SCOTUSblog
   and SCOTUSblog Animated Explainers (The Dispatch), Strict Scrutiny, Divided Argument. Through official interfaces only:
   each playlist's public RSS feed (its latest 15 videos, with full descriptions, where shows put chapter timestamps), or,
   with a YouTube Data API v3 key in YT_API_KEY, every video in the playlist (playlistItems + videos: length, embeddable,
   public). Without a key, embeddability comes from YouTube's oEmbed endpoint (as scripts/youtube.sh checks it).
   -> data/raw/media/yt/<videoId>.json
2. Videos about older landmark cases (needs YT_API_KEY): a Data API search for "<case name>", embeddable videos only,
   for the 500 most-cited cases decided before 2015. -> data/raw/media/search/<case>.json
3. Newspaper pages (public domain) from the Library of Congress's Chronicling America, for the most-cited cases decided
   before 1964 and every named case decided before 1836: pages printed in the three weeks (two months before 1870) after the decision that name the parties and the Supreme Court.
   -> data/raw/media/loc/<case>.json
4. Podcast feeds (Advisory Opinions, Strict Scrutiny, Divided Argument, 5-4, SCOTUScast, SCOTUStalk, We the People,
   Amarica’s Constitution, More Perfect, Amicus, C-SPAN Landmark Cases, Make No Law, Supreme Myths,
   Constitutional, Bound By Oath, Opening Arguments, The Citizen's Guide to the Supreme Court, Landmark Decisions): every episode with show notes. -> data/raw/media/pod/<show>.xml
Resumable.  Run from the repo root:  python scripts/media_fetch.py [yt|search|loc]   (YT_API_KEY=... for the back catalog)
"""
import glob, html, json, os, re, sys, time, urllib.parse, urllib.request
import local_keys  # noqa: F401  (loads API keys from .keys.env)
from datetime import date, timedelta

RAW = 'data/raw/media'
UA = {'User-Agent': 'LexConstitutio/1.0 (academic research index; lexconstitutio.com)'}
PLAYLISTS = {
    'PLDuw5W_udnx2RhekBcHhFSIpDC9TE286q': 'Advisory Opinions',
    'PLDuw5W_udnx2IqUp8Lj9_qpfCpX7W8fEz': 'SCOTUSblog',
    'PLDuw5W_udnx09k7Lt6wS_GU2BUNC-CRCe': 'SCOTUSblog Animated Explainers',
    'UUk-Km4tcqAbhpnbrvj1pJFw': 'Strict Scrutiny',
    'UUaqFv9hD-XJmPMzC5Yvtneg': 'The Dispatch',          # all Dispatch uploads: older Advisory Opinions episodes are not in the show's playlist
    'UUu4dm15fbc4jWrOC-AtfDdg': 'Divided Argument',
}


def get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode('utf-8', 'replace')


def oembed_ok(vid):
    try:
        urllib.request.urlopen(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json', timeout=30)
        return True
    except Exception:
        return False


def save_video(rec):
    dest = f"{RAW}/yt/{rec['id']}.json"
    if os.path.exists(dest):
        old = json.load(open(dest, encoding='utf-8'))
        if len(old.get('desc', '')) >= len(rec.get('desc', '')) and (old.get('sec') or not rec.get('sec')):
            return
    json.dump(rec, open(dest, 'w', encoding='utf-8'), ensure_ascii=False)


def rss(pid):
    import xml.etree.ElementTree as ET
    ns = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'm': 'http://search.yahoo.com/mrss/'}
    q = f'channel_id=UC{pid[2:]}' if pid.startswith('UU') else f'playlist_id={pid}'   # uploads: the channel feed
    for attempt in range(5):                          # the feeds answer 404 intermittently
        try:
            root = ET.fromstring(get(f'https://www.youtube.com/feeds/videos.xml?{q}'))
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    n = 0
    for e in root.findall('a:entry', ns):
        vid = e.find('yt:videoId', ns).text
        rec = {'id': vid, 't': e.find('a:title', ns).text or '', 'ch': e.find('a:author/a:name', ns).text or '', 'show': PLAYLISTS[pid],
               'desc': e.find('m:group/m:description', ns).text or '', 'date': (e.find('a:published', ns).text or '')[:10], 'sec': 0,
               'embed': oembed_ok(vid)}
        save_video(rec)
        n += 1
        time.sleep(0.3)
    print(PLAYLISTS[pid], n, 'videos from the RSS feed', flush=True)


def data_api(pid, key):
    tok, ids = '', []
    while True:
        r = json.loads(get(f'https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={pid}&key={key}'
                           + (f'&pageToken={tok}' if tok else '')))
        for it in r.get('items', []):
            sn = it['snippet']
            vid = sn['resourceId']['videoId']
            ids.append(vid)
            save_video({'id': vid, 't': sn.get('title', ''), 'ch': sn.get('videoOwnerChannelTitle', ''), 'show': PLAYLISTS[pid],
                        'desc': sn.get('description', ''), 'date': (sn.get('publishedAt') or '')[:10], 'sec': 0, 'embed': True})
        tok = r.get('nextPageToken')
        if not tok:
            break
    for k in range(0, len(ids), 50):
        r = json.loads(get(f'https://www.googleapis.com/youtube/v3/videos?part=contentDetails,status&id={",".join(ids[k:k + 50])}&key={key}'))
        for it in r.get('items', []):
            p = f"{RAW}/yt/{it['id']}.json"
            rec = json.load(open(p, encoding='utf-8'))
            m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', it['contentDetails'].get('duration', ''))
            rec['sec'] = sum(int(x or 0) * f for x, f in zip(m.groups(), (3600, 60, 1))) if m else 0
            rec['embed'] = bool(it['status'].get('embeddable')) and it['status'].get('privacyStatus') == 'public'
            json.dump(rec, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    print(PLAYLISTS[pid], len(ids), 'videos from the Data API', flush=True)


def yt():
    os.makedirs(f'{RAW}/yt', exist_ok=True)
    key = os.environ.get('YT_API_KEY')
    for pid in PLAYLISTS:
        try:
            data_api(pid, key) if key else rss(pid)
        except Exception as e:
            print('playlist failed', pid, e, flush=True)


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def top_cases(before, n):
    S = load_js('docs/data/scotus.js')['cases']
    I = load_js('docs/data/case_impact.js')['c']
    cs = [c for c in S if c.get('dec') and c['dec'] < before and ' v. ' in c['n']]
    cs.sort(key=lambda c: -(I.get(c['id']) or [0, 0, 0])[2])
    return cs[:n]


def search():
    key = os.environ.get('YT_API_KEY')
    if not key:
        print('search skipped: set YT_API_KEY (YouTube Data API v3) to search for videos about older cases', flush=True)
        return
    os.makedirs(f'{RAW}/search', exist_ok=True)
    # essential cases first, then the most cited; cases that already have a video on the site are skipped; at most
    # YT_SEARCHES (default 95: 100 quota units each against the 10,000 a day) new searches a run
    ess = set(load_js('docs/data/essential.js'))
    have = set()
    for pth in glob.glob('docs/data/media/*.js'):
        t = open(pth, encoding='utf-8').read()
        for cid, m in json.loads(t[t.index('Object.assign(window.MEDIA,') + 27:].rstrip().rstrip(';').rstrip(')')).items():
            if m.get('videos'):
                have.add(cid)
    budget = int(os.environ.get('YT_SEARCHES', 95))
    cs = top_cases('2100-01-01', 3000)
    cs = [c for c in cs if c['id'] in ess] + [c for c in cs if c['id'] not in ess]
    for c in cs:
        dest = f"{RAW}/search/{c['id'].replace('/', '_')}.json"
        if os.path.exists(dest) or c['id'] in have:
            continue
        if budget <= 0:
            break
        budget -= 1
        name = re.sub(r'\s*\(\d\)$', '', c['n'])
        try:
            r = json.loads(get('https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&videoEmbeddable=true&maxResults=10&q='
                               + urllib.parse.quote_plus(f'"{name}"') + f'&key={key}'))
        except Exception as e:
            print('  search failed', c['id'], str(e).replace(key, '<key>'), flush=True)
            break
        json.dump([{'id': it['id']['videoId'], 't': html.unescape(it['snippet']['title']), 'ch': it['snippet']['channelTitle'],
                    'date': it['snippet']['publishedAt'][:10]} for it in r.get('items', [])], open(dest, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(0.2)
    print('search done', flush=True)


GENERIC = set('united states state states city county commissioner people secretary attorney general board department commonwealth '
              'town village school district government federal national american the of in re ex parte matter inc co corp company '
              'corporation association et al new york california texas ohio pennsylvania virginia illinois georgia florida'.split())


def party_words(name):
    m = re.match(r'^\s*(?:The\s+)?(.+?)\s+v\.\s+(?:The\s+)?(.+)$', name)
    if not m:
        return []
    out = []
    for side in m.groups():
        ws = [w for w in re.findall(r"[A-Z][A-Za-z'’\-]{3,}", side) if w.lower() not in GENERIC]
        if ws:
            out.append(ws[0])
    return out


def loc_one(c):
    dest = f"{RAW}/loc/{c['id'].replace('/', '_')}.json"
    if os.path.exists(dest):
        return
    ws = party_words(c['n'])
    if not ws:
        json.dump({'skip': 'no distinctive party name'}, open(dest, 'w'))
        return
    d = date.fromisoformat(c['dec'])
    # news travelled slowly before the telegraph: Marshall-era reports of a decision appeared for months afterwards
    days = 120 if d.year < 1836 else 60 if d.year < 1870 else 21
    a, b = d - timedelta(days=1), d + timedelta(days=days)
    q = ' '.join(f'"{w}"' for w in ws) + ' "supreme court"'
    url = ('https://www.loc.gov/collections/chronicling-america/?fo=json&c=25&at=results&q=' + urllib.parse.quote_plus(q) +
           f'&dates={a.isoformat()}/{b.isoformat()}')
    for attempt in range(3):
        try:
            r = json.loads(get(url, timeout=180))
            break
        except Exception as e:
            if attempt == 2:
                print('  loc failed', c['id'], e, flush=True)
                return
            time.sleep(20 * (attempt + 1))
    res = [{'date': x.get('date'), 'title': x.get('title'), 'url': x.get('url'), 'img': (x.get('image_url') or [None])[0],
            'paper': (x.get('partof_title') or [None])[0] if isinstance(x.get('partof_title'), list) else x.get('partof_title'),
            'loc': x.get('location_city') or x.get('location')} for x in r.get('results', [])]
    json.dump({'q': q, 'from': a.isoformat(), 'to': b.isoformat(), 'results': res}, open(dest, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(1.5)


def loc():
    """The most-cited cases decided before 1964 (LOC_N, default 150) and every named case of the Marshall era and
    before (decided before 1836); with LOC_ALL=1, then every other named case through 1963, a decade at a time.
    The API takes ~30 s a query, so several run at a time (LOC_WORKERS, default 3)."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(f'{RAW}/loc', exist_ok=True)
    S = load_js('docs/data/scotus.js')['cases']
    early = [c for c in S if c.get('dec') and c['dec'] < '1836-01-01' and ' v. ' in c['n']]
    todo, seen = [], set()
    for c in top_cases('1963-12-31', int(os.environ.get('LOC_N', 150))) + early:
        if c['id'] not in seen:
            seen.add(c['id']); todo.append(c)
    if os.environ.get('LOC_ALL'):
        # then every other named case through 1963 (Chronicling America's range), most cited first, taken a decade at a
        # time in turn so that every period fills in early; resumable, so it can run over several sessions
        I = load_js('docs/data/case_impact.js')['c']
        rest = [c for c in S if c.get('dec') and c['dec'] < '1964-01-01' and ' v. ' in c['n'] and c['id'] not in seen]
        rest.sort(key=lambda c: -(I.get(c['id']) or [0, 0, 0])[2])
        by_dec = {}
        for c in rest:
            by_dec.setdefault(c['dec'][:3], []).append(c)
        queues = [by_dec[k] for k in sorted(by_dec)]
        while any(queues):
            for q in queues:
                if q:
                    todo.append(q.pop(0))
    with ThreadPoolExecutor(int(os.environ.get('LOC_WORKERS', 3))) as ex:
        for k, _ in enumerate(ex.map(loc_one, todo)):
            if k % 50 == 0:
                print('loc', k, '/', len(todo), flush=True)
    print('loc done', flush=True)


# Podcast feeds (public RSS, found through the Apple Podcasts directory): every episode with its show notes, date,
# length and audio file. The case page plays the publisher's audio file in the browser; nothing is copied.
PODCASTS = {
    'advisory-opinions': ('Advisory Opinions', 'The Dispatch', 'https://feeds.megaphone.fm/DISPME4573820108'),
    'strict-scrutiny': ('Strict Scrutiny', 'Crooked Media', 'https://audioboom.com/channels/5166629.rss'),
    'divided-argument': ('Divided Argument', 'Will Baude & Dan Epps', 'https://feeds.beamly.com/GxB3ykF8pz0UMRya/feed.xml'),
    'five-four': ('5-4', 'Prologue Projects', 'https://feeds.redcircle.com/b6f505a9-f29d-4915-9e94-85182953a0ba'),
    'scotuscast': ('SCOTUScast', 'The Federalist Society', 'https://www.spreaker.com/show/2654486/episodes/feed'),
    'scotustalk': ('SCOTUStalk', 'SCOTUSblog', 'https://feeds.acast.com/public/shows/5c7d6c6a80f32c6a7cdeca24'),
    'we-the-people': ('We the People', 'National Constitution Center', 'https://pdrl.fm/2f25bb/feeds.megaphone.fm/wethepeople'),
    'amaricas-constitution': ("Amarica's Constitution", 'Akhil Reed Amar', 'https://feed.podbean.com/amaricasconstitution/feed.xml'),
    'more-perfect': ('More Perfect', 'WNYC Studios', 'https://feeds.simplecast.com/lQwwDIs1'),
    'amicus': ('Amicus', 'Slate (Dahlia Lithwick)', 'https://my.slate.com/podcasts/feeds/amicus/'),
    'landmark-cases': ('Landmark Cases', 'C-SPAN', 'https://feeds.megaphone.fm/cspanlandmarkcases'),
    'make-no-law': ('Make No Law', 'Legal Talk Network (Ken White)', 'https://feeds.megaphone.fm/LTN4153488764'),
    'supreme-myths': ('Supreme Myths', 'Eric Segall', 'https://feeds.captivate.fm/supreme-myths/'),
    'constitutional': ('Constitutional', 'The Washington Post', 'http://podcast.posttv.com/itunes-5951e18ce4b056ae8fa8e4b2.xml'),
    'bound-by-oath': ('Bound By Oath', 'Institute for Justice', 'https://feeds.podcastmirror.com/bound-by-oath'),
    'opening-arguments': ('Opening Arguments', 'Opening Arguments Media', 'https://openargs.libsyn.com/'),
    'citizens-guide': ("The Citizen's Guide to the Supreme Court", "The Citizen's Guide", 'https://rss.libsyn.com/shows/61022/destinations/236445.xml'),
    'landmark-decisions': ('Landmark Decisions in the U.S. Supreme Court', 'Aaron Larson', 'https://anchor.fm/s/44d196bc/podcast/rss'),
}


def pod():
    os.makedirs(f'{RAW}/pod', exist_ok=True)
    for k, (name, by, url) in PODCASTS.items():
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0 (podcast directory)'}), timeout=120).read()
            open(f'{RAW}/pod/{k}.xml', 'wb').write(b)
            print(name, len(b) // 1024, 'KB', b.count(b'<item'), 'episodes', flush=True)
        except Exception as e:
            print('feed failed', name, e, flush=True)
        time.sleep(1)


def gdelt():
    """News coverage of cases decided in the last three months and of pending cases, from the GDELT DOC 2.0 API (free,
    no key; it indexes only the most recent three months of news, so older cases get nothing). Only link, title,
    domain and date are kept. A headline counts when it contains one of the case's distinctive party names.
    -> data/raw/media/gdelt/<case>.json (re-run every few weeks to accumulate; results are merged, never dropped)"""
    os.makedirs(f'{RAW}/gdelt', exist_ok=True)
    S = load_js('docs/data/scotus.js')['cases']
    K = load_js('docs/data/docket.js')['cases']
    cut = (date.today() - timedelta(days=92)).isoformat()
    todo = [{'id': e['id'], 'n': e['n']} for e in K if ' v. ' in e['n']] +            [c for c in S if c.get('dec') and c['dec'] >= cut and ' v. ' in c['n']]
    n = 0
    for c in todo:
        dest = f"{RAW}/gdelt/{c['id'].replace('/', '_')}.json"
        old = json.load(open(dest, encoding='utf-8')) if os.path.exists(dest) else {'items': []}
        if old.get('checked') == date.today().isoformat():
            continue
        name = re.sub(r'\s*\(\d\)$', '', c['n'])
        ws = party_words(name)
        if not ws:
            continue
        url = 'https://api.gdeltproject.org/api/v2/doc/doc?' + urllib.parse.urlencode(
            {'query': f'"{name}" sourcelang:english', 'mode': 'artlist', 'maxrecords': 40, 'format': 'json', 'timespan': '3months', 'sort': 'datedesc'})
        try:
            r = json.loads(get(url, timeout=90) or '{}')
        except Exception as e:
            print('  gdelt failed', name, e, flush=True)
            time.sleep(15)
            continue
        have = {x['u'] for x in old['items']}
        for a in r.get('articles', []):
            t = html.unescape(a.get('title') or '').strip()
            if a['url'] in have or not t or not any(w.lower() in t.lower() for w in ws):
                continue
            sd = a.get('seendate') or ''
            old['items'].append({'u': a['url'], 't': t, 'o': a.get('domain') or '', 'd': f'{sd[:4]}-{sd[4:6]}-{sd[6:8]}' if len(sd) >= 8 else ''})
            n += 1
        old['checked'] = date.today().isoformat()
        json.dump(old, open(dest, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(6)                                   # GDELT asks for one request every five seconds
    print('gdelt: new headlines', n, 'for', len(todo), 'cases', flush=True)


def wiki():
    """Each case's English Wikipedia article (wikitext), for the news and commentary it cites. Titles are tried in
    batches of 50 (the case name as the site writes it, redirects followed); build_media.py keeps an article only when
    its Supreme Court case infobox gives the same U.S. Reports citation or docket number.
    -> data/raw/media/wiki/<batch>.json"""
    os.makedirs(f'{RAW}/wiki', exist_ok=True)
    S = load_js('docs/data/scotus.js')['cases']
    K = load_js('docs/data/docket.js')['cases']
    names = sorted({re.sub(r'\s*\(\d\)$', '', c['n']) for c in S if c.get('s') != 1 and ' v. ' in c['n']} |
                   {c['n'] for c in K if ' v. ' in c['n']})
    for k in range(0, len(names), 50):
        dest = f'{RAW}/wiki/{k // 50:04d}.json'
        if os.path.exists(dest):
            continue
        batch = names[k:k + 50]
        url = ('https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&redirects=1&prop=revisions'
               '&rvprop=content&rvslots=main&titles=' + urllib.parse.quote('|'.join(batch)))
        r = None
        for attempt in range(8):                      # Wikipedia answers 429 when asked too fast: back off and retry the same batch
            try:
                r = json.loads(get(url, timeout=120))
                break
            except Exception as e:
                print('  wiki retry', k, e, flush=True)
                time.sleep(min(300, 20 * (attempt + 1) ** 2))
        if r is None:
            continue
        q = r.get('query', {})
        back = {}
        for m in q.get('normalized', []) + q.get('redirects', []):
            back[m['to']] = back.get(m['from'], m['from'])
        pages = {}
        for p in q.get('pages', []):
            if p.get('missing') or not p.get('revisions'):
                continue
            pages[back.get(p['title'], p['title'])] = {'title': p['title'], 'text': p['revisions'][0]['slots']['main']['content']}
        json.dump(pages, open(dest, 'w', encoding='utf-8'), ensure_ascii=False)
        if k % 1000 == 0:
            print('wiki', k, '/', len(names), flush=True)
        time.sleep(3)
    print('wiki done', flush=True)


def _norm(t):
    return re.sub(r'[^a-z0-9 ]+', '', html.unescape(t or '').lower().replace('’', "'")).split()


def _similar(a, b):
    A, B = set(_norm(a)), set(_norm(b))
    return len(A & B) / max(1, min(len(A), len(B))) if A and B else 0


# YouTube channels of shows whose episodes may have a video (the Data API search is restricted to them)
SHOW_CHANNEL_IDS = {'Advisory Opinions': 'UCaqFv9hD-XJmPMzC5Yvtneg', 'Strict Scrutiny': 'UCk-Km4tcqAbhpnbrvj1pJFw',
                    'Divided Argument': 'UCu4dm15fbc4jWrOC-AtfDdg'}


def epfind():
    """Find a page or a video for podcast episodes that build_media.py could not pair (data/raw/media/unlinked.json):
    1. YouTube Data API search (needs YT_API_KEY; 100 quota units a search, so at most YT_SEARCHES, default 95, a run),
       restricted to the show's channel when known; a result counts only when its title matches the episode's, it was
       published within a week of the episode, and videos.list reports it public and embeddable.
    2. The episode's Apple Podcasts page (iTunes Search API): same show, matching title.
    Results are cached in data/raw/media/epfind/<key>.json; re-runs skip what was already tried."""
    os.makedirs(f'{RAW}/epfind', exist_ok=True)
    todo = json.load(open(f'{RAW}/unlinked.json', encoding='utf-8')) if os.path.exists(f'{RAW}/unlinked.json') else []
    key = os.environ.get('YT_API_KEY')
    budget = int(os.environ.get('YT_SEARCHES', 95))
    n_yt = n_ap = 0
    for ep in todo:
        k = re.sub(r'\W+', '-', (ep['show'] + '-' + ep['t']).lower())[:120]
        dest = f'{RAW}/epfind/{k}.json'
        rec = json.load(open(dest, encoding='utf-8')) if os.path.exists(dest) else {}
        if key and 'yt' not in rec and ep.get('yt', True) and budget > 0:
            budget -= 1
            d = date.fromisoformat(ep['date'])
            q = {'part': 'snippet', 'type': 'video', 'maxResults': 5, 'q': ep['t'], 'key': key,
                 'publishedAfter': (d - timedelta(days=7)).isoformat() + 'T00:00:00Z', 'publishedBefore': (d + timedelta(days=8)).isoformat() + 'T00:00:00Z'}
            if ep['show'] in SHOW_CHANNEL_IDS:
                q['channelId'] = SHOW_CHANNEL_IDS[ep['show']]
            try:
                r = json.loads(get('https://www.googleapis.com/youtube/v3/search?' + urllib.parse.urlencode(q)))
                best = None
                for it in r.get('items', []):
                    sn = it['snippet']
                    if _similar(sn['title'], ep['t']) >= 0.8 and (ep['show'] in SHOW_CHANNEL_IDS or any(w in sn['channelTitle'].lower() for w in ep['show'].lower().split() if len(w) > 3)):
                        best = it['id']['videoId']
                        break
                rec['yt'] = None
                if best:
                    v = json.loads(get(f'https://www.googleapis.com/youtube/v3/videos?part=status,contentDetails&id={best}&key={key}'))
                    st = (v.get('items') or [{}])[0].get('status', {})
                    if st.get('embeddable') and st.get('privacyStatus') == 'public':
                        rec['yt'] = best
                        n_yt += 1
            except Exception as e:
                print('  search failed', ep['t'][:50], e, flush=True)
                if '403' in str(e):
                    budget = 0          # quota used up for today
            time.sleep(0.3)
        if 'apple' not in rec and not rec.get('yt'):
            try:
                r = json.loads(get('https://itunes.apple.com/search?' + urllib.parse.urlencode({'term': ep['t'], 'entity': 'podcastEpisode', 'limit': 10})))
                rec['apple'] = None
                for it in r.get('results', []):
                    if _similar(it.get('collectionName', ''), ep['show']) >= 0.8 and _similar(it.get('trackName', ''), ep['t']) >= 0.85:
                        rec['apple'] = it.get('trackViewUrl')
                        n_ap += 1
                        break
            except Exception as e:
                print('  apple failed', ep['t'][:50], e, flush=True)
            time.sleep(3.2)             # the iTunes Search API allows about 20 calls a minute
        json.dump(rec, open(dest, 'w', encoding='utf-8'))
    print('epfind: youtube', n_yt, 'apple', n_ap, 'of', len(todo), flush=True)


if __name__ == '__main__':
    for w in sys.argv[1:] or ['pod', 'yt', 'search', 'loc']:
        {'yt': yt, 'search': search, 'loc': loc, 'pod': pod, 'wiki': wiki, 'epfind': epfind, 'gdelt': gdelt}[w]()
