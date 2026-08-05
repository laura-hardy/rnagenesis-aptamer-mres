"""Tests for the AptaBase S2 molecule-evidence adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt.
Does not import the legacy AptaBase cleaner or read real source data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s2 import (  # noqa: E402
    AptabaseNormalisationPolicy,
    AptaBaseS2Stats,
    clean_aptabase_terminal_label_artifacts,
    compare_gc_content,
    compare_legacy_diagnostics,
    compare_legacy_molecule_type,
    compare_reported_length,
    load_aptabase_policy,
    normalise_aptabase_record,
    parse_reported_length,
    resolve_aptabase_molecule_type,
    update_stats_from_row,
)
from common.corpus_schema import (  # noqa: E402
    empty_corpus_record,
    validate_s2_record,
)
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402


def _meta(**overrides: str) -> dict[str, str]:
    row = {
        "record_id": "aptabase:1",
        "aptabase_aptamer_name": "",
        "aptabase_reference": "",
        "aptabase_target_general": "",
        "aptabase_target_specific": "",
        "aptabase_reported_length": "",
        "aptabase_gc_content_reported": "",
        "aptabase_gc_content_calculated": "",
        "aptabase_sequence_clean": "",
        "aptabase_sequence_length_calculated": "",
        "aptabase_sequence_alphabet": "",
        "aptabase_molecule_type_inferred": "",
        "aptabase_sequence_normalization_status": "",
    }
    row.update(overrides)
    return row


def _s1(**overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "aptabase:1",
            "sequence_raw": "ACGUAC",
            "source_db": "aptabase",
            "source_dataset": "demo_ds",
            "contributing_sources": "aptabase",
            "contributing_datasets": "demo_ds",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": "1",
            "target_name_raw": "demo_target",
            "publication": "Demo",
            "doi": "",
            "pubmed_id": "",
            "notes": json.dumps({"aptamer_name": "demo"}, separators=(",", ":")),
        }
    )
    record.update(overrides)
    return record


@pytest.fixture(scope="module")
def policy() -> AptabaseNormalisationPolicy:
    return load_aptabase_policy(
        REPO_ROOT / "config" / "source_normalisation" / "aptabase.json"
    )


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


# --- Molecule-evidence policy ---


def test_01_aptamer_name_rna_evidence(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(aptabase_aptamer_name="Example RNA aptamer X"),
        "DNA_T",
        policy,
        has_t=True,
    )
    assert result.molecule_type == "RNA"
    assert result.evidence_source == "aptamer_name"
    assert result.evidence_category == "explicit_text"


def test_02_aptamer_name_dna_evidence(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(aptabase_aptamer_name="ssDNA binder"),
        "RNA",
        policy,
        has_u=True,
    )
    assert result.molecule_type == "ssDNA"
    assert result.evidence_source == "aptamer_name"


def test_03_name_precedence_over_reference(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(
            aptabase_aptamer_name="DNA aptamer clone",
            aptabase_reference="Paper on RNA oligonucleotide selection",
        ),
        "missing",
        policy,
    )
    assert result.molecule_type == "ssDNA"
    assert result.evidence_source == "aptamer_name"


def test_04_reference_rna_when_name_empty(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(aptabase_reference="An RNA aptamer study"),
        "DNA_T",
        policy,
        has_t=True,
    )
    assert result.molecule_type == "RNA"
    assert result.evidence_source == "reference"


def test_05_reference_dna_when_name_empty(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(aptabase_reference="ssDNA selection paper"),
        "RNA",
        policy,
        has_u=True,
    )
    assert result.molecule_type == "ssDNA"
    assert result.evidence_source == "reference"


def test_06_conflicting_rna_dna_yields_unknown(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(aptabase_aptamer_name="RNA aptamer and DNA aptamer hybrid"),
        "RNA",
        policy,
        has_u=True,
    )
    assert result.molecule_type == "unknown"
    assert result.conflict is True
    assert "conflicting_molecule_evidence" in result.qc_flags


def test_07_target_fields_never_molecule_evidence(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(
            aptabase_target_general="RNA polymerase",
            aptabase_target_specific="DNA ligase",
        ),
        "DNA_T",
        policy,
        has_t=True,
    )
    assert result.molecule_type == "unknown"
    assert result.evidence_source == "sequence_alphabet"
    assert result.evidence_category == "alphabet"


def test_08_legacy_inferred_never_authoritative(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(aptabase_molecule_type_inferred="RNA"),
        "DNA_T",
        policy,
        has_t=True,
    )
    assert result.molecule_type == "unknown"
    assert result.evidence_category == "alphabet"


def test_09_u_only_alphabet_fallback_rna(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(),
        "RNA",
        policy,
        has_u=True,
        has_t=False,
    )
    assert result.molecule_type == "RNA"
    assert result.evidence_source == "sequence_alphabet"


def test_10_t_only_alphabet_fallback_unknown(policy) -> None:
    result = resolve_aptabase_molecule_type(
        _meta(),
        "DNA_T",
        policy,
        has_t=True,
        has_u=False,
    )
    assert result.molecule_type == "unknown"
    assert "molecule_type_unknown" in result.qc_flags


def test_11_invalid_missing_alphabet_unknown(policy) -> None:
    for alphabet in ("missing", "invalid", "ambiguous", "mixed_T_U"):
        result = resolve_aptabase_molecule_type(_meta(), alphabet, policy)
        assert result.molecule_type == "unknown"
        assert result.evidence_category == "none"


# --- S2 sequence behaviour ---


def test_12_sequence_raw_unchanged(policy, rules) -> None:
    s1 = _s1(sequence_raw="5′-ac gu-3′")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_raw"] == "5′-ac gu-3′"


def test_13_display_labels_removed_from_full_core(policy, rules) -> None:
    s1 = _s1(sequence_raw="5′-ACGU-3′")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGU"
    assert result.canonical["sequence_core"] == "ACGU"
    assert result.canonical["sequence_raw"] == "5′-ACGU-3′"


def test_14_whitespace_removed_from_full_core(policy, rules) -> None:
    s1 = _s1(sequence_raw="AC GU AC")
    meta = _meta(aptabase_aptamer_name="RNA aptamer demo")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["sequence_raw"] == "AC GU AC"


def test_15_explicit_rna_with_t_performs_t_to_u(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGTAC")
    meta = _meta(aptabase_aptamer_name="RNA aptamer demo")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["molecule_type"] == "RNA"


def test_16_explicit_ssdna_retains_t(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGTAC")
    meta = _meta(aptabase_aptamer_name="ssDNA clone")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGTAC"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["molecule_type"] == "ssDNA"


def test_17_mixed_t_u_unresolved(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGTU")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGTU"
    assert "mixed_t_u" in result.canonical["qc_flags"]


def test_18_invalid_characters_retained_and_flagged(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGXac")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert "X" in result.canonical["sequence_full"]
    assert "invalid_character" in result.canonical["qc_flags"]


def test_19_ambiguity_retained_and_flagged(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGNRY")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGNRY"
    assert "ambiguous_base" in result.canonical["qc_flags"]


def test_20_missing_row_remains(policy, rules) -> None:
    s1 = _s1(sequence_raw="")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == ""
    assert result.canonical["construct_scope"] == "missing"
    assert result.canonical["trim_status"] == "not_applicable"
    assert "missing_sequence" in result.canonical["qc_flags"]
    assert result.canonical["record_id"] == "aptabase:1"


def test_21_full_equals_core_without_trim(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGUACGU")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == result.canonical["sequence_core"]
    assert result.canonical["construct_scope"] == "full_equals_core_untrimmed"
    assert result.canonical["trim_status"] == "not_trimmed"


def test_22_known_promoter_detected_not_trimmed(policy, rules) -> None:
    motif = "TAATACGACTCACTATA"
    assert len(motif) < 20
    s1 = _s1(sequence_raw=motif + "AC")
    meta = _meta(aptabase_aptamer_name="ssDNA clone")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == result.canonical["sequence_core"]
    assert "t7_promoter_minimal" in result.canonical["detected_constant_5p"]
    assert "known_promoter_detected" in result.canonical["qc_flags"]


def test_23_review_required_trim_status(policy, rules) -> None:
    motif = "TAATACGACTCACTATA"
    s1 = _s1(sequence_raw=motif + "AC")
    meta = _meta(aptabase_aptamer_name="ssDNA clone")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.canonical["trim_status"] == "review_required"
    assert "trim_requires_review" in result.canonical["qc_flags"]


def test_24_below_minimum_core_flagged(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGU")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert "core_below_min_length" in result.canonical["qc_flags"]


def test_25_above_maximum_core_flagged(policy, rules) -> None:
    fragment = "ACGU"
    long_seq = fragment * 26  # 104 nt, no ≥20 literal
    assert len(long_seq) > 100
    s1 = _s1(sequence_raw=long_seq)
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert "core_above_max_length" in result.canonical["qc_flags"]


def test_26_no_target_evidence_field_populated(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGUAC")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    for field in (
        "chemistry",
        "target_name",
        "target_uniprot",
        "target_type",
        "affinity_value",
        "experiment_group_id",
        "cluster_id",
        "partition",
    ):
        assert result.canonical[field] == ""


# --- Length and GC diagnostics ---


def test_27_integer_reported_length_parsed(policy) -> None:
    parsed, flags = parse_reported_length(
        "90", tolerance=policy.reported_length_integer_tolerance
    )
    assert parsed == 90
    assert flags == ()


def test_28_integer_valued_decimal_parsed(policy) -> None:
    parsed, flags = parse_reported_length(
        "90.0", tolerance=policy.reported_length_integer_tolerance
    )
    assert parsed == 90
    assert flags == ()


def test_29_free_text_reported_length_unparsed(policy) -> None:
    parsed, flags = parse_reported_length(
        "about 90 nt", tolerance=policy.reported_length_integer_tolerance
    )
    assert parsed is None
    assert "reported_length_unparseable" in flags


def test_30_length_mismatch_flagged(policy) -> None:
    diag = compare_reported_length(
        "10",
        8,
        tolerance=policy.reported_length_integer_tolerance,
    )
    assert diag.reported_length_parsed == "10"
    assert diag.reported_length_difference == "-2"
    assert "reported_length_mismatch" in diag.qc_flags


def test_31_canonical_dna_gc_calculation() -> None:
    # GCGT = 75%
    value = compare_gc_content("75", "GCGT", "DNA_T", threshold_pp=1.0)
    assert value.gc_calculated_s2 == "75"
    assert value.gc_difference_percentage_points == "0"


def test_32_canonical_rna_gc_calculation() -> None:
    # GCGU = 75%
    value = compare_gc_content("75", "GCGU", "RNA", threshold_pp=1.0)
    assert value.gc_calculated_s2 == "75"


def test_33_mixed_ambiguous_invalid_gc_empty() -> None:
    assert compare_gc_content("50", "ACGTU", "mixed_T_U", threshold_pp=1.0).gc_calculated_s2 == ""
    assert compare_gc_content("50", "ACGN", "ambiguous", threshold_pp=1.0).gc_calculated_s2 == ""
    assert compare_gc_content("50", "ACGX", "invalid", threshold_pp=1.0).gc_calculated_s2 == ""


def test_34_reported_gc_mismatch_threshold() -> None:
    diag = compare_gc_content("50", "GCGC", "DNA_T", threshold_pp=1.0)
    # GCGC = 100%; diff 50 pp
    assert "reported_gc_mismatch" in diag.qc_flags


def test_35_old_calculated_gc_does_not_drive_result(policy, rules) -> None:
    s1 = _s1(sequence_raw="GCGC")
    meta = _meta(
        aptabase_aptamer_name="ssDNA clone",
        aptabase_gc_content_reported="100",
        aptabase_gc_content_calculated="12.3",
    )
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.qc["gc_calculated_s2"] == "100"
    assert "legacy_gc_disagreement" in result.canonical["qc_flags"]


# --- Legacy comparisons ---


def test_36_legacy_sequence_clean_disagreement() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="ACGUAC",
        sequence_length_full=6,
        alphabet_as_reported="RNA",
        molecule_type="RNA",
        molecule_evidence_source="sequence_alphabet",
        gc_calculated_s2="",
        source_metadata=_meta(aptabase_sequence_clean="AAAAAA"),
    )
    assert "legacy_sequence_clean_disagreement" in legacy.qc_flags


def test_37_legacy_length_disagreement() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="ACGUAC",
        sequence_length_full=6,
        alphabet_as_reported="RNA",
        molecule_type="RNA",
        molecule_evidence_source="sequence_alphabet",
        gc_calculated_s2="",
        source_metadata=_meta(aptabase_sequence_length_calculated="9"),
    )
    assert "legacy_length_disagreement" in legacy.qc_flags


def test_38_legacy_alphabet_disagreement() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="ACGUAC",
        sequence_length_full=6,
        alphabet_as_reported="RNA",
        molecule_type="RNA",
        molecule_evidence_source="sequence_alphabet",
        gc_calculated_s2="",
        source_metadata=_meta(aptabase_sequence_alphabet="DNA_T"),
    )
    assert "legacy_alphabet_disagreement" in legacy.qc_flags


def test_39_legacy_molecule_disagreement() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="ACGUAC",
        sequence_length_full=6,
        alphabet_as_reported="RNA",
        molecule_type="RNA",
        molecule_evidence_source="sequence_alphabet",
        gc_calculated_s2="",
        source_metadata=_meta(aptabase_molecule_type_inferred="DNA_like_sequence"),
    )
    assert "legacy_molecule_type_disagreement" in legacy.qc_flags
    assert legacy.molecule_comparison_status == "disagreement"


def test_40_legacy_gc_disagreement() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="GCGC",
        sequence_length_full=4,
        alphabet_as_reported="DNA_T",
        molecule_type="ssDNA",
        molecule_evidence_source="reference",
        gc_calculated_s2="100",
        source_metadata=_meta(aptabase_gc_content_calculated="50"),
    )
    assert "legacy_gc_disagreement" in legacy.qc_flags


def test_41_agreement_produces_no_legacy_flag() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="ACGUAC",
        sequence_length_full=6,
        alphabet_as_reported="RNA",
        molecule_type="RNA",
        molecule_evidence_source="sequence_alphabet",
        gc_calculated_s2="33.3333333333",
        source_metadata=_meta(
            aptabase_sequence_clean="ACGUAC",
            aptabase_sequence_length_calculated="6",
            aptabase_sequence_alphabet="RNA",
            aptabase_molecule_type_inferred="RNA_like_sequence",
            aptabase_gc_content_calculated="33.3333333333",
        ),
    )
    assert "legacy_molecule_type_disagreement" not in legacy.qc_flags
    assert legacy.molecule_comparison_status == "agreement"
    assert legacy.qc_flags == ()


def test_validate_s2_rejects_provenance_change(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGU")
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    broken = dict(result.canonical)
    broken["native_id"] = "changed"
    with pytest.raises(Exception, match="provenance"):
        validate_s2_record(broken, s1_record=s1)


def test_no_legacy_cleaner_imported() -> None:
    assert "aptabase_cleaning" not in sys.modules


# --- AptaBase corrupted terminal-label preprocessing ---


def test_terminal_01_corrupted_leading_5p_fffd(policy, rules) -> None:
    raw = "5\ufffdACGUAC"
    s1 = _s1(sequence_raw=raw)
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "remove_aptabase_corrupted_5p_label" in result.transformations
    assert "invalid_character" not in result.canonical["qc_flags"]


def test_terminal_02_corrupted_trailing_3p_fffd(policy, rules) -> None:
    raw = "ACGUAC3\ufffd"
    s1 = _s1(sequence_raw=raw)
    result = normalise_aptabase_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "remove_aptabase_corrupted_3p_label" in result.transformations
    assert "invalid_character" not in result.canonical["qc_flags"]


def test_terminal_03_corrupted_leading_5p_question(policy, rules) -> None:
    raw = "5?ACGUAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "remove_aptabase_corrupted_5p_label" in result.transformations


def test_terminal_04_corrupted_trailing_3p_question(policy, rules) -> None:
    raw = "ACGUAC3?"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert "remove_aptabase_corrupted_3p_label" in result.transformations


def test_terminal_05_both_corrupted_terminals(policy, rules) -> None:
    raw = "5\ufffdACGU3?"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"] == "ACGU"
    assert "remove_aptabase_corrupted_5p_label" in result.transformations
    assert "remove_aptabase_corrupted_3p_label" in result.transformations


def test_terminal_06_optional_hyphen_after_leading(policy, rules) -> None:
    raw = "5\ufffd-ACGUAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_terminal_07_optional_hyphen_before_trailing(policy, rules) -> None:
    raw = "ACGUAC-3?"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_terminal_08_unicode_and_ascii_whitespace(policy, rules) -> None:
    raw = " 5\ufffd\u00a0ACGU\t3? "
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"] == "ACGU"


def test_terminal_09_internal_digit_5_retained(policy, rules) -> None:
    raw = "ACG5UAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert "5" in result.canonical["sequence_full"]
    assert "invalid_character" in result.canonical["qc_flags"]
    assert "remove_aptabase_corrupted_5p_label" not in result.transformations


def test_terminal_10_internal_digit_3_retained(policy, rules) -> None:
    raw = "ACG3UAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert "3" in result.canonical["sequence_full"]
    assert "invalid_character" in result.canonical["qc_flags"]
    assert "remove_aptabase_corrupted_3p_label" not in result.transformations


def test_terminal_11_internal_question_retained(policy, rules) -> None:
    raw = "ACG?UAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert "?" in result.canonical["sequence_full"]
    assert "invalid_character" in result.canonical["qc_flags"]


def test_terminal_12_internal_fffd_retained(policy, rules) -> None:
    raw = "ACG\ufffdUAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert "\ufffd" in result.canonical["sequence_full"]
    assert "invalid_character" in result.canonical["qc_flags"]


def test_terminal_13_chemical_modification_not_removed(policy, rules) -> None:
    raw = "2'-O-Me-ACGU"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert "2" in result.canonical["sequence_full"]
    assert "O" in result.canonical["sequence_full"]
    assert "remove_aptabase_corrupted_5p_label" not in result.transformations
    assert "remove_aptabase_corrupted_3p_label" not in result.transformations
    assert "invalid_character" in result.canonical["qc_flags"]


def test_terminal_14_nucleotide_then_malformed_not_overcleaned(policy, rules) -> None:
    raw = "A5?CGU"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"].startswith("A")
    assert "5" in result.canonical["sequence_full"]
    assert "?" in result.canonical["sequence_full"]
    assert "remove_aptabase_corrupted_5p_label" not in result.transformations


def test_terminal_15_sequence_raw_unchanged(policy, rules) -> None:
    raw = "5\ufffdACGU3?"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_raw"] == raw


def test_terminal_16_transformations_deterministic() -> None:
    raw = "5?ACGU-3\ufffd"
    first = clean_aptabase_terminal_label_artifacts(raw)
    second = clean_aptabase_terminal_label_artifacts(raw)
    assert first == second
    assert first.transformations == (
        "remove_aptabase_corrupted_5p_label",
        "remove_aptabase_corrupted_3p_label",
    )


def test_terminal_17_no_removed_fragment_printed() -> None:
    raw = "5\ufffdACGU3?"
    cleaned = clean_aptabase_terminal_label_artifacts(raw)
    assert "5\ufffd" not in cleaned.transformations
    assert "3?" not in cleaned.transformations
    rendered = repr(cleaned)
    # Transformation codes only; the helper result must not echo the fragment
    # as a dedicated removed-text field.
    assert not hasattr(cleaned, "removed_text")
    assert "value_for_shared_normaliser" in rendered


def test_terminal_18_repeated_execution_identical(policy, rules) -> None:
    raw = "5\ufffd-ACGU-3?"
    s1 = _s1(sequence_raw=raw)
    meta = _meta()
    first = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    second = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert first.canonical == second.canonical
    assert first.qc == second.qc
    assert first.transformations == second.transformations


def test_terminal_standalone_digit_not_stripped(policy, rules) -> None:
    raw = "5ACGUAC"
    result = normalise_aptabase_record(
        _s1(sequence_raw=raw), _meta(), policy=policy, rules=rules
    )
    assert result.canonical["sequence_full"].startswith("5")
    assert "remove_aptabase_corrupted_5p_label" not in result.transformations


# --- Semantic legacy molecule comparison ---


def test_semantic_01_rna_like_versus_rna_agrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="RNA",
        legacy_molecule_type="RNA_like",
        new_alphabet="RNA",
        molecule_evidence_source="sequence_alphabet",
    )
    assert cmp.status == "agreement"
    assert cmp.disagreement is False


def test_semantic_02_rna_like_sequence_versus_rna_agrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="RNA",
        legacy_molecule_type="RNA_like_sequence",
        new_alphabet="RNA",
        molecule_evidence_source="sequence_alphabet",
    )
    assert cmp.status == "agreement"
    assert cmp.disagreement is False


def test_semantic_03_dna_like_versus_ssdna_agrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="ssDNA",
        legacy_molecule_type="DNA_like",
        new_alphabet="DNA_T",
        molecule_evidence_source="reference",
    )
    assert cmp.status == "agreement"
    assert cmp.disagreement is False


def test_semantic_04_dna_like_versus_dna_agrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="DNA",
        legacy_molecule_type="DNA_like_sequence",
        new_alphabet="DNA_T",
        molecule_evidence_source="reference",
    )
    assert cmp.status == "agreement"
    assert cmp.disagreement is False


def test_semantic_05_missing_versus_unknown_compatible() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="unknown",
        legacy_molecule_type="missing",
        new_alphabet="missing",
        molecule_evidence_source="",
    )
    assert cmp.status == "compatible_difference"
    assert cmp.disagreement is False


def test_semantic_06_invalid_versus_unknown_compatible() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="unknown",
        legacy_molecule_type="invalid",
        new_alphabet="invalid",
        molecule_evidence_source="",
    )
    assert cmp.status == "compatible_difference"
    assert cmp.disagreement is False


def test_semantic_07_mixed_versus_unknown_compatible() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="unknown",
        legacy_molecule_type="mixed_or_uncertain",
        new_alphabet="mixed_T_U",
        molecule_evidence_source="",
    )
    assert cmp.status == "compatible_difference"
    assert cmp.disagreement is False


def test_semantic_08_dna_like_versus_t_only_unknown_unresolved() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="unknown",
        legacy_molecule_type="DNA_like_sequence",
        new_alphabet="DNA_T",
        molecule_evidence_source="sequence_alphabet",
    )
    assert cmp.status == "unresolved"
    assert cmp.disagreement is False
    assert cmp.reason == "dna_like_versus_conservative_t_only_unknown"


def test_semantic_09_dna_template_versus_rna_agrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="RNA",
        legacy_molecule_type="possible_DNA_template_for_RNA",
        new_alphabet="invalid",
        molecule_evidence_source="reference",
    )
    assert cmp.status == "agreement"
    assert cmp.disagreement is False


def test_semantic_10_dna_template_versus_unknown_unresolved() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="unknown",
        legacy_molecule_type="possible_DNA_template_for_RNA",
        new_alphabet="DNA_T",
        molecule_evidence_source="sequence_alphabet",
    )
    assert cmp.status == "unresolved"
    assert cmp.disagreement is False


def test_semantic_11_legacy_rna_versus_ssdna_disagrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="ssDNA",
        legacy_molecule_type="RNA_like_sequence",
        new_alphabet="DNA_T",
        molecule_evidence_source="reference",
    )
    assert cmp.status == "disagreement"
    assert cmp.disagreement is True


def test_semantic_12_legacy_dna_versus_rna_disagrees() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="RNA",
        legacy_molecule_type="DNA_like_sequence",
        new_alphabet="RNA",
        molecule_evidence_source="reference",
    )
    assert cmp.status == "disagreement"
    assert cmp.disagreement is True


def test_semantic_13_unrecognised_legacy_reported() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="RNA",
        legacy_molecule_type="weird_legacy_label",
        new_alphabet="RNA",
        molecule_evidence_source="sequence_alphabet",
    )
    assert cmp.status == "unrecognised"
    assert cmp.legacy_semantic_category == "unrecognised"
    assert cmp.disagreement is False


def test_semantic_14_empty_legacy_handled() -> None:
    cmp = compare_legacy_molecule_type(
        new_molecule_type="RNA",
        legacy_molecule_type="",
        new_alphabet="RNA",
        molecule_evidence_source="sequence_alphabet",
    )
    assert cmp.status == "empty_legacy"
    assert cmp.disagreement is False


def test_semantic_empty_legacy_is_counted_in_stats(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGUAC")
    meta = _meta(aptabase_molecule_type_inferred="")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.qc["legacy_molecule_comparison_status"] == "empty_legacy"
    stats = AptaBaseS2Stats()
    update_stats_from_row(stats, result)
    assert stats.legacy_molecule_type_empty_legacy_count == 1
    assert stats.legacy_molecule_type_agreement_count == 0
    assert stats.legacy_molecule_type_compatible_difference_count == 0
    assert stats.legacy_molecule_type_unresolved_comparison_count == 0
    assert stats.legacy_molecule_type_unrecognised_count == 0
    assert stats.legacy_molecule_type_disagreement_count == 0


def test_semantic_15_flagging_deterministic() -> None:
    kwargs = dict(
        new_molecule_type="unknown",
        legacy_molecule_type="DNA_like_sequence",
        new_alphabet="DNA_T",
        molecule_evidence_source="sequence_alphabet",
    )
    assert compare_legacy_molecule_type(**kwargs) == compare_legacy_molecule_type(
        **kwargs
    )


def test_semantic_16_literal_vocabulary_alone_not_disagreement() -> None:
    legacy = compare_legacy_diagnostics(
        sequence_full="ACGUAC",
        sequence_length_full=6,
        alphabet_as_reported="RNA",
        molecule_type="RNA",
        molecule_evidence_source="sequence_alphabet",
        gc_calculated_s2="",
        source_metadata=_meta(aptabase_molecule_type_inferred="RNA_like_sequence"),
    )
    assert legacy.molecule_comparison_status == "agreement"
    assert "legacy_molecule_type_disagreement" not in legacy.qc_flags
    assert "legacy_molecule_type_disagreement" not in legacy.legacy_disagreement_flags


def test_semantic_sidecar_fields_populated(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGUAC")
    meta = _meta(aptabase_molecule_type_inferred="RNA_like_sequence")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.qc["legacy_molecule_comparison_status"] == "agreement"
    assert result.qc["legacy_molecule_comparison_reason"] == "semantic_agreement"


def test_semantic_compatible_not_sole_review_reason(policy, rules) -> None:
    s1 = _s1(sequence_raw="")
    meta = _meta(aptabase_molecule_type_inferred="missing")
    result = normalise_aptabase_record(s1, meta, policy=policy, rules=rules)
    assert result.qc["legacy_molecule_comparison_status"] == "compatible_difference"
    assert "legacy_molecule_type_compatible_difference" in result.qc[
        "legacy_disagreement_flags"
    ]
    assert "legacy_molecule_type_compatible_difference" not in result.canonical[
        "qc_flags"
    ]
