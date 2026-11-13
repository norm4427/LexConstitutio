#!/usr/bin/env bash
# Fetches Wikipedia (CC BY-SA) summaries for each guide topic and checks the Cornell LII Wex link.
cd "$(dirname "$0")/.."
mkdir -p data/raw/wiki
perl -MJSON::PP -0777 -ne 'for my $g (@{decode_json($_)}) { print "$g->{id}\t$g->{wiki}\t$g->{wex}\n" }' scripts/guide.json |
while IFS=$'\t' read -r id wiki wex; do
  t=$(printf %s "$wiki" | sed 's/ /_/g')
  curl -s -m 30 -A "ConLawIndex/1.0 (educational index)" "https://en.wikipedia.org/api/rest_v1/page/summary/$t?redirect=true" -o data/raw/wiki/$id.json
  code=$(curl -s -m 30 -A "Mozilla/5.0" -o /dev/null -w "%{http_code}" "https://www.law.cornell.edu/wex/$wex")
  echo -e "$id\t$code\t$(grep -o '"type":"[^"]*"' data/raw/wiki/$id.json | head -1)\t$(grep -o '"extract":"[^"]\{0,70\}' data/raw/wiki/$id.json)"
  sleep 0.3
done | tee data/raw/wiki/status.tsv
