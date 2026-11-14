#!/usr/bin/env bash
# Downloads raw metadata pages for every source in sources.tsv into data/raw/<id>/.
# OAI-PMH (Digital Commons) follows resumption tokens; WordPress pages through the REST API.
# Usage: [SOURCES=scripts/other.tsv] bash scripts/harvest.sh [source_id ...]
cd "$(dirname "$0")/.."
UA="ConLawIndex/1.0 (academic metadata harvester)"
harvest_oai(){ id=$1 host=$2 set=$3; dir=data/raw/$id; mkdir -p "$dir"; rm -f "$dir"/*.xml
  url="https://$host/do/oai/?verb=ListRecords&metadataPrefix=oai_dc&set=publication:$set"; n=0
  while [ -n "$url" ]; do n=$((n+1)); f="$dir/page-$(printf %04d $n).xml"
    for try in 1 2 3; do curl -s -m 120 -A "$UA" "$url" -o "$f" && grep -q "</OAI-PMH>" "$f" && break; sleep 5; done
    tok=$(grep -o '<resumptionToken[^>]*>[^<]*</resumptionToken>' "$f" | sed 's/.*>\([^<]*\)<.*/\1/')
    if [ -n "$tok" ]; then url="https://$host/do/oai/?verb=ListRecords&resumptionToken=$tok"; else url=""; fi
    sleep 1; done; echo "$id: $n pages"; }
harvest_wp(){ id=$1 host=$2; dir=data/raw/$id; mkdir -p "$dir"; rm -f "$dir"/*.json; p=1
  while :; do f="$dir/page-$(printf %04d $p).json"
    code=$(curl -s -m 120 -A "Mozilla/5.0 $UA" -w "%{http_code}" -o "$f" "https://$host/wp-json/wp/v2/posts?per_page=100&page=$p&_fields=id,date,link,title,excerpt,class_list,yoast_head_json")
    [ "$code" = "200" ] || { rm -f "$f"; break; }
    [ "$(head -c 2 "$f")" = "[]" ] && { rm -f "$f"; break; }
    p=$((p+1)); sleep 1; done; echo "$id: $((p-1)) pages"; }
while IFS=$'\t' read -r id kind host set name; do
  [ -z "$id" ] && continue
  if [ $# -gt 0 ] && [[ ! " $* " == *" $id "* ]]; then continue; fi
  case $kind in oai) harvest_oai "$id" "$host" "$set" & ;; wp) harvest_wp "$id" "$host" & ;; esac  # openalex sources: scripts/openalex.sh
done < "${SOURCES:-scripts/sources.tsv}"
wait; echo DONE
