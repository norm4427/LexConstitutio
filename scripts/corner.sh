#!/usr/bin/env bash
# Downloads the historical sources for the Originalist's Corner into data/raw/corner/.
#  - Lonang Institute: Blackstone, Story, St. George Tucker, Kent, Vattel, Locke (chapter pages)
#  - Project Gutenberg: The Federalist (#1404)
#  - Avalon Project (Yale): Madison's Notes of Debates in the Federal Convention; founding documents
#  - Wikisource: every chapter of U.S. Statutes at Large, Volume 1 (1789-1799); other founding-era texts
# Pages are cached: delete a file to re-fetch it.
cd "$(dirname "$0")/.."
UA="Mozilla/5.0 ConLawIndex/1.0 (educational project)"
R=data/raw/corner; mkdir -p $R
get(){ [ -s "$2" ] && return 0; curl -s -m 120 -A "$UA" -L "$1" -o "$2"; sleep "${3:-0.6}"; }

# --- Lonang reference works
for w in story-commentaries-us-constitution:story blackstone-commentaries-law-england:blackstone tucker-blackstone-notes-reference:tucker kent-commentaries-american-law:kent vattel-law-of-nations:vattel locke-two-treatises-government:locke; do
  slug=${w%%:*}; id=${w##*:}; mkdir -p $R/$id
  get "https://lonang.com/library/reference/$slug/" $R/$id/index.html
  grep -o 'href="[a-z]\{2,5\}-[0-9a-z-]*/"' $R/$id/index.html | sed 's/href="//; s/\/"//' | awk '!s[$0]++' > $R/$id/chapters.txt
  while read -r ch; do get "https://lonang.com/library/reference/$slug/$ch/" $R/$id/$ch.html; done < $R/$id/chapters.txt
  echo "$id: $(ls $R/$id | wc -l) files"
done &

# --- The Federalist (Gutenberg)
mkdir -p $R/federalist; get https://www.gutenberg.org/cache/epub/1404/pg1404.txt $R/federalist/pg1404.txt

# --- Madison's Notes (Avalon)
mkdir -p $R/madison
get https://avalon.law.yale.edu/subject_menus/debcont.asp $R/madison/index.html
grep -o 'href="[^"]*debates_[0-9]*\.asp"' $R/madison/index.html | sed 's/href="//; s/"$//; s#^\.\./##' | awk '!s[$0]++' | while read -r p; do
  f=$(basename "$p"); get "https://avalon.law.yale.edu/$p" $R/madison/$f 0.4; done
echo "madison: $(ls $R/madison | wc -l) files"

# --- Founding documents (Avalon)
mkdir -p $R/docs
while IFS='|' read -r id url; do get "$url" "$R/docs/$id.html" 0.4; done <<'EOF'
declaration|https://avalon.law.yale.edu/18th_century/declare.asp
articles|https://avalon.law.yale.edu/18th_century/artconf.asp
northwest|https://avalon.law.yale.edu/18th_century/nworder.asp
vadeclaration|https://avalon.law.yale.edu/18th_century/virginia.asp
ma1780|https://avalon.law.yale.edu/18th_century/mass03.asp
pa1776|https://avalon.law.yale.edu/18th_century/pa08.asp
va1776|https://avalon.law.yale.edu/18th_century/va05.asp
ny1777|https://avalon.law.yale.edu/18th_century/ny01.asp
nc1776|https://avalon.law.yale.edu/18th_century/nc07.asp
md1776|https://avalon.law.yale.edu/17th_century/ma02.asp
magna|https://avalon.law.yale.edu/medieval/magframe.asp
engbill|https://avalon.law.yale.edu/17th_century/england.asp
virres|https://avalon.law.yale.edu/18th_century/virres.asp
kenres|https://avalon.law.yale.edu/18th_century/kenres.asp
farewell|https://avalon.law.yale.edu/18th_century/washing.asp
EOF
echo "docs: $(ls $R/docs | wc -l) files"

# --- Wikisource: Statutes at Large vol. 1 and other founding-era texts
mkdir -p $R/statutes $R/wikisource
API="https://en.wikisource.org/w/api.php"
get "$API?action=query&list=allpages&apprefix=United%20States%20Statutes%20at%20Large/Volume%201/&apnamespace=0&aplimit=500&format=json" $R/statutes/allpages.json
perl -MJSON::PP -0777 -ne 'print "$_->{title}\n" for @{decode_json($_)->{query}{allpages}}' $R/statutes/allpages.json | grep -E "/Chapter [0-9]+$|/Resolution" > $R/statutes/titles.txt
while read -r t; do
  f=$(echo "$t" | sed 's#.*Volume 1/##; s#[ /]#_#g'); enc=$(perl -MURI::Escape -e 'print uri_escape($ARGV[0])' "$t")
  get "$API?action=parse&page=$enc&prop=text|displaytitle&format=json&formatversion=2" "$R/statutes/$f.json" 0.8
done < $R/statutes/titles.txt
echo "statutes: $(ls $R/statutes | wc -l) files"
while IFS='|' read -r id title; do
  enc=$(perl -MURI::Escape -e 'print uri_escape($ARGV[0])' "$title")
  get "$API?action=parse&page=$enc&prop=text|displaytitle&format=json&formatversion=2&redirects=1" "$R/wikisource/$id.json" 0.8
done <<'EOF'
vsrf|Virginia Statute for Religious Freedom
remonstrance|Memorial and Remonstrance Against Religious Assessments
danbury|Letter to the Danbury Baptists
EOF
wait
echo DONE
