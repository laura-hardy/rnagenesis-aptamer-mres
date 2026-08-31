"""Tests for the RiboAptamer S3 eligibility adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
RiboAptamer source sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.riboaptamer_s3 import (  # noqa: E402
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    REASON_PRIORITY_RULE,
    RiboAptamerS3Error,
    actual_core_length,
    apply_random_accept_audit,
    classify_riboaptamer_record,
    index_constant_proposals,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "riboaptamer.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _s2(
    *,
    sequence: str = "ACGUAC",
    molecule_type: str = "RNA",
    alphabet: str = "RNA",
    chemistry: str = "RNA",
    target: str = "",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "n/a",
    construct_scope: str = "unknown",
    native_id: str = "1",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"riboaptamer:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": construct_scope if sequence else "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": target,
            "source_db": "riboaptamer",
            "source_dataset": "riboaptamer_full_2026-08",
            "contributing_sources": "riboaptamer",
            "contributing_datasets": "riboaptamer_full_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "pubmed_id": "11111111",
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "target_name_raw": canonical["target_name_raw"],
        "source_type": "Proteins",
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
    }


def _meta(
    canonical: dict[str, str],
    *,
    source_type: str = "Proteins",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "riboaptamer_native_id": canonical["native_id"],
        "riboaptamer_sequence_name": f"seq-{canonical['native_id']}",
        "riboaptamer_aptamer_name": f"name-{canonical['native_id']}",
        "riboaptamer_category": "Natural",
        "riboaptamer_type": source_type,
        "riboaptamer_article_name": "Demo article",
    }
    row.update(overrides)
    return row


def _classify(
    canonical: dict[str, str],
    *,
    source_type: str = "Proteins",
    proposals: list[dict[str, str]] | None = None,
    **meta: str,
):
    return classify_riboaptamer_record(
        canonical,
        _qc(canonical),
        _meta(canonical, source_type=source_type, **meta),
        policy=POLICY,
        proposals=proposals or (),
    )


def test_policy_defers_target_evidence_leakage() -> None:
    assert POLICY.defer_target_classification is True
    assert POLICY.defer_evidence_scoring is True
    assert POLICY.defer_leakage_exclusion is True
    assert POLICY.sequence_leakage_matching_enabled is False
    assert POLICY.target_leakage_matching_enabled is False
    assert POLICY.random_accept_audit_size == 30
    assert POLICY.random_seed == 42


def test_valid_rna_is_technically_eligible_with_empty_target() -> None:
    result = _classify(_s2(sequence=_rna(40), native_id="ok", target=""))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert (
        result.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    )
    assert result.primary_route == PRIMARY_ROUTE_ELIGIBLE
    assert result.rejection_row is None


def test_source_type_does_not_park_small_molecules() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="sm"),
        source_type="Small molecules",
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.park_row is None
    assert result.eligibility.primary_reason != EligibilityReason.NON_PROTEIN_TARGET_PARKED


def test_source_type_does_not_park_cells_or_nucleic_acids() -> None:
    for source_type in ("Cells", "Nucleic acids"):
        result = _classify(
            _s2(sequence=_rna(40), native_id=source_type.replace(" ", "_")),
            source_type=source_type,
        )
        assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
        assert result.park_row is None


def test_length_uses_actual_core_not_s2_qc_flags() -> None:
    sequence = _rna(101)
    canonical = _s2(
        sequence=sequence,
        native_id="long_invalid_path",
        alphabet="invalid",
        qc_flags="invalid_character",
    )
    assert "core_above_max_length" not in canonical["qc_flags"]
    assert actual_core_length(canonical) == 101
    result = _classify(canonical)
    assert EligibilityReason.LENGTH_OUT_OF_RANGE in result.eligibility.all_reasons
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT


def test_length_19_rejects() -> None:
    result = _classify(_s2(sequence=_rna(19), native_id="short"))
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.manual_review_required is False


def test_length_20_and_100_are_accepted_boundaries() -> None:
    low = _classify(_s2(sequence=_rna(20), native_id="b20"))
    high = _classify(_s2(sequence=_rna(100), native_id="b100"))
    assert low.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert high.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.LOWER_LENGTH_BOUNDARY in low.eligibility.all_reasons
    assert EligibilityReason.UPPER_LENGTH_BOUNDARY in high.eligibility.all_reasons
    assert low.eligibility.manual_review_required is True
    assert high.eligibility.manual_review_required is True
    assert low.decision["review_batch"] == "03_length_boundary"


def test_length_101_rejects_even_without_length_qc_flag() -> None:
    canonical = _s2(sequence=_rna(101), native_id="over", qc_flags="")
    result = _classify(canonical)
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE


def test_ambiguous_bases_automatic_reject() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="amb", qc_flags="ambiguous_base")
    )
    assert result.eligibility.primary_reason == EligibilityReason.AMBIGUOUS_BASES
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.manual_review_required is False


def test_invalid_alphabet_automatic_reject() -> None:
    result = _classify(
        _s2(
            sequence="ACGUACGUACGUACGUACGUACGUXXXX",
            native_id="inv",
            alphabet="invalid",
            qc_flags="invalid_character",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.INVALID_ALPHABET
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.manual_review_required is False


def test_mixed_t_u_automatic_reject() -> None:
    result = _classify(
        _s2(sequence=_rna(40), native_id="mix", qc_flags="mixed_t_u")
    )
    assert result.eligibility.primary_reason == EligibilityReason.MIXED_T_AND_U
    assert result.eligibility.manual_review_required is False


def test_truncated_alignment_overlap_goes_to_review() -> None:
    """SelB-like overlap: truncation + gap + invalid must enter CHECKPOINT-1."""
    seq = "ACGUACGU...ACGU-ACGU1234ACGUACGU"
    result = _classify(
        _s2(
            sequence=seq,
            native_id="selb",
            alphabet="invalid",
            qc_flags="alignment_gaps|invalid_character|truncated_sequence",
        )
    )
    reasons = set(result.eligibility.all_reasons)
    assert EligibilityReason.TRUNCATED_SEQUENCE in reasons
    assert EligibilityReason.ALIGNMENT_GAPS in reasons
    assert EligibilityReason.INVALID_ALPHABET in reasons
    assert result.eligibility.primary_reason == EligibilityReason.TRUNCATED_SEQUENCE
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert "judgement_dependent_technical" in result.decision["checkpoint_review_reasons"]
    assert "invalid_alphabet" in result.decision["secondary_reasons"]
    assert REASON_PRIORITY_RULE


def test_known_t7_goes_to_review_and_is_not_trimmed() -> None:
    sequence = _rna(40)
    proposal = {
        "proposal_id": "riboaptamer:t7:known_motif:five_prime:t7_promoter_minimal",
        "experiment_group_id": "riboaptamer:t7",
        "proposal_source": "known_motif",
        "side": "five_prime",
        "motif_id": "t7_promoter_minimal",
        "motif_length": "18",
        "applied": "false",
        "records_considered": "1",
        "support": "",
    }
    canonical = _s2(
        sequence=sequence,
        native_id="t7",
        qc_flags="known_promoter_detected|trim_requires_review|constants_suspected_unresolved",
        trim_status="constants_suspected_unresolved",
    )
    result = _classify(canonical, proposals=[proposal])
    assert result.canonical["sequence_core"] == sequence
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.KNOWN_MOTIF_PROPOSAL in result.eligibility.all_reasons
    assert EligibilityReason.PRIMER_LIKE not in result.eligibility.all_reasons
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "02_constant_region_proposal"
    assert result.decision["constant_proposal_sources"] == "known_motif"


def test_group_consensus_proposal_is_forbidden() -> None:
    with pytest.raises(RiboAptamerS3Error, match="group_consensus"):
        index_constant_proposals(
            [_s2(sequence=_rna(40), native_id="g")],
            [
                {
                    "proposal_id": "group-1",
                    "experiment_group_id": "synthetic-group",
                    "proposal_source": "group_consensus",
                    "side": "five_prime",
                    "motif_length": "12",
                }
            ],
        )


def test_ssdna_molecule_raises_under_rna_contract() -> None:
    with pytest.raises(RiboAptamerS3Error, match="experimental RNA"):
        _classify(_s2(sequence=_rna(40), native_id="dna", molecule_type="ssDNA"))


def test_missing_sequence_rejects() -> None:
    result = _classify(_s2(sequence="", native_id="miss"))
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert result.eligibility.manual_review_required is False


def test_s4_fields_remain_untouched() -> None:
    canonical = _s2(sequence=_rna(40), native_id="s4")
    result = _classify(canonical)
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field_name, "") == ""


def test_random_accept_audit_is_deterministic() -> None:
    rows = []
    details = {}
    for i in range(40):
        classified = _classify(_s2(sequence=_rna(40), native_id=str(i)))
        rows.append(classified.decision)
        details[classified.decision["record_id"]] = {
            "record_id": classified.decision["record_id"],
            "secondary_reasons": "",
            "checkpoint_review_reasons": "",
            "manual_review_required": "false",
            "manual_review_priority": "none",
            "review_batch": "",
        }
    copies_a = [dict(row) for row in rows]
    copies_b = [dict(row) for row in rows]
    details_a = {key: dict(value) for key, value in details.items()}
    details_b = {key: dict(value) for key, value in details.items()}
    first, pool, shortfall = apply_random_accept_audit(
        copies_a,
        details_a,
        seed=42,
        sample_size=30,
    )
    second, pool2, shortfall2 = apply_random_accept_audit(
        copies_b,
        details_b,
        seed=42,
        sample_size=30,
    )
    assert first == second == 30
    assert pool == pool2 == 40
    assert shortfall == shortfall2 == 0
    selected = [
        row["record_id"]
        for row in copies_a
        if "random_accept_audit" in row.get("secondary_reasons", "")
    ]
    selected_b = [
        row["record_id"]
        for row in copies_b
        if "random_accept_audit" in row.get("secondary_reasons", "")
    ]
    assert selected == selected_b
    assert len(selected) == 30
    assert len(set(selected)) == 30


def test_rejection_reason_is_closed_vocabulary() -> None:
    result = _classify(_s2(sequence=_rna(19), native_id="vocab"))
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "length_out_of_range"
    assert result.rejection_row["stage"] == "S3"
