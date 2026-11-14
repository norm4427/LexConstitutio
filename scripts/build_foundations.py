"""Build docs/data/foundations.js: fuller "Foundations" material for each Beginner's Guide topic.

  basics   the most relevant subsections of OpenStax, American Government 3e (Krutz & Waskiewicz; Rice University),
           licensed CC BY 4.0, via the UCF Pressbooks edition; excerpted, with the source sections credited and linked
  clauses  the clauses of the annotated Constitution (constitution.js) that the topic turns on; the page shows their text
           and the Constitution Annotated's overview of the first one
Pages are cached in data/raw/openstax/. Run from the repo root:  python scripts/build_foundations.py
"""
import html, json, os, re, sys, time, urllib.request
sys.path.insert(0, 'scripts')
from titlecase import titlecase
from html.parser import HTMLParser

BASE = 'https://pressbooks.online.ucf.edu/americangovernment3e/chapter/'
# topic: ([OpenStax sections], keyword regex for choosing subsections, [annotated-Constitution clause ids])
MAP = {
    'judicial-review': (['__unknown__-9', '__unknown__-12', '__unknown__-13'], r'judicial review|marbury|constitutional|supreme court', ['judicial-vesting', 'cases-controversies']),
    'interpretation': (['__unknown__-13', 'constitutional-change'], r'interpret|original|restraint|activism|precedent|amend', ['article-v']),
    'incorporation': (['642', '4-4-interpreting-the-bill-of-rights'], r'incorporat|bill of rights|fourteenth|states', ['due-process-14', 'privileges-or-immunities']),
    'separation-of-powers': (['the-development-of-the-constitution', 'the-institutional-design-of-congress'], r'separation of powers|checks and balances|branch|veto|legislative', ['legislative-vesting', 'executive-vesting', 'presentment']),
    'executive-power': (['__unknown__-4', '__unknown__-8'], r'president|executive|veto|order|power|commander', ['executive-vesting', 'commander-in-chief', 'pardon', 'appointments', 'take-care']),
    'federalism': (['the-division-of-powers', 'the-evolution-of-american-federalism'], r'federalism|states|national|tenth|supremacy|dual|cooperative', ['tenth-amendment', 'supremacy']),
    'commerce-clause': (['the-evolution-of-american-federalism', 'the-division-of-powers'], r'commerce|necessary and proper|enumerated|implied|congress', ['commerce', 'necessary-proper', 'taxing-spending']),
    'standing': (['__unknown__-12', '__unknown__-9'], r'standing|controvers|certiorari|cases|hear|jurisdiction', ['cases-controversies']),
    'administrative-state': (['__unknown__-24', '__unknown__-27'], r'bureaucra|agenc|regulat|rule|administrat', ['legislative-vesting', 'appointments']),
    'free-speech': (['securing-basic-freedoms', 'free-speech-and-the-regulation-of-interest-groups'], r'speech|press|expression|libel|obscen|campaign', ['free-speech', 'free-press']),
    'religion': (['securing-basic-freedoms'], r'religio|establishment|free exercise|church|prayer', ['establishment', 'free-exercise']),
    'second-amendment': (['securing-basic-freedoms'], r'arms|gun|militia|second amendment|firearm', ['second-amendment', 'militia']),
    'equal-protection': (['what-are-civil-rights-and-how-do-we-identify-them', 'the-african-american-struggle-for-equality'], r'equal protection|discriminat|scrutiny|segregat|brown|classification', ['equal-protection']),
    'due-process': (['4-4-interpreting-the-bill-of-rights', '642'], r'privacy|due process|abortion|roe|liberty|unenumerated|ninth', ['due-process-14', 'due-process-5', 'ninth-amendment']),
    'fourth-amendment': (['securing-basic-freedoms', 'the-rights-of-suspects'], r'search|seizure|warrant|fourth amendment|probable cause|exclusionary', ['fourth-amendment']),
    'trial-rights': (['the-rights-of-suspects'], r'fifth amendment|sixth amendment|counsel|jury|miranda|self-incrimination|trial|jeopardy', ['self-incrimination', 'counsel', 'sixth-trial', 'confrontation', 'double-jeopardy']),
    'punishment': (['the-rights-of-suspects'], r'eighth amendment|cruel|unusual|death penalty|capital|bail|punishment', ['eighth-amendment']),
    'takings': (['securing-basic-freedoms', 'the-rights-of-suspects', '4-4-interpreting-the-bill-of-rights'], r'property|takings|eminent domain|compensation', ['takings']),
    'voting': (['voter-registration', 'the-african-american-struggle-for-equality', 'congressional-representation'], r'vot|ballot|suffrage|redistrict|gerrymander|apportion|voting rights act', ['fifteenth-amendment', 'elections-clause', 'apportionment', 'nineteenth-amendment']),
    'war-powers': (['__unknown__-39', '__unknown__-8'], r'war|military|foreign|treat|commander|national security', ['war-powers', 'commander-in-chief', 'treaty']),
}
SKIP_CLASS = re.compile(r'textbox|figure|wp-caption|learning|link-to-learning|footnote|media|glossary|review|key-terms')


