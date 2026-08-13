#!/usr/bin/env python3
"""Prepare the AptaBase CHECKPOINT-1 manual-review package.

Consumes sequence-free review and sequence-bearing local-detail CHECKPOINT-1
artefacts. Emits an active review queue for rows with
``manual_review_required=true``. Does not approve the checkpoint, alter
proposed decisions, or authorise any record for S4.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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

from s0_build_registry import find_repo_root  # noqa: E402
from adapters.utexas_s3 import (  # noqa: E402
    DEFAULT_UTEXAS_BATCHES,
    LOCAL_DETAIL_COLUMNS as UTEXAS_LOCAL_DETAIL_COLUMNS,
)

EXPECTED_ACTIVE_ROWS = 431
EXPECTED_TOTAL_ROWS = 610
EXPECTED_NO_REVIEW_ROWS = 179

PIPELINE_STOP_STATEMENT = (
    "PIPELINE STOP: AptaBase CHECKPOINT-1 remains pending manual review.\n"
    "No record is authorised to proceed to S4."
)

PERMITTED_REVIEW_ACTIONS: tuple[str, ...] = (
    "confirm_current",
    "override_to_accept",
    "override_to_park",
    "override_to_reject",
    "needs_source_review",
)

BATCH_ORDER: tuple[str, ...] = (
    "01_reject_review",
    "02_accept_with_diagnostics",
    "03_park_unresolved_molecule",
    "04_park_ssdna",
    "05_park_invalid_sequence",
    "06_park_overlength",
    "07_park_mixed_t_u",
    "08_park_trim_construct",
    "09_park_ambiguous",
)

EXPECTED_BATCH_COUNTS: Mapping[str, int] = {
    "01_reject_review": 40,
    "02_accept_with_diagnostics": 48,
    "03_park_unresolved_molecule": 227,
    "04_park_ssdna": 41,
    "05_park_invalid_sequence": 36,
    "06_park_overlength": 34,
    "07_park_mixed_t_u": 3,
    "08_park_trim_construct": 1,
    "09_park_ambiguous": 1,
}

UTEXAS_EXPECTED_TOTAL_ROWS = 1894
UTEXAS_BATCH_ORDER: tuple[str, ...] = DEFAULT_UTEXAS_BATCHES
UTEXAS_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No record authorised for S4 yet."
)

UTEXAS_MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    "review_batch",
    "review_order",
    "record_id",
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "publication",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_priority",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "chemistry",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "qc_flags",
    "review_action",
    "reviewer_note",
    "reviewer_initials",
)

UTEXAS_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
)

UTEXAS_INDEX_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in UTEXAS_MANUAL_REVIEW_COLUMNS
    if column not in UTEXAS_SEQUENCE_COLUMNS
)

UTEXAS_LOCAL_DETAIL_JOIN_FIELDS: tuple[str, ...] = (
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "publication",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_priority",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "chemistry",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "qc_flags",
)

PRIORITY_ORDER: tuple[str, ...] = ("high", "medium", "low", "none")

MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    "review_batch",
    "review_order",
    "record_id",
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "target_general_raw",
    "target_specific_raw",
    "publication",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_priority",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "detected_constant_5p",
    "detected_constant_3p",
    "source_record_validity",
    "source_parse_warnings",
    "reported_length_raw",
    "reported_length_difference",
    "gc_reported_raw",
    "gc_calculated_s2",
    "gc_difference_percentage_points",
    "sequence_leakage_match",
    "target_leakage_match",
    "qc_flags",
    "review_action",
    "reviewer_note",
    "reviewer_initials",
)

SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
)

INDEX_COLUMNS: tuple[str, ...] = tuple(
    column for column in MANUAL_REVIEW_COLUMNS if column not in SEQUENCE_COLUMNS
)

LOCAL_DETAIL_JOIN_FIELDS: tuple[str, ...] = (
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "target_general_raw",
    "target_specific_raw",
    "publication",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_priority",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "detected_constant_5p",
    "detected_constant_3p",
    "source_record_validity",
    "source_parse_warnings",
    "reported_length_raw",
    "reported_length_difference",
    "gc_reported_raw",
    "gc_calculated_s2",
    "gc_difference_percentage_points",
    "sequence_leakage_match",
    "target_leakage_match",
    "qc_flags",
)


class Checkpoint1ReviewError(ValueError):
    """Hard failure while preparing the CHECKPOINT-1 review package."""


@dataclass
class ReviewPackageStats:
    """Aggregate-only counts for the manual-review package."""

    total_checkpoint_records: int = 0
    active_review_rows: int = 0
    no_review_records: int = 0
    batch_counts: dict[str, int] = field(default_factory=dict)
    decision_counts: dict[str, int] = field(default_factory=dict)
    primary_reason_counts: dict[str, int] = field(default_factory=dict)
    priority_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewPackageResult:
    """Paths and aggregates from one review-package preparation run."""

    source_key: str
    stats: ReviewPackageStats
    output_queue: Path
    output_index: Path
    output_summary: Path
    review_hash_before: str
    review_hash_after: str
    local_detail_hash_before: str
    local_detail_hash_after: str
    inputs_unchanged: bool


def assert_no_legacy_cleaner_import() -> None:
    """Hard-fail if the legacy AptaBase cleaner module is imported."""
    forbidden = {
        "aptabase_cleaning",
        "scripts.data_preparation.aptabase_cleaning",
    }
    for name in forbidden:
        if name in sys.modules:
            raise Checkpoint1ReviewError(
                "legacy AptaBase cleaner must not be imported by review prep"
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_under_repo(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _assert_output_dir_allowed(repo_root: Path, output_dir: Path) -> Path:
    resolved = _resolve_under_repo(repo_root, output_dir)
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise Checkpoint1ReviewError(
            "Review output directory must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise Checkpoint1ReviewError(
            f"Refusing to write review outputs under data/raw/: {output_dir}"
        )
    return resolved


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def write_csv_atomic(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    """Atomically write a CSV with Unix newlines and a trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in fieldnames})
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


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


