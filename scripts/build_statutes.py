"""Build docs/data/statutes.js: an index of federal statutes that come up in Supreme Court cases on the site.

  which statutes  the Supreme Court Database's statute codes (lawSupp 300-389: the statute each case turned on), plus other
                  statutes the case summaries name often (matched by name in the case's summary, question and holding)
  summary         the statute's Wikipedia article (CC BY-SA 4.0): the introduction, then the opening paragraphs of its
                  background / provisions / history sections, up to about 450 words; the hover blurb is the first two
                  sentences of the introduction
  link            the official U.S. Code via GovInfo (public domain) for statutes still in the Code; otherwise the
                  enacted text on Wikisource when Wikipedia links to one
  cases           SCDB-coded cases first, then cases whose summaries name the statute, ranked by later citations (CAP)
  tags            the site's area-of-law tags, plus a few statute-only areas (labor, business, environment, tax, benefits)
Cached: data/raw/statutes/wiki.json. Run from the repo root after build_case_impact.py:  python scripts/build_statutes.py
"""
import collections, csv, html, json, os, re, time, urllib.parse, urllib.request

RAW = 'data/raw/statutes'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build script)'}

# id, short name, Wikipedia title, SCDB codes, U.S.C. (title, section) or None, tags, name regex (None: built from the name)
S = [
    ('ada', 'Americans with Disabilities Act', 'Americans with Disabilities Act of 1990', [300], (42, 12101), ['equality'], r'Americans with Disabilities Act|\bADA\b'),
    ('adea', 'Age Discrimination in Employment Act', 'Age Discrimination in Employment Act', [302], (29, 621), ['equality', 'labor'], r'Age Discrimination in Employment Act|\bADEA\b'),
    ('afdc', 'Aid to Families with Dependent Children', 'Aid to Families with Dependent Children', [303], (42, 601), ['benefits'], r'Aid to Families with Dependent Children|\bAFDC\b'),
    ('caa', 'Clean Air Act', 'Clean Air Act (United States)', [304], (42, 7401), ['environment', 'admin'], r'Clean Air Act'),
    ('apa', 'Administrative Procedure Act', 'Administrative Procedure Act (United States)', [305], (5, 551), ['admin'], r'Administrative Procedure Act|\bAPA\b'),
    ('aea', 'Atomic Energy Act', 'Atomic Energy Act of 1954', [306], (42, 2011), ['environment', 'federalism'], r'Atomic Energy Act'),
    ('bankruptcy', 'Bankruptcy Code', 'Title 11 of the United States Code', [307], (11, 101), ['business'], r'Bankruptcy (?:Code|Act|Reform Act)'),
    ('medicaid', 'Medicaid Act', 'Medicaid', [308], (42, 1396), ['benefits', 'federalism'], r'\bMedicaid\b'),
    ('medicare', 'Medicare Act', 'Medicare (United States)', [309], (42, 1395), ['benefits'], r'\bMedicare\b'),
    ('clayton', 'Clayton Antitrust Act', 'Clayton Antitrust Act of 1914', [310], (15, 12), ['business'], r'Clayton (?:Antitrust )?Act'),
    ('s1981', '42 U.S.C. § 1981', 'Civil Rights Act of 1866', [312], (42, 1981), ['equality'], r'(?:§|[Ss]ection) ?1981\b|Civil Rights Act of 1866'),
    ('s1982', '42 U.S.C. § 1982', 'Civil Rights Act of 1866', [313], (42, 1982), ['equality'], r'(?:§|[Ss]ection) ?1982\b'),
    ('s1983', '42 U.S.C. § 1983', 'Section 1983', [314, 311], (42, 1983), ['equality', 'dueprocess'], r'(?:§|[Ss]ection) ?1983\b|Civil Rights Act of 1871'),
    ('s1985', '42 U.S.C. § 1985', 'Ku Klux Klan Act', [315, 316], (42, 1985), ['equality'], r'(?:§|[Ss]ection) ?1985\b|Ku Klux Klan Act'),
    ('cra1964', 'Civil Rights Act of 1964', 'Civil Rights Act of 1964', [317, 381, 382, 383, 385], (42, '2000a'), ['equality'], r'Civil Rights Act of 1964|Title II of the Civil Rights'),
    ('title6', 'Title VI of the Civil Rights Act', 'Title VI of the Civil Rights Act of 1964', [387], (42, '2000d'), ['equality', 'education'], r'Title VI\b'),
    ('title7', 'Title VII of the Civil Rights Act', 'Title VII of the Civil Rights Act of 1964', [384], (42, '2000e'), ['equality', 'labor'], r'Title VII\b'),
    ('cra1957', 'Civil Rights Act of 1957', 'Civil Rights Act of 1957', [318], None, ['voting', 'equality'], r'Civil Rights Act of 1957'),
    ('cra1991', 'Civil Rights Act of 1991', 'Civil Rights Act of 1991', [319], (42, '1981a'), ['equality', 'labor'], r'Civil Rights Act of 1991'),
    ('cra1875', 'Civil Rights Act of 1875', 'Civil Rights Act of 1875', [], None, ['equality'], r'Civil Rights Act of 1875'),
    ('eaja', 'Equal Access to Justice Act', 'Equal Access to Justice Act', [321], (28, 2412), ['article3'], r'Equal Access to Justice Act'),
    ('title9', 'Title IX', 'Title IX', [322], (20, 1681), ['equality', 'education'], r'Title IX\b|Education Amendments of 1972'),
    ('erisa', 'Employee Retirement Income Security Act', 'Employee Retirement Income Security Act of 1974', [323], (29, 1001), ['labor', 'benefits'], r'Employee Retirement Income Security Act|\bERISA\b'),
    ('esea', 'Elementary and Secondary Education Act', 'Elementary and Secondary Education Act', [324], (20, 6301), ['education'], r'Elementary and Secondary Education Act'),
    ('fca', 'False Claims Act', 'False Claims Act', [325], (31, 3729), ['business'], r'False Claims Act'),
    ('commact', 'Communications Act of 1934', 'Communications Act of 1934', [326], (47, 151), ['speech', 'admin', 'tech'], r'Communications Act'),
    ('feca', "Federal Employees' Compensation Act", "Federal Employees' Compensation Act", [327], (5, 8101), ['labor', 'benefits'], r"Federal Employees'? Compensation Act"),
    ('s1988', "Civil Rights Attorney's Fees Awards Act", "Civil Rights Attorney's Fees Awards Act of 1976", [328], (42, 1988), ['equality', 'article3'], r"(?:§|[Ss]ection) ?1988\b|Attorney's Fees Awards Act"),
    ('fela', "Federal Employers' Liability Act", "Federal Employers' Liability Act", [329], (45, 51), ['labor'], r"Federal Employers'? Liability Act|\bFELA\b"),
    ('fecaelect', 'Federal Election Campaign Act', 'Federal Election Campaign Act', [330], (52, 30101), ['voting', 'speech'], r'Federal Election Campaign Act|\bFECA\b'),
    ('ferpa', 'Family Educational Rights and Privacy Act', 'Family Educational Rights and Privacy Act', [331], (20, '1232g'), ['education', 'dueprocess'], r'Family Educational Rights and Privacy Act|\bFERPA\b'),
    ('fdca', 'Federal Food, Drug, and Cosmetic Act', 'Federal Food, Drug, and Cosmetic Act', [332], (21, 301), ['health', 'admin'], r'Food, Drug,? and Cosmetic Act|\bFDCA\b'),
    ('fifra', 'Federal Insecticide, Fungicide, and Rodenticide Act', 'Federal Insecticide, Fungicide, and Rodenticide Act', [333], (7, 136), ['environment'], r'Insecticide, Fungicide,? and Rodenticide Act|\bFIFRA\b'),
    ('flsa', 'Fair Labor Standards Act', 'Fair Labor Standards Act of 1938', [334], (29, 201), ['labor'], r'Fair Labor Standards Act|\bFLSA\b'),
    ('foia', 'Freedom of Information Act', 'Freedom of Information Act (United States)', [335], (5, 552), ['admin'], r'Freedom of Information Act|\bFOIA\b'),
    ('privacyact', 'Privacy Act of 1974', 'Privacy Act of 1974', [], (5, '552a'), ['admin', 'dueprocess'], r'Privacy Act'),
    ('fpa', 'Federal Power Act', 'Federal Power Act', [336], (16, '791a'), ['environment', 'admin'], r'Federal Power Act'),
    ('ftca', 'Federal Trade Commission Act', 'Federal Trade Commission Act of 1914', [337], (15, 41), ['business', 'seppowers'], r'Federal Trade Commission Act|\bFTC Act'),
    ('cwa', 'Clean Water Act', 'Clean Water Act', [338], (33, 1251), ['environment', 'admin'], r'Clean Water Act|Federal Water Pollution Control Act'),
    ('omnibus', 'Omnibus Crime Control and Safe Streets Act', 'Omnibus Crime Control and Safe Streets Act of 1968', [339], (34, 10101), ['crimpro'], r'Omnibus Crime Control|Safe Streets Act|Title III of the Omnibus'),
    ('gca', 'Gun Control Act of 1968', 'Gun Control Act of 1968', [], (18, 921), ['guns', 'crimpro'], r'Gun Control Act|18 U\.S\.C\. § 922'),
    ('nfa', 'National Firearms Act', 'National Firearms Act', [], (26, 5801), ['guns', 'tax'], r'National Firearms Act'),
    ('idea', 'Individuals with Disabilities Education Act', 'Individuals with Disabilities Education Act', [340], (20, 1400), ['education', 'equality'], r'Individuals with Disabilities Education Act|\bIDEA\b|Education for All Handicapped Children Act|Education of the Handicapped Act'),
    ('habeas', 'Federal habeas corpus statute (28 U.S.C. §§ 2241–2255)', 'Habeas corpus in the United States', [341], (28, 2241), ['crimpro', 'article3', 'security'], r'(?:§|[Ss]ection) ?22(?:41|54|55)\b|federal habeas'),
    ('aedpa', 'Antiterrorism and Effective Death Penalty Act', 'Antiterrorism and Effective Death Penalty Act of 1996', [], (28, 2244), ['crimpro', 'article3'], r'Antiterrorism and Effective Death Penalty Act|\bAEDPA\b'),
    ('fha', 'Fair Housing Act', 'Civil Rights Act of 1968', [342], (42, 3601), ['equality'], r'Fair Housing Act'),
    ('ica', 'Interstate Commerce Act', 'Interstate Commerce Act of 1887', [343], None, ['business', 'admin'], r'Interstate Commerce Act'),
    ('ina', 'Immigration and Nationality Act', 'Immigration and Nationality Act of 1952', [344], (8, 1101), ['citizenship'], r'Immigration and Nationality Act|\bINA\b|Illegal Immigration Reform and Immigrant Responsibility Act'),
    ('irc', 'Internal Revenue Code', 'Internal Revenue Code', [345], (26, 1), ['tax'], r'Internal Revenue Code|Revenue Act of \d{4}'),
    ('isa', 'Internal Security Act of 1950', 'McCarran Internal Security Act', [346], None, ['security', 'speech'], r'Internal Security Act|McCarran Act'),
    ('jencks', 'Jencks Act', 'Jencks Act', [347], (18, 3500), ['crimpro'], r'Jencks Act'),
    ('jones', 'Jones Act', 'Merchant Marine Act of 1920', [348], (46, 30104), ['labor'], r'Jones Act|Death on the High Seas Act'),
    ('lhwca', "Longshore and Harbor Workers' Compensation Act", "Longshore and Harbor Workers' Compensation Act", [349], (33, 901), ['labor', 'benefits'], r"Longshore(?:men's)? and Harbor Workers'? Compensation Act"),
    ('lmra', 'Labor Management Relations Act (Taft–Hartley)', 'Taft–Hartley Act', [350], (29, 141), ['labor'], r'Labor Management Relations Act|Taft-Hartley|Taft–Hartley'),
    ('lmrda', 'Labor Management Reporting and Disclosure Act', 'Labor Management Reporting and Disclosure Act', [351], (29, 401), ['labor'], r'Labor[- ]Management Reporting and Disclosure Act|Landrum-Griffin'),
    ('mca', 'Motor Carrier Act', 'Motor Carrier Act of 1935', [352], None, ['business', 'admin'], r'Motor Carrier Act'),
    ('miller', 'Miller Act', 'Miller Act', [353], (40, 3131), ['business'], r'Miller Act'),
    ('nepa', 'National Environmental Policy Act', 'National Environmental Policy Act', [354], (42, 4321), ['environment', 'admin'], r'National Environmental Policy Act|\bNEPA\b'),
    ('nga', 'Natural Gas Act', 'Natural Gas Act of 1938', [355], (15, 717), ['environment', 'admin'], r'Natural Gas (?:Policy )?Act'),
    ('nlra', 'National Labor Relations Act', 'National Labor Relations Act of 1935', [356], (29, 151), ['labor', 'admin'], r'National Labor Relations Act|\bNLRA\b|Wagner Act'),
    ('norris', 'Norris–LaGuardia Act', 'Norris–LaGuardia Act', [357], (29, 101), ['labor'], r'Norris-LaGuardia|Norris–LaGuardia'),
    ('osha', 'Occupational Safety and Health Act', 'Occupational Safety and Health Act (United States)', [358], (29, 651), ['labor', 'admin'], r'Occupational Safety and Health Act|\bOSH Act'),
    ('purpa', 'Public Utility Regulatory Policies Act', 'Public Utility Regulatory Policies Act', [359], (16, 2601), ['environment'], r'Public Utility Regulatory Polic(?:y|ies) Act|\bPURPA\b'),
    ('rehab', 'Rehabilitation Act of 1973', 'Rehabilitation Act of 1973', [360], (29, 701), ['equality'], r'Rehabilitation Act'),
    ('rfra', 'Religious Freedom Restoration Act', 'Religious Freedom Restoration Act', [361], (42, '2000bb'), ['religion'], r'Religious Freedom Restoration Act|\bRFRA\b'),
    ('rluipa', 'Religious Land Use and Institutionalized Persons Act', 'Religious Land Use and Institutionalized Persons Act', [], (42, '2000cc'), ['religion'], r'Religious Land Use and Institutionalized Persons Act|\bRLUIPA\b'),
    ('rico', 'Racketeer Influenced and Corrupt Organizations Act', 'Racketeer Influenced and Corrupt Organizations Act', [362], (18, 1961), ['crimpro', 'business'], r'Racketeer Influenced and Corrupt Organizations|\bRICO\b'),
    ('rla', 'Railway Labor Act', 'Railway Labor Act', [363], (45, 151), ['labor'], r'Railway Labor Act'),
    ('rpa', 'Robinson–Patman Act', 'Robinson–Patman Act', [364], (15, 13), ['business'], r'Robinson-Patman|Robinson–Patman'),
    ('secact', 'Securities Act of 1933', 'Securities Act of 1933', [365], (15, '77a'), ['business'], r'Securities Act of 1933'),
    ('secex', 'Securities Exchange Act of 1934', 'Securities Exchange Act of 1934', [], (15, '78a'), ['business', 'admin'], r'Securities Exchange Act|Exchange Act of 1934|Rule 10b-5'),
    ('ssa', 'Selective Service Act', 'Military Selective Service Act', [366], (50, 3801), ['security'], r'Selective Service|Selective Training and Service Act|Universal Military Training'),
    ('sherman', 'Sherman Antitrust Act', 'Sherman Antitrust Act of 1890', [367], (15, 1), ['business'], r'Sherman (?:Antitrust )?Act'),
    ('sla', 'Submerged Lands Act', 'Submerged Lands Act', [368], (43, 1301), ['federalism', 'environment'], r'Submerged Lands Act'),
    ('smith', 'Smith Act', 'Smith Act', [369], (18, 2385), ['speech', 'security'], r'Smith Act|Subversive Activities Control Act|Communist Control Act'),
    ('socsec', 'Social Security Act', 'Social Security Act', [370], (42, 301), ['benefits'], r'Social Security Act'),
    ('ssi', 'Supplemental Security Income', 'Supplemental Security Income', [371], (42, 1381), ['benefits'], r'Supplemental Security Income'),
    ('tila', 'Truth in Lending Act', 'Truth in Lending Act', [373], (15, 1601), ['business'], r'Truth in Lending Act|\bTILA\b'),
    ('ftcaTort', 'Federal Tort Claims Act', 'Federal Tort Claims Act', [374], (28, 2671), ['article3'], r'Federal Tort Claims Act'),
    ('ats', 'Alien Tort Statute', 'Alien Tort Statute', [], (28, 1350), ['article3', 'security'], r'Alien Tort (?:Statute|Claims Act)'),
    ('tucker', 'Tucker Act', 'Tucker Act', [375], (28, 1491), ['article3', 'takings'], r'Tucker Act'),
    ('twea', 'Trading with the Enemy Act', 'Trading with the Enemy Act of 1917', [376], (50, 4301), ['security'], r'Trading with the Enemy Act'),
    ('ucmj', 'Uniform Code of Military Justice', 'Uniform Code of Military Justice', [377], (10, 801), ['security', 'crimpro'], r'Uniform Code of Military Justice|\bUCMJ\b'),
    ('vra', 'Voting Rights Act of 1965', 'Voting Rights Act of 1965', [378], (52, 10301), ['voting', 'equality'], r'Voting Rights Act'),
    ('s1971', '52 U.S.C. § 10101 (formerly 42 U.S.C. § 1971)', 'Civil Rights Act of 1960', [379], (52, 10101), ['voting'], r'(?:§|[Ss]ection) ?1971\b'),
    ('faa', 'Federal Arbitration Act', 'Federal Arbitration Act', [388], (9, 1), ['business', 'article3'], r'Federal Arbitration Act'),
    ('ja1789', 'Judiciary Act of 1789', 'Judiciary Act of 1789', [389], None, ['article3'], r'Judiciary Act of 1789|Section 25 of the Judiciary Act|Section 13 of the Judiciary Act'),
    # statutes not coded by SCDB that the case summaries name often
    ('alien1798', 'Alien and Sedition Acts', 'Alien and Sedition Acts', [], None, ['speech', 'citizenship'], r'Alien and Sedition Acts|Sedition Act of 1798'),
    ('aea1798', 'Alien Enemies Act', 'Alien Enemies Act', [], (50, 21), ['security', 'citizenship'], r'Alien Enemies Act'),
    ('fugitive', 'Fugitive Slave Acts', 'Fugitive Slave Act of 1850', [], None, ['federalism', 'equality'], r'Fugitive Slave (?:Act|Law)'),
    ('missouri', 'Missouri Compromise', 'Missouri Compromise', [], None, ['citizenship', 'federalism'], r'Missouri Compromise'),
    ('espionage', 'Espionage Act of 1917', 'Espionage Act of 1917', [], (18, 793), ['speech', 'security'], r'Espionage Act|Sedition Act of 1918'),
    ('mann', 'Mann Act', 'Mann Act', [], (18, 2421), ['crimpro', 'federalism'], r'Mann Act|White-Slave Traffic Act'),
    ('nira', 'National Industrial Recovery Act', 'National Industrial Recovery Act of 1933', [], None, ['seppowers', 'federalism', 'business'], r'National Industrial Recovery Act|\bNIRA\b'),
    ('aaa', 'Agricultural Adjustment Act', 'Agricultural Adjustment Act', [], None, ['federalism', 'tax'], r'Agricultural Adjustment Act'),
    ('hatch', 'Hatch Act', 'Hatch Act of 1939', [], (5, 7321), ['speech', 'seppowers'], r'Hatch Act'),
    ('ira', 'Indian Reorganization Act', 'Indian Reorganization Act', [], (25, 5101), ['citizenship'], r'Indian Reorganization Act'),
    ('icwa', 'Indian Child Welfare Act', 'Indian Child Welfare Act', [], (25, 1901), ['citizenship', 'federalism'], r'Indian Child Welfare Act|\bICWA\b'),
    ('majorcrimes', 'Major Crimes Act', 'Major Crimes Act', [], (18, 1153), ['citizenship', 'crimpro'], r'Major Crimes Act'),
    ('icra', 'Indian Civil Rights Act', 'Indian Civil Rights Act of 1968', [], (25, 1301), ['citizenship'], r'Indian Civil Rights Act'),
    ('gfsza', 'Gun-Free School Zones Act', 'Gun-Free School Zones Act of 1990', [], (18, 922), ['guns', 'federalism'], r'Gun-Free School Zones Act'),
    ('brady', 'Brady Handgun Violence Prevention Act', 'Brady Handgun Violence Prevention Act', [], (34, 40901), ['guns', 'federalism'], r'Brady (?:Handgun Violence Prevention )?Act'),
    ('vawa', 'Violence Against Women Act', 'Violence Against Women Act', [], (34, 12291), ['federalism', 'equality'], r'Violence Against Women Act|\bVAWA\b'),
    ('csa', 'Controlled Substances Act', 'Controlled Substances Act', [], (21, 801), ['crimpro', 'federalism'], r'Controlled Substances Act'),
    ('aca', 'Affordable Care Act', 'Affordable Care Act', [], (42, 18001), ['benefits', 'health', 'federalism'], r'Affordable Care Act|Patient Protection and Affordable Care|\bACA\b|individual mandate'),
    ('doma', 'Defense of Marriage Act', 'Defense of Marriage Act', [], None, ['dueprocess', 'equality'], r'Defense of Marriage Act|\bDOMA\b'),
    ('bcra', 'Bipartisan Campaign Reform Act', 'Bipartisan Campaign Reform Act', [], (52, 30101), ['voting', 'speech'], r'Bipartisan Campaign Reform Act|McCain-Feingold|\bBCRA\b'),
    ('cda', 'Communications Decency Act', 'Communications Decency Act', [], (47, 230), ['speech', 'tech'], r'Communications Decency Act|Section 230'),
    ('copa', 'Child Online Protection Act', 'Child Online Protection Act', [], None, ['speech', 'tech'], r'Child Online Protection Act|\bCOPA\b'),
    ('milcom', 'Military Commissions Act of 2006', 'Military Commissions Act of 2006', [], (10, '948a'), ['security', 'crimpro'], r'Military Commissions Act'),
    ('dta', 'Detainee Treatment Act', 'Detainee Treatment Act of 2005', [], None, ['security'], r'Detainee Treatment Act'),
    ('aumf', 'Authorization for Use of Military Force (2001)', 'Authorization for Use of Military Force of 2001', [], None, ['security', 'seppowers'], r'Authorization for Use of Military Force|\bAUMF\b'),
    ('wpr', 'War Powers Resolution', 'War Powers Resolution', [], (50, 1541), ['security', 'seppowers'], r'War Powers Resolution|War Powers Act'),
    ('lineitem', 'Line Item Veto Act', 'Line Item Veto Act of 1996', [], None, ['seppowers'], r'Line Item Veto Act'),
    ('grh', 'Gramm–Rudman–Hollings Act', 'Gramm–Rudman–Hollings Balanced Budget Act', [], None, ['seppowers'], r'Gramm-Rudman|Gramm–Rudman|Balanced Budget and Emergency Deficit Control Act'),
    ('ethics', 'Ethics in Government Act', 'Ethics in Government Act', [], None, ['seppowers'], r'Ethics in Government Act|independent counsel provisions'),
    ('fvra', 'Federal Vacancies Reform Act', 'Federal Vacancies Reform Act of 1998', [], (5, 3345), ['seppowers'], r'Federal Vacancies Reform Act|Vacancies Act'),
    ('ieepa', 'International Emergency Economic Powers Act', 'International Emergency Economic Powers Act', [], (50, 1701), ['seppowers', 'security', 'business'], r'International Emergency Economic Powers Act|\bIEEPA\b'),
    ('fra', 'Federal Reserve Act', 'Federal Reserve Act', [], (12, 221), ['seppowers', 'business'], r'Federal Reserve Act'),
    ('insurrection', 'Insurrection Act', 'Insurrection Act of 1807', [], (10, 251), ['security', 'seppowers'], r'Insurrection Act'),
    ('fisa', 'Foreign Intelligence Surveillance Act', 'Foreign Intelligence Surveillance Act', [], (50, 1801), ['security', 'crimpro'], r'Foreign Intelligence Surveillance Act|\bFISA\b'),
    ('sca', 'Stored Communications Act', 'Stored Communications Act', [], (18, 2701), ['crimpro', 'tech'], r'Stored Communications Act'),
    ('cfaa', 'Computer Fraud and Abuse Act', 'Computer Fraud and Abuse Act', [], (18, 1030), ['crimpro', 'tech'], r'Computer Fraud and Abuse Act|\bCFAA\b'),
    ('copyright', 'Copyright Act of 1976', 'Copyright Act of 1976', [], (17, 101), ['ip'], r'Copyright Act'),
    ('lanham', 'Lanham Act', 'Lanham Act', [], (15, 1051), ['ip', 'speech'], r'Lanham Act'),
    ('patent', 'Patent Act', 'Patent Act of 1952', [], (35, 1), ['ip'], r'Patent Act'),
    ('plra', 'Prison Litigation Reform Act', 'Prison Litigation Reform Act', [], (42, '1997e'), ['crimpro', 'article3'], r'Prison Litigation Reform Act|\bPLRA\b'),
    ('esa', 'Endangered Species Act', 'Endangered Species Act of 1973', [], (16, 1531), ['environment'], r'Endangered Species Act'),
    ('cercla', 'CERCLA (Superfund)', 'Superfund', [], (42, 9601), ['environment'], r'Comprehensive Environmental Response|\bCERCLA\b|Superfund'),
    ('acca', 'Armed Career Criminal Act', 'Armed Career Criminal Act', [], (18, 924), ['crimpro', 'guns'], r'Armed Career Criminal Act|\bACCA\b'),
    ('sra', 'Sentencing Reform Act', 'Sentencing Reform Act', [], (18, 3551), ['crimpro'], r'Sentencing Reform Act|Sentencing Guidelines'),
    ('hobbs', 'Hobbs Act', 'Hobbs Act', [], (18, 1951), ['crimpro'], r'Hobbs Act'),
    ('fraud', 'Mail and wire fraud statutes', 'Mail and wire fraud', [], (18, 1341), ['crimpro'], r'wire fraud|mail fraud|honest[- ]services'),
    ('idtheft', 'Aggravated identity theft statute', 'Identity Theft Penalty Enhancement Act', [], (18, '1028A'), ['crimpro'], r'aggravated identity theft|(?:§|[Ss]ection) ?1028A'),
    ('firststep', 'First Step Act', 'First Step Act', [], None, ['crimpro'], r'First Step Act'),
    ('fmla', 'Family and Medical Leave Act', 'Family and Medical Leave Act of 1993', [], (29, 2601), ['labor', 'equality'], r'Family and Medical Leave Act|\bFMLA\b'),
    ('epa1963', 'Equal Pay Act', 'Equal Pay Act of 1963', [], (29, 206), ['labor', 'equality'], r'Equal Pay Act'),
    ('pda', 'Pregnancy Discrimination Act', 'Pregnancy Discrimination Act', [], (42, '2000e'), ['labor', 'equality'], r'Pregnancy Discrimination Act'),
    ('emtala', 'Emergency Medical Treatment and Active Labor Act', 'Emergency Medical Treatment and Active Labor Act', [], (42, '1395dd'), ['health', 'federalism'], r'Emergency Medical Treatment and Active Labor Act|\bEMTALA\b'),
    ('comstock', 'Comstock Act', 'Comstock laws', [], (18, 1461), ['speech', 'dueprocess'], r'Comstock (?:Act|laws?)'),
    ('stolenvalor', 'Stolen Valor Act', 'Stolen Valor Act of 2005', [], None, ['speech'], r'Stolen Valor Act'),
    ('tcpa', 'Telephone Consumer Protection Act', 'Telephone Consumer Protection Act of 1991', [], (47, 227), ['business', 'speech', 'tech'], r'Telephone Consumer Protection Act|\bTCPA\b'),
    ('fcra', 'Fair Credit Reporting Act', 'Fair Credit Reporting Act', [], (15, 1681), ['business', 'article3'], r'Fair Credit Reporting Act|\bFCRA\b'),
    ('telecom', 'Telecommunications Act of 1996', 'Telecommunications Act of 1996', [], (47, 251), ['business', 'tech'], r'Telecommunications Act'),
    ('cra_review', 'Congressional Review Act', 'Congressional Review Act', [], (5, 801), ['admin', 'seppowers'], r'Congressional Review Act'),
    ('ja1925', 'Judiciary Act of 1925', 'Judiciary Act of 1925', [], None, ['article3'], r'Judiciary Act of 1925|Judges\' Bill'),
    ('enforcement', 'Enforcement Acts', 'Enforcement Acts', [], None, ['voting', 'equality'], r'Enforcement Acts? of 18(?:70|71)|Force Acts?\b'),
    ('naturalization', 'Naturalization Act of 1790', 'Naturalization Act of 1790', [], None, ['citizenship'], r'Naturalization Act'),
    ('chinese', 'Chinese Exclusion Act', 'Chinese Exclusion Act', [], None, ['citizenship', 'equality'], r'Chinese Exclusion Act'),
    ('kansas', 'Kansas–Nebraska Act', 'Kansas–Nebraska Act', [], None, ['federalism'], r'Kansas-Nebraska Act|Kansas–Nebraska Act'),
    ('tenure', 'Tenure of Office Act', 'Tenure of Office Act (1867)', [], None, ['seppowers'], r'Tenure of Office Act'),
    ('pca', 'Posse Comitatus Act', 'Posse Comitatus Act', [], (18, 1385), ['security', 'seppowers'], r'Posse Comitatus Act'),
    ('rfa', 'Lacey Act', 'Lacey Act of 1900', [], (16, 3371), ['environment', 'crimpro'], r'Lacey Act'),
]
SECTION_WANT = re.compile(r'^(background|history|legislative history|provisions|major provisions|key provisions|content|contents|overview|summary|purpose|enactment|legislative background|text|description)$', re.I)
SKIP_LINE = re.compile(r'^(See also|References|External links|Further reading|Notes|Citations|Bibliography|Sources|Gallery|Footnotes|Works cited)$', re.I)


