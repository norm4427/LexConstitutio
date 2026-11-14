"""Build scripts/pronounce.tsv, the narration pronunciation lexicon, from the sources cached by pronounce_fetch.py.

- Names: the IPA given in the lead of each Wikipedia page, matched to the name word it belongs to. Sources, most trusted
  first: the party's own page (linked from the case article) and the justices' pages; the case article itself
  (e.g. Regents v. Bakke gives /ˈbɑːki/); other pages for people with the same surname (e.g. "Lujan" -> Ben Ray Luján, /luːˈhɑːn/).
- Terms: Wiktionary's English pronunciation, preferring the US / General American one.
Only words used in the narrated text are kept, and only where the voice engine's own guess differs from the source.
Entries in scripts/pronounce_manual.tsv (term <TAB> phonemes <TAB> note) override everything.
Output columns: term, phonemes (the voice engine's espeak-style IPA), source.
Run from the repo root:  python scripts/pronounce_build.py
"""
import collections, html, itertools, json, re, sys, unicodedata

SRC = 'data/raw/pron'
VOWELS = set('aeiouæɑɒɔəɚɛɜɪʊʌɐᵻɨʉɵy')
# Wikipedia / Wiktionary English IPA -> espeak en-us symbols (longest match first)
MAP = {
    'aɪər': 'aɪɚ', 'aʊər': 'aʊɚ', 'jʊər': 'jʊɹ', 'ɔɪər': 'ɔɪɚ',
    'ɪər': 'ɪɹ', 'ɛər': 'ɛɹ', 'ʊər': 'ʊɹ', 'ɑːr': 'ɑːɹ', 'ɔːr': 'ɔːɹ', 'ɜːr': 'ɜː', 'ɪəɹ': 'ɪɹ', 'ɛəɹ': 'ɛɹ', 'ʊəɹ': 'ʊɹ', 'ɑːɹ': 'ɑːɹ', 'ɔːɹ': 'ɔːɹ', 'ɜːɹ': 'ɜː',
    'ɑr': 'ɑːɹ', 'ɔr': 'ɔːɹ', 'ɜr': 'ɜː', 'ər': 'ɚ', 'əɹ': 'ɚ', 'ɪr': 'ɪɹ', 'ɛr': 'ɛɹ', 'ʊr': 'ʊɹ', 'ɝ': 'ɜː', 'ɚ': 'ɚ',
    'oɹ': 'ɔːɹ', 'or': 'ɔːɹ', 'ɔɪ': 'ɔɪ', 'aɪ': 'aɪ', 'aʊ': 'aʊ', 'ɑː': 'ɑː', 'ɔː': 'ɔː', 'ɜː': 'ɜː', 'iː': 'iː', 'uː': 'uː', 'oi': 'ɔɪ', 'əʊ': 'oʊ', 'ɒ': 'ɑː', 'ɑ': 'ɑː', 'ɔ': 'ɔː',
    'r': 'ɹ', 'g': 'ɡ', 'x': 'k', 'ɫ': 'l', 'ʍ': 'w', 'ɵ': 'oʊ', 'ɨ': 'ᵻ', 'ʉ': 'uː', 'e': 'eɪ', 'o': 'oʊ', "'": 'ˈ', ',': 'ˌ',
}
MAP_KEYS = sorted(MAP, key=len, reverse=True)
# ASCII stand-ins that {{IPAc-en}} accepts for its tokens
ASCII_IPA = {'@': 'ə', '@r': 'ər', 'S': 'ʃ', 'Z': 'ʒ', 'T': 'θ', 'D': 'ð', 'N': 'ŋ', 'tS': 'tʃ', 'dZ': 'dʒ', 'a:': 'ɑː', 'A:': 'ɑː', 'a:r': 'ɑːr',
             'ei': 'eɪ', 'ai': 'aɪ', 'au': 'aʊ', 'ou': 'oʊ', 'oi': 'ɔɪ', 'i:': 'iː', 'u:': 'uː', 'O:': 'ɔː', 'O:r': 'ɔːr', 'E': 'ɛ', 'I': 'ɪ',
             'U': 'ʊ', 'V': 'ʌ', '3:': 'ɜː', '3:r': 'ɜːr', '{': 'æ', 'Q': 'ɒ', 'Ir': 'ɪər', 'Er': 'ɛər', 'Ur': 'ʊər'}


