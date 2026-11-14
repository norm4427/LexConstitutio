"""Build docs/data/glossary.js: short and longer definitions of constitutional-law terms, shown when a reader hovers a
highlighted term in the Beginner's Guide.

Source: Wex, the legal dictionary and encyclopedia of Cornell Law School's Legal Information Institute
(https://www.law.cornell.edu/wex), licensed CC BY-NC-SA 2.5; definitions are excerpted (the opening paragraphs) and
credited with a link. Terms Wex lacks fall back to the U.S. Courts glossary (uscourts.gov, a U.S. government work).
Pages are cached in data/raw/wex/. Run from the repo root:  python scripts/build_glossary.py
"""
import html, json, os, re, time, urllib.request

TERMS = '''judicial review|precedent|stare decisis|certiorari|originalism|textualism|living constitution|federalism|separation of powers|checks and balances
enumerated powers|implied powers|necessary and proper clause|commerce clause|dormant commerce clause|police power|tenth amendment|preemption|supremacy clause
sovereign immunity|standing|mootness|ripeness|political question doctrine|justiciability|case or controversy|advisory opinion|incorporation doctrine
selective incorporation|due process|procedural due process|substantive due process|fundamental right|equal protection|strict scrutiny|intermediate scrutiny
rational basis test|suspect classification|quasi-suspect classification|affirmative action|disparate impact|state action|prior restraint|content-based
content neutral|public forum|time, place, and manner restrictions|overbreadth doctrine|void for vagueness|symbolic speech|commercial speech|defamation
actual malice|obscenity|fighting words|incitement|establishment clause|free exercise clause|lemon test|probable cause|search warrant|exclusionary rule
fruit of the poisonous tree|miranda warning|self-incrimination|double jeopardy|right to counsel|cruel and unusual punishment|takings clause|eminent domain
just compensation|regulatory taking|contract clause|executive order|executive privilege|impeachment|veto|pocket veto|war powers|nondelegation doctrine
administrative agency|chevron deference|major questions doctrine|appointments clause|removal power|pardon|treaty|habeas corpus|bill of attainder|ex post facto
privileges and immunities clause|birthright citizenship|gerrymandering|apportionment|one person, one vote|voting rights act|poll tax|electoral college
amicus curiae|injunction|declaratory judgment|plurality opinion|concurring opinion|dissenting opinion|majority opinion|per curiam|dicta|holding|remand
original jurisdiction|appellate jurisdiction|facial challenge|as-applied challenge|quasi-legislative|bill of rights|reconstruction amendments|civil rights
civil liberties|unenumerated rights|ninth amendment|right to privacy|search and seizure|warrantless search|reasonable expectation of privacy|grand jury
jury trial|confrontation clause|bail|excessive fines|death penalty|separate but equal|segregation|de jure|de facto|compelling state interest|narrowly tailored
least restrictive means|undue burden|viability|ministerial exception|free speech|freedom of the press|freedom of association|right to bear arms
militia|full faith and credit|interstate commerce|spending clause|taxing power|general welfare clause|anti-commandeering doctrine|cooperative federalism
judicial restraint|judicial activism|constitutional amendment|ratification|veto power|filibuster|presentment clause|bicameralism|qualified immunity|section 1983'''
TERMS = [t.strip() for line in TERMS.split('\n') for t in line.split('|') if t.strip()]
ALT = {'living constitution': ['living_constitutionalism'], 'implied powers': ['implied_power'], 'police power': ['police_powers'],
       'mootness': ['moot'], 'ripeness': ['ripe'], 'case or controversy': ['case_or_controversy_requirement'], 'selective incorporation': ['incorporation_doctrine'],
       'content-based': ['content_based_restrictions', 'content_based'], 'content neutral': ['content_neutral_laws'], 'public forum': ['public_forum_doctrine'],
       'time, place, and manner restrictions': ['time_place_and_manner_restrictions', 'time_place_and_manner'], 'overbreadth doctrine': ['overbreadth'],
       'incitement': ['imminent_lawless_action', 'incitement_to_riot'], 'self-incrimination': ['self_incrimination', 'fifth_amendment'], 'takings clause': ['takings'],
       'regulatory taking': ['regulatory_takings'], 'contract clause': ['contracts_clause'], 'appointments clause': ['appointment_clause'], 'gerrymandering': ['gerrymander'],
       'apportionment': ['reapportionment'], 'one person, one vote': ['one_person_one_vote', 'one_man_one_vote'], 'plurality opinion': ['plurality'],
       'majority opinion': ['opinion'], 'facial challenge': ['facial_challenges'], 'unenumerated rights': ['unenumerated_right'], 'warrantless search': ['warrantless_searches'],
       'reasonable expectation of privacy': ['expectation_of_privacy'], 'compelling state interest': ['compelling_governmental_interest'], 'narrowly tailored': ['narrow_tailoring'],
       'least restrictive means': ['least_restrictive_means_test'], 'free speech': ['freedom_of_speech'], 'right to bear arms': ['second_amendment'], 'spending clause': ['spending_power'],
       'general welfare clause': ['general_welfare'], 'anti-commandeering doctrine': ['anti-commandeering', 'anticommandeering'], 'presentment clause': ['presentment'],
       'bicameralism': ['bicameral'], 'section 1983': ['42_u.s.c._1983'], 'veto power': ['veto'], 'tenth amendment': ['tenth_amendment_0'], 'ninth amendment': ['ninth_amendment_0']}
