"""Frozen-checkpoint overlay for the seven approved Aptabase corrections."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aptabase_seven_record_overlay import (  # noqa: E402
    FROZEN_BASELINE_REL,
    FROZEN_REVIEW_REL,
    build_overlay,
    resolve_overlay_checkpoint,
)

APPROVED = {
    "aptabase:592",
    "aptabase:593",
    "aptabase:104",
    "aptabase:185",
    "aptabase:118",
    "aptabase:123",
    "aptabase:82",
}
CORE_CHANGED = {
    "aptabase:104",
    "aptabase:185",
    "aptabase:118",
    "aptabase:123",
    "aptabase:82",
}
PEPTIDES = {f"aptabase:{i}" for i in list(range(200, 211)) + [213]}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def overlay():
    baseline = REPO_ROOT / FROZEN_BASELINE_REL
    if not baseline.is_file():
        pytest.skip("frozen Aptabase baseline is not present")
    return build_overlay(repo_root=REPO_ROOT)


def test_only_five_cores_change(overlay) -> None:
    _fields, rows, _review_fields, _review = overlay
    frozen = {row["record_id"]: row for row in _read(REPO_ROOT / FROZEN_BASELINE_REL)}
    changed = [
        row["record_id"]
        for row in rows
        if row["sequence_core"] != frozen[row["record_id"]]["sequence_core"]
    ]
    assert set(changed) == CORE_CHANGED
    for row in rows:
        assert row["sequence_raw"] == frozen[row["record_id"]]["sequence_raw"]
        if row["record_id"] in CORE_CHANGED:
            assert "T" not in row["sequence_core"]
            assert row["t_to_u_applied"] == "false"


def test_non_seven_scientific_fields_match_frozen_baseline(overlay) -> None:
    _fields, rows, _review_fields, review_rows = overlay
    frozen = {row["record_id"]: row for row in _read(REPO_ROOT / FROZEN_BASELINE_REL)}
    frozen_review = {
        row["record_id"]: row for row in _read(REPO_ROOT / FROZEN_REVIEW_REL)
    }
    compared = (
        "sequence_core",
        "molecule_type",
        "proposed_decision",
        "primary_reason",
    )
    for row in rows:
        if row["record_id"] in APPROVED:
            continue
        original = frozen[row["record_id"]]
        for field in compared:
            assert row[field] == original[field]
        assert row.get("chemistry", "") == ""
    for row in review_rows:
        if row["record_id"] in APPROVED:
            continue
        assert row == frozen_review[row["record_id"]]


def test_overlay_resolution_authorises_only_the_approved_accepts(overlay) -> None:
    _fields, rows, _review_fields, review_rows = overlay
    frozen_resolutions = _read(
        REPO_ROOT / "data/interim/checkpoints/aptabase_cp1/resolved/aptabase_checkpoint1_resolution.csv"
    )
    resolutions = {
        row["record_id"]: row
        for row in resolve_overlay_checkpoint(rows, review_rows, frozen_resolutions)
    }
    assert len(resolutions) == 610
    for record_id in ("aptabase:592", "aptabase:593", "aptabase:104"):
        assert resolutions[record_id]["review_action"] == "confirm_current"
        assert resolutions[record_id]["authorised_for_s4"] == "false"
    for record_id in ("aptabase:185", "aptabase:118", "aptabase:123", "aptabase:82"):
        assert resolutions[record_id]["authorised_for_s4"] == "true"
        assert resolutions[record_id]["resolved_decision"] == "accept"
    for record_id in PEPTIDES:
        assert resolutions[record_id]["resolved_decision"] == "reject"
        assert resolutions[record_id]["authorised_for_s4"] == "false"


def test_approved_routes_and_peptide_records_stay_frozen(overlay) -> None:
    _fields, rows, _review_fields, review_rows = overlay
    by_id = {row["record_id"]: row for row in rows}
    review = {row["record_id"]: row for row in review_rows}
    assert by_id["aptabase:104"]["sequence_length_core"] == "19"
    assert by_id["aptabase:104"]["proposed_decision"] == "proposed_reject"
    assert by_id["aptabase:104"]["primary_reason"] == "core_below_minimum"
    for record_id in ("aptabase:592", "aptabase:593"):
        assert by_id[record_id]["molecule_type"] == "ssDNA"
        assert by_id[record_id]["chemistry"] == "DNA"
        assert "T" in by_id[record_id]["sequence_core"]
        assert by_id[record_id]["proposed_decision"] == "proposed_park"
        assert review[record_id]["review_action"] == "confirm_current"
        assert review[record_id]["review_batch"] == "04_park_ssdna"
    for record_id in ("aptabase:185", "aptabase:118", "aptabase:123", "aptabase:82"):
        assert by_id[record_id]["proposed_decision"] == "proposed_accept"
        assert review[record_id]["review_action"] == "confirm_current"
        assert review[record_id]["review_batch"] == "02_accept_with_diagnostics"
    frozen = {row["record_id"]: row for row in _read(REPO_ROOT / FROZEN_BASELINE_REL)}
    for record_id in PEPTIDES:
        assert by_id[record_id]["proposed_decision"] == "proposed_reject"
        assert by_id[record_id]["primary_reason"] == "core_below_minimum"
        assert by_id[record_id]["sequence_core"] == frozen[record_id]["sequence_core"]
        assert review[record_id]["review_batch"] == "01_reject_review"
