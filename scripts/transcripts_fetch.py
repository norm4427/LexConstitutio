"""Cache the Supreme Court's official oral argument transcripts (supremecourt.gov) as text, for the vote models.

Transcripts name the justice who is speaking only from the 2004 Term on (earlier ones say "QUESTION:"), so the cache
covers October Terms 2004 to the current Term: the yearly listing pages
https://www.supremecourt.gov/oral_arguments/argument_transcript/<year>, every transcript PDF they link, plus the
transcripts of argued pending cases in docs/data/docket.js. PDFs are converted with pdftotext and deleted.
Output: data/raw/transcripts/<year>/<docket>.txt (and list-<year>.html). Resumable; about 1 request per second.
Run from the repo root:  python scripts/transcripts_fetch.py
"""
import json, os, re, subprocess, sys, time, urllib.request

OUT = 'data/raw/transcripts'
UA = {'User-Agent': 'Mozilla/5.0 LexConstitutio/1.0 (academic research index)'}


def get(url, timeout=90):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def fetch_pdf(url, dest):
    if os.path.exists(dest):
        return True
    try:
        pdf = dest[:-4] + '.pdf'
        open(pdf, 'wb').write(get(url))
        subprocess.run(['pdftotext', '-q', pdf, dest], check=True)
        os.remove(pdf)
        time.sleep(0.8)
        return True
    except Exception as e:
        print('  failed', url, e, flush=True)
        return False


def main():
    os.makedirs(OUT, exist_ok=True)
    years = range(2004, int(sys.argv[1]) + 1 if len(sys.argv) > 1 else 2026 + 1)
    n = 0
    for y in years:
        lp = f'{OUT}/list-{y}.html'
        if not os.path.exists(lp) or y >= 2025:
            try:
                open(lp, 'wb').write(get(f'https://www.supremecourt.gov/oral_arguments/argument_transcript/{y}'))
                time.sleep(1)
            except Exception as e:
                print('listing failed', y, e); continue
        page = open(lp, encoding='utf-8', errors='replace').read()
        links = dict.fromkeys(re.findall(r"href='([^']*(?:argument_transcripts|/pdfs/transcripts)/%d/[^']+\.pdf)'" % y, page))
        os.makedirs(f'{OUT}/{y}', exist_ok=True)
        for href in links:
            url = ('https://www.supremecourt.gov' + href) if href.startswith('/') else 'https://www.supremecourt.gov/oral_arguments/' + href.replace('../', '')
            name = href.rsplit('/', 1)[1][:-4]
            n += fetch_pdf(url, f'{OUT}/{y}/{name}.txt')
        print(y, len(links), 'transcripts', flush=True)
    # pending cases already argued
    s = open('docs/data/docket.js', encoding='utf-8').read()
    for c in json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['cases']:
        if c.get('tr'):
            y = str(c.get('t') or '')
            os.makedirs(f'{OUT}/{y}', exist_ok=True)
            fetch_pdf(c['tr'], f"{OUT}/{y}/{c['tr'].rsplit('/', 1)[1][:-4]}.txt")
    print('done', n)


if __name__ == '__main__':
    main()
