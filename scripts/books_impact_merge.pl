#!/usr/bin/perl
# Adds scholarly citation counts (from scripts/books_impact.sh) to docs/data/books.js as `cites`.
# Book impact is kept separate from article impact: it appears only on the Books tab.
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; $s }
sub nt { my $s = lc(shift // ''); $s =~ s/^(the|a|an)\s+//; $s =~ s/[^a-z0-9]//g; $s }
my $js = slurp('docs/data/books.js'); $js =~ s/^window\.BOOKS=//; $js =~ s/;\s*$//;
my $B = decode_json($js);
my ($found, @miss) = (0);
for my $b (@{ $B->{books} }) {
  my ($main) = split /:/, $b->{title};
  my $key = nt($main);
  my %last = map { my $n = $_; $n =~ s/,?\s+(Jr|Sr)\.?$//; my @p = split /\s+/, $n; (lc($p[-1]) => 1) } @{ $b->{authors} };
  my $titleOk = sub { my $t = nt((split /:/, shift // '')[0]); $t eq $key || (length($key) >= 12 && index($t, $key) == 0) };
  my $authorOk = sub { grep { my @p = split /\s+/, $_; $last{ lc($p[-1] // '') } } @_ };
  my $best;
  if (my $s2 = eval { decode_json(slurp("data/raw/books/$b->{id}.s2.json")) }) {
    for my $r (@{ $s2->{data} || [] }) {
      next unless $titleOk->($r->{title}) && $authorOk->(map { $_->{name} } @{ $r->{authors} || [] });
      $best = { n => $r->{citationCount} + 0, src => 'Semantic Scholar', url => $r->{url} } if !$best || ($r->{citationCount} // 0) > $best->{n};
    }
  }
  if (my $oa = eval { decode_json(slurp("data/raw/books/$b->{id}.oa.json")) }) {
    for my $r (@{ $oa->{results} || [] }) {
      next unless $titleOk->($r->{title}) && $authorOk->(map { $_->{author}{display_name} } @{ $r->{authorships} || [] });
      $best = { n => $r->{cited_by_count} + 0, src => 'OpenAlex', url => $r->{id} } if !$best || ($r->{cited_by_count} // 0) > $best->{n};
    }
  }
  if ($best && $best->{n} > 0) { $b->{cites} = $best; $found++ } else { delete $b->{cites}; push @miss, $b->{id} }
}
# rank among the curated books
my @ranked = sort { $b->{cites}{n} <=> $a->{cites}{n} } grep { $_->{cites} } @{ $B->{books} };
$ranked[$_]{cites}{rank} = $_ + 1 for 0 .. $#ranked;
$B->{citedBooks} = scalar @ranked;
open my $o, '>:raw', 'docs/data/books.js'; print $o 'window.BOOKS=', JSON::PP->new->utf8->canonical->encode($B), ';'; close $o;
printf "books with citation counts: %d / %d\n", $found, scalar @{ $B->{books} };
print "  top: ", join('; ', map { "$_->{title} ($_->{cites}{n}, $_->{cites}{src})" } @ranked[0 .. 4]), "\n" if @ranked >= 5;
print "  missing: @miss\n" if @miss;
