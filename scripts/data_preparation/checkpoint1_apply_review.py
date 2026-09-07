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
    UTEXAS_EXPECTED_TOTAL_ROWS,
    UTEXAS_MANUAL_REVIEW_COLUMNS,
    UTEXAS_SEQUENCE_COLUMNS,
    prepare_aptabase_checkpoint1_review,
    prepare_utexas_checkpoint1_review,
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
    *,
    immutable_fields: Sequence[str] | None = None,
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
    fields = (
        tuple(immutable_fields)
        if immutable_fields is not None
        else IMMUTABLE_REVIEW_FIELDS
    )
    discrepancies: list[str] = []
    for reviewed in reviewed_rows:
        record_id = reviewed["record_id"]
        pristine = pristine_by_id[record_id]
        if reviewed.get("review_order", "") != pristine.get("review_order", ""):
            discrepancies.append(f"review_order:{record_id}")
        for field_name in fields:
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


UTEXAS_REGISTERED_RAW_REL = (
    "data/raw/UTexas_aptamer_dataset/UTexas Aptamer Database dataset_Sept2023.xlsx"
)
UTEXAS_REGISTERED_RAW_SHA256 = (
    "b5a66beb58d30c5c3d2f36a29ea2cc3678e7d4a6b1bb1a97efc1e166a49fd15c"
)
UTEXAS_S1_CANONICAL_REL = "data/interim/extracted/utexas_extracted.csv"
UTEXAS_S1_SIDECAR_REL = "data/interim/extracted/utexas_source_metadata.csv"
UTEXAS_S2_CANONICAL_REL = "data/interim/normalised/utexas_normalised.csv"
UTEXAS_S2_QC_REL = "data/interim/normalised/utexas_s2_qc.csv"
UTEXAS_CHECKPOINT_CLOSED_STATEMENT = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to future global S4.\n"
    "authorised_for_s4 means technically eligible after UTexas sequence/"
    "molecule/checkpoint review. It does not mean protein target confirmed, "
    "target canonicalised, UniProt resolved, evidence threshold passed, "
    "leakage passed, globally deduplicated, balanced, or final training inclusion."
)
UTEXAS_IMMUTABLE_REVIEW_FIELDS: tuple[str, ...] = tuple(
    column
    for column in UTEXAS_MANUAL_REVIEW_COLUMNS
    if column not in PERMITTED_REVIEW_FIELDS
)
UTEXAS_RESOLUTION_COLUMNS: tuple[str, ...] = RESOLUTION_COLUMNS + ("resolved_reason",)
COMPLEX_CONSTRUCT_REASON = "complex_construct_unresolved"


def populate_utexas_checkpoint1_actions(review_file: Path) -> int:
    """Fill blank active-review actions with confirm_current (UTexas policy)."""
    rows = _read_csv(review_file, label="UTexas active review")
    filled = 0
    for row in rows:
        action = (row.get("review_action") or "").strip()
        if action:
            continue
        row["review_action"] = "confirm_current"
        filled += 1
    if any(not (row.get("review_action") or "").strip() for row in rows):
        raise Checkpoint1ApplyError("UTexas active review still has blank actions")
    write_csv_atomic(review_file, UTEXAS_MANUAL_REVIEW_COLUMNS, rows)
    return filled


def _overlay_utexas_alphabet_resolutions(
    resolutions: list[dict[str, str]],
    alphabet_resolutions: Mapping[str, object],
) -> None:
    """Apply alphabet-exception park/reject overlays, including mechanical rows."""
    from adapters.utexas_alphabet_exceptions import (
        SUGGESTED_CONFIRM_REJECT,
        SUGGESTED_OVERRIDE_PARK,
    )

    by_id = {row["record_id"]: row for row in resolutions}
    for record_id, alphabet in alphabet_resolutions.items():
        if record_id not in by_id:
            raise Checkpoint1ApplyError(
                f"Alphabet resolution record_id missing from CHECKPOINT-1: {record_id}"
            )
        row = by_id[record_id]
        decision = getattr(alphabet, "decision", "")
        note = getattr(alphabet, "review_note", "")
        if decision == SUGGESTED_OVERRIDE_PARK:
            row["review_action"] = "override_to_park"
            row["resolved_decision"] = "park"
            row["checkpoint1_resolution_status"] = "parked_after_checkpoint1"
            row["authorised_for_s4"] = "false"
            row["override_applied"] = "true"
            row["reviewer_note"] = note
            row["resolved_reason"] = COMPLEX_CONSTRUCT_REASON
        elif decision == SUGGESTED_CONFIRM_REJECT:
            if row["resolved_decision"] != "reject":
                row["review_action"] = "override_to_reject"
                row["resolved_decision"] = "reject"
                row["checkpoint1_resolution_status"] = "rejected_after_checkpoint1"
                row["authorised_for_s4"] = "false"
                row["override_applied"] = "true"
            row["reviewer_note"] = note or row.get("reviewer_note", "")
            row["resolved_reason"] = row.get("primary_reason") or "invalid_alphabet"


def _utexas_resolved_reason(row: Mapping[str, str]) -> str:
    if row.get("resolved_reason"):
        return row["resolved_reason"]
    if row.get("resolved_decision") == "accept":
        return "technically_eligible_rna"
    return row.get("primary_reason") or ""


def _collect_utexas_integrity_hashes(repo_root: Path) -> dict[str, str]:
    paths = {
        "raw": repo_root / UTEXAS_REGISTERED_RAW_REL,
        "s1_canonical": repo_root / UTEXAS_S1_CANONICAL_REL,
        "s1_sidecar": repo_root / UTEXAS_S1_SIDECAR_REL,
        "s2_canonical": repo_root / UTEXAS_S2_CANONICAL_REL,
        "s2_qc": repo_root / UTEXAS_S2_QC_REL,
    }
    hashes: dict[str, str] = {}
    for key, path in paths.items():
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing integrity input: {path.name}")
        hashes[key] = sha256_file(path)
    return hashes


def build_utexas_resolution_summary(
    *,
    repo_root: Path,
    result: ApplyReviewResult,
    extra_counts: Mapping[str, int],
) -> str:
    stats = result.stats
    lines = [
        "# UTexas CHECKPOINT-1 resolution summary",
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
            "## Source-specific outcomes",
            "",
            f"- alphabet recoveries applied: `{extra_counts.get('alphabet_recoveries', 0)}`",
            f"- true IUPAC final rejects: `{extra_counts.get('iupac_rejects', 0)}`",
            f"- malformed final rejects: `{extra_counts.get('malformed_rejects', 0)}`",
            f"- complex construct final parks: `{extra_counts.get('complex_parks', 0)}`",
            f"- FANA / unresolved-molecule parks: `{extra_counts.get('fana_parks', 0)}`",
            f"- DNA / ssDNA parks: `{extra_counts.get('dna_parks', 0)}`",
            f"- missing-sequence rejects: `{extra_counts.get('missing_rejects', 0)}`",
            f"- length_out_of_range rejects: `{extra_counts.get('length_rejects', 0)}`",
            "",
            "## QC retained on accepted records",
            "",
            f"- `trim_requires_review`: `{extra_counts.get('accept_trim_review', 0)}`",
            f"- `constants_suspected_unresolved`: "
            f"`{extra_counts.get('accept_constants_unresolved', 0)}`",
            f"- `trim_combined_exceeds_40pct`: "
            f"`{extra_counts.get('accept_trim_40pct', 0)}`",
            f"- medium trim confidence: `{extra_counts.get('accept_medium_trim', 0)}`",
            "",
            "These QC flags are provenance, not eligibility gates, under the",
            "UTexas source-specific CHECKPOINT-1 policy.",
            "",
            "## Authorisation",
            "",
            f"- Authorised for S4: `{stats.authorised_for_s4}`",
            f"- Parked: `{stats.parked}`",
            f"- Rejected: `{stats.rejected}`",
            "",
            "## Validation",
            "",
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
            f"- Parked IDs: `{_relative_display(result.output_parked_ids, repo_root)}`",
            f"- Rejected IDs: "
            f"`{_relative_display(result.output_rejected_ids, repo_root)}`",
            f"- Tracked manifest: "
            f"`{_relative_display(result.tracked_manifest, repo_root)}`",
            f"- Tracked metadata: `{_relative_display(result.metadata_out, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Target/evidence boundary",
            "",
            "- target_name remains unresolved",
            "- target_type remains unresolved",
            "- protein/non-protein filtering not performed",
            "- Kd/Affinity evidence not scored",
            "- leakage not applied",
            "- global deduplication not performed",
            "- balancing not performed",
            "- partitioning not performed",
            "",
            UTEXAS_CHECKPOINT_CLOSED_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def apply_utexas_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    review_file: Path,
    output_dir: Path,
    tracked_manifest: Path,
    metadata_out: Path,
    alphabet_resolutions_path: Path,
    pristine_dir: Path | None = None,
    expected_total_rows: int | None = UTEXAS_EXPECTED_TOTAL_ROWS,
    verify_pipeline_integrity: bool = True,
    populate_confirm_current: bool = True,
    check_deterministic_rerun: bool = False,
) -> ApplyReviewResult:
    """Validate completed UTexas review, overlay alphabet decisions, and close CP1."""
    from adapters.utexas_alphabet_exceptions import (
        load_alphabet_exception_resolutions,
        park_override_ids,
        reject_confirm_ids,
    )

    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    review_file = _resolve_under_repo(repo_root, review_file)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
    metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)
    alphabet_resolutions_path = _resolve_under_repo(repo_root, alphabet_resolutions_path)

    if populate_confirm_current and review_file.is_file():
        populate_utexas_checkpoint1_actions(review_file)
    if not review_file.is_file():
        raise Checkpoint1ApplyError(f"Missing completed review file: {review_file.name}")

    s3_canonical = checkpoint_dir / "utexas_s3_canonical.csv"
    s3_decisions = checkpoint_dir / "utexas_s3_decisions.csv"
    s3_review = checkpoint_dir / "utexas_checkpoint1_review.csv"
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
        integrity_before = _collect_utexas_integrity_hashes(repo_root)
        if integrity_before.get("raw") != UTEXAS_REGISTERED_RAW_SHA256:
            raise Checkpoint1ApplyError("Registered UTexas raw hash mismatch")

    if pristine_dir is None:
        pristine_dir = checkpoint_dir / "closure_validation" / "pristine"
    pristine_dir = _assert_output_dir_allowed(repo_root, pristine_dir)
    pristine_result = prepare_utexas_checkpoint1_review(
        repo_root=repo_root,
        checkpoint_dir=checkpoint_dir,
        output_dir=pristine_dir,
        expected_total_rows=expected_total_rows,
    )
    pristine_queue = pristine_result.output_queue
    if pristine_queue.resolve() == review_file.resolve():
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the completed human review file with pristine baseline"
        )

    reviewed_rows = _read_csv(review_file, label="completed review")
    pristine_rows = _read_csv(pristine_queue, label="pristine review")
    s3_rows = _read_csv(s3_review, label="checkpoint review")
    canonical_rows = _read_csv(s3_canonical, label="S3 canonical")
    if expected_total_rows is not None and len(s3_rows) != expected_total_rows:
        raise Checkpoint1ApplyError(
            f"S3 / CHECKPOINT-1 row count must be {expected_total_rows}; "
            f"got {len(s3_rows)}"
        )
    compare_review_to_pristine(
        reviewed_rows,
        pristine_rows,
        immutable_fields=UTEXAS_IMMUTABLE_REVIEW_FIELDS,
    )
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
            resolved = resolve_active_review_row(reviewed_by_id[record_id])
        elif required == "false":
            if record_id in reviewed_by_id:
                raise Checkpoint1ApplyError(
                    f"No-review record unexpectedly present in active review: "
                    f"{record_id!r}"
                )
            resolved = resolve_no_review_row(s3_row)
        else:
            raise Checkpoint1ApplyError(
                f"manual_review_required must be lowercase true/false; "
                f"got {required!r} for {record_id!r}"
            )
        resolved["resolved_reason"] = _utexas_resolved_reason(resolved)
        resolutions.append(resolved)

    alphabet_resolutions = load_alphabet_exception_resolutions(alphabet_resolutions_path)
    _overlay_utexas_alphabet_resolutions(resolutions, alphabet_resolutions)
    for row in resolutions:
        row["resolved_reason"] = _utexas_resolved_reason(row)

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
    ids = [row["record_id"] for row in resolutions]
    if len(ids) != len(set(ids)):
        raise Checkpoint1ApplyError("Duplicate record_id in UTexas resolutions")
    for row in resolutions:
        status = row["checkpoint1_resolution_status"]
        resolved = row["resolved_decision"]
        auth = row["authorised_for_s4"] == "true"
        if resolved == "accept" and not auth:
            raise Checkpoint1ApplyError("accepted record not authorised for S4")
        if resolved != "accept" and auth:
            raise Checkpoint1ApplyError("non-accept record authorised for S4")
        if resolved == "accept" and status != "approved_for_s4":
            raise Checkpoint1ApplyError("accept without approved_for_s4 status")
        if resolved == "reject" and status != "rejected_after_checkpoint1":
            raise Checkpoint1ApplyError("reject with unexpected status")
        if resolved == "park" and status not in {
            "parked_after_checkpoint1",
            "needs_source_review",
        }:
            raise Checkpoint1ApplyError("park with unexpected status")

    park_ids = park_override_ids(alphabet_resolutions)
    reject_ids = reject_confirm_ids(alphabet_resolutions)
    for record_id in park_ids:
        row = next(item for item in resolutions if item["record_id"] == record_id)
        if row["resolved_decision"] != "park":
            raise Checkpoint1ApplyError("Complex construct did not finish as park")
    for record_id in reject_ids:
        row = next(item for item in resolutions if item["record_id"] == record_id)
        if row["resolved_decision"] != "reject":
            raise Checkpoint1ApplyError("Reviewed IUPAC/malformed case did not reject")

    review_count = sum(
        1 for row in resolutions if row["manual_review_required"] == "true"
    )
    no_review_count = len(resolutions) - review_count
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
        direction = row["review_action"]
        stats.override_direction_counts[direction] = (
            stats.override_direction_counts.get(direction, 0) + 1
        )

    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    accept_ids = {row["record_id"] for row in s4_rows}
    extra_counts = {
        "alphabet_recoveries": sum(
            1
            for item in alphabet_resolutions.values()
            if item.decision == "accept_recovered_sequence"
        ),
        "iupac_rejects": sum(
            1
            for item in alphabet_resolutions.values()
            if item.decision == "confirm_reject"
            and "IUPAC" in (item.review_note or "")
        ),
        "malformed_rejects": sum(
            1
            for item in alphabet_resolutions.values()
            if item.decision == "confirm_reject"
            and "corrupted" in (item.review_note or "")
        ),
        "complex_parks": len(park_ids),
        "fana_parks": sum(
            1
            for row in resolutions
            if row["resolved_decision"] == "park"
            and row.get("primary_reason") == "molecule_type_unresolved"
        ),
        "dna_parks": sum(
            1
            for row in resolutions
            if row["resolved_decision"] == "park"
            and row.get("primary_reason") == "non_rna_molecule"
        ),
        "missing_rejects": sum(
            1
            for row in resolutions
            if row["resolved_decision"] == "reject"
            and row.get("primary_reason") == "missing_sequence"
        ),
        "length_rejects": sum(
            1
            for row in resolutions
            if row["resolved_decision"] == "reject"
            and row.get("primary_reason") == "length_out_of_range"
        ),
        "accept_trim_review": 0,
        "accept_constants_unresolved": 0,
        "accept_trim_40pct": 0,
        "accept_medium_trim": 0,
    }
    for record_id in accept_ids:
        canonical = canonical_by_id[record_id]
        flags = {
            part for part in (canonical.get("qc_flags") or "").split("|") if part
        }
        if "trim_requires_review" in flags:
            extra_counts["accept_trim_review"] += 1
        if "constants_suspected_unresolved" in flags or canonical.get("trim_status") == (
            "constants_suspected_unresolved"
        ):
            extra_counts["accept_constants_unresolved"] += 1
        if "trim_combined_exceeds_40pct" in flags:
            extra_counts["accept_trim_40pct"] += 1
        if (canonical.get("trim_confidence") or "") == "medium":
            extra_counts["accept_medium_trim"] += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    out_resolution = output_dir / "utexas_checkpoint1_resolution.csv"
    out_s4 = output_dir / "utexas_s4_authorised_ids.csv"
    out_parked = output_dir / "utexas_checkpoint1_parked_ids.csv"
    out_rejected = output_dir / "utexas_checkpoint1_rejected_ids.csv"
    out_summary = output_dir / "utexas_checkpoint1_resolution_summary.md"
    write_csv_atomic(out_resolution, UTEXAS_RESOLUTION_COLUMNS, resolutions)
    write_csv_atomic(out_s4, S4_ID_COLUMNS, s4_rows)
    write_csv_atomic(out_parked, PARKED_ID_COLUMNS, parked_rows)
    write_csv_atomic(out_rejected, REJECTED_ID_COLUMNS, rejected_rows)
    write_csv_atomic(tracked_manifest, MANIFEST_COLUMNS, manifest_rows)
    metadata = {
        "source_key": "utexas",
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "reviewer_initials_required": False,
        "reviewer_notes_required": False,
        "review_rows": review_count,
        "no_review_rows": no_review_count,
        "total_records": len(resolutions),
        "review_file_sha256": sha256_file(review_file),
        "checkpoint_status": "closed",
        "next_stage": "global_S4_handoff",
        "authorised_for_s4": len(s4_rows),
        "resolved_accept": resolved_counts.get("accept", 0),
        "resolved_park": resolved_counts.get("park", 0),
        "resolved_reject": resolved_counts.get("reject", 0),
    }
    _write_json_atomic(metadata_out, metadata)

    if verify_pipeline_integrity:
        integrity_after = _collect_utexas_integrity_hashes(repo_root)
        if integrity_before != integrity_after:
            raise Checkpoint1ApplyError("Pipeline integrity failure during UTexas apply")
        for label, path in (
            ("s3_canonical", s3_canonical),
            ("s3_decisions", s3_decisions),
            ("s3_review", s3_review),
        ):
            if sha256_file(path) != s3_hashes_before[label]:
                raise Checkpoint1ApplyError(f"{label} changed during checkpoint apply")
        if sha256_file(s3_canonical) != integrity_before["s2_canonical"]:
            raise Checkpoint1ApplyError(
                "S3 canonical hash no longer matches S2 normalised canonical"
            )
    stats.integrity_ok = True
    stats.review_file_sha256 = sha256_file(review_file)

    result = ApplyReviewResult(
        source_key="utexas",
        stats=stats,
        output_resolution=out_resolution,
        output_s4_ids=out_s4,
        output_parked_ids=out_parked,
        output_rejected_ids=out_rejected,
        output_summary=out_summary,
        tracked_manifest=tracked_manifest,
        metadata_out=metadata_out,
        review_file_sha256=stats.review_file_sha256,
        review_file_unchanged=True,
        integrity_ok=True,
    )
    summary_text = build_utexas_resolution_summary(
        repo_root=repo_root, result=result, extra_counts=extra_counts
    )
    if str(repo_root.resolve()) in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary must not contain absolute repository paths"
        )
    if UTEXAS_CHECKPOINT_CLOSED_STATEMENT not in summary_text:
        raise Checkpoint1ApplyError("Resolution summary missing checkpoint-closed statement")
    _write_text_atomic(out_summary, summary_text)

    if check_deterministic_rerun:
        first_hashes = {
            "resolution": sha256_file(out_resolution),
            "s4": sha256_file(out_s4),
            "parked": sha256_file(out_parked),
            "rejected": sha256_file(out_rejected),
            "summary": sha256_file(out_summary),
            "manifest": sha256_file(tracked_manifest),
            "metadata": sha256_file(metadata_out),
        }
        second = apply_utexas_checkpoint1_review(
            repo_root=repo_root,
            checkpoint_dir=checkpoint_dir,
            review_file=review_file,
            output_dir=output_dir,
            tracked_manifest=tracked_manifest,
            metadata_out=metadata_out,
            alphabet_resolutions_path=alphabet_resolutions_path,
            pristine_dir=pristine_dir,
            expected_total_rows=expected_total_rows,
            verify_pipeline_integrity=verify_pipeline_integrity,
            populate_confirm_current=False,
            check_deterministic_rerun=False,
        )
        second_hashes = {
            "resolution": sha256_file(second.output_resolution),
            "s4": sha256_file(second.output_s4_ids),
            "parked": sha256_file(second.output_parked_ids),
            "rejected": sha256_file(second.output_rejected_ids),
            "summary": sha256_file(second.output_summary),
            "manifest": sha256_file(second.tracked_manifest),
            "metadata": sha256_file(second.metadata_out),
        }
        if first_hashes != second_hashes:
            raise Checkpoint1ApplyError(
                "UTexas CHECKPOINT-1 closure outputs were not byte-identical "
                "across deterministic rerun"
            )
        stats.deterministic_rerun_ok = True
        result = ApplyReviewResult(
            source_key="utexas",
            stats=stats,
            output_resolution=out_resolution,
            output_s4_ids=out_s4,
            output_parked_ids=out_parked,
            output_rejected_ids=out_rejected,
            output_summary=out_summary,
            tracked_manifest=tracked_manifest,
            metadata_out=metadata_out,
            review_file_sha256=stats.review_file_sha256,
            review_file_unchanged=True,
            integrity_ok=True,
        )
        summary_text = build_utexas_resolution_summary(
            repo_root=repo_root, result=result, extra_counts=extra_counts
        )
        _write_text_atomic(out_summary, summary_text)

    return result


