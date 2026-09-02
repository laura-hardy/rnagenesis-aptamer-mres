# RiboAptamer CHECKPOINT-1 structured review schema

This note records the RiboAptamer CHECKPOINT-1 review-field extension and
fail-closed apply process. It contains no sequences and does not authorise S4.

The record-level human fields, recommendation fields, bulk-audit confirmation,
and fail-closed apply semantics reuse the AptaDB structured-review schema
documented in `docs/data_curation/aptadb_checkpoint1_review_schema.md`.

CHECKPOINT-1 remains a human-review gate. Machine `review_recommendation`
values are guidance only and must never be treated as `manual_decision`.

## RiboAptamer-specific routing

- S3 defers target classification, evidence scoring, and leakage exclusion.
- Source `Type` is review-context metadata only. It is not a parking rule.
- Length eligibility uses `len(sequence_core)`, not S2 length QC flags.
- Judgement-dependent truncation/alignment/primer/library conditions take
  CHECKPOINT-1 review precedence when they overlap automatic reasons such as
  `invalid_alphabet`. A single canonical `rejection_reason` is emitted;
  overlaps are retained in `secondary_reasons`, `qc_flags`, and
  `checkpoint_review_reasons`.
- Known T7 motif detections are unapplied trim proposals. Group-wise
  constant-region inference was disabled for the RiboAptamer S2/S3 run.

## Status

CHECKPOINT-1 is closed. Laura's 85-record review has been validated and
applied fail-closed. Group-wise constant-region inference remained
disabled. S4 has not begun. Target extraction has not been performed.

Human unresolved-constant observations are preserved from `manual_notes`:

- `CP1_FLAG:constants_suspected_unresolved` → `trim_status=constants_suspected_unresolved`
  with QC flag `constants_suspected_unresolved`. Sequence unchanged.
- `CP1_FLAG:possible_constants_unresolved` → warning QC flag
  `possible_constants_unresolved` with `trim_status=no_constants_detected`.

Informal `manual_trim_action=trim` is treated as schema `approve` of the
existing known-motif proposal. Trim lengths are not invented.
