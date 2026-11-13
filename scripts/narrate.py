"""Narrate text with Kokoro (open-weight TTS, Apache 2.0) and write an MP3 plus a sentence-timing JSON.

Usage (library):  from narrate import Narrator; Narrator().render(paragraphs, 'out/name', voice='af_heart')
Writes out/name.mp3 and out/name.json  -> {"voice":..., "dur": seconds, "s": [[start, end, paragraphIndex, sentenceText], ...]}
Requires: pip install kokoro-onnx soundfile ; ffmpeg on PATH ; model files in data/raw/tts/
"""
import html, json, os, re, subprocess, tempfile, unicodedata
import numpy as np
import soundfile as sf

MODEL = 'data/raw/tts/kokoro-v1.0.onnx'
VOICES = 'data/raw/tts/voices-v1.0.bin'
ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS = 'zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()


def two(n):
    if n < 20:
        return ONES[n]
    return TENS[n // 10] + ('' if n % 10 == 0 else '-' + ONES[n % 10])


def year_words(y):
    y = int(y)
    hi, lo = divmod(y, 100)
    if 2000 <= y <= 2009:
        return 'two thousand' + ('' if lo == 0 else ' ' + ONES[lo])
    if lo == 0:
        return two(hi) + ' hundred'
    if lo < 10:
        return two(hi) + ' oh ' + ONES[lo]
    return two(hi) + ' ' + two(lo)


def paren(m):
    """Citation parentheticals: drop bare years, read case lists as 'as in A and B'."""
    inner = m.group(1).strip()
    if re.fullmatch(r'(?:\d{4}|\d+(?:st|nd|rd|th)? Cir\.? \d{4})', inner):
        return ''
    if ';' in inner or re.search(r'\bv\.\s|^[A-Z][\w.\'-]+(?: [A-Z][\w.\'-]+)*(?:, \d{4})?$', inner):
        inner = re.sub(r',\s*\d{4}\b', '', inner)
        parts = [x.strip() for x in inner.split(';') if x.strip()]
        joined = parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]
        return ', as in ' + joined + ','
    return ', ' + inner + ','


def speakable(text):
    t = html.unescape(re.sub(r'<[^>]+>', '', text))
    t = re.sub(r'\[\d+\]', '', t)
    t = re.sub(r'\s*\(([^()]{1,200})\)', paren, t)
    t = re.sub(r',?\s*\b\d+\s+(?:U\.\s?S\.|S\.\s?Ct\.|L\.\s?Ed\.(?:\s?2d)?|F\.(?:\s?[234]d|\s?Supp\.)?)\s+\d+(?:,\s*\d+)?', '', t)  # reporter citations aren't read aloud
    t = re.sub(r'\bv\.\s', 'versus ', t)
    t = re.sub(r'§§\s*', 'Sections ', t)
    t = re.sub(r'§\s*', 'Section ', t)
    t = re.sub(r'\be\.g\.,?', 'for example,', t)
    t = re.sub(r'\bi\.e\.,?', 'that is,', t)
    t = re.sub(r'\bArt\.\s', 'Article ', t)
    t = re.sub(r'\bcl\.\s', 'clause ', t)
    t = re.sub(r'\bAmend\.\s', 'Amendment ', t)
    t = re.sub(r'\bNo\.\s(?=\d)', 'Number ', t)
    t = re.sub(r'\b(Mr|Mrs|Ms|Dr|St|Jr|Inc|Co|Corp|Ltd|Bros)\.', r'\1', t)
    # periods inside abbreviations become pauses in the voice engine: U.S. -> US, N.A.A.C.P. -> NAACP, Susan B. Anthony -> Susan B Anthony
    t = re.sub(r'\b((?:[A-Z]\.\s?){2,})', lambda m: m.group(1).replace('.', '').replace(' ', '') + ' ', t)
    t = re.sub(r'\b([A-Z])\.\s(?=[A-Z])', r'\1 ', t)
    t = re.sub(r'(?<![\d,])\b(1[6-9]\d\d|20\d\d)\b(?![\d,])', lambda m: year_words(m.group(1)), t)
    t = t.replace('—', ', ').replace('–', ' to ').replace('“', '"').replace('”', '"').replace('’', "'")
    t = re.sub(r'\s+([,.;:])', r'\1', t)
    t = re.sub(r',\s*,', ',', t)
    t = re.sub(r',(\s*[.;:!?])', r'\1', t)
    return re.sub(r'\s+', ' ', t).strip()


