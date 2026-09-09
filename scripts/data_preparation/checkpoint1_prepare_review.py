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
from adapters.ena_checkpoint1_review import (  # noqa: E402
    BULK_CONFIRMATION_COLUMNS as ENA_BULK_CONFIRMATION_COLUMNS,
    EXCEPTION_COLUMNS as ENA_EXCEPTION_COLUMNS,
    MANUAL_FIELDS as ENA_MANUAL_FIELDS,
    RECOMMENDATION_FIELDS as ENA_RECOMMENDATION_FIELDS,
    RECONCILIATION_COLUMNS as ENA_RECONCILIATION_COLUMNS,
    RECONCILIATION_INDEX_COLUMNS as ENA_RECONCILIATION_INDEX_COLUMNS,
    RULE_MEMBERSHIP_COLUMNS as ENA_RULE_MEMBERSHIP_COLUMNS,
    RULE_REVIEW_COLUMNS as ENA_RULE_REVIEW_COLUMNS,
    RULE_SEQUENCE_COLUMNS as ENA_RULE_SEQUENCE_COLUMNS,
    EnaCheckpoint1ReviewError,
    build_bulk_confirmation_row as build_ena_bulk_confirmation_row,
    build_legacy_collapse_reconciliation,
    build_review_readme as build_ena_review_readme,
    build_rule_review_tables,
    format_validation_markdown as format_ena_validation_markdown,
    populate_record_recommendations as populate_ena_record_recommendations,
    read_csv_rows as read_ena_csv_rows,
    rule_summary_markdown as ena_rule_summary_markdown,
    validate_ena_review_package,
)
from adapters.ena_s3 import (  # noqa: E402
    DEFAULT_ENA_BATCHES,
    LOCAL_DETAIL_COLUMNS as ENA_LOCAL_DETAIL_COLUMNS,
)
from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    BULK_CONFIRMATION_COLUMNS,
    DEFAULT_RECOMMENDATIONS_REL,
    GROUP_REVIEW_COLUMNS,
    MANUAL_FIELDS,
    RECOMMENDATION_FIELDS,
    AptaDBCheckpoint1ReviewError,
    build_bulk_confirmation_row,
    build_group_review_rows,
    build_review_readme,
    format_validation_markdown,
    load_review_recommendations,
    populate_record_recommendations,
    read_csv_rows,
    validate_review_package,
)
from adapters.aptaindex_checkpoint1_review import (  # noqa: E402
    DEFAULT_RECOMMENDATIONS_REL as APTAINDEX_RECOMMENDATIONS_REL,
    AptaIndexCheckpoint1ReviewError,
    build_review_readme as build_aptaindex_review_readme,
    load_review_recommendations as load_aptaindex_recommendations,
    populate_aptaindex_recommendations,
)
from adapters.aptaindex_s3 import (  # noqa: E402
    DEFAULT_APTAINDEX_BATCHES,
    LOCAL_DETAIL_COLUMNS as APTAINDEX_LOCAL_DETAIL_COLUMNS,
)
from adapters.aptamerbase_checkpoint1_audit import (  # noqa: E402
    AptamerBaseCheckpoint1AuditError,
    run_aptamerbase_checkpoint1_audit,
)
from adapters.aptamerbase_checkpoint1_review import (  # noqa: E402
    DEFAULT_RECOMMENDATIONS_REL as APTAMERBASE_RECOMMENDATIONS_REL,
    AptamerBaseCheckpoint1ReviewError,
    build_review_readme as build_aptamerbase_review_readme,
    load_review_recommendations as load_aptamerbase_recommendations,
    populate_aptamerbase_recommendations,
)
from adapters.aptamerbase_s3 import (  # noqa: E402
    DEFAULT_APTAMERBASE_BATCHES,
    LOCAL_DETAIL_COLUMNS as APTAMERBASE_LOCAL_DETAIL_COLUMNS,
)
from adapters.riboaptamer_checkpoint1_review import (  # noqa: E402
    DEFAULT_RECOMMENDATIONS_REL as RIBOAPTAMER_RECOMMENDATIONS_REL,
    RiboAptamerCheckpoint1ReviewError,
    build_review_readme as build_riboaptamer_review_readme,
    format_riboaptamer_validation_markdown,
    load_review_recommendations as load_riboaptamer_recommendations,
    populate_riboaptamer_recommendations,
)
from adapters.riboaptamer_s3 import (  # noqa: E402
    DEFAULT_RIBOAPTAMER_BATCHES,
    LOCAL_DETAIL_COLUMNS as RIBOAPTAMER_LOCAL_DETAIL_COLUMNS,
)
from adapters.aptadb_s3 import (  # noqa: E402
    DEFAULT_APTADB_BATCHES,
    LOCAL_DETAIL_COLUMNS as APTADB_LOCAL_DETAIL_COLUMNS,
)
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
APTADB_EXPECTED_TOTAL_ROWS = 1350
APTADB_BATCH_ORDER: tuple[str, ...] = DEFAULT_APTADB_BATCHES
APTADB_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptaDB record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review."
)
APTADB_PERMITTED_DECISIONS: tuple[str, ...] = ("keep", "drop", "edit")
RIBOAPTAMER_EXPECTED_TOTAL_ROWS = 509
RIBOAPTAMER_BATCH_ORDER: tuple[str, ...] = DEFAULT_RIBOAPTAMER_BATCHES
RIBOAPTAMER_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No RiboAptamer record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review."
)
RIBOAPTAMER_PERMITTED_DECISIONS: tuple[str, ...] = ("keep", "drop", "edit")
APTAINDEX_EXPECTED_TOTAL_ROWS = 1050
APTAINDEX_BATCH_ORDER: tuple[str, ...] = DEFAULT_APTAINDEX_BATCHES
APTAINDEX_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptaIndex record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review."
)
APTAINDEX_PERMITTED_DECISIONS: tuple[str, ...] = ("keep", "drop", "edit")
ENA_EXPECTED_TOTAL_ROWS = 679
ENA_BATCH_ORDER: tuple[str, ...] = DEFAULT_ENA_BATCHES
ENA_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No ENA record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review.\n"
    "Global S4 has not been run."
)
ENA_PERMITTED_DECISIONS: tuple[str, ...] = ("keep", "drop", "edit")
APTAMERBASE_EXPECTED_TOTAL_ROWS = 2128
APTAMERBASE_BATCH_ORDER: tuple[str, ...] = DEFAULT_APTAMERBASE_BATCHES
APTAMERBASE_PIPELINE_STOP_STATEMENT = (
    "CHECKPOINT-1 package generated.\n"
    "No human decisions applied.\n"
    "No AptamerBase record is authorised for S4 yet.\n"
    "The pipeline is stopped awaiting Laura CHECKPOINT-1 review.\n"
    "Global S4 has not been run."
)
APTAMERBASE_PERMITTED_DECISIONS: tuple[str, ...] = ("keep", "drop", "edit")

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

APTADB_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
)

APTADB_MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    ("review_order",)
    + APTADB_LOCAL_DETAIL_COLUMNS
    + tuple(
        column
        for column in RECOMMENDATION_FIELDS
        if column not in APTADB_LOCAL_DETAIL_COLUMNS
    )
)

APTADB_INDEX_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in APTADB_MANUAL_REVIEW_COLUMNS
    if column not in APTADB_SEQUENCE_COLUMNS
)

RIBOAPTAMER_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
)

RIBOAPTAMER_MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    ("review_order",)
    + RIBOAPTAMER_LOCAL_DETAIL_COLUMNS
    + tuple(
        column
        for column in RECOMMENDATION_FIELDS
        if column not in RIBOAPTAMER_LOCAL_DETAIL_COLUMNS
    )
)

RIBOAPTAMER_INDEX_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in RIBOAPTAMER_MANUAL_REVIEW_COLUMNS
    if column not in RIBOAPTAMER_SEQUENCE_COLUMNS
)

APTAINDEX_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
)

APTAINDEX_MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    ("review_order",)
    + APTAINDEX_LOCAL_DETAIL_COLUMNS
    + tuple(
        column
        for column in RECOMMENDATION_FIELDS
        if column not in APTAINDEX_LOCAL_DETAIL_COLUMNS
    )
)

