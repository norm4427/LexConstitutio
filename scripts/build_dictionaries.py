"""Build the period-dictionary data: definitions of the words of the Constitution (and of the legal terms in the glossary
and the Originalist's Corner topics) from founding-era and early American dictionaries.

Sources, in date order (key: source):
  j   Samuel Johnson, A Dictionary of the English Language (1755). LEME transcription (Lexicons of Early Modern English,
      University of Toronto), CC BY 4.0: https://leme.library.utoronto.ca/lexicons/1345
  ba  Nathan Bailey and Joseph Nicol Scott, A New Universal Etymological English Dictionary (1755), the complete
      Bailey as revised by Scott. LEME transcription, CC BY 4.0: https://leme.library.utoronto.ca/lexicons/1346
  w   Noah Webster, An American Dictionary of the English Language (1828), public domain. Transcription from the
      webster1828 project (Akai Tsurugi, codeberg.org/akaitsurugi/webster1828), CC BY-SA 4.0; part-of-speech labels are
      spelled out ("noun") by that edition.
  b   John Bouvier, A Law Dictionary Adapted to the Constitution and Laws of the United States (6th ed., 1856), public
      domain; text from constitution.org.
  bu  Alexander M. Burrill, A Law Dictionary and Glossary (2nd ed., 1860), public domain. OCR of the Internet Archive scan
      (lawdictionar_burr_1860_00).
  bl  Henry Campbell Black, A Dictionary of Law (1st ed., 1891), public domain. OCR of the Internet Archive scan
      (blacks-law-dictionary-1891_202209, the cleaner of its two 1891 scans).
OCR-derived text (bu, bl) is repaired only mechanically: a word not found in the clean transcriptions is replaced
only when one standard OCR confusion turns it into a word that is found there, and an entry is cut at its first
sentence that still holds an unreadable word. The opening bracketed etymology of an OCR entry is dropped.

Writes docs/data/founding-dict.js (sources, Johnson, Webster and Bouvier, and multi-word terms from every source) and
docs/data/founding-dict-more.js (Bailey and the OCR law dictionaries bu/bl), loaded together by the word inspector and the
Companion. Raw files are downloaded to data/raw/dict/ on first run.
Run from the repo root after build_constitution.py and build_glossary.py:  python scripts/build_dictionaries.py
"""
import collections, csv, glob, html, json, os, re, sys, unicodedata, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fix_text import end_at_sentence  # noqa: E402

D = 'data/raw/dict'
STOP = set('the of and to a an in or be by for as at any such which that this it its on with from all each no not but if he his they their them there thereof have has been is are was were so than then other every one two three'.split())
IA = 'https://archive.org/download/'
RAW = {
    'scottbailey1755.txt': 'https://leme.library.utoronto.ca/plainText/lexicon1346.txt',
    'johnson1755.txt': 'https://leme.library.utoronto.ca/plainText/lexicon1345.txt',
    'webster1828.csv': 'https://codeberg.org/akaitsurugi/webster1828/raw/branch/master/webster1828.csv',
    'burrill1860.txt': IA + 'lawdictionar_burr_1860_00/lawdictionar_burr_1860_00_djvu.txt',
    'black1891.txt': IA + 'blacks-law-dictionary-1891_202209/Black%27s%20Law%20Dictionary%20%281891%29_djvu.txt',
}
RAW.update({f'bouvier/bouvier_{c}.htm': f'https://constitution.org/1-Constitution/bouv/bouvier_{c}.htm' for c in 'abcdefghijklmnopqrstuvwy'})

