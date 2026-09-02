"""Tests for the AptaIndex S1 adapter (synthetic fixtures only).

Real AptaIndex sequences are never embedded in fixtures. The optional
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
from adapters.aptaindex import (  # noqa: E402
    APTAINDEX_INPUT_COLUMNS,
    EXPECTED_DUPLICATE_TITLE_KEYS,
    EXPECTED_FIRST_NATIVE_ID,
    EXPECTED_INPUT_ROWS,
    EXPECTED_LAST_NATIVE_ID,
    EXPECTED_MISSING_SEQUENCES,
    EXPECTED_MISSING_TARGETS,
    EXPECTED_NONEMPTY_PUBLICATION,
    EXPECTED_NONEMPTY_SEQUENCES,
    EXPECTED_NONEMPTY_TARGETS,
    EXPECTED_ROWS_IN_DUPLICATE_TITLE_GROUPS,
    EXPECTED_UNIQUE_TITLES,
    SIDECAR_COLUMNS,
    AptaIndexAdapterError,
    extract_aptaindex,
    format_native_id,
    map_aptaindex_row,
    read_aptaindex_rows,
    validate_aptaindex_header,
    write_sidecar_csv_atomic,
    write_canonical_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CORPUS_COLUMNS,
    S1_FORBIDDEN_FIELDS,
)
from s0_build_registry import REQUIRED_COLUMNS  # noqa: E402
from s1_extract import (  # noqa: E402
    S1ExtractError,
    run_s1_extraction,
)

SYNTHETIC_CHEMICAL = "5'-dApdTpdG-3'"
SYNTHETIC_WHITESPACE = "  5'-dAp dTpdG-3'  "


def _blank_source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in APTAINDEX_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_aptaindex_csv(
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
            fieldnames=list(APTAINDEX_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {col: row.get(col, "") for col in APTAINDEX_INPUT_COLUMNS}
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
    """Synthetic rows covering duplicate Titles, blanks, and chemical notation."""
    return [
        _blank_source_row(
            Title="shared_title",
            Type="RNA",
            Target="synthetic protein A",
            **{
                "Affinity Type": "Kd",
                "Affinity": "1.2",
                "Affinity Units": "nM",
            },
            Sequence=SYNTHETIC_CHEMICAL,
            Comments="first shared title",
            Reference="Synthetic citation A, 1990",
            **{"Target Type": "Protein"},
        ),
        _blank_source_row(
            Title="shared_title",
            Type="DNA",
            Target="",
            **{
                "Affinity Type": "IC50",
                "Affinity": "3",
                "Affinity Units": "uM",
            },
            Sequence=SYNTHETIC_WHITESPACE,
            Comments="second shared title; blank target",
            Reference="Synthetic citation B, 1991",
            **{"Target Type": "Small Molecule"},
        ),
        _blank_source_row(
            Title="unique_title",
            Type="Peptide",
            Target="synthetic ligand C",
            Sequence="",
            Comments="blank sequence; peptide type retained as metadata",
            Reference="",
            **{"Target Type": "Protein"},
        ),
        _blank_source_row(
            Title="chimeric_title",
            Type="Chimeric",
            Target="synthetic cell D",
            Sequence="5'-rApdGpdC-3'",
            Comments="L-RNA/Chimeric type must still emit an S1 record",
            Reference="Synthetic citation D, 1992",
            **{"Target Type": "Cell"},
        ),
    ]


def test_adapter_dispatch_recognises_aptaindex() -> None:
    assert "aptaindex" in ADAPTER_KEYS
    from s1_extract import _get_adapter

    assert _get_adapter("aptaindex") is extract_aptaindex


def test_exact_schema_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    _write_aptaindex_csv(path, _demo_rows())
    result = extract_aptaindex(
        path,
        source_dataset="demo_ds",
        redistribution_status="restricted",
        expected_rows=None,
    )
    assert result.stats.input_rows == 4
    assert result.stats.canonical_rows == 4
    validate_aptaindex_header(list(APTAINDEX_INPUT_COLUMNS))


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    cols = list(APTAINDEX_INPUT_COLUMNS)
    cols.remove("Comments")
    _write_csv(path, cols, [_blank_source_row()])
    with pytest.raises(AptaIndexAdapterError, match="missing"):
        extract_aptaindex(
            path,
            source_dataset="demo_ds",
            redistribution_status="restricted",
            expected_rows=None,
        )


def test_extra_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    cols = list(APTAINDEX_INPUT_COLUMNS) + ["extra_col"]
    _write_csv(
        path,
        cols,
        [{**_blank_source_row(), "extra_col": "x"}],
    )
    with pytest.raises(AptaIndexAdapterError, match="extra"):
        extract_aptaindex(
            path,
            source_dataset="demo_ds",
            redistribution_status="restricted",
            expected_rows=None,
        )


def test_reordered_columns_rejected(tmp_path: Path) -> None:
    path = tmp_path / "reordered.csv"
    cols = list(APTAINDEX_INPUT_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    _write_csv(path, cols, [_blank_source_row()])
    with pytest.raises(AptaIndexAdapterError, match="reordered"):
        extract_aptaindex(
            path,
            source_dataset="demo_ds",
            redistribution_status="restricted",
            expected_rows=None,
        )


def test_row_based_native_ids_are_zero_padded() -> None:
    assert format_native_id(1) == "0001"
    assert format_native_id(1050) == "1050"
    source = _blank_source_row(Sequence=SYNTHETIC_CHEMICAL)
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=7,
        source_dataset="aptaindex_export_2026-07-22",
        redistribution_status="restricted",
    )
    assert canonical["native_id"] == "0007"
    assert canonical["record_id"] == "aptaindex:0007"
    assert sidecar["record_id"] == "aptaindex:0007"
    assert sidecar["aptaindex_native_id"] == "0007"
    assert sidecar["aptaindex_csv_data_row"] == "7"


def test_duplicate_titles_do_not_collide(tmp_path: Path) -> None:
    path = tmp_path / "dups.csv"
    _write_aptaindex_csv(path, _demo_rows())
    result = extract_aptaindex(
        path,
        source_dataset="demo_ds",
        redistribution_status="restricted",
        expected_rows=None,
    )
    ids = [row["record_id"] for row in result.canonical_rows]
    native = [row["native_id"] for row in result.canonical_rows]
    titles = [row["aptaindex_title"] for row in result.sidecar_rows]
    assert ids == [
        "aptaindex:0001",
        "aptaindex:0002",
        "aptaindex:0003",
        "aptaindex:0004",
    ]
    assert native == ["0001", "0002", "0003", "0004"]
    assert titles[0] == titles[1] == "shared_title"
    assert len(set(ids)) == 4
    assert result.stats.duplicate_title_keys == 1
    assert result.stats.rows_in_duplicate_title_groups == 2
    assert result.stats.unique_titles == 3


def test_sequence_copied_without_chemical_interpretation() -> None:
    source = _blank_source_row(Sequence=SYNTHETIC_CHEMICAL, Type="DNA")
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert canonical["sequence_raw"] == SYNTHETIC_CHEMICAL
    assert sidecar["aptaindex_sequence"] == SYNTHETIC_CHEMICAL
    assert canonical["sequence_full"] == ""
    assert canonical["sequence_core"] == ""
    assert canonical["molecule_type"] == ""
    assert canonical["chemistry"] == ""
    assert canonical["alphabet_as_reported"] == ""
    assert canonical["t_to_u_applied"] == ""


def test_whitespace_and_punctuation_not_cleaned_at_s1() -> None:
    source = _blank_source_row(Sequence=SYNTHETIC_WHITESPACE)
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert canonical["sequence_raw"] == SYNTHETIC_WHITESPACE
    assert sidecar["aptaindex_sequence"] == SYNTHETIC_WHITESPACE
    assert canonical["sequence_raw"] != SYNTHETIC_WHITESPACE.strip()
    assert canonical["sequence_raw"] != SYNTHETIC_WHITESPACE.replace(" ", "")


def test_blank_sequence_still_emits_record() -> None:
    source = _blank_source_row(Title="blank_seq", Target="ligand", Sequence="")
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=9,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert canonical["record_id"] == "aptaindex:0009"
    assert canonical["sequence_raw"] == ""
    assert sidecar["aptaindex_sequence"] == ""


def test_blank_target_still_emits_record() -> None:
    source = _blank_source_row(
        Title="blank_tgt",
        Target="",
        Sequence=SYNTHETIC_CHEMICAL,
    )
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=10,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert canonical["record_id"] == "aptaindex:0010"
    assert canonical["target_name_raw"] == ""
    assert sidecar["aptaindex_target"] == ""


def test_raw_target_preserved_into_target_name_raw() -> None:
    source = _blank_source_row(
        Sequence=SYNTHETIC_CHEMICAL,
        Target="  VEGF-A (isoform)  ",
    )
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert canonical["target_name_raw"] == "  VEGF-A (isoform)  "
    assert sidecar["aptaindex_target"] == "  VEGF-A (isoform)  "
    assert canonical["target_name"] == ""


def test_source_type_target_type_affinity_remain_metadata() -> None:
    source = _blank_source_row(
        Title="meta_row",
        Type="L-RNA",
        Target="synthetic protein",
        **{
            "Affinity Type": "Kd",
            "Affinity": "12.5",
            "Affinity Units": "nM",
            "Target Type": "Protein",
        },
        Sequence=SYNTHETIC_CHEMICAL,
    )
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert sidecar["aptaindex_type"] == "L-RNA"
    assert sidecar["aptaindex_target_type"] == "Protein"
    assert sidecar["aptaindex_affinity_type"] == "Kd"
    assert sidecar["aptaindex_affinity"] == "12.5"
    assert sidecar["aptaindex_affinity_units"] == "nM"
    assert canonical["molecule_type"] == ""
    assert canonical["chemistry"] == ""
    assert canonical["target_type"] == ""
    assert canonical["target_type_source"] == ""
    assert canonical["binding_evidence_type"] == ""
    assert canonical["binding_evidence_score"] == ""
    assert canonical["affinity_value"] == ""
    assert canonical["affinity_unit"] == ""
    assert canonical["affinity_type"] == ""


def test_canonical_s4_fields_remain_empty() -> None:
    source = _blank_source_row(
        Sequence=SYNTHETIC_CHEMICAL,
        Type="RNA",
        Target="ligand",
        **{
            "Affinity Type": "Kd",
            "Affinity": "1",
            "Affinity Units": "nM",
            "Target Type": "Protein",
        },
    )
    canonical, _ = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    for field in S1_FORBIDDEN_FIELDS:
        assert canonical[field] == "", field
    assert canonical["target_name"] == ""
    assert canonical["target_uniprot"] == ""
    assert canonical["target_family"] == ""
    assert canonical["target_pfam"] == ""
    assert canonical["pdb_id"] == ""


def test_restricted_redistribution_status_is_propagated() -> None:
    source = _blank_source_row(Sequence=SYNTHETIC_CHEMICAL)
    canonical, _ = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="aptaindex_export_2026-07-22",
        redistribution_status="restricted",
    )
    assert canonical["redistribution_status"] == "restricted"
    assert canonical["independently_attested_by_permissive_source"] == "false"
    assert canonical["source_db"] == "aptaindex"
    assert canonical["contributing_sources"] == "aptaindex"


def test_publication_copied_from_reference_without_doi_pmid_parser() -> None:
    source = _blank_source_row(
        Sequence=SYNTHETIC_CHEMICAL,
        Reference="Synthetic Author (1990) J. Example 12:34. PubMed 12345678",
    )
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert canonical["publication"] == source["Reference"]
    assert canonical["doi"] == ""
    assert canonical["pubmed_id"] == ""
    assert sidecar["aptaindex_reference"] == source["Reference"]


def test_all_source_fields_preserved_in_sidecar() -> None:
    source = _demo_rows()[0]
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    assert list(sidecar.keys()) == list(SIDECAR_COLUMNS)
    assert sidecar["record_id"] == canonical["record_id"]
    for column, sidecar_col in (
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
    ):
        assert sidecar[sidecar_col] == source[column]


def test_order_preserved_and_n_in_equals_n_out(tmp_path: Path) -> None:
    path = tmp_path / "order.csv"
    rows = _demo_rows()
    _write_aptaindex_csv(path, rows)
    result = extract_aptaindex(
        path,
        source_dataset="demo_ds",
        redistribution_status="restricted",
        expected_rows=None,
    )
    assert result.stats.input_rows == result.stats.canonical_rows == 4
    assert result.stats.sidecar_rows == 4
    assert [row["sequence_raw"] for row in result.canonical_rows] == [
        r["Sequence"] for r in rows
    ]
    assert [row["target_name_raw"] for row in result.canonical_rows] == [
        r["Target"] for r in rows
    ]
    assert result.stats.order_preserved is True
    assert result.stats.missing_sequences == 1
    assert result.stats.missing_targets == 1


def test_bom_quoted_fields_and_embedded_cr_yield_logical_rows(tmp_path: Path) -> None:
    path = tmp_path / "bom_cr.csv"
    comments_with_cr = "line1\rstill same logical row"
    rows = [
        _blank_source_row(
            Title="row_a",
            Type="RNA",
            Target="tA",
            Sequence=SYNTHETIC_CHEMICAL,
            Comments=comments_with_cr,
            Reference="cite A",
        ),
        _blank_source_row(
            Title="row_b",
            Type="DNA",
            Target="tB",
            Sequence="5'-dGpdC-3'",
            Comments="plain",
            Reference="cite B",
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(APTAINDEX_INPUT_COLUMNS),
            lineterminator="\n",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {col: row.get(col, "") for col in APTAINDEX_INPUT_COLUMNS}
            )
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" in raw

    # splitlines() must not be used as a record counter: the embedded CR
    # inflates the physical line count above the logical CSV row count.
    text = raw.decode("utf-8-sig")
    physical_split = len(text.splitlines())
    result = extract_aptaindex(
        path,
        source_dataset="demo_ds",
        redistribution_status="restricted",
        expected_rows=None,
    )
    assert result.stats.input_rows == 2
    assert result.stats.canonical_rows == 2
    assert result.sidecar_rows[0]["aptaindex_comments"] == comments_with_cr
    assert "\r" in result.sidecar_rows[0]["aptaindex_comments"]
    assert physical_split > result.stats.input_rows + 1


def test_production_row_count_gate_rejects_non_1050(tmp_path: Path) -> None:
    path = tmp_path / "small.csv"
    _write_aptaindex_csv(path, _demo_rows())
    with pytest.raises(AptaIndexAdapterError, match="1050"):
        read_aptaindex_rows(path)


def test_written_csv_preserves_embedded_cr_as_one_logical_row(
    tmp_path: Path,
) -> None:
    comments_with_cr = "line1\rstill same logical row"
    source = _blank_source_row(
        Title="row_a",
        Sequence=SYNTHETIC_CHEMICAL,
        Comments=comments_with_cr,
        Reference="cite A\rwith CR",
        Target="tA",
    )
    canonical, sidecar = map_aptaindex_row(
        source,
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
    )
    canonical_path = tmp_path / "extracted.csv"
    sidecar_path = tmp_path / "sidecar.csv"
    write_canonical_csv_atomic(canonical_path, [canonical])
    write_sidecar_csv_atomic(sidecar_path, [sidecar])
    with canonical_path.open("r", encoding="utf-8", newline="") as handle:
        loaded = list(csv.DictReader(handle))
    with sidecar_path.open("r", encoding="utf-8", newline="") as handle:
        loaded_side = list(csv.DictReader(handle))
    assert len(loaded) == 1
    assert len(loaded_side) == 1
    assert loaded[0]["sequence_raw"] == SYNTHETIC_CHEMICAL
    assert loaded_side[0]["aptaindex_comments"] == comments_with_cr
    assert loaded[0]["publication"] == "cite A\rwith CR"
    assert "\r" in loaded_side[0]["aptaindex_comments"]


def test_sidecar_write_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.csv"
    _, sidecar = map_aptaindex_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset="demo_ds",
        redistribution_status="restricted",
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
    _write_aptaindex_csv(path, _demo_rows())
    kwargs = dict(
        source_dataset="demo_ds",
        redistribution_status="restricted",
        expected_rows=None,
    )
    first = extract_aptaindex(path, **kwargs)
    second = extract_aptaindex(path, **kwargs)
    assert first.canonical_rows == second.canonical_rows
    assert first.sidecar_rows == second.sidecar_rows


def test_stage_schema_compliance() -> None:
    canonical, _ = map_aptaindex_row(
        _demo_rows()[0],
        csv_data_row=1,
        source_dataset="aptaindex_export_2026-07-22",
        redistribution_status="restricted",
    )
    assert list(canonical.keys()) == list(CORPUS_COLUMNS)
    assert canonical["source_db"] == "aptaindex"
    assert canonical["source_dataset"] == "aptaindex_export_2026-07-22"
    assert canonical["contributing_sources"] == "aptaindex"
    assert canonical["contributing_datasets"] == "aptaindex_export_2026-07-22"
    assert canonical["corroboration_count"] == "1"
    assert canonical["redistribution_status"] == "restricted"
    assert canonical["independently_attested_by_permissive_source"] == "false"


def _make_s1_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "AptaIndex").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def test_dispatcher_round_trip(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = repo / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
    rows = _demo_rows()
    _write_aptaindex_csv(input_path, rows)
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "aptaindex",
                "source_dataset": "aptaindex_export_2026-07-22",
                "path": "data/raw/AptaIndex/aptamers-export-2026-07-22.csv",
                "sha256": digest,
                "n_rows_expected": str(len(rows)),
                "snapshot_date": "2026-07-22",
                "tier": "1",
                "redistribution_status": "restricted",
                "notes": "synthetic",
            }
        ],
    )
    result = run_s1_extraction(
        repo_root=repo,
        source_key="aptaindex",
        registry_spec=spec,
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert result.stats.input_rows == 4
    assert result.deterministic_rerun_ok is True
    assert result.input_hash_unchanged is True
    canonical = repo / "data" / "interim" / "extracted" / "aptaindex_extracted.csv"
    sidecar = repo / "data" / "interim" / "extracted" / "aptaindex_source_metadata.csv"
    report = repo / "data" / "interim" / "extracted" / "aptaindex_s1_report.md"
    with canonical.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(CORPUS_COLUMNS)
        out_rows = list(reader)
    assert [row["native_id"] for row in out_rows] == [
        "0001",
        "0002",
        "0003",
        "0004",
    ]
    assert out_rows[0]["sequence_raw"] == SYNTHETIC_CHEMICAL
    assert out_rows[1]["target_name_raw"] == ""
    assert out_rows[2]["sequence_raw"] == ""
    assert all(row["redistribution_status"] == "restricted" for row in out_rows)
    assert all(row["target_type"] == "" for row in out_rows)
    assert all(row["molecule_type"] == "" for row in out_rows)
    with sidecar.open(encoding="utf-8", newline="") as handle:
        side_reader = csv.DictReader(handle)
        assert list(side_reader.fieldnames or []) == list(SIDECAR_COLUMNS)
        side_rows = list(side_reader)
    assert len(side_rows) == 4
    report_text = report.read_text(encoding="utf-8")
    assert str(repo.resolve()) not in report_text
    assert "S2 has not started" in report_text
    assert SYNTHETIC_CHEMICAL not in report_text
    assert SYNTHETIC_WHITESPACE not in report_text


def test_dispatcher_rejects_unknown_source_key(tmp_path: Path) -> None:
    repo = _make_s1_repo(tmp_path)
    input_path = repo / "data" / "raw" / "AptaIndex" / "aptamers-export-2026-07-22.csv"
    _write_aptaindex_csv(input_path, _demo_rows())
    digest = _hash_path(input_path)
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "not_aptaindex",
                "source_dataset": "demo",
                "path": "data/raw/AptaIndex/aptamers-export-2026-07-22.csv",
                "sha256": digest,
                "n_rows_expected": "4",
                "snapshot_date": "2026-07-22",
                "tier": "1",
                "redistribution_status": "restricted",
                "notes": "must fail",
            }
        ],
    )
    with pytest.raises(S1ExtractError, match="Unknown S1 adapter"):
        run_s1_extraction(
            repo_root=repo,
            source_key="not_aptaindex",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )


@pytest.mark.skipif(
    not (
        REPO_ROOT / "data/raw/AptaIndex/aptamers-export-2026-07-22.csv"
    ).is_file(),
    reason="Registered AptaIndex CSV not present locally",
)
def test_real_export_1050_in_equals_1050_out_without_embedding_sequences() -> None:
    path = REPO_ROOT / "data/raw/AptaIndex/aptamers-export-2026-07-22.csv"
    result = extract_aptaindex(
        path,
        source_dataset="aptaindex_export_2026-07-22",
        redistribution_status="restricted",
        expected_rows=EXPECTED_INPUT_ROWS,
    )
    assert result.stats.input_rows == EXPECTED_INPUT_ROWS
    assert result.stats.canonical_rows == EXPECTED_INPUT_ROWS
    assert result.stats.sidecar_rows == EXPECTED_INPUT_ROWS
    assert result.stats.unique_native_ids == EXPECTED_INPUT_ROWS
    assert result.stats.unique_record_ids == EXPECTED_INPUT_ROWS
    assert result.stats.nonempty_sequences == EXPECTED_NONEMPTY_SEQUENCES
    assert result.stats.missing_sequences == EXPECTED_MISSING_SEQUENCES
    assert result.stats.nonempty_targets == EXPECTED_NONEMPTY_TARGETS
    assert result.stats.missing_targets == EXPECTED_MISSING_TARGETS
    assert result.stats.nonempty_publication == EXPECTED_NONEMPTY_PUBLICATION
    assert result.stats.nonempty_doi == 0
    assert result.stats.nonempty_pmid == 0
    assert result.stats.unique_titles == EXPECTED_UNIQUE_TITLES
    assert result.stats.duplicate_title_keys == EXPECTED_DUPLICATE_TITLE_KEYS
    assert (
        result.stats.rows_in_duplicate_title_groups
        == EXPECTED_ROWS_IN_DUPLICATE_TITLE_GROUPS
    )
    assert result.stats.first_native_id == EXPECTED_FIRST_NATIVE_ID
    assert result.stats.last_native_id == EXPECTED_LAST_NATIVE_ID
    assert result.canonical_rows[0]["record_id"] == "aptaindex:0001"
    assert result.canonical_rows[-1]["record_id"] == "aptaindex:1050"
    assert all(row["source_db"] == "aptaindex" for row in result.canonical_rows)
    assert all(
        row["redistribution_status"] == "restricted"
        for row in result.canonical_rows
    )
    assert all(row["molecule_type"] == "" for row in result.canonical_rows)
    assert all(row["target_type"] == "" for row in result.canonical_rows)
    assert all(row["doi"] == "" for row in result.canonical_rows)
    assert all(row["pubmed_id"] == "" for row in result.canonical_rows)
    assert result.stats.sequence_exact_copy_ok is True
    assert result.stats.target_exact_copy_ok is True