APTAINDEX_INDEX_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in APTAINDEX_MANUAL_REVIEW_COLUMNS
    if column not in APTAINDEX_SEQUENCE_COLUMNS
)

ENA_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "detected_constant_5p",
    "detected_constant_3p",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
)

ENA_MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    ("review_order",)
    + ENA_LOCAL_DETAIL_COLUMNS
    + tuple(
        column
        for column in ENA_RECOMMENDATION_FIELDS
        if column not in ENA_LOCAL_DETAIL_COLUMNS
    )
)

ENA_INDEX_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in ENA_MANUAL_REVIEW_COLUMNS
    if column not in ENA_SEQUENCE_COLUMNS
)

APTAMERBASE_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "recommended_sequence_corrected",
)

APTAMERBASE_MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    ("review_order",)
    + APTAMERBASE_LOCAL_DETAIL_COLUMNS
    + tuple(
        column
        for column in RECOMMENDATION_FIELDS
        if column not in APTAMERBASE_LOCAL_DETAIL_COLUMNS
    )
)

APTAMERBASE_INDEX_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in APTAMERBASE_MANUAL_REVIEW_COLUMNS
    if column not in APTAMERBASE_SEQUENCE_COLUMNS
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
    output_group_review: Path | None = None
    output_bulk_confirmation: Path | None = None
    output_readme: Path | None = None
    output_validation: Path | None = None
    output_rule_membership: Path | None = None
    output_exceptions: Path | None = None
    output_reconciliation: Path | None = None
    output_reconciliation_index: Path | None = None
    output_audit_dir: Path | None = None


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
    *,
    quoting: int = csv.QUOTE_MINIMAL,
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
                quoting=quoting,
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


def build_aptadb_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one AptaDB sequence-bearing active-review row."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
        "checkpoint_review_reasons",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )
    row = {column: "" for column in APTADB_MANUAL_REVIEW_COLUMNS}
    for column in APTADB_LOCAL_DETAIL_COLUMNS:
        row[column] = local_detail.get(column, "")
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for name in MANUAL_FIELDS:
        row[name] = ""
    return row


def build_aptadb_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    return {column: queue_row.get(column, "") for column in APTADB_INDEX_COLUMNS}


def aptadb_review_package_sort_key(
    row: Mapping[str, str],
) -> tuple[int, int, str, str]:
    batch = row.get("review_batch", "")
    try:
        batch_rank = APTADB_BATCH_ORDER.index(batch)
    except ValueError:
        batch_rank = len(APTADB_BATCH_ORDER)
    return (
        batch_rank,
        _priority_rank(row.get("manual_review_priority", "none")),
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )


def build_aptadb_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
) -> str:
    stats = result.stats
    lines = [
        "# AptaDB CHECKPOINT-1 manual-review package",
        "",
        "## Totals",
        "",
        f"- Total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- Active review rows: `{stats.active_review_rows}`",
        f"- No-review records: `{stats.no_review_records}`",
        f"- Human decisions recorded: `0`",
        "",
        "## Review model",
        "",
        "- `review_model` = `single_reviewer`",
        "- Permitted `manual_decision` values: `keep` / `drop` / `edit`",
        "- Permitted `manual_trim_action` values: `approve` / `override` / `reject` / `defer`",
        "- `manual_*` fields are blank until Laura completes review.",
        "- Machine `proposed_decision` and `review_recommendation` are not human decisions.",
        "",
        "## Counts by review batch",
        "",
    ]
    for batch in APTADB_BATCH_ORDER:
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
            "## Permitted reviewer decisions",
            "",
        ]
    )
    for action in APTADB_PERMITTED_DECISIONS:
        lines.append(f"- `{action}`")

    lines.extend(
        [
            "",
            "## Completion requirements",
            "",
            "- `manual_decision` must be nonempty for every active row before apply.",
            "- Trim actions, molecule overrides and sequence corrections are structured fields.",
            "- Recommendations must not be copied blindly into `manual_*` fields.",
            "- No human decision has yet been recorded.",
            "- Do not apply constant-region trims during this review step.",
            "- Do not infer UniProt, target families, evidence scores or leakage.",
            "",
            "## Outputs",
            "",
            f"- Sequence-bearing review queue: "
            f"`{_relative_display(result.output_queue, repo_root)}`",
            f"- Sequence-free review index: "
            f"`{_relative_display(result.output_index, repo_root)}`",
            (
                f"- Group-level constant review: "
                f"`{_relative_display(result.output_group_review, repo_root)}`"
                if result.output_group_review
                else "- Group-level constant review: `(not generated)`"
            ),
            (
                f"- Bulk audit confirmation template: "
                f"`{_relative_display(result.output_bulk_confirmation, repo_root)}`"
                if result.output_bulk_confirmation
                else "- Bulk audit confirmation template: `(not generated)`"
            ),
            (
                f"- Local review README: "
                f"`{_relative_display(result.output_readme, repo_root)}`"
                if result.output_readme
                else "- Local review README: `(not generated)`"
            ),
            (
                f"- Validation snapshot: "
                f"`{_relative_display(result.output_validation, repo_root)}`"
                if result.output_validation
                else "- Validation snapshot: `(not generated)`"
            ),
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local sequence warning",
            "",
            "WARNING: `aptadb_checkpoint1_manual_review.csv` contains source "
            "and canonical sequences for manual scientific review. It must "
            "remain beneath ignored `data/` and must never be staged or tracked.",
            "",
            "## Pipeline stop",
            "",
            APTADB_PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def prepare_aptadb_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = None,
    expected_total_rows: int | None = APTADB_EXPECTED_TOTAL_ROWS,
) -> ReviewPackageResult:
    """Build the AptaDB CHECKPOINT-1 active manual-review package."""
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "aptadb_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "aptadb_checkpoint1_local_detail.csv"
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
                    "No-review AptaDB row must not carry review_batch: "
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
            review_row.get("primary_reason") == "ssdna_parked"
            and review_row.get("manual_review_required") == "true"
            and "length_boundary"
            not in (review_row.get("checkpoint_review_reasons") or "")
            and "constant_region_proposal"
            not in (review_row.get("checkpoint_review_reasons") or "")
            and "judgement_dependent_technical"
            not in (review_row.get("checkpoint_review_reasons") or "")
        ):
            raise Checkpoint1ReviewError(
                "Technically valid ssDNA parks enter review only for checkpoint "
                f"categories: {review_row['record_id']!r}"
            )
        batch = (review_row.get("review_batch") or "").strip()
        if not batch:
            raise Checkpoint1ReviewError(
                "Review-required AptaDB row missing review_batch: "
                f"{review_row['record_id']!r}"
            )
        if batch not in APTADB_BATCH_ORDER:
            raise Checkpoint1ReviewError(
                f"Unknown AptaDB review_batch {batch!r} for "
                f"{review_row['record_id']!r}"
            )
        detail_batch = (detail_row.get("review_batch") or "").strip()
        if detail_batch and detail_batch != batch:
            raise Checkpoint1ReviewError(
                f"review_batch mismatch for {review_row['record_id']!r}"
            )
        if detail_row.get("manual_decision"):
            raise Checkpoint1ReviewError(
                "Prepared review must not pre-fill manual_decision: "
                f"{review_row['record_id']!r}"
            )
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )

    recommendations_path = repo_root / DEFAULT_RECOMMENDATIONS_REL
    recommendations: dict[str, object] = {"records": {}, "groups": {}, "audit_only": {}}
    if recommendations_path.is_file():
        recommendations = load_review_recommendations(recommendations_path)

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        built = build_aptadb_manual_review_row(
            review_row=review_row,
            local_detail=detail_row,
            review_batch=batch,
            review_order=0,
        )
        try:
            built = populate_record_recommendations(
                built, recommendations=recommendations
            )
        except AptaDBCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc
        draft_rows.append(built)

    draft_rows.sort(key=aptadb_review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if any(ordered.get(name) for name in MANUAL_FIELDS):
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

    index_rows = [build_aptadb_index_row(row) for row in queue_rows]
    if any(column in APTADB_INDEX_COLUMNS for column in APTADB_SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")

    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "aptadb_constant_region_proposals.csv"
    )
    canonical_path = checkpoint_dir / "aptadb_s3_canonical.csv"
    proposals = read_csv_rows(proposals_path) if proposals_path.is_file() else []
    canonical_by_id: dict[str, dict[str, str]] = {}
    if canonical_path.is_file():
        canonical_by_id = {
            row["record_id"]: row for row in read_csv_rows(canonical_path)
        }
    group_rows = build_group_review_rows(
        queue_rows=queue_rows,
        proposals=proposals,
        canonical_by_id=canonical_by_id,
        recommendations=recommendations,
    )
    bulk_row = build_bulk_confirmation_row(queue_rows)
    try:
        validation = validate_review_package(
            queue_rows=queue_rows,
            group_rows=group_rows,
            bulk_confirmation=bulk_row,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "aptadb_checkpoint1_manual_review.csv"
    out_index = output_dir / "aptadb_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "aptadb_checkpoint1_manual_review_summary.md"
    out_group = output_dir / "aptadb_checkpoint1_constant_group_review.csv"
    out_bulk = output_dir / "aptadb_checkpoint1_bulk_audit_confirmation.csv"
    out_readme = output_dir / "README.md"
    out_validation = output_dir / "aptadb_checkpoint1_validation.md"

    write_csv_atomic(out_queue, APTADB_MANUAL_REVIEW_COLUMNS, queue_rows)
    write_csv_atomic(out_index, APTADB_INDEX_COLUMNS, index_rows)
    write_csv_atomic(out_group, GROUP_REVIEW_COLUMNS, group_rows)
    write_csv_atomic(out_bulk, BULK_CONFIRMATION_COLUMNS, [bulk_row])
    _write_text_atomic(out_readme, build_review_readme())
    _write_text_atomic(out_validation, format_validation_markdown(validation))

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
        source_key="aptadb",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
        output_group_review=out_group,
        output_bulk_confirmation=out_bulk,
        output_readme=out_readme,
        output_validation=out_validation,
    )
    summary_text = build_aptadb_review_summary(repo_root=repo_root, result=result)
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    if APTADB_PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No human decision has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no human decision has been recorded"
        )
    _write_text_atomic(out_summary, summary_text)
    return result


