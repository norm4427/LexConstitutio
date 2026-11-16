"""Cache the merits briefs (and, for decided cases, the slip opinion) of every Supreme Court case whose supremecourt.gov
docket page links its filings, for build_authorities.py.

supremecourt.gov links filings as PDFs from the docket pages of cases docketed from about October Term 2016 on; older
docket pages list the filings without documents, so earlier cases have no briefs here.
Docket pages: data/raw/docket/hist/<docket>.html (dockets_fetch.py) and data/raw/docket/d-<docket>.html (docket.sh).
Which filings: after the grant, the brief of the petitioner(s)/appellant(s), of the respondent(s)/appellee(s), the reply
brief, and the brief of the United States (as a party or as amicus curiae). Other amicus briefs are not fetched.
Slip opinions: the "pdf" of each decided case in docs/data/scotus.js when it is a supremecourt.gov opinion PDF.
Output: data/raw/briefs/<docket>/<kind>[-n].txt (pdftotext -enc UTF-8; the PDF is deleted),
        data/raw/briefs/<docket>/opinion.txt, data/raw/briefs/manifest.json
Resumable; about one request per second.  Run from the repo root:  python scripts/briefs_fetch.py
"""
import glob, html, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime

OUT = 'data/raw/briefs'
UA = {'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0 (academic research index)'}
MON = '(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
GRANT = re.compile(r'(Petition (?:for (?:a )?writ of certiorari )?GRANTED|JURISDICTION (?:NOTED|POSTPONED)|CERTIORARI GRANTED|Motion for leave to file (?:a )?bill of complaint GRANTED)', re.I)
KINDS = [
    ('petitioner', re.compile(r'^Brief (?:of|for) (?:the )?(?:federal )?(?:petitioners?|appellants?|plaintiffs?)\b(?!.*(?:in opposition|amic|reply|supplemental))', re.I)),
    ('respondent', re.compile(r'^Brief (?:of|for) (?:the )?(?:federal )?(?:respondents?|appellees?|defendants?)\b(?!.*(?:in opposition|amic|supplemental))', re.I)),
    ('reply', re.compile(r'^(?:Reply (?:brief )?of (?:the )?(?:petitioners?|appellants?)|Reply brief (?:of|for) (?:the )?(?:petitioners?|appellants?))\b(?!.*supplemental)', re.I)),
    ('united-states', re.compile(r'^Brief (?:of )?amicus curiae (?:of )?(?:the )?United States\b', re.I)),
]


