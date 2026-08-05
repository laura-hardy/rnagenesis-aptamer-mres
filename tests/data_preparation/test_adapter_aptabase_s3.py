"""Tests for the AptaBase S3 eligibility adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not import the
legacy cleaner or read real AptaBase source data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase_s3 import classify_aptabase_record  # noqa: E402
from common.corpus_schema import empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    ExclusionReference,
    SequenceLeakageIndex,
    load_eligibility_policy,
    load_target_alias_rules,
)
from common.leakage_matching import comparison_form  # noqa: E402

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptabase.json"
)
ALIASES = load_target_alias_rules(
    REPO_ROOT / "config" / "leakage_target_aliases.csv"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _s2(
    *,
    sequence: str = "ACGUAC",
    molecule_type: str = "RNA",
    alphabet: str = "RNA",
    target: str = "demo_target",
    qc_flags: str = "",
    trim_status: str = "not_trimmed",
    native_id: str = "1",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptabase:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": (
                "missing" if sequence == "" else "full_equals_core_untrimmed"
            ),
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "molecule_type": molecule_type,
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "target_name_raw": target,
            "source_db": "aptabase",
            "source_dataset": "demo_ds",
            "contributing_sources": "aptabase",
            "contributing_datasets": "demo_ds",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "qc_flags": qc_flags,
            "notes": "",
        }
    )
    if sequence == "":
        record["molecule_type"] = "unknown"
        record["alphabet_as_reported"] = "missing"
    record.update(overrides)
    return record


def _qc(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": f"name-{canonical['native_id']}",
        "target_name_raw": canonical["target_name_raw"],
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "molecule_type": canonical["molecule_type"],
        "qc_flags": canonical["qc_flags"],
    }
    row.update(overrides)
    return row


def _meta(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "aptabase_aptamer_name": f"name-{canonical['native_id']}",
        "aptabase_target_general": canonical["target_name_raw"],
        "aptabase_target_specific": "",
        "aptabase_record_validity": "valid",
        "aptabase_parse_warnings": "",
        "aptabase_molecule_type_inferred": "",
    }
    row.update(overrides)
    return row


def _empty_index() -> SequenceLeakageIndex:
    return SequenceLeakageIndex(references=())


def _classify(
    canonical: dict[str, str],
    *,
    leakage: SequenceLeakageIndex | None = None,
    meta_overrides: dict[str, str] | None = None,
    qc_overrides: dict[str, str] | None = None,
):
    return classify_aptabase_record(
        canonical,
        _qc(canonical, **(qc_overrides or {})),
        _meta(canonical, **(meta_overrides or {})),
        policy=POLICY,
        leakage_index=leakage if leakage is not None else _empty_index(),
        target_alias_rules=ALIASES,
    )


def test_15_eligible_rna_accepts() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    )


def test_1_sequence_leakage_overrides_accept() -> None:
    seq = _rna(25)
    index = SequenceLeakageIndex(
        references=(
            ExclusionReference(
                exclusion_id="ex1",
                reference_id="ref1",
                target_name="NDM-1",
                evaluation_role="positive",
                sequence_compare_full=comparison_form(seq),
                sequence_compare_core=comparison_form(seq),
                status="resolved",
            ),
        )
    )
    result = _classify(_s2(sequence=seq), leakage=index)
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE
    )


def test_2_target_leakage_overrides_accept() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq, target="NDM-1"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.EVALUATION_TARGET_LEAKAGE
    )


def test_3_sequence_leakage_overrides_missing_sequence_secondary() -> None:
    # Missing sequence cannot leak by sequence; ensure target leakage still
    # outranks other secondary conditions when present with a nonempty sequence.
    seq = _rna(25)
    index = SequenceLeakageIndex(
        references=(
            ExclusionReference(
                exclusion_id="ex1",
                reference_id="ref1",
                target_name="NDM-1",
                evaluation_role="positive",
                sequence_compare_full=comparison_form(seq),
                sequence_compare_core=comparison_form(seq),
                status="resolved",
            ),
        )
    )
    result = _classify(
        _s2(sequence=seq, target="NDM-1", molecule_type="unknown", alphabet="DNA_T"),
        leakage=index,
    )
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE
    )
    assert EligibilityReason.EVALUATION_TARGET_LEAKAGE in (
        result.eligibility.secondary_reasons
    )


def test_4_missing_sequence_rejects() -> None:
    result = _classify(_s2(sequence="", target=""))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE


def test_5_and_30_source_invalid_rejects() -> None:
    seq = _rna(25)
    result = _classify(
        _s2(sequence=seq),
        meta_overrides={"aptabase_record_validity": "invalid"},
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert (
        result.eligibility.primary_reason == EligibilityReason.SOURCE_RECORD_INVALID
    )


def test_31_valid_with_warnings_does_not_auto_reject() -> None:
    seq = _rna(25)
    result = _classify(
        _s2(sequence=seq),
        meta_overrides={"aptabase_record_validity": "valid_with_warnings"},
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT


def test_6_and_38_core_below_minimum_rejects() -> None:
    result = _classify(_s2(sequence="ACGUACGUAC"))  # 10 nt
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.CORE_BELOW_MINIMUM


def test_7_invalid_sequence_parks() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq, qc_flags="invalid_character"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.INVALID_SEQUENCE_REQUIRES_REVIEW
    )


def test_8_ambiguous_sequence_parks() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq, qc_flags="ambiguous_base"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW
    )


def test_9_mixed_t_u_parks() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq, qc_flags="mixed_t_u"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.MIXED_T_U_REQUIRES_REVIEW
    )


def test_10_and_36_trim_review_parks() -> None:
    seq = _rna(25)
    result = _classify(
        _s2(
            sequence=seq,
            trim_status="review_required",
            qc_flags="known_promoter_detected|trim_requires_review",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.TRIM_OR_CONSTRUCT_REQUIRES_REVIEW
    )


def test_11_and_37_core_above_maximum_parks() -> None:
    seq = _rna(120)
    result = _classify(_s2(sequence=seq))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW
    )


def test_12_and_39_ssdna_parks_never_accepts() -> None:
    seq = ("ACGT" * 8)[:32]
    result = _classify(_s2(sequence=seq, molecule_type="ssDNA", alphabet="DNA_T"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING
    )


def test_13_and_40_unknown_molecule_parks_never_accepts() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq, molecule_type="unknown", alphabet="DNA_T"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    )


def test_14_and_35_missing_target_parks() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq, target=""))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW
    )


def test_16_secondary_reasons_do_not_change_primary() -> None:
    result = _classify(_s2(sequence="", target="", molecule_type="unknown"))
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert EligibilityReason.MOLECULE_TYPE_UNRESOLVED in (
        result.eligibility.secondary_reasons
    )
    assert EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW in (
        result.eligibility.secondary_reasons
    )


def test_32_legacy_molecule_cannot_promote_unknown() -> None:
    seq = _rna(25)
    result = _classify(
        _s2(sequence=seq, molecule_type="unknown", alphabet="DNA_T"),
        meta_overrides={"aptabase_molecule_type_inferred": "RNA_like_sequence"},
    )
    assert result.eligibility.proposed_decision != EligibilityDecision.PROPOSED_ACCEPT
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    )


def test_33_dna_t_accepted_only_for_experimental_rna() -> None:
    seq = _rna(25)  # RNA alphabet core after approved T→U
    ok = _classify(_s2(sequence=seq, molecule_type="RNA", alphabet="DNA_T"))
    assert ok.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT

    dna_core = ("ACGT" * 8)[:32]
    bad = _classify(
        _s2(sequence=dna_core, molecule_type="ssDNA", alphabet="DNA_T")
    )
    # Explicit ssDNA with DNA_T must never be promoted to accept.
    assert bad.eligibility.proposed_decision != EligibilityDecision.PROPOSED_ACCEPT
    assert (
        bad.eligibility.primary_reason
        == EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING
    )


def test_34_rna_sequence_valid_length_accepts() -> None:
    seq = _rna(40)
    result = _classify(_s2(sequence=seq))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT


def test_41_exactly_one_decision_and_primary() -> None:
    seq = _rna(25)
    result = _classify(_s2(sequence=seq))
    assert isinstance(result.eligibility.proposed_decision, EligibilityDecision)
    assert isinstance(result.eligibility.primary_reason, EligibilityReason)
    assert result.decision["proposed_decision"]
    assert result.decision["primary_reason"]
    assert "|" not in result.decision["primary_reason"]


def test_missing_sequence_plus_unresolved_molecule_priority_none() -> None:
    result = _classify(_s2(sequence="", target="demo_target", molecule_type="unknown"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.eligibility.manual_review_priority.value == "none"
    assert result.eligibility.manual_review_required is False
    assert result.decision["manual_review_priority"] == "none"
    assert result.decision["manual_review_required"] == "false"
    assert EligibilityReason.MOLECULE_TYPE_UNRESOLVED in (
        result.eligibility.secondary_reasons
    )


def test_missing_sequence_plus_missing_target_priority_none() -> None:
    result = _classify(_s2(sequence="", target=""))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.eligibility.manual_review_priority.value == "none"
    assert result.eligibility.manual_review_required is False
    assert EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW in (
        result.eligibility.secondary_reasons
    )


def test_missing_sequence_retains_deterministic_secondary_reasons() -> None:
    result = _classify(_s2(sequence="", target="", molecule_type="unknown"))
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    secondaries = list(result.eligibility.secondary_reasons)
    assert EligibilityReason.MOLECULE_TYPE_UNRESOLVED in secondaries
    assert EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW in secondaries
    assert result.decision["secondary_reasons"] == "|".join(
        reason.value for reason in secondaries
    )


def test_missing_sequence_manual_review_required_false() -> None:
    result = _classify(_s2(sequence=""))
    assert result.eligibility.manual_review_required is False
    assert result.decision["manual_review_required"] == "false"


def test_source_invalid_reject_remains_high_priority() -> None:
    seq = _rna(25)
    result = _classify(
        _s2(sequence=seq),
        meta_overrides={"aptabase_record_validity": "invalid"},
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert (
        result.eligibility.primary_reason == EligibilityReason.SOURCE_RECORD_INVALID
    )
    assert result.eligibility.manual_review_priority.value == "high"
    assert result.eligibility.manual_review_required is True


def test_leakage_reject_remains_high_priority() -> None:
    seq = _rna(25)
    index = SequenceLeakageIndex(
        references=(
            ExclusionReference(
                exclusion_id="ex1",
                reference_id="ref1",
                target_name="NDM-1",
                evaluation_role="positive",
                sequence_compare_full=comparison_form(seq),
                sequence_compare_core=comparison_form(seq),
                status="resolved",
            ),
        )
    )
    result = _classify(_s2(sequence=seq), leakage=index)
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE
    )
    assert result.eligibility.manual_review_priority.value == "high"
    assert result.eligibility.manual_review_required is True


def test_short_nonmissing_reject_retains_configured_priority() -> None:
    result = _classify(_s2(sequence="ACGUACGUAC"))  # 10 nt
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.CORE_BELOW_MINIMUM
    # Short nonmissing rejects are not covered by the missing-sequence rule.
    assert result.eligibility.manual_review_priority.value == "low"
    assert result.decision["proposed_decision"] == "proposed_reject"
    assert result.decision["primary_reason"] == "core_below_minimum"


def test_missing_sequence_decision_and_primary_unchanged() -> None:
    result = _classify(_s2(sequence="", target="", molecule_type="unknown"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.decision["proposed_decision"] == "proposed_reject"
    assert result.decision["primary_reason"] == "missing_sequence"
