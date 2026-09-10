"""Unit tests for AptaBase cleaning, affinity parsing, and validity rules."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
FIXTURES_DIR = REPO_ROOT / "data" / "raw" / "aptabase" / "fixtures"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aptabase_cleaning import (  # noqa: E402
    calculate_gc_content,
    clean_raw_dataframe,
    normalise_sequence,
    parse_affinity,
    repair_text,
    summarise_duplicate_name_conflicts,
)
from aptabase_parser import parse_html_directory  # noqa: E402


@pytest.fixture(scope="module")
def fixture_cleaned():
    raw = parse_html_directory(FIXTURES_DIR)
    cleaned = clean_raw_dataframe(raw)
    return raw, cleaned


def test_dna_sequence_with_spaces_is_cleaned():
    raw = "TCA CCT CAT ACG ACT CAC TAT AGC GGA CCC"
    result = normalise_sequence(raw)
    assert result["sequence_clean"] == "TCACCTCATACGACTCACTATAGCGGACCC"
    assert result["sequence_alphabet"] == "DNA"
    assert result["sequence_normalization_status"] in {
        "success",
        "success_with_terminal_labels_removed",
    }


def test_rna_sequence_containing_u_classified_as_rna():
    raw = "5' GGGAACAGUCCGAGCCUCACUGUUAUCCGA 3'"
    result = normalise_sequence(raw)
    assert result["sequence_alphabet"] == "RNA"
    assert result["molecule_type_inferred"] == "RNA_like_sequence"
    assert "U" in result["sequence_clean"]
    assert "T" not in result["sequence_clean"]


def test_terminal_5_prime_3_prime_notation_removed():
    raw = "5′-ATACGGGAGCCAACACCAG-3′"
    result = normalise_sequence(raw)
    assert result["sequence_clean"] == "ATACGGGAGCCAACACCAG"
    assert "success_with_terminal_labels_removed" in result["sequence_normalization_status"]


def test_corrupted_terminal_primes_do_not_invalidate_dna():
    raw = "5?-UCCCGAUUACUGUACAUACCUUAGCCCAUAGCUGGCUGC-3?"
    result = normalise_sequence(raw)
    assert result["sequence_alphabet"] == "RNA"
    assert result["sequence_clean"].startswith("UCCC")
    assert "?" not in result["sequence_clean"]


def test_missing_sequences_remain_missing():
    result = normalise_sequence("")
    assert result["sequence_alphabet"] == "missing"
    assert result["sequence_clean"] == ""
    assert result["sequence_normalization_status"] == "missing"


def test_record_618_flagged_invalid(fixture_cleaned):
    _, cleaned = fixture_cleaned
    row = cleaned.loc[cleaned["record_id"] == 618].iloc[0]
    assert row["record_validity"] == "invalid"
    assert row["sequence_alphabet"] == "invalid"


def test_mojibake_repaired():
    repaired, changed = repair_text("13.1 Â± 2.10 Î¼M")
    assert changed is True
    assert "±" in repaired
    assert "µM" in repaired or "μM" in repaired
    assert "Â±" not in repaired
    assert "Î¼" not in repaired


def test_affinity_35_6_nm_to_molar():
    parsed = parse_affinity("35.6 nM")
    assert parsed["affinity_value"] == pytest.approx(35.6)
    assert parsed["affinity_unit"] == "nM"
    assert parsed["affinity_molar"] == pytest.approx(35.6e-9)
    assert parsed["affinity_measurement_type"] == "concentration"


def test_affinity_plus_minus_micromolar():
    parsed = parse_affinity("13.1 ± 2.10 µM")
    assert parsed["affinity_value"] == pytest.approx(13.1)
    assert parsed["affinity_uncertainty"] == pytest.approx(2.10)
    assert parsed["affinity_unit"] == "µM"
    assert parsed["affinity_molar"] == pytest.approx(13.1e-6)


def test_kcal_not_treated_as_molar_affinity():
    parsed = parse_affinity("8.34 kcal.mole-1")
    assert parsed["affinity_measurement_type"] == "energy_or_other"
    assert parsed["affinity_molar"] is None


def test_na_does_not_become_zero():
    parsed = parse_affinity("NA")
    assert parsed["affinity_molar"] is None
    assert parsed["affinity_value"] is None
    assert parsed["affinity_measurement_type"] == "unavailable"

    parsed2 = parse_affinity("na nM")
    assert parsed2["affinity_molar"] is None
    assert parsed2["affinity_value"] is None


def test_gc_content_calculated_correctly():
    # 50% GC: ACGT
    gc = calculate_gc_content("ACGT", "DNA")
    assert gc == pytest.approx(50.0)
    # All GC
    assert calculate_gc_content("GCGC", "DNA") == pytest.approx(100.0)
    assert calculate_gc_content("", "missing") is None


def test_duplicate_aptamer_names_detected(fixture_cleaned):
    # Create an artificial duplicate on top of fixtures for a clear signal,
    # and also check the helper on a hand-built frame.
    frame = pd.DataFrame(
        {
            "aptamer_name": ["N53", "N53", "Other"],
            "target_specific": ["A", "A", "B"],
            "reported_length": [90, 90, 10],
            "sequence_clean": ["ACGT", "", "TTTT"],
            "duplicate_group": ["dup_0001", "dup_0001", ""],
        }
    )
    summary = summarise_duplicate_name_conflicts(frame)
    assert summary["duplicate_name_count"] >= 1
    assert "N53" in summary["duplicate_names"]


def test_duplicate_records_are_retained(fixture_cleaned):
    raw, cleaned = fixture_cleaned
    assert len(cleaned) == len(raw)
    # Even invalid rows remain.
    assert (cleaned["record_id"] == 618).sum() == 1


def test_build_from_fixtures_does_not_contact_internet(fixture_cleaned):
    """Building cleaned outputs from fixtures must not use requests."""
    with patch("requests.Session.get") as mock_get:
        raw = parse_html_directory(FIXTURES_DIR)
        cleaned = clean_raw_dataframe(raw)
        assert len(cleaned) == 40
        mock_get.assert_not_called()


def test_fixture_affinity_mojibake_row(fixture_cleaned):
    _, cleaned = fixture_cleaned
    row = cleaned.loc[cleaned["record_id"] == 613].iloc[0]
    assert "±" in row["affinity_raw"]
    assert row["affinity_unit"] == "µM"
    assert row["affinity_value"] == pytest.approx(13.1)
    assert row["affinity_uncertainty"] == pytest.approx(2.10)


def test_missing_sequence_record_605_not_invalid_solely_for_missing(fixture_cleaned):
    _, cleaned = fixture_cleaned
    row = cleaned.loc[cleaned["record_id"] == 605].iloc[0]
    assert row["sequence_alphabet"] == "missing"
    assert row["record_validity"] != "invalid"