DRY_RUN_FORBIDDEN_DIR_NAMES: frozenset[str] = frozenset(
    {"resolved", "s4", "handoff", "authorised_for_s4"}
)
EXPECTED_APTADB_S2_S3_SHA256 = (
    "b4075b602a9e569e3e91a66f1437a8939d56432138b8e9fcd2063920b0028aa5"
)
EXPECTED_APTADB_RAW_SHA256 = {
    "interaction.csv": (
        "6dbd97f20fa6f98d359d697713c43032d5a6a3c1a400d80ef28a150d676dff86"
    ),
    "aptamer.csv": (
        "9d3ab029d1de4408d2406051a68bc0e6da347ee1be1838aee9c938ca3f3fb464"
    ),
    "protein.csv": (
        "4de0d8b105b3318c9704ff64819089f5e17b5c735f0730724052f3e808325f79"
    ),
}


def _assert_aptadb_dry_run_output(path: Path) -> Path:
    resolved = path.resolve()
    lowered = [part.lower() for part in resolved.parts]
    if any(name in DRY_RUN_FORBIDDEN_DIR_NAMES for name in lowered):
        raise Checkpoint1ApplyError(
            f"Dry-run output must not use a resolved/S4 directory: {resolved}"
        )
    return resolved


def _index_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        record_id = row["record_id"]
        if record_id in indexed:
            raise Checkpoint1ApplyError(f"Duplicate record_id {record_id!r}")
        indexed[record_id] = dict(row)
    return indexed


def _serialise_preview_payload(simulation: object) -> bytes:
    from adapters.aptadb_checkpoint1_dry_run import AptaDBDryRunSimulation

    if not isinstance(simulation, AptaDBDryRunSimulation):
        raise Checkpoint1ApplyError("Dry-run payload has unexpected type")
    chunks = [
        json.dumps(simulation.preview_canonical, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_decisions, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_rejections, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_parked_ssdna, sort_keys=True, ensure_ascii=True),
        json.dumps(
            simulation.preview_parked_non_protein, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.group_summaries, sort_keys=True, ensure_ascii=True),
        json.dumps(
            simulation.guard_rail_failure_rows, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(simulation.large_trim_records, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.large_trim_groups, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def run_aptadb_checkpoint1_dry_run(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    check_deterministic_rerun: bool = True,
    expected_interaction_rows: int | None = 1350,
    expected_unlinked_rows: int | None = 37,
) -> None:
    """Simulate AptaDB CHECKPOINT-1 application without closing it."""
    from adapters.aptadb_checkpoint1_dry_run import (
        CHANGE_REPORT_COLUMNS,
        DRY_RUN_BANNER,
        ELIGIBLE_PREVIEW_COLUMNS,
        GROUP_SUMMARY_COLUMNS,
        GUARD_RAIL_FAILURE_COLUMNS,
        LARGE_TRIM_GROUP_COLUMNS,
        LARGE_TRIM_RECORD_COLUMNS,
        format_dry_run_markdown,
        simulate_aptadb_checkpoint1_application,
    )
    from adapters.aptadb_checkpoint1_review import (
        AptaDBCheckpoint1ReviewError,
        load_default_policy,
        read_csv_rows,
        validate_review_package,
    )
    from adapters.aptadb_s2 import load_aptadb_policy
    from adapters.aptadb_s3 import (
        DECISION_COLUMNS,
        PARK_COLUMNS,
        REJECTION_COLUMNS,
        index_constant_proposals,
    )
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    output_dir = _assert_aptadb_dry_run_output(output_dir)
    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "aptadb_checkpoint1_manual_review.csv"
    group_path = review_dir / "aptadb_checkpoint1_constant_group_review.csv"
    bulk_path = review_dir / "aptadb_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "aptadb_s3_canonical.csv"
    decision_path = checkpoint_dir / "aptadb_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_aptadb.csv"
    parked_ssdna_path = checkpoint_dir / "aptadb_s3_parked_ssdna.csv"
    parked_non_protein_path = checkpoint_dir / "aptadb_s3_parked_non_protein.csv"
    s2_path = repo_root / "data" / "interim" / "normalised" / "aptadb_normalised.csv"
    qc_path = repo_root / "data" / "interim" / "normalised" / "aptadb_s2_qc.csv"
    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "aptadb_constant_region_proposals.csv"
    )
    sidecar_path = (
        repo_root / "data" / "interim" / "extracted" / "aptadb_source_metadata.csv"
    )
    unlinked_path = (
        repo_root / "data" / "interim" / "extracted" / "aptadb_unlinked_aptamers.csv"
    )
    rec_json = (
        repo_root / "config" / "checkpoint_reviews" / "aptadb_checkpoint1_recommendations.json"
    )
    raw_dir = repo_root / "data" / "raw" / "AptaDB"

    required = [
        queue_path,
        group_path,
        bulk_path,
        canonical_path,
        decision_path,
        rejection_path,
        s2_path,
        qc_path,
        proposals_path,
        sidecar_path,
        unlinked_path,
    ]
    for path in required:
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing dry-run input: {path.name}")

    hashes_before = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path),
        "bulk": sha256_file(bulk_path),
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "s3_decisions": sha256_file(decision_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path),
        "unlinked": sha256_file(unlinked_path),
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw_interaction": (
            sha256_file(raw_dir / "interaction.csv")
            if (raw_dir / "interaction.csv").is_file()
            else ""
        ),
        "raw_aptamer": (
            sha256_file(raw_dir / "aptamer.csv")
            if (raw_dir / "aptamer.csv").is_file()
            else ""
        ),
        "raw_protein": (
            sha256_file(raw_dir / "protein.csv")
            if (raw_dir / "protein.csv").is_file()
            else ""
        ),
    }
    if hashes_before["s2"] != EXPECTED_APTADB_S2_S3_SHA256 and (
        expected_interaction_rows == 1350
    ):
        raise Checkpoint1ApplyError(
            "S2 canonical SHA-256 does not match the frozen AptaDB value"
        )
    if hashes_before["s3"] != EXPECTED_APTADB_S2_S3_SHA256 and (
        expected_interaction_rows == 1350
    ):
        raise Checkpoint1ApplyError(
            "S3 canonical SHA-256 does not match the frozen AptaDB value"
        )
    if expected_interaction_rows == 1350:
        for name, expected in EXPECTED_APTADB_RAW_SHA256.items():
            key = f"raw_{name.split('.')[0]}"
            if hashes_before[key] != expected:
                raise Checkpoint1ApplyError(
                    f"Raw {name} SHA-256 does not match registry"
                )

    queue_rows = read_csv_rows(queue_path)
    group_rows = read_csv_rows(group_path)
    bulk_rows = read_csv_rows(bulk_path)
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if expected_interaction_rows == 1350 and (
        report.total_review_records != 238
        or report.unresolved_manual_decisions != 0
        or report.unresolved_constant_groups != 0
        or report.unresolved_exceptions != 0
        or report.audit_only_unconfirmed != 0
        or report.blocking_issues
        or report.ready_for_application != 238
        or not report.ok
    ):
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for dry-run application"
        )
    if expected_interaction_rows != 1350 and not report.ok:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for dry-run application"
        )

    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path)
    parked_ssdna = (
        read_csv_rows(parked_ssdna_path) if parked_ssdna_path.is_file() else []
    )
    parked_non_protein = (
        read_csv_rows(parked_non_protein_path)
        if parked_non_protein_path.is_file()
        else []
    )
    qc_rows = read_csv_rows(qc_path)
    sidecar_rows = read_csv_rows(sidecar_path)
    proposal_rows = read_csv_rows(proposals_path)
    unlinked_rows = read_csv_rows(unlinked_path)
    qc_by_id = _index_rows(qc_rows)
    sidecar_by_id = _index_rows(sidecar_rows)
    grouping_mode = "target_name_raw_plus_publication"
    policy_path = repo_root / "config" / "source_normalisation" / "aptadb.json"
    if policy_path.is_file():
        grouping_mode = load_aptadb_policy(policy_path).group_inference_key
    proposals_by_record = index_constant_proposals(
        canonical_rows, proposal_rows, grouping_mode=grouping_mode
    )
    policy = load_default_policy(repo_root)

    def _simulate():
        try:
            return simulate_aptadb_checkpoint1_application(
                queue_rows=queue_rows,
                group_rows=group_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=sidecar_by_id,
                s2_qc_by_id=qc_by_id,
                policy=policy,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                unlinked_rows=unlinked_rows,
                existing_rejection_rows=rejection_rows,
                existing_parked_ssdna=parked_ssdna,
                existing_parked_non_protein=parked_non_protein,
                expected_interaction_rows=expected_interaction_rows,
                expected_unlinked_rows=expected_unlinked_rows,
            )
        except AptaDBCheckpoint1ReviewError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if _serialise_preview_payload(simulation) != _serialise_preview_payload(
            second
        ):
            raise Checkpoint1ApplyError(
                "AptaDB CHECKPOINT-1 dry-run preview was not byte-identical "
                "across deterministic rerun"
            )
        deterministic_ok = True

    output_dir.mkdir(parents=True, exist_ok=True)
    failed = bool(simulation.guard_rail_failure_rows)
    if not failed:
        write_corpus_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_canonical_preview.csv",
            simulation.preview_canonical,
            columns=CORPUS_COLUMNS,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_routing_preview.csv",
            DECISION_COLUMNS,
            simulation.preview_decisions,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_rejection_preview.csv",
            REJECTION_COLUMNS,
            simulation.preview_rejections,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_parked_ssdna_preview.csv",
            PARK_COLUMNS,
            simulation.preview_parked_ssdna,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_parked_non_protein_preview.csv",
            PARK_COLUMNS,
            simulation.preview_parked_non_protein,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_eligible_preview.csv",
            ELIGIBLE_PREVIEW_COLUMNS,
            simulation.preview_eligible,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_change_report.csv",
            CHANGE_REPORT_COLUMNS,
            simulation.change_report,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_large_trim_human_approved.csv",
            LARGE_TRIM_RECORD_COLUMNS,
            simulation.large_trim_records,
        )
        write_csv_atomic(
            output_dir / "aptadb_checkpoint1_dry_run_large_trim_group_summary.csv",
            LARGE_TRIM_GROUP_COLUMNS,
            simulation.large_trim_groups,
        )
    write_csv_atomic(
        output_dir / "aptadb_checkpoint1_dry_run_group_summary.csv",
        GROUP_SUMMARY_COLUMNS,
        simulation.group_summaries,
    )
    write_csv_atomic(
        output_dir / "aptadb_checkpoint1_dry_run_guard_rail_failures.csv",
        GUARD_RAIL_FAILURE_COLUMNS,
        simulation.guard_rail_failure_rows,
    )
    review_hashes = {
        "queue": hashes_before["queue"],
        "groups": hashes_before["groups"],
        "bulk": hashes_before["bulk"],
    }
    integrity = {
        "s2": hashes_before["s2"],
        "s3": hashes_before["s3"],
        "raw_interaction": hashes_before["raw_interaction"],
        "raw_aptamer": hashes_before["raw_aptamer"],
        "raw_protein": hashes_before["raw_protein"],
        "deterministic_ok": "true" if deterministic_ok else "false",
    }
    report_text = format_dry_run_markdown(
        simulation, review_hashes=review_hashes, integrity=integrity
    )
    _write_text_atomic(
        output_dir / "aptadb_checkpoint1_dry_run_report.md", report_text
    )
    _write_text_atomic(
        output_dir / "README.md",
        DRY_RUN_BANNER
        + (
            "\n\nDRY-RUN FAILED CLOSED: remaining absolute trim guard-rail "
            "failures.\n"
            "These files are not an applied CHECKPOINT-1 and not an S4 handoff.\n"
            if failed
            else
            "\n\nThese files are application previews only. They must not be "
            "treated as resolved CHECKPOINT-1 outputs or an S4 handoff.\n"
        ),
    )

    hashes_after = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path),
        "bulk": sha256_file(bulk_path),
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "s3_decisions": sha256_file(decision_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path),
        "unlinked": sha256_file(unlinked_path),
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw_interaction": (
            sha256_file(raw_dir / "interaction.csv")
            if (raw_dir / "interaction.csv").is_file()
            else ""
        ),
        "raw_aptamer": (
            sha256_file(raw_dir / "aptamer.csv")
            if (raw_dir / "aptamer.csv").is_file()
            else ""
        ),
        "raw_protein": (
            sha256_file(raw_dir / "protein.csv")
            if (raw_dir / "protein.csv").is_file()
            else ""
        ),
    }
    if hashes_after != hashes_before:
        raise Checkpoint1ApplyError(
            "Dry-run mutated an input artefact; aborting without treating "
            "preview files as authoritative"
        )

    stats = simulation.stats
    print(
        "source=aptadb\n"
        "mode=dry_run\n"
        "checkpoint_status=unapplied\n"
        f"total_interactions={stats['total_interactions']}\n"
        f"human_reviewed_drops={stats['human_reviewed_drops']}\n"
        f"technical_rejects_after_review={stats['technical_rejects_after_review']}\n"
        f"parked_ssdna={stats['parked_ssdna']}\n"
        f"parked_non_protein={stats['parked_non_protein']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"route_changed={stats['route_changed']}\n"
        f"guard_rail_failures={stats['guard_rail_failures']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        f"review_queue_sha256={hashes_before['queue']}\n"
        f"review_groups_sha256={hashes_before['groups']}\n"
        f"review_bulk_sha256={hashes_before['bulk']}\n"
        f"s2_sha256={hashes_before['s2']}\n"
        f"s3_sha256={hashes_before['s3']}\n"
        f"deterministic_rerun={'pass' if deterministic_ok else 'skipped'}\n"
        "CHECKPOINT-1 is not closed\n"
        "S4 remains blocked"
    )
    if failed:
        raise Checkpoint1ApplyError(
            f"Dry-run fail-closed: {stats['guard_rail_failures']} remaining "
            "absolute trim guard-rail failures. No canonical preview was "
            "authorised. CHECKPOINT-1 remains unapplied."
        )


APPLY_FORBIDDEN_DIR_NAMES: frozenset[str] = frozenset(
    {"dry_run", "s4", "handoff", "authorised_for_s4", "normalised", "extracted"}
)


@dataclass(frozen=True)
class AptaDBApplyResult:
    """Authoritative AptaDB CHECKPOINT-1 apply/closure result."""

    output_dir: Path
    metadata_out: Path
    tracked_manifest: Path
    summary_out: Path
    output_hashes: dict[str, str]
    stats: dict[str, int | str | bool]
    preview_comparison_ok: bool
    deterministic_rerun_ok: bool
    checkpoint_closed: bool


def _assert_aptadb_resolved_output(path: Path, *, checkpoint_dir: Path) -> Path:
    resolved = path.resolve()
    checkpoint_resolved = checkpoint_dir.resolve()
    if resolved == checkpoint_resolved:
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the AptaDB CHECKPOINT-1 snapshot directory"
        )
    dry_run_dir = (checkpoint_resolved / "dry_run").resolve()
    if resolved == dry_run_dir:
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the validated dry-run preview directory"
        )
    lowered = [part.lower() for part in resolved.parts]
    if any(name in APPLY_FORBIDDEN_DIR_NAMES for name in lowered):
        raise Checkpoint1ApplyError(
            f"Resolved output must not use a dry-run/S2/S3/S4 directory: {resolved}"
        )
    return resolved


def _hash_paths(paths: Mapping[str, Path]) -> dict[str, str]:
    hashed: dict[str, str] = {}
    for name, path in paths.items():
        hashed[name] = sha256_file(path) if path.is_file() else ""
    return hashed


def _write_aptadb_transform_csvs(output_dir: Path, simulation: object) -> dict[str, Path]:
    from adapters.aptadb_checkpoint1_dry_run import (
        CHANGE_REPORT_COLUMNS,
        ELIGIBLE_PREVIEW_COLUMNS,
        GROUP_SUMMARY_COLUMNS,
        GUARD_RAIL_FAILURE_COLUMNS,
        LARGE_TRIM_GROUP_COLUMNS,
        LARGE_TRIM_RECORD_COLUMNS,
        AptaDBDryRunSimulation,
    )
    from adapters.aptadb_s3 import DECISION_COLUMNS, PARK_COLUMNS, REJECTION_COLUMNS
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    if not isinstance(simulation, AptaDBDryRunSimulation):
        raise Checkpoint1ApplyError("Apply payload has unexpected type")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "canonical": output_dir / "aptadb_checkpoint1_applied_canonical.csv",
        "routing": output_dir / "aptadb_checkpoint1_applied_routing.csv",
        "rejection": output_dir / "aptadb_checkpoint1_applied_rejection.csv",
        "parked_ssdna": output_dir / "aptadb_checkpoint1_applied_parked_ssdna.csv",
        "parked_non_protein": output_dir / "aptadb_checkpoint1_applied_parked_non_protein.csv",
        "eligible": output_dir / "aptadb_checkpoint1_applied_eligible.csv",
        "change_report": output_dir / "aptadb_checkpoint1_applied_change_report.csv",
        "group_summary": output_dir / "aptadb_checkpoint1_applied_group_summary.csv",
        "large_trim_human_approved": (
            output_dir / "aptadb_checkpoint1_applied_large_trim_human_approved.csv"
        ),
        "large_trim_group_summary": (
            output_dir / "aptadb_checkpoint1_applied_large_trim_group_summary.csv"
        ),
        "guard_rail_failures": (
            output_dir / "aptadb_checkpoint1_applied_guard_rail_failures.csv"
        ),
    }
    write_corpus_csv_atomic(
        paths["canonical"], simulation.preview_canonical, columns=CORPUS_COLUMNS
    )
    write_csv_atomic(paths["routing"], DECISION_COLUMNS, simulation.preview_decisions)
    write_csv_atomic(
        paths["rejection"], REJECTION_COLUMNS, simulation.preview_rejections
    )
    write_csv_atomic(
        paths["parked_ssdna"], PARK_COLUMNS, simulation.preview_parked_ssdna
    )
    write_csv_atomic(
        paths["parked_non_protein"],
        PARK_COLUMNS,
        simulation.preview_parked_non_protein,
    )
    write_csv_atomic(
        paths["eligible"], ELIGIBLE_PREVIEW_COLUMNS, simulation.preview_eligible
    )
    write_csv_atomic(
        paths["change_report"], CHANGE_REPORT_COLUMNS, simulation.change_report
    )
    write_csv_atomic(
        paths["group_summary"], GROUP_SUMMARY_COLUMNS, simulation.group_summaries
    )
    write_csv_atomic(
        paths["large_trim_human_approved"],
        LARGE_TRIM_RECORD_COLUMNS,
        simulation.large_trim_records,
    )
    write_csv_atomic(
        paths["large_trim_group_summary"],
        LARGE_TRIM_GROUP_COLUMNS,
        simulation.large_trim_groups,
    )
    write_csv_atomic(
        paths["guard_rail_failures"],
        GUARD_RAIL_FAILURE_COLUMNS,
        simulation.guard_rail_failure_rows,
    )
    return paths


def _compare_applied_to_preview(
    *,
    applied_paths: Mapping[str, Path],
    preview_dir: Path,
) -> None:
    from adapters.aptadb_checkpoint1_apply import PREVIEW_COMPARISON_FILES

    missing = [
        preview_name
        for _key, preview_name, _applied in PREVIEW_COMPARISON_FILES
        if not (preview_dir / preview_name).is_file()
    ]
    if missing:
        raise Checkpoint1ApplyError(
            "Validated dry-run preview is incomplete; refusing real apply: "
            + ", ".join(missing)
        )
    mismatches: list[str] = []
    for key, preview_name, _applied_name in PREVIEW_COMPARISON_FILES:
        preview_path = preview_dir / preview_name
        applied_path = applied_paths[key]
        if preview_path.read_bytes() != applied_path.read_bytes():
            mismatches.append(key)
    if mismatches:
        raise Checkpoint1ApplyError(
            "Real application is not byte-identical to the validated dry-run "
            "preview for: " + ", ".join(mismatches)
        )


