#!/usr/bin/env bash
# Current Supreme Court docket: Oyez case lists for the current and prior term, the Court's monthly
# argument calendars, and the supremecourt.gov docket page (briefs) for every undecided case.
# Re-run any time to refresh; then run  perl scripts/build_docket.pl
cd "$(dirname "$0")/.."
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
D=data/raw/docket; mkdir -p $D
Y=$(date +%Y); M=$(date +%-m); TERM=$([ "$M" -ge 10 ] && echo $Y || echo $((Y - 1)))
echo "current term: OT$TERM"
for t in $((TERM - 1)) $TERM; do curl -s -m 120 "https://api.oyez.org/cases?filter=term:$t&per_page=1000" -o $D/oyez-$t.json; sleep 1; done
# argument calendars for the term (October..April)
curl -s -m 60 -A "$UA" "https://www.supremecourt.gov/oral_arguments/calendarsandlists.aspx" -o $D/calendars.html
for m in October November December; do echo "$m$TERM"; done > $D/months.txt
for m in January February March April; do echo "$m$((TERM + 1))"; done >> $D/months.txt
while read -r m; do
  grep -q "MonthlyArgumentCal$m.pdf" $D/calendars.html || continue
  curl -s -m 60 -A "$UA" -o $D/cal-$m.pdf "https://www.supremecourt.gov/oral_arguments/argument_calendars/MonthlyArgumentCal$m.pdf"
  pdftotext -layout -enc UTF-8 $D/cal-$m.pdf $D/cal-$m.txt; sleep 1
done < $D/months.txt
# dockets: undecided Oyez cases + every docket number on the calendars
{ perl -MJSON::PP -0777 -ne 'for (@{decode_json($_)}) { my %e = map { ($_->{event} // "") => 1 } grep { $_ } @{$_->{timeline}||[]}; print "$_->{docket_number}\n" unless $e{Decided} }' $D/oyez-$((TERM - 1)).json $D/oyez-$TERM.json
  cat $D/cal-*.txt 2>/dev/null | grep -o '\b[0-9]\{2\}-[0-9A-Z]\{1,5\}\b' ; } | tr -d '\r' | sort -u > $D/dockets.txt
while read -r dk; do
  [ -n "$dk" ] || continue
  curl -s -m 60 -A "$UA" -o "$D/d-$dk.html" "https://www.supremecourt.gov/docket/docketfiles/html/public/$dk.html"; sleep 0.8
done < $D/dockets.txt
echo "dockets: $(wc -l < $D/dockets.txt); calendars: $(ls $D/cal-*.txt 2>/dev/null | wc -l)"
# argument transcripts posted for the current term
curl -s -m 60 -A "$UA" -o $D/transcripts.html "https://www.supremecourt.gov/oral_arguments/argument_transcript/$TERM"
