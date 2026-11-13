#!/usr/bin/perl
# Finds book reviews masquerading as articles. OpenAlex often credits a reviewed book's citations to
# the review (which carries the book's title and lists the book's author), so a review can rank as
# a "most cited article". For every item with >= 10 citations, look the title up in Open Library:
# if a book with the same title, by one of the listed authors (or, for exact long titles, by anyone),
# was published no later than the item, it is a review.
# Writes data/review_flags.tsv (journal|normalized title -> book) and patches docs/data/articles.js.
# Usage: perl scripts/flag_reviews.pl   (cached in data/raw/reviewcheck/)
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my $J = JSON::PP->new->utf8->canonical;
sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; $s }
sub nt { my $s = lc(shift // ''); $s =~ s/^(the|a|an)\s+//; $s =~ s/[^a-z0-9]//g; $s }
sub last_name { my $n = shift // ''; $n =~ s/,?\s+(jr|sr|ii|iii)\.?$//i; my @p = split /\s+/, $n; lc($p[-1] // '') =~ s/[^a-z]//gr }
mkdir 'data/raw/reviewcheck' unless -d 'data/raw/reviewcheck';

my $src = slurp(-s 'data/articles.orig.js' ? 'data/articles.orig.js' : 'docs/data/articles.js');   # always start from unflagged data
$src =~ s/^window\.CL_DATA=//; $src =~ s/;\s*$//;
my $data = decode_json($src);
my @cand = grep { defined $_->{c} && $_->{c} >= 10 && !$_->{rv} } @{ $data->{articles} };
printf "checking %d items\n", scalar @cand;
my (%flag, $n);
for my $a (@cand) {
  my $title = $a->{t}; $title =~ s/\s*[\[(].*$//;   # drop trailing bracketed notes
  my ($main) = split /:/, $title; $main =~ s/^\s+|\s+$//g;
  next if length($main) < 8;
  next if $a->{t} =~ /^The Supreme Court,? \d{4} Term/i;   # Harvard's annual Forewords are articles
  my $key = nt($main); next unless $key;
  my $cache = "data/raw/reviewcheck/" . substr($key, 0, 80) . ".json";
  unless (-s $cache) {
    my $q = $main; utf8::encode($q); $q =~ s/([^A-Za-z0-9 ])/sprintf('%%%02X', ord $1)/ge; $q =~ s/ /+/g;
    system('curl', '-s', '-m', '60', '-A', 'ConLawIndex/1.0 (educational project)', '-o', $cache,
      "https://openlibrary.org/search.json?title=$q&limit=8&fields=title,author_name,first_publish_year,edition_count");
    select(undef, undef, undef, 0.7);
  }
  my $d = eval { decode_json(slurp($cache)) } or next;
  my %mine = map { last_name($_) => 1 } @{ $a->{a} || [] };
  my $y = $a->{y} // 9999;
  for my $b (@{ $d->{docs} || [] }) {
    next unless $b->{title} && $b->{first_publish_year};
    my $bt = nt((split /:/, $b->{title})[0]);
    next unless $bt eq $key || (length($key) >= 15 && index($bt, $key) == 0) || (length($bt) >= 15 && index($key, $bt) == 0);
    next if $b->{first_publish_year} > $y;
    my %bookAuth = map { last_name($_) => 1 } @{ $b->{author_name} || [] };
    my $shared = grep { $bookAuth{$_} } keys %mine;
    my $others = grep { !$bookAuth{$_} } keys %mine;
    # OpenAlex review records list the reviewer plus the reviewed book's author. If every listed
    # author wrote the book, this is the article itself (Open Library also holds reprints of articles).
    # Review records list the reviewer first; if the first listed author wrote the book, it is their own work.
    my $firstIsAuthor = $bookAuth{ last_name(($a->{a} || [])->[0]) };
    my $reviewerPlusAuthor = $shared && $others && !$firstIsAuthor;
    # unsigned "book notices" are credited to the journal itself
    my $journalAuthor = grep { /law review|journal|review$/i } @{ $a->{a} || [] };
    my $titleOnly = !$shared && $bt eq $key && $b->{first_publish_year} < $y
      && (($journalAuthor && length($key) >= 10) || (length($key) >= 22 && ($b->{edition_count} // 0) >= 3));
    next unless $reviewerPlusAuthor || $titleOnly;
    # Same-year matches are often the article itself reissued as a pamphlet; require a book-length work.
    if ($b->{first_publish_year} == $y) {
      my $pc = "data/raw/reviewcheck/pages_" . substr($key, 0, 70) . ".json";
      unless (-s $pc) {
        my $q = (split /:/, $b->{title})[0]; utf8::encode($q); $q =~ s/([^A-Za-z0-9 ])/sprintf('%%%02X', ord $1)/ge; $q =~ s/ /+/g;
        system('curl', '-s', '-m', '60', '-A', 'ConLawIndex/1.0 (educational project)', '-o', $pc, "https://openlibrary.org/search.json?title=$q&limit=5&fields=title,first_publish_year,number_of_pages_median");
        select(undef, undef, undef, 0.7);
      }
      my $pd = eval { decode_json(slurp($pc)) } || {};
      my ($pages) = map { $_->{number_of_pages_median} // () } grep { nt((split /:/, $_->{title} // '')[0]) eq $bt } @{ $pd->{docs} || [] };
      next unless $pages && $pages >= 120;
    }
    $flag{"$a->{j}|" . nt($a->{t})} = join(' / ', $b->{title}, join(', ', @{ $b->{author_name} || [] }), $b->{first_publish_year});
    $a->{rv} = 1; delete $a->{c};
    printf "  review: [%s %s] %s  <=  %s\n", $a->{j}, $a->{y} // '', $a->{t}, $flag{"$a->{j}|" . nt($a->{t})};
    $n++;
    last;
  }
}
# Clean up author names OpenAlex renders with Greek/Cyrillic look-alike letters or in another script.
my %NAME_FIX = ("\x{415}\x{43B}\x{435}\x{43D}\x{430} \x{421}\x{435}\x{440}\x{433}\x{435}\x{435}\x{432}\x{43D}\x{430} \x{41A}\x{430}\x{433}\x{430}\x{43D}" => 'Elena Kagan');
for my $a (@{ $data->{articles} }) {
  for (@{ $a->{a} || [] }) {
    $_ = $NAME_FIX{$_} if $NAME_FIX{$_};
    next unless /[A-Za-z]/;   # leave names written entirely in another script alone
    tr/\x{391}\x{392}\x{395}\x{396}\x{397}\x{399}\x{39A}\x{39C}\x{39D}\x{39F}\x{3A1}\x{3A4}\x{3A5}\x{3A7}\x{430}\x{435}\x{43E}\x{440}\x{441}\x{443}\x{445}/ABEZHIKMNOPTYXaeopcyx/;
  }
}
open my $o, '>:encoding(UTF-8)', 'data/review_flags.tsv'; print $o "$_\t$flag{$_}\n" for sort keys %flag; close $o;
open my $w, '>:raw', 'docs/data/articles.js'; print $w 'window.CL_DATA=', $J->encode($data), ';'; close $w;
printf "flagged %d reviews; wrote data/review_flags.tsv and updated docs/data/articles.js\n", $n // 0;
