"""Build docs/data/justices.js: every Supreme Court justice with full name, years, positions, appointing president,
portrait (Wikimedia Commons, with its licence) and a short biography (the lead of the justice's Wikipedia article,
CC BY-SA 4.0), keyed to the Supreme Court Database's justice codes so votes and opinion authorship can link to them.

Sources: Wikipedia, "List of justices of the Supreme Court of the United States" (cached by pronounce_fetch.py in
data/raw/pron/list.json); Wikipedia REST page summaries and the Commons API (cached in data/raw/justices/).
Run from the repo root after build_votes.py:  python scripts/build_justices.py
"""
import csv, json, os, re, time, unicodedata, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build script)'}
CACHE = 'data/raw/justices'


def get(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, 'code', None) == 404:
                return None
            time.sleep(10 * (attempt + 1))
    return None


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c))


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', fold(s).lower()).strip('-')


def parse_list():
    text = list(json.load(open('data/raw/pron/list.json', encoding='utf-8')).values())[0][1]
    table = text[text.index('{|class="wikitable sortable'):]
    table = table[:table.index('\n|}')]
    rows, appointer = [], None
    for chunk in re.split(r'\n\|-[^\n]*', table)[1:]:
        cells = [c.strip() for c in re.split(r'\n\|', '\n' + chunk.strip()) if c.strip()]
        cells = [c.replace("'''", '') for c in cells]   # sitting justices are bolded
        if len(cells) < 8 or not re.match(r'^\d+$', cells[0]):
            continue
        img = re.search(r'\[\[File:([^|\]]+)', cells[1])
        sn = re.search(r'\{\{sortname\|([^|}]*)\|([^|}]*)(?:\|([^|}=]*))?(?:\|dab=([^}]*))?\}\}', cells[2])
        if not sn:
            continue
        first, last, link, dab = sn.groups()
        name = f'{first} {last}'.strip()
        title = link or (f'{name} ({dab})' if dab else name)
        years = re.search(r'\((\d{4})\s*[–-]\s*(\d{4})?\)', cells[2]) or re.search(r'\(born (\d{4})()\)', cells[2])
        pos = 'Chief Justice' if 'Chief' in cells[4] else 'Associate Justice'
        dates = re.findall(r'(?:\{\{dts\|)?([A-Z][a-z]+ \d{1,2}, \d{4})', cells[7])
        appt = next((c for c in cells[9:] if 'sortname' in c), None)
        if appt:
            a = re.search(r'\{\{sortname\|([^|}]*)\|([^|}]*)', appt); appointer = f'{a.group(1)} {a.group(2)}'
        rows.append({'no': int(cells[0]), 'name': name, 'first': first, 'last': last, 'title': title, 'img': img.group(1).strip() if img else None,
                     'born': years.group(1) if years else None, 'died': (years.group(2) or None) if years else None, 'pos': pos,
                     'start': dates[0] if dates else None, 'end': dates[1] if len(dates) > 1 else None, 'appointer': appointer})
    return rows


def scdb_codes():
    codes = {}
    for f in ('data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv'):
        for r in csv.DictReader(open(f, encoding='latin-1')):
            if r['justiceName']:
                c = codes.setdefault(r['justiceName'], {'num': int(r['justice']), 'first': r['term'], 'last': r['term']})
                c['first'] = min(c['first'], r['term'], key=int); c['last'] = max(c['last'], r['term'], key=int)
    return codes


