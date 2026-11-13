#!/usr/bin/env bash
# Re-fetches Wikisource pages that came back as rate-limit errors, slowly, with backoff.
cd "$(dirname "$0")/.."
R=data/raw/corner; UA="ConLawIndex/1.0 (educational project; low-volume)"; API="https://en.wikisource.org/w/api.php"
fetch(){ local t="$1" out="$2" enc; enc=$(perl -MURI::Escape -e 'print uri_escape($ARGV[0])' "$t")
  for try in 1 2 3 4 5; do
    curl -s -m 60 -A "$UA" "$API?action=parse&page=$enc&prop=text|displaytitle&format=json&formatversion=2&redirects=1&maxlag=5" -o "$out"
    if grep -q '"parse"' "$out"; then sleep 2; return 0; fi
    sleep $((try * 15))
  done; echo "failed: $t"; }
while read -r t; do
  f="$R/statutes/$(echo "$t" | sed 's#.*Volume 1/##; s#[ /]#_#g').json"
  grep -q '"parse"' "$f" 2>/dev/null || fetch "$t" "$f"
done < $R/statutes/titles.txt
for p in "vsrf|Virginia Statute for Religious Freedom" "remonstrance|Memorial and Remonstrance Against Religious Assessments" "danbury|Letter to the Danbury Baptists"; do
  id=${p%%|*}; t=${p#*|}; grep -q '"parse"' "$R/wikisource/$id.json" 2>/dev/null || fetch "$t" "$R/wikisource/$id.json"; done
echo "good statutes: $(grep -l '"parse"' $R/statutes/*.json | wc -l)"