def run_aptadb_checkpoint1_apply(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    tracked_manifest: Path,
    metadata_out: Path,
    preview_dir: Path | None = None,
    check_deterministic_rerun: bool = True,
    expected_interaction_rows: int | None = 1350,
    expected_unlinked_rows: int | None = 37,
    compare_to_preview: bool | None = None,
) -> AptaDBApplyResult:
    """Apply completed AptaDB CHECKPOINT-1 review and close the checkpoint."""
    from adapters.aptadb_checkpoint1_apply import (
        APTADB_CHECKPOINT_CLOSED_STATEMENT,
        APTADB_TRACKED_RESOLUTION_COLUMNS,
        CLOSURE_ONLY_FIELDS,
        EXPECTED_APTADB_REC_JSON_SHA256,
        EXPECTED_APTADB_REVIEW_BULK_SHA256,
        EXPECTED_APTADB_REVIEW_GROUPS_SHA256,
        EXPECTED_APTADB_REVIEW_QUEUE_SHA256,
        EXPECTED_APTADB_SIDECAR_SHA256,
        AptaDBCheckpoint1ApplyError,
        build_tracked_resolutions,
        check_production_expectations,
        count_group_decisions,
        count_manual_decisions,
        format_closure_markdown,
        PREVIEW_COMPARISON_FILES,
    )
    from adapters.aptadb_checkpoint1_dry_run import (
        simulate_aptadb_checkpoint1_application,
    )
    from adapters.aptadb_checkpoint1_review import (
        AptaDBCheckpoint1ReviewError,
        load_default_policy,
        read_csv_rows,
        validate_review_package,
    )
    from adapters.aptadb_s2 import load_aptadb_policy
    from adapters.aptadb_s3 import index_constant_proposals

    output_dir = _assert_aptadb_resolved_output(
        output_dir, checkpoint_dir=checkpoint_dir
    )
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
    metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)
    if preview_dir is None:
        preview_dir = checkpoint_dir / "dry_run"
    if not Path(preview_dir).is_absolute():
        preview_dir = repo_root / preview_dir
    preview_dir = preview_dir.resolve()
    if compare_to_preview is None:
        compare_to_preview = expected_interaction_rows == 1350

    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "aptadb_checkpoint1_manual_review.csv"
    group_path = review_dir / "aptadb_checkpoint1_constant_group_review.csv"
    bulk_path = review_dir / "aptadb_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "aptadb_s3_canonical.csv"
    decision_path = checkpoint_dir / "aptadb_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_aptadb.csv"
    parked_ssdna_path = checkpoint_dir / "aptadb_s3_parked_ssdna.csv"
    parked_non_protein_path = checkpoint_dir / "aptadb_s3_parked_non_protein.csv"
    s2_path = repo_root / "data" / "interim" / "normalised" / "aptadb_normalised.csv"
    qc_path = repo_root / "data" / "interim" / "normalised" / "aptadb_s2_qc.csv"
    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "aptadb_constant_region_proposals.csv"
    )
    sidecar_path = (
        repo_root / "data" / "interim" / "extracted" / "aptadb_source_metadata.csv"
    )
    unlinked_path = (
        repo_root / "data" / "interim" / "extracted" / "aptadb_unlinked_aptamers.csv"
    )
    rec_json = (
        repo_root / "config" / "checkpoint_reviews" / "aptadb_checkpoint1_recommendations.json"
    )
    raw_dir = repo_root / "data" / "raw" / "AptaDB"

    required = [
        queue_path,
        group_path,
        bulk_path,
        canonical_path,
        decision_path,
        rejection_path,
        s2_path,
        qc_path,
        proposals_path,
        sidecar_path,
        unlinked_path,
        rec_json,
    ]
    for path in required:
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing apply input: {path.name}")

    preview_hash_paths = {
        key: preview_dir / preview_name
        for key, preview_name, _applied in PREVIEW_COMPARISON_FILES
    }
    preview_hashes_before = (
        _hash_paths(preview_hash_paths) if compare_to_preview else {}
    )

    hashes_before = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path),
        "bulk": sha256_file(bulk_path),
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "s3_decisions": sha256_file(decision_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path),
        "unlinked": sha256_file(unlinked_path),
        "rec_json": sha256_file(rec_json),
        "raw_interaction": (
            sha256_file(raw_dir / "interaction.csv")
            if (raw_dir / "interaction.csv").is_file()
            else ""
        ),
        "raw_aptamer": (
            sha256_file(raw_dir / "aptamer.csv")
            if (raw_dir / "aptamer.csv").is_file()
            else ""
        ),
        "raw_protein": (
            sha256_file(raw_dir / "protein.csv")
            if (raw_dir / "protein.csv").is_file()
            else ""
        ),
    }
    if expected_interaction_rows == 1350:
        if hashes_before["queue"] != EXPECTED_APTADB_REVIEW_QUEUE_SHA256:
            raise Checkpoint1ApplyError(
                "Record review SHA-256 does not match the frozen reviewed file"
            )
        if hashes_before["groups"] != EXPECTED_APTADB_REVIEW_GROUPS_SHA256:
            raise Checkpoint1ApplyError(
                "Group review SHA-256 does not match the frozen reviewed file"
            )
        if hashes_before["bulk"] != EXPECTED_APTADB_REVIEW_BULK_SHA256:
            raise Checkpoint1ApplyError(
                "Bulk confirmation SHA-256 does not match the frozen reviewed file"
            )
        if hashes_before["rec_json"] != EXPECTED_APTADB_REC_JSON_SHA256:
            raise Checkpoint1ApplyError(
                "Recommendation JSON SHA-256 does not match the tracked file"
            )
        if hashes_before["s2"] != EXPECTED_APTADB_S2_S3_SHA256:
            raise Checkpoint1ApplyError(
                "S2 canonical SHA-256 does not match the frozen AptaDB value"
            )
        if hashes_before["s3"] != EXPECTED_APTADB_S2_S3_SHA256:
            raise Checkpoint1ApplyError(
                "S3 canonical SHA-256 does not match the frozen AptaDB value"
            )
        if hashes_before["sidecar"] != EXPECTED_APTADB_SIDECAR_SHA256:
            raise Checkpoint1ApplyError(
                "AptaDB source-metadata sidecar SHA-256 does not match freeze"
            )
        for name, expected in EXPECTED_APTADB_RAW_SHA256.items():
            key = f"raw_{name.split('.')[0]}"
            if hashes_before[key] != expected:
                raise Checkpoint1ApplyError(
                    f"Raw {name} SHA-256 does not match registry"
                )

    queue_rows = read_csv_rows(queue_path)
    group_rows = read_csv_rows(group_path)
    bulk_rows = read_csv_rows(bulk_path)
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if expected_interaction_rows == 1350 and (
        report.total_review_records != 238
        or report.unresolved_manual_decisions != 0
        or report.unresolved_constant_groups != 0
        or report.unresolved_exceptions != 0
        or report.audit_only_unconfirmed != 0
        or report.blocking_issues
        or report.ready_for_application != 238
        or not report.ok
    ):
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for CHECKPOINT-1 application"
        )
    if expected_interaction_rows != 1350 and not report.ok:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for CHECKPOINT-1 application"
        )

    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path)
    parked_ssdna = (
        read_csv_rows(parked_ssdna_path) if parked_ssdna_path.is_file() else []
    )
    parked_non_protein = (
        read_csv_rows(parked_non_protein_path)
        if parked_non_protein_path.is_file()
        else []
    )
    qc_rows = read_csv_rows(qc_path)
    sidecar_rows = read_csv_rows(sidecar_path)
    proposal_rows = read_csv_rows(proposals_path)
    unlinked_rows = read_csv_rows(unlinked_path)
    qc_by_id = _index_rows(qc_rows)
    sidecar_by_id = _index_rows(sidecar_rows)
    grouping_mode = "target_name_raw_plus_publication"
    policy_path = repo_root / "config" / "source_normalisation" / "aptadb.json"
    if policy_path.is_file():
        grouping_mode = load_aptadb_policy(policy_path).group_inference_key
    proposals_by_record = index_constant_proposals(
        canonical_rows, proposal_rows, grouping_mode=grouping_mode
    )
    policy = load_default_policy(repo_root)

    def _simulate():
        try:
            return simulate_aptadb_checkpoint1_application(
                queue_rows=queue_rows,
                group_rows=group_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=sidecar_by_id,
                s2_qc_by_id=qc_by_id,
                policy=policy,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                unlinked_rows=unlinked_rows,
                existing_rejection_rows=rejection_rows,
                existing_parked_ssdna=parked_ssdna,
                existing_parked_non_protein=parked_non_protein,
                expected_interaction_rows=expected_interaction_rows,
                expected_unlinked_rows=expected_unlinked_rows,
            )
        except AptaDBCheckpoint1ReviewError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    if simulation.guard_rail_failure_rows:
        raise Checkpoint1ApplyError(
            f"Real apply fail-closed: {simulation.stats['guard_rail_failures']} "
            "remaining absolute trim guard-rail failures. CHECKPOINT-1 is not closed."
        )

    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if _serialise_preview_payload(simulation) != _serialise_preview_payload(
            second
        ):
            raise Checkpoint1ApplyError(
                "AptaDB CHECKPOINT-1 application was not byte-identical "
                "across deterministic in-memory rerun"
            )
        deterministic_ok = True

    record_decisions = count_manual_decisions(queue_rows)
    group_decisions = count_group_decisions(group_rows)
    bulk_count = len(report.eligible_bulk_audit_ids)
    if expected_interaction_rows == 1350:
        try:
            check_production_expectations(
                simulation=simulation,
                queue_rows=queue_rows,
                group_rows=group_rows,
                bulk_confirmation_count=bulk_count,
            )
        except AptaDBCheckpoint1ApplyError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    compare_dir = checkpoint_dir / "closure_validation" / "apply_vs_preview"
    compare_dir = _assert_output_dir_allowed(repo_root, compare_dir)
    compare_paths = _write_aptadb_transform_csvs(compare_dir, simulation)
    preview_comparison_ok = False
    if compare_to_preview:
        _compare_applied_to_preview(
            applied_paths=compare_paths, preview_dir=preview_dir
        )
        preview_hashes_after_compare = _hash_paths(preview_hash_paths)
        if preview_hashes_after_compare != preview_hashes_before:
            raise Checkpoint1ApplyError(
                "Dry-run preview files changed during real application"
            )
        preview_comparison_ok = True

    output_dir.mkdir(parents=True, exist_ok=True)
    applied_paths = _write_aptadb_transform_csvs(output_dir, simulation)
    if compare_to_preview:
        _compare_applied_to_preview(
            applied_paths=applied_paths, preview_dir=preview_dir
        )

    tracked_rows = build_tracked_resolutions(
        decisions=simulation.preview_decisions,
        queue_rows=queue_rows,
        route_changed_ids=simulation.route_changed_ids,
    )
    s4_rows = [
        {
            "record_id": row["record_id"],
            "resolved_decision": "accept",
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
        }
        for row in tracked_rows
        if row["authorised_for_s4"] == "true"
    ]
    parked_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"]
        in {"parked_ssdna", "parked_non_protein"}
    ]
    rejected_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] == "technical_reject"
    ]
    write_csv_atomic(
        tracked_manifest, APTADB_TRACKED_RESOLUTION_COLUMNS, tracked_rows
    )
    write_csv_atomic(
        output_dir / "aptadb_checkpoint1_s4_authorised_ids.csv",
        S4_ID_COLUMNS,
        s4_rows,
    )
    write_csv_atomic(
        output_dir / "aptadb_checkpoint1_parked_ids.csv",
        PARKED_ID_COLUMNS,
        parked_id_rows,
    )
    write_csv_atomic(
        output_dir / "aptadb_checkpoint1_rejected_ids.csv",
        REJECTED_ID_COLUMNS,
        rejected_id_rows,
    )

    transform_hashes = {name: sha256_file(path) for name, path in applied_paths.items()}
    closure_paths = {
        "s4_authorised_ids": output_dir / "aptadb_checkpoint1_s4_authorised_ids.csv",
        "parked_ids": output_dir / "aptadb_checkpoint1_parked_ids.csv",
        "rejected_ids": output_dir / "aptadb_checkpoint1_rejected_ids.csv",
        "tracked_manifest": tracked_manifest,
    }
    output_hashes = {
        **transform_hashes,
        **{name: sha256_file(path) for name, path in closure_paths.items()},
    }

    review_hashes = {
        "queue": hashes_before["queue"],
        "groups": hashes_before["groups"],
        "bulk": hashes_before["bulk"],
        "rec_json": hashes_before["rec_json"],
    }
    integrity = {
        "s2": hashes_before["s2"],
        "s3": hashes_before["s3"],
        "sidecar": hashes_before["sidecar"],
        "raw_interaction": hashes_before["raw_interaction"],
        "raw_aptamer": hashes_before["raw_aptamer"],
        "raw_protein": hashes_before["raw_protein"],
        "deterministic_ok": "true" if deterministic_ok else "false",
    }
    summary_text = format_closure_markdown(
        simulation,
        review_hashes=review_hashes,
        integrity=integrity,
        output_hashes=output_hashes,
        record_decisions=record_decisions,
        group_decisions=group_decisions,
        bulk_confirmations=bulk_count,
        preview_comparison_ok=preview_comparison_ok or not compare_to_preview,
        deterministic_ok=deterministic_ok,
    )
    if APTADB_CHECKPOINT_CLOSED_STATEMENT not in summary_text:
        raise Checkpoint1ApplyError("Resolution summary missing checkpoint-closed statement")
    if str(repo_root.resolve()) in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary must not contain absolute repository paths"
        )
    summary_path = output_dir / "aptadb_checkpoint1_resolution_summary.md"
    _write_text_atomic(summary_path, summary_text)
    _write_text_atomic(
        output_dir / "README.md",
        "CHECKPOINT-1 CLOSED.\n"
        "These files are the authoritative AptaDB post-review artefacts.\n"
        "They must not overwrite S2, pre-review S3, or dry-run previews.\n"
        "S4 has not started.\n",
    )
    output_hashes["summary"] = sha256_file(summary_path)

    metadata = {
        "source_key": "aptadb",
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "checkpoint_status": "closed",
        "checkpoint_closed": True,
        "s4_started": False,
        "next_stage": "global_S4_handoff",
        "reviewed_records": int(simulation.stats["reviewed_records"]),
        "record_decisions": record_decisions,
        "group_decisions": group_decisions,
        "bulk_audit_confirmations": bulk_count,
        "human_reviewed_drops": int(simulation.stats["human_reviewed_drops"]),
        "technical_rejects_after_review": int(
            simulation.stats["technical_rejects_after_review"]
        ),
        "technical_rejects_excluding_human_drop": int(
            simulation.stats["technical_rejects_excluding_human_drop"]
        ),
        "parked_ssdna": int(simulation.stats["parked_ssdna"]),
        "parked_non_protein": int(simulation.stats["parked_non_protein"]),
        "technically_eligible": int(simulation.stats["technically_eligible"]),
        "authorised_for_s4": int(simulation.stats["technically_eligible"]),
        "unlinked_aptamers": int(simulation.stats["unlinked_aptamers"]),
        "unlinked_missing_target": int(simulation.stats["unlinked_missing_target"]),
        "route_changed": int(simulation.stats["route_changed"]),
        "route_changed_ids": list(simulation.route_changed_ids),
        "sequence_corrections": int(simulation.stats["sequence_corrections"]),
        "molecule_overrides": int(simulation.stats["molecule_overrides"]),
        "records_trimmed": int(simulation.stats["records_trimmed"]),
        "trimmed_by_group": int(simulation.stats["trimmed_by_group"]),
        "trimmed_by_record_override": int(
            simulation.stats["trimmed_by_record_override"]
        ),
        "core_length_changed": int(simulation.stats["core_length_changed"]),
        "large_trim_human_approved": int(
            simulation.stats["large_trim_human_approved"]
        ),
        "guard_rail_failures": int(simulation.stats["guard_rail_failures"]),
        "review_file_sha256": hashes_before["queue"],
        "review_groups_sha256": hashes_before["groups"],
        "review_bulk_sha256": hashes_before["bulk"],
        "recommendations_sha256": hashes_before["rec_json"],
        "s2_sha256": hashes_before["s2"],
        "s3_sha256": hashes_before["s3"],
        "sidecar_sha256": hashes_before["sidecar"],
        "raw_interaction_sha256": hashes_before["raw_interaction"],
        "raw_aptamer_sha256": hashes_before["raw_aptamer"],
        "raw_protein_sha256": hashes_before["raw_protein"],
        "output_hashes": output_hashes,
        "preview_comparison_ok": preview_comparison_ok or not compare_to_preview,
        "deterministic_rerun_ok": deterministic_ok,
        "closure_only_fields": list(CLOSURE_ONLY_FIELDS),
        "application_mode": "apply",
    }
    _write_json_atomic(metadata_out, metadata)
    output_hashes["metadata"] = sha256_file(metadata_out)

    if check_deterministic_rerun:
        determinism_dir = checkpoint_dir / "closure_validation" / "determinism"
        determinism_dir = _assert_output_dir_allowed(repo_root, determinism_dir)
        third = _simulate()
        if _serialise_preview_payload(simulation) != _serialise_preview_payload(
            third
        ):
            raise Checkpoint1ApplyError(
                "Deterministic verification rerun diverged from the "
                "authoritative in-memory payload"
            )
        verify_paths = _write_aptadb_transform_csvs(determinism_dir, third)
        for name, path in applied_paths.items():
            if sha256_file(path) != sha256_file(verify_paths[name]):
                raise Checkpoint1ApplyError(
                    f"Deterministic verification mismatch for {name}"
                )

    hashes_after = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path),
        "bulk": sha256_file(bulk_path),
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "s3_decisions": sha256_file(decision_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path),
        "unlinked": sha256_file(unlinked_path),
        "rec_json": sha256_file(rec_json),
        "raw_interaction": (
            sha256_file(raw_dir / "interaction.csv")
            if (raw_dir / "interaction.csv").is_file()
            else ""
        ),
        "raw_aptamer": (
            sha256_file(raw_dir / "aptamer.csv")
            if (raw_dir / "aptamer.csv").is_file()
            else ""
        ),
        "raw_protein": (
            sha256_file(raw_dir / "protein.csv")
            if (raw_dir / "protein.csv").is_file()
            else ""
        ),
    }
    if hashes_after != hashes_before:
        raise Checkpoint1ApplyError(
            "CHECKPOINT-1 apply mutated an immutable input artefact"
        )
    if compare_to_preview:
        preview_hashes_final = _hash_paths(preview_hash_paths)
        if preview_hashes_final != preview_hashes_before:
            raise Checkpoint1ApplyError(
                "Dry-run preview files changed after real application"
            )

    stats = dict(simulation.stats)
    stats["checkpoint_closed"] = True
    stats["authorised_for_s4"] = int(simulation.stats["technically_eligible"])
    stats["preview_comparison_ok"] = preview_comparison_ok or not compare_to_preview
    stats["deterministic_rerun_ok"] = deterministic_ok
    print(
        "source=aptadb\n"
        "mode=apply\n"
        "checkpoint_status=closed\n"
        "checkpoint_closed=true\n"
        f"total_interactions={stats['total_interactions']}\n"
        f"human_reviewed_drops={stats['human_reviewed_drops']}\n"
        f"technical_rejects_after_review={stats['technical_rejects_after_review']}\n"
        f"parked_ssdna={stats['parked_ssdna']}\n"
        f"parked_non_protein={stats['parked_non_protein']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"route_changed={stats['route_changed']}\n"
        f"guard_rail_failures={stats['guard_rail_failures']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        f"review_queue_sha256={hashes_before['queue']}\n"
        f"review_groups_sha256={hashes_before['groups']}\n"
        f"review_bulk_sha256={hashes_before['bulk']}\n"
        f"s2_sha256={hashes_before['s2']}\n"
        f"s3_sha256={hashes_before['s3']}\n"
        f"preview_comparison={'pass' if stats['preview_comparison_ok'] else 'fail'}\n"
        f"deterministic_rerun={'pass' if deterministic_ok else 'skipped'}\n"
        "CHECKPOINT-1 is closed\n"
        "S4 was not started"
    )
    return AptaDBApplyResult(
        output_dir=output_dir,
        metadata_out=metadata_out,
        tracked_manifest=tracked_manifest,
        summary_out=summary_path,
        output_hashes=output_hashes,
        stats=stats,
        preview_comparison_ok=bool(stats["preview_comparison_ok"]),
        deterministic_rerun_ok=deterministic_ok,
        checkpoint_closed=True,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply completed CHECKPOINT-1 human review and close the "
            "checkpoint with tracked sequence-free resolution artefacts."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key (aptabase, utexas, aptadb, riboaptamer, aptaindex, or ena)",
    )
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Simulate CHECKPOINT-1 application without writing resolved, "
            "closed, or S4-authorised artefacts"
        ),
    )
    parser.add_argument(
        "--skip-deterministic-rerun",
        action="store_true",
        help="Skip in-memory dry-run determinism check (tests only)",
    )
    return parser


