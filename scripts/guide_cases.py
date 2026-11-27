"""Add landmark cases to each Beginner's Guide topic. The cases are named here, by case name and year (a hand-picked list of the
standard cases for each topic); each is looked up in the site's own case data (docs/data/scotus.js) so that it links to its
case page, and a name that is not found is reported and skipped. The cases already listed are kept first.
Run from the repo root after build_extras.pl and guide_lectures.py (before fix_text.py):  python scripts/guide_cases.py"""
import json, re

EXTRA = {
    'judicial-review': ['Marbury v. Madison 1803', "Martin v. Hunter's Lessee 1816", 'Cohens v. Virginia 1821', 'Cooper v. Aaron 1958', 'Baker v. Carr 1962', 'City of Boerne v. Flores 1997', 'Dred Scott v. Sandford 1857'],
    'interpretation': ['District of Columbia v. Heller 2008', 'New York State Rifle & Pistol Association, Inc. v. Bruen 2022', 'Bostock v. Clayton County 2020', 'Crawford v. Washington 2004', "Dobbs v. Jackson Women's Health Organization 2022", 'Home Building & Loan Association v. Blaisdell 1934', 'McCulloch v. Maryland 1819'],
    'incorporation': ['Barron v. Baltimore 1833', 'Slaughter-House Cases 1873', 'Gitlow v. New York 1925', 'Palko v. Connecticut 1937', 'Duncan v. Louisiana 1968', 'McDonald v. City of Chicago 2010', 'Timbs v. Indiana 2019'],
    'separation-of-powers': ['Youngstown Sheet & Tube Co. v. Sawyer 1952', "Humphrey's Executor v. United States 1935", 'INS v. Chadha 1983', 'Morrison v. Olson 1988', 'Mistretta v. United States 1989', 'Clinton v. City of New York 1998', 'Seila Law LLC v. Consumer Financial Protection Bureau 2020'],
    'executive-power': ['Youngstown Sheet & Tube Co. v. Sawyer 1952', 'United States v. Nixon 1974', 'Nixon v. Fitzgerald 1982', 'Clinton v. Jones 1997', 'Trump v. Hawaii 2018', 'Trump v. United States 2024', 'Myers v. United States 1926'],
    'federalism': ['McCulloch v. Maryland 1819', 'Gibbons v. Ogden 1824', 'National League of Cities v. Usery 1976', 'Garcia v. San Antonio Metropolitan Transit Authority 1985', 'New York v. United States 1992', 'Printz v. United States 1997', 'Murphy v. National Collegiate Athletic Association 2018'],
    'commerce-clause': ['Gibbons v. Ogden 1824', 'Wickard v. Filburn 1942', 'Heart of Atlanta Motel, Inc. v. United States 1964', 'Katzenbach v. McClung 1964', 'United States v. Lopez 1995', 'United States v. Morrison 2000', 'Gonzales v. Raich 2005'],
    'standing': ['Frothingham v. Mellon 1923', 'Baker v. Carr 1962', 'Flast v. Cohen 1968', 'Lujan v. Defenders of Wildlife 1992', 'Massachusetts v. Environmental Protection Agency 2007', 'Clapper v. Amnesty International USA 2013', 'Spokeo, Inc. v. Robins 2016'],
    'administrative-state': ["Humphrey's Executor v. United States 1935", 'A.L.A. Schechter Poultry Corp. v. United States 1935', 'Mistretta v. United States 1989', 'Chevron U.S.A. Inc. v. Natural Resources Defense Council, Inc. 1984', 'Whitman v. American Trucking Associations, Inc. 2001', 'Loper Bright Enterprises v. Raimondo 2024', 'West Virginia v. EPA 2022'],
    'free-speech': ['Schenck v. United States 1919', 'Brandenburg v. Ohio 1969', 'New York Times Co. v. Sullivan 1964', 'Texas v. Johnson 1989', 'Citizens United v. Federal Election Commission 2010', 'Reed v. Town of Gilbert 2015', 'Tinker v. Des Moines Independent Community School District 1969'],
    'religion': ['Reynolds v. United States 1879', 'Everson v. Board of Education 1947', 'Engel v. Vitale 1962', 'Lemon v. Kurtzman 1971', 'Employment Division v. Smith 1990', 'Town of Greece v. Galloway 2014', 'Kennedy v. Bremerton School District 2022'],
    'second-amendment': ['United States v. Miller 1939', 'District of Columbia v. Heller 2008', 'McDonald v. City of Chicago 2010', 'New York State Rifle & Pistol Association, Inc. v. Bruen 2022', 'United States v. Rahimi 2024', 'Caetano v. Massachusetts 2016', 'Presser v. Illinois 1886'],
    'equal-protection': ['Plessy v. Ferguson 1896', 'Brown v. Board of Education of Topeka 1954', 'Loving v. Virginia 1967', 'Craig v. Boren 1976', 'Regents of the University of California v. Bakke 1978', 'Romer v. Evans 1996', 'Students for Fair Admissions, Inc. v. President and Fellows of Harvard College 2023'],
    'due-process': ['Lochner v. New York 1905', 'Griswold v. Connecticut 1965', 'Roe v. Wade 1973', 'Planned Parenthood of Southeastern Pennsylvania v. Casey 1992', 'Lawrence v. Texas 2003', 'Obergefell v. Hodges 2015', 'Washington v. Glucksberg 1997'],
    'fourth-amendment': ['Weeks v. United States 1914', 'Mapp v. Ohio 1961', 'Katz v. United States 1967', 'Terry v. Ohio 1968', 'United States v. Leon 1984', 'Kyllo v. United States 2001', 'Carpenter v. United States 2018'],
    'trial-rights': ['Powell v. Alabama 1932', 'Gideon v. Wainwright 1963', 'Miranda v. Arizona 1966', 'Duncan v. Louisiana 1968', 'Batson v. Kentucky 1986', 'Crawford v. Washington 2004', 'Strickland v. Washington 1984'],
    'punishment': ['Furman v. Georgia 1972', 'Gregg v. Georgia 1976', 'Coker v. Georgia 1977', 'Atkins v. Virginia 2002', 'Roper v. Simmons 2005', 'Graham v. Florida 2010', 'Glossip v. Gross 2015'],
    'takings': ['Pennsylvania Coal Co. v. Mahon 1922', 'Penn Central Transportation Co. v. New York City 1978', 'Loretto v. Teleprompter Manhattan CATV Corp. 1982', 'Lucas v. South Carolina Coastal Council 1992', 'Kelo v. City of New London 2005', 'Murr v. Wisconsin 2017', 'Cedar Point Nursery v. Hassid 2021'],
    'voting': ['Smith v. Allwright 1944', 'Reynolds v. Sims 1964', 'South Carolina v. Katzenbach 1966', 'Shaw v. Reno 1993', 'Bush v. Gore 2000', 'Shelby County v. Holder 2013', 'Rucho v. Common Cause 2019'],
    'war-powers': ['Ex parte Milligan 1866', 'Korematsu v. United States 1944', 'Youngstown Sheet & Tube Co. v. Sawyer 1952', 'Hamdi v. Rumsfeld 2004', 'Rasul v. Bush 2004', 'Hamdan v. Rumsfeld 2006', 'Boumediene v. Bush 2008'],
}