SRC = [  # key, short label, year, full citation and credit, kind
    ('j', 'Johnson', 1755, 'Samuel Johnson, A Dictionary of the English Language (1755); transcription by LEME, University of Toronto, CC BY 4.0', 'clean'),
    ('ba', 'Bailey', 1755, 'Nathan Bailey and Joseph Nicol Scott, A New Universal Etymological English Dictionary (1755); transcription by LEME, University of Toronto, CC BY 4.0', 'clean'),
    ('w', 'Webster', 1828, 'Noah Webster, An American Dictionary of the English Language (1828); transcription from the webster1828 project (Akai Tsurugi), CC BY-SA 4.0', 'clean'),
    ('b', 'Bouvier’s Law Dictionary', 1856, 'John Bouvier, A Law Dictionary Adapted to the Constitution and Laws of the United States (6th ed., 1856); public domain, text from constitution.org', 'clean'),
    ('bu', 'Burrill’s Law Dictionary', 1860, 'Alexander M. Burrill, A Law Dictionary and Glossary (2nd ed., 1860); OCR of the Internet Archive scan; shown only where the OCR reads cleanly, cut at the first garbled passage', 'ocr'),
    ('bl', 'Black’s Law Dictionary', 1891, 'Henry Campbell Black, A Dictionary of Law (1st ed., 1891); OCR of the Internet Archive scan; shown only where the OCR reads cleanly, cut at the first garbled passage', 'ocr'),
]
MORE_FILE = ('ba', 'bu', 'bl')         # written to founding-dict-more.js; the rest to founding-dict.js


def fetch_raw():
    for name, url in RAW.items():
        path = f'{D}/{name}'
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print('fetching', url)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (educational site; dictionary build)'})
        with urllib.request.urlopen(req, timeout=300) as r:
            open(path, 'wb').write(r.read())


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c))


def key(w):
    return re.sub(r'[^a-z]', '', fold(w).lower())


def pkey(p):
    """Key for a multi-word term: lower case, letters and single spaces."""
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z ]', ' ', fold(p).lower().replace('-', ' '))).strip()


VARIANT = {'chuse': 'choose', 'chusing': 'choosing', 'chosen': 'choose', 'controul': 'control', 'encreased': 'increased', 'erazure': 'erasure', 'compleat': 'complete',
           'defence': 'defense', 'offence': 'offense', 'offences': 'offense', 'behaviour': 'behavior', 'labour': 'labor', 'tranquility': 'tranquillity', 'born': 'bear',
           'held': 'hold', 'laid': 'lay', 'paid': 'pay', 'made': 'make', 'taken': 'take', 'given': 'give', 'chose': 'choose', 'bound': 'bind', 'thought': 'think', 'shewn': 'show'}


def lemmas(w):
    out = [w] + ([VARIANT[w]] if w in VARIANT else [])
    for suf, rep in (('ies', 'y'), ('ied', 'y'), ('es', ''), ('s', ''), ('ed', ''), ('ed', 'e'), ('ing', ''), ('ing', 'e'), ('ly', ''), ('d', ''), ("'s", '')):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            out.append(w[:-len(suf)] + rep)
    return list(dict.fromkeys(out))


def tidy(s, n=650):
    """Whitespace collapsed; text longer than n is shortened, at its last full sentence when one is near the end (as
    fix_text.py does), otherwise at a word with "…"."""
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else end_at_sentence(s[:n].rsplit(' ', 1)[0] + '…')


# ------------------------------------------------------------------ clean transcriptions
def parse_johnson():
    head = re.compile(r"^(?:To )?([A-Z][A-Z’'\-]+(?: [A-Z’'\-]+)?)\.? +(n\. ?s\.|v\. ?a\.|v\. ?n\.|adj\.|adv\.|n\.|v\.|prep\.|conj\.|interj\.|part\.|pron\.)(.*)$")
    out, cur = collections.defaultdict(list), None
    for line in open(f'{D}/johnson1755.txt', encoding='utf-8'):
        line = line.rstrip('\n').replace('­', '')
        m = head.match(line)
        if m:
            cur = [m.group(1), m.group(2), [m.group(3).strip()]]
            out[key(m.group(1))].append(cur)
        elif cur is not None:
            if not line.strip():
                cur = None
            else:
                cur[2].append(line.strip())
    return {k: [{'pos': pos, 't': tidy(' '.join(body).replace('­ ', ''))} for hw, pos, body in v] for k, v in out.items()}