def run_riboaptamer_checkpoint1_apply(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path | None = None,
    tracked_manifest: Path | None = None,
    metadata_out: Path | None = None,
    dry_run: bool = False,
    check_deterministic_rerun: bool = True,
    expected_source_rows: int | None = 509,
) -> None:
    """Apply or dry-run RiboAptamer CHECKPOINT-1. Fail-closed if unresolved."""
    from adapters.riboaptamer_checkpoint1_apply import (
        RIBOAPTAMER_CHECKPOINT_CLOSED_STATEMENT,
        RIBOAPTAMER_TRACKED_RESOLUTION_COLUMNS,
        build_tracked_resolutions,
        count_manual_decisions,
        count_trim_actions,
        format_closure_markdown,
    )
    from adapters.riboaptamer_checkpoint1_dry_run import (
        CHANGE_REPORT_COLUMNS,
        DECISION_AUDIT_COLUMNS,
        DRY_RUN_BANNER,
        ELIGIBLE_COLUMNS,
        serialise_riboaptamer_simulation,
        simulate_riboaptamer_checkpoint1_application,
    )
    from adapters.riboaptamer_checkpoint1_review import (
        RiboAptamerCheckpoint1ReviewError,
        load_default_policy,
        normalise_riboaptamer_review_rows,
        preserve_human_review_source,
        read_csv_rows,
        read_riboaptamer_review_csv,
        validate_review_package,
        write_canonical_utf8_review_csv,
    )
    from adapters.riboaptamer_s3 import (
        DECISION_COLUMNS,
        PARK_COLUMNS,
        REJECTION_COLUMNS,
        index_constant_proposals,
    )
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    if not Path(checkpoint_dir).is_absolute():
        checkpoint_dir = repo_root / checkpoint_dir
    checkpoint_dir = Path(checkpoint_dir).resolve()
    if output_dir is None:
        output_dir = Path(checkpoint_dir) / ("dry_run" if dry_run else "resolved")
    if not Path(output_dir).is_absolute():
        output_dir = repo_root / output_dir
    output_dir = _assert_output_dir_allowed(repo_root, Path(output_dir))
    if tracked_manifest is None:
        tracked_manifest = Path(
            "config/checkpoint_reviews/riboaptamer_checkpoint1_resolutions.csv"
        )
    if metadata_out is None:
        metadata_out = Path(
            "config/checkpoint_reviews/riboaptamer_checkpoint1_metadata.json"
        )
    if not dry_run:
        tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
        metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)

    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "riboaptamer_checkpoint1_manual_review.csv"
    group_path = review_dir / "riboaptamer_checkpoint1_constant_group_review.csv"
    bulk_path = review_dir / "riboaptamer_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "riboaptamer_s3_canonical.csv"
    decision_path = checkpoint_dir / "riboaptamer_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_riboaptamer.csv"
    parked_ssdna_path = checkpoint_dir / "riboaptamer_s3_parked_ssdna.csv"
    if not queue_path.is_file():
        raise Checkpoint1ApplyError(
            "Missing RiboAptamer CHECKPOINT-1 review CSV; prepare first"
        )
    human_source_path = preserve_human_review_source(queue_path)
    queue_rows = normalise_riboaptamer_review_rows(
        read_riboaptamer_review_csv(queue_path)
    )
    write_canonical_utf8_review_csv(queue_path, queue_rows)
    group_rows = read_csv_rows(group_path) if group_path.is_file() else []
    bulk_rows = read_csv_rows(bulk_path) if bulk_path.is_file() else []
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk,
        )
    except Exception as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if not report.ok:
        raise Checkpoint1ApplyError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    if report.unresolved_manual_decisions or report.unresolved_exceptions:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for CHECKPOINT-1 application"
        )

    policy = load_default_policy(repo_root)
    if not canonical_path.is_file() or not decision_path.is_file():
        raise Checkpoint1ApplyError("Missing RiboAptamer S3 canonical/decision files")
    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path) if rejection_path.is_file() else []
    parked_ssdna = (
        read_csv_rows(parked_ssdna_path) if parked_ssdna_path.is_file() else []
    )
    qc_path = repo_root / "data" / "interim" / "normalised" / "riboaptamer_s2_qc.csv"
    sidecar_path = (
        repo_root / "data" / "interim" / "extracted" / "riboaptamer_source_metadata.csv"
    )
    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "detected_constants_riboaptamer.csv"
    )
    rec_json = (
        repo_root
        / "config"
        / "checkpoint_reviews"
        / "riboaptamer_checkpoint1_recommendations.json"
    )
    s2_path = repo_root / "data" / "interim" / "normalised" / "riboaptamer_normalised.csv"
    raw_path = repo_root / "data" / "raw" / "riboaptamer" / "all_sequences_509_rows.csv"
    qc_rows = read_csv_rows(qc_path) if qc_path.is_file() else []
    sidecar_rows = read_csv_rows(sidecar_path) if sidecar_path.is_file() else []
    proposal_rows = read_csv_rows(proposals_path) if proposals_path.is_file() else []
    s2_qc_by_id = {row["record_id"]: row for row in qc_rows}
    source_metadata_by_id = {row["record_id"]: row for row in sidecar_rows}
    proposals_by_record = index_constant_proposals(canonical_rows, proposal_rows)

    hashes_before = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path) if group_path.is_file() else "",
        "bulk": sha256_file(bulk_path) if bulk_path.is_file() else "",
        "s2": sha256_file(s2_path) if s2_path.is_file() else "",
        "s3": sha256_file(canonical_path),
        "sidecar": sha256_file(sidecar_path) if sidecar_path.is_file() else "",
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw": sha256_file(raw_path) if raw_path.is_file() else "",
        "human_source": sha256_file(human_source_path),
    }

    def _simulate():
        try:
            return simulate_riboaptamer_checkpoint1_application(
                queue_rows=queue_rows,
                group_rows=group_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=source_metadata_by_id,
                s2_qc_by_id=s2_qc_by_id,
                policy=policy,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                existing_rejection_rows=rejection_rows,
                existing_parked_ssdna=parked_ssdna,
                expected_source_rows=expected_source_rows,
            )
        except RiboAptamerCheckpoint1ReviewError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if serialise_riboaptamer_simulation(
            simulation
        ) != serialise_riboaptamer_simulation(second):
            raise Checkpoint1ApplyError(
                "RiboAptamer CHECKPOINT-1 application was not byte-identical "
                "across deterministic in-memory rerun"
            )
        deterministic_ok = True

    if dry_run:
        print(DRY_RUN_BANNER)
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    write_corpus_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_applied_canonical.csv",
        simulation.preview_canonical,
        columns=CORPUS_COLUMNS,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_applied_routing.csv",
        DECISION_COLUMNS,
        simulation.preview_decisions,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_applied_rejection.csv",
        REJECTION_COLUMNS,
        simulation.preview_rejections,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_applied_parked_ssdna.csv",
        PARK_COLUMNS,
        simulation.preview_parked_ssdna,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_applied_eligible.csv",
        ELIGIBLE_COLUMNS,
        simulation.preview_eligible,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_applied_change_report.csv",
        CHANGE_REPORT_COLUMNS,
        simulation.change_report,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_decision_audit.csv",
        DECISION_AUDIT_COLUMNS,
        simulation.decision_audit,
    )

    record_decisions = count_manual_decisions(queue_rows)
    trim_actions = count_trim_actions(queue_rows)
    tracked_rows = build_tracked_resolutions(
        decisions=simulation.preview_decisions,
        queue_rows=queue_rows,
        route_changed_ids=simulation.route_changed_ids,
    )
    s4_rows = [
        {
            "record_id": row["record_id"],
            "resolved_decision": "accept",
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
        }
        for row in tracked_rows
        if row["authorised_for_s4"] == "true"
    ]
    rejected_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] == "technical_reject"
    ]
    parked_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] == "parked_ssdna"
    ]
    write_csv_atomic(
        tracked_manifest, RIBOAPTAMER_TRACKED_RESOLUTION_COLUMNS, tracked_rows
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_s4_authorised_ids.csv",
        S4_ID_COLUMNS,
        s4_rows,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_rejected_ids.csv",
        REJECTED_ID_COLUMNS,
        rejected_id_rows,
    )
    write_csv_atomic(
        output_dir / "riboaptamer_checkpoint1_parked_ids.csv",
        PARKED_ID_COLUMNS,
        parked_id_rows,
    )

    applied_names = [
        "riboaptamer_checkpoint1_applied_canonical.csv",
        "riboaptamer_checkpoint1_applied_routing.csv",
        "riboaptamer_checkpoint1_applied_rejection.csv",
        "riboaptamer_checkpoint1_applied_parked_ssdna.csv",
        "riboaptamer_checkpoint1_applied_eligible.csv",
        "riboaptamer_checkpoint1_applied_change_report.csv",
        "riboaptamer_checkpoint1_decision_audit.csv",
        "riboaptamer_checkpoint1_s4_authorised_ids.csv",
        "riboaptamer_checkpoint1_rejected_ids.csv",
        "riboaptamer_checkpoint1_parked_ids.csv",
    ]
    output_hashes = {
        Path(name).stem.replace("riboaptamer_checkpoint1_", ""): sha256_file(
            output_dir / name
        )
        for name in applied_names
    }
    output_hashes["tracked_manifest"] = sha256_file(tracked_manifest)

    if check_deterministic_rerun:
        determinism_dir = checkpoint_dir / "closure_validation" / "determinism"
        determinism_dir = _assert_output_dir_allowed(repo_root, determinism_dir)
        determinism_dir.mkdir(parents=True, exist_ok=True)
        third = _simulate()
        if serialise_riboaptamer_simulation(
            simulation
        ) != serialise_riboaptamer_simulation(third):
            raise Checkpoint1ApplyError(
                "Deterministic verification rerun diverged from the "
                "authoritative in-memory payload"
            )
        write_corpus_csv_atomic(
            determinism_dir / "riboaptamer_checkpoint1_applied_canonical.csv",
            third.preview_canonical,
            columns=CORPUS_COLUMNS,
        )
        if sha256_file(
            output_dir / "riboaptamer_checkpoint1_applied_canonical.csv"
        ) != sha256_file(
            determinism_dir / "riboaptamer_checkpoint1_applied_canonical.csv"
        ):
            raise Checkpoint1ApplyError(
                "Deterministic verification mismatch for applied canonical"
            )

    summary_text = format_closure_markdown(
        simulation,
        review_hashes=hashes_before,
        integrity={
            "s2": hashes_before["s2"],
            "s3": hashes_before["s3"],
            "sidecar": hashes_before["sidecar"],
            "raw": hashes_before["raw"],
        },
        output_hashes=output_hashes,
        record_decisions=record_decisions,
        trim_actions=trim_actions,
        deterministic_ok=deterministic_ok,
        human_source_preserved=human_source_path.is_file(),
    )
    if RIBOAPTAMER_CHECKPOINT_CLOSED_STATEMENT not in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary missing checkpoint-closed statement"
        )
    if str(repo_root.resolve()) in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary must not contain absolute repository paths"
        )
    summary_path = output_dir / "riboaptamer_checkpoint1_resolution_summary.md"
    _write_text_atomic(summary_path, summary_text)
    _write_text_atomic(
        output_dir / "README.md",
        "CHECKPOINT-1 CLOSED.\n"
        "These files are the authoritative RiboAptamer post-review artefacts.\n"
        "They must not overwrite S2 or pre-review S3 snapshots.\n"
        "S4 has not started.\n",
    )
    output_hashes["summary"] = sha256_file(summary_path)

    metadata = {
        "source_key": "riboaptamer",
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "checkpoint_status": "closed",
        "checkpoint_closed": True,
        "s4_started": False,
        "next_stage": "global_S4_handoff",
        "reviewed_records": int(simulation.stats["reviewed_records"]),
        "record_decisions": record_decisions,
        "trim_actions": trim_actions,
        "human_reviewed_drops": int(simulation.stats["human_reviewed_drops"]),
        "technical_rejects_after_review": int(
            simulation.stats["technical_rejects_after_review"]
        ),
        "parked_ssdna": int(simulation.stats["parked_ssdna"]),
        "parked_non_protein": 0,
        "technically_eligible": int(simulation.stats["technically_eligible"]),
        "authorised_for_s4": int(simulation.stats["authorised_for_s4"]),
        "records_trimmed": int(simulation.stats["records_trimmed"]),
        "approved_known_t7_trims": int(simulation.stats["approved_known_t7_trims"]),
        "group_consensus_proposals": 0,
        "strong_unresolved_constant_flags": int(
            simulation.stats["strong_unresolved_constant_flags"]
        ),
        "weak_possible_constant_flags": int(
            simulation.stats["weak_possible_constant_flags"]
        ),
        "unconsumed_decisions": 0,
        "review_file_sha256": hashes_before["queue"],
        "human_source_sha256": hashes_before["human_source"],
        "s2_sha256": hashes_before["s2"],
        "s3_sha256": hashes_before["s3"],
        "sidecar_sha256": hashes_before["sidecar"],
        "raw_sha256": hashes_before["raw"],
        "output_hashes": output_hashes,
        "deterministic_rerun_ok": deterministic_ok,
        "application_mode": "apply",
    }
    _write_json_atomic(metadata_out, metadata)

    hashes_after = {
        "s2": sha256_file(s2_path) if s2_path.is_file() else "",
        "s3": sha256_file(canonical_path),
        "sidecar": sha256_file(sidecar_path) if sidecar_path.is_file() else "",
        "raw": sha256_file(raw_path) if raw_path.is_file() else "",
        "human_source": sha256_file(human_source_path),
    }
    for key in ("s2", "s3", "sidecar", "raw", "human_source"):
        if hashes_after[key] != hashes_before[key]:
            raise Checkpoint1ApplyError(
                f"CHECKPOINT-1 apply mutated immutable input artefact {key}"
            )

    stats = dict(simulation.stats)
    stats["checkpoint_closed"] = True
    print(
        "source=riboaptamer\n"
        f"reviewed_records={stats['reviewed_records']}\n"
        f"decisions_consumed={stats['decisions_consumed']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"technical_rejects_after_review={stats['technical_rejects_after_review']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        "CHECKPOINT-1 CLOSED\n"
        "S4 has not started"
    )


EXPECTED_APTAINDEX_REVIEW_SHA256 = (
    "843946d525a1bb269e9d5c399db30faa6a5b626beef8470eb6469e1529fc02fd"
)
EXPECTED_APTAINDEX_BULK_SHA256 = (
    "df65efea68aa787c51a19e90af29f07d19a63f6d8c6e16c6e85c154302a87457"
)
EXPECTED_APTAINDEX_RAW_SHA256 = (
    "912b8e554fa2bb2ed3a9e9bdf1cfbe4f757d8c7a00c401629e5bcb5e5c2877a8"
)
EXPECTED_APTAINDEX_S1_SHA256 = (
    "b74f6cc852ab342a6a28eafdbe97ee51cf325d5419c67ac6456d560753530552"
)
EXPECTED_APTAINDEX_S2_S3_SHA256 = (
    "4a41c90c102d5dc5b9d9e469c6b636014d27c428868d1b3230b8fb2b1c4412da"
)


def run_aptaindex_checkpoint1_dry_run(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    check_deterministic_rerun: bool = True,
    expected_source_rows: int | None = 1050,
    verify_production_hashes: bool = True,
) -> None:
    """Simulate AptaIndex CHECKPOINT-1 application without closing it."""
    from adapters.aptaindex_checkpoint1_dry_run import (
        CHANGE_REPORT_COLUMNS,
        DECISION_AUDIT_COLUMNS,
        DRY_RUN_BANNER,
        ELIGIBLE_COLUMNS,
        format_dry_run_markdown,
        serialise_aptaindex_simulation_sequence_free,
        simulate_aptaindex_checkpoint1_application,
    )
    from adapters.aptaindex_checkpoint1_review import (
        AptaIndexCheckpoint1ReviewError,
        load_default_policy,
        validate_review_package,
    )
    from adapters.aptadb_checkpoint1_review import (
        AptaDBCheckpoint1ReviewError,
        read_csv_rows,
    )
    from adapters.aptaindex_s3 import (
        DECISION_COLUMNS,
        PARK_COLUMNS,
        REJECTION_COLUMNS,
        index_constant_proposals,
    )
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    output_dir = _assert_aptadb_dry_run_output(output_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "aptaindex_checkpoint1_manual_review.csv"
    group_path = review_dir / "aptaindex_checkpoint1_constant_group_review.csv"
    bulk_path = review_dir / "aptaindex_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "aptaindex_s3_canonical.csv"
    decision_path = checkpoint_dir / "aptaindex_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_aptaindex.csv"
    parked_ssdna_path = checkpoint_dir / "aptaindex_s3_parked_ssdna.csv"
    parked_chemistry_path = checkpoint_dir / "aptaindex_s3_parks.csv"
    s1_path = repo_root / "data" / "interim" / "extracted" / "aptaindex_extracted.csv"
    s2_path = repo_root / "data" / "interim" / "normalised" / "aptaindex_normalised.csv"
    qc_path = repo_root / "data" / "interim" / "normalised" / "aptaindex_s2_qc.csv"
    sidecar_path = (
        repo_root / "data" / "interim" / "extracted" / "aptaindex_source_metadata.csv"
    )
    proposals_path = (
        repo_root
        / "data"
        / "interim"
        / "normalised"
        / "detected_constants_aptaindex.csv"
    )
    rec_json = (
        repo_root
        / "config"
        / "checkpoint_reviews"
        / "aptaindex_checkpoint1_recommendations.json"
    )
    raw_path = (
        repo_root / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
    )

    required = [
        queue_path,
        bulk_path,
        canonical_path,
        decision_path,
        rejection_path,
        s2_path,
        qc_path,
        sidecar_path,
    ]
    for path in required:
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing dry-run input: {path.name}")

    hashes_before = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path) if group_path.is_file() else "",
        "bulk": sha256_file(bulk_path),
        "s1": sha256_file(s1_path) if s1_path.is_file() else "",
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path) if proposals_path.is_file() else "",
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw": sha256_file(raw_path) if raw_path.is_file() else "",
    }
    if verify_production_hashes:
        if hashes_before["queue"] != EXPECTED_APTAINDEX_REVIEW_SHA256:
            raise Checkpoint1ApplyError(
                "AptaIndex review SHA-256 does not match the locked human review"
            )
        if hashes_before["bulk"] != EXPECTED_APTAINDEX_BULK_SHA256:
            raise Checkpoint1ApplyError(
                "AptaIndex bulk-confirmation SHA-256 does not match the locked file"
            )
        if hashes_before["raw"] and hashes_before["raw"] != EXPECTED_APTAINDEX_RAW_SHA256:
            raise Checkpoint1ApplyError("AptaIndex raw SHA-256 drifted")
        if hashes_before["s1"] and hashes_before["s1"] != EXPECTED_APTAINDEX_S1_SHA256:
            raise Checkpoint1ApplyError("AptaIndex S1 SHA-256 drifted")
        if hashes_before["s2"] != EXPECTED_APTAINDEX_S2_S3_SHA256:
            raise Checkpoint1ApplyError("AptaIndex S2 SHA-256 drifted")
        if hashes_before["s3"] != EXPECTED_APTAINDEX_S2_S3_SHA256:
            raise Checkpoint1ApplyError("AptaIndex S3 canonical SHA-256 drifted")

    queue_rows = read_csv_rows(queue_path)
    group_rows = read_csv_rows(group_path) if group_path.is_file() else []
    bulk_rows = read_csv_rows(bulk_path)
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk,
        )
    except Exception as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if not report.ok:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for dry-run application"
        )
    if report.unresolved_manual_decisions or report.audit_only_unconfirmed:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for dry-run application"
        )

    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path) if rejection_path.is_file() else []
    parked_ssdna = (
        read_csv_rows(parked_ssdna_path) if parked_ssdna_path.is_file() else []
    )
    parked_chemistry = (
        read_csv_rows(parked_chemistry_path) if parked_chemistry_path.is_file() else []
    )
    qc_rows = read_csv_rows(qc_path)
    sidecar_rows = read_csv_rows(sidecar_path)
    proposal_rows = read_csv_rows(proposals_path) if proposals_path.is_file() else []
    s2_qc_by_id = {row["record_id"]: row for row in qc_rows}
    source_metadata_by_id = {row["record_id"]: row for row in sidecar_rows}
    proposals_by_record = index_constant_proposals(canonical_rows, proposal_rows)
    policy = load_default_policy(repo_root)

    def _simulate():
        try:
            return simulate_aptaindex_checkpoint1_application(
                queue_rows=queue_rows,
                group_rows=group_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=source_metadata_by_id,
                s2_qc_by_id=s2_qc_by_id,
                policy=policy,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                existing_rejection_rows=rejection_rows,
                existing_parked_ssdna=parked_ssdna,
                existing_parked_chemistry=parked_chemistry,
                expected_source_rows=expected_source_rows,
            )
        except (AptaIndexCheckpoint1ReviewError, AptaDBCheckpoint1ReviewError) as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if serialise_aptaindex_simulation_sequence_free(
            simulation
        ) != serialise_aptaindex_simulation_sequence_free(second):
            raise Checkpoint1ApplyError(
                "AptaIndex CHECKPOINT-1 dry-run preview was not byte-identical "
                "across deterministic in-memory rerun"
            )
        deterministic_ok = True

    output_dir.mkdir(parents=True, exist_ok=True)
    # AptaIndex sequence_raw can contain bare CR; match S1/S2/S3 QUOTE_ALL.
    write_corpus_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_canonical_preview.csv",
        simulation.preview_canonical,
        columns=CORPUS_COLUMNS,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_routing_preview.csv",
        DECISION_COLUMNS,
        simulation.preview_decisions,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_rejection_preview.csv",
        REJECTION_COLUMNS,
        simulation.preview_rejections,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_parked_ssdna_preview.csv",
        PARK_COLUMNS,
        simulation.preview_parked_ssdna,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_parked_chemistry_preview.csv",
        PARK_COLUMNS,
        simulation.preview_parked_chemistry,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_eligible_preview.csv",
        ELIGIBLE_COLUMNS,
        simulation.preview_eligible,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_change_report.csv",
        CHANGE_REPORT_COLUMNS,
        simulation.change_report,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_decision_audit.csv",
        DECISION_AUDIT_COLUMNS,
        simulation.decision_audit,
        quoting=csv.QUOTE_ALL,
    )
    review_hashes = {
        "queue": hashes_before["queue"],
        "groups": hashes_before["groups"],
        "bulk": hashes_before["bulk"],
    }
    integrity = {
        "s1": hashes_before["s1"],
        "s2": hashes_before["s2"],
        "s3": hashes_before["s3"],
        "raw": hashes_before["raw"],
        "deterministic_ok": "true" if deterministic_ok else "false",
    }
    report_text = format_dry_run_markdown(
        simulation, review_hashes=review_hashes, integrity=integrity
    )
    _write_text_atomic(
        output_dir / "aptaindex_checkpoint1_dry_run_report.md", report_text
    )
    _write_text_atomic(
        output_dir / "README.md",
        DRY_RUN_BANNER
        + (
            "\n\nThese files are application previews only. They must not be "
            "treated as resolved CHECKPOINT-1 outputs or an S4 handoff.\n"
            "Canonical preview rows contain restricted sequences and must "
            "remain under ignored data/.\n"
        ),
    )

    hashes_after = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path) if group_path.is_file() else "",
        "bulk": sha256_file(bulk_path),
        "s1": sha256_file(s1_path) if s1_path.is_file() else "",
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path) if proposals_path.is_file() else "",
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw": sha256_file(raw_path) if raw_path.is_file() else "",
    }
    if hashes_after != hashes_before:
        raise Checkpoint1ApplyError(
            "Dry-run mutated an input artefact; aborting without treating "
            "preview files as authoritative"
        )

    stats = simulation.stats
    print(DRY_RUN_BANNER)
    print(
        "source=aptaindex\n"
        "mode=dry_run\n"
        "checkpoint_status=unapplied\n"
        f"total_records={stats['total_records']}\n"
        f"reviewed_records={stats['reviewed_records']}\n"
        f"human_keep={stats['human_keep']}\n"
        f"human_edit={stats['human_edit']}\n"
        f"human_drop={stats['human_drop']}\n"
        f"human_reviewed_drops={stats['human_reviewed_drops']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"parked_ssdna={stats['parked_ssdna']}\n"
        f"parked_chemistry_review={stats['parked_chemistry_review']}\n"
        f"technical_rejects_after_review={stats['technical_rejects_after_review']}\n"
        f"manual_rejects={stats['manual_rejects']}\n"
        f"technical_rejects_after_edit={stats['technical_rejects_after_edit']}\n"
        f"route_changed={stats['route_changed']}\n"
        f"keep_unexpected_route_changes={stats['keep_unexpected_route_changes']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        f"review_queue_sha256={hashes_before['queue']}\n"
        f"review_bulk_sha256={hashes_before['bulk']}\n"
        f"s1_sha256={hashes_before['s1']}\n"
        f"s2_sha256={hashes_before['s2']}\n"
        f"s3_sha256={hashes_before['s3']}\n"
        f"raw_sha256={hashes_before['raw']}\n"
        f"nogo_reasons={';'.join(simulation.nogo_reasons) or 'none'}\n"
        f"deterministic_rerun={'pass' if deterministic_ok else 'skipped'}\n"
        "CHECKPOINT-1 is not closed\n"
        "S4 remains blocked"
    )


