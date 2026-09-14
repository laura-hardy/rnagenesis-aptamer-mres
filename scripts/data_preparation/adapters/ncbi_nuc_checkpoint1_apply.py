"""NCBI Nucleotide CHECKPOINT-1 apply helpers.

The scientific transformation lives in ``apply_ncbi_nuc_checkpoint1_package``
and ``simulate_ncbi_nuc_checkpoint1_application``. Actual apply requires
``--authorise-actual-apply``. Does not start S4 or prepare a global-S4 handoff.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from adapters.ncbi_nuc_checkpoint1_dry_run import NcbiNucDryRunSimulation
from adapters.ncbi_nuc_checkpoint1_review import (
    CHECKPOINT_STATUS_APPROVED,
    CHECKPOINT_STATUS_PARKED,
    CHECKPOINT_STATUS_REJECTED,
    NcbiNucCheckpoint1ReviewError,
)
from adapters.ncbi_nuc_s3 import (
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS
from s0_build_registry import sha256_file

NCBI_NUC_EXPECTED_TOTAL_ROWS = 18
NCBI_NUC_EXPECTED_REVIEWED_ROWS = 18
SOURCE_DATASET = "ncbi_nuc_genbank_2026-07-27"

NCBI_NUC_APPLY_NOT_AUTHORISED = (
    "NCBI Nucleotide actual CHECKPOINT-1 apply is not authorised. "
    "Pass --authorise-actual-apply after Laura authorises real apply. "
    "Without that flag this dispatcher still permits --dry-run only. "
    "CHECKPOINT-1 remains open and unapplied. Do not write resolved/ "
    "or closure metadata."
)

NCBI_NUC_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    "authorised_for_s4=true means only technical sequence/molecule/source-object "
    "eligibility after NCBI CHECKPOINT-1 and permission to enter future "
    "corpus-wide global S4 preparation. It does not mean protein target "
    "confirmed, target canonicalised, target_name resolved, UniProt "
    "resolved, target family assigned, evidence threshold passed, affinity "
    "resolved, leakage cleared, deduplicated against ENA, final corpus "
    "included, clustered, balanced, or partitioned."
)

AUTHORISED_FOR_S4_MEANING = (
    "authorised_for_s4=true means only: technical sequence/molecule/"
    "source-object eligibility after NCBI CHECKPOINT-1 and permission to "
    "enter future corpus-wide global S4 preparation. It does NOT mean "
    "protein target confirmed, target canonicalised, target_name resolved, "
    "UniProt resolved, target family assigned, evidence threshold passed, "
    "affinity resolved, leakage cleared, deduplicated against ENA, final "
    "corpus included, clustered, balanced, or partitioned."
)

FROZEN_NCBI_NUC_S1_CANONICAL_SHA256 = (
    "329f518e94e0813080545fe61d823ad44607ec8a193e14498fc62a91d647e9dc"
)
FROZEN_NCBI_NUC_S1_SIDECAR_SHA256 = (
    "f1d003f64e7a9619d94b7025838e229b4ec7655fa93f9bda2bf34e2ba0021fe1"
)
FROZEN_NCBI_NUC_S2_CANONICAL_SHA256 = (
    "965cd5a88426c40f54b43afb9fbe7fdb9688c16ff53fad3ef8858ee9ef86824c"
)
FROZEN_NCBI_NUC_S2_QC_SHA256 = (
    "6639c15db9752370f3bd65702d8740776d50e0082aa9724181fdea7aa6729342"
)
FROZEN_NCBI_NUC_S3_CANONICAL_SHA256 = FROZEN_NCBI_NUC_S2_CANONICAL_SHA256
FROZEN_NCBI_NUC_S3_DECISIONS_SHA256 = (
    "1fc014981832b83be04eab7d5a3cf957f2b66174dd11f1126d440b25b32b9c8d"
)
FROZEN_NCBI_NUC_REVIEW_QUEUE_SHA256 = (
    "caf1dfab759e8f1d77434953e68b1afa7023b9794f274ae995d9f96c199f71dd"
)
FROZEN_NCBI_NUC_REVIEW_INDEX_SHA256 = (
    "b15522bada3c41aab4be53474b856738e26fdf877dbc339c92b5ea482ed79ab0"
)
FROZEN_NCBI_NUC_REVIEW_BULK_SHA256 = (
    "99a41880756d51e5f2e8ff0ada895eef889756e1eccb65726295a66ca176ca85"
)
FROZEN_NCBI_NUC_RECOMMENDATIONS_SHA256 = (
    "7a10fe0683bebb6fde8456e7cc58ce3607e3c25982d703a7965c300338e817ed"
)
FROZEN_NCBI_NUC_ELIGIBILITY_SHA256 = (
    "3a10960cf64455d930c17c377bd19b75476de4b6eaf08360bb18c4d01030b445"
)
FROZEN_NCBI_NUC_S3_REVIEW_SHA256 = (
    "05444cd3d26aaf6be21bb33a3e65fc3450a6585538cc83c0ef10b110ec5eaa34"
)
FROZEN_NCBI_NUC_S3_LOCAL_DETAIL_SHA256 = (
    "6f8ab47c7546085bc0d7084d627dc55d0d1127fb87edd63850ae4803f42cb0c9"
)
FROZEN_ENA_S1_SHA256 = (
    "3d823f4007cde419e2c5cb4a71230c8febaefbeb237cf54e5888740c02578fac"
)
FROZEN_ENA_S2_SHA256 = (
    "4e88f44a07cfee89014eae17d68b90f70acc23d6a6792f29c8ee8f622e2aa8ca"
)
FROZEN_NCBI_NUC_DRY_RUN_REPORT_SHA256 = (
    "077a4c8459071db1292b996ec78655081115ceb86f52e36c47c35df01ea90442"
)

ACCEPTED_DRY_RUN_PAYLOAD_SHA256: dict[str, str] = {
    "canonical": (
        "1c62154b163f19845749f2c9aab1b831e9f1764c643e6cb3af89be3a84cae324"
    ),
    "routing": (
        "196c928fc34eb16e0e29c2492de91222227fa64f2f18507b39a533d4168996c3"
    ),
    "rejection": (
        "08706f24502fb8e5b2a47be0b2e530261278e864b12193af1817badbda36aaf0"
    ),
    "parked": (
        "5b29b2b29adcd5a856efef20928661d6ddef26ccfd79006ee44c53b9fff4a9fc"
    ),
    "eligible": (
        "c3e48b8299c7f48c99aa8d4fd45a658d07d0089f6678e6cb2a6d0f287597b33e"
    ),
    "change_report": (
        "7d8a0cfebff037a7c3598c0f9bd2e3d3c71e430bdf56789d108c1c232aafae19"
    ),
    "decision_audit": (
        "075b41b4bc7fdd9ac6a05d7387f0c63c12e14b38755b83dd522a9500e010c824"
    ),
}

AUTHORISED_NATIVE_IDS: tuple[str, ...] = (
    "AF083271",
    "BD161067",
    "U34759",
    "U37123",
    "U37124",
)
PARKED_NATIVE_IDS: tuple[str, ...] = (
    "DD421991",
    "DI115369",
    "DI183534",
    "DI198507",
    "DI203649",
    "HV200497",
    "HV507922",
    "HW065069",
    "HW308409",
)
REJECTED_NATIVE_IDS: tuple[str, ...] = (
    "DJ028182",
    "FW366678",
    "FZ422269",
    "QT662269",
)
REJECT_REASONS: dict[str, str] = {
    "FW366678": "primer_like",
    "FZ422269": "primer_like",
    "DJ028182": "non_aptamer_source_object",
    "QT662269": "non_aptamer_source_object",
}

PREVIEW_COMPARISON_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "canonical",
        "ncbi_nuc_checkpoint1_dry_run_canonical_preview.csv",
        "ncbi_nuc_checkpoint1_applied_canonical.csv",
    ),
    (
        "routing",
        "ncbi_nuc_checkpoint1_dry_run_routing_preview.csv",
        "ncbi_nuc_checkpoint1_applied_routing.csv",
    ),
    (
        "rejection",
        "ncbi_nuc_checkpoint1_dry_run_rejection_preview.csv",
        "ncbi_nuc_checkpoint1_applied_rejection.csv",
    ),
    (
        "parked",
        "ncbi_nuc_checkpoint1_dry_run_parked_preview.csv",
        "ncbi_nuc_checkpoint1_applied_parked.csv",
    ),
    (
        "eligible",
        "ncbi_nuc_checkpoint1_dry_run_eligible_preview.csv",
        "ncbi_nuc_checkpoint1_applied_eligible.csv",
    ),
    (
        "change_report",
        "ncbi_nuc_checkpoint1_dry_run_change_report.csv",
        "ncbi_nuc_checkpoint1_applied_change_report.csv",
    ),
    (
        "decision_audit",
        "ncbi_nuc_checkpoint1_dry_run_decision_audit.csv",
        "ncbi_nuc_checkpoint1_decision_audit.csv",
    ),
)

NCBI_NUC_TRACKED_RESOLUTION_COLUMNS: tuple[str, ...] = (
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
)

ROUTE_TO_STATUS: Mapping[str, str] = {
    PRIMARY_ROUTE_ELIGIBLE: CHECKPOINT_STATUS_APPROVED,
    PRIMARY_ROUTE_MOLECULE: CHECKPOINT_STATUS_PARKED,
    PRIMARY_ROUTE_REJECT: CHECKPOINT_STATUS_REJECTED,
}

CLOSURE_ONLY_FIELDS: tuple[str, ...] = (
    "checkpoint_status",
    "checkpoint_closed",
    "application_mode",
    "review_file_sha256",
    "review_index_sha256",
    "review_bulk_sha256",
    "accepted_dry_run_hashes",
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
    "detected_constant_5p",
    "detected_constant_3p",
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
    "accession",
    "cluster_id",
    "partition",
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


class NcbiNucCheckpoint1ApplyError(ValueError):
    """Hard failure while applying NCBI Nucleotide CHECKPOINT-1."""


def frozen_pipeline_hashes() -> dict[str, str]:
    return {
        "s1": FROZEN_NCBI_NUC_S1_CANONICAL_SHA256,
        "sidecar": FROZEN_NCBI_NUC_S1_SIDECAR_SHA256,
        "s2": FROZEN_NCBI_NUC_S2_CANONICAL_SHA256,
        "qc": FROZEN_NCBI_NUC_S2_QC_SHA256,
        "s3": FROZEN_NCBI_NUC_S3_CANONICAL_SHA256,
        "s3_decisions": FROZEN_NCBI_NUC_S3_DECISIONS_SHA256,
        "queue": FROZEN_NCBI_NUC_REVIEW_QUEUE_SHA256,
        "index": FROZEN_NCBI_NUC_REVIEW_INDEX_SHA256,
        "bulk": FROZEN_NCBI_NUC_REVIEW_BULK_SHA256,
        "rec_json": FROZEN_NCBI_NUC_RECOMMENDATIONS_SHA256,
        "eligibility": FROZEN_NCBI_NUC_ELIGIBILITY_SHA256,
        "s3_review": FROZEN_NCBI_NUC_S3_REVIEW_SHA256,
        "s3_local": FROZEN_NCBI_NUC_S3_LOCAL_DETAIL_SHA256,
        "ena_s1": FROZEN_ENA_S1_SHA256,
        "ena_s2": FROZEN_ENA_S2_SHA256,
    }


def refuse_unauthorised_apply() -> None:
    raise NcbiNucCheckpoint1ApplyError(NCBI_NUC_APPLY_NOT_AUTHORISED)


def check_production_expectations(stats: Mapping[str, object]) -> None:
    expected = {
        "total_records": NCBI_NUC_EXPECTED_TOTAL_ROWS,
        "technically_eligible": 5,
        "parked_molecule_unresolved": 9,
        "technical_rejects_after_review": 4,
        "route_changed": 0,
        "sequence_corrections": 0,
        "molecule_overrides": 0,
        "chemistry_overrides": 0,
        "records_trimmed": 0,
        "authorised_for_s4": 0,
        "projected_authorised_for_s4": 5,
        "transition_accept_to_eligible": 5,
        "transition_park_to_park": 9,
        "transition_reject_to_reject": 4,
        "guard_rail_failures": 0,
    }
    mismatches = [
        f"{key}={stats.get(key)!r}"
        for key, value in expected.items()
        if stats.get(key) != value
    ]
    if mismatches:
        raise NcbiNucCheckpoint1ApplyError(
            "Production dry-run routing mismatch: " + "; ".join(mismatches)
        )


def verify_registered_raw_hashes(repo_root: Path) -> dict[str, str]:
    """Confirm the 18 registered NCBI GenBank files still match the registry."""
    registry_path = Path(repo_root) / "config" / "source_registry.csv"
    hashes: dict[str, str] = {}
    with registry_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("source_key") or "").strip() != "ncbi_nuc":
                continue
            rel = (row.get("path") or "").strip()
            expected = (row.get("sha256") or "").strip().lower()
            path = Path(repo_root) / rel
            digest = sha256_file(path)
            if digest != expected:
                raise NcbiNucCheckpoint1ApplyError(
                    f"Registered NCBI raw file hash mismatch: {rel}"
                )
            hashes[rel] = digest
    if len(hashes) != NCBI_NUC_EXPECTED_TOTAL_ROWS:
        raise NcbiNucCheckpoint1ApplyError(
            "Expected "
            f"{NCBI_NUC_EXPECTED_TOTAL_ROWS} registered NCBI raw files; "
            f"got {len(hashes)}"
        )
    return hashes


def assert_no_ena_inputs(paths: Mapping[str, object]) -> None:
    for name in paths:
        lowered = str(name).lower()
        if "ena" in lowered and name not in {"ena_s1", "ena_s2"}:
            raise NcbiNucCheckpoint1ReviewError(
                f"NCBI CHECKPOINT apply must not consume ENA input {name!r}"
            )


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("manual_decision") or "").strip() for row in queue_rows)
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def resolution_status_for_route(route: str) -> str:
    if route not in ROUTE_TO_STATUS:
        raise NcbiNucCheckpoint1ApplyError(f"Unknown primary_route {route!r}")
    return ROUTE_TO_STATUS[route]


def tracked_payload_contains_sequence(text: str) -> bool:
    lowered = text.lower()
    return any(fragment in lowered for fragment in TRACKED_SEQUENCE_COLUMN_FRAGMENTS)


def assert_s4_fields_empty(canonical_rows: Sequence[Mapping[str, str]]) -> None:
    forbidden = set(S3_FORBIDDEN_FIELDS) | set(S4_FORBIDDEN_CANONICAL_FIELDS)
    for row in canonical_rows:
        for field_name in forbidden:
            if row.get(field_name, ""):
                raise NcbiNucCheckpoint1ApplyError(
                    f"Apply populated S4-forbidden field {field_name!r} for "
                    f"{row.get('record_id', '')!r}"
                )


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
                "sequence_corrected": change.get("sequence_corrected", "false"),
                "molecule_overridden": change.get("molecule_overridden", "false"),
                "trim_applied": (
                    "true"
                    if (change.get("trim_5p_nt") or change.get("trim_3p_nt"))
                    else "false"
                ),
                "post_molecule": canonical.get("molecule_type", ""),
                "post_chemistry": canonical.get("chemistry", ""),
                "post_core_length": canonical.get("sequence_length_core", ""),
            }
        )
    return rows


def check_applied_id_sets(
    *,
    eligible_rows: Sequence[Mapping[str, str]],
    parked_rows: Sequence[Mapping[str, str]],
    rejection_rows: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
) -> None:
    eligible_ids = tuple(sorted(row["native_id"] for row in eligible_rows))
    parked_ids = tuple(sorted(row["native_id"] for row in parked_rows))
    rejected_ids = tuple(sorted(row["native_id"] for row in rejection_rows))
    if eligible_ids != AUTHORISED_NATIVE_IDS:
        raise NcbiNucCheckpoint1ApplyError(
            f"Eligible ACCESSION set differs from accepted dry-run: {eligible_ids}"
        )
    if parked_ids != PARKED_NATIVE_IDS:
        raise NcbiNucCheckpoint1ApplyError(
            f"Parked ACCESSION set differs from accepted dry-run: {parked_ids}"
        )
    if rejected_ids != REJECTED_NATIVE_IDS:
        raise NcbiNucCheckpoint1ApplyError(
            f"Rejected ACCESSION set differs from accepted dry-run: {rejected_ids}"
        )
    record_ids = [row["record_id"] for row in canonical_rows]
    native_ids = [row["native_id"] for row in canonical_rows]
    if len(set(record_ids)) != NCBI_NUC_EXPECTED_TOTAL_ROWS:
        raise NcbiNucCheckpoint1ApplyError("Applied canonical lost unique record_id")
    if len(set(native_ids)) != NCBI_NUC_EXPECTED_TOTAL_ROWS:
        raise NcbiNucCheckpoint1ApplyError("Applied canonical lost unique native_id")
    overlapping = (
        set(eligible_ids) & set(parked_ids)
        | set(eligible_ids) & set(rejected_ids)
        | set(parked_ids) & set(rejected_ids)
    )
    if overlapping:
        raise NcbiNucCheckpoint1ApplyError(
            "Records present in more than one final route: "
            + ", ".join(sorted(overlapping))
        )
    routed = set(eligible_ids) | set(parked_ids) | set(rejected_ids)
    if routed != set(native_ids):
        raise NcbiNucCheckpoint1ApplyError(
            "Some NCBI records have zero or extra final routes"
        )
    for row in rejection_rows:
        expected_reason = REJECT_REASONS.get(row["native_id"])
        if expected_reason and row.get("rejection_reason") != expected_reason:
            raise NcbiNucCheckpoint1ApplyError(
                f"{row['native_id']} rejection_reason must be {expected_reason!r}"
            )


def format_closure_markdown(
    simulation: NcbiNucDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    byte_identical: Mapping[str, bool],
    semantic_mismatches: int,
    deterministic_ok: bool,
    preview_comparison_ok: bool,
) -> str:
    stats = simulation.stats
    accession_lines = [
        f"- `{row['native_id']}`: `{row['pre_review_route']}` → "
        f"`{row['post_review_route']}` "
        f"({row['primary_reason_after']})"
        for row in simulation.change_report
    ]
    eligible_ids = [row["native_id"] for row in simulation.preview_eligible]
    parked_ids = [row["native_id"] for row in simulation.preview_parked]
    rejected = [
        f"- `{row['native_id']}`: `{row.get('rejection_reason', '')}`"
        for row in simulation.preview_rejections
    ]
    lines = [
        "# NCBI Nucleotide CHECKPOINT-1 closure",
        "",
        NCBI_NUC_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Human CHECKPOINT-1 decisions were applied through the same",
        "`apply_reviewed_record` / `simulate_ncbi_nuc_checkpoint1_application`",
        "transformation used by the accepted dry-run. Pre-review S1/S2/S3",
        "snapshots were not overwritten. Dry-run previews were not regenerated.",
        "Global S4 was not started. No global-S4 handoff was prepared.",
        "NCBI was not deduplicated against ENA.",
        "Sequences are not printed here.",
        "",
        "## Review inputs",
        "",
        f"- record review SHA-256: `{review_hashes.get('queue', '')}`",
        f"- review index SHA-256: `{review_hashes.get('index', '')}`",
        f"- bulk confirmation SHA-256: `{review_hashes.get('bulk', '')}`",
        f"- recommendations SHA-256: `{review_hashes.get('rec_json', '')}`",
        "",
        "## Human decisions",
        "",
        f"- source records: `{stats['total_records']}`",
        f"- reviewed records: `{stats['reviewed_records']}`",
        f"- human review resolved: `{stats['reviewed_records']}/"
        f"{stats['total_records']}`",
        f"- keep (CSV): `{record_decisions.get('keep', 0)}`",
        f"- edit: `{record_decisions.get('edit', 0)}`",
        f"- drop: `{record_decisions.get('drop', 0)}`",
        f"- audit-only bulk confirmed: `{stats['audit_only_rows']}`",
        f"- sequence corrections: `{stats['sequence_corrections']}`",
        f"- molecule overrides: `{stats['molecule_overrides']}`",
        f"- chemistry overrides: `{stats['chemistry_overrides']}`",
        f"- target corrections: `{stats['target_corrections']}`",
        f"- applied trims: `{stats['records_trimmed']}`",
        f"- route changes: `{stats['route_changed']}`",
        "",
        "## Final routing",
        "",
        f"- technically eligible: `{stats['technically_eligible']}`",
        f"- parked molecule_type_unresolved: `{stats['parked_molecule_unresolved']}`",
        f"- technical rejects: `{stats['technical_rejects_after_review']}`",
        f"- authorised_for_s4: `{stats['authorised_for_s4']}`",
        "",
        "```text",
        f"18 = {stats['technically_eligible']} eligible + "
        f"{stats['parked_molecule_unresolved']} parked + "
        f"{stats['technical_rejects_after_review']} rejected",
        "```",
        "",
        AUTHORISED_FOR_S4_MEANING,
        "",
        "The five authorised records are not final corpus inclusions.",
        "",
        "## Authorised ACCESSION values",
        "",
        *[f"- `{native_id}`" for native_id in eligible_ids],
        "",
        "## Parked ACCESSION values",
        "",
        *[f"- `{native_id}`" for native_id in parked_ids],
        "",
        "## Rejected ACCESSION values",
        "",
        *rejected,
        "",
        "## ACCESSION-level applied routes",
        "",
        *accession_lines,
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
        f"- global_s4_handoff_prepared: `false`",
        f"- global_s4_run: `false`",
        f"- NCBI-ENA deduplication: `false`",
        "",
        "## Integrity",
        "",
        f"- S1 SHA-256: `{integrity.get('s1', '')}`",
        f"- S1 sidecar SHA-256: `{integrity.get('sidecar', '')}`",
        f"- S2 SHA-256: `{integrity.get('s2', '')}`",
        f"- S2 QC SHA-256: `{integrity.get('qc', '')}`",
        f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
        f"- pre-review S3 decisions SHA-256: "
        f"`{integrity.get('s3_decisions', '')}`",
        "",
        "## Applied output hashes",
        "",
    ]
    for name, digest in output_hashes.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Pipeline stop",
            "",
            "NCBI Nucleotide CHECKPOINT-1 applied and closed.",
            (
                f"{stats['authorised_for_s4']} NCBI Nucleotide records are "
                "technically authorised for future global S4."
            ),
            "NCBI Nucleotide global-S4 handoff has NOT been prepared.",
            "Global S4 has not been run.",
            "",
        ]
    )
    return "\n".join(lines)
