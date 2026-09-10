"""AptaDiff CHECKPOINT-1 real application helpers.

Uses the same simulation/transform as the dry-run. Does not start S4 or
prepare a global-S4 handoff. Dataset-A replication is not built here.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from adapters.aptadiff_checkpoint1_dry_run import AptaDiffDryRunSimulation
from adapters.aptadiff_checkpoint1_review import (
    CHECKPOINT_STATUS_PARKED,
    CHECKPOINT_STATUS_REJECTED,
)
from adapters.aptadiff_s3 import (
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)

APTADIFF_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "No AptaDiff record is authorised for global S4.\n"
    "Reviewed rejects are unresolved-IUPAC-N records with no source-supported "
    "repair. Ordinary ssDNA parks remain parked DNA. Global S4 was not prepared "
    "or run. Dataset-A replication was not built."
)

FROZEN_APTADIFF_A_RAW_SHA256 = (
    "ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77"
)
FROZEN_APTADIFF_B_RAW_SHA256 = (
    "546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72"
)
FROZEN_APTADIFF_A_S1_CANONICAL_SHA256 = (
    "22bd7357311ce5d9d0a000c20f75fc439942b16c37105a71509fb8329ee7b083"
)
FROZEN_APTADIFF_A_S1_SIDECAR_SHA256 = (
    "ec0453c50205854dc1648c833a2f96a40b691ee39b8c49433d0024480c9314ea"
)
FROZEN_APTADIFF_B_S1_CANONICAL_SHA256 = (
    "321ef00b4e7a78834f431b4335bf21e89752c8e596523480676f2d5ac2e50921"
)
FROZEN_APTADIFF_B_S1_SIDECAR_SHA256 = (
    "3f7183e5999d2f729b1fd1d225287b3515414cec2d7b91e44de46cf84a5ec4a0"
)
FROZEN_APTADIFF_A_S2_SHA256 = (
    "c88e6f12dea4d60377a1c5a7a95861fcc666e47be27920a234f828b70df6ca55"
)
FROZEN_APTADIFF_B_S2_SHA256 = (
    "c40bc662f4c79fcc24c161c5a82e74c2d58f96fbb6ca74fbb84b105bf8bc98f6"
)

SOURCE_DATASETS: dict[str, str] = {
    "aptadiff_a": "aptadiff_a_igfbp3_p6_2026-06-22",
    "aptadiff_b": "aptadiff_b_ptk7_p6_2026-06-22",
}

ACCEPTED_DRY_RUN_ROUTES: dict[str, dict[str, int]] = {
    "aptadiff_a": {
        "total_records": 13803,
        "reviewed_records": 1,
        "parked_ssdna": 13802,
        "technical_rejects_after_review": 1,
        "technically_eligible": 0,
        "authorised_for_s4": 0,
    },
    "aptadiff_b": {
        "total_records": 11547,
        "reviewed_records": 15,
        "parked_ssdna": 11532,
        "technical_rejects_after_review": 15,
        "technically_eligible": 0,
        "authorised_for_s4": 0,
    },
}

PREVIEW_COMPARISON_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "canonical",
        "{source}_checkpoint1_dry_run_canonical_preview.csv",
        "{source}_checkpoint1_applied_canonical.csv",
    ),
    (
        "routing",
        "{source}_checkpoint1_dry_run_routing_preview.csv",
        "{source}_checkpoint1_applied_routing.csv",
    ),
    (
        "rejection",
        "{source}_checkpoint1_dry_run_rejection_preview.csv",
        "{source}_checkpoint1_applied_rejection.csv",
    ),
    (
        "parked_ssdna",
        "{source}_checkpoint1_dry_run_parked_ssdna_preview.csv",
        "{source}_checkpoint1_applied_parked_ssdna.csv",
    ),
    (
        "eligible",
        "{source}_checkpoint1_dry_run_eligible_preview.csv",
        "{source}_checkpoint1_applied_eligible.csv",
    ),
    (
        "change_report",
        "{source}_checkpoint1_dry_run_change_report.csv",
        "{source}_checkpoint1_applied_change_report.csv",
    ),
    (
        "decision_audit",
        "{source}_checkpoint1_dry_run_decision_audit.csv",
        "{source}_checkpoint1_decision_audit.csv",
    ),
)

APTADIFF_TRACKED_RESOLUTION_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "primary_route",
    "proposed_decision",
    "resolved_decision",
    "primary_reason",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
    "manual_decision",
    "manual_review_required",
    "route_changed",
    "sequence_corrected",
    "molecule_overridden",
    "trim_applied",
)

SEMANTIC_RECORD_FIELDS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "molecule_type",
    "chemistry",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "trim_status",
    "trim_confidence",
    "primary_route",
    "primary_reason",
)

TRACKED_SEQUENCE_COLUMN_FRAGMENTS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
    "detected_constant_5p",
    "detected_constant_3p",
)

CLOSURE_ONLY_FIELDS: tuple[str, ...] = (
    "checkpoint_status",
    "checkpoint_closed",
    "application_mode",
    "review_file_sha256",
    "review_bulk_sha256",
    "raw_sha256",
    "s1_sha256",
    "sidecar_sha256",
    "s2_sha256",
    "s3_sha256",
    "s3_decisions_sha256",
    "output_hashes",
    "record_decisions",
    "next_stage",
    "s4_started",
    "global_s4_handoff_prepared",
    "global_s4_run",
)

ROUTE_TO_STATUS: Mapping[str, str] = {
    PRIMARY_ROUTE_ELIGIBLE: "approved_for_s4",
    PRIMARY_ROUTE_SSDNA: CHECKPOINT_STATUS_PARKED,
    PRIMARY_ROUTE_REJECT: CHECKPOINT_STATUS_REJECTED,
}


class AptaDiffCheckpoint1ApplyError(ValueError):
    """Hard failure while applying AptaDiff CHECKPOINT-1 for real."""


def frozen_pipeline_hashes(source_key: str) -> dict[str, str]:
    if source_key == "aptadiff_a":
        return {
            "raw": FROZEN_APTADIFF_A_RAW_SHA256,
            "s1": FROZEN_APTADIFF_A_S1_CANONICAL_SHA256,
            "sidecar": FROZEN_APTADIFF_A_S1_SIDECAR_SHA256,
            "s2": FROZEN_APTADIFF_A_S2_SHA256,
        }
    if source_key == "aptadiff_b":
        return {
            "raw": FROZEN_APTADIFF_B_RAW_SHA256,
            "s1": FROZEN_APTADIFF_B_S1_CANONICAL_SHA256,
            "sidecar": FROZEN_APTADIFF_B_S1_SIDECAR_SHA256,
            "s2": FROZEN_APTADIFF_B_S2_SHA256,
        }
    raise AptaDiffCheckpoint1ApplyError(f"Unknown source_key={source_key!r}")


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("manual_decision") or "").strip() for row in queue_rows)
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def resolution_status_for_route(route: str) -> str:
    if route not in ROUTE_TO_STATUS:
        raise AptaDiffCheckpoint1ApplyError(f"Unknown primary_route {route!r}")
    return ROUTE_TO_STATUS[route]


def preview_comparison_files(source_key: str) -> tuple[tuple[str, str, str], ...]:
    token = source_key
    return tuple(
        (key, preview.format(source=token), applied.format(source=token))
        for key, preview, applied in PREVIEW_COMPARISON_FILES
    )


def tracked_payload_contains_sequence(text: str) -> bool:
    lowered = text.lower()
    return any(fragment in lowered for fragment in TRACKED_SEQUENCE_COLUMN_FRAGMENTS)


def build_tracked_resolutions(
    *,
    decisions: Sequence[Mapping[str, str]],
    queue_rows: Sequence[Mapping[str, str]],
    route_changed_ids: Sequence[str],
) -> list[dict[str, str]]:
    review_by_id = {row["record_id"]: row for row in queue_rows}
    changed = set(route_changed_ids)
    rows: list[dict[str, str]] = []
    for decision in decisions:
        record_id = decision["record_id"]
        route = decision["primary_route"]
        authorised = route == PRIMARY_ROUTE_ELIGIBLE
        if authorised:
            resolved = "accept"
        elif route == PRIMARY_ROUTE_REJECT:
            resolved = "reject"
        else:
            resolved = "park"
        review = review_by_id.get(record_id, {})
        required = decision.get("manual_review_required") or review.get(
            "manual_review_required", ""
        )
        rows.append(
            {
                "record_id": record_id,
                "native_id": decision.get("native_id", ""),
                "primary_route": route,
                "proposed_decision": decision.get("proposed_decision", ""),
                "resolved_decision": resolved,
                "primary_reason": decision.get("primary_reason", ""),
                "checkpoint1_resolution_status": resolution_status_for_route(route),
                "authorised_for_s4": "true" if authorised else "false",
                "manual_decision": review.get("manual_decision", ""),
                "manual_review_required": required,
                "route_changed": "true" if record_id in changed else "false",
                "sequence_corrected": "false",
                "molecule_overridden": "false",
                "trim_applied": "false",
            }
        )
    return rows


def check_production_expectations(
    *,
    source_key: str,
    simulation: AptaDiffDryRunSimulation,
    queue_rows: Sequence[Mapping[str, str]],
) -> None:
    expected = ACCEPTED_DRY_RUN_ROUTES.get(source_key)
    if expected is None:
        return
    stats = simulation.stats
    for key, value in expected.items():
        got = int(stats.get(key, -1))
        if got != value:
            raise AptaDiffCheckpoint1ApplyError(
                f"{source_key} {key} must be {value}; got {got}"
            )
    decisions = count_manual_decisions(queue_rows)
    if decisions.get("keep") != expected["reviewed_records"]:
        raise AptaDiffCheckpoint1ApplyError(
            f"{source_key} keep count must equal reviewed records"
        )
    if decisions.get("edit") or decisions.get("drop"):
        raise AptaDiffCheckpoint1ApplyError(
            f"{source_key} must not contain edit or drop decisions"
        )
    if int(stats["sequence_corrections"]) or int(stats["molecule_overrides"]):
        raise AptaDiffCheckpoint1ApplyError(
            f"{source_key} must not apply sequence or molecule corrections"
        )
    if simulation.nogo_reasons:
        raise AptaDiffCheckpoint1ApplyError(
            "Dry-run/apply NO-GO: " + "; ".join(simulation.nogo_reasons)
        )


def format_closure_markdown(
    simulation: AptaDiffDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    semantic_mismatches: int,
    deterministic_ok: bool,
    preview_comparison_ok: bool,
) -> str:
    stats = simulation.stats
    label = "Dataset A" if simulation.source_key == "aptadiff_a" else "Dataset B"
    lines = [
        f"# AptaDiff {label} CHECKPOINT-1 closure",
        "",
        APTADIFF_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Human CHECKPOINT-1 decisions were applied through the same",
        "`apply_aptadiff_checkpoint1_package` transformation used by the",
        "accepted dry-run. Pre-review S1/S2/S3 snapshots were not overwritten.",
        "Global S4 was not started. No global-S4 handoff was prepared.",
        "Dataset-A replication was not built.",
        "",
        "## Review inputs",
        "",
        f"- source_key: `{simulation.source_key}`",
        f"- source records: `{stats['total_records']}`",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        "",
        "## Human decisions",
        "",
        f"- keep (confirm current reject): `{record_decisions.get('keep', 0)}`",
        f"- edit: `{record_decisions.get('edit', 0)}`",
        f"- drop: `{record_decisions.get('drop', 0)}`",
        "- reviewed rejects were unresolved-IUPAC-N records with no "
        "source-supported repair",
        f"- sequence corrections: `{stats['sequence_corrections']}`",
        f"- molecule/chemistry overrides: `{stats['molecule_overrides']}`",
        f"- trim changes: `{stats['records_trimmed']}`",
        "",
        "## Final routing",
        "",
        f"- parked ssDNA: `{stats['parked_ssdna']}`",
        f"- technical reject (ambiguous_bases): `{stats['technical_rejects_after_review']}`",
        f"- authorised_for_s4: `{stats['authorised_for_s4']}`",
        "",
        "Ordinary clean ssDNA records remain parked DNA.",
        "These sources do not contribute records to the RNA corpus.",
        "",
        "## Integrity",
        "",
        f"- raw SHA-256: `{integrity.get('raw', '')}`",
        f"- S1 SHA-256: `{integrity.get('s1', '')}`",
        f"- sidecar SHA-256: `{integrity.get('sidecar', '')}`",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- S3 SHA-256: `{integrity.get('s3', '')}`",
        f"- preview comparison: `{'pass' if preview_comparison_ok else 'fail'}`",
        f"- semantic mismatches: `{semantic_mismatches}`",
        f"- deterministic rerun: `{'pass' if deterministic_ok else 'skipped'}`",
        "",
        f"- tracked resolutions SHA-256: `{output_hashes.get('tracked_manifest', '')}`",
        "",
        "checkpoint1_closed = true",
        "global S4 not run",
        "Dataset-A replication not built",
        "",
    ]
    return "\n".join(lines)