@dataclass(frozen=True)
class AptaIndexApplyResult:
    """Authoritative AptaIndex CHECKPOINT-1 apply/closure result."""

    output_dir: Path
    metadata_out: Path
    tracked_manifest: Path
    summary_out: Path
    output_hashes: dict[str, str]
    stats: dict[str, int | str | bool]
    preview_comparison_ok: bool
    deterministic_rerun_ok: bool
    semantic_mismatches: int
    checkpoint_closed: bool


def _assert_aptaindex_resolved_output(path: Path, *, checkpoint_dir: Path) -> Path:
    resolved = path.resolve()
    checkpoint_resolved = checkpoint_dir.resolve()
    if resolved == checkpoint_resolved:
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the AptaIndex CHECKPOINT-1 snapshot directory"
        )
    dry_run_dir = (checkpoint_resolved / "dry_run").resolve()
    if resolved == dry_run_dir:
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the validated dry-run preview directory"
        )
    lowered = [part.lower() for part in resolved.parts]
    if any(name in APPLY_FORBIDDEN_DIR_NAMES for name in lowered):
        raise Checkpoint1ApplyError(
            f"Resolved output must not use a dry-run/S2/S3/S4 directory: {resolved}"
        )
    return resolved


def _write_aptaindex_transform_csvs(
    output_dir: Path, simulation: object
) -> dict[str, Path]:
    from adapters.aptaindex_checkpoint1_dry_run import (
        CHANGE_REPORT_COLUMNS,
        DECISION_AUDIT_COLUMNS,
        ELIGIBLE_COLUMNS,
        AptaIndexDryRunSimulation,
    )
    from adapters.aptaindex_s3 import DECISION_COLUMNS, PARK_COLUMNS, REJECTION_COLUMNS
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    if not isinstance(simulation, AptaIndexDryRunSimulation):
        raise Checkpoint1ApplyError("Apply payload has unexpected type")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "canonical": output_dir / "aptaindex_checkpoint1_applied_canonical.csv",
        "routing": output_dir / "aptaindex_checkpoint1_applied_routing.csv",
        "rejection": output_dir / "aptaindex_checkpoint1_applied_rejection.csv",
        "parked_ssdna": output_dir / "aptaindex_checkpoint1_applied_parked_ssdna.csv",
        "parked_chemistry": (
            output_dir / "aptaindex_checkpoint1_applied_parked_chemistry.csv"
        ),
        "eligible": output_dir / "aptaindex_checkpoint1_applied_eligible.csv",
        "change_report": output_dir / "aptaindex_checkpoint1_applied_change_report.csv",
        "decision_audit": output_dir / "aptaindex_checkpoint1_decision_audit.csv",
    }
    write_corpus_csv_atomic(
        paths["canonical"],
        simulation.preview_canonical,
        columns=CORPUS_COLUMNS,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["routing"],
        DECISION_COLUMNS,
        simulation.preview_decisions,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["rejection"],
        REJECTION_COLUMNS,
        simulation.preview_rejections,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["parked_ssdna"],
        PARK_COLUMNS,
        simulation.preview_parked_ssdna,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["parked_chemistry"],
        PARK_COLUMNS,
        simulation.preview_parked_chemistry,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["eligible"],
        ELIGIBLE_COLUMNS,
        simulation.preview_eligible,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["change_report"],
        CHANGE_REPORT_COLUMNS,
        simulation.change_report,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        paths["decision_audit"],
        DECISION_AUDIT_COLUMNS,
        simulation.decision_audit,
        quoting=csv.QUOTE_ALL,
    )
    return paths


def _compare_aptaindex_applied_to_preview(
    *,
    applied_paths: Mapping[str, Path],
    preview_dir: Path,
) -> list[str]:
    from adapters.aptaindex_checkpoint1_apply import PREVIEW_COMPARISON_FILES

    missing = [
        preview_name
        for _key, preview_name, _applied in PREVIEW_COMPARISON_FILES
        if not (preview_dir / preview_name).is_file()
    ]
    if missing:
        raise Checkpoint1ApplyError(
            "Validated dry-run preview is incomplete; refusing real apply: "
            + ", ".join(missing)
        )
    mismatches: list[str] = []
    for key, preview_name, _applied_name in PREVIEW_COMPARISON_FILES:
        preview_path = preview_dir / preview_name
        applied_path = applied_paths[key]
        if preview_path.read_bytes() != applied_path.read_bytes():
            mismatches.append(key)
    return mismatches


def run_aptaindex_checkpoint1_apply(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    tracked_manifest: Path,
    metadata_out: Path,
    preview_dir: Path | None = None,
    check_deterministic_rerun: bool = True,
    expected_source_rows: int | None = 1050,
    verify_production_hashes: bool | None = None,
    compare_to_preview: bool | None = None,
) -> AptaIndexApplyResult:
    """Apply completed AptaIndex CHECKPOINT-1 review and close the checkpoint."""
    from adapters.aptaindex_checkpoint1_apply import (
        APTAINDEX_CHECKPOINT_CLOSED_STATEMENT,
        APTAINDEX_TRACKED_RESOLUTION_COLUMNS,
        CLOSURE_ONLY_FIELDS,
        PREVIEW_COMPARISON_FILES,
        AptaIndexCheckpoint1ApplyError,
        build_tracked_resolutions,
        check_production_expectations,
        check_special_records,
        count_manual_decisions,
        format_closure_markdown,
    )
    from adapters.aptaindex_checkpoint1_dry_run import (
        serialise_aptaindex_simulation_sequence_free,
        simulate_aptaindex_checkpoint1_application,
    )
    from adapters.aptaindex_checkpoint1_review import (
        AptaIndexCheckpoint1ReviewError,
        load_default_policy,
        validate_review_package,
    )
    from adapters.aptadb_checkpoint1_review import (
        AptaDBCheckpoint1ReviewError,
        read_csv_rows,
    )
    from adapters.aptaindex_s3 import (
        PRIMARY_ROUTE_CHEMISTRY_REVIEW,
        PRIMARY_ROUTE_REJECT,
        PRIMARY_ROUTE_SSDNA,
        index_constant_proposals,
    )

    if not Path(checkpoint_dir).is_absolute():
        checkpoint_dir = repo_root / checkpoint_dir
    checkpoint_dir = Path(checkpoint_dir).resolve()
    output_dir = _assert_aptaindex_resolved_output(
        output_dir, checkpoint_dir=checkpoint_dir
    )
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
    metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)
    if preview_dir is None:
        preview_dir = checkpoint_dir / "dry_run"
    if not Path(preview_dir).is_absolute():
        preview_dir = repo_root / preview_dir
    preview_dir = preview_dir.resolve()
    if verify_production_hashes is None:
        verify_production_hashes = expected_source_rows == 1050
    if compare_to_preview is None:
        compare_to_preview = expected_source_rows == 1050

    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "aptaindex_checkpoint1_manual_review.csv"
    group_path = review_dir / "aptaindex_checkpoint1_constant_group_review.csv"
    bulk_path = review_dir / "aptaindex_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "aptaindex_s3_canonical.csv"
    decision_path = checkpoint_dir / "aptaindex_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_aptaindex.csv"
    parked_ssdna_path = checkpoint_dir / "aptaindex_s3_parked_ssdna.csv"
    parked_chemistry_path = checkpoint_dir / "aptaindex_s3_parks.csv"
    s1_path = repo_root / "data" / "interim" / "extracted" / "aptaindex_extracted.csv"
    s2_path = repo_root / "data" / "interim" / "normalised" / "aptaindex_normalised.csv"
    qc_path = repo_root / "data" / "interim" / "normalised" / "aptaindex_s2_qc.csv"
    sidecar_path = (
        repo_root / "data" / "interim" / "extracted" / "aptaindex_source_metadata.csv"
    )
    proposals_path = (
        repo_root
        / "data"
        / "interim"
        / "normalised"
        / "detected_constants_aptaindex.csv"
    )
    rec_json = (
        repo_root
        / "config"
        / "checkpoint_reviews"
        / "aptaindex_checkpoint1_recommendations.json"
    )
    raw_path = (
        repo_root / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
    )

    required = [
        queue_path,
        bulk_path,
        canonical_path,
        decision_path,
        rejection_path,
        s2_path,
        qc_path,
        sidecar_path,
    ]
    for path in required:
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing apply input: {path.name}")

    preview_hash_paths = {
        key: preview_dir / preview_name
        for key, preview_name, _applied in PREVIEW_COMPARISON_FILES
    }
    preview_hashes_before = (
        _hash_paths(preview_hash_paths) if compare_to_preview else {}
    )

    hashes_before = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path) if group_path.is_file() else "",
        "bulk": sha256_file(bulk_path),
        "s1": sha256_file(s1_path) if s1_path.is_file() else "",
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path) if proposals_path.is_file() else "",
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw": sha256_file(raw_path) if raw_path.is_file() else "",
    }
    if verify_production_hashes:
        if hashes_before["queue"] != EXPECTED_APTAINDEX_REVIEW_SHA256:
            raise Checkpoint1ApplyError(
                "AptaIndex review SHA-256 does not match the locked human review"
            )
        if hashes_before["bulk"] != EXPECTED_APTAINDEX_BULK_SHA256:
            raise Checkpoint1ApplyError(
                "AptaIndex bulk-confirmation SHA-256 does not match the locked file"
            )
        if hashes_before["raw"] and hashes_before["raw"] != EXPECTED_APTAINDEX_RAW_SHA256:
            raise Checkpoint1ApplyError("AptaIndex raw SHA-256 drifted")
        if hashes_before["s1"] and hashes_before["s1"] != EXPECTED_APTAINDEX_S1_SHA256:
            raise Checkpoint1ApplyError("AptaIndex S1 SHA-256 drifted")
        if hashes_before["s2"] != EXPECTED_APTAINDEX_S2_S3_SHA256:
            raise Checkpoint1ApplyError("AptaIndex S2 SHA-256 drifted")
        if hashes_before["s3"] != EXPECTED_APTAINDEX_S2_S3_SHA256:
            raise Checkpoint1ApplyError("AptaIndex S3 canonical SHA-256 drifted")

    queue_rows = read_csv_rows(queue_path)
    group_rows = read_csv_rows(group_path) if group_path.is_file() else []
    bulk_rows = read_csv_rows(bulk_path)
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk,
        )
    except Exception as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if not report.ok:
        raise Checkpoint1ApplyError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    if report.unresolved_manual_decisions or report.audit_only_unconfirmed:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for CHECKPOINT-1 application"
        )
    if verify_production_hashes and (
        report.total_review_records != 206
        or report.ready_for_application != 206
        or report.blocking_issues
    ):
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for CHECKPOINT-1 application"
        )

    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path) if rejection_path.is_file() else []
    parked_ssdna = (
        read_csv_rows(parked_ssdna_path) if parked_ssdna_path.is_file() else []
    )
    parked_chemistry = (
        read_csv_rows(parked_chemistry_path) if parked_chemistry_path.is_file() else []
    )
    qc_rows = read_csv_rows(qc_path)
    sidecar_rows = read_csv_rows(sidecar_path)
    proposal_rows = read_csv_rows(proposals_path) if proposals_path.is_file() else []
    s2_qc_by_id = {row["record_id"]: row for row in qc_rows}
    source_metadata_by_id = {row["record_id"]: row for row in sidecar_rows}
    proposals_by_record = index_constant_proposals(canonical_rows, proposal_rows)
    policy = load_default_policy(repo_root)

    def _simulate():
        try:
            return simulate_aptaindex_checkpoint1_application(
                queue_rows=queue_rows,
                group_rows=group_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=source_metadata_by_id,
                s2_qc_by_id=s2_qc_by_id,
                policy=policy,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                existing_rejection_rows=rejection_rows,
                existing_parked_ssdna=parked_ssdna,
                existing_parked_chemistry=parked_chemistry,
                expected_source_rows=expected_source_rows,
            )
        except (AptaIndexCheckpoint1ReviewError, AptaDBCheckpoint1ReviewError) as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if serialise_aptaindex_simulation_sequence_free(
            simulation
        ) != serialise_aptaindex_simulation_sequence_free(second):
            raise Checkpoint1ApplyError(
                "AptaIndex CHECKPOINT-1 application was not byte-identical "
                "across deterministic in-memory rerun"
            )
        deterministic_ok = True

    record_decisions = count_manual_decisions(queue_rows)
    if expected_source_rows == 1050:
        try:
            check_production_expectations(
                simulation=simulation, record_decisions=record_decisions
            )
            check_special_records(simulation)
        except AptaIndexCheckpoint1ApplyError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    compare_dir = checkpoint_dir / "closure_validation" / "apply_vs_preview"
    compare_dir = _assert_output_dir_allowed(repo_root, compare_dir)
    compare_paths = _write_aptaindex_transform_csvs(compare_dir, simulation)
    preview_comparison_ok = False
    semantic_mismatches = 0
    if compare_to_preview:
        mismatches = _compare_aptaindex_applied_to_preview(
            applied_paths=compare_paths, preview_dir=preview_dir
        )
        if mismatches:
            raise Checkpoint1ApplyError(
                "Real application is not byte-identical to the validated "
                "dry-run preview for: " + ", ".join(mismatches)
            )
        preview_hashes_after_compare = _hash_paths(preview_hash_paths)
        if preview_hashes_after_compare != preview_hashes_before:
            raise Checkpoint1ApplyError(
                "Dry-run preview files changed during real application"
            )
        preview_comparison_ok = True
        semantic_mismatches = 0

    output_dir.mkdir(parents=True, exist_ok=True)
    applied_paths = _write_aptaindex_transform_csvs(output_dir, simulation)
    if compare_to_preview:
        mismatches = _compare_aptaindex_applied_to_preview(
            applied_paths=applied_paths, preview_dir=preview_dir
        )
        if mismatches:
            raise Checkpoint1ApplyError(
                "Authoritative apply outputs are not byte-identical to the "
                "validated dry-run preview for: " + ", ".join(mismatches)
            )

    simulation.stats["authorised_for_s4"] = int(simulation.stats["technically_eligible"])
    simulation.stats["checkpoint_closed"] = True

    tracked_rows = build_tracked_resolutions(
        decisions=simulation.preview_decisions,
        queue_rows=queue_rows,
        route_changed_ids=simulation.route_changed_ids,
    )
    s4_rows = [
        {
            "record_id": row["record_id"],
            "resolved_decision": "accept",
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
        }
        for row in tracked_rows
        if row["authorised_for_s4"] == "true"
    ]
    parked_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] in {PRIMARY_ROUTE_SSDNA, PRIMARY_ROUTE_CHEMISTRY_REVIEW}
    ]
    rejected_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] == PRIMARY_ROUTE_REJECT
    ]
    write_csv_atomic(
        tracked_manifest,
        APTAINDEX_TRACKED_RESOLUTION_COLUMNS,
        tracked_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_s4_authorised_ids.csv",
        S4_ID_COLUMNS,
        s4_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_parked_ids.csv",
        PARKED_ID_COLUMNS,
        parked_id_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        output_dir / "aptaindex_checkpoint1_rejected_ids.csv",
        REJECTED_ID_COLUMNS,
        rejected_id_rows,
        quoting=csv.QUOTE_ALL,
    )

    transform_hashes = {name: sha256_file(path) for name, path in applied_paths.items()}
    closure_paths = {
        "s4_authorised_ids": output_dir / "aptaindex_checkpoint1_s4_authorised_ids.csv",
        "parked_ids": output_dir / "aptaindex_checkpoint1_parked_ids.csv",
        "rejected_ids": output_dir / "aptaindex_checkpoint1_rejected_ids.csv",
        "tracked_manifest": tracked_manifest,
    }
    output_hashes = {
        **transform_hashes,
        **{name: sha256_file(path) for name, path in closure_paths.items()},
    }

    review_hashes = {
        "queue": hashes_before["queue"],
        "groups": hashes_before["groups"],
        "bulk": hashes_before["bulk"],
        "rec_json": hashes_before["rec_json"],
    }
    integrity = {
        "s1": hashes_before["s1"],
        "s2": hashes_before["s2"],
        "s3": hashes_before["s3"],
        "sidecar": hashes_before["sidecar"],
        "raw": hashes_before["raw"],
        "deterministic_ok": "true" if deterministic_ok else "false",
    }
    summary_text = format_closure_markdown(
        simulation,
        review_hashes=review_hashes,
        integrity=integrity,
        output_hashes=output_hashes,
        record_decisions=record_decisions,
        deterministic_ok=deterministic_ok,
        preview_comparison_ok=preview_comparison_ok or not compare_to_preview,
    )
    if APTAINDEX_CHECKPOINT_CLOSED_STATEMENT not in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary missing checkpoint-closed statement"
        )
    if str(repo_root.resolve()) in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary must not contain absolute repository paths"
        )
    summary_path = output_dir / "aptaindex_checkpoint1_resolution_summary.md"
    _write_text_atomic(summary_path, summary_text)
    _write_text_atomic(
        output_dir / "README.md",
        "CHECKPOINT-1 CLOSED.\n"
        "These files are the authoritative AptaIndex post-review artefacts.\n"
        "They must not overwrite S2, pre-review S3, or dry-run previews.\n"
        "S4 has not started.\n",
    )
    output_hashes["summary"] = sha256_file(summary_path)

    metadata = {
        "source_key": "aptaindex",
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "checkpoint_status": "closed",
        "checkpoint_closed": True,
        "s4_started": False,
        "next_stage": "global_S4_handoff",
        "reviewed_records": int(simulation.stats["reviewed_records"]),
        "record_decisions": record_decisions,
        "human_reviewed_drops": int(simulation.stats["human_reviewed_drops"]),
        "technical_rejects_after_review": int(
            simulation.stats["technical_rejects_after_review"]
        ),
        "parked_ssdna": int(simulation.stats["parked_ssdna"]),
        "parked_chemistry_review": int(simulation.stats["parked_chemistry_review"]),
        "parked_non_protein": 0,
        "technically_eligible": int(simulation.stats["technically_eligible"]),
        "authorised_for_s4": int(simulation.stats["authorised_for_s4"]),
        "authorised_for_s4_meaning": (
            "Technically eligible RNA/2F-RNA after AptaIndex sequence/molecule "
            "CHECKPOINT-1 and eligible to enter the future corpus-wide "
            "target-normalisation stage. Does not mean every AptaIndex record "
            "is included in S4, nor protein target confirmed, target "
            "canonicalised, UniProt resolved, evidence threshold passed, "
            "leakage check passed globally, globally deduplicated, balanced, "
            "or CHECKPOINT-2 approved."
        ),
        "route_changed": int(simulation.stats["route_changed"]),
        "sequence_corrections": int(simulation.stats["sequence_corrections"]),
        "molecule_overrides": int(simulation.stats["molecule_overrides"]),
        "records_trimmed": int(simulation.stats["records_trimmed"]),
        "core_length_changed": int(simulation.stats["core_length_changed"]),
        "unconsumed_decisions": 0,
        "review_file_sha256": hashes_before["queue"],
        "review_bulk_sha256": hashes_before["bulk"],
        "recommendations_sha256": hashes_before["rec_json"],
        "s1_sha256": hashes_before["s1"],
        "s2_sha256": hashes_before["s2"],
        "s3_sha256": hashes_before["s3"],
        "sidecar_sha256": hashes_before["sidecar"],
        "raw_sha256": hashes_before["raw"],
        "output_hashes": output_hashes,
        "preview_comparison_ok": preview_comparison_ok or not compare_to_preview,
        "semantic_mismatches": semantic_mismatches,
        "deterministic_rerun_ok": deterministic_ok,
        "closure_only_fields": list(CLOSURE_ONLY_FIELDS),
        "application_mode": "apply",
    }
    _write_json_atomic(metadata_out, metadata)
    output_hashes["metadata"] = sha256_file(metadata_out)

    if check_deterministic_rerun:
        determinism_dir = checkpoint_dir / "closure_validation" / "determinism"
        determinism_dir = _assert_output_dir_allowed(repo_root, determinism_dir)
        third = _simulate()
        verify_paths = _write_aptaindex_transform_csvs(determinism_dir, third)
        for name, path in applied_paths.items():
            if sha256_file(path) != sha256_file(verify_paths[name]):
                raise Checkpoint1ApplyError(
                    f"Deterministic verification mismatch for {name}"
                )

    hashes_after = {
        "queue": sha256_file(queue_path),
        "groups": sha256_file(group_path) if group_path.is_file() else "",
        "bulk": sha256_file(bulk_path),
        "s1": sha256_file(s1_path) if s1_path.is_file() else "",
        "s2": sha256_file(s2_path),
        "s3": sha256_file(canonical_path),
        "sidecar": sha256_file(sidecar_path),
        "qc": sha256_file(qc_path),
        "proposals": sha256_file(proposals_path) if proposals_path.is_file() else "",
        "rec_json": sha256_file(rec_json) if rec_json.is_file() else "",
        "raw": sha256_file(raw_path) if raw_path.is_file() else "",
    }
    if hashes_after != hashes_before:
        raise Checkpoint1ApplyError(
            "CHECKPOINT-1 apply mutated an immutable input artefact"
        )

    stats = dict(simulation.stats)
    print(
        "source=aptaindex\n"
        "mode=apply\n"
        "checkpoint_status=closed\n"
        f"total_records={stats['total_records']}\n"
        f"reviewed_records={stats['reviewed_records']}\n"
        f"human_keep={stats['human_keep']}\n"
        f"human_edit={stats['human_edit']}\n"
        f"human_drop={stats['human_drop']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"parked_ssdna={stats['parked_ssdna']}\n"
        f"parked_chemistry_review={stats['parked_chemistry_review']}\n"
        f"technical_rejects_after_review={stats['technical_rejects_after_review']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        f"review_queue_sha256={hashes_before['queue']}\n"
        f"review_bulk_sha256={hashes_before['bulk']}\n"
        f"s1_sha256={hashes_before['s1']}\n"
        f"s2_sha256={hashes_before['s2']}\n"
        f"s3_sha256={hashes_before['s3']}\n"
        f"raw_sha256={hashes_before['raw']}\n"
        f"preview_comparison={'pass' if preview_comparison_ok or not compare_to_preview else 'fail'}\n"
        f"semantic_mismatches={semantic_mismatches}\n"
        f"deterministic_rerun={'pass' if deterministic_ok else 'skipped'}\n"
        "CHECKPOINT-1 CLOSED\n"
        "S4 has not started"
    )
    return AptaIndexApplyResult(
        output_dir=output_dir,
        metadata_out=metadata_out,
        tracked_manifest=tracked_manifest,
        summary_out=summary_path,
        output_hashes=output_hashes,
        stats=stats,
        preview_comparison_ok=preview_comparison_ok or not compare_to_preview,
        deterministic_rerun_ok=deterministic_ok,
        semantic_mismatches=semantic_mismatches,
        checkpoint_closed=True,
    )


