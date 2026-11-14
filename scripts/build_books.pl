#!/usr/bin/perl
# Builds docs/data/books.js from scripts/books.json + Open Library + Goodreads (scripts/books.sh), with law-journal reviews
# matched from docs/data/articles.js. Split out of build_extras.pl so the books can be rebuilt on their own.
# Books that Open Library cannot match (title + first author) are dropped unless marked essential; see the printed list.
# Usage: perl scripts/build_books.pl   (then perl scripts/books_impact_merge.pl)
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my $J = JSON::PP->new->utf8->canonical;

sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; $s }
sub strip_html { my $s = shift // ''; $s =~ s/<[^>]+>/ /g; $s =~ s/&nbsp;/ /g; $s =~ s/&amp;/&/g; $s =~ s/&#39;|&rsquo;/’/g; $s =~ s/&quot;/"/g; $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s }
sub norm { my $s = lc(shift // ''); $s =~ s/&/and/g; $s =~ s/\b(the|inc|co|company|of|et al)\b//g; $s =~ s/[^a-z0-9]//g; $s }
sub write_js { my ($file, $var, $data) = @_; open my $o, '>:raw', $file or die "$file: $!"; print $o "window.$var=", $J->encode($data), ";"; close $o; printf "wrote %s (%.1f MB)\n", $file, (-s $file) / 1048576 }

# ------------------------------------------------------------------ Beginner's guide
my $guide = decode_json(slurp('scripts/guide.json'));
my $artJs = slurp('docs/data/articles.js'); $artJs =~ s/^window\.CL_DATA=//; $artJs =~ s/;\s*$//;
my $arts = decode_json($artJs)->{articles};
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
my (@booksOut, @dropped);
for my $bk (@$books) {
  my ($last) = $bk->{authors}[0] =~ /(\S+?)(?:,? (?:Jr|Sr)\.?)?$/;
  my $lastRx = qr/\Q$last\E/i;
  my ($main) = split /:/, $bk->{title};
  my %o = (%$bk);
  # Open Library: the work by the right author with the most editions
  my $ol = eval { decode_json(slurp("data/raw/books/$bk->{id}.ol.json")) } || {};
  my $mainKey = substr(norm($main), 0, 14);
  my ($best) = sort { ($b->{edition_count} // 0) <=> ($a->{edition_count} // 0) }
    grep { index(norm($_->{title} // ''), $mainKey) == 0 || index($mainKey, substr(norm($_->{title} // ''), 0, 14)) == 0 }
    grep { grep { $_ =~ $lastRx } @{ $_->{author_name} || [] } } @{ $ol->{docs} || [] };
  # verification: a book outside the curated essentials must match a real Open Library work (title and first author)
  if (!$best && !$bk->{essential}) { push @dropped, "$bk->{title} ($bk->{authors}[0])"; next }
  $o{year} = $best->{first_publish_year} if $best && !$bk->{essential} && $best->{first_publish_year} && abs($best->{first_publish_year} - $bk->{year}) <= 15;
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
  if (my $site = $PUBLISHER_SITE{$bk->{publisher} // q()}) {
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
printf "dropped %d books that Open Library could not verify:
  %s
", scalar @dropped, join("
  ", @dropped) if @dropped;
printf "books: %d (with Goodreads %d, with cover %d, with index reviews %d; %d review links)\n", scalar @booksOut,
  scalar(grep { $_->{gr} } @booksOut), scalar(grep { $_->{cover} } @booksOut), scalar(grep { @{ $_->{reviews} } } @booksOut), scalar(map { @{ $_->{reviews} } } @booksOut);
my @bookCats = ('Introductions & Primers', 'Theory & Interpretation', 'History & Founding', 'The Supreme Court', 'Structure & Powers', 'Rights & Liberties', 'Democracy & Elections');
write_js('docs/data/books.js', 'BOOKS', { categories => \@bookCats, books => \@booksOut });
