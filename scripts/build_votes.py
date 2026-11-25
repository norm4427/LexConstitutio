"""Build docs/data/votes.js: each justice's vote for every case in docs/data/scotus.js that the
Supreme Court Database covers (Spaeth et al., Supreme Court Database, Version 2026 Release 01 and Legacy 07).

Input: data/raw/scdb/csv/SCDB_{2026_01,Legacy_07}_justiceCentered_{Citation,Docket}.csv
       (downloaded from http://scdb.wustl.edu/_brickFiles/<release>/<file>.csv.zip)
Output: window.VOTES = {src, j: [justice names], c: {caseId: [majVotes, minVotes, [[justiceIdx, flag], ...] majority, [...] minority]}}
        flag: 1 wrote the majority/plurality opinion, 2 wrote a concurrence, 3 wrote a dissent, 0 joined.
Cases the database misses (chiefly terms decided after the release) are filled from the lineup paragraph of the Court's own
opinion PDF ("ROBERTS, C. J., delivered the opinion of the Court, in which ... joined. KAGAN, J., filed a dissenting opinion ..."),
using the term's membership from the database; PDFs and their text are cached in data/raw/slip/.
Run from the repo root:  python scripts/build_votes.py
"""
import csv, json, os, re, subprocess, time, unicodedata, urllib.request

fold = lambda s: "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))

FILES = ['data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv']
DOCKET_FILES = ['data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Docket.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Docket.csv']
SPECIAL = {'SDOConnor': "O'Connor", 'JMarshall': 'John Marshall', 'TMarshall': 'Thurgood Marshall', 'JHarlan1': 'John M. Harlan (I)',
           'JHarlan2': 'John M. Harlan (II)', 'JGRoberts': 'Roberts', 'OJRoberts': 'Owen J. Roberts', 'KBJackson': 'Jackson',
           'RHJackson': 'Robert H. Jackson', 'HHJackson': 'Howell E. Jackson', 'WJohnson': 'William Johnson', 'TJohnson': 'Thomas Johnson',
           'JRutledge': 'John Rutledge', 'WBRutledge': 'Wiley B. Rutledge', 'PPBarbour': 'Barbour', 'NClifford': 'Clifford'}


# Lineups checked by hand against the Court's own text: (majority, minority, {justice: 1 opinion of the Court,
# 2 concurrence, 3 dissent}). Roman Catholic Diocese of Brooklyn v. Cuomo, 592 U.S. 14 (2020), per curiam: Oyez codes
# Sotomayor as not writing, but she filed a dissent joined by Kagan. Trump v. IRAP (Oct. 10, 2017 order list,
# 16-1436): vacated as moot; "Justice Sotomayor dissents from the order vacating the judgment below".
HAND = {
    '2020/20a87': (['CThomas', 'SAAlito', 'NMGorsuch', 'BMKavanaugh', 'ACBarrett'], ['JGRoberts', 'SGBreyer', 'SSotomayor', 'EKagan'],
                   {'NMGorsuch': 2, 'BMKavanaugh': 2, 'JGRoberts': 3, 'SGBreyer': 3, 'SSotomayor': 3}),
    '2017/16-1436': (['JGRoberts', 'AMKennedy', 'CThomas', 'RBGinsburg', 'SGBreyer', 'SAAlito', 'EKagan', 'NMGorsuch'], ['SSotomayor'], {}),
}


def display(code):
    if code in SPECIAL:
        return SPECIAL[code]
    m = re.search(r'((?:Mc|Mac|De|Van)?[A-Z][a-z].*)$', code)
    return re.sub(r'[0-9]+$', '', m.group(1) if m else code)


def roster_by_term(rows, idx_of):
    """Justices (display names) who voted in each term, from the SCDB rows."""
    terms, codes = {}, {}
    for rs in rows.values():
        for r in rs:
            if r['justiceName']:
                terms.setdefault(r['term'], set()).add(display(r['justiceName']))
                codes.setdefault(r['term'], {})[display(r['justiceName'])] = r['justiceName']
    return terms, codes


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


