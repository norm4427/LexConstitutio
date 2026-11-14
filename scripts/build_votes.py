"""Build docs/data/votes.js: each justice's vote for every case in docs/data/scotus.js that the
Supreme Court Database covers (Spaeth et al., Supreme Court Database, Version 2025 Release 01 and Legacy 07).

Input: data/raw/scdb/csv/SCDB_2025_01_justiceCentered_Citation.csv and SCDB_Legacy_07_justiceCentered_Citation.csv
       (downloaded from http://scdb.wustl.edu/_brickFiles/<release>/<file>.csv.zip)
Output: window.VOTES = {src, j: [justice names], c: {caseId: [majVotes, minVotes, [[justiceIdx, flag], ...] majority, [...] minority]}}
        flag: 1 wrote the majority/plurality opinion, 2 wrote a concurrence, 3 wrote a dissent, 0 joined.
Cases the database misses (chiefly terms decided after the release) are filled from the lineup paragraph of the Court's own
opinion PDF ("ROBERTS, C. J., delivered the opinion of the Court, in which ... joined. KAGAN, J., filed a dissenting opinion ..."),
using the term's membership from the database; PDFs and their text are cached in data/raw/slip/.
Run from the repo root:  python scripts/build_votes.py
"""
import csv, json, os, re, subprocess, time, urllib.request

FILES = ['data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2025_01_justiceCentered_Citation.csv']
SPECIAL = {'SDOConnor': "O'Connor", 'JMarshall': 'John Marshall', 'TMarshall': 'Thurgood Marshall', 'JHarlan1': 'John M. Harlan (I)',
           'JHarlan2': 'John M. Harlan (II)', 'JGRoberts': 'Roberts', 'OJRoberts': 'Owen J. Roberts', 'KBJackson': 'Jackson',
           'RHJackson': 'Robert H. Jackson', 'HHJackson': 'Howell E. Jackson', 'WJohnson': 'William Johnson', 'TJohnson': 'Thomas Johnson',
           'JRutledge': 'John Rutledge', 'WBRutledge': 'Wiley B. Rutledge', 'PPBarbour': 'Barbour', 'NClifford': 'Clifford'}


def display(code):
    if code in SPECIAL:
        return SPECIAL[code]
    m = re.search(r'((?:Mc|Mac|De|Van)?[A-Z][a-z].*)$', code)
    return re.sub(r'[0-9]+$', '', m.group(1) if m else code)


def roster_by_term(rows, idx_of):
    """Justices (display names) who voted in each term, from the SCDB rows."""
    terms = {}
    for rs in rows.values():
        for r in rs:
            if r['justiceName']:
                terms.setdefault(r['term'], set()).add(display(r['justiceName']))
    return terms


def slip_text(cid, url):
    path = 'data/raw/slip/' + cid.replace('/', '_')
    if not os.path.exists(path + '.txt'):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0'})
            open(path + '.pdf', 'wb').write(urllib.request.urlopen(req, timeout=90).read())
            subprocess.run(['pdftotext', '-q', '-l', '40', path + '.pdf', path + '.txt'], check=True)
            os.remove(path + '.pdf')
            time.sleep(0.5)
        except Exception as e:
            print('  slip fetch failed', cid, e)
            open(path + '.txt', 'w').close()
    return open(path + '.txt', encoding='utf-8', errors='replace').read()


NAME = r"[A-Z][A-Za-z'’]+"
TITLE = r'(?:C\.\s*J\.|JJ?\.)'


def names_in(s, roster):
    """Justice surnames mentioned in s, matched against the term roster (case-insensitive)."""
    found = []
    for tok in re.findall(NAME, s):
        t = tok.replace('’', "'")
        for r in roster:
            last = r.split()[-1].split('(')[0] if '(' not in r else r.split()[-2]
            if t.lower() == last.lower() or t.lower() == r.lower():
                if r not in found:
                    found.append(r)
    return found


