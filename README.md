# Lex Constitutio

A PhilPapers-style hub for constitutional law. It is a static site (`docs/`) built from openly published metadata.

## Sections
- **Articles:** about 22,600 constitutional law articles from 27 law reviews. Includes full-text search, a topic taxonomy (5 areas, 29 subtopics), filters, author pages, and Bluebook and BibTeX citations.
- **Most influential (in Articles):** OpenAlex citation counts with a percentile within each decade, a "Most cited" sort, and rankings by topic, decade and journal.
- **Supreme Court:** about 8,500 cases from Oyez. Each has a summary, the official one-line holding (recent terms), and an opinion PDF (supremecourt.gov or Library of Congress). Argument and opinion-announcement audio plays on the page with a synced, click-to-seek transcript.
- **Current docket:** undecided cases for the current Term with the Court's argument calendar, status, questions presented, merits and amicus briefs, transcript PDFs, and argument audio (Oyez, or the Court's own MP3 until Oyez posts it). Every case page has a Precedents panel listing cases named in the Oyez summary and the most closely related decisions.
- **Lectures:** about 230 lectures and debates from law schools, universities and constitutional institutions, embedded from YouTube.
- **Beginner's Guide:** 20 beginner topics (overview, Wex link, explainer videos, landmark cases, starter books and articles), followed by an advanced doctrine section in 14 parts and 52 sections. The advanced section has original doctrinal summaries, black-letter tests, 179 linked cases, and excerpts from the opinions (`scripts/advanced/*.md`).
- **Originalist's Corner:** 37 topics with passages from Blackstone, Tucker, Story, Kent, Vattel, Locke, The Federalist, Madison's Notes, founding documents and the acts of the first five Congresses, plus an on-site library of full texts.
- **Quizzes:** 5 multiple-choice questions at the end of each beginner topic, and 4–8 Socratic-style case questions at the end of each advanced part (`scripts/quizzes/*.txt` → `build_quizzes.pl`). Answers show explanations, and the best score is kept in the browser.
- **Quiz Me!:** 1,794 spaced-repetition flashcards for 560 essential Supreme Court cases in 20 topic decks. Cards are graded Again / Hard / Good / Easy (Anki-style SM-2 scheduling), with daily limits, sibling burying and per-profile progress in localStorage (export/import to move devices), plus a stats view. "What did the Court decide?" answers have three parts: Background (Oyez facts of the case, including what the law at issue says), Ruling (Oyez description and conclusion, plus the vote) and Importance (the advanced-section notes, the Constitution Annotated, and Congressional Research Service Legal Sidebars published after the decision; both public domain). Oyez text is CC BY-NC 4.0, so it is credited and linked on every card and the site must stay non-commercial.
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
bash scripts/corner.sh && bash scripts/wikisource_retry.sh   # founding-era sources (Wikisource rate-limits; the retry script backs off)
perl scripts/build_corner.pl           # writes corner.js and library-*.js
perl scripts/build_advanced.pl         # writes advanced.js from scripts/advanced/*.md
bash scripts/conan_fetch.sh && python scripts/conan_extract.py && perl scripts/build_conan.pl   # Constitution Annotated commentary (PDFs in data/raw/conan from GovInfo)
perl scripts/build_quizzes.pl          # writes quizzes.js from scripts/quizzes/*.txt
python scripts/build_votes.py          # writes votes.js (justice votes: SCDB CSVs in data/raw/scdb/csv/ + lineups parsed from opinion PDFs)
python scripts/crs_fetch.py           # caches CRS Legal Sidebars (public domain) from EveryCRSReport in data/raw/crs/
python scripts/flashcards_fetch.py     # caches Oyez case details (facts, conclusion, vote) in data/raw/oyez/cases/
perl scripts/build_flashcards.pl       # writes flashcards.js (run after build_extras.pl and build_advanced.pl)
perl scripts/flag_reviews.pl           # confirms book reviews via Open Library so they leave the article rankings
bash scripts/books_impact.sh && perl scripts/books_impact_merge.pl   # citation counts for books (Books tab only)
bash scripts/docket.sh && perl scripts/build_docket.pl   # current docket, calendar, briefs (re-run weekly during the Term)
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
