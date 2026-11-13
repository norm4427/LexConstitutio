#!/usr/bin/perl
# Attaches Constitution Annotated essays (Congressional Research Service, Library of Congress; 2022 GPO edition,
# public domain) to the advanced-doctrine sections, using scripts/conan_map.tsv.
# Input: data/conan_essays.json (from scripts/conan_extract.py). Output: docs/data/commentary.js,
# plus data/conan_essays.tsv, an index of every essay for editing the map.
# Map syntax: <section-id> TAB <essay id or prefix>, ...   (prefix includes sub-essays; trailing ! = that essay only)
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or die "$f: $!"; <$h> }
my @essays = @{ decode_json(slurp('data/conan_essays.json')) };
my %by = map { $_->{id} => $_ } @essays;
my @order = map { $_->{id} } @essays;
open my $ix, '>:encoding(UTF-8)', 'data/conan_essays.tsv';
print $ix "$_->{id}\t$_->{words}\t$_->{title}\n" for @essays;
close $ix;

my (%bySection, @missing);
open my $mf, '<:encoding(UTF-8)', 'scripts/conan_map.tsv' or die;
while (my $line = <$mf>) {
  chomp $line; $line =~ s/\r$//;
  next if $line =~ /^\s*(#|$)/;
  my ($sec, $spec) = split /\t+/, $line, 2;
  for my $pre (split /\s*,\s*/, $spec // '') {
    my $exact = $pre =~ s/!$//;
    my @hits = grep { $_ eq $pre || (!$exact && index($_, "$pre.") == 0) } @order;
    push @missing, "$sec: $pre" unless @hits;
    for my $id (@hits) { push @{ $bySection{$sec} }, $id unless grep { $_ eq $id } @{ $bySection{$sec} || [] } }
  }
}
my (%out, $words);
for my $sec (keys %bySection) {
  $out{$sec} = [ map { $words += $by{$_}{words}; { id => $_, title => $by{$_}{title}, p => $by{$_}{paras} } } grep { @{ $by{$_}{paras} } } @{ $bySection{$sec} } ];
}
open my $o, '>:raw', 'docs/data/commentary.js';
print $o 'window.COMMENTARY=', JSON::PP->new->utf8->canonical->encode({
  source => 'Constitution of the United States of America: Analysis and Interpretation (Congressional Research Service, Library of Congress), 2022 edition',
  url => 'https://constitution.congress.gov/', sections => \%out }), ';';
close $o;
printf "sections with commentary: %d; essays attached: %d (%d words); wrote docs/data/commentary.js (%.1f MB)\n",
  scalar keys %out, scalar(map { @$_ } values %out), $words // 0, (-s 'docs/data/commentary.js') / 1048576;
print "  unmatched: $_\n" for @missing;
