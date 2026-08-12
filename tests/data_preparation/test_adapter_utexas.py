"""Tests for the UTexas S1 adapter (synthetic fixtures only).

Real UTexas aptamer sequences are never embedded in fixtures.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.utexas import (  # noqa: E402
    EXPECTED_INPUT_ROWS,
    SIDECAR_COLUMNS,
    UTEXAS_INPUT_COLUMNS,
    UTexasAdapterError,
    UTexasSourceRow,
    encode_aptamer_name_notes,
    extract_pubmed_id,
    extract_utexas,
    format_native_id,
    map_utexas_row,
    read_utexas_rows,
    validate_utexas_header,
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


def _col_ref(index: int, row: int) -> str:
    """Convert 0-based column index to an Excel A1-style reference."""
    n = index + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def write_synthetic_utexas_xlsx(
    path: Path,
    rows: list[dict[str, str]],
    *,
    worksheet_rows: list[int] | None = None,
    include_empty_trailing: int = 0,
) -> None:
    """Write a minimal OOXML workbook with the UTexas header schema.

    ``worksheet_rows`` supplies the Excel ``r`` attributes for data rows.
    When omitted, contiguous rows starting at 2 are used. Empty trailing
    physical rows may be appended with consecutive worksheet numbers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if worksheet_rows is None:
        worksheet_rows = list(range(2, 2 + len(rows)))
    if len(worksheet_rows) != len(rows):
        raise ValueError("worksheet_rows length must match rows length")

    shared: list[str] = list(UTEXAS_INPUT_COLUMNS)
    cell_plans: list[tuple[int, list[tuple[int, str | None]]]] = []

    def shared_index(text: str) -> int:
        shared.append(text)
        return len(shared) - 1

    for excel_row, values in zip(worksheet_rows, rows, strict=True):
        cells: list[tuple[int, int]] = []
        for col_i, header in enumerate(UTEXAS_INPUT_COLUMNS):
            value = values.get(header, "")
            if value == "":
                continue
            # Prefer shared-string storage for textual fidelity in fixtures.
            cells.append((col_i, shared_index(value)))
        cell_plans.append((excel_row, cells))

    next_row = (max(worksheet_rows) + 1) if worksheet_rows else 2
    for offset in range(include_empty_trailing):
        cell_plans.append((next_row + offset, []))

    sheet_rows_xml = [
        '<row r="1">'
        + "".join(
            f'<c r="{_col_ref(i, 1)}" t="s"><v>{i}</v></c>'
            for i in range(len(UTEXAS_INPUT_COLUMNS))
        )
        + "</row>"
    ]
    for excel_row, cells in cell_plans:
        if not cells:
            sheet_rows_xml.append(f'<row r="{excel_row}"/>')
            continue
        body = "".join(
            f'<c r="{_col_ref(col_i, excel_row)}" t="s"><v>{idx}</v></c>'
            for col_i, idx in cells
        )
        sheet_rows_xml.append(f'<row r="{excel_row}">{body}</row>')
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
        + "</sst>"
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_rows_xml)
        + "</sheetData></worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Dataset" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    wb_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("xl/sharedStrings.xml", shared_xml)


def _blank_source(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in UTEXAS_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _install_registry(
    repo: Path,
    *,
    relative_path: str,
    sha256: str,
    n_rows: int,
) -> Path:
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": "utexas",
                "source_dataset": "utexas_demo_v1",
                "path": relative_path,
                "sha256": sha256,
                "n_rows_expected": str(n_rows),
                "snapshot_date": "2026-08-04",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            }
        ],
    )
    return spec


