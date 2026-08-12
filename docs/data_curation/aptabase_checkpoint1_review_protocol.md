# AptaBase CHECKPOINT-1 manual-review protocol

## Purpose

This protocol governs manual scientific review of AptaBase S3 provisional
eligibility decisions at CHECKPOINT-1. Review confirms, overrides or defers
proposed accept, park and reject outcomes before any record may proceed to S4
target and evidence curation. No decision is final until CHECKPOINT-1 review is
completed and validated. This protocol contains no source sequences.

## Meaning of the proposed decisions

- `proposed_accept` means the record is technically eligible to proceed to
  target and evidence curation at S4. It does **not** mean the record is
  accepted into the final fine-tuning corpus.
- `proposed_park` means the record is unresolved but potentially recoverable
  after further scientific or source review. Parked records must not proceed to
  S4 until an approved override permits them.
- `proposed_reject` means the record is unsuitable under the current S3
  technical eligibility rules. Rejected records do not proceed to S4 unless an
  approved override changes that outcome.
- No proposed decision is final until CHECKPOINT-1 review is completed and
  validated.

## Review scope

Active review covers only records with `manual_review_required=true` in the
CHECKPOINT-1 decision sidecar (431 AptaBase rows). Mechanical missing-sequence
rejects and clean no-review accepts remain outside the active queue
(`manual_review_required=false`). Reviewers work from the ignored
sequence-bearing queue and may consult the sequence-free index for safe
summaries.

## Review batches

Each active row is assigned exactly one deterministic batch:

| Batch code | Scope |
|---|---|
| `01_reject_review` | Proposed rejects requiring review (excludes missing-sequence) |
| `02_accept_with_diagnostics` | Proposed accepts that still require manual review |
| `03_park_unresolved_molecule` | Parked unresolved molecule type |
| `04_park_ssdna` | Parked explicit ssDNA |
| `05_park_invalid_sequence` | Parked invalid sequence |
| `06_park_overlength` | Parked overlength cores |
| `07_park_mixed_t_u` | Parked mixed T/U |
| `08_park_trim_construct` | Parked trim or construct review |
| `09_park_ambiguous` | Parked ambiguous sequence |

## Permitted reviewer actions

Reviewers may record exactly one of:

- `confirm_current` — retain the proposed decision.
- `override_to_accept` — permit the record to proceed to S4.
- `override_to_park` — retain for later recovery but do not send to S4.
- `override_to_reject` — exclude from later corpus processing.
- `needs_source_review` — insufficient evidence; publication or source review
  is required before deciding.

The human `review_action` is the authoritative checkpoint judgement. A blank
`reviewer_note` does not invalidate any permitted action, including overrides
and `needs_source_review`.

## Review criteria

- Prefer technical evidence already present in the review package (molecule
  type, alphabet, lengths, QC flags, construct/trim status, leakage flags and
  source validity).
- Do not invent target, affinity, UniProt, cluster or partition annotations at
  this checkpoint.
- Treat leakage matches, source-invalid records and unresolved sequence or
  construct issues as high-scrutiny cases.
- Prefer `needs_source_review` when the available fields are insufficient for a
  confident confirm or override.
- Do not approve CHECKPOINT-1 as a whole from a partial batch; completion is
  package-wide.

## Batch-specific guidance

- `01_reject_review`: confirm short-core and source-invalid rejects unless clear
  evidence shows the technical rule was misapplied.
- `02_accept_with_diagnostics`: confirm technical accepts that carry only minor
  diagnostics, or park/reject if diagnostics undermine S4 readiness.
- `03_park_unresolved_molecule`: resolve only when molecule type is scientifically
  clear; otherwise confirm park or request source review.
- `04_park_ssdna`: keep parked for the RNA training corpus unless an override is
  explicitly justified.
- `05_park_invalid_sequence` / `09_park_ambiguous` / `07_park_mixed_t_u`: do not
  override to accept without correcting or explaining the sequence issue.
- `06_park_overlength`: consider whether fixed regions or full constructs
  explain length; do not auto-accept.
- `08_park_trim_construct`: require clear construct evidence before any accept
  override.

## Recording decisions

Record decisions in the ignored sequence-bearing review CSV:

- `review_action` — one permitted action from the list above (required;
  authoritative).
- `reviewer_note` — optional supplementary rationale for any action, including
  overrides and `needs_source_review`.
- `reviewer_initials` — optional; not auto-populated.

A row is complete when:

- `review_action` is nonempty and valid.

Notes are optional supplementary rationale. Absence of a note does not
invalidate an override or any other permitted action.

## Single-reviewer convention (AptaBase CHECKPOINT-1)

This AptaBase checkpoint used a **single reviewer**. Reviewer initials were
intentionally omitted (`reviewer_initials` left blank;
`review_model=single_reviewer`; `reviewer_initials_required=false`). Reviewer
notes were optional (`reviewer_notes_required=false`). The reviewer's name is
not recorded in tracked artefacts.

The human `review_action` is the authoritative checkpoint judgement. Any
supplied notes are preserved in ignored working data and cryptographically
linked in the tracked resolution manifest via per-row `reviewer_note_sha256`
(empty when the note is empty). The completed ignored review file is also bound
through the review-file SHA-256 recorded in checkpoint metadata.

Full reviewer-note text remains only in ignored working data under `data/`.
CHECKPOINT-1 closure authorises only resolved accepts
(`authorised_for_s4=true`) to proceed to S4; parked, rejected and
`needs_source_review` records do not.

## What this checkpoint does not decide

CHECKPOINT-1 does not:

- normalise targets or map UniProt accessions;
- score binding evidence or interpret affinity;
- deduplicate, cluster, balance or partition the corpus;
- approve final fine-tuning membership;
- authorise S4 for any record before package validation.

## Completion requirements

CHECKPOINT-1 review is complete only when every active queue row has a valid
nonempty `review_action`, batch counts still reconcile, and a separate
validation step confirms the package against its pristine baseline. Notes and
initials may remain blank. Until package validation and closure succeed the
checkpoint remains unapproved.

## Closure status

CHECKPOINT-1 for AptaBase is closed after validated application of the completed
human review. Only records with `authorised_for_s4=true` (resolved accepts) may
proceed to S4. S4 target normalisation has not been started by this protocol.