def parse_bailey():
    """Scott-Bailey: paragraphs opening with a capitalized headword ("To RE’GULATE, verb act. [regulier, Fr. ...] to adjust
    by rule"). A headword followed by lower-case words before its comma or etymology ("MILITARY Execution, ...",
    "COMMERCE a Horse [...]") is a phrase."""
    text = open(f'{D}/scottbailey1755.txt', encoding='utf-8').read()
    text = re.sub(r'­\s*\n\s*', '', text)                      # soft hyphen at a line end
    start = text.find('\nA, in burlesque')
    text = text[start if start > 0 else 0:]
    out, phr = collections.defaultdict(list), collections.defaultdict(list)
    head = re.compile(r"^(?:To )?([A-Z][A-Z’'＇\-]+(?: [A-Z][A-Z’'＇\-]+)*)(.*)$", re.S)
    for para in re.split(r'\n\s*\n', text):
        para = re.sub(r'\s+', ' ', para).strip()
        m = head.match(para)
        if not m or len(para) < 12 or len(key(m.group(1))) < 2:
            continue
        hw, after = m.group(1), m.group(2)
        if re.match(r'\s*[,.\[]', after):
            out[key(hw)].append({'t': tidy(after.lstrip(' ,.'))})
            continue
        sub = re.match(r" ((?:[A-Za-z][a-z]*\.? ?){1,5}?)\s*(?=,|\[)", after)
        if sub:
            phr[pkey(hw + ' ' + sub.group(1))].append({'t': tidy(after[sub.end():].lstrip(' ,'))})
    return dict(out), phr


def webster_text(h):
    h = re.sub(r'</p>\s*<p>', ' ', h)
    return html.unescape(re.sub(r'<[^>]+>', '', h))


def parse_webster():
    """webster1828.csv: word, HTML definition. A row may hold several homographs, each opening <p><b>HEADWORD</b>, <i>pos</i>."""
    out = collections.defaultdict(list)
    csv.field_size_limit(10 ** 7)
    for row in csv.reader(open(f'{D}/webster1828.csv', encoding='utf-8', newline='')):
        if len(row) < 2:
            continue
        word, h = row[0], row[1]
        for part in re.split(r'(?=<p><b>[A-Z][^<]{0,40}</b>\s*,?\s*<i>)', h):
            if not part.strip():
                continue
            m = re.match(r'<p><b>([^<]+)</b>\s*,?\s*(?:<i>([^<]+)</i>)?', part)
            pos = (m.group(2) or '').strip() if m else ''
            body = part[m.end():] if m else part
            t = webster_text(body).strip(' ,')
            if len(t) > 3:
                out[key(word)].append({'pos': pos, 't': tidy(t, 700)})
    return out


def parse_bouvier():
    out = collections.defaultdict(list)
    for f in sorted(glob.glob(f'{D}/bouvier/*.htm')):
        s = open(f, encoding='latin-1').read()
        for m in re.finditer(r'<P>\s*<B>([^<]{2,60})</B>(.*?)(?=<P>\s*<B>|$)', s, re.S | re.I):
            term = html.unescape(m.group(1)).strip().rstrip(',.')
            body = html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2)))
            body = re.sub(r'^\s*[,.]\s*', '', body)
            out[term.lower()].append({'t': tidy(body, 900)})
    return out


# ------------------------------------------------------------------ OCR sources
OCR_SWAPS = [('cli', 'ch'), ('li', 'h'), ('rn', 'm'), ('ii', 'u'), ('iu', 'm'), ('ni', 'm'), ('in', 'm'), ('vv', 'w'), ('tl', 'th'), ('ai', 'a'), ('cil', 'ed'),
             ('il', 'd'), ('lil', 'bl'), ('tli', 'th'), ('fl', 'sh'), ('f', 's'), ('ft', 'st'), ('ff', 'ss'),
             ('mi', 'u'), ('m', 'rn'), ('h', 'li'), ('c', 'e'), ('e', 'c'), ('l', 'i'), ('i', 'l'), ('u', 'n'), ('n', 'u'), ('b', 'h'),
             ('h', 'b'), ('f', 't'), ('t', 'f'), ('o', 'e'), ('e', 'o'), ('a', 'o'), ('s', 'a'), ('1', 'l'), ('0', 'o'), ('3', 's'),
             ('5', 's'), ('I', 'l'), ('l', 'I'), ('j', 'y'), ('j', ''), (')', 'p'), ('/', 'f'), ('tt', 'to'), ('A', 'h'), ('r', 'n'), ('n', 'r'),
             ('z', 'r'), ('p', 'y'), ('l', 's'), ('k', 'f')]


