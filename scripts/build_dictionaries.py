"""Build docs/data/founding-dict.js: definitions of the words in the Constitution from period dictionaries.

  Johnson   Samuel Johnson, A Dictionary of the English Language (1755). Transcription from Lexicons of Early Modern
            English (LEME, University of Toronto), CC BY 4.0: data/raw/dict/johnson1755.txt
  Webster   Noah Webster, An American Dictionary of the English Language (1828), public domain. OCR text of the
            Internet Archive scans (americandictiona01/02websrich); may contain OCR errors.
  Bouvier   John Bouvier, A Law Dictionary, Adapted to the Constitution and Laws of the United States (6th ed. 1856),
            public domain; text from constitution.org. Includes multi-word legal terms ("ex post facto").
Only words (and Bouvier phrases) that occur in the Constitution are kept.
Run from the repo root after build_constitution.py:  python scripts/build_dictionaries.py
"""
import collections, glob, html, json, re, unicodedata

D = 'data/raw/dict'
STOP = set('the of and to a an in or be by for as at any such which that this it its on with from all each no not but if he his they their them there thereof have has been is are was were so than then other every one two three'.split())


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c))


def key(w):
    return re.sub(r'[^a-z]', '', fold(w).lower())


VARIANT = {'chuse': 'choose', 'chusing': 'choosing', 'chosen': 'choose', 'controul': 'control', 'encreased': 'increased', 'erazure': 'erasure', 'compleat': 'complete', 'defence': 'defence'}


def lemmas(w):
    out = [w] + ([VARIANT[w]] if w in VARIANT else [])
    for suf, rep in (('ies', 'y'), ('ied', 'y'), ('es', ''), ('s', ''), ('ed', ''), ('ed', 'e'), ('ing', ''), ('ing', 'e'), ('ly', ''), ('d', ''), ("'s", '')):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            out.append(w[:-len(suf)] + rep)
    return list(dict.fromkeys(out))


def tidy(s, n=650):
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else s[:n].rsplit(' ', 1)[0] + '…'


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


def parse_webster():
    text = ''
    for v in ('americandictiona01websrich', 'americandictiona02websrich'):
        text += open(f'{D}/{v}.txt', encoding='utf-8', errors='replace').read() + '\n'
    text = re.sub(r'-\s*\n\s*', '', text)          # rejoin words hyphenated across lines
    head = re.compile(r"^([A-Z][A-Z'\"’\-]{1,}(?:, [A-Z][A-Z'\-]+)*), +(n|v\. ?t|v\. ?i|v|a|adv|prep|conj|ppr|pp|pron|part|exclam)\.(.*)$", re.M)
    out = collections.defaultdict(list)
    ms = list(head.finditer(text))
    for i, m in enumerate(ms):
        body = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else m.end() + 3000][:3000]
        body = re.sub(r'\s{2,}', ' ', (m.group(3) + ' ' + body).replace('\n', ' '))
        hw = m.group(1).split(',')[0]
        out[key(hw)].append({'pos': m.group(2), 't': tidy(body)})
    return out


# Webster OCR repair. The scans' OCR garbles letters ("macliine", "himian", "Ivlongs") and mangles the Greek and other
# scripts in the etymologies. The repairs are mechanical: the bracketed etymology that opens an entry is dropped; a word
# not found in the clean Johnson and Bouvier transcriptions is replaced only when one standard OCR confusion turns it
# into a word that is found there; and a sentence still holding unreadable words is cut.
OCR_SWAPS = [('cli', 'ch'), ('li', 'h'), ('rn', 'm'), ('ii', 'u'), ('iu', 'm'), ('ni', 'm'), ('in', 'm'), ('vv', 'w'), ('tl', 'th'),
             ('mi', 'u'), ('m', 'rn'), ('h', 'li'), ('c', 'e'), ('e', 'c'), ('l', 'i'), ('i', 'l'), ('u', 'n'), ('n', 'u'), ('b', 'h'),
             ('h', 'b'), ('f', 't'), ('t', 'f'), ('o', 'e'), ('e', 'o'), ('a', 'o'), ('s', 'a'), ('1', 'l'), ('0', 'o'), ('3', 's'),
             ('5', 's'), ('Iv', 'be'), ('I', 'l'), ('l', 'I'), ('j', 'y'), ('j', ''), ('])', 'p'), (')', 'p'), ('/', 'f'), ('tt', 'to'), ('A', 'h')]


def vocabulary(J, B):
    v = collections.Counter()
    for src in (J, B):
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
    for c1 in swaps(core):
        if c1.lower() in V:
            return c1
    for c1 in swaps(core):
        for c2 in swaps(c1):
            if c2.lower() in V:
                return c2
    return w


