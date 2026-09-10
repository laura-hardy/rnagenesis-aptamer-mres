# ENA aptamer candidate processing

Conservative triage of ENA/EMBL “RNA aptamer” search records into reviewable
**RNA aptamer – protein target** candidate tables.

This stage sits **after** inspection and **before** final corpus export.

## Scientific objective

Identify accessions that may contribute RNA aptamer–protein pairs with some
defensible experimental-binding evidence, suitable later for possible inclusion
in an RNA foundation-model fine-tuning corpus.

This stage does **not**:

* create a final training corpus under `data/processed/`;
* silently approve ambiguous records;
* auto-trim promoters, primers or flanks;
* convert every deposited `T` to `U`;
* infer a protein target from a cell/virus label without a named protein;
* treat small-molecule aptamers as core protein-target pairs;
* delete duplicates or collapse clone families;
* query external literature APIs.

## Pipeline stages

| Stage | Script | Role |
|---|---|---|
| Inspection | `inspect_ena_aptamer_records.py` | Inventory structure, phrases, signals, duplicates |
| **Candidate processing (this stage)** | `process_ena_aptamer_candidates.py` | Evidence assembly, grouping, provisional tiers, review queue |
| Final corpus inclusion | *(not yet)* | Literature-verified sequence–target pairs |

Rules live in `ena_candidate_rules.py` so classifications stay testable and
reusable.

## Inputs

Primary inputs are inspection outputs (no internet required):

```text
data/raw/ena/inspection/
├── ena_record_inventory.csv
├── ena_record_class_signals.csv
├── ena_feature_table_long.csv
├── ena_reference_summary.csv
├── ena_duplicate_summary.csv
├── ena_sequence_diagnostics.csv
└── ena_record_offsets.csv          # optional; for EMBL recovery
```

Optional EMBL flat file (recovery only):

```text
data/raw/ENA/ena_embl_20260720-0853.txt
```

If `data/raw/aptabase/aptabase_cleaned.csv` is present, exact sequence / DOI /
PMID matches are recorded as optional informational fields.

## Outputs

```text
data/raw/ena/candidates/
├── ena_candidate_records.csv
├── ena_candidate_groups.csv
├── ena_candidate_references.csv
├── ena_candidate_evidence_long.csv
├── ena_candidate_review_queue.csv
├── ena_candidate_exclusions.csv
├── ena_target_normalization_review.csv
├── ena_candidate_qc_report.md
└── ena_candidate_processing_log.txt
```

Every derived conclusion is backed by long-form evidence rows
(`evidence_type`, `source_field`, `source_text`, `evidence_strength`, notes).

## Candidate tiers (provisional)

| Tier | Meaning |
|---|---|
| `Tier_A_high_confidence` | Strong combined RNA + protein + binding/selection evidence; still reviewable |
| `Tier_B_plausible_needs_review` | Plausible RNA–protein candidate with unresolved details |
| `Tier_C_sequence_role_uncertain` | Relevant but sequence may be template / promoter / flanks / embed |
| `Tier_D_non_core_or_exclude` | Natural motif, riboswitch, DNA aptamer, non-protein target, etc. |
| `Tier_E_insufficient_information` | Aptamer wording present but target/binding not recoverable |

`signal_synthetic_selected` from inspection is **not** used as a final inclusion
criterion (it is too permissive).

## RNA identity

Statuses include `explicit_rna_aptamer`, `rna_molecule_type`,
`rna_described_but_dna_alphabet`, `possible_dna_template_for_rna`,
`dna_aptamer`, `uncertain_nucleic_acid_type`, `not_rna_aptamer`.

ENA RNA records commonly use `T` rather than `U`. Alphabet alone does **not**
decide biological molecule type. A derived `sequence_rna_normalized` (`T→U`) is
created only when RNA identity is sufficiently confident; the deposited
sequence is always retained unaltered.

## Protein-target logic

Targets are extracted preferentially from feature notes / products, then
description, then reference title (lower confidence).

Protein-compatible types: `protein`, `protein_complex`, `enzyme`, `antibody`.

`peptide` is kept separate. Small molecules, ions, nucleic acids, cells/tissues
and viruses without a named protein are non-core and written to the exclusions
table with reasons (not deleted).

## Binding evidence

Types include explicit affinity, binds/recognises statements, selection language,
functional inhibition, structure mentions, and title-only inference.

Strength: `strong` / `moderate` / `weak` / `none`.

Absence of SELEX wording does **not** automatically exclude a record. Synthetic
construct alone does **not** create Tier A.

## Sequence roles

Roles distinguish mature aptamers from DNA templates, promoter-bearing deposits,
primer-flanked library sequences, embedded constructs, riboswitches, natural
motifs and reverse-complement features.

Where a clear non-`source` feature location exists (including `complement(...)`),
a feature subsequence may be extracted with
`feature_sequence_extraction_method` recorded. Full-record sequences are never
trimmed in place.

## Duplicate / family grouping

Group IDs are assigned for exact sequence, RNA-normalised sequence, reverse
complement, reference, description and candidate experiment families.

Records are **not** collapsed. Same-sequence / different-target conflicts are
flagged. The later inclusion unit is expected to be a unique biological
sequence–target pair, not an ENA accession.

## Manual-review workflow

1. Read `ena_candidate_qc_report.md` for counts and largest families.
2. Work through `ena_candidate_review_queue.csv` by `review_priority`.
3. Use `ena_candidate_evidence_long.csv` for supporting text.
4. Resolve targets via `ena_target_normalization_review.csv` where needed.
5. Keep Tier D/E rows in `ena_candidate_exclusions.csv` until a human decision.

Suggested review actions: verify paper; confirm protein target; confirm mature
RNA sequence; inspect promoter/flanks; inspect feature coordinates; resolve
duplicate family; exclude natural motif; confirm binding evidence.

## Limitations

* ENA is not a curated aptamer database.
* Most records lack DOI/PMID (often patent bulk deposits).
* Deposits may include templates or flanks.
* Free-text target extraction can be incomplete or wrong.
* Tiers are provisional; literature verification is required before corpus use.

## Example commands

Using the project conda environment (`rnagenesis-mac`):

```bash
conda activate rnagenesis-mac

python scripts/data_preparation/process_ena_aptamer_candidates.py \
  --inspection-dir data/raw/ena/inspection \
  --output-dir data/raw/ena/candidates \
  --overwrite
```

Optional arguments:

```text
--input-embl PATH
--max-review-records N
--log-level INFO|DEBUG
--overwrite
```

Tests:

```bash
conda activate rnagenesis-mac
pytest tests/data_preparation/test_process_ena_aptamer_candidates.py -q
```
