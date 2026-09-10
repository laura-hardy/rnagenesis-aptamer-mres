# Source-preparation methodology (pre-S1)

Some Tier-1 source inputs required substantial acquisition, parsing, cleaning,
or manual-review preparation before a frozen snapshot could be registered.
Those pre-S1 methods remain in Git as methodological provenance. They are
not part of the current S1–S3 execution path.

```text
source acquisition / preparation
        ->
frozen source snapshot
        ->
S0 registry
        ->
S1–S3 corpus curation
```

Keeping this code in version control documents how heterogeneous source
material was transformed into the authoritative registered input. It does
not make the historical workflow operational again. Current adapters must not
import these scripts, and the frozen registered files remain the live inputs.

## AptaBase

`scripts/data_preparation/scrape_aptabase.py`,
`aptabase_parser.py`, and `aptabase_cleaning.py`, with
`README_aptabase.md` and the associated parser/cleaning tests, document
preparation of the AptaBase scrape that became the registered cleaned source
(`data/raw/aptabase/aptabase_cleaned.csv`).

The live AptaBase S1 adapter reads that frozen registered input. It does not
rerun website acquisition, HTML parsing, or the historical cleaner.

## ENA

The ENA preparation scripts document the workflow from a heterogeneous EMBL
download through:

1. inspection / parsing (`inspect_ena_aptamer_records.py`)
2. candidate processing (`process_ena_aptamer_candidates.py`)
3. review consolidation (`consolidate_ena_candidate_review.py`)
4. review-v2 group-first refinement (`refine_ena_manual_review.py`)

together with their READMEs, synthetic tests, and the synthetic EMBL fixture
`tests/data_preparation/fixtures/ena/synthetic_aptamer_cases.embl`.

Those steps produced the authoritative 679-row selected lane later frozen
in the source registry. Current ENA S1 begins from that frozen reviewed
selected file. It does not rerun EMBL inspection, candidate extraction, or
manual-review preparation.

Tracked ENA rule and finalisation modules
(`ena_candidate_rules.py`, `ena_review_rules.py`, `ena_review_v2_rules.py`,
`finalize_ena_aptamer_supplement.py`) remain part of that documented
preparation layer. Their primary unit tests live with these files.

## Architectural boundary

The current corpus pipeline consumes frozen registered snapshots only:

```text
historical source preparation
        ->
frozen registered source input
        ->
S0 / S1–S3
```

Do not reintegrate these scripts into S1, S2, or S3 adapters. Do not rerun
them against `data/raw` as part of ordinary curation. They are retained as
pre-S1 source-preparation methodology, not as disposable remnants.
