"""Scan every narrated section for proper names and unusual words, and verify each one's pronunciation before narration.

For each section (see narration_sections.py) the exact spoken text is tokenized. A word needs checking when it is
  - a proper name (capitalized away from the start of a sentence), or a sentence-initial word that is not an English word, or
  - a lowercase word that is not in the CMU Pronouncing Dictionary (Latin, legal terms of art, rare words).
Each is verified against, most trusted first:
  1. scripts/pronounce_manual.tsv and scripts/pronounce.tsv (Wikipedia / Wiktionary sourced, built by pronounce_build.py)
  2. the CMU Pronouncing Dictionary (Carnegie Mellon, BSD licence; data/raw/pron/cmudict/) - a name whose CMU
     pronunciation differs substantively from the voice engine's guess gets the CMU pronunciation
  3. Wiktionary, then Wikipedia (looked up live, cached in data/raw/pron/scan_*.json)
Words no source covers are left to the engine and listed in data/raw/pron/unverified.tsv.
Writes scripts/pronounce_scan.tsv (term, phonemes, source) and data/raw/pron/scan_report.tsv (one row per section).
Run from the repo root:  python scripts/pron_scan.py [guide doctrine conan]
"""
import collections, json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, 'scripts')
from narration_sections import sections
from narrate import speakable, sentences, fold
from pronounce_build import to_espeak, differs, lead_ipa, dist, bare

SRC = 'data/raw/pron'
UA = {'User-Agent': 'LexConstitutio-pronunciation-builder/1.0 (static site build script)'}
ARPA = {'AA': 'ɑː', 'AE': 'æ', 'AH': 'ʌ', 'AO': 'ɔː', 'AW': 'aʊ', 'AY': 'aɪ', 'EH': 'ɛ', 'ER': 'ɜː', 'EY': 'eɪ', 'IH': 'ɪ', 'IY': 'iː',
        'OW': 'oʊ', 'OY': 'ɔɪ', 'UH': 'ʊ', 'UW': 'uː', 'B': 'b', 'CH': 'tʃ', 'D': 'd', 'DH': 'ð', 'F': 'f', 'G': 'ɡ', 'HH': 'h', 'JH': 'dʒ',
        'K': 'k', 'L': 'l', 'M': 'm', 'N': 'n', 'NG': 'ŋ', 'P': 'p', 'R': 'ɹ', 'S': 's', 'SH': 'ʃ', 'T': 't', 'TH': 'θ', 'V': 'v', 'W': 'w',
        'Y': 'j', 'Z': 'z', 'ZH': 'ʒ'}
VOWEL_RE = re.compile(r'ɑː|æ|ʌ|ɔː|aʊ|aɪ|ɛ|ɜː|eɪ|ɪ|iː|i|oʊ|ɔɪ|ʊ|uː|ə|ɚ|ɐ|ᵻ|ɑ|ɔ|ɜ|a|e|o|u')


def arpa_to_espeak(arpa):
    out = []
    for p in arpa.split():
        m = re.match(r'([A-Z]+)([012])?$', p)
        base, st = m.group(1), m.group(2)
        if st is None:
            out.append(ARPA[base]); continue
        if base == 'AH' and st == '0': v = 'ə'
        elif base == 'ER' and st == '0': v = 'ɚ'
        elif base == 'IY' and st == '0': v = 'i'
        else: v = ARPA[base]
        out.append(('ˈ' if st == '1' else 'ˌ' if st == '2' else '') + v)
    return ''.join(out)


def syllables(ph):
    """(number of syllables, index of the primary-stressed syllable)"""
    toks = re.findall(r'ˈ|ˌ|' + VOWEL_RE.pattern, ph)
    n, primary = 0, None
    pending = None
    for t in toks:
        if t in 'ˈˌ':
            pending = t; continue
        if pending == 'ˈ' and primary is None:
            primary = n
        n += 1; pending = None
    return n, primary


def normv(p):
    p = bare(p)
    for a, b in (('ɐ', 'ə'), ('ᵻ', 'ɪ'), ('ɜ', 'ɚ'), ('ɾ', 't'), ('ɑ', 'a'), ('ɔ', 'o'), ('i', 'ɪ')):
        p = p.replace(a, b)
    return p


CONS_DROP = re.compile(r'[ˈˌːəɚɐᵻɪiɛæʌʊuɑɔɜaeoɒ ]')


def consonants(p):
    p = p.replace('ɾ', 't').replace('ʔ', 't').replace('n̩', 'n').replace('l̩', 'l')
    p = re.sub(r'j(?=ə|ɚ|ʊ|u)', '', p)          # "-nia" written n-jə vs n-iə
    p = re.sub(r'([ɚɜ]ː?)ɹ', r'', p).replace('ɹɹ', 'ɹ')   # the engine writes an r-coloured vowel plus an extra r
    p = p.replace('z', 's').replace('x', 'k')   # s/z voicing and final ch are not worth overriding
    return CONS_DROP.sub('', p)


