"""Full texts for the library reader, from Wikisource and Project Gutenberg (public-domain texts; Wikisource
transcriptions are CC BY-SA, Project Gutenberg texts are public domain in the U.S.; the source is credited on every page
of the reader).

Wikisource works (WIKISOURCE): the root page's table of contents is read in order, each chapter page is fetched through
the MediaWiki API (one request every ~2 seconds; cached in data/raw/library/<id>/), headers, footnote markers and
editing links are dropped, and paragraphs and headings are kept.
Project Gutenberg works (GUTENBERG): the HTML edition of each eBook is downloaded once (from gutenberg.org, or from one
of Project Gutenberg's official mirrors when the main site is down; cached in data/raw/library/gutenberg/<n>.html), the
licence header and footer, tables of contents, footnotes and page numbers are dropped, and the text is split into parts
at its chapter headings.
Collections (COLLECTIONS) gather shorter works into one book, a part per essay or letter: pamphlets transcribed by the
Text Creation Partnership's Evans collection (Evans-TCP, Phase I, released under CC0; the TEI XML is read from the TCP
repositories on GitHub and cached in data/raw/library/tcp/; letters the transcribers could not read are shown as ◊) and
single Wikisource pages.
Output, one small file per part so the reader loads only what is read:
  docs/data/lib/<id>.js        window.LIB_BOOKS[id] = {id, title, author, year, src, srcName, license, toc: [[title, words], ...]}
  docs/data/lib/<id>-<n>.js    window.LIB_CHS['<id>-<n>'] = {id, n, t, b: [[kind, text], ...]}  kind: 'h' heading, 'p' paragraph
  docs/data/lib-index.js       window.LIB_INDEX = [{id, title, author, year, corner, chapters, words, srcName}, ...]
Run from the repo root:  python scripts/library_books.py [book id ...]
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'LexConstitutio/1.0 (static site build)'}
RAW = 'data/raw/library'
OUT = 'docs/data/lib'
WIKISOURCE = [
    # id, title, author, year, Wikisource root page, Originalist's Corner source id it stands for ('' if none)
    ('story', 'Commentaries on the Constitution of the United States', 'Joseph Story', '1833',
     'Commentaries on the Constitution of the United States', 'story'),
    ('blackstone', 'Commentaries on the Laws of England', 'William Blackstone', '1765–1769',
     'Commentaries on the Laws of England', 'blackstone'),
    ('spirit-of-laws', 'The Spirit of Laws', 'Montesquieu', '1748 (Nugent trans., 1758 ed.)', 'The Spirit of Laws (1758)', ''),
    ('notes-virginia', 'Notes on the State of Virginia', 'Thomas Jefferson', '1785 (1802 ed.)', 'Notes on the State of Virginia (1802)', ''),
    ('cato', "Cato's Letters", 'John Trenchard and Thomas Gordon', '1720–1723', "Cato's Letters", '', "Cato's Letter No. "),
    ('otis', 'The Rights of the British Colonies Asserted and Proved', 'James Otis', '1764',
     'The Rights of the British Colonies Asserted and Proved', ''),
    ('thoughts-government', 'Thoughts on Government', 'John Adams', '1776', 'Thoughts on Government', ''),
    ('summary-view', 'A Summary View of the Rights of British America', 'Thomas Jefferson', '1774',
     'A Summary View of the Rights of British America', ''),
    ('farrand-3', 'The Records of the Federal Convention of 1787, Volume III: Letters, Recollections and Documents',
     'Max Farrand (ed.)', '1787–1837 (pub. 1911)', 'The Records of the Federal Convention of 1787/Volume 3', ''),
]
GUTENBERG = [
    # id, title, author, year, eBook numbers (volumes in order), Corner source id, options
    ('madison', 'The Journal of the Debates in the Convention which Framed the Constitution', 'James Madison',
     '1787 (Hunt ed., 1908)', [40861, 41095], 'madison',
     {'title_re': r'^((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[\s,]+\w+\.?\s+\d+(?:st|nd|rd|th|d)?)'}),
    ('tocqueville', 'Democracy in America', 'Alexis de Tocqueville', '1835–1840 (Reeve trans.)', [815, 816], '', {}),
    ('common-sense', 'Common Sense', 'Thomas Paine', '1776', [147], '', {}),
    ('farmer-letters', 'Letters from a Farmer in Pennsylvania', 'John Dickinson', '1767–1768', [47111], '', {}),
    ('novanglus', 'Novanglus and Massachusettensis', 'John Adams and Daniel Leonard', '1774–1775', [45205], '', {}),
    ('grotius', 'The Rights of War and Peace', 'Hugo Grotius', '1625 (Campbell trans.)', [46564], '', {}),
    ('lincoln-speeches', 'Noted Speeches of Abraham Lincoln, Including the Lincoln–Douglas Debate', 'Abraham Lincoln', '1838–1865', [48364], '', {}),
    ('ford-essays', 'Essays on the Constitution of the United States, Published During Its Discussion by the People',
     'Paul Leicester Ford (ed.): Agrippa, Cato, Sydney, Luther Martin, the Landholder and others', '1787–1788 (pub. 1892)', [31891], '',
     {'smart': True, 'drop_front': True, 'rename': {
         'A Letter to the Landholder. by William Williams': 'A Letter to the Landholder, by William Williams',
         'The Letters of a Countryman. Written by Roger Sherman': 'The Letters of a Countryman, Written by Roger Sherman',
         'The Letters of Sydney. Written by Robert Yates': 'The Letters of Sydney, Written by Robert Yates'}}),
    ('ford-pamphlets', 'Pamphlets on the Constitution of the United States, Published During Its Discussion by the People',
     'Paul Leicester Ford (ed.): Gerry, Jay, Dickinson, Mason, Iredell, Richard Henry Lee and others', '1787–1788 (pub. 1888)', [47110], '',
     # part titles in the library's style; Ford's attributions are kept (the Columbian Patriot is now known to be Mercy Otis
     # Warren, and the Federal Farmer is no longer credited to Richard Henry Lee)
     {'invert_name': True, 'drop_front': True, 'rename': {
         'Elbridge Gerry, Observations on the New Constitution, and on the Federal and State Conventions. By a Columbian Patriot':
             '"A Columbian Patriot" (Mercy Otis Warren), Observations on the New Constitution',
         'Noah Webster, An Examination into the leading principles of the Federal Constitution. By a Citizen of America':
             'Noah Webster, An Examination into the Federal Constitution',
         'John Jay, An Address to the People of the State of New York, on the subject of the Constitution. By a Citizen of New York':
             'John Jay, An Address to the People of the State of New York',
         'Melancthon Smith, Address to the People of the State of New York. By a Plebeian':
             'Melancton Smith ("A Plebeian"), Address to the People of the State of New York',
         'Pelatiah Webster, The Weakness of Brutus exposed: or some remarks in vindication of the Constitution. By a Citizen of Philadelphia':
             'Pelatiah Webster, The Weakness of Brutus Exposed',
         'Tench Coxe, An Examination of the Constitution of the United States of America. By an American Citizen':
             'Tench Coxe ("An American Citizen"), An Examination of the Constitution',
         'Alexander Contee Hanson, Remarks on the Proposed Plan of a Federal Government. By Aristides':
             'Alexander Contee Hanson ("Aristides"), Remarks on the Proposed Plan',
         'Richard Henry Lee, Observations of the System of Government proposed by the late Convention. By a Federal Farmer':
             'The Federal Farmer, Observations on the System of Government',
         'James Iredell, Observations on George Mason’s Objections to the Federal Constitution. By Marcus':
             'James Iredell ("Marcus"), Observations on George Mason’s Objections',
         'David Ramsay, An Address to the Freemen of South Carolina on the Federal Constitution. By Civis':
             'David Ramsay ("Civis"), An Address to the Freemen of South Carolina'}}),
    ('hume-political', 'Political Discourses', 'David Hume', '1752 (Scott Library ed.)', [59792], '',
     {'drop_front': True, 'drop_re': r'^NOTES?, ', 'skip_re': r'^alphabetical arrangement'}),
    ('lincoln-douglas', 'The Lincoln–Douglas Debates of 1858', 'Abraham Lincoln and Stephen A. Douglas', '1858 (Lapsley ed.)', [2655, 2656], '',
     {'drop_front': True, 'vol_labels': ['', ''],
      'nosplit_re': r"^(?:VOLUME |THE (?:PAPERS|WRITINGS|LINCOLN-DOUGLAS)|Mr\.? (?:LINCOLN|DOUGLAS)|INTERROGATORIES|CAMPBELL)", 'rename': {
          'First Joint Debate, at Ottawa': 'First Joint Debate, at Ottawa, August 21, 1858',
          'Second Joint Debate, at Freeport': 'Second Joint Debate, at Freeport, August 27, 1858',
          'Third Joint Debate, at Jonesboro': 'Third Joint Debate, at Jonesboro, September 15, 1858',
          'Lincoln and Douglas Fourth Debate, at Charleston, September 18, 1858': 'Fourth Joint Debate, at Charleston, September 18, 1858',
          'Last Debate, at Alton, October 15, 1858': 'Seventh Joint Debate, at Alton, October 15, 1858'}}),
    ('webster-speeches', 'Select Speeches, 1817–1845', 'Daniel Webster', '1817–1845 (George ed.)', [7600], '',
     {'drop_front': True, 'nosplit_re': r'^Select Speeches', 'skip_re': r'^biographical'}),
    ('blaine-congress-2', 'Twenty Years of Congress, Volume II: From Lincoln to Garfield', 'James G. Blaine', '1886', [20065], '',
     {'start_re': r'^Twenty Years of Congress$', 'start_last': True, 'toc_titles': True, 'smart': True,
      'skip_re': r'^(?:twenty years of congress|list of steel portraits)$|^(?:annual production of gold|years\. gold)'}),
    ('douglass-writings', 'Writings and Addresses on Reconstruction and Civil Rights', 'Frederick Douglass', '1866–1886', [99, 67919], '',
     {'drop_front': True, 'nosplit_re': r'^by Frederick', 'vol_labels': ['Collected Articles', 'Three Addresses'], 'rename': {
         'In Louisville, KY': 'Address at Louisville, Kentucky, 1883', 'In Louisville, KY., 1883': 'Address at Louisville, Kentucky, 1883',
         'In Washington, D. C., 1885': 'Address at Washington, D.C., 1885', 'In Washington, D. C., 1886': 'Address at Washington, D.C., 1886'}}),
    # added November 2026: English precedents, the Revolutionary argument, framing histories, early practice, Reconstruction
    ('mckechnie-magna-carta', 'Magna Carta: A Commentary on the Great Charter of King John', 'William Sharp McKechnie',
     '1215 (commentary, 1905)', [65363], '',
     {'drop_front': True, 'stop_re': r'^Select Bibliography', 'resplit': {r'^Magna Carta$': 'h3'},
      'title_sub': [(r'^PART V\.?$', 'Part V. Manuscripts, Editions and Commentaries')],
      'rename': {'Historical Introduction': 'Historical Introduction: Part I. Events Leading to Magna Carta',
                 'Text, Translation, and Commentary': 'Text, Translation and Commentary: Preamble'}}),
    ('hallam-constitutional', 'The Constitutional History of England from Henry VII to George II', 'Henry Hallam',
     '1827 (Everyman ed.)', [39711, 42179, 44410], '',
     {'drop_front': True, 'sub_title': True, 'skip_re': r'^(?:preface|introduction|bibliography)', 'vol_labels': ['', '', ''],
      'vol_opt': {1: {'split': 'h3'}},
      'title_sub': [(r'^CHAPTER ([XVI]+) (?=[A-Z])', r'CHAPTER \1: ')]}),
    ('milton-areopagitica', 'Areopagitica: A Speech for the Liberty of Unlicensed Printing', 'John Milton', '1644', [608], '', {}),
    ('price-civil-liberty', 'Two Tracts on Civil Liberty, the War with America, and the Debts and Finances of the Kingdom', 'Richard Price',
     '1776–1777', [57970], '',
     {'drop_front': True, 'skip_re': r'^(?:corrections|a summary view and comparison)',
      'title_sub': [(r'^PART I\. SUPPLEMENTAL.*', 'Additional Observations, Part I: The Nature and Value of Civil Liberty'),
                    (r'^PART II\. CONTAINING.*', 'Additional Observations, Part II: Remarks on the Budget Speech of 1776')],
      'rename': {'General Introduction': 'General Introduction (1778)',
                 'Observations, &C': 'Observations on the Nature of Civil Liberty (1776), Part I',
                 'Part II': 'Observations on the Nature of Civil Liberty, Part II: The War with America',
                 'Introduction': 'Additional Observations (1777): Introduction',
                 'Part III': 'Additional Observations, Part III: The War and the National Debt',
                 'Supplement to Section III Part II': 'Additional Observations: Supplement on Public Loans'}}),
    ('burke-america', 'Speeches on American Taxation and Conciliation with the Colonies, and to the Electors of Bristol', 'Edmund Burke',
     '1774–1777', [15198], '',
     {'drop_front': True, 'stop_re': r'^Two Letters to Gentlemen', 'skip_re': r'^The Works of', 'nosplit_re': r'^(?:PREFACE|SPEECH)\.$', 'rename': {
         'Speech on American Taxation. April 19, 1774': 'Speech on American Taxation (April 19, 1774)',
         'Speeches at His Arrival at Bristol, and at the Conclusion of the Poll. 1774': 'Speeches at Bristol (1774): Editor’s Advertisement',
         'Speech at His Arrival at Bristol': 'Speech at His Arrival at Bristol (1774)',
         'Speech on Moving His Resolutions for Conciliation with the Colonies. March 22, 1775': 'Speech on Conciliation with the Colonies (March 22, 1775)'},
      'title_sub': [(r'^SPEECH TO THE ELECTORS OF BRISTOL.*', 'Speech to the Electors of Bristol at the Conclusion of the Poll (1774)'),
                    (r'^A LETTER TO JOHN FARR AND JOHN HARRIS.*', 'Letter to the Sheriffs of Bristol on the Affairs of America (1777)')]}),
    ('paine-crisis', 'The American Crisis', 'Thomas Paine', '1776–1783 (Conway ed.)', [3741], '',
     {'drop_front': True, 'split': 'h2', 'smart': True, 'skip_re': r'^1774',
      'title_sub': [(r'^THE CRISIS\.? ([IVX]+)\.?\s*\(?([^)]*?)\)?$', r'The Crisis \1: \2'), (r'^THE CRISIS\.? ([IVX]+)\.?$', r'The Crisis \1')]}),
    ('paine-rights', 'Rights of Man', 'Thomas Paine', '1791–1792 (Conway ed.)', [3742], '',
     {'drop_front': True, 'smart': True, 'skip_re': r'^(?:by thomas paine|1779)', 'nosplit_re': r'^RIGHTS OF MAN(?: PART II)?\.?$',
      'title_sub': [(r"^PAINE'S PREFACE TO THE (ENGLISH|FRENCH) EDITION$", r'PART THE FIRST: PREFACE TO THE \1 EDITION'),
                    (r'^RIGHTS OF MAN\. PART THE FIRST.*', 'PART THE FIRST: BEING AN ANSWER TO MR. BURKE’S ATTACK ON THE FRENCH REVOLUTION'),
                    (r'^OBSERVATIONS ON THE DECLARATION OF RIGHTS$', 'PART THE FIRST: OBSERVATIONS ON THE DECLARATION OF RIGHTS'),
                    (r'^RIGHTS OF MAN\. PART SECOND.*', 'PART SECOND: FRENCH TRANSLATOR’S PREFACE'),
                    (r'^(PREFACE|INTRODUCTION|APPENDIX)\.?$', r'PART SECOND: \1'),
                    (r'^CHAPTER ([IV]+)\. ', r'PART SECOND, CHAPTER \1: '),
                    (r"^EDITOR'S INTRODUCTION\.?$", 'EDITOR’S INTRODUCTION (MONCURE D. CONWAY)'),
                    (r"^THE AUTHOR'S NOTES.*", 'THE AUTHOR’S NOTES')]}),
    ('curtis-history', 'History of the Origin, Formation, and Adoption of the Constitution of the United States', 'George Ticknor Curtis',
     '1854–1858', [40400, 40679], '',
     {'drop_front': True, 'sub_title': True, 'book_re': r'^Book [IVX]+\b', 'smart': True, 'skip_re': r'^By George Ticknor'}),
    ('annual-messages', 'Annual Messages to Congress, 1790–1816', 'George Washington, John Adams, Thomas Jefferson and James Madison',
     '1790–1816', [5010, 5011, 5012, 5013], '',
     {'drop_front': True, 'split': 'h2', 'vol_labels': ['', '', '', ''], 'head_text': True,
      'head_re': r'^State of the Union Address (?:George Washington|John Adams|Thomas Jefferson|James Madison) \w+ \d',
      'title_sub': [(r'^State of the Union Address (?:George |John |Thomas |James )?(\w+) (.*)$', r'\1, Annual Message, \2')]}),
    ('marshall-washington', 'The Life of George Washington', 'John Marshall', '1804–1807 (1926 reprint)',
     [18591, 18592, 18593, 18594, 18595], '',
     {'drop_front': True, 'sub_title': True, 'smart': True,
      'skip_re': r"^(?:publisher's preface|illustrations|list of illustrations|the life|george washington|american forces|first president|united states|an introduction|introduction|independence|by john marshall)$"}),
    ('tucker-slavery', 'A Dissertation on Slavery, with a Proposal for the Gradual Abolition of It, in the State of Virginia',
     'St. George Tucker', '1796', [32239], '', {'drop_front': True, 'smart': True}),
    ('dred-scott', 'Dred Scott v. Sandford: The Decision and the Opinions of the Judges', 'Supreme Court of the United States (Howard’s report)',
     '1857', [31425], '',
     {'drop_front': True, 'split': 'h2',
      'head_re': r'^Mr\. (?:Chief )?Justice (?:[A-Z]{2,}|McLEAN)(?: dissenting| delivered the opinion of the court)?\.$',
      'rename': {'December Term, 1856': 'The Case and the Arguments',
                 'Mr. Chief Justice TANEY delivered the opinion of the court': 'Opinion of the Court, Chief Justice Taney',
                 'Mr. Justice WAYNE': 'Justice Wayne, concurring', 'Mr. Justice NELSON': 'Justice Nelson, concurring',
                 'Mr. Justice GRIER': 'Justice Grier, concurring', 'Mr. Justice DANIEL': 'Justice Daniel, concurring',
                 'Mr. Justice CAMPBELL': 'Justice Campbell, concurring', 'Mr. Justice CATRON': 'Justice Catron, concurring',
                 'Mr. Justice McLEAN dissenting': 'Justice McLean, dissenting', 'Mr. Justice CURTIS dissenting': 'Justice Curtis, dissenting'}}),
    ('ross-impeachment', 'History of the Impeachment of Andrew Johnson', 'Edmund G. Ross', '1896', [2442], '',
     {'drop_front': True, 'smart': True, 'title_sub': [(r'^CHAPTER (\w+)\. — ', r'CHAPTER \1: '), (r'^CHAPTER 1:', 'CHAPTER I:')],
      'rename': {'By Edmund G. Ross': 'Preface'}}),
    ('lynch-reconstruction', 'The Facts of Reconstruction', 'John R. Lynch', '1913', [16158], '',
     {'drop_front': True, 'smart': True, 'sub_title': True, 'skip_re': r'^the facts of reconstruction$', 'rename': {'John R. Lynch': 'Preface'}}),
]


COLLECTIONS = [
    ('locke', 'Two Treatises of Government', 'John Locke', '1690 (first edition)', 'locke', [
        ('First Treatise · {head}', 'tcp', 'A48901', {'type': 'chapter', 'within': {'type': 'book', 'n': '1'}}),
        ('Second Treatise · {head}', 'tcp', 'A48901', {'type': 'chapter', 'within': {'type': 'book', 'n': '2'}}),
    ]),
    ('sidney', 'Discourses Concerning Government', 'Algernon Sidney', '1698', '', [
        ('Chapter I · {head}', 'tcp', 'A60214', {'type': 'section', 'within': {'type': 'chapter', 'n': '1'}}),
        ('Chapter II · {head}', 'tcp', 'A60214', {'type': 'section', 'within': {'type': 'chapter', 'n': '2'}}),
        ('Chapter III · {head}', 'tcp', 'A60214', {'type': 'section', 'within': {'type': 'chapter', 'n': '3'}}),
    ]),
    ('oceana', 'The Commonwealth of Oceana', 'James Harrington', '1656', '', [
        ('{head}', 'tcp', 'A45613', {'type': 'part'}),
        ('The Corollary', 'tcp', 'A45613', {'type': 'corollary'}),
    ]),
    # id, title, author line, year, Corner source id, [(part title, source, page or eBook, selector)]
    # source 'tcp': selector picks divisions of the TEI body: {'type': ..., 'head': regex}; the part title may use {num}
    # (the Roman numeral in the division's heading) or {head}; 'ws': a Wikisource page
    ('antifederalists', 'The Anti-Federalists',
     'Centinel, the Federal Farmer, the Pennsylvania Minority, Edmund Randolph, Mercy Otis Warren, James Monroe', '1787–1788', 'antifederalist', [
        ('Centinel No. {num}', 'tcp', 'N16599', {'type': 'letter', 'head': r'^CENTINEL'}),
        ('Federal Farmer, Letter {num}', 'tcp', 'N15980', {'type': 'letter'}),
        ('The Address and Reasons of Dissent of the Minority of the Convention of Pennsylvania', 'tcp', 'N16599', {'type': 'reasons_of_dissent'}),
        ('Edmund Randolph, Letter on the Federal Constitution', 'tcp', 'N16126', {'type': 'letter', 'head': r'^A LETTER OF HIS EXCELLENCY'}),
        ('Mercy Otis Warren ("A Columbian Patriot"), Observations on the New Constitution', 'tcp', 'N16431', {'type': 'text'}),
        ('James Monroe, Observations upon the Proposed Plan of Federal Government', 'tcp', 'N16547', {'type': 'text'}),
        ('James Monroe, Observations upon the Proposed Plan of Federal Government (continued): the Plan Examined', 'tcp', 'N16547', {'type': 'discussion_of_constitution'}),
    ]),
    ('federalist-pamphlets', 'Federalist Pamphlets', 'James Wilson, Tench Coxe, Alexander Contee Hanson', '1787–1788', '', [
        ("James Wilson, State House Yard Speech (October 6, 1787)", 'tcp', 'N16378', {'type': 'speech'}),
        ('Tench Coxe, An Examination of the Constitution, No. {num}', 'tcp', 'N16378', {'type': 'part'}),
        ('Alexander Contee Hanson ("Aristides"), Remarks on the Proposed Plan of a Federal Government', 'tcp', 'N16445', {'type': 'text'}),
    ]),
    # later periods (the library lists these apart from the founding era: era 'later')
    ('union-slavery-war', 'Union, Slavery and Civil War: Documents, 1830–1865', 'Webster, Jackson, the Seneca Falls Convention, Douglass, Lincoln and others', '1830–1865', '', [
        ("Daniel Webster, Second Reply to Hayne (1830)", 'ws', 'The Great Speeches and Orations of Daniel Webster/The Reply to Hayne', None),
        ("Andrew Jackson, Proclamation Regarding Nullification (1832)", 'ws', 'Proclamation 43', None),
        ('Declaration of Sentiments, Seneca Falls Convention (1848)', 'ws', 'Declaration of Sentiments', None),
        ('Frederick Douglass, What to the Slave Is the Fourth of July? (1852)', 'ws', 'What to the Slave Is the Fourth of July?', None),
        ('Abraham Lincoln, "A House Divided" (1858)', 'ws', 'Life and Works of Abraham Lincoln/Volume 4/A House Divided Against Itself Cannot Stand', None),
        ('South Carolina, Declaration of the Causes of Secession (1860)', 'ws', 'Declaration of the Immediate Causes Which Induce and Justify the Secession of South Carolina from the Federal Union', None),
        ("Abraham Lincoln, First Inaugural Address (1861)", 'ws', "Abraham Lincoln's First Inaugural Address", None),
        ('Alexander H. Stephens, "Cornerstone" Speech (1861)', 'ws', 'Cornerstone Speech', None),
        ('Abraham Lincoln, Emancipation Proclamation (1863)', 'ws', 'Proclamation 95 (1863)', None),
        ('Abraham Lincoln, Gettysburg Address (1863)', 'ws', 'Gettysburg Address (Bliss copy)', None),
        ("Abraham Lincoln, Second Inaugural Address (1865)", 'ws', "Abraham Lincoln's Second Inaugural Address", None),
    ]),
    ('twentieth-century', 'Twentieth-Century Documents', 'Du Bois, Wilson, Roosevelt, Truman, Eisenhower, Johnson', '1903–1965', '', [
        ('W. E. B. Du Bois, "The Talented Tenth" (1903)', 'ws', 'The Talented Tenth', None),
        ('Woodrow Wilson, The Fourteen Points (1918)', 'ws', 'Fourteen Points Speech', None),
        ('Franklin D. Roosevelt, Executive Order 9066 (1942)', 'ws', 'Executive Order 9066', None),
        ('Harry S. Truman, Executive Order 9981 (1948)', 'ws', 'Executive Order 9981', None),
        ("Dwight D. Eisenhower, Farewell Address (1961)", 'ws', "Eisenhower's farewell address (press copy)", None),
        ('Lyndon B. Johnson, "We Shall Overcome" (1965)', 'ws', 'We Shall Overcome (Johnson)', None),
    ]),
    ('state-papers', 'State Papers of the Early Republic', 'Congress, Thomas Jefferson, James Madison', '1789–1800', '', [
        ('Amendments Proposed by Congress to the States (1789)', 'tcp', 'N17725', {'type': 'amendments'}),
        ('Kentucky Resolutions of 1799', 'ws', 'Kentucky Resolutions of 1799', None),
        ("Madison's Report on the Virginia Resolutions (1800)", 'ws', "Madison's Report on the Virginia Resolutions", None),
    ]),
]


FARRAND_DAY = r'^(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY),?\s+(?:MAY|JUNE|JULY|AUGUST|SEPTEMBER)\.?\s+[\w ]{1,4}?[,.]?\s*1\s?7\s?8\s?7\b'

ELLIOT_DAY = r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),?\s+(?:(?:January|February|March|April|May|June|July|August|September|October|November|December|J\w{1,3}/?\w?)\.?,?\s*)?[\dIilSoQ\^/AhtTHn]{1,5}(?:th|st|d)?[.,;]'
ELLIOT_HEADS = (r'^(?:[\w\[\]. ]{0,25}\]\s*)?(?:MASSACHUSETTS|CONNECTICUT|NEW\s+HAMPSHIRE|NEW\s+YORK|PENNSYLVANIA|MARYLAND|VIRGINIA|'
                r'NORTH\s+CAROLINA|SOUTH\s+CAROLINA|DEBATES|PROCEEDINGS|CONSTITUTIONAL\s+PRINCIPLES|OPINIONS)\.?(?:\s+[\w\[\]^.,"\'-]{1,14}){0,3}\s*$'
                r'|^\d+\s+[A-Z][A-Z .]+\.\s*\[')

# Kent's lectures in volume I and the page of the original edition each begins on (the scan misses most LECTURE headings)
KENT_LECTURES = [
    ('Lecture I: Of the Foundation and History of the Law of Nations', 1),
    ('Lecture II: Of the Rights and Duties of Nations in a State of Peace', 21),
    ('Lecture III: Of the Declaration and Early Measures of War', 47),
    ('Lecture IV: Of the Various Kinds of Property Liable to Capture', 73),
    ('Lecture V: Of the Rights of Belligerents', 89),
    ('Lecture VI: Of the Rights and Duties of Neutrals', 115),
    ('Lecture VII: Of Restrictions upon Neutral Trade', 135),
    ('Lecture VIII: Of Truces, Passports, and Treaties of Peace', 159),
    ('Lecture IX: Of Offences against the Law of Nations', 181),
    ('Lecture X: Of the History of the American Union', 201),
    ('Lecture XI: Of Congress', 221),
    ('Lecture XII: Of Judicial Constructions of the Powers of Congress', 243),
    ('Lecture XIII: Of the President', 271),
    ('Lecture XIV: Of the Judiciary Department', 291),
    ('Lecture XV: Of the Original and Appellate Jurisdiction of the Supreme Court', 313),
    ('Lecture XVI: Of the Jurisdiction of the Federal Courts, in Respect to the Common Law, and in Respect to Parties', 331),
    ('Lecture XVII: Of the District and Territorial Courts of the United States', 353),
    ('Lecture XVIII: Of the Concurrent Jurisdiction of the State Governments', 387),
    ('Lecture XIX: Of Constitutional Restrictions on the Powers of the States', 407),
    ('Lecture XX: Of Statute Law', 447),
    ('Lecture XXI: Of Reports of Judicial Decisions', 471),
    ('Lecture XXII: Of the Principal Publications of the Common Law', 499),
    ('Lecture XXIII: Of the Civil Law', 515),
]

ARCHIVE = [
    # id, title, author, year, Internet Archive identifiers (volumes in order), Corner source id, options (build_archive)
    ('farrand-1-2', 'The Records of the Federal Convention of 1787, Volumes I–II: The Daily Records', 'Max Farrand (ed.)',
     '1787 (pub. 1911)', ['recordsoffederal01unit', 'recordsoffederal02unit'], '',
     {'head_re': FARRAND_DAY, 'start_re': r'^(?:May 14|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b', 'stop_re': r'^(?:Index|Appendix)',
      'vol_opt': {1: {'head_re': FARRAND_DAY + r'|^In f\w{1,3}deral-Convention\.\s*$'}},
      'sub_re': r'^(?:JOURNAL|MADISON|YATES|KING|PATERSON|HAMILTON|PIERCE|McHENRY|MASON|LANSING|WILSON|BREARLEY|BREARLY|PINCKNEY|RANDOLPH|DETAIL OF AYES AND NOES|COMMITTEE OF DETAIL|COMMITTEE OF STYLE|[IVX]+\.)\s*$',
      'title_sub': [(r'^In f\w{1,3}deral-Convention\.\s*$', 'May 14–25, 1787'), (r'^(\w+),?\s+(\w+)\.?\s+([\w ]{1,4}?)[,.]?\s*1\s?7\s?8\s?7.*$', lambda m: f'{m.group(1)}, {m.group(2)} {ocr_num(m.group(3).replace(" ", ""))}, 1787')],
      'furniture_re': r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s+[A-Z][A-Za-z]+\s+(?:May|June|July|August|September)\s+[\w ]{1,4}\.?$|^(?:May|June|July|August|September)\s+[\dIil]{1,2}\.?$',
      'smart': True, 'merge_below': 20, 'min_words': 10}),
    ('elliot-debates', "The Debates in the Several State Conventions on the Adoption of the Federal Constitution (Elliot's Debates), Volumes II–IV",
     'Jonathan Elliot (ed.)', '1787–1788 (2d ed., 1836; 1888 printing)', ['debatesinseveral02elli', 'debatesinseveral03elli', 'debatesinseveral04elli'], '',
     {'head_re': ELLIOT_DAY, 'head_inline': True, 'merge_below': 40, 'vol_labels': ['', '', ''],
      'furniture_re': ELLIOT_HEADS,
      # dates the scanner misread, checked against the convention journals
      'rename': {'Friday, 11': 'Friday, January 11', 'Saturday, 12': 'Saturday, January 12', 'Saturday, Juli /': 'Saturday, July 19', 'Saturday, 5': 'Saturday, July 5', 'Thursday, 10': 'Thursday, July 10',
                 'Monday, November 2': 'Monday, November 26', 'Wednesday, October 2': 'Wednesday, November 28',
                 'Friday, June 16': 'Friday, June 6', 'Monday, June 14': 'Monday, June 16', 'Tuesday, June 15': 'Tuesday, June 17',
                 'Tuesday, Jult /': 'Tuesday, July 29'},
      'title_sub': [(r'^(\w+day),?\s+([A-Z][a-z]+)?\.?,?\s*([\w/^\\]{1,5})[.,;]?.*$',
                     lambda m: f'{m.group(1)}, {m.group(2) + " " if m.group(2) and m.group(2) not in ("A", "P") else ""}{(re.sub(r"[^0-9]", "", ocr_num(m.group(3))) or m.group(3))[:2]}')],
      'vol_opt': {
          1: {'start_re': r'^Massachusetts', 'groups': [
              (r'^COMMONWEALTH\s+OF\s+MASSACHUSETTS,', 'Massachusetts (January–February 1788)'),
              (r'^STATE\s+O[FP]\s+CONNECTICUT,', 'Connecticut (January 1788)'),
              (r'^NEW\s+HAMPSHIRE\s+CONVENTION\.', 'New Hampshire (February–June 1788)'),
              (r'^THE\s+STATE\s+OF\s+NEW\s+YORK,', 'New York (June–July 1788)'),
              (r'^STATE\s+OF\s+PENNSYLVANIA,', 'Pennsylvania (November–December 1787)'),
              (r'^THE\s+MARYLAND\s+CONVENTION', 'Maryland (April 1788)')]},
          2: {'start_re': r'^Virginia', 'groups': [(r'^COMMONWEALTH\s+OF\s+VIRGINIA,', 'Virginia (June 1788)')]},
          3: {'start_re': r'^North Carolina', 'stop_re': r'^Stop', 'groups': [
              (r'^STATE\s+OF\s+NORTH\s+CAROLINA,', 'North Carolina (July–August 1788)'),
              (r'^STATE\s+O[EF]\s+SOUTH\s+CAROLINA,', 'South Carolina (January and May 1788)'),
              (r'^SELECTED\s+FROM\s+DEBATES\s+IN\s+CONGRESS', 'Debates in Congress on Constitutional Principles, 1789–1836'),
              (r'^PRONOUNCING\s+THE\s+ALIEN', 'The Virginia and Kentucky Resolutions and the Replies of the States, 1798–1800'),
              (r'^THE\s+TARIFF\.\s+SOUTH\s+CAROLINA', 'Nullification and the Tariff, 1828–1833'),
              (r'^MADISON\s+ON\s+THE\s+TARIFF', 'Madison on the Tariff and the Bank; Hamilton on the Bank'),
              (r'^LIST\s+OF\s+THE\s+VETOES', 'Stop')]}}}),
    ('kent-commentaries-1', 'Commentaries on American Law, Volume I: The Law of Nations, the Government and Constitutional Jurisprudence of the United States, and the Sources of Municipal Law',
     'James Kent', '1826 (rev. ed., 1889)', ['commentariesonam01kentuoft'], 'kent',
     {'start_re': r'^Lecture I\b', 'star_splits': KENT_LECTURES, 'merge_below': 0,
      'strip_re': [r'\s*\[\s*\*\s*\d+\s*\]', r'\s?\((?:[a-z]{1,2}|\d)\)(?=[\s.,;:]|$)', r'^\*\s*'],
      'furniture_re': r'^\S{1,6}\.?\s+[\w.]{1,6}\]\s+[A-Z]|^\d+\s+[A-Z ,.]+\[\s*(?:PART|LECT)',
      'note_re': r'^(?:\([a-z]{1,2}\)|\(\d\)|[*"^]+\s*[A-Z]|\d{1,3}\s+[A-Z])'}),
]



def ocr_num(s):
    # a date the scanner misread: "i" -> 1, "n" -> 11, "io" -> 10
    return s.translate(str.maketrans({'i': '1', 'l': '1', 'I': '1', 'o': '0', 'O': '0', 'n': '11', 'z': '2', 'S': '5'})).replace('1111', '11')


def api(**p):
    p.update(format='json', formatversion=2)
    url = 'https://en.wikisource.org/w/api.php?' + urllib.parse.urlencode(p)
    for a in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90))
            time.sleep(2)
            return r
        except Exception as e:
            if getattr(e, 'code', 0) in (429, 503):
                time.sleep(20 * (a + 1))
                continue
            raise
    raise RuntimeError('Wikisource unavailable')


def page_html(bid, title):
    os.makedirs(f'{RAW}/{bid}', exist_ok=True)
    p = f"{RAW}/{bid}/{re.sub(r'[^A-Za-z0-9]+', '_', title)[-150:]}.html"
    if not os.path.exists(p):
        r = api(action='parse', page=title, prop='text', disableeditsection=1, redirects=1)
        open(p, 'w', encoding='utf-8').write(r.get('parse', {}).get('text', ''))
    return open(p, encoding='utf-8').read()


def toc(bid, root, prefix=None):
    """Chapter pages linked from the root page, in the order they appear; book-level pages are expanded the same way."""
    out, seen = [], set()

    def walk(title, depth):
        h = page_html(bid, title)
        for m in re.finditer(r'<a href="/wiki/([^"#?]+)"[^>]*>', h):
            t = urllib.parse.unquote(m.group(1)).replace('_', ' ')
            if not t.startswith(prefix or root + '/') or t in seen or re.search(r'/(Index|Contents|Table of Contents)$', t):
                continue
            seen.add(t)
            sub = page_html(bid, t)
            # a "Book I" page that is only a list of its chapters: follow it instead of keeping it
            kids = sum(1 for k in re.finditer(r'<a href="/wiki/([^"#?]+)"', sub) if urllib.parse.unquote(k.group(1)).replace('_', ' ').startswith(t + '/'))
            if depth < 2 and kids >= 2 and len(text_blocks(sub)) < 12:
                walk(t, depth + 1)
            else:
                out.append(t)
    walk(root, 0)
    return out


DROP = re.compile(r'<(?:sup class="reference|span class="mw-editsection|div class="(?:wst-header|ws-header|ws-noexport|licenseContainer|wst-license|mw-references|navbox))[^>]*>.*?</(?:sup|span|div)>', re.S)


def clean(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def text_blocks(h):
    h = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', h, flags=re.S)
    h = re.sub(r'<table[^>]*>.*?</table>', '', h, flags=re.S)
    h = drop_elements(h, 'div', 'wst-header|ws-header|ws-noexport|licenseContainer|wst-license|reflist|references')
    h = re.sub(r'<br\s*/?>\s*<br\s*/?>', '</p><p>', h)      # paragraphs separated only by blank lines
    # a block quotation holding paragraphs is read as those paragraphs (not as one block running to its end)
    h = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', lambda m: m.group(1) if '<p' in m.group(1) else m.group(0), h, flags=re.S)
    h = re.sub(r'<sup[^>]*class="[^"]*reference[^"]*"[^>]*>.*?</sup>', '', h, flags=re.S)
    h = re.sub(r'<span[^>]*class="[^"]*(?:pagenum|ws-pagenum|mw-editsection)[^"]*"[^>]*>.*?</span>', '', h, flags=re.S)
    h = re.sub(r'<ol class="references">.*?</ol>', '', h, flags=re.S)
    out = []
    for m in re.finditer(r'<(h[2-5]|p|blockquote)[^>]*>(.*?)</\1>', h, re.S):
        t = clean(m.group(2))
        if not t or re.fullmatch(r'[\W\d]{0,4}', t):
            continue
        if re.fullmatch(r'Layout \d+', t):
            continue
        letters = [c for c in t if c.isalpha()]
        caps = letters and sum(c.isupper() for c in letters) > 0.85 * len(letters) and len(t) <= 120
        out.append(['h' if m.group(1).startswith('h') or caps else 'p', t])
    # the short title lines that open a chapter ("Book the first.", "Chapter the first.", "Of the Rights of Persons.")
    for x in out:
        if len(x[1]) > 140:
            break
        if len(x[1]) <= 90:
            x[0] = 'h'
    return out


def smart_title(s):
    small = {'a', 'an', 'the', 'of', 'and', 'or', 'in', 'on', 'to', 'for', 'by', 'at', 'as', 'with', 'from'}
    w = s.lower().rstrip('.').split()
    roman = re.compile(r'^(?=[ivxlc]+\W*$)(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})\W*$')

    def cap(x):      # first letter, letters after a hyphen and initials: "Hayes-Tilden", "B.K. Bruce", '"Negro'
        return x if re.match(r'^\d', x) else re.sub(r'^([^a-z]*)([a-z])|(?<=[-.])([a-z])', lambda m: (m.group(1) or '') + (m.group(2) or m.group(3)).upper(), x)
    out = []
    for i, x in enumerate(w):
        after_break = i and re.search(r'[:.!?—]$', w[i - 1]) and ((roman.match(w[i - 1]) and x not in ('and', 'or', 'to')) or not re.fullmatch(r'(?:[a-z]\.)+|mr\.|st\.|no\.|vol\.', w[i - 1]))
        out.append(x.upper() if roman.match(x) else x if i and x in small and not after_break and not x.startswith('(') else cap(x))
    return ' '.join(out)


TOC_LINE = re.compile(r"^(Book|Chapter|Chap|Letter|Part|Section|Query|Article|Number|No\.|[IVXLC]+\.)\b", re.I)


def drop_apparatus(blocks):
    """Remove what a modern editor or transcriber added: transcriber's notes, a printed table of contents, and the
    printer's "End of this Book" / "End of the First Volume" lines."""
    out, i = [], 0
    while i < len(blocks):
        kind, t = blocks[i]
        if re.match(r"^Transcriber.?s? notes?\b", t, re.I):
            i += 1
            while i < len(blocks) and blocks[i][0] != 'h':
                i += 1
            continue
        if re.fullmatch(r"(?:TABLE OF )?CONTENTS\.?", t.strip(), re.I) and i + 1 < len(blocks) and TOC_LINE.match(blocks[i + 1][1]):
            i += 1
            while i < len(blocks) and TOC_LINE.match(blocks[i][1]) and len(blocks[i][1]) < 220:
                i += 1
            continue
        t = re.sub(r"\s*End of (?:this|the \w+) (?:Book|Volume)\.?\s*$", "", t)
        if t:
            out.append([kind, t])
        i += 1
    return out


