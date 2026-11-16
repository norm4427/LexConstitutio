"""AI-generated case briefs for Supreme Court cases that have no summary from Oyez.

The site otherwise shows only sourced text. These briefs are the one exception the site owner asked for: each is
written by Claude from the Court's opinion and shown on the case page under a notice that it is AI-generated.
Quotations in a brief are checked against the opinion text: a brief whose quoted words are not found verbatim in the
opinion is regenerated once and otherwise discarded.

Which cases, in this order (the owner's priority):
  1. the most-cited cases without a summary (50+ later Supreme Court citations, Caselaw Access Project), most cited first
  2. then the most recent cases without a summary (decided 2000 or later), newest first
  3. then every other case, most cited first, then newest
"Without a summary": listed from the Supreme Court Database only (no Oyez record), or Oyez's record has neither facts
nor conclusion (cached in data/raw/oyez/cases/, re-checked live before writing).

Opinion text: the case's opinion PDF on the site (Library of Congress U.S. Reports, or supremecourt.gov), converted
with pdftotext, cached in data/raw/aibriefs/op/. Other sources the site already parsed are added when present: the
merits briefs' Tables of Authorities are not needed, but the official argument transcript's appearances (who argued)
and the docket's parties are passed as context (data/raw/briefs, docs/data/parties).

Store: data/raw/aibriefs/briefs.json (one record per case id). Output: docs/data/aibriefs/<decade>.js
(window.AIBRIEFS[<case id>]) and docs/data/aibriefs-index.js (decades present).

Usage (from the repo root):
  python scripts/build_ai_briefs.py --queue 40             print the next 40 cases in the queue
  python scripts/build_ai_briefs.py --fetch 40             fetch and cache the opinion text of the next 40
  python scripts/build_ai_briefs.py --generate 50          write briefs for the next 50 with the Claude API
                                                           (pip install anthropic; ANTHROPIC_API_KEY or `ant auth login`)
  python scripts/build_ai_briefs.py --import file.json     add briefs written elsewhere ({"<case id>": {...}}), same checks
  python scripts/build_ai_briefs.py --publish              rewrite docs/data/aibriefs/ from the store
Then: sh scripts/stamp.sh
"""
import collections, glob, json, os, re, subprocess, sys, time, urllib.request
from datetime import date

RAW = 'data/raw/aibriefs'
OUT = 'docs/data/aibriefs'
STORE = f'{RAW}/briefs.json'
MODEL = 'claude-opus-5-5'
UA = {'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0 (academic research index)'}
FIELDS = ['facts', 'procedure', 'question', 'holding', 'reasoning', 'separate', 'disposition']


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def load_store():
    return json.load(open(STORE, encoding='utf-8')) if os.path.exists(STORE) else {}


def save_store(st):
    os.makedirs(RAW, exist_ok=True)
    json.dump(st, open(STORE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ queue
def queue():
    S = load_js('docs/data/scotus.js')['cases']
    I = load_js('docs/data/case_impact.js')['c']
    cache = {}
    for f in glob.glob('data/raw/oyez/cases/*.json'):
        d = json.load(open(f, encoding='utf-8'))
        cache[os.path.basename(f)[:-5]] = bool((d.get('facts_of_the_case') or '').strip() or (d.get('conclusion') or '').strip())
    cand = []
    for c in S:
        if c.get('s') == 1 and not c.get('pdf'):      # Library of Congress U.S. Reports PDF, as the site links it (app.js scdbLinks)
            m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
            if m and int(m.group(1)) <= 576:
                v, pg = int(m.group(1)), int(m.group(2))
                k = f'usrep{v:03d}{pg:03d}'
                c['pdf'] = f'https://tile.loc.gov/storage-services/service/ll/usrep/usrep{v:03d}/{k}/{k}.pdf'
        if not c.get('dec') or not c.get('pdf'):
            continue
        k = c['id'].replace('/', '_')
        if c.get('s') == 1 or (k in cache and not cache[k]):
            cand.append(c)
    cites = lambda c: (I.get(c['id']) or [0, 0, 0])[2]
    a = sorted([c for c in cand if cites(c) >= 50], key=lambda c: -cites(c))
    seen = {c['id'] for c in a}
    b = sorted([c for c in cand if c['id'] not in seen and c['dec'] >= '2000-01-01'], key=lambda c: c['dec'], reverse=True)
    seen |= {c['id'] for c in b}
    rest = sorted([c for c in cand if c['id'] not in seen], key=lambda c: (-cites(c), c['dec']), reverse=False)
    return a + b + rest, cites


def still_no_summary(c):
    if c.get('s') == 1:
        return True
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request('https://api.oyez.org/cases/' + c['id'], headers=UA), timeout=60))
        return not ((d.get('facts_of_the_case') or '').strip() or (d.get('conclusion') or '').strip())
    except Exception:
        return True


