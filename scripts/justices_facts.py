"""Add appointment facts, education and career to docs/data/justices.js (run after build_justices.py).

Sources (both U.S. government works, public domain):
  Federal Judicial Center, Biographical Directory of Article III Federal Judges: the export of all judges
    (https://www.fjc.gov/sites/default/files/history/judges.csv), cached in data/raw/fjc/judges.csv. For each Supreme
    Court appointment: the nominating president, nomination, confirmation and commission dates and the Senate vote; the
    justice's schools and degrees, professional career and other federal judicial service.
  U.S. Senate, Supreme Court Nominations (1789-Present)
    (https://www.senate.gov/legislative/nominations/SupremeCourtNominations1789present.htm), cached in
    data/raw/fjc/senate_scotus.html: the roll-call tally and vote number, used where the FJC gives none and to check it.
Each role in `roles` gains nom, conf, comm, recess, rejected (ISO dates) and vote ("63–37", "voice vote"; the Senate's tally
where the two differ); the justice gains `fjc`
{url, edu: [[school, degree, year]], career: [...], other: [...]}.
Run from the repo root:  python scripts/justices_facts.py
"""
import csv, html, json, os, re, unicodedata, urllib.request

RAW = 'data/raw/fjc'
SOURCES = {'judges.csv': 'https://www.fjc.gov/sites/default/files/history/judges.csv',
           'senate_scotus.html': 'https://www.senate.gov/legislative/nominations/SupremeCourtNominations1789present.htm'}
SCOTUS = 'Supreme Court of the United States'
MONTHS = {m: i for i, m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split(), 1)}


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if not unicodedata.combining(c)).lower()


def base_last(s):
    return re.sub(r'[^a-z]', '', fold(re.sub(r',?\s+(Jr\.?|Sr\.?|II|III)$', '', s)))


def fetch():
    os.makedirs(RAW, exist_ok=True)
    for name, url in SOURCES.items():
        path = f'{RAW}/{name}'
        if not os.path.exists(path):
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (LexConstitutio static site build)'})
            open(path, 'wb').write(urllib.request.urlopen(req, timeout=120).read())