def build_riboaptamer_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one RiboAptamer sequence-bearing active-review row."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
        "checkpoint_review_reasons",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )
    row = {column: "" for column in RIBOAPTAMER_MANUAL_REVIEW_COLUMNS}
    for column in RIBOAPTAMER_LOCAL_DETAIL_COLUMNS:
        row[column] = local_detail.get(column, "")
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for name in MANUAL_FIELDS:
        row[name] = ""
    return row


def build_riboaptamer_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    return {column: queue_row.get(column, "") for column in RIBOAPTAMER_INDEX_COLUMNS}


def riboaptamer_review_package_sort_key(
    row: Mapping[str, str],
) -> tuple[int, int, str, str]:
    batch = row.get("review_batch", "")
    try:
        batch_rank = RIBOAPTAMER_BATCH_ORDER.index(batch)
    except ValueError:
        batch_rank = len(RIBOAPTAMER_BATCH_ORDER)
    return (
        batch_rank,
        _priority_rank(row.get("manual_review_priority", "none")),
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )


def build_riboaptamer_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
) -> str:
    stats = result.stats
    lines = [
        "# RiboAptamer CHECKPOINT-1 manual-review package",
        "",
        "## Totals",
        "",
        f"- Total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- Active review rows: `{stats.active_review_rows}`",
        f"- No-review records: `{stats.no_review_records}`",
        f"- Human decisions recorded: `0`",
        "",
        "## Review model",
        "",
        "- `review_model` = `single_reviewer`",
        "- Permitted `manual_decision` values: `keep` / `drop` / `edit`",
        "- Permitted `manual_trim_action` values: `approve` / `override` / `reject` / `defer`",
        "- `manual_*` fields are blank until Laura completes review.",
        "- Machine `proposed_decision` and `review_recommendation` are not human decisions.",
        "",
        "## What S3 automatically excluded",
        "",
        "Automatic technical rejects (length out of range, ambiguous bases,",
        "invalid alphabet without a judgement-dependent overlap, mixed T/U,",
        "missing sequence) are in the rejection log. They are not in this",
        "active queue unless a judgement-dependent condition also applies.",
        "",
        "## What requires human judgement",
        "",
        "- Judgement-dependent technical rows: truncation, alignment gaps,",
        "  primer-like / library-template if present, and trim-induced cases.",
        "  Truncation/alignment review takes precedence over overlapping",
        "  invalid-character context. The SelB ellipsis record is in this batch.",
        "- The known T7 motif is an unapplied trim proposal. Detection",
        "  confidence is the approved motif library. `sequence_core` is unchanged.",
        "- Trim-induced length failures: currently zero because no trim was applied.",
        "- Length-boundary retained records (20–25 nt and 90–100 nt) are for",
        "  eyeballing, not rejection.",
        "- A deterministic random kept sample of 30 technically eligible records.",
        "",
        "Group-wise constant-region inference was disabled for the RiboAptamer",
        "S2/S3 run. Target/evidence/non-protein routing remains deferred to S4.",
        "",
        "## Counts by review batch",
        "",
    ]
    for batch in RIBOAPTAMER_BATCH_ORDER:
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
            "## Permitted reviewer decisions",
            "",
        ]
    )
    for action in RIBOAPTAMER_PERMITTED_DECISIONS:
        lines.append(f"- `{action}`")

    lines.extend(
        [
            "",
            "## How edit / sequence correction / trim work",
            "",
            "- `keep` retains the current technical route.",
            "- `drop` is a human-reviewed exclusion. Do not combine it with",
            "  sequence/molecule/trim edits.",
            "- `edit` requires a corrected sequence, molecule/chemistry override,",
            "  or an explicit trim action.",
            "- `sequence_raw` remains the original source sequence even if a",
            "  corrected technical sequence is supplied.",
            "- Trim lengths are nucleotide counts removed from reviewed",
            "  `sequence_full`. Approve, override, reject, or defer the T7",
            "  proposal; do not paste a new core sequence unless using `edit`.",
            "",
            "## Completion requirements",
            "",
            "- `manual_decision` must be nonempty for every active row before apply.",
            "- Trim actions, molecule overrides and sequence corrections are structured fields.",
            "- Recommendations must not be copied blindly into `manual_*` fields.",
            "- No human decision has yet been recorded.",
            "- The apply stage will fail closed until required review decisions are resolved.",
            "- Do not apply constant-region trims during this review step.",
            "- Do not infer UniProt, target families, evidence scores or leakage.",
            "",
            "## Outputs",
            "",
            f"- Sequence-bearing review queue: "
            f"`{_relative_display(result.output_queue, repo_root)}`",
            f"- Sequence-free review index: "
            f"`{_relative_display(result.output_index, repo_root)}`",
        ]
    )
    if result.output_group_review is not None:
        lines.append(
            f"- Group-level constant review: "
            f"`{_relative_display(result.output_group_review, repo_root)}`"
        )
    if result.output_bulk_confirmation is not None:
        lines.append(
            f"- Bulk audit confirmation: "
            f"`{_relative_display(result.output_bulk_confirmation, repo_root)}`"
        )
    if result.output_readme is not None:
        lines.append(
            f"- README: `{_relative_display(result.output_readme, repo_root)}`"
        )
    if result.output_validation is not None:
        lines.append(
            f"- Validation: `{_relative_display(result.output_validation, repo_root)}`"
        )
    lines.extend(
        [
            f"- This summary: `{_relative_display(result.output_summary, repo_root)}`",
            "",
            "## Local-detail warning",
            "",
            "WARNING: the record-level review CSV contains source sequences.",
            "It must remain under ignored `data/` and must never be staged.",
            "",
            "## Pipeline stop",
            "",
            RIBOAPTAMER_PIPELINE_STOP_STATEMENT,
            "",
        ]
    )
    return "\n".join(lines)


