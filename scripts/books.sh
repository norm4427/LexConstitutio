#!/usr/bin/env bash
# For each book in scripts/books.json, fetches Open Library metadata (ISBN, cover, publisher)
# and the Goodreads rating via Goodreads' public search-suggestion endpoint (Goodreads has no official API).
# Output: data/raw/books/<id>.ol.json and data/raw/books/<id>.gr.json
cd "$(dirname "$0")/.."
mkdir -p data/raw/books
perl -MJSON::PP -0777 -ne 'for my $b (@{decode_json($_)}) { my $t = $b->{title}; $t =~ s/:.*//; my ($last) = $b->{authors}[0] =~ /(\S+?)(?:,? (?:Jr|Sr)\.?)?$/; print "$b->{id}\t$t\t$last\n" }' scripts/books.json |
while IFS=$'\t' read -r id title last; do
  enc(){ perl -MURI::Escape -e 'print uri_escape($ARGV[0])' "$1" 2>/dev/null || printf %s "$1" | sed 's/ /+/g; s/&/%26/g; s/’/%27/g'; }
  t=$(enc "$title"); a=$(enc "$last"); q=$(enc "$title $last")
  [ -s data/raw/books/$id.ol.json ] || curl -s -m 30 -A "ConLawIndex/1.0 (educational book index)" \
    "https://openlibrary.org/search.json?title=$t&author=$a&limit=5&fields=key,title,author_name,first_publish_year,isbn,publisher,cover_i,ratings_average,ratings_count,number_of_pages_median,edition_count" -o data/raw/books/$id.ol.json
  [ -s data/raw/books/$id.gr.json ] || curl -s -m 30 -A "Mozilla/5.0" "https://www.goodreads.com/book/auto_complete?format=json&q=$q" -o data/raw/books/$id.gr.json
  echo "$id ol:$(grep -o '"numFound":[0-9]*' data/raw/books/$id.ol.json) gr:$(grep -o '"avgRating":"[^"]*"' data/raw/books/$id.gr.json | head -1)"
  sleep 1
done
