"""Cache Oyez case records (facts, conclusion, vote, opinion author) for every case on the site that lacks a one-line
summary, so the term-by-term flashcards can use Oyez's conclusion. Same cache as flashcards_fetch.py
(data/raw/oyez/cases/). Safe to re-run. Run from the repo root:  python scripts/oyez_fetch_all.py"""
import json, os, time, urllib.request

D = 'data/raw/oyez/cases'
os.makedirs(D, exist_ok=True)
S = json.loads(open('docs/data/scotus.js', encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))['cases']
todo = [c['id'] for c in S if not c.get('ds')]
for i, cid in enumerate(todo):
    path = os.path.join(D, cid.replace('/', '_') + '.json')
    if os.path.exists(path):
        continue
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request('https://api.oyez.org/cases/' + cid, headers={'User-Agent': 'LexConstitutio/1.0'}), timeout=60) as r:
                d = json.load(r)
            break
        except Exception as e:
            d = None
            if getattr(e, 'code', None) == 404:
                break
            time.sleep(10 * (attempt + 1))
    d = d or {}
    keep = {k: d.get(k) for k in ('name', 'facts_of_the_case', 'conclusion', 'decisions', 'written_opinion')}
    if keep['decisions']:
        keep['decisions'] = [{k: x.get(k) for k in ('majority_vote', 'minority_vote', 'winning_party', 'decision_type')} for x in keep['decisions']]
    if keep['written_opinion']:
        keep['written_opinion'] = [{'type': (x.get('type') or {}).get('value'), 'judge': x.get('judge_full_name')} for x in keep['written_opinion']]
    json.dump(keep, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    if i % 200 == 0:
        print(f'{i}/{len(todo)}', flush=True)
    time.sleep(0.25)
print('done', flush=True)
