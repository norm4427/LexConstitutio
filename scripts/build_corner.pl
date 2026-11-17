#!/usr/bin/perl
# Builds the Originalist's Corner data from data/raw/corner (see scripts/corner.sh):
#   docs/data/corner.js        topics, sources, and the best passages per topic per source
#   docs/data/library-*.js     full texts readable on the site (Federalist, statutes, founding documents)
# Usage: perl scripts/build_corner.pl   (from the project root)
use strict; use warnings; use utf8;
use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
my $J = JSON::PP->new->utf8->canonical;
my $R = 'data/raw/corner';

sub slurp { my $f = shift; local $/; open my $h, '<:raw', $f or return ''; my $s = <$h>; $s }
sub dehtml {
  my $s = shift // '';
  $s =~ s/<(script|style)\b.*?<\/\1>//gis; $s =~ s/<sup\b[^>]*>.*?<\/sup>//gis;   # footnote markers
  $s =~ s/<br\s*\/?>/ /gi; $s =~ s/<[^>]+>//g;
  my %ent = (amp => '&', lt => '<', gt => '>', quot => '"', nbsp => ' ', rsquo => "\x{2019}", lsquo => "\x{2018}", ldquo => "\x{201C}", rdquo => "\x{201D}", mdash => "\x{2014}", ndash => "\x{2013}", sect => "\x{a7}", hellip => "\x{2026}", apos => "'");
  $s =~ s/&#(\d+);/chr($1)/ge; $s =~ s/&#x([0-9a-f]+);/chr(hex $1)/gie; $s =~ s/&(\w+);/exists $ent{$1} ? $ent{$1} : "&$1;"/ge;
  $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s
}
sub utf8dec { my $s = shift; utf8::decode($s) unless utf8::is_utf8($s); $s }
sub paras_from_html {
  my $h = utf8dec(shift);
  my @p = map { dehtml($_) } ($h =~ /<p\b[^>]*>(.*?)<\/p>/gis);
  grep { length($_) >= 60 && !/LONANG Library|Organic Documents Reference Works|Copyright|All rights reserved|Avalon Project|Yale Law School|Lillian Goldman|This work (?:was|is) (?:published|in the public domain)|public domain (?:worldwide|in the United States) because/i } @p;
}
sub write_js { my ($file, $var, $data) = @_; open my $o, '>:raw', $file or die "$file: $!"; print $o "window.$var=", $J->encode($data), ";"; close $o; printf "wrote %s (%.1f MB)\n", $file, (-s $file) / 1048576 }