def vocabulary(*srcs):
    v = collections.Counter()
    for src in srcs:
        for ents in src.values():
            for e in ents:
                v.update(w.lower() for w in re.findall(r'[A-Za-z]+', e['t']))
    return {w for w, n in v.items() if n >= 2}


def fix_word(w, V):
    """w itself if it is a known word; else the known word reached by one or two OCR swaps; else w."""
    core = w.strip("])(|/!'")
    lw = core.lower()
    if not re.search(r'[a-z]', lw) or lw in V or len(core) < 3:
        return w
    def swaps(x):
        for a, b in OCR_SWAPS:
            i = x.find(a)
            while i >= 0:
                yield x[:i] + b + x[i + len(a):]
                i = x.find(a, i + 1)
    def known(x):                       # x, or x after one OCR swap, if it is a known word
        if x.lower() in V:
            return x
        return next((c for c in swaps(x) if c.lower() in V), None)
    if core[:1].isupper():
        # a capitalized unknown word is left alone (names, Latin and French terms) unless it is two words run together
        m = re.match(r'(The|In|An|Of|To|It|And|A)([a-z]{3,})$', core)
        r = m and known(m.group(2))
        return f'{m.group(1)} {r}' if r else w
    for c1 in swaps(core):
        if c1.lower() in V:
            return c1
    for c1 in swaps(core):
        for c2 in swaps(c1):
            if c2.lower() in V:
                return c2
    if re.fullmatch(r'[a-z]{6,}', core):  # two words run together ("namedinit", "inthe")
        for i in range(len(core) - 2, 1, -1):
            a, b = core[:i], core[i:]
            if a in V and (len(a) > 2 or a in ('in', 'of', 'to', 'on', 'by', 'or', 'an', 'as', 'at', 'is', 'be', 'it')):
                r = known(b) if len(b) > 2 else (b if b in ('in', 'of', 'to', 'on', 'by', 'or', 'an', 'as', 'at', 'is', 'be', 'it') else None)
                if r:
                    return f'{a} {r}'
    return w


SHORT = set('a i v q c s p n f b l r e d m t x ad am an as at be by do ex go he if in is it me my no of oh on or so to up us we ch pp ed co id de et eo ab re vs sc ib ff st nd rd th'.split())


def clean_ocr(t, V):
    """The clean run from the start of an OCR definition, or ''."""
    t = t.replace('�', ' ').replace('|', ' ').replace('ſ', 's')
    t = re.sub(r'[*†‡]', '', t)                                     # footnote marks
    t = re.sub(r'\(\s*\d+\s*\)\s*[A-Z]{2,4}\b', ' ', t)                 # running page header: "( 332 ) COM"
    t = re.sub(r'\s+', ' ', t).strip(' ,.')
    # the opening language label and bracketed etymology ("L. Lat. [from ad, to, and ponere, to put.) In old practice. ...")
    m = re.match(r'(?:(?:[A-Z][a-z]{0,3}\.\s?){1,2}(?:and (?:[A-Z][a-z]{0,3}\.\s?)+)?\s*)?[\[(][^\])}]{0,300}[\])}]\.?\s*', t)
    if m:
        t = t[m.end():]
    t = re.sub(r"[A-Za-z0-9^\])(/!']+", lambda m: fix_word(m.group(0), V), t)
    t = re.sub(r'\s+([;,:.])', r'\1', t)
    t = t.replace('q. v.', 'q.\x00v.')                              # keep "(q. v.)" in one sentence
    keep = []
    for s in re.split(r'(?<=[.;?!])\s+(?=[A-Z0-9(])', t):
        toks = re.findall(r"[A-Za-z0-9^\])(/!'’]+\.?", s)
        words = [x.strip("'’") for x in toks]
        junk = [x for x in words if re.search(r'[\^\]\[/!]|[a-z][A-Z]|[a-z]j$|^[a-z]+[0-9]|[0-9][a-z]', x.rstrip('.'))]
        unknown = [x for i, x in enumerate(words) if re.fullmatch(r'[A-Za-z]{3,}', x) and x.lower() not in V
                   and not (i and re.fullmatch(r'[A-Z][a-z]{2,11}', x))]      # a name, but not as the sentence's first word
        unknown += [x for x in words if re.fullmatch(r'[a-z]{1,2}', x) and x not in SHORT]   # "bow nda", "ine close und"
        if words and not junk and not unknown and not re.search(r'[<>\\*•■]|&;|[^\x00-\x7f’‘“”—–§æœÆŒéèêàâçüöäëï]', s):
            keep.append(s)
        else:
            break
    out = re.sub(r'\s+', ' ', ' '.join(keep)).strip().replace('\x00', ' ')
    out = re.sub(r'\s+[^A-Za-z\s]*\d+\.?$', '', out)
    if out and not re.search(r'[.;:)]$', out):
        out = out[:out.rfind('.') + 1] if '.' in out else out
    if not re.match(r'(?:1\. )?[A-Z(][a-z A-Z]', out) or re.match(r'[A-Z]{2,}', out) or re.match(r'(?:See|Vide|Hence|Fr|Lat|Sax|L|Gr)\b', out):
        return ''
    body = re.sub(r'^(?:(?:L\. )?(?:Lat|Fr|Sax|Eng|Sc|Gr)\.\s*|In [^.]{0,40}\.\s*)+', '', out)   # more than a language or field label
    if len(body) < 25 or len(re.findall(r'\b[a-z]{3,}\b', body)) < 4:
        return ''
    return out


