"""AptaIndex CHECKPOINT-1 real application helpers.

Uses the same simulation/transform as the dry-run. Does not start S4.
This module exists so a later apply milestone can close the checkpoint.
This milestone must not write tracked closure artefacts.
"""

from __future__ import annotations

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


def format_closure_markdown(
    simulation: AptaIndexDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    deterministic_ok: bool,
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
        "## Integrity",
        "",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
        f"- raw SHA-256: `{integrity.get('raw', '')}`",
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
            "Global S4 target normalisation has not started. AptaIndex remains",
            "restricted until a later corpus-wide S4 handoff is authorised.",
            "",
        ]
    )
    return "\n".join(lines)