# ------------------------------------------------------------------ topics
my @topics = (
  ['judicial-review', 'Judicial Review & the Judiciary', 'The judicial power, independence of judges, and voiding unconstitutional acts.', 'judicial power|judiciary|judges|courts of justice|repugnant to the constitution|void|good behaviou?r|supreme court|judicial department', 'repugnant to the constitution|judicial power|good behaviou?r|expositors? of the (law|constitution)'],
  ['separation', 'Separation of Powers', 'Dividing legislative, executive and judicial power, and the checks among them.', 'separat\w* of (the )?(powers|departments)|legislative,? executive,? and judicia|three (great )?(branches|departments)|checks? and balance|encroach', 'separat\w* of (the )?(powers|departments)|accumulation of all powers'],
  ['executive', 'Executive Power & the Presidency', 'The President, the King\'s prerogative, and the energy of the executive.', 'executive power|executive department|president|chief magistrate|prerogative|energy in the executive|veto|negative', 'energy in the executive|executive power|prerogative'],
  ['removal-appointments', 'Appointments & Removal', 'Who appoints officers, the Senate\'s role, and the power to remove.', 'appoint|removal|remove|nominat|officers of the united states|advice and consent', 'power of removal|appointment of officers|nominate, and by and with'],
  ['war', 'War, Militia & Standing Armies', 'Declaring war, raising armies, the militia, and the fear of standing armies.', 'declare war|declaring war|standing arm|militia|letters of marque|troops|war|army|armies', 'standing arm|declare war|power of war'],
  ['treaties', 'Treaties & Foreign Affairs', 'Making treaties, ambassadors, and the law of nations.', 'treat(y|ies)|ambassador|foreign nations|law of nations|foreign powers', 'treaty|law of nations'],
  ['commerce', 'Commerce & Trade', 'Regulating trade among the states and with foreign nations.', 'commerce|trade|navigation|imports?|exports?|tonnage|merchant', 'regulate commerce|commerce among|commerce with foreign'],
  ['taxing', 'Taxation, Spending & the General Welfare', 'The power to tax, requisitions, and spending for the general welfare.', 'tax|taxes|taxation|revenue|general welfare|appropriation|excise|imposts|requisition', 'general welfare|power of taxation|lay and collect'],
  ['necessary-proper', 'Necessary & Proper and Implied Powers', 'Means to carry granted powers into execution, and the "sweeping clause."', 'necessary and proper|implied powers?|incidental|sweeping clause|means', 'necessary and proper|sweeping clause|implied powers?'],
  ['federalism', 'Federalism & State Sovereignty', 'The division of sovereignty between the Union and the states.', 'sovereignty of the states|state governments|confedera|reserved|consolidat|state legislatures|federal government|the union', 'state sovereignty|sovereignty of the states|consolidat|reserved to the states'],
  ['supremacy', 'Supremacy of Federal Law', 'The supreme law of the land and conflicts with state law.', 'supreme law|supremacy|paramount|law of the land', 'supreme law of the land'],
  ['religion', 'Religion, Conscience & Establishment', 'Religious liberty, established churches, and liberty of conscience.', 'religio|church|establishment|worship|conscience|sect|clergy|test oath|religious test', 'establishment of religion|liberty of conscience|religious test|free exercise|freedom of religion'],
  ['speech-press', 'Speech, Press & Seditious Libel', 'Liberty of the press, prior restraint, and seditious libel.', 'liberty of the press|freedom of the press|freedom of speech|press|libel|sedition|seditious|printing', 'liberty of the press|freedom of the press|seditious libel|previous restraints?'],
  ['arms', 'Right to Bear Arms', 'Keeping and bearing arms, self-defense, and the militia.', 'bear arms|keep arms|arms|self[- ]defen[cs]e|weapons|fire-?arms|militia', 'bear arms|keep and bear|right of having arms|self[- ]defen[cs]e'],
  ['search', 'Searches, Seizures & Warrants', 'General warrants, searches of houses and papers.', 'search|seizure|warrant|general warrants?|houses|papers', 'general warrants?|search(es)? and seizures?|unreasonable search'],
  ['jury', 'Trial by Jury', 'The jury as the palladium of liberty.', 'trial by jury|jury|juries|jurors|petit|vicinage', 'trial by jury|palladium'],
  ['habeas', 'Habeas Corpus & Personal Liberty', 'The Great Writ and freedom from unlawful imprisonment.', 'habeas corpus|imprison|personal liberty|liberty of the person|confinement|detain', 'habeas corpus'],
  ['punishment', 'Punishment, Bail & Fines', 'Cruel punishments, excessive bail, and capital crimes.', 'cruel|punishment|bail|fines?|excessive|capital|death|penalt', 'cruel and unusual|excessive bail|excessive fines'],
  ['criminal-process', 'Criminal Procedure & the Accused', 'Indictment, self-incrimination, double jeopardy, and counsel.', 'indictment|grand jury|accus|witness against himself|confession|jeopardy|twice|counsel|prosecution', 'grand jury|witness against himself|twice put in jeopardy|assistance of counsel'],
  ['due-process', 'Due Process & the Law of the Land', 'Lex terrae and due process of law, from Magna Carta forward.', 'due process|law of the land|lex terrae|per legem terrae|judgment of his peers', 'due process of law|law of the land|lex terrae'],
  ['property', 'Property & Takings', 'Private property, eminent domain, and just compensation.', 'property|just compensation|private property|public use|eminent domain|estates?|lands?', 'private property|just compensation|eminent domain|right of property'],
  ['contracts', 'Contracts, Ex Post Facto & Attainder', 'Obligation of contracts, retroactive laws, and bills of attainder.', 'obligation of contracts?|contracts?|ex post facto|retrospective|retroactive|bills? of attainder|attainder', 'ex post facto|bills? of attainder|obligation of contracts?'],
  ['life-unborn', 'Life, the Unborn & Homicide', 'The right to life, the unborn child, abortion and homicide at common law.', 'womb|quick with child|unborn|abortion|miscarr|ventre|infant|homicide|murder|right to life|life is the immediate gift', 'womb|quick with child|unborn (?:child|infant|children)|abortion|ventre sa mere|life is the immediate gift|killeth it in her womb'],,
  ['marriage-family', 'Marriage, Parents & Family', 'Husband and wife, parent and child, and domestic relations.', 'marri|husband|wife|parents?|child|famil|divorce|guardian', 'husband and wife|parent and child|marriage'],
  ['citizenship', 'Citizenship, Naturalization & Aliens', 'Allegiance, natural-born subjects, naturalization and aliens.', 'citizens?|naturaliz|aliens?|denizen|allegiance|natural[- ]born', 'natural[- ]born|naturaliz|allegiance'],
  ['slavery', 'Slavery', 'Slavery, the slave trade, and fugitive slaves.', 'slave|slavery|servitude|bondage|negro|importation of such persons|three fifths|fugitive', 'slave|slavery'],
  ['elections', 'Elections & Representation', 'Suffrage, representation, apportionment and elections.', 'election|electors?|representat|suffrage|votes?|voting|apportion|census|qualifications', 'right of suffrage|representation|apportion'],
  ['impeachment', 'Impeachment', 'High crimes and misdemeanors and the trial of impeachments.', 'impeach|high crimes|misdemeanou?rs|removal from office', 'impeach'],
  ['amendment', 'Amendment & Constitutional Change', 'Altering the constitution, conventions, and ratification.', 'amendments?|amend|alter or abolish|convention|ratif', 'amendments? to the constitution|alter or abolish|mode of amendment'],
  ['natural-rights', 'Natural Rights & the Social Compact', 'The state of nature, consent of the governed, and inalienable rights.', 'natural rights?|state of nature|social compact|consent of the governed|inalienable|unalienable|law of nature|rights of mankind', 'state of nature|law of nature|unalienable|inalienable|social compact'],
  ['common-law', 'Common Law & Precedent', 'The common law, custom, and the authority of precedent.', 'common law|precedent|customs?|stare decisis|reports|maxim', 'common law|precedents?|stare decisis'],
  ['privileges', 'Privileges & Immunities', 'The privileges and immunities of citizens across the states.', 'privileges and immunities|privileges|immunities', 'privileges and immunities'],
  ['bankruptcy-ip', 'Bankruptcy, Patents & Copyright', 'Bankruptcy laws and securing rights to authors and inventors.', 'bankrupt|patents?|copy-?right|inventors?|authors|useful arts', 'bankrupt|useful arts|exclusive right'],
  ['money', 'Money, Coinage & Banking', 'Coining money, bills of credit, legal tender and a national bank.', 'coin|money|bills of credit|currency|legal tender|bank', 'coin money|bills of credit|legal tender'],
  ['indians', 'Indian Tribes', 'Relations with Indian tribes and nations.', 'indians?|tribes?|savages|natives', 'indian tribes|indians'],
  ['territories', 'Territories & New States', 'Western lands, new states, and governing territory.', 'territor|new states?|western|ordinance', 'new states|territory'],
  ['guarantee', 'Republican Government & Faction', 'Republics, democracy, faction and the guarantee of republican government.', 'republican form|republic|democracy|tyranny|faction|popular government', 'republican form of government|faction'],
);
for (@topics) { $_->[5] = qr/$_->[3]/i; $_->[6] = qr/$_->[4]/i }

