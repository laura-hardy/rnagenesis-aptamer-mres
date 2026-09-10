"""Unit tests for AptaBase HTML parsing using saved fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
FIXTURES_DIR = REPO_ROOT / "data" / "raw" / "aptabase" / "fixtures"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aptabase_parser import (  # noqa: E402
    EXPECTED_HEADERS,
    parse_aptabase_html_file,
    parse_html_directory,
)


@pytest.fixture(scope="module")
def fixture_frames():
    assert FIXTURES_DIR.exists(), f"Missing fixtures directory: {FIXTURES_DIR}"
    pages = {}
    for page in (1, 2, 37, 61):
        path = FIXTURES_DIR / f"page_{page:03d}.html"
        records = parse_aptabase_html_file(path, source_page=page)
        pages[page] = records
    return pages


def test_page_1_returns_ten_rows(fixture_frames):
    assert len(fixture_frames[1]) == 10
    ids = [r["record_id_raw"] for r in fixture_frames[1]]
    assert ids == [str(i) for i in range(1, 11)]


def test_page_2_returns_ten_rows(fixture_frames):
    assert len(fixture_frames[2]) == 10
    ids = [r["record_id_raw"] for r in fixture_frames[2]]
    assert ids == [str(i) for i in range(11, 21)]


def test_page_37_returns_ten_rows(fixture_frames):
    assert len(fixture_frames[37]) == 10
    ids = [r["record_id_raw"] for r in fixture_frames[37]]
    assert ids == [str(i) for i in range(361, 371)]


def test_page_61_returns_all_visible_rows(fixture_frames):
    records = fixture_frames[61]
    assert len(records) == 10
    ids = [r["record_id_raw"] for r in records]
    assert ids == ["601", "602", "603", "604", "605", "613", "614", "616", "617", "618"]


def test_each_well_formed_row_has_ten_cells(fixture_frames):
    for page, records in fixture_frames.items():
        for record in records:
            # Parser stores ten raw fields; malformed rows are flagged.
            assert record["row_parse_status"] in {"ok", "malformed"}
            if record["row_parse_status"] == "ok":
                for key in [
                    "record_id_raw",
                    "aptamer_name_raw",
                    "target_general_raw",
                    "target_specific_raw",
                    "reported_length_raw",
                    "affinity_raw",
                    "buffer_raw",
                    "gc_content_raw",
                    "sequence_raw",
                    "reference_raw",
                ]:
                    assert key in record


def test_record_1_parses_correctly(fixture_frames):
    record = fixture_frames[1][0]
    assert record["record_id_raw"] == "1"
    assert record["aptamer_name_raw"] == "N53"
    assert record["target_general_raw"] == "Protein"
    assert "hFABP3" in record["target_specific_raw"]
    assert record["reported_length_raw"] == "90"
    assert record["gc_content_raw"] == "66.70%"
    assert "CACCTAATACGACTCACTATA" in record["sequence_raw"]
    assert record["source_page"] == 1
    assert record["row_parse_status"] == "ok"


def test_parse_html_directory_combines_fixtures():
    frame = parse_html_directory(FIXTURES_DIR)
    assert len(frame) == 40
    assert set(frame["source_page"].astype(int)) == {1, 2, 37, 61}


def test_expected_headers_constant():
    assert len(EXPECTED_HEADERS) == 10
    assert EXPECTED_HEADERS[0] == "#"
    assert EXPECTED_HEADERS[-1] == "Reference"