def clean_webster(t, V):
    t = t.replace('�', ' ')
    end = t.find(']')
    if 0 <= end < 900 and (t.startswith('[') or '[' not in t[:end]):
        t = t[end + 1:]                 # the opening etymology (sometimes its "[" fell on the headword line)
    t = re.sub(r"[A-Za-z0-9^\])(|/!']+", lambda m: fix_word(m.group(0), V), t)
    t = re.sub(r'\s+([;,:])', r'\1', t)
    t = re.split(r"\s[A-Z]{3,}['A-Z]*\b(?!\.)", t)[0]          # the next headword ("HIMS", "NINTH, n.") ran into this one
    keep = []
    for s in re.split(r'(?<=[.;?!])\s+(?=[A-Z0-9])', t.strip()):
        toks = re.findall(r"[A-Za-z0-9^\])(|/!']+", s)
        words = [x.strip("'") for x in toks]
        junk = [x for x in words if re.search(r'[\^\]\[|/!]|[a-z][A-Z]|[a-z]j$|^[a-z]+[0-9]|[0-9][a-z]', x)]
        unknown = [x for x in words if re.fullmatch(r'[A-Za-z]{3,}', x) and x.lower() not in V and not x.isupper()]
        if words and not junk and not unknown and not re.search(r'[^\x00-\x7f’‘“”—–]|[<>\\*]|&;|\s1 [a-z]', s):
            keep.append(s)
        else:
            break                       # keep only the clean run from the start of the definition
    out = re.sub(r'\s+', ' ', ' '.join(keep)).strip()
    out = re.sub(r'\s+[^A-Za-z\s]*\d+\.$', '', out)                           # a dangling sense number
    if not re.search(r'[.;:)]$', out):
        out = out[:out.rfind('.') + 1] if '.' in out else out               # a sentence cut off by the next headword
    # it must open as a definition: "1. ...", or a capitalized word that is not a citation, cross-reference or stray headword
    if not re.match(r'(?:1\. )?[A-Z][a-z]', out) or re.match(r'(?:Hence|Lev|Matt|Gen|Ex|Rut|See|It|Fr|Sax|L|Gr|Sp|D)\b', out):
        return ''
    return out if len(out) >= 30 else ''


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


def main():
    c = json.loads(open('docs/data/constitution.js', encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
    text = ' '.join(u['text'] for u in c['units'])
    words = sorted({w.lower() for w in re.findall(r"[A-Za-z]+(?:'[a-z]+)?", text)} - STOP)
    J, W, B = parse_johnson(), parse_webster(), parse_bouvier()
    print(f'parsed: Johnson {len(J)} headwords, Webster {len(W)}, Bouvier {len(B)} terms')
    V = vocabulary(J, B)
    for k in list(W):
        ents = [dict(e, t=tidy(c)) for e in W[k] for c in [clean_webster(e['t'].rstrip('…'), V)] if c]
        if ents:
            W[k] = ents
        else:
            del W[k]
    out, miss = {}, []
    for w in words:
        rec = {}
        for name, src in (('j', J), ('w', W)):
            for lm in lemmas(w):
                if key(lm) in src:
                    rec[name] = {'hw': lm, 'e': src[key(lm)][:2]}; break
        for lm in lemmas(w):
            if lm in B:
                rec['b'] = {'hw': lm, 'e': B[lm][:2]}; break
        if rec:
            out[w] = rec
        else:
            miss.append(w)
    low = text.lower()
    phrases = {}
    skip = {'new hampshire', 'new jersey', 'new york', 'north carolina', 'south carolina', 'rhode island', 'for that', 'no bill', 'in chief', 'post facto'}
    for term, ents in B.items():
        if term in skip:
            continue
        if ' ' in term and len(term) > 6 and re.search(r'\b' + re.escape(term) + r'\b', low):
            phrases[term] = {'hw': term, 'e': ents[:2]}
    data = {'src': {'j': 'Samuel Johnson, A Dictionary of the English Language (1755); transcription by LEME, University of Toronto, CC BY 4.0',
                    'w': 'Noah Webster, An American Dictionary of the English Language (1828); OCR of the Internet Archive scans; only entries whose OCR reads cleanly are shown, cut at the first garbled passage',
                    'b': 'John Bouvier, A Law Dictionary Adapted to the Constitution and Laws of the United States (6th ed., 1856)'},
            'words': out, 'phrases': phrases}
    open('docs/data/founding-dict.js', 'w', encoding='utf-8').write('window.FOUNDING_DICT=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    cov = lambda k: sum(1 for v in out.values() if k in v)
    print(f'{len(words)} distinct words; defined {len(out)} (Johnson {cov("j")}, Webster {cov("w")}, Bouvier {cov("b")}); phrases {len(phrases)}: {sorted(phrases)[:30]}')
    print('no entry:', miss[:60])


if __name__ == '__main__':
    main()
