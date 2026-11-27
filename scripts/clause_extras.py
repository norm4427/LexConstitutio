"""Extra links for the annotated Constitution's clause panels, used by build_constitution.py.

CI_EXTRA   leading cases the Supreme Court Database does not code under a provision, for clauses that would otherwise list no
           case (clause id -> site case ids)
USC        Acts of Congress in docs/data/statutes.js that implement a clause or that the Supreme Court has tested under it
           (clause id -> statute ids); the panel's "Federal statutes" section
FOUNDING_FALLBACK  clauses whose Originalist's Corner topics hold no passage but whose words occur in the founding-era sources:
           build_constitution.py then searches every passage for the clause's pattern given here (quotes stay verbatim, with their citation)
"""

CI_EXTRA = {
    'preamble': ['1900-1940/197us11'],                       # Jacobson v. Massachusetts: the Preamble is no source of power
    'impeachment-trials': ['1992/91-740'], 'impeachment-judgments': ['1992/91-740'], 'speaker-impeachment-power': ['1992/91-740'],   # Nixon v. United States
    'senate-qualifications': ['1994/93-1456'],              # U.S. Term Limits v. Thornton
    'senate-composition': ['1963/23'],                       # Reynolds v. Sims (the Senate as the exception to one person, one vote)
    'natural-born': ['scdb/1874-147'],                       # Minor v. Happersett
    'third-amendment': ['1964/496'],                         # Griswold v. Connecticut
    'ineligibility-incompatibility': ['1973/72-1188'],       # Schlesinger v. Reservists Committee to Stop the War
    'house-vacancies': ['1968/138'],                         # Powell v. McCormack (the House's power over its membership)
}

USC = {
    'legislative-vesting': ['nira', 'grh', 'lineitem', 'apa'], 'presentment': ['lineitem'], 'appropriations': ['lineitem', 'grh'],
    'elections-clause': ['vra', 'fecaelect', 's1971', 'bcra'], 'taxing-spending': ['irc', 'socsec', 'aca', 'medicaid', 'esea'],
    'borrowing': ['fra'], 'commerce': ['cra1964', 'sherman', 'ica', 'nlra', 'flsa', 'csa', 'gfsza', 'vawa', 'aaa'],
    'naturalization-bankruptcy': ['bankruptcy', 'ina', 'naturalization', 'chinese'], 'coinage': ['fra'], 'counterfeiting': ['fra'],
    'copyright-patent': ['copyright', 'patent', 'lanham'], 'inferior-tribunals': ['ja1789'], 'define-punish': ['ats', 'espionage'],
    'war-powers': ['aumf', 'twea', 'ssa', 'ieepa', 'milcom', 'dta'], 'raise-armies': ['ssa', 'ucmj'], 'military-regulation': ['ucmj', 'milcom'],
    'militia': ['gca', 'nfa'], 'necessary-proper': ['aca', 'fra', 'irc'], 'habeas': ['habeas', 'aedpa', 'dta', 'milcom'],
    'attainder-ex-post-facto': ['sra', 'acca'], 'direct-taxes': ['irc', 'aca'], 'sixteenth-amendment': ['irc'],
    'executive-vesting': ['ethics', 'lineitem', 'fvra'], 'appointments': ['fvra', 'ethics'], 'recess-appointments': ['fvra'],
    'take-care': ['apa', 'ethics'], 'impeachment': ['ethics'], 'commander-in-chief': ['aumf', 'ucmj', 'milcom'],
    'judicial-vesting': ['ja1789', 'habeas', 'tucker'], 'cases-controversies': ['ja1789', 'apa', 's1983', 'ftcaTort'],
    'original-jurisdiction': ['ja1789'], 'eleventh-amendment': ['adea', 'ada', 'fmla', 's1983'],
    'supremacy': ['erisa', 'faa', 'fdca', 'fifra', 'nlra'], 'tenth-amendment': ['brady', 'aca', 'gfsza', 'vawa', 'caa'],
    'property-clause': ['sla', 'ira', 'esa'], 'admissions-clause': ['sla', 'missouri'], 'fugitive-slave': ['fugitive'],
    'establishment': ['rfra', 'rluipa', 'esea'], 'free-exercise': ['rfra', 'rluipa'],
    'free-speech': ['bcra', 'cda', 'copa', 'stolenvalor', 'espionage', 'smith', 'fecaelect', 'commact'],
    'free-press': ['espionage', 'cda'], 'assembly-petition': ['hatch', 'smith'], 'second-amendment': ['gca', 'nfa', 'brady', 'gfsza'],
    'fourth-amendment': ['fisa', 'sca', 'omnibus', 'csa'], 'self-incrimination': ['omnibus'], 'grand-jury': ['jencks', 'omnibus'],
    'sixth-trial': ['sra', 'acca', 'firststep'], 'confrontation': ['omnibus'], 'counsel': ['aedpa', 'omnibus'],
    'eighth-amendment': ['sra', 'plra', 'acca', 'firststep', 'aedpa'], 'takings': ['tucker', 'esa', 'sla'],
    'due-process-5': ['apa', 'ftcaTort', 'habeas'], 'due-process-14': ['s1983', 'apa', 'fha'],
    'equal-protection': ['cra1964', 'title6', 'title7', 'title9', 's1981', 's1983', 'adea', 'doma', 'pda'],
    'thirteenth-amendment': ['s1981', 's1982', 'fha'], 'thirteenth-enforcement': ['s1982', 's1981', 'fha', 'cra1875'],
    'citizenship-clause': ['ina', 'naturalization'], 'privileges-or-immunities': ['s1983', 'cra1875'],
    'enforcement-14': ['s1983', 's1985', 'enforcement', 'cra1875', 'vra', 'rfra', 'ada', 'adea'],
    'fifteenth-amendment': ['vra', 'enforcement', 's1971'], 'fifteenth-enforcement': ['vra', 'enforcement', 'cra1957', 's1971'],
    'nineteenth-amendment': ['vra'], 'twenty-fourth-amendment': ['vra'], 'twenty-fourth-enforcement': ['vra'],
    'twenty-sixth-amendment': ['vra'], 'twenty-sixth-enforcement': ['vra'], 'disqualification': ['enforcement'],
    'electors-appointment': ['fecaelect'], 'treason': ['espionage'],
    'seventh-amendment': ['ftcaTort', 'faa'], 'contract-clause': ['bankruptcy'], 'post-office': ['commact'],
}

FOUNDING_FALLBACK = {   # clause id -> the pattern a passage must match (stricter than the clause's own, since it is applied to every passage)
    'speech-debate': r"speech(?:es)? (?:or|and) debates?|freedom of speech and debates?|privileged from arrest|privilege from arrest",
    'rules-expulsion': r"expel|disorderly behaviou?r|rules of (?:its|their) proceedings",
    'emoluments': r"present, emolument|office of profit or trust.{0,260}(?:Congress|foreign)|emoluments whereof|\btitles? of nobility.{0,80}\bUnited States",
    'full-faith-credit': r"full faith and credit|public acts, records|records and judicial proceedings|credit shall be given",
    'extradition-clause': r"extradit|demand of the executive authority|fugitive from justice",
    'journal-clause': r"keep a journal|conceal their journals|yeas and nays",
}
