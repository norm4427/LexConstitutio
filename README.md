# Lex Constitutio

A PhilPapers-style hub for constitutional law. It is a static site (`docs/`) built from openly published metadata.

## Sections
- **Articles:** about 22,600 constitutional law articles from 27 law reviews. Includes full-text search, a topic taxonomy (5 areas, 29 subtopics), filters, author pages, and Bluebook and BibTeX citations.
- **Most influential (in Articles):** OpenAlex citation counts with a percentile within each decade, a "Most cited" sort, and rankings by topic, decade and journal.
- **Supreme Court:** about 29,100 cases: about 8,500 from Oyez, plus every other Supreme Court Database case (1791–2025) with a name, citation, date and recorded vote (about 20,600, mostly before 1955; `add_scdb_cases.py`). Those show the citation, date, each justice's vote, and links to the opinion in the *United States Reports* (Library of Congress) and on Justia. The Oyez cases have a summary, the official one-line holding (recent terms), and an opinion PDF (supremecourt.gov or Library of Congress). Argument and opinion-announcement audio plays on the page with a synced, click-to-seek transcript.
- **Justice ratings (Justices):** each justice's page shows a liberal–conservative score (share of liberal votes as coded by the Supreme Court Database, the same measured against the colleagues in the same cases, and Martin–Quinn scores through the 2021 Term) and an institutionalism score (voting with the majority, not writing separately, not concurring only in the judgment, not joining overrulings of precedent or decisions striking down laws, each measured against colleagues). The method is described on the page (`build_ratings.py`).
- **Vote prediction (Justices):** for each sitting justice, a model of their vote (for the petitioner or the respondent) trained on SCDB variables known before the decision, tested on the most recent 20% of their votes against constant-guess baselines, with the main predictors and predicted votes in pending cases (`build_models.py`).
- **Statistics (in Supreme Court):** term-by-term tables after the *Harvard Law Review*'s annual "The Statistics" for every Term 1791–2025: opinions written, dissenting votes, agreement matrices, unanimity, vote splits, 5–4 coalitions, dispositions by lower court, subject matter, and every case classed by direction and by an institutionalism index (`build_stats.py`).
- **Current docket:** undecided cases for the current Term with the Court's argument calendar, status, questions presented, merits and amicus briefs, transcript PDFs, and argument audio (Oyez, or the Court's own MP3 until Oyez posts it). Every case page has a Precedents panel listing cases named in the Oyez summary and the most closely related decisions.
- **Lectures:** about 230 lectures and debates from law schools, universities and constitutional institutions, embedded from YouTube. There is no Lectures tab; the Beginner's Guide shows the ones that fit each topic under "Lectures and debates" (`scripts/guide_lectures.py`). The old `#/lectures` page still works for existing links.
- **Beginner's Guide:** 20 beginner topics (overview, Wex link, explainer videos, landmark cases, starter books and articles), followed by an advanced doctrine section in 14 parts and 52 sections. The advanced section has original doctrinal summaries, black-letter tests, 179 linked cases, and excerpts from the opinions (`scripts/advanced/*.md`).
- **Originalist's Corner:** 37 topics with passages from Blackstone, Tucker, Story, Kent, Vattel, Locke, The Federalist, Madison's Notes, founding documents and the acts of the first five Congresses, plus an on-site library of full texts.
- **Quizzes:** 5 multiple-choice questions at the end of each beginner topic, and 4–8 Socratic-style case questions at the end of each advanced part (`scripts/quizzes/*.txt` → `build_quizzes.pl`). Answers show explanations, and the best score is kept in the browser.
- **Statutes (in Supreme Court):** 137 federal statutes the Court has interpreted, each with a multi-paragraph summary (Wikipedia, CC BY-SA), its Congress, public law and Statutes at Large citation, a link to its text (uscode.house.gov, GovInfo or Wikisource), area tags, and the cases that turned on it (Supreme Court Database statute codes) or name it (case summaries and Oyez facts). Statute names in case summaries show a two-sentence description on hover and link to the statute page (`build_statutes.py`).
- **Learning Center:** flashcards and games.
  - *Flashcards:* "The Basics" (the 100 most important cases), the topic decks, and "Every case, term by term": a deck for each Term with every other decided case that has an Oyez summary, grouped by Chief Justice (`build_flashcards_terms.py`; loaded only when a Term deck is opened).
  - *Games* (essential cases only): Match-up, Choose the Ruling (decoys are the ruling reversed plus other cases' rulings on the same subject, at least as long as the real answer), Overruled, Current Events (cases on the current docket), Who Wrote It?, and Timeline (`build_games.py`). Best scores are kept in the browser.
- **Narration:** a Listen button on each guide topic and advanced section plays a Kokoro (open-weight) narration and highlights each paragraph as it is read; click a paragraph to jump to it. Names and terms are checked against Wikipedia, Wiktionary and the CMU dictionary first (`pron_scan.py`, `narrate_all.py`). Constitution Annotated narration is written to `../audio-r2/` and plays once a public bucket URL is set in `LC_AUDIO_BASE`.
- **Annotated Constitution (Originalist's Corner):** every clause opens a panel with an overview, the Constitution Annotated commentary, leading cases by impact, scholarship, founding-era commentary and early statutes (`build_constitution.py`), and a word inspector with Johnson (1755), Webster (1828) and Bouvier (1856) definitions (`build_dictionaries.py`).
- **Article pages:** a side pane lists the Supreme Court cases and indexed articles named in the article's title and abstract. The repositories serve full-text PDFs behind bot protection, so full text is not scanned.
- **Topic flashcards (Learning Center):** 1,794 spaced-repetition flashcards for 560 essential Supreme Court cases in 20 topic decks. Cards are graded Again / Hard / Good / Easy (Anki-style SM-2 scheduling), with daily limits, sibling burying and per-profile progress in localStorage (export/import to move devices), plus a stats view. "What did the Court decide?" answers have three parts: Background (Oyez facts of the case, including what the law at issue says), Ruling (Oyez description and conclusion, plus the vote) and Importance (the advanced-section notes, the Constitution Annotated, and Congressional Research Service Legal Sidebars published after the decision; both public domain). Oyez text is CC BY-NC 4.0, so it is credited and linked on every card and the site must stay non-commercial.
- **Books:** 76 curated major works (`scripts/books.json`) with covers, Goodreads ratings, matched law review book reviews, and Amazon, publisher, Goodreads and Open Library links. Guide topics link 1–2 introductory books each.
- **My list:** a saved bibliography with Bluebook and BibTeX export.

## Data sources
| Source | Used for | Script |
|---|---|---|
| Digital Commons OAI-PMH | 16 law reviews (Michigan, Chicago, Duke, Cornell, Constitutional Commentary, …) | `harvest.sh` |
| WordPress REST API and article pages | NYU, Texas, UCLA (and their bylines) | `harvest.sh`, `enrich.sh` |
| OpenAlex API | Harvard, Yale, Columbia, Virginia, California, Penn, Stanford, Georgetown, plus citation counts | `openalex.sh`, `openalex_flatten.pl` |
| Oyez API | Case lists (build time); facts, audio, transcripts (fetched live in the browser) | `scotus.sh` |
| supremecourt.gov | Slip-opinion PDFs and holdings (OT2017–), argument transcript PDFs | `scotus.sh` |
| Library of Congress | *U.S. Reports* PDFs (through vol. 576) | constructed in `build_extras.pl` |
| YouTube | Lecture and explainer search, embeddability check via oEmbed | `youtube.sh`, `yt_search.pl` |
| Wikipedia REST API | Guide overviews (CC BY-SA) | `wiki.sh` |
| Lonang Institute, Gutenberg, Avalon Project, Wikisource | Originalist's Corner texts and early statutes | `corner.sh`, `wikisource_retry.sh` |
| U.S. Reports PDFs (LOC), slip opinions, Wikisource | Opinion excerpts in the advanced section | `build_advanced.pl` (needs `pdftotext`) |
| Constitution Annotated (CRS / Library of Congress, GovInfo PDFs, public domain) | In-depth commentary in the advanced section | `conan_extract.py` (needs `pip install pymupdf`), `build_conan.pl`, `conan_map.tsv` |
| Open Library API | Book covers, ISBNs, page counts | `books.sh` |
| Goodreads search suggestions (unofficial; Goodreads has no public API) | Book ratings, descriptions | `books.sh` |
| Open Library, Goodreads, Google Books, Amazon catalog images | The sharpest available cover for each book | `book_covers.py` |
| Wikipedia (CC BY-SA), uscode.house.gov, GovInfo, Wikisource | Statute summaries and text links | `build_statutes.py` |
| Wex (Cornell LII, CC BY-NC-SA) and the U.S. Courts glossary | Hover definitions in the Beginner's Guide | `build_glossary.py` |
| OpenStax *American Government 3e* (CC BY 4.0) | The basics in each guide topic | `build_foundations.py` |
| LEME (Johnson 1755, CC BY 4.0), Webster 1828 and Bouvier 1856 (public domain) | Founding-era word inspector | `build_dictionaries.py` |
| National Archives transcription, Constitution Annotated | Annotated Constitution | `build_constitution.py`, `clauses.py` |
| Supreme Court Database (Spaeth et al.), 2026 Release 01 and Legacy Release 07; its online codebook | Older cases, justice ratings, the Statistics tab, vote models | `scdb_codebook.py`, `add_scdb_cases.py`, `build_ratings.py`, `build_stats.py`, `build_models.py` |
| Martin–Quinn scores (Martin & Quinn, 2021 release, mqscores.quantitative.emory.edu) | Ideal-point scores by term, 1937–2021 | `build_ratings.py` (CSV in `data/raw/mq/justices.csv`) |
| supremecourt.gov docket pages | Lower court and counsel for pending cases (vote models) | `docket.sh` (cache), `build_models.py` |

`scripts/sources.tsv` lists the journals. `scripts/guide.json` defines the guide topics and their landmark cases. `scripts/yt_queries.tsv` defines the lecture searches.

## Rebuilding
Run these from the project root. The shell and Perl steps need Git Bash, and `build.ps1` needs Windows PowerShell.

```bash
bash scripts/harvest.sh                 # repository and WordPress journals (about 15 min)
bash scripts/openalex.sh                # OpenAlex journals and citation counts (about 250 requests)
perl scripts/openalex_flatten.pl
bash scripts/scotus.sh                  # Oyez lists and supremecourt.gov listings
bash scripts/youtube.sh                 # lecture and guide video searches
bash scripts/wiki.sh                    # guide overviews
bash scripts/books.sh                   # book metadata and ratings (cached; delete data/raw/books/<id>.* to refresh)
powershell -ExecutionPolicy Bypass -File scripts/build.ps1     # writes docs/data/articles.js
bash scripts/enrich.sh                  # bylines for new WordPress articles, then re-run build.ps1
perl scripts/build_extras.pl            # writes scotus.js, lectures.js, guide.js, books.js
python scripts/guide_lectures.py           # adds a "Lectures and debates" shelf to each guide topic (after build_extras.pl)
bash scripts/corner.sh && bash scripts/wikisource_retry.sh   # founding-era sources (Wikisource rate-limits; the retry script backs off)
perl scripts/build_corner.pl           # writes corner.js and library-*.js
perl scripts/build_advanced.pl         # writes advanced.js from scripts/advanced/*.md
bash scripts/conan_fetch.sh && python scripts/conan_extract.py && perl scripts/build_conan.pl   # Constitution Annotated commentary (PDFs in data/raw/conan from GovInfo)
perl scripts/build_quizzes.pl          # writes quizzes.js from scripts/quizzes/*.txt
python scripts/build_votes.py          # writes votes.js: each justice's vote (SCDB 2026_01 + Legacy 07 CSVs in data/raw/scdb/csv/, then opinion PDFs, then Oyez)
python scripts/build_justices.py       # writes justices.js: all justices with portraits (Wikimedia Commons) and Wikipedia bios; run build_votes.py again after
python scripts/cap_fetch.py            # caches Caselaw Access Project citation data for Supreme Court cases (data/raw/cap/)
python scripts/build_case_impact.py    # writes case_impact.js: later Supreme Court citations + citation PageRank per case
python scripts/crs_fetch.py           # caches CRS Legal Sidebars (public domain) from EveryCRSReport in data/raw/crs/
python scripts/flashcards_fetch.py     # caches Oyez case details (facts, conclusion, vote) in data/raw/oyez/cases/
perl scripts/build_flashcards.pl       # writes flashcards.js (run after build_extras.pl and build_advanced.pl)
perl scripts/flag_reviews.pl           # confirms book reviews via Open Library so they leave the article rankings
bash scripts/books_impact.sh && perl scripts/books_impact_merge.pl   # citation counts for books (Books tab only)
bash scripts/docket.sh && perl scripts/build_docket.pl   # current docket, calendar, briefs (re-run weekly during the Term)
python scripts/fix_citations.py         # real citations for "584 U.S. ___" placeholders; corrects mistyped S. Ct. volumes
python scripts/scdb_codebook.py          # caches SCDB variable labels in data/raw/scdb/codebook/
python scripts/add_scdb_cases.py         # adds SCDB cases the site lacks to scotus.js (re-runnable; after fix_citations.py)
python scripts/build_votes.py            # again, so the added cases get their votes
python scripts/build_ratings.py          # writes ratings.js (needs data/raw/mq/justices.csv from the Martin-Quinn site)
python scripts/build_stats.py            # writes stats.js and stcases-<decade>.js (the Statistics tab)
python scripts/build_models.py           # writes models.js: per-justice vote models + pending-case predictions (needs scikit-learn; re-run after docket.sh)
python scripts/oyez_fetch_all.py        # caches Oyez records for every case without a summary (slow; resumable)
python scripts/build_flashcards_terms.py   # writes fc-terms.js and fc-court-*.js (term-by-term decks)
python scripts/build_games.py           # writes games.js and essential.js
python scripts/build_constitution.py    # writes constitution.js (annotated Constitution)
python scripts/build_dictionaries.py    # writes founding-dict.js
python scripts/build_glossary.py        # writes glossary.js
python scripts/build_foundations.py     # writes foundations.js (OpenStax basics for each guide topic)
python scripts/build_statutes.py        # writes statutes.js (Wikipedia is rate-limited; the script backs off and caches)
python scripts/book_covers.py           # picks the sharpest cover for each book (cached)
python scripts/pron_scan.py && python scripts/narrate_all.py guide doctrine   # narration (CPU; hours). Then: python scripts/narrate_all.py --manifest
python scripts/fix_text.py              # LAST: repairs mojibake, adds ellipses to cut-off abstracts, drops non-abstracts, tidies text
sh scripts/stamp.sh                     # version stamps so browsers load the new files
```

OpenAlex works without an API key, but unkeyed requests share a small daily budget per IP address. If `openalex.sh` starts returning errors, wait a day or add `&api_key=…` to its URL.

## Running
```bash
powershell -ExecutionPolicy Bypass -File scripts/serve.ps1 -Port 8080
```
Then open http://localhost:8080. The site is fully static, so `docs/` can be deployed to any web host. Oyez case details and audio are fetched from api.oyez.org in the visitor's browser.

## Hosting on GitHub Pages
The site is served from the `docs/` folder of the `main` branch (Settings → Pages → Deploy from a branch → `main` / `/docs`).
After rebuilding the data, commit the changed files in `docs/data/` and push, and Pages redeploys automatically.
`data/raw/` is git-ignored because it can be regenerated.

## Known limitations
- Citation counts exist for about 8,000 articles. They are mostly for journals that OpenAlex covers well, and are sparse for BYU, Northwestern, Hastings, W&M and the WordPress journals.
- OpenAlex sometimes credits a reviewed book's citations to its review. Repeated titles are flagged as reviews, but a few single reviews of famous books still rank high.
- Georgetown has little coverage in OpenAlex.
- Opinion PDFs are missing for roughly the 2015–2016 terms, which fall between Library of Congress coverage and the slip-opinion listings. Those cases link to Justia.

## Before each commit

Run `sh scripts/stamp.sh` so visitors get the new files right away (GitHub Pages lets browsers cache files for 10 minutes).

## Narration pronunciations

AI narration (`scripts/narrate.py`, Kokoro voice `am_michael`) uses a pronunciation lexicon so names and legal terms are said correctly (e.g. Lujan = loo-HAHN):

- `python scripts/pronounce_fetch.py` caches sources in `data/raw/pron/`: Wikipedia pages for the case articles, the parties they link, the justices, and same-surname people; plus Wiktionary for legal Latin.
- `python scripts/pronounce_build.py` writes `scripts/pronounce.tsv` (term, phonemes, source). It keeps only words used in the narrated text whose sourced pronunciation differs from the voice engine's guess.
- `scripts/pronounce_manual.tsv` holds hand overrides, which win over the sourced entries; `-` keeps the engine's default.

## Narration

```
python scripts/pron_scan.py            # verify pronunciations of names and unusual words in every narrated section
python scripts/narrate_all.py guide doctrine   # docs/audio/ (in the repo)
python scripts/narrate_all.py conan    # ../audio-r2/ (Constitution Annotated, for Cloudflare R2)
```
Unverified words are listed in data/raw/pron/unverified.tsv; add corrections to scripts/pronounce_manual.tsv.

## Post-build fixes and additions

```
python scripts/fix_titles.py           # ALL-CAPS article titles -> title case (after build.ps1)
python scripts/retopic.py              # Jurisprudence, Democratic Theory, Taxation & Economic Regulation; "General" only as a fallback
python scripts/fix_citations.py        # "584 U.S. ___" -> real page (SCDB) or the S. Ct. citation; then rebuild flashcards
```

### Additional journals (high-impact articles only)

`scripts/sources_new.tsv` lists 39 more journals (Law Review Commons, WordPress sites, OpenAlex). Only articles whose
OpenAlex citations reach the 75th percentile of the existing index for their decade (minimum 3) are added.

```
SOURCES=scripts/sources_new.tsv bash scripts/harvest.sh
bash scripts/openalex.sh scr hjlpp uwlr utahlr smulr lcp jclc && perl scripts/openalex_flatten.pl
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -SourcesFile scripts/sources_new.tsv -OutFile data/raw/new_articles.js
python scripts/cite_lookup.py          # title lookups, ~20 per request; re-run daily until done (or set OPENALEX_KEY)
python scripts/merge_new.py            # re-runnable; replaces earlier merges of these journals
```

### Books

`scripts/books.json` holds the curated essentials (`essential: true`) plus about 300 more (`python scripts/books_more.py`).
`bash scripts/books.sh` fetches Open Library and Goodreads data; `perl scripts/build_books.pl` builds books.js and drops
non-essential books that Open Library cannot verify; then `perl scripts/books_impact_merge.pl`.
