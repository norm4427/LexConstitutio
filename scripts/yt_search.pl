#!/usr/bin/perl
# Parses a saved YouTube search-results page and prints one TSV line per video:
# videoId, title, channel, channelId, length, views, published
use strict; use warnings; use JSON::PP;
binmode STDOUT, ':encoding(UTF-8)';
local $/; my $html = <STDIN>;
my ($json) = $html =~ /var ytInitialData = (\{.*?\});<\/script>/s or exit 0;
my $data = eval { JSON::PP->new->utf8(1)->decode($json) } or exit 0;
sub txt { my $o = shift; return '' unless $o; return $o->{simpleText} // join('', map { $_->{text} } @{ $o->{runs} || [] }); }
my @out;
sub walk { my $n = shift;
  if (ref $n eq 'HASH') {
    if (my $v = $n->{videoRenderer}) {
      my $ch = $v->{ownerText}{runs}[0] || {};
      push @out, join("\t", map { my $s = $_ // ''; $s =~ s/[\t\r\n]+/ /g; $s }
        $v->{videoId}, txt($v->{title}), $ch->{text}, $ch->{navigationEndpoint}{browseEndpoint}{browseId},
        txt($v->{lengthText}), txt($v->{viewCountText}), txt($v->{publishedTimeText}));
      return;
    }
    walk($_) for values %$n;
  } elsif (ref $n eq 'ARRAY') { walk($_) for @$n; }
}
walk($data);
print "$_\n" for @out;
