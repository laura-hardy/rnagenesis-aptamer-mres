"""Tests for Aim 3 Stage 1 hard filtering."""

from __future__ import annotations

from pathlib import Path

import pytest

from aim3_pipeline.config import Stage1Config
from aim3_pipeline.io import strip_leading_artifact, validate_rna_alphabet
from aim3_pipeline.stage1_hard_filter import (
    RNAImportError,
    apply_exact_dedup_filter,
    apply_gc_filter,
    apply_homopolymer_filter,
    apply_length_filter,
    apply_mfe_filter,
    apply_near_dedup_filter,
    assign_exact_deduplication,
    build_preprocessed_records,
    compute_gc_fraction,
    compute_max_homopolymer_run,
    compute_mfe,
    finalise_stage1_record,
    try_import_rna,
)


def test_strip_leading_11():
    cleaned, stripped = strip_leading_artifact("11AUCG")
    assert cleaned == "AUCG"
    assert stripped is True

    cleaned, stripped = strip_leading_artifact("AUCG")
    assert cleaned == "AUCG"
    assert stripped is False


def test_alphabet_validation():
    valid, invalid = validate_rna_alphabet("AUCG")
    assert valid is True
    assert invalid == ""

    valid, invalid = validate_rna_alphabet("AUCGX")
    assert valid is False
    assert invalid == "X"


def test_length_calculation_in_preprocessing(tmp_path: Path):
    input_file = tmp_path / "sample.txt"
    input_file.write_text("11AUCG\n", encoding="utf-8")
    config = Stage1Config()
    records = build_preprocessed_records([input_file], "test_condition", config)
    assert len(records) == 1
    assert records[0]["raw_length"] == 6
    assert records[0]["cleaned_length"] == 4
    assert records[0]["cleaning_notes"] == "stripped_leading_11"


def test_duplicate_handling():
    records = [
        {
            "sequence_id": "a",
            "cleaned_sequence": "AUCG",
        },
        {
            "sequence_id": "b",
            "cleaned_sequence": "AUCG",
        },
        {
            "sequence_id": "c",
            "cleaned_sequence": "GGGG",
        },
    ]
    assign_exact_deduplication(records)
    config = Stage1Config()

    apply_exact_dedup_filter(records[0], config)
    apply_exact_dedup_filter(records[1], config)
    apply_exact_dedup_filter(records[2], config)

    assert records[0]["duplicate_rank_within_condition"] == 1
    assert records[0]["passes_exact_dedup"] is True
    assert records[1]["duplicate_rank_within_condition"] == 2
    assert records[1]["is_exact_duplicate_within_condition"] is True
    assert records[1]["passes_exact_dedup"] is False
    assert records[1]["duplicate_representative_id"] == "a"


def test_homopolymer_max_run():
    assert compute_max_homopolymer_run("") == 0
    assert compute_max_homopolymer_run("A") == 1
    assert compute_max_homopolymer_run("AAAACG") == 4
    assert compute_max_homopolymer_run("AAAAA") == 5


def test_homopolymer_filter_fail():
    record = {
        "cleaned_sequence": "AAAAA",
        "alphabet_valid": True,
    }
    apply_homopolymer_filter(record, Stage1Config())
    assert record["max_homopolymer_run"] == 5
    assert record["passes_homopolymer_filter"] is False


def test_gc_fraction():
    assert compute_gc_fraction("AUCG") == 0.5
    assert compute_gc_fraction("AAAA") == 0.0


def test_gc_filter_not_applied_by_default():
    record = {"cleaned_sequence": "AAAA", "alphabet_valid": True}
    apply_gc_filter(record, Stage1Config())
    assert record["gc_filter_status"] == "not_applied"
    assert record["passes_gc_filter"] is True
    assert record["gc_fraction"] == 0.0


def test_length_filter_not_applied_by_default():
    record = {"cleaned_length": 10}
    apply_length_filter(record, Stage1Config())
    assert record["length_filter_status"] == "not_applied"
    assert record["passes_length_filter"] is True


def test_mfe_on_tiny_sequence():
    try:
        rna = try_import_rna()
    except RNAImportError:
        pytest.skip("ViennaRNA not available")
    structure, mfe = compute_mfe("GCGCGCGC", rna_module=rna)
    assert isinstance(structure, str)
    assert len(structure) == 8
    assert isinstance(mfe, float)


def test_mfe_filter_not_applied_by_default():
    try:
        rna = try_import_rna()
    except RNAImportError:
        pytest.skip("ViennaRNA not available")

    record = {"cleaned_sequence": "GCGCGCGC", "cleaned_length": 8, "alphabet_valid": True}
    apply_mfe_filter(record, Stage1Config(), skip_mfe=False, rna_module=rna)
    assert record["mfe_filter_status"] == "not_applied"
    assert record["passes_mfe_filter"] is True
    assert record["mfe"] is not None
    assert record["normalised_mfe"] == record["mfe"] / 8


def test_near_dedup_not_applied_without_reference():
    record = {"cleaned_sequence": "AUCG", "alphabet_valid": True}
    apply_near_dedup_filter(record, Stage1Config(), reference_sequences=None, distance_fn=None)
    assert record["near_dedup_filter_status"] == "not_applied_reference_missing"
    assert record["passes_near_dedup_filter"] is True
    assert record["nearest_reference_edit_distance"] is None


def test_final_failure_reasons():
    record = {
        "alphabet_valid": False,
        "passes_length_filter": True,
        "passes_exact_dedup": True,
        "passes_homopolymer_filter": False,
        "_homopolymer_fail_reasons": ["homopolymer_run>=5"],
        "passes_gc_filter": True,
        "passes_mfe_filter": True,
        "passes_near_dedup_filter": True,
    }
    finalise_stage1_record(record, Stage1Config())
    assert record["stage1_pass"] is False
    assert "invalid_alphabet" in record["stage1_failure_reasons"]
    assert "homopolymer_run>=5" in record["stage1_failure_reasons"]
