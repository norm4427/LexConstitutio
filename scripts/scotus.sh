#!/usr/bin/env bash
# Supreme Court data: Oyez case lists (summaries, audio links are fetched live by the site),
# supremecourt.gov slip-opinion PDF listings (with official one-line holdings) and argument transcript PDFs.
cd "$(dirname "$0")/.."
UA="Mozilla/5.0 ConLawIndex/1.0 (academic research index)"
mkdir -p data/raw/oyez data/raw/scotus
for t in 1789-1850 1850-1900 1900-1940 1940-1955 $(seq 1955 2025); do
  curl -s -m 120 "https://api.oyez.org/cases?filter=term:$t&per_page=1000" -o data/raw/oyez/term-$t.json; sleep 0.3; done &
for y in $(seq 2005 2025); do yy=$(printf %02d $((y % 100)))
  curl -s -m 120 -A "$UA" "https://www.supremecourt.gov/opinions/slipopinion/$yy" -o data/raw/scotus/slip-$y.html; sleep 1
  curl -s -m 120 -A "$UA" "https://www.supremecourt.gov/oral_arguments/argument_transcript/$y" -o data/raw/scotus/tr-$y.html; sleep 1; done &
wait; echo "oyez terms: $(ls data/raw/oyez | wc -l); scotus pages: $(ls data/raw/scotus | wc -l)"
