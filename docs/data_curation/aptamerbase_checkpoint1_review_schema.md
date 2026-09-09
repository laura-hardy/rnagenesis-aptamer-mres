# AptamerBase CHECKPOINT-1 review schema (decision-support audit)

This note records the AptamerBase CHECKPOINT-1 structured-review fields,
bulk-audit confirmation, and decision-support recommendation vocabularies.
It contains no sequences and does not authorise S4.

CHECKPOINT-1 remains a human-review gate. Machine recommendations are
guidance only and must never be treated as `manual_decision`.

## Record-level human fields

Permitted human decision fields:

- `manual_decision`: blank / `keep` / `drop` / `edit`
- `manual_sequence_corrected`
- `manual_molecule_type_override`: blank / `RNA` / `ssDNA`
- `manual_chemistry_override`: blank or a canonical chemistry vocabulary value
- `manual_trim_action`: blank / `approve` / `override` / `reject` / `defer`
- `manual_trim_5p_nt` / `manual_trim_3p_nt`
- `manual_notes`

Do not populate `manual_target_corrected`, canonical `pubmed_id`,
`target_name_raw`, or other S4 fields at this checkpoint.

Laura has entered the 169 judgement-required decisions. The 122 audit-only
rows keep blank `manual_decision` and are resolved by bulk confirmation.
CHECKPOINT-1 remains open and unapplied.

## Recommendation fields

Separate from human fields:

- `review_recommendation` / `review_rationale` / `recommended_*`
- `audit_only_row` / `bulk_audit_eligible`

Audit-only rows (length-boundary and random-kept) use
`review_recommendation=keep_current_route`.

Fine-grained decision-support recommendations live in ignored files under
`data/interim/checkpoints/aptamerbase_cp1/manual_review/audit/`. They do not
collapse physical records.

## Bulk audit confirmation

`aptamerbase_checkpoint1_bulk_audit_confirmation.csv` follows the AptaDB /
AptaIndex convention:

- `confirmation_id=audit_only_keep_current_route`
- `confirm=true` after Laura confirmed the audit-only cohort
- eligible IDs are the frozen length-boundary and/or random-kept rows only

The validator remains fail-closed while:

- any judgement-required `manual_decision` is blank; or
- audit-only rows are unconfirmed.

Bulk confirmation does not write 122 individual `manual_decision` values.

## Decision-support vocabularies (machine only)

Notation:

- `likely_true_degenerate_or_ambiguous_sequence`
- `likely_alignment_notation_recoverable_if_source_confirmed`
- `likely_modification_or_display_notation_recoverable`
- `malformed_or_unrecoverable`
- `chemistry_and_sequence_both_require_review`
- `needs_publication_source_review`

RDF DNA × U:

- `confirm_rdf_dna_keep_ssdna_park`
- `override_molecule_to_RNA`
- `needs_publication_source_review`

Unresolved molecule:

- `recommend_RNA_from_source_evidence`
- `recommend_ssDNA_from_source_evidence`
- `remain_unresolved_park`
- `needs_publication_source_review`

Chemistry evidence:

- `source_supports_2NH2_RNA`
- `source_supports_2OMe_RNA`
- `source_supports_mixed_chemistry`
- `terminal_or_post_selection_modification_only`
- `Spiegelmer_L_RNA`
- `modified_DNA_like`
- `chemistry_unresolved`
- `needs_publication_source_review`

Known-motif simulation (unapplied):

- `approve_existing_known_motif`
- `reject_trim_keep_full`
- `needs_source_review`
- `cannot_resolve_due_other_blocker`

Freebase-ID grouping is decision support only. It does not change
`record_id`, does not deduplicate, and is not a new biological corpus grain.

PMID-like label prefixes are `audit_only_bibliographic_hint` values only.

## AptamerBase-specific reviewed chemistry eligibility

Pre-review S3 accepted RNA/2F-RNA only. After CHECKPOINT-1 review, AptamerBase
S3/apply treats reviewed `2NH2-RNA`, `2OMe-RNA`, and `mixed` as technically
eligible RNA chemistries for this source only. Reviewed `unknown` remains a
chemistry-review park and is not inferred back to RNA.

## Status

AptamerBase CHECKPOINT-1 human review is entered. CHECKPOINT-1 remains open
and unapplied. S4 has not begun. No AptamerBase record is authorised for
global S4.
