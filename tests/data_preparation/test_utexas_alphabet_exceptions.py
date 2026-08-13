"""Synthetic tests for the UTexas RNA alphabet-exception classifier.

Every literal nucleotide string in this file is shorter than 20 nt.
Does not read real UTexas source sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.utexas_alphabet_exceptions import (  # noqa: E402
    CLASS_IUPAC,
    CLASS_MALFORMED,
    CLASS_NEEDS_REVIEW,
    CLASS_RECOVERABLE,
    CLASS_UNRESOLVED_MOD,
    REVIEW_COLUMNS,
    AlphabetExceptionError,
    attempt_recovery,
    build_exception_summary,
    build_review_row,
    classify_exception,
    diagnose_sequence,
    select_exception_cohort,
)


def test_recoverable_inverted_terminal_cap_keeps_explicit_base() -> None:
    raw = "5'ACGUACGU3'(3'U5')"
    result = classify_exception(
        sequence_raw=raw,
        sequence_full="ACGUACGU3'(3'U5')",
        post_selex="The truncated aptamer contains a 3'-3' thymidine cap at the 3' end",
    )
    assert result.exception_class == CLASS_RECOVERABLE
    assert result.proposed_underlying_rna_sequence == "ACGUACGUU"
    assert "map_inverted_terminal_cap_to_base" in result.recovery_transformations
    assert result.modification_metadata_reason.startswith("source explicitly reports")


def test_recoverable_parenthetical_2f_maps_to_explicit_base() -> None:
    raw = "AG(2′FC)U"
    diagnostic = diagnose_sequence(sequence_full=raw.upper(), sequence_raw=raw)
    result = classify_exception(
        sequence_raw=raw,
        sequence_full=raw.upper(),
        diagnostic=diagnostic,
        additional="2′FC is 2′-flurocytosine",
        chemistry="2F-RNA",
        source_type="2'-fluoro-RNA",
    )
    assert result.exception_class == CLASS_RECOVERABLE
    assert result.proposed_underlying_rna_sequence == "AGCU"
    assert "map_2f_parenthetical_residue" in result.recovery_transformations
    assert result.recovery_confidence == "high"


def test_recoverable_curly_terminal_labels() -> None:
    raw = "5‘ACGUACGU3‘"
    result = classify_exception(sequence_raw=raw, sequence_full=raw)
    assert result.exception_class == CLASS_RECOVERABLE
    assert result.proposed_underlying_rna_sequence == "ACGUACGU"
    assert "remove_leading_five_prime_display_label" in result.recovery_transformations
    assert "remove_trailing_three_prime_display_label" in result.recovery_transformations


def test_recoverable_gcon_and_2ome_phosphorothioate() -> None:
    gcon = classify_exception(
        sequence_raw="5'ACGconGU3'",
        sequence_full="ACGCONGU",
        additional="Gcon is a conserved base essential for binding",
    )
    assert gcon.exception_class == CLASS_RECOVERABLE
    assert gcon.proposed_underlying_rna_sequence == "ACGGU"
    ome = classify_exception(
        sequence_raw="5'm(GA)ACUm(UsC)3'",
        sequence_full="M(GA)ACUM(USC)",
        post_selex="Transcribed with 2'-O-methyl terminal residues",
    )
    assert ome.exception_class == CLASS_RECOVERABLE
    assert ome.proposed_underlying_rna_sequence == "GAACUUC"


def test_genuine_iupac_ambiguity_is_not_recovered() -> None:
    raw = "5'ACGUACGY3'"
    full = "ACGUACGY"
    result = classify_exception(
        sequence_raw=raw,
        sequence_full=full,
        additional="Y = pyrimidine, R = purine",
    )
    assert result.exception_class == CLASS_IUPAC
    assert result.proposed_underlying_rna_sequence == ""
    assert result.recovery_confidence == "unresolved"
    assert result.suggested_review_action == "confirm_reject"


def test_numbered_n_run_is_degenerate_not_expanded() -> None:
    result = classify_exception(
        sequence_raw="5'ACGUN4GU3'",
        sequence_full="ACGUN4GU",
    )
    assert result.exception_class == CLASS_IUPAC
    assert result.proposed_underlying_rna_sequence == ""
    assert "N4" not in result.proposed_underlying_rna_sequence


def test_unknown_modified_residue_is_unresolved() -> None:
    result = classify_exception(
        sequence_raw="5'ACGXUGUA3'",
        sequence_full="ACGXUGUA",
        additional="contains a specialised modified residue X",
        chemistry="2F-RNA",
        source_type="2'-fluoro-RNA",
    )
    assert result.exception_class == CLASS_UNRESOLVED_MOD
    assert result.proposed_underlying_rna_sequence == ""
    assert result.suggested_review_action == "override_to_park"


def test_malformed_string_is_rejected() -> None:
    result = classify_exception(
        sequence_raw="ACGU@@@",
        sequence_full="ACGU@@@",
    )
    assert result.exception_class == CLASS_MALFORMED
    assert result.proposed_underlying_rna_sequence == ""
    assert result.suggested_review_action == "confirm_reject"


def test_cyrillic_lookalikes_are_malformed() -> None:
    result = classify_exception(
        sequence_raw="ACGUСGUA",
        sequence_full="ACGUСGUA",
        chemistry="2F-RNA",
        source_type="2'-fluoro-RNA",
    )
    assert result.exception_class == CLASS_MALFORMED
    assert result.proposed_underlying_rna_sequence == ""


def test_concatenated_entries_need_source_review() -> None:
    raw = "5'ACGUACGUAC3'\n5'UGCAUGCAUG3'"
    full = "ACGUACGUAC3'5'UGCAUGCAUG"
    result = classify_exception(sequence_raw=raw, sequence_full=full)
    assert result.exception_class == CLASS_NEEDS_REVIEW
    assert result.proposed_underlying_rna_sequence == ""
    assert result.suggested_review_action == "needs_source_review"


def test_unknown_characters_are_never_silently_deleted() -> None:
    recovery = attempt_recovery("5'ACGXUGUA3'")
    assert recovery.sequence == ""
    assert "X" in recovery.leftover_characters
    assert "delete_unknown" not in recovery.transformations
    assert all("delete" not in name for name in recovery.transformations)
    result = classify_exception(sequence_raw="5'ACGXUGUA3'", sequence_full="ACGXUGUA")
    assert result.proposed_underlying_rna_sequence == ""
    assert "X" not in result.proposed_underlying_rna_sequence or result.proposed_underlying_rna_sequence == ""


def test_recovery_does_not_invent_an_iupac_base() -> None:
    recovery = attempt_recovery("ACGUACGN")
    assert recovery.sequence == ""
    assert "N" in recovery.leftover_characters


def test_determinism_same_input_same_output() -> None:
    raw = "5‘AG(2′FU)C3‘"
    first = classify_exception(sequence_raw=raw, sequence_full=raw.upper())
    second = classify_exception(sequence_raw=raw, sequence_full=raw.upper())
    assert first == second
    diag1 = diagnose_sequence(sequence_full=raw.upper(), sequence_raw=raw)
    diag2 = diagnose_sequence(sequence_full=raw.upper(), sequence_raw=raw)
    assert diag1 == diag2


def test_diagnostic_does_not_transform_characters() -> None:
    full = "AG(2′FC)U"
    diagnostic = diagnose_sequence(sequence_full=full, sequence_raw=full)
    assert diagnostic.contains_parenthetical_modification is True
    assert "(" in "".join(diagnostic.unexpected_characters) or diagnostic.contains_parenthetical_modification
    # Original string is not mutated; unexpected characters still include the token alphabet.
    assert "2" in diagnostic.unexpected_characters or "F" in diagnostic.unexpected_characters


def test_select_cohort_requires_rna_and_expected_split() -> None:
    rows = []
    for i in range(8):
        rows.append(
            {
                "record_id": f"utexas:{i:04d}",
                "primary_reason": "ambiguous_bases",
                "molecule_type": "RNA",
            }
        )
    for i in range(8, 31):
        rows.append(
            {
                "record_id": f"utexas:{i:04d}",
                "primary_reason": "invalid_alphabet",
                "molecule_type": "RNA",
            }
        )
    selected = select_exception_cohort(rows)
    assert len(selected) == 31
    with pytest.raises(AlphabetExceptionError):
        bad = list(rows)
        bad[0]["molecule_type"] = "ssDNA"
        select_exception_cohort(bad)


def test_review_row_leaves_human_actions_blank() -> None:
    decision = {
        "record_id": "utexas:demo",
        "native_id": "demo",
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "alphabet_as_reported": "invalid",
        "qc_flags": "invalid_character",
        "proposed_decision": "proposed_reject",
        "primary_reason": "invalid_alphabet",
        "target_name_raw": "demo_target",
    }
    detail = {
        "aptamer_name": "demo-apt",
        "sequence_raw": "5‘ACGUACGU3‘",
        "sequence_full": "5‘ACGUACGU3‘",
        "sequence_core": "5‘ACGUACGU3‘",
        "publication": "Demo 2020",
    }
    metadata = {
        "utexas_type_of_nucleic_acid": "ssRNA",
        "utexas_name_of_aptamer": "demo-apt",
        "utexas_post_selex_modifications": "",
        "utexas_additional_information": "",
        "utexas_sequence_length": "8",
        "utexas_gc_content": "0.5",
        "utexas_journal_doi": "10.0/demo",
        "utexas_link_to_pubmed_entry": "",
        "utexas_pool_type": "",
        "utexas_pool_random_region": "",
        "utexas_application_as_quoted": "",
        "utexas_serial_number": "1",
    }
    row = build_review_row(decision=decision, detail=detail, metadata=metadata)
    assert row["review_action"] == ""
    assert row["reviewer_note"] == ""
    assert row["reviewer_initials"] == ""
    assert row["exception_class"] == CLASS_RECOVERABLE
    assert set(row) == set(REVIEW_COLUMNS)


def test_summary_is_sequence_safe() -> None:
    rows = [
        {
            "primary_reason": "invalid_alphabet",
            "exception_class": CLASS_RECOVERABLE,
            "chemistry": "RNA",
            "source_type_of_nucleic_acid": "ssRNA",
            "recovery_confidence": "high",
            "proposed_underlying_rna_sequence": "ACGUACGU",
            "recovered_passes_length_policy": "no",
            "suggested_later_disposition": "recover",
            "suggested_review_action": "accept_recovered_sequence",
            "modification_metadata_supports_interpretation": "no",
            "contains_iupac_ambiguity": "no",
            "contains_parenthetical_modification": "no",
            "contains_bracketed_modification": "no",
            "contains_digit_annotation": "no",
            "contains_star_or_linkage_marker": "no",
            "contains_nonstandard_base_symbol": "no",
            "contains_internal_separator": "no",
            "contains_other_notation": "yes",
            "contains_cyrillic_lookalike": "no",
            "contains_concatenated_entries": "no",
            "review_action": "",
        }
    ]
    # Pad to the expected 31 rows without embedding long sequences in the summary path.
    while len(rows) < 31:
        extra = dict(rows[0])
        extra["primary_reason"] = "ambiguous_bases" if len(rows) < 9 else "invalid_alphabet"
        extra["exception_class"] = CLASS_IUPAC
        extra["proposed_underlying_rna_sequence"] = ""
        extra["recovery_confidence"] = "unresolved"
        extra["suggested_later_disposition"] = "reject"
        extra["suggested_review_action"] = "confirm_reject"
        extra["contains_iupac_ambiguity"] = "yes"
        rows.append(extra)
    text = build_exception_summary(
        rows,
        raw_sha_before="a" * 64,
        raw_sha_after="a" * 64,
        s2_hash_before="b" * 64,
        s2_hash_after="b" * 64,
        s3_hash_before="c" * 64,
        s3_hash_after="c" * 64,
        checkpoint_actions_populated=0,
        deterministic_rerun_ok=True,
    )
    assert "ACGUACGU" not in text
    assert "total exceptions = `31`" in text
    assert "CHECKPOINT-1 closed: `no`" in text
    assert "Canonical sequences changed: `no`" in text


def test_apply_approved_recovery_requires_accept_decision() -> None:
    from adapters.utexas_alphabet_exceptions import (
        AlphabetResolution,
        SUGGESTED_CONFIRM_REJECT,
        apply_approved_recovery,
    )

    resolution = AlphabetResolution(
        record_id="utexas:row_0001",
        decision=SUGGESTED_CONFIRM_REJECT,
        transformation_profile="",
        expected_recovered_length=None,
        review_note="Genuine IUPAC/degenerate sequence",
    )
    with pytest.raises(AlphabetExceptionError):
        apply_approved_recovery("ACGUACGY", resolution)


def test_approved_recovery_is_deterministic_and_length_checked() -> None:
    from adapters.utexas_alphabet_exceptions import (
        AlphabetResolution,
        SUGGESTED_ACCEPT_RECOVERED,
        apply_approved_recovery,
        attempt_recovery,
    )

    raw = "5'ACGUACGU3'"
    first = attempt_recovery(raw)
    assert first.confidence == "high"
    assert first.sequence == "ACGUACGU"
    resolution = AlphabetResolution(
        record_id="utexas:row_0001",
        decision=SUGGESTED_ACCEPT_RECOVERED,
        transformation_profile="|".join(first.transformations),
        expected_recovered_length=len(first.sequence),
        review_note="Approved at the alphabet-normalisation level only",
    )
    recovered = apply_approved_recovery(raw, resolution)
    assert recovered.sequence == first.sequence
    assert recovered.sequence == apply_approved_recovery(raw, resolution).sequence
    wrong_length = AlphabetResolution(
        record_id="utexas:row_0001",
        decision=SUGGESTED_ACCEPT_RECOVERED,
        transformation_profile="|".join(first.transformations),
        expected_recovered_length=len(first.sequence) + 1,
        review_note="Approved at the alphabet-normalisation level only",
    )
    with pytest.raises(AlphabetExceptionError):
        apply_approved_recovery(raw, wrong_length)