def _read_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise Checkpoint1ReviewError(f"{label} CSV has no header: {path.name}")
        if "record_id" not in reader.fieldnames:
            raise Checkpoint1ReviewError(f"{label} CSV missing record_id")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        if not (row.get("record_id") or "").strip():
            raise Checkpoint1ReviewError(f"{label} row {index} has blank record_id")
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def assign_review_batch(row: Mapping[str, str]) -> str:
    """Assign exactly one deterministic review batch to an active review row."""
    decision = row.get("proposed_decision", "")
    primary = row.get("primary_reason", "")

    matches: list[str] = []
    if decision == "proposed_reject" and primary != "missing_sequence":
        matches.append("01_reject_review")
    if decision == "proposed_accept":
        matches.append("02_accept_with_diagnostics")
    if primary == "molecule_type_unresolved":
        matches.append("03_park_unresolved_molecule")
    if primary == "ssdna_not_eligible_for_rna_training":
        matches.append("04_park_ssdna")
    if primary == "invalid_sequence_requires_review":
        matches.append("05_park_invalid_sequence")
    if primary == "core_above_maximum_requires_review":
        matches.append("06_park_overlength")
    if primary == "mixed_t_u_requires_review":
        matches.append("07_park_mixed_t_u")
    if primary == "trim_or_construct_requires_review":
        matches.append("08_park_trim_construct")
    if primary == "ambiguous_sequence_requires_review":
        matches.append("09_park_ambiguous")

    if len(matches) == 0:
        raise Checkpoint1ReviewError(
            "Review-required record belongs to no batch: "
            f"record_id={row.get('record_id')!r} "
            f"decision={decision!r} primary={primary!r}"
        )
    if len(matches) > 1:
        raise Checkpoint1ReviewError(
            "Review-required record matches multiple batches: "
            f"record_id={row.get('record_id')!r} batches={matches}"
        )
    return matches[0]


def _priority_rank(priority: str) -> int:
    try:
        return PRIORITY_ORDER.index(priority)
    except ValueError:
        return len(PRIORITY_ORDER)


def _batch_rank(batch: str) -> int:
    try:
        return BATCH_ORDER.index(batch)
    except ValueError:
        return len(BATCH_ORDER)


def review_package_sort_key(row: Mapping[str, str]) -> tuple[int, int, str, str]:
    """Sort by batch, priority, primary reason, then record ID."""
    return (
        _batch_rank(row.get("review_batch", "")),
        _priority_rank(row.get("manual_review_priority", "none")),
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )


