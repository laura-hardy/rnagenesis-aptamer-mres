# AptaDB CHECKPOINT-1 structured review schema

This note records the CHECKPOINT-1 review-field extension used before AptaDB
human review. It contains no sequences and does not authorise S4.

CHECKPOINT-1 remains a human-review gate. Machine `review_recommendation`
values are guidance only and must never be treated as `manual_decision`.

## Record-level human fields

- `manual_decision`: blank / `keep` / `drop` / `edit`
- `manual_sequence_corrected`: reviewed source sequence, if edited
- `manual_target_corrected`: reserved; unused at this checkpoint
- `manual_molecule_type_override`: blank / `RNA` / `ssDNA`
- `manual_chemistry_override`: blank or a canonical chemistry vocabulary value
- `manual_trim_action`: blank / `approve` / `override` / `reject` / `defer`
- `manual_trim_5p_nt` / `manual_trim_3p_nt`: non-negative integers or blank
- `manual_trim_group_override`: blank / `true` / `false`
- `manual_notes`

Trim lengths are nucleotide counts removed from reviewed `sequence_full`.
They are not hand-pasted core coordinates.

## Recommendation fields

Separate from human fields:

- `review_recommendation`
- `review_rationale`
- `requires_specific_human_decision`
- `recommended_*` counterparts for decision, molecule, chemistry, trim, and
  sequence-correction operator

Preparing the package may fill recommendation fields. It must leave every
`manual_*` field blank.

## Group-level artefact

`aptadb_checkpoint1_constant_group_review.csv` has one row per constant-region
proposal group. A group decision applies to linked records by default.
A nonempty record-level trim action takes precedence. Application is
fail-closed: deferred trims do not become `keep`, and invalid lengths stop
the run.

## Provenance

`sequence_raw` remains the original AptaDB source sequence. Future application
re-runs shared molecule-aware normalisation after any sequence or molecule
correction, then applies approved numeric trims to `sequence_full`.

Evidence, target canonicalisation, leakage, clustering and partitioning remain
S4+ work.

## Status

CHECKPOINT-1 is prepared for structured human review. It is not complete and
has not been applied.
