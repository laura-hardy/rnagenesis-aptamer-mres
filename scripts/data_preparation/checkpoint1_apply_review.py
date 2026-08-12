#!/usr/bin/env python3
"""Apply and close AptaBase CHECKPOINT-1 human review.

Validates the completed manual-review CSV against a pristine reconstructed
baseline, resolves all CHECKPOINT-1 records (active review + no-review), and
writes tracked sequence-free resolution artefacts plus ignored full outputs.

Does not perform S4 target normalisation. Never reinterprets scientific
judgement from reviewer notes. Never prints sequences or reviewer-note text.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from checkpoint1_prepare_review import (  # noqa: E402
    EXPECTED_ACTIVE_ROWS,
    EXPECTED_NO_REVIEW_ROWS,
    EXPECTED_TOTAL_ROWS,
    MANUAL_REVIEW_COLUMNS,
    SEQUENCE_COLUMNS,
    prepare_aptabase_checkpoint1_review,
    write_csv_atomic,
)
from s0_build_registry import find_repo_root, sha256_file  # noqa: E402

PERMITTED_REVIEW_FIELDS: frozenset[str] = frozenset(
    {"review_action", "reviewer_note", "reviewer_initials"}
)

IMMUTABLE_REVIEW_FIELDS: tuple[str, ...] = tuple(
    column for column in MANUAL_REVIEW_COLUMNS if column not in PERMITTED_REVIEW_FIELDS
)

# Spreadsheet editors commonly coerce these immutable fields. Comparison accepts
# semantic equivalence (not free-form rewrite) while still hard-failing on any
# other immutable-field drift, especially sequences and proposed decisions.
BOOLEAN_IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "t_to_u_applied",
        "sequence_leakage_match",
        "target_leakage_match",
    }
)

NUMERIC_IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "sequence_length_full",
        "sequence_length_core",
        "reported_length_raw",
        "reported_length_difference",
        "gc_reported_raw",
        "gc_calculated_s2",
        "gc_difference_percentage_points",
    }
)

ACTIVE_REVIEW_ACTIONS: frozenset[str] = frozenset(
    {
        "confirm_current",
        "override_to_accept",
        "override_to_park",
        "override_to_reject",
        "needs_source_review",
    }
)

OVERRIDE_ACTIONS: frozenset[str] = frozenset(
    {"override_to_accept", "override_to_park", "override_to_reject"}
)

PROPOSED_TO_RESOLVED: Mapping[str, str] = {
    "proposed_accept": "accept",
    "proposed_park": "park",
    "proposed_reject": "reject",
}

RESOLUTION_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_required",
    "review_action",
    "reviewer_note",
    "reviewer_initials",
    "resolved_decision",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
    "override_applied",
)

MANIFEST_COLUMNS: tuple[str, ...] = (
    "record_id",
    "proposed_decision",
    "manual_review_required",
    "review_action",
    "resolved_decision",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
    "override_applied",
    "reviewer_note_present",
    "reviewer_note_sha256",
)

S4_ID_COLUMNS: tuple[str, ...] = (
    "record_id",
    "resolved_decision",
    "checkpoint1_resolution_status",
)

PARKED_ID_COLUMNS: tuple[str, ...] = (
    "record_id",
    "checkpoint1_resolution_status",
    "review_action",
)

REJECTED_ID_COLUMNS: tuple[str, ...] = (
    "record_id",
    "checkpoint1_resolution_status",
    "review_action",
)

CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to S4."
)

REGISTERED_RAW_REL = "data/raw/aptabase/aptabase_cleaned.csv"
REGISTERED_RAW_SHA256 = (
    "649ca9c2db37743917fc611eb2154ebaf7a3aa1a8a729f05c0f9c61fc376430e"
)

S1_CANONICAL_REL = "data/interim/extracted/aptabase_extracted.csv"
S1_SIDECAR_REL = "data/interim/extracted/aptabase_source_metadata.csv"
S2_CANONICAL_REL = "data/interim/normalised/aptabase_normalised.csv"
S2_QC_REL = "data/interim/normalised/aptabase_s2_qc.csv"


class Checkpoint1ApplyError(ValueError):
    """Hard failure while applying CHECKPOINT-1 review."""


@dataclass
class ResolutionStats:
    """Aggregate-only resolution counts (no sequences or notes)."""

    total_records: int = 0
    review_rows: int = 0
    no_review_rows: int = 0
    action_counts: dict[str, int] = field(default_factory=dict)
    proposed_counts: dict[str, int] = field(default_factory=dict)
    resolved_counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
    override_transition_counts: dict[str, int] = field(default_factory=dict)
    override_direction_counts: dict[str, int] = field(default_factory=dict)
    authorised_for_s4: int = 0
    parked: int = 0
    rejected: int = 0
    needs_source_review: int = 0
    blank_initials_rows: int = 0
    notes_present: int = 0
    notes_absent: int = 0
    notes_optional_ok: bool = False
    pristine_comparison_ok: bool = False
    review_file_sha256: str = ""
    integrity_ok: bool = False
    deterministic_rerun_ok: bool = False


@dataclass(frozen=True)
class ApplyReviewResult:
    """Paths and aggregates from one CHECKPOINT-1 closure run."""

    source_key: str
    stats: ResolutionStats
    output_resolution: Path
    output_s4_ids: Path
    output_parked_ids: Path
    output_rejected_ids: Path
    output_summary: Path
    tracked_manifest: Path
    metadata_out: Path
    review_file_sha256: str
    review_file_unchanged: bool
    integrity_ok: bool


def assert_no_legacy_cleaner_import() -> None:
    """Hard-fail if the legacy AptaBase cleaner module is imported."""
    forbidden = {
        "aptabase_cleaning",
        "scripts.data_preparation.aptabase_cleaning",
    }
    for name in forbidden:
        if name in sys.modules:
            raise Checkpoint1ApplyError(
                "legacy AptaBase cleaner must not be imported by checkpoint apply"
            )


def _resolve_under_repo(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    for value in payload.values():
        if isinstance(value, str) and (
            value.startswith("/") or (len(value) > 2 and value[1] == ":")
        ):
            raise Checkpoint1ApplyError("Metadata must not contain absolute paths")
    text = json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    _write_text_atomic(path, text)


def _read_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise Checkpoint1ApplyError(f"{label} CSV has no header: {path.name}")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
        if "record_id" in row and not (row.get("record_id") or "").strip():
            raise Checkpoint1ApplyError(f"{label} row {index} has blank record_id")
    return rows


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _floats_close(left: float, right: float) -> bool:
    if left == right:
        return True
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= 1e-6 * scale


def _cells_equivalent(field_name: str, reviewed: str, pristine: str) -> bool:
    """Compare immutable cells; tolerate spreadsheet boolean/numeric coercions."""
    if reviewed == pristine:
        return True
    if field_name in BOOLEAN_IMMUTABLE_FIELDS:
        left = reviewed.strip().lower()
        right = pristine.strip().lower()
        return left == right and left in {"true", "false"}
    if field_name in NUMERIC_IMMUTABLE_FIELDS:
        try:
            return _floats_close(float(reviewed), float(pristine))
        except ValueError:
            return False
    return False


def _proposed_to_resolved(proposed: str) -> str:
    if proposed not in PROPOSED_TO_RESOLVED:
        raise Checkpoint1ApplyError(f"Unknown proposed_decision={proposed!r}")
    return PROPOSED_TO_RESOLVED[proposed]


def _assert_output_dir_allowed(repo_root: Path, output_dir: Path) -> Path:
    resolved = _resolve_under_repo(repo_root, output_dir)
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise Checkpoint1ApplyError(
            "Resolved output directory must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise Checkpoint1ApplyError(
            f"Refusing to write resolved outputs under data/raw/: {output_dir}"
        )
    return resolved


def _assert_tracked_path_allowed(repo_root: Path, path: Path) -> Path:
    resolved = _resolve_under_repo(repo_root, path)
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise Checkpoint1ApplyError(
            f"Refusing to write tracked outputs under data/raw/: {path}"
        )
    data_root = (repo_root / "data").resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError:
        return resolved
    raise Checkpoint1ApplyError(
        f"Tracked checkpoint artefacts must not be written under data/: {path}"
    )


def reconstruct_pristine_review_package(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    pristine_dir: Path,
    expected_active_rows: int | None,
    expected_total_rows: int | None,
    enforce_expected_batch_counts: bool,
) -> Path:
    """Reconstruct the unedited review package into an ignored temp directory."""
    pristine_dir = _assert_output_dir_allowed(repo_root, pristine_dir)
    result = prepare_aptabase_checkpoint1_review(
        repo_root=repo_root,
        checkpoint_dir=checkpoint_dir,
        output_dir=pristine_dir,
        expected_active_rows=expected_active_rows,
        expected_total_rows=expected_total_rows,
        enforce_expected_batch_counts=enforce_expected_batch_counts,
    )
    return result.output_queue


def compare_review_to_pristine(
    reviewed_rows: Sequence[Mapping[str, str]],
    pristine_rows: Sequence[Mapping[str, str]],
) -> None:
    """Require exact equality on all non-review fields; report field + record_id only."""
    if len(reviewed_rows) != len(pristine_rows):
        raise Checkpoint1ApplyError(
            "Active review row count differs from pristine baseline: "
            f"{len(reviewed_rows)} vs {len(pristine_rows)}"
        )

    reviewed_ids = [row["record_id"] for row in reviewed_rows]
    pristine_ids = [row["record_id"] for row in pristine_rows]
    if len(set(reviewed_ids)) != len(reviewed_ids):
        dupes = sorted({rid for rid in reviewed_ids if reviewed_ids.count(rid) > 1})
        raise Checkpoint1ApplyError(
            f"Duplicate review row record_id values: {dupes[:5]}"
        )
    if len(set(pristine_ids)) != len(pristine_ids):
        raise Checkpoint1ApplyError("Pristine baseline has duplicate record_id values")

    reviewed_set = set(reviewed_ids)
    pristine_set = set(pristine_ids)
    missing = sorted(pristine_set - reviewed_set)
    extra = sorted(reviewed_set - pristine_set)
    if missing:
        raise Checkpoint1ApplyError(
            f"Missing review row(s) relative to pristine: {missing[:5]}"
        )
    if extra:
        raise Checkpoint1ApplyError(
            f"Extra review row(s) relative to pristine: {extra[:5]}"
        )

    pristine_by_id = {row["record_id"]: row for row in pristine_rows}
    discrepancies: list[str] = []
    for reviewed in reviewed_rows:
        record_id = reviewed["record_id"]
        pristine = pristine_by_id[record_id]
        if reviewed.get("review_order", "") != pristine.get("review_order", ""):
            discrepancies.append(f"review_order:{record_id}")
        for field_name in IMMUTABLE_REVIEW_FIELDS:
            reviewed_value = reviewed.get(field_name, "")
            pristine_value = pristine.get(field_name, "")
            if not _cells_equivalent(field_name, reviewed_value, pristine_value):
                discrepancies.append(f"{field_name}:{record_id}")
                if field_name in SEQUENCE_COLUMNS:
                    # Do not include sequence values; field+id is enough.
                    continue
    if discrepancies:
        preview = "; ".join(discrepancies[:20])
        more = "" if len(discrepancies) <= 20 else f" (+{len(discrepancies) - 20} more)"
        raise Checkpoint1ApplyError(
            "Non-review fields differ from pristine baseline: "
            f"{preview}{more}"
        )


def validate_active_review_actions(
    reviewed_rows: Sequence[Mapping[str, str]],
) -> None:
    """Validate review_action for all active rows; notes and initials are optional."""
    if not reviewed_rows:
        raise Checkpoint1ApplyError("Active review file has no data rows")

    empty_actions: list[str] = []
    unknown_actions: list[str] = []
    for row in reviewed_rows:
        record_id = row.get("record_id", "")
        action = (row.get("review_action") or "").strip()
        if not action:
            empty_actions.append(record_id)
            continue
        if action not in ACTIVE_REVIEW_ACTIONS:
            unknown_actions.append(f"{record_id}:{action}")

    if empty_actions:
        raise Checkpoint1ApplyError(
            f"Empty review_action for {len(empty_actions)} active review row(s); "
            f"examples={empty_actions[:5]}"
        )
    if unknown_actions:
        raise Checkpoint1ApplyError(
            f"Unknown review_action values: {unknown_actions[:5]}"
        )


def resolve_active_review_row(row: Mapping[str, str]) -> dict[str, str]:
    """Map one completed human-review row to a final resolution."""
    action = (row.get("review_action") or "").strip()
    proposed = row["proposed_decision"]
    note = row.get("reviewer_note") or ""
    initials = row.get("reviewer_initials") or ""

    if action == "confirm_current":
        resolved = _proposed_to_resolved(proposed)
        status = {
            "accept": "approved_for_s4",
            "park": "parked_after_checkpoint1",
            "reject": "rejected_after_checkpoint1",
        }[resolved]
    elif action == "override_to_accept":
        resolved = "accept"
        status = "approved_for_s4"
    elif action == "override_to_park":
        resolved = "park"
        status = "parked_after_checkpoint1"
    elif action == "override_to_reject":
        resolved = "reject"
        status = "rejected_after_checkpoint1"
    elif action == "needs_source_review":
        resolved = "park"
        status = "needs_source_review"
    else:
        raise Checkpoint1ApplyError(f"Unhandled review_action={action!r}")

    authorised = resolved == "accept"
    if status == "needs_source_review" and authorised:
        raise Checkpoint1ApplyError(
            "needs_source_review must not be authorised for S4"
        )
    if resolved != "accept" and authorised:
        raise Checkpoint1ApplyError("Only accept may be authorised for S4")

    override_applied = action in OVERRIDE_ACTIONS
    return {
        "record_id": row["record_id"],
        "native_id": row.get("native_id", ""),
        "proposed_decision": proposed,
        "primary_reason": row.get("primary_reason", ""),
        "secondary_reasons": row.get("secondary_reasons", ""),
        "manual_review_required": "true",
        "review_action": action,
        "reviewer_note": note,
        "reviewer_initials": initials,
        "resolved_decision": resolved,
        "checkpoint1_resolution_status": status,
        "authorised_for_s4": _bool_str(authorised),
        "override_applied": _bool_str(override_applied),
    }


def resolve_no_review_row(row: Mapping[str, str]) -> dict[str, str]:
    """Automatically resolve a manual_review_required=false S3 row."""
    proposed = row["proposed_decision"]
    resolved = _proposed_to_resolved(proposed)
    if resolved == "accept":
        status = "approved_for_s4"
    elif resolved == "park":
        status = "parked_after_checkpoint1"
    else:
        status = "rejected_after_checkpoint1"
    return {
        "record_id": row["record_id"],
        "native_id": row.get("native_id", ""),
        "proposed_decision": proposed,
        "primary_reason": row.get("primary_reason", ""),
        "secondary_reasons": row.get("secondary_reasons", ""),
        "manual_review_required": "false",
        "review_action": "not_required",
        "reviewer_note": "",
        "reviewer_initials": "",
        "resolved_decision": resolved,
        "checkpoint1_resolution_status": status,
        "authorised_for_s4": _bool_str(resolved == "accept"),
        "override_applied": "false",
    }


def build_manifest_row(resolution: Mapping[str, str]) -> dict[str, str]:
    """Build one sequence-free tracked manifest row."""
    note = resolution.get("reviewer_note") or ""
    note_present = bool(note.strip())
    return {
        "record_id": resolution["record_id"],
        "proposed_decision": resolution["proposed_decision"],
        "manual_review_required": resolution["manual_review_required"],
        "review_action": resolution["review_action"],
        "resolved_decision": resolution["resolved_decision"],
        "checkpoint1_resolution_status": resolution["checkpoint1_resolution_status"],
        "authorised_for_s4": resolution["authorised_for_s4"],
        "override_applied": resolution["override_applied"],
        "reviewer_note_present": _bool_str(note_present),
        "reviewer_note_sha256": _sha256_text(note) if note_present else "",
    }


def _collect_integrity_hashes(repo_root: Path) -> dict[str, str]:
    paths = {
        "raw": repo_root / REGISTERED_RAW_REL,
        "s1_canonical": repo_root / S1_CANONICAL_REL,
        "s1_sidecar": repo_root / S1_SIDECAR_REL,
        "s2_canonical": repo_root / S2_CANONICAL_REL,
        "s2_qc": repo_root / S2_QC_REL,
    }
    hashes: dict[str, str] = {}
    for key, path in paths.items():
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing integrity input: {path.name}")
        hashes[key] = sha256_file(path)
    return hashes


def _verify_integrity(
    *,
    repo_root: Path,
    before: Mapping[str, str],
    after: Mapping[str, str],
    s3_canonical: Path,
    s3_decisions: Path,
    s3_review: Path,
    s3_hashes_before: Mapping[str, str],
) -> None:
    if before != after:
        changed = [key for key in before if before[key] != after.get(key)]
        raise Checkpoint1ApplyError(
            f"Pipeline integrity failure; changed inputs: {changed}"
        )
    if before.get("raw") != REGISTERED_RAW_SHA256:
        raise Checkpoint1ApplyError(
            "Registered AptaBase raw hash mismatch against expected binding hash"
        )
    for label, path in (
        ("s3_canonical", s3_canonical),
        ("s3_decisions", s3_decisions),
        ("s3_review", s3_review),
    ):
        after_hash = sha256_file(path)
        if after_hash != s3_hashes_before[label]:
            raise Checkpoint1ApplyError(f"{label} changed during checkpoint apply")
    # S3 canonical must remain identical to S2 normalised.
    if sha256_file(s3_canonical) != before["s2_canonical"]:
        raise Checkpoint1ApplyError(
            "S3 canonical hash no longer matches S2 normalised canonical"
        )


def build_resolution_summary(
    *,
    repo_root: Path,
    result: ApplyReviewResult,
) -> str:
    """Build aggregate-only Markdown summary (no sequences or note text)."""
    stats = result.stats
    lines = [
        "# AptaBase CHECKPOINT-1 resolution summary",
        "",
        "## Totals",
        "",
        f"- Total S3 / CHECKPOINT-1 records: `{stats.total_records}`",
        f"- Active review rows: `{stats.review_rows}`",
        f"- No-review rows: `{stats.no_review_rows}`",
        "",
        "## Review-action counts",
        "",
    ]
    for action in (
        "confirm_current",
        "override_to_accept",
        "override_to_park",
        "override_to_reject",
        "needs_source_review",
        "not_required",
    ):
        lines.append(f"- `{action}`: `{stats.action_counts.get(action, 0)}`")

    lines.extend(["", "## Proposed-decision counts", ""])
    for name in ("proposed_accept", "proposed_park", "proposed_reject"):
        lines.append(f"- `{name}`: `{stats.proposed_counts.get(name, 0)}`")

    lines.extend(["", "## Resolved-decision counts", ""])
    for name in ("accept", "park", "reject"):
        lines.append(f"- `{name}`: `{stats.resolved_counts.get(name, 0)}`")

    lines.extend(["", "## Override counts by direction", ""])
    if stats.override_direction_counts:
        for name, count in sorted(stats.override_direction_counts.items()):
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Resolution-status counts",
            "",
            f"- `approved_for_s4`: `{stats.status_counts.get('approved_for_s4', 0)}`",
            f"- `parked_after_checkpoint1`: "
            f"`{stats.status_counts.get('parked_after_checkpoint1', 0)}`",
            f"- `rejected_after_checkpoint1`: "
            f"`{stats.status_counts.get('rejected_after_checkpoint1', 0)}`",
            f"- `needs_source_review`: `{stats.needs_source_review}`",
            "",
            "## Authorisation",
            "",
            f"- Authorised for S4: `{stats.authorised_for_s4}`",
            f"- Parked (including needs_source_review): `{stats.parked}`",
            f"- Rejected: `{stats.rejected}`",
            "",
            "## Validation",
            "",
            f"- Reviewer-notes-optional validation: "
            f"`{'pass' if stats.notes_optional_ok else 'fail'}`",
            f"- Active rows with notes present/absent: "
            f"`{stats.notes_present}` / `{stats.notes_absent}`",
            f"- Blank-initials convention (single reviewer): accepted; "
            f"blank_initials_rows=`{stats.blank_initials_rows}`",
            f"- Pristine-baseline comparison: "
            f"`{'pass' if stats.pristine_comparison_ok else 'fail'}`",
            f"- Review-file SHA-256: `{stats.review_file_sha256}`",
            f"- Raw/S1/S2/S3 integrity: "
            f"`{'pass' if stats.integrity_ok else 'fail'}`",
            f"- Deterministic rerun: "
            f"`{'pass' if stats.deterministic_rerun_ok else 'pending'}`",
            "",
            "## Outputs",
            "",
            f"- Full resolution table: "
            f"`{_relative_display(result.output_resolution, repo_root)}`",
            f"- S4-authorised IDs: "
            f"`{_relative_display(result.output_s4_ids, repo_root)}`",
            f"- Parked IDs: "
            f"`{_relative_display(result.output_parked_ids, repo_root)}`",
            f"- Rejected IDs: "
            f"`{_relative_display(result.output_rejected_ids, repo_root)}`",
            f"- Tracked manifest: "
            f"`{_relative_display(result.tracked_manifest, repo_root)}`",
            f"- Tracked metadata: "
            f"`{_relative_display(result.metadata_out, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            CHECKPOINT_CLOSED_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def apply_aptabase_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    review_file: Path,
    output_dir: Path,
    tracked_manifest: Path,
    metadata_out: Path,
    pristine_dir: Path | None = None,
    expected_active_rows: int | None = EXPECTED_ACTIVE_ROWS,
    expected_total_rows: int | None = EXPECTED_TOTAL_ROWS,
    enforce_expected_batch_counts: bool = True,
    verify_pipeline_integrity: bool = True,
) -> ApplyReviewResult:
    """Validate completed review and close CHECKPOINT-1 for AptaBase."""
    assert_no_legacy_cleaner_import()
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    review_file = _resolve_under_repo(repo_root, review_file)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
    metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)

    if not review_file.is_file():
        raise Checkpoint1ApplyError(f"Missing completed review file: {review_file.name}")

    s3_canonical = checkpoint_dir / "aptabase_s3_canonical.csv"
    s3_decisions = checkpoint_dir / "aptabase_s3_decisions.csv"
    s3_review = checkpoint_dir / "aptabase_checkpoint1_review.csv"
    for path, label in (
        (s3_canonical, "S3 canonical"),
        (s3_decisions, "S3 decisions"),
        (s3_review, "checkpoint review"),
    ):
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing {label} input: {path.name}")

    review_hash_before = sha256_file(review_file)
    integrity_before: dict[str, str] = {}
    s3_hashes_before = {
        "s3_canonical": sha256_file(s3_canonical),
        "s3_decisions": sha256_file(s3_decisions),
        "s3_review": sha256_file(s3_review),
    }
    if verify_pipeline_integrity:
        integrity_before = _collect_integrity_hashes(repo_root)

    # Reconstruct pristine baseline away from the completed human review file.
    if pristine_dir is None:
        pristine_dir = checkpoint_dir / "closure_validation" / "pristine"
    pristine_queue = reconstruct_pristine_review_package(
        repo_root=repo_root,
        checkpoint_dir=checkpoint_dir,
        pristine_dir=pristine_dir,
        expected_active_rows=expected_active_rows,
        expected_total_rows=expected_total_rows,
        enforce_expected_batch_counts=enforce_expected_batch_counts,
    )
    if pristine_queue.resolve() == review_file.resolve():
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the completed human review file with pristine baseline"
        )

    reviewed_rows = _read_csv(review_file, label="completed review")
    pristine_rows = _read_csv(pristine_queue, label="pristine review")
    s3_rows = _read_csv(s3_review, label="checkpoint review")

    if expected_active_rows is not None and len(reviewed_rows) != expected_active_rows:
        raise Checkpoint1ApplyError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(reviewed_rows)}"
        )
    if expected_total_rows is not None and len(s3_rows) != expected_total_rows:
        raise Checkpoint1ApplyError(
            f"S3 / CHECKPOINT-1 row count must be {expected_total_rows}; "
            f"got {len(s3_rows)}"
        )

    # Header must include the full review schema.
    with review_file.open("r", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    missing_cols = [c for c in MANUAL_REVIEW_COLUMNS if c not in header]
    if missing_cols:
        raise Checkpoint1ApplyError(
            f"Completed review missing columns: {missing_cols[:10]}"
        )

    compare_review_to_pristine(reviewed_rows, pristine_rows)
    validate_active_review_actions(reviewed_rows)

    reviewed_by_id = {row["record_id"]: row for row in reviewed_rows}
    resolutions: list[dict[str, str]] = []
    for s3_row in s3_rows:
        required = (s3_row.get("manual_review_required") or "").strip()
        record_id = s3_row["record_id"]
        if required == "true":
            if record_id not in reviewed_by_id:
                raise Checkpoint1ApplyError(
                    f"Active review missing for record_id={record_id!r}"
                )
            resolutions.append(resolve_active_review_row(reviewed_by_id[record_id]))
        elif required == "false":
            if record_id in reviewed_by_id:
                raise Checkpoint1ApplyError(
                    f"No-review record unexpectedly present in active review: "
                    f"{record_id!r}"
                )
            resolutions.append(resolve_no_review_row(s3_row))
        else:
            raise Checkpoint1ApplyError(
                f"manual_review_required must be lowercase true/false; "
                f"got {required!r} for {record_id!r}"
            )

    if expected_total_rows is not None and len(resolutions) != expected_total_rows:
        raise Checkpoint1ApplyError(
            f"Resolution row count must be {expected_total_rows}; "
            f"got {len(resolutions)}"
        )

    # Hard closure assertions.
    resolved_counts = Counter(row["resolved_decision"] for row in resolutions)
    if sum(resolved_counts.values()) != len(resolutions):
        raise Checkpoint1ApplyError("Resolved decision counts do not cover all rows")
    if set(resolved_counts) - {"accept", "park", "reject"}:
        raise Checkpoint1ApplyError(
            f"Unexpected resolved decisions: {sorted(set(resolved_counts))}"
        )
    authorised = [row for row in resolutions if row["authorised_for_s4"] == "true"]
    if len(authorised) != resolved_counts.get("accept", 0):
        raise Checkpoint1ApplyError(
            "authorised_for_s4 count must equal resolved accept count"
        )
    for row in resolutions:
        status = row["checkpoint1_resolution_status"]
        resolved = row["resolved_decision"]
        auth = row["authorised_for_s4"] == "true"
        if status == "needs_source_review" and auth:
            raise Checkpoint1ApplyError(
                "needs_source_review record authorised for S4"
            )
        if resolved == "park" and auth:
            raise Checkpoint1ApplyError("parked record authorised for S4")
        if resolved == "reject" and auth:
            raise Checkpoint1ApplyError("rejected record authorised for S4")
        if resolved == "accept" and not auth:
            raise Checkpoint1ApplyError("accepted record not authorised for S4")
        if resolved == "accept" and status != "approved_for_s4":
            raise Checkpoint1ApplyError("accept without approved_for_s4 status")
        if resolved == "reject" and status != "rejected_after_checkpoint1":
            raise Checkpoint1ApplyError("reject with unexpected status")
        if resolved == "park" and status not in {
            "parked_after_checkpoint1",
            "needs_source_review",
        }:
            raise Checkpoint1ApplyError("park with unexpected status")

    no_review_count = sum(
        1 for row in resolutions if row["manual_review_required"] == "false"
    )
    review_count = sum(
        1 for row in resolutions if row["manual_review_required"] == "true"
    )
    if expected_active_rows is not None and review_count != expected_active_rows:
        raise Checkpoint1ApplyError(
            f"Resolved active-review count must be {expected_active_rows}; "
            f"got {review_count}"
        )
    if (
        expected_total_rows == EXPECTED_TOTAL_ROWS
        and no_review_count != EXPECTED_NO_REVIEW_ROWS
    ):
        raise Checkpoint1ApplyError(
            f"No-review count must be {EXPECTED_NO_REVIEW_ROWS}; got {no_review_count}"
        )

    manifest_rows = [build_manifest_row(row) for row in resolutions]
    s4_rows = [
        {
            "record_id": row["record_id"],
            "resolved_decision": row["resolved_decision"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
        }
        for row in resolutions
        if row["authorised_for_s4"] == "true"
    ]
    parked_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["review_action"],
        }
        for row in resolutions
        if row["resolved_decision"] == "park"
    ]
    rejected_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["review_action"],
        }
        for row in resolutions
        if row["resolved_decision"] == "reject"
    ]

    if len(s4_rows) + len(parked_rows) + len(rejected_rows) != len(resolutions):
        raise Checkpoint1ApplyError("S4/parked/rejected subsets do not reconcile")

    stats = ResolutionStats()
    stats.total_records = len(resolutions)
    stats.review_rows = review_count
    stats.no_review_rows = no_review_count
    stats.action_counts = dict(Counter(row["review_action"] for row in resolutions))
    stats.proposed_counts = dict(
        Counter(row["proposed_decision"] for row in resolutions)
    )
    stats.resolved_counts = dict(resolved_counts)
    stats.status_counts = dict(
        Counter(row["checkpoint1_resolution_status"] for row in resolutions)
    )
    stats.authorised_for_s4 = len(s4_rows)
    stats.parked = len(parked_rows)
    stats.rejected = len(rejected_rows)
    stats.needs_source_review = stats.status_counts.get("needs_source_review", 0)
    stats.blank_initials_rows = sum(
        1
        for row in resolutions
        if row["manual_review_required"] == "true"
        and not (row.get("reviewer_initials") or "").strip()
    )
    active_resolutions = [
        row for row in resolutions if row["manual_review_required"] == "true"
    ]
    stats.notes_present = sum(
        1 for row in active_resolutions if (row.get("reviewer_note") or "").strip()
    )
    stats.notes_absent = len(active_resolutions) - stats.notes_present
    stats.notes_optional_ok = True
    stats.pristine_comparison_ok = True
    stats.review_file_sha256 = review_hash_before

    for row in resolutions:
        if row["override_applied"] != "true":
            continue
        proposed = _proposed_to_resolved(row["proposed_decision"])
        resolved = row["resolved_decision"]
        if proposed == resolved:
            continue
        key = f"{proposed} → {resolved}"
        stats.override_transition_counts[key] = (
            stats.override_transition_counts.get(key, 0) + 1
        )
        direction = row["review_action"]
        stats.override_direction_counts[direction] = (
            stats.override_direction_counts.get(direction, 0) + 1
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_resolution = output_dir / "aptabase_checkpoint1_resolution.csv"
    out_s4 = output_dir / "aptabase_s4_authorised_ids.csv"
    out_parked = output_dir / "aptabase_checkpoint1_parked_ids.csv"
    out_rejected = output_dir / "aptabase_checkpoint1_rejected_ids.csv"
    out_summary = output_dir / "aptabase_checkpoint1_resolution_summary.md"

    write_csv_atomic(out_resolution, RESOLUTION_COLUMNS, resolutions)
    write_csv_atomic(out_s4, S4_ID_COLUMNS, s4_rows)
    write_csv_atomic(out_parked, PARKED_ID_COLUMNS, parked_rows)
    write_csv_atomic(out_rejected, REJECTED_ID_COLUMNS, rejected_rows)
    write_csv_atomic(tracked_manifest, MANIFEST_COLUMNS, manifest_rows)

    metadata = {
        "source_key": "aptabase",
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "reviewer_initials_required": False,
        "reviewer_notes_required": False,
        "review_rows": review_count,
        "no_review_rows": no_review_count,
        "total_records": len(resolutions),
        "review_file_sha256": review_hash_before,
        "checkpoint_status": "closed",
        "next_stage": "S4_target_normalisation",
    }
    _write_json_atomic(metadata_out, metadata)

    review_hash_after = sha256_file(review_file)
    if review_hash_after != review_hash_before:
        raise Checkpoint1ApplyError(
            "Completed review CSV was modified during checkpoint application"
        )

    integrity_ok = True
    if verify_pipeline_integrity:
        integrity_after = _collect_integrity_hashes(repo_root)
        _verify_integrity(
            repo_root=repo_root,
            before=integrity_before,
            after=integrity_after,
            s3_canonical=s3_canonical,
            s3_decisions=s3_decisions,
            s3_review=s3_review,
            s3_hashes_before=s3_hashes_before,
        )
    stats.integrity_ok = integrity_ok

    result = ApplyReviewResult(
        source_key="aptabase",
        stats=stats,
        output_resolution=out_resolution,
        output_s4_ids=out_s4,
        output_parked_ids=out_parked,
        output_rejected_ids=out_rejected,
        output_summary=out_summary,
        tracked_manifest=tracked_manifest,
        metadata_out=metadata_out,
        review_file_sha256=review_hash_before,
        review_file_unchanged=True,
        integrity_ok=integrity_ok,
    )
    summary_text = build_resolution_summary(repo_root=repo_root, result=result)
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary must not contain absolute repository paths"
        )
    if CHECKPOINT_CLOSED_STATEMENT not in summary_text:
        raise Checkpoint1ApplyError("Resolution summary missing checkpoint-closed statement")
    # Never allow sequence-like dumps from notes into summary (aggregate only).
    _write_text_atomic(out_summary, summary_text)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply completed AptaBase CHECKPOINT-1 human review and close the "
            "checkpoint with tracked sequence-free resolution artefacts."
        )
    )
    parser.add_argument("--source", required=True, help="Source key (only aptabase)")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="CHECKPOINT-1 directory (default: data/interim/checkpoints/aptabase_cp1)",
    )
    parser.add_argument(
        "--review-file",
        type=Path,
        default=None,
        help="Completed manual-review CSV path",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Ignored resolved-output directory beneath data/interim",
    )
    parser.add_argument(
        "--tracked-manifest",
        type=Path,
        default=None,
        help="Tracked sequence-free resolutions CSV",
    )
    parser.add_argument(
        "--metadata-out",
        type=Path,
        default=None,
        help="Tracked checkpoint metadata JSON",
    )
    parser.add_argument(
        "--pristine-dir",
        type=Path,
        default=None,
        help="Temporary ignored directory for pristine baseline reconstruction",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--expected-active-rows",
        type=int,
        default=None,
        help="Override expected active review rows (tests only)",
    )
    parser.add_argument(
        "--expected-total-rows",
        type=int,
        default=None,
        help="Override expected checkpoint row count (tests only)",
    )
    parser.add_argument(
        "--skip-expected-batch-counts",
        action="store_true",
        help="Skip hard-coded AptaBase batch-count checks (tests only)",
    )
    parser.add_argument(
        "--skip-pipeline-integrity",
        action="store_true",
        help="Skip raw/S1/S2 integrity checks (tests only)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.source != "aptabase":
            raise Checkpoint1ApplyError(
                f"Unsupported source_key={args.source!r}; only aptabase is implemented"
            )
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise Checkpoint1ApplyError(f"Repository root does not exist: {repo_root}")

        checkpoint_dir = (
            args.checkpoint_dir
            if args.checkpoint_dir is not None
            else Path("data/interim/checkpoints/aptabase_cp1")
        )
        review_file = (
            args.review_file
            if args.review_file is not None
            else Path(checkpoint_dir)
            / "manual_review"
            / "aptabase_checkpoint1_manual_review.csv"
        )
        output_dir = (
            args.output_dir
            if args.output_dir is not None
            else Path(checkpoint_dir) / "resolved"
        )
        tracked_manifest = (
            args.tracked_manifest
            if args.tracked_manifest is not None
            else Path("config/checkpoint_reviews/aptabase_checkpoint1_resolutions.csv")
        )
        metadata_out = (
            args.metadata_out
            if args.metadata_out is not None
            else Path("config/checkpoint_reviews/aptabase_checkpoint1_metadata.json")
        )
        pristine_dir = (
            args.pristine_dir
            if args.pristine_dir is not None
            else Path(checkpoint_dir) / "closure_validation" / "pristine"
        )

        result = apply_aptabase_checkpoint1_review(
            repo_root=repo_root,
            checkpoint_dir=checkpoint_dir,
            review_file=review_file,
            output_dir=output_dir,
            tracked_manifest=tracked_manifest,
            metadata_out=metadata_out,
            pristine_dir=pristine_dir,
            expected_active_rows=(
                EXPECTED_ACTIVE_ROWS
                if args.expected_active_rows is None
                else args.expected_active_rows
            ),
            expected_total_rows=(
                EXPECTED_TOTAL_ROWS
                if args.expected_total_rows is None
                else args.expected_total_rows
            ),
            enforce_expected_batch_counts=not args.skip_expected_batch_counts,
            verify_pipeline_integrity=not args.skip_pipeline_integrity,
        )
    except Checkpoint1ApplyError as exc:
        # Aggregate / field+id diagnostics only — never print sequences or notes.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    print(
        f"source={result.source_key}\n"
        f"checkpoint_status=closed\n"
        f"total_records={stats.total_records}\n"
        f"review_rows={stats.review_rows}\n"
        f"no_review_rows={stats.no_review_rows}\n"
        f"resolved_accept={stats.resolved_counts.get('accept', 0)}\n"
        f"resolved_park={stats.resolved_counts.get('park', 0)}\n"
        f"resolved_reject={stats.resolved_counts.get('reject', 0)}\n"
        f"authorised_for_s4={stats.authorised_for_s4}\n"
        f"needs_source_review={stats.needs_source_review}\n"
        f"review_file_sha256={stats.review_file_sha256}\n"
        f"pristine_comparison={'pass' if stats.pristine_comparison_ok else 'fail'}\n"
        f"integrity={'pass' if result.integrity_ok else 'fail'}\n"
        f"review_file_unchanged="
        f"{'pass' if result.review_file_unchanged else 'fail'}"
    )
    for action, count in sorted(stats.action_counts.items()):
        print(f"action_{action}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