ABBREV = re.compile(r'(?:\b(?:v|U\.S|[A-Z]|Mr|Ms|Mrs|Dr|St|Co|Inc|Jr|No|Art|cl|Amend|Corp|Bros|Ltd|Ct|Cir|ed|al|Id|id))\.$')


def sentences(par):
    """Split a paragraph at sentence ends, skipping legal and name abbreviations."""
    out, start = [], 0
    for m in re.finditer(r'[.!?]["\')\]]?\s+(?=["(\[]?[A-Z0-9])', par):
        head = par[start:m.start() + 1]
        if m.group(0)[0] == '.' and ABBREV.search(head):
            continue
        out.append(par[start:m.end()].strip())
        start = m.end()
    out.append(par[start:].strip())
    return [p for p in out if p]


LEXICON = 'scripts/pronounce.tsv'


def fold(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t) if not unicodedata.combining(c))


class Narrator:
    def __init__(self):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(MODEL, VOICES)
        self.sr = 24000
        self.lex = {}
        if os.path.exists(LEXICON):
            for line in open(LEXICON, encoding='utf-8'):
                if line.strip() and not line.startswith('#'):
                    term, ph = line.rstrip('\n').split('\t')[:2]
                    self.lex[term if term[0].isupper() else term.lower()] = ph
        names = sorted((t for t in self.lex if t[0].isupper()), key=len, reverse=True)
        terms = sorted((t for t in self.lex if not t[0].isupper()), key=len, reverse=True)
        alts = [re.escape(t) for t in names] + ['(?i:' + re.escape(t) + ')' for t in terms]
        self.lex_re = re.compile(r"(?<![\w'-])(" + '|'.join(alts) + r")('s)?(?![\w-])") if alts else None

    def phonemes(self, spoken, lang='en-us'):
        """espeak phonemes for the sentence, with sourced pronunciations spliced in for lexicon words."""
        spoken = fold(spoken)
        if not self.lex_re:
            return self.k.tokenizer.phonemize(spoken, lang)
        out, pos = [], 0
        for m in self.lex_re.finditer(spoken):
            if m.start() > pos:
                out.append(self.k.tokenizer.phonemize(spoken[pos:m.start()], lang).strip())
            w = m.group(1)
            ph = self.lex.get(w) or self.lex[w.lower()]
            if m.group(2):
                ph += 'ɪz' if re.search(r'(s|z|ʃ|ʒ|tʃ|dʒ)$', ph) else ('s' if re.search(r'[ptkfθ]$', ph) else 'z')
            out.append(ph)
            pos = m.end()
        if pos < len(spoken):
            out.append(self.k.tokenizer.phonemize(spoken[pos:], lang).strip())
        return re.sub(r'\s+([,.;:!?])', r'\1', ' '.join(x for x in out if x))

    def render(self, paragraphs, out_base, voice='af_heart', speed=1.0, lang='en-us'):
        chunks, timeline, t = [], [], 0.0
        sent_gap = np.zeros(int(self.sr * 0.28), dtype=np.float32)
        para_gap = np.zeros(int(self.sr * 0.65), dtype=np.float32)
        for pi, par in enumerate(paragraphs):
            for s in sentences(html.unescape(re.sub(r'<[^>]+>', '', par))):
                spoken = speakable(s)
                if not re.search(r'[A-Za-z0-9]', spoken):
                    continue
                audio, sr = self.k.create(self.phonemes(spoken, lang), voice=voice, speed=speed, lang=lang, is_phonemes=True)
                audio = audio.astype(np.float32)
                dur = len(audio) / sr
                timeline.append([round(t, 2), round(t + dur, 2), pi, re.sub(r'<[^>]+>', '', html.unescape(s))])
                chunks += [audio, sent_gap]
                t += dur + len(sent_gap) / sr
            chunks.append(para_gap)
            t += len(para_gap) / self.sr
        wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
        os.makedirs(os.path.dirname(out_base) or '.', exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            tmp = os.path.join(td, 'n.wav')
            sf.write(tmp, wav, self.sr)
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp, '-ac', '1', '-codec:a', 'libmp3lame', '-b:a', '64k', out_base + '.mp3'], check=True)
        with open(out_base + '.json', 'w', encoding='utf-8') as fh:
            json.dump({'voice': voice, 'dur': round(len(wav) / self.sr, 2), 's': timeline}, fh, ensure_ascii=False)
        return len(wav) / self.sr
