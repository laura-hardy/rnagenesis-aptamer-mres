"""AptaDiff CHECKPOINT-1 structured review: schema, validation, and apply.

Shared A/B helpers. Outputs remain source-specific. Confirming the current
technical rejection uses ``manual_decision=keep`` so ``ambiguous_bases`` is
preserved. Does not authorise S4.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.aptadiff import APTADIFF_SOURCE_KEYS
from adapters.aptadiff_s3 import (
    DECISION_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from adapters.aptadb_checkpoint1_review import AppliedRecordResult, _corpus_only
from common.corpus_schema import S3_FORBIDDEN_FIELDS

ALLOWED_MANUAL_DECISIONS: Final[frozenset[str]] = frozenset({"", "keep", "drop", "edit"})
CONFIRM_CURRENT_DECISION: Final[str] = "keep"
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
CONFIRM_CURRENT_NOTE: Final[str] = (
    "Confirm rejection: authoritative source sequence contains unresolved "
    "IUPAC N; no source-supported deterministic repair."
)
CHECKPOINT_STATUS_REJECTED: Final[str] = "rejected_after_checkpoint1"
CHECKPOINT_STATUS_PARKED: Final[str] = "parked_after_checkpoint1"
CHECKPOINT_STATUS_APPROVED: Final[str] = "approved_for_s4"
DEFAULT_RECOMMENDATIONS_REL: Final[dict[str, str]] = {
    "aptadiff_a": "config/checkpoint_reviews/aptadiff_a_checkpoint1_recommendations.json",
    "aptadiff_b": "config/checkpoint_reviews/aptadiff_b_checkpoint1_recommendations.json",
}

MANUAL_FIELDS: Final[tuple[str, ...]] = (
    "manual_decision",
    "manual_sequence_corrected",
    "manual_target_corrected",
    "manual_molecule_type_override",
    "manual_chemistry_override",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_trim_group_override",
    "manual_notes",
)
PERMITTED_REVIEW_DRIFT_FIELDS: Final[frozenset[str]] = frozenset(MANUAL_FIELDS)

RECOMMENDATION_FIELDS: Final[tuple[str, ...]] = (
    "review_recommendation",
    "review_rationale",
    "requires_specific_human_decision",
    "recommended_manual_decision",
    "recommended_sequence_correction_op",
    "recommended_sequence_corrected",
    "recommended_molecule_type_override",
    "recommended_chemistry_override",
    "recommended_trim_action",
    "recommended_trim_5p_nt",
    "recommended_trim_3p_nt",
    "recommended_trim_group_override",
    "audit_only_row",
    "bulk_audit_eligible",
)

GROUP_REVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "constant_group_id",
    "group_label",
    "n_records",
    "n_review_records",
    "associated_record_ids",
    "review_recommendation",
    "review_rationale",
    "requires_specific_human_decision",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_notes",
)

BULK_CONFIRMATION_COLUMNS: Final[tuple[str, ...]] = (
    "confirmation_id",
    "scope",
    "eligible_record_count",
    "eligible_record_ids",
    "confirm",
    "reviewer_initials",
    "manual_notes",
)

BULK_CONFIRMATION_ID: Final[str] = "audit_only_keep_current_route"
BULK_SCOPE: Final[str] = "length_boundary_and_or_random_kept_audit_only"

AMBIGUOUS_N_RECOMMENDATION: Final[str] = "confirm_current_reject"
AMBIGUOUS_N_RATIONALE: Final[str] = (
    "unresolved IUPAC N in the authoritative 36-nt source sequence; "
    "no source-supported deterministic repair available."
)


class AptaDiffCheckpoint1ReviewError(ValueError):
    """Invalid AptaDiff CHECKPOINT-1 review schema or prepared package."""


@dataclass
class ValidationReport:
    """Fail-closed CHECKPOINT-1 review validation (aggregates only)."""

    total_review_records: int = 0
    unresolved_manual_decisions: int = 0
    unresolved_constant_groups: int = 0
    unresolved_exceptions: int = 0
    judgement_required_rows: int = 0
    unresolved_judgement_required: int = 0
    audit_only_rows: int = 0
    audit_only_unconfirmed: int = 0
    bulk_audit_confirmed: bool = False
    ready_for_application: int = 0
    blocking_issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocking_issues and self.ready_for_application == (
            self.total_review_records
        )


def _blank(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_review_recommendations(path: str | Path, *, source_key: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_key") != source_key:
        raise AptaDiffCheckpoint1ReviewError(
            f"recommendation file source_key must be {source_key}"
        )
    if source_key not in APTADIFF_SOURCE_KEYS:
        raise AptaDiffCheckpoint1ReviewError(
            f"Unknown AptaDiff source_key={source_key!r}"
        )
    return payload


def populate_record_recommendations(
    row: dict[str, str],
    *,
    recommendations: Mapping[str, Any],
) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    out = dict(row)
    for name in RECOMMENDATION_FIELDS:
        out.setdefault(name, "")
    for name in MANUAL_FIELDS:
        out[name] = ""

    record_id = out.get("record_id", "")
    record_cfg = (recommendations.get("records") or {}).get(record_id, {})
    by_reason = (recommendations.get("default_by_primary_reason") or {}).get(
        out.get("primary_reason", ""), {}
    )
    cfg: dict[str, Any] = {}
    if record_cfg:
        cfg.update(record_cfg)
    elif by_reason:
        cfg.update(by_reason)
    elif out.get("primary_reason") == "ambiguous_bases":
        cfg = {
            "review_recommendation": AMBIGUOUS_N_RECOMMENDATION,
            "rationale": AMBIGUOUS_N_RATIONALE,
            "requires_specific_human_decision": True,
            "recommended_manual_decision": "",
            "sequence_correction_op": "",
        }

    if cfg:
        out["review_recommendation"] = _blank(cfg.get("review_recommendation"))
        out["review_rationale"] = _blank(cfg.get("rationale"))
        out["requires_specific_human_decision"] = (
            "true" if cfg.get("requires_specific_human_decision") else "false"
        )
        out["recommended_manual_decision"] = _blank(
            cfg.get("recommended_manual_decision")
        )
        out["recommended_sequence_correction_op"] = _blank(
            cfg.get("sequence_correction_op")
        )
        out["recommended_sequence_corrected"] = ""
        out["recommended_molecule_type_override"] = ""
        out["recommended_chemistry_override"] = ""
        out["recommended_trim_action"] = ""
        out["recommended_trim_5p_nt"] = ""
        out["recommended_trim_3p_nt"] = ""
        out["recommended_trim_group_override"] = ""

    out["audit_only_row"] = "false"
    out["bulk_audit_eligible"] = "false"

    for name in MANUAL_FIELDS:
        if out.get(name):
            raise AptaDiffCheckpoint1ReviewError(
                f"Recommendations must not populate {name} for {record_id!r}"
            )
    return out


def build_bulk_confirmation_row(
    queue_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    eligible = sorted(
        row["record_id"]
        for row in queue_rows
        if _blank(row.get("audit_only_row")).lower() == "true"
        or _blank(row.get("bulk_audit_eligible")).lower() == "true"
    )
    return {
        "confirmation_id": BULK_CONFIRMATION_ID,
        "scope": BULK_SCOPE,
        "eligible_record_count": str(len(eligible)),
        "eligible_record_ids": "|".join(eligible),
        "confirm": "",
        "reviewer_initials": "",
        "manual_notes": "",
    }


def build_group_review_rows(
    queue_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """AptaDiff has no constant-region proposals; return an empty table."""
    del queue_rows
    return []


def validate_review_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None = None,
) -> ValidationReport:
    """Validate prepared or completed AptaDiff CHECKPOINT-1 review files.

    Blank ``manual_decision`` remains unresolved. Completed confirm-current
    rejection uses ``keep`` and must not invent nucleotide repairs. An empty
    random-kept audit pool with blank ``confirm`` is not an unresolved human
    decision.
    """
    report = ValidationReport(total_review_records=len(queue_rows))
    if group_rows:
        report.unresolved_constant_groups = len(group_rows)
        report.blocking_issues.append(
            "AptaDiff CHECKPOINT-1 must not contain constant-region group rows"
        )
    if bulk_confirmation is not None:
        confirm = _blank(bulk_confirmation.get("confirm")).lower()
        eligible_text = _blank(bulk_confirmation.get("eligible_record_count"))
        eligible_count = int(eligible_text) if eligible_text.isdigit() else 0
        eligible_ids = [
            part
            for part in _blank(
                bulk_confirmation.get("eligible_record_ids", "")
            ).split("|")
            if part
        ]
        if eligible_count != 0 or eligible_ids:
            report.blocking_issues.append(
                "AptaDiff has no random-kept audit pool; bulk eligible count "
                "must be 0 and eligible_record_ids must be empty"
            )
        if confirm == "true":
            report.blocking_issues.append(
                "Empty AptaDiff audit pool must not be bulk-confirmed"
            )
        elif confirm not in {"", "false"}:
            report.blocking_issues.append(
                "Invalid bulk confirmation value for empty AptaDiff audit pool"
            )
        if _blank(bulk_confirmation.get("reviewer_initials")):
            report.blocking_issues.append(
                "AptaDiff bulk confirmation must leave reviewer_initials blank"
            )
        report.bulk_audit_confirmed = False

    for row in queue_rows:
        record_id = row["record_id"]
        if _blank(row.get("audit_only_row")).lower() == "true" or _blank(
            row.get("bulk_audit_eligible")
        ).lower() == "true":
            report.blocking_issues.append(
                f"AptaDiff must not manufacture audit-only review rows: {record_id}"
            )
        report.judgement_required_rows += 1
        decision = _blank(row.get("manual_decision"))
        if decision not in ALLOWED_MANUAL_DECISIONS:
            report.blocking_issues.append(f"Invalid manual_decision for {record_id}")
            continue
        if decision == "":
            report.unresolved_manual_decisions += 1
            report.unresolved_judgement_required += 1
            report.blocking_issues.append(
                f"Unresolved manual_decision for {record_id}"
            )
            for name in MANUAL_FIELDS:
                if name == "manual_decision":
                    continue
                if _blank(row.get(name)):
                    report.blocking_issues.append(
                        f"Prepared package must leave {name} blank for {record_id}"
                    )
        elif decision == "edit":
            report.blocking_issues.append(
                f"AptaDiff CHECKPOINT-1 forbids edit/repair for {record_id}"
            )
        elif decision == "drop":
            report.blocking_issues.append(
                f"AptaDiff confirm-current reject must use keep so "
                f"ambiguous_bases is preserved: {record_id}"
            )
        elif decision != CONFIRM_CURRENT_DECISION:
            report.blocking_issues.append(
                f"Unsupported manual_decision {decision!r} for {record_id}"
            )
        else:
            if row.get("proposed_decision") != "proposed_reject":
                report.blocking_issues.append(
                    f"keep on non-reject AptaDiff row is not authorised: {record_id}"
                )
            if row.get("primary_reason") != "ambiguous_bases":
                report.blocking_issues.append(
                    f"keep must confirm ambiguous_bases for {record_id}"
                )
            if row.get("primary_route") != PRIMARY_ROUTE_REJECT:
                report.blocking_issues.append(
                    f"keep must remain on technical_reject for {record_id}"
                )
            for name in FORBIDDEN_CORRECTION_FIELDS:
                if _blank(row.get(name)):
                    report.blocking_issues.append(
                        f"Confirm-current reject must leave {name} blank for "
                        f"{record_id}"
                    )
        if row.get("primary_reason") == "ambiguous_bases":
            combined = (
                row.get("sequence_raw", "") + row.get("sequence_full", "")
            ).upper()
            if "N" not in combined:
                report.blocking_issues.append(
                    f"ambiguous_bases row missing N in source sequence: {record_id}"
                )
            if row.get("sequence_full") and "N" not in row.get(
                "sequence_full", ""
            ).upper():
                report.blocking_issues.append(
                    f"ambiguous_bases sequence must not be repaired: {record_id}"
                )
            if "U" in (row.get("sequence_full", "") + row.get("sequence_raw", "")).upper():
                report.blocking_issues.append(
                    f"AptaDiff sequence must not contain U: {record_id}"
                )

    if (
        not report.blocking_issues
        and report.unresolved_manual_decisions == 0
    ):
        report.ready_for_application = report.total_review_records
    else:
        report.ready_for_application = 0
    return report


def format_validation_markdown(report: ValidationReport) -> str:
    lines = [
        "# AptaDiff CHECKPOINT-1 validation",
        "",
        "## Totals",
        "",
        f"- total review records: `{report.total_review_records}`",
        f"- unresolved manual decisions: `{report.unresolved_manual_decisions}`",
        f"- judgement-required rows: `{report.judgement_required_rows}`",
        f"- unresolved judgement-required: `{report.unresolved_judgement_required}`",
        f"- audit-only rows: `{report.audit_only_rows}`",
        f"- ready for application: `{report.ready_for_application}`",
        "",
        "## Blocking issues",
        "",
    ]
    if report.blocking_issues:
        lines.append(f"- issue count: `{len(report.blocking_issues)}`")
        lines.append(
            "- unresolved human decisions are expected until CHECKPOINT-1 review"
        )
    else:
        lines.append("- none")
    status_lines = [
        "",
        "## Status",
        "",
        "CHECKPOINT-1 is not closed.",
    ]
    if report.ok:
        status_lines.extend(
            [
                "Human decisions are recorded and ready for application.",
                "S4 remains blocked.",
                "authorised_for_s4 remains 0.",
                "",
            ]
        )
    else:
        status_lines.extend(
            [
                "No human decisions have been applied.",
                "S4 remains blocked.",
                "authorised_for_s4 remains 0.",
                "",
            ]
        )
    lines.extend(status_lines)
    return "\n".join(lines)


def build_review_readme(source_key: str) -> str:
    label = "Dataset A" if source_key == "aptadiff_a" else "Dataset B"
    return f"""# AptaDiff {label} CHECKPOINT-1 human review

