"""Repair text problems in the site data (run after any build step; safe to re-run):
  1. mojibake: UTF-8 text that was read as Windows-1252 somewhere upstream ("â€¦" for "…", "â€™" for "’", "Ã©" for "é"),
     repaired run by run in every docs/data/*.js file
  2. truncated abstracts: an article abstract that stops mid-sentence (the source cut it off) gets an ellipsis
  3. not-abstracts: JSTOR citation lines ("..., Harvard Law Review, Vol. 112, No. 4 (Feb., 1999), pp. 988-993") and tables
     of contents scraped as abstracts are dropped (the page then says no abstract is available); an abstract that
     starts with the article's own title has the title removed
Run from the repo root:  python scripts/fix_text.py
"""
import glob, json, re

# a run of characters that cp1252-encodes to valid multi-byte UTF-8
CP = 'ÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ'
CONT = '\u0080-¿€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ'
RUN = re.compile(f'[{CP}][{CONT}]{{1,3}}(?:[{CP}][{CONT}]{{1,3}})*')


CITE_LINE = re.compile(r'Vol\. \d+, No\. [\w/-]+.*\((?:[A-Z][a-z]{2,4}\.?,? )?(?:[A-Z][a-z]+ )?\d{4}\), pp?\. [\d-]+\s*$')
TOC = re.compile(r'TABLE OF CONTENTS|^INTRODU ?CTION \d|\.{4,} ?\d{2,4}\b')


def unmojibake(s):
    def fix(m):
        t = m.group(0)
        try:
            return t.encode('cp1252').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return t
    return RUN.sub(fix, s)


PLAIN_KEYS = {'ab', 't', 'q', 'ds', 'h', 'n', 'blurb', 'intro', 'note', 'title', 'a', 'd', 's', 'l'}   # fields shown as plain text
ENT = {'&apos;': '’', '&#39;': '’', '&quot;': '"', '&amp;': '&', '&nbsp;': ' ', '&lt;': '<', '&gt;': '>'}


def tidy(s, key):
    """small cleanups for every string, plus a few for plain-text fields."""
    s = s.replace('​', '').replace('﻿', '')
    s = re.sub(r'(?<=[A-Za-z])�(?=s\b)', '’', s)        # Alfieri�s -> Alfieri’s
    s = re.sub(r'(?<=\s)�(?=\w)', '“', s).replace('�', '”')
    s = re.sub(r'\b(the|from|of|to|and|in|on) \1\b', r'\1', s)  # doubled small words
    s = re.sub(r'\b(Court|Justice|Sandra|John|William) \1\b', r'\1', s)   # doubled words seen in the sources
    if key in PLAIN_KEYS:
        for e, r in ENT.items():
            s = s.replace(e, r)
        if key in ('q', 'ds', 'h'):
            s = re.sub(r'^<p>\s*|\s*</p>$', '', s)
        s = re.sub(r'(?<=[\w’”)]) ([,;])(?= )', r'\1', s)      # "Tigard , simply" -> "Tigard, simply"
        if key == 't':
            s = re.sub(r'(?<=\w) ([?!])(?=\s|$)', r'\1', s)       # "the New Usery ?" -> "the New Usery?"
    if key == 'ds':
        # Oyez summaries that dropped the verb: "A case in which the Court that ..." / "... the Court the Sixth Amendment ..."
        s = re.sub(r'^(A case (?:that|in which) the Court) that\s+', r'\1 held that ', s)
        s = re.sub(r'^(A case (?:that|in which) the Court) (?=(?:the|a|an|he|she|both|[A-Z][a-z]+’s)\b)', r'\1 held that ', s)
    return s


def walk(x, fn, key=None):
    if isinstance(x, str):
        return fn(x, key)
    if isinstance(x, list):
        return [walk(v, fn, key) for v in x]
    if isinstance(x, dict):
        return {k: walk(v, fn, k) for k, v in x.items()}
    return x


def main():
    total = 0
    for path in sorted(glob.glob('docs/data/*.js')):
        raw = open(path, encoding='utf-8').read()
        m = re.match(r'(window\.[A-Z_0-9]+=)(.*?)(;?\s*)$', raw, re.S)
        if not m:
            continue
        try:
            data = json.loads(m.group(2))
        except json.JSONDecodeError:
            continue
        changed = [0]

        def fn(s, key):
            t = tidy(unmojibake(s), key)
            if t != s:
                changed[0] += 1
            return t
        data = walk(data, fn)
        ell = drop = 0
        if path.endswith('articles.js'):
            for a in data.get('articles', []):
                ab = (a.get('ab') or '').rstrip()
                if ab and (CITE_LINE.search(ab) or TOC.search(ab[:400])):
                    a['ab'] = ''
                    drop += 1
                    continue
                t = (a.get('t') or '').strip()
                if t and len(t) > 15 and ab.startswith(t) and len(ab) > len(t) + 40:
                    ab = ab[len(t):].lstrip(' .:—-')
                    a['ab'] = ab
                # stops on a letter, comma, colon, semicolon or dash: the source cut it off mid-sentence
                if ab and re.search(r'[A-Za-z,;:\-–—]$', ab) and len(ab) > 200:
                    a['ab'] = re.sub(r'[,;:\-–—\s]+$', '', ab) + '…'
                    ell += 1
        if changed[0] or ell or drop:
            open(path, 'w', encoding='utf-8').write(m.group(1) + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
            print(f'{path}: {changed[0]} strings repaired' + (f', {ell} abstracts given an ellipsis, {drop} citation lines or tables of contents dropped' if ell or drop else ''))
            total += changed[0]
    print(f'done ({total} strings repaired)')


if __name__ == '__main__':
    main()
