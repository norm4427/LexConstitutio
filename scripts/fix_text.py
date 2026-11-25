"""Repair text problems in the site data (run after any build step; safe to re-run):
  1. mojibake: UTF-8 text that was read as Windows-1252 somewhere upstream ("â€¦" for "…", "â€™" for "’", "Ã©" for "é"),
     repaired run by run in every docs/data/*.js file
  2. truncated abstracts: an article abstract that stops mid-sentence (the source cut it off) gets an ellipsis
  3. not-abstracts: JSTOR citation lines ("..., Harvard Law Review, Vol. 112, No. 4 (Feb., 1999), pp. 988-993") and tables
     of contents scraped as abstracts are dropped (the page then says no abstract is available); an abstract that
     starts with the article's own title has the title removed
  4. excerpts of longer sources (founding-era passages, early statutes, library documents) lose scraped attributions and
     page navigation glued to their ends, and one that stops mid-sentence is marked with an ellipsis
  5. a book "description" that only repeats the title is dropped; one cut mid-word ends at a sentence or whole word
  6. dictionary entries and flashcard backs shortened mid-sentence end at their last full sentence when one is near
Run from the repo root:  python scripts/fix_text.py
"""
import glob, json, os, re

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


TYPOS = {   # garbled words in source summaries, fixed wherever they appear
    'the are not police allowed': 'the police are not allowed',
    '"freedom contract"': '"freedom of contract"',
}
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
    for a, b in TYPOS.items():
        s = s.replace(a, b)
    if key == 'ds':
        # Oyez summaries that dropped the verb: "A case in which the Court that ..." / "... the Court the Sixth Amendment ..."
        s = re.sub(r'^(A case (?:that|in which) the Court) that\s+', r'\1 held that ', s)
        s = re.sub(r'^(A case (?:that|in which) the Court) (?=(?:the|a|an|he|she|both|[A-Z][a-z]+’s)\b)', r'\1 held that ', s)
    return s


HLR = 'https://harvardlawreview.org/'
MOVED = {   # Harvard Law Review PDFs on its retired cdn.harvardlawreview.org host (now a Cloudflare DNS error) -> the article's
            # page on harvardlawreview.org, found with the site's own search and matched by title and volume
    'cdn.harvardlawreview.org/wp-content/uploads/2015/06/vol128_Schauer.pdf': HLR + 'forum/vol-128/out-of-range-on-patently-covered-speech/',
    'cdn.harvardlawreview.org/wp-content/uploads/2015/11/vol129_Lazarus.pdf': HLR + 'forum/vol-129/back-to-business-at-the-supreme-court-the-administrative-side-of-chief-justice-roberts/',
    'cdn.harvardlawreview.org/wp-content/uploads/2015/06/vol128_CalebNelson.pdf': HLR + 'forum/vol-128/avoiding-constitutional-questions-versus-avoiding-unconstitutionality/',
    'cdn.harvardlawreview.org/wp-content/uploads/pdfs/vol126_karlan.pdf': HLR + 'print/vol-126/democracy-and-disdain/',
    'cdn.harvardlawreview.org/wp-content/uploads/pdfs/skowronek.pdf': HLR + 'print/vol-122/the-conservative-insurgency-and-presidential-power-a-developmental-perspective-on-the-unitary-executive/',
    'cdn.harvardlawreview.org/wp-content/uploads/pdfs/schauer.pdf': HLR + 'print/vol-120/the-courts-agenda-ae-and-the-nations/',
}

CONTINUES = {   # file -> keys of source passages that are excerpts of longer texts (shown with an ellipsis if cut mid-sentence)
    'corner.js': {'t'}, 'constitution.js': {'t'}, 'statutes.js': {'p'},
}
WHOLE_TEXTS = {   # complete documents shown paragraph by paragraph: a paragraph ending in a comma continues in the next one, so
    'library-documents.js': {'paras'}, 'library-statutes.js': {'paras'}, 'library-federalist.js': {'paras'},   # junk only
}