def prepare_riboaptamer_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = None,
    expected_total_rows: int | None = RIBOAPTAMER_EXPECTED_TOTAL_ROWS,
) -> ReviewPackageResult:
    """Build the RiboAptamer CHECKPOINT-1 active manual-review package."""
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "riboaptamer_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "riboaptamer_checkpoint1_local_detail.csv"
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
                    "No-review RiboAptamer row must not carry review_batch: "
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
        batch = (review_row.get("review_batch") or "").strip()
        if not batch:
            raise Checkpoint1ReviewError(
                "Review-required RiboAptamer row missing review_batch: "
                f"{review_row['record_id']!r}"
            )
        if batch not in RIBOAPTAMER_BATCH_ORDER:
            raise Checkpoint1ReviewError(
                f"Unknown RiboAptamer review_batch {batch!r} for "
                f"{review_row['record_id']!r}"
            )
        detail_batch = (detail_row.get("review_batch") or "").strip()
        if detail_batch and detail_batch != batch:
            raise Checkpoint1ReviewError(
                f"review_batch mismatch for {review_row['record_id']!r}"
            )
        if detail_row.get("manual_decision"):
            raise Checkpoint1ReviewError(
                "Prepared review must not pre-fill manual_decision: "
                f"{review_row['record_id']!r}"
            )
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )

    recommendations_path = repo_root / RIBOAPTAMER_RECOMMENDATIONS_REL
    recommendations: dict[str, object] = {
        "records": {},
        "groups": {},
        "audit_only": {},
        "known_motif": {},
        "judgement_dependent": {},
    }
    if recommendations_path.is_file():
        try:
            recommendations = load_riboaptamer_recommendations(recommendations_path)
        except RiboAptamerCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        built = build_riboaptamer_manual_review_row(
            review_row=review_row,
            local_detail=detail_row,
            review_batch=batch,
            review_order=0,
        )
        try:
            built = populate_riboaptamer_recommendations(
                built, recommendations=recommendations
            )
        except RiboAptamerCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc
        draft_rows.append(built)

    draft_rows.sort(key=riboaptamer_review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if any(ordered.get(name) for name in MANUAL_FIELDS):
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

    index_rows = [build_riboaptamer_index_row(row) for row in queue_rows]
    if any(column in RIBOAPTAMER_INDEX_COLUMNS for column in RIBOAPTAMER_SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")

    bulk_row = build_bulk_confirmation_row(queue_rows)
    try:
        validation = validate_review_package(
            queue_rows=queue_rows,
            group_rows=[],
            bulk_confirmation=bulk_row,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "riboaptamer_checkpoint1_manual_review.csv"
    out_index = output_dir / "riboaptamer_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "riboaptamer_checkpoint1_manual_review_summary.md"
    out_group = output_dir / "riboaptamer_checkpoint1_constant_group_review.csv"
    out_bulk = output_dir / "riboaptamer_checkpoint1_bulk_audit_confirmation.csv"
    out_readme = output_dir / "README.md"
    out_validation = output_dir / "riboaptamer_checkpoint1_validation.md"

    write_csv_atomic(out_queue, RIBOAPTAMER_MANUAL_REVIEW_COLUMNS, queue_rows)
    write_csv_atomic(out_index, RIBOAPTAMER_INDEX_COLUMNS, index_rows)
    write_csv_atomic(out_group, GROUP_REVIEW_COLUMNS, [])
    write_csv_atomic(out_bulk, BULK_CONFIRMATION_COLUMNS, [bulk_row])
    _write_text_atomic(out_readme, build_riboaptamer_review_readme())
    _write_text_atomic(
        out_validation, format_riboaptamer_validation_markdown(validation)
    )

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
        source_key="riboaptamer",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
        output_group_review=out_group,
        output_bulk_confirmation=out_bulk,
        output_readme=out_readme,
        output_validation=out_validation,
    )
    summary_text = build_riboaptamer_review_summary(
        repo_root=repo_root, result=result
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    if RIBOAPTAMER_PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No human decision has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no human decision has been recorded"
        )
    if "fail closed" not in summary_text.lower():
        raise Checkpoint1ReviewError(
            "Review summary must state that apply will fail closed"
        )
    _write_text_atomic(out_summary, summary_text)
    return result


def build_aptaindex_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one AptaIndex sequence-bearing active-review row."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
        "checkpoint_review_reasons",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )
    row = {column: "" for column in APTAINDEX_MANUAL_REVIEW_COLUMNS}
    for column in APTAINDEX_LOCAL_DETAIL_COLUMNS:
        row[column] = local_detail.get(column, "")
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for name in MANUAL_FIELDS:
        row[name] = ""
    return row


def build_aptaindex_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    return {column: queue_row.get(column, "") for column in APTAINDEX_INDEX_COLUMNS}


def aptaindex_review_package_sort_key(
    row: Mapping[str, str],
) -> tuple[int, int, str, str]:
    batch = row.get("review_batch", "")
    try:
        batch_rank = APTAINDEX_BATCH_ORDER.index(batch)
    except ValueError:
        batch_rank = len(APTAINDEX_BATCH_ORDER)
    return (
        batch_rank,
        _priority_rank(row.get("manual_review_priority", "none")),
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )


def build_aptaindex_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
) -> str:
    stats = result.stats
    lines = [
        "# AptaIndex CHECKPOINT-1 manual-review package",
        "",
        "## Totals",
        "",
        f"- Total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- Active review rows: `{stats.active_review_rows}`",
        f"- No-review records: `{stats.no_review_records}`",
        f"- Human decisions recorded: `0`",
        "",
        "## Review model",
        "",
        "- `review_model` = `single_reviewer`",
        "- Permitted `manual_decision` values: `keep` / `drop` / `edit`",
        "- Permitted `manual_trim_action` values: `approve` / `override` / `reject` / `defer`",
        "- `manual_*` fields are blank until Laura completes review.",
        "- Machine `proposed_decision` and `review_recommendation` are not human decisions.",
        "",
        "## What S3 automatically excluded",
        "",
        "Automatic technical rejects (missing sequence, peptide",
        "`non_nucleic_acid_molecule`, ordinary length-out-of-range, automatic",
        "alphabet failures without chemistry judgement) are in the rejection",
        "log. Straightforward ssDNA is parked. They are not in this active",
        "queue unless a judgement-dependent condition also applies.",
        "",
        "## What requires human judgement",
        "",
        "- Unsupported chemical notation: parser failed closed; do not auto-edit.",
        "- Source Type / token-family disagreement: no silent molecule override.",
        "- L-RNA / L-DNA: preserve stereochemistry.",
        "- Chimeric: preserve source Type and token-family evidence.",
        "- Mixed T/U after chemical parsing: do not silently convert.",
        "- Known-motif constant-region proposals are unapplied.",
        "- Length-boundary retained records (20–25 nt and 90–100 nt) are for",
        "  eyeballing, not rejection.",
        "- A deterministic random kept sample of 30 technically eligible records.",
        "",
        "Group-wise constant-region inference was disabled. Target, evidence,",
        "affinity, Target Type routing, and leakage remain deferred to S4.",
        "Blank Target is not an S3 missing_target reject. Multi-target",
        "sequence copies are not S3 conflicts.",
        "",
        "## Counts by review batch",
        "",
    ]
    for batch in APTAINDEX_BATCH_ORDER:
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
            "## Permitted reviewer decisions",
            "",
        ]
    )
    for action in APTAINDEX_PERMITTED_DECISIONS:
        lines.append(f"- `{action}`")

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Queue: `{_relative_display(result.output_queue, repo_root)}`",
            f"- Sequence-free index: `{_relative_display(result.output_index, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
        ]
    )
    if result.output_group_review is not None:
        lines.append(
            f"- Constant-group review: "
            f"`{_relative_display(result.output_group_review, repo_root)}`"
        )
    if result.output_bulk_confirmation is not None:
        lines.append(
            f"- Bulk audit confirmation: "
            f"`{_relative_display(result.output_bulk_confirmation, repo_root)}`"
        )
    if result.output_validation is not None:
        lines.append(
            f"- Validation: `{_relative_display(result.output_validation, repo_root)}`"
        )
    lines.extend(
        [
            "",
            "WARNING: the manual-review CSV contains restricted AptaIndex",
            "sequences. Keep it under `data/`. Do not commit it.",
            "",
            "No human decision has yet been recorded.",
            "Apply will fail closed until every active row is resolved.",
            "",
            APTAINDEX_PIPELINE_STOP_STATEMENT,
        ]
    )
    return "\n".join(lines) + "\n"


