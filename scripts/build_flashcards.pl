#!/usr/bin/perl
# Builds docs/data/flashcards.js: decks (the Beginner's Guide topics) and cards for the essential Supreme Court cases.
# Case selection: every case featured in the guide or advanced doctrine, plus the constitutional decisions most
# discussed in the article index. Card text comes from Oyez case descriptions and questions (CC BY-NC), the Court's
# official holdings, and the advanced-doctrine case notes written for this site.
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my $J = JSON::PP->new->utf8->canonical;
sub load { my ($f, $var) = @_; local $/; open my $h, '<:raw', $f or die "$f: $!"; my $s = <$h>; $s =~ s/^window\.\w+=//; $s =~ s/;\s*$//; decode_json($s) }
my $TARGET = 560;

my @cases = @{ load('docs/data/scotus.js')->{cases} };
my %byId = map { $_->{id} => $_ } @cases;
my $G = load('docs/data/guide.js');
my $A = load('docs/data/advanced.js');
my @arts = @{ load('docs/data/articles.js')->{articles} };

# ---- decks = beginner topics
my @decks = map { { id => $_->{id}, title => $_->{title}, group => $_->{group} } } @{ $G->{topics} };
my %deckOk = map { $_->{id} => 1 } @decks;

# ---- curated cases (guide essentials and advanced-section cases, with notes)
my (%curated, %notes, %deckOf);
for my $t (@{ $G->{topics} }) { for my $c (@{ $t->{cases} }) { next unless $c->{id}; $curated{ $c->{id} } = 1; $deckOf{ $c->{id} }{ $t->{id} } = 1 } }
my %SEC2DECK = (   # advanced section -> beginner deck (reverse of the guide's "Go deeper" links)
  'supremacy-review' => 'judicial-review', 'review-of-states' => 'judicial-review', 'political-question' => 'standing', 'advisory' => 'standing',
  'interpretation' => 'interpretation', 'functions' => 'interpretation', 'incorporation' => 'incorporation', 'p-or-i' => 'incorporation', 'state-action' => 'incorporation',
  'separation-of-powers' => 'separation-of-powers', 'youngstown' => 'separation-of-powers', 'article-two' => 'executive-power', 'immunity-privilege' => 'executive-power',
  'commerce' => 'commerce-clause', 'enumerated' => 'commerce-clause', 'dormant-commerce' => 'commerce-clause', 'tax-spend' => 'commerce-clause', 'state-tax' => 'commerce-clause',
  'sovereign-immunity' => 'federalism', 'preemption' => 'federalism', 'article-iv-pi' => 'federalism', 'section-five' => 'federalism', 'other-powers' => 'federalism',
  'standing' => 'standing', 'ripeness' => 'standing', 'mootness' => 'standing', 'jurisdiction-control' => 'standing',
  'speech-coverage' => 'free-speech', 'content' => 'free-speech', 'forums' => 'free-speech', 'prior-restraints' => 'free-speech', 'categories' => 'free-speech', 'special-contexts' => 'free-speech',
  'free-exercise' => 'religion', 'establishment' => 'religion', 'religion-interaction' => 'religion',
  'ep-framework' => 'equal-protection', 'strict' => 'equal-protection', 'intermediate' => 'equal-protection', 'rational' => 'equal-protection', 'race-remedies' => 'equal-protection',
  'identifying' => 'due-process', 'privacy-family' => 'due-process', 'economic-sdp' => 'due-process', 'pdp-interests' => 'due-process', 'mathews' => 'due-process', 'pdp-timing' => 'due-process',
  'takings' => 'takings', 'contracts-clause' => 'takings',
);
for my $p (@{ $A->{parts} }) {
  for my $s (@{ $p->{sections} }) {
    for my $c (@{ $s->{cases} }) {
      next unless $c->{id};
      $curated{ $c->{id} } = 1;
      push @{ $notes{ $c->{id} } }, $c->{note} if $c->{note} && !grep { $_ eq $c->{note} } @{ $notes{ $c->{id} } || [] };
      my $d = $SEC2DECK{ $s->{id} }; $d = 'second-amendment' if $s->{id} eq 'other-fundamental' && $c->{n} =~ /Heller|Bruen|Rahimi|McDonald/;
      $d = 'voting' if $s->{id} eq 'other-fundamental' && $c->{n} =~ /Reynolds|Harper/;
      $deckOf{ $c->{id} }{$d} = 1 if $d;
    }
  }
}

# ---- importance: how often law review titles and abstracts discuss each case ("Party v. Party")
my %mentions;
for my $a (@arts) {
  my $text = ($a->{t} // '') . ' ' . ($a->{ab} // '');
  my %seen;
  while ($text =~ /(?:^|[^A-Za-z])([A-Z][\w'.&-]+)(?: [A-Z][\w'.&-]+){0,4} v\. (?:The )?([A-Z][\w'.&-]+)/g) { my $k = lc "$1|$2"; $mentions{$k}++ unless $seen{$k}++ }
}
sub ckey { my $n = shift; $n =~ /^(?:The )?([A-Z][\w'.&-]+)[^v]*? v\. (?:The )?([A-Z][\w'.&-]+)/ ? lc "$1|$2" : '' }

# ---- deck assignment from area tags and text, for cases not placed by curation
my %TAG2DECK = (speech => 'free-speech', religion => 'religion', guns => 'second-amendment', equality => 'equal-protection', dueprocess => 'due-process',
  admin => 'administrative-state', voting => 'voting', takings => 'takings', security => 'war-powers', article3 => 'standing');
sub auto_decks {
  my $c = shift;
  my $text = join ' ', grep { defined } $c->{n}, $c->{q}, $c->{ds}, $c->{h};
  my %d;
  for my $t (@{ $c->{tg} || [] }) {
    if ($TAG2DECK{$t}) { $d{ $TAG2DECK{$t} } = 1 }
    elsif ($t eq 'crimpro') {
      if ($text =~ /fourth amendment|search|seizure|warrant|exclusionary/i) { $d{'fourth-amendment'} = 1 }
      if ($text =~ /eighth amendment|cruel|death penalty|capital punishment|excessive (bail|fines)/i) { $d{punishment} = 1 }
      if ($text =~ /fifth amendment|sixth amendment|counsel|jury|miranda|self-incrimination|confrontation|double jeopardy|speedy trial/i) { $d{'trial-rights'} = 1 }
    }
    elsif ($t eq 'federalism') { $d{ $text =~ /commerce clause|interstate commerce/i ? 'commerce-clause' : 'federalism' } = 1 }
    elsif ($t eq 'seppowers') { $d{ $text =~ /president|executive|pardon|removal|appoint/i ? 'executive-power' : 'separation-of-powers' } = 1 }
  }
  $d{'judicial-review'} = 1 if $text =~ /judicial review|power of the courts to|authority to review/i;
  $d{incorporation} = 1 if $text =~ /incorporat|appl(y|ies) to the states|applicable to the states|through the Fourteenth Amendment/i;
  $d{'war-powers'} = 1 if $text =~ /war powers|military commission|enemy combatant|commander in chief/i;
  return keys %d;
}

# ---- choose cases
my @pool;
for my $c (@cases) {
  next unless $c->{ds} || $c->{h};
  next unless $c->{con} || $curated{ $c->{id} };
  my @d = (keys %{ $deckOf{ $c->{id} } || {} }, auto_decks($c));
  my %u; @d = grep { $deckOk{$_} && !$u{$_}++ } @d;
  next unless @d;
  my $score = ($curated{ $c->{id} } ? 1000 : 0) + 5 * ($mentions{ ckey($c->{n}) } // 0) + scalar(@{ $c->{tg} || [] }) + ($c->{arg} ? 1 : 0);
  push @pool, [$score, $c, \@d];
}
@pool = sort { $b->[0] <=> $a->[0] } @pool;
my @chosen = @pool[0 .. ($#pool < $TARGET - 1 ? $#pool : $TARGET - 1)];

# ---- cards
sub tidy { my $s = shift // ''; $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s =~ s/&/&amp;/g; $s =~ s/</&lt;/g; $s =~ s/>/&gt;/g; $s }
sub holding_text {
  my $c = shift; my $s = tidy($c->{ds} // '');
  $s =~ s/^A case in which the Court (held|decided|ruled|found|concluded|considered|addressed|examined|determined|established)/The Court $1/i;
  $s =~ s/^A case (?:that|in which)\s*/The Court /i;
  return $s;
}
sub mask_parties {
  my ($text, $name) = @_;
  my @words = grep { length > 3 && !/^(United|States|America|Board|Education|County|City|State|Department|Company|Corporation|Inc|Commission|School|District|Court|Town|Ohio|Texas|York|California)$/i } ($name =~ /([A-Z][a-z][\w'-]+)/g);
  for my $w (@words) { $text =~ s/\b\Q$w\E\b/\x{2014}\x{2014}\x{2014}/g }
  return $text;
}
my (@cards, %deckCount);
my $topicName = { map { $_->{id} => $_->{title} } @decks };
for my $x (@chosen) {
  my ($score, $c, $ds) = @$x;
  my $name = tidy($c->{n}); $name =~ s/\s*\(\d\)$//;
  my $label = "$name (" . ($c->{y} // $c->{t}) . ")";
  my $hold = holding_text($c);
  my $official = tidy($c->{h} // '');
  my $answer = $hold || $official;
  my @mk;
  push @mk, ['held', "What did the Court decide in <i>$label</i>?", $answer . ($official && $hold ? "<br><span class=\"fc-sub\">Official holding: $official</span>" : '')] if $answer;
  if ($hold && length $hold > 40) { push @mk, ['which', 'Which case? ' . mask_parties($hold, $name), "<i>$label</i>" . ($c->{cit} ? " &middot; $c->{cit}" : '')] }
  if ($c->{q} && length($c->{q}) < 700) { push @mk, ['qp', "Question presented in <i>$label</i>: " . tidy($c->{q}), $official || $answer] }
  for my $i (0 .. $#{ $notes{ $c->{id} } || [] }) {
    push @mk, ["rule$i", "What rule or principle is <i>$label</i> known for?", tidy($notes{ $c->{id} }[$i])] if $i == 0;
  }
  for my $m (@mk) {
    my ($type, $front, $back) = @$m;
    push @cards, { id => "$c->{id}|$type", c => $c->{id}, k => $type, d => $ds, f => $front, b => $back };
  }
  $deckCount{$_}++ for @$ds;
}
my %cases = map { my $c = $_->[1]; ($c->{id} => { n => $c->{n} =~ s/\s*\(\d\)$//r, y => $c->{y} // $c->{t}, cit => $c->{cit} }) } @chosen;
for my $d (@decks) { $d->{cases} = $deckCount{ $d->{id} } // 0; $d->{cards} = scalar grep { grep { $_ eq $d->{id} } @{ $_->{d} } } @cards }
open my $o, '>:raw', 'docs/data/flashcards.js';
print $o 'window.FLASHCARDS=', $J->encode({ decks => \@decks, cases => \%cases, cards => \@cards }), ';';
close $o;
printf "cases: %d (curated %d); cards: %d; wrote docs/data/flashcards.js (%.0f KB)\n", scalar @chosen, scalar(grep { $curated{ $_->[1]{id} } } @chosen), scalar @cards, (-s 'docs/data/flashcards.js') / 1024;
printf "  %-24s %3d cases %4d cards\n", $_->{id}, $_->{cases}, $_->{cards} for @decks;
