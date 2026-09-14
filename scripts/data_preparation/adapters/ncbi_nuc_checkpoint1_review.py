"""NCBI Nucleotide CHECKPOINT-1 structured review helpers.

Reuses the AptaDB structured-review field vocabulary and fail-closed
validation. Recommendations live in separate fields and must never
masquerade as human decisions. Apply lives in ``apply_reviewed_record``
/ ``apply_ncbi_nuc_checkpoint1_package`` and preserves the current S3
route on ``keep``. Does not start S4.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptadb_checkpoint1_review import (
    AppliedRecordResult,
    MANUAL_FIELDS,
    AptaDBCheckpoint1ReviewError,
    ValidationReport,
    _blank,
    _corpus_only,
    format_validation_markdown,
    materialize_bulk_audit_decisions,
    parse_review_reasons,
    populate_record_recommendations,
    validate_review_package as validate_aptadb_review_package,
)
from adapters.ncbi_nuc_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    REJECTION_COLUMNS,
    REJECTION_STAGE,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS
from common.eligibility import format_reasons

ALLOWED_MOLECULE_OVERRIDES: Final[frozenset[str]] = frozenset({"", "RNA", "DNA"})
CONFIRM_CURRENT_DECISION: Final[str] = "keep"
MANUAL_REJECT_REASON: Final[str] = "manual_reject"
FORBIDDEN_CORRECTION_FIELDS: Final[tuple[str, ...]] = (
    "manual_sequence_corrected",
    "manual_target_corrected",
    "manual_molecule_type_override",
    "manual_chemistry_override",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_trim_group_override",
)
CHECKPOINT_STATUS_REJECTED: Final[str] = "rejected_after_checkpoint1"
CHECKPOINT_STATUS_PARKED: Final[str] = "parked_after_checkpoint1"
CHECKPOINT_STATUS_APPROVED: Final[str] = "approved_for_s4"
PERMITTED_REVIEW_DRIFT_FIELDS: Final[frozenset[str]] = frozenset(MANUAL_FIELDS)
DEFAULT_RECOMMENDATIONS_REL: Final[str] = (
    "config/checkpoint_reviews/ncbi_nuc_checkpoint1_recommendations.json"
)
DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/ncbi_nuc.json"

REASON_TO_RECOMMENDATION_KEY: Final[Mapping[str, str]] = {
    "judgement_dependent_technical": "primer_like",
    "molecule_type_unresolved": "molecule_type_unresolved",
    "construct_source_object": "construct_source_object",
}


class NcbiNucCheckpoint1ReviewError(ValueError):
    """Invalid NCBI Nucleotide CHECKPOINT-1 review schema or prepare input."""


def load_review_recommendations(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_key") != "ncbi_nuc":
        raise NcbiNucCheckpoint1ReviewError(
            "recommendation file source_key must be ncbi_nuc"
        )
    return payload


def populate_ncbi_nuc_recommendations(
    row: dict[str, str],
    *,
    recommendations: Mapping[str, Any],
) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    try:
        out = populate_record_recommendations(row, recommendations=recommendations)
    except AptaDBCheckpoint1ReviewError as exc:
        raise NcbiNucCheckpoint1ReviewError(str(exc)) from exc

    if out.get("review_recommendation"):
        for name in MANUAL_FIELDS:
            out[name] = ""
        return out

    reasons = parse_review_reasons(out.get("checkpoint_review_reasons", ""))
    primary = _blank(out.get("primary_reason"))
    cfg: Mapping[str, Any] = {}
    if primary == "primer_like":
        cfg = recommendations.get("primer_like") or {}
    elif primary == "non_aptamer_source_object":
        cfg = recommendations.get("non_aptamer_source_object") or {}
    elif primary == "molecule_type_unresolved":
        cfg = recommendations.get("molecule_type_unresolved") or {}
    else:
        for token in (
            "judgement_dependent_technical",
            "molecule_type_unresolved",
            "construct_source_object",
        ):
            if token in reasons:
                key = REASON_TO_RECOMMENDATION_KEY[token]
                cfg = recommendations.get(key) or {}
                break
    if cfg:
        out["review_recommendation"] = _blank(cfg.get("review_recommendation"))
        out["review_rationale"] = _blank(cfg.get("rationale"))
        out["requires_specific_human_decision"] = (
            "true" if cfg.get("requires_specific_human_decision") else "false"
        )
        out["recommended_manual_decision"] = _blank(
            cfg.get("recommended_manual_decision")
        )
        out["recommended_molecule_type_override"] = ""
        out["recommended_chemistry_override"] = ""
        out["recommended_trim_action"] = ""
        out["recommended_trim_5p_nt"] = ""
        out["recommended_trim_3p_nt"] = ""
        out["recommended_sequence_corrected"] = ""
        out["recommended_sequence_correction_op"] = ""
    for name in MANUAL_FIELDS:
        out[name] = ""
    return out


def validate_ncbi_nuc_review_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None = None,
    allow_deferred: bool = False,
) -> ValidationReport:
    """Fail-closed validation. Human fields must be filled before closure."""
    try:
        report = validate_aptadb_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk_confirmation,
            allow_deferred=allow_deferred,
            allowed_molecule_overrides=ALLOWED_MOLECULE_OVERRIDES,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise NcbiNucCheckpoint1ReviewError(str(exc)) from exc
    for row in queue_rows:
        record_id = row["record_id"]
        decision = _blank(row.get("manual_decision"))
        if decision == "edit":
            report.blocking_issues.append(
                f"ncbi_nuc CHECKPOINT-1 apply does not consume edit for {record_id}"
            )
        if decision in {CONFIRM_CURRENT_DECISION, "drop"}:
            for name in FORBIDDEN_CORRECTION_FIELDS:
                if _blank(row.get(name)):
                    report.blocking_issues.append(
                        f"{decision} must not populate {name} for {record_id}"
                    )
    if report.blocking_issues:
        report.ready_for_application = 0
    return report


def build_review_readme() -> str:
    return """# NCBI Nucleotide CHECKPOINT-1 human review