# ------------------------------------------------------------------ opinion text
def opinion_text(c):
    os.makedirs(f'{RAW}/op', exist_ok=True)
    p = f"{RAW}/op/{c['id'].replace('/', '_')}.txt"
    if os.path.exists(p):
        return open(p, encoding='utf-8', errors='replace').read()
    for dk in re.split(r'[,;\s]+', (c.get('d') or '').lower()):      # already fetched for the Authorities tab
        q = f'data/raw/briefs/{dk}/opinion.txt'
        if dk and os.path.exists(q):
            t = open(q, encoding='utf-8', errors='replace').read()
            open(p, 'w', encoding='utf-8').write(t)
            return t
    pdf = p[:-4] + '.pdf'
    try:
        b = urllib.request.urlopen(urllib.request.Request(c['pdf'], headers=UA), timeout=180).read()
        if not b.startswith(b'%PDF'):
            return ''
        open(pdf, 'wb').write(b)
        subprocess.run(['pdftotext', '-q', '-enc', 'UTF-8', pdf, p], check=True)
        time.sleep(0.8)
        return open(p, encoding='utf-8', errors='replace').read()
    except Exception as e:
        print('  opinion failed', c['id'], e, flush=True)
        return ''
    finally:
        if os.path.exists(pdf):
            os.remove(pdf)


