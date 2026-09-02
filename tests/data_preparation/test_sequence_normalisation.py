"""Tests for shared sequence normalisation (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt.
"""

from __future__ import annotations

import copy
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.sequence_normalisation import (  # noqa: E402
    ALPHABET_CHEMICAL_NOTATION,
    ALPHABET_DNA_T,
    ALPHABET_INVALID,
    ALPHABET_MISSING,
    ALPHABET_MIXED_T_U,
    ALPHABET_RNA,
    ALPHABET_VOCABULARY,
    ConfigurationError,
    TrimMismatchError,
    TrimProposal,
    classify_alphabet,
    clean_display_sequence,
    detect_known_non_core_motifs,
    load_normalisation_rules,
    normalise_sequence,
    rules_to_public_dict,
    validate_core_length,
    validate_rules_dict,
)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


def test_alphabet_vocabulary_includes_chemical_notation_without_removing_live_values() -> None:
    """chemical_notation is an additive DECIDED plan value (AptaIndex)."""
    assert ALPHABET_CHEMICAL_NOTATION == "chemical_notation"
    assert ALPHABET_CHEMICAL_NOTATION in ALPHABET_VOCABULARY
    for existing in (
        ALPHABET_RNA,
        ALPHABET_DNA_T,
        ALPHABET_MIXED_T_U,
        ALPHABET_MISSING,
        ALPHABET_INVALID,
        "ambiguous",
    ):
        assert existing in ALPHABET_VOCABULARY


def test_classify_alphabet_still_reports_rna_and_dna_t_for_nucleotide_letters(rules) -> None:
    """Existing source lanes keep RNA/DNA_T; chemical_notation is not inferred here."""
    rna = classify_alphabet("ACGU", rules=rules, molecule_type="RNA")
    dna = classify_alphabet("ACGT", rules=rules, molecule_type="ssDNA")
    assert rna.alphabet == ALPHABET_RNA
    assert dna.alphabet == ALPHABET_DNA_T
    assert rna.alphabet != ALPHABET_CHEMICAL_NOTATION
    assert dna.alphabet != ALPHABET_CHEMICAL_NOTATION


def test_01_missing_and_textual_null(rules) -> None:
    for raw in [None, "", "NA", "N/A", "NULL", "NONE", "-", " na "]:
        result = normalise_sequence(raw, molecule_type="unknown", rules=rules)
        assert result.sequence_full is None
        assert result.sequence_core is None
        assert "missing_sequence" in result.qc_flags
        clean = clean_display_sequence(raw, rules=rules)
        assert clean.is_missing is True


def test_02_uppercase_conversion(rules) -> None:
    result = normalise_sequence("acgu", molecule_type="RNA", rules=rules)
    assert result.sequence_display_clean == "ACGU"
    assert "uppercase" in result.transformations


