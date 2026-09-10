# ENA candidate review consolidation

Clerical consolidation of provisional ENA aptamer–protein candidates into
reviewable **experiment-family** and **sequence–target** units.

This stage sits **after** inspection and candidate processing. It does **not**
replace those stages, does **not** write a final fine-tuning corpus, and does
**not** auto-approve sequences.

## Scientific objective

Eventual corpus unit:

```text
one unique RNA aptamer sequence – protein target pair
```

with a concrete RNA sequence, a named protein/enzyme/complex/antibody target,
binding/selection/claim evidence, and provenance to supporting ENA accessions.

The accession-level review queue is highly repetitive (exact duplicates, near
variants, patent families). This stage consolidates before manual review while
**never silently merging distinct biological sequences**.

## Pipeline stages

| Stage | Script | Role |
|---|---|---|
| Inspection | `inspect_ena_aptamer_records.py` | Inventory, signals, duplicates |
| Candidate processing | `process_ena_aptamer_candidates.py` | Evidence, tiers, review queue |
| **Review consolidation (this stage)** | `consolidate_ena_candidate_review.py` | Exact/near-dup consolidation, repair, templates |

Rules live in `ena_review_rules.py`.

## Inputs

```text
data/raw/ena/candidates/
├── ena_candidate_records.csv
├── ena_candidate_groups.csv
├── ena_candidate_review_queue.csv
└── (optional evidence / exclusions / references)
```

Paths are resolved case-insensitively (`ENA` / `ena`).

## Commands

```bash
python scripts/data_preparation/consolidate_ena_candidate_review.py build-review \
  --candidate-dir data/raw/ena/candidates \
  --output-dir data/raw/ena/review \
  --overwrite
```

```bash
python scripts/data_preparation/consolidate_ena_candidate_review.py apply-review \
  --review-file data/raw/ena/review/ena_manual_review_template.csv \
  --output-dir data/raw/ena/review
```

No internet access is required.

## Outputs

```text
data/raw/ena/review/
├── ena_experiment_group_review.csv      # Level 1: family / patent review
├── ena_sequence_target_review.csv       # Level 2: unique sequence–target
├── ena_sequence_family_summary.csv      # Near-duplicate families
├── ena_target_repair_review.csv
├── ena_ambiguous_library_sequences.csv
├── ena_short_sequence_review.csv
├── ena_sequence_target_provenance.csv   # One row per unit–accession
├── ena_review_qc_report.md
├── ena_manual_review_template.csv       # Excel-friendly (utf-8-sig)
├── ena_selected_after_manual_review.csv
├── ena_rejected_after_manual_review.csv
└── ena_review_processing_log.txt
```

## Two-stage clerical review

### Level 1 — experiment / patent family

`ena_experiment_group_review.csv`: one row per candidate experiment group.
Decide whether the family is worth sequence-level review.

`manual_group_include`:

| value | meaning |
|---|---|
| `1` | retain group for sequence-level review |
| `0` | reject group |
| blank | not yet reviewed |

Manual columns are left blank by `build-review`.

### Level 2 — unique sequence–target

`ena_sequence_target_review.csv`: one row per **RNA-normalised sequence +
repaired normalised target** (only when the sequence is concrete/recoverable).

Exact duplicate accessions collapse into one row; provenance is retained in
`ena_sequence_target_provenance.csv`.

Near-duplicate (non-identical) sequences stay as **separate** rows but share a
`near_duplicate_family_id` when related within the same experiment group and
proposed target.

`manual_include`:

| value | meaning |
|---|---|
| `1` | include this sequence–target pair |
| `0` | exclude it |
| blank | not reviewed |

## Exact vs near-duplicate policy

* **Exact key**: RNA sequence + repaired target key (`FGF2` ≡ `FGF-2`).
* **Near duplicates**: compared only within experiment group + target.
  Equal-length Hamming ≤ `max(2, ceil(0.05 × L))`; edit distance / max length
  ≤ 0.08; substring truncation/extension when shorter ≥ 15 nt and ≥ 50% of
  longer. Reverse complements are flagged. Sequences are **not** merged.

## Sequence quality

Statuses include `concrete_candidate_sequence`, `limited_ambiguity`,
`degenerate_library_template`, `too_short_requires_review`,
`long_construct_requires_review`, `promoter_or_template_requires_review`,
`missing_or_invalid`.

Library templates (many `N`s / high ambiguity / random-library language) go to
`ena_ambiguous_library_sequences.csv` and are excluded from the main template.
Ambiguous bases are never silently removed.

Short sequences (&lt;20 nt) are flagged in `ena_short_sequence_review.csv` and
are **not** auto-rejected.

## Target repair

Structured forms such as “extracellular domain of PAP”, “X region of Y
protein”, and “surface protein TSA56 …” are split into name / region /
organism. Generic phrases (“target protein”, “use thereof”, “same”) become
`unknown`. Compound codes / “analogue thereof” become
`unknown_or_probable_small_molecule`.

## Binding evidence scope

`evidence_scope` distinguishes individual quantitative/qualitative claims from
experiment-family and patent-claim language. Family-level claims are **not**
upgraded to individual evidence.

## Manual review template

`ena_manual_review_template.csv` is a subset of eligible sequence–target rows,
ordered by experiment group → target → near-duplicate family → length →
sequence. Manual fields are blank. Written with `utf-8-sig` for Excel.

Eligibility (all required):

* RNA identity plausible or explicit
* repaired target protein / enzyme / complex / antibody
* concrete sequence or limited ambiguity
* not a clear large construct (&gt;500 nt / long-construct status)
* some aptamer or binding/selection claim at record or group level

## Applying decisions

`apply-review` accepts only blank / `0` / `1` for `manual_include`. Included
rows use corrected target/sequence when supplied. Ambiguous included sequences
require `allow_ambiguous_include=1`. Blank rows stay **unreviewed** (not
rejected).

## Tests

```bash
pytest tests/data_preparation/test_consolidate_ena_candidate_review.py -q
```
