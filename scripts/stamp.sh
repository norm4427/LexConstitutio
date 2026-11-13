#!/bin/sh
# Stamps a fresh version on every stylesheet/script URL in docs/index.html (and on data files loaded by app.js),
# so browsers fetch the new files right after a deploy instead of using GitHub Pages' 10-minute cache.
# Run from the repo root before committing:  sh scripts/stamp.sh
V=$(date +%Y%m%d%H%M)
sed -i -E "s#(href|src)=\"([^\"?]+\.(css|js))(\?v=[0-9a-z]+)?\"#\1=\"\2?v=$V\"#g; s#window\.LC_VER='[^']*'#window.LC_VER='$V'#" docs/index.html
grep -q "window.LC_VER" docs/index.html || sed -i "s#<script src=\"data/articles.js#<script>window.LC_VER='$V'</script>\n  &#" docs/index.html
echo "stamped v=$V"