def _join_review_and_local_detail(
    review_rows: Sequence[Mapping[str, str]],
    local_detail_rows: Sequence[Mapping[str, str]],
) -> list[tuple[dict[str, str], dict[str, str]]]:
    """One-to-one join by record_id; hard-fail on mismatch."""
    if len(review_rows) != len(local_detail_rows):
        raise Checkpoint1ReviewError(
            "Checkpoint review and local-detail row counts must match: "
            f"{len(review_rows)} vs {len(local_detail_rows)}"
        )

    detail_by_id: dict[str, dict[str, str]] = {}
    for row in local_detail_rows:
        record_id = row["record_id"]
        if record_id in detail_by_id:
            raise Checkpoint1ReviewError(
                f"Duplicate local-detail record_id: {record_id!r}"
            )
        detail_by_id[record_id] = dict(row)

    review_ids: set[str] = set()
    paired: list[tuple[dict[str, str], dict[str, str]]] = []
    for review in review_rows:
        record_id = review["record_id"]
        if record_id in review_ids:
            raise Checkpoint1ReviewError(
                f"Duplicate checkpoint-review record_id: {record_id!r}"
            )
        review_ids.add(record_id)
        if record_id not in detail_by_id:
            raise Checkpoint1ReviewError(
                f"Missing local-detail row for record_id={record_id!r}"
            )
        paired.append((dict(review), detail_by_id[record_id]))

    extra = set(detail_by_id) - review_ids
    if extra:
        raise Checkpoint1ReviewError(
            f"Extra local-detail record_id values not in review: {len(extra)}"
        )
    return paired


def build_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one sequence-bearing active-review row with empty reviewer fields."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")

    # Decision fields must reconcile between sequence-free review and local detail.
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )

    row = {column: "" for column in MANUAL_REVIEW_COLUMNS}
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for field_name in LOCAL_DETAIL_JOIN_FIELDS:
        row[field_name] = local_detail.get(field_name, "")
    # Reviewer fields remain empty until manual completion.
    row["review_action"] = ""
    row["reviewer_note"] = ""
    row["reviewer_initials"] = ""
    return row


def build_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    """Copy a queue row into the sequence-free index schema."""
    return {column: queue_row.get(column, "") for column in INDEX_COLUMNS}