UA = {'User-Agent':'Mozilla/5.0 (LexConstitutio educational site; glossary build)'}


def fetch(url, path):
    if os.path.exists(path):
        return open(path, encoding='utf-8', errors='replace').read()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            s = r.read().decode('utf-8', 'replace')
    except Exception:
        s = ''
    open(path, 'w', encoding='utf-8').write(s)
    time.sleep(0.6)
    return s


def paras(s):
    out = []
    for p in re.findall(r'<p[^>]*>(.*?)</p>', s, re.S):
        t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', p))).replace('\xa0', ' ').strip()
        if len(t) > 60 and not re.match(r'^(For more|See also|\[Last updated|Last reviewed|Wex|This material)', t):
            out.append(t)
    return out


def short(t):
    s = re.split(r'(?<=[.!?])\s+(?=[A-Z])', t)
    out = s[0]
    if len(out) < 140 and len(s) > 1:
        out += ' ' + s[1]
    return out


def main():
    os.makedirs('data/raw/wex', exist_ok=True)
    gl, miss = {}, []
    for t in TERMS:
        slug = re.sub(r'[^a-z0-9]+', '_', t.lower()).strip('_')
        url = f'https://www.law.cornell.edu/wex/{slug}'
        ps = paras(fetch(url, f'data/raw/wex/{slug}.html'))
        for alt in (ALT.get(t, []) if not ps else []):
            url = f'https://www.law.cornell.edu/wex/{alt}'
            ps = paras(fetch(url, 'data/raw/wex/' + re.sub(r'[^a-z0-9_]', '_', alt) + '.html'))
            if ps:
                break
        while ps and len(ps) > 1 and re.search(r'different meanings|may refer to|several meanings', ps[0]):
            ps = ps[1:]
        if ps:
            gl[t] = {'s': short(ps[0]), 'l': ps[:3], 'url': url, 'src': 'wex'}
        else:
            miss.append(t)
    # fallback: U.S. Courts glossary (public domain)
    uc = fetch('https://www.uscourts.gov/glossary', 'data/raw/wex/_uscourts.html')
    ucg = {}
    for m in re.finditer(r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>', uc, re.S):
        ucg[html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip().lower()] = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', m.group(2)))).strip()
    for t in list(miss):
        if t in ucg:
            gl[t] = {'s': short(ucg[t]), 'l': [ucg[t]], 'url': 'https://www.uscourts.gov/glossary', 'src': 'uscourts'}
            miss.remove(t)
    data = {'src': {'wex': 'Wex, Legal Information Institute, Cornell Law School (CC BY-NC-SA 2.5)', 'uscourts': 'Glossary of Legal Terms, United States Courts'}, 'terms': gl}
    open('docs/data/glossary.js', 'w', encoding='utf-8').write('window.GLOSSARY=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{len(gl)} of {len(TERMS)} terms defined (U.S. Courts glossary entries parsed: {len(ucg)}); missing: {miss}')


if __name__ == '__main__':
    main()
