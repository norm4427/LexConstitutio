"""Find more lecture and explainer videos for the Beginner's Guide topics with the YouTube Data API (YT_API_KEY in the
environment; the key is never written to disk). For each topic in scripts/guide.json, three searches (embeddable videos
only, English); a result is kept only when
  - its channel is an established legal or educational publisher (CHANNELS below: law schools, universities, the
    National Constitution Center, C-SPAN, the Federalist Society, the American Constitution Society, and the like);
  - its title matches the topic (the topic's articleRx, or the query's key phrase);
  - it is public, embeddable and between 4 minutes and 3 hours long.
Results are cached in data/raw/guide_yt/ and added to docs/data/lectures.js with a `gt` (guide topic) tag, which
guide_lectures.py places on that topic's lecture shelf. Search costs 100 quota units: 60 searches use ~6,000 of the
10,000 free daily units. Run from the repo root:
  YT_API_KEY=... python scripts/guide_videos.py && python scripts/guide_lectures.py && sh scripts/stamp.sh
"""
import json, os, re, time, urllib.parse, urllib.request

KEY = os.environ.get('YT_API_KEY')
RAW = 'data/raw/guide_yt'
CHANNELS = {
    'the federalist society', 'national constitution center', 'stanford law school', 'harvard law school', 'yalecourses',
    'university of chicago law school', 'hoover institution', 'american constitution society', 'crashcourse', 'yale university',
    'pbs newshour', 'open to debate', 'khan academy', 'the heritage foundation', 'annenberg classroom', 'nyu school of law',
    'stanford', 'university of virginia school of law', 'vanderbilt law school', 'the cato institute', 'yale law school',
    'c-span', 'library of congress', 'notre dame law school', 'center for civic education', 'pacific legal foundation',
    'bill of rights institute', 'institute for justice', 'columbia law school', 'georgetown law', 'berkeley law',
    'penn carey law', 'michigan law', 'duke law', 'ucla law', 'northwestern pritzker school of law', 'cornell law school',
    'brookings institution', 'american enterprise institute', 'aei', 'the federalist society videos', 'supreme court historical society',
    'national archives', 'the national archives', 'iCivics'.lower(), 'oyez', 'legal information institute', 'scotusblog',
    'the dispatch', 'intelligence squared u.s.', 'cato institute', 'manhattan institute', 'mercatus center', 'fire',
    'foundation for individual rights and expression', 'aclu', 'brennan center for justice', 'constitutional accountability center',
    'university of chicago', 'harvard university', 'princeton university', 'mit opencourseware', 'the university of chicago',
    'federal judicial center', 'u.s. national archives', 'hillsdale college', 'hillsdale digital', 'learn liberty',
    'josh blackman', 'lawshelf', 'the c. boyden gray center george mason university', 'mr. beat', "heimler's history", 'the cooper union',
}
EXTRA = {   # a third query per topic, aimed at the doctrine's core cases and terms
    'judicial-review': 'Marbury v. Madison judicial review lecture', 'interpretation': 'originalism living constitutionalism debate',
    'incorporation': 'incorporation doctrine Fourteenth Amendment Bill of Rights', 'separation-of-powers': 'separation of powers appointments removal power',
    'executive-power': 'unitary executive presidential power Article II', 'federalism': 'federalism anti-commandeering Tenth Amendment',
    'commerce-clause': 'Commerce Clause Wickard Lopez NFIB', 'standing': 'Article III standing doctrine justiciability',
    'administrative-state': 'nondelegation doctrine Chevron major questions', 'free-speech': 'First Amendment free speech doctrine lecture',
    'religion': 'Establishment Clause Free Exercise Clause', 'second-amendment': 'Second Amendment Heller Bruen',
    'equal-protection': 'Equal Protection Clause strict scrutiny', 'due-process': 'substantive due process unenumerated rights',
    'fourth-amendment': 'Fourth Amendment search and seizure exclusionary rule', 'trial-rights': 'Miranda right to counsel Sixth Amendment Gideon',
    'punishment': 'Eighth Amendment cruel and unusual punishment death penalty', 'takings': 'Takings Clause eminent domain Kelo just compensation',
    'voting': 'Voting Rights Act gerrymandering Supreme Court', 'war-powers': 'war powers Congress president commander in chief',
}