def substantive(src, guess):
    """A difference a listener would hear: a different consonant, the stress on another syllable, or an extra syllable.
    Vowel-quality differences between the two notations (schwa vs. short i, etc.) are ignored."""
    norm = lambda p: re.sub(r'j(?=ə)', 'i', p)
    s1, s2 = syllables(norm(src)), syllables(norm(guess))
    if consonants(src) != consonants(guess):
        return True
    if s1[1] is not None and s2[1] is not None and s1[1] != s2[1]:
        return True
    return abs(s1[0] - s2[0]) >= 1 and dist(normv(src), normv(guess)) >= 2


def api(host, params):
    params.update(format='json', formatversion='2')
    url = f'https://{host}/w/api.php?' + urllib.parse.urlencode(params)
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(20 * (attempt + 1))
    return {}


def fetch_pages(titles, host, cache):
    path = f'{SRC}/{cache}'
    have = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    todo = [t for t in dict.fromkeys(titles) if t not in have]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = api(host, {'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main', 'redirects': 1, 'titles': '|'.join(batch)})
        q = d.get('query', {})
        alias = {x['from']: x['to'] for k in ('normalized', 'redirects') for x in q.get(k, [])}
        final = {p['title']: (p['revisions'][0]['slots']['main']['content'] if p.get('revisions') else None) for p in q.get('pages', [])}
        for t in batch:
            f = t
            for _ in range(3):
                f = alias.get(f, f)
            have[t] = [f, final.get(f)]
        json.dump(have, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'  {cache}: {min(i + 50, len(todo))}/{len(todo)}', flush=True)
        time.sleep(3)
    return have


def wiktionary_ipa(text, word):
    if not text or '==English==' not in text:
        return None
    eng = re.split(r'\n==[^=]', text.split('==English==', 1)[1])[0]
    pron = re.findall(r'.*\{\{IPA\|en\|[^}]*\}\}.*', eng)
    if not pron:
        return None
    us = [p for p in pron if re.search(r'(?:\{\{a(?:ccent)?\||\ba=)[^}]*\b(?:US|GA|GenAm)\b', p)]
    line = (us or pron)[0]
    args = [a for a in re.search(r'\{\{IPA\|en\|([^}]*)\}\}', line).group(1).split('|') if a.strip().startswith(('/', '['))]
    return args[0] if args else None