def main():
    os.makedirs(CACHE, exist_ok=True)
    rows = parse_list()
    # merge repeat appointments (Rutledge, White, Hughes, Stone, Rehnquist as chief) into one person
    people = {}
    for r in rows:
        p = people.setdefault(r['title'], {**r, 'roles': []})
        p['roles'].append({'pos': r['pos'], 'start': r['start'], 'end': r['end'], 'appointer': r['appointer']})
        if r['img'] and not p.get('img'):
            p['img'] = r['img']
    people = list(people.values())

    # SCDB code -> person: surname match, then initials, then service years
    codes = scdb_codes()
    def code_last(code):
        m = re.search(r'((?:Mc|Mac|De|Van)?[A-Z][a-z].*?)(\d*)$', code)
        return m.group(1) if m else code
    for code, info in codes.items():
        last = code_last(code)
        if code == 'SDOConnor': last = 'Connor'
        base = lambda p: re.sub(r',?\s+(?:Jr\.?|Sr\.?|II|III)$', '', p['last'])
        cands = [p for p in people if fold(base(p)).replace("'", '').replace(' ', '').lower().endswith(fold(last).lower())]
        num = re.search(r'(\d+)$', code)
        if len(cands) > 1 and num and code.rstrip('0123456789').endswith('Harlan'):   # SCDB numbers the two John Marshall Harlans
            cands = sorted(cands, key=lambda p: p['no'])[int(num.group(1)) - 1:int(num.group(1))]
        if len(cands) > 1:
            initials = code[:len(code) - len(last) - len(re.search(r'\d*$', code).group(0))]
            init_match = [p for p in cands if initials and fold(''.join(w[0] for w in re.findall(r'[A-Za-z]+', p['first']))).upper().startswith(initials[:1])
                          and all(ch in ''.join(w[0] for w in re.findall(r'[A-Za-z]+', p['first'])).upper() for ch in initials)]
            cands = init_match or cands
        if len(cands) > 1:   # still ambiguous: the one serving in the code's first term
            yr = int(info['first'])
            cands = sorted(cands, key=lambda p: min(abs(int(re.search(r'\d{4}', x['start']).group(0)) - yr) for x in p['roles'] if x['start']))
        if cands:
            cands[0].setdefault('codes', []).append(code)
        else:
            print('unmatched SCDB code', code)

    # summaries and portraits
    sum_cache = f'{CACHE}/summaries.json'
    sums = json.load(open(sum_cache, encoding='utf-8')) if os.path.exists(sum_cache) else {}
    for p in people:
        if p['title'] not in sums:
            sums[p['title']] = get('https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(p['title'].replace(' ', '_')))
            time.sleep(0.4)
    json.dump(sums, open(sum_cache, 'w', encoding='utf-8'), ensure_ascii=False)
    img_cache = f'{CACHE}/images.json'
    imgs = json.load(open(img_cache, encoding='utf-8')) if os.path.exists(img_cache) else {}
    files = [p['img'] for p in people if p.get('img') and p['img'] not in imgs]
    for i in range(0, len(files), 40):
        batch = files[i:i + 40]
        d = get('https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'format': 'json', 'formatversion': 2,
              'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 400, 'titles': '|'.join('File:' + f for f in batch)})) or {}
        norm = {x['to']: x['from'] for x in d.get('query', {}).get('normalized', [])}
        for pg in d.get('query', {}).get('pages', []):
            ii = (pg.get('imageinfo') or [{}])[0]
            md = ii.get('extmetadata') or {}
            strip = lambda v: re.sub(r'<[^>]+>', '', (md.get(v) or {}).get('value') or '').strip()
            fname = norm.get(pg['title'], pg['title'])[5:]
            imgs[fname] = {'thumb': ii.get('thumburl'), 'page': ii.get('descriptionurl'), 'license': strip('LicenseShortName'),
                           'artist': strip('Artist')[:120]}
        time.sleep(1)
    json.dump(imgs, open(img_cache, 'w', encoding='utf-8'), ensure_ascii=False)

    out, by_code = [], {}
    for p in sorted(people, key=lambda p: p['no']):
        s = sums.get(p['title']) or {}
        im = imgs.get(p.get('img') or '', {})
        jid = slug(p['name'] if sum(1 for q in people if q['name'] == p['name']) == 1 else p['title'])
        rec = {'id': jid, 'name': p['name'], 'last': p['last'], 'born': p['born'], 'died': p['died'], 'roles': p['roles'],
               'bio': s.get('extract'), 'wiki': (s.get('content_urls') or {}).get('desktop', {}).get('page'),
               'img': im.get('thumb'), 'imgPage': im.get('page'), 'imgLicense': im.get('license'), 'codes': p.get('codes', [])}
        out.append(rec)
        for c in rec['codes']:
            by_code[c] = jid
    data = {'src': 'Wikipedia (list of justices; biographies CC BY-SA 4.0); portraits from Wikimedia Commons', 'justices': out, 'byCode': by_code}
    open('docs/data/justices.js', 'w', encoding='utf-8').write('window.JUSTICES=' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';')
    lic = {}
    for r in out:
        lic[r['imgLicense'] or 'none'] = lic.get(r['imgLicense'] or 'none', 0) + 1
    print(f"{len(out)} justices; with SCDB codes {sum(1 for r in out if r['codes'])}; portraits {sum(1 for r in out if r['img'])}; bios {sum(1 for r in out if r['bio'])}")
    print('portrait licences:', lic)


if __name__ == '__main__':
    main()