def load_js(name):
    s = open(f'docs/data/{name}.js', encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def api(params):
    url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({**params, 'format': 'json', 'formatversion': 2, 'redirects': 1})
    for attempt in range(6):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        except Exception:
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(url)


def wiki(titles):
    os.makedirs(RAW, exist_ok=True)
    path = f'{RAW}/wiki.json'
    have = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    for t in titles:
        if t in have:
            continue
        d = api({'action': 'query', 'prop': 'extracts|info|revisions', 'explaintext': 1, 'exsectionformat': 'wiki', 'inprop': 'url', 'rvprop': 'content', 'rvslots': 'main', 'titles': t})
        p = (d.get('query', {}).get('pages') or [{}])[0]
        wt = ((p.get('revisions') or [{}])[0].get('slots', {}).get('main', {}).get('content') or '')
        ws = re.search(r'\{\{\s*[Ww]ikisource(?:\s*\|\s*([^}|]+))?', wt)
        have[t] = {'title': p.get('title'), 'url': p.get('fullurl'), 'text': p.get('extract') or '',
                   'wikisource': (ws.group(1) or p.get('title')).strip() if ws else None,
                   'enacted': (re.search(r'\|\s*enacted by\s*=\s*([^\n]+)', wt) or [None, None])[1],
                   'publaw': (re.search(r'\|\s*public law\s*=\s*([^\n]+)', wt) or [None, None])[1],
                   'stat': (re.search(r'\|\s*statutes at large\s*=\s*([^\n]+)', wt) or [None, None])[1]}
        json.dump(have, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(2.5)
    return have


def infoboxes(titles):
    """wikitext of each article (50 titles per request), for the legislation infobox: Congress, public law, Statutes at Large."""
    path = f'{RAW}/wikitext.json'
    have = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    todo = [t for t in titles if t not in have]
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        d = api({'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main', 'titles': '|'.join(batch)})
        q = d.get('query', {})
        alias = {x['from']: x['to'] for k in ('normalized', 'redirects') for x in q.get(k, [])}
        pages = {p.get('title'): p for p in q.get('pages', [])}
        for t in batch:
            f = t
            for _ in range(3):
                f = alias.get(f, f)
            p = pages.get(f) or {}
            have[t] = ((p.get('revisions') or [{}])[0].get('slots', {}).get('main', {}).get('content') or '')
        json.dump(have, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(3)
    return have


def field(wt, *names):
    wt = re.sub(r'\{\{\s*US(?:PL|Pub\.?L)\s*\|\s*(\d+)\s*\|\s*(\d+)[^}]*\}\}', lambda m: f'Pub. L. {m[1]}–{m[2]}', wt, flags=re.I)
    wt = re.sub(r'\{\{\s*USStat\s*\|\s*(\d+)\s*\|\s*(\d+)[^}]*\}\}', lambda m: f'{m[1]} Stat. {m[2]}', wt, flags=re.I)
    for n in names:
        m = re.search(r'\|[ \t]*' + n + r'[ \t]*=[ \t]*([^\n]*)', wt)
        if m and wclean(m.group(1)):
            return wclean(m.group(1))
    return None


def wclean(s):
    s = re.sub(r'\{\{[^{}]*\}\}', '', s or '').replace("'''", '').replace("''", '')
    s = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', s)
    s = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>|<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip(' |') or None


def summarize(text, max_words=450):
    """intro paragraphs, then the opening paragraphs of background/provisions/history sections."""
    out, words, section, taken = [], 0, '', collections.Counter()
    any_wanted = any(SECTION_WANT.match(h) for h in re.findall(r'^==\s*(.*?)\s*==$', text, re.M))
    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'^(=+)\s*(.*?)\s*=+$', line)
        if m:
            section = m.group(2) if len(m.group(1)) == 2 else section
            continue
        if not line or len(line) < 80 or SKIP_LINE.match(section or ''):
            continue
        if section and not SECTION_WANT.match(section) and any_wanted:
            continue
        if section and taken[section] >= 2:
            continue
        n = len(line.split())
        if out and words + n > max_words:
            break
        line = re.sub(r'\s*\((?:\s*[;,]\s*)*\)', '', line)          # "( )" left where Wikipedia drops a pronunciation
        line = re.sub(r'\(\s*[;,]\s*', '(', line)
        out.append({'h': section, 'p': line})
        taken[section] += 1
        words += n
    return out


def sentences(p, n=2):
    # drop a citation parenthetical after the name: "The X Act (Pub.L. 103–159, 107 Stat. 1536, enacted ...) is ..."
    p = re.sub(r'\s*\((?=[^()]*(?:Pub\.\s?L|Stat\.|enacted|U\.S\.C))[^()]*\)', '', p, count=1)
    parts = re.split(r'(?<=[a-z0-9\)\]”"])\.\s+(?=[A-Z])', p)
    return ('. '.join(parts[:n]).rstrip('.') + '.') if parts else p


def usc_url(t, s):
    # uscode.house.gov's granuleid URLs now all return 404; GovInfo's stable link service redirects to the section
    return f'https://www.govinfo.gov/link/uscode/{t}/{s}'


WS = 'https://en.wikisource.org/wiki/'
# Enacted-text links checked by hand (200) for statutes with no U.S. Code section and no GovInfo Statutes at Large PDF (before vol. 65);
# the infobox gives no usable link for these. id: (url, label). Wikipedia's generic "url" field is a citation, not the text, so it is not used.
LINK_OVERRIDES = {
    'dta': (usc_url(42, '2000dd'), '42 U.S.C. § 2000dd (GovInfo)'),
    'enforcement': (WS + 'Enforcement_Act_of_1870', 'Enacted text (Wikisource)'),
    'firststep': ('https://www.govinfo.gov/content/pkg/STATUTE-132/pdf/STATUTE-132-Pg5194.pdf', '132 Stat. 5194 (GovInfo)'),
    'fugitive': (WS + 'Fugitive_Slave_Act_of_1850', 'Enacted text (Wikisource)'),
    'chinese': ('https://www.archives.gov/milestone-documents/chinese-exclusion-act', 'Enacted text (National Archives)'),
    'isa': (WS + 'Internal_Security_Act_of_1950', 'Enacted text (Wikisource)'),
    'ica': ('https://www.archives.gov/milestone-documents/interstate-commerce-act', 'Enacted text (National Archives)'),
    'mca': ('https://www.archives.gov/milestone-documents/interstate-commerce-act', 'Enacted text (National Archives)'),
    'cra1875': (WS + 'Civil_Rights_Act_of_1875', 'Enacted text (Wikisource)'),
    'ja1789': (WS + 'Judiciary_Act_of_1789', 'Enacted text (Wikisource)'),
    'missouri': (WS + 'Missouri_Compromise', 'Enacted text (Wikisource)'),
    'nira': ('https://www.archives.gov/milestone-documents/national-industrial-recovery-act', 'Enacted text (National Archives)'),
    'naturalization': (WS + 'United_States_Statutes_at_Large/Volume_1/1st_Congress/2nd_Session/Chapter_3', 'Enacted text (Wikisource, 1 Stat. 103)'),
}


def scdb_cases():
    cases = load_js('scotus')['cases']
    by_cite = {c['cit']: c['id'] for c in cases if c.get('cit')}
    by_dk = {(str(c['t']), (c.get('d') or '').lower()): c['id'] for c in cases}
    out = collections.defaultdict(set)
    for f in ('data/raw/scdb/csv/SCDB_Legacy_07_justiceCentered_Citation.csv', 'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Citation.csv',
              'data/raw/scdb/csv/SCDB_2026_01_justiceCentered_Docket.csv'):
        for r in csv.DictReader(open(f, encoding='latin-1')):
            code = r['lawSupp']
            if not code.isdigit() or not 300 <= int(code) < 400:
                continue
            cid = by_cite.get(r['usCite'].strip()) or by_cite.get(r['sctCite'].strip()) or by_dk.get((r['term'], r['docket'].replace('â\u0080\u0093', '-').strip().lower()))
            if cid:
                out[int(code)].add(cid)
    return out


def main():
    W = wiki(sorted({x[2] for x in S}))
    cases = load_js('scotus')['cases']
    docket = load_js('docket')['cases']
    impact = load_js('case_impact')['c']
    coded = scdb_cases()
    text = {c['id']: ' '.join([c.get('ds') or '', c.get('q') or '', c.get('h') or '']) for c in cases}
    for e in docket:
        text.setdefault(e['id'], ' '.join([e.get('ds') or '', e.get('q') or '']))
    # Oyez's facts of the case and conclusion (cached by flashcards_fetch.py / oyez_fetch_all.py) usually name the statute
    for f in os.listdir('data/raw/oyez/cases'):
        cid = f[:-5].replace('_', '/', 1)
        if cid in text:
            try:
                d = json.load(open(f'data/raw/oyez/cases/{f}', encoding='utf-8'))
            except Exception:
                continue
            text[cid] += ' ' + re.sub(r'<[^>]+>', ' ', html.unescape((d.get('facts_of_the_case') or '') + ' ' + (d.get('conclusion') or '')))
    IB = infoboxes(sorted({x[2] for x in S}))
    out, missing, dropped = [], [], []
    for sid, name, title, codes, usc, tags, rx in S:
        w = W.get(title) or {}
        paras = summarize(w.get('text') or '')
        if not paras:
            missing.append(title)
            continue
        hits = set().union(*[coded.get(c, set()) for c in codes]) if codes else set()
        mention = {cid for cid, t in text.items() if re.search(rx, t)}
        if not hits and not mention:
            dropped.append(sid)
            continue
        ids = sorted(hits | mention, key=lambda cid: (cid not in hits, -(impact.get(cid) or [0, 0, 0])[1]))
        wt = IB.get(title) or ''
        enacted, publaw = field(wt, 'enacted by'), field(wt, 'cite public law', 'public law')
        stat = field(wt, 'cite statutes at large', 'statutes at large')
        sm = re.match(r'^(\d+)\s+Stat\.\s+(\d+)', stat or '')
        purl = field(wt, 'public law url')
        purl = (re.match(r'https?://[^\s|}\]]+', purl or '') or [None])[0]   # stop at the first space, | or }
        link = ({'url': usc_url(*usc), 'label': f'{usc[0]} U.S.C. § {usc[1]} (GovInfo)'} if usc else
                {'url': f'https://www.govinfo.gov/content/pkg/STATUTE-{sm[1]}/pdf/STATUTE-{sm[1]}-Pg{sm[2]}.pdf', 'label': f'{sm[1]} Stat. {sm[2]} (GovInfo)'} if sm and int(sm[1]) >= 65 else
                {'url': purl, 'label': f'{stat} (enacted text)' if stat else 'Enacted text'} if purl else
                {'url': 'https://en.wikisource.org/wiki/' + urllib.parse.quote(w['wikisource'].replace(' ', '_')), 'label': 'Enacted text (Wikisource)'} if w.get('wikisource') else None)
        if sid in LINK_OVERRIDES:
            link = {'url': LINK_OVERRIDES[sid][0], 'label': LINK_OVERRIDES[sid][1]}
        out.append({'id': sid, 'n': name, 'blurb': sentences(paras[0]['p']), 'paras': paras, 'tags': tags, 'rx': rx,
                    'link': link, 'enacted': enacted and re.sub(r'^(?:the )?(\d+(?:st|nd|rd|th))$', r'\1 Congress', enacted), 'publaw': publaw, 'stat': stat,
                    'wiki': {'title': w.get('title'), 'url': w.get('url')}, 'cases': ids, 'coded': len(hits)})
    out.sort(key=lambda x: x['n'].lstrip('0123456789 .U.S.C§').lower())
    data = {'src': 'Summaries from Wikipedia (CC BY-SA 4.0). Statute text from the U.S. Code (GovInfo, Office of the Law Revision Counsel), the National Archives and Wikisource. Case links from the Supreme Court Database (lawSupp) and case summaries.', 'statutes': out}
    open('docs/data/statutes.js', 'w', encoding='utf-8').write('window.STATUTES=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{len(out)} statutes ({sum(1 for x in out if x["link"])} with a link to the text); {sum(len(x["cases"]) for x in out)} case links')
    if missing:
        print('no Wikipedia text:', missing)
    if dropped:
        print('left out (no cases on the site):', ' '.join(dropped))
    for x in out:
        if not x['link']:
            print(f"  {x['id']:14} cases={len(x['cases']):4} link={'yes' if x['link'] else 'NO'}")


if __name__ == '__main__':
    main()
