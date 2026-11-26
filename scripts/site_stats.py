"""Write docs/data/site-stats.js: the counts quoted in the site's descriptions (home page, section intros, About), so the
text matches the data without loading the large files. Run from the repo root after rebuilding data:
    python scripts/site_stats.py
window.SITE_STATS = {articles, journals, cases, oyezCases, firstYear, aiBriefs, headnotes, justices, books,
                     essentialBooks, lectures, guideTopics, doctrineSections, cornerTopics, cornerPassages, cornerSources,
                     libraryWorks, libraryWords, libraryFounding, crsSidebars, flashcards}
"""
import glob, json, re


def load(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def assigned(pattern):
    """Entries in files written as window.X=window.X||{};Object.assign(window.X,{...});"""
    n = 0
    for f in glob.glob(pattern):
        s = open(f, encoding='utf-8').read()
        m = re.search(r'Object\.assign\(window\.\w+,', s)
        if m:
            n += len(json.loads(s[m.end():s.rindex(')')]))
    return n


def count_items(o):
    if isinstance(o, list):
        return len(o)
    if isinstance(o, dict):
        for k in ('cards', 'items', 'questions', 'quizzes', 'decks', 'terms'):
            if k in o:
                return count_items(o[k])
        return sum(count_items(v) for v in o.values() if isinstance(v, (list, dict)))
    return 0


def main():
    st = {}
    A = load('docs/data/articles.js')
    st['articles'] = len(A['articles'])
    st['journals'] = sum(1 for j in A['journals'] if j.get('count'))
    S = load('docs/data/scotus.js')['cases']
    st['cases'] = len(S)
    st['oyezCases'] = sum(1 for c in S if 'ds' in c or 'q' in c)     # cases with Oyez's summary, question and argument audio
    st['firstYear'] = min(int(c['y']) for c in S if str(c.get('y', '')).isdigit())
    st['aiBriefs'] = assigned('docs/data/aibriefs/*.js')
    st['headnotes'] = assigned('docs/data/headnotes/*.js')
    J = load('docs/data/justices.js')
    st['justices'] = count_items(J.get('justices', J) if isinstance(J, dict) else J)
    B = load('docs/data/books.js')
    books = B['books'] if isinstance(B, dict) else B
    st['books'] = len(books)
    st['essentialBooks'] = sum(1 for b in books if b.get('essential') or b.get('ess'))
    Lc = load('docs/data/lectures.js')
    st['lectures'] = len(Lc['videos']) if isinstance(Lc, dict) and 'videos' in Lc else count_items(Lc)
    G = load('docs/data/guide.js')
    st['guideTopics'] = len(G['topics'])
    D = load('docs/data/advanced.js')
    st['doctrineParts'] = len(D['parts'])
    st['doctrineSections'] = sum(len(p['sections']) for p in D['parts'])
    C = load('docs/data/corner.js')
    st['cornerTopics'] = sum(1 for t in C['topics'] if t.get('n'))
    st['cornerPassages'] = len(C['passages'])
    st['cornerSources'] = len(C['sources'])
    idx = load('docs/data/lib-index.js')
    # later-period works (app.js LATER_IDS): listed apart from the founding era
    LATER = ('tocqueville', 'union-slavery-war', 'lincoln-speeches', 'twentieth-century', 'webster-speeches', 'lincoln-douglas',
             'douglass-writings', 'dred-scott', 'ross-impeachment', 'lynch-reconstruction', 'blaine-congress-2')
    st['libraryWorks'] = len(idx) + 3   # plus The Federalist, the founding documents and the early statutes
    st['libraryWords'] = sum(x['words'] for x in idx)
    st['libraryFounding'] = sum(1 for x in idx if x.get('shelf') != 'gov' and x['id'] not in LATER) + 3
    st['crsSidebars'] = next((x['chapters'] for x in idx if x['id'] == 'crs-sidebars'), 0)
    st['flashcards'] = count_items(load('docs/data/flashcards.js'))
    open('docs/data/site-stats.js', 'w', encoding='utf-8').write('window.SITE_STATS=' + json.dumps(st, separators=(',', ':')) + ';')
    print(json.dumps(st, indent=1))


if __name__ == '__main__':
    main()