def senate_votes():
    """(surname, confirmation date) -> 'ayes–nays' from the Senate's table."""
    s = open(f'{RAW}/senate_scotus.html', encoding='utf-8', errors='replace').read()
    out = {}
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', s, re.S):
        cells = [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
        cells = [c for c in cells if c]
        if len(cells) < 5 or ',' not in cells[0]:
            continue
        vote = next((c for c in cells if re.match(r'\d+-\d+', c)), '')
        date = next((c for c in reversed(cells) if re.match(r'[A-Z][a-z]{2} \d{1,2}, \d{4}$', c)), '')
        res = next((c for c in cells if c in ('C', 'D', 'R')), '')
        if not (res and date):
            continue
        m = re.match(r'([A-Z][a-z]{2}) (\d{1,2}), (\d{4})', date)
        iso = f'{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}'
        v = re.match(r'(\d+)-(\d+)', vote)
        tally = f'{v.group(1)}–{v.group(2)}' if v else 'voice vote'
        out[(base_last(cells[0].split(',')[0]), iso)] = tally if res != 'R' else ('rejected', tally)
    return out


def main():
    fetch()
    J = json.loads(open('docs/data/justices.js', encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
    rows = [r for r in csv.DictReader(open(f'{RAW}/judges.csv', encoding='utf-8-sig', newline=''))
            if any(r.get(f'Court Name ({i})') == SCOTUS for i in range(1, 7))]
    sen = senate_votes()
    unmatched, checks = [], []
    for j in J['justices']:
        cand = [r for r in rows if base_last(r['Last Name']) == base_last(j['last']) and r['Birth Year'] == (j.get('born') or '')]
        if len(cand) != 1:
            unmatched.append(j['id']); continue
        r = cand[0]
        appts = []
        for i in range(1, 7):
            if r.get(f'Court Name ({i})') != SCOTUS:
                continue
            g = lambda k: (r.get(f'{k} ({i})') or '').strip()
            an = re.sub(r'\s+', '', g('Ayes/Nays'))
            vote = an.replace('/', '–') if re.match(r'\d+/\d+$', an) else ('voice vote' if 'voice' in g('Senate Vote Type').lower() else '')
            sv = sen.get((base_last(r['Last Name']), g('Confirmation Date')))
            sv = sv if isinstance(sv, str) else None
            if sv and vote and sv != vote:
                checks.append(f"{j['id']} {g('Confirmation Date')}: FJC {vote}, Senate {sv}")
            appts.append({'pos': g('Appointment Title'), 'pres': g('Appointing President'), 'nom': g('Nomination Date'), 'conf': g('Confirmation Date'),
                          'comm': g('Commission Date'), 'recess': g('Recess Appointment Date'), 'vote': sv or vote or ''})   # the Senate's own tally first
        for role in j['roles']:
            y = re.search(r'\d{4}', role.get('start') or '')
            a = min((a for a in appts if a['pos'] == role['pos']), default=None,
                    key=lambda a: abs(int((a['comm'] or a['conf'] or '0')[:4] or 0) - int(y.group(0) if y else 0)))
            if a:
                for k in ('nom', 'conf', 'comm', 'vote', 'recess'):
                    if a[k]:
                        role[k] = a[k]
                if a['pres'] and not role.get('appointer'):
                    role['appointer'] = a['pres']
        for role in j['roles']:   # a nomination the Senate voted down (Rutledge as chief justice, after a recess appointment)
            if not role.get('conf'):
                y = (role.get('nom') or '')[:4]
                rej = [(d, v[1]) for (ln, d), v in sen.items() if ln == base_last(r['Last Name']) and isinstance(v, tuple) and d[:4] == y]
                if rej:
                    role['rejected'], role['vote'] = rej[0]
        edu = [[r[f'School ({i})'].strip(), (r.get(f'Degree ({i})') or '').strip(), (r.get(f'Degree Year ({i})') or '').strip()]
               for i in range(1, 6) if (r.get(f'School ({i})') or '').strip()]
        career = [c.strip() for c in re.split(r';\s*', r.get('Professional Career') or '') if c.strip()]
        other = [c.strip() for i in range(1, 6) for c in re.split(r';\s*', r.get(f'Other Federal Judicial Service ({i})') or '') if c.strip()]
        lower = [f"{(r.get(f'Appointment Title ({i})') or '').strip()}, {r[f'Court Name ({i})'].strip()}, {(r.get(f'Commission Date ({i})') or '')[:4]}–{(r.get(f'Termination Date ({i})') or '')[:4]}"
                 for i in range(1, 7) if (r.get(f'Court Name ({i})') or '').strip() and r[f'Court Name ({i})'] != SCOTUS]
        j['fjc'] = {k: v for k, v in {'url': f"https://www.fjc.gov/node/{r['nid']}", 'edu': edu, 'career': career, 'other': lower + other}.items() if v}
    J['src'] = re.sub(r'\s*Appointments, education and career:.*$', '', J['src']) + \
        '; appointments, education and career: Federal Judicial Center, Biographical Directory of Article III Federal Judges, with Senate tallies from senate.gov (public domain)'
    open('docs/data/justices.js', 'w', encoding='utf-8').write('window.JUSTICES=' + json.dumps(J, ensure_ascii=False, separators=(',', ':')) + ';')
    n = len(J['justices'])
    have = lambda f: sum(1 for j in J['justices'] if f(j))
    print(f"{n} justices; FJC matched {have(lambda j: j.get('fjc'))}; unmatched: {unmatched}")
    print(f"with education {have(lambda j: (j.get('fjc') or {}).get('edu'))}, career {have(lambda j: (j.get('fjc') or {}).get('career'))}, "
          f"confirmation date {have(lambda j: any(r.get('conf') for r in j['roles']))}, commission {have(lambda j: any(r.get('comm') for r in j['roles']))}, "
          f"vote {have(lambda j: any(r.get('vote') for r in j['roles']))}")
    print('FJC and Senate tallies differ:', checks)


if __name__ == '__main__':
    main()
