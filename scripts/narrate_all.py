"""Generate narration for every section (voice: Kokoro am_michael) and write the manifest docs/data/narration.js.

Run pron_scan.py first so names and unusual words have verified pronunciations.
Each section becomes <out>.mp3 (64 kbps mono) + <out>.json (sentence timings for follow-along highlighting); see
narration_sections.py for which text each section reads and where it is written. Existing outputs are skipped, so the
run can be stopped and resumed; pass --force to regenerate.
  python scripts/narrate_all.py guide doctrine      # the parts stored in the repo (docs/audio/)
  python scripts/narrate_all.py conan               # Constitution Annotated essays, written to ../audio-r2/ for Cloudflare R2
  python scripts/narrate_all.py --manifest          # only rebuild docs/data/narration.js from what exists
"""
import json, os, sys, time

sys.path.insert(0, 'scripts')
from narration_sections import sections, R2_DIR

VOICE = 'am_michael'
# Public base URL of the Cloudflare R2 bucket that serves ../audio-r2/ (set once the bucket exists).
R2_BASE = os.environ.get('LC_AUDIO_BASE', '')


def manifest():
    items = {}
    for s in sections():
        j = s['out'] + '.json'
        if not (os.path.exists(j) and os.path.exists(s['out'] + '.mp3')):
            continue
        meta = json.load(open(j, encoding='utf-8'))
        rel = s['out'][len('docs/'):] if s['out'].startswith('docs/') else s['out'][len(R2_DIR) + 1:]
        items[s['id']] = {'p': rel, 'd': meta['dur'], 'r2': 0 if s['out'].startswith('docs/') else 1}
    data = {'voice': 'Kokoro (am_michael), open-weight text-to-speech', 'r2': R2_BASE, 'items': items}
    with open('docs/data/narration.js', 'w', encoding='utf-8') as fh:
        fh.write('window.NARRATION=' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';')
    hrs = sum(v['d'] for v in items.values()) / 3600
    print(f'manifest: {len(items)} narrated sections, {hrs:.1f} hours')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--manifest' in sys.argv:
        return manifest()
    force = '--force' in sys.argv
    todo = [s for s in sections(args or ('guide', 'doctrine', 'conan')) if force or not os.path.exists(s['out'] + '.json')]
    from narrate import Narrator
    n = Narrator()
    t0, done_audio = time.time(), 0.0
    total_words = sum(len(' '.join(s['paras']).split()) for s in todo)
    words_done = 0
    print(f'{len(todo)} sections to narrate (~{total_words / 9000:.1f} hours of audio)', flush=True)
    for i, s in enumerate(todo, 1):
        dur = n.render(s['paras'], s['out'], voice=VOICE)   # keep every paragraph so timing indexes match the page
        if s.get('pidx'):   # map piece numbers to page element numbers for highlighting
            j = s['out'] + '.json'; meta = json.load(open(j, encoding='utf-8'))
            for row in meta['s']:
                row[2] = s['pidx'][row[2]]
            json.dump(meta, open(j, 'w', encoding='utf-8'), ensure_ascii=False)
        done_audio += dur
        words_done += len(' '.join(s['paras']).split())
        el = time.time() - t0
        eta = el / max(words_done, 1) * (total_words - words_done)
        print(f"[{i}/{len(todo)}] {s['id']}: {dur / 60:.1f} min audio | elapsed {el / 60:.0f} min, ~{eta / 60:.0f} min left", flush=True)
    manifest()


if __name__ == '__main__':
    main()
