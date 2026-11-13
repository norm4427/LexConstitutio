#!/usr/bin/perl
# Flattens data/raw/openalex/<id>/page-*.json into data/raw/openalex/<id>/works.tsv
# (PowerShell's JSON parser can't read OpenAlex abstract indexes, which have case-variant keys).
# Columns: title, year, cites, authors(;), url, pdf, volume, issue, first_page, primary_topic, abstract
use strict; use warnings; use JSON::PP;
my $root = shift // 'data/raw/openalex';
for my $dir (glob "$root/*") {
  next unless -d $dir;
  open my $out, '>:encoding(UTF-8)', "$dir/works.tsv" or die;
  my $n = 0;
  for my $f (sort glob "$dir/page-*.json") {
    local $/; open my $in, '<:raw', $f or next; my $d = eval { decode_json(<$in>) } or next;
    for my $w (@{ $d->{results} || [] }) {
      my $abs = '';
      if (my $inv = $w->{abstract_inverted_index}) {
        my @words; while (my ($k, $v) = each %$inv) { $words[$_] = $k for @$v } $abs = join ' ', grep { defined } @words;
      }
      my $loc = $w->{primary_location} || {};
      my @row = ($w->{title}, $w->{publication_year}, $w->{cited_by_count},
        join(';', map { $_->{author}{display_name} // () } @{ $w->{authorships} || [] }),
        $w->{doi} || $loc->{landing_page_url} || $w->{id}, $loc->{pdf_url},
        $w->{biblio}{volume}, $w->{biblio}{issue}, $w->{biblio}{first_page},
        ($w->{primary_topic} || {})->{display_name}, $abs);
      print $out join("\t", map { my $s = $_ // ''; $s =~ s/[\t\r\n]+/ /g; $s } @row), "\n"; $n++;
    }
  }
  print "$dir: $n\n";
}