def prepare_aptaindex_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = None,
    expected_total_rows: int | None = APTAINDEX_EXPECTED_TOTAL_ROWS,
) -> ReviewPackageResult:
    """Build the AptaIndex CHECKPOINT-1 active manual-review package."""
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "aptaindex_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "aptaindex_checkpoint1_local_detail.csv"
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
                    "No-review AptaIndex row must not carry review_batch: "
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
            review_row.get("proposed_decision") == "proposed_reject"
            and review_row.get("primary_reason") == "non_nucleic_acid_molecule"
        ):
            raise Checkpoint1ReviewError(
                "Peptide-molecule reject must not enter the active review queue: "
                f"{review_row['record_id']!r}"
            )
        batch = (review_row.get("review_batch") or "").strip()
        if not batch:
            raise Checkpoint1ReviewError(
                "Review-required AptaIndex row missing review_batch: "
                f"{review_row['record_id']!r}"
            )
        if batch not in APTAINDEX_BATCH_ORDER:
            raise Checkpoint1ReviewError(
                f"Unknown AptaIndex review_batch {batch!r} for "
                f"{review_row['record_id']!r}"
            )
        detail_batch = (detail_row.get("review_batch") or "").strip()
        if detail_batch and detail_batch != batch:
            raise Checkpoint1ReviewError(
                f"review_batch mismatch for {review_row['record_id']!r}"
            )
        if detail_row.get("manual_decision"):
            raise Checkpoint1ReviewError(
                "Prepared review must not pre-fill manual_decision: "
                f"{review_row['record_id']!r}"
            )
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )

    recommendations_path = repo_root / APTAINDEX_RECOMMENDATIONS_REL
    recommendations: dict[str, object] = {
        "records": {},
        "groups": {},
        "audit_only": {},
        "known_motif": {},
        "judgement_dependent": {},
    }
    if recommendations_path.is_file():
        try:
            recommendations = load_aptaindex_recommendations(recommendations_path)
        except AptaIndexCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        built = build_aptaindex_manual_review_row(
            review_row=review_row,
            local_detail=detail_row,
            review_batch=batch,
            review_order=0,
        )
        try:
            built = populate_aptaindex_recommendations(
                built, recommendations=recommendations
            )
        except AptaIndexCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc
        draft_rows.append(built)

    draft_rows.sort(key=aptaindex_review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if any(ordered.get(name) for name in MANUAL_FIELDS):
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

    index_rows = [build_aptaindex_index_row(row) for row in queue_rows]
    if any(column in APTAINDEX_INDEX_COLUMNS for column in APTAINDEX_SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")

    bulk_row = build_bulk_confirmation_row(queue_rows)
    try:
        validation = validate_review_package(
            queue_rows=queue_rows,
            group_rows=[],
            bulk_confirmation=bulk_row,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "aptaindex_checkpoint1_manual_review.csv"
    out_index = output_dir / "aptaindex_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "aptaindex_checkpoint1_manual_review_summary.md"
    out_group = output_dir / "aptaindex_checkpoint1_constant_group_review.csv"
    out_bulk = output_dir / "aptaindex_checkpoint1_bulk_audit_confirmation.csv"
    out_readme = output_dir / "README.md"
    out_validation = output_dir / "aptaindex_checkpoint1_validation.md"

    write_csv_atomic(
        out_queue,
        APTAINDEX_MANUAL_REVIEW_COLUMNS,
        queue_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        out_index,
        APTAINDEX_INDEX_COLUMNS,
        index_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(out_group, GROUP_REVIEW_COLUMNS, [], quoting=csv.QUOTE_ALL)
    write_csv_atomic(
        out_bulk, BULK_CONFIRMATION_COLUMNS, [bulk_row], quoting=csv.QUOTE_ALL
    )
    _write_text_atomic(out_readme, build_aptaindex_review_readme())
    _write_text_atomic(out_validation, format_validation_markdown(validation))

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
        source_key="aptaindex",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
        output_group_review=out_group,
        output_bulk_confirmation=out_bulk,
        output_readme=out_readme,
        output_validation=out_validation,
    )
    summary_text = build_aptaindex_review_summary(
        repo_root=repo_root, result=result
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    if APTAINDEX_PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No human decision has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no human decision has been recorded"
        )
    if "fail closed" not in summary_text.lower():
        raise Checkpoint1ReviewError(
            "Review summary must state that apply will fail closed"
        )
    _write_text_atomic(out_summary, summary_text)
    return result


def build_aptamerbase_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one AptamerBase sequence-bearing active-review row."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
        "checkpoint_review_reasons",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )
    row = {column: "" for column in APTAMERBASE_MANUAL_REVIEW_COLUMNS}
    for column in APTAMERBASE_LOCAL_DETAIL_COLUMNS:
        row[column] = local_detail.get(column, "")
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for name in MANUAL_FIELDS:
        row[name] = ""
    return row


def build_aptamerbase_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    return {column: queue_row.get(column, "") for column in APTAMERBASE_INDEX_COLUMNS}


def aptamerbase_review_package_sort_key(
    row: Mapping[str, str],
) -> tuple[int, int, str, str]:
    batch = row.get("review_batch", "")
    try:
        batch_rank = APTAMERBASE_BATCH_ORDER.index(batch)
    except ValueError:
        batch_rank = len(APTAMERBASE_BATCH_ORDER)
    return (
        batch_rank,
        _priority_rank(row.get("manual_review_priority", "none")),
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )


def build_aptamerbase_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
) -> str:
    stats = result.stats
    lines = [
        "# AptamerBase CHECKPOINT-1 manual-review package",
        "",
        "## Totals",
        "",
        f"- Total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- Active review rows: `{stats.active_review_rows}`",
        f"- No-review records: `{stats.no_review_records}`",
        f"- Human decisions recorded: `0`",
        f"- ready_for_application: `0`",
        "",
        "## Review model",
        "",
        "- `review_model` = `single_reviewer`",
        "- Permitted `manual_decision` values: `keep` / `drop` / `edit`",
        "- Permitted `manual_trim_action` values: `approve` / `override` / `reject` / `defer`",
        "- `manual_*` fields are blank until Laura completes review.",
        "- Machine `proposed_decision` and `review_recommendation` are not human decisions.",
        "",
        "## What S3 automatically excluded",
        "",
        "Non-aptamer RDF structure objects (`non_aptamer_source_object`),",
        "ordinary missing-sequence rejects, ordinary clean ssDNA parks, and",
        "ordinary automatic length rejects with no plausible known-motif trim",
        "are not in this active queue.",
        "",
        "## What requires human judgement",
        "",
        "- Source sequence notation (mixed T/U, ambiguous, gaps, invalid).",
        "- RDF DNA × U alphabet molecule/source contradiction.",
        "- Aptamer-topic unresolved molecule type.",
        "- Unsupported RNA chemistry, including Spiegelmer/L-RNA.",
        "- Unapplied known-motif / construct proposals.",
        "- Length-boundary retained records (20–25 nt and 90–100 nt) are for",
        "  eyeballing, not rejection.",
        "- A deterministic random kept sample of 30 technically eligible records.",
        "",
        "Group-wise constant-region inference was disabled. Target, evidence,",
        "affinity, PDB, leakage, deduplication, and clustering remain deferred.",
        "Blank `target_name_raw` is not an S3 missing_target reject.",
        "",
        "## Counts by review batch",
        "",
    ]
    for batch in APTAMERBASE_BATCH_ORDER:
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
            "## Permitted reviewer decisions",
            "",
        ]
    )
    for action in APTAMERBASE_PERMITTED_DECISIONS:
        lines.append(f"- `{action}`")

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Queue: `{_relative_display(result.output_queue, repo_root)}`",
            f"- Sequence-free index: `{_relative_display(result.output_index, repo_root)}`",
            f"- Summary: `{_relative_display(result.output_summary, repo_root)}`",
        ]
    )
    if result.output_group_review is not None:
        lines.append(
            f"- Constant-group review: "
            f"`{_relative_display(result.output_group_review, repo_root)}`"
        )
    if result.output_bulk_confirmation is not None:
        lines.append(
            f"- Bulk audit confirmation: "
            f"`{_relative_display(result.output_bulk_confirmation, repo_root)}`"
        )
    if result.output_validation is not None:
        lines.append(
            f"- Validation: `{_relative_display(result.output_validation, repo_root)}`"
        )
    if result.output_audit_dir is not None:
        lines.append(
            f"- Decision-support audit: "
            f"`{_relative_display(result.output_audit_dir, repo_root)}`"
        )
    lines.extend(
        [
            "",
            "WARNING: the manual-review CSV contains source sequences.",
            "Keep it under `data/`. Do not commit it.",
            "",
            "No human decision has yet been recorded.",
            "Apply will fail closed until every active row is resolved.",
            "",
            APTAMERBASE_PIPELINE_STOP_STATEMENT,
        ]
    )
    return "\n".join(lines) + "\n"


