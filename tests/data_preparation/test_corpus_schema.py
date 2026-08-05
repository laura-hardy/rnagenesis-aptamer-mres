"""Tests for the central canonical corpus schema (no biological sequences)."""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
    CorpusSchemaError,
    empty_corpus_record,
    normalise_csv_value,
    validate_column_order,
    validate_s1_record,
    write_corpus_csv_atomic,
)


def _s1_populated() -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "aptabase:1",
            "sequence_raw": "ACGU",
            "source_db": "aptabase",
            "source_dataset": "demo_dataset",
            "contributing_sources": "aptabase",
            "contributing_datasets": "demo_dataset",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": "1",
            "target_name_raw": "demo_target",
            "publication": "Demo Ref",
            "doi": "10.0/demo",
            "pubmed_id": "123",
            "notes": '{"aptamer_name":"demo"}',
        }
    )
    return record


def test_corpus_columns_exact_order_and_count() -> None:
    assert len(CORPUS_COLUMNS) == 47
    assert CORPUS_COLUMNS[0] == "record_id"
    assert CORPUS_COLUMNS[1] == "sequence_raw"
    assert CORPUS_COLUMNS[-1] == "notes"
    assert CORPUS_COLUMNS[CORPUS_COLUMNS.index("source_db")] == "source_db"
    expected_prefix = (
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
    assert CORPUS_COLUMNS == expected_prefix


def test_empty_record_contains_all_columns() -> None:
    record = empty_corpus_record()
    assert list(record.keys()) == list(CORPUS_COLUMNS)
    assert all(value == "" for value in record.values())


def test_missing_values_serialise_as_empty_strings() -> None:
    assert normalise_csv_value(None) == ""
    assert normalise_csv_value(float("nan")) == ""
    assert normalise_csv_value(math.nan) == ""


def test_forbidden_missing_tokens_not_emitted_for_none() -> None:
    """Missing values must become empty strings, never NA/NaN/None/null/<NA>."""
    for missing in (None, float("nan")):
        serialised = normalise_csv_value(missing)
        assert serialised == ""
        assert serialised not in {"NA", "NaN", "None", "null", "<NA>"}


def test_s1_validator_accepts_allowed_fields() -> None:
    validated = validate_s1_record(_s1_populated())
    assert validated["record_id"] == "aptabase:1"
    assert validated["sequence_raw"] == "ACGU"
    assert validated["independently_attested_by_permissive_source"] == "false"


def test_s1_validator_accepts_empty_sequence_raw() -> None:
    record = _s1_populated()
    record["sequence_raw"] = ""
    validated = validate_s1_record(record)
    assert validated["sequence_raw"] == ""


def test_s1_validator_rejects_premature_s2_fields() -> None:
    for field in sorted(S1_FORBIDDEN_FIELDS):
        record = _s1_populated()
        record[field] = "premature"
        with pytest.raises(CorpusSchemaError, match="later-stage"):
            validate_s1_record(record)


def test_s1_validator_rejects_missing_required_field() -> None:
    record = _s1_populated()
    record["native_id"] = ""
    with pytest.raises(CorpusSchemaError, match="native_id"):
        validate_s1_record(record)


def test_lowercase_boolean_serialisation() -> None:
    assert normalise_csv_value(True) == "true"
    assert normalise_csv_value(False) == "false"
    record = _s1_populated()
    record["independently_attested_by_permissive_source"] = False  # type: ignore[assignment]
    assert (
        validate_s1_record(record)["independently_attested_by_permissive_source"]
        == "false"
    )
    record["independently_attested_by_permissive_source"] = True  # type: ignore[assignment]
    assert (
        validate_s1_record(record)["independently_attested_by_permissive_source"]
        == "true"
    )


def test_validate_column_order_rejects_mismatch() -> None:
    with pytest.raises(CorpusSchemaError):
        validate_column_order(list(CORPUS_COLUMNS)[::-1])
    validate_column_order(CORPUS_COLUMNS)


def test_atomic_deterministic_csv_writing(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    rows = [_s1_populated(), _s1_populated()]
    rows[1]["record_id"] = "aptabase:2"
    rows[1]["native_id"] = "2"
    write_corpus_csv_atomic(path, rows)
    first = path.read_bytes()
    write_corpus_csv_atomic(path, rows)
    second = path.read_bytes()
    assert first == second
    assert first.endswith(b"\n")
    assert b"\r\n" not in first
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    assert list(reader.fieldnames or []) == list(CORPUS_COLUMNS)
    loaded = list(reader)
    assert len(loaded) == 2
    assert loaded[0]["sequence_full"] == ""
    assert "NA" not in loaded[0].values()
    assert "NaN" not in loaded[0].values()
    assert "None" not in loaded[0].values()
    assert "null" not in loaded[0].values()
    assert "<NA>" not in loaded[0].values()


def test_atomic_write_failure_leaves_no_partial_final(tmp_path: Path) -> None:
    path = tmp_path / "final.csv"
    path.write_text("prior\n", encoding="utf-8")

    class Broken(dict):
        def __getitem__(self, key: str) -> str:  # type: ignore[override]
            if key == "notes":
                raise RuntimeError("boom")
            return ""

    broken = Broken({column: "" for column in CORPUS_COLUMNS})
    with pytest.raises(RuntimeError, match="boom"):
        write_corpus_csv_atomic(path, [broken])
    assert path.read_text(encoding="utf-8") == "prior\n"
    leftovers = list(tmp_path.glob(".final.csv.*.tmp"))
    assert leftovers == []
