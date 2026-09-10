# AptaBase extraction and cleaning

Transparent, reproducible scraper for the publicly displayed AptaBase search results.

## Purpose

Retrieve aptamer records shown on the AptaBase website, preserve an exact raw CSV of website values, and produce a conservatively cleaned CSV plus a quality-control report for academic research on RNA/DNA aptamers.

**Public accessibility does not imply permission to redistribute the complete database.** These scripts retrieve displayed records for academic research. Cite the original AptaBase database and the primary publications for each aptamer before reuse.

## Source

- Search interface: <https://www.iitg.ac.in/proj/aptabase/aptasearch.php>
- Example page URL: `https://www.iitg.ac.in/proj/aptabase/aptasearch.php?page=1`

### AptaBase citation (from the website)

> Vinay Bachu, Lazmy Deware, Ayush Kumar, Pooja Rani Kuri, Malaya Mili, Naveen Kumar Singh, & Pranab Goswami. Aptabase: An aptamer database, October 24 (2021): www.iitg.ac.in/proj/aptabase

## Repository paths

```text
data/raw/aptabase/
  html/                     # cached live HTML pages
  fixtures/                 # manually saved pages for offline development
  aptabase_raw.csv
  aptabase_cleaned.csv
  aptabase_qc_report.md
  aptabase_scrape_log.txt

scripts/data_preparation/
  scrape_aptabase.py        # CLI orchestration + downloader
  aptabase_parser.py        # HTML → raw records
  aptabase_cleaning.py      # raw → cleaned + QC report
  README_aptabase.md        # this file

tests/data_preparation/
  test_aptabase_parser.py
  test_aptabase_cleaning.py
```

## Dependencies

Python 3.10+ with:

```text
requests
beautifulsoup4
pandas
ftfy
pytest
```

Using the project conda environment:

```bash
conda activate rnagenesis-mac
pip install ftfy   # if not already installed
# requests, beautifulsoup4, pandas, pytest are already listed in environment/mac_environment.yml
```

Do not rely on the scripts to install packages automatically.

## Workflow

### 1. Parse fixtures only (offline)

```bash
conda activate rnagenesis-mac
python scripts/data_preparation/scrape_aptabase.py parse-fixtures
```

### 2. Download live pages

```bash
python scripts/data_preparation/scrape_aptabase.py download --start-page 1 --max-pages 100
```

Useful options:

| Option | Default | Meaning |
|--------|---------|---------|
| `--start-page` | 1 | First page to request |
| `--max-pages` | 100 | Safety maximum pages to walk |
| `--delay` | 2.0 | Seconds between **uncached** live requests |
| `--timeout` | 30 | Request timeout (seconds) |
| `--overwrite` | off | Overwrite existing cached HTML |
| `--log-level` | INFO | Logging verbosity |

Caching and resume:

- Each page is saved as `data/raw/aptabase/html/page_NNN.html`.
- Existing files are reused unless `--overwrite` is set, so an interrupted scrape can be resumed safely.
- The scraper waits at least two seconds between live requests, uses one sequential `requests.Session`, and retries HTTP 500/502/503/504 up to three times.
- Repeated HTTP 403 or 429 responses stop the download cleanly.

Pagination stops when:

1. a page has zero table data rows; or
2. a page repeats the same record IDs/content as the previous page; or
3. the configurable maximum page limit is reached.

Do not assume page 61 is final: the saved page 61 links to page 62.

### 3. Build outputs from cache (offline)

```bash
python scripts/data_preparation/scrape_aptabase.py build
python scripts/data_preparation/scrape_aptabase.py build --fixtures-only
```

`build` does not require internet access when HTML is already cached (or when `--fixtures-only` is used).

### 4. Download and build

```bash
python scripts/data_preparation/scrape_aptabase.py all --start-page 1 --max-pages 100
```

### 5. Tests

```bash
pytest tests/data_preparation/ -q
```

## Output schemas

### Raw CSV (`aptabase_raw.csv`)

One row per HTML table row. Values are website text without scientific normalisation.