This package is a human-review gate. Machine recommendations are guidance
only. Do not treat `review_recommendation` as a completed `manual_decision`.

Permitted `manual_decision` values: `keep` / `drop` / `edit`.

The active queue contains only N-containing technical exceptions.
Ordinary clean ssDNA parks are not in this queue.

Machine recommendation for unresolved IUPAC N:

- `review_recommendation` = `confirm_current_reject`
- No source-supported nucleotide repair is available.
- Do not replace, infer, or delete N, and do not apply T→U.

Human `manual_*` fields must remain blank until Laura records a decision.

Do not authorise any AptaDiff record for global S4 from this package.
"""


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def record_confirm_current_reject(row: Mapping[str, str]) -> dict[str, str]:
    """Record Laura's confirm-current technical rejection on one review row."""
    out = dict(row)
    out["manual_decision"] = CONFIRM_CURRENT_DECISION
    for name in FORBIDDEN_CORRECTION_FIELDS:
        out[name] = ""
    out["manual_notes"] = CONFIRM_CURRENT_NOTE
    return out


def compare_review_to_pristine(
    reviewed_rows: Sequence[Mapping[str, str]],
    pristine_rows: Sequence[Mapping[str, str]],
) -> list[str]:
    """Return immutable-field drift; permitted human fields may differ."""
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


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def _int_len(value: str) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def checkpoint_status_for_route(route: str) -> str:
    if route == PRIMARY_ROUTE_REJECT:
        return CHECKPOINT_STATUS_REJECTED
    if route == PRIMARY_ROUTE_SSDNA:
        return CHECKPOINT_STATUS_PARKED
    if route == PRIMARY_ROUTE_ELIGIBLE:
        return CHECKPOINT_STATUS_APPROVED
    raise AptaDiffCheckpoint1ReviewError(f"Unknown primary_route {route!r}")


