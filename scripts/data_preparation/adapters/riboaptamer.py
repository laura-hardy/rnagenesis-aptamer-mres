"""RiboAptamer S1 adapter: verbatim extraction into the canonical corpus schema.

Reads only the registry-bound corrected 509-row CSV. Does not perform S2
normalisation, filtering, trimming, molecule inference, target extraction,
affinity interpretation, or deduplication.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

RIBOAPTAMER_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Sequence Name",
    "Aptamer Name",
    "Category",
    "Type",
    "Article name",
    "Sequence",
    "Length",
    "GC Content",
    "Discovery Year",
    "Affinity (Kd)",
    "Description",
    "PubMed Link",
    "mmCIF Download URL",
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "riboaptamer_native_id",
    "riboaptamer_csv_data_row",
    "riboaptamer_sequence_name",
    "riboaptamer_aptamer_name",
    "riboaptamer_category",
    "riboaptamer_type",
    "riboaptamer_article_name",
    "riboaptamer_sequence",
    "riboaptamer_length",
    "riboaptamer_gc_content",
    "riboaptamer_discovery_year",
    "riboaptamer_affinity_kd",
    "riboaptamer_description",
    "riboaptamer_pubmed_link",
    "riboaptamer_mmcif_download_url",
)

_SOURCE_TO_SIDECAR: Final[tuple[tuple[str, str], ...]] = (
    ("Sequence Name", "riboaptamer_sequence_name"),
    ("Aptamer Name", "riboaptamer_aptamer_name"),
    ("Category", "riboaptamer_category"),
    ("Type", "riboaptamer_type"),
    ("Article name", "riboaptamer_article_name"),
    ("Sequence", "riboaptamer_sequence"),
    ("Length", "riboaptamer_length"),
    ("GC Content", "riboaptamer_gc_content"),
    ("Discovery Year", "riboaptamer_discovery_year"),
    ("Affinity (Kd)", "riboaptamer_affinity_kd"),
    ("Description", "riboaptamer_description"),
    ("PubMed Link", "riboaptamer_pubmed_link"),
    ("mmCIF Download URL", "riboaptamer_mmcif_download_url"),
)

EXPECTED_INPUT_ROWS: Final[int] = 509
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = 509
EXPECTED_MISSING_SEQUENCES: Final[int] = 0
EXPECTED_EMPTY_TARGET_NAME_RAW: Final[int] = 509
EXPECTED_NONEMPTY_PMID: Final[int] = 505
EXPECTED_UNIQUE_SEQUENCE_NAMES: Final[int] = 506
EXPECTED_DUPLICATE_SEQUENCE_NAME_KEYS: Final[int] = 3
EXPECTED_ROWS_IN_DUPLICATE_SEQUENCE_NAME_GROUPS: Final[int] = 6
EXPECTED_FIRST_NATIVE_ID: Final[str] = "001"
EXPECTED_LAST_NATIVE_ID: Final[str] = "509"

NATIVE_ID_WIDTH: Final[int] = 3
SOURCE_DB: Final[str] = "riboaptamer"

# Format parsing only: numeric PMID from an unambiguous PubMed URL or a
# bare numeric token. Non-PubMed citation URLs are not converted to DOI.
_PMID_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?pubmed\.ncbi\.nlm\.nih\.gov/(?:pubmed/)?"
    r"(?P<pmid>\d+)\b"
)
_PMID_BARE_RE: Final[re.Pattern[str]] = re.compile(r"^\d{1,9}$")


class RiboAptamerAdapterError(ValueError):
    """Hard failure while validating or extracting the RiboAptamer source."""


@dataclass
class RiboAptamerExtractionStats:
    """Aggregate counts for the RiboAptamer S1 report (no sequence values)."""

    input_rows: int = 0
    canonical_rows: int = 0
    sidecar_rows: int = 0
    unique_native_ids: int = 0
    unique_record_ids: int = 0
    nonempty_sequences: int = 0
    missing_sequences: int = 0
    empty_target_name_raw: int = 0
    nonempty_target_name_raw: int = 0
    nonempty_publication: int = 0
    nonempty_doi: int = 0
    nonempty_pmid: int = 0
    unique_sequence_names: int = 0
    duplicate_sequence_name_keys: int = 0
    rows_in_duplicate_sequence_name_groups: int = 0
    first_native_id: str = ""
    last_native_id: str = ""
    sequence_exact_copy_ok: bool = False
    order_preserved: bool = False
    native_id_strategy: str = (
        "1-based CSV data-row number, zero-padded to 3 digits "
        "(Sequence Name retained only in sidecar)"
    )


@dataclass
class RiboAptamerExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: RiboAptamerExtractionStats = field(
        default_factory=RiboAptamerExtractionStats
    )


def format_native_id(csv_data_row: int, *, width: int = NATIVE_ID_WIDTH) -> str:
    """Format a 1-based CSV data-row number as the RiboAptamer native_id."""
    if csv_data_row < 1:
        raise RiboAptamerAdapterError(
            f"csv_data_row must be a positive 1-based row number; got {csv_data_row}"
        )
    return f"{csv_data_row:0{width}d}"


def encode_category_prior_notes(category: str) -> str:
    """Encode a nonempty Category value as structured S1 notes provenance."""
    if category == "":
        return ""
    return json.dumps(
        {"category_prior": category},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def extract_pubmed_id(raw_value: str) -> str:
    """Return a numeric PMID when the source string is an unambiguous PubMed ID.

    Accepts a PubMed URL or a bare numeric token. Otherwise returns ``\"\"``.
    Does not invent DOI values from arbitrary external URLs.
    """
    if raw_value == "":
        return ""
    stripped = raw_value.strip()
    if _PMID_BARE_RE.fullmatch(stripped):
        return stripped
    match = _PMID_URL_RE.search(raw_value)
    if match is not None:
        return match.group("pmid")
    return ""


def validate_riboaptamer_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise RiboAptamerAdapterError("RiboAptamer input has no header row")

    actual = list(fieldnames)
    if any(not name.strip() for name in actual):
        raise RiboAptamerAdapterError("RiboAptamer input has a blank header column")
    if len(actual) != len(set(actual)):
        raise RiboAptamerAdapterError(
            "RiboAptamer input has duplicate header columns"
        )
    expected = list(RIBOAPTAMER_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise RiboAptamerAdapterError(
                "RiboAptamer input columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise RiboAptamerAdapterError(
            "RiboAptamer input columns are reordered relative to the required schema"
        )


def _coerce_source_row(row: Mapping[str, str | None], index: int) -> dict[str, str]:
    """Return a source row with every expected column present as a string."""
    coerced: dict[str, str] = {}
    for column in RIBOAPTAMER_INPUT_COLUMNS:
        value = row.get(column)
        if value is None:
            raise RiboAptamerAdapterError(
                f"RiboAptamer row {index} missing column {column!r}"
            )
        coerced[column] = value
    return coerced


def read_riboaptamer_rows(path: Path) -> list[dict[str, str]]:
    """Read the RiboAptamer CSV with exact schema and production row-count gates.

    Uses ``encoding=utf-8-sig`` and ``newline=''``. Does not use pandas.
    """
    rows = _read_riboaptamer_rows_flexible(path)
    if len(rows) != EXPECTED_INPUT_ROWS:
        raise RiboAptamerAdapterError(
            f"RiboAptamer input row count must be {EXPECTED_INPUT_ROWS}; "
            f"got {len(rows)}"
        )
    return rows


def _read_riboaptamer_rows_flexible(path: Path) -> list[dict[str, str]]:
    """Schema-validated read without the frozen 509-row production check."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_riboaptamer_header(reader.fieldnames)
        raw_rows = list(reader)

    coerced: list[dict[str, str]] = []
    for index, row in enumerate(raw_rows, start=2):
        coerced.append(_coerce_source_row(row, index))
    return coerced


