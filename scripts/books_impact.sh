#!/usr/bin/env bash
# Citation counts for the curated books (shown on the Books tab, separate from article impact).
# Primary: OpenAlex book records (type:book), searched by title + author surname.
# Fallback: Semantic Scholar (free but rate-limited; it often splits a book's citations across records).
# OpenAlex's free tier has a small shared daily budget; if it runs out, re-run the next day (results are cached).
# Output: data/raw/books/<id>.oa.json and <id>.s2.json, merged by scripts/books_impact_merge.pl
cd "$(dirname "$0")/.."
perl -MJSON::PP -0777 -ne 'for my $b (@{decode_json($_)}) { my $t = $b->{title}; $t =~ s/:.*//; my ($last) = $b->{authors}[0] =~ /(\S+?)(?:,? (?:Jr|Sr)\.?)?$/; print "$b->{id}\t$t\t$last\n" }' scripts/books.json |
while IFS=$'\t' read -r id title last; do
  q=$(perl -MURI::Escape -e 'print uri_escape_utf8($ARGV[0])' "$title $last")
  oa=data/raw/books/$id.oa.json
  if ! grep -q '"oa_query": "title+author"' "$oa.meta" 2>/dev/null; then
    curl -s -m 60 -o "$oa.tmp" "https://api.openalex.org/works?search=$q&filter=type:book&select=id,title,publication_year,cited_by_count,authorships&per_page=5"
    if grep -q '"results"' "$oa.tmp"; then mv "$oa.tmp" "$oa"; echo '{"oa_query": "title+author"}' > "$oa.meta"
    else echo "OpenAlex unavailable (likely daily budget): $(head -c 100 "$oa.tmp")"; rm -f "$oa.tmp"; fi
    sleep 1
  fi
  s2=data/raw/books/$id.s2.json
  if ! grep -q '"data"' "$s2" 2>/dev/null; then
    for try in 1 2; do
      curl -s -m 60 -A "ConLawIndex/1.0 (educational project)" -o "$s2" "https://api.semanticscholar.org/graph/v1/paper/search?query=$q&fields=title,year,citationCount,authors,publicationTypes,url&limit=5"
      grep -q '"data"' "$s2" && break; sleep 4
    done
    sleep 3
  fi
done
