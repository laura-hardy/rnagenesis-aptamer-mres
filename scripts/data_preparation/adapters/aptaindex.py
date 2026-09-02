"""AptaIndex S1 adapter: verbatim extraction into the canonical corpus schema.

Reads only the registry-bound 22 July 2026 CSV export. Does not parse
chemical sequence notation, infer molecule type or chemistry, classify
targets, normalise affinity, or perform S2/S3/S4 work.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

APTAINDEX_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Title",
    "Type",
    "Target",
    "Affinity Type",
    "Affinity",
    "Affinity Units",
    "Refolding Protocol",
    "Binding Conditions",
    "Temp",
    "Sequence",
    "Molecular Weight",
    "Comments",
    "Reference",
    "Target Type",
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "aptaindex_native_id",
    "aptaindex_csv_data_row",
    "aptaindex_title",
    "aptaindex_type",
    "aptaindex_target",
    "aptaindex_affinity_type",
    "aptaindex_affinity",
    "aptaindex_affinity_units",
    "aptaindex_refolding_protocol",
    "aptaindex_binding_conditions",
    "aptaindex_temp",
    "aptaindex_sequence",
    "aptaindex_molecular_weight",
    "aptaindex_comments",
    "aptaindex_reference",
    "aptaindex_target_type",
)

_SOURCE_TO_SIDECAR: Final[tuple[tuple[str, str], ...]] = (
    ("Title", "aptaindex_title"),
    ("Type", "aptaindex_type"),
    ("Target", "aptaindex_target"),
    ("Affinity Type", "aptaindex_affinity_type"),
    ("Affinity", "aptaindex_affinity"),
    ("Affinity Units", "aptaindex_affinity_units"),
    ("Refolding Protocol", "aptaindex_refolding_protocol"),
    ("Binding Conditions", "aptaindex_binding_conditions"),
    ("Temp", "aptaindex_temp"),
    ("Sequence", "aptaindex_sequence"),
    ("Molecular Weight", "aptaindex_molecular_weight"),
    ("Comments", "aptaindex_comments"),
    ("Reference", "aptaindex_reference"),
    ("Target Type", "aptaindex_target_type"),
)

EXPECTED_INPUT_ROWS: Final[int] = 1050
EXPECTED_MISSING_SEQUENCES: Final[int] = 31
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = 1019
EXPECTED_MISSING_TARGETS: Final[int] = 28
EXPECTED_NONEMPTY_TARGETS: Final[int] = 1022
EXPECTED_NONEMPTY_PUBLICATION: Final[int] = 1013
EXPECTED_UNIQUE_TITLES: Final[int] = 1023
EXPECTED_DUPLICATE_TITLE_KEYS: Final[int] = 21
EXPECTED_ROWS_IN_DUPLICATE_TITLE_GROUPS: Final[int] = 48
EXPECTED_FIRST_NATIVE_ID: Final[str] = "0001"
EXPECTED_LAST_NATIVE_ID: Final[str] = "1050"

NATIVE_ID_WIDTH: Final[int] = 4
SOURCE_DB: Final[str] = "aptaindex"


class AptaIndexAdapterError(ValueError):
    """Hard failure while validating or extracting the AptaIndex source."""


@dataclass
class AptaIndexExtractionStats:
    """Aggregate counts for the AptaIndex S1 report (no sequence values)."""

    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    nonempty_targets: int = 0
    missing_targets: int = 0
    nonempty_publication: int = 0
    nonempty_doi: int = 0
    nonempty_pmid: int = 0
    unique_titles: int = 0
    duplicate_title_keys: int = 0
    rows_in_duplicate_title_groups: int = 0
    first_native_id: str = ""
    last_native_id: str = ""
    sequence_exact_copy_ok: bool = False
    target_exact_copy_ok: bool = False
    order_preserved: bool = False
    type_counts: dict[str, int] = field(default_factory=dict)
    native_id_strategy: str = (
        "1-based CSV data-row number, zero-padded to 4 digits "
        "(Title retained only in sidecar)"
    )


@dataclass
class AptaIndexExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: AptaIndexExtractionStats = field(
        default_factory=AptaIndexExtractionStats
    )


def format_native_id(csv_data_row: int, *, width: int = NATIVE_ID_WIDTH) -> str:
    """Format a 1-based CSV data-row number as the AptaIndex native_id."""
    if csv_data_row < 1:
        raise AptaIndexAdapterError(
            f"csv_data_row must be a positive 1-based row number; got {csv_data_row}"
        )
    return f"{csv_data_row:0{width}d}"


def validate_aptaindex_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise AptaIndexAdapterError("AptaIndex input has no header row")

    actual = list(fieldnames)
    if any(not name.strip() for name in actual):
        raise AptaIndexAdapterError("AptaIndex input has a blank header column")
    if len(actual) != len(set(actual)):
        raise AptaIndexAdapterError("AptaIndex input has duplicate header columns")
    expected = list(APTAINDEX_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise AptaIndexAdapterError(
                "AptaIndex input columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise AptaIndexAdapterError(
            "AptaIndex input columns are reordered relative to the required schema"
        )


def _coerce_source_row(row: Mapping[str, str | None], index: int) -> dict[str, str]:
    """Return a source row with every expected column present as a string."""
    coerced: dict[str, str] = {}
    for column in APTAINDEX_INPUT_COLUMNS:
        value = row.get(column)
        if value is None:
            raise AptaIndexAdapterError(
                f"AptaIndex row {index} missing column {column!r}"
            )
        coerced[column] = value
    return coerced


def read_aptaindex_rows(path: Path) -> list[dict[str, str]]:
    """Read the AptaIndex CSV with exact schema and production row-count gates.

    Uses ``encoding=utf-8-sig`` and ``newline=''`` so a UTF-8 BOM is stripped
    from the header and quoted embedded CR characters stay inside fields.
    Does not use pandas or ``splitlines()`` as a record counter.
    """
    rows = _read_aptaindex_rows_flexible(path)
    if len(rows) != EXPECTED_INPUT_ROWS:
        raise AptaIndexAdapterError(
            f"AptaIndex input row count must be {EXPECTED_INPUT_ROWS}; "
            f"got {len(rows)}"
        )
    return rows


def _read_aptaindex_rows_flexible(path: Path) -> list[dict[str, str]]:
    """Schema-validated read without the frozen 1050-row production check."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_aptaindex_header(reader.fieldnames)
        raw_rows = list(reader)

    coerced: list[dict[str, str]] = []
    for index, row in enumerate(raw_rows, start=2):
        coerced.append(_coerce_source_row(row, index))
    return coerced