def write_book(meta, parts):
    """parts: [(name, blocks)]; writes the per-part files and the book file, returns the index entry."""
    bid = meta['id']
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if re.fullmatch(re.escape(bid) + r'(-\d+)?\.js', f):
            os.remove(os.path.join(OUT, f))
    tocout, words = [], 0
    for n, (name, b0) in enumerate(parts, 1):
        b0 = drop_apparatus(b0)
        b = []
        for kind, t in b0:
            t = t.replace('ſ', 's')            # the long s of 18th-century printing
            # a paragraph cut by a page break (it goes on in lower case after one that doesn't end a sentence)
            if b and kind == 'p' and b[-1][0] == 'p' and re.match(r'^[a-z]', t) and not re.search(r'[.!?:"”’)\]]$', b[-1][1]):
                b[-1][1] += ' ' + t
                continue
            b.append([kind, t])
        w = sum(len(x[1].split()) for x in b)
        words += w
        tocout.append([name, w])
        open(f'{OUT}/{bid}-{n}.js', 'w', encoding='utf-8').write('window.LIB_CHS=window.LIB_CHS||{};window.LIB_CHS[' + json.dumps(f'{bid}-{n}') + ']=' + json.dumps({'id': bid, 'n': n, 't': name, 'b': b}, ensure_ascii=False, separators=(',', ':')) + ';')
    meta = dict(meta, toc=tocout)
    open(f'{OUT}/{bid}.js', 'w', encoding='utf-8').write('window.LIB_BOOKS=window.LIB_BOOKS||{};window.LIB_BOOKS[' + json.dumps(bid) + ']=' + json.dumps(meta, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f'{bid}: {len(parts)} parts, {words:,} words', flush=True)
    return {'id': bid, 'title': meta['title'], 'author': meta['author'], 'year': meta['year'], 'corner': meta['corner'],
            'chapters': len(parts), 'words': words, 'srcName': meta['srcName']}


APPENDIX_NAMES = {'farrand-3': {
    'Appendix B': 'Appendix B: The Delegates, Their Credentials and Attendance',
    'Appendix C': 'Appendix C: The Virginia Plan (Randolph Resolutions)',
    'Appendix D': 'Appendix D: The Pinckney Plan',
    'Appendix E': 'Appendix E: The New Jersey Plan',
    'Appendix F': "Appendix F: Hamilton's Plan",
}}
# works whose short pages are real documents (a two-line letter), not navigation pages
SHORT_PAGES_OK = {'farrand-3'}


def build(bid, title, author, year, root, corner, prefix=None):
    chapters = toc(bid, root, prefix) or [root]
    # appendices in letter order (the root page can link them out of order), source order within each
    order = {t: i for i, t in enumerate(chapters)}
    chapters.sort(key=lambda t: ((re.search(r'/Appendix ([A-Z])\b', t) or re.search(r'$', '')).group(0), order[t]))
    parts = []
    for t in chapters:
        b = text_blocks(page_html(bid, t))
        if sum(len(x[1].split()) for x in b) < (20 if bid in SHORT_PAGES_OK else 150):
            continue
        name = t[len(root) + 1:] if t.startswith(root + '/') else t[len(prefix) - 4:] if prefix and t.startswith(prefix) else title
        name = name.replace('/', ' · ')
        if re.search(r'Chapter \d+$', name):          # "Book 3 · Chapter 8" -> "Book 3 · Chapter 8: The Legislature"
            hs = [x[1] for x in b[:6] if x[0] == 'h']
            k = next((i for i, h in enumerate(hs) if re.match(r'^CHAPTER\b', h, re.I)), None)
            if k is not None and k + 1 < len(hs) and not re.match(r'^(CHAPTER|BOOK)\b', hs[k + 1], re.I):
                name += ': ' + smart_title(hs[k + 1])
        if re.search(r'· [IVXLC]+$', name):          # "Appendix A · CLVII" -> "Appendix A · CLVII: Gerry to ..."
            first = next((x[1] for x in b if x[0] == 'h' and not re.fullmatch(r'[IVXLCⅠ-ↈ]+[a-z]?\.?', x[1].strip())), '')
            first = re.sub(r'^[IVXLCⅠ-ↈ]+[a-z]?\.\s*', '', first)      # "IX. James Madison to ..." -> "James Madison to ..."
            if first:
                name += ': ' + (first if len(first) <= 90 else first[:88].rsplit(' ', 1)[0] + '…')
        name = APPENDIX_NAMES.get(bid, {}).get(name, name)
        parts.append((name, b))
    src = 'https://en.wikisource.org/wiki/' + urllib.parse.quote(root.replace(' ', '_'))
    return write_book({'id': bid, 'title': title, 'author': author, 'year': year, 'src': src, 'srcName': 'Wikisource',
                       'license': 'Public-domain text; Wikisource transcription, CC BY-SA 4.0', 'corner': corner}, parts)


# ---------------------------------------------------------------------------------------------- Project Gutenberg
MIRRORS = ['https://www.gutenberg.org/cache/epub/{n}/pg{n}-images.html',
           'http://mirrors.xmission.com/gutenberg/{p}/{n}/{n}-h/{n}-h.htm',
           'https://gutenberg.pglaf.org/{p}/{n}/{n}-h/{n}-h.htm']


def gutenberg_html(n):
    os.makedirs(f'{RAW}/gutenberg', exist_ok=True)
    path = f'{RAW}/gutenberg/{n}.html'
    if not os.path.exists(path):
        s = str(n)
        p = '/'.join(s[:-1]) if len(s) > 1 else '0'
        for m in MIRRORS:
            try:
                data = urllib.request.urlopen(urllib.request.Request(m.format(n=n, p=p), headers=UA), timeout=120).read()
                if b'START OF TH' in data:
                    open(path, 'wb').write(data)
                    break
            except Exception as e:
                print(f'  {n}: {m.split("/")[2]}: {e}', flush=True)
            time.sleep(2)
        else:
            data = gutenberg_txt_html(n)      # some older eBooks exist only as plain text on the mirrors
            if not data:
                raise RuntimeError(f'eBook {n}: no copy found')
            open(path, 'wb').write(data)
    raw = open(path, 'rb').read()
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000])
    enc = (m.group(1).decode() if m else 'utf-8').lower()
    try:
        return raw.decode(enc)
    except (LookupError, UnicodeDecodeError):
        return raw.decode('cp1252', errors='replace')