KW = {   # extra title terms per topic, beyond scripts/guide.json's articleRx
    'takings': r'kelo|eminent domain|takings|regulatory taking', 'voting': r'election|voting|vote|gerrymander|redistricting|ballot',
    'war-powers': r'war|national security|terror|military', 'standing': r'standing|justiciab|political question|article iii|ripeness|mootness',
    'punishment': r'eighth amendment|death penalty|punishment|execution|sentenc', 'trial-rights': r'miranda|gideon|counsel|jury|sixth amendment|self-incrimination|fifth amendment',
    'commerce-clause': r'commerce|wickard|lopez|spending power|necessary and proper', 'second-amendment': r'second amendment|gun|heller|bruen|bear arms',
}


def api(path, **q):
    q['key'] = KEY
    url = f'https://www.googleapis.com/youtube/v3/{path}?' + urllib.parse.urlencode(q)
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'LexConstitutio/1.0'}), timeout=60))


def secs(iso):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    return sum(int(x or 0) * f for x, f in zip(m.groups(), (3600, 60, 1))) if m else 0


def clock(s):
    h, m, x = s // 3600, s % 3600 // 60, s % 60
    return f'{h}:{m:02d}:{x:02d}' if h else f'{m}:{x:02d}'


def search_topic(g):
    p = f"{RAW}/{g['id']}.json"
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    queries = [f"{g['title']} constitutional law lecture", f"{g['title']} Supreme Court explained", EXTRA.get(g['id'], g['title'])]
    hits = {}
    for q in queries:
        r = api('search', part='snippet', type='video', videoEmbeddable='true', relevanceLanguage='en', safeSearch='strict',
                maxResults=25, q=q)
        for it in r.get('items', []):
            sn = it['snippet']
            hits.setdefault(it['id']['videoId'], {'t': sn['title'], 'ch': sn['channelTitle'], 'q': q, 'date': sn.get('publishedAt', '')[:10]})
        time.sleep(0.3)
    ids = list(hits)
    for k in range(0, len(ids), 50):
        r = api('videos', part='contentDetails,statistics,status', id=','.join(ids[k:k + 50]))
        for it in r.get('items', []):
            h = hits[it['id']]
            h['sec'] = secs(it['contentDetails'].get('duration'))
            h['v'] = int(it['statistics'].get('viewCount') or 0)
            h['ok'] = bool(it['status'].get('embeddable')) and it['status'].get('privacyStatus') == 'public'
    os.makedirs(RAW, exist_ok=True)
    json.dump(hits, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    return hits


def main():
    import html
    if not KEY:
        raise SystemExit('set YT_API_KEY')
    G = json.load(open('scripts/guide.json', encoding='utf-8'))
    s = open('docs/data/lectures.js', encoding='utf-8').read()
    L = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    have = {v['id']: v for v in L['videos']}
    added = 0
    for g in G:
        rx = re.compile(r'\b(?:' + g['articleRx'] + ')', re.I)
        hits = search_topic(g)
        keep = []
        for vid, h in hits.items():
            t = html.unescape(h['t'])
            if not h.get('ok') or not (240 <= h.get('sec', 0) <= 3 * 3600):
                continue
            if h['ch'].lower() not in CHANNELS:
                continue
            kw = KW.get(g['id'])
            if not (rx.search(t) or (kw and re.search(kw, t, re.I))):     # the video's own title must be on the topic
                continue
            keep.append((h['v'], vid, t, h))
        keep.sort(reverse=True)
        n = 0
        for views, vid, t, h in keep[:10]:
            if vid in have:
                gt = have[vid].setdefault('gt', [])
                if g['id'] not in gt:
                    gt.append(g['id'])
                continue
            have[vid] = {'id': vid, 't': t, 'ch': h['ch'], 'len': clock(h['sec']), 'sec': h['sec'], 'v': views, 'cat': [], 'gt': [g['id']], 'src': 'api'}
            L['videos'].append(have[vid])
            n += 1
        added += n
        print(f"{g['id']:22} {len(hits):3} results, {len(keep):2} from listed channels, {n} new", flush=True)
    open('docs/data/lectures.js', 'w', encoding='utf-8').write('window.LECTURES=' + json.dumps(L, ensure_ascii=False, separators=(',', ':')) + ';')
    print(added, 'videos added to the lecture collection')


if __name__ == '__main__':
    main()