FROZEN_ENA_REVIEW_HASHES: dict[str, str] = {
    "ena_checkpoint1_manual_review.csv": (
        "27482ea0765905d01b9fb571393735ab75c4646bfe1d85bca091cdf4221d3588"
    ),
    "ena_checkpoint1_manual_review_index.csv": (
        "8851302adb1930b34aeaa5838ff9c7a1abc0703f5c27b3853d5452c12caaaafe"
    ),
    "ena_checkpoint1_constant_rule_review.csv": (
        "dee948714a5563158a596f37af2bccb537d4af7370220ce889f64d40eef847c4"
    ),
    "ena_checkpoint1_constant_exceptions.csv": (
        "dd65eac66fd08e13696d2f439459a3675d1104abbb8ca0e41b2e7ae8954c48df"
    ),
    "ena_checkpoint1_legacy_collapse_reconciliation.csv": (
        "e2efc138c26aa291611461a29c055f77ddf51fafe286a4167bd07472538d7be9"
    ),
    "ena_checkpoint1_legacy_collapse_reconciliation_index.csv": (
        "e2efc138c26aa291611461a29c055f77ddf51fafe286a4167bd07472538d7be9"
    ),
    "ena_checkpoint1_bulk_audit_confirmation.csv": (
        "36197eae089fc61762bf40c8106561c17ae4a973b882e3307c3363d535a56f19"
    ),
}

FROZEN_ENA_PIPELINE_HASHES: dict[str, str] = {
    "s1": "3d823f4007cde419e2c5cb4a71230c8febaefbeb237cf54e5888740c02578fac",
    "sidecar": "977cf57be81152e2c5307db68928ccdfc9f66aa2c0a20f8999eab4c9ba78acad",
    "s3_decisions": (
        "14a70d3dc80dc7078d92a3eeaff45ee26c73467dd5131e4a2c2c4952a5dc857b"
    ),
}

ACCEPTED_ENA_DRY_RUN_HASHES: dict[str, str] = {
    "canonical": (
        "3f8995e139478b43e322460906486f388aaaf79685460b07077757c7a6dc2005"
    ),
    "routing": "af919b719665d1162c5d1e1dbdb3d60a81e46a7b2cb6f88e6ac6e2e0603694e0",
    "rejection": (
        "e293cbb6231276940820250246facb9dd095fd783131d0db85ae9334f7a4fb41"
    ),
    "parked_construct": (
        "a51eb535939fa48d92e15ae5892f18228c96e57cfb1ebcb7c794dda801865301"
    ),
    "eligible": "b94bcde4d52d4a20e70fa46f7acdc78dafc1fb81dc558e68ada931f94d780233",
    "change_report": (
        "6d38db8af2382468b6f40e6f7b1c43a95b12f71a81fe1e337e41e387eaf83aa9"
    ),
    "group_summary": (
        "d889cdfcc93779bd2a31e491bf2c72bf35ca3deb3c0b4487663929efec2a4be5"
    ),
    "large_trim_human_approved": (
        "63d363911a986fd8d68977fc67770266d6f22256c616b25908800bd0d6baace8"
    ),
    "guard_rail_failures": (
        "9d8e87387be359b8521d0b9ecca6da3141408b8094b71d34de4f29332e7f0a83"
    ),
}


@dataclass(frozen=True)
class EnaApplyResult:
    """Authoritative ENA CHECKPOINT-1 apply/closure result."""

    output_dir: Path
    metadata_out: Path
    tracked_manifest: Path
    summary_out: Path
    output_hashes: dict[str, str]
    stats: dict[str, int | str | bool | float]
    preview_comparison_ok: bool
    deterministic_rerun_ok: bool
    semantic_mismatches: int
    byte_identical: dict[str, bool]
    checkpoint_closed: bool


def _assert_ena_resolved_output(path: Path, *, checkpoint_dir: Path) -> Path:
    resolved = path.resolve()
    checkpoint_resolved = checkpoint_dir.resolve()
    if resolved == checkpoint_resolved:
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the ENA CHECKPOINT-1 snapshot directory"
        )
    dry_run_dir = (checkpoint_resolved / "dry_run").resolve()
    if resolved == dry_run_dir:
        raise Checkpoint1ApplyError(
            "Refusing to overwrite the validated dry-run preview directory"
        )
    lowered = [part.lower() for part in resolved.parts]
    if any(name in APPLY_FORBIDDEN_DIR_NAMES for name in lowered):
        raise Checkpoint1ApplyError(
            f"Resolved output must not use a dry-run/S2/S3/S4 directory: {resolved}"
        )
    return resolved


def _write_ena_transform_csvs(output_dir: Path, simulation: object) -> dict[str, Path]:
    from adapters.ena_checkpoint1_apply import (
        CHANGE_REPORT_COLUMNS,
        ELIGIBLE_PREVIEW_COLUMNS,
        GROUP_SUMMARY_COLUMNS,
        GUARD_RAIL_FAILURE_COLUMNS,
        LARGE_TRIM_RECORD_COLUMNS,
        EnaDryRunSimulation,
    )
    from adapters.ena_s3 import DECISION_COLUMNS, PARK_COLUMNS, REJECTION_COLUMNS
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    if not isinstance(simulation, EnaDryRunSimulation):
        raise Checkpoint1ApplyError("Apply payload has unexpected type")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "canonical": output_dir / "ena_checkpoint1_applied_canonical.csv",
        "routing": output_dir / "ena_checkpoint1_applied_routing.csv",
        "rejection": output_dir / "ena_checkpoint1_applied_rejection.csv",
        "parked_construct": output_dir / "ena_checkpoint1_applied_parked_construct.csv",
        "eligible": output_dir / "ena_checkpoint1_applied_eligible.csv",
        "change_report": output_dir / "ena_checkpoint1_applied_change_report.csv",
        "group_summary": output_dir / "ena_checkpoint1_applied_group_summary.csv",
        "large_trim_human_approved": (
            output_dir / "ena_checkpoint1_applied_large_trim_human_approved.csv"
        ),
        "guard_rail_failures": (
            output_dir / "ena_checkpoint1_applied_guard_rail_failures.csv"
        ),
    }
    write_corpus_csv_atomic(
        paths["canonical"], simulation.preview_canonical, columns=CORPUS_COLUMNS
    )
    write_csv_atomic(paths["routing"], DECISION_COLUMNS, simulation.preview_decisions)
    write_csv_atomic(
        paths["rejection"], REJECTION_COLUMNS, simulation.preview_rejections
    )
    write_csv_atomic(
        paths["parked_construct"], PARK_COLUMNS, simulation.preview_parked_construct
    )
    write_csv_atomic(
        paths["eligible"], ELIGIBLE_PREVIEW_COLUMNS, simulation.preview_eligible
    )
    write_csv_atomic(
        paths["change_report"], CHANGE_REPORT_COLUMNS, simulation.change_report
    )
    write_csv_atomic(
        paths["group_summary"], GROUP_SUMMARY_COLUMNS, simulation.group_summaries
    )
    write_csv_atomic(
        paths["large_trim_human_approved"],
        LARGE_TRIM_RECORD_COLUMNS,
        simulation.large_trim_records,
    )
    write_csv_atomic(
        paths["guard_rail_failures"],
        GUARD_RAIL_FAILURE_COLUMNS,
        simulation.guard_rail_failure_rows,
    )
    return paths


def _ena_csv_scientific_mismatches(preview_path: Path, applied_path: Path) -> int:
    """Count cell mismatches, ignoring checkpoint_status wrapper metadata."""
    with preview_path.open("r", encoding="utf-8", newline="") as handle:
        preview_reader = csv.DictReader(handle)
        preview_fields = list(preview_reader.fieldnames or [])
        preview_rows = list(preview_reader)
    with applied_path.open("r", encoding="utf-8", newline="") as handle:
        applied_reader = csv.DictReader(handle)
        applied_fields = list(applied_reader.fieldnames or [])
        applied_rows = list(applied_reader)
    scientific_preview = [name for name in preview_fields if name != "checkpoint_status"]
    scientific_applied = [name for name in applied_fields if name != "checkpoint_status"]
    if scientific_preview != scientific_applied:
        return max(len(preview_rows), len(applied_rows), 1)
    if len(preview_rows) != len(applied_rows):
        return abs(len(preview_rows) - len(applied_rows)) or 1
    mismatches = 0
    for left, right in zip(preview_rows, applied_rows, strict=True):
        for field_name in scientific_preview:
            if (left.get(field_name) or "") != (right.get(field_name) or ""):
                mismatches += 1
    return mismatches


def _compare_ena_applied_to_preview(
    *,
    applied_paths: Mapping[str, Path],
    preview_dir: Path,
) -> tuple[dict[str, bool], int]:
    from adapters.ena_checkpoint1_apply import PREVIEW_COMPARISON_FILES

    missing = [
        preview_name
        for _key, preview_name, _applied in PREVIEW_COMPARISON_FILES
        if not (preview_dir / preview_name).is_file()
    ]
    if missing:
        raise Checkpoint1ApplyError(
            "Validated dry-run preview is incomplete; refusing real apply: "
            + ", ".join(missing)
        )
    byte_identical: dict[str, bool] = {}
    semantic_total = 0
    scientific_mismatches: list[str] = []
    for key, preview_name, _applied_name in PREVIEW_COMPARISON_FILES:
        preview_path = preview_dir / preview_name
        applied_path = applied_paths[key]
        identical = preview_path.read_bytes() == applied_path.read_bytes()
        byte_identical[key] = identical
        if identical:
            continue
        cell_mismatches = _ena_csv_scientific_mismatches(preview_path, applied_path)
        semantic_total += cell_mismatches
        if cell_mismatches:
            scientific_mismatches.append(key)
    if scientific_mismatches:
        raise Checkpoint1ApplyError(
            "Real application has scientific mismatches versus the validated "
            "dry-run preview for: " + ", ".join(scientific_mismatches)
        )
    return byte_identical, semantic_total


