"""AptaDB CHECKPOINT-1 real application helpers (closure, comparison).

Uses the same simulation/transform as the dry-run. Does not start S4.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from adapters.aptadb_checkpoint1_dry_run import AptaDBDryRunSimulation
from adapters.aptadb_s3 import (
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_NON_PROTEIN,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)

APTADB_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    "authorised_for_s4 means RNA-protein technical eligibility after AptaDB "
    "CHECKPOINT-1. It does not mean target canonicalisation, UniProt "
    "resolution, evidence mapping, leakage filtering, merge, deduplication, "
    "clustering, balancing, partitioning, or S4 execution."
)

EXPECTED_APTADB_REVIEW_QUEUE_SHA256 = (
    "a446e1155c26472410d3eee26c4e06ed3a1a915acbd289f1735888bd7553c06d"
)
EXPECTED_APTADB_REVIEW_GROUPS_SHA256 = (
    "af414e0383902708908320c6683267c6ceb98aef7604e615a6ee1fd610877e4e"
)
EXPECTED_APTADB_REVIEW_BULK_SHA256 = (
    "f839899eb6e83157a79c74e77d0e4feb2903846cd3678904d8f3864ef50e38ce"
)
EXPECTED_APTADB_REC_JSON_SHA256 = (
    "7eae933ebf9845680accdd1e9320851e94df6ee8f215e7d0c0c2ea14153d7dd5"
)
EXPECTED_APTADB_SIDECAR_SHA256 = (
    "12e817369c620625c6d9758d88de71b82ca387d7376ca21d4614c4c7343d5465"
)

EXPECTED_PRODUCTION_ROUTES: dict[str, int] = {
    "technical_rejects_after_review": 47,
    "parked_ssdna": 1037,
    "parked_non_protein": 115,
    "technically_eligible": 151,
}
EXPECTED_PRODUCTION_ROUTE_CHANGES: tuple[tuple[str, str, str], ...] = (
    ("aptadb:230", PRIMARY_ROUTE_REJECT, PRIMARY_ROUTE_SSDNA),
    ("aptadb:491", PRIMARY_ROUTE_REJECT, PRIMARY_ROUTE_SSDNA),
    ("aptadb:1170", PRIMARY_ROUTE_REJECT, PRIMARY_ROUTE_ELIGIBLE),
)
EXPECTED_PRODUCTION_TRANSFORMS: dict[str, int] = {
    "human_reviewed_drops": 1,
    "technical_rejects_excluding_human_drop": 46,
    "sequence_corrections": 3,
    "molecule_overrides": 1,
    "records_trimmed": 62,
    "trimmed_by_group": 60,
    "trimmed_by_record_override": 2,
    "core_length_changed": 64,
    "large_trim_human_approved": 60,
    "guard_rail_failures": 0,
    "route_changed": 3,
    "unlinked_aptamers": 37,
    "unlinked_missing_target": 37,
}
EXPECTED_PRODUCTION_CORE: dict[str, int | float] = {
    "after_core_min": 12,
    "after_core_median": 47,
    "after_core_max": 133,
    "after_core_lt20": 25,
    "after_core_20_25": 77,
    "after_core_26_89": 1157,
    "after_core_90_100": 70,
    "after_core_gt100": 21,
}
EXPECTED_RECORD_DECISIONS: dict[str, int] = {
    "keep": 173,
    "edit": 64,
    "drop": 1,
}
EXPECTED_GROUP_DECISIONS: dict[str, int] = {
    "approve": 5,
    "override": 3,
    "reject": 1,
}
EXPECTED_BULK_CONFIRMATIONS = 168
EXPECTED_LARGE_TRIM_GROUP_COUNTS: dict[str, int] = {
    "HIV_Gag_Pol": 6,
    "AP65": 5,
    "OX40": 5,
    "pancreatic_polypeptide": 12,
    "CBF1": 15,
    "CD25": 5,
    "NPY": 12,
}

PREVIEW_COMPARISON_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "canonical",
        "aptadb_checkpoint1_dry_run_canonical_preview.csv",
        "aptadb_checkpoint1_applied_canonical.csv",
    ),
    (
        "routing",
        "aptadb_checkpoint1_dry_run_routing_preview.csv",
        "aptadb_checkpoint1_applied_routing.csv",
    ),
    (
        "rejection",
        "aptadb_checkpoint1_dry_run_rejection_preview.csv",
        "aptadb_checkpoint1_applied_rejection.csv",
    ),
    (
        "parked_ssdna",
        "aptadb_checkpoint1_dry_run_parked_ssdna_preview.csv",
        "aptadb_checkpoint1_applied_parked_ssdna.csv",
    ),
    (
        "parked_non_protein",
        "aptadb_checkpoint1_dry_run_parked_non_protein_preview.csv",
        "aptadb_checkpoint1_applied_parked_non_protein.csv",
    ),
    (
        "eligible",
        "aptadb_checkpoint1_dry_run_eligible_preview.csv",
        "aptadb_checkpoint1_applied_eligible.csv",
    ),
    (
        "change_report",
        "aptadb_checkpoint1_dry_run_change_report.csv",
        "aptadb_checkpoint1_applied_change_report.csv",
    ),
    (
        "group_summary",
        "aptadb_checkpoint1_dry_run_group_summary.csv",
        "aptadb_checkpoint1_applied_group_summary.csv",
    ),
    (
        "large_trim_human_approved",
        "aptadb_checkpoint1_dry_run_large_trim_human_approved.csv",
        "aptadb_checkpoint1_applied_large_trim_human_approved.csv",
    ),
    (
        "large_trim_group_summary",
        "aptadb_checkpoint1_dry_run_large_trim_group_summary.csv",
        "aptadb_checkpoint1_applied_large_trim_group_summary.csv",
    ),
    (
        "guard_rail_failures",
        "aptadb_checkpoint1_dry_run_guard_rail_failures.csv",
        "aptadb_checkpoint1_applied_guard_rail_failures.csv",
    ),
)

APTADB_TRACKED_RESOLUTION_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "primary_route",
    "proposed_decision",
    "primary_reason",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
    "manual_decision",
    "route_changed",
)

CLOSURE_ONLY_FIELDS: tuple[str, ...] = (
    "checkpoint_status",
    "checkpoint_closed",
    "application_mode",
    "review_file_sha256",
    "review_groups_sha256",
    "review_bulk_sha256",
    "recommendations_sha256",
    "s2_sha256",
    "s3_sha256",
    "sidecar_sha256",
    "output_hashes",
    "record_decisions",
    "group_decisions",
    "bulk_audit_confirmations",
    "next_stage",
    "s4_started",
)

ROUTE_TO_STATUS: Mapping[str, str] = {
    PRIMARY_ROUTE_ELIGIBLE: "approved_for_s4",
    PRIMARY_ROUTE_SSDNA: "parked_after_checkpoint1",
    PRIMARY_ROUTE_NON_PROTEIN: "parked_after_checkpoint1",
    PRIMARY_ROUTE_REJECT: "rejected_after_checkpoint1",
}


class AptaDBCheckpoint1ApplyError(ValueError):
    """Hard failure while applying AptaDB CHECKPOINT-1 for real."""


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter(
        (row.get("manual_decision") or "").strip() for row in queue_rows
    )
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def count_group_decisions(group_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter(
        (row.get("manual_trim_action") or "").strip() for row in group_rows
    )
    return {
        key: int(counts.get(key, 0)) for key in ("approve", "override", "reject")
    }


def resolution_status_for_route(route: str) -> str:
    if route not in ROUTE_TO_STATUS:
        raise AptaDBCheckpoint1ApplyError(f"Unknown primary_route {route!r}")
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
        rows.append(
            {
                "record_id": record_id,
                "native_id": decision.get("native_id", ""),
                "primary_route": route,
                "proposed_decision": decision.get("proposed_decision", ""),
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
    simulation: AptaDBDryRunSimulation,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    bulk_confirmation_count: int,
) -> None:
    stats = simulation.stats
    total = int(stats["total_interactions"])
    reject_n = int(stats["technical_rejects_after_review"])
    ssdna_n = int(stats["parked_ssdna"])
    non_protein_n = int(stats["parked_non_protein"])
    eligible_n = int(stats["technically_eligible"])
    if reject_n + ssdna_n + non_protein_n + eligible_n != total:
        raise AptaDBCheckpoint1ApplyError(
            "Applied routes do not reconcile to the interaction corpus"
        )
    if total != 1350:
        raise AptaDBCheckpoint1ApplyError(
            f"Applied interaction count must be 1350; got {total}"
        )
    for key, expected in EXPECTED_PRODUCTION_ROUTES.items():
        got = int(stats[key])
        if got != expected:
            raise AptaDBCheckpoint1ApplyError(
                f"Applied {key} must be {expected}; got {got}"
            )
    for key, expected in EXPECTED_PRODUCTION_TRANSFORMS.items():
        got = int(stats[key])
        if got != expected:
            raise AptaDBCheckpoint1ApplyError(
                f"Applied {key} must be {expected}; got {got}"
            )
    for key, expected in EXPECTED_PRODUCTION_CORE.items():
        got = stats[key]
        if got != expected:
            raise AptaDBCheckpoint1ApplyError(
                f"Applied {key} must be {expected}; got {got}"
            )
    decisions = count_manual_decisions(queue_rows)
    if decisions != EXPECTED_RECORD_DECISIONS:
        raise AptaDBCheckpoint1ApplyError(
            f"Record keep/edit/drop must be {EXPECTED_RECORD_DECISIONS}; "
            f"got {decisions}"
        )
    groups = count_group_decisions(group_rows)
    if groups != EXPECTED_GROUP_DECISIONS:
        raise AptaDBCheckpoint1ApplyError(
            f"Group approve/override/reject must be {EXPECTED_GROUP_DECISIONS}; "
            f"got {groups}"
        )
    if bulk_confirmation_count != EXPECTED_BULK_CONFIRMATIONS:
        raise AptaDBCheckpoint1ApplyError(
            "Bulk audit confirmations must be "
            f"{EXPECTED_BULK_CONFIRMATIONS}; got {bulk_confirmation_count}"
        )
    observed_changes = {
        (row["record_id"], row["pre_review_route"], row["post_review_route"])
        for row in simulation.change_report
        if row.get("route_changed") == "true"
    }
    expected_changes = set(EXPECTED_PRODUCTION_ROUTE_CHANGES)
    if observed_changes != expected_changes:
        raise AptaDBCheckpoint1ApplyError(
            "Applied route-change set does not match the validated dry-run: "
            f"expected {sorted(expected_changes)}; got {sorted(observed_changes)}"
        )
    if int(stats["guard_rail_failures"]) != 0 or simulation.guard_rail_failure_rows:
        raise AptaDBCheckpoint1ApplyError(
            "Real apply produced remaining guard-rail failures"
        )
    large_by_label = {
        row["group_label"]: int(row["n_records"])
        for row in simulation.large_trim_groups
    }
    # AP65 ordinary members are recorded without the record-level exception.
    if "AP65" in large_by_label and large_by_label["AP65"] != 5:
        raise AptaDBCheckpoint1ApplyError(
            "AP65 large-trim cohort must be the 5 ordinary members, not "
            f"{large_by_label['AP65']}"
        )
    for label, expected in EXPECTED_LARGE_TRIM_GROUP_COUNTS.items():
        got = large_by_label.get(label, 0)
        if got != expected:
            raise AptaDBCheckpoint1ApplyError(
                f"Large-trim cohort {label} must be {expected}; got {got}"
            )
    if sum(EXPECTED_LARGE_TRIM_GROUP_COUNTS.values()) != 60:
        raise AptaDBCheckpoint1ApplyError("Large-trim expected map does not sum to 60")
    albumin_ids = {
        record_id
        for group in group_rows
        if "albumin" in (group.get("group_label") or "").lower()
        for record_id in (group.get("associated_record_ids") or "").split("|")
        if record_id
    }
    applied_by_id = {item.record_id: item for item in simulation.applied}
    for record_id in albumin_ids:
        item = applied_by_id.get(record_id)
        if item is None:
            continue
        if item.applied_trim_5p_nt or item.applied_trim_3p_nt:
            raise AptaDBCheckpoint1ApplyError(
                f"Albumin deletion-series record {record_id} must remain untrimmed"
            )
    required = {
        "aptadb:230",
        "aptadb:491",
        "aptadb:305",
        "aptadb:1170",
        "aptadb:459",
    }
    missing = required - set(applied_by_id)
    if missing:
        raise AptaDBCheckpoint1ApplyError(
            f"Missing required applied records: {sorted(missing)}"
        )
    g5 = applied_by_id["aptadb:1170"]
    if g5.sequence_length_core != 57:
        raise AptaDBCheckpoint1ApplyError(
            "aptadb:1170 resulting core length must be 57; "
            f"got {g5.sequence_length_core}"
        )
    exception = applied_by_id["aptadb:459"]
    if exception.sequence_length_core != 72:
        raise AptaDBCheckpoint1ApplyError(
            "aptadb:459 resulting core length must be 72; "
            f"got {exception.sequence_length_core}"
        )
    if exception.applied_trim_5p_nt != 23 or exception.applied_trim_3p_nt != 0:
        raise AptaDBCheckpoint1ApplyError("aptadb:459 trim must be 23/0")
    if exception.primary_route_after != PRIMARY_ROUTE_SSDNA:
        raise AptaDBCheckpoint1ApplyError(
            "aptadb:459 must remain parked_ssdna"
        )


def format_closure_markdown(
    simulation: AptaDBDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    group_decisions: Mapping[str, int],
    bulk_confirmations: int,
    preview_comparison_ok: bool,
    deterministic_ok: bool,
) -> str:
    stats = simulation.stats
    lines = [
        "# AptaDB CHECKPOINT-1 closure",
        "",
        APTADB_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Human CHECKPOINT-1 decisions were applied through the same",
        "`apply_reviewed_record` transformation used by the validated dry-run.",
        "The 40% combined-trim rule remains a review/trigger threshold:",
        "explicit human approve/override may apply a biologically large trim,",
        "with derived `large_trim_human_approved` provenance. Empty core,",
        "core <20 nt, over-length, negative, non-integer, contradictory, and",
        "non-contiguous trims remain absolute blockers.",
        "",
        "Canonical S2 and pre-review S3 snapshots were not overwritten.",
        "Dry-run previews were not regenerated. S4 was not started.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- group review SHA-256: `{review_hashes.get('groups', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        f"- recommendation JSON SHA-256: `{review_hashes.get('rec_json', '')}`",
        "",
        "## Human decisions",
        "",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- keep: `{record_decisions.get('keep', 0)}`",
        f"- edit: `{record_decisions.get('edit', 0)}`",
        f"- drop: `{record_decisions.get('drop', 0)}`",
        f"- constant groups: `{sum(group_decisions.values())}`",
        f"- group approve: `{group_decisions.get('approve', 0)}`",
        f"- group override: `{group_decisions.get('override', 0)}`",
        f"- group reject: `{group_decisions.get('reject', 0)}`",
        f"- bulk audit confirmations: `{bulk_confirmations}`",
        "",
        "## Routing reconciliation (1,350 interactions)",
        "",
        f"- total interactions: `{stats['total_interactions']}`",
        f"- human-reviewed drops: `{stats['human_reviewed_drops']}`",
        f"- post-review technical rejects (including human drops): "
        f"`{stats['technical_rejects_after_review']}`",
        f"- post-review technical rejects excluding human drops: "
        f"`{stats['technical_rejects_excluding_human_drop']}`",
        f"- parked ssDNA: `{stats['parked_ssdna']}`",
        f"- parked RNA non-protein: `{stats['parked_non_protein']}`",
        f"- RNA-protein technically eligible: `{stats['technically_eligible']}`",
        "",
        "Reconciliation: technical rejects + parked ssDNA + parked RNA",
        "non-protein + technically eligible = total interactions.",
        "",
        "## Route changes",
        "",
        f"- records whose primary route changed: `{stats['route_changed']}`",
    ]
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
            "## Transformation counts",
            "",
            f"- source-sequence corrections: `{stats['sequence_corrections']}`",
            f"- molecule-type overrides: `{stats['molecule_overrides']}`",
            f"- records actually trimmed: `{stats['records_trimmed']}`",
            f"- trimmed by group decision: `{stats['trimmed_by_group']}`",
            f"- trimmed by record-level override: "
            f"`{stats['trimmed_by_record_override']}`",
            f"- cores changed: `{stats['core_length_changed']}`",
            f"- human-approved >40% trims: "
            f"`{stats.get('large_trim_human_approved', 0)}`",
            f"- remaining guard-rail failures: `{stats['guard_rail_failures']}`",
            "",
            "## Core-length distribution (applied canonical, all routes)",
            "",
            "| metric | after |",
            "|---|---:|",
            f"| min | `{stats['after_core_min']}` |",
            f"| median | `{stats['after_core_median']}` |",
            f"| max | `{stats['after_core_max']}` |",
            f"| <20 | `{stats['after_core_lt20']}` |",
            f"| 20–25 | `{stats['after_core_20_25']}` |",
            f"| 26–89 | `{stats['after_core_26_89']}` |",
            f"| 90–100 | `{stats['after_core_90_100']}` |",
            f"| >100 | `{stats['after_core_gt100']}` |",
            "",
            "Rejected and parked rows remain in the applied canonical file;",
            "their presence is not an application failure. Routing determines",
            "eligibility.",
            "",
            "## Unlinked aptamers (outside the 1,350 interaction denominator)",
            "",
            f"- unlinked aptamers: `{stats['unlinked_aptamers']}`",
            f"- missing_target rejection entries: "
            f"`{stats['unlinked_missing_target']}`",
            "",
            "## Closure checks",
            "",
            f"- dry-run vs applied comparison: "
            f"{'pass' if preview_comparison_ok else 'fail'}",
            f"- deterministic rerun: {'pass' if deterministic_ok else 'skipped'}",
            f"- checkpoint_closed: `true`",
            f"- authorised_for_s4: `{stats['technically_eligible']}`",
            f"- s4_started: `false`",
            f"- S2 SHA-256: `{integrity.get('s2', '')}`",
            f"- S3 SHA-256: `{integrity.get('s3', '')}`",
            f"- sidecar SHA-256: `{integrity.get('sidecar', '')}`",
            f"- raw interaction SHA-256: `{integrity.get('raw_interaction', '')}`",
            f"- raw aptamer SHA-256: `{integrity.get('raw_aptamer', '')}`",
            f"- raw protein SHA-256: `{integrity.get('raw_protein', '')}`",
            "",
            "## Applied output hashes",
            "",
        ]
    )
    for name, digest in output_hashes.items():
        lines.append(f"- {name}: `{digest}`")
    lines.extend(
        [
            "",
            "## Pipeline stop",
            "",
            "CHECKPOINT-1 is closed.",
            "S4 has not started.",
            "",
        ]
    )
    return "\n".join(lines)
