"""NCBI Nucleotide CHECKPOINT-1 application dry-run.

Uses the same ``apply_ncbi_nuc_checkpoint1_package`` transformation as a
future actual apply. Dry-run writes nothing that the pipeline treats as a
closed checkpoint or S4 handoff. Production reports are sequence-free.
Does not read ENA.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from adapters.aptadb_checkpoint1_review import AppliedRecordResult, _corpus_only
from adapters.ncbi_nuc_checkpoint1_review import (
    CONFIRM_CURRENT_DECISION,
    NcbiNucCheckpoint1ReviewError,
    apply_ncbi_nuc_checkpoint1_package,
    checkpoint_status_for_route,
)
from adapters.ncbi_nuc_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
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
    "native_id",
    "manual_decision",
    "consumed",
    "pre_review_route",
    "post_review_route",
    "post_molecule",
    "post_chemistry",
    "post_core_length",
    "primary_reason_after",
    "secondary_reasons_after",
)


@dataclass
class NcbiNucDryRunSimulation:
    """In-memory post-review NCBI Nucleotide corpus (no S4 fields)."""

    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked: list[dict[str, str]]
    preview_eligible: list[dict[str, str]]
    change_report: list[dict[str, str]]
    decision_audit: list[dict[str, str]]
    applied: list[AppliedRecordResult]
    route_changed_ids: tuple[str, ...] = ()
    nogo_reasons: tuple[str, ...] = ()
    stats: dict[str, int | str | bool] = field(default_factory=dict)


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def _blank(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _cause(*, manual_decision: str) -> str:
    if manual_decision == "drop":
        return "human_drop"
    return "keep"


def simulate_ncbi_nuc_checkpoint1_application(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
    decision_rows: Sequence[Mapping[str, str]],
    existing_rejection_rows: Sequence[Mapping[str, str]] = (),
    existing_parked_rows: Sequence[Mapping[str, str]] = (),
    bulk_confirmation: Mapping[str, str] | None = None,
    expected_source_rows: int | None = None,
    expected_reviewed_rows: int | None = None,
) -> NcbiNucDryRunSimulation:
    """Apply reviewed records in memory. Does not read ENA or GenBank text."""
    if len(canonical_rows) != len(decision_rows):
        raise NcbiNucCheckpoint1ReviewError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_source_rows is not None and len(canonical_rows) != expected_source_rows:
        raise NcbiNucCheckpoint1ReviewError(
            f"Canonical must have {expected_source_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    if expected_reviewed_rows is not None and len(queue_rows) != expected_reviewed_rows:
        raise NcbiNucCheckpoint1ReviewError(
            f"Active review must have {expected_reviewed_rows} rows; "
            f"got {len(queue_rows)}"
        )
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise NcbiNucCheckpoint1ReviewError("Duplicate canonical record_id")
    decision_by_id = {row["record_id"]: row for row in decision_rows}
    existing_rejections = {
        row["record_id"]: dict(row) for row in existing_rejection_rows
    }
    parked_by_id = {row["record_id"]: dict(row) for row in existing_parked_rows}

    applied, _report = apply_ncbi_nuc_checkpoint1_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        canonical_by_id=canonical_by_id,
        decision_by_id=decision_by_id,
        rejection_by_id=existing_rejections,
        park_by_id=parked_by_id,
        bulk_confirmation=bulk_confirmation,
    )
    applied_by_id = {item.record_id: item for item in applied}
    if len(applied_by_id) != len(queue_rows):
        raise NcbiNucCheckpoint1ReviewError(
            "Not every CHECKPOINT-1 review row was consumed"
        )

    preview_canonical: list[dict[str, str]] = []
    preview_decisions: list[dict[str, str]] = []
    preview_rejections: list[dict[str, str]] = []
    preview_parked: list[dict[str, str]] = []
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
            raise NcbiNucCheckpoint1ReviewError(
                f"Unconsumed NCBI CHECKPOINT-1 record {record_id!r}"
            )
        canonical = _corpus_only(applied_row.canonical)
        if canonical["sequence_raw"] != original_raw:
            raise NcbiNucCheckpoint1ReviewError(
                f"Apply mutated sequence_raw for {record_id!r}"
            )
        if canonical.get("sequence_full") != original_canonical.get("sequence_full", ""):
            nogo.append(f"sequence_full_changed:{record_id}")
        if canonical.get("sequence_core") != original_canonical.get("sequence_core", ""):
            nogo.append(f"sequence_core_changed:{record_id}")
        if canonical.get("sequence_core") != canonical.get("sequence_full"):
            nogo.append(f"core_ne_full:{record_id}")
        if canonical.get("molecule_type") != original_canonical.get("molecule_type", ""):
            nogo.append(f"molecule_changed:{record_id}")
        if canonical.get("chemistry") != original_canonical.get("chemistry", ""):
            nogo.append(f"chemistry_changed:{record_id}")
        if canonical.get("target_name_raw", "") != original_canonical.get(
            "target_name_raw", ""
        ):
            nogo.append(f"target_changed:{record_id}")
        if applied_row.sequence_corrected:
            nogo.append(f"sequence_corrected:{record_id}")
        if applied_row.molecule_overridden:
            nogo.append(f"molecule_overridden:{record_id}")
        if applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt:
            nogo.append(f"trim_applied:{record_id}")
        if applied_row.primary_route_after != applied_row.primary_route_before:
            route_changed.append(record_id)
            if effective_decision == CONFIRM_CURRENT_DECISION:
                nogo.append(f"keep_changed_route:{record_id}")
        for field_name in S3_FORBIDDEN_FIELDS:
            if canonical.get(field_name, ""):
                raise NcbiNucCheckpoint1ReviewError(
                    f"Apply populated S4 field {field_name!r} for {record_id!r}"
                )
        review = review_by_id[record_id]
        csv_decision = review.get("manual_decision", "")
        effective_decision = csv_decision or (
            "keep"
            if _blank(review.get("audit_only_row")).lower() == "true"
            else csv_decision
        )
        decision = _row(DECISION_COLUMNS, applied_row.decision)
        decision["notes"] = applied_row.notes
        decision["checkpoint_status"] = checkpoint_status_for_route(
            applied_row.primary_route_after
        )
        rejection = (
            dict(applied_row.rejection_row)
            if applied_row.rejection_row
            else existing_rejections.get(record_id)
        )
        park = dict(applied_row.park_row) if applied_row.park_row else None
        route = applied_row.primary_route_after
        change_report.append(
            {
                "record_id": record_id,
                "native_id": canonical.get("native_id", ""),
                "pre_review_route": applied_row.primary_route_before,
                "post_review_route": applied_row.primary_route_after,
                "manual_decision": csv_decision,
                "sequence_corrected": "false",
                "molecule_overridden": "false",
                "pre_molecule": original_canonical.get("molecule_type", ""),
                "post_molecule": canonical.get("molecule_type", ""),
                "pre_chemistry": original_canonical.get("chemistry", ""),
                "post_chemistry": canonical.get("chemistry", ""),
                "trim_action": review.get("manual_trim_action", ""),
                "trim_5p_nt": "",
                "trim_3p_nt": "",
                "pre_core_length": original_canonical.get("sequence_length_core", ""),
                "post_core_length": canonical.get("sequence_length_core", ""),
                "t_to_u_applied": original_canonical.get("t_to_u_applied", ""),
                "route_changed": "false",
                "primary_reason_before": original_decision.get("primary_reason", ""),
                "primary_reason_after": decision.get("primary_reason", ""),
                "cause": _cause(manual_decision=effective_decision),
            }
        )
        decision_audit.append(
            {
                "record_id": record_id,
                "native_id": canonical.get("native_id", ""),
                "manual_decision": csv_decision,
                "consumed": "true",
                "pre_review_route": applied_row.primary_route_before,
                "post_review_route": applied_row.primary_route_after,
                "post_molecule": canonical.get("molecule_type", ""),
                "post_chemistry": canonical.get("chemistry", ""),
                "post_core_length": canonical.get("sequence_length_core", ""),
                "primary_reason_after": decision.get("primary_reason", ""),
                "secondary_reasons_after": decision.get("secondary_reasons", ""),
            }
        )
        preview_canonical.append(canonical)
        preview_decisions.append(decision)
        if route == PRIMARY_ROUTE_REJECT:
            if rejection is None:
                raise NcbiNucCheckpoint1ReviewError(
                    f"technical_reject missing rejection row for {record_id!r}"
                )
            preview_rejections.append(_row(REJECTION_COLUMNS, rejection))
        elif route == PRIMARY_ROUTE_MOLECULE:
            if park is None:
                park = parked_by_id.get(record_id) or {
                    **decision,
                    "park_reason": decision.get(
                        "primary_reason", "molecule_type_unresolved"
                    ),
                }
            preview_parked.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            if canonical.get("molecule_type") != "RNA":
                nogo.append(f"eligible_non_rna:{record_id}")
            preview_eligible.append(_row(ELIGIBLE_COLUMNS, {**decision, **canonical}))
        else:
            raise NcbiNucCheckpoint1ReviewError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    if len(preview_canonical) != len(canonical_rows):
        raise NcbiNucCheckpoint1ReviewError("Reviewed corpus lost records")

    total = len(preview_canonical)
    reject_n = len(preview_rejections)
    parked_n = len(preview_parked)
    eligible_n = len(preview_eligible)
    if reject_n + parked_n + eligible_n != total:
        raise NcbiNucCheckpoint1ReviewError(
            "Applied routes do not reconcile to the NCBI Nucleotide source"
        )

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
    if edit_n:
        nogo.append("edit_decision")
    sequence_corrections = sum(1 for item in applied if item.sequence_corrected)
    molecule_overrides = sum(1 for item in applied if item.molecule_overridden)
    chemistry_overrides = sum(
        1
        for original in canonical_rows
        if original.get("chemistry", "") != applied_by_id[original["record_id"]].chemistry
    )
    trims = sum(
        1 for item in applied if item.applied_trim_5p_nt or item.applied_trim_3p_nt
    )
    if sequence_corrections:
        nogo.append("sequence_corrections")
    if molecule_overrides:
        nogo.append("molecule_overrides")
    if trims:
        nogo.append("trims")
    if route_changed:
        nogo.append("route_changed")

    before_routes = Counter(row.get("primary_route", "") for row in decision_rows)
    after_routes = Counter(row.get("primary_route", "") for row in preview_decisions)
    transition = Counter(
        (item.primary_route_before, item.primary_route_after) for item in applied
    )
    stats: dict[str, int | str | bool] = {
        "total_records": total,
        "reviewed_records": len(queue_rows),
        "unaffected_records": 0,
        "decisions_consumed": len(applied),
        "unconsumed_decisions": 0,
        "judgement_required": len(queue_rows) - audit_only_n,
        "human_keep_csv": keep_csv,
        "human_edit": edit_n,
        "human_drop": drop_n,
        "human_blank_audit_only": blank_n,
        "audit_only_rows": audit_only_n,
        "technical_rejects_after_review": reject_n,
        "parked_molecule_unresolved": parked_n,
        "technically_eligible": eligible_n,
        "projected_authorised_for_s4": eligible_n,
        "authorised_for_s4": 0,
        "records_trimmed": trims,
        "core_length_changed": 0,
        "route_changed": len(route_changed),
        "sequence_corrections": sequence_corrections,
        "molecule_overrides": molecule_overrides,
        "chemistry_overrides": chemistry_overrides,
        "target_corrections": 0,
        "guard_rail_failures": 0,
        "s4_started": False,
        "checkpoint_closed": False,
        "before_technically_eligible": int(before_routes.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "before_parked_molecule": int(before_routes.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "before_technical_rejects": int(before_routes.get(PRIMARY_ROUTE_REJECT, 0)),
        "after_technically_eligible": int(after_routes.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "after_parked_molecule": int(after_routes.get(PRIMARY_ROUTE_MOLECULE, 0)),
        "after_technical_rejects": int(after_routes.get(PRIMARY_ROUTE_REJECT, 0)),
        "transition_accept_to_eligible": int(
            transition.get((PRIMARY_ROUTE_ELIGIBLE, PRIMARY_ROUTE_ELIGIBLE), 0)
        ),
        "transition_park_to_park": int(
            transition.get((PRIMARY_ROUTE_MOLECULE, PRIMARY_ROUTE_MOLECULE), 0)
        ),
        "transition_reject_to_reject": int(
            transition.get((PRIMARY_ROUTE_REJECT, PRIMARY_ROUTE_REJECT), 0)
        ),
    }

    return NcbiNucDryRunSimulation(
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked=preview_parked,
        preview_eligible=preview_eligible,
        change_report=change_report,
        decision_audit=decision_audit,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        nogo_reasons=tuple(nogo),
        stats=stats,
    )


def serialise_ncbi_nuc_simulation_sequence_free(
    simulation: NcbiNucDryRunSimulation,
) -> bytes:
    """Determinism payload that omits sequence-bearing canonical rows."""
    import json

    chunks = [
        json.dumps(
            [
                {
                    key: value
                    for key, value in row.items()
                    if not key.startswith("sequence_")
                }
                for row in simulation.preview_canonical
            ],
            sort_keys=True,
            ensure_ascii=True,
        ),
        json.dumps(simulation.preview_decisions, sort_keys=True, ensure_ascii=True),
        json.dumps(
            [
                {k: v for k, v in row.items() if k != "sequence_raw"}
                for row in simulation.preview_rejections
            ],
            sort_keys=True,
            ensure_ascii=True,
        ),
        json.dumps(simulation.preview_parked, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.decision_audit, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.stats, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def format_dry_run_markdown(
    simulation: NcbiNucDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
) -> str:
    stats = simulation.stats
    nogo = simulation.nogo_reasons
    go = not nogo
    accession_lines = [
        f"- `{row['native_id']}`: `{row['pre_review_route']}` → "
        f"`{row['post_review_route']}` "
        f"({row['primary_reason_after']})"
        for row in simulation.change_report
    ]
    lines = [
        "# NCBI Nucleotide CHECKPOINT-1 application dry-run",
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
        "`manual_decision=keep` preserved the current proposed route.",
        "Canonical S1/S2/S3 outputs were not rewritten. CHECKPOINT-1 is not closed.",
        "Projected technically eligible records are **not** currently authorised for S4.",
        "Sequences are not printed here. ENA was not consulted.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- review index SHA-256: `{review_hashes.get('index', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        f"- recommendations SHA-256: `{review_hashes.get('rec_json', '')}`",
        "",
        "## Human decisions consumed",
        "",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- judgement-required: `{stats['judgement_required']}`",
        f"- judgement keep (CSV): `{stats['human_keep_csv']}`",
        f"- edit: `{stats['human_edit']}`",
        f"- drop: `{stats['human_drop']}`",
        f"- audit-only blank (bulk confirmed): `{stats['human_blank_audit_only']}`",
        f"- sequence corrections: `{stats['sequence_corrections']}`",
        f"- molecule overrides: `{stats['molecule_overrides']}`",
        f"- chemistry overrides: `{stats['chemistry_overrides']}`",
        f"- target corrections: `{stats['target_corrections']}`",
        f"- trims: `{stats['records_trimmed']}`",
        f"- route changes: `{stats['route_changed']}`",
        "",
        "## Projected routing (not currently authorised)",
        "",
        f"- total records: `{stats['total_records']}`",
        f"- technically eligible (projected): `{stats['technically_eligible']}`",
        f"- parked molecule_type_unresolved: `{stats['parked_molecule_unresolved']}`",
        f"- technical rejects: `{stats['technical_rejects_after_review']}`",
        f"- projected_authorised_for_s4: `{stats['projected_authorised_for_s4']}`",
        f"- current authoritative authorised_for_s4: `{stats['authorised_for_s4']}`",
        "",
        "```text",
        f"proposed accept -> final eligible = {stats['transition_accept_to_eligible']}",
        f"proposed park   -> final park     = {stats['transition_park_to_park']}",
        f"proposed reject -> final reject   = {stats['transition_reject_to_reject']}",
        "```",
        "",
        "## ACCESSION-level projected routes",
        "",
        *accession_lines,
        "",
        "## Integrity",
        "",
        f"- S1 SHA-256: `{integrity.get('s1', '')}`",
        f"- S1 sidecar SHA-256: `{integrity.get('sidecar', '')}`",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- S2 QC SHA-256: `{integrity.get('qc', '')}`",
        f"- S3 canonical SHA-256: `{integrity.get('s3', '')}`",
        f"- S3 decisions SHA-256: `{integrity.get('s3_decisions', '')}`",
        f"- S3 review SHA-256: `{integrity.get('s3_review', '')}`",
        f"- S3 local-detail SHA-256: `{integrity.get('s3_local', '')}`",
        "",
        "CHECKPOINT-1 is not closed.",
        "S4 remains blocked.",
        "",
    ]
    return "\n".join(lines)
