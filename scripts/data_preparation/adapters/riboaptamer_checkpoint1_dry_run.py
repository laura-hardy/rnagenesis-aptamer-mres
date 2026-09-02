"""RiboAptamer CHECKPOINT-1 application dry-run and in-memory merge.

Uses the same ``apply_riboaptamer_checkpoint1_package`` transformation as the
real apply. Dry-run writes nothing that the pipeline treats as a closed
checkpoint or S4 handoff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from adapters.aptadb_checkpoint1_review import AppliedRecordResult, _corpus_only
from adapters.riboaptamer_checkpoint1_review import (
    RiboAptamerCheckpoint1ReviewError,
    apply_riboaptamer_checkpoint1_package,
    parse_cp1_constant_flag,
)
from adapters.riboaptamer_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS
from common.eligibility import EligibilityPolicy

DRY_RUN_BANNER = (
    "DRY-RUN PREVIEW. NOT AUTHORITATIVE. CHECKPOINT-1 IS NOT APPLIED. "
    "S4 REMAINS BLOCKED."
)

CHANGE_REPORT_COLUMNS: tuple[str, ...] = (
    "record_id",
    "pre_review_route",
    "post_review_route",
    "manual_decision",
    "sequence_corrected",
    "molecule_overridden",
    "pre_chemistry",
    "post_chemistry",
    "trim_action",
    "trim_5p_nt",
    "trim_3p_nt",
    "trim_source",
    "pre_core_length",
    "post_core_length",
    "route_changed",
    "rejection_reason_before",
    "rejection_reason_after",
    "constant_flag",
    "cause",
)

ELIGIBLE_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "proposed_decision",
    "primary_reason",
    "primary_route",
    "molecule_type",
    "chemistry",
    "sequence_length_full",
    "sequence_length_core",
    "trim_status",
    "trim_confidence",
)

DECISION_AUDIT_COLUMNS: tuple[str, ...] = (
    "record_id",
    "manual_decision",
    "manual_trim_action",
    "consumed",
    "notes_survived",
    "applied_trim_5p_nt",
    "applied_trim_3p_nt",
    "constant_flag",
    "pre_review_route",
    "post_review_route",
)


@dataclass
class RiboAptamerDryRunSimulation:
    """In-memory post-review RiboAptamer corpus (no S4 fields)."""

    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked_ssdna: list[dict[str, str]]
    preview_eligible: list[dict[str, str]]
    change_report: list[dict[str, str]]
    decision_audit: list[dict[str, str]]
    applied: list[AppliedRecordResult]
    route_changed_ids: tuple[str, ...] = ()
    stats: dict[str, int | str | bool] = field(default_factory=dict)


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def _int_len(value: str) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def simulate_riboaptamer_checkpoint1_application(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
    decision_rows: Sequence[Mapping[str, str]],
    source_metadata_by_id: Mapping[str, Mapping[str, str]],
    s2_qc_by_id: Mapping[str, Mapping[str, str]],
    policy: EligibilityPolicy,
    proposals_by_record: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    bulk_confirmation: Mapping[str, str] | None = None,
    existing_rejection_rows: Sequence[Mapping[str, str]] = (),
    existing_parked_ssdna: Sequence[Mapping[str, str]] = (),
    expected_source_rows: int | None = 509,
) -> RiboAptamerDryRunSimulation:
    """Apply reviewed records in memory and merge onto the full 509-row set."""
    if len(canonical_rows) != len(decision_rows):
        raise RiboAptamerCheckpoint1ReviewError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_source_rows is not None and len(canonical_rows) != expected_source_rows:
        raise RiboAptamerCheckpoint1ReviewError(
            f"Canonical must have {expected_source_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise RiboAptamerCheckpoint1ReviewError("Duplicate canonical record_id")
    existing_rejections = {
        row["record_id"]: dict(row) for row in existing_rejection_rows
    }
    parked_ssdna_by_id = {row["record_id"]: dict(row) for row in existing_parked_ssdna}

    applied, _report = apply_riboaptamer_checkpoint1_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        canonical_by_id=canonical_by_id,
        source_metadata_by_id=source_metadata_by_id,
        s2_qc_by_id=s2_qc_by_id,
        policy=policy,
        proposals_by_record=proposals_by_record,
        bulk_confirmation=bulk_confirmation,
    )
    applied_by_id = {item.record_id: item for item in applied}
    if len(applied_by_id) != len(queue_rows):
        raise RiboAptamerCheckpoint1ReviewError(
            "Not every CHECKPOINT-1 review row was consumed"
        )

    preview_canonical: list[dict[str, str]] = []
    preview_decisions: list[dict[str, str]] = []
    preview_rejections: list[dict[str, str]] = []
    preview_parked_ssdna: list[dict[str, str]] = []
    preview_eligible: list[dict[str, str]] = []
    change_report: list[dict[str, str]] = []
    decision_audit: list[dict[str, str]] = []
    route_changed: list[str] = []
    human_drops = 0
    n_trimmed = 0
    n_core_changed = 0
    strong_flags = 0
    weak_flags = 0
    review_by_id = {row["record_id"]: row for row in queue_rows}

    for original_canonical, original_decision in zip(
        canonical_rows, decision_rows, strict=True
    ):
        record_id = original_canonical["record_id"]
        original_raw = original_canonical["sequence_raw"]
        applied_row = applied_by_id.get(record_id)
        if applied_row is None:
            canonical = _corpus_only(original_canonical)
            decision = _row(DECISION_COLUMNS, original_decision)
            rejection = existing_rejections.get(record_id)
            park = parked_ssdna_by_id.get(record_id)
            route = decision["primary_route"]
        else:
            canonical = _corpus_only(applied_row.canonical)
            if canonical["sequence_raw"] != original_raw:
                raise RiboAptamerCheckpoint1ReviewError(
                    f"Apply mutated sequence_raw for {record_id!r}"
                )
            review = review_by_id[record_id]
            constant_flag = parse_cp1_constant_flag(review.get("manual_notes", ""))
            if constant_flag == "constants_suspected_unresolved":
                strong_flags += 1
            elif constant_flag == "possible_constants_unresolved":
                weak_flags += 1
            if applied_row.primary_route_after != applied_row.primary_route_before:
                route_changed.append(record_id)
            if applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt:
                n_trimmed += 1
            if _int_len(canonical["sequence_length_core"]) != _int_len(
                original_canonical.get("sequence_length_core", "")
            ):
                n_core_changed += 1
            notes_survived = "true"
            if review.get("manual_notes") and (
                "checkpoint1_reviewer_notes=" not in (applied_row.notes or "")
            ):
                notes_survived = "false"
            if review.get("manual_decision") == "drop":
                human_drops += 1
                decision = _row(DECISION_COLUMNS, original_decision)
                decision["notes"] = applied_row.notes
                rejection = dict(existing_rejections.get(record_id) or {})
                if not rejection:
                    raise RiboAptamerCheckpoint1ReviewError(
                        f"Human drop {record_id!r} has no rejection-log row"
                    )
                detail = rejection.get("rejection_detail", "")
                extra = "checkpoint1_manual_decision=drop"
                if extra not in detail:
                    rejection["rejection_detail"] = (
                        f"{detail}|{extra}" if detail else extra
                    )
                park = None
                route = applied_row.primary_route_after
            else:
                if not applied_row.decision:
                    raise RiboAptamerCheckpoint1ReviewError(
                        f"Missing post-review decision for {record_id!r}"
                    )
                decision = _row(DECISION_COLUMNS, applied_row.decision)
                decision["notes"] = applied_row.notes
                rejection = (
                    dict(applied_row.rejection_row)
                    if applied_row.rejection_row
                    else None
                )
                park = dict(applied_row.park_row) if applied_row.park_row else None
                route = applied_row.primary_route_after
            for field_name in S3_FORBIDDEN_FIELDS:
                if canonical.get(field_name, ""):
                    raise RiboAptamerCheckpoint1ReviewError(
                        f"Apply populated S4 field {field_name!r} for {record_id!r}"
                    )
            change_report.append(
                {
                    "record_id": record_id,
                    "pre_review_route": applied_row.primary_route_before,
                    "post_review_route": applied_row.primary_route_after,
                    "manual_decision": review.get("manual_decision", ""),
                    "sequence_corrected": (
                        "true" if applied_row.sequence_corrected else "false"
                    ),
                    "molecule_overridden": (
                        "true" if applied_row.molecule_overridden else "false"
                    ),
                    "pre_chemistry": original_canonical.get("chemistry", ""),
                    "post_chemistry": canonical.get("chemistry", ""),
                    "trim_action": review.get("manual_trim_action", ""),
                    "trim_5p_nt": str(applied_row.applied_trim_5p_nt)
                    if (applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt)
                    else "",
                    "trim_3p_nt": str(applied_row.applied_trim_3p_nt)
                    if (applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt)
                    else "",
                    "trim_source": applied_row.trim_source,
                    "pre_core_length": original_canonical.get(
                        "sequence_length_core", ""
                    ),
                    "post_core_length": canonical.get("sequence_length_core", ""),
                    "route_changed": (
                        "true"
                        if applied_row.primary_route_after
                        != applied_row.primary_route_before
                        else "false"
                    ),
                    "rejection_reason_before": existing_rejections.get(
                        record_id, {}
                    ).get("rejection_reason", ""),
                    "rejection_reason_after": (rejection or {}).get(
                        "rejection_reason", ""
                    ),
                    "constant_flag": constant_flag,
                    "cause": (
                        "human_drop"
                        if review.get("manual_decision") == "drop"
                        else (
                            "approved_trim"
                            if applied_row.applied_trim_5p_nt
                            or applied_row.applied_trim_3p_nt
                            else "keep"
                        )
                    ),
                }
            )
            decision_audit.append(
                {
                    "record_id": record_id,
                    "manual_decision": review.get("manual_decision", ""),
                    "manual_trim_action": review.get("manual_trim_action", ""),
                    "consumed": "true",
                    "notes_survived": notes_survived,
                    "applied_trim_5p_nt": str(applied_row.applied_trim_5p_nt or ""),
                    "applied_trim_3p_nt": str(applied_row.applied_trim_3p_nt or ""),
                    "constant_flag": constant_flag,
                    "pre_review_route": applied_row.primary_route_before,
                    "post_review_route": applied_row.primary_route_after,
                }
            )

        preview_canonical.append(canonical)
        preview_decisions.append(decision)
        if route == PRIMARY_ROUTE_REJECT:
            if rejection is None:
                raise RiboAptamerCheckpoint1ReviewError(
                    f"technical_reject missing rejection row for {record_id!r}"
                )
            preview_rejections.append(_row(REJECTION_COLUMNS, rejection))
        elif route == PRIMARY_ROUTE_SSDNA:
            if park is None:
                park = _row(
                    PARK_COLUMNS,
                    {
                        **decision,
                        "park_reason": decision.get("primary_reason", "ssdna_parked"),
                    },
                )
            preview_parked_ssdna.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            preview_eligible.append(_row(ELIGIBLE_COLUMNS, decision))
        else:
            raise RiboAptamerCheckpoint1ReviewError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    if len(preview_canonical) != len(canonical_rows):
        raise RiboAptamerCheckpoint1ReviewError("Reviewed corpus lost records")
    unconsumed = [row["record_id"] for row in queue_rows if row["record_id"] not in applied_by_id]
    if unconsumed:
        raise RiboAptamerCheckpoint1ReviewError(
            f"Unconsumed review decisions: {unconsumed[:5]}"
        )
    notes_lost = [
        row["record_id"] for row in decision_audit if row["notes_survived"] == "false"
    ]
    if notes_lost:
        raise RiboAptamerCheckpoint1ReviewError(
            "Human review notes did not survive apply for "
            + ", ".join(notes_lost[:5])
        )

    total = len(preview_canonical)
    reject_n = len(preview_rejections)
    parked_n = len(preview_parked_ssdna)
    eligible_n = len(preview_eligible)
    if reject_n + parked_n + eligible_n != total:
        raise RiboAptamerCheckpoint1ReviewError(
            "Applied routes do not reconcile to the RiboAptamer source"
        )
    stats: dict[str, int | str | bool] = {
        "total_records": total,
        "reviewed_records": len(queue_rows),
        "decisions_consumed": len(applied),
        "unconsumed_decisions": 0,
        "human_reviewed_drops": human_drops,
        "technical_rejects_after_review": reject_n,
        "parked_ssdna": parked_n,
        "parked_non_protein": 0,
        "technically_eligible": eligible_n,
        "authorised_for_s4": eligible_n,
        "records_trimmed": n_trimmed,
        "core_length_changed": n_core_changed,
        "approved_known_t7_trims": n_trimmed,
        "group_consensus_proposals": 0,
        "strong_unresolved_constant_flags": strong_flags,
        "weak_possible_constant_flags": weak_flags,
        "route_changed": len(route_changed),
        "sequence_corrections": sum(1 for item in applied if item.sequence_corrected),
        "molecule_overrides": sum(1 for item in applied if item.molecule_overridden),
        "s4_started": False,
        "checkpoint_closed": False,
    }
    return RiboAptamerDryRunSimulation(
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked_ssdna=preview_parked_ssdna,
        preview_eligible=preview_eligible,
        change_report=change_report,
        decision_audit=decision_audit,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        stats=stats,
    )


def serialise_riboaptamer_simulation(simulation: RiboAptamerDryRunSimulation) -> bytes:
    import json

    chunks = [
        json.dumps(simulation.preview_canonical, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_decisions, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_rejections, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_parked_ssdna, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.decision_audit, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")
