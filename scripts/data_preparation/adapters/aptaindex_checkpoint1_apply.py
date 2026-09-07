"""AptaIndex CHECKPOINT-1 real application helpers.

Uses the same simulation/transform as the dry-run. Does not start S4.
Writes sequence-free tracked closure artefacts; restricted sequence data
remain under ignored data/.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Mapping, Sequence

from adapters.aptaindex_checkpoint1_dry_run import AptaIndexDryRunSimulation
from adapters.aptaindex_s3 import (
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)

APTAINDEX_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    "authorised_for_s4 means RNA/2F-RNA technical eligibility after "
    "AptaIndex CHECKPOINT-1. It does not mean target canonicalisation, "
    "UniProt resolution, evidence mapping, leakage filtering, merge, "
    "deduplication, clustering, balancing, partitioning, or S4 execution."
)

APTAINDEX_TRACKED_RESOLUTION_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "primary_route",
    "proposed_decision",
    "resolved_decision",
    "primary_reason",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
    "manual_decision",
    "route_changed",
)

ROUTE_TO_STATUS: Mapping[str, str] = {
    PRIMARY_ROUTE_ELIGIBLE: "approved_for_s4",
    PRIMARY_ROUTE_REJECT: "rejected_after_checkpoint1",
    PRIMARY_ROUTE_SSDNA: "parked_after_checkpoint1",
    PRIMARY_ROUTE_CHEMISTRY_REVIEW: "parked_after_checkpoint1",
}

PREVIEW_COMPARISON_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "canonical",
        "aptaindex_checkpoint1_dry_run_canonical_preview.csv",
        "aptaindex_checkpoint1_applied_canonical.csv",
    ),
    (
        "routing",
        "aptaindex_checkpoint1_dry_run_routing_preview.csv",
        "aptaindex_checkpoint1_applied_routing.csv",
    ),
    (
        "rejection",
        "aptaindex_checkpoint1_dry_run_rejection_preview.csv",
        "aptaindex_checkpoint1_applied_rejection.csv",
    ),
    (
        "parked_ssdna",
        "aptaindex_checkpoint1_dry_run_parked_ssdna_preview.csv",
        "aptaindex_checkpoint1_applied_parked_ssdna.csv",
    ),
    (
        "parked_chemistry",
        "aptaindex_checkpoint1_dry_run_parked_chemistry_preview.csv",
        "aptaindex_checkpoint1_applied_parked_chemistry.csv",
    ),
    (
        "eligible",
        "aptaindex_checkpoint1_dry_run_eligible_preview.csv",
        "aptaindex_checkpoint1_applied_eligible.csv",
    ),
    (
        "change_report",
        "aptaindex_checkpoint1_dry_run_change_report.csv",
        "aptaindex_checkpoint1_applied_change_report.csv",
    ),
    (
        "decision_audit",
        "aptaindex_checkpoint1_dry_run_decision_audit.csv",
        "aptaindex_checkpoint1_decision_audit.csv",
    ),
)

EXPECTED_PRODUCTION_ROUTES: dict[str, int] = {
    "technically_eligible": 221,
    "parked_ssdna": 614,
    "parked_chemistry_review": 33,
    "technical_rejects_after_review": 182,
}

EXPECTED_REVIEWED_AFTER: dict[str, int] = {
    "reviewed_after_eligible": 91,
    "reviewed_after_ssdna": 59,
    "reviewed_after_chemistry": 33,
    "reviewed_after_reject": 23,
}

EXPECTED_HUMAN_DECISIONS: dict[str, int] = {
    "keep": 142,
    "edit": 42,
    "drop": 22,
}

EXPECTED_EDIT_TRANSITIONS: dict[str, int] = {
    "edit_to_eligible": 16,
    "edit_to_ssdna": 12,
    "edit_to_chemistry": 13,
    "edit_to_reject": 1,
}

EXPECTED_SPECIAL_RECORDS: dict[str, dict[str, object]] = {
    "aptaindex:0412": {
        "length": 40,
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "route": PRIMARY_ROUTE_SSDNA,
        "alphabet": "ACGT",
        "t_to_u_applied": False,
    },
    "aptaindex:0518": {
        "length": 40,
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "route": PRIMARY_ROUTE_SSDNA,
        "alphabet": "ACGT",
        "t_to_u_applied": False,
    },
    "aptaindex:0519": {
        "length": 81,
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "route": PRIMARY_ROUTE_SSDNA,
        "alphabet": "ACGT",
        "t_to_u_applied": False,
    },
    "aptaindex:0492": {
        "length": 48,
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "route": PRIMARY_ROUTE_SSDNA,
        "alphabet": "ACGT",
        "t_to_u_applied": False,
    },
    "aptaindex:0753": {
        "length": 39,
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "route": PRIMARY_ROUTE_SSDNA,
        "alphabet": "ACGT",
        "t_to_u_applied": False,
    },
    "aptaindex:0960": {
        "length": 39,
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "route": PRIMARY_ROUTE_SSDNA,
        "alphabet": "ACGT",
        "t_to_u_applied": False,
    },
    "aptaindex:0754": {
        "length": 19,
        "molecule_type": "RNA",
        "chemistry": "2F-RNA",
        "route": PRIMARY_ROUTE_REJECT,
        "reason": "length_out_of_range",
        "alphabet": "ACGU",
    },
    "aptaindex:0610": {
        "length": 76,
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "route": PRIMARY_ROUTE_ELIGIBLE,
        "alphabet": "ACGU",
    },
    "aptaindex:0372": {
        "length": 100,
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "route": PRIMARY_ROUTE_ELIGIBLE,
        "alphabet": "ACGU",
    },
    "aptaindex:0938": {
        "length": 80,
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "route": PRIMARY_ROUTE_ELIGIBLE,
        "alphabet": "ACGU",
    },
    "aptaindex:0187": {
        "length": 51,
        "molecule_type": "RNA",
        "chemistry": "2F-RNA",
        "route": PRIMARY_ROUTE_ELIGIBLE,
        "alphabet": "ACGU",
        "no_additional_trim": True,
    },
    "aptaindex:0605": {
        "length": 58,
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "route": PRIMARY_ROUTE_ELIGIBLE,
        "alphabet": "ACGU",
        "no_additional_trim": True,
    },
}

CLOSURE_ONLY_FIELDS: tuple[str, ...] = (
    "checkpoint_status",
    "checkpoint_closed",
    "application_mode",
    "review_file_sha256",
    "review_bulk_sha256",
    "s1_sha256",
    "s2_sha256",
    "s3_sha256",
    "sidecar_sha256",
    "raw_sha256",
    "output_hashes",
    "record_decisions",
    "next_stage",
    "s4_started",
)

_DNA_ALPHABET = re.compile(r"^[ACGT]+$")
_RNA_ALPHABET = re.compile(r"^[ACGU]+$")

TRACKED_SEQUENCE_COLUMN_FRAGMENTS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
    "aptaindex_sequence",
    "proposed_5p_sequence",
    "proposed_3p_sequence",
    "detected_constant_5p",
    "detected_constant_3p",
)


class AptaIndexCheckpoint1ApplyError(ValueError):
    """Hard failure while applying AptaIndex CHECKPOINT-1."""


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("manual_decision") or "").strip() for row in queue_rows)
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def resolution_status_for_route(route: str) -> str:
    if route not in ROUTE_TO_STATUS:
        raise ValueError(f"Unknown primary_route {route!r}")
    return ROUTE_TO_STATUS[route]


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
                "manual_decision": review_by_id.get(record_id, {}).get(
                    "manual_decision", ""
                ),
                "route_changed": "true" if record_id in changed else "false",
            }
        )
    return rows


def check_production_expectations(
    *,
    simulation: AptaIndexDryRunSimulation,
    record_decisions: Mapping[str, int],
) -> None:
    stats = simulation.stats
    total = int(stats["total_records"])
    eligible = int(stats["technically_eligible"])
    ssdna = int(stats["parked_ssdna"])
    chemistry = int(stats["parked_chemistry_review"])
    reject_n = int(stats["technical_rejects_after_review"])
    if eligible + ssdna + chemistry + reject_n != total:
        raise AptaIndexCheckpoint1ApplyError(
            "Applied routes do not reconcile to the AptaIndex source"
        )
    if total != 1050:
        raise AptaIndexCheckpoint1ApplyError(
            f"Applied source count must be 1050; got {total}"
        )
    for key, expected in EXPECTED_PRODUCTION_ROUTES.items():
        got = int(stats[key])
        if got != expected:
            raise AptaIndexCheckpoint1ApplyError(
                f"Applied {key} must be {expected}; got {got}"
            )
    for key, expected in EXPECTED_REVIEWED_AFTER.items():
        got = int(stats[key])
        if got != expected:
            raise AptaIndexCheckpoint1ApplyError(
                f"Reviewed-206 {key} must be {expected}; got {got}"
            )
    for key, expected in EXPECTED_HUMAN_DECISIONS.items():
        got = int(record_decisions.get(key, stats.get(f"human_{key}", 0)))
        if got != expected:
            raise AptaIndexCheckpoint1ApplyError(
                f"Human {key} must be {expected}; got {got}"
            )
    if int(stats["keep_unexpected_route_changes"]) != 0:
        raise AptaIndexCheckpoint1ApplyError(
            "Keep decisions must not change pre-review route"
        )
    if int(stats["human_reviewed_drops"]) != EXPECTED_HUMAN_DECISIONS["drop"]:
        raise AptaIndexCheckpoint1ApplyError(
            "Human drops must all use the manual-reject route"
        )
    for key, expected in EXPECTED_EDIT_TRANSITIONS.items():
        got = int(stats[key])
        if got != expected:
            raise AptaIndexCheckpoint1ApplyError(
                f"Edit transition {key} must be {expected}; got {got}"
            )
    if simulation.nogo_reasons:
        raise AptaIndexCheckpoint1ApplyError(
            "Apply fail-closed: " + "; ".join(simulation.nogo_reasons)
        )


def check_special_records(simulation: AptaIndexDryRunSimulation) -> None:
    applied_by_id = {item.record_id: item for item in simulation.applied}
    for record_id, expected in EXPECTED_SPECIAL_RECORDS.items():
        item = applied_by_id.get(record_id)
        if item is None:
            raise AptaIndexCheckpoint1ApplyError(
                f"Locked special record {record_id} was not consumed"
            )
        mismatches: list[str] = []
        if item.sequence_length_core != expected["length"]:
            mismatches.append("sequence_length_core")
        if item.molecule_type != expected["molecule_type"]:
            mismatches.append("molecule_type")
        if item.chemistry != expected["chemistry"]:
            mismatches.append("chemistry")
        if item.primary_route_after != expected["route"]:
            mismatches.append("primary_route")
        if "reason" in expected and item.primary_reason != expected["reason"]:
            mismatches.append("primary_reason")
        if expected.get("t_to_u_applied") is False and item.t_to_u_applied:
            mismatches.append("t_to_u_applied")
        if expected.get("no_additional_trim"):
            if item.applied_trim_5p_nt or item.applied_trim_3p_nt:
                mismatches.append("additional_trim")
        alphabet = expected.get("alphabet")
        seq = item.sequence_full or ""
        if alphabet == "ACGT":
            if item.t_to_u_applied or "U" in seq or not _DNA_ALPHABET.fullmatch(seq):
                mismatches.append("dna_alphabet")
        elif alphabet == "ACGU":
            if seq and not _RNA_ALPHABET.fullmatch(seq):
                mismatches.append("rna_alphabet")
        if mismatches:
            raise AptaIndexCheckpoint1ApplyError(
                f"Special-record outcome diverged from locked dry-run for "
                f"{record_id}: {', '.join(mismatches)}"
            )


def format_closure_markdown(
    simulation: AptaIndexDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    deterministic_ok: bool,
    preview_comparison_ok: bool,
) -> str:
    stats = simulation.stats
    lines = [
        "# AptaIndex CHECKPOINT-1 closure",
        "",
        APTAINDEX_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Human CHECKPOINT-1 decisions were applied through the fail-closed",
        "`apply_reviewed_record` path. Pre-review S2/S3 snapshots were not",
        "overwritten. S4 was not started. Target extraction was not performed.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- group review SHA-256: `{review_hashes.get('groups', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        "",
        "## Human decisions",
        "",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- keep: `{record_decisions.get('keep', 0)}`",
        f"- edit: `{record_decisions.get('edit', 0)}`",
        f"- drop: `{record_decisions.get('drop', 0)}`",
        "",
        "## Routing reconciliation",
        "",
        f"- total source records: `{stats['total_records']}`",
        f"- technically eligible: `{stats['technically_eligible']}`",
        f"- parked ssDNA: `{stats['parked_ssdna']}`",
        f"- parked chemistry-review: `{stats['parked_chemistry_review']}`",
        f"- technical rejects after review: `{stats['technical_rejects_after_review']}`",
        f"- authorised for future global S4: `{stats['authorised_for_s4']}`",
        "",
        "authorised_for_s4 counts technically eligible RNA/2F-RNA records",
        "after CHECKPOINT-1. Parked ssDNA, chemistry-review parks, and",
        "rejects are not authorised for S4. Source-level closure means this",
        "source may proceed to later global-S4 preparation under those",
        "routing rules; it does not authorise every AptaIndex record.",
        "",
        "## Integrity",
        "",
        f"- S1 SHA-256: `{integrity.get('s1', '')}`",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
        f"- raw SHA-256: `{integrity.get('raw', '')}`",
        f"- dry-run/apply parity: `{'true' if preview_comparison_ok else 'false'}`",
        f"- deterministic rerun: `{'true' if deterministic_ok else 'false'}`",
        "",
        "## Output hashes",
        "",
    ]
    for name, digest in output_hashes.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "Global S4 target normalisation has not started. AptaIndex is",
            "prepared as one input to a later corpus-wide S4 handoff.",
            "",
        ]
    )
    return "\n".join(lines)
