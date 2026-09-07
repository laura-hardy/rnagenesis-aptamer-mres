"""ENA S1 adapter: verbatim extraction into the canonical corpus schema.

Reads only the registry-bound 679-row review_v2 selected file. Does not
classify molecules, convert T→U, trim, canonicalise targets, score
evidence, deduplicate, or perform S2/S3/S4 work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

import csv

from common.corpus_schema import (
    empty_corpus_record,
    validate_s1_record,
    write_corpus_csv_atomic,
)

ENA_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "sequence",
    "target",
    "target_region",
    "target_type",
    "sequence_length",
    "review_unit_id",
    "review_unit_ids",
    "experiment_group_id",
    "experiment_group_ids",
    "accession_count",
    "accessions",
    "near_duplicate_family_id",
    "binding_evidence_type",
    "binding_evidence_strength",
    "evidence_scope",
    "representative_title",
    "manual_target_corrected",
    "manual_sequence_corrected",
    "manual_notes",
    "automatic_concern_flags",
    "source_database",
    "sequence_original",
    "target_original",
    "sequence_corrected_applied",
    "target_corrected_applied",
    "allow_ambiguous_include",
    "sequence_quality_status",
    "length_status",
    "selection_evidence_summary",
    "references",
    "doi_values",
    "pubmed_values",
    "genuine_target_conflict",
    "unresolved_target",
    "near_duplicate_family_size",
    "consolidated_from_n_units",
    "target_comparison_key",
)

DERIVED_SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    "ena_effective_near_duplicate_family_id",
    "ena_effective_near_duplicate_family_size",
    "ena_source_family_id_was_blank",
)

SIDECAR_COLUMNS: Final[tuple[str, ...]] = (
    ("record_id",) + ENA_INPUT_COLUMNS + DERIVED_SIDECAR_COLUMNS
)

EXPECTED_INPUT_ROWS: Final[int] = 679
EXPECTED_NONEMPTY_SEQUENCES: Final[int] = 679
EXPECTED_MISSING_SEQUENCES: Final[int] = 0
EXPECTED_NONEMPTY_TARGETS: Final[int] = 679
EXPECTED_MISSING_TARGETS: Final[int] = 0
EXPECTED_BLANK_SOURCE_FAMILY_IDS: Final[int] = 312
EXPECTED_NONBLANK_SOURCE_FAMILY_IDS: Final[int] = 367
EXPECTED_MATERIALISED_SINGLETONS: Final[int] = 312
EXPECTED_DISTINCT_PRIMARY_EXPERIMENT_GROUPS: Final[int] = 25
EXPECTED_POPULATED_PRIMARY_EXPERIMENT_GROUPS: Final[int] = 679
EXPECTED_SEQUENCE_CORRECTIONS_APPLIED: Final[int] = 8
EXPECTED_TARGET_CORRECTIONS_APPLIED: Final[int] = 1
EXPECTED_CONSOLIDATED_ROWS: Final[int] = 3
EXPECTED_PIPE_FAMILY_ROWS: Final[int] = 1

SOURCE_DB: Final[str] = "ena"
SINGLETON_FAMILY_PREFIX: Final[str] = "ena_singleton_"


class EnaAdapterError(ValueError):
    """Hard failure while validating or extracting the ENA source."""


@dataclass
class EnaExtractionStats:
    """Aggregate counts for the ENA S1 report (no sequence values)."""

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
    populated_primary_experiment_groups: int = 0
    distinct_primary_experiment_groups: int = 0
    blank_source_family_ids: int = 0
    nonblank_source_family_ids: int = 0
    materialised_singleton_family_ids: int = 0
    unique_materialised_singleton_ids: int = 0
    sequence_corrections_applied: int = 0
    target_corrections_applied: int = 0
    consolidated_rows: int = 0
    pipe_family_rows: int = 0
    first_native_id: str = ""
    last_native_id: str = ""
    sequence_exact_copy_ok: bool = False
    target_exact_copy_ok: bool = False
    order_preserved: bool = False
    native_id_strategy: str = (
        "source review_unit_id (unique selected-lane identity; "
        "review_unit_ids retained only in sidecar)"
    )


@dataclass
class EnaExtractionResult:
    """Canonical rows, sidecar rows, and aggregate extraction statistics."""

    canonical_rows: list[dict[str, str]]
    sidecar_rows: list[dict[str, str]]
    stats: EnaExtractionStats = field(default_factory=EnaExtractionStats)


def materialise_effective_family(
    review_unit_id: str,
    source_family_id: str,
    source_family_size: str,
) -> tuple[str, str, str]:
    """Return effective family ID, size, and original-blank indicator.

    Blank source family IDs are singletons, not unknown. Nonblank source
    values, including pipe-delimited consolidated provenance, are kept
    exactly as supplied.
    """
    if source_family_id == "":
        if review_unit_id == "":
            raise EnaAdapterError(
                "Cannot materialise a singleton family ID for a blank "
                "review_unit_id"
            )
        return f"{SINGLETON_FAMILY_PREFIX}{review_unit_id}", "1", "true"
    return source_family_id, source_family_size, "false"


def validate_ena_header(fieldnames: Sequence[str] | None) -> None:
    """Hard-fail on missing, extra, reordered, duplicate, or blank headers."""
    if fieldnames is None:
        raise EnaAdapterError("ENA input has no header row")

    actual = list(fieldnames)
    if any(not name.strip() for name in actual):
        raise EnaAdapterError("ENA input has a blank header column")
    if len(actual) != len(set(actual)):
        raise EnaAdapterError("ENA input has duplicate header columns")
    expected = list(ENA_INPUT_COLUMNS)
    if actual != expected:
        if set(actual) != set(expected):
            missing = [c for c in expected if c not in actual]
            extra = [c for c in actual if c not in expected]
            parts: list[str] = []
            if missing:
                parts.append(f"missing={missing}")
            if extra:
                parts.append(f"extra={extra}")
            raise EnaAdapterError(
                "ENA input columns do not match the required schema; "
                + "; ".join(parts)
            )
        raise EnaAdapterError(
            "ENA input columns are reordered relative to the required schema"
        )


def _coerce_source_row(row: Mapping[str, str | None], index: int) -> dict[str, str]:
    """Return a source row with every expected column present as a string."""
    coerced: dict[str, str] = {}
    for column in ENA_INPUT_COLUMNS:
        value = row.get(column)
        if value is None:
            raise EnaAdapterError(
                f"ENA row {index} missing column {column!r}"
            )
        coerced[column] = value
    return coerced


def read_ena_rows(path: Path) -> list[dict[str, str]]:
    """Read the ENA selected CSV with exact schema and production row-count gates.

    Uses ``encoding=utf-8-sig`` and ``newline=''`` so a UTF-8 BOM is stripped
    from the header. Does not use pandas.
    """
    rows = _read_ena_rows_flexible(path)
    if len(rows) != EXPECTED_INPUT_ROWS:
        raise EnaAdapterError(
            f"ENA input row count must be {EXPECTED_INPUT_ROWS}; got {len(rows)}"
        )
    return rows


def _read_ena_rows_flexible(path: Path) -> list[dict[str, str]]:
    """Schema-validated read without the frozen 679-row production check."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_ena_header(reader.fieldnames)
        raw_rows = list(reader)

    coerced: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(raw_rows, start=2):
        item = _coerce_source_row(row, index)
        native_id = item["review_unit_id"]
        if native_id == "":
            raise EnaAdapterError(
                f"ENA row {index} has a blank review_unit_id"
            )
        if native_id in seen_ids:
            raise EnaAdapterError(
                f"Duplicate ENA review_unit_id: {native_id!r}"
            )
        seen_ids.add(native_id)
        coerced.append(item)
    return coerced


