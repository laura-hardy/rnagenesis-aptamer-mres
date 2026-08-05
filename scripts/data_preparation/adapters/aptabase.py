"""AptaBase S1 adapter: verbatim extraction into the canonical corpus schema.

Reads only the registry-bound cleaned scrape. Does not import the legacy
scraper or cleaner. Does not perform S2 normalisation, filtering, trimming,
molecule inference, affinity interpretation, or deduplication.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
)

APTABASE_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "aptamer_name",
    "target_general",
    "target_specific",
    "reported_length",
    "affinity_raw",
    "affinity_measurement_type",
    "affinity_relation",
    "affinity_value",
    "affinity_uncertainty",
    "affinity_lower",
    "affinity_upper",
    "affinity_unit",
    "affinity_molar",
    "buffer",
    "gc_content_raw",
    "gc_content_reported",
    "gc_content_calculated",
    "gc_content_difference",
    "sequence_raw",
    "sequence_clean",
    "sequence_length_calculated",
    "sequence_alphabet",
    "molecule_type_inferred",
    "sequence_normalization_status",
    "reference",
    "doi",
    "pmid",
    "duplicate_group",
    "record_validity",
    "source_page",
    "source_url",
    "parse_warnings",
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "aptabase_record_id",
    "aptabase_aptamer_name",
    "aptabase_target_general",
    "aptabase_target_specific",
    "aptabase_reported_length",
    "aptabase_affinity_raw",
    "aptabase_affinity_measurement_type",
    "aptabase_affinity_relation",
    "aptabase_affinity_value",
    "aptabase_affinity_uncertainty",
    "aptabase_affinity_lower",
    "aptabase_affinity_upper",
    "aptabase_affinity_unit",
    "aptabase_affinity_molar",
    "aptabase_buffer",
    "aptabase_gc_content_raw",
    "aptabase_gc_content_reported",
    "aptabase_gc_content_calculated",
    "aptabase_gc_content_difference",
    "aptabase_sequence_raw",
    "aptabase_sequence_clean",
    "aptabase_sequence_length_calculated",
    "aptabase_sequence_alphabet",
    "aptabase_molecule_type_inferred",
    "aptabase_sequence_normalization_status",
    "aptabase_reference",
    "aptabase_doi",
    "aptabase_pmid",
    "aptabase_duplicate_group",
    "aptabase_record_validity",
    "aptabase_source_page",
    "aptabase_source_url",
    "aptabase_parse_warnings",
)

# Map each source column (except record_id) to its sidecar column name.
_SOURCE_TO_SIDECAR: Final[tuple[tuple[str, str], ...]] = tuple(
    (col, f"aptabase_{col}") for col in APTABASE_INPUT_COLUMNS
)

_NON_SUBSTANTIVE_TARGETS: Final[frozenset[str]] = frozenset(
    {"", "NA", "N/A", "NULL", "NONE"}
)

EXPECTED_INPUT_ROWS: Final[int] = 610
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = 556
EXPECTED_MISSING_SEQUENCES: Final[int] = 54


class AptaBaseAdapterError(ValueError):
    """Hard failure while validating or extracting the AptaBase source."""


@dataclass
class AptaBaseExtractionStats:
    """Aggregate counts for the AptaBase S1 report (no sequence values)."""

    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    target_specific_used: int = 0
    target_general_fallback: int = 0
    target_empty: int = 0
    nonempty_publication: int = 0
    nonempty_doi: int = 0
    nonempty_pmid: int = 0
    rows_with_parse_warnings: int = 0
    rows_with_duplicate_group: int = 0
    sequence_exact_copy_ok: bool = False
    order_preserved: bool = False


@dataclass
class AptaBaseExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: AptaBaseExtractionStats = field(default_factory=AptaBaseExtractionStats)


def _is_substantive_target(value: str) -> bool:
    return value.strip().upper() not in _NON_SUBSTANTIVE_TARGETS


def select_target_name_raw(
    target_specific: str,
    target_general: str,
) -> tuple[str, str]:
    """Choose target_name_raw and return ``(value, source_tag)``.

    ``source_tag`` is one of ``specific``, ``general``, or ``empty``.
    The returned value is an exact copy of the selected source string.
    """
    if _is_substantive_target(target_specific):
        return target_specific, "specific"
    if _is_substantive_target(target_general):
        return target_general, "general"
    return "", "empty"


def encode_aptamer_name_notes(aptamer_name: str) -> str:
    """Encode a nonempty aptamer name as deterministic JSON for ``notes``."""
    if aptamer_name == "":
        return ""
    return json.dumps(
        {"aptamer_name": aptamer_name},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def validate_aptabase_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise AptaBaseAdapterError("AptaBase input has no header row")

    actual = list(fieldnames)
    if any(not name.strip() for name in actual):
        raise AptaBaseAdapterError("AptaBase input has a blank header column")
    if len(actual) != len(set(actual)):
        raise AptaBaseAdapterError("AptaBase input has duplicate header columns")
    expected = list(APTABASE_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise AptaBaseAdapterError(
                "AptaBase input columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise AptaBaseAdapterError(
            "AptaBase input columns are reordered relative to the required schema"
        )


def read_aptabase_rows(path: Path) -> list[dict[str, str]]:
    """Read the AptaBase cleaned CSV with exact schema validation.

    Uses ``encoding=utf-8-sig`` and ``newline=''`` so quoted embedded newlines
    are parsed correctly. Does not use pandas.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_aptabase_header(reader.fieldnames)
        rows = list(reader)

    if len(rows) != EXPECTED_INPUT_ROWS:
        raise AptaBaseAdapterError(
            f"AptaBase input row count must be {EXPECTED_INPUT_ROWS}; "
            f"got {len(rows)}"
        )

    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        native_id = row.get("record_id")
        if native_id is None:
            raise AptaBaseAdapterError(
                f"AptaBase row {index} is missing record_id"
            )
        # DictReader may omit keys only if headers are wrong; still guard blanks.
        if native_id == "":
            raise AptaBaseAdapterError(
                f"AptaBase row {index} has a blank record_id"
            )
        if native_id in seen_ids:
            raise AptaBaseAdapterError(
                f"Duplicate AptaBase source record_id: {native_id!r}"
            )
        seen_ids.add(native_id)
        # Ensure every expected column is present as a string (DictReader
        # returns None for missing fields when restkeys differ).
        for column in APTABASE_INPUT_COLUMNS:
            value = row.get(column)
            if value is None:
                raise AptaBaseAdapterError(
                    f"AptaBase row {index} missing column {column!r}"
                )
            row[column] = value

    return rows


