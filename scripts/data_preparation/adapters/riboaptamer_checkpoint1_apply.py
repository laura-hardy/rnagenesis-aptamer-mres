"""RiboAptamer CHECKPOINT-1 real application helpers.

Uses the same simulation/transform as the dry-run. Does not start S4.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from adapters.riboaptamer_checkpoint1_dry_run import RiboAptamerDryRunSimulation
from adapters.riboaptamer_s3 import PRIMARY_ROUTE_ELIGIBLE, PRIMARY_ROUTE_REJECT

RIBOAPTAMER_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    "authorised_for_s4 means RNA technical eligibility after RiboAptamer "
    "CHECKPOINT-1. It does not mean target canonicalisation, UniProt "
    "resolution, evidence mapping, leakage filtering, merge, deduplication, "
    "clustering, balancing, partitioning, or S4 execution."
)

RIBOAPTAMER_TRACKED_RESOLUTION_COLUMNS: tuple[str, ...] = (
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
    "parked_ssdna": "parked_after_checkpoint1",
}


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("manual_decision") or "").strip() for row in queue_rows)
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def count_trim_actions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter(
        (row.get("manual_trim_action") or "").strip() for row in queue_rows
    )
    return {
        key: int(counts.get(key, 0)) for key in ("approve", "override", "reject", "trim")
    }


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
    simulation: RiboAptamerDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    trim_actions: Mapping[str, int],
    deterministic_ok: bool,
    human_source_preserved: bool,
) -> str:
    stats = simulation.stats
    lines = [
        "# RiboAptamer CHECKPOINT-1 closure",
        "",
        RIBOAPTAMER_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Human CHECKPOINT-1 decisions were applied through the fail-closed",
        "`apply_reviewed_record` path. Pre-review S2/S3 snapshots were not",
        "overwritten. Group-wise constant-region inference remained disabled.",
        "S4 was not started. Target extraction was not performed.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- group review SHA-256: `{review_hashes.get('groups', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        f"- recommendation JSON SHA-256: `{review_hashes.get('rec_json', '')}`",
        f"- human-source copy preserved: `{str(human_source_preserved).lower()}`",
        "",
        "## Human decisions",
        "",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- decisions consumed: `{stats['decisions_consumed']}` / `{stats['reviewed_records']}`",
        f"- unconsumed decisions: `{stats['unconsumed_decisions']}`",
        f"- keep: `{record_decisions.get('keep', 0)}`",
        f"- edit: `{record_decisions.get('edit', 0)}`",
        f"- drop: `{record_decisions.get('drop', 0)}`",
        f"- trim approve (schema): `{trim_actions.get('approve', 0)}`",
        f"- trim override: `{trim_actions.get('override', 0)}`",
        f"- trim reject: `{trim_actions.get('reject', 0)}`",
        "",
        "## Routing reconciliation",
        "",
        f"- total source records: `{stats['total_records']}`",
        f"- human-reviewed drops: `{stats['human_reviewed_drops']}`",
        f"- technical rejects after review: `{stats['technical_rejects_after_review']}`",
        f"- parked ssDNA: `{stats['parked_ssdna']}`",
        f"- parked non-protein: `{stats['parked_non_protein']}`",
        f"- technically eligible: `{stats['technically_eligible']}`",
        f"- authorised for future global S4: `{stats['authorised_for_s4']}`",
        "",
        "Reconciliation: technical rejects + parked ssDNA + parked non-protein",
        "+ technically eligible = total source records.",
        "",
        "## Constant-region accounting",
        "",
        "- known T7 proposals before CP1: `1`",
        f"- approved known T7 trims: `{stats['approved_known_t7_trims']}`",
        "- rejected/deferred known proposals: `0`",
        "- group-consensus proposals: `0`",
        f"- strong unresolved-constant flags (human CP1 observation): "
        f"`{stats['strong_unresolved_constant_flags']}`",
        f"- weak possible-constant flags (human CP1 observation): "
        f"`{stats['weak_possible_constant_flags']}`",
        "- speculative/manual numeric trims outside approved proposals: `0`",
        "",
        "Strong unresolved-constant flags are human CHECKPOINT-1 observations,",
        "not S2 group-consensus inferences. Sequences were retained without a",
        "guessed trim. Weak flags remain a separate warning class.",
        "",
        "## Integrity",
        "",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
        f"- sidecar SHA-256: `{integrity.get('sidecar', '')}`",
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
            "Global S4 target normalisation has not started. RiboAptamer is",
            "prepared as one input to a later corpus-wide S4 handoff.",
            "",
        ]
    )
    return "\n".join(lines)