def map_riboaptamer_row(
    source_row: Mapping[str, str],
    *,
    csv_data_row: int,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one source row to canonical + sidecar records.

    ``csv_data_row`` is the 1-based data-row number in source order.
    ``Sequence Name`` is never used as ``native_id``.
    """
    native_id = format_native_id(csv_data_row)
    canonical_id = f"{SOURCE_DB}:{native_id}"
    sequence_raw = source_row["Sequence"]

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
    record["pubmed_id"] = extract_pubmed_id(source_row["PubMed Link"])
    record["notes"] = encode_category_prior_notes(source_row["Category"])

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {
        "record_id": canonical_id,
        "riboaptamer_native_id": native_id,
        "riboaptamer_csv_data_row": str(csv_data_row),
    }
    for source_col, sidecar_col in _SOURCE_TO_SIDECAR:
        sidecar[sidecar_col] = source_row[source_col]

    return validated, sidecar


def extract_riboaptamer(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = EXPECTED_INPUT_ROWS,
) -> RiboAptamerExtractionResult:
    """Extract all RiboAptamer rows into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected`` for this input.
    When it equals the frozen production snapshot size (509), known
    production audit counts are also enforced. Pass ``expected_rows=None``
    only in unit tests that intentionally skip the production row-count gate.
    """
    if expected_rows == EXPECTED_INPUT_ROWS:
        source_rows = read_riboaptamer_rows(input_path)
    else:
        source_rows = _read_riboaptamer_rows_flexible(input_path)

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = RiboAptamerExtractionStats()
    stats.input_rows = len(source_rows)
    stats.order_preserved = True
    sequence_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []
    sequence_names: list[str] = []

    for csv_data_row, source_row in enumerate(source_rows, start=1):
        canonical, sidecar = map_riboaptamer_row(
            source_row,
            csv_data_row=csv_data_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        if canonical["sequence_raw"] != source_row["Sequence"]:
            sequence_exact = False
        if sidecar["riboaptamer_sequence"] != source_row["Sequence"]:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["riboaptamer_sequence"]:
            sequence_exact = False

        if canonical["sequence_raw"] == "":
            stats.missing_sequences += 1
        else:
            stats.nonempty_sequences += 1

        if canonical["target_name_raw"] == "":
            stats.empty_target_name_raw += 1
        else:
            stats.nonempty_target_name_raw += 1

        if canonical["publication"] != "":
            stats.nonempty_publication += 1
        if canonical["doi"] != "":
            stats.nonempty_doi += 1
        if canonical["pubmed_id"] != "":
            stats.nonempty_pmid += 1

        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        sequence_names.append(source_row["Sequence Name"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    name_counts = Counter(sequence_names)
    duplicate_keys = {name: n for name, n in name_counts.items() if n > 1}

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.unique_sequence_names = len(name_counts)
    stats.duplicate_sequence_name_keys = len(duplicate_keys)
    stats.rows_in_duplicate_sequence_name_groups = sum(duplicate_keys.values())
    stats.first_native_id = native_ids[0] if native_ids else ""
    stats.last_native_id = native_ids[-1] if native_ids else ""
    stats.sequence_exact_copy_ok = sequence_exact

    _assert_extraction_invariants(stats, expected_rows=expected_rows)

    return RiboAptamerExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: RiboAptamerExtractionStats,
    *,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise RiboAptamerAdapterError(
            f"input_rows must be {expected_rows}; got {n}"
        )
    if stats.canonical_rows != n:
        raise RiboAptamerAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise RiboAptamerAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise RiboAptamerAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise RiboAptamerAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise RiboAptamerAdapterError("sequence_raw exact-copy validation failed")
    if not stats.order_preserved:
        raise RiboAptamerAdapterError("input order was not preserved")
    if stats.nonempty_target_name_raw != 0:
        raise RiboAptamerAdapterError(
            "S1 must not populate target_name_raw for RiboAptamer; "
            f"got {stats.nonempty_target_name_raw} nonempty values"
        )
    if stats.empty_target_name_raw != n:
        raise RiboAptamerAdapterError(
            "every RiboAptamer S1 row must have empty target_name_raw"
        )

    if expected_rows == EXPECTED_INPUT_ROWS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise RiboAptamerAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise RiboAptamerAdapterError(
                f"missing sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )
        if stats.nonempty_pmid != EXPECTED_NONEMPTY_PMID:
            raise RiboAptamerAdapterError(
                f"nonempty pubmed_id must be {EXPECTED_NONEMPTY_PMID}; "
                f"got {stats.nonempty_pmid}"
            )
        if stats.unique_sequence_names != EXPECTED_UNIQUE_SEQUENCE_NAMES:
            raise RiboAptamerAdapterError(
                f"unique Sequence Name values must be {EXPECTED_UNIQUE_SEQUENCE_NAMES}; "
                f"got {stats.unique_sequence_names}"
            )
        if stats.duplicate_sequence_name_keys != EXPECTED_DUPLICATE_SEQUENCE_NAME_KEYS:
            raise RiboAptamerAdapterError(
                "duplicate Sequence Name keys must be "
                f"{EXPECTED_DUPLICATE_SEQUENCE_NAME_KEYS}; "
                f"got {stats.duplicate_sequence_name_keys}"
            )
        if (
            stats.rows_in_duplicate_sequence_name_groups
            != EXPECTED_ROWS_IN_DUPLICATE_SEQUENCE_NAME_GROUPS
        ):
            raise RiboAptamerAdapterError(
                "rows in duplicated Sequence Name groups must be "
                f"{EXPECTED_ROWS_IN_DUPLICATE_SEQUENCE_NAME_GROUPS}; "
                f"got {stats.rows_in_duplicate_sequence_name_groups}"
            )
        if stats.first_native_id != EXPECTED_FIRST_NATIVE_ID:
            raise RiboAptamerAdapterError(
                f"first native_id must be {EXPECTED_FIRST_NATIVE_ID!r}; "
                f"got {stats.first_native_id!r}"
            )
        if stats.last_native_id != EXPECTED_LAST_NATIVE_ID:
            raise RiboAptamerAdapterError(
                f"last native_id must be {EXPECTED_LAST_NATIVE_ID!r}; "
                f"got {stats.last_native_id!r}"
            )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the RiboAptamer source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)
