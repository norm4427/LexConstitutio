"""Title case for article titles that a source supplied in ALL CAPS (e.g. "OPENING PANDORA'S JURY BOX").

Used by fix_titles.py (and mirrored in build.ps1's TitleCase). Rules: capitalize principal words; lowercase articles,
short conjunctions and prepositions except at the start, at the end, and after a colon, dash or question mark;
keep known abbreviations, Roman numerals and dotted initialisms (U.S., FBI, NAACP, II) in capitals; handle
Mc-/Mac- and O'-/D'- names and hyphenated words.
"""
import re

SMALL = set('a an the and but or nor for so yet as at by in of off on per to up via v vs into onto from with over upon than'.split())
ACRONYMS = set('''US USA UK EU UN FBI CIA NSA FCC SEC EPA FTC NLRB ACLU NAACP DNA AI ADA RFRA RLUIPA FACA FISA ERISA HIPAA ICE DHS DOJ IRS
OSHA NEPA FDA CDC HHS LGBT LGBTQ ACA VRA ERA AEDPA PLRA CAFA FAA FEC NRA NFIB NFL NCAA TV GPS CEO CEOS ESG DEI ABA AALS NGO NGOS ISIS
UCC UCMJ AUMF NDAA CFPB OIRA OLC OMB GAO CBO DC NYC LA ALJ ALJS APA FOIA FERC NRC NHTSA FAQ II III IV VI VII VIII IX XI XII XIII XIV
XV XVI XIX XX MDL RICO PTAB USPTO ITC WTO NATO ICC ICJ ECHR ECJ GDPR COVID HIV AIDS SCOTUS'''.split())


def _word(w, first):
    if not w:
        return w
    core = re.sub(r"[^A-Za-z'’.]", '', w)
    bare = core.replace('.', '').replace("'", '').replace('’', '')
    if bare.upper() in ACRONYMS or re.fullmatch(r'(?:[A-Z]\.){2,}', core):     # FBI, U.S.
        return w
    if re.fullmatch(r'[IVXLC]{2,4}', bare) and bare not in ('CIVIL', 'LIVID', 'VIVID', 'CIVIC', 'CLI'):   # II, VII, XIV
        return w
    low = w.lower()
    if not first and re.sub(r'[^a-z.]', '', low).rstrip('.') in SMALL:
        return low
    out = re.sub(r"(^|[-–—/(\"“‘])([a-z])", lambda m: m.group(1) + m.group(2).upper(), low)   # first letter, and after hyphens etc.
    out = re.sub(r"(^|[-–—/(\"“‘])([OD])(['’])([a-z])(?=[a-z]{2,})", lambda m: m.group(1) + m.group(2) + m.group(3) + m.group(4).upper(), out)   # O'Connor
    out = re.sub(r"(^|[-–—/(\"“‘])(Mc)([a-z])(?=[a-z]{2,})", lambda m: m.group(1) + m.group(2) + m.group(3).upper(), out)                    # McCulloch
    out = re.sub(r"(?<=-)(Of|The|And|In|On|To|A|An|For|By|At|Or)(?=-)", lambda m: m.group(1).lower(), out)   # Out-of-State
    return out


def is_shouting(t):
    letters = [c for c in t if c.isalpha()]
    return len(letters) > 8 and sum(c.isupper() for c in letters) / len(letters) > 0.75


def titlecase(t):
    if not is_shouting(t):
        return t
    parts = re.split(r'(\s+)', t)
    out, first = [], True
    words = [p for p in parts if p.strip()]
    last = words[-1] if words else None
    for p in parts:
        if not p.strip():
            out.append(p); continue
        out.append(_word(p, first or p is last))
        first = bool(re.search(r'[:?!—–]$|^[—–-]$', p))
    s = ''.join(out)
    return s[:1].upper() + s[1:]


if __name__ == '__main__':
    for t in ["OPENING PANDORA’S JURY BOX", "THE TWENTY-FIFTH AMENDMENT—IN THE WORDS OF BIRCH BAYH, ITS PRINCIPAL",
              "FIXING FACA: THE CASE FOR EXEMPTING PRESIDENTIAL ADVISORY COMMITTEES FROM JUDICIAL REVIEW UNDER THE FEDERAL ADVISORY COMMITTEE ACT",
              "FROM WINSHIP TO APPRENDI TO BOOKER: CONSTITUTIONAL COMMAND OR CONSTITUTIONAL BLUNDER?",
              "MCCULLOCH V. MARYLAND AND THE U.S. CONSTITUTION: O'CONNOR'S TITLE VII LEGACY", "THE CURIOUS CASE OF CELL PHONE LOCATION DATA: FOURTH AMENDMENT DOCTRINE MASH-UP"]:
        print(titlecase(t))