def build_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
) -> str:
    """Build an aggregate-only Markdown summary (no sequences or record IDs)."""
    stats = result.stats
    lines = [
        "# AptaBase CHECKPOINT-1 manual-review package",
        "",
        "## Totals",
        "",
        f"- Total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- Active review rows: `{stats.active_review_rows}`",
        f"- No-review records: `{stats.no_review_records}`",
        f"- Review actions recorded: `0`",
        "",
        "## Counts by review batch",
        "",
    ]
    for batch in BATCH_ORDER:
        count = stats.batch_counts.get(batch, 0)
        lines.append(f"- `{batch}`: `{count}`")

    lines.extend(["", "## Counts by proposed decision", ""])
    for name, count in sorted(stats.decision_counts.items()):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Counts by primary reason", ""])
    for name, count in sorted(stats.primary_reason_counts.items()):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Counts by review priority", ""])
    for name in PRIORITY_ORDER:
        if name in stats.priority_counts:
            lines.append(f"- `{name}`: `{stats.priority_counts[name]}`")
    for name, count in sorted(stats.priority_counts.items()):
        if name not in PRIORITY_ORDER:
            lines.append(f"- `{name}`: `{count}`")

    lines.extend(
        [
            "",
            "## Permitted reviewer actions",
            "",
        ]
    )
    for action in PERMITTED_REVIEW_ACTIONS:
        lines.append(f"- `{action}`")

    lines.extend(
        [
            "",
            "## Completion requirements",
            "",
            "- `review_action` must be nonempty for every active row.",
            "- `reviewer_note` must be nonempty for any override or "
            "`needs_source_review` action.",
            "- `confirm_current` does not require a reviewer note.",
            "- No review action has yet been recorded.",
            "",
            "## Outputs",
            "",
            f"- Sequence-bearing review queue: "
            f"`{_relative_display(result.output_queue, repo_root)}`",
            f"- Sequence-free review index: "
            f"`{_relative_display(result.output_index, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local sequence warning",
            "",
            "WARNING: `aptabase_checkpoint1_manual_review.csv` contains source "
            "and canonical sequences for manual scientific review. It must "
            "remain beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def prepare_aptabase_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = EXPECTED_ACTIVE_ROWS,
    expected_total_rows: int | None = EXPECTED_TOTAL_ROWS,
    enforce_expected_batch_counts: bool = True,
) -> ReviewPackageResult:
    """Build the AptaBase CHECKPOINT-1 active manual-review package."""
    assert_no_legacy_cleaner_import()
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "aptabase_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "aptabase_checkpoint1_local_detail.csv"
    for path, label in (
        (review_path, "checkpoint review"),
        (local_detail_path, "local-detail"),
    ):
        if not path.is_file():
            raise Checkpoint1ReviewError(f"Missing {label} input: {path.name}")

    review_hash_before = _sha256_file(review_path)
    local_detail_hash_before = _sha256_file(local_detail_path)

    review_rows = _read_csv(review_path, label="checkpoint review")
    local_detail_rows = _read_csv(local_detail_path, label="local-detail")
    paired = _join_review_and_local_detail(review_rows, local_detail_rows)

    if expected_total_rows is not None and len(paired) != expected_total_rows:
        raise Checkpoint1ReviewError(
            f"Checkpoint row count must be {expected_total_rows}; got {len(paired)}"
        )

    stats = ReviewPackageStats()
    stats.total_checkpoint_records = len(paired)

    active_pairs: list[tuple[dict[str, str], dict[str, str], str]] = []
    for review_row, detail_row in paired:
        required = (review_row.get("manual_review_required") or "").strip()
        if required not in {"true", "false"}:
            raise Checkpoint1ReviewError(
                "manual_review_required must be lowercase true/false; "
                f"got {required!r} for {review_row['record_id']!r}"
            )
        if required == "false":
            stats.no_review_records += 1
            continue
        if (
            review_row.get("proposed_decision") == "proposed_reject"
            and review_row.get("primary_reason") == "missing_sequence"
        ):
            raise Checkpoint1ReviewError(
                "Missing-sequence reject must not enter the active review queue: "
                f"{review_row['record_id']!r}"
            )
        batch = assign_review_batch(review_row)
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )
    if (
        expected_total_rows == EXPECTED_TOTAL_ROWS
        and stats.no_review_records != EXPECTED_NO_REVIEW_ROWS
    ):
        raise Checkpoint1ReviewError(
            f"No-review count must be {EXPECTED_NO_REVIEW_ROWS}; "
            f"got {stats.no_review_records}"
        )

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        draft = build_manual_review_row(
            review_row=review_row,
            local_detail=detail_row,
            review_batch=batch,
            review_order=0,
        )
        draft_rows.append(draft)

    draft_rows.sort(key=review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if ordered["review_action"] or ordered["reviewer_note"] or ordered[
            "reviewer_initials"
        ]:
            raise Checkpoint1ReviewError(
                "Reviewer fields must be empty in the prepared package"
            )
        queue_rows.append(ordered)
        batch = ordered["review_batch"]
        stats.batch_counts[batch] = stats.batch_counts.get(batch, 0) + 1
        decision = ordered["proposed_decision"]
        stats.decision_counts[decision] = stats.decision_counts.get(decision, 0) + 1
        primary = ordered["primary_reason"]
        stats.primary_reason_counts[primary] = (
            stats.primary_reason_counts.get(primary, 0) + 1
        )
        priority = ordered["manual_review_priority"]
        stats.priority_counts[priority] = stats.priority_counts.get(priority, 0) + 1

    stats.active_review_rows = len(queue_rows)
    if len({row["record_id"] for row in queue_rows}) != len(queue_rows):
        raise Checkpoint1ReviewError("Active review queue has duplicate record_id")

    if enforce_expected_batch_counts and expected_active_rows == EXPECTED_ACTIVE_ROWS:
        for batch, expected in EXPECTED_BATCH_COUNTS.items():
            got = stats.batch_counts.get(batch, 0)
            if got != expected:
                raise Checkpoint1ReviewError(
                    f"Batch {batch} count must be {expected}; got {got}"
                )
        if sum(stats.batch_counts.values()) != EXPECTED_ACTIVE_ROWS:
            raise Checkpoint1ReviewError("Batch counts do not reconcile to 431")

    index_rows = [build_index_row(row) for row in queue_rows]
    if any(column in INDEX_COLUMNS for column in SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")
    for column in SEQUENCE_COLUMNS:
        if column not in MANUAL_REVIEW_COLUMNS:
            raise Checkpoint1ReviewError(
                f"Queue schema missing sequence column {column!r}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "aptabase_checkpoint1_manual_review.csv"
    out_index = output_dir / "aptabase_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "aptabase_checkpoint1_manual_review_summary.md"

    write_csv_atomic(out_queue, MANUAL_REVIEW_COLUMNS, queue_rows)
    write_csv_atomic(out_index, INDEX_COLUMNS, index_rows)

    review_hash_after = _sha256_file(review_path)
    local_detail_hash_after = _sha256_file(local_detail_path)
    inputs_unchanged = (
        review_hash_before == review_hash_after
        and local_detail_hash_before == local_detail_hash_after
    )
    if not inputs_unchanged:
        raise Checkpoint1ReviewError(
            "CHECKPOINT-1 inputs were modified during review-package preparation"
        )

    result = ReviewPackageResult(
        source_key="aptabase",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
    )
    summary_text = build_review_summary(repo_root=repo_root, result=result)
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    if PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No review action has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no review action has been recorded"
        )
    _write_text_atomic(out_summary, summary_text)
    return result


def build_utexas_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one UTexas sequence-bearing active-review row."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )
    row = {column: "" for column in UTEXAS_MANUAL_REVIEW_COLUMNS}
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for field_name in UTEXAS_LOCAL_DETAIL_JOIN_FIELDS:
        row[field_name] = local_detail.get(field_name, "")
    row["review_action"] = ""
    row["reviewer_note"] = ""
    row["reviewer_initials"] = ""
    return row


def build_utexas_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    return {column: queue_row.get(column, "") for column in UTEXAS_INDEX_COLUMNS}


def utexas_review_package_sort_key(
    row: Mapping[str, str],
) -> tuple[int, int, str, str]:
    batch = row.get("review_batch", "")
    try:
        batch_rank = UTEXAS_BATCH_ORDER.index(batch)
    except ValueError:
        batch_rank = len(UTEXAS_BATCH_ORDER)
    return (
        batch_rank,
        _priority_rank(row.get("manual_review_priority", "none")),
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )


def build_utexas_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
) -> str:
    stats = result.stats
    lines = [
        "# UTexas CHECKPOINT-1 manual-review package",
        "",
        "## Totals",
        "",
        f"- Total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- Active review rows: `{stats.active_review_rows}`",
        f"- No-review records: `{stats.no_review_records}`",
        f"- Review actions recorded: `0`",
        "",
        "## Review model",
        "",
        "- `review_model` = `single_reviewer`",
        "- `reviewer_initials_required` = `false`",
        "- `reviewer_notes_required` = `false`",
        "",
        "## Counts by review batch",
        "",
    ]
    for batch in UTEXAS_BATCH_ORDER:
        count = stats.batch_counts.get(batch, 0)
        lines.append(f"- `{batch}`: `{count}`")

    lines.extend(["", "## Counts by proposed decision", ""])
    for name, count in sorted(stats.decision_counts.items()):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Counts by primary reason", ""])
    for name, count in sorted(stats.primary_reason_counts.items()):
        lines.append(f"- `{name}`: `{count}`")

    lines.extend(["", "## Counts by review priority", ""])
    for name in PRIORITY_ORDER:
        if name in stats.priority_counts:
            lines.append(f"- `{name}`: `{stats.priority_counts[name]}`")

    lines.extend(
        [
            "",
            "## Permitted reviewer actions",
            "",
        ]
    )
    for action in PERMITTED_REVIEW_ACTIONS:
        lines.append(f"- `{action}`")

    lines.extend(
        [
            "",
            "## Completion requirements",
            "",
            "- `review_action` must be nonempty for every active row.",
            "- `reviewer_note` and `reviewer_initials` may remain blank.",
            "- No review action has yet been recorded.",
            "- Do not infer target type or score evidence during this review.",
            "",
            "## Outputs",
            "",
            f"- Sequence-bearing review queue: "
            f"`{_relative_display(result.output_queue, repo_root)}`",
            f"- Sequence-free review index: "
            f"`{_relative_display(result.output_index, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local sequence warning",
            "",
            "WARNING: `utexas_checkpoint1_manual_review.csv` contains source "
            "and canonical sequences for manual scientific review. It must "
            "remain beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            UTEXAS_PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def prepare_utexas_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = None,
    expected_total_rows: int | None = UTEXAS_EXPECTED_TOTAL_ROWS,
) -> ReviewPackageResult:
    """Build the UTexas CHECKPOINT-1 active manual-review package."""
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "utexas_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "utexas_checkpoint1_local_detail.csv"
    for path, label in (
        (review_path, "checkpoint review"),
        (local_detail_path, "local-detail"),
    ):
        if not path.is_file():
            raise Checkpoint1ReviewError(f"Missing {label} input: {path.name}")

    review_hash_before = _sha256_file(review_path)
    local_detail_hash_before = _sha256_file(local_detail_path)

    review_rows = _read_csv(review_path, label="checkpoint review")
    local_detail_rows = _read_csv(local_detail_path, label="local-detail")
    paired = _join_review_and_local_detail(review_rows, local_detail_rows)

    if expected_total_rows is not None and len(paired) != expected_total_rows:
        raise Checkpoint1ReviewError(
            f"Checkpoint row count must be {expected_total_rows}; got {len(paired)}"
        )

    stats = ReviewPackageStats()
    stats.total_checkpoint_records = len(paired)

    active_pairs: list[tuple[dict[str, str], dict[str, str], str]] = []
    for review_row, detail_row in paired:
        required = (review_row.get("manual_review_required") or "").strip()
        if required not in {"true", "false"}:
            raise Checkpoint1ReviewError(
                "manual_review_required must be lowercase true/false; "
                f"got {required!r} for {review_row['record_id']!r}"
            )
        if required == "false":
            stats.no_review_records += 1
            if review_row.get("review_batch"):
                raise Checkpoint1ReviewError(
                    "No-review UTexas row must not carry review_batch: "
                    f"{review_row['record_id']!r}"
                )
            continue
        if (
            review_row.get("proposed_decision") == "proposed_reject"
            and review_row.get("primary_reason") == "missing_sequence"
        ):
            raise Checkpoint1ReviewError(
                "Missing-sequence reject must not enter the active review queue: "
                f"{review_row['record_id']!r}"
            )
        if (
            review_row.get("primary_reason") == "non_rna_molecule"
            and review_row.get("manual_review_required") == "true"
        ):
            raise Checkpoint1ReviewError(
                "Explicit DNA/ssDNA must not enter an active UTexas review batch: "
                f"{review_row['record_id']!r}"
            )
        batch = (review_row.get("review_batch") or "").strip()
        if not batch:
            raise Checkpoint1ReviewError(
                "Review-required UTexas row missing review_batch: "
                f"{review_row['record_id']!r}"
            )
        if batch not in UTEXAS_BATCH_ORDER:
            raise Checkpoint1ReviewError(
                f"Unknown UTexas review_batch {batch!r} for "
                f"{review_row['record_id']!r}"
            )
        detail_batch = (detail_row.get("review_batch") or "").strip()
        if detail_batch and detail_batch != batch:
            raise Checkpoint1ReviewError(
                f"review_batch mismatch for {review_row['record_id']!r}"
            )
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        draft_rows.append(
            build_utexas_manual_review_row(
                review_row=review_row,
                local_detail=detail_row,
                review_batch=batch,
                review_order=0,
            )
        )

    draft_rows.sort(key=utexas_review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if (
            ordered["review_action"]
            or ordered["reviewer_note"]
            or ordered["reviewer_initials"]
        ):
            raise Checkpoint1ReviewError(
                "Reviewer fields must be empty in the prepared package"
            )
        queue_rows.append(ordered)
        batch = ordered["review_batch"]
        stats.batch_counts[batch] = stats.batch_counts.get(batch, 0) + 1
        decision = ordered["proposed_decision"]
        stats.decision_counts[decision] = stats.decision_counts.get(decision, 0) + 1
        primary = ordered["primary_reason"]
        stats.primary_reason_counts[primary] = (
            stats.primary_reason_counts.get(primary, 0) + 1
        )
        priority = ordered["manual_review_priority"]
        stats.priority_counts[priority] = stats.priority_counts.get(priority, 0) + 1

    stats.active_review_rows = len(queue_rows)
    if len({row["record_id"] for row in queue_rows}) != len(queue_rows):
        raise Checkpoint1ReviewError("Active review queue has duplicate record_id")
    if sum(stats.batch_counts.values()) != stats.active_review_rows:
        raise Checkpoint1ReviewError("Batch counts do not reconcile to active rows")

    index_rows = [build_utexas_index_row(row) for row in queue_rows]
    if any(column in UTEXAS_INDEX_COLUMNS for column in UTEXAS_SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")
    for column in UTEXAS_SEQUENCE_COLUMNS:
        if column not in UTEXAS_MANUAL_REVIEW_COLUMNS:
            raise Checkpoint1ReviewError(
                f"Queue schema missing sequence column {column!r}"
            )
    missing_detail = [
        column
        for column in UTEXAS_LOCAL_DETAIL_JOIN_FIELDS
        if column not in UTEXAS_LOCAL_DETAIL_COLUMNS
    ]
    if missing_detail:
        raise Checkpoint1ReviewError(
            f"UTexas local-detail schema missing join fields: {missing_detail}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "utexas_checkpoint1_manual_review.csv"
    out_index = output_dir / "utexas_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "utexas_checkpoint1_manual_review_summary.md"

    write_csv_atomic(out_queue, UTEXAS_MANUAL_REVIEW_COLUMNS, queue_rows)
    write_csv_atomic(out_index, UTEXAS_INDEX_COLUMNS, index_rows)

    review_hash_after = _sha256_file(review_path)
    local_detail_hash_after = _sha256_file(local_detail_path)
    inputs_unchanged = (
        review_hash_before == review_hash_after
        and local_detail_hash_before == local_detail_hash_after
    )
    if not inputs_unchanged:
        raise Checkpoint1ReviewError(
            "CHECKPOINT-1 inputs were modified during review-package preparation"
        )

    result = ReviewPackageResult(
        source_key="utexas",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
    )
    summary_text = build_utexas_review_summary(repo_root=repo_root, result=result)
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    if UTEXAS_PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No review action has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no review action has been recorded"
        )
    _write_text_atomic(out_summary, summary_text)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a CHECKPOINT-1 manual-review package from existing "
            "checkpoint review and local-detail artefacts."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source key (aptabase or utexas)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="CHECKPOINT-1 directory (default: data/interim/checkpoints/aptabase_cp1)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory beneath data/interim "
            "(default: <checkpoint-dir>/manual_review)"
        ),
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.source not in {"aptabase", "utexas"}:
            raise Checkpoint1ReviewError(
                f"Unsupported source_key={args.source!r}; "
                "supported: aptabase, utexas"
            )
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise Checkpoint1ReviewError(f"Repository root does not exist: {repo_root}")

        default_checkpoint = (
            Path("data/interim/checkpoints/utexas_cp1")
            if args.source == "utexas"
            else Path("data/interim/checkpoints/aptabase_cp1")
        )
        checkpoint_dir = (
            args.checkpoint_dir
            if args.checkpoint_dir is not None
            else default_checkpoint
        )
        output_dir = (
            args.output_dir
            if args.output_dir is not None
            else Path(checkpoint_dir) / "manual_review"
        )
        if args.source == "utexas":
            result = prepare_utexas_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
                expected_active_rows=args.expected_active_rows,
                expected_total_rows=(
                    UTEXAS_EXPECTED_TOTAL_ROWS
                    if args.expected_total_rows is None
                    else args.expected_total_rows
                ),
            )
        else:
            result = prepare_aptabase_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
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
            )
    except Checkpoint1ReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    # Aggregate counts only — never print sequence values.
    print(
        f"source={result.source_key}\n"
        f"total_checkpoint_records={stats.total_checkpoint_records}\n"
        f"active_review_rows={stats.active_review_rows}\n"
        f"no_review_records={stats.no_review_records}\n"
        f"inputs_unchanged={'pass' if result.inputs_unchanged else 'fail'}"
    )
    batch_order = UTEXAS_BATCH_ORDER if result.source_key == "utexas" else BATCH_ORDER
    for batch in batch_order:
        print(f"{batch}={stats.batch_counts.get(batch, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