def _demo_rows() -> list[dict[str, str]]:
    return [
        _blank_source(
            **{
                "Serial Number": "100",
                "Aptamer Sequence": "5'acgu[3'T]",
                "Target ": " Protein X ",
                "Citation": "Smith 1990",
                "Journal DOI": "https://doi.org/10.1000/demo",
                "Link to PubMed Entry": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                "Name of Aptamer": "Demo-1",
            }
        ),
        _blank_source(
            **{
                "Serial Number": "100",  # duplicate serial
                "Aptamer Sequence": "ACGT-ACGU",
                "Target ": "TargetY",
                "Citation": "",
                "Journal DOI": "",
                "Link to PubMed Entry": "not-a-pmid",
                "Name of Aptamer": "",
            }
        ),
        _blank_source(),  # blank physical row / blank serial
    ]


def test_format_native_id_uses_worksheet_row_padding() -> None:
    assert format_native_id(10) == "row_0010"
    assert format_native_id(1903) == "row_1903"


def test_extract_pubmed_id_deterministic() -> None:
    assert extract_pubmed_id("https://pubmed.ncbi.nlm.nih.gov/1697402/") == "1697402"
    assert extract_pubmed_id("1697402") == "1697402"
    assert extract_pubmed_id("not-a-pmid") == ""
    assert extract_pubmed_id("") == ""


def test_header_trailing_space_required() -> None:
    cols = list(UTEXAS_INPUT_COLUMNS)
    cols[7] = "Target"  # drop trailing space
    with pytest.raises(UTexasAdapterError, match="missing|extra|match"):
        validate_utexas_header(cols)