def map_aptabase_row(
    source_row: Mapping[str, str],
    *,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str], str]:
    """Map one source row to canonical + sidecar records.

    Returns ``(canonical, sidecar, target_source_tag)``.
    """
    native_id = source_row["record_id"]
    canonical_id = f"aptabase:{native_id}"
    sequence_raw = source_row["sequence_raw"]
    target_value, target_tag = select_target_name_raw(
        source_row["target_specific"],
        source_row["target_general"],
    )

    record = empty_corpus_record()
    record["record_id"] = canonical_id
    record["sequence_raw"] = sequence_raw
    record["source_db"] = "aptabase"
    record["source_dataset"] = source_dataset
    record["contributing_sources"] = "aptabase"
    record["contributing_datasets"] = source_dataset
    record["corroboration_count"] = "1"
    record["redistribution_status"] = redistribution_status
    record["independently_attested_by_permissive_source"] = "false"
    record["native_id"] = native_id
    record["target_name_raw"] = target_value
    record["publication"] = source_row["reference"]
    record["doi"] = source_row["doi"]
    record["pubmed_id"] = source_row["pmid"]
    record["notes"] = encode_aptamer_name_notes(source_row["aptamer_name"])

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {"record_id": canonical_id}
    for source_col, sidecar_col in _SOURCE_TO_SIDECAR:
        sidecar[sidecar_col] = source_row[source_col]

    return validated, sidecar, target_tag


def extract_aptabase(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = EXPECTED_INPUT_ROWS,
) -> AptaBaseExtractionResult:
    """Extract all AptaBase rows into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected`` for this input.
    When it equals the frozen production snapshot size (610), the known
    nonempty/missing sequence audit counts are also enforced. Pass
    ``expected_rows=None`` only in unit tests that intentionally skip the
    production row-count gate inside ``read_aptabase_rows``.
    """
    if expected_rows == EXPECTED_INPUT_ROWS:
        source_rows = read_aptabase_rows(input_path)
    else:
        source_rows = _read_aptabase_rows_flexible(input_path)

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = AptaBaseExtractionStats()
    stats.input_rows = len(source_rows)
    stats.order_preserved = True
    sequence_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []

    for source_row in source_rows:
        canonical, sidecar, target_tag = map_aptabase_row(
            source_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        if canonical["sequence_raw"] != source_row["sequence_raw"]:
            sequence_exact = False
        if sidecar["aptabase_sequence_raw"] != source_row["sequence_raw"]:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["aptabase_sequence_raw"]:
            sequence_exact = False

        if canonical["sequence_raw"] == "":
            stats.missing_sequences += 1
        else:
            stats.nonempty_sequences += 1

        if target_tag == "specific":
            stats.target_specific_used += 1
        elif target_tag == "general":
            stats.target_general_fallback += 1
        else:
            stats.target_empty += 1

        if canonical["publication"] != "":
            stats.nonempty_publication += 1
        if canonical["doi"] != "":
            stats.nonempty_doi += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1
        if source_row["parse_warnings"] != "":
            stats.rows_with_parse_warnings += 1
        if source_row["duplicate_group"] != "":
            stats.rows_with_duplicate_group += 1

        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.sequence_exact_copy_ok = sequence_exact

    _assert_extraction_invariants(stats, expected_rows=expected_rows)

    return AptaBaseExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _read_aptabase_rows_flexible(path: Path) -> list[dict[str, str]]:
    """Schema-validated read without the frozen 610-row production check."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_aptabase_header(reader.fieldnames)
        rows = list(reader)

    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        native_id = row.get("record_id")
        if native_id is None or native_id == "":
            raise AptaBaseAdapterError(
                f"AptaBase row {index} has a missing or blank record_id"
            )
        if native_id in seen_ids:
            raise AptaBaseAdapterError(
                f"Duplicate AptaBase source record_id: {native_id!r}"
            )
        seen_ids.add(native_id)
        for column in APTABASE_INPUT_COLUMNS:
            value = row.get(column)
            if value is None:
                raise AptaBaseAdapterError(
                    f"AptaBase row {index} missing column {column!r}"
                )
            row[column] = value
    return rows


def _assert_extraction_invariants(
    stats: AptaBaseExtractionStats,
    *,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise AptaBaseAdapterError(
            f"input_rows must be {expected_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise AptaBaseAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise AptaBaseAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise AptaBaseAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise AptaBaseAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise AptaBaseAdapterError(
            "sequence_raw exact-copy validation failed"
        )
    if not stats.order_preserved:
        raise AptaBaseAdapterError("input order was not preserved")

    if expected_rows == EXPECTED_INPUT_ROWS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise AptaBaseAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise AptaBaseAdapterError(
                f"missing sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the AptaBase source-metadata sidecar."""
    from common.corpus_schema import write_corpus_csv_atomic

    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)
