#!/usr/bin/perl
# Builds docs/data/quizzes.js from scripts/quizzes/*.txt
#   ## guide:<id> or ## doctrine:<part-id>, then blocks of  Q: / - wrong / * correct / E: explanation
use strict; use warnings; use utf8; use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my (%out, $cur, $q, @errs);
for my $f (sort glob 'scripts/quizzes/*.txt') {
  open my $fh, '<:encoding(UTF-8)', $f or die;
  while (my $l = <$fh>) {
    chomp $l; $l =~ s/\r$//;
    next if $l =~ /^#(?!#)/;
    if ($l =~ /^## (guide|doctrine):(\S+)/) { $cur = $out{$1}{$2} = []; next }
    if ($l =~ /^Q:\s*(.+)/) { $q = { q => $1, o => [], a => undef }; push @$cur, $q; next }
    if ($l =~ /^([-*])\s+(.+)/ && $q) { push @{ $q->{o} }, $2; $q->{a} = $#{ $q->{o} } if $1 eq '*'; next }
    if ($l =~ /^E:\s*(.+)/ && $q) { $q->{e} = $1; next }
  }
}
for my $k (sort keys %out) { for my $id (sort keys %{ $out{$k} }) { my $i = 0; for (@{ $out{$k}{$id} }) { $i++; push @errs, "$k:$id #$i" unless defined $_->{a} && @{ $_->{o} } >= 3 && $_->{e} } } }
die "malformed questions: @errs\n" if @errs;
open my $o, '>:raw', 'docs/data/quizzes.js'; print $o 'window.QUIZZES=', JSON::PP->new->utf8->canonical->encode(\%out), ';'; close $o;
printf "%s: %d sets, %d questions\n", $_, scalar(keys %{ $out{$_} }), scalar(map { @$_ } values %{ $out{$_} }) for sort keys %out;
