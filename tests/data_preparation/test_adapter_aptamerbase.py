"""Tests for the AptamerBase S1 adapter (synthetic fixtures only).

Real AptamerBase sequences are never embedded in fixtures. The optional
local-only production skipif gate asserts counts without writing sequences
into this file.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters import ADAPTER_KEYS  # noqa: E402
from adapters.aptamerbase import (  # noqa: E402
    APTAMERBASE_INPUT_COLUMNS,
    EXPECTED_DUPLICATE_FREEBASE_ID_GROUPS,
    EXPECTED_EMPTY_SEQUENCES,
    EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_EXCESS,
    EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS,
    EXPECTED_FIRST_NATIVE_ID,
    EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_BLANK,
    EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_FALSE,
    EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_TRUE,
    EXPECTED_HAS_MINIMAL_APTAMER_NONEMPTY,
    EXPECTED_HAS_MUTATIONAL_ANALYSIS_BLANK,
    EXPECTED_HAS_MUTATIONAL_ANALYSIS_FALSE,
    EXPECTED_HAS_MUTATIONAL_ANALYSIS_TRUE,
    EXPECTED_INPUT_ROWS,
    EXPECTED_IS_MINIMAL_APTAMER_OF_NONEMPTY,
    EXPECTED_LAST_NATIVE_ID,
    EXPECTED_NONEMPTY_SEQUENCES,
    EXPECTED_OTHER_NONEMPTY_SEQUENCES,
    EXPECTED_ROWS_IN_DUPLICATE_FREEBASE_ID_GROUPS,
    EXPECTED_ROWS_IN_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS,
    EXPECTED_SEQUENCE_NA_TEXT,
    EXPECTED_TYPE_APTAMER,
    EXPECTED_TYPE_PREDICTED_STRUCTURE,
    EXPECTED_TYPE_SECONDARY_STRUCTURE,
    EXPECTED_UNIQUE_FREEBASE_IDS,
    SIDECAR_COLUMNS,
    TYPE_APTAMER,
    TYPE_PREDICTED_STRUCTURE,
    TYPE_SECONDARY_STRUCTURE,
    AptamerBaseAdapterError,
    extract_aptamerbase,
    format_native_id,
    map_aptamerbase_row,
    read_aptamerbase_rows,
    validate_aptamerbase_header,
    write_sidecar_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
    write_corpus_csv_atomic,
)
from s0_build_registry import REQUIRED_COLUMNS, load_registry_spec  # noqa: E402
from s1_extract import (  # noqa: E402
    S1ExtractError,
    run_s1_extraction,
)

EXPECTED_SOURCE_DATASET = "aptamerbase_export_2026-06-24"
EXPECTED_PRODUCTION_SHA256 = (
    "40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c"
)
EXPECTED_PRODUCTION_PATH = "data/raw/aptamerbase/aptamerbase_aptamers.csv"
EXPECTED_RDF_PATH = "data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz"
EXPECTED_RDF_SHA256 = (
    "3ab9340ee1fcb6a0910532a6e8d4cf5cc62579c3b21d85355c48d473e372006c"
)
EXPECTED_RDF_STATEMENTS = 270507

SYNTHETIC_T = "ZzTtQq"
SYNTHETIC_U = "ZzUuQq"
SYNTHETIC_MIXED_CASE = "aAtTgGcCxx"
SYNTHETIC_WHITESPACE = "  ZZ QQ  "
SYNTHETIC_UNUSUAL = "ZZ#QQ?!!"
SYNTHETIC_NA = "n/a"
SYNTHETIC_LABEL = "synthetic Freebase export label (PMID 00000000)"
SYNTHETIC_FREEBASE_A = "http://rdf.freebase.com/ns/m.synthetic_a"
SYNTHETIC_FREEBASE_B = "http://rdf.freebase.com/ns/m.synthetic_b"
SYNTHETIC_MINIMAL_OF = "http://rdf.freebase.com/ns/m.synthetic_parent"
SYNTHETIC_HAS_MINIMAL = "http://rdf.freebase.com/ns/m.synthetic_child"


def _blank_source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in APTAMERBASE_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_aptamerbase_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(APTAMERBASE_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {col: row.get(col, "") for col in APTAMERBASE_INPUT_COLUMNS}
            )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_synthetic_nt_gz(path: Path, n_statements: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for index in range(1, n_statements + 1):
            handle.write(
                f"<http://example.org/s{index}> "
                f"<http://example.org/p> "
                f"<http://example.org/o{index}> .\n"
            )


def _demo_rows() -> list[dict[str, str]]:
    """Synthetic rows covering duplicates, blanks, n/a, and mixed alphabets."""
    shared_complete = _blank_source_row(
        type=TYPE_APTAMER,
        id=SYNTHETIC_FREEBASE_A,
        label=SYNTHETIC_LABEL,
        sequence=SYNTHETIC_T,
        sequence_length="6",
        has_mutational_analysis="true",
        has_experimentally_determined_structure="false",
        has_minimal_aptamer=SYNTHETIC_HAS_MINIMAL,
        is_minimal_aptamer_of="",
        has_application="",
        has_modification_details="",
        has_secondary_structure="",
        has_predicted_secondary_structure="",
        has_sequence_pattern="",
    )
    return [
        shared_complete,
        dict(shared_complete),
        _blank_source_row(
            type=TYPE_APTAMER,
            id=SYNTHETIC_FREEBASE_A,
            label=SYNTHETIC_LABEL,
            sequence=SYNTHETIC_U,
            sequence_length="6",
            has_mutational_analysis="false",
            has_experimentally_determined_structure="true",
            has_minimal_aptamer="",
            is_minimal_aptamer_of=SYNTHETIC_MINIMAL_OF,
        ),
        _blank_source_row(
            type=TYPE_SECONDARY_STRUCTURE,
            id=SYNTHETIC_FREEBASE_B,
            label="synthetic secondary-structure topic",
            sequence="",
            sequence_length="",
            has_mutational_analysis="",
            has_experimentally_determined_structure="",
            has_secondary_structure="http://rdf.freebase.com/ns/m.synthetic_ss",
        ),
        _blank_source_row(
            type=TYPE_PREDICTED_STRUCTURE,
            id="http://rdf.freebase.com/ns/m.synthetic_c",
            label="synthetic predicted-structure topic",
            sequence=SYNTHETIC_NA,
            sequence_length="n/a",
            has_predicted_secondary_structure=(
                "http://rdf.freebase.com/ns/m.synthetic_pred"
            ),
        ),
        _blank_source_row(
            type=TYPE_APTAMER,
            id="http://rdf.freebase.com/ns/m.synthetic_d",
            label="synthetic mixed-case whitespace row",
            sequence=SYNTHETIC_WHITESPACE,
            sequence_length="8",
            has_sequence_pattern="ZZ",
        ),
        _blank_source_row(
            type=TYPE_APTAMER,
            id="http://rdf.freebase.com/ns/m.synthetic_e",
            label="synthetic unusual-character row",
            sequence=SYNTHETIC_UNUSUAL,
            sequence_length="8",
            has_modification_details="synthetic modifier token",
        ),
        _blank_source_row(
            type=TYPE_APTAMER,
            id="http://rdf.freebase.com/ns/m.synthetic_f",
            label="synthetic mixed-case T/U-free token",
            sequence=SYNTHETIC_MIXED_CASE,
            sequence_length="10",
        ),
    ]


def test_adapter_dispatch_recognises_aptamerbase() -> None:
    assert "aptamerbase" in ADAPTER_KEYS
    from s1_extract import _get_adapter

    assert _get_adapter("aptamerbase") is extract_aptamerbase


def test_tracked_registry_spec_registers_authoritative_aptamerbase_file() -> None:
    rows = load_registry_spec(REPO_ROOT / "config" / "source_registry.csv")
    aptamerbase = [row for row in rows if row.source_key == "aptamerbase"]
    assert len(aptamerbase) == 2
    assert {row.source_dataset for row in aptamerbase} == {EXPECTED_SOURCE_DATASET}
    csv_row = next(row for row in aptamerbase if row.path == EXPECTED_PRODUCTION_PATH)
    rdf_row = next(row for row in aptamerbase if row.path == EXPECTED_RDF_PATH)
    assert csv_row.sha256 == EXPECTED_PRODUCTION_SHA256
    assert csv_row.n_rows_expected == EXPECTED_INPUT_ROWS
    assert csv_row.snapshot_date == "2026-06-24"
    assert csv_row.tier == "1"
    assert csv_row.redistribution_status == "unknown"
    assert "paper.pdf" not in csv_row.notes or "documentation only" in csv_row.notes
    assert rdf_row.sha256 == EXPECTED_RDF_SHA256
    assert rdf_row.n_rows_expected == EXPECTED_RDF_STATEMENTS
    assert rdf_row.snapshot_date == "2026-06-24"
    assert rdf_row.tier == "1"
    assert rdf_row.redistribution_status == "unknown"
    assert "not row-generating" in rdf_row.notes
    assert "does not create additional corpus records" in rdf_row.notes
    assert "micheldumontier/aptamerbase@e7a3eb43d24504fd5a7b6c3e470ab242bc471b3a" in (
        rdf_row.notes
    )
    assert "Freebase ID" in rdf_row.notes
    forbidden_paths = {
        row.path
        for row in rows
        if "aptamerbase" in row.path
        and row.path not in {EXPECTED_PRODUCTION_PATH, EXPECTED_RDF_PATH}
    }
    assert forbidden_paths == set()


def test_exact_schema_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    _write_aptamerbase_csv(path, _demo_rows())
    result = extract_aptamerbase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 8
    assert result.stats.canonical_rows == 8
    assert result.stats.sidecar_rows == 8
    validate_aptamerbase_header(list(APTAMERBASE_INPUT_COLUMNS))


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    cols = list(APTAMERBASE_INPUT_COLUMNS)
    cols.remove("has_sequence_pattern")
    _write_csv(path, cols, [_blank_source_row()])
    with pytest.raises(AptamerBaseAdapterError, match="missing"):
        extract_aptamerbase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_extra_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    cols = list(APTAMERBASE_INPUT_COLUMNS) + ["extra_col"]
    _write_csv(
        path,
        cols,
        [{**_blank_source_row(), "extra_col": "x"}],
    )
    with pytest.raises(AptamerBaseAdapterError, match="extra"):
        extract_aptamerbase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_reordered_columns_rejected(tmp_path: Path) -> None:
    path = tmp_path / "reordered.csv"
    cols = list(APTAMERBASE_INPUT_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    _write_csv(path, cols, [_blank_source_row()])
    with pytest.raises(AptamerBaseAdapterError, match="reordered"):
        extract_aptamerbase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_every_physical_input_row_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "preserve.csv"
    rows = _demo_rows()
    _write_aptamerbase_csv(path, rows)
    result = extract_aptamerbase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == len(rows)
    assert result.stats.canonical_rows == len(rows)
    assert result.stats.sidecar_rows == len(rows)
    assert result.stats.no_row_consolidation is True
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        r["sequence"] for r in rows
    ]


def test_duplicate_source_ids_are_allowed(tmp_path: Path) -> None:
    path = tmp_path / "dup_ids.csv"
    _write_aptamerbase_csv(path, _demo_rows())
    result = extract_aptamerbase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    ids = [row["aptamerbase_id"] for row in result.sidecar_rows]
    assert ids[0] == ids[1] == ids[2] == SYNTHETIC_FREEBASE_A
    assert result.stats.duplicate_freebase_id_groups == 1
    assert result.stats.rows_in_duplicate_freebase_id_groups == 3
    assert len({row["record_id"] for row in result.canonical_rows}) == 8


def test_duplicate_full_rows_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "dup_rows.csv"
    _write_aptamerbase_csv(path, _demo_rows())
    result = extract_aptamerbase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.exact_duplicate_complete_row_groups == 1
    assert result.stats.rows_in_exact_duplicate_complete_row_groups == 2
    assert result.stats.exact_duplicate_complete_row_excess == 1
    assert result.canonical_rows[0]["sequence_raw"] == SYNTHETIC_T
    assert result.canonical_rows[1]["sequence_raw"] == SYNTHETIC_T
    assert result.canonical_rows[0]["record_id"] != result.canonical_rows[1]["record_id"]


def test_row_based_native_ids_are_zero_padded() -> None:
    assert format_native_id(1) == "0001"
    assert format_native_id(2128) == "2128"
    source = _blank_source_row(sequence=SYNTHETIC_T, id=SYNTHETIC_FREEBASE_A)
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=7,
        source_dataset=EXPECTED_SOURCE_DATASET,
        redistribution_status="unknown",
    )
    assert canonical["native_id"] == "0007"
    assert canonical["record_id"] == "aptamerbase:0007"
    assert sidecar["record_id"] == "aptamerbase:0007"
    assert sidecar["native_id"] == "0007"
    assert sidecar["aptamerbase_csv_data_row"] == "7"
    assert sidecar["aptamerbase_id"] == SYNTHETIC_FREEBASE_A


def test_record_ids_are_unique(tmp_path: Path) -> None:
    path = tmp_path / "unique.csv"
    _write_aptamerbase_csv(path, _demo_rows())
    result = extract_aptamerbase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    ids = [row["record_id"] for row in result.canonical_rows]
    native = [row["native_id"] for row in result.canonical_rows]
    assert ids == [f"aptamerbase:{n}" for n in native]
    assert native == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
        "0007",
        "0008",
    ]
    assert len(set(ids)) == 8


def test_source_order_preserved(tmp_path: Path) -> None:
    path = tmp_path / "order.csv"
    rows = _demo_rows()
    _write_aptamerbase_csv(path, rows)
    result = extract_aptamerbase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.order_preserved is True
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        r["sequence"] for r in rows
    ]
    assert [row["aptamerbase_id"] for row in result.sidecar_rows] == [
        r["id"] for r in rows
    ]


@pytest.mark.parametrize(
    "sequence",
    [
        "",
        SYNTHETIC_NA,
        SYNTHETIC_MIXED_CASE,
        SYNTHETIC_WHITESPACE,
        SYNTHETIC_T,
        SYNTHETIC_U,
        SYNTHETIC_UNUSUAL,
    ],
)
def test_sequence_raw_copied_verbatim(sequence: str) -> None:
    source = _blank_source_row(sequence=sequence, label=SYNTHETIC_LABEL)
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["sequence_raw"] == sequence
    assert sidecar["aptamerbase_sequence"] == sequence
    assert canonical["sequence_full"] == ""
    assert canonical["sequence_core"] == ""
    assert canonical["molecule_type"] == ""
    assert canonical["chemistry"] == ""
    assert canonical["alphabet_as_reported"] == ""
    assert canonical["t_to_u_applied"] == ""


def test_whitespace_not_stripped_and_na_not_missing() -> None:
    whitespace, sidecar_ws = map_aptamerbase_row(
        _blank_source_row(sequence=SYNTHETIC_WHITESPACE),
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert whitespace["sequence_raw"] == SYNTHETIC_WHITESPACE
    assert whitespace["sequence_raw"] != SYNTHETIC_WHITESPACE.strip()
    assert sidecar_ws["aptamerbase_sequence"] == SYNTHETIC_WHITESPACE

    na_row, sidecar_na = map_aptamerbase_row(
        _blank_source_row(sequence=SYNTHETIC_NA),
        csv_data_row=2,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert na_row["sequence_raw"] == "n/a"
    assert sidecar_na["aptamerbase_sequence"] == "n/a"


def test_label_does_not_populate_target_name_raw() -> None:
    source = _blank_source_row(sequence=SYNTHETIC_T, label=SYNTHETIC_LABEL)
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["target_name_raw"] == ""
    assert canonical["target_name"] == ""
    assert sidecar["aptamerbase_label"] == SYNTHETIC_LABEL


def test_freebase_id_survives_in_sidecar() -> None:
    source = _blank_source_row(sequence=SYNTHETIC_T, id=SYNTHETIC_FREEBASE_A)
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=12,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["native_id"] == "0012"
    assert canonical["record_id"] == "aptamerbase:0012"
    assert sidecar["aptamerbase_id"] == SYNTHETIC_FREEBASE_A
    assert sidecar["aptamerbase_id"] != canonical["native_id"]


def test_minimal_aptamer_relationships_survive_verbatim_in_sidecar() -> None:
    source = _blank_source_row(
        sequence=SYNTHETIC_T,
        has_minimal_aptamer=SYNTHETIC_HAS_MINIMAL,
        is_minimal_aptamer_of=SYNTHETIC_MINIMAL_OF,
    )
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["aptamerbase_has_minimal_aptamer"] == SYNTHETIC_HAS_MINIMAL
    assert sidecar["aptamerbase_is_minimal_aptamer_of"] == SYNTHETIC_MINIMAL_OF
    assert canonical["near_duplicate_family_id"] == ""
    assert canonical["experiment_group_id"] == ""
    assert canonical["cluster_id"] == ""
    assert canonical["notes"] == ""


def test_structure_and_evidence_remain_sidecar_only() -> None:
    source = _blank_source_row(
        sequence=SYNTHETIC_T,
        has_mutational_analysis="true",
        has_experimentally_determined_structure="true",
        has_secondary_structure="http://rdf.freebase.com/ns/m.synthetic_ss",
        has_predicted_secondary_structure="http://rdf.freebase.com/ns/m.synthetic_pred",
    )
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["aptamerbase_has_mutational_analysis"] == "true"
    assert sidecar["aptamerbase_has_experimentally_determined_structure"] == "true"
    assert sidecar["aptamerbase_has_secondary_structure"].startswith("http://")
    assert sidecar["aptamerbase_has_predicted_secondary_structure"].startswith(
        "http://"
    )
    assert canonical["pdb_id"] == ""
    assert canonical["binding_evidence_type"] == ""
    assert canonical["binding_evidence_score"] == ""


def test_s2_s3_s4_fields_stay_empty() -> None:
    source = _blank_source_row(
        sequence=SYNTHETIC_T,
        type=TYPE_APTAMER,
        label=SYNTHETIC_LABEL,
        has_mutational_analysis="true",
        has_experimentally_determined_structure="true",
        has_minimal_aptamer=SYNTHETIC_HAS_MINIMAL,
        is_minimal_aptamer_of=SYNTHETIC_MINIMAL_OF,
        has_modification_details="synthetic modifier token",
    )
    canonical, _ = map_aptamerbase_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    for field in S1_FORBIDDEN_FIELDS:
        assert canonical[field] == "", field
    assert canonical["publication"] == ""
    assert canonical["doi"] == ""
    assert canonical["pubmed_id"] == ""
    assert canonical["notes"] == ""
    assert canonical["target_name_raw"] == ""
    assert canonical["accession"] == ""
    assert canonical["experiment_group_id"] == ""
    assert canonical["near_duplicate_family_id"] == ""


def test_all_source_fields_preserved_in_sidecar() -> None:
    source = _demo_rows()[2]
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=3,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert list(sidecar.keys()) == list(SIDECAR_COLUMNS)
    assert sidecar["record_id"] == canonical["record_id"]
    for column, sidecar_col in (
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
    ):
        assert sidecar[sidecar_col] == source[column]


def test_structure_topic_rows_are_retained() -> None:
    source = _demo_rows()[3]
    canonical, sidecar = map_aptamerbase_row(
        source,
        csv_data_row=4,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["aptamerbase_type"] == TYPE_SECONDARY_STRUCTURE
    assert canonical["sequence_raw"] == ""
    assert canonical["record_id"] == "aptamerbase:0004"


def test_repeated_extraction_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "repeat.csv"
    _write_aptamerbase_csv(path, _demo_rows())
    kwargs = dict(
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    first = extract_aptamerbase(path, **kwargs)
    second = extract_aptamerbase(path, **kwargs)
    assert first.canonical_rows == second.canonical_rows
    assert first.sidecar_rows == second.sidecar_rows


def test_production_row_count_gate_rejects_non_2128(tmp_path: Path) -> None:
    path = tmp_path / "small.csv"
    _write_aptamerbase_csv(path, _demo_rows())
    with pytest.raises(AptamerBaseAdapterError, match="2128"):
        read_aptamerbase_rows(path)


def test_stage_schema_compliance() -> None:
    canonical, _ = map_aptamerbase_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset=EXPECTED_SOURCE_DATASET,
        redistribution_status="unknown",
    )
    assert list(canonical.keys()) == list(CORPUS_COLUMNS)
    assert canonical["source_db"] == "aptamerbase"
    assert canonical["source_dataset"] == EXPECTED_SOURCE_DATASET
    assert canonical["contributing_sources"] == "aptamerbase"
    assert canonical["contributing_datasets"] == EXPECTED_SOURCE_DATASET
    assert canonical["corroboration_count"] == "1"
    assert canonical["redistribution_status"] == "unknown"
    assert canonical["independently_attested_by_permissive_source"] == "false"


def _make_s1_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "aptamerbase").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def test_dispatcher_round_trip(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = repo / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
    rows = _demo_rows()
    _write_aptamerbase_csv(input_path, rows)
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "aptamerbase",
                "source_dataset": EXPECTED_SOURCE_DATASET,
                "path": EXPECTED_PRODUCTION_PATH,
                "sha256": digest,
                "n_rows_expected": str(len(rows)),
                "snapshot_date": "2026-06-24",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            }
        ],
    )
    result = run_s1_extraction(
        repo_root=repo,
        source_key="aptamerbase",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert result.stats.input_rows == 8
    assert result.deterministic_rerun_ok is True
    assert result.input_hash_unchanged is True
    canonical = repo / "data" / "interim" / "extracted" / "aptamerbase_extracted.csv"
    sidecar = (
        repo / "data" / "interim" / "extracted" / "aptamerbase_source_metadata.csv"
    )
    report = repo / "data" / "interim" / "extracted" / "aptamerbase_s1_report.md"
    with canonical.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(CORPUS_COLUMNS)
        out_rows = list(reader)
    assert [row["native_id"] for row in out_rows] == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
        "0007",
        "0008",
    ]
    assert out_rows[0]["sequence_raw"] == SYNTHETIC_T
    assert out_rows[3]["sequence_raw"] == ""
    assert out_rows[4]["sequence_raw"] == SYNTHETIC_NA
    assert all(row["target_name_raw"] == "" for row in out_rows)
    assert all(row["source_db"] == "aptamerbase" for row in out_rows)
    assert all(row["molecule_type"] == "" for row in out_rows)
    assert all(row["pdb_id"] == "" for row in out_rows)
    with sidecar.open(encoding="utf-8", newline="") as handle:
        side_reader = csv.DictReader(handle)
        assert list(side_reader.fieldnames or []) == list(SIDECAR_COLUMNS)
        side_rows = list(side_reader)
    assert len(side_rows) == 8
    assert side_rows[0]["aptamerbase_id"] == SYNTHETIC_FREEBASE_A
    assert side_rows[2]["aptamerbase_is_minimal_aptamer_of"] == SYNTHETIC_MINIMAL_OF
    report_text = report.read_text(encoding="utf-8")
    assert str(repo.resolve()) not in report_text
    assert "S2 has not started" in report_text
    assert "target_name_raw populated: `0`" in report_text
    assert "No row consolidation occurred" in report_text
    assert SYNTHETIC_T not in report_text
    assert SYNTHETIC_U not in report_text
    assert SYNTHETIC_WHITESPACE not in report_text
    assert SYNTHETIC_UNUSUAL not in report_text
    assert SYNTHETIC_MIXED_CASE not in report_text


def test_dispatcher_uses_csv_spine_not_rdf_statement_count(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = repo / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
    rdf_path = (
        repo / "data" / "raw" / "aptamerbase" / "aptamerbase.freebase.extract.nt.gz"
    )
    rows = _demo_rows()
    _write_aptamerbase_csv(input_path, rows)
    _write_synthetic_nt_gz(rdf_path, n_statements=5)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "aptamerbase",
                "source_dataset": EXPECTED_SOURCE_DATASET,
                "path": EXPECTED_PRODUCTION_PATH,
                "sha256": _hash_path(input_path),
                "n_rows_expected": str(len(rows)),
                "snapshot_date": "2026-06-24",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic csv spine",
            },
            {
                "source_key": "aptamerbase",
                "source_dataset": EXPECTED_SOURCE_DATASET,
                "path": EXPECTED_RDF_PATH,
                "sha256": _hash_path(rdf_path),
                "n_rows_expected": "5",
                "snapshot_date": "2026-06-24",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic supporting rdf",
            },
        ],
    )
    result = run_s1_extraction(
        repo_root=repo,
        source_key="aptamerbase",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
    )
    assert result.stats.input_rows == 8
    assert result.stats.canonical_rows == 8
    assert result.registered_path == EXPECTED_PRODUCTION_PATH
    assert EXPECTED_RDF_PATH in result.registered_paths
    assert result.registered_sha256 == _hash_path(input_path)
    canonical = repo / "data" / "interim" / "extracted" / "aptamerbase_extracted.csv"
    with canonical.open(encoding="utf-8", newline="") as handle:
        out_rows = list(csv.DictReader(handle))
    assert len(out_rows) == 8
    assert len(out_rows) != 5


def test_dispatcher_rejects_unknown_source_key(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = repo / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
    _write_aptamerbase_csv(input_path, _demo_rows())
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "not_aptamerbase",
                "source_dataset": "demo",
                "path": EXPECTED_PRODUCTION_PATH,
                "sha256": digest,
                "n_rows_expected": "8",
                "snapshot_date": "2026-06-24",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "must fail",
            }
        ],
    )
    with pytest.raises(S1ExtractError, match="Unknown S1 adapter"):
        run_s1_extraction(
            repo_root=repo,
            source_key="not_aptamerbase",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )


def test_sidecar_write_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.csv"
    _, sidecar = map_aptamerbase_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    write_sidecar_csv_atomic(path, [sidecar])
    first = path.read_bytes()
    write_sidecar_csv_atomic(path, [sidecar])
    assert path.read_bytes() == first
    canonical_path = tmp_path / "extracted.csv"
    canonical, _ = map_aptamerbase_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    write_corpus_csv_atomic(canonical_path, [canonical])
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(SIDECAR_COLUMNS)


@pytest.mark.skipif(
    not (REPO_ROOT / EXPECTED_PRODUCTION_PATH).is_file(),
    reason="Registered AptamerBase CSV not present locally",
)
def test_real_export_2128_in_equals_2128_out_without_embedding_sequences() -> None:
    path = REPO_ROOT / EXPECTED_PRODUCTION_PATH
    result = extract_aptamerbase(
        path,
        source_dataset=EXPECTED_SOURCE_DATASET,
        redistribution_status="unknown",
        expected_rows=EXPECTED_INPUT_ROWS,
    )
    assert result.stats.input_rows == EXPECTED_INPUT_ROWS
    assert result.stats.canonical_rows == EXPECTED_INPUT_ROWS
    assert result.stats.sidecar_rows == EXPECTED_INPUT_ROWS
    assert result.stats.unique_native_ids == EXPECTED_INPUT_ROWS
    assert result.stats.unique_record_ids == EXPECTED_INPUT_ROWS
    assert result.stats.empty_sequences == EXPECTED_EMPTY_SEQUENCES
    assert result.stats.sequence_na_text == EXPECTED_SEQUENCE_NA_TEXT
    assert result.stats.other_nonempty_sequences == EXPECTED_OTHER_NONEMPTY_SEQUENCES
    assert result.stats.nonempty_sequences == EXPECTED_NONEMPTY_SEQUENCES
    assert result.stats.nonempty_targets == 0
    assert result.stats.nonempty_publication == 0
    assert result.stats.nonempty_doi == 0
    assert result.stats.nonempty_pmid == 0
    assert result.stats.unique_freebase_ids == EXPECTED_UNIQUE_FREEBASE_IDS
    assert (
        result.stats.duplicate_freebase_id_groups
        == EXPECTED_DUPLICATE_FREEBASE_ID_GROUPS
    )
    assert (
        result.stats.rows_in_duplicate_freebase_id_groups
        == EXPECTED_ROWS_IN_DUPLICATE_FREEBASE_ID_GROUPS
    )
    assert (
        result.stats.exact_duplicate_complete_row_groups
        == EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS
    )
    assert (
        result.stats.rows_in_exact_duplicate_complete_row_groups
        == EXPECTED_ROWS_IN_EXACT_DUPLICATE_COMPLETE_ROW_GROUPS
    )
    assert (
        result.stats.exact_duplicate_complete_row_excess
        == EXPECTED_EXACT_DUPLICATE_COMPLETE_ROW_EXCESS
    )
    assert result.stats.type_counts[TYPE_APTAMER] == EXPECTED_TYPE_APTAMER
    assert (
        result.stats.type_counts[TYPE_SECONDARY_STRUCTURE]
        == EXPECTED_TYPE_SECONDARY_STRUCTURE
    )
    assert (
        result.stats.type_counts[TYPE_PREDICTED_STRUCTURE]
        == EXPECTED_TYPE_PREDICTED_STRUCTURE
    )
    assert (
        result.stats.has_minimal_aptamer_nonempty
        == EXPECTED_HAS_MINIMAL_APTAMER_NONEMPTY
    )
    assert (
        result.stats.is_minimal_aptamer_of_nonempty
        == EXPECTED_IS_MINIMAL_APTAMER_OF_NONEMPTY
    )
    assert (
        result.stats.has_mutational_analysis_true
        == EXPECTED_HAS_MUTATIONAL_ANALYSIS_TRUE
    )
    assert (
        result.stats.has_mutational_analysis_false
        == EXPECTED_HAS_MUTATIONAL_ANALYSIS_FALSE
    )
    assert (
        result.stats.has_mutational_analysis_blank
        == EXPECTED_HAS_MUTATIONAL_ANALYSIS_BLANK
    )
    assert (
        result.stats.has_experimentally_determined_structure_true
        == EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_TRUE
    )
    assert (
        result.stats.has_experimentally_determined_structure_false
        == EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_FALSE
    )
    assert (
        result.stats.has_experimentally_determined_structure_blank
        == EXPECTED_HAS_EXPERIMENTAL_STRUCTURE_BLANK
    )
    assert result.stats.first_native_id == EXPECTED_FIRST_NATIVE_ID
    assert result.stats.last_native_id == EXPECTED_LAST_NATIVE_ID
    assert result.canonical_rows[0]["record_id"] == "aptamerbase:0001"
    assert result.canonical_rows[-1]["record_id"] == "aptamerbase:2128"
    assert all(row["source_db"] == "aptamerbase" for row in result.canonical_rows)
    assert all(row["target_name_raw"] == "" for row in result.canonical_rows)
    assert all(row["molecule_type"] == "" for row in result.canonical_rows)
    assert all(row["pdb_id"] == "" for row in result.canonical_rows)
    assert result.stats.sequence_exact_copy_ok is True
    assert result.stats.no_row_consolidation is True
