#!/usr/bin/env bash
# Fetch only the records each repository journal added or changed since a date (default 2023-01-01), into
# data/raw/<id>/ in the same layout as harvest.sh, so build.ps1 can parse them; merge_recent.py then adds the pieces the
# index does not have yet. Digital Commons: OAI-PMH ListRecords with from=; WordPress: the REST API with after=.
# Usage: [SINCE=2024-06-01] bash scripts/harvest_recent.sh [source_id ...]
cd "$(dirname "$0")/.."
UA="ConLawIndex/1.0 (academic metadata harvester)"
SINCE=${SINCE:-2023-01-01}
oai(){ id=$1 host=$2 set=$3; dir=data/raw/$id; mkdir -p "$dir"; rm -f "$dir"/*.xml "$dir"/*.json
  url="https://$host/do/oai/?verb=ListRecords&metadataPrefix=oai_dc&set=publication:$set&from=$SINCE"; n=0
  while [ -n "$url" ]; do n=$((n+1)); f="$dir/page-$(printf %04d $n).xml"
    for try in 1 2 3; do curl -s -m 120 -A "$UA" "$url" -o "$f" && grep -q "</OAI-PMH>" "$f" && break; sleep 5; done
    tok=$(grep -o '<resumptionToken[^>]*>[^<]*</resumptionToken>' "$f" | sed 's/.*>\([^<]*\)<.*/\1/')
    if [ -n "$tok" ]; then url="https://$host/do/oai/?verb=ListRecords&resumptionToken=$tok"; else url=""; fi
    sleep 1; done; echo "$id: $n pages, $(grep -o '<record>' "$dir"/*.xml 2>/dev/null | wc -l) records"; }
wp(){ id=$1 host=$2; dir=data/raw/$id; mkdir -p "$dir"; rm -f "$dir"/*.json "$dir"/*.xml; p=1
  while :; do f="$dir/page-$(printf %04d $p).json"
    code=$(curl -s -m 120 -A "Mozilla/5.0 $UA" -w "%{http_code}" -o "$f" "https://$host/wp-json/wp/v2/posts?per_page=100&page=$p&after=${SINCE}T00:00:00&_fields=id,date,link,title,excerpt,class_list,yoast_head_json")
    [ "$code" = "200" ] || { rm -f "$f"; break; }
    [ "$(head -c 2 "$f")" = "[]" ] && { rm -f "$f"; break; }
    p=$((p+1)); sleep 1; done; echo "$id: $((p-1)) pages"; }
while IFS=$'\t' read -r id kind host set name; do
  [ -z "$id" ] && continue
  if [ $# -gt 0 ] && [[ ! " $* " == *" $id "* ]]; then continue; fi
  case $kind in oai) oai "$id" "$host" "$set" & ;; wp) wp "$id" "$host" & ;; esac
done < scripts/sources.tsv
wait; echo DONE