def alpha_chain(ms):
    """Headwords run in alphabetical order: keep the longest run of candidate heads whose first three letters never go
    backwards, which drops lines that only look like headwords (citations, cross-references, OCR noise)."""
    import bisect
    keys = [key(m.group(1))[:3] for m in ms]
    tails, tail_i, parent = [], [], [-1] * len(ms)
    for i, k in enumerate(keys):
        j = bisect.bisect_right(tails, k)
        if j == len(tails):
            tails.append(k); tail_i.append(i)
        else:
            tails[j] = k; tail_i[j] = i
        parent[i] = tail_i[j - 1] if j else -1
    out, i = [], tail_i[-1] if tail_i else -1
    while i >= 0:
        out.append(ms[i]); i = parent[i]
    return out[::-1]


def caps_heads(text, start_rx):
    """Entries of a dictionary whose headwords are set in capitals at the start of a line ("ATTAINDER. That ...")."""
    i = re.search(start_rx, text, re.M)
    text = text[i.start():] if i else text
    text = re.sub(r'(\w)-\s*\n\s*[‘’\'"]?(?=[a-z])', r'\1', text)
    text = re.sub(r'([A-Z])- ?\n\s*(?=[A-Z])', r'\1', text)            # a capitalized headword broken across lines
    text = re.sub(r'[ \t]{2,}', ' ', text)
    head = re.compile(r"^[^A-Za-z\n]{0,3}([A-Z][A-Z'’\-]+(?:,? (?:[A-Z][A-Z'’\-]+|OF|IN|AND|THE|TO|DE|AD))*)[.,] +(?=[\[(A-Z])", re.M)
    ents = []
    good = alpha_chain([m for m in head.finditer(text) if len(key(m.group(1))) >= 2])
    for i, m in enumerate(good):
        end = good[i + 1].start() if i + 1 < len(good) else m.end() + 4000
        ents.append((m.group(1), text[m.end(): min(end, m.end() + 4000)]))
    return ents


def norm_head(hw):
    """'ATTAINDER, BILL OF' -> 'bill of attainder'; 'LETTERS OF MARQUE' -> 'letters of marque'."""
    h = pkey(hw.replace('’', "'"))
    m = re.match(r'([a-z ]+?), ([a-z ]+ (?:of|in|to))$', hw.lower())
    if m:
        h = pkey(m.group(2) + ' ' + m.group(1))
    return h


def build_ocr(ents, V):
    words, phr = collections.defaultdict(list), collections.defaultdict(list)
    for hw, body in ents:
        t = clean_ocr(body, V)
        if not t:
            continue
        h = norm_head(hw)
        e = {'t': tidy(t)}
        (phr[h] if ' ' in h else words[key(h)]).append(e)
    return words, phr