def tidy_excerpt(s, mark=True):
    """a passage cut from a longer source: drop scraped attributions and page navigation glued to its end, then mark a
    passage that stops mid-sentence ("... the State is therefore left to fix these qualifica-") with an ellipsis."""
    t = re.sub(r'\s*"[^"]{3,90}," in Wikipedia, the Free Encyclopedia\.?$', '', s.rstrip())
    t = re.sub(r'(?<=[.;:])\s+(?:Back|Next|Previous|Top|Return to [\w ]+)$', '', t)
    if mark and len(t) > 80 and re.search(r'[A-Za-z0-9,\-–—(]$', t):
        t = re.sub(r'\s+\S+-$', '', t)                      # a word broken at the source's line end
        t = re.sub(r'[\s,;:\-–—(]+$', '', t) + ' …'
    return t


SENTENCE_END = {'founding-dict.js': {'t'}, 'founding-dict-more.js': {'t'}, 'flashcards.js': {'f', 'b'}}   # plus every fc-court-*.js deck: {'f', 'b'}


def end_at_sentence(s):
    """text shortened to a fixed length and ended with "…" mid-sentence: end it at its last full sentence when one is
    near the end (within the last 45%), so it reads as complete."""
    if not s.endswith('…'):
        return s
    body = s[:-1].rstrip()
    ends = [m.end() for m in re.finditer(r'(?<!\bv)(?<!\b[A-Z])(?<!\bNo)(?<!\bSt)(?<!\bMr)(?<!\bJ)(?<!\bU\.S)[.!?]["”’)]?(?=\s)', body)]
    return body[:ends[-1]] if ends and ends[-1] > 0.55 * len(body) else s


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

        cont = CONTINUES.get(os.path.basename(path), set())
        whole = WHOLE_TEXTS.get(os.path.basename(path), set())
        sent = SENTENCE_END.get(os.path.basename(path)) or ({'f', 'b'} if os.path.basename(path).startswith('fc-court-') else set())

        def fn(s, key):
            t = tidy(unmojibake(s), key)
            if key in cont:
                t = tidy_excerpt(t)
            elif key in whole:
                t = tidy_excerpt(t, mark=False)
            if key in sent:
                t = end_at_sentence(t)
            if t != s:
                changed[0] += 1
            return t
        data = walk(data, fn)
        ell = drop = 0
        if path.endswith('books.js'):       # a "description" that is only the book's title repeated is not a description
            nrm = lambda x: re.sub(r'\W+', ' ', x or '').strip().lower()
            for b in data.get('books', []):
                bl = b.get('blurb')
                if not bl:
                    continue
                if nrm(bl) in nrm(b.get('title')) or (nrm(b.get('title')) in nrm(bl) and len(bl) < len(b.get('title', '')) + 25):
                    b.pop('blurb'); changed[0] += 1
                    continue
                # a description cut at a fixed length mid-word ("... of polit…"): end it at its last full sentence, or at
                # least at a whole word
                if bl.endswith('…') and re.search(r'[A-Za-z]…$', bl):
                    body = bl[:-1]
                    ends = [m.end() for m in re.finditer(r'[.!?]["”’)]?(?=\s)', body)]
                    cut = body[:ends[-1]] if ends and ends[-1] > 0.5 * len(body) else re.sub(r'\s+\S*$', '', body).rstrip(',;:—– ') + ' …'
                    if cut != bl:
                        b['blurb'] = cut; changed[0] += 1
        if path.endswith('articles.js'):
            for a in data.get('articles', []):
                for k in ('u', 'pdf', 'oa'):
                    v = re.sub(r'^https?://', '', a.get(k) or '')
                    if v in MOVED:
                        a[k] = MOVED[v]; changed[0] += 1
                    elif v.startswith('cdn.harvardlawreview.org/'):     # a retired address not yet mapped: don't show a dead link
                        print('  unmapped dead link', a['id'], a[k])
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