def apply_reviewed_record(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    decision_row: Mapping[str, str],
    rejection_row: Mapping[str, str] | None,
) -> AppliedRecordResult:
    """Confirm the current technical reject. Do not re-normalise or repair N."""
    record_id = canonical["record_id"]
    decision = _blank(review_row.get("manual_decision"))
    if decision != CONFIRM_CURRENT_DECISION:
        raise AptaDiffCheckpoint1ReviewError(
            f"Cannot apply unresolved or non-confirm decision for {record_id!r}"
        )
    for name in FORBIDDEN_CORRECTION_FIELDS:
        if _blank(review_row.get(name)):
            raise AptaDiffCheckpoint1ReviewError(
                f"Confirm-current reject must not populate {name} for {record_id!r}"
            )
    original_raw = canonical.get("sequence_raw", "")
    sequence_full = canonical.get("sequence_full", "")
    if "N" not in (original_raw + sequence_full).upper():
        raise AptaDiffCheckpoint1ReviewError(
            f"ambiguous_bases apply missing N for {record_id!r}"
        )
    if "U" in (original_raw + sequence_full).upper():
        raise AptaDiffCheckpoint1ReviewError(
            f"AptaDiff apply must not introduce U for {record_id!r}"
        )
    route_before = review_row.get("primary_route") or decision_row.get(
        "primary_route", ""
    )
    if route_before != PRIMARY_ROUTE_REJECT:
        raise AptaDiffCheckpoint1ReviewError(
            f"Confirm-current reject expected technical_reject for {record_id!r}"
        )
    primary_reason = review_row.get("primary_reason") or decision_row.get(
        "primary_reason", ""
    )
    if primary_reason != "ambiguous_bases":
        raise AptaDiffCheckpoint1ReviewError(
            f"Confirm-current reject must retain ambiguous_bases for {record_id!r}"
        )

    updated = _corpus_only(canonical)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""
    note_parts = [
        "checkpoint1_manual_decision=keep",
        "confirm_current_reject=true",
        "primary_reason=ambiguous_bases",
    ]
    if _blank(review_row.get("manual_notes")):
        note_parts.append("reviewer_notes_present=true")
    notes = "|".join(note_parts)
    updated["notes"] = notes

    applied_decision = _row(DECISION_COLUMNS, decision_row)
    applied_decision["notes"] = notes
    applied_decision["checkpoint_status"] = CHECKPOINT_STATUS_REJECTED
    applied_decision["primary_reason"] = "ambiguous_bases"
    applied_decision["primary_route"] = PRIMARY_ROUTE_REJECT
    applied_decision["proposed_decision"] = "proposed_reject"
    applied_decision["molecule_type"] = canonical.get("molecule_type", "")
    applied_decision["chemistry"] = canonical.get("chemistry", "")

    applied_rejection = None
    if rejection_row is not None:
        applied_rejection = _row(REJECTION_COLUMNS, rejection_row)
        applied_rejection["rejection_reason"] = "ambiguous_bases"
        if applied_rejection.get("sequence_raw", "") != original_raw:
            raise AptaDiffCheckpoint1ReviewError(
                f"Rejection sequence_raw drifted for {record_id!r}"
            )

    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=original_raw,
        sequence_full=sequence_full,
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
        primary_reason="ambiguous_bases",
        decision=applied_decision,
        rejection_row=applied_rejection,
        park_row=None,
        sequence_corrected=False,
        molecule_overridden=False,
    )


def apply_aptadiff_checkpoint1_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    decision_by_id: Mapping[str, Mapping[str, str]],
    rejection_by_id: Mapping[str, Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None = None,
) -> tuple[list[AppliedRecordResult], ValidationReport]:
    """Apply a fully resolved AptaDiff CHECKPOINT-1 package. Fail-closed."""
    report = validate_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
    )
    if not report.ok:
        raise AptaDiffCheckpoint1ReviewError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    applied: list[AppliedRecordResult] = []
    for row in queue_rows:
        record_id = row["record_id"]
        if record_id not in canonical_by_id:
            raise AptaDiffCheckpoint1ReviewError(
                f"Review record missing from canonical: {record_id!r}"
            )
        if record_id not in decision_by_id:
            raise AptaDiffCheckpoint1ReviewError(
                f"Review record missing from S3 decisions: {record_id!r}"
            )
        applied.append(
            apply_reviewed_record(
                canonical=canonical_by_id[record_id],
                review_row=row,
                decision_row=decision_by_id[record_id],
                rejection_row=rejection_by_id.get(record_id),
            )
        )
    return applied, report