This package is a human-review gate. Machine recommendations are guidance
only. Do not treat `review_recommendation` as a completed `manual_decision`.

NCBI sequences stay local under `data/`. Do not copy real sequences into
tracked docs, commits, or chat.

## What S3 already did automatically

- Five approved RNA records that pass ordinary 20-100 nt technical rules
  remain proposed accepts. Unknown construct scope alone did not block them.
- Primer objects (`primer_like`) and non-aptamer source objects
  (`non_aptamer_source_object`) are proposed rejects with active review.
- Unresolved `molecule_type=unknown` records are parked, not rejected, with
  active molecule/construct review. Length and ambiguous-base conditions are
  secondary.
- No trim was applied. `sequence_core` equals `sequence_full`.
- Alphabet classification, including A-only RNA-alphabet artefacts, did not
  resolve molecule type.
- Target extraction, evidence, leakage, and NCBI-ENA deduplication were
  not performed. `target_name_raw` remains empty.

## What requires human judgement

Fill `manual_decision` for every judgement-required row.

Permitted `manual_decision` values: `keep` / `drop` / `edit`.

Permitted molecule overrides: `RNA` / `DNA` (not inferred from alphabet).

Permitted `manual_trim_action` values: `approve` / `override` / `reject` /
`defer`. Do not invent an aptamer core. Numeric trim is only for a later
source-supported boundary, not a guessed core.

### Batch 01 — judgement-dependent source objects

Primers, reverse primers, poly-A fragments, and method/non-aptamer DNA
objects. Confirm or override the proposed rejection. Do not repair.

### Batch 02 — unresolved molecule identity

Including cDNA and transcription-template parks. Resolve molecule/chemistry
from source evidence. Do not copy ENA decisions. Do not transcribe.

Ambiguous `N` remains unrepaired. Even if molecule identity were later
resolved as RNA, unresolved N would still block ordinary technical
acceptance unless a source-supported repair exists.

### Batch 03 — construct or unexpected known-motif

Only if a construct/core issue or unexpected motif is not already covered
by batches 01-02.

### Batch 04 — length-boundary audit

Otherwise-kept 20-25 nt and 90-100 nt proposed accepts. Audit only.

### Batch 05 — random kept audit

Deterministic sample of technically eligible RNA (seed 42, requested 30).
If the clean pool is smaller than 30, the sample is the entire pool and
the shortfall is reported. Rows are not fabricated.

## Bulk audit confirmation (blank)

Audit-only length-boundary and random-kept rows may later be confirmed
together by setting `confirm=true` in
`ncbi_nuc_checkpoint1_bulk_audit_confirmation.csv`. Do not populate `confirm`
now. The validator remains fail-closed until judgement-required
`manual_decision` values are filled and audit-only rows are confirmed.

## What is deferred