# ------------------------------------------------------------------ verbatim check
def norm(s):
    s = s.replace('­', '')
    s = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', s)
    s = s.translate(str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'", '—': '-', '–': '-', '\f': ' '}))
    return re.sub(r'\s+', ' ', s).lower().strip()


def quotes_in(text):
    return [q for q in re.findall(r'[“"]([^“”"]{4,})[”"]', text)]


def check_quotes(brief, source):
    src = norm(source)
    src_nohy = src.replace('- ', '')
    bad = []
    for f in FIELDS:
        for q in quotes_in(brief.get(f) or ''):
            parts = [x for x in re.split(r'\s*(?:\.\s?\.\s?\.|…)\s*', q) if x.strip()]   # ellipses join verbatim pieces
            for part in parts:
                n = norm(part).strip(' ,.;:')
                n = re.sub(r'\[[^\]]{0,12}\]', '', n).strip()                     # bracketed alterations
                if len(n) < 4:
                    continue
                pieces = [x.strip() for x in re.split(r'\s*\[[^\]]*\]\s*', norm(part)) if len(x.strip()) >= 4]
                if not all(x.strip(' ,.;:') in src or x.strip(' ,.;:') in src_nohy for x in pieces or [n]):
                    bad.append(q)
                    break
    return bad


# ------------------------------------------------------------------ generation (Claude API)
SCHEMA = {
    'type': 'object',
    'properties': {
        'facts': {'type': 'string', 'description': 'The facts of the case and how the dispute arose (2-5 sentences).'},
        'procedure': {'type': 'string', 'description': 'What the lower courts decided and how the case reached the Supreme Court (1-3 sentences).'},
        'question': {'type': 'string', 'description': 'The legal question(s) the Court decided, phrased as a question.'},
        'holding': {'type': 'string', 'description': 'The Court\'s answer and the rule it announced (1-3 sentences).'},
        'reasoning': {'type': 'string', 'description': 'The main steps of the Court\'s reasoning (3-7 sentences).'},
        'separate': {'type': 'string', 'description': 'Concurring and dissenting opinions: who wrote them and their main point; empty string if none.'},
        'disposition': {'type': 'string', 'description': 'Affirmed / reversed / remanded etc., with the vote and the author of the opinion of the Court when the opinion states them.'},
    },
    'required': FIELDS,
    'additionalProperties': False,
}
SYSTEM = """You write short, accurate case briefs of United States Supreme Court decisions for a constitutional-law study site.
Work only from the opinion text provided; do not add facts, history or later developments that the text does not contain.
Write plain, neutral prose for a law student. Name the justices who wrote each opinion when the text shows it.
Use quotation marks only for words copied exactly, character for character, from the opinion text (an ellipsis may join
two exact pieces); keep quotations short. Otherwise paraphrase without quotation marks.
If the text is incomplete or unreadable for some part, say so briefly in that field instead of guessing."""


def context_for(c):
    lines = [f"Case: {c['n']}", f"Citation: {c.get('cit') or ''}", f"Decided: {c.get('dec') or ''}", f"Docket: {c.get('d') or ''}"]
    pf = f"docs/data/parties/{c.get('t')}.js"
    if os.path.exists(pf):
        s = open(pf, encoding='utf-8').read()
        P = json.loads(s[s.index(',') + 1:-2]).get(c['id'])
        if P:
            if P.get('title'):
                lines.append('Docket title: ' + P['title'])
            for a in P.get('argued', []):
                lines.append(f"Argued by: {a['name']} ({a['desc']})")
    return '\n'.join(lines)


def generate(n):
    import anthropic                                   # pip install anthropic
    client = anthropic.Anthropic()
    st = load_store()
    q, _ = queue()
    done = 0
    for c in q:
        if done >= n:
            break
        if c['id'] in st:
            continue
        text = opinion_text(c)
        if len(text) < 2000:
            st[c['id']] = {'skip': 'no opinion text'}; save_store(st); continue
        if not still_no_summary(c):
            st[c['id']] = {'skip': 'Oyez has a summary'}; save_store(st); continue
        feedback = ''
        for attempt in range(2):
            try:
                resp = client.beta.messages.create(
                    model=MODEL, max_tokens=16000,
                    betas=['server-side-fallback-2026-07-01'], fallbacks='default',
                    output_config={'effort': 'medium', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
                    system=SYSTEM,
                    messages=[{'role': 'user', 'content': f'{context_for(c)}\n\n<opinion>\n{text}\n</opinion>\n\nWrite the case brief.{feedback}'}],
                )
            except anthropic.RateLimitError:
                time.sleep(60); continue
            except anthropic.APIStatusError as e:
                print('  API error', c['id'], e.status_code, flush=True); break
            if resp.stop_reason == 'refusal':
                print('  declined', c['id'], flush=True); break
            brief = json.loads(next(b.text for b in resp.content if b.type == 'text'))
            bad = check_quotes(brief, text)
            if not bad:
                brief.update({'model': resp.model, 'date': date.today().isoformat(), 'src': c['pdf']})
                st[c['id']] = brief; save_store(st); done += 1
                print('ok', c['id'], c['n'], flush=True)
                break
            feedback = '\n\nThese quotations were not found verbatim in the opinion; quote exactly or paraphrase without quotation marks: ' + ' | '.join(bad[:5])
        else:
            print('  quotes not verified, skipped', c['id'], flush=True)
    publish()


def import_file(path):
    st = load_store()
    new = json.load(open(path, encoding='utf-8'))
    S = {c['id']: c for c in load_js('docs/data/scotus.js')['cases']}
    for cid, brief in new.items():
        c = S[cid]
        bad = check_quotes(brief, opinion_text(c))
        if bad:
            print('REJECTED', cid, 'unverified quotations:', bad)
            continue
        brief.setdefault('date', date.today().isoformat())
        brief.setdefault('src', c['pdf'])
        st[cid] = brief
        print('imported', cid, c['n'])
    save_store(st)
    publish()


def publish():
    st = load_store()
    S = {c['id']: c for c in load_js('docs/data/scotus.js')['cases']}
    by_dec = collections.defaultdict(dict)
    for cid, b in st.items():
        if b.get('skip') or cid not in S:
            continue
        y = S[cid].get('y') or 0
        by_dec[str(y // 10 * 10)][cid] = {k: b[k] for k in FIELDS + ['model', 'date', 'src'] if b.get(k)}
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(f'{OUT}/*.js'):
        os.remove(f)
    for d, recs in by_dec.items():
        open(f'{OUT}/{d}.js', 'w', encoding='utf-8').write('window.AIBRIEFS=window.AIBRIEFS||{};Object.assign(window.AIBRIEFS,' + json.dumps(recs, ensure_ascii=False, separators=(',', ':')) + ');')
    open('docs/data/aibriefs-index.js', 'w', encoding='utf-8').write('window.AIBRIEFS_INDEX=' + json.dumps(sorted(by_dec), separators=(',', ':')) + ';')
    print('published', sum(len(v) for v in by_dec.values()), 'briefs in', len(by_dec), 'files')


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--queue':
        q, cites = queue()
        done = load_store()
        q = [c for c in q if c['id'] not in done]        # cases already briefed (or skipped) are not listed again
        n = int(a[1]) if len(a) > 1 else 40
        print(len(q), 'cases without a summary still to brief')
        for c in q[:n]:
            print(c['id'], '|', c['n'], '|', c.get('cit'), '|', c.get('dec'), '|', cites(c), 'citations')
    elif a[0] == '--fetch':
        q, _ = queue()
        done = load_store()
        q = [c for c in q if c['id'] not in done]
        for c in q[:int(a[1]) if len(a) > 1 else 40]:
            print(c['id'], len(opinion_text(c)), flush=True)
    elif a[0] == '--generate':
        generate(int(a[1]) if len(a) > 1 else 50)
    elif a[0] == '--import':
        import_file(a[1])
    elif a[0] == '--publish':
        publish()


if __name__ == '__main__':
    main()
