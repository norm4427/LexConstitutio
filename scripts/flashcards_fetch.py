"""Fetch the extra case detail the flashcard answers use (cached; safe to re-run).

- Oyez case records (facts of the case, conclusion, vote, opinion author)   -> data/raw/oyez/cases/<term>_<docket>.json
Run from the repo root after build_flashcards.pl has chosen the cases:  python scripts/flashcards_fetch.py
"""
import json, os, time, urllib.request

UA = {'User-Agent': 'LexConstitutio-flashcards/1.0 (static site build script)'}
D = 'data/raw/oyez/cases'


def get(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, 'code', None) == 404:
                return None
            time.sleep(15 * (attempt + 1))
    return None


def main():
    os.makedirs(D, exist_ok=True)
    s = open('docs/data/flashcards.js', encoding='utf-8').read()
    cases = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['cases']
    for i, cid in enumerate(sorted(cases)):
        path = os.path.join(D, cid.replace('/', '_') + '.json')
        if os.path.exists(path):
            continue
        d = get('https://api.oyez.org/cases/' + cid) or {}
        keep = {k: d.get(k) for k in ('name', 'facts_of_the_case', 'conclusion', 'decisions', 'written_opinion')}
        if keep['decisions']:
            keep['decisions'] = [{k: x.get(k) for k in ('majority_vote', 'minority_vote', 'winning_party', 'decision_type')} for x in keep['decisions']]
        if keep['written_opinion']:
            keep['written_opinion'] = [{'type': (x.get('type') or {}).get('value'), 'judge': x.get('judge_full_name')} for x in keep['written_opinion']]
        json.dump(keep, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        if i % 50 == 0:
            print(f'oyez {i}/{len(cases)}', flush=True)
        time.sleep(0.3)

if __name__ == '__main__':
    main()