Columns: `record_id_raw`, `aptamer_name_raw`, `target_general_raw`, `target_specific_raw`, `reported_length_raw`, `affinity_raw`, `buffer_raw`, `gc_content_raw`, `sequence_raw`, `reference_raw`, `source_page`, `source_url`, `source_html_file`, `retrieved_at_utc`, `row_parse_status`, `row_parse_warnings`.

Encoding: UTF-8 with BOM (`utf-8-sig`) for Excel inspection.

### Cleaned CSV (`aptabase_cleaned.csv`)

Conservatively repaired text, structured affinity fields, sequence normalisation, GC checks, DOI/PMID extraction when explicit, duplicate-group labels, and `record_validity`.

See `aptabase_cleaning.CLEANED_COLUMNS` for the full ordered schema.

### QC report (`aptabase_qc_report.md`)

Summary counts, ID gaps (informational; IDs may be non-contiguous by design), alphabet/molecule-type distributions, duplicate diagnostics, and invalid/major problem record IDs.

## Sequence-normalisation rules

- Always keep `sequence_raw`.
- `sequence_clean` removes only obvious formatting: whitespace, line breaks, terminal `5'`/`3'` (including curly primes), and quote/dash ornaments around those labels.
- Letters are uppercased.
- Unknown internal characters are **not** silently deleted; substantial non-nucleotide content → `invalid`.
- Alphabets: `DNA`, `RNA`, `mixed_T_U`, `ambiguous`, `missing`, `invalid`.
- **Never** convert T↔U.
- A sequence containing T is not assumed to be a mature DNA aptamer; some records may show DNA transcription templates for RNA aptamers.
- `possible_DNA_template_for_RNA` is used only when the reference explicitly indicates an RNA aptamer **and** the sequence is DNA-like / contains a likely T7 promoter motif.

## Affinity-parsing limitations

- Heterogeneous free text; many rows lack units.
- Supported concentration units: M, mM, µM/uM/micro Molar, nM, pM, fM.
- Supports exact values, inequalities, ± uncertainty, and simple ranges.
- `kcal.mole-1` / `kcal/mol` → `energy_or_other`; `affinity_molar` left blank.
- `NA` / `na nM` are unavailable, **not** zero.
- Numeric values without recoverable units keep the number but leave unit/molar blank.
- No Crossref/PubMed lookups are performed.

## Duplicate handling

Duplicates are **retained**. A probable duplicate key uses normalised aptamer name + normalised specific target + reported length. Matching clusters receive a `duplicate_group` ID. The QC report summarises duplicate names, sequences, name–target pairs, conflicting sequences, and groups where one sequence is missing.

## Record validity

Every row appears in both raw and cleaned outputs.

- `invalid`: several strong problems (non-numeric ID/length, clearly non-nucleotide sequence, nonsensical target category, placeholder reference, multiple short random fields). Known spam-like record **618** is expected to be invalid.
- Missing sequence, unavailable affinity, length disagreement, or uncertain molecule type alone → normally `valid_with_warnings`, not `invalid`.

## Known data-quality issues

- Mojibake in affinity/reference text (`Â±`, `Î¼M`, `â€“`).
- Incomplete reconstruction of placeholders such as `TGF-??1`.
- Corrupted terminal primes in some sequences (`5?`, `5�`); the cleaner strips these when they are clearly terminal labels.
- Non-contiguous database IDs (for example page 61 jumps 605 → 613).
- Occasional blank sequences with otherwise complete metadata.
- Some “Sequence” fields contain peptides or other non-nucleotide text; these are retained and marked `invalid`.
- Affinity fields mixing concentration and free-energy units.
- Displayed sequences may include primer/promoter regions; this pipeline does **not** auto-trim them.
- Live page 62 returns an empty results table (pagination “Next” from page 61 is a dead end).

## Warning for training corpora

**Database records should be checked against their cited publications before inclusion in a training corpus.** Prefer primary-literature sequences and assay conditions over secondary database text whenever they disagree.
