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

# ---- The Basics: 100 core cases = the Beginner's Guide landmarks first, then the most-cited (later Supreme Court citations)
my $impact = eval { load('docs/data/case_impact.js')->{c} } || {};
my %guideCase; for my $t (@{ $G->{topics} }) { $guideCase{ $_->{id} } = 1 for grep { $_->{id} } @{ $t->{cases} } }
my @basicsOrder = sort { ($guideCase{ $b->[1]{id} } ? 1 : 0) <=> ($guideCase{ $a->[1]{id} } ? 1 : 0) || (($impact->{ $b->[1]{id} } // [0, 0, -1])->[2] <=> ($impact->{ $a->[1]{id} } // [0, 0, -1])->[2]) } @chosen;
my %basics = map { $_->[1]{id} => 1 } @basicsOrder[0 .. ($#basicsOrder < 99 ? $#basicsOrder : 99)];
$_->[2] = [ 'basics', @{ $_->[2] } ] for grep { $basics{ $_->[1]{id} } } @chosen;
unshift @decks, { id => 'basics', title => 'The Basics: 100 essential cases', group => 'The Basics' };

# ---- cards
sub tidy { my $s = shift // ''; $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s =~ s/&/&amp;/g; $s =~ s/</&lt;/g; $s =~ s/>/&gt;/g; $s }
sub holding_text {
  my $c = shift; my $s = tidy($c->{ds} // '');
  $s =~ s/^A case in which the Court (held|decided|ruled|found|concluded|considered|addressed|examined|determined|established)/The Court $1/i;
  $s =~ s/^A case (?:that|in which) the Court (?:that\s+)?(?=(?:the|a|an|he|she|both|[A-Z])\b)/The Court held that /;   # Oyez dropped the verb
  $s =~ s/^A case (?:that|in which) the Court that\s+/The Court held that /i;
  $s =~ s/^A case (?:that|in which) (?:the Court )?/The Court /i;
  return $s;
}
sub mask_parties {
  my ($text, $name) = @_;
  my @words = grep { length > 3 && !/^(United|States|America|Board|Education|County|City|State|Department|Company|Corporation|Inc|Commission|School|District|Court|Town|Ohio|Texas|York|California)$/i } ($name =~ /([A-Z][a-z][\w'-]+)/g);
  for my $w (@words) { $text =~ s/\b\Q$w\E\b/\x{2014}\x{2014}\x{2014}/g }
  return $text;
}

# ---- three-part answers: background (Oyez facts of the case), ruling (Oyez conclusion + vote), importance (site notes, CONAN)
my %ENT = (amp => '&', quot => '"', apos => "'", nbsp => ' ', lt => '<', gt => '>', ldquo => "\x{201C}", rdquo => "\x{201D}", lsquo => "\x{2018}", rsquo => "\x{2019}", mdash => "\x{2014}", ndash => "\x{2013}", hellip => "\x{2026}", sect => "\x{A7}");
sub plain { my $s = shift // ''; $s =~ s/<[^>]+>/ /g; $s =~ s/&#(\d+);/chr($1)/ge; $s =~ s/&#x([0-9a-f]+);/chr(hex $1)/gie; $s =~ s/&(\w+);/$ENT{$1} \/\/ "&$1;"/ge; $s =~ s/\s+/ /g; $s =~ s/\s+([,.;:])/$1/g; $s =~ s/^\s+|\s+$//g; $s }
my $NOSPLIT = qr/(?:\b(?:v|U\.S|U\.S\.C|Mr|Mrs|Ms|Dr|St|Co|Inc|Corp|Jr|Sr|No|Nos|Art|Stat|Cong|Sess|Ct|Cir|Supp|ed|al|Gen|Gov|Rev|Sen|Rep|Ltd|Bros|Dist|Ass'n|Dep't|Comm'n|cl|amend|ch|pp|p|seq|e\.g|i\.e|cf|viz)|\b[A-Z])\.$/;
sub sents {
  my $t = shift; my (@out, $start); $start = 0;
  while ($t =~ /[.!?]["\x{201D}')\]]?\s+(?=["\x{201C}(\[]?[A-Z0-9])/g) {
    my $end = pos($t); my $head = substr($t, $start, $-[0] + 1 - $start);
    next if substr($t, $-[0], 1) eq '.' && $head =~ $NOSPLIT;
    push @out, substr($t, $start, $end - $start) =~ s/\s+$//r; $start = $end;
  }
  push @out, substr($t, $start) if $start < length $t;
  return grep { /\w/ } @out;
}
sub words { scalar(() = $_[0] =~ /\S+/g) }
my $LAWWORD = qr/\b(?:Act|statute|statutory|law|laws|ordinance|regulation|rule|provision|code|policy|amendment|constitution|clause|forbids|prohibit|required?s?|bann?e?d?|criminali[sz])/i;
sub background {
  my $facts = plain(shift); return '' unless $facts;
  my @s = grep { !/^(?:Decided|Consolidated|Argued) (?:together )?with\b/ } sents($facts); $facts = join ' ', @s; return $facts if words($facts) <= 110;
  my (@keep, $n); my $haveLaw = 0;
  for my $i (0 .. $#s) {
    my $isLaw = $s[$i] =~ $LAWWORD;
    my $w = words($s[$i]);
    if ($i < 2 || ($isLaw && !$haveLaw) || ($n + $w <= 95 && ($isLaw || $i < 4))) { push @keep, $i; $n += $w; $haveLaw ||= $isLaw }
    last if $n >= 95 && $haveLaw;
  }
  my $out = join ' ', @s[@keep];
  return $out;
}
sub overlap {
  my %A = map { lc($_) => 1 } grep { length > 3 } $_[0] =~ /(\w+)/g; my %B = map { lc($_) => 1 } grep { length > 3 } $_[1] =~ /(\w+)/g;
  my $common = grep { $B{$_} } keys %A; my $min = (keys %A) < (keys %B) ? keys %A : keys %B; $min ? $common / $min : 0 }
sub reasoning {
  my ($concl, $hold) = @_; my $t = plain($concl); return '' unless $t;
  $t =~ s/^(?:Yes|No|Yes and no|No and yes|Not necessarily|Probably not|Maybe)[.,;:]\s*//i;
  my @s = sents($t); my @keep; my $n = 0;
  for my $x (@s) {
    $x =~ s/^(?:In|With) an? (?:[\w\x{2013}-]+ )?(?:decision|ruling|opinion|vote)\b[^,]{0,140}, (?:the Court|the majority|it) //i and $x = 'The Court ' . $x;
    $x =~ s/^(?:Justice|Chief Justice) [\w. ]+? (?:delivered|wrote|authored) (?:the|a) (?:majority |plurality |unanimous )?opinion(?: of the Court| for the Court)?[^.]*?(?:\.\s*|, )//i;
    next if $x !~ /\w{4}/ || $x =~ /^(?:Justice|Chief Justice) [\w. ]+ (?:concurred|dissented|filed)/i || $x =~ /^(?:Justice|Chief Justice)\b[^.]{0,60}?\b(?:delivered|wrote|authored|announced)\b/i;
    next if grep { overlap($x, $_) > 0.5 } grep { $_ } ($hold, @keep);
    my $w = words($x); last if @keep && $n + $w > 75;
    push @keep, ucfirst $x; $n += $w; last if @keep == 2;
  }
  return join ' ', @keep;
}
sub vote_line {
  my $o = shift; return '' unless $o;
  my $d = (@{ $o->{decisions} || [] })[0] || {}; my @bits;
  push @bits, "Vote: $d->{majority_vote}\x{2013}$d->{minority_vote}" if defined $d->{majority_vote} && defined $d->{minority_vote} && $d->{majority_vote} =~ /^\d+$/;
  if (($d->{decision_type} // '') =~ /per curiam/i) { push @bits, 'per curiam' }
  else { my ($m) = grep { ($_->{type} // '') =~ /majority|plurality/i } @{ $o->{written_opinion} || [] }; push @bits, ($m->{type} =~ /plurality/i ? 'plurality' : 'majority') . " opinion by $m->{judge}" if $m && $m->{judge} }
  return join "\x{2003}\x{B7}\x{2003}", @bits;
}
# importance: sentences that discuss the case in the site's doctrine text and the Constitution Annotated (public domain)
my $C = load('docs/data/commentary.js');
my (@advText, @conText);
for my $p (@{ $A->{parts} }) { for my $s (@{ $p->{sections} }) { my $h = $s->{html} // ''; push @advText, plain($1) while $h =~ /<p>(.*?)<\/p>/gs } }
for my $list (values %{ $C->{sections} }) { for my $e (@$list) { push @conText, map { plain($_) } @{ $e->{p} } } }
for my $f (glob 'data/raw/conan/g*.txt') {   # full Constitution Annotated text (GovInfo PDFs via pdftotext): body paragraphs are single long lines
  open my $h, '<:encoding(UTF-8)', $f or next;
  while (my $l = <$h>) {
    $l =~ s/\r?\n$//; next if $l =~ /^\d+ / || words($l) < 40 || $l =~ /\.{8}/;
    $l =~ s/([a-z.,;:\x{201D}\x{2019})])\d{1,3}(?=[\s,.;:]|$)/$1/g;   # inline footnote markers
    push @conText, plain($l);
  }
}
my %seenPara; @conText = grep { !$seenPara{$_}++ } @conText;
# Congressional Research Service reports (public domain), via EveryCRSReport's mirror; see scripts/crs_fetch.py
my (%crsDate, @crsText);
if (open my $h, '<:encoding(UTF-8)', 'data/raw/crs/reports.csv') { <$h>; while (<$h>) { my ($num, undef, undef, $date) = split /,/, $_, 5; $crsDate{$num} = $date if $date } }
for my $f (glob 'data/raw/crs/html/*.html') {
  my ($num) = $f =~ m{([A-Za-z0-9-]+)[.]html$}; my $date = $crsDate{$num} // next;
  open my $h, '<:encoding(UTF-8)', $f or next; local $/; my $html = <$h>;
  $html =~ s{</?(?:span|a|em|i|b|strong|u|sup|sub)\b[^>]*>}{}gi;   # inline tags split words ("A</span><span>dditional")
  while ($html =~ m{<p\b[^>]*>(.*?)</p>}gs) { my $t = plain($1); push @crsText, [$date, $num, $t] if words($t) >= 25 }
}
my $SIG = qr/\b(?:landmark|first|overrul|establish|announc|adopt|test|framework|standard|doctrine|rule|reject|extend|limit|narrow|expan|recogni|struck|invalidat|upheld|foundation|leading|seminal|principle|precedent|later|since|remain|today|reaffirm|repudiat|abandon|transform|watershed|marked|began|ended|cornerstone|canonical|era|famous)/i;
my %nameKeys;   # how many decided cases share a "Party v. Party" key (e.g. several "Davis v. United States")
for my $c (@cases) { my $k = ckey($c->{n} // ''); $nameKeys{$k}++ if $k }
sub importance {
  my ($name, $decided, $year, $cit) = @_;
  my $ambiguous = ($nameKeys{ ckey($name) } // 0) > 1;
  my ($vol) = ($cit // '') =~ /^(\d+) U\.S\./;
  $vol //= 'NOVOLUME'; $year = 'NOYEAR' unless ($year // '') =~ /^\d{4}$/;
  my $disamb = qr/\b(?:$year|$vol U\.\s?S\.)/;
  my ($p1, $p2) = $name =~ /^(?:The )?(.+?) v\. (?:The )?(.+)$/ or return ('', '');
  my $f1 = ($p1 =~ /^([A-Z][\w'&.-]+)/)[0] // return ('', ''); my $f2 = ($p2 =~ /^([A-Z][\w'&.-]+)/)[0] // return ('', '');
  my $full = qr/(?<![\w.])\Q$f1\E(?!\w)[^;]{0,60}? v\. (?:The )?\Q$f2\E(?!\w)/;
  my $short = $p1 =~ /^(United States|State|People|Commonwealth|[A-Z][a-z]+ (?:County|City))\b/ || $f1 =~ /^(?:Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|Ohio|Oklahoma|Oregon|Pennsylvania|Tennessee|Texas|Utah|Vermont|Virginia|Washington|Wisconsin|Wyoming)$/ ? $f2 : $f1;
  my $best = sub {
    my ($min, @paras) = @_; my ($top, $score) = ('', 0);
    for my $para (@paras) {
      next unless index($para, $f2) >= 0 && index($para, $f1) >= 0 && $para =~ $full;
      for my $s (sents($para)) {
        next unless $s =~ $full || $s =~ /(?<![\w.])\Q$short\E(?!\w)/;
        next if $ambiguous && $s !~ $disamb;
        my $w = words($s); next if $w < 10 || $w > 70;
        next if $s =~ /^(?:See|Cf|Id|Compare)\b/;
        next if $s =~ /\bCRS (?:Resources|Legal Sidebar|Report|In Focus|Insight)\b|^[^.;:]{0,60}[;:]\s/;   # CRS cross-reference lists; fragments that open mid-citation
        my $sc = (() = $s =~ /$SIG/g) * 2 + ($s =~ $full ? 1 : 0) - ($w > 50 ? 1 : 0);
        ($top, $score) = ($s, $sc) if $sc > $score;
      }
    }
    return $score >= $min ? $top : '';
  };
  my %num; my @crs = grep { !$decided || $_->[0] gt $decided } @crsText;
  $num{ $_->[2] } = $_->[1] for @crs;
  my $crs = $best->(2, map { $_->[2] } @crs);
  my ($crsNum) = $crs ? (grep { index($_->[2], $crs) >= 0 } @crs)[0][1] : ();
  return ($best->(2, @advText), $best->(2, @conText) || $best->(1, @conText), $crs, $crsNum);
}
sub clean_cite { my $s = shift // ""; $s =~ s/^\d{1,3}\s+(?=[A-Z])//; $s =~ s/^(?:Indeed|Thus|Moreover|However|Accordingly|Similarly|Likewise|Nonetheless|Nevertheless|Further|Furthermore|Also|And|But|So|Still|Again|Finally|Notably|Instead|Rather|Consequently|Hence|Therefore),?\s+(\w)/\u$1/; $s =~ s/\s+(\x{2019}s|'s)\b/$1/g; $s =~ s/,?\s*\d+\s+U\.\s?S\.\s+\d+(?:,\s*\d+(?:\x{2013}\d+)?)*(?:\s*\(\d{4}\))?//g; $s =~ s/\s*\(\d{4}\)//g; $s =~ s/\s+([,.;])/$1/g; $s =~ /^[^.;:]{0,60}[;:]\s/ ? '' : $s }
sub sec { my ($h, $body) = @_; $body ? "<div class=\"fc-sec\"><h4>$h</h4><p>$body</p></div>" : '' }
sub oyez { my $id = shift; my $f = 'data/raw/oyez/cases/' . ($id =~ s{/}{_}r) . '.json'; -e $f ? load($f) : undef }
my %STAT = (bg => 0, rs => 0, imp => 0, impNote => 0, impAdv => 0, impCon => 0);

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
  my $oy = oyez($c->{id});
  my $bg = tidy(background($oy && $oy->{facts_of_the_case}));
  my $why = tidy(reasoning($oy && $oy->{conclusion}, $hold || $official));
  my $vote = tidy(vote_line($oy));
  my $ruling = join(' ', grep { $_ } ($hold || $official), $why);
  $ruling .= "<span class=\"fc-vote\">$vote</span>" if $ruling && $vote;
  my ($impAdv, $impCon, $impCrs, $crsNum) = importance($name, $c->{dec}, $c->{y} // '', $c->{cit});
  $impCrs = '' if $impCon;
  my $note = $notes{ $c->{id} } ? tidy($notes{ $c->{id} }[0]) : '';
  my $imp = join(' ', grep { $_ } ($note ? "Known for: $note" . ($note =~ /[.!?]["\x{201D}\x{2019}']?$/ ? '' : '.') : ''), tidy(clean_cite($impAdv)), ($impAdv && $note ? '' : tidy(clean_cite($impCon || $impCrs))));
  my $usesCrs = $impCrs && !($impAdv && $note);
  $STAT{bg}++ if $bg; $STAT{rs}++ if $why; $STAT{imp}++ if $imp; $STAT{impNote}++ if $note; $STAT{impAdv}++ if $impAdv; $STAT{impCon}++ if $impCon; $STAT{impCrs}++ if $impCrs && !($impAdv && $note);
  my $usesCon = $impCon && !($impAdv && $note);
  my @src;
  push @src, "Background and ruling adapted from <a href=\"https://www.oyez.org/cases/$c->{id}\" target=\"_blank\" rel=\"noopener\">Oyez</a> (<a href=\"https://creativecommons.org/licenses/by-nc/4.0/\" target=\"_blank\" rel=\"noopener\">CC BY-NC 4.0</a>)" if $bg || $why || $hold;
  push @src, 'importance from ' . join(' and ', grep { $_ } (($note || $impAdv) ? "Lex Constitutio's doctrine notes" : ''), ($usesCon ? 'the <i>Constitution Annotated</i> (public domain)' : ''), ($usesCrs ? "the Congressional Research Service (<a href=\"https://crsreports.congress.gov/product/pdf/LSB/$crsNum\" target=\"_blank\" rel=\"noopener\">$crsNum</a>, public domain)" : '')) if $imp;
  my $srcLine = @src ? '<p class="fc-src">' . ucfirst(join('; ', @src)) . '.</p>' : '';
  my $three = sec('Background', $bg) . sec('Ruling', $ruling) . sec('Importance', $imp);
  push @mk, ['held', "What did the Court decide in <i>$label</i>?", "<div class=\"fc-secs\">$three</div>$srcLine"] if $ruling;
  if ($hold && length $hold > 40) { push @mk, ['which', 'Which case? ' . mask_parties($hold, $name), "<i>$label</i>" . ($c->{cit} ? " &middot; $c->{cit}" : '')] }
  if ($c->{q} && length($c->{q}) < 700 && $ruling) { push @mk, ['qp', "Question presented in <i>$label</i>: " . tidy($c->{q}), '<div class="fc-secs">' . sec('Ruling', $ruling) . sec('Importance', $imp) . "</div>$srcLine"] }
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
printf "three-part answers: background %d, reasoning %d, importance %d (doctrine notes %d, doctrine text %d, CONAN %d, CRS %d)
", @STAT{qw(bg rs imp impNote impAdv impCon impCrs)};
printf "  %-24s %3d cases %4d cards\n", $_->{id}, $_->{cases}, $_->{cards} for @decks;
