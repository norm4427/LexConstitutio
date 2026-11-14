"""Measure each justice's questioning of each side at oral argument, from the Court's official transcripts cached by
transcripts_fetch.py (data/raw/transcripts/<term>/<docket>.txt, October Term 2004 on, when transcripts began naming
the justice speaking).

For every transcript: the body is split into the arguments of each advocate ("ORAL ARGUMENT OF ... ON BEHALF OF THE
PETITIONERS", "... FOR THE UNITED STATES, AS AMICUS CURIAE, SUPPORTING RESPONDENT", rebuttals), each assigned to the
petitioner's or respondent's side (an amicus counts for the side it supports). Within each argument, every turn by
"JUSTICE <NAME>:" or "CHIEF JUSTICE <NAME>:" is counted (turns and words), except the Chief Justice's procedural
lines (calling the case, "Thank you, counsel", "The case is submitted").
Output: data/raw/transcripts/features.json  {"<term>/<docket>": {"<SURNAME>": [words_pet, words_res, turns_pet, turns_res,
questions_pet, questions_res], "_us": [side of the United States (0 petitioner, 1 respondent, -1 not appearing), 1 if as amicus]}}
(questions = question marks in the justice's turns; the United States' side is read from the appearances list, where
government lawyers are listed with "Department of Justice, Washington, D.C.; on behalf of ...").
Studies of oral argument (e.g. Epstein, Landes & Posner, J. Legal Analysis 2010; Johnson et al., Law & Society Rev.
2009) find that justices direct more questions and words at the side they vote against; build_models.py uses these
counts as predictors.
Run from the repo root:  python scripts/build_arguments.py
"""
import glob, json, os, re

OUT = 'data/raw/transcripts/features.json'
SPK = re.compile(r'(?:^|\n)\s*((?:CHIEF )?JUSTICE [A-Z][A-Z\'-]+|M[RS]S?\. [A-Z][A-Z\'-]+|GENERAL [A-Z][A-Z\'-]+|[A-Z][A-Z\'-]+ [A-Z][A-Z\'-]+):', re.M)
PROC = re.compile(r'^(We\'?ll hear argument|We will hear argument|Thank you,? counsel|Thank you,? (Mr|Ms|General)|The case is submitted|The case is now submitted|[A-Z][a-z]+\.? [A-Z][a-z]+\.?$)', re.I)


def clean(t):
    t = t.replace('\f', '\n')
    t = re.sub(r'(?m)^\s*\d{1,2}(\s+|$)', '', t)                    # line numbers
    t = re.sub(r'(?im)^.*(Official - Subject to Final Review|Alderson Reporting|Heritage Reporting|www\.|1111 14th Street|\(202\) ?\d{3}).*$', '', t)
    return t


def side_of(header):
    h = re.sub(r'\s+', ' ', header.upper())
    if re.search(r'(SUPPORTING|IN SUPPORT OF) (?:THE )?(REVERSAL|VACATUR)', h):
        return 0
    if re.search(r'(SUPPORTING|IN SUPPORT OF) (?:THE )?(AFFIRMANCE|JUDGMENT)', h):
        return 1
    m = re.search(r'(?:SUPPORTING|IN SUPPORT OF) (?:THE )?(PETITIONER|APPELLANT|RESPONDENT|APPELLEE)', h)
    key = m.group(1) if m else ('PETITIONER' if re.search(r'PETITIONER|APPELLANT', h) else 'RESPONDENT' if re.search(r'RESPONDENT|APPELLEE', h) else '')
    if not key and re.search(r'(COURT-APPOINTED|APPOINTED BY THIS COURT).{0,40}AMICUS|AMICUS CURIAE.{0,40}(APPOINTED|INVITED)', h):
        return 1   # an amicus appointed by the Court defends the judgment below when no party does
    return 0 if key in ('PETITIONER', 'APPELLANT') else 1 if key in ('RESPONDENT', 'APPELLEE') else None


def parse(text):
    t = clean(text)
    first = re.search(r'(?:CHIEF )?JUSTICE [A-Z]+:', t)          # the body starts with the first justice speaking
    if not first:
        return None
    body = t[first.start():]
    end = re.search(r'\(Whereupon', body)                        # the word index follows the argument
    body = body[:end.start()] if end else body
    heads = []
    for m in re.finditer(r'(?:ORAL|REBUTTAL) ARGUMENT OF', body):
        nxt = SPK.search(body, m.end())                          # the header runs to the next speaker label
        heads.append((m.start(), side_of(body[m.end(): nxt.start() if nxt else m.end() + 300][:400])))
    if not heads:
        return None
    out = {}
    for i, (pos, side) in enumerate(heads):
        if side is None:
            continue
        seg = body[pos: heads[i + 1][0] if i + 1 < len(heads) else len(body)]
        marks = list(SPK.finditer(seg))
        for k, m in enumerate(marks):
            who = m.group(1)
            if 'JUSTICE' not in who:
                continue
            words = seg[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(seg)].strip()
            if PROC.match(words.split('\n')[0].strip()) and len(words.split()) < 15:
                continue
            name = who.split()[-1]
            r = out.setdefault(name, [0, 0, 0, 0, 0, 0])
            r[side] += len(words.split()); r[2 + side] += 1; r[4 + side] += words.count('?')
    # the United States' side (party or amicus): from the appearances list before the argument, where government
    # lawyers are listed as "... Department of Justice, Washington, D.C.; on behalf of ..."
    us = [-1, 0]
    for m in re.finditer(r'Department\s+of\s+Justice,?(?:\s*Washington,?\s*D\.?\s*C\.?)?;?\s*([\s\S]{0,220})', t[:first.start()]):
        txt = re.split(r'\.(?:\s|$)', re.sub(r'\s+', ' ', m.group(1)))[0]   # this lawyer's entry only (to its full stop)
        sd = side_of(txt)
        if sd is not None:
            us = [sd, int('AMICUS' in txt.upper())]
            break
    if us[0] < 0:
        for pos, sd in heads:
            hd = body[pos: pos + 260].upper()
            if 'UNITED STATES' in hd and 'AMICUS' in hd and sd is not None:
                us = [sd, 1]
                break
    out['_us'] = us
    return out


def main():
    feats = {}
    for f in sorted(glob.glob('data/raw/transcripts/*/*.txt')):
        term = os.path.basename(os.path.dirname(f))
        dk = os.path.basename(f)[:-4]
        dk = re.sub(r'_[a-z0-9]+$', '', dk)       # newer file names carry a suffix, e.g. 25-332_7lhn
        try:
            r = parse(open(f, encoding='utf-8', errors='replace').read())
        except Exception as e:
            print('parse failed', f, e); continue
        dk = re.sub(r'-(monday|tuesday|wednesday|thursday|friday|day\d)$', '', dk, flags=re.I)
        if r and sum(v[0] + v[1] for k, v in r.items() if k != '_us') > 200:
            cur = feats.setdefault(f'{term}/{dk.lower()}', {})
            us = r.pop('_us')
            if us[0] >= 0 or '_us' not in cur:
                cur['_us'] = us
            for name, v in r.items():
                cur[name] = [a + b for a, b in zip(cur.get(name, [0] * 6), v)]
    json.dump(feats, open(OUT, 'w'), separators=(',', ':'))
    print(f'{len(feats)} transcripts with justice questioning; e.g.', next(iter(feats.items())) if feats else None)


if __name__ == '__main__':
    main()