def to_espeak(ipa, vocab):
    s = unicodedata.normalize('NFC', ipa)
    s = re.sub(r'\([^)]*\)', '', s)                       # optional sounds, e.g. (j)
    s = re.sub(r'[/\[\]\.ˑ‿̯̩͡ʰ]', '', s).replace('_', ' ')
    s = s.replace('eɪ', '\x01').replace('oʊ', '\x02')     # protect diphthongs from the single e/o mapping
    s = re.sub(r'[rɹ](?=[ˈˌ]?[aeiouæɑɒɔəɛɜɪʊʌɐ\x01\x02])', '\x03', s)
    s = re.sub(r'([ɛɪʊ])ə(?=\x03)', r'\1', s)   # an r before a vowel stays a consonant (Moreno, not "Mo-er-eeno")
    out, i = '', 0
    while i < len(s):
        for k in MAP_KEYS:
            if s.startswith(k, i):
                out += MAP[k]; i += len(k); break
        else:
            out += s[i]; i += 1
    out = out.replace('\x01', 'eɪ').replace('\x02', 'oʊ').replace('\x03', 'ɹ').replace('ːː', 'ː')
    # espeak puts the stress mark right before the vowel; Wikipedia puts it before the syllable
    res, pending = [], ''
    for ch in out:
        if ch in 'ˈˌ':
            pending = ch
        elif pending and ch in VOWELS:
            res.append(pending + ch); pending = ''
        elif ch == ' ' and pending:
            res.append(' '); pending = ''
        else:
            res.append(ch)
    out = ''.join(res)
    out = out.replace(':', 'ː')
    # phoneme symbols only: no capitals or punctuation, which the engine reads as letters or pauses
    out = ''.join(ch for ch in out if ch == ' ' or (ch in vocab and not ch.isupper() and ch not in '!"(),.:;?—“”…→↓↗↘'))
    return re.sub(r'\s+', ' ', out).strip()


def bare(p):
    return re.sub(r'[ˈˌː ]', '', p)


def differs(src, guess):
    """True when the source pronunciation differs from the engine's guess in sounds or in where the stress falls."""
    norm = lambda p: re.sub(r'\s', '', p.replace('ˌ', 'ˈ'))
    return norm(src) != norm(guess)