def main():
    from kokoro_onnx import Kokoro
    k = Kokoro('data/raw/tts/kokoro-v1.0.onnx', 'data/raw/tts/voices-v1.0.bin')
    vocab = set(k.tokenizer.vocab.keys())
    eg_cache = {}
    eg = lambda w: eg_cache.setdefault(w, k.tokenizer.phonemize(w, 'en-us').strip())

    lex = {}
    for f in ('scripts/pronounce.tsv', 'scripts/pronounce_manual.tsv'):
        if os.path.exists(f):
            for line in open(f, encoding='utf-8'):
                if line.strip() and not line.startswith('#'):
                    t, ph, *src = line.rstrip('\n').split('\t')
                    lex[t] = (ph, src[0] if src else f)
    lexl = {t.lower(): v for t, v in lex.items()}
    if os.path.exists(f'{SRC}/verified_same.tsv'):   # sourced words the engine already says correctly (from pronounce_build.py)
        for line in open(f'{SRC}/verified_same.tsv', encoding='utf-8'):
            t, src = line.rstrip('\n').split('\t')[:2]
            lex.setdefault(t, (None, src)); lexl.setdefault(t.lower(), (None, src))
    cmu = {}
    for line in open(f'{SRC}/cmudict/cmudict.dict', encoding='utf-8'):
        w, *ph = line.split(' #')[0].split()
        if '(' not in w:
            cmu.setdefault(w, ' '.join(ph))

    kinds = sys.argv[1:] or ['guide', 'doctrine', 'conan']
    secs = sections(kinds)
    lower_seen = set()
    occ = collections.defaultdict(lambda: {'n': 0, 'secs': set(), 'cap': False, 'name': False})
    per_sec = {}
    for s in secs:
        words = set()
        for par in s['paras']:
            for sent in sentences(re.sub(r'<[^>]+>', '', par)):
                toks = re.findall(r"[A-Za-z][A-Za-z'’]*", fold(speakable(sent)))
                for i, w in enumerate(toks):
                    w = re.sub(r"['’]s$|['’]$", '', w)
                    if len(w) < 2:
                        continue
                    if w.islower():
                        lower_seen.add(w)
                    elif w.isupper():
                        continue          # acronyms are spelled out by the engine
                    o = occ[w]; o['n'] += 1; o['secs'].add(s['id'])
                    if w[0].isupper():
                        o['cap'] = True
                        if i > 0: o['name'] = True
                    words.add(w)
        per_sec[s['id']] = words

    verified, additions, needs = {}, {}, set()
    for w, o in occ.items():
        lw = w.lower()
        if w in lex or (w.islower() and lw in lexl):
            verified[w] = lex.get(w, lexl.get(lw))[1]; continue
        if w.islower() or (o['cap'] and not o['name']):
            if lw in cmu or lw in lower_seen and w[0].isupper():
                verified[w] = 'English word'; continue
            if w[0].isupper() and lw in cmu:
                verified[w] = 'English word'; continue
        if o['name'] and lw in lower_seen and lw in cmu:
            verified[w] = 'English word'; continue      # capitalized ordinary word ("Court", "Brown" as a colour too)
        if lw in cmu:
            src = arpa_to_espeak(cmu[lw])
            verified[w] = 'CMU Pronouncing Dictionary'
            if o['name'] and len(w) > 3 and not re.search(r'(?:teenth|ieth|tion|tions|ist|ing)$', w) and substantive(src, eg(w)):
                additions[w] = (src, 'CMU Pronouncing Dictionary')
            continue
        needs.add(w)

    print(f'{len(occ)} distinct candidate words; verified offline {len(verified)}; to look up {len(needs)}', flush=True)
    wk = fetch_pages(sorted(needs | {w.lower() for w in needs if w[0].isupper()}), 'en.wiktionary.org', 'scan_wikt.json')
    still = set()
    for w in needs:
        ipa = None
        for t in ((w,) if occ[w]['name'] else (w, w.lower())):   # a name only matches an entry spelled the same way (not "trop" for Trop)
            title, text = wk.get(t, [None, None])
            ipa = wiktionary_ipa(text, t)
            if ipa:
                break
        if ipa:
            ph = to_espeak(ipa, vocab).replace(' ', '')
            if ph and dist(ph, eg(w)) / max(len(bare(ph)), 1) <= 0.9:
                verified[w] = f'Wiktionary: {title}'
                if differs(ph, eg(w)):
                    additions[w] = (ph, f'Wiktionary: {title}')
                continue
        still.add(w)
    caps = sorted(w for w in still if w[0].isupper())
    wp = fetch_pages(caps, 'en.wikipedia.org', 'scan_wiki.json')
    for w in caps:
        title, text = wp.get(w, [None, None])
        if not text:
            continue
        name, ipas = lead_ipa(text)
        if not ipas or not name:
            continue
        groups = to_espeak(ipas[0], vocab).split()
        names = [fold(x) for x in re.findall(r"[A-ZÀ-Ž][\w'’À-ž-]+", name)]
        if fold(w) not in names or not groups:
            continue
        g = groups[names.index(fold(w))] if len(groups) == len(names) else (groups[0] if len(groups) == 1 and len(names) == 1 else None)
        exact = title.split(',')[0].split(' (')[0] == w   # exact spelling, accents included (Konigsberg is not Königsberg)    # the page is about this very name ("Boerne" -> Boerne, Texas)
        if title.split(',')[0].split(' (')[0] != w and fold(title.split(',')[0].split(' (')[0]) == fold(w):
            continue
        if not g or (not exact and dist(g, eg(w)) / max(len(bare(g)), 1) > 0.75):
            continue
        verified[w] = f'Wikipedia: {title}'
        still.discard(w)
        if differs(g, eg(w)):
            additions[w] = (g, f'Wikipedia: {title}')

    with open('scripts/pronounce_scan.tsv', 'w', encoding='utf-8') as fh:
        fh.write('# Pronunciations verified by pron_scan.py (term, phonemes, source). pronounce.tsv and pronounce_manual.tsv take precedence.\n')
        for w in sorted(additions):
            fh.write(f'{w}\t{additions[w][0]}\t{additions[w][1]}\n')
    with open(f'{SRC}/unverified.tsv', 'w', encoding='utf-8') as fh:
        fh.write('word\toccurrences\tsections\tengine guess\n')
        for w in sorted(still, key=lambda x: -occ[x]['n']):
            fh.write(f"{w}\t{occ[w]['n']}\t{len(occ[w]['secs'])}\t{eg(w)}\n")
    with open(f'{SRC}/scan_report.tsv', 'w', encoding='utf-8') as fh:
        fh.write('section\tcandidates\tverified\tnew pronunciations\tunverified\tunverified words\n')
        for s in secs:
            ws = per_sec[s['id']]
            un = sorted(w for w in ws if w in still)
            fh.write(f"{s['id']}\t{len(ws)}\t{sum(1 for w in ws if w in verified)}\t{sum(1 for w in ws if w in additions)}\t{len(un)}\t{' '.join(un)}\n")
    src_count = collections.Counter(v.split(':')[0] for v in verified.values())
    print(f'verified {len(verified)} ({dict(src_count)}); new pronunciations {len(additions)}; unverified {len(still)}')


if __name__ == '__main__':
    main()
