"""AptaIndex CHECKPOINT-1 application dry-run and in-memory merge.

Uses the same ``apply_aptaindex_checkpoint1_package`` transformation as a
future real apply. Dry-run writes nothing that the pipeline treats as a
closed checkpoint or S4 handoff. Production reports are sequence-free.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from adapters.aptadb_checkpoint1_review import AppliedRecordResult, _corpus_only
from adapters.aptaindex_checkpoint1_review import (
    MANUAL_REJECT_REASON,
    AptaIndexCheckpoint1ReviewError,
    apply_aptaindex_checkpoint1_package,
)
from adapters.aptaindex_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
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
    "pre_mapping_class",
    "post_mapping_class",
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
    "mapping_class",
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

SPECIAL_RECORD_IDS: tuple[str, ...] = (
    "aptaindex:0412",
    "aptaindex:0518",
    "aptaindex:0519",
    "aptaindex:0492",
    "aptaindex:0753",
    "aptaindex:0960",
    "aptaindex:0754",
    "aptaindex:0610",
    "aptaindex:0372",
    "aptaindex:0938",
    "aptaindex:0187",
    "aptaindex:0605",
)

EDIT_CHEMISTRY_CLASSES: tuple[str, ...] = (
    "RNA",
    "2F-RNA",
    "2NH2-RNA",
    "2OMe-RNA",
    "mixed",
    "DNA",
)


@dataclass
class AptaIndexDryRunSimulation:
    """In-memory post-review AptaIndex corpus (no S4 fields)."""

    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked_ssdna: list[dict[str, str]]
    preview_parked_chemistry: list[dict[str, str]]
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


def simulate_aptaindex_checkpoint1_application(
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
    existing_parked_chemistry: Sequence[Mapping[str, str]] = (),
    expected_source_rows: int | None = 1050,
) -> AptaIndexDryRunSimulation:
    """Apply reviewed records in memory and merge onto the full source set."""
    if len(canonical_rows) != len(decision_rows):
        raise AptaIndexCheckpoint1ReviewError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_source_rows is not None and len(canonical_rows) != expected_source_rows:
        raise AptaIndexCheckpoint1ReviewError(
            f"Canonical must have {expected_source_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise AptaIndexCheckpoint1ReviewError("Duplicate canonical record_id")
    existing_rejections = {
        row["record_id"]: dict(row) for row in existing_rejection_rows
    }
    parked_ssdna_by_id = {row["record_id"]: dict(row) for row in existing_parked_ssdna}
    parked_chemistry_by_id = {
        row["record_id"]: dict(row) for row in existing_parked_chemistry
    }

    applied, _report = apply_aptaindex_checkpoint1_package(
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
        raise AptaIndexCheckpoint1ReviewError(
            "Not every CHECKPOINT-1 review row was consumed"
        )

    preview_canonical: list[dict[str, str]] = []
    preview_decisions: list[dict[str, str]] = []
    preview_rejections: list[dict[str, str]] = []
    preview_parked_ssdna: list[dict[str, str]] = []
    preview_parked_chemistry: list[dict[str, str]] = []
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
            park = parked_ssdna_by_id.get(record_id) or parked_chemistry_by_id.get(
                record_id
            )
            route = decision["primary_route"]
        else:
            canonical = _corpus_only(applied_row.canonical)
            if canonical["sequence_raw"] != original_raw:
                raise AptaIndexCheckpoint1ReviewError(
                    f"Apply mutated sequence_raw for {record_id!r}"
                )
            review = review_by_id[record_id]
            if applied_row.primary_route_after != applied_row.primary_route_before:
                route_changed.append(record_id)
                if review.get("manual_decision") == "keep":
                    keep_route_changes += 1
                    nogo.append(f"keep_changed_route:{record_id}")
            if applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt:
                n_trimmed += 1
            if _int_len(canonical["sequence_length_core"]) != _int_len(
                original_canonical.get("sequence_length_core", "")
            ):
                n_core_changed += 1
            if review.get("manual_decision") == "drop":
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
                    raise AptaIndexCheckpoint1ReviewError(
                        f"Apply populated S4 field {field_name!r} for {record_id!r}"
                    )
            post_mapping = (
                applied_row.decision.get("mapping_class", "")
                or s2_qc_by_id.get(record_id, {}).get("mapping_class", "")
            )
            change_report.append(
                {
                    "record_id": record_id,
                    "native_id": canonical.get("native_id", ""),
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
                    "pre_mapping_class": s2_qc_by_id.get(record_id, {}).get(
                        "mapping_class", ""
                    ),
                    "post_mapping_class": post_mapping,
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
                raise AptaIndexCheckpoint1ReviewError(
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
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            preview_eligible.append(_row(ELIGIBLE_COLUMNS, {**decision, **canonical}))
        else:
            raise AptaIndexCheckpoint1ReviewError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    if len(preview_canonical) != len(canonical_rows):
        raise AptaIndexCheckpoint1ReviewError("Reviewed corpus lost records")
    unconsumed = [
        row["record_id"] for row in queue_rows if row["record_id"] not in applied_by_id
    ]
    if unconsumed:
        raise AptaIndexCheckpoint1ReviewError(
            f"Unconsumed review decisions: {unconsumed[:5]}"
        )

    total = len(preview_canonical)
    reject_n = len(preview_rejections)
    parked_ssdna_n = len(preview_parked_ssdna)
    parked_chem_n = len(preview_parked_chemistry)
    eligible_n = len(preview_eligible)
    if reject_n + parked_ssdna_n + parked_chem_n + eligible_n != total:
        raise AptaIndexCheckpoint1ReviewError(
            "Applied routes do not reconcile to the AptaIndex source"
        )

    before_routes = Counter(row.get("primary_route", "") for row in decision_rows)
    after_routes = Counter(row.get("primary_route", "") for row in preview_decisions)
    reviewed_before = Counter(item.primary_route_before for item in applied)
    reviewed_after = Counter(item.primary_route_after for item in applied)
    decisions = Counter(
        (row.get("manual_decision") or "").strip() for row in queue_rows
    )
    keep_n = int(decisions.get("keep", 0))
    drop_n = int(decisions.get("drop", 0))
    edit_n = int(decisions.get("edit", 0))
    if keep_n + drop_n + edit_n != len(queue_rows):
        nogo.append("human_decision_count_mismatch")

    transition = Counter(
        (item.primary_route_before, item.primary_route_after) for item in applied
    )
    edit_after = Counter(
        item.primary_route_after
        for item in applied
        if review_by_id[item.record_id].get("manual_decision") == "edit"
    )
    edit_chem_routes: dict[str, Counter[str]] = {
        chem: Counter() for chem in EDIT_CHEMISTRY_CLASSES
    }
    for item in applied:
        if review_by_id[item.record_id].get("manual_decision") != "edit":
            continue
        chem = item.chemistry if item.chemistry != "DNA" else "DNA"
        if item.molecule_type in {"ssDNA", "DNA"}:
            chem = "DNA"
        if chem in edit_chem_routes:
            edit_chem_routes[chem][item.primary_route_after] += 1

    technical_reject_after_edit = sum(
        1
        for item in applied
        if review_by_id[item.record_id].get("manual_decision") == "edit"
        and item.primary_route_after == PRIMARY_ROUTE_REJECT
        and item.primary_reason != MANUAL_REJECT_REASON
    )

    stats: dict[str, int | str | bool] = {
        "total_records": total,
        "reviewed_records": len(queue_rows),
        "unaffected_records": total - len(queue_rows),
        "decisions_consumed": len(applied),
        "unconsumed_decisions": 0,
        "human_keep": keep_n,
        "human_edit": edit_n,
        "human_drop": drop_n,
        "human_reviewed_drops": human_drops,
        "keep_routes_unchanged": keep_n - keep_route_changes,
        "keep_unexpected_route_changes": keep_route_changes,
        "technical_rejects_after_review": reject_n,
        "manual_rejects": human_drops,
        "technical_rejects_after_edit": technical_reject_after_edit,
        "automatic_rejects_unaffected": reject_n
        - human_drops
        - technical_reject_after_edit,
        "parked_ssdna": parked_ssdna_n,
        "parked_chemistry_review": parked_chem_n,
        "parked_non_protein": 0,
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
        "before_parked_chemistry_review": int(
            before_routes.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "before_technical_rejects": int(before_routes.get(PRIMARY_ROUTE_REJECT, 0)),
        "after_technically_eligible": int(after_routes.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "after_parked_ssdna": int(after_routes.get(PRIMARY_ROUTE_SSDNA, 0)),
        "after_parked_chemistry_review": int(
            after_routes.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "after_technical_rejects": int(after_routes.get(PRIMARY_ROUTE_REJECT, 0)),
        "reviewed_before_eligible": int(reviewed_before.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "reviewed_before_ssdna": int(reviewed_before.get(PRIMARY_ROUTE_SSDNA, 0)),
        "reviewed_before_chemistry": int(
            reviewed_before.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "reviewed_before_reject": int(reviewed_before.get(PRIMARY_ROUTE_REJECT, 0)),
        "reviewed_after_eligible": int(reviewed_after.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "reviewed_after_ssdna": int(reviewed_after.get(PRIMARY_ROUTE_SSDNA, 0)),
        "reviewed_after_chemistry": int(
            reviewed_after.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        ),
        "reviewed_after_reject": int(reviewed_after.get(PRIMARY_ROUTE_REJECT, 0)),
        "edit_to_eligible": int(edit_after.get(PRIMARY_ROUTE_ELIGIBLE, 0)),
        "edit_to_ssdna": int(edit_after.get(PRIMARY_ROUTE_SSDNA, 0)),
        "edit_to_chemistry": int(edit_after.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)),
        "edit_to_reject": int(edit_after.get(PRIMARY_ROUTE_REJECT, 0)),
    }
    for chem, counts in edit_chem_routes.items():
        stats[f"edit_{chem}_eligible"] = int(counts.get(PRIMARY_ROUTE_ELIGIBLE, 0))
        stats[f"edit_{chem}_ssdna"] = int(counts.get(PRIMARY_ROUTE_SSDNA, 0))
        stats[f"edit_{chem}_chemistry"] = int(
            counts.get(PRIMARY_ROUTE_CHEMISTRY_REVIEW, 0)
        )
        stats[f"edit_{chem}_reject"] = int(counts.get(PRIMARY_ROUTE_REJECT, 0))
        stats[f"edit_{chem}_total"] = int(sum(counts.values()))
    for (pre, post), count in sorted(transition.items()):
        stats[f"transition_{pre}__{post}"] = int(count)

    if keep_route_changes:
        nogo.append("keep_changed_route")
    if human_drops != drop_n:
        nogo.append("drop_count_mismatch")
    if total != (expected_source_rows or total):
        nogo.append("source_count_mismatch")

    return AptaIndexDryRunSimulation(
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked_ssdna=preview_parked_ssdna,
        preview_parked_chemistry=preview_parked_chemistry,
        preview_eligible=preview_eligible,
        change_report=change_report,
        decision_audit=decision_audit,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        nogo_reasons=tuple(nogo),
        stats=stats,
    )


def serialise_aptaindex_simulation(simulation: AptaIndexDryRunSimulation) -> bytes:
    import json

    chunks = [
        json.dumps(simulation.preview_canonical, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_decisions, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_rejections, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_parked_ssdna, sort_keys=True, ensure_ascii=True),
        json.dumps(
            simulation.preview_parked_chemistry, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.decision_audit, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def serialise_aptaindex_simulation_sequence_free(
    simulation: AptaIndexDryRunSimulation,
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
        json.dumps(
            simulation.preview_parked_chemistry, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.decision_audit, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.stats, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def format_dry_run_markdown(
    simulation: AptaIndexDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
) -> str:
    stats = simulation.stats
    applied_by_id = {item.record_id: item for item in simulation.applied}
    nogo = simulation.nogo_reasons
    go = not nogo
    lines = [
        "# AptaIndex CHECKPOINT-1 application dry-run",
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
        f"- keep: `{stats['human_keep']}`",
        f"- edit: `{stats['human_edit']}`",
        f"- drop: `{stats['human_drop']}`",
        f"- decisions consumed: `{stats['decisions_consumed']}`",
        "",
        "## 206-row route transition",
        "",
        f"- pre technically eligible: `{stats['reviewed_before_eligible']}`",
        f"- pre parked ssDNA: `{stats['reviewed_before_ssdna']}`",
        f"- pre chemistry-review park: `{stats['reviewed_before_chemistry']}`",
        f"- pre technical reject: `{stats['reviewed_before_reject']}`",
        f"- post technically eligible: `{stats['reviewed_after_eligible']}`",
        f"- post parked ssDNA: `{stats['reviewed_after_ssdna']}`",
        f"- post chemistry-review park: `{stats['reviewed_after_chemistry']}`",
        f"- post technical reject (includes manual_reject): "
        f"`{stats['reviewed_after_reject']}`",
        "",
        "### keep",
        "",
        f"- count: `{stats['human_keep']}`",
        f"- routes unchanged: `{stats['keep_routes_unchanged']}`",
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
        f"- to chemistry-review park: `{stats['edit_to_chemistry']}`",
        f"- to technical reject: `{stats['edit_to_reject']}`",
        "",
        "## Full 1050-row projected reconciliation",
        "",
        f"- total source records: `{stats['total_records']}`",
        f"- unaffected by CHECKPOINT: `{stats['unaffected_records']}`",
        f"- post-review technically eligible: `{stats['technically_eligible']}`",
        f"- post-review parked ssDNA: `{stats['parked_ssdna']}`",
        f"- post-review chemistry-review parks: `{stats['parked_chemistry_review']}`",
        f"- human/manual rejects: `{stats['manual_rejects']}`",
        f"- technical rejects after manual edits: "
        f"`{stats['technical_rejects_after_edit']}`",
        f"- automatic pre-checkpoint rejects remaining: "
        f"`{stats['automatic_rejects_unaffected']}`",
        f"- all technical rejects after review: "
        f"`{stats['technical_rejects_after_review']}`",
        "",
        "Reconciliation: technically eligible + parked ssDNA + chemistry-review",
        "parks + technical rejects = 1050. Automatic S3 rejects that were not",
        "in the 206-row CHECKPOINT remain rejected. Human drops become",
        f"`{MANUAL_REJECT_REASON}` and are counted inside technical rejects.",
        "",
        "## Edited-chemistry routes",
        "",
    ]
    for chem in EDIT_CHEMISTRY_CLASSES:
        lines.append(
            f"- `{chem}`: n=`{stats.get(f'edit_{chem}_total', 0)}`; "
            f"eligible=`{stats.get(f'edit_{chem}_eligible', 0)}`; "
            f"ssDNA=`{stats.get(f'edit_{chem}_ssdna', 0)}`; "
            f"chemistry-review=`{stats.get(f'edit_{chem}_chemistry', 0)}`; "
            f"reject=`{stats.get(f'edit_{chem}_reject', 0)}`"
        )
    lines.extend(["", "## Special records (length/route only)", ""])
    for record_id in SPECIAL_RECORD_IDS:
        item = applied_by_id.get(record_id)
        if item is None:
            lines.append(f"- `{record_id}`: not in this dry-run subset")
            continue
        lines.append(
            f"- `{record_id}`: `{item.primary_route_before}` → "
            f"`{item.primary_route_after}`; "
            f"core `{item.sequence_length_core}` nt; "
            f"molecule `{item.molecule_type}`/`{item.chemistry}`; "
            f"reason `{item.primary_reason}`"
        )
    lines.extend(
        [
            "",
            "## T→U provenance",
            "",
            "`t_to_u_applied` records whether the **current** nucleotide",
            "normaliser performed T→U on the working nucleotide input. Keep and",
            "no-correction edits preserve the S2 field. Human corrections that",
            "already contain U therefore remain `false` unless this apply step",
            "itself converted T. Manual T→U is not a separate schema field.",
            "",
            "## S4 boundary",
            "",
            "Dry-run did not populate target/evidence/affinity/clustering/",
            "partition/leakage fields. Raw source target and affinity metadata",
            "remain available for a later global S4.",
            "",
            "## Integrity",
            "",
            f"- authorised_for_s4: `{stats['authorised_for_s4']}`",
            f"- checkpoint_closed: `{stats['checkpoint_closed']}`",
            f"- S1 SHA-256: `{integrity.get('s1', '')}`",
            f"- S2 SHA-256: `{integrity.get('s2', '')}`",
            f"- S3 SHA-256: `{integrity.get('s3', '')}`",
            f"- raw SHA-256: `{integrity.get('raw', '')}`",
            "",
            "## Pipeline stop",
            "",
            "CHECKPOINT-1 remains unapplied.",
            "S4 remains blocked.",
            "",
        ]
    )
    return "\n".join(lines)