def get(url, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def to_text(url, dest):
    if os.path.exists(dest):
        return True
    pdf = dest[:-4] + '.pdf'
    try:
        b = get(url)
        if not b.startswith(b'%PDF'):
            return False
        open(pdf, 'wb').write(b)
        subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', pdf, dest], check=True)
        return True
    except Exception as e:
        print('  failed', url, e, flush=True)
        return False
    finally:
        if os.path.exists(pdf):
            os.remove(pdf)
        time.sleep(0.8)


def filings(raw):
    """(date, description, main-document url) for each docket entry that links a document."""
    out = []
    for m in re.finditer(r'<td class="ProceedingDate">([^<]+)</td>\s*<td>(.*?)</td>', raw, re.S):
        date, cell = m.group(1).strip(), m.group(2)
        desc = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', re.split(r'<br|<span class="documentlinks"', cell, 1, flags=re.I)[0]))).strip()
        links = re.findall(r'<a\s+href=\s*"?([^"\s>]+\.pdf)"?[^>]*>\s*([^<]+?)\s*</a>', cell, re.I)
        main = next((u for u, t in links if t.strip() in ('Main Document', 'Brief')), links[0][0] if links else None)
        try:
            d = datetime.strptime(re.sub(r'\s+', ' ', date), '%b %d %Y')
        except ValueError:
            d = None
        out.append((d, desc, main))
    return out


def merits(raw):
    E = filings(raw)
    grant = next((d for d, t, _ in E if d and GRANT.search(t)), None)
    got, n = [], {}
    for d, t, url in E:
        if not url or (grant and d and d < grant):
            continue
        for k, rx in KINDS:
            if rx.search(t):
                n[k] = n.get(k, 0) + 1
                got.append({'k': k, 'f': k if n[k] == 1 else f'{k}-{n[k]}', 'label': re.sub(r'\s*\bfiled\b.*$', '', t), 'date': d.strftime('%Y-%m-%d') if d else '', 'url': url})
                break
    return got


def main():
    os.makedirs(OUT, exist_ok=True)
    pages = {}
    for p in glob.glob('data/raw/docket/hist/*.html'):
        pages[os.path.basename(p)[:-5].lower()] = p
    for p in glob.glob('data/raw/docket/d-*.html'):
        pages[os.path.basename(p)[2:-5].lower()] = p      # pending dockets are fresher
    s = open('docs/data/scotus.js', encoding='utf-8').read()
    S = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    op = {}
    for c in S['cases']:
        if c.get('d') and c.get('dec') and re.match(r'https://www\.supremecourt\.gov/opinions/\d+pdf/', c.get('pdf') or ''):
            for dk in re.split(r'[,;\s]+', c['d'].lower()):
                op.setdefault(dk, c['pdf'])
    manifest = {}
    todo = sorted(pages)
    for i, dk in enumerate(todo):
        raw = open(pages[dk], encoding='utf-8', errors='replace').read()
        if 'DocketPDF' not in raw:
            continue
        bs = merits(raw)
        if not bs:
            continue
        os.makedirs(f'{OUT}/{dk}', exist_ok=True)
        for b in bs:
            b['ok'] = to_text(b['url'], f"{OUT}/{dk}/{b['f']}.txt")
        if dk in op:
            to_text(op[dk], f'{OUT}/{dk}/opinion.txt')
        manifest[dk] = {'briefs': [b for b in bs if b['ok']], 'opinion': op.get(dk) if os.path.exists(f'{OUT}/{dk}/opinion.txt') else None}
        if i % 25 == 0:
            print(i, '/', len(todo), dk, len(bs), 'briefs', flush=True)
            json.dump(manifest, open(f'{OUT}/manifest.json', 'w'), indent=0)
    json.dump(manifest, open(f'{OUT}/manifest.json', 'w'), indent=0)
    print('done', len(manifest), 'dockets with briefs;', sum(len(v['briefs']) for v in manifest.values()), 'briefs;',
          sum(1 for v in manifest.values() if v['opinion']), 'opinions', flush=True)


def prelim_opinions():
    """Opinions the site has no slip-opinion PDF for. supremecourt.gov's yearly opinion lists
    (https://www.supremecourt.gov/opinions/slipopinion/<yy>) link some Terms' opinions only into the preliminary print
    of the U.S. Reports, a whole-volume PDF with a #page= anchor; each opinion runs from its page to the page before the
    next opinion in that volume. Text goes to data/raw/briefs/<docket>/opinion.txt; the manifest's "opinion" is the
    anchored link."""
    man = json.load(open(f'{OUT}/manifest.json'))
    os.makedirs(f'{OUT}/pp', exist_ok=True)
    rows = []
    for yy in range(16, 26):
        lp = f'{OUT}/slip-{yy}.html'
        if not os.path.exists(lp):
            try:
                open(lp, 'wb').write(get(f'https://www.supremecourt.gov/opinions/slipopinion/{yy}'))
            except Exception as e:
                print('list failed', yy, e)
                continue
            time.sleep(1)
        h = open(lp, encoding='utf-8', errors='replace').read()
        for tr in re.findall(r'<tr>(.*?)</tr>', h, re.S):
            td = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
            m = re.search(r"href='(/opinions/preliminaryprint/[^'#]+\.pdf)#page=(\d+)'", tr)
            if len(td) >= 3 and m:
                dk = re.sub(r'<[^>]+>', '', td[2]).strip().lower()
                rows.append((dk, m.group(1), int(m.group(2))))
    starts = {}
    for dk, vol, p in rows:
        starts.setdefault(vol, set()).add(p)
    for dk, vol, p in rows:
        if dk not in man or man[dk].get('opinion'):
            continue
        dest = f'{OUT}/{dk}/opinion.txt'
        nxt = min([q for q in starts[vol] if q > p] or [p + 80])
        last = min(nxt - 1, p + 120)
        pdf = f"{OUT}/pp/{vol.rsplit('/', 1)[1]}"
        if not os.path.exists(pdf):
            try:
                open(pdf, 'wb').write(get('https://www.supremecourt.gov' + vol, timeout=600))
                time.sleep(1)
            except Exception as e:
                print('volume failed', vol, e)
                continue
        if not os.path.exists(dest):
            subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', '-f', str(p), '-l', str(last), pdf, dest])
        if os.path.exists(dest):
            man[dk]['opinion'] = f'https://www.supremecourt.gov{vol}#page={p}'
            print('opinion', dk, vol, p, last, flush=True)
    # the same lists link other Terms' slip opinions directly (/opinions/<yy>pdf/...): use them where the site has none
    for lp in sorted(glob.glob(f'{OUT}/slip-*.html')):
        h = open(lp, encoding='utf-8', errors='replace').read()
        for tr in re.findall(r'<tr>(.*?)</tr>', h, re.S):
            td = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
            m = re.search(r"href='(/opinions/\d+pdf/[^'#]+\.pdf)'", tr)
            if len(td) < 3 or not m:
                continue
            dk = re.sub(r'<[^>]+>', '', td[2]).strip().lower()
            if dk not in man or man[dk].get('opinion'):
                continue
            url = 'https://www.supremecourt.gov' + m.group(1)
            if to_text(url, f'{OUT}/{dk}/opinion.txt'):
                man[dk]['opinion'] = url
                print('opinion', dk, url, flush=True)
    json.dump(man, open(f'{OUT}/manifest.json', 'w'), indent=0)


if __name__ == '__main__':
    if '--prelim' in sys.argv:
        prelim_opinions()
    else:
        main()
        prelim_opinions()