def prepare_aptamerbase_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = None,
    expected_total_rows: int | None = APTAMERBASE_EXPECTED_TOTAL_ROWS,
) -> ReviewPackageResult:
    """Build the AptamerBase CHECKPOINT-1 active manual-review package."""
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "aptamerbase_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "aptamerbase_checkpoint1_local_detail.csv"
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
                    "No-review AptamerBase row must not carry review_batch: "
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
            review_row.get("proposed_decision") == "proposed_reject"
            and review_row.get("primary_reason") == "non_aptamer_source_object"
        ):
            raise Checkpoint1ReviewError(
                "Non-aptamer source-object reject must not enter the active "
                f"review queue: {review_row['record_id']!r}"
            )
        batch = (review_row.get("review_batch") or "").strip()
        if not batch:
            raise Checkpoint1ReviewError(
                "Review-required AptamerBase row missing review_batch: "
                f"{review_row['record_id']!r}"
            )
        if batch not in APTAMERBASE_BATCH_ORDER:
            raise Checkpoint1ReviewError(
                f"Unknown AptamerBase review_batch {batch!r} for "
                f"{review_row['record_id']!r}"
            )
        detail_batch = (detail_row.get("review_batch") or "").strip()
        if detail_batch and detail_batch != batch:
            raise Checkpoint1ReviewError(
                f"review_batch mismatch for {review_row['record_id']!r}"
            )
        if detail_row.get("manual_decision"):
            raise Checkpoint1ReviewError(
                "Prepared review must not pre-fill manual_decision: "
                f"{review_row['record_id']!r}"
            )
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )

    recommendations_path = repo_root / APTAMERBASE_RECOMMENDATIONS_REL
    recommendations: dict[str, object] = {
        "records": {},
        "groups": {},
        "audit_only": {},
        "known_motif": {},
        "judgement_dependent": {},
    }
    if recommendations_path.is_file():
        try:
            recommendations = load_aptamerbase_recommendations(recommendations_path)
        except AptamerBaseCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        built = build_aptamerbase_manual_review_row(
            review_row=review_row,
            local_detail=detail_row,
            review_batch=batch,
            review_order=0,
        )
        try:
            built = populate_aptamerbase_recommendations(
                built, recommendations=recommendations
            )
        except AptamerBaseCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc
        draft_rows.append(built)

    draft_rows.sort(key=aptamerbase_review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if any(ordered.get(name) for name in MANUAL_FIELDS):
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

    index_rows = [build_aptamerbase_index_row(row) for row in queue_rows]
    if any(column in APTAMERBASE_INDEX_COLUMNS for column in APTAMERBASE_SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")

    bulk_row = build_bulk_confirmation_row(queue_rows)
    try:
        validation = validate_review_package(
            queue_rows=queue_rows,
            group_rows=[],
            bulk_confirmation=bulk_row,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "aptamerbase_checkpoint1_manual_review.csv"
    out_index = output_dir / "aptamerbase_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "aptamerbase_checkpoint1_manual_review_summary.md"
    out_group = output_dir / "aptamerbase_checkpoint1_constant_group_review.csv"
    out_bulk = output_dir / "aptamerbase_checkpoint1_bulk_audit_confirmation.csv"
    out_readme = output_dir / "README.md"
    out_validation = output_dir / "aptamerbase_checkpoint1_validation.md"

    write_csv_atomic(
        out_queue,
        APTAMERBASE_MANUAL_REVIEW_COLUMNS,
        queue_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(
        out_index,
        APTAMERBASE_INDEX_COLUMNS,
        index_rows,
        quoting=csv.QUOTE_ALL,
    )
    write_csv_atomic(out_group, GROUP_REVIEW_COLUMNS, [], quoting=csv.QUOTE_ALL)
    write_csv_atomic(
        out_bulk, BULK_CONFIRMATION_COLUMNS, [bulk_row], quoting=csv.QUOTE_ALL
    )
    _write_text_atomic(out_readme, build_aptamerbase_review_readme())
    _write_text_atomic(
        out_validation,
        format_validation_markdown(validation, source_label="AptamerBase"),
    )
    out_audit = output_dir / "audit"
    production_artefacts = (
        expected_total_rows == APTAMERBASE_EXPECTED_TOTAL_ROWS
        and (repo_root / "data/interim/normalised/aptamerbase_normalised.csv").is_file()
        and (
            repo_root
            / "data/interim/checkpoints/aptamerbase_cp1/aptamerbase_s3_canonical.csv"
        ).is_file()
    )
    rdf_path = (
        repo_root / "data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz"
    )
    try:
        run_aptamerbase_checkpoint1_audit(
            repo_root=repo_root,
            queue_rows=queue_rows,
            audit_dir=out_audit,
            rdf_path=rdf_path if rdf_path.is_file() else None,
            freeze_production_artefacts=production_artefacts,
        )
    except AptamerBaseCheckpoint1AuditError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc

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
        source_key="aptamerbase",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
        output_group_review=out_group,
        output_bulk_confirmation=out_bulk,
        output_readme=out_readme,
        output_validation=out_validation,
        output_audit_dir=out_audit,
    )
    summary_text = build_aptamerbase_review_summary(
        repo_root=repo_root, result=result
    )
    abs_root = str(repo_root.resolve())
    if abs_root in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    if APTAMERBASE_PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No human decision has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no human decision has been recorded"
        )
    if "fail closed" not in summary_text.lower():
        raise Checkpoint1ReviewError(
            "Review summary must state that apply will fail closed"
        )
    _write_text_atomic(out_summary, summary_text)
    return result


def build_ena_manual_review_row(
    *,
    review_row: Mapping[str, str],
    local_detail: Mapping[str, str],
    review_batch: str,
    review_order: int,
) -> dict[str, str]:
    """Build one ENA sequence-bearing active-review row."""
    if review_row["record_id"] != local_detail["record_id"]:
        raise Checkpoint1ReviewError("Joined record_id mismatch")
    for field_name in (
        "proposed_decision",
        "primary_reason",
        "secondary_reasons",
        "manual_review_priority",
        "checkpoint_review_reasons",
    ):
        if review_row.get(field_name, "") != local_detail.get(field_name, ""):
            raise Checkpoint1ReviewError(
                f"Checkpoint field mismatch for {field_name!r} on "
                f"{review_row['record_id']!r}"
            )
    row = {column: "" for column in ENA_MANUAL_REVIEW_COLUMNS}
    for column in ENA_LOCAL_DETAIL_COLUMNS:
        row[column] = local_detail.get(column, "")
    row["review_batch"] = review_batch
    row["review_order"] = str(review_order)
    row["record_id"] = review_row["record_id"]
    for name in ENA_MANUAL_FIELDS:
        row[name] = ""
    return row


def build_ena_index_row(queue_row: Mapping[str, str]) -> dict[str, str]:
    return {column: queue_row.get(column, "") for column in ENA_INDEX_COLUMNS}


def ena_review_package_sort_key(
    row: Mapping[str, str],
) -> tuple[int, int, str, str]:
    batch = row.get("review_batch", "")
    try:
        batch_rank = ENA_BATCH_ORDER.index(batch)
    except ValueError:
        batch_rank = len(ENA_BATCH_ORDER)
    try:
        order = int(row.get("review_order") or "0")
    except ValueError:
        order = 0
    return (batch_rank, order, row.get("primary_reason", ""), row.get("record_id", ""))


def build_ena_review_summary(
    *,
    repo_root: Path,
    result: ReviewPackageResult,
    rule_rows: Sequence[Mapping[str, str]],
    exception_rows: Sequence[Mapping[str, str]],
    reconciliation_rows: Sequence[Mapping[str, str]],
    validation_ready: int,
) -> str:
    stats = result.stats
    lines = [
        "# ENA CHECKPOINT-1 manual-review package",
        "",
        f"- total checkpoint records: `{stats.total_checkpoint_records}`",
        f"- active record-level review rows: `{stats.active_review_rows}`",
        f"- no record-level review: `{stats.no_review_records}`",
        "",
        "## Record-level batches",
        "",
    ]
    for batch in ENA_BATCH_ORDER:
        lines.append(f"- `{batch}`: `{stats.batch_counts.get(batch, 0)}`")
    lines.extend(
        [
            "",
            ena_rule_summary_markdown(rule_rows),
            "",
            f"- record-level constant-region exceptions: `{len(exception_rows)}`",
            f"- 679-versus-676 reconciliation groups: `{len(reconciliation_rows)}`",
            f"- validator ready_for_application: `{validation_ready}`",
            "",
            "Human decision fields are blank. Machine recommendations are not",
            "human decisions. Apply will fail closed.",
            "",
            "No human decision has yet been recorded.",
            "",
            ENA_PIPELINE_STOP_STATEMENT,
        ]
    )
    text = "\n".join(lines) + "\n"
    abs_root = str(repo_root.resolve())
    if abs_root in text:
        raise Checkpoint1ReviewError(
            "Review summary must not contain absolute repository paths"
        )
    return text


def prepare_ena_checkpoint1_review(
    *,
    repo_root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    expected_active_rows: int | None = None,
    expected_total_rows: int | None = ENA_EXPECTED_TOTAL_ROWS,
) -> ReviewPackageResult:
    """Build the ENA CHECKPOINT-1 structured manual-review package."""
    repo_root = repo_root.resolve()
    checkpoint_dir = _resolve_under_repo(repo_root, checkpoint_dir)
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    review_path = checkpoint_dir / "ena_checkpoint1_review.csv"
    local_detail_path = checkpoint_dir / "ena_checkpoint1_local_detail.csv"
    canonical_path = checkpoint_dir / "ena_s3_canonical.csv"
    for path, label in (
        (review_path, "checkpoint review"),
        (local_detail_path, "local-detail"),
        (canonical_path, "S3 canonical"),
    ):
        if not path.is_file():
            raise Checkpoint1ReviewError(f"Missing {label} input: {path.name}")

    review_hash_before = _sha256_file(review_path)
    local_detail_hash_before = _sha256_file(local_detail_path)
    canonical_hash_before = _sha256_file(canonical_path)

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
                    "No-review ENA row must not carry review_batch: "
                    f"{review_row['record_id']!r}"
                )
            continue
        batch = (review_row.get("review_batch") or "").strip()
        if not batch:
            raise Checkpoint1ReviewError(
                "Review-required ENA row missing review_batch: "
                f"{review_row['record_id']!r}"
            )
        if batch not in ENA_BATCH_ORDER:
            raise Checkpoint1ReviewError(
                f"Unknown ENA review_batch {batch!r} for {review_row['record_id']!r}"
            )
        if detail_row.get("manual_decision"):
            raise Checkpoint1ReviewError(
                "Prepared review must not pre-fill manual_decision: "
                f"{review_row['record_id']!r}"
            )
        active_pairs.append((review_row, detail_row, batch))

    if expected_active_rows is not None and len(active_pairs) != expected_active_rows:
        raise Checkpoint1ReviewError(
            f"Active review row count must be {expected_active_rows}; "
            f"got {len(active_pairs)}"
        )

    draft_rows: list[dict[str, str]] = []
    for review_row, detail_row, batch in active_pairs:
        built = build_ena_manual_review_row(
            review_row=review_row,
            local_detail=detail_row,
            review_batch=batch,
            review_order=0,
        )
        try:
            built = populate_ena_record_recommendations(built)
        except EnaCheckpoint1ReviewError as exc:
            raise Checkpoint1ReviewError(str(exc)) from exc
        draft_rows.append(built)

    draft_rows.sort(key=ena_review_package_sort_key)
    queue_rows: list[dict[str, str]] = []
    for index, row in enumerate(draft_rows, start=1):
        ordered = dict(row)
        ordered["review_order"] = str(index)
        if any(ordered.get(name) for name in ENA_MANUAL_FIELDS):
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

    index_rows = [build_ena_index_row(row) for row in queue_rows]
    if any(column in ENA_INDEX_COLUMNS for column in ENA_SEQUENCE_COLUMNS):
        raise Checkpoint1ReviewError("Sequence columns leaked into index schema")

    proposals_path = (
        repo_root / "data" / "interim" / "normalised" / "ena_constant_region_proposals.csv"
    )
    membership_path = (
        repo_root
        / "data"
        / "interim"
        / "normalised"
        / "ena_constant_region_membership.csv"
    )
    sidecar_path = (
        repo_root / "data" / "interim" / "extracted" / "ena_source_metadata.csv"
    )
    processed_path = (
        repo_root / "data" / "processed" / "ena" / "ena_aptamer_supplement_clean.csv"
    )
    proposals = read_ena_csv_rows(proposals_path) if proposals_path.is_file() else []
    membership = read_ena_csv_rows(membership_path) if membership_path.is_file() else []
    canonical_rows = read_ena_csv_rows(canonical_path)
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    decision_by_id = {row["record_id"]: row for row, _detail in paired}
    try:
        rule_rows, membership_out, exception_rows = build_rule_review_tables(
            proposals=proposals,
            membership_rows=membership,
            canonical_by_id=canonical_by_id,
            decision_by_id=decision_by_id,
        )
    except EnaCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc
    for col in ENA_RULE_SEQUENCE_COLUMNS:
        if col in ENA_RULE_REVIEW_COLUMNS:
            raise Checkpoint1ReviewError(
                f"Motif/sequence column leaked into rule review schema: {col}"
            )
        if col in ENA_RECONCILIATION_COLUMNS:
            raise Checkpoint1ReviewError(
                f"Sequence column leaked into reconciliation schema: {col}"
            )

    sidecar_rows = read_ena_csv_rows(sidecar_path) if sidecar_path.is_file() else []
    processed_rows = read_ena_csv_rows(processed_path) if processed_path.is_file() else []
    if expected_total_rows == ENA_EXPECTED_TOTAL_ROWS and not processed_path.is_file():
        raise Checkpoint1ReviewError(
            "ENA CHECKPOINT-1 reconciliation requires "
            "data/processed/ena/ena_aptamer_supplement_clean.csv"
        )
    try:
        reconciliation_rows = build_legacy_collapse_reconciliation(
            canonical_rows=canonical_rows,
            sidecar_rows=sidecar_rows,
            processed_rows=processed_rows,
            decision_by_id=decision_by_id,
        )
    except EnaCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc
    if expected_total_rows == ENA_EXPECTED_TOTAL_ROWS and len(reconciliation_rows) != 3:
        raise Checkpoint1ReviewError(
            "ENA CHECKPOINT-1 expected 3 legacy collapse groups; got "
            f"{len(reconciliation_rows)}"
        )
    collapse_ids: set[str] = set()
    for row in reconciliation_rows:
        collapse_ids.add(row["record_id_a"])
        collapse_ids.add(row["record_id_b"])
    if expected_total_rows == ENA_EXPECTED_TOTAL_ROWS and len(collapse_ids) != 6:
        raise Checkpoint1ReviewError(
            "ENA CHECKPOINT-1 expected six records across three collapse pairs"
        )
    present = {row["record_id"] for row, _detail in paired}
    missing = collapse_ids - present
    if missing:
        raise Checkpoint1ReviewError(
            "Legacy collapse members disappeared from the 679-row S3 set"
        )

    bulk_row = build_ena_bulk_confirmation_row(queue_rows)
    try:
        validation = validate_ena_review_package(
            queue_rows=queue_rows,
            rule_rows=rule_rows,
            exception_rows=exception_rows,
            reconciliation_rows=reconciliation_rows,
            bulk_confirmation=bulk_row,
        )
    except EnaCheckpoint1ReviewError as exc:
        raise Checkpoint1ReviewError(str(exc)) from exc
    if validation.ready_for_application != 0:
        raise Checkpoint1ReviewError(
            "Blank CHECKPOINT-1 package must not be ready_for_application"
        )
    if validation.unresolved_manual_decisions == 0 and queue_rows:
        raise Checkpoint1ReviewError(
            "Blank CHECKPOINT-1 package must retain unresolved human decisions"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_queue = output_dir / "ena_checkpoint1_manual_review.csv"
    out_index = output_dir / "ena_checkpoint1_manual_review_index.csv"
    out_summary = output_dir / "ena_checkpoint1_manual_review_summary.md"
    out_group = output_dir / "ena_checkpoint1_constant_rule_review.csv"
    out_membership = output_dir / "ena_checkpoint1_constant_rule_membership.csv"
    out_exceptions = output_dir / "ena_checkpoint1_constant_exceptions.csv"
    out_reconciliation = output_dir / "ena_checkpoint1_legacy_collapse_reconciliation.csv"
    out_reconciliation_index = (
        output_dir / "ena_checkpoint1_legacy_collapse_reconciliation_index.csv"
    )
    out_bulk = output_dir / "ena_checkpoint1_bulk_audit_confirmation.csv"
    out_readme = output_dir / "README.md"
    out_validation = output_dir / "ena_checkpoint1_validation.md"

    write_csv_atomic(out_queue, ENA_MANUAL_REVIEW_COLUMNS, queue_rows)
    write_csv_atomic(out_index, ENA_INDEX_COLUMNS, index_rows)
    write_csv_atomic(out_group, ENA_RULE_REVIEW_COLUMNS, rule_rows)
    write_csv_atomic(out_membership, ENA_RULE_MEMBERSHIP_COLUMNS, membership_out)
    write_csv_atomic(out_exceptions, ENA_EXCEPTION_COLUMNS, exception_rows)
    write_csv_atomic(out_reconciliation, ENA_RECONCILIATION_COLUMNS, reconciliation_rows)
    write_csv_atomic(
        out_reconciliation_index, ENA_RECONCILIATION_INDEX_COLUMNS, reconciliation_rows
    )
    write_csv_atomic(out_bulk, ENA_BULK_CONFIRMATION_COLUMNS, [bulk_row])
    _write_text_atomic(out_readme, build_ena_review_readme())
    _write_text_atomic(out_validation, format_ena_validation_markdown(validation))

    review_hash_after = _sha256_file(review_path)
    local_detail_hash_after = _sha256_file(local_detail_path)
    canonical_hash_after = _sha256_file(canonical_path)
    inputs_unchanged = (
        review_hash_before == review_hash_after
        and local_detail_hash_before == local_detail_hash_after
        and canonical_hash_before == canonical_hash_after
    )
    if not inputs_unchanged:
        raise Checkpoint1ReviewError(
            "CHECKPOINT-1 inputs were modified during review-package preparation"
        )

    result = ReviewPackageResult(
        source_key="ena",
        stats=stats,
        output_queue=out_queue,
        output_index=out_index,
        output_summary=out_summary,
        review_hash_before=review_hash_before,
        review_hash_after=review_hash_after,
        local_detail_hash_before=local_detail_hash_before,
        local_detail_hash_after=local_detail_hash_after,
        inputs_unchanged=inputs_unchanged,
        output_group_review=out_group,
        output_bulk_confirmation=out_bulk,
        output_readme=out_readme,
        output_validation=out_validation,
        output_rule_membership=out_membership,
        output_exceptions=out_exceptions,
        output_reconciliation=out_reconciliation,
        output_reconciliation_index=out_reconciliation_index,
    )
    summary_text = build_ena_review_summary(
        repo_root=repo_root,
        result=result,
        rule_rows=rule_rows,
        exception_rows=exception_rows,
        reconciliation_rows=reconciliation_rows,
        validation_ready=validation.ready_for_application,
    )
    if ENA_PIPELINE_STOP_STATEMENT not in summary_text:
        raise Checkpoint1ReviewError("Review summary missing pipeline stop statement")
    if "No human decision has yet been recorded." not in summary_text:
        raise Checkpoint1ReviewError(
            "Review summary must state that no human decision has been recorded"
        )
    if "fail closed" not in summary_text.lower():
        raise Checkpoint1ReviewError(
            "Review summary must state that apply will fail closed"
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
        help="Source key (aptabase, utexas, aptadb, riboaptamer, aptaindex, ena, or aptamerbase)",
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
        if args.source not in {
            "aptabase",
            "utexas",
            "aptadb",
            "riboaptamer",
            "aptaindex",
            "ena",
            "aptamerbase",
        }:
            raise Checkpoint1ReviewError(
                f"Unsupported source_key={args.source!r}; "
                "supported: aptabase, utexas, aptadb, riboaptamer, aptaindex, "
                "ena, aptamerbase"
            )
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise Checkpoint1ReviewError(f"Repository root does not exist: {repo_root}")

        if args.source == "utexas":
            default_checkpoint = Path("data/interim/checkpoints/utexas_cp1")
        elif args.source == "aptadb":
            default_checkpoint = Path("data/interim/checkpoints/aptadb_cp1")
        elif args.source == "riboaptamer":
            default_checkpoint = Path("data/interim/checkpoints/riboaptamer_cp1")
        elif args.source == "aptaindex":
            default_checkpoint = Path("data/interim/checkpoints/aptaindex_cp1")
        elif args.source == "ena":
            default_checkpoint = Path("data/interim/checkpoints/ena_cp1")
        elif args.source == "aptamerbase":
            default_checkpoint = Path("data/interim/checkpoints/aptamerbase_cp1")
        else:
            default_checkpoint = Path("data/interim/checkpoints/aptabase_cp1")
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
        elif args.source == "aptadb":
            result = prepare_aptadb_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
                expected_active_rows=args.expected_active_rows,
                expected_total_rows=(
                    APTADB_EXPECTED_TOTAL_ROWS
                    if args.expected_total_rows is None
                    else args.expected_total_rows
                ),
            )
        elif args.source == "riboaptamer":
            result = prepare_riboaptamer_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
                expected_active_rows=args.expected_active_rows,
                expected_total_rows=(
                    RIBOAPTAMER_EXPECTED_TOTAL_ROWS
                    if args.expected_total_rows is None
                    else args.expected_total_rows
                ),
            )
        elif args.source == "aptaindex":
            result = prepare_aptaindex_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
                expected_active_rows=args.expected_active_rows,
                expected_total_rows=(
                    APTAINDEX_EXPECTED_TOTAL_ROWS
                    if args.expected_total_rows is None
                    else args.expected_total_rows
                ),
            )
        elif args.source == "ena":
            result = prepare_ena_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
                expected_active_rows=args.expected_active_rows,
                expected_total_rows=(
                    ENA_EXPECTED_TOTAL_ROWS
                    if args.expected_total_rows is None
                    else args.expected_total_rows
                ),
            )
        elif args.source == "aptamerbase":
            result = prepare_aptamerbase_checkpoint1_review(
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                output_dir=output_dir,
                expected_active_rows=args.expected_active_rows,
                expected_total_rows=(
                    APTAMERBASE_EXPECTED_TOTAL_ROWS
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
    except (
        Checkpoint1ReviewError,
        EnaCheckpoint1ReviewError,
        AptamerBaseCheckpoint1ReviewError,
        AptamerBaseCheckpoint1AuditError,
    ) as exc:
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
    if result.source_key == "utexas":
        batch_order = UTEXAS_BATCH_ORDER
    elif result.source_key == "aptadb":
        batch_order = APTADB_BATCH_ORDER
    elif result.source_key == "riboaptamer":
        batch_order = RIBOAPTAMER_BATCH_ORDER
    elif result.source_key == "aptaindex":
        batch_order = APTAINDEX_BATCH_ORDER
    elif result.source_key == "ena":
        batch_order = ENA_BATCH_ORDER
    elif result.source_key == "aptamerbase":
        batch_order = APTAMERBASE_BATCH_ORDER
    else:
        batch_order = BATCH_ORDER
    for batch in batch_order:
        print(f"{batch}={stats.batch_counts.get(batch, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
