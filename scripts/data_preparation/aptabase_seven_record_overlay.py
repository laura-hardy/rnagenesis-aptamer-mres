#!/usr/bin/env python3
"""Overlay seven approved Aptabase corrections onto the frozen checkpoint.

Does not rerun the shared sequence normaliser. Non-seven rows are copied
unchanged from the frozen 610-row audit baseline and the frozen review queue.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s2 import (  # noqa: E402
    CORRECTION_CONFIG_REL,
    OPERATION_REPLACE_CORE,
    OPERATION_SET_MOLECULE,
    AptabaseRecordCorrection,
    load_aptabase_record_corrections,
)
from checkpoint1_apply_review import (  # noqa: E402
    MANIFEST_COLUMNS,
    PARKED_ID_COLUMNS,
    REJECTED_ID_COLUMNS,
    RESOLUTION_COLUMNS,
    S4_ID_COLUMNS,
    build_manifest_row,
    resolve_active_review_row,
)
from common.corpus_schema import CORPUS_COLUMNS, empty_corpus_record  # noqa: E402

FROZEN_BASELINE_REL = (
    "data/interim/checkpoints/aptabase_cp1/audit/"
    "aptabase_checkpoint1_local_detail.csv"
)
FROZEN_REVIEW_REL = (
    "data/interim/checkpoints/aptabase_cp1/manual_review/"
    "aptabase_checkpoint1_manual_review.csv"
)
FROZEN_RESOLUTION_REL = (
    "data/interim/checkpoints/aptabase_cp1/resolved/"
    "aptabase_checkpoint1_resolution.csv"
)
DEFAULT_OUTPUT_REL = (
    "data/interim/checkpoints/aptabase_cp1/seven_record_overlay_preview"
)
S1_CANONICAL_REL = "data/interim/extracted/aptabase_extracted.csv"
RESOLVED_DIR_REL = "data/interim/checkpoints/aptabase_cp1/resolved"
CANONICAL_OUT_REL = "data/interim/checkpoints/aptabase_cp1/aptabase_s3_canonical.csv"
TRACKED_RESOLUTIONS_REL = "config/checkpoint_reviews/aptabase_checkpoint1_resolutions.csv"
TRACKED_METADATA_REL = "config/checkpoint_reviews/aptabase_checkpoint1_metadata.json"
OVERLAY_METADATA_REL = (
    "config/checkpoint_reviews/aptabase_seven_record_overlay_metadata.json"
)
S4_SOURCE_CONFIG_REL = "config/global_s4_sources/aptabase.json"
APPROVED_IDS = (
    "aptabase:592",
    "aptabase:593",
    "aptabase:104",
    "aptabase:185",
    "aptabase:118",
    "aptabase:123",
    "aptabase:82",
)

STALE_FLAGS = {
    "mixed_t_u",
    "t_in_reported_rna",
    "u_in_reported_dna",
    "trim_requires_review",
    "molecule_type_unknown",
    "core_below_min_length",
    "core_above_max_length",
}

ROUTE_PARK_SSDNA = ("proposed_park", "ssdna_not_eligible_for_rna_training", "04_park_ssdna")
ROUTE_REJECT_SHORT = ("proposed_reject", "core_below_minimum", "01_reject_review")
ROUTE_ACCEPT = ("proposed_accept", "technically_eligible_rna", "02_accept_with_diagnostics")


class OverlayError(ValueError):
    """Frozen Aptabase overlay failed its record-scope checks."""


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise OverlayError(f"Missing header: {path}")
        return list(reader.fieldnames), list(reader)


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _route(correction: AptabaseRecordCorrection) -> tuple[str, str, str]:
    if correction.operation == OPERATION_SET_MOLECULE:
        if correction.molecule_type != "ssDNA":
            raise OverlayError(f"{correction.record_id} retain operation must be ssDNA")
        return ROUTE_PARK_SSDNA
    if correction.operation != OPERATION_REPLACE_CORE:
        raise OverlayError(f"Unsupported operation for {correction.record_id}")
    if correction.expected_core_length < 20:
        return ROUTE_REJECT_SHORT
    if correction.expected_core_length > 100:
        raise OverlayError(f"{correction.record_id} core is above the existing maximum")
    return ROUTE_ACCEPT


def _qc_flags(existing: str, correction: AptabaseRecordCorrection) -> str:
    flags = [part for part in existing.split("|") if part and part not in STALE_FLAGS]
    if correction.expected_core_length < 20:
        flags.append("core_below_min_length")
    flags.append("approved_aptabase_record_correction")
    if correction.note:
        flags.append(correction.note)
    return "|".join(sorted(set(flags)))


def overlay_baseline_row(
    row: Mapping[str, str],
    correction: AptabaseRecordCorrection,
) -> dict[str, str]:
    """Return one corrected baseline row. sequence_raw is preserved."""
    updated = dict(row)
    if updated.get("sequence_raw", "") == "":
        raise OverlayError(f"{correction.record_id} frozen sequence_raw is empty")
    if correction.operation == OPERATION_REPLACE_CORE:
        updated["sequence_full"] = correction.sequence_core
        updated["sequence_core"] = correction.sequence_core
        updated["sequence_length_full"] = str(correction.expected_core_length)
        updated["sequence_length_core"] = str(correction.expected_core_length)
        updated["trim_status"] = "primers_removed"
    elif updated.get("sequence_core") != correction.sequence_core:
        raise OverlayError(
            f"{correction.record_id} frozen core does not match the retained DNA sequence"
        )
    updated["molecule_type"] = correction.molecule_type
    updated["alphabet_as_reported"] = correction.alphabet_as_reported
    updated["t_to_u_applied"] = "false"
    updated["chemistry"] = correction.chemistry
    decision, reason, _batch = _route(correction)
    updated["proposed_decision"] = decision
    updated["primary_reason"] = reason
    updated["secondary_reasons"] = ""
    updated["qc_flags"] = _qc_flags(row.get("qc_flags", ""), correction)
    if updated["sequence_raw"] != row["sequence_raw"]:
        raise OverlayError(f"{correction.record_id} sequence_raw changed")
    return updated


def overlay_review_row(
    row: Mapping[str, str],
    correction: AptabaseRecordCorrection,
    baseline: Mapping[str, str],
) -> dict[str, str]:
    """Update one frozen review row from its overlaid baseline row."""
    updated = dict(row)
    for field in (
        "sequence_full",
        "sequence_core",
        "sequence_length_full",
        "sequence_length_core",
        "molecule_type",
        "alphabet_as_reported",
        "t_to_u_applied",
        "trim_status",
        "qc_flags",
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
    ):
        if field in updated:
            updated[field] = baseline[field]
    _decision, _reason, batch = _route(correction)
    updated["review_batch"] = batch
    updated["review_action"] = "confirm_current"
    if updated["sequence_raw"] != row["sequence_raw"]:
        raise OverlayError(f"{correction.record_id} review sequence_raw changed")
    return updated


def build_overlay(
    *,
    repo_root: Path,
    baseline_path: Path | None = None,
    review_path: Path | None = None,
    resolution_path: Path | None = None,
    config_path: Path | None = None,
) -> tuple[list[str], list[dict[str, str]], list[str], list[dict[str, str]]]:
    """Copy the frozen 610-row baseline and patch only the approved seven."""
    repo_root = repo_root.resolve()
    baseline_path = baseline_path or (repo_root / FROZEN_BASELINE_REL)
    review_path = review_path or (repo_root / FROZEN_REVIEW_REL)
    resolution_path = resolution_path or (repo_root / FROZEN_RESOLUTION_REL)
    config_path = config_path or (repo_root / CORRECTION_CONFIG_REL)
    for path in (baseline_path, review_path, resolution_path, config_path):
        if not path.is_file():
            raise OverlayError(f"Missing frozen Aptabase input: {path}")

    base_fields, base_rows = _read_csv(baseline_path)
    review_fields, review_rows = _read_csv(review_path)
    _res_fields, resolution_rows = _read_csv(resolution_path)
    if len(base_rows) != 610 or len(resolution_rows) != 610:
        raise OverlayError("Frozen Aptabase baseline must contain 610 rows")
    corrections = load_aptabase_record_corrections(config_path, repo_root=repo_root)
    if set(corrections) != {
        "aptabase:592",
        "aptabase:593",
        "aptabase:104",
        "aptabase:185",
        "aptabase:118",
        "aptabase:123",
        "aptabase:82",
    }:
        raise OverlayError("Correction config is not the approved seven-record set")

    resolved = {row["record_id"]: row for row in resolution_rows}
    if len(resolved) != 610:
        raise OverlayError("Frozen resolution record_ids are not unique")
    for row in base_rows:
        record_id = row["record_id"]
        frozen = resolved[record_id]
        if row["proposed_decision"] != frozen["proposed_decision"]:
            raise OverlayError(f"Baseline decision drifted for {record_id}")
        if row["primary_reason"] != frozen["primary_reason"]:
            raise OverlayError(f"Baseline reason drifted for {record_id}")

    output_fields = list(base_fields)
    if "chemistry" not in output_fields:
        output_fields.append("chemistry")
    overlaid: list[dict[str, str]] = []
    by_id: dict[str, dict[str, str]] = {}
    for row in base_rows:
        record_id = row["record_id"]
        if record_id in corrections:
            updated = overlay_baseline_row(row, corrections[record_id])
        else:
            updated = dict(row)
            updated["chemistry"] = row.get("chemistry", "")
        overlaid.append(updated)
        by_id[record_id] = updated

    review_ids = [row["record_id"] for row in review_rows]
    missing = [record_id for record_id in corrections if record_id not in review_ids]
    if missing:
        raise OverlayError(f"Approved records missing from frozen review: {missing}")
    overlaid_review: list[dict[str, str]] = []
    for row in review_rows:
        record_id = row["record_id"]
        if record_id in corrections:
            overlaid_review.append(
                overlay_review_row(row, corrections[record_id], by_id[record_id])
            )
        else:
            overlaid_review.append(dict(row))
    return output_fields, overlaid, review_fields, overlaid_review


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_overlay_checkpoint(
    baseline_rows: Sequence[Mapping[str, str]],
    review_rows: Sequence[Mapping[str, str]],
    frozen_resolutions: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Apply overlay review actions. Rows outside the review keep the frozen resolution.

    The frozen audit marks some mechanical rejects as review-required even though
    they were excluded from the 431-row human queue. Those rows must stay on the
    closed resolution rather than be re-derived.
    """
    if len(baseline_rows) != 610 or len(frozen_resolutions) != 610:
        raise OverlayError("Overlay baseline and frozen resolutions must have 610 rows")
    review_by_id = {row["record_id"]: row for row in review_rows}
    frozen_by_id = {row["record_id"]: row for row in frozen_resolutions}
    if len(review_by_id) != len(review_rows) or len(frozen_by_id) != 610:
        raise OverlayError("Overlay review or frozen resolution ids are not unique")
    resolutions: list[dict[str, str]] = []
    for row in baseline_rows:
        record_id = row["record_id"]
        if record_id in review_by_id:
            review = review_by_id[record_id]
            if review["proposed_decision"] != row["proposed_decision"]:
                raise OverlayError(f"Review/baseline decision mismatch for {record_id}")
            if review["primary_reason"] != row["primary_reason"]:
                raise OverlayError(f"Review/baseline reason mismatch for {record_id}")
            resolutions.append(resolve_active_review_row(review))
        else:
            frozen = frozen_by_id.get(record_id)
            if frozen is None:
                raise OverlayError(f"Frozen resolution missing for {record_id}")
            resolutions.append({column: frozen.get(column, "") for column in RESOLUTION_COLUMNS})
    if len(resolutions) != 610:
        raise OverlayError("Resolution row count must be 610")
    return resolutions