def dk_norm(d):
    """Docket numbers as one key: '21–707' / '21â70' -> '21-707'; 'No. 142, Orig.' / '22O142' / '142-orig' -> '142-orig'."""
    d = (d or '').replace('â', '-').replace('–', '-').replace('—', '-').strip().lower()
    m = re.match(r'^(?:no\.\s*)?(\d+),?\s*orig\.?$', d) or re.match(r'^\d{2}o(\d+)$', d) or re.match(r'^(\d+)-orig$', d)
    return f'{m.group(1)}-orig' if m else re.sub(r'^no\.\s*', '', d)


def main():
    s = open('docs/data/scotus.js', encoding='utf-8').read()
    cases = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['cases']
    by_cite, by_docket = {}, {}
    for c in cases:
        if c.get('cit') and '___' not in c['cit']:
            by_cite.setdefault(c['cit'], []).append(c['id'])
        if c.get('d') and c.get('t'):
            by_docket[(str(c['t']), dk_norm(c['d']))] = c['id']

    rows = {}   # scdb caseId -> list of rows
    for f in FILES:
        for r in csv.DictReader(open(f, encoding='latin-1')):
            rows.setdefault(r['caseId'], []).append(r)

    names, idx, out = [], {}, {}

    def record(rs):
        r0 = rs[0]
        if not r0['majVotes'].isdigit():
            return None
        maj, mino = [], []
        seen = set()
        for r in rs:
            if not r['justiceName'] or r['justiceName'] in seen:
                continue
            seen.add(r['justiceName'])
            code = r['justiceName']
            if code not in idx:
                idx[code] = len(names); names.append(code)
            wrote = r['opinion'] == '2'
            if r['majority'] == '2':
                flag = 1 if r['justice'] == r['majOpinWriter'] else (2 if wrote else 0)
                maj.append([idx[code], flag])
            elif r['majority'] == '1':
                mino.append([idx[code], 3 if wrote else 0])
        if not maj and any(r['vote'] == '8' for r in rs):
            # equally divided Court (affirmed 4-4): the Court does not disclose sides, so record only who took part
            part = sorted({idx[r['justiceName']] for r in rs if r['justiceName'] and r['vote'] == '8'})
            return [int(r0['majVotes']), int(r0['minVotes'] or 0), [], [], 0, part]
        if not maj:
            return None
        return [int(r0['majVotes']), int(r0['minVotes'] or 0), maj, mino]

    for cid, rs in rows.items():
        r0 = rs[0]
        targets = by_cite.get(r0['usCite'].strip()) or []
        if not targets:
            t = by_docket.get((r0['term'], dk_norm(r0['docket'])))
            targets = [t] if t else []
        rec = record(rs) if targets else None
        for t in targets if rec else []:
            out.setdefault(t, rec)
    # the docket-organized files list every docket of a consolidated case, so cases filed under a non-lead docket match too
    by_docket_rows = {}
    for f in DOCKET_FILES:
        if os.path.exists(f):
            for r in csv.DictReader(open(f, encoding='latin-1')):
                by_docket_rows.setdefault(r['docketId'], []).append(r)
    from_docket = 0
    for did, rs in by_docket_rows.items():
        t = by_docket.get((rs[0]['term'], dk_norm(rs[0]['docket'])))
        if t and t not in out:
            rec = record(rs)
            if rec:
                out[t] = rec; from_docket += 1
    print(f'matched by docket: {from_docket}')
    for cid, rs in by_docket_rows.items():
        for r in rs:
            rows.setdefault('d:' + cid, []).append(r)   # so later-term rosters include every justice
    # ---- fill gaps from opinion PDFs
    terms, term_codes = roster_by_term(rows, idx)
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
        tc = term_codes.get(str(c.get('t'))) or term_codes[latest]   # display surname -> SCDB code for that term
        for n in majority + minority:
            if tc[n] not in idx: idx[tc[n]] = len(names); names.append(tc[n])
        maj = [[idx[tc[n]], 1 if n == author else (2 if n in concur else 0)] for n in majority]
        mino = [[idx[tc[n]], 3 if n in dis_filers else 0] for n in minority]
        out[c['id']] = [len(maj), len(mino), maj, mino, 1]   # 5th element: from the opinion PDF
        added += 1
    print(f'filled {added} more from opinion PDFs')
    # ---- last resort: Oyez's per-justice votes (CC BY-NC), matched to justices by name
    if os.path.exists('docs/data/justices.js'):
        js = open('docs/data/justices.js', encoding='utf-8').read(); J = json.loads(js[js.index('=') + 1:].rstrip().rstrip(';'))
        code_of = {}
        for j in J['justices']:
            for code in j['codes']:
                key = re.sub(r'[^a-z]', '', fold(j['name']).lower())
                code_of.setdefault(key, code)
                code_of.setdefault(re.sub(r'[^a-z]', '', fold(j['name'].split()[0] + j['last']).lower()), code)
        os.makedirs('data/raw/oyez/votes', exist_ok=True)
        oy = 0
        for c in cases:
            if c['id'] in out or not c.get('dec'):
                continue
            path = 'data/raw/oyez/votes/' + c['id'].replace('/', '_') + '.json'
            if not os.path.exists(path):
                try:
                    req = urllib.request.Request('https://api.oyez.org/cases/' + c['id'], headers={'User-Agent': 'LexConstitutio/1.0'})
                    d = json.load(urllib.request.urlopen(req, timeout=60))
                    json.dump({'decisions': d.get('decisions')}, open(path, 'w', encoding='utf-8'))
                    time.sleep(0.3)
                except Exception:
                    continue
            dec = ((json.load(open(path, encoding='utf-8')).get('decisions')) or [None])[0]
            if not dec or dec.get('majority_vote') is None or not dec.get('votes'):
                continue
            maj, mino, ok = [], [], True
            for v in dec['votes']:
                m = (v or {}).get('member') or {}
                key = re.sub(r'[^a-z]', '', fold(m.get('name') or '').lower())
                # "Samuel A. Alito, Jr." / "Brett M. Kavanaugh": also try first name + surname, without initials or suffix
                toks = [t for t in re.sub(r',?\s+(Jr|Sr|II|III)\.?$', '', fold(m.get('name') or '')).split() if not re.fullmatch(r'[A-Z]\.?', t)]
                key2 = re.sub(r'[^a-z]', '', (toks[0] + toks[-1]).lower()) if len(toks) >= 2 else ''
                code = (code_of.get(key) or code_of.get(key2)
                        or code_of.get(re.sub(r'[^a-z]', '', fold((m.get('first_name') or '') + (m.get('last_name') or '')).lower())))
                if not code:
                    ok = False; break
                if code not in idx: idx[code] = len(names); names.append(code)
                op = str(v.get('opinion_type') or '')
                if v.get('vote') == 'majority':
                    maj.append([idx[code], 1 if re.search('majority|plurality', op) else 2 if 'concur' in op else 0])
                elif v.get('vote') == 'minority':
                    mino.append([idx[code], 3 if 'dissent' in op else 0])
            if ok and maj:
                out[c['id']] = [dec['majority_vote'], dec['minority_vote'], maj, mino, 2]   # 5th element 2: from Oyez
                oy += 1
        print(f'filled {oy} more from Oyez')
    # ---- hand-checked against the Court's own text (essential cases the sources above miss or miscode)
    for cid, (maj_codes, min_codes, writers) in HAND.items():
        if not any(c['id'] == cid for c in cases):
            continue
        for code in maj_codes + min_codes:
            if code not in idx: idx[code] = len(names); names.append(code)
        out[cid] = [len(maj_codes), len(min_codes), [[idx[k], writers.get(k, 0)] for k in maj_codes],
                    [[idx[k], writers.get(k, 0)] for k in min_codes], 1]   # 5th element 1: from the Court's opinion or order
    print(f'{len(HAND)} lineups hand-checked')
    # justices as [full name, justice page id] (from build_justices.py), falling back to the surname
    jmap = {}
    if os.path.exists('docs/data/justices.js'):
        js = open('docs/data/justices.js', encoding='utf-8').read(); J = json.loads(js[js.index('=') + 1:].rstrip().rstrip(';'))
        full = {j['id']: j['name'] for j in J['justices']}
        jmap = {code: [full[jid], jid] for code, jid in J['byCode'].items()}
    names = [jmap.get(code, [display(code), '']) for code in names]
    data = {'src': 'Supreme Court Database, Version 2026 Release 01 and Legacy 07 (Spaeth et al.); lineups from the Court opinions for later cases', 'j': names, 'c': out}
    open('docs/data/votes.js', 'w', encoding='utf-8').write('window.VOTES=' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';')
    print(f'votes for {len(out)} of {len(cases)} cases; {len(names)} justices; {len(json.dumps(data)) / 1024:.0f} KB')


if __name__ == '__main__':
    main()