def test_duplicate_and_blank_serials_yield_unique_ids(tmp_path: Path) -> None:
    path = tmp_path / "demo.xlsx"
    rows = _demo_rows()
    # Use non-contiguous worksheet rows, mirroring the real workbook gap pattern.
    write_synthetic_utexas_xlsx(
        path,
        rows,
        worksheet_rows=[2, 3, 10],
    )
    result = extract_utexas(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    native_ids = [r["native_id"] for r in result.canonical_rows]
    record_ids = [r["record_id"] for r in result.canonical_rows]
    assert native_ids == ["row_0002", "row_0003", "row_0010"]
    assert record_ids == [
        "utexas:row_0002",
        "utexas:row_0003",
        "utexas:row_0010",
    ]
    assert len(set(native_ids)) == 3
    assert len(set(record_ids)) == 3
    serials = [r["utexas_serial_number"] for r in result.sidecar_rows]
    assert serials == ["100", "100", ""]
    assert result.stats.duplicate_serial_keys == 1
    assert result.stats.rows_in_duplicate_serial_groups == 2
    assert result.stats.blank_serials == 1


def test_verbatim_sequence_and_target_preservation(tmp_path: Path) -> None:
    path = tmp_path / "verbatim.xlsx"
    quirky = "5' acguACGU TtUu [3'T] ;!! "
    target = "  Target with spaces  "
    write_synthetic_utexas_xlsx(
        path,
        [
            _blank_source(
                **{
                    "Serial Number": "1",
                    "Aptamer Sequence": quirky,
                    "Target ": target,
                }
            )
        ],
    )
    result = extract_utexas(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.canonical_rows[0]["sequence_raw"] == quirky
    assert result.canonical_rows[0]["target_name_raw"] == target
    assert result.sidecar_rows[0]["utexas_aptamer_sequence"] == quirky
    assert result.sidecar_rows[0]["utexas_target"] == target


def test_empty_physical_rows_retained(tmp_path: Path) -> None:
    path = tmp_path / "empty_rows.xlsx"
    write_synthetic_utexas_xlsx(
        path,
        [_blank_source(**{"Aptamer Sequence": "ACGU", "Target ": "T1"})],
        include_empty_trailing=2,
    )
    result = extract_utexas(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 3
    assert result.stats.nonempty_sequences == 1
    assert result.stats.missing_sequences == 2
    assert result.canonical_rows[1]["sequence_raw"] == ""
    assert result.canonical_rows[2]["sequence_raw"] == ""
    assert result.canonical_rows[1]["native_id"] == "row_0003"
    assert result.canonical_rows[2]["native_id"] == "row_0004"


def test_s1_forbidden_fields_remain_empty(tmp_path: Path) -> None:
    path = tmp_path / "boundary.xlsx"
    write_synthetic_utexas_xlsx(
        path,
        [
            _blank_source(
                **{
                    "Aptamer Sequence": "ACGU",
                    "Target ": "T",
                    "Type of Nucleic Acid": "ssRNA",
                    "Kd (nM)": "1.2",
                    "Affinity": "high",
                }
            )
        ],
    )
    result = extract_utexas(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    record = result.canonical_rows[0]
    for field in S1_FORBIDDEN_FIELDS:
        assert record[field] == "", field
    assert list(record.keys()) == list(CORPUS_COLUMNS)
    # Source molecule/Kd text is preserved only in the sidecar.
    assert result.sidecar_rows[0]["utexas_type_of_nucleic_acid"] == "ssRNA"
    assert result.sidecar_rows[0]["utexas_kd_nm"] == "1.2"


def test_identifiers_deterministic_across_reads(tmp_path: Path) -> None:
    path = tmp_path / "det.xlsx"
    write_synthetic_utexas_xlsx(path, _demo_rows(), worksheet_rows=[5, 6, 20])
    first = extract_utexas(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    second = extract_utexas(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert [r["record_id"] for r in first.canonical_rows] == [
        r["record_id"] for r in second.canonical_rows
    ]
    assert [r["native_id"] for r in first.canonical_rows] == [
        r["native_id"] for r in second.canonical_rows
    ]


def test_map_row_provenance_and_notes() -> None:
    source = UTexasSourceRow(
        worksheet_row=10,
        values=_blank_source(
            **{
                "Aptamer Sequence": "ACGU",
                "Target ": "Prot",
                "Citation": "Cite",
                "Journal DOI": "10.1/x",
                "Link to PubMed Entry": "https://pubmed.ncbi.nlm.nih.gov/99/",
                "Name of Aptamer": "N1",
                "Serial Number": "7",
            }
        ),
    )
    canonical, sidecar = map_utexas_row(
        source,
        source_dataset="ds",
        redistribution_status="unknown",
    )
    assert canonical["record_id"] == "utexas:row_0010"
    assert canonical["native_id"] == "row_0010"
    assert canonical["source_db"] == "utexas"
    assert canonical["contributing_sources"] == "utexas"
    assert canonical["corroboration_count"] == "1"
    assert canonical["independently_attested_by_permissive_source"] == "false"
    assert canonical["publication"] == "Cite"
    assert canonical["doi"] == "10.1/x"
    assert canonical["pubmed_id"] == "99"
    assert json.loads(canonical["notes"]) == {"aptamer_name": "N1"}
    assert sidecar["utexas_worksheet_row"] == "10"
    assert sidecar["utexas_serial_number"] == "7"
    assert encode_aptamer_name_notes("") == ""


def test_expected_row_mismatch_hard_fails(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.xlsx"
    write_synthetic_utexas_xlsx(path, _demo_rows())
    with pytest.raises(UTexasAdapterError, match="row count"):
        extract_utexas(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=999,
        )


def test_registry_sha_mismatch_fails_before_adapter(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "UTexas_aptamer_dataset").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    relative = (
        "data/raw/UTexas_aptamer_dataset/"
        "UTexas Aptamer Database dataset_Sept2023.xlsx"
    )
    xlsx = repo / relative
    write_synthetic_utexas_xlsx(xlsx, _demo_rows())
    _install_registry(
        repo,
        relative_path=relative,
        sha256="0" * 64,
        n_rows=3,
    )
    with pytest.raises((RegistryError, S1ExtractError), match="SHA-256|sha256"):
        run_s1_extraction(
            repo_root=repo,
            source_key="utexas",
            registry_spec=repo / "config" / "source_registry.csv",
            output_dir=Path("data/interim/extracted"),
        )
    out = repo / "data" / "interim" / "extracted" / "utexas_extracted.csv"
    assert not out.exists()


def test_registry_row_count_mismatch_fails_before_adapter(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "UTexas_aptamer_dataset").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    relative = (
        "data/raw/UTexas_aptamer_dataset/"
        "UTexas Aptamer Database dataset_Sept2023.xlsx"
    )
    xlsx = repo / relative
    write_synthetic_utexas_xlsx(xlsx, _demo_rows())
    digest = _hash_path(xlsx)
    _install_registry(
        repo,
        relative_path=relative,
        sha256=digest,
        n_rows=999,
    )
    with pytest.raises((RegistryError, S1ExtractError), match="[Rr]ow"):
        run_s1_extraction(
            repo_root=repo,
            source_key="utexas",
            registry_spec=repo / "config" / "source_registry.csv",
            output_dir=Path("data/interim/extracted"),
        )


def test_runner_end_to_end_synthetic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "UTexas_aptamer_dataset").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    relative = (
        "data/raw/UTexas_aptamer_dataset/"
        "UTexas Aptamer Database dataset_Sept2023.xlsx"
    )
    xlsx = repo / relative
    write_synthetic_utexas_xlsx(xlsx, _demo_rows(), include_empty_trailing=0)
    digest = _hash_path(xlsx)
    _install_registry(
        repo,
        relative_path=relative,
        sha256=digest,
        n_rows=3,
    )
    result = run_s1_extraction(
        repo_root=repo,
        source_key="utexas",
        registry_spec=repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
        check_deterministic_rerun=True,
    )
    assert result.stats.input_rows == 3
    assert result.deterministic_rerun_ok is True
    assert result.input_hash_unchanged is True
    canonical = repo / "data" / "interim" / "extracted" / "utexas_extracted.csv"
    sidecar = repo / "data" / "interim" / "extracted" / "utexas_source_metadata.csv"
    report = repo / "data" / "interim" / "extracted" / "utexas_s1_report.md"
    assert canonical.is_file()
    assert sidecar.is_file()
    assert report.is_file()
    with canonical.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(CORPUS_COLUMNS)
        out_rows = list(reader)
    assert len(out_rows) == 3
    assert out_rows[0]["sequence_raw"] == "5'acgu[3'T]"
    assert "S2 has not started" in report.read_text(encoding="utf-8")
    with sidecar.open(encoding="utf-8", newline="") as handle:
        side_reader = csv.DictReader(handle)
        assert list(side_reader.fieldnames or []) == list(SIDECAR_COLUMNS)


@pytest.mark.skipif(
    not (
        REPO_ROOT
        / "data/raw/UTexas_aptamer_dataset/"
        "UTexas Aptamer Database dataset_Sept2023.xlsx"
    ).is_file(),
    reason="Registered UTexas workbook not present locally",
)
def test_real_workbook_row_preservation_counts() -> None:
    """Optional local-only gate for the registered workbook snapshot."""
    path = (
        REPO_ROOT
        / "data/raw/UTexas_aptamer_dataset/"
        "UTexas Aptamer Database dataset_Sept2023.xlsx"
    )
    source_rows, sheet_name = read_utexas_rows(path)
    assert sheet_name == "Dataset"
    assert len(source_rows) == EXPECTED_INPUT_ROWS
    assert source_rows[0].worksheet_row == 2
    # Gap after row 1496 in the registered workbook.
    worksheet_nums = [r.worksheet_row for r in source_rows]
    assert 1497 not in worksheet_nums
    assert max(worksheet_nums) == 1903
    nonempty_seq = sum(
        1 for r in source_rows if r.values["Aptamer Sequence"] != ""
    )
    empty_seq = sum(1 for r in source_rows if r.values["Aptamer Sequence"] == "")
    assert nonempty_seq == 1495
    assert empty_seq == 399