def canonical_from_s1_and_overlay(
    s1_rows: Sequence[Mapping[str, str]],
    baseline_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Build corpus-schema canonical rows from frozen S1 plus the overlay baseline.

    Does not read the drifted regenerated S2 or S3 canonical files.
    """
    s1_by_id = {row["record_id"]: row for row in s1_rows}
    if len(s1_by_id) != len(baseline_rows):
        raise OverlayError("S1 and overlay baseline row counts differ")
    canonical_rows: list[dict[str, str]] = []
    copied = (
        "sequence_full",
        "sequence_core",
        "sequence_length_full",
        "sequence_length_core",
        "construct_scope",
        "trim_status",
        "molecule_type",
        "alphabet_as_reported",
        "t_to_u_applied",
        "chemistry",
        "qc_flags",
    )
    for baseline in baseline_rows:
        record_id = baseline["record_id"]
        source = s1_by_id.get(record_id)
        if source is None:
            raise OverlayError(f"S1 row missing for {record_id}")
        if source.get("sequence_raw", "") != baseline.get("sequence_raw", ""):
            raise OverlayError(f"S1 sequence_raw does not match frozen baseline for {record_id}")
        canonical = empty_corpus_record()
        for column in CORPUS_COLUMNS:
            if column in source and source[column] != "":
                canonical[column] = source[column]
        for column in copied:
            if column in baseline:
                canonical[column] = baseline.get(column, "")
        canonical["sequence_raw"] = source["sequence_raw"]
        canonical_rows.append(canonical)
    return canonical_rows


def apply_overlay_checkpoint(
    *,
    repo_root: Path,
    overlay_dir: Path,
    resolved_dir: Path,
    canonical_out: Path,
    tracked_resolutions: Path,
    tracked_metadata: Path,
    overlay_metadata: Path,
    s4_source_config: Path,
) -> dict[str, int]:
    """Write CHECKPOINT-1 resolutions from the approved overlay files only."""
    baseline_path = overlay_dir / "aptabase_overlay_baseline.csv"
    review_path = overlay_dir / "aptabase_overlay_review.csv"
    s1_path = repo_root / S1_CANONICAL_REL
    for path in (baseline_path, review_path, s1_path):
        if not path.is_file():
            raise OverlayError(f"Missing overlay apply input: {path}")
    _base_fields, baseline_rows = _read_csv(baseline_path)
    _review_fields, review_rows = _read_csv(review_path)
    _s1_fields, s1_rows = _read_csv(s1_path)
    _frozen_fields, frozen_rows = _read_csv(repo_root / FROZEN_RESOLUTION_REL)
    resolutions = resolve_overlay_checkpoint(baseline_rows, review_rows, frozen_rows)
    canonical_rows = canonical_from_s1_and_overlay(s1_rows, baseline_rows)
    manifest_rows = [build_manifest_row(row) for row in resolutions]
    authorised = [
        {
            "record_id": row["record_id"],
            "resolved_decision": row["resolved_decision"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
        }
        for row in resolutions
        if row["authorised_for_s4"] == "true"
    ]
    parked = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["review_action"],
        }
        for row in resolutions
        if row["resolved_decision"] == "park"
    ]
    rejected = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["review_action"],
        }
        for row in resolutions
        if row["resolved_decision"] == "reject"
    ]
    if len(authorised) + len(parked) + len(rejected) != 610:
        raise OverlayError("Authorised, parked, and rejected rows do not cover 610 records")
    resolved_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(resolved_dir / "aptabase_checkpoint1_resolution.csv", RESOLUTION_COLUMNS, resolutions)
    _write_csv(resolved_dir / "aptabase_s4_authorised_ids.csv", S4_ID_COLUMNS, authorised)
    _write_csv(resolved_dir / "aptabase_checkpoint1_parked_ids.csv", PARKED_ID_COLUMNS, parked)
    _write_csv(resolved_dir / "aptabase_checkpoint1_rejected_ids.csv", REJECTED_ID_COLUMNS, rejected)
    _write_csv(canonical_out, CORPUS_COLUMNS, canonical_rows)
    _write_csv(overlay_dir / "aptabase_overlay_s3_canonical.csv", CORPUS_COLUMNS, canonical_rows)
    _write_csv(tracked_resolutions, MANIFEST_COLUMNS, manifest_rows)
    review_hash = _sha256_file(review_path)
    metadata = {
        "source_key": "aptabase",
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "reviewer_initials_required": False,
        "reviewer_notes_required": False,
        "review_rows": len(review_rows),
        "no_review_rows": 610 - len(review_rows),
        "total_records": 610,
        "review_file_sha256": review_hash,
        "checkpoint_status": "closed",
        "next_stage": "S4_target_normalisation",
        "apply_mode": "seven_record_frozen_overlay",
    }
    tracked_metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    overlay_note = {
        "source_key": "aptabase",
        "apply_mode": "seven_record_frozen_overlay",
        "approved_record_ids": list(APPROVED_IDS),
        "overlay_baseline": str(baseline_path.relative_to(repo_root)),
        "overlay_review": str(review_path.relative_to(repo_root)),
        "frozen_audit_baseline": FROZEN_BASELINE_REL,
        "supersedes": (
            "Previous CHECKPOINT-1 override_to_accept actions for the seven "
            "approved records. Does not adopt the current-normaliser rerun."
        ),
        "authorised_for_s4_count": len(authorised),
        "review_file_sha256": review_hash,
    }
    overlay_metadata.write_text(json.dumps(overlay_note, indent=2) + "\n", encoding="utf-8")
    s4_config = json.loads(s4_source_config.read_text(encoding="utf-8"))
    s4_config["expected_authorised_records"] = len(authorised)
    target_meta = s4_config.get("target_metadata")
    if isinstance(target_meta, dict):
        target_meta["specific_target_present_in_authorised_records"] = len(authorised)
        target_meta["specific_target_missing_in_authorised_records"] = 0
    s4_source_config.write_text(json.dumps(s4_config, indent=2) + "\n", encoding="utf-8")
    return {
        "resolutions": len(resolutions),
        "authorised_for_s4": len(authorised),
        "parked": len(parked),
        "rejected": len(rejected),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the approved overlay review onto CHECKPOINT-1 outputs",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    output_dir = args.output_dir or (repo_root / DEFAULT_OUTPUT_REL)
    if args.apply:
        stats = apply_overlay_checkpoint(
            repo_root=repo_root,
            overlay_dir=output_dir,
            resolved_dir=repo_root / RESOLVED_DIR_REL,
            canonical_out=repo_root / CANONICAL_OUT_REL,
            tracked_resolutions=repo_root / TRACKED_RESOLUTIONS_REL,
            tracked_metadata=repo_root / TRACKED_METADATA_REL,
            overlay_metadata=repo_root / OVERLAY_METADATA_REL,
            s4_source_config=repo_root / S4_SOURCE_CONFIG_REL,
        )
        print(
            "applied "
            f"resolutions={stats['resolutions']} "
            f"authorised_for_s4={stats['authorised_for_s4']} "
            f"parked={stats['parked']} "
            f"rejected={stats['rejected']}"
        )
        return 0
    fields, rows, review_fields, review_rows = build_overlay(repo_root=repo_root)
    _write_csv(output_dir / "aptabase_overlay_baseline.csv", fields, rows)
    _write_csv(output_dir / "aptabase_overlay_review.csv", review_fields, review_rows)
    print(f"overlay_rows={len(rows)}")
    print(f"overlay_review_rows={len(review_rows)}")
    print(f"output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OverlayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
