#!/usr/bin/perl
# Builds docs/data/docket.js: undecided cases on the Supreme Court's docket, with argument calendar,
# questions presented, status, and the briefs filed on supremecourt.gov. Inputs from scripts/docket.sh.
use strict; use warnings; use utf8;
use JSON::PP;
use Time::Local;
binmode STDOUT, ':encoding(UTF-8)';
my $D = 'data/raw/docket';
sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; utf8::decode($s); $s }
sub strip { my $s = shift // ''; $s =~ s/<br\s*\/?>/ /gi; $s =~ s/<[^>]+>/ /g; $s =~ s/&amp;/&/g; $s =~ s/&nbsp;/ /g; $s =~ s/&#(\d+);/chr($1)/ge; $s =~ s/&quot;/"/g; $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s }
my %MON = (jan => 1, feb => 2, mar => 3, apr => 4, may => 5, jun => 6, jul => 7, aug => 8, sep => 9, oct => 10, nov => 11, dec => 12);
sub iso { my ($m, $d, $y) = @_; my $mm = $MON{ lc substr($m, 0, 3) } or return undef; sprintf('%04d-%02d-%02d', $y, $mm, $d) }
sub title_case { my $s = lc shift; $s =~ s/\b([a-z])/\u$1/g; $s =~ s/\bV\.\s/v. /g; $s =~ s/\b(Of|The|And|For|In|On|To|At|By)\b/\l$1/g; $s =~ s/^(\w)/\u$1/; $s =~ s/\b(Llc|Inc|Usa|Us|Fbi|Epa|Nlrb|Sec|Ftc|Fcc)\b/\U$1/g; $s =~ s/\bLlc\b/LLC/g; $s }

# ------------------------------------------------------------------ Oyez
my (%oyez, $term);
for my $f (sort glob "$D/oyez-*.json") {
  my ($t) = $f =~ /oyez-(\d+)\.json/; $term = $t if !$term || $t > $term;
  my $list = eval { decode_json(do { local $/; open my $h, '<:raw', $f; <$h> }) } or next;
  for my $c (@$list) {
    my %ev; for my $e (grep { $_ } @{ $c->{timeline} || [] }) { $ev{ $e->{event} } = $e->{dates}[-1] if $e->{dates} && @{ $e->{dates} } }
    next if $ev{Decided};
    my ($id) = ($c->{href} // '') =~ m{/cases/(.+)$};
    $oyez{ $c->{docket_number} } = { id => $id, n => strip($c->{name}), q => strip($c->{question}), ds => strip($c->{description}), term => $c->{term},
      granted => $ev{Granted} ? do { my @t = gmtime $ev{Granted}; sprintf('%04d-%02d-%02d', $t[5] + 1900, $t[4] + 1, $t[3]) } : undef,
      argued => $ev{Argued} ? do { my @t = gmtime $ev{Argued}; sprintf('%04d-%02d-%02d', $t[5] + 1900, $t[4] + 1, $t[3]) } : undef };
  }
}

# ------------------------------------------------------------------ calendars (two-column layout)
my (%sched, %calName, @sittings);
for my $f (glob "$D/cal-*.txt") {
  my ($label) = $f =~ /cal-(\w+)\.txt/; my ($year) = $label =~ /(\d{4})/;
  my @lines = split /\n/, slurp($f) =~ s/\r//gr;
  my $split;
  for (@lines) { if (/^(.*?\b(?:Monday|Tuesday|Wednesday|Thursday|Friday),\s+\w+\s+\d+.*?)\b((?:Monday|Tuesday|Wednesday|Thursday|Friday),)/) { $split = length($1); last } }
  my @cols = ([], []);
  for my $l (@lines) {
    if (defined $split && length($l) > $split) { push @{ $cols[0] }, substr($l, 0, $split); push @{ $cols[1] }, substr($l, $split) }
    else { push @{ $cols[0] }, $l }
  }
  my %days;
  for my $col (@cols) {
    my ($date, $cur);
    for my $l (@$col) {
      if ($l =~ /\b(?:Monday|Tuesday|Wednesday|Thursday|Friday),\s+(\w+)\s+(\d{1,2})\b/) { $date = iso($1, $2, $year); $cur = undef; next }
      if ($l =~ /^\s*(\d{2}-[0-9A-Z]{1,5})\b(?:\s+\(\d+\))?/) {
        my $dk = $1; $cur = $dk; next unless $date;
        $sched{$dk} //= $date; push @{ $days{$date} }, $dk unless grep { $_ eq $dk } @{ $days{$date} || [] };
        my $rest = $l =~ s/^\s*\d{2}-[0-9A-Z]{1,5}\s*(?:\(\d+\))?//r; $rest =~ s/^\s+|\s+$//g; $calName{$dk} .= " $rest" if $rest;
        next;
      }
      next unless $cur;
      next if $l =~ /LEGAL HOLIDAY|Court Convenes|SUPREME COURT|OCTOBER TERM|For the Session|^\s*$|\d{4}\s*$/;
      (my $t = $l) =~ s/^\s+|\s+$//g; $calName{$cur} .= " $t" if $t && length($calName{$cur} // '') < 160;
    }
  }
  my ($first) = sort keys %days;
  push @sittings, { label => ($label =~ s/(\d{4})/ $1/r), start => $first, days => [ map { { date => $_, cases => $days{$_} } } sort keys %days ] } if %days;
}
@sittings = sort { ($a->{start} // '') cmp ($b->{start} // '') } @sittings;

# ------------------------------------------------------------------ argument transcripts (current term)
my %tr;
{ my $h = slurp("$D/transcripts.html");
  while ($h =~ m{argument_transcripts/(\d{4})/([^'"\s>]+\.pdf)['"]?[^>]*>\s*([0-9A-Z-]+)\s*<}g) { $tr{$3} //= "https://www.supremecourt.gov/oral_arguments/argument_transcripts/$1/$2" } }

# ------------------------------------------------------------------ docket pages
my @cases; my $decidedCount = 0;
my @dockets = grep { length } map { s/\s+//gr } split /\n/, slurp("$D/dockets.txt");
for my $dk (@dockets) {
  my $h = slurp("$D/d-$dk.html");
  my $o = $oyez{$dk};
  next unless $h || $o;
  my %c = (d => $dk, docket => "https://www.supremecourt.gov/docket/docketfiles/html/public/$dk.html");
  my ($title) = $h =~ /Title:\s*<\/td>\s*<td[^>]*>(.*?)<\/td>/is; $title = strip($title);
  my ($lower) = $h =~ /Lower Ct:\s*<\/td>\s*<td[^>]*>(.*?)<\/td>/is; $lower = strip($lower);
  my ($qp) = $h =~ /href="([^"]*qp\/[^"]+\.pdf)"/i;
  $c{qp} = 'https://www.supremecourt.gov/' . ($qp =~ s{^(\.\./)+}{}r) if $qp;
  $c{lower} = $lower if $lower;
  my (@briefs, @amici, %st);
  while ($h =~ /<tr[^>]*>\s*<td class="ProceedingDate">([^<]+)<\/td>\s*<td>(.*?)<\/td>/gs) {
    my ($date, $cell) = ($1, $2);
    my ($m, $d, $y) = $date =~ /(\w{3})\s+(\d{1,2})\s+(\d{4})/;
    my $when = $m ? iso($m, $d, $y) : undef;
    my ($desc) = split /<br|<span class="documentlinks"/i, $cell; $desc = strip($desc);
    my %links; while ($cell =~ /<a\s+href=\s*"?([^"\s>]+\.pdf)"?[^>]*>([^<]+)<\/a>/gi) { my ($u, $t) = ($1, $2); $links{ strip($t) } //= $u }
    my $main = $links{'Main Document'} // $links{'Petition'} // $links{'Brief'} // (values %links)[0];
    $st{granted} //= $when if $desc =~ /Petition GRANTED|GRANTED\./;
    $st{set} = $1 if $desc =~ /SET FOR ARGUMENT on (\w+, \w+ \d{1,2}, \d{4}|\w+ \d{1,2}, \d{4})/i;
    $st{argued} = $when if $desc =~ /^Argued\./;
    push @{$main::why{$dk}}, "$when $desc" if $desc =~ /JUDGMENT ISSUED|delivered the opinion|Opinion per curiam|denied by the Court.|(?:AFFIRMED|REVERSED|VACATED)|Adjudged to be|DISMISSED (?:as improvidently granted|per Rule)/; $st{decided} //= $when if $desc =~ /JUDGMENT ISSUED|delivered the opinion|Opinion per curiam|denied by the Court\.|(?:AFFIRMED|REVERSED|VACATED)|Adjudged to be|DISMISSED (?:as improvidently granted|per Rule)/;
    next unless $main;
    my $kind = $desc =~ /amic(?:us|i) curiae/i ? 'amicus'
      : $desc =~ /Petition for a writ of certiorari filed/i ? 'petition'
      : $desc =~ /in opposition/i ? 'opposition'
      : $desc =~ /Joint appendix/i ? 'appendix'
      : $desc =~ /^Reply of petitioner|^Reply brief/i ? 'reply'
      : $desc =~ /^Brief of (?:the )?(?:federal )?(?:petitioner|petitioners)/i ? 'petitioner'
      : $desc =~ /^Brief of (?:the )?(?:federal )?(?:respondent|respondents)/i ? 'respondent'
      : $desc =~ /^Brief of .*United States/i ? 'united-states'
      : next;
    my $label = $desc; $label =~ s/\s*\((?:Distributed|Response due[^)]*)\)//g; $label =~ s/\s*filed\.?\s*$//i;
    if ($kind eq 'amicus') { my ($who) = $label =~ /curiae of (.+?)(?: in support of (.+))?$/i; push @amici, { date => $when, who => $who // $label, side => ($label =~ /in support of (.+)$/i ? $1 : ''), url => $main } }
    else { push @briefs, { k => $kind, label => $label, date => $when, url => $main } }
  }
  $c{briefs} = \@briefs; $c{amici} = \@amici;
  $c{n} = $o ? $o->{n} : $calName{$dk} ? title_case($calName{$dk} =~ s/^\s+|\s+$//gr =~ s/\s+/ /gr) : $title;
  $c{title} = $title if $title;
  if ($o) { $c{id} = $o->{id}; $c{q} = $o->{q} if $o->{q}; $c{ds} = $o->{ds} if $o->{ds}; $c{t} = $o->{term} }
  $c{t} //= $term;
  $c{id} //= "$c{t}/$dk";
  $c{granted} = $o && $o->{granted} || $st{granted};
  $c{argued} = $o && $o->{argued} || $st{argued};
  $c{sched} = $sched{$dk};
  $c{tr} = $tr{$dk} if $tr{$dk};
  if (!$c{sched} && $st{set} && $st{set} =~ /(\w+)\s+(\d{1,2}),\s+(\d{4})/) { $c{sched} = iso($1, $2, $3) }
  if ($st{decided}) { $decidedCount++; print STDERR "DROP $dk: ", substr($main::why{$dk}[0], 0, 170), "
"; next }   # decided: no longer on the pending docket
  $c{n} =~ s/^\s*\)\s*//; $c{n} =~ s/\s*\(Consolidated[^)]*\)//i;
  delete @c{ grep { !defined $c{$_} } keys %c };
  push @cases, \%c;
}
# consolidated calendar lines run two names together ("Viramontes v. Cook County Grant v. Higgins"): drop another case's name used as a prefix
for my $c (@cases) { for my $o (@cases) { next if $o == $c; my $short = $o->{n} =~ s/,.*$//r; next if length $short >= length $c->{n}; $c->{n} =~ s/^\Q$short\E(?:,[^,]*?)?\s+(?=\S+ v\. )// and last } }
my $today = do { my @t = localtime; sprintf('%04d-%02d-%02d', $t[5] + 1900, $t[4] + 1, $t[3]) };
for (@cases) { $_->{argued} //= $_->{sched} if $_->{sched} && $_->{sched} lt $today }
@cases = sort { ($a->{sched} // $a->{argued} // '9999') cmp ($b->{sched} // $b->{argued} // '9999') || $a->{d} cmp $b->{d} } @cases;
printf "dropped %d decided; ", $decidedCount; printf "pending cases: %d (argued %d, scheduled %d, with merits briefs %d); sittings: %d\n", scalar @cases,
  scalar(grep { $_->{argued} } @cases), scalar(grep { $_->{sched} } @cases), scalar(grep { grep { $_->{k} =~ /petitioner|respondent/ } @{ $_->{briefs} } } @cases), scalar @sittings;
open my $out, '>:raw', 'docs/data/docket.js' or die;
print $out 'window.DOCKET=', JSON::PP->new->utf8->canonical->encode({ term => $term + 0, updated => $today, sittings => \@sittings, cases => \@cases }), ';';
close $out;
printf "wrote docs/data/docket.js (%.0f KB)\n", (-s 'docs/data/docket.js') / 1024;
