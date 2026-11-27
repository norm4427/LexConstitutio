"""Which way each predictor group pushes a justice's vote, for the hover notes under "What moves X's vote" on the
justice pages. Adds m['dir'] = {group: {"how": what the group measures, "dir": the pattern in this justice's own votes}}
to each current justice in docs/data/models.js. Plain counts from the justice's votes (vote for the petitioner = 1),
1946 on, or 2004 on where the data starts then; nothing is refitted. build_models.py calls directions() too.
Run from the repo root:  python scripts/model_directions.py
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import build_models as B
from scdb_lib import ISSUE_AREA

HOW = {
    'Oral argument questioning': 'How much the justice spoke to, and questioned, each side’s lawyer at oral argument, and how the Court as a whole divided its questions (official transcripts, cases since 2004).',
    'United States position': 'Which side the United States supports, as a party or as amicus curiae, and whether the Court invited the Solicitor General’s views.',
    'Parties': 'Whether the petitioner and the respondent are the federal government, a state, a local government or a private party.',
    'Amicus briefs': 'How many amicus briefs were filed for each side at the merits stage and at the cert stage (supremecourt.gov dockets, cases since 2004).',
    "Justice's record in earlier terms": 'The justice’s own share of liberal votes and of votes for the petitioner in earlier Terms, overall and in the case’s issue area.',
    "Lower court's direction x the justice's lean": 'Whether the decision under review was liberal or conservative (Supreme Court Database coding), combined with how far the justice leans from colleagues.',
    'Court trend': 'How often the whole Court has sided with petitioners in recent Terms, and the Term itself.',
    'Lower court': 'Which court the case comes from, and how often the Court has reversed that court recently.',
    'Jurisdiction': 'How the case reached the Court: certiorari, mandatory appeal, original jurisdiction or other routes.',
    'Issue area': 'The Supreme Court Database issue area (criminal procedure, civil rights, First Amendment, economic activity, …).',
    'Oral argument interruptions and first/last questions': 'How often the justice, and the Court as a whole, cut off each side’s lawyer mid-sentence, and whether the justice asked the first or the last question of each side’s argument (official transcripts, cases since 2004).',
    'Martin-Quinn ideology x direction below': 'The justice’s Martin–Quinn ideal point (a liberal–conservative score estimated from votes) from the previous Term, relative to the other justices, combined with whether the decision under review was liberal or conservative. The latest public scores are for 2021; later Terms use those.',
}
MIN = 12
PRON = {'JGRoberts': 'he', 'CThomas': 'he', 'SAAlito': 'he', 'SSotomayor': 'she', 'EKagan': 'she', 'NMGorsuch': 'he',
        'BMKavanaugh': 'he', 'ACBarrett': 'she', 'KBJackson': 'she'}


def pct(a):
    return f'{round(100 * float(a))}%'


def rate(y):
    return pct(y.mean()), int(len(y))


def directions(V, code, last):
    v = V[V.justiceName == code]
    pr = PRON.get(code, 'the justice')
    y = v.y.astype(float)
    out = {}
    # questioning: positive argW = the justice's words aimed more at the respondent's side
    a = v[(v.argHas == 1) & (v.argW != 0)]
    if len(a) >= MIN:
        res, pet = a[a.argW > 0], a[a.argW < 0]
        if len(res) >= 5 and len(pet) >= 5:
            r1, n1 = rate(res.y); r2, n2 = rate(pet.y)
            against = (res.y.mean() > pet.y.mean())
            out['Oral argument questioning'] = (f'{last} tends to vote {"against" if against else "for"} the side {pr} questions more: '
                                                f'when {pr} spoke more to the respondent’s lawyer, {pr} voted for the petitioner {r1} of the time ({n1} votes); '
                                                f'when {pr} spoke more to the petitioner’s lawyer, {r2} ({n2} votes).')
    # first question: argFirst > 0 = the justice asked the respondent's lawyer the first question (and not the petitioner's)
    if 'argFirst' in v:
        notes = []
        ir, ip = v[v.argInt > 0], v[v.argInt < 0]       # argInt > 0: interrupted the respondent's lawyer more
        if len(ir) >= 5 and len(ip) >= 5:
            notes.append(f'When {last} interrupted the respondent’s lawyer more, {pr} voted for the petitioner {pct(ir.y.mean())} of the time ({len(ir)} votes); '
                         f'when {pr} interrupted the petitioner’s lawyer more, {pct(ip.y.mean())} ({len(ip)} votes).')
        fr, fp = v[v.argFirst > 0], v[v.argFirst < 0]
        if len(fr) >= 5 and len(fp) >= 5:
            notes.append(f'When {pr} asked the respondent’s lawyer the first question, {pr} voted for the petitioner {pct(fr.y.mean())} of the time ({len(fr)} votes); '
                         f'when {pr} asked the petitioner’s lawyer first, {pct(fp.y.mean())} ({len(fp)} votes).')
        if notes:
            out['Oral argument interruptions and first/last questions'] = ' '.join(notes)
    # United States
    u = v[v.usSide != 0]
    if len(u) >= MIN:
        withus = (u.y == (u.usSide > 0)).astype(float)
        am = u[u.usAmicus == 1]
        s = f'{last} voted for the side the United States supported in {pct(withus.mean())} of {len(u)} votes'
        if len(am) >= MIN:
            s += f' ({pct((am.y == (am.usSide > 0)).mean())} of {len(am)} when it took part as amicus curiae)'
        out['United States position'] = s + '.'
    # parties: government vs private
    gov = {'federal', 'state', 'local'}
    gp = v[v.petParty.isin(gov) & ~v.resParty.isin(gov)]
    gr = v[v.resParty.isin(gov) & ~v.petParty.isin(gov)]
    if len(gp) + len(gr) >= MIN:
        g = np.concatenate([gp.y.values, 1 - gr.y.values])
        out['Parties'] = f'When a government was on one side and a private party on the other, {last} voted for the government in {pct(g.mean())} of {len(g)} votes.'
    # amicus
    m = v[(v.amKnown == 1) & (v.amDiff != 0)]
    if len(m) >= MIN:
        more = (m.y == (m.amDiff > 0)).astype(float)
        out['Amicus briefs'] = f'{last} voted for the side with more merits-stage amicus briefs in {pct(more.mean())} of {len(m)} votes.'
    # earlier record
    if len(v) >= MIN:
        out["Justice's record in earlier terms"] = (f'The model expects {last} to keep to past patterns: over the whole record, {last} voted for the petitioner in '
                                                   f'{pct(y.mean())} of {len(v)} votes.')
    # direction below
    lib, con = v[v.lcLib == 1], v[v.lcLib == 0]
    if len(lib) >= 5 and len(con) >= 5:
        out["Lower court's direction x the justice's lean"] = (f'{last} voted to reverse {pct(lib.y.mean())} of liberal decisions below ({len(lib)} votes) '
                                                             f'and {pct(con.y.mean())} of conservative ones ({len(con)} votes).')
    # court trend
    if len(v) >= MIN:
        hi, lo = v[v.courtRev >= v.courtRev.median()], v[v.courtRev < v.courtRev.median()]
        if len(hi) >= 5 and len(lo) >= 5:
            out['Court trend'] = (f'In Terms when the Court had recently been siding with petitioners more often, {last} voted for the petitioner {pct(hi.y.mean())} of the time; '
                                  f'in other Terms, {pct(lo.y.mean())}.')
    # lower court
    g = v.groupby('srcGroup').y.agg(['mean', 'count'])
    g = g[g['count'] >= MIN]
    if len(g) >= 2:
        h, l = g['mean'].idxmax(), g['mean'].idxmin()
        out['Lower court'] = (f'{last} voted to reverse the {h} in {pct(g.loc[h, "mean"])} of {int(g.loc[h, "count"])} votes, the most of any source; '
                              f'the {l} in {pct(g.loc[l, "mean"])} of {int(g.loc[l, "count"])}.').replace('the District courts', 'district courts').replace('the State courts', 'state courts')
    # jurisdiction
    j = v.groupby('jurisdiction').y.agg(['mean', 'count'])
    names = {'1': 'certiorari', '2': 'appeal'}
    parts = [f'{pct(j.loc[k, "mean"])} on {names[k]} ({int(j.loc[k, "count"])} votes)' for k in names if k in j.index and j.loc[k, 'count'] >= 5]
    if parts:
        out['Jurisdiction'] = f'{last} voted for the petitioner ' + ' and '.join(parts) + '.'
    # issue area
    ia = v.groupby('issueArea').y.agg(['mean', 'count'])
    ia = ia[ia['count'] >= MIN]
    if len(ia) >= 2:
        nm = lambda k: ISSUE_AREA.get(int(float(k)), str(k)) if str(k).lstrip('-').replace('.', '').isdigit() else str(k)
        h, l = ia['mean'].idxmax(), ia['mean'].idxmin()
        out['Issue area'] = (f'{last} voted for the petitioner most often in {nm(h)} cases ({pct(ia.loc[h, "mean"])} of {int(ia.loc[h, "count"])}) '
                             f'and least often in {nm(l)} cases ({pct(ia.loc[l, "mean"])} of {int(ia.loc[l, "count"])}).')
    return {g: {'how': HOW[g], 'dir': out.get(g, '')} for g in HOW}


def main():
    d, C, ARG, FCT, srev, crev, surname, code2id, *_ = B.build_frames()
    V = B.vote_rows(d, C, ARG, surname)
    p = 'docs/data/models.js'
    s = open(p, encoding='utf-8').read()
    pre = s[:s.index('=') + 1]
    M = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    for code in B.CURRENT:
        jid = code2id[code]
        if jid in M['j']:
            last = surname.get(code, code).title() if surname.get(code) else code
            M['j'][jid]['dir'] = directions(V, code, last)
            print(jid, M['j'][jid]['dir']['Oral argument questioning']['dir'][:160], flush=True)
    open(p, 'w', encoding='utf-8').write(pre + json.dumps(M, ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
