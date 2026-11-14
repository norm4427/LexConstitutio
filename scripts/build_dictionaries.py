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
                    'w': 'Noah Webster, An American Dictionary of the English Language (1828); OCR of the Internet Archive scans, may contain errors',
                    'b': 'John Bouvier, A Law Dictionary Adapted to the Constitution and Laws of the United States (6th ed., 1856)'},
            'words': out, 'phrases': phrases}
    open('docs/data/founding-dict.js', 'w', encoding='utf-8').write('window.FOUNDING_DICT=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
    cov = lambda k: sum(1 for v in out.values() if k in v)
    print(f'{len(words)} distinct words; defined {len(out)} (Johnson {cov("j")}, Webster {cov("w")}, Bouvier {cov("b")}); phrases {len(phrases)}: {sorted(phrases)[:30]}')
    print('no entry:', miss[:60])


if __name__ == '__main__':
    main()
