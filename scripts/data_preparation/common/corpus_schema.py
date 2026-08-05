"""Central canonical corpus schema for S1 onward.

This module is the single definition of the canonical corpus column order and
shared CSV serialisation rules. Missing values are always empty strings.
Adapters must not invent alternate column orders or null tokens.
"""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, MutableMapping, Sequence

CORPUS_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "molecule_type",
    "alphabet_as_reported",
    "t_to_u_applied",
    "chemistry",
    "target_name_raw",
    "target_name",
    "target_uniprot",
    "target_type",
    "target_type_source",
    "target_family",
    "target_pfam",
    "pdb_id",
    "binding_evidence_type",
    "binding_evidence_score",
    "affinity_value",
    "affinity_unit",
    "affinity_type",
    "source_db",
    "source_dataset",
    "contributing_sources",
    "contributing_datasets",
    "corroboration_count",
    "redistribution_status",
    "independently_attested_by_permissive_source",
    "native_id",
    "publication",
    "doi",
    "pubmed_id",
    "accession",
    "experiment_group_id",
    "near_duplicate_family_id",
    "cluster_id",
    "is_cluster_representative",
    "partition",
    "qc_flags",
    "notes",
)

# Fields that S1 adapters must populate (sequence_raw may be empty).
S1_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "record_id",
        "sequence_raw",
        "source_db",
        "source_dataset",
        "contributing_sources",
        "contributing_datasets",
        "corroboration_count",
        "redistribution_status",
        "independently_attested_by_permissive_source",
        "native_id",
    }
)

# Fields that may be populated at S1 when available.
S1_OPTIONAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "target_name_raw",
        "publication",
        "doi",
        "pubmed_id",
        "notes",
    }
)

# All remaining fields belong to later stages and must stay empty at S1.
S1_FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    set(CORPUS_COLUMNS) - S1_REQUIRED_FIELDS - S1_OPTIONAL_FIELDS
)

class CorpusSchemaError(ValueError):
    """Invalid corpus schema usage or S1 validation failure."""


def empty_corpus_record() -> dict[str, str]:
    """Return a canonical record with every field set to the empty string."""
    return {column: "" for column in CORPUS_COLUMNS}


def normalise_csv_value(value: Any) -> str:
    """Serialise a canonical cell value.

    Missing values (``None``, IEEE NaN) become the empty string — never
    ``NA``, ``NaN``, ``None``, ``null``, or ``<NA>``. Booleans become
    lowercase ``true`` / ``false``. Explicit source strings are preserved
    character-for-character (including a literal source token such as
    ``N/A``).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value == int(value):
            return str(int(value))
        return str(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value)

def validate_column_order(columns: Sequence[str]) -> None:
    """Hard-fail unless ``columns`` exactly matches ``CORPUS_COLUMNS``."""
    actual = list(columns)
    expected = list(CORPUS_COLUMNS)
    if actual != expected:
        raise CorpusSchemaError(
            "Canonical corpus columns must match exactly in order. "
            f"Expected {len(expected)} columns, got {len(actual)}."
        )


def validate_s1_record(record: Mapping[str, Any]) -> dict[str, str]:
    """Validate and normalise one S1-stage canonical record.

    Required S1 fields (except ``sequence_raw``) must be nonempty.
    ``sequence_raw`` may be empty. Later-stage fields must remain empty.
    Returns a dict with every ``CORPUS_COLUMNS`` key as a serialised string.
    """
    if set(record.keys()) != set(CORPUS_COLUMNS):
        missing = [c for c in CORPUS_COLUMNS if c not in record]
        extra = [k for k in record if k not in CORPUS_COLUMNS]
        parts: list[str] = []
        if missing:
            parts.append(f"missing={missing}")
        if extra:
            parts.append(f"extra={extra}")
        raise CorpusSchemaError(
            "S1 record keys must exactly match CORPUS_COLUMNS; " + "; ".join(parts)
        )

    normalised = {
        column: normalise_csv_value(record[column]) for column in CORPUS_COLUMNS
    }

    for field in S1_REQUIRED_FIELDS:
        if field == "sequence_raw":
            continue
        if normalised[field] == "":
            raise CorpusSchemaError(
                f"S1 required field {field!r} must be nonempty"
            )

    for field in S1_FORBIDDEN_FIELDS:
        if normalised[field] != "":
            raise CorpusSchemaError(
                f"S1 record must not populate later-stage field {field!r}"
            )

    # Enforce lowercase CSV booleans for the S1 boolean field.
    attested = normalised["independently_attested_by_permissive_source"]
    if attested not in {"true", "false"}:
        raise CorpusSchemaError(
            "independently_attested_by_permissive_source must be lowercase "
            f"true/false at S1; got {attested!r}"
        )

    return normalised


def write_corpus_csv_atomic(
    path: Path,
    records: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
) -> None:
    """Atomically write a corpus CSV with Unix newlines and a trailing newline.

    Missing values are empty strings. Partial final outputs are not left behind
    on failure. Output is deterministic for identical record sequences.
    """
    fieldnames = list(columns) if columns is not None else list(CORPUS_COLUMNS)
    if columns is None:
        validate_column_order(fieldnames)

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
                fieldnames=fieldnames,
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for record in records:
                row: MutableMapping[str, str] = {}
                for column in fieldnames:
                    try:
                        raw_value = record[column]
                    except KeyError as exc:
                        raise CorpusSchemaError(
                            f"Record missing column {column!r} while writing {path.name}"
                        ) from exc
                    row[column] = normalise_csv_value(raw_value)
                writer.writerow(row)
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
