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
        return re.sub(r'^([^a-z]*)([a-z])|(?<=[-.])([a-z])', lambda m: (m.group(1) or '') + (m.group(2) or m.group(3)).upper(), x)
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
            raise RuntimeError(f'eBook {n}: no copy found')
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
    # re-read the index before writing: another run may have added works meanwhile; keep theirs, update ours
    built = {k: v for k, v in index.items() if not only or k in only}
    if os.path.exists(idx_path):
        s = open(idx_path, encoding='utf-8').read()
        index = {x['id']: x for x in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))}
    index.update(built)
    open(idx_path, 'w', encoding='utf-8').write('window.LIB_INDEX=' + json.dumps(list(index.values()), ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
