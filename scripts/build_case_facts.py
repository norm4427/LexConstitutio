"""Read case facts known before a decision from supremecourt.gov docket pages, for the vote models (build_models.py).

Inputs: data/raw/docket/hist/<docket>.html (argued cases since October Term 2004, dockets_fetch.py) and
data/raw/docket/d-<docket>.html (pending cases, docket.sh).
For every docket the entries ("Mar 24 2004 Brief amicus curiae of United States filed.") are read in order:
  grant           first "Petition GRANTED" / "JURISDICTION NOTED" / "JURISDICTION POSTPONED" entry
  merits briefs   "Brief of petitioner(s) ... filed" and "Brief of respondent(s) ... filed" after the grant
  amicus briefs   "Brief amicus curiae / amici curiae of ... filed". Before the grant they count as cert-stage briefs.
                  After it, the side is the one named in the entry ("in support of petitioner", "supporting
                  respondents", "in support of neither party") when the docket says so; otherwise it is read from the
                  Court's briefing schedule (Rule 37.3(a): an amicus brief supporting the petitioner, or neither party,
                  is due 7 days after the petitioner's brief; one supporting the respondent 7 days after the
                  respondent's brief): filed before the respondent's merits brief = petitioner's side, on or after it
                  = respondent's side.
  United States   an amicus brief "of United States" (side as above); the Solicitor General invited to file a brief
                  expressing the views of the United States at the cert stage (CVSG).
Output: data/raw/docket/facts.json  {"<docket>": {"amPet", "amRes", "amNeither", "amCert", "usAmicus" (0 petitioner,
1 respondent, -1 none), "cvsg", "grant", "resBrief" (1 once the respondent's merits brief is filed)}}
Run from the repo root:  python scripts/build_case_facts.py
"""
import glob, html, json, os, re
from datetime import datetime

MON = '(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
GRANT = re.compile(r'(Petition (?:for (?:a )?writ of certiorari )?GRANTED|JURISDICTION (?:NOTED|POSTPONED)|CERTIORARI GRANTED|Motion for leave to file (?:a )?bill of complaint GRANTED)', re.I)
AMICUS = re.compile(r'^Brief (?:of )?amic(?:us|i) curiae (?:of )?(.*?)(?: filed|$)', re.I)
PET_BRIEF = re.compile(r'^Brief (?:of|for) (?:the )?(?:petitioners?|appellants?|plaintiffs?)\b(?!.*(?:in opposition|amic))', re.I)
RES_BRIEF = re.compile(r'^Brief (?:of|for) (?:the )?(?:federal )?(?:respondents?|appellees?|defendants?)\b(?!.*(?:in opposition|amic))', re.I)


def entries(raw):
    s = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw)))
    out = []
    for e in re.split(r'\s(?=%s \d{1,2} \d{4}\s)' % MON, s)[1:]:
        m = re.match(r'(%s \d{1,2} \d{4})\s+(.*)' % MON, e)
        if m:
            try:
                out.append((datetime.strptime(m.group(1), '%b %d %Y'), m.group(2)[:400]))
            except ValueError:
                pass
    return out


def side_named(txt):
    t = txt.lower()
    if re.search(r'(support of|supporting) (the )?neither|neither party', t):
        return 2
    if re.search(r'(support of|supporting) (the )?(petitioner|appellant|reversal|plaintiff)', t):
        return 0
    if re.search(r'(support of|supporting) (the )?(respondent|appellee|affirmance|defendant)', t):
        return 1
    return None


def facts(raw):
    E = entries(raw)
    if not E:
        return None
    grant = next((d for d, t in E if GRANT.search(t)), None)
    after = [(d, t) for d, t in E if grant is None or d >= grant]
    res_date = next((d for d, t in after if RES_BRIEF.search(t)), None)
    f = {'amPet': 0, 'amRes': 0, 'amNeither': 0, 'amCert': 0, 'usAmicus': -1, 'cvsg': 0,
         'grant': grant.strftime('%Y-%m-%d') if grant else '', 'resBrief': int(res_date is not None)}
    for d, t in E:
        if re.search(r'Solicitor General is invited to file a brief', t, re.I):
            f['cvsg'] = 1
        m = AMICUS.match(t)
        if not m:
            continue
        who = m.group(1)
        us = bool(re.match(r'(the )?United States\b', who, re.I))
        if grant is not None and d < grant:
            if not us:
                f['amCert'] += 1
            continue
        sd = side_named(t)
        if sd is None:
            sd = 1 if (res_date is not None and d >= res_date) else 0
        if us:
            f['usAmicus'] = min(sd, 1) if sd != 2 else -1
        else:
            f[['amPet', 'amRes', 'amNeither'][sd]] += 1
    return f


def main():
    out = {}
    for p in glob.glob('data/raw/docket/hist/*.html') + glob.glob('data/raw/docket/d-*.html'):
        dk = os.path.basename(p)[:-5]
        dk = dk[2:] if dk.startswith('d-') else dk
        r = facts(open(p, encoding='utf-8', errors='replace').read())
        if r:
            out[dk.lower()] = r
    json.dump(out, open('data/raw/docket/facts.json', 'w'), indent=0)
    n = len(out)
    print(n, 'dockets;', 'with a grant date', sum(1 for v in out.values() if v['grant']),
          '| mean amicus pet/res/neither/cert', *[round(sum(v[k] for v in out.values()) / max(1, n), 2) for k in ('amPet', 'amRes', 'amNeither', 'amCert')],
          '| US amicus', sum(1 for v in out.values() if v['usAmicus'] >= 0), '| CVSG', sum(v['cvsg'] for v in out.values()))


if __name__ == '__main__':
    main()
