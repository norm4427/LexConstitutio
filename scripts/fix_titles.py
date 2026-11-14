"""Convert ALL-CAPS article titles in docs/data/articles.js to title case (see titlecase.py). Run after build.ps1."""
import json, sys
sys.path.insert(0, 'scripts')
from titlecase import titlecase, is_shouting

path = 'docs/data/articles.js'
s = open(path, encoding='utf-8').read()
head = s[:s.index('=') + 1]
d = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
n = 0
for a in d['articles']:
    if a.get('t') and is_shouting(a['t']):
        a['t'] = titlecase(a['t']); n += 1
open(path, 'w', encoding='utf-8').write(head + json.dumps(d, ensure_ascii=False, separators=(',', ':')) + ';')
print(f'title-cased {n} titles')
