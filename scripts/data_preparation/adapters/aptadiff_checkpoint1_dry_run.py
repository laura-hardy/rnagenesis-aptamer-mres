"""AptaDiff CHECKPOINT-1 application dry-run and in-memory merge.

Uses the same ``apply_aptadiff_checkpoint1_package`` transformation as actual
apply. Dry-run writes nothing that the pipeline treats as a closed checkpoint
or S4 handoff. Production reports are sequence-free.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from adapters.aptadb_checkpoint1_review import AppliedRecordResult, _corpus_only
from adapters.aptadiff_checkpoint1_review import (
    AptaDiffCheckpoint1ReviewError,
    apply_aptadiff_checkpoint1_package,
    checkpoint_status_for_route,
)
from adapters.aptadiff_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS

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

EXPECTED_ROUTES: dict[str, dict[str, int]] = {
    "aptadiff_a": {
        "total_records": 13803,
        "parked_ssdna": 13802,
        "technical_rejects_after_review": 1,
        "technically_eligible": 0,
        "reviewed_records": 1,
    },
    "aptadiff_b": {
        "total_records": 11547,
        "parked_ssdna": 11532,
        "technical_rejects_after_review": 15,
        "technically_eligible": 0,
        "reviewed_records": 15,
    },
}


@dataclass
class AptaDiffDryRunSimulation:
    """In-memory post-review AptaDiff corpus (no S4 fields)."""

    source_key: str
    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked_ssdna: list[dict[str, str]]
    preview_eligible: list[dict[str, str]]
    change_report: list[dict[str, str]]
    decision_audit: list[dict[str, str]]
    applied: list[AppliedRecordResult]
    route_changed_ids: tuple[str, ...] = ()
    nogo_reasons: tuple[str, ...] = ()
    stats: dict[str, int | str | bool] = field(default_factory=dict)


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def simulate_aptadiff_checkpoint1_application(
    *,
    source_key: str,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
    decision_rows: Sequence[Mapping[str, str]],
    existing_rejection_rows: Sequence[Mapping[str, str]] = (),
    existing_parked_ssdna: Sequence[Mapping[str, str]] = (),
    bulk_confirmation: Mapping[str, str] | None = None,
    expected_source_rows: int | None = None,
    expected_reviewed_rows: int | None = None,
) -> AptaDiffDryRunSimulation:
    """Apply reviewed records in memory and merge onto the full source set."""
    if source_key not in {"aptadiff_a", "aptadiff_b"}:
        raise AptaDiffCheckpoint1ReviewError(
            f"Unknown AptaDiff source_key={source_key!r}"
        )
    if len(canonical_rows) != len(decision_rows):
        raise AptaDiffCheckpoint1ReviewError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_source_rows is not None and len(canonical_rows) != expected_source_rows:
        raise AptaDiffCheckpoint1ReviewError(
            f"Canonical must have {expected_source_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    if expected_reviewed_rows is not None and len(queue_rows) != expected_reviewed_rows:
        raise AptaDiffCheckpoint1ReviewError(
            f"Active review must have {expected_reviewed_rows} rows; "
            f"got {len(queue_rows)}"
        )
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise AptaDiffCheckpoint1ReviewError("Duplicate canonical record_id")
    decision_by_id = {row["record_id"]: row for row in decision_rows}
    existing_rejections = {
        row["record_id"]: dict(row) for row in existing_rejection_rows
    }
    parked_ssdna_by_id = {row["record_id"]: dict(row) for row in existing_parked_ssdna}

    applied, _report = apply_aptadiff_checkpoint1_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        canonical_by_id=canonical_by_id,
        decision_by_id=decision_by_id,
        rejection_by_id=existing_rejections,
        bulk_confirmation=bulk_confirmation,
    )
    applied_by_id = {item.record_id: item for item in applied}
    if len(applied_by_id) != len(queue_rows):
        raise AptaDiffCheckpoint1ReviewError(
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
    nogo: list[str] = []
    review_by_id = {row["record_id"]: row for row in queue_rows}

    for original_canonical, original_decision in zip(
        canonical_rows, decision_rows, strict=True
    ):
        record_id = original_canonical["record_id"]
        original_raw = original_canonical["sequence_raw"]
        applied_row = applied_by_id.get(record_id)
        if applied_row is None:
            canonical = _corpus_only(original_canonical)
            for field_name in S3_FORBIDDEN_FIELDS:
                canonical[field_name] = ""
            decision = _row(DECISION_COLUMNS, original_decision)
            route = decision["primary_route"]
            decision["checkpoint_status"] = checkpoint_status_for_route(route)
            rejection = existing_rejections.get(record_id)
            park = parked_ssdna_by_id.get(record_id)
            if route == PRIMARY_ROUTE_REJECT:
                nogo.append(f"no_review_reject:{record_id}")
            if original_decision.get("manual_review_required") == "true":
                nogo.append(f"unconsumed_review:{record_id}")
        else:
            canonical = _corpus_only(applied_row.canonical)
            if canonical["sequence_raw"] != original_raw:
                raise AptaDiffCheckpoint1ReviewError(
                    f"Apply mutated sequence_raw for {record_id!r}"
                )
            if applied_row.sequence_corrected:
                nogo.append(f"sequence_corrected:{record_id}")
            if applied_row.molecule_overridden:
                nogo.append(f"molecule_overridden:{record_id}")
            if applied_row.t_to_u_applied:
                nogo.append(f"t_to_u:{record_id}")
            if "N" not in (
                canonical.get("sequence_raw", "") + canonical.get("sequence_full", "")
            ).upper():
                nogo.append(f"n_removed:{record_id}")
            if applied_row.primary_route_after != PRIMARY_ROUTE_REJECT:
                nogo.append(f"reviewed_not_rejected:{record_id}")
            if applied_row.primary_reason != "ambiguous_bases":
                nogo.append(f"reason_changed:{record_id}")
            if applied_row.primary_route_after != applied_row.primary_route_before:
                route_changed.append(record_id)
                nogo.append(f"keep_changed_route:{record_id}")
            if canonical.get("molecule_type") not in {"ssDNA", "DNA"}:
                nogo.append(f"molecule_changed:{record_id}")
            decision = _row(DECISION_COLUMNS, applied_row.decision)
            decision["notes"] = applied_row.notes
            rejection = (
                dict(applied_row.rejection_row)
                if applied_row.rejection_row
                else existing_rejections.get(record_id)
            )
            park = None
            route = applied_row.primary_route_after
            for field_name in S3_FORBIDDEN_FIELDS:
                if canonical.get(field_name, ""):
                    raise AptaDiffCheckpoint1ReviewError(
                        f"Apply populated S4 field {field_name!r} for {record_id!r}"
                    )
            review = review_by_id[record_id]
            change_report.append(
                {
                    "record_id": record_id,
                    "native_id": canonical.get("native_id", ""),
                    "pre_review_route": applied_row.primary_route_before,
                    "post_review_route": applied_row.primary_route_after,
                    "manual_decision": review.get("manual_decision", ""),
                    "sequence_corrected": "false",
                    "molecule_overridden": "false",
                    "pre_molecule": original_canonical.get("molecule_type", ""),
                    "post_molecule": canonical.get("molecule_type", ""),
                    "pre_chemistry": original_canonical.get("chemistry", ""),
                    "post_chemistry": canonical.get("chemistry", ""),
                    "trim_action": "",
                    "trim_5p_nt": "",
                    "trim_3p_nt": "",
                    "pre_core_length": original_canonical.get(
                        "sequence_length_core", ""
                    ),
                    "post_core_length": canonical.get("sequence_length_core", ""),
                    "t_to_u_applied": "false",
                    "route_changed": "false",
                    "primary_reason_before": original_decision.get(
                        "primary_reason", ""
                    ),
                    "primary_reason_after": decision.get("primary_reason", ""),
                    "cause": "keep",
                }
            )
            decision_audit.append(
                {
                    "record_id": record_id,
                    "manual_decision": review.get("manual_decision", ""),
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
                raise AptaDiffCheckpoint1ReviewError(
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
            park_row = _row(PARK_COLUMNS, park)
            park_row["manual_review_required"] = decision.get(
                "manual_review_required", park_row.get("manual_review_required", "")
            )
            preview_parked_ssdna.append(park_row)
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            nogo.append(f"authorised:{record_id}")
            preview_eligible.append(_row(ELIGIBLE_COLUMNS, {**decision, **canonical}))
        else:
            raise AptaDiffCheckpoint1ReviewError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    if len(preview_canonical) != len(canonical_rows):
        raise AptaDiffCheckpoint1ReviewError("Reviewed corpus lost records")
    unconsumed = [
        row["record_id"] for row in queue_rows if row["record_id"] not in applied_by_id
    ]
    if unconsumed:
        raise AptaDiffCheckpoint1ReviewError(
            f"Unconsumed review decisions: {unconsumed[:5]}"
        )

    total = len(preview_canonical)
    reject_n = len(preview_rejections)
    parked_ssdna_n = len(preview_parked_ssdna)
    eligible_n = len(preview_eligible)
    if reject_n + parked_ssdna_n + eligible_n != total:
        raise AptaDiffCheckpoint1ReviewError(
            "Applied routes do not reconcile to the AptaDiff source"
        )
    csv_decisions = Counter(
        (row.get("manual_decision") or "").strip() for row in queue_rows
    )
    keep_n = int(csv_decisions.get("keep", 0))
    drop_n = int(csv_decisions.get("drop", 0))
    edit_n = int(csv_decisions.get("edit", 0))
    if drop_n or edit_n:
        nogo.append("non_keep_decision")
    if keep_n != len(queue_rows):
        nogo.append("keep_count_mismatch")
    sequence_corrections = sum(1 for item in applied if item.sequence_corrected)
    molecule_overrides = sum(1 for item in applied if item.molecule_overridden)
    if sequence_corrections:
        nogo.append("sequence_corrections")
    if molecule_overrides:
        nogo.append("molecule_overrides")
    if eligible_n:
        nogo.append("authorised_for_s4")
    production = EXPECTED_ROUTES.get(source_key)
    if expected_source_rows == (production or {}).get("total_records"):
        for key in (
            "parked_ssdna",
            "technical_rejects_after_review",
            "technically_eligible",
            "reviewed_records",
        ):
            expected = production[key]
            got = {
                "parked_ssdna": parked_ssdna_n,
                "technical_rejects_after_review": reject_n,
                "technically_eligible": eligible_n,
                "reviewed_records": len(queue_rows),
            }[key]
            if got != expected:
                nogo.append(f"{key}_mismatch")

    stats: dict[str, int | str | bool] = {
        "source_key": source_key,
        "total_records": total,
        "reviewed_records": len(queue_rows),
        "unaffected_records": total - len(queue_rows),
        "decisions_consumed": len(applied),
        "unconsumed_decisions": 0,
        "judgement_required": len(queue_rows),
        "human_keep": keep_n,
        "human_edit": edit_n,
        "human_drop": drop_n,
        "audit_only_rows": 0,
        "technical_rejects_after_review": reject_n,
        "parked_ssdna": parked_ssdna_n,
        "technically_eligible": eligible_n,
        "authorised_for_s4": 0,
        "records_trimmed": 0,
        "core_length_changed": 0,
        "route_changed": len(route_changed),
        "sequence_corrections": sequence_corrections,
        "molecule_overrides": molecule_overrides,
        "target_corrections": 0,
        "s4_started": False,
        "checkpoint_closed": False,
        "before_parked_ssdna": int(
            Counter(row.get("primary_route", "") for row in decision_rows).get(
                PRIMARY_ROUTE_SSDNA, 0
            )
        ),
        "before_technical_rejects": int(
            Counter(row.get("primary_route", "") for row in decision_rows).get(
                PRIMARY_ROUTE_REJECT, 0
            )
        ),
        "after_parked_ssdna": parked_ssdna_n,
        "after_technical_rejects": reject_n,
    }

    return AptaDiffDryRunSimulation(
        source_key=source_key,
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked_ssdna=preview_parked_ssdna,
        preview_eligible=preview_eligible,
        change_report=change_report,
        decision_audit=decision_audit,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        nogo_reasons=tuple(nogo),
        stats=stats,
    )


def serialise_aptadiff_simulation_sequence_free(
    simulation: AptaDiffDryRunSimulation,
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
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.decision_audit, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.stats, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def format_dry_run_markdown(
    simulation: AptaDiffDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
) -> str:
    stats = simulation.stats
    nogo = simulation.nogo_reasons
    go = not nogo
    label = "Dataset A" if simulation.source_key == "aptadiff_a" else "Dataset B"
    lines = [
        f"# AptaDiff {label} CHECKPOINT-1 application dry-run",
        "",
        DRY_RUN_BANNER,
        "",
        (
            "**GO for actual apply** (dry-run invariants held)."
            if go
            else "**NO-GO for actual apply.** " + "; ".join(nogo)
        ),
        "",
        "Human decisions were simulated through the real apply transformation.",
        "Canonical S1/S2/S3 outputs were not rewritten. CHECKPOINT-1 is not closed.",
        "No record is authorised for S4. Sequences are not printed here.",
        "Dataset-A replication was not built. Global S4 was not run.",
        "",
        "## Review inputs",
        "",
        f"- source_key: `{simulation.source_key}`",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        "",
        "## Human decisions consumed",
        "",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- keep (confirm current reject): `{stats['human_keep']}`",
        f"- edit: `{stats['human_edit']}`",
        f"- drop: `{stats['human_drop']}`",
        f"- sequence corrections: `{stats['sequence_corrections']}`",
        f"- molecule/chemistry overrides: `{stats['molecule_overrides']}`",
        f"- trim changes: `{stats['records_trimmed']}`",
        f"- target corrections: `{stats['target_corrections']}`",
        "",
        "## Projected routing",
        "",
        f"- total records: `{stats['total_records']}`",
        f"- parked ssDNA: `{stats['parked_ssdna']}`",
        f"- technical reject (ambiguous_bases): `{stats['technical_rejects_after_review']}`",
        f"- technically eligible / authorised_for_s4: `{stats['authorised_for_s4']}`",
        "",
        "## Integrity",
        "",
        f"- raw SHA-256: `{integrity.get('raw', '')}`",
        f"- S1 SHA-256: `{integrity.get('s1', '')}`",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- S3 SHA-256: `{integrity.get('s3', '')}`",
        "",
        "CHECKPOINT-1 is not closed.",
        "S4 remains blocked.",
        "",
    ]
    return "\n".join(lines)