def drop_elements(h, tag, cls):
    """Remove every <tag class="...cls..."> element with its contents (nesting-aware)."""
    opener = re.compile(r'<%s\b[^>]*class=["\'][^"\']*\b(?:%s)\b[^"\']*["\'][^>]*>' % (tag, cls), re.I)
    tok = re.compile(r'<(/?)%s\b[^>]*>' % tag, re.I)
    while True:
        m = opener.search(h)
        if not m:
            return h
        depth, i = 1, m.end()
        while depth:
            t = tok.search(h, i)
            if not t:
                i = len(h)
                break
            depth += -1 if t.group(1) else 1
            i = t.end()
        h = h[:m.start()] + h[i:]


def gutenberg_blocks(h):
    a = re.search(r'\*\*\* ?START OF TH[^*]*\*\*\*', h)
    z = re.search(r'\*\*\* ?END OF TH[^*]*\*\*\*', h)
    h = h[a.end() if a else 0: z.start() if z else len(h)]
    h = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', h, flags=re.S | re.I)
    h = re.sub(r'<table[^>]*>.*?</table>', '', h, flags=re.S | re.I)
    for tag in ('div', 'p', 'span'):
        h = drop_elements(h, tag, 'footnotes?|pagenum|pageno|tei-pb|toc|transnote|tnotes?|figcenter|caption|blockquot-toc')
    h = re.sub(r'<a\b[^>]*(?:fnanchor|#Footnote|#FN|#fn|#note_)[^>]*>.*?</a>', '', h, flags=re.S | re.I)
    h = re.sub(r'<br\s*/?>', ' ', h, flags=re.I)
    out = []
    for m in re.finditer(r'<(h[1-4]|p)\b[^>]*>(.*?)</\1>', h, re.S | re.I):
        t = clean(m.group(2)).replace('\xad', '').replace('​', '')
        t = re.sub(r'\s*\[(?:Footnote:? ?)?(?:\d+|[a-z])\]', '', t).strip()
        t = re.sub(r'\s*\[Footnote \w{1,3}: [^\]]*\]', '', t).strip()      # a footnote printed inline: [Footnote s: ...]
        if not t or re.fullmatch(r'[\W\d]{0,4}', t):
            continue
        if re.match(r'^(?:E-text prepared by|Produced by)\b', t):      # the transcribers' credit line
            continue
        if re.match(r'^The Project Gutenberg e-?Book,? ', t, re.I):      # the eBook's own title line
            continue
        out.append([m.group(1).lower(), t])
    return out