# ------------------------------------------------------------------ sources
my @sources;   # {id, name, author, year, desc, url, paras => [{loc, t, url}]}
sub lonang_labels { my $f = shift; my %l; my $h = utf8dec(slurp($f)); while ($h =~ /href="([a-z]{2,5}-[0-9a-z-]*)\/"[^>]*>(.*?)<\/a>/gs) { $l{$1} //= dehtml($2) } \%l }
my %LON = (
  blackstone => ['Blackstone, Commentaries on the Laws of England', 'William Blackstone', '1765–1769', 'The leading treatise on English common law, read by every founding-era lawyer.', 'blackstone-commentaries-law-england'],
  story      => ['Story, Commentaries on the Constitution of the United States', 'Joseph Story', '1833', 'Justice Story\'s comprehensive treatise on the Constitution, section by section.', 'story-commentaries-us-constitution'],
  tucker     => ['Tucker, Blackstone\'s Commentaries with Notes of Reference', 'St. George Tucker', '1803', 'The first major American commentary, annotating Blackstone for the new republic; includes "View of the Constitution."', 'tucker-blackstone-notes-reference'],
  kent       => ['Kent, Commentaries on American Law', 'James Kent', '1826–1830', 'Chancellor Kent\'s treatise on American law and the constitutional jurisprudence of the United States.', 'kent-commentaries-american-law'],
  vattel     => ['Vattel, The Law of Nations', 'Emer de Vattel', '1758', 'The law-of-nations treatise most cited by the founders on sovereignty, war and treaties.', 'vattel-law-of-nations'],
  locke      => ['Locke, Two Treatises of Government', 'John Locke', '1689', 'The social-compact theory behind the Declaration of Independence.', 'locke-two-treatises-government'],
);
for my $id (qw(blackstone story tucker kent vattel locke)) {
  my $dir = "$R/$id"; next unless -d $dir;
  my ($name, $author, $year, $desc, $slug) = @{ $LON{$id} };
  my $labels = lonang_labels("$dir/index.html");
  my @paras;
  for my $f (sort glob "$dir/*.html") {
    my ($ch) = $f =~ m{/([a-z]{2,5}-[0-9a-z-]+)\.html$} or next;
    my $h = slurp($f);
    my ($title) = utf8dec($h) =~ /<title>(.*?)<\/title>/s; $title = dehtml($title // ''); $title =~ s/\s*-\s*LONANG Institute\s*$//;
    my $label = $labels->{$ch} // $title;
    my $book = '';
    if ($id =~ /blackstone|tucker/ && $ch =~ /-(\d)(\d\d)$/ && $1 > 0) { $book = "Bk. $1, " }
    if ($id eq 'story' && $ch =~ /-(\d)\d\d$/ && $1 > 0) { $book = "Bk. $1, " }
    my $url = "https://lonang.com/library/reference/$slug/$ch/";
    for my $p (paras_from_html($h)) {
      my $loc = "$book$label";
      if ($id eq 'story' && $p =~ /^\x{a7}\s*(\d+)\./) { $loc = "\x{a7} $1 ($label)" }
      push @paras, { loc => $loc, t => $p, url => $url };
    }
  }
  push @sources, { id => $id, name => $name, author => $author, year => $year, desc => $desc, url => "https://lonang.com/library/reference/$slug/", paras => \@paras };
  printf "%-10s %5d paragraphs\n", $id, scalar @paras;
}

# Federalist (Gutenberg #1404)
my @federalist;
{
  my $txt = utf8dec(slurp("$R/federalist/pg1404.txt"));
  $txt =~ s/\r//g;
  $txt =~ s/\*\*\* END OF (THE|THIS) PROJECT GUTENBERG.*//s;
  my @parts = split /\n(?=FEDERALIST No\. \d+\n)/, $txt;
  my %seen;
  for my $part (@parts) {
    my ($n) = $part =~ /^FEDERALIST No\. (\d+)\n/ or next;
    next if $seen{$n}++;
    my @blocks = grep { /\S/ } split /\n\s*\n/, $part;
    shift @blocks;   # "FEDERALIST No. N"
    my $title = shift(@blocks) // ''; $title =~ s/\s+/ /g;
    my ($author) = grep { /^\s*(HAMILTON|MADISON|JAY|HAMILTON OR MADISON|HAMILTON AND MADISON)\s*$/ } @blocks[0 .. 3];
    $author = $author ? ucfirst(lc($author =~ s/^\s+|\s+$//gr)) : '';
    $author =~ s/ (or|and) (\w)/" $1 " . uc $2/e;
    my @ps = map { my $s = $_; $s =~ s/\s+/ /g; $s =~ s/^\s+|\s+$//g; $s } @blocks;
    @ps = grep { length > 40 && !/^(From the |For the Independent Journal|From McLEAN|To the People of the State of New York|HAMILTON|MADISON|JAY|PUBLIUS\.?$)/ } @ps;
    push @federalist, { n => $n + 0, title => $title, author => $author, paras => \@ps };
  }
  @federalist = sort { $a->{n} <=> $b->{n} } @federalist;
  push @sources, { id => 'federalist', name => 'The Federalist', author => 'Hamilton, Madison & Jay', year => '1787–1788', desc => 'The 85 essays urging New York to ratify the Constitution.', url => 'https://www.gutenberg.org/ebooks/1404',
    paras => [ map { my $f = $_; map { { loc => "No. $f->{n}" . ($f->{author} ? " ($f->{author})" : ''), t => $_, fed => $f->{n} } } @{ $f->{paras} } } @federalist ] };
  printf "%-10s %5d papers\n", 'federalist', scalar @federalist;
}

# Madison's Notes (Avalon)
{
  my @paras;
  my %mo = (1 => 'January', 5 => 'May', 6 => 'June', 7 => 'July', 8 => 'August', 9 => 'September');
  for my $f (sort { (-M $a) <=> (-M $b) } glob "$R/madison/debates_*.asp") {
    my $h = slurp($f);
    my ($title) = $h =~ /<title>(.*?)<\/title>/s; $title = dehtml($title // ''); $title =~ s/^Avalon Project - Madison Debates - //;
    my ($file) = $f =~ m{/(debates_\w+\.asp)$};
    push @paras, map { { loc => $title, t => $_, url => "https://avalon.law.yale.edu/18th_century/$file", d => $title } } paras_from_html($h);
  }
  my %order; my $i = 0;
  my @months = qw(May June July August September);
  push @sources, { id => 'madison', name => "Madison's Notes of Debates in the Federal Convention", author => 'James Madison', year => '1787', desc => 'The fullest record of the secret debates at the Philadelphia Convention.', url => 'https://avalon.law.yale.edu/subject_menus/debcont.asp', paras => \@paras };
  printf "%-10s %5d paragraphs\n", 'madison', scalar @paras;
}

# Founding documents (Avalon) and other Wikisource texts
my %DOCS = (
  declaration => ['Declaration of Independence', 1776], articles => ['Articles of Confederation', 1781], northwest => ['Northwest Ordinance', 1787],
  vadeclaration => ['Virginia Declaration of Rights', 1776], ma1780 => ['Massachusetts Constitution', 1780], pa1776 => ['Pennsylvania Constitution', 1776],
  va1776 => ['Virginia Constitution', 1776], ny1777 => ['New York Constitution', 1777], nc1776 => ['North Carolina Constitution', 1776], md1776 => ['Maryland Constitution', 1776],
  magna => ['Magna Carta', 1215], engbill => ['English Bill of Rights', 1689], virres => ['Virginia Resolutions', 1798], kenres => ['Kentucky Resolutions', 1798], farewell => ["Washington's Farewell Address", 1796],
  vsrf => ['Virginia Statute for Religious Freedom', 1786], remonstrance => ['Madison, Memorial and Remonstrance Against Religious Assessments', 1785], danbury => ['Jefferson, Letter to the Danbury Baptists', 1802],
);
my @docs;
for my $id (sort keys %DOCS) {
  my ($title, $year) = @{ $DOCS{$id} };
  my @ps;
  if (-s "$R/docs/$id.html") { @ps = paras_from_html(slurp("$R/docs/$id.html")) }
  elsif (-s "$R/wikisource/$id.json") { my $d = eval { decode_json(slurp("$R/wikisource/$id.json")) } or next; @ps = paras_from_html($d->{parse}{text} // '') }
  next unless @ps >= 1;
  push @docs, { id => $id, title => $title, year => $year, paras => \@ps };
}
@docs = sort { $a->{year} <=> $b->{year} } @docs;
push @sources, { id => 'documents', name => 'Founding Documents & State Constitutions', author => 'Various', year => '1215–1802', desc => 'Magna Carta, the English Bill of Rights, the Declaration, the Articles, early state constitutions and declarations of rights, and more.', url => '',
  paras => [ map { my $d = $_; map { { loc => "$d->{title} ($d->{year})", t => $_, doc => $d->{id} } } @{ $d->{paras} } } @docs ] };
printf "%-10s %5d documents\n", 'documents', scalar @docs;

# Statutes at Large, vol. 1 (Wikisource)
# Only the transcluded statute text is kept: Wikisource's page header (navigation, "sister projects" links and editors'
# notes, which can quote an encyclopedia), the printed margin notes and page numbers are dropped.
sub drop_tag {
  my ($h, $tag, $cls) = @_;
  while ($h =~ /<$tag\b[^>]*class="[^"]*\b(?:$cls)\b[^"]*"[^>]*>/gi) {
    my $start = $-[0]; my $pos = $+[0]; my $depth = 1;
    while ($depth && $h =~ /<(\/?)$tag\b[^>]*>/gi) { $depth += $1 ? -1 : 1; $pos = $+[0] }
    substr($h, $start, $pos - $start) = '';
    pos($h) = $start;
  }
  $h
}
my @statutes;
for my $f (glob "$R/statutes/*.json") {
  next if $f =~ /allpages\.json$/;
  my $d = eval { decode_json(slurp($f)) } or next;
  my $html = $d->{parse}{text} // next;
  my ($cong, $sess, $chap) = $f =~ /(\d+)\w\w_Congress_(\d+)\w\w_Session_(Chapter_\d+|Resolution\w*)/ or next;
  $html = utf8dec($html);
  $html = substr($html, $-[0]) if $html =~ /<div[^>]*class="[^"]*prp-pages-output/;
  $html = drop_tag($html, 'div', 'ws-noexport|wst-header|ws-header');
  my ($margin) = $html =~ /class="wst-sidenote-inner"[^>]*>(.*?)<\/span><\/span>/is;   # the printed margin summary
  $margin = dehtml($margin) if defined $margin;
  $html = drop_tag($html, 'span', 'wst-sidenote|pagenum|ws-pagenum');
  my $plain = dehtml($html);
  my @ps = paras_from_html($html);
  @ps = grep { !/^(Statute |STATUTE )/ } @ps;
  # a short resolution can be a single block with no paragraph tags
  if (!@ps) { (my $t = $plain) =~ s/\s*\bLayout \d+\s*$//; $t =~ s/^[\x{200B}\s]+//; @ps = ($t) if length($t) >= 60 }
  my ($title) = $html =~ /class="us-stat-chap-title"[^>]*>.*?<i>(.*?)<\/i>/is;
  $title = dehtml($title) if $title;
  undef $title if $title && $title !~ /^An Act/;
  ($title) = $plain =~ /(An Act[^.]{10,300}?\.)/ unless $title;
  $title = $margin if !$title && $margin && length($margin) > 15;
  unless ($title) {
    # a resolution without a printed summary: its own words, after the enacting formula
    (my $t = $ps[0] // '') =~ s/^[\x{2160}-\x{217F}IVXL\d.\s]*Resolved,?\s+(?:by the Senate and House of Representatives of the United States of America,?\s+in Congress assembled,?\s*)?(?:two.thirds of both Houses (?:concurring|deeming it necessary),?\s*)?(?:That,?\s+)?//i;
    $t = ucfirst $t;
    $t = (substr($t, 0, 150) =~ s/\s+\S*$//r) . '…' if length($t) > 150;
    $title = $t if length($t) > 15;
  }
  next unless $title && @ps;
  my ($date) = $plain =~ /((?:Approved|Passed|Became a law)[^.,]{0,10},? (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2},? 17\d\d)/;
  ($date) = $plain =~ /((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2},? 17\d\d)/ unless $date;
  my ($year) = ($date // '') =~ /(17\d\d)/;
  $chap =~ s/_/ /g;
  # a resolution with a name rather than a number ("Resolution regarding John White") is titled by its name
  $title = $chap if $chap =~ /^Resolution \D/;
  push @statutes, { id => "c$cong-s$sess-" . lc($chap =~ s/ /-/gr), title => $title, cong => $cong + 0, sess => $sess + 0, chap => $chap, date => $date, year => $year, paras => \@ps,
    url => "https://en.wikisource.org/wiki/United_States_Statutes_at_Large/Volume_1/" . ($f =~ m{/([^/]+)\.json$} ? $1 : '') };
}
# in each session: the numbered chapters, then the numbered resolutions, then the named (private) resolutions
my $kind = sub { $_[0]{chap} =~ /^Chapter/ ? 0 : $_[0]{chap} =~ /^Resolution \d/ ? 1 : 2 };
@statutes = sort { $a->{cong} <=> $b->{cong} || $a->{sess} <=> $b->{sess} || $kind->($a) <=> $kind->($b) || (($a->{chap} =~ /(\d+)/)[0] // 0) <=> (($b->{chap} =~ /(\d+)/)[0] // 0) || $a->{chap} cmp $b->{chap} } @statutes;
for (@statutes) { $_->{url} =~ s/(Volume_1\/)(\d+\w\w_Congress)_(\d+\w\w_Session)_(.+)$/$1$2\/$3\/$4/ }
push @sources, { id => 'statutes', name => 'Acts of the First Congresses (Statutes at Large, vol. 1)', author => 'U.S. Congress', year => '1789–1799', desc => 'Every act and resolution of the first five Congresses, from the Judiciary Act to the Alien and Sedition Acts.', url => 'https://en.wikisource.org/wiki/United_States_Statutes_at_Large/Volume_1',
  paras => [ map { my $s = $_; map { { loc => "$s->{cong}th Cong., $s->{chap}: " . substr($s->{title}, 0, 140), t => $_, st => $s->{id} } } @{ $s->{paras} } } @statutes ] };
for (@{ $sources[-1]{paras} }) { $_->{loc} =~ s/^1th/1st/; $_->{loc} =~ s/^2th/2nd/; $_->{loc} =~ s/^3th/3rd/ }
printf "%-10s %5d acts\n", 'statutes', scalar @statutes;

# ------------------------------------------------------------------ more commentaries (constitution.org transcriptions of public-domain texts)
# William Rawle, A View of the Constitution of the United States (2d ed. 1829)
{
  my @paras;
  for my $f (sort glob "$R/rawle/rawle_*.htm") {
    my $h = utf8dec(slurp($f));
    my ($title) = $h =~ /<title>[^<]*?(Chapter [^<]+|Introduction[^<]*)<\/title>/i;
    next unless $title;
    $title =~ s/\s+/ /g;
    my ($n) = $f =~ /rawle_(\d+)/;
    push @paras, map { { loc => $title, t => $_, url => "https://constitution.org/2-Authors/wr/rawle_$n.htm" } } paras_from_html($h);
  }
  push @sources, { id => 'rawle', name => 'Rawle, A View of the Constitution of the United States', author => 'William Rawle', year => '1825; 2d ed. 1829',
    desc => 'An early systematic commentary by a Philadelphia lawyer who knew many of the framers; often cited on the original understanding.', url => 'https://constitution.org/2-Authors/wr/rawle-00.htm', paras => \@paras };
  printf "%-10s %5d paragraphs\n", 'rawle', scalar @paras;
}
# Thomas M. Cooley, The General Principles of Constitutional Law in the United States (3d ed. 1898)
{
  my $h = utf8dec(slurp("$R/cooley/pcl.htm"));
  my (@paras, $chap);
  while ($h =~ /<p\b[^>]*>(.*?)<\/p>|<h\d[^>]*>(.*?)<\/h\d>/gis) {
    my $t = dehtml($1 // $2);
    if (defined $2 || $t =~ /^CHAPTER [IVXL]+\.?\s/) { $chap = $t if $t =~ /CHAPTER|SECTION/i; next }
    next if length($t) < 60 || $t =~ /\.{6,}/;
    push @paras, { loc => ($chap // 'General Principles'), t => $t, url => 'https://constitution.org/1-Constitution/cmt/tmc/pcl.htm' };
  }
  push @sources, { id => 'cooley', name => 'Cooley, The General Principles of Constitutional Law', author => 'Thomas M. Cooley', year => '1880; 3d ed. 1898',
    desc => "The leading late-nineteenth-century treatise by the Michigan chief justice, author of Constitutional Limitations.", url => 'https://constitution.org/1-Constitution/cmt/tmc/pcl.htm', paras => \@paras };
  printf "%-10s %5d paragraphs\n", 'cooley', scalar @paras;
}
# The Anti-Federalists: Brutus, the Federal Farmer, Centinel, Cato
{
  my %SERIES = (brutus => 'Brutus', fedfar => 'Federal Farmer', centin => 'Centinel', cato_ => 'Cato');
  my @paras;
  for my $s (qw(brutus fedfar centin cato_)) {
    for my $f (sort glob "$R/antifederalist/$s\[0-9][0-9]*.htm") {
      my ($n) = $f =~ /(\d+)\.htm$/;
      next if $n == 0;
      (my $base = $f) =~ s{.*/}{};
      push @paras, map { { loc => "$SERIES{$s} No. " . ($n + 0), t => $_, url => "https://constitution.org/1-Constitution/afp/$base" } } paras_from_html(slurp($f));
    }
  }
  push @sources, { id => 'antifederalist', name => 'The Anti-Federalists: Brutus, the Federal Farmer, Centinel and Cato', author => 'Various (pseudonymous)', year => '1787–1788',
    desc => 'The leading essays against ratification, which pressed the case for a bill of rights and limited federal power.', url => 'https://constitution.org/afp.htm', paras => \@paras };
  printf "%-10s %5d paragraphs\n", 'antifed', scalar @paras;
}

# ------------------------------------------------------------------ passage selection
# Score each paragraph per topic: strong-phrase hits count triple; require >= 3 points (or a strong phrase).
my (%passages, %index, %srcRank, $pid);
my %PER = (statutes => 10, documents => 10);
for my $src (@sources) {
  my $paras = $src->{paras};
  for my $t (@topics) {
    my ($tid, $rx, $strong) = ($t->[0], $t->[5], $t->[6]);
    my (@scored, $anyStrong);
    for my $i (0 .. $#$paras) {
      my $p = $paras->[$i]{t};
      next if length($p) < 80;
      next if (() = $p =~ /(?:^|\s)\d{1,3}\.\s+(?:\d|[A-Z][a-z]*\.)/g) >= 3;   # footnote and citation lists
      (my $q = $p) =~ s/sergeant[- ]at[- ]arms|coat of arms|arms of the (?:sea|united states)|womb of (?:time|futurity|events|the future)//gi;
      my @hits = map { lc } ($q =~ /$rx/g);
      next unless @hits;
      my %distinct = map { $_ => 1 } @hits;
      my $st = () = $q =~ /$strong/g;
      # without a defining phrase, require several distinct topic terms
      next unless $st || (@hits >= 5 && keys(%distinct) >= 3);
      $anyStrong ||= $st;
      my $score = @hits + 4 * $st + keys(%distinct);
      $score = $score / (1 + length($p) / 2500);   # mild preference for focused paragraphs
      push @scored, [$score, $i, $st];
    }
    # when this source has paragraphs using the topic's defining phrases, use only those
    @scored = grep { $_->[2] } @scored if $anyStrong;
    @scored = () if !$anyStrong && $src->{id} eq 'statutes';
    if (!$anyStrong && @scored) { @scored = (sort { $b->[0] <=> $a->[0] } @scored)[0 .. ($#scored < 1 ? $#scored : 1)] }
    my $k = $PER{$src->{id}} // 6;
    my (%usedLoc, @pick);
    for my $s (sort { $b->[0] <=> $a->[0] } @scored) {
      my $p = $paras->[$s->[1]];
      next if $usedLoc{ $p->{st} // $p->{doc} // $p->{fed} // $p->{loc} }++ >= ($src->{id} eq 'statutes' ? 1 : 2);   # spread across works
      push @pick, $s->[1];
      last if @pick >= $k;
    }
    next unless @pick;
    # rank sources within a topic by their best passage (strong matches first)
    my ($best) = sort { $b->[2] <=> $a->[2] || $b->[0] <=> $a->[0] } @scored;
    $srcRank{$tid}{ $src->{id} } = ($best->[2] ? 1000 : 0) + $best->[0];
    for my $i (@pick) {
      my $key = "$src->{id}:$i";
      unless ($passages{$key}) {
        my $p = $paras->[$i];
        my $text = $p->{t};
        $text = substr($text, 0, 2400) =~ s/\s+\S*$//r . " \x{2026}" if length $text > 2400;
        my %o = (s => $src->{id}, loc => $p->{loc}, t => $text);
        $o{u} = $p->{url} if $p->{url};
        $o{fed} = $p->{fed} if $p->{fed};
        $o{doc} = $p->{doc} if $p->{doc};
        $o{st} = $p->{st} if $p->{st};
        $passages{$key} = { id => 'p' . (++$pid), %o };
      }
      push @{ $index{$tid}{ $src->{id} } }, $passages{$key}{id};
    }
  }
}
my %byId = map { $_->{id} => do { my %c = %$_; delete $c{id}; \%c } } values %passages;
printf "passages: %d across %d topics\n", scalar(keys %byId), scalar(keys %index);
my %counts; for my $tid (keys %index) { $counts{$tid} += scalar @{ $index{$tid}{$_} } for keys %{ $index{$tid} } }
write_js('docs/data/corner.js', 'CORNER', {
  topics => [ map { { id => $_->[0], name => $_->[1], desc => $_->[2], n => $counts{ $_->[0] } // 0 } } @topics ],
  sources => [ map { { id => $_->{id}, name => $_->{name}, author => $_->{author}, year => $_->{year}, desc => $_->{desc}, url => $_->{url}, n => scalar @{ $_->{paras} } } } @sources ],
  passages => \%byId, index => \%index,
  order => { map { my $t = $_; ($t => [ sort { $srcRank{$t}{$b} <=> $srcRank{$t}{$a} } keys %{ $srcRank{$t} } ]) } keys %srcRank },
});
write_js('docs/data/library-federalist.js', 'LIB_FEDERALIST', \@federalist);
write_js('docs/data/library-documents.js', 'LIB_DOCUMENTS', \@docs);
write_js('docs/data/library-statutes.js', 'LIB_STATUTES', [ map { my %s = %$_; \%s } @statutes ]);
