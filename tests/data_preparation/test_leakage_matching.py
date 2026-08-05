"""Tests for leakage-specific sequence comparison helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.leakage_matching import (  # noqa: E402
    IDENTITY_THRESHOLD,
    LeakageMatchingError,
    comparison_form,
    edit_distance,
    global_edit_identity,
    meets_identity_threshold,
    prepare_molecule_native_sequence,
    remove_display_artifacts,
    rna_form_from_dna_alphabet,
    validate_simple_nucleotide_string,
)


def test_tu_comparison_equivalence() -> None:
    dna = "ACGTACGTAC"
    rna = "ACGUACGUAC"
    assert comparison_form(dna) == comparison_form(rna)
    assert global_edit_identity(comparison_form(dna), comparison_form(rna)) == 1.0


def test_global_edit_identity_and_threshold() -> None:
    # 10 nt vs 1 substitution → identity 0.90 exactly.
    a = "ACGTACGTAC"
    b = "ACGTACGTAG"
    assert len(a) == 10 and edit_distance(a, b) == 1
    identity = global_edit_identity(a, b)
    assert identity == pytest.approx(0.90)
    assert meets_identity_threshold(a, b) is True

    # 2 substitutions on length-10 → 0.80, below threshold.
    c = "ACGTACGAAA"
    assert edit_distance(a, c) == 2
    assert global_edit_identity(a, c) == pytest.approx(0.80)
    assert meets_identity_threshold(a, c) is False


def test_empty_sequence_comparison_rejected() -> None:
    with pytest.raises(LeakageMatchingError):
        global_edit_identity("", "ACGT")
    with pytest.raises(LeakageMatchingError):
        global_edit_identity("ACGT", "")


def test_rna_printed_with_t_converted_only_for_rna() -> None:
    raw = "ACGTAC"
    rna, applied = prepare_molecule_native_sequence(
        raw, molecule_type="RNA", alphabet_as_reported="DNA_T"
    )
    assert rna == "ACGUAC"
    assert applied is True

    dna, applied_dna = prepare_molecule_native_sequence(
        raw, molecule_type="ssDNA", alphabet_as_reported="DNA"
    )
    assert dna == "ACGTAC"
    assert applied_dna is False

    with pytest.raises(LeakageMatchingError):
        rna_form_from_dna_alphabet(raw, molecule_type="ssDNA")


def test_ssdna_retains_t() -> None:
    seq, applied = prepare_molecule_native_sequence(
        "5'-ACGT-3'", molecule_type="ssDNA", alphabet_as_reported="DNA"
    )
    assert seq == "ACGT"
    assert applied is False
    assert "U" not in seq


def test_display_cleanup_and_validation() -> None:
    cleaned = remove_display_artifacts("5′ AC GT -- AC 3'")
    assert cleaned == "ACGTAC"
    validate_simple_nucleotide_string(cleaned)
    with pytest.raises(LeakageMatchingError):
        validate_simple_nucleotide_string("ACGX")


def test_identity_threshold_constant() -> None:
    assert IDENTITY_THRESHOLD == 0.90
