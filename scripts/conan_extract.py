"""Extract essays from the Constitution Annotated (CRS / Library of Congress, GPO 2022 edition; public domain).

Uses font sizes to keep only body text: body is 10pt, footnotes 8pt, reference marks ~5-6.5pt, running
headers 9-9.5pt. Essay headings are bold 10pt lines holding an essay ID (e.g. ArtIII.S2.C1.6.4.2) followed
by a bold title line. Italic spans (case names) are kept as <em>.

Usage: python scripts/conan_extract.py   ->  data/conan_essays.json
Requires: pip install pymupdf
"""
import glob, html, json, re
import pymupdf

ID_RX = re.compile(r'^(?:Art[IVX]+(?:\.S\d+)?(?:\.C\d+)?|Amdt\d+(?:\.S\d+)?|Intro|Preamble)(?:\.\d+)*$')
LABEL_RX = re.compile(r'^(Article [IVX]+(, Section \d+)?(, Clause \d+)?|[A-Z][a-z]+(-[A-Z]?[a-z]+)? Amendment(, Section \d+)?|Preamble):\s*$')
RUNNING_RX = re.compile(r'^(ARTICLE [IVX]+|[A-Z\-]+ AMENDMENT|PREAMBLE|INTRODUCTION)\b')


def line_info(line):
    spans = [s for s in line['spans'] if s['text'].strip()]
    if not spans:
        return None
    total = sum(len(s['text']) for s in spans)
    size = max(spans, key=lambda s: len(s['text']))['size']
    text = ''.join(s['text'] for s in spans).strip()
    bold = sum(len(s['text']) for s in spans if 'Bold' in s['font']) > total / 2
    italic = sum(len(s['text']) for s in spans if 'Italic' in s['font']) > total * 0.9
    body = []
    for s in line['spans']:
        if s['size'] < 9.6:          # footnote reference marks and small text
            continue
        t = html.escape(s['text'])
        body.append(f'<em>{t}</em>' if 'Italic' in s['font'] and t.strip() else t)
    return dict(text=text, size=size, bold=bold, italic=italic, x0=line['bbox'][0], html=''.join(body))


def main():
    essays, order = {}, []
    files = sorted(glob.glob('data/raw/conan/g*.pdf'), key=lambda f: int(re.search(r'g(\d+)', f).group(1)))
    for f in files:
        doc = pymupdf.open(f)
        cur = None          # current essay id
        pending_id = None   # heading id waiting for its title line
        skip_clause = False
        last_block_end = None
        for page in doc:
            for block in page.get_text('dict')['blocks']:
                lines = [li for li in (line_info(l) for l in block.get('lines', [])) if li]
                block_started = False
                for li in lines:
                    t = li['text']
                    if li['size'] < 9.9 or re.fullmatch(r'\d{1,4}', t):
                        continue                               # footnotes, running heads, page numbers
                    if li['bold'] and ID_RX.match(t):
                        pending_id = t
                        continue
                    if pending_id and li['bold']:
                        cur = pending_id
                        pending_id = None
                        if cur not in essays:
                            essays[cur] = dict(id=cur, title=t, paras=[])
                            order.append(cur)
                        last_block_end = None
                        continue
                    if li['bold'] and RUNNING_RX.match(t):
                        continue
                    if LABEL_RX.match(t):
                        skip_clause = True
                        continue
                    if skip_clause:
                        if li['italic']:
                            continue                           # the constitutional text being annotated
                        skip_clause = False
                    if not cur:
                        continue
                    paras = essays[cur]['paras']
                    h = li['html'].strip()
                    if not h:
                        continue
                    if not block_started:
                        block_started = True
                        prev = paras[-1] if paras else ''
                        plain_prev = re.sub(r'<[^>]+>', '', prev).rstrip()
                        continues = prev and (h[:1].islower() or not re.search(r'[.?!:”"’)]$', plain_prev))
                        if continues and (last_block_end == 'open' or h[:1].islower()):
                            paras[-1] = join(prev, h)
                        else:
                            paras.append(h)
                    else:
                        paras[-1] = join(paras[-1], h)
                if block_started and cur and essays[cur]['paras']:
                    plain = re.sub(r'<[^>]+>', '', essays[cur]['paras'][-1]).rstrip()
                    last_block_end = 'closed' if re.search(r'[.?!:”"’)]$', plain) else 'open'
    out = []
    for i in order:
        e = essays[i]
        e['paras'] = [re.sub(r'\s+', ' ', p).strip() for p in e['paras'] if len(re.sub(r'<[^>]+>', '', p)) > 30]
        e['paras'] = [re.sub(r'</em>(\s*)<em>', r'\1', p) for p in e['paras']]
        e['words'] = sum(len(re.sub(r'<[^>]+>', '', p).split()) for p in e['paras'])
        out.append(e)
    with open('data/conan_essays.json', 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False)
    print(f'essays: {len(out)}, words: {sum(e["words"] for e in out)}')


def join(a, b):
    if a.endswith('-') and b[:1].islower():
        return a[:-1] + b
    return a + ' ' + b


if __name__ == '__main__':
    main()
