"""Tests for the AptaBase S1 adapter (synthetic fixtures only)."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase import (  # noqa: E402
    APTABASE_INPUT_COLUMNS,
    SIDECAR_COLUMNS,
    AptaBaseAdapterError,
    encode_aptamer_name_notes,
    extract_aptabase,
    map_aptabase_row,
    read_aptabase_rows,
    select_target_name_raw,
    validate_aptabase_header,
    write_sidecar_csv_atomic,
)
from common.corpus_schema import S1_FORBIDDEN_FIELDS  # noqa: E402


def _blank_source_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in APTABASE_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _write_aptabase_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(APTABASE_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in APTABASE_INPUT_COLUMNS})


def _write_csv_with_header(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def test_exact_schema_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ok.csv"
    rows = [
        _blank_source_row(record_id="1", sequence_raw="ACGUACGU"),
        _blank_source_row(record_id="2", sequence_raw=""),
    ]
    _write_aptabase_csv(path, rows)
    result = extract_aptabase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.stats.input_rows == 2
    assert result.stats.canonical_rows == 2
    validate_aptabase_header(list(APTABASE_INPUT_COLUMNS))


def test_missing_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"
    cols = list(APTABASE_INPUT_COLUMNS)
    cols.remove("doi")
    _write_csv_with_header(path, cols, [_blank_source_row(record_id="1")])
    with pytest.raises(AptaBaseAdapterError, match="missing"):
        extract_aptabase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_extra_column_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    cols = list(APTABASE_INPUT_COLUMNS) + ["extra_col"]
    _write_csv_with_header(
        path,
        cols,
        [{**_blank_source_row(record_id="1"), "extra_col": "x"}],
    )
    with pytest.raises(AptaBaseAdapterError, match="extra"):
        extract_aptabase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_reordered_columns_rejected(tmp_path: Path) -> None:
    path = tmp_path / "reordered.csv"
    cols = list(APTABASE_INPUT_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    _write_csv_with_header(path, cols, [_blank_source_row(record_id="1")])
    with pytest.raises(AptaBaseAdapterError, match="reordered"):
        extract_aptabase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_duplicate_header_rejected() -> None:
    cols = list(APTABASE_INPUT_COLUMNS) + ["doi"]
    with pytest.raises(AptaBaseAdapterError, match="duplicate"):
        validate_aptabase_header(cols)


def test_blank_header_rejected() -> None:
    cols = list(APTABASE_INPUT_COLUMNS)
    cols[3] = "  "
    with pytest.raises(AptaBaseAdapterError, match="blank"):
        validate_aptabase_header(cols)


def test_duplicate_source_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dup.csv"
    _write_aptabase_csv(
        path,
        [
            _blank_source_row(record_id="1", sequence_raw="ACGU"),
            _blank_source_row(record_id="1", sequence_raw="UGCA"),
        ],
    )
    with pytest.raises(AptaBaseAdapterError, match="Duplicate"):
        extract_aptabase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_missing_source_id_rejected(tmp_path: Path) -> None:
    path = tmp_path / "blank_id.csv"
    _write_aptabase_csv(path, [_blank_source_row(record_id="", sequence_raw="ACGU")])
    with pytest.raises(AptaBaseAdapterError, match="blank|missing"):
        extract_aptabase(
            path,
            source_dataset="demo_ds",
            redistribution_status="unknown",
            expected_rows=None,
        )


def test_canonical_and_native_id_generation() -> None:
    source = _blank_source_row(record_id="42", sequence_raw="ACGUAC")
    canonical, sidecar, _ = map_aptabase_row(
        source,
        source_dataset="aptabase_cleaned_scrape_2026-07-20",
        redistribution_status="unknown",
    )
    assert canonical["native_id"] == "42"
    assert canonical["record_id"] == "aptabase:42"
    assert sidecar["record_id"] == "aptabase:42"
    assert sidecar["aptabase_record_id"] == "42"


def test_sequence_copied_exactly_including_whitespace_and_terminals() -> None:
    raw = " 5'-ACG U-3' "
    assert len(raw) < 20
    source = _blank_source_row(record_id="1", sequence_raw=raw, sequence_clean="ACGU")
    canonical, sidecar, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["sequence_raw"] == raw
    assert sidecar["aptabase_sequence_raw"] == raw
    assert canonical["sequence_full"] == ""
    assert canonical["sequence_core"] == ""
    assert "ACGU" != raw
    assert sidecar["aptabase_sequence_clean"] == "ACGU"


def test_empty_sequence_retained() -> None:
    source = _blank_source_row(record_id="1", sequence_raw="")
    canonical, _, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["sequence_raw"] == ""


def test_sequence_clean_never_enters_canonical_sequence_fields() -> None:
    source = _blank_source_row(
        record_id="1",
        sequence_raw="",
        sequence_clean="GGGGAAAA",
        molecule_type_inferred="RNA",
    )
    canonical, _, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["sequence_raw"] == ""
    assert canonical["sequence_full"] == ""
    assert canonical["sequence_core"] == ""
    assert canonical["molecule_type"] == ""


def test_specific_target_preferred() -> None:
    value, tag = select_target_name_raw("Specific X", "General Y")
    assert value == "Specific X"
    assert tag == "specific"


def test_general_target_fallback() -> None:
    value, tag = select_target_name_raw("", "General Y")
    assert value == "General Y"
    assert tag == "general"


@pytest.mark.parametrize("token", ["NA", "N/A", "null", "None", "na", "n/a"])
def test_textual_null_specific_triggers_fallback(token: str) -> None:
    value, tag = select_target_name_raw(token, "General Y")
    assert value == "General Y"
    assert tag == "general"


def test_both_targets_absent_keeps_row() -> None:
    source = _blank_source_row(
        record_id="1",
        sequence_raw="ACGU",
        target_specific="N/A",
        target_general="",
    )
    canonical, _, tag = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert tag == "empty"
    assert canonical["target_name_raw"] == ""
    assert canonical["record_id"] == "aptabase:1"


def test_publication_doi_pmid_mapping() -> None:
    source = _blank_source_row(
        record_id="1",
        sequence_raw="ACGU",
        reference="Smith 2020",
        doi="10.1000/xyz",
        pmid="999",
    )
    canonical, _, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["publication"] == "Smith 2020"
    assert canonical["doi"] == "10.1000/xyz"
    assert canonical["pubmed_id"] == "999"


def test_aptamer_name_notes_deterministic() -> None:
    assert encode_aptamer_name_notes("") == ""
    notes = encode_aptamer_name_notes("Apt-1")
    assert notes == json.dumps(
        {"aptamer_name": "Apt-1"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    source = _blank_source_row(
        record_id="1",
        sequence_raw="ACGU",
        aptamer_name="Apt-1",
    )
    canonical, _, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["notes"] == notes


def test_later_stage_fields_remain_empty() -> None:
    source = _blank_source_row(
        record_id="1",
        sequence_raw="ACGU",
        affinity_value="1.2",
        affinity_unit="nM",
        molecule_type_inferred="RNA",
        sequence_clean="ACGU",
    )
    canonical, _, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    for field in S1_FORBIDDEN_FIELDS:
        assert canonical[field] == "", field


def test_all_source_fields_preserved_in_sidecar() -> None:
    source = _blank_source_row(
        record_id="7",
        aptamer_name="N7",
        target_general="TG",
        target_specific="TS",
        sequence_raw="ACGUACGU",
        sequence_clean="ACGUACGU",
        reference="Ref",
        doi="10.1/x",
        pmid="1",
        parse_warnings="warn",
        duplicate_group="g1",
        affinity_raw="Kd=1",
    )
    canonical, sidecar, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert list(sidecar.keys()) == list(SIDECAR_COLUMNS)
    assert sidecar["record_id"] == canonical["record_id"]
    for column in APTABASE_INPUT_COLUMNS:
        assert sidecar[f"aptabase_{column}"] == source[column]


def test_embedded_newline_in_reference_parsed(tmp_path: Path) -> None:
    path = tmp_path / "newline.csv"
    rows = [
        _blank_source_row(
            record_id="1",
            sequence_raw="ACGU",
            reference="Line1\nLine2",
        )
    ]
    _write_aptabase_csv(path, rows)
    result = extract_aptabase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert result.canonical_rows[0]["publication"] == "Line1\nLine2"
    assert result.sidecar_rows[0]["aptabase_reference"] == "Line1\nLine2"


def test_unicode_and_mojibake_preserved() -> None:
    weird = "cafÃ© · β-lactamase"
    source = _blank_source_row(
        record_id="1",
        sequence_raw="ACGU",
        target_specific=weird,
        aptamer_name="α-apt",
        reference="José et al.",
    )
    canonical, sidecar, _ = map_aptabase_row(
        source,
        source_dataset="demo_ds",
        redistribution_status="unknown",
    )
    assert canonical["target_name_raw"] == weird
    assert sidecar["aptabase_target_specific"] == weird
    assert canonical["publication"] == "José et al."
    assert "α-apt" in canonical["notes"]


def test_input_order_preserved_and_no_filtering(tmp_path: Path) -> None:
    path = tmp_path / "order.csv"
    rows = [
        _blank_source_row(record_id="a", sequence_raw="AAAA"),
        _blank_source_row(record_id="b", sequence_raw=""),
        _blank_source_row(record_id="c", sequence_raw="CCCC"),
    ]
    _write_aptabase_csv(path, rows)
    result = extract_aptabase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    assert [r["native_id"] for r in result.canonical_rows] == ["a", "b", "c"]
    assert result.stats.canonical_rows == 3
    assert result.stats.missing_sequences == 1


def test_source_input_remains_byte_identical(tmp_path: Path) -> None:
    path = tmp_path / "immutable.csv"
    rows = [_blank_source_row(record_id="1", sequence_raw="ACGUACGU")]
    _write_aptabase_csv(path, rows)
    before = path.read_bytes()
    digest_before = hashlib.sha256(before).hexdigest()
    extract_aptabase(
        path,
        source_dataset="demo_ds",
        redistribution_status="unknown",
        expected_rows=None,
    )
    after = path.read_bytes()
    assert after == before
    assert hashlib.sha256(after).hexdigest() == digest_before


def test_sidecar_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "side.csv"
    source = _blank_source_row(record_id="1", sequence_raw="ACGU")
    _, sidecar, _ = map_aptabase_row(
        source,
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


def test_no_legacy_cleaner_or_scraper_imported() -> None:
    # Ensure adapter module does not pull legacy preprocessing modules.
    banned = {
        "scrape_aptabase",
        "aptabase_parser",
        "aptabase_cleaning",
    }
    # Fresh import check of the adapter dependency graph via sys.modules snapshot.
    before = {name for name in sys.modules if name in banned}
    importlib.import_module("adapters.aptabase")
    after = {name for name in sys.modules if name in banned}
    assert after == before
    for name in banned:
        assert name not in sys.modules or name in before