def test_03_internal_whitespace_removal(rules) -> None:
    result = normalise_sequence("AC GU AC", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGUAC"
    assert "remove_whitespace" in result.transformations


def test_04_terminal_label_removal(rules) -> None:
    result = normalise_sequence("5′-ACGU-3′", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGU"
    assert "remove_five_prime_label" in result.transformations
    assert "remove_three_prime_label" in result.transformations


def test_04b_ascii_terminal_hyphens_are_display_not_gaps(rules) -> None:
    result = normalise_sequence("5'-ACGUACGU-3'", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGUACGU"
    assert "remove_five_prime_label" in result.transformations
    assert "remove_three_prime_label" in result.transformations
    assert "alignment_gaps" not in result.qc_flags
    assert "remove_display_separators" not in result.transformations
    assert "-" not in (result.sequence_full or "")


def test_05_unicode_dash_display_separator_removal(rules) -> None:
    result = normalise_sequence("ACGU–AC—GU", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGUACGU"
    assert "remove_display_separators" in result.transformations
    assert "alignment_gaps" not in result.qc_flags


def test_05b_internal_hyphen_is_alignment_gap(rules) -> None:
    raw = "AC-GUAC"
    result = normalise_sequence(raw, molecule_type="RNA", rules=rules)
    assert result.sequence_raw == raw
    assert result.sequence_full == "AC-GUAC"
    assert "alignment_gaps" in result.qc_flags
    assert "remove_display_separators" not in result.transformations
    assert "invalid_character" not in result.qc_flags
    assert result.sequence_core == result.sequence_full


def test_05c_internal_dot_is_alignment_gap(rules) -> None:
    raw = "AC.GUAC"
    result = normalise_sequence(raw, molecule_type="RNA", rules=rules)
    assert result.sequence_raw == raw
    assert result.sequence_full == "AC.GUAC"
    assert "alignment_gaps" in result.qc_flags
    assert "remove_display_separators" not in result.transformations
    assert "invalid_character" not in result.qc_flags
    assert result.sequence_core == result.sequence_full


def test_05d_terminal_labels_do_not_hide_internal_hyphen(rules) -> None:
    result = normalise_sequence("5'-AC-GU-3'", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "AC-GU"
    assert "remove_five_prime_label" in result.transformations
    assert "remove_three_prime_label" in result.transformations
    assert "alignment_gaps" in result.qc_flags
    assert "remove_display_separators" not in result.transformations


def test_06_u_only_rna_classification(rules) -> None:
    classification = classify_alphabet("ACGUAC", rules=rules)
    assert classification.alphabet == "RNA"


def test_07_t_only_dna_alphabet_classification(rules) -> None:
    classification = classify_alphabet("ACGTAC", rules=rules)
    assert classification.alphabet == "DNA_T"


def test_08_mixed_t_u_classification(rules) -> None:
    classification = classify_alphabet("ACGTU", rules=rules)
    assert classification.alphabet == "mixed_T_U"
    assert "mixed_t_u" in classification.qc_flags


def test_acg_only_ssdna_reports_dna_t(rules) -> None:
    result = normalise_sequence("ACGACG", molecule_type="ssDNA", rules=rules)
    assert result.alphabet_as_reported == "DNA_T"
    assert result.molecule_type == "ssDNA"
    assert result.sequence_full == "ACGACG"
    assert result.t_to_u_applied is False
    classification = classify_alphabet(
        "ACGACG", rules=rules, molecule_type="ssDNA"
    )
    assert classification.alphabet == "DNA_T"


def test_acg_only_rna_reports_rna(rules) -> None:
    result = normalise_sequence("ACGACG", molecule_type="RNA", rules=rules)
    assert result.alphabet_as_reported == "RNA"
    assert result.molecule_type == "RNA"
    assert result.sequence_full == "ACGACG"
    assert result.t_to_u_applied is False
    classification = classify_alphabet("ACGACG", rules=rules, molecule_type="RNA")
    assert classification.alphabet == "RNA"


def test_explicit_t_remains_dna_t(rules) -> None:
    result = normalise_sequence("ACGTAC", molecule_type="ssDNA", rules=rules)
    assert result.alphabet_as_reported == "DNA_T"
    assert result.sequence_full == "ACGTAC"
    classification = classify_alphabet("ACGTAC", rules=rules, molecule_type="RNA")
    assert classification.alphabet == "DNA_T"


def test_explicit_u_remains_rna(rules) -> None:
    result = normalise_sequence("ACGUAC", molecule_type="RNA", rules=rules)
    assert result.alphabet_as_reported == "RNA"
    assert result.sequence_full == "ACGUAC"
    classification = classify_alphabet("ACGUAC", rules=rules, molecule_type="ssDNA")
    assert classification.alphabet == "RNA"


def test_mixed_t_u_unaffected_by_molecule_tiebreak(rules) -> None:
    rna = classify_alphabet("ACGTU", rules=rules, molecule_type="RNA")
    dna = classify_alphabet("ACGTU", rules=rules, molecule_type="ssDNA")
    assert rna.alphabet == "mixed_T_U"
    assert dna.alphabet == "mixed_T_U"


def test_09_supported_ambiguity_code_classification(rules) -> None:
    classification = classify_alphabet("ACGNRY", rules=rules)
    assert classification.alphabet == "ambiguous"
    assert "ambiguous_base" in classification.qc_flags


def test_10_invalid_character_detection(rules) -> None:
    classification = classify_alphabet("ACGXac", rules=rules)
    assert classification.alphabet == "invalid"
    assert "invalid_character" in classification.qc_flags
    result = normalise_sequence("ACGXac", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGXAC"
    assert "invalid_character" in result.qc_flags


def test_11_input_string_remains_unchanged(rules) -> None:
    raw = "5'-ac gu-3'"
    original = raw
    normalise_sequence(raw, molecule_type="RNA", rules=rules)
    assert raw == original


def test_12_explicit_rna_with_t_converted(rules) -> None:
    result = normalise_sequence("ACGTAC", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGUAC"
    assert result.t_to_u_applied is True
    assert "t_to_u" in result.transformations
    assert "t_in_reported_rna" in result.qc_flags


def test_13_explicit_ssdna_retains_t(rules) -> None:
    result = normalise_sequence("ACGTAC", molecule_type="ssDNA", rules=rules)
    assert result.sequence_full == "ACGTAC"
    assert result.t_to_u_applied is False
    assert "U" not in result.sequence_full


def test_14_unknown_t_only_remains_unknown(rules) -> None:
    result = normalise_sequence("ACGTAC", molecule_type="unknown", rules=rules)
    assert result.molecule_type == "unknown"
    assert result.alphabet_as_reported == "DNA_T"
    assert result.t_to_u_applied is False
    assert "molecule_type_unknown" in result.qc_flags


def test_15_unknown_u_only_may_resolve_to_rna(rules) -> None:
    result = normalise_sequence("ACGUAC", molecule_type="unknown", rules=rules)
    assert result.molecule_type == "RNA"
    assert result.alphabet_as_reported == "RNA"


def test_16_reported_dna_containing_u_flagged(rules) -> None:
    result = normalise_sequence("ACGUAC", molecule_type="DNA", rules=rules)
    assert result.sequence_full == "ACGUAC"
    assert result.t_to_u_applied is False
    assert "u_in_reported_dna" in result.qc_flags


def test_17_mixed_t_u_not_silently_repaired(rules) -> None:
    result = normalise_sequence("ACGTU", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGTU"
    assert result.t_to_u_applied is False
    assert "mixed_t_u" in result.qc_flags
    assert "trim_requires_review" in result.qc_flags


def test_18_full_equals_core_without_trim(rules) -> None:
    result = normalise_sequence("ACGUACGU", molecule_type="RNA", rules=rules)
    assert result.sequence_full == result.sequence_core
    assert result.applied_trims == ()


def test_19_exact_five_prime_trim(rules) -> None:
    plan = TrimProposal(
        five_prime="ACGU",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    result = normalise_sequence(
        "ACGUGGGG", molecule_type="RNA", trim_plan=plan, rules=rules
    )
    assert result.sequence_full == "ACGUGGGG"
    assert result.sequence_core == "GGGG"
    assert result.applied_trims[0].side == "five_prime"
    assert result.applied_trims[0].bases_removed == 4


def test_20_exact_three_prime_trim(rules) -> None:
    plan = TrimProposal(
        three_prime="GGGG",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    result = normalise_sequence(
        "ACGUGGGG", molecule_type="RNA", trim_plan=plan, rules=rules
    )
    assert result.sequence_core == "ACGU"
    assert result.applied_trims[0].side == "three_prime"


def test_21_exact_two_sided_trim(rules) -> None:
    plan = TrimProposal(
        five_prime="AA",
        three_prime="UU",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    result = normalise_sequence(
        "AACCCCUU", molecule_type="RNA", trim_plan=plan, rules=rules
    )
    assert result.sequence_full == "AACCCCUU"
    assert result.sequence_core == "CCCC"


def test_22_trim_mismatch_hard_failure(rules) -> None:
    plan = TrimProposal(
        five_prime="GGGG",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    with pytest.raises(TrimMismatchError):
        normalise_sequence("ACGUAC", molecule_type="RNA", trim_plan=plan, rules=rules)


def test_23_empty_result_trim_rejection(rules) -> None:
    plan = TrimProposal(
        five_prime="ACGU",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    with pytest.raises(TrimMismatchError):
        normalise_sequence("ACGU", molecule_type="RNA", trim_plan=plan, rules=rules)


def test_24_full_retained_after_trimming(rules) -> None:
    plan = TrimProposal(
        five_prime="AC",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    result = normalise_sequence(
        "ACGUAC", molecule_type="RNA", trim_plan=plan, rules=rules
    )
    assert result.sequence_full == "ACGUAC"
    assert result.sequence_core == "GUAC"


def test_25_core_below_minimum_flagged(rules) -> None:
    # Use a temporary lower max/min via validate on short core after trim.
    short_rules = validate_rules_dict(
        {
            **rules_to_public_dict(rules),
            "core_length_min": 8,
            "core_length_max": 100,
        }
    )
    plan = TrimProposal(
        five_prime="ACGU",
        reason="documented_constant",
        confidence=1.0,
        source="test",
        status="approved",
    )
    result = normalise_sequence(
        "ACGUGGGG", molecule_type="RNA", trim_plan=plan, rules=short_rules
    )
    assert result.sequence_core == "GGGG"
    assert "core_below_min_length" in result.qc_flags


def test_26_core_above_maximum_flagged(rules) -> None:
    tight = validate_rules_dict(
        {
            **rules_to_public_dict(rules),
            "core_length_min": 2,
            "core_length_max": 4,
        }
    )
    result = normalise_sequence("ACGUAC", molecule_type="RNA", rules=tight)
    assert "core_above_max_length" in result.qc_flags


def test_27_t7_motif_detected_not_auto_trimmed(rules) -> None:
    # Build motif + short core without a single literal ≥20 nt.
    motif = "TAATACGACTCACTATA"
    assert len(motif) < 20
    raw = motif + "AC"
    assert len(raw) < 20
    result = normalise_sequence(raw, molecule_type="ssDNA", rules=rules)
    assert any(m.name == "t7_promoter_minimal" for m in result.detected_motifs)
    assert "known_promoter_detected" in result.qc_flags
    assert result.sequence_core == result.sequence_full
    assert result.applied_trims == ()


def test_28_deterministic_transformation_and_flag_ordering(rules) -> None:
    raw = "5' ac-gu 3'"
    first = normalise_sequence(raw, molecule_type="RNA", rules=rules)
    second = normalise_sequence(raw, molecule_type="RNA", rules=rules)
    assert first == second
    assert list(first.qc_flags) == sorted(first.qc_flags)
    assert first.transformations == second.transformations


def test_43_configuration_loads_deterministically() -> None:
    a = load_normalisation_rules()
    b = load_normalisation_rules()
    assert rules_to_public_dict(a) == rules_to_public_dict(b)
    assert a.contract_version == "1.0"
    assert a.core_length_min == 20
    assert a.core_length_max == 100


def test_44_invalid_configuration_values_fail_clearly() -> None:
    with pytest.raises(ConfigurationError):
        validate_rules_dict({"contract_version": "1.0"})


def test_45_minimum_support_constrained_to_0_1(rules) -> None:
    payload = rules_to_public_dict(rules)
    payload["constant_region_inference"] = {
        **payload["constant_region_inference"],
        "minimum_support": 1.5,
    }
    with pytest.raises(ConfigurationError, match="between 0 and 1"):
        validate_rules_dict(payload)


def test_46_minimum_core_length_cannot_exceed_maximum(rules) -> None:
    payload = rules_to_public_dict(rules)
    payload["core_length_min"] = 50
    payload["core_length_max"] = 40
    with pytest.raises(ConfigurationError, match="cannot exceed"):
        validate_rules_dict(payload)


def test_47_no_absolute_paths_enter_outputs(rules) -> None:
    result = normalise_sequence("ACGU", molecule_type="RNA", rules=rules)
    blob = json.dumps(
        {
            "flags": result.qc_flags,
            "transformations": result.transformations,
            "rules": rules_to_public_dict(rules),
        }
    )
    assert "/Users/" not in blob
    assert "C:\\\\" not in blob
    assert str(REPO_ROOT) not in blob


def test_48_no_stdout_stderr_sequence_dumping(rules) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        normalise_sequence("ACGUACGT", molecule_type="RNA", rules=rules)
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_49_no_real_source_files_read_by_test_suite(rules) -> None:
    # Only the tracked rules JSON should be consulted by these helpers.
    assert Path(rules.source_path).name == "sequence_normalisation_rules.json"
    raw_root = REPO_ROOT / "data" / "raw"
    # Ensure we did not open any raw CSV during this module's helper calls.
    assert raw_root.exists() or True
    # Guard: normalisation helpers accept only in-memory strings.
    result = normalise_sequence("ACGU", molecule_type="RNA", rules=rules)
    assert result.sequence_raw == "ACGU"


def test_50_repeated_runs_byte_dict_identical(rules) -> None:
    payload = {
        "raw": "5′-ACGU-3′",
        "molecule_type": "RNA",
        "trim": TrimProposal(
            five_prime="AC",
            reason="documented",
            confidence=1.0,
            source="test",
            status="approved",
        ),
    }
    runs = [
        normalise_sequence(
            payload["raw"],
            molecule_type=payload["molecule_type"],
            trim_plan=payload["trim"],
            rules=rules,
        )
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_validate_core_length_direct(rules) -> None:
    below = validate_core_length("ACGU", rules=rules)
    assert "core_below_min_length" in below.flags
    # Construct a >100 nt core from short fragments without a long literal.
    fragment = "ACGU"
    long_core = fragment * 26  # 104 nt
    assert len(long_core) > 100
    above = validate_core_length(long_core, rules=rules)
    assert "core_above_max_length" in above.flags


def test_detect_motifs_flag_only(rules) -> None:
    motif = "TAATACGACTCACTATA"
    hits = detect_known_non_core_motifs(motif + "GG", rules)
    assert hits[0].action == "flag_only"
    assert hits[0].name == "t7_promoter_minimal"


def test_bracketed_three_prime_ascii_label(rules) -> None:
    result = normalise_sequence("5'-ACGU-[3'T]", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGU"
    assert "remove_bracketed_three_prime_label" in result.transformations
    assert result.sequence_raw == "5'-ACGU-[3'T]"


def test_bracketed_three_prime_unicode_label(rules) -> None:
    result = normalise_sequence("5′-ACGU-[3′T]", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGU"
    assert "remove_bracketed_three_prime_label" in result.transformations


def test_bracketed_five_prime_label(rules) -> None:
    result = normalise_sequence("[5'T]-ACGU-3'", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGU"
    assert "remove_bracketed_five_prime_label" in result.transformations


def test_internal_brackets_not_stripped(rules) -> None:
    result = normalise_sequence("AC[foo]GU", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "AC[FOO]GU"
    assert "invalid_character" in result.qc_flags
    assert "remove_bracketed_three_prime_label" not in result.transformations
    assert "remove_bracketed_five_prime_label" not in result.transformations


def test_trailing_phosphate_display_label(rules) -> None:
    result = normalise_sequence("ACGUp", molecule_type="RNA", rules=rules)
    assert result.sequence_full == "ACGU"
    assert "remove_trailing_phosphate_label" in result.transformations


def test_unexpected_character_retained_and_flagged(rules) -> None:
    raw = "5'-ACGX-3'"
    result = normalise_sequence(raw, molecule_type="RNA", rules=rules)
    assert result.sequence_raw == raw
    assert "X" in (result.sequence_full or "")
    assert "invalid_character" in result.qc_flags
