"""AptamerBase S1 adapter: verbatim extraction into the canonical corpus schema.

Reads only the registry-bound flattened Freebase/RDF-style CSV. One physical
CSV row is not necessarily one biological aptamer. S1 retains every physical
row in source order, including duplicate Freebase IDs, duplicate complete
rows, structure-topic rows, blank sequences, and textual ``n/a`` sequences.
Does not classify molecules, convert T→U, parse ``label`` as a target,
interpret structure/evidence flags, trim, filter, or perform S2/S3/S4 work.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

import csv

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

APTAMERBASE_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "type",
    "id",
    "label",
    "sequence",
    "sequence_length",
    "has_mutational_analysis",
    "has_experimentally_determined_structure",
    "has_minimal_aptamer",
    "is_minimal_aptamer_of",
    "has_application",
    "has_modification_details",
    "has_secondary_structure",
    "has_predicted_secondary_structure",
    "has_sequence_pattern",
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamerbase_csv_data_row",
    "aptamerbase_type",
    "aptamerbase_id",
    "aptamerbase_label",
    "aptamerbase_sequence",
    "aptamerbase_sequence_length",
    "aptamerbase_has_mutational_analysis",
    "aptamerbase_has_experimentally_determined_structure",
    "aptamerbase_has_minimal_aptamer",
    "aptamerbase_is_minimal_aptamer_of",
    "aptamerbase_has_application",
    "aptamerbase_has_modification_details",
    "aptamerbase_has_secondary_structure",
    "aptamerbase_has_predicted_secondary_structure",
    "aptamerbase_has_sequence_pattern",
)

_SOURCE_TO_SIDECAR: Final[tuple[tuple[str, str], ...]] = (
    ("type", "aptamerbase_type"),
    ("id", "aptamerbase_id"),
    ("label", "aptamerbase_label"),
    ("sequence", "aptamerbase_sequence"),
    ("sequence_length", "aptamerbase_sequence_length"),
    ("has_mutational_analysis", "aptamerbase_has_mutational_analysis"),
    (
        "has_experimentally_determined_structure",
        "aptamerbase_has_experimentally_determined_structure",
    ),
    ("has_minimal_aptamer", "aptamerbase_has_minimal_aptamer"),
    ("is_minimal_aptamer_of", "aptamerbase_is_minimal_aptamer_of"),
    ("has_application", "aptamerbase_has_application"),
    ("has_modification_details", "aptamerbase_has_modification_details"),
    ("has_secondary_structure", "aptamerbase_has_secondary_structure"),
    (
        "has_predicted_secondary_structure",
        "aptamerbase_has_predicted_secondary_structure",
    ),
    ("has_sequence_pattern", "aptamerbase_has_sequence_pattern"),
)

SEQUENCE_NA_TOKEN: Final[str] = "n/a"

TYPE_APTAMER: Final[str] = "http://rdf.freebase.com/ns/base.aptamer.aptamer"
TYPE_SECONDARY_STRUCTURE: Final[str] = (
    "http://rdf.freebase.com/ns/base.aptamer.nucleic_acid_secondary_structure"
)
TYPE_PREDICTED_STRUCTURE: Final[str] = (
    "http://rdf.freebase.com/ns/base.aptamer.predicted_secondary_structure"
)

EXPECTED_INPUT_ROWS: Final[int] = 2128
EXPECTED_EMPTY_SEQUENCES: Final[int] = 179
EXPECTED_SEQUENCE_NA_TEXT: Final[int] = 4
EXPECTED_OTHER_NONEMPTY_SEQUENCES: Final[int] = 1945
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = (
    EXPECTED_SEQUENCE_NA_TEXT + EXPECTED_OTHER_NONEMPTY_SEQUENCES
)
EXPECTED_MISSING_SEQUENCES: Final[int] = EXPECTED_EMPTY_SEQUENCES
EXPECTED_NONEMPTY_TARGETS: Final[int] = 0
EXPECTED_UNIQUE_FREEBASE_IDS: Final[int] = 1868
EXPECTED_DUPLICATE_FREEBASE_ID_GROUPS: Final[int] = 66
EXPECTED_ROWS_IN_DUPLICATE_FREEBASE_ID_GROUPS: Final[int] = 326
EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS: Final[int] = 2
EXPECTED_ROWS_IN_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS: Final[int] = 6
EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_EXCESS: Final[int] = 4
EXPECTED_TYPE_APTAMER: Final[int] = 2056
EXPECTED_TYPE_SECONDARY_STRUCTURE: Final[int] = 69
EXPECTED_TYPE_PREDICTED_STRUCTURE: Final[int] = 3
EXPECTED_HAS_MINIMAL_APTAMER_NONEMPTY: Final[int] = 273
EXPECTED_IS_MINIMAL_APTAMER_OF_NONEMPTY: Final[int] = 266
EXPECTED_HAS_MUTATIONAL_ANALYSIS_TRUE: Final[int] = 168
EXPECTED_HAS_MUTATIONAL_ANALYSIS_FALSE: Final[int] = 1031
EXPECTED_HAS_MUTATIONAL_ANALYSIS_BLANK: Final[int] = 929
EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_TRUE: Final[int] = 185
EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_FALSE: Final[int] = 956
EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_BLANK: Final[int] = 987
EXPECTED_HAS_APPLICATION_NONEMPTY: Final[int] = 723
EXPECTED_HAS_MODIFICATION_DETAILS_NONEMPTY: Final[int] = 156
EXPECTED_HAS_SECONDARY_STRUCTURE_NONEMPTY: Final[int] = 889
EXPECTED_HAS_PREDICTED_SECONDARY_STRUCTURE_NONEMPTY: Final[int] = 815
EXPECTED_HAS_SEQUENCE_PATTERN_NONEMPTY: Final[int] = 249
EXPECTED_FIRST_NATIVE_ID: Final[str] = "0001"
EXPECTED_LAST_NATIVE_ID: Final[str] = "2128"

NATIVE_ID_WIDTH: Final[int] = 4
SOURCE_DB: Final[str] = "aptamerbase"


class AptamerBaseAdapterError(ValueError):
    """Hard failure while validating or extracting the AptamerBase source."""


@dataclass
class AptamerBaseExtractionStats:
    """Aggregate counts for the AptamerBase S1 report (no sequence values)."""

    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    empty_sequences: int = 0
    sequence_na_text: int = 0
    other_nonempty_sequences: int = 0
    nonempty_targets: int = 0
    missing_targets: int = 0
    nonempty_publication: int = 0
    nonempty_doi: int = 0
    nonempty_pmid: int = 0
    unique_freebase_ids: int = 0
    duplicate_freebase_id_groups: int = 0
    rows_in_duplicate_freebase_id_groups: int = 0
    exact_duplicate_complete_row_groups: int = 0
    rows_in_exact_duplicate_complete_row_groups: int = 0
    exact_duplicate_complete_row_excess: int = 0
    has_minimal_aptamer_nonempty: int = 0
    is_minimal_aptamer_of_nonempty: int = 0
    has_mutational_analysis_true: int = 0
    has_mutational_analysis_false: int = 0
    has_mutational_analysis_blank: int = 0
    has_experimentally_determined_structure_true: int = 0
    has_experimentally_determined_structure_false: int = 0
    has_experimentally_determined_structure_blank: int = 0
    has_application_nonempty: int = 0
    has_modification_details_nonempty: int = 0
    has_secondary_structure_nonempty: int = 0
    has_predicted_secondary_structure_nonempty: int = 0
    has_sequence_pattern_nonempty: int = 0
    first_native_id: str = ""
    last_native_id: str = ""
    sequence_exact_copy_ok: bool = False
    order_preserved: bool = False
    no_row_consolidation: bool = True
    type_counts: dict[str, int] = field(default_factory=dict)
    native_id_strategy: str = (
        "1-based CSV data-row number, zero-padded to 4 digits "
        "(source Freebase id retained only in sidecar)"
    )


@dataclass
class AptamerBaseExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: AptamerBaseExtractionStats = field(
        default_factory=AptamerBaseExtractionStats
    )


def format_native_id(csv_data_row: int, *, width: int = NATIVE_ID_WIDTH) -> str:
    """Format a 1-based CSV data-row number as the AptamerBase native_id."""
    if csv_data_row < 1:
        raise AptamerBaseAdapterError(
            f"csv_data_row must be a positive 1-based row number; got {csv_data_row}"
        )
    return f"{csv_data_row:0{width}d}"


def validate_aptamerbase_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise AptamerBaseAdapterError("AptamerBase input has no header row")

    actual = list(fieldnames)
    if any(not name.strip() for name in actual):
        raise AptamerBaseAdapterError("AptamerBase input has a blank header column")
    if len(actual) != len(set(actual)):
        raise AptamerBaseAdapterError("AptamerBase input has duplicate header columns")
    expected = list(APTAMERBASE_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise AptamerBaseAdapterError(
                "AptamerBase input columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise AptamerBaseAdapterError(
            "AptamerBase input columns are reordered relative to the required schema"
        )


def _coerce_source_row(row: Mapping[str, str | None], index: int) -> dict[str, str]:
    """Return a source row with every expected column present as a string."""
    coerced: dict[str, str] = {}
    for column in APTAMERBASE_INPUT_COLUMNS:
        value = row.get(column)
        if value is None:
            raise AptamerBaseAdapterError(
                f"AptamerBase row {index} missing column {column!r}"
            )
        coerced[column] = value
    return coerced


def read_aptamerbase_rows(path: Path) -> list[dict[str, str]]:
    """Read the AptamerBase CSV with exact schema and production row-count gates.

    Uses ``encoding=utf-8-sig`` and ``newline=''`` so a UTF-8 BOM, if present,
    is stripped from the header. Does not use pandas.
    """
    rows = _read_aptamerbase_rows_flexible(path)
    if len(rows) != EXPECTED_INPUT_ROWS:
        raise AptamerBaseAdapterError(
            f"AptamerBase input row count must be {EXPECTED_INPUT_ROWS}; "
            f"got {len(rows)}"
        )
    return rows


def _read_aptamerbase_rows_flexible(path: Path) -> list[dict[str, str]]:
    """Schema-validated read without the frozen 2128-row production check."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_aptamerbase_header(reader.fieldnames)
        raw_rows = list(reader)

    coerced: list[dict[str, str]] = []
    for index, row in enumerate(raw_rows, start=2):
        coerced.append(_coerce_source_row(row, index))
    return coerced


