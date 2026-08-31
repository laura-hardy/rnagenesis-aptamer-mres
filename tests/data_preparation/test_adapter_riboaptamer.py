"""Tests for the RiboAptamer S1 adapter (synthetic fixtures only).

Real RiboAptamer aptamer sequences are never embedded in fixtures except
in the optional local-only production skipif gate, which asserts counts
without writing sequences into this file.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.riboaptamer import (  # noqa: E402
    EXPECTED_DUPLICATE_SEQUENCE_NAME_KEYS,
    EXPECTED_EMPTY_TARGET_NAME_RAW,
    EXPECTED_FIRST_NATIVE_ID,
    EXPECTED_INPUT_ROWS,
    EXPECTED_LAST_NATIVE_ID,
    EXPECTED_NONEMPTY_PMID,
    EXPECTED_NONEMPTY_SEQUENCES,
    EXPECTED_ROWS_IN_DUPLICATE_SEQUENCE_NAME_GROUPS,
    EXPECTED_UNIQUE_SEQUENCE_NAMES,
    RIBOAPTAMER_INPUT_COLUMNS,
    SIDECAR_COLUMNS,
    RiboAptamerAdapterError,
    encode_category_prior_notes,
    extract_pubmed_id,
    extract_riboaptamer,
    format_native_id,
    map_riboaptamer_row,
    read_riboaptamer_rows,
    validate_riboaptamer_header,
    write_sidecar_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
)
from s0_build_registry import REQUIRED_COLUMNS, RegistryError  # noqa: E402
from s1_extract import (  # noqa: E402
    S1ExtractError,
    run_s1_extraction,
)


def _blank_source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in RIBOAPTAMER_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_riboaptamer_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(RIBOAPTAMER_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {col: row.get(col, "") for col in RIBOAPTAMER_INPUT_COLUMNS}
            )


def _write_csv_with_header(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _demo_rows() -> list[dict[str, str]]:
    """Three synthetic rows, two sharing Sequence Name (not used as native_id)."""
    return [
        _blank_source_row(
            **{
                "Sequence Name": "shared_label",
                "Aptamer Name": "Apt-A",
                "Category": "Mammalian",
                "Type": "Proteins",
                "Article name": "clone-A",
                "Sequence": "ACGUACGU",
                "Length": "8",
                "GC Content": "50",
                "Discovery Year": "1990",
                "Affinity (Kd)": "1 nM",
                "Description": "binds protein A",
                "PubMed Link": "https://pubmed.ncbi.nlm.nih.gov/1697402/",
                "mmCIF Download URL": "https://example.invalid/a.cif",
            }
        ),
        _blank_source_row(
            **{
                "Sequence Name": "shared_label",
                "Aptamer Name": "Apt-B",
                "Category": "Viral",
                "Type": "Small molecules",
                "Article name": "clone-B",
                "Sequence": " 5'-UGCA-3' ",
                "Length": "4",
                "GC Content": "50",
                "Discovery Year": "1991",
                "Affinity (Kd)": "2 nM",
                "Description": "binds ligand B",
                "PubMed Link": "https://pubs.acs.org/doi/10.1021/ja00084a010",
                "mmCIF Download URL": "https://example.invalid/b.cif",
            }
        ),
        _blank_source_row(
            **{
                "Sequence Name": "unique_label",
                "Aptamer Name": "Apt-C",
                "Category": "Cell",
                "Type": "Cells",
                "Article name": "clone-C",
                "Sequence": "GGCC",
                "Length": "4",
                "GC Content": "100",
                "Discovery Year": "1992",
                "Affinity (Kd)": "3 nM",
                "Description": "cell binder",
                "PubMed Link": "https://pubmed.ncbi.nlm.nih.gov/2200121/",
                "mmCIF Download URL": "https://example.invalid/c.cif",
            }
        ),
    ]


def test_exact_schema_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    _write_riboaptamer_csv(path, _demo_rows())
    result = extract_riboaptamer(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 3
    assert result.stats.canonical_rows == 3
    validate_riboaptamer_header(list(RIBOAPTAMER_INPUT_COLUMNS))


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    cols = list(RIBOAPTAMER_INPUT_COLUMNS)
    cols.remove("Description")
    _write_csv_with_header(path, cols, [_blank_source_row()])
    with pytest.raises(RiboAptamerAdapterError, match="missing"):
        extract_riboaptamer(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_extra_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    cols = list(RIBOAPTAMER_INPUT_COLUMNS) + ["extra_col"]
    _write_csv_with_header(
        path,
        cols,
        [{**_blank_source_row(), "extra_col": "x"}],
    )
    with pytest.raises(RiboAptamerAdapterError, match="extra"):
        extract_riboaptamer(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_reordered_columns_rejected(tmp_path: Path) -> None:
    path = tmp_path / "reordered.csv"
    cols = list(RIBOAPTAMER_INPUT_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    _write_csv_with_header(path, cols, [_blank_source_row()])
    with pytest.raises(RiboAptamerAdapterError, match="reordered"):
        extract_riboaptamer(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_row_based_native_ids_are_zero_padded() -> None:
    assert format_native_id(1) == "001"
    assert format_native_id(509) == "509"
    source = _blank_source_row(**{"Sequence": "ACGU"})
    canonical, sidecar = map_riboaptamer_row(
        source,
        csv_data_row=7,
        source_dataset="riboaptamer_full_2026-08",
        redistribution_status="unknown",
    )
    assert canonical["native_id"] == "007"
    assert canonical["record_id"] == "riboaptamer:007"
    assert sidecar["record_id"] == "riboaptamer:007"
    assert sidecar["riboaptamer_native_id"] == "007"
    assert sidecar["riboaptamer_csv_data_row"] == "7"


def test_duplicate_sequence_names_do_not_collide(tmp_path: Path) -> None:
    path = tmp_path / "dups.csv"
    _write_riboaptamer_csv(path, _demo_rows())
    result = extract_riboaptamer(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    ids = [row["record_id"] for row in result.canonical_rows]
    native = [row["native_id"] for row in result.canonical_rows]
    names = [
        row["riboaptamer_sequence_name"] for row in result.sidecar_rows
    ]
    assert ids == ["riboaptamer:001", "riboaptamer:002", "riboaptamer:003"]
    assert native == ["001", "002", "003"]
    assert names[0] == names[1] == "shared_label"
    assert len(set(ids)) == 3
    assert result.stats.duplicate_sequence_name_keys == 1
    assert result.stats.rows_in_duplicate_sequence_name_groups == 2
    assert result.stats.unique_sequence_names == 2


def test_sequence_copied_exactly_including_whitespace_and_terminals() -> None:
    raw = " 5'-ACG U-3' "
    source = _blank_source_row(**{"Sequence": raw, "Type": "Proteins"})
    canonical, sidecar = map_riboaptamer_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["sequence_raw"] == raw
    assert sidecar["riboaptamer_sequence"] == raw
    assert canonical["sequence_full"] == ""
    assert canonical["sequence_core"] == ""


def test_category_and_type_are_not_targets_or_molecule_type() -> None:
    source = _blank_source_row(
        **{
            "Sequence": "ACGU",
            "Category": "Mammalian",
            "Type": "Proteins",
            "Aptamer Name": "theophylline aptamer",
            "Sequence Name": "Theo_1",
            "Description": "binds theophylline",
        }
    )
    canonical, sidecar = map_riboaptamer_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["target_name_raw"] == ""
    assert canonical["target_name"] == ""
    assert canonical["target_type"] == ""
    assert canonical["target_type_source"] == ""
    assert canonical["molecule_type"] == ""
    assert canonical["chemistry"] == ""
    assert canonical["notes"] == encode_category_prior_notes("Mammalian")
    assert sidecar["riboaptamer_category"] == "Mammalian"
    assert sidecar["riboaptamer_type"] == "Proteins"
    assert sidecar["riboaptamer_aptamer_name"] == "theophylline aptamer"
    assert sidecar["riboaptamer_description"] == "binds theophylline"
    assert "Proteins" not in (
        canonical["molecule_type"],
        canonical["target_type"],
        canonical["target_name_raw"],
    )
    assert "Mammalian" not in (
        canonical["molecule_type"],
        canonical["target_type"],
        canonical["target_name_raw"],
    )


def test_article_name_is_not_publication_and_doi_is_not_invented() -> None:
    source = _blank_source_row(
        **{
            "Sequence": "ACGU",
            "Article name": "clone-label-not-a-citation",
            "PubMed Link": "https://pubs.acs.org/doi/10.1021/ja00084a010",
        }
    )
    canonical, sidecar = map_riboaptamer_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["publication"] == ""
    assert canonical["doi"] == ""
    assert canonical["pubmed_id"] == ""
    assert sidecar["riboaptamer_article_name"] == "clone-label-not-a-citation"
    assert sidecar["riboaptamer_pubmed_link"] == (
        "https://pubs.acs.org/doi/10.1021/ja00084a010"
    )


def test_extract_pubmed_id_unambiguous_only() -> None:
    assert (
        extract_pubmed_id("https://pubmed.ncbi.nlm.nih.gov/1697402/") == "1697402"
    )
    assert extract_pubmed_id("1697402") == "1697402"
    assert extract_pubmed_id("https://pubs.acs.org/doi/10.1021/ja00084a010") == ""
    assert extract_pubmed_id("") == ""


def test_later_stage_fields_remain_empty() -> None:
    source = _blank_source_row(
        **{
            "Sequence": "ACGU",
            "Type": "Nucleic acids",
            "Affinity (Kd)": "12 nM",
            "mmCIF Download URL": "https://example.invalid/x.cif",
            "Category": "RNA",
        }
    )
    canonical, _ = map_riboaptamer_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    for field in S1_FORBIDDEN_FIELDS:
        assert canonical[field] == "", field
    assert canonical["pdb_id"] == ""
    assert canonical["binding_evidence_type"] == ""
    assert canonical["affinity_value"] == ""
    assert canonical["affinity_unit"] == ""
    assert canonical["affinity_type"] == ""


def test_all_source_fields_preserved_in_sidecar() -> None:
    source = _demo_rows()[0]
    canonical, sidecar = map_riboaptamer_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert list(sidecar.keys()) == list(SIDECAR_COLUMNS)
    assert sidecar["record_id"] == canonical["record_id"]
    for column, sidecar_col in (
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
    ):
        assert sidecar[sidecar_col] == source[column]


def test_category_prior_notes_deterministic() -> None:
    assert encode_category_prior_notes("") == ""
    notes = encode_category_prior_notes("Mammalian")
    assert notes == json.dumps(
        {"category_prior": "Mammalian"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_order_preserved_and_n_in_equals_n_out(tmp_path: Path) -> None:
    path = tmp_path / "order.csv"
    rows = _demo_rows()
    _write_riboaptamer_csv(path, rows)
    result = extract_riboaptamer(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == result.stats.canonical_rows == 3
    assert result.stats.sidecar_rows == 3
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        r["Sequence"] for r in rows
    ]
    assert result.stats.order_preserved is True
    assert result.stats.empty_target_name_raw == 3
    assert result.stats.nonempty_target_name_raw == 0


def test_synthetic_509_in_equals_509_out(tmp_path: Path) -> None:
    path = tmp_path / "five_oh_nine.csv"
    rows = [
        _blank_source_row(
            **{
                "Sequence Name": "dup_name" if i in {2, 3} else f"name_{i:03d}",
                "Aptamer Name": f"apt_{i}",
                "Category": "Other",
                "Type": "Proteins",
                "Sequence": f"ACGU{i % 4}",
                "PubMed Link": "https://pubmed.ncbi.nlm.nih.gov/1697402/",
            }
        )
        for i in range(1, 510)
    ]
    _write_riboaptamer_csv(path, rows)
    result = extract_riboaptamer(
        path,
        source_dataset="riboaptamer_full_2026-08",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 509
    assert result.stats.canonical_rows == 509
    assert result.stats.sidecar_rows == 509
    assert result.stats.unique_native_ids == 509
    assert result.stats.unique_record_ids == 509
    assert result.canonical_rows[0]["native_id"] == "001"
    assert result.canonical_rows[-1]["native_id"] == "509"
    assert result.canonical_rows[1]["record_id"] == "riboaptamer:002"
    assert result.canonical_rows[2]["record_id"] == "riboaptamer:003"
    assert (
        result.sidecar_rows[1]["riboaptamer_sequence_name"]
        == result.sidecar_rows[2]["riboaptamer_sequence_name"]
        == "dup_name"
    )


def test_production_row_count_gate_rejects_non_509(tmp_path: Path) -> None:
    path = tmp_path / "small.csv"
    _write_riboaptamer_csv(path, _demo_rows())
    with pytest.raises(RiboAptamerAdapterError, match="509"):
        read_riboaptamer_rows(path)


def test_sidecar_write_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.csv"
    _, sidecar = map_riboaptamer_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset="demo_ds",
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
    _write_riboaptamer_csv(path, _demo_rows())
    kwargs = dict(
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    first = extract_riboaptamer(path, **kwargs)
    second = extract_riboaptamer(path, **kwargs)
    assert first.canonical_rows == second.canonical_rows
    assert first.sidecar_rows == second.sidecar_rows


def test_stage_schema_compliance() -> None:
    canonical, _ = map_riboaptamer_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset="riboaptamer_full_2026-08",
        redistribution_status="unknown",
    )
    assert list(canonical.keys()) == list(CORPUS_COLUMNS)
    assert canonical["source_db"] == "riboaptamer"
    assert canonical["source_dataset"] == "riboaptamer_full_2026-08"
    assert canonical["contributing_sources"] == "riboaptamer"
    assert canonical["contributing_datasets"] == "riboaptamer_full_2026-08"
    assert canonical["corroboration_count"] == "1"
    assert canonical["redistribution_status"] == "unknown"
    assert canonical["independently_attested_by_permissive_source"] == "false"


def _make_s1_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "riboaptamer").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def test_dispatcher_round_trip(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = repo / "data" / "raw" / "riboaptamer" / "all_sequences_509_rows.csv"
    rows = _demo_rows()
    _write_riboaptamer_csv(input_path, rows)
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "riboaptamer",
                "source_dataset": "riboaptamer_full_2026-08",
                "path": "data/raw/riboaptamer/all_sequences_509_rows.csv",
                "sha256": digest,
                "n_rows_expected": str(len(rows)),
                "snapshot_date": "2026-08-04",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            }
        ],
    )
    result = run_s1_extraction(
        repo_root=repo,
        source_key="riboaptamer",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert result.stats.input_rows == 3
    assert result.deterministic_rerun_ok is True
    assert result.input_hash_unchanged is True
    canonical = repo / "data" / "interim" / "extracted" / "riboaptamer_extracted.csv"
    sidecar = repo / "data" / "interim" / "extracted" / "riboaptamer_source_metadata.csv"
    report = repo / "data" / "interim" / "extracted" / "riboaptamer_s1_report.md"
    with canonical.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(CORPUS_COLUMNS)
        out_rows = list(reader)
    assert [row["native_id"] for row in out_rows] == ["001", "002", "003"]
    assert out_rows[0]["sequence_raw"] == "ACGUACGU"
    assert all(row["target_name_raw"] == "" for row in out_rows)
    with sidecar.open(encoding="utf-8", newline="") as handle:
        side_reader = csv.DictReader(handle)
        assert list(side_reader.fieldnames or []) == list(SIDECAR_COLUMNS)
        side_rows = list(side_reader)
    assert len(side_rows) == 3
    report_text = report.read_text(encoding="utf-8")
    assert str(repo.resolve()) not in report_text
    assert "S2 has not started" in report_text
    assert "ACGUACGU" not in report_text


def test_dispatcher_rejects_truncated_export(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    truncated = repo / "data" / "raw" / "riboaptamer" / "rna_aptamer_seqs.csv"
    _write_riboaptamer_csv(truncated, _demo_rows())
    digest = _hash_path(truncated)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "riboaptamer",
                "source_dataset": "riboaptamer_truncated_forbidden",
                "path": "data/raw/riboaptamer/rna_aptamer_seqs.csv",
                "sha256": digest,
                "n_rows_expected": "3",
                "snapshot_date": "2026-08-04",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "must fail",
            }
        ],
    )
    with pytest.raises(
        (RegistryError, S1ExtractError), match="[Ff]orbidden|truncated"
    ):
        run_s1_extraction(
            repo_root=repo,
            source_key="riboaptamer",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )


@pytest.mark.skipif(
    not (
        REPO_ROOT / "data/raw/riboaptamer/all_sequences_509_rows.csv"
    ).is_file(),
    reason="Registered RiboAptamer CSV not present locally",
)
def test_real_export_509_in_equals_509_out_without_embedding_sequences() -> None:
    path = REPO_ROOT / "data/raw/riboaptamer/all_sequences_509_rows.csv"
    result = extract_riboaptamer(
        path,
        source_dataset="riboaptamer_full_2026-08",
        redistribution_status="unknown",
        expected_rows=EXPECTED_INPUT_ROWS,
    )
    assert result.stats.input_rows == EXPECTED_INPUT_ROWS
    assert result.stats.canonical_rows == EXPECTED_INPUT_ROWS
    assert result.stats.sidecar_rows == EXPECTED_INPUT_ROWS
    assert result.stats.unique_native_ids == EXPECTED_INPUT_ROWS
    assert result.stats.unique_record_ids == EXPECTED_INPUT_ROWS
    assert result.stats.nonempty_sequences == EXPECTED_NONEMPTY_SEQUENCES
    assert result.stats.empty_target_name_raw == EXPECTED_EMPTY_TARGET_NAME_RAW
    assert result.stats.nonempty_target_name_raw == 0
    assert result.stats.nonempty_pmid == EXPECTED_NONEMPTY_PMID
    assert result.stats.unique_sequence_names == EXPECTED_UNIQUE_SEQUENCE_NAMES
    assert (
        result.stats.duplicate_sequence_name_keys
        == EXPECTED_DUPLICATE_SEQUENCE_NAME_KEYS
    )
    assert (
        result.stats.rows_in_duplicate_sequence_name_groups
        == EXPECTED_ROWS_IN_DUPLICATE_SEQUENCE_NAME_GROUPS
    )
    assert result.stats.first_native_id == EXPECTED_FIRST_NATIVE_ID
    assert result.stats.last_native_id == EXPECTED_LAST_NATIVE_ID
    assert result.canonical_rows[0]["record_id"] == "riboaptamer:001"
    assert result.canonical_rows[-1]["record_id"] == "riboaptamer:509"
    assert all(row["target_name_raw"] == "" for row in result.canonical_rows)
    assert all(row["molecule_type"] == "" for row in result.canonical_rows)
    assert all(row["target_type"] == "" for row in result.canonical_rows)
    assert result.stats.sequence_exact_copy_ok is True
