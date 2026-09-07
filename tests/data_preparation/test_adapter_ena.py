"""Tests for the ENA S1 adapter (synthetic fixtures only).

Real ENA aptamer sequences are never embedded in fixtures. The optional
local-only production skipif gate asserts counts without writing sequences
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
from adapters.ena import (  # noqa: E402
    ENA_INPUT_COLUMNS,
    EXPECTED_BLANK_SOURCE_FAMILY_IDS,
    EXPECTED_CONSOLIDATED_ROWS,
    EXPECTED_DISTINCT_PRIMARY_EXPERIMENT_GROUPS,
    EXPECTED_INPUT_ROWS,
    EXPECTED_MATERIALISED_SINGLETONS,
    EXPECTED_NONBLANK_SOURCE_FAMILY_IDS,
    EXPECTED_NONEMPTY_SEQUENCES,
    EXPECTED_NONEMPTY_TARGETS,
    EXPECTED_PIPE_FAMILY_ROWS,
    EXPECTED_POPULATED_PRIMARY_EXPERIMENT_GROUPS,
    EXPECTED_SEQUENCE_CORRECTIONS_APPLIED,
    EXPECTED_TARGET_CORRECTIONS_APPLIED,
    SIDECAR_COLUMNS,
    SINGLETON_FAMILY_PREFIX,
    SOURCE_DB,
    EnaAdapterError,
    extract_ena,
    map_ena_row,
    materialise_effective_family,
    read_ena_rows,
    validate_ena_header,
    write_sidecar_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
)
from s0_build_registry import REQUIRED_COLUMNS, load_registry_spec  # noqa: E402
from s1_extract import (  # noqa: E402
    S1ExtractError,
    run_s1_extraction,
)

PRODUCTION_PATH = (
    REPO_ROOT / "data/raw/ENA/review_v2/ena_selected_after_manual_review.csv"
)
EXPECTED_PRODUCTION_SHA256 = (
    "d1069b96c2bcf5eba02d7d7907b3bcc33e041bf80aac6345e7295715e45c5a35"
)
EXPECTED_SOURCE_DATASET = "ena_selected_v2_2026-08"

SYNTHETIC_RNA = "ACGUACGU"
SYNTHETIC_T = "ACGTACGT"
SYNTHETIC_WHITESPACE = "  ACGU  "
SYNTHETIC_ORIGINAL = "ACGT|ACGU"


def _blank_source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in ENA_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_ena_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    with_bom: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if with_bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(ENA_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in ENA_INPUT_COLUMNS})


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
    """Synthetic rows covering identity, family, grouping, and corrections."""
    return [
        _blank_source_row(
            sequence=SYNTHETIC_RNA,
            target="synthetic protein A",
            target_type="protein",
            review_unit_id="ru_blank_fam",
            review_unit_ids="ru_blank_fam",
            experiment_group_id="eg_primary",
            experiment_group_ids="eg_primary",
            near_duplicate_family_id="",
            near_duplicate_family_size="",
            sequence_original=SYNTHETIC_RNA,
            target_original="synthetic protein A",
            sequence_corrected_applied="0",
            target_corrected_applied="0",
            representative_title="Synthetic title A",
            binding_evidence_type="SELEX",
            binding_evidence_strength="weak",
            evidence_scope="selection",
            references="Synthetic ref A",
            doi_values="10.0/demo-a",
            pubmed_values="111",
            genuine_target_conflict="0",
            unresolved_target="0",
            consolidated_from_n_units="1",
        ),
        _blank_source_row(
            sequence=SYNTHETIC_T,
            target="synthetic ligand B",
            target_type="small_molecule",
            review_unit_id="ru_named_fam",
            review_unit_ids="ru_named_fam",
            experiment_group_id="eg_primary",
            experiment_group_ids="eg_primary|eg_support",
            near_duplicate_family_id="ndfam_9",
            near_duplicate_family_size="4",
            sequence_original=SYNTHETIC_T,
            target_original="synthetic ligand B",
            sequence_corrected_applied="0",
            target_corrected_applied="0",
            genuine_target_conflict="0",
            unresolved_target="0",
            consolidated_from_n_units="1",
        ),
        _blank_source_row(
            sequence=SYNTHETIC_WHITESPACE,
            target=" synthetic target C ",
            review_unit_id="ru_corrected",
            review_unit_ids="ru_corrected",
            experiment_group_id="eg_other",
            experiment_group_ids="eg_other",
            near_duplicate_family_id="",
            near_duplicate_family_size="",
            sequence_original=SYNTHETIC_ORIGINAL,
            target_original="old target C",
            manual_sequence_corrected=SYNTHETIC_WHITESPACE,
            manual_target_corrected=" synthetic target C ",
            sequence_corrected_applied="1",
            target_corrected_applied="1",
            genuine_target_conflict="0",
            unresolved_target="0",
            consolidated_from_n_units="1",
        ),
        _blank_source_row(
            sequence=SYNTHETIC_RNA,
            target="synthetic protein D",
            review_unit_id="ru_keep",
            review_unit_ids="ru_a|ru_b",
            experiment_group_id="eg_cons",
            experiment_group_ids="eg_cons|eg_extra",
            accession_count="2",
            accessions="ACC1|ACC2",
            near_duplicate_family_id="ndfam_1|ndfam_2",
            near_duplicate_family_size="2",
            sequence_original=SYNTHETIC_ORIGINAL,
            target_original="synthetic protein D",
            sequence_corrected_applied="0",
            target_corrected_applied="0",
            genuine_target_conflict="0",
            unresolved_target="0",
            consolidated_from_n_units="2",
        ),
    ]


def test_adapter_dispatch_recognises_ena() -> None:
    assert "ena" in ADAPTER_KEYS
    from s1_extract import _get_adapter

    assert _get_adapter("ena") is extract_ena


def test_tracked_registry_spec_registers_authoritative_ena_file() -> None:
    rows = load_registry_spec(REPO_ROOT / "config" / "source_registry.csv")
    ena = [row for row in rows if row.source_key == "ena"]
    assert len(ena) == 1
    assert ena[0].source_dataset == EXPECTED_SOURCE_DATASET
    assert ena[0].path == (
        "data/raw/ENA/review_v2/ena_selected_after_manual_review.csv"
    )
    assert ena[0].sha256 == EXPECTED_PRODUCTION_SHA256
    assert ena[0].n_rows_expected == EXPECTED_INPUT_ROWS
    assert ena[0].snapshot_date == "2026-08-04"
    assert ena[0].tier == "1"
    assert ena[0].redistribution_status == "unknown"
    forbidden_paths = {
        row.path
        for row in rows
        if "ENA" in row.path
        and row.path
        != "data/raw/ENA/review_v2/ena_selected_after_manual_review.csv"
    }
    assert forbidden_paths == set()


def test_exact_schema_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    _write_ena_csv(path, _demo_rows())
    result = extract_ena(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 4
    assert result.stats.canonical_rows == 4
    assert result.stats.sidecar_rows == 4
    validate_ena_header(list(ENA_INPUT_COLUMNS))


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    cols = list(ENA_INPUT_COLUMNS)
    cols.remove("manual_notes")
    _write_csv(path, cols, [_blank_source_row(review_unit_id="ru1")])
    with pytest.raises(EnaAdapterError, match="missing"):
        extract_ena(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_extra_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    cols = list(ENA_INPUT_COLUMNS) + ["extra_col"]
    _write_csv(
        path,
        cols,
        [{**_blank_source_row(review_unit_id="ru1"), "extra_col": "x"}],
    )
    with pytest.raises(EnaAdapterError, match="extra"):
        extract_ena(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_reordered_columns_rejected(tmp_path: Path) -> None:
    path = tmp_path / "reordered.csv"
    cols = list(ENA_INPUT_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    _write_csv(path, cols, [_blank_source_row(review_unit_id="ru1")])
    with pytest.raises(EnaAdapterError, match="reordered"):
        extract_ena(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_one_row_in_one_row_out() -> None:
    source = _demo_rows()[0]
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["native_id"] == "ru_blank_fam"
    assert canonical["record_id"] == "ena:ru_blank_fam"
    assert sidecar["record_id"] == "ena:ru_blank_fam"
    assert sidecar["review_unit_id"] == "ru_blank_fam"


def test_identity_uses_review_unit_id_not_accession_or_row_number() -> None:
    source = _blank_source_row(
        sequence=SYNTHETIC_RNA,
        target="t",
        review_unit_id="ru_identity",
        review_unit_ids="ru_other|ru_identity",
        accessions="ACC999",
        experiment_group_id="eg1",
        consolidated_from_n_units="1",
        genuine_target_conflict="0",
        unresolved_target="0",
        sequence_corrected_applied="0",
        target_corrected_applied="0",
    )
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["native_id"] == "ru_identity"
    assert canonical["record_id"] == "ena:ru_identity"
    assert canonical["accession"] == ""
    assert sidecar["review_unit_ids"] == "ru_other|ru_identity"
    assert sidecar["accessions"] == "ACC999"


def test_sequence_copied_verbatim_including_t_and_whitespace() -> None:
    for raw in (SYNTHETIC_RNA, SYNTHETIC_T, SYNTHETIC_WHITESPACE):
        source = _blank_source_row(
            sequence=raw,
            sequence_original=SYNTHETIC_ORIGINAL,
            target="t",
            review_unit_id="ru_seq",
            experiment_group_id="eg1",
            genuine_target_conflict="0",
            unresolved_target="0",
            sequence_corrected_applied="0",
            target_corrected_applied="0",
            consolidated_from_n_units="1",
        )
        canonical, sidecar = map_ena_row(
            source,
            source_dataset="demo_ds",
            redistribution_status="unknown",
        )
        assert canonical["sequence_raw"] == raw
        assert sidecar["sequence"] == raw
        assert sidecar["sequence_original"] == SYNTHETIC_ORIGINAL
        assert canonical["sequence_raw"] != sidecar["sequence_original"]
        assert canonical["sequence_full"] == ""
        assert canonical["t_to_u_applied"] == ""
        assert canonical["molecule_type"] == ""
        assert canonical["alphabet_as_reported"] == ""


def test_target_copied_verbatim_and_not_canonicalised() -> None:
    raw_target = " synthetic Target Name "
    source = _blank_source_row(
        sequence=SYNTHETIC_RNA,
        target=raw_target,
        target_original="old name",
        target_type="protein",
        review_unit_id="ru_tgt",
        experiment_group_id="eg1",
        genuine_target_conflict="0",
        unresolved_target="0",
        sequence_corrected_applied="0",
        target_corrected_applied="0",
        consolidated_from_n_units="1",
    )
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["target_name_raw"] == raw_target
    assert sidecar["target"] == raw_target
    assert sidecar["target_original"] == "old name"
    assert sidecar["target_type"] == "protein"
    assert canonical["target_name"] == ""
    assert canonical["target_type"] == ""
    assert canonical["target_uniprot"] == ""
    assert canonical["target_family"] == ""
    assert canonical["target_pfam"] == ""


def test_correction_fields_are_sidecar_provenance_only() -> None:
    source = _demo_rows()[2]
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["manual_sequence_corrected"] == SYNTHETIC_WHITESPACE
    assert sidecar["sequence_corrected_applied"] == "1"
    assert sidecar["manual_target_corrected"] == " synthetic target C "
    assert sidecar["target_corrected_applied"] == "1"
    assert sidecar["sequence_original"] == SYNTHETIC_ORIGINAL
    assert canonical["sequence_raw"] == SYNTHETIC_WHITESPACE
    assert canonical["notes"] == ""


def test_primary_and_supporting_experiment_groups_remain_distinct() -> None:
    source = _demo_rows()[1]
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["experiment_group_id"] == "eg_primary"
    assert sidecar["experiment_group_ids"] == "eg_primary|eg_support"
    assert sidecar["experiment_group_id"] != sidecar["experiment_group_ids"]
    assert canonical["experiment_group_id"] == ""


def test_blank_family_gets_deterministic_singleton_sidecar_id() -> None:
    effective_id, effective_size, was_blank = materialise_effective_family(
        "ru_blank_fam", "", ""
    )
    assert effective_id == f"{SINGLETON_FAMILY_PREFIX}ru_blank_fam"
    assert effective_size == "1"
    assert was_blank == "true"
    source = _demo_rows()[0]
    _, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["near_duplicate_family_id"] == ""
    assert sidecar["near_duplicate_family_size"] == ""
    assert sidecar["ena_effective_near_duplicate_family_id"] == (
        f"{SINGLETON_FAMILY_PREFIX}ru_blank_fam"
    )
    assert sidecar["ena_effective_near_duplicate_family_size"] == "1"
    assert sidecar["ena_source_family_id_was_blank"] == "true"


def test_nonblank_family_preserved_exactly() -> None:
    source = _demo_rows()[1]
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["near_duplicate_family_id"] == "ndfam_9"
    assert sidecar["near_duplicate_family_size"] == "4"
    assert sidecar["ena_effective_near_duplicate_family_id"] == "ndfam_9"
    assert sidecar["ena_effective_near_duplicate_family_size"] == "4"
    assert sidecar["ena_source_family_id_was_blank"] == "false"
    assert canonical["near_duplicate_family_id"] == ""


def test_pipe_delimited_family_is_not_split_or_rewritten() -> None:
    source = _demo_rows()[3]
    canonical, sidecar = map_ena_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["near_duplicate_family_id"] == "ndfam_1|ndfam_2"
    assert sidecar["ena_effective_near_duplicate_family_id"] == "ndfam_1|ndfam_2"
    assert sidecar["review_unit_ids"] == "ru_a|ru_b"
    assert sidecar["consolidated_from_n_units"] == "2"
    assert canonical["native_id"] == "ru_keep"


def test_consolidated_provenance_is_not_split(tmp_path: Path) -> None:
    path = tmp_path / "cons.csv"
    _write_ena_csv(path, [_demo_rows()[3]])
    result = extract_ena(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 1
    assert result.stats.canonical_rows == 1
    assert result.stats.consolidated_rows == 1
    assert result.sidecar_rows[0]["review_unit_ids"] == "ru_a|ru_b"
    assert result.sidecar_rows[0]["accessions"] == "ACC1|ACC2"


def test_duplicate_review_unit_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dups.csv"
    row = _blank_source_row(
        sequence=SYNTHETIC_RNA,
        target="t",
        review_unit_id="ru_dup",
        experiment_group_id="eg1",
        genuine_target_conflict="0",
        unresolved_target="0",
        sequence_corrected_applied="0",
        target_corrected_applied="0",
        consolidated_from_n_units="1",
    )
    _write_ena_csv(path, [row, dict(row)])
    with pytest.raises(EnaAdapterError, match="Duplicate ENA review_unit_id"):
        extract_ena(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_blank_review_unit_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "blank.csv"
    _write_ena_csv(path, [_blank_source_row(sequence=SYNTHETIC_RNA, target="t")])
    with pytest.raises(EnaAdapterError, match="blank review_unit_id"):
        extract_ena(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_later_stage_fields_remain_empty() -> None:
    canonical, sidecar = map_ena_row(
        _demo_rows()[0],
        source_dataset=EXPECTED_SOURCE_DATASET,
        redistribution_status="unknown",
    )
    for field in S1_FORBIDDEN_FIELDS:
        assert canonical[field] == ""
    assert canonical["publication"] == ""
    assert canonical["doi"] == ""
    assert canonical["pubmed_id"] == ""
    assert canonical["binding_evidence_type"] == ""
    assert canonical["binding_evidence_score"] == ""
    assert sidecar["representative_title"] == "Synthetic title A"
    assert sidecar["binding_evidence_type"] == "SELEX"
    assert sidecar["doi_values"] == "10.0/demo-a"
    assert sidecar["pubmed_values"] == "111"


def test_source_evidence_is_not_mapped_to_canonical_publication() -> None:
    canonical, sidecar = map_ena_row(
        _demo_rows()[0],
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert sidecar["representative_title"] != ""
    assert sidecar["references"] != ""
    assert canonical["publication"] == ""
    assert canonical["doi"] == ""
    assert canonical["pubmed_id"] == ""


def test_singleton_ids_do_not_collide_with_source_ndfam_values(tmp_path: Path) -> None:
    path = tmp_path / "families.csv"
    _write_ena_csv(path, _demo_rows())
    result = extract_ena(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    source_families = {
        row["near_duplicate_family_id"]
        for row in result.sidecar_rows
        if row["near_duplicate_family_id"]
    }
    singletons = {
        row["ena_effective_near_duplicate_family_id"]
        for row in result.sidecar_rows
        if row["ena_source_family_id_was_blank"] == "true"
    }
    assert result.stats.blank_source_family_ids == 2
    assert result.stats.materialised_singleton_family_ids == 2
    assert result.stats.unique_materialised_singleton_ids == 2
    assert result.stats.nonblank_source_family_ids == 2
    assert singletons.isdisjoint(source_families)
    assert all(item.startswith(SINGLETON_FAMILY_PREFIX) for item in singletons)


def test_production_row_count_gate_rejects_non_679(tmp_path: Path) -> None:
    path = tmp_path / "small.csv"
    _write_ena_csv(path, _demo_rows())
    with pytest.raises(EnaAdapterError, match="679"):
        read_ena_rows(path)


def test_stage_schema_compliance() -> None:
    canonical, _ = map_ena_row(
        _demo_rows()[0],
        source_dataset=EXPECTED_SOURCE_DATASET,
        redistribution_status="unknown",
    )
    assert list(canonical.keys()) == list(CORPUS_COLUMNS)
    assert canonical["source_db"] == SOURCE_DB
    assert canonical["source_dataset"] == EXPECTED_SOURCE_DATASET
    assert canonical["contributing_sources"] == SOURCE_DB
    assert canonical["contributing_datasets"] == EXPECTED_SOURCE_DATASET
    assert canonical["corroboration_count"] == "1"
    assert canonical["redistribution_status"] == "unknown"
    assert canonical["independently_attested_by_permissive_source"] == "false"


def test_sidecar_write_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.csv"
    _, sidecar = map_ena_row(
        _demo_rows()[0],
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
    _write_ena_csv(path, _demo_rows())
    kwargs = dict(
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    first = extract_ena(path, **kwargs)
    second = extract_ena(path, **kwargs)
    assert first.canonical_rows == second.canonical_rows
    assert first.sidecar_rows == second.sidecar_rows


def _make_s1_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "ENA" / "review_v2").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def test_dispatcher_round_trip(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = (
        repo / "data" / "raw" / "ENA" / "review_v2" / "ena_selected_after_manual_review.csv"
    )
    rows = _demo_rows()
    _write_ena_csv(input_path, rows)
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "ena",
                "source_dataset": EXPECTED_SOURCE_DATASET,
                "path": "data/raw/ENA/review_v2/ena_selected_after_manual_review.csv",
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
        source_key="ena",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert result.stats.input_rows == 4
    assert result.deterministic_rerun_ok is True
    assert result.input_hash_unchanged is True
    canonical = repo / "data" / "interim" / "extracted" / "ena_extracted.csv"
    sidecar = repo / "data" / "interim" / "extracted" / "ena_source_metadata.csv"
    report = repo / "data" / "interim" / "extracted" / "ena_s1_report.md"
    with canonical.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(CORPUS_COLUMNS)
        out_rows = list(reader)
    assert [row["native_id"] for row in out_rows] == [
        "ru_blank_fam",
        "ru_named_fam",
        "ru_corrected",
        "ru_keep",
    ]
    assert out_rows[0]["sequence_raw"] == SYNTHETIC_RNA
    assert out_rows[1]["sequence_raw"] == SYNTHETIC_T
    assert out_rows[2]["sequence_raw"] == SYNTHETIC_WHITESPACE
    assert out_rows[2]["target_name_raw"] == " synthetic target C "
    assert all(row["source_db"] == "ena" for row in out_rows)
    assert all(row["molecule_type"] == "" for row in out_rows)
    assert all(row["target_type"] == "" for row in out_rows)
    assert all(row["publication"] == "" for row in out_rows)
    assert all(row["experiment_group_id"] == "" for row in out_rows)
    assert all(row["near_duplicate_family_id"] == "" for row in out_rows)
    with sidecar.open(encoding="utf-8", newline="") as handle:
        side_reader = csv.DictReader(handle)
        assert list(side_reader.fieldnames or []) == list(SIDECAR_COLUMNS)
        side_rows = list(side_reader)
    assert len(side_rows) == 4
    assert side_rows[0]["ena_source_family_id_was_blank"] == "true"
    assert side_rows[1]["near_duplicate_family_id"] == "ndfam_9"
    assert side_rows[3]["review_unit_ids"] == "ru_a|ru_b"
    report_text = report.read_text(encoding="utf-8")
    assert str(repo.resolve()) not in report_text
    assert "S2 has not started" in report_text
    assert SYNTHETIC_RNA not in report_text
    assert SYNTHETIC_T not in report_text
    assert SYNTHETIC_WHITESPACE not in report_text
    assert SYNTHETIC_ORIGINAL not in report_text


def test_dispatcher_rejects_unknown_source_key(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = (
        repo / "data" / "raw" / "ENA" / "review_v2" / "ena_selected_after_manual_review.csv"
    )
    _write_ena_csv(input_path, _demo_rows())
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "not_ena",
                "source_dataset": "demo",
                "path": "data/raw/ENA/review_v2/ena_selected_after_manual_review.csv",
                "sha256": digest,
                "n_rows_expected": "4",
                "snapshot_date": "2026-08-04",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "must fail",
            }
        ],
    )
    with pytest.raises(S1ExtractError, match="Unknown S1 adapter"):
        run_s1_extraction(
            repo_root=repo,
            source_key="not_ena",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )


@pytest.mark.skipif(
    not PRODUCTION_PATH.is_file(),
    reason="Registered ENA selected CSV not present locally",
)
def test_real_selected_file_679_in_equals_679_out_without_embedding_sequences() -> None:
    before = _hash_path(PRODUCTION_PATH)
    assert before == EXPECTED_PRODUCTION_SHA256
    result = extract_ena(
        PRODUCTION_PATH,
        source_dataset=EXPECTED_SOURCE_DATASET,
        redistribution_status="unknown",
        expected_rows=EXPECTED_INPUT_ROWS,
    )
    after = _hash_path(PRODUCTION_PATH)
    assert after == before
    assert result.stats.input_rows == EXPECTED_INPUT_ROWS
    assert result.stats.canonical_rows == EXPECTED_INPUT_ROWS
    assert result.stats.sidecar_rows == EXPECTED_INPUT_ROWS
    assert result.stats.unique_native_ids == EXPECTED_INPUT_ROWS
    assert result.stats.unique_record_ids == EXPECTED_INPUT_ROWS
    assert result.stats.nonempty_sequences == EXPECTED_NONEMPTY_SEQUENCES
    assert result.stats.nonempty_targets == EXPECTED_NONEMPTY_TARGETS
    assert result.stats.populated_primary_experiment_groups == (
        EXPECTED_POPULATED_PRIMARY_EXPERIMENT_GROUPS
    )
    assert result.stats.distinct_primary_experiment_groups == (
        EXPECTED_DISTINCT_PRIMARY_EXPERIMENT_GROUPS
    )
    assert result.stats.blank_source_family_ids == EXPECTED_BLANK_SOURCE_FAMILY_IDS
    assert result.stats.materialised_singleton_family_ids == (
        EXPECTED_MATERIALISED_SINGLETONS
    )
    assert result.stats.unique_materialised_singleton_ids == (
        EXPECTED_MATERIALISED_SINGLETONS
    )
    assert result.stats.nonblank_source_family_ids == (
        EXPECTED_NONBLANK_SOURCE_FAMILY_IDS
    )
    assert result.stats.sequence_corrections_applied == (
        EXPECTED_SEQUENCE_CORRECTIONS_APPLIED
    )
    assert result.stats.target_corrections_applied == (
        EXPECTED_TARGET_CORRECTIONS_APPLIED
    )
    assert result.stats.consolidated_rows == EXPECTED_CONSOLIDATED_ROWS
    assert result.stats.pipe_family_rows == EXPECTED_PIPE_FAMILY_ROWS
    assert result.stats.nonempty_publication == 0
    assert result.stats.nonempty_doi == 0
    assert result.stats.nonempty_pmid == 0
    assert result.stats.sequence_exact_copy_ok is True
    assert result.stats.target_exact_copy_ok is True
    assert all(row["source_db"] == "ena" for row in result.canonical_rows)
    assert all(row["molecule_type"] == "" for row in result.canonical_rows)
    assert all(row["t_to_u_applied"] == "" for row in result.canonical_rows)
    assert all(row["target_name"] == "" for row in result.canonical_rows)
    assert all(row["target_type"] == "" for row in result.canonical_rows)
    assert all(row["publication"] == "" for row in result.canonical_rows)
    assert all(row["experiment_group_id"] == "" for row in result.canonical_rows)
    assert all(row["near_duplicate_family_id"] == "" for row in result.canonical_rows)
    native_ids = [row["native_id"] for row in result.canonical_rows]
    record_ids = [row["record_id"] for row in result.canonical_rows]
    source_ids = [row["review_unit_id"] for row in result.sidecar_rows]
    assert native_ids == source_ids
    assert record_ids == [f"ena:{native}" for native in native_ids]
    assert len(set(native_ids)) == EXPECTED_INPUT_ROWS
    blank_family_rows = [
        row
        for row in result.sidecar_rows
        if row["near_duplicate_family_id"] == ""
    ]
    assert len(blank_family_rows) == EXPECTED_BLANK_SOURCE_FAMILY_IDS
    singleton_ids = [
        row["ena_effective_near_duplicate_family_id"] for row in blank_family_rows
    ]
    assert len(set(singleton_ids)) == EXPECTED_MATERIALISED_SINGLETONS
    assert all(
        item == f"{SINGLETON_FAMILY_PREFIX}{row['review_unit_id']}"
        for item, row in zip(singleton_ids, blank_family_rows, strict=True)
    )
    assert all(
        row["ena_effective_near_duplicate_family_size"] == "1"
        for row in blank_family_rows
    )
    assert all(
        row["ena_source_family_id_was_blank"] == "true" for row in blank_family_rows
    )
    nonblank_family_rows = [
        row
        for row in result.sidecar_rows
        if row["near_duplicate_family_id"] != ""
    ]
    assert len(nonblank_family_rows) == EXPECTED_NONBLANK_SOURCE_FAMILY_IDS
    assert all(
        row["ena_effective_near_duplicate_family_id"]
        == row["near_duplicate_family_id"]
        for row in nonblank_family_rows
    )
    assert all(
        row["ena_source_family_id_was_blank"] == "false"
        for row in nonblank_family_rows
    )
    source_families = {
        row["near_duplicate_family_id"] for row in nonblank_family_rows
    }
    assert set(singleton_ids).isdisjoint(source_families)
    assert all(
        row["experiment_group_id"] != "" for row in result.sidecar_rows
    )
    primary_groups = {row["experiment_group_id"] for row in result.sidecar_rows}
    assert len(primary_groups) == EXPECTED_DISTINCT_PRIMARY_EXPERIMENT_GROUPS
    assert all("|" not in group for group in primary_groups)