# Books already in docs/data/books.js (by id) added to topics that recommend only one, and lectures (YouTube, public and embeddable
# per YouTube's oEmbed endpoint when added; scripts/guide_extra_lectures.json) for topics the lecture collection leaves thin
EXTRA_BOOKS = {
    'standing': ['the-federal-courts-and-the-federal-system', 'matter-of-interpretation'],
    'religion': ['religious-freedom-and-the-constitution', 'religion-and-the-constitution'],
    'second-amendment': ['to-keep-and-bear-arms'],
    'fourth-amendment': ['the-fourth-amendment'],
    'trial-rights': ['constitution-criminal-procedure'],
    'punishment': ['the-death-penalty'],
}


def load(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def norm(n):
    return re.sub(r'[^a-z0-9]+', ' ', re.sub(r'\s*\(\d\)$', '', n).lower().replace('&', 'and')).strip()


def main():
    G = load('docs/data/guide.js')
    S = [c for c in load('docs/data/scotus.js')['cases'] if c.get('dec')]
    by = {}
    for c in S:
        by.setdefault(norm(c['n']), []).append(c)
    for t in G['topics']:
        have = {c['id'] for c in t['cases']}
        before = len(t['cases'])
        for spec in EXTRA[t['id']]:
            name, year = spec.rsplit(' ', 1)
            k = norm(name)
            found = by.get(k) or [c for kk, v in by.items() if len(kk) > 12 and (kk.startswith(k) or k.startswith(kk)) for c in v]
            found = [c for c in found if abs(int(c['dec'][:4]) - int(year)) <= 1]
            if not found:       # the data spells some names differently: the same year and mostly the same words
                tk = lambda x: {w for w in norm(x).split() if w not in ('of', 'the', 'and', 'inc', 'co', 'company', 'corporation', 'corp', 'v', 'et', 'al')}
                a = tk(name)
                found = [c for c in S if c['dec'][:4] == year and len(a & tk(c['n'])) / max(1, min(len(a), len(tk(c['n'])))) >= 0.7 and len(a & tk(c['n'])) >= 2]
            found.sort(key=lambda c: (abs(int(c['dec'][:4]) - int(year)), c['n'].endswith('(2)')))
            if not found:
                print('  not found:', spec)
                continue
            c = found[0]
            if c['id'] not in have:
                have.add(c['id'])
                print('    +', spec, '->', c['n'])
                t['cases'].append({'cit': c.get('cit') or '', 'id': c['id'], 'n': c['n'], 'y': int(c['dec'][:4])})
        print(f"{t['id']:22} {before} -> {len(t['cases'])}")
    book_ids = {b['id'] for b in load('docs/data/books.js')['books']}
    lec = json.load(open('scripts/guide_extra_lectures.json', encoding='utf-8'))
    for t in G['topics']:
        for b in EXTRA_BOOKS.get(t['id'], []):
            if b in book_ids and b not in t['books']:
                t['books'].append(b)
        have = {v['id'] for v in t.get('lectures', [])} | {v['id'] for v in t.get('videos', [])}
        for v in lec.get(t['id'], []):
            if v['id'] not in have:
                t.setdefault('lectures', []).append(v)
        print(f"{t['id']:22} lectures {len(t.get('lectures', []))} books {len(t['books'])}")
    open('docs/data/guide.js', 'w', encoding='utf-8').write('window.GUIDE=' + json.dumps(G, ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