def run_ena_checkpoint1_apply(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    tracked_manifest: Path,
    metadata_out: Path,
    preview_dir: Path | None = None,
    check_deterministic_rerun: bool = True,
    expected_total_rows: int | None = 679,
    verify_frozen_review: bool = True,
    compare_to_pristine: bool = True,
    skip_pipeline_integrity: bool = False,
    compare_to_preview: bool | None = None,
    expected_review_hashes: Mapping[str, str] | None = None,
    expected_pipeline_hashes: Mapping[str, str] | None = None,
    expected_dry_run_hashes: Mapping[str, str] | None = None,
) -> EnaApplyResult:
    """Apply completed ENA CHECKPOINT-1 review and close the checkpoint.

    Uses the same ``simulate_ena_checkpoint1_application`` transform as
    dry-run. Does not prepare a global-S4 handoff or start S4.
    """
    from adapters.ena_checkpoint1_apply import (
        AUTHORISED_FOR_S4_MEANING,
        CLOSURE_ONLY_FIELDS,
        ENA_CHECKPOINT_CLOSED_STATEMENT,
        ENA_TRACKED_RESOLUTION_COLUMNS,
        PREVIEW_COMPARISON_FILES,
        SOURCE_DATASET,
        EnaCheckpoint1ApplyError,
        build_tracked_resolutions,
        compare_ena_package_to_pristine,
        count_manual_decisions,
        format_closure_markdown,
        load_default_policy,
        serialise_ena_simulation,
        simulate_ena_checkpoint1_application,
    )
    from adapters.ena_checkpoint1_review import (
        read_csv_rows,
        validate_ena_review_package,
    )
    from adapters.ena_s3 import (
        PRIMARY_ROUTE_CONSTRUCT,
        PRIMARY_ROUTE_ELIGIBLE,
        PRIMARY_ROUTE_REJECT,
        index_constant_proposals,
    )
    from checkpoint1_prepare_review import prepare_ena_checkpoint1_review
    from s3_classify import EXPECTED_ENA_RAW_SHA256, EXPECTED_ENA_S2_HASH

    if not Path(checkpoint_dir).is_absolute():
        checkpoint_dir = repo_root / checkpoint_dir
    checkpoint_dir = Path(checkpoint_dir).resolve()
    output_dir = _assert_ena_resolved_output(
        output_dir, checkpoint_dir=checkpoint_dir
    )
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    tracked_manifest = _assert_tracked_path_allowed(repo_root, tracked_manifest)
    metadata_out = _assert_tracked_path_allowed(repo_root, metadata_out)
    if preview_dir is None:
        preview_dir = checkpoint_dir / "dry_run"
    if not Path(preview_dir).is_absolute():
        preview_dir = repo_root / preview_dir
    preview_dir = preview_dir.resolve()
    if compare_to_preview is None:
        compare_to_preview = expected_total_rows == 679
    if expected_review_hashes is None and verify_frozen_review:
        expected_review_hashes = FROZEN_ENA_REVIEW_HASHES
    if expected_pipeline_hashes is None and not skip_pipeline_integrity:
        expected_pipeline_hashes = FROZEN_ENA_PIPELINE_HASHES
    if expected_dry_run_hashes is None and compare_to_preview and expected_total_rows == 679:
        expected_dry_run_hashes = ACCEPTED_ENA_DRY_RUN_HASHES

    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "ena_checkpoint1_manual_review.csv"
    index_path = review_dir / "ena_checkpoint1_manual_review_index.csv"
    rule_path = review_dir / "ena_checkpoint1_constant_rule_review.csv"
    membership_path = review_dir / "ena_checkpoint1_constant_rule_membership.csv"
    exception_path = review_dir / "ena_checkpoint1_constant_exceptions.csv"
    recon_path = review_dir / "ena_checkpoint1_legacy_collapse_reconciliation.csv"
    recon_index_path = (
        review_dir / "ena_checkpoint1_legacy_collapse_reconciliation_index.csv"
    )
    bulk_path = review_dir / "ena_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "ena_s3_canonical.csv"
    decision_path = checkpoint_dir / "ena_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_ena.csv"
    parked_path = checkpoint_dir / "ena_s3_parked_construct.csv"
    s1_path = repo_root / "data" / "interim" / "extracted" / "ena_extracted.csv"
    sidecar_path = repo_root / "data" / "interim" / "extracted" / "ena_source_metadata.csv"
    s2_path = repo_root / "data" / "interim" / "normalised" / "ena_normalised.csv"
    qc_path = repo_root / "data" / "interim" / "normalised" / "ena_s2_qc.csv"
    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "ena_constant_region_proposals.csv"
    )
    s2_membership_path = (
        repo_root
        / "data"
        / "interim"
        / "normalised"
        / "ena_constant_region_membership.csv"
    )
    raw_path = (
        repo_root
        / "data"
        / "raw"
        / "ENA"
        / "review_v2"
        / "ena_selected_after_manual_review.csv"
    )
    handoff_json = repo_root / "config" / "global_s4_sources" / "ena.json"
    handoff_csv = repo_root / "data" / "interim" / "global_s4_ready" / "ena_global_s4_input.csv"

    required = [
        queue_path,
        rule_path,
        exception_path,
        recon_path,
        bulk_path,
        canonical_path,
        decision_path,
        s2_path,
        qc_path,
        sidecar_path,
        proposals_path,
    ]
    for path in required:
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing apply input: {path.name}")

    preview_hash_paths = {
        key: preview_dir / preview_name
        for key, preview_name, _applied in PREVIEW_COMPARISON_FILES
    }
    preview_hashes_before = (
        _hash_paths(preview_hash_paths) if compare_to_preview else {}
    )
    if expected_dry_run_hashes:
        for key, expected in expected_dry_run_hashes.items():
            actual = preview_hashes_before.get(key, "")
            if actual != expected:
                raise Checkpoint1ApplyError(
                    f"Accepted dry-run hash mismatch for {key}"
                )

    review_hash_paths = {
        "ena_checkpoint1_manual_review.csv": queue_path,
        "ena_checkpoint1_manual_review_index.csv": index_path,
        "ena_checkpoint1_constant_rule_review.csv": rule_path,
        "ena_checkpoint1_constant_exceptions.csv": exception_path,
        "ena_checkpoint1_legacy_collapse_reconciliation.csv": recon_path,
        "ena_checkpoint1_legacy_collapse_reconciliation_index.csv": recon_index_path,
        "ena_checkpoint1_bulk_audit_confirmation.csv": bulk_path,
    }
    hashes_before = {
        name: sha256_file(path) if path.is_file() else ""
        for name, path in review_hash_paths.items()
    }
    hashes_before.update(
        {
            "raw": sha256_file(raw_path) if raw_path.is_file() else "",
            "s1": sha256_file(s1_path) if s1_path.is_file() else "",
            "sidecar": sha256_file(sidecar_path),
            "s2": sha256_file(s2_path),
            "s3": sha256_file(canonical_path),
            "s3_decisions": sha256_file(decision_path),
            "qc": sha256_file(qc_path),
            "proposals": sha256_file(proposals_path),
            "membership": (
                sha256_file(membership_path) if membership_path.is_file() else ""
            ),
        }
    )
    if verify_frozen_review:
        if expected_review_hashes is None:
            raise Checkpoint1ApplyError(
                "Frozen ENA review hashes must be supplied as a run-time gate"
            )
        for name, expected in expected_review_hashes.items():
            actual = hashes_before.get(name, "")
            if actual != expected:
                raise Checkpoint1ApplyError(
                    f"Frozen review hash mismatch for {name}"
                )
    if not skip_pipeline_integrity:
        if hashes_before["raw"] and hashes_before["raw"] != EXPECTED_ENA_RAW_SHA256:
            raise Checkpoint1ApplyError("ENA raw SHA-256 does not match freeze")
        if hashes_before["s2"] != EXPECTED_ENA_S2_HASH:
            raise Checkpoint1ApplyError("ENA S2 SHA-256 does not match freeze")
        if hashes_before["s3"] != EXPECTED_ENA_S2_HASH:
            raise Checkpoint1ApplyError("ENA S3 canonical SHA-256 does not match freeze")
        if expected_pipeline_hashes:
            for key, expected in expected_pipeline_hashes.items():
                if hashes_before.get(key, "") != expected:
                    raise Checkpoint1ApplyError(
                        f"ENA {key} SHA-256 does not match freeze"
                    )

    queue_rows = read_csv_rows(queue_path)
    rule_rows = read_csv_rows(rule_path)
    exception_rows = read_csv_rows(exception_path)
    reconciliation_rows = read_csv_rows(recon_path)
    membership_rows = (
        read_csv_rows(membership_path) if membership_path.is_file() else []
    )
    bulk_rows = read_csv_rows(bulk_path)
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_ena_review_package(
            queue_rows=queue_rows,
            rule_rows=rule_rows,
            exception_rows=exception_rows,
            reconciliation_rows=reconciliation_rows,
            bulk_confirmation=bulk,
        )
    except Exception as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if not report.ok or report.blocking_issues:
        raise Checkpoint1ApplyError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    if (
        expected_total_rows == 679
        and (
            report.total_review_records != 77
            or report.unresolved_manual_decisions != 0
            or report.unresolved_constant_groups != 0
            or report.unresolved_exceptions != 0
            or report.unresolved_reconciliation_groups != 0
            or report.audit_only_unconfirmed != 0
            or report.ready_for_application != 77
        )
    ):
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for CHECKPOINT-1 application"
        )

    if compare_to_pristine:
        pristine_dir = checkpoint_dir / "closure_validation" / "pristine"
        if pristine_dir.resolve() == review_dir.resolve():
            raise Checkpoint1ApplyError(
                "Refusing to overwrite the completed human review with pristine"
            )
        prepare_ena_checkpoint1_review(
            repo_root=repo_root,
            checkpoint_dir=checkpoint_dir,
            output_dir=pristine_dir,
            expected_total_rows=expected_total_rows,
        )
        try:
            compare_ena_package_to_pristine(
                reviewed_queue=queue_rows,
                pristine_queue=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_manual_review.csv"
                ),
                reviewed_rules=rule_rows,
                pristine_rules=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_constant_rule_review.csv"
                ),
                reviewed_exceptions=exception_rows,
                pristine_exceptions=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_constant_exceptions.csv"
                ),
                reviewed_reconciliation=reconciliation_rows,
                pristine_reconciliation=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_legacy_collapse_reconciliation.csv"
                ),
                reviewed_bulk=bulk_rows,
                pristine_bulk=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_bulk_audit_confirmation.csv"
                ),
                reviewed_membership=membership_rows,
                pristine_membership=(
                    read_csv_rows(
                        pristine_dir / "ena_checkpoint1_constant_rule_membership.csv"
                    )
                    if (pristine_dir / "ena_checkpoint1_constant_rule_membership.csv").is_file()
                    else []
                ),
            )
        except EnaCheckpoint1ApplyError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path) if rejection_path.is_file() else []
    parked_rows = read_csv_rows(parked_path) if parked_path.is_file() else []
    qc_rows = read_csv_rows(qc_path)
    sidecar_rows = read_csv_rows(sidecar_path)
    proposal_rows = read_csv_rows(proposals_path)
    s2_membership = (
        read_csv_rows(s2_membership_path) if s2_membership_path.is_file() else []
    )
    qc_by_id = _index_rows(qc_rows)
    sidecar_by_id = _index_rows(sidecar_rows)
    proposals_by_record = index_constant_proposals(
        qc_rows, proposal_rows, s2_membership
    )
    policy = load_default_policy(repo_root)

    def _simulate():
        try:
            return simulate_ena_checkpoint1_application(
                queue_rows=queue_rows,
                rule_rows=rule_rows,
                exception_rows=exception_rows,
                reconciliation_rows=reconciliation_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=sidecar_by_id,
                s2_qc_by_id=qc_by_id,
                policy=policy,
                membership_rows=membership_rows,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                existing_rejection_rows=rejection_rows,
                existing_parked_construct=parked_rows,
                expected_total_rows=expected_total_rows,
            )
        except EnaCheckpoint1ApplyError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if serialise_ena_simulation(simulation) != serialise_ena_simulation(second):
            raise Checkpoint1ApplyError(
                "ENA CHECKPOINT-1 application was not byte-identical "
                "across deterministic in-memory rerun"
            )
        deterministic_ok = True

    if int(simulation.stats.get("guard_rail_failures") or 0) != 0:
        raise Checkpoint1ApplyError("Apply guard-rail failures are forbidden")
    if int(simulation.stats.get("unresolved_after_consumption") or 0) != 0:
        raise Checkpoint1ApplyError("Unresolved human review remains after apply")

    compare_dir = checkpoint_dir / "closure_validation" / "apply_vs_preview"
    compare_dir = _assert_output_dir_allowed(repo_root, compare_dir)
    compare_paths = _write_ena_transform_csvs(compare_dir, simulation)
    preview_comparison_ok = False
    semantic_mismatches = 0
    byte_identical: dict[str, bool] = {}
    if compare_to_preview:
        byte_identical, semantic_mismatches = _compare_ena_applied_to_preview(
            applied_paths=compare_paths, preview_dir=preview_dir
        )
        preview_hashes_after_compare = _hash_paths(preview_hash_paths)
        if preview_hashes_after_compare != preview_hashes_before:
            raise Checkpoint1ApplyError(
                "Dry-run preview files changed during real application"
            )
        preview_comparison_ok = True

    output_dir.mkdir(parents=True, exist_ok=True)
    applied_paths = _write_ena_transform_csvs(output_dir, simulation)
    if compare_to_preview:
        byte_identical, semantic_mismatches = _compare_ena_applied_to_preview(
            applied_paths=applied_paths, preview_dir=preview_dir
        )

    eligible_n = int(simulation.stats["technically_eligible"])
    simulation.stats["authorised_for_s4"] = eligible_n
    simulation.stats["checkpoint_closed"] = True

    record_decisions = count_manual_decisions(queue_rows)
    tracked_rows = build_tracked_resolutions(
        decisions=simulation.preview_decisions,
        queue_rows=queue_rows,
        route_changed_ids=simulation.route_changed_ids,
    )
    if any(
        row["checkpoint1_resolution_status"] == "pending_checkpoint_1_review"
        for row in tracked_rows
    ):
        raise Checkpoint1ApplyError(
            "Resolved routing still contains pending_checkpoint_1_review"
        )
    s4_rows = [
        {
            "record_id": row["record_id"],
            "resolved_decision": "accept",
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
        }
        for row in tracked_rows
        if row["authorised_for_s4"] == "true"
    ]
    parked_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] == PRIMARY_ROUTE_CONSTRUCT
    ]
    rejected_id_rows = [
        {
            "record_id": row["record_id"],
            "checkpoint1_resolution_status": row["checkpoint1_resolution_status"],
            "review_action": row["manual_decision"],
        }
        for row in tracked_rows
        if row["primary_route"] == PRIMARY_ROUTE_REJECT
    ]
    authorised_n = sum(1 for row in tracked_rows if row["authorised_for_s4"] == "true")
    if authorised_n != eligible_n:
        raise Checkpoint1ApplyError(
            "authorised_for_s4 was not derived from the technical eligible route"
        )
    for row in tracked_rows:
        if row["primary_route"] == PRIMARY_ROUTE_ELIGIBLE:
            if row["authorised_for_s4"] != "true":
                raise Checkpoint1ApplyError(
                    "Eligible technical route must be authorised_for_s4"
                )
        elif row["authorised_for_s4"] != "false":
            raise Checkpoint1ApplyError(
                "Non-eligible technical routes must remain unauthorised for S4"
            )

    write_csv_atomic(
        tracked_manifest, ENA_TRACKED_RESOLUTION_COLUMNS, tracked_rows
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_s4_authorised_ids.csv",
        S4_ID_COLUMNS,
        s4_rows,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_parked_ids.csv",
        PARKED_ID_COLUMNS,
        parked_id_rows,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_rejected_ids.csv",
        REJECTED_ID_COLUMNS,
        rejected_id_rows,
    )

    transform_hashes = {name: sha256_file(path) for name, path in applied_paths.items()}
    closure_paths = {
        "s4_authorised_ids": output_dir / "ena_checkpoint1_s4_authorised_ids.csv",
        "parked_ids": output_dir / "ena_checkpoint1_parked_ids.csv",
        "rejected_ids": output_dir / "ena_checkpoint1_rejected_ids.csv",
        "tracked_manifest": tracked_manifest,
    }
    output_hashes = {
        **transform_hashes,
        **{name: sha256_file(path) for name, path in closure_paths.items()},
    }

    review_hashes = {
        name: hashes_before[name]
        for name in review_hash_paths
        if hashes_before.get(name)
    }
    integrity = {
        "raw": hashes_before["raw"],
        "s1": hashes_before["s1"],
        "sidecar": hashes_before["sidecar"],
        "s2": hashes_before["s2"],
        "s3": hashes_before["s3"],
        "s3_decisions": hashes_before["s3_decisions"],
        "deterministic_ok": "true" if deterministic_ok else "false",
    }
    summary_text = format_closure_markdown(
        simulation,
        review_hashes=review_hashes,
        integrity=integrity,
        output_hashes=output_hashes,
        record_decisions=record_decisions,
        deterministic_ok=deterministic_ok,
        preview_comparison_ok=preview_comparison_ok or not compare_to_preview,
        semantic_mismatches=semantic_mismatches,
    )
    if ENA_CHECKPOINT_CLOSED_STATEMENT not in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary missing checkpoint-closed statement"
        )
    if str(repo_root.resolve()) in summary_text:
        raise Checkpoint1ApplyError(
            "Resolution summary must not contain absolute repository paths"
        )
    summary_path = output_dir / "ena_checkpoint1_resolution_summary.md"
    _write_text_atomic(summary_path, summary_text)
    _write_text_atomic(
        output_dir / "README.md",
        "CHECKPOINT-1 CLOSED.\n"
        "These files are the authoritative ENA post-review artefacts.\n"
        "They must not overwrite S2, pre-review S3, or dry-run previews.\n"
        "S4 has not started. An ENA global-S4 handoff has not been prepared.\n",
    )
    output_hashes["summary"] = sha256_file(summary_path)

    accepted_dry_run = dict(expected_dry_run_hashes or {})
    metadata = {
        "source": "ena",
        "source_key": "ena",
        "source_dataset": SOURCE_DATASET,
        "checkpoint": "CHECKPOINT-1",
        "review_model": "single_reviewer",
        "checkpoint_status": "closed",
        "checkpoint_closed": True,
        "review_completion_status": "complete",
        "application_status": "applied",
        "s4_started": False,
        "global_s4_handoff_prepared": False,
        "global_s4_run": False,
        "next_stage": "review_ena_closure_before_global_s4_handoff",
        "reviewed_records": int(simulation.stats["record_decisions_consumed"]),
        "record_decisions": record_decisions,
        "technically_eligible": eligible_n,
        "parked_construct_review": int(simulation.stats["parked_construct_review"]),
        "technical_rejects": int(simulation.stats["technical_rejects"]),
        "authorised_for_s4": int(simulation.stats["authorised_for_s4"]),
        "authorised_for_s4_meaning": AUTHORISED_FOR_S4_MEANING,
        "records_trimmed": int(simulation.stats["records_trimmed"]),
        "large_trim_human_approved": int(
            simulation.stats["large_trim_human_approved"]
        ),
        "guard_rail_failures": int(simulation.stats["guard_rail_failures"]),
        "unresolved_after_consumption": 0,
        "review_file_sha256": hashes_before["ena_checkpoint1_manual_review.csv"],
        "review_index_sha256": hashes_before[
            "ena_checkpoint1_manual_review_index.csv"
        ],
        "review_rules_sha256": hashes_before[
            "ena_checkpoint1_constant_rule_review.csv"
        ],
        "review_exceptions_sha256": hashes_before[
            "ena_checkpoint1_constant_exceptions.csv"
        ],
        "review_reconciliation_sha256": hashes_before[
            "ena_checkpoint1_legacy_collapse_reconciliation.csv"
        ],
        "review_reconciliation_index_sha256": hashes_before[
            "ena_checkpoint1_legacy_collapse_reconciliation_index.csv"
        ],
        "review_bulk_sha256": hashes_before[
            "ena_checkpoint1_bulk_audit_confirmation.csv"
        ],
        "frozen_human_review_hashes": {
            name: hashes_before[name]
            for name in review_hash_paths
            if hashes_before.get(name)
        },
        "raw_sha256": hashes_before["raw"],
        "s1_sha256": hashes_before["s1"],
        "sidecar_sha256": hashes_before["sidecar"],
        "s2_sha256": hashes_before["s2"],
        "s3_sha256": hashes_before["s3"],
        "s3_decisions_sha256": hashes_before["s3_decisions"],
        "accepted_dry_run_hashes": accepted_dry_run,
        "accepted_dry_run_parity": preview_comparison_ok or not compare_to_preview,
        "output_hashes": output_hashes,
        "preview_comparison_ok": preview_comparison_ok or not compare_to_preview,
        "semantic_mismatches": semantic_mismatches,
        "byte_identical": byte_identical,
        "deterministic_rerun_ok": deterministic_ok,
        "code_identity": {
            "apply_adapter": "adapters.ena_checkpoint1_apply",
            "dispatcher": "scripts/data_preparation/checkpoint1_apply_review.py",
            "eligibility_policy": "config/source_eligibility/ena.json",
        },
        "closure_only_fields": list(CLOSURE_ONLY_FIELDS),
        "application_mode": "apply",
    }
    _write_json_atomic(metadata_out, metadata)
    output_hashes["metadata"] = sha256_file(metadata_out)

    if check_deterministic_rerun:
        determinism_dir = checkpoint_dir / "closure_validation" / "determinism"
        determinism_dir = _assert_output_dir_allowed(repo_root, determinism_dir)
        third = _simulate()
        verify_paths = _write_ena_transform_csvs(determinism_dir, third)
        for name, path in applied_paths.items():
            if sha256_file(path) != sha256_file(verify_paths[name]):
                raise Checkpoint1ApplyError(
                    f"Deterministic verification mismatch for {name}"
                )

    hashes_after = {
        name: sha256_file(path) if path.is_file() else ""
        for name, path in review_hash_paths.items()
    }
    hashes_after.update(
        {
            "raw": sha256_file(raw_path) if raw_path.is_file() else "",
            "s1": sha256_file(s1_path) if s1_path.is_file() else "",
            "sidecar": sha256_file(sidecar_path),
            "s2": sha256_file(s2_path),
            "s3": sha256_file(canonical_path),
            "s3_decisions": sha256_file(decision_path),
            "qc": sha256_file(qc_path),
            "proposals": sha256_file(proposals_path),
            "membership": (
                sha256_file(membership_path) if membership_path.is_file() else ""
            ),
        }
    )
    if hashes_after != hashes_before:
        raise Checkpoint1ApplyError(
            "CHECKPOINT-1 apply mutated an immutable input artefact"
        )
    if handoff_json.is_file() or handoff_csv.is_file():
        raise Checkpoint1ApplyError(
            "ENA apply must not create a global-S4 source handoff"
        )

    stats = dict(simulation.stats)
    print(
        "source=ena\n"
        "mode=apply\n"
        "checkpoint_status=closed\n"
        f"total_records={stats['total_records']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"parked_construct_review={stats['parked_construct_review']}\n"
        f"technical_rejects={stats['technical_rejects']}\n"
        f"records_trimmed={stats['records_trimmed']}\n"
        f"large_trim_human_approved={stats['large_trim_human_approved']}\n"
        f"guard_rail_failures={stats['guard_rail_failures']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        f"preview_comparison={'pass' if preview_comparison_ok or not compare_to_preview else 'fail'}\n"
        f"semantic_mismatches={semantic_mismatches}\n"
        f"deterministic_rerun={'pass' if deterministic_ok else 'skipped'}\n"
        "CHECKPOINT-1 CLOSED\n"
        "ENA global-S4 handoff has not been prepared\n"
        "S4 has not started"
    )
    return EnaApplyResult(
        output_dir=output_dir,
        metadata_out=metadata_out,
        tracked_manifest=tracked_manifest,
        summary_out=summary_path,
        output_hashes=output_hashes,
        stats=stats,
        preview_comparison_ok=preview_comparison_ok or not compare_to_preview,
        deterministic_rerun_ok=deterministic_ok,
        semantic_mismatches=semantic_mismatches,
        byte_identical=byte_identical,
        checkpoint_closed=True,
    )


