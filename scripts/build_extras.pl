#!/usr/bin/perl
# Builds docs/data/scotus.js, docs/data/lectures.js and docs/data/guide.js from the raw downloads
# (scotus.sh, youtube.sh, wiki.sh) plus scripts/guide.json and docs/data/articles.js.
# Usage: perl scripts/build_extras.pl   (run from the project root, after build.ps1)
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my $J = JSON::PP->new->utf8->canonical;

sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; $s }
sub strip_html { my $s = shift // ''; $s =~ s/<[^>]+>/ /g; $s =~ s/&nbsp;/ /g; $s =~ s/&amp;/&/g; $s =~ s/&#39;|&rsquo;/’/g; $s =~ s/&quot;/"/g; $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s }
sub norm { my $s = lc(shift // ''); $s =~ s/&/and/g; $s =~ s/\b(the|inc|co|company|of|et al)\b//g; $s =~ s/[^a-z0-9]//g; $s }
sub write_js { my ($file, $var, $data) = @_; open my $o, '>:raw', $file or die "$file: $!"; print $o "window.$var=", $J->encode($data), ";"; close $o; printf "wrote %s (%.1f MB)\n", $file, (-s $file) / 1048576 }

# ------------------------------------------------------------------ Supreme Court
my %slip;   # docket -> { pdf, holding }
for my $f (glob 'data/raw/scotus/slip-*.html') {
  my $html = slurp($f); utf8::decode($html);   # pages are UTF-8
  while ($html =~ m{<tr>(.*?)</tr>}gs) {
    my $row = $1;
    my @td = $row =~ m{<td[^>]*>(.*?)</td>}gs;
    next unless @td >= 4;
    my ($docket) = strip_html($td[2]);
    my ($pdf, $title) = $row =~ m{href='(/opinions/\d+pdf/[^']+\.pdf)'[^>]*?title="([^"]*)"}s;
    next unless $pdf && $docket;
    $slip{lc $docket} = { pdf => "https://www.supremecourt.gov$pdf", holding => strip_html($title) };
  }
}
my %transcript;   # docket -> pdf
for my $f (glob 'data/raw/scotus/tr-*.html') {
  my $html = slurp($f); utf8::decode($html);
  while ($html =~ m{href=['"]?\.\./argument_transcripts/(\d{4})/([^'"\s>]+\.pdf)['"]?[^>]*>\s*([^<]+?)\s*</a>}gs) {
    my ($y, $file, $dk) = ($1, $2, lc $3);
    $transcript{$dk} //= "https://www.supremecourt.gov/oral_arguments/argument_transcripts/$y/$file";
  }
}
printf "slip opinions: %d, transcripts: %d\n", scalar(keys %slip), scalar(keys %transcript);

# light topical tagging for filtering (ids match the article taxonomy)
my @caseTags = (
  [speech => qr/first amendment|free speech|freedom of speech|freedom of the press|expressive|speech/i],
  [religion => qr/establishment clause|free exercise|religio/i],
  [guns => qr/second amendment|firearm|bear arms|\bguns?\b/i],
  [equality => qr/equal protection|discriminat|race|racial|segregat|affirmative action|sex-based|gender/i],
  [dueprocess => qr/due process|privacy|abortion|marriage|liberty interest|parental/i],
  [crimpro => qr/fourth amendment|fifth amendment|sixth amendment|eighth amendment|search|seizure|miranda|counsel|jury|cruel and unusual|death penalty|self-incrimination|confrontation|double jeopardy/i],
  [federalism => qr/tenth amendment|sovereign immunity|eleventh amendment|commerce clause|preempt|federalism|state sovereignty/i],
  [seppowers => qr/separation of powers|appointments clause|removal|executive power|president|nondelegation|delegat|congress(?:ional)? power/i],
  [admin => qr/agency|administrative|chevron|environmental protection agency|federal communications commission|regulation/i],
  [article3 => qr/standing|article iii|jurisdiction|moot|justiciab/i],
  [voting => qr/voting|election|ballot|redistricting|gerrymander|apportion|campaign/i],
  [takings => qr/taking|just compensation|eminent domain/i],
  [citizenship => qr/immigra|citizenship|deport|alien|asylum|tribal|indian/i],
  [security => qr/war powers|military|detain|guantanamo|national security|habeas/i],
);
my @cases;
for my $f (sort glob 'data/raw/oyez/term-*.json') {
  my $list = eval { decode_json(slurp($f)) } or next;
  for my $c (@$list) {
    my ($id) = ($c->{href} // '') =~ m{/cases/(.+)$} or next;
    my (%t);
    for my $ev (@{ $c->{timeline} || [] }) { next unless $ev && $ev->{dates} && @{ $ev->{dates} }; $t{$ev->{event}} = $ev->{dates}[-1] }
    my $decided = $t{Decided};
    my @d = $decided ? gmtime($decided) : ();
    my $cit = $c->{citation} || {};
    my $vol = $cit->{volume}; my $page = $cit->{page};
    my $dk = lc($c->{docket_number} // '');
    my %o = (id => $id, n => strip_html($c->{name}), t => $c->{term}, d => $c->{docket_number});
    $o{q} = strip_html($c->{question}) if $c->{question};
    $o{ds} = strip_html($c->{description}) if $c->{description};
    $o{dec} = sprintf('%04d-%02d-%02d', $d[5] + 1900, $d[4] + 1, $d[3]) if @d;
    $o{y} = @d ? $d[5] + 1900 : ($c->{term} =~ /^(\d{4})$/ ? $1 : undef);
    $o{arg} = 1 if $t{Argued};
    $o{cit} = "$vol U.S. " . ($page // '___') if $vol;
    $o{ju} = $c->{justia_url} if $c->{justia_url};
    if (my $s = $slip{$dk}) { $o{pdf} = $s->{pdf}; $o{h} = $s->{holding} }
    elsif ($vol && $vol =~ /^\d+$/ && $vol <= 576 && $page && $page =~ /^\d+$/) {
      my $k = sprintf('usrep%03d%03d', $vol, $page);
      $o{pdf} = sprintf('https://tile.loc.gov/storage-services/service/ll/usrep/usrep%03d/%s/%s.pdf', $vol, $k, $k);
    }
    $o{tr} = $transcript{$dk} if $transcript{$dk};
    my $text = join ' ', grep { defined } $o{n}, $o{q}, $o{ds}, $o{h};
    my @tg = map { $_->[0] } grep { $text =~ $_->[1] } @caseTags;
    $o{tg} = \@tg if @tg;
    $o{con} = 1 if $text =~ /constitution|amendment|clause|bill of rights/i;
    push @cases, \%o;
  }
}
@cases = sort { ($b->{dec} // '') cmp ($a->{dec} // '') } @cases;
printf "supreme court cases: %d (with pdf %d, with transcript pdf %d)\n", scalar @cases, scalar(grep { $_->{pdf} } @cases), scalar(grep { $_->{tr} } @cases);
write_js('docs/data/scotus.js', 'SCOTUS', { generated => scalar(localtime), cases => \@cases });

# ------------------------------------------------------------------ YouTube
my %embed;
for (split /\n/, slurp('data/raw/youtube/embeddable.tsv')) { my ($id, $ok) = split /\t/; $embed{$id} = $ok }
my $INSTITUTIONS = qr/^(National Constitution Center|The Federalist Society|American Constitution Society|Harvard Law School|Harvard University|Yale Law School|Yale University|YaleCourses|Stanford Law School|Stanford|Stanford GSB|Columbia Law School|Columbia University|NYU Law|NYU School of Law|University of Chicago Law School|UChicago|Georgetown Law|Georgetown University|Berkeley Law|UC Berkeley|Penn Carey Law|Penn Law|University of Michigan Law School|Michigan Law|Duke Law School|Duke Law|University of Virginia School of Law|UVA Law|Northwestern Pritzker School of Law|Cornell Law School|Hoover Institution|Brookings Institution|The Cato Institute|Cato Institute|The Heritage Foundation|Heritage Foundation|American Enterprise Institute|AEI|Hillsdale College|Hillsdale Digital|Khan Academy|CrashCourse|TED-Ed|C-SPAN|Library of Congress|Institute for Justice|Brennan Center for Justice|Bill of Rights Institute|Annenberg Classroom|Supreme Court Historical Society|Princeton University|James Madison Program|MIT OpenCourseWare|Notre Dame Law School|Vanderbilt Law School|UCLA School of Law|UCLA Law|Texas Law|Center for Civic Education|R\.H\. Smith Center for the Constituton|Open to Debate|Intelligence Squared US|Liberty Fund|Constitutional Accountability Center|American Bar Association|Federal Judicial Center|PBS NewsHour|Pacific Legal Foundation|Manhattan Institute|Claremont Institute|Ashbrook Center|ACLU|Constitution Center|icivics|iCivics)$/i;
my $EDU_PREF = qr/^(National Constitution Center|Khan Academy|CrashCourse|TED-Ed|Annenberg Classroom|Bill of Rights Institute|iCivics|Center for Civic Education|Hillsdale College|Hillsdale Digital|The Federalist Society|Institute for Justice)$/i;
my $RELEVANT = qr/constitution|amendment|court|justice|\blaw\b|clause|federalis|(?:separation of|executive|presidential|war|congressional) powers?|rights|speech|religio|originalis|liberty|president|congress|judicial|equal|due process|search|\bvot|elect|\bguns?\b|bear arms|takings|privacy|founding|federal|marbury|scotus/i;
sub secs { my $l = shift // ''; my @p = split /:/, $l; my $s = 0; $s = $s * 60 + $_ for grep { /^\d+$/ } @p; $s }
sub views { my $v = shift // ''; $v =~ s/[^\d]//g; $v || 0 }
my (%vid, %guideVids);
for my $line (split /\n/, slurp('data/raw/youtube/results.tsv')) {
  utf8::decode($line);
  my ($kind, $label, $query, $id, $title, $ch, $chid, $len, $views, $pub) = split /\t/, $line;
  next unless $id && $title && ($embed{$id} // '') eq 'ok';
  my $s = secs($len);
  if ($kind eq 'guide') {
    next unless $ch && $ch =~ $INSTITUTIONS && $s >= 90 && $s <= 40 * 60;
    push @{ $guideVids{$label} }, { id => $id, t => $title, ch => $ch, len => $len, v => views($views), pref => ($ch =~ $EDU_PREF ? 1 : 0) };
    next;
  }
  next unless $ch && $ch =~ $INSTITUTIONS && $s >= 5 * 60 && $title =~ $RELEVANT;
  my $v = $vid{$id} //= { id => $id, t => $title, ch => $ch, len => $len, sec => $s, v => views($views), pub => $pub, cat => [] };
  push @{ $v->{cat} }, $label unless grep { $_ eq $label } @{ $v->{cat} };
}
my @videos = sort { $b->{v} <=> $a->{v} } values %vid;
my %catCount; $catCount{$_}++ for map { @{ $_->{cat} } } @videos;
my @cats = sort { $catCount{$b} <=> $catCount{$a} } keys %catCount;
my %chCount; $chCount{$_->{ch}}++ for @videos;
printf "lectures: %d videos, %d channels\n", scalar @videos, scalar keys %chCount;
write_js('docs/data/lectures.js', 'LECTURES', { categories => \@cats, channels => [map { { name => $_, n => $chCount{$_} } } sort { $chCount{$b} <=> $chCount{$a} } keys %chCount], videos => \@videos });

# ------------------------------------------------------------------ Beginner's guide
my $guide = decode_json(slurp('scripts/guide.json'));
my $artJs = slurp('docs/data/articles.js'); $artJs =~ s/^window\.CL_DATA=//; $artJs =~ s/;\s*$//;
my $arts = decode_json($artJs)->{articles};
my %caseByName;
for my $c (@cases) { push @{ $caseByName{norm($c->{n})} }, $c }
my $PRIMER = qr/introduct|primer|overview|guide|history of|origins?|meaning of|foundations?|understanding|what is|the case for|essay on|theory of/i;
my @topicsOut;
for my $g (@$guide) {
  my $w = eval { decode_json(slurp("data/raw/wiki/$g->{id}.json")) } || {};
  my %o = (id => $g->{id}, title => $g->{title}, group => $g->{group}, tagline => $g->{tagline}, topics => $g->{topics});
  if ($w->{extract}) { $o{wiki} = { text => $w->{extract}, title => $w->{title}, url => $w->{content_urls}{desktop}{page} } }
  $o{wex} = "https://www.law.cornell.edu/wex/$g->{wex}" if $g->{wex};
  $o{books} = $g->{books} || [];
  # videos: educational explainer channels first, then by views; at most one per channel
  my (%seenCh, %seenId, @v);
  my $vrx = qr/$g->{articleRx}|\Q$g->{title}\E/i;
  my @pool = @{ $guideVids{$g->{id}} || [] };
  my @onTopic = grep { $_->{t} =~ $vrx } @pool;
  @pool = @onTopic if @onTopic >= 2;
  for my $x (sort { $b->{pref} <=> $a->{pref} || $b->{v} <=> $a->{v} } @pool) {
    next if $seenCh{$x->{ch}}++ || $seenId{$x->{id}}++;
    push @v, { id => $x->{id}, t => $x->{t}, ch => $x->{ch}, len => $x->{len} };
    last if @v == 3;
  }
  $o{videos} = \@v;
  # cases
  my @c;
  for my $want (@{ $g->{cases} }) {
    my ($name, $year) = @$want;
    my $cands = $caseByName{norm($name)} || [];
    my ($best) = sort { abs(($a->{y} // 0) - $year) <=> abs(($b->{y} // 0) - $year) } @$cands;
    if ($best && abs(($best->{y} // $year) - $year) <= 2) { push @c, { id => $best->{id}, n => $best->{n}, y => $best->{y}, cit => $best->{cit} } }
    else { print "  guide $g->{id}: no Oyez match for $name ($year)\n"; push @c, { n => $name, y => $year } }
  }
  $o{cases} = \@c;
  # articles: topic match + title match, weighted toward cited and accessible pieces
  my %tp = map { $_ => 1 } @{ $g->{topics} };
  my $rx = qr/$g->{articleRx}/i;
  my @scored;
  for my $a (@$arts) {
    next if $a->{rv};
    next unless grep { $tp{$_} } @{ $a->{tp} || [] };
    next unless $a->{t} =~ $rx;
    my $s = 2 * log(1 + ($a->{c} // 0)) + ($a->{ab} ? 1.5 : 0) + ($a->{t} =~ $PRIMER ? 3 : 0) + (($a->{y} // 0) >= 1985 ? 1 : 0) + (length($a->{t}) < 90 ? 0.5 : 0);
    push @scored, [$s, $a];
  }
  my (%seenAu, @picked);
  for my $x (sort { $b->[0] <=> $a->[0] } @scored) {
    my $au = join ';', @{ $x->[1]{a} || [] };
    next if $au && $seenAu{$au}++;
    push @picked, $x->[1]{id};
    last if @picked == 5;
  }
  $o{articles} = \@picked;
  push @topicsOut, \%o;
}
write_js('docs/data/guide.js', 'GUIDE', { topics => \@topicsOut });

# ------------------------------------------------------------------ Books
# Metadata: scripts/books.json (curated) + Open Library + Goodreads (scripts/books.sh).
# Law-journal reviews are matched against the article index by title and author.
my %PUBLISHER_SITE = (
  'Harvard University Press' => 'hup.harvard.edu', 'Oxford University Press' => 'global.oup.com', 'Yale University Press' => 'yalebooks.yale.edu',
  'Princeton University Press' => 'press.princeton.edu', 'University of Chicago Press' => 'press.uchicago.edu', 'University of North Carolina Press' => 'uncpress.org',
  'University Press of Kansas' => 'kansaspress.ku.edu', 'University of Michigan Press' => 'press.umich.edu', 'NYU Press' => 'nyupress.org',
  'Knopf' => 'penguinrandomhouse.com', 'Random House' => 'penguinrandomhouse.com', 'Doubleday' => 'penguinrandomhouse.com', 'Viking' => 'penguinrandomhouse.com',
  'Crown Forum' => 'penguinrandomhouse.com', 'Penguin Books' => 'penguinrandomhouse.com', 'Penguin Classics' => 'penguinrandomhouse.com',
  'W. W. Norton' => 'wwnorton.com', 'Simon & Schuster' => 'simonandschuster.com', 'Free Press' => 'simonandschuster.com',
  'Basic Books' => 'hachettebookgroup.com', 'Twelve' => 'hachettebookgroup.com', 'Little, Brown and Company' => 'hachettebookgroup.com',
  'Farrar, Straus and Giroux' => 'us.macmillan.com', 'Houghton Mifflin' => 'harpercollins.com', 'Houghton Mifflin Harcourt' => 'harpercollins.com',
  'Harper & Row' => 'harpercollins.com', 'Harper & Brothers' => 'harpercollins.com', 'Polity' => 'politybooks.com', 'Aspen Publishing' => 'aspenpublishing.com',
  'Thomson/West' => 'store.legal.thomsonreuters.com', 'Macmillan' => 'gutenberg.org',
);
sub uri { my $s = shift; utf8::encode($s) if utf8::is_utf8($s); $s =~ s/([^A-Za-z0-9\-_.~ ])/sprintf('%%%02X', ord $1)/ge; $s =~ s/ /+/g; $s }
my $books = decode_json(slurp('scripts/books.json'));
my %by_id = map { $_->{id} => $_ } @$arts;
my %guideFor;
for my $g (@$guide) { push @{ $guideFor{$_} }, { id => $g->{id}, title => $g->{title} } for @{ $g->{books} || [] } }
my @booksOut;
for my $bk (@$books) {
  my ($last) = $bk->{authors}[0] =~ /(\S+?)(?:,? (?:Jr|Sr)\.?)?$/;
  my $lastRx = qr/\Q$last\E/i;
  my ($main) = split /:/, $bk->{title};
  my %o = (%$bk);
  # Open Library: the work by the right author with the most editions
  my $ol = eval { decode_json(slurp("data/raw/books/$bk->{id}.ol.json")) } || {};
  my ($best) = sort { ($b->{edition_count} // 0) <=> ($a->{edition_count} // 0) }
    grep { grep { $_ =~ $lastRx } @{ $_->{author_name} || [] } } @{ $ol->{docs} || [] };
  if ($best) {
    $o{ol} = "https://openlibrary.org$best->{key}";
    $o{cover} = "https://covers.openlibrary.org/b/id/$best->{cover_i}-L.jpg" if $best->{cover_i};
    my ($isbn) = grep { /^97[89]\d{10}$/ } @{ $best->{isbn} || [] };
    $o{isbn} = $isbn if $isbn;
    $o{pages} = $best->{number_of_pages_median} if $best->{number_of_pages_median};
  }
  # Goodreads: the matching edition with the most ratings
  my $gr = eval { decode_json(slurp("data/raw/books/$bk->{id}.gr.json")) } || [];
  my $mainNorm = norm($main);
  my ($g) = sort { ($b->{ratingsCount} // 0) <=> ($a->{ratingsCount} // 0) }
    grep { ($_->{author}{name} // '') =~ $lastRx && index(norm($_->{bookTitleBare} // $_->{title}), substr($mainNorm, 0, 12)) >= 0 } @$gr;
  if ($g && ($g->{ratingsCount} // 0) >= 20) {
    $o{gr} = { rating => $g->{avgRating} + 0, count => $g->{ratingsCount} + 0, url => "https://www.goodreads.com$g->{bookUrl}" };
    $o{gr}{url} =~ s/\?.*$//;
    if (!$o{cover} && $g->{imageUrl}) { (my $img = $g->{imageUrl}) =~ s/\._S[XY]\d+_//; $o{cover} = $img }
    if ($g->{description} && $g->{description}{html}) { my $d = strip_html($g->{description}{html}); $o{blurb} = $d if length $d > 60 }
  }
  # links
  my $q = $o{isbn} || "$main $last";
  $o{amazon} = 'https://www.amazon.com/s?k=' . uri($q) . '&i=stripbooks';
  if (my $site = $PUBLISHER_SITE{$bk->{publisher}}) {
    $o{pubUrl} = $site eq 'gutenberg.org' ? 'https://www.gutenberg.org/ebooks/search/?query=' . uri($main)
      : 'https://www.google.com/search?q=' . uri("site:$site \"$main\"");
  }
  $o{pubUrl} = 'https://guides.loc.gov/federalist-papers/full-text' if $bk->{id} eq 'federalist';
  # law-journal reviews and discussions from the index
  my $mainLc = lc $main; $mainLc =~ s/[’']/'/g;
  my $minYear = $bk->{year} - 1;
  my @rev;
  my $fullLc = lc $bk->{title}; $fullLc =~ s/[’']/'/g;
  my $generic = (grep { index(lc $_->{t}, $mainLc) >= 0 } @$arts) > 6;
  for my $a (@$arts) {
    my $t = lc $a->{t}; $t =~ s/[’']/'/g;
    next unless index($t, $mainLc) >= 0;
    next if ($a->{y} // 9999) < $minYear;
    # JSTOR-style reviews are titled exactly as the book; others say "review" or name the author
    my $exact = $t eq $mainLc || $t eq $fullLc || index($fullLc, $t) == 0;
    my $saysReview = $t =~ /review|reviewing|reply|response|retrospective|revisited|after twenty|essay on/;
    my $byAuthor = grep { $_ =~ $lastRx } @{ $a->{a} || [] };
    my $namesAuthor = ($a->{t} =~ $lastRx) || (($a->{ab} // '') =~ $lastRx);
    my $ok;
    if ($generic) {   # common phrase ("Takings", "The Unitary Executive"): demand an explicit link to this book
      $ok = $a->{rv} || ($exact && ($byAuthor || $namesAuthor)) || ($a->{t} =~ $lastRx && !$byAuthor);
    } else {
      $exact &&= ($a->{rv} || $byAuthor || $namesAuthor || length($main) >= 20);
      $saysReview &&= ($namesAuthor || $byAuthor);
      $ok = $a->{rv} || $exact || $saysReview || ($namesAuthor && !$byAuthor);
    }
    next unless $ok;
    next if $byAuthor && !$exact && !$a->{rv} && $t !~ /retrospective|reply|response/;   # the book author's own later articles
    push @rev, $a->{id};
  }
  @rev = sort { ($by_id{$a}{y} // 0) <=> ($by_id{$b}{y} // 0) } @rev;
  $o{reviews} = [@rev[0 .. ($#rev < 11 ? $#rev : 11)]];
  $o{scholar} = 'https://scholar.google.com/scholar?q=' . uri("\"$main\" $last review");
  $o{jstor} = 'https://www.jstor.org/action/doBasicSearch?Query=' . uri("\"$main\" $last") . '&so=rel';
  $o{guide} = $guideFor{$bk->{id}} if $guideFor{$bk->{id}};
  push @booksOut, \%o;
}
printf "books: %d (with Goodreads %d, with cover %d, with index reviews %d; %d review links)\n", scalar @booksOut,
  scalar(grep { $_->{gr} } @booksOut), scalar(grep { $_->{cover} } @booksOut), scalar(grep { @{ $_->{reviews} } } @booksOut), scalar(map { @{ $_->{reviews} } } @booksOut);
my @bookCats = ('Introductions & Primers', 'Theory & Interpretation', 'History & Founding', 'The Supreme Court', 'Structure & Powers', 'Rights & Liberties', 'Democracy & Elections');
write_js('docs/data/books.js', 'BOOKS', { categories => \@bookCats, books => \@booksOut });