# ------------------------------------------------------------------ word lists
def terms_to_cover(text):
    """Distinct words of the Constitution, plus single words and phrases from the glossary terms and the Corner topics."""
    words = {w.lower() for w in re.findall(r"[A-Za-z]+(?:'[a-z]+)?", text)} - STOP
    extra, phrases = set(), set()
    try:
        G = json.loads(open('docs/data/glossary.js', encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
        gl = list(G['terms'])
    except Exception:
        gl = []
    try:
        C = json.loads(open('docs/data/corner.js', encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
        topics = [p for t in C['topics'] for p in re.split(r'\s*(?:&|,| and )\s*', t['name'])]
    except Exception:
        topics = []
    for t in gl + topics:
        p = pkey(t)
        if ' ' in p:
            phrases.add(p)
        for w in p.split():
            if w not in STOP and len(w) > 2:
                extra.add(w)
    phrases |= set(CURATED)
    return sorted(words), sorted(extra - words), phrases


CURATED = ['letters of marque', 'letters of marque and reprisal', 'bill of attainder', 'attainder', 'ex post facto', 'natural born', 'natural born subject',
           'natural born citizen', 'privileges and immunities', 'due process of law', 'law of the land', 'habeas corpus', 'eminent domain', 'police power',
           'full faith and credit', 'general welfare', 'cruel and unusual punishment', 'corruption of blood', 'high crimes and misdemeanors', 'misdemeanor',
           'good behaviour', 'good behavior', 'bills of credit', 'legal tender', 'standing army', 'trial by jury', 'grand jury', 'common law', 'law of nations',
           'writ of habeas corpus', 'probable cause', 'just compensation', 'public use', 'religious test', 'establishment of religion', 'free exercise',
           'freedom of speech', 'liberty of the press', 'freedom of the press', 'right of petition', 'search warrant', 'general warrant', 'double jeopardy',
           'speedy trial', 'excessive bail', 'capitation tax', 'direct tax', 'poll tax', 'impairing the obligation of contracts', 'obligation of contracts',
           'commerce among the several states', 'post roads', 'post office', 'high seas', 'piracy', 'felony', 'treason', 'aid and comfort', 'overt act',
           'impeachment', 'pardon', 'reprieve', 'veto', 'quorum', 'naturalization', 'bankruptcy', 'copyright', 'patent', 'militia', 'posse comitatus',
           'seditious libel', 'social compact', 'natural law', 'natural rights', 'separation of powers', 'judicial review', 'stare decisis', 'precedent',
           'state of nature', 'republican government', 'standing armies', 'quartering of soldiers', 'title of nobility', 'titles of nobility', 'emolument']


# ------------------------------------------------------------------ main
def pick(src, w, single=True):
    for lm in lemmas(w):
        k = key(lm) if single else lm
        if k in src and src[k]:
            return {'hw': lm, 'e': src[k][:2]}
    return None


def pnorm(p):
    """Match key for a multi-word term: singular forms ("letters of marque" ~ "letter of marque")."""
    return ' '.join(w[:-1] if len(w) > 4 and w.endswith('s') and not w.endswith('ss') else w for w in p.split())


BOUVIER_FIX = {'bill op attainder': 'bill of attainder', 'letter of marque and reprrisal': 'letter of marque and reprisal'}   # typos in the transcription's headwords


def main():
    fetch_raw()
    c = json.loads(open('docs/data/constitution.js', encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
    text = ' '.join(u['text'] for u in c['units'])
    low = ' ' + pnorm(' '.join(pkey(text).split())) + ' '
    words, extra, want = terms_to_cover(text)
    wantn = {pnorm(p) for p in want}
    J = parse_johnson()
    BA, BAP = parse_bailey()
    W = parse_webster()
    B = parse_bouvier()
    V = vocabulary(J, B, W, BA)
    rx = r'^A\.\s+(?:Lat\.\s+)?The (?:first )?letter'
    BU, BUP = build_ocr(caps_heads(open(f'{D}/burrill1860.txt', encoding='utf-8', errors='replace').read(), rx), V)
    BL, BLP = build_ocr(caps_heads(open(f'{D}/black1891.txt', encoding='utf-8', errors='replace').read(), rx), V)
    print(f'parsed headwords: Johnson {len(J)}, Bailey {len(BA)} (+{len(BAP)} phrases), Webster {len(W)}, Bouvier {len(B)}, '
          f'Burrill {len(BU)} (+{len(BUP)}), Black {len(BL)} (+{len(BLP)})')
    single = {'j': J, 'ba': BA, 'w': W, 'bu': BU, 'bl': BL}
    Bw = {k: v for k, v in B.items() if ' ' not in k}
    out, miss = {}, []
    for w in words + extra + sorted(t for t in want if ' ' not in t):
        rec = {s: r for s, src in single.items() for r in [pick(src, w)] if r}
        r = pick(Bw, w, single=False)
        if r:
            rec['b'] = r
        if rec:
            out[w] = rec
        elif w in words:
            miss.append(w)
    # multi-word terms: any dictionary term found in the Constitution's text, plus the glossary, Corner and curated terms
    multi = {'ba': BAP, 'b': {BOUVIER_FIX.get(pkey(k), pkey(k)): v for k, v in B.items() if ' ' in k}, 'bu': BUP, 'bl': BLP}
    skip = {'new hampshire', 'new jersey', 'new york', 'north carolina', 'south carolina', 'rhode island', 'for that', 'no bill', 'in chief', 'post facto',
            'to constitute', 'to declare', 'to execute', 'to have', 'to hold', 'to make', 'to pass'}
    phrases = {}
    for s, src in multi.items():
        for term, ents in src.items():
            n = pnorm(term)
            if term in skip or len(term) <= 6 or not ents or re.match(r'(?:of|in|the|to|by|for|and|or)\b', term):
                continue
            if n in wantn or f' {n} ' in low:
                phrases.setdefault(n, {}).setdefault(s, {'hw': term, 'e': ents[:2]})
    # a phrase is shown under the form people search for: the Constitution's or the wanted wording when there is one
    named = {pnorm(p): p for p in sorted(want)}
    phrases = {named.get(n, next((v['hw'] for v in r.values()), n)): r for n, r in phrases.items()}
    order = [s[0] for s in SRC]
    srcmeta = {k: {'label': lab, 'year': y, 'cite': cite, 'ocr': kind == 'ocr'} for k, lab, y, cite, kind in SRC}
    split = lambda rec, more: {s: rec[s] for s in order if s in rec and (s in MORE_FILE) == more}
    core = {w: v for w, v in ((w, split(r, False)) for w, r in out.items()) if v}
    more = {w: v for w, v in ((w, split(r, True)) for w, r in out.items()) if v}
    ph = {p: {s: v[s] for s in order if s in v} for p, v in sorted(phrases.items())}
    data = {'order': order, 'src': {k: m['cite'] for k, m in srcmeta.items()}, 'meta': srcmeta, 'words': core, 'phrases': ph}
    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
    open('docs/data/founding-dict.js', 'w', encoding='utf-8').write('window.FOUNDING_DICT=' + dump(data) + ';')
    open('docs/data/founding-dict-more.js', 'w', encoding='utf-8').write('window.FOUNDING_DICT_MORE=' + dump({'words': more}) + ';')
    cw = set(words)
    cov = lambda k: sum(1 for w, v in out.items() if w in cw and k in v)
    print(f'{len(words)} distinct Constitution words; defined {sum(1 for w in out if w in cw)}: ' + ', '.join(f'{lab} {cov(k)}' for k, lab, *_ in SRC))
    print(f'{len(extra)} glossary/Corner words, defined {sum(1 for w in extra if w in out)}; {len(ph)} phrases: ' +
          ', '.join(f'{lab} {sum(1 for v in ph.values() if k in v)}' for k, lab, *_ in SRC))
    print('Constitution words with no entry:', miss)
    print('wanted phrases with no entry:', sorted(p for p in want if ' ' in p and p not in ph))
    for f in ('founding-dict', 'founding-dict-more'):
        print(f, os.path.getsize(f'docs/data/{f}.js') // 1024, 'KB')


if __name__ == '__main__':
    main()
