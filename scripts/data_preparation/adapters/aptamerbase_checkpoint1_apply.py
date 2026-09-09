"""AptamerBase CHECKPOINT-1 real application helpers.

Uses the same simulation/transform as the dry-run. Actual apply requires
explicit authorisation. Does not start S4 or prepare a global-S4 handoff.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from adapters.aptamerbase_checkpoint1_dry_run import (
    CHEMISTRY_PARK_EXPECTATION,
    AptamerBaseDryRunSimulation,
)
from adapters.aptamerbase_s3 import (
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS

APTAMERBASE_APPLY_NOT_AUTHORISED = (
    "Actual AptamerBase CHECKPOINT-1 apply is not authorised. "
    "Pass --authorise-actual-apply after Laura authorises real apply. "
    "Without that flag this dispatcher still permits --dry-run only. "
    "CHECKPOINT-1 remains open and unapplied. Do not write resolved/ "
    "or closure metadata."
)

APTAMERBASE_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    "authorised_for_s4 means the AptamerBase source object is an aptamer, "
    "sequence/molecule/chemistry/construct review is complete, and the "
    "record is technically permitted to enter a future corpus-wide global "
    "S4. It does not mean target identified, target canonicalised, protein "
    "target confirmed, UniProt resolved, evidence score assigned, affinity "
    "resolved, PDB resolved, leakage cleared, final corpus included, "
    "deduplicated, clustered, balanced, or partitioned."
)

AUTHORISED_FOR_S4_MEANING = (
    "authorised_for_s4=true means ONLY: the AptamerBase source object is "
    "an aptamer; sequence/molecule/chemistry/construct review is complete; "
    "and the record is technically permitted to enter a future corpus-wide "
    "global S4. It does NOT mean target identified, target canonicalised, "
    "protein target confirmed, UniProt resolved, evidence score assigned, "
    "affinity resolved, PDB resolved, leakage cleared, final corpus "
    "included, deduplicated, clustered, balanced, or partitioned."
)

SOURCE_DATASET = "aptamerbase_export_2026-06-24"
SOURCE_DENOMINATOR = 2128

FROZEN_APTAMERBASE_RAW_CSV_SHA256 = (
    "40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c"
)
FROZEN_APTAMERBASE_RAW_RDF_SHA256 = (
    "3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c"
)
FROZEN_APTAMERBASE_S1_CANONICAL_SHA256 = (
    "0bb0282033ba0561b2c8d8de1358ae6e5a4e8fa47bfb640c56dc87b177552896"
)
FROZEN_APTAMERBASE_S1_SIDECAR_SHA256 = (
    "47a49f7495648bb11105a77eee9cbcfeabeb7b7b05f357dc433d3edb779f41b7"
)
FROZEN_APTAMERBASE_S2_S3_CANONICAL_SHA256 = (
    "69bcfb97592255bc0d70727991bd68d7bf5dc18f1c47db532b182461ba6d81f8"
)
FROZEN_APTAMERBASE_S3_DECISIONS_SHA256 = (
    "f76127b32e930981e40a1ee15bbd08083fc798c9d0215f33b89c0c8ef026e866"
)
FROZEN_APTAMERBASE_REVIEW_QUEUE_SHA256 = (
    "55000f2ea3cf51e5236c4ba9e44bc2e73d87050cc9c0d1c0e7afe5d995098ae1"
)
FROZEN_APTAMERBASE_REVIEW_BULK_SHA256 = (
    "6ea8217f952c7f66489d9a07a664669023f7230b02f64312c61c2e78226f916a"
)
FROZEN_APTAMERBASE_DRY_RUN_REPORT_SHA256 = (
    "f589fd95317b33266e5b63e465c59e3b11aaa727bd0a5f707474b3c9695bc3af"
)

ACCEPTED_DRY_RUN_ROUTES: dict[str, int] = {
    "technical_rejects_after_review": 395,
    "parked_ssdna": 845,
    "parked_molecule_unresolved": 0,
    "parked_chemistry_review": 7,
    "parked_construct_review": 0,
    "technically_eligible": 881,
}

ACCEPTED_HUMAN_DECISIONS: dict[str, int] = {
    "keep": 0,
    "edit": 119,
    "drop": 50,
}

ACCEPTED_TRANSFORM_COUNTS: dict[str, int] = {
    "audit_only_rows": 122,
    "sequence_corrections": 11,
    "molecule_overrides": 106,
    "records_trimmed": 7,
    "manual_rejects": 50,
}

ACCEPTED_ELIGIBLE_CHEMISTRY: dict[str, int] = {
    "RNA": 758,
    "2F-RNA": 112,
    "2NH2-RNA": 6,
    "mixed": 5,
}

EXPECTED_APPLIED_TRIMS: dict[str, tuple[int, int]] = {
    "aptamerbase:0922": (106, 89),
    "aptamerbase:1738": (98, 81),
    "aptamerbase:1739": (98, 81),
    "aptamerbase:1740": (98, 81),
    "aptamerbase:1741": (98, 81),
    "aptamerbase:1935": (82, 65),
    "aptamerbase:1955": (75, 58),
}

PREVIEW_COMPARISON_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "canonical",
        "aptamerbase_checkpoint1_dry_run_canonical_preview.csv",
        "aptamerbase_checkpoint1_applied_canonical.csv",
    ),
    (
        "routing",
        "aptamerbase_checkpoint1_dry_run_routing_preview.csv",
        "aptamerbase_checkpoint1_applied_routing.csv",
    ),
    (
        "rejection",
        "aptamerbase_checkpoint1_dry_run_rejection_preview.csv",
        "aptamerbase_checkpoint1_applied_rejection.csv",
    ),
    (
        "parked_ssdna",
        "aptamerbase_checkpoint1_dry_run_parked_ssdna_preview.csv",
        "aptamerbase_checkpoint1_applied_parked_ssdna.csv",
    ),
    (
        "parked_molecule",
        "aptamerbase_checkpoint1_dry_run_parked_molecule_preview.csv",
        "aptamerbase_checkpoint1_applied_parked_molecule.csv",
    ),
    (
        "parked_chemistry",
        "aptamerbase_checkpoint1_dry_run_parked_chemistry_preview.csv",
        "aptamerbase_checkpoint1_applied_parked_chemistry.csv",
    ),
    (
        "parked_construct",
        "aptamerbase_checkpoint1_dry_run_parked_construct_preview.csv",
        "aptamerbase_checkpoint1_applied_parked_construct.csv",
    ),
    (
        "eligible",
        "aptamerbase_checkpoint1_dry_run_eligible_preview.csv",
        "aptamerbase_checkpoint1_applied_eligible.csv",
    ),
    (
        "change_report",
        "aptamerbase_checkpoint1_dry_run_change_report.csv",
        "aptamerbase_checkpoint1_applied_change_report.csv",
    ),
    (
        "decision_audit",
        "aptamerbase_checkpoint1_dry_run_decision_audit.csv",
        "aptamerbase_checkpoint1_decision_audit.csv",
    ),
)

APTAMERBASE_TRACKED_RESOLUTION_COLUMNS: tuple[str, ...] = (
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
    "sequence_corrected",
    "molecule_overridden",
    "trim_applied",
    "post_molecule",
    "post_chemistry",
    "post_core_length",
    "post_full_length",
    "trim_status",
)

TRIM_AUDIT_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "trim_5p_nt",
    "trim_3p_nt",
    "pre_full_length",
    "post_full_length",
    "pre_core_length",
    "post_core_length",
    "trim_status",
    "trim_confidence",
)

ROUTE_TO_STATUS: Mapping[str, str] = {
    PRIMARY_ROUTE_ELIGIBLE: "approved_for_s4",
    PRIMARY_ROUTE_REJECT: "rejected_after_checkpoint1",
    PRIMARY_ROUTE_SSDNA: "parked_after_checkpoint1",
    PRIMARY_ROUTE_MOLECULE: "parked_after_checkpoint1",
    PRIMARY_ROUTE_CHEMISTRY_REVIEW: "parked_after_checkpoint1",
    PRIMARY_ROUTE_CONSTRUCT: "parked_after_checkpoint1",
}

CLOSURE_ONLY_FIELDS: tuple[str, ...] = (
    "checkpoint_status",
    "checkpoint_closed",
    "application_mode",
    "review_file_sha256",
    "review_bulk_sha256",
    "accepted_dry_run_report_sha256",
    "raw_sha256",
    "rdf_sha256",
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

TRACKED_SEQUENCE_COLUMN_FRAGMENTS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
    "aptamerbase_sequence",
    "proposed_5p_sequence",
    "proposed_3p_sequence",
    "detected_constant_5p",
    "detected_constant_3p",
    "proposed_sequence",
)

S4_FORBIDDEN_CANONICAL_FIELDS: tuple[str, ...] = (
    "target_name_raw",
    "target_name",
    "target_uniprot",
    "target_type",
    "target_type_source",
    "target_family",
    "target_pfam",
    "pdb_id",
    "binding_evidence_type",
    "binding_evidence_score",
    "affinity_value",
    "affinity_unit",
    "affinity_type",
    "cluster_id",
    "partition",
)

SEMANTIC_RECORD_FIELDS: tuple[str, ...] = (
    "record_id",
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


class AptamerBaseCheckpoint1ApplyError(ValueError):
    """Hard failure while applying AptamerBase CHECKPOINT-1."""


def refuse_unauthorised_apply() -> None:
    raise AptamerBaseCheckpoint1ApplyError(APTAMERBASE_APPLY_NOT_AUTHORISED)


def assert_dry_run_simulation(simulation: AptamerBaseDryRunSimulation) -> None:
    if simulation.stats.get("checkpoint_closed"):
        raise AptamerBaseCheckpoint1ApplyError(
            "Dry-run simulation must not close CHECKPOINT-1"
        )
    if int(simulation.stats.get("authorised_for_s4", 0)) != 0:
        raise AptamerBaseCheckpoint1ApplyError(
            "Dry-run must not authorise records for S4"
        )


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("manual_decision") or "").strip() for row in queue_rows)
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def resolution_status_for_route(route: str) -> str:
    if route not in ROUTE_TO_STATUS:
        raise AptamerBaseCheckpoint1ApplyError(f"Unknown primary_route {route!r}")
    return ROUTE_TO_STATUS[route]


def build_tracked_resolutions(
    *,
    decisions: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
    queue_rows: Sequence[Mapping[str, str]],
    change_report: Sequence[Mapping[str, str]],
    route_changed_ids: Sequence[str],
) -> list[dict[str, str]]:
    review_by_id = {row["record_id"]: row for row in queue_rows}
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    change_by_id = {row["record_id"]: row for row in change_report}
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
        canonical = canonical_by_id.get(record_id, {})
        change = change_by_id.get(record_id, {})
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
                "sequence_corrected": change.get("sequence_corrected", ""),
                "molecule_overridden": change.get("molecule_overridden", ""),
                "trim_applied": (
                    "true"
                    if (change.get("trim_5p_nt") or change.get("trim_3p_nt"))
                    else "false"
                ),
                "post_molecule": canonical.get("molecule_type", ""),
                "post_chemistry": canonical.get("chemistry", ""),
                "post_core_length": canonical.get("sequence_length_core", ""),
                "post_full_length": canonical.get("sequence_length_full", ""),
                "trim_status": canonical.get("trim_status", ""),
            }
        )
    return rows


def build_trim_audit(
    *,
    applied: Sequence[object],
    canonical_before: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in applied:
        five = int(getattr(item, "applied_trim_5p_nt", 0) or 0)
        three = int(getattr(item, "applied_trim_3p_nt", 0) or 0)
        if not five and not three:
            continue
        record_id = str(getattr(item, "record_id"))
        before = canonical_before.get(record_id, {})
        canonical = getattr(item, "canonical", {})
        rows.append(
            {
                "record_id": record_id,
                "native_id": str(canonical.get("native_id", "")),
                "trim_5p_nt": str(five),
                "trim_3p_nt": str(three),
                "pre_full_length": str(before.get("sequence_length_full", "")),
                "post_full_length": str(canonical.get("sequence_length_full", "")),
                "pre_core_length": str(before.get("sequence_length_core", "")),
                "post_core_length": str(canonical.get("sequence_length_core", "")),
                "trim_status": str(canonical.get("trim_status", "")),
                "trim_confidence": str(canonical.get("trim_confidence", "")),
            }
        )
    return rows


def eligible_chemistry_counts(
    eligible_rows: Sequence[Mapping[str, str]],
) -> dict[str, int]:
    counts = Counter(row.get("chemistry", "") for row in eligible_rows)
    return {key: int(counts.get(key, 0)) for key in counts}


def assert_s4_fields_empty(canonical_rows: Sequence[Mapping[str, str]]) -> None:
    forbidden = set(S3_FORBIDDEN_FIELDS) | set(S4_FORBIDDEN_CANONICAL_FIELDS)
    for row in canonical_rows:
        for field_name in forbidden:
            if row.get(field_name, ""):
                raise AptamerBaseCheckpoint1ApplyError(
                    f"Apply populated S4-forbidden field {field_name!r} for "
                    f"{row.get('record_id', '')!r}"
                )


def check_accepted_dry_run_counts(
    *,
    simulation: AptamerBaseDryRunSimulation,
    record_decisions: Mapping[str, int],
) -> None:
    """Fail-closed check of derived counts against the accepted dry-run."""
    stats = simulation.stats
    total = int(stats["total_records"])
    reject_n = int(stats["technical_rejects_after_review"])
    ssdna_n = int(stats["parked_ssdna"])
    mol_n = int(stats["parked_molecule_unresolved"])
    chem_n = int(stats["parked_chemistry_review"])
    construct_n = int(stats["parked_construct_review"])
    eligible_n = int(stats["technically_eligible"])
    if reject_n + ssdna_n + mol_n + chem_n + construct_n + eligible_n != total:
        raise AptamerBaseCheckpoint1ApplyError(
            "Applied routes do not reconcile to the AptamerBase source"
        )
    if total != SOURCE_DENOMINATOR:
        raise AptamerBaseCheckpoint1ApplyError(
            f"Applied source count must be {SOURCE_DENOMINATOR}; got {total}"
        )
    for key, expected in ACCEPTED_DRY_RUN_ROUTES.items():
        got = int(stats[key])
        if got != expected:
            raise AptamerBaseCheckpoint1ApplyError(
                f"Derived {key}={got} differs from accepted dry-run {expected}"
            )
    for key, expected in ACCEPTED_HUMAN_DECISIONS.items():
        got = int(record_decisions.get(key, 0))
        if got != expected:
            raise AptamerBaseCheckpoint1ApplyError(
                f"Human {key}={got} differs from accepted dry-run {expected}"
            )
    for key, expected in ACCEPTED_TRANSFORM_COUNTS.items():
        got = int(stats[key])
        if got != expected:
            raise AptamerBaseCheckpoint1ApplyError(
                f"Derived {key}={got} differs from accepted dry-run {expected}"
            )
    chemistry = eligible_chemistry_counts(simulation.preview_eligible)
    if chemistry != ACCEPTED_ELIGIBLE_CHEMISTRY:
        raise AptamerBaseCheckpoint1ApplyError(
            "Eligible chemistry distribution differs from accepted dry-run: "
            f"{chemistry}"
        )
    park_ids = tuple(
        sorted(row["record_id"] for row in simulation.preview_parked_chemistry)
    )
    if park_ids != CHEMISTRY_PARK_EXPECTATION:
        raise AptamerBaseCheckpoint1ApplyError(
            "Chemistry-park record set differs from accepted dry-run: "
            f"{park_ids}"
        )
    if int(stats["keep_unexpected_route_changes"]) != 0:
        raise AptamerBaseCheckpoint1ApplyError(
            "Keep/bulk-audit decisions must not change pre-review route"
        )
    if simulation.nogo_reasons:
        raise AptamerBaseCheckpoint1ApplyError(
            "Apply fail-closed: " + "; ".join(simulation.nogo_reasons)
        )
    applied_by_id = {item.record_id: item for item in simulation.applied}
    trimmed_ids = [
        item.record_id
        for item in simulation.applied
        if item.applied_trim_5p_nt or item.applied_trim_3p_nt
    ]
    if sorted(trimmed_ids) != sorted(EXPECTED_APPLIED_TRIMS):
        raise AptamerBaseCheckpoint1ApplyError(
            "Applied trim set differs from the seven accepted known-motif trims"
        )
    for record_id, (full_n, core_n) in EXPECTED_APPLIED_TRIMS.items():
        item = applied_by_id.get(record_id)
        if item is None:
            raise AptamerBaseCheckpoint1ApplyError(
                f"Accepted trim record {record_id} was not consumed"
            )
        if item.applied_trim_5p_nt != 17 or item.applied_trim_3p_nt != 0:
            raise AptamerBaseCheckpoint1ApplyError(
                f"{record_id} trim must be 17/0; got "
                f"{item.applied_trim_5p_nt}/{item.applied_trim_3p_nt}"
            )
        if item.sequence_length_full != full_n:
            raise AptamerBaseCheckpoint1ApplyError(
                f"{record_id} full length must be {full_n}; "
                f"got {item.sequence_length_full}"
            )
        if item.sequence_length_core != core_n:
            raise AptamerBaseCheckpoint1ApplyError(
                f"{record_id} core length must be {core_n}; "
                f"got {item.sequence_length_core}"
            )
        if item.sequence_length_core < 20 or item.sequence_length_core > 100:
            raise AptamerBaseCheckpoint1ApplyError(
                f"{record_id} core fell outside 20–100 after trim"
            )
        if full_n and (17 / full_n) > 0.40:
            raise AptamerBaseCheckpoint1ApplyError(
                f"{record_id} trim exceeds the 40% guard rail"
            )
        if item.primary_route_after != PRIMARY_ROUTE_ELIGIBLE:
            raise AptamerBaseCheckpoint1ApplyError(
                f"{record_id} must be technically eligible after the reviewed trim"
            )


def tracked_payload_contains_sequence(text: str) -> bool:
    lowered = text.lower()
    return any(fragment in lowered for fragment in TRACKED_SEQUENCE_COLUMN_FRAGMENTS)


def format_closure_markdown(
    simulation: AptamerBaseDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    chemistry_counts: Mapping[str, int],
    byte_identical: Mapping[str, bool],
    semantic_mismatches: int,
    deterministic_ok: bool,
    preview_comparison_ok: bool,
) -> str:
    stats = simulation.stats
    lines = [
        "# AptamerBase CHECKPOINT-1 closure",
        "",
        APTAMERBASE_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Human CHECKPOINT-1 decisions were applied through the same",
        "`apply_aptamerbase_checkpoint1_package` transformation used by the",
        "accepted dry-run. Pre-review S1/S2/S3 snapshots were not overwritten.",
        "Dry-run previews were not regenerated. Global S4 was not started.",
        "No global-S4 handoff was prepared.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- group review SHA-256: `{review_hashes.get('groups', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        f"- accepted dry-run report SHA-256: "
        f"`{review_hashes.get('dry_run_report', '')}`",
        "",
        "## Human decisions",
        "",
        f"- source denominator: `{stats['total_records']}`",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- judgement-required: `{stats['judgement_required']}`",
        f"- keep: `{record_decisions.get('keep', 0)}`",
        f"- edit: `{record_decisions.get('edit', 0)}`",
        f"- drop: `{record_decisions.get('drop', 0)}`",
        f"- audit-only bulk confirmed: `{stats['audit_only_rows']}`",
        f"- sequence corrections: `{stats['sequence_corrections']}`",
        f"- molecule/chemistry overrides: `{stats['molecule_overrides']}`",
        "",
        "## Final routing",
        "",
        f"- technical/source reject: `{stats['technical_rejects_after_review']}`",
        f"- parked ssDNA: `{stats['parked_ssdna']}`",
        f"- parked molecule unknown: `{stats['parked_molecule_unresolved']}`",
        f"- parked chemistry review: `{stats['parked_chemistry_review']}`",
        f"- parked unresolved construct: `{stats['parked_construct_review']}`",
        f"- technically eligible: `{stats['technically_eligible']}`",
        f"- authorised_for_s4: `{stats['authorised_for_s4']}`",
        "",
        "Reconciliation: reject + ssDNA park + molecule park + chemistry park",
        "+ construct park + technically eligible = source denominator.",
        "",
        AUTHORISED_FOR_S4_MEANING,
        "",
        "## Eligible chemistry",
        "",
    ]
    for name, count in sorted(chemistry_counts.items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reviewed chemistry parks",
            "",
        ]
    )
    for record_id in (
        row["record_id"] for row in simulation.preview_parked_chemistry
    ):
        lines.append(f"- `{record_id}`")
    lines.extend(
        [
            "",
            "## Applied known-motif trims",
            "",
            f"- records trimmed: `{stats['records_trimmed']}`",
            "- each accepted trim is 5′ 17 nt / 3′ 0 nt, applied once",
            "",
            "## Closure checks",
            "",
            f"- dry-run/apply byte-identical payloads: "
            f"`{sum(1 for ok in byte_identical.values() if ok)}/"
            f"{len(byte_identical)}`",
            f"- semantic mismatches: `{semantic_mismatches}`",
            f"- deterministic rerun: "
            f"{'pass' if deterministic_ok else 'skipped'}",
            f"- preview comparison: "
            f"{'pass' if preview_comparison_ok else 'fail'}",
            f"- checkpoint_closed: `true`",
            f"- global_s4_run: `false`",
            "",
            "## Integrity",
            "",
            f"- raw SHA-256: `{integrity.get('raw', '')}`",
            f"- RDF SHA-256: `{integrity.get('rdf', '')}`",
            f"- S1 SHA-256: `{integrity.get('s1', '')}`",
            f"- sidecar SHA-256: `{integrity.get('sidecar', '')}`",
            f"- S2 SHA-256: `{integrity.get('s2', '')}`",
            f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
            f"- pre-review S3 decisions SHA-256: "
            f"`{integrity.get('s3_decisions', '')}`",
            "",
            "## Applied output hashes",
            "",
        ]
    )
    for name, digest in output_hashes.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Pipeline stop",
            "",
            "AptamerBase CHECKPOINT-1 applied and closed.",
            (
                f"{stats['authorised_for_s4']} AptamerBase records are "
                "technically authorised for future global S4."
            ),
            "AptamerBase global-S4 handoff has NOT been prepared.",
            "Global S4 has not been run.",
            "",
        ]
    )
    return "\n".join(lines)