SKIP_PART = re.compile(r'^(contents|table of contents|list of|index|footnotes?|notes?|illustrations|transcriber|errata|advertisements?|bibliography|reference list)\b', re.I)


def part_title(t, opt):
    t = re.sub(r'\s*[—–-]+\s*$', '', t).strip()
    for pat, rep in opt.get('title_sub', []):
        t = re.sub(pat, rep, t)
    if opt.get('title_re'):
        m = re.match(opt['title_re'], t)
        if m:
            return m.group(1)
    if opt.get('invert_name'):          # "Gerry, Elbridge. Observations ..." -> "Elbridge Gerry, Observations ..."
        t = re.sub(r'^([A-Z][\w’\']+), ([A-Z][\w. ]+?)\. ', r'\2 \1, ', t)
    letters = [c for c in t if c.isalpha()]
    if opt.get('smart') or (letters and sum(c.isupper() for c in letters) > 0.85 * len(letters)):
        t = smart_title(t)
    t = t.rstrip('.,;: ')
    t = opt.get('rename', {}).get(t, t)
    if len(t) > 80:
        t = t[:78].rsplit(' ', 1)[0] + '…'
    return t


def split_long(parts):
    """A very long division (Oceana's "Model", 72,000 words) is read in pieces of about 12,000 words, cut at a heading
    where there is one nearby, otherwise between paragraphs."""
    split = []
    for n, b in parts:
        w = sum(len(x[1].split()) for x in b)
        if w <= 20000:
            split.append((n, b))
            continue
        k = -(-w // 12000)
        target, pieces, cur, cw = w / k, [], [], 0
        for x in b:
            xw = len(x[1].split())
            if cur and cw >= target * (0.8 if x[0] == 'h' else 1.0) and len(pieces) < k - 1:
                pieces.append(cur)
                cur, cw = [], 0
            cur.append(x)
            cw += xw
        pieces.append(cur)
        split.extend((f'{n} ({i} of {len(pieces)})', pc) for i, pc in enumerate(pieces, 1))
    return split


def sub_title(name, b):
    """'Chapter IV' -> 'Chapter IV: Origin and Necessity of the Power to Regulate Commerce', from the short lines under
    the heading (a date line becomes a parenthesis: 'Chapter I: Organization of the First Continental Congress (1774-1775)')."""
    if not re.fullmatch(r"(?:.* · )?(?:Chapter|Book|Part|Section|Letter|Number|No\.)\s+[IVXLC\d]+", name, re.I):
        return name
    nxt = [x[1] for x in b[1:3] if len(x[1]) <= 400 or '....' in x[1][:400]]
    date = ''
    if nxt and len(nxt[0]) <= 40 and re.match(r'(?:\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,? ?\d)', nxt[0]):
        date, nxt = nxt[0].rstrip('.'), nxt[1:]
    sub = re.split(r'\.\s*[—–-]|\.{3,}|\.$', nxt[0])[0].strip() if nxt else ''
    if nxt and '....' in nxt[0] and sub:      # a chapter's printed summary ("Greene invests Camden.... Battle of ..."): its first item
        sub += '…'
    elif not sub or len(sub) > 120 or (b[1][0] == 'p' and len(nxt[0]) > 200 and not date):
        return name + (f' ({date})' if date else '')
    else:      # the opening sentence of the text is not a subtitle: a subtitle capitalizes most of its longer words
        long_words = [x for x in sub.split() if len(x) > 3]
        if long_words and sum(x[0].isupper() for x in long_words) < 0.35 * len(long_words):
            return name + (f' ({date})' if date else '')
    letters = [c for c in sub if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > 0.85 * len(letters):
        sub = smart_title(sub)
    return f'{name}: {sub}' + (f' ({date})' if date else '')


def build_gutenberg(bid, title, author, year, nums, corner, opt):
    """opt: title_re (part title = its first group), smart (title-case every part title), invert_name, rename
    ({part title: new title}), nosplit_re (split-level headings that stay inside the part: "Mr. Lincoln's Rejoinder"),
    drop_re (sub-headings dropped with what follows them up to the next heading of the same or a higher level: an
    editor's notes), skip_re (more part titles to leave out), drop_front (leave out what precedes the first part),
    vol_labels (part-title prefix for each eBook instead of "Vol. I · "; '' for none), split (the heading level to split
    at, instead of the highest one used three times), head_re (paragraphs that open a part, as if they were headings:
    an eBook without headings), title_sub ([(regex, replacement)] applied to part titles first), stop_re (the part whose
    title matches and everything after it in that eBook are left out), keep_re (only parts whose title matches are
    kept), book_re (part titles that name a book: they prefix the parts that follow, "Book II · Chapter III"), sub_title
    (a bare "Chapter IV" takes the subtitle printed under it), resplit ({part-title regex: heading level}: such a part
    is split again at that level, "Magna Carta · Chapter Thirty-Nine"), head_text (a head_re paragraph is shown as its part
    title: an editor's label such as "State of the Union Address George Washington ..."), vol_opt ({volume number: options for that eBook only})."""
    parts = []
    for v, num in enumerate(nums, 1):
        vo = dict(opt, **opt.get('vol_opt', {}).get(v, {}))
        nosplit = re.compile(vo['nosplit_re'], re.I) if vo.get('nosplit_re') else None
        drop = re.compile(vo['drop_re'], re.I) if vo.get('drop_re') else None
        skip = re.compile(vo['skip_re'], re.I) if vo.get('skip_re') else None
        heads = re.compile(vo['head_re']) if vo.get('head_re') else None
        blocks = gutenberg_blocks(gutenberg_html(num))
        levels = [x[0] for x in blocks if x[0] != 'p' and not (nosplit and nosplit.match(x[1]))]
        # split at the highest heading level used at least three times (h1 is usually only the title page)
        split = vo.get('split') or next((l for l in ('h1', 'h2', 'h3', 'h4') if levels.count(l) >= 3), None)
        if heads:
            blocks = [[split, part_title(t, vo) if vo.get('head_text') else t] if k == 'p' and heads.match(t) else [k, t] for k, t in blocks]
        cur, name, vparts, dropping = [], 'Front matter', [], None
        for kind, t in blocks:
            if dropping and kind != 'p' and kind <= dropping:
                dropping = None
            if dropping:
                continue
            if drop and kind != 'p' and kind != split and drop.match(t):
                dropping = kind
                continue
            if kind == split and not (nosplit and nosplit.match(t)):
                vparts.append((name, cur))
                cur, name = [], part_title(t, vo)
                cur.append(['h', t])
            else:
                cur.append([kind, t])      # heading levels kept until the part is written (resplit reads them)
        vparts.append((name, cur))
        if vo.get('drop_front') and vparts and vparts[0][0] == 'Front matter':
            vparts = vparts[1:]
        if vo.get('start_re'):      # begin at the (last, with start_last: past a table of contents) part whose title matches
            ks = [i for i, (n, _) in enumerate(vparts) if re.match(vo['start_re'], n, re.I)] or [0]
            k0 = ks[-1] if vo.get('start_last') else ks[0]
            if vo.get('toc_titles'):      # chapter titles from the summaries printed in the table of contents
                toc = {}
                for n, b in vparts[:k0]:
                    if re.fullmatch(r'Chapter [IVXLC]+', n) and len(b) > 1:
                        first = re.split(r'\.\s*--|\.\s*—', b[1][1])[0].strip().rstrip('.')
                        toc[n] = f'{n}: {smart_title(first)}' if len(first) < 110 else n
                vparts = [(toc.get(n, n), b) for n, b in vparts]
            vparts = vparts[k0:]
        if vo.get('stop_re'):
            k = next((i for i, (n, _) in enumerate(vparts) if re.match(vo['stop_re'], n, re.I)), None)
            vparts = vparts[:k] if k is not None else vparts
        if vo.get('keep_re'):
            vparts = [(n, b) for n, b in vparts if re.match(vo['keep_re'], n, re.I)]
        for pat, lvl in vo.get('resplit', {}).items():      # a very long part read in its own sections
            out = []
            for n, b in vparts:
                if not re.match(pat, n, re.I):
                    out.append((n, b))
                    continue
                cur, cn = [], n
                for x in b:
                    if x[0] == lvl and cur:
                        out.append((cn, cur))
                        cur, cn = [], f'{n} · {part_title(x[1], vo)}'
                    cur.append(x)
                out.append((cn, cur))
            vparts = out
        if vo.get('sub_title'):
            vparts = [(sub_title(n, b), b) for n, b in vparts]
        bookre = re.compile(vo['book_re'], re.I) if vo.get('book_re') else None
        if bookre:
            book, named = '', []
            for n, b in vparts:
                if bookre.match(n):
                    book = bookre.match(n).group(0)
                elif book and not SKIP_PART.match(n) and not (skip and skip.match(n)):
                    n = f'{book} · {n}'
                named.append((n, b))
            vparts = named
        merged = []
        for name, b in vparts:
            w = sum(len(x[1].split()) for x in b)
            if SKIP_PART.match(name) or (skip and skip.match(name)) or not b:
                continue
            # a part that is only headings or a few lines (a "Book I" divider, a half-title) joins the next one
            if merged and merged[-1][2] < 120:
                pn, pb, pw = merged.pop()
                keep_prev = pn != 'Front matter' and not (bookre and bookre.match(pn))
                name, b, w = (pn if keep_prev else name), pb + b, pw + w
            merged.append((name, b, w))
        if merged and merged[-1][2] < 120 and len(merged) > 1:
            pn, pb, pw = merged.pop()
            merged[-1] = (merged[-1][0], merged[-1][1] + pb, merged[-1][2] + pw)
        if opt.get('vol_labels'):
            prefix = opt['vol_labels'][v - 1] + ' · ' if opt['vol_labels'][v - 1] else ''
        else:
            prefix = f'Vol. {["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][v - 1]} · ' if len(nums) > 1 else ''
        for name, b, w in merged:
            if w < 60:
                continue
            parts.append((prefix + name, [['p' if k == 'p' else 'h', t] for k, t in b]))
    if len(parts) == 1 and parts[0][0] == 'Front matter':      # a single essay or speech: the part is the work
        parts = [(title, parts[0][1])]
    parts = split_long(parts)
    src = f'https://www.gutenberg.org/ebooks/{nums[0]}'
    lic = 'Public-domain text from Project Gutenberg (eBook' + ('s ' if len(nums) > 1 else ' ') + ', '.join(f'#{n}' for n in nums) + ')'
    return write_book({'id': bid, 'title': title, 'author': author, 'year': year, 'src': src, 'srcName': 'Project Gutenberg',
                       'license': lic, 'corner': corner}, parts)


# ---------------------------------------------------------------------------------------------- Evans-TCP (CC0)
TEI = '{http://www.tei-c.org/ns/1.0}'


def tcp_xml(n):
    import xml.etree.ElementTree as ET
    os.makedirs(f'{RAW}/tcp', exist_ok=True)
    path = f'{RAW}/tcp/{n}.xml'
    if not os.path.exists(path):
        data = urllib.request.urlopen(urllib.request.Request(f'https://raw.githubusercontent.com/textcreationpartnership/{n}/master/{n}.xml', headers=UA), timeout=120).read()
        if b'publicdomain/zero' not in data:
            raise RuntimeError(f'{n}: not marked CC0')
        open(path, 'wb').write(data)
        time.sleep(1)
    return ET.parse(path).getroot()


def tcp_text(el):
    """An element's text: notes and page breaks dropped, end-of-line hyphens joined, illegible letters shown as ◊."""
    out = [el.text or '']
    for c in el:
        tag = c.tag.replace(TEI, '')
        if tag in ('note', 'pb', 'figure'):
            pass
        elif tag == 'g' and (c.get('ref') or '').startswith('char:EOL'):
            pass
        elif tag == 'gap':
            m = re.match(r'(\d+) letters?', c.get('extent') or '')
            out.append('◊' * int(m.group(1)) if m else '◊◊◊')
        else:
            out.append(tcp_text(c))
        out.append(c.tail or '')
    return ''.join(out)


def tcp_blocks(div):
    blocks = []
    for c in div:
        tag = c.tag.replace(TEI, '')
        if tag in ('note', 'pb', 'figure', 'table'):
            continue
        if tag == 'div':
            blocks.extend(tcp_blocks(c))
        elif tag in ('opener', 'closer', 'list', 'lg', 'sp'):
            for k in c:
                t = re.sub(r'\s+', ' ', tcp_text(k)).strip()
                if t:
                    blocks.append(['p', t])
        else:
            t = re.sub(r'\s+', ' ', tcp_text(c)).strip()
            if t:
                blocks.append(['h' if tag == 'head' else 'p', t])
    return blocks


def tcp_divs(n, sel):
    body = tcp_xml(n).find(f'.//{TEI}text/{TEI}body')
    roots = [body]
    if sel.get('within'):
        w = sel['within']
        roots = [d for d in body.iter(f'{TEI}div') if d.get('type') == w.get('type') and (not w.get('n') or d.get('n') == w['n'])]
    out = []
    for d in (x for r in roots for x in r.iter(f'{TEI}div')):
        if sel.get('type') and d.get('type') != sel['type']:
            continue
        h = d.find(f'{TEI}head')
        head = re.sub(r'\s+', ' ', tcp_text(h)).strip() if h is not None else ''
        if sel.get('head') and not re.search(sel['head'], head):
            continue
        out.append((head, d))
    return out


def tidy_head(h):
    """'CHAP. III. Of  Adams  Title to Sovereignty' -> 'Chapter III: Of Adams Title to Sovereignty'"""
    h = re.sub(r'\s+', ' ', h).strip().rstrip('.')
    h = re.sub(r'^(?:CHAP|Chap)\.?\s*([IVXLC]+)\.?\s*', r'Chapter \1: ', h)
    h = re.sub(r'^(?:SECTION|SECT|Sect)\.?\s*([IVXLC]+)\.?\s*', r'Section \1: ', h)
    h = re.sub(r'^(Chapter|Section) ([IVXLC]+): (?:INTRODUCTION)?$', r'\1 \2', h)
    if re.sub(r'[^A-Za-z]', '', h).isupper() or len(re.findall(r'\b[A-Z]{2,}\b', h)) >= 2:
        h = smart_title(h)
    return h.rstrip(': ')


def build_collection(bid, title, author, year, corner, items):
    parts, srcs = [], []
    for fmt, src, ref, sel in items:
        if src == 'tcp':
            for head, d in tcp_divs(ref, sel):
                m = re.search(r'\b(?:NUMBER|LETTER|No\.)\s*([IVXL]+)\b', head, re.I)
                parts.append((fmt.format(num=m.group(1).upper() if m else '', head=tidy_head(head)), tcp_blocks(d)))
            srcs.append(f"{ {'A': 'EEBO-TCP', 'B': 'EEBO-TCP', 'K': 'ECCO-TCP'}.get(ref[0], 'Evans-TCP')} {ref}")
        else:
            h = page_html(bid, ref)
            b = text_blocks(h)
            if sum(len(x[1].split()) for x in b) < 150:      # some documents are laid out in a table
                b = text_blocks(re.sub(r'<(/?)li\b', r'<\1p', re.sub(r'</?(?:table|tbody|thead|tr|td|th)\b[^>]*>', '', h)))
            # Wikisource's own notes and references at the end of a document
            k = next((i for i, x in enumerate(b) if x[0] == 'h' and re.fullmatch(r'(?:Notes|References|See also|External links|Sources)', x[1].strip()) and i > len(b) * 0.5), None)
            if k is not None:
                b = b[:k]
            if sum(len(x[1].split()) for x in b) >= 150:
                parts.append((fmt, b))
                srcs.append(f'Wikisource ({ref})')
    parts = [(n, b) for n, b in parts if sum(len(x[1].split()) for x in b) >= 60]
    parts = split_long(parts)
    names = ' and '.join(dict.fromkeys([s.split(' ')[0] + ' (CC0)' if '-TCP' in s else 'Wikisource (CC BY-SA 4.0)' for s in srcs]))
    meta = {'id': bid, 'title': title, 'author': author, 'year': year, 'corner': corner,
            'src': 'https://textcreationpartnership.org/tcp-texts/evans-tcp-evans-early-american-imprints/' if 'TCP' in names else 'https://en.wikisource.org/',
            'srcName': 'Text Creation Partnership' if 'TCP' in names else 'Wikisource',
            'license': f'Public-domain texts; transcriptions from {names}: ' + '; '.join(dict.fromkeys(srcs)) + '. Letters the transcribers could not read are shown as ◊'}
    entry = write_book(meta, parts)
    return entry



# ---------------------------------------------------------------------------------------------- plain-text Gutenberg
TXT_MIRRORS = ['https://gutenberg.pglaf.org/{p}/{n}/{n}-0.txt', 'https://gutenberg.pglaf.org/{p}/{n}/{n}.txt',
               'https://gutenberg.pglaf.org/{p}/{n}/{n}-8.txt', 'http://mirrors.xmission.com/gutenberg/{p}/{n}/{n}.txt']


def gutenberg_txt_html(n):
    """An eBook that Project Gutenberg has only as plain text: fetched once and turned into simple HTML (a paragraph per
    blank-line-separated block; a short line in capitals on its own is a heading), so gutenberg_html can read it."""
    s = str(n)
    p = '/'.join(s[:-1]) if len(s) > 1 else '0'
    for m in TXT_MIRRORS:
        try:
            data = urllib.request.urlopen(urllib.request.Request(m.format(n=n, p=p), headers=UA), timeout=120).read()
        except Exception as e:
            print(f'  {n}: {m}: {e}', flush=True)
            time.sleep(2)
            continue
        if b'START OF TH' not in data:
            continue
        txt = data.decode('utf-8') if m.endswith('-0.txt') else data.decode('latin-1')
        txt = txt.replace('\r\n', '\n')
        out = ['<html><head><meta charset="utf-8"></head><body>']
        for blk in re.split(r'\n\s*\n', txt):
            lines = [x.strip() for x in blk.strip().split('\n') if x.strip()]
            if not lines:
                continue
            t = html.escape(' '.join(lines))
            letters = [c for c in t if c.isalpha()]
            if len(lines) <= 2 and len(t) <= 90 and letters and sum(c.isupper() for c in letters) > 0.85 * len(letters) and not t.startswith('***'):
                out.append(f'<h2>{t}</h2>')
            else:
                out.append(f'<p>{t}</p>')
        out.append('</body></html>')
        return '\n'.join(out).encode('utf-8')
    return None


# ---------------------------------------------------------------------------------------------- the Avalon Project
LONG_S_VOCAB = None


def long_s_vocab():
    """Word counts from the library's modern-spelled texts, used to undo the long s printed as f ("poffeffion")."""
    global LONG_S_VOCAB
    if LONG_S_VOCAB is None:
        from collections import Counter
        c = Counter()
        for bid in ('story', 'tocqueville', 'madison', 'ford-essays', 'ford-pamphlets', 'curtis-history', 'hallam-constitutional',
                    'mckechnie-magna-carta', 'marshall-washington', 'webster-speeches', 'lincoln-douglas', 'cato', 'spirit-of-laws'):
            for f in os.listdir(OUT):
                if re.fullmatch(re.escape(bid) + r'-\d+\.js', f):
                    c.update(re.findall(r'[a-z]+', open(os.path.join(OUT, f), encoding='utf-8').read().lower()))
        LONG_S_VOCAB = c
    return LONG_S_VOCAB


def fix_long_s(text):
    v = long_s_vocab()

    def fix(m):
        w = m.group(0)
        low = w.lower()
        pos = [i for i, ch in enumerate(w[:-1]) if ch == 'f']      # a long s never ends a word, and is never a capital
        if not pos or len(pos) > 6:
            return w
        best, best_n = w, v.get(low, 0)
        for mask in range(1, 1 << len(pos)):
            cand = list(w)
            for k, i in enumerate(pos):
                if mask >> k & 1:
                    cand[i] = 's'
            cand = ''.join(cand)
            n = v.get(cand.lower(), 0)
            if n > best_n * 2 or (best_n == 0 and n > 0):
                best, best_n = cand, n
        if best == w and best_n == 0:      # a word not in the library at all: f before a consonant no English f precedes is a long s
            best = re.sub(r'^ft|f(?=[pcbkmnwhqd])', lambda x: 'st' if x.group(0) == 'ft' else 's', w)
        return best
    return re.sub(r"[A-Za-z]+", fix, text)


def avalon_blocks(url, key):
    os.makedirs(f'{RAW}/avalon', exist_ok=True)
    path = f'{RAW}/avalon/{key}.html'
    if not os.path.exists(path):
        open(path, 'wb').write(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read())
        time.sleep(2)
    h = open(path, encoding='utf-8', errors='replace').read()
    a = h.find('</div>', h.find('class="document-title"'))
    z = h.rfind('class="page-menu"')      # the contents link printed again below the text
    h = h[a + 6: h.rfind('<div', 0, z) if z > 0 else len(h)]
    h = re.sub(r'<table class="page-menu".*?</table>', '', h, flags=re.S)
    h = re.sub(r'\.?\{FS\}.*?\.?\{FE\}', '', h, flags=re.S)      # footnotes
    h = re.sub(r'\.?\{\.?\{?F[SE]\}\}?', '', h)      # a footnote marker left unpaired in the transcription
    h = re.sub(r'<table.*?</table>', '', h, flags=re.S)          # the printer's signature and catchword line
    h = re.sub(r'<sup>.*?</sup>', '', h, flags=re.S)
    h = re.sub(r'</?font[^>]*>', '', h)
    # a page marker and the running head that follows it ("PRIVATE WRONGS. / BOOK III. / Ch. 1")
    h = re.sub(r'\.P \d+\s*<br>(?:\s*(?:[A-Z][A-Z ,.;\'&-]{0,40}|BOOK [IVX]+\.?|Ch\. ?\d+\.?)\s*<br>){0,3}', '\n', h)
    h = re.sub(r'\.P \d+', '', h)
    out = []
    for para in re.split(r'<br>\s*<br>', h):
        lines = [clean(x) for x in re.split(r'<br>|\n', para)]
        lines = [x for x in lines if x]
        if not lines:
            continue
        caps = all(re.sub(r'[^A-Za-z]', '', x).isupper() and len(x) <= 90 for x in lines)
        if caps:
            out.extend(['h', fix_long_s(x)] for x in lines)
        else:
            out.append(['p', fix_long_s(' '.join(lines))])
    return out


# ---------------------------------------------------------------------------------------------- Internet Archive OCR
def ia_text(ident):
    os.makedirs(f'{RAW}/ia', exist_ok=True)
    path = f'{RAW}/ia/{ident}.txt'
    if not os.path.exists(path):
        data = urllib.request.urlopen(urllib.request.Request(f'https://archive.org/download/{ident}/{ident}_djvu.txt', headers=UA), timeout=600).read()
        open(path, 'wb').write(data)
        time.sleep(2)
    return open(path, encoding='utf-8', errors='replace').read()


def ocr_blocks(txt, opt):
    """OCR text (one line per printed line, blank lines between paragraphs) -> [[kind, text]]: running heads and page
    numbers dropped (short lines that recur through the volume), words broken at line ends joined, footnotes dropped."""
    from collections import Counter
    head = re.compile(opt['head_re']) if opt.get('head_re') else None
    sub = re.compile(opt['sub_re']) if opt.get('sub_re') else None
    note = re.compile(opt.get('note_re', r'^(?:\d{1,3}|[*†‡§])\s+[A-Z"“‘(\[]'))
    furn = re.compile(opt['furniture_re']) if opt.get('furniture_re') else None
    groups = [(re.compile(g), label) for g, label in opt.get('groups', [])]
    group_of = lambda x: next((label for g, label in groups if g.match(x)), None)
    inline = opt.get('head_inline')
    lines = [re.sub(r'[ \t]+', ' ', x).strip() for x in txt.replace('\r', '').split('\n')]
    norm = lambda x: re.sub(r'[\W\d_]+', ' ', x.lower()).strip()
    freq = Counter(norm(x) for x in lines if 0 < len(x) <= 70)
    keep = []
    for x in lines:
        if x and not (head and head.match(x)) and not (sub and sub.match(x)) and not group_of(x):
            n = norm(x)
            if (len(x) <= 70 and freq[n] >= opt.get('head_freq', 4) and n.count(' ') <= 6) or not n \
                    or re.fullmatch(r'[ivxlc]{1,6}\.?', n) or (furn and furn.search(x)):
                x = ''      # a running head, page number or stray mark
                keep.append(None)
                continue
        keep.append(x)
    # paragraphs: consecutive lines; a dropped line (page furniture) does not end a paragraph
    paras, cur = [], []
    for x in keep:
        if x is None:
            continue
        if x == '':
            if cur:
                paras.append(cur)
                cur = []
            continue
        if (head and head.match(x) and not inline) or (sub and sub.match(x)) or group_of(x):
            if cur:
                paras.append(cur)
            paras.append([x])
            cur = []
            continue
        cur.append(x)
    if cur:
        paras.append(cur)
    out = []
    for p in paras:
        t = p[0]
        for x in p[1:]:
            if re.search(r'[-¬]$', t) and re.match(r'[a-z]', x):
                t = t[:-1] + x
            else:
                t += ' ' + x
        t = t.replace('¬', '')
        t = re.sub(r'(?<=[a-z,.;:)”"’\]])\d{1,3}(?=[\s,.;:]|$)', '', t)      # a note number set against a word
        t = re.sub(r'(?<=[.;:)”"’\]*])\s\d{1,2}(?=\s[A-Z(“"]|$)', '', t)       # ... or set after the sentence
        t = re.sub(r'\s+([,.;:])', r'\1', t).strip()
        if not t:
            continue
        if group_of(t):
            out.append(['group', group_of(t)])
            continue
        if head and head.match(t):
            out.append(['split', t])
            if inline:      # the date opens a paragraph of the text: it names the part and the paragraph stays
                out.append(['p', t])
            continue
        if sub and sub.match(t):
            out.append(['h', t])
            continue
        if note.match(t) and not re.match(r'^\d{1,3}\.', t):
            continue                                                            # a footnote
        if opt.get('drop_re') and re.search(opt['drop_re'], t):
            continue
        letters = [c for c in t if c.isalpha()]
        if len(t) <= 80 and letters and sum(c.isupper() for c in letters) > 0.85 * len(letters):
            out.append(['h', t])
        elif len(letters) < 0.5 * len(t) and len(t) < 200 and not re.search(r'\[\s*\*\s*\d+\s*\]', t):
            continue                                                            # a vote table or OCR debris
        else:
            out.append(['p', t])
    return out


def fix_ocr_words(title):
    """Misread words in a part title ("Op the Eight of Indivrdijals") replaced by the closest common word in the library."""
    import difflib
    v = long_s_vocab()
    common = getattr(fix_ocr_words, 'common', None)
    if common is None:
        common = fix_ocr_words.common = {}
        for w, n in v.items():
            if n >= 20 and len(w) > 1:
                common.setdefault(len(w), []).append(w)
    def fix(m):
        w = m.group(0)
        low = w.lower()
        if v.get(low, 0) >= 5 or len(w) < 2 or re.fullmatch(r'[IVXLC]+', w):
            return w
        cands = [c for L in (len(low) - 1, len(low), len(low) + 1) for c in common.get(L, [])]
        best = difflib.get_close_matches(low, cands, n=1, cutoff=0.7)
        if not best:
            return w
        b = best[0]
        return b.capitalize() if w[0].isupper() else b
    title = title.replace('£', 'e').replace('«', '').replace('"', '')
    return re.sub(r"[A-Za-z]+", fix, title)


def _roman(n):
    out = ''
    for v, r in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
        out += r * (n // v)
        n %= v
    return out


def build_archive(bid, title, author, year, idents, corner, opt):
    """opt: head_re (a line that opens a part), sub_re (lines kept as headings inside a part), start_re / stop_re (the
    text begins at the first part whose title matches / ends before it, per volume), note_re (footnote paragraphs),
    furniture_re (more lines to drop), drop_re, head_freq, vol_labels, title_sub, rename, smart, sub_title, vol_opt,
    groups ([(regex, label)]: a line naming a section, such as a state's convention; it opens a part and prefixes the part
    titles that follow), head_inline (head_re matches the start of a paragraph, which stays in the text), merge_below,
    min_words, star_splits ([(part title, page)]: parts open where the original edition's page, marked [*n] in the text,
    begins: the lecture headings of Kent's Commentaries that the scanner missed), strip_re (patterns removed from the text
    after splitting), seq (parts numbered in order, "Chapter" -> Chapter I, II, ..., restarting at each group, instead of
    the misread numerals)."""
    parts, group, seq_n = [], '', 0
    for v, ident in enumerate(idents, 1):
        vo = dict(opt, **opt.get('vol_opt', {}).get(v, {}))
        blocks = ocr_blocks(ia_text(ident), vo)
        if vo.get('star_splits'):
            marks, last = {}, -1
            for title_, page in vo['star_splits']:
                find = lambda pg: next((i for i, (_, t) in enumerate(blocks) if i > last and re.search(r'\[\s*\*\s*%d\s*\]' % pg, t)), None)
                k = find(page)
                if k is None and page > 1:      # the first page's marker was lost: go back from the next page's to the title
                    k = find(page + 1)
                    if k is not None:
                        k = next((j for j in range(k, max(last, k - 25), -1) if blocks[j][0] == 'h' and re.match(r'^\W*OF\s', blocks[j][1])), k)
                if k is None:      # no page marker at all: the lecture's own title line, as printed ("OF THE GENERAL RIGHTS ...")
                    import difflib
                    want = re.sub(r'^.*?:\s*', '', title_).lower()
                    sim = lambda t: difflib.SequenceMatcher(None, want, re.sub(r'[^a-z ]', '', t.lower())).ratio()
                    cands = [(sim(t), i) for i, (kind, t) in enumerate(blocks) if i > last and kind == 'h' and re.match(r'^\W*O[FP]\s', t)][:40]
                    best = max(cands, default=(0, None))
                    k = best[1] if best[0] >= 0.6 else None
                if k is not None and k > last:
                    marks[k], last = title_, k
            out = []
            for i, b in enumerate(blocks):
                if i in marks:
                    out.append(['split', marks[i]])
                    if re.match(r'^\W*L\s?E\s?C', b[1]) and len(b[1]) < 40:      # the misread "LECTURE VI." line itself
                        continue
                out.append(b)
            blocks = out
        for pat in vo.get('strip_re', []):
            blocks = [[k, re.sub(pat, '', t).strip()] for k, t in blocks]
            blocks = [b for b in blocks if b[1]]
        vparts, cur, name = [], [], None
        for kind, t in blocks:
            if kind == 'group':      # a new section (a state's convention): its opening text is a part of its own
                if name is not None or cur:
                    vparts.append((name or 'Front matter', cur))
                group, seq_n = t, 0
                name, cur = t, [['h', t]]
            elif kind == 'split':
                if name is not None or cur:
                    vparts.append((name or 'Front matter', cur))
                seq_n += 1
                ttl = f"{vo['seq']} {_roman(seq_n)}" if vo.get('seq') else part_title(t, vo)
                if vo.get('fix_titles'):
                    ttl = fix_ocr_words(ttl)
                name = (f'{group} · ' if group else '') + ttl
                cur = [] if vo.get('head_inline') or vo.get('star_splits') else [['h', ttl if vo.get('seq') else t]]
            else:
                cur.append([kind, t])
        vparts.append((name or 'Front matter', cur))
        if vo.get('start_re'):
            ks = [i for i, (n, _) in enumerate(vparts) if re.match(vo['start_re'], n, re.I)] or [0]
            vparts = vparts[ks[-1] if vo.get('start_last') else ks[0]:]      # start_last: past a table of contents
        if vo.get('stop_re'):
            k = next((i for i, (n, _) in enumerate(vparts) if re.match(vo['stop_re'], n, re.I)), None)
            vparts = vparts[:k] if k is not None else vparts
        if vo.get('sub_title'):
            vparts = [(sub_title(n, b), b) for n, b in vparts]
        if vo.get('fix_titles'):
            vparts = [(fix_ocr_words(n), b) for n, b in vparts]
        if vo.get('word_fix'):      # misread words in titles, corrected by hand
            wf = vo['word_fix']
            vparts = [(re.sub(r"[^\s]+", lambda m: wf.get(m.group(0), m.group(0)), n), b) for n, b in vparts]
        merged = []
        for n, b in vparts:
            w = sum(len(x[1].split()) for x in b)
            if merged and merged[-1][2] < vo.get('merge_below', 120):
                pn, pb, pw = merged.pop()
                n, b, w = (pn if pn != 'Front matter' else n), pb + b, pw + w
            merged.append((n, b, w))
        labels = vo.get('vol_labels')
        prefix = (labels[v - 1] + ' · ' if labels[v - 1] else '') if labels else (f'Vol. {["I", "II", "III", "IV", "V"][v - 1]} · ' if len(idents) > 1 else '')
        parts.extend((prefix + n, b) for n, b, w in merged if w >= vo.get('min_words', 60))
    parts = split_long(parts)
    lic = ('Public-domain text; OCR of the Internet Archive scan' + ('s ' if len(idents) > 1 else ' ') + ', '.join(idents) +
           ', cleaned automatically (running heads, page numbers and footnotes removed). OCR errors remain; check quotations against the page images')
    return write_book({'id': bid, 'title': title, 'author': author, 'year': year, 'src': f'https://archive.org/details/{idents[0]}',
                       'srcName': 'Internet Archive', 'license': lic, 'corner': corner}, parts)


# ---------------------------------------------------------------------------------------------- supplements
def read_book(bid):
    s = open(f'{OUT}/{bid}.js', encoding='utf-8').read()
    meta = json.loads(s[s.index(']=') + 2:].rstrip().rstrip(';'))
    parts = []
    for n in range(1, len(meta['toc']) + 1):
        c = open(f'{OUT}/{bid}-{n}.js', encoding='utf-8').read()
        c = json.loads(c[c.index(']=') + 2:].rstrip().rstrip(';'))
        parts.append((c['t'], c['b']))
    return meta, parts


def supplement(bid, cut_re, label, src_note, new_parts):
    """Add parts from another source to the end of a built work (Blackstone's Books III-IV from Avalon, Montesquieu's
    second volume from an Internet Archive scan), first dropping its own parts from the first whose title matches
    cut_re; the earlier parts keep their numbers, so readers' places and highlights stay put."""
    meta, parts = read_book(bid)
    k = next((i for i, (n, _) in enumerate(parts) if cut_re and re.match(cut_re, n)), len(parts))
    parts = parts[:k] + [(f'{label}{n}', b) for n, b in new_parts]
    meta = {x: meta[x] for x in ('id', 'title', 'author', 'year', 'src', 'srcName', 'license', 'corner')}
    meta['license'] = meta['license'].split(' · Supplemented')[0] + f' · Supplemented: {src_note}'
    return write_book(meta, parts)


SUPPLEMENTS = [
    # id, parts of the work to drop from (regex on part title, '' for none), part-title prefix, source note, builder
    ('blackstone', r'^(?:Of Redress by the mere operation of Law|Book III · )', '', 'Books III and IV from the Avalon Project (Yale Law School), '
     'transcribed from the first edition (1768–1769); the long s, printed there as f, is restored automatically',
     lambda: avalon_blackstone()),
    ('spirit-of-laws', r'^Volume II · ', 'Volume II · ', 'Books XX–XXXI from the Internet Archive scans spiritoflawsincl01mont and spiritoflawsincl02montuoft (Nugent '
     'trans., Colonial Press ed., 1900), OCR cleaned automatically', lambda: montesquieu_vol2()),
]


def avalon_blackstone():
    idx = urllib.request.urlopen(urllib.request.Request('https://avalon.law.yale.edu/subject_menus/blackstone.asp', headers=UA), timeout=60).read().decode('utf-8', 'replace')
    parts = []
    for m in re.finditer(r'href="\.\./18th_century/(blackstone_bk([34])(ch\d+|app\d*|supp))\.asp">([^<]+)', idx):
        key, book, name = m.group(1), m.group(2), clean(m.group(4))
        b = avalon_blocks(f'https://avalon.law.yale.edu/18th_century/{key}.asp', key)
        name = re.sub(r'^Chapter the ([\w-]+)\s*:\s*', lambda x: f'Chapter {x.group(1).title()}: ', name)
        parts.append((f'Book {"III" if book == "3" else "IV"} · {name}', b))
    return parts


MONTESQUIEU_BOOKS = {
    'XX': 'Of Laws in Relation to Commerce, Considered in Its Nature and Distinctions',
    'XXI': 'Of Laws in Relation to Commerce, Considered in the Revolutions It Has Met With in the World',
    'XXII': 'Of Laws in Relation to the Use of Money',
    'XXIII': 'Of Laws in the Relation They Bear to the Number of Inhabitants',
    'XXIV': 'Of Laws in Relation to Religion, Considered in Itself and in Its Doctrines',
    'XXV': 'Of Laws in Relation to the Establishment of Religion and Its External Polity',
    'XXVI': 'Of Laws in Relation to the Order of Things Which They Determine',
    'XXVII': 'Of the Origin and Revolutions of the Roman Laws on Successions',
    'XXVIII': 'Of the Origin and Revolutions of the Civil Laws Among the French',
    'XXIX': 'Of the Manner of Composing Laws',
    'XXX': 'Theory of the Feudal Laws Among the Franks, in the Relation They Bear to the Establishment of the Monarchy',
    'XXXI': 'Theory of the Feudal Laws Among the Franks, in the Relation They Bear to the Revolutions of Their Monarchy',
}


def montesquieu_vol2():
    """Books XX-XXXI (the Wikisource transcription stops at Book XIX) from the Colonial Press edition's two volumes,
    each read up to its index."""
    opt = {'head_re': r'^BOOK\s+[XVIL]{2,6}\.?\s*$', 'note_re': r'^(?:\d{1,3}|[a-z]|[*†‡§])\s+(?:[A-Z"“‘(\[]|ibid|see)'}
    blocks = []
    for ident in ('spiritoflawsincl01mont', 'spiritoflawsincl02montuoft'):
        txt = ia_text(ident)
        a = re.search(r'^BOOK\s+XX\s*$', txt, re.M) if ident.endswith('01mont') else None
        txt = txt[a.start():] if a else txt
        last = list(re.finditer(r'^BOOK\s+[XVIL]+\s*$', txt, re.M))      # the index or the publisher's pages after the last book
        z = re.compile(r"^(?:INDEX|THE\s+WORLD'S)\s*$", re.M).search(txt, last[-1].end() if last else 0)
        blocks += ocr_blocks(txt[:z.start()] if z else txt, opt)
    parts, cur, name = [], [], None
    for kind, t in blocks:
        if kind == 'split':
            if name:
                parts.append((name, cur))
            num = re.sub(r'[^XVIL]', '', t.split(None, 1)[1])
            name, cur = f'Book {num}: {MONTESQUIEU_BOOKS.get(num, "")}'.rstrip(': '), [['h', f'Book {num}']]
        elif name:
            cur.append([kind, t])
    if name:
        parts.append((name, cur))
    k = next((i for i, (n, _) in enumerate(parts) if n.startswith('Book XX:')), 0)
    return split_long([(n, b) for n, b in parts[k:] if sum(len(x[1].split()) for x in b) >= 60])



# ---------------------------------------------------------------------------------------------- Annals of Congress
ANNALS_DAY = re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),?\s+([A-Z][a-zA-Z^]{2,9})\.?,?\s+([\dIilSoO ]{1,4})[.,]?\s*$', re.I)
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']


def build_annals(bid, title, author, year, ident, first_year):
    """The Annals of Congress from an Internet Archive scan: each chamber's proceedings read a day per part. The scanner
    misreads many day numbers ("June 33"), so each date is worked out from its weekday and month, the day falling on or
    after the previous sitting; a date that goes back marks the next chamber or session, named from the running heads."""
    import datetime
    lines = ia_text(ident).replace('\r', '').split('\n')
    heads = []
    for i, x in enumerate(lines):
        m = ANNALS_DAY.match(re.sub(r'[ \t]+', ' ', x).strip())
        if not m:
            continue
        wd = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'].index(m.group(1).lower())
        mon = next((k for k, name in enumerate(MONTHS, 1) if difflib_ratio(m.group(2).lower(), name) >= 0.7), None)
        if mon:
            heads.append((i, wd, mon, re.sub(r'\D', '', ocr_num(m.group(3).replace(' ', '')))))
    # sessions of the First Congress: a misread date can only fall inside one of them
    sessions = [(datetime.date(1789, 3, 4), datetime.date(1789, 9, 29), 'First Session'),
                (datetime.date(1790, 1, 4), datetime.date(1790, 8, 12), 'Second Session'),
                (datetime.date(1790, 12, 6), datetime.date(1791, 3, 3), 'Third Session')]
    in_session = lambda d: next((name for a_, z_, name in sessions if a_ <= d <= z_), None)
    dated, prev = [], None
    for i, wd, mon, num in heads:
        days = [datetime.date(y, mon, d) for y in (1789, 1790, 1791) for d in range(1, 32)
                if _valid(y, mon, d) and datetime.date(y, mon, d).weekday() == wd and in_session(datetime.date(y, mon, d))]
        if not days:
            continue
        after = [d for d in days if prev and 0 <= (d - prev).days <= 14]
        if not after and prev:      # the month misread too ("Monday, January 31" for February 1): the same weekday soon after
            after = [prev + datetime.timedelta(days=k) for k in range(1, 8) if (prev + datetime.timedelta(days=k)).weekday() == wd]
            after = [d for d in after if in_session(d)] if (int(num or 0) > 28 or not num) else []
        if after:
            d = after[0]
        else:      # the next chamber begins its record again: the session day nearest the printed number
            n = int(num) if num else 1
            sidx = lambda x: next(k for k, (a_, z_, _) in enumerate(sessions) if a_ <= x <= z_)
            d = min(days, key=lambda x: (abs(x.day - n) + (3 * abs(sidx(x) - sidx(prev)) if prev else 0), x))
        dated.append((i, d))
        prev = d
    # sections where the dates go back; each named from its running heads ("[Senate." or "H. OF R.")
    sections, start = [], 0
    for k in range(1, len(dated)):
        gap = (dated[k][1] - dated[k - 1][1]).days
        if gap < -3 or gap > 30:      # back to the start of a session, or on to the next session
            sections.append((start, k))
            start = k
    sections.append((start, len(dated)))
    parts = []
    for a, z in sections:
        lo = dated[a][0]
        hi = dated[z][0] if z < len(dated) else len(lines)
        seg = '\n'.join(lines[lo:hi])
        senate = len(re.findall(r'\[Senate\.|Senate\.\]', seg))
        house = len(re.findall(r'H\.\s*(?:OF|of)\s*R', seg))
        chamber = 'Senate' if senate > house else 'House of Representatives'
        sess = in_session(dated[a][1])
        for k in range(a, z):
            lo = dated[k][0]
            hi = dated[k + 1][0] if k + 1 < len(dated) else len(lines)
            b = ocr_blocks('\n'.join(lines[lo + 1:hi]), {'furniture_re': r'^\S{0,14}(?:Senate|SENATE|H\.\s*(?:OF|of)\s*R)\S{0,3}\s*$|^\S{0,4}\s*[A-Z]{3,9},\s*1\s?7\s?[89]\s?\d\.?\]?\s*\S{0,10}$|^\d{2,4}\s*$'})
            d = dated[k][1]
            parts.append((f'{chamber} ({sess}) · {d.strftime("%A")}, {d.strftime("%B")} {d.day}, {d.year}', [['h', lines[lo].strip()]] + b))
    merged = []
    for n, b in parts:      # a day whose page ended up empty is joined to the next
        w = sum(len(x[1].split()) for x in b)
        if merged and merged[-1][2] < 40:
            pn, pb, pw = merged.pop()
            b, w = pb + b, pw + w
        merged.append((n, b, w))
    parts = split_long([(n, b) for n, b, w in merged])
    lic = (f'Public-domain text; OCR of the Internet Archive scan {ident} (Gales and Seaton, 1834), cleaned automatically; dates '
           'reconstructed from the weekday where the scan misread them. OCR errors remain; check quotations against the page images')
    return write_book({'id': bid, 'title': title, 'author': author, 'year': year, 'src': f'https://archive.org/details/{ident}',
                       'srcName': 'Internet Archive', 'license': lic, 'corner': ''}, parts)


def _valid(y, m, d):
    import datetime
    try:
        datetime.date(y, m, d)
        return True
    except ValueError:
        return False


def difflib_ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


ANNALS = [
    ('annals-1', 'Annals of Congress, Volume I: The First Congress, March 1789–February 1790 (with the Bill of Rights Debates)', 'Joseph Gales (comp.)',
     '1789–1790 (pub. 1834)', 'debatesandproce00galegoog', 1789),
]


def main():
    only = sys.argv[1:]
    idx_path = 'docs/data/lib-index.js'
    index = {}
    if os.path.exists(idx_path):
        s = open(idx_path, encoding='utf-8').read()
        index = {x['id']: x for x in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))}
    for b in WIKISOURCE:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    for b in GUTENBERG:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build_gutenberg(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    for b in COLLECTIONS:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build_collection(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    for b in ARCHIVE:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build_archive(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    for b in ANNALS:
        if only and b[0] not in only:
            continue
        try:
            index[b[0]] = build_annals(*b)
        except Exception as e:
            print(f'{b[0]}: FAILED {e}', flush=True)
    for bid, cut, label, note, fn in SUPPLEMENTS:      # after the work itself is built (or on its own: "blackstone+")
        if only and bid not in only and bid + '+' not in only:
            continue
        try:
            index[bid] = supplement(bid, cut, label, note, fn())
        except Exception as e:
            print(f'{bid} supplement: FAILED {e}', flush=True)
    # re-read the index before writing: another run may have added works meanwhile; keep theirs, update ours
    built = {k: v for k, v in index.items() if not only or k in only or k + '+' in only}
    if os.path.exists(idx_path):
        s = open(idx_path, encoding='utf-8').read()
        index = {x['id']: x for x in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))}
    index.update(built)
    open(idx_path, 'w', encoding='utf-8').write('window.LIB_INDEX=' + json.dumps(list(index.values()), ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
