#!/usr/bin/perl
# Builds docs/data/advanced.js from scripts/advanced/*.md.
#   - converts the light markup to HTML (paragraphs, lists, **bold**, *italic*, !test boxes)
#   - links !cases to Supreme Court case pages (docs/data/scotus.js)
#   - pulls !excerpt passages from the official opinion PDFs (pdftotext), falling back to Wikisource
#   - attaches the most-cited matching articles from docs/data/articles.js for !articles
# Usage: perl scripts/build_advanced.pl   (from the project root; needs pdftotext and curl)
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my $J = JSON::PP->new->utf8->canonical;
sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; $s }
sub norm { my $s = lc(shift // ''); $s =~ s/&/and/g; $s =~ s/\b(the|inc|co|company|of|et al|corp|corporation|llc)\b//g; $s =~ s/[^a-z0-9]//g; $s }
sub esc { my $s = shift // ''; $s =~ s/&/&amp;/g; $s =~ s/</&lt;/g; $s =~ s/>/&gt;/g; $s =~ s/"/&quot;/g; $s }
sub inline { my $s = esc(shift); $s =~ s/\*\*(.+?)\*\*/<strong>$1<\/strong>/g; $s =~ s/(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])/<em>$1<\/em>/g; $s }

# ------------------------------------------------------------------ reference data
my $sc = slurp('docs/data/scotus.js'); $sc =~ s/^window\.SCOTUS=//; $sc =~ s/;\s*$//;
my @cases = @{ decode_json($sc)->{cases} };
my %caseByName; push @{ $caseByName{ norm($_->{n}) } }, $_ for @cases;
sub find_case {
  my ($name, $year) = @_;
  my $c = $caseByName{ norm($name) } || [];
  unless (@$c) {   # loose match: every word of the wanted name appears
    my @w = grep { length > 2 } map { lc } ($name =~ /([A-Za-z]+)/g);
    $c = [ grep { my $n = lc $_->{n}; !grep { index($n, $_) < 0 } @w } @cases ];
  }
  my ($best) = sort { abs(($a->{y} // 0) - $year) <=> abs(($b->{y} // 0) - $year) } @$c;
  return $best && abs(($best->{y} // $year) - $year) <= 2 ? $best : undef;
}
my $ar = slurp('docs/data/articles.js'); $ar =~ s/^window\.CL_DATA=//; $ar =~ s/;\s*$//;
my @arts = grep { !$_->{rv} } @{ decode_json($ar)->{articles} };

# ------------------------------------------------------------------ opinion text
mkdir 'data/raw/opinions' unless -d 'data/raw/opinions';
sub opinion_text {
  my ($case) = @_;
  my $key = $case->{id}; $key =~ s/[^\w-]+/_/g;
  my $txt = "data/raw/opinions/$key.txt";
  return slurp($txt) if -s $txt;
  return '' unless $case->{pdf};
  my $pdf = "data/raw/opinions/$key.pdf";
  system('curl', '-s', '-L', '-m', '180', '-A', 'Mozilla/5.0 ConLawIndex/1.0', '-o', $pdf, $case->{pdf}) unless -s $pdf;
  return '' unless -s $pdf && slurp($pdf) =~ /^%PDF/;
  system('pdftotext', '-q', '-enc', 'UTF-8', $pdf, $txt);
  sleep 1;
  return slurp($txt);
}
sub wikisource_text {
  my ($name) = @_;
  my $file = 'data/raw/opinions/ws_' . norm($name) . '.txt';
  return slurp($file) if -s $file;
  my $q = $name; $q =~ s/([^A-Za-z0-9])/sprintf('%%%02X', ord $1)/ge;
  my $list = `curl -s -m 60 -A "ConLawIndex/1.0 (educational project)" "https://en.wikisource.org/w/api.php?action=query&list=prefixsearch&pssearch=$q&pslimit=20&format=json"`;
  my @titles = ($list =~ /"title":"([^"]+)"/g);
  my ($page) = (grep { /Opinion of the Court$/ } @titles), (grep { !/\// } @titles);
  # Wikisource titles abbreviate ("New York Times Co. v. Sullivan"); try that spelling before giving up
  if (!$page && $name =~ /\b(?:Company|Corporation|Incorporated)\b/) {
    (my $alt = $name) =~ s/\bCompany\b/Co./; $alt =~ s/\bCorporation\b/Corp./; $alt =~ s/\bIncorporated\b/Inc./;
    my $t = wikisource_text($alt); return $t;
  }
  return '' unless $page;
  $page =~ s/\\u(\w{4})/chr(hex $1)/ge;
  my $p = $page; utf8::encode($p); $p =~ s/([^A-Za-z0-9])/sprintf('%%%02X', ord $1)/ge;
  sleep 2;
  my $raw = `curl -s -m 60 -A "ConLawIndex/1.0 (educational project)" "https://en.wikisource.org/w/api.php?action=parse&page=$p&prop=text&format=json&formatversion=2"`;
  my $d = eval { decode_json($raw) } or return '';
  my $h = $d->{parse}{text} // '';
  $h =~ s{<style\b.*?</style>}{}gs; $h =~ s{<div class="wst-header.*?</div>\s*</div>}{}s;
  $h =~ s/<sup[^>]*>.*?<\/sup>//gs; $h =~ s/<[^>]+>/ /g; $h =~ s/&#(\d+);/chr($1)/ge; $h =~ s/&amp;/&/g; $h =~ s/&quot;/"/g; $h =~ s/&nbsp;/ /g;
  open my $o, '>:encoding(UTF-8)', $file; print $o $h; close $o;
  sleep 2;
  return slurp($file);
}
# Recent slip-opinion PDFs lose fi/fl/ff ligatures in text extraction ("frearm", "efect", "fag").
# Repair words that are unknown by restoring a ligature when that yields a word seen in the clean
# (pre-2017, Library of Congress) opinion texts.
my %VOCAB;
sub vocab {
  return \%VOCAB if %VOCAB;
  for my $f (glob 'data/raw/opinions/*.txt') {
    next unless $f =~ m{/(\d{4})[_-]} && $1 < 2015 || $f =~ m{/\d{4}-\d{4}_};
    my $t = lc slurp($f); $VOCAB{$_}++ for ($t =~ /([a-z]{3,})/g);
  }
  delete @VOCAB{ grep { $VOCAB{$_} < 2 } keys %VOCAB };
  \%VOCAB;
}
sub fix_ligatures {
  my $t = shift; my $v = vocab();
  $t =~ s{\b([A-Za-z]*f[A-Za-z]*)\b}{
    my $w = $1; my $lw = lc $w;
    if ($v->{$lw} || length($w) < 3) { $w }
    else {
      my $fixed;
      OUTER: for my $i (grep { substr($lw, $_, 1) eq 'f' } 0 .. length($lw) - 1) {
        for my $lig (qw(fi fl ff ffi ffl)) { my $c = substr($lw, 0, $i) . $lig . substr($lw, $i + 1); if ($v->{$c}) { $fixed = $c; last OUTER } }
      }
      $fixed ? ($w =~ /^[A-Z]/ ? ucfirst $fixed : $fixed) : $w;
    }
  }ge;
  $t
}
sub clean_text {
  my $t = shift; utf8::decode($t) unless utf8::is_utf8($t);
  $t =~ s/\x{AD}\s*//g;                                  # soft hyphens
  $t = fix_ligatures($t) if $t =~ /\b(frst|efect|frearm|justifcation|fnd)\b/;
  $t =~ s/\r//g; $t =~ s/\f/\n/g;                       # pdftotext on Windows writes CRLF
  $t =~ s/-\n\s*([a-z])/$1/g;                         # rejoin hyphenated line breaks
  $t =~ s/\n\s*\d{1,4}\s+(?:CASES? (?:ADJUDGED|IN THE SUPREME COURT)|SUPREME COURT)[^\n]*\n/\n/g;   # old running heads
  $t =~ s/\n\s*\d{1,4}\s*\n/\n/g;                       # bare page numbers
  $t =~ s/\n[^\n]{0,60}(OCTOBER TERM|Opinion of the Court|Cite as:|U\. ?S\.)[^\n]{0,60}\n/\n/g;   # running heads
  $t =~ s/[ \t]*\n[ \t]*/ /g; $t =~ s/\s+/ /g;
  $t =~ s/\s*Page Proof Pending Publication\s*\d*\s*/ /g;              # slip-opinion page footer
  $t =~ s/\s*\[p\d+\]\s*/ /g;                                          # Wikisource page markers ("[p495]")
  $t =~ s/\b([A-Za-z]{2,})- ([a-z]{2,})\b/$1$2/g;                      # a word hyphenated at a line end: "Pro- tection"
  $t =~ s/(?<=[a-z)][,.;"])\d{1,2}(?=\s)//g;                            # footnote numbers: "Carolina,3 quoted", "J.).4 In"
  # a running head ("MATHEWS v. ELDRIDGE") that landed inside a word hyphenated across pages: "de- MATHEWS v. ELDRIDGE cisions"
  $t =~ s/\b([a-z]+)- (?:[A-Z][A-Z.,'&]+ )+v\. (?:[A-Z][A-Z.,'&]+ )*?([a-z]+)/$1$2/g;
  $t =~ s/[\x{2018}\x{2019}]/'/g; $t =~ s/[\x{201C}\x{201D}]/"/g;
  $t
}
sub junk_score {
  my $t = shift; my $n = 0;
  $n++ while $t =~ /°|\boniy\b|\.\s+[a-z]|\b[A-Za-z]+\.\s*§|[a-z][,.;"]\d{1,2}\s|\bv\.\s*$/g;
  $n += 2 if $t =~ /^(?:See\b|[A-Z][\w.']+, (?:\d|On )|[a-z])/;
  $n
}
sub find_excerpt {
  my ($text, $anchor) = @_;
  my @w = ($anchor =~ /([A-Za-z0-9]+)/g);
  my $rx = join "[^A-Za-z0-9]{0,12}", map { quotemeta } @w;
  # prefer a match inside the opinion itself rather than the syllabus
  my $opStart = $text =~ /delivered the opinion of the Court|announced the judgment of the Court/ ? $-[0] : 0;
  pos($text) = $opStart;
  my ($s, $e);
  if ($text =~ /$rx/gi) { ($s, $e) = ($-[0], $+[0]) }
  elsif ($text =~ /$rx/i) { ($s, $e) = ($-[0], $+[0]) }
  else { return undef }
  # back up to the start of the sentence (and include one more sentence of context when short)
  my $pre = substr($text, ($s > 600 ? $s - 600 : 0), ($s > 600 ? 600 : $s));
  my @starts; push @starts, $+[0] while $pre =~ /(?<!\bv)(?<!\b[A-Z])(?<!\bMr)(?<!\bNo)(?<!\bId)(?<!\bSt)(?<!\bCo)(?<!\bJr)(?<!\bU\.S)[.!?]["')\]]?\s+(?=["'(]?[A-Z])/g;   # skip "v.", initials and legal abbreviations
  my $back = @starts ? (length($pre) - $starts[-1]) : length($pre);
  if (@starts >= 2 && $back < 140) { $back = length($pre) - $starts[-2] }
  my $start = $s - $back;
  # run forward to the end of the sentence, plus one more if short
  my $post = substr($text, $e, 900);
  # (the same abbreviation guards as above, so an excerpt never stops at "Palko v." or "458 U.")
  my @ends; push @ends, $+[0] while $post =~ /(?<!\bv)(?<!\b[A-Z])(?<!\bMr)(?<!\bNo)(?<!\bId)(?<!\bid)(?<!\bSt)(?<!\bCo)(?<!\bJr)(?<!\bUniv)(?<!\bDist)(?<!\bSch)(?<!\bDept)(?<!\bU\.S)[.!?]["')\]]?(?=\s+["'(]?[A-Z]|\s*$)/g;
  my $fwd = @ends ? $ends[0] : length($post);
  $fwd = $ends[1] if @ends > 1 && ($e - $start + $fwd) < 350;
  my $out = substr($text, $start, $e - $start + $fwd);
  $out =~ s/^\W+//; $out =~ s/\s+/ /g;
  # drop leading citation fragments left by abbreviations such as "U. S." ("S. 737, 751 (1984). Over the years…")
  $out =~ s/^(?:[^.]{0,60}?\d[^.]{0,40}?\(\d{4}\)\.\s+)+(?=[A-Z])//;
  $out =~ s/^(?:S\.|U\. ?S\.|Id\.|id\.)\s*[\d, ]*(?:\(\d{4}\))?\.?\s*(?=[A-Z])//;
  $out =~ s/^(?:Id\.|id\.|Ibid\.)\s*,?\s*(?:at\s*)?[\d\x{2013}\-, ]*\.?\s*(?=[A-Z])//;
  # the tail of an earlier sentence's citation string ("Arnett v. Kennedy, supra, at 167-168 (...); Goldberg ..., at 263.")
  # an excerpt that opens inside a citation string or a page head ("Brief for Respondents 50.", "See, e. g., Allen v.
  # Wright, 468 U. S. 737 (1984).", "UNITED STATES v. VIRGINIA the closest guide.") starts at the first prose sentence
  $out =~ s/^[A-Z][A-Z.,'& ]+ v\. [A-Z][A-Z.,'& ]+?\s+\d*\s*(?:[A-Z]\s+)?(?=[A-Z][a-z])//;   # a page head: "PERRY ED. ASSN. v. PERRY LOCAL EDUCATORS' ASSN. 45 A"
  for my $pass (1 .. 4) {
    last unless $out =~ /^(?:See\b|see\b|Brief\b|[A-Z][A-Z .]+ v\. [A-Z]|.{0,80}?\b(?:supra|U\. ?S\.,? (?:at )?\d|at \d)|[A-Z][\w'.]+, (?:\d|On )|Loving\b|Mill\b)/;
    last unless $out =~ /^(.{0,600}?(?:\d[^.]{0,40}|\)|\d\)))\.["')]?\s+(?=(?:[A-Z][a-z]+)(?:,| [a-z]))/s;
    $out = substr($out, length $1); $out =~ s/^[."')]*\s+//;
  }
  # a footnote mark glued to a word ("all that Congress can delegate2 In these cir- 'A Hamilton...") means the scan's
  # footnote text follows: the excerpt ends at the mark
  $out = "$1." if $out =~ /^(.{120,}?[a-z])\d{1,2}\s+[A-Z'"]/s;
  $out =~ s/\.\s+[IVX]{1,4}\s+(?=[A-Z][a-z])/. /g;                      # a section numeral between sentences ("itself. III Like")
  $out =~ s/\s*" `\[T\]he line' "\s*/ /;                                 # an unclosed quotation fragment in the slip opinion
  $out =~ s/\s*\b\d{1,3}\s*(?=[A-Z])//g if length $out > 0 && 0;
  return length($out) > 1400 ? substr($out, 0, 1400) . "\x{2026}" : $out;
}

# ------------------------------------------------------------------ parse markup
my (@parts, $part, $sec);
my ($mode, @buf, $testTitle) = ('');
my %stats = (excerpts => 0, excerptsMissing => 0, casesLinked => 0, cases => 0);
my @missing;
sub flush_para {
  return unless @buf;
  my $html = '';
  my @lines = @buf; @buf = ();
  my ($list, $ltype) = ([], '');
  my $close = sub { if (@$list) { $html .= "<$ltype>" . join('', map { "<li>$_</li>" } @$list) . "</$ltype>"; $list = [] } };
  my $para = '';
  for my $l (@lines) {
    if ($l =~ /^\s{2,}[-*]\s+(.*)/ && @$list) { $list->[-1] .= "<ul><li>" . inline($1) . "</li></ul>"; $list->[-1] =~ s/<\/ul><ul>//g; next }
    if ($l =~ /^\s*[-*]\s+(.*)/) { if ($para) { $html .= "<p>$para</p>"; $para = '' } $close->() if $ltype ne 'ul'; $ltype = 'ul'; push @$list, inline($1); next }
    if ($l =~ /^\s*\d+\.\s+(.*)/) { if ($para) { $html .= "<p>$para</p>"; $para = '' } $close->() if $ltype ne 'ol'; $ltype = 'ol'; push @$list, inline($1); next }
    if ($l =~ /^\s*$/) { $close->(); if ($para) { $html .= "<p>$para</p>"; $para = '' } next }
    if (@$list && $l =~ /^\s{3,}\S/) { $list->[-1] .= ' ' . inline($l =~ s/^\s+//r); next }
    $close->(); $para .= ($para ? ' ' : '') . inline($l);
  }
  $close->(); $html .= "<p>$para</p>" if $para;
  return $html;
}
for my $f (sort glob 'scripts/advanced/*.md') {
  open my $fh, '<:encoding(UTF-8)', $f or die;
  while (my $line = <$fh>) {
    chomp $line; $line =~ s/\r$//;
    if ($mode eq 'test') {
      if ($line =~ /^!end/) { my $h = flush_para(); $sec->{html} .= '<div class="testbox"><div class="testbox-h">' . inline($testTitle) . "</div>$h</div>"; $mode = ''; next }
      push @buf, $line; next;
    }
    if ($mode eq 'cases') {
      if ($line =~ /^!end/) { $mode = ''; next }
      next unless $line =~ /\S/;
      my ($n, $y, $note) = map { s/^\s+|\s+$//gr } split /\|/, $line, 3;
      my $c = find_case($n, $y); $stats{cases}++;
      my %o = (n => $n, y => $y + 0, note => $note);
      if ($c) { $o{id} = $c->{id}; $o{cit} = $c->{cit} if $c->{cit}; $stats{casesLinked}++ } else { push @missing, "case: $n ($y)" }
      push @{ $sec->{cases} }, \%o; next;
    }
    if ($line =~ /^# (\S+) \| (.+)$/) { $sec->{html} .= flush_para() if $sec; $part = { id => $1, title => $2, sections => [] }; push @parts, $part; $sec = undef; next }
    if ($line =~ /^\@summary (.+)$/) { $part->{summary} = $1; next }
    if ($line =~ /^## (\S+) \| (.+)$/) { $sec->{html} .= flush_para() if $sec; $sec = { id => $1, title => $2, html => '', cases => [], excerpts => [], corner => [], articles => [] }; push @{ $part->{sections} }, $sec; next }
    next unless $sec;
    if ($line =~ /^!test (.+)$/) { $sec->{html} .= flush_para(); $testTitle = $1; $mode = 'test'; next }
    if ($line =~ /^!cases/) { $sec->{html} .= flush_para(); $mode = 'cases'; next }
    if ($line =~ /^!corner (.+)$/) { $sec->{corner} = [ split /\s*,\s*/, $1 ]; next }
    if ($line =~ /^!articles (.+)$/) {
      my $rx = qr/$1/i;
      my @m = sort { ($b->{c} // -1) <=> ($a->{c} // -1) || ($b->{y} // 0) <=> ($a->{y} // 0) } grep { $_->{t} =~ $rx } @arts;
      $sec->{articles} = [ map { $_->{id} } @m[0 .. ($#m < 5 ? $#m : 5)] ];
      next;
    }
    if ($line =~ /^!excerpt (.+?) \| (\d{4}) \| (.+)$/) {
      my ($n, $y, $anchor) = ($1, $2, $3);
      my $c = find_case($n, $y);
      my ($text, $src);
      my $fromPdf = sub { return unless $c; my $t = opinion_text($c); return unless $t; $text = find_excerpt(clean_text($t), $anchor);
        $src = ($c->{pdf} // '') =~ /loc\.gov/ ? 'U.S. Reports (Library of Congress)' : 'Slip opinion (supremecourt.gov)' if $text };
      my $fromWs = sub { my $t = wikisource_text($n); return unless $t; $text = find_excerpt(clean_text($t), $anchor); $src = 'Wikisource (public-domain transcription)' if $text };
      # older scans have noisy OCR, so prefer Wikisource's proofread transcriptions for them
      if ($y < 1950) { $fromWs->(); $fromPdf->() unless $text } else { $fromPdf->(); $fromWs->() unless $text }
      # an OCR'd excerpt with footnote debris, a lowercase sentence start or an opening citation string: take the
      # Wikisource transcription of the same passage if it is cleaner
      if ($text && junk_score($text) > 0) {
        my ($t1, $s1) = ($text, $src);
        $text = undef; ($y < 1950 ? $fromPdf : $fromWs)->();
        ($text, $src) = ($t1, $s1) unless $text && junk_score($text) < junk_score($t1);
      }
      if ($text) { push @{ $sec->{excerpts} }, { n => $c ? $c->{n} : $n, y => $y + 0, id => $c ? $c->{id} : undef, cit => $c ? $c->{cit} : undef, pdf => $c ? $c->{pdf} : undef, t => $text, src => $src }; $stats{excerpts}++ }
      else { $stats{excerptsMissing}++; push @missing, "excerpt: $n ($y): $anchor" }
      next;
    }
    $sec->{html} .= flush_para() if $line =~ /^\s*$/ && @buf && $buf[-1] =~ /^\s*$/;
    push @buf, $line;
  }
  $sec->{html} .= flush_para() if $sec;
  close $fh;
}
printf "parts: %d, sections: %d, cases linked %d/%d, excerpts %d (missing %d)\n", scalar @parts, scalar(map { @{ $_->{sections} } } @parts), $stats{casesLinked}, $stats{cases}, $stats{excerpts}, $stats{excerptsMissing};
print "  - $_\n" for @missing;
open my $o, '>:raw', 'docs/data/advanced.js' or die; print $o 'window.ADVANCED=', $J->encode({ parts => \@parts }), ';'; close $o;
printf "wrote docs/data/advanced.js (%.2f MB)\n", (-s 'docs/data/advanced.js') / 1048576;
