#!/usr/bin/env bash
# Pulls constitutional-law works (by OpenAlex topic) with citation counts, one journal at a time.
#  new_*: journals that block direct harvesting (Harvard, Yale, Columbia, Virginia, California, Penn, Stanford, Georgetown)
#  old_*: journals already harvested via OAI/WordPress, used to attach citation counts
# Works without an API key (page-number paging, ~$0.0001 of the shared free daily budget per page).
cd "$(dirname "$0")/.."
T="T10802|T13445|T13138|T12332|T14288|T11762|T13075"
SEL="id,doi,title,publication_year,cited_by_count,authorships,biblio,primary_location,abstract_inverted_index,primary_topic"
SOURCES="new:scr:S94195887 new:hjlpp:S1110361 new:uwlr:S109420025 new:utahlr:S2764895072 new:smulr:S4387282199 new:lcp:S2765008069 new:jclc:S66810094 new:hlr:S117766065 new:ylj:S161895660 new:colr:S183770981 new:valr:S67391710 new:calr:S172107878 new:pennlr:S107914479 new:slr:S161743634 new:glj:S54227673
old:mlr_mich:S69429964 old:uclrev:S21339052 old:mlr_minn:S120024774 old:vlr:S120000808 old:dlj:S120433428 old:concomm:S2764695005 old:wlulr:S161985995 old:tlr:S105204244 old:nulr:S15963141 old:elj:S2764466347 old:uclalr:S38213919 old:nyulr:S40812874 old:flr:S142409771 old:clr:S194663980 old:ndlr:S205279741 old:wmlr:S2764488310 old:wmborj:S2764953993 old:hclq:S110755011"
for spec in $SOURCES; do IFS=: read kind id src <<< "$spec"
  [ $# -gt 0 ] && [[ ! " $* " == *" $id "* ]] && continue
  dir=data/raw/openalex/$id; mkdir -p $dir; rm -f $dir/*.json; p=1
  while :; do f=$dir/page-$(printf %03d $p).json
    for try in 1 2 3; do curl -s -m 120 "https://api.openalex.org/works?filter=primary_location.source.id:$src,topics.id:$T&select=$SEL&per_page=200&page=$p" -o $f && grep -q '"results"' $f && break; sleep 5; done
    grep -q '"results": \[\]' $f && { rm -f $f; break; }
    grep -q '"results"' $f || { echo "$id: error on page $p"; head -c 300 $f; rm -f $f; break; }
    p=$((p+1)); [ $p -gt 50 ] && break; sleep 0.2; done
  echo "$kind $id: $((p-1)) pages"
done
