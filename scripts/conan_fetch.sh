#!/usr/bin/env bash
# Downloads the Constitution Annotated (2022 GPO edition, public domain) chapter PDFs from GovInfo into data/raw/conan/.
cd "$(dirname "$0")/.."; mkdir -p data/raw/conan
UA="Mozilla/5.0 ConLawIndex/1.0 (educational project)"
for g in 6 8 9 10 11 13 15 16 18 19 20 22 23 24 25 27 28 29 41; do   # 41: the Twenty-Seventh Amendment
  [ -s data/raw/conan/g$g.pdf ] || curl -s -m 300 -A "$UA" -o data/raw/conan/g$g.pdf "https://www.govinfo.gov/content/pkg/GPO-CONAN-2022/pdf/GPO-CONAN-2022-$g.pdf"; sleep 1
done
echo "downloaded: $(ls data/raw/conan/*.pdf | wc -l) PDFs"
