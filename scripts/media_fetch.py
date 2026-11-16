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
   before 1964: pages printed in the three weeks (two months before 1870) after the decision that name the parties and the Supreme Court.
   -> data/raw/media/loc/<case>.json
Resumable.  Run from the repo root:  python scripts/media_fetch.py [yt|search|loc]   (YT_API_KEY=... for the back catalog)
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import date, timedelta

RAW = 'data/raw/media'
UA = {'User-Agent': 'LexConstitutio/1.0 (academic research index)'}
PLAYLISTS = {
    'PLDuw5W_udnx2RhekBcHhFSIpDC9TE286q': 'Advisory Opinions',
    'PLDuw5W_udnx2IqUp8Lj9_qpfCpX7W8fEz': 'SCOTUSblog',
    'PLDuw5W_udnx09k7Lt6wS_GU2BUNC-CRCe': 'SCOTUSblog Animated Explainers',
    'UUk-Km4tcqAbhpnbrvj1pJFw': 'Strict Scrutiny',
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
    for c in top_cases('2015-01-01', 500):
        dest = f"{RAW}/search/{c['id'].replace('/', '_')}.json"
        if os.path.exists(dest):
            continue
        name = re.sub(r'\s*\(\d\)$', '', c['n'])
        try:
            r = json.loads(get('https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&videoEmbeddable=true&maxResults=10&q='
                               + urllib.parse.quote_plus(f'"{name}"') + f'&key={key}'))
        except Exception as e:
            print('  search failed', c['id'], e, flush=True)
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


def loc():
    os.makedirs(f'{RAW}/loc', exist_ok=True)
    for c in top_cases('1963-12-31', int(os.environ.get('LOC_N', 150))):   # the API takes ~30 s a query
        dest = f"{RAW}/loc/{c['id'].replace('/', '_')}.json"
        if os.path.exists(dest):
            continue
        ws = party_words(c['n'])
        if not ws:
            json.dump({'skip': 'no distinctive party name'}, open(dest, 'w'))
            continue
        d = date.fromisoformat(c['dec'])
        a, b = d - timedelta(days=1), d + timedelta(days=60 if d.year < 1870 else 21)   # news travelled slower before the telegraph age
        q = ' '.join(f'"{w}"' for w in ws) + ' "supreme court"'
        url = ('https://www.loc.gov/collections/chronicling-america/?fo=json&c=12&at=results&q=' + urllib.parse.quote_plus(q) +
               f'&dates={a.isoformat()}/{b.isoformat()}')
        try:
            r = json.loads(get(url, timeout=150))
        except Exception as e:
            print('  loc failed', c['id'], e, flush=True)
            time.sleep(5)
            continue
        res = [{'date': x.get('date'), 'title': x.get('title'), 'url': x.get('url'), 'img': (x.get('image_url') or [None])[0],
                'paper': (x.get('partof_title') or [None])[0] if isinstance(x.get('partof_title'), list) else x.get('partof_title'),
                'loc': x.get('location_city') or x.get('location')} for x in r.get('results', [])]
        json.dump({'q': q, 'from': a.isoformat(), 'to': b.isoformat(), 'results': res}, open(dest, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(1.5)
    print('loc done', flush=True)


if __name__ == '__main__':
    for w in sys.argv[1:] or ['yt', 'search', 'loc']:
        {'yt': yt, 'search': search, 'loc': loc}[w]()
