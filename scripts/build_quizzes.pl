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
# the short names of essential cases ("Janus", "Lopez") that occur in the quiz text, so the page can italicize them;
# the first party, or the second when the first is a government
my $read = sub { my $f = shift; open my $h, '<:raw', $f or return; local $/; my $s = <$h>; $s =~ s/^[^=]*=//; $s =~ s/;\s*$//; decode_json($s) };
my %ess = map { $_ => 1 } @{ $read->('docs/data/essential.js') || [] };
my $S = $read->('docs/data/scotus.js') || { cases => [] };
my $gov = qr/^(?:United States|State|People|Commonwealth|City|County|Board|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New \w+|North \w+|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South \w+|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\b/;
my $all = join ' ', map { my $q = $_; ($q->{q}, @{ $q->{o} }, $q->{e}) } map { @$_ } map { values %$_ } values %out;
# names that also mean a Justice, a President, a place or an ordinary word, so they are left upright
my %NOT_CASE = map { $_ => 1 } ('Alexander', 'Bank', 'Church', 'Civil Rights', 'Department', 'District', 'Heart', 'Johnson', 'Kennedy',
  'Madison', 'Powers', 'Stevens', 'Thomas', 'Town', 'Trump', 'Students', 'White', 'School District', 'Los Angeles', 'San Antonio',
  'Home Building', 'Nixon', 'Bush', 'Davis', 'Harris', 'Miller', 'Moore', 'Williams', 'Carr', 'Craig', 'Holder', 'Marsh', 'Perry',
  'Reed', 'Simmons', 'Gilbert', 'Flores', 'Baker', 'Bond', 'Cooper', 'Our Lady', 'National Pork', 'Employment Division', 'Montgomery');
my %short;
for my $c (grep { $ess{$_->{id}} } @{ $S->{cases} }) {
  my ($a, $b) = split /\s+v\.\s+/, $c->{n} // '', 2;
  my $p = ($b && $a =~ $gov) ? $b : $a; next unless $p;
  $p =~ s/,.*$//; $p =~ s/^(?:The|In re)\s+//; my @w = split /\s+/, $p; $p = join ' ', @w[0 .. ($#w > 0 ? 1 : 0)]; $p =~ s/\s+(?:of|the|and|for)$//i;
  $short{$p} = 1 if length $p > 3 && $p !~ $gov && !$NOT_CASE{$p} && $all =~ /\b\Q$p\E\b/;
}
$out{cases} = [ sort keys %short ];
open my $o, '>:raw', 'docs/data/quizzes.js'; print $o 'window.QUIZZES=', JSON::PP->new->utf8->canonical->encode(\%out), ';'; close $o;
printf "case names to italicize: %d\n", scalar keys %short;
printf "%s: %d sets, %d questions\n", $_, scalar(keys %{ $out{$_} }), scalar(map { @$_ } values %{ $out{$_} }) for grep { $_ ne "cases" } sort keys %out;
