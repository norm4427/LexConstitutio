# Handoff notes (Nov 25–27, 2026)

Context for picking this work up on another computer. README.md covers how the site and build work; this file covers
what changed in this round of work, what is still running, and what does not travel with the repo.

## Set up on a new computer

1. `git pull`. Everything finished is on `main`.
2. **Recreate `.keys.env`** in the repo root. It is gitignored, so it is not in the repo. Each line is `NAME=value`,
   with no quotes. `scripts/local_keys.py` loads it, and every script that needs a key imports that module. Keys in use:
   `YT_API_KEY`, `NYT_API_KEY`, `GUARDIAN_API_KEY`, `COURTLISTENER_TOKEN`, `DATA_GOV_KEY` (GovInfo + Congress.gov) and
   `OPENALEX_KEY`. Optional and still blank: `S2_API_KEY`, `PODCASTINDEX_KEY`/`PODCASTINDEX_SECRET`,
   `GOOGLE_BOOKS_KEY` and `ANTHROPIC_API_KEY` (AI case briefs). CORE was skipped because its terms don't allow a public site.
3. **`data/raw/` is gitignored** (hundreds of MB of caches), so a new machine starts without them. The scripts refetch
   what they need, but some rebuilds expect caches:
   - `data/raw/cap/scotus_compact.json` (CAP citation graph): needed by `build_case_impact.py`, `build_precedents.py`
     and `build_crosslinks.py`. Refetch with `cap_fetch.py`.
   - `data/raw/corner`: needed by `build_corner.pl`. Don't rerun that script without it, or the Corner empties. After
     any rerun, run `corner_curated.py`.
   - Media caches (`data/raw/media/`): `build_media.py` now merges the previous build's entries, so a missing cache
     loses nothing.
   - Copy `data/raw/` across if you can.
4. Python: `build_models.py` needs scikit-learn < 1.8 (1.7.2) to reproduce the model numbers.
5. Local preview: `powershell -File scripts/serve.ps1 -Port 8090`.

## Rules that still apply

- **Never run `open_copies.py`.** It wipes and rebuilds every free-copy (`oa`) link.
- After rebuilding data, run `sh scripts/stamp.sh`, then **`python scripts/fix_text.py` last**.
- Free-copy matches must agree on journal, volume and first page and/or title, with year ±1, on an institutional or
  official host. No SSRN. Only link Internet Archive items that are openly readable (not borrow-only).
- Data files are single-line `window.X = {json};`. Write them so they round-trip byte-identical.
- In `docs/app.js`, write string escapes with Python, not an editor. A literal newline inside `split('\n')` once broke
  the whole site. There is no Node on this machine to syntax-check, so check in the browser.

## What changed

**Free copies of articles** (`articles.js` `oa`/`oav`)
- Open copies went from 1,247 to 4,561. 3,774 of 25,203 non-review articles still have no free route.
- Scripts: `archive_copies.py`, `repo_copies.py` (84 OAI repositories), `modern_copies.py`, `pd_copies.py`,
  `more_copies.py` (journal-site PDFs, Unpaywall, Internet Archive `sim_` scans, Wayback, HathiFiles + Extracted Features).
- Remaining gaps: mostly Harvard, Columbia and Virginia from 1931–89, which are in copyright and only on HeinOnline or
  JSTOR. HathiTrust has no full-view volumes for Columbia, Virginia, Yale, California or Penn from 1923 on, nor any of
  these journals for 1931–63. The HathiTrust Data API is retired; use HathiFiles and Extracted Features 2.0 instead.

**Article metadata**
- Citation counts: 13.5k → 19.8k (OpenAlex).
- Abstracts: 3,215 cut-off abstracts replaced with the full text, plus more from Crossref (`abstracts_fetch.py`, `fill_meta.py`).
- Volumes: 1,473 added. Topics: 537 reclassified out of "general".
- Authors: almost none findable, because the articles missing one are unsigned student notes.

**Cases**
- Summaries: cases with no summary went from 2,191 to about 309 (`case_summaries.py`: CAP headnotes, LOC syllabi,
  Wikipedia leads, CourtListener, GovInfo syllabi).
