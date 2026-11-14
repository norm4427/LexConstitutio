"""Give each Beginner's Guide topic a shelf of longer lectures and debates from the YouTube lecture collection
(docs/data/lectures.js, built by build_extras.pl), skipping videos already in the topic's "Watch" carousel.

A lecture goes to a topic when its title matches the topic's articleRx (scripts/guide.json), or, failing that, when its one YouTube
search category maps to exactly that topic. Each lecture is shown on at most two topics, title matches first;
each topic keeps up to 6, most viewed first. Adds 'lectures' to every topic in docs/data/guide.js.
Run from the repo root after build_extras.pl (and before fix_text.py):  python scripts/guide_lectures.py
"""
import json, re

CAT_TOPICS = {   # lecture search category -> guide topics it can stand for without a title match
    'The Supreme Court': ['judicial-review'], 'Interpretation & Theory': ['interpretation'],
    'Courses & Overviews': ['interpretation'], 'Executive Power': ['executive-power'],
    'Administrative State': ['administrative-state'], 'Free Speech': ['free-speech'], 'Federalism': ['federalism'],
    'Separation of Powers': ['separation-of-powers'], 'Due Process & Privacy': ['due-process'],
    'Equal Protection': ['equal-protection'], 'Religious Liberty': ['religion'], 'Democracy & Elections': ['voting'],
    'Second Amendment': ['second-amendment'],
}
PER_TOPIC, PER_VIDEO = 6, 2


def load(path, prefix):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def main():
    G = load('docs/data/guide.js', 'GUIDE')
    L = load('docs/data/lectures.js', 'LECTURES')
    rx = {g['id']: re.compile(r'\b(?:' + g['articleRx'] + ')', re.I) for g in json.load(open('scripts/guide.json', encoding='utf-8'))}
    in_carousel = {v['id'] for t in G['topics'] for v in t.get('videos', [])}
    cands = {t['id']: [] for t in G['topics']}
    for v in L['videos']:
        if v['id'] in in_carousel:
            continue
        title_hits = [tid for tid, r in rx.items() if r.search(v['t'])]
        cat_hits = [tid for c in v.get('cat', []) for tid in CAT_TOPICS.get(c, []) if tid not in title_hits] if len(v.get('cat', [])) == 1 and not title_hits else []
        for tid in title_hits[:PER_VIDEO] + cat_hits:
            cands[tid].append((0 if tid in title_hits else 1, -int(v.get('v') or 0), v))
    placed = {}
    for t in G['topics']:
        out = []
        for _, _, v in sorted(cands[t['id']], key=lambda x: (x[0], x[1])):
            if placed.get(v['id'], 0) >= PER_VIDEO:
                continue
            placed[v['id']] = placed.get(v['id'], 0) + 1
            out.append({k: v[k] for k in ('id', 't', 'ch', 'len', 'v') if k in v})
            if len(out) == PER_TOPIC:
                break
        t['lectures'] = out
        print(f"{t['id']:22} {len(out)}")
    open('docs/data/guide.js', 'w', encoding='utf-8').write('window.GUIDE=' + json.dumps(G, ensure_ascii=False, separators=(',', ':')) + ';')
    print(f"{len(placed)} lectures placed on guide pages")


if __name__ == '__main__':
    main()
