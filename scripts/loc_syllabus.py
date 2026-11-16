"""Cache the first pages (the official syllabus) of the U.S. Reports opinion PDFs at the Library of Congress for cases
that have no Oyez summary and no Caselaw Access Project headnotes (mostly 1930-1990s). Used by build_headnotes.py.

Only the bytes needed are fetched: the first 360 KB of the PDF and its last 150 KB (the cross-reference table), placed
at their offsets in an otherwise empty file, which pdftotext can read for the first pages. If that fails the whole
PDF is fetched. Text of the first 5 pages -> data/raw/loc_syl/<case id>.txt. Resumable.
Run from the repo root:  python scripts/loc_syllabus.py [limit]
"""
import glob, json, os, re, subprocess, sys, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

OUT = 'data/raw/loc_syl'
UA = {'User-Agent': 'LexConstitutio/1.0 (static site build script)'}
HEAD, TAIL = 360_000, 150_000


def load_js(path):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))


def pdf_url(c):
    m = re.match(r'^(\d+) U\.S\. (\d+)$', c.get('cit') or '')
    if m and int(m.group(1)) <= 542:
        v, pg = int(m.group(1)), int(m.group(2))
        k = f'usrep{v:03d}{pg:03d}'
        return f'https://tile.loc.gov/storage-services/service/ll/usrep/usrep{v:03d}/{k}/{k}.pdf'
    p = c.get('pdf') or ''
    return p if 'tile.loc.gov' in p else None


def req(u, **h):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers={**UA, **h}), timeout=120)
        except Exception as e:
            if getattr(e, 'code', None) in (403, 404):
                raise
            time.sleep(15 * (attempt + 1))
    raise RuntimeError('gave up')


def to_text(buf):
    fd, pdf = tempfile.mkstemp(suffix='.pdf'); os.close(fd)
    txt = pdf[:-4] + '.txt'
    try:
        open(pdf, 'wb').write(buf)
        subprocess.run(['pdftotext', '-q', '-l', '5', '-enc', 'UTF-8', pdf, txt], timeout=120)
        return open(txt, encoding='utf-8', errors='replace').read() if os.path.exists(txt) else ''
    finally:
        for f in (pdf, txt):
            if os.path.exists(f):
                os.remove(f)


def one(job):
    cid, u = job
    dest = f"{OUT}/{cid.replace('/', '_')}.txt"
    if os.path.exists(dest):
        return
    try:
        r = req(u, Range=f'bytes=0-{HEAD - 1}')
        head = r.read()
        size = int((r.headers.get('Content-Range') or '/0').split('/')[-1] or 0) or len(head)
        if size <= len(head):
            buf = head
        else:
            buf = bytearray(size)
            buf[:len(head)] = head
            tail = req(u, Range=f'bytes={max(len(head), size - TAIL)}-{size - 1}').read()
            buf[size - len(tail):] = tail
        t = to_text(bytes(buf))
        if len(t.strip()) < 200 and size > len(head):
            t = to_text(req(u).read())
        open(dest, 'w', encoding='utf-8').write(t)
    except Exception as e:
        print('  failed', cid, e, flush=True)
    time.sleep(0.7)


def main():
    os.makedirs(OUT, exist_ok=True)
    S = load_js('docs/data/scotus.js')['cases']
    summ = {}
    for f in glob.glob('data/raw/oyez/cases/*.json'):
        d = json.load(open(f, encoding='utf-8'))
        summ[os.path.basename(f)[:-5]] = bool((d.get('facts_of_the_case') or '').strip() or (d.get('conclusion') or '').strip())
    have = set()
    if os.path.exists('docs/data/headnotes-index.js'):
        for f in glob.glob('docs/data/headnotes/*.js'):
            s = open(f, encoding='utf-8').read()
            have |= set(json.loads(s[s.index('HEADNOTES,') + 10:-2]))
    jobs = []
    for c in sorted(S, key=lambda c: c.get('dec') or '', reverse=True):
        if c['id'] in have or not (c.get('s') == 1 or summ.get(c['id'].replace('/', '_')) is False):
            continue
        u = pdf_url(c)
        if u:
            jobs.append((c['id'], u))
    if len(sys.argv) > 1:
        jobs = jobs[:int(sys.argv[1])]
    print(len(jobs), 'cases', flush=True)
    with ThreadPoolExecutor(3) as ex:
        for k, _ in enumerate(ex.map(one, jobs)):
            if k % 200 == 0:
                print(k, '/', len(jobs), flush=True)
    print('done', flush=True)


if __name__ == '__main__':
    main()