def map_ena_row(
    source_row: Mapping[str, str],
    *,
    source_dataset: str,
    redistribution_status: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Map one source row to canonical + sidecar records.

    ``review_unit_id`` is the native identity. Reviewed ``sequence`` and
    ``target`` are copied verbatim. Correction, grouping, family, and
    evidence fields remain sidecar provenance.
    """
    native_id = source_row["review_unit_id"]
    if native_id == "":
        raise EnaAdapterError("ENA review_unit_id must be nonempty")
    canonical_id = f"{SOURCE_DB}:{native_id}"
    sequence_raw = source_row["sequence"]
    target_name_raw = source_row["target"]
    effective_family_id, effective_family_size, family_was_blank = (
        materialise_effective_family(
            native_id,
            source_row["near_duplicate_family_id"],
            source_row["near_duplicate_family_size"],
        )
    )

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
    record["publication"] = ""
    record["doi"] = ""
    record["pubmed_id"] = ""
    record["notes"] = ""

    validated = validate_s1_record(record)

    sidecar: dict[str, str] = {"record_id": canonical_id}
    for column in ENA_INPUT_COLUMNS:
        sidecar[column] = source_row[column]
    sidecar["ena_effective_near_duplicate_family_id"] = effective_family_id
    sidecar["ena_effective_near_duplicate_family_size"] = effective_family_size
    sidecar["ena_source_family_id_was_blank"] = family_was_blank

    return validated, sidecar


def extract_ena(
    input_path: Path,
    *,
    source_dataset: str,
    redistribution_status: str,
    expected_rows: int | None = EXPECTED_INPUT_ROWS,
) -> EnaExtractionResult:
    """Extract all ENA rows into canonical and sidecar tables.

    ``expected_rows`` is the registry ``n_rows_expected`` for this input.
    When it equals the frozen production snapshot size (679), known
    production audit counts are also enforced. Pass ``expected_rows=None``
    only in unit tests that intentionally skip the production row-count gate.
    """
    if expected_rows == EXPECTED_INPUT_ROWS:
        source_rows = read_ena_rows(input_path)
    else:
        source_rows = _read_ena_rows_flexible(input_path)

    canonical_rows: list[dict[str, str]] = []
    sidecar_rows: list[dict[str, str]] = []
    stats = EnaExtractionStats()
    stats.input_rows = len(source_rows)
    stats.order_preserved = True
    sequence_exact = True
    target_exact = True

    native_ids: list[str] = []
    record_ids: list[str] = []
    primary_groups: list[str] = []
    singleton_ids: list[str] = []
    source_nonblank_families: set[str] = set()

    for source_row in source_rows:
        canonical, sidecar = map_ena_row(
            source_row,
            source_dataset=source_dataset,
            redistribution_status=redistribution_status,
        )
        if canonical["sequence_raw"] != source_row["sequence"]:
            sequence_exact = False
        if sidecar["sequence"] != source_row["sequence"]:
            sequence_exact = False
        if canonical["sequence_raw"] != sidecar["sequence"]:
            sequence_exact = False

        if canonical["target_name_raw"] != source_row["target"]:
            target_exact = False
        if sidecar["target"] != source_row["target"]:
            target_exact = False
        if canonical["target_name_raw"] != sidecar["target"]:
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

        if source_row["experiment_group_id"] != "":
            stats.populated_primary_experiment_groups += 1
            primary_groups.append(source_row["experiment_group_id"])

        source_family = source_row["near_duplicate_family_id"]
        if source_family == "":
            stats.blank_source_family_ids += 1
            singleton_ids.append(
                sidecar["ena_effective_near_duplicate_family_id"]
            )
        else:
            stats.nonblank_source_family_ids += 1
            source_nonblank_families.add(source_family)
            if sidecar["ena_effective_near_duplicate_family_id"] != source_family:
                raise EnaAdapterError(
                    "Nonblank source near_duplicate_family_id must be preserved "
                    "exactly as the effective family ID"
                )
            if sidecar["near_duplicate_family_id"] != source_family:
                raise EnaAdapterError(
                    "Sidecar near_duplicate_family_id must remain the original "
                    "source value"
                )
            if "|" in source_family:
                stats.pipe_family_rows += 1

        if source_row["sequence_corrected_applied"] == "1":
            stats.sequence_corrections_applied += 1
        if source_row["target_corrected_applied"] == "1":
            stats.target_corrections_applied += 1
        consolidated = source_row["consolidated_from_n_units"]
        if consolidated not in {"", "1"}:
            stats.consolidated_rows += 1

        native_ids.append(canonical["native_id"])
        record_ids.append(canonical["record_id"])
        canonical_rows.append(canonical)
        sidecar_rows.append(sidecar)

    overlap = source_nonblank_families.intersection(singleton_ids)
    if overlap:
        raise EnaAdapterError(
            "Materialised singleton family IDs collide with source "
            f"near_duplicate_family_id values ({len(overlap)} collision(s))"
        )

    stats.canonical_rows = len(canonical_rows)
    stats.sidecar_rows = len(sidecar_rows)
    stats.unique_native_ids = len(set(native_ids))
    stats.unique_record_ids = len(set(record_ids))
    stats.distinct_primary_experiment_groups = len(set(primary_groups))
    stats.materialised_singleton_family_ids = len(singleton_ids)
    stats.unique_materialised_singleton_ids = len(set(singleton_ids))
    stats.first_native_id = native_ids[0] if native_ids else ""
    stats.last_native_id = native_ids[-1] if native_ids else ""
    stats.sequence_exact_copy_ok = sequence_exact
    stats.target_exact_copy_ok = target_exact

    _assert_extraction_invariants(stats, expected_rows=expected_rows)

    return EnaExtractionResult(
        canonical_rows=canonical_rows,
        sidecar_rows=sidecar_rows,
        stats=stats,
    )


def _assert_extraction_invariants(
    stats: EnaExtractionStats,
    *,
    expected_rows: int | None,
) -> None:
    """Hard-fail unless S1 retention and identity invariants hold."""
    n = stats.input_rows
    if expected_rows is not None and n != expected_rows:
        raise EnaAdapterError(f"input_rows must be {expected_rows}; got {n}")
    if stats.canonical_rows != n:
        raise EnaAdapterError(
            f"canonical_rows ({stats.canonical_rows}) != input_rows ({n})"
        )
    if stats.sidecar_rows != n:
        raise EnaAdapterError(
            f"sidecar_rows ({stats.sidecar_rows}) != input_rows ({n})"
        )
    if stats.unique_native_ids != n:
        raise EnaAdapterError(
            f"unique_native_ids ({stats.unique_native_ids}) != input_rows ({n})"
        )
    if stats.unique_record_ids != n:
        raise EnaAdapterError(
            f"unique_record_ids ({stats.unique_record_ids}) != input_rows ({n})"
        )
    if not stats.sequence_exact_copy_ok:
        raise EnaAdapterError("sequence_raw exact-copy validation failed")
    if not stats.target_exact_copy_ok:
        raise EnaAdapterError("target_name_raw exact-copy validation failed")
    if not stats.order_preserved:
        raise EnaAdapterError("input order was not preserved")
    if stats.nonempty_publication != 0:
        raise EnaAdapterError(
            "S1 must not populate publication for ENA; "
            f"got {stats.nonempty_publication} nonempty values"
        )
    if stats.nonempty_doi != 0:
        raise EnaAdapterError(
            "S1 must not populate doi for ENA; "
            f"got {stats.nonempty_doi} nonempty values"
        )
    if stats.nonempty_pmid != 0:
        raise EnaAdapterError(
            "S1 must not populate pubmed_id for ENA; "
            f"got {stats.nonempty_pmid} nonempty values"
        )
    if stats.materialised_singleton_family_ids != stats.blank_source_family_ids:
        raise EnaAdapterError(
            "Materialised singleton count must equal original blank family IDs"
        )
    if (
        stats.unique_materialised_singleton_ids
        != stats.materialised_singleton_family_ids
    ):
        raise EnaAdapterError("Materialised singleton family IDs must be unique")

    if expected_rows == EXPECTED_INPUT_ROWS:
        if stats.nonempty_sequences != EXPECTED_NONEMPTY_SEQUENCES:
            raise EnaAdapterError(
                f"nonempty sequence_raw must be {EXPECTED_NONEMPTY_SEQUENCES}; "
                f"got {stats.nonempty_sequences}"
            )
        if stats.missing_sequences != EXPECTED_MISSING_SEQUENCES:
            raise EnaAdapterError(
                f"missing sequence_raw must be {EXPECTED_MISSING_SEQUENCES}; "
                f"got {stats.missing_sequences}"
            )
        if stats.nonempty_targets != EXPECTED_NONEMPTY_TARGETS:
            raise EnaAdapterError(
                f"nonempty target_name_raw must be {EXPECTED_NONEMPTY_TARGETS}; "
                f"got {stats.nonempty_targets}"
            )
        if stats.missing_targets != EXPECTED_MISSING_TARGETS:
            raise EnaAdapterError(
                f"missing target_name_raw must be {EXPECTED_MISSING_TARGETS}; "
                f"got {stats.missing_targets}"
            )
        if stats.blank_source_family_ids != EXPECTED_BLANK_SOURCE_FAMILY_IDS:
            raise EnaAdapterError(
                "blank source near_duplicate_family_id count must be "
                f"{EXPECTED_BLANK_SOURCE_FAMILY_IDS}; "
                f"got {stats.blank_source_family_ids}"
            )
        if stats.nonblank_source_family_ids != EXPECTED_NONBLANK_SOURCE_FAMILY_IDS:
            raise EnaAdapterError(
                "nonblank source near_duplicate_family_id count must be "
                f"{EXPECTED_NONBLANK_SOURCE_FAMILY_IDS}; "
                f"got {stats.nonblank_source_family_ids}"
            )
        if stats.materialised_singleton_family_ids != EXPECTED_MATERIALISED_SINGLETONS:
            raise EnaAdapterError(
                "materialised singleton family IDs must be "
                f"{EXPECTED_MATERIALISED_SINGLETONS}; "
                f"got {stats.materialised_singleton_family_ids}"
            )
        if (
            stats.populated_primary_experiment_groups
            != EXPECTED_POPULATED_PRIMARY_EXPERIMENT_GROUPS
        ):
            raise EnaAdapterError(
                "populated primary experiment_group_id count must be "
                f"{EXPECTED_POPULATED_PRIMARY_EXPERIMENT_GROUPS}; "
                f"got {stats.populated_primary_experiment_groups}"
            )
        if (
            stats.distinct_primary_experiment_groups
            != EXPECTED_DISTINCT_PRIMARY_EXPERIMENT_GROUPS
        ):
            raise EnaAdapterError(
                "distinct primary experiment_group_id count must be "
                f"{EXPECTED_DISTINCT_PRIMARY_EXPERIMENT_GROUPS}; "
                f"got {stats.distinct_primary_experiment_groups}"
            )
        if stats.sequence_corrections_applied != EXPECTED_SEQUENCE_CORRECTIONS_APPLIED:
            raise EnaAdapterError(
                "sequence_corrected_applied=1 count must be "
                f"{EXPECTED_SEQUENCE_CORRECTIONS_APPLIED}; "
                f"got {stats.sequence_corrections_applied}"
            )
        if stats.target_corrections_applied != EXPECTED_TARGET_CORRECTIONS_APPLIED:
            raise EnaAdapterError(
                "target_corrected_applied=1 count must be "
                f"{EXPECTED_TARGET_CORRECTIONS_APPLIED}; "
                f"got {stats.target_corrections_applied}"
            )
        if stats.consolidated_rows != EXPECTED_CONSOLIDATED_ROWS:
            raise EnaAdapterError(
                "consolidated_from_n_units>1 count must be "
                f"{EXPECTED_CONSOLIDATED_ROWS}; got {stats.consolidated_rows}"
            )
        if stats.pipe_family_rows != EXPECTED_PIPE_FAMILY_ROWS:
            raise EnaAdapterError(
                "pipe-delimited source family rows must be "
                f"{EXPECTED_PIPE_FAMILY_ROWS}; got {stats.pipe_family_rows}"
            )


def write_sidecar_csv_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically write the ENA source-metadata sidecar."""
    write_corpus_csv_atomic(path, rows, columns=SIDECAR_COLUMNS)