- `target_name_raw` stays empty. Do not extract DEFINITION/COMMENT targets.
- Evidence, affinity, leakage, NCBI-ENA deduplication, clustering, and
  global S4 were not run.

CHECKPOINT-1 authorisation means only technical sequence/molecule/
source-object eligibility to enter later global S4.

## How to fill the form

1. Inspect the sequence-bearing queue.
2. Enter `manual_decision` (`keep` / `drop` / `edit`).
3. For molecule conflicts, use `manual_molecule_type_override` /
   `manual_chemistry_override` only when authorising a reviewed change.
4. Leave machine `review_recommendation*` columns unchanged.
"""


def format_ncbi_nuc_validation_markdown(report: ValidationReport) -> str:
    return format_validation_markdown(report, source_label="NCBI Nucleotide")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def _int_len(value: str) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def checkpoint_status_for_route(route: str) -> str:
    if route == PRIMARY_ROUTE_REJECT:
        return CHECKPOINT_STATUS_REJECTED
    if route == PRIMARY_ROUTE_MOLECULE:
        return CHECKPOINT_STATUS_PARKED
    if route == PRIMARY_ROUTE_ELIGIBLE:
        return CHECKPOINT_STATUS_APPROVED
    raise NcbiNucCheckpoint1ReviewError(f"Unknown primary_route {route!r}")


def compare_review_to_pristine(
    reviewed_rows: Sequence[Mapping[str, str]],
    pristine_rows: Sequence[Mapping[str, str]],
) -> list[str]:
    """Return immutable-field drift; permitted human decision fields may differ."""
    if len(reviewed_rows) != len(pristine_rows):
        return [
            "Active review row count differs from pristine baseline: "
            f"{len(reviewed_rows)} vs {len(pristine_rows)}"
        ]
    reviewed_ids = [row["record_id"] for row in reviewed_rows]
    pristine_ids = [row["record_id"] for row in pristine_rows]
    if reviewed_ids != pristine_ids:
        return ["Review order or record_id membership differs from pristine baseline"]
    mismatches: list[str] = []
    for reviewed, pristine in zip(reviewed_rows, pristine_rows, strict=True):
        record_id = reviewed["record_id"]
        for field_name, reviewed_value in reviewed.items():
            if field_name in PERMITTED_REVIEW_DRIFT_FIELDS:
                continue
            if reviewed_value != pristine.get(field_name, ""):
                mismatches.append(f"{record_id}:{field_name}")
                if len(mismatches) >= 20:
                    return mismatches
    return mismatches


def _working_queue_rows(
    queue_rows: Sequence[Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None,
) -> list[dict[str, str]]:
    """Materialise bulk-confirmed audit-only keep in memory only."""
    if bulk_confirmation is None:
        return [dict(row) for row in queue_rows]
    if _blank(bulk_confirmation.get("confirm")).lower() != "true":
        return [dict(row) for row in queue_rows]
    try:
        return materialize_bulk_audit_decisions(queue_rows, bulk_confirmation)
    except AptaDBCheckpoint1ReviewError as exc:
        raise NcbiNucCheckpoint1ReviewError(str(exc)) from exc


def apply_reviewed_record(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    decision_row: Mapping[str, str],
    rejection_row: Mapping[str, str] | None = None,
    park_row: Mapping[str, str] | None = None,
) -> AppliedRecordResult:
    """Apply one NCBI Nucleotide review decision.

    ``keep`` preserves the pre-review S3 route. It does not force
    technical acceptance, re-normalise, reclassify, or reread GenBank.
    """
    record_id = canonical["record_id"]
    original_raw = canonical.get("sequence_raw", "")
    route_before = review_row.get("primary_route") or decision_row.get(
        "primary_route", ""
    )
    if route_before != decision_row.get("primary_route", ""):
        raise NcbiNucCheckpoint1ReviewError(
            f"Review/S3 primary_route mismatch for {record_id!r}"
        )
    decision = _blank(review_row.get("manual_decision"))
    if decision not in {"keep", "drop", "edit"}:
        raise NcbiNucCheckpoint1ReviewError(
            f"Cannot apply unresolved manual_decision for {record_id!r}"
        )
    if decision == "edit":
        raise NcbiNucCheckpoint1ReviewError(
            f"ncbi_nuc CHECKPOINT-1 apply does not consume edit for {record_id!r}"
        )
    if decision == "drop":
        return _apply_drop(
            canonical=canonical,
            review_row=review_row,
            decision_row=decision_row,
            route_before=route_before,
        )
    return _apply_keep(
        canonical=canonical,
        review_row=review_row,
        decision_row=decision_row,
        rejection_row=rejection_row,
        park_row=park_row,
        route_before=route_before,
        original_raw=original_raw,
    )


def _apply_keep(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    decision_row: Mapping[str, str],
    rejection_row: Mapping[str, str] | None,
    park_row: Mapping[str, str] | None,
    route_before: str,
    original_raw: str,
) -> AppliedRecordResult:
    record_id = canonical["record_id"]
    for name in FORBIDDEN_CORRECTION_FIELDS:
        if _blank(review_row.get(name)):
            raise NcbiNucCheckpoint1ReviewError(
                f"keep must not populate {name} for {record_id!r}"
            )
    if canonical.get("sequence_full") != canonical.get("sequence_core"):
        raise NcbiNucCheckpoint1ReviewError(
            f"keep must not apply a trim for {record_id!r}"
        )
    updated = _corpus_only(canonical)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""
    note_parts = ["checkpoint1_manual_decision=keep"]
    if _blank(review_row.get("audit_only_row")).lower() == "true":
        note_parts.append("keep_current_route=true")
    if review_row.get("manual_notes"):
        note_parts.append("reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={route_before}")
    notes = "|".join(part for part in note_parts if part)
    updated["notes"] = notes

    applied_decision = _row(DECISION_COLUMNS, decision_row)
    applied_decision["notes"] = notes
    applied_decision["checkpoint_status"] = checkpoint_status_for_route(route_before)
    applied_decision["primary_route"] = route_before
    applied_decision["molecule_type"] = canonical.get("molecule_type", "")
    applied_decision["chemistry"] = canonical.get("chemistry", "")
    applied_decision["sequence_length_full"] = canonical.get(
        "sequence_length_full", ""
    )
    applied_decision["sequence_length_core"] = canonical.get(
        "sequence_length_core", ""
    )

    applied_rejection = None
    applied_park = None
    if route_before == PRIMARY_ROUTE_REJECT:
        if rejection_row is None:
            raise NcbiNucCheckpoint1ReviewError(
                f"technical_reject missing rejection row for {record_id!r}"
            )
        applied_rejection = _row(REJECTION_COLUMNS, rejection_row)
        if applied_rejection.get("sequence_raw", "") != original_raw:
            raise NcbiNucCheckpoint1ReviewError(
                f"Rejection sequence_raw drifted for {record_id!r}"
            )
        applied_rejection["rejection_reason"] = decision_row.get(
            "primary_reason", ""
        )
    elif route_before == PRIMARY_ROUTE_MOLECULE:
        source_park = park_row or {
            **applied_decision,
            "park_reason": decision_row.get("primary_reason", "molecule_type_unresolved"),
        }
        applied_park = _row(PARK_COLUMNS, source_park)
        applied_park["park_reason"] = decision_row.get(
            "primary_reason", "molecule_type_unresolved"
        )
        applied_park["secondary_reasons"] = decision_row.get("secondary_reasons", "")
        applied_park["qc_flags"] = canonical.get("qc_flags", "") or decision_row.get(
            "qc_flags", ""
        )
        applied_park["molecule_type"] = canonical.get("molecule_type", "")
        applied_park["chemistry"] = canonical.get("chemistry", "")
    elif route_before != PRIMARY_ROUTE_ELIGIBLE:
        raise NcbiNucCheckpoint1ReviewError(
            f"Unsupported keep route {route_before!r} for {record_id!r}"
        )

    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=original_raw,
        sequence_full=canonical.get("sequence_full", ""),
        sequence_core=canonical.get("sequence_core", ""),
        sequence_length_full=_int_len(canonical.get("sequence_length_full", "")),
        sequence_length_core=_int_len(canonical.get("sequence_length_core", "")),
        molecule_type=canonical.get("molecule_type", ""),
        chemistry=canonical.get("chemistry", ""),
        alphabet_as_reported=canonical.get("alphabet_as_reported", ""),
        t_to_u_applied=canonical.get("t_to_u_applied", "") == "true",
        trim_status=canonical.get("trim_status", ""),
        trim_confidence=canonical.get("trim_confidence", ""),
        primary_route_before=route_before,
        primary_route_after=route_before,
        notes=notes,
        canonical=updated,
        proposed_decision=decision_row.get("proposed_decision", ""),
        primary_reason=decision_row.get("primary_reason", ""),
        decision=applied_decision,
        rejection_row=applied_rejection,
        park_row=applied_park,
        sequence_corrected=False,
        molecule_overridden=False,
    )


def _apply_drop(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    decision_row: Mapping[str, str],
    route_before: str,
) -> AppliedRecordResult:
    record_id = canonical["record_id"]
    for name in FORBIDDEN_CORRECTION_FIELDS:
        if _blank(review_row.get(name)):
            raise NcbiNucCheckpoint1ReviewError(
                f"drop must not populate {name} for {record_id!r}"
            )
    original_reason = decision_row.get("primary_reason", "")
    updated = _corpus_only(canonical)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""
    note_parts = [
        "checkpoint1_manual_decision=drop",
        "human_reviewed_exclusion=true",
    ]
    if original_reason:
        note_parts.append(f"original_primary_reason={original_reason}")
    if review_row.get("manual_notes"):
        note_parts.append("reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={PRIMARY_ROUTE_REJECT}")
    notes = "|".join(part for part in note_parts if part)
    updated["notes"] = notes
    applied_decision = _row(DECISION_COLUMNS, decision_row)
    applied_decision["proposed_decision"] = "proposed_reject"
    applied_decision["primary_reason"] = MANUAL_REJECT_REASON
    applied_decision["secondary_reasons"] = format_reasons(
        part for part in (original_reason, decision_row.get("secondary_reasons", "")) if part
    )
    applied_decision["primary_route"] = PRIMARY_ROUTE_REJECT
    applied_decision["checkpoint_status"] = CHECKPOINT_STATUS_REJECTED
    applied_decision["notes"] = notes
    rejection_row = {
        "record_id": record_id,
        "source_db": canonical.get("source_db", "ncbi_nuc"),
        "source_dataset": canonical.get("source_dataset", ""),
        "native_id": canonical.get("native_id", ""),
        "sequence_raw": canonical.get("sequence_raw", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "stage": REJECTION_STAGE,
        "rejection_reason": MANUAL_REJECT_REASON,
        "rejection_detail": notes,
    }
    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=canonical.get("sequence_raw", ""),
        sequence_full=canonical.get("sequence_full", ""),
        sequence_core=canonical.get("sequence_core", ""),
        sequence_length_full=_int_len(canonical.get("sequence_length_full", "")),
        sequence_length_core=_int_len(canonical.get("sequence_length_core", "")),
        molecule_type=canonical.get("molecule_type", ""),
        chemistry=canonical.get("chemistry", ""),
        alphabet_as_reported=canonical.get("alphabet_as_reported", ""),
        t_to_u_applied=canonical.get("t_to_u_applied", "") == "true",
        trim_status=canonical.get("trim_status", ""),
        trim_confidence=canonical.get("trim_confidence", ""),
        primary_route_before=route_before,
        primary_route_after=PRIMARY_ROUTE_REJECT,
        notes=notes,
        canonical=updated,
        proposed_decision="proposed_reject",
        primary_reason=MANUAL_REJECT_REASON,
        decision=applied_decision,
        rejection_row=_row(REJECTION_COLUMNS, rejection_row),
        park_row=None,
        sequence_corrected=False,
        molecule_overridden=False,
    )


def apply_ncbi_nuc_checkpoint1_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    decision_by_id: Mapping[str, Mapping[str, str]],
    rejection_by_id: Mapping[str, Mapping[str, str]],
    park_by_id: Mapping[str, Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None = None,
) -> tuple[list[AppliedRecordResult], ValidationReport]:
    """Apply a fully resolved NCBI CHECKPOINT-1 package. Fail-closed."""
    report = validate_ncbi_nuc_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
    )
    if not report.ok:
        raise NcbiNucCheckpoint1ReviewError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    working_rows = _working_queue_rows(queue_rows, bulk_confirmation)
    applied: list[AppliedRecordResult] = []
    for row in working_rows:
        record_id = row["record_id"]
        if record_id not in canonical_by_id:
            raise NcbiNucCheckpoint1ReviewError(
                f"Review record missing from canonical: {record_id!r}"
            )
        if record_id not in decision_by_id:
            raise NcbiNucCheckpoint1ReviewError(
                f"Review record missing from S3 decisions: {record_id!r}"
            )
        applied.append(
            apply_reviewed_record(
                canonical=canonical_by_id[record_id],
                review_row=row,
                decision_row=decision_by_id[record_id],
                rejection_row=rejection_by_id.get(record_id),
                park_row=park_by_id.get(record_id),
            )
        )
    return applied, report