def parse_lineup(text, roster):
    text = re.sub(r'[­�]', '', text)
    text = re.sub(r'\bf(?:i|ﬁ)?led\b', 'filed', text)
    m = re.search(r'(' + NAME + r',\s*' + TITLE + r',?\s*(?:delivered the opinion of the Court|announced the judgment of the Court)|PER CURIAM)', text)
    if not m:
        return None
    para = text[m.start(): m.start() + 2500]
    para = re.split(r'\n\s*\n(?=[A-Z][a-z]+ [A-Z])|argued the cause|Opinion of the Court\n', para)[0]
    para = re.sub(r'\s+', ' ', para)
    sents = re.split(r'(?<=\.)\s+(?=' + NAME + r',\s*' + TITLE + r')', para)
    author, maj_join, concur, dissent, out = None, [], [], [], []
    for st in sents:
        filer = names_in(st.split(',')[0], roster)
        if re.search(r'delivered the opinion of the Court|announced the judgment', st) and filer:
            author = filer[0]
            j = re.search(r'in which (.*?)joined', st)
            if j: maj_join += names_in(j.group(1), roster)
        elif 'dissenting opinion' in st and 'concurring in part' not in st:
            dissent += names_in(re.sub(r'\bpost\b.*', '', st), roster)
            out += filer
        elif 'concurring' in st and filer:
            concur += filer
        if 'took no part' in st:
            out += names_in(st.split('took no part')[0], roster)
    nonpart = set(n for n in names_in(' '.join(s for s in sents if 'took no part' in s), roster))
    minority = [n for n in dict.fromkeys(dissent) if n not in nonpart]
    majority = [n for n in sorted(roster) if n not in minority and n not in nonpart]
    if not author:   # per curiam opinions carry no lineup paragraph; don't guess
        return None
    return majority, minority, author, set(concur), set(out) - nonpart


def main():
    s = open('docs/data/scotus.js', encoding='utf-8').read()
    cases = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['cases']
    by_cite, by_docket = {}, {}
    for c in cases:
        if c.get('cit') and '___' not in c['cit']:
            by_cite.setdefault(c['cit'], []).append(c['id'])
        if c.get('d') and c.get('t'):
            by_docket[(str(c['t']), c['d'].strip().lower())] = c['id']

    rows = {}   # scdb caseId -> list of rows
    for f in FILES:
        for r in csv.DictReader(open(f, encoding='latin-1')):
            rows.setdefault(r['caseId'], []).append(r)

    names, idx, out = [], {}, {}
    for cid, rs in rows.items():
        r0 = rs[0]
        targets = by_cite.get(r0['usCite'].strip()) or []
        if not targets:
            t = by_docket.get((r0['term'], r0['docket'].strip().lower()))
            targets = [t] if t else []
        if not targets or not r0['majVotes'].isdigit():
            continue
        maj, mino = [], []
        seen = set()
        for r in rs:
            if not r['justiceName'] or r['justiceName'] in seen:
                continue
            seen.add(r['justiceName'])
            code = r['justiceName']
            if code not in idx:
                idx[code] = len(names); names.append(display(code))
            wrote = r['opinion'] == '2'
            if r['majority'] == '2':
                flag = 1 if r['justice'] == r['majOpinWriter'] else (2 if wrote else 0)
                maj.append([idx[code], flag])
            elif r['majority'] == '1':
                mino.append([idx[code], 3 if wrote else 0])
        if not maj:
            continue
        rec = [int(r0['majVotes']), int(r0['minVotes'] or 0), maj, mino]
        for t in targets:
            out.setdefault(t, rec)
    # ---- fill gaps from opinion PDFs
    terms = roster_by_term(rows, idx)
    latest = max(terms, key=int)
    added = 0
    for c in cases:
        if c['id'] in out or not c.get('dec') or not c.get('pdf') or 'supremecourt.gov' not in c['pdf']:
            continue
        roster = terms.get(str(c.get('t'))) or terms[latest]
        res = parse_lineup(slip_text(c['id'], c['pdf']), roster)
        if not res:
            continue
        majority, minority, author, concur, dis_filers = res
        for n in majority + minority:
            if n not in names: names.append(n)
        idx2 = {n: i for i, n in enumerate(names)}
        maj = [[idx2[n], 1 if n == author else (2 if n in concur else 0)] for n in majority]
        mino = [[idx2[n], 3 if n in dis_filers else 0] for n in minority]
        out[c['id']] = [len(maj), len(mino), maj, mino, 1]   # 5th element: from the opinion PDF
        added += 1
    print(f'filled {added} more from opinion PDFs')
    data = {'src': 'Supreme Court Database, Version 2025 Release 01 and Legacy 07 (Spaeth et al.); lineups from the Court opinions for later cases', 'j': names, 'c': out}
    open('docs/data/votes.js', 'w', encoding='utf-8').write('window.VOTES=' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';')
    print(f'votes for {len(out)} of {len(cases)} cases; {len(names)} justices; {len(json.dumps(data)) / 1024:.0f} KB')


if __name__ == '__main__':
    main()