- Opinion PDFs: every decided case has one. Transcripts: 10 missing.
- Impact scores: 28,055 of 29,115 cases (`build_case_impact.py`; CAP PageRank, plus CourtListener counts after 2019).
- Precedents panel (`build_precedents.py`, `docs/data/prec*`): from the citation graph, ranked by relevance to the case.
  It shows precedents relied on, later citing decisions, related decisions (citation coupling) and overruled flags.
- Article ↔ case links (`build_crosslinks.py`, `docs/data/xl/`): two-way, including 987 articles cited by the Court.
- Authorities tab: 1,697 cases (`build_authorities.py`, `osg_briefs_fetch.py`).
- In the media: news from the Guardian and NYT (strict matching) and more YouTube videos (`media_fetch.py`, `build_media.py`).
- Cornell LII links: by docket from 2000 on, by U.S. Reports cite before that.

**Vote prediction** (`build_models.py`, `build_arguments.py`, `model_directions.py`)
- A boosted trees + random forest average per justice.
- New predictors: oral-argument interruptions and first/last question by side, and Martin-Quinn scores.
- 2022–25 holdout: winning side 73.0% (always reverse 66.4%), votes 72.0%.
- Each case page shows the chance of the winning side and the likeliest split separately. The justices' probabilities
  are the margins of the joint split distribution (`check_splits()`).
- Research notes are in `model-research.md` in the old machine's session notes folder; not in the repo.

**Other sections**
- Annotated Constitution: panels for all 134 units, plus more cases, founding material and statutes per clause
  (`clauses.py`, `build_constitution.py`, `clause_extras.py`).
- Statutes: GovInfo text links, and legislative histories from Congress.gov for 125+ of 140 (`build_statutes.py`).
- Library: Farrand I–II, Elliot, Kent, Annals, 14 Gutenberg works, and Wilson's *Lectures on Law* (1804 ed.)
  (`library_books.py`).
- Originalist's Corner: curated passages for the thin topics (`corner_curated.py` + `.json`).
- Dictionaries: six sources, plus the word inspector (`build_dictionaries.py`).
- Guide: more lectures, landmark cases and books per topic (`guide_cases.py`, `guide_extra_lectures.json`).
- Books: publisher, note, reviews and citations (`books_enrich.py`, `books_notes.tsv`).
- Justices: FJC education, career and confirmation facts (`justices_facts.py`).
- Justice charts: fixed outlined labels and the collapsed hover box (`styles-stats.css`).

## In progress / not committed when this was written

- **"Works cited" lists from article footnotes.** In progress: `scripts/fulltext_cites.py` and its `docs/app.js` edits
  are uncommitted on the old machine. It parses citations from the free full texts we link (cached in the gitignored
  `data/raw/fulltext/`) and matches them to indexed articles and cases. It shows "Works cited", "Cases cited" and
  "Cited by" on article pages. It was mid-pilot (~600 articles) before precision checks and the full run.
- **CourtListener daily runner** (old machine, background). The token allows about 125 requests a day. It is filling
  citation counts after 2019, then summaries for the last ~309 cases. Resume with `python scripts/courtlistener.py`.
  It picks up from its cache.

## Machine-local things that don't move with the repo

- **Scheduled task "Lex Constitutio: daily media searches"** (Claude app, 8:00 AM daily). It runs
  `media_fetch.py search`, `guardian` and `nyt`, then `build_media.py`, stamp and fix_text, and commits only the media
  files. Recreate it on the new machine, or disable it on the old one so two machines don't run it. It reports
  "BACKLOG FINISHED" when nothing is left to search.
- Claude sub-sessions and their notes (gap audit, model research, free-copy reports) are in the old machine's
  `%APPDATA%\Claude\side-session-notes\`.

## Open ideas

- Restyle the line charts' year tooltips (they still use the browser's native tooltip).
- Show the official U.S. Reports syllabus alongside the Oyez summary on the 267 cases that have both.
- Add the other works printed in Wilson's vol. III (1774 Considerations, the 1787 speech, the 1791 grand-jury charge).
- An Anthropic key would allow AI briefs for the cases still without a summary.
- Ask Columbia, Virginia and Stanford to post back-issue PDFs. That is the main remaining route to free copies from 1964–2009.
