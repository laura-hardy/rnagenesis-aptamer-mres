"""Tests for AptaDiff Dataset A/B S1 adapters (synthetic fixtures only).

Real AptaDiff sequences are never embedded in fixtures. The optional
local-only production skipif gates assert counts without writing sequences
into this file.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters import ADAPTER_KEYS  # noqa: E402
from adapters.aptadiff import (  # noqa: E402
    APTADIFF_INPUT_COLUMNS,
    APTADIFF_SOURCE_KEYS,
    SIDECAR_COLUMNS,
    SOURCE_PROFILES,
    AptaDiffAdapterError,
    extract_aptadiff_a,
    extract_aptadiff_b,
    format_native_id,
    map_aptadiff_row,
    profile_for_source,
    read_aptadiff_rows,
    validate_aptadiff_header,
    write_sidecar_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
    write_corpus_csv_atomic,
)
from s0_build_registry import (  # noqa: E402
    REQUIRED_COLUMNS,
    RegistryError,
    RegistrySpecRow,
    load_registry_spec,
    validate_registered_file,
)
from s1_extract import (  # noqa: E402
    S1ExtractError,
    run_s1_extraction,
)

EXPECTED_A_DATASET = "aptadiff_a_igfbp3_p6_2026-06-22"
EXPECTED_B_DATASET = "aptadiff_b_ptk7_p6_2026-06-22"
EXPECTED_A_PATH = "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv"
EXPECTED_B_PATH = "data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv"
EXPECTED_A_SHA256 = (
    "ec970c478aaba1aa089ecbaf7f5bc8aa7a11f6eacd0f7b3d3c418de6a27e8c77"
)
EXPECTED_B_SHA256 = (
    "546de810e34035731502caf6476c73cc06feab8156ec8178efaade2d21bf4d72"
)
FORBIDDEN_APTADIFF_PATHS = {
    "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_x_z.csv",
    "data/raw/Aptadiff_otherdata/datasetC.fastq",
    "data/raw/Aptadiff_otherdata/datasetD.fastq",
    "data/raw/Aptadiff_datasetA/aptadiff_repo_readme.rtf",
}

SYNTHETIC_T = "ZzTtQq"
SYNTHETIC_U = "ZzUuQq"
SYNTHETIC_N = "ZzNnQq"
SYNTHETIC_WHITESPACE = "  ZZ QQ  "
SYNTHETIC_MIXED_CASE = "aAtTgGcCxx"
SYNTHETIC_DUP = "ZzQqAa"


def _blank_source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in APTADIFF_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_aptadiff_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(APTADIFF_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {col: row.get(col, "") for col in APTADIFF_INPUT_COLUMNS}
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


def _demo_rows() -> list[dict[str, str]]:
    """Synthetic rows covering duplicates, N, mixed alphabets, and p6 tokens."""
    return [
        _blank_source_row(seq=SYNTHETIC_T, p6="5"),
        _blank_source_row(seq=SYNTHETIC_DUP, p6="9"),
        _blank_source_row(seq=SYNTHETIC_DUP, p6="9"),
        _blank_source_row(seq=SYNTHETIC_N, p6="194981"),
        _blank_source_row(seq=SYNTHETIC_U, p6="2"),
        _blank_source_row(seq=SYNTHETIC_WHITESPACE, p6=" 12 "),
        _blank_source_row(seq=SYNTHETIC_MIXED_CASE, p6="4"),
    ]


def _spec_row(
    *,
    source_key: str,
    source_dataset: str,
    path: str,
    sha256: str,
    n_rows: int,
) -> dict[str, str]:
    return {
        "source_key": source_key,
        "source_dataset": source_dataset,
        "path": path,
        "sha256": sha256,
        "n_rows_expected": str(n_rows),
        "snapshot_date": "2026-06-22",
        "tier": "1",
        "redistribution_status": "unknown",
        "notes": "synthetic",
    }


def test_adapter_dispatch_recognises_both_aptadiff_keys() -> None:
    assert "aptadiff_a" in ADAPTER_KEYS
    assert "aptadiff_b" in ADAPTER_KEYS
    assert "aptadiff" not in ADAPTER_KEYS
    from s1_extract import _get_adapter

    assert _get_adapter("aptadiff_a") is extract_aptadiff_a
    assert _get_adapter("aptadiff_b") is extract_aptadiff_b
    assert APTADIFF_SOURCE_KEYS == frozenset({"aptadiff_a", "aptadiff_b"})


def test_tracked_registry_spec_registers_two_distinct_aptadiff_sources() -> None:
    rows = load_registry_spec(REPO_ROOT / "config" / "source_registry.csv")
    a_rows = [row for row in rows if row.source_key == "aptadiff_a"]
    b_rows = [row for row in rows if row.source_key == "aptadiff_b"]
    assert len(a_rows) == 1
    assert len(b_rows) == 1
    a_row, b_row = a_rows[0], b_rows[0]
    assert a_row.source_dataset == EXPECTED_A_DATASET
    assert b_row.source_dataset == EXPECTED_B_DATASET
    assert a_row.source_dataset != b_row.source_dataset
    assert a_row.path == EXPECTED_A_PATH
    assert b_row.path == EXPECTED_B_PATH
    assert a_row.sha256 == EXPECTED_A_SHA256
    assert b_row.sha256 == EXPECTED_B_SHA256
    assert a_row.n_rows_expected == 13803
    assert b_row.n_rows_expected == 11547
    assert a_row.snapshot_date == "2026-06-22"
    assert b_row.snapshot_date == "2026-06-22"
    assert a_row.tier == "1"
    assert b_row.tier == "1"
    assert a_row.redistribution_status == "unknown"
    assert b_row.redistribution_status == "unknown"
    assert "IGFBP3" in a_row.notes
    assert "PTK7" in b_row.notes
    assert "DRA009383" in a_row.notes
    assert "DRA009384" in b_row.notes
    assert "x_z" in a_row.notes
    assert "uncapped replication" in a_row.notes
    assert "Dataset C" in b_row.notes
    assert "No capping" in a_row.notes
    assert "No capping" in b_row.notes
    assert not any(row.source_key == "aptadiff" for row in rows)
    registered_paths = {row.path for row in rows}
    assert FORBIDDEN_APTADIFF_PATHS.isdisjoint(registered_paths)


def test_exact_schema_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    _write_aptadiff_csv(path, _demo_rows())
    result = extract_aptadiff_a(
        path,
        source_dataset="demo_a",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 7
    assert result.stats.canonical_rows == 7
    validate_aptadiff_header(list(APTADIFF_INPUT_COLUMNS))


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    _write_csv(path, ["seq"], [{"seq": SYNTHETIC_T}])
    with pytest.raises(AptaDiffAdapterError, match="missing"):
        extract_aptadiff_a(
            path,
            source_dataset="demo_a",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_extra_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    _write_csv(
        path,
        ["seq", "p6", "extra_col"],
        [{"seq": SYNTHETIC_T, "p6": "5", "extra_col": "x"}],
    )
    with pytest.raises(AptaDiffAdapterError, match="extra"):
        extract_aptadiff_a(
            path,
            source_dataset="demo_a",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_reordered_columns_rejected(tmp_path: Path) -> None:
    path = tmp_path / "reordered.csv"
    _write_csv(path, ["p6", "seq"], [{"p6": "5", "seq": SYNTHETIC_T}])
    with pytest.raises(AptaDiffAdapterError, match="reordered"):
        extract_aptadiff_a(
            path,
            source_dataset="demo_a",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_every_source_row_is_retained_including_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "preserve.csv"
    rows = _demo_rows()
    _write_aptadiff_csv(path, rows)
    result = extract_aptadiff_a(
        path,
        source_dataset="demo_a",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == len(rows)
    assert result.stats.canonical_rows == len(rows)
    assert result.stats.sidecar_rows == len(rows)
    assert result.stats.no_row_consolidation is True
    assert result.stats.duplicate_sequence_groups == 1
    assert result.stats.rows_in_duplicate_sequence_groups == 2
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        r["seq"] for r in rows
    ]
    assert result.canonical_rows[1]["record_id"] != result.canonical_rows[2]["record_id"]
    assert result.canonical_rows[1]["sequence_raw"] == SYNTHETIC_DUP
    assert result.canonical_rows[2]["sequence_raw"] == SYNTHETIC_DUP


@pytest.mark.parametrize(
    "sequence",
    [
        SYNTHETIC_T,
        SYNTHETIC_U,
        SYNTHETIC_N,
        SYNTHETIC_WHITESPACE,
        SYNTHETIC_MIXED_CASE,
        "",
    ],
)
def test_sequence_raw_copied_verbatim(sequence: str) -> None:
    source = _blank_source_row(seq=sequence, p6="5")
    canonical, sidecar = map_aptadiff_row(
        source,
        csv_data_row=1,
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        redistribution_status="unknown",
    )
    assert canonical["sequence_raw"] == sequence
    assert sidecar["aptadiff_seq"] == sequence
    assert canonical["sequence_raw"] != sequence.upper() or sequence == sequence.upper()


def test_p6_preserved_exactly_in_sidecar() -> None:
    source = _blank_source_row(seq=SYNTHETIC_T, p6=" 12 ")
    _, sidecar = map_aptadiff_row(
        source,
        csv_data_row=3,
        source_key="aptadiff_b",
        source_dataset=EXPECTED_B_DATASET,
        redistribution_status="unknown",
    )
    assert sidecar["aptadiff_p6"] == " 12 "


def test_row_based_native_ids_are_zero_padded_five_digits() -> None:
    assert format_native_id(1) == "00001"
    assert format_native_id(13803) == "13803"
    assert format_native_id(11547) == "11547"
    canonical_a, sidecar_a = map_aptadiff_row(
        _blank_source_row(seq=SYNTHETIC_T, p6="5"),
        csv_data_row=7,
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        redistribution_status="unknown",
    )
    canonical_b, sidecar_b = map_aptadiff_row(
        _blank_source_row(seq=SYNTHETIC_T, p6="5"),
        csv_data_row=7,
        source_key="aptadiff_b",
        source_dataset=EXPECTED_B_DATASET,
        redistribution_status="unknown",
    )
    assert canonical_a["native_id"] == "00007"
    assert canonical_b["native_id"] == "00007"
    assert canonical_a["record_id"] == "aptadiff_a:00007"
    assert canonical_b["record_id"] == "aptadiff_b:00007"
    assert sidecar_a["aptadiff_csv_data_row"] == "7"
    assert sidecar_b["aptadiff_source_key"] == "aptadiff_b"


def test_a_and_b_have_distinct_record_id_namespaces(tmp_path: Path) -> None:
    path = tmp_path / "shared.csv"
    _write_aptadiff_csv(path, _demo_rows()[:2])
    a_result = extract_aptadiff_a(
        path,
        source_dataset="demo_a",
        redistribution_status="unknown",
        expected_rows=None,
    )
    b_result = extract_aptadiff_b(
        path,
        source_dataset="demo_b",
        redistribution_status="unknown",
        expected_rows=None,
    )
    a_ids = {row["record_id"] for row in a_result.canonical_rows}
    b_ids = {row["record_id"] for row in b_result.canonical_rows}
    assert a_ids.isdisjoint(b_ids)
    assert all(record_id.startswith("aptadiff_a:") for record_id in a_ids)
    assert all(record_id.startswith("aptadiff_b:") for record_id in b_ids)


def test_s1_forbidden_fields_remain_empty() -> None:
    canonical, sidecar = map_aptadiff_row(
        _blank_source_row(seq=SYNTHETIC_T, p6="5"),
        csv_data_row=1,
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        redistribution_status="unknown",
    )
    for field in S1_FORBIDDEN_FIELDS:
        assert canonical[field] == "", field
    assert canonical["target_name_raw"] == ""
    assert canonical["molecule_type"] == ""
    assert canonical["chemistry"] == ""
    assert canonical["alphabet_as_reported"] == ""
    assert canonical["t_to_u_applied"] == ""
    assert canonical["sequence_full"] == ""
    assert canonical["sequence_core"] == ""
    assert canonical["construct_scope"] == ""
    assert canonical["target_name"] == ""
    assert canonical["target_uniprot"] == ""
    assert canonical["binding_evidence_score"] == ""
    assert canonical["affinity_value"] == ""
    assert canonical["cluster_id"] == ""
    assert canonical["partition"] == ""
    assert sidecar["aptadiff_documented_target"] == "IGFBP3"
    assert "DRA009383" in sidecar["aptadiff_target_provenance"]
    assert sidecar["aptadiff_dataset"] == "A"


def test_documented_target_is_sidecar_only_not_manufactured_as_csv_value() -> None:
    _, sidecar_a = map_aptadiff_row(
        _blank_source_row(seq=SYNTHETIC_T, p6="5"),
        csv_data_row=1,
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        redistribution_status="unknown",
    )
    _, sidecar_b = map_aptadiff_row(
        _blank_source_row(seq=SYNTHETIC_T, p6="5"),
        csv_data_row=1,
        source_key="aptadiff_b",
        source_dataset=EXPECTED_B_DATASET,
        redistribution_status="unknown",
    )
    assert sidecar_a["aptadiff_documented_target"] == "IGFBP3"
    assert sidecar_b["aptadiff_documented_target"] == "PTK7"
    assert sidecar_a["aptadiff_seq"] == SYNTHETIC_T
    assert "IGFBP3" not in sidecar_a["aptadiff_seq"]


def test_n_containing_rows_are_retained(tmp_path: Path) -> None:
    path = tmp_path / "n_rows.csv"
    _write_aptadiff_csv(path, _demo_rows())
    result = extract_aptadiff_b(
        path,
        source_dataset="demo_b",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.n_containing == 1
    assert result.canonical_rows[3]["sequence_raw"] == SYNTHETIC_N
    assert len(result.canonical_rows) == 7


def test_source_order_preserved(tmp_path: Path) -> None:
    path = tmp_path / "order.csv"
    rows = _demo_rows()
    _write_aptadiff_csv(path, rows)
    result = extract_aptadiff_a(
        path,
        source_dataset="demo_a",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.order_preserved is True
    assert [row["aptadiff_p6"] for row in result.sidecar_rows] == [
        r["p6"] for r in rows
    ]


def test_registration_rejects_hash_mismatch_through_s0(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    input_path = repo / EXPECTED_A_PATH
    _write_aptadiff_csv(input_path, _demo_rows()[:2])
    row = RegistrySpecRow(
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        path=EXPECTED_A_PATH,
        sha256="0" * 64,
        n_rows_expected=2,
        snapshot_date="2026-06-22",
        tier="1",
        redistribution_status="unknown",
        notes="synthetic",
    )
    with pytest.raises(RegistryError, match="SHA-256"):
        validate_registered_file(repo, row)


def test_registration_rejects_row_mismatch_through_s0(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    input_path = repo / EXPECTED_A_PATH
    _write_aptadiff_csv(input_path, _demo_rows()[:2])
    row = RegistrySpecRow(
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        path=EXPECTED_A_PATH,
        sha256=_hash_path(input_path),
        n_rows_expected=13803,
        snapshot_date="2026-06-22",
        tier="1",
        redistribution_status="unknown",
        notes="synthetic",
    )
    with pytest.raises(RegistryError, match="[Rr]ow"):
        validate_registered_file(repo, row)


def _make_s1_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "Aptadiff_datasetA").mkdir(parents=True)
    (repo / "data" / "raw" / "Aptadiff_otherdata").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def _install_both_sources(repo: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    a_rows = _demo_rows()
    b_rows = list(reversed(_demo_rows()))
    a_path = repo / EXPECTED_A_PATH
    b_path = repo / EXPECTED_B_PATH
    _write_aptadiff_csv(a_path, a_rows)
    _write_aptadiff_csv(b_path, b_rows)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptadiff_a",
                source_dataset=EXPECTED_A_DATASET,
                path=EXPECTED_A_PATH,
                sha256=_hash_path(a_path),
                n_rows=len(a_rows),
            ),
            _spec_row(
                source_key="aptadiff_b",
                source_dataset=EXPECTED_B_DATASET,
                path=EXPECTED_B_PATH,
                sha256=_hash_path(b_path),
                n_rows=len(b_rows),
            ),
        ],
    )
    return a_rows, b_rows


def test_both_source_keys_dispatch_independently(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    a_rows, b_rows = _install_both_sources(repo)
    spec = repo / "config" / "source_registry.csv"
    a_result = run_s1_extraction(
        repo_root=repo,
        source_key="aptadiff_a",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    b_result = run_s1_extraction(
        repo_root=repo,
        source_key="aptadiff_b",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert a_result.stats.input_rows == len(a_rows)
    assert b_result.stats.input_rows == len(b_rows)
    assert a_result.deterministic_rerun_ok is True
    assert b_result.deterministic_rerun_ok is True
    a_canonical = repo / "data" / "interim" / "extracted" / "aptadiff_a_extracted.csv"
    b_canonical = repo / "data" / "interim" / "extracted" / "aptadiff_b_extracted.csv"
    a_sidecar = (
        repo / "data" / "interim" / "extracted" / "aptadiff_a_source_metadata.csv"
    )
    b_sidecar = (
        repo / "data" / "interim" / "extracted" / "aptadiff_b_source_metadata.csv"
    )
    assert a_canonical.is_file()
    assert b_canonical.is_file()
    assert a_canonical != b_canonical
    with a_canonical.open(encoding="utf-8", newline="") as handle:
        a_out = list(csv.DictReader(handle))
    with b_canonical.open(encoding="utf-8", newline="") as handle:
        b_out = list(csv.DictReader(handle))
    assert [row["sequence_raw"] for row in a_out] == [r["seq"] for r in a_rows]
    assert [row["sequence_raw"] for row in b_out] == [r["seq"] for r in b_rows]
    assert [row["record_id"] for row in a_out][0].startswith("aptadiff_a:")
    assert [row["record_id"] for row in b_out][0].startswith("aptadiff_b:")
    with a_sidecar.open(encoding="utf-8", newline="") as handle:
        a_side = list(csv.DictReader(handle))
    with b_sidecar.open(encoding="utf-8", newline="") as handle:
        b_side = list(csv.DictReader(handle))
    assert [row["aptadiff_p6"] for row in a_side] == [r["p6"] for r in a_rows]
    assert [row["aptadiff_p6"] for row in b_side] == [r["p6"] for r in b_rows]
    assert all(row["aptadiff_documented_target"] == "IGFBP3" for row in a_side)
    assert all(row["aptadiff_documented_target"] == "PTK7" for row in b_side)
    report_a = (
        repo / "data" / "interim" / "extracted" / "aptadiff_a_s1_report.md"
    ).read_text(encoding="utf-8")
    assert "S2 has not started" in report_a
    assert SYNTHETIC_T not in report_a
    assert str(repo.resolve()) not in report_a


def test_dispatcher_rejects_xz_c_d_as_a_or_b_inputs(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    forbidden = repo / "data" / "raw" / "Aptadiff_datasetA" / "datasetA_IGFBP3_x_z.csv"
    _write_aptadiff_csv(forbidden, _demo_rows()[:2])
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptadiff_a",
                source_dataset=EXPECTED_A_DATASET,
                path="data/raw/Aptadiff_datasetA/datasetA_IGFBP3_x_z.csv",
                sha256=_hash_path(forbidden),
                n_rows=2,
            )
        ],
    )
    with pytest.raises((RegistryError, S1ExtractError), match="[Ff]orbidden|must be"):
        run_s1_extraction(
            repo_root=repo,
            source_key="aptadiff_a",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )


def test_dispatcher_rejects_cross_wired_a_b_basenames(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    b_path = repo / EXPECTED_B_PATH
    _write_aptadiff_csv(b_path, _demo_rows()[:2])
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptadiff_a",
                source_dataset=EXPECTED_A_DATASET,
                path=EXPECTED_B_PATH,
                sha256=_hash_path(b_path),
                n_rows=2,
            )
        ],
    )
    with pytest.raises(S1ExtractError, match="datasetA_IGFBP3_P6.csv"):
        run_s1_extraction(
            repo_root=repo,
            source_key="aptadiff_a",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )


def test_dispatcher_rejects_sha_mismatch_before_outputs(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    a_path = repo / EXPECTED_A_PATH
    _write_aptadiff_csv(a_path, _demo_rows()[:2])
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptadiff_a",
                source_dataset=EXPECTED_A_DATASET,
                path=EXPECTED_A_PATH,
                sha256="0" * 64,
                n_rows=2,
            )
        ],
    )
    with pytest.raises((RegistryError, S1ExtractError), match="SHA-256|sha256"):
        run_s1_extraction(
            repo_root=repo,
            source_key="aptadiff_a",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )
    assert not (
        repo / "data" / "interim" / "extracted" / "aptadiff_a_extracted.csv"
    ).exists()


def test_sidecar_write_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.csv"
    _, sidecar = map_aptadiff_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_key="aptadiff_a",
        source_dataset="demo_a",
        redistribution_status="unknown",
    )
    write_sidecar_csv_atomic(path, [sidecar])
    first = path.read_bytes()
    write_sidecar_csv_atomic(path, [sidecar])
    assert path.read_bytes() == first
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(SIDECAR_COLUMNS)


def test_repeated_extraction_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "repeat.csv"
    _write_aptadiff_csv(path, _demo_rows())
    kwargs = dict(
        source_dataset="demo_a",
        redistribution_status="unknown",
        expected_rows=None,
    )
    first = extract_aptadiff_a(path, **kwargs)
    second = extract_aptadiff_a(path, **kwargs)
    assert first.canonical_rows == second.canonical_rows
    assert first.sidecar_rows == second.sidecar_rows
    canonical_path = tmp_path / "extracted.csv"
    write_corpus_csv_atomic(canonical_path, first.canonical_rows)
    first_bytes = canonical_path.read_bytes()
    write_corpus_csv_atomic(canonical_path, second.canonical_rows)
    assert canonical_path.read_bytes() == first_bytes


def test_stage_schema_compliance() -> None:
    canonical, sidecar = map_aptadiff_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_key="aptadiff_a",
        source_dataset=EXPECTED_A_DATASET,
        redistribution_status="unknown",
    )
    assert list(canonical.keys()) == list(CORPUS_COLUMNS)
    assert list(sidecar.keys()) == list(SIDECAR_COLUMNS)
    assert canonical["source_db"] == "aptadiff_a"
    assert canonical["contributing_sources"] == "aptadiff_a"
    assert canonical["corroboration_count"] == "1"
    assert canonical["independently_attested_by_permissive_source"] == "false"


def test_production_row_count_gate_rejects_non_production_size(tmp_path: Path) -> None:
    path = tmp_path / "small.csv"
    _write_aptadiff_csv(path, _demo_rows())
    with pytest.raises(AptaDiffAdapterError, match="13803"):
        extract_aptadiff_a(
            path,
            source_dataset=EXPECTED_A_DATASET,
            redistribution_status="unknown",
            expected_rows=SOURCE_PROFILES["aptadiff_a"].expected_input_rows,
        )
    with pytest.raises(AptaDiffAdapterError, match="11547"):
        extract_aptadiff_b(
            path,
            source_dataset=EXPECTED_B_DATASET,
            redistribution_status="unknown",
            expected_rows=SOURCE_PROFILES["aptadiff_b"].expected_input_rows,
        )


def test_combined_aptadiff_key_is_rejected() -> None:
    with pytest.raises(AptaDiffAdapterError, match="Unknown AptaDiff source_key"):
        profile_for_source("aptadiff")
    from s1_extract import _get_adapter

    with pytest.raises(S1ExtractError, match="Unknown S1 adapter"):
        _get_adapter("aptadiff")


def test_read_aptadiff_rows_is_schema_neutral(tmp_path: Path) -> None:
    path = tmp_path / "shared.csv"
    _write_aptadiff_csv(path, _demo_rows())
    rows = read_aptadiff_rows(path)
    assert [row["seq"] for row in rows] == [r["seq"] for r in _demo_rows()]
    assert [row["p6"] for row in rows] == [r["p6"] for r in _demo_rows()]


@pytest.mark.skipif(
    not (REPO_ROOT / EXPECTED_A_PATH).is_file(),
    reason="Registered AptaDiff Dataset A P6 CSV not present locally",
)
def test_real_dataset_a_13803_in_equals_13803_out_without_embedding_sequences() -> None:
    path = REPO_ROOT / EXPECTED_A_PATH
    before = _hash_path(path)
    assert before == EXPECTED_A_SHA256
    result = extract_aptadiff_a(
        path,
        source_dataset=EXPECTED_A_DATASET,
        redistribution_status="unknown",
        expected_rows=13803,
    )
    assert result.stats.input_rows == 13803
    assert result.stats.canonical_rows == 13803
    assert result.stats.sidecar_rows == 13803
    assert result.stats.unique_native_ids == 13803
    assert result.stats.unique_record_ids == 13803
    assert result.stats.n_containing == 1
    assert result.stats.acgt_only == 13802
    assert result.stats.length_36 == 13803
    assert result.stats.duplicate_sequence_groups == 0
    assert result.stats.nonempty_target_name_raw == 0
    assert result.canonical_rows[0]["record_id"] == "aptadiff_a:00001"
    assert result.canonical_rows[-1]["record_id"] == "aptadiff_a:13803"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        row["seq"] for row in source_rows
    ]
    assert [row["aptadiff_p6"] for row in result.sidecar_rows] == [
        row["p6"] for row in source_rows
    ]
    assert _hash_path(path) == before
    assert all(row["target_name_raw"] == "" for row in result.canonical_rows)
    assert all(row["molecule_type"] == "" for row in result.canonical_rows)


@pytest.mark.skipif(
    not (REPO_ROOT / EXPECTED_B_PATH).is_file(),
    reason="Registered AptaDiff Dataset B P6 CSV not present locally",
)
def test_real_dataset_b_11547_in_equals_11547_out_without_embedding_sequences() -> None:
    path = REPO_ROOT / EXPECTED_B_PATH
    before = _hash_path(path)
    assert before == EXPECTED_B_SHA256
    result = extract_aptadiff_b(
        path,
        source_dataset=EXPECTED_B_DATASET,
        redistribution_status="unknown",
        expected_rows=11547,
    )
    assert result.stats.input_rows == 11547
    assert result.stats.canonical_rows == 11547
    assert result.stats.sidecar_rows == 11547
    assert result.stats.unique_native_ids == 11547
    assert result.stats.unique_record_ids == 11547
    assert result.stats.n_containing == 15
    assert result.stats.acgt_only == 11532
    assert result.stats.length_36 == 11547
    assert result.stats.duplicate_sequence_groups == 0
    assert result.canonical_rows[0]["record_id"] == "aptadiff_b:00001"
    assert result.canonical_rows[-1]["record_id"] == "aptadiff_b:11547"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        row["seq"] for row in source_rows
    ]
    assert [row["aptadiff_p6"] for row in result.sidecar_rows] == [
        row["p6"] for row in source_rows
    ]
    assert _hash_path(path) == before
    assert all(row["target_name_raw"] == "" for row in result.canonical_rows)
    assert all(row["molecule_type"] == "" for row in result.canonical_rows)