class Blocks(HTMLParser):
    """Headings and body paragraphs of a Pressbooks chapter, skipping boxes, figures and captions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.cur, self.tag, self.on = [], 0, [], None, False

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get('class') or ''
        if tag in ('div', 'figure', 'aside', 'section', 'table', 'ul', 'ol') and (self.skip or SKIP_CLASS.search(cls) or tag in ('figure', 'aside', 'table')):
            self.skip += 1
            return
        if 'entry-content' in cls or 'chapter-content' in cls or (tag == 'section' and 'chapter' in cls):
            self.on = True
        if not self.skip and tag in ('p', 'h2', 'h3'):
            self.tag, self.cur = tag, []

    def handle_endtag(self, tag):
        if self.skip and tag in ('div', 'figure', 'aside', 'section', 'table', 'ul', 'ol'):
            self.skip -= 1
            return
        if self.tag == tag:
            t = re.sub(r'\s+', ' ', ''.join(self.cur)).strip()
            if t:
                self.out.append((tag, t))
            self.tag = None

    def handle_data(self, d):
        if self.tag and not self.skip:
            self.cur.append(d)


def fetch(slug):
    path = f'data/raw/openstax/{slug.strip("/")}.html'
    if not os.path.exists(path):
        req = urllib.request.Request(BASE + slug.strip('/') + '/', headers={'User-Agent': 'Mozilla/5.0 (LexConstitutio educational site)'})
        open(path, 'w', encoding='utf-8').write(urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace'))
        time.sleep(0.8)
    s = open(path, encoding='utf-8').read()
    title = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', s, re.S) or re.search(r'<title>(.*?)[–|]', s, re.S)
    body = s[s.find('<section data-type="chapter"') if '<section data-type="chapter"' in s else s.find('entry-content'):]
    b = Blocks(); b.feed(body)
    return html.unescape(re.sub(r'<[^>]+>', '', title.group(1))).strip() if title else slug, b.out


def subsections(blocks):
    secs, cur = [], {'h': None, 'paras': []}
    for tag, t in blocks:
        if tag in ('h2', 'h3'):
            if cur['paras'] and cur['h'] != 'License':
                secs.append(cur)
            cur = {'h': titlecase(t) if t.isupper() else t, 'paras': []}
        elif len(t.split()) >= 18 and not re.match(r'^(By the end of this section|Figure \d|Link to Learning|Visit |Watch |Read |\(credit)', t):
            cur['paras'].append(t)
    if cur['paras']:
        secs.append(cur)
    return secs


def main():
    os.makedirs('data/raw/openstax', exist_ok=True)
    out = {}
    for topic, (slugs, kw, clauses) in MAP.items():
        rx = re.compile(kw, re.I)
        cands, srcs = [], []
        for order, slug in enumerate(slugs):
            title, blocks = fetch(slug)
            for i, sec in enumerate(subsections(blocks)):
                txt = ' '.join(sec['paras'])
                score = len(rx.findall(txt)) / (1 + len(txt.split()) / 400) + (3 * len(rx.findall(sec['h'] or '')))
                cands.append((score, order, i, sec, title, slug))
        cands = [c for c in cands if c[0] >= 1.5]
        cands.sort(key=lambda c: -c[0])
        picked, words = [], 0
        for c in cands:
            w = sum(len(p.split()) for p in c[3]['paras'])
            if words and words + w > 1100:
                continue
            paras = c[3]['paras']
            if w > 700:      # long subsection: keep its most relevant paragraphs
                paras = sorted(paras, key=lambda p: -len(rx.findall(p)))[:5]
                paras = [p for p in c[3]['paras'] if p in paras]
                w = sum(len(p.split()) for p in paras)
            picked.append((c[1], c[2], {'h': c[3]['h'], 'paras': paras}, c[4], c[5]))
            words += w
            if words > 800:
                break
        picked.sort(key=lambda c: (c[0], c[1]))
        for _, _, _, title, slug in picked:
            if not any(s['url'].endswith(slug.strip('/') + '/') for s in srcs):
                srcs.append({'title': title, 'url': BASE + slug.strip('/') + '/'})
        out[topic] = {'basics': [p[2] for p in picked], 'src': srcs, 'clauses': clauses}
        print(f'{topic:22} {len(picked)} subsections, {words} words from {", ".join(s["title"][:30] for s in srcs)}')
    data = {'src': 'OpenStax, American Government 3e (Rice University), CC BY 4.0', 'topics': out}
    open('docs/data/foundations.js', 'w', encoding='utf-8').write('window.FOUNDATIONS=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')


if __name__ == '__main__':
    main()
