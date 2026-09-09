"""AptamerBase CHECKPOINT-1 application dry-run and in-memory merge.

Uses the same ``apply_aptamerbase_checkpoint1_package`` transformation as a
future real apply. Dry-run writes nothing that the pipeline treats as a
closed checkpoint or S4 handoff. Production reports are sequence-free.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from adapters.aptadb_checkpoint1_review import AppliedRecordResult, _corpus_only
from adapters.aptamerbase_checkpoint1_review import (
    MANUAL_REJECT_REASON,
    AptamerBaseCheckpoint1ReviewError,
    apply_aptamerbase_checkpoint1_package,
)
from adapters.aptamerbase_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
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
    "native_id",
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
    "pre_core_length",
    "post_core_length",
    "t_to_u_applied",
    "route_changed",
    "primary_reason_before",
    "primary_reason_after",
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
    "consumed",
    "pre_review_route",
    "post_review_route",
    "post_molecule",
    "post_chemistry",
    "post_core_length",
    "primary_reason_after",
)

CHEMISTRY_PARK_EXPECTATION: tuple[str, ...] = (
    "aptamerbase:0410",
    "aptamerbase:0473",
    "aptamerbase:0474",
    "aptamerbase:1152",
    "aptamerbase:1160",
    "aptamerbase:1161",
    "aptamerbase:1162",
)


@dataclass
class AptamerBaseDryRunSimulation:
    """In-memory post-review AptamerBase corpus (no S4 fields)."""

    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked_ssdna: list[dict[str, str]]
    preview_parked_molecule: list[dict[str, str]]
    preview_parked_chemistry: list[dict[str, str]]
    preview_parked_construct: list[dict[str, str]]
    preview_eligible: list[dict[str, str]]
    change_report: list[dict[str, str]]
    decision_audit: list[dict[str, str]]
    applied: list[AppliedRecordResult]
    route_changed_ids: tuple[str, ...] = ()
    nogo_reasons: tuple[str, ...] = ()
    stats: dict[str, int | str | bool] = field(default_factory=dict)


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def _int_len(value: str) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def _cause(
    *,
    manual_decision: str,
    sequence_corrected: bool,
    molecule_overridden: bool,
    trimmed: bool,
) -> str:
    if manual_decision == "drop":
        return "human_drop"
    if manual_decision == "keep":
        return "keep"
    parts: list[str] = []
    if sequence_corrected:
        parts.append("sequence_correction")
    if molecule_overridden:
        parts.append("molecule_or_chemistry_override")
    if trimmed:
        parts.append("trim")
    return "|".join(parts) if parts else "edit"


def simulate_aptamerbase_checkpoint1_application(
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
    existing_parked_molecule: Sequence[Mapping[str, str]] = (),
    existing_parked_chemistry: Sequence[Mapping[str, str]] = (),
    existing_parked_construct: Sequence[Mapping[str, str]] = (),
    expected_source_rows: int | None = 2128,
) -> AptamerBaseDryRunSimulation:
    """Apply reviewed records in memory and merge onto the full source set."""
    if len(canonical_rows) != len(decision_rows):
        raise AptamerBaseCheckpoint1ReviewError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_source_rows is not None and len(canonical_rows) != expected_source_rows:
        raise AptamerBaseCheckpoint1ReviewError(
            f"Canonical must have {expected_source_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise AptamerBaseCheckpoint1ReviewError("Duplicate canonical record_id")
    existing_rejections = {
        row["record_id"]: dict(row) for row in existing_rejection_rows
    }
    parked_ssdna_by_id = {row["record_id"]: dict(row) for row in existing_parked_ssdna}
    parked_molecule_by_id = {
        row["record_id"]: dict(row) for row in existing_parked_molecule
    }
    parked_chemistry_by_id = {
        row["record_id"]: dict(row) for row in existing_parked_chemistry
    }
    parked_construct_by_id = {
        row["record_id"]: dict(row) for row in existing_parked_construct
    }

    applied, _report = apply_aptamerbase_checkpoint1_package(
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
        raise AptamerBaseCheckpoint1ReviewError(
            "Not every CHECKPOINT-1 review row was consumed"
        )

    preview_canonical: list[dict[str, str]] = []
    preview_decisions: list[dict[str, str]] = []
    preview_rejections: list[dict[str, str]] = []
    preview_parked_ssdna: list[dict[str, str]] = []
    preview_parked_molecule: list[dict[str, str]] = []
    preview_parked_chemistry: list[dict[str, str]] = []
    preview_parked_construct: list[dict[str, str]] = []
    preview_eligible: list[dict[str, str]] = []
    change_report: list[dict[str, str]] = []
    decision_audit: list[dict[str, str]] = []
    route_changed: list[str] = []
    nogo: list[str] = []
    human_drops = 0
    keep_route_changes = 0
    n_trimmed = 0
    n_core_changed = 0
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
            park = (
                parked_ssdna_by_id.get(record_id)
                or parked_molecule_by_id.get(record_id)
                or parked_chemistry_by_id.get(record_id)
                or parked_construct_by_id.get(record_id)
            )
            route = decision["primary_route"]
        else:
            canonical = _corpus_only(applied_row.canonical)
            if canonical["sequence_raw"] != original_raw:
                raise AptamerBaseCheckpoint1ReviewError(
                    f"Apply mutated sequence_raw for {record_id!r}"
                )
            review = review_by_id[record_id]
            csv_decision = review.get("manual_decision", "")
            effective_decision = csv_decision or (
                "keep"
                if _blank_audit_keep(review, bulk_confirmation)
                else csv_decision
            )
            if applied_row.primary_route_after != applied_row.primary_route_before:
                route_changed.append(record_id)
                if effective_decision == "keep":
                    keep_route_changes += 1
                    nogo.append(f"keep_changed_route:{record_id}")
            if applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt:
                n_trimmed += 1
            if _int_len(canonical["sequence_length_core"]) != _int_len(
                original_canonical.get("sequence_length_core", "")
            ):
                n_core_changed += 1
            if effective_decision == "drop":
                human_drops += 1
                if applied_row.primary_route_after != PRIMARY_ROUTE_REJECT:
                    nogo.append(f"drop_not_rejected:{record_id}")
                if applied_row.primary_reason != MANUAL_REJECT_REASON:
                    nogo.append(f"drop_missing_manual_reject:{record_id}")
            decision = _row(DECISION_COLUMNS, applied_row.decision)
            decision["notes"] = applied_row.notes
            rejection = (
                dict(applied_row.rejection_row)
                if applied_row.rejection_row
                else existing_rejections.get(record_id)
            )
            park = dict(applied_row.park_row) if applied_row.park_row else None
            route = applied_row.primary_route_after
            for field_name in S3_FORBIDDEN_FIELDS:
                if canonical.get(field_name, ""):
                    raise AptamerBaseCheckpoint1ReviewError(
                        f"Apply populated S4 field {field_name!r} for {record_id!r}"
                    )
            change_report.append(
                {
                    "record_id": record_id,
                    "native_id": canonical.get("native_id", ""),
                    "pre_review_route": applied_row.primary_route_before,
                    "post_review_route": applied_row.primary_route_after,
                    "manual_decision": csv_decision,
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
                    "trim_action": review.get("manual_trim_action", ""),
                    "trim_5p_nt": str(applied_row.applied_trim_5p_nt)
                    if (applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt)
                    else "",
                    "trim_3p_nt": str(applied_row.applied_trim_3p_nt)
                    if (applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt)
                    else "",
                    "pre_core_length": original_canonical.get(
                        "sequence_length_core", ""
                    ),
                    "post_core_length": canonical.get("sequence_length_core", ""),
                    "t_to_u_applied": (
                        "true" if applied_row.t_to_u_applied else "false"
                    ),
                    "route_changed": (
                        "true"
                        if applied_row.primary_route_after
                        != applied_row.primary_route_before
                        else "false"
                    ),
                    "primary_reason_before": original_decision.get(
                        "primary_reason", ""
                    ),
                    "primary_reason_after": decision.get("primary_reason", ""),
                    "cause": _cause(
                        manual_decision=effective_decision,
                        sequence_corrected=applied_row.sequence_corrected,
                        molecule_overridden=applied_row.molecule_overridden,
                        trimmed=bool(
                            applied_row.applied_trim_5p_nt
                            or applied_row.applied_trim_3p_nt
                        ),
                    ),
                }
            )
            decision_audit.append(
                {
                    "record_id": record_id,
                    "manual_decision": csv_decision,
                    "consumed": "true",
                    "pre_review_route": applied_row.primary_route_before,
                    "post_review_route": applied_row.primary_route_after,
                    "post_molecule": canonical.get("molecule_type", ""),
                    "post_chemistry": canonical.get("chemistry", ""),
                    "post_core_length": canonical.get("sequence_length_core", ""),
                    "primary_reason_after": decision.get("primary_reason", ""),
                }
            )

        preview_canonical.append(canonical)
        preview_decisions.append(decision)
        if route == PRIMARY_ROUTE_REJECT:
            if rejection is None:
                raise AptamerBaseCheckpoint1ReviewError(
                    f"technical_reject missing rejection row for {record_id!r}"
                )
            preview_rejections.append(_row(REJECTION_COLUMNS, rejection))
        elif route == PRIMARY_ROUTE_SSDNA:
            if park is None:
                park = parked_ssdna_by_id.get(record_id) or _row(
                    PARK_COLUMNS,
                    {
                        **decision,
                        "park_reason": decision.get("primary_reason", "ssdna_parked"),
                    },
                )
            preview_parked_ssdna.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_MOLECULE:
            if park is None:
                park = parked_molecule_by_id.get(record_id) or _row(
                    PARK_COLUMNS,
                    {
                        **decision,
                        "park_reason": decision.get("primary_reason", ""),
                    },
                )
            preview_parked_molecule.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_CHEMISTRY_REVIEW:
            if park is None:
                park = parked_chemistry_by_id.get(record_id) or _row(
                    PARK_COLUMNS,
                    {
                        **decision,
                        "park_reason": decision.get("primary_reason", ""),
                    },
                )
            preview_parked_chemistry.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_CONSTRUCT:
            if park is None:
                park = parked_construct_by_id.get(record_id) or _row(
                    PARK_COLUMNS,
                    {
                        **decision,
                        "park_reason": decision.get("primary_reason", ""),
                    },
                )
            preview_parked_construct.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            preview_eligible.append(_row(ELIGIBLE_COLUMNS, {**decision, **canonical}))
        else:
            raise AptamerBaseCheckpoint1ReviewError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    if len(preview_canonical) != len(canonical_rows):
        raise AptamerBaseCheckpoint1ReviewError("Reviewed corpus lost records")
    unconsumed = [
        row["record_id"] for row in queue_rows if row["record_id"] not in applied_by_id
    ]
    if unconsumed:
        raise AptamerBaseCheckpoint1ReviewError(
            f"Unconsumed review decisions: {unconsumed[:5]}"
        )

    total = len(preview_canonical)
    reject_n = len(preview_rejections)
    parked_ssdna_n = len(preview_parked_ssdna)
    parked_mol_n = len(preview_parked_molecule)
    parked_chem_n = len(preview_parked_chemistry)
    parked_construct_n = len(preview_parked_construct)
    eligible_n = len(preview_eligible)
    if (
        reject_n
        + parked_ssdna_n
        + parked_mol_n
        + parked_chem_n
        + parked_construct_n
        + eligible_n
        != total
    ):
        raise AptamerBaseCheckpoint1ReviewError(
            "Applied routes do not reconcile to the AptamerBase source"
        )

    before_routes = Counter(row.get("primary_route", "") for row in decision_rows)
    after_routes = Counter(row.get("primary_route", "") for row in preview_decisions)
    reviewed_before = Counter(item.primary_route_before for item in applied)
    reviewed_after = Counter(item.primary_route_after for item in applied)
    csv_decisions = Counter(
        (row.get("manual_decision") or "").strip() for row in queue_rows
    )
    keep_csv = int(csv_decisions.get("keep", 0))
    drop_n = int(csv_decisions.get("drop", 0))
    edit_n = int(csv_decisions.get("edit", 0))
    blank_n = int(csv_decisions.get("", 0))
    audit_only_n = sum(
        1
        for row in queue_rows
        if (row.get("audit_only_row") or "").strip().lower() == "true"
    )
    judgement_n = len(queue_rows) - audit_only_n

    transition = Counter(
        (item.primary_route_before, item.primary_route_after) for item in applied
    )
    edit_after = Counter(
        item.primary_route_after
        for item in applied
        if review_by_id[item.record_id].get("manual_decision") == "edit"
    )

    chemistry_park_ids = tuple(
        sorted(
            item.record_id
            for item in applied
            if item.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW
        )
    )
    if expected_source_rows == 2128 and chemistry_park_ids != CHEMISTRY_PARK_EXPECTATION:
        # Diagnostic for the live 2128-row corpus, not hardcoded routing.
        extra = sorted(set(chemistry_park_ids) - set(CHEMISTRY_PARK_EXPECTATION))
        missing = sorted(set(CHEMISTRY_PARK_EXPECTATION) - set(chemistry_park_ids))
        if extra or missing:
            nogo.append(
                "chemistry_park_set_differs:"
                + f"extra={','.join(extra) or 'none'};"
                + f"missing={','.join(missing) or 'none'}"
            )

    for item in applied:
        if item.primary_route_after != PRIMARY_ROUTE_ELIGIBLE:
            continue
        if item.canonical.get("source_object_type") not in {"", "aptamer"}:
            if (s2_qc_by_id.get(item.record_id, {}).get("source_object_type") or "") not in {
                "",
                "aptamer",
            } and (item.decision.get("source_object_type") or "") != "aptamer":
                nogo.append(f"eligible_non_aptamer:{item.record_id}")
        if item.molecule_type != "RNA":
            nogo.append(f"eligible_non_rna:{item.record_id}")
        if item.chemistry not in {"RNA", "2F-RNA", "2NH2-RNA", "2OMe-RNA", "mixed"}:
            nogo.append(f"eligible_chemistry:{item.record_id}")
        core = item.sequence_length_core
        if not (20 <= core <= 100):
            nogo.append(f"eligible_length:{item.record_id}")

    stats: dict[str, int | str | bool] = {
        "total_records": total,
        "reviewed_records": len(queue_rows),
        "unaffected_records": total - len(queue_rows),
        "decisions_consumed": len(applied),
        "unconsumed_decisions": 0,
        "judgement_required": judgement_n,
        "human_keep_csv": keep_csv,
        "human_edit": edit_n,
        "human_drop": drop_n,
        "human_blank_audit_only": blank_n,
        "audit_only_rows": audit_only_n,
        "human_reviewed_drops": human_drops,
        "keep_routes_unchanged": (keep_csv + audit_only_n) - keep_route_changes
        if keep_csv == 0
        else keep_csv - keep_route_changes,
        "keep_unexpected_route_changes": keep_route_changes,
        "technical_rejects_after_review": reject_n,
        "manual_rejects": human_drops,
        "parked_ssdna": parked_ssdna_n,
        "parked_molecule_unresolved": parked_mol_n,
        "parked_chemistry_review": parked_chem_n,
        "parked_construct_review": parked_construct_n,
        "technically_eligible": eligible_n,
        "authorised_for_s4": 0,
        "records_trimmed": n_trimmed,
        "core_length_changed": n_core_changed,
        "route_changed": len(route_changed),
        "sequence_corrections": sum(1 for item in applied if item.sequence_corrected),
        "molecule_overrides": sum(1 for item in applied if item.molecule_overridden),
        "s4_started": False,
        "checkpoint_closed": False,
        "before_technically_eligible": int(before_routes.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "before_parked_ssdna": int(before_routes.get(PRIMARY_ROUTE_SSDNA, 0)),
        "before_parked_molecule": int(before_routes.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "before_parked_chemistry_review": int(
            before_routes.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "before_parked_construct": int(before_routes.get(PRIMARY_ROUTE_CONSTRUCT, 0)),
        "before_technical_rejects": int(before_routes.get(PRIMARY_ROUTE_REJECT, 0)),
        "after_technically_eligible": int(after_routes.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "after_parked_ssdna": int(after_routes.get(PRIMARY_ROUTE_SSDNA, 0)),
        "after_parked_molecule": int(after_routes.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "after_parked_chemistry_review": int(
            after_routes.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "after_parked_construct": int(after_routes.get(PRIMARY_ROUTE_CONSTRUCT, 0)),
        "after_technical_rejects": int(after_routes.get(PRIMARY_ROUTE_REJECT, 0)),
        "reviewed_before_eligible": int(reviewed_before.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "reviewed_before_ssdna": int(reviewed_before.get(PRIMARY_ROUTE_SSDNA, 0)),
        "reviewed_before_molecule": int(reviewed_before.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "reviewed_before_chemistry": int(
            reviewed_before.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "reviewed_before_construct": int(reviewed_before.get(PRIMARY_ROUTE_CONSTRUCT, 0)),
        "reviewed_before_reject": int(reviewed_before.get(PRIMARY_ROUTE_REJECT, 0)),
        "reviewed_after_eligible": int(reviewed_after.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "reviewed_after_ssdna": int(reviewed_after.get(PRIMARY_ROUTE_SSDNA, 0)),
        "reviewed_after_molecule": int(reviewed_after.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "reviewed_after_chemistry": int(
            reviewed_after.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "reviewed_after_construct": int(reviewed_after.get(PRIMARY_ROUTE_CONSTRUCT, 0)),
        "reviewed_after_reject": int(reviewed_after.get(PRIMARY_ROUTE_REJECT, 0)),
        "edit_to_eligible": int(edit_after.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "edit_to_ssdna": int(edit_after.get(PRIMARY_ROUTE_SSDNA, 0)),
        "edit_to_molecule": int(edit_after.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "edit_to_chemistry": int(edit_after.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)),
        "edit_to_construct": int(edit_after.get(PRIMARY_ROUTE_CONSTRUCT, 0)),
        "edit_to_reject": int(edit_after.get(PRIMARY_ROUTE_REJECT, 0)),
    }
    for (pre, post), count in sorted(transition.items()):
        stats[f"transition_{pre}__{post}"] = int(count)

    if keep_route_changes:
        nogo.append("keep_changed_route")
    if human_drops != drop_n:
        nogo.append("drop_count_mismatch")
    if total != (expected_source_rows or total):
        nogo.append("source_count_mismatch")
    if expected_source_rows == 2128:
        if parked_mol_n != 0:
            nogo.append("molecule_unresolved_remaining")
        if parked_construct_n != 0:
            nogo.append("construct_unresolved_remaining")

    return AptamerBaseDryRunSimulation(
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked_ssdna=preview_parked_ssdna,
        preview_parked_molecule=preview_parked_molecule,
        preview_parked_chemistry=preview_parked_chemistry,
        preview_parked_construct=preview_parked_construct,
        preview_eligible=preview_eligible,
        change_report=change_report,
        decision_audit=decision_audit,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        nogo_reasons=tuple(nogo),
        stats=stats,
    )


def _blank_audit_keep(
    review: Mapping[str, str],
    bulk_confirmation: Mapping[str, str] | None,
) -> bool:
    from adapters.aptadb_checkpoint1_review import _blank, is_audit_only_row

    if not is_audit_only_row(review):
        return False
    if _blank(review.get("manual_decision")):
        return False
    return bool(
        bulk_confirmation is not None
        and _blank(bulk_confirmation.get("confirm")).lower() == "true"
    )


def serialise_aptamerbase_simulation_sequence_free(
    simulation: AptamerBaseDryRunSimulation,
) -> bytes:
    """Determinism payload that omits sequence-bearing canonical rows."""
    import json

    chunks = [
        json.dumps(simulation.preview_decisions, sort_keys=True, ensure_ascii=True),
        json.dumps(
            [
                {k: v for k, v in row.items() if k != "sequence_raw"}
                for row in simulation.preview_rejections
            ],
            sort_keys=True,
            ensure_ascii=True,
        ),
        json.dumps(simulation.preview_parked_ssdna, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_parked_molecule, sort_keys=True, ensure_ascii=True),
        json.dumps(
            simulation.preview_parked_chemistry, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(
            simulation.preview_parked_construct, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.decision_audit, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.stats, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def format_dry_run_markdown(
    simulation: AptamerBaseDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
) -> str:
    stats = simulation.stats
    nogo = simulation.nogo_reasons
    go = not nogo
    lines = [
        "# AptamerBase CHECKPOINT-1 application dry-run",
        "",
        DRY_RUN_BANNER,
        "",
        (
            "**GO for a later actual-apply milestone** (dry-run invariants held)."
            if go
            else "**NO-GO for actual apply.** " + "; ".join(nogo)
        ),
        "",
        "Human decisions were simulated through the real apply transformation.",
        "Canonical S2/S3 outputs were not rewritten. CHECKPOINT-1 is not closed.",
        "No record is authorised for S4. Sequences are not printed here.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- group review SHA-256: `{review_hashes.get('groups', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        "",
        "## Human decisions consumed",
        "",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- judgement-required: `{stats['judgement_required']}`",
        f"- judgement keep (CSV): `{stats['human_keep_csv']}`",
        f"- edit: `{stats['human_edit']}`",
        f"- drop: `{stats['human_drop']}`",
        f"- audit-only blank (bulk confirmed): `{stats['human_blank_audit_only']}`",
        f"- decisions consumed: `{stats['decisions_consumed']}`",
        "",
        "## 291-row route transition",
        "",
        f"- pre technically eligible: `{stats['reviewed_before_eligible']}`",
        f"- pre parked ssDNA: `{stats['reviewed_before_ssdna']}`",
        f"- pre molecule-unresolved: `{stats['reviewed_before_molecule']}`",
        f"- pre chemistry-review park: `{stats['reviewed_before_chemistry']}`",
        f"- pre construct park: `{stats['reviewed_before_construct']}`",
        f"- pre technical reject: `{stats['reviewed_before_reject']}`",
        f"- post technically eligible: `{stats['reviewed_after_eligible']}`",
        f"- post parked ssDNA: `{stats['reviewed_after_ssdna']}`",
        f"- post molecule-unresolved: `{stats['reviewed_after_molecule']}`",
        f"- post chemistry-review park: `{stats['reviewed_after_chemistry']}`",
        f"- post construct park: `{stats['reviewed_after_construct']}`",
        f"- post technical reject (includes manual_reject): "
        f"`{stats['reviewed_after_reject']}`",
        "",
        "### keep / bulk audit",
        "",
        f"- CSV keep: `{stats['human_keep_csv']}`",
        f"- audit-only bulk keep: `{stats['human_blank_audit_only']}`",
        f"- unexpected route changes: `{stats['keep_unexpected_route_changes']}`",
        "",
        "### drop",
        "",
        f"- count: `{stats['human_drop']}`",
        f"- final route: `{PRIMARY_ROUTE_REJECT}` / `{MANUAL_REJECT_REASON}`",
        "",
        "### edit",
        "",
        f"- count: `{stats['human_edit']}`",
        f"- to technically eligible: `{stats['edit_to_eligible']}`",
        f"- to parked ssDNA: `{stats['edit_to_ssdna']}`",
        f"- to molecule-unresolved: `{stats['edit_to_molecule']}`",
        f"- to chemistry-review park: `{stats['edit_to_chemistry']}`",
        f"- to construct park: `{stats['edit_to_construct']}`",
        f"- to technical reject: `{stats['edit_to_reject']}`",
        "",
        "## Full 2128-row projected reconciliation",
        "",
        f"- total source records: `{stats['total_records']}`",
        f"- unaffected by CHECKPOINT: `{stats['unaffected_records']}`",
        f"- post-review technically eligible: `{stats['technically_eligible']}`",
        f"- post-review parked ssDNA: `{stats['parked_ssdna']}`",
        f"- post-review molecule-unresolved: `{stats['parked_molecule_unresolved']}`",
        f"- post-review chemistry-review parks: `{stats['parked_chemistry_review']}`",
        f"- post-review construct parks: `{stats['parked_construct_review']}`",
        f"- all technical rejects after review: "
        f"`{stats['technical_rejects_after_review']}`",
        f"- records trimmed: `{stats['records_trimmed']}`",
        "",
        "Reconciliation: technically eligible + parked ssDNA + molecule +",
        "chemistry + construct + technical rejects = 2128.",
        "",
        "## Integrity",
        "",
        f"- S1 SHA-256: `{integrity.get('s1', '')}`",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
        f"- raw SHA-256: `{integrity.get('raw', '')}`",
        f"- deterministic rerun: `{integrity.get('deterministic_ok', '')}`",
        "",
        "## Pipeline stop",
        "",
        "CHECKPOINT-1 remains open and unapplied.",
        "No AptamerBase record is authorised for global S4.",
        "Global S4 has not been run.",
        "",
    ]
    return "\n".join(lines)