def dist(a, b):
    a, b = bare(a), bare(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fold(w):
    return ''.join(c for c in unicodedata.normalize('NFD', w) if not unicodedata.combining(c))


def lead_ipa(text):
    """IPA strings from a page lead, with the bolded name they follow."""
    lead = re.sub(r'<!--.*?-->', '', text.split('\n==')[0], flags=re.S)
    lead = re.sub(r'\{\{(?:Short description|Infobox|Use |About|Other|For|Redirect|pp|Distinguish|good article|featured)[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}', '', lead, flags=re.I | re.S)
    m = re.search(r"'''(.+?)'''", lead)
    if not m:
        return None, []
    name = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', m.group(1))
    after = lead[m.end():m.end() + 600]
    out = []
    for t in re.finditer(r'\{\{\s*(IPAc-en|IPA-en|IPA)\s*\|([^{}]*)\}\}', after):
        kind, args = t.group(1), [a.strip() for a in t.group(2).split('|')]
        if kind == 'IPAc-en':
            toks = [a for a in args if a and '=' not in a and not re.fullmatch(r'(?:US|UK|pron|icon|lang|local|also|Can|Aus|NZ|Eng|Irl|Sco|GA|RP)', a)]
            out.append(''.join(ASCII_IPA.get(a, a) for a in toks))
        elif kind == 'IPA-en':
            out.append(args[0])
        else:
            if args and args[0] == 'en' and len(args) > 1:
                out.append(args[1])
            elif args and args[0].startswith('/'):
                out.append(args[0])
        break   # the first pronunciation given is the one for the name
    return name, out


def main():
    from kokoro_onnx import Kokoro
    k = Kokoro('data/raw/tts/kokoro-v1.0.onnx', 'data/raw/tts/voices-v1.0.bin')
    vocab = set(k.tokenizer.vocab.keys())
    espeak = {}

    def eg(w):
        if w not in espeak:
            espeak[w] = k.tokenizer.phonemize(w, 'en-us').strip()
        return espeak[w]

    corpus = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', open(f'docs/data/{x}.js', encoding='utf-8').read())) for x in ['guide', 'advanced', 'commentary'])
    cap_words = collections.Counter(re.findall(r"\b[A-Z][\w'-]+\b", corpus))
    low_words = set(re.findall(r'\b[a-z][a-z]+\b', corpus))
    # name words used in the narration: case parties and justices, not ordinary English words
    case_words = set()
    for f in ('cases.json', 'corpus_cases.json'):
        for n in json.load(open(f'{SRC}/{f}', encoding='utf-8')):
            case_words |= set(re.findall(r"[A-Z][\w'-]+", n))
    justices = set(json.load(open(f'{SRC}/justices.json', encoding='utf-8')))
    people = json.load(open(f'{SRC}/people_wiki.json', encoding='utf-8'))
    for j in justices:
        case_words |= {w for w in re.findall(r"[A-Z][\w'-]+", j) if cap_words[w]}
    wanted = {w for w in case_words if cap_words[w] and w.lower() not in low_words and len(w) > 2 and w not in ('The', 'United', 'States')}
    wanted_fold = {fold(w): w for w in wanted}

    cands = collections.defaultdict(list)   # word -> [(phonemes, source, priority)]
    import os
    sources = [(people, 3)]
    for f, pri in (('cases_wiki.json', 2), ('surname_wiki.json', 1)):
        if os.path.exists(f'{SRC}/{f}'):
            sources.append((json.load(open(f'{SRC}/{f}', encoding='utf-8')), pri))
    pages = [(req, title, text, pri) for src, pri in sources for req, (title, text) in src.items() if text]
    for req, title, text, base in pages:
        name, ipas = lead_ipa(text)
        if not ipas or not name:
            continue
        groups = to_espeak(ipas[0], vocab).split()
        words = [w for w in re.findall(r"[A-ZÀ-Ž][\w'’À-ž-]+", name) if w not in ('Jr', 'Sr', 'II', 'III', 'IV')]
        if not groups or not words or len(groups) > len(words):
            continue
        if base == 1:
            # same-surname pages: only people's pages ("First Last"), and a lone IPA group must be the title's surname
            tw = re.findall(r"[A-ZÀ-Ž][\w'’À-ž-]+", title)
            if re.search(r'[,(]', title) or not 2 <= len(title.split()) <= 4 or not tw:
                continue
            if len(groups) == 1:
                best1 = min(words, key=lambda x: dist(eg(fold(x)), groups[0]))
                if fold(best1) != fold(tw[-1]):
                    continue
                words = [best1]
        best = None
        for combo in itertools.combinations(range(len(words)), len(groups)):
            score = sum(dist(eg(fold(words[i])), g) / max(len(bare(g)), 1) for i, g in zip(combo, groups))
            if best is None or score < best[0]:
                best = (score, combo)
        for i, g in zip(best[1], groups):
            w = fold(words[i]).replace('’', "'")
            if w not in wanted_fold:
                continue
            ratio = dist(eg(w), g) / max(len(bare(g)), 1)
            if ratio > (0.75 if base > 1 else 0.6):        # too far from the spelling: probably the wrong word
                continue
            if base == 1 and w not in fold(title):
                continue
            if len(bare(g)) > 1.6 * len(bare(eg(w))) + 2:   # IPA covers more than this word (e.g. "Coeur d'Alene")
                continue
            pri = base
            cands[wanted_fold[w]].append((g, f'Wikipedia: {title}', pri))

    lex, same = {}, {}   # same: sourced words the engine already says correctly (recorded for pron_scan.py)
    for w, lst in cands.items():
        top = max(lst, key=lambda x: (x[2], sum(1 for y in lst if y[0] == x[0])))
        if differs(top[0], eg(w)):
            lex[w] = (top[0], top[1])
        else:
            same[w] = top[1]

    # Wiktionary terms
    terms = json.load(open(f'{SRC}/terms_wikt.json', encoding='utf-8'))
    for req, (title, text) in terms.items():
        if not text or '==English==' not in text:
            continue
        eng = text.split('==English==', 1)[1]
        eng = re.split(r'\n==[^=]', eng)[0]
        pron = re.findall(r'.*\{\{IPA\|en\|[^}]*\}\}.*', eng)
        if not pron:
            continue
        us = [p for p in pron if re.search(r'(?:\{\{a(?:ccent)?\||\ba=)[^}]*\b(?:US|GA|GenAm)\b', p)]
        rhotic = [p for p in pron if re.search(r'[ɹrɚɝ]', p)]
        line = (us or (rhotic if 'r' in req else []) or pron)[0]
        args = [a for a in re.search(r'\{\{IPA\|en\|([^}]*)\}\}', line).group(1).split('|') if a.strip().startswith(('/', '['))]
        if not args:
            continue
        ph = to_espeak(args[0], vocab)
        if not ph or not any(c in VOWELS for c in ph):
            continue
        if ph and req.lower() in corpus.lower() and differs(ph, eg(req)):
            lex[req] = (ph, f'Wiktionary: {title}')
        elif ph:
            same[req] = f'Wiktionary: {title}'

    # manual overrides win
    try:
        for line in open('scripts/pronounce_manual.tsv', encoding='utf-8'):
            if line.strip() and not line.startswith('#'):
                parts = line.rstrip('\n').split('\t')
                if parts[1].strip() == '-':      # "-" = keep the voice engine's own pronunciation
                    lex.pop(parts[0], None)
                else:
                    lex[parts[0]] = (parts[1], 'manual' + (': ' + parts[2] if len(parts) > 2 and parts[2] else ''))
    except FileNotFoundError:
        pass

    with open('scripts/pronounce.tsv', 'w', encoding='utf-8', newline='\n') as o:
        o.write('# term\tphonemes\tsource   (generated by scripts/pronounce_build.py; edit scripts/pronounce_manual.tsv instead)\n')
        for w in sorted(lex, key=str.lower):
            o.write(f'{w}\t{lex[w][0]}\t{lex[w][1]}\n')
    with open(f'{SRC}/verified_same.tsv', 'w', encoding='utf-8', newline='\n') as o:
        for w in sorted(same, key=str.lower):
            o.write(f'{w}\t{same[w]}\n')
    print(f'{len(lex)} entries ({sum(1 for v in lex.values() if v[1].startswith("Wikipedia"))} names, '
          f'{sum(1 for v in lex.values() if v[1].startswith("Wiktionary"))} terms, {sum(1 for v in lex.values() if v[1].startswith("manual"))} manual)')
    for w in sys.argv[1:]:
        print(f'  {w}: espeak {eg(w)}  ->  {lex.get(w, ("(no entry)", ""))[0]}  {lex.get(w, ("", ""))[1]}')


if __name__ == '__main__':
    main()
