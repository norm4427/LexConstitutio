#!/usr/bin/env bash
# Fetches bylines for WordPress-hosted articles listed in data/wp_needed.txt
# (written by build.ps1) and appends "url<TAB>Author A;Author B" to data/wp_authors.tsv.
cd "$(dirname "$0")/.."
UA="Mozilla/5.0 ConLawIndex/1.0 (academic metadata harvester)"
touch data/wp_authors.tsv
decode(){ sed -e 's/&amp;/\&/g; s/&#8217;/’/g; s/&#8216;/‘/g; s/&#039;/'"'"'/g; s/&#8211;/–/g; s/&nbsp;/ /g; s/&#8220;/“/g; s/&#8221;/”/g'; }
split_names(){ # "A, B &amp; C" or "A and B" -> "A;B;C"
  decode | sed -E 's/^\s*(By|Author:?)\s+//I; s/\s*(,\s*and\s+|\s+and\s+|\s*&\s*|,\s*)\s*/;/g; s/The Honorable\s+//g; s/Hon\.\s+//g; s/^\s+|\s+$//g; s/;+/;/g; s/^;|;$//g'; }
fetch_one(){ id=$1 url=$2
  html=$(curl -s -m 60 -A "$UA" "$url")
  case $id in
    nyulr) names=$(echo "$html" | grep -o '<h4 class="author">[^<]*</h4>' | sed 's/<[^>]*>//g' | split_names | paste -sd';') ;;
    tlr)   names=$(echo "$html" | grep -o 'class="author url fn"[^>]*>[^<]*<' | head -3 | sed 's/.*>\([^<]*\)</\1/' | split_names | awk '!s[$0]++' | paste -sd';') ;;
    # first byline on the page is the article's; later ones belong to "related posts"
    uclalr) names=$(echo "$html" | perl -0ne 'if (m{class="meta-item meta-author">(.*?)</div>}s) { $x=$1; $x=~s/<[^>]+>//g; $x=~s/\s+/ /g; print "$x\n" }' | split_names) ;;
  esac
  printf '%s\t%s\n' "$url" "$names"; }
export -f fetch_one decode split_names; export UA
[ -s data/wp_needed.txt ] || { echo "nothing to do"; exit 0; }
# a few requests at a time per site, politely
for id in nyulr tlr uclalr; do
  grep "^$id	" data/wp_needed.txt | while IFS=$'\t' read -r i u; do fetch_one "$i" "$u"; sleep 0.5; done > "data/wp_authors.$id.part" &
done
wait
cat data/wp_authors.*.part >> data/wp_authors.tsv && rm -f data/wp_authors.*.part
echo "bylines: $(wc -l < data/wp_authors.tsv) cached"
