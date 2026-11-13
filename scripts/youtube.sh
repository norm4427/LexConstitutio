#!/usr/bin/env bash
# Runs the YouTube searches in yt_queries.tsv and guide.json, then checks embeddability via oEmbed.
# Output: data/raw/youtube/results.tsv  (kind, label, query, videoId, title, channel, channelId, length, views, published)
#         data/raw/youtube/embeddable.tsv (videoId, ok|no)
cd "$(dirname "$0")/.."
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
mkdir -p data/raw/youtube; out=data/raw/youtube/results.tsv; : > $out
{ cat scripts/yt_queries.tsv
  perl -MJSON::PP -0777 -ne 'for my $g (@{decode_json($_)}) { print "guide\t$g->{id}\t$g->{videoQuery}\n"; print "guide\t$g->{id}\t$g->{title} constitution explained\n"; }' scripts/guide.json
} | while IFS=$'\t' read -r kind label query; do
  [ -z "$query" ] && continue
  q=$(printf %s "$query" | sed 's/ /+/g; s/&/%26/g')
  curl -s -m 60 -A "$UA" -H "Accept-Language: en-US,en;q=0.9" "https://www.youtube.com/results?search_query=$q&sp=EgIQAQ%253D%253D" \
    | perl scripts/yt_search.pl | while IFS= read -r line; do printf '%s\t%s\t%s\t%s\n' "$kind" "$label" "$query" "$line"; done >> $out
  sleep 1.5
done
echo "results: $(wc -l < $out)"
# oEmbed returns 401/403 for videos whose owners disabled embedding
cut -f4 $out | sort -u | while read -r id; do
  code=$(curl -s -m 30 -o /dev/null -w "%{http_code}" "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=$id&format=json")
  [ "$code" = 200 ] && echo -e "$id\tok" || echo -e "$id\tno"; sleep 0.15
done > data/raw/youtube/embeddable.tsv
echo "embeddable: $(grep -c ok data/raw/youtube/embeddable.tsv) / $(wc -l < data/raw/youtube/embeddable.tsv)"
