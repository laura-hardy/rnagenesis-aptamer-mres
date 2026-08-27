"""AptaDB CHECKPOINT-1 application dry-run (preview only).

Uses the same ``apply_aptadb_checkpoint1_package`` transformation as a future
real apply. Writes nothing that the pipeline treats as a closed checkpoint or
S4 handoff.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from adapters.aptadb import EXPECTED_UNLINKED_APTAMERS
from adapters.aptadb_checkpoint1_review import (
    AptaDBCheckpoint1ReviewError,
    AppliedRecordResult,
    apply_reviewed_record,
    validate_review_package,
    _corpus_only,
    LARGE_TRIM_HUMAN_APPROVED_FLAG,
    CHECKPOINT1_TRIM_AUTHORISATION,
)
from adapters.aptadb_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_NON_PROTEIN,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
    UNLINKED_REJECTION_STAGE,
    build_unlinked_rejection_row,
)
from common.corpus_schema import CORPUS_COLUMNS, S3_FORBIDDEN_FIELDS
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
    "pre_molecule",
    "post_molecule",
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
    "primary_reason_before",
    "primary_reason_after",
    "cause",
)

GROUP_SUMMARY_COLUMNS: tuple[str, ...] = (
    "constant_group_id",
    "group_label",
    "n_linked_records",
    "manual_trim_action",
    "applied_5p_nt",
    "applied_3p_nt",
    "core_length_min",
    "core_length_median",
    "core_length_max",
    "guard_rail_failures",
    "n_route_changed",
    "record_exceptions",
    "n_large_trim_human_approved",
    "large_trim_pct_min",
    "large_trim_pct_median",
    "large_trim_pct_max",
)

ELIGIBLE_PREVIEW_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "proposed_decision",
    "primary_reason",
    "primary_route",
    "molecule_type",
    "chemistry",
    "aptadb_target_chemistry",
    "sequence_length_full",
    "sequence_length_core",
    "trim_status",
    "trim_confidence",
)

GUARD_RAIL_FAILURE_COLUMNS: tuple[str, ...] = (
    "record_id",
    "constant_group_id",
    "group_label",
    "manual_decision",
    "pre_full_length",
    "pre_core_length",
    "trim_5p_nt",
    "trim_3p_nt",
    "combined_trim_nt",
    "combined_trim_fraction",
    "hypothetical_core_length",
    "error",
)

LARGE_TRIM_RECORD_COLUMNS: tuple[str, ...] = (
    "record_id",
    "constant_group_id",
    "group_label",
    "trim_source",
    "human_trim_action",
    "full_length",
    "trim_5p_nt",
    "trim_3p_nt",
    "trim_fraction",
    "trim_pct",
    "core_length",
    "authorisation",
    "large_trim_human_approved",
    "pre_review_route",
    "post_review_route",
    "route_changed",
)

LARGE_TRIM_GROUP_COLUMNS: tuple[str, ...] = (
    "group_label",
    "constant_group_id",
    "n_records",
    "record_ids",
    "full_length_min",
    "full_length_max",
    "trim_5p_nt",
    "trim_3p_nt",
    "trim_pct_min",
    "trim_pct_median",
    "trim_pct_max",
    "core_length_min",
    "core_length_median",
    "core_length_max",
    "n_passing_remaining_guard_rails",
    "n_failing_remaining_guard_rails",
    "n_route_changed",
)


@dataclass
class AptaDBDryRunSimulation:
    """In-memory dry-run preview. Not an applied checkpoint."""

    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked_ssdna: list[dict[str, str]]
    preview_parked_non_protein: list[dict[str, str]]
    preview_eligible: list[dict[str, str]]
    change_report: list[dict[str, str]]
    group_summaries: list[dict[str, str]]
    applied: list[AppliedRecordResult]
    route_changed_ids: tuple[str, ...]
    guard_rail_failure_rows: list[dict[str, str]] = field(default_factory=list)
    large_trim_records: list[dict[str, str]] = field(default_factory=list)
    large_trim_groups: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, int | str | bool] = field(default_factory=dict)


def _derive_route_change_cause(
    *,
    manual_decision: str,
    sequence_corrected: bool,
    molecule_overridden: bool,
    trimmed: bool,
) -> str:
    parts: list[str] = []
    if manual_decision == "drop":
        parts.append("human drop")
    if sequence_corrected:
        parts.append("sequence correction")
    if molecule_overridden:
        parts.append("molecule override")
    if trimmed:
        parts.append("trim")
    if not parts:
        return "other"
    if len(parts) == 1:
        return parts[0]
    return "combination"


def _fmt_pct(values: Sequence[float]) -> tuple[str, str, str]:
    if not values:
        return "", "", ""
    ordered = sorted(values)
    return (
        f"{ordered[0]:.2f}",
        f"{statistics.median(ordered):.2f}",
        f"{ordered[-1]:.2f}",
    )


def _fmt_int_stats(values: Sequence[int]) -> tuple[str, str, str]:
    if not values:
        return "", "", ""
    ordered = sorted(values)
    median = statistics.median(ordered)
    median_text = (
        str(int(median)) if float(median).is_integer() else str(median)
    )
    return str(ordered[0]), median_text, str(ordered[-1])


def _int_len(value: str) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def _length_buckets(lengths: Sequence[int]) -> dict[str, int | float]:
    if not lengths:
        return {
            "min": 0,
            "median": 0,
            "max": 0,
            "lt20": 0,
            "b20_25": 0,
            "b26_89": 0,
            "b90_100": 0,
            "gt100": 0,
        }
    ordered = sorted(lengths)
    return {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
        "lt20": sum(1 for item in ordered if item < 20),
        "b20_25": sum(1 for item in ordered if 20 <= item <= 25),
        "b26_89": sum(1 for item in ordered if 26 <= item <= 89),
        "b90_100": sum(1 for item in ordered if 90 <= item <= 100),
        "gt100": sum(1 for item in ordered if item > 100),
    }


def _row(fieldnames: Sequence[str], payload: Mapping[str, str]) -> dict[str, str]:
    return {column: str(payload.get(column, "") or "") for column in fieldnames}


def _before_route_counts(decision_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    routes = [row.get("primary_route", "") for row in decision_rows]
    return {
        "before_technical_rejects": sum(
            1 for route in routes if route == PRIMARY_ROUTE_REJECT
        ),
        "before_parked_ssdna": sum(
            1 for route in routes if route == PRIMARY_ROUTE_SSDNA
        ),
        "before_parked_non_protein": sum(
            1 for route in routes if route == PRIMARY_ROUTE_NON_PROTEIN
        ),
        "before_technically_eligible": sum(
            1 for route in routes if route == PRIMARY_ROUTE_ELIGIBLE
        ),
    }


def _build_large_trim_records(
    *,
    applied: Sequence[AppliedRecordResult],
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    fail_ids: set[str],
) -> list[dict[str, str]]:
    groups_by_id = {row["constant_group_id"]: row for row in group_rows}
    review_by_id = {row["record_id"]: row for row in queue_rows}
    rows: list[dict[str, str]] = []
    for item in applied:
        if not item.large_trim_human_approved:
            continue
        review = review_by_id.get(item.record_id, {})
        group = groups_by_id.get(review.get("constant_group_id", ""), {})
        human_action = (
            review.get("manual_trim_action", "")
            or group.get("manual_trim_action", "")
        )
        rows.append(
            {
                "record_id": item.record_id,
                "constant_group_id": review.get("constant_group_id", ""),
                "group_label": group.get("group_label", ""),
                "trim_source": item.trim_source,
                "human_trim_action": human_action,
                "full_length": str(item.sequence_length_full),
                "trim_5p_nt": str(item.applied_trim_5p_nt),
                "trim_3p_nt": str(item.applied_trim_3p_nt),
                "trim_fraction": f"{item.trim_fraction:.6f}",
                "trim_pct": f"{item.trim_fraction * 100:.2f}",
                "core_length": str(item.sequence_length_core),
                "authorisation": CHECKPOINT1_TRIM_AUTHORISATION,
                "large_trim_human_approved": "true",
                "pre_review_route": item.primary_route_before,
                "post_review_route": item.primary_route_after,
                "route_changed": (
                    "true"
                    if item.primary_route_after != item.primary_route_before
                    else "false"
                ),
            }
        )
    rows.sort(key=lambda row: (row["constant_group_id"], row["record_id"]))
    return rows


def _build_large_trim_groups(
    records: Sequence[Mapping[str, str]],
    *,
    fail_ids: set[str],
) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, str]]] = {}
    for row in records:
        key = (
            row.get("constant_group_id", ""),
            row.get("group_label", ""),
            row.get("trim_5p_nt", ""),
            row.get("trim_3p_nt", ""),
        )
        grouped.setdefault(key, []).append(row)
    summaries: list[dict[str, str]] = []
    for (group_id, label, five, three), members in grouped.items():
        fulls = [_int_len(item.get("full_length", "")) for item in members]
        cores = [_int_len(item.get("core_length", "")) for item in members]
        pcts = [float(item.get("trim_pct") or 0.0) for item in members]
        ids = [item["record_id"] for item in members]
        failing = sum(1 for record_id in ids if record_id in fail_ids)
        passing = len(ids) - failing
        route_changed = sum(
            1 for item in members if item.get("route_changed") == "true"
        )
        pct_min, pct_med, pct_max = _fmt_pct(pcts)
        core_min, core_med, core_max = _fmt_int_stats(cores)
        summaries.append(
            {
                "group_label": label,
                "constant_group_id": group_id,
                "n_records": str(len(members)),
                "record_ids": "|".join(ids),
                "full_length_min": str(min(fulls)) if fulls else "",
                "full_length_max": str(max(fulls)) if fulls else "",
                "trim_5p_nt": five,
                "trim_3p_nt": three,
                "trim_pct_min": pct_min,
                "trim_pct_median": pct_med,
                "trim_pct_max": pct_max,
                "core_length_min": core_min,
                "core_length_median": core_med,
                "core_length_max": core_max,
                "n_passing_remaining_guard_rails": str(passing),
                "n_failing_remaining_guard_rails": str(failing),
                "n_route_changed": str(route_changed),
            }
        )
    summaries.sort(key=lambda row: (row["group_label"], row["constant_group_id"]))
    return summaries


def simulate_aptadb_checkpoint1_application(
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
    unlinked_rows: Sequence[Mapping[str, str]] = (),
    existing_rejection_rows: Sequence[Mapping[str, str]] = (),
    existing_parked_ssdna: Sequence[Mapping[str, str]] = (),
    existing_parked_non_protein: Sequence[Mapping[str, str]] = (),
    expected_interaction_rows: int | None = 1350,
    expected_unlinked_rows: int | None = EXPECTED_UNLINKED_APTAMERS,
) -> AptaDBDryRunSimulation:
    """Apply reviewed records in memory and merge onto the full interaction set."""
    if len(canonical_rows) != len(decision_rows):
        raise AptaDBCheckpoint1ReviewError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_interaction_rows is not None and len(canonical_rows) != (
        expected_interaction_rows
    ):
        raise AptaDBCheckpoint1ReviewError(
            f"Dry-run canonical must have {expected_interaction_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    if expected_unlinked_rows is not None and len(unlinked_rows) != (
        expected_unlinked_rows
    ):
        raise AptaDBCheckpoint1ReviewError(
            f"Unlinked aptamers must be {expected_unlinked_rows}; "
            f"got {len(unlinked_rows)}"
        )

    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    decision_by_id = {row["record_id"]: row for row in decision_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise AptaDBCheckpoint1ReviewError("Duplicate canonical record_id")
    existing_interaction_rejections = {
        row["record_id"]: row
        for row in existing_rejection_rows
        if row.get("stage") != UNLINKED_REJECTION_STAGE
    }
    parked_ssdna_by_id = {row["record_id"]: row for row in existing_parked_ssdna}
    parked_non_protein_by_id = {
        row["record_id"]: row for row in existing_parked_non_protein
    }

    applied, report = [], validate_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
    )
    if not report.ok:
        raise AptaDBCheckpoint1ReviewError(
            "Dry-run cannot proceed; review package is not ready"
        )
    groups_by_id = {row["constant_group_id"]: row for row in group_rows}
    proposals_by_record = proposals_by_record or {}
    review_by_id = {row["record_id"]: row for row in queue_rows}
    applied: list[AppliedRecordResult] = []
    guard_rail_failure_rows: list[dict[str, str]] = []
    for row in queue_rows:
        record_id = row["record_id"]
        group = groups_by_id.get(row.get("constant_group_id", ""), None)
        machine_five = 0
        machine_three = 0
        if group:
            machine_five = (
                int(group["machine_trim_5p_nt"] or 0)
                if str(group.get("machine_trim_5p_nt") or "").isdigit()
                else 0
            )
            machine_three = (
                int(group["machine_trim_3p_nt"] or 0)
                if str(group.get("machine_trim_3p_nt") or "").isdigit()
                else 0
            )
        try:
            applied.append(
                apply_reviewed_record(
                    canonical=canonical_by_id[record_id],
                    review_row=row,
                    source_metadata=source_metadata_by_id[record_id],
                    s2_qc=s2_qc_by_id[record_id],
                    policy=policy,
                    proposals=list(proposals_by_record.get(record_id, ())),
                    group_row=group,
                    machine_five=machine_five,
                    machine_three=machine_three,
                )
            )
        except AptaDBCheckpoint1ReviewError as exc:
            message = str(exc)
            canonical = canonical_by_id[record_id]
            full_len = _int_len(canonical.get("sequence_length_full", ""))
            five = row.get("manual_trim_5p_nt") or (
                group.get("manual_trim_5p_nt", "") if group else ""
            )
            three = row.get("manual_trim_3p_nt") or (
                group.get("manual_trim_3p_nt", "") if group else ""
            )
            five_n = int(five) if str(five).isdigit() else 0
            three_n = int(three) if str(three).isdigit() else 0
            combined = five_n + three_n
            fraction = (combined / full_len) if full_len else 0.0
            guard_rail_failure_rows.append(
                {
                    "record_id": record_id,
                    "constant_group_id": row.get("constant_group_id", ""),
                    "group_label": group.get("group_label", "") if group else "",
                    "manual_decision": row.get("manual_decision", ""),
                    "pre_full_length": str(full_len),
                    "pre_core_length": canonical.get("sequence_length_core", ""),
                    "trim_5p_nt": str(five_n),
                    "trim_3p_nt": str(three_n),
                    "combined_trim_nt": str(combined),
                    "combined_trim_fraction": f"{fraction:.4f}",
                    "hypothetical_core_length": str(full_len - combined),
                    "error": message,
                }
            )
    applied_by_id = {item.record_id: item for item in applied}
    if "aptadb:1170" in applied_by_id:
        g5 = applied_by_id["aptadb:1170"]
        if g5.applied_trim_5p_nt != 18 or g5.applied_trim_3p_nt != 0:
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:1170 dry-run trim must be 18/0"
            )
        if g5.sequence_length_core != 57:
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:1170 reviewed core length must be 57 nt; "
                f"got {g5.sequence_length_core}"
            )
        if g5.molecule_type != "RNA" or g5.chemistry != "RNA":
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:1170 must be reviewed as RNA/RNA"
            )
    if "aptadb:459" in applied_by_id:
        exception = applied_by_id["aptadb:459"]
        if exception.applied_trim_5p_nt != 23 or exception.applied_trim_3p_nt != 0:
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:459 dry-run trim must be 23/0"
            )

    if guard_rail_failure_rows:
        fail_ids = {row["record_id"] for row in guard_rail_failure_rows}
        large_trim_records = _build_large_trim_records(
            applied=applied,
            queue_rows=queue_rows,
            group_rows=group_rows,
            fail_ids=fail_ids,
        )
        before_routes = _before_route_counts(decision_rows)
        stats: dict[str, int | str | bool] = {
            "total_interactions": len(canonical_rows),
            "human_reviewed_drops": sum(
                1
                for item in applied
                if "checkpoint1_manual_decision=drop" in item.notes
            ),
            "technical_rejects_after_review": 0,
            "technical_rejects_excluding_human_drop": 0,
            "parked_ssdna": 0,
            "parked_non_protein": 0,
            "technically_eligible": 0,
            "unlinked_aptamers": len(unlinked_rows),
            "unlinked_missing_target": len(unlinked_rows),
            "route_changed": 0,
            "sequence_corrections": sum(
                1 for item in applied if item.sequence_corrected
            ),
            "molecule_overrides": sum(1 for item in applied if item.molecule_overridden),
            "records_trimmed": sum(
                1
                for item in applied
                if item.applied_trim_5p_nt or item.applied_trim_3p_nt
            ),
            "trimmed_by_group": sum(
                1 for item in applied if item.trim_source == "group"
            ),
            "trimmed_by_record_override": sum(
                1 for item in applied if item.trim_source == "record"
            ),
            "core_length_changed": 0,
            "large_trim_human_approved": len(large_trim_records),
            "guard_rail_failures": len(guard_rail_failure_rows),
            "reviewed_records_applied": len(applied),
            "reviewed_records": len(queue_rows),
            "authorised_for_s4": 0,
            "checkpoint_closed": False,
            "preview_complete": False,
            "before_core_min": 0,
            "before_core_median": 0,
            "before_core_max": 0,
            "before_core_lt20": 0,
            "before_core_20_25": 0,
            "before_core_26_89": 0,
            "before_core_90_100": 0,
            "before_core_gt100": 0,
            "after_core_min": 0,
            "after_core_median": 0,
            "after_core_max": 0,
            "after_core_lt20": 0,
            "after_core_20_25": 0,
            "after_core_26_89": 0,
            "after_core_90_100": 0,
            "after_core_gt100": 0,
            **before_routes,
        }
        return AptaDBDryRunSimulation(
            preview_canonical=[],
            preview_decisions=[],
            preview_rejections=[],
            preview_parked_ssdna=[],
            preview_parked_non_protein=[],
            preview_eligible=[],
            change_report=[],
            group_summaries=_group_summaries(
                group_rows=group_rows,
                queue_rows=queue_rows,
                applied_by_id=applied_by_id,
                guard_rail_failure_rows=guard_rail_failure_rows,
            ),
            applied=applied,
            route_changed_ids=tuple(),
            guard_rail_failure_rows=guard_rail_failure_rows,
            large_trim_records=large_trim_records,
            large_trim_groups=_build_large_trim_groups(
                large_trim_records, fail_ids=fail_ids
            ),
            stats=stats,
        )

    preview_canonical: list[dict[str, str]] = []
    preview_decisions: list[dict[str, str]] = []
    preview_rejections: list[dict[str, str]] = []
    preview_parked_ssdna: list[dict[str, str]] = []
    preview_parked_non_protein: list[dict[str, str]] = []
    preview_eligible: list[dict[str, str]] = []
    change_report: list[dict[str, str]] = []
    route_changed: list[str] = []
    guard_failures = 0
    human_drops = 0
    n_sequence_corrected = 0
    n_molecule_overridden = 0
    n_trimmed = 0
    n_trimmed_group = 0
    n_trimmed_record = 0
    n_core_changed = 0

    for original_canonical, original_decision in zip(
        canonical_rows, decision_rows, strict=True
    ):
        record_id = original_canonical["record_id"]
        original_raw = original_canonical["sequence_raw"]
        applied_row = applied_by_id.get(record_id)
        if applied_row is None:
            canonical = _corpus_only(original_canonical)
            decision = _row(DECISION_COLUMNS, original_decision)
            rejection = existing_interaction_rejections.get(record_id)
            park = parked_ssdna_by_id.get(record_id) or parked_non_protein_by_id.get(
                record_id
            )
            route = decision["primary_route"]
        else:
            canonical = _corpus_only(applied_row.canonical)
            if canonical["sequence_raw"] != original_raw:
                raise AptaDBCheckpoint1ReviewError(
                    f"Dry-run mutated sequence_raw for {record_id!r}"
                )
            review = review_by_id[record_id]
            if applied_row.primary_route_after != applied_row.primary_route_before:
                route_changed.append(record_id)
            if applied_row.sequence_corrected:
                n_sequence_corrected += 1
            if applied_row.molecule_overridden:
                n_molecule_overridden += 1
            if applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt:
                n_trimmed += 1
                if applied_row.trim_source == "group":
                    n_trimmed_group += 1
                elif applied_row.trim_source == "record":
                    n_trimmed_record += 1
            if _int_len(canonical["sequence_length_core"]) != _int_len(
                original_canonical.get("sequence_length_core", "")
            ):
                n_core_changed += 1
            if review.get("manual_decision") == "drop":
                human_drops += 1
                decision = _row(DECISION_COLUMNS, original_decision)
                decision["notes"] = applied_row.notes
                rejection = dict(existing_interaction_rejections.get(record_id) or {})
                if rejection:
                    detail = rejection.get("rejection_detail", "")
                    extra = "checkpoint1_manual_decision=drop"
                    rejection["rejection_detail"] = (
                        f"{detail}|{extra}" if detail else extra
                    )
                park = None
                route = applied_row.primary_route_after
            else:
                if not applied_row.decision:
                    raise AptaDBCheckpoint1ReviewError(
                        f"Missing post-review decision for {record_id!r}"
                    )
                decision = _row(DECISION_COLUMNS, applied_row.decision)
                decision["notes"] = applied_row.notes
                rejection = applied_row.rejection_row
                park = applied_row.park_row
                route = applied_row.primary_route_after
            if (
                canonical["sequence_full"]
                and canonical["sequence_core"]
                and canonical["sequence_core"] not in canonical["sequence_full"]
            ):
                guard_failures += 1
                raise AptaDBCheckpoint1ReviewError(
                    f"sequence_core is not a substring of sequence_full for "
                    f"{record_id!r}"
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
                    "pre_molecule": original_canonical.get("molecule_type", ""),
                    "post_molecule": canonical.get("molecule_type", ""),
                    "pre_chemistry": original_canonical.get("chemistry", ""),
                    "post_chemistry": canonical.get("chemistry", ""),
                    "trim_action": review.get("manual_trim_action", "")
                    or groups_by_id.get(
                        review.get("constant_group_id", ""), {}
                    ).get("manual_trim_action", ""),
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
                    "rejection_reason_before": (
                        existing_interaction_rejections.get(record_id, {}).get(
                            "rejection_reason", ""
                        )
                    ),
                    "rejection_reason_after": (
                        (rejection or {}).get("rejection_reason", "")
                    ),
                    "primary_reason_before": original_decision.get(
                        "primary_reason", ""
                    ),
                    "primary_reason_after": decision.get("primary_reason", ""),
                    "cause": _derive_route_change_cause(
                        manual_decision=review.get("manual_decision", ""),
                        sequence_corrected=applied_row.sequence_corrected,
                        molecule_overridden=applied_row.molecule_overridden,
                        trimmed=bool(
                            applied_row.applied_trim_5p_nt
                            or applied_row.applied_trim_3p_nt
                        ),
                    ),
                }
            )

        for field_name in S3_FORBIDDEN_FIELDS:
            if canonical.get(field_name, ""):
                raise AptaDBCheckpoint1ReviewError(
                    f"Dry-run populated S4 field {field_name!r} for {record_id!r}"
                )
        preview_canonical.append(canonical)
        preview_decisions.append(decision)
        if route == PRIMARY_ROUTE_REJECT:
            if rejection is None:
                raise AptaDBCheckpoint1ReviewError(
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
        elif route == PRIMARY_ROUTE_NON_PROTEIN:
            if park is None:
                park = _row(
                    PARK_COLUMNS,
                    {
                        **decision,
                        "park_reason": decision.get(
                            "primary_reason", "non_protein_target_parked"
                        ),
                    },
                )
            preview_parked_non_protein.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            preview_eligible.append(_row(ELIGIBLE_PREVIEW_COLUMNS, decision))
        else:
            raise AptaDBCheckpoint1ReviewError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    source_dataset = canonical_rows[0]["source_dataset"] if canonical_rows else ""
    unlinked_rejections: list[dict[str, str]] = []
    unlinked_ids: set[str] = set()
    for unlinked in unlinked_rows:
        rejection = build_unlinked_rejection_row(
            unlinked, source_dataset=source_dataset
        )
        if not rejection["record_id"].startswith("aptadb:unlinked:"):
            raise AptaDBCheckpoint1ReviewError(
                "Unlinked rejection must use source-level identity"
            )
        if rejection["record_id"] in decision_by_id:
            raise AptaDBCheckpoint1ReviewError(
                "Unlinked rejection collided with an interaction record_id"
            )
        unlinked_ids.add(rejection["record_id"])
        unlinked_rejections.append(rejection)
    preview_rejections.extend(unlinked_rejections)

    if "aptadb:1170" in applied_by_id:
        g5 = applied_by_id["aptadb:1170"]
        if g5.applied_trim_5p_nt != 18 or g5.applied_trim_3p_nt != 0:
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:1170 dry-run trim must be 18/0"
            )
        if g5.sequence_length_core != 57:
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:1170 reviewed core length must be 57 nt; "
                f"got {g5.sequence_length_core}"
            )
        if g5.molecule_type != "RNA" or g5.chemistry != "RNA":
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:1170 must be reviewed as RNA/RNA"
            )
    if "aptadb:459" in applied_by_id:
        exception = applied_by_id["aptadb:459"]
        if exception.applied_trim_5p_nt != 23 or exception.applied_trim_3p_nt != 0:
            raise AptaDBCheckpoint1ReviewError(
                "aptadb:459 dry-run trim must be 23/0"
            )

    ap65_id = "aptadb:tgt_pub:0e015a3d17a96ed2"
    for item in applied:
        review = review_by_id[item.record_id]
        if review.get("constant_group_id") != ap65_id:
            continue
        if item.record_id == "aptadb:459":
            continue
        if item.applied_trim_5p_nt != 23 or item.applied_trim_3p_nt != 21:
            raise AptaDBCheckpoint1ReviewError(
                f"AP65 ordinary member {item.record_id} must use 23/21; "
                f"got {item.applied_trim_5p_nt}/{item.applied_trim_3p_nt}"
            )

    routes = [row["primary_route"] for row in preview_decisions]
    if len(routes) != len(canonical_rows):
        raise AptaDBCheckpoint1ReviewError("Preview decision count drifted")
    reject_n = sum(1 for route in routes if route == PRIMARY_ROUTE_REJECT)
    ssdna_n = sum(1 for route in routes if route == PRIMARY_ROUTE_SSDNA)
    non_protein_n = sum(1 for route in routes if route == PRIMARY_ROUTE_NON_PROTEIN)
    eligible_n = sum(1 for route in routes if route == PRIMARY_ROUTE_ELIGIBLE)
    if reject_n + ssdna_n + non_protein_n + eligible_n != len(canonical_rows):
        raise AptaDBCheckpoint1ReviewError(
            "Preview routes do not reconcile to the interaction corpus"
        )
    if len(preview_parked_ssdna) != ssdna_n:
        raise AptaDBCheckpoint1ReviewError("Parked ssDNA preview count mismatch")
    if len(preview_parked_non_protein) != non_protein_n:
        raise AptaDBCheckpoint1ReviewError("Parked non-protein preview count mismatch")
    if len(preview_eligible) != eligible_n:
        raise AptaDBCheckpoint1ReviewError("Eligible preview count mismatch")
    interaction_rejects = [
        row
        for row in preview_rejections
        if row.get("stage") != UNLINKED_REJECTION_STAGE
    ]
    if len(interaction_rejects) != reject_n:
        raise AptaDBCheckpoint1ReviewError(
            "Interaction rejection preview count does not match technical_reject"
        )
    if len(unlinked_rejections) != len(unlinked_rows):
        raise AptaDBCheckpoint1ReviewError("Unlinked rejection count mismatch")
    missing_target = [
        row
        for row in unlinked_rejections
        if row.get("rejection_reason") == "missing_target"
    ]
    if len(missing_target) != len(unlinked_rows):
        raise AptaDBCheckpoint1ReviewError(
            "Every unlinked aptamer must remain missing_target"
        )
    if any(
        not row["record_id"].startswith("aptadb:unlinked:")
        for row in unlinked_rejections
    ):
        raise AptaDBCheckpoint1ReviewError("Fake interaction unlinked IDs are forbidden")

    group_summaries = _group_summaries(
        group_rows=group_rows,
        queue_rows=queue_rows,
        applied_by_id=applied_by_id,
    )
    large_trim_records = _build_large_trim_records(
        applied=applied,
        queue_rows=queue_rows,
        group_rows=group_rows,
        fail_ids=set(),
    )
    large_trim_groups = _build_large_trim_groups(
        large_trim_records, fail_ids=set()
    )
    before_lengths = [
        _int_len(row.get("sequence_length_core", "")) for row in canonical_rows
    ]
    after_lengths = [
        _int_len(row.get("sequence_length_core", "")) for row in preview_canonical
    ]
    before_buckets = _length_buckets(before_lengths)
    after_buckets = _length_buckets(after_lengths)
    before_routes = _before_route_counts(decision_rows)

    stats: dict[str, int | str | bool] = {
        "total_interactions": len(canonical_rows),
        "human_reviewed_drops": human_drops,
        "technical_rejects_after_review": reject_n,
        "technical_rejects_excluding_human_drop": reject_n - human_drops,
        "parked_ssdna": ssdna_n,
        "parked_non_protein": non_protein_n,
        "technically_eligible": eligible_n,
        "unlinked_aptamers": len(unlinked_rows),
        "unlinked_missing_target": len(missing_target),
        "route_changed": len(route_changed),
        "sequence_corrections": n_sequence_corrected,
        "molecule_overrides": n_molecule_overridden,
        "records_trimmed": n_trimmed,
        "trimmed_by_group": n_trimmed_group,
        "trimmed_by_record_override": n_trimmed_record,
        "core_length_changed": n_core_changed,
        "large_trim_human_approved": len(large_trim_records),
        "guard_rail_failures": guard_failures,
        "reviewed_records": len(applied),
        "authorised_for_s4": 0,
        "checkpoint_closed": False,
        "preview_complete": True,
        "before_core_min": int(before_buckets["min"]),
        "before_core_median": before_buckets["median"],
        "before_core_max": int(before_buckets["max"]),
        "before_core_lt20": int(before_buckets["lt20"]),
        "before_core_20_25": int(before_buckets["b20_25"]),
        "before_core_26_89": int(before_buckets["b26_89"]),
        "before_core_90_100": int(before_buckets["b90_100"]),
        "before_core_gt100": int(before_buckets["gt100"]),
        "after_core_min": int(after_buckets["min"]),
        "after_core_median": after_buckets["median"],
        "after_core_max": int(after_buckets["max"]),
        "after_core_lt20": int(after_buckets["lt20"]),
        "after_core_20_25": int(after_buckets["b20_25"]),
        "after_core_26_89": int(after_buckets["b26_89"]),
        "after_core_90_100": int(after_buckets["b90_100"]),
        "after_core_gt100": int(after_buckets["gt100"]),
        **before_routes,
    }
    if guard_failures != 0:
        raise AptaDBCheckpoint1ReviewError("Dry-run guard-rail failures are forbidden")

    return AptaDBDryRunSimulation(
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked_ssdna=preview_parked_ssdna,
        preview_parked_non_protein=preview_parked_non_protein,
        preview_eligible=preview_eligible,
        change_report=change_report,
        group_summaries=group_summaries,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        large_trim_records=large_trim_records,
        large_trim_groups=large_trim_groups,
        stats=stats,
    )


def _group_summaries(
    *,
    group_rows: Sequence[Mapping[str, str]],
    queue_rows: Sequence[Mapping[str, str]],
    applied_by_id: Mapping[str, AppliedRecordResult],
    guard_rail_failure_rows: Sequence[Mapping[str, str]] = (),
) -> list[dict[str, str]]:
    linked: dict[str, list[str]] = {}
    for row in queue_rows:
        group_id = (row.get("constant_group_id") or "").strip()
        if group_id:
            linked.setdefault(group_id, []).append(row["record_id"])
    summaries: list[dict[str, str]] = []
    for group in group_rows:
        group_id = group["constant_group_id"]
        fail_ids = {
            row["record_id"]
            for row in guard_rail_failure_rows
            if row.get("constant_group_id") == group_id
        }
        members = linked.get(group_id, [])
        cores: list[int] = []
        large_pcts: list[float] = []
        route_changed_n = 0
        exceptions: list[str] = []
        applied_five = group.get("manual_trim_5p_nt", "")
        applied_three = group.get("manual_trim_3p_nt", "")
        for record_id in members:
            item = applied_by_id.get(record_id)
            if item is None:
                continue
            cores.append(item.sequence_length_core)
            if item.large_trim_human_approved:
                large_pcts.append(item.trim_fraction * 100.0)
            if item.primary_route_after != item.primary_route_before:
                route_changed_n += 1
            review_action = ""
            for row in queue_rows:
                if row["record_id"] == record_id:
                    review_action = row.get("manual_trim_action", "")
                    break
            if review_action:
                exceptions.append(record_id)
            if record_id == members[0] and group.get("manual_trim_action") in {
                "approve",
                "override",
            }:
                applied_five = str(item.applied_trim_5p_nt)
                applied_three = str(item.applied_trim_3p_nt)
        if group.get("manual_trim_action") == "reject":
            applied_five = ""
            applied_three = ""
        if exceptions:
            # Prefer exception member lengths separately; group applied lengths
            # come from an ordinary member when possible.
            ordinary = [
                applied_by_id[record_id]
                for record_id in members
                if record_id not in exceptions and record_id in applied_by_id
            ]
            if ordinary:
                applied_five = str(ordinary[0].applied_trim_5p_nt)
                applied_three = str(ordinary[0].applied_trim_3p_nt)
            else:
                applied_five = group.get("manual_trim_5p_nt", "")
                applied_three = group.get("manual_trim_3p_nt", "")
        cores_sorted = sorted(cores)
        summaries.append(
            {
                "constant_group_id": group_id,
                "group_label": group.get("group_label", ""),
                "n_linked_records": str(len(members)),
                "manual_trim_action": group.get("manual_trim_action", ""),
                "applied_5p_nt": applied_five,
                "applied_3p_nt": applied_three,
                "core_length_min": str(cores_sorted[0]) if cores_sorted else "",
                "core_length_median": (
                    str(statistics.median(cores_sorted)) if cores_sorted else ""
                ),
                "core_length_max": str(cores_sorted[-1]) if cores_sorted else "",
                "guard_rail_failures": str(len(fail_ids)),
                "n_route_changed": str(route_changed_n),
                "record_exceptions": "|".join(exceptions),
                "n_large_trim_human_approved": str(len(large_pcts)),
                "large_trim_pct_min": (
                    f"{min(large_pcts):.2f}" if large_pcts else ""
                ),
                "large_trim_pct_median": (
                    f"{statistics.median(large_pcts):.2f}" if large_pcts else ""
                ),
                "large_trim_pct_max": (
                    f"{max(large_pcts):.2f}" if large_pcts else ""
                ),
            }
        )
    return summaries


def format_dry_run_markdown(
    simulation: AptaDBDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
) -> str:
    stats = simulation.stats
    failed = int(stats.get("guard_rail_failures") or 0) > 0
    complete = bool(stats.get("preview_complete"))
    lines = [
        "# AptaDB CHECKPOINT-1 application dry-run",
        "",
        DRY_RUN_BANNER,
        "",
        (
            "**NO-GO for real CHECKPOINT-1 application.** Remaining absolute "
            "trim guard rails blocked one or more records. No complete "
            "1,350-row post-review routing preview was produced."
            if failed
            else
            "Human decisions were simulated through the real apply transformation. "
            "Combined trim >40% is treated as a review/trigger rail: explicit "
            "human CHECKPOINT-1 approve/override may proceed with derived "
            f"`{LARGE_TRIM_HUMAN_APPROVED_FLAG}` provenance."
        ),
        "Canonical S2/S3 outputs were not rewritten. CHECKPOINT-1 is not closed.",
        "No record is authorised for S4.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- group review SHA-256: `{review_hashes.get('groups', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        "",
        "## Successfully simulated technical/exception records",
        "",
    ]
    notable = {
        item.record_id: item
        for item in simulation.applied
        if item.record_id
        in {"aptadb:230", "aptadb:491", "aptadb:305", "aptadb:1170", "aptadb:459"}
    }
    if notable:
        for record_id in (
            "aptadb:230",
            "aptadb:491",
            "aptadb:305",
            "aptadb:1170",
            "aptadb:459",
        ):
            item = notable.get(record_id)
            if item is None:
                continue
            lines.append(
                f"- `{record_id}`: `{item.primary_route_before}` → "
                f"`{item.primary_route_after}`; "
                f"core `{item.sequence_length_core}`; "
                f"trim `{item.applied_trim_5p_nt}/{item.applied_trim_3p_nt}`; "
                f"molecule `{item.molecule_type}`/`{item.chemistry}`"
            )
    else:
        lines.append("- none in this dry-run subset")
    lines.extend(["", "## Routing reconciliation (1,350 interactions)", ""])
    if failed or not complete:
        lines.append(
            "Not produced. Guard-rail failures prevent a complete "
            "post-review 1,350-row routing preview."
        )
    else:
        lines.extend(
            [
                f"- total interactions: `{stats['total_interactions']}`",
                f"- human-reviewed drops: `{stats['human_reviewed_drops']}` "
                "(subset of technical rejects)",
                f"- post-review technical rejects (including human drops): "
                f"`{stats['technical_rejects_after_review']}`",
                f"- post-review technical rejects excluding human drops: "
                f"`{stats['technical_rejects_excluding_human_drop']}`",
                f"- parked ssDNA: `{stats['parked_ssdna']}`",
                f"- parked RNA non-protein: `{stats['parked_non_protein']}`",
                f"- RNA-protein technically eligible: "
                f"`{stats['technically_eligible']}`",
                "",
                "Reconciliation: technical rejects + parked ssDNA + parked "
                "RNA non-protein + technically eligible = total interactions.",
                "",
                "## Routing before → after (pre-review S3 → dry-run preview)",
                "",
                "| route | before | after |",
                "|---|---:|---:|",
                f"| technical rejects | `{stats.get('before_technical_rejects', '')}` "
                f"| `{stats['technical_rejects_after_review']}` |",
                f"| parked ssDNA | `{stats.get('before_parked_ssdna', '')}` "
                f"| `{stats['parked_ssdna']}` |",
                f"| parked RNA non-protein | "
                f"`{stats.get('before_parked_non_protein', '')}` "
                f"| `{stats['parked_non_protein']}` |",
                f"| RNA-protein technically eligible | "
                f"`{stats.get('before_technically_eligible', '')}` "
                f"| `{stats['technically_eligible']}` |",
            ]
        )
    lines.extend(
        [
            "",
            "## Route changes",
            "",
            f"- records whose primary route changed: `{stats['route_changed']}`",
        ]
    )
    if simulation.route_changed_ids:
        for record_id in simulation.route_changed_ids:
            row = next(
                item
                for item in simulation.change_report
                if item["record_id"] == record_id
            )
            lines.append(
                f"- `{record_id}`: `{row['pre_review_route']}` → "
                f"`{row['post_review_route']}`; cause=`{row.get('cause', '')}`"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Human-approved >40% trims",
            "",
            f"- records: `{stats.get('large_trim_human_approved', 0)}`",
            f"- derived marker: `{LARGE_TRIM_HUMAN_APPROVED_FLAG}`",
            "",
        ]
    )
    if simulation.large_trim_groups:
        for group in simulation.large_trim_groups:
            lines.append(
                f"- `{group['group_label']}` (`{group['constant_group_id']}`): "
                f"n=`{group['n_records']}`; "
                f"full-length `{group['full_length_min']}`–"
                f"`{group['full_length_max']}`; "
                f"5′=`{group['trim_5p_nt']}`; 3′=`{group['trim_3p_nt']}`; "
                f"trim% min/median/max=`{group['trim_pct_min']}`/"
                f"`{group['trim_pct_median']}`/`{group['trim_pct_max']}`; "
                f"core min/median/max=`{group['core_length_min']}`/"
                f"`{group['core_length_median']}`/`{group['core_length_max']}`; "
                f"passing remaining rails=`{group['n_passing_remaining_guard_rails']}`; "
                f"failing remaining rails=`{group['n_failing_remaining_guard_rails']}`; "
                f"route_changed=`{group['n_route_changed']}`"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Constant-region groups",
            "",
        ]
    )
    for group in simulation.group_summaries:
        five = group["applied_5p_nt"] or "blank"
        three = group["applied_3p_nt"] or "blank"
        lines.append(
            f"- `{group['group_label']}` (`{group['constant_group_id']}`): "
            f"action=`{group['manual_trim_action']}`; 5′=`{five}`; 3′=`{three}`; "
            f"linked=`{group['n_linked_records']}`; "
            f"core min/median/max=`{group['core_length_min']}`/"
            f"`{group['core_length_median']}`/`{group['core_length_max']}`; "
            f"route_changed=`{group['n_route_changed']}`; "
            f"exceptions=`{group['record_exceptions'] or 'none'}`; "
            f">40% human-approved=`{group.get('n_large_trim_human_approved', '0')}`; "
            f"guard_rail_failures=`{group['guard_rail_failures']}`"
        )
    lines.extend(
        [
            "",
            "## Core-length distribution",
            "",
            "| metric | before | after |",
            "|---|---:|---:|",
            f"| min | `{stats['before_core_min']}` | `{stats['after_core_min']}` |",
            f"| median | `{stats['before_core_median']}` | `{stats['after_core_median']}` |",
            f"| max | `{stats['before_core_max']}` | `{stats['after_core_max']}` |",
            f"| <20 | `{stats['before_core_lt20']}` | `{stats['after_core_lt20']}` |",
            f"| 20–25 | `{stats['before_core_20_25']}` | `{stats['after_core_20_25']}` |",
            f"| 26–89 | `{stats['before_core_26_89']}` | `{stats['after_core_26_89']}` |",
            f"| 90–100 | `{stats['before_core_90_100']}` | `{stats['after_core_90_100']}` |",
            f"| >100 | `{stats['before_core_gt100']}` | `{stats['after_core_gt100']}` |",
            "",
            "## Transformation counts",
            "",
            f"- source-sequence corrections: `{stats['sequence_corrections']}`",
            f"- molecule-type overrides: `{stats['molecule_overrides']}`",
            f"- records actually trimmed: `{stats['records_trimmed']}`",
            f"- trimmed by group decision: `{stats['trimmed_by_group']}`",
            f"- trimmed by record-level override: `{stats['trimmed_by_record_override']}`",
            f"- cores changed: `{stats['core_length_changed']}`",
            f"- human-approved >40% trims: `{stats.get('large_trim_human_approved', 0)}`",
            f"- remaining guard-rail failures: `{stats['guard_rail_failures']}`",
            "",
            "## Invariants",
            "",
            f"- unlinked aptamers: `{stats['unlinked_aptamers']}`",
            f"- unlinked missing_target rejections: `{stats['unlinked_missing_target']}`",
            f"- authorised_for_s4: `{stats['authorised_for_s4']}`",
            f"- checkpoint_closed: `{stats['checkpoint_closed']}`",
            f"- S2 SHA-256: `{integrity.get('s2', '')}`",
            f"- S3 SHA-256: `{integrity.get('s3', '')}`",
            f"- raw interaction SHA-256: `{integrity.get('raw_interaction', '')}`",
            f"- raw aptamer SHA-256: `{integrity.get('raw_aptamer', '')}`",
            f"- raw protein SHA-256: `{integrity.get('raw_protein', '')}`",
            "",
            "## Pipeline stop",
            "",
            "CHECKPOINT-1 remains unapplied.",
            "S4 remains blocked.",
            "",
        ]
    )
    return "\n".join(lines)