def map_aptaindex_row(
    source_row: Mapping[str, str],
    *,
    csv_data_row: int,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one source row to canonical + sidecar records.

    ``csv_data_row`` is the 1-based data-row number in source order.
    ``Title`` is never used as ``native_id``. Chemical notation in
    ``Sequence`` is copied verbatim and is not parsed.
    """
    native_id = format_native_id(csv_data_row)
    canonical_id = f"{SOURCE_DB}:{native_id}"
    sequence_raw = source_row["Sequence"]
    target_name_raw = source_row["Target"]

    record = empty_corpus_record()
    record["record_id"] = canonical_id
    record["sequence_raw"] = sequence_raw
    record["source_db"] = SOURCE_DB
    record["source_dataset"] = source_dataset
    record["contributing_sources"] = SOURCE_DB
    record["contributing_datasets"] = source_dataset
    record["corroboration_count"] = "1"
    record["redistribution_status"] = redistribution_status
    record["independently_attested_by_permissive_source"] = "false"
    record["native_id"] = native_id
    record["target_name_raw"] = target_name_raw
    # Reference is a mixed citation string, analogous to AptaBase
    # ``reference`` / UTexas ``Citation``. Copy it into publication only.
    # There is no dedicated DOI/PMID column; those stay empty rather than
    # inventing an AptaIndex-specific citation parser at S1.
    record["publication"] = source_row["Reference"]
    record["doi"] = ""
    record["pubmed_id"] = ""
    record["notes"] = ""

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {
        "record_id": canonical_id,
        "aptaindex_native_id": native_id,
        "aptaindex_csv_data_row": str(csv_data_row),
    }
    for source_col, sidecar_col in _SOURCE_TO_SIDECAR:
        sidecar[sidecar_col] = source_row[source_col]

    return validated, sidecar


def extract_aptaindex(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = EXPECTED_INPUT_ROWS,
) -> AptaIndexExtractionResult:
    """Extract all AptaIndex rows into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected`` for this input.
    When it equals the frozen production snapshot size (1050), known
    production audit counts are also enforced. Pass ``expected_rows=None``
    only in unit tests that intentionally skip the production row-count gate.
    """
    if expected_rows == EXPECTED_INPUT_ROWS:
        source_rows = read_aptaindex_rows(input_path)
    else:
        source_rows = _read_aptaindex_rows_flexible(input_path)

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = AptaIndexExtractionStats()
    stats.input_rows = len(source_rows)
    stats.order_preserved = True
    sequence_exact = True
    target_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []
    titles: list[str] = []
    type_values: list[str] = []

    for csv_data_row, source_row in enumerate(source_rows, start=1):
        canonical, sidecar = map_aptaindex_row(
            source_row,
            csv_data_row=csv_data_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        if canonical["sequence_raw"] != source_row["Sequence"]:
            sequence_exact = False
        if sidecar["aptaindex_sequence"] != source_row["Sequence"]:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["aptaindex_sequence"]:
            sequence_exact = False

        if canonical["target_name_raw"] != source_row["Target"]:
            target_exact = False
        if sidecar["aptaindex_target"] != source_row["Target"]:
            target_exact = False
        if canonical["target_name_raw"] != sidecar["aptaindex_target"]:
            target_exact = False

        if canonical["sequence_raw"] == "":
            stats.missing_sequences += 1
        else:
            stats.nonempty_sequences += 1

        if canonical["target_name_raw"] == "":
            stats.missing_targets += 1
        else:
            stats.nonempty_targets += 1

        if canonical["publication"] != "":
            stats.nonempty_publication += 1
        if canonical["doi"] != "":
            stats.nonempty_doi += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1

        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        titles.append(source_row["Title"])
        type_values.append(source_row["Type"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    title_counts = Counter(titles)
    duplicate_keys = {name: n for name, n in title_counts.items() if n > 1}

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.unique_titles = len(title_counts)
    stats.duplicate_title_keys = len(duplicate_keys)
    stats.rows_in_duplicate_title_groups = sum(duplicate_keys.values())
    stats.first_native_id = native_ids[0] if native_ids else ""
    stats.last_native_id = native_ids[-1] if native_ids else ""
    stats.sequence_exact_copy_ok = sequence_exact
    stats.target_exact_copy_ok = target_exact
    stats.type_counts = dict(sorted(Counter(type_values).items()))

    _assert_extraction_invariants(stats, expected_rows=expected_rows)

    return AptaIndexExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: AptaIndexExtractionStats,
    *,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise AptaIndexAdapterError(
            f"input_rows must be {expected_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise AptaIndexAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise AptaIndexAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise AptaIndexAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise AptaIndexAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise AptaIndexAdapterError("sequence_raw exact-copy validation failed")
    if not stats.target_exact_copy_ok:
        raise AptaIndexAdapterError("target_name_raw exact-copy validation failed")
    if not stats.order_preserved:
        raise AptaIndexAdapterError("input order was not preserved")
    if stats.nonempty_doi != 0:
        raise AptaIndexAdapterError(
            "S1 must not invent doi values for AptaIndex; "
            f"got {stats.nonempty_doi} nonempty values"
        )
    if stats.nonempty_pmid != 0:
        raise AptaIndexAdapterError(
            "S1 must not invent pubmed_id values for AptaIndex; "
            f"got {stats.nonempty_pmid} nonempty values"
        )

    if expected_rows == EXPECTED_INPUT_ROWS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise AptaIndexAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise AptaIndexAdapterError(
                f"missing sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )
        if stats.nonempty_targets != EXPECTED_NONEMPTY_TARGETS:
            raise AptaIndexAdapterError(
                f"nonempty target_name_raw must be {EXPECTED_NONEMPTY_TARGETS}; "
                f"got {stats.nonempty_targets}"
            )
        if stats.missing_targets != EXPECTED_MISSING_TARGETS:
            raise AptaIndexAdapterError(
                f"missing target_name_raw must be {EXPECTED_MISSING_TARGETS}; "
                f"got {stats.missing_targets}"
            )
        if stats.nonempty_publication != EXPECTED_NONEMPTY_PUBLICATION:
            raise AptaIndexAdapterError(
                f"nonempty publication must be {EXPECTED_NONEMPTY_PUBLICATION}; "
                f"got {stats.nonempty_publication}"
            )
        if stats.unique_titles != EXPECTED_UNIQUE_TITLES:
            raise AptaIndexAdapterError(
                f"unique Title values must be {EXPECTED_UNIQUE_TITLES}; "
                f"got {stats.unique_titles}"
            )
        if stats.duplicate_title_keys != EXPECTED_DUPLICATE_TITLE_KEYS:
            raise AptaIndexAdapterError(
                "duplicate Title keys must be "
                f"{EXPECTED_DUPLICATE_TITLE_KEYS}; "
                f"got {stats.duplicate_title_keys}"
            )
        if (
            stats.rows_in_duplicate_title_groups
            != EXPECTED_ROWS_IN_DUPLICATE_TITLE_GROUPS
        ):
            raise AptaIndexAdapterError(
                "rows in duplicated Title groups must be "
                f"{EXPECTED_ROWS_IN_DUPLICATE_TITLE_GROUPS}; "
                f"got {stats.rows_in_duplicate_title_groups}"
            )
        if stats.first_native_id != EXPECTED_FIRST_NATIVE_ID:
            raise AptaIndexAdapterError(
                f"first native_id must be {EXPECTED_FIRST_NATIVE_ID!r}; "
                f"got {stats.first_native_id!r}"
            )
        if stats.last_native_id != EXPECTED_LAST_NATIVE_ID:
            raise AptaIndexAdapterError(
                f"last native_id must be {EXPECTED_LAST_NATIVE_ID!r}; "
                f"got {stats.last_native_id!r}"
            )


def write_canonical_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write AptaIndex canonical S1 rows.

    Uses ``QUOTE_ALL`` so embedded CR characters in verbatim source fields
    remain inside quoted fields and do not split logical rows.
    """
    write_corpus_csv_atomic(path, rows, quoting=csv.QUOTE_ALL)


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the AptaIndex source-metadata sidecar.

    Uses ``QUOTE_ALL`` so embedded CR characters in source metadata remain
    inside quoted fields and do not split logical rows.
    """
    write_corpus_csv_atomic(
        path, rows, columns=SIDECAR_COLUMNS, quoting=csv.QUOTE_ALL
    )