def map_aptamerbase_row(
    source_row: Mapping[str, str],
    *,
    csv_data_row: int,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one physical source row to canonical + sidecar records.

    ``csv_data_row`` is the 1-based data-row number in source order.
    Source Freebase ``id`` is never used as ``native_id``. Source ``label``
    is never copied into ``target_name_raw``.
    """
    native_id = format_native_id(csv_data_row)
    canonical_id = f"{SOURCE_DB}:{native_id}"
    sequence_raw = source_row["sequence"]

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
    record["target_name_raw"] = ""
    record["publication"] = ""
    record["doi"] = ""
    record["pubmed_id"] = ""
    record["notes"] = ""

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {
        "record_id": canonical_id,
        "native_id": native_id,
        "aptamerbase_csv_data_row": str(csv_data_row),
    }
    for source_col, sidecar_col in _SOURCE_TO_SIDECAR:
        sidecar[sidecar_col] = source_row[source_col]

    return validated, sidecar


def _truthy_blank_counts(values: Sequence[str]) -> tuple[int, int, int]:
    """Return (true, false, blank) counts for verbatim source tokens."""
    true_n = sum(1 for value in values if value == "true")
    false_n = sum(1 for value in values if value == "false")
    blank_n = sum(1 for value in values if value == "")
    return true_n, false_n, blank_n


def extract_aptamerbase(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = EXPECTED_INPUT_ROWS,
) -> AptamerBaseExtractionResult:
    """Extract all AptamerBase physical rows into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected`` for this input.
    When it equals the frozen production snapshot size (2128), known
    production audit counts are also enforced. Pass ``expected_rows=None``
    only in unit tests that intentionally skip the production row-count gate.
    """
    if expected_rows == EXPECTED_INPUT_ROWS:
        source_rows = read_aptamerbase_rows(input_path)
    else:
        source_rows = _read_aptamerbase_rows_flexible(input_path)

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = AptamerBaseExtractionStats()
    stats.input_rows = len(source_rows)
    stats.order_preserved = True
    stats.no_row_consolidation = True
    sequence_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []
    freebase_ids: list[str] = []
    type_values: list[str] = []
    complete_row_keys: list[tuple[str, ...]] = []
    mutational_values: list[str] = []
    experimental_structure_values: list[str] = []

    for csv_data_row, source_row in enumerate(source_rows, start=1):
        canonical, sidecar = map_aptamerbase_row(
            source_row,
            csv_data_row=csv_data_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        if canonical["sequence_raw"] != source_row["sequence"]:
            sequence_exact = False
        if sidecar["aptamerbase_sequence"] != source_row["sequence"]:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["aptamerbase_sequence"]:
            sequence_exact = False
        if canonical["target_name_raw"] != "":
            raise AptamerBaseAdapterError(
                "S1 must not populate target_name_raw from AptamerBase label"
            )

        sequence_raw = canonical["sequence_raw"]
        if sequence_raw == "":
            stats.empty_sequences += 1
            stats.missing_sequences += 1
        elif sequence_raw == SEQUENCE_NA_TOKEN:
            stats.sequence_na_text += 1
            stats.nonempty_sequences += 1
        else:
            stats.other_nonempty_sequences += 1
            stats.nonempty_sequences += 1

        stats.missing_targets += 1

        if canonical["publication"] != "":
            stats.nonempty_publication += 1
        if canonical["doi"] != "":
            stats.nonempty_doi += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1

        if source_row["has_minimal_aptamer"] != "":
            stats.has_minimal_aptamer_nonempty += 1
        if source_row["is_minimal_aptamer_of"] != "":
            stats.is_minimal_aptamer_of_nonempty += 1
        if source_row["has_application"] != "":
            stats.has_application_nonempty += 1
        if source_row["has_modification_details"] != "":
            stats.has_modification_details_nonempty += 1
        if source_row["has_secondary_structure"] != "":
            stats.has_secondary_structure_nonempty += 1
        if source_row["has_predicted_secondary_structure"] != "":
            stats.has_predicted_secondary_structure_nonempty += 1
        if source_row["has_sequence_pattern"] != "":
            stats.has_sequence_pattern_nonempty += 1

        mutational_values.append(source_row["has_mutational_analysis"])
        experimental_structure_values.append(
            source_row["has_experimentally_determined_structure"]
        )
        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        freebase_ids.append(source_row["id"])
        type_values.append(source_row["type"])
        complete_row_keys.append(
            tuple(source_row[column] for column in APTAMERBASE_INPUT_COLUMNS)
        )
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    id_counts = Counter(freebase_ids)
    duplicate_id_groups = {name: n for name, n in id_counts.items() if n > 1}
    complete_row_counts = Counter(complete_row_keys)
    duplicate_complete = {key: n for key, n in complete_row_counts.items() if n > 1}

    (
        stats.has_mutational_analysis_true,
        stats.has_mutational_analysis_false,
        stats.has_mutational_analysis_blank,
    ) = _truthy_blank_counts(mutational_values)
    (
        stats.has_experimentally_determined_structure_true,
        stats.has_experimentally_determined_structure_false,
        stats.has_experimentally_determined_structure_blank,
    ) = _truthy_blank_counts(experimental_structure_values)

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.unique_freebase_ids = len(id_counts)
    stats.duplicate_freebase_id_groups = len(duplicate_id_groups)
    stats.rows_in_duplicate_freebase_id_groups = sum(duplicate_id_groups.values())
    stats.exact_duplicate_complete_row_groups = len(duplicate_complete)
    stats.rows_in_exact_duplicate_complete_row_groups = sum(
        duplicate_complete.values()
    )
    stats.exact_duplicate_complete_row_excess = sum(
        n - 1 for n in duplicate_complete.values()
    )
    stats.first_native_id = native_ids[0] if native_ids else ""
    stats.last_native_id = native_ids[-1] if native_ids else ""
    stats.sequence_exact_copy_ok = sequence_exact
    stats.type_counts = dict(sorted(Counter(type_values).items()))
    stats.nonempty_targets = 0

    _assert_extraction_invariants(stats, expected_rows=expected_rows)

    return AptamerBaseExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: AptamerBaseExtractionStats,
    *,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise AptamerBaseAdapterError(
            f"input_rows must be {expected_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise AptamerBaseAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise AptamerBaseAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise AptamerBaseAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise AptamerBaseAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise AptamerBaseAdapterError("sequence_raw exact-copy validation failed")
    if not stats.order_preserved:
        raise AptamerBaseAdapterError("input order was not preserved")
    if not stats.no_row_consolidation:
        raise AptamerBaseAdapterError("S1 must not consolidate AptamerBase rows")
    if stats.nonempty_targets != 0:
        raise AptamerBaseAdapterError(
            "S1 must not populate target_name_raw for AptamerBase; "
            f"got {stats.nonempty_targets} nonempty values"
        )
    if stats.nonempty_publication != 0:
        raise AptamerBaseAdapterError(
            "S1 must not populate publication for AptamerBase; "
            f"got {stats.nonempty_publication} nonempty values"
        )
    if stats.nonempty_doi != 0:
        raise AptamerBaseAdapterError(
            "S1 must not invent doi values for AptamerBase; "
            f"got {stats.nonempty_doi} nonempty values"
        )
    if stats.nonempty_pmid != 0:
        raise AptamerBaseAdapterError(
            "S1 must not invent pubmed_id values for AptamerBase; "
            f"got {stats.nonempty_pmid} nonempty values"
        )
    if stats.empty_sequences + stats.sequence_na_text + stats.other_nonempty_sequences != n:
        raise AptamerBaseAdapterError(
            "sequence empty / n/a / other buckets must sum to input_rows"
        )
    if stats.missing_sequences != stats.empty_sequences:
        raise AptamerBaseAdapterError(
            "missing_sequences must equal empty-string sequence count"
        )
    if stats.nonempty_sequences != (
        stats.sequence_na_text + stats.other_nonempty_sequences
    ):
        raise AptamerBaseAdapterError(
            "nonempty_sequences must equal n/a plus other nonempty sequences"
        )

    if expected_rows == EXPECTED_INPUT_ROWS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise AptamerBaseAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise AptamerBaseAdapterError(
                f"empty sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )
        if stats.sequence_na_text != EXPECTED_SEQUENCE_NA_TEXT:
            raise AptamerBaseAdapterError(
                f"exact textual n/a sequences must be {EXPECTED_SEQUENCE_NA_TEXT}; "
                f"got {stats.sequence_na_text}"
            )
        if stats.other_nonempty_sequences != EXPECTED_OTHER_NONEMPTY_SEQUENCES:
            raise AptamerBaseAdapterError(
                "other nonempty sequences must be "
                f"{EXPECTED_OTHER_NONEMPTY_SEQUENCES}; "
                f"got {stats.other_nonempty_sequences}"
            )
        if stats.unique_freebase_ids != EXPECTED_UNIQUE_FREEBASE_IDS:
            raise AptamerBaseAdapterError(
                f"unique Freebase ids must be {EXPECTED_UNIQUE_FREEBASE_IDS}; "
                f"got {stats.unique_freebase_ids}"
            )
        if stats.duplicate_freebase_id_groups != EXPECTED_DUPLICATE_FREEBASE_ID_GROUPS:
            raise AptamerBaseAdapterError(
                "duplicated Freebase ID groups must be "
                f"{EXPECTED_DUPLICATE_FREEBASE_ID_GROUPS}; "
                f"got {stats.duplicate_freebase_id_groups}"
            )
        if (
            stats.rows_in_duplicate_freebase_id_groups
            != EXPECTED_ROWS_IN_DUPLICATE_FREEBASE_ID_GROUPS
        ):
            raise AptamerBaseAdapterError(
                "rows in duplicated Freebase ID groups must be "
                f"{EXPECTED_ROWS_IN_DUPLICATE_FREEBASE_ID_GROUPS}; "
                f"got {stats.rows_in_duplicate_freebase_id_groups}"
            )
        if (
            stats.exact_duplicate_complete_row_groups
            != EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS
        ):
            raise AptamerBaseAdapterError(
                "exact duplicate complete-row groups must be "
                f"{EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS}; "
                f"got {stats.exact_duplicate_complete_row_groups}"
            )
        if (
            stats.rows_in_exact_duplicate_complete_row_groups
            != EXPECTED_ROWS_IN_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS
        ):
            raise AptamerBaseAdapterError(
                "rows in exact duplicate complete-row groups must be "
                f"{EXPECTED_ROWS_IN_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS}; "
                f"got {stats.rows_in_exact_duplicate_complete_row_groups}"
            )
        if (
            stats.exact_duplicate_complete_row_excess
            != EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_EXCESS
        ):
            raise AptamerBaseAdapterError(
                "exact duplicate complete-row excess must be "
                f"{EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_EXCESS}; "
                f"got {stats.exact_duplicate_complete_row_excess}"
            )
        if stats.type_counts.get(TYPE_APTAMER, 0) != EXPECTED_TYPE_APTAMER:
            raise AptamerBaseAdapterError(
                f"aptamer-topic type rows must be {EXPECTED_TYPE_APTAMER}; "
                f"got {stats.type_counts.get(TYPE_APTAMER, 0)}"
            )
        if (
            stats.type_counts.get(TYPE_SECONDARY_STRUCTURE, 0)
            != EXPECTED_TYPE_SECONDARY_STRUCTURE
        ):
            raise AptamerBaseAdapterError(
                "secondary-structure topic rows must be "
                f"{EXPECTED_TYPE_SECONDARY_STRUCTURE}; "
                f"got {stats.type_counts.get(TYPE_SECONDARY_STRUCTURE, 0)}"
            )
        if (
            stats.type_counts.get(TYPE_PREDICTED_STRUCTURE, 0)
            != EXPECTED_TYPE_PREDICTED_STRUCTURE
        ):
            raise AptamerBaseAdapterError(
                "predicted-structure topic rows must be "
                f"{EXPECTED_TYPE_PREDICTED_STRUCTURE}; "
                f"got {stats.type_counts.get(TYPE_PREDICTED_STRUCTURE, 0)}"
            )
        if stats.has_minimal_aptamer_nonempty != EXPECTED_HAS_MINIMAL_APTAMER_NONEMPTY:
            raise AptamerBaseAdapterError(
                "nonempty has_minimal_aptamer rows must be "
                f"{EXPECTED_HAS_MINIMAL_APTAMER_NONEMPTY}; "
                f"got {stats.has_minimal_aptamer_nonempty}"
            )
        if (
            stats.is_minimal_aptamer_of_nonempty
            != EXPECTED_IS_MINIMAL_APTAMER_OF_NONEMPTY
        ):
            raise AptamerBaseAdapterError(
                "nonempty is_minimal_aptamer_of rows must be "
                f"{EXPECTED_IS_MINIMAL_APTAMER_OF_NONEMPTY}; "
                f"got {stats.is_minimal_aptamer_of_nonempty}"
            )
        if (
            stats.has_mutational_analysis_true
            != EXPECTED_HAS_MUTATIONAL_ANALYSIS_TRUE
        ):
            raise AptamerBaseAdapterError(
                "has_mutational_analysis=true must be "
                f"{EXPECTED_HAS_MUTATIONAL_ANALYSIS_TRUE}; "
                f"got {stats.has_mutational_analysis_true}"
            )
        if (
            stats.has_mutational_analysis_false
            != EXPECTED_HAS_MUTATIONAL_ANALYSIS_FALSE
        ):
            raise AptamerBaseAdapterError(
                "has_mutational_analysis=false must be "
                f"{EXPECTED_HAS_MUTATIONAL_ANALYSIS_FALSE}; "
                f"got {stats.has_mutational_analysis_false}"
            )
        if (
            stats.has_mutational_analysis_blank
            != EXPECTED_HAS_MUTATIONAL_ANALYSIS_BLANK
        ):
            raise AptamerBaseAdapterError(
                "has_mutational_analysis blank must be "
                f"{EXPECTED_HAS_MUTATIONAL_ANALYSIS_BLANK}; "
                f"got {stats.has_mutational_analysis_blank}"
            )
        if (
            stats.has_experimentally_determined_structure_true
            != EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_TRUE
        ):
            raise AptamerBaseAdapterError(
                "has_experimentally_determined_structure=true must be "
                f"{EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_TRUE}; "
                f"got {stats.has_experimentally_determined_structure_true}"
            )
        if (
            stats.has_experimentally_determined_structure_false
            != EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_FALSE
        ):
            raise AptamerBaseAdapterError(
                "has_experimentally_determined_structure=false must be "
                f"{EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_FALSE}; "
                f"got {stats.has_experimentally_determined_structure_false}"
            )
        if (
            stats.has_experimentally_determined_structure_blank
            != EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_BLANK
        ):
            raise AptamerBaseAdapterError(
                "has_experimentally_determined_structure blank must be "
                f"{EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_BLANK}; "
                f"got {stats.has_experimentally_determined_structure_blank}"
            )
        if stats.has_application_nonempty != EXPECTED_HAS_APPLICATION_NONEMPTY:
            raise AptamerBaseAdapterError(
                "nonempty has_application rows must be "
                f"{EXPECTED_HAS_APPLICATION_NONEMPTY}; "
                f"got {stats.has_application_nonempty}"
            )
        if (
            stats.has_modification_details_nonempty
            != EXPECTED_HAS_MODIFICATION_DETAILS_NONEMPTY
        ):
            raise AptamerBaseAdapterError(
                "nonempty has_modification_details rows must be "
                f"{EXPECTED_HAS_MODIFICATION_DETAILS_NONEMPTY}; "
                f"got {stats.has_modification_details_nonempty}"
            )
        if (
            stats.has_secondary_structure_nonempty
            != EXPECTED_HAS_SECONDARY_STRUCTURE_NONEMPTY
        ):
            raise AptamerBaseAdapterError(
                "nonempty has_secondary_structure rows must be "
                f"{EXPECTED_HAS_SECONDARY_STRUCTURE_NONEMPTY}; "
                f"got {stats.has_secondary_structure_nonempty}"
            )
        if (
            stats.has_predicted_secondary_structure_nonempty
            != EXPECTED_HAS_PREDICTED_SECONDARY_STRUCTURE_NONEMPTY
        ):
            raise AptamerBaseAdapterError(
                "nonempty has_predicted_secondary_structure rows must be "
                f"{EXPECTED_HAS_PREDICTED_SECONDARY_STRUCTURE_NONEMPTY}; "
                f"got {stats.has_predicted_secondary_structure_nonempty}"
            )
        if (
            stats.has_sequence_pattern_nonempty
            != EXPECTED_HAS_SEQUENCE_PATTERN_NONEMPTY
        ):
            raise AptamerBaseAdapterError(
                "nonempty has_sequence_pattern rows must be "
                f"{EXPECTED_HAS_SEQUENCE_PATTERN_NONEMPTY}; "
                f"got {stats.has_sequence_pattern_nonempty}"
            )
        if stats.first_native_id != EXPECTED_FIRST_NATIVE_ID:
            raise AptamerBaseAdapterError(
                f"first native_id must be {EXPECTED_FIRST_NATIVE_ID!r}; "
                f"got {stats.first_native_id!r}"
            )
        if stats.last_native_id != EXPECTED_LAST_NATIVE_ID:
            raise AptamerBaseAdapterError(
                f"last native_id must be {EXPECTED_LAST_NATIVE_ID!r}; "
                f"got {stats.last_native_id!r}"
            )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the AptamerBase source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)
