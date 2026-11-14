"""The text each narrated section reads, in page order, shared by pron_scan.py and narrate_all.py.

Each section: {'id', 'kind', 'title', 'paras': [html strings], 'pidx': [page element index per para] (optional), 'out': path}.
Paragraph indexes in the audio's timing file refer to positions in 'paras':
  guide/<topic>       0 title, 1 tagline, then the foundations section (basics, clauses, Constitution Annotated overview);
                      each piece points at its page element (see the comment in sections())    -> docs/audio/guide/<topic>
  doctrine/<section>  0 title, then n+1 for the n-th element matching "p, li, .testbox-h" in the section body, in page
                      order (a list item's own text and its sub-items are separate pieces; both point at their element)
                                                                                           -> docs/audio/doctrine/<section>
  conan/<essay>       0 essay title, 1.. the essay's paragraphs (Constitution Annotated)   -> ../audio-r2/conan/<essay> (for Cloudflare R2)
"""
import json, re
from html.parser import HTMLParser

R2_DIR = '../audio-r2'


def load(name):
    s = open(f'docs/data/{name}.js', encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


class _Blocks(HTMLParser):
    """Readable pieces of a doctrine section in page order: paragraphs, list items and test-box headings.
    Each piece carries the index of its element among the section's "p, li, .testbox-h" elements."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.n, self.stack, self.out = -1, [], []

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get('class') or ''
        if tag in ('p', 'li') or (tag == 'div' and 'testbox-h' in cls.split()):
            self._flush()
            self.n += 1
            self.stack.append([tag, self.n, []])
        elif tag in ('ul', 'ol'):
            self._flush()

    def handle_endtag(self, tag):
        if self.stack and (tag == self.stack[-1][0] or (tag == 'div' and self.stack[-1][0] == 'div')):
            self._flush()
            self.stack.pop()

    def handle_data(self, d):
        if self.stack:
            self.stack[-1][2].append(d)

    def _flush(self):
        if self.stack:
            t = re.sub(r'\s+', ' ', ''.join(self.stack[-1][2])).strip()
            self.stack[-1][2] = []
            if t:
                self.out.append((self.stack[-1][1], t if re.search(r'[.!?:;]["”)]?$', t) else t + '.'))


def blocks(html):
    b = _Blocks(); b.feed(html or ''); b._flush()
    return b.out


def sections(kinds=('guide', 'doctrine', 'conan')):
    out = []
    if 'guide' in kinds:
        F = load('foundations')['topics']
        K = {c['id']: c for c in load('constitution')['clauses']}
        for t in load('guide')['topics']:
            # the page's foundations section, in page order; element n+2 is the n-th "h2, h3, p:not(.attrib), .found-clause"
            # inside section.found (0 is the title, 1 the tagline); see renderGuideTopic in docs/app.js
            paras, pidx, n = [t['title'] + '.', t.get('tagline') or ''], [0, 1], 1
            def add(text, count=True):
                nonlocal n
                n += 1
                text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', text or '')).strip()
                if text:
                    paras.append(text if re.search(r'[.!?:;]["”)]?$', text) else text + '.'); pidx.append(n)
            f = F.get(t['id'])
            if f:
                if f['basics']:
                    add('The basics')
                    for sec in f['basics']:
                        if sec.get('h'):
                            add(sec['h'])
                        for p in sec['paras']:
                            add(p)
                cls = [K[c] for c in f.get('clauses') or [] if c in K]
                if cls:
                    add('In the Constitution')
                    for c in cls:
                        hl = c['hl'] if len(c['hl']) <= 420 else re.sub(r'\s+\S*$', '', c['hl'][:420])
                        add(f"{c['loc']}, {c['name']}: {hl}")
                ov = next((c['conan']['overview'] for c in cls if (c.get('conan') or {}).get('overview')), None)
                if ov:
                    add('How the Court has read it')
                    for p in ov['paras'][:3]:
                        add(p)
            out.append({'id': f"guide/{t['id']}", 'kind': 'guide', 'title': t['title'],
                        'paras': paras, 'pidx': pidx, 'out': f"docs/audio/guide/{t['id']}"})
    if 'doctrine' in kinds:
        for p in load('advanced')['parts']:
            for s in p['sections']:
                bl = blocks(s.get('html'))
                out.append({'id': f"doctrine/{s['id']}", 'kind': 'doctrine', 'title': s['title'],
                            'paras': [s['title'] + '.'] + [t for _, t in bl], 'pidx': [0] + [i + 1 for i, _ in bl],
                            'out': f"docs/audio/doctrine/{s['id']}"})
    if 'conan' in kinds:
        seen = set()
        for sec, essays in load('commentary')['sections'].items():
            for e in essays:
                if e['id'] in seen:
                    continue
                seen.add(e['id'])
                out.append({'id': f"conan/{e['id']}", 'kind': 'conan', 'title': e.get('title') or e['id'],
                            'paras': [(e.get('title') or '') + '.'] + list(e['p']), 'out': f"{R2_DIR}/conan/{e['id']}"})
    return out