def run_ena_checkpoint1_dry_run(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    check_deterministic_rerun: bool = True,
    expected_total_rows: int | None = 679,
    verify_frozen_review: bool = True,
    compare_to_pristine: bool = True,
    skip_pipeline_integrity: bool = False,
    expected_review_hashes: Mapping[str, str] | None = None,
    expected_pipeline_hashes: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Simulate ENA CHECKPOINT-1 application without closing it.

    ``expected_review_hashes`` gates this completed-review instance at
    run time. It is not a source-level ENA pipeline constant.
    """
    from adapters.ena_checkpoint1_apply import (
        CHANGE_REPORT_COLUMNS,
        DRY_RUN_BANNER,
        ELIGIBLE_PREVIEW_COLUMNS,
        GROUP_SUMMARY_COLUMNS,
        GUARD_RAIL_FAILURE_COLUMNS,
        LARGE_TRIM_RECORD_COLUMNS,
        EnaCheckpoint1ApplyError,
        compare_ena_package_to_pristine,
        format_dry_run_markdown,
        load_default_policy,
        serialise_ena_simulation,
        simulate_ena_checkpoint1_application,
    )
    from adapters.ena_checkpoint1_review import (
        read_csv_rows,
        validate_ena_review_package,
    )
    from adapters.ena_s3 import (
        DECISION_COLUMNS,
        PARK_COLUMNS,
        REJECTION_COLUMNS,
        index_constant_proposals,
    )
    from checkpoint1_prepare_review import prepare_ena_checkpoint1_review
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic
    from s3_classify import EXPECTED_ENA_RAW_SHA256, EXPECTED_ENA_S2_HASH

    output_dir = _assert_aptadb_dry_run_output(output_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)
    review_dir = checkpoint_dir / "manual_review"
    queue_path = review_dir / "ena_checkpoint1_manual_review.csv"
    index_path = review_dir / "ena_checkpoint1_manual_review_index.csv"
    rule_path = review_dir / "ena_checkpoint1_constant_rule_review.csv"
    membership_path = review_dir / "ena_checkpoint1_constant_rule_membership.csv"
    exception_path = review_dir / "ena_checkpoint1_constant_exceptions.csv"
    recon_path = review_dir / "ena_checkpoint1_legacy_collapse_reconciliation.csv"
    recon_index_path = (
        review_dir / "ena_checkpoint1_legacy_collapse_reconciliation_index.csv"
    )
    bulk_path = review_dir / "ena_checkpoint1_bulk_audit_confirmation.csv"
    canonical_path = checkpoint_dir / "ena_s3_canonical.csv"
    decision_path = checkpoint_dir / "ena_s3_decisions.csv"
    rejection_path = checkpoint_dir / "rejected_ena.csv"
    parked_path = checkpoint_dir / "ena_s3_parked_construct.csv"
    s1_path = repo_root / "data" / "interim" / "extracted" / "ena_extracted.csv"
    sidecar_path = repo_root / "data" / "interim" / "extracted" / "ena_source_metadata.csv"
    s2_path = repo_root / "data" / "interim" / "normalised" / "ena_normalised.csv"
    qc_path = repo_root / "data" / "interim" / "normalised" / "ena_s2_qc.csv"
    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "ena_constant_region_proposals.csv"
    )
    s2_membership_path = (
        repo_root
        / "data"
        / "interim"
        / "normalised"
        / "ena_constant_region_membership.csv"
    )
    raw_path = (
        repo_root
        / "data"
        / "raw"
        / "ENA"
        / "review_v2"
        / "ena_selected_after_manual_review.csv"
    )

    required = [
        queue_path,
        rule_path,
        exception_path,
        recon_path,
        bulk_path,
        canonical_path,
        decision_path,
        s2_path,
        qc_path,
        sidecar_path,
        proposals_path,
    ]
    for path in required:
        if not path.is_file():
            raise Checkpoint1ApplyError(f"Missing dry-run input: {path.name}")

    review_hash_paths = {
        "ena_checkpoint1_manual_review.csv": queue_path,
        "ena_checkpoint1_manual_review_index.csv": index_path,
        "ena_checkpoint1_constant_rule_review.csv": rule_path,
        "ena_checkpoint1_constant_exceptions.csv": exception_path,
        "ena_checkpoint1_legacy_collapse_reconciliation.csv": recon_path,
        "ena_checkpoint1_legacy_collapse_reconciliation_index.csv": recon_index_path,
        "ena_checkpoint1_bulk_audit_confirmation.csv": bulk_path,
    }
    hashes_before = {
        name: sha256_file(path) if path.is_file() else ""
        for name, path in review_hash_paths.items()
    }
    hashes_before.update(
        {
            "raw": sha256_file(raw_path) if raw_path.is_file() else "",
            "s1": sha256_file(s1_path) if s1_path.is_file() else "",
            "sidecar": sha256_file(sidecar_path),
            "s2": sha256_file(s2_path),
            "s3": sha256_file(canonical_path),
            "s3_decisions": sha256_file(decision_path),
            "qc": sha256_file(qc_path),
            "proposals": sha256_file(proposals_path),
            "membership": (
                sha256_file(membership_path) if membership_path.is_file() else ""
            ),
        }
    )
    if verify_frozen_review:
        if expected_review_hashes is None:
            raise Checkpoint1ApplyError(
                "Frozen ENA review hashes must be supplied as a run-time gate"
            )
        for name, expected in expected_review_hashes.items():
            actual = hashes_before.get(name, "")
            if actual != expected:
                raise Checkpoint1ApplyError(
                    f"Frozen review hash mismatch for {name}"
                )
    if not skip_pipeline_integrity:
        if hashes_before["raw"] and hashes_before["raw"] != EXPECTED_ENA_RAW_SHA256:
            raise Checkpoint1ApplyError("ENA raw SHA-256 does not match freeze")
        if hashes_before["s2"] != EXPECTED_ENA_S2_HASH:
            raise Checkpoint1ApplyError("ENA S2 SHA-256 does not match freeze")
        if hashes_before["s3"] != EXPECTED_ENA_S2_HASH:
            raise Checkpoint1ApplyError("ENA S3 canonical SHA-256 does not match freeze")
        if expected_pipeline_hashes:
            for key, expected in expected_pipeline_hashes.items():
                if hashes_before.get(key, "") != expected:
                    raise Checkpoint1ApplyError(
                        f"ENA {key} SHA-256 does not match freeze"
                    )

    queue_rows = read_csv_rows(queue_path)
    rule_rows = read_csv_rows(rule_path)
    exception_rows = read_csv_rows(exception_path)
    reconciliation_rows = read_csv_rows(recon_path)
    membership_rows = (
        read_csv_rows(membership_path) if membership_path.is_file() else []
    )
    bulk_rows = read_csv_rows(bulk_path)
    bulk = bulk_rows[0] if bulk_rows else None
    try:
        report = validate_ena_review_package(
            queue_rows=queue_rows,
            rule_rows=rule_rows,
            exception_rows=exception_rows,
            reconciliation_rows=reconciliation_rows,
            bulk_confirmation=bulk,
        )
    except Exception as exc:
        raise Checkpoint1ApplyError(str(exc)) from exc
    if not report.ok or report.blocking_issues:
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for dry-run application"
        )
    if (
        expected_total_rows == 679
        and (
            report.total_review_records != 77
            or report.unresolved_manual_decisions != 0
            or report.unresolved_constant_groups != 0
            or report.unresolved_exceptions != 0
            or report.unresolved_reconciliation_groups != 0
            or report.audit_only_unconfirmed != 0
            or report.ready_for_application != 77
        )
    ):
        raise Checkpoint1ApplyError(
            "Fail-closed validator is not ready for dry-run application"
        )

    if compare_to_pristine:
        pristine_dir = output_dir / "pristine_reconstruction"
        if pristine_dir.resolve() == review_dir.resolve():
            raise Checkpoint1ApplyError(
                "Refusing to overwrite the completed human review with pristine"
            )
        prepare_ena_checkpoint1_review(
            repo_root=repo_root,
            checkpoint_dir=checkpoint_dir,
            output_dir=pristine_dir,
            expected_total_rows=expected_total_rows,
        )
        try:
            compare_ena_package_to_pristine(
                reviewed_queue=queue_rows,
                pristine_queue=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_manual_review.csv"
                ),
                reviewed_rules=rule_rows,
                pristine_rules=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_constant_rule_review.csv"
                ),
                reviewed_exceptions=exception_rows,
                pristine_exceptions=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_constant_exceptions.csv"
                ),
                reviewed_reconciliation=reconciliation_rows,
                pristine_reconciliation=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_legacy_collapse_reconciliation.csv"
                ),
                reviewed_bulk=bulk_rows,
                pristine_bulk=read_csv_rows(
                    pristine_dir / "ena_checkpoint1_bulk_audit_confirmation.csv"
                ),
                reviewed_membership=membership_rows,
                pristine_membership=(
                    read_csv_rows(
                        pristine_dir / "ena_checkpoint1_constant_rule_membership.csv"
                    )
                    if (pristine_dir / "ena_checkpoint1_constant_rule_membership.csv").is_file()
                    else []
                ),
            )
        except EnaCheckpoint1ApplyError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    canonical_rows = read_csv_rows(canonical_path)
    decision_rows = read_csv_rows(decision_path)
    rejection_rows = read_csv_rows(rejection_path) if rejection_path.is_file() else []
    parked_rows = read_csv_rows(parked_path) if parked_path.is_file() else []
    qc_rows = read_csv_rows(qc_path)
    sidecar_rows = read_csv_rows(sidecar_path)
    proposal_rows = read_csv_rows(proposals_path)
    s2_membership = (
        read_csv_rows(s2_membership_path) if s2_membership_path.is_file() else []
    )
    qc_by_id = _index_rows(qc_rows)
    sidecar_by_id = _index_rows(sidecar_rows)
    proposals_by_record = index_constant_proposals(
        qc_rows, proposal_rows, s2_membership
    )
    policy = load_default_policy(repo_root)

    def _simulate():
        try:
            return simulate_ena_checkpoint1_application(
                queue_rows=queue_rows,
                rule_rows=rule_rows,
                exception_rows=exception_rows,
                reconciliation_rows=reconciliation_rows,
                canonical_rows=canonical_rows,
                decision_rows=decision_rows,
                source_metadata_by_id=sidecar_by_id,
                s2_qc_by_id=qc_by_id,
                policy=policy,
                membership_rows=membership_rows,
                proposals_by_record=proposals_by_record,
                bulk_confirmation=bulk,
                existing_rejection_rows=rejection_rows,
                existing_parked_construct=parked_rows,
                expected_total_rows=expected_total_rows,
            )
        except EnaCheckpoint1ApplyError as exc:
            raise Checkpoint1ApplyError(str(exc)) from exc

    simulation = _simulate()
    deterministic_ok = False
    if check_deterministic_rerun:
        second = _simulate()
        if serialise_ena_simulation(simulation) != serialise_ena_simulation(second):
            raise Checkpoint1ApplyError(
                "ENA CHECKPOINT-1 dry-run preview was not byte-identical "
                "across deterministic rerun"
            )
        deterministic_ok = True

    output_dir.mkdir(parents=True, exist_ok=True)
    write_corpus_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_canonical_preview.csv",
        simulation.preview_canonical,
        columns=CORPUS_COLUMNS,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_routing_preview.csv",
        DECISION_COLUMNS,
        simulation.preview_decisions,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_rejection_preview.csv",
        REJECTION_COLUMNS,
        simulation.preview_rejections,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_parked_construct_preview.csv",
        PARK_COLUMNS,
        simulation.preview_parked_construct,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_eligible_preview.csv",
        ELIGIBLE_PREVIEW_COLUMNS,
        simulation.preview_eligible,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_change_report.csv",
        CHANGE_REPORT_COLUMNS,
        simulation.change_report,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_group_summary.csv",
        GROUP_SUMMARY_COLUMNS,
        simulation.group_summaries,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_large_trim_human_approved.csv",
        LARGE_TRIM_RECORD_COLUMNS,
        simulation.large_trim_records,
    )
    write_csv_atomic(
        output_dir / "ena_checkpoint1_dry_run_guard_rail_failures.csv",
        GUARD_RAIL_FAILURE_COLUMNS,
        simulation.guard_rail_failure_rows,
    )
    review_hashes = {
        name: hashes_before[name]
        for name in review_hash_paths
        if hashes_before.get(name)
    }
    integrity = {
        "raw": hashes_before["raw"],
        "s1": hashes_before["s1"],
        "sidecar": hashes_before["sidecar"],
        "s2": hashes_before["s2"],
        "s3": hashes_before["s3"],
        "s3_decisions": hashes_before["s3_decisions"],
        "deterministic_ok": "true" if deterministic_ok else "false",
    }
    report_text = format_dry_run_markdown(
        simulation, review_hashes=review_hashes, integrity=integrity
    )
    _write_text_atomic(
        output_dir / "ena_checkpoint1_dry_run_report.md", report_text
    )
    _write_text_atomic(
        output_dir / "README.md",
        DRY_RUN_BANNER
        + "\n\nThese files are application previews only. They must not be "
        "treated as resolved CHECKPOINT-1 outputs or an S4 handoff.\n",
    )

    hashes_after = {
        name: sha256_file(path) if path.is_file() else ""
        for name, path in review_hash_paths.items()
    }
    hashes_after.update(
        {
            "raw": sha256_file(raw_path) if raw_path.is_file() else "",
            "s1": sha256_file(s1_path) if s1_path.is_file() else "",
            "sidecar": sha256_file(sidecar_path),
            "s2": sha256_file(s2_path),
            "s3": sha256_file(canonical_path),
            "s3_decisions": sha256_file(decision_path),
            "qc": sha256_file(qc_path),
            "proposals": sha256_file(proposals_path),
            "membership": (
                sha256_file(membership_path) if membership_path.is_file() else ""
            ),
        }
    )
    if hashes_after != hashes_before:
        raise Checkpoint1ApplyError(
            "Dry-run mutated an input artefact; aborting without treating "
            "preview files as authoritative"
        )

    output_hash_names = [
        "ena_checkpoint1_dry_run_canonical_preview.csv",
        "ena_checkpoint1_dry_run_routing_preview.csv",
        "ena_checkpoint1_dry_run_rejection_preview.csv",
        "ena_checkpoint1_dry_run_parked_construct_preview.csv",
        "ena_checkpoint1_dry_run_eligible_preview.csv",
        "ena_checkpoint1_dry_run_change_report.csv",
        "ena_checkpoint1_dry_run_group_summary.csv",
        "ena_checkpoint1_dry_run_large_trim_human_approved.csv",
        "ena_checkpoint1_dry_run_guard_rail_failures.csv",
        "ena_checkpoint1_dry_run_report.md",
    ]
    output_hashes = {
        name: sha256_file(output_dir / name)
        for name in output_hash_names
        if (output_dir / name).is_file()
    }
    hash_lines = [
        "# ENA CHECKPOINT-1 dry-run output hashes (apply-parity reference)",
        "",
        DRY_RUN_BANNER,
        "",
    ]
    for name, digest in output_hashes.items():
        hash_lines.append(f"- `{name}`: `{digest}`")
    _write_text_atomic(
        output_dir / "ena_checkpoint1_dry_run_output_hashes.md",
        "\n".join(hash_lines) + "\n",
    )

    stats = simulation.stats
    if int(stats.get("guard_rail_failures") or 0) != 0:
        raise Checkpoint1ApplyError("Dry-run guard-rail failures are forbidden")
    print(
        "source=ena\n"
        "mode=dry_run\n"
        "checkpoint_status=unapplied\n"
        f"total_records={stats['total_records']}\n"
        f"technically_eligible={stats['technically_eligible']}\n"
        f"parked_construct_review={stats['parked_construct_review']}\n"
        f"technical_rejects={stats['technical_rejects']}\n"
        f"records_trimmed={stats['records_trimmed']}\n"
        f"large_trim_human_approved={stats['large_trim_human_approved']}\n"
        f"guard_rail_failures={stats['guard_rail_failures']}\n"
        f"authorised_for_s4={stats['authorised_for_s4']}\n"
        f"deterministic_rerun={'pass' if deterministic_ok else 'skipped'}\n"
        "CHECKPOINT-1 is not closed\n"
        "S4 remains blocked"
    )
    return output_hashes


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.source not in {
            "aptabase",
            "utexas",
            "aptadb",
            "riboaptamer",
            "aptaindex",
            "ena",
        }:
            raise Checkpoint1ApplyError(
                f"Unsupported source_key={args.source!r}; "
                "supported: aptabase, utexas, aptadb, riboaptamer, aptaindex, ena"
            )
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise Checkpoint1ApplyError(f"Repository root does not exist: {repo_root}")

        if args.source == "ena":
            checkpoint_dir = (
                args.checkpoint_dir
                if args.checkpoint_dir is not None
                else Path("data/interim/checkpoints/ena_cp1")
            )
            if not Path(checkpoint_dir).is_absolute():
                checkpoint_dir = repo_root / checkpoint_dir
            # Run-time gate for this completed-review instance only. Not a
            # source-level ENA constant and not copied into adapters/ena.py.
            expected_total = (
                679
                if args.expected_total_rows is None
                else args.expected_total_rows
            )
            if args.dry_run:
                output_dir = (
                    args.output_dir
                    if args.output_dir is not None
                    else Path(checkpoint_dir) / "dry_run"
                )
                if not Path(output_dir).is_absolute():
                    output_dir = repo_root / output_dir
                run_ena_checkpoint1_dry_run(
                    repo_root=repo_root,
                    checkpoint_dir=Path(checkpoint_dir),
                    output_dir=Path(output_dir),
                    check_deterministic_rerun=not args.skip_deterministic_rerun,
                    expected_total_rows=expected_total,
                    verify_frozen_review=not args.skip_pipeline_integrity,
                    compare_to_pristine=not args.skip_pipeline_integrity,
                    skip_pipeline_integrity=args.skip_pipeline_integrity,
                    expected_review_hashes=(
                        None
                        if args.skip_pipeline_integrity
                        else FROZEN_ENA_REVIEW_HASHES
                    ),
                    expected_pipeline_hashes=(
                        None
                        if args.skip_pipeline_integrity
                        else FROZEN_ENA_PIPELINE_HASHES
                    ),
                )
                return 0
            output_dir = (
                args.output_dir
                if args.output_dir is not None
                else Path(checkpoint_dir) / "resolved"
            )
            if not Path(output_dir).is_absolute():
                output_dir = repo_root / output_dir
            tracked_manifest = (
                args.tracked_manifest
                if args.tracked_manifest is not None
                else Path(
                    "config/checkpoint_reviews/ena_checkpoint1_resolutions.csv"
                )
            )
            metadata_out = (
                args.metadata_out
                if args.metadata_out is not None
                else Path(
                    "config/checkpoint_reviews/ena_checkpoint1_metadata.json"
                )
            )
            run_ena_checkpoint1_apply(
                repo_root=repo_root,
                checkpoint_dir=Path(checkpoint_dir),
                output_dir=Path(output_dir),
                tracked_manifest=tracked_manifest,
                metadata_out=metadata_out,
                check_deterministic_rerun=not args.skip_deterministic_rerun,
                expected_total_rows=expected_total,
                verify_frozen_review=not args.skip_pipeline_integrity,
                compare_to_pristine=not args.skip_pipeline_integrity,
                skip_pipeline_integrity=args.skip_pipeline_integrity,
                expected_review_hashes=(
                    None
                    if args.skip_pipeline_integrity
                    else FROZEN_ENA_REVIEW_HASHES
                ),
                expected_pipeline_hashes=(
                    None
                    if args.skip_pipeline_integrity
                    else FROZEN_ENA_PIPELINE_HASHES
                ),
                expected_dry_run_hashes=(
                    None
                    if args.skip_pipeline_integrity
                    else ACCEPTED_ENA_DRY_RUN_HASHES
                ),
            )
            return 0
        if args.source == "aptadb":
            checkpoint_dir = (
                args.checkpoint_dir
                if args.checkpoint_dir is not None
                else Path("data/interim/checkpoints/aptadb_cp1")
            )
            if not Path(checkpoint_dir).is_absolute():
                checkpoint_dir = repo_root / checkpoint_dir
            if args.dry_run:
                output_dir = (
                    args.output_dir
                    if args.output_dir is not None
                    else Path(checkpoint_dir) / "dry_run"
                )
                if not Path(output_dir).is_absolute():
                    output_dir = repo_root / output_dir
                run_aptadb_checkpoint1_dry_run(
                    repo_root=repo_root,
                    checkpoint_dir=Path(checkpoint_dir),
                    output_dir=Path(output_dir),
                    check_deterministic_rerun=not args.skip_deterministic_rerun,
                )
                return 0
            output_dir = (
                args.output_dir
                if args.output_dir is not None
                else Path(checkpoint_dir) / "resolved"
            )
            if not Path(output_dir).is_absolute():
                output_dir = repo_root / output_dir
            tracked_manifest = (
                args.tracked_manifest
                if args.tracked_manifest is not None
                else Path(
                    "config/checkpoint_reviews/aptadb_checkpoint1_resolutions.csv"
                )
            )
            metadata_out = (
                args.metadata_out
                if args.metadata_out is not None
                else Path(
                    "config/checkpoint_reviews/aptadb_checkpoint1_metadata.json"
                )
            )
            run_aptadb_checkpoint1_apply(
                repo_root=repo_root,
                checkpoint_dir=Path(checkpoint_dir),
                output_dir=Path(output_dir),
                tracked_manifest=tracked_manifest,
                metadata_out=metadata_out,
                check_deterministic_rerun=not args.skip_deterministic_rerun,
            )
            return 0
        if args.source == "aptaindex":
            checkpoint_dir = (
                args.checkpoint_dir
                if args.checkpoint_dir is not None
                else Path("data/interim/checkpoints/aptaindex_cp1")
            )
            if not Path(checkpoint_dir).is_absolute():
                checkpoint_dir = repo_root / checkpoint_dir
            if args.dry_run:
                output_dir = (
                    args.output_dir
                    if args.output_dir is not None
                    else Path(checkpoint_dir) / "dry_run"
                )
                if not Path(output_dir).is_absolute():
                    output_dir = repo_root / output_dir
                run_aptaindex_checkpoint1_dry_run(
                    repo_root=repo_root,
                    checkpoint_dir=Path(checkpoint_dir),
                    output_dir=Path(output_dir),
                    check_deterministic_rerun=not args.skip_deterministic_rerun,
                )
                return 0
            output_dir = (
                args.output_dir
                if args.output_dir is not None
                else Path(checkpoint_dir) / "resolved"
            )
            if not Path(output_dir).is_absolute():
                output_dir = repo_root / output_dir
            tracked_manifest = (
                args.tracked_manifest
                if args.tracked_manifest is not None
                else Path(
                    "config/checkpoint_reviews/aptaindex_checkpoint1_resolutions.csv"
                )
            )
            metadata_out = (
                args.metadata_out
                if args.metadata_out is not None
                else Path(
                    "config/checkpoint_reviews/aptaindex_checkpoint1_metadata.json"
                )
            )
            run_aptaindex_checkpoint1_apply(
                repo_root=repo_root,
                checkpoint_dir=Path(checkpoint_dir),
                output_dir=Path(output_dir),
                tracked_manifest=tracked_manifest,
                metadata_out=metadata_out,
                check_deterministic_rerun=not args.skip_deterministic_rerun,
            )
            return 0
        if args.source == "riboaptamer":
            checkpoint_dir = (
                args.checkpoint_dir
                if args.checkpoint_dir is not None
                else Path("data/interim/checkpoints/riboaptamer_cp1")
            )
            output_dir = (
                args.output_dir
                if args.output_dir is not None
                else Path(checkpoint_dir) / ("dry_run" if args.dry_run else "resolved")
            )
            run_riboaptamer_checkpoint1_apply(
                repo_root=repo_root,
                checkpoint_dir=Path(checkpoint_dir),
                output_dir=Path(output_dir),
                dry_run=args.dry_run,
            )
            return 0
        if args.source == "utexas":
            checkpoint_dir = (
                args.checkpoint_dir
                if args.checkpoint_dir is not None
                else Path("data/interim/checkpoints/utexas_cp1")
            )
            review_file = (
                args.review_file
                if args.review_file is not None
                else Path(checkpoint_dir)
                / "manual_review"
                / "utexas_checkpoint1_manual_review.csv"
            )
            output_dir = (
                args.output_dir
                if args.output_dir is not None
                else Path(checkpoint_dir) / "resolved"
            )
            tracked_manifest = (
                args.tracked_manifest
                if args.tracked_manifest is not None
                else Path(
                    "config/checkpoint_reviews/utexas_checkpoint1_resolutions.csv"
                )
            )
            metadata_out = (
                args.metadata_out
                if args.metadata_out is not None
                else Path("config/checkpoint_reviews/utexas_checkpoint1_metadata.json")
            )
            pristine_dir = (
                args.pristine_dir
                if args.pristine_dir is not None
                else Path(checkpoint_dir) / "closure_validation" / "pristine"
            )
            result = apply_utexas_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                review_file=review_file,
                output_dir=output_dir,
                tracked_manifest=tracked_manifest,
                metadata_out=metadata_out,
                alphabet_resolutions_path=Path(
                    "config/checkpoint_reviews/utexas_alphabet_exception_resolutions.csv"
                ),
                pristine_dir=pristine_dir,
                expected_total_rows=(
                    UTEXAS_EXPECTED_TOTAL_ROWS
                    if args.expected_total_rows is None
                    else args.expected_total_rows
                ),
                verify_pipeline_integrity=not args.skip_pipeline_integrity,
                check_deterministic_rerun=True,
            )
        else:
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
